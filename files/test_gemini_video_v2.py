"""Re-test Gemini video on clips 1 and 3 with two new prompts:

  PROMPT_STRUCT  — strict schema, NO example values, forced "unknown"
                   when uncertain.  Tests whether anchoring caused the
                   confabulation we saw in v1.

  PROMPT_COMMENT — free-form commentator description.  No schema, no
                   classification, just "tell me what you see".  Tests
                   whether Gemini can perceive cricket events at all
                   when not constrained to a label set.

Hand-validated truth (from user):
  clip 1 (30fps): LEFT-handed batsman; played square of the wicket
  clip 3 (60fps_long): SHORT delivery, steep bounce, dab (not a drive)
"""
import json
import os
import re
import time
from pathlib import Path

ROOT = Path(__file__).parent
os.environ.setdefault("GEMINI_API_KEY",
                      os.environ["GEMINI_API_KEY"])

# ────────────────────────────────────────────────────────────────────
# Prompt A: structured, no examples, forced honesty
# ────────────────────────────────────────────────────────────────────
PROMPT_STRUCT = """\
You will receive a video clip from a cricket broadcast.

STEP 1 — DECIDE if the clip actually contains a bowled delivery
captured from the bowler's-end (high straight) camera.  If you do not
clearly see a bowler running in, releasing the ball, the ball
travelling through the air, AND the batsman responding (or leaving),
then this is NOT a delivery.  Return is_valid_delivery=false and
"unknown" for every other field.  Do NOT invent player names, speeds
or shot details when you cannot see them.

STEP 2 — Only if a real delivery is clearly visible, classify it.
Return a single JSON object on one line, with EXACTLY these keys
(no extras).  Use "unknown" for any field you cannot read directly
from the video — guessing is forbidden.

Schema (allowed values shown after each key):
  is_valid_delivery   true | false
  batsman_handed      right | left | unknown
  bowling_angle       over | round | unknown
  length              yorker | full | good_length | short_of_a_length |
                      short | bouncer | unknown
  line                wide_outside_off | outside_off | off_stump |
                      middle | leg_stump | down_leg | wide_down_leg |
                      unknown
  bounce              low | normal | steep | unknown
  shot_played         true | false | unknown
  footwork            front_foot | back_foot | crease | left_alone |
                      unknown
  shot_type           defend | leave | drive | dab | cut | pull |
                      hook | flick | sweep | reverse_sweep | slog |
                      paddle | unknown
  shot_side           off | leg | straight | behind | no_shot | unknown
  shot_angle          third_man | point | cover | mid_off | mid_on |
                      mid_wicket | square_leg | fine_leg | down_ground |
                      no_shot | unknown
  elevation           along_ground | in_air | edged | no_shot | unknown
  bowler_speed_kph    integer if shown on broadcast overlay,
                      otherwise null  (do NOT guess)
  bowler_name         string if a name graphic is on screen,
                      otherwise null
  batsman_name        string if a name graphic is on screen,
                      otherwise null
  narrative           one sentence describing only what you actually
                      see; if very unsure, say "unclear"
  confidence          high | medium | low — be honest; if more than
                      two fields are "unknown", confidence is low

Return only the JSON object, no markdown.
"""

# ────────────────────────────────────────────────────────────────────
# Prompt B: free-form commentator
# ────────────────────────────────────────────────────────────────────
PROMPT_COMMENT = """\
You are a cricket commentator watching a short video clip from a
broadcast.  In 2-4 sentences, describe ONLY what you can actually see
happening in the clip — like a TV commentator would call it for a
listener.

Cover (only the parts that are visible):
  - what the bowler does (run-up, release, ball flight, where it
    pitches, how it bounces),
  - what the batsman does (which hand, footwork, shot played, where
    the ball goes after contact),
  - any speed, score or graphic visible on screen.

Do NOT invent details.  If the clip does not show a delivery (e.g.
just a batsman walking, a closeup, a replay, an ad), say so plainly
and stop.  Do NOT use a fixed schema or JSON — write natural English.
"""


def parse_json(text):
    if not text:
        return None
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def call(client, types, video_bytes, prompt):
    parts = [
        types.Part.from_bytes(data=video_bytes, mime_type="video/mp4"),
        types.Part.from_text(text=prompt),
    ]
    t0 = time.time()
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=parts,
    )
    return (resp.text or ""), int((time.time() - t0) * 1000)


def main():
    from google import genai
    from google.genai import types
    client = genai.Client()

    clips = [
        ("ball_test_clip_30fps.mp4",
         "Clip 1 (30fps, 15s) — LEFT-handed batsman, square of wicket"),
        ("ball_test_clip_60fps_long.mp4",
         "Clip 3 (60fps, 45s) — SHORT delivery, steep bounce, dab"),
    ]

    out = []
    for fname, truth in clips:
        path = ROOT / fname
        with open(path, "rb") as f:
            data = f.read()
        size_mb = len(data) / (1024 * 1024)
        print(f"\n{'='*72}")
        print(f"{fname}  ({size_mb:.1f} MB)")
        print(f"  truth: {truth}")
        print(f"{'='*72}")

        # --- Prompt A: structured ---
        print(f"\n[A] STRUCTURED prompt (no anchors, forced unknown):")
        raw_a, ms_a = call(client, types, data, PROMPT_STRUCT)
        parsed_a = parse_json(raw_a)
        print(f"  wall: {ms_a/1000:.1f}s")
        if parsed_a:
            print(json.dumps(parsed_a, indent=2))
        else:
            print(f"  RAW: {raw_a[:600]}")

        # --- Prompt B: commentator ---
        print(f"\n[B] COMMENTATOR prompt (free-form English):")
        raw_b, ms_b = call(client, types, data, PROMPT_COMMENT)
        print(f"  wall: {ms_b/1000:.1f}s")
        print(f"  >>> {raw_b.strip()}")

        out.append({
            "clip": fname,
            "truth": truth,
            "structured": {"wall_ms": ms_a, "raw": raw_a, "parsed": parsed_a},
            "commentator": {"wall_ms": ms_b, "raw": raw_b},
        })

    (ROOT / "results_video_v2.json").write_text(json.dumps(out, indent=2))
    print(f"\n\nWrote results_video_v2.json")


if __name__ == "__main__":
    main()
