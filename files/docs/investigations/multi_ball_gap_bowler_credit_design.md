# Multi-ball gap bowler credit lost (B-α design memo, 2026-05-20)

**Status.** Design memo. No code commits. Output is the failure-mechanism
classification + proposed fix shape for the B-α bug class surfaced by
`validate_gtrr_20260520_180715`'s `DISPATCH-LOOP-SHADOW-COMPARISON` divergence
events.

**Bonus finding (§5).** The audit also surfaces a shadow-comparison
implementation bug in my own `_capture_multi_ball_shadow_state` scaffold —
reading the wrong scoreboard attribute, producing false positives at 2 of 3
divergent events. Same lesson as the B-ζ falsification: hypotheses about the
production pipeline AND hypotheses about my own observability tooling are both
subject to gate-6 empirical verification.

## 1. Audit scope

Five `DISPATCH-LOOP-SHADOW-COMPARISON` events fired across the session. Two
exceeded `MULTI_BALL_MAX_BALLS` (d_balls=10, 11) and the actual path correctly
rejected them; expected divergence. Three within-cap events (d_balls=2 each)
are the audit subject:

- Frame **302**: `d_balls=2, d_score=0, d_wickets=0`, bowler=`Brijesh Sharma`,
  striker=`Shubman Gill`
- Frame **522**: `d_balls=2, d_score=5, d_wickets=0`, bowler=`None`,
  striker=`Shubman Gill`
- Frame **1325**: `d_balls=2, d_score=5, d_wickets=0`,
  bowler=`Donovan Ferreira`, striker=`Washington Sundar`

## 2. Frame-by-frame walks

### 2.1 Frame 302 — bowler=Brijesh Sharma, runs=0 across 2 balls

Trace events at frame 302:

```
[MULTI_BALL_DECOMPOSED] balls_skipped=2 runs=0 wickets_in_gap=0 overs_skipped=0.2
[PENDING-BALL-ENQUEUED] queue_depth=2
[BOWL-DELTA] Brijesh Sharma +runs=0 +balls=1 → runs=6 overs=0.1 wkts=0
[ABSORBED-LEGAL-BOWLER-CREDITED] bowler=Brijesh Sharma ball_index=0 token='.' wicket_credited=False
[BAT-DELTA] Shubman Gill +runs=0 +balls=1 → runs=11 balls=10
[BOWL-DELTA] Brijesh Sharma +runs=0 +balls=1 → runs=6 overs=0.2 wkts=0
[ABSORBED-LEGAL-BOWLER-CREDITED] bowler=Brijesh Sharma ball_index=1 token='.' wicket_credited=False
[BAT-DELTA] Shubman Gill +runs=0 +balls=1 → runs=11 balls=11
[DISPATCH-LOOP-SHADOW-COMPARISON] divergence_fields=['bowler_balls_delta']
  predicted.bowler_balls_delta=2
  actual.bowler={}  ← EMPTY
```

**Two `BOWL-DELTA` events fired, each crediting Brijesh +1 ball. The actual path
correctly credited the bowler for both balls.** But the shadow comparison's
`actual.bowler` dict is empty — falsely flagging divergence.

### 2.2 Frame 1325 — bowler=Donovan Ferreira, +5 runs across 2 balls

```
[MULTI_BALL_DECOMPOSED] balls_skipped=2 runs=5 wickets_in_gap=0 overs_skipped=0.2
[PENDING-BALL-ENQUEUED] queue_depth=1
[BOWL-DELTA] Donovan Ferreira +runs=0 +balls=1 → runs=5 overs=0.4 wkts=0
[ABSORBED-LEGAL-BOWLER-CREDITED] ball_index=0 token='.'
[BAT-DELTA] Washington Sundar +runs=0 +balls=1
[BOWL-DELTA] Donovan Ferreira +runs=5 +balls=1 → runs=10 overs=0.5 wkts=0
[ABSORBED-LEGAL-BOWLER-CREDITED] ball_index=1 token='5'
[BAT-DELTA] Washington Sundar +runs=5 +balls=1
[DISPATCH-LOOP-SHADOW-COMPARISON] divergence_fields=['bowler_balls_delta','bowler_runs_delta']
  predicted.bowler_balls_delta=2, predicted.bowler_runs_delta=5
  actual.bowler={}  ← EMPTY AGAIN
```

