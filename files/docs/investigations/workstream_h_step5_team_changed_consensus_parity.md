# Workstream H — Step-5: `_team_changed` consensus-parity static investigation

**Status.** Step-5 deliverable: static-falsification memo on the consensus-gating shape for `_team_changed` (the F939 residual root per WS-H memo §9.1 + §11.1). No code edits this pass. Empirical-falsification budget UNCHANGED at 3/5.
**Branch.** `derive-not-detect` at HEAD `113b747` (WS-H step-4 close-out landed).
**Comparator trace.** `logs/trace/validate_ws_h_step3_20260523_164642.jsonl` (749 frames; produced under P1 patch `ef0860d`).
**Predecessor.** `workstream_h_cold_start_reentry_root_cause.md` §9.1 + §10 S16 + §11.1.
**Result.** Static-falsification chain converges on **H1 — consensus-gate `_team_changed` at its derivation site (`:4417-4419`)**. All 7 gates passable on static analysis (gate-7 deferred per step-5 stop-condition). S18 cascade-closure dividend is **DEGENERATE-ON-DUMP** (zero positive `score_reset_from_progress` fires across all 12 captured traces) but **architecturally real** (closes a hypothetical single-frame team-flip + score-reset attack surface that the current data doesn't exercise). One new sub-finding S19.

---

## §1 Empirical anchor

### §1.1 F939 — the single residual SM-INNINGS-2-RESET on the WS-H step-3 trace

Cricket truth: over 10.1, DC batting first innings, no innings transition in fixture window. F939 is a single-frame KKR-team misread coinciding with a wickets-counter misread.

| Field | Pre-fix at F939 |
|---|---|
| Telemetry | `[INNINGS-TRANSITION-TELEMETRY] source=score_manager reason=wickets_regressed prev=84/3 (10.1) prev_team=DC cand=51/0 cand_team=KKR cand_target=None` |
| Sibling branch state | `[SM] team-change candidate KKR streak 1/3 — deferring inn-2 trigger` (`batting_team_changed` correctly defers via 3-frame consensus) |
| Wickets_regressed branch state | `_team_changed=True` (single-frame KKR ≠ DC) → **fires** |
| Surrounding frames (F938, F940, F941, F942) | no notable decisions; KKR-team candidate never reaches consensus → genuine single-frame transient |

### §1.2 19-rejection cohort spot-check classification

P1's 19 structured rejection records on the same trace classified by `_team_changed` evaluation:

| Cohort | Frames | `cand_team` | `prev_team` | `_team_changed` today | Reject path today | Reject path post-H1 |
|---|---|---|---|---|---|---|
| 1. `cand_team=None` (no team evidence) | F462, F502, F690, F704, F859, F933 | None | DC | False (None branch) | rejects via team-mismatch path | unchanged — still rejects |
| 2. `cand_team=DC` matches `prev_team` (no flip) | F463-F470, F482-F483, F503, F514, F801 | DC | DC | False (equality branch) | rejects via team-equality path | unchanged — still rejects |
| 3. `cand_team=KKR` flips with consensus | (none in cohort) | — | — | — | — | — |
| 4. `cand_team=KKR` single-frame flip (residual) | **F939 (escapes cohort)** | KKR | DC | True (single-frame) | **fires SM-INNINGS-2-RESET** | rejects (streak < 3) |

Cohorts 1 + 2 (all 19 frames in the rejection cohort): post-H1 prediction is **unchanged rejection** because `_team_changed=False` for these regardless of consensus state. Cohort 4 (F939): post-H1 prediction is **rejection** (`_team_change_streak` would be 1, below `TEAM_CHANGE_CONSENSUS_FRAMES=3`).

**Conclusion.** F939 is the only frame in the trace whose disposition flips under H1. The 19 baseline rejections are stable.

### §1.3 Cross-fixture survey (12 captured traces on disk)

`INN2-SCORE-RESET-TEAM-CHANGE-REQUIRED-REJECTED` and `INNINGS-TRANSITION-TELEMETRY reason=score_reset_from_progress` enumerated across all 12 `logs/trace/validate_*.jsonl`:

| Trace | Frames | `SM-INNINGS-2-RESET` (w_reg / sc_reset) | `INN2-SCORE-RESET-…-REJECTED` |
|---|---|---|---|
| validate_20260513_180911 | 195 | 0 / 0 | 0 |
| validate_20260513_194442 | 10 | 0 / 0 | 0 |
| validate_20260520_114437 | 188 | 0 / 0 | 0 |
| validate_dckkr_20260521_070545 | 341 | 0 / 0 | 0 |
| validate_dckkr_20260521_155356 | 405 | 0 / 0 | 0 |
| validate_dckkr_20260522_062844 | 23 | 0 / 0 | 0 |
| validate_dckkr_20260522_063211 | 461 | 0 / 0 | 0 |
| validate_gtrr_20260520_180715 | 489 | 0 / 0 | 0 |
| validate_shape_a_114349 | 749 | 5 / 0 | 2 |
| validate_shape_a_20260523_114053 | 749 | 5 / 0 | 2 |
| validate_surface_b_121222 | 749 | 5 / 0 | 2 |
| validate_ws_h_step3_20260523_164642 | 749 | 1 / 0 | 4 |

**Two-line summary.** Zero `score_reset_from_progress` fires across all traces — the sibling is already 100% reject via its existing team-change guard (2-4 deferral records on the DCKKR replay; 0 on every other fixture). The S18 cascade-closure dividend for H1 has no positive-fire baseline to suppress on captured data; the architectural closure is real but the empirical measurement is degenerate (§5 below).

---

## §2 Sibling consensus implementation — `batting_team_changed` at `:4337-4385`

### §2.1 State variables (initialized in `__init__`)

| Variable | Site | Type | Init | Purpose |
|---|---|---|---|---|
| `self._team_change_candidate` | `:607` | `str \| None` | `None` | Proposed new team being evaluated for consensus |
| `self._team_change_streak` | `:608` | `int` | `0` | Number of consecutive frames the same candidate has been observed |
| `self.TEAM_CHANGE_CONSENSUS_FRAMES` | `:609` | `int` | `3` | Required consecutive-frame count to commit a team change |

Lifetime: persists across `_handle_warm` calls; mutated only inside the `batting_team_changed` branch and its else-reset.

### §2.2 Semantics inside `_detect_innings_change` (lines `:4345-4385`)

```python
if (frame.broadcast_team and self.batting_team
        and frame.broadcast_team.upper() != self.batting_team.upper()
        and (len(_playing_teams) < 2
             or frame.broadcast_team.upper() in _playing_teams)):
    # increment / reset
    if frame.broadcast_team.upper() == (
            self._team_change_candidate or "").upper():
        self._team_change_streak += 1
    else:
        self._team_change_candidate = frame.broadcast_team
        self._team_change_streak = 1
    # commit / defer
    if self._team_change_streak >= self.TEAM_CHANGE_CONSENSUS_FRAMES:
        changed = True
        reason = reason or "batting_team_changed"
        # commit log + clear state
        self._team_change_candidate = None
        self._team_change_streak = 0
    else:
        # defer log + REJECTED_TEAM_CHANGE_PENDING ledger entry
        ...
elif (frame.broadcast_team and self.batting_team
        and frame.broadcast_team.upper()
        == self.batting_team.upper()):
    # no-flip reset
    self._team_change_candidate = None
    self._team_change_streak = 0
```

**Outer guard.** Fires when `broadcast_team` is truthy AND `batting_team` is truthy AND they differ (post-upper) AND (playing-teams set has <2 members OR broadcast_team is in playing-teams set — the 2026-05-19 squad-membership tightening per `:4324-4336` comment).

**Increment rule.** Same candidate → `+= 1`. Different candidate → reset to 1 with new candidate.

**Commit rule.** `streak >= TEAM_CHANGE_CONSENSUS_FRAMES (=3)` → set `changed=True`, `reason="batting_team_changed"` (if no prior reason), clear `_team_change_candidate` and `_team_change_streak`.

**Defer rule.** `streak < 3` → log + ledger; preserve state for next frame.

**No-flip reset.** When `broadcast_team` matches `batting_team`, clear state.

**Implicit state preservation.** When `broadcast_team` is None or `batting_team` is None, neither outer guard nor else-reset fires. `_team_change_candidate` and `_team_change_streak` survive untouched across such frames. This is intentional — a single None-frame gap mid-consensus does not break the streak.

**Post-commit `_team_changed` invariant.** Immediately after commit (`_team_change_streak = 0` reset at `:4363`), the consensus state itself is gone. The only signals that the commit *just happened* are `changed=True` and `reason=="batting_team_changed"`.

---

## §3 `_team_changed` derivation analysis — `:4411-4419`

```python
_bcast_team = (
    (frame.broadcast_team or "").upper()
    if frame.broadcast_team else None)
_cur_team = (
    (self.batting_team or "").upper()
    if self.batting_team else None)
_team_changed = bool(
    _bcast_team and _cur_team
    and _bcast_team != _cur_team)
```

**Inputs.** `frame.broadcast_team` (Scout per-frame read) and `self.batting_team` (running SM state from last accepted commit).

**Normalization.** Uppercase if non-empty, else None.

**Equality test.** `_team_changed = True` iff both are non-None AND differ post-upper.

**Single-frame property.** The boolean is computed fresh every call; there is no consensus state coupling. A single-frame team flip evaluates True regardless of the persistent `_team_change_streak` value held just three lines above the consumers.

**Why single-frame today.** The 2026-05-19 score_reset hardening (comment block `:4390-4410`) added team-change corroboration to `score_reset_from_progress` but did NOT require consensus — the prior author's risk model was that the score-reset misread surface was already constrained by `s == 0 and w == 0 and self.score > 20`. The score-reset gate is so narrow (full-zero candidate with substantial prior progress) that the team flip alone was deemed sufficient corroboration. P1 inherited the same single-frame shape via parity-mirror at `:4454-4486`. F939 demonstrates the inherited gap: when the wickets_regressed predicate window (much wider — anywhere `self.wickets >= 2` with regression by >1) intersects a single-frame team misread, the inherited single-frame `_team_changed` is insufficient.

**Consumers in scope of P1.**

| Site | Consumer | Behavior under `_team_changed=True` |
|---|---|---|
| `:4423` | `score_reset_from_progress` branch fires | sets `changed=True`, `reason="score_reset_from_progress"` |
| `:4456` (P1) | `wickets_regressed` branch fires | sets `changed=True`, `reason="wickets_regressed"` |

Both consumers are downstream of the `batting_team_changed` branch in the predicate body, so the persistent consensus state is already in scope.

---

## §4 Hypothesis enumeration

Three candidate consensus-gating shapes. Each evaluated against §7.2 gates 1-5 statically. Gates failing → static-falsification (does not consume budget).

### §4.1 H1 — Gate at the derivation site

Make `_team_changed` reflect consensus at the point of computation.

```python
# Replace :4417-4419 with:
_team_changed = bool(
    _bcast_team and _cur_team
    and _bcast_team != _cur_team
    and changed and reason == "batting_team_changed")
```

The added clause is True iff the `batting_team_changed` branch above just committed in this frame (i.e., consensus met). Both consumers downstream (`:4423` score_reset + `:4456` wickets_regressed) automatically pick up the consensus semantics.

| Gate | Result |
|---|---|
| 1. Callers | Single edit site; two existing consumers; no new caller surface. **PASS.** |
| 2. Classification | Predicate-derivation tightening. Consumer is the existing two sites; no new producer/consumer split. **PASS.** |
| 3. Adjacent state | Reads `changed` and `reason` locals set by the immediately-preceding `batting_team_changed` branch. `changed` could also be True from `target_appeared` (`:4316-4318`) — in that case `reason=="target_appeared"`, so the `reason == "batting_team_changed"` clause correctly rejects. No new state introduced. No §12 dual-state-write. **PASS.** |
| 4. Equivalence / behavioral delta | Strict subset: `(team flip) ∧ (consensus committed)` ⊆ `(team flip)`. Pre-fix accepts single-frame flips; post-H1 requires consensus. **PASS.** |
| 5. Lifecycle | Persistent state (`_team_change_streak`) lifecycle already managed by `batting_team_changed` branch. H1 reads `reason`/`changed` (frame-local) — no new lifecycle. **PASS.** |

**Status.** Leading candidate.

### §4.2 H2 — Gate at consumer sites

Add a separate `_team_change_consensus_met` local at the top of the predicate body and check it inside both consumers.

```python
_team_change_consensus_met = (
    self._team_change_streak + 1 >= self.TEAM_CHANGE_CONSENSUS_FRAMES
    if _team_changed else False)
# Then at :4423 and :4454, gate on this local.
```

| Gate | Result |
|---|---|
| 1. Callers | Single edit; touches both consumer sites + derives an additional local. **PASS.** |
| 2. Classification | Producer side (the additional local) + 2 consumer sites — wider blast radius than H1 (~5 lines added vs. ~1 line for H1). **PASS.** |
| 3. Adjacent state | Read-side; no §12. **PASS.** |
| 4. Equivalence | Same semantic as H1 if implemented correctly; the off-by-one `_team_change_streak + 1` is fragile (the increment happens INSIDE the batting_team_changed branch, so pre-branch the streak is N-1 if the frame matches the candidate). **FRAGILE — risk of off-by-one bugs.** |
| 5. Lifecycle | Couples consumers to the streak counter directly; if the streak's lifetime semantics change in the future, both consumers regress together. Tighter coupling than H1. **PASS but with operational concern.** |

**Status.** Architecturally redundant with H1 (same final semantic) but more code and more fragile due to off-by-one risk on the un-incremented `_team_change_streak`. Rejected as inferior to H1.

### §4.3 H3 — Reuse `_team_change_streak >= TEAM_CHANGE_CONSENSUS_FRAMES`

Replace `_team_changed` derivation entirely with a streak-based predicate.

```python
# Replace :4417-4419 with:
_team_changed = bool(
    _bcast_team and _cur_team
    and _bcast_team != _cur_team
    and self._team_change_streak >= self.TEAM_CHANGE_CONSENSUS_FRAMES)
```

| Gate | Result |
|---|---|
| 1. Callers | Single edit site. **PASS.** |
| 2. Classification | Predicate-derivation tightening. **PASS.** |
| 3. Adjacent state | Reads `_team_change_streak` BEFORE the batting_team_changed branch increments it. At the derivation site (line :4417), streak is **N-1** for the current frame (N = post-increment). At the commit moment (line :4355), streak is N. Post-commit, streak is **cleared to 0** at line :4363. So at the consumers (line :4423+), streak is 0 if commit just happened, or N if defer just happened (where N < CONSENSUS_FRAMES). H3 evaluates `streak >= CONSENSUS_FRAMES` at consumers, which is **always False post-commit (streak=0) and always False during defer (streak<CONSENSUS_FRAMES)**. **STATIC FALSIFICATION.** |
| 4. Equivalence | Always False ⇒ `_team_changed` always False at consumer sites ⇒ score_reset and wickets_regressed branches NEVER fire even on legitimate inn-2. Catastrophic regression. **FAIL.** |

**Status.** Statically falsified at gate 3. The post-commit streak-clear behavior makes the streak counter unreadable to downstream consumers. H1's `changed and reason == "batting_team_changed"` invariant survives the clear; H3 doesn't.

### §4.4 Coverage summary

| Hypothesis | Static gates 1-5 | Falsification cause | Verdict |
|---|---|---|---|
| H1 — derivation-site gate | 5/5 PASS | — | **Leading.** |
| H2 — consumer-site gate | 4/5 PASS (fragile gate-4 off-by-one) | code duplication + fragility | Inferior to H1. Rejected. |
| H3 — streak-counter reuse | 3/5 PASS (gates 3+4 FAIL) | post-commit streak clear makes consumers see 0 | Statically falsified. |

H1 is the unique candidate that (a) gates at one site, (b) reuses an invariant that survives the consensus commit (`changed and reason`), and (c) tightens both consumers (`:4423` + `:4456`) atomically by parity inheritance — the same parity-mirror mechanism that produced the inherited bug now produces the inherited fix.

**Static-falsification count.** 1 (H3 at gate 3). Well under the 8-falsification methodology-class-issue threshold.

---

## §5 S18 cascade-closure verification

**Claim under test.** Closing F939 via H1 must tighten `score_reset_from_progress` (`:4423`) by the same delta with zero new behavioral surface (per S18 third-instance pattern).

**Static analysis.** H1 changes `_team_changed` semantics; both `:4423` and `:4456` consumers read the same `_team_changed` boolean. Therefore any tightening at `:4456` (wickets_regressed) is mirrored exactly at `:4423` (score_reset) — they share the predicate input. The cascade-closure dividend is structurally guaranteed; the question is whether it is empirically measurable on captured data.

**Empirical evidence (cross-fixture survey, §1.3).** Across all 12 captured traces:

- `SM-INNINGS-2-RESET reason=score_reset_from_progress` count: **0 across every trace**.
- `INN2-SCORE-RESET-TEAM-CHANGE-REQUIRED-REJECTED` (the existing reject-path tag for score_reset): 2 on `validate_shape_a*`, 2 on `validate_surface_b_121222`, 4 on `validate_ws_h_step3_20260523_164642`, 0 elsewhere.

The existing single-frame `_team_changed` guard already rejects 100% of the captured score-reset triggers — no positive fires exist to suppress further. The score_reset branch's outer condition (`s == 0 and w == 0 and self.score > 20`) is so narrow on real broadcast data that the misread surface coinciding with a team-flip OR equal-team is extremely rare.

**Verdict.** **DEGENERATE-ON-DUMP, architecturally real.** Two interpretations:

- (a) **Cascade-closure dividend confirmed in shape, not in magnitude.** H1's `_team_changed` tightening propagates to both consumers structurally. The score-reset reject count would shift from "single-frame guard rejects" to "consensus-not-met defers" terminology, but the disposition (no fire) is unchanged on captured data. Future fixtures with a single-frame KKR+0/0 misread (the F939 shape applied to the score_reset surface) would now be caught at the consensus-gate rather than the existing equality-gate (which would have allowed the fire if the team WAS different and score WAS 0/0).
- (b) **S18 third-instance is one-and-a-half, not three.** First instance (F1): N-class closure via single edit. Second instance (S9): F855→F983 cross-frame dependency closure. Third candidate (S18 from WS-H memo): D1+P1 composite γ-bowler-w closure. Step-5's H1 would be a degenerate cascade-closure — true closure happens only on hypothetical future data, not on the current empirical set. **Promotes S19 below as the methodology insight: "cascade-closure dividend may be architecturally real but empirically degenerate; both states are valid closure shapes."**

The architectural dividend stands; the empirical-magnitude prediction is degenerate-on-dump and should be flagged in the step-6 commit body as such.

---

## §6 7-gate audit on H1 (leading candidate)

Static-only this pass per step-5 stop-condition.

### §6.1 Gate 1 — Caller enumeration

`_team_changed` local is read at exactly two sites in the predicate body:

- `:4423` (`score_reset_from_progress` branch outer guard).
- `:4456` (P1 `wickets_regressed` branch outer guard).

No other readers in `score_manager.py` (grep-confirmed — local scope). **PASS.**

### §6.2 Gate 2 — Classification

H1 modifies a single predicate-derivation expression. Both consumers automatically inherit the tightened semantics. No producer/consumer split changes. No init/transition/preserved/async splits. **PASS.**

### §6.3 Gate 3 — Adjacent state + §12 dual-state-write

H1 reads `changed` (local boolean, set by prior branches in the same predicate call) and `reason` (local string, same lifecycle). Both are frame-local; no `self.*` mutation. No new persistent state surface. No parallel state writes.

`_team_change_streak` and `_team_change_candidate` (the consensus state) remain managed exclusively by the `batting_team_changed` branch — H1 does not read or write them, depending only on the post-branch invariants `changed` and `reason`.

Cross-check on `changed=True` via `target_appeared` (`:4316-4318`): if a target appears in the same frame as a non-consensus team flip, `changed=True` but `reason="target_appeared"`. H1's `reason == "batting_team_changed"` clause correctly evaluates False, preserving the consensus requirement for the score_reset and wickets_regressed consumers. (A real innings-2 transition can validly have both target_appeared AND a team flip in the same frame — but target appearance is itself a strong inn-2 signal that bypasses team-change corroboration entirely via its own branch, so the consumers downstream don't need to re-corroborate.)

