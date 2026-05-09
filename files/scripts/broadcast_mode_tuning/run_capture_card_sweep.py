#!/usr/bin/env python3
"""Drive ``tune_thresholds.py`` over (a) the existing motion-baseline
control corpus and (b) the capture-card treatment corpus, then emit a
three-way comparison vs the v1 production defaults.

Wraps ``tune_thresholds`` instead of editing it (the underlying tool
exposes neither ``--raw`` nor ``--aggregates``; both are module-level
constants). For each sweep we monkey-patch ``RAW_DIR`` / ``AGG_CSV``
and reuse the existing ``replay`` / ``build_grid`` machinery.

Outputs into ``files/scripts/broadcast_mode_tuning/``:

* ``sweep_results_control.csv`` / ``best_params_control.json``
* ``sweep_results_capture_card.csv`` / ``best_params_capture_card.json``
* ``capture_card_comparison.md`` — the three-way table from §3.1.
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

V1_DEFAULTS = {
    "open_strip_mean_max": 0.35,
    "open_flow_peak_min": 10,
    "close_strip_mean_max": 0.475,
    "close_flow_peak_min": 5,
}

WINDOW_S = 10.0
MIN_ACTIVE_S = 1.5
MIN_INACTIVE_S = 3.0


def run_sweep(
    raw_dir: Path,
    agg_csv: Path,
    sweep_csv: Path,
    best_json: Path,
    score_version: str,
    broad: bool,
) -> Tuple[List[Dict], Dict]:
    tt.RAW_DIR = raw_dir
    tt.AGG_CSV = agg_csv

    labels = tt.load_clip_labels()
    clip_signals: Dict[str, Tuple[str, List]] = {}
    for p in sorted(raw_dir.glob("*.jsonl")):
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
    print(f"  loaded {len(clip_signals)} clips from {raw_dir.name}: "
          + ", ".join(f"{k}={len(v)}" for k, v in sorted(by_label.items())),
          flush=True)

    grid = tt.build_grid(broad=broad)
    print(f"  grid={len(grid)}  → {len(grid) * len(clip_signals)} replays",
          flush=True)
    fixed = dict(window_s=WINDOW_S, min_active_s=MIN_ACTIVE_S,
                 min_inactive_s=MIN_INACTIVE_S)

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
        summary = {lbl: (sum(v) / len(v)) for lbl, v in per_label_active.items()}
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
            "window_s": WINDOW_S,
            "min_active_s": MIN_ACTIVE_S,
            "min_inactive_s": MIN_INACTIVE_S,
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
    with sweep_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        for r in results:
            w.writerow(r)
    best = dict(results[0])
    best["score_version"] = score_version
    best_json.write_text(json.dumps(best, indent=2) + "\n")
    return results, best


def find_v1_row(results: List[Dict]) -> Dict:
    for r in results:
        if all(abs(r[k] - V1_DEFAULTS[k]) < 1e-6 for k in V1_DEFAULTS):
            return r
    raise SystemExit("v1 defaults not found in sweep grid")


def make_comparison(
    control_results: List[Dict],
    control_best: Dict,
    cc_results: List[Dict],
    cc_best: Dict,
) -> str:
    cc_v1 = find_v1_row(cc_results)
    ctrl_v1 = find_v1_row(control_results)

    def fmt_row(name: str, v1: float, cap: float) -> str:
        delta = cap - v1
        pct = (delta / v1 * 100.0) if v1 else 0.0
        return (f"| {name} | {v1} | {cap} | "
                f"{delta:+.4f} ({pct:+.1f}%) |")

    lines: List[str] = []
    lines.append("# Phase B/C — Capture-card threshold comparison\n")
    lines.append("_Generated 2026-05-04 from session 20260503_200806 (55 clips)._\n")
    lines.append("## §3.1 Three-way threshold comparison\n")
    lines.append("Sweep 1 = control (motion-baseline mp4 corpus, ~15 fps). "
                 "Sweep 2 = treatment (capture-card clips subsampled to 5 fps).\n")
    lines.append("| Threshold | v1 production | capture-card optimum | Δ |")
    lines.append("|---|---|---|---|")
    for k in ("open_strip_mean_max", "open_flow_peak_min",
              "close_strip_mean_max", "close_flow_peak_min"):
        lines.append(fmt_row(k, V1_DEFAULTS[k], cc_best[k]))
    lines.append("")
    lines.append("Control sweep optimum (sanity-check vs v1):\n")
    lines.append("| Threshold | v1 production | control optimum | match? |")
    lines.append("|---|---|---|---|")
    for k in ("open_strip_mean_max", "open_flow_peak_min",
              "close_strip_mean_max", "close_flow_peak_min"):
        match = "✓" if abs(control_best[k] - V1_DEFAULTS[k]) < 1e-6 else "✗"
        lines.append(f"| {k} | {V1_DEFAULTS[k]} | {control_best[k]} | {match} |")
    lines.append("")
    lines.append("## §3.2 Active-fraction summary\n")
    lines.append("| corpus | params | rd_active_frac | replay_frac | noise_frac | score |")
    lines.append("|---|---|---|---|---|---|")
    lines.append(f"| control | v1 (production defaults) "
                 f"| {ctrl_v1['real_delivery_active_frac']:.3f} "
                 f"| {ctrl_v1['replay_active_frac']:.3f} "
                 f"| {ctrl_v1['noise_active_frac']:.3f} "
                 f"| {ctrl_v1['score']:.3f} |")
    lines.append(f"| control | control optimum "
                 f"| {control_best['real_delivery_active_frac']:.3f} "
                 f"| {control_best['replay_active_frac']:.3f} "
                 f"| {control_best['noise_active_frac']:.3f} "
                 f"| {control_best['score']:.3f} |")
    lines.append(f"| capture-card | v1 thresholds @ 5 fps "
                 f"| {cc_v1['real_delivery_active_frac']:.3f} "
                 f"| {cc_v1['replay_active_frac']:.3f} "
                 f"| {cc_v1['noise_active_frac']:.3f} "
                 f"| {cc_v1['score']:.3f} |")
    lines.append(f"| capture-card | capture-card optimum "
                 f"| {cc_best['real_delivery_active_frac']:.3f} "
                 f"| {cc_best['replay_active_frac']:.3f} "
                 f"| {cc_best['noise_active_frac']:.3f} "
                 f"| {cc_best['score']:.3f} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    out_dir = THIS
    print("Sweep 1 (control: motion_baseline)…", flush=True)
    control_results, control_best = run_sweep(
        raw_dir=ROOT / "scripts" / "motion_baseline" / "raw",
        agg_csv=ROOT / "scripts" / "motion_baseline" / "clip_aggregates.csv",
        sweep_csv=out_dir / "sweep_results_control.csv",
        best_json=out_dir / "best_params_control.json",
        score_version="v1",
        broad=True,
    )
    print(f"  control best: {control_best}\n", flush=True)

    print("Sweep 2 (treatment: capture-card)…", flush=True)
    cc_results, cc_best = run_sweep(
        raw_dir=ROOT / "logs" / "bmf_capture_card",
        agg_csv=out_dir / "capture_card_aggregates.csv",
        sweep_csv=out_dir / "sweep_results_capture_card.csv",
        best_json=out_dir / "best_params_capture_card.json",
        score_version="v1",
        broad=True,
    )
    print(f"  capture-card best: {cc_best}\n", flush=True)

    md = make_comparison(control_results, control_best, cc_results, cc_best)
    (out_dir / "capture_card_comparison.md").write_text(md)
    print(md)
    print(f"\nwrote {out_dir / 'capture_card_comparison.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
