# YouTube Replay — Delivery Detection Quality Analysis

> **2026-05-02 14:18 — Verification pass (re: user observation that the UI ticked ball-by-ball).**
> Re-counted with corrected grep (`ball_event=[A-Za-z0-9_]+` — original missed `1_RUNS`).
> Corrected ball-event count is **11**, not 8. Three `1_RUNS` events were dropped by the
> previous pattern. See §0 below for the verification, §6 for the corrected lever ranking.
> The headline conclusion (gate-driven freeze on overs 1.0 → 4.0) stands; the user's
> "ticking ball-by-ball" observation is consistent with what they saw during over 1
> (5 / 6 ticks captured), and reflects a real 3 min UI freeze that followed.

---

## §0 Verification (2026-05-02 14:18)

The previous count of "8 ball events" was wrong. The grep pattern
`ball_event=(DOT|ONE|TWO|THREE|FOUR|SIX|WICKET)` did not include `1_RUNS` /
`N_RUNS`, which is the actual event-type label the pipeline emits for run-scoring
deliveries. Re-running with `ball_event=[A-Za-z0-9_]+`:

| Event type | Count |
| --- | --- |
| `1_RUNS` | 3 |
| `DOT` | 2 |
| `EXTRA` | 4 |
| `MULTI_BALL` | 1 |
| `WICKET` | 1 |
| **Total ball events** | **11** |

The 11 events line up 1:1 with frames F130, F135, F140, F147, F157, F179, F209,
F226, F231, F331, F413. Of those, F179 (`MULTI_BALL`) does not produce an
enqueue, leaving exactly **10 enqueues** (d001–d010) — matches `[DELIVERY ENQUEUED]`
log count and the on-disk `files/logs/deliveries/20260502_122517/d*` directories.

**Within-window classification rate: 10 / 10 = 100%** (every enqueue produced a real,
non-em-dash ball_event). The classifier never failed to classify a window it was given.

### Reconciling with the user's observation

The state-machine committed-state surface (which is what the WS UI receives via
`broadcast_state`) progressed through these states during the run:

```
overs:    0.1 → 0.2 → 0.3 → 0.4 → 0.5 → 1.0 → 2.4 → 4.0      (8 unique)
score:    1   → 2   → 3   → 4   → 11  → 12  → 13  → 17 → 21  (9 unique)
wickets:  0   → 1                                              (2 unique)
```

This rules out **path (a)** (UI driven by a non-state-machine source): there is no
"DIRECT bypass" of the gate. The `[DIRECT]` path shares `SCORE-INF-GATE-DIRECT`
(test_pipeline.py:8761) — zero `SCORE-INF-GATE-DIRECT` rejections fired this run
because the DIRECT path was just re-asserting the same already-committed score on
every frame (idempotent confirmation, not a new commit). The 417 `[DIRECT]` log
lines are these idempotent re-confirmations, not unique state changes.

It rules out **path (c)** as the *headline* explanation but confirms **path (c)
partially**: the 8 → 11 correction is real but doesn't change the diagnosis.

It confirms **path (b)**: the pipeline genuinely missed deliveries between 1.0
and 4.0. The user's "ticking ball-by-ball" observation matches what they would
have seen during the **first over** (5 ticks for balls 0.2 → 1.0, every legal
ball captured). After 1.0 the UI froze for ~3 minutes (gates rejected every
proposal), then jumped 1.0 → 2.4 (one MULTI_BALL composite event covering
~6 real balls), then froze again until 4.0. If the user looked away during
overs 1.x–3.x they would not have noticed the freeze.

### Corrected detection ratios

| Ratio | Original | Corrected |
| --- | --- | --- |
| `enqueues / expected_balls` | 10 / 30 ≈ 33% | 10 / 30 ≈ 33% (unchanged) |
| `ball_events / expected_balls` | 8 / 30 ≈ 27% | **11 / 30 ≈ 37%** |
| `effective ball coverage` (incl. ~6 from `MULTI_BALL`) | n/a | **~16 / 30 ≈ 53%** |
| `within-window classification` | 8 / 10 = 80% | **10 / 10 = 100%** |

### Surface-coverage clarification

UI surface coverage and classifier output are the **same surface** (both gated by
the same state-machine commits). The user did not observe a higher UI tick rate
than the ball_event log line count — they observed a perfect first over followed
by an undetected freeze.

---

