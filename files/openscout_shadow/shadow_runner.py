"""OpenScout shadow-mode runner — Component 3.

Wires Stage 1 (BroadcastModeFilter) + Stage 2 (DeliverySpanSelector)
+ Stage 3 (Qwen) into a same-process daemon thread that runs alongside
the main pipeline. Read-only against main pipeline state; output is a
log-only JSONL file. The shadow thread can never crash the main
pipeline — every tick is wrapped, every public push is bounded, and
overflow drops oldest rather than blocking the caller.

See files/docs/investigations/openscout_shadow_runner.md for the
architecture, JSONL schema, and SHADOW_MODE contract.
"""
from __future__ import annotations

import atexit
import json
import logging
import queue
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from eyes.broadcast_mode_filter import BroadcastModeFilter, STATE_ACTIVE
from eyes.delivery_span_selector import DeliverySpan, DeliverySpanSelector


_DEFAULT_OUTPUT_DIR = Path("files/logs/openscout_shadow")

_FRAME_QUEUE_MAX = 60
_SCOUT_QUEUE_MAX = 100
_SPAN_QUEUE_MAX = 50

_TICK_IDLE_SLEEP_S = 0.02
_SCOUTS_PER_TICK = 16
_FRAMES_PER_TICK = 8
_STOP_JOIN_TIMEOUT_S = 10.0


