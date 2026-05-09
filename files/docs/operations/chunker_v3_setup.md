# Chunker v3 setup + cutover gates

## TL;DR

- `USE_V3_CHUNKER=1` → shadow mode.  v3 runs in parallel, every
  delivery cut emits a `v3_chunker` block in `window_debug.json`,
  but the actual cut is unchanged.
- `USE_V3_CHUNKER_SPANS=1` → v3 drives the cut when it returns a
  non-None window.  Falls back to the legacy span when v3 returns
  None.

Both flags default to 0.  No new API calls; v3 reuses cached Scout
outputs from the OpenScout result-sink (~$0 cost).

## Configuration

```
USE_V3_CHUNKER=1
USE_V3_CHUNKER_SPANS=0
USE_OPEN_SCOUT=1            # required — supplies v3 with per-frame inputs
```

The decoupled OpenScout loop (`OPENSCOUT_DECOUPLED=1`) is recommended
but not required; v3 also receives frames from the inline OpenScout
path.

## Algorithm

See `files/docs/algorithms/chunker_v3.md` for the full spec.  Summary:

- Rule-based per-frame labels (AD > DRS > REPLAY > UMPIRE_SIGNAL >
  DELIVERY_ACTION > NON_DELIVERY_ACTION).
- Time-based thresholds throughout — robust to OpenScout cadence
  drift (1.0–1.3 s median post-decoupling).
- Three fixes on top of the v3 baseline (10/7/1/0):
  1. Bidirectional REPLAY propagation (4 s OR 3 live anchors).
  2. Celebration tightened — needs crowd-as-subject for REPLAY.
  3. Cluster-merge ≤10 s when the gap is benign.
- Acceptance: ≥13/18 MATCH on the 18 cached fixtures.

## Cutover gates

Flip `USE_V3_CHUNKER_SPANS=1` only after **all three** gates clear.

### Gate 1 — Shadow stability

50 windows in shadow with no errors.  Verify:

- `analyze_trace.py` shows zero `[CHUNKER-V3]` exceptions in
  `decisions[]`.
- `window_debug.json` `v3_chunker` block populated on every match
  (start/end may be null for low-evidence events; that's fine —
  errors are not).
- `BallAnalyzer` log: zero `[CHUNKER-V3] aggregator add swallowed`
  warnings.

### Gate 2 — IoU vs legacy on labeled sample

≥80% v3 vs legacy IoU on a 25-window human-labeled sample.

Procedure:

1. After a match in shadow mode, pick 25 events covering action /
   replay / wickets / boundaries.
2. For each, open `delivery_window.mp4` and label the true
   delivery boundaries.
3. Compare ground truth IoU for v3 (`v3_chunker.start`/`end`) and
   legacy (`legacy_window.span_start`/`span_end`).
4. Pass: v3 IoU geomean ≥ 0.8 × legacy IoU geomean across the 25.

### Gate 3 — Operator review

1 full match in shadow with operator review of all P21 advisories
(see analyze_trace `P21 (chunker v3 divergence)` rule).

- Spot-check every P21 firing where `|v3 − legacy| > 2 s`.
- Determine if v3 or legacy is closer to ground truth.
- Pass: v3 wins on ≥60% of advisories spot-checked.

## Pre-flight check (tonight's match)

1. Set `USE_V3_CHUNKER=1`, `USE_V3_CHUNKER_SPANS=0`.  Shadow only;
   legacy continues to drive cuts.
2. After the match, run:

   ```
   python files/analyze_trace.py logs/trace/<SESSION>.jsonl \
       --report files/docs/match_reports/<DATE>_<slug>.md
   ```
3. In the report, scan the `Advisory` section for `P21`
   firings — those are the v3-vs-legacy divergence hotspots.
4. For each, open the matching `delivery_window.mp4` (path under
   `logs/deliveries/<SESSION>/window_<NNNN>/`) and judge which
   bound is closer to the true delivery.
5. Track results per match toward Gate 2 / Gate 3 above.

## Rollback

Set `USE_V3_CHUNKER_SPANS=0`.  v3 continues to run as shadow telemetry
(no behavior change to actual cuts).  To disable v3 entirely set
`USE_V3_CHUNKER=0`; the aggregator is not constructed and DWR's
`v3_chunker` block is omitted from `window_debug.json`.

## Files