**Date:** 2026-05-02
**Trace:** `logs/trace/866ce150.jsonl` (174 SCOREBOARD frames)
**Pipeline log:** `logs/pipeline-2026-05-02-1225-wi-vs-rsa-2nd-t20i-…log` (8030 lines)
**Deliveries dir:** `files/logs/deliveries/20260502_122517/` (10 enqueues, `d001`–`d010`)
**Match:** WI vs RSA, 2nd T20I (YouTube replay) — 1st innings, SA batting from 0.0

---

## §1 Run summary

| Metric | Value |
| --- | --- |
| Wall-clock duration | 18.6 min (12:25:31 → 12:44:02) |
| Processed scoreboard frames | 163 SCOREBOARD + 11 GRAPHIC = 174 |
| Mean per-frame processing latency | 2.6 s (range 1.94 – 5.32 s) |
| Earliest broadcast over reached | 0.1 (1 ball already bowled at startup) |
| Latest broadcast over reached | 4.0 (24 legal balls completed) |
| Max `extras_total` observed | 7 |
| **Expected deliveries in window** | **~30** (23 legal balls + ~7 extras) |
| Delivery enqueues | **10** |
| Pipeline `ball_event` lines | **8** (2 DOT + 4 EXTRA + 1 MULTI_BALL + 1 WICKET) |
| Score commits accepted by state machine | 89 |
| Score/extras gate **rejections** | **89** (55 SCORE-INF-GATE + 34 EXTRAS-INF-GATE) |

Pipeline came online at the very start of the innings (first observation `0.1`). Only the first 5 enqueues correspond to discrete real balls (overs 0.2–1.0); the last 5 are all stamped `over=4.0` and were emitted in a 6-min span after a 3-min silence, when the OCR finally re-acquired a coherent score line.

---

## §2 Detection ratios (headline)

| Ratio | Value |
| --- | --- |
| `enqueues / expected_balls` | **10 / 30 ≈ 33%** |
| `pipeline ball_events / expected_balls` | **8 / 30 ≈ 27%** |
| `pipeline ball_events / enqueues` (within-window classification) | **8 / 10 = 80%** |

Per-over breakdown (from `extractor.match_overs` progression):

| Over | Broadcast balls (legal+extras est.) | Enqueues | Ball events |
| --- | --- | --- | --- |
| 0.x (Hosein, 1st over) | 6 + 0 = 6 | 5 (0.2, 0.3, 0.4, 0.5, 1.0) | 3 DOT/1_RUNS-shaped |
| 1.x (S Joseph, 2nd over) | 6 + 0 = 6 | 0 | 0 (single MULTI_BALL straddled here, see §3) |
| 2.x (Hosein, 3rd over) | 6 + 0 = 6 | 0 | 0 |
| 3.x (S Joseph, 4th over) | 6 + ≥3 = ~9 | 0 | 0 |
| 4.0 (start of 5th over, then chaos) | — | 5 | 4 EXTRA + 1 WICKET |
| **Total** | **~30** | **10** | **8** |

The "worst over" is everything between 1.0 and 4.0: **0 enqueues for ~17 deliveries** that the broadcast clearly ran through.

---

## §3 Miss pattern — where detection fell off

The pipeline's enqueue trigger fires on a **score / wicket / over delta committed to the state machine**. Two upstream defects cause the misses:

### 3.1 OCR team-abbreviation thrash

Across 174 SCOREBOARD reads the team abbreviation flipped between **9 different codes**:

| Abbrev | Reads | Notes |
| --- | --- | --- |
| `SA` | 375 | correct |
| `LIONS` | 15 | sponsor / promo strip |
| `LSG` | 9 | IPL graphic mis-read |
| `RCB` | 10 | IPL graphic mis-read |
| `KKR` / `MI` / `JAM` / `PR` / `SOU` | 3+3+2+2+3 | spurious |

Whenever the abbrev jumps, the score string usually goes with it (e.g. `STRIP: LIONS 8-0 (1.2)` at F204 right after `STRIP: SA 11-0 (4.0)` at F185), which trips the consistency gates downstream.

### 3.2 SCORE-INF-GATE / EXTRAS-INF-GATE rejections

The state machine has a defensive rule: a score commit is rejected if `proposed_score < bat_sum + extras` (or if `bat_sum + extras > committed_score`). Across the run:

