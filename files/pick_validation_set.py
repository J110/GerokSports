"""Pick 15 deliveries from the tier-1 set for Cricbuzz validation.

Selection criteria:
  - 10 with Gemini's modal answer (good_length / outside_off /
    along_ground / offside) — to test modal-class precision
  - 5 with non-modal answers — to test whether Gemini can be right
    when it doesn't fall back to the prior
  - Spread evenly across the ~2.5 hour match timespan
  - Skip rows that are obviously contaminated or have no parsed answer

Output: validation_set.json + validation_set.html (contact sheet)
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent
SNAP = ROOT / "logs/deliveries/snapshot_20260417_postkill_222206"
OUT_J = ROOT / "validation_set.json"
OUT_H = ROOT / "audit_v1/validation_set.html"

TIER1 = json.loads((ROOT / "tier1_deliveries.json").read_text())
GEM   = json.loads((ROOT / "results_gemini_full.json").read_text())
GEM_BY_ID = {r["id"]: r for r in GEM}

MODAL = ("good_length", "outside_off", "along_ground", "offside")


def gem_tuple(p):
    return (p.get("length"), p.get("line"),
            p.get("shot"), p.get("direction"))


# attach gemini prediction to each tier-1 row
rows = []
for r in TIER1:
    g = GEM_BY_ID.get(r["id"])
    if not g or not g.get("parsed"):
        continue
    p = g["parsed"]
    if p.get("is_delivery") is False:
        continue
    rows.append({**r, "gemini": p, "is_modal": gem_tuple(p) == MODAL})

# sort by ts, then split into time buckets so the picks span the match
rows.sort(key=lambda r: r["ts"])
print(f"{len(rows)} candidates; "
      f"{sum(1 for r in rows if r['is_modal'])} modal-answer, "
      f"{sum(1 for r in rows if not r['is_modal'])} non-modal")
print()

# select 10 modal + 5 non-modal, evenly spread across time
modal = [r for r in rows if r["is_modal"]]
nonmodal = [r for r in rows if not r["is_modal"]]


def take_evenly(seq, k):
    if k >= len(seq): return seq
    step = len(seq) / k
    return [seq[int(i * step)] for i in range(k)]


# detect innings break = largest >= 15 min gap between consecutive deliveries
gap_idx = 0
best = 0
prev = None
for i, r in enumerate(rows):
    cur = datetime.fromisoformat(r["ts"])
    if prev:
        delta = (cur - prev).total_seconds() / 60
        if delta >= 15 and delta > best:
            best = delta
            gap_idx = i
    prev = cur
innings_break = rows[gap_idx]["ts"] if gap_idx else None
print(f"Innings break detected at: {innings_break} ({best:.1f} min gap)")
print()


def is_inn1(r):
    return not innings_break or r["ts"] < innings_break


inn1_modal    = [r for r in modal    if is_inn1(r)]
inn2_modal    = [r for r in modal    if not is_inn1(r)]
inn1_nonmodal = [r for r in nonmodal if is_inn1(r)]
inn2_nonmodal = [r for r in nonmodal if not is_inn1(r)]
print(f"  KKR (inn 1): {len(inn1_modal)} modal + "
      f"{len(inn1_nonmodal)} non-modal")
print(f"  GT  (inn 2): {len(inn2_modal)} modal + "
      f"{len(inn2_nonmodal)} non-modal")
print()

# Stratified pick across innings AND modal/non-modal
pick = (take_evenly(inn1_modal, 5) +
        take_evenly(inn1_nonmodal, 3) +
        take_evenly(inn2_modal, 4) +
        take_evenly(inn2_nonmodal, 3))
pick.sort(key=lambda r: r["ts"])
n_kkr = sum(1 for r in pick if is_inn1(r))
print(f"Picked {len(pick)}: KKR={n_kkr} / GT={len(pick)-n_kkr}, "
      f"modal={sum(1 for r in pick if r['is_modal'])} / "
      f"non-modal={sum(1 for r in pick if not r['is_modal'])}")
print()

# build the json
out = []
for r in pick:
    p = r["gemini"]
    out.append({
        "id": r["id"],
        "ts": r["ts"],
        "innings": ("KKR" if (not innings_break or r["ts"] < innings_break)
                    else "GT"),
        "runs_scored": r.get("runs"),
        "pipeline_pred": r.get("pred_raw"),
        "gemini_pred": {
            "length": p.get("length"),
            "line": p.get("line"),
            "shot": p.get("shot"),
            "direction": p.get("direction"),
            "phase": p.get("phase_visible"),
            "confidence": p.get("confidence"),
            "narrative": p.get("narrative"),
        },
        "is_modal": r["is_modal"],
        "cricbuzz_label": None,  # to be filled by hand
        "cricbuzz_text": None,
    })
OUT_J.write_text(json.dumps(out, indent=2))
print(f"Wrote {OUT_J}")


# ---- HTML contact sheet ----------------------------------------------
def img(p):
    return "../" + str(p.relative_to(ROOT)) if p.exists() else ""

html = ["""<!doctype html><html><head><meta charset='utf-8'>
<title>Cricbuzz validation set (15 deliveries)</title>
<style>
body{font-family:system-ui;background:#0e1117;color:#e6edf3;
     max-width:1500px;margin:0 auto;padding:20px}
