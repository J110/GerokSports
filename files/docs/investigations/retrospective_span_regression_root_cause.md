# Retrospective-span regression — root-cause investigation

**Date:** 2026-05-05  
**Author:** Investigation memo  
**Sessions compared:**
- Working: `20260420_202239` (36/36 `retrospective_span`)
- Working: `20260421_195050` (referenced; same regime)
- Broken: `20260503_205835` and `20260504_192431` (1/30 `retrospective_span`
  on May 4; same regime on May 3)

**Pipeline log analysed:** `logs/pipeline-2026-05-04-1924-.log` (~19 min,
30 deliveries), `logs/pipeline-2026-05-03-2058--stage1ready.log`.

---

## Phase A — `window_source` assignment, code path

Decision lives in
`files/delivery_window_recorder.py:320-389`. Three competing producers:

1. **Stage 2** `DeliverySpanSelector` (`stage2_bounds`,
   `source="open_scout_span"`, `reason="stage2_emitted_anchored"`) —
   wins when `USE_OPEN_SCOUT_SPANS=1` AND the lookup returns a span.
2. **OpenScout direct** via `SpanAggregator.match_span_to_event_detailed`
   (`source="open_scout_span"`, `reason="open_scout_single_candidate"`)
   — wins on `verdict == open_scout_span`.
