"""P22 density-based span detection sweep.

Reads logs/openscout-d03b43da.jsonl (yesterday's CSK vs MI innings 2)
and logs/pipeline-2026-05-02-2049-csk-vs-mi-44th-match-ipl-2026-innings2.log.

Produces JSON output to stdout summarising:
  * 1 Hz density time series for window sizes W in {6, 10, 14, 20} s
  * delivery- vs non-delivery-window density distributions
  * full hysteresis-state-machine parameter sweep with precision/recall/F1
  * sub-sampled (half-rate) sweep to estimate the impact of doubling the
    dispatch rate.

Run from repo root: ``python3 files/scripts/investigations/p22_density_sweep.py``.
"""
from __future__ import annotations

import bisect
import datetime as dt
import json
import re
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
JSONL = ROOT / "logs" / "openscout-d03b43da.jsonl"
PIPELINE_LOG = (
    ROOT / "logs"
    / "pipeline-2026-05-02-2049-csk-vs-mi-44th-match-ipl-2026-innings2.log"
)
ANSI = re.compile(r"\x1b\[[0-9;]*m")
DELIVERY_RE = re.compile(
    r"\[(\d{2}:\d{2}:\d{2})\s+F(\d+)\s+TEST\]\s+INFO:\s+\[DELIVERY ENQUEUED\]"
    r"\s+dnum=(\d+)"
)
DATE_STR = "2026-05-02"


def load_records():
    recs = [json.loads(line) for line in JSONL.open()]
    recs.sort(key=lambda r: r["ts"])
    return recs


def load_deliveries():
    out = []
    for line in PIPELINE_LOG.open(errors="replace"):
        s = ANSI.sub("", line)
        m = DELIVERY_RE.search(s)
        if not m:
            continue
        hms = m.group(1)
        wall = dt.datetime.strptime(f"{DATE_STR} {hms}", "%Y-%m-%d %H:%M:%S")
        out.append(wall.timestamp())
    return out


def density_series(recs, *, window_s, classes, grid_step_s=1.0):
    """Return list[(ts, ratio)] over the match span at grid_step_s cadence.

    ratio = (# records whose frame_class in classes) / (# records in window).
    Returns 0.0 when the window has no records.
    """
    typed = [r for r in recs if r.get("frame_class") is not None]
    typed.sort(key=lambda r: r["ts"])
    times = [r["ts"] for r in typed]
    if not typed:
        return []
    cls_set = set(classes)
    is_target = [1 if r["frame_class"] in cls_set else 0 for r in typed]
    cum_target = [0]
    cum_total = [0]
    for v in is_target:
        cum_target.append(cum_target[-1] + v)
        cum_total.append(cum_total[-1] + 1)

    t0 = times[0]
    t1 = times[-1]
    out = []
    half = window_s / 2.0
    n_steps = int((t1 - t0) / grid_step_s) + 1
    for i in range(n_steps):
        t = t0 + i * grid_step_s
        lo = t - half
        hi = t + half
        i_lo = bisect.bisect_left(times, lo)
        i_hi = bisect.bisect_right(times, hi)
        n = cum_total[i_hi] - cum_total[i_lo]
        if n == 0:
            ratio = 0.0
        else:
            tgt = cum_target[i_hi] - cum_target[i_lo]
            ratio = tgt / n
        out.append((t, ratio, n))
    return out


def detect_with_hysteresis(series, *, t_open, t_close, k_close_s):
    """Return list[(start_ts, end_ts)] of detected delivery spans.

    State machine:
      NOT_IN -> IN when ratio >= t_open
      IN -> NOT_IN when ratio < t_close for k_close_s consecutive seconds
    """
    spans = []
    in_span = False
    span_start = None
    below_since = None
    last_above_ts = None
    for t, ratio, _n in series:
        if not in_span:
            if ratio >= t_open:
                in_span = True
                span_start = t
                last_above_ts = t
                below_since = None
        else:
            if ratio >= t_close:
                last_above_ts = t
                below_since = None
            else:
                if below_since is None:
                    below_since = t
                if (t - below_since) >= k_close_s:
                    spans.append((span_start, last_above_ts))
                    in_span = False
                    span_start = None
                    below_since = None
                    last_above_ts = None
    if in_span and span_start is not None:
        spans.append((span_start, last_above_ts or span_start))
    return spans


def evaluate_against_truth(detected, truths, tol_s=5.0):
    """Greedy match each detected span (by midpoint) to nearest truth.

    Returns (tp, fp, fn, matched_truth_set).
    """
    truth_used = [False] * len(truths)
    truths_sorted_idx = sorted(range(len(truths)), key=lambda i: truths[i])
    truth_ts_sorted = [truths[i] for i in truths_sorted_idx]
    tp = 0
    for s, e in detected:
        mid = (s + e) / 2.0
        # Find closest truth via bisect
        i = bisect.bisect_left(truth_ts_sorted, mid)
        cand = []
        for j in (i - 1, i):
            if 0 <= j < len(truth_ts_sorted):
                cand.append(j)
        cand.sort(key=lambda j: abs(truth_ts_sorted[j] - mid))
        matched = False
        for j in cand:
            real_idx = truths_sorted_idx[j]
            if truth_used[real_idx]:
                continue
            if abs(truth_ts_sorted[j] - mid) <= tol_s:
                truth_used[real_idx] = True
                matched = True
                tp += 1
                break
        # else: not matched (FP)
        if not matched:
            pass
    fp = len(detected) - tp
    fn = sum(1 for u in truth_used if not u)
    return tp, fp, fn


