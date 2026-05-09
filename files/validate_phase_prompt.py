"""Validate the extended Scout prompt that adds frame_phase + ball_position.

Builds on the proven existing SCOUT_PROMPT.  Adds two fields to the
opening JSON tag line so a single Scout call returns both the
scoreboard read AND the per-frame moment-of-the-delivery tag.

Two assertions we need to confirm before integrating:

  1. SCOREBOARD REGRESSION: the existing scoreboard extraction
     ("STRIP: TEAM SCORE-WICKETS (OVERS)...") must still work.  The
     original prompt has 97% camera_view recall and reliable strip
     parsing; we cannot regress that to gain phase tagging.

  2. PHASE SIGNAL: on the 115 frames Scout previously classified as
     real deliveries (high/medium confidence with concrete length+
     line), the frame_phase distribution should be dominated by
     `release`, `flight`, `shot`, and `post_shot` rather than
     `between_play`, `fielder_reaction`, or `replay`.  Each delivery
     should have at least one frame Scout calls `release`/`flight`/
     `shot` so the integrated pipeline can sample the moment of
     action.

Usage:
    .venv/bin/python validate_phase_prompt.py
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
import time
from collections import Counter
from pathlib import Path

import cv2
from groq import AsyncGroq

from eyes.config import GROQ_API_KEY, GROQ_PRIMARY_MODEL


# ────────────────────────────────────────────────────────────────────
# Extended SCOUT_PROMPT: identical structure to production, with the
# JSON tag line widened to include frame_phase + ball_position.
# ────────────────────────────────────────────────────────────────────
SCOUT_PROMPT_PHASE = """\
You are reading a live IPL cricket broadcast frame.

STEP 1 — CLASSIFY. Output this JSON on the FIRST line, nothing before it:
{"has_strip": true, "has_overlay_stats": false, "drs_review": false, \
"camera_view": "bowlers_end", "frame_phase": "release", \
"ball_position": null}

has_strip: Is the team score strip visible at the bottom?
has_overlay_stats: Are career/tournament/head-to-head stats shown as an \
OVERLAY on top of the live feed? (NOT the regular scoreboard strip)
drs_review: Is a DRS review decision being shown?

camera_view: ONE of these exact strings, describing the camera angle:
  - "bowlers_end": standard wide shot down the pitch from the bowler's \
end (bowler running in / mid-delivery / batter at the far crease).
  - "side_on": square / side-on field camera (third-man, fine-leg, \
boundary-chase angle).
  - "closeup": closeup of one player — face / upper body fills the frame.
  - "replay": clearly a replay or slow-motion of an earlier moment.
  - "graphic": full-screen broadcaster graphic (full scorecard, \
partnership graphic, statistical overlay, sponsor card).
  - "ad": commercial / advertisement break.
  - "other": pre-match presenter, post-match presentation, drinks \
break, anything else.

frame_phase: ONE of these exact strings, describing the MOMENT of the \
delivery this frame shows.  Use the visual signature, not your guess:
  - "runup": Camera behind the bowler looking down the pitch.  The \
bowler is walking or running toward the crease.  The ball is in the \
bowler's hand.  The batter is at the far crease, often taking guard \
or settling in stance.
  - "release": Camera still behind the bowler.  The bowler is in \
their delivery stride — front foot landing, arm coming through, or \
arm at the top of the action.  The ball may still be in the hand or \
just released.
  - "flight": Camera behind the bowler.  The ball has left the \
bowler's hand and is visible in the air between the bowler's end and \
the batter.  The batter is preparing to play a shot.  Bowler in \
follow-through.
  - "shot": Camera behind the bowler (or a tight angle).  The ball \
has been struck by the batter, is being defended, or is being left.  \
The bat is in motion through the shot or just after contact.
  - "post_shot": The shot has been played.  Camera may still be on \
bowler's end briefly, or has just cut to follow the ball.  The batter \
has completed the shot motion.  Fielders may be reacting.
  - "fielder_reaction": Camera has cut to a fielder running after \
the ball, diving, catching, or throwing.  The pitch is no longer the \
focus.  Could also be a celebration huddle around the stumps after a \
wicket.
  - "replay": Slow-motion replay of a past event, spider-cam, close-\
up of ball/bat contact, wagon wheel, or stats overlay covering the \
live feed.
  - "between_play": Cricket is visible but no delivery is happening.  \
Bowler walking back to mark, field change, drinks, batter signalling \
for new bat, umpire discussion.
  - "graphic": Full-screen / near-full-screen graphic overlay.  Score \
summary, partnership stats, player profile, sponsor animation.
  - "advertisement": Commercial break, no cricket content visible.
  - "other": None of the above.

