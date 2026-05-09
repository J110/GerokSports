"""Parse tier-1 contact sheet into a structured list of deliveries."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
SHEET = ROOT / "logs/deliveries/snapshot_20260417_postkill_222206/contact_sheet_tier1.html"
OUT = ROOT / "tier1_deliveries.json"

text = SHEET.read_text()

# Each delivery block has id + ts + predicted line.  Use a non-greedy
# multi-line regex to capture them in order.
pattern = re.compile(
    r'<div class="id">#\s*\d+\s+(delivery_\d+)</div>\s*'
    r'<div>ts:\s*([^<]+)</div>\s*'
    r'<div>dets:\s*(\d+),\s*flight:\s*(\d+),\s*post-shot:\s*(\d+)</div>\s*'
    r'<div>runs:\s*([^<]*)</div>\s*'
    r'<div class="pred">predicted:\s*([^<]+?)\s*</div>',
    re.DOTALL)

rows = []
for m in pattern.finditer(text):
    pred = m.group(7).strip()
    parts = [p.strip() for p in re.split(r'/|→', pred)]
    length = parts[0] if len(parts) > 0 else ""
    line = parts[1] if len(parts) > 1 else ""
    shot = parts[2] if len(parts) > 2 else ""
    direction = parts[3] if len(parts) > 3 else ""
    rows.append({
        "id": m.group(1),
        "ts": m.group(2).strip(),
        "dets": int(m.group(3)),
        "flight": int(m.group(4)),
        "post_shot": int(m.group(5)),
        "runs": m.group(6).strip(),
        "pred_raw": pred,
        "length": length,
        "line": line,
        "shot": shot,
        "direction": direction,
    })

print(f"Parsed {len(rows)} tier-1 deliveries")
for r in rows[:6]:
    print(f"  {r['id']}  {r['runs']:>4} runs  {r['pred_raw']}")
OUT.write_text(json.dumps(rows, indent=2))
print(f"Wrote {OUT}")
