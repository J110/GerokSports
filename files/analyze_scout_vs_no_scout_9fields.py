"""For just the 9 RELIABLE+USEFUL fields (≥70% single-model ceiling),
does Scout actually add anything over Qwen+Gemini?

Compares three policies on the same simulated 45 calls:
  A) Q + G only, best owner per field
  B) Q + G + S, best owner per field
  C) A with NO scout at all — same exact calls but with Qwen routed
     for bowling_arm instead of Scout

Reports per-delivery committed/correct for each policy on the 9 fields.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from model_bakeoff_spatial import CLIPS, FIELDS, matches, normalise  # noqa: E402

QWEN, GEM, SCOUT = "qwen30b-instruct", "gemini-3-flash", "scout"

# The 9 fields that came out reliable (≥90%) or useful (70–89%) in
# the routed Q+G+S analysis.
NINE_FIELDS = [
    "is_valid_delivery",
    "batsman_handed",
    "bowling_arm",
    "bowling_angle",
    "bowling_type",
    "bounce",
    "shot_played",
    "shot_angle",
    "elevation",
]


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


def simulate(rows, routing, fields):
    """Return list of per-call records: {committed, correct, wrong}."""
    idx = {}
    for r in rows:
        idx[(r["model"], r["clip"], r["run"], r["rep"])] = r
    calls = []
    for clip in CLIPS:
        truths = {f: truth_for(clip["id"], f) for f in fields
                  if truth_for(clip["id"], f) is not None}
        if not truths:
            continue
        for run_idx in (1, 2, 3):
            for rep in (1, 2, 3):
                committed = correct = wrong = 0
                for fld, t in truths.items():
                    owner = routing[fld]
                    src = idx.get((owner, clip["id"], run_idx, rep))
                    if not src:
                        continue
                    v = src["pred"].get(fld)
                    c = float((src.get("pred_conf") or {}).get(fld, 0.0))
                    is_ok = matches(v, t)
                    # Commit iff value is not unknown and conf >= 0.7
                    is_unk = (v is None or
                              str(v).strip().lower() in ("unknown", "none"))
                    if (not is_unk) and c >= 0.70:
                        committed += 1
                        if is_ok:
                            correct += 1
                        else:
                            wrong += 1
                calls.append({
                    "clip": clip["id"], "run": run_idx, "rep": rep,
                    "n_truth": len(truths),
                    "committed": committed,
                    "correct": correct,
                    "wrong": wrong,
                })
    return calls


def main():
    rows = load_all()

    # ── Routing A: Q+G only ──
    routing_QG = {}
    # ── Routing B: Q+G+S ──
    routing_QGS = {}
    for fld in NINE_FIELDS:
        rates = {}
        for sys_ in (QWEN, GEM, SCOUT):
            ok, n = pooled_acc(rows, sys_, fld)
            rates[sys_] = ((ok / n) if n else 0.0, ok, n)
        rQG = {k: v for k, v in rates.items() if k != SCOUT}
        routing_QG[fld] = max(rQG, key=lambda k: rQG[k][0])
        routing_QGS[fld] = max(rates, key=lambda k: rates[k][0])

    print("Fields and their owners under each policy:")
    print()
    print(f"{'field':22s}  {'Qwen':>6s}  {'Gem':>6s}  {'Scout':>6s}  "
          f"{'Q+G owner':>12s}  {'Q+G+S owner':>12s}")
    for fld in NINE_FIELDS:
        r = {}
        for sys_ in (QWEN, GEM, SCOUT):
            ok, n = pooled_acc(rows, sys_, fld)
            r[sys_] = (ok / n) if n else 0.0
        change = ("*" if routing_QG[fld] != routing_QGS[fld] else "")
        short = {QWEN: "Q", GEM: "G", SCOUT: "S"}
        print(f"{fld:22s}  {r[QWEN]*100:5.0f}%  {r[GEM]*100:5.0f}%  "
              f"{r[SCOUT]*100:5.0f}%  {short[routing_QG[fld]]:>12s}  "
              f"{short[routing_QGS[fld]]:>12s}{change}")
    print()

    # ── Simulate both policies ──
    calls_A = simulate(rows, routing_QG, NINE_FIELDS)
    calls_B = simulate(rows, routing_QGS, NINE_FIELDS)

    def summarize(name, calls):
        n = len(calls)
        sum_tr = sum(c["n_truth"] for c in calls)
        sum_co = sum(c["committed"] for c in calls)
        sum_ok = sum(c["correct"] for c in calls)
        sum_wr = sum(c["wrong"] for c in calls)
        print(f"── Policy {name} ──")
        print(f"  {n} simulated calls, avg {sum_tr/n:.2f} fields "
              f"with truth per call (of 9).")
        print(f"  Committed   : {sum_co/n:5.2f} per call "
              f"({sum_co}/{sum_tr} total)")
        print(f"  Correct     : {sum_ok/n:5.2f} per call  "
              f"(precision {sum_ok/max(1, sum_co)*100:.1f}%)")
        print(f"  Wrong       : {sum_wr/n:5.2f} per call")
        print()

    print("Simulating on the 9-field subset "
          "(45 calls = 5 clips × 3 runs × 3 reps):\n")
    summarize("A) Q + G only", calls_A)
    summarize("B) Q + G + Scout", calls_B)

    # ── Per-call diff — where does Scout actually change the answer? ──
    print("Per-call difference (fields where Scout-owned prediction "
          "differs from Qwen-owned):")
    diff_count = 0
    for a, b in zip(calls_A, calls_B):
        da = a["correct"] - b["correct"]
        if da != 0:
            diff_count += 1
    # Summaries
    print(f"  calls where correct count differs: "
          f"{diff_count} / {len(calls_A)}")
    delta_correct = (sum(c["correct"] for c in calls_B) -
                     sum(c["correct"] for c in calls_A))
    delta_commit = (sum(c["committed"] for c in calls_B) -
                    sum(c["committed"] for c in calls_A))
    print(f"  total correct delta    : {delta_correct:+d}  "
          f"(=+{delta_correct/len(calls_A):.3f} per call)")
    print(f"  total committed delta  : {delta_commit:+d}")
    print()

    # ── Per-clip comparison ──
    print("Per-clip mean correct, A vs B:")
    by_clip_A = defaultdict(list)
    by_clip_B = defaultdict(list)
    for a in calls_A:
        by_clip_A[a["clip"]].append(a)
    for b in calls_B:
        by_clip_B[b["clip"]].append(b)
    print(f"  {'clip':10s}  {'nTruth':>6s}  "
          f"{'A correct':>10s}  {'B correct':>10s}  {'Δ':>5s}")
    for cid in [c["id"] for c in CLIPS]:
        if cid not in by_clip_A:
            continue
        nt = by_clip_A[cid][0]["n_truth"]
        ma = statistics.mean(x["correct"] for x in by_clip_A[cid])
        mb = statistics.mean(x["correct"] for x in by_clip_B[cid])
        print(f"  {cid:10s}  {nt:6d}  {ma:10.2f}  {mb:10.2f}  "
              f"{mb-ma:+5.2f}")
    print()

    # ── Single field of interest: bowling_arm ──
    print("Zoom: bowling_arm field only — Qwen vs Scout per call "
          "(across all 45 reps):")
    idx = {}
    for r in rows:
        idx[(r["model"], r["clip"], r["run"], r["rep"])] = r
    qwen_wins = scout_wins = both_right = both_wrong = 0
    for clip in CLIPS:
        t = truth_for(clip["id"], "bowling_arm")
        if t is None:
            continue
        for run_idx in (1, 2, 3):
            for rep in (1, 2, 3):
                q = idx.get((QWEN, clip["id"], run_idx, rep))
                s = idx.get((SCOUT, clip["id"], run_idx, rep))
                if not q or not s:
                    continue
                okq = matches(q["pred"].get("bowling_arm"), t)
                oks = matches(s["pred"].get("bowling_arm"), t)
                if okq and oks:
                    both_right += 1
                elif okq and not oks:
                    qwen_wins += 1
                elif oks and not okq:
                    scout_wins += 1
                else:
                    both_wrong += 1
    print(f"  both right  : {both_right}")
    print(f"  Qwen right, Scout wrong : {qwen_wins}")
    print(f"  Scout right, Qwen wrong : {scout_wins}")
    print(f"  both wrong  : {both_wrong}")
    print()

    # ── Cost annotation ──
    print("Cost/latency per call (approximate):")
    print("  Qwen30b-instruct  ~$0.0006  ~ 6s     burst")
    print("  Gemini 3 Flash    ~$0.005   ~25s     burst")
    print("  Scout (Groq)      ~$0.0002  ~13s     3 chunks of 5 frames")


if __name__ == "__main__":
    main()
