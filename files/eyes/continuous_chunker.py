"""ContinuousChunker — streaming confidence-based delivery detector.

Replaces v3's hard-threshold rules (4 s anchor window, ≥2 frame count,
fixed cluster-merge gaps) with the validated v3.2 confidence pipeline
ported from
``files/scripts/broadcast_mode_tuning/simulate_confidence_chunker.py``:

  1. Each ingested frame is scored by
     :func:`eyes.chunker_v3.score_frame_confidence` →
     ``{label: confidence}`` over six labels.  Every frame becomes an
     anchor (the top-scoring label is its classification).
  2. :func:`eyes.chunker_v3.demote_sandwiched_anchors` corrects
     single-frame structural sandwiches.
  3. :func:`eyes.chunker_v3.find_clusters` walks DELIVERY anchors with
     inertia (no fixed time windows), merging overlapping walks.
  4. :func:`eyes.chunker_v3.cluster_level_sandwich_reject` discards
     clusters bracketed by the same non-DELIVERY label on both sides.
  5. :func:`eyes.chunker_v3.cluster_rejection_v31` applies in-cluster
     v3.1 rules (replay overlay, crowd sandwich, close-up dominated).
  6. ``min_clip_duration_s`` / ``max_clip_duration_s`` clamp,
     ``min_event_gap_s`` dedups, ``min_confidence`` is the cluster's
     walk-strength threshold (was a 0–1 normalized confidence; default
     stays 0.65).

Streaming control: each :meth:`ingest` re-runs the pipeline on the
rolling buffer.  A cluster is eligible to emit only when at least
``_STABLE_MARGIN`` frames have arrived after its end (so the walk
inertia can't extend it further).  Emitted clusters are tracked by
their start timestamp so subsequent ingests don't re-fire them.
"""
from __future__ import annotations

import collections
import logging
from dataclasses import dataclass, field
from typing import Callable, Deque, Optional

from eyes.chunker_v3 import (
    cluster_level_sandwich_reject as _cluster_level_sandwich_reject,
    cluster_rejection_v31 as _cluster_rejection_v31,
    find_all_anchors,
    find_clusters,
    has_speed_alone,
    has_speed_with_score,
    score_frame_confidence,
)


_BUFFER_RETENTION_S = 60.0
_BUFFER_MAX_FRAMES = 1024
_DEFAULT_MIN_CONFIDENCE = 0.65
# Frames after a cluster's end_idx required before we trust the cluster
# bounds.  walk_chunk's Case B / Case C lookahead is 2-3 frames; a
# margin of 3 means a cluster with end_idx == latest_idx-3 has been
# fully decided by the algorithm and can be safely emitted.
_STABLE_MARGIN = 3
# Sub-clusters within this many seconds of each other are coalesced
# before v3.1 / sandwich rejection runs, so a replay-overlay frame
# 2 s outside a sub-cluster still invalidates the cluster.  Mirrors
# ``simulate_confidence_chunker.py`` § coalesce.
_COALESCE_GAP_S = 5.0
# Look this far past the cluster end for a speed-with-score overlay
# (Scout often picks up the post-delivery scoreboard rendering a few
# frames after the action concludes).  Within this window a speed-
# with-score frame CONFIRMS the cluster as a real delivery.
_SPEED_LOOKAHEAD_S = 15.0

_log = logging.getLogger("continuous_chunker")


@dataclass
class DeliveryDetectedEvent:
    """One closed DELIVERY cluster.  Emitted by :class:`ContinuousChunker`."""

    start_ts: float
    end_ts: float
    duration_s: float
    anchor_frames: int
    confidence_score: float
    labels: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "start_ts": round(self.start_ts, 3),
            "end_ts": round(self.end_ts, 3),
            "duration_s": round(self.duration_s, 3),
            "anchor_frames": self.anchor_frames,
            "confidence_score": round(self.confidence_score, 3),
            "labels": list(self.labels),
        }


EventSink = Callable[[DeliveryDetectedEvent], None]
StateTraceSink = Callable[[str, str, dict], None]


