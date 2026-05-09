"""Bare loop: capture ONE frame, STOP capture, call Ollama, repeat.

Tests whether continuous Quartz capture is what slows Ollama down.
"""

import base64
import json
import time
import sys

import cv2
import numpy as np
import requests

from eyes.capture.frame_source import FrameSource
from eyes.capture.broadcast_detector import BroadcastDetector
from eyes.capture.downscale import downscale
from eyes.config import DOWNSCALE_WIDTH, VISION_MODEL, OLLAMA_HOST
from eyes.vision.prompts import FAST_PROMPT

WINDOW_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 103


def encode(frame):
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buf.tobytes()).decode()


def call_ollama(b64):
    payload = {
        "model": VISION_MODEL,
        "messages": [
            {"role": "system", "content": "Cricket broadcast analyst. Read numbers exactly. JSON only."},
            {"role": "user", "content": FAST_PROMPT, "images": [b64]},
        ],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 200, "num_ctx": 2048},
    }
    return requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=120)


def grab_one_frame():
    """Start capture, grab one frame, stop capture immediately."""
    fs = FrameSource(window_id=WINDOW_ID, fps=2)
    fs.start()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        f = fs.get_latest()
        if f is not None:
            fs.stop()
            return f
        time.sleep(0.1)
    fs.stop()
    return None


def main():
    print(f"Bare loop (no continuous capture): model={VISION_MODEL}, width={DOWNSCALE_WIDTH}")

    # Warmup
    print("Warming up model...")
    t0 = time.monotonic()
    tiny = encode(np.zeros((64, 64, 3), dtype=np.uint8))
    requests.post(f"{OLLAMA_HOST}/api/chat", json={
        "model": VISION_MODEL,
        "messages": [{"role": "user", "content": "Hi", "images": [tiny]}],
        "stream": False,
        "options": {"num_predict": 1, "num_ctx": 2048},
    }, timeout=180)
    print(f"Model warm in {time.monotonic()-t0:.1f}s")

    bd = BroadcastDetector()

    for i in range(5):
        raw = grab_one_frame()
        if raw is None:
            print(f"[{i+1}] No frame captured")
            continue

        if not bd.detected:
            bd.detect(raw)
            if not bd.detected:
                print(f"[{i+1}] No broadcast detected")
                continue

        frame = bd.crop(raw)
        frame = downscale(frame, DOWNSCALE_WIDTH)
        h, w = frame.shape[:2]
        b64 = encode(frame)
        kb = len(b64) * 3 // 4 // 1024

        print(f"[{i+1}] {w}x{h} ({kb}KB)...", end=" ", flush=True)
        t0 = time.monotonic()
        resp = call_ollama(b64)
        elapsed = time.monotonic() - t0
        data = resp.json()
        ptoks = data.get("prompt_eval_count", "?")
        otoks = data.get("eval_count", "?")
        content = data.get("message", {}).get("content", "")[:200]
        print(f"{elapsed:.1f}s (p={ptoks} o={otoks}) → {content}")


if __name__ == "__main__":
    main()