**Same pattern.** Bowler credited correctly (Ferreira +1/+0 then +1/+5 across the
two absorbed balls), but the shadow's `actual.bowler` is empty.

### 2.3 Frame 522 — bowler=None at gap commit, +5 runs across 2 balls

```
[MULTI_BALL_DECOMPOSED] balls_skipped=2 runs=5 wickets_in_gap=0 overs_skipped=0.2
[PENDING-BALL-ENQUEUED] queue_depth=1
[DISPATCH-LOOP-SHADOW-COMPARISON] divergence_fields=['bowler_balls_delta',
                                                     'bowler_runs_delta',
                                                     'batter_runs_total',
                                                     'batter_balls_total']
  predicted.bowler_balls_delta=2, predicted.bowler_runs_delta=5
  predicted.batter_credits=[Shubman Gill +0/+1, Shubman Gill +5/+1]
  actual.bowler={}, actual.batter={}, partnership=+5/+2
```

**No `BOWL-DELTA`, no `BAT-DELTA`, no `ABSORBED-LEGAL-BOWLER-CREDITED`.** The
absorbed events fired (`SM ABSORBED_LEGAL` logged twice), but `_apply_absorbed_event`'s
attribution block — gated on `if (bowler_name and self.scoreboard is not None
and _infer_gap_tokens is not None and nballs > 0)` at
`score_manager.py:4861-4862` — was skipped because `bowler_name` was `None`.
The gap's 5 runs reached `self.score` (already mutated by `_accept_update`)
and partnership_runs (incremented inside `_apply_absorbed_event` BEFORE the
bowler-credit gate), but the per-bowler card never received the credit. The
per-batter card also never received credit because batter attribution happens
INSIDE the gated block.

## 3. Two distinct bugs

The audit's hypotheses (h1: bowler=None silent skip; h2: per-ball iteration
fails; h3: pending queue absorbs but never drains) split apart along frames:

- **Frames 302, 1325**: The actual path credits correctly. Divergence is a
  **shadow-comparison implementation bug** (§5 below). Not a B-α defect.
- **Frame 522**: h1 holds. `bowler_name=None` at gap commit → entire attribution
  block skipped → bowler AND batter credits lost. **Real B-α defect.**

The 5-frame `ACT.bowler={}` divergence wasn't 5 instances of the same bug —
it was 1 real bug (frame 522) wearing 3 instances of disguise (frames 302,
522, 1325) because of how my snapshot reads the bowling card.

## 4. Real B-α mechanism (frame 522)

`_apply_absorbed_event` (`score_manager.py:5089+`) has this structure:

```python
def _apply_absorbed_event(self, evt, sim_prev, sim_card, frame):
    # Partnership credit — unconditional on bowler name
    self.partnership_balls += 1
    if is_last:
        self.partnership_runs += runs_in_gap

    # Bowler + batter credit — gated on bowler_name
    bowler_name = self.bowler_name
    if (bowler_name and self.scoreboard is not None
            and _infer_gap_tokens is not None and nballs > 0):
        # ... per-ball bowler.update + batter.update + striker rotation ...
        pass

    # WICKET-FALL-ONLY — only if gap_finalize_wicket
    if evt.get("gap_finalize_wicket"):
        self._apply_wicket_fall_only(w_ev, frame)
```

When `bowler_name is None`:
- **Partnership credit fires** (unconditional)
- **Bowler card credit skipped** (gated)
- **Batter card credit skipped** (also inside the gated block)
- **Striker rotation skipped** (also inside the gated block — see §6 risk)