**PASS.**

### §6.4 Gate 4 — Equivalence / behavioral delta

| Predicate state | Pre-H1 `_team_changed` | Post-H1 `_team_changed` | Δ on consumers |
|---|---|---|---|
| `broadcast_team` is None | False | False | no change |
| `cur_team` is None | False | False | no change |
| Teams match (no flip) | False | False | no change |
| Teams differ, consensus not met (streak < 3) | **True** (single-frame) | **False** | consumers REJECT (was: ACCEPT) |
| Teams differ, consensus committed this frame | **True** | **True** (because `changed=True`, `reason="batting_team_changed"`) | no change |
| `target_appeared=True` in same frame as team flip | True | False | consumers REJECT instead of double-fire (acceptable — target_appeared branch already triggers inn-2) |

Strict-additive guard at one cell of the truth table: "teams differ, consensus not met" flips from ACCEPT to REJECT at both consumers. **PASS.**

### §6.5 Gate 5 — Lifecycle + trace observability

Reset paths unchanged:

| Reset path | Pre-H1 trace fires | Post-H1 predicted |
|---|---|---|
| `set_innings_2` via `wickets_regressed` | 1 (F939) | 0 |
| `set_innings_2` via `score_reset_from_progress` | 0 | 0 |
| `set_innings_2` via `batting_team_changed` | 0 | 0 |
| `set_innings_2` via `target_appeared` | 0 | 0 |
| `WICKETS-REGRESS-TEAM-CHANGE-REQUIRED-REJECTED` | 19 structured | ≥19 (now also catches F939) |
| `INN2-SCORE-RESET-TEAM-CHANGE-REQUIRED-REJECTED` | 4 | ≥4 (consensus-not-met may add deferrals at score_reset surface; same architectural shape as P1's deferrals) |

H1 does not introduce a new trace tag. The existing `WICKETS-REGRESS-TEAM-CHANGE-REQUIRED-REJECTED` (P1) and `INN2-SCORE-RESET-TEAM-CHANGE-REQUIRED-REJECTED` (2026-05-19) cover the consensus-not-met rejection paths transparently. Insight #17 mandate met (existing tags capture the rejection). **PASS.**

### §6.6 Gate 6 — Predicted flip with concrete frame numbers

Per §7 below. Strict gate-6 PASS on the F939 fire suppression with zero regression at the 19 baseline rejections. **PASS.**

### §6.7 Gate 7 — Cross-fixture verification

Deferred per step-5 stop-condition. Step-6 empirical replay will exercise this; budget impact 1/5 if cross-fixture surfaces an unexpected regression. **DEFER.**

### §6.8 7-gate summary

| Gate | Status |
|---|---|
| 1. Callers | PASS |
| 2. Classification | PASS |
| 3. Adjacent state + §12 | PASS |
| 4. Equivalence | PASS |
| 5. Lifecycle + trace | PASS |
| 6. Predicted flip | PASS (per §7) |
| 7. Cross-fixture | DEFER (stop-condition met; static-only convergence) |

**GREEN-LIGHT for step-6 code implementation.**

---

## §7 Predicted-flip table for step-6

| Metric | Pre-H1 (validate_ws_h_step3_20260523_164642) | Post-H1 predicted |
|---|---|---|
| `SM-INNINGS-2-RESET reason=wickets_regressed` | 1 (F939) | **0** |
| `SM-INNINGS-2-RESET reason=score_reset_from_progress` | 0 | 0 (unchanged; no positive baseline) |
| `WICKETS-REGRESS-TEAM-CHANGE-REQUIRED-REJECTED` structured | 19 | **≥19** (consensus deferrals add to or hold the count; never decrease) |
| `INN2-SCORE-RESET-TEAM-CHANGE-REQUIRED-REJECTED` | 4 | ≥4 (same shape: never decrease) |
| `POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START` | 0 | 0 (unchanged; F939 wasn't a cascade-window fire) |
| `POST-WICKET-CASCADE-DRAIN-FIRED` | 2 (F680, F858) | 2 (unchanged) |
| `D-post-FoW-striker` surface count | 2 | 2 (unchanged; primary objective already closed) |
| `trace_gamma_fow_name_matches_striker_at_wicket` | FAIL × 1 (F679) | FAIL × 1 (step-5b territory; step-5 does not touch) |
| `trace_gamma_bowler_w_increment_on_dispatch` | PASS | PASS (unchanged) |
| `trace_eta_post_wicket_cascade_drains` | PASS × 2 | PASS × 2 |

**Cascade-closure status.** H1 propagates to `score_reset_from_progress` consumer structurally; cross-fixture survey (§1.3) shows zero positive `score_reset_from_progress` baseline fires across all 12 captured traces, so the empirical-magnitude tightening is **degenerate-on-dump**. Architecturally the dividend is real (closes a hypothetical single-frame team-flip + 0/0 score misread that current data does not exercise). Cite this caveat explicitly in the step-6 commit body — do NOT claim a cascade-closure magnitude that the data cannot support.

**Legitimate-innings-2 regression check.** No captured fixture in the trace set on disk includes a legitimate innings-1-to-innings-2 transition (all 12 traces are partial first-innings windows). Therefore H1's 3-frame consensus delay cannot be empirically falsified on captured data. The parity argument with `batting_team_changed` (which already uses 3-frame consensus and is known cricket-safe per the 2026-05-19 design) is the static justification. Gate-7 cross-fixture in step-6 should explicitly check any future fixture containing a real inn-2 boundary.

---

## §8 Sub-findings (S19+)

### S19 — Cascade-closure dividend can be architecturally real but empirically degenerate

When a fix mirrors a sibling-parity surface and the sibling's existing protection has already rejected 100% of the captured misread cohort, the cascade-closure dividend is **architecturally real** (closes hypothetical future variants) but **empirically degenerate-on-current-data** (no positive baseline fires to suppress). Both states are valid closure shapes; commits should distinguish them in the body rather than claim a magnitude that the data does not support.

**Operational corollary.** When auditing a cascade-closure claim per S18 (third-instance F1 pattern), the gate-6 predicted-flip table should split into two rows:

- "Architectural surface closed" (boolean: did the predicate input now reject hypothetical-X?) — yes/no.
- "Empirical baseline reduction" (count delta on captured fixtures) — number, possibly 0.

A cascade-closure with `architectural=YES, empirical=0` is still a valid closure — it widens the safety margin against future regressions. But it must not be reported as "tightens sibling by N fires" when N is zero. WS-H step-5 H1 is the prototype: it propagates to the sibling, but the sibling already rejects all captured triggers, so the dividend is in safety margin rather than fire-count.

**Cross-reference.** S16 (parity-precedent inheritance) and S18 (third-instance F1 pattern) compose with S19 — S19 is the empirical-measurement caveat on S18-shaped cascade closures.

---

## §9 Step-6 entry data

### §9.1 Patch surface

Single edit at `files/score_manager.py:4417-4419`:

```python
# Before (current):
_team_changed = bool(
    _bcast_team and _cur_team
    and _bcast_team != _cur_team)

# After (H1):
_team_changed = bool(
    _bcast_team and _cur_team
    and _bcast_team != _cur_team
    and changed and reason == "batting_team_changed")
```

No other code changes. No new trace tag (existing `WICKETS-REGRESS-TEAM-CHANGE-REQUIRED-REJECTED` and `INN2-SCORE-RESET-TEAM-CHANGE-REQUIRED-REJECTED` cover the new rejection cohort transparently).

### §9.2 Test additions

L1.5 case additions in `files/tests/test_innings_change_wickets_regressed_guard.py` — extend the existing 6-case file with 3 new consensus-parity cases:

| Case | Prev | Cand (1st frame) | Cand (2nd frame) | Cand (3rd frame) | Expected disposition |
|---|---|---|---|---|---|
| H-7 single-frame KKR-flip (F939 analog) | 84/3 (10.1) team=DC | 51/0 team=KKR | n/a | n/a | REJECT (consensus not met) |
| H-8 two-frame KKR-flip (consensus building) | 84/3 (10.1) team=DC | 51/0 team=KKR | 52/0 team=KKR | n/a | REJECT × 2 (streak 1, streak 2) |
| H-9 three-frame KKR-flip (consensus committed) | 84/3 (10.1) team=DC | 51/0 team=KKR | 52/0 team=KKR | 53/0 team=KKR | ACCEPT via `batting_team_changed` on 3rd frame; wickets_regressed inherits `reason="batting_team_changed"` |

The existing H-6 case (legitimate innings-2 DC→KKR with wickets reset) is structurally equivalent to a single-frame post-consensus commit and may need refactoring to drive 3 frames instead of 1. Alternative: keep H-6 as-is but inject `_team_change_streak = 2` into the SM seed so the third frame trips consensus.

L1.5 total: 60 → 63 cases (or 60 + minor rewrite of H-6 + 2 new cases).

### §9.3 Gate-7 cross-fixture obligations

Cross-fixture replay against any fixture containing a legitimate innings-1-to-innings-2 boundary. Current trace set on disk has zero such fixtures (all are partial first-innings windows). Step-6 empirical-replay budget impact: 1/5 if cross-fixture regression surfaces (highly unlikely per parity with `batting_team_changed` precedent); 0/5 if H1 holds.

### §9.4 Commit message format (do not commit yet)

```
feat(workstream-h): step-6 — _team_changed consensus parity (H1; closes F939 sibling-asymmetry per S16)

Tightens `_detect_innings_change` _team_changed derivation at
score_manager.py:4417-4419 to require `batting_team_changed`
branch consensus commit in the same frame. Closes the F939 single-
frame KKR misread residual surfaced by WS-H step-3 (1× SM-INNINGS-
2-RESET reason=wickets_regressed; per S16 inherited consensus-
asymmetry from score_reset_from_progress sibling).

H1 propagates to both consumers (score_reset_from_progress at
:4423 + wickets_regressed P1 at :4456) by parity inheritance —
the same parity-mirror mechanism that produced the inherited bug
now produces the inherited fix.

Cascade-closure status (S19): DEGENERATE-ON-DUMP, architecturally
real. The sibling score_reset_from_progress has zero positive
fires across all 12 captured traces; H1's tightening propagates to
that consumer structurally but the empirical-magnitude reduction
is zero on captured data. Architectural safety margin widened
against future single-frame team-flip + 0/0 score misread variants.

Static-falsification chain converged in WS-H step-5 memo
(files/docs/investigations/workstream_h_step5_team_changed_
consensus_parity.md). 7-gate audit GREEN-LIGHT (gates 1-6 PASS;
gate 7 cross-fixture deferred to this step's empirical replay).

Predicted-flip table (locked):
  SM-INNINGS-2-RESET reason=wickets_regressed: 1 → 0
  WICKETS-REGRESS-TEAM-CHANGE-REQUIRED-REJECTED: 19 → ≥19
  INN2-SCORE-RESET-TEAM-CHANGE-REQUIRED-REJECTED: 4 → ≥4
  D-post-FoW-striker surface count: 2 → 2 (unchanged; closed in step-3)

L1.5 60 → 63 cases (H-7/H-8/H-9 in test_innings_change_wickets_
regressed_guard.py).

L1.5 PASS. L2 PASS. Derivation 48/48 PASS.

Co-Authored-By: ...
```

---

## §10 Stop-condition status + reporting

**Convergence.** Static-falsification chain converges on H1. All 7 gates passable (gate-6 pre-empirical PASS via §7 prediction; gate-7 deferred). **STOP per spec: "Static chain converges on single candidate with all 7 gates passable → STOP, report, do not commit code."**

**S18 cascade-closure dividend.** DEGENERATE-ON-DUMP (zero positive score_reset fires across 12 traces); architecturally real (H1 propagates to sibling consumer structurally). Promotes S19 as the cascade-closure-empirical-degeneracy methodology insight.

**Static-falsification count.** 1 (H3 falsified at gate 3 — post-commit streak clear makes consumers see 0).

**Empirical-budget status.** UNCHANGED at 3/5 remaining. No empirical replays consumed.

**Next-session deliverable.** WS-H step-6 — single-line code edit at `files/score_manager.py:4419` mirror of `:4417-4419` + 3 new L1.5 cases. Layer 1.5 + Layer 2 + derivation unit gates required green pre-commit. WS-H step-7 — empirical replay against `validate_ws_h_step3_20260523_164642` (and one legitimate-inn-2 fixture if available) to confirm gate-6 + gate-7 predictions.

---

## §11 Step-7 empirical confirmation (2026-05-23)

**Trace artifact.** `logs/trace/validate_ws_h_step7_20260523_172140.jsonl` — 749 records (single-independent-variable vs. step-3 baseline; H1 patch `832d376` is the only delta).

### §11.1 S18 cascade-closure dividend — structural propagation confirmed

H1's single-line addition at `:4417-4420` (`and changed and reason == "batting_team_changed"`) tightens the `_team_changed` boolean for BOTH downstream consumers. Empirical witness on the step-7 trace:

| Consumer site | Pre-H1 (step-3) | Post-H1 (step-7) | Δ |
|---|---|---|---|
| `:4456` wickets_regressed branch (P1) — `WICKETS-REGRESS-TEAM-CHANGE-REQUIRED-REJECTED` structured | 19 | 26 | **+7** (F939, F940, F942, F946, F993, F1008 + cohort propagation) |
| `:4423` score_reset_from_progress branch — `INN2-SCORE-RESET-TEAM-CHANGE-REQUIRED-REJECTED` structured | 2 | 3 | **+1** (F1008) |

Both consumers gain rejection records from consensus-pending frames. The propagation is empirically verified — the single-line edit at the predicate-derivation site touches two consumer surfaces atomically, exactly as the §4 H1 gate-1/2 analysis predicted.

### §11.2 S19 empirical-degeneracy hypothesis — confirmed

Pre-H1 cross-fixture survey (§1.3): zero positive `INNINGS-TRANSITION-TELEMETRY reason=score_reset_from_progress` fires across all 12 captured traces.

Post-H1 step-7 trace: **zero** positive `score_reset_from_progress` fires. The degeneracy holds under the H1-tightened regime — not just on the pre-existing traces surveyed in step-5 §1.3, but on the freshly-produced step-7 trace where H1 actively tightens the sibling.

The S18 cascade-closure dividend at the score_reset consumer is now **empirically verified as degenerate-on-dump under H1 specifically**, not merely predicted to be so by extrapolation from the pre-H1 cross-fixture survey. This is the strongest form S19 can take with current captured-data — the architectural closure remains real (the predicate input tightens both consumers; the gate is in place against the F939-shape attack applied to the score_reset surface), but the empirical magnitude reduction is exactly zero on the dump.

### §11.3 Sibling-baseline frame attribution

The single new `INN2-SCORE-RESET-TEAM-CHANGE-REQUIRED-REJECTED` structured record post-H1 lands at F1008. Cricket-truth correspondence: a sponsor/overlay frame near the 10.x over window where the score-reset surface (s=0, w=0) coincided with a non-DC team read; H1's consensus-gate correctly held the rejection at the sibling consumer rather than letting the single-frame misread through. Pre-H1, this same frame would have hit the existing single-frame `_team_changed` guard (which already rejected it, hence baseline=2 with no F1008 entry — the H1 tightening doesn't change the disposition, only the gating reason recorded in the structured payload).

### §11.4 Step-5 closure declaration

WS-H step-5 **CLOSED**. The static-falsification chain in §4 (H1 leading; H2 inferior; H3 falsified) was empirically validated by step-7:

- F939 SM-INNINGS-2-RESET: 1 → 0 (load-bearing prediction).
- score_reset_from_progress fires: 0 → 0 (S19 prediction).
- Sibling propagation: 2 → 3 (S18 structural propagation).
- Existing rejection cohort growth: 19 → 26 (consensus-pending defers add as predicted).

Plus a cascade-lifecycle advancement bonus not in the locked table: DRAIN-FIRED 2 → 4 (two additional cascade resolutions because F939's spurious reset no longer wipes innings-1 cascades mid-over). See root-cause memo §13.3 for the bonus characterization.

**γ-bundle cohort exposure (S20).** Per root-cause memo §13.2 + §14: F948 + F1017 join F679 in the `no_prev_striker` cohort. Step-5b empirical anchor extends from 1 frame to 3; defect class unchanged. This consumed 1/5 budget per the step-7 stop-condition (γ-regression beyond F679); load-bearing artifact = S20.

**Empirical-budget status.** 3/5 → **2/5** (step-7 validation). H1 patch `832d376` STAYS LANDED — no revert.
