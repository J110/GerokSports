"""Build a single clean HTML page showing every tier-1 delivery
with: 3 frames, timestamp, innings, runs, Gemini prediction,
pipeline prediction.  Simple, scrollable, no fluff.
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent
SNAP = ROOT / "logs/deliveries/snapshot_20260417_postkill_222206"
OUT  = ROOT / "audit_v1/all_deliveries.html"

TIER1 = json.loads((ROOT / "tier1_deliveries.json").read_text())
GEM   = json.loads((ROOT / "results_gemini_full.json").read_text())
GEM_BY = {r["id"]: r for r in GEM}

MODAL = ("good_length", "outside_off", "along_ground", "offside")

# detect innings break
ts_sorted = sorted(TIER1, key=lambda r: r["ts"])
innings_break = None
best = 0
prev = None
for r in ts_sorted:
    cur = datetime.fromisoformat(r["ts"])
    if prev:
        d = (cur - prev).total_seconds() / 60
        if d >= 15 and d > best:
            best = d
            innings_break = r["ts"]
    prev = cur


def innings(r): return "KKR" if (not innings_break or r["ts"] < innings_break) else "GT"


def img(p):
    # Relative to ROOT (= files/), so works under
    # `python -m http.server` started from files/
    return "/" + str(p.relative_to(ROOT)) if p.exists() else ""


rows = sorted(TIER1, key=lambda r: r["ts"])
n_kkr = sum(1 for r in rows if innings(r) == "KKR")
n_gt  = sum(1 for r in rows) - n_kkr


html = ["""<!doctype html><html><head><meta charset='utf-8'>
<title>All tier-1 deliveries · GT vs KKR · 17 Apr 2026</title>
<style>
*{box-sizing:border-box}
body{font-family:system-ui;background:#0e1117;color:#e6edf3;
     margin:0;padding:16px;max-width:1600px;margin:0 auto}
