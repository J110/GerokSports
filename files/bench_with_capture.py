"""Test: does running Quartz capture during Ollama inference slow it down?"""

import cv2, base64, json, time, sys, threading
import requests
from eyes.capture.frame_source import FrameSource
from eyes.capture.downscale import downscale

fs = FrameSource(window_id=103, fps=2)
fs.start()
time.sleep(2)
raw = fs.get_latest()
if raw is None:
    print("No frame captured")
    fs.stop()
    sys.exit(1)

h, w = raw.shape[:2]
scale = 960 / w
frame = cv2.resize(raw, (960, int(h * scale)))
_, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
b64 = base64.b64encode(buf.tobytes()).decode()
print(f"Frame: {frame.shape} ({len(buf)/1024:.0f}KB)")

payload = {
    "model": "qwen2.5vl:7b",
    "messages": [
        {"role": "system", "content": "Cricket broadcast analyst. Read numbers exactly. JSON only."},
        {"role": "user", "content": "Cricket broadcast frame. Short JSON only. score=total runs. wickets=0-10. overs=like 7.4. Include frame_type.", "images": [b64]},
    ],
    "stream": False,
    "options": {"temperature": 0.1, "num_predict": 200, "num_ctx": 2048},
}

# Test 1: WITH capture running
print("\n--- WITH Quartz capture at 2fps ---")
t0 = time.monotonic()
resp = requests.post("http://localhost:11434/api/chat", json=payload, timeout=180)
e = time.monotonic() - t0
d = resp.json()
print(f"  Time: {e:.1f}s | Tokens: {d.get('prompt_eval_count','?')}/{d.get('eval_count','?')}")
print(f"  {d.get('message',{}).get('content','')[:150]}")

# Test 2: STOP capture, then test
fs.stop()
time.sleep(1)
print("\n--- WITHOUT capture (stopped) ---")
t0 = time.monotonic()
resp = requests.post("http://localhost:11434/api/chat", json=payload, timeout=180)
e = time.monotonic() - t0
d = resp.json()
print(f"  Time: {e:.1f}s | Tokens: {d.get('prompt_eval_count','?')}/{d.get('eval_count','?')}")
print(f"  {d.get('message',{}).get('content','')[:150]}")

# Test 3: Start capture again
fs2 = FrameSource(window_id=103, fps=2)
fs2.start()
time.sleep(1)
print("\n--- WITH capture restarted ---")
t0 = time.monotonic()
resp = requests.post("http://localhost:11434/api/chat", json=payload, timeout=180)
e = time.monotonic() - t0
d = resp.json()
print(f"  Time: {e:.1f}s | Tokens: {d.get('prompt_eval_count','?')}/{d.get('eval_count','?')}")
print(f"  {d.get('message',{}).get('content','')[:150]}")
fs2.stop()
