#!/usr/bin/env python3
"""Analyze results.csv from run_prompts.py.

For each prompt, prints:
  - confusion matrix (predicted answer x truth label)
  - per-class accuracy / discrimination signal
  - examples of correct and wrong classifications
  - KEEP / DROP recommendation

Output: analysis.txt (also stdout).

Usage:
    cd files/scripts/broadcast_mode_tuning/prompt_experiment
    python3 analyze_results.py
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
RESULTS_CSV = SCRIPT_DIR / "results.csv"
ANALYSIS_TXT = SCRIPT_DIR / "analysis.txt"

TRUTHS = ["real", "replay_overlay", "replay_action", "pre", "post"]

# Mapping of "ideal" parsed answer per truth label, per prompt.
# A prompt is rated by how strongly each truth class concentrates on
# its ideal answer (or any answer distinct from the other classes').
IDEAL = {
    "P1_binary": {
        "real": "LIVE",
        "replay_overlay": "REPLAY",
        "replay_action": "REPLAY",
        "pre": "LIVE",
        "post": "LIVE",
    },
    "P2_scene": {
        "real": "DELIVERY",
        "replay_overlay": "REPLAY",
        "replay_action": "REPLAY",
        "pre": "BETWEEN_DELIVERIES",
        "post": "BETWEEN_DELIVERIES",
    },
    "P4_camera": {
        "real": "BOWLERS_END_WIDE",
        "replay_overlay": "GRAPHIC",
        "replay_action": "REPLAY_CUT",
        "pre": "BOWLERS_END_WIDE",
        "post": "BOWLERS_END_WIDE",
    },
    "P5_anchor": {
        "real": "YES",
        "replay_overlay": "NO",
        "replay_action": "NO",
        "pre": "YES",
        "post": "NO",
    },
}


def load_rows() -> list[dict[str, str]]:
    with RESULTS_CSV.open() as f:
        return list(csv.DictReader(f))


def fmt_matrix(rows_for_prompt: list[dict[str, str]]) -> tuple[str, dict]:
    # truth -> Counter(predicted)
    counts: dict[str, dict[str, int]] = {t: defaultdict(int) for t in TRUTHS}
    all_preds: set[str] = set()
    for r in rows_for_prompt:
        truth = r["truth_label"]
        pred = r["parsed_answer"]
        counts[truth][pred] += 1
        all_preds.add(pred)
    preds_sorted = sorted(all_preds)

    col_w = max(8, max((len(p) for p in preds_sorted), default=8) + 1)
    head = f"{'truth':<18s}" + "".join(f"{p:>{col_w}s}" for p in preds_sorted)
    lines = [head, "-" * len(head)]
    for t in TRUTHS:
        row = f"{t:<18s}"
        for p in preds_sorted:
            n = counts[t].get(p, 0)
            row += f"{n:>{col_w}d}"
        lines.append(row)
    return "\n".join(lines), counts


def discrimination_score(prompt_id: str, counts: dict) -> tuple[float, list[str]]:
    """How distinguishable are the truth classes by their answer
    distribution?

    Score = mean over truth pairs of total-variation distance between
    their predicted-answer distributions.  Range 0 (indistinguishable)
    to 1 (perfectly separated).  Bonus heuristic: per-truth accuracy
    against IDEAL when defined.
    """
    truths = list(counts.keys())
    # build per-truth probability vectors over union of preds
    preds = sorted({p for t in truths for p in counts[t]})
    dists = {}
    for t in truths:
        total = sum(counts[t].values())
        if total == 0:
            dists[t] = {p: 0.0 for p in preds}
        else:
            dists[t] = {p: counts[t].get(p, 0) / total for p in preds}
    pairs = []
    for i in range(len(truths)):
        for j in range(i + 1, len(truths)):
            a, b = dists[truths[i]], dists[truths[j]]
            tv = 0.5 * sum(abs(a[p] - b[p]) for p in preds)
            pairs.append(tv)
    sep = sum(pairs) / len(pairs) if pairs else 0.0

    notes = []
    ideal = IDEAL.get(prompt_id)
    if ideal:
        per_truth_acc = {}
        for t in truths:
            total = sum(counts[t].values())
            hit = counts[t].get(ideal[t], 0)
            per_truth_acc[t] = (hit, total)
            pct = (hit / total * 100) if total else 0.0
            notes.append(f"  ideal[{t}]={ideal[t]:<20s} hit "
                         f"{hit}/{total} ({pct:.0f}%)")
    return sep, notes


def examples(rows_for_prompt: list[dict[str, str]],
             prompt_id: str, n: int = 2) -> str:
    ideal = IDEAL.get(prompt_id, {})
    correct: list[str] = []
    wrong: list[str] = []
    for r in rows_for_prompt:
        line = (f"    [{r['truth_label']:<14s}] {r['frame']:<28s} "
                f"-> {r['parsed_answer']}")
        target = ideal.get(r["truth_label"])
        if target is None:
            continue
        if r["parsed_answer"] == target and len(correct) < n:
            correct.append(line)
        elif r["parsed_answer"] != target and len(wrong) < n:
            wrong.append(line)
    out = ["  correct examples:"] + (correct or ["    (none)"])
    out += ["  wrong examples:"] + (wrong or ["    (none)"])
    return "\n".join(out)


def main() -> int:
    rows = load_rows()
    by_prompt: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        by_prompt[r["prompt_id"]].append(r)

    out: list[str] = []
    out.append("Prompt experimentation analysis")
    out.append("=" * 60)
    out.append(f"Total rows: {len(rows)} | prompts: {len(by_prompt)}")
    out.append("")

    rankings: list[tuple[float, str]] = []
    for pid in sorted(by_prompt):
        out.append(f"### {pid}")
        out.append("-" * 60)
        if pid == "P3_checklist":
            # Aggregate per-flag Y rates by truth
            keys = [
                "REPLAY_TAG", "SLO_MO", "ANALYSIS", "BALL_SPEED",
                "CROWD_FOREGROUND", "BOWLER_RELEASING",
                "BATTER_PLAYING", "FIELDER_DIVING",
            ]
            tab: dict[str, dict[str, list[int]]] = {
                t: {k: [] for k in keys} for t in TRUTHS
            }
            for r in by_prompt[pid]:
                truth = r["truth_label"]
                for part in r["parsed_answer"].split(";"):
                    if "=" not in part:
                        continue
                    k, v = part.split("=", 1)
                    if k in tab[truth]:
                        tab[truth][k].append(1 if v == "Y" else 0)
            head = f"{'flag':<18s}" + "".join(f"{t:>16s}" for t in TRUTHS)
            out.append(head)
            out.append("-" * len(head))
            # discrimination = max - min Y-rate across truths per flag
            sep_per_flag = []
            for k in keys:
                row = f"{k:<18s}"
                rates = []
                for t in TRUTHS:
                    arr = tab[t][k]
                    rate = (sum(arr) / len(arr)) if arr else 0.0
                    rates.append(rate)
                    row += f"{rate*100:>15.0f}%"
                out.append(row)
                sep_per_flag.append((max(rates) - min(rates), k))
            sep_per_flag.sort(reverse=True)
            best = sep_per_flag[:4]
            sep = sum(s for s, _ in sep_per_flag) / len(sep_per_flag)
            out.append("")
            out.append(f"  mean per-flag discrimination (max-min Y-rate): "
                       f"{sep:.2f}")
            out.append("  most-discriminating flags: "
                       + ", ".join(f"{k} (Δ={s:.2f})" for s, k in best))
            verdict = ("KEEP" if any(s >= 0.5 for s, _ in sep_per_flag)
                       else "DROP")
            out.append(f"  recommendation: {verdict}")
            rankings.append((sep, pid))
        else:
            mat, counts = fmt_matrix(by_prompt[pid])
            out.append(mat)
            out.append("")
            sep, notes = discrimination_score(pid, counts)
            out.append(f"  mean pair-wise total-variation separation: "
                       f"{sep:.2f}  (1.0 = perfectly distinguishable)")
            out.extend(notes)
            out.append(examples(by_prompt[pid], pid))
            verdict = (
                "KEEP" if sep >= 0.55 else
                "BORDERLINE" if sep >= 0.40 else
                "DROP"
            )
            out.append(f"  recommendation: {verdict}")
            rankings.append((sep, pid))
        out.append("")

    out.append("=" * 60)
    out.append("Summary ranking by discrimination score (higher = better):")
    rankings.sort(reverse=True)
    for sep, pid in rankings:
        out.append(f"  {pid:14s}  sep={sep:.2f}")
    out.append("")
    top = [pid for _, pid in rankings[:3]]
    out.append(f"Top candidates for chunker integration: {', '.join(top)}")

    # ----- decision criterion on real_* timing-corrected fixtures -----
    out.append("")
    out.append("=" * 60)
    out.append("Decision criterion (real_* delivery-moment recall)")
    out.append("-" * 60)

    real_p2 = [r for r in by_prompt.get("P2_scene", [])
               if r["truth_label"] == "real"]
    p2_delivery = sum(1 for r in real_p2 if r["parsed_answer"] == "DELIVERY")
    p2_total = len(real_p2)
    out.append(f"P2 DELIVERY hits on real_*: {p2_delivery}/{p2_total}")
    p2_dist = defaultdict(int)
    for r in real_p2:
        p2_dist[r["parsed_answer"]] += 1
    out.append("  P2 distribution on real_*: "
               + ", ".join(f"{k}={v}" for k, v in sorted(p2_dist.items())))

    real_p3 = [r for r in by_prompt.get("P3_checklist", [])
               if r["truth_label"] == "real"]
    p3_either = 0
    p3_bowler = 0
    p3_batter = 0
    for r in real_p3:
        flags = dict(part.split("=", 1) for part in r["parsed_answer"].split(";")
                     if "=" in part)
        b = flags.get("BOWLER_RELEASING") == "Y"
        s = flags.get("BATTER_PLAYING") == "Y"
        if b:
            p3_bowler += 1
        if s:
            p3_batter += 1
        if b or s:
            p3_either += 1
    out.append(f"P3 BOWLER_RELEASING Y on real_*: {p3_bowler}/{len(real_p3)}")
    out.append(f"P3 BATTER_PLAYING   Y on real_*: {p3_batter}/{len(real_p3)}")
    out.append(f"P3 EITHER (bowler OR batter) on real_*: "
               f"{p3_either}/{len(real_p3)}")

    out.append("")
    if p2_delivery >= 3:
        verdict = ("P2 IS the per-frame primary classifier. "
                   "Integrate into chunker.")
    elif p3_either >= 4:
        verdict = ("P3 checklist alone carries the delivery signal. "
                   "P2 is unreliable even at correct timing. Use P3 only.")
    else:
        verdict = ("Scout cannot reliably identify delivery moments even "
                   "at proper timing with structured prompts. Need to "
                   "investigate further — possibly re-frame the prompt "
                   "around what Scout CAN see.")
    out.append(f"VERDICT: {verdict}")

    text = "\n".join(out)
    print(text)
    ANALYSIS_TXT.write_text(text + "\n")
    print(f"\nWrote {ANALYSIS_TXT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