h1,h2{color:#7ee787}
.row{display:flex;gap:8px;margin:6px 0;
     border-top:1px solid #30363d;padding-top:10px}
.row img{width:260px;height:146px;object-fit:cover;border-radius:4px}
.meta{flex:1;font-size:13px;line-height:1.5}
.tag{display:inline-block;padding:1px 6px;margin:0 2px;
     border-radius:3px;background:#21262d;font-size:11px}
.modal{background:#5a4d1d;color:#ffd33d}
.nonmodal{background:#1d4a5a;color:#79c0ff}
.kkr{background:#3a1f5a;color:#d2a8ff}
.gt{background:#1f5a3a;color:#7ee787}
.gem{color:#fc9}
.pipe{color:#9d9}
hr{border:none;border-top:1px solid #30363d;margin:24px 0}
</style></head><body>"""]

modal_count = sum(1 for r in pick if r["is_modal"])
html.append(f"<h1>Cricbuzz validation set</h1>")
html.append(f"<p><b>{len(pick)}</b> deliveries · "
            f"<b>{modal_count}</b> with Gemini's modal answer · "
            f"<b>{len(pick)-modal_count}</b> non-modal · "
            f"sorted by time of day.</p>")
html.append("<p>For each, manually look up the corresponding ball in "
            "Cricbuzz commentary and compare against Gemini's prediction. "
            "Match by <b>over.ball + runs scored + innings</b>.</p>")

for i, r in enumerate(pick, 1):
    p = r["gemini"]
    inn = "KKR" if (not innings_break or r["ts"] < innings_break) else "GT"
    cls_inn = "kkr" if inn == "KKR" else "gt"
    cls_mod = "modal" if r["is_modal"] else "nonmodal"
    html.append("<div class='row'>")
    for fname in ("moment_start.jpg", "moment_key.jpg", "moment_end.jpg"):
        fp = SNAP / r["id"] / fname
        if fp.exists():
            html.append(f"<img src='{img(fp)}'>")
    html.append(f"<div class='meta'>"
                f"<b>#{i:>2}  {r['id']}</b>  "
                f"<span class='tag {cls_inn}'>{inn} innings</span> "
                f"<span class='tag {cls_mod}'>"
                f"{'MODAL' if r['is_modal'] else 'non-modal'}</span><br>"
                f"<b>ts:</b> {r['ts']}  ·  "
                f"<b>runs scored:</b> {r.get('runs')}<br>"
                f"<span class='gem'><b>gemini:</b></span> "
                f"<span class='tag'>{p.get('length')}</span>"
                f"<span class='tag'>{p.get('line')}</span>"
                f"<span class='tag'>{p.get('shot')}</span>"
                f"<span class='tag'>{p.get('direction')}</span>"
                f"  <span class='tag'>conf {p.get('confidence')}</span>  "
                f"<span class='tag'>phase {p.get('phase_visible')}</span>"
                f"<br><i>narr:</i> {p.get('narrative')}<br>"
                f"<span class='pipe'><b>pipeline:</b> "
                f"{r.get('pred_raw')}</span>"
                f"</div></div>")

html.append("</body></html>")
OUT_H.parent.mkdir(parents=True, exist_ok=True)
OUT_H.write_text("".join(html))
print(f"Wrote {OUT_H}")