- **55 SCORE-INF-GATE** rejections (out of ~143 score-bearing proposals → **~38% of proposals dropped**).
- **34 EXTRAS-INF-GATE** rejections.
- Net effect: between 12:31:34 and 12:34:26 (3 min, ~70 frames), the OCR proposed scores `4 → 11 → 8 → 8 → 8 → 9` while bat_sum/extras inferred a floor of `11–15`. **Every single score commit was vetoed**, so the enqueue trigger never fired even though balls 1.1–2.4 were unambiguously visible.

When the gate finally let go at F178 (12:32:54), the score jumped 4 → 11 in one step. The pipeline correctly classified that single event as **`MULTI_BALL`** (one composite ball event covering ~6 real balls), but `MULTI_BALL` does **not** produce an enqueue. The 6-ball gap is invisible downstream.

### 3.3 Late-cluster artefact

`d006`–`d010` are all stamped `over=4.0` but were enqueued at 12:34:26, 12:35:20, 12:35:43, 12:41:30, 12:43:57. All of them ride on `extras` deltas (1, 1, 4, 4) and one wicket — but `extras_total` only ever reached 7. Two of the four EXTRA enqueues are likely **double-counts** of the same broadcast extras burst (the OCR oscillated between extras=4 and extras=7 across multiple frames). At least one of `d009`/`d010` (both `EXTRA runs=4`) is a phantom.

---

## §4 OpenScout vs legacy verdict mix

**All 10 windows used `fallback_pre_event_window` (12.5 s pre-event clip) — neither detector built a real span.**

| Bucket | Count |
| --- | --- |
| Legacy span built (`bowlers_end_span`) | **0 / 10** |
| OpenScout verdict `match` | **0 / 10** |
| OpenScout verdict `no_match` | **10 / 10** |
| Both fallback, `use_open_scout_spans=False` | **10 / 10** |

**Agreement rate:** 100% — both detectors agree on "no span found" on every single delivery. There are zero divergence cases to sample.

### 4.1 Critical sub-finding

OpenScout's per-frame classifier IS firing — `d004` and `d005` carry **3 `bowlers_end / between_play` tags** between them — but its `SpanAggregator` still returns `no_match`. The upstream signal exists; the aggregator is rejecting valid sequences (likely because the cadence (~2.6 s between SCOREBOARD frames) leaves too few consecutive bowler's-end frames to satisfy whatever min-run-length / phase-progression rule the aggregator uses).

Outside those two windows, **0 frames were tagged** by OpenScout. The vision model is flat-out missing the bowler's-end view in 8 of 10 windows.

---

## §7 OpenScout re-analysis (2026-05-02 14:31)

### §7.1 What §4 got wrong

The original §4 grepped `window_debug.json["tags"]` for `bowlers_end` entries
and concluded "OpenScout fired only 3 / 174 frames." That was wrong on three
counts:

1. **`window_debug.json["tags"]` is the LEGACY scout JSON tag stream**, not
   OpenScout's per-frame classifications. Those tags come from
   `DeliveryWindowRecorder._get_tags()` (legacy `camera_view='bowlers_end'` /
   `frame_phase=between_play` taxonomy), which is plumbed in
   `delivery_window_recorder.py:574,_compute_open_scout_window()`.
   OpenScout itself emits `{action, replay, ad, umpire, other}` per
   `eyes/open_scout_classify.py` (binary v2).
2. **OpenScout per-frame classifications are not persisted anywhere**. They
   feed `BallAnalyzer.record_open_classification()` →
   `SpanAggregator.add_classification()` (in-memory only, see
   `ball_analyzer.py:652–667`). Only the per-event matcher verdict
   (`open_scout_verdict`) lands in `window_debug.json`.
3. The `[OPEN-SCOUT-SELECT]` log line — emitted by
   `span_aggregator.py:232/240/252` on every score event — *should* be in
   the pipeline log but isn't. The `span_aggregator` logger writes only to
   the `cricket_logger` rotating file
   (`logs/machine-1-2026-05-02.log`), and that file was truncated and
   re-populated by a later test run starting 13:06. The original
   per-event verdicts are unrecoverable for this run.

### §7.2 Estimated OpenScout invocation count

Reconstructed from `[SCOUT]` lines in the pipeline log (240 total VISION
frames) by simulating `OpenScoutRateGate.allow()` (1 fps for ACTIVE views,
0.5 fps for ambiguous, skip on `cam=ad`):

