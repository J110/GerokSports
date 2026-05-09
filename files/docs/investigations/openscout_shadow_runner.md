# OpenScout shadow-mode runner (Component 3)

Standalone Python module that wires Stage 1 (BroadcastModeFilter) +
Stage 2 (DeliverySpanSelector) + Stage 3 (Qwen) into a same-process
shadow pipeline running alongside the main pipeline. Output is
log-only JSONL; the main pipeline is unaffected by shadow crashes.

## Architecture

Same-process, daemon-thread shadow (Option W). The caller pushes
frames and Scout results via non-blocking, bounded queues; a single
shadow thread drains the queues, runs Stage 1 + Stage 2, and
dispatches Stage 3 (Qwen) on each closed delivery span.

```
caller thread       │  shadow daemon thread
────────────────────┼─────────────────────────────────────────────
add_frame(ts, bgr) ─┼─► frame_q ──► Stage 1 (BroadcastModeFilter)
add_scout_result(d)─┼─► scout_q ──► Stage 1 ACTIVE gate
                    │                     │
                    │                     ▼
                    │            Stage 2 (DeliverySpanSelector)
                    │                     │ on_span_emitted
                    │                     ▼
                    │            span_q ──► Stage 3 (Qwen)
                    │                              │
                    │                              ▼
                    │                       JSONL append
```

The Stage 1 callbacks (`on_window_open` / `on_window_close`) and the
Stage 2 callback (`on_span_emitted`) all run on the shadow thread.
Window close triggers an immediate `Stage2.flush()` so any pending
spans drain into `span_q` before a new candidate window starts.

All exception handling is inside `_thread_main`'s tick loop; the
shadow thread can never crash the caller. Worst case it dies and
the main pipeline keeps running.

## Queue bounds

- `frame_q`: 60 (drop oldest on overflow)
- `scout_q`: 100 (drop oldest on overflow)
- `span_q`: 50 (drop newest on overflow with warning)

Drops are counted in `_n_dropped_overflow` and surfaced in the
JSONL footer.

## JSONL output

- Path: `files/logs/openscout_shadow/<session_id>.jsonl`
- Append-only, one JSON record per line, opened with line buffering.
- First line is a `_header` record; final line on `stop()` is a
  `_footer` record with run counters
  (`n_frames`, `n_scouts`, `n_dropped_inactive`, `n_dropped_overflow`,
  `n_emitted`, `n_qwen_errors`).

Per-delivery schema:

| field | type | source |
|---|---|---|
| `session_id` | str | constructor |
| `delivery_id` | str | `<session>-d<NNNN>` monotonic seq |
| `stage1_window_open_ts` | float \| null | latest Stage 1 open ts |
| `stage1_window_close_ts` | float \| null | latest Stage 1 close ts (null if window still open) |
| `stage2_span_start_ts` | float | `DeliverySpan.raw_start_ts` |
| `stage2_span_end_ts` | float | `DeliverySpan.raw_end_ts` |
| `stage2_span_padded_start` | float | `DeliverySpan.start_ts` (Qwen-input bound) |
| `stage2_span_padded_end` | float | `DeliverySpan.end_ts` (Qwen-input bound) |
| `stage2_max_consecutive_action` | int | `DeliverySpan.max_consecutive_action` |
| `stage2_action_ratio` | float | `DeliverySpan.action_ratio` |
| `stage2_hard_close_count` | int | `DeliverySpan.hard_close_count` |
| `stage3_qwen_details` | dict \| null | classifier output (or `{"qwen_disabled": True}`) |
| `stage3_qwen_latency_ms` | int | wall-clock around classifier call |
| `stage3_qwen_error` | str \| null | `type: msg` if classifier raised |

## Integration hook

```python
from openscout_shadow.pipeline_hook import attach_shadow_runner

shadow_runner = attach_shadow_runner(
    ball_analyzer, session_id=SESSION_ID)

# In the main loop, after the production OpenScout dispatch:
if shadow_runner is not None:
    try:
        shadow_runner.add_frame(ts, frame_bgr)
        shadow_runner.add_scout_result({
            "ts": res.timestamp,
            "frame_class": res.frame_class,
            "raw_description": res.raw_description,
        })
    except Exception:
        log.exception("[SHADOW] caller-side push failed")
```

`stop()` is auto-registered with `atexit` in `start()`, so callers do
not need to plumb shutdown through the main pipeline's existing
`finally` blocks. They MAY call `stop()` explicitly for deterministic
flush ordering.

## Qwen wiring (v0)

The runner accepts `qwen_classifier: Callable | None` at construction.
v0 ships with the classifier left as None (records get
`stage3_qwen_details = {"qwen_disabled": True, "frame_count": N}`).

`pipeline_hook.attach_shadow_runner` wraps the classifier in a
closure that snapshots `ball_analyzer._frame_buffer` for the span
window before invoking it (see Stop condition S1 — `list()` on a
deque is atomic in CPython, no extra lock needed). Real Qwen wiring
is a follow-up: replace the `qwen_callable=None` argument with a
function that mirrors the production Qwen Layer 2 signature
(`files/ball_analyzer.py:909, 979`).

## SHADOW_MODE env var

- Unset / `"0"`: `attach_shadow_runner` returns None; runner not
  constructed. The integration hook becomes a None check.
- `"1"`: runner constructed and `start()`-ed.

## Comparing shadow output against the main pipeline

After a match:

1. Shadow JSONL: `files/logs/openscout_shadow/<session>.jsonl`.
2. Main pipeline deliveries: usual sidecar / per-delivery logs (see
   `files/eyes/openscout_persistence.py`).
3. Align by `stage2_span_start_ts` ↔ main pipeline
   `Span.start_ts` (both come from the same `SpanAggregator`); diff
   the Stage 3 details once the Qwen classifier is wired.

## Smoke test

`files/scripts/openscout_shadow_smoke/run_smoke.py` runs a
self-contained drive:

- Latches Stage 1 ACTIVE via `ingest_signals` (no opencv needed).
- Feeds 8 action Scout obs over ~4 s, then a `replay` hard-close,
  then 6 `other` tail obs to elapse the 3 s closure-hold.
- Stops the runner and asserts:
  - JSONL file exists at `/tmp/openscout_shadow_smoke/<session>.jsonl`
  - At least one delivery record present
  - All required schema fields populated
  - `_header` and `_footer` records present

## Stop conditions encountered

- **S1** (`_frame_buffer` access): handled in `pipeline_hook` via
  `list()` snapshot on the deque. No locking helper added — the
  CPython GIL makes `list(deque)` atomic vs the producer thread's
  `append()`.
- **S3** (Qwen reuse): accepted stub-only Qwen for v0 per spec.
  Real wiring is a follow-up task.
