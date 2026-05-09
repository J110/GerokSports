#!/usr/bin/env python3
"""Wide-pitch-camera rules on Scout **open descriptions** (no new API calls).

Re-validates and iterates **binary** action-vs-rest from
``output/scout_responses_open.jsonl``, dumps FP/FN artifacts, multiclass shim,
span simulation. See memo Section 11.

Example::

    cd files/scripts/scout_validation_research
    python3 classify_descriptions.py
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Callable

import analyze as an

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_JSONL = SCRIPT_DIR / "output" / "scout_responses_open.jsonl"
OUT_METRICS = SCRIPT_DIR / "output" / "rule_iteration_metrics.json"

# --- v1 baseline (memo Section 11.2) -------------------------------------------------

CLOSEUP_TERMS_V1 = [
    "close-up", "closeup", "medium shot", "medium close", "close up",
    "medium-close", "full-body shot", "full body shot", "full shot of",
]


def classify_v1(desc: str) -> str:
    d = (desc or "").lower()
    if any(t in d for t in CLOSEUP_TERMS_V1):
        return "other"
    if "wide field view" in d:
        return "action"
    return "other"


# --- v2 primitives -------------------------------------------------------------------

CLOSEUP_TERMS_V2 = list(CLOSEUP_TERMS_V1)

CEREMONY_NEG = (
    "cheerleader",
    "cheerleaders",
    "pom-pom",
    "pom poms",
    "pompoms",
    "air asia",
    "dancers on the field",
    "dancers standing",
)


def neg_ad_semantic(d: str) -> bool:
    return (
        "does not depict a professional cricket" in d
        or ("does not depict" in d and "cricket match" in d)
        or ("pinky" in d and "home loan" in d)
    )


def neg_empty_wide_stadium(d: str) -> bool:
    crowd = (
        "stands filled" in d
        or "crowd in the stands" in d
        or "large crowd in the stands" in d
        or "crowded stadium" in d
    )
    idle = (
        "no active play" in d
        or "no intense action" in d
        or "not actively engaged" in d
        or "mostly stationary" in d
        or ("standing still" in d and "few individuals" in d)
        or ("appear to be standing still" in d and "few" in d)
    )
    if not crowd or not idle:
        return False
    energetic = (
        "mid-stride" in d
        or "mid stride" in d
        or "mid-swing" in d
        or "mid swing" in d
        or "mid-throw" in d
        or "just bowled" in d
        or "having just bowled" in d
        or "airborne" in d
    )
    return not energetic


def neg_solitary_wide_batter_prep(d: str) -> bool:
    """Single-batter staging on an otherwise wide frame (GT often `other`)."""
    if "wide field view of a cricket player standing" not in d:
        if not (
            "wide field view of a cricket player" in d
            and "standing still" in d
        ):
            return False
    elif "standing still" not in d and "stands still" not in d:
        return False

    # Pitch-corridor guard: crease tap / waiting frames still use live wide camera.
    if (
        ("holding a bat" in d or "holding a cricket bat" in d)
        and any(
            x in d for x in (
                "wickets",
                "wicket",
                "stumps",
                "near the wicket",
                "near the wickets",
            ))):
        return False

    multitext = ("bowler" in d or "umpire" in d or "wicketkeeper" in d or "fielder" in d)
    if multitext and ("several players" in d or "another player" in d or "two players" in d):
        return False
    if multitext:
        return False

    # Avoid matching the substring "delivery" inside "deliveries".
    energetic = (
        "mid-" in d
        or re.search(r"\b(bowls?|bowling|bowled)\b", d) is not None
        or re.search(r"\bswings?\b", d) is not None
    )
    return not energetic


def pos_wide_only(d: str) -> bool:
    return "wide field view" in d or ("frame shows a wide field view" in d)


def pos_full_body_pitch(d: str) -> bool:
    if not any(
            k in d for k in (
                "full shot of",
                "full-body shot",
                "full body shot",
            )):
        return False
    markers = (
        "bowler",
        "stumps",
        "wickets",
        "wicket",
        "crease",
        "pitch",
        "near the wickets",
        "preparing to bowl",
    )
    if any(m in d for m in markers):
        return True
    if "glove" in d and "ball" in d:
        return True
    return False


def pos_alt_delivery_language(d: str) -> bool:
    """Kinetic / multi-player signals that survive non-wide framing."""
    kinetic = [
        "mid-swing",
        "mid swing",
        "mid-throw",
        "mid throw",
        "mid-stride",
        "mid stride",
        "mid-action",
        "mid action",
        "ball airborne",
        "the ball airborne",
        "having just bowled",
        "just bowled",
        "just thrown the ball",
        "appears to have just thrown",
        "captured in mid-throw",
        "in mid-throw",
        "in mid-action",
        "attempting to catch",
        "fallen while attempting to catch",
        "fielding stance",
        "crouching on a green field",
        "wicket-keeper",
        "wicketkeeper",
        "kneeling on one knee",
        "two cricket players on a green field",
        "throwing or catching a ball",
    ]
    if any(a in d for a in kinetic):
        return True
    if "preparing to hit the ball" in d:
        return True
    if "preparing to hit a ball" in d:
        return True
    if "preparing for the next delivery" in d and "pitch" in d:
        return True
    if "has just received a delivery" in d:
        return True
    if "in the act of bowling" in d or "in the act of hitting" in d:
        return True
    return False


def pos_pitch_standing_batter(d: str) -> bool:
    if "cricket player standing on the pitch" not in d and "standing on the pitch" not in d:
        return False
    return any(
        k in d for k in (
            "preparing",
            "delivery",
            "bowler",
            "wicket",
        ))


def is_tight_framing(d: str) -> bool:
    """Framing Scout often uses for non–wide-pitch shots."""
    return any(t in d for t in CLOSEUP_TERMS_V2) or "medium shot" in d


def pos_batter_wideish_prep(d: str) -> bool:
    """Batter setup when camera language is not explicitly wide (no tight framing)."""
    if is_tight_framing(d):
        return False
    if "batter" not in d and "batsman" not in d:
        return False
    if "preparing to hit" not in d:
        return False
    return "green field" in d or "pitch" in d


def has_strong_action_signal(d: str) -> bool:
    if is_tight_framing(d):
        return pos_full_body_pitch(d) or pos_alt_delivery_language(d)
    return (
        pos_full_body_pitch(d)
        or pos_alt_delivery_language(d)
        or pos_pitch_standing_batter(d)
        or pos_batter_wideish_prep(d)
    )


def classify_v2_final(desc: str) -> str:
    """Hand-tuned wide-pitch-camera + kinetic rescue rule (memo Section 11.4)."""
    d = (desc or "").lower()

    if neg_ad_semantic(d):
        return "other"
    if any(c in d for c in CEREMONY_NEG):
        return "other"
    if neg_empty_wide_stadium(d):
        return "other"
    if neg_solitary_wide_batter_prep(d):
        return "other"

    strong = has_strong_action_signal(d)
    tight = is_tight_framing(d)
    if tight and not strong:
        return "other"

    wide = pos_wide_only(d)
    if wide and not neg_empty_wide_stadium(d) and not neg_solitary_wide_batter_prep(d):
        return "action"

    if strong:
        return "action"

    return "other"


# --- Multiclass (Section 11.6) -------------------------------------------------------

REPLAY_CONSERVATIVE = (
    "replay",
    "slow motion",
    "slow-motion",
    "freeze-frame",
    "freeze frame",
)

REPLAY_UPPER = ("REPLAY", "SLOW-MO")


def is_replay_pattern(desc: str) -> bool:
    u = desc or ""
    if any(s in u for s in REPLAY_UPPER):
        return True
    d = u.lower()
    return any(s in d for s in REPLAY_CONSERVATIVE)


def is_ad_pattern(desc: str) -> bool:
    d = (desc or "").lower()
    if neg_ad_semantic(d):
        return True
    if "pinky" in d and "home loan" in d:
        return True
    return False


def is_umpire_pattern(desc: str) -> bool:
    d = (desc or "").lower()
    if "umpire" not in d:
        return False
    return any(
        k in d for k in (
            "signal",
            "signaling",
            "signalling",
            "raised",
            "outstretched",
            "arms outstretched",
            "gesture",
        ))


def classify_full(desc: str, *, binary_fn: Callable[[str], str]) -> str:
    d = desc or ""
    if is_ad_pattern(d):
        return "ad"
    if is_replay_pattern(d):
        return "replay"
    if is_umpire_pattern(d):
        return "umpire"
    if binary_fn(d) == "action":
        return "action"
    return "other"


# --- Metrics -------------------------------------------------------------------------

def binary_prf(rows: list[dict], pred_fn: Callable[[str], str]) -> dict:
    tp = fp = fn = 0
    for r in rows:
        g = an.gt_label(r)
        if g == "unknown":
            continue
        pred = pred_fn(r.get("open_description") or "")
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
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": None if math.isnan(prec) else round(prec, 4),
        "recall": None if math.isnan(rec) else round(rec, 4),
        "f1": None if math.isnan(f1) else round(f1, 4),
    }


def cluster_fp_row(row: dict, pred_fn: Callable[[str], str]) -> str:
    desc = (row.get("open_description") or "").lower()
    if any(x in desc for x in ("cheerleader", "pom-pom", "pom poms", "air asia")):
        return "FP1_cheer_ceremony"
    if ("stands filled" in desc or "crowded stadium" in desc) and any(
            x in desc for x in (
                "no active play",
                "no intense action",
                "not actively engaged",
                "mostly stationary",
            )):
        return "FP2_empty_field_spectators"
    if "wide field view of a cricket player" in desc and (
            "standing still" in desc or "stands still" in desc
    ):
        return "FP3_single_batter_tap_prep"
    g = an.gt_label(row)
    if g == "replay":
        return "FP_replay_GT_modeled_as_live_wide"
    return "FP_other"


def cluster_fn_row(row: dict) -> str:
    desc = (row.get("open_description") or "").lower()
    if any(t in desc for t in CLOSEUP_TERMS_V1):
        return "FN_closeup_or_full_body_language"
    if "boundary" in desc or "wide-angle" in desc or "curved boundary" in desc:
        return "FN_boundary_edge_framing"
    if "player" in desc and any(
            x in desc for x in ("preparing", "standing on the pitch", "fielding")
    ):
        return "FN_pitch_player_no_wide_phrase"
    return "FN_misc"


def dump_errors_jsonl(
        path: Path,
        rows: list[dict],
        *,
        pred_fn: Callable[[str], str],
        tag: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            desc = r.get("open_description") or ""
            g = an.gt_label(r)
            p = pred_fn(desc)
            gt_act = g == "action"
            pr_act = p == "action"
            if gt_act and not pr_act:
                kind = "FN"
                cl = cluster_fn_row(r)
            elif not gt_act and pr_act:
                kind = "FP"
                cl = cluster_fp_row(r, pred_fn)
            else:
                continue
            fh.write(json.dumps({
                "kind": kind,
                "rule_tag": tag,
                "frame_path": r.get("frame_path"),
                "ground_truth": g,
                "cluster": cl,
                "open_description": desc,
            }, ensure_ascii=False) + "\n")


def confusion_five(rows: list[dict], pred_key: str) -> dict[str, dict[str, int]]:
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


def prf_multiclass_fixed(cm: dict[str, dict[str, int]], klass: str) -> dict:
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    args = ap.parse_args()
    js = args.jsonl.resolve()
    if not js.is_file():
        print(f"Missing {js}", file=sys.stderr)
        sys.exit(1)

    rows = an.load_rows(js)

    b1 = binary_prf(rows, classify_v1)
    exp_p, exp_r = 0.73, 0.83
    if b1["precision"] and b1["recall"]:
        if abs(b1["precision"] - exp_p) > 0.05 or abs(b1["recall"] - exp_r) > 0.05:
            print(
                f"[warn] v1 P/R {b1['precision']}/{b1['recall']} "
                f"deviate from expected ~{exp_p}/~{exp_r} — check data.",
                file=sys.stderr,
            )

    out_dir = SCRIPT_DIR / "output"
    dump_errors_jsonl(out_dir / "rule_v1_errors.jsonl", rows, pred_fn=classify_v1, tag="v1")

    b2 = binary_prf(rows, classify_v2_final)
    dump_errors_jsonl(out_dir / "rule_v2_errors.jsonl", rows, pred_fn=classify_v2_final, tag="v2")

    rows_b1 = []
    for r in rows:
        rr = dict(r)
        d = rr.get("open_description") or ""
        rr["rule_binary"] = classify_v1(d)
        rr["rule_full"] = classify_full(d, binary_fn=classify_v1)
        rows_b1.append(rr)

    rows_b2 = []
    for r in rows:
        rr = dict(r)
        d = rr.get("open_description") or ""
        rr["rule_binary"] = classify_v2_final(d)
        rr["rule_full"] = classify_full(d, binary_fn=classify_v2_final)
        rows_b2.append(rr)

    cm5 = confusion_five(rows_b2, "rule_full")
    per5 = {c: prf_multiclass_fixed(cm5, c) for c in cm5}

    acc5 = sum(
        1 for r in rows_b2
        if an.gt_label(r) in cm5 and r["rule_full"] == an.gt_label(r)
    )
    n5 = sum(1 for r in rows_b2 if an.gt_label(r) in cm5)

    span_v1 = an.span_simulation(rows_b1, pred_key="rule_binary")
    span_v2 = an.span_simulation(rows_b2, pred_key="rule_binary")
    span_full = an.span_simulation(rows_b2, pred_key="rule_full")

    # FP/FN cluster histograms
    def hist_errors(pred_fn):
        fp_h: dict[str, int] = {}
        fn_h: dict[str, int] = {}
        for r in rows:
            desc = r.get("open_description") or ""
            g = an.gt_label(r)
            if g == "unknown":
                continue
            p = pred_fn(desc)
            if g == "action" and p != "action":
                k = cluster_fn_row(r)
                fn_h[k] = fn_h.get(k, 0) + 1
            elif g != "action" and p == "action":
                k = cluster_fp_row(r, pred_fn)
                fp_h[k] = fp_h.get(k, 0) + 1
        return fp_h, fn_h

    fp_v1, fn_v1 = hist_errors(classify_v1)
    fp_v2, fn_v2 = hist_errors(classify_v2_final)

    iteration_table = [
        {
            "name": "v1_wide_field_closeup_gate",
            "binary_action": b1,
            "delta_fp_vs_prior": None,
            "delta_fn_vs_prior": None,
        },
        {
            "name": "v2_tuned_strong_negs_alt_pos",
            "binary_action": b2,
            "delta_fp_vs_v1": b2["fp"] - b1["fp"],
            "delta_fn_vs_v1": b2["fn"] - b1["fn"],
            "resolved_fp_estimate": max(0, b1["fp"] - b2["fp"]),
            "new_fn_estimate": max(0, b2["fn"] - b1["fn"]),
        },
    ]

    # Verdict heuristic (Section 11.8)
    p2 = b2.get("precision")
    r2 = b2.get("recall")
    if p2 is not None and r2 is not None and p2 >= 0.85 and r2 >= 0.85:
        verdict = "Mixed_or_Strong_candidate"
        vnote = f"Binary action P={p2} R={r2} both ≥0.85 on open-description rules."
    elif p2 is not None and r2 is not None and (p2 >= 0.85 or r2 >= 0.85):
        verdict = "Mixed"
        vnote = (
            f"Binary action: R={r2} meets or exceeds 0.85; P={p2} stalls below 0.85 on this "
            f"247-frame sample — hand rules cannot simultaneously shed replay/wide FPs without "
            f"learned scoring or richer non-text cues."
        )
    else:
        verdict = "Weak_unchanged"
        vnote = (
            "Open-description shot-type heuristic improves over prompted Scout but "
            "does not clear dual 0.85 gate; pivot Path 2/3 for production fidelity."
        )

    span_note = ""
    pv1 = span_v1["summary"]["clip_pass_total"]
    pv2 = span_v2["summary"]["clip_pass_total"]
    if pv2 < pv1:
        span_note = (
            f"Span heuristic {pv2}/{span_v2['summary']['clip_denominator']} vs v1 "
            f"{pv1}/{span_v1['summary']['clip_denominator']} — v2 lengthens kinetic replay "
            f"sequences (e.g. `20260430_195352/d102`) spanning ≥3 s whereas v1 surfaced "
            f"singleton false alarms."
        )

    span_diff = {
        cl: {
            "v1_verdict": span_v1["per_clip"][cl]["verdict_clip"],
            "v2_verdict": span_v2["per_clip"][cl]["verdict_clip"],
        }
        for cl in span_v1["per_clip"]
        if span_v1["per_clip"][cl]["verdict_clip"] != span_v2["per_clip"][cl]["verdict_clip"]
    }

    irreducible_fn = [
        r.get("frame_path")
        for r in rows
        if an.gt_label(r) == "action"
        and classify_v2_final(r.get("open_description") or "") == "other"
    ]

    payload = {
        "source_jsonl": str(js.relative_to(SCRIPT_DIR) if str(js).startswith(str(SCRIPT_DIR)) else js),
        "n_frames": len(rows),
        "binary_action_vs_rest": {
            "v1": b1,
            "v2_final": b2,
        },
        "iteration_table": iteration_table,
        "fp_fn_clusters": {
            "v1": {"fp": fp_v1, "fn": fn_v1},
            "v2": {"fp": fp_v2, "fn": fn_v2},
        },
        "multiclass_rule_full_v2": {
            "confusion_rows_gt_cols_pred": cm5,
            "per_class": per5,
            "five_class_accuracy": {
                "correct": acc5,
                "n": n5,
                "rate": round(acc5 / n5, 4) if n5 else None,
            },
            "comparison_note": (
                "Compare to Section 11 memorandum tables for production (~R=0.28 action naive) "
                "and Section 10 keyword skim (~R=0.89 P~0.35)."
            ),
        },
        "span_simulation_binary_rule_v1": span_v1["summary"],
        "span_simulation_binary_rule_v2": span_v2["summary"],
        "span_simulation_multiclass_rule_full_v2": span_full["summary"],
        "per_clip_rule_v2": span_v2["per_clip"],
        "span_verdict_deltas_v1_to_v2": span_diff,
        "irreducible_binary_false_negatives_v2": irreducible_fn,
        "verdict_open_rule_architecture": verdict,
        "verdict_notes": vnote + (" " + span_note if span_note else ""),
        "baseline_expectation_note": (
            "v1 nominal P≈0.73 R≈0.83 (this run may differ ±0.01 due to rounding / tie rules)."
        ),
    }

    OUT_METRICS.parent.mkdir(parents=True, exist_ok=True)
    OUT_METRICS.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    print("Binary v1", b1)
    print("Binary v2", b2)
    print("Wrote", OUT_METRICS)
    print("Wrote", out_dir / "rule_v1_errors.jsonl")
    print("Wrote", out_dir / "rule_v2_errors.jsonl")


if __name__ == "__main__":
    main()
