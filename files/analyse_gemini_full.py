"""Analyse the full 60-delivery Gemini run.

Two questions, per the user's framing:

1. REJECTION QUALITY.  When is_delivery=false, is Gemini correct?
   Surface each rejection with its 3 frames so it can be spot-checked.

2. CONFIDENCE CALIBRATION.  Does conf=0.9 actually mean "more right"?
   Bucket predictions by confidence, then for each bucket compute:
     - agreement with the pipeline label (a noisy proxy for truth)
     - prediction homogeneity (all-the-same → low information)
     - share rejected
   Render an HTML contact sheet so a human can verify directly.
"""
from __future__ import annotations
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
SNAP = ROOT / "logs/deliveries/snapshot_20260417_postkill_222206"
OUT_HTML = ROOT / "audit_v1/gemini_full_contact_sheet.html"
OUT_HTML.parent.mkdir(parents=True, exist_ok=True)

ROWS = json.loads((ROOT / "results_gemini_full.json").read_text())
PARSED = [r for r in ROWS if r.get("parsed")]


# ---------- helpers ----------------------------------------------------
def conf_bucket(c):
    if c is None:
        return "none"
    try:
        c = float(c)
    except Exception:
        return "none"
    if c >= 0.9:
        return "0.90+"
    if c >= 0.8:
        return "0.80-0.89"
    if c >= 0.7:
        return "0.70-0.79"
    return "<0.70"


def short(s, n=80):
    s = (s or "").replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def pipeline_label(r):
    p = r.get("pipeline_pred") or ""
    return short(p, 70)


# ---------- 1. rejection quality --------------------------------------
rejected = [r for r in PARSED
            if r["parsed"].get("is_delivery") is False]

print("=" * 72)
print(f"REJECTION QUALITY  ({len(rejected)} of {len(PARSED)} rejected"
      f"  = {100 * len(rejected) / max(1, len(PARSED)):.1f}%)")
print("=" * 72)
for r in rejected:
    p = r["parsed"]
    print(f"  {r['id']}  conf={p.get('confidence')}  "
          f"phase={p.get('phase_visible')}")
    print(f"      gemini : {short(p.get('narrative'), 110)}")
    print(f"      pipe   : {pipeline_label(r)}")


# ---------- 2. label homogeneity --------------------------------------
print()
print("=" * 72)
print("LABEL HOMOGENEITY  (every delivery's structured label)")
print("=" * 72)

accepted = [r for r in PARSED
            if r["parsed"].get("is_delivery") is not False]
combo = Counter()
for r in accepted:
    p = r["parsed"]
    combo[(p.get("length"), p.get("line"),
           p.get("shot"), p.get("direction"))] += 1
print(f"  unique (length, line, shot, direction) tuples: {len(combo)}")
for k, n in combo.most_common():
    print(f"    {n:>3}  {k}")
top_share = combo.most_common(1)[0][1] / max(1, len(accepted))
print(f"  top-tuple share: {top_share*100:.1f}%   "
      f"(>70% = Gemini is mostly outputting the modal answer, "
      f"low information)")


# ---------- 3. confidence calibration --------------------------------
print()
print("=" * 72)
print("CONFIDENCE CALIBRATION  (vs noisy pipeline label as proxy)")
print("=" * 72)
buckets = defaultdict(list)
for r in accepted:
    buckets[conf_bucket(r["parsed"].get("confidence"))].append(r)

for b in ["0.90+", "0.80-0.89", "0.70-0.79", "<0.70", "none"]:
    rs = buckets.get(b, [])
    if not rs:
        continue
    # crude agreement: does the gemini length appear inside the pipeline
    # label string (since the pipeline records prose like "good length, off")
    agree_len = 0
    agree_dir = 0
    for r in rs:
        pp = (r.get("pipeline_pred") or "").lower()
        gl = str(r["parsed"].get("length", "")).replace("_", " ")
        gd = str(r["parsed"].get("direction", ""))
        if gl and gl != "unknown" and gl in pp:
            agree_len += 1
        if gd and gd != "unknown" and gd in pp:
            agree_dir += 1
    print(f"  {b:>9}  n={len(rs):>3}   "
          f"len-agree={agree_len:>2}/{len(rs):<2} "
          f"({100*agree_len/len(rs):>4.0f}%)   "
          f"dir-agree={agree_dir:>2}/{len(rs):<2} "
          f"({100*agree_dir/len(rs):>4.0f}%)")


# ---------- 4. HTML contact sheet ------------------------------------
def img_uri(p):
    # Render with relative path so the HTML stays portable next to the
    # snapshot directory.
    return "../" + str(p.relative_to(ROOT))


