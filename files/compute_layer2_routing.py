"""Compute Q-vs-G per-field routing for Layer 2 production wiring.

Uses the offline spatial bakeoff results (3 runs × 3 reps × 5 clips) to
decide, for each of the 14 cricket fields: does Qwen or Gemini own this
field?  Owner = higher pooled accuracy; ties broken by lower run-to-run
spread, then by Gemini (video input should be preferred on ties).

Also reports per-field commit/abstain rates at confidence floor 0.70, so
we can sanity-check the live L2 numbers match offline expectations.

Writes:
    layer2_routing.json   (loaded by layer2_classifier.py at startup)
Prints:
    Human-readable routing table + expected-per-delivery summary.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from model_bakeoff_spatial import (  # noqa: E402
    CLIPS, FIELDS, matches, normalise,
)

QWEN, GEM = "qwen30b-instruct", "gemini-3-flash"
CONF_FLOOR = 0.70


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


def is_unknown(v):
    if v is None:
        return True
    s = str(v).strip().lower()
    return s in ("unknown", "none", "")


def main():
    rows = load_all()

    routing: dict[str, str] = {}
    field_stats: dict[str, dict] = {}

    print("\nQ-vs-G per-field routing (pooled across 3 runs × 3 reps):\n")
    print(f"{'field':22s} {'Qwen':>10s} {'Gemini':>10s}   owner  "
          f"(spread Q/G)")
    print("-" * 78)

    for fld in FIELDS:
        accs = {}
        spreads = {}
        for sys_ in (QWEN, GEM):
            ok, n = pooled_acc(rows, sys_, fld)
            accs[sys_] = (ok / n) if n else 0.0
            per_run = [per_run_acc(rows, sys_, fld, r) for r in (1, 2, 3)]
            per_run = [x for x in per_run if x is not None]
            spreads[sys_] = (max(per_run) - min(per_run)) if per_run else 0.0

        # Pick owner: higher accuracy, then lower spread, ties → Gemini
        # (video input is a superset of frame-burst input).
        cand = sorted(
            ((accs[s], -spreads[s], 0 if s == GEM else 1, s)
             for s in (QWEN, GEM)),
            key=lambda x: (-x[0], -x[1], x[2]),
        )
        owner = cand[0][3]
        routing[fld] = owner

        field_stats[fld] = {
            "owner": owner,
            "qwen_acc": round(accs[QWEN], 3),
            "gemini_acc": round(accs[GEM], 3),
            "qwen_spread": round(spreads[QWEN], 3),
            "gemini_spread": round(spreads[GEM], 3),
        }

        short = "Qwen " if owner == QWEN else "Gem  "
        print(f"{fld:22s} {accs[QWEN]*100:9.0f}% {accs[GEM]*100:9.0f}%   "
              f"{short}  ({spreads[QWEN]*100:.0f}% / "
              f"{spreads[GEM]*100:.0f}%)")

    print()

    # ── Simulate routed calls at conf floor 0.70 ──
    idx = {}
    for r in rows:
        idx[(r["model"], r["clip"], r["run"], r["rep"])] = r

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
                for fld, t in truths.items():
                    owner = routing[fld]
                    src = idx.get((owner, clip["id"], run_idx, rep))
                    per_field_agg[fld]["total"] += 1
                    if not src:
                        continue
                    v = src["pred"].get(fld)
                    c = float((src.get("pred_conf") or {}).get(fld, 0.0))
                    is_ok = matches(v, t)
                    commits = (not is_unknown(v)) and c >= CONF_FLOOR
                    if commits:
                        per_field_agg[fld]["committed"] += 1
                        if is_ok:
                            per_field_agg[fld]["correct_commits"] += 1
                        else:
                            per_field_agg[fld]["wrong_commits"] += 1
                    else:
                        per_field_agg[fld]["abstained"] += 1

    print(f"Expected per-delivery behaviour (conf ≥ {CONF_FLOOR}):\n")
    print(f"{'field':22s} {'owner':>6s}  {'commit%':>8s}  "
          f"{'correct%':>8s}  {'acc|commit':>12s}")
    exp_commit = exp_correct = 0.0
    for fld in FIELDS:
        a = per_field_agg[fld]
        if a["total"] == 0:
            continue
        cr = a["committed"] / a["total"]
        kr = a["correct_commits"] / a["total"]
        acc = (a["correct_commits"] / a["committed"]
               if a["committed"] else 0.0)
        owner_short = "Qwen" if routing[fld] == QWEN else "Gem"
        print(f"{fld:22s} {owner_short:>6s}  "
              f"{cr*100:7.0f}%  "
              f"{kr*100:7.0f}%  "
              f"{acc*100:11.0f}%")
        exp_commit += cr
        exp_correct += kr

    print()
    print(f"Expected per delivery (sum across 14 fields):")
    print(f"  COMMITTED : {exp_commit:.2f} / 14")
    print(f"  CORRECT   : {exp_correct:.2f}  "
          f"(precision {exp_correct/max(0.01, exp_commit)*100:.0f}%)")
    print(f"  ABSTAINED : {14 - exp_commit:.2f} / 14")
    print()

    out_path = ROOT / "layer2_routing.json"
    out = {
        "conf_floor": CONF_FLOOR,
        "routing": routing,  # {field: owner}
        "field_stats": field_stats,
        "expected": {
            "committed_per_delivery": round(exp_commit, 2),
            "correct_per_delivery": round(exp_correct, 2),
            "precision": round(
                exp_correct / max(0.01, exp_commit), 3),
        },
    }
    out_path.write_text(json.dumps(out, indent=2))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
