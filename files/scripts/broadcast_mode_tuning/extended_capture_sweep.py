#!/usr/bin/env python3
"""Extended-grid capture-card sweep.

The broad grid in ``tune_thresholds.build_grid`` caps
``open_strip_mean_max`` at 0.40, but capture-card per-clip
``strip_mean`` values run 0.4–6.0 (median 1.32). Every broad-grid
point therefore scores 0 — the sweep optimum is a sentinel corner.
This driver widens ``open_strip`` to {0.5, 1.0, 1.5, 2.0, 2.5, 3.0,
4.0, 5.0} so we can locate where ``real_delivery_active_frac``
actually rises off the floor.
"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

THIS = Path(__file__).resolve().parent
ROOT = THIS.parent.parent
sys.path.insert(0, str(ROOT))

import scripts.broadcast_mode_tuning.tune_thresholds as tt  # noqa: E402

WINDOW_S = 10.0
MIN_ACTIVE_S = 1.5
MIN_INACTIVE_S = 3.0


def extended_grid() -> List[Dict]:
    open_strip_vals = [0.4, 0.6, 0.8, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
    open_flow_vals = [5, 10, 15, 20, 25]
    close_strip_deltas = [0.1, 0.2, 0.4, 0.8]
    close_flow_deltas = [3, 5, 10]
    grid = []
    for os_strip in open_strip_vals:
        for of_flow in open_flow_vals:
            for d_strip in close_strip_deltas:
                for d_flow in close_flow_deltas:
                    grid.append({
                        "open_strip_mean_max": os_strip,
                        "open_flow_peak_min": of_flow,
                        "close_strip_mean_max": round(os_strip + d_strip, 4),
                        "close_flow_peak_min": max(1, of_flow - d_flow),
                    })
    return grid


def main() -> int:
    tt.RAW_DIR = ROOT / "logs" / "bmf_capture_card"
    tt.AGG_CSV = THIS / "capture_card_aggregates.csv"

    labels = tt.load_clip_labels()
    clip_signals = {}
    for p in sorted(tt.RAW_DIR.glob("*.jsonl")):
        key = p.stem
        lbl = labels.get(key)
        if not lbl:
            continue
        sigs = tt.load_clip_signals(p)
        if len(sigs) >= 3:
            clip_signals[key] = (lbl, sigs)
    print(f"loaded {len(clip_signals)} clips", flush=True)

    grid = extended_grid()
    print(f"grid={len(grid)}  → {len(grid)*len(clip_signals)} replays",
          flush=True)
    fixed = dict(window_s=WINDOW_S, min_active_s=MIN_ACTIVE_S,
                 min_inactive_s=MIN_INACTIVE_S)

    results = []
    t0 = time.monotonic()
    for gi, g in enumerate(grid):
        params = dict(fixed); params.update(g)
        rd_list = []
        for key, (lbl, sigs) in clip_signals.items():
            active, total = tt.replay(sigs, **params)
            rd_list.append(active / total if total > 0 else 0.0)
        rd = sum(rd_list) / len(rd_list)
        results.append({**g, **fixed,
                        "real_delivery_active_frac": round(rd, 4),
                        "score": round(rd, 4)})
        if (gi + 1) % 100 == 0 or gi + 1 == len(grid):
            dt = time.monotonic() - t0
            print(f"  [{gi+1}/{len(grid)}] elapsed {dt:.1f}s", flush=True)

    results.sort(key=lambda r: (-r["score"], r["open_strip_mean_max"],
                                -r["open_flow_peak_min"]))

    out_csv = THIS / "sweep_results_capture_card_extended.csv"
    with out_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        for r in results:
            w.writerow(r)
    print(f"\nwrote {out_csv}")
    print("\nTop 12 by rd_active_frac (tiebreak: tightest open_strip):\n")
    print(f"{'open_strip':>10} {'open_flow':>9} {'close_strip':>11} "
          f"{'close_flow':>10} {'rd_active':>10}")
    for r in results[:12]:
        print(f"{r['open_strip_mean_max']:>10.3f} "
              f"{r['open_flow_peak_min']:>9d} "
              f"{r['close_strip_mean_max']:>11.3f} "
              f"{r['close_flow_peak_min']:>10d} "
              f"{r['real_delivery_active_frac']:>10.3f}")

    print("\nrd_active_frac vs open_strip ceiling (best per ceiling):\n")
    by_strip = {}
    for r in results:
        s = r["open_strip_mean_max"]
        if s not in by_strip or r["real_delivery_active_frac"] > by_strip[s]["real_delivery_active_frac"]:
            by_strip[s] = r
    for s in sorted(by_strip.keys()):
        r = by_strip[s]
        print(f"  open_strip={s:>5.2f}  best rd={r['real_delivery_active_frac']:.3f}  "
              f"(open_flow={r['open_flow_peak_min']}, "
              f"close_strip={r['close_strip_mean_max']:.3f}, "
              f"close_flow={r['close_flow_peak_min']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
