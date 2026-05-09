#!/usr/bin/env python3
"""Phase D — Capture-card LIVE telemetry threshold sweep.

Drives the existing ``tune_thresholds`` machinery against the Phase-A
per-ingest BMF telemetry captured during tonight's match
(``files/files/logs/bmf_debug/bmf_b0cdc9f9.jsonl``, 5 MB / ~30k rows /
30 score events at ~14 fps).

Phase 1 — Build labeled clip corpus:
  * For each contiguous ``score_event_within_5s=True`` group, emit one
    ``real_delivery`` clip = [score_commit_ts - 10s, score_commit_ts +
    5s]. The score-commit timestamp lands at the first True frame in
    each group; pre-extending captures the actual delivery (run-up
    through ball-into-keeper) which precedes the score commit.
  * Inter-delivery gaps ≥ 14 s are sliced into 14 s clips and labeled
    by motion signature: low p95 flow + low strip_mean → ``ad`` (the
    sweep's ad-suppression slot — these are stretches of graphic
    overlays / score-strip-static / pre-match cards that Stage 1 must
    not open on); higher motion → ``replay`` (between-delivery cricket
    motion that Stage 1 may or may not open on per §10).

Phase 2 — Sweep:
  Reuses ``tune_thresholds.build_grid(broad=True)`` (945 grid points)
  and ``tune_thresholds.replay``. Score = v1 (rd × (1 − ad)) — the
  Stage-1 mandate is ad-suppression per §10/§13.

Phase 3 — Comparison:
  Prints v1-production row, capture-card-morning best, capture-card-
  live best side-by-side and writes a Phase-D §13 fragment to
  ``capture_card_live_comparison.md``.

Outputs (under ``files/scripts/broadcast_mode_tuning/``):
  * ``capture_card_live_aggregates.csv`` — synthetic per-clip labels.
  * ``live_raw/<clip_id>.jsonl`` — per-clip BMF signal traces.
  * ``sweep_results_capture_card_live.csv``
  * ``best_params_capture_card_live.json``
  * ``capture_card_live_comparison.md``
"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

THIS = Path(__file__).resolve().parent
ROOT = THIS.parent.parent
sys.path.insert(0, str(ROOT))

import scripts.broadcast_mode_tuning.tune_thresholds as tt  # noqa: E402

INPUT_JSONL = ROOT / "files" / "logs" / "bmf_debug" / "bmf_b0cdc9f9.jsonl"
SESSION = "live_b0cdc9f9"

RAW_DIR = THIS / "live_raw"
AGG_CSV = THIS / "capture_card_live_aggregates.csv"
SWEEP_CSV = THIS / "sweep_results_capture_card_live.csv"
BEST_JSON = THIS / "best_params_capture_card_live.json"
COMPARE_MD = THIS / "capture_card_live_comparison.md"
MORNING_BEST = THIS / "best_params_capture_card.json"

V1_DEFAULTS = {
    "open_strip_mean_max": 0.35,
    "open_flow_peak_min": 10,
    "close_strip_mean_max": 0.475,
    "close_flow_peak_min": 5,
}

# Real-delivery window: pre-extend to capture the run-up + ball delivery
# (the score commit lands AFTER the delivery completes).
PRE_S = 10.0
POST_S = 5.0
# Gap clips: 14 s each, longer than window_s=10 s so the rolling window
# can saturate inside one clip.
GAP_CLIP_S = 14.0
GAP_MIN_S = 14.0
# ad/replay split for gap clips, picked from non-event chunk distribution
# (flow_p95 median 7.35, strip_mean p50 2.16). Below both = quiet
# graphics/strip-static (ad-like); above either = motion (replay).
AD_FLOW_P95_MAX = 5.0
AD_STRIP_MEAN_MAX = 2.0


def load_rows() -> List[dict]:
    out: List[dict] = []
    with INPUT_JSONL.open() as f:
        for line in f:
            out.append(json.loads(line))
    return out


def find_score_groups(rows: List[dict]) -> List[Tuple[int, int]]:
    spans: List[Tuple[int, int]] = []
    i, n = 0, len(rows)
    while i < n:
        if rows[i]["score_event_within_5s"]:
            j = i
            while j < n and rows[j]["score_event_within_5s"]:
                j += 1
            spans.append((i, j - 1))
            i = j
        else:
            i += 1
    return spans


def slice_by_ts(rows: List[dict], t0: float, t1: float) -> List[dict]:
    return [r for r in rows if t0 <= r["ts_s"] <= t1]


def label_gap(seg: List[dict]) -> str:
    flows = np.array([r["flow_magnitude"] for r in seg])
    strips = np.array([r["strip_diff"] for r in seg])
    flow_p95 = float(np.percentile(flows, 95))
    strip_mean = float(strips.mean())
    if flow_p95 <= AD_FLOW_P95_MAX and strip_mean <= AD_STRIP_MEAN_MAX:
        return "ad"
    return "replay"


def build_clips(rows: List[dict]) -> List[Tuple[str, str, List[dict]]]:
    """Return [(label, clip_id, segment), ...]."""
    groups = find_score_groups(rows)
    clips: List[Tuple[str, str, List[dict]]] = []

    real_windows: List[Tuple[float, float]] = []
    for gi, (s, _e) in enumerate(groups):
        score_ts = rows[s]["ts_s"]
        t0 = score_ts - PRE_S
        t1 = score_ts + POST_S
        seg = slice_by_ts(rows, t0, t1)
        if len(seg) >= 50:
            cid = f"{SESSION}__rd_{gi:03d}"
            clips.append(("real_delivery", cid, seg))
            real_windows.append((t0, t1))

    real_windows.sort()
    boundaries: List[Tuple[float, float]] = []
    if not real_windows:
        boundaries.append((rows[0]["ts_s"], rows[-1]["ts_s"]))
    else:
        if real_windows[0][0] - rows[0]["ts_s"] > GAP_MIN_S:
            boundaries.append((rows[0]["ts_s"], real_windows[0][0]))
        for k in range(1, len(real_windows)):
            t0 = real_windows[k - 1][1]
            t1 = real_windows[k][0]
            if t1 - t0 > GAP_MIN_S:
                boundaries.append((t0, t1))
        if rows[-1]["ts_s"] - real_windows[-1][1] > GAP_MIN_S:
            boundaries.append((real_windows[-1][1], rows[-1]["ts_s"]))

    gi = 0
    for (gt0, gt1) in boundaries:
        cs = gt0
        while cs + GAP_CLIP_S <= gt1:
            ce = cs + GAP_CLIP_S
            seg = slice_by_ts(rows, cs, ce)
            if len(seg) >= 50:
                lbl = label_gap(seg)
                cid = f"{SESSION}__gap_{gi:03d}_{lbl}"
                clips.append((lbl, cid, seg))
                gi += 1
            cs = ce
    return clips


def write_corpus(clips: List[Tuple[str, str, List[dict]]]) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for p in RAW_DIR.glob("*.jsonl"):
        p.unlink()
    with AGG_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["session", "clip_id", "manual_label"])
        for lbl, cid, seg in clips:
            session, clip_id = cid.split("__", 1)
            w.writerow([session, clip_id, lbl])
            with (RAW_DIR / f"{cid}.jsonl").open("w") as cf:
                for r in seg:
                    cf.write(json.dumps({
                        "ts_s": r["ts_s"],
                        "flow_magnitude": r["flow_magnitude"],
                        "strip_diff": r["strip_diff"],
                    }) + "\n")


def run_sweep(score_version: str = "v1") -> Tuple[List[Dict], Dict]:
    tt.RAW_DIR = RAW_DIR
    tt.AGG_CSV = AGG_CSV

    labels = tt.load_clip_labels()
    clip_signals: Dict[str, Tuple[str, List]] = {}
    for p in sorted(RAW_DIR.glob("*.jsonl")):
        key = p.stem
        lbl = labels.get(key)
        if not lbl:
            continue
        sigs = tt.load_clip_signals(p)
        if len(sigs) >= 3:
            clip_signals[key] = (lbl, sigs)

    by_label: Dict[str, List[str]] = {}
    for key, (lbl, _) in clip_signals.items():
        by_label.setdefault(lbl, []).append(key)
    print("  loaded clips: "
          + ", ".join(f"{k}={len(v)}" for k, v in sorted(by_label.items())),
          flush=True)

    grid = tt.build_grid(broad=True)
    print(f"  grid={len(grid)}  → {len(grid) * len(clip_signals)} replays",
          flush=True)
    fixed = dict(window_s=10.0, min_active_s=1.5, min_inactive_s=3.0)

    results: List[Dict] = []
    t0 = time.monotonic()
    for gi, g in enumerate(grid):
        params = dict(fixed)
        params.update(g)
        per_label_active: Dict[str, List[float]] = {}
        for key, (lbl, sigs) in clip_signals.items():
            active, total = tt.replay(sigs, **params)
            frac = active / total if total > 0 else 0.0
            per_label_active.setdefault(lbl, []).append(frac)
        summary = {lbl: (sum(v) / len(v))
                   for lbl, v in per_label_active.items()}
        rd = summary.get("real_delivery", 0.0)
        ad = summary.get("ad", 0.0)
        rp = summary.get("replay", 0.0)
        ns = summary.get("noise", 0.0)
        if score_version == "v1":
            score = rd * (1.0 - ad)
        else:
            score = rd * (1.0 - ad) * (1.0 - rp)
        results.append({
            **g,
            "window_s": fixed["window_s"],
            "min_active_s": fixed["min_active_s"],
            "min_inactive_s": fixed["min_inactive_s"],
            "real_delivery_active_frac": round(rd, 4),
            "ad_active_frac": round(ad, 4),
            "replay_active_frac": round(rp, 4),
            "noise_active_frac": round(ns, 4),
            "score": round(score, 4),
        })
        if (gi + 1) % 100 == 0 or gi + 1 == len(grid):
            dt = time.monotonic() - t0
            eta = dt / (gi + 1) * (len(grid) - gi - 1)
            print(f"    [{gi + 1}/{len(grid)}] elapsed {dt:.1f}s eta {eta:.1f}s",
                  flush=True)

    results.sort(key=lambda r: (
        -r["score"],
        -r["real_delivery_active_frac"],
        r["ad_active_frac"],
    ))
    with SWEEP_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        for r in results:
            w.writerow(r)
    best = dict(results[0])
    best["score_version"] = score_version
    BEST_JSON.write_text(json.dumps(best, indent=2) + "\n")
    return results, best


def find_v1_row(results: List[Dict]) -> Dict:
    for r in results:
        if all(abs(r[k] - V1_DEFAULTS[k]) < 1e-6 for k in V1_DEFAULTS):
            return r
    raise SystemExit("v1 defaults not found in sweep grid")


def write_comparison(results: List[Dict], best: Dict, clips_by_label: Dict[str, int]) -> str:
    v1_row = find_v1_row(results)
    morning_best = json.loads(MORNING_BEST.read_text())

    lines: List[str] = []
    lines.append("# Phase D — capture-card LIVE telemetry sweep (2026-05-04)\n")
    lines.append(f"_Source: `files/files/logs/bmf_debug/bmf_b0cdc9f9.jsonl` "
                 f"(5 MB, ~30k rows, 30 score-event groups, ~14 fps)._\n")
    lines.append("## §D.1 Synthetic clip corpus\n")
    lines.append("| label | clips |")
    lines.append("|---|---|")
    for k in sorted(clips_by_label):
        lines.append(f"| {k} | {clips_by_label[k]} |")
    lines.append("")
    lines.append(f"Real-delivery clips windowed [score_ts − {PRE_S}s, "
                 f"score_ts + {POST_S}s]; gap clips {GAP_CLIP_S}s; "
                 f"gap split: ad if flow_p95 ≤ {AD_FLOW_P95_MAX} AND "
                 f"strip_mean ≤ {AD_STRIP_MEAN_MAX}, else replay.\n")
    lines.append("## §D.2 Threshold comparison\n")
    lines.append("| Threshold | v1 production | morning capture-card | live capture-card |")
    lines.append("|---|---|---|---|")
    for k in ("open_strip_mean_max", "open_flow_peak_min",
              "close_strip_mean_max", "close_flow_peak_min"):
        lines.append(f"| {k} | {V1_DEFAULTS[k]} | "
                     f"{morning_best.get(k)} | {best.get(k)} |")
    lines.append("")
    lines.append("## §D.3 Active-fraction summary on LIVE corpus\n")
    lines.append("| params | rd | ad | replay | noise | score |")
    lines.append("|---|---|---|---|---|---|")
    lines.append(f"| v1 production "
                 f"| {v1_row['real_delivery_active_frac']:.3f} "
                 f"| {v1_row['ad_active_frac']:.3f} "
                 f"| {v1_row['replay_active_frac']:.3f} "
                 f"| {v1_row['noise_active_frac']:.3f} "
                 f"| {v1_row['score']:.3f} |")
    lines.append(f"| live optimum "
                 f"| {best['real_delivery_active_frac']:.3f} "
                 f"| {best['ad_active_frac']:.3f} "
                 f"| {best['replay_active_frac']:.3f} "
                 f"| {best['noise_active_frac']:.3f} "
                 f"| {best['score']:.3f} |")
    lines.append("")
    delta_rd = best["real_delivery_active_frac"] - v1_row["real_delivery_active_frac"]
    lines.append(f"Δ rd_active_frac (live optimum − v1) = "
                 f"**{delta_rd:+.3f}**. §13 §C2 ship gate is ≥ 0.15.\n")
    return "\n".join(lines)


def main() -> int:
    print(f"reading {INPUT_JSONL}")
    rows = load_rows()
    print(f"  rows={len(rows)} span={rows[-1]['ts_s']-rows[0]['ts_s']:.1f}s")

    clips = build_clips(rows)
    by_label: Dict[str, int] = {}
    for lbl, _cid, _seg in clips:
        by_label[lbl] = by_label.get(lbl, 0) + 1
    print(f"clip corpus: {by_label}")
    write_corpus(clips)
    print(f"  wrote {AGG_CSV}")
    print(f"  wrote {len(clips)} per-clip JSONLs to {RAW_DIR}/")

    print("running sweep (v1 score)…")
    results, best = run_sweep(score_version="v1")
    print(f"\nbest live-corpus row: {json.dumps(best, indent=2)}")

    md = write_comparison(results, best, by_label)
    COMPARE_MD.write_text(md)
    print("\n" + md)
    print(f"\nwrote {COMPARE_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
