"""Geometric pitch-perspective detector.

Tests the user's described structural signature of a bowler's-end frame
without any VLM:

  * Brown pitch strip running vertically through the centre of the frame
  * Strip spans most of the vertical extent (top to near-bottom)
  * Strip is wider at the bottom than at the top (perspective foreshortening)

This combination is unique to bowler's-end views.  Aerial views see the
pitch horizontally; closeups see only a fragment; post_shot may see
partial pitch with humans crossing it; replays from above lack the
perspective trapezoid.

All math is done on the brown HSV mask only; total cost ~1-2 ms/frame.

Tested on the same 60-frame audit_v1 set so it's directly comparable to
the Moondream and Scout audits.
"""
from __future__ import annotations
import json
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).parent
AUDIT = ROOT / "audit_v1"

# Pitch can be brown (dry-old) or white-cream (hard-new IPL late season).
# Common signature: low-saturation AND brighter than the surrounding
# green outfield.  We also accept the brown-orange family.
# HSV in OpenCV: H in [0,179], S in [0,255], V in [0,255]


def pitch_mask(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    # Achromatic-bright (white/cream/grey pitch).
    achromatic = cv2.inRange(hsv, (0, 0, 110), (179, 70, 255))
    # Warm-tan family (dry brown pitch).
    tan = cv2.inRange(hsv, (5, 30, 80), (30, 200, 230))
    return cv2.bitwise_or(achromatic, tan)


_GREEN_LO = (35, 35, 30)
_GREEN_HI = (90, 255, 255)


def green_mask(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, _GREEN_LO, _GREEN_HI)


def measure_pitch(bgr: np.ndarray) -> dict:
    """Compute pitch-shape features for a single frame.

    Only the central 30% horizontal band and the central 70% vertical
    band are inspected, so the scoreboard chrome (bottom 18%), sponsor
    boards / browser chrome (top 12%), and side ads do NOT contaminate
    the pitch signal.

    A pitch row is defined as: in the central band, mostly pitch-coloured
    (achromatic + tan) AND flanked by green on at least one side OR
    visibly low-saturation high-value (cream pitch).
    """
    h, w = bgr.shape[:2]
    pmask = pitch_mask(bgr)
    gmask = green_mask(bgr)

    # Restrict to inside-of-broadcast region (skip top/bottom UI bands).
    y_lo, y_hi = int(h * 0.12), int(h * 0.82)
    cx_lo, cx_hi = int(w * 0.30), int(w * 0.70)

    central_pitch = pmask[y_lo:y_hi, cx_lo:cx_hi]
    central_h, central_w = central_pitch.shape
    if central_w == 0 or central_h == 0:
        return {"valid": False, "reason": "empty_central"}

    # Side bands for green-flanking check (left & right of central).
    side_w = max(1, int(w * 0.10))
    left_band = gmask[y_lo:y_hi, max(0, cx_lo - side_w):cx_lo]
    right_band = gmask[y_lo:y_hi, cx_hi:min(w, cx_hi + side_w)]
    left_green_per_row = (left_band > 0).mean(axis=1) if left_band.size else \
        np.zeros(central_h)
    right_green_per_row = (right_band > 0).mean(axis=1) if right_band.size else \
        np.zeros(central_h)
    flanked = ((left_green_per_row > 0.4) | (right_green_per_row > 0.4))

    pitch_per_row = (central_pitch > 0).mean(axis=1)

    # A row is "pitch" if it has high pitch-pixel density AND is flanked
    # by green on at least one side (excludes scoreboard, sponsor boards,
    # uniform crowd shots etc.)
    is_pitch_row = (pitch_per_row > 0.40) & flanked
    pitch_rows = np.where(is_pitch_row)[0]
    if pitch_rows.size < 5:
        return {"valid": False, "reason": "no_pitch_rows",
                "n_rows": int(pitch_rows.size)}

    y_top = (pitch_rows[0] + y_lo) / h
    y_bot = (pitch_rows[-1] + y_lo) / h
    vspan = y_bot - y_top
    n_pitch = int(pitch_rows.size)
    pitch_density = float(n_pitch / central_h)

    # Centroid drift inside central band (pitch column should be steady).
    cols = np.arange(central_w)
    sums = (central_pitch > 0).sum(axis=1)
    safe = np.where(sums > 0, sums, 1)
    centroids = ((central_pitch > 0) * cols).sum(axis=1) / safe
    centroid_norm = centroids / central_w
    centroid_drift = float(np.std(centroid_norm[pitch_rows]))

    # Pitch density on the side bands (delivery view = pitch flanked by
    # outfield, NOT pitch dominating the whole frame).
    side_pitch = float(((pmask[y_lo:y_hi, max(0, cx_lo - side_w):cx_lo] > 0).mean() +
                        (pmask[y_lo:y_hi, cx_hi:min(w, cx_hi + side_w)] > 0).mean()) / 2)

    return {
        "valid": True,
        "y_top": float(y_top),
        "y_bot": float(y_bot),
        "vspan": float(vspan),
        "n_pitch_rows": n_pitch,
        "pitch_density": pitch_density,
        "centroid_drift": centroid_drift,
        "side_pitch": side_pitch,
    }


def gate(feats: dict) -> bool:
    """Hard gate: pitch is a steady, central, green-flanked vertical strip
    that occupies most of the inner-frame vertical extent."""
    if not feats.get("valid"):
        return False
    return (
        feats["vspan"]          >= 0.30  # at least 30 % of inner frame
        and feats["y_top"]      <= 0.45  # pitch starts in the top half
        and feats["y_bot"]      >= 0.55  # pitch reaches into the bottom half
        and feats["pitch_density"] >= 0.40  # row-fraction inside inner-frame
        and feats["centroid_drift"] <= 0.12  # column doesn't snake around
        and feats["side_pitch"] <= 0.20  # outfield (not pitch) on the sides
    )


def main():
    labs = json.loads((AUDIT / "labels.json").read_text())["labels"]
    frames = sorted((AUDIT / "frames").glob("*.jpg"))

    rows = []
    total_ms = 0.0
    print(f"Running pitch-perspective gate on {len(frames)} frames...\n")
    print(f"{'frame':<5} {'truth':<26} {'vspan':>5} {'ytop':>5} "
          f"{'ybot':>5} {'pd':>5} {'side':>5} {'drift':>5} "
          f"{'gate':>5}")
    for fp in frames:
        bgr = cv2.imread(str(fp))
        t0 = time.time()
        feats = measure_pitch(bgr)
        passed = gate(feats)
        ms = (time.time() - t0) * 1000
        total_ms += ms
        truth = labs[fp.stem]["truth"]
        rows.append({"frame": fp.stem, "truth": truth, "passed": passed,
                     **feats})
        if not feats.get("valid"):
            print(f"  {fp.stem:<5} {truth:<26}  --  no pitch  "
                  f"({feats.get('reason','')})")
            continue
        print(f"  {fp.stem:<5} {truth:<26} "
              f"{feats['vspan']:>5.2f} {feats['y_top']:>5.2f} "
              f"{feats['y_bot']:>5.2f} {feats['pitch_density']:>5.2f} "
              f"{feats['side_pitch']:>5.2f} {feats['centroid_drift']:>5.2f} "
              f"{'  TP' if passed else '   .'}")

    (AUDIT / "results_pitch_perspective.json").write_text(
        json.dumps(rows, indent=2))

    n = len(rows)
    n_tp = sum(1 for r in rows if r["truth"] == "tp_bowlers_end_release")
    live_truths = {"tp_bowlers_end_release", "post_shot"}
    n_live = sum(1 for r in rows if r["truth"] in live_truths)

    admits = [r for r in rows if r["passed"]]
    tp_in = sum(1 for r in admits if r["truth"] == "tp_bowlers_end_release")
    live_in = sum(1 for r in admits if r["truth"] in live_truths)

    print(f"\n=== Pitch-perspective gate ({total_ms / n:.2f} ms/frame avg) ===")
    print(f"  admitted:                {len(admits)}/{n}")
    print(f"  precision (release):      {tp_in}/{len(admits)} = "
          f"{(tp_in*100/len(admits) if admits else 0):.1f}%")
    print(f"  recall (release):         {tp_in}/{n_tp} = "
          f"{(tp_in*100/n_tp if n_tp else 0):.1f}%")
    print(f"  precision (live-action):  {live_in}/{len(admits)} = "
          f"{(live_in*100/len(admits) if admits else 0):.1f}%")
    print(f"  recall (live-action):     {live_in}/{n_live} = "
          f"{(live_in*100/n_live if n_live else 0):.1f}%")

    by_truth = defaultdict(lambda: [0, 0])
    for r in rows:
        by_truth[r["truth"]][1] += 1
        if r["passed"]:
            by_truth[r["truth"]][0] += 1
    print(f"  admit rate per truth category:")
    for cat, (a, t) in sorted(by_truth.items(), key=lambda x: -x[1][1]):
        mk = " TP " if cat == "tp_bowlers_end_release" else (
            "live" if cat in live_truths else "FP  ")
        print(f"    {mk} {cat:<22} {a}/{t} ({a*100/t:5.1f}%)")


if __name__ == "__main__":
    main()
