"""Head-to-head: qwen2.5vl:7b vs llama3.2-vision on same frame."""

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

PROMPT = 'Cricket score? {"frame_type":"X","score":N,"wickets":N,"overs":N,"batter_1":"name","batter_2":"name","bowler":"name"}'

def test_model(model, n=5):
    print(f"\n{'='*60}")
    print(f"MODEL: {model}")
    print(f"{'='*60}")

    # Unload previous model
    requests.post("http://localhost:11434/api/generate",
                  json={"model": model, "keep_alive": 0}, timeout=10)
    time.sleep(1)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "JSON only. No markdown."},
            {"role": "user", "content": PROMPT, "images": [b64]},
        ],
        "stream": False,
        "options": {"num_predict": 80, "num_ctx": 2048},
    }

    for i in range(n):
        t0 = time.monotonic()
        r = requests.post("http://localhost:11434/api/chat", json=payload, timeout=180)
        elapsed = time.monotonic() - t0
        d = r.json()
        pe = d.get("prompt_eval_duration", 0) / 1e9
        ge = d.get("eval_duration", 0) / 1e9
        pt = d.get("prompt_eval_count", "?")
        gt = d.get("eval_count", "?")
        content = d.get("message", {}).get("content", "").replace("\n", " ")[:120]
        label = "COLD" if i == 0 else f"  {i+1} "
        gen_tps = int(gt) / ge if isinstance(gt, int) and ge > 0 else 0
        print(f"  [{label}] {elapsed:5.1f}s  pf={pe:5.1f}s/{pt}tok  gen={ge:4.1f}s/{gt}tok ({gen_tps:.1f}t/s)  | {content}")

test_model("qwen2.5vl:7b", n=5)
test_model("llama3.2-vision", n=5)
