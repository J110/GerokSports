# Sub-clip delivery isolation v3 — 1 s padding + event_ts anchoring

Status: ready for operator review · 2026-05-03 · iteration on
`sub_clip_delivery_isolation_v2.md`

This memo accompanies artefacts produced by
`files/scripts/sub_clip_isolation_v3/extract_spans.py`.  Goal: address
v2's specific failures (`d005` picked a replay-bookended span,
`d032` picked a pre-delivery setup span, `d013` was over-padded into
near-full clip) by reducing padding from 2 s to 1 s and adding
event_ts-anchored span selection.  Validate against v2's same 10
clips PLUS 5 new clips with no overlap.

## §1  Methodology — v3 changes

Two wrapper-side changes; `eyes/span_aggregator.py` core untouched.

### §1.1  Padding 2.0 s → 1.0 s

`SUB_CLIP_PADDING_S` default reduced; env-overridable.  Targets v2's
"long span padded into near-full clip" behaviour (e.g. v2 d013 padded
to `[0-16.52]` of a 16.54 s clip — there is no daylight to recover
when both ends clamp).

### §1.2  event_ts anchoring

Each clip's `window_debug.json` carries wall-clock `event_ts` and
`clip_start_ts`.  Compute `event_offset_s = event_ts - clip_start_ts`.

Selection rule:

1. **Candidates:** action spans with `frame_count ≥ 5` and
   `duration_s ≥ MIN_ACTION_SPAN_S=2.0` (unchanged from v2).
2. **Anchor filter:** drop candidates whose midpoint
   (`(start + end)/2`) is past `event_offset_s` — those are
   structurally post-event content (replays, crowd reactions,
   commentary cutaways).
3. **Pick:** of the survivors, prefer the span with the *largest*
   `end_ts ≤ event_offset_s` (i.e. ending closest-to-but-not-after
   the score event).  If every survivor straddles the event
   (`end_ts > event_offset_s`), pick the smallest `end_ts` among
   them as the least-overshooting straddler.  Tie-break by
   `frame_count`.
4. **Fallback:** if `event_offset_s` is missing or ≤ 0, fall back
   to v2's "longest by `frame_count`" rule (basis flag
   `fallback_no_event_ts`).  If the anchor filter eliminates all
   candidates, also fall back to longest, but flag basis
   `anchor_filtered_all`.

Selection-basis tags written to the CSV: `anchor_end_before_event`
(majority case in this dataset), `anchor_straddle_event`,
`anchor_filtered_all`, `fallback_no_event_ts`,
`no_qualifying_span`, `below_min_run_5`.

### §1.3  Data-quality observation about event_offset_s

In this dataset, `event_offset_s > clip_duration` for **14 of 15**
clips.  The score event is detected ~1–10 s after the
`retrospective_span` window closes, by design of the window source.
Consequence: the midpoint filter is rarely the active gate, but the
"latest end before event" preference is a real change against v2's
"longest by count" rule, and it materially differs whenever a clip
has > 1 qualifying span.

## §2  v3-vs-v2 selection diff on the original 10 clips

| clip                   | event   | v2 padded     | v3 padded      | changed | basis                       |
|------------------------|---------|---------------|----------------|---------|------------------------------|
| 20260420_202239/d012   | 1_RUNS  | 0.0 → 12.98   | 0.0 → 12.98    | no      | anchor_end_before_event       |
| 20260420_202239/d032   | 1_RUNS  | 0.0 → 12.0    | **15.0 → 25.51** | **YES (selection swap)** | anchor_end_before_event_n=2 |
| 20260421_195050/d013   | 1_RUNS  | 0.0 → 16.52   | 0.0 → 16.0     | yes (pad shrink) | anchor_end_before_event |
| 20260420_202239/d033   | SIX     | 0.0 → 15.0    | 0.0 → 14.0     | yes (pad shrink) | anchor_end_before_event |
| 20260420_202239/d005   | DOT     | 0.0 → 7.0     | 0.0 → 6.0      | yes (pad shrink) | anchor_end_before_event |
| 20260421_195050/d066   | FOUR    | 0.0 → 13.0    | 0.0 → 12.0     | yes (pad shrink) | anchor_end_before_event |
| 20260421_195050/d008   | 1_RUNS  | 9.0 → 22.0    | 10.0 → 21.0    | yes (pad shrink) | anchor_end_before_event |
| 20260420_202239/d017   | 1_RUNS  | 11.0 → 20.0   | 12.0 → 19.0    | yes (pad shrink) | anchor_end_before_event |
| 20260421_195050/d021   | 1_RUNS  | NO_SPAN       | NO_SPAN        | no      | no_qualifying_span            |
| 20260421_195050/d027   | SIX     | 0.0 → 8.0     | 1.0 → 7.0      | yes (pad shrink) | anchor_end_before_event |

