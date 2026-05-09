#!/usr/bin/env python3
"""Phase B threshold sweep for ``BroadcastModeFilter``.

Replays every per-frame motion-signal trace in
``files/scripts/motion_baseline/raw/*.jsonl`` through the filter at
every combination of hysteresis parameters and scores each grid
point on

    score = real_delivery_active_fraction × ad_inactive_fraction

The script writes two artifacts:

* ``sweep_results.csv`` — every grid point with per-label active
  fractions and the combined score.
* ``best_params.json``  — the single grid point maximizing the
  score (tie-break: prefer higher real_delivery fraction, then
  lower ad fraction).

Usage::

    cd files
    python3 scripts/broadcast_mode_tuning/tune_thresholds.py
    python3 scripts/broadcast_mode_tuning/tune_thresholds.py --top 20
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

THIS = Path(__file__).resolve().parent
ROOT = THIS.parent.parent
sys.path.insert(0, str(ROOT))

from eyes.broadcast_mode_filter import BroadcastModeFilter, STATE_ACTIVE

RAW_DIR = ROOT / "scripts" / "motion_baseline" / "raw"
AGG_CSV = ROOT / "scripts" / "motion_baseline" / "clip_aggregates.csv"
OUT_DIR = THIS
# v1 = rd × (1 − ad); v2 = rd × (1 − ad) × (1 − replay).
# Version gets bumped via --out-tag so prior sweeps stay on disk for
# comparison (see tuning memo §9).
SWEEP_CSV_DEFAULT = OUT_DIR / "sweep_results.csv"
BEST_JSON_DEFAULT = OUT_DIR / "best_params.json"


def load_clip_labels() -> Dict[str, str]:
    """Return {``<session>__<clip>``: manual_label}."""
    out: Dict[str, str] = {}
    with AGG_CSV.open() as f:
        for r in csv.DictReader(f):
            out[f"{r['session']}__{r['clip_id']}"] = r["manual_label"]
    return out


def load_clip_signals(p: Path) -> List[Tuple[float, float, float]]:
    rows: List[Tuple[float, float, float]] = []
    with p.open() as f:
        for line in f:
            d = json.loads(line)
            rows.append((d["ts_s"], d["flow_magnitude"], d["strip_diff"]))
    return rows


def replay(
    signals: List[Tuple[float, float, float]],
    **params,
) -> Tuple[float, float]:
    """Return (active_time_s, total_time_s) for a single clip."""
    bmf = BroadcastModeFilter(
        on_window_open=lambda _t: None,
        on_window_close=lambda _t: None,
        **params,
    )
    active = 0.0
    total = 0.0
    prev_ts = signals[0][0] if signals else 0.0
    for ts, flow, strip in signals:
        dt = max(0.0, ts - prev_ts)
        bmf.ingest_signals(ts, flow, strip)
        if bmf.current_state() == STATE_ACTIVE:
            active += dt
        total += dt
        prev_ts = ts
    return active, total


def build_grid(broad: bool = False) -> List[Dict]:
    """Per spec B2, with close thresholds defined as deltas from open.

    ``--broad`` enlarges the grid beyond the spec defaults to probe
    operating points past the spec corner (the spec grid's optimum
    saturates at open_strip=0.25 / open_flow=25 because the
    sliding-window peak_count ≪ the full-clip peak_count the spec
    was calibrated against — see Phase-B tuning memo).
    """
    if broad:
        open_strip_vals = [round(0.10 + 0.05 * i, 4) for i in range(7)]  # 0.10..0.40
        open_flow_vals = list(range(10, 55, 5))                          # 10..50
    else:
        open_strip_vals = [round(0.10 + 0.025 * i, 4) for i in range(7)]  # 0.10..0.25
        open_flow_vals = list(range(25, 55, 5))                           # 25..50
    close_strip_deltas = [0.05, 0.075, 0.10, 0.125, 0.15]
    close_flow_deltas = [5, 10, 15]
    grid: List[Dict] = []
    for os_strip in open_strip_vals:
        for of_flow in open_flow_vals:
            for d_strip in close_strip_deltas:
                for d_flow in close_flow_deltas:
                    grid.append({
                        "open_strip_mean_max": os_strip,
                        "open_flow_peak_min": of_flow,
                        "close_strip_mean_max": round(
                            os_strip + d_strip, 4),
                        "close_flow_peak_min": max(
                            1, of_flow - d_flow),
                    })
    return grid


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-s", type=float, default=10.0)
    ap.add_argument("--min-active-s", type=float, default=3.0)
    ap.add_argument("--min-inactive-s", type=float, default=5.0)
    ap.add_argument("--top", type=int, default=10,
                    help="print top-N grid points by score")
    ap.add_argument("--broad", action="store_true",
                    help="expanded grid beyond spec defaults")
    ap.add_argument("--score", choices=["v1", "v2"], default="v2",
                    help="v1 = rd × (1 − ad); "
                         "v2 = rd × (1 − ad) × (1 − replay). Default v2.")
    ap.add_argument("--out-tag", type=str, default=None,
                    help="suffix for output files; defaults to score "
                         "version (sweep_results_<tag>.csv / "
                         "best_params_<tag>.json). Tag 'v1' writes the "
                         "legacy sweep_results.csv / best_params.json.")
    args = ap.parse_args()

    labels = load_clip_labels()

    clip_signals: Dict[str, Tuple[str, List]] = {}
    for p in sorted(RAW_DIR.glob("*.jsonl")):
        key = p.stem
        lbl = labels.get(key)
        if not lbl:
            continue
        sigs = load_clip_signals(p)
        if len(sigs) >= 3:
            clip_signals[key] = (lbl, sigs)
    if not clip_signals:
        print("no clip signals found", file=sys.stderr)
        return 1

    by_label: Dict[str, List[str]] = {}
    for key, (lbl, _) in clip_signals.items():
        by_label.setdefault(lbl, []).append(key)
    print(f"loaded {len(clip_signals)} clips: "
          + ", ".join(f"{k}={len(v)}" for k, v in sorted(by_label.items())),
          flush=True)

    grid = build_grid(broad=args.broad)
    print(f"grid size: {len(grid)}  "
          f"({len(clip_signals)} clips × {len(grid)} "
          f"= {len(clip_signals) * len(grid)} replays)",
          flush=True)

    fixed_kwargs = dict(
        window_s=args.window_s,
        min_active_s=args.min_active_s,
        min_inactive_s=args.min_inactive_s,
    )

    results: List[Dict] = []
    t0 = time.monotonic()
    for gi, g in enumerate(grid):
        params = dict(fixed_kwargs)
        params.update(g)
        per_label_active: Dict[str, List[float]] = {}
        for key, (lbl, sigs) in clip_signals.items():
            active, total = replay(sigs, **params)
            frac = active / total if total > 0 else 0.0
            per_label_active.setdefault(lbl, []).append(frac)
        summary = {lbl: (sum(v) / len(v)) for lbl, v in per_label_active.items()}
        rd = summary.get("real_delivery", 0.0)
        ad = summary.get("ad", 0.0)
        rp = summary.get("replay", 0.0)
        ns = summary.get("noise", 0.0)
        if args.score == "v1":
            score = rd * (1.0 - ad)
        else:
            score = rd * (1.0 - ad) * (1.0 - rp)
        row = {
            **g,
            "window_s": args.window_s,
            "min_active_s": args.min_active_s,
            "min_inactive_s": args.min_inactive_s,
            "real_delivery_active_frac": round(rd, 4),
            "ad_active_frac": round(ad, 4),
            "replay_active_frac": round(rp, 4),
            "noise_active_frac": round(ns, 4),
            "score": round(score, 4),
        }
        results.append(row)
        if (gi + 1) % 50 == 0 or gi + 1 == len(grid):
            dt = time.monotonic() - t0
            eta = dt / (gi + 1) * (len(grid) - gi - 1)
            print(f"  [{gi + 1}/{len(grid)}] "
                  f"elapsed {dt:.1f}s  eta {eta:.1f}s", flush=True)

    results.sort(key=lambda r: (
        -r["score"],
        -r["real_delivery_active_frac"],
        r["ad_active_frac"],
    ))

    tag = args.out_tag or args.score
    if tag == "v1" and not args.out_tag:
        sweep_csv = SWEEP_CSV_DEFAULT
        best_json = BEST_JSON_DEFAULT
    else:
        sweep_csv = OUT_DIR / f"sweep_results_{tag}.csv"
        best_json = OUT_DIR / f"best_params_{tag}.json"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with sweep_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        for r in results:
            w.writerow(r)

    best = dict(results[0])
    best["score_version"] = args.score
    best_json.write_text(json.dumps(best, indent=2) + "\n")

    score_formula = ("rd × (1 − ad)" if args.score == "v1"
                     else "rd × (1 − ad) × (1 − replay)")
    print(f"\nTop {args.top} grid points (by score = {score_formula}):\n")
    hdr = ("open_strip  open_flow  close_strip  close_flow  "
           "  rd    ad  replay  noise   score")
    print(hdr)
    print("-" * len(hdr))
    for r in results[: args.top]:
        print(f"   {r['open_strip_mean_max']:.3f}        "
              f"{r['open_flow_peak_min']:3d}        "
              f"{r['close_strip_mean_max']:.3f}        "
              f"{r['close_flow_peak_min']:3d}    "
              f"{r['real_delivery_active_frac']:.2f}  "
              f"{r['ad_active_frac']:.2f}  "
              f"{r['replay_active_frac']:.2f}  "
              f"{r['noise_active_frac']:.2f}   "
              f"{r['score']:.3f}")
    print(f"\nsweep → {sweep_csv}")
    print(f"best  → {best_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