h1{font-size:20px;color:#7ee787;margin:8px 0}
.summary{font-size:13px;color:#9aa4af;margin-bottom:14px}
.row{display:grid;
     grid-template-columns:200px 200px 200px 1fr;
     gap:8px;padding:10px 0;border-top:1px solid #21262d;
     align-items:center}
.row img{width:100%;height:112px;object-fit:cover;border-radius:4px;
         background:#000;border:1px solid #30363d}
.meta{font-size:12px;line-height:1.5}
.idx{color:#7ee787;font-weight:bold;margin-right:6px}
.id{font-weight:bold;color:#e6edf3;font-size:13px}
.tag{display:inline-block;padding:1px 6px;margin:1px 2px;border-radius:3px;
     background:#21262d;font-size:11px;color:#c9d1d9}
.kkr{background:#3a1f5a;color:#d2a8ff}
.gt{background:#1f5a3a;color:#7ee787}
.modal{background:#5a4d1d;color:#ffd33d}
.reject{background:#5a1d1d;color:#ff7b72}
.gem{color:#fc9;margin-top:4px}
.pipe{color:#9d9}
.narr{color:#9aa4af;margin-top:3px;font-style:italic;font-size:11px}
.controls{position:sticky;top:0;background:#0e1117;padding:8px 0;
          border-bottom:1px solid #30363d;z-index:10;margin-bottom:8px}
.controls label{margin-right:14px;font-size:13px;color:#c9d1d9}
.controls input{margin-right:4px}
</style></head><body>"""]

html.append(f"<h1>All tier-1 deliveries · GT vs KKR · IPL 2026 Match 25</h1>")
html.append(f"<div class='summary'><b>{len(rows)}</b> deliveries · "
            f"<b>{n_kkr}</b> KKR innings · <b>{n_gt}</b> GT innings · "
            f"innings break around <b>{innings_break[11:] if innings_break else '—'}</b></div>")

# filter controls (toggle innings + show only modal/non-modal)
html.append("""<div class='controls'>
  <label><input type='checkbox' id='kkr' checked onchange='upd()'>KKR innings</label>
  <label><input type='checkbox' id='gt'  checked onchange='upd()'>GT innings</label>
  <label><input type='checkbox' id='m'   checked onchange='upd()'>modal-answer (Gemini said good_length/outside_off/along_ground/offside)</label>
  <label><input type='checkbox' id='nm'  checked onchange='upd()'>non-modal answers</label>
  <label><input type='checkbox' id='rj'  checked onchange='upd()'>rejected (is_delivery=false)</label>
  <span id='count' style='color:#9aa4af;margin-left:14px'></span>
</div>""")

for i, r in enumerate(rows, 1):
    g = GEM_BY.get(r["id"], {}).get("parsed") or {}
    inn = innings(r)
    cls_inn = "kkr" if inn == "KKR" else "gt"
    is_rej = g.get("is_delivery") is False
    is_modal = (g.get("length"), g.get("line"),
                g.get("shot"), g.get("direction")) == MODAL
    classes = [cls_inn]
    if is_rej: classes.append("reject")
    elif is_modal: classes.append("modal")
    else: classes.append("nonmodal")

    flags = []
    if is_rej: flags.append("<span class='tag reject'>REJECTED</span>")
    elif is_modal: flags.append("<span class='tag modal'>MODAL</span>")
    else: flags.append("<span class='tag'>non-modal</span>")
    flags.append(f"<span class='tag {cls_inn}'>{inn}</span>")

    gem_html = ""
    if g:
        if is_rej:
            gem_html = ("<div class='gem'><b>gemini:</b> "
                        "<span class='tag reject'>not a delivery</span></div>")
        else:
            gem_html = (f"<div class='gem'><b>gemini:</b> "
                        f"<span class='tag'>{g.get('length')}</span>"
                        f"<span class='tag'>{g.get('line')}</span>"
                        f"<span class='tag'>{g.get('shot')}</span>"
                        f"<span class='tag'>{g.get('direction')}</span>"
                        f"<span class='tag'>conf {g.get('confidence')}</span>"
                        f"<span class='tag'>{g.get('phase_visible')}</span></div>")
        if g.get("narrative"):
            gem_html += f"<div class='narr'>{g['narrative']}</div>"
    else:
        gem_html = "<div class='gem'><b>gemini:</b> <i>no result</i></div>"

    html.append(f"<div class='row' data-tags='{' '.join(classes)}'>")
    for fname in ("moment_start.jpg", "moment_key.jpg", "moment_end.jpg"):
        fp = SNAP / r["id"] / fname
        if fp.exists():
            html.append(f"<a href='{img(fp)}' target='_blank'>"
                        f"<img src='{img(fp)}' loading='lazy'></a>")
        else:
            html.append("<div></div>")
    html.append(
        f"<div class='meta'>"
        f"<div><span class='idx'>#{i}</span>"
        f"<span class='id'>{r['id']}</span>  "
        f"{' '.join(flags)}</div>"
        f"<div>ts: {r['ts'][11:]} · runs: <b>{r.get('runs')}</b> · "
        f"flight: {r.get('flight')} · post-shot: {r.get('post_shot')}</div>"
        f"<div class='pipe'><b>pipeline:</b> {r.get('pred_raw')}</div>"
        f"{gem_html}"
        f"</div></div>"
    )

html.append("""<script>
function upd(){
  const inc = {
    kkr: document.getElementById('kkr').checked,
    gt:  document.getElementById('gt').checked,
    m:   document.getElementById('m').checked,
    nm:  document.getElementById('nm').checked,
    rj:  document.getElementById('rj').checked,
  };
  const rows = document.querySelectorAll('.row');
  let shown = 0;
  rows.forEach(r => {
    const t = r.dataset.tags;
    const isKKR = t.includes('kkr'), isGT = t.includes('gt');
    const isMod = t.includes('modal') && !t.includes('reject');
    const isNon = t.includes('nonmodal');
    const isRej = t.includes('reject');
    let show = (isKKR && inc.kkr) || (isGT && inc.gt);
    if (show) {
      if (isRej && !inc.rj) show = false;
      else if (isMod && !inc.m) show = false;
      else if (isNon && !inc.nm) show = false;
    }
    r.style.display = show ? '' : 'none';
    if (show) shown++;
  });
  document.getElementById('count').textContent =
      shown + ' / ' + rows.length + ' visible';
}
upd();
</script></body></html>""")

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("".join(html))
print(f"Wrote {OUT}")
print(f"  {len(rows)} deliveries  ·  KKR={n_kkr} GT={n_gt}")
