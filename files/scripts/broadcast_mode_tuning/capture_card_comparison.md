# Phase B/C — Capture-card threshold re-tune findings

_Generated 2026-05-04 from session `20260503_200806` (55 clips, d049
missing mp4)._

## §1 Per-frame signal distribution shift

| signal (per frame-pair) | control corpus (15 fps) | capture-card (5 fps) | ratio |
| ----------------------- | ----------------------- | -------------------- | ----- |
| `flow_magnitude` median | 1.57                    | 3.21                 | 2.0×  |
| `flow_magnitude` p95    | 9.11                    | 9.19                 | 1.0×  |
| `strip_diff` median     | 0.018                   | 0.633                | 35×   |
| `strip_diff` p95        | 0.500                   | 9.295                | 19×   |

Per-clip aggregates (driving the sweep):

| aggregate           | control p50 / p95 | capture-card p50 / p95 |
| ------------------- | ----------------- | ---------------------- |
| `strip_mean`        | 0.069 / 0.312     | **1.321 / 4.734**      |
| `flow_mean`         | 1.16 / 5.79       | 3.62 / 6.10            |

The `strip_diff` distribution shift is the headline finding. At
~20× the offline-baseline median, capture-card strip aggregates
sit far outside any spec or broad-grid `open_strip_mean_max`
ceiling.

## §2 Cadence sensitivity (6 clips, multi-fps probe)

| ingest cadence | flow median / p95 | strip median / p95 |
| -------------- | ----------------- | ------------------- |
|  5 fps         | 2.92 / 11.15      | 0.610 / 13.67       |
| 15 fps         | 1.44 /  6.61      | 0.215 /  7.33       |
| 30 fps         | 0.50 /  4.74      | 0.070 /  3.77       |
| baseline (15)  | 1.57 /  9.11      | 0.018 /  0.50       |

Cadence absorbs roughly half of the flow shift and a third of the
strip shift, but **strip_diff stays ~12–15× above baseline at
matched 15 fps**. So cadence is part of the gap, not all of it.

## §3 Sweep results

### §3.1 Control sweep (sanity check)

`tune_thresholds.py --score v1 --broad` reproduced the v1
production defaults exactly:

| param                  | v1 production | control optimum | match |
| ---------------------- | ------------- | --------------- | ----- |
| `open_strip_mean_max`  | 0.350         | 0.350           | ✓     |
| `open_flow_peak_min`   | 10            | 10              | ✓     |
| `close_strip_mean_max` | 0.475         | 0.475           | ✓     |
| `close_flow_peak_min`  | 5             | 5               | ✓     |

`real_delivery_active_frac` 0.687 at v1 — matches the value
recorded in `best_params.json`. The sweep tool itself is not the
issue.

### §3.2 Capture-card sweep (broad grid, per memo §13)

Every grid point produced
`real_delivery_active_frac = 0.000`. The recorded "optimum" is the
sentinel corner (`open_strip=0.10`, `open_flow=10`,
`score=0.0000`) — the broad grid (open_strip ≤ 0.40) is fully
below the capture-card per-clip strip_mean distribution
(p50=1.32). Sweep CSV: `sweep_results_capture_card.csv`,
`best_params_capture_card.json`.

### §3.3 Capture-card sweep (extended grid, open_strip up to 5.0)

Best-per-`open_strip` after widening the grid:

| `open_strip_mean_max` | best rd_active_frac | flow / close-strip / close-flow |
| --------------------- | ------------------- | ------------------------------- |
|  0.40                 | 0.009               | 5 / 0.50 / 2                    |
|  0.60                 | 0.063               | 5 / 0.70 / 2                    |
|  0.80                 | 0.109               | 5 / 0.90 / 2                    |
|  1.00                 | 0.124               | 5 / 1.10 / 2                    |
|  1.50                 | 0.213               | 5 / 1.90 / 2                    |
|  2.00                 | 0.245               | 5 / 2.80 / 2                    |
|  2.50                 | 0.262               | 5 / 3.30 / 2                    |
|  3.00                 | 0.274               | 5 / 3.40 / 2                    |
|  4.00                 | 0.280               | 5 / 4.10 / 2                    |
|  **5.00**             | **0.288**           | 5 / 5.10 / 2                    |

`real_delivery_active_frac` saturates at **0.288** even with an
absurdly loose `open_strip=5.0` and the lowest possible
`open_flow=5` / `close_flow=2`. Pure-threshold tuning does not
recover the v1 control 0.687.

CSV: `sweep_results_capture_card_extended.csv`.

## §4 Threshold-only ceiling and why

Two structural limits combine:

1. **Strip distribution saturates the open band.** Capture-card
   `strip_mean` per-clip p95 is 4.7. To open on those, we need
   `open_strip_mean_max ≥ 4.7`. At `open_strip=5.0` we still
   only fire 28.8 % active because…
