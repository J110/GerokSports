# Dispatch-loop redesign scoping (2026-05-20)

**Status.** Design audit only. No code commits during scoping.

**Why.** The `_apply_event(event, prev, card, frame)` dispatch loop at
`score_manager.py:3363-3373` is the blocker preventing four §7 deletions from shipping
together: Queue A (`PendingBall` + `_pending_ball_queue`), `_over_archive_pending`,
`_pending_slots`, and MULTI_BALL gap decomposition. Each is structurally dependent on
the same producer (`_decompose_multi_ball` at `:4302-4352`) emitting N ABSORBED_LEGAL
events into a shared-state loop. The Option E bundled refactor (S1+S3) regressed
class_7 (3→7 flips, predicted 3→0) precisely because this loop has surface area beyond
the multi-ball case — `_apply_event`'s over-rollover handling clobbers token state
shared with the broadcast strip-coverage gap-fill in `eyes/this_over.py`.

This document scopes the redesign per the §7.2 six-gate checklist preemptively. Goal:
produce a candidate design with an equivalence proof BEFORE attempting any code
deletion that depends on it.

## 1. Current dispatch loop (as of 2026-05-20)

```python
base_balls = self._overs_to_balls(prev.get("overs") or 0)
for i, evt in enumerate(events):
    if evt.get("type") == ABSORBED_LEGAL:
        tb_after = base_balls + i + 1
        evt["over"] = str(self._balls_to_overs(tb_after))
        sp_o = self._balls_to_overs(base_balls + i)
        sc_o = self._balls_to_overs(base_balls + i + 1)
        self._apply_absorbed_event(
            evt, {"overs": sp_o}, {"overs": sc_o}, frame)
    else:
        self._apply_event(evt, prev, card, frame)
```

**Two execution paths exist already.** The loop is NOT uniformly broken — it already
synthesizes per-event `(sp_o, sc_o)` overs stubs for ABSORBED_LEGAL events. The shared
`(prev, card)` reuse is only for non-ABSORBED_LEGAL events. The pathology surfaces at
the seams between the two paths.

**Producer.** `_decompose_multi_ball` (`:4302-4352`) emits a list of N ABSORBED_LEGAL
events when `d_balls > 1`, queueing a `PendingBall` per event into Queue A. Each event
carries `runs=None` and `legal=True`; per-ball striker/bowler attribution is unknown
until the trackers lock.

**Consumer.** `_apply_absorbed_event` (`:4815`) is invoked once per event. Striker
rotation and bowler-ball crediting happen here; the queue-drain machinery backfills
attribution later via `_drain_pending_queue` triggered by on_lock callbacks.

## 2. Pathology — where the seams fail

Three observed failure modes from the Option E dry-run plus surrounding investigation:

**P1. Token-state coupling between `_apply_event` and `eyes/this_over.py`.** When an
ABSORBED_LEGAL event commits, the ThisOverManager appends `?` placeholders via the
`_pending_slots` mechanism. The next non-ABSORBED_LEGAL event in the same `events` list
hits `_apply_event` with the shared `(prev, card)`; if that event triggers
`is_over_change` logic (`_track_overs_advance` and inline rollover at `:5330`), it can
archive `this_over` *with the `?` placeholders still in place* — locking in
unattributed tokens before the queue drain has a chance to backfill. The
`_over_archive_pending` deferral exists specifically to dodge this race.

**P2. `fill_strip_coverage_gap` (broadcast G remnant) independently pads `?`.** The
ThisOverManager has a separate code path that pads missing slots with `?` when the
broadcast strip's per-ball read shows fewer tokens than `len(self.this_over)` would
imply. This path operates without consulting the SM pending queue, so it can produce
`?` placeholders that have NO corresponding `PendingBall` to drain — orphan `?`
tokens. The class_7 regression in Option E was traced to this site.

**P3. Bowler/striker attribution lag.** The on_lock callbacks
(`test_pipeline.py:7211-7232`) fire on a False→True streak transition. Until then, every
absorbed event commits with `bowler=None` / `striker=None` to the queue. The queue
drains FIFO; if attribution resolves between absorbed events 3 and 4 of a 4-ball gap,
events 1-3 stay un-drained until the next round of drain triggers fires. This is the
same 3-way race that bit Queue B, with the additional complication that *multiple*
events per frame can land in the queue.

## 3. Two candidate designs

### Design A — per-event `(prev, card)` advancement

Rebuild the loop so every event sees a `(prev, card)` snapshot that reflects all
prior events in the same frame. For each event in `events`:

1. Compute `(prev_i, card_i)` = state-after-event-(i-1), state-after-event-i.
2. Call `_apply_event(event_i, prev_i, card_i, frame)` uniformly — no special
   ABSORBED_LEGAL branch.
