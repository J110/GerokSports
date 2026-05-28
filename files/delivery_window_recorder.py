"""DeliveryWindowRecorder — retrospective score-event delivery assembly.

Architecture (2026-04-20, retrospective rewrite):

    Continuous capture (BallAnalyzer thread):
        ~20 fps frames -> rolling raw frame buffer

    Scout polling (main pipeline thread, ~1 Hz):
        record_tagged_frame() stores (ts, frame, camera_view, frame_phase)
        in BallAnalyzer's tagged buffer for ~60-90 s.

    Score event (main pipeline thread, deterministic):
        classify_for_score_event(event_ts):
            1. look backward in the tagged buffer for the most recent
               contiguous `bowlers_end` span
            2. expand it with pre/post padding
            3. fetch raw 20 fps frames from the raw frame buffer
            4. compile mp4 and send to Gemini

    Fallback:
        If no `bowlers_end` span exists, take a broader raw-buffer
        window before the score event and let Gemini's
        `is_valid_delivery` field act as the safety net.

Scout tags are supporting data only.  Score events are the primary
trigger, which removes the race where a rogue walkback window can be
consumed by the wrong ball event.
"""
from __future__ import annotations

import collections
import json
import logging
import time
from pathlib import Path
from typing import Callable

import numpy as np

from gemini_delivery_classifier import GeminiDeliveryClassifier

log = logging.getLogger("delivery_window_recorder")

# Wire into the cricket_logger file handler so window events show up
# in the standard pipeline log alongside Scout / ScoreManager output.
try:
    from eyes.cricket_logger import _ensure_file_handler
    log.addHandler(_ensure_file_handler())
    log.setLevel(logging.INFO)
except Exception:
    pass

_NOTE_MATCH_DISABLED_LOGGED = False


def _log_note_match_disabled_once() -> None:
    global _NOTE_MATCH_DISABLED_LOGGED
    if _NOTE_MATCH_DISABLED_LOGGED:
        return
    log.info(
        "[OPEN-SCOUT-DELIVERY] note_match disabled for validation run")
    _NOTE_MATCH_DISABLED_LOGGED = True

# ── Tunables ───────────────────────────────────────────────────────
PRE_PADDING_S = 2.0
POST_PADDING_S = 1.5
LOOKBACK_S = 25.0
FALLBACK_LOOKBACK_S = 10.0
# RC-6 (2026-04-21): broadcast strip updates lag the live ball by 2-6s,
# so the live shot + early follow-through regularly extends past the
# score event.  Clamping the clip at event_ts+0.5 truncated the shot;
# bump to +2.5s so the clip ends on the post-shot fielder cutaway rather
# than mid-swing.
MAX_EVENT_DRIFT_S = 2.5
DELAYED_SCORE_FALLBACK_LOOKBACK_S = 24.0
DELAYED_SCORE_FALLBACK_END_BEFORE_EVENT_S = 4.0
RETROSPECTIVE_SPAN_REJECTION_THRESHOLD_S = 2.5
MIN_FRAMES_FOR_CLASSIFICATION = 4
REPLAY_CAPTURE_S = 15.0
# RC-3 (2026-04-21): replays of the SCORED delivery happen AFTER
# event_ts but BEFORE the next ball fires.  Anything Scout-tagged in
# the last 1.5s before event_ts is almost always the tail of the
# live release; anything AFTER event_ts - 0.0s is post-event (replay
# cluster, reaction, graphic).  We look back in
# [event_ts - LOOKBACK_S, event_ts - POST_EVENT_EXCLUSION_S] so that
# replay frames tagged `bowlers_end` near event_ts can't get chosen
# as the latest span for the NEXT delivery.
POST_EVENT_EXCLUSION_S = 1.5
# RC-3 sanity: if the best span we can find ends more than this many
# seconds before event_ts, it's almost certainly a previous ball's
# span (broadcaster lag + live release lag combined top out at ~6s).
# Fall through to the raw pre-event fallback window instead.
MAX_END_TO_EVENT_GAP_S = 8.0
# RC-4 (2026-04-21): two Scout tags separated by more than this are
# NOT the same contiguous span — at 0.4-1 Hz sampling the intervening
# seconds may well contain a replay/reaction we simply didn't sample.
# A live delivery from runup to shot is 5-9s, so tag-to-tag gaps of
# 2.5s+ almost always cross a camera cut.  Break the span there.
MAX_CONTIGUOUS_GAP_S = 2.5
# RC-5 (2026-04-21): real IPL over-rate peaks around 4 balls/min, so
# anything under ~12s between accepted score events is almost certainly
# a phantom re-read of the strip (OCR flicker on overlay / graphic).
# Skip the event entirely and tell the caller to mark it untrackable.
MIN_INTER_DELIVERY_S = 8.0
# RC-5 dedupe: if the span we'd pick for this event overlaps more
# than this fraction with the span already consumed by the last
# accepted event, treat as duplicate clip and skip.
MAX_SPAN_OVERLAP_RATIO = 0.5
# RC-7 (2026-04-23, Part A of the window-selection investigation):
# Scout tags every bowlers_end frame with a frame_phase describing
# the MOMENT of the delivery it thinks it's seeing.  Prior to RC-7
# `_find_span` keyed only on camera_view and ignored phase, so an
# anchor tag with phase=between_play / post_shot / fielder_reaction
# was accepted as an equally-valid delivery anchor.  Forensic audit
# across 1369 tags (2026-04-20..23) found ~8% of anchors are
# explicit non-action phases — dropping them eliminates a clean
# class of non-delivery clips without touching Scout.  (The larger
# failure mode — close-ups mislabeled as phase=release, ~50% of
# historical tags — is Part B territory and lives in Scout's prompt,
# not here.)
_ACTION_PHASES: frozenset[str] = frozenset({
    "release", "flight", "shot", "runup",
})