**Selection swaps:** 1 of 10 (d032).  All other "changed" entries
are mechanical 1 s padding contractions on the same underlying
span.  d012 is unchanged because `pad_end` was already clamped to
`clip_duration` in v2.

### Targeted-failure verdicts

* **d032 — fixed (mechanically):** v2 picked the longest (11-frame)
  span at `[0-10]`.  v3 picked the second qualifying span at
  `[16-25]` (n=10) because its end_ts=25 is closer to
  `event_offset=26.79 s` than end_ts=10.  This matches the
  hypothesis that the post-event-adjacent span is the real
  delivery, not the pre-delivery setup that filled the early clip.
  Operator confirms visually.
* **d013 — partially addressed:** padding shrank from 16.52 s to
  16.0 s of a 16.54 s clip.  Still essentially the full clip; the
  underlying single 16-frame span genuinely covers the entire clip
  (Scout saw action throughout).  No anchoring win here because
  there's only one candidate.
* **d005 — NOT fixed by anchoring:** only one qualifying span exists
  (`[0-5]`, n=6).  The "real delivery" allegedly later in the clip
  (per operator) corresponds to a 4-frame action stretch
  (`[12-15]`) that fails `MIN_RUN_FRAMES=5`.  Anchoring can re-rank
  candidates but can't synthesise new ones; relaxing
  `MIN_RUN_FRAMES` to 4 here would surface the right span but is
  out of scope for v3 (one variable change at a time).  Documented
  as a known v3 limitation; flag for v4.
* **d021 — unchanged (Scout-side limit):** still `NO_SPAN` because
  `max_run=2`.  No aggregation rule can rescue it.

## §3  New 5-clip selection results

Excluded from v1+v2: see preamble of `extract_spans.py` (`V2_CLIPS`
list defines v3's first 10; the 5 below are picked from the
remaining `real_delivery` clips).

| clip                   | event   | ar    | max_run | replay | clip_dur | event_off | raw            | padded         | basis                  |
|------------------------|---------|-------|---------|--------|----------|-----------|----------------|----------------|------------------------|
| 20260420_202239/d015   | 1_RUNS  | 1.000 | 23 | 0  | 23.10 s | 24.05 s | 0.0 → 22.0 | 0.0 → 23.0     | anchor_end_before_event |
| 20260421_195050/d029   | 1_RUNS  | 1.000 | 10 | 0  | 9.94 s  | 12.14 s | 0.0 → 9.0  | 0.0 → 9.94     | anchor_end_before_event |
| 20260420_202239/d029   | DOT     | 0.700 | 13 | 0  | 19.93 s | 21.01 s | 0.0 → 14.0 | 0.0 → 15.0     | anchor_end_before_event |
| 20260421_195050/d055   | 1_RUNS  | 0.583 | 11 | 0  | 23.53 s | 25.13 s | 6.0 → 17.0 | 5.0 → 18.0     | anchor_end_before_event |
| 20260421_195050/d060   | 1_RUNS  | 0.455 | 5  | 0  | 10.11 s | 11.21 s | 0.0 → 4.0  | 0.0 → 5.0      | anchor_end_before_event |

Diversity: 2 HIGH (d015 ar=1.000, d029 ar=1.000), 2 MED (d029 sess1
ar=0.700, d055 ar=0.583), 1 LOW (d060 ar=0.455).  Event types:
1_RUNS × 4, DOT × 1.  Both sessions represented.

All 5 produced a qualifying span; none triggered hard-close.  d055
is the most interesting — it produced a span starting at 6 s of a
23.5 s clip, suggesting the early portion was non-action content
(probably wide stadium shot or replay before the live delivery).

## §4  Anchor effectiveness analysis

Across all 15 clips:

* **Selection basis distribution:** 14 `anchor_end_before_event` (1
  with `_n=2` annotation), 1 `no_qualifying_span`.  Zero
  `anchor_filtered_all`, `anchor_straddle_event`, or
  `fallback_no_event_ts`.
* **Hard-close events:** 26 across 4 clips (same as v2 — pre-pass
  unchanged).
* **Selection swaps from v2 (excluding d021 NO_SPAN):** 1 of 9
  (d032).  This is the ceiling: only 1 of the original 10 clips had
  a multi-candidate set, and the v2 longest-by-count vs v3
  closest-to-event preference disagreed there.  All other 8 clips
  with v2 selections had a single candidate, where the swap rule
  has no effect.
* **Padding shrinks:** 8 of 9 clips with selections produced a
  smaller `padded_*` window than v2.  Clip-side bound was
  unchanged for d012 (clamped both sides in both v2 and v3).