3. Inside `_apply_event`, the over-rollover / token-archive logic sees the correct
   per-event boundary, so P1 disappears.

**Equivalence proof requirements.**
- Enumerate every field `_apply_event` reads from `(prev, card)`. Build the
  per-event delta correctly for each.
- Confirm `_apply_absorbed_event`'s body folds into `_apply_event` without behavior
  change (or stays as a separate dispatch case but always with per-event
  `(prev_i, card_i)`).
- Verify the streak / consensus trackers (`ConfidenceTracker`, score-jump consensus)
  do not double-count when their inputs advance N times per frame instead of once.

**§7.2 six-gate preemptive audit.**

| Gate | Status / risk |
|---|---|
| 1. Enumerate callers | `_apply_event` is the dispatch sink; `_apply_absorbed_event` is its sibling. Both are called once each per event-list element. |
| 2. Classify callers | All callers in `_handle_warm` (`score_manager.py:3363`) are uniform; one dispatch site. |
| 3. Cross-reference adjacent state | High risk. `_apply_event` reads `prev` for: `prev.get("score")`, `prev.get("wickets")`, `prev.get("overs")`, `prev.get("bat1_*")` / `bat2_*` snapshots. Computing each per-event delta is nontrivial — runs/wickets typically attach to one event in the list, but extras + dismissal can split. |
| 4. Equivalence proof | Requires a synthetic test bench that runs the same N-event frame through the old loop and the new loop, asserts bit-identical final state across the 9-fixture corpus + class assertion library. |
| 5. State variable lifecycle | `_event_baseline_score` at `:3381` is set from `c_score` after the entire loop. With per-event advancement, the baseline becomes per-event — confirm downstream consumers don't break. |
| 6. Predicted flip gate | Predict class_7 returns to 3 (baseline) and class_1 holds at 0 before any dry-run. If the prediction is off, pause. |

**Pros.**
- Uniform dispatch — removes the ABSORBED_LEGAL special case.
- Unblocks Queue A deletion (events have their own attribution context per call).
- Removes the `_over_archive_pending` race by giving over-rollover the correct
  per-event boundary.

**Cons.**
- Highest blast radius. Touches the central dispatch path used by every committed
  ball event, not just multi-ball.
- Equivalence proof requires bit-identical replay across the corpus; any drift in
  the streak trackers or consensus gates surfaces here.

### Design B — bypass `_apply_event` for multi-ball decomposition

Leave `_apply_event` and the existing single-ball dispatch untouched. Instead, route
the multi-ball gap through a separate code path that *does not emit ABSORBED_LEGAL
events into the dispatch loop at all*. The decomposition becomes inline:

1. `_handle_warm` detects `d_balls > 1`.
2. Instead of calling `_decompose_multi_ball` to build N events, call a new
   `_apply_multi_ball_gap` method that directly mutates `self.score`,
   `self.wickets`, `self.overs`, bowler-card stats, and the over_history archive
   in one atomic step.
3. `eyes/this_over.py`'s ABSORBED_LEGAL handler never fires; `?` placeholders are
   appended (or not appended) by `_apply_multi_ball_gap` directly.

**Equivalence proof requirements.**
- Demonstrate that the inline path produces the same final scoreboard state as the
  N-event loop would, across the corpus.
- Audit every site that listens for ABSORBED_LEGAL events (over_mgr handler at
  `eyes/this_over.py:665`, any downstream consumers) and confirm none is load-bearing.

**§7.2 six-gate preemptive audit.**

| Gate | Status / risk |
|---|---|
| 1. Enumerate callers | `_decompose_multi_ball` has one caller (`_infer_event` at `:4366`). The downstream ABSORBED_LEGAL event-listener set: `eyes/this_over.py:665` + Queue A binding callback. Both are part of the same multi-ball machinery. |
| 2. Classify callers | All multi-ball-only. No third-party consumer of ABSORBED_LEGAL exists outside the gap-decomposition flow (confirmed by grep — see §4). |
| 3. Cross-reference adjacent state | Low-to-moderate risk. The multi-ball flow already operates on its own atomic gap_meta; folding it inline preserves that atomicity. Striker-rotation handling needs explicit treatment (currently happens in `_apply_absorbed_event` per ball). |
| 4. Equivalence proof | Smaller surface than Design A — just the multi-ball case. Replay across the 9-fixture corpus, asserting bowler ball-counts + over_history tokens match baseline. |
| 5. State variable lifecycle | `_pending_ball_queue`, `_pending_slots`, `_over_archive_pending` all become reachable-only-via-MULTI_BALL — and MULTI_BALL no longer emits ABSORBED_LEGAL. They go quiet, then can be deleted in a follow-up. |
| 6. Predicted flip gate | Predict class_1 (multi-ball events count) drops to whatever the actual gap-frame count is across the corpus; class_7 holds at baseline. Quantify before dry-run. |

