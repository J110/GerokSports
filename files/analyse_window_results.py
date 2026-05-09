"""Consolidate Gemini results from both runs and compare to existing
pipeline tier-1 predictions."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent

# Combine results from both runs
def parse_json_from_text(text):
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


# Load primary results (run 2 with retry)
primary = json.loads((ROOT / "results_gemini_only.json").read_text())
# Load run 1 (combined results) if present
combined_path = ROOT / "results_window_compare.json"
combined = json.loads(combined_path.read_text()) if combined_path.exists() else {}

# Build map id -> best result (prefer parsed)
by_id = {}
for r in primary:
    if r.get("parsed"):
        by_id[r["id"]] = {"source": "run2", "parsed": r["parsed"],
                          "raw": r["raw"], "wall_ms": r["wall_ms"],
                          "pipeline_pred": r["pipeline_pred"],
                          "pipeline_runs": r["pipeline_runs"]}

for r in combined.get("gemini", []):
    if r["id"] in by_id:
        continue
    parsed = parse_json_from_text(r.get("raw", ""))
    if parsed:
        # Find pipeline pred from primary
        match = next((p for p in primary if p["id"] == r["id"]), None)
        by_id[r["id"]] = {"source": "run1", "parsed": parsed,
                          "raw": r["raw"], "wall_ms": r["wall_ms"],
                          "pipeline_pred": match["pipeline_pred"] if match else "?",
                          "pipeline_runs": match["pipeline_runs"] if match else "?"}

print(f"Successful Gemini predictions: {len(by_id)} of 12 sampled deliveries")
print()
print(f"{'delivery':<14} {'time':<6} {'gemini':<60}")
print(f"{'':14} {'':6} {'pipeline':<60}")
print("-" * 90)

# Field-level comparison
fields = ["length", "line", "shot", "direction"]
agree = {f: 0 for f in fields}
total = 0

for did in sorted(by_id):
    r = by_id[did]
    p = r["parsed"]
    gem = (f"{p.get('length','?')} / {p.get('line','?')} / "
           f"{p.get('shot','?')} / {p.get('direction','?')}  "
           f"(conf={p.get('confidence','?')})")
    pipe = r["pipeline_pred"]
    pipe_parts = [s.strip() for s in re.split(r'/|→', pipe)]
    pipe_dict = {
        "length": pipe_parts[0] if len(pipe_parts) > 0 else "",
        "line": pipe_parts[1] if len(pipe_parts) > 1 else "",
        "shot": pipe_parts[2] if len(pipe_parts) > 2 else "",
        "direction": pipe_parts[3] if len(pipe_parts) > 3 else "",
    }
    print(f"{did:<14} {r['wall_ms']/1000:>5.1f}s GEM: {gem}")
    print(f"{'':14} {'':6} PIPE: {pipe}")
    print(f"{'':14} {'':6} runs: {r['pipeline_runs']}")
    if p.get("is_delivery") is False:
        print(f"{'':14} {'':6} (gemini said NOT a delivery)")
    print(f"{'':14} {'':6} narrative: {p.get('narrative','')[:120]}")
    total += 1
    for f in fields:
        if (p.get(f) or "").lower() == pipe_dict[f].lower():
            agree[f] += 1
    print()

print("=" * 90)
print(f"Field-level agreement (Gemini vs existing pipeline tier-1):")
for f in fields:
    pct = (agree[f] * 100 / total) if total else 0
    print(f"  {f:<10} {agree[f]}/{total} = {pct:.0f}%")

# Latency stats
times = [r["wall_ms"] for r in by_id.values() if r["wall_ms"] > 1000]
times.sort()
if times:
    mean = sum(times) / len(times)
    p50 = times[len(times) // 2]
    p95 = times[int(len(times) * 0.95)]
    print(f"\nGemini latency: mean {mean/1000:.1f}s  p50 {p50/1000:.1f}s  p95 {p95/1000:.1f}s")
