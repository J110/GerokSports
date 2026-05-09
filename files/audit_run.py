"""Run Scout on the audit_v1/ frames with a chosen prompt and report:

  - Per-frame Scout judgment (camera_view, frame_phase, has_strip)
  - Scout's call: ADMIT (camera_view=bowlers_end AND phase in
    release/flight/shot) vs REJECT
  - Comparison against hand labels in audit_v1/labels.json:
      * precision (admitted ∩ truly tp) / admitted
      * recall    (admitted ∩ truly tp) / total tp
      * per-failure-mode admit rate (how often Scout is fooled by
        each failure category)

Usage:
  python audit_run.py baseline    # uses current eyes.vision.SCOUT_PROMPT
  python audit_run.py v2          # uses prompt with negative anchors

Writes audit_v1/results_<tag>.json so v2 vs baseline can be diffed
deterministically.
"""
from __future__ import annotations
import asyncio
import base64
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import cv2
from groq import AsyncGroq

from eyes.config import GROQ_API_KEY, GROQ_PRIMARY_MODEL
from eyes.vision import SCOUT_PROMPT as SCOUT_PROMPT_BASE, Vision

# v2 prompt: SCOUT_PROMPT_BASE + targeted negative anchors injected
# right after the existing camera_view definition block.  We splice
# rather than rewrite so any other behavior (strip parsing, phase
# definitions) stays identical and the only variable we're measuring
# is the negative-anchor block.
NEGATIVE_ANCHORS = """

CRITICAL — DO NOT label as "bowlers_end" in any of these cases (these
are the dominant false positives we're trying to eliminate):

  * Camera shows a single player's face, helmet, jersey, or upper
    body filling more than ~40% of the frame.  This is "closeup", no
    matter what scoreboard strip is at the bottom of the screen.
  * Camera is high above the field looking DOWN at the whole pitch
    or stadium (the players appear small, the boundary rope is
    visible, the camera is not behind the bowler).  This is "graphic"
    or "between_play", not "bowlers_end".
  * Camera is wide on the field showing batters running between
    wickets, fielders dispersed, OR a fielder running/diving/
    throwing the ball.  This is "post_shot" or "fielder_reaction",
    not "bowlers_end" — even if the pitch is partially visible.
  * Camera is on the pitch but no delivery is happening: DRS review
    timer overlay, two batters meeting mid-pitch, dismissed batter
    walking off, umpire signaling, field placement discussion.  This
    is "between_play".
  * Top-down or near-top-down replay angle (camera looking straight
    down at the pitch with batters running L-R or T-B).  This is
    "replay".

"bowlers_end" REQUIRES ALL of the following:
  - Camera is positioned BEHIND the bowler at ground or low-elevated
    level, looking DOWN the pitch toward the batter.
  - The pitch fills the centre of the frame end-to-end.
  - The bowler is visible (running up, in delivery stride, or in
    follow-through) OR the ball is in flight between bowler and
    batter OR the batter is playing a shot.
  - The far-end stumps and/or batter at the far crease are visible.

If ANY of these is missing, label "other" or the closest matching
phase — never "bowlers_end".

"""


def make_v2_prompt() -> str:
    # Splice the negative anchors right before STEP 2 so STEP 1's
    # camera_view definitions are read first and then narrowed.
    needle = "STEP 2 — READ THE STRIP"
    if needle not in SCOUT_PROMPT_BASE:
        raise SystemExit("could not find splice point in SCOUT_PROMPT_BASE")
    return SCOUT_PROMPT_BASE.replace(needle, NEGATIVE_ANCHORS + needle)


# v3: v2 anchors + a HARD REQUIREMENT that the bowler must be visible
# in the foreground for camera_view=bowlers_end.  This targets the
# wide-pitch failure modes (aerial, post_shot, between_play) which v2
# can't distinguish because the pitch IS visible — they just lack the
# bowler in the foreground.
HARD_BOWLER_REQUIREMENT = """

HARD REQUIREMENT for camera_view="bowlers_end":

  Look in the FOREGROUND (bottom half of the frame).  You MUST see
  the bowler's body — either their back (running up to the crease),
  their side profile (in delivery stride), or their follow-through
  (arm extended after release).  The bowler must be the closest
  human figure to the camera.

  If the foreground is empty (just pitch and grass), or the closest
  figure is an umpire, fielder, or batter, the camera is NOT at the
  bowler's end.  Use "other" or "between_play" instead.

  This rule overrides any other consideration.  No bowler in the
  foreground = NOT bowlers_end.

"""


def make_v3_prompt() -> str:
    needle = "STEP 2 — READ THE STRIP"
    return SCOUT_PROMPT_BASE.replace(
        needle, NEGATIVE_ANCHORS + HARD_BOWLER_REQUIREMENT + needle)


def encode(p: Path) -> str:
    bgr = cv2.imread(str(p))
    h, w = bgr.shape[:2]
    if w > 1280:
        bgr = cv2.resize(bgr, (1280, int(h * 1280 / w)),
                         interpolation=cv2.INTER_AREA)
    _, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buf.tobytes()).decode("ascii")


