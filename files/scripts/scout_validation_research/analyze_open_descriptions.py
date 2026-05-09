#!/usr/bin/env python3
"""N-gram + discriminator + naive keyword classifier on open Scout descriptions.

Reads ``output/scout_responses_open.jsonl``.
Writes:
  - ``output/description_ngrams_by_class.json``
  - ``output/keyword_classifier_metrics.json``
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable, Iterable

import analyze as an

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OPEN_JSONL = SCRIPT_DIR / "output" / "scout_responses_open.jsonl"
OUT_NGRAMS = SCRIPT_DIR / "output" / "description_ngrams_by_class.json"
OUT_KEYWORD = SCRIPT_DIR / "output" / "keyword_classifier_metrics.json"

STOPWORDS = frozenset("""
a an the and or but if in on at to for of as is was are were be been being
it its this that these those with from by about into through during before
after above below between under again further then once here there when where
why how all each both few more most other some such no nor not only own same
so than too very can will just don should now
i you he she we they me him her us them my your our their what which who whom
whom whose
""".split())

_TOKEN_RE = re.compile(r"[a-z0-9']+", re.IGNORECASE)

# Naive lexicon (diagnostic baseline — intentionally limited).
ACTION_WORDS = frozenset({
    "bowler", "bowlers", "bowling", "batsman", "batter", "batting",
    "delivery", "deliveries", "stride", "runup", "run", "running",
    "released", "releasing", "flight", "stumps", "creases", "umpiring",
})

# Naive lexicon — ad branch kept **narrow**: live IPL frames often legitimately mention
# sponsor overlays; broad tokens like ``logo``/``sponsor`` create mass false positives.
AD_PHRASES = (
    "commercial break",
    "television advertisement",
    "during a commercial",
    "full-screen advertisement",
)
AD_BRANDS = frozenset({
    "dream11",
    "vivo",
    "rupeeplay",
})

REPLAY_UPPER_SUBSTRINGS = frozenset({
    "REPLAY",
    "SLOW-MO",
    "SLOWMO",
})


def normalize_text(raw: str) -> str:
    s = raw.lower().replace("-", " ").replace("—", " ")
    return s


def tokenize_words(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(normalize_text(text)) if len(t) > 1]


def filtered_tokens(text: str) -> list[str]:
    return [t for t in tokenize_words(text) if t not in STOPWORDS]


def ngrams_from_tokens(tokens: list[str], n: int) -> list[str]:
    if len(tokens) < n:
        return []
    out = []
    for i in range(len(tokens) - n + 1):
        out.append(" ".join(tokens[i : i + n]))
    return out


def classify_keyword(desc: str) -> str:
    if not desc or not desc.strip():
        return "other"
    u = desc.upper()
    lo = normalize_text(desc)
    for rub in REPLAY_UPPER_SUBSTRINGS:
        if rub in u:
            return "replay"
    if "slow motion" in lo:
        return "replay"
    for ph in AD_PHRASES:
        if ph in lo:
            return "ad"
    for b in AD_BRANDS:
        if b in lo:
            return "ad"
    if "umpire" in lo and (
        "signal" in lo or "signaling" in lo or "signalling" in lo
        or "raised" in lo or "gesture" in lo
    ):
        return "umpire"
    toks = set(tokenize_words(desc))
    if toks & ACTION_WORDS:
        return "action"
    return "other"


def confusion_and_prf(
        rows: list[dict],
        pred_fn,
) -> tuple[dict, dict]:
    labs = ["action", "replay", "ad", "other", "umpire"]
    cm = {g: defaultdict(int) for g in labs}
    for r in rows:
        gt = an.gt_label(r)
        if gt not in labs:
            continue
        pred = pred_fn(r.get("open_description") or "")
        if pred not in labs:
            pred = "other"
        cm[gt][pred] += 1

    def prf(klass: str) -> dict:
        tp = cm[klass][klass]
        fp = sum(cm[g][klass] for g in labs if g != klass)
        fn = sum(cm[klass][p] for p in labs if p != klass)
        p = tp / (tp + fp) if (tp + fp) else None
        rec = tp / (tp + fn) if (tp + fn) else None
        f1 = (
            (2 * p * rec / (p + rec))
            if p is not None and rec is not None and (p + rec) > 0
            else None
        )
        return {"precision": p, "recall": rec, "f1": f1}

    nested = {g: dict(cm[g]) for g in labs}
    per = {lab: prf(lab) for lab in labs}
    return nested, per


def top_counter(c: Counter, k: int) -> list[tuple[str, int]]:
    return [(a, int(b)) for a, b in c.most_common(k)]


def discriminative_tokens(
        class_tokens: dict[str, Counter],
        *,
        top_k: int,
        min_in_class: int,
) -> dict[str, list[dict]]:
    """Log-ratio style: enrichment of token t in class c vs rest."""
    totals = {c: sum(cnt.values()) for c, cnt in class_tokens.items()}
    all_vocab = Counter()
    for cnt in class_tokens.values():
        all_vocab.update(cnt)
    combined = sum(totals.values()) or 1

    report: dict[str, list[dict]] = {}
    for cname, cnt in class_tokens.items():
        rows: list[tuple[float, str, dict]] = []
        t_c = totals[cname] or 1
        t_not = combined - t_c or 1
        for tok, f in cnt.items():
            if f < min_in_class:
                continue
            f_not = max(0, all_vocab[tok] - f)
            p_in = (f + 1) / (t_c + len(cnt) + 1)
            p_out = (f_not + 1) / (t_not + 1)
            score = math.log(p_in / p_out)
            # PMI-ish on presence in random token draw
            rows.append((score, tok, {"count_in_class": f, "log_ratio": score}))
        rows.sort(key=lambda x: -x[0])
        report[cname] = [
            {"term": tok, **meta}
            for _, tok, meta in rows[:top_k]
        ]
    return report


def discriminator_rules(
        rows: list[dict],
        signals: Iterable[tuple[str, str, Callable[[str], bool]]],
) -> list[dict]:
    """callable(desc) -> bool if signal fires."""
    labs = frozenset({"action", "replay", "ad", "other", "umpire"})
    out = []
    n = sum(1 for r in rows if an.gt_label(r) in labs)
    for sig_name, target_gt, detector in signals:
        tp = fp = fn = tn = 0
        for r in rows:
            gt = an.gt_label(r)
            if gt not in labs:
                continue
            desc = r.get("open_description") or ""
            hit = bool(detector(desc))
            pos = gt == target_gt
            if hit and pos:
                tp += 1
            elif hit and not pos:
                fp += 1
            elif not hit and pos:
                fn += 1
            else:
                tn += 1
        tpr = tp / (tp + fn) if (tp + fn) else None
        fpr = fp / (fp + tn) if (fp + tn) else None
        # accuracy as multiclass hinge: predicting target if fires else "not target"
        out.append({
            "signal": sig_name,
            "target_ground_truth": target_gt,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "n_eval_frames": tp + fp + fn + tn,
            "true_positive_rate": tpr,
            "false_positive_rate": fpr,
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jsonl", type=Path, default=DEFAULT_OPEN_JSONL)
    args = ap.parse_args()

    path = args.jsonl.resolve()
    if not path.is_file():
        print(f"No {path} — run run_scout_open.py first.", file=sys.stderr)
        raise SystemExit(2)

    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    labs = frozenset({"action", "replay", "ad", "other", "umpire"})
    by_class_desc: dict[str, list[str]] = defaultdict(list)
    samples_by_class: dict[str, list[dict[str, str]]] = defaultdict(list)

    for r in sorted(rows, key=lambda x: x.get("frame_path", "")):
        gt = an.gt_label(r)
        desc = (r.get("open_description") or "").strip()
        rec = {"frame_path": r.get("frame_path", ""), "description": desc}
        if gt in labs:
            by_class_desc[gt].append(desc)
            if len(samples_by_class[gt]) < 10 and desc:
                samples_by_class[gt].append(rec)

    # Fill short classes up to 10 best-effort (allow blanks noted)
    for gt in labs:
        if len(samples_by_class[gt]) < 10:
            for r in rows:
                if an.gt_label(r) != gt:
                    continue
                if len(samples_by_class[gt]) >= 10:
                    break
                d = (r.get("open_description") or "").strip()
                fps = [x["frame_path"] for x in samples_by_class[gt]]
                if r.get("frame_path") not in fps:
                    samples_by_class[gt].append({
                        "frame_path": r.get("frame_path", ""),
                        "description": d,
                    })

    class_tokens: dict[str, Counter] = {}
    gram1: dict[str, Counter] = {}
    gram2: dict[str, Counter] = {}
    gram3: dict[str, Counter] = {}
    len_stats: dict[str, dict] = {}

    for cname in sorted(labs):
        texts = by_class_desc.get(cname, [])
        ctr = Counter()
        g2 = Counter()
        g3 = Counter()
        lengths = [len(t) for t in texts if t.strip()]
        for t in texts:
            fts = filtered_tokens(t)
            ctr.update(fts)
            toks_full = tokenize_words(t)
            for ng in ngrams_from_tokens(filtered_tokens(t), 2):
                g2[ng] += 1
            for ng in ngrams_from_tokens(fts, 3):
                g3[ng] += 1
        class_tokens[cname] = ctr
        gram1[cname] = ctr.copy()
        gram2[cname] = g2
        gram3[cname] = g3
        len_stats[cname] = {}
        if lengths:
            len_stats[cname] = {
                "n": len(lengths),
                "mean_chars": statistics.mean(lengths),
                "median_chars": statistics.median(lengths),
                "min_chars": min(lengths),
                "max_chars": max(lengths),
            }
        else:
            len_stats[cname] = {"n": 0}

    repeats = Counter()
    for r in rows:
        d = (r.get("open_description") or "").strip()
        if d:
            repeats[d.lower()] += 1
    duplicated_templates = [(t, c) for t, c in repeats.items() if c >= 4]

    def _has_slow(d: str) -> bool:
        lo = normalize_text(d)
        return "slow" in lo and "motion" in lo

    def _has_running_bowler(d: str) -> bool:
        lo = normalize_text(d)
        return ("bowler" in lo or "bowling" in lo) and "running" in lo

    def _replay_graphic_u(d: str) -> bool:
        return "REPLAY" in d.upper()

    def _umpire_sig(d: str) -> bool:
        lo = normalize_text(d)
        return "umpire" in lo and (
            "signal" in lo or "raised" in lo or "finger" in lo
        )

    rule_rows = discriminator_rules(rows, (
        ("word_replay_upper", "replay", lambda d: _replay_graphic_u(d)),
        ("phrase_slow_motion", "replay", lambda d: _has_slow(d)),
        ("running_bowler_language", "action", lambda d: _has_running_bowler(d)),
        ("umpire_signal_language", "umpire", lambda d: _umpire_sig(d)),
        ("ad_commercial_any", "ad",
         lambda d: any(ph in normalize_text(d) for ph in AD_PHRASES)
         or any(b in normalize_text(d) for b in AD_BRANDS)),
    ))

    disc = discriminative_tokens(class_tokens, top_k=40, min_in_class=2)

    ngram_bundle = {}
    top_n = 30
    for cname in sorted(labs):
        ngram_bundle[cname] = {
            "1grams_top": top_counter(gram1[cname], top_n),
            "2grams_top": top_counter(gram2[cname], top_n),
            "3grams_top": top_counter(gram3[cname], max(15, top_n // 2)),
            "discriminative_log_ratio_terms": disc.get(cname, []),
            "description_lengths": len_stats.get(cname, {}),
            "verbatim_samples": samples_by_class.get(cname, []),
        }

    OUT_NGRAMS.parent.mkdir(parents=True, exist_ok=True)
    dup_report = sorted(duplicated_templates, key=lambda x: -x[1])[:15]

    try:
        rel_jsonl = str(path.relative_to(SCRIPT_DIR))
    except ValueError:
        rel_jsonl = str(path)

    full_ngram_payload = {
        "source_jsonl": rel_jsonl,
        "n_frames_total": len(rows),
        "n_frames_by_gt_class": {c: sum(1 for r in rows if an.gt_label(r) == c) for c in sorted(labs)},
        "duplicate_description_strings_ge4": dup_report,
        "per_class": ngram_bundle,
        "candidate_signal_evaluation": rule_rows,
    }
    OUT_NGRAMS.write_text(json.dumps(full_ngram_payload, indent=2, ensure_ascii=False) + "\n")

    nested, per_kw = confusion_and_prf(rows, classify_keyword)

    labs_eval = labs
    n_eval_kw = sum(1 for r in rows if an.gt_label(r) in labs_eval)
    n_correct_kw = sum(
        1 for r in rows
        if an.gt_label(r) in labs_eval
        and classify_keyword(r.get("open_description") or "") == an.gt_label(r)
    )
    overall_kw = n_correct_kw / n_eval_kw if n_eval_kw else None
    baseline_prod = {"action_pr": {"precision": 0.7692, "recall": 0.2778}}
    baseline_focused = {"action_pr": {"precision": 0.5333, "recall": 0.1111}}

    kw_action = per_kw["action"]

    vague_short = (
        sum(
            1 for r in rows
            if an.gt_label(r) in labs and len((r.get("open_description") or "").strip()) < 30
        )
        / max(1, sum(1 for r in rows if an.gt_label(r) in labs))
    )

    act_rec_kw = kw_action["recall"] if kw_action["recall"] is not None else 0.0
    act_pre_kw = kw_action["precision"] if kw_action["precision"] is not None else 0.0

    max_lr_action = disc.get("action", [{}])[0].get("log_ratio", -99.0) if disc.get("action") else -99.0
    max_lr_other = disc.get("other", [{}])[0].get("log_ratio", -99.0) if disc.get("other") else -99.0
    lexical_peak = max(max_lr_action, max_lr_other)

    prod_r_action = baseline_prod["action_pr"]["recall"]
    prod_prec_action = baseline_prod["action_pr"]["precision"]
    prod_f1_action = (
        (2 * prod_prec_action * prod_r_action / (prod_prec_action + prod_r_action))
        if prod_prec_action and prod_r_action
        else 0.0
    )

    kw_f1 = kw_action["f1"] if kw_action.get("f1") is not None else 0.0

    foc_r_action = baseline_focused["action_pr"]["recall"]
    tmpl_heavy = bool(dup_report and dup_report[0][1] >= max(8, len(rows) // 35))

    # Perception ordinal (see memo Section 10.5): 1=strong lexical signal,
    # 2=partial, 3=mostly generic — informed by lexical recall vs prompted baselines.
    rationale: list[str] = []
    if vague_short > 0.08:
        rationale.append(f"Vague-short fraction (<30 chars): {vague_short:.3f}")

    ordinal = 2
    code = "partial_overlap_language"

    if tmpl_heavy and act_rec_kw < prod_r_action + 0.05:
        ordinal = 3
        code = "template_or_repetitive_descriptions"
        rationale.append(f"Highly duplicated description strings ({dup_report[0][1]} copies)")
    elif act_rec_kw < foc_r_action and lexical_peak < 0.45:
        ordinal = 3
        code = "weak_lexical_separator"
        rationale.append(
            f"Lexical-keyword action recall {act_rec_kw:.3f} below focused prompted "
            f"recall ({foc_r_action:.3f}) with modest δ log-ratio enrichment ({lexical_peak:.2f}).",
        )
    elif (
        act_rec_kw >= prod_r_action
        and lexical_peak > 0.5
        and act_pre_kw >= 0.55
        and kw_f1 >= prod_f1_action - 1e-6
    ):
        ordinal = 1
        code = "lexical_signals_match_or_exceed_prod_prompt_action_recall"
        rationale.append(
            f"Lexical heuristic improves both recall ({act_rec_kw:.3f} vs {prod_r_action:.3f}) "
            f"and class-F1 ({kw_f1:.3f} vs {prod_f1_action:.3f}) with precision {act_pre_kw:.3f} "
            f"and enrichment peak {lexical_peak:.2f}.",
        )
    elif act_rec_kw >= prod_r_action + 0.05 and act_pre_kw < min(0.5, prod_prec_action - 0.15):
        ordinal = 2
        code = "mixed_recall_but_prompt_language_bleed"
        rationale.append(
            f"Recall improves to {act_rec_kw:.3f} vs production {prod_r_action:.3f}, but "
            f"precision collapses ({act_pre_kw:.3f} vs {prod_prec_action:.3f}) — prompt-echo vocabulary "
            f"(e.g., deliveries, between play rhetoric) spills across GT other frames.",
        )
    elif prod_r_action - 0.05 <= act_rec_kw < prod_r_action + 0.05 or lexical_peak > 0.35:
        ordinal = 2
        code = "partial_overlap_language"
        rationale.append(
            f"Action recall lexical {act_rec_kw:.3f}; precision {act_pre_kw:.3f}; "
            f"log-ratio enrichment peak {lexical_peak:.2f}; keyword-F1 {kw_f1:.3f} vs "
            f"production-mapped-F1 {prod_f1_action:.3f}.",
        )
    else:
        ordinal = 3
        code = "underperforms_relative_to_baselines"
        rationale.append(f"Recall {act_rec_kw:.3f} without compensating lexical lift ({lexical_peak:.2f}).")

    keyword_payload = {
        **{
            "keyword_action_f1": kw_f1,
            "production_mapped_action_f1": prod_f1_action,
            "overall_five_class_exact_match_naive_keyword": {
                "correct": n_correct_kw,
                "n": n_eval_kw,
                "rate": overall_kw,
            },
        },
        "keyword_classifier_note": (
            "Order: replay(upper overlays) → tight ad phrases/brands → "
            "umpire(umpire+signal) → action(ACTION_WORDS) → other."
        ),
        "ACTION_WORDS_sorted": sorted(ACTION_WORDS),
        "AD_BRANCH": {
            "phrases": AD_PHRASES,
            "brand_substrings_sorted": sorted(AD_BRANDS),
        },
        "confusion_matrix_naive_keyword": nested,
        "per_class_naive_keyword": per_kw,
        "baselines_from_prior_runs_action_class": {
            "production_naive_mapper": baseline_prod["action_pr"],
            "focused_single_task_prompt": baseline_focused["action_pr"],
            "keyword_open_description": {
                "precision": kw_action["precision"],
                "recall": kw_action["recall"],
            },
        },
        "perception_verdict_codes": {
            "ordinal_plain": ordinal,
            "code": code,
            "notes": rationale,
            "signals": {
                "vague_short_fraction": vague_short,
                "lexical_log_ratio_peak": lexical_peak,
                "keyword_action_recall": act_rec_kw,
                "keyword_action_precision": act_pre_kw,
            },
        },
        "memo_hooks": {"duplicate_templates": dup_report[:5]},
    }

    OUT_KEYWORD.write_text(json.dumps(keyword_payload, indent=2, ensure_ascii=False) + "\n")

    print(f"Wrote {OUT_NGRAMS}")
    print(f"Wrote {OUT_KEYWORD}")
    print(
        "Keyword action recall=",
        None if kw_action["recall"] is None else f"{kw_action['recall']:.3f}",
        "precision=",
        None if kw_action["precision"] is None else f"{kw_action['precision']:.3f}",
    )


if __name__ == "__main__":
    main()
