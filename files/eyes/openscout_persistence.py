"""OpenScout output persistence (Layer A + Layer B).

Layer A — per-frame JSONL sidecar at ``logs/openscout-<session>.jsonl``.
One record per OpenScout invocation (success / error / rate-gate skip).

Layer B — per-span clip archive at
``files/logs/openscout_spans/<session>/span_<NNNN>/``:
  * ``clip.mp4`` (frame-buffer slice with ``pre_pad_s`` / ``post_pad_s``)
  * ``metadata.json``
  * ``classifications.jsonl`` (Layer A records inside the span window)

Decoupled validation export — :class:`OpenScoutDeliveryWriter` writes
``files/logs/openscout_deliveries/<session>/delivery_<NNNN>.mp4`` plus
companion JSON (no score-event or DWR coupling).

Background: per
``files/docs/investigations/youtube_test_delivery_detection_analysis.md``
§7.1 / §10, OpenScout per-frame classifications used to live only in
``SpanAggregator``'s in-memory state and a rotating shared log; the
next session's run truncated that log and made post-match analysis
irrecoverable.  These two persistence layers fix that.

Failure isolation is total: every disk operation is wrapped in
``try/except Exception`` and only logs.  If the disk fills, JSON
serialisation breaks, or the frame buffer is empty, the pipeline keeps
running unaffected — Scout / scoring / WS broadcast are isolated.
"""
from __future__ import annotations

import collections
import json
import logging
import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np

log = logging.getLogger("open_scout_persistence")
try:
    from eyes.cricket_logger import _ensure_file_handler
    log.addHandler(_ensure_file_handler())
    log.setLevel(logging.INFO)
except Exception:  # noqa: BLE001
    pass

_DEFAULT_PRE_PAD_S = 1.0
_DEFAULT_POST_PAD_S = 1.0
_RAW_TEXT_MAX = 500
_RECORDS_BUFFER_MAX = 4096


def _truncate(text: str | None, n: int = _RAW_TEXT_MAX) -> str:
    if not text:
        return ""
    text = text.strip()
    return text if len(text) <= n else text[:n]


# ── Layer A ────────────────────────────────────────────────────────


class OpenScoutSidecar:
    """Per-frame JSONL sidecar (``logs/openscout-<session>.jsonl``).

    Thread-safe: every record write takes a lock and flushes immediately
    so a Ctrl-C still leaves a valid file.  Records are also kept in a
    bounded in-memory deque so :class:`OpenScoutSpanArchive` can pull
    classifications-in-range without re-reading the JSONL.
    """

    def __init__(self,
                 session_id: str,
                 *,
                 log_dir: str | Path = "logs",
                 buffer_max: int = _RECORDS_BUFFER_MAX):
        self.session_id = session_id
        self._lock = threading.Lock()
        self._records: collections.deque[dict] = collections.deque(
            maxlen=buffer_max)
        self._fh = None
        self._path: Path | None = None
        try:
            log_root = Path(log_dir)
            log_root.mkdir(parents=True, exist_ok=True)
            self._path = log_root / f"openscout-{session_id}.jsonl"
            self._fh = open(self._path, "a", encoding="utf-8")
            log.info(
                f"[OPEN-SCOUT-SIDECAR] writing per-frame JSONL to "
                f"{self._path}")
        except Exception as e:  # noqa: BLE001
            log.warning(
                f"[OPEN-SCOUT-SIDECAR] could not open sidecar file "
                f"({e}); per-frame persistence disabled this run")

    @property
    def path(self) -> Path | None:
        return self._path

    def record_classification(self,
                              *,
                              ts: float,
                              frame_idx: int | None,
                              frame_class: str | None,
                              raw_text: str | None,
                              latency_ms: int | None,
                              error: str | None = None,
                              rate_gate_reason: str = "passed",
                              tokens_total: int = 0) -> None:
        rec = {
            "ts": float(ts),
            "frame_idx": frame_idx,
            "frame_class": frame_class,
            "raw_text": _truncate(raw_text),
            "latency_ms": (
                int(latency_ms) if latency_ms is not None else None),
            "error": error,
            "rate_gate_reason": rate_gate_reason,
            "tokens_total": int(tokens_total) if tokens_total else 0,
        }
        self._append(rec)

    def record_skip(self,
                    *,
                    ts: float,
                    frame_idx: int | None,
                    rate_gate_reason: str) -> None:
        rec = {
            "ts": float(ts),
            "frame_idx": frame_idx,
            "frame_class": None,
            "raw_text": "",
            "latency_ms": None,
            "error": None,
            "rate_gate_reason": rate_gate_reason,
        }
        self._append(rec)

    def records_in_range(self,
                         start_ts: float,
                         end_ts: float) -> list[dict]:
        with self._lock:
            return [
                dict(r) for r in self._records
                if start_ts <= r.get("ts", 0.0) <= end_ts
            ]

    def close(self) -> None:
        with self._lock:
            try:
                if self._fh is not None:
                    self._fh.flush()
                    self._fh.close()
            except Exception:  # noqa: BLE001
                pass
            self._fh = None

    # ── internals ──────────────────────────────────────────────

    def _append(self, rec: dict) -> None:
        try:
            line = json.dumps(rec, ensure_ascii=False, default=str)
        except Exception as e:  # noqa: BLE001
            log.warning(
                f"[OPEN-SCOUT-SIDECAR] json serialisation failed "
                f"({e}); dropping record")
            return
        with self._lock:
            self._records.append(rec)
            if self._fh is None:
                return
            try:
                self._fh.write(line)
                self._fh.write("\n")
                self._fh.flush()
            except Exception as e:  # noqa: BLE001
                log.warning(
                    f"[OPEN-SCOUT-SIDECAR] write failed ({e}); "
                    f"closing sidecar to avoid log spam")
                try:
                    self._fh.close()
                except Exception:  # noqa: BLE001
                    pass
                self._fh = None


