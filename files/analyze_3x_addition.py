"""Does adding Gemini-3x-slowed-video to (Qwen-burst, Gemini-burst)
add any new signal?

Three views:

  1. Per-field BEST-OF (upper bound).  For each field, compare:
       max( Qwen-burst, Gemini-burst )   vs
       max( Qwen-burst, Gemini-burst, Gemini-3x )

  2. Per-cell UNIQUES.  For each (clip, field) cell, take the modal
     answer of each system over its 3 reps.  Count cells where
     Gemini-3x's modal answer is correct AND both Qwen-burst and
     Gemini-burst modal answers are wrong.  These are the cells
     Gemini-3x rescues.

  3. Ensemble VOTE.  Per (clip, field), majority vote across the three
     system-modes.  Compare ensemble accuracy to:
       - best single system
       - 2-system vote (Qwen + Gemini-burst, tie-broken by Qwen)
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from model_bakeoff_spatial import (  # noqa: E402
    CLIPS, FIELDS, matches, normalise, pct,
)


def load_burst_runs():
    """Return list of rows tagged with model in {'qwen', 'gemini'}."""
    rows = []
    for ridx in (1, 2, 3):
        p = ROOT / f"logs/audit_v1/bakeoff_spatial/run_{ridx}/results.json"
        for r in json.loads(p.read_text()):
            tag = ("qwen" if r["model"].startswith("qwen")
                   else "gemini")
            rows.append({
                "system": tag, "clip": r["clip"], "rep": r["rep"],
                "pred": r["pred"],
            })
    return rows


def load_slow3x():
    p = ROOT / "logs/audit_v1/gemini_slow3x/results.json"
    data = json.loads(p.read_text())
    return [{"system": "gemini-3x", "clip": r["clip"],
             "rep": r["rep"], "pred": r["pred"]}
            for r in data["rows"]]


def truth_for(clip_id, field):
    for c in CLIPS:
        if c["id"] == clip_id and field in c["truth"]:
            return normalise(field, c["truth"][field])
    return None


def per_field_acc(rows, system, field):
    """Accuracy of one system on one field, pooled across all reps."""
    n = ok = 0
    for r in rows:
        if r["system"] != system:
            continue
        t = truth_for(r["clip"], field)
        if t is None:
            continue
        n += 1
        if matches(r["pred"].get(field), t):
            ok += 1
    return ok, n


def system_modal(rows, system, clip, field):
    """Most-frequent answer for a (system, clip, field) across reps.
    None if no reps.  Ties broken by first-seen."""
    seen = []
    for r in rows:
        if r["system"] == system and r["clip"] == clip:
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
    burst = load_burst_runs()
    slow = load_slow3x()
    all_rows = burst + slow

    SYSTEMS = ["qwen", "gemini", "gemini-3x"]

    print("=" * 78)
    print("(1) PER-FIELD UPPER BOUND")
    print("=" * 78)
    print(f"{'field':22s} {'Qwen':>10s} {'Gem-burst':>10s} "
          f"{'Gem-3x':>10s}  best(Q+G)  best(Q+G+3x)  Δ")
    grand_best2 = grand_best3 = grand_n = 0
    field_table = []
    for fld in FIELDS:
        cells = {}
        for sys_ in SYSTEMS:
            ok, n = per_field_acc(all_rows, sys_, fld)
            cells[sys_] = (ok, n)
        if all(n == 0 for ok, n in cells.values()):
            continue
        # Use rate, not count, since Gemini-3x has fewer calls (15 vs 45).
        rates = {s: (ok / n if n else 0.0) for s, (ok, n) in cells.items()}
        best2 = max(rates["qwen"], rates["gemini"])
        best3 = max(best2, rates["gemini-3x"])
        delta = best3 - best2
        # n for "denom" used in grand totals: assume 5 unique clips per field
        # (one truth per clip × field).  We sum over clips that have truth.
        clip_ns = sum(
            1 for c in CLIPS if truth_for(c["id"], fld) is not None)
        grand_best2 += best2 * clip_ns
        grand_best3 += best3 * clip_ns
        grand_n += clip_ns
        marker = " ← +" if delta > 0.001 else ""
        print(f"{fld:22s} "
              f"{cells['qwen'][0]}/{cells['qwen'][1]:<3d} ({rates['qwen']:5.0%}) "
              f"{cells['gemini'][0]}/{cells['gemini'][1]:<3d} ({rates['gemini']:5.0%}) "
              f"{cells['gemini-3x'][0]}/{cells['gemini-3x'][1]:<3d} ({rates['gemini-3x']:5.0%}) "
              f"  {best2:5.0%}     {best3:5.0%}     "
              f"{delta:+5.0%}{marker}")
        field_table.append({"field": fld, **rates,
                            "best2": best2, "best3": best3,
                            "delta": delta})
    print(f"\nGrand mean (weighted by clips with truth): "
          f"best(Q+G)={grand_best2/grand_n:.1%}  "
          f"best(Q+G+3x)={grand_best3/grand_n:.1%}  "
          f"Δ={(grand_best3-grand_best2)/grand_n:+.1%}")
    print()

    print("=" * 78)
    print("(2) UNIQUE RESCUES — cells where Gemini-3x is right and BOTH")
    print("    Qwen-burst AND Gemini-burst are wrong (modal answer per system)")
    print("=" * 78)
    rescues = []
    losses = []  # 3x wrong while at least one of the others was right
    total_cells = 0
    for clip in CLIPS:
        for fld in FIELDS:
            t = truth_for(clip["id"], fld)
            if t is None:
                continue
            total_cells += 1
            mq = system_modal(all_rows, "qwen", clip["id"], fld)
            mg = system_modal(all_rows, "gemini", clip["id"], fld)
            m3 = system_modal(all_rows, "gemini-3x", clip["id"], fld)
            ok_q = matches(mq, t)
            ok_g = matches(mg, t)
            ok_3 = matches(m3, t)
            if ok_3 and not ok_q and not ok_g:
                rescues.append((clip["id"], fld, t, mq, mg, m3))
            if not ok_3 and (ok_q or ok_g):
                losses.append((clip["id"], fld, t, mq, mg, m3,
                               ok_q, ok_g))
    print(f"\nTotal scored cells (5 clips × ~10 truth fields): "
          f"{total_cells}")
    print(f"Cells Gemini-3x rescues  (3x ✓, Q ✗, G ✗) : {len(rescues)}")
    print(f"Cells Gemini-3x loses    (3x ✗, Q or G ✓): {len(losses)}")
    print()
    if rescues:
        print("RESCUES — Gemini-3x adds value here:")
        for cid, fld, t, mq, mg, m3 in rescues:
            print(f"  {cid:10s} {fld:20s} truth={t}  "
                  f"Q={mq}  G={mg}  G3x={m3}")
        print()
    if losses:
        print(f"LOSSES — Gemini-3x is wrong where Q or G was right "
              f"({len(losses)} cells):")
        for cid, fld, t, mq, mg, m3, oq, og in losses:
            who = []
            if oq:
                who.append("Q")
            if og:
                who.append("G")
            print(f"  {cid:10s} {fld:20s} truth={t}  "
                  f"Q={mq}{'✓' if oq else ''}  "
                  f"G={mg}{'✓' if og else ''}  G3x={m3}  "
                  f"(right: {'+'.join(who)})")
        print()

    print("=" * 78)
    print("(3) ENSEMBLE VOTE — modal answer of each system, then majority")
    print("=" * 78)
    n_each = {s: 0 for s in SYSTEMS}
    ok_each = {s: 0 for s in SYSTEMS}
    n_2vote = ok_2vote = 0
    n_3vote = ok_3vote = 0
    for clip in CLIPS:
        for fld in FIELDS:
            t = truth_for(clip["id"], fld)
            if t is None:
                continue
            mq = system_modal(all_rows, "qwen", clip["id"], fld)
            mg = system_modal(all_rows, "gemini", clip["id"], fld)
            m3 = system_modal(all_rows, "gemini-3x", clip["id"], fld)
            for sys_, m in (("qwen", mq), ("gemini", mg),
                            ("gemini-3x", m3)):
                if m is None:
                    continue
                n_each[sys_] += 1
                if matches(m, t):
                    ok_each[sys_] += 1
            # 2-vote: Qwen + Gemini-burst.  If they disagree, pick Qwen
            # (arbitrary tie-break) — but better, fall back to single
            # "best individual" instead.  We'll just count exact-agreement
            # accuracy.
            if mq is not None and mg is not None:
                n_2vote += 1
                votes = [mq, mg]
                top, _ = Counter(votes).most_common(1)[0]
                if matches(top, t):
                    ok_2vote += 1
            # 3-vote: majority across all three modal answers.  If all
            # three differ → no winner (skip).
            votes = [v for v in (mq, mg, m3) if v is not None]
            if len(votes) >= 2:
                counts = Counter(votes).most_common()
                if counts[0][1] >= 2:
                    n_3vote += 1
                    if matches(counts[0][0], t):
                        ok_3vote += 1
    print()
    for sys_ in SYSTEMS:
        print(f"  {sys_:12s} modal-only acc: "
              f"{ok_each[sys_]}/{n_each[sys_]} "
              f"({pct(ok_each[sys_], n_each[sys_])})")
    print(f"  2-vote (Qwen+Gemini-burst tie-break Qwen): "
          f"{ok_2vote}/{n_2vote} ({pct(ok_2vote, n_2vote)})")
    print(f"  3-vote (Qwen+Gemini-burst+Gemini-3x, 2/3 majority): "
          f"{ok_3vote}/{n_3vote} ({pct(ok_3vote, n_3vote)})")
    print()


if __name__ == "__main__":
    main()
