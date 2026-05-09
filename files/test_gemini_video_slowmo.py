"""Re-test Gemini Flash on slow-motion versions of clips 1 and 3.

Hypothesis: Gemini samples video at ~1fps internally.  Slowing the
clip down lets it see more frames around the bounce/contact moment,
which may unblock perception of length / bounce / shot type.
"""
import json
import os
import re
import time
from pathlib import Path

ROOT = Path(__file__).parent
os.environ.setdefault("GEMINI_API_KEY",
                      os.environ["GEMINI_API_KEY"])

# Same prompts as v2
import sys
sys.path.insert(0, str(ROOT))
from test_gemini_video_v2 import PROMPT_STRUCT, PROMPT_COMMENT, parse_json


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
        ("ball_test_clip_30fps_slow3x.mp4",
         "Clip 1 SLOW 3x  (45s) — LEFT-handed batsman, square of wicket"),
        ("ball_test_clip_60fps_long_slow2x.mp4",
         "Clip 3 SLOW 2x  (90s) — SHORT delivery, steep bounce, dab"),
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

        print(f"\n[A] STRUCTURED prompt:")
        raw_a, ms_a = call(client, types, data, PROMPT_STRUCT)
        parsed_a = parse_json(raw_a)
        print(f"  wall: {ms_a/1000:.1f}s")
        if parsed_a:
            print(json.dumps(parsed_a, indent=2))
        else:
            print(f"  RAW: {raw_a[:600]}")

        print(f"\n[B] COMMENTATOR prompt:")
        raw_b, ms_b = call(client, types, data, PROMPT_COMMENT)
        print(f"  wall: {ms_b/1000:.1f}s")
        print(f"  >>> {raw_b.strip()}")

        out.append({
            "clip": fname,
            "truth": truth,
            "structured": {"wall_ms": ms_a, "raw": raw_a, "parsed": parsed_a},
            "commentator": {"wall_ms": ms_b, "raw": raw_b},
        })

    (ROOT / "results_video_slowmo.json").write_text(json.dumps(out, indent=2))
    print(f"\n\nWrote results_video_slowmo.json")


if __name__ == "__main__":
    main()