# ── Layer B ────────────────────────────────────────────────────────


class OpenScoutSpanArchive:
    """Per-span clip + metadata + classifications archive.

    Wired as a callback on ``SpanAggregator``: every committed span
    becomes ``files/logs/openscout_spans/<session>/span_<NNNN>/``
    containing ``clip.mp4`` (with pre/post padding from the rolling
    frame buffer), ``metadata.json``, and ``classifications.jsonl``.

    When ``DeliveryWindowRecorder.classify_for_score_event`` later
    matches a span to a score event, it calls
    :meth:`note_match_to_event` which patches the existing
    ``metadata.json`` with the matched ``delivery_id`` + verdict.
    """

    def __init__(self,
                 session_id: str,
                 *,
                 frame_source_fn: Callable[
                     [float, float], list[tuple[float, np.ndarray]]],
                 sidecar: OpenScoutSidecar | None = None,
                 root: str | Path = "files/logs/openscout_spans",
                 pre_pad_s: float = _DEFAULT_PRE_PAD_S,
                 post_pad_s: float = _DEFAULT_POST_PAD_S):
        self.session_id = session_id
        self._frame_source_fn = frame_source_fn
        self._sidecar = sidecar
        self._pre_pad_s = pre_pad_s
        self._post_pad_s = post_pad_s
        self._lock = threading.Lock()
        self._span_dirs: dict[int, Path] = {}
        self._root: Path | None = None
        try:
            root_path = Path(root) / session_id
            root_path.mkdir(parents=True, exist_ok=True)
            self._root = root_path
            log.info(
                f"[OPEN-SCOUT-ARCHIVE] writing per-span bundles to "
                f"{root_path}")
        except Exception as e:  # noqa: BLE001
            log.warning(
                f"[OPEN-SCOUT-ARCHIVE] mkdir {root}/{session_id} "
                f"failed: {e}; archive disabled")

    @property
    def root(self) -> Path | None:
        return self._root

    def on_span_committed(self, span) -> None:
        """Callback invoked by :class:`SpanAggregator` after a commit.

        Runs synchronously on the aggregator's caller thread (typically
        the per-frame loop) but outside the aggregator's lock.  Keep
        work bounded; mp4 encode of a 2–10 s span tops out at a few
        hundred ms in practice.
        """
        if self._root is None:
            return
        try:
            self._write_span(span)
        except Exception as e:  # noqa: BLE001
            log.warning(
                f"[OPEN-SCOUT-ARCHIVE] span "
                f"{getattr(span, 'span_id', '?')} persist failed: {e}")

    def note_match_to_event(self,
                            *,
                            span_id: int | None,
                            event_ts: float,
                            delivery_id: str | None,
                            verdict: str) -> None:
        """Update an existing span's metadata.json with match details.

        Tolerates a missing span dir (e.g. archive disabled, or span
        cleaned up after retention) — logs and returns.
        """
        if not span_id:
            return
        with self._lock:
            dpath = self._span_dirs.get(int(span_id))
        if dpath is None or not dpath.exists():
            return
        meta_path = dpath / "metadata.json"
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception as e:  # noqa: BLE001
            log.warning(
                f"[OPEN-SCOUT-ARCHIVE] note_match: read {meta_path} "
                f"failed: {e}")
            return
        meta["matched_to_event"] = {
            "event_ts": float(event_ts),
            "delivery_id": delivery_id,
            "verdict": verdict,
            "noted_at_ts": time.time(),
        }
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, default=str)
        except Exception as e:  # noqa: BLE001
            log.warning(
                f"[OPEN-SCOUT-ARCHIVE] note_match: write {meta_path} "
                f"failed: {e}")

    # ── internals ──────────────────────────────────────────────

    def _write_span(self, span) -> None:
        if self._root is None:
            return
        span_id = int(getattr(span, "span_id", 0) or 0)
        if span_id <= 0:
            return
        dname = f"span_{span_id:04d}"
        dpath = self._root / dname
        try:
            dpath.mkdir(parents=True, exist_ok=True)
        except Exception as e:  # noqa: BLE001
            log.warning(
                f"[OPEN-SCOUT-ARCHIVE] mkdir {dpath} failed: {e}")
            return
        with self._lock:
            self._span_dirs[span_id] = dpath

        clip_start = max(0.0, float(span.start_ts) - self._pre_pad_s)
        clip_end = float(span.end_ts) + self._post_pad_s

        cls_records: list[dict] = []
        if self._sidecar is not None:
            cls_records = self._sidecar.records_in_range(
                span.start_ts, span.end_ts)

        n_action = sum(
            1 for r in cls_records if r.get("frame_class") == "action")
        n_other = sum(
            1 for r in cls_records
            if r.get("frame_class") not in (None, "action"))

        meta = {
            "span_id": dname,
            "span_id_int": span_id,
            "session_id": self.session_id,
            "span_start_ts": float(span.start_ts),
            "span_end_ts": float(span.end_ts),
            "duration_s": float(getattr(span, "duration_s", max(
                0.0, span.end_ts - span.start_ts))),
            "frame_count": int(getattr(span, "frame_count", 0)),
            "frame_class": str(getattr(span, "frame_class", "")),
            "n_classifications_in_span": len(cls_records),
            "n_frames_classified_action": n_action,
            "n_frames_classified_other": n_other,
            "clip_pre_pad_s": self._pre_pad_s,
            "clip_post_pad_s": self._post_pad_s,
            "clip_start_ts": clip_start,
            "clip_end_ts": clip_end,
            "matched_to_event": None,
            "text_samples": list(
                getattr(span, "text_samples", []) or []),
            "written_at_ts": time.time(),
        }

        cjs_path = dpath / "classifications.jsonl"
        try:
            with open(cjs_path, "w", encoding="utf-8") as f:
                for r in cls_records:
                    f.write(
                        json.dumps(r, ensure_ascii=False, default=str))
                    f.write("\n")
        except Exception as e:  # noqa: BLE001
            log.warning(
                f"[OPEN-SCOUT-ARCHIVE] write {cjs_path} failed: {e}")

        clip_meta: dict = {
            "frames_written": 0,
            "filename": None,
            "note": None,
        }
        try:
            frames = self._frame_source_fn(clip_start, clip_end)
        except Exception as e:  # noqa: BLE001
            log.warning(
                f"[OPEN-SCOUT-ARCHIVE] frame_source_fn failed: {e}")
            frames = []
        if frames:
            mp4_path = dpath / "clip.mp4"
            try:
                # Local import keeps gemini_delivery_classifier and its
                # transitive imports off this module's import path.
                from gemini_delivery_classifier import (
                    compile_frames_to_mp4,
                )
                compile_frames_to_mp4(
                    frames=list(frames),
                    out_path=str(mp4_path),
                )
                clip_meta = {
                    "frames_written": len(frames),
                    "filename": mp4_path.name,
                    "note": None,
                }
            except Exception as e:  # noqa: BLE001
                clip_meta["note"] = f"mp4 compile failed: {e}"
                log.warning(
                    f"[OPEN-SCOUT-ARCHIVE] mp4 compile failed for "
                    f"{dname}: {e}")
        else:
            clip_meta["note"] = "frame buffer empty for span window"
        meta["clip"] = clip_meta

        meta_path = dpath / "metadata.json"
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, default=str)
        except Exception as e:  # noqa: BLE001
            log.warning(
                f"[OPEN-SCOUT-ARCHIVE] write {meta_path} failed: {e}")

        log.info(
            f"[OPEN-SCOUT-ARCHIVE] {dname} class={span.frame_class} "
            f"dur={meta['duration_s']:.1f}s "
            f"frames_in_clip={clip_meta['frames_written']} "
            f"cls_records={len(cls_records)}")


