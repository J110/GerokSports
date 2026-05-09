#!/usr/bin/env python3
"""A/B: production `scout_label_naive` vs focused prompt `focused_label`.

Reads:
  - ``output/scout_responses.jsonl`` (production path)
  - ``output/scout_responses_focused.jsonl``

Writes ``output/confusion_metrics_focused.json``.
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

# Reuse span/temporal helpers from sibling module
import analyze as an

SCRIPT_DIR = Path(__file__).resolve().parent

GT_ORDER = ("action", "replay", "ad", "other", "umpire", "unknown")
GT_FIVE = frozenset({"action", "replay", "ad", "other", "umpire"})
PROD_PRED = frozenset({"action", "replay", "ad", "other"})
FOC_PRED = frozenset({"action", "replay", "ad", "other", "umpire", "invalid"})


def annotate_temporal_key(rows: list[dict], naive_key: str, out_key: str) -> None:
    by_clip: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        by_clip[(r.get("source_clip") or "").strip()].append(i)
    temporal: list[str | None] = [None] * len(rows)
    for ix_list in by_clip.values():
        indexed = [(i, rows[i]) for i in ix_list]
        indexed.sort(key=lambda ii: float(ii[1]["time_in_clip_s"]))
        seq = []
        for _, rr in indexed:
            v = rr.get(naive_key)
            if v == "invalid":
                v = "other"
            seq.append(v)
        tseq = an.naive_to_temporal_per_clip(seq)
        for (list_idx, _), lab in zip(indexed, tseq):
            temporal[list_idx] = lab
    for i, r in enumerate(rows):
        r[out_key] = temporal[i]


def confusion_full(
        rows: list[dict],
        pred_key: str,
        pred_classes: tuple[str, ...],
) -> dict[str, dict[str, int]]:
    mat = {g: defaultdict(int) for g in GT_ORDER}
    for r in rows:
        g = an.gt_label(r)
        if g not in GT_FIVE and g != "unknown":
            continue
        if g == "unknown":
            continue
        pred = r.get(pred_key)
        if pred not in pred_classes:
            pred = "invalid" if "invalid" in pred_classes else "other"
        mat[g][pred] += 1
    return {gk: dict(v) for gk, v in mat.items()}


def prf_for_class(
        cm: dict[str, dict[str, int]],
        klass: str,
        pred_classes: tuple[str, ...],
        gt_classes: tuple[str, ...],
) -> dict:
    tp = cm.get(klass, {}).get(klass, 0)
    fp = sum(
        cm.get(yt, {}).get(klass, 0)
        for yt in gt_classes
        if yt != klass
    )
    fn = sum(
        cm.get(klass, {}).get(p, 0)
        for p in pred_classes
        if p != klass
    )
    prec = tp / (tp + fp) if (tp + fp) else math.nan
    rec = tp / (tp + fn) if (tp + fn) else math.nan
    f1 = 2 * prec * rec / (prec + rec) if prec + rec > 0 else math.nan
    return {
        "precision": None if math.isnan(prec) else round(prec, 4),
        "recall": None if math.isnan(rec) else round(rec, 4),
        "f1": None if math.isnan(f1) else round(f1, 4),
        "support": sum(cm.get(klass, {}).values()),
    }


def accuracy_five(rows: list[dict], pred_key: str) -> tuple[float, int, int]:
    ok = tot = 0
    for r in rows:
        g = an.gt_label(r)
        if g not in GT_FIVE:
            continue
        tot += 1
        pred = r.get(pred_key)
        if pred == "invalid":
            pred = "invalid"
        if pred == g:
            ok += 1
    return (ok / tot if tot else math.nan, ok, tot)


def accuracy_four(rows: list[dict], pred_key: str) -> tuple[float, int, int]:
    """Same rubric as original analyze: GT ∈ {action,replay,ad,other}."""
    ok = tot = 0
    for r in rows:
        g = an.gt_label(r)
        if g not in an.GT_ALIGNMENT_SET:
            continue
        tot += 1
        pred = r.get(pred_key)
        if pred not in PROD_PRED:
            pred = "other"
        if pred == g:
            ok += 1
    return (ok / tot if tot else math.nan, ok, tot)


def merge_rows(
        prod_path: Path,
        focused_path: Path,
) -> list[dict]:
    prod = {r["frame_path"]: r for r in an.load_rows(prod_path)}
    out = []
    for fr in an.load_rows(focused_path):
        fp = fr["frame_path"]
        pr = prod.get(fp, {})
        row = {
            "frame_path": fp,
            "source_clip": fr.get("source_clip", ""),
            "time_in_clip_s": fr.get("time_in_clip_s", ""),
            "ground_truth": fr.get("ground_truth", ""),
            "focused_response_raw": fr.get("focused_response_raw"),
            "focused_label": fr.get("focused_label"),
            "scout_label_naive": pr.get("scout_label_naive"),
        }
        out.append(row)
    return out


def sample_paths(paths: list[str], k: int = 5) -> list[str]:
    return paths[:k]


def verdict_focused(action_temporal: dict, span_summ: dict) -> tuple[str, str]:
    return an.verdict_for(action_temporal, span_summ)


def main() -> None:
    prod_p = SCRIPT_DIR / "output" / "scout_responses.jsonl"
    foc_p = SCRIPT_DIR / "output" / "scout_responses_focused.jsonl"
    out_p = SCRIPT_DIR / "output" / "confusion_metrics_focused.json"

    if not prod_p.is_file() or not foc_p.is_file():
        print(f"Missing {prod_p} and/or {foc_p}", file=sys.stderr)
        sys.exit(1)

    merged = merge_rows(prod_p, foc_p)
    annotate_temporal_key(
        merged, "focused_label", "focused_label_temporal",
    )

    pred_prod = ("action", "replay", "ad", "other")
    pred_foc = ("action", "replay", "ad", "other", "umpire", "invalid")

    cm_prod = confusion_full(merged, "scout_label_naive", pred_prod)
    cm_foc_n = confusion_full(merged, "focused_label", pred_foc)
    cm_foc_t = confusion_full(merged, "focused_label_temporal", pred_foc)

    # Normalize invalid→other for production-style 4-class view of focused
    for r in merged:
        r["focused_label_4"] = r["focused_label"]
        if r["focused_label_4"] in ("invalid", "umpire"):
            r["focused_label_4"] = "other"
        r["focused_label_temporal_4"] = r["focused_label_temporal"]
        if r["focused_label_temporal_4"] in ("invalid", "umpire"):
            r["focused_label_temporal_4"] = "other"

    cm_foc_n4 = confusion_full(merged, "focused_label_4", pred_prod)
    cm_foc_t4 = confusion_full(merged, "focused_label_temporal_4", pred_prod)

    def pack_metrics(cm, preds, name):
        return {
            "action": prf_for_class(cm, "action", preds, GT_ORDER),
            "replay": prf_for_class(cm, "replay", preds, GT_ORDER),
            "ad": prf_for_class(cm, "ad", preds, GT_ORDER),
            "other": prf_for_class(cm, "other", preds, GT_ORDER),
            "umpire": prf_for_class(cm, "umpire", preds, GT_ORDER),
        }

    m_prod = pack_metrics(cm_prod, pred_prod, "prod")
    m_foc_n = pack_metrics(cm_foc_n, pred_foc, "foc_n")
    m_foc_t = pack_metrics(cm_foc_t, pred_foc, "foc_t")
    m_foc_n4 = pack_metrics(cm_foc_n4, pred_prod, "foc_n4")
    m_foc_t4 = pack_metrics(cm_foc_t4, pred_prod, "foc_t4")

    acc4_p = accuracy_four(merged, "scout_label_naive")
    acc4_f = accuracy_four(merged, "focused_label_4")
    acc4_ft = accuracy_four(merged, "focused_label_temporal_4")
    acc5_p = accuracy_five(merged, "scout_label_naive")
    acc5_f = accuracy_five(merged, "focused_label")
    acc5_ft = accuracy_five(merged, "focused_label_temporal")

    invalid_n = sum(1 for r in merged if r.get("focused_label") == "invalid")
    invalid_rate = invalid_n / len(merged) if merged else 0.0

    act_p = m_prod["action"]
    act_f = m_foc_n["action"]

    delta_r = None

    if act_p.get("recall") is not None and act_f.get("recall") is not None:
        delta_r = round(act_f["recall"] - act_p["recall"], 4)

    stop_s3_focus = False
    if act_f.get("precision") is not None and act_f.get("recall") is not None:
        if act_f["precision"] <= 0.5 or act_f["recall"] <= 0.5:
            stop_s3_focus = True

    capability_ceiling = False
    if act_p.get("recall") is not None and act_f.get("recall") is not None:
        if abs(act_f["recall"] - act_p["recall"]) < 0.05:
            capability_ceiling = True

    # Cohorts (GT action)
    act_frames = [r for r in merged if an.gt_label(r) == "action"]
    foc_miss = [r for r in act_frames if r.get("focused_label") != "action"]
    prod_miss = [r for r in act_frames if r.get("scout_label_naive") != "action"]
    wins = [
        r for r in act_frames
        if r.get("scout_label_naive") != "action"
        and r.get("focused_label") == "action"
    ]
    both_miss = [
        r for r in act_frames
        if r.get("scout_label_naive") != "action"
        and r.get("focused_label") != "action"
    ]

    def pred_counts(rs: list[dict]) -> dict[str, int]:
        c: dict[str, int] = defaultdict(int)
        for r in rs:
            c[str(r.get("focused_label"))] += 1
        return dict(c)

    cohorts = {
        "action_gt_focused_wrong": {
            "n": len(foc_miss),
            "focused_label_histogram": pred_counts(foc_miss),
            "sample_frame_paths": sample_paths(
                [r["frame_path"] for r in foc_miss],
            ),
        },
        "action_gt_production_other_focused_action_wins": {
            "n": len(wins),
            "sample_frame_paths": sample_paths([r["frame_path"] for r in wins]),
        },
        "action_gt_both_prompts_miss": {
            "n": len(both_miss),
            "sample_frame_paths": sample_paths(
                [r["frame_path"] for r in both_miss],
            ),
        },
        "action_gt_production_miss_count": len(prod_miss),
    }

    span_f = an.span_simulation(merged, pred_key="focused_label_temporal_4")
    action_f_temp = prf_for_class(cm_foc_t4, "action", pred_prod, GT_ORDER)
    v_label, v_note = verdict_focused(action_f_temp, span_f["summary"])

    if stop_s3_focus:
        v_note += " (Focused stop S3: action P or R ≤0.5.)"
    if capability_ceiling:
        v_note += " (S3 A/B: Δrecall <5pp vs production — likely capability ceiling.)"

    comparison_rows = [
        {
            "metric": "action_precision_naive",
            "production": m_prod["action"]["precision"],
            "focused": m_foc_n["action"]["precision"],
            "delta": _delta(m_foc_n["action"]["precision"], m_prod["action"]["precision"]),
        },
        {
            "metric": "action_recall_naive",
            "production": m_prod["action"]["recall"],
            "focused": m_foc_n["action"]["recall"],
            "delta": _delta(m_foc_n["action"]["recall"], m_prod["action"]["recall"]),
        },
        {
            "metric": "action_f1_naive",
            "production": m_prod["action"]["f1"],
            "focused": m_foc_n["action"]["f1"],
            "delta": _delta(m_foc_n["action"]["f1"], m_prod["action"]["f1"]),
        },
        {
            "metric": "replay_precision_naive",
            "production": m_prod["replay"]["precision"],
            "focused": m_foc_n["replay"]["precision"],
            "delta": _delta(m_foc_n["replay"]["precision"], m_prod["replay"]["precision"]),
        },
        {
            "metric": "replay_recall_naive",
            "production": m_prod["replay"]["recall"],
            "focused": m_foc_n["replay"]["recall"],
            "delta": _delta(m_foc_n["replay"]["recall"], m_prod["replay"]["recall"]),
        },
        {
            "metric": "umpire_precision_naive",
            "production": m_prod["umpire"]["precision"],
            "focused": m_foc_n["umpire"]["precision"],
            "delta": _delta(m_foc_n["umpire"]["precision"], m_prod["umpire"]["precision"]),
        },
        {
            "metric": "umpire_recall_naive",
            "production": m_prod["umpire"]["recall"],
            "focused": m_foc_n["umpire"]["recall"],
            "delta": _delta(m_foc_n["umpire"]["recall"], m_prod["umpire"]["recall"]),
        },
        {
            "metric": "overall_acc_4class_gt",
            "production": round(acc4_p[0], 4) if not math.isnan(acc4_p[0]) else None,
            "focused": round(acc4_f[0], 4) if not math.isnan(acc4_f[0]) else None,
            "delta": round(acc4_f[0] - acc4_p[0], 4)
            if not math.isnan(acc4_f[0]) and not math.isnan(acc4_p[0]) else None,
        },
        {
            "metric": "overall_acc_5class_gt",
            "production": round(acc5_p[0], 4) if not math.isnan(acc5_p[0]) else None,
            "focused": round(acc5_f[0], 4) if not math.isnan(acc5_f[0]) else None,
            "delta": round(acc5_f[0] - acc5_p[0], 4)
            if not math.isnan(acc5_f[0]) and not math.isnan(acc5_p[0]) else None,
        },
    ]

    action_ft_full = prf_for_class(cm_foc_t, "action", pred_foc, GT_ORDER)

    temporal_compare = {
        "focused_action_naive_full": m_foc_n["action"],
        "focused_action_temporal_collapsed_4pred": m_foc_t4["action"],
        "focused_action_temporal_full": action_ft_full,
        "delta_recall_temporal_minus_naive_collapsed": _delta(
            m_foc_t4["action"]["recall"],
            m_foc_n4["action"]["recall"],
        ),
        "delta_recall_temporal_full_minus_naive_full": _delta(
            action_ft_full["recall"],
            m_foc_n["action"]["recall"],
        ),
    }

    report = {
        "n_frames": len(merged),
        "invalid_focused_parses": invalid_n,
        "invalid_rate": round(invalid_rate, 4),
        "confusion_production_naive": cm_prod,
        "confusion_focused_naive_full": cm_foc_n,
        "confusion_focused_temporal_full": cm_foc_t,
        "confusion_focused_naive_4class_collapsed": cm_foc_n4,
        "confusion_focused_temporal_4class_collapsed": cm_foc_t4,
        "per_class_production_naive": m_prod,
        "per_class_focused_naive_full": m_foc_n,
        "per_class_focused_temporal_full": m_foc_t,
        "accuracy": {
            "fourclass_production_naive": {
                "rate": None if math.isnan(acc4_p[0]) else round(acc4_p[0], 4),
                "correct": acc4_p[1], "n": acc4_p[2],
            },
            "fourclass_focused_naive_collapsed": {
                "rate": None if math.isnan(acc4_f[0]) else round(acc4_f[0], 4),
                "correct": acc4_f[1], "n": acc4_f[2],
            },
            "fourclass_focused_temporal_collapsed": {
                "rate": None if math.isnan(acc4_ft[0]) else round(acc4_ft[0], 4),
                "correct": acc4_ft[1], "n": acc4_ft[2],
            },
            "fiveclass_production_naive": {
                "rate": None if math.isnan(acc5_p[0]) else round(acc5_p[0], 4),
                "correct": acc5_p[1], "n": acc5_p[2],
            },
            "fiveclass_focused_naive": {
                "rate": None if math.isnan(acc5_f[0]) else round(acc5_f[0], 4),
                "correct": acc5_f[1], "n": acc5_f[2],
            },
            "fiveclass_focused_temporal": {
                "rate": None if math.isnan(acc5_ft[0]) else round(acc5_ft[0], 4),
                "correct": acc5_ft[1], "n": acc5_ft[2],
            },
        },
        "comparison_table": comparison_rows,
        "cohorts": cohorts,
        "temporal_on_focused": temporal_compare,
        "span_simulation_focused_temporal_4class": span_f,
        "verdict_focused_temporal": v_label,
        "verdict_notes": v_note,
        "flags": {
            "focused_stop_s3_action_pr_le_0_5": stop_s3_focus,
            "s3_ab_recall_within_5pp": capability_ceiling,
        },
    }

    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {out_p}")


def _delta(new, old):
    if new is None or old is None:
        return None
    return round(new - old, 4)


if __name__ == "__main__":
    main()
