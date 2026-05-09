"""Validation v3 of the unified Scout-tagged-frame architecture.

Implements the recommendations:
  1. Concrete category names (`bowling_action`, `between_play`,
     `replay_or_graphic`, `advertisement`) — self-documenting; the
     name itself is a visual anchor.
  2. Explicit visual anchor for `bowling_action`: camera BEHIND the
     bowler, looking DOWN the pitch, both sets of stumps roughly
     vertical.
  3. Cascade structure (Q1→Q4) so Scout answers easy questions first
     and only reaches the ambiguous bowling_action vs between_play
     check after ads + replays + graphics are filtered out.
  4. Scoreboard-visible boolean as a sanity-check signal — Scout is
     forced to declare whether the strip is on screen, which acts as
     internal contradiction-detection (bowling_action without
     scoreboard would be a flag).
  5. Optional previous-frame tag for temporal context (caller
     toggles).
  6. Lower-res image (default 512 px wide) for classification — the
     broadcast category is obvious without scoreboard-text resolution.

Two test modes:

    .venv/bin/python validate_scout_v3.py recall
        Runs over the 23 truly-classified deliveries, 5 frames each
        (115 frames).  Reports recall on bowling_action.

    .venv/bin/python validate_scout_v3.py broadcast <session_dir>
        Runs over a captured-broadcast session (e.g. the 80-frame
        innings-break capture) to confirm ad / replay precision.
"""
from __future__ import annotations

import argparse
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


# ────────────────────────────────────────────────────────────────────
# Prompt v3
# ────────────────────────────────────────────────────────────────────
PROMPT_V3 = """\
You are watching a live IPL cricket broadcast.  Classify the camera
view of THIS SINGLE FRAME by answering the four questions below in
order.  Stop at the first "yes".

Q1. Is this a COMMERCIAL ADVERTISEMENT?
    Cues: no cricket field visible, brand/product imagery fills the
    screen, presenter ad-read, app/movie promo.
    If yes → category is "advertisement".

Q2. Is this a REPLAY or BROADCASTER GRAPHIC?
    Cues: "REPLAY" / "SUPER SIXES" / "BEST OF" / "WICKET" /
    "MOMENT OF THE MATCH" badge, slow-motion motion blur, full-screen
    scorecard / partnership / leaderboard / sponsor / wagonwheel /
    hawkeye / stats overlay covering most of the frame.
    If yes → category is "replay_or_graphic".

Q3. Is this the BOWLING-ACTION CAMERA?
    REQUIRED visual signature (ALL must be true):
      a) Camera is BEHIND the bowler's end, looking DOWN the pitch.
      b) The pitch strip runs from the bottom of the frame toward the
         far end (roughly vertical, narrowing with distance).
      c) The batter at the FAR end is visible (small figure(s) at the
         top half of the pitch); often the wicketkeeper / slips are
         visible behind them.
      d) Both sets of stumps are in a roughly vertical line down the
         middle of the frame.
    NOT bowling_action if:
      - the camera is side-on / square / from the boundary
      - the camera is behind the BATTER looking back at the bowler
      - it's a close-up of any single player (face / upper body)
      - it's a wide stadium establishing shot
    The bowler may or may not be in shot — this view is held during
    runup, delivery, AND the moments immediately around it (batter
    taking guard, fielders setting from this angle).  All of those
    count as bowling_action because they're the same camera.
    If yes → category is "bowling_action".

Q4. Otherwise → category is "between_play" (live cricket but not the
    bowler's-end angle: side-on, close-up, fielder shot, umpire,
    crowd, cheerleaders, batter walking).

ALSO report whether the team scoreboard strip is visible at the
bottom of the frame.  If category=="bowling_action" the scoreboard
strip is almost always visible — if you say bowling_action with no
strip, double-check; this view rarely appears without the strip.
{prev_hint}
Output EXACTLY this JSON on a single line, nothing else:
{{"view": "<advertisement|replay_or_graphic|bowling_action|between_play>", \
"scoreboard_visible": <true|false>, \
"replay_badge": "<exact text of any replay/graphic badge, or empty>", \
"reason": "<<= 12 words anchored on the cues above>"}}
"""

CATEGORIES = ("bowling_action", "between_play",
              "replay_or_graphic", "advertisement")


