# Sub-clip delivery isolation v2 — padding + replay/ad hard-close + fresh validation

Status: ready for operator review · 2026-05-03 · iteration on
`sub_clip_delivery_isolation.md`

This memo accompanies artefacts produced by
`files/scripts/sub_clip_isolation_v2/extract_spans.py`.  Goal: address
the v1 failure modes (start-late, end-early, no-span-found) by adding
two changes around the production `SpanAggregator` — symmetric
padding and a replay/ad hard-close pre-pass — then validate against
a fresh 10-clip set with zero overlap with v1.

## §1  Methodology — what changed vs v1

v1 outcome: 6 clips perfectly isolated, 2 partial (d002 started 2 s
late and missed the run-up; d016 ended 1–2 s early and clipped the
reaction), 2 missed entirely (d022, d031 — both in the LOW band).

Two wrapper-side fixes in v2 (the `eyes/span_aggregator.py` core is
NOT touched):

* **Symmetric padding** (`SUB_CLIP_PADDING_S`, default 2.0 s) on
  either side of the picked span, clamped to `[0, clip_duration]`.
  Targets the start-late / end-early v1 failures.
* **Replay/ad hard-close pre-pass** — every Scout per-frame result
  whose `scout_class` is `replay` or `ad` triggers
  `SpanAggregator.force_close(now=ts)` and is then dropped from the
  feed.  This bypasses `SAME_CLASS_GAP_TOL=1`, which would otherwise
  absorb a single replay flicker into a surrounding action span.
  Defensive change — not directly observed as a v1 failure mode but
  principled, and necessary before we can trust any sub-span that
  the aggregator emits.

Selection rule unchanged from v1: pick the longest action span with
`frame_count ≥ 5` (`max_consecutive_action ≥ 5` operating point) and
`duration_s ≥ MIN_ACTION_SPAN_S=2.0`.  No qualifying span → record
`(0, 0)` and tag `no_qualifying_span` — matches production where no
span = no Qwen call.

## §2  Fresh clip selection

Zero overlap with v1, which used
`{d002, d004, d010, d020, d025}` from `20260420_202239` and
`{d016, d022, d024, d031, d048}` from `20260421_195050`.

| # | session/clip       | label / event   | ar    | max_run | replay | band |
|---|--------------------|-----------------|-------|---------|--------|------|
| 1 | 20260420_202239/d012 | real_delivery / 1_RUNS | 1.000 | 13 | 0  | HIGH |
| 2 | 20260420_202239/d032 | real_delivery / 1_RUNS | 0.885 | 11 | 0  | HIGH |
| 3 | 20260421_195050/d013 | real_delivery / 1_RUNS | 0.941 | 16 | 0  | HIGH |
| 4 | 20260420_202239/d033 | real_delivery / SIX    | 0.591 | 11 | 3  | MED  |
| 5 | 20260420_202239/d005 | real_delivery / DOT    | 0.688 | 6  | 1  | MED  |
| 6 | 20260421_195050/d066 | real_delivery / FOUR   | 0.625 | 7  | 0  | MED  |
| 7 | 20260421_195050/d008 | real_delivery / 1_RUNS | 0.565 | 10 | 9  | MED  |
| 8 | 20260420_202239/d017 | real_delivery / 1_RUNS | 0.480 | 7  | 0  | LOW  |
| 9 | 20260421_195050/d021 | real_delivery / 1_RUNS | 0.238 | 2  | 13 | LOW  |
|10 | 20260421_195050/d027 | real_delivery / SIX    | 0.389 | 6  | 0  | LOW  |

Even split across sessions (5/5).  Event-type variety: 1_RUNS, SIX,
FOUR, DOT.  Two clips intentionally chosen for replay-heavy
behaviour to exercise the new hard-close (d008 with 9 replay
frames, d021 with 13).

## §3  Aggregation changes

### §3.1  Padding

```
pad_start = max(0, span.start_ts - SUB_CLIP_PADDING_S)
pad_end   = min(clip_duration, span.end_ts + SUB_CLIP_PADDING_S)
```

