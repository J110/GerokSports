"""Joint analysis: rejection quality + confidence calibration.

Inputs:
  results_gemini_full.json         (60 tier-1 deliveries, 1 call each)
  results_gemini_negatives.json    (15 failed_* triplets)
  results_gemini_consistency.json  (20 tier-1 deliveries x 3 calls)

Reports:
  1. Rejection: how often Gemini rejects (a) curated deliveries, (b)
     pipeline-rejected triplets.
  2. Calibration: across 3 calls per delivery, how often does each
     field stay the same?  Bucketed by mean confidence.
  3. Label collapse: what % of accepted deliveries get the modal
     "good_length / outside_off / along_ground / offside" answer?
     (i.e. is Gemini classifying or guessing the IPL prior?)
"""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
FULL = json.loads((ROOT/"results_gemini_full.json").read_text())
NEG  = json.loads((ROOT/"results_gemini_negatives.json").read_text())
CONS = json.loads((ROOT/"results_gemini_consistency.json").read_text())


def hr(t):
    print()
    print("=" * 72)
    print(t)
    print("=" * 72)


# ===== 1. REJECTION QUALITY ============================================
hr("1. REJECTION QUALITY")
def rej_stats(rows, label):
    parsed = [r for r in rows if r.get("parsed")]
    rej = [r for r in parsed if r["parsed"].get("is_delivery") is False]
    print(f"  {label:<40} rejected {len(rej):>2}/{len(parsed):<2} "
          f"({100*len(rej)/max(1,len(parsed)):>5.1f}%)")
    return parsed, rej

print("Tier-1 set (curated real deliveries — should rarely reject):")
full_p, full_rej = rej_stats(FULL, "  curated tier-1")

print("\nNegative-control set (pipeline's failed_* candidates):")
neg_p, neg_rej = rej_stats(NEG, "  failed_* triplets")

if neg_rej:
    print("\n  Rejected non-deliveries:")
    for r in neg_rej:
        p = r["parsed"]
        print(f"    {r['id']:<14} conf={p.get('confidence')}  "
              f"{(p.get('narrative') or '')[:90]}")

if neg_p:
    accepted_neg = [r for r in neg_p
                    if r["parsed"].get("is_delivery") is not False]
    if accepted_neg:
        print("\n  ACCEPTED from negative set "
              "(probably real deliveries hidden in failed_* set):")
        for r in accepted_neg:
            p = r["parsed"]
            print(f"    {r['id']:<14} conf={p.get('confidence')}  "
                  f"{(p.get('narrative') or '')[:90]}")


# ===== 2. LABEL COLLAPSE ===============================================
hr("2. LABEL COLLAPSE  (is Gemini classifying or guessing the prior?)")
acc = [r for r in full_p if r["parsed"].get("is_delivery") is not False]
combo = Counter()
for r in acc:
    p = r["parsed"]
    combo[(p.get("length"), p.get("line"),
           p.get("shot"), p.get("direction"))] += 1
print(f"  {len(acc)} accepted deliveries  →  "
      f"{len(combo)} unique (len,line,shot,dir) tuples")
top = combo.most_common(1)[0]
print(f"  modal answer: {top[0]}  → {top[1]}/{len(acc)} "
      f"({100*top[1]/len(acc):.0f}%)")
print(f"\n  full distribution:")
for k, n in combo.most_common():
    bar = "█" * n
    print(f"    {n:>3}  {bar}  {k}")


# ===== 3. SELF-CONSISTENCY / CONFIDENCE CALIBRATION ====================
hr("3. SELF-CONSISTENCY  (3 calls per delivery → does conf predict stability?)")
# group by id
by_id = defaultdict(list)
for r in CONS:
    if r.get("parsed"):
        by_id[r["id"]].append(r["parsed"])

FIELDS = ["is_delivery", "phase_visible", "length",
          "line", "shot", "direction"]


def all_same(vals):
    return len(set(vals)) == 1


per_delivery = []
for did, calls in by_id.items():
    if len(calls) < 2:
        continue
    confs = [float(c.get("confidence", 0) or 0) for c in calls]
    mean_conf = sum(confs) / len(confs)
    min_conf = min(confs)
    field_agree = {f: all_same([c.get(f) for c in calls]) for f in FIELDS}
    n_agree = sum(field_agree.values())
    per_delivery.append({
        "id": did, "n_calls": len(calls),
        "mean_conf": mean_conf, "min_conf": min_conf,
        "field_agree": field_agree,
        "n_agree": n_agree, "n_fields": len(FIELDS),
        "answers": [{f: c.get(f) for f in FIELDS} for c in calls],
    })

print(f"\n  Per-delivery stability "
      f"({len(per_delivery)} deliveries × 3 calls):\n")
print(f"  {'id':<14}  mean_c  min_c  agree   answer drift")
for d in sorted(per_delivery, key=lambda x: -x["mean_conf"]):
    drift = ""
    if d["n_agree"] < d["n_fields"]:
        # show the fields that drifted
        drifts = []
        for f in FIELDS:
            if not d["field_agree"][f]:
                vals = [a[f] for a in d["answers"]]
                drifts.append(f"{f}={'/'.join(str(v) for v in vals)}")
        drift = "; ".join(drifts)
    print(f"  {d['id']:<14}  {d['mean_conf']:>5.2f}  "
          f"{d['min_conf']:>5.2f}  "
          f"{d['n_agree']}/{d['n_fields']}    {drift[:120]}")

# bucket by min confidence
print(f"\n  Stability by MIN confidence across the 3 calls:")
print(f"  {'bucket':>10}  n  fields-fully-stable  classification-fields-stable")
buckets = defaultdict(list)
for d in per_delivery:
    if d["min_conf"] >= 0.9: b = "≥0.90"
    elif d["min_conf"] >= 0.8: b = "0.80-0.89"
    elif d["min_conf"] >= 0.7: b = "0.70-0.79"
    else: b = "<0.70"
    buckets[b].append(d)

CLASS_FIELDS = ["length", "line", "shot", "direction"]
for b in ["≥0.90","0.80-0.89","0.70-0.79","<0.70"]:
    rs = buckets.get(b, [])
    if not rs: continue
    full_stable = sum(1 for d in rs if d["n_agree"] == d["n_fields"])
    cls_stable = sum(1 for d in rs
                     if all(d["field_agree"][f] for f in CLASS_FIELDS))
    print(f"  {b:>10}  {len(rs):>2}  "
          f"{full_stable}/{len(rs)} ({100*full_stable/len(rs):.0f}%)        "
          f"{cls_stable}/{len(rs)} ({100*cls_stable/len(rs):.0f}%)")
