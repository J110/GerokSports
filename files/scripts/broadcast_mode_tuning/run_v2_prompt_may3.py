#!/usr/bin/env python3
"""OpenScout v2 prompt diagnostic on the May 3 (20260503_205835) corpus.

Samples each delivery_window.mp4 at 1 fps, sends each frame to Groq with
OPEN_PROMPT_V2 (imported from eyes.open_scout), routes the response through
classify_full (eyes.open_scout_classify), and prints the per-frame class
together with the first 200 chars of the raw response.  Mirrors output to
may3_v2_prompt_results.txt and prints class totals.

Usage::
    cd files/scripts/broadcast_mode_tuning
    PYTHONPATH=../.. python3 run_v2_prompt_may3.py
"""
from __future__ import annotations

import asyncio
import base64
import json
import sys
from collections import Counter
from pathlib import Path

import cv2

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent.parent
CORPUS_DIR = REPO_ROOT / "files" / "logs" / "deliveries" / "20260503_205835"
OUTPUT_TXT = SCRIPT_DIR / "may3_v2_prompt_results.txt"


def _ensure_path() -> None:
    root_s = str((REPO_ROOT / "files").resolve())
    if root_s not in sys.path:
        sys.path.insert(0, root_s)


def sample_frames_1fps(mp4_path: Path) -> list[tuple[float, bytes]]:
    cap = cv2.VideoCapture(str(mp4_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if fps <= 0 or total <= 0:
        cap.release()
        return []
    duration = total / fps
    out: list[tuple[float, bytes]] = []
    t = 0.0
    while t <= duration + 1e-3:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            t += 1.0
            continue
        ok2, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok2:
            out.append((t, buf.tobytes()))
        t += 1.0
    cap.release()
    return out


async def describe(client, model: str, prompt: str, jpg: bytes,
                   timeout_s: float = 90.0) -> str:
    b64 = base64.b64encode(jpg).decode()
    try:
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                temperature=0.2,
                max_tokens=220,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        {"type": "text", "text": prompt},
                    ],
                }],
            ),
            timeout=timeout_s,
        )
        if resp.choices and resp.choices[0].message:
            return (resp.choices[0].message.content or "").strip()
        return ""
    except asyncio.TimeoutError:
        return "[timeout]"
    except Exception as e:  # noqa: BLE001
        return f"[err: {e}]"


async def main_async() -> int:
    _ensure_path()
    from groq import AsyncGroq
    from eyes.config import GROQ_API_KEY, GROQ_PRIMARY_MODEL
    from eyes.open_scout import OPEN_PROMPT_V2
    from eyes.open_scout_classify import classify_full

    clip_dirs = sorted(p for p in CORPUS_DIR.glob("d*") if p.is_dir())
    if not clip_dirs:
        print(f"No clips in {CORPUS_DIR}", file=sys.stderr)
        return 1

    client = AsyncGroq(api_key=GROQ_API_KEY, timeout=90.0)
    out_lines: list[str] = []
    totals: Counter[str] = Counter()

    def emit(line: str) -> None:
        print(line, flush=True)
        out_lines.append(line)

    for clip in clip_dirs:
        mp4 = clip / "delivery_window.mp4"
        meta_path = clip / "window_debug.json"
        try:
            meta = json.loads(meta_path.read_text())
            event_in_clip = meta["event_ts"] - meta["clip_start_ts"]
            duration = meta["clip_end_ts"] - meta["clip_start_ts"]
        except Exception:
            event_in_clip = float("nan")
            duration = float("nan")

        emit("=" * 20)
        emit(f"[CLIP {clip.name}] dur={duration:.2f}s event_ts={event_in_clip:.2f}s")
        emit("")

        for t, jpg in sample_frames_1fps(mp4):
            raw = await describe(client, GROQ_PRIMARY_MODEL, OPEN_PROMPT_V2, jpg)
            cls = classify_full(raw)
            totals[cls] += 1
            preview = " ".join(raw.split())[:200]
            emit(f"  {t:5.2f}s  class={cls}")
            emit(f"    raw: \"{preview}\"")
            await asyncio.sleep(0.35)
        emit("")

    await client.close()

    emit("=" * 20)
    summary = ("Total class counts across 8 clips: "
               + ", ".join(f"{c}={totals.get(c, 0)}"
                           for c in ("action", "replay", "ad", "umpire", "other")))
    emit(summary)

    OUTPUT_TXT.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"\nWrote {OUTPUT_TXT}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