class DeliveryWindowRecorder:
    """Score-event-triggered delivery clip assembly + Gemini classify."""

    def __init__(self,
                 classifier: GeminiDeliveryClassifier,
                 frame_source_fn: Callable[[float, float],
                                           list[tuple[float, np.ndarray]]],
                 tagged_source_fn: Callable[
                     [float, float, tuple[str, ...] | None],
                     list[tuple[float, np.ndarray, str, str | None]]
                 ],
                 save_root: Path | str | None = None,
                 pre_padding_s: float = PRE_PADDING_S,
                 post_padding_s: float = POST_PADDING_S,
                 lookback_s: float = LOOKBACK_S,
                 fallback_lookback_s: float = FALLBACK_LOOKBACK_S,
                 replay_capture_s: float = REPLAY_CAPTURE_S,
                 min_frames: int = MIN_FRAMES_FOR_CLASSIFICATION,
                 post_event_exclusion_s: float = POST_EVENT_EXCLUSION_S,
                 max_end_to_event_gap_s: float = MAX_END_TO_EVENT_GAP_S,
                 max_contiguous_gap_s: float = MAX_CONTIGUOUS_GAP_S,
                 min_inter_delivery_s: float = MIN_INTER_DELIVERY_S,
                 max_span_overlap_ratio: float = MAX_SPAN_OVERLAP_RATIO,
                 span_aggregator: object | None = None,
                 use_open_scout_spans: bool = False,
                 stage2_span_lookup: Callable[
                     [float], tuple[float, float] | None] | None = None,
                 v3_aggregator: object | None = None,
                 use_v3_chunker_spans: bool = False,
                 v3_fallback_enabled: bool | None = None,
                 v3_fallback_lookback_s: float | None = None,
                 v3_fallback_forward_s: float | None = None):
        self._clf = classifier
        self._get_frames = frame_source_fn
        self._get_tags = tagged_source_fn
        self._save_root = Path(save_root) if save_root else None
        self._pre_padding_s = pre_padding_s
        self._post_padding_s = post_padding_s
        self._lookback_s = lookback_s
        self._fallback_lookback_s = fallback_lookback_s
        self._replay_capture_s = replay_capture_s
        self._min_frames = min_frames
        # RC-3/4/5 tunables (2026-04-21).
        self._post_event_exclusion_s = post_event_exclusion_s
        self._max_end_to_event_gap_s = max_end_to_event_gap_s
        self._max_contiguous_gap_s = max_contiguous_gap_s
        self._min_inter_delivery_s = min_inter_delivery_s
        self._max_span_overlap_ratio = max_span_overlap_ratio
        # Parallel-Scout coexistence (design memo §7).  When the
        # aggregator is provided, both legacy `_find_span` and
        # `match_span_to_event` run on every score event so the
        # shadow-vs-active comparison fields land in window_debug.json
        # regardless of the flag.  Only `use_open_scout_spans` controls
        # which path's window is actually fed to Layer 2.
        self._span_aggregator = span_aggregator
        self._use_open_scout_spans = bool(use_open_scout_spans)
        # Stage 2 (DeliverySpanSelector) lookup callable.  When provided
        # AND ``USE_OPEN_SCOUT_SPANS=1``, takes priority over the legacy
        # SpanAggregator-direct path.  Returns ``(raw_start_ts,
        # raw_end_ts)`` for the most recent emitted span belonging to
        # ``event_ts`` per sub_clip_delivery_isolation_v4.md §8.
        self._stage2_span_lookup = stage2_span_lookup
        # Chunker v3 (shadow + optional cut).  See
        # files/docs/algorithms/chunker_v3.md.  When the aggregator is
        # provided, ``find_span(event_ts)`` is called on every score
        # event so the v3 proposal lands in window_debug.json regardless
        # of whether ``use_v3_chunker_spans`` is on.
        self._v3_aggregator = v3_aggregator
        self._use_v3_chunker_spans = bool(use_v3_chunker_spans)
        # V3 None-fallback (safety net — see chunker_v3_setup.md).  When
        # any kwarg is None, fall through to the env-driven config
        # constants so the operator can flip behavior without code
        # changes.
        from eyes import config as _cfg
        self._v3_fallback_enabled = bool(
            _cfg.V3_FALLBACK_ENABLED if v3_fallback_enabled is None
            else v3_fallback_enabled)
        self._v3_fallback_lookback_s = float(
            _cfg.V3_FALLBACK_LOOKBACK_S if v3_fallback_lookback_s is None
            else v3_fallback_lookback_s)
        self._v3_fallback_forward_s = float(
            _cfg.V3_FALLBACK_FORWARD_S if v3_fallback_forward_s is None
            else v3_fallback_forward_s)

        self._window_id = 0
        self._stats = collections.Counter()
        self._pending_replay_jobs: list[dict] = []
        # Layer B / OpenScout span archive hook (legacy).  BallAnalyzer
        # no longer calls ``attach_open_scout_archive``; validation clips
        # use OpenScoutDeliveryWriter instead.  Field retained for tests.
        self._open_scout_archive = None
        # RC-5 phantom/duplicate bookkeeping: track the event_ts and
        # span of the LAST event we actually accepted (produced a
        # classification clip for).  Events arriving <min_inter_delivery
        # later are suspect phantom re-reads; spans overlapping the
        # consumed span >max_overlap are duplicate clips.
        self._last_accepted_event_ts: float = 0.0
        self._last_consumed_span: tuple[float, float] | None = None
        # Live-monitoring v1 (2026-05-05).  Counters are populated
        # alongside the existing ``self._stats`` so the periodic
        # emitters in ``test_pipeline.py`` can snapshot without
        # touching internal counter keys.
        from monitoring_emitters import (
            ChunkerV3StatsCounters, RetroCounters)
        self._retro_counters = RetroCounters()
        self._v3_stats_counters = ChunkerV3StatsCounters()
        # Match-cumulative variant — never reset by the periodic
        # emitter so [MATCH-SUMMARY] can read totals across the match.
        self._v3_stats_match = ChunkerV3StatsCounters()
        # Tripwire counter: number of consecutive score events where
        # v3 returned None.  Reset on any v3 non-None outcome.
        self._v3_consecutive_none: int = 0
        _log_note_match_disabled_once()

    def on_scout_tag(self, ts: float, camera_view: str | None) -> None:
        cv = (camera_view or "").strip().lower()
        self._stats[f"tag:{cv or 'none'}"] += 1

    def tick(self, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        remaining: list[dict] = []
        for job in self._pending_replay_jobs:
            if now >= job["ready_ts"]:
                self._flush_replay_job(job)
            else:
                remaining.append(job)
        self._pending_replay_jobs = remaining

    def classify_for_score_event(self,
                                 runs: int,
                                 over_number: float | None = None,
                                 innings: int | None = None,
                                 event_type: str | None = None,
                                 event_ts: float | None = None,
                                 delivery_num: int | None = None,
                                 save_dir: str | None = None,
                                 await_timeout_s: float = 20.0,
                                 known_batsman_handed: str = "unknown",
                                 known_bowling_arm: str = "unknown",
                                 ) -> dict | None:
        del await_timeout_s  # Retained for call-site compatibility.
        event_ts = event_ts if event_ts is not None else time.time()
        self._stats["score_event"] += 1
        self._retro_counters.note_event()
        self.tick(now=event_ts)
        self._window_id += 1
        win_id = self._window_id

        dpath = Path(save_dir) if save_dir else None
        context = {
            "window_id": win_id,
            "delivery_num": delivery_num,
            "event_ts": event_ts,
            "over_number": over_number,
            "innings": innings,
            "event_type": event_type,
            "runs": runs,
            "known_batsman_handed": known_batsman_handed,
            "known_bowling_arm": known_bowling_arm,
        }

        # RC-5 phantom-event rate guard (2026-04-21).  Two accepted score
        # events closer than MIN_INTER_DELIVERY_S apart are physically
        # impossible in real cricket (max over-rate ~4 balls/min => >=15s
        # between balls).  Near-duplicate event_ts values almost always
        # mean the scorer's strip OCR flickered (e.g., over flipped
        # 8.2 -> 8.3 -> 8.2 due to a stats overlay obscuring the over
        # digit).  Refuse to classify — otherwise we amplify one bad
        # scorer read into a duplicated clip in the delivery dataset.
        if (self._last_accepted_event_ts > 0.0
                and (event_ts - self._last_accepted_event_ts)
                < self._min_inter_delivery_s):
            inter = event_ts - self._last_accepted_event_ts
            log.warning(
                f"[DWR] window #{win_id} SKIP phantom event — only "
                f"{inter:.2f}s since last accepted event "
                f"(<{self._min_inter_delivery_s:.1f}s). "
                f"over={over_number} event={event_type} runs={runs} "
                f"event_ts={event_ts:.2f} "
                f"prev_event_ts={self._last_accepted_event_ts:.2f}"
            )
            self._stats["score_phantom_skipped"] += 1
            return self._skip_result(
                win_id=win_id,
                skip_reason="phantom_event",
                context=context,
                save_dir=dpath,
                extra={"inter_event_s": round(inter, 3),
                       "min_inter_delivery_s": self._min_inter_delivery_s,
                       "prev_event_ts": self._last_accepted_event_ts},
            )

        # Cut-precedence outcome flags.  ``fallback_used`` flips True
        # only when the V3 None-fallback safety net fires.
        fallback_used = False
        fallback_scan_block: dict | None = None
        retrospective_rejection_block: dict | None = None
        retrospective_safety_block: dict | None = None

        legacy_span = self._find_span(
            event_ts=event_ts, target_view="bowlers_end")

        # RC-5 duplicate-span guard: the d025/d026 case.  If the span we
        # just picked overlaps >MAX_SPAN_OVERLAP_RATIO with the span we
        # already consumed for the previous accepted event, we'd be
        # shipping two "different" deliveries with effectively the same
        # clip bytes.  Fall through to the raw-buffer fallback so d026
        # at least gets a DIFFERENT window (even if it's just event-
        # aligned raw frames).  In most phantom cases the rate guard
        # already caught it, so this is a belt-and-suspenders check for
        # legitimately-fast events where Scout just never tagged the
        # gap between them.
        if (legacy_span is not None
                and self._last_consumed_span is not None):
            overlap = _span_overlap_ratio(
                legacy_span, self._last_consumed_span)
            if overlap > self._max_span_overlap_ratio:
                log.warning(
                    f"[DWR] window #{win_id} span "
                    f"[{legacy_span[0]:.2f}, {legacy_span[1]:.2f}] "
                    f"overlaps {overlap * 100:.0f}% with last "
                    f"consumed span "
                    f"[{self._last_consumed_span[0]:.2f}, "
                    f"{self._last_consumed_span[1]:.2f}] — refusing "
                    f"to reuse.  Falling back to raw pre-event window."
                )
                self._stats["score_span_duplicate"] += 1
                legacy_span = None

        # Parallel-Scout shadow telemetry (design memo §7.3).  Run the
        # OpenScout matcher unconditionally so window_debug.json
        # captures both proposals.  ``open_scout_verdict`` is one of
        # {"no_match", "open_scout_span", "defer_to_legacy",
        # "aggregator_unavailable", "aggregator_error"}.
        (open_scout_verdict,
         open_scout_bounds,
         open_scout_span_id) = self._resolve_open_scout(event_ts)

        # Chunker v3 shadow.  Always called when an aggregator is
        # wired; the v3 bounds land in window_debug.json regardless of
        # whether they drive the actual cut.
        v3_bounds = self._resolve_v3_chunker(event_ts)

        # Path selection (§D1 of implementation memo / design §7.1):
        #   USE_OPEN_SCOUT_SPANS=1 + verdict==open_scout_span
        #     → committed bounds become (clip_start, clip_end).
        #   Otherwise (flag off, or verdict ∈ {no_match, defer_to_legacy,
        #   aggregator_*})  → fall through to the legacy path
        #   (retrospective_span or fallback_pre_event_window) exactly
        #   as before.  See §8 F1 / F2.
        stage2_bounds: tuple[float, float] | None = None
        if (self._use_open_scout_spans
                and self._stage2_span_lookup is not None):
            try:
                stage2_bounds = self._stage2_span_lookup(event_ts)
            except Exception as e:  # noqa: BLE001
                log.warning(
                    f"[OPEN-SCOUT-SPAN] stage2 lookup raised: {e}")
                stage2_bounds = None

        used_stage2 = stage2_bounds is not None
        used_open_scout = (
            not used_stage2
            and self._use_open_scout_spans
            and open_scout_verdict == "open_scout_span"
            and open_scout_bounds is not None
        )
        used_v3 = (
            not used_stage2
            and not used_open_scout
            and self._use_v3_chunker_spans
            and v3_bounds is not None
        )

        if used_stage2:
            span_start, span_end = stage2_bounds
            clip_start, clip_end, tags = self._span_to_clip_bounds(
                span_start=span_start,
                span_end=span_end,
                event_ts=event_ts,
            )
            frames = self._get_frames(clip_start, clip_end)
            source = "open_scout_span"
            reason = "stage2_emitted_anchored"
            span = (span_start, span_end)
            self._stats["score_stage2_used"] += 1
            log.info(
                f"[OPEN-SCOUT-SPAN] used: event_ts={event_ts:.2f} "
                f"span=[{span_start:.2f},{span_end:.2f}]")
        elif used_open_scout:
            span_start, span_end = open_scout_bounds
            clip_start, clip_end, tags = self._span_to_clip_bounds(
                span_start=span_start,
                span_end=span_end,
                event_ts=event_ts,
            )
            frames = self._get_frames(clip_start, clip_end)
            source = "open_scout_span"
            reason = "open_scout_single_candidate"
            span = (span_start, span_end)
            self._stats["score_open_scout_used"] += 1
        elif used_v3:
            span_start, span_end = v3_bounds
            clip_start, clip_end, tags = self._span_to_clip_bounds(
                span_start=span_start,
                span_end=span_end,
                event_ts=event_ts,
            )
            frames = self._get_frames(clip_start, clip_end)
            source = "v3_chunker_span"
            reason = "v3_consequential_window"
            span = (span_start, span_end)
            self._stats["score_v3_used"] += 1
            log.info(
                f"[CHUNKER-V3] used: event_ts={event_ts:.2f} "
                f"span=[{span_start:.2f},{span_end:.2f}]")
        elif legacy_span is not None:
            clip_start, clip_end, tags = self._span_to_clip_bounds(
                span_start=legacy_span[0],
                span_end=legacy_span[1],
                event_ts=event_ts,
            )
            safe_margin = event_ts - clip_end
            safe_cutoff = (
                event_ts - RETROSPECTIVE_SPAN_REJECTION_THRESHOLD_S)
            has_dead_time_tag = self._has_dead_time_tag(tags)
            retrospective_safety_block = {
                "safe_margin_s": round(safe_margin, 3),
                "rejection_threshold_s": (
                    RETROSPECTIVE_SPAN_REJECTION_THRESHOLD_S),
                "has_dead_time_tag": has_dead_time_tag,
            }
            if safe_margin < RETROSPECTIVE_SPAN_REJECTION_THRESHOLD_S:
                rejection_reason = "too_close_to_event"
            elif has_dead_time_tag:
                rejection_reason = "dead_time_tag"
            else:
                rejection_reason = None
            if rejection_reason is not None:
                retrospective_rejection_block = {
                    "reason": rejection_reason,
                    "rejected_span_start_ts": round(legacy_span[0], 3),
                    "rejected_span_end_ts": round(legacy_span[1], 3),
                    "rejected_clip_start_ts": round(clip_start, 3),
                    "rejected_clip_end_ts": round(clip_end, 3),
                    "rejection_event_safe_cutoff_ts": round(safe_cutoff, 3),
                }
                log.warning(
                    f"[DWR] retrospective_span rejected: "
                    f"event_ts={event_ts:.2f} "
                    f"clip_end={clip_end:.2f} "
                    f"safe_margin_s={safe_margin:.2f} "
                    f"threshold_s="
                    f"{RETROSPECTIVE_SPAN_REJECTION_THRESHOLD_S:.2f} "
                    f"reason={rejection_reason}")
                self._stats["score_span_rejected_too_close"] += 1
                legacy_span = None
                clip_start = max(
                    0.0, event_ts - DELAYED_SCORE_FALLBACK_LOOKBACK_S)
                clip_end = max(
                    clip_start,
                    event_ts - DELAYED_SCORE_FALLBACK_END_BEFORE_EVENT_S)
                frames = self._get_frames(clip_start, clip_end)
                tags = self._get_tags(clip_start, clip_end, None)
                source = "v3_chunker_fallback"
                reason = "retrospective_span_rejected_too_close_to_event"
                (clip_start, clip_end, frames, tags,
                 fallback_scan_block) = self._scan_v3_fallback_window(
                     event_ts=event_ts,
                     clip_start=clip_start,
                     clip_end=clip_end,
                     frames=frames,
                     tags=tags,
                     reason=reason)
                span = (clip_start, clip_end)
                fallback_used = True
                self._stats["score_v3_fallback_used"] += 1
            else:
                frames = self._get_frames(clip_start, clip_end)
                source = "retrospective_span"
                reason = "latest_bowlers_end_span"
                span = legacy_span
                self._stats["score_span_found"] += 1
        else:
            self._stats["score_span_missing"] += 1
            if self._v3_fallback_enabled:
                # Safety net — v3 + legacy both returned None.  Cut a
                # delayed-score pre-event window so every score event
                # still produces a clip.  See chunker_v3_setup.md
                # "None-event fallback".
                clip_start = max(
                    0.0, event_ts - DELAYED_SCORE_FALLBACK_LOOKBACK_S)
                clip_end = max(
                    clip_start,
                    event_ts - DELAYED_SCORE_FALLBACK_END_BEFORE_EVENT_S)
                frames = self._get_frames(clip_start, clip_end)
                tags = self._get_tags(clip_start, clip_end, None)
                source = "v3_chunker_fallback"
                reason = "v3_and_legacy_returned_none"
                (clip_start, clip_end, frames, tags,
                 fallback_scan_block) = self._scan_v3_fallback_window(
                     event_ts=event_ts,
                     clip_start=clip_start,
                     clip_end=clip_end,
                     frames=frames,
                     tags=tags,
                     reason=reason)
                span = (clip_start, clip_end)
                fallback_used = True
                self._stats["score_v3_fallback_used"] += 1
                log.warning(
                    f"[CHUNKER-V3-FALLBACK] event_ts={event_ts:.2f} "
                    f"window=({clip_start:.2f}, {clip_end:.2f}) "
                    "fallback_type=delayed_score_pre_event "
                    f"lookback_s={DELAYED_SCORE_FALLBACK_LOOKBACK_S:.2f} "
                    f"end_before_event_s="
                    f"{DELAYED_SCORE_FALLBACK_END_BEFORE_EVENT_S:.2f} "
                    f"old_lookback_s="
                    f"{self._v3_fallback_lookback_s:.2f} "
                    f"old_forward_s="
                    f"{self._v3_fallback_forward_s:.2f}")
            else:
                clip_start = max(
                    0.0, event_ts - self._fallback_lookback_s)
                clip_end = event_ts + MAX_EVENT_DRIFT_S
                frames = self._get_frames(clip_start, clip_end)
                tags = self._get_tags(clip_start, clip_end, None)
                source = "fallback_pre_event_window"
                reason = "no_bowlers_end_span"
                span = None
                if (self._use_open_scout_spans
                        and self._stage2_span_lookup is not None):
                    log.info(
                        f"[OPEN-SCOUT-SPAN] no_match: "
                        f"event_ts={event_ts:.2f}"
                        " — falling back to legacy window")

        # Per-path telemetry counters for shadow-mode dashboards.
        self._stats[f"open_scout_verdict:{open_scout_verdict}"] += 1
        if self._use_open_scout_spans:
            self._stats["score_open_scout_flag_on"] += 1

        # Pre-compute legacy/open windows for shadow telemetry — both
        # are persisted in window_debug.json regardless of which path
        # actually drives the mp4.
        legacy_window = self._compute_legacy_window(
            legacy_span=legacy_span, event_ts=event_ts)
        open_scout_window = self._compute_open_scout_window(
            open_scout_bounds=open_scout_bounds, event_ts=event_ts)
        # ``drove_cut`` is normally a bool ("did v3 drive?") but turns
        # into the literal "fallback" string when the V3 None-fallback
        # safety net fires — so analyzers can distinguish "v3 won the
        # cut" from "everything else lost and fallback caught the
        # event".
        v3_drove_cut: bool | str = (
            "fallback" if fallback_used else bool(used_v3))
        v3_chunker_block = self._compute_v3_chunker_block(
            v3_bounds=v3_bounds,
            drove_cut=v3_drove_cut,
            labels_provider=self._v3_aggregator,
            event_ts=event_ts,
        )
        fallback_block = {
            "used": bool(fallback_used),
            "type": (
                "delayed_score_pre_event" if fallback_used else None),
            "lookback_s": (
                DELAYED_SCORE_FALLBACK_LOOKBACK_S
                if fallback_used else self._v3_fallback_lookback_s),
            "end_before_event_s": (
                DELAYED_SCORE_FALLBACK_END_BEFORE_EVENT_S
                if fallback_used else None),
            "forward_s": self._v3_fallback_forward_s,
            "old_lookback_s": self._v3_fallback_lookback_s,
            "old_forward_s": self._v3_fallback_forward_s,
            "clip_start_ts": round(clip_start, 3) if fallback_used else None,
            "clip_end_ts": round(clip_end, 3) if fallback_used else None,
        }

        # Live-monitoring v1: retro hit-rate + v3 stats bookkeeping.
        # Any of stage2/open_scout/v3/legacy/fallback counts as a
        # committed span (every score event produces a clip).
        self._retro_counters.note_commit()
        if fallback_used:
            self._retro_counters.note_fallback()
        legacy_bounds_for_diff = (
            (legacy_span[0], legacy_span[1])
            if legacy_span is not None else None)
        self._v3_stats_counters.note_outcome(
            v3_bounds=v3_bounds,
            legacy_bounds=legacy_bounds_for_diff,
            fallback_used=fallback_used,
            drove_cut=bool(used_v3),
        )
        self._v3_stats_match.note_outcome(
            v3_bounds=v3_bounds,
            legacy_bounds=legacy_bounds_for_diff,
            fallback_used=fallback_used,
            drove_cut=bool(used_v3),
        )

        if v3_bounds is None:
            self._v3_consecutive_none += 1
            from monitoring_emitters import check_consecutive_none_alarm
            _alarm_msg = check_consecutive_none_alarm(
                self._v3_consecutive_none, event_ts)
            if _alarm_msg is not None:
                log.warning(_alarm_msg)
        else:
            self._v3_consecutive_none = 0

        # Trace-and-Detect: emit chunker_v3.window decision tag once
        # per window resolution.  Auto-promoted to decisions[] by the
        # DecisionLogHandler installed in test_pipeline.py.
        self._emit_chunker_v3_trace(
            legacy_window=legacy_window,
            v3_bounds=v3_bounds,
            drove_cut="v3" if used_v3 else "legacy",
        )

        result = self._classify_frames_for_event(
            frames=frames,
            save_dir=dpath,
            context=context,
            tags=tags,
            clip_start=clip_start,
            clip_end=clip_end,
            source=source,
            reason=reason,
            legacy_window=legacy_window,
            open_scout_window=open_scout_window,
            open_scout_verdict=open_scout_verdict,
            use_open_scout_spans=self._use_open_scout_spans,
            v3_chunker_block=v3_chunker_block,
            fallback_block=fallback_block,
            fallback_scan_block=fallback_scan_block,
            retrospective_rejection_block=retrospective_rejection_block,
            retrospective_safety_block=retrospective_safety_block,
        )
        if result is None:
            self._stats["score_unknown"] += 1
            return None

        # Event accepted — remember it so the next event can run
        # phantom/duplicate checks against it.  Only update on accept
        # so rejected events don't shift the rate-guard baseline and
        # legitimate events after a phantom still pass through.
        self._last_accepted_event_ts = event_ts
        if span is not None:
            self._last_consumed_span = span

        self._schedule_replay_capture(
            event_ts=event_ts,
            delivery_num=delivery_num,
            save_dir=dpath,
            over_number=over_number,
            event_type=event_type,
            runs=runs,
        )

        return self._tag_result(result, runs, event_type, from_cache=False)

    def stats(self) -> dict:
        return {
            **dict(self._stats),
            "active_window_id": self._window_id,
            "pending_replay_jobs": len(self._pending_replay_jobs),
        }

    def shutdown(self) -> None:
        self.tick(now=time.time() + self._replay_capture_s + 0.1)

    # ── Helpers ──────────────────────────────────────────────────

    def attach_open_scout_archive(self, archive) -> None:
        """Retain a reference for legacy tests.  ``note_match_to_event`` is
        not invoked from ``classify_for_score_event`` during validation
        runs."""
        self._open_scout_archive = archive

    def _resolve_open_scout(self,
                            event_ts: float,
                            ) -> tuple[str,
                                       tuple[float, float] | None,
                                       int | None]:
        """Run the SpanAggregator matcher with full failure isolation.

        Returns ``(verdict, bounds, span_id)``.  Verdict mirrors
        ``SpanAggregator.match_span_to_event_detailed`` plus two
        synthetic codes for the cases where the aggregator can't be
        consulted:
          * ``aggregator_unavailable`` — no aggregator wired in
            (e.g., legacy boot path or test harness).
          * ``aggregator_error`` — the matcher raised; treat as
            no-match per §8 F1.
        ``span_id`` is non-None only for the ``open_scout_span``
        verdict (single-candidate case).
        """
        agg = self._span_aggregator
        if agg is None:
            return ("aggregator_unavailable", None, None)
        try:
            matcher = getattr(
                agg, "match_span_to_event_detailed", None)
            if matcher is not None:
                return matcher(event_ts)
            verdict, bounds = agg.match_span_to_event(event_ts)
            return (verdict, bounds, None)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[OPEN-SCOUT] matcher raised: {e}")
            return ("aggregator_error", None, None)

    def _compute_legacy_window(self,
                               legacy_span: tuple[float, float] | None,
                               event_ts: float,
                               ) -> dict:
        """Project the legacy `_find_span` choice to clip bounds for
        side-by-side comparison with the open-scout window.  Always
        returns a dict so window_debug.json keys are stable."""
        if legacy_span is None:
            fb_start = max(0.0, event_ts - self._fallback_lookback_s)
            fb_end = event_ts + MAX_EVENT_DRIFT_S
            return {
                "source": "fallback_pre_event_window",
                "span_start": None,
                "span_end": None,
                "clip_start": round(fb_start, 3),
                "clip_end": round(fb_end, 3),
            }
        clip_start = max(0.0, legacy_span[0] - self._pre_padding_s)
        clip_end = min(legacy_span[1] + self._post_padding_s,
                       event_ts + MAX_EVENT_DRIFT_S)
        return {
            "source": "retrospective_span",
            "span_start": round(legacy_span[0], 3),
            "span_end": round(legacy_span[1], 3),
            "clip_start": round(clip_start, 3),
            "clip_end": round(clip_end, 3),
        }

    def _resolve_v3_chunker(
            self,
            event_ts: float,
            ) -> tuple[float, float] | None:
        """Run the v3 chunker with full failure isolation.  Returns
        ``(start_ts, end_ts)`` or None.  Never raises."""
        agg = self._v3_aggregator
        if agg is None:
            return None
        try:
            finder = getattr(agg, "find_span", None)
            if finder is None:
                return None
            window = finder(event_ts)
            if window is None:
                return None
            return (float(window[0]), float(window[1]))
        except Exception as e:  # noqa: BLE001
            log.warning(f"[CHUNKER-V3] find_span raised: {e}")
            return None

    def _compute_v3_chunker_block(
            self,
            v3_bounds: tuple[float, float] | None,
            drove_cut: bool | str,
            labels_provider: object | None,
            event_ts: float,
            ) -> dict | None:
        """Build the v3_chunker block for window_debug.json.

        Returns None when no aggregator is wired so the field is omitted
        rather than serialized as null.  The labels list is best-effort
        from the aggregator's snapshot; never raises."""
        if labels_provider is None:
            return None
        labels: list[dict] = []
        try:
            snap = getattr(labels_provider, "snapshot_frames", None)
            if snap is not None:
                # Bound to ±15 s around the event so the block stays
                # small.  classify lazily so we don't hold the agg lock.
                from eyes.chunker_v3 import classify_frames
                frames = [
                    f for f in snap()
                    if (event_ts - 30.0) <= f.ts <= (event_ts + 10.0)
                ]
                for lf in classify_frames(frames):
                    labels.append({
                        "ts": round(float(lf.ts), 3),
                        "label": lf.label,
                    })
        except Exception as e:  # noqa: BLE001
            log.warning(f"[CHUNKER-V3] label snapshot failed: {e}")
        return {
            "start": (round(v3_bounds[0], 3)
                      if v3_bounds is not None else None),
            "end": (round(v3_bounds[1], 3)
                    if v3_bounds is not None else None),
            "labels": labels,
            "drove_cut": (
                drove_cut if isinstance(drove_cut, str)
                else bool(drove_cut)),
        }

    def _emit_chunker_v3_trace(
            self,
            legacy_window: dict | None,
            v3_bounds: tuple[float, float] | None,
            drove_cut: str,
            ) -> None:
        """Auto-decision tag for trace_emitter — picked up by the
        log-handler bridge in trace_emitter.DecisionLogHandler.

        Format mirrors the existing ``[OPEN-SCOUT-SPAN]`` tag style so
        the analyzer's existing rules see it as a structured decision.
        """
        try:
            ls = (legacy_window or {}).get("span_start")
            le = (legacy_window or {}).get("span_end")
            v3s = (v3_bounds[0] if v3_bounds is not None else None)
            v3e = (v3_bounds[1] if v3_bounds is not None else None)
            log.info(
                f"[CHUNKER-V3-WINDOW] legacy_start={ls} legacy_end={le} "
                f"v3_start={v3s} v3_end={v3e} drove_cut={drove_cut}")
        except Exception:  # noqa: BLE001
            pass

    def _compute_open_scout_window(
        self,
        open_scout_bounds: tuple[float, float] | None,
        event_ts: float,
    ) -> dict | None:
        if open_scout_bounds is None:
            return None
        clip_start = max(0.0, open_scout_bounds[0] - self._pre_padding_s)
        clip_end = min(open_scout_bounds[1] + self._post_padding_s,
                       event_ts + MAX_EVENT_DRIFT_S)
        return {
            "span_start": round(open_scout_bounds[0], 3),
            "span_end": round(open_scout_bounds[1], 3),
            "clip_start": round(clip_start, 3),
            "clip_end": round(clip_end, 3),
        }

    def _find_span(self,
                   event_ts: float,
                   target_view: str,
                   ) -> tuple[float, float] | None:
        """Find the live-delivery bowlers_end span for this score event.

        RC-3 (2026-04-21): the search window is bounded to
        ``[event_ts - LOOKBACK_S, event_ts - POST_EVENT_EXCLUSION_S]``.
        The exclusion zone before event_ts drops any tag from the
        immediate post-event replay cluster — those are replays of the
        CURRENT delivery and they must NOT be picked as the span for
        the NEXT delivery (the d025 "last 30-40% is the real ball"
        symptom).

        RC-4: the backward walk also breaks the span when adjacent
        target_view tags are more than ``MAX_CONTIGUOUS_GAP_S`` apart.
        At Scout's 0.4-1 Hz sampling rate, two bowlers_end tags 7s
        apart with no intervening tag are NOT the same contiguous
        span — the gap almost certainly contains a camera cut Scout
        didn't happen to sample.

        RC-3 sanity: if the best span ends more than
        ``MAX_END_TO_EVENT_GAP_S`` before event_ts, it is almost
        certainly a previous ball's span (broadcaster strip lag +
        live-release lag cap out around 6s).  Return None so we fall
        through to the raw-buffer fallback window instead of shipping
        a clip that's entirely the prior delivery's replay cycle.
        """
        start_ts = max(0.0, event_ts - self._lookback_s)
        end_ts = event_ts - self._post_event_exclusion_s
        if end_ts <= start_ts:
            return None
        relevant = self._get_tags(start_ts, end_ts, None)
        if not relevant:
            return None

        # Batch BB (2026-05-05): pre-compute action-phase target-view
        # tag timestamps so a between_play tag can be admitted as a
        # bridge anchor when it sits within MAX_CONTIGUOUS_GAP_S of an
        # action-phase tag on either side.  See
        # retrospective_span_regression_root_cause.md Phase D #1.
        action_ts: list[float] = [
            t for t, _f, v, p in relevant
            if v == target_view and p in _ACTION_PHASES
        ]
        gap = self._max_contiguous_gap_s

        def _has_action_neighbor(at: float) -> bool:
            return any(abs(a - at) <= gap for a in action_ts)

        span_start: float | None = None
        span_end: float | None = None
        in_span = False
        prev_target_ts: float | None = None
        for tag_ts, _frame, view, phase in reversed(relevant):
            is_target_view = (view == target_view)
            # RC-7 (2026-04-23, Part A): only action-phase anchors may
            # seed or extend a delivery span.  A bowlers_end tag whose
            # phase is between_play / post_shot / fielder_reaction /
            # None is Scout telling us "camera is at bowlers_end but
            # nothing is being bowled right now" — pinning a 3.5s clip
            # on such a tag reliably produces non-delivery content.
            # Batch BB relaxes this for between_play tags that bridge
            # two action-phase tags (the ball-in-flight transition
            # Scout now labels conservatively).
            is_action_phase = phase in _ACTION_PHASES
            is_between_play = (phase == "between_play")
            is_bridge_accept = (
                is_target_view and is_between_play
                and _has_action_neighbor(tag_ts)
            )
            is_anchor = (
                is_target_view and (is_action_phase or is_bridge_accept))
            if is_target_view and not is_anchor:
                reject_reason = (
                    "isolated_between_play" if is_between_play
                    else "non_action_no_bridge"
                )
                self._stats["anchor_phase_reject"] += 1
                self._stats[
                    f"anchor_phase_reject_{phase or 'none'}"] += 1
                self._stats[
                    f"anchor_phase_reject_reason_{reject_reason}"] += 1
                log.info(
                    f"[PHASE-REJECT] skipping anchor tag "
                    f"ts={tag_ts:.2f} view={view} "
                    f"phase={phase or 'none'} reason={reject_reason}"
                )
            if is_bridge_accept:
                self._stats["anchor_bridge_accept"] += 1
                log.info(
                    f"[PHASE-BRIDGE-ACCEPT] admitting between_play "
                    f"anchor ts={tag_ts:.2f} view={view} — action "
                    f"neighbor within {gap:.1f}s"
                )
            if is_anchor:
                # RC-4: break the span if this target-view tag is too
                # far from the previous one (camera cut we didn't
                # sample).  `prev_target_ts` is the more-recent
                # target-view tag we already admitted into the span.
                if (in_span and prev_target_ts is not None
                        and (prev_target_ts - tag_ts)
                        > self._max_contiguous_gap_s):
                    break
                if not in_span:
                    span_end = tag_ts
                    in_span = True
                span_start = tag_ts
                prev_target_ts = tag_ts
            elif in_span:
                # Non-target view OR non-action phase inside an open
                # span ends it immediately — same semantics as the
                # pre-RC-7 non-target-view break.
                break

        if span_start is None or span_end is None:
            return None

        # RC-3 sanity: reject spans that end too far before event_ts.
        gap_to_event = event_ts - span_end
        if gap_to_event > self._max_end_to_event_gap_s:
            log.info(
                f"[DWR] rejecting stale span [{span_start:.2f}, "
                f"{span_end:.2f}] — ends {gap_to_event:.2f}s before "
                f"event_ts={event_ts:.2f} "
                f"(>{self._max_end_to_event_gap_s:.1f}s, almost "
                f"certainly previous ball's span). "
                f"Will use raw-buffer fallback."
            )
            self._stats["score_span_too_old"] += 1
            return None
        return (span_start, span_end)

    def _span_to_clip_bounds(self,
                             span_start: float,
                             span_end: float,
                             event_ts: float,
                             ) -> tuple[float, float,
                                        list[tuple[float, np.ndarray, str,
                                                   str | None]]]:
        clip_start = max(0.0, span_start - self._pre_padding_s)
        clip_end = min(span_end + self._post_padding_s,
                       event_ts + MAX_EVENT_DRIFT_S)
        tags = self._get_tags(clip_start, clip_end, None)
        return clip_start, clip_end, tags

    @staticmethod
    def _has_dead_time_tag(tags: list[tuple[float, np.ndarray, str,
                                           str | None]]) -> bool:
        dead_views = {"ad", "graphic", "replay"}
        dead_phases = {"advertisement", "graphic", "replay",
                       "post_shot", "fielder_reaction"}
        for _ts, _frame, view, phase in tags:
            if (view or "").strip().lower() in dead_views:
                return True
            if (phase or "").strip().lower() in dead_phases:
                return True
        return False

    @staticmethod
    def _fallback_window_scan_reason(
            tags: list[tuple[float, np.ndarray, str, str | None]],
            frames: list[tuple[float, np.ndarray]]) -> str | None:
        if not frames:
            return "no_frames"
        if not tags:
            return "no_tags"
        dead_views = {"ad", "graphic", "replay", "other"}
        dead_phases = {"advertisement", "graphic", "replay"}
        useful_views = {"bowlers_end", "side_on", "closeup"}
        action_phases = {"runup", "release", "flight", "shot", "post_shot"}
        dead_count = 0
        useful_count = 0
        action_count = 0
        for _ts, _frame, view, phase in tags:
            view_norm = (view or "").strip().lower()
            phase_norm = (phase or "").strip().lower()
            is_dead = view_norm in dead_views or phase_norm in dead_phases
            if is_dead:
                dead_count += 1
            is_action = phase_norm in action_phases
            if is_action:
                action_count += 1
            if view_norm in useful_views and is_action and not is_dead:
                useful_count += 1
        if useful_count == 0:
            if action_count == 0:
                return "no_action_tags"
            return "dead_or_no_useful_tags"
        if dead_count / max(1, len(tags)) >= 0.75:
            return "dead_dominated"
        return None

    def _scan_v3_fallback_window(
            self,
            *,
            event_ts: float,
            clip_start: float,
            clip_end: float,
            frames: list[tuple[float, np.ndarray]],
            tags: list[tuple[float, np.ndarray, str, str | None]],
            reason: str,
    ) -> tuple[
            float, float,
            list[tuple[float, np.ndarray]],
            list[tuple[float, np.ndarray, str, str | None]],
            dict]:
        scan_reason = self._fallback_window_scan_reason(tags, frames)
        block = {
            "used": False,
            "reason": scan_reason,
            "direction": None,
            "original_clip_start_ts": round(clip_start, 3),
            "original_clip_end_ts": round(clip_end, 3),
            "candidates_checked": 0,
        }
        if scan_reason is None:
            return clip_start, clip_end, frames, tags, block

        original_start = clip_start
        original_end = clip_end
        window_s = max(0.0, original_end - original_start)
        candidates_checked = 0
        forward_end = original_end
        max_forward_end = event_ts + MAX_EVENT_DRIFT_S
        forward_step_s = max(1.0, DELAYED_SCORE_FALLBACK_END_BEFORE_EVENT_S)
        while forward_end < max_forward_end:
            cand_end = min(max_forward_end, forward_end + forward_step_s)
            cand_start = max(0.0, cand_end - window_s)
            if cand_end <= cand_start or cand_end <= original_end:
                break
            candidates_checked += 1
            cand_frames = self._get_frames(cand_start, cand_end)
            cand_tags = self._get_tags(cand_start, cand_end, None)
            cand_reason = self._fallback_window_scan_reason(
                cand_tags, cand_frames)
            if cand_reason is None:
                log.warning(
                    f"[CHUNKER-V3-FALLBACK-SCAN] "
                    f"event_ts={event_ts:.2f} "
                    f"old=({original_start:.2f},{original_end:.2f}) "
                    f"new=({cand_start:.2f},{cand_end:.2f}) "
                    f"reason={scan_reason} "
                    f"direction=forward "
                    f"trigger={reason} "
                    f"candidates_checked={candidates_checked}")
                block.update({
                    "used": True,
                    "reason": scan_reason,
                    "direction": "forward",
                    "original_clip_start_ts": round(original_start, 3),
                    "original_clip_end_ts": round(original_end, 3),
                    "candidates_checked": candidates_checked,
                })
                return cand_start, cand_end, cand_frames, cand_tags, block
            forward_end = cand_end

        block["candidates_checked"] = candidates_checked
        return clip_start, clip_end, frames, tags, block

    def _classify_frames_for_event(self,
                                   frames: list[tuple[float, np.ndarray]],
                                   save_dir: Path | None,
                                   context: dict,
                                   tags: list[tuple[float, np.ndarray, str,
                                                    str | None]],
                                   clip_start: float,
                                   clip_end: float,
                                   source: str,
                                   reason: str,
                                   legacy_window: dict | None = None,
                                   open_scout_window: dict | None = None,
                                   open_scout_verdict: str | None = None,
                                   use_open_scout_spans: bool = False,
                                   v3_chunker_block: dict | None = None,
                                   fallback_block: dict | None = None,
                                   fallback_scan_block: dict | None = None,
                                   retrospective_rejection_block:
                                   dict | None = None,
                                   retrospective_safety_block:
                                   dict | None = None,
                                   ) -> dict | None:
        win_id = context["window_id"]
        log.info(f"[DWR] window #{win_id} source={source} "
                 f"frames={len(frames)} span={clip_start:.2f}->{clip_end:.2f} "
                 f"reason={reason}")

        if save_dir is None and self._save_root is not None:
            save_dir = self._save_root / f"window_{win_id:04d}"

        if save_dir is not None:
            save_dir.mkdir(parents=True, exist_ok=True)

        self._write_window_debug(
            save_dir=save_dir,
            context=context,
            tags=tags,
            clip_start=clip_start,
            clip_end=clip_end,
            source=source,
            reason=reason,
            frame_count=len(frames),
            legacy_window=legacy_window,
            open_scout_window=open_scout_window,
            open_scout_verdict=open_scout_verdict,
            use_open_scout_spans=use_open_scout_spans,
            v3_chunker_block=v3_chunker_block,
            fallback_block=fallback_block,
            fallback_scan_block=fallback_scan_block,
            retrospective_rejection_block=retrospective_rejection_block,
            retrospective_safety_block=retrospective_safety_block,
        )

        if len(frames) < self._min_frames:
            self._stats["windows_too_short"] += 1
            log.warning(f"[DWR] window #{win_id} too few frames "
                        f"({len(frames)}) — emitting unknown")
            return {
                "_method": "gemini",
                "_untrackable": True,
                "_skip_reason": "too_few_frames",
                "_window_id": win_id,
                "_window_reason": reason,
                "_window_source": source,
                "_window_dur_s": round(max(0.0, clip_end - clip_start), 2),
                "_window_frames": len(frames),
                "_window_start_ts": round(clip_start, 3),
                "_window_end_ts": round(clip_end, 3),
            }

        try:
            result = self._clf.classify_frames(
                frames=frames,
                runs=0,
                save_dir=str(save_dir) if save_dir else None,
                known_batsman_handed=context.get(
                    "known_batsman_handed", "unknown"),
                known_bowling_arm=context.get(
                    "known_bowling_arm", "unknown"),
            )
        except Exception as e:  # noqa: BLE001
            log.warning(f"[DWR] window #{win_id} classifier crashed: {e}")
            result = {
                "_method": "gemini",
                "_untrackable": True,
                "_skip_reason": "classifier_exception",
                "_classifier_error": str(e)[:300],
            }

        # Clip-write verification (2026-05-05).  Stat the
        # ``delivery_window.mp4`` the classifier just wrote to confirm
        # ffmpeg/cv2 didn't silently drop the file.  Tag is auto-
        # promoted to decisions[] by the DecisionLogHandler bridge.
        if save_dir is not None:
            try:
                from monitoring_emitters import verify_clip_write
                verify_clip_write(
                    mp4_path=save_dir / "delivery_window.mp4",
                    delivery_id=context.get("delivery_num"),
                    window_start=clip_start,
                    window_end=clip_end,
                    source=source,
                    logger=log,
                )
            except Exception as _ve:  # noqa: BLE001
                log.warning(
                    f"[CLIP-WRITE-FAIL] window #{win_id} "
                    f"verifier raised: {_ve!r}")

        result["_window_id"] = win_id
        result["_window_reason"] = reason
        result["_window_source"] = source
        result["_window_dur_s"] = round(max(0.0, clip_end - clip_start), 2)
        result["_window_frames"] = len(frames)
        result["_window_start_ts"] = round(clip_start, 3)
        result["_window_end_ts"] = round(clip_end, 3)
        result["_event_ts"] = round(float(context["event_ts"]), 3)
        result["_over_number"] = context.get("over_number")
        result["_innings"] = context.get("innings")
        return result

    def _write_window_debug(self,
                            save_dir: Path | None,
                            context: dict,
                            tags: list[tuple[float, np.ndarray, str,
                                             str | None]],
                            clip_start: float,
                            clip_end: float,
                            source: str,
                            reason: str,
                            frame_count: int,
                            legacy_window: dict | None = None,
                            open_scout_window: dict | None = None,
                            open_scout_verdict: str | None = None,
                            use_open_scout_spans: bool = False,
                            v3_chunker_block: dict | None = None,
                            fallback_block: dict | None = None,
                            fallback_scan_block: dict | None = None,
                            retrospective_rejection_block:
                            dict | None = None,
                            retrospective_safety_block:
                            dict | None = None,
                            ) -> None:
        if save_dir is None:
            return
        payload = {
            "delivery_num": context.get("delivery_num"),
            "window_id": context.get("window_id"),
            "event_ts": context.get("event_ts"),
            "over_number": context.get("over_number"),
            "innings": context.get("innings"),
            "event_type": context.get("event_type"),
            "runs": context.get("runs"),
            "window_source": source,
            "window_reason": reason,
            "clip_start_ts": clip_start,
            "clip_end_ts": clip_end,
            "frame_count": frame_count,
            # Parallel-Scout shadow telemetry (design memo §7.3) —
            # always populated regardless of USE_OPEN_SCOUT_SPANS so
            # offline analyzers can compare proposals across matches.
            "legacy_window": legacy_window,
            "open_scout_window": open_scout_window,
            "open_scout_verdict": open_scout_verdict,
            "use_open_scout_spans": bool(use_open_scout_spans),
            # Chunker v3 shadow block — see chunker_v3.md.  Always
            # populated when an aggregator is wired regardless of
            # USE_V3_CHUNKER_SPANS so offline analyzers can compare
            # proposals across matches.
            "v3_chunker": v3_chunker_block,
            # V3 None-fallback safety net (chunker_v3_setup.md).
            # ``used`` flips True when v3 + legacy both returned None
            # and the fixed-window fallback caught the event.  The
            # ``lookback_s`` / ``forward_s`` fields document the bounds
            # that produced the cut.
            "fallback": fallback_block,
            "fallback_scan_used": (
                bool(fallback_scan_block.get("used"))
                if fallback_scan_block else False),
            "fallback_scan_reason": (
                fallback_scan_block.get("reason")
                if fallback_scan_block else None),
            "fallback_scan_direction": (
                fallback_scan_block.get("direction")
                if fallback_scan_block else None),
            "fallback_scan_original_clip_start_ts": (
                fallback_scan_block.get("original_clip_start_ts")
                if fallback_scan_block else None),
            "fallback_scan_original_clip_end_ts": (
                fallback_scan_block.get("original_clip_end_ts")
                if fallback_scan_block else None),
            "fallback_scan_candidates_checked": (
                fallback_scan_block.get("candidates_checked")
                if fallback_scan_block else 0),
            "retrospective_span_rejected": (
                retrospective_rejection_block.get("reason")
                if retrospective_rejection_block else None),
            "rejected_span_start_ts": (
                retrospective_rejection_block.get("rejected_span_start_ts")
                if retrospective_rejection_block else None),
            "rejected_span_end_ts": (
                retrospective_rejection_block.get("rejected_span_end_ts")
                if retrospective_rejection_block else None),
            "rejected_clip_start_ts": (
                retrospective_rejection_block.get("rejected_clip_start_ts")
                if retrospective_rejection_block else None),
            "rejected_clip_end_ts": (
                retrospective_rejection_block.get("rejected_clip_end_ts")
                if retrospective_rejection_block else None),
            "rejection_event_safe_cutoff_ts": (
                retrospective_rejection_block.get(
                    "rejection_event_safe_cutoff_ts")
                if retrospective_rejection_block else None),
            "retrospective_span_safe_margin_s": (
                retrospective_safety_block.get("safe_margin_s")
                if retrospective_safety_block else None),
            "retrospective_span_rejection_threshold_s": (
                retrospective_safety_block.get("rejection_threshold_s")
                if retrospective_safety_block else None),
            "retrospective_span_has_dead_time_tag": (
                retrospective_safety_block.get("has_dead_time_tag")
                if retrospective_safety_block else None),
            "tags": [
                {
                    "ts": ts,
                    "camera_view": view,
                    "frame_phase": phase,
                }
                for ts, _frame, view, phase in tags
            ],
        }
        try:
            (save_dir / "window_debug.json").write_text(
                json.dumps(payload, indent=2))
        except Exception as e:  # noqa: BLE001
            log.warning(f"[DWR] could not save window debug: {e}")

    def _schedule_replay_capture(self,
                                 event_ts: float,
                                 delivery_num: int | None,
                                 save_dir: Path | None,
                                 over_number: float | None,
                                 event_type: str | None,
                                 runs: int,
                                 ) -> None:
        if save_dir is None:
            return
        self._pending_replay_jobs.append({
            "ready_ts": event_ts + self._replay_capture_s,
            "event_ts": event_ts,
            "delivery_num": delivery_num,
            "save_dir": save_dir,
            "over_number": over_number,
            "event_type": event_type,
            "runs": runs,
        })

    def _flush_replay_job(self, job: dict) -> None:
        start_ts = float(job["event_ts"])
        end_ts = float(job["ready_ts"])
        tags = self._get_tags(start_ts, end_ts, ("replay",))
        replay_dir = Path(job["save_dir"]) / "replay"
        replay_dir.mkdir(parents=True, exist_ok=True)

        picks = self._evenly_spaced_indices(len(tags), cap=8)
        for out_idx, src_idx in enumerate(picks):
            _ts, frame, _view, _phase = tags[src_idx]
            try:
                import cv2
                cv2.imwrite(str(replay_dir / f"replay_{out_idx:02d}.jpg"),
                            frame)
            except Exception as e:  # noqa: BLE001
                log.warning(f"[DWR] could not save replay frame: {e}")
                break

        payload = {
            "delivery_num": job.get("delivery_num"),
            "event_ts": job.get("event_ts"),
            "ready_ts": job.get("ready_ts"),
            "over_number": job.get("over_number"),
            "event_type": job.get("event_type"),
            "runs": job.get("runs"),
            "replay_tag_count": len(tags),
            "saved_frame_count": len(picks),
            "tags": [
                {
                    "ts": ts,
                    "camera_view": view,
                    "frame_phase": phase,
                }
                for ts, _frame, view, phase in tags
            ],
        }
        try:
            (replay_dir / "replay_capture.json").write_text(
                json.dumps(payload, indent=2))
        except Exception as e:  # noqa: BLE001
            log.warning(f"[DWR] could not save replay debug: {e}")

        self._stats["replay_jobs_flushed"] += 1
        self._stats["replay_tags_saved"] += len(tags)

    @staticmethod
    def _evenly_spaced_indices(n: int, cap: int) -> list[int]:
        if n <= 0:
            return []
        if n <= cap:
            return list(range(n))
        step = (n - 1) / float(cap - 1)
        out = [int(round(i * step)) for i in range(cap)]
        deduped: list[int] = []
        seen: set[int] = set()
        for idx in out:
            if idx in seen:
                continue
            seen.add(idx)
            deduped.append(idx)
        return deduped

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _tag_result(result: dict, runs: int,
                    event_type: str | None,
                    from_cache: bool) -> dict:
        """Copy + inject runs / event_type / from_cache flags."""
        out = dict(result)
        out["runs"] = runs
        out["_event_type"] = event_type
        out["_from_cache"] = from_cache
        return out

    def _skip_result(self,
                     win_id: int,
                     skip_reason: str,
                     context: dict,
                     save_dir: Path | None,
                     extra: dict | None = None) -> dict:
        """Build the untrackable-marker dict for phantom / duplicate
        events (RC-5).  Mirrors the shape of _classify_frames_for_event
        so downstream callers (ball_analyzer._run_gemini_delivery_analysis)
        treat it the same as a classifier-rejected result.

        Also writes a minimal window_debug.json so these cases show up
        in the audit trail — we want to be able to grep the deliveries
        folder later and find every skipped phantom, not silently drop
        them.
        """
        event_ts = float(context.get("event_ts") or 0.0)
        runs = int(context.get("runs") or 0)
        if save_dir is None and self._save_root is not None:
            save_dir = self._save_root / f"window_{win_id:04d}"
        if save_dir is not None:
            try:
                save_dir.mkdir(parents=True, exist_ok=True)
                self._write_window_debug(
                    save_dir=save_dir,
                    context=context,
                    tags=[],
                    clip_start=event_ts,
                    clip_end=event_ts,
                    source="skipped",
                    reason=skip_reason,
                    frame_count=0,
                )
            except Exception as e:  # noqa: BLE001
                log.debug(f"[DWR] skip_result debug write swallowed: {e}")
        result: dict = {
            "_method": "gemini",
            "_untrackable": True,
            "_skip_reason": skip_reason,
            "_window_id": win_id,
            "_window_source": "skipped",
            "_window_reason": skip_reason,
            "_window_dur_s": 0.0,
            "_window_frames": 0,
            "_window_start_ts": round(event_ts, 3),
            "_window_end_ts": round(event_ts, 3),
            "_event_ts": round(event_ts, 3),
            "_over_number": context.get("over_number"),
            "_innings": context.get("innings"),
            "runs": runs,
            "_event_type": context.get("event_type"),
            "_from_cache": False,
        }
        if extra:
            for k, v in extra.items():
                result[f"_{k}"] = v
        return result


def _span_overlap_ratio(a: tuple[float, float],
                        b: tuple[float, float]) -> float:
    """Return the Jaccard-like overlap ratio of two time spans.

    Ratio = intersection_duration / min(a_duration, b_duration).
    Using ``min`` rather than ``union`` means a shorter span that is
    fully contained in a longer one scores 1.0 — which is the d025/d026
    case we want to flag (d026's 16.7s clip was entirely inside d025's
    22.2s clip, same clip_end_ts).
    """
    a_lo, a_hi = a
    b_lo, b_hi = b
    if a_hi <= a_lo or b_hi <= b_lo:
        return 0.0
    inter_lo = max(a_lo, b_lo)
    inter_hi = min(a_hi, b_hi)
    if inter_hi <= inter_lo:
        return 0.0
    inter = inter_hi - inter_lo
    shorter = min(a_hi - a_lo, b_hi - b_lo)
    if shorter <= 0:
        return 0.0
    return inter / shorter