3. **Legacy retrospective** via `_find_span()` (this memo's subject).
   Returns `source="retrospective_span"`,
   `reason="latest_bowlers_end_span"`. Used iff #1, #2 both decline AND
   `_find_span()` returns non-None.
4. **Fallback** raw pre-event window (`source="fallback_pre_event_window"`,
   `reason="no_bowlers_end_span"`) — when all three above fail.

`_find_span()` (delivery_window_recorder.py:536-633) walks
`BallAnalyzer._tagged_buffer` snapshot in
`[event_ts - LOOKBACK_S, event_ts - POST_EVENT_EXCLUSION_S]` =
`[event_ts - 25 s, event_ts - 1.5 s]`. Required:

- `camera_view == "bowlers_end"`
- `frame_phase ∈ {release, flight, shot, runup}` (RC-7,
  delivery_window_recorder.py:118-120) — `_ACTION_PHASES`
- Contiguous-tag gap ≤ `MAX_CONTIGUOUS_GAP_S = 2.5 s` (RC-4)
- Span must end within `MAX_END_TO_EVENT_GAP_S = 8 s` of `event_ts` (RC-3)

A **single** matching tag is sufficient — produces `(span_start ==
span_end == tag_ts)`, padded to a 3.5 s clip (`PRE_PADDING_S=2`,
`POST_PADDING_S=1.5`). This is the d003 May-4 shape.

Tagged buffer is populated by
`BallAnalyzer.record_tagged_frame()` (`files/ball_analyzer.py:760-788`),
called from `test_pipeline.py:6788`. **Filters to camera_view ∈
{bowlers_end, side_on, replay} only**; everything else is dropped at
ingest. Retention: 90 s by ts.

---

## Phase B — Why retrospective fired in April but not in May

### B1. Window-debug tag-count comparison

| Session | Windows | `retrospective_span` | `fallback_pre_event_window` |
|---|---|---|---|
| 20260420_202239 | 36 | **36 (100%)** | 0 |
| 20260504_192431 | 30 | **1 (3.3%)** | 27 |

(The May 4 d003 retrospective is a **degenerate single-anchor** clip:
3.5 s, only 1 bowlers_end+release tag in the entire window_debug.)

### B2. `bowlers_end` × `frame_phase` cross-tab

Counted from `window_debug.json` `tags[]` per session:

| Phase on `cam=bowlers_end` | April 20 (working) | May 4 (broken) |
|---|---|---|
| `release` | **166** | 2 |
| `shot` | 7 | 1 |
| `flight` | 0 | 1 |
| `between_play` | 15 | 5 |
| **action-phase total** | **173** | **4** |
| **action-phase share** | **92 %** | **44 %** of buffered window-tag bowlers_end |

From the May 4 pipeline log directly (whole match, not just clipped
windows):

```
cam= distribution (May 4 full match, ~19 min):
  44 cam=ad        108 cam=closeup    103 cam=graphic
  97 cam=bowlers_end                    8 cam=other
   2 cam=side_on

cam=bowlers_end × phase= (full match):
  53 between_play   18 release    8 shot
   3 flight          1 runup      2 post_shot
```

So Scout produced **97 bowlers_end frames in 19 min ≈ 5/min**, but only
**30 satisfied `_ACTION_PHASES`** (31 %).
At ~1 delivery / 35 s, that is ~1 action-phase anchor per delivery on
average — but the distribution is bursty, so most windows see zero in
the 23.5 s effective lookback.

### B3. RC-7 phase filter is the dominant killer

`_ACTION_PHASES` was added 2026-04-23 (delivery_window_recorder.py:106-120,
"RC-7, Part A of the window-selection investigation") — **after** the
April 20-21 working corpus was captured. April 20-21 ran without phase
gating: any `cam=bowlers_end` was a valid anchor, and Scout's bias
toward `release` (92 % then) produced abundant anchors anyway.

May 4 phase mix is the inverse — `between_play` is now the modal
phase on bowlers_end frames (55 % of all bowlers_end across the match),
and RC-7 hard-rejects them at the anchor stage with `[PHASE-REJECT]`.
After RC-7, **the anchor pool shrinks by roughly 2-3×** AND Scout's
phase output for a similar broadcast has shifted toward
`between_play`. The two regressions stack.

### B4. SpanAggregator (OpenScout #2) also silent

Every May 4 `window_debug.json` shows `open_scout_verdict=no_match`
(30/30). The matcher
(`files/eyes/span_aggregator.py:259-317`) requires:

- ≥1 committed `action`-class span overlapping
  `[event_ts - LOOKBACK_S, event_ts - POST_EVENT_EXCLUSION_S]`
- duration ≥ `MIN_ACTION_SPAN_S = 2.0 s`
- end within `MAX_END_TO_EVENT_GAP_S = 8 s` of event

OpenScout cadence + commit thresholds (`MIN_SPAN_FRAMES = 2`,
`SOFT_GAP_TOLERANCE_S = 7 s`) never accumulate a 2-frame `action`
sequence per delivery in this run. Pipeline log shows only one
`[OPEN-SCOUT]` line at boot — no `[OPEN-SCOUT-SELECT]` candidates
ever evaluated.

### B5. Stage 2 not the hijacker

`SHADOW-STATS` snapshots in May 4 log show
`stage2_spans_emitted=0` for the entire run (sample at F30/F60/F90/...).
Stage 2 never emitted, so it cannot have starved the legacy path.

### B6. Frame buffer retention not the cause

`TAGGED_BUFFER_RETENTION_S = 90` exceeds `LOOKBACK_S = 25` by 3.6×.
Buffer is sufficiently long. The d003 anchor sat at `event_ts - 4.13 s`
and was retrievable; the failures are **content-not-present**, not
**content-aged-out**.

---

## Phase C — Camera classification health

| Metric | April 20 | May 4 |
|---|---|---|
| Scout calls / min (production) | not measured here, see below | ~7 / min from log |
| `cam=bowlers_end` rate | high (n≈173 action) | 5 / min |
| `phase=release` share of bowlers_end | **92 %** | 19 % |
| `phase=between_play` share of bowlers_end | 8 % | **55 %** |

The Scout PROMPT is producing radically different phase distributions
on bowlers_end frames between April and May. This is consistent with
either (a) a Scout-prompt revision that became more conservative about
labeling phases as `release`, or (b) a real change in WHICH bowlers_end
moments Scout sees (camera angles, broadcast cuts) — not yet
disentangled in this memo.

`USE_OPEN_SCOUT=1` was on for May 4 (boot log line). The added
parallel OpenScout calls have not visibly throttled production Scout
in the log.

---

## Phase D — Recommendation

**Two independent regressions stack** to drive `retrospective_span`
from 100 % to 3 %:

1. **RC-7 phase filter** (added 2026-04-23) hard-rejects ~67 % of
   bowlers_end tags. The April-corpus's strong `release`-bias
   masked how aggressive this filter is in practice.
2. **Scout phase distribution shift**: bowlers_end frames now resolve
   to `between_play` 55 % of the time (vs 8 % in April), so the post-
   filter pool shrinks further to a near-empty handful.

`SpanAggregator` (parallel OpenScout) does NOT compensate — it has its
own anchor-density requirements that the current OpenScout cadence
fails to meet.

### Minimum-scope fixes to evaluate (in priority order)

1. **Relax the anchor-phase filter for `_find_span` selection only**,
   not for clip-placement. Specifically: accept `between_play` as an
   anchor candidate **when** an action-phase tag exists within
   `MAX_CONTIGUOUS_GAP_S` either side. This restores 90 %+ of the
   April anchor-pool size without re-introducing the RC-7 audit's
   "non-delivery clip" failure (those failures came from isolated
   `between_play` tags, not from bridges between actions).
   Touch points: `delivery_window_recorder.py:586-615`.

2. **Falling back: revert RC-7 entirely** behind a flag (e.g.
   `RC7_PHASE_FILTER=1`, default `0`). Re-introduces the
   non-delivery-clip risk RC-7 was added to fix, but recovers the
   100 % retrospective-span rate immediately. Pair with downstream
   Layer 2 acceptance gating to catch the bad clips.

3. **Cause-side investigation, not yet fixable**: diagnose the
   May-vs-April Scout phase-distribution shift. The hypothesis is a
   Scout-prompt change post April-20; verify by diffing
   `files/eyes/vision.py` and Scout system prompts across the period.
   If confirmed, restoring the April-20 prompt for phase resolution
   would unwind regression #2.

### Out of scope (not recommended now)

- Modifying `fallback_pre_event_window` behavior (per task).
- Touching Stage 2 `DeliverySpanSelector` (per task).
- Rewriting `SpanAggregator` thresholds (different surface area).
- Architectural redesign.

---

## Appendix — d003 anatomy (the one May 4 success)

```
event_ts:    1777903414.293
clip:        1777903408.16 → 1777903411.66  (3.5 s)
legacy_window.span_start == span_end == 1777903410.16
tags in window: 1
  ts=1777903410.16  cam=bowlers_end  phase=release
frame_count: 637  (≈ 182 fps — duplicate-inflated, pre-Batch-AA capture)
```

Single-anchor degenerate span: span duration = 0, padded out to 3.5 s
clip. This proves the code path still works; it just rarely finds an
anchor.
