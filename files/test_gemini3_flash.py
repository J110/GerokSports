"""Re-test on Gemini 3 Flash Preview, same two clips, original speed.

Lets us compare 2.5-flash vs 3-flash-preview cleanly on the same input
+ same prompts.
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
os.environ.setdefault("GEMINI_API_KEY",
                      os.environ["GEMINI_API_KEY"])

sys.path.insert(0, str(ROOT))
from test_gemini_video_v2 import PROMPT_STRUCT, PROMPT_COMMENT, parse_json

MODEL = "gemini-3-flash-preview"


def call(client, types, video_bytes, prompt):
    parts = [
        types.Part.from_bytes(data=video_bytes, mime_type="video/mp4"),
        types.Part.from_text(text=prompt),
    ]
    t0 = time.time()
    resp = client.models.generate_content(model=MODEL, contents=parts)
    return (resp.text or ""), int((time.time() - t0) * 1000)


def main():
    from google import genai
    from google.genai import types
    client = genai.Client()

    clips = [
        ("ball_test_clip_30fps.mp4",
         "Clip 1 (15s) — LEFT-handed batsman, played square of wicket"),
        ("ball_test_clip_60fps_long.mp4",
         "Clip 3 (45s) — SHORT delivery, steep bounce, dab"),
    ]

    out = []
    for fname, truth in clips:
        path = ROOT / fname
        with open(path, "rb") as f:
            data = f.read()
        size_mb = len(data) / (1024 * 1024)
        print(f"\n{'='*72}")
        print(f"[{MODEL}]  {fname}  ({size_mb:.1f} MB)")
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
            "model": MODEL,
            "structured": {"wall_ms": ms_a, "raw": raw_a, "parsed": parsed_a},
            "commentator": {"wall_ms": ms_b, "raw": raw_b},
        })

    (ROOT / "results_video_g3flash.json").write_text(json.dumps(out, indent=2))
    print(f"\n\nWrote results_video_g3flash.json")


if __name__ == "__main__":
    main()
