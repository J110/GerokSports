# Sub-clip delivery isolation v2 — Scout span extraction + visual review

Status: ready for operator review · 2026-05-03 · pipeline owner action item

This memo accompanies the artefacts produced by
`files/scripts/sub_clip_isolation/extract_spans.py`.  Goal: validate
whether v2 Scout outputs, processed through the existing
`SpanAggregator`, can isolate the actual delivery moment inside a
labelled `delivery_window.mp4` clip — i.e., is Scout-alone enough for
delivery boundary detection, or is motion fusion / temporal context
still required.

## §1  Methodology

### Clip selection

10 `real_delivery` clips drawn from
`files/scripts/path_a_baseline/clip_aggregates_v2.csv`, spanning
`action_ratio` bands (HIGH ≥0.85, MED 0.5–0.7, LOW <0.5) and event
types across both `20260420_202239` and `20260421_195050` sessions.

| # | session/clip       | label / event   | ar    | max_run | band |
|---|--------------------|-----------------|-------|---------|------|
| 1 | 20260420_202239/d004 | real_delivery / 2_RUNS  | 0.955 | 21 | HIGH |
| 2 | 20260421_195050/d048 | real_delivery / 1_RUNS  | 1.000 | 15 | HIGH |
| 3 | 20260421_195050/d016 | real_delivery / 1_RUNS  | 0.857 | 7  | HIGH |
| 4 | 20260420_202239/d010 | real_delivery / WICKET  | 0.625 | 7  | MED  |
| 5 | 20260420_202239/d020 | real_delivery / SIX     | 0.688 | 8  | MED  |
| 6 | 20260421_195050/d024 | real_delivery / 2_RUNS  | 0.692 | 11 | MED  |
| 7 | 20260420_202239/d002 | real_delivery / 1_RUNS  | 0.636 | 7  | MED  |
| 8 | 20260420_202239/d025 | real_delivery / 1_RUNS  | 0.375 | 7  | LOW  |
| 9 | 20260421_195050/d022 | real_delivery / DOT     | 0.200 | 2  | LOW  |
|10 | 20260421_195050/d031 | real_delivery / 1_RUNS  | 0.133 | 1  | LOW  |

Bonus diversity: WICKET, SIX, 1/2_RUNS, DOT are all represented; LOW
band is intentionally weighted toward the worst-case clips so the
"no span found" failure mode shows up.

### SpanAggregator config

Per-frame v2 results are loaded from
`files/scripts/path_a_baseline/scout_results_v2.jsonl` and replayed
into `eyes.span_aggregator.SpanAggregator` with `frame_index` used as
the synthetic timestamp (1 fps cadence).  Two configs run side-by-side:

* **default** — `MIN_SPAN_FRAMES=2`, `SAME_CLASS_GAP_TOL=1`,
  `SOFT_GAP_TOLERANCE_S=2.5`, `MIN_ACTION_SPAN_S=2.0`.  Production
  values from `eyes/span_aggregator.py`.
* **p22-tuned** — same as default but `SOFT_GAP_TOLERANCE_S=5.0` per
  the F1 fix identified earlier in the Path A iteration memo.

`SpanAggregator` is consumed as-is — no edits.  `force_close()` runs
after the last frame of each clip so the trailing open span is
committed before snapshot.

### Sub-span pick rule

For each clip, of all closed `action`-class spans, keep those with
`frame_count ≥ 5` (the `max_consecutive_action ≥ 5` operating point
that gave F1=0.934 in the Path A v2 iteration) AND
`duration_s ≥ MIN_ACTION_SPAN_S=2.0`.  Pick the longest by
`frame_count`.  If zero qualifying spans, record `(0, 0)` and tag
`no_qualifying_span`.  If multiple qualifying spans, tag
`multi_qualifying_n=N_picked_longest`.

A diagnostic fallback also reports the longest-by-frame `action` span
that meets `MIN_ACTION_SPAN_S` but is below the 5-frame threshold,
tagged `below_min_run_5`, so a near-miss isn't invisible.

## §2  Per-clip span selection results

