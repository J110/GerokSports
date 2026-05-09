# OpenScout span formation — diagnosis (CSK vs MI 2026-05-02 innings 2)

**Status:** investigation complete, no fixes implemented.
**Date:** 2026-05-03
**Source data:** `logs/pipeline-2026-05-02-2049-csk-vs-mi-44th-match-ipl-2026-innings2.log`,
`logs/openscout-d03b43da.jsonl`,
`files/logs/openscout_deliveries/20260502_204958/`,
`logs/machine-1-2026-05-02.log`.

## TL;DR

Three independent issues compound to produce "33 deliveries → 1 action span":

1. **(High-confidence root cause, tuning-only fix)** `SOFT_GAP_TOLERANCE_S = 2.5 s`
   in `files/eyes/span_aggregator.py` is far below the actual OpenScout
   inter-arrival cadence (median 5.36 s, p95 9.96 s). 186 of 187 action
   classifications were force-closed as 1-frame singletons and dropped by
   `MIN_SPAN_FRAMES = 2`. Only one consecutive-action pair under 2.5 s
   existed in the entire 59-minute run, which is exactly the lone action
   span that committed.
2. **(Operator-confusion artefact, not a real bug)** The
   `openscout-smoke_test_openscout.jsonl` file the operator surfaced is
   from an unrelated manual smoke-test invocation (mtime 20:41, 8 min
   *before* the live run started; 2 hand-crafted records `ts=100/101`,
   `raw_text="x"`). It is not session bleed.
3. **(Real session-id divergence, no functional impact yet)** The Layer A
   sidecar JSONL is keyed on `SESSION_ID = uuid.uuid4().hex[:8]`
   (`logs/openscout-d03b43da.jsonl`) while Layer B span/delivery writers
   are keyed on `BallAnalyzer._session_id =
   time.strftime("%Y%m%d_%H%M%S")` (`files/logs/openscout_deliveries/20260502_204958/`).
   Plus the JSONL path is relative to cwd, so older sessions launched from
   `files/` landed under `files/logs/` and yesterday's session launched
   from repo root landed under `logs/` — making the JSONL appear
   "missing" when the operator only checked `files/logs/`.

Tuning fix #1 alone unblocks the architecture redesign. With
`SOFT_GAP_TOLERANCE_S = 5.0 s` (everything else unchanged), simulation
shows **27 action spans of ≥ 2 s** form against the actual data — vs.
the 33 deliveries enqueued by the main pipeline, that is dense enough
signal to drive downstream work.

---

## §1 Yesterday's artifact inventory

### 1.1 Pipeline log

* `logs/pipeline-2026-05-02-2049-csk-vs-mi-44th-match-ipl-2026-innings2.log`
  — 14 224 lines, ANSI-coloured stdout capture.
* Startup at `[20:49:56 F0 TEST]`; first frame `F1` at `20:50:01`; last
  frame referenced `F787` (matches the prior analysis).
* Only two OpenScout-tagged lines exist in this file (`pipeline-*.log`):
  * line 85 — `[OPEN-SCOUT] enabled (USE_OPEN_SCOUT=1)`
  * line 4 045 — `[21:04:00 F250 OPEN-SCOUT] WARN: [OPEN-SCOUT] timeout after 8.0s`
* Everything else from the persistence layer (`OPEN-SCOUT-SIDECAR`,
  `OPEN-SCOUT-DELIVERY`, `OPEN-SCOUT-SELECT`, `OPEN-SCOUT-ARCHIVE`) lives
  on a *different* destination — the cricket logger file handler in
  `logs/machine-1-2026-05-02.log` (see §4.1).

### 1.2 Cricket logger

* `logs/machine-1-2026-05-02.log` — 2.4 MB; contains the
  per-OpenScout-component lines that are missing from the colored
  pipeline log. Yesterday's run startup is at line 4 688:

  ```
  4688: [OPEN-SCOUT-SIDECAR] writing per-frame JSONL to logs/openscout-d03b43da.jsonl
  4689: [20:49:57 F0 TEST] INFO: [OPEN-SCOUT] enabled (USE_OPEN_SCOUT=1)
  4694: [OPEN-SCOUT-DELIVERY] note_match disabled for validation run
  4700: [OPEN-SCOUT-DELIVERY] writing validation clips under files/logs/openscout_deliveries/20260502_204958
  ```

  Note the two distinct session ids on consecutive lines.