`SUB_CLIP_PADDING_S` defaults to `2.0` and is overridden via
environment variable.  Clamping flags (`clamped_start`,
`clamped_end`) are recorded in the CSV when the pad runs into a
clip boundary; that's frequent in this set because Scout frames are
sampled at 1 fps starting at frame 0, so a span whose first action
frame is index 0 already touches the start of the clip.

### §3.2  Replay/ad hard-close pre-pass

Implemented as a wrapper around the SpanAggregator feed loop (chosen
over a sentinel-injection approach because it requires zero
SpanAggregator changes):

```python
for fr in frames:
    cls = fr.get("scout_class")
    if cls in {"replay", "ad"}:
        agg.force_close(now=ts)        # commit any open action span
        hard_closes += 1
        continue                       # do NOT pass the frame through
    elif cls:
        agg.add_classification(ts, cls, text=fr.get("raw_description"))
agg.force_close()                       # close trailing span
```

Because replay/ad frames are dropped from the feed, the aggregator
only ever observes `action`, `other`, `unknown`.  The first
replay/ad frame inside an action burst commits the burst at that
timestamp; the next action frame opens a new span.  Without this
pre-pass, a single dissenting `replay` would be absorbed under the
default `SAME_CLASS_GAP_TOL=1`, silently re-stitching across a
broadcast cut.

## §4  Per-clip span selection results

Source: `files/scripts/sub_clip_isolation_v2/span_selection.csv`.

| clip                   | event   | ar    | hc | n_spans | raw (s)        | padded (s)     | clamp | note |
|------------------------|---------|-------|----|---------|----------------|----------------|-------|------|
| 20260420_202239/d012   | 1_RUNS  | 1.000 | 0  | 1       | 0.0  → 12.0    | 0.0  → 12.98   | s,e   | single |
| 20260420_202239/d032   | 1_RUNS  | 0.885 | 0  | 2       | 0.0  → 10.0    | 0.0  → 12.0    | s     | multi_n=2_picked_longest |
| 20260421_195050/d013   | 1_RUNS  | 0.941 | 0  | 1       | 0.0  → 15.0    | 0.0  → 16.52   | s,e   | single |
| 20260420_202239/d033   | SIX     | 0.591 | 3  | 1       | 0.0  → 13.0    | 0.0  → 15.0    | s     | single |
| 20260420_202239/d005   | DOT     | 0.688 | 1  | 1       | 0.0  → 5.0     | 0.0  → 7.0     | s     | single |
| 20260421_195050/d066   | FOUR    | 0.625 | 0  | 1       | 0.0  → 11.0    | 0.0  → 13.0    | s     | single |
| 20260421_195050/d008   | 1_RUNS  | 0.565 | 9  | 1       | 11.0 → 20.0    | 9.0  → 22.0    | —     | single |
| 20260420_202239/d017   | 1_RUNS  | 0.480 | 0  | 1       | 13.0 → 18.0    | 11.0 → 20.0    | —     | single |
| 20260421_195050/d021   | 1_RUNS  | 0.238 | 13 | 0       | —              | —              | —     | no_qualifying_span |
| 20260421_195050/d027   | SIX     | 0.389 | 0  | 1       | 2.0  → 6.0     | 0.0  → 8.0     | —     | single |

Headline: **9/10 clips** produced a qualifying span, vs 8/10 in v1.
Only `20260421_195050/d021` (LOW band, 13 of 21 frames classified
`replay`) had no span.  Padding extended a meaningful window in
4 clips (d008, d017, d027, d033) and was harmlessly clamped on the
remaining clips whose raw span already touched a boundary.

The single multi-span result (`d032`) is interesting: even with no
replay/ad frames, the aggregator emitted two separate action spans
in a 25.5 s clip, evidence of an internal `other` (closeup or wide
shot) gap > `SOFT_GAP_TOLERANCE_S=2.5`.  We picked the longer
11-frame span; the second was shorter and behind.

## §5  Hard-close trigger analysis

