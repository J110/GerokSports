"""Validation step 1 for the unified Scout-tagged-frame architecture.

Captures ~80 frames from the live broadcast at varied intervals, calls
Scout with a *focused* 4-category prompt, and writes both:

  logs/scout_4cat_validation/<ts>/results.jsonl
  logs/scout_4cat_validation/<ts>/inspect.html

inspect.html is a side-by-side gallery of every frame + Scout's tag +
short reason — designed so a human can scan in ~10 minutes and assign a
ground-truth label (delivery / live / replay_scorecard / ads).

Why a new prompt rather than re-using SCOUT_PROMPT:
  - SCOUT_PROMPT.camera_view conflates "delivery in progress" with
    "bowler walking back" (both are bowlers_end).  The unified
    architecture needs those split.
  - SCOUT_PROMPT also reads the strip + overlays + action; that's
    extra work + tokens we don't need for this experiment.

Run:
    .venv/bin/python validate_scout_4cat.py --n 80 --interval 2.0
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from groq import AsyncGroq

from eyes.capture.frame_source import FrameSource
from eyes.config import GROQ_API_KEY, GROQ_PRIMARY_MODEL


PROMPT_4CAT = """\
You are watching a live IPL cricket broadcast.

Classify THIS SINGLE FRAME into exactly one of four categories:

1. "delivery" — the bowler is in their RUN-UP, in the LOADING action, or
   in the BALL-RELEASE motion right now.  The camera is the standard
   bowler's-end wide shot down the pitch.  The ball is either about to
   be delivered, in flight, or has just been struck.  This category is
   ONLY for the moment of action — not for the bowler walking back to
   his mark, not for the batter taking guard.

2. "live" — live game action that is NOT the delivery moment.  Examples:
   bowler walking back to the top of his mark, batter taking guard,
   fielder running after a ball, mid-off conversation, captain setting
   the field, square-of-the-wicket angle of a shot being chased,
   close-up of a player reaction.  Anything that's clearly the live
   feed but not the actual ball-being-bowled instant.

3. "replay_scorecard" — replay or slow-motion of an earlier moment, OR a
   full-screen broadcaster graphic (full scorecard, partnership graphic,
   stats card, "REPLAY" badge, slow-mo motion blur, sponsor card).

4. "ads" — commercial / advertisement break.  Includes brand logos,
   product shots, jingles, presenter-led ad slots.

