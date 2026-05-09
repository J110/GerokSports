# Parallel-Scout (OpenScout) — operator setup

**Status:** Implementation Session 1 shipped; default OFF behind
`USE_OPEN_SCOUT_SPANS=0`. Shadow telemetry is on whenever the
SpanAggregator is wired in (any normal pipeline run).

**Design memo:** `files/docs/investigations/parallel_scout_delivery_window_design.md`

---

## TL;DR

A second Groq Llama-Scout-17B instance ("OpenScout") runs
fire-and-forget after each `vision.describe(...)` call, classifies
the frame as `{action, replay, ad, umpire, other}` from natural
prose, and feeds a `SpanAggregator` that emits closed contiguous
spans. On a score event, both the legacy `_find_span` path and the
new `match_span_to_event` path propose a window; both windows are
written to `window_debug.json`. The flag controls only which window
the Layer 2 classifier actually sees.

---

## Environment variables

| Var | Default | Effect |
|---|---|---|
| `USE_OPEN_SCOUT` | `1` | Master switch. When `0`, no extra Groq calls are made and the SpanAggregator stays empty. |
| `USE_OPEN_SCOUT_SPANS` | `0` | When `1`, the score-event window selector commits OpenScout's single-candidate span; otherwise it falls through to legacy `_find_span` / `fallback_pre_event_window`. |
| `OPEN_SCOUT_ACTIVE_INTERVAL_S` | `1.0` | Seconds between OpenScout calls during active play (`bowlers_end` / `side_on`). |
| `OPEN_SCOUT_AMBIGUOUS_INTERVAL_S` | `2.0` | Seconds between OpenScout calls in ambiguous states (`closeup`, `graphic`, `other`, unknown). |
| `OPEN_SCOUT_MAX_TOKENS` | `220` | Open-prompt response budget. |
| `OPEN_SCOUT_TEMPERATURE` | `0.2` | Matches validation harness. |
| `OPEN_SCOUT_TIMEOUT_S` | `8.0` | Per-call timeout. Failures drop silently. |

OpenScout shares `GROQ_API_KEY` with primary Vision but uses its own
`AsyncGroq` client (separate connection pool / timeout). Ad breaks +
paused capture skip the call entirely.

---

## OpenScout output persistence (added 2026-05-02)

Two layers of on-disk persistence let the operator reconstruct
OpenScout behaviour after the run finishes — including for
post-match investigations into per-frame recall and SpanAggregator
filter tuning. Wired automatically when `USE_OPEN_SCOUT=1`; both
layers degrade gracefully if the disk fills or files cannot be
opened.

### Layer A — per-frame JSONL sidecar

Path: `logs/openscout-<SESSION_ID>.jsonl` (one file per pipeline
run, where `SESSION_ID` is the same uuid hex8 that
`logs/trace/<SESSION_ID>.jsonl` uses).

One JSON object per line, written for every OpenScout invocation
**and** every rate-gate-skipped frame:

```json
{
  "ts": 1714638742.512,
  "frame_idx": 4823,
  "frame_class": "action",
  "raw_text": "Wide field view from bowler's end. Bowler is mid-runup; …",
  "latency_ms": 412,
  "error": null,
  "rate_gate_reason": "passed"
}
```

`rate_gate_reason` values:
- `passed` — gate allowed the frame; `frame_class` populated.
- `skipped:throttled(interval_s=1.00)` — within active/ambiguous interval.
- `skipped:paused_view(cam=ad,phase=advertisement)` — view/phase paused.
- `skipped:capture_paused` — `ball_analyzer.alive == False`.

For errors (timeout / API exception / encode failure) the record is
written with `frame_class=null`, an `error` string, and the actual
`latency_ms` consumed.

### Layer B — per-span clip + metadata bundle

Path: `files/logs/openscout_spans/<SESSION_ID>/span_<NNNN>/` — one
directory per closed span (action / replay / ad / umpire / other).
`<NNNN>` is the per-aggregator span_id, monotonically increasing
from `0001`.

Each span dir contains:

| File | Description |
|---|---|
| `clip.mp4` | Frame-buffer slice of `[span_start − 1.0s, span_end + 1.0s]`. The 1.0 s pre/post pad gives visual context without dragging the legacy `PRE_PADDING_S=2.0 / POST_PADDING_S=1.5` over (raw span clips, not Layer-2 windows). |
| `metadata.json` | `span_id`, `span_start_ts`, `span_end_ts`, `duration_s`, `frame_count`, `frame_class`, `n_classifications_in_span`, `n_frames_classified_action`, `n_frames_classified_other`, `text_samples`, `clip` sub-dict, `matched_to_event` (initially null). |
| `classifications.jsonl` | Subset of Layer A's per-frame records that fall inside `[span_start_ts, span_end_ts]`. Lets you see, for each persisted span, exactly what OpenScout said frame-by-frame. |

