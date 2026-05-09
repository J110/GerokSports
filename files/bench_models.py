"""Compare models and test for degradation over repeated calls."""

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

PROMPT = "Cricket broadcast frame. What is the score? Short JSON only."

def test_model(model, num_ctx, n=6):
    print(f"\n{'='*60}")
    print(f"MODEL: {model}  (num_ctx={num_ctx}, {n} calls)")
    print(f"{'='*60}")

    # Unload any loaded model first
    requests.post("http://localhost:11434/api/generate",
                  json={"model": model, "keep_alive": 0}, timeout=10)
    time.sleep(1)

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": PROMPT, "images": [b64]},
        ],
        "stream": False,
        "options": {"num_predict": 100, "num_ctx": num_ctx},
    }

    for i in range(n):
        t0 = time.monotonic()
        r = requests.post("http://localhost:11434/api/chat", json=payload, timeout=180)
        elapsed = time.monotonic() - t0
        d = r.json()
        pe_dur = d.get("prompt_eval_duration", 0) / 1e9
        ge_dur = d.get("eval_duration", 0) / 1e9
        pt = d.get("prompt_eval_count", "?")
        gt = d.get("eval_count", "?")
        content = d.get("message", {}).get("content", "")[:120].replace("\n", " ")
        label = "COLD" if i == 0 else f"  {i+1} "
        print(f"  [{label}] {elapsed:5.1f}s  prefill={pe_dur:5.1f}s/{pt}tok  gen={ge_dur:5.1f}s/{gt}tok  | {content}")

test_model("qwen2.5vl:7b", num_ctx=2048, n=6)
test_model("moondream:latest", num_ctx=2048, n=6)