| Bucket | Count |
| --- | --- |
| Estimated OpenScout invocations (gate-allowed) | **223** |
| Skipped (ad / paused) | 11 |
| Skipped (throttled) | 6 |

So OpenScout was almost certainly invoked **~223 times** during the run —
not "3 / 174". The original two-orders-of-magnitude underestimate is
purely from looking at the wrong field.

### §7.3 Estimated class distribution

We don't have OpenScout's actual per-frame outputs (see §7.1 #2 / #3), but
we can estimate from the legacy Scout's `cam=` and `phase=` distribution
across the same 240 frames, since the binary v2 `action` class tracks
roughly the union of release / runup / shot / post_shot phases:

| Legacy `cam=` value | Frames | Plausible OpenScout class |
| --- | --- | --- |
| `bowlers_end` | 60 | mostly `action` if the bowler is delivering, else `other` |
| `closeup` | 154 | mostly `replay` / `other` |
| `graphic` | 42 | mostly `other` |
| `ad` | 11 | (skipped by gate) |
| `other` | 3 | `other` |
| `None` | 1 | `other` |

| Legacy `phase=` value | Frames |
| --- | --- |
| `between_play` | 182 |
| `graphic` | 21 |
| `release` | 16 |
| `advertisement` | 11 |
| `shot` | 5 |
| `post_shot` | 3 |
| `runup` | 2 |
| `powerplay` | 9 |

**True-action phase frames (release + shot + runup + post_shot) total = 26
across the full 18-min run** (2.3% of wall clock). Applying §11.4's binary
v2 (R≈0.99, P≈0.77), expected OpenScout output is roughly:
`action ≈ 26 (TP) + ~45 (FP from non-action frames) ≈ 70 / 223 ≈ 31%`.
That's in line with the validation-set GT action rate of ~30–40%.

So OpenScout per-frame recall is almost certainly fine. **The bottleneck
is upstream of OpenScout.**

---

## §8 Per-delivery aggregator state at score event

For each enqueue, count of legacy `cam=bowlers_end` and `phase∈{release,
shot, runup, post_shot}` frames inside the SpanAggregator's effective
lookback window `[event_ts − LOOKBACK_S=25s, event_ts − POST_EVENT_EXCLUSION_S=2s]`:

| d | over | event | `cam=bowlers_end` in 25s | true-action phase in 25s |
| --- | --- | --- | --- | --- |
| 1 | 0.2 | DOT | 2 | 2 |
| 2 | 0.3 | 1_RUNS | 2 | 1 |
| 3 | 0.4 | DOT | 1 | 0 |
| 4 | 0.5 | 1_RUNS | 3 | 2 |
| 5 | 1.0 | 1_RUNS | 5 | 2 |
| 6 | 4.0 | EXTRA | **0** | **0** |
| 7 | 4.0 | WICKET | 1 | 1 |
| 8 | 4.0 | EXTRA | **0** | **0** |
| 9 | 4.0 | EXTRA | 1 | 0 |
| 10 | 4.0 | EXTRA | 1 | 1 |

The aggregator's hard constraints are:
`MIN_SPAN_FRAMES=2`, `SAME_CLASS_GAP_TOL=1`, `SOFT_GAP_TOLERANCE_S=2.5s`,
`MIN_ACTION_SPAN_S=2.0s`, `MAX_END_TO_EVENT_GAP_S=8s`.

Crossing those against the per-delivery counts above:

- **d3, d6, d7, d8, d9, d10 (6 / 10)** — fewer than 2 bowlers_end frames in
  the window. Even with perfect OpenScout recall, **no span can form**
  (`MIN_SPAN_FRAMES=2`).
- **d1, d2 (2 / 10)** — exactly 2 BE frames. At gate cadence ≥1 s, two obs
  are typically 4–5 s apart in this run (avg frame interval is ~4 s).
  `SOFT_GAP_TOLERANCE_S=2.5 s` would force-close after the first obs,
  preventing the 2-frame span. **No span forms.**
- **d4, d5 (2 / 10)** — 3 and 5 BE frames respectively. d5 is the only
  delivery with a viable contiguous BE run (5 frames spanning 11 s at
  12:31:18 → 12:31:29), which would form a span — but the legacy `phase`
  on those 5 frames is mostly `between_play`, not release/shot, so
  OpenScout would likely classify them `other`, not `action`. Only the 2
  release-phase frames in d5's window would be candidate `action` obs,
  again falling under `MIN_SPAN_FRAMES`/`SOFT_GAP_TOLERANCE_S`.

### §8.1 Real cause of all 10 `no_match` verdicts

In every case the matcher returns `no_match` because **fewer than 2 frames
in the lookback window are eligible to be classified `action` by OpenScout
under any reasonable interpretation of §11.4's class definition**, and even
where they exist, they are too far apart in wall clock to satisfy
`SOFT_GAP_TOLERANCE_S`.

The root cause is **upstream capture cadence (~4 s mean frame interval
across all frame types)** combined with the broadcast spending most of its
time in non-action phases (182 / 240 = 76% `phase=between_play`). OpenScout
is doing what it should; SpanAggregator's defaults assume ≥1 fps capture
cadence on action moments and that assumption isn't met by this stream.

---

## §9 Bottleneck classification

| Category | Verdict |
| --- | --- |
| **A — per-frame recall low** | NO. Estimated 223 invocations and ~26 true-action frames available; recall isn't the limiter. |
| **B — aggregator filter too strict** | PARTIALLY. `MIN_SPAN_FRAMES=2` + `MIN_ACTION_SPAN_S=2.0s` defeats every 0/1-frame window; loosening to `MIN_SPAN_FRAMES=1` would unlock d3, d7, d9, d10 at the cost of admitting the §11.4 FP_other singletons the constants were chosen to filter. |
| **C — per-frame recall fine, capture cadence too sparse** | **YES (dominant).** Avg frame interval ≈ 4 s (`cadence_ms=2.6 s` mean for SCOREBOARD + slower for ad/closeup); SpanAggregator's `SOFT_GAP_TOLERANCE_S=2.5 s` was sized for ≥1 fps OpenScout and snaps spans before a second action obs lands. |
| **D — aggregator/matcher bug** | NO. Code is consistent with design memo §4–§5. |

---

## §10 Revised lever recommendation

| Lever | Verdict (revised) | Reason |
| --- | --- | --- |
| **3 — Vision model swap (strip OCR)** | **STILL PRIMARY** | The 89 SCORE-INF-GATE rejections (§3.2) cause the 10 / 30 enqueue ratio. Even if OpenScout were perfect, only the existing 10 enqueue events would benefit — the 20 missed deliveries don't even reach the matcher. |
| **1 — `USE_OPEN_SCOUT_SPANS=1`** | **STILL SKIP** | OpenScout returned `no_match` 10 / 10 — there is nothing to switch to on this run. |
| **2 — Delivery-detection prompt** | **STILL SKIP** | Within-window classification was 10 / 10 (§0). Prompt isn't the bottleneck. |
| **NEW — Capture cadence / Scout sampling rate** | **SECONDARY (small change, high leverage)** | Reducing `AdaptiveSleep` minimum interval during `cam=bowlers_end` from ~3 s to ~1 s would let SpanAggregator see ≥3 contiguous action frames per delivery, which is the difference between `no_match` and `open_scout_span`. This is a ~2-line config change and is independent of Lever 3. |
| **NEW — Persist OpenScout per-frame output to a sidecar** | **TOOLING FIX** | The reason this entire investigation took an hour is that OpenScout's per-frame classifications are in-memory only and the `[OPEN-SCOUT-SELECT]` lines went to a rotating file that got overwritten. A `logs/openscout-<session>.jsonl` sidecar with `{ts, frame_class, raw_description}` would let future investigations skip §7's reconstruction. |

### §10.1 Order of operations (revised)

1. **Vision model swap (Lever 3)** — addresses the 89 gate rejections that
   cap enqueues at 10 / 30. Highest payoff.
2. **Capture cadence on `cam=bowlers_end`** — once enqueues climb, this is
   the cheapest fix to make OpenScout's verdict actually useful. Without it,
   `USE_OPEN_SCOUT_SPANS=1` will continue to be moot.
3. **OpenScout sidecar logging** (tooling) — do this before the next test
   run; it costs ~30 LOC and makes the next investigation 5× faster.
4. Re-run; *then* decide whether to tune `SpanAggregator` constants
   (Lever 1B) or flip `USE_OPEN_SCOUT_SPANS=1` (Lever 1).

---

## §6 Lever ranking (revised after §0 verification)

The corrected numbers don't change the diagnosis — the within-window classifier hit
**10 / 10** when given a window, so Lever 2 (prompt) is still moot on this run.
The miss source remains the gate-induced freeze on overs 1.0 → 4.0, which traces back
to OCR thrash (team-abbreviation flips, score-floor inconsistency).

| Lever | Verdict | Why |
| --- | --- | --- |
| **3 — Vision model / strip reading** | **PRIMARY** (unchanged) | Drives gate rejection rate (89 rejections) and OpenScout per-frame tag rate (3 / 174). Fix here unblocks both surfaces simultaneously. |
| **1 — `USE_OPEN_SCOUT_SPANS=1`** | **SKIP** | OpenScout returned `no_match` on 10 / 10 windows; flipping the flag has nothing to switch to. The latent `SpanAggregator` bug (rejects the 3 valid `bowlers_end` tags it did get) only matters once Lever 3 produces enough signal to feed it. |
| **2 — Delivery-detection prompt** | **SKIP** | Within-window classification was 100% (10 / 10 enqueues classified). The prompt isn't being asked the wrong question — it's not the bottleneck on this run. |

## §5 Recommendation — which lever to pull first (original)

### 5.1 The single largest miss source is upstream of all three levers

`SCORE-INF-GATE` + `EXTRAS-INF-GATE` rejected ~38% of score proposals. Even if the delivery-window detectors were perfect, **enqueues can't fire because the score never advances in committed state**. Every miss in the 1.0 → 4.0 gap traces back to OCR thrash, not to window detection.

### 5.2 Lever ranking for THIS run

**Lever 1 — OpenScout `USE_OPEN_SCOUT_SPANS=1`: SKIP for now.**
Zero divergences (both detectors at 0/10). Flipping the flag changes nothing on this stream because OpenScout itself returns `no_match` on every delivery. The `SpanAggregator` is the bottleneck, not the prompt — but fixing it gives 0 → maybe 2 windows on this run, not 10 → 30.

**Lever 2 — Delivery-detection prompt: SKIP.**
Both detectors agree. The prompt isn't being asked the wrong question — it's not being asked at all on 20+ missed balls because no enqueue ever fired.

**Lever 3 — Vision model swap: PRIMARY recommendation.**
Two independent failures point at the same root cause: the current vision model can't read this YouTube broadcast's score strip reliably.
- Team abbreviation correct on only 375 / 432 reads (87%); the other 13% includes IPL/CPL team codes that don't even exist in this match.
- Score / over fields jump arbitrarily (e.g. `(4.0)` ↔ `(1.2)` ↔ `(9)` in adjacent frames).
- OpenScout's per-frame `bowlers_end` tagger fires on only 3 / 174 frames — way below ground-truth occurrence (a bowler's-end view appears for several seconds before every delivery, so should be ~30%+ of frames).

