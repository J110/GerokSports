"""Cold-start benchmark: model unloaded, first request triggers load."""

import cv2, base64, time, requests, numpy as np, sys
from eyes.capture.frame_source import FrameSource

fs = FrameSource(window_id=103, fps=2)
fs.start()
time.sleep(1)
raw = fs.get_latest()
fs.stop()
if raw is None:
    print("No frame captured")
    sys.exit(1)

h, w = raw.shape[:2]
scale = 960 / w
resized = cv2.resize(raw, (960, int(h * scale)))
_, buf = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 85])
b64 = base64.b64encode(buf.tobytes()).decode()

prompt = (
    "Cricket broadcast frame. Short JSON only. "
    "score=total runs (integer). wickets=batters out (0-10). "
    "overs=like 7.4 (max 20). Include frame_type."
)

payload = {
    "model": "qwen2.5vl:7b",
    "messages": [
        {"role": "system", "content": "You extract cricket data from broadcast frames. Reply with JSON only."},
        {"role": "user", "content": prompt, "images": [b64]},
    ],
    "stream": False,
    "options": {"temperature": 0.1, "num_predict": 200, "num_ctx": 2048},
}

for i in range(3):
    label = "COLD" if i == 0 else f"WARM-{i}"
    print(f"\n--- Request {i+1} ({label}) ---")
    t0 = time.monotonic()
    try:
        resp = requests.post("http://localhost:11434/api/chat", json=payload, timeout=120)
        elapsed = time.monotonic() - t0
        data = resp.json()
        content = data.get("message", {}).get("content", "")
        ptoks = data.get("prompt_eval_count", "?")
        otoks = data.get("eval_count", "?")
        print(f"  Time: {elapsed:.1f}s | Prompt: {ptoks} | Output: {otoks}")
        print(f"  Response: {content[:200]}")
    except requests.Timeout:
        elapsed = time.monotonic() - t0
        print(f"  TIMEOUT after {elapsed:.0f}s")
    except Exception as e:
        print(f"  ERROR: {e}")
