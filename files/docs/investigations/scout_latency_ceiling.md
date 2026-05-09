# OpenScout per-call latency ceiling

**Date:** 2026-05-03
**Source:** `logs/openscout-d03b43da.jsonl` (CSK vs MI 2026-05-02 innings 2,
59 min run, 583 records). Code: `files/eyes/open_scout.py`,
`files/eyes/config.py`, `files/test_pipeline.py:6557-6606`.

## §1 Latency aggregates

* Successful classifier calls (latency_ms set, no error): **468**
* Timeouts: **1** (frame_idx=247 @ 21:03:51, 8 005 ms)
* No other errors.

| stat | ms |
|---|---:|
| min | 496 |
| median / p50 | **808** |
| mean | 908 |
| p75 | 1 012 |
| p90 | 1 267 |
| p95 | **1 489** |
| p99 | 2 582 |
| max | 4 222 |

### Histogram (50 ms buckets)

| bucket | count | cum % |
|---|---:|---:|
| 450-499 | 1 | 0.2 |
| 500-549 | 8 | 1.9 |
| 550-599 | 21 | 6.4 |
| 600-649 | 46 | 16.2 |
| 650-699 | 53 | 27.6 |
| 700-749 | 53 | 38.9 |
| 750-799 | 44 | 48.3 |
| 800-849 | 34 | 55.6 |
| 850-899 | 34 | 62.8 |
| 900-949 | 26 | 68.4 |
| 950-999 | 28 | 74.4 |
| 1000-1099 | 37 | 82.3 |
| 1100-1199 | 27 | 88.0 |
| 1200-1299 | 12 | 90.6 |
| 1300-1399 | 16 | 94.0 |
| 1400-1499 | 6 | 95.3 |
| 1500-1999 | 11 | 97.4 |
| 2000-2999 | 11 | 99.8 |
| 4200-4249 | 1 | 100.0 |

Distribution is unimodal around 700-800 ms with a thin right tail (≤ 5 %
above 1.5 s). No bimodality.

## §2 Latency by frame_class

| class | n | median ms | p95 ms | max ms |
|---|---:|---:|---:|---:|
| other | 265 | 804 | 1 607 | 2 988 |
| action | 187 | 821 | 1 354 | 4 222 |
| replay | 11 | 873 | 1 236 | 1 236 |
| umpire | 4 | 904 | 1 301 | 1 301 |
| ad | 1 | 590 | 590 | 590 |

**No meaningful class skew.** Action and other are within 17 ms at the
median; the small classes are too sparse to draw conclusions from.
Latency is image-content-independent at this resolution / max_tokens.

## §3 Timeouts

One timeout at `2026-05-02 21:03:51` (`frame_idx=247`, latency 8 005 ms,
matches `OPEN_SCOUT_TIMEOUT_S=8.0`). Single isolated event — no
cluster, no neighbouring high-latency calls. Treat as Groq tail jitter.

## §4 Source confirmation

* **Model**: `meta-llama/llama-4-scout-17b-16e-instruct` via
  `groq.AsyncGroq` (`files/eyes/config.py:15`,
  `files/eyes/open_scout.py:34, 101-105`). Same model family as primary
  Vision; OpenScout uses a *separate* `AsyncGroq` client instance for
  failure isolation (per `open_scout.py:11-18` docstring).
* **Dispatch**: fully **async / fire-and-forget**.
  `files/test_pipeline.py:6588-6590` does
  `asyncio.create_task(_open_scout_pipe(...))` — the per-frame loop
  never awaits the result. **No `Semaphore` / concurrency cap** is
  configured anywhere in the call path. Steady-state in-flight count =
  `dispatch_rate × avg_latency`; at 1 Hz dispatch + 0.81 s avg, that is
  ~0.8 calls in flight on average.
* **Rate gate**: `OpenScoutRateGate.allow(...)` in
  `files/eyes/open_scout.py:260-327`, applied at
  `test_pipeline.py:6565`. Per-state intervals in
  `files/eyes/config.py:59-62`:
  * active views (`bowlers_end`, `side_on`) → `OPEN_SCOUT_ACTIVE_INTERVAL_S = 1.0`
  * ambiguous views (`closeup`, `graphic`, `other`, unknown) →
    `OPEN_SCOUT_AMBIGUOUS_INTERVAL_S = 2.0`
  * paused views (`ad`, `advertisement` phase) → no calls
* **Per-call timeout**: `OPEN_SCOUT_TIMEOUT_S = 8.0`
  (`config.py:69-70`).

Rate-gate evidence in yesterday's data: only **5 of 583** records have
`rate_gate_reason="skipped:throttled(interval_s=2.00)"`. The throttle
almost never fires — the gate is not the bottleneck.

## §5 Maximum sustainable dispatch rate

Two ways to read "sustainable":

1. **Serial-equivalent ceiling** (worst-case if any one call blocked
   the next):
   `1 / median = 1 / 0.808 s ≈ 1.24 Hz`.
   Using p95 instead: `1 / 1.49 s ≈ 0.67 Hz`.

2. **Concurrent-dispatch ceiling** (current architecture). Latency
   doesn't gate throughput because calls run in parallel. The
   practical caps are:
   * Groq token-throughput limits per API key (not measured here, but
     220 max_tokens × 1 Hz ≈ 220 tok/s — well within stated limits).
   * Bounded queue depth: in-flight = rate × avg_latency. To keep p99
     in-flight ≤ 4 (a comfortable budget): `rate ≤ 4 / 2.58 ≈ 1.55 Hz`.

**Both readings converge on ≈ 1.0 - 1.2 Hz** as the practical safe
ceiling. The current `OPEN_SCOUT_ACTIVE_INTERVAL_S = 1.0` (1 Hz) sits
right at the median-latency boundary with ~70 % p75 headroom — fine
under typical conditions, marginal in tail.

## §6 Recommended `interval_s`

* **Active interval: keep at `1.0 s`** (current default). The
  observation in P22 that real action-action JSONL gaps were 5-10 s
  median was *not* caused by latency or rate-gating — only 5 throttle
  skips occurred all match. The gaps came from interleaved
  `other`/`closeup` classifications between consecutive `action`
  frames. Tightening the rate gate would not fix span sparseness; the
  P22 fix (raising `SOFT_GAP_TOLERANCE_S` to 5 s) is the right knob.
* **Ambiguous interval: keep at `2.0 s`** (current default). No
  evidence to change.
* **Conservative tightening would be `0.75 s` active** if span
  density is later found to need more action samples per delivery,
  but that pushes p99 in-flight to ~3.4 — close enough to the 8 s
  timeout × parallel-tail risk that it is not worth doing pre-emptively.
* **Do not tighten below 0.75 s.** At 0.75 s the steady-state in-flight
  count under p95 latency (1.49 s) crosses 2; at 0.5 s it crosses 3
  with no ceiling — a brief Groq tail spike could pile work and trip
  the 8 s timeout.

## §7 Bottom line

Per-call latency is well-behaved (median 0.8 s, p95 < 1.5 s) and the
classifier is not a throughput bottleneck under the current 1 Hz
active gate. **Latency is not the cause of the P22 sparse-span
problem.** The recommended `OPEN_SCOUT_ACTIVE_INTERVAL_S` value is
unchanged at `1.0 s`.