# ────────────────────────────────────────────────────────────────────
def encode_jpeg(frame: np.ndarray, max_w: int = 512, q: int = 78) -> str:
    """Resize + JPEG-encode for the classification call.

    512px is plenty for category classification.  Tested on broadcast
    frames at 1024-1280 wide; downscaling to 512 keeps the bowler's-
    end signature visible (pitch lines, far-end batter silhouette,
    stumps line) while ~quartering the byte count.
    """
    h, w = frame.shape[:2]
    if w > max_w:
        scale = max_w / w
        frame = cv2.resize(frame, (max_w, int(h * scale)),
                           interpolation=cv2.INTER_AREA)
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, q])
    return base64.b64encode(buf.tobytes()).decode("ascii")


def parse_v3(raw: str) -> dict:
    txt = raw.strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:]
    txt = txt.strip()
    try:
        obj = json.loads(txt.splitlines()[0])
        view = str(obj.get("view", "")).lower()
        if view not in CATEGORIES:
            view = "unknown"
        return {
            "view": view,
            "scoreboard_visible": bool(obj.get("scoreboard_visible", False)),
            "replay_badge": str(obj.get("replay_badge", ""))[:60],
            "reason": str(obj.get("reason", ""))[:120],
        }
    except Exception:
        for c in CATEGORIES:
            if c in txt.lower():
                return {"view": c, "scoreboard_visible": False,
                        "replay_badge": "", "reason": "fallback parse"}
        return {"view": "unknown", "scoreboard_visible": False,
                "replay_badge": "", "reason": "parse fail"}


