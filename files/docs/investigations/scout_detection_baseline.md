# Scout Detection Baseline (Path A regression set)

Date: 2026-05-03
Author: agent (regression baseline for prompt-sharpening work)
Inputs:
- `files/logs/deliveries/20260420_202239/labels.csv` (36 clips)
- `files/logs/deliveries/20260421_195050/labels.csv` (69 clips)
- 105 manually labeled clips total; 0 `skip` rows.
Artifacts:
- `files/scripts/path_a_baseline/run_scout_baseline.py`
- `files/scripts/path_a_baseline/scout_results.jsonl` (1851 frame rows, 0 errors)
- `files/scripts/path_a_baseline/clip_aggregates.csv`
- `files/scripts/path_a_baseline/frames/<session>/<clip>/fNNN.jpg` (extracted frame cache)

---

## §1 What Scout is

- Module: `files/eyes/open_scout.py`, class `OpenScout`.
- Model: `meta-llama/llama-4-scout-17b-16e-instruct` via `groq.AsyncGroq`.
- Entry point: `await OpenScout(...).classify(frame_bgr_np, timestamp, frame_idx=…)` →
  `OpenScoutResult(timestamp, frame_class, raw_description) | None`. Failures (timeout,
  encode, 429) return `None` and are logged on the instance.
- Prompt: frozen `OPEN_PROMPT` (lines 53–69) — open-prose description, *not* a
  classification request. Rule-v2 keyword classifier in
  `eyes.open_scout_classify.classify_full` collapses the prose to one of
  `{action, replay, ad, umpire, other}`.
- Production call site: `files/test_pipeline.py:6557-6606` — fire-and-forget,
  rate-gated to 1 fps on active views, 0.5 fps on ambiguous.

## §2 Methodology

- Frame cadence 1.0 s (matches `OPEN_SCOUT_ACTIVE_INTERVAL_S`). Frames extracted
  with cv2 `VideoCapture`, saved as JPEG q90 to a per-clip cache directory so
  re-runs don't re-extract.
- Scout invoked through the unmodified `OpenScout.classify` path — same prompt,
  same model, same rule-v2 classifier as production.
- Concurrency 4 → 1 fallback after Groq TPM 429s on the first sweep
  (300k tokens/min limit; concurrency 4 saturated it). Final pass at
  concurrency 1 cleared all 451 retried frames with zero errors.
- 1851 frames classified end-to-end; 0 final errors.
- Per-frame latency (concurrency 1, after retry): p50 1543 ms, p90 2999 ms,
  mean 1602 ms.

## §3 Per-clip aggregate distributions

Clip counts and Scout `action_ratio` / `max_consecutive_action` stats by
manual label:

| manual_label  | n  | mean ratio | p25  | p50  | p75  | mean run | max run |
|---------------|----|------------|------|------|------|----------|---------|
| ad            | 3  | 0.211      | 0.13 | 0.25 | 0.25 | 1.33     | 2       |
| noise         | 14 | 0.346      | 0.13 | 0.32 | 0.55 | 2.50     | 6       |
| replay        | 5  | 0.516      | 0.33 | 0.50 | 0.70 | 6.00     | 16      |
| real_delivery | 83 | 0.569      | 0.43 | 0.57 | 0.71 | 6.52     | 13      |

Per-frame Scout-class counts grouped by manual label (n = total frames):

| manual_label  | n    | action       | other        | replay   | umpire  | ad |
|---------------|------|--------------|--------------|----------|---------|----|
| real_delivery | 1566 | 879 (56%)    | 643 (41%)    | 21 (1%)  | 23 (1%) | 0  |
| replay        | 81   | 43 (53%)     | 36 (44%)     | 1 (1%)   | 1 (1%)  | 0  |
| noise         | 161  | 54 (34%)     | 100 (62%)    | 6 (4%)   | 1 (1%)  | 0  |
| ad            | 43   | 9 (21%)      | 33 (77%)     | 1 (2%)   | 0       | 0  |

## §4 Class separation analysis

- **`real_delivery` vs `replay`**: per-frame Scout output is statistically
  indistinguishable. Replay clips fire 53% action vs 56% on deliveries; max
  consecutive action runs are 6.0 mean / 16 max for replays vs 6.5 / 13 for
  deliveries. The `replay` Scout class itself fires on **1 / 81** replay
  frames (1.2%). The rule-v2 classifier is not detecting replays.
