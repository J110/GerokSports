"""Compare auto-predicted delivery labels against manual ground-truth.

Reads:
  - logs/deliveries/raw_features.jsonl  (auto predictions)
  - logs/deliveries/ground_truth_labels.jsonl (manual labels)

Reports per-field accuracy and lists all mismatches.

Superseded by `delivery_tools.py compare` which has richer output.
Use this for quick standalone comparison.
"""
from __future__ import annotations
import json
from pathlib import Path
from collections import defaultdict

DELIVERIES_DIR = Path(__file__).parent / "logs" / "deliveries"
GT_PATH = DELIVERIES_DIR / "ground_truth_labels.jsonl"
RAW_PATH = DELIVERIES_DIR / "raw_features.jsonl"

COMPARE_FIELDS = [
    "bowling_angle", "length", "line", "bounce",
    "shot_elevation", "shot_direction_side",
]


def load_ground_truth() -> list[dict]:
    rows = []
    if not GT_PATH.exists():
        return rows
    with open(GT_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_auto_predictions() -> dict[int, dict]:
    preds = {}
    if not RAW_PATH.exists():
        return preds
    with open(RAW_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("predicted"):
                preds[row["delivery_num"]] = row
    return preds


def compare():
    gt_rows = load_ground_truth()
    preds = load_auto_predictions()

    genuine = [r for r in gt_rows if r.get("frame_quality") == "genuine"]
    contaminated = [r for r in gt_rows if r.get("frame_quality") != "genuine"]

    print("=" * 70)
    print("DELIVERY FRAME QUALITY AUDIT")
    print("=" * 70)
    print(f"Total labeled:    {len(gt_rows)}")
    print(f"Genuine delivery: {len(genuine)}")
    print(f"Contaminated:     {len(contaminated)}")
    if gt_rows:
        print(f"Frame quality:    {len(genuine)/len(gt_rows)*100:.0f}% genuine")
    print()

    contam_types = defaultdict(int)
    for r in contaminated:
        contam_types[r.get("frame_quality", "unknown")] += 1
    if contam_types:
        print("Non-genuine breakdown:")
        for ctype, count in sorted(contam_types.items(),
                                   key=lambda x: -x[1]):
            print(f"  {ctype}: {count}")
        print()

    print("=" * 70)
    print("AUTO-PREDICTION vs GROUND-TRUTH (genuine frames only)")
    print("=" * 70)

    field_stats: dict[str, dict] = {
        f: {"correct": 0, "wrong": 0, "skipped": 0, "mismatches": []}
        for f in COMPARE_FIELDS
    }

    for gt in genuine:
        dnum = gt["delivery_num"]
        auto = preds.get(dnum)

        if not auto or not auto.get("predicted"):
            for f in COMPARE_FIELDS:
                field_stats[f]["skipped"] += 1
            continue

        pred = auto["predicted"]
        for f in COMPARE_FIELDS:
            gt_val = gt.get(f)
            auto_val = pred.get(f)

            if gt_val is None or gt_val == "unknown":
                field_stats[f]["skipped"] += 1
                continue

            if auto_val == gt_val:
                field_stats[f]["correct"] += 1
            else:
                field_stats[f]["wrong"] += 1
                field_stats[f]["mismatches"].append({
                    "delivery": dnum,
                    "auto": auto_val,
                    "truth": gt_val,
                })

    print()
    for f in COMPARE_FIELDS:
        s = field_stats[f]
        total = s["correct"] + s["wrong"]
        if total == 0:
            print(f"  {f:25s}  no comparable data")
            continue
        acc = s["correct"] / total * 100
        print(f"  {f:25s}  {acc:5.1f}% ({s['correct']}/{total})")
        for m in s["mismatches"]:
            print(f"    D#{m['delivery']:2d}: "
                  f"auto={m['auto']} vs truth={m['truth']}")

    print()
    print("For detailed output with raw values, use:")
    print("  python delivery_tools.py compare")


if __name__ == "__main__":
    compare()
