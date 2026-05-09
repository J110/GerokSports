# Sub-clip delivery isolation v4 — clip_end fallback for anchor target

Status: ready for operator review · 2026-05-03 · iteration on
`sub_clip_delivery_isolation_v3.md`

This memo accompanies artefacts produced by
`files/scripts/sub_clip_isolation_v4/extract_spans.py`.  Goal:
explicitly handle the v3 diagnostic finding that `event_offset_s` is
typically *outside* clip bounds for `retrospective_span` clips by
making `clip_duration` the anchor target in that case.  Validate
against v3's same 15 clips PLUS 5 brand-new clips (20 total).

## §1  Methodology — v4 changes

Single wrapper-side change; `eyes/span_aggregator.py` core untouched.

```python
def resolve_anchor(event_offset_s, clip_duration):
    if event_offset_s is None:
        return (clip_duration, "fallback_no_event_ts")
    if 0 < event_offset_s <= clip_duration:
        return (event_offset_s, "event_ts")
    return (clip_duration, "clip_end")
```

The downstream selection rule is unchanged from v3 (filter on
`midpoint ≤ anchor_target`, prefer `max end_ts ≤ anchor_target`,
tie-break by `frame_count`).  Padding (1.0 s) and replay/ad
hard-close: unchanged from v3.

## §2  Diagnostic finding from v3 evaluation

Across all 20 clips in the v4 set:

* **`event_offset_s` inside clip bounds:** **0 / 20** (zero).
* **`event_offset_s` outside clip bounds (after `clip_end_ts`):**
  **20 / 20** (all of them).
* **`event_offset_s` missing / malformed:** 0 / 20.

The score event timestamp lands 0.5 s – 14 s *after* the
`delivery_window.mp4` ends in the captured corpus.  This is by
design of the `retrospective_span` window source: the recorder
publishes the clip when the broadcast goes quiet, and the score
event arrives later when the on-screen scoreboard updates and the
ingest pipeline detects the change.

Distribution of `event_offset_s − clip_duration` (s) across the 20
clips: median ≈ 1.5 s, range ≈ 0.5–11 s.  Examples:

| clip                        | clip_dur | event_off | gap (s) |
|-----------------------------|----------|-----------|---------|
| 20260420_202239/d015        | 23.10    | 24.05     | +0.95   |
| 20260420_202239/d033        | 21.86    | 22.57     | +0.71   |
| 20260421_195050/d029        | 9.94     | 12.14     | +2.20   |
| 20260420_202239/d017        | 24.75    | 25.37     | +0.63   |
| 20260420_202239/d005        | 15.32    | 26.15     | **+10.83** |
| 20260421_195050/d036        | 11.78    | 25.40     | **+13.61** |
| 20260421_195050/d013        | 16.52    | 25.38     | +8.86   |

Consequence for v4 vs v3:

* In v3, the anchor target was `event_offset_s` regardless of where
  it landed; the "max end_ts ≤ event_offset" preference was
  effectively "max end_ts ≤ very-large-number" → "max end_ts ≤
  clip_duration" because spans can't end past the last frame.
* In v4 the anchor target is explicitly `clip_duration` for the
  outside-bounds case.  Because every span's `end_ts ≤ clip_duration`
  and every span's midpoint ≤ end_ts, the midpoint filter trivially
  passes and the selection collapses to the same "max end_ts" rule
  v3 exercised — **identical outputs.**

