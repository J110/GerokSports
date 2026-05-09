"""Analyse Moondream stump-box geometry: TPs vs FPs.

Goal: see if any geometric tightening (size, y-position, etc.) can
separate the 2 TPs from the 31 false-positive admits.
"""
import json
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).parent
AUDIT = ROOT / "audit_v1"
rows = json.loads((AUDIT / "results_moondream.json").read_text())

print(f"{'frame':<5} {'truth':<26} {'cx':>6} {'cy':>6} "
      f"{'w':>6} {'h':>6} {'area':>7}")
print("-" * 70)

groups = {"tp": [], "post_shot": [], "between_play": [],
          "aerial": [], "closeup": [], "fielder_chase": [], "replay": [],
          "advertisement": []}
for r in rows:
    if not r.get("primary"):
        continue
    p = r["primary"]
    cx = (p["x_min"] + p["x_max"]) / 2
    cy = (p["y_min"] + p["y_max"]) / 2
    w = p["x_max"] - p["x_min"]
    h = p["y_max"] - p["y_min"]
    area = w * h
    truth = r["truth"]
    key = "tp" if truth == "tp_bowlers_end_release" else truth
    groups.setdefault(key, []).append(
        {"cx": cx, "cy": cy, "w": w, "h": h, "area": area, "frame": r["frame"]})
    print(f"{r['frame']:<5} {truth:<26} "
          f"{cx:>6.3f} {cy:>6.3f} {w:>6.3f} {h:>6.3f} {area:>7.4f}")

print("\n=== Per-category stump-box stats (median) ===")
print(f"{'category':<20} {'n':>3} {'cx':>7} {'cy':>7} "
      f"{'w':>7} {'h':>7} {'area':>8}")
for cat, items in groups.items():
    if not items:
        continue
    print(f"{cat:<20} {len(items):>3} "
          f"{median(i['cx'] for i in items):>7.3f} "
          f"{median(i['cy'] for i in items):>7.3f} "
          f"{median(i['w'] for i in items):>7.3f} "
          f"{median(i['h'] for i in items):>7.3f} "
          f"{median(i['area'] for i in items):>8.4f}")
