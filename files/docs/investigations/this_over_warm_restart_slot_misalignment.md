# this_over slot misalignment on warm restart

## Context

Tonight's pipeline restart at 18:08 picked up KKR vs SRH innings 2 mid-over
at 8.4 (broadcast was actually showing 8.5 on the strip). U5 reported:

- "9.0" ball (the +1 run that took the score 98 → 99) was "missing" from
  the recent_overs panel post-restart.
- It "appeared in the 9.1 slot" once 9.1 was actually bowled.
- Display "recovered" after 9.1's DOT landed.

Live evidence — `logs/pipeline-2026-05-03-1808-srh-vs-kkr-RESTART2.log`:

| Frame | Time     | Score   | Overs | this_over after frame                    | Notes                                    |
|-------|----------|---------|-------|------------------------------------------|------------------------------------------|
| F20   | 18:10:17 | 96/1    | 8.4   | `[?,?,?,?]`                              | Cold-start (TO-WIN-derived 96/1, 8.4)    |
| F21   | 18:10:23 | 96 → 98 | 8.5*  | `[?,?,?,?]`                              | overs deferred 2/3, BED did NOT fire     |
| F22   | 18:10:28 | 98      | 8.5   | `[?,?,?,?,?]`                            | TIMEOUT-GAP-INFER added `?` for 8.5      |
| F26   | 18:10:40 | 98      | 8.5   | `[?,?,?,?,?]` (RESYNC + FLOOR re-pad)    | cold→warm cutover                        |
| F29   | 18:10:49 | 98 → 99 | 8.5 → 9.0 | `[?,?,?,?,?,1]` → archived as over 8 | `[BALL ✓] 1_RUNS \| 9.0`                  |
| F30   | 18:10:55 | 99      | 9.0   | `[]`                                     | hold-window 3s elapsed → flushed         |
| F53   | 18:12:26 | 99      | 9.1   | `['.']`                                  | First real ball of over 9 (DOT)          |

Broadcast strip's `this_over` field was `null` on every frame after the
restart, so we never had a chance to backfill from broadcast.

## Root cause — the user's diagnosis is wrong

The "off-by-one slot mapping" hypothesis is not the bug.

`ThisOverManager.on_ball_event` decodes the event's `over` field with a
fractional-aware mapping (`this_over.py:257-270`):

```
ev_over_str = "9.0"  →  v_int=9, v_frac=0  →  ev_over_logical = 9-1 = 8
```

i.e. a ball event reported at "9.0" is the **6th ball of over 8**, by
cricket convention (team_overs only ticks to "X.0" *after* the closing
delivery of over X-1 has been bowled). At F29 the pipeline correctly:

1. Appended the `1` token to the still-open over 8's `this_over`,
   producing `[?,?,?,?,?,1]` (slot 6 = ball 8.6).
2. Archived over 8 with that 6-token ribbon via `check_over_change(9.0)`.
3. Held the completed over visible for 3 s (`COMPLETED_OVER_HOLD_S`).
4. Started over 9 cleanly with the F53 DOT in slot 1.

The WS payload (`test_pipeline.py:4849`) and `ThisOver.tsx:23-62` are both
purely positional — they do not assign tokens to ball numbers, they just
left-align observed tokens and pad trailing slots. There is no
slot-to-ball-number mapping anywhere that could be "off by one".

## What actually went wrong

Two effects, both caused by the cold-start consensus path holding SM
behind the broadcast strip for ~6 seconds after restart:

**(1) Ball 8.5 (+2 runs) lost to a `?` placeholder.**

The broadcast strip read `98/1 (8.5)` from F20 onward, but the cold-start
TO-WIN regex derived `96/1 (8.4)` and SM held that for the consensus
streak. When SM finally caught up on F21-F22, it advanced score `96 → 98`
(F21) and overs `8.4 → 8.5` (F22) on **different** frames. BallEventDetector
requires both deltas in the same frame, so it never fired for ball 8.5.
`fill_strip_coverage_gap` then added a generic `?` for the missing slot,
discarding the `+2` runs.

Result: over 8's archive is `[?,?,?,?,?,1]` instead of `[?,?,?,?,2,1]`.
The 6th ball is correct; the 5th is silently zeroed.

**(2) Perceptual confusion.**

A user looking at over 8's recent-overs entry sees five `?` placeholders
followed by a lone `1`. The `1` is in the right slot (ball 8.6) but
visually feels orphaned — it's the only confirmed token amid five
unknowns, and it sits at the *end* of an over that the pipeline never
saw the start of. The user's intuition jumps to "this 1 must belong to
the next over" rather than "this 1 is the closing ball of an
otherwise-unobserved over".

## Linked issues

- **P2** (warm-restart placeholders): `fill_strip_coverage_gap` and the
  `_log_count_mismatch` / FLOOR pad always emit `?`, ignoring the score
  delta carried in the same overs-jump call. This is where the `+2` is
  lost.
- **U5** (UI perceived-misalignment): user-facing presentation of an
  over with five placeholders + one digit is ambiguous; users read it
  as "the digit is in the wrong slot" rather than "the placeholders
  are unfilled".

## Options

| Option | Approach | Pros | Cons |
|--------|----------|------|------|
| (a) | Carry ball-number per token to the WS / UI; render by absolute slot | Eliminates any future positional ambiguity | Schema + UI change; doesn't fix the lost-runs problem |
| (b) | When `fill_strip_coverage_gap` fires with `new_score - old_score > 0`, attribute the delta to the *last* padded slot (fill `2` instead of `?`) | Recovers ball 8.5's runs; ~10 LOC; same as how MULTI_BALL handles missed deliveries | Heuristic — assumes the score delta accrued on the most recently padded slot, not earlier ones |
| (c) | Re-derive `this_over` wholesale from the broadcast strip on every cold-start cutover | "Authoritative" feel | Strip's `this_over` was `null` for the entire post-restart window tonight, so this would have changed nothing in practice; long-tail it's lossier than incremental observation |
| (d) | Attach a small "Restarted mid-over — earlier balls not observed" badge to any over_history entry whose first observed token is not slot 1 | Pure UX clarity, no data change | Doesn't recover the lost run; needs UI wiring |

## Recommendation

**Option (b)**, with the score-delta attached to the last padded slot.

Decisive factor: it recovers real run data that was visible to the
pipeline (the +2 score delta was observed at F21, just not on the same
frame as the overs delta). The fix lives entirely inside
`fill_strip_coverage_gap`, parallels the existing MULTI_BALL placeholder
distribution, and needs no UI or schema change. (a) and (c) don't fix
the data loss; (d) is presentational and complementary, not a substitute.

Sketch:

```python
# in fill_strip_coverage_gap, after computing pad:
delta = (new_score or 0) - (old_score or 0)
for i in range(pad):
    last = (i == pad - 1)
    if last and delta > 0 and delta <= 6:
        token = str(delta) if delta else "."
        self.this_over.append(token)
        self.this_over_sources.append("gap_infer_score")
    else:
        self.this_over.append("?")
        self.this_over_sources.append("gap_infer")
```

The "attribute to last padded slot" heuristic is correct in the common
"score caught up one frame after overs" case (which is exactly tonight's
incident) and degrades gracefully when the assumption is wrong (any
mis-attributed digit is still `<= 6` runs and still recoverable by a
later real ball event via the existing replace-? logic in
`on_broadcast_override`).
