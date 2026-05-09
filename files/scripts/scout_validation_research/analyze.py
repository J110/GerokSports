#!/usr/bin/env python3
"""Confusion matrices (naive + temporal), span simulation, umpire sweep, verdict.

Reads ``output/scout_responses.jsonl`` from ``run_scout.py``.
Writes ``output/confusion_metrics.json`` and ``output/failure_patterns.txt``.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_JSONL = SCRIPT_DIR / "output" / "scout_responses.jsonl"

GT_LABELS_ORDER = ("action", "replay", "ad", "other", "umpire", "unknown")
SCOUT_PRED_ORDER = ("action", "replay", "ad", "other")
GT_ALIGNMENT_SET = frozenset({"action", "replay", "ad", "other"})
POSITIVE_SESSION_PREFIX = "20260420_214218/"


def gt_label(row: dict) -> str:
    return (row.get("ground_truth") or row.get("ground_truth_label") or "").strip()


def load_rows(path: Path) -> list[dict]:
    out: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def action_runs_indices(naive: list[str]) -> list[tuple[int, int]]:
    n = len(naive)
    runs: list[tuple[int, int]] = []
    i = 0
    while i < n:
        if naive[i] != "action":
            i += 1
            continue
        j = i
        while j < n and naive[j] == "action":
            j += 1
        runs.append((i, j - 1))
        i = j
    return runs


def naive_to_temporal_per_clip(naive: list[str]) -> list[str]:
    runs = action_runs_indices(naive)
    out = list(naive)
    for rk, (a, b) in enumerate(runs):
        if rk == 0:
            continue
        for idx in range(a, b + 1):
            out[idx] = "replay"
    return out


def annotate_temporal(rows: list[dict]) -> list[dict]:
    by_clip: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        clip = (r.get("source_clip") or "").strip()
        by_clip[clip].append(i)

    temporal: list[str | None] = [None] * len(rows)
    for ix_list in by_clip.values():
        indexed = [(i, rows[i]) for i in ix_list]
        indexed.sort(key=lambda ii: float(ii[1]["time_in_clip_s"]))
        naive_seq = [r["scout_label_naive"] for _, r in indexed]
        temporal_seq = naive_to_temporal_per_clip(naive_seq)
        for (list_idx, _), tlab in zip(indexed, temporal_seq):
            temporal[list_idx] = tlab

    out_rows = []
    for i, r in enumerate(rows):
        rr = dict(r)
        rr["scout_label_temporal"] = temporal[i]
        out_rows.append(rr)
    return out_rows


def confusion_counts(rows: list[dict], *, pred_key: str) -> dict[str, dict[str, int]]:
    mat: dict[str, dict[str, int]] = {
        lg: defaultdict(int) for lg in GT_LABELS_ORDER
    }
    gt_allowed = frozenset(GT_LABELS_ORDER)
    for r in rows:
        yt = gt_label(r)
        if yt not in gt_allowed:
            continue
        pred = r.get(pred_key)
        if pred not in SCOUT_PRED_ORDER:
            pred = "other"
        mat[yt][pred] += 1
    return {yk: dict(vv) for yk, vv in mat.items()}


def overall_accuracy_fourclass(rows: list[dict], pred_key: str) -> tuple[float, int, int]:
    usable = [r for r in rows if gt_label(r) in GT_ALIGNMENT_SET]
    if not usable:
        return float("nan"), 0, 0
    ok = sum(1 for r in usable if r[pred_key] == gt_label(r))
    return ok / len(usable), ok, len(usable)


def class_prf(cm: dict[str, dict[str, int]], *, klass: str) -> dict:
    tp = cm.get(klass, {}).get(klass, 0)
    fp = sum(cm.get(yt, {}).get(klass, 0) for yt in GT_LABELS_ORDER if yt != klass)
    fn = sum(cm.get(klass, {}).get(p, 0) for p in SCOUT_PRED_ORDER if p != klass)
    prec = tp / (tp + fp) if (tp + fp) else math.nan
    rec = tp / (tp + fn) if (tp + fn) else math.nan
    f1 = 2 * prec * rec / (prec + rec) if prec + rec > 0 else math.nan
    return {
        "precision": None if math.isnan(prec) else round(prec, 4),
        "recall": None if math.isnan(rec) else round(rec, 4),
        "f1": None if math.isnan(f1) else round(f1, 4),
        "support": sum(cm.get(klass, {}).values()),
    }


def temporal_lift_stats(rows: list[dict]) -> dict:

    naive_action_to_temp_replay = 0

    of_those_gt_replay = 0

    of_those_gt_action = 0

    of_those_gt_other = 0

    for r in rows:

        if r["scout_label_naive"] != "action":

            continue

        if r["scout_label_temporal"] != "replay":

            continue

        naive_action_to_temp_replay += 1

        g = gt_label(r)

        if g == "replay":

            of_those_gt_replay += 1

        elif g == "action":

            of_those_gt_action += 1

        else:

            of_those_gt_other += 1

    return {
        "naive_action_frames_reclassified_to_replay": naive_action_to_temp_replay,

        "of_those_with_ground_truth_replay": of_those_gt_replay,

        "of_those_with_ground_truth_action": of_those_gt_action,

        "of_those_with_ground_truth_other_bucket": of_those_gt_other,
    }


def umpire_report(rows: list[dict]) -> list[dict]:
    rep = []
    for r in rows:
        if gt_label(r) != "umpire":
            continue
        sr = r.get("scout_response") or {}
        rep.append({
            "frame_path": r.get("frame_path"),
            "scout_label_naive": r.get("scout_label_naive"),
            "scout_label_temporal": r.get("scout_label_temporal"),
            "frame_type": sr.get("frame_type"),

            "last_camera_view": sr.get("last_camera_view"),

            "last_frame_phase": sr.get("last_frame_phase"),

            "description_preview": (sr.get("description_preview") or "")[:240],
        })

    return rep


def classify_failure_pattern(gt: str, pred: str) -> str:

    """Temporal-corrected misclassification bucket."""

    if gt == "action" and pred == "other":

        return "P1_action_as_other"

    if gt == "action" and pred == "replay":

        return "P1b_action_as_replay_demotion_or_model"

    if gt == "replay" and pred == "action":

        return "P2_replay_as_action_after_temporal"

    if gt == "umpire":

        return "P3_umpire_frame"

    if (gt == "ad" and pred != "ad") or (pred == "ad" and gt != "ad"):

        return "P4_ad_other_cross"

    return "P5_other"


def collect_failure_patterns(
        rows: list[dict],
        *,
        pred_key: str,
) -> tuple[dict[str, list[str]], dict[str, int]]:
    buckets: dict[str, list[str]] = defaultdict(list)
    counts: dict[str, int] = defaultdict(int)

    for r in rows:
        g = gt_label(r)
        pred = r.get(pred_key)
        if pred not in SCOUT_PRED_ORDER:
            pred = "other"

        if g == "umpire":
            pat = "P3_umpire_frame"
            counts[pat] += 1
            fp = r.get("frame_path") or ""
            if len(buckets[pat]) < 5 and fp:
                buckets[pat].append(fp)
            continue

        if g == "unknown":
            pat = "P5_other"
            counts[pat] += 1
            fp = r.get("frame_path") or ""
            if len(buckets[pat]) < 5 and fp:
                buckets[pat].append(fp)
            continue

        if g not in GT_ALIGNMENT_SET:
            continue

        if pred == g:
            continue

        pat = classify_failure_pattern(g, pred)

        counts[pat] += 1
        fp = r.get("frame_path") or ""
        if len(buckets[pat]) < 5 and fp:
            buckets[pat].append(fp)

    return dict(buckets), dict(counts)


def _spans(times: list[float], labels: list[str], target: str) -> list[dict]:
    pairs = sorted(zip(times, labels), key=lambda z: z[0])
    spans: list[dict] = []
    start = None
    last_t = None
    cnt = 0
    for t, lbl in pairs:
        tt = float(t)
        if lbl == target:
            if start is None:
                start = tt
                cnt = 1
            else:
                cnt += 1
            last_t = tt
        else:
            if start is not None and last_t is not None:
                spans.append({"start_s": start, "end_s": last_t, "frames": cnt})
                start = last_t = None
                cnt = 0
    if start is not None:
        spans.append({"start_s": start, "end_s": last_t or start, "frames": cnt})
    return spans


def _intervals_overlap(
        a: list[tuple[float, float]],
        b: list[tuple[float, float]],
) -> bool:
    for xa, xb in a:
        for ya, yb in b:
            if xa <= yb + 1e-6 and ya <= xb + 1e-6:
                return True
    return False


def span_simulation(rows: list[dict], *, pred_key: str) -> dict:
    by_clip: dict[str, list[tuple[float, dict]]] = defaultdict(list)
    for r in rows:
        clip = (r.get("source_clip") or "").strip()
        try:
            t = float(r["time_in_clip_s"])
        except (TypeError, ValueError):
            continue
        by_clip[clip].append((t, r))

    per_clip: dict[str, dict] = {}
    pos_ok = neg_ok = 0
    pos_tot = neg_tot = 0

    for clip, zipped in sorted(by_clip.items()):
        zipped.sort(key=lambda z: z[0])
        times = [t for t, _ in zipped]
        gt_lbls = [gt_label(rr) for _, rr in zipped]
        pred_lbls = [rr[pred_key] for _, rr in zipped]

        st_action = _spans(times, gt_lbls, "action")
        sd_action = _spans(times, pred_lbls, "action")

        it_t = [(s["start_s"], s["end_s"]) for s in st_action]
        it_p = [(s["start_s"], s["end_s"]) for s in sd_action]
        overlap = _intervals_overlap(it_t, it_p)
        longest_pred = max((s["frames"] for s in sd_action), default=0)
        truth_has_action = len(st_action) > 0

        if clip.startswith(POSITIVE_SESSION_PREFIX):
            pos_tot += 1
            ok = overlap and longest_pred >= 1
            pos_ok += int(ok)
        else:
            neg_tot += 1
            ok = True
            if not truth_has_action and longest_pred >= 3:
                ok = False
            elif truth_has_action and not overlap and longest_pred == 0:
                ok = False
            neg_ok += int(ok)

        per_clip[clip] = {
            "truth_action_spans": st_action,
            "pred_action_spans": sd_action,
            "overlap": overlap,
            "verdict_clip": "pass" if ok else "fail",
        }

    return {
        "per_clip": per_clip,
        "summary": {
            "positive_pass": pos_ok,
            "positive_total": pos_tot,
            "negative_pass": neg_ok,
            "negative_total": neg_tot,
            "clip_pass_total": pos_ok + neg_ok,
            "clip_denominator": pos_tot + neg_tot,
        },
    }


def verdict_for(
        action_pr: dict,
        span_summary: dict,
) -> tuple[str, str]:
    p = action_pr.get("precision")
    r = action_pr.get("recall")
    cp = span_summary["clip_pass_total"]
    cd = span_summary["clip_denominator"]

    pr_ok = (
        p is not None and r is not None
        and p > 0.85 and r > 0.85
    )
    if pr_ok and cp >= max(13, cd - 2 if cd else 0):
        return (
            "Strong",
            f"Temporal action P={p}/R={r} (>0.85) and span QC {cp}/{cd}.",
        )

    weak_pr = p is None or r is None or min(p, r) < 0.7
    if weak_pr or cp < 11:
        return (
            "Weak",
            f"Temporal action weak or span pass {cp}/{cd}.",
        )
    return (
        "Mixed",
        "Borderline temporal action metrics or span-level 11–13/15.",
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    ap.add_argument(
        "--out-json",
        type=Path,
        default=SCRIPT_DIR / "output" / "confusion_metrics.json",
    )
    ap.add_argument(
        "--patterns-out",
        type=Path,
        default=SCRIPT_DIR / "output" / "failure_patterns.txt",
    )
    args = ap.parse_args()

    js = args.jsonl.expanduser().resolve()
    if not js.is_file():
        print(f"Missing {js}", file=sys.stderr)
        sys.exit(1)

    raw_rows = load_rows(js)
    rows_t = annotate_temporal(raw_rows)

    cm_naive = confusion_counts(rows_t, pred_key="scout_label_naive")
    cm_temp = confusion_counts(rows_t, pred_key="scout_label_temporal")

    acc_n, ok_n, n_n = overall_accuracy_fourclass(rows_t, "scout_label_naive")
    acc_t, ok_t, n_t = overall_accuracy_fourclass(rows_t, "scout_label_temporal")

    action_naive = class_prf(cm_naive, klass="action")
    action_temp = class_prf(cm_temp, klass="action")

    p_na = action_naive.get("precision")
    r_na = action_naive.get("recall")
    stop_s3 = False
    if p_na is not None and r_na is not None:
        if min(p_na, r_na) < 0.5:
            stop_s3 = True

    stop_s4 = False
    if not math.isnan(acc_n) and not math.isnan(acc_t) and acc_t < acc_n:
        stop_s4 = True

    lift = temporal_lift_stats(rows_t)

    patterns_b, pattern_counts = collect_failure_patterns(
        rows_t, pred_key="scout_label_temporal",
    )

    ump = umpire_report(rows_t)

    span_block = span_simulation(rows_t, pred_key="scout_label_temporal")
    v_label, v_note = verdict_for(action_temp, span_block["summary"])
    if stop_s3:
        v_note += (
            " Stop S3 fired (naive action min(P,R)<0.5 — recall dominates failure); "
            "span table kept for Section 5 audit."
        )

    report = {
        "n_frames": len(rows_t),
        "confusion_matrix_naive_rows_gt_cols_pred": cm_naive,
        "confusion_matrix_temporal_rows_gt_cols_pred": cm_temp,
        "per_class_metrics_naive": {
            c: class_prf(cm_naive, klass=c) for c in SCOUT_PRED_ORDER
        },
        "per_class_metrics_temporal": {
            c: class_prf(cm_temp, klass=c) for c in SCOUT_PRED_ORDER
        },
        "accuracy_fourclass_only": {
            "naive": {"rate": None if math.isnan(acc_n) else round(acc_n, 4),
                      "correct": ok_n, "n": n_n},
            "temporal": {"rate": None if math.isnan(acc_t) else round(acc_t, 4),
                         "correct": ok_t, "n": n_t},
        },
        "stop_s3_naive_action_min_pr_below_0_5": stop_s3,
        "stop_s4_temporal_accuracy_lower_than_naive": stop_s4,
        "temporal_reclassification_stats": lift,
        "failure_pattern_counts_temporal": pattern_counts,
        "failure_pattern_example_paths_max5": patterns_b,
        "umpire_frame_scout_outputs": ump,
        "span_simulation_temporal": span_block,
        "verdict": v_label,
        "verdict_notes": v_note,
        "action_metrics_temporal": action_temp,
        "action_metrics_naive": action_naive,
    }

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        f"# Verdict: {v_label}",
        v_note,
        "",
        "## Stop flags",
        f"S3 (naive action min(P,R) <0.5): {stop_s3}",
        f"S4 (temporal 4-class acc < naive): {stop_s4}",
        "",
        "## Temporal reclassification (naive action → temporal replay)",
        json.dumps(lift, indent=2),
        "",
        "## Failure pattern counts (temporal)",
        json.dumps(pattern_counts, indent=2),
        "",
        "## Example paths (max 5 per pattern)",
        json.dumps(patterns_b, indent=2),
        "",
        "## Span simulation (temporal labels, audit)",
        json.dumps(span_block["summary"], indent=2),
        "",
        "## Umpire frames (Scout behavior)",
        json.dumps(ump, indent=2),
    ]
    args.patterns_out.parent.mkdir(parents=True, exist_ok=True)
    args.patterns_out.write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote {args.out_json} and {args.patterns_out}")


if __name__ == "__main__":
    main()