This is structurally different from the regular ball-event path
(`_accumulate_stats_from_event` at `score_manager.py:5230+`), which queues
runs/balls credits into `_pending_bowler_ball_credits` when bowler_name is
None at `score_manager.py:5283-5290`. That queue (Queue B per memo §7.1) is
the 3-way-race resolver for normal balls.

**ABSORBED_LEGAL events have no equivalent Queue B safety net.** When
bowler_name is None at gap commit, the credit is lost permanently — no
backfill mechanism, no orphaned-trace warning, no operator-visible signal
beyond the divergence in the shadow comparison.

## 5. Shadow-comparison implementation bug

My `_capture_multi_ball_shadow_state` at `score_manager.py:4445-4479`:

```python
def _capture_multi_ball_shadow_state(self) -> dict:
    sb = self.scoreboard
    if sb is not None:
        inn = sb._inn or {}
        bowling_card = inn.get("bowling_card") or {}   # ← WRONG PATH
        batting_card = sb.batting_card or {}
    else:
        bowling_card = {}
        batting_card = {}
    return {
        ...
        "bowling_card": {...},
        ...
    }
```

`Scoreboard.bowling_card` is stored at `sb.bowling_card` (`scoreboard.py:206`,
populated at `:813` and updated at `:2940` via `update_bowler_card`). My
snapshot reads `sb._inn.get("bowling_card")` which is a separate, unused
location — returns empty dict. Every shadow comparison's `actual.bowling_card`
is `{}` regardless of what the actual path did.

**This means**: across all 5 `DISPATCH-LOOP-SHADOW-COMPARISON` events in the
session, the `bowler_balls_delta` / `bowler_runs_delta` divergence flags were
**all false positives caused by my own bug**, not by B-α. Only frame 522's
divergence is a real signal — and even that was hidden in the noise.

Fix: read `sb.bowling_card` instead of `sb._inn.get("bowling_card")`. One-line
change. The `STRIKER-POST-WICKET-DERIVATION` shadow comparison and the
existing `_pending_bowler_ball_credits` lifecycle were unaffected — only the
multi-ball-gap shadow snapshot has this defect.

## 6. Risk register

- **Striker rotation in ABSORBED_LEGAL is also gated on bowler_name.** Per
  `_apply_absorbed_event:4910-4948`, the striker-rotation logic is INSIDE
  the `if bowler_name and ...` block. When bowler_name=None at gap commit,
  the striker doesn't rotate even if the gap contained odd runs. For frame
  522 specifically: 5 runs across 2 balls = `[., 5]` per `_infer_gap_tokens`;
  the second ball is a +5 (even, no rotation) so the rotation wouldn't have
  fired anyway. But for gaps containing single-run balls, this is a hidden
  striker-attribution bug.

- **The partnership credit IS correctly applied even with bowler=None.** So
  the partnership total in the UI stays accurate; the gap appears only in
  per-bowler and per-batter cards. Suggests the divergence is more visible
  in detailed scorecards than in headline numbers.

- **Queue B + ABSORBED_LEGAL has no precedent.** The existing Queue B
  (`_pending_bowler_ball_credits`) queues for `_accumulate_stats_from_event`
  paths; extending it to ABSORBED_LEGAL means producers in `_apply_absorbed_event`
  must enqueue per-ball entries, and the drain must correctly attribute
  multi-ball gap runs distribution. The `_infer_gap_tokens` distribution
  needs to be computed at queue time (or carried in the queue entry) so the
  later drain can credit individual balls correctly.

## 7. Proposed fix shapes

### F-α-shadow (immediate, observability cleanup)

One-line change: `_capture_multi_ball_shadow_state` reads `sb.bowling_card`
instead of `sb._inn.get("bowling_card")`. Predicted flips: zero (observability
fix, no production behavior change). Effect: divergence_fields on the 5
historical shadow events will be recomputed correctly the next time the
shadow path fires — frames 302 and 1325 will show ZERO divergence, frame
522 still shows real divergence.

