"""Validate shadow-mode phash dedup instrumentation in Vision.describe().

Loads ~15 frames from files/scripts/frame_dedup/samples/, mocks the
AsyncGroq client to avoid hitting the real API, sets
SCOUT_DEDUP_SHADOW=1, runs Vision.describe() on each frame, and verifies:
  - SCOUT-DEDUP-SHADOW trace tag fires on every call
  - would_skip=True fires at least once
  - Zero exceptions raised

Usage:
    files/.venv/bin/python files/scripts/scout_crop_eval/validate_shadow.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "files"))

os.environ.setdefault("GROQ_API_KEY", "stub-for-validation")
os.environ["SCOUT_DEDUP_SHADOW"] = "1"

import cv2  # noqa: E402

from eyes.vision import Vision  # noqa: E402
from trace_emitter import get_recorder  # noqa: E402


SAMPLES_DIR = REPO_ROOT / "files" / "scripts" / "frame_dedup" / "samples"

STUB_RAW = (
    '{"camera_view":"graphic","frame_phase":"between_play",'
    '"has_strip":true,"has_overlay_stats":false,"drs_review":false}\n'
    "TAG: SCOREBOARD\n"
    "STRIP: MI 87/3 (12.4) | Suryakumar 42* | Tilak 8\n"
    "ACTION: between deliveries\n"
)


class _StubMessage:
    def __init__(self, content):
        self.content = content


class _StubChoice:
    def __init__(self, content):
        self.message = _StubMessage(content)
        self.finish_reason = "stop"


class _StubResponse:
    def __init__(self, content):
        self.choices = [_StubChoice(content)]


async def _run():
    base = sorted(SAMPLES_DIR.glob("frame_*.jpg"))[:14]
    if not base:
        print(f"[FAIL] no sample frames at {SAMPLES_DIR}")
        return 1
    # Re-feed the first frame at the end to guarantee a near-duplicate
    # hit (dist=0 against the first cache entry — still within TTL).
    frames = list(base) + [base[0]]
    print(f"[INFO] loaded {len(frames)} frames from {SAMPLES_DIR}")

    recorder = get_recorder()
    recorder.begin_frame(0)

    vision = Vision()

    stub_create = AsyncMock(return_value=_StubResponse(STUB_RAW))
    vision._groq.chat.completions.create = stub_create  # type: ignore[attr-defined]

    fired = 0
    would_skip_count = 0
    exceptions = 0
    best_dists = []

    for i, fp in enumerate(frames):
        recorder.begin_frame(i)
        frame = cv2.imread(str(fp))
        if frame is None:
            print(f"[WARN] could not load {fp}")
            continue
        try:
            await vision.describe(frame)
        except Exception as exc:
            exceptions += 1
            print(f"[FAIL] describe() raised: {exc!r}")
            continue

        bucket = recorder.drain()
        shadow_entries = [
            e for e in bucket if e.get("tag") == "SCOUT-DEDUP-SHADOW"
            and not e.get("_auto")
        ]
        if shadow_entries:
            fired += 1
            entry = shadow_entries[0]
            if entry.get("would_skip"):
                would_skip_count += 1
            best_dists.append(entry.get("best_dist"))
            print(
                f"[OK] frame={i} would_skip={entry.get('would_skip')} "
                f"best_dist={entry.get('best_dist')} "
                f"score_match={entry.get('score_match')}"
            )
        else:
            print(f"[FAIL] frame={i} no SCOUT-DEDUP-SHADOW tag in bucket")

        await asyncio.sleep(0.05)

    print()
    print(f"[SUMMARY] frames={len(frames)} fired={fired} "
          f"would_skip={would_skip_count} exceptions={exceptions}")
    print(f"[SUMMARY] best_dists={best_dists}")

    ok = (
        fired == len(frames)
        and would_skip_count >= 1
        and exceptions == 0
    )
    if ok:
        print("[PASS] validation succeeded")
        return 0
    print("[FAIL] validation criteria not met")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