Output EXACTLY this JSON on a single line, nothing else:
{"category": "<one of: delivery, live, replay_scorecard, ads>", \
"confidence": "<low|medium|high>", "reason": "<<= 12 words>"}
"""


CATEGORIES = ("delivery", "live", "replay_scorecard", "ads")


def encode_jpeg(frame: np.ndarray, max_w: int = 1280, q: int = 85) -> str:
    h, w = frame.shape[:2]
    if w > max_w:
        scale = max_w / w
        frame = cv2.resize(frame, (max_w, int(h * scale)),
                           interpolation=cv2.INTER_AREA)
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, q])
    return base64.b64encode(buf.tobytes()).decode("ascii")


async def call_scout(client: AsyncGroq, frame: np.ndarray) -> dict:
    img = encode_jpeg(frame)
    t0 = time.time()
    try:
        resp = await client.chat.completions.create(
            model=GROQ_PRIMARY_MODEL,
            temperature=0,
            max_tokens=120,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {
                         "url": f"data:image/jpeg;base64,{img}"}},
                    {"type": "text", "text": PROMPT_4CAT},
                ],
            }],
        )
        ms = (time.time() - t0) * 1000
        raw = resp.choices[0].message.content.strip()
    except Exception as e:
        return {"raw": "", "error": str(e), "ms": (time.time() - t0) * 1000}

    parsed = parse_response(raw)
    parsed["raw"] = raw
    parsed["ms"] = round(ms)
    return parsed


def parse_response(raw: str) -> dict:
    """Tolerant JSON parse — strip backticks/markdown if present."""
    txt = raw.strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:]
    txt = txt.strip()
    try:
        obj = json.loads(txt.splitlines()[0])
        cat = str(obj.get("category", "")).lower()
        if cat not in CATEGORIES:
            cat = "unknown"
        return {
            "category": cat,
            "confidence": str(obj.get("confidence", "")).lower(),
            "reason": str(obj.get("reason", ""))[:120],
        }
    except Exception:
        # Last-resort substring match
        for c in CATEGORIES:
            if c in txt.lower():
                return {"category": c, "confidence": "low",
                        "reason": "fallback parse"}
        return {"category": "unknown", "confidence": "low",
                "reason": "parse fail"}


def find_firefox_window() -> int | None:
    for w in FrameSource.list_windows():
        if "firefox" in w["owner"].lower():
            return w["id"]
    return None


async def main(n: int, interval: float) -> None:
    if not GROQ_API_KEY:
        raise SystemExit("GROQ_API_KEY missing")

    wid = find_firefox_window()
    if not wid:
        raise SystemExit("Firefox window not found — please open the broadcast.")
    print(f"Capturing from Firefox window id={wid}")

    fs = FrameSource(window_id=wid, fps=5)
    fs.start()
    await asyncio.sleep(1.0)
    if fs.get_latest() is None:
        raise SystemExit("No frame captured after 1s — is Firefox visible?")

    out_root = Path("logs/scout_4cat_validation")
    out_root.mkdir(parents=True, exist_ok=True)
    sess = out_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    sess.mkdir()
    img_dir = sess / "frames"
    img_dir.mkdir()
    print(f"Output: {sess}")

    client = AsyncGroq(api_key=GROQ_API_KEY, timeout=10)
    results: list[dict] = []

    for i in range(n):
        frame = fs.get_latest()
        if frame is None:
            print(f"  [{i:03d}] no frame, sleeping")
            await asyncio.sleep(interval)
            continue
        # Save the original capture for the gallery
        img_path = img_dir / f"f{i:03d}.jpg"
        cv2.imwrite(str(img_path), frame,
                    [cv2.IMWRITE_JPEG_QUALITY, 80])

        r = await call_scout(client, frame)
        r["i"] = i
        r["ts"] = time.time()
        r["path"] = str(img_path.relative_to(sess))
        results.append(r)
        print(f"  [{i:03d}] {r.get('category','?'):>17s} "
              f"conf={r.get('confidence','?'):>6s} "
              f"({r.get('ms','?'):>4}ms)  {r.get('reason','')[:60]}")

        with (sess / "results.jsonl").open("w") as f:
            for x in results:
                f.write(json.dumps(x) + "\n")

        await asyncio.sleep(interval)

    fs.stop()
    write_inspection_html(sess, results)
    write_summary(sess, results)
    print(f"\nDone. Open: {sess / 'inspect.html'}")


def write_summary(sess: Path, results: list[dict]) -> None:
    counts: dict[str, int] = {}
    for r in results:
        c = r.get("category", "unknown")
        counts[c] = counts.get(c, 0) + 1
    total = max(len(results), 1)
    lines = [f"  {c:>17s}: {n:>3d}  ({n*100/total:.0f}%)"
             for c, n in sorted(counts.items(), key=lambda kv: -kv[1])]
    print("\nScout-tagged distribution:")
    print("\n".join(lines))


def write_inspection_html(sess: Path, results: list[dict]) -> None:
    rows = []
    for r in results:
        cat = r.get("category", "?")
        conf = r.get("confidence", "?")
        reason = r.get("reason", "")
        path = r.get("path", "")
        cls = {
            "delivery": "del", "live": "liv",
            "replay_scorecard": "rep", "ads": "ad",
        }.get(cat, "unk")
        rows.append(
            f"""<div class="card {cls}" data-i="{r['i']}">
  <img src="{path}" />
  <div class="meta">
    <div class="tag">{cat}</div>
    <div class="conf">{conf} · {r.get('ms','?')}ms</div>
    <div class="reason">{reason}</div>
    <div class="label">
      <label>truth: <select onchange="setTruth({r['i']}, this.value)">
        <option value=""></option>
        <option value="delivery">delivery</option>
        <option value="live">live</option>
        <option value="replay_scorecard">replay_scorecard</option>
        <option value="ads">ads</option>
      </select></label>
    </div>
  </div>