### F-α-queue (the real B-α fix, gated on shadow-cleanup)

Extend `_apply_absorbed_event` to queue per-ball runs/balls credits into Queue
B when `bowler_name is None` at gap commit. Spec:

```python
if not bowler_name and nballs > 0 and _infer_gap_tokens is not None:
    tokens = list(_infer_gap_tokens(nballs, runs_in_gap, wkts_in_gap))
    for idx, tok in enumerate(tokens):
        if tok in (".", "W", "?"):
            single_runs = 0
        else:
            try:
                single_runs = int(tok)
            except (TypeError, ValueError):
                single_runs = 0
        self._queue_pending_bowler_ball_credit(
            runs_delta=single_runs,
            wickets_delta=(1 if (idx == nballs - 1
                                  and evt.get("gap_finalize_wicket"))
                          else 0),
            event_overs=...,
            frame_id=self._current_frame)
```

Drain triggers (D1 inline + D2 on_lock) already exist; the queue is the same
Queue B with the same 3-way-race semantics. Once the bowler resolves, the
queued credits backfill.

Predicted flips: `trace_alpha_bowler_runs_sum` baseline gap was 25 runs;
F-α-queue closes the part attributable to frame 522 (5 runs lost) — though
the headline gap might not move much because frame 522's gap was already
accounted in partnership but lost in per-bowler. The 20-run residual is
plausibly from other classes (B-β wicket dispatch losing balls, byes/leg-byes
unclassified, etc.).

**Predicted flip estimate: gap shrinks from 25 to ~20 runs with F-α-queue
alone.** Full closure requires B-β fix + bye-classification fix.

### F-α-rotation (deferred — striker rotation when bowler=None)

A parallel issue: striker rotation is also gated on bowler_name inside
`_apply_absorbed_event`. When the gap contains single-run balls and bowler=None,
the striker doesn't rotate. This is a different attribution bug than the
bowler-credit loss; same architectural cause (over-broad gate). Separate fix
scope; document but don't ship in F-α-queue.

## 8. Equivalence proof outline

For F-α-queue: the queue B drain produces the same per-bowler delta the
inline `_apply_multi_ball_gap` would predict, AS LONG AS:

- `_infer_gap_tokens` returns the same distribution at queue time and at
  drain time. (Deterministic for the same `(nballs, runs, wickets)` inputs.)
- The bowler that locks after the gap is the one who actually bowled the
  gap balls. (Production assumption: bowlers don't switch mid-over outside
  injury / mankad scenarios.)

The first assumption holds by construction. The second is the standard cricket
invariant — same one Queue B already relies on for normal balls.

**Empirical validation path**: after F-α-shadow + F-α-queue land, re-run the
captured Scout dump for validate_gtrr through F1-patched code. Verify:

- `DISPATCH-LOOP-SHADOW-COMPARISON` at frames 302, 1325: zero divergence.
- `DISPATCH-LOOP-SHADOW-COMPARISON` at frame 522: zero divergence (Queue B
  drain produces matching delta).
- `trace_alpha_bowler_runs_sum` gap shrinks toward 20 runs.

## 9. Sequence recommendation

| Stage | Action | Gate | Predicted flips |
|---|---|---|---|
| F-α-shadow | Read `sb.bowling_card` in `_capture_multi_ball_shadow_state` | L1.5 + L2 hold (observability-only change) | Zero production. False-positive divergences disappear from future shadow data. |
| F-α-queue | Queue ABSORBED_LEGAL credits into Queue B when bowler=None | L1.5 + L2 hold; shadow comparison shows zero divergence for the within-cap gaps in captured dump | `trace_alpha_bowler_runs_sum` gap shrinks ~5 runs (frame 522 case alone). Rest of 25-run gap remains for B-β / bye-classification fixes. |
| F-α-rotation (deferred) | Lift striker-rotation outside the bowler-name gate | Separate audit memo | n/a |

## 10. Out of scope

