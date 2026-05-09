"""AutoDeliveryRecorder — clip writer for ContinuousChunker events.

Subscribes to :class:`DeliveryDetectedEvent` emissions from
:class:`ContinuousChunker` and writes ``delivery.mp4`` + ``metadata.json``
under ``files/logs/deliveries/<session>/auto/d<NNN>/``.

Independent of the score-event-driven recorder under ``d<NNN>/`` — does
NOT touch :class:`ScoreManager`, the WebSocket state, or the SM card.
``auto_NNN`` numbering is sequential per recorder instance.

Frame source: ``ball_analyzer._frame_buffer_raw`` via the public
``_frame_source(start_ts, end_ts)`` slice helper.  Inherits the v3
crop fix (uses raw broadcast frame, not the downscaled vision input).
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Callable, Optional

import cv2
import numpy as np

from eyes.continuous_chunker import DeliveryDetectedEvent
from eyes.cricket_logger import CricketLogger

log = CricketLogger("AUTO-DELIVERY")


FrameSliceFn = Callable[[float, float], list[tuple[float, np.ndarray]]]


class AutoDeliveryRecorder:
    """Writes delivery clips to ``auto/d<NNN>/`` per detected event."""

    def __init__(
            self,
            *,
            session_id: str,
            frame_slice_fn: FrameSliceFn,
            out_root: Optional[str] = None,
            fps: float = 25.0,
            fourcc_str: str = "mp4v",
    ) -> None:
        self._session_id = session_id
        self._frame_slice_fn = frame_slice_fn
        self._fps = float(fps)
        self._fourcc_str = fourcc_str
        if out_root is None:
            out_root = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "logs", "deliveries", session_id, "auto")
        self._out_root = out_root
        os.makedirs(self._out_root, exist_ok=True)
        self._counter = 0
        self._lock = threading.Lock()
        self._stats = {
            "events_received": 0,
            "clips_written": 0,
            "clips_skipped_no_frames": 0,
            "clips_failed": 0,
        }

    def stats(self) -> dict:
        with self._lock:
            return dict(self._stats)

    def __call__(self, event: DeliveryDetectedEvent) -> None:
        self.handle_event(event)

    def handle_event(self, event: DeliveryDetectedEvent) -> None:
        with self._lock:
            self._stats["events_received"] += 1
            self._counter += 1
            auto_id = f"d{self._counter:03d}"

        try:
            self._write_clip(auto_id, event)
        except Exception as e:  # noqa: BLE001
            with self._lock:
                self._stats["clips_failed"] += 1
            log.warn(
                f"[AUTO-CLIP-WRITE-FAIL] auto_id={auto_id} "
                f"err={e!r}")

    def _write_clip(self, auto_id: str,
                    event: DeliveryDetectedEvent) -> None:
        out_dir = os.path.join(self._out_root, auto_id)
        os.makedirs(out_dir, exist_ok=True)
        mp4_path = os.path.join(out_dir, "delivery.mp4")
        meta_path = os.path.join(out_dir, "metadata.json")

        frames = self._frame_slice_fn(event.start_ts, event.end_ts)
        if not frames:
            with self._lock:
                self._stats["clips_skipped_no_frames"] += 1
            log.warn(
                f"[AUTO-CLIP-WRITE-FAIL] auto_id={auto_id} "
                f"reason=no_frames start={event.start_ts:.3f} "
                f"end={event.end_ts:.3f}")
            metadata = self._build_metadata(auto_id, event,
                                            frame_count=0,
                                            mp4_written=False)
            _write_json(meta_path, metadata)
            return

        frames_sorted = sorted(frames, key=lambda x: x[0])
        h, w = frames_sorted[0][1].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*self._fourcc_str)
        writer = cv2.VideoWriter(mp4_path, fourcc, self._fps, (w, h))
        if not writer.isOpened():
            with self._lock:
                self._stats["clips_failed"] += 1
            log.warn(
                f"[AUTO-CLIP-WRITE-FAIL] auto_id={auto_id} "
                f"reason=writer_open_failed path={mp4_path}")
            return

        frames_written = 0
        try:
            for _ts, fr in frames_sorted:
                writer.write(fr)
                frames_written += 1
        finally:
            writer.release()

        try:
            size_bytes = os.path.getsize(mp4_path)
        except OSError:
            size_bytes = 0
        if size_bytes < 1024:
            with self._lock:
                self._stats["clips_failed"] += 1
            log.warn(
                f"[AUTO-CLIP-WRITE-FAIL] auto_id={auto_id} "
                f"reason=undersized bytes={size_bytes}")
            return

        with self._lock:
            self._stats["clips_written"] += 1

        metadata = self._build_metadata(auto_id, event,
                                        frame_count=frames_written,
                                        mp4_written=True,
                                        bytes_written=size_bytes)
        _write_json(meta_path, metadata)
        log.info(
            f"[AUTO-CLIP-WRITE-OK] auto_id={auto_id} "
            f"start={event.start_ts:.3f} end={event.end_ts:.3f} "
            f"dur={event.duration_s:.2f}s frames={frames_written} "
            f"bytes={size_bytes}")

    def _build_metadata(
            self,
            auto_id: str,
            event: DeliveryDetectedEvent,
            *,
            frame_count: int,
            mp4_written: bool,
            bytes_written: int = 0,
    ) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "auto_id": auto_id,
            "session": self._session_id,
            "start_ts": round(event.start_ts, 3),
            "end_ts": round(event.end_ts, 3),
            "duration_s": round(event.duration_s, 3),
            "anchor_frames": event.anchor_frames,
            "confidence_score": round(event.confidence_score, 3),
            "labels": list(event.labels),
            "frame_count": frame_count,
            "mp4_written": mp4_written,
            "bytes_written": bytes_written,
            "written_at_wall": round(time.time(), 3),
        }
        return meta


def _write_json(path: str, payload: dict) -> None:
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2, default=str)


__all__ = ["AutoDeliveryRecorder"]