def f1(tp, fp, fn):
    if tp == 0:
        return 0.0, 0.0, 0.0
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    if p + r == 0:
        return p, r, 0.0
    return p, r, 2 * p * r / (p + r)


def parameter_sweep(recs, deliveries, *, half_rate=False, tol_s=5.0):
    if half_rate:
        recs = [r for i, r in enumerate(recs) if i % 2 == 0]
    results = []
    class_sets = {
        "action": ("action",),
        "action+closeup": ("action", "closeup"),
        "action+closeup+other": ("action", "closeup", "other"),
    }
    # Note: open_scout exposes {action, replay, ad, umpire, other}; "closeup"
    # is not a frame_class value. Treat the "action+closeup" combo as the
    # design-memo intent: action plus the cam=closeup tag, but since cam
    # is not in JSONL, we approximate "active broadcast view" = action only.
    # Drop the "+closeup" combos for honesty; report action and action+other.
    class_sets = {
        "action": ("action",),
        "action+other": ("action", "other"),
    }
    sweep_W = (6, 10, 14, 20)
    sweep_open = (0.30, 0.40, 0.50, 0.60, 0.70)
    sweep_drop = (0.10, 0.20)
    sweep_K = (1, 2, 3)

    cache = {}
    for cls_label, classes in class_sets.items():
        for W in sweep_W:
            key = (cls_label, W)
            if key not in cache:
                cache[key] = density_series(
                    recs, window_s=W, classes=classes)
            series = cache[key]
            for t_open in sweep_open:
                for drop in sweep_drop:
                    t_close = max(0.0, t_open - drop)
                    if t_close >= t_open:
                        continue
                    for K in sweep_K:
                        detected = detect_with_hysteresis(
                            series,
                            t_open=t_open,
                            t_close=t_close,
                            k_close_s=K,
                        )
                        tp, fp, fn = evaluate_against_truth(
                            detected, deliveries, tol_s=tol_s)
                        p, r, f = f1(tp, fp, fn)
                        results.append({
                            "classes": cls_label,
                            "W": W,
                            "t_open": t_open,
                            "t_close": round(t_close, 2),
                            "K": K,
                            "n_detected": len(detected),
                            "tp": tp, "fp": fp, "fn": fn,
                            "precision": round(p, 3),
                            "recall": round(r, 3),
                            "f1": round(f, 3),
                        })
    return results, cache


def signal_shape_around(deliveries, series, *, before_s=15.0, after_s=15.0):
    """For each delivery ts, sample series at [-before, +after] s offsets."""
    times = [t for t, _r, _n in series]
    ratios = [r for _t, r, _n in series]
    rows = []
    for ts in deliveries:
        i_lo = bisect.bisect_left(times, ts - before_s)
        i_hi = bisect.bisect_right(times, ts + after_s)
        offsets = [round(times[i] - ts) for i in range(i_lo, i_hi)]
        rs = ratios[i_lo:i_hi]
        rows.append((ts, offsets, rs))
    return rows


def density_distribution(series, *, intervals):
    """For each interval (lo, hi), collect series ratios whose ts is in window.
    intervals is list of (lo_ts, hi_ts, label).
    """
    times = [t for t, _r, _n in series]
    out = {}
    for lo, hi, label in intervals:
        i_lo = bisect.bisect_left(times, lo)
        i_hi = bisect.bisect_right(times, hi)
        out[label] = [series[i][1] for i in range(i_lo, i_hi)]
    return out