- **`real_delivery` vs `noise`**: noticeable gap — 0.569 vs 0.346 mean ratio
  and 6.5 vs 2.5 mean max-run. Noise is mostly `other` (62%).
- **`real_delivery` vs `ad`**: ads almost never produce `action` (21% per
  frame, 0.21 ratio per clip), but only 3 ad clips so the sample is too small
  to draw a hard conclusion. The `ad` Scout class fires **0 times across
  1851 frames** — the rule-v2 ad keyword path is dead.
- **Class collapse**: Scout effectively emits a binary action / other signal
  with rare umpire/replay tokens. 985 + 812 = 1797 / 1851 frames (97%) land
  in {action, other}.

## §5 Best-threshold sweep

`real_delivery` is positive class; `replay`+`ad`+`noise` is negative.

Threshold on `action_ratio`:

| T   | TP | FN | FP | TN | P    | R    | F1   |
|-----|----|----|----|----|------|------|------|
| 0.0 | 83 | 0  | 22 | 0  | 0.79 | 1.00 | 0.88 |
| 0.1 | 83 | 0  | 19 | 3  | 0.81 | 1.00 | 0.90 |
| 0.2 | 82 | 1  | 15 | 7  | 0.85 | 0.99 | **0.91** |
| 0.3 | 75 | 8  | 11 | 11 | 0.87 | 0.90 | 0.89 |
| 0.5 | 54 | 29 | 7  | 15 | 0.89 | 0.65 | 0.75 |

Threshold on `max_consecutive_action`:

| K   | TP | FN | FP | TN | P    | R    | F1   |
|-----|----|----|----|----|------|------|------|
| 1   | 83 | 0  | 19 | 3  | 0.81 | 1.00 | 0.90 |
| 2   | 82 | 1  | 16 | 6  | 0.84 | 0.99 | 0.91 |
| 3   | 80 | 3  | 11 | 11 | 0.88 | 0.96 | **0.92** |
| 4   | 74 | 9  | 7  | 15 | 0.91 | 0.89 | 0.90 |
| 5   | 64 | 19 | 4  | 18 | 0.94 | 0.77 | 0.85 |

Best operating point: `max_consecutive_action ≥ 3` → F1 0.92 (P 0.88, R 0.96).
`action_ratio ≥ 0.2` is essentially tied at F1 0.91. `max_consecutive_action`
gives slightly better separation at higher thresholds because noise frames
rarely chain into 3+ consecutive `action` calls, but it cannot separate
`real_delivery` from `replay`. **All 5 replay clips have max_run ≥ 4.**

## §6 Verdict

The current Scout signal is **not sufficient** for the delivery-vs-replay
problem and prompt sharpening alone (Path A) is unlikely to fix it.
Mixed verdict by question:

1. **Delivery vs noise/ad** — solvable today. F1 0.91-0.92 with simple
   `max_consecutive_action ≥ 3` filter. No prompt change needed; better
   aggregation (already implemented in `SpanAggregator`) is enough.
2. **Delivery vs replay** — *not* solvable with the current prompt+classifier.
   The open-prose description for replay frames does not mention "replay",
   "slow-motion", or "REPLAY graphic" in the samples checked; the prose just
   describes the underlying cricket action. Per-clip stats are statistically
   identical (0.569 vs 0.516 mean ratio; 6.5 vs 6.0 mean max-run).
3. **Class taxonomy collapse** — `ad` fires 0/1851, `replay` fires 29/1851
   (and only 1/81 on replay clips). The rule-v2 keyword classifier has
   effectively degraded to binary `action` vs `other`.

Recommended next step (prioritised):

- **Path A iteration (cheap, do first)**: rewrite `OPEN_PROMPT` to explicitly
  ask Scout to look for REPLAY/Slo-Mo broadcaster overlays, super-slow-motion
  visual cues, and slow ball physics; in parallel, audit `open_scout_classify`
  rule-v2 to confirm it actually has replay/ad keyword paths. If the
  description starts naming "REPLAY graphic" reliably the keyword classifier
  may already pick it up. Estimate the lift on the same 105-clip set before
  shipping.
- **Path B (fallback)**: a small local CNN trained on these labels is the
  realistic plan if Path A iteration on the prompt does not move the
  delivery-vs-replay needle. The 105-clip regression set produced here is
  the supervised seed.
- The delivery-vs-noise/ad axis does *not* need either; ship better
  aggregation against the existing signal.
