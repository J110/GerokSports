"""How many of the 14 cricket fields per call are 'noisy' — either
the model said unknown or it self-rated confidence below 0.70?

We do NOT consult truth here.  This is purely a measure of how often
each model declines to commit to an answer per call.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from model_bakeoff_spatial import FIELDS  # noqa: E402

CONF_FLOOR = 0.70


def load_all_bakeoff():
    rows = []
    for ridx in (1, 2, 3):
        p = ROOT / f"logs/audit_v1/bakeoff_spatial/run_{ridx}/results.json"
        for r in json.loads(p.read_text()):
            rows.append({"run": ridx, **r})
    return rows


def is_unknown(v):
    if v is None:
        return True
    s = str(v).strip().lower()
    return s in ("unknown", "none", "")


def main():
    rows = load_all_bakeoff()

    by_model = {"qwen30b-instruct": [], "gemini-3-flash": []}
    field_unknown = {m: Counter() for m in by_model}
    field_lowconf = {m: Counter() for m in by_model}
    field_calls = {m: 0 for m in by_model}

    for r in rows:
        m = r["model"]
        if m not in by_model:
            continue
        pred = r["pred"]
        conf = r.get("pred_conf") or {}
        n_unk = n_low = n_either = 0
        for f in FIELDS:
            v = pred.get(f)
            c = float(conf.get(f, 0.0))
            unk = is_unknown(v)
            low = (not unk) and (c < CONF_FLOOR)
            if unk:
                n_unk += 1
                field_unknown[m][f] += 1
            if low:
                n_low += 1
                field_lowconf[m][f] += 1
            if unk or low:
                n_either += 1
        by_model[m].append({"n_unk": n_unk, "n_low": n_low,
                            "n_either": n_either})
        field_calls[m] += 1

    print(f"Per-call distribution — how many of {len(FIELDS)} fields per "
          f"call are 'noisy' (unknown OR confidence < {CONF_FLOOR})?")
    print(f"Pooled across all 3 runs ({field_calls['qwen30b-instruct']} "
          f"calls per model).\n")

    for m, calls in by_model.items():
        n = len(calls)
        unk = [c["n_unk"] for c in calls]
        low = [c["n_low"] for c in calls]
        either = [c["n_either"] for c in calls]
        print(f"── {m} ({n} calls) ──")
        print(f"  unknown  per call: mean {sum(unk)/n:.2f}  "
              f"min {min(unk)}  max {max(unk)}")
        print(f"  conf<{CONF_FLOOR} per call: mean {sum(low)/n:.2f}  "
              f"min {min(low)}  max {max(low)}")
        print(f"  EITHER   per call: mean {sum(either)/n:.2f}  "
              f"min {min(either)}  max {max(either)}")
        # Histogram of "noisy fields per call"
        hist = Counter(either)
        print(f"  histogram of noisy-fields-per-call:")
        for k in sorted(hist):
            bar = "█" * hist[k]
            print(f"    {k:2d} fields  {hist[k]:3d} calls  {bar}")
        print()

    print("Which fields drive the noise (per-model, % of calls noisy)?\n")
    for m in by_model:
        n = field_calls[m]
        print(f"── {m} ──")
        rows_out = []
        for f in FIELDS:
            unk_pct = 100 * field_unknown[m][f] / n
            low_pct = 100 * field_lowconf[m][f] / n
            either_pct = 100 * (field_unknown[m][f]
                                + field_lowconf[m][f]) / n
            rows_out.append((either_pct, f, unk_pct, low_pct))
        rows_out.sort(reverse=True)
        print(f"  {'field':22s} {'unknown%':>10s} {'lowconf%':>10s} "
              f"{'either%':>10s}")
        for either, f, unk, low in rows_out:
            print(f"  {f:22s} {unk:9.0f}% {low:9.0f}% {either:9.0f}%")
        print()


if __name__ == "__main__":
    main()
