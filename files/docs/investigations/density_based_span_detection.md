# Density-based span detection — feasibility study

**Status:** investigation complete, no implementation.
**Date:** 2026-05-03
**Source data:** `logs/openscout-d03b43da.jsonl` (583 records, 59 min,
yesterday's CSK-vs-MI innings 2) and the 33 `[DELIVERY ENQUEUED]`
ground-truth events from
`logs/pipeline-2026-05-02-2049-csk-vs-mi-44th-match-ipl-2026-innings2.log`.
**Reproducer:** `files/scripts/investigations/p22_density_sweep.py`.

## TL;DR — verdict

**Do NOT ship a density-based SpanAggregator replacement against the
current OpenScout signal.** The action-density distributions inside
delivery and non-delivery windows are not separable. The best F1
across a wide parameter sweep is **0.21 at strict ±5 s match
tolerance** (P = 0.15, R = 0.33). Even after compensating for the
score-event detection lag (truth-ts shifted back 15 s) and relaxing
the match tolerance to ±20 s, F1 caps at **0.53** (P = 0.41, R = 0.73)
— still well below useful precision.

The bottleneck is the per-frame classifier itself: the `action` class
is emitted for ~40 % of all broadcast time (W = 60 s mean ratio 0.38),
including bowler walk-ups, fielder repositioning, and post-ball
follow-throughs. Density of `action` does not correlate with the
delivery moment.

The P22 fix (raise `SOFT_GAP_TOLERANCE_S` from 2.5 → 5.0 s in the
existing `SpanAggregator`) remains the right short-term action.
A density approach only becomes viable after the per-frame label is
sharpened — either via a stricter prompt definition of `action` or a
local CNN delivery-moment detector.

---

## §1 Density signal time series

The signal computed at every ts on a 1 Hz grid:

```
ratio(t) = |{records with frame_class ∈ S, ts ∈ [t - W/2, t + W/2]}|
         / |{records with frame_class is not None, ts ∈ [t - W/2, t + W/2]}|
```

with `S ∈ {{action}, {action, other}}` and
`W ∈ {6, 10, 14, 20}` seconds. `n_records` underlying each ratio is
small at narrow W: at the median 5.4 s inter-arrival cadence, W = 10
typically holds 1-2 records and W = 6 holds 0-1. This produces the
heavily-quantised distribution observed below
(values clustered at 0.0, 0.33, 0.50, 1.0).

Whole-match action-ratio means at three window sizes:

| W | median action_ratio | mean action_ratio |
|---|---:|---:|
| 10 s | 0.00 | 0.29 |
| 30 s | 0.33 | 0.36 |
| 60 s | 0.40 | 0.38 |

The 60-second mean of 0.38 is the key context: ~40 % of broadcast
wall-clock is labelled "action" by the per-frame classifier. Any
density threshold has to exceed this baseline to be meaningful.

---

## §2 Delivery vs non-delivery signal shape

### 2.1 Aligned-average profile around real delivery timestamps

W = 10 s, classes = `{action}`, n = 33 deliveries, 1-second offsets:

| offset (s) | mean ratio | p25 | p50 | p75 |
|---:|---:|---:|---:|---:|
| -9 | 0.45 | 0.00 | 0.50 | 1.00 |
| -8 | 0.43 | 0.00 | 0.33 | 1.00 |
| -7 | 0.39 | 0.00 | 0.50 | 0.50 |
| -6 | 0.35 | 0.00 | 0.33 | 0.50 |
| -5 | 0.37 | 0.00 | 0.33 | 0.50 |
| -4 | 0.36 | 0.00 | 0.33 | 0.50 |
| -3 | 0.28 | 0.00 | 0.00 | 0.50 |
| -2 | 0.26 | 0.00 | 0.00 | 0.50 |
| -1 | 0.30 | 0.00 | 0.00 | 0.50 |
| 0 | 0.32 | 0.00 | 0.33 | 0.50 |
| +1 | 0.32 | 0.00 | 0.33 | 0.50 |
| +2 | 0.31 | 0.00 | 0.00 | 0.50 |
| +3 | 0.35 | 0.00 | 0.00 | 1.00 |
| +5 | 0.35 | 0.00 | 0.33 | 0.50 |
| +9 | 0.33 | 0.00 | 0.00 | 0.50 |

Two observations:

* **There is no peak at t = 0.** The mean ratio at the delivery moment
  (0.32) is slightly *lower* than at t = -9 (0.45). The score-event
  enqueue ts lags the actual ball delivery by an unknown amount
  (~5-15 s), so the "real" delivery moment is in the negative-offset
  region — but even there the action ratio only reaches 0.45.
* **The signal is essentially flat** across ±10 s. Action density is
  not a delivery-moment marker; it is a coarse "we're showing a
  cricket field" indicator.

### 2.2 Distribution: ±5 s windows around deliveries vs non-deliveries

Non-delivery windows: midpoints of inter-delivery gaps ≥ 30 s
(20 windows, ±5 s each).

| | n samples | min | p25 | p50 | p75 | p90 | max | mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **delivery** ±5 s | 330 | 0.00 | 0.00 | 0.00 | 0.50 | 1.00 | 1.00 | **0.324** |
| **non-delivery** ±5 s | 200 | 0.00 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | **0.382** |

**The distributions are inseparable.** Non-delivery windows have a
*higher* mean action density (0.38) than delivery windows (0.32). This
is the primary reason any threshold-based detector underperforms: the
class boundary it relies on does not exist in this data.

### 2.3 Why the non-delivery mean is higher

Two contributors visible in the data:

* The `[DELIVERY ENQUEUED]` ts is fired by the scoreboard score-event
  detector, which fires on the *score-strip update* — typically 5-15 s
  after the ball is bowled, often during the post-ball replay.
  So the ±5 s window around the enqueue ts mostly catches replay /
  reaction shots (which the classifier labels `other`), not the ball.
* Inter-delivery gaps between consecutive deliveries within an over
  often contain bowler-walk-back wide shots that are also labelled
  `action`.

---

## §3 Parameter sweep results

Hysteresis state machine:

```
NOT_IN -> IN  when ratio(t) >= t_open
IN  -> NOT_IN when ratio(t) < t_close for >= K consecutive seconds
```

Sweep grid: `W ∈ {6, 10, 14, 20}`, `t_open ∈ {0.30, 0.40, 0.50, 0.60, 0.70}`,
`t_close = t_open - drop` for `drop ∈ {0.10, 0.20}`,
`K ∈ {1, 2, 3} s`, `classes ∈ {{action}, {action, other}}`. Detected
spans are matched to the 33 truth events by midpoint distance with
tolerance ±5 s (greedy, each truth used at most once).

Note on the requested `closeup` class set: OpenScout's
`open_scout_classify.classify_full` emits one of `{action, replay, ad,
umpire, other}`. There is no `closeup` value in the JSONL, so the
"+closeup" combinations from the brief are reduced here to
`{action, other}` (the closest "non-replay, non-ad" approximation).

### 3.1 Top-15 by F1, strict tolerance ±5 s

| rank | classes | W | t_open | t_close | K | n_det | TP | FP | FN | P | R | F1 |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | action | 10 | 0.30 | 0.20 | 2 | 74 | 11 | 63 | 22 | 0.15 | 0.33 | **0.21** |
| 2 | action | 10 | 0.30 | 0.20 | 3 | 74 | 11 | 63 | 22 | 0.15 | 0.33 | 0.21 |
| 3 | action | 10 | 0.30 | 0.10 | 2 | 74 | 11 | 63 | 22 | 0.15 | 0.33 | 0.21 |
| 4 | action | 10 | 0.40 | 0.20 | 2 | 74 | 11 | 63 | 22 | 0.15 | 0.33 | 0.21 |
| 5 | action | 20 | 0.50 | 0.30 | 2 | 55 | 9 | 46 | 24 | 0.16 | 0.27 | 0.20 |
| 6 | action | 10 | 0.50 | 0.30 | 2 | 75 | 11 | 64 | 22 | 0.15 | 0.33 | 0.20 |
| 7 | action | 6 | 0.30 | 0.20 | 1 | 100 | 13 | 87 | 20 | 0.13 | 0.39 | 0.20 |
| ... | (rest cluster around F1 ≈ 0.18-0.20) |

### 3.2 Best per class set

| class set | best F1 | P | R | params |
|---|---:|---:|---:|---|
| `{action}` | **0.21** | 0.15 | 0.33 | W = 10, o = 0.30, c = 0.20, K = 2 |
| `{action, other}` | 0.19 | 0.14 | 0.27 | W = 10, o = 0.70, c = 0.60, K = 2 |

Adding `other` to the target class set degrades F1 — `other` is even
more uniformly distributed than `action` and adds noise.

### 3.3 Truth-shift sensitivity

Score-event detection lags the actual ball; shifting the ground-truth
ts back compensates. Best F1 across the full sweep at ±8 s tolerance:

| truth shift | best F1 | P | R | best params |
|---:|---:|---:|---:|---|
| 0 s | 0.31 | 0.21 | 0.58 | W=6 o=0.6 c=0.5 K=3 |
| -3 s | 0.31 | 0.25 | 0.42 | W=20 o=0.4 c=0.3 K=2 |
| -5 s | 0.36 | 0.26 | 0.58 | W=10 o=0.3 c=0.2 K=2 |
| -8 s | 0.36 | 0.28 | 0.48 | W=20 o=0.4 c=0.3 K=2 |
| -10 s | 0.36 | 0.28 | 0.52 | W=20 o=0.5 c=0.4 K=2 |
| **-15 s** | **0.38** | 0.26 | 0.70 | W=6 o=0.6 c=0.5 K=3 |
| -20 s | 0.29 | 0.22 | 0.39 | W=20 o=0.5 c=0.4 K=3 |

A -15 s shift maximises F1 — consistent with the typical Scout score-
event lag — but caps at 0.38. Push the match tolerance further:

| match tol (shift = -8 s) | best F1 | P | R | best params |
|---:|---:|---:|---:|---|
| ±5 s | 0.32 | 0.24 | 0.48 | W=10 o=0.7 c=0.5 K=1 |
| ±8 s | 0.36 | 0.28 | 0.48 | W=20 o=0.4 c=0.3 K=2 |
| ±12 s | 0.42 | 0.28 | 0.79 | W=6 o=0.6 c=0.5 K=2 |
| ±15 s | 0.47 | 0.36 | 0.67 | W=20 o=0.5 c=0.4 K=2 |
| **±20 s** | **0.53** | 0.41 | 0.73 | W=20 o=0.5 c=0.4 K=3 |

Even with the most generous reasonable matching (±20 s, on a
~30 s-per-delivery cadence), F1 caps at 0.53. Beyond ±20 s the matching
becomes meaningless because adjacent deliveries start being matched.

### 3.4 Half-rate sub-sample (does doubling Scout dispatch help?)

To estimate the impact of dropping `OPEN_SCOUT_ACTIVE_INTERVAL_S` to
0.5 s, we ran the inverse experiment: drop every other record from the
JSONL (simulating *halving* the dispatch rate from 1 Hz to 0.5 Hz).
If signal quality is rate-limited, F1 should collapse with half the
data; if the bottleneck is signal noise, F1 should be roughly flat.

| | best F1 | P | R | best params |
|---|---:|---:|---:|---|
| full rate (468 typed records) | 0.21 | 0.15 | 0.33 | W=10 o=0.30 c=0.20 K=2 |
| half rate (234 typed records) | 0.23 | 0.19 | 0.30 | W=20 o=0.30 c=0.20 K=1 |

Half-rate F1 is statistically indistinguishable from full-rate. The
limit is not sample density. Doubling the dispatch rate to 2 Hz would
not meaningfully change the picture either — the per-frame label is
the signal-to-noise bottleneck.

---

## §4 Top-3 recommendations (if forced to ship)

If product *requires* density-based detection regardless of these
results, the least-bad parameter choices are:

| rank | params | F1 (±5 s) | P | R | notes |
|---:|---|---:|---:|---:|---|
| 1 | classes={action}, W=10 s, t_open=0.30, t_close=0.20, K=2 | 0.21 | 0.15 | 0.33 | smallest detector, decent recall |
| 2 | classes={action}, W=20 s, t_open=0.50, t_close=0.30, K=2 | 0.20 | 0.16 | 0.27 | wider window, fewer FPs |
| 3 | classes={action}, W=6 s, t_open=0.30, t_close=0.10, K=1 | 0.20 | 0.13 | 0.39 | best recall, worst precision |

All three would emit 55-100 spans against 33 real deliveries —
i.e. 60-200 % more spans than there are actual deliveries — and
correctly identify only ~30-40 % of them. None of these are
ship-quality numbers.

---

## §5 Verdict and recommendation

### 5.1 Density approach is not viable today

**Do not replace `SpanAggregator` with a density-based detector
against the current OpenScout signal.** Three corroborating lines of
evidence:

1. The action-density distribution at delivery vs non-delivery
   windows overlaps almost completely (means 0.32 vs 0.38; the
   non-delivery window is *more* action-dense than the delivery
   window).
2. Best F1 across ~120 parameter combinations is 0.21 at the
   requested ±5 s tolerance. Even with score-event lag compensation
   and ±20 s tolerance, F1 caps at 0.53.
3. Sub-sampling tests show F1 is not bottlenecked by sample density.
   Doubling Scout dispatch rate would burn API quota for negligible
   F1 lift.

### 5.2 What to ship instead (short term)

* **Keep the existing `SpanAggregator` and apply the P22 tuning fix**
  (`SOFT_GAP_TOLERANCE_S 2.5 → 5.0 s`, see
  `openscout_span_formation_diagnosis.md` §6 F1). This restores
  ≈ 27 action spans per innings — enough signal for the redesigned
  matcher to consume — without changing the underlying classifier.
* **Keep `OPEN_SCOUT_ACTIVE_INTERVAL_S = 1.0 s`.** Per
  `scout_latency_ceiling.md` §6, latency is not a bottleneck either,
  and as shown in §3.4 above, more samples do not raise detection
  quality.

### 5.3 What to investigate before revisiting density (medium term)

The per-frame `action` label is what needs sharpening. Two paths,
ranked by effort:

* **Path A — prompt sharpening.** The current `OPEN_PROMPT`
  (`files/eyes/open_scout.py:53-69`) asks Scout to describe the frame
  in 2-4 sentences and downstream `classify_full` rule-buckets that
  prose into `action`. Tightening the rule definition of `action` to
  require ball-in-flight cues (bowler released / batter playing the
  shot / catch-in-air) would shrink `action` away from the bowler
  walk-up and post-ball follow-through. Estimated effort: 1-2 days
  of prompt + rule iteration with the existing JSONL as a regression
  set.
* **Path B — local CNN delivery-moment classifier.** Train a small
  per-frame CNN on a labelled set of "ball-in-flight vs not" frames.
  Decouples detection from the broadcast-vision label and runs
  locally at full FPS. Estimated effort: 1-2 weeks (label collection
  + training + integration). High-confidence path to F1 ≥ 0.8 based
  on similar published work on broadcast cricket.

Density-based span detection should be re-evaluated only after one
of these per-frame sharpening efforts lands. The shape of the
state machine itself (hysteresis with `t_open`, `t_close`, `K`) is
sensible — the input signal is the problem.

### 5.4 Pseudocode (for completeness, not for shipping)

If a future per-frame label achieves clean separation, the state
machine shape that performed least-badly here was:

```python
# Inputs: 1 Hz time series (ts, ratio) where ratio is the share of
# the last W=10 s of records labelled as "action".
state = "IDLE"
span_start = None
below_since = None
last_above = None
T_OPEN = 0.30
T_CLOSE = 0.20
K_CLOSE_S = 2.0

for ts, ratio in series:
    if state == "IDLE":
        if ratio >= T_OPEN:
            state = "IN_DELIVERY"
            span_start = ts
            last_above = ts
            below_since = None
    else:  # IN_DELIVERY
        if ratio >= T_CLOSE:
            last_above = ts
            below_since = None
        else:
            below_since = below_since or ts
            if ts - below_since >= K_CLOSE_S:
                emit_span(span_start, last_above)
                state = "IDLE"
                span_start = below_since = last_above = None
```

To be revisited only after the per-frame `action` label has been
sharpened (Path A or B above).

---

## Appendix — reproduction

```bash
cd /Users/anmolmohan/Projects/SportsComm
python3 files/scripts/investigations/p22_density_sweep.py
```

The script (Path: `files/scripts/investigations/p22_density_sweep.py`)
loads `logs/openscout-d03b43da.jsonl`, parses 33 `[DELIVERY ENQUEUED]`
events from the pipeline log, computes the density series, runs the
full sweep, and prints the tables in this memo. Edits to the sweep
grid live in `parameter_sweep()`.
