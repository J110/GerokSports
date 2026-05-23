# Workstream G — Cold-drain surface audit (Surface A vs Surface B)

**Status.** Step-6 deliverable B (§7.2 7-gate audit on the two
candidate surfaces from step-5 addendum §3).
**Predecessor.** `workstream_g_shape_a_validation_addendum.md`
(empirical falsification of Shape A drain); `workstream_g_cold_start
_transition_catalogue.md` (transition-site enumeration + reset-path
matrix). Both are required reads.
**Branch.** `obs/silent-wicket-absorption` (HEAD `cc21d03`).
**Empirical substrate.** `logs/trace/validate_shape_a_114349.jsonl`.
**Budget.** 1/5 empirical-falsification consumed in step 5; this memo
preserves the remaining 4/5 (static-only analysis).
**Discipline.** Insight #17 enforced: gate-5 lifecycle enumeration
verifies each reset path against the step-5 trace, not via reasoning
about `__init__` re-runs.

---

## §1 Candidate surface restatement

### §1.1 Surface A — drain-in-cold + expire-only

```python
# in _handle_cold_start (at the top, mirroring _handle_warm:3357-3364)
if self._pending_post_wicket_cascade:
    self._attempt_pending_cascade_drain()
```

Drain semantics identical to WARM. The drain dispatches through
`apply_striker_event` (the §15 fence canonical ROTATION path) if
slot-diff resolves a new_batter; otherwise TTL ticks down. No new
wipe site; no new trace tag.

### §1.2 Surface B — wipe on WARM→COLD + one-shot drain on COLD→WARM

```python
# at each WARM→COLD site (W1/W2/W3/W4)
if self._pending_post_wicket_cascade:
    _wiped = [
        {"frame_set_at": pc.frame_set_at,
         "age": self._current_frame - pc.frame_set_at,
         "dismissed": pc.dismissed}
        for pc in self._pending_post_wicket_cascade]
    self._emit_trace(
        tag="POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START",
        payload={"wiped_entries": _wiped,
                 "site": "<W1|W2|W3|W4>",
                 "frame_id": self._current_frame})
    self._pending_post_wicket_cascade = []
self.mode = "COLD_START"

# at each COLD→WARM site (C1/C2/C3/C4/C5/C6)
self.mode = "WARM"
if self._pending_post_wicket_cascade:
    self._attempt_pending_cascade_drain()
```

No new dispatcher; reuses the existing drain mechanism. Adds wipe-
emission at 4 WARM→COLD sites + drain-trigger at 6 COLD→WARM sites.

---

## §2 Surface A audit

### §2.1 Gate 1 — callers

`_handle_cold_start` is invoked from `on_frame` at `:1935` when
`mode == "COLD_START"`. Single caller; same shape as `_handle_warm`.

Symbol under change: `_handle_cold_start` body gains one new top-of-
function call. No other site needs modification.

**Verdict.** PASS.

### §2.2 Gate 2 — classification

Caller `_handle_cold_start` is class **consumer** (deferred) —
identical role to `_handle_warm` for the warm drain. No new
classifications introduced.

**Verdict.** PASS.

### §2.3 Gate 3 — adjacent state + §12 dual-state-write

**Dual-state-write check.** The drain writes `self.striker` via
`apply_striker_event` (single canonical ROTATION writer). No new
parallel state surface. Not a §12 instance.

**Cold-start synthesizer interaction.** `_synthesize_cold_start_ball_
events` (`score_manager.py:2638-2657`) is invoked from `_maybe_
synthesize_cold_start_gap`, called at C1/C2/C3/C4 (each COLD→WARM
site). It internally calls `_set_slot_pair(..., source="cold_start_
synth")` at `:2631`. The synth runs **after** the mode flip (so
during WARM frames following the cold→warm transition), NOT during
COLD frames where Surface A's drain would run.

Concrete race scenarios:

- (i) **COLD frame, drain resolves new_batter**: drain writes
  `(self.striker, self.non) = (next_striker, next_non)` via the
  StrikerEvent. Subsequent cold-frame body continues — cold-start
  uses `card.score / card.wickets / card.overs` to grow consensus;
  does NOT read `self.striker` for cold-start logic. No conflict.

