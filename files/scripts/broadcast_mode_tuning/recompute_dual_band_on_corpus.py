"""BMF Phase E2: validate v3 ROI band on the 105-clip labeled corpus.

For every row in ``files/scripts/motion_baseline/clip_aggregates.csv``,
re-decode the source ``delivery_window.mp4`` from
``files/logs/deliveries/{session}/{clip_id}/`` and compute three
per-frame-pair signals at a 15 fps subsample cadence:

* ``flow_magnitude``  — whole-frame Farneback optical flow magnitude.
* ``strip_diff_v1``   — bottom 12% ROI (y in [0.88h, h]).
* ``strip_diff_v3``   — Batch T band   (y in [0.78h, 0.88h]).

Per-pair rows are written to ``corpus_dual_band_signals.csv`` tagged
with the manual_label from clip_aggregates.csv. A summary of medians
and p95 per label is printed along with the ad/real_delivery
discrimination ratio for v1 vs v3.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

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

DELIVERIES_ROOT = REPO_ROOT / "files/logs/deliveries"
LABELS_CSV = REPO_ROOT / "files/scripts/motion_baseline/clip_aggregates.csv"
OUT_CSV = (
    REPO_ROOT
    / "files/scripts/broadcast_mode_tuning/corpus_dual_band_signals.csv"
)

SUBSAMPLE_FPS = 15.0

V1_TOP_FRAC = 0.88
V1_BOT_FRAC = 1.00
V3_TOP_FRAC = 0.78
V3_BOT_FRAC = 0.88


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
            prev_small = small
    finally:
        cap.release()


def _load_labels() -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with LABELS_CSV.open() as fh:
        for r in csv.DictReader(fh):
            rows.append(
                {
                    "session": r["session"],
                    "clip_id": r["clip_id"],
                    "label": r["manual_label"],
                }
            )
    return rows


def _process_clip(
    session: str, clip_id: str, label: str, writer: csv.writer
) -> int:
    mp4_path = DELIVERIES_ROOT / session / clip_id / "delivery_window.mp4"
    if not mp4_path.exists():
        print(f"skip {session}/{clip_id}: missing mp4", file=sys.stderr)
        return 0
    try:
        pairs = list(_iter_subsampled_pairs(mp4_path, SUBSAMPLE_FPS))
    except RuntimeError as e:
        print(f"skip {session}/{clip_id}: {e}", file=sys.stderr)
        return 0
    n = 0
    for frame_idx, ts_offset, prev_small, cur_small in pairs:
        flow = cv2.calcOpticalFlowFarneback(
            prev_small, cur_small, None, **_FARNEBACK_KWARGS
        )
        flow_mag = float(
            np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2).mean()
        )
        diff = cv2.absdiff(prev_small, cur_small)
        sd_v1 = _strip_mean(diff, V1_TOP_FRAC, V1_BOT_FRAC)
        sd_v3 = _strip_mean(diff, V3_TOP_FRAC, V3_BOT_FRAC)
        writer.writerow(
            [
                f"{session}__{clip_id}",
                label,
                f"{ts_offset:.6f}",
                f"{flow_mag:.6f}",
                f"{sd_v1:.6f}",
                f"{sd_v3:.6f}",
            ]
        )
        n += 1
    return n


def _aggregate(csv_path: Path) -> None:
    by_label: Dict[str, Dict[str, List[float]]] = {}
    with csv_path.open() as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            lab = r["label"]
            slot = by_label.setdefault(
                lab, {"flow": [], "v1": [], "v3": []}
            )
            slot["flow"].append(float(r["flow_magnitude"]))
            slot["v1"].append(float(r["strip_diff_v1"]))
            slot["v3"].append(float(r["strip_diff_v3"]))

    labels = ["real_delivery", "ad", "replay", "noise"]
    labels = [lab for lab in labels if lab in by_label]

    def _stat(vals: List[float], pct: float) -> float:
        if not vals:
            return float("nan")
        return float(np.percentile(vals, pct))

    print()
    print(
        "| label | n | flow med | flow p95 | "
        "strip_v1 med | strip_v1 p95 | strip_v3 med | strip_v3 p95 |"
    )
    print("|---|---|---|---|---|---|---|---|")
    medians: Dict[str, Dict[str, float]] = {}
    for lab in labels:
        slot = by_label[lab]
        n = len(slot["v1"])
        flow_med = _stat(slot["flow"], 50)
        flow_p95 = _stat(slot["flow"], 95)
        v1_med = _stat(slot["v1"], 50)
        v1_p95 = _stat(slot["v1"], 95)
        v3_med = _stat(slot["v3"], 50)
        v3_p95 = _stat(slot["v3"], 95)
        medians[lab] = {"v1": v1_med, "v3": v3_med}
        print(
            f"| {lab} | {n} | {flow_med:.4f} | {flow_p95:.4f} | "
            f"{v1_med:.4f} | {v1_p95:.4f} | "
            f"{v3_med:.4f} | {v3_p95:.4f} |"
        )

    if "real_delivery" not in medians or "ad" not in medians:
        print()
        print("Cannot compute discrimination: missing real_delivery or ad.")
        return

    rd_v1 = medians["real_delivery"]["v1"]
    rd_v3 = medians["real_delivery"]["v3"]
    ad_v1 = medians["ad"]["v1"]
    ad_v3 = medians["ad"]["v3"]
    v1_ratio = ad_v1 / rd_v1 if rd_v1 else float("nan")
    v3_ratio = ad_v3 / rd_v3 if rd_v3 else float("nan")
    improvement = v3_ratio / v1_ratio if v1_ratio else float("nan")

    print()
    print("Discrimination ratios (ad / real_delivery, higher = better):")
    print(f"  v1: {v1_ratio:.4f}")
    print(f"  v3: {v3_ratio:.4f}")
    print(f"  improvement_factor (v3 / v1): {improvement:.4f}")

    print()
    if improvement >= 1.5:
        print(
            f"Decision: v3 ROI improves discrimination ({improvement:.2f}x). "
            "Recommend Phase E3 sweep + ship."
        )
    elif improvement >= 0.9:
        print(
            f"Decision: Neutral ({improvement:.2f}x). "
            "v1 already works on labeled data; yesterday's failure was "
            "about labels, not signal. Path forward: clean capture-card "
            "labels via manual annotation OR fresh Stage-2-fired session."
        )
    else:
        print(
            f"Decision: v1 better ({improvement:.2f}x). Don't ship v3."
        )


def main() -> None:
    rows = _load_labels()
    print(f"Loaded {len(rows)} labeled clips", file=sys.stderr)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "clip_id",
                "label",
                "ts_s",
                "flow_magnitude",
                "strip_diff_v1",
                "strip_diff_v3",
            ]
        )
        for i, r in enumerate(rows, 1):
            n = _process_clip(r["session"], r["clip_id"], r["label"], writer)
            print(
                f"[{i}/{len(rows)}] {r['session']}__{r['clip_id']} "
                f"label={r['label']} pairs={n}",
                file=sys.stderr,
            )

    _aggregate(OUT_CSV)


if __name__ == "__main__":
    main()
