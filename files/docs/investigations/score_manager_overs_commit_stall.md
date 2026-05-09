# ScoreManager overs commit stall (F231-F243)

Source log: `logs/pipeline-2026-05-03-2058--stage1ready.log`
Window: F213 → F244 (21:08:54 → 21:10:49), STATE frozen at `PBKS 141-8 (18.0)`
Linked: `overs_fix_skip_regression_false_positive.md`,
`wide_breaks_this_over_slot_count.md`

## TL;DR

The blocker is **not** in ScoreManager's overs-commit gating. Every
strip-derived `(18.1)` / `(18.2)` read in F231-F243 was rejected
**upstream of ScoreManager** by frame-poison guards in
`test_pipeline.py`. The scorer's `Changes:` line records the rejection
verbatim as `FRAME_POISONED:144` / `FRAME_POISONED:145` and `BEFORE_*`
fields equal `AFTER_*` on every frame in the stall window — i.e.
ScoreManager was never offered an overs proposal to commit. The 18.0
→ 18.2 jump at F244 fired through the **graphic fast-path**
(`cam=graphic phase=graphic`, `[CAM-GRAPHIC-FAST-PATH-READ]`), which
bypasses the strip-overlay / row-delta poison guards entirely.

So the question "why did ScoreManager refuse 18.1?" inverts: it never
saw 18.1. The upstream strip-pipeline poisoned it.

## Phase A — Where the gate actually lives

### A1. ScoreManager overs path (no gate fired here)

Searched `files/score_manager.py` for overs-commit gating and the
deferred-score machinery:

- `_deferred_score` / `_deferred_frames` (line 248-249, 1592-1725):
  defer-fire for "score advanced but overs didn't" — only relevant
  when extractor *did* advance score and overs lagged. Did not fire
  in F231-F243.
- `_overs_regress_streak` (line 257-259, threshold 2): protects
  COLD_START re-entry on a single-frame regression. Not in path
  (no regression observed at F231+).
- Reconcile site uses `team_overs=overs_for_reconcile` (line 1900)
  — this is the *consumer*, fed by upstream extracted state.

No multi-frame consensus gate, no score-must-advance-with-overs
gate, and no post-rollover lockout was found that would explain
the 18.1 reads being silently dropped *inside* ScoreManager.

### A2. Upstream poison gates (the actual gate)

Located in `test_pipeline.py`:

| Site (line) | Effect | Fires on |
|-------------|--------|----------|
| `apply_overlay_strip_batter_pop_guard` (3360-3423) | `popped=batters` and emits `[STRIP-OVERLAY-DETECTED]` | strip batters not in `batting_card` active set |
| `apply_comparison_strip_batter_row_delta_guard` (3426-3478) | `popped=batters`, emits `[STRIP-ROWS-MISALIGNED]` | confirmed batter row diverges >20 runs |
| `_poison_scoreboard_after_graphic_transition` (3481-3490) | sets `_frame_poisoned=True` | prev frame was GRAPHIC, current is SCOREBOARD |
| Score-mismatch poison (~7720-7735) | `_frame_poisoned = True`; clears score-shaped fields | extractor score diverges from tracker beyond threshold |
| Score-streak / poison-streak (5959-5966 + 5461-5466) | rolling poison-rate watchdog | ≥56% poison in window |

When `_frame_poisoned` is set, score-shaped fields (`score`,
`wickets`, `match_overs`) are stripped before the scorer runs, and
the scorer's diff records `FRAME_POISONED:<raw_score>`.

### A3. Frame-by-frame trace, F231-F244

`scout` and `scorer_changes` columns from `DETAIL|F…|SCOREBOARD`:

| F   | cam        | strip score | strip overs | Guards fired                         | scorer_changes        | AFTER (state) |
|-----|------------|-------------|-------------|--------------------------------------|-----------------------|----------------|
| 231 | closeup    | 144-8       | 18.1        | STRIP-OVERLAY-DETECTED active_batting| FRAME_POISONED:144    | 141-8 (18.0)   |
| 236 | bowlers_end| 8.1*        | —           | (different scoreboard)               | —                     | 141-8 (18.0)   |
| 237 | bowlers_end| 8.2*        | —           | (different scoreboard)               | —                     | 141-8 (18.0)   |
| 239 | bowlers_end| 144-8       | 18.1        | STRIP-ROWS-MISALIGNED row_delta=32   | FRAME_POISONED:144    | 141-8 (18.0)   |
| 240 | bowlers_end| 144-8       | 18.1        | STRIP-ROWS-MISALIGNED row_delta=35   | FRAME_POISONED:144    | 141-8 (18.0)   |
| 241 | closeup    | 145-8       | 18.2        | STRIP-OVERLAY-DETECTED active_batting| FRAME_POISONED:145    | 141-8 (18.0)   |
| 242 | bowlers_end| 145-8       | 18.2        | STRIP-OVERLAY-DETECTED active_batting| FRAME_POISONED:145    | 141-8 (18.0)   |
| 243 | closeup    | 145-8       | 18.2        | STRIP-OVERLAY-DETECTED active_batting| FRAME_POISONED:145    | 141-8 (18.0)   |
| 244 | **graphic**| 145         | 18.2        | (fast-path bypasses poison guards)   | post-event immediate  | 145-8 (18.2)   |

(*F236/F237 strip reads `(8.1)` / `(8.2)` are a different scoreboard
mode and unrelated.)

### A4. Why each guard fired

All seven poisoned frames logged the same `strip_batters=
['Vijaykumar Vyshak', 'Marco Jansen']`. Marco Jansen was **dismissed
at F212** (the rollover event); the scoreboard `batting_card` active
set was `['Marcus Stoinis']` (Vyshak had not yet been
added/promoted-to-batting on the card, since no ball-event for him
had fired since the rollover).