Source: `files/scripts/sub_clip_isolation/span_selection.csv`.

| clip                   | event   | ar    | n_spans | sub-span (s)   | n_frames | note                  |
|------------------------|---------|-------|---------|----------------|----------|-----------------------|
| 20260420_202239/d004   | 2_RUNS  | 0.955 | 1       | 2.0 → 21.0     | 20       | single_qualifying_span |
| 20260421_195050/d048   | 1_RUNS  | 1.000 | 1       | 0.0 → 14.0     | 15       | single_qualifying_span |
| 20260421_195050/d016   | 1_RUNS  | 0.857 | 1       | 0.0 → 6.0      | 7        | single_qualifying_span |
| 20260420_202239/d010   | WICKET  | 0.625 | 1       | 0.0 → 6.0      | 7        | single_qualifying_span |
| 20260420_202239/d020   | SIX     | 0.688 | 1       | 0.0 → 11.0     | 11       | single_qualifying_span |
| 20260421_195050/d024   | 2_RUNS  | 0.692 | 1       | 9.0 → 20.0     | 11       | single_qualifying_span |
| 20260420_202239/d002   | 1_RUNS  | 0.636 | 1       | 10.0 → 15.0    | 6        | single_qualifying_span |
| 20260420_202239/d025   | 1_RUNS  | 0.375 | 1       | 7.0 → 13.0     | 7        | single_qualifying_span |
| 20260421_195050/d022   | DOT     | 0.200 | 0       | —              | 0        | no_qualifying_span    |
| 20260421_195050/d031   | 1_RUNS  | 0.133 | 0       | —              | 0        | no_qualifying_span    |

Default and P22-tuned configs produced identical sub-spans on every
selected clip — the soft-gap relaxation from 2.5 s to 5.0 s did not
restitch any spans here.  This matches expectation: at 1 fps Scout
cadence, gaps within a clip are dominated by the single-frame
flicker handled by `SAME_CLASS_GAP_TOL`, not multi-second pauses.
Where the P22 fix helps F1 is at the inter-clip boundary, not within
a single delivery_window.

## §3  Failure modes observed

**Zero qualifying spans (2/10):**

* **20260421_195050/d022** (DOT, ar=0.20, max_run=2) — 13 of 25
  frames classified `replay`.  Scout sees the cutaway/replay segment
  as the dominant content; only 5 isolated `action` frames remain,
  none in a 5+ run.
* **20260421_195050/d031** (1_RUNS, ar=0.13, max_run=1) — 11 of 15
  frames classified `replay`, 2 `action` frames are non-consecutive
  singletons.  Real delivery is buried inside a clip dominated by
  replay broadcast.

Both clips are in the LOW band by design.  The "no span" failure
mode is itself a useful finding: when `max_run < 5`, the v2 pipeline
will deliver zero candidate from Scout-alone — these are the cases
where motion-signal fusion is most likely to add value.

**Multiple competing spans:** none in the sampled set.  Every clip
that produced a qualifying span produced exactly one.

**Suspicious aggregate-shape sub-spans:**

* **20260420_202239/d002** (ar=0.64, dur=21.9 s) — picked sub-span is
  10–15 s, sitting near the *middle* of a 22 s clip.  The clip was
  manually labelled `real_delivery` for over 11.1, so the actual ball
  bowled likely happens early in the clip; the chosen 10–15 s window
  is suspect and may capture a delayed action segment (post-replay
  cricket-on-ground footage).  Operator should confirm visually.
* **20260421_195050/d024** (ar=0.69, dur=34.5 s) — picked sub-span is
  9–20 s of a 34 s clip.  Long total duration suggests this window
  contains the pre-pitch + delivery + post-shot live-action stretch
  before the broadcast cut to a replay/closeup.  Sub-span being far
  from the very start is plausible here, not necessarily wrong.
* **20260420_202239/d025** (LOW band, ar=0.37) — span 7–13 s isolates
  a 7-frame `action` stretch even though overall action_ratio is 0.37.
  This is exactly the case `SpanAggregator` is built for: a low
  global ratio with a tight local action burst.  Worth checking
  whether the burst is the bowling motion or post-shot reaction.

