"""May-3 corpus detection validation.

For each clip in files/logs/deliveries/20260503_205835/d{001..008}/, run
both detection mechanisms over delivery_window.mp4:

  * Method 1 — BroadcastModeFilter Stage 1 (motion gating, v1 thresholds)
    at 15 fps subsample. Reports clip-relative spans where state==ACTIVE.
  * Method 2 — Scout VLM at 1 fps + Batch BB bridge rule. Reports spans
    of contiguous accepted (cam=bowlers_end + action-phase OR bridged
    between_play) tags.
  * Method 3 — score event_ts offset within the clip.
"""
from __future__ import annotations

import asyncio
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
FILES_DIR = REPO_ROOT / "files"
if str(FILES_DIR) not in sys.path:
    sys.path.insert(0, str(FILES_DIR))

from files.eyes.broadcast_mode_filter import BroadcastModeFilter  # noqa: E402
from eyes.vision import Vision  # noqa: E402

CORPUS_DIR = REPO_ROOT / "files/logs/deliveries/20260503_205835"
OUT_TXT = (
    REPO_ROOT
    / "files/scripts/broadcast_mode_tuning/may3_validation_results.txt"
)

BMF_FPS = 15.0
SCOUT_FPS = 1.0
ACTION_PHASES = frozenset({"release", "flight", "shot", "runup"})
TARGET_VIEW = "bowlers_end"
BRIDGE_GAP_S = 2.5


def iter_subsampled(mp4: Path, target_fps: float
                    ) -> Iterator[tuple[float, np.ndarray]]:
    cap = cv2.VideoCapture(str(mp4))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(src_fps / target_fps)))
    idx = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % step == 0:
                ts = idx / src_fps
                yield ts, frame
            idx += 1
    finally:
        cap.release()


def run_bmf(mp4: Path) -> list[tuple[float, float]]:
    opens: list[tuple[float, float]] = []
    open_ts: list[float] = []

    def on_open(ts: float) -> None:
        open_ts.append(ts)

    def on_close(ts: float) -> None:
        if open_ts:
            opens.append((open_ts.pop(), ts))

    bmf = BroadcastModeFilter(on_window_open=on_open, on_window_close=on_close)
    last_ts = 0.0
    for ts, frame in iter_subsampled(mp4, BMF_FPS):
        bmf.add_frame(ts, frame)
        last_ts = ts
    if open_ts:
        opens.append((open_ts.pop(), last_ts))
    return opens


async def run_scout(mp4: Path) -> list[tuple[float, str | None, str | None]]:
    vision = Vision()
    out: list[tuple[float, str | None, str | None]] = []
    sink = io.StringIO()
    with redirect_stdout(sink):
        for ts, frame in iter_subsampled(mp4, SCOUT_FPS):
            try:
                await vision.describe(frame)
            except Exception:
                out.append((ts, None, None))
                continue
            out.append((ts, vision.last_camera_view, vision.last_frame_phase))
    return out


def derive_bb_spans(tags: list[tuple[float, str | None, str | None]]
                    ) -> tuple[list[tuple[float, float, list[str]]],
                               list[tuple[float, str]]]:
    accepted: list[tuple[float, str]] = []
    action_ts = [t for t, v, p in tags
                 if v == TARGET_VIEW and p in ACTION_PHASES]

    def has_action_neighbor(at: float) -> bool:
        return any(abs(a - at) <= BRIDGE_GAP_S for a in action_ts)

    for ts, view, phase in tags:
        if view != TARGET_VIEW:
            continue
        if phase in ACTION_PHASES:
            accepted.append((ts, phase or ""))
        elif phase == "between_play" and has_action_neighbor(ts):
            accepted.append((ts, "between_play*"))

    spans: list[tuple[float, float, list[str]]] = []
    if not accepted:
        return spans, accepted

    cur_start = accepted[0][0]
    cur_anchors = [f"{accepted[0][1]}@{accepted[0][0]:.1f}"]
    cur_end = accepted[0][0]
    for ts, phase in accepted[1:]:
        if ts - cur_end <= BRIDGE_GAP_S:
            cur_end = ts
            cur_anchors.append(f"{phase}@{ts:.1f}")
        else:
            spans.append((cur_start, cur_end, cur_anchors))
            cur_start = ts
            cur_end = ts
            cur_anchors = [f"{phase}@{ts:.1f}"]
    spans.append((cur_start, cur_end, cur_anchors))
    return spans, accepted


def format_clip_block(name: str, mp4: Path, dur: float, event_offset: float,
                      bmf_opens: list[tuple[float, float]],
                      scout_tags: list[tuple[float, str | None, str | None]],
                      bb_spans: list[tuple[float, float, list[str]]]
                      ) -> str:
    lines = [
        "════════════════════",
        f"[CLIP {name}]",
        f"duration={dur:.2f}s",
        f"mp4: {mp4.relative_to(REPO_ROOT)}",
        f"event_ts: at {event_offset:.2f}s in clip",
        "BMF (motion-based):",
    ]
    if bmf_opens:
        for s, e in bmf_opens:
            lines.append(f"- opens at {s:.2f}-{e:.2f}s")
    else:
        lines.append("- no opens")
    lines.append("Scout/BB (semantic):")
    if bb_spans:
        for s, e, anchors in bb_spans:
            lines.append(
                f"- span at {s:.2f}-{e:.2f}s ({', '.join(anchors)})")
    else:
        lines.append("- no spans")
    lines.append("Scout raw tags (cam/phase per 1Hz frame):")
    for ts, view, phase in scout_tags:
        lines.append(f"  {ts:5.2f}s  cam={view}  phase={phase}")
    lines.append("════════════════════")
    return "\n".join(lines)


async def main() -> None:
    clip_dirs = sorted(p for p in CORPUS_DIR.iterdir() if p.is_dir())
    blocks: list[str] = []
    for cdir in clip_dirs:
        mp4 = cdir / "delivery_window.mp4"
        meta_path = cdir / "window_debug.json"
        if not mp4.exists() or not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        clip_start = meta["clip_start_ts"]
        clip_end = meta["clip_end_ts"]
        event_ts = meta["event_ts"]
        dur = clip_end - clip_start
        event_offset = event_ts - clip_start

        print(f"[{cdir.name}] running BMF...", flush=True)
        bmf_opens = run_bmf(mp4)
        print(f"[{cdir.name}] running Scout @1Hz...", flush=True)
        scout_tags = await run_scout(mp4)
        bb_spans, _ = derive_bb_spans(scout_tags)

        block = format_clip_block(
            cdir.name, mp4, dur, event_offset, bmf_opens, scout_tags, bb_spans)
        print(block, flush=True)
        blocks.append(block)

    OUT_TXT.write_text("\n".join(blocks) + "\n")
    print(f"\nSaved → {OUT_TXT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
