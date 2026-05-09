# Decoupled OpenScout setup

`OPENSCOUT_DECOUPLED=1` runs OpenScout in a dedicated async coroutine
that polls the capture-card frame source independently of the main
pipeline iteration cadence.  Targets ~1.0s effective Scout cadence
versus the ~6s median observed inline (see
`files/docs/investigations/openscout_span_formation_diagnosis.md`).

## When to enable

- You want span formation to be driven by a near-realtime sample of the
  broadcast (1.0s gap median) rather than the main pipeline's variable
  cadence.
- The TPM budget headroom is acceptable (see below).

## When NOT to enable

- Custom OpenScout prompt that consumes >5K tokens per call — projected
  TPM utilization at 1.0s exceeds the safe ceiling.  Measure first;
  raise `OPENSCOUT_DECOUPLED_TARGET_INTERVAL_S` to compensate.
- Running on the free Groq tier — quota math below assumes the
  Developer plan.

## Quota math (Developer plan, llama-4-scout-17b-16e-instruct)

| Limit | Cap | Usage @ 1.0s target | % of cap |
|---|---|---|---|
| RPM | 1,000 | 60 | 6% |
| RPD | 500,000 | ~12,600 / match | 2.5% |
| TPM | 300,000 | ~180,000 (3K tok/call) | 60% |

TPM is the only meaningful ceiling.  The `OPENSCOUT_TPM_BUDGET`
default of 240,000 (80% of 300K) trips auto-derate before the cap is
reached.  Drift above ~5K tokens/call would push observed TPM past
that ceiling — see verification step below.

## Configuration

```
OPENSCOUT_DECOUPLED=1
OPENSCOUT_DECOUPLED_TARGET_INTERVAL_S=1.0
OPENSCOUT_TPM_BUDGET=240000
USE_OPEN_SCOUT=1            # required — provides the OpenScout instance
```

Both decoupled flags default to 0.  Behavior with `OPENSCOUT_DECOUPLED=0`
is unchanged from the legacy inline path.

## Pre-flight check (run before live match)

1. Run a 5-minute smoke against a warm-up / practice broadcast with
   `OPENSCOUT_DECOUPLED=1`, `OPENSCOUT_DECOUPLED_TARGET_INTERVAL_S=1.0`.
2. Verify the loop's 30-second log lines (search for
   `[OPEN-SCOUT-LOOP] cadence`):
   - `median_gap` ≤ 1.5 s
   - `429` count = 0
   - `mean_tokens` ≤ 5,000
   - `util` ≤ 70%
3. If `mean_tokens` > 5,000, raise
   `OPENSCOUT_DECOUPLED_TARGET_INTERVAL_S` to 1.25 (or higher) and
   re-run the smoke.

## Cadence verification (post-match)

```
python - <<'PY'
import json, sys
gaps = []
prev = None
with open("logs/openscout-<SESSION_ID>.jsonl") as f:
    for line in f:
        rec = json.loads(line)
        if rec.get("frame_class") and rec.get("rate_gate_reason") == "passed":
            ts = float(rec["ts"])
            if prev is not None:
                gaps.append(ts - prev)
            prev = ts
gaps.sort()
n = len(gaps)
print(f"calls={n}  median_gap={gaps[n//2]:.2f}s  "
      f"p95_gap={gaps[int(n*0.95)]:.2f}s  "
      f"mean_tokens={sum(json.loads(l).get('tokens_total', 0) for l in open(f.name))/max(1,n):.0f}")
PY
```

Pass criteria for a 1.0s target:

- `median_gap` ≤ 1.5 s — the API latency floor is ~1.3 s, so 1.5 s
  median is the realistic ceiling.
- `p95_gap` ≤ 3.0 s — taller spikes indicate intermittent 429s or
  network stalls.

## Cost note

At 1.0s target and ~3K tokens/call:

- ~12,600 calls per 4-hour match
- Groq llama-4-scout-17b-16e-instruct pricing: confirm current rate
  in the Groq console; back-of-envelope is well under the legacy
  Together AI baseline that the parallel-Scout design replaced.

## Rollback

Set `OPENSCOUT_DECOUPLED=0` and restart the pipeline.  Behavior reverts
to the inline path — no other changes required.  The slot, loop, and
TPM budget are no-ops when the flag is off.

## Operator hotkey toggle

Mid-match flip is supported only via process restart with the env var
flipped.  In-process toggle is out of scope for v1; the loop-task
spawn happens once at startup.

## Files

- Loop: `files/eyes/openscout_loop.py`
- Slot: `files/eyes/latest_frame_slot.py`
- Budget: `files/eyes/tpm_budget.py`
- Tests: `files/tests/test_openscout_loop.py`
- Wiring: `files/test_pipeline.py` (around the BallAnalyzer / shadow
  runner spawn block)
