"""Test: use EXACT same pipeline as Eyes (broadcast crop + downscale)
but with synchronous requests instead of aiohttp in an event loop."""

import cv2, base64, json, time, sys
import requests
from eyes.capture.frame_source import FrameSource
from eyes.capture.broadcast_detector import BroadcastDetector
from eyes.capture.downscale import downscale

fs = FrameSource(window_id=103, fps=2)
fs.start()
time.sleep(2)
raw = fs.get_latest()
fs.stop()
if raw is None:
    print("No frame captured")
    sys.exit(1)

print(f"Raw: {raw.shape}")

det = BroadcastDetector()
det.detect(raw)
if not det.detected:
    print("No broadcast detected, using raw")
    frame = raw
else:
    frame = det.crop(raw)

frame = downscale(frame, 960)
print(f"Downscaled: {frame.shape}")

_, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
b64 = base64.b64encode(buf.tobytes()).decode()
print(f"JPEG: {len(buf)/1024:.0f}KB, base64: {len(b64)/1024:.0f}KB")

payload = {
    "model": "qwen2.5vl:7b",
    "messages": [
        {"role": "system", "content": "Cricket broadcast analyst. Read numbers exactly. JSON only."},
        {"role": "user", "content": "Cricket broadcast frame. Short JSON only. score=total runs (integer). wickets=batters out (0-10). overs=like 7.4 (max 20). Include frame_type.", "images": [b64]},
    ],
    "stream": False,
    "options": {"temperature": 0.1, "num_predict": 200, "num_ctx": 2048},
}

for i in range(3):
    label = "COLD" if i == 0 else f"WARM-{i}"
    print(f"\n--- {label} ---")
    t0 = time.monotonic()
    resp = requests.post("http://localhost:11434/api/chat", json=payload, timeout=180)
    elapsed = time.monotonic() - t0
    d = resp.json()
    ptoks = d.get("prompt_eval_count", "?")
    otoks = d.get("eval_count", "?")
    content = d.get("message", {}).get("content", "")
    print(f"  Time: {elapsed:.1f}s | Prompt: {ptoks} | Output: {otoks}")
    print(f"  {content[:200]}")
