"""Benchmark is_delivery_frame on representative captured frames.

Decides whether the filter is cheap enough to run inline in the
capture loop (sync) or needs offloading to a worker thread (async).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).parent))
from pitch_detector import is_delivery_frame  # noqa: E402


def main() -> None:
    base = Path("logs/deliveries/20260419_195420")
    frames = []
    for ddir in sorted(base.iterdir()):
        if not ddir.is_dir():
            continue
        for p in sorted(ddir.glob("scout_pick_*.jpg")):
            f = cv2.imread(str(p))
            if f is not None:
                frames.append(f)
        if len(frames) >= 60:
            break

    if not frames:
        print("No frames found")
        return

    print(f"Loaded {len(frames)} frames "
          f"({frames[0].shape[1]}x{frames[0].shape[0]})")

    # Warm-up
    for f in frames[:5]:
        is_delivery_frame(f)

    n_iter = 5
    t0 = time.time()
    for _ in range(n_iter):
        for f in frames:
            is_delivery_frame(f)
    elapsed = time.time() - t0
    total_calls = n_iter * len(frames)
    per_ms = elapsed / total_calls * 1000

    print(f"Total: {total_calls} calls in {elapsed*1000:.0f}ms")
    print(f"Per call: {per_ms:.2f}ms")
    print(f"At 30fps capture: {per_ms * 30:.1f}ms/sec "
          f"({per_ms * 30 / 10:.1f}% CPU)")
    print(f"Verdict: {'SAFE for inline capture' if per_ms < 5 else 'OFFLOAD to worker'}")


if __name__ == "__main__":
    main()
