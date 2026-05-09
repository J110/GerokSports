"""BMF Phase E1: dual-band strip_diff comparison.

For each saved delivery clip under
``files/logs/deliveries/20260504_192431/d001..d030``, decode at native
fps, subsample to 5 fps wall-clock cadence, and compute per-pair:

* ``flow_magnitude``  — whole-frame Farneback flow (shared signal).
* ``strip_diff_v1``   — bottom 12% ROI (legacy: y in [0.88h, h]).
* ``strip_diff_v3``   — Batch T band   (Y in [0.78h, 0.88h]).

Each pair is labeled by distance from the clip's ``event_ts``:

* ``real_delivery``   — |Δt| <= 1.5 s
* ``post_event``      — 1.5 < |Δt| <= 4.0 s
* ``noise``           — |Δt| > 4.0 s

Writes per-pair rows to ``dual_band_signals.csv`` and prints an
aggregate discrimination summary (median/p25/p75/p95 per label per
ROI) plus the v3/v1 improvement_factor on the
``median(real_delivery)/median(noise)`` ratio.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Iterator, Tuple

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from files.eyes.broadcast_mode_filter import (  # noqa: E402
    MAX_DIM_DEFAULT,
    _FARNEBACK_KWARGS,
    _downsample_if_larger,
)

DELIVERIES_DIR = REPO_ROOT / "files/logs/deliveries/20260504_192431"
OUT_CSV = (
    REPO_ROOT
    / "files/scripts/broadcast_mode_tuning/dual_band_signals.csv"
)

SUBSAMPLE_FPS = 5.0
REAL_WINDOW_S = 1.5
POST_WINDOW_S = 4.0

V1_TOP_FRAC = 0.88
V1_BOT_FRAC = 1.00
V3_TOP_FRAC = 0.78
V3_BOT_FRAC = 0.88


def _label(ts_offset: float, event_ts_local: float) -> str:
    delta = abs(ts_offset - event_ts_local)
    if delta <= REAL_WINDOW_S:
        return "real_delivery"
    if delta <= POST_WINDOW_S:
        return "post_event"
    return "noise"


def _strip_mean(diff: np.ndarray, top_frac: float, bot_frac: float) -> float:
    h = diff.shape[0]
    y0 = int(h * top_frac)
    y1 = int(h * bot_frac)
    if y1 <= y0:
        y1 = y0 + 1
    return float(diff[y0:y1, :].mean())


def _iter_subsampled_pairs(
    mp4_path: Path, target_fps: float
) -> Iterator[Tuple[int, float, np.ndarray, np.ndarray]]:
    cap = cv2.VideoCapture(str(mp4_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {mp4_path}")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    if src_fps <= 0:
        cap.release()
        raise RuntimeError(f"invalid fps for {mp4_path}: {src_fps}")
    step = max(1, int(round(src_fps / target_fps)))
    prev_small = None
    prev_idx = -1
    frame_idx = -1
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame_idx += 1
            if frame_idx % step != 0:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            small = _downsample_if_larger(gray, MAX_DIM_DEFAULT)
            if prev_small is not None:
                ts_offset = frame_idx / src_fps
                yield frame_idx, ts_offset, prev_small, small
                _ = prev_idx  # unused
            prev_small = small
            prev_idx = frame_idx
    finally:
        cap.release()


def _process_clip(clip_dir: Path, writer: csv.writer) -> None:
    mp4_path = clip_dir / "delivery_window.mp4"
    debug_path = clip_dir / "window_debug.json"
    if not mp4_path.exists() or not debug_path.exists():
        print(f"skip {clip_dir.name}: missing inputs", file=sys.stderr)
        return
    debug = json.loads(debug_path.read_text())
    event_ts = float(debug["event_ts"])
    clip_start = float(debug["clip_start_ts"])
    event_ts_local = event_ts - clip_start

    for frame_idx, ts_offset, prev_small, cur_small in (
        _iter_subsampled_pairs(mp4_path, SUBSAMPLE_FPS)
    ):
        flow = cv2.calcOpticalFlowFarneback(
            prev_small, cur_small, None, **_FARNEBACK_KWARGS
        )
        flow_mag = float(
            np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2).mean()
        )
        diff = cv2.absdiff(prev_small, cur_small)
        sd_v1 = _strip_mean(diff, V1_TOP_FRAC, V1_BOT_FRAC)
        sd_v3 = _strip_mean(diff, V3_TOP_FRAC, V3_BOT_FRAC)
        label = _label(ts_offset, event_ts_local)
        writer.writerow([
            clip_dir.name,
            frame_idx,
            f"{ts_offset:.6f}",
            label,
            f"{flow_mag:.6f}",
            f"{sd_v1:.6f}",
            f"{sd_v3:.6f}",
        ])


def _aggregate(csv_path: Path) -> None:
    rows = []
    with csv_path.open() as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            rows.append({
                "label": r["label"],
                "v1": float(r["strip_diff_v1"]),
                "v3": float(r["strip_diff_v3"]),
            })

    labels = ["real_delivery", "post_event", "noise"]
    stats: dict[str, dict[str, dict[str, float]]] = {}
    counts: dict[str, int] = {}
    for lab in labels:
        sub = [r for r in rows if r["label"] == lab]
        counts[lab] = len(sub)
        stats[lab] = {}
        for sig in ("v1", "v3"):
            vals = np.array([r[sig] for r in sub], dtype=float)
            if vals.size == 0:
                stats[lab][sig] = {
                    "median": float("nan"), "p25": float("nan"),
                    "p75": float("nan"), "p95": float("nan"),
                }
            else:
                stats[lab][sig] = {
                    "median": float(np.median(vals)),
                    "p25": float(np.percentile(vals, 25)),
                    "p75": float(np.percentile(vals, 75)),
                    "p95": float(np.percentile(vals, 95)),
                }

    print()
    print("| label | rows | v1 median | v1 p95 | v3 median | v3 p95 |")
    print("|---|---|---|---|---|---|")
    for lab in labels:
        s = stats[lab]
        print(
            f"| {lab} | {counts[lab]} | "
            f"{s['v1']['median']:.4f} | {s['v1']['p95']:.4f} | "
            f"{s['v3']['median']:.4f} | {s['v3']['p95']:.4f} |"
        )

    def _ratio(sig: str) -> float:
        real_med = stats["real_delivery"][sig]["median"]
        noise_med = stats["noise"][sig]["median"]
        if not noise_med:
            return float("nan")
        return real_med / noise_med

    v1_ratio = _ratio("v1")
    v3_ratio = _ratio("v3")
    improvement = (
        v3_ratio / v1_ratio if v1_ratio else float("nan")
    )

    print()
    print(f"v1 ratio: {v1_ratio:.4f}")
    print(f"v3 ratio: {v3_ratio:.4f}")
    print(f"improvement_factor: {improvement:.4f}")

    print()
    if improvement >= 2.0:
        print(
            "Recommendation: Phase E2 sweep + ship "
            f"(improvement {improvement:.2f}x >= 2.0x)."
        )
    elif improvement >= 1.5:
        print(
            "Recommendation: Marginal "
            f"({improvement:.2f}x in [1.5, 2.0)); "
            "capture fresh clips before deciding."
        )
    else:
        print(
            "Recommendation: ROI relocation insufficient "
            f"({improvement:.2f}x < 1.5x); "
            "deeper preprocessing investigation needed."
        )


def main() -> None:
    clip_dirs = sorted(
        d for d in DELIVERIES_DIR.iterdir() if d.is_dir() and d.name.startswith("d")
    )
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "clip_id", "frame_idx", "ts_offset", "label",
            "flow_magnitude", "strip_diff_v1", "strip_diff_v3",
        ])
        for clip_dir in clip_dirs:
            print(f"processing {clip_dir.name}", file=sys.stderr)
            _process_clip(clip_dir, writer)

    _aggregate(OUT_CSV)


if __name__ == "__main__":
    main()