**Pros.**
- Smaller blast radius — only touches the multi-ball code path.
- Folds Queue A, `_over_archive_pending`, `_pending_slots`, MULTI_BALL decomposition
  into one coordinated deletion (their producer goes away).
- Aligns with the architectural direction "don't plan for multi-ball events" — the
  inline path is the cricket-realistic step (gap = atomic deficit application, not
  N synthetic events).

**Cons.**
- The inline `_apply_multi_ball_gap` becomes a parallel implementation of much of
  what `_apply_event` does (score/wicket/overs commit, bowler-card stats). Risk of
  drift between the two if `_apply_event` evolves.
- Striker rotation across N balls within the gap still needs handling — the per-ball
  rotation rules can't be hand-waved.

## 4. ABSORBED_LEGAL listener inventory

Confirming no third-party consumer:

| Site | Role | If we stop emitting ABSORBED_LEGAL |
|---|---|---|
| `score_manager.py:5263-5267` | `_apply_event` rejects ABSORBED_LEGAL with a warn (defense-in-depth) | unreachable warn; safe to delete |
| `score_manager.py:4815` | `_apply_absorbed_event` (dispatched from `:3370`) | dispatch never fires; remove method |
| `eyes/this_over.py:665-683` | ABSORBED_LEGAL handler appends `?` + binds slot | dispatch never fires; remove block |
| Producer | `_decompose_multi_ball` at `:4302` | replaced by `_apply_multi_ball_gap` in Design B |
| Queue A binding | `bind_pending_slot` at `:893` | unreachable; Queue A goes quiet |

The listener set is fully contained within the multi-ball machinery. No third-party
consumer exists. Design B's bypass is feasible.

## 5. Recommendation

**Design B (bypass).** Decisive factor: smaller equivalence-proof scope, and the
multi-ball decomposition path is the actual scar tissue per the §7 audit — folding it
inline removes the dispatch-loop complication AND the queue machinery in a coordinated
deletion, exactly the pattern the §7.4 sweep showed is needed (related items collapse
together when their shared producer is removed).

**Sequence.**

1. Write `_apply_multi_ball_gap` as a new method alongside `_decompose_multi_ball`
   (additive, no behavior change yet).
2. Add a feature flag `SM_INLINE_MULTI_BALL` (off by default). Gate `_infer_event`'s
   `d_balls > 1` branch on the flag — flag-on routes through `_apply_multi_ball_gap`,
   flag-off keeps `_decompose_multi_ball`.
3. Run shadow comparison across the 9-fixture L2 corpus: flag-off vs flag-on must
   produce identical scoreboard final state and over_history archives. Predicted
   flips: 0 (it's an architectural refactor, not a behavior change).
4. If shadow matches: flip the flag default to on, observe in production for one
   session, then delete `_decompose_multi_ball` + all downstream ABSORBED_LEGAL
   machinery (Queue A, `_pending_slots`, `_over_archive_pending`, ABSORBED_LEGAL
   dispatch case, `_apply_absorbed_event`).
5. Per the §7.2 checklist, predict the assertion-library flip count before each
   step. Pause if any step diverges from prediction.

**Stop signals during scoping.**

- If ABSORBED_LEGAL listener inventory (§4) turns up a third-party consumer not
  listed above, Design B's blast radius grows — re-audit before committing to it.
- If striker-rotation rules across an N-ball gap are not derivable from the existing
  per-ball rotation primitives (i.e., the gap requires modeling that the inline
  path can't reproduce), pause and reconsider Design A.
- If the shadow comparison in step 3 produces any divergence, the architectural
  premise ("multi-ball gap = atomic deficit") is wrong; pause and investigate.

## 6. What this scoping deliberately does NOT do

- No code commits. Per the §7.2 checklist, equivalence proofs come before the
  refactor itself, and that proof requires shadow data from a real corpus run.
- No prediction of Layer 1.5 / Layer 2 flip counts beyond the qualitative "zero
  drift expected for an architectural refactor." Those numbers come from the
  shadow run in step 3.
- No decision on whether `_pending_ball_queue` and friends are deleted in the same
  commit as the flag flip or in a follow-up. That call depends on how quietly the
  queue actually goes in production telemetry post-flag-on.

The dispatch-loop redesign is a precondition, not a §7 deletion. The actual deletions
remain gated on (a) successful shadow comparison and (b) the §7.2 checklist applied
per deletable component in step 4.
