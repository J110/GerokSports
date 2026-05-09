#!/usr/bin/env python3
"""Phase B/C — capture-card motion signals (per memo §13).

For each ``files/logs/deliveries/<session>/d*/delivery_window.mp4`` +
``window_debug.json`` pair, decode the clip, subsample to ~5 fps to
mimic ``SHADOW_INGEST_FPS=5.0`` production cadence, then compute the
same per-frame-pair signals as ``motion_baseline/compute_motion_
signals.py`` (mean optical flow magnitude, strip_diff over the bottom
12 % of the downsampled grayscale pair).

Outputs:
* ``files/logs/bmf_capture_card/<session>__d<NNN>.jsonl`` — one row
  per frame-pair with fields {frame_idx, ts_s, flow_magnitude,
  strip_diff, label} where label ∈ {real_delivery, replay, noise}
  via |ts_s − event_ts_local| ≤ 1.5 / ≤ 4.0 / >4.0.
* ``files/scripts/broadcast_mode_tuning/capture_card_aggregates.csv``
  — per-clip aggregates matching the schema of
  ``motion_baseline/clip_aggregates.csv``.

Per memo §13 each clip is event-anchored, so the per-clip
``manual_label`` is fixed to ``real_delivery``.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np

ROOT = Path("/Users/anmolmohan/Projects/SportsComm")
DELIVERIES = ROOT / "files/logs/deliveries"
DEFAULT_SESSION = "20260503_200806"
OUT_RAW = ROOT / "files/logs/bmf_capture_card"
AGG_CSV = ROOT / "files/scripts/broadcast_mode_tuning/capture_card_aggregates.csv"

MAX_DIM = (640, 360)
STRIP_FRAC = 0.12
TARGET_FPS = 5.0


def label_for(rel_ts: float) -> str:
    a = abs(rel_ts)
    if a <= 1.5:
        return "real_delivery"
    if a <= 4.0:
        return "replay"
    return "noise"


def compute_clip_signals(
    mp4: Path,
    event_ts_local: float,
    target_fps: float,
) -> List[Dict]:
    cap = cv2.VideoCapture(str(mp4))
    if not cap.isOpened():
        return []
    native_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(native_fps / target_fps)))
    prev_gray = None
    rows: List[Dict] = []
    out_idx = 0
    src_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if src_idx % step != 0:
            src_idx += 1
            continue
        h, w = frame.shape[:2]
        if w > MAX_DIM[0] or h > MAX_DIM[1]:
            scale = min(MAX_DIM[0] / w, MAX_DIM[1] / h)
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if prev_gray is not None:
            flow = cv2.calcOpticalFlowFarneback(
                prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0
            )
            mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
            flow_mag = float(mag.mean())
            diff = cv2.absdiff(prev_gray, gray)
            frame_diff = float(diff.mean())
            sh = gray.shape[0]
            strip_y0 = int(sh * (1.0 - STRIP_FRAC))
            strip_diff = float(
                cv2.absdiff(prev_gray[strip_y0:, :], gray[strip_y0:, :]).mean()
            )
            ts_s = src_idx / native_fps
            rows.append(
                {
                    "frame_idx": out_idx,
                    "ts_s": ts_s,
                    "flow_magnitude": flow_mag,
                    "frame_diff": frame_diff,
                    "strip_diff": strip_diff,
                    "label": label_for(ts_s - event_ts_local),
                }
            )
            out_idx += 1
        prev_gray = gray
        src_idx += 1
    cap.release()
    return rows


def peak_count(arr: np.ndarray) -> int:
    if arr.size < 3:
        return 0
    thr = float(np.median(arr) + np.std(arr))
    return int(np.sum(arr > thr))


def aggregate(values: np.ndarray) -> Dict[str, float]:
    if values.size == 0:
        return {k: 0.0 for k in ("mean", "std", "p50", "p95", "peak_count")}
    return {
        "mean": float(np.mean(values)),
        "std": float(np.std(values)),
        "p50": float(np.percentile(values, 50)),
        "p95": float(np.percentile(values, 95)),
        "peak_count": peak_count(values),
    }


def aggregate_strip(values: np.ndarray) -> Dict[str, float]:
    if values.size == 0:
        return {"mean": 0.0, "std": 0.0, "p95": 0.0}
    return {
        "mean": float(np.mean(values)),
        "std": float(np.std(values)),
        "p95": float(np.percentile(values, 95)),
    }


def process_session(session: str) -> List[Dict]:
    base = DELIVERIES / session
    clips = sorted(p for p in base.iterdir() if p.is_dir() and p.name.startswith("d"))
    OUT_RAW.mkdir(parents=True, exist_ok=True)
    agg_rows: List[Dict] = []
    for i, clip_dir in enumerate(clips, 1):
        clip_id = clip_dir.name
        mp4 = clip_dir / "delivery_window.mp4"
        wd = clip_dir / "window_debug.json"
        if not mp4.exists() or not wd.exists():
            print(f"[{i}/{len(clips)}] {clip_id} missing", flush=True)
            continue
        meta = json.loads(wd.read_text())
        event_ts = float(meta["event_ts"])
        clip_start_ts = float(meta["clip_start_ts"])
        event_ts_local = event_ts - clip_start_ts
        rows = compute_clip_signals(mp4, event_ts_local, TARGET_FPS)
        if not rows:
            print(f"[{i}/{len(clips)}] {clip_id} no_frames", flush=True)
            continue
        out_jsonl = OUT_RAW / f"{session}__{clip_id}.jsonl"
        with out_jsonl.open("w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        flow = np.array([r["flow_magnitude"] for r in rows])
        diff = np.array([r["frame_diff"] for r in rows])
        strip = np.array([r["strip_diff"] for r in rows])
        fa, da, sa = aggregate(flow), aggregate(diff), aggregate_strip(strip)
        agg_rows.append({
            "session": session,
            "clip_id": clip_id,
            "manual_label": "real_delivery",
            "over": meta.get("over_number", ""),
            "event_type": meta.get("event_type", ""),
            "n_frames": len(rows),
            "flow_mean": fa["mean"],
            "flow_std": fa["std"],
            "flow_p50": fa["p50"],
            "flow_p95": fa["p95"],
            "flow_peak_count": fa["peak_count"],
            "diff_mean": da["mean"],
            "diff_std": da["std"],
            "diff_p50": da["p50"],
            "diff_p95": da["p95"],
            "diff_peak_count": da["peak_count"],
            "strip_mean": sa["mean"],
            "strip_std": sa["std"],
            "strip_p95": sa["p95"],
        })
        print(f"[{i}/{len(clips)}] {clip_id} ok n={len(rows)} flow_mean={fa['mean']:.3f} strip_mean={sa['mean']:.3f}", flush=True)
    cols = [
        "session", "clip_id", "manual_label", "over", "event_type", "n_frames",
        "flow_mean", "flow_std", "flow_p50", "flow_p95", "flow_peak_count",
        "diff_mean", "diff_std", "diff_p50", "diff_p95", "diff_peak_count",
        "strip_mean", "strip_std", "strip_p95",
    ]
    AGG_CSV.parent.mkdir(parents=True, exist_ok=True)
    with AGG_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in agg_rows:
            w.writerow(r)
    return agg_rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default=DEFAULT_SESSION)
    args = ap.parse_args()
    rows = process_session(args.session)
    print(f"\nWrote {len(rows)} rows → {AGG_CSV}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