2. **Clip length vs window_s.** Each clip is ~12 s long. With
   `window_s=10.0` the sliding window only stabilizes near
   clip-end; with `min_active_s=1.5` and `min_inactive_s=3.0`
   debounce, max achievable active fraction on 12 s clips is
   ~70 % even with always-true open conditions. Combined with
   strip volatility this caps real-corpus rd_active well below
   the offline 0.687.

The capture-card corpus underestimates rd_active vs production
(continuous stream), but the *relative* shift between v1 (0.000)
and any threshold-tuned point (≤0.288) is informative.

## §5 Diagnosis

Per the §13 decision rule:

> "If capture-card thresholds within ±20 % of v1: distribution
> not the issue. Ship preprocessing fix.
> If capture-card thresholds differ significantly: distribution
> shift. Ship as v3 production thresholds."

We have **distribution shift far beyond ±20 %**:
`open_strip_mean_max` would need to move from 0.35 to ~3.0 to
recover any meaningful rd_active. But threshold tuning alone
caps at rd=0.288 — the §13 ≥0.15-absolute-improvement gate is
met (0.000 → 0.288 ≈ +0.29 absolute), but the absolute level
remains far below the control-corpus 0.687 and ad-suppression
cannot be evaluated on this single-class corpus.

The cadence probe (§2) shows preprocessing absorbs part of the
shift but not all. The residual after cadence-correction is the
broadcast-feed difference itself: a different network's overlay
graphics, or a different decode path, or both.

## §6 Recommendation (operator approval required before ship)

**Do not ship a v3 threshold update before tonight's match on
this evidence alone.** Both options below are non-trivial. The
data narrows the choice but does not decide it.

### Option A — Preprocessing fix (lowest blast radius)

1. Raise `SHADOW_INGEST_FPS` from 5.0 → 15.0 (matches offline
   baseline cadence; closes the flow gap; reduces strip volatility
   ~3×).
2. Verify the capture-decode path honors `max_flow_dim=(640,360)`
   downsampling before computing `strip_diff`. Per §13.3 a
   pipeline path that resizes after `strip_diff` would inflate
   strip values.

Risks: triples BMF compute load (5 → 15 fps × Farneback flow);
needs S1-equivalent perf re-validation. Doesn't fully close the
gap (residual ~12× strip shift remains from broadcast graphics
themselves).

### Option B — Threshold-only v3 update (highest brittleness)

Candidate v3 thresholds (capture-card extended sweep, conservative
floor that still gives meaningful rd_active):

| param                  | v1     | v3 candidate |
| ---------------------- | ------ | ------------ |
| `open_strip_mean_max`  | 0.35   | **2.00**     |
| `open_flow_peak_min`   | 10     | **5**        |
| `close_strip_mean_max` | 0.475  | **2.80**     |
| `close_flow_peak_min`  | 5      | **2**        |

At those values, capture-card rd_active = 0.245 (vs 0.000 today).
But: this corpus has no ad/replay/noise samples, so we cannot
verify ad suppression — the original Stage-1 mandate (§10). v3
shipped on this evidence alone may pass any-motion content
including ads.

### Recommended next step

**Option A first**, gated on a single-night soak in shadow:

1. Land a `SHADOW_INGEST_FPS=15` flag (env-gated, default 5.0
   for safety) before tonight.
2. Capture telemetry per §13 Phase A while running both flag
   states side-by-side.
3. If `rd_active` recovers to ≥0.5 at 15 fps with v1 thresholds,
   ship as preprocessing fix.
4. If still floor-stuck, the broadcast-graphics residual is the
   problem. At that point we need a *labeled* capture-card corpus
   with ad / replay / noise content (the current corpus is
   delivery-only) before moving v1 thresholds.

## §7 Artefacts produced

- `files/scripts/broadcast_mode_tuning/compute_capture_card_signals.py`
- `files/scripts/broadcast_mode_tuning/run_capture_card_sweep.py`
- `files/scripts/broadcast_mode_tuning/extended_capture_sweep.py`
- `files/scripts/broadcast_mode_tuning/capture_card_aggregates.csv` (55 rows)
- `files/scripts/broadcast_mode_tuning/sweep_results_control.csv` + `best_params_control.json`
- `files/scripts/broadcast_mode_tuning/sweep_results_capture_card.csv` + `best_params_capture_card.json`
- `files/scripts/broadcast_mode_tuning/sweep_results_capture_card_extended.csv`
- `files/logs/bmf_capture_card/20260503_200806__d{001..056}.jsonl` (55 files)

## §8 Phase 4 status

Production thresholds (`files/eyes/broadcast_mode_filter.py:170-202`)
**not modified** per Phase 4.2 caveat ("don't ship without user
approval — preprocessing fix has more risk than threshold update").
Memo §13 updated below with these findings.
