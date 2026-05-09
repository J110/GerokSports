#!/usr/bin/env python3
"""Compare open-ended Scout vs Qwen on the same 247 frames.

Reads:
  - output/scout_responses_open.jsonl
  - output/qwen_responses_open.jsonl

Writes:
  - output/qwen_vs_scout_comparison.json
  - output/qwen_vs_scout_per_frame.csv

Rule v1: ``classify_descriptions.classify_v1`` (wide field view ∧ no close-up terms).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

import analyze as an
import analyze_open_descriptions as aod
import classify_descriptions as cd

SCRIPT_DIR = Path(__file__).resolve().parent
SCOUT_JSONL = SCRIPT_DIR / "output" / "scout_responses_open.jsonl"
QWEN_JSONL = SCRIPT_DIR / "output" / "qwen_responses_open.jsonl"
OUT_JSON = SCRIPT_DIR / "output" / "qwen_vs_scout_comparison.json"
OUT_CSV = SCRIPT_DIR / "output" / "qwen_vs_scout_per_frame.csv"


def classify_v1_equivalent_cross_vlm(desc: str) -> str:
    """Intent-align v1 for models that paraphrase the prompt ('wide view' not 'wide field view')."""
    d = (desc or "").lower()
    if any(t in d for t in cd.CLOSEUP_TERMS_V1):
        return "other"
    if "wide field view" in d:
        return "action"
    if "wide view" in d and ("cricket" in d or "field" in d or "pitch" in d
                              or "match" in d or "stadium" in d or "ground" in d):
        return "action"
    if ("wide angle" in d or "wide-angle" in d) and (
            "cricket" in d or "field" in d or "pitch" in d or "match" in d):
        return "action"
    return "other"


def _binary_action_prf(
        rows: list[dict],
        pred_key_or_fn: Any,
        desc_key: str = "open_description",
) -> dict:
    """action vs rest (binary), GT uses an.gt_label."""
    tp = fp = fn = 0
    for r in rows:
        g = an.gt_label(r)
        if g == "unknown":
            continue
        desc = (r.get(desc_key) or "")
        if callable(pred_key_or_fn):
            pred = pred_key_or_fn(r, desc)
        else:
            pred = r.get(pred_key_or_fn) or "other"
        gt_act = g == "action"
        pr_act = pred == "action"
        if gt_act and pr_act:
            tp += 1
        elif not gt_act and pr_act:
            fp += 1
        elif gt_act and not pr_act:
            fn += 1
    prec = tp / (tp + fp) if (tp + fp) else float("nan")
    rec = tp / (tp + fn) if (tp + fn) else float("nan")
    f1 = 2 * prec * rec / (prec + rec) if prec + rec > 0 else float("nan")
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": None if math.isnan(prec) else round(prec, 4),
        "recall": None if math.isnan(rec) else round(rec, 4),
        "f1": None if math.isnan(f1) else round(f1, 4),
    }


def _prf_binary_detector(
        rows: list[dict],
        desc_key: str,
        detector: Callable[[str], bool],
        pos_gt: Callable[[str], bool],
) -> dict:
    tp = fp = fn = tn = 0
    for r in rows:
        g = an.gt_label(r)
        if g == "unknown":
            continue
        desc = r.get(desc_key) or ""
        hit = detector(desc)
        pos = pos_gt(g)
        if hit and pos:
            tp += 1
        elif hit and not pos:
            fp += 1
        elif not hit and pos:
            fn += 1
        else:
            tn += 1
    prec = tp / (tp + fp) if (tp + fp) else float("nan")
    rec = tp / (tp + fn) if (tp + fn) else float("nan")
    f1 = 2 * prec * rec / (prec + rec) if prec + rec > 0 else float("nan")
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": None if math.isnan(prec) else round(prec, 4),
        "recall": None if math.isnan(rec) else round(rec, 4),
        "f1": None if math.isnan(f1) else round(f1, 4),
        "support_pos": tp + fn,
    }


def _five_class_acc(rows: list[dict], pred_key: str) -> dict:
    labs = frozenset({"action", "replay", "ad", "other", "umpire"})
    n = c = 0
    for r in rows:
        g = an.gt_label(r)
        if g not in labs:
            continue
        n += 1
        p = r.get(pred_key, "other")
        if p not in labs:
            p = "other"
        if p == g:
            c += 1
    return {"correct": c, "n": n, "rate": round(c / n, 4) if n else None}


def _multiclass_cm(rows: list[dict], pred_key: str) -> dict[str, dict[str, int]]:
    labs = ("action", "replay", "ad", "other", "umpire")
    mat = {g: {p: 0 for p in labs} for g in labs}
    for r in rows:
        g = an.gt_label(r)
        if g not in labs:
            continue
        p = r.get(pred_key, "other")
        if p not in labs:
            p = "other"
        mat[g][p] += 1
    return mat


def _per_class_prf(cm: dict[str, dict[str, int]], klass: str) -> dict:
    tp = cm[klass][klass]
    fp = sum(cm[g][klass] for g in cm if g != klass)
    fn = sum(cm[klass][p] for p in cm[klass] if p != klass)
    prec = tp / (tp + fp) if (tp + fp) else float("nan")
    rec = tp / (tp + fn) if (tp + fn) else float("nan")
    f1 = 2 * prec * rec / (prec + rec) if prec + rec > 0 else float("nan")
    return {
        "precision": None if math.isnan(prec) else round(prec, 4),
        "recall": None if math.isnan(rec) else round(rec, 4),
        "f1": None if math.isnan(f1) else round(f1, 4),
        "support": sum(cm[klass].values()),
    }


def _build_ngram_corner(rows: list[dict]) -> dict:
    """Subset of ``analyze_open_descriptions`` per-class bigrams/trigrams + disc terms."""
    labs = frozenset({"action", "replay", "ad", "other", "umpire"})
    by_class_desc: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        gt = an.gt_label(r)
        if gt in labs:
            by_class_desc[gt].append((r.get("open_description") or "").strip())

    class_tokens: dict[str, Counter] = {}
    gram2: dict[str, Counter] = {}
    gram3: dict[str, Counter] = {}
    for cname in sorted(labs):
        ctr = Counter()
        g2 = Counter()
        g3 = Counter()
        for t in by_class_desc.get(cname, []):
            fts = aod.filtered_tokens(t)
            ctr.update(fts)
            for ng in aod.ngrams_from_tokens(fts, 2):
                g2[ng] += 1
            for ng in aod.ngrams_from_tokens(fts, 3):
                g3[ng] += 1
        class_tokens[cname] = ctr
        gram2[cname] = g2
        gram3[cname] = g3

    disc = aod.discriminative_tokens(class_tokens, top_k=25, min_in_class=2)
    top_n = 20
    out = {}
    for cname in sorted(labs):
        out[cname] = {
            "2grams_top": aod.top_counter(gram2[cname], top_n),
            "3grams_top": aod.top_counter(gram3[cname], 15),
            "discriminative_log_ratio_terms": disc.get(cname, []),
        }
    return out


def _merge_scout_qwen(scout_rows: list[dict], qwen_by_path: dict[str, dict]) -> list[dict]:
    merged = []
    missing_q = 0
    for sr in sorted(scout_rows, key=lambda x: x.get("frame_path", "")):
        fp = sr.get("frame_path", "")
        qr = qwen_by_path.get(fp)
        if not qr:
            missing_q += 1
            continue
        merged.append({
            "frame_path": fp,
            "source_clip": sr.get("source_clip", ""),
            "time_in_clip_s": sr.get("time_in_clip_s", ""),
            "ground_truth": sr.get("ground_truth", ""),
            "scout_description": sr.get("open_description", ""),
            "qwen_description": qr.get("open_description", ""),
            "scout_raw": sr.get("raw_response"),
            "qwen_raw": qr.get("raw_response"),
            "qwen_latency_ms": qr.get("latency_ms"),
        })
    return merged, missing_q


def _classify_full_on(desc: str, *, binary_fn: Callable[[str], str] | None = None) -> str:
    fn = binary_fn if binary_fn is not None else cd.classify_v1
    return cd.classify_full(desc or "", binary_fn=fn)


def _combo_or(scout_d: str, qwen_d: str) -> str:
    """Multiclass: pattern OR across models; action if either v1 fires."""
    if cd.is_ad_pattern(scout_d) or cd.is_ad_pattern(qwen_d):
        return "ad"
    if cd.is_replay_pattern(scout_d) or cd.is_replay_pattern(qwen_d):
        return "replay"
    if cd.is_umpire_pattern(scout_d) or cd.is_umpire_pattern(qwen_d):
        return "umpire"
    if cd.classify_v1(scout_d) == "action" or cd.classify_v1(qwen_d) == "action":
        return "action"
    return "other"


def _combo_and(scout_d: str, qwen_d: str) -> str:
    """Multiclass: patterns OR; action only if both v1 action."""
    if cd.is_ad_pattern(scout_d) or cd.is_ad_pattern(qwen_d):
        return "ad"
    if cd.is_replay_pattern(scout_d) or cd.is_replay_pattern(qwen_d):
        return "replay"
    if cd.is_umpire_pattern(scout_d) or cd.is_umpire_pattern(qwen_d):
        return "umpire"
    if cd.classify_v1(scout_d) == "action" and cd.classify_v1(qwen_d) == "action":
        return "action"
    return "other"


def _combo_agreement(scout_d: str, qwen_d: str) -> str:
    """Multiclass: same priority; action only when v1 agrees on action."""
    if cd.is_ad_pattern(scout_d) or cd.is_ad_pattern(qwen_d):
        return "ad"
    if cd.is_replay_pattern(scout_d) or cd.is_replay_pattern(qwen_d):
        return "replay"
    if cd.is_umpire_pattern(scout_d) or cd.is_umpire_pattern(qwen_d):
        return "umpire"
    sa = cd.classify_v1(scout_d) == "action"
    qa = cd.classify_v1(qwen_d) == "action"
    if sa and qa:
        return "action"
    return "other"


def _combo_or_scout_literal_qwen_equiv(scout_d: str, qwen_d: str) -> str:
    """OR on binary: Scout literal v1 ∨ Qwen intent-equivalent wide rule."""
    if cd.is_ad_pattern(scout_d) or cd.is_ad_pattern(qwen_d):
        return "ad"
    if cd.is_replay_pattern(scout_d) or cd.is_replay_pattern(qwen_d):
        return "replay"
    if cd.is_umpire_pattern(scout_d) or cd.is_umpire_pattern(qwen_d):
        return "umpire"
    if cd.classify_v1(scout_d) == "action" or classify_v1_equivalent_cross_vlm(
            qwen_d) == "action":
        return "action"
    return "other"


def _combo_and_scout_literal_qwen_equiv(scout_d: str, qwen_d: str) -> str:
    if cd.is_ad_pattern(scout_d) or cd.is_ad_pattern(qwen_d):
        return "ad"
    if cd.is_replay_pattern(scout_d) or cd.is_replay_pattern(qwen_d):
        return "replay"
    if cd.is_umpire_pattern(scout_d) or cd.is_umpire_pattern(qwen_d):
        return "umpire"
    if cd.classify_v1(scout_d) == "action" and classify_v1_equivalent_cross_vlm(
            qwen_d) == "action":
        return "action"
    return "other"


def _combo_agreement_scout_literal_qwen_equiv(scout_d: str, qwen_d: str) -> str:
    if cd.is_ad_pattern(scout_d) or cd.is_ad_pattern(qwen_d):
        return "ad"
    if cd.is_replay_pattern(scout_d) or cd.is_replay_pattern(qwen_d):
        return "replay"
    if cd.is_umpire_pattern(scout_d) or cd.is_umpire_pattern(qwen_d):
        return "umpire"
    sa = cd.classify_v1(scout_d) == "action"
    qa = classify_v1_equivalent_cross_vlm(qwen_d) == "action"
    if sa and qa:
        return "action"
    return "other"


def _row_flag(m: dict) -> str:
    ds = m["scout_description"] or ""
    dq = m["qwen_description"] or ""
    sl = ds.lower()
    ql = dq.lower()
    wfs = "wide field view" in sl
    wfq = "wide field view" in ql
    if wfs != wfq:
        if wfs and not wfq:
            return "scout_wide_not_qwen"
        return "qwen_wide_not_scout"
    # coarse content hints (not exhaustive)
    if not ds.strip() or not dq.strip():
        return "empty_description"
    rs = cd.is_replay_pattern(ds)
    rq = cd.is_replay_pattern(dq)
    if rs != rq:
        return "replay_language_mismatch"
    return "similar_wide_field_hint" if wfs and wfq else "both_no_wide_phrase"


def _scout_latency_ms(raw: Any) -> int | None:
    if not isinstance(raw, dict):
        return None
    u = raw.get("usage")
    if isinstance(u, dict) and u.get("total_time") is not None:
        try:
            return int(float(u["total_time"]) * 1000)
        except (TypeError, ValueError):
            pass
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scout-jsonl", type=Path, default=SCOUT_JSONL)
    ap.add_argument("--qwen-jsonl", type=Path, default=QWEN_JSONL)
    args = ap.parse_args()

    scout_p = args.scout_jsonl.resolve()
    qwen_p = args.qwen_jsonl.resolve()
    if not scout_p.is_file():
        print(f"Missing {scout_p}", file=sys.stderr)
        return 2
    if not qwen_p.is_file():
        print(f"Missing {qwen_p} — run run_qwen_open.py first.", file=sys.stderr)
        return 2

    scout_rows = an.load_rows(scout_p)
    qwen_rows = an.load_rows(qwen_p)
    qwen_by = {r["frame_path"]: r for r in qwen_rows if r.get("frame_path")}

    merged, missing_q = _merge_scout_qwen(scout_rows, qwen_by)
    if missing_q:
        print(f"[warn] {missing_q} scout frames missing Qwen rows", file=sys.stderr)

    emp_usd = 0.0
    for r in qwen_rows:
        raw = r.get("raw_response")
        if isinstance(raw, dict):
            u = raw.get("usage")
            if isinstance(u, dict) and u.get("prompt_tokens") is not None:
                pi = int(u.get("prompt_tokens") or 0)
                co = int(u.get("completion_tokens") or 0)
                emp_usd += (pi * 0.15 + co * 0.60) / 1_000_000.0

    qwen_err = sum(
        1 for r in qwen_rows
        if isinstance(r.get("raw_response"), dict) and r["raw_response"].get("error")
    )
    qwen_empty = sum(
        1 for r in merged
        if not (r.get("qwen_description") or "").strip()
    )

    scout_lat: list[int] = []
    qwen_lat: list[int] = []
    for m in merged:
        sl = _scout_latency_ms(m.get("scout_raw"))
        if sl:
            scout_lat.append(sl)
        ql = m.get("qwen_latency_ms")
        if isinstance(ql, int) and ql > 0:
            qwen_lat.append(ql)

    # Enrich merged rows with predictions
    enriched = []
    for m in merged:
        ds, dq = m["scout_description"], m["qwen_description"]
        row = dict(m)
        row["rule_v1_scout"] = cd.classify_v1(ds)
        row["rule_v1_qwen_literal"] = cd.classify_v1(dq)
        row["rule_v1_qwen_equivalent"] = classify_v1_equivalent_cross_vlm(dq)
        row["multiclass_scout"] = _classify_full_on(ds)
        row["multiclass_qwen"] = _classify_full_on(
            dq, binary_fn=classify_v1_equivalent_cross_vlm,
        )
        row["multiclass_combo_or"] = _combo_or(ds, dq)
        row["multiclass_combo_and"] = _combo_and(ds, dq)
        row["multiclass_combo_agreement"] = _combo_agreement(ds, dq)
        row["multiclass_combo_or_scout_lit_qwen_equiv"] = (
            _combo_or_scout_literal_qwen_equiv(ds, dq))
        row["multiclass_combo_and_scout_lit_qwen_equiv"] = (
            _combo_and_scout_literal_qwen_equiv(ds, dq))
        row["multiclass_combo_agreement_scout_lit_qwen_equiv"] = (
            _combo_agreement_scout_literal_qwen_equiv(ds, dq))
        row["review_flag"] = _row_flag(m)
        enriched.append(row)

    scout_only = [{"open_description": e["scout_description"],
                   "ground_truth": e["ground_truth"],
                   "frame_path": e["frame_path"]} for e in enriched]
    qwen_only = [{"open_description": e["qwen_description"],
                  "ground_truth": e["ground_truth"],
                  "frame_path": e["frame_path"]} for e in enriched]

    def _pred_binary_or(r: dict, _: str) -> str:
        if r["rule_v1_scout"] == "action" or r["rule_v1_qwen_literal"] == "action":
            return "action"
        return "other"

    def _pred_binary_and(r: dict, _: str) -> str:
        if r["rule_v1_scout"] == "action" and r["rule_v1_qwen_literal"] == "action":
            return "action"
        return "other"

    def _pred_binary_agree(r: dict, _: str) -> str:
        sa = r["rule_v1_scout"] == "action"
        qa = r["rule_v1_qwen_literal"] == "action"
        if sa and qa:
            return "action"
        return "other"

    def _pred_binary_or_equiv_qwen(r: dict, _: str) -> str:
        if r["rule_v1_scout"] == "action" or r["rule_v1_qwen_equivalent"] == "action":
            return "action"
        return "other"

    def _pred_binary_and_equiv_qwen(r: dict, _: str) -> str:
        if r["rule_v1_scout"] == "action" and r["rule_v1_qwen_equivalent"] == "action":
            return "action"
        return "other"

    metrics = {
        "n_frames_scout": len(scout_rows),
        "n_frames_qwen_file": len(qwen_rows),
        "n_frames_merged": len(merged),
        "qwen_api_error_rows": qwen_err,
        "qwen_empty_description_merged": qwen_empty,
        "latency_ms": {
            "scout_from_usage_total_time": {
                "n": len(scout_lat),
                "median": statistics.median(scout_lat) if scout_lat else None,
            },
            "qwen_wall": {
                "n": len(qwen_lat),
                "median": statistics.median(qwen_lat) if qwen_lat else None,
                "p90": sorted(qwen_lat)[int(len(qwen_lat) * 0.9) - 1] if len(qwen_lat) > 5 else None,
            },
        },
        "rule_v1_binary_action_vs_rest": {
            "scout_literal": _binary_action_prf(enriched, "rule_v1_scout"),
            "qwen_literal_substring_wide_field_view": _binary_action_prf(
                enriched, "rule_v1_qwen_literal"),
            "qwen_equivalent_wide_camera_paraphrase": _binary_action_prf(
                enriched, "rule_v1_qwen_equivalent"),
            "either_literal_OR": _binary_action_prf(enriched, _pred_binary_or),
            "both_literal_AND": _binary_action_prf(enriched, _pred_binary_and),
            "agreement_literal_both_must_match": _binary_action_prf(
                enriched, _pred_binary_agree),
            "either_scout_literal_OR_qwen_equiv": _binary_action_prf(
                enriched, _pred_binary_or_equiv_qwen),
            "both_scout_literal_AND_qwen_equiv": _binary_action_prf(
                enriched, _pred_binary_and_equiv_qwen),
        },
        "pattern_detection": {
            "replay": {
                "scout": _prf_binary_detector(
                    enriched, "scout_description", cd.is_replay_pattern,
                    lambda g: g == "replay",
                ),
                "qwen": _prf_binary_detector(
                    enriched, "qwen_description", cd.is_replay_pattern,
                    lambda g: g == "replay",
                ),
            },
            "ad": {
                "scout": _prf_binary_detector(
                    enriched, "scout_description", cd.is_ad_pattern,
                    lambda g: g == "ad",
                ),
                "qwen": _prf_binary_detector(
                    enriched, "qwen_description", cd.is_ad_pattern,
                    lambda g: g == "ad",
                ),
            },
            "umpire": {
                "scout": _prf_binary_detector(
                    enriched, "scout_description", cd.is_umpire_pattern,
                    lambda g: g == "umpire",
                ),
                "qwen": _prf_binary_detector(
                    enriched, "qwen_description", cd.is_umpire_pattern,
                    lambda g: g == "umpire",
                ),
            },
        },
        "five_class_accuracy": {
            "scout_classify_full_v1": _five_class_acc(enriched, "multiclass_scout"),
            "qwen_classify_full_equiv_wide_rule": _five_class_acc(enriched, "multiclass_qwen"),
            "combo_OR_literal_both": _five_class_acc(enriched, "multiclass_combo_or"),
            "combo_AND_literal_both": _five_class_acc(enriched, "multiclass_combo_and"),
            "combo_agreement_literal_both": _five_class_acc(
                enriched, "multiclass_combo_agreement"),
            "combo_OR_scout_literal_qwen_equiv": _five_class_acc(
                enriched, "multiclass_combo_or_scout_lit_qwen_equiv"),
            "combo_AND_scout_literal_qwen_equiv": _five_class_acc(
                enriched, "multiclass_combo_and_scout_lit_qwen_equiv"),
            "combo_agreement_scout_literal_qwen_equiv": _five_class_acc(
                enriched, "multiclass_combo_agreement_scout_lit_qwen_equiv"),
        },
        "qwen_ngrams_summary": _build_ngram_corner(qwen_only),
        "cost_note": {
            "scout_reference": "eyes/config.py — ~$0.09/match at CAPTURE_FPS=2-style broadcast (Groq Scout comment; per-window not per-frame).",
            "qwen_fireworks_list": (
                "Qwen3-VL-30B Instruct ≈ $0.15/1M input + $0.60/1M output tokens on Fireworks; "
                "sum usage.* from qwen JSONL for empirical totals."
            ),
            "qwen_empirical_usd_summed_from_jsonl": round(emp_usd, 4),
        },
    }

    for block_name, pred_key in [
        ("multiclass_detail_scout", "multiclass_scout"),
        ("multiclass_detail_qwen", "multiclass_qwen"),
        ("multiclass_detail_combo_or", "multiclass_combo_or"),
    ]:
        cm = _multiclass_cm(enriched, pred_key)
        metrics[block_name] = {
            "confusion_gt_rows_pred_cols": cm,
            "per_class_prf": {c: _per_class_prf(cm, c) for c in cm},
        }

    # CSV for manual review
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([
            "frame_path", "ground_truth", "review_flag",
            "rule_v1_scout", "rule_v1_qwen_literal", "rule_v1_qwen_equivalent",
            "scout_open_description", "qwen_open_description",
        ])
        for e in enriched:
            w.writerow([
                e["frame_path"],
                e["ground_truth"],
                e["review_flag"],
                e["rule_v1_scout"],
                e["rule_v1_qwen_literal"],
                e["rule_v1_qwen_equivalent"],
                e["scout_description"].replace("\n", " ").replace("\r", " "),
                e["qwen_description"].replace("\n", " ").replace("\r", " "),
            ])

    combos = metrics["rule_v1_binary_action_vs_rest"]
    combo_keys = [
        "either_literal_OR",
        "both_literal_AND",
        "agreement_literal_both_must_match",
        "either_scout_literal_OR_qwen_equiv",
        "both_scout_literal_AND_qwen_equiv",
        "qwen_equivalent_wide_camera_paraphrase",
        "scout_literal",
    ]
    best_name = max(
        combo_keys,
        key=lambda k: (combos[k]["f1"] if combos[k].get("f1") is not None else -1.0),
    )
    metrics["verdict_sketch"] = {
        "binary_f1_scout_literal": combos["scout_literal"]["f1"],
        "binary_f1_qwen_literal": combos["qwen_literal_substring_wide_field_view"]["f1"],
        "binary_f1_qwen_equivalent_rule": combos["qwen_equivalent_wide_camera_paraphrase"]["f1"],
        "best_binary_strategy_key": best_name,
        "best_binary_f1": combos[best_name].get("f1"),
        "note": (
            "Literal substring 'wide field view' matches Scout's prompt-echo; Qwen paraphrases "
            "('wide view of the cricket field'). Use equivalent rule for fair Qwen v1 intent."
        ),
    }

    OUT_JSON.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
