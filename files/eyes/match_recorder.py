"""Full-match raw recorder.

Async task that consumes from a :class:`LatestFrameSlot` and writes a
single ``match_<SESSION_ID>.mp4`` covering the whole pipeline run.

Polls the slot at ``fps`` cadence and writes the current frame on every
tick (duplicating when the producer hasn't advanced) so playback timing
matches wall-clock duration.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Optional

import cv2

from eyes.cricket_logger import CricketLogger
from eyes.latest_frame_slot import LatestFrameSlot

log = CricketLogger("MATCH-RECORDER")


async def match_recorder(
        *,
        slot: LatestFrameSlot,
        session_id: str,
        fps: float = 25.0,
        out_dir: Optional[str] = None,
        stop_event: Optional[asyncio.Event] = None,
) -> None:
    if out_dir is None:
        out_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "logs", "deliveries", session_id)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"match_{session_id}.mp4")

    writer: Optional[cv2.VideoWriter] = None
    interval = 1.0 / max(1.0, float(fps))
    frames_written = 0
    started_monotonic: Optional[float] = None

    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                break
            tick_t0 = time.monotonic()

            latest = await slot.get_latest()
            if latest is None:
                await asyncio.sleep(interval)
                continue
            frame, _ts, _set_t = latest

            if writer is None:
                h, w = frame.shape[:2]
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                writer = cv2.VideoWriter(path, fourcc, float(fps), (w, h))
                if not writer.isOpened():
                    log.warn(
                        f"[MATCH-RECORDER] failed to open writer at {path}")
                    return
                started_monotonic = time.monotonic()
                log.info(
                    f"[MATCH-RECORDER-START path={path} fps={float(fps):.2f}]")

            try:
                writer.write(frame)
                frames_written += 1
            except Exception as exc:  # noqa: BLE001
                log.warn(f"[MATCH-RECORDER] write failed: {exc!r}")

            elapsed = time.monotonic() - tick_t0
            if elapsed < interval:
                await asyncio.sleep(interval - elapsed)
    except asyncio.CancelledError:
        raise
    finally:
        duration_s = (time.monotonic() - started_monotonic
                      if started_monotonic is not None else 0.0)
        if writer is not None:
            try:
                writer.release()
            except Exception:  # noqa: BLE001
                pass
        log.info(
            f"[MATCH-RECORDER-STOP frames={frames_written} "
            f"duration_s={duration_s:.2f}]")


__all__ = ["match_recorder"]
