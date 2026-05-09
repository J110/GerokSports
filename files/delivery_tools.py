"""Delivery classifier toolbox — test, save, label, compare, tune.

Usage:
    python delivery_tools.py test-detection [--dir DIR]
        Run is_delivery_frame on saved frames, show pass/fail + diagnostics.
        Use after a match to verify frame detection is working.

    python delivery_tools.py save-frames [--source DIR] [--dest DIR]
        Organize delivery frames from a completed run into a labeled dataset.
        Archives the current run and prepares for labeling.

    python delivery_tools.py label [--dir DIR]
        Interactive labeling: prints frame info for each delivery,
        outputs a ground_truth_labels.jsonl entry to copy/edit.

    python delivery_tools.py compare [--dir DIR]
        Compare auto-predictions against ground truth labels.
        Reports per-field accuracy and lists all mismatches.

    python delivery_tools.py accuracy-report [--dir DIR]
        Full accuracy report: detection rate + classification accuracy.

All paths default to files/logs/deliveries/.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

DELIVERIES_DIR = Path(__file__).parent / "logs" / "deliveries"

LABEL_FIELDS = {
    "bowling_angle": ["over", "round"],
    "length": [
        "bouncer", "short", "back_of_length", "good_length",
        "full", "overpitched", "yorker", "full_toss",
    ],
    "line": [
        "wide_outside_off", "outside_off", "off_stump", "on_stumps",
        "leg_stump", "on_pads", "down_leg",
    ],
    "bounce": [
        "bouncer", "sharp_bounce", "good_bounce", "normal",
        "stayed_low", "skidded_through",
    ],
    "shot_elevation": ["along_ground", "in_the_air", "no_shot"],
    "shot_direction_side": [
        "offside", "legside", "straight", "no_shot",
    ],
}

COMPARE_FIELDS = list(LABEL_FIELDS.keys())


# ── Test Detection ────────────────────────────────────────────────────

def cmd_test_detection(args):
    """Run is_delivery_frame on all saved frames and report results."""
    sys.path.insert(0, str(Path(__file__).parent))
    from pitch_detector import (
        is_delivery_frame, _find_pitch_center, _has_figures_at_both_ends,
        is_delivery_view_fast,
    )
    import cv2
    import numpy as np

    base = Path(args.dir)
    if not base.exists():
        print(f"Directory not found: {base}")
        return

    gt = _load_ground_truth(base)

    print("=" * 80)
    print("DELIVERY FRAME DETECTION TEST")
    print("=" * 80)
    print(f"Directory: {base}")
    print()

    results = {"pass": 0, "fail_pitch": 0, "fail_figure": 0}
    delivery_dirs = sorted(
        [d for d in base.iterdir()
         if d.is_dir() and d.name.startswith("delivery_")],
        key=lambda d: d.name,
    )

    for ddir in delivery_dirs:
        dnum = int(ddir.name.split("_")[1])
        quality = gt.get(dnum, {}).get("frame_quality", "?")
        frames_tested = []

        for fname in sorted(ddir.iterdir()):
            if fname.suffix != ".jpg" or fname.stem == "pitch_annotated":
                continue
            frame = cv2.imread(str(fname))
            if frame is None:
                continue

            h, w = frame.shape[:2]
            pitch_cx = _find_pitch_center(frame)
            dv_fast = is_delivery_view_fast(frame)
            full_check = is_delivery_frame(frame)

            diag = ""
            if pitch_cx is not None and not full_check:
                diag = " (pitch ok, figure pattern failed)"

            status = "PASS" if full_check else "FAIL"
            frames_tested.append((fname.name, w, h, pitch_cx, dv_fast,
                                  full_check, diag))

            if full_check:
                results["pass"] += 1
            elif pitch_cx is None:
                results["fail_pitch"] += 1
            else:
                results["fail_figure"] += 1

        if frames_tested:
            print(f"D#{dnum:2d} [{quality:12s}]")
            for name, w, h, pcx, dvf, fc, diag in frames_tested:
                pcx_s = str(pcx) if pcx is not None else "-"
                print(f"  {name:25s} {w}x{h}  pitch={pcx_s:>5s}  "
                      f"dv_fast={'Y' if dvf else 'N'}  "
                      f"full={'PASS' if fc else 'FAIL'}{diag}")

    print()
    print(f"Summary: {results['pass']} PASS, "
          f"{results['fail_pitch']} fail(no pitch), "
          f"{results['fail_figure']} fail(figure pattern)")
    print()
    print("NOTE: Saved frames have different resolutions than capture-loop")
    print("frames due to letterbox stripping and JPEG compression.")
    print("The definitive test is during a live match.")


# ── Save Frames ──────────────────────────────────────────────────────

def cmd_save_frames(args):
    """Archive current run and prepare for labeling."""
    base = Path(args.dir)
    source = base

    delivery_dirs = sorted(
        [d for d in source.iterdir()
         if d.is_dir() and d.name.startswith("delivery_")],
        key=lambda d: d.name,
    )

    if not delivery_dirs:
        print("No delivery_NNN directories found.")
        return

    raw_features = source / "raw_features.jsonl"

    archive_name = args.archive or _next_archive_name(base)
    archive_dir = base / archive_name
    archive_dir.mkdir(exist_ok=True)

    import shutil
    moved = 0
    for ddir in delivery_dirs:
        dest = archive_dir / ddir.name
        shutil.move(str(ddir), str(dest))
        moved += 1

    if raw_features.exists():
        shutil.move(str(raw_features), str(archive_dir / "raw_features.jsonl"))

    print(f"Archived {moved} deliveries + raw_features.jsonl → {archive_dir}")
    print(f"Next step: python delivery_tools.py label --dir {archive_dir}")


def _next_archive_name(base: Path) -> str:
    existing = [d.name for d in base.iterdir()
                if d.is_dir() and d.name.startswith("archive_run")]
    nums = []
    for name in existing:
        parts = name.replace("archive_run", "").split("_")
        try:
            nums.append(int(parts[0]))
        except (ValueError, IndexError):
            pass
    next_num = max(nums, default=0) + 1
    return f"archive_run{next_num}"


# ── Label ────────────────────────────────────────────────────────────

def cmd_label(args):
    """Print frame info for each delivery to help manual labeling."""
    base = Path(args.dir)

    raw_path = base / "raw_features.jsonl"
    preds = {}
    if raw_path.exists():
        with open(raw_path) as f:
            for line in f:
                row = json.loads(line.strip())
                preds[row["delivery_num"]] = row

    gt_path = base / "ground_truth_labels.jsonl"
    existing_gt = {}
    if gt_path.exists():
        with open(gt_path) as f:
            for line in f:
                row = json.loads(line.strip())
                existing_gt[row["delivery_num"]] = row

    delivery_dirs = sorted(
        [d for d in base.iterdir()
         if d.is_dir() and d.name.startswith("delivery_")],
        key=lambda d: d.name,
    )

    print("=" * 80)
    print("DELIVERY LABELING GUIDE")
    print("=" * 80)
    print(f"Directory: {base}")
    print(f"Deliveries found: {len(delivery_dirs)}")
    print(f"Raw features: {'yes' if preds else 'no'}")
    print(f"Existing labels: {len(existing_gt)}")
    print()
    print("For each delivery, open the frame images in the delivery folder.")
    print("Look at: wide_shot.jpg (or moment_key.jpg) for the delivery view,")
    print("         pitch_annotated.jpg for ball trajectory visualization.")
    print()
    print("Label taxonomy:")
    for field, values in LABEL_FIELDS.items():
        print(f"  {field}: {', '.join(values)}")
    print()

    entries = []
    for ddir in delivery_dirs:
        dnum = int(ddir.name.split("_")[1])
        frames = [f.name for f in sorted(ddir.iterdir())
                  if f.suffix == ".jpg"]
        pred = preds.get(dnum, {})
        auto = pred.get("predicted", {})
        runs = pred.get("runs", "?")
        dets = pred.get("num_detections", 0)
        flight = pred.get("num_flight", 0)

        has_label = dnum in existing_gt

        print(f"─── D#{dnum} {'[LABELED]' if has_label else '[UNLABELED]'} "
              f"───")
        print(f"  Frames: {', '.join(frames)}")
        print(f"  Runs: {runs}  Detections: {dets}  Flight: {flight}")
        if auto:
            print(f"  Auto: {auto.get('bowling_angle','?')}/"
                  f"{auto.get('length','?')}/"
                  f"{auto.get('line','?')}/"
                  f"{auto.get('bounce','?')} "
                  f"shot={auto.get('shot_elevation','?')}/"
                  f"{auto.get('shot_direction_side','?')}")

        if not has_label:
            # Generate template
            entry = {
                "delivery_num": dnum,
                "frame_quality": "genuine",
                "bowling_angle": auto.get("bowling_angle", "unknown"),
                "length": auto.get("length", "unknown"),
                "line": auto.get("line", "unknown"),
                "bounce": auto.get("bounce", "unknown"),
                "shot_elevation": auto.get("shot_elevation", "unknown"),
                "shot_direction_side": auto.get(
                    "shot_direction_side", "unknown"),
                "runs": runs,
                "notes": "",
            }
            print(f"  Template (verify against frames, edit, append to "
                  f"ground_truth_labels.jsonl):")
            print(f"  {json.dumps(entry)}")
        print()


# ── Compare ──────────────────────────────────────────────────────────

def cmd_compare(args):
    """Compare auto-predictions against ground truth labels."""
    base = Path(args.dir)

    gt_path = base / "ground_truth_labels.jsonl"
    raw_path = base / "raw_features.jsonl"

    if not gt_path.exists():
        # Try the default location
        gt_path = DELIVERIES_DIR / "ground_truth_labels.jsonl"
    if not gt_path.exists():
        print(f"No ground_truth_labels.jsonl found in {base} or {DELIVERIES_DIR}")
        return

    gt_rows = []
    with open(gt_path) as f:
        for line in f:
            line = line.strip()
            if line:
                gt_rows.append(json.loads(line))

    preds = {}
    if raw_path.exists():
        with open(raw_path) as f:
            for line in f:
                row = json.loads(line.strip())
                if row.get("predicted"):
                    preds[row["delivery_num"]] = row

    # Also check archive subdirs for raw_features
    if not preds:
        for subdir in base.iterdir():
            rf = subdir / "raw_features.jsonl" if subdir.is_dir() else None
            if rf and rf.exists():
                with open(rf) as f:
                    for line in f:
                        row = json.loads(line.strip())
                        if row.get("predicted"):
                            preds[row["delivery_num"]] = row

    genuine = [r for r in gt_rows
               if r.get("frame_quality") == "genuine"]
    contaminated = [r for r in gt_rows
                    if r.get("frame_quality") != "genuine"]

    print("=" * 80)
    print("DELIVERY CLASSIFIER ACCURACY REPORT")
    print("=" * 80)
    print(f"Ground truth: {len(gt_rows)} labeled "
          f"({len(genuine)} genuine, {len(contaminated)} other)")
    print(f"Auto predictions: {len(preds)} deliveries")
    print()

    if not genuine:
        print("No genuine delivery frames labeled. Label some first:")
        print(f"  python delivery_tools.py label --dir {base}")
        return

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
                    "raw": {
                        "offset_frac": auto.get("offset_frac"),
                        "len_frac": auto.get("len_frac"),
                        "speed_kph": auto.get("speed_kph"),
                    },
                })

    print("Per-field accuracy (genuine frames only):")
    print()
    all_correct = True
    for f in COMPARE_FIELDS:
        s = field_stats[f]
        total = s["correct"] + s["wrong"]
        if total == 0:
            print(f"  {f:25s}  — (no data)")
            continue
        acc = s["correct"] / total * 100
        mark = "✓" if acc == 100 else "✗"
        if acc < 100:
            all_correct = False
        print(f"  {f:25s}  {acc:5.1f}% ({s['correct']}/{total}) {mark}")
        for m in s["mismatches"]:
            print(f"    D#{m['delivery']:2d}: auto={m['auto']:20s} "
                  f"truth={m['truth']:20s}  "
                  f"raw={json.dumps(m['raw'])}")

    print()
    if all_correct:
        print("ALL FIELDS 100% ACCURATE — classifier is ready.")
    else:
        print("MISMATCHES FOUND — tune ball_classifier.py thresholds.")
        print()
        print("Tuning guide:")
        print("  1. Look at the raw values (offset_frac, len_frac, speed_kph)")
        print("  2. Compare against the threshold boundaries in ball_classifier.py")
        print("  3. Adjust thresholds so the raw value falls in the correct bucket")
        print("  4. Re-run: python delivery_tools.py compare --dir DIR")


# ── Accuracy Report ──────────────────────────────────────────────────

def cmd_accuracy_report(args):
    """Full accuracy report: detection rate + classification accuracy."""
    base = Path(args.dir)

    raw_path = base / "raw_features.jsonl"
    if not raw_path.exists():
        print(f"No raw_features.jsonl in {base}")
        return

    rows = []
    with open(raw_path) as f:
        for line in f:
            rows.append(json.loads(line.strip()))

    total = len(rows)
    detected = [r for r in rows if r.get("num_detections", 0) >= 2]
    failed = [r for r in rows if r.get("num_detections", 0) < 2]

    print("=" * 80)
    print("DELIVERY DETECTION ACCURACY")
    print("=" * 80)
    print(f"Total deliveries analyzed: {total}")
    print(f"Detected (≥2 detections):  {len(detected)} "
          f"({len(detected)/max(total,1)*100:.0f}%)")
    print(f"Failed (<2 detections):    {len(failed)} "
          f"({len(failed)/max(total,1)*100:.0f}%)")
    print()

    if failed:
        print("Failed deliveries:")
        for r in failed:
            bs = r.get("buffer_stats", {})
            print(f"  D#{r['delivery_num']:2d}: runs={r.get('runs','?')}  "
                  f"dets={r.get('num_detections',0)}  "
                  f"dv={bs.get('dv_frame_count','?')}  "
                  f"wide={bs.get('temporal_slice_count','?')}")
        print()

    if detected:
        print("Detection quality:")
        det_counts = [r["num_detections"] for r in detected]
        flight_counts = [r.get("num_flight", 0) for r in detected]
        print(f"  Detections: min={min(det_counts)} max={max(det_counts)} "
              f"avg={sum(det_counts)/len(det_counts):.1f}")
        print(f"  Flight pts: min={min(flight_counts)} "
              f"max={max(flight_counts)} "
              f"avg={sum(flight_counts)/len(flight_counts):.1f}")

    # Check for trajectory rejections
    traj_rejected = [r for r in rows if r.get("status", "").startswith(
        "trajectory_")]
    if traj_rejected:
        print()
        print(f"Trajectory rejections: {len(traj_rejected)}")
        for r in traj_rejected:
            print(f"  D#{r['delivery_num']:2d}: {r['status']}")

    print()
    print(f"Next step: python delivery_tools.py label --dir {base}")


# ── Helpers ──────────────────────────────────────────────────────────

def _load_ground_truth(base: Path) -> dict[int, dict]:
    gt = {}
    for path in [base / "ground_truth_labels.jsonl",
                 DELIVERIES_DIR / "ground_truth_labels.jsonl"]:
        if path.exists():
            with open(path) as f:
                for line in f:
                    row = json.loads(line.strip())
                    gt[row["delivery_num"]] = row
            break
    return gt


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Delivery classifier toolbox",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("test-detection",
                        help="Test is_delivery_frame on saved frames")
    p.add_argument("--dir", default=str(DELIVERIES_DIR))

    p = sub.add_parser("save-frames",
                        help="Archive current run for labeling")
    p.add_argument("--dir", default=str(DELIVERIES_DIR))
    p.add_argument("--archive", default=None,
                    help="Archive name (default: auto-numbered)")

    p = sub.add_parser("label",
                        help="Interactive labeling guide")
    p.add_argument("--dir", default=str(DELIVERIES_DIR))

    p = sub.add_parser("compare",
                        help="Compare auto vs ground truth")
    p.add_argument("--dir", default=str(DELIVERIES_DIR))

    p = sub.add_parser("accuracy-report",
                        help="Detection + classification accuracy")
    p.add_argument("--dir", default=str(DELIVERIES_DIR))

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return

    cmds = {
        "test-detection": cmd_test_detection,
        "save-frames": cmd_save_frames,
        "label": cmd_label,
        "compare": cmd_compare,
        "accuracy-report": cmd_accuracy_report,
    }
    cmds[args.command](args)


if __name__ == "__main__":
    main()
