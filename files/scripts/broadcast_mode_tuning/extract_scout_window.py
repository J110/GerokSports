#!/usr/bin/env python3
"""Extract 1fps frames from a time window and Scout-caption them.

For each integer second t in [start, end), pull a single jpg with
ffmpeg, encode base64, hit Groq with the OPEN_PROMPT, write a sidecar
.txt mirroring the first_5min_scout_run header format.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import os
import subprocess
import sys
import time
from pathlib import Path

from groq import AsyncGroq

REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_VIDEO = REPO_ROOT / "files/logs/deliveries/dfb1c947/match_dfb1c947.mp4"
DEFAULT_OUT = REPO_ROOT / "files/scripts/broadcast_mode_tuning/second_5min_scout_run"

FPS_SOURCE = 25.0
MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
TEMPERATURE = 0.2
MAX_TOKENS = 220
TIMEOUT_S = 20.0
CONCURRENCY = 3
THROTTLE_S = 0.35

OPEN_PROMPT = (
    "This is a single frame from a professional cricket match "
    "broadcast on television.\n\n"
    "Describe what you see in this frame in detail. Specifically "
    "address:\n"
    "- What is the camera showing? (e.g., wide field view, closeup "
    "of a player, crowd shot, score graphic)\n"
    "- What are the people in the frame doing? (e.g., bowler "
    "running, batter standing, players talking, fielders walking)\n"
    "- Are there any graphical overlays? (e.g., score graphics, "
    "REPLAY tags, sponsor logos, player stats)\n"
    "- What does the action level look like? (e.g., active play "
    "happening, between deliveries, post-action moment, replay or "
    "slow-motion)\n\n"
    "Provide a 2-4 sentence description in plain language. Don't "
    "classify the frame; just describe it.\n"
)

GROQ_KEY = os.environ.get(
    "GROQ_API_KEY",
    os.environ["GROQ_API_KEY"],
)

progress = {"done": 0, "errors": 0, "rate_limited": 0}
progress_lock = asyncio.Lock()


def extract_jpg(video: Path, t: float, out: Path) -> bool:
    if out.exists() and out.stat().st_size > 0:
        return True
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{t:.3f}",
        "-i", str(video),
        "-frames:v", "1",
        "-q:v", "2",
        str(out),
    ]
    try:
        subprocess.run(cmd, check=True)
        return out.exists() and out.stat().st_size > 0
    except subprocess.CalledProcessError:
        return False


async def call_scout(client: AsyncGroq, b64: str) -> tuple[str, str | None]:
    delay = 1.0
    last_err = None
    for attempt in range(4):
        try:
            resp = await asyncio.wait_for(
                client.chat.completions.create(
                    model=MODEL,
                    temperature=TEMPERATURE,
                    max_tokens=MAX_TOKENS,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image_url",
                             "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                            {"type": "text", "text": OPEN_PROMPT},
                        ],
                    }],
                ),
                timeout=TIMEOUT_S,
            )
            text = ""
            if resp.choices and resp.choices[0].message:
                text = (resp.choices[0].message.content or "").strip()
            return text, None
        except Exception as e:  # noqa: BLE001
            last_err = repr(e)
            msg = str(e).lower()
            if "rate" in msg or "429" in msg:
                async with progress_lock:
                    progress["rate_limited"] += 1
                await asyncio.sleep(delay + attempt * 2.0)
                delay = min(delay * 2, 8.0)
                continue
            await asyncio.sleep(delay)
            delay = min(delay * 2, 8.0)
    return "", last_err


def write_sidecar(txt_path: Path, t: float, frame_no: int, prose: str,
                  err: str | None) -> None:
    yn = "Y"  # placeholder; downstream pipeline ignores header fields
    nn = "N"
    with open(txt_path, "w") as f:
        f.write(f"frame_idx: {frame_no}\n")
        f.write(f"rel_t: {t:.3f}\n")
        f.write(f"frame_no: {frame_no}\n")
        f.write("binary_label: UNCLASSIFIED\n")
        f.write("classify_reason: extract_scout_window\n")
        f.write("signals:\n")
        f.write(f"  has_action: {nn}\n")
        f.write(f"  has_score: {nn}\n")
        f.write(f"  is_replay_hard: {nn}\n")
        f.write(f"  is_crowd_dominant: {nn}\n")
        if err:
            f.write(f"error: {err}\n")
        f.write("---\n")
        f.write(prose)
        f.write("\n")


async def worker(client: AsyncGroq, queue: asyncio.Queue, total: int) -> None:
    while True:
        item = await queue.get()
        if item is None:
            queue.task_done()
            return
        t, frame_no, jpg, txt = item
        try:
            with open(jpg, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            prose, err = await call_scout(client, b64)
            write_sidecar(txt, t, frame_no, prose, err)
            async with progress_lock:
                progress["done"] += 1
                if err:
                    progress["errors"] += 1
                d = progress["done"]
                if d % 25 == 0 or d == total:
                    print(f"  [{d}/{total}] errors={progress['errors']} "
                          f"rate_limited={progress['rate_limited']}",
                          flush=True)
        finally:
            queue.task_done()


async def producer(queue: asyncio.Queue, video: Path, out_dir: Path,
                   start: int, end: int) -> int:
    last = 0.0
    extracted = 0
    for t in range(start, end):
        frame_no = int(t * FPS_SOURCE)
        stem = f"f_{frame_no:05d}_t={float(t):06.2f}"
        jpg = out_dir / f"{stem}.jpg"
        txt = out_dir / f"{stem}.txt"
        if not jpg.exists() or jpg.stat().st_size == 0:
            ok = extract_jpg(video, float(t), jpg)
            if not ok:
                print(f"  ffmpeg failed at t={t}", flush=True)
                continue
        # throttle dispatch
        if THROTTLE_S > 0:
            now = time.time()
            wait = (last + THROTTLE_S) - now
            if wait > 0:
                await asyncio.sleep(wait)
            last = time.time()
        await queue.put((t, frame_no, jpg, txt))
        extracted += 1
        if t % 25 == 0:
            print(f"  dispatched t={t}", flush=True)
    return extracted


async def main_async(args) -> int:
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    video = Path(args.video)
    if not video.exists():
        sys.exit(f"video missing: {video}")

    print(f"Video:       {video}")
    print(f"Out dir:     {out_dir}")
    print(f"Window:      {args.start}-{args.end}s "
          f"({args.end - args.start} frames)")
    print(f"Concurrency: {CONCURRENCY}, throttle={THROTTLE_S}s")

    queue: asyncio.Queue = asyncio.Queue(maxsize=CONCURRENCY * 4)
    client = AsyncGroq(api_key=GROQ_KEY, timeout=TIMEOUT_S + 5)

    total = args.end - args.start
    workers = [
        asyncio.create_task(worker(client, queue, total))
        for _ in range(CONCURRENCY)
    ]

    t0 = time.time()
    await producer(queue, video, out_dir, args.start, args.end)
    print("Producer done; waiting on Scout calls...", flush=True)
    for _ in workers:
        await queue.put(None)
    await asyncio.gather(*workers)

    dt = time.time() - t0
    print(f"Done in {dt:.1f}s. errors={progress['errors']} "
          f"rate_limited={progress['rate_limited']}")

    # Verify
    jpgs = sorted(out_dir.glob("f_*.jpg"))
    txts = sorted(out_dir.glob("f_*.txt"))
    empty = 0
    for p in txts:
        raw = p.read_text()
        prose = raw.split("---\n", 1)[1].strip() if "---\n" in raw else ""
        if not prose:
            empty += 1
    print(f"Verify: {len(jpgs)} jpgs, {len(txts)} txts, "
          f"{empty} empty prose, {progress['errors']} errors")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=str(DEFAULT_VIDEO))
    ap.add_argument("--output-dir", default=str(DEFAULT_OUT))
    ap.add_argument("--start", type=int, default=300)
    ap.add_argument("--end", type=int, default=600)
    args = ap.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