### 1.3 OpenScout JSONL files (Layer A)

| Path | Size | mtime | Records | Session label |
|---|---|---|---|---|
| `logs/openscout-d03b43da.jsonl` | 324 KB | 21:48:59 | **583** | yesterday's CSK-vs-MI innings 2 |
| `logs/openscout-1ee054d7.jsonl` | 1.2 KB | 20:49 | 2 | abandoned start at 20:49:09 |
| `files/logs/openscout-ac752eb5.jsonl` | 240 KB | 20:05 | 421 | earlier session (cwd=`files/`) |
| `files/logs/openscout-f2098e63.jsonl` | 11 KB | 19:27 | 19 | earlier session (cwd=`files/`) |
| `files/logs/openscout-smoke_test_openscout.jsonl` | 268 B | 20:41 | 2 | **manual smoke test, not pipeline output** |

Only the first two are from the pipeline-launched sessions on
2026-05-02 evening. They live under `logs/`, not `files/logs/`,
because the `OpenScoutSidecar.__init__` default `log_dir="logs"` is
relative to the launch cwd and yesterday's run was started from the
repo root (older runs were started from `files/`).

`openscout-smoke_test_openscout.jsonl` is a test fixture, not session
bleed:

```
{"ts": 100.0, "frame_idx": 1, "frame_class": "action", "raw_text": "x", "latency_ms": 1, "error": null, "rate_gate_reason": "passed"}
{"ts": 101.0, "frame_idx": 2, "frame_class": "action", "raw_text": "x", "latency_ms": 1, "error": null, "rate_gate_reason": "passed"}
```

mtime = 20:41:00, which is 9 minutes *before* the pipeline log's first
line at 20:49:56. The literal string `"smoke_test_openscout"` does
not appear anywhere in the codebase (only in the prior investigation
memo). It is a hand-crafted operator artefact from a manual
`OpenScoutSidecar(session_id="smoke_test_openscout")` call.

### 1.4 Span / delivery clip directories (Layer B)

```
files/logs/openscout_deliveries/20260502_204958/
├── delivery_0001.mp4                       (367 KB, 21:23:05)
├── delivery_0001_metadata.json             (span_id=4)
└── non_action/
    ├── span_0001_other.mp4 + metadata      (20:54:37)
    ├── span_0002_other.mp4 + metadata      (20:56:30)
    ├── span_0003_other.mp4 + metadata      (20:58:27)
    └── span_0005_other_metadata.json       (21:24:06, mp4 missing — frame buffer empty)
```

Five committed spans total: 1 action + 4 other. Matches `SpanAggregator`
state at end of run (see §3.1 default-constants simulation).

`files/files/logs/openscout_spans/` contains only directories from
2026-05-02 19:25/19:28 sessions; nothing from yesterday's match. This
is `OpenScoutSpanArchive` output — it requires `attach_open_scout_sidecar`
to register a *second* committed callback distinct from
`OpenScoutDeliveryWriter`. Per `BallAnalyzer.attach_open_scout_sidecar`
(`files/ball_analyzer.py:681-716`), only the delivery writer is wired;
`OpenScoutSpanArchive` is never instantiated by the live pipeline path
(it appears to be exercised only by validation harnesses). This is a
documentation/expectation gap, not a runtime bug.

---

## §2 Per-frame dispatch analysis

Source: `logs/openscout-d03b43da.jsonl` — 583 records spanning
`2026-05-02 20:49:59.96` → `21:48:59.66` (59.0 min).

### 2.1 Rate-gate disposition

| `rate_gate_reason` | count | share |
|---|---:|---:|
| `passed` | **469** | 80.4 % |
| `skipped:paused_view(cam=ad,phase=advertisement)` | 109 | 18.7 % |
| `skipped:throttled(interval_s=2.00)` | 5 | 0.9 % |

469 actually dispatched to the classifier; 1 of those returned an error
(timeout @ `frame_idx=247`, `latency_ms=8005`).

### 2.2 frame_class distribution (over 469 dispatched)

| `frame_class` | count | share of dispatched |
|---|---:|---:|
| `other` | 265 | 56.5 % |
| **`action`** | **187** | **39.9 %** |
| `replay` | 11 | 2.3 % |
| `umpire` | 4 | 0.9 % |
| `ad` | 1 | 0.2 % |
| `null` (timeout) | 1 | 0.2 % |