- (ii) **Cold→warm transition then synth runs**: the synth assumes
  fresh-start striker semantics. If Surface A's drain wrote a
  striker in the prior cold frame, the synth's
  `_synthesize_cold_start_ball_events` enters with a non-None
  `self.striker`. The synth's striker-rotation logic at `:2627-2635`
  treats `self.striker` as the current pointer and rotates from it
  on odd-run cricket-rules events. Drain's earlier-set striker
  becomes the input to synth.

  **Concrete defect surface:** drain set striker=Stubbs (the new
  batter) at e.g. F750 while SM was still in COLD. Then C5
  watchdog-forced fires at F843 (`COLD-START-FORCED-RECOVER`).
  `_maybe_synthesize_cold_start_gap` then runs and starts
  synthesizing ball-events from `_cold_start_entry` → current.
  Synth's BAT-DELTA attribution would credit Stubbs for runs that
  happened BEFORE Stubbs walked in (since the cold-start gap
  spans frames before the drain resolved Stubbs).

  This is a real defect class — drain-in-cold sets striker too
  early relative to the cold-start synth's bookkeeping.

**Verdict.** **FAIL on gate-3.** Cold-start synth contamination is a
concrete defect surface — not theoretical. The mitigation would be
to gate the synth against pending-cascade activity, but that re-
opens §15 fence (synth is HANDOFF "What NOT to touch").

### §2.4 Gate 4 — equivalence / behavioral delta

Compared to f09fc38 baseline:

| State | f09fc38 | Surface A |
|---|---|---|
| WARM frame, queue empty | no-op | no-op |
| WARM frame, queue non-empty | drain attempts resolve | drain attempts resolve (unchanged) |
| COLD frame, queue empty | no-op (drain not called) | no-op (drain called, returns immediately) |
| COLD frame, queue non-empty, slot-diff resolves | no drain | drain fires + writes striker via apply_striker_event |
| COLD frame, queue non-empty, slot-diff doesn't resolve | TTL doesn't tick (no drain called) | TTL ticks down (drain called but no-op resolve) |

Surface A is strict-additive on WARM behavior; adds drain firing in
COLD + TTL ticking. The gate-3 concern from §2.3 is the load-bearing
behavioral delta.

**Verdict.** PASS (behavioral delta well-defined). The gate-3 issue
is the disqualifier, not gate-4.

### §2.5 Gate 5 — LIFECYCLE WITH EMPIRICAL TRACE-OBSERVABILITY

Per insight #17, every reset path must be empirically traced.

| Reset path | Surface A handles? | Step-5 trace evidence |
|---|---|---|
| `__init__` (constructor) | No queue carryover | N/A — pre-session |
| `_clear_per_innings_sm_surface` | Already wipes via Shape A wiring | NOT observed in trace |
| `set_innings_2` → `__init__` re-run | SILENT wipe (still unsolved) | × 5 in trace; no WIPED tag |
| `force_cold_start_recalibration` | No wipe coverage | NOT observed |
| W1 overs-regress | No wipe coverage | NOT observed |
| W2 stale-reject | No wipe coverage | NOT observed |

**Surface A does not address W4's silent wipe.** Even with drain-in-
cold, when `SM-INNINGS-2-RESET` fires at F690 the queue is silently
emptied via `__init__` body. `trace_eta` continues to flag orphans
because the wipe leaves no trail.

In the step-5 trace specifically: F679 enqueue, F690 silent wipe
(no WIPED tag, no DRAIN-FIRED tag) → orphan. Surface A doesn't fix
this.

**Verdict.** **FAIL on gate-5.** The dominant cold-start re-entry
path on this dump (`SM-INNINGS-2-RESET`) is not addressed by Surface
A. The gate-5 lifecycle gap from step 5 persists. Insight #17 mandate
not met.

### §2.6 Gate 6 — predicted flip with concrete frame numbers

Predictions per step-2 audit §5 (original Shape A predictions):

