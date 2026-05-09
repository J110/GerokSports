"""Debug pitch detector on a specific frame."""
import sys
import cv2
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent
fp = ROOT / "audit_v1" / "frames" / sys.argv[1]
bgr = cv2.imread(str(fp))
h, w = bgr.shape[:2]
print(f"Frame: {fp.name}  shape={bgr.shape}")

hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

# Sample pitch pixels (centre column, y=0.45)
samples = []
for sy in [0.30, 0.40, 0.50, 0.60, 0.65]:
    for sx in [0.45, 0.50, 0.55]:
        px = hsv[int(h * sy), int(w * sx)]
        samples.append((sy, sx, list(px)))
        bgr_px = bgr[int(h * sy), int(w * sx)]
        print(f"  pitch sample y={sy:.2f} x={sx:.2f}  "
              f"BGR={list(bgr_px)}  HSV={list(px)}")

print("\n  outfield samples:")
for sy in [0.40, 0.50, 0.60]:
    for sx in [0.10, 0.20, 0.85, 0.95]:
        px = hsv[int(h * sy), int(w * sx)]
        bgr_px = bgr[int(h * sy), int(w * sx)]
        print(f"  outfield y={sy:.2f} x={sx:.2f}  "
              f"BGR={list(bgr_px)}  HSV={list(px)}")

# Apply current masks
ach = cv2.inRange(hsv, (0, 0, 110), (179, 70, 255))
tan = cv2.inRange(hsv, (5, 30, 80), (30, 200, 230))
pmask = cv2.bitwise_or(ach, tan)
gmask = cv2.inRange(hsv, (35, 35, 30), (90, 255, 255))

cx_lo, cx_hi = int(w * 0.30), int(w * 0.70)
y_lo, y_hi = int(h * 0.12), int(h * 0.82)

central_p = pmask[y_lo:y_hi, cx_lo:cx_hi]
central_g = gmask[y_lo:y_hi, cx_lo:cx_hi]

print(f"\n  central band [y={y_lo}:{y_hi}, x={cx_lo}:{cx_hi}]")
print(f"  central pitch mean: {(central_p > 0).mean():.3f}")
print(f"  central green mean: {(central_g > 0).mean():.3f}")

# Per-row density inside central
prow = (central_p > 0).mean(axis=1)
grow = (central_g > 0).mean(axis=1)
print(f"\n  per-row pitch density in central band (every 10th row of {len(prow)}):")
for i in range(0, len(prow), max(1, len(prow) // 20)):
    y_norm = (i + y_lo) / h
    print(f"    row idx {i}  y={y_norm:.2f}  pitch={prow[i]:.2f}  green={grow[i]:.2f}")