| clip                   | replay frames | ad | hard_closes fired | spans after hardclose |
|------------------------|---------------|----|--------------------|------------------------|
| 20260420_202239/d012   | 0             | 0  | 0                  | 1 |
| 20260420_202239/d032   | 0             | 0  | 0                  | 2 |
| 20260421_195050/d013   | 0             | 0  | 0                  | 1 |
| 20260420_202239/d033   | 3             | 0  | 3                  | 1 |
| 20260420_202239/d005   | 1             | 0  | 1                  | 1 |
| 20260421_195050/d066   | 0             | 0  | 0                  | 1 |
| 20260421_195050/d008   | 9             | 0  | 9                  | 1 |
| 20260420_202239/d017   | 0             | 0  | 0                  | 1 |
| 20260421_195050/d021   | 13            | 0  | 13                 | 0 |
| 20260421_195050/d027   | 0             | 0  | 0                  | 1 |

* Total hard-close events: **26** across 10 clips.  All from
  `replay`; zero `ad` triggers in this fresh set.
* `d008` is the strong validation: 9 replay frames inside a 23-frame
  clip would have invited multiple absorb-and-restitch artefacts
  under default soft-gap behaviour; the pre-pass yielded a clean
  single 10-frame action span late in the clip (`raw=[11-20s]`,
  padded `[9-22s]`), which is consistent with delivery-then-replay
  broadcast structure.
* `d021` triggered hard-close on 13 frames but still produced no
  qualifying span — the residual `action` frames were 2 isolated
  singletons.  This is a `max_run=2` Scout-side limitation, not an
  aggregation failure; no aggregation change can rescue a clip with
  no consecutive action frames.
* No clip was over-fragmented by the hard-close: the only multi-span
  outcome (`d032`) had zero replay/ad frames and the split was
  driven by an `other`-class gap, not by hardclose.  This addresses
  stop-condition S2 — the replay/ad classifier is not too
  aggressive at the moment.

## §6  Operator review prompt

For each clip in
`files/scripts/sub_clip_isolation_v2/gallery.mp4`, answer:

* **(a)** Does the right-half (padded) sub-span CONTAIN the actual
  delivery — run-up → bowling → ball into play → shot resolution?
  Yes / No / Partial.
* **(b)** Does the right-half sub-span correctly EXCLUDE the
  replays/cutaways/closeups?  Yes / No / Partial.
* **(c)** Compared to v1's analogous-band clip, does padding +
  hard-close visibly improve the isolation?  Yes / No / Mixed.

Suggested fill-in (paste back into §7):

```
clip                            (a) contains  (b) excludes  vs v1   notes
20260420_202239/d012            Y/N/P         Y/N/P         Y/N/M   …
20260420_202239/d032            Y/N/P         Y/N/P         Y/N/M   …
20260421_195050/d013            Y/N/P         Y/N/P         Y/N/M   …
20260420_202239/d033 (hc=3)     Y/N/P         Y/N/P         Y/N/M   …
20260420_202239/d005 (hc=1)     Y/N/P         Y/N/P         Y/N/M   …
20260421_195050/d066            Y/N/P         Y/N/P         Y/N/M   …
20260421_195050/d008 (hc=9)     Y/N/P         Y/N/P         Y/N/M   …  KEY
20260420_202239/d017            Y/N/P         Y/N/P         Y/N/M   …
20260421_195050/d021 NO_SPAN    N             —             N/A     scout-side miss
20260421_195050/d027            Y/N/P         Y/N/P         Y/N/M   …
```

## §7  Verdict (operator fills in)

* **(a) Strong** — v2 generalizes; padding + hard-close earn their
  keep, ship to production.
* **(b) Mixed** — specific failures observed.  Document the
  pattern (e.g., padding overshoots into ad break, hard-close fires
  on a misclassified replay, etc.) and decide on follow-up.
* **(c) Failed** — v2 doesn't help relative to v1 baseline.  Need a
  different approach (motion fusion / temporal context).

Operator sign-off: ___________________________  date: __________

---

### Reproduction

```
python files/scripts/sub_clip_isolation_v2/extract_spans.py
SUB_CLIP_PADDING_S=3.0 python files/scripts/sub_clip_isolation_v2/extract_spans.py
```

Inputs (read-only): `scout_results_v2.jsonl`,
`clip_aggregates_v2.csv`, `delivery_window.mp4` per session/clip,
`labels.csv` per session, `eyes/span_aggregator.py`.

Outputs: `comparisons/*.mp4`, `gallery.mp4`, `span_selection.csv`,
`_titles/` (intermediate).