A model swap (or at minimum a prompt-side OCR-stability filter on the strip) should be tested first: if the strip readings stabilise, both the gate-rejection rate and OpenScout's tag rate will rise simultaneously, which fixes the upstream block on enqueues *and* gives the span aggregator something to work with.

### 5.3 Concrete order of operations

1. **Swap or tighten the vision model on the score strip** (Lever 3) and re-run the same YouTube clip. Target: SCORE-INF-GATE rejection rate < 10%, team abbreviation stable.
2. If post-swap the enqueue rate climbs but `open_scout_verdict` is still `no_match` on >50% of windows, **then** debug `SpanAggregator` min-run-length / cadence tolerance (latent Lever 1 work).
3. Re-evaluate the prompt only after (1) + (2) — at that point miss patterns will be specific (e.g. "we miss every leg-bye") instead of "we miss everything."

---

## Appendix — supporting commands

```bash
jq -r '.extractor.match_overs // empty' logs/trace/866ce150.jsonl | sort -V | uniq -c
grep -c '\[DELIVERY ENQUEUED\]' logs/pipeline-2026-05-02-1225-*.log
grep -oE 'ball_event=[A-Z_]+' logs/pipeline-2026-05-02-1225-*.log | sort | uniq -c
grep -oE 'STRIP: [A-Z]{2,5} ' logs/pipeline-2026-05-02-1225-*.log | sort | uniq -c
grep -oE '\[(SCORE-INF-GATE|EXTRAS-INF-GATE)\]' logs/pipeline-2026-05-02-1225-*.log | sort | uniq -c
for f in files/logs/deliveries/20260502_122517/d*/window_debug.json; do
  python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print(d['delivery_num'],d['event_type'],d['open_scout_verdict'],d['window_source'],len(d.get('tags') or []))" "$f"
done
```
