"""Test: compare requests vs aiohttp, full-screen vs broadcast crop."""

import asyncio
import cv2, base64, time, requests as req, numpy as np, sys
import aiohttp
from eyes.capture.frame_source import FrameSource
from eyes.capture.broadcast_detector import BroadcastDetector

fs = FrameSource(window_id=103, fps=2)
fs.start()
time.sleep(1)
raw = fs.get_latest()
fs.stop()
if raw is None:
    print("No frame captured")
    sys.exit(1)

print(f"Raw frame: {raw.shape}")

# Prepare two images: full-screen resize and broadcast crop
h, w = raw.shape[:2]

# Full screen → 960px
scale = 960 / w
full = cv2.resize(raw, (960, int(h * scale)))
_, buf_full = cv2.imencode(".jpg", full, [cv2.IMWRITE_JPEG_QUALITY, 85])
b64_full = base64.b64encode(buf_full.tobytes()).decode()
print(f"Full-screen: {full.shape} ({len(buf_full)/1024:.0f}KB)")

# Broadcast crop → 960px
det = BroadcastDetector()
det.detect(raw)
if det.detected:
    cropped = det.crop(raw)
    ch, cw = cropped.shape[:2]
    cscale = 960 / cw
    bcast = cv2.resize(cropped, (960, int(ch * cscale)))
    _, buf_bcast = cv2.imencode(".jpg", bcast, [cv2.IMWRITE_JPEG_QUALITY, 85])
    b64_bcast = base64.b64encode(buf_bcast.tobytes()).decode()
    print(f"Broadcast crop: {bcast.shape} ({len(buf_bcast)/1024:.0f}KB)")
else:
    print("No broadcast detected, using full")
    b64_bcast = b64_full
    bcast = full

prompt = (
    "Cricket broadcast frame. Short JSON only. "
    "score=total runs (integer). wickets=batters out (0-10). "
    "overs=like 7.4 (max 20). Include frame_type."
)

def make_payload(img_b64):
    return {
        "model": "qwen2.5vl:7b",
        "messages": [
            {"role": "system", "content": "Cricket broadcast analyst. Read numbers exactly. JSON only."},
            {"role": "user", "content": prompt, "images": [img_b64]},
        ],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 200, "num_ctx": 2048},
    }

# Test 1: requests + full screen
print("\n--- Test 1: requests + full-screen 960px ---")
t0 = time.monotonic()
r = req.post("http://localhost:11434/api/chat", json=make_payload(b64_full), timeout=120)
e = time.monotonic() - t0
d = r.json()
print(f"  Time: {e:.1f}s | Tokens: {d.get('prompt_eval_count','?')}/{d.get('eval_count','?')}")
print(f"  {d.get('message',{}).get('content','')[:150]}")

# Test 2: requests + broadcast crop
print("\n--- Test 2: requests + broadcast crop 960px ---")
t0 = time.monotonic()
r = req.post("http://localhost:11434/api/chat", json=make_payload(b64_bcast), timeout=120)
e = time.monotonic() - t0
d = r.json()
print(f"  Time: {e:.1f}s | Tokens: {d.get('prompt_eval_count','?')}/{d.get('eval_count','?')}")
print(f"  {d.get('message',{}).get('content','')[:150]}")

# Test 3: aiohttp + broadcast crop
async def test_aiohttp():
    print("\n--- Test 3: aiohttp + broadcast crop 960px ---")
    async with aiohttp.ClientSession() as session:
        t0 = time.monotonic()
        async with session.post(
            "http://localhost:11434/api/chat",
            json=make_payload(b64_bcast),
            timeout=aiohttp.ClientTimeout(total=120)
        ) as resp:
            d = await resp.json()
        e = time.monotonic() - t0
        print(f"  Time: {e:.1f}s | Tokens: {d.get('prompt_eval_count','?')}/{d.get('eval_count','?')}")
        print(f"  {d.get('message',{}).get('content','')[:150]}")

asyncio.run(test_aiohttp())

# Test 4: aiohttp + broadcast crop (second call, model HOT)
async def test_aiohttp2():
    print("\n--- Test 4: aiohttp + broadcast crop 960px (2nd call) ---")
    async with aiohttp.ClientSession() as session:
        t0 = time.monotonic()
        async with session.post(
            "http://localhost:11434/api/chat",
            json=make_payload(b64_bcast),
            timeout=aiohttp.ClientTimeout(total=120)
        ) as resp:
            d = await resp.json()
        e = time.monotonic() - t0
        print(f"  Time: {e:.1f}s | Tokens: {d.get('prompt_eval_count','?')}/{d.get('eval_count','?')}")
        print(f"  {d.get('message',{}).get('content','')[:150]}")

asyncio.run(test_aiohttp2())
