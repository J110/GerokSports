"""Debug: run Scout reader on specific problem frames to see raw output."""
import asyncio
import base64
import os
import sys
import time

import cv2
from groq import AsyncGroq

sys.path.insert(0, os.path.dirname(__file__))
from eyes.config import GROQ_API_KEY, GROQ_PRIMARY_MODEL

READER_PROMPT = """\
You are watching a live cricket match broadcast.

Describe everything visible on the scoreboard strip and any overlays.

CRITICAL — TWO SOURCES OF DATA ON SCREEN:

1. LIVE SCOREBOARD STRIP (bottom bar, always present during play):
  Small text. Shows: team score-wickets (overs), two batters \
with MATCH runs(balls), current bowler with MATCH figures W-R(overs).

2. INFO/CAREER PANEL (rotating overlay, appears above or beside strip):
  Larger text. Contains words like: IPL, CAREER, T20, SINCE, TOURNAMENT.
  Label them: INFO_PANEL: [whatever it says]
  Do NOT mix info panel numbers with strip data.

BOWLING SPEED: If you see a speed number (80-160 range), report: SPEED: X
THIS OVER: If ball-by-ball results shown, report them exactly.
Report every number exactly. Describe what you SEE.

HINT FROM SCORER:
None — debug run.\
"""

FRAMES = [
    "debug_frames/f5_scoreboard.jpg",
    "debug_frames/f6_scoreboard.jpg",
    "debug_frames/f7_scoreboard.jpg",
    "debug_frames/f8_scoreboard.jpg",
]


async def main():
    client = AsyncGroq(api_key=GROQ_API_KEY, timeout=10.0)

    for fpath in FRAMES:
        fname = os.path.basename(fpath)
        frame = cv2.imread(fpath)
        if frame is None:
            print(f"\n{'='*60}\n{fname}: FAILED TO READ\n")
            continue

        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        b64 = base64.b64encode(buf).decode()

        t0 = time.time()
        try:
            resp = await client.chat.completions.create(
                model=GROQ_PRIMARY_MODEL,
                temperature=0,
                max_tokens=400,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        {"type": "text", "text": READER_PROMPT},
                    ],
                }],
            )
            content = resp.choices[0].message.content.strip()
        except Exception as e:
            content = f"ERROR: {e}"

        ms = (time.time() - t0) * 1000

        print(f"\n{'='*60}")
        print(f"{fname} — {ms:.0f}ms")
        print(f"{'='*60}")
        print(content)

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
