"""Quick test: verify Moondream stump detection on saved frames.

Usage:
    .venv/bin/python3 test_moondream_pitch.py [frame_dir]

Defaults to files/logs/deliveries/ which contains delivery frames from
multiple match runs.

Uses the MLX backend directly (no REST server needed).
"""
import os
import sys
import cv2
import time

sys.path.insert(0, os.path.dirname(__file__))

from pitch_grounder import detect_pitch_in_frame, PitchBox, check_station_available


def test_frames_in_dir(base_dir: str):
    """Test all .jpg frames in the directory tree."""
    results: list[tuple[str, PitchBox | None, float]] = []

    for root, dirs, files in os.walk(base_dir):
        dirs.sort()
        for fname in sorted(files):
            if not fname.endswith(".jpg"):
                continue
            path = os.path.join(root, fname)
            frame = cv2.imread(path)
            if frame is None:
                continue

            rel = os.path.relpath(path, base_dir)
            t0 = time.time()
            box = detect_pitch_in_frame(frame)
            ms = (time.time() - t0) * 1000

            results.append((rel, box, ms))

            if box:
                h, w = frame.shape[:2]
                print(f"  [OK] {rel:55s} "
                      f"stumps=({box.stump_x_norm:.2f},{box.stump_y_norm:.2f}) "
                      f"roi=({box.x},{box.y},{box.w},{box.h}) "
                      f"{ms:.0f}ms")
            else:
                print(f"  [--] {rel:55s} "
                      f"no stumps  {ms:.0f}ms")

    print(f"\n{'='*70}")
    hits = sum(1 for _, b, _ in results if b is not None)
    total = len(results)
    avg_ms = sum(ms for _, _, ms in results) / max(total, 1)
    print(f"Results: {hits}/{total} frames had valid stump detection")
    print(f"Average latency: {avg_ms:.0f}ms per frame")

    delivery_frames = [r for r in results if "moment_" in r[0] or "wide_shot" in r[0]]
    failed_frames = [r for r in results if "failed_" in r[0]]

    if delivery_frames:
        d_hits = sum(1 for _, b, _ in delivery_frames if b is not None)
        print(f"Delivery frames (moment_*/wide_shot): {d_hits}/{len(delivery_frames)} detected")
    if failed_frames:
        f_hits = sum(1 for _, b, _ in failed_frames if b is not None)
        print(f"Failed frames: {f_hits}/{len(failed_frames)} detected")


if __name__ == "__main__":
    base = (sys.argv[1] if len(sys.argv) > 1
            else os.path.join(os.path.dirname(__file__),
                              "logs", "deliveries"))

    if not os.path.isdir(base):
        print(f"Directory not found: {base}")
        print("Usage: .venv/bin/python3 test_moondream_pitch.py [frame_dir]")
        sys.exit(1)

    print("Loading MLX Moondream model...")
    if not check_station_available():
        print("\n  Failed to load MLX Moondream model.")
        print("  Ensure moondream-station is installed and MLX dependencies are available.")
        print("  Install: pip install mlx tokenizers Pillow huggingface_hub")
        sys.exit(1)

    print("  Model loaded!")
    print(f"\nTesting stump detection on: {base}")
    print(f"{'='*70}")
    test_frames_in_dir(base)