**Below-threshold near-misses:** none — every clip with action frames
either crossed the 5-frame bar or had 1–2 isolated action frames.
There were no clips whose longest action span was 3 or 4 frames.

## §4  Side-by-side rendering artefacts

Layout: 1280×360 frame; left half (640×360) is the original
`delivery_window.mp4`, right half is the trimmed sub-span scaled to
the same dimensions and time-padded with black (`tpad`) so both halves
end at the same wall-clock instant relative to the original
timeline.  The right half therefore appears mid-frame and runs to
its end before going black — the operator can scrub the original on
the left and see whether the right-side sub-span fires while the
delivery is happening, or while a replay/cutaway is on screen.

A two-line text overlay at the bottom shows
`session/clip  label  event_type` and
`ar  max_run  sub-span  cfg`.  Text is rendered to a transparent PNG
via Pillow and composited with `overlay` because the locally-built
ffmpeg lacks libfreetype (drawtext is unavailable); the PNG-overlay
path is self-contained and produced no rendering issues.

For the two `no_qualifying_span` clips, both halves play the
original (right side has no trim) and the overlay flags `NO_SPAN` so
the operator can still review what the pipeline *missed*.

Audio is dropped (`-an`) because the right-half time-padding doesn't
have an obvious audio mapping.

Outputs:

* `files/scripts/sub_clip_isolation/comparisons/<session>_<clip>_comparison.mp4` (10 files)
* `files/scripts/sub_clip_isolation/gallery.mp4` (~193 s, 10 clips
  with 1.5 s title cards between them)
* `files/scripts/sub_clip_isolation/span_selection.csv`

## §5  Operator review prompt

For each clip in `gallery.mp4`, answer two questions:

* **(a)** Does the right-half sub-span CONTAIN the actual delivery
  moment (run-up + bowling + ball into play)?  Yes / No / Partial.
* **(b)** Does the right-half sub-span EXCLUDE the replays, cutaways,
  closeups, and crowd shots in the clip?  Yes / No / Partial.

Suggested fill-in table (paste the result back into §6):

```
clip                            (a) contains  (b) excludes  notes
20260420_202239/d004            Y/N/P         Y/N/P         …
20260421_195050/d048            Y/N/P         Y/N/P         …
20260421_195050/d016            Y/N/P         Y/N/P         …
20260420_202239/d010            Y/N/P         Y/N/P         …
20260420_202239/d020            Y/N/P         Y/N/P         …
20260421_195050/d024            Y/N/P         Y/N/P         …
20260420_202239/d002            Y/N/P         Y/N/P         …
20260420_202239/d025            Y/N/P         Y/N/P         …
20260421_195050/d022 (NO_SPAN)  N             —             miss
20260421_195050/d031 (NO_SPAN)  N             —             miss
```

## §6  Verdict (operator fills in)

Pick one, append rationale:

* **(a) Strong** — sub-spans reliably isolate deliveries.  Ship
  Scout-only architecture; treat NO_SPAN clips as the known
  low-confidence corner.
* **(b) Mixed** — works for some clips but fails on others.
  Document the failure pattern (e.g., "fails when replay precedes
  delivery", "trims pre-pitch run-up") and decide whether to ship
  Scout-only with a flagged-clip review queue, or block on a
  motion-signal augmentation.
* **(c) Failed** — sub-spans consistently capture wrong content
  (replay segments, post-shot footage, closeups).  Need motion
  fusion or temporal context before Scout-alone can drive boundary
  detection.

Operator sign-off: ___________________________  date: __________

---

### Reproduction

```
python files/scripts/sub_clip_isolation/extract_spans.py
```

Inputs (read-only): `scout_results_v2.jsonl`,
`clip_aggregates_v2.csv`, `delivery_window.mp4` per session/clip,
`labels.csv` per session, `eyes/span_aggregator.py`.

Outputs: `comparisons/*.mp4`, `gallery.mp4`, `span_selection.csv`,
`_titles/` (intermediate, can be deleted).