parts = ["""<!doctype html><html><head><meta charset='utf-8'>
<title>Gemini full-run contact sheet</title>
<style>
body {font-family:system-ui;background:#0e1117;color:#e6edf3;
      max-width:1400px;margin:0 auto;padding:20px;}
h1, h2 {color:#7ee787;}
.row {display:flex;gap:8px;margin:6px 0;
      border-top:1px solid #30363d;padding-top:6px;}
.row img {width:230px;height:130px;object-fit:cover;border-radius:4px;}
.meta {flex:1;font-size:13px;line-height:1.4;}
.bad {color:#ff7b72;font-weight:bold;}
.warn {color:#ffd33d;}
.good {color:#7ee787;}
.tag {display:inline-block;padding:1px 6px;margin:0 2px;
      border-radius:3px;background:#21262d;font-size:11px;}
.conf-low{background:#5a1d1d;}
.conf-mid{background:#5a4d1d;}
.conf-high{background:#1d5a25;}
</style></head><body>"""]
parts.append(f"<h1>Gemini full-run audit · "
             f"{len(PARSED)}/{len(ROWS)} parsed</h1>")
parts.append(f"<p>Rejected: <b>{len(rejected)}</b> "
             f"({100*len(rejected)/max(1,len(PARSED)):.1f}%) · "
             f"top-tuple share: <b>{top_share*100:.1f}%</b></p>")


def render(group, title, sort_key):
    parts.append(f"<h2>{title} · n={len(group)}</h2>")
    for r in sorted(group, key=sort_key):
        p = r["parsed"]
        c = p.get("confidence")
        cls = ("conf-high" if (c or 0) >= 0.9
               else "conf-mid" if (c or 0) >= 0.7
               else "conf-low")
        parts.append("<div class='row'>")
        for fname in ("moment_start.jpg", "moment_key.jpg",
                       "moment_end.jpg"):
            fp = SNAP / r["id"] / fname
            if fp.exists():
                parts.append(f"<img src='{img_uri(fp)}'>")
        parts.append(
            f"<div class='meta'><b>{r['id']}</b>  "
            f"<span class='tag {cls}'>conf {c}</span> "
            f"<span class='tag'>{p.get('phase_visible')}</span><br>"
            f"<span class='tag'>{p.get('length')}</span>"
            f"<span class='tag'>{p.get('line')}</span>"
            f"<span class='tag'>{p.get('shot')}</span>"
            f"<span class='tag'>{p.get('direction')}</span><br>"
            f"<i>gem:</i> {short(p.get('narrative'), 200)}<br>"
            f"<i>pipe:</i> {pipeline_label(r)}</div>"
        )
        parts.append("</div>")


parts.append("<hr><h1>1 · REJECTIONS  (is_delivery=false)</h1>")
parts.append("<p>Spot-check these against the frames. Each one Gemini "
             "claims is NOT a real delivery — verify by eye.</p>")
render(rejected, "Rejected windows", lambda r: r["id"])

# Also append the negative-control results so the user can see them.
NEG_PATH = ROOT / "results_gemini_negatives.json"
if NEG_PATH.exists():
    neg = json.loads(NEG_PATH.read_text())
    neg_parsed = [r for r in neg if r.get("parsed")]
    parts.append("<hr><h1>1b · NEGATIVE-CONTROL TEST "
                 "(failed_* triplets)</h1>")
    parts.append(f"<p>{len(neg_parsed)} pipeline-rejected triplets sent "
                 "to Gemini.  Rejection here = correct.  Acceptance "
                 "here = either Gemini error OR a real delivery the "
                 "pipeline lost.</p>")

    def render_neg(rows, title):
        parts.append(f"<h2>{title} · n={len(rows)}</h2>")
        for r in rows:
            p = r["parsed"]
            c = p.get("confidence")
            cls = ("conf-high" if (c or 0) >= 0.9
                   else "conf-mid" if (c or 0) >= 0.7
                   else "conf-low")
            parts.append("<div class='row'>")
            for fname in ("failed_start.jpg", "failed_mid.jpg",
                           "failed_end.jpg"):
                fp = SNAP / r["id"] / fname
                if fp.exists():
                    parts.append(f"<img src='{img_uri(fp)}'>")
            label = ("REJECT" if p.get("is_delivery") is False
                     else "ACCEPT")
            parts.append(
                f"<div class='meta'><b>{r['id']}</b> [failed_*]  "
                f"<span class='tag {cls}'>{label} conf {c}</span><br>"
                f"<i>gem:</i> {short(p.get('narrative'), 220)}</div>"
            )
            parts.append("</div>")

    neg_rej = [r for r in neg_parsed
               if r["parsed"].get("is_delivery") is False]
    neg_acc = [r for r in neg_parsed
               if r["parsed"].get("is_delivery") is not False]
    render_neg(neg_rej, "Correctly rejected (true negatives)")
    render_neg(neg_acc, "ACCEPTED — likely real deliveries pipeline lost")

parts.append("<hr><h1>2 · ACCEPTED, by confidence</h1>")
for b in ["0.90+", "0.80-0.89", "0.70-0.79", "<0.70", "none"]:
    rs = buckets.get(b, [])
    if rs:
        render(rs, f"Confidence {b}", lambda r: r["id"])

parts.append("</body></html>")
OUT_HTML.write_text("".join(parts))
print(f"\nWrote {OUT_HTML}")
