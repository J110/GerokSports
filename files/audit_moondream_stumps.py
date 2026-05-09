"""Test Moondream's `detect("stumps")` as a precision signal for
bowler's-end delivery views.

Runs `detect_pitch_in_frame` (existing pitch_grounder pipeline) on every
frame in audit_v1/frames/ and compares the result to the hand labels in
audit_v1/labels.json.

Outputs:
  - per-frame: stumps_found (bool), n_objects, validated (bool),
    box coords, ms latency
  - aggregate: precision/recall vs hand labels
  - per-truth-category: detect rate (false-positive susceptibility)

Two definitions of "Moondream says delivery view":
  1. ANY object detected (raw)             -- looser
  2. validated stump box (size/position)   -- stricter, used in pitch_grounder
"""
from __future__ import annotations
import json
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

from pitch_grounder import (
    _get_model, _bgr_to_pil, _validate_stump_box, warmup,
)

ROOT = Path(__file__).parent
AUDIT = ROOT / "audit_v1"
PROMPT = "stumps"


def detect_raw(model, bgr: np.ndarray):
    """Run model.detect and return raw objects + latency."""
    pil = _bgr_to_pil(bgr)
    t0 = time.time()
    try:
        result = model.detect(pil, PROMPT)
    except Exception as e:
        return {"error": repr(e), "ms": int((time.time() - t0) * 1000)}
    ms = int((time.time() - t0) * 1000)
    objs = result.get("objects", [])
    return {"objects": objs, "ms": ms}


def main():
    print("Loading Moondream MLX model (int4)...")
    model = _get_model()
    if model is None:
        raise SystemExit("Moondream unavailable")

    print("Warming up (2 dummy calls)...")
    warmup()

    labs = json.loads((AUDIT / "labels.json").read_text())["labels"]
    frames = sorted((AUDIT / "frames").glob("*.jpg"))
    print(f"Running detect('{PROMPT}') on {len(frames)} frames...\n")

    rows: list[dict] = []
    for fp in frames:
        bgr = cv2.imread(str(fp))
        out = detect_raw(model, bgr)
        if "error" in out:
            print(f"  {fp.stem}  ERROR  {out['error'][:60]}")
            rows.append({"frame": fp.stem, **out,
                         "truth": labs[fp.stem]["truth"]})
            continue
        objs = out["objects"]
        any_obj = len(objs) > 0
        validated = False
        primary = None
        if objs:
            o = objs[0]
            xn, yn, xx, yx = (o.get("x_min", 0), o.get("y_min", 0),
                              o.get("x_max", 0), o.get("y_max", 0))
            validated = _validate_stump_box(xn, yn, xx, yx)
            primary = {"x_min": xn, "y_min": yn,
                       "x_max": xx, "y_max": yx}
        truth = labs[fp.stem]["truth"]
        is_tp = (truth == "tp_bowlers_end_release")
        row = {
            "frame": fp.stem,
            "truth": truth,
            "n_objs": len(objs),
            "any_obj": any_obj,
            "validated": validated,
            "primary": primary,
            "ms": out["ms"],
        }
        rows.append(row)
        ok_loose = "OK" if (any_obj == is_tp) else "MISS"
        ok_strict = "OK" if (validated == is_tp) else "MISS"
        v_flag = "  V" if validated else "   "
        print(f"  {fp.stem}  obj={len(objs)}{v_flag}  "
              f"truth={truth:<26}  {out['ms']}ms  "
              f"loose={ok_loose} strict={ok_strict}")

    # Save raw results
    (AUDIT / "results_moondream.json").write_text(
        json.dumps(rows, indent=2))

    # Aggregate
    rows_ok = [r for r in rows if "error" not in r]
    n = len(rows_ok)
    n_tp = sum(1 for r in rows_ok if r["truth"] == "tp_bowlers_end_release")
    print()
    print(f"=== Moondream detect('{PROMPT}') on {n} frames ===")

    for label, key in [("ANY object detected (loose)", "any_obj"),
                       ("validated stump box (strict)", "validated")]:
        admits = sum(1 for r in rows_ok if r[key])
        admits_correct = sum(
            1 for r in rows_ok
            if r[key] and r["truth"] == "tp_bowlers_end_release")
        prec = (admits_correct / admits) if admits else 0.0
        rec = (admits_correct / n_tp) if n_tp else 0.0
        print()
        print(f"  -- {label} --")
        print(f"  admitted:    {admits}/{n}")
        print(f"  TP in admit: {admits_correct}")
        print(f"  precision:   {admits_correct}/{admits} = {prec*100:.1f}%")
        print(f"  recall:      {admits_correct}/{n_tp} = {rec*100:.1f}%")

        by_truth = defaultdict(lambda: [0, 0])
        for r in rows_ok:
            by_truth[r["truth"]][1] += 1
            if r[key]:
                by_truth[r["truth"]][0] += 1
        print(f"  admit rate per truth category:")
        for cat, (a, t) in sorted(by_truth.items(), key=lambda x: -x[1][1]):
            marker = " TP" if cat == "tp_bowlers_end_release" else "FP "
            print(f"    {marker} {cat:<26} {a}/{t} "
                  f"({a*100/t:>5.1f}% admitted)")

    msvals = [r["ms"] for r in rows_ok]
    msvals.sort()
    mean = sum(msvals) / len(msvals)
    p50 = msvals[len(msvals) // 2]
    p95 = msvals[int(len(msvals) * 0.95)]
    print()
    print(f"Latency: mean {mean:.0f}ms  p50 {p50}ms  p95 {p95}ms")


if __name__ == "__main__":
    main()