### 2.3 Cadence & dispatch ratio

* All-record inter-arrival mean / median / p95: **6.08 / 5.36 / 9.96 s**.
* Action-only inter-arrival distribution (the relevant one for
  `SpanAggregator`):

  | gap | count | cumulative |
  |---|---:|---:|
  | < 1 s | 0 | 0 |
  | 1 – 2 s | 0 | 0 |
  | 2 – 2.5 s | **1** | 1 |
  | 2.5 – 5 s | 41 | 42 |
  | 5 – 10 s | 56 | 98 |
  | > 10 s | 88 | 186 |

  **Only one consecutive-action pair fell inside the
  `SOFT_GAP_TOLERANCE_S = 2.5 s` window.**

* Main pipeline: ~787 frames processed.
  Dispatch ratio **469 / 787 = 59.6 %** — lines up with the rate-gate
  blocking ad/throttle frames.

### 2.4 Coverage gaps over the run

The trace has the single timeout at 21:04:00 plus the 109 advertisement
skips. There is no minute-long blackout window — dispatches stream
continuously across all 59 minutes (verified by spot-checking
timestamps; no gap > ~30 s outside of advertisement runs).

---

## §3 SpanAggregator simulation

Source defaults from `files/eyes/span_aggregator.py:60-69`:

```
MIN_SPAN_FRAMES       = 2
SAME_CLASS_GAP_TOL    = 1
SOFT_GAP_TOLERANCE_S  = 2.5
SPAN_RETENTION_S      = 90.0
MIN_ACTION_SPAN_S     = 2.0
```

Closure rules (from the `_add_locked` state machine, lines 330-374):

* Same class → extend open span.
* One dissenting class under tolerance → counts as gap, holds open.
* Two dissenting classes OR `(now - last) > soft_gap` → force-close.
* On force-close, drop if `frame_count < MIN_SPAN_FRAMES`.
* Action-span matcher additionally requires `duration_s ≥ MIN_ACTION_SPAN_S`.

### 3.1 Simulation against actual yesterday data

`SpanAggregator` was driven directly with all 468 typed observations
from `openscout-d03b43da.jsonl` (skipping the 1 null), then `force_close`
called at end-of-run.

| Constants | total spans | action spans | action ≥ 2 s | singletons dropped |
|---|---:|---:|---:|---:|
| **DEFAULT** mfn=2, sct=1, sgt=2.5 | 5 | **1** | 1 | **455** |
| A: mfn=1, sct=1, sgt=2.5 | 460 | 184 | 1 | 0 |
| **B: mfn=2, sct=1, sgt=5.0** | **60** | **27** | **27** | **261** |
| C: mfn=1, sct=2, sgt=5.0 | 321 | 125 | 27 | 0 |
| D: mfn=1, sct=1, sgt=10.0 | 148 | 63 | 30 | 0 |

Reconciliation: the DEFAULT-row count of 5 / 1 matches *exactly*
what's on disk in `files/logs/openscout_deliveries/20260502_204958/`
(4 non-action + 1 action). The simulation is faithful.

### 3.2 What the table tells us

* **DEFAULT is broken for current dispatch cadence.** 455 of 468
  observations are dropped as singletons; the only action span that
  survives is the single 2.38 s pair at frames whose ts gap fell under
  2.5 s.
* **Lowering `MIN_SPAN_FRAMES` to 1 alone (row A) is wrong.** It
  promotes every isolated obs to a span; 184 "action spans" of 0.0 s
  duration would all fail the `MIN_ACTION_SPAN_S = 2.0 s` gate at the
  matcher and produce no usable signal.
* **Raising `SOFT_GAP_TOLERANCE_S` to ~5 s (row B) is the correct
  knob.** It produces 27 action spans of ≥ 2 s with the existing
  `MIN_SPAN_FRAMES = 2` filter. 27 is in the right ballpark vs the 33
  deliveries the main pipeline saw (the missing ~6 plausibly fall under
  the wider-gap pairs that span an ad break or replay).