def _duration_band(duration_s: float) -> str:
    if duration_s < 3.0:
        return "short"
    if duration_s <= 15.0:
        return "normal"
    return "long"


def _safe_class_slug(frame_class: str) -> str:
    s = (frame_class or "unknown").strip().lower().replace(" ", "_")
    out = "".join(
        c if c.isalnum() or c in "-_" else "_" for c in s)
    return (out or "unknown")[:64]


class OpenScoutDeliveryWriter:
    """Write operator-validation clips for every committed OpenScout span.

    Decoupled from score events and DeliveryWindowRecorder.  One mp4 +
    JSON metadata per committed span.  Action spans use sequential
    ``delivery_<NNNN>.mp4`` names; other classes land under
    ``non_action/``.  Clips may race the main pipeline at the frame
    buffer (same model as OpenScoutSpanArchive).  Non-action clips can
    be disabled via ``save_non_action=False`` if disk is a concern.
    Only spans that clear ``SpanAggregator``'s ``MIN_SPAN_FRAMES``
    threshold reach this callback (singleton observations never commit).
    """

    def __init__(self,
                 session_id: str,
                 *,
                 frame_source_fn: Callable[
                     [float, float], list[tuple[float, np.ndarray]]],
                 sidecar: OpenScoutSidecar | None = None,
                 root: str | Path = "files/logs/openscout_deliveries",
                 pre_pad_s: float = _DEFAULT_PRE_PAD_S,
                 post_pad_s: float = _DEFAULT_POST_PAD_S,
                 save_non_action: bool = True):
        self.session_id = session_id
        self._frame_source_fn = frame_source_fn
        self._sidecar = sidecar
        self._pre_pad_s = pre_pad_s
        self._post_pad_s = post_pad_s
        self._save_non_action = save_non_action
        self._lock = threading.Lock()
        self._next_delivery_seq = 1
        self._root: Path | None = None
        try:
            root_path = Path(root) / session_id
            root_path.mkdir(parents=True, exist_ok=True)
            if self._save_non_action:
                (root_path / "non_action").mkdir(parents=True, exist_ok=True)
            self._root = root_path
            log.info(
                f"[OPEN-SCOUT-DELIVERY] writing validation clips under "
                f"{root_path}")
        except Exception as e:  # noqa: BLE001
            log.warning(
                f"[OPEN-SCOUT-DELIVERY] mkdir {root}/{session_id} "
                f"failed: {e}; delivery writer disabled")

    @property
    def root(self) -> Path | None:
        return self._root

    def on_span_committed(self, span) -> None:
        if self._root is None:
            return
        try:
            self._write_span(span)
        except Exception as e:  # noqa: BLE001
            log.warning(
                f"[OPEN-SCOUT-DELIVERY] span "
                f"{getattr(span, 'span_id', '?')} persist failed: {e}")

    def _write_span(self, span) -> None:
        if self._root is None:
            return
        span_id = int(getattr(span, "span_id", 0) or 0)
        if span_id <= 0:
            return
        fc_raw = str(getattr(span, "frame_class", "") or "")
        is_action = fc_raw == "action"
        if not is_action and not self._save_non_action:
            return

        duration_s = float(getattr(
            span, "duration_s",
            max(0.0, float(span.end_ts) - float(span.start_ts))))
        band = _duration_band(duration_s)

        cls_records: list[dict] = []
        if self._sidecar is not None:
            cls_records = self._sidecar.records_in_range(
                span.start_ts, span.end_ts)
        n_action = sum(
            1 for r in cls_records if r.get("frame_class") == "action")
        n_other = sum(
            1 for r in cls_records
            if r.get("frame_class") not in (None, "action"))

        clip_start = max(0.0, float(span.start_ts) - self._pre_pad_s)
        clip_end = float(span.end_ts) + self._post_pad_s

        delivery_seq: int | None
        if is_action:
            with self._lock:
                delivery_seq = self._next_delivery_seq
                self._next_delivery_seq += 1
            seq4 = delivery_seq
            base = f"delivery_{seq4:04d}"
            out_dir = self._root
        else:
            delivery_seq = None
            slug = _safe_class_slug(fc_raw)
            base = f"span_{span_id:04d}_{slug}"
            out_dir = self._root / "non_action"

        mp4_path = out_dir / f"{base}.mp4"
        meta_path = out_dir / f"{base}_metadata.json"

        meta = {
            "delivery_seq": delivery_seq,
            "session_id": self.session_id,
            "span_id": span_id,
            "span_start_ts": float(span.start_ts),
            "span_end_ts": float(span.end_ts),
            "duration_s": duration_s,
            "duration_band": band,
            "frame_count": int(getattr(span, "frame_count", 0)),
            "frame_class": fc_raw,
            "n_classifications_action": n_action,
            "n_classifications_other": n_other,
            "clip_pre_pad_s": self._pre_pad_s,
            "clip_post_pad_s": self._post_pad_s,
            "clip_start_ts": clip_start,
            "clip_end_ts": clip_end,
            "mp4_path": str(mp4_path),
            "frames_written": 0,
            "mp4_exists": False,
            "frame_source_error": None,
            "compile_error": None,
            "note": None,
            "manual_review": None,
        }

        frames_written = 0
        try:
            frames = self._frame_source_fn(clip_start, clip_end)
        except Exception as e:  # noqa: BLE001
            meta["frame_source_error"] = str(e)
            log.warning(
                f"[OPEN-SCOUT-DELIVERY] frame_source_fn failed: {e}")
            frames = []
        if frames:
            try:
                from gemini_delivery_classifier import compile_frames_to_mp4
                compile_frames_to_mp4(
                    frames=list(frames),
                    out_path=str(mp4_path),
                )
                frames_written = len(frames)
            except Exception as e:  # noqa: BLE001
                meta["compile_error"] = str(e)
                log.warning(
                    f"[OPEN-SCOUT-DELIVERY] mp4 compile failed for "
                    f"{base}: {e}")
        else:
            meta["note"] = "frame buffer empty for span window"
            log.warning(
                f"[OPEN-SCOUT-DELIVERY] no frames for {base} window")
        meta["frames_written"] = frames_written
        meta["mp4_exists"] = mp4_path.exists()

        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, default=str)
        except Exception as e:  # noqa: BLE001
            log.warning(
                f"[OPEN-SCOUT-DELIVERY] write {meta_path} failed: {e}")

        log.info(
            f"[OPEN-SCOUT-DELIVERY] {base} class={fc_raw} "
            f"band={band} dur={duration_s:.1f}s "
            f"frames_in_clip={frames_written}")


__all__ = [
    "OpenScoutSidecar",
    "OpenScoutSpanArchive",
    "OpenScoutDeliveryWriter",
]
