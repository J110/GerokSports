# Phase D — capture-card LIVE telemetry sweep (2026-05-04)

_Source: `files/files/logs/bmf_debug/bmf_b0cdc9f9.jsonl` (5 MB, ~30k rows, 30 score-event groups, ~14 fps)._

## §D.1 Synthetic clip corpus

| label | clips |
|---|---|
| ad | 35 |
| real_delivery | 30 |
| replay | 67 |

Real-delivery clips windowed [score_ts − 10.0s, score_ts + 5.0s]; gap clips 14.0s; gap split: ad if flow_p95 ≤ 5.0 AND strip_mean ≤ 2.0, else replay.

## §D.2 Threshold comparison

| Threshold | v1 production | morning capture-card | live capture-card |
|---|---|---|---|
| open_strip_mean_max | 0.35 | 0.1 | 0.1 |
| open_flow_peak_min | 10 | 10 | 30 |
| close_strip_mean_max | 0.475 | 0.15 | 0.15 |
| close_flow_peak_min | 5 | 5 | 25 |

## §D.3 Active-fraction summary on LIVE corpus

| params | rd | ad | replay | noise | score |
|---|---|---|---|---|---|
| v1 production | 0.000 | 0.018 | 0.010 | 0.000 | 0.000 |
| live optimum | 0.000 | 0.000 | 0.002 | 0.000 | 0.000 |

Δ rd_active_frac (live optimum − v1) = **+0.000**. §13 §C2 ship gate is ≥ 0.15.
