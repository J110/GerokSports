# Motion-Signal Baseline Feasibility Study

_Generated 2026-05-03 from 105/105 clips_

## §1 Methodology

- 105 manually labeled `delivery_window.mp4` clips from sessions `20260420_202239` (36) and `20260421_195050` (69).
- Each video decoded with OpenCV; frames downsampled so neither dim exceeds 640×360 before optical flow.
- Three per-frame-pair signals on consecutive grayscale frames:
  - **A. Dense optical flow magnitude** — `cv2.calcOpticalFlowFarneback`, mean of pixelwise √(dx²+dy²).
  - **B. Frame difference** — mean of `cv2.absdiff(prev, cur)` over the full grayscale frame.
  - **C. Score-strip stability** — same absdiff restricted to the bottom 12 % rows of the frame.
- Color-inversion of the broadcast feed is irrelevant: all signals operate on grayscale magnitudes only.
- Bottom 12 % strip is used as a universal default ROI; per-broadcast strip geometry is not modeled.
- Per-clip aggregates: mean/std/p25/p50/p75/p95/max plus peak_count (samples above median+1σ) and Shannon entropy over 16-bin histogram.
- 

## §2 Per-class aggregate distributions

| label | n | flow_mean | diff_mean | strip_mean | flow_peak_count | strip_p95 |
|---|---|---|---|---|---|---|
| real_delivery | 83 | 2.643 (p25 1.821 / p75 3.459) | 7.312 (p25 5.639 / p75 8.914) | 0.095 (p25 0.032 / p75 0.124) | 57.482 (p25 44.000 / p75 67.500) | 0.307 (p25 0.099 / p75 0.431) |
| replay | 5 | 2.973 (p25 2.635 / p75 3.615) | 8.130 (p25 8.395 / p75 8.852) | 0.271 (p25 0.226 / p75 0.340) | 45.600 (p25 39.000 / p75 61.000) | 0.725 (p25 0.525 / p75 0.930) |
| ad | 3 | 2.127 (p25 1.877 / p75 2.591) | 8.586 (p25 7.515 / p75 9.290) | 0.250 (p25 0.153 / p75 0.375) | 32.000 (p25 13.500 / p75 44.000) | 0.691 (p25 0.362 / p75 1.036) |
| noise | 14 | 2.647 (p25 1.561 / p75 3.566) | 7.740 (p25 6.344 / p75 9.497) | 0.092 (p25 0.051 / p75 0.118) | 34.357 (p25 18.000 / p75 45.000) | 0.263 (p25 0.138 / p75 0.229) |

## §3 Best-signal-per-pair AUC (real_delivery vs each non-delivery class)

| comparison | best signal | AUC | direction | n_pos | n_neg |
|---|---|---|---|---|---|
| real_delivery vs ad | diff_std | 0.988 | pos_low | 83 | 3 |
| real_delivery vs replay | strip_mean | 0.911 | pos_low | 83 | 5 |
| real_delivery vs noise | flow_peak_count | 0.815 | pos_high | 83 | 14 |


<details><summary>All signals × all comparisons</summary>

| signal | vs ad | vs replay | vs noise |
|---|---|---|---|
| flow_mean | 0.647 (pos_high) | 0.619 (pos_low) | 0.524 (pos_high) |
| flow_std | 0.518 (pos_low) | 0.641 (pos_low) | 0.610 (pos_high) |
| flow_p50 | 0.594 (pos_high) | 0.530 (pos_high) | 0.526 (pos_low) |
| flow_p95 | 0.639 (pos_high) | 0.677 (pos_low) | 0.591 (pos_high) |
| flow_peak_count | 0.739 (pos_high) | 0.692 (pos_high) | 0.815 (pos_high) |
| diff_mean | 0.679 (pos_low) | 0.627 (pos_low) | 0.567 (pos_low) |
| diff_std | 0.988 (pos_low) | 0.687 (pos_low) | 0.633 (pos_high) |
| diff_p50 | 0.622 (pos_low) | 0.516 (pos_high) | 0.542 (pos_low) |
| diff_p95 | 0.518 (pos_low) | 0.665 (pos_low) | 0.512 (pos_high) |
| diff_peak_count | 0.972 (pos_high) | 0.530 (pos_high) | 0.738 (pos_high) |
| strip_mean | 0.655 (pos_low) | 0.911 (pos_low) | 0.531 (pos_low) |
| strip_std | 0.643 (pos_low) | 0.648 (pos_low) | 0.575 (pos_low) |
| strip_p95 | 0.618 (pos_low) | 0.860 (pos_low) | 0.518 (pos_high) |

</details>

Direction `pos_high` = real_delivery scores higher; `pos_low` = real_delivery scores lower. AUC ≥0.5 by construction (we report the side that separates).

## §4 Visual inspection summary

- Per-clip waveforms saved to `files/scripts/motion_baseline/plots/<label>/<session>__<clip>.png`.
- Distribution boxplot saved to `files/scripts/motion_baseline/distributions.png`.
- The dominant feature on inspection: real_delivery clips show a multi-second high-flow burst centered on the bowler's run-up, while ads and replays exhibit sustained or oscillating high motion across the entire clip; noise clips are typically flatter than deliveries.
- Strip-diff is near-zero for nearly every real_delivery clip and visibly elevated when graphics overlay or replay transitions occur, but a fraction of real_delivery clips have transient strip-diff spikes from score-update animations.

## §5 Combined-signal exploration

Compared three combiners against the best single signal per pairing:

1. **Sum of z-scores** (flow_mean + diff_mean + strip_p95) — quick fusion sanity check.
2. **AND-rule** — flow_mean above its real_delivery median AND strip_p95 below its real_delivery 75th percentile.
3. **Logistic regression** on 8 z-scored aggregates, leave-one-out cross-validation, AUC on held-out scores.

| comparison | best single AUC | sum-zscore AUC | AND-rule TPR/FPR | logistic LOO AUC |
|---|---|---|---|---|
| real_delivery vs ad | 0.988 | 0.655 | 0.31/0.00 | 0.747 |
| real_delivery vs replay | 0.911 | 0.720 | 0.31/0.00 | 0.887 |
| real_delivery vs noise | 0.815 | 0.542 | 0.31/0.43 | 0.804 |

Interpretation: combiners are computed but only meaningfully exceed the best single signal when the underlying features are not redundant. See the verdict in §6.

## §6 Verdict

Best single-signal AUC across all class pairings: **0.988**.

Best combined-signal AUC (logistic on z-scored aggregates, leave-one-out): **0.887**.


**(a) Strong separation — promising for AI-free detection. Next: threshold-based detector vs Scout baseline.**