class OpenScoutShadowRunner:
    """Background shadow runner. See module docstring."""

    def __init__(
        self,
        session_id: str,
        output_dir: Path = _DEFAULT_OUTPUT_DIR,
        qwen_classifier: Optional[Callable[..., dict]] = None,
        log: Optional[logging.Logger] = None,
        frame_source: Optional[Any] = None,
        ingest_fps: float = 5.0,
    ):
        self.session_id = session_id
        self.output_dir = Path(output_dir)
        self.qwen_classifier = qwen_classifier
        self.log = log or logging.getLogger("openscout_shadow")

        self._frame_q: queue.Queue = queue.Queue(maxsize=_FRAME_QUEUE_MAX)
        self._scout_q: queue.Queue = queue.Queue(maxsize=_SCOUT_QUEUE_MAX)
        self._span_q: queue.Queue = queue.Queue(maxsize=_SPAN_QUEUE_MAX)

        self._shutdown = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._start_lock = threading.Lock()
        self._started = False
        self._stopped = False

        self._frame_source = frame_source
        self._ingest_fps = max(0.0, float(ingest_fps))
        self._ingest_thread: Optional[threading.Thread] = None
        self._ingest_shutdown = threading.Event()
        self._last_ingested_frame_id: Optional[int] = None

        self._stage1 = BroadcastModeFilter(
            on_window_open=self._handle_window_open,
            on_window_close=self._handle_window_close,
        )
        self._stage2 = DeliverySpanSelector(
            on_span_emitted=self._handle_span_emitted,
        )

        self._window_open_ts: Optional[float] = None
        self._window_close_ts: Optional[float] = None

        self._n_frames = 0
        self._n_scouts = 0
        self._n_dropped_inactive = 0
        self._n_dropped_overflow = 0
        self._n_emitted = 0
        self._n_qwen_errors = 0
        self._n_qwen_dispatched = 0
        self._n_stage1_windows_opened = 0
        self._n_stage1_windows_closed = 0
        self._n_stage2_spans_emitted = 0
        self._n_score_events_marked = 0
        self._n_exceptions = 0
        self._last_record_ts: Optional[float] = None
        self._delivery_seq = 0
        self._emitted_spans: list[DeliverySpan] = []
        self._emitted_spans_lock = threading.Lock()

        self._jsonl_fh = None
        self._jsonl_path: Optional[Path] = None

    # ── public API ──────────────────────────────────────────────────

    def start(self) -> None:
        with self._start_lock:
            if self._started:
                return
            self._started = True
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._jsonl_path = self.output_dir / f"{self.session_id}.jsonl"
        self._jsonl_fh = open(self._jsonl_path, "a", buffering=1)
        self._write_record({
            "_header": True,
            "session_id": self.session_id,
            "started_ts": time.time(),
            "schema_version": 1,
        })
        self._thread = threading.Thread(
            target=self._thread_main,
            name="openscout-shadow",
            daemon=True,
        )
        self._thread.start()
        if self._has_own_ingest:
            self._ingest_thread = threading.Thread(
                target=self._ingest_loop,
                name="openscout-shadow-ingest",
                daemon=True,
            )
            self._ingest_thread.start()
            self.log.info(
                "[SHADOW] ingest thread started @%.1f fps",
                self._ingest_fps)
        atexit.register(self._atexit_stop)
        self.log.info(
            "[SHADOW] runner started, output=%s", self._jsonl_path)

    def stop(self) -> None:
        if not self._started or self._stopped:
            return
        self._stopped = True
        self._ingest_shutdown.set()
        self._shutdown.set()
        if self._ingest_thread is not None and self._ingest_thread.is_alive():
            self._ingest_thread.join(timeout=2.0)
        if self._thread is not None:
            self._thread.join(timeout=_STOP_JOIN_TIMEOUT_S)
        try:
            self._stage2.flush()
        except Exception:
            self.log.exception("[SHADOW] stage2 flush failed")
        while True:
            try:
                meta = self._span_q.get_nowait()
            except queue.Empty:
                break
            self._dispatch_qwen_and_write(meta)
        if self._jsonl_fh is not None:
            try:
                self._write_record({
                    "_footer": True,
                    "session_id": self.session_id,
                    "stopped_ts": time.time(),
                    "n_frames": self._n_frames,
                    "n_scouts": self._n_scouts,
                    "n_dropped_inactive": self._n_dropped_inactive,
                    "n_dropped_overflow": self._n_dropped_overflow,
                    "n_emitted": self._n_emitted,
                    "n_qwen_errors": self._n_qwen_errors,
                })
                self._jsonl_fh.close()
            except Exception:
                self.log.exception("[SHADOW] footer / close failed")
            finally:
                self._jsonl_fh = None
        self.log.info("[SHADOW] runner stopped")

    def add_frame(self, ts: float, frame_bgr: np.ndarray) -> None:
        if not self._started or self._stopped:
            return
        self._enqueue_drop_oldest(self._frame_q, (float(ts), frame_bgr))

    def add_scout_result(self, scout_result: dict) -> None:
        if not self._started or self._stopped:
            return
        self._enqueue_drop_oldest(self._scout_q, dict(scout_result))

    def mark_score_event(self, ts: float) -> None:
        """Pass score-event timestamp through to ``DeliverySpanSelector``
        for temporal anchoring (sub_clip_delivery_isolation_v4.md §8.7).

        Called from the main pipeline on every accepted score commit;
        crossing thread boundaries here is safe because the underlying
        list mutation is atomic in CPython and the selector reads it
        only on its own tick.
        """
        if not self._started or self._stopped:
            return
        try:
            self._stage2.mark_score_event(float(ts))
            self._n_score_events_marked += 1
        except Exception:
            self._n_exceptions += 1
            self.log.exception(
                "[SHADOW] mark_score_event in stage2 failed")
        try:
            self._stage1.mark_score_event(float(ts))
        except Exception:
            self._n_exceptions += 1
            self.log.exception(
                "[SHADOW] mark_score_event in stage1 failed")

    def find_stage2_span_for_event(
            self,
            event_ts: float,
            *,
            pre_window_s: float = 15.0,
    ) -> Optional[tuple[float, float]]:
        """Look up the most recent Stage-2 span that plausibly belongs
        to ``event_ts``.

        Returns ``(raw_start_ts, raw_end_ts)`` of the closest span whose
        start lies in ``[event_ts - pre_window_s, event_ts]``.  Used by
        path-1 clip extraction when ``USE_OPEN_SCOUT_SPANS=1`` (see
        ``files/docs/investigations/sub_clip_delivery_isolation_v4.md``
        §8).  Returns ``None`` if no matching span has been emitted yet
        (Stage 2 closure hold = 3 s plus selection latency).
        """
        with self._emitted_spans_lock:
            spans = list(self._emitted_spans)
        candidates = [
            s for s in spans
            if (event_ts - pre_window_s) <= s.raw_start_ts <= event_ts
        ]
        if not candidates:
            return None
        best = max(candidates, key=lambda s: s.raw_start_ts)
        return (best.raw_start_ts, best.raw_end_ts)

    def stats(self) -> dict:
        """Snapshot of runner counters (Component 3 telemetry).

        Cheap to call (atomic-int reads + ``Queue.qsize`` ints).  Wired
        into the periodic ``[SHADOW-STATS]`` heartbeat from
        ``files/test_pipeline.py`` and into the live monitor's shadow
        panel.  Schema is part of the SHADOW_MODE operational contract.
        """
        thread = self._thread
        return {
            "thread_alive": bool(thread is not None and thread.is_alive()),
            "frames_received": int(self._n_frames),
            "scout_results_received": int(self._n_scouts),
            "stage1_windows_opened": int(self._n_stage1_windows_opened),
            "stage1_windows_closed": int(self._n_stage1_windows_closed),
            "stage2_spans_emitted": int(self._n_stage2_spans_emitted),
            "score_events_marked": int(self._n_score_events_marked),
            "stage3_qwen_dispatched": int(self._n_qwen_dispatched),
            "stage3_qwen_failed": int(self._n_qwen_errors),
            "exceptions_total": int(self._n_exceptions),
            "queue_depth_frame": self._frame_q.qsize(),
            "queue_depth_scout": self._scout_q.qsize(),
            "queue_depth_span": self._span_q.qsize(),
            "last_record_ts": self._last_record_ts,
        }

    @property
    def _has_own_ingest(self) -> bool:
        return self._frame_source is not None and self._ingest_fps > 0.0

    # ── thread internals ────────────────────────────────────────────

    def _ingest_loop(self) -> None:
        interval = 1.0 / self._ingest_fps
        while not self._ingest_shutdown.is_set():
            try:
                getter = getattr(
                    self._frame_source, "get_latest_bgr", None)
                if getter is None:
                    getter = getattr(self._frame_source, "get_latest", None)
                frame = getter() if getter is not None else None
                if frame is not None:
                    fid = id(frame)
                    if fid != self._last_ingested_frame_id:
                        self.add_frame(time.time(), frame)
                        self._last_ingested_frame_id = fid
            except Exception:
                self._n_exceptions += 1
                self.log.exception("[SHADOW] ingest_loop error")
            self._ingest_shutdown.wait(interval)

    def _thread_main(self) -> None:
        while not self._shutdown.is_set():
            try:
                self._tick()
            except Exception:
                self._n_exceptions += 1
                self.log.exception("[SHADOW] tick failed, continuing")
                time.sleep(0.1)

    def _tick(self) -> None:
        did_work = False
        for _ in range(_SCOUTS_PER_TICK):
            try:
                sr = self._scout_q.get_nowait()
            except queue.Empty:
                break
            did_work = True
            self._n_scouts += 1
            self._process_scout(sr)
        for _ in range(_FRAMES_PER_TICK):
            try:
                ts, frame = self._frame_q.get_nowait()
            except queue.Empty:
                break
            did_work = True
            self._n_frames += 1
            try:
                self._stage1.add_frame(ts, frame)
            except Exception:
                self._n_exceptions += 1
                self.log.exception("[SHADOW] stage1 add_frame failed")
        while True:
            try:
                meta = self._span_q.get_nowait()
            except queue.Empty:
                break
            did_work = True
            self._dispatch_qwen_and_write(meta)
        if not did_work:
            time.sleep(_TICK_IDLE_SLEEP_S)

    def _process_scout(self, sr: dict) -> None:
        if self._stage1.current_state() != STATE_ACTIVE:
            self._n_dropped_inactive += 1
            return
        try:
            self._stage2.add_scout_result(sr)
        except Exception:
            self._n_exceptions += 1
            self.log.exception("[SHADOW] stage2 add_scout_result failed")

    def _handle_window_open(self, ts: float) -> None:
        self._window_open_ts = ts
        self._window_close_ts = None
        self._n_stage1_windows_opened += 1

    def _handle_window_close(self, ts: float) -> None:
        self._window_close_ts = ts
        self._n_stage1_windows_closed += 1
        try:
            self._stage2.flush()
        except Exception:
            self._n_exceptions += 1
            self.log.exception("[SHADOW] stage2 flush on close failed")

    def _handle_span_emitted(self, span: DeliverySpan) -> None:
        self._n_stage2_spans_emitted += 1
        with self._emitted_spans_lock:
            self._emitted_spans.append(span)
            if len(self._emitted_spans) > 64:
                self._emitted_spans = self._emitted_spans[-32:]
        meta = {
            "span": span,
            "window_open_ts": self._window_open_ts,
            "window_close_ts": self._window_close_ts,
        }
        try:
            self._span_q.put_nowait(meta)
        except queue.Full:
            self._n_dropped_overflow += 1
            self.log.warning(
                "[SHADOW] span_q full, dropping span sid=%s",
                span.diagnostic.get("span_id"))

    def _dispatch_qwen_and_write(self, meta: dict) -> None:
        span: DeliverySpan = meta["span"]
        self._delivery_seq += 1
        delivery_id = f"{self.session_id}-d{self._delivery_seq:04d}"

        qwen_details: Optional[dict] = None
        qwen_error: Optional[str] = None
        latency_ms = 0
        if self.qwen_classifier is None:
            qwen_details = {"qwen_disabled": True}
        else:
            self._n_qwen_dispatched += 1
            t0 = time.monotonic()
            try:
                qwen_details = self.qwen_classifier(
                    span_start_ts=span.start_ts,
                    span_end_ts=span.end_ts,
                    span=span,
                )
            except Exception as e:  # noqa: BLE001
                qwen_error = f"{type(e).__name__}: {e}"
                self._n_qwen_errors += 1
                self._n_exceptions += 1
                self.log.exception("[SHADOW] qwen classifier failed")
            latency_ms = int((time.monotonic() - t0) * 1000)

        self._write_record({
            "session_id": self.session_id,
            "delivery_id": delivery_id,
            "stage1_window_open_ts": meta.get("window_open_ts"),
            "stage1_window_close_ts": meta.get("window_close_ts"),
            "stage2_span_start_ts": span.raw_start_ts,
            "stage2_span_end_ts": span.raw_end_ts,
            "stage2_span_padded_start": span.start_ts,
            "stage2_span_padded_end": span.end_ts,
            "stage2_max_consecutive_action": span.max_consecutive_action,
            "stage2_action_ratio": span.action_ratio,
            "stage2_hard_close_count": span.hard_close_count,
            "stage3_qwen_details": qwen_details,
            "stage3_qwen_latency_ms": latency_ms,
            "stage3_qwen_error": qwen_error,
        })
        self._n_emitted += 1

    # ── helpers ─────────────────────────────────────────────────────

    def _enqueue_drop_oldest(self, q: queue.Queue, item: Any) -> None:
        try:
            q.put_nowait(item)
            return
        except queue.Full:
            pass
        try:
            q.get_nowait()
            self._n_dropped_overflow += 1
        except queue.Empty:
            pass
        try:
            q.put_nowait(item)
        except queue.Full:
            self._n_dropped_overflow += 1

    def _write_record(self, record: dict) -> None:
        if self._jsonl_fh is None:
            return
        try:
            self._jsonl_fh.write(json.dumps(record, default=str) + "\n")
            self._last_record_ts = time.time()
        except Exception:
            self._n_exceptions += 1
            self.log.exception("[SHADOW] jsonl write failed")

    def _atexit_stop(self) -> None:
        try:
            self.stop()
        except Exception:
            pass


__all__ = ["OpenScoutShadowRunner"]