* **Direction vs operator labels (where known):**
  * d032 → moved span window from `[0-12]` to `[15-25.51]`.
    Operator-reported v2 failure was "caught pre-delivery setup,
    cut off before run-up"; v3 swap relocates the window to the
    post-event-adjacent action burst.  *Operator must confirm
    visually whether the new window indeed contains the bowling.*
  * d005 → unchanged span; padding shrank.  Operator-reported
    failure was "caught replay, missed delivery".  v3 does NOT
    fix this; the failure is upstream of selection (the actual
    delivery action stretch is too short for `MIN_RUN_FRAMES=5`).
  * d013 → unchanged span; padding shrank.  Operator-reported
    failure was "padded to nearly full clip"; v3 trims 0.5 s but
    still fills the clip because the underlying span itself does.
* **Fallbacks:** zero `anchor_filtered_all` triggered → S2 not
  exercised in this dataset.  Zero `fallback_no_event_ts` → S1 not
  exercised.

Conclusion on anchoring as a one-variable change: **clean and
defensible, but limited reach**.  In this 15-clip set the rule only
flipped 1 selection (d032), because every other clip had a single
qualifying span.  Multi-candidate clips appear to be the minority
in v2 Scout output; for the rule to earn its keep at scale we'd
need either (a) `SOFT_GAP_TOLERANCE_S` lowered so spans fragment
more often (creating more multi-candidate cases) or (b) a Scout
prompt that distinguishes "delivery action" from "fielding /
celebration action", giving the anchor more meaningful
discrimination targets.

## §5  Operator review prompt

For each clip in
`files/scripts/sub_clip_isolation_v3/gallery.mp4` (10 v2-comparable
clips first, then 5 new), answer:

* **(a)** Does the right-half (anchored, 1 s-padded) sub-span
  CONTAIN the actual delivery — run-up → bowling → ball into play
  → shot resolution?  Yes / No / Partial.
* **(b)** Does the right-half sub-span correctly EXCLUDE the
  replays/cutaways/closeups?  Yes / No / Partial.
* **(c)** For the 10 v2-comparable clips, is v3 better/worse/same
  than v2?  Better / Worse / Same.

Suggested fill-in (paste back into §6):

```
clip                          (a)  (b)   v3 vs v2   notes
20260420_202239/d012          Y/P  Y/P   B/W/S
20260420_202239/d032 *SWAP*   Y/P  Y/P   B/W/S       KEY check: is post-event window correct?
20260421_195050/d013          Y/P  Y/P   B/W/S
20260420_202239/d033          Y/P  Y/P   B/W/S
20260420_202239/d005          Y/P  Y/P   B/W/S       v3 known limit; no swap possible
20260421_195050/d066          Y/P  Y/P   B/W/S
20260421_195050/d008 (hc=9)   Y/P  Y/P   B/W/S
20260420_202239/d017          Y/P  Y/P   B/W/S
20260421_195050/d021 NO_SPAN  N    —     S           Scout-side miss
20260421_195050/d027          Y/P  Y/P   B/W/S
20260420_202239/d015          Y/P  Y/P   N/A         new
20260421_195050/d029          Y/P  Y/P   N/A         new
20260420_202239/d029          Y/P  Y/P   N/A         new
20260421_195050/d055          Y/P  Y/P   N/A         new (span starts mid-clip)
20260421_195050/d060          Y/P  Y/P   N/A         new
```

## §6  Verdict (operator fills in)

* **(a) Strong** — v3 generalizes; ship 1 s padding + event_ts
  anchoring.  The d032 swap is correct; new clips look clean;
  d005 limitation is acceptable as known corner.
* **(b) Mixed** — anchoring helps where it can but reaches too
  little of the dataset to be worth the complexity, OR padding
  reduction trims real reaction content.  Document and decide.
* **(c) Failed** — v3 is no better than v2 in operator review.
  Roll back to v2 defaults and consider a different v4 lever
  (`MIN_RUN_FRAMES` relaxation, density-based selection, motion
  fusion).

Operator sign-off: ___________________________  date: __________

---

### Reproduction

```
python files/scripts/sub_clip_isolation_v3/extract_spans.py
SUB_CLIP_PADDING_S=0.5 python files/scripts/sub_clip_isolation_v3/extract_spans.py
```

Inputs (read-only): `scout_results_v2.jsonl`,
`clip_aggregates_v2.csv`, `delivery_window.mp4` per session/clip,
`window_debug.json` per session/clip, `labels.csv` per session,
`eyes/span_aggregator.py`, v2's `span_selection.csv` (for diff).

Outputs: `comparisons/*.mp4` (15), `gallery.mp4`,
`span_selection.csv`, `_titles/` (intermediate).
