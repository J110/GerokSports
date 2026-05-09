"""Iteration 2 of the 4-category prompt.

Goals:
 1. Boost recall on `delivery` — the previous prompt's "ONLY for the
    moment of action" wording made Scout hedge.  We now ask the
    question: "Does this frame show the delivery-action camera angle
    looking down the pitch from the bowler's end, with batter and pitch
    clearly visible?"  Bowler walking back is still `live` because the
    angle is the same but framing emphasises the bowler walking away.
 2. Distinguish replays of deliveries from live deliveries via
    badge/branding cues ("REPLAY", "SUPER SIXES", slow-mo blur).

Re-runs over an existing capture session to compare prompts side by
side.  Usage:

    .venv/bin/python validate_scout_4cat_iter.py logs/scout_4cat_validation/<sess>
"""
from __future__ import annotations

import asyncio
import base64
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from groq import AsyncGroq

from eyes.config import GROQ_API_KEY, GROQ_PRIMARY_MODEL


PROMPT_V2 = """\
You are watching a live IPL cricket broadcast.  Classify THIS SINGLE
FRAME into one of four categories.

THE FOUR CATEGORIES:

1. "delivery" — the LIVE bowler's-end camera angle looking down the
   pitch.  You can see the pitch strip running away from the camera,
   the batter at the far end, often the bowler in the foreground or
   the ball in play.  This includes:
     • bowler running in
     • bowler's load-up / delivery stride
     • bowler's follow-through right after release
     • ball in flight down the pitch
     • batter playing the shot from this angle
   Do NOT use this if there is a "REPLAY", "SUPER SIXES", "BEST OF",
   or similar badge anywhere on screen — that's `replay_scorecard`
   even if the action looks like a delivery.

2. "live" — live game feed but not the bowler's-end delivery angle.
   Examples: square / side-on camera, fielder running, mid-on chat,
   captain setting field, batter taking guard from a side angle,
   close-up of any player, crowd shot, umpire signal, cheerleaders.

3. "replay_scorecard" — a replay (slow-mo, "REPLAY" badge, "SUPER
   SIXES", "BEST OF", "MOMENT OF THE MATCH" etc.), OR a full-screen
   broadcaster graphic (full scorecard, partnership card, leaderboard,
   sponsor card, stats card).

4. "ads" — commercial / advertisement / non-cricket content.  No
   stadium visible.  Brand logos, product shots, presenter ad reads.

Output EXACTLY this JSON on a single line, nothing else:
{"category": "<delivery|live|replay_scorecard|ads>", \
"confidence": "<low|medium|high>", \
"replay_badge": "<exact text of any REPLAY/SUPER SIXES/etc badge, or empty>", \
"reason": "<<= 12 words>"}
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


def parse(raw: str) -> dict:
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
            "replay_badge": str(obj.get("replay_badge", ""))[:60],
            "reason": str(obj.get("reason", ""))[:120],
        }
    except Exception:
        for c in CATEGORIES:
            if c in txt.lower():
                return {"category": c, "confidence": "low",
                        "replay_badge": "", "reason": "fallback"}
        return {"category": "unknown", "confidence": "low",
                "replay_badge": "", "reason": "parse fail"}


async def run(sess_dir: Path) -> None:
    if not GROQ_API_KEY:
        raise SystemExit("GROQ_API_KEY missing")

    frames_dir = sess_dir / "frames"
    if not frames_dir.exists():
        raise SystemExit(f"No frames dir at {frames_dir}")
    images = sorted(frames_dir.glob("f*.jpg"))
    print(f"Loaded {len(images)} frames from {frames_dir}")

    client = AsyncGroq(api_key=GROQ_API_KEY, timeout=10)
    out: list[dict] = []
    for i, p in enumerate(images):
        bgr = cv2.imread(str(p))
        if bgr is None:
            continue
        b64 = encode_jpeg(bgr)
        t0 = time.time()
        try:
            resp = await client.chat.completions.create(
                model=GROQ_PRIMARY_MODEL,
                temperature=0,
                max_tokens=140,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url",
                         "image_url": {
                             "url": f"data:image/jpeg;base64,{b64}"}},
                        {"type": "text", "text": PROMPT_V2},
                    ],
                }],
            )
            ms = (time.time() - t0) * 1000
            raw = resp.choices[0].message.content.strip()
        except Exception as e:
            raw = ""
            ms = (time.time() - t0) * 1000
            print(f"  [{i:03d}] ERROR {e}")
        r = parse(raw)
        r["i"] = i
        r["path"] = str(p.relative_to(sess_dir))
        r["raw"] = raw
        r["ms"] = round(ms)
        out.append(r)
        print(f"  [{i:03d}] {r['category']:>17s} conf={r['confidence']:>6s} "
              f"badge={r['replay_badge'][:24]:<24s} {r['reason'][:50]}")

    # Diff against v1
    v1_path = sess_dir / "results.jsonl"
    v1 = {}
    if v1_path.exists():
        for line in v1_path.read_text().splitlines():
            if not line.strip():
                continue
            o = json.loads(line)
            v1[o["i"]] = o.get("category", "?")

    counts: dict[str, int] = {}
    diffs: list[tuple[int, str, str]] = []
    for r in out:
        c = r["category"]
        counts[c] = counts.get(c, 0) + 1
        v1c = v1.get(r["i"], "?")
        if v1c != c:
            diffs.append((r["i"], v1c, c))

    n = max(len(out), 1)
    print("\nv2 distribution:")
    for c, ct in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {c:>17s}: {ct:>3d}  ({ct*100/n:.0f}%)")

    print(f"\nChanges from v1 → v2: {len(diffs)} frames")
    for i, a, b in diffs[:30]:
        print(f"  f{i:03d}: {a:>17s} → {b}")
    if len(diffs) > 30:
        print(f"  ... and {len(diffs)-30} more")

    out_path = sess_dir / "results_v2.jsonl"
    with out_path.open("w") as f:
        for x in out:
            f.write(json.dumps(x) + "\n")
    print(f"\nSaved → {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: validate_scout_4cat_iter.py <session_dir>")
    asyncio.run(run(Path(sys.argv[1])))
