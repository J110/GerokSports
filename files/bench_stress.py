"""Stress test: 10 requests with timing breakdown to detect degradation."""

import time, requests, base64, numpy as np, cv2, sys
from eyes.capture.frame_source import FrameSource
from eyes.capture.broadcast_detector import BroadcastDetector
from eyes.capture.downscale import downscale

WINDOW_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 103

fs = FrameSource(window_id=WINDOW_ID, fps=2)
fs.start()
time.sleep(2)
raw = fs.get_latest()
fs.stop()

bd = BroadcastDetector()
bd.detect(raw)
frame = bd.crop(raw) if bd.detected else raw
frame = downscale(frame, 960)
_, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
b64 = base64.b64encode(buf.tobytes()).decode()
print(f"Frame: {frame.shape} ({len(buf)//1024}KB)")

payload = {
    "model": "qwen2.5vl:7b",
    "messages": [
        {"role": "system", "content": "JSON only."},
        {"role": "user", "content": "Cricket score? Short JSON.", "images": [b64]},
    ],
    "stream": False,
    "options": {"num_predict": 50, "num_ctx": 2048},
}

for i in range(10):
    t0 = time.monotonic()
    r = requests.post("http://localhost:11434/api/chat", json=payload, timeout=180)
    elapsed = time.monotonic() - t0
    d = r.json()
    pe = d.get("prompt_eval_duration", 0) / 1e9
    ge = d.get("eval_duration", 0) / 1e9
    pt = d.get("prompt_eval_count", "?")
    gt = d.get("eval_count", "?")
    content = d.get("message", {}).get("content", "").replace("\n", " ")[:80]
    label = "COLD" if i == 0 else f"  {i+1:2d}"
    print(f"  [{label}] {elapsed:5.1f}s  pf={pe:5.1f}s/{pt}tok  gen={ge:4.1f}s/{gt}tok  | {content}")
