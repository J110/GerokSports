#!/usr/bin/env python3
"""Extract every frame from the first 5 min of dfb1c947 mp4, call Scout on each, save paired jpg+txt, then run delivery-zone detection."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path

import cv2
from groq import AsyncGroq

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from detect_delivery_zones import (  # noqa: E402
    classify, has_action, has_strong_score, has_weak_info, is_not_delivery,
    smooth, detect_blocks, annotate, Frame,
)

VIDEO = REPO_ROOT / "files/logs/deliveries/dfb1c947/match_dfb1c947.mp4"
OUT = REPO_ROOT / "files/scripts/broadcast_mode_tuning/first_5min_scout_run"

FPS = 25.0
DURATION_S = 300.0
N_FRAMES = int(FPS * DURATION_S)
FRAME_STRIDE = 25
MIN_DISPATCH_INTERVAL_S = 1.0

MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
TEMPERATURE = 0.2
MAX_TOKENS = 220
TIMEOUT_S = 20.0
CONCURRENCY = 1
JPEG_QUALITY = 70

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


def yn(b: bool) -> str:
    return "Y" if b else "N"


def write_pair_text(txt_path: Path, i: int, rel_t: float, frame_no: int, text: str, error: str | None) -> None:
    is_d, reason = classify(text) if not error else (False, "n/a")
    a = has_action(text) if not error else False
    sc = has_scoreboard(text) if not error else False
    nd, nd_reason = is_not_delivery(text) if not error else (False, "")
    is_replay_hard = nd and nd_reason.startswith(("replay-overlay", "analysis-as-graphic"))
    is_crowd_dominant = nd and nd_reason.startswith("crowd")

    with open(txt_path, "w") as f:
        f.write(f"frame_idx: {i}\n")
        f.write(f"rel_t: {rel_t:.3f}\n")
        f.write(f"frame_no: {frame_no}\n")
        f.write(f"binary_label: {'DELIVERY' if is_d else 'NOT_DELIVERY'}\n")
        f.write(f"classify_reason: {reason}\n")
        f.write(f"signals:\n")
        f.write(f"  has_action: {yn(a)}\n")
        f.write(f"  has_score: {yn(sc)}\n")
        f.write(f"  is_replay_hard: {yn(is_replay_hard)}\n")
        f.write(f"  is_crowd_dominant: {yn(is_crowd_dominant)}\n")
        if error:
            f.write(f"error: {error}\n")
        f.write("---\n")
        f.write(text)
        f.write("\n")


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


async def worker(client: AsyncGroq, queue: asyncio.Queue, total: int) -> None:
    while True:
        item = await queue.get()
        if item is None:
            queue.task_done()
            return
        i, rel_t, frame_no, jpg_path, txt_path = item
        try:
            with open(jpg_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            text, err = await call_scout(client, b64)
            write_pair_text(txt_path, i, rel_t, frame_no, text, err)
            async with progress_lock:
                progress["done"] += 1
                if err:
                    progress["errors"] += 1
                d = progress["done"]
                if d % 100 == 0 or d == total:
                    print(f"  [{d}/{total}] errors={progress['errors']} rate_limited={progress['rate_limited']}",
                          flush=True)
        finally:
            queue.task_done()


async def producer(queue: asyncio.Queue, video: str, n_frames: int, stride: int,
                   min_interval: float, skip_existing: bool) -> int:
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise SystemExit(f"cannot open {video}")
    extracted = 0
    last_dispatch = 0.0
    for i in range(n_frames):
        ok, frame = cap.read()
        if not ok:
            break
        if i % stride != 0:
            continue
        rel_t = i / FPS
        stem = f"f_{i:05d}_t={rel_t:06.2f}"
        jpg_path = OUT / f"{stem}.jpg"
        txt_path = OUT / f"{stem}.txt"
        if skip_existing and jpg_path.exists() and txt_path.exists():
            extracted += 1
            continue
        if not jpg_path.exists():
            cv2.imwrite(str(jpg_path), frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if min_interval > 0:
            now = time.time()
            wait = (last_dispatch + min_interval) - now
            if wait > 0:
                await asyncio.sleep(wait)
            last_dispatch = time.time()
        await queue.put((i, rel_t, i, jpg_path, txt_path))
        extracted += 1
        if extracted % 50 == 0:
            print(f"  dispatched {extracted} (frame_idx {i}/{n_frames})", flush=True)
    cap.release()
    return extracted


async def main_async(args) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Video:      {args.video}")
    print(f"Out dir:    {OUT}")
    print(f"Frames:     {args.n_frames}")
    print(f"Concurrency:{args.concurrency}")
    print(f"Model:      {MODEL}")

    expected = (args.n_frames + args.stride - 1) // args.stride
    queue: asyncio.Queue = asyncio.Queue(maxsize=max(1, args.concurrency) * 4)
    client = AsyncGroq(api_key=GROQ_KEY, timeout=TIMEOUT_S + 5)

    workers = [
        asyncio.create_task(worker(client, queue, expected))
        for _ in range(args.concurrency)
    ]

    t0 = time.time()
    print(f"Stride: {args.stride} (expected ~{expected} Scout calls)", flush=True)
    print(f"Dispatch min-interval: {args.min_interval:.2f}s", flush=True)
    print("Extracting frames + dispatching Scout calls...", flush=True)
    extracted = await producer(queue, args.video, args.n_frames, args.stride,
                                args.min_interval, args.skip_existing)
    print(f"Extraction done ({extracted} frames). Waiting on Scout calls...", flush=True)

    for _ in workers:
        await queue.put(None)
    await asyncio.gather(*workers)

    dt = time.time() - t0
    print(f"All Scout calls finished in {dt:.1f}s. errors={progress['errors']} rate_limited={progress['rate_limited']}")

    return 0


def read_pair_text(txt_path: Path) -> str:
    raw = txt_path.read_text()
    if "---\n" in raw:
        return raw.split("---\n", 1)[1].strip()
    return raw.strip()


def run_detection(n_frames: int, stride: int) -> int:
    print()
    print("=== Loading per-frame Scout outputs ===")
    frames: list[Frame] = []
    missing = 0
    for i in range(0, n_frames, stride):
        rel_t = i / FPS
        stem = f"f_{i:05d}_t={rel_t:06.2f}"
        txt_path = OUT / f"{stem}.txt"
        if not txt_path.exists():
            missing += 1
            continue
        text = read_pair_text(txt_path)
        f = Frame(ts=rel_t, rel_t=rel_t, text=text)
        annotate(f)
        frames.append(f)
    print(f"Loaded {len(frames)} frames (missing {missing})")

    def yn(b: bool) -> str:
        return "Y" if b else "N"

    def parse_old_label(t: float) -> str:
        i = int(round(t * FPS))
        rel_t = i / FPS
        stem = f"f_{i:05d}_t={rel_t:06.2f}"
        path = OUT / f"{stem}.txt"
        if not path.exists():
            return "?"
        for line in path.read_text().splitlines():
            if line.startswith("binary_label:"):
                return line.split(":", 1)[1].strip()
        return "?"

    def dump_frames(times: list[float], title: str) -> None:
        print()
        print(f"=== Verify: {title} ===")
        by_t = {round(f.rel_t): f for f in frames}
        for t in times:
            f = by_t.get(int(t))
            if f is None:
                print(f"  t={t:5.1f}s  (no frame)")
                continue
            new_tag = "DELIVERY" if f.is_delivery else "NOT_DELIVERY"
            old_tag = parse_old_label(t)
            multi_s = f"{yn(f.has_multi_actor)}({f.multi_actor_source})"
            print(f"  t={f.rel_t:5.1f}s  was={old_tag:13s}  now={new_tag:13s}  "
                  f"path={f.path}  "
                  f"verb={yn(f.has_action_verb)} "
                  f"strong={yn(f.has_strong_score)} "
                  f"weak={yn(f.has_weak_info)} "
                  f"multi={multi_s} "
                  f"wide={yn(f.has_wide_field)}")
            print(f"            roles={list(f.roles_seen)} "
                  f"plural={list(f.plural_matches)} "
                  f"x_players='{f.x_players_match}' "
                  f"the_player_count={f.the_player_count}")
            print(f"            reason={f.reason}")

    dump_frames([6, 10, 25, 30, 55, 60, 85], "PRE-MATCH (expect NOT_DELIVERY)")
    dump_frames([100, 104, 109, 110], "LIVE 1st delivery (expect DELIVERY)")
    dump_frames([122, 124, 125, 126, 127, 128], "LIVE 2nd delivery (expect DELIVERY)")

    blocks = detect_blocks(frames)

    print()
    print("=== DELIVERY zones detected (every-frame Scout, first 5 min) ===")
    print()
    for n, (a, b) in enumerate(blocks, 1):
        ta = frames[a].rel_t
        tb = frames[b].rel_t
        m = sum(1 for f in frames[a:b + 1] if f.smoothed)
        print(f"Block {n}: t={ta:.1f}s -> t={tb:.1f}s ({tb - ta:.1f}s, {m} frames)")
    print()
    print(f"Total blocks: {len(blocks)}")

    raw_d = sum(1 for f in frames if f.is_delivery)
    sm_d = sum(1 for f in frames if f.smoothed)
    print(f"Raw DELIVERY frames: {raw_d}/{len(frames)} ({100*raw_d/max(1,len(frames)):.1f}%)")
    print(f"Smoothed DELIVERY frames: {sm_d}/{len(frames)} ({100*sm_d/max(1,len(frames)):.1f}%)")

    print()
    print("=== Reference (user-provided truth) ===")
    print("First delivery: 1:40 to 1:55 (t=100s -> t=115s)")
    overlap = [(n, frames[a].rel_t, frames[b].rel_t)
               for n, (a, b) in enumerate(blocks, 1)
               if frames[a].rel_t <= 115 and frames[b].rel_t >= 100]
    if overlap:
        print(f"Truth overlap: {len(overlap)} block(s) -> "
              + ", ".join(f"#{n}({a:.1f}-{b:.1f})" for n, a, b in overlap))
    else:
        print("Truth overlap: NONE")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=str(VIDEO))
    ap.add_argument("--n-frames", type=int, default=N_FRAMES)
    ap.add_argument("--concurrency", type=int, default=CONCURRENCY)
    ap.add_argument("--stride", type=int, default=FRAME_STRIDE,
                    help="frame stride (25 = 1 fps to match production)")
    ap.add_argument("--min-interval", type=float, default=MIN_DISPATCH_INTERVAL_S,
                    help="min seconds between Scout dispatches (production = 1.0)")
    ap.add_argument("--skip-existing", action="store_true",
                    help="skip frames whose jpg+txt already exist (resume)")
    ap.add_argument("--detect-only", action="store_true",
                    help="skip Scout calls, just run detection on existing txts")
    args = ap.parse_args()

    if args.detect_only:
        return run_detection(args.n_frames, args.stride)
    rc = asyncio.run(main_async(args))
    if rc == 0:
        rc = run_detection(args.n_frames, args.stride)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
