"""Smoke test: Gemini 2.5-flash video classification of a single cricket
delivery clip.  Uses inline upload (clip < 20 MB).
"""
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
os.environ.setdefault("GEMINI_API_KEY",
                      os.environ["GEMINI_API_KEY"])

PROMPT = """\
This is a video clip of a single cricket delivery, from the bowler's-end
camera.  Watch the FULL sequence — runup, release, ball flight, bounce,
shot — and return ONLY a single JSON object on one line:

{
  "is_valid_delivery": true,
  "bowling_angle": "over",
  "length": "good_length",
  "line": "outside_off",
  "shot_side": "off",
  "shot_angle": "behind_wicket",
  "elevation": "along_ground",
  "shot_type": "drive",
  "bowler_speed_kph": null,
  "narrative": "2-3 sentence description of what actually happened",
  "confidence": "high"
}

Field options:
  bowling_angle: over | round | unknown
  length:        yorker | full | good_length | short_of_a_length | short | bouncer | unknown
  line:          wide_outside_off | outside_off | off_stump | middle | leg_stump | down_leg | unknown
  shot_side:     off | leg | straight | behind | no_shot
  shot_angle:    behind_wicket | square | mid | down_ground | no_shot
  elevation:     along_ground | in_air | no_shot
  shot_type:     defend | drive | cut | pull | flick | sweep | leave | unknown
  confidence:    high | medium | low

Set is_valid_delivery=false if this is not actually a bowled delivery
(closeup, replay, fielding drill, etc.) and use "unknown" for fields
you can't determine.  bowler_speed_kph: number from broadcast overlay,
otherwise null.
"""


def parse(text):
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


def main():
    from google import genai
    from google.genai import types
    client = genai.Client()

    clips = [
        ROOT / "ball_test_clip_30fps.mp4",
        ROOT / "ball_test_clip_60fps.mp4",
        ROOT / "ball_test_clip_60fps_long.mp4",
    ]
    out = []
    for clip in clips:
        if not clip.exists():
            continue
        size_mb = clip.stat().st_size / (1024 * 1024)
        print(f"\n=== {clip.name}  ({size_mb:.1f} MB) ===")

        with open(clip, "rb") as f:
            data = f.read()

        parts = [
            types.Part.from_bytes(data=data, mime_type="video/mp4"),
            types.Part.from_text(text=PROMPT),
        ]

        t0 = time.time()
        try:
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=parts,
            )
            raw = resp.text or ""
            wall_ms = int((time.time() - t0) * 1000)
            parsed = parse(raw)
            print(f"  wall: {wall_ms/1000:.1f}s")
            if parsed:
                print(f"  parsed JSON:")
                print(json.dumps(parsed, indent=4))
            else:
                print(f"  RAW:")
                print(raw[:1500])
            out.append({"clip": clip.name, "wall_ms": wall_ms,
                        "raw": raw, "parsed": parsed})
        except Exception as e:
            wall_ms = int((time.time() - t0) * 1000)
            print(f"  ERROR after {wall_ms}ms: {str(e)[:200]}")
            out.append({"clip": clip.name, "wall_ms": wall_ms,
                        "error": str(e)})

    (ROOT / "results_video_smoketest.json").write_text(
        json.dumps(out, indent=2))
    print(f"\nWrote results_video_smoketest.json")


if __name__ == "__main__":
    main()
