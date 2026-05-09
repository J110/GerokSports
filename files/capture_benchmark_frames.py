"""Capture 10 broadcast frames for vision benchmarking."""
import time
import cv2
import numpy as np
from eyes.capture.frame_source import FrameSource
from eyes.capture.downscale import downscale

FRAME_WIDTH = 1280
TARGET_FRAMES = 10
MIN_INTERVAL = 4.0  # 4s apart for more broadcast variety

def main():
    firefox_wid = None
    for w in FrameSource.list_windows():
        if "firefox" in w["owner"].lower():
            firefox_wid = w["id"]
            print(f"Found Firefox window: id={w['id']} "
                  f"{w.get('width','?')}x{w.get('height','?')} "
                  f"\"{w.get('name','')}\"")
            break

    if firefox_wid:
        frames = FrameSource(window_id=firefox_wid, fps=2)
    else:
        print("Firefox not found — using full screen")
        frames = FrameSource(fps=2)
    frames.start()
    time.sleep(1)

    saved = 0
    prev = None
    last_save = 0

    print(f"Capturing {TARGET_FRAMES} frames from Firefox...")
    while saved < TARGET_FRAMES:
        raw = frames.get_latest()
        if raw is None:
            time.sleep(0.5)
            continue

        frame = downscale(raw, FRAME_WIDTH)
        now = time.time()

        if now - last_save < MIN_INTERVAL:
            time.sleep(0.3)
            continue

        if prev is not None:
            diff = np.mean(np.abs(frame.astype(float) - prev.astype(float)))
            if diff < 255 * 0.02:
                time.sleep(0.3)
                continue

        saved += 1
        path = f"benchmark_frames/f{saved}.jpg"
        cv2.imwrite(path, frame)
        print(f"  [{saved}/{TARGET_FRAMES}] Saved {path} "
              f"({frame.shape[1]}x{frame.shape[0]})")
        prev = frame.copy()
        last_save = now

    print(f"\nDone! {TARGET_FRAMES} frames saved to benchmark_frames/")
    frames.stop()

if __name__ == "__main__":
    main()
