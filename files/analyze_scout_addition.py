"""Does adding Scout change anything when pooled with Qwen + Gemini?

Three views (mirrors analyze_3x_addition.py + adds Scout to routing):

  1. Per-field UPPER BOUND.  best(Q+G) vs best(Q+G+S).
  2. Per-cell UNIQUE rescues by Scout.
  3. ROUTED single-call: does any field's owner switch to Scout?
     New expected fields-right-per-delivery.
  4. 3-way ENSEMBLE majority.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from model_bakeoff_spatial import CLIPS, FIELDS, matches, normalise, pct  # noqa: E402

QWEN, GEM, SCOUT = "qwen30b-instruct", "gemini-3-flash", "scout"


def load_all():
    rows = []
    for ridx in (1, 2, 3):
        p = ROOT / f"logs/audit_v1/bakeoff_spatial/run_{ridx}/results.json"
        for r in json.loads(p.read_text()):
            rows.append({"run": ridx, **r})
        ps = ROOT / f"logs/audit_v1/scout_spatial/run_{ridx}/results.json"
        for r in json.loads(ps.read_text()):
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


def system_modal(rows, system, clip, field):
    seen = []
    for r in rows:
        if r["model"] == system and r["clip"] == clip:
            seen.append(r["pred"].get(field))
    if not seen:
        return None
    counts = Counter(seen)
    top = counts.most_common(1)[0][1]
    for v in seen:
        if counts[v] == top:
            return v
    return seen[0]


def main():
    rows = load_all()

    # ── (1) Per-field upper bound ──
    print("=" * 84)
    print("(1) PER-FIELD ACCURACY — Qwen vs Gemini vs Scout, plus best-of")
    print("=" * 84)
    print(f"{'field':22s} {'Qwen':>8s} {'Gem':>8s} {'Scout':>8s}  "
          f"best(Q+G) best(Q+G+S)  Δ_from_Scout")
    weighted_b2 = weighted_b3 = grand_n = 0
    for fld in FIELDS:
        oq, nq = pooled_acc(rows, QWEN, fld)
        og, ng = pooled_acc(rows, GEM, fld)
        os_, ns = pooled_acc(rows, SCOUT, fld)
        rq = (oq / nq) if nq else 0.0
        rg = (og / ng) if ng else 0.0
        rs = (os_ / ns) if ns else 0.0
        if max(nq, ng, ns) == 0:
            continue
        b2 = max(rq, rg)
        b3 = max(b2, rs)
        delta = b3 - b2
        clip_ns = sum(
            1 for c in CLIPS if truth_for(c["id"], fld) is not None)
        weighted_b2 += b2 * clip_ns
        weighted_b3 += b3 * clip_ns
        grand_n += clip_ns
        marker = " ← Scout!" if delta > 0.001 else ""
        print(f"{fld:22s} {rq*100:7.0f}% {rg*100:7.0f}% {rs*100:7.0f}%  "
              f"{b2*100:7.0f}%   {b3*100:7.0f}%  {delta*100:+5.0f} pp"
              + marker)
    print(f"\nWeighted-by-clip mean: best(Q+G)={weighted_b2/grand_n:.1%}  "
          f"best(Q+G+S)={weighted_b3/grand_n:.1%}  "
          f"Δ={(weighted_b3-weighted_b2)/grand_n:+.1%}")
    print()

    # ── (2) Per-cell rescues ──
    print("=" * 84)
    print("(2) UNIQUE RESCUES BY SCOUT")
    print("    Cells where Scout's modal answer is correct AND both")
    print("    Qwen-modal AND Gemini-modal are wrong.")
    print("=" * 84)
    rescues = []
    losses = []
    n_cells = 0
    for clip in CLIPS:
        for fld in FIELDS:
            t = truth_for(clip["id"], fld)
            if t is None:
                continue
            n_cells += 1
            mq = system_modal(rows, QWEN, clip["id"], fld)
            mg = system_modal(rows, GEM, clip["id"], fld)
            ms_ = system_modal(rows, SCOUT, clip["id"], fld)
            ok_q = matches(mq, t)
            ok_g = matches(mg, t)
            ok_s = matches(ms_, t)
            if ok_s and not ok_q and not ok_g:
                rescues.append((clip["id"], fld, t, mq, mg, ms_))
            if not ok_s and (ok_q or ok_g):
                losses.append((clip["id"], fld, t, mq, mg, ms_,
                               ok_q, ok_g))
    print(f"\nScored cells: {n_cells}")
    print(f"Rescues by Scout (S✓, Q✗, G✗): {len(rescues)}")
    print(f"Losses by Scout (S✗ but Q or G ✓): {len(losses)}")
    print()
    if rescues:
        print("RESCUES — Scout adds value:")
        for cid, fld, t, mq, mg, ms_ in rescues:
            print(f"  {cid:10s} {fld:22s} truth={t}  "
                  f"Q={mq}  G={mg}  S={ms_}")
        print()

    # ── (3) Routing including Scout ──
    print("=" * 84)
    print("(3) FIELD ROUTING WITH SCOUT — does anyone get demoted?")
    print("=" * 84)
    print(f"{'field':22s} {'Qwen':>8s} {'Gem':>8s} {'Scout':>8s}  "
          f"{'old owner':>15s}  {'new owner':>15s}")
    routing_old = {}
    routing_new = {}
    field_rates_new = []
    for fld in FIELDS:
        oq, nq = pooled_acc(rows, QWEN, fld)
        og, ng = pooled_acc(rows, GEM, fld)
        os_, ns = pooled_acc(rows, SCOUT, fld)
        rq = (oq / nq) if nq else 0.0
        rg = (og / ng) if ng else 0.0
        rs = (os_ / ns) if ns else 0.0
        if max(nq, ng, ns) == 0:
            continue
        # Old owner (Qwen vs Gemini, prior policy)
        old = QWEN if rq >= rg else GEM
        # Per-run spread
        spreads = {}
        for sys_ in (QWEN, GEM, SCOUT):
            per_run = [per_run_acc(rows, sys_, fld, r) for r in (1, 2, 3)]
            per_run = [x for x in per_run if x is not None]
            spreads[sys_] = (max(per_run) - min(per_run)) if per_run else 0
        # New owner: highest pooled rate; tie → lowest spread; tie → Qwen, Gemini, Scout
        cand = [(rq, spreads[QWEN], 0, QWEN),
                (rg, spreads[GEM], 1, GEM),
                (rs, spreads[SCOUT], 2, SCOUT)]
        cand.sort(key=lambda x: (-x[0], x[1], x[2]))
        new = cand[0][3]
        routing_old[fld] = old
        routing_new[fld] = new
        field_rates_new.append((fld, new, max(rq, rg, rs)))
        marker = ""
        if new != old:
            marker = " ← CHANGED"
        # Short owner names
        def short(s):
            return {QWEN: "Q", GEM: "G", SCOUT: "S"}[s]
        print(f"{fld:22s} {rq*100:7.0f}% {rg*100:7.0f}% {rs*100:7.0f}%  "
              f"{short(old):>15s}  {short(new):>15s}{marker}")
    print()

    sum_old = 0.0
    sum_new = 0.0
    for fld in FIELDS:
        if fld not in routing_new:
            continue
        ok_o, n_o = pooled_acc(rows, routing_old[fld], fld)
        ok_n, n_n = pooled_acc(rows, routing_new[fld], fld)
        sum_old += (ok_o / n_o) if n_o else 0.0
        sum_new += (ok_n / n_n) if n_n else 0.0
    print(f"E[fields right per delivery] OLD policy (Q+G):     "
          f"{sum_old:.2f} / {len(FIELDS)}")
    print(f"E[fields right per delivery] NEW policy (Q+G+S):   "
          f"{sum_new:.2f} / {len(FIELDS)}  Δ {sum_new-sum_old:+.2f}")
    print()

    # ── (4) Per-clip simulation under NEW routing ──
    print("=" * 84)
    print("(4) SIMULATED PER-DELIVERY DISTRIBUTION UNDER NEW ROUTING")
    print("=" * 84)
    idx = {}
    for r in rows:
        idx[(r["model"], r["clip"], r["run"], r["rep"])] = r
    routed_results = []
    for clip in CLIPS:
        truths = {f: truth_for(clip["id"], f) for f in FIELDS
                  if truth_for(clip["id"], f) is not None}
        if not truths:
            continue
        for run_idx in (1, 2, 3):
            for rep in (1, 2, 3):
                pred = {}
                for fld in FIELDS:
                    owner = routing_new.get(fld)
                    src = idx.get((owner, clip["id"], run_idx, rep))
                    if src:
                        pred[fld] = src["pred"].get(fld)
                ok = sum(1 for fld, t in truths.items()
                         if matches(pred.get(fld), t))
                routed_results.append({
                    "clip": clip["id"], "n_ok": ok,
                    "n_truth": len(truths),
                    "rate": ok / len(truths),
                })
    n = len(routed_results)
    rates = [r["rate"] for r in routed_results]
    print(f"\n{n} simulated routed calls "
          f"(5 clips × 3 runs × 3 reps):")
    print(f"  mean   {sum(rates)/n*100:.0f}%   "
          f"min {min(rates)*100:.0f}%   max {max(rates)*100:.0f}%")
    by_clip = defaultdict(list)
    for r in routed_results:
        by_clip[r["clip"]].append(r)
    print(f"\nPer-clip mean fields-right-per-call:")
    for cid in [c["id"] for c in CLIPS]:
        rs = by_clip.get(cid, [])
        if not rs:
            continue
        nt = rs[0]["n_truth"]
        mean_ok = sum(r["n_ok"] for r in rs) / len(rs)
        print(f"  {cid:10s}  {mean_ok:4.1f}/{nt} "
              f"({100*mean_ok/nt:.0f}%)")
    print()

    # ── (5) 3-way ensemble vote ──
    print("=" * 84)
    print("(5) 3-WAY ENSEMBLE — majority of (Q-modal, G-modal, S-modal)")
    print("=" * 84)
    n3 = ok3 = 0
    no_majority = 0
    for clip in CLIPS:
        for fld in FIELDS:
            t = truth_for(clip["id"], fld)
            if t is None:
                continue
            mq = system_modal(rows, QWEN, clip["id"], fld)
            mg = system_modal(rows, GEM, clip["id"], fld)
            ms_ = system_modal(rows, SCOUT, clip["id"], fld)
            votes = [v for v in (mq, mg, ms_) if v is not None]
            if not votes:
                continue
            counts = Counter(votes).most_common()
            if counts[0][1] >= 2:
                n3 += 1
                if matches(counts[0][0], t):
                    ok3 += 1
            else:
                no_majority += 1
    print(f"\n  3-vote majority: {ok3}/{n3} ({pct(ok3, n3)}) "
          f"({no_majority} cells had no majority)")


if __name__ == "__main__":
    main()