| File | Purpose |
|---|---|
| `files/eyes/chunker_v3.py` | Pure-function algorithm |
| `files/eyes/chunker_v3_aggregator.py` | Per-match buffer + `find_span` |
| `files/docs/algorithms/chunker_v3.md` | Algorithm spec |
| `files/tests/test_chunker_v3.py` | 18-fixture acceptance + units |
| `files/eyes/config.py` | `USE_V3_CHUNKER`, `USE_V3_CHUNKER_SPANS` |
| `files/ball_analyzer.py` | Aggregator construction + `record_v3_frame` |
| `files/delivery_window_recorder.py` | DWR window-resolution branch |
| `files/trace_emitter.py` | `CHUNKER-V3-WINDOW` tag registration |
| `files/anomaly_rules.py` | `P21` divergence advisory |
| `files/test_pipeline.py` | OpenScout result-sink wiring |

## None-event fallback

When v3 returns `None` for a score event AND legacy `_find_span` also
returns `None`, the recorder emits a fixed-width window centered on
`event_ts` instead of the legacy `fallback_pre_event_window`
(historical default — known to produce unusable cuts when the strip-
OCR tag stream is broken).  This is the *None-event safety net*:
better a slightly-off window than no window.

### When it fires

Each fallback usage logs:

```
[CHUNKER-V3-FALLBACK] event_ts=<t> window=(<start>, <end>)
                      lookback_s=<L> forward_s=<F>
```

`window_debug.json` records:

```json
{
  "v3_chunker": { "drove_cut": "fallback", ... },
  "fallback": {
    "used": true,
    "lookback_s": 6.0,
    "forward_s": 4.0
  }
}
```

The post-match analyzer surfaces every firing as a `P22` warning
(rule `chunker_v3_fallback_used`).

### Defaults and tuning

- `V3_FALLBACK_ENABLED` (default `1`) — master switch.  Set `0` to
  revert to the legacy `fallback_pre_event_window` semantics
  (regression-safe).
- `V3_FALLBACK_LOOKBACK_S` (default `6.0`) — seconds before
  `event_ts`.  Covers bowler run-up.
- `V3_FALLBACK_FORWARD_S` (default `4.0`) — seconds after
  `event_ts`.  Covers post-shot fielding.

Defaults are derived from the average delivery duration in the
18-clip corpus.  If post-match review finds the fallback windows
systematically miss the actual delivery, tune these per match before
launch:

```
V3_FALLBACK_LOOKBACK_S=8.0
V3_FALLBACK_FORWARD_S=5.0
```

### Design note

Fallback windows are **not score-consequential** by construction —
they catch *UI clip availability* (every event gets a clip), not
*detection accuracy* (whether the delivery is correctly framed).
Do not tune fallback bounds expecting them to land precisely on the
delivery; tune them to be a safe envelope.

## Tonight's match

Pre-launch env:

```
USE_V3_CHUNKER=1
USE_V3_CHUNKER_SPANS=1
V3_FALLBACK_ENABLED=1
OPENSCOUT_DECOUPLED=1
OPENSCOUT_DECOUPLED_TARGET_INTERVAL_S=1.0
OPENSCOUT_TPM_BUDGET=240000
```

In-match monitoring (tail the pipeline log):

- `[CHUNKER-V3-WINDOW]` — v3 produced a span (good).
- `[CHUNKER-V3-FALLBACK]` — v3 + legacy both `None`; fallback used
  (acceptable, but watch the rate).
- `[OPEN-SCOUT-LOOP] cadence` lines every 30 s — `median_gap` should
  stay ≤ 1.5 s, `util` ≤ 70%.

Rate guidance:

- > 3 fallback firings per 10 events ⇒ v3 is misfiring.  Consider
  `USE_V3_CHUNKER_SPANS=0` + restart.  Cuts will still be produced
  by the fallback (legacy is broken tonight).
- Cadence drift > 1.5 s median ⇒ check Groq dashboard for 429s, then
  drop `OPENSCOUT_DECOUPLED_TARGET_INTERVAL_S` to `1.25`.

Post-match:

- Run `analyze_trace.py` on `logs/trace/<SESSION>.jsonl`.
- Review `P21` (legacy-vs-v3 divergence) and `P22` (fallback used)
  advisories.
- Spot-check 5–10 fallback events against the `delivery_window.mp4`
  files.  If the fixed window caught the actual delivery reasonably,
  accept the defaults.  If systematically off, retune
  `V3_FALLBACK_LOOKBACK_S` / `V3_FALLBACK_FORWARD_S` for next match.

## Known limitations (v1)

- The per-event v3 label snapshot in `window_debug.json` reclassifies
  ±15 s around `event_ts`.  CPU cost is negligible (<5 ms / event)
  at OpenScout cadence but scales linearly if the buffer grows.
