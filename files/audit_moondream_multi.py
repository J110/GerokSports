"""Test Moondream's structural understanding of bowler's-end delivery
frames using multiple complementary signals.

Hypothesis under test: a delivery frame has a unique structural
signature — bowler in foreground (lower half), batter+umpire stacked at
the far end on the pitch centerline, pitch visible end-to-end. Stumps
alone are not enough because they're visible across the entire 10s
bowler's-end camera hold.

Signals tested (per frame):
  (A) detect("bowler")                        -> any bowler box?
  (B) detect("batsman")                       -> any batter box?
  (C) query("Is a cricket bowler currently in his run-up or delivery
            stride?  Answer only yes or no.")
  (D) STRUCTURAL composite:
        bowler box AND batter box AND
        bowler.cy > 0.45 (lower half) AND
        batter.cy < 0.55 (upper half) AND
        |bowler.cx - batter.cx| < 0.30 (roughly same vertical strip)
  (E) STRICT composite: D AND C-says-yes

All signals tested on the same 60-frame audit set (audit_v1/), labels
in audit_v1/labels.json.
"""
from __future__ import annotations
import json
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

from pitch_grounder import _get_model, _bgr_to_pil, warmup

ROOT = Path(__file__).parent
AUDIT = ROOT / "audit_v1"

QUERY_TEXT = (
    "Is a cricket bowler currently in his run-up or in his bowling "
    "delivery stride in this image?  Answer only yes or no."
)


def _box_geom(o):
    cx = (o["x_min"] + o["x_max"]) / 2
    cy = (o["y_min"] + o["y_max"]) / 2
    return cx, cy, o["x_max"] - o["x_min"], o["y_max"] - o["y_min"]


def _largest(objs):
    if not objs:
        return None
    return max(objs, key=lambda o: (o["x_max"] - o["x_min"]) * (o["y_max"] - o["y_min"]))


def run_frame(model, bgr):
    pil = _bgr_to_pil(bgr)
    out = {"ms": {}}

    t0 = time.time()
    try:
        bowler = model.detect(pil, "bowler")
    except Exception as e:
        bowler = {"error": str(e), "objects": []}
    out["ms"]["bowler"] = int((time.time() - t0) * 1000)
    out["bowler_objs"] = bowler.get("objects", [])

    t0 = time.time()
    try:
        batter = model.detect(pil, "batsman")
    except Exception as e:
        batter = {"error": str(e), "objects": []}
    out["ms"]["batter"] = int((time.time() - t0) * 1000)
    out["batter_objs"] = batter.get("objects", [])

    t0 = time.time()
    try:
        ans = model.query(pil, QUERY_TEXT)
        out["query_answer"] = (ans.get("answer") or "").strip().lower()
    except Exception as e:
        out["query_answer"] = f"error:{e}"
    out["ms"]["query"] = int((time.time() - t0) * 1000)

    return out


def composites(r):
    bowler = _largest(r["bowler_objs"])
    batter = _largest(r["batter_objs"])
    sigA = bool(bowler)
    sigB = bool(batter)

    ans = r.get("query_answer", "")
    sigC = ans.startswith("yes")

    sigD = False
    if bowler and batter:
        bcx, bcy, _, _ = _box_geom(bowler)
        tcx, tcy, _, _ = _box_geom(batter)
        sigD = (bcy > 0.45) and (tcy < 0.55) and (abs(bcx - tcx) < 0.30)

    sigE = sigD and sigC
    return {"A": sigA, "B": sigB, "C": sigC, "D": sigD, "E": sigE}


def main():
    print("Loading Moondream MLX model (int4)...")
    model = _get_model()
    if model is None:
        raise SystemExit("Moondream unavailable")
    print("Warming up...")
    warmup()

    labs = json.loads((AUDIT / "labels.json").read_text())["labels"]
    frames = sorted((AUDIT / "frames").glob("*.jpg"))
    print(f"Running multi-signal on {len(frames)} frames "
          f"(3 calls each, ~7 s/frame)...\n")

    rows = []
    for fp in frames:
        bgr = cv2.imread(str(fp))
        r = run_frame(model, bgr)
        sigs = composites(r)
        truth = labs[fp.stem]["truth"]
        rows.append({"frame": fp.stem, "truth": truth, **r, **sigs})
        flag = "TP" if truth == "tp_bowlers_end_release" else "  "
        print(f"  {fp.stem} {flag} {truth:<26} "
              f"A={int(sigs['A'])} B={int(sigs['B'])} "
              f"C={int(sigs['C'])} D={int(sigs['D'])} E={int(sigs['E'])} "
              f"q='{r.get('query_answer','')[:20]}' "
              f"({sum(r['ms'].values())}ms)")

    (AUDIT / "results_moondream_multi.json").write_text(
        json.dumps(rows, indent=2, default=str))

    n = len(rows)
    n_tp = sum(1 for r in rows if r["truth"] == "tp_bowlers_end_release")
    # also report on a broader "live action" target = release + post_shot
    # (active play with ball in flight or just hit, before chase)
    live_truths = {"tp_bowlers_end_release", "post_shot"}
    n_live = sum(1 for r in rows if r["truth"] in live_truths)

    sig_descriptions = {
        "A": "bowler-detected",
        "B": "batter-detected",
        "C": "query says 'yes' (run-up/delivery)",
        "D": "STRUCT: bowler-low AND batter-high AND aligned",
        "E": "STRICT: D AND C",
    }

    for sig, desc in sig_descriptions.items():
        admits = [r for r in rows if r[sig]]
        tp_in_admit = sum(
            1 for r in admits if r["truth"] == "tp_bowlers_end_release")
        live_in_admit = sum(1 for r in admits if r["truth"] in live_truths)
        print(f"\n  -- Signal {sig}: {desc} --")
        print(f"  admitted:        {len(admits)}/{n}")
        print(f"  precision (release-only): "
              f"{tp_in_admit}/{len(admits)} = "
              f"{(tp_in_admit*100/len(admits) if admits else 0):.1f}%")
        print(f"  recall (release-only):    "
              f"{tp_in_admit}/{n_tp} = "
              f"{(tp_in_admit*100/n_tp if n_tp else 0):.1f}%")
        print(f"  precision (live-action incl post_shot): "
              f"{live_in_admit}/{len(admits)} = "
              f"{(live_in_admit*100/len(admits) if admits else 0):.1f}%")
        print(f"  recall (live-action incl post_shot):    "
              f"{live_in_admit}/{n_live} = "
              f"{(live_in_admit*100/n_live if n_live else 0):.1f}%")

        by_truth = defaultdict(lambda: [0, 0])
        for r in rows:
            by_truth[r["truth"]][1] += 1
            if r[sig]:
                by_truth[r["truth"]][0] += 1
        print(f"  admit rate per truth category:")
        for cat, (a, t) in sorted(by_truth.items(), key=lambda x: -x[1][1]):
            mk = " TP " if cat == "tp_bowlers_end_release" else (
                "live" if cat in live_truths else "FP  ")
            print(f"    {mk} {cat:<22} {a}/{t} ({a*100/t:5.1f}%)")


if __name__ == "__main__":
    main()