ball_position: If you can clearly see the ball in flight as a small \
white object between the bowler's end and the batter, give its \
position as {"x": 0.0..1.0, "y": 0.0..1.0} where (0,0) is top-left.  \
Only set this for "release", "flight", or "shot" phases.  Otherwise \
return null.  Do NOT guess — if the ball is not clearly visible as a \
small object in flight, return null.

STEP 2 — READ THE STRIP (skip if has_strip is false).
Output the strip data in this exact format:
STRIP: [TEAM] [SCORE]-[WICKETS] ([OVERS]) | [BATTER1] [RUNS]([BALLS]) | \
[BATTER2] [RUNS]([BALLS]) | [BOWLER] [W]-[R] ([OVERS])

Example: STRIP: KKR 105-2 (11.3) | Green 45(32) | Raghuvanshi 4(5) | \
Siddharth 0-21 (2.3)

STEP 3 — REPORT OVERLAYS (skip if nothing visible):
INFO_PANEL: [career/tournament/head-to-head text]
SPEED: [number] (bowling speed in kph)
EXTRA: wide/no_ball/leg_bye/bye
THIS OVER: [ball-by-ball results]
FULL SCORECARD: [every batter/bowler row]

STEP 4 — ACTION (1 sentence):
What is happening? (delivery bowled, shot played, celebration, etc.)

RULES:
- JSON tag line MUST be first. Then strip. Then overlays. Then action.
- Report exact numbers from the strip. Don't guess or infer.
- * or > prefix on batter name = striker.
- If this is a pure ADVERTISEMENT with no strip: output the JSON with \
all false / "advertisement" frame_phase, then say "ADVERTISEMENT" \
and stop.

HINT FROM SCORER:
None.
"""


PHASE_VALUES = {
    "runup", "release", "flight", "shot", "post_shot",
    "fielder_reaction", "replay", "between_play", "graphic",
    "advertisement", "other",
}
ACTION_PHASES = {"release", "flight", "shot"}
DELIVERY_ADJACENT_PHASES = {"runup", "release", "flight", "shot", "post_shot"}


# ────────────────────────────────────────────────────────────────────
def encode_jpeg(frame, max_w=1280, q=85):
    h, w = frame.shape[:2]
    if w > max_w:
        scale = max_w / w
        frame = cv2.resize(frame, (max_w, int(h * scale)),
                           interpolation=cv2.INTER_AREA)
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, q])
    return base64.b64encode(buf.tobytes()).decode("ascii")


def parse_response(raw: str) -> dict:
    """Pull the JSON tag and the STRIP line out of Scout's response."""
    out = {
        "has_strip": False, "camera_view": None, "frame_phase": None,
        "ball_position": None, "strip_text": "", "raw": raw[:300],
    }
    # JSON tag: first {} on a line within first 5 lines.
    for line in raw.split("\n")[:5]:
        line = line.strip()
        if line.startswith("{") and "has_strip" in line:
            for end in (line.rfind("}") + 1, len(line)):
                try:
                    obj = json.loads(line[:end])
                    out["has_strip"] = bool(obj.get("has_strip", False))
                    cv = obj.get("camera_view")
                    if isinstance(cv, str):
                        out["camera_view"] = cv.lower().strip()
                    fp = obj.get("frame_phase")
                    if isinstance(fp, str):
                        fp = fp.lower().strip()
                        out["frame_phase"] = (
                            fp if fp in PHASE_VALUES else "other")
                    bp = obj.get("ball_position")
                    if isinstance(bp, dict) and "x" in bp and "y" in bp:
                        try:
                            out["ball_position"] = {
                                "x": float(bp["x"]), "y": float(bp["y"])}
                        except (TypeError, ValueError):
                            pass
                    break
                except json.JSONDecodeError:
                    continue
            break
    # STRIP line.
    m = re.search(
        r"STRIP:\s*([A-Z]{2,5})\s+(\d{1,3})-(\d{1,2})\s*\(([\d.]+)\)",
        raw)
    if m:
        out["strip_text"] = m.group(0)
        out["strip_team"] = m.group(1)
        out["strip_score"] = int(m.group(2))
        out["strip_wickets"] = int(m.group(3))
        out["strip_overs"] = m.group(4)
    return out


