"""Re-run Scout on frames the live pipeline tagged as `release` to
verify whether Scout's production tags match human visual judgment.

For each frame: print Scout's camera_view + frame_phase + has_strip
alongside what a human (me) labels it as.  If Scout consistently says
`release` on what's actually post_shot / closeup / between_play, the
phase tagging is the bottleneck — not temporal diversity.
"""
from __future__ import annotations
import asyncio
import base64
import json
import time
from pathlib import Path

import cv2
from groq import AsyncGroq

from eyes.config import GROQ_API_KEY, GROQ_PRIMARY_MODEL
from eyes.vision import SCOUT_PROMPT, Vision


# (path, human_label, expected_to_be_useful)
FRAMES = [
    ("logs/deliveries/20260419_230742/d004/frame_00.jpg",
     "wide_field_post_shot",     False),
    ("logs/deliveries/20260419_230742/d004/frame_01.jpg",
     "closeup_batter_helmet",    False),
    ("logs/deliveries/20260419_230742/d005/frame_00.jpg",
     "closeup_player_waving",    False),
    ("logs/deliveries/20260419_230742/d005/frame_01.jpg",
     "TRUE_release_bowler_run",  True),
    ("logs/deliveries/20260419_230742/d007/frame_00.jpg",
     "post_shot_batter_back",    False),
    ("logs/deliveries/20260419_230742/d007/frame_03.jpg",
     "stadium_aerial",           False),
    ("logs/deliveries/20260419_230742/d008/frame_00.jpg",
     "fielder_chase_boundary",   False),
    ("logs/deliveries/20260419_230742/d008/frame_01.jpg",
     "wide_post_shot_fielders",  False),
    ("logs/deliveries/20260419_230742/d008/frame_02.jpg",
     "closeup_batter_helmet",    False),
    ("logs/deliveries/20260419_230742/d008/frame_03.jpg",
     "between_play_walkoff",     False),
]


def encode(p: str) -> str:
    bgr = cv2.imread(p)
    h, w = bgr.shape[:2]
    if w > 1280:
        bgr = cv2.resize(bgr, (1280, int(h * 1280 / w)),
                         interpolation=cv2.INTER_AREA)
    _, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buf.tobytes()).decode("ascii")


async def main():
    if not GROQ_API_KEY:
        raise SystemExit("GROQ_API_KEY missing")
    client = AsyncGroq(api_key=GROQ_API_KEY, timeout=15)
    prompt = SCOUT_PROMPT.format(vision_hint="None.")

    print(f"{'frame':<55} {'human':<26} "
          f"{'cam':<11} {'phase':<14} {'strip':<5}")
    print("-" * 115)

    matches = 0
    for path, human, useful in FRAMES:
        b64 = encode(path)
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
        except Exception as e:
            print(f"  {Path(path).name}  ERROR {e}")
            continue
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

        # "Match" = Scout's classification is consistent with human
        # judgment.  For a non-release/post_shot frame, "match" means
        # Scout DIDN'T tag it release/flight/shot.
        is_action = ph in ("release", "flight", "shot")
        ok = (useful and is_action) or (not useful and not is_action)
        matches += int(ok)

        flag = "OK" if ok else "MISS"
        short = Path(path).parent.name + "/" + Path(path).name
        print(f"  {short:<53} {human:<26} "
              f"{str(cv):<11} {str(ph):<14} {str(strip):<5} {flag}")

    print()
    print(f"agreement: {matches}/{len(FRAMES)} "
          f"({matches*100/len(FRAMES):.0f}%)")


if __name__ == "__main__":
    asyncio.run(main())
