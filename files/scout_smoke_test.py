"""Verify Llama-4-Scout on Groq accepts a 16-frame burst before we
burn the full bake-off run."""
from __future__ import annotations

import base64
import sys
from pathlib import Path

import cv2
from openai import OpenAI

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from eyes.config import GROQ_API_KEY, GROQ_PRIMARY_MODEL  # noqa: E402

CLIP = ROOT / "logs/deliveries/20260420_140137/windows/window_0021/delivery_window.mp4"


def burst(mp4: str, n: int) -> list[bytes]:
    cap = cv2.VideoCapture(mp4)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    out = []
    for i in range(n):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * (i + 0.5) / n))
        ok, fr = cap.read()
        if ok:
            ok, j = cv2.imencode(".jpg", fr,
                                 [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if ok:
                out.append(j.tobytes())
    cap.release()
    return out


def b64(d): return base64.b64encode(d).decode()


def call(n_frames: int):
    frames = burst(str(CLIP), n_frames)
    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=GROQ_API_KEY,
    )
    content = [
        {"type": "image_url",
         "image_url": {"url": f"data:image/jpeg;base64,{b64(f)}"}}
        for f in frames
    ]
    content.append({"type": "text",
                    "text": "How many frames are in this sequence? "
                            "Reply with just a number."})
    try:
        resp = client.chat.completions.create(
            model=GROQ_PRIMARY_MODEL,
            messages=[{"role": "user", "content": content}],
            max_tokens=200,
            temperature=0.1,
        )
        u = resp.usage
        print(f"  n={n_frames}: OK  in={u.prompt_tokens} "
              f"out={u.completion_tokens}  reply='{resp.choices[0].message.content[:80]}'")
        return True
    except Exception as e:  # noqa: BLE001
        msg = str(e)[:300]
        print(f"  n={n_frames}: FAIL  {msg}")
        return False


for n in (16, 8, 5, 4, 3):
    if call(n):
        print(f"\n→ MAX usable: {n} frames per Scout call.\n")
        break