async def call_one(client: AsyncGroq, b64: str, prompt: str) -> dict:
    t0 = time.perf_counter()
    last_err = None
    for attempt in range(6):
        try:
            resp = await client.chat.completions.create(
                model=GROQ_PRIMARY_MODEL,
                temperature=0,
                max_tokens=600,
                messages=[{"role": "user", "content": [
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": prompt},
                ]}],
            )
            raw = resp.choices[0].message.content.strip()
            break
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            if "rate limit" in msg or "429" in msg:
                wait = min(20, 4 * (2 ** attempt))
                await asyncio.sleep(wait)
                continue
            return {"error": repr(e), "ms": int(
                (time.perf_counter() - t0) * 1000)}
    else:
        return {"error": repr(last_err), "ms": int(
            (time.perf_counter() - t0) * 1000)}
    ms = int((time.perf_counter() - t0) * 1000)
    tag, ftype = Vision._parse_tag(raw)
    cv = Vision._normalise_camera_view(
        tag.get("camera_view") if tag else None,
        frame_type=ftype,
        has_strip=bool(tag.get("has_strip")) if tag else False,
        has_overlay=bool(tag.get("has_overlay_stats")) if tag else False,
    )
    ph = Vision._normalise_frame_phase(
        tag.get("frame_phase") if tag else None,
        camera_view=cv, frame_type=ftype)
    strip = bool(tag.get("has_strip", False)) if tag else False
    admit = (cv == "bowlers_end" and ph in ("release", "flight", "shot"))
    return {"camera_view": cv, "frame_phase": ph,
            "has_strip": strip, "admit": admit, "ms": ms}


async def main():
    tag = (sys.argv[1] if len(sys.argv) > 1 else "baseline").lower()
    if tag == "baseline":
        prompt_text = SCOUT_PROMPT_BASE
    elif tag == "v2":
        prompt_text = make_v2_prompt()
    elif tag == "v3":
        prompt_text = make_v3_prompt()
    else:
        raise SystemExit("usage: audit_run.py {baseline|v2|v3}")
    prompt_text = prompt_text.format(vision_hint="None.")

    base = Path(__file__).parent / "audit_v1"
    labs = json.loads((base / "labels.json").read_text())["labels"]
    frames = sorted((base / "frames").glob("*.jpg"))
    print(f"Running Scout ({tag}) on {len(frames)} frames...")
    print(f"Prompt length: {len(prompt_text)} chars")

    client = AsyncGroq(api_key=GROQ_API_KEY, timeout=60)
    sem = asyncio.Semaphore(1)

    async def go(p: Path):
        async with sem:
            b64 = encode(p)
            res = await call_one(client, b64, prompt_text)
            res["frame"] = p.stem
            res["truth"] = labs[p.stem]["truth"]
            return res

    results = await asyncio.gather(*[go(p) for p in frames])
    results.sort(key=lambda r: r["frame"])

    out = base / f"results_{tag}.json"
    out.write_text(json.dumps(results, indent=2))

    n_err = sum(1 for r in results if "error" in r)
    if n_err:
        print(f"WARN: {n_err}/{len(results)} calls errored — "
              f"metrics computed over {len(results) - n_err} responses")
    results_ok = [r for r in results if "error" not in r]
    n_total = len(results_ok)
    results = results_ok
    n_admit = sum(1 for r in results if r.get("admit"))
    n_tp = sum(1 for r in results
               if r["truth"] == "tp_bowlers_end_release")
    n_admit_correct = sum(
        1 for r in results
        if r.get("admit") and r["truth"] == "tp_bowlers_end_release")

    precision = (n_admit_correct / n_admit) if n_admit else 0.0
    recall = (n_admit_correct / n_tp) if n_tp else 0.0

    print()
    print(f"=== Scout ({tag}) on {n_total} hand-labeled frames ===")
    print(f"True positives in set:  {n_tp}")
    print(f"Scout admitted:         {n_admit}")
    print(f"  ... correctly:        {n_admit_correct}")
    print(f"Precision:              {n_admit_correct}/{n_admit} = "
          f"{precision*100:.1f}%")
    print(f"Recall:                 {n_admit_correct}/{n_tp} = "
          f"{recall*100:.1f}%")

    by_truth = defaultdict(lambda: [0, 0])  # [admitted, total]
    for r in results:
        by_truth[r["truth"]][1] += 1
        if r.get("admit"):
            by_truth[r["truth"]][0] += 1
    print()
    print("Admit rate per ground-truth category:")
    for cat, (a, t) in sorted(by_truth.items(), key=lambda x: -x[1][1]):
        rate = a * 100 / t if t else 0
        marker = "  TP" if cat == "tp_bowlers_end_release" else "FP "
        print(f"  {marker} {cat:<26} {a}/{t} ({rate:>5.1f}% admitted)")

    avg_ms = sum(r.get("ms", 0) for r in results) // n_total
    print(f"\nMean Scout latency: {avg_ms} ms")


if __name__ == "__main__":
    asyncio.run(main())
