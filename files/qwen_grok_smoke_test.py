"""Smoke test: verify each Qwen + Grok model accepts our inputs and
returns parseable JSON before we burn 180 calls on the full matrix.

For each model, we try:
  1. Native video input (base64-encoded mp4) — if the model supports it.
  2. Multi-image input (3 frames extracted from the clip) — fallback
     for models without video, and the only path for Grok.

Pass criteria: HTTP 200, non-empty response, parses to JSON-ish dict.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).parent

FIREWORKS_API_KEY = "fw_8Kyu9Ug7kXVp6kPRDvhL3n"
XAI_API_KEY = (
    "xai-QFdbmyTWtrbBHzPvDyLqbEgP8HUWQNqbXCcyrEG0ZpfJfFFjXcHKTODYHJ8TQZ6CK10J3Quy02eGSeiX")

QWEN_MODELS = {
    # Only the 30B-A3B variants are serverless on Fireworks today.
    # 8B/32B/235B require dedicated on-demand GPU deployments ($/hr).
    "qwen3vl-30b-instruct": "accounts/fireworks/models/qwen3-vl-30b-a3b-instruct",
    "qwen3vl-30b-thinking": "accounts/fireworks/models/qwen3-vl-30b-a3b-thinking",
}
GROK_MODEL = "grok-4-1-fast-non-reasoning"  # vision, no reasoning overhead

# Use the smallest existing clip so the smoke test is fast/cheap
TEST_CLIP = ROOT / ("logs/deliveries/20260420_140137/windows/"
                    "window_0021/delivery_window.mp4")

SMOKE_PROMPT = """\
You are watching a short cricket-delivery video clip from the bowler's-end \
camera.  Return ONLY a single-line JSON object:

{"is_valid_delivery": true | false, "length": "short" | "good_length" | \
"full" | "yorker" | "bouncer" | "unknown", "shot_type": string, \
"narrative": "<one sentence>"}
"""


def parse_json(s):
    if not s:
        return None
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s.strip())
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def extract_keyframes(mp4_path: str, n: int = 3) -> list[bytes]:
    """Pick n frames evenly spaced through the clip, encode as JPEG."""
    cap = cv2.VideoCapture(mp4_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        cap.release()
        return []
    indices = [int(total * (i + 0.5) / n) for i in range(n)]
    out = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            continue
        ok, jpg = cv2.imencode(".jpg", frame,
                               [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if ok:
            out.append(jpg.tobytes())
    cap.release()
    return out


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def try_qwen_video(model_id: str, mp4_path: str, prompt: str):
    from openai import OpenAI
    client = OpenAI(
        base_url="https://api.fireworks.ai/inference/v1",
        api_key=FIREWORKS_API_KEY,
    )
    data = Path(mp4_path).read_bytes()
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model_id,
        messages=[{
            "role": "user",
            "content": [
                {"type": "video_url",
                 "video_url": {
                     "url": f"data:video/mp4;base64,{b64(data)}"}},
                {"type": "text", "text": prompt},
            ],
        }],
        max_tokens=600,
        temperature=0.2,
    )
    ms = int((time.time() - t0) * 1000)
    return resp.choices[0].message.content, ms, resp.usage


def try_qwen_frames(model_id: str, frames: list[bytes], prompt: str):
    from openai import OpenAI
    client = OpenAI(
        base_url="https://api.fireworks.ai/inference/v1",
        api_key=FIREWORKS_API_KEY,
    )
    content = []
    for f in frames:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64(f)}"},
        })
    content.append({"type": "text", "text": prompt})
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model_id,
        messages=[{"role": "user", "content": content}],
        max_tokens=600,
        temperature=0.2,
    )
    ms = int((time.time() - t0) * 1000)
    return resp.choices[0].message.content, ms, resp.usage


def try_grok_frames(frames: list[bytes], prompt: str):
    from openai import OpenAI
    client = OpenAI(
        base_url="https://api.x.ai/v1",
        api_key=XAI_API_KEY,
    )
    content = []
    for f in frames:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{b64(f)}",
                "detail": "high",
            },
        })
    content.append({"type": "text", "text": prompt})
    t0 = time.time()
    resp = client.chat.completions.create(
        model=GROK_MODEL,
        messages=[{"role": "user", "content": content}],
        max_tokens=600,
        temperature=0.2,
    )
    ms = int((time.time() - t0) * 1000)
    return resp.choices[0].message.content, ms, resp.usage


def main():
    if not TEST_CLIP.exists():
        sys.exit(f"missing test clip: {TEST_CLIP}")
    mp4 = str(TEST_CLIP)
    print(f"test clip: {mp4} ({TEST_CLIP.stat().st_size/1024:.0f} KB)\n")

    frames = extract_keyframes(mp4, n=3)
    print(f"extracted {len(frames)} keyframes "
          f"(sizes: {[f'{len(f)/1024:.0f}KB' for f in frames]})\n")

    summary = []

    for tag, model_id in QWEN_MODELS.items():
        print(f"=== {tag}  model={model_id} ===")
        # Try video first
        try:
            text, ms, usage = try_qwen_video(model_id, mp4, SMOKE_PROMPT)
            parsed = parse_json(text)
            print(f"  VIDEO  {ms} ms   in={getattr(usage, 'prompt_tokens', '?')} "
                  f"out={getattr(usage, 'completion_tokens', '?')}")
            print(f"   parsed: {json.dumps(parsed) if parsed else text[:200]}")
            summary.append((tag, "video", "OK", ms, bool(parsed)))
        except Exception as e:  # noqa: BLE001
            err = str(e)[:300]
            print(f"  VIDEO  FAILED: {err}")
            summary.append((tag, "video", "FAIL", 0, False))
            # Fall back to frames
            try:
                text, ms, usage = try_qwen_frames(model_id, frames,
                                                  SMOKE_PROMPT)
                parsed = parse_json(text)
                print(f"  FRAMES {ms} ms   in={getattr(usage, 'prompt_tokens', '?')} "
                      f"out={getattr(usage, 'completion_tokens', '?')}")
                print(f"   parsed: {json.dumps(parsed) if parsed else text[:200]}")
                summary.append((tag, "frames", "OK", ms, bool(parsed)))
            except Exception as e2:  # noqa: BLE001
                err2 = str(e2)[:300]
                print(f"  FRAMES FAILED: {err2}")
                summary.append((tag, "frames", "FAIL", 0, False))
        print()

    print(f"=== grok  model={GROK_MODEL}  (frames only) ===")
    try:
        text, ms, usage = try_grok_frames(frames, SMOKE_PROMPT)
        parsed = parse_json(text)
        print(f"  FRAMES {ms} ms   in={getattr(usage, 'prompt_tokens', '?')} "
              f"out={getattr(usage, 'completion_tokens', '?')}")
        print(f"   parsed: {json.dumps(parsed) if parsed else text[:200]}")
        summary.append(("grok", "frames", "OK", ms, bool(parsed)))
    except Exception as e:  # noqa: BLE001
        err = str(e)[:400]
        print(f"  FRAMES FAILED: {err}")
        summary.append(("grok", "frames", "FAIL", 0, False))

    print("\n=== summary ===")
    print(f"{'model':14s} {'mode':7s} {'status':6s} {'ms':>6s} {'parsed':>7s}")
    for row in summary:
        print(f"{row[0]:14s} {row[1]:7s} {row[2]:6s} "
              f"{row[3]:>6d} {str(row[4]):>7s}")


if __name__ == "__main__":
    main()