- **B-β SM wicket dispatch.** Separate memo; B-β's frames 979 and 1190 are
  WICKET events that bypassed SM entirely, different mechanism from
  ABSORBED_LEGAL bowler-credit loss.
- **Bye / leg-bye classification.** Scout-side failure; separate workstream.
- **Compound token encoding (`Wd+N`).** Separate Scout/extractor cleanup.
- **The `partnership_balls/runs` always-credit behavior.** Currently
  partnership is correct even when bowler=None. F-α-queue preserves this;
  no change.

---

## Addendum A — B-ζ falsification + recursive gate-6 application (2026-05-20)

The B-ζ hypothesis ("striker mid-over flip without wicket between frames 12
and 49 in post-F1 replay") was **falsified one turn after** the §7.2 gate 6
tightening was baked into §11.8 of `cold_start_initial_striker_design.md`.

**Falsification.** The frame-49 striker flip Sai → Gill was a legitimate
cricket rotation: +1 run on a legal ball (single) → batters cross → striker
rotates. Per `_apply_event`'s rotation logic, `runs % 2 == 1` triggers
exchange of `self.striker` and `self.non`. The trace at frame 49 shows
`[BAT-DELTA] Sai Sudharsan +runs=1 +balls=1` followed by the deterministic
rotation. Correct cricket behavior, not a bug.

**The lesson the original tightening missed.** §11.8 framed gate 6 as
applying to **fix predictions** ("predicted flips must cite concrete frame
numbers, not qualitative code-path reasoning"). The B-ζ false alarm reveals
that gate 6 applies recursively to **bug-class hypotheses** too. Declaring
"B-ζ surfaced" based on a qualitative state-transition observation (state at
frame 12 vs state at frame 49) without checking the intermediate frames for
a legitimate trigger event is the same discipline violation, applied one
level up.

**Permanent reinforcement.** Gate 6 now applies to every classification in
the §7 framework:

- Bug-class hypotheses (e.g., "B-ζ exists")
- NOT-A-DEFECT verdicts (e.g., S5a, Queue B, `_ScoutRetryBuffer`)
- Fix-feasibility claims (e.g., "this deletion is audit-clean")
- "Already addressed" verdicts (e.g., S5b-3 Context A, falsified by the
  validate_gtrr session one turn after declaration)

The discipline doesn't have a privileged direction. Every classification is
a hypothesis pending empirical verification against captured trace data.
The five-observability-streams convergence + the trace-session assertion
library are the operational mechanism that catches drift in any direction.

**Compound finding.** This memo (B-α audit) repeats the pattern: my hypothesis
"3 of 5 within-cap shadow events show real B-α" turned out to be 1 real B-α
+ 2 false positives from my own observability tooling. The audit's
frame-by-frame walk caught it before any code fix was proposed. Gate 6
working as designed.

---

## Addendum B — workstream queue update

Closed this session:
- F1 (B-ε): shipped `437d952`. `trace_epsilon_initial_striker` will flip on
  fresh trace. Captured-replay confirms striker=Sai at frame 12.
- B-ζ: falsified by audit. No code change. Lesson baked into gate 6
  recursive application.
- B-α: this memo. F-α-shadow + F-α-queue proposed.

Open:
- **F-α-shadow**: ready to ship (one-line snapshot fix). Predicted flips
  zero.
- **F-α-queue**: ready to ship after F-α-shadow lands (Queue B extension
  for ABSORBED_LEGAL with bowler=None). Predicted ~5-run shrink in
  `trace_alpha_bowler_runs_sum`.
- **F-α-rotation**: deferred to separate memo (striker rotation when
  bowler=None in ABSORBED_LEGAL).
- **B-β** (SM wicket dispatch missed): design memo queued. 2 events in
  validate_gtrr.
- **Compound tokens, extras_total UI**: assertion-monitored, separate fix
  scope.

Natural next move after F-α-shadow + F-α-queue: B-β audit, since B-β also
involves SM-side state writes diverging from BED-detected reality.
