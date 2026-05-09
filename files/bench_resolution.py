"""Quick benchmark: test Qwen2.5-VL latency at different image resolutions."""

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

print(f"Raw frame: {raw.shape}")

prompt = (
    "Cricket broadcast frame. Short JSON only. "
    "score=total runs (integer). wickets=batters out (0-10). "
    "overs=like 7.4 (max 20). Include frame_type."
)

for width in [480, 640, 800, 960, 1280]:
    h, w = raw.shape[:2]
    scale = width / w
    new_h = int(h * scale)
    resized = cv2.resize(raw, (width, new_h))
    _, buf = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 85])
    b64 = base64.b64encode(buf.tobytes()).decode()

    payload = {
        "model": "qwen2.5vl:7b",
        "messages": [
            {"role": "system", "content": "You extract cricket data from broadcast frames. Reply with JSON only."},
            {"role": "user", "content": prompt, "images": [b64]},
        ],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 200, "num_ctx": 2048},
    }

    print(f"\n--- {width}x{new_h} (JPEG {len(buf)/1024:.0f}KB) ---")
    t0 = time.monotonic()
    try:
        resp = requests.post("http://localhost:11434/api/chat", json=payload, timeout=120)
        elapsed = time.monotonic() - t0
        data = resp.json()
        content = data.get("message", {}).get("content", "")
        tokens = data.get("eval_count", "?")
        prompt_tokens = data.get("prompt_eval_count", "?")
        print(f"  Time: {elapsed:.1f}s | Prompt tokens: {prompt_tokens} | Output tokens: {tokens}")
        print(f"  Response: {content[:250]}")
    except requests.Timeout:
        elapsed = time.monotonic() - t0
        print(f"  TIMEOUT after {elapsed:.0f}s")
    except Exception as e:
        print(f"  ERROR: {e}")
