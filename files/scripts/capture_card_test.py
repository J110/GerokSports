"""Standalone capture-card sanity check.

Usage:
    cd files && python scripts/capture_card_test.py
    cd files && CAPTURE_DEVICE_INDEX=2 python scripts/capture_card_test.py

What it does:
    1. Opens the capture card via CaptureCardFrameSource.
    2. Pulls 100 frames continuously (blocking on freshness, not
       re-reading the same buffered frame twice).
    3. Reports observed FPS, resolution, mean pixel intensity (a
       crude liveness check — black HDMI feeds will read ~0).
    4. Saves frames 1, 50, and 100 to ``/tmp/capture_card_test_*.png``
       for visual inspection.

Run this with the broadcast playing on the Air (HDMI mirror → UGREEN
→ M1 Max) BEFORE switching the live pipeline. Expected output on
working setup: 1920x1080 BGR, ~30 fps, mean intensity in the 60–140
range for typical HDR-mapped broadcast frames.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eyes.capture.frame_source import CaptureCardFrameSource  # noqa: E402

NUM_FRAMES = int(os.environ.get("NUM_FRAMES", "100"))
DEVICE_INDEX = int(os.environ.get("CAPTURE_DEVICE_INDEX", "0"))
SAVE_DIR = Path(os.environ.get("CAPTURE_TEST_DIR", "/tmp"))


def main() -> int:
    print(f"[capture_card_test] device_index={DEVICE_INDEX} "
          f"target_frames={NUM_FRAMES}")
    src = CaptureCardFrameSource(device_index=DEVICE_INDEX)
    try:
        src.start()
    except Exception as e:
        print(f"[capture_card_test] start failed: {e}")
        return 2

    deadline = time.time() + 5.0
    while src.get_latest_bgr() is None and time.time() < deadline:
        time.sleep(0.05)
    if src.get_latest_bgr() is None:
        print("[capture_card_test] no frames within 5s of start — "
              "is the HDMI source live and the cable seated?")
        src.stop()
        return 3

    saved: list[Path] = []
    last_count = src.get_frame_count()
    intensities: list[float] = []
    h = w = 0
    t0 = time.time()
    collected = 0

    while collected < NUM_FRAMES:
        cur = src.get_frame_count()
        if cur == last_count:
            time.sleep(0.005)
            continue
        last_count = cur
        frame = src.get_latest_bgr()
        if frame is None:
            continue
        collected += 1
        if h == 0:
            h, w = frame.shape[:2]
        intensities.append(float(frame.mean()))
        if collected in (1, NUM_FRAMES // 2, NUM_FRAMES):
            path = SAVE_DIR / f"capture_card_test_f{collected:03d}.png"
            cv2.imwrite(str(path), frame)
            saved.append(path)

    elapsed = time.time() - t0
    fps = collected / elapsed if elapsed > 0 else 0.0
    src.stop()

    print(f"[capture_card_test] frames={collected} "
          f"elapsed={elapsed:.2f}s observed_fps={fps:.1f}")
    print(f"[capture_card_test] resolution={w}x{h} channels=3 dtype=uint8")
    print(f"[capture_card_test] mean_intensity "
          f"min={min(intensities):.1f} "
          f"max={max(intensities):.1f} "
          f"avg={np.mean(intensities):.1f}")
    for p in saved:
        print(f"[capture_card_test] saved {p}")

    if max(intensities) < 5.0:
        print("[capture_card_test] WARNING: feed appears black — "
              "verify Air is mirroring and the player is foregrounded.")
        return 4
    if fps < 5.0:
        print("[capture_card_test] WARNING: observed FPS < 5 — "
              "capture card may be misconfigured or USB-starved.")
        return 5
    print("[capture_card_test] OK — capture card is usable for live pipeline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
