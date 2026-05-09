"""Routed Q+G+S with high-confidence filter — what gets committed per
delivery, what gets abstained, what lands right.

For each field, owner is picked from {Qwen, Gemini, Scout} by pooled
accuracy; ties → lower run-to-run spread.

Per routed call, a field is:
  - COMMITTED  if owner self-rated confidence ≥ CONF_FLOOR (and value
                is not "unknown")
  - ABSTAINED otherwise

We then count, per delivery, the expected:
  - fields committed
  - fields committed and correct
  - fields committed and wrong
  - fields abstained
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from model_bakeoff_spatial import CLIPS, FIELDS, matches, normalise, pct  # noqa: E402

QWEN, GEM, SCOUT = "qwen30b-instruct", "gemini-3-flash", "scout"

CONF_FLOOR = 0.70


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


def is_unknown(v):
    if v is None:
        return True
    s = str(v).strip().lower()
    return s in ("unknown", "none", "")


def main():
    rows = load_all()

    # ── Build routing ──
    routing = {}
    print(f"Routing decision (pooled across all reps in 3 runs):\n")
    print(f"{'field':22s} {'Qwen':>8s} {'Gem':>8s} {'Scout':>8s}   owner")
    for fld in FIELDS:
        rs = {}
        sp = {}
        for sys_ in (QWEN, GEM, SCOUT):
            ok, n = pooled_acc(rows, sys_, fld)
            rs[sys_] = (ok / n) if n else 0.0
            per_run = [per_run_acc(rows, sys_, fld, r) for r in (1, 2, 3)]
            per_run = [x for x in per_run if x is not None]
            sp[sys_] = (max(per_run) - min(per_run)) if per_run else 0
        # Rank: higher acc, lower spread, (Qwen, Gemini, Scout order)
        cand = sorted(
            ((rs[s], sp[s], i, s) for i, s in enumerate(
                (QWEN, GEM, SCOUT))),
            key=lambda x: (-x[0], x[1], x[2]),
        )
        owner = cand[0][3]
        routing[fld] = owner
        short = {QWEN: "Qwen", GEM: "Gem", SCOUT: "Scout"}[owner]
        print(f"{fld:22s} {rs[QWEN]*100:7.0f}% {rs[GEM]*100:7.0f}% "
              f"{rs[SCOUT]*100:7.0f}%    {short}")
    print()

    # ── Simulate routed calls ──
    idx = {}
    for r in rows:
        idx[(r["model"], r["clip"], r["run"], r["rep"])] = r

    per_call = []
    per_field_agg = defaultdict(lambda: {
        "committed": 0, "correct_commits": 0,
        "wrong_commits": 0, "abstained": 0, "total": 0,
    })

    for clip in CLIPS:
        truths = {f: truth_for(clip["id"], f) for f in FIELDS
                  if truth_for(clip["id"], f) is not None}
        if not truths:
            continue
        for run_idx in (1, 2, 3):
            for rep in (1, 2, 3):
                committed = correct = wrong = abstained = 0
                uncommitted_correct = uncommitted_wrong = 0
                detail = []
                for fld, t in truths.items():
                    owner = routing[fld]
                    src = idx.get(
                        (owner, clip["id"], run_idx, rep))
                    per_field_agg[fld]["total"] += 1
                    if not src:
                        continue
                    v = src["pred"].get(fld)
                    c = float((src.get("pred_conf") or {}).get(fld, 0.0))
                    is_ok = matches(v, t)
                    commits = (not is_unknown(v)) and c >= CONF_FLOOR
                    if commits:
                        committed += 1
                        per_field_agg[fld]["committed"] += 1
                        if is_ok:
                            correct += 1
                            per_field_agg[fld]["correct_commits"] += 1
                        else:
                            wrong += 1
                            per_field_agg[fld]["wrong_commits"] += 1
                    else:
                        abstained += 1
                        per_field_agg[fld]["abstained"] += 1
                        if is_ok:
                            uncommitted_correct += 1
                        else:
                            uncommitted_wrong += 1
                    detail.append((fld, v, round(c, 2), is_ok, commits))
                per_call.append({
                    "clip": clip["id"], "run": run_idx, "rep": rep,
                    "n_truth": len(truths),
                    "committed": committed,
                    "correct": correct,
                    "wrong": wrong,
                    "abstained": abstained,
                    "uncommitted_correct": uncommitted_correct,
                    "uncommitted_wrong": uncommitted_wrong,
                    "detail": detail,
                })

    # ── Summary ──
    n = len(per_call)
    print(f"Simulated {n} routed calls "
          f"(5 clips × 3 runs × 3 reps) with "
          f"confidence floor ≥ {CONF_FLOOR}.\n")

    # Mean per-call numbers, using n_truth as denominator equivalents
    sum_truth = sum(p["n_truth"] for p in per_call)
    sum_commit = sum(p["committed"] for p in per_call)
    sum_correct = sum(p["correct"] for p in per_call)
    sum_wrong = sum(p["wrong"] for p in per_call)
    sum_abst = sum(p["abstained"] for p in per_call)
    sum_uc_correct = sum(p["uncommitted_correct"] for p in per_call)
    sum_uc_wrong = sum(p["uncommitted_wrong"] for p in per_call)

    print(f"Per routed call (averaging over {n} calls "
          f"with variable n_truth per clip):")
    print(f"  avg truth fields  : {sum_truth/n:5.2f}")
    print(f"  avg COMMITTED     : {sum_commit/n:5.2f}  "
          f"of these "
          f"{sum_correct/max(1, sum_commit)*100:4.0f}% right")
    print(f"     correct        : {sum_correct/n:5.2f}")
    print(f"     wrong          : {sum_wrong/n:5.2f}")
    print(f"  avg ABSTAINED     : {sum_abst/n:5.2f}  "
          f"(of these "
          f"{sum_uc_correct/max(1, sum_abst)*100:4.0f}% would have "
          f"been right if committed)")
    print()

    # Scale to a theoretical per-delivery view
    # (assume all 14 fields have truth — just use per-field rates)
    print("=" * 78)
    print("Scaled to all 14 fields (field-by-field probability):")
    print("=" * 78)
    print(f"{'field':22s} {'owner':>6s}  {'commit%':>8s}  "
          f"{'commit-correct%':>16s}  {'acc when commit':>18s}")
    fields_in_order = FIELDS
    exp_commits = exp_correct = exp_wrong = exp_abstain = 0.0
    for fld in fields_in_order:
        agg = per_field_agg[fld]
        total = agg["total"]
        if total == 0:
            continue
        commit_rate = agg["committed"] / total
        correct_rate = agg["correct_commits"] / total
        wrong_rate = agg["wrong_commits"] / total
        abst_rate = agg["abstained"] / total
        accwc = (agg["correct_commits"] / agg["committed"]
                 if agg["committed"] else 0.0)
        owner_short = {QWEN: "Qwen", GEM: "Gem",
                       SCOUT: "Scout"}[routing[fld]]
        print(f"{fld:22s} {owner_short:>6s}  "
              f"{commit_rate*100:7.0f}%  "
              f"{correct_rate*100:15.0f}%  "
              f"{accwc*100:17.0f}%")
        exp_commits += commit_rate
        exp_correct += correct_rate
        exp_wrong += wrong_rate
        exp_abstain += abst_rate
    print()
    print(f"Expected per delivery (sum across 14 fields):")
    print(f"  fields COMMITTED              : {exp_commits:5.2f} / 14")
    print(f"    of which CORRECT            : {exp_correct:5.2f} "
          f"(precision {exp_correct/max(0.01, exp_commits)*100:.0f}%)")
    print(f"    of which WRONG              : {exp_wrong:5.2f}")
    print(f"  fields ABSTAINED              : {exp_abstain:5.2f} / 14")
    print()

    # ── Per-clip breakdown ──
    print("=" * 78)
    print("Per-clip mean committed / correct / wrong / abstained")
    print("=" * 78)
    by_clip = defaultdict(list)
    for p in per_call:
        by_clip[p["clip"]].append(p)
    for cid in [c["id"] for c in CLIPS]:
        rs = by_clip.get(cid, [])
        if not rs:
            continue
        nt = rs[0]["n_truth"]
        mc = statistics.mean(p["committed"] for p in rs)
        mk = statistics.mean(p["correct"] for p in rs)
        mw = statistics.mean(p["wrong"] for p in rs)
        ma = statistics.mean(p["abstained"] for p in rs)
        print(f"  {cid:10s}  truth={nt:2d}  commit={mc:4.1f}  "
              f"correct={mk:4.1f}  wrong={mw:4.1f}  abstain={ma:4.1f}")
    print()

    # ── No-threshold baseline (for reference) ──
    sum_all_correct = sum(p["correct"] + p["uncommitted_correct"]
                          for p in per_call)
    print(f"(Reference — NO confidence threshold, all 14 fields "
          f"committed always:)")
    print(f"  correct per call:  "
          f"{sum_all_correct/n:.2f} of "
          f"{sum_truth/n:.2f} truth fields = "
          f"{sum_all_correct/max(1, sum_truth)*100:.0f}%")


if __name__ == "__main__":
    main()
