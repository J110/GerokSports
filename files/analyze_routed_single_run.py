"""Routed single-run policy: per-field, pick the better model
(considering variability), then simulate how many of 14 fields per
delivery come back right.

Routing decided from the 3-run pooled data:
  pick model with higher pooled accuracy.
  tie → pick the lower-variance model (Qwen everywhere it ties).
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from model_bakeoff_spatial import (  # noqa: E402
    CLIPS, FIELDS, matches, normalise, pct,
)


def load_all():
    rows = []
    for ridx in (1, 2, 3):
        p = ROOT / f"logs/audit_v1/bakeoff_spatial/run_{ridx}/results.json"
        for r in json.loads(p.read_text()):
            rows.append({"run": ridx, **r})
    return rows


def truth_for(clip_id, field):
    for c in CLIPS:
        if c["id"] == clip_id and field in c["truth"]:
            return normalise(field, c["truth"][field])
    return None


def pooled_acc(rows, model, field):
    n = ok = 0
    for r in rows:
        if r["model"] != model:
            continue
        t = truth_for(r["clip"], field)
        if t is None:
            continue
        n += 1
        if matches(r["pred"].get(field), t):
            ok += 1
    return ok, n


def per_run_acc(rows, model, field, run_idx):
    n = ok = 0
    for r in rows:
        if r["model"] != model or r["run"] != run_idx:
            continue
        t = truth_for(r["clip"], field)
        if t is None:
            continue
        n += 1
        if matches(r["pred"].get(field), t):
            ok += 1
    return (ok / n) if n else None


def main():
    rows = load_all()
    QWEN, GEM = "qwen30b-instruct", "gemini-3-flash"

    # ── Build routing ──
    print("=" * 78)
    print("FIELD-LEVEL ROUTING — pick the better model per field")
    print("=" * 78)
    print(f"{'field':22s} {'Qwen':>10s} {'Gem':>10s} "
          f"{'Q spread':>10s} {'G spread':>10s}   owner")
    routing = {}
    for fld in FIELDS:
        oq, nq = pooled_acc(rows, QWEN, fld)
        og, ng = pooled_acc(rows, GEM, fld)
        rq = (oq / nq) if nq else 0.0
        rg = (og / ng) if ng else 0.0
        # Per-run rates → spread = max-min
        per_run_q = [per_run_acc(rows, QWEN, fld, r) for r in (1, 2, 3)]
        per_run_g = [per_run_acc(rows, GEM, fld, r) for r in (1, 2, 3)]
        sq = (max(x for x in per_run_q if x is not None)
              - min(x for x in per_run_q if x is not None)) \
            if any(x is not None for x in per_run_q) else 0.0
        sg = (max(x for x in per_run_g if x is not None)
              - min(x for x in per_run_g if x is not None)) \
            if any(x is not None for x in per_run_g) else 0.0
        # Choose: higher acc; tie → lower spread; tie → Qwen (faster)
        if rq > rg + 0.001:
            owner = QWEN
        elif rg > rq + 0.001:
            owner = GEM
        else:
            owner = QWEN if sq <= sg else GEM
        routing[fld] = owner
        marker = "Q" if owner == QWEN else "G"
        print(f"{fld:22s} {rq*100:9.0f}% {rg*100:9.0f}% "
              f"{sq*100:9.0f}pp {sg*100:9.0f}pp     {marker}")
    print()

    # ── Routed expected accuracy per field ──
    print("=" * 78)
    print("EXPECTED PER-FIELD ACCURACY UNDER ROUTING (one call per delivery)")
    print("=" * 78)
    field_rates = []
    for fld in FIELDS:
        owner = routing[fld]
        ok, n = pooled_acc(rows, owner, fld)
        rate = (ok / n) if n else 0.0
        field_rates.append((fld, owner, rate, ok, n))
    for fld, owner, rate, ok, n in field_rates:
        marker = "Q" if owner == QWEN else "G"
        print(f"  [{marker}] {fld:22s} {rate*100:5.0f}% ({ok}/{n})")
    sum_rate = sum(r for _, _, r, _, _ in field_rates)
    print(f"\nE[fields right per delivery] = sum of per-field rates "
          f"= {sum_rate:.2f} of {len(FIELDS)}")
    print()

    # ── Simulation: per-delivery histogram ──
    # For each (clip, run, rep), compose a routed call by taking
    # pred[field] from owner-model on that specific (clip, run, rep).
    # Count fields-with-truth that are correct.
    print("=" * 78)
    print("SIMULATED PER-DELIVERY DISTRIBUTION")
    print("(45 routed calls = 5 clips × 3 runs × 3 reps)")
    print("=" * 78)
    # index rows by (model, clip, run, rep)
    idx = {}
    for r in rows:
        idx[(r["model"], r["clip"], r["run"], r["rep"])] = r
    routed_results = []
    for clip in CLIPS:
        clip_truths = {f: truth_for(clip["id"], f) for f in FIELDS
                       if truth_for(clip["id"], f) is not None}
        n_truth = len(clip_truths)
        if n_truth == 0:
            continue
        for run_idx in (1, 2, 3):
            for rep in (1, 2, 3):
                pred = {}
                for fld in FIELDS:
                    owner = routing[fld]
                    src = idx.get((owner, clip["id"], run_idx, rep))
                    if src:
                        pred[fld] = src["pred"].get(fld)
                ok = 0
                wrong_fields = []
                for fld, t in clip_truths.items():
                    if matches(pred.get(fld), t):
                        ok += 1
                    else:
                        wrong_fields.append(fld)
                routed_results.append({
                    "clip": clip["id"], "run": run_idx, "rep": rep,
                    "n_ok": ok, "n_truth": n_truth,
                    "rate": ok / n_truth,
                    "wrong": wrong_fields,
                })
    n = len(routed_results)
    total_ok = sum(r["n_ok"] for r in routed_results)
    total_n = sum(r["n_truth"] for r in routed_results)
    rates = [r["rate"] for r in routed_results]
    print(f"\nPer-delivery field-hit-rate over {n} simulated routed calls:")
    print(f"  mean   {statistics.mean(rates)*100:.0f}%   "
          f"median {statistics.median(rates)*100:.0f}%   "
          f"min {min(rates)*100:.0f}%   max {max(rates)*100:.0f}%")
    print(f"  total  {total_ok}/{total_n} fields ({pct(total_ok, total_n)})")

    # Per-clip mean
    print(f"\nPer-clip mean (clips have different #truth fields):")
    by_clip = defaultdict(list)
    for r in routed_results:
        by_clip[r["clip"]].append(r)
    for cid in [c["id"] for c in CLIPS]:
        rs = by_clip.get(cid, [])
        if not rs:
            continue
        nt = rs[0]["n_truth"]
        mean_ok = sum(r["n_ok"] for r in rs) / len(rs)
        print(f"  {cid:10s}  expect {mean_ok:4.1f}/{nt} fields right "
              f"per call ({100*mean_ok/nt:.0f}%)")

    # Histogram of fields-right-per-call
    print(f"\nHistogram of fields-right per routed call (n_truth varies "
          f"by clip):")
    hist = Counter(r["n_ok"] for r in routed_results)
    for k in sorted(hist):
        bar = "█" * hist[k]
        print(f"  {k:2d} right   {hist[k]:3d} calls  {bar}")

    # Most common wrong fields under routing
    wrong_counter = Counter()
    for r in routed_results:
        for f in r["wrong"]:
            wrong_counter[f] += 1
    print(f"\nMost common wrong fields under routing "
          f"(out of {n} routed calls):")
    for f, c in wrong_counter.most_common():
        # Denominator = number of routed calls where this field had truth
        denom = sum(1 for r in routed_results
                    if truth_for(r["clip"], f) is not None)
        print(f"  {f:22s} wrong {c:3d}/{denom}  "
              f"({100*c/denom:.0f}% wrong)")
    print()

    # ── Tier the fields ──
    print("=" * 78)
    print("TIER-BY-RELIABILITY BREAKDOWN")
    print("=" * 78)
    tiers = {"reliable (≥90%)": [], "useful (70-89%)": [],
             "weak (40-69%)": [], "broken (<40%)": []}
    for fld, owner, rate, ok, n in field_rates:
        m = "Q" if owner == QWEN else "G"
        entry = f"{fld} [{m}] {rate*100:.0f}%"
        if rate >= 0.90:
            tiers["reliable (≥90%)"].append(entry)
        elif rate >= 0.70:
            tiers["useful (70-89%)"].append(entry)
        elif rate >= 0.40:
            tiers["weak (40-69%)"].append(entry)
        else:
            tiers["broken (<40%)"].append(entry)
    for tier, items in tiers.items():
        print(f"\n  {tier}: {len(items)} fields")
        for e in items:
            print(f"    • {e}")
    print()


if __name__ == "__main__":
    main()