</div>""")

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Scout 4-cat validation</title>
<style>
  body{{font-family:system-ui;margin:0;padding:16px;background:#111;color:#eee}}
  h1{{margin:0 0 12px 0;font-size:18px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}}
  .card{{background:#1c1c1f;border-radius:6px;overflow:hidden;border-left:4px solid #444}}
  .card.del{{border-left-color:#3fc26b}}
  .card.liv{{border-left-color:#5b9dff}}
  .card.rep{{border-left-color:#f0b04a}}
  .card.ad{{border-left-color:#e95b6a}}
  .card.unk{{border-left-color:#888}}
  .card img{{width:100%;height:auto;display:block;background:#000}}
  .meta{{padding:8px 10px;font-size:12px;line-height:1.3}}
  .tag{{font-weight:600;font-size:13px;text-transform:uppercase;letter-spacing:.04em}}
  .conf{{color:#888;margin:2px 0 4px 0}}
  .reason{{color:#bbb;font-style:italic}}
  .label{{margin-top:6px}}
  select{{background:#222;color:#eee;border:1px solid #444;padding:2px 4px}}
  #report{{position:fixed;top:8px;right:8px;background:#222;padding:10px;border-radius:6px;
           font-size:12px;max-width:320px;border:1px solid #444}}
  button{{background:#3fc26b;color:#000;border:0;padding:6px 12px;border-radius:4px;cursor:pointer;font-weight:600}}
</style></head>
<body>
<div id="report">
  <div><b>Scout 4-cat validation</b></div>
  <div>{len(results)} frames</div>
  <div id="prog">labelled: 0 / {len(results)}</div>
  <button onclick="report()">Compute accuracy</button>
  <pre id="result" style="white-space:pre-wrap;font-size:11px"></pre>
</div>
<h1>Scout 4-cat validation — {sess.name}</h1>
<div class="grid">
{''.join(rows)}
</div>
<script>
const truths = {{}};
function setTruth(i, v) {{
  if (v) truths[i] = v; else delete truths[i];
  document.getElementById('prog').textContent =
    'labelled: ' + Object.keys(truths).length + ' / {len(results)}';
}}
const preds = {json.dumps([{'i': r['i'], 'pred': r.get('category','unknown')} for r in results])};
function report() {{
  const cats = ['delivery','live','replay_scorecard','ads','unknown'];
  const conf = {{}}; cats.forEach(a=>{{conf[a]={{}}; cats.forEach(b=>conf[a][b]=0)}});
  let n = 0, ok = 0;
  preds.forEach(p => {{
    const t = truths[p.i];
    if (!t) return;
    n++;
    conf[t][p.pred] = (conf[t][p.pred] || 0) + 1;
    if (t === p.pred) ok++;
  }});
  let s = 'Labelled: ' + n + '/' + preds.length + '\\n';
  s += 'Accuracy: ' + (n ? (ok*100/n).toFixed(1) : 0) + '%\\n\\n';
  s += 'Confusion (rows=truth, cols=pred):\\n';
  s += 'truth\\\\pred'.padEnd(18);
  cats.forEach(c => s += c.padStart(10));
  s += '\\n';
  cats.forEach(t => {{
    s += t.padEnd(18);
    cats.forEach(p => s += String(conf[t][p]||0).padStart(10));
    s += '\\n';
  }});
  document.getElementById('result').textContent = s;
}}
</script></body></html>
"""
    (sess / "inspect.html").write_text(html)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=80)
    p.add_argument("--interval", type=float, default=2.0)
    args = p.parse_args()
    asyncio.run(main(args.n, args.interval))