- `_detect_overlay_via_active_batting` (line 3384) compares the strip's
  `(Vyshak, Jansen)` pair against the card's `(Stoinis,)` active set.
  Neither name matches → fires `reason=active_batting`, pops batters.
- `_OVERLAY_LOCKOUT_BREAKOUT_K` would force-accept after K consecutive
  identical mismatches, but the broadcast strip's name pair was stable
  across F231-F243 yet the breakout didn't trip in the trace — either
  `K` is set higher than the run length (≈7 SCOREBOARD frames) or the
  poison was attributed to row-delta on the interleaved F239/F240
  reads, resetting `consecutive`.
- F239/F240's `STRIP-ROWS-MISALIGNED row_delta=32/35` fires because
  the strip's "Stoinis 4(3)" / "Stoinis 1(3)" rows compare against
  card "Stoinis 36(34)" — the strip is *correctly* reading a
  different (incoming) batter's row but the row-pair label is mapped
  onto Stoinis by `resolve_name`, producing a phantom 32-run delta.

### A5. Why F244 succeeded

Vision tagged F244 as `cam=graphic phase=graphic`. The graphic
fast-path read (`[CAM-GRAPHIC-FAST-PATH-READ] score=145 overs=18.2
changes=['score', 'overs']`) runs *before* the strip-overlay /
row-delta poison guards and feeds ScoreManager directly. The TRACK
log shows `score: 141 → 145 (post-event immediate, grace=1)` followed
by `overs: 18.0 → 18.2 (post-event immediate, grace=0)`. Both jumps
landed on the same frame, with FLOOR padding 2 `?` placeholders into
`this_over` (F244 line: `team_overs=18.2 expects 2 legal, observed
only 0`).

## Phase B — Candidate root causes

| # | Hypothesis | Evidence | Verdict |
|---|------------|----------|---------|
| a | ScoreManager multi-frame consensus on `team_overs` | No such gate found in code; `team_overs` is reconcile-fed (line 1900), not consensus-tracked | **Not the bug** |
| b | ScoreManager score-gates overs (overs cannot advance unless score advances) | scorer never received a non-poisoned score *or* overs in F231-F243 (`BEFORE`==`AFTER` on all rows) | **Not in path** |
| c | Post-rollover hysteresis lockout | F212 rollover used `grace=1`; F244 commit uses `grace=0`. No post-rollover overs-only lockout located | **Not the bug** |
| d | `[OVERS FIX] SKIP regression` rejected legitimate 18.1 | Disproved by `overs_fix_skip_regression_false_positive.md` (guard bypassed at line 1344) | **Not the bug** |
| e | Upstream FRAME_POISON guard stripped score+overs before ScoreManager saw them | `Changes:['FRAME_POISONED:N']` on every poisoned frame; `BEFORE`==`AFTER`; F244's graphic fast-path bypassed it and committed both changes simultaneously | **Confirmed root cause** |
| f | `batting_card` active-set stale (Vyshak never promoted to batting) drives the active_batting guard | strip_batters constant at `[Vyshak, Jansen]`; active_pair constant at `[Stoinis]` for 12+ frames | **Confirmed precondition for (e)** |

## Root cause

The stall is **upstream of ScoreManager**, in
`apply_overlay_strip_batter_pop_guard` and the score-mismatch poison
gate in `test_pipeline.py`. Both fire because `scoreboard.batting_card`
was not updated to mark **Vyshak as batting** after Jansen's dismissal
at F212 — the active-batting set stayed `[Stoinis]` for ~2 minutes,
during which every clean strip read of `[Vyshak, Jansen]` (a correct
broadcast view: incoming + lagging-display) tripped the
`reason=active_batting` guard, popped batters, and (via downstream
score-mismatch / row-delta paths) poisoned the score+overs fields.
ScoreManager's overs path is correct; it simply received nothing to
commit until F244's graphic frame routed through the fast-path
bypass.

## Recommended fix

**One change.** Promote the incoming batter to `status=batting` in
`scoreboard.batting_card` immediately on a wicket-event rollover
(F212-class), using the strip's incoming-batter row as the source.
Once `[Vyshak]` is in the active set, the
`_detect_overlay_via_active_batting` guard at line 3384 will accept
`strip_batters=[Vyshak, Jansen]` (one of two names matches active),
the score-overlay poison cascade stops, and the F231 18.1 read flows
through normally.

Two secondary mitigations (do **not** bundle):

1. Verify `_OVERLAY_LOCKOUT_BREAKOUT_K` against expected stale-pair
   run lengths. The breakout exists for exactly this scenario but did
   not trip in F231-F243 — likely because intervening row-delta
   pops at F239/F240 reset `consecutive`. Consider counting "any
   poison on (strip_pair, active_pair) signature" rather than only
   active_batting hits.
2. Distinguish "strip shows N+1 batters where one is in active set"
   from "strip shows entirely different pair". Today both produce
   `popped=batters`; the former is the normal post-wicket transition
   and should be a card-promotion signal, not a poison signal.

**Out of scope here**: do not modify `_validate_overs` (verified
correct in linked memo), do not change ScoreManager's overs-commit
path (no gate is fault here), do not redesign the guard architecture.

## Linked issues

- `overs_fix_skip_regression_false_positive.md` — disproves the
  hypothesis that `_validate_overs` rejected the 18.1 reads.
- `wide_breaks_this_over_slot_count.md` (P4) — disproves the
  this_over slot-count hypothesis.
- U4: 18.1 skipped on UI — root cause is the upstream poison
  cascade documented here, not the ribbon code paths.