`matched_to_event` is patched in by
`DeliveryWindowRecorder.classify_for_score_event` whenever the
matcher resolves a span to a score event:

```json
{
  "matched_to_event": {
    "event_ts": 1714638750.21,
    "delivery_id": "d004",
    "verdict": "open_scout_span",
    "noted_at_ts": 1714638750.93
  }
}
```

If a span never matches (no score event arrives within the matcher's
lookback window) the field stays `null`.

### Failure handling

| Failure | Behaviour |
|---|---|
| Layer A file can't be opened | Warning logged once at boot; sidecar disabled, in-memory ring buffer continues so Layer B `classifications.jsonl` still works. |
| Layer A append fails (disk full / IO error) | Warning logged once, file handle closed; subsequent writes silently dropped. |
| Layer A JSON serialisation error | Single-record warning, drop record, continue. |
| Layer B mp4 compile fails | `metadata.json` and `classifications.jsonl` still written; `clip.note` carries the failure reason. |
| Layer B span dir mkdir fails | Span persistence disabled for the run; aggregator continues. |
| `note_match_to_event` after span dir was cleaned up | Warning logged, no-op. |

In every case the live pipeline (Scout / scoring / WS broadcast) is
unaffected.

### Manual review

```bash
ls files/logs/openscout_spans/<SESSION_ID>/
# span_0001  span_0002  span_0003 …
cat files/logs/openscout_spans/<SESSION_ID>/span_0001/metadata.json
open files/logs/openscout_spans/<SESSION_ID>/span_0001/clip.mp4
head -5 files/logs/openscout_spans/<SESSION_ID>/span_0001/classifications.jsonl
```

For aggregate per-frame analysis (recall, class distribution, latency
histograms) operate directly on
`logs/openscout-<SESSION_ID>.jsonl` — one record per frame, easy
`jq` / pandas territory.

---

## How to enable shadow telemetry

Already on — `USE_OPEN_SCOUT=1` is the default. Every `window_debug.json`
under `logs/deliveries/<session>/window_NNNN/` now carries:

```json
{
  "window_source": "retrospective_span",
  "legacy_window":   {"source": "retrospective_span", "span_start": ..., "span_end": ..., "clip_start": ..., "clip_end": ...},
  "open_scout_window": {"span_start": ..., "span_end": ..., "clip_start": ..., "clip_end": ...} | null,
  "open_scout_verdict": "open_scout_span" | "no_match" | "defer_to_legacy" | "aggregator_unavailable" | "aggregator_error",
  "use_open_scout_spans": false
}
```

Run `python3 -c 'import json; ...'` over a session to compute span
overlap between `legacy_window.clip_*` and `open_scout_window.clip_*`
per delivery for the §9.4 cutover criteria.

---

## How to flip the flag for trial runs

```bash
USE_OPEN_SCOUT_SPANS=1 python3 test_pipeline.py
```

When the flag is on:
- `verdict == "open_scout_span"` → OpenScout's bounds drive the mp4.
- `verdict == "defer_to_legacy"` (multi-span case, §5.2) → legacy
  `_find_span` runs as fallback.
- `verdict == "no_match"` / `"aggregator_*"` → identical to flag-off
  behavior (legacy path, then `fallback_pre_event_window`).

---

## How to roll back

```bash
USE_OPEN_SCOUT_SPANS=0 python3 test_pipeline.py    # default
```

To fully disable OpenScout (no extra Groq calls, no shadow
telemetry):

```bash
USE_OPEN_SCOUT=0 python3 test_pipeline.py
```

`window_debug.json` will then carry
`open_scout_verdict = "aggregator_unavailable"` for every delivery
(aggregator is wired but receives no observations).

---

## Cost expectations

Per design memo §3.3: `+$0.03 to +$0.10 per match` on top of the
documented `~$0.09 / match` Scout baseline. Day-1 shadow telemetry
should measure `usage.total_tokens` against this estimate; if the
real cost overshoots, drop `OPEN_SCOUT_ACTIVE_INTERVAL_S` to `2.0`.

---

## Cutover gate (§5.2 + §9.4)

Before flipping the default, the offline analyzer (Session 2) must
confirm — across 3-5 matches / ≥600 deliveries:

1. ≥50 % of deliveries produce a non-null `open_scout_window`.
2. Span overlap with `legacy_window` ≥70 %.
3. Multi-span subset ≥15 % of deliveries AND multi-span heuristic
   agreement ≥70 % with legacy/manual ground truth.
4. No regression on phantom-skip / duplicate-span / `too_few_frames`
   rates.

Until those gates are met, `USE_OPEN_SCOUT_SPANS` stays `0` and the
heuristic remains shadow-only.
