#!/usr/bin/env python3
"""Standalone evaluator: bridge-gated pick_anchor candidate rule.

Reads the 23-row pinned regression set in `anchor_regression_classified.tsv`,
loads each cluster's metadata.json, applies a candidate bridge-gated rule, and
writes per-cluster results to `anchor_bridge_gated_results.tsv` plus a
classification confusion matrix on stdout.

The candidate rule (NOT shipped to delivery_classifier.py):

    Given the existing best anchor B (= current_anchor_t in metadata),
    iterate cluster frames in t-ascending order. For each frame f with
    f.t < B.t:
      - require V (or V_post)
      - require M2 or W
      - require all "bridge" frames g with f.t < g.t < B.t to satisfy
        (M or W) and not HARD
      - require (B.t - f.t) > 4.0
    First f passing all gates is chosen as bridge_anchor; otherwise fall
    through to B.

No production file is modified. No imports from delivery_classifier.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TSV_IN = ROOT / "anchor_regression_classified.tsv"
TSV_OUT = ROOT / "anchor_bridge_gated_results.tsv"

MIN_SHIFT_S = 4.0

REAL_RELEASE_RE = re.compile(
    r"\b(release[ds]?|delivers?|delivered|bowls?|bowled|throwing|"
    r"about to release|about to bowl|in process of throw)\b",
    re.IGNORECASE,
)


def parse_signals(sig_str: str) -> dict:
    """Parse 'VY Sn MY M2Y WY Kn SSY CGY rc=4 [HARD]' into a flag dict."""
    out = {"V": False, "V_post": False, "S": False, "M": False, "M2": False,
           "W": False, "K": False, "SS": False, "CG": False, "HARD": False,
           "rc": 0}
    if not sig_str:
        return out
    tokens = sig_str.split()
    for tok in tokens:
        if tok == "HARD":
            out["HARD"] = True
        elif tok.startswith("rc="):
            try:
                out["rc"] = int(tok.split("=", 1)[1])
            except ValueError:
                pass
        elif tok.startswith("V_post") or tok.startswith("Vpost"):
            out["V_post"] = tok.endswith("Y")
        elif tok.startswith("V") and len(tok) == 2:
            out["V"] = tok.endswith("Y")
        elif tok.startswith("M2"):
            out["M2"] = tok.endswith("Y")
        elif tok.startswith("M") and len(tok) == 2:
            out["M"] = tok.endswith("Y")
        elif tok.startswith("SS"):
            out["SS"] = tok.endswith("Y")
        elif tok.startswith("S") and len(tok) == 2:
            out["S"] = tok.endswith("Y")
        elif tok.startswith("W"):
            out["W"] = tok.endswith("Y")
        elif tok.startswith("K"):
            out["K"] = tok.endswith("Y")
        elif tok.startswith("CG"):
            out["CG"] = tok.endswith("Y")
    return out


def find_metadata(source_dir: Path, cluster_id: int) -> Path | None:
    if not source_dir.exists():
        return None
    prefix = f"c{cluster_id}_"
    for cdir in source_dir.iterdir():
        if cdir.is_dir() and cdir.name.startswith(prefix):
            mp = cdir / "metadata.json"
            if mp.exists():
                return mp
    return None


def apply_bridge_rule(frames: list[dict], best_t: float):
    """Return (bridge_t, fired_bool, reason_str)."""
    sorted_frames = sorted(frames, key=lambda f: f["t"])
    annotated = [(f["t"], parse_signals(f.get("signals", "")), f.get("signals", ""))
                 for f in sorted_frames]
    for ft, sig, raw in annotated:
        if ft >= best_t:
            break
        if not sig["V"] and not sig["V_post"]:
            continue
        if not (sig["M2"] or sig["W"]):
            continue
        if (best_t - ft) <= MIN_SHIFT_S:
            continue
        bridge = [(g_t, g_sig) for g_t, g_sig, _ in annotated
                  if ft < g_t < best_t]
        # Change 3 (2026-05-10): tolerate ≤1 empty frame in the bridge.
        # Matches production pick_anchor relaxation in
        # delivery_classifier.py:475.
        hard_in_bridge = any(g_sig["HARD"] for _, g_sig in bridge)
        empty_in_bridge = sum(
            1 for _, g_sig in bridge
            if not (g_sig["M"] or g_sig["W"]) and not g_sig["HARD"]
        )
        if not hard_in_bridge and empty_in_bridge <= 1:
            return ft, True, (
                f"fired_at_t={ft}"
                if empty_in_bridge == 0
                else f"fired_at_t={ft};empty_in_bridge=1")
        # bridge broken — keep scanning later candidates, but record
        # that this candidate was vetoed
    # No qualifying candidate
    return best_t, False, "no_qualifying_candidate"


def classify_prose(prose: str) -> str:
    return "CORRECT" if REAL_RELEASE_RE.search(prose or "") else "PHANTOM"


def main():
    rows_in = []
    with TSV_IN.open() as f:
        reader = csv.DictReader(f, delimiter="\t")
        for r in reader:
            rows_in.append(r)

    enriched = []
    for r in rows_in:
        src = r["source_dir"]
        try:
            cid = int(r["cluster_id"])
        except (TypeError, ValueError):
            cid = None
        meta_path = find_metadata(ROOT / src, cid) if cid is not None else None
        bridge_t = ""
        bridge_shift = ""
        fired = "N"
        reason = "no_metadata"
        if meta_path:
            try:
                meta = json.loads(meta_path.read_text())
                frames = meta.get("frames", [])
                cur_t = float(meta.get("anchor_t"))
                bt, ok, reason = apply_bridge_rule(frames, cur_t)
                bridge_t = bt
                bridge_shift = round(cur_t - bt, 2)
                fired = "Y" if ok else "N"
            except Exception as e:
                reason = f"error:{e}"
        r2 = dict(r)
        r2["bridge_anchor_t"] = bridge_t
        r2["bridge_shift_s"] = bridge_shift
        r2["bridge_fired"] = fired
        r2["bridge_reason"] = reason
        r2["classification"] = classify_prose(r.get("raw_description", ""))
        enriched.append(r2)

    out_cols = list(rows_in[0].keys()) + [
        "bridge_anchor_t", "bridge_shift_s", "bridge_fired",
        "bridge_reason", "classification",
    ]
    with TSV_OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_cols, delimiter="\t",
                           extrasaction="ignore")
        w.writeheader()
        for r in enriched:
            w.writerow(r)

    correct_idx = [i for i, r in enumerate(enriched, start=2)
                   if r["classification"] == "CORRECT"]
    phantom_idx = [i for i, r in enumerate(enriched, start=2)
                   if r["classification"] == "PHANTOM"]
    pos_idx = [i for i, r in enumerate(enriched, start=2)
               if r.get("positive_control") == "Y"]

    correct_fired = [r for r in enriched
                     if r["classification"] == "CORRECT" and r["bridge_fired"] == "Y"]
    phantom_fired = [r for r in enriched
                     if r["classification"] == "PHANTOM" and r["bridge_fired"] == "Y"]
    pos_fired = [r for r in enriched
                 if r.get("positive_control") == "Y" and r["bridge_fired"] == "Y"]
    pos_missed = [r for r in enriched
                  if r.get("positive_control") == "Y" and r["bridge_fired"] != "Y"]

    print(f"WROTE {TSV_OUT}  rows={len(enriched)}")
    print()
    print("=== Row indices used (TSV line numbers, header=line 1) ===")
    print(f"CORRECT-SHIFT rows ({len(correct_idx)}): {correct_idx}")
    print(f"PHANTOM-SHIFT rows ({len(phantom_idx)}): {phantom_idx}")
    print(f"POSITIVE-CONTROL rows ({len(pos_idx)}): {pos_idx}")
    print()
    print("=== Confusion matrix ===")
    print(f"CORRECT-SHIFT total           : {len(correct_idx)}")
    print(f"  bridge fired (TRUE-POS)     : {len(correct_fired)}")
    print(f"  bridge skipped (FALSE-NEG)  : {len(correct_idx) - len(correct_fired)}")
    print(f"PHANTOM-SHIFT total           : {len(phantom_idx)}")
    print(f"  bridge fired (FALSE-POS)    : {len(phantom_fired)}")
    print(f"  bridge skipped (TRUE-NEG)   : {len(phantom_idx) - len(phantom_fired)}")
    print(f"POSITIVE-CONTROL total        : {len(pos_idx)}")
    print(f"  bridge fired correctly      : {len(pos_fired)}")
    print(f"  bridge missed               : {len(pos_missed)}")
    print()
    if phantom_fired:
        print("=== FALSE-POSITIVES (bridge fired on PHANTOM) ===")
        for r in phantom_fired:
            print(f"  cid={r['cluster_id']} src={r['source_dir']} "
                  f"bridge_anchor_t={r['bridge_anchor_t']} "
                  f"blanket_signals=[{r.get('blanket_anchor_signals','')}]")
            print(f"    raw: {r.get('raw_description','')[:300]}")
    else:
        print("=== FALSE-POSITIVES: NONE ===")
    print()
    if pos_missed:
        print("=== POSITIVE-CONTROLS missed by bridge ===")
        for r in pos_missed:
            print(f"  cid={r['cluster_id']} src={r['source_dir']} "
                  f"current_anchor_t={r['current_anchor_t']} "
                  f"blanket_anchor_t={r['blanket_anchor_t']} "
                  f"reason={r['bridge_reason']}")
            print(f"    blanket_signals=[{r.get('blanket_anchor_signals','')}]")
    else:
        print("=== POSITIVE-CONTROLS missed: NONE ===")


if __name__ == "__main__":
    main()
