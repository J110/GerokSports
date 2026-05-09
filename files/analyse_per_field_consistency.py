"""Per-field stability across 3 Gemini calls on the same delivery.

Hypothesis: length is the LEAST stable field because 3 frames can't
show a bounce-to-pitch reference; line / shot / direction are MORE
stable because they're determinable from spatial cues in single frames.

If hypothesis holds → static frames cannot do length, video required.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
CONS = json.loads((ROOT / "results_gemini_consistency.json").read_text())

FIELDS = ["is_delivery", "phase_visible", "length",
          "line", "shot", "direction"]

by_id = defaultdict(list)
for r in CONS:
    if r.get("parsed"):
        by_id[r["id"]].append(r["parsed"])

stable = Counter()
unstable_examples = defaultdict(list)
n_full = 0
for did, calls in by_id.items():
    if len(calls) < 3:
        continue
    n_full += 1
    for f in FIELDS:
        vals = [c.get(f) for c in calls]
        if len(set(vals)) == 1:
            stable[f] += 1
        else:
            unstable_examples[f].append((did, vals))

print(f"Per-field stability across 3 calls (n={n_full} deliveries):\n")
print(f"  {'field':<15}  stable    unstable")
print(f"  {'-'*15}  {'------':<8}  {'--------':<8}")
for f in FIELDS:
    s = stable[f]
    u = n_full - s
    pct = 100 * s / n_full
    bar = "█" * int(pct/5)
    print(f"  {f:<15}  {s:>2}/{n_full} ({pct:>3.0f}%)  {u:>2}     {bar}")

print(f"\nUnstable examples per field:")
for f in FIELDS:
    if not unstable_examples[f]:
        continue
    print(f"\n  {f}:")
    for did, vals in unstable_examples[f]:
        print(f"    {did:<14}  {' / '.join(str(v) for v in vals)}")

print(f"\n{'='*60}")
print("Interpretation:")
print(f"{'='*60}")
print("If length is the LEAST stable field → 3 frames cannot")
print("determine length → video input is REQUIRED for length.")
print("If line/shot/direction are MOST stable → 3 frames work")
print("for those fields.")