* **Pushing `sgt = 10.0` (row D)** generates a few longer aggregated
  spans (max 49.6 s) but starts merging unrelated action bursts —
  acceptable for shadow telemetry, risky for span-driven windowing.
  Not recommended without a `MAX_SPAN_S` cap.

### 3.3 Why 2.5 s was chosen and why it broke

The constant predates the post-hoc dispatch-rate evidence. OpenScout's
*nominal* cadence is "≈ 1 fps" but the real schedule is gated by:

* Vision-call latency (typical 500-1500 ms).
* Rate-gate skips on advertisements (109 here = 18.7 % of frames).
* Other frame classes interleaved between two action frames (e.g., a
  `closeup` between the bowler's run-up and ball-release frame).

The combined effect: the median *all-record* gap is 5.4 s, and the
median *action-action* gap is in the 5-10 s bucket. A 2.5 s hard
boundary is incompatible with the actual cadence.

---

## §4 Persistence session-id audit

### 4.1 Two independent session-id sources

| Layer | Owner | Source | Yesterday's value |
|---|---|---|---|
| A — JSONL sidecar | `OpenScoutSidecar` (`files/eyes/openscout_persistence.py:73`) | `SESSION_ID` module-level @ `files/test_pipeline.py:851`, `uuid.uuid4().hex[:8]` | `d03b43da` |
| B — clip writers | `OpenScoutDeliveryWriter`, `OpenScoutSpanArchive` | `BallAnalyzer._session_id` @ `files/ball_analyzer.py:398`, `time.strftime("%Y%m%d_%H%M%S")` | `20260502_204958` |

The wiring sits at `files/ball_analyzer.py:703-704`:

```python
writer = OpenScoutDeliveryWriter(
    session_id=self._session_id,        # ← Layer B uses ball_analyzer ts
    frame_source_fn=self._frame_source,
    sidecar=sidecar,                    # ← passes the Layer A sidecar object
)
```

The sidecar object is correctly threaded through, so the Layer B writer
*can* read Layer A records via `records_in_range(...)`. But the two
session ids never reconcile; an analyst handed only the
`20260502_204958/` directory has no easy way to find the matching
`openscout-d03b43da.jsonl`.

### 4.2 The "smoke_test bleed" hypothesis is wrong

Re-stating §1.3 explicitly:

* `smoke_test_openscout` is a literal `session_id` argument the operator
  passed to `OpenScoutSidecar` from a Python REPL or test harness;
* the resulting JSONL has only 2 records with `ts=100/101`,
  `raw_text="x"`, `latency_ms=1` — clearly hand-crafted;
* mtime is **20:41**, which is **8 minutes before** the live pipeline
  even started initialising (20:49:56 in the log);
* the literal string `"smoke_test_openscout"` does not appear anywhere
  in source.

There is no startup path that auto-creates a `smoke_test_openscout`
sidecar, and the live run did not write to it.

### 4.3 cwd-relative JSONL path

`OpenScoutSidecar.__init__` defaults `log_dir="logs"` (relative). The
JSONL therefore lands under whichever directory the pipeline was
launched from. Yesterday's run launched from repo root → `logs/`.
Earlier 19:25-20:05 sessions launched from `files/` → `files/logs/`.
This is the second reason the operator's `ls files/logs/openscout-*.jsonl`
returned only stale files.

### 4.4 OpenScoutSpanArchive is never wired in the live path

`attach_open_scout_sidecar` (`files/ball_analyzer.py:681-716`)
constructs an `OpenScoutDeliveryWriter` and registers
`writer.on_span_committed` as the *single* `_on_committed_cb` on the
SpanAggregator. `set_committed_callback` replaces any prior callback,
so even if `OpenScoutSpanArchive` were instantiated separately it would
overwrite or be overwritten. The live match path therefore produces no
`files/files/logs/openscout_spans/<session>/` output. Documentation in
the persistence module's docstring implies otherwise — that's a doc
drift, not a regression.

---

## §5 Coverage cross-reference: 33 deliveries vs JSONL action hits

Method: parse every `[DELIVERY ENQUEUED] dnum=…` line from the pipeline
log (33 events, 20:51:33 → 21:46:39) and, for each delivery's
wall-clock timestamp, count action records in `openscout-d03b43da.jsonl`
within ±W seconds.

| Window | Deliveries with ≥ 1 action hit | % |
|---|---:|---:|
| ± 5 s | 17 / 33 | 52 % |
| ± 10 s | 26 / 33 | 79 % |
| ± 15 s | 32 / 33 | 97 % |
| ± 30 s | 33 / 33 | 100 % |

**OpenScout did see action frames near every delivery.** The 7
deliveries with zero ±10 s coverage (20:53:16, 21:04:21, 21:15:50,
21:17:01, 21:19:21, 21:23:53, 21:44:30) all had at least one action
record within ±15 s. The 21:04:21 zero corresponds to the 21:04:00
timeout window plus an advertisement skip — i.e. classifier was
genuinely unavailable for ~10-15 s there.

So the funnel is:

```
33 deliveries  → 33 with some action coverage at ±30 s
              → 187 action classifications across the run
              → only 1 action span survived the 2.5 s soft-gap +
                 MIN_SPAN_FRAMES=2 double filter
```

The bottleneck is unambiguously inside `SpanAggregator`, not at
classifier dispatch and not at the persistence layer.

---

## §6 Fix proposals (ranked)

Tier 1 = required for span density to be usable. Tier 2 = correctness /
hygiene. Tier 3 = nice-to-have for future analysis.

### Tier 1 — span density (ship before redesign)

**F1.** Raise `SOFT_GAP_TOLERANCE_S` from 2.5 → 5.0 s in
`files/eyes/span_aggregator.py:62`. Keep `MIN_SPAN_FRAMES=2` and
`MIN_ACTION_SPAN_S=2.0`. Simulation against yesterday's data: 27
action spans of ≥ 2 s vs current 1.
*Risk:* could merge two genuinely separate action bursts that are < 5 s
apart; in the actual data the action-action gap distribution shows
only 1 pair under 2.5 s and 41 in the 2.5-5 s bucket, so the
under-merge risk is bounded.
*Effort:* trivial (1 constant + a unit-test update if
`test_span_aggregator.py` pins the value).

**F2.** Add a `MAX_SPAN_S = 12.0` cap inside `_add_locked` to bound
how long a single span can grow under the wider tolerance. Prevents
"49 s spans" of the kind row D produced when SGT was pushed further.
*Effort:* ~10 lines + 1 test case.

### Tier 2 — correctness & observability

**F3.** Reconcile session ids. Two options, pick one:
* (a) Pass `BallAnalyzer._session_id` into `OpenScoutSidecar` from
  `test_pipeline.py:5770` (drop the uuid for live runs).
* (b) Stamp both ids into a `session_links.json` written at startup.
Either makes post-hoc analysis tractable.
*Effort:* (a) ~15 min; (b) ~30 min.

**F4.** Make `OpenScoutSidecar(log_dir=...)` an absolute path anchored
to the repo root (or pass it explicitly from
`test_pipeline.py:5770`). Stops cwd-dependence from scattering JSONL
across `files/logs/` and `logs/`.
*Effort:* ~10 min.

**F5.** Mirror the `[OPEN-SCOUT-SIDECAR]`, `[OPEN-SCOUT-DELIVERY]`,
`[OPEN-SCOUT-SELECT]` lines into the pipeline log so an operator
inspecting only `pipeline-*.log` sees them. Currently they only land
in `machine-1-*.log`.
*Effort:* ~30 min — add a stdout console handler to the
`open_scout_persistence` and `span_aggregator` loggers.

**F6.** Either wire `OpenScoutSpanArchive` into
`attach_open_scout_sidecar` (using a multi-callback dispatcher on the
aggregator) or delete the dead-doc claim. Today the docstring lies.
*Effort:* multi-callback ~45 min; doc fix ~5 min.

### Tier 3 — future-proofing

**F7.** Stop dropping `_TRACE_RECORDER` records on
`SAME_CLASS_GAP_TOL`-absorbed dissents — emit a structured trace event
so we can later tune that constant from data instead of intuition.
*Effort:* ~30 min.

**F8.** Track `singletons_dropped_per_class` in `SpanAggregator.stats()`
so the next time this fails the symptom appears in
`window_debug.json` instead of requiring a re-simulation.
*Effort:* ~15 min.

**F9.** Add a regression test that drives `SpanAggregator` with a
real-cadence fixture (median 5 s gap, p95 10 s) and asserts at least
N action spans commit. Pins the soft-gap value to evidence.
*Effort:* ~45 min.

---

## §7 Effort summary

| Fix | Tier | Est. effort | Required for redesign? |
|---|---|---|---|
| F1 — `SOFT_GAP_TOLERANCE_S 2.5 → 5.0` | 1 | trivial | **yes** |
| F2 — `MAX_SPAN_S` cap | 1 | ~30 min | nice-to-have |
| F3 — reconcile session ids | 2 | 15-30 min | recommended |
| F4 — anchor JSONL `log_dir` | 2 | ~10 min | recommended |
| F5 — mirror persistence logs to pipeline log | 2 | ~30 min | optional |
| F6 — wire OpenScoutSpanArchive (or doc fix) | 2 | 5-45 min | optional |
| F7 — trace SAME_CLASS_GAP absorbs | 3 | ~30 min | no |
| F8 — extend `stats()` | 3 | ~15 min | no |
| F9 — cadence-realistic regression test | 3 | ~45 min | recommended |

Bare minimum for the next live run to produce dense span signal:
**F1 + F3 + F4** (~45 min total; F1 is the only one strictly needed
for span density).

---

## Appendix A — reproduction commands

```bash
# JSONL distributions
python3 - <<'PY'
import json, collections
recs = [json.loads(l) for l in open("logs/openscout-d03b43da.jsonl")]
print(collections.Counter(r["frame_class"] for r in recs))
print(collections.Counter(r["rate_gate_reason"] for r in recs))
PY

# SpanAggregator simulation
python3 - <<'PY'
import json, sys; sys.path.insert(0, "files")
from eyes.span_aggregator import SpanAggregator
recs = [json.loads(l) for l in open("logs/openscout-d03b43da.jsonl")]
def sim(mfn, sgt):
    agg = SpanAggregator(min_span_frames=mfn, soft_gap_tolerance_s=sgt)
    closed=[]; agg.set_committed_callback(closed.append)
    for r in recs:
        if r.get("frame_class"): agg.add_classification(r["ts"], r["frame_class"])
    agg.force_close(now=recs[-1]["ts"]+10)
    return [s for s in closed if s.frame_class=="action" and s.duration_s>=2]
print("default:", len(sim(2, 2.5)), "  sgt=5.0:", len(sim(2, 5.0)))
PY

# Coverage cross-reference (deliveries vs action hits)
# See §5 — full script in chat history of this investigation.
```

---

## §6 Live-match no-commit diagnostic (2026-05-03 SRH-KKR innings 2)

**Status:** Diagnosis complete; fix proposed and ready to apply on operator approval.
**Symptom:** Live PID 82459, session `20260503_173229` (trace) /
sidecar id `69f98c9c`. 13/14 first-innings deliveries closed with
`window_source=fallback_pre_event_window`,
`reason=no_bowlers_end_span`, `open_scout_verdict=no_match`.
`files/logs/openscout_deliveries/20260503_172728/non_action/` is
empty — **zero spans committed** in 4+ minutes of broadcast.

### 6.1 Reproduce

The Layer A sidecar exists and is healthy:
`logs/openscout-69f98c9c.jsonl`, 43 records, mtime `17:31:39`,
zero errors, zero rate-gate throttle skips. 39 records have a
`frame_class` (4 are `skipped:paused_view(cam=ad,...)`). Class mix:
19 action, 20 other, 0 replay/ad/umpire-as-class.

```text
Total observations: 39
Window: 1777809456.87 → 1777809697.93 (241.1 s)
Inter-arrival gap: min=3.18s  p50=5.09s  p90=5.82s  max=40.60s (ad break)
```

**Crucially every consecutive-observation gap is ≥ 3.18 s.** No
pair of OpenScout dispatches in this run was ≤ `SOFT_GAP_TOLERANCE_S
= 2.5 s` apart.

### 6.2 Replay simulation

Replaying the full 39-record sidecar through `SpanAggregator`
(everything else default):

| `SOFT_GAP_TOLERANCE_S` | total commits | action commits ≥2 s | singletons dropped |
|------------------------|---------------|---------------------|--------------------|
| **2.5 (production)**   | **0**         | **0**               | 39                 |
| 5.0 (P22 proposal)     | 7             | 4                   | 17                 |
| 7.0                    | 8             | 5                   | 6                  |
| 10.0                   | 9             | 5                   | 4                  |
| 15.0                   | 7             | 4                   | 3 (over-bridges ads) |

### 6.3 Root cause

Same mechanism as §4 of this memo, but more extreme tonight: **every
single observation triggers a force-close** because the smallest gap
(3.18 s) exceeds `SOFT_GAP_TOLERANCE_S = 2.5 s`. The aggregator
never gets the chance to grow a span past `n=1`, and `MIN_SPAN_FRAMES
= 2` drops every singleton. Hence `spans_committed = 0` for the run.

Why this run is worse than CSK-MI (§3.2 had 1 commit):
* SRH-KKR's OpenScout cadence is *tighter* and *more uniform*
  (p50 5.09 vs 5.36, no sub-2.5 s gaps at all). CSK-MI had one
  freak ~2.4 s pair that survived.
* Underlying broadcast Scout cadence in this run is ~5 s/frame
  (verifiable from `[F1..F18]` Vision lines in
  `logs/pipeline-2026-05-03-srh-vs-kkr-45th-match-ipl-2026-innings2.log`),
  so the rate-gate's 1 fps target is unreachable — Scout itself is
  the cadence floor.

The architectural assumption baked into `SOFT_GAP_TOLERANCE_S = 2.5`
(that OpenScout dispatches at ≈1 Hz) does not hold when Vision
itself is throttled below that rate. The constant must be set by
observed dispatch cadence, not by intended cadence.

### 6.4 Recommended fix

**Set `SOFT_GAP_TOLERANCE_S = 7.0`** in
`files/eyes/span_aggregator.py:62`. Rationale:

* 7.0 captures all 5 viable action spans in tonight's data
  (10.0 captures the same 5).
* 7.0 keeps the 40.6 s ad-break gap as a hard split, so an ad
  cannot be welded onto an action span.
* Headroom over the observed `p90 = 5.82 s` is ≈ 1.2 s — a
  conservative single-skip absorption without bridging real
  state changes.
* Constant-only change. Live-patchable. No interface or logic
  change.

Estimated impact for the current match if applied: ~5 action
spans and ~3 other spans committed per innings half × the
remaining 20-ish deliveries → most subsequent deliveries should
flip from `fallback_pre_event_window` to `open_scout_span` once
the SpanAggregator has fresh data. Past deliveries (d001–d014)
cannot be retroactively recovered.

### 6.5 Patch + restart sequence (ready to run on approval)

```bash
# In-place tunable bump (single line, no interface change).
python3 -c "
import re, pathlib
p = pathlib.Path('files/eyes/span_aggregator.py')
s = p.read_text()
new = re.sub(
    r'^SOFT_GAP_TOLERANCE_S: float = 2\.5\b',
    'SOFT_GAP_TOLERANCE_S: float = 7.0',
    s, count=1, flags=re.M)
assert new != s, 'pattern not found'
p.write_text(new)
print('patched')
"

# Verify
grep -n 'SOFT_GAP_TOLERANCE_S: float' files/eyes/span_aggregator.py

# Restart sequence (operator-driven; do not auto-execute):
#   1. Note current PID:    pgrep -f test_pipeline.py
#   2. Stop pipeline:       kill -INT <pid> ; wait
#   3. Relaunch:            (operator's normal launch command — same env)
#   4. Confirm SpanAgg:     tail -F the new pipeline log;
#                           grep 'OPEN-SCOUT-SELECT' should start showing
#                           single_candidate / multi_candidate verdicts
#                           within ~30 s of first action span.
```

### 6.6 Out-of-scope follow-ups (do NOT block the patch)

* The "Vision throttled to ~5 s/frame" upstream issue (slow-motion
  / fps degradation) is the deeper root cause of why P22's 5.0 s
  proposal undershoots. Tracked separately by operator.
* `SESSION_ID` divergence (sidecar `69f98c9c` vs deliveries
  `20260503_172728` vs trace `20260503_173229`) — same as §1.3 of
  this memo, no functional impact, deferred.
* `MIN_SPAN_FRAMES = 2` is now the *only* singleton filter. With
  ~5 s cadence, requiring ≥2 obs means a span needs ≥1 cadence
  interval of duration. Acceptable given `MIN_ACTION_SPAN_S = 2.0`
  already filters short spans downstream — but worth revisiting if
  Vision cadence stays low.