This was anticipated as stop-condition S3 ("if most v3→v4
selections don't change…").  The result here is the maximal version
of S3: zero selections changed.  v4 is a *semantic* clean-up
(documents the intent, removes the implicit "anchor past the clip"
weirdness) but has no behavioural effect on this corpus.

## §3  v3-vs-v4 selection diff for the 15 repeated clips

| clip                   | v3 padded     | v4 padded      | changed |
|------------------------|---------------|----------------|---------|
| 20260420_202239/d012   | 0.0 → 12.98   | 0.0 → 12.98    | no |
| 20260420_202239/d032   | 15.0 → 25.51  | 15.0 → 25.51   | no |
| 20260421_195050/d013   | 0.0 → 16.0    | 0.0 → 16.0     | no |
| 20260420_202239/d033   | 0.0 → 14.0    | 0.0 → 14.0     | no |
| 20260420_202239/d005   | 0.0 → 6.0     | 0.0 → 6.0      | no |
| 20260421_195050/d066   | 0.0 → 12.0    | 0.0 → 12.0     | no |
| 20260421_195050/d008   | 10.0 → 21.0   | 10.0 → 21.0    | no |
| 20260420_202239/d017   | 12.0 → 19.0   | 12.0 → 19.0    | no |
| 20260421_195050/d021   | NO_SPAN       | NO_SPAN        | no |
| 20260421_195050/d027   | 1.0 → 7.0     | 1.0 → 7.0      | no |
| 20260420_202239/d015   | 0.0 → 23.0    | 0.0 → 23.0     | no |
| 20260421_195050/d029   | 0.0 → 9.94    | 0.0 → 9.94     | no |
| 20260420_202239/d029   | 0.0 → 15.0    | 0.0 → 15.0     | no |
| 20260421_195050/d055   | 5.0 → 18.0    | 5.0 → 18.0     | no |
| 20260421_195050/d060   | 0.0 → 5.0     | 0.0 → 5.0      | no |

**0 of 15** selections changed.  d032 still benefits from the same
selection swap that v3 introduced (`[15-25.5]` over `[0-12]`), and
d005 still suffers the same "only one qualifying span exists"
limitation that v3 documented.  No clip improved, no clip regressed.

## §4  New 5-clip selection results (zero overlap with v1+v2+v3)

| clip                 | event   | ar    | max_run | replay | clip_dur | event_off | raw            | padded         | pick                |
|----------------------|---------|-------|---------|--------|----------|-----------|----------------|----------------|---------------------|
| 20260421_195050/d019 | DOT     | 0.933 | 14      | 0      | 14.43 s  | 19.94 s   | 0.0 → 13.0     | 0.0 → 14.0     | end_before_anchor   |
| 20260421_195050/d036 | DOT     | 1.000 | 12      | 0      | 11.78 s  | 25.40 s   | 0.0 → 11.0     | 0.0 → 11.78    | end_before_anchor   |
| 20260420_202239/d014 | DOT     | 0.667 | 6       | 0      | 11.95 s  | 13.32 s   | 0.0 → 5.0      | 0.0 → 6.0      | end_before_anchor   |
| 20260421_195050/d020 | FOUR    | 0.591 | 11      | 0      | 21.99 s  | 25.42 s   | 0.0 → 12.0     | 0.0 → 13.0     | end_before_anchor   |
| 20260421_195050/d051 | EXTRA   | 0.333 | 5       | 0      | 22.92 s  | 26.74 s   | 0.0 → 4.0      | 0.0 → 5.0      | end_before_anchor   |

All 5 produced a qualifying span.  All anchors resolved to
`clip_end` (event_offset > clip_duration in every case).  Notable:

* **d014** (MED, ar=0.667 max_run=6) — picked `[0-5]` of an 11.95 s
  clip.  Like d005, the action burst is early in the clip but
  there's no later qualifying span to compete with.
* **d051** (LOW, ar=0.333 max_run=5) — picked `[0-4]` of a 22.9 s
  clip.  Span is exactly at the `MIN_RUN_FRAMES=5` threshold; most
  of the clip is non-action content.  Operator should check whether
  the actual delivery is in the [0-5 s] range or buried later in
  the long tail of `other` frames.
* **d020** (FOUR, ar=0.591 max_run=11) — picked `[0-12]` of a 22 s
  clip.  Decent-length span; padding adds 1 s.

## §5  `anchor_basis` distribution across all 20 clips

| basis                  | count | %    |
|------------------------|-------|------|
| `clip_end`             | 20    | 100% |
| `event_ts`             | 0     | 0%   |
| `fallback_no_event_ts` | 0     | 0%   |

Selection-pick distribution (15 clips with qualifying spans, plus
1 NO_SPAN, plus 4 new clips):

| pick                             | count |
|----------------------------------|-------|
| `end_before_anchor`              | 18    |
| `end_before_anchor_n=2` (d032)   | 1     |
| `no_qualifying_span` (d021)      | 1     |

Zero `straddle_anchor`, `anchor_filtered_all`, or `below_min_run_5`
in this dataset.  d032 remains the only multi-candidate clip in
the entire 20-clip set — confirming v3's observation that the
anchor preference rarely has multi-candidate work to do.

## §6  Operator review prompt

For each clip in
`files/scripts/sub_clip_isolation_v4/gallery.mp4` (10 v3-comparable
+ 5 v3-new + 5 v4-new, with section divider cards), answer:

* **(a)** Does the right-half (clip_end-anchored, 1 s-padded)
  sub-span CONTAIN the actual delivery — run-up → bowling → ball
  into play → shot resolution?  Yes / No / Partial.
* **(b)** Does the right-half sub-span correctly EXCLUDE replays /
  cutaways / closeups?  Yes / No / Partial.
* **(c)** For the 15 repeated clips, is v4 better/worse/same than
  v3?  Better / Worse / Same.  *(All are mathematically the same;
  this is a sanity check that nothing visually regressed.)*
* **(d)** For the d032 swap and d005 known-limit cases, do they
  read the way v3 promised?

Suggested fill-in (paste back into §7):

```
clip                            (a)  (b)  v4 vs v3   notes
== v3 repeated set ==
20260420_202239/d012            Y/P  Y/P  S
20260420_202239/d032 SWAP       Y/P  Y/P  S          KEY: did v3 swap survive v4?
20260421_195050/d013            Y/P  Y/P  S
20260420_202239/d033            Y/P  Y/P  S
20260420_202239/d005            Y/P  Y/P  S          v3 known limit, unchanged
20260421_195050/d066            Y/P  Y/P  S
20260421_195050/d008            Y/P  Y/P  S
20260420_202239/d017            Y/P  Y/P  S
20260421_195050/d021 NO_SPAN    N    —    S          Scout-side miss
20260421_195050/d027            Y/P  Y/P  S
== v3 new set ==
20260420_202239/d015            Y/P  Y/P  S
20260421_195050/d029            Y/P  Y/P  S
20260420_202239/d029            Y/P  Y/P  S
20260421_195050/d055            Y/P  Y/P  S
20260421_195050/d060            Y/P  Y/P  S
== v4 new set ==
20260421_195050/d019            Y/P  Y/P  N/A
20260421_195050/d036            Y/P  Y/P  N/A
20260420_202239/d014            Y/P  Y/P  N/A        early-burst, same shape as d005
20260421_195050/d020            Y/P  Y/P  N/A
20260421_195050/d051            Y/P  Y/P  N/A        at MIN_RUN threshold
```

## §7  Verdict (operator fills in)

* **(a) Strong** — v4 generalizes; ship `clip_end` fallback as the
  semantic clean-up of v3.  The fact that 0 / 15 selections
  changed vs v3 is a feature, not a bug — it confirms the v3
  result was already correct under the implicit semantics.
* **(b) Mixed** — v4 is a no-op behaviourally and the still-open
  d005-style failures (single qualifying span placed in the wrong
  half of the clip) need a different lever (relax
  `MIN_RUN_FRAMES`, density-based selection, or motion fusion).
* **(c) Failed** — v4 visibly regresses on something that was fine
  in v3 (would be a bug, since the math says the outputs are
  identical — investigate).

**Recommendation if (a):** stop iterating on the *anchor* lever and
move to the next variable (almost certainly `MIN_RUN_FRAMES`
relaxation for short bursts like d005 / d014, or a density-based
"longest contiguous action density per fixed window" selection
that doesn't depend on the exact `MIN_RUN_FRAMES` boundary).

Operator sign-off: ___________________________  date: __________

---

### Reproduction

```
python files/scripts/sub_clip_isolation_v4/extract_spans.py
SUB_CLIP_PADDING_S=1.5 python files/scripts/sub_clip_isolation_v4/extract_spans.py
```

Inputs (read-only): `scout_results_v2.jsonl`,
`clip_aggregates_v2.csv`, `delivery_window.mp4` per session/clip,
`window_debug.json` per session/clip, `labels.csv` per session,
`eyes/span_aggregator.py`, v3's `span_selection.csv` (for diff).

Outputs: `comparisons/*.mp4` (20), `gallery.mp4`,
`span_selection.csv`, `_titles/` (intermediate, includes section
divider cards used in the gallery).

## §8  Streaming-mode failure (2026-05-03 SRH-KKR live diagnostic)

Status: investigation only · 2026-05-03 · driven by live
post-restart deliveries in session `20260503_180900` showing
post-shot reactions / players walking / celebrations instead of
the actual delivery in most clips.

### §8.1  Symptom from live match

Operator review of `files/logs/deliveries/20260503_180900/d*` after
the 18:08 restart: the produced `delivery_window.mp4` clips
predominantly show post-delivery content (reactions, walking,
celebrations).  Only `d003` was reported as containing the actual
delivery.  Operator framed this as a regression versus the v4
pre-cut validation (17/20 perfect) that signed off Component 1
earlier today.

### §8.2  What the live data actually shows

**Tonight's clips were not produced by the streaming
`DeliverySpanSelector`.**  Every `window_debug.json` in the
session reports:

* `window_source: "fallback_pre_event_window"`
* `window_reason: "no_bowlers_end_span"`
* `open_scout_verdict: "no_match"`
* `use_open_scout_spans: false`
* fixed geometry: `clip_dur = 12.50 s`, `event_offset = 10.00 s`
  (= `event_ts − 10 s` … `event_ts + 2.5 s`)

The `[SHADOW-STATS]` heartbeats in
`logs/pipeline-2026-05-03-1808-srh-vs-kkr-RESTART2.log` confirm
`stage1_windows_opened: 0` and `stage2_spans_emitted: 0` for the
entire session — Stage 1 (`BroadcastModeFilter`) never went
`STATE_ACTIVE`, so Stage 2 never received Scout results.  The
`files/logs/openscout_shadow/69f98c9c.jsonl` file contains only the
header record; no spans were ever emitted in shadow.

So the operator's "wrong content" is actually the legacy
`fallback_pre_event_window` path — a fixed `[event_ts−10, event_ts+2.5]`
window — firing because `bowlers_end_span` detection was missing
across the post-restart deliveries.  That is a **separate bug**
from the Component 1 design question, and is the dominant cause of
tonight's bad clips.

### §8.3  But the design hypothesis is independently correct

Even though tonight's failures aren't Component 1 emissions, the
hypothesis the operator raised is structurally accurate and would
manifest the moment `USE_OPEN_SCOUT_SPANS=1` flips.  Pre-cut v4 vs
streaming Stage 2 differ on three load-bearing points:

| dimension | v4 pre-cut (`extract_spans.py`) | streaming (`delivery_span_selector.py`) |
|-----------|----------------------------------|-----------------------------------------|
| temporal bound | implicit `clip_duration` ceiling on every span (`end_ts ≤ clip_duration`) | none — spans can extend arbitrarily into post-event content |
| event anchor | `event_offset_s` known per clip; `select_span()` filters `midpoint ≤ anchor_target` and prefers `max end_ts ≤ anchor_target`, tie-break by `frame_count` | no `event_ts` input exists on the selector at all |
| emit cardinality | exactly **one** span chosen per clip | **every** qualifying span emits as it closes |

§2 of this memo records that across all 20 v4 clips the anchor
resolved to `clip_end` in 100% of cases — i.e., the entire v4
selection result was driven by the implicit `clip_duration` bound,
not by `event_offset_s`.  Removing that bound (which is exactly
what the streaming migration did, see
`files/eyes/delivery_span_selector.py:10-16`) deletes the only
mechanism v4 had to favour the delivery span over a later
post-event action span.

Concrete failure modes the streaming selector will exhibit on a
delivery whose Scout output is `[bowling-action] [reaction-walk]
[celebration]` with sub-`SOFT_GAP_TOLERANCE_S` gaps and no
`replay`/`ad` punctuation:

1. The aggregator's same-class soft-gap merge (≤ 2.5 s) fuses
   delivery + reaction + celebration into one extended action span.
   Padded by 1 s, the emitted window covers the entire post-event
   tail.  Stage 3 Qwen sees mostly post-shot content.
2. If a hard-close *does* fire mid-stream, multiple action spans
   emit per real delivery.  Component 3 dispatches Qwen on each;
   the operator sees several "deliveries" produced from one
   bowling event, only one of which is the real one.

The v4 dataset never exposed (1) because `clip_duration` always
truncated the post-event tail at the recorder boundary, and never
exposed (2) because the per-clip selector picked exactly one span.

### §8.4  Why pre-cut validation didn't catch this

The 17/20 v4 result was earned on clips whose right boundary
(`clip_end_ts`) was already cut **at or shortly after the score
event** — §2's table shows `event_offset_s − clip_duration` median
≈ 1.5 s.  The recorder did the temporal anchoring; v4's
`select_span()` only had to pick the latest action burst within an
already-tight window.  Streaming has no recorder-side cut and no
event input, so the selector must do the temporal anchoring itself
— and it currently does none.

### §8.5  Root cause

`DeliverySpanSelector` migrated v4's *closure rule* (replay/ad
hard-close, `MIN_RUN_FRAMES`, `MIN_ACTION_SPAN_S`, padding) but
**dropped v4's *selection rule*** (`select_span` with
`anchor_target`).  The migration docstring acknowledges this —
"there is no per-clip anchor here, so the v3/v4 anchor-selection
logic is dropped" — but treats the absence of the anchor as
acceptable.  It isn't: §2 of this memo proves the anchor (via the
`clip_end` collapse) was the load-bearing piece of v4's behaviour
on the validation corpus, not the closure rule.