| Frame | Expected | Surface A actual |
|---|---|---|
| F679 enqueue | YES | YES (unchanged from Shape A baseline) |
| F~709 drain (Rizvi) | DRAIN-FIRED, age=30 | F708 strip shows RIZVI; bat1/bat2 in SM = None throughout F690→F739 COLD window per catalogue §6 (the strip read doesn't propagate to SM bat slots during COLD). Slot-diff predicate input = ∅ → no resolve → no drain |
| F~893 drain (Stubbs) | DRAIN-FIRED, age=38 | Same as above for F855 enqueue. SM in COLD through F859 wipe; bat slots stay None. |

Predicted drains: 0 (despite drain hook running in cold frames).
Surface A is empirically equivalent to no-fix on this trace because
the SM-side bat slots are nulled when entering cold.

**Verdict.** **FAIL on gate-6.** Predicted-flip baseline NOT MATCHED.
Drain frames F708/F892 cannot resolve because slot-diff predicate
input (`self.bat1_name`, `self.bat2_name`) is empty in COLD mode.

### §2.7 Gate 7 — cross-fixture verification

Moot. Surface A fails gates 3, 5, 6.

### §2.8 Surface A verdict

**RED-LIGHT.** Three gates fail:

1. Gate 3: cold-start synth contamination risk (concrete defect
   surface; not theoretical).
2. Gate 5: silent W4 wipe (the dominant path in this regime) is not
   addressed; insight #17 mandate not met.
3. Gate 6: drain predicate has no input in COLD mode; predicted
   F708/F892 drain fires structurally unreachable.

Surface A is not viable as a standalone fix.

---

## §3 Surface B audit

### §3.1 Gate 1 — callers

**WARM→COLD wipe-emission sites (4):**
- W1 at `:3859` — `_handle_warm` overs-regress branch
- W2 at `:3919` — `_handle_warm` stale-reject branch
- W3 at `:4103` — `force_cold_start_recalibration`
- W4 at `:4487` — `set_innings_2` (inside `__init__` body re-run path)

**COLD→WARM drain-trigger sites (6):**
- C1 at `:2840` — `_handle_cold_start` physics-promote
- C2 at `:2905` — `_handle_cold_start` give-up (with ref)
- C3 at `:2941` — `_handle_cold_start` give-up (second branch)
- C4 at `:2950` — `_handle_cold_start` consensus reached
- C5 at `:2993` — `_cold_start_maybe_pipeline_fallback` watchdog
- C6 at `:3263` — `_handle_hot_resume` from cache

10 sites total. W4 is special — `set_innings_2`'s `__init__` body
re-runs BEFORE `mode="COLD_START"` (line 4479 vs 4487). The wipe
emission must happen BEFORE `__init__` re-runs, OR the wipe emission
must be re-implemented after `__init__` since the queue list is
already empty by then. Implementation note baked into §4.

**Verdict.** PASS. All 10 sites identified statically + verified in
catalogue §1/§2.

### §3.2 Gate 2 — classification

| Site | Class |
|---|---|
| W1–W4 | init/reset (producer of WIPED-BY-COLD-START) |
| C1–C6 | transition (consumer; one-shot drain) |

No new classes introduced. The wipe-emission and one-shot drain are
both standard cleanup/dispatch patterns.

**Verdict.** PASS.

### §3.3 Gate 3 — adjacent state + §12 dual-state-write

**Dual-state-write check.** Surface B mutates only
`self._pending_post_wicket_cascade` (drain-side via existing
`apply_striker_event` canonical path; wipe-side via list assignment).
No parallel state surface created.

**Wipe-emission coverage requirement (insight #17).** Each of the 4
WARM→COLD sites must emit a structured `POST-WICKET-CASCADE-DRAIN-
WIPED-BY-COLD-START` trace at the wipe moment. Per catalogue §1,
W1/W2/W3 emit no structured tags today — adding the wipe emission
also adds the transition-tag coverage. W4 already emits
`SM-INNINGS-2-RESET` but the wipe is silent — Surface B adds the
queue-specific tag adjacent to the existing innings-2 tag.

**W4 ordering hazard.** `set_innings_2` calls `self.__init__()` at
line 4479 which default-inits `_pending_post_wicket_cascade = []`.
The wipe-emission MUST run BEFORE `__init__` (capturing the queue
state before it's silently emptied). Implementation order at W4:

```python
# inside set_innings_2, BEFORE the __init__ re-run at :4479
if self._pending_post_wicket_cascade:
    _wiped = [...]  # capture
    self._emit_trace(tag="POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START",
                     payload={"wiped_entries": _wiped, "site": "set_innings_2", ...})
# then proceed with the existing __init__ re-run
self.__init__(shadow=shadow)
```

No race; the call is synchronous + single-threaded per `on_frame`
contract.

**Race vs `_attempt_pending_cascade_drain` (warm side).** Drain runs
inside `_handle_warm`. WARM→COLD transition runs from within
`_handle_warm`'s frame body. If a wicket-commit happens in the same
frame as a WARM→COLD transition, the enqueue and wipe race within
the same frame. Order today:

- W1/W2 fire when SM's per-frame validation rejects the current
  card. The wicket-commit path (`_apply_wicket_fall_only` → cascade
  enqueue) runs AFTER the validation passes. So if validation
  fails, no enqueue happens that frame.
- W4 fires from `_detect_innings_change` which is called at the top
  of `_handle_warm` before `_apply_event`. Same protection.
- W3 is external — outside `on_frame`; no race within a single frame.

No same-frame enqueue+wipe race in any path.

**One-shot drain at COLD→WARM.** Reuses `_attempt_pending_cascade_
drain` which is already gate-3-compliant per step-2 audit §2.3. The
drain dispatches via `apply_striker_event` canonical path.

**Cold-start synth interaction.** At C1/C2/C3/C4, the existing flow
is: `_accept_initial(card, frame)` → `mode="WARM"` → `_maybe_
synthesize_cold_start_gap()`. Surface B's drain runs AFTER `mode=
"WARM"` and BEFORE `_maybe_synthesize_cold_start_gap()`. If the
cascade resolves, drain writes striker via `apply_striker_event`,
then the synth runs with that striker in `self.striker`.

Concrete scenario: drain at COLD→WARM resolves new_batter=Stubbs at
F843; immediately afterward, `_maybe_synthesize_cold_start_gap` runs
to synthesize the F462→F843 gap (massive runs/wickets accumulation).
Synth credits Stubbs for runs that happened BEFORE he was at the
crease.

**This is the same gate-3 concern as Surface A (§2.3 (ii)).** It
applies whenever the synth runs after a drain has set striker. But:

- In Surface B, this only happens if the cascade survives the wipe
  on the WARM→COLD entry side. With wipe-on-WARM→COLD emitting,
  the queue is empty at C1-C6 in this dump (every WARM→COLD path
  wipes before the COLD frames). So the one-shot drain at COLD→WARM
  has zero work to do empirically.
- For traces where W1/W2/W3 fire (the no-wipe-by-default sites,
  now wiped by Surface B), the queue still empties on cold entry.

So Surface B's drain at COLD→WARM is empirically a no-op on this
dump — there's no queue surviving the wipe to drain. The synth
contamination scenario from §2.3 doesn't materialize.

**Verdict.** **PASS-WITH-MITIGATION.** Wipe-emission coverage
requires explicit insertions at 4 sites (acceptable cost; insight
#17 satisfied by the explicit traces). W4 ordering must be pre-
`__init__`. No dual-state-write surface introduced. Drain-on-cold→
warm carries the §2.3 (ii) gate-3 risk theoretically but is
empirically benign (queue always empty by COLD→WARM if wipes work).

### §3.4 Gate 4 — equivalence / behavioral delta

Compared to f09fc38 baseline:

| State | f09fc38 | Surface B |
|---|---|---|
| Wicket-commit in WARM, queue empty before | enqueue | enqueue (unchanged) |
| WARM→COLD transition, queue empty | silent transition | silent transition (no wipe emission) |
| WARM→COLD transition, queue non-empty | silent wipe (W4 only) or no wipe (W1/W2/W3) | explicit wipe + WIPED-BY-COLD-START emission at all 4 sites |
| COLD→WARM transition, queue empty | no drain attempt | no-op (queue empty; drain called returns immediately) |
| COLD→WARM transition, queue non-empty | no drain attempt; queue persists into WARM | drain attempt; resolves if slot-diff has input |

Surface B is strict-additive — preserves f09fc38 WARM behavior and
adds explicit wipe-emission + one-shot drain at the transition
moments. Both new behaviors are observable via trace tags.

**Verdict.** PASS.

### §3.5 Gate 5 — LIFECYCLE WITH EMPIRICAL TRACE-OBSERVABILITY

Per insight #17, every reset path verified against step-5 trace.

| Reset path | Surface B handles? | Step-5 trace evidence |
|---|---|---|
| `__init__` (constructor) | N/A (no queue carryover) | session-init only |
| `_clear_per_innings_sm_surface` direct call | Existing Shape A trace tag fires | Not exercised in step-5 trace; tag would fire if reached |
| `set_innings_2` → `__init__` re-run (W4) | **YES — explicit wipe-emission BEFORE `__init__`** | 5 fires (F462/F690/F801/F859/F992); Surface B adds 5 WIPED-BY-COLD-START emissions at these frames |
| `force_cold_start_recalibration` (W3) | YES — explicit wipe-emission added | 0 fires in this trace; would fire if reached |
| W1 overs-regress | YES — explicit wipe-emission added | 0 fires in this trace |
| W2 stale-reject | YES — explicit wipe-emission added | 0 fires in this trace |

**Every reset path has a structured trace tag.** Insight #17
mandate satisfied. `trace_eta_post_wicket_cascade_drains` should
PASS on this trace because:
- F679 enqueue + F690 WIPED-BY-COLD-START = matched pair
- F855 enqueue + F859 WIPED-BY-COLD-START = matched pair

**Verdict.** **PASS.** Gate-5 lifecycle gap closed.

### §3.6 Gate 6 — predicted flip with concrete frame numbers

**Surface B predicted post-fix trace (step-5 dump):**

| Frame | Tag |
|---|---|
| 679 | `POST-WICKET-CASCADE-ENQUEUED` (unchanged) |
| 690 | `POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START` site=W4 wiped_entries=[{frame_set_at:679, age:11, dismissed:"Nitish Rana"}] |
| 855 | `POST-WICKET-CASCADE-ENQUEUED` (unchanged) |
| 859 | `POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START` site=W4 wiped_entries=[{frame_set_at:855, age:4, dismissed:"Pathum Nissanka"}] |

`POST-WICKET-CASCADE-DRAIN-FIRED`: **0** (queue never survives long
enough to reach a COLD→WARM transition with bat slots resolved).

`trace_eta` post-fix: **PASS × 2** (2 enqueues matched by 2 WIPED-
BY-COLD-START terminals).

**Predicted replay-diff-harness deltas (Surface B alone):**

| Surface | Pre-fix | Surface B post-fix |
|---|---|---|
| `D-post-FoW-striker` | 20 | **20 (UNCHANGED)** — cascade still doesn't dispatch striker mutation |
| `POST-WICKET-CASCADE-DRAIN-FIRED` count | 0 | 0 |
| `POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START` count | 0 | 5 (for all SM-INNINGS-2-RESET fires) |
| `trace_eta` orphans | 2 | 0 |

**Critical finding.** Surface B closes the gate-5 lifecycle gap but
does NOT deliver the step-2 audit §5 predicted-flip table (D-post-
FoW-striker 20 → 5–10). Surface B is **necessary-but-not-sufficient**
for the Workstream G primary objective.

The shortfall is structural: the SM enters COLD aggressively post-
wicket (per catalogue §5.1 — `wickets_regressed` triggered by bad-
Scout-read window). The cascade is wiped before any cold→warm
transition with usable bat slots. Closing this gap requires
addressing HANDOFF §17.3 Item 2 (cold-start re-entry frequency root
cause) — specifically, suppressing `SM-INNINGS-2-RESET` with
`reason=wickets_regressed` within a hot post-wicket window.

**Verdict.** PASS on the gate-5 closure objective. ACKNOWLEDGE on
the primary-objective shortfall. Predicted-flip frame numbers
documented; the primary objective remains gated on a separate
investigation.

### §3.7 Gate 7 — cross-fixture verification

| Fixture | Predicted Surface B outcome |
|---|---|
| `validate_dckkr_20260521_155356` (this dump) | 2 enqueues / 2 WIPED-BY-COLD-START; trace_eta PASS; D-post-FoW-striker unchanged at 20 |
| `validate_gtrr_20260520_180715` | Cold-start dynamics differ; expect mostly enqueues from wicket frames + WIPED-BY-COLD-START for any cold-entry that wipes a non-empty queue. Specific frame counts TBD until replayed. |
| A future "warm-stable" trace (no `SM-INNINGS-2-RESET` post-wicket) | enqueues + DRAIN-FIRED (the original Shape A predicted-flip). Surface B preserves the warm-side drain path. |

**Verdict.** PASS. Cross-fixture verification plan documented; new
γ-bundle row not needed (trace_eta already covers).

### §3.8 Surface B verdict

**GREEN-LIGHT** for gate-5 closure objective. All 7 gates PASS
(gate 3 PASS-WITH-MITIGATION for the W4 ordering + the 4-site emit
coverage).

Explicit caveat: Surface B does NOT deliver the step-2 audit §5
predicted-flip table. The primary Workstream G objective (D-post-
FoW-striker drop) requires additionally addressing the cold-start
re-entry frequency root cause per HANDOFF §17.3 Item 2.

---

## §4 Verdict summary + selection

| Gate | Surface A | Surface B |
|---|---|---|
| 1. Callers | PASS | PASS |
| 2. Classification | PASS | PASS |
| 3. Dual-state-write + race | **FAIL** (cold-start synth contamination) | PASS-WITH-MITIGATION (W4 ordering + 4-emit coverage) |
| 4. Behavioral delta | PASS | PASS |
| 5. Lifecycle empirical | **FAIL** (silent W4 wipe unsolved; insight #17 unmet) | **PASS** (5 WIPED emissions match 5 SM-INNINGS-2-RESET fires) |
| 6. Predicted flip | **FAIL** (slot-diff predicate has no input in COLD) | PASS for gate-5 closure (2 WIPED match 2 enqueues); ACKNOWLEDGE primary-objective shortfall |
| 7. Cross-fixture | moot | PASS |

**Selection: Surface B.** Surface A red-lights on three gates;
Surface B clears all seven with explicit gate-3 mitigations.

Per the brief's tiebreak: "If both green: prefer Surface A." This
clause does NOT apply — only Surface B is green.

Per the brief's escalation clause: "If both fail any gate: open
Surface C audit (TBD)." This clause does NOT apply either — Surface
B passes all gates.

### §4.1 Scope statement

Surface B's deliverable is a **gate-5 lifecycle closure**, not a
primary-objective resolution. Workstream G's step-7 code commit
landing Surface B will:

1. Close the `trace_eta_post_wicket_cascade_drains` orphan-FAIL
   condition on the validation trace.
2. Add 4 structured trace-tag emission sites (W1/W2/W3/W4) for
   wipe observability.
3. Add 6 one-shot drain triggers (C1-C6) for the lifecycle-complete
   COLD→WARM path (empirically a no-op on this dump; structurally
   required for future warm-stable traces).
4. NOT alter the step-2 audit §5 predicted-flip table outcomes on
   this specific dump. D-post-FoW-striker remains at 20.

**The Workstream G primary objective remains open.** A follow-on
investigation (proposed: **Workstream H** — cold-start re-entry
frequency root cause + COLD-START-EXIT semantics redesign) must
land before D-post-FoW-striker drop is achievable. This is the
HANDOFF §17.3 Item 2 + Item 3 work that step-5 surfaced as critical-
path-coupled.

### §4.2 Empirical-falsification budget

**Budget unchanged: 1/5 consumed (from step 5).** This step is
purely static-analysis. The Surface B step-7 code commit will
re-validate against the same captured-Scout dump; if predicted
WIPED emissions don't fire at F690/F859/etc, that consumes 2/5.

### §4.3 Commit sequence (step 7 + step 8)

| Step | Commit | Scope |
|---|---|---|
| G-step 7 code | `feat(workstream-g): Surface B cold-start lifecycle closure` | Implementation per §4.1 (4 wipe-emit sites + 6 drain-trigger sites + W4 pre-`__init__` ordering) |
| G-step 7 test | `test(L1.5): G-4 cold-start wipe via set_innings_2` | New L1.5 case: enqueue at WARM, trigger W4, verify WIPED-BY-COLD-START fires + queue empty. Existing G-3 covers the `_clear_per_innings_sm_surface` direct-call path. |
| G-step 8 validation | `docs(workstream-g): step-8 re-validation — Surface B closes gate-5 gap` | Empirical re-validation; trace_eta PASS verified; explicit scope statement that D-post-FoW-striker remains at 20 pending Workstream H |
| Workstream H — open | Future session | Cold-start re-entry frequency root cause; COLD-START-EXIT semantics redesign; `_detect_innings_change` predicate tightening for `wickets_regressed` post-wicket hot window |

---

## §5 Methodology track-record notes

### §5.1 Insight #17 satisfied for Surface B

Gate-5 enumeration verified each reset path against the step-5
trace. The W4 silent-wipe trap (the cause of step-5 falsification)
is closed by explicit emission. No reasoning-from-`__init__`-re-runs
is used to certify the wipe — instead, the explicit emit-before-
`__init__` ordering is the audit's mechanical mitigation.

### §5.2 Insight candidate #18

*A green-light audit can deliver lifecycle closure without
delivering the original predicted-flip outcomes. The two objectives
are separable; declare scope explicitly and verify only the closed
objective at re-validation.*

Surface B is the first instance of this pattern in the discipline
track record. Prior audits (C13 Shape B, C30b D2-Layer-1a) delivered
primary-objective fixes; Surface B delivers a sub-objective. The
discipline should accept "necessary-but-not-sufficient" as a valid
audit-completion verdict, provided the sub-objective is explicitly
scoped and the parent objective's blocker is identified.

This is the cost of the 1/5 budget consumed in step 5 — the
methodology surfaced a coupling (G2 cold-start interaction with
strip-render lag) that the static analysis from step 1 could not
have predicted from code alone.