def main():
    recs = load_records()
    deliveries = load_deliveries()
    print(json.dumps({
        "n_records": len(recs),
        "n_deliveries": len(deliveries),
        "match_first_ts": recs[0]["ts"],
        "match_last_ts": recs[-1]["ts"],
        "match_duration_min": round((recs[-1]["ts"] - recs[0]["ts"]) / 60, 1),
    }))

    # --- Phase B: signal shape around real deliveries -----------------
    series_action_w10 = density_series(
        recs, window_s=10, classes=("action",))
    rows = signal_shape_around(
        deliveries, series_action_w10, before_s=10, after_s=10)
    # Aggregate the offset profile across deliveries
    by_off = {}
    for _ts, offsets, rs in rows:
        for o, r in zip(offsets, rs):
            by_off.setdefault(o, []).append(r)
    print("\n# Phase B — average action-density (W=10 s) around delivery ts")
    print("# offset_s, n_samples, mean_ratio, p25, p50, p75")
    for o in sorted(by_off):
        vals = sorted(by_off[o])
        if len(vals) < 5:
            continue
        n = len(vals)
        print(f"  {o:>+3d}, {n:>3d}, "
              f"{statistics.mean(vals):.2f}, "
              f"{vals[n // 4]:.2f}, "
              f"{vals[n // 2]:.2f}, "
              f"{vals[3 * n // 4]:.2f}")

    # Sample 20 non-delivery windows: pick ts midpoints between consecutive
    # deliveries that are far from any delivery (>= 10s gap), plus some
    # known-quiet windows (innings break, ad runs).
    nondelivery_intervals = []
    sorted_d = sorted(deliveries)
    for a, b in zip(sorted_d, sorted_d[1:]):
        if (b - a) >= 30:
            mid = (a + b) / 2.0
            nondelivery_intervals.append((mid - 5, mid + 5, f"gap_mid_{mid:.0f}"))
        if len(nondelivery_intervals) >= 20:
            break
    # Distributions
    delivery_intervals = [
        (ts - 5, ts + 5, f"delivery_{ts:.0f}") for ts in deliveries
    ]
    dist_d = density_distribution(
        series_action_w10, intervals=delivery_intervals)
    dist_nd = density_distribution(
        series_action_w10, intervals=nondelivery_intervals)
    flat_d = [v for vs in dist_d.values() for v in vs]
    flat_nd = [v for vs in dist_nd.values() for v in vs]

    def quartiles(vals):
        if not vals:
            return None
        v = sorted(vals)
        n = len(v)
        return {
            "n": n,
            "min": round(v[0], 3),
            "p25": round(v[n // 4], 3),
            "p50": round(v[n // 2], 3),
            "p75": round(v[3 * n // 4], 3),
            "p90": round(v[min(n - 1, int(0.9 * n))], 3),
            "max": round(v[-1], 3),
            "mean": round(statistics.mean(v), 3),
        }

    print("\n# Phase B — action-density (W=10) distribution (±5 s windows)")
    print(f"  delivery windows : {quartiles(flat_d)}")
    print(f"  non-delivery     : {quartiles(flat_nd)}")

    # --- Phase C: full sweep ------------------------------------------
    print("\n# Phase C — full sweep (top-15 by F1)")
    results, _cache = parameter_sweep(recs, deliveries)
    results_sorted = sorted(results, key=lambda r: (-r["f1"], -r["tp"]))
    print("# rank, classes, W, t_open, t_close, K, n_det, tp, fp, fn, P, R, F1")
    for i, r in enumerate(results_sorted[:15], 1):
        print(f"  {i:>2}, {r['classes']:>16}, W={r['W']:>2}, "
              f"o={r['t_open']:.2f}, c={r['t_close']:.2f}, K={r['K']}, "
              f"n={r['n_detected']:>3}, tp={r['tp']:>2}, fp={r['fp']:>2}, "
              f"fn={r['fn']:>2}, P={r['precision']:.2f}, R={r['recall']:.2f}, "
              f"F1={r['f1']:.2f}")

    # By class set
    print("\n# Phase D — best F1 per class set")
    by_cls = {}
    for r in results_sorted:
        by_cls.setdefault(r["classes"], r)
    for cls, best in by_cls.items():
        print(f"  {cls:>16}: F1={best['f1']:.2f} "
              f"P={best['precision']:.2f} R={best['recall']:.2f} "
              f"@ W={best['W']} o={best['t_open']} c={best['t_close']} K={best['K']}")

    # --- Phase D: half-rate sub-sample --------------------------------
    print("\n# Phase D — half-rate sweep (every other record dropped)")
    halfres, _ = parameter_sweep(recs, deliveries, half_rate=True)
    halfres_sorted = sorted(halfres, key=lambda r: (-r["f1"], -r["tp"]))
    print("# top-5 (half-rate)")
    for i, r in enumerate(halfres_sorted[:5], 1):
        print(f"  {i:>2}, {r['classes']:>16}, W={r['W']:>2}, "
              f"o={r['t_open']:.2f}, c={r['t_close']:.2f}, K={r['K']}, "
              f"n={r['n_detected']:>3}, tp={r['tp']:>2}, fp={r['fp']:>2}, "
              f"fn={r['fn']:>2}, P={r['precision']:.2f}, R={r['recall']:.2f}, "
              f"F1={r['f1']:.2f}")

    # Compare best F1 full vs half
    print(f"\n  full-rate best F1: {results_sorted[0]['f1']:.3f}  "
          f"(P={results_sorted[0]['precision']:.2f} "
          f"R={results_sorted[0]['recall']:.2f})")
    print(f"  half-rate best F1: {halfres_sorted[0]['f1']:.3f}  "
          f"(P={halfres_sorted[0]['precision']:.2f} "
          f"R={halfres_sorted[0]['recall']:.2f})")

    # Class-distribution context
    print("\n# Class counts in JSONL (typed records only):")
    typed = [r for r in recs if r.get("frame_class") is not None]
    cnt = Counter(r["frame_class"] for r in typed)
    print(f"  {dict(cnt)}  (total typed: {len(typed)})")

    # Innings-break window: F647-F864 per task brief.
    # Find approximate innings-break wall-clock from the pipeline log.
    # (Not strictly needed for sweep; informational.)


if __name__ == "__main__":
    main()