### §8.6  Design options considered

| option | sketch | scope | gap |
|--------|--------|-------|-----|
| (a) **`mark_score_event(ts)` + buffered selection** | Pipeline calls `selector.mark_score_event(ts)` on score-delta detection.  Selector buffers closed spans for a grace period (~5 s post-event) and runs v4 `select_span(spans, anchor_target=ts)` over the buffer, emitting exactly one span per score event. | Stage 2 internal: replace `_pending` immediate-emit with score-event-keyed buckets; one new public method.  Pipeline integration: one new call site in the score-delta path. | Aligns streaming behaviour with the validated v4 logic.  Requires pipeline to surface score-event timestamps to Stage 2 (currently it doesn't). |
| (b) Aggressive replay/ad closure | Tighten hard-close pre-pass: any non-action class triggers `force_close`. | Stage 2 only, ~5 LOC. | Doesn't help when the post-event tail contains no replay/ad classes — and the live Scout class set is sparse, so this is the common case. |
| (c) Post-event filter without anchor input | Drop spans whose `start_ts` is past some heuristic "expected delivery" point. | Stage 2 only. | Requires a heuristic for "expected delivery" without an event_ts input.  No principled way to set it. |
| (d) Span-end clipping at first non-action class | When closing, retroactively clip `end_ts` to the last consecutive action frame, ignoring soft-gap-absorbed dissent. | Stage 2 only. | Reduces tail bleed (failure mode 1) but does nothing for failure mode 2 (multiple post-event spans). |

### §8.7  Recommendation

**(a)** — `mark_score_event(ts)` plus buffered single-emit
selection.  This is the only option that restores the v4 contract
(one delivery per score event, anchored to the event) rather than
patching symptoms.

Required pipeline integration:

1. Surface score-event timestamps to Stage 2.  Wherever the legacy
   pipeline currently fires its scoreboard-delta detection (the
   path that today populates `event_ts` in `window_debug.json`),
   add a call to `selector.mark_score_event(event_ts)`.  This is
   the same input v4 had in `event_offset_s`; the streaming
   selector simply never wired it up.
2. Stage 2 internal change: replace the immediate-emit pattern in
   `_on_aggregator_commit` / `_maybe_emit_ready` with an
   event-keyed buffer.  When `mark_score_event(ts)` fires, run v4
   `select_span(spans_in_window, anchor_target=ts)` over the spans
   that closed in some bounded pre-event window, emit exactly one
   `DeliverySpan`, and discard the rest.  Spans that close after
   the event without a matching score event eventually expire and
   are dropped (no emit).
3. `flush()` semantics: on `flush()`, run a final selection pass
   for any pending score event, then drop unmatched spans.

### §8.8  Test coverage gap

`files/tests/test_delivery_span_selector.py` exercises the
streaming closure rule (hard-close attribution, closure hold,
soft-gap dissent absorption, pending-emit ordering) but contains
**no test that asserts which span is picked when several action
spans close in proximity to a score event**.  Adding (a) requires
a new test class along the v4 selection rule's lines:

* multi-span scenario with one span ending just before
  `event_ts`, one straddling, one starting after — assert the
  v4 rule (filter `midpoint ≤ event_ts`, prefer `max end_ts ≤
  event_ts`) is reproduced byte-identically.
* score-event-with-no-spans, spans-with-no-score-event, multiple
  score events in flight (out-of-order, buffered).

### §8.9  Out of scope of this memo

* Tonight's actual `fallback_pre_event_window` failure (`no_bowlers_end_span`)
  is a Stage-1 / camera-detection issue, not a Component 1 issue.
  Tracked separately.
* `SOFT_GAP_TOLERANCE_S` tuning (separate live patch).
* `SpanAggregator` core changes — the recommendation above keeps
  the aggregator untouched, mirroring v4's "wrapper-only" discipline.
