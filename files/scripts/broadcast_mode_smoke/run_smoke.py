#!/usr/bin/env python3
"""Integration smoke test for ``BroadcastModeFilter`` (Phase D).

Reads frames from a recorded ``delivery_window.mp4`` at its native
decode rate, pumps them through ``BroadcastModeFilter`` with the
production defaults, and reports:

* total ACTIVE vs INACTIVE time
* every state transition with timestamp
* per-frame compute wall-time mean / p95 / max (<50 ms budget)
* mean ACTIVE-window duration

Usage::

    cd files
    python3 scripts/broadcast_mode_smoke/run_smoke.py \\
        --clip 20260420_202239/d002

    # Multi-clip sweep (pure delivery, ad, replay):
    python3 scripts/broadcast_mode_smoke/run_smoke.py \\
        --clips 20260420_202239/d002,20260420_202239/d001,\\
20260421_195050/d043
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import List, Tuple

THIS = Path(__file__).resolve().parent
ROOT = THIS.parent.parent
sys.path.insert(0, str(ROOT))

import cv2

from eyes.broadcast_mode_filter import (
    STATE_ACTIVE,
    STATE_INACTIVE,
    BroadcastModeFilter,
)

DELIVERIES = ROOT / "logs" / "deliveries"


def percentile(xs: List[float], q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = min(len(s) - 1, max(0, int(round((len(s) - 1) * q))))
    return s[k]


def run_clip(clip_slug: str, **bmf_kwargs) -> dict:
    mp4 = DELIVERIES / clip_slug / "delivery_window.mp4"
    if not mp4.exists():
        raise FileNotFoundError(mp4)

    transitions: List[Tuple[float, str]] = []

    def on_open(ts: float) -> None:
        transitions.append((ts, STATE_ACTIVE))

    def on_close(ts: float) -> None:
        transitions.append((ts, STATE_INACTIVE))

    bmf = BroadcastModeFilter(on_open, on_close, **bmf_kwargs)

    cap = cv2.VideoCapture(str(mp4))
    if not cap.isOpened():
        raise RuntimeError(f"failed to open {mp4}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    per_frame_ms: List[float] = []
    idx = 0
    active_time = 0.0
    total_time = 0.0
    prev_ts = 0.0
    prev_state = bmf.current_state()
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            ts = idx / fps
            t0 = time.monotonic()
            bmf.add_frame(ts, frame)
            per_frame_ms.append((time.monotonic() - t0) * 1000.0)
            cur_state = bmf.current_state()
            dt = max(0.0, ts - prev_ts)
            if prev_state == STATE_ACTIVE:
                active_time += dt
            total_time += dt
            prev_state = cur_state
            prev_ts = ts
            idx += 1
    finally:
        cap.release()

    active_durations: List[float] = []
    open_ts: float | None = None
    for t, st in transitions:
        if st == STATE_ACTIVE:
            open_ts = t
        elif st == STATE_INACTIVE and open_ts is not None:
            active_durations.append(t - open_ts)
            open_ts = None
    # Tail-open window
    if open_ts is not None:
        active_durations.append(prev_ts - open_ts)

    return {
        "clip": clip_slug,
        "mp4": str(mp4),
        "fps": round(fps, 2),
        "frames": idx,
        "active_time_s": round(active_time, 2),
        "inactive_time_s": round(total_time - active_time, 2),
        "total_time_s": round(total_time, 2),
        "transitions": transitions,
        "mean_active_window_s": round(
            sum(active_durations) / len(active_durations), 2)
        if active_durations else 0.0,
        "per_frame_ms_mean": round(
            sum(per_frame_ms) / max(1, len(per_frame_ms)), 2),
        "per_frame_ms_p95": round(percentile(per_frame_ms, 0.95), 2),
        "per_frame_ms_max": round(max(per_frame_ms) if per_frame_ms
                                  else 0.0, 2),
        "final_state": bmf.current_state(),
    }


def print_report(r: dict) -> None:
    print(f"\n== {r['clip']} ==")
    print(f"  mp4:          {r['mp4']}")
    print(f"  fps:          {r['fps']}  frames: {r['frames']}  "
          f"duration: {r['total_time_s']} s")
    print(f"  active:       {r['active_time_s']} s  "
          f"({r['active_time_s'] / max(1e-9, r['total_time_s']):.0%})")
    print(f"  inactive:     {r['inactive_time_s']} s")
    print(f"  transitions:  {len(r['transitions'])}")
    for ts, st in r["transitions"]:
        print(f"    - ts={ts:6.2f}  → {st}")
    print(f"  mean active window: {r['mean_active_window_s']} s")
    print(f"  per-frame compute:  mean {r['per_frame_ms_mean']} ms  "
          f"p95 {r['per_frame_ms_p95']} ms  "
          f"max {r['per_frame_ms_max']} ms")
    budget_ok = r["per_frame_ms_p95"] < 50.0
    print(f"  30 fps budget:      "
          f"{'OK' if budget_ok else 'OVER'} "
          f"(p95 < 50 ms required)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", type=str, default=None,
                    help="single clip slug e.g. 20260420_202239/d002")
    ap.add_argument("--clips", type=str, default=None,
                    help="comma-separated list of clip slugs")
    # Defaults mirror the filter's constructor — pass ``None`` so
    # ``BroadcastModeFilter`` supplies its own production defaults
    # (avoids drift when the memo updates tuned thresholds).
    ap.add_argument("--window-s", type=float, default=None)
    ap.add_argument("--open-strip", type=float, default=None)
    ap.add_argument("--open-flow", type=int, default=None)
    ap.add_argument("--close-strip", type=float, default=None)
    ap.add_argument("--close-flow", type=int, default=None)
    ap.add_argument("--min-active-s", type=float, default=None)
    ap.add_argument("--min-inactive-s", type=float, default=None)
    args = ap.parse_args()

    if args.clip:
        clips = [args.clip]
    elif args.clips:
        clips = [s.strip() for s in args.clips.split(",") if s.strip()]
    else:
        # Default representative trio.
        clips = [
            "20260420_202239/d002",  # real_delivery
            "20260420_202239/d001",  # ad
            "20260421_195050/d043",  # replay
        ]

    _bmf_overrides = {
        "window_s": args.window_s,
        "open_strip_mean_max": args.open_strip,
        "open_flow_peak_min": args.open_flow,
        "close_strip_mean_max": args.close_strip,
        "close_flow_peak_min": args.close_flow,
        "min_active_s": args.min_active_s,
        "min_inactive_s": args.min_inactive_s,
    }
    bmf_kwargs = {k: v for k, v in _bmf_overrides.items() if v is not None}
    print(f"BroadcastModeFilter params: {bmf_kwargs}")

    reports: List[dict] = []
    for slug in clips:
        try:
            r = run_clip(slug, **bmf_kwargs)
        except FileNotFoundError as e:
            print(f"\n== {slug} ==  skip: {e}")
            continue
        reports.append(r)
        print_report(r)

    if reports:
        print("\n== summary ==")
        for r in reports:
            print(
                f"  {r['clip']:<32} "
                f"active={r['active_time_s']:5.1f}s / "
                f"{r['total_time_s']:5.1f}s "
                f"({r['active_time_s'] / max(1e-9, r['total_time_s']):.0%})  "
                f"transitions={len(r['transitions'])}  "
                f"p95={r['per_frame_ms_p95']}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