async def call(client, frame) -> dict:
    b64 = encode_jpeg(frame)
    t0 = time.time()
    try:
        resp = await client.chat.completions.create(
            model=GROQ_PRIMARY_MODEL,
            temperature=0,
            max_tokens=600,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": SCOUT_PROMPT_PHASE},
            ]}],
        )
        ms = (time.time() - t0) * 1000
        raw = resp.choices[0].message.content.strip()
    except Exception as e:
        return {"error": str(e), "ms": (time.time() - t0) * 1000,
                "raw": "", "has_strip": False, "camera_view": None,
                "frame_phase": None, "ball_position": None,
                "strip_text": ""}
    r = parse_response(raw)
    r["ms"] = round(ms)
    return r


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


async def main() -> None:
    if not GROQ_API_KEY:
        raise SystemExit("GROQ_API_KEY missing")
    delivs = find_classified_deliveries()
    print(f"Found {len(delivs)} truly-classified deliveries")
    client = AsyncGroq(api_key=GROQ_API_KEY, timeout=15)

    per: list[dict] = []
    total_ms = 0
    for di, d in enumerate(delivs):
        picks = sorted(d.glob("scout_pick_*.jpg"))
        if not picks:
            continue
        results = []
        for p in picks:
            bgr = cv2.imread(str(p))
            if bgr is None:
                continue
            r = await call(client, bgr)
            r["pick"] = p.name
            results.append(r)
            total_ms += r.get("ms", 0)
        phases = [r.get("frame_phase") for r in results]
        cams = [r.get("camera_view") for r in results]
        strips = [r.get("strip_text", "") for r in results]
        n_strip = sum(1 for s in strips if s)
        n_be = sum(1 for c in cams if c == "bowlers_end")
        n_action = sum(1 for p in phases if p in ACTION_PHASES)
        n_adj = sum(1 for p in phases if p in DELIVERY_ADJACENT_PHASES)
        per.append({"d": str(d), "n_frames": len(results),
                    "phases": phases, "cams": cams,
                    "n_with_strip": n_strip,
                    "n_bowlers_end": n_be,
                    "n_action_phase": n_action,
                    "n_delivery_adjacent": n_adj,
                    "results": results})
        print(f"  [{di:02d}] {d.parent.name}/{d.name} "
              f"strip={n_strip}/{len(results)} "
              f"be={n_be} action={n_action} adj={n_adj}  "
              f"phases={phases}")

    n = len(per)
    total_frames = sum(r["n_frames"] for r in per)
    avg_ms = total_ms / max(total_frames, 1)
    n_strip_total = sum(r["n_with_strip"] for r in per)
    n_be_total = sum(r["n_bowlers_end"] for r in per)

    delivs_with_action = sum(1 for r in per if r["n_action_phase"] > 0)
    delivs_with_adj = sum(1 for r in per if r["n_delivery_adjacent"] > 0)
    delivs_with_strip = sum(1 for r in per if r["n_with_strip"] > 0)

    phase_count: Counter = Counter()
    for r in per:
        phase_count.update(r["phases"])

    print("\n" + "=" * 70)
    print("REGRESSION CHECK — scoreboard extraction (must stay high)")
    print("=" * 70)
    print(f"  Frames with parseable STRIP:       "
          f"{n_strip_total}/{total_frames}  "
          f"({n_strip_total*100/max(total_frames,1):.0f}%)")
    print(f"  Deliveries with >=1 STRIP frame:   "
          f"{delivs_with_strip}/{n}  "
          f"({delivs_with_strip*100/max(n,1):.0f}%)")
    print(f"  Frames with camera_view=bowlers_end: "
          f"{n_be_total}/{total_frames}  "
          f"({n_be_total*100/max(total_frames,1):.0f}%)")
    print(f"  Avg call latency: {avg_ms:.0f} ms")

    print("\n" + "=" * 70)
    print("PHASE SIGNAL — moment-of-delivery tagging")
    print("=" * 70)
    print(f"  Deliveries with >=1 release/flight/shot frame: "
          f"{delivs_with_action}/{n}  "
          f"({delivs_with_action*100/max(n,1):.0f}%)")
    print(f"  Deliveries with >=1 delivery-adjacent frame    "
          f"(runup/release/flight/shot/post_shot): "
          f"{delivs_with_adj}/{n}  "
          f"({delivs_with_adj*100/max(n,1):.0f}%)")
    print(f"\n  Phase distribution across {total_frames} frames:")
    for p, c in phase_count.most_common():
        print(f"    {p:<20s} {c:>3d}  "
              f"({c*100/max(total_frames,1):.0f}%)")

    out_dir = Path("logs/scout_4cat_validation/phase_recall")
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "results.jsonl").open("w") as f:
        for r in per:
            f.write(json.dumps(r) + "\n")
    print(f"\nSaved → {out_dir}/results.jsonl")


if __name__ == "__main__":
    asyncio.run(main())