async def call(client: AsyncGroq, frame: np.ndarray,
               prev_tag: str | None = None,
               max_w: int = 512) -> dict:
    b64 = encode_jpeg(frame, max_w=max_w)
    if prev_tag:
        prev_hint = (f"\nPRIOR CONTEXT: the previous frame was classified "
                     f"as \"{prev_tag}\".  Cricket broadcasts are temporally "
                     f"coherent — `bowling_action` typically transitions to "
                     f"`replay_or_graphic` or `between_play`, almost never "
                     f"directly to `advertisement`.  Use this only as a "
                     f"weak prior; the visual content of THIS frame still "
                     f"governs the answer.\n")
    else:
        prev_hint = ""
    prompt = PROMPT_V3.format(prev_hint=prev_hint)
    t0 = time.time()
    try:
        resp = await client.chat.completions.create(
            model=GROQ_PRIMARY_MODEL,
            temperature=0,
            max_tokens=180,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {
                         "url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        ms = (time.time() - t0) * 1000
        raw = resp.choices[0].message.content.strip()
    except Exception as e:
        return {"view": "unknown", "raw": "", "error": str(e),
                "ms": (time.time() - t0) * 1000,
                "scoreboard_visible": False, "replay_badge": "",
                "reason": "api error"}
    r = parse_v3(raw)
    r["raw"] = raw
    r["ms"] = round(ms)
    return r


# ────────────────────────────────────────────────────────────────────
def find_classified_deliveries() -> list[Path]:
    out: list[Path] = []
    for sess in sorted(Path("logs/deliveries").iterdir()):
        if not sess.is_dir():
            continue
        for d in sorted(sess.iterdir()):
            if not d.is_dir():
                continue
            pj = d / "predictions.json"
            if not pj.exists():
                continue
            try:
                o = json.load(open(pj))
            except Exception:
                continue
            if (o.get("vlm_confidence") in ("high", "medium")
                    and o.get("components", {}).get("2_length") not in (
                        None, "", "unknown")):
                out.append(d)
    return out


async def cmd_recall(use_temporal: bool, max_w: int) -> None:
    delivs = find_classified_deliveries()
    print(f"Found {len(delivs)} truly-classified deliveries  "
          f"(temporal_chain={use_temporal}, image_w={max_w})")
    client = AsyncGroq(api_key=GROQ_API_KEY, timeout=10)
    per_delivery = []
    for di, d in enumerate(delivs):
        picks = sorted(d.glob("scout_pick_*.jpg"))
        if not picks:
            continue
        cats: list[str] = []
        prev = None
        for p in picks:
            bgr = cv2.imread(str(p))
            if bgr is None:
                continue
            r = await call(client, bgr,
                           prev_tag=prev if use_temporal else None,
                           max_w=max_w)
            cats.append(r.get("view", "unknown"))
            prev = r.get("view")
        n_ba = sum(1 for c in cats if c == "bowling_action")
        n_bp = sum(1 for c in cats if c == "between_play")
        n_r = sum(1 for c in cats if c == "replay_or_graphic")
        n_ad = sum(1 for c in cats if c == "advertisement")
        per_delivery.append({
            "d": str(d), "n_frames": len(cats),
            "n_bowling_action": n_ba, "n_between_play": n_bp,
            "n_replay": n_r, "n_ad": n_ad, "cats": cats,
        })
        print(f"  [{di:02d}] {d.parent.name}/{d.name} "
              f"ba={n_ba} bp={n_bp} r={n_r} ad={n_ad}  {cats}")

    n = len(per_delivery)
    any_ba = sum(1 for r in per_delivery if r["n_bowling_action"] > 0)
    maj_ba = sum(1 for r in per_delivery
                 if r["n_bowling_action"] > r["n_frames"]/2)
    total = sum(r["n_frames"] for r in per_delivery)
    t_ba = sum(r["n_bowling_action"] for r in per_delivery)
    t_bp = sum(r["n_between_play"] for r in per_delivery)
    t_r = sum(r["n_replay"] for r in per_delivery)
    t_ad = sum(r["n_ad"] for r in per_delivery)
    print("\n=== RECALL on truly-classified deliveries (v3) ===")
    print(f"  Deliveries with ANY bowling_action frame:  {any_ba}/{n}  "
          f"({any_ba*100/max(n,1):.0f}%)")
    print(f"  Deliveries with MAJORITY bowling_action:   {maj_ba}/{n}  "
          f"({maj_ba*100/max(n,1):.0f}%)")
    print(f"  Total frames: {total}")
    print(f"    bowling_action:    {t_ba}  ({t_ba*100/max(total,1):.0f}%)")
    print(f"    between_play:      {t_bp}  ({t_bp*100/max(total,1):.0f}%)")
    print(f"    replay_or_graphic: {t_r}   ({t_r*100/max(total,1):.0f}%)")
    print(f"    advertisement:     {t_ad}  ({t_ad*100/max(total,1):.0f}%)")

    out_dir = Path("logs/scout_4cat_validation/v3_recall"
                   + ("_chained" if use_temporal else ""))
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "results.jsonl").open("w") as f:
        for r in per_delivery:
            f.write(json.dumps(r) + "\n")
    print(f"\nSaved → {out_dir}/results.jsonl")


async def cmd_broadcast(sess_dir: Path, use_temporal: bool,
                        max_w: int) -> None:
    frames = sorted((sess_dir / "frames").glob("f*.jpg"))
    print(f"Loaded {len(frames)} frames from {sess_dir}/frames "
          f"(temporal_chain={use_temporal}, image_w={max_w})")
    client = AsyncGroq(api_key=GROQ_API_KEY, timeout=10)
    out: list[dict] = []
    prev = None
    for i, p in enumerate(frames):
        bgr = cv2.imread(str(p))
        if bgr is None:
            continue
        r = await call(client, bgr,
                       prev_tag=prev if use_temporal else None,
                       max_w=max_w)
        r["i"] = i
        r["path"] = str(p.relative_to(sess_dir))
        out.append(r)
        prev = r.get("view")
        print(f"  [{i:03d}] {r.get('view','?'):>17s} "
              f"strip={'Y' if r.get('scoreboard_visible') else 'N'} "
              f"badge={r.get('replay_badge','')[:18]:<18s} "
              f"{r.get('reason','')[:50]}")

    counts: dict[str, int] = {}
    for r in out:
        v = r.get("view", "unknown")
        counts[v] = counts.get(v, 0) + 1
    n = max(len(out), 1)
    print("\n=== BROADCAST distribution (v3) ===")
    for c, ct in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {c:>17s}: {ct:>3d}  ({ct*100/n:.0f}%)")

    out_path = sess_dir / ("results_v3"
                           + ("_chained" if use_temporal else "")
                           + ".jsonl")
    with out_path.open("w") as f:
        for r in out:
            f.write(json.dumps(r) + "\n")
    print(f"\nSaved → {out_path}")


# ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not GROQ_API_KEY:
        raise SystemExit("GROQ_API_KEY missing")
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["recall", "broadcast"])
    p.add_argument("sess", nargs="?")
    p.add_argument("--chain", action="store_true",
                   help="pass previous frame's tag as context")
    p.add_argument("--w", type=int, default=512,
                   help="image width sent to Scout (default 512)")
    args = p.parse_args()
    if args.mode == "recall":
        asyncio.run(cmd_recall(args.chain, args.w))
    else:
        if not args.sess:
            raise SystemExit("broadcast mode needs <session_dir>")
        asyncio.run(cmd_broadcast(Path(args.sess), args.chain, args.w))