class ContinuousChunker:
    """Confidence-walk streaming delivery detector.

    Per-frame :meth:`ingest` returns a :class:`DeliveryDetectedEvent`
    whenever a stable DELIVERY cluster closes (else ``None``).  When
    ``event_sink`` is supplied, the same event is also pushed to that
    callback.

    Tunables:
        min_clip_duration_s   default 4.0 — clamp lower bound on
                              emitted clip duration.
        max_clip_duration_s   default 20.0 — clamp upper bound.
        min_event_gap_s       default 4.0 — dedup vs prior emission.
        min_confidence        default 0.65 — cluster walk-strength
                              threshold (the cumulative strength
                              walk_chunk reports).
    """

    def __init__(
            self,
            *,
            min_clip_duration_s: float = 4.0,
            max_clip_duration_s: float = 20.0,
            min_event_gap_s: float = 4.0,
            min_confidence: float = _DEFAULT_MIN_CONFIDENCE,
            event_sink: Optional[EventSink] = None,
            state_trace_sink: Optional[StateTraceSink] = None,
    ) -> None:
        self.min_clip_duration_s = float(min_clip_duration_s)
        self.max_clip_duration_s = float(max_clip_duration_s)
        self.min_event_gap_s = float(min_event_gap_s)
        self.min_confidence = float(min_confidence)
        self._event_sink = event_sink
        self._state_trace_sink = state_trace_sink

        # Each entry: {ts, desc, v2_tag, score} — score derived once at
        # ingest time so the pipeline can be re-run cheaply.
        self._buffer: Deque[dict] = collections.deque(
            maxlen=_BUFFER_MAX_FRAMES)
        self._emitted_starts: set[float] = set()
        self._last_event_end_ts: Optional[float] = None
        self._stats = {
            "frames_ingested": 0,
            "events_emitted": 0,
            "events_suppressed_dedup": 0,
            "events_suppressed_short": 0,
            "events_suppressed_low_confidence": 0,
            "events_suppressed_v31": 0,
            "events_suppressed_cluster_sandwich": 0,
            "events_suppressed_speed_alone": 0,
            "events_confirmed_speed_with_score": 0,
        }

    @property
    def state(self) -> str:
        """Compatibility shim — the v3.2 confidence pipeline has no
        state machine.  Always returns ``"IDLE"``."""
        return "IDLE"

    def stats(self) -> dict:
        return dict(self._stats)

    def ingest(
            self,
            ts: float,
            *,
            prod_cam: str | None = None,
            prod_phase: str | None = None,
            v2_broadcast_tag: str | None = None,
            v2_class: str | None = None,
            open_desc: str | None = None,
    ) -> Optional[DeliveryDetectedEvent]:
        """Feed one classified frame.  Returns event when a stable
        DELIVERY cluster closes."""
        try:
            ts_f = float(ts)
        except (TypeError, ValueError):
            return None

        score = score_frame_confidence(open_desc, v2_broadcast_tag)
        self._buffer.append({
            "ts": ts_f,
            "desc": open_desc or "",
            "v2_tag": (v2_broadcast_tag or "").upper(),
            "score": score,
        })
        self._prune(ts_f)
        self._stats["frames_ingested"] += 1
        # Garbage-collect emitted_starts that have aged out of the buffer.
        if self._buffer:
            cutoff = self._buffer[0]["ts"]
            self._emitted_starts = {
                t for t in self._emitted_starts if t >= cutoff}

        return self._maybe_emit()

    def _prune(self, now: float) -> None:
        cutoff = now - _BUFFER_RETENTION_S
        while self._buffer and self._buffer[0]["ts"] < cutoff:
            self._buffer.popleft()

    def _maybe_emit(self) -> Optional[DeliveryDetectedEvent]:
        n = len(self._buffer)
        if n < 3:
            return None

        # Snapshot frames so demotion mutations don't leak across
        # ingests; raw scores in self._buffer stay pristine.
        frames = [{
            "ts": f["ts"],
            "desc": f["desc"],
            "v2_tag": f["v2_tag"],
            "score": dict(f["score"]),
        } for f in self._buffer]

        clusters = find_clusters(frames)
        if not clusters:
            return None
        # Use the same (already-demoted) frames for anchor sandwich
        # detection so cluster-level sandwich sees the corrected labels.
        all_anchors = find_all_anchors(frames)

        # Coalesce sub-clusters within _COALESCE_GAP_S so v3.1 /
        # sandwich rejection sees full surrounding context.  Each
        # coalesced group is accepted/rejected as a unit; on accept,
        # we still emit each member separately.
        groups: list[list] = []
        for c in clusters:
            cs, ce, cS = c
            if not groups:
                groups.append([cs, ce, [c]])
                continue
            prev = groups[-1]
            prev_end_ts = frames[prev[1]]["ts"]
            curr_start_ts = frames[cs]["ts"]
            if curr_start_ts - prev_end_ts <= _COALESCE_GAP_S:
                prev[1] = max(prev[1], ce)
                prev[2].append(c)
            else:
                groups.append([cs, ce, [c]])

        latest_idx = n - 1
        for grp_s, grp_e, members in groups:
            # Group-level rejections evaluated once over the full span.
            grp_start_ts = frames[grp_s]["ts"]
            grp_end_ts = frames[grp_e]["ts"]

            # Speed-overlay isolation classifier (broadcast-side
            # signal).  Inspect the cluster window plus a 15 s
            # lookahead — Scout often picks up the post-delivery
            # speed-with-score overlay a few frames after the action
            # frame.  If any frame in this range has speed-with-score
            # the cluster is CONFIRMED as a real delivery and bypasses
            # v3.1 / sandwich rejection.  Conversely, if speed-alone
            # dominates the speed-bearing frames AND no
            # speed-with-score frame exists, the cluster is rejected.
            n_speed_score = 0
            n_speed_alone = 0
            speed_window_end_ts = grp_end_ts + _SPEED_LOOKAHEAD_S
            for f in frames:
                if f["ts"] < grp_start_ts:
                    continue
                if f["ts"] > speed_window_end_ts:
                    break
                desc = f.get("desc") or ""
                if has_speed_with_score(desc):
                    n_speed_score += 1
                elif has_speed_alone(desc):
                    n_speed_alone += 1
            speed_confirmed = n_speed_score >= 1
            speed_alone_dominant = (
                not speed_confirmed
                and n_speed_alone >= 1
                and n_speed_alone >= n_speed_score)

            if speed_confirmed:
                self._stats["events_confirmed_speed_with_score"] += 1
                _log.info(
                    "[CONTINUOUS-CHUNKER-CONFIRMED] reason=speed_with_score "
                    "start=%.3f end=%.3f members=%d",
                    grp_start_ts, grp_end_ts, len(members))
            elif speed_alone_dominant:
                for cs, _ce, _cS in members:
                    self._emitted_starts.add(frames[cs]["ts"])
                self._stats["events_suppressed_speed_alone"] += 1
                _log.info(
                    "[CONTINUOUS-CHUNKER-REJECTED] reason=speed_alone "
                    "alone=%d score=%d start=%.3f end=%.3f members=%d",
                    n_speed_alone, n_speed_score,
                    grp_start_ts, grp_end_ts, len(members))
                continue

            if not speed_confirmed:
                sandwich = _cluster_level_sandwich_reject(
                    grp_s, grp_e, all_anchors)
                if sandwich is not None:
                    for cs, _ce, _cS in members:
                        self._emitted_starts.add(frames[cs]["ts"])
                    self._stats["events_suppressed_cluster_sandwich"] += 1
                    _log.info(
                        "[CONTINUOUS-CHUNKER-REJECTED] reason=%s "
                        "start=%.3f end=%.3f members=%d",
                        sandwich, grp_start_ts, grp_end_ts, len(members))
                    continue
                v31_reason = _cluster_rejection_v31(frames, grp_s, grp_e)
                if v31_reason is not None:
                    for cs, _ce, _cS in members:
                        self._emitted_starts.add(frames[cs]["ts"])
                    self._stats["events_suppressed_v31"] += 1
                    _log.info(
                        "[CONTINUOUS-CHUNKER-REJECTED] reason=%s "
                        "start=%.3f end=%.3f members=%d",
                        v31_reason, grp_start_ts, grp_end_ts,
                        len(members))
                    continue

            for s, e, S in members:
                emitted = self._consider_member(
                    frames, s, e, S, latest_idx)
                if emitted is not None:
                    return emitted
        return None

    def _consider_member(
            self,
            frames: list[dict],
            s: int, e: int, S: float,
            latest_idx: int,
            ) -> Optional[DeliveryDetectedEvent]:
        # Stability gate: require at least _STABLE_MARGIN frames AFTER
        # the cluster end.  Without this, a cluster whose end sits at
        # the latest frame might extend further on the next ingest.
        if e > latest_idx - _STABLE_MARGIN:
            return None
        start_ts = frames[s]["ts"]
        end_ts = frames[e]["ts"]

        if start_ts in self._emitted_starts:
            return None

        # Cluster walk-strength floor.
        if S < self.min_confidence:
            self._emitted_starts.add(start_ts)
            self._stats["events_suppressed_low_confidence"] += 1
            _log.info(
                "[CONTINUOUS-CHUNKER-REJECTED] reason=below_floor "
                "S=%.2f floor=%.2f start=%.3f end=%.3f",
                S, self.min_confidence, start_ts, end_ts)
            return None

        # Dedup against last emission.
        if (self._last_event_end_ts is not None
                and (start_ts - self._last_event_end_ts)
                < self.min_event_gap_s):
            self._emitted_starts.add(start_ts)
            self._stats["events_suppressed_dedup"] += 1
            return None

        # Duration clamp.
        duration = max(0.0, end_ts - start_ts)
        if duration < self.min_clip_duration_s:
            pad = (self.min_clip_duration_s - duration) / 2.0
            start_ts -= pad
            end_ts += pad
            duration = end_ts - start_ts
        if duration > self.max_clip_duration_s:
            end_ts = start_ts + self.max_clip_duration_s
            duration = end_ts - start_ts

        anchor_count = sum(
            1 for i in range(s, e + 1)
            if frames[i]["score"]["DELIVERY"] >= 0.5)
        labels = [
            {
                "ts": round(frames[i]["ts"], 3),
                "label": max(
                    frames[i]["score"].items(),
                    key=lambda kv: kv[1])[0],
            }
            for i in range(s, e + 1)
        ]
        event = DeliveryDetectedEvent(
            start_ts=start_ts,
            end_ts=end_ts,
            duration_s=duration,
            anchor_frames=anchor_count,
            confidence_score=round(float(S), 3),
            labels=labels,
        )
        self._emitted_starts.add(frames[s]["ts"])
        self._last_event_end_ts = end_ts
        self._stats["events_emitted"] += 1
        if self._event_sink is not None:
            try:
                self._event_sink(event)
            except Exception:  # noqa: BLE001
                pass
        return event


__all__ = [
    "ContinuousChunker",
    "DeliveryDetectedEvent",
]
