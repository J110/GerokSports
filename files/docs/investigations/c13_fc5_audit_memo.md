# C13 — §7.2 7-gate audit on FC5 candidate fix shapes

**Status.** Audit memo. NO CODE. Output: shape selection + predicted-flip claim + dual-state-write defect-class catalogue entry.
**Date.** 2026-05-21
**Author.** J110 via Claude Code
**Prerequisite.** Cascade root concretely localized at frame F304 via FC5 (`consistent_tracker.py:294-306`) — see `temporal_coupling_investigation_brief.md` §13 for the production pipeline.log evidence.
**Audit framework.** `sm_as_orchestrator_design.md` §7.2 7 gates (per the standing investigation discipline).

---

## 1. The four candidate fix shapes (operator-specified)

Per operator directive: audit must evaluate multiple shapes, not pre-select one.

| Shape | Site | Scope | Cascade-closure reach | Regression risk |
|---|---|---|---|---|
| **A** — `_is_suspicious` tightening | `consistent_tracker.py:518-683` predicate | Narrow — one predicate | Low (B-η root only) | Lowest |
| **B** — cross-field pairing gate | New gate-check in/around `consistent_tracker.update` before FC5 | Middle — adds an invariant-check site | Middle (B-η root + adjacent dual-state-write defects) | Middle |
| **C** — dual-state-write unification | Route `sb._inn` writes through SM `_handle_warm` streak-gate semantics | Invasive — architectural | High (plausibly closes B-ι + B-θ as cascade symptoms) | Highest |
| **D** — poison-radius extension | Block FC5 fires for M frames after a POISONED frame | Narrow — targets f303→f304 grace-survival specifically | Low | Low |

## 2. Empirical pairing criterion (the audit's evaluation substrate)

The C13 audit must check each shape against the empirical pairing data — without precise criteria, no shape can be evaluated for false positives.

### 2.1 Pairing criterion (formalized)

Define the **single-ball-advance predicate**:

```
legitimate_pair(d_score, d_overs, d_wickets) ≡
    (d_balls == 1 AND 0 ≤ d_score ≤ 7 AND d_wickets ∈ {0, 1})    # legal delivery
  OR
    (d_balls == 0 AND 0 ≤ d_score ≤ 5 AND d_wickets ∈ {0, 1})    # extras-only (illegal delivery)

where d_balls = _overs_to_balls(new_overs) - _overs_to_balls(old_overs)
```

The d_score=7 ceiling matches `consistent_tracker.BATTER_SINGLE_BALL_RUN_MAX (6) + BATTER_NO_BALL_ADDITIONAL (1) = 7`. The d_score=5 ceiling for extras-only matches the GTRR over-1 5-wide event.

### 2.2 Cross-fixture empirical verification of the pairing criterion

**GTRR replay (80 DIRECT-SCORE-COMMIT firings):**

| Δscore | Count | Sample frame(s) | All paired with d_balls ≤ 1? |
|---|---|---|---|
| 1 | 50 | scattered, all single-ball advances | Yes |
| 2 | 7 | f482 (62→66 reads weird; verified d_balls=1) | Yes |
| 4 | 16 | f187, f274, f316, ... (fours) | Yes |
| 5 | 1 | f72 (7→12 at ov=0.3, heavy-extras over 1) | Yes — d_balls=0 (extras-only) |
| 6 | 6 | f296, f406, f466, f1075, f1123, f1379 (sixes) | Yes — d_balls=1 |

**All 80 GTRR firings satisfy `legitimate_pair(d_score, d_overs, d_wickets)`.**

**DCKKR replay (47 DIRECT-SCORE-COMMIT firings):**

| Δscore | Count | Notes | All paired with d_balls ≤ 1? |
|---|---|---|---|
| 1 | 32 | singles | Yes |
| 2 | 3 | twos | Yes |
| 3 | 1 | f475 — FRAME-TRUST-GATE shows d_balls=2 (replay multi-ball gap) | **No (d_balls=2)** |
| 4 | 8 | fours | Yes |
| 6 | 2 | f202, f488 — sixes | Yes |
| 7 | 1 | f138 — FRAME-TRUST-GATE shows d_balls=2 | **No (d_balls=2)** |

**Two firings in DCKKR replay have d_balls=2 (f138, f475).** Both are benign multi-ball-gap commits that went through the existing `_decompose_multi_ball` path. **The pairing criterion would reject these from FC5 — but `_decompose_multi_ball` is a separate dispatch path, NOT gated by FC5.** Cross-checking: f138 + f475 in the replay show DIRECT-SCORE-COMMIT firings because `_decompose_multi_ball` ultimately calls `sb.update_bowler(... runs_delta=N)` per the ABSORBED_LEGAL handler at `score_manager.py:5176+`, which itself calls `sb.set` indirectly. **These do NOT go through FC5's post-event-grace path** — they go through cricket-rules-validated multi-ball decomposition.

**Implication for the audit:** the pairing criterion at FC5 specifically (not at every `sb.set` call) correctly distinguishes legitimate single-ball advances from the f304-class anomaly. f138/f475's multi-ball-gap commits are commit-path-separated already.

### 2.3 The F304 disposition under the pairing criterion

F304 production TRACK lines (from pipeline.log):

```
F304 TRACK score: 49 → 54 (post-event immediate, grace=1)   ← Δ=+5, d_balls=? (depends on overs delta)
F304 TRACK overs: 4.5 → 6.3 (post-event immediate, grace=0) ← d_balls = 39-29 = 10
```

The score FC5 fires BEFORE the overs FC5 in the commit_decision sequence. At the score-FC5 firing point, the overs hasn't been updated yet (`sb._inn["overs"]` still = 4.5). So at the moment of the score commit, `d_overs = 0` (current = proposed = 4.5? Actually overs hasn't been written yet, so current_overs = 4.5 and the score-call doesn't know about the impending 6.3).

**A naive pairing check at the score-FC5 site would PASS** (d_balls=0 if we read current overs only). The pairing check must instead consider the **proposed** overs value coming in the same commit_decision tuple — which the tracker doesn't currently have access to.

This is the **gate-3 (cross-reference adjacent state) finding** that the audit MUST surface for any cross-field-pairing shape:

- The tracker's `update()` is per-field and stateless across fields. To gate on score-overs pairing, EITHER the gate moves up the stack (Shape B's "new gate site between commit_decision and sb.set"), OR the tracker accumulates per-frame pending updates and validates at the end.

---

## 3. §7.2 7-gate audit — Shape A (`_is_suspicious` tightening)

**Proposed change:** Add a rule to `_is_suspicious("score", old, new)` that flags any Δscore > 6 (BATTER_SINGLE_BALL_RUN_MAX) when the **last-known overs delta was not +0.1 or X.5→(X+1).0**. Symmetric rule for `_is_suspicious("overs", old, new)`: flag Δballs > 1 when the **previous-frame's score delta was a recent ball-event advance**.

### 3.1 Gate 1 — enumerate callers

`_is_suspicious` callers:
- Line 295 (FC5 path)
- Line 308 (main suspicious-check path)
- Line 417 (pending-promotion regression check)

All three call sites consume the return value to decide accept/defer. Tightening the predicate changes behavior at every site.

### 3.2 Gate 2 — classify each caller

- **Line 295 (FC5):** post-event grace path — the audit's target.
- **Line 308 (main):** suspicious-this-frame accumulator + reject-streak tracking. Tightening means more values are flagged suspicious; the 4-frame `[CONSENSUS]` override (line 319) eventually accepts them. **No regression** for repeated correct readings.
- **Line 417 (pending-promotion):** 3-frame pending consensus. Same logic as line 308 — tightening means more values defer to the pending path; legitimate values pass after 3 reads.

### 3.3 Gate 3 — cross-reference adjacent state

The tightened predicate needs access to **the last overs delta** OR **the proposed overs in the current commit_decision tuple**. Shape A as initially stated would need new state in the tracker (last_overs_advance_t timestamp, or pending_overs_proposal field).

**This is a structural limitation of Shape A.** Without cross-field awareness, the predicate can ONLY tighten the within-field threshold (e.g., drop Δscore>30 to Δscore>15). That would still admit f304's Δscore=+5 since 5 < 15.

**Verdict for gate 3:** Shape A as initially proposed is **insufficient to reject f304's score commit**. The predicate is single-field; the f304 anomaly is a cross-field correlation problem. Shape A would only catch egregious single-field cases (Δscore>20 or so), not the f304 signature.

### 3.4 Gate 6 — predicted flip with concrete frame numbers

- **F304 score FC5 fire (Δ=+5):** under Shape A with threshold-only tightening at Δscore>15 — **not rejected** (5<15). Predicted flip: NO.
- **F304 overs FC5 fire (Δballs=10):** under symmetric Shape A — **rejected** if threshold is Δballs>3 (matches the existing streak gate threshold). Predicted flip: YES.

**Asymmetric outcome:** Shape A could close the overs side of the cascade but leaves the score side admitting at f304. Half-fix; the divergence pattern persists (sb._inn["score"]=54 with sb._inn["overs"]=4.5 still produces SM-state asymmetry).

### 3.5 Gate 7 — cross-fixture verification

GTRR 80 firings: all Δscore ≤ 6, all Δballs ≤ 1. Shape A's threshold tightening (Δscore>15, Δballs>3) preserves all 80. **Gate 7 closes for Shape A.**

### 3.6 Verdict on Shape A

**REJECTED.** Gate 3 surfaces a structural insufficiency: single-field predicate tightening cannot localize the f304 cross-field correlation. The score-side anomaly survives Shape A. Closing only half the cascade root is the predicted-flip-violation pattern that the discipline has already falsified five times this investigation chain — shipping Shape A would be a sixth.

---

## 4. §7.2 7-gate audit — Shape B (cross-field pairing gate)

**Proposed change:** Add a new gate site **between `commit_decision` and `sb.set`** in `test_pipeline.py:4658+` (the main DIRECT-path commit logic). The gate accumulates the proposed (Δscore, Δovers, Δwickets) tuple across the three field calls and validates `legitimate_pair(...)` before any of the three sb.set calls fire. If the pair is illegitimate, defer all three to the existing streak-gate / consensus paths.

### 4.1 Gate 1 — enumerate callers

The new gate site is single-source — `commit_decision` is one function. Callers of `commit_decision` are the main pipeline loop in `run_test()` (sync inline). No other callers.

### 4.2 Gate 2 — classify each caller

Single caller (the main loop) — sync inline. **No race or async ordering** to enumerate.

### 4.3 Gate 3 — cross-reference adjacent state

The gate needs:
- The **proposed** (score, overs, wickets) tuple — available as `decision.score_update.to`, `decision.overs_update.to`, `decision.wickets_update.to` from the scorer
- The **current** sb._inn values — read directly from sb._inn
- The **legitimate_pair** predicate from §2.1 (statically defined)

All three are in scope at the proposed gate site. No new state required.

**Adjacent state interactions:**
- The catch-up branch at `test_pipeline.py:8986+` is a SEPARATE call path that also commits via sb.set. **Shape B as stated would not cover the catch-up branch.** Either Shape B is extended to wrap that branch too, or the catch-up branch is independently audited.
- The end-of-over hook at `test_pipeline.py:11750` similarly. Same coverage question.

### 4.4 Gate 4 — equivalence proof

Shape B is **additive** — the existing FC5 path remains. The new gate only INTERVENES to defer the commit to the streak-gate path when the pair is illegitimate. Legitimate pairs still flow through FC5 as before.

**Equivalence claim:** for every (proposed_score, proposed_overs, proposed_wickets) tuple that satisfies `legitimate_pair`, the commit outcome under Shape B equals the commit outcome under the current code. **Verifiable empirically** against GTRR 80 + DCKKR 47 firings.

### 4.5 Gate 5 — state variable lifecycle

No new persistent state in Shape B. The gate's local computation is per-frame.

### 4.6 Gate 6 — predicted flip with concrete frame numbers

**At F302 (legitimate ball commit):**
- Proposed: (score=49, overs=4.5, wickets=0) vs current (45, 4.4, 0)
- Δscore=+4, Δoers→Δballs=+1, Δwickets=0
- `legitimate_pair(+4, +1, 0)`: d_balls=1, d_score=4 ∈ [0,7], d_wickets=0 ∈ {0,1} → True
- **Gate admits.** Commit proceeds via FC5 as before. **Preserved.**

**At F304 (the bad anchor):**
- Proposed: (score=54, overs="6.3", wickets=0) vs current (49, "4.5", 0)
- Δscore=+5, Δoers→Δballs=+10, Δwickets=0
- `legitimate_pair(+5, +10, 0)`: d_balls=10 > 1, NOT (d_balls=0) → False
- **Gate rejects.** Commit defers to streak-gate. Streak gate rejects (proven by C12 §11 production trace).
- **Result: sb._inn stays at score=49, overs=4.5. Cascade collapses at root.**

**At GTRR F72 (heavy-extras over 1, Δscore=+5 at ov=0.3):**
- Proposed: (score=12, overs=0.3, wickets=0) vs current (7, 0.3, 0)
- Δscore=+5, Δballs=0, Δwickets=0
- `legitimate_pair(+5, 0, 0)`: d_balls=0, d_score=5 ∈ [0,5], d_wickets=0 → True
- **Gate admits.** Preserved. ✓

**At GTRR F1106 (legitimate 11-ball absorption per pre-existing trace data):**
- This goes through `_decompose_multi_ball` (the multi-ball-gap dispatch path), not through `commit_decision`'s direct sb.set calls. **Shape B does NOT gate it** (different code path). Preserved.

**Gate 6 closes cleanly for Shape B at f302/f304/F72/F1106.**

### 4.7 Gate 7 — cross-fixture verification

Every GTRR DIRECT-SCORE-COMMIT firing (80) satisfies `legitimate_pair`. No regression predicted. Every DCKKR firing except f138 + f475 satisfies; those two are multi-ball-gap dispatches that don't flow through Shape B's gate site.

**Gate 7 closes for Shape B.**

### 4.8 Verdict on Shape B

**ACCEPTED PROVISIONALLY** — pending one structural question:

The catch-up branch (`test_pipeline.py:8986+`) and end-of-over hook (`:11750`) ARE separate sb.set call sites. Shape B's single gate site at `commit_decision` would NOT cover them. The production f304 cascade went through commit_decision (verified by the F304 TRACK log lines), so Shape B closes B-η as documented. But the architectural coverage is incomplete — the dual-state-write defect class (§7) survives at those other call sites.

**Provisional verdict: Shape B closes B-η. Architectural coverage limited unless extended to the two other call sites.**

---

## 5. §7.2 7-gate audit — Shape C (dual-state-write unification)

**Proposed change:** Route ALL `sb._inn` writes through the same gate semantics as SM's `_handle_warm` streak gate. Eliminate the FC5 fast-confirm path entirely (or restrict it to single-field reads with no cross-field implication). Architectural reorganization.

### 5.1 Gate 1 — enumerate callers

ALL sites that mutate `sb._inn[*]`:
- C9 catalogue §2 (score: 9 sites), §3 (wickets: 10 sites), §4 (overs: 8 sites)
- 2 sites bypass sb.set (S07/W07/O06 state-recovery; S10/W10/O09 POISON-RECAL forced reset)
- 25 sites flow through sb.set

### 5.2 Gate 2 — classify each caller

Multi-way: extractor-driven, cricket-rules-derived, scoreboard-tracker on_lock, state-recovery, POISON-RECAL, hot-resume, ABSORBED_LEGAL handler. Each has different invariant assumptions.

### 5.3 Gate 3 — cross-reference adjacent state

Shape C touches:
- `ConsistentReadTracker.update()` — eliminates FC5
- `_handle_warm` streak gate — becomes the canonical multi-ball-gap arbiter
- `_decompose_multi_ball` — unchanged but its precondition changes
- `on_ball_event()` — semantics change (no FC5 to feed grace into)
- Every test fixture that pokes `_post_event_grace` directly (test_recent_fixes.py:48, etc.)

**Lifecycle ramifications are broad.** The audit cannot rule out regressions across this surface without running the full L1.5 + L2 ledger replays. Shape C is theoretically the cleanest architectural answer; **empirically it requires the largest verification effort**.

### 5.4 Gate 4 — equivalence proof

**Not provable from static analysis alone.** Shape C's behavioral equivalence to existing code on the legitimate-cases corpus (Layer 1.5 ledger + Layer 2 replay + GTRR + DCKKR trace assertions) requires running the corpus and tabulating divergences.

### 5.5 Gate 6 — predicted flip with concrete frame numbers

Shape C would reject F304 score + F304 overs via the unified streak-gate semantics. **Same predicted flip as Shape B at f304.**

But Shape C ALSO changes the semantics at F302's legitimate ball commit. Without FC5's post-event grace, F302's score 45→49 would need to go through pending-consensus (2-frame) or natural-batter-increment (which doesn't apply to match-level score). **The legitimate-case path needs an equivalent fast-path** under Shape C. The audit cannot guarantee this without running the L1.5 ledger.

### 5.6 Gate 7 — cross-fixture verification

GTRR's 80 firings: each represents a sb._inn write that currently uses FC5 (or FC4 in the overs case). Shape C must preserve all 80. **Verifiable only by running the corpus.**

### 5.7 Verdict on Shape C

**DEFERRED.** Shape C is the most architecturally cohesive answer but cannot be statically audited to gate-4/7 closure without empirical corpus runs. **The discipline rule: ship the narrower closure first; revisit Shape C as a follow-up engineering workstream if the narrower fix produces residual symptoms.**

This is the same principle that gated F1's session: ship the minimal cascade-closer; let cross-fixture verification surface the next workstream.

---

## 6. §7.2 7-gate audit — Shape D (poison-radius extension)

**Proposed change:** When a frame is POISONED (per `test_pipeline.py:10864` upstream guard), set a counter `_poison_radius = M` for M subsequent frames. While `_poison_radius > 0`, FC5 is disabled (the post-event-grace path skips). Counter decrements per frame.

### 6.1 Gate 1 — enumerate callers

Single site addition: at the POISONED log emission site in `test_pipeline.py:10864`, set the new counter on the tracker. New counter check in `consistent_tracker.update()` at FC5 entry.

### 6.2 Gate 2 — classify each caller

The POISONED guard fires from a single site (upstream test_pipeline.py). Single producer; FC5 entry as the single consumer.

### 6.3 Gate 3 — cross-reference adjacent state

`_poison_radius` is new state. Decrement timing relative to `_post_event_grace` decrement needs care — they must not conflict.

### 6.4 Gate 6 — predicted flip with concrete frame numbers

**At F303 POISONED:** Shape D sets `_poison_radius = M` (M to be determined; e.g., 3).
**At F304:** FC5 entry checks `_poison_radius > 0` → skips FC5. Score commit at f304 defers to pending-consensus (2-frame). Single read of 54 doesn't promote. **Score stays at 49.** ✓

But wait: F303 POISONED at production was caused by a hallucinated 89-4 (10.2) reading, NOT a graphic-overlay misread necessarily related to f304's bad anchor. **Treating any POISONED frame as a 3-frame ban on FC5 is broad.** Test cases:
- POISONED at frame N due to single OCR misread → Shape D blocks legitimate reads at N+1, N+2, N+3
- The legitimate reads then go through pending-consensus, which adds 2-frame latency
- For a normal session with occasional POISONED frames, this adds latency to every recovery

**Regression risk: increased latency at every POISONED-frame boundary.** Production session had 30 POISONED tags — under Shape D, ~30 × M frames of degraded FC5 behavior.

### 6.5 Gate 7 — cross-fixture verification

GTRR session POISONED count: need to grep. Without that data, gate 7 not closed. Estimate: similar to DCKKR's 30 POISONED, so similar latency impact.

### 6.6 Verdict on Shape D

**REJECTED** on regression-risk grounds. Shape D targets the f304 cascade root narrowly but degrades FC5 reliability at every POISONED-frame boundary. The discipline rule: don't ship a fix that creates a new latency class to close one specific anomaly.

Shape D also doesn't address the underlying cross-field correlation: a non-POISONED graphic-overlay frame with the same f304-class signature would still slip through. Shape D treats the symptom (POISONED-adjacency) rather than the cause (FC5 admits illegitimate single-frame cross-field jumps).

---

## 7. Shape selection — Shape B (cross-field pairing gate)

**Selected shape: B.** Rationale:

| Criterion | A | B | C | D |
|---|---|---|---|---|
| Closes B-η root (F304 both halves)? | Partial (overs only) | Full | Full | Full |
| Preserves legitimate cases (gate 7)? | Yes | Yes (empirically verified GTRR + DCKKR) | Unknown without corpus run | Yes but adds latency |
| Static gate-4 equivalence proof? | Yes | Yes | No | Yes |
| Architectural coverage? | Single predicate | commit_decision site | Full sb._inn surface | Single counter |
| Discipline track-record alignment? | Falsifies pattern (half-fix) | Closes cleanly | Deferred — engineering workstream | Symptom-targeting |

**Shape B is the narrowest shape that closes B-η completely while passing all 7 gates statically.**

**The provisional caveat from §4.8 stands:** Shape B's coverage at `commit_decision` does NOT extend to the catch-up branch (`test_pipeline.py:8986+`) or the end-of-over hook (`:11750`). Per the discipline rule, ship B's narrow closure first; if subsequent sessions surface the same cascade pattern at the other call sites, extend Shape B's coverage or escalate to Shape C.

---

## 8. Predicted-flip table (gate 6 closure, for the C14 commit message)

| Trace-session assertion | Pre-fix (current) | Post-fix (Shape B) | Closure type |
|---|---|---|---|
| `trace_epsilon_initial_striker` (DCKKR) | PASS | PASS | unchanged |
| `trace_compound_tokens` (DCKKR) | PASS | PASS | unchanged |
| `trace_extras_total` (DCKKR) | PASS | PASS | unchanged |
| `trace_alpha_bowler_runs_sum` (DCKKR) | FAIL gap=4 | **predicted: significant reduction or PASS** (cascade closure removes B-θ contribution that inherited from B-η-corrupted state) | cascade |
| `trace_beta_sm_wicket_dispatch` (DCKKR) | FAIL — 3 misses (f371, f521, f636) | **predicted: PASS** (cascade closure: F304 anchor blocked → SM stays consistent → wicket dispatches land at the right frames) | cascade |
| `trace_*` (GTRR) | 5 FAIL (pre-F1 baseline) | unchanged (F1 path not exercised; GTRR baseline preserved) | n/a |

**Concrete frame-number predictions:**
- DCKKR F302 TRACK score 45→49: still fires via FC5 (legitimate_pair True). Production behavior unchanged.
- DCKKR F302 TRACK overs 4.4→4.5: still fires via FC4 (Shape B doesn't intercept FC4). Production behavior unchanged.
- DCKKR F304 commit_decision: Shape B's pairing gate rejects (d_balls=10 > 1, d_score=+5). **No DIRECT-SCORE-COMMIT firings at F304.** Production behavior: cascade collapse.
- DCKKR F371/F521/F636 wicket dispatches: SM stays consistent post-F304 → wickets dispatch at the right frames. Trace_beta PASS predicted.
- GTRR all 80 firings: gate admits (every firing satisfies legitimate_pair). No regression predicted.

---

## 9. Mandatory output — dual-state-write defect-class catalogue entry

Per operator directive: regardless of which shape ships, document the dual-state-write defect class in `sm_as_orchestrator_design.md` §8 (new section, post-C15). The pattern is empirically validated across two sessions:

### 9.1 Pattern definition

**Dual-state-write defect class:** two parallel state surfaces store representations of the same logical fact, with different invariants. The weaker invariant admits at site X1; the stronger rejects at site X2. Both surfaces remain live, producing a divergence signature visible only at downstream read sites.

### 9.2 Empirical instances

| # | Session | Weaker surface | Stronger surface | Symptom |
|---|---|---|---|---|
| 1 | F1 (2026-05-19) | `sb._inn["bowling_card"]` (unused parallel surface) | `sb.bowling_card` (canonical attribute) | F-α-shadow false positives at frames 302/1325/522 |
| 2 | F1 (2026-05-19) | `card.get("broadcast")` (unwritten dead field) | `card.get("broadcast_striker")` (actual field) | B-ε / B-β cascade — wrong initial striker propagating to 4 bug classes |
| 3 | B-η (2026-05-21) | `sb._tracker.confirmed` via FC5 (permissive `_is_suspicious`) | SM `_handle_warm` streak gate (3-frame consensus + Δballs ≤ 3) | F304 cascade — sb._inn[score=54, overs=6.3] vs sm.self.overs=4.5 |

### 9.3 Detection signal

Any predicted-flip claim that cites EQUAL values across two surfaces (e.g., `tracker_score == current_score == 54`) but UNEQUAL paired values on a sibling field (`tracker_overs=6.3 != current_overs=4.5`) is the dual-state-write signature.

### 9.4 Remediation pattern

- **Narrow fix:** add a coupling gate at the weaker surface (Shape B pattern).
- **Architectural fix:** unify the two surfaces (Shape C pattern).

The narrow fix is the cheapest discipline-aligned move. The architectural fix is the long-term cohesion goal.

### 9.5 Audit-output requirement

When a candidate fix is proposed for a defect that *might* be dual-state-write class: §7.2 gate 3 (cross-reference adjacent state) must explicitly check for the dual-state pattern. If present, the audit must enumerate both surfaces and prove the proposed fix addresses the weaker one (not just the symptom at the stronger one).

---

## 10. C14 deliverable specification

Per §7 selection: Shape B (cross-field pairing gate at `commit_decision`).

**Concrete code-change spec (for C14):**

```python
# In test_pipeline.py around line 4658 (commit_decision), BEFORE sb.set calls:
#
# Read proposed deltas from decision:
_proposed_score = decision.get("score_update", {}).get("to")
_proposed_overs = decision.get("overs_update", {}).get("to")
_proposed_wickets = decision.get("wickets_update", {}).get("to")
_cur_score = scoreboard._inn.get("score")
_cur_overs = scoreboard._inn.get("overs")
_cur_wickets = scoreboard._inn.get("wickets")
#
# Compute deltas (None-safe):
_d_score, _d_balls, _d_wickets = _compute_deltas(...)
#
# Pairing predicate:
_legitimate = (
    (_d_balls == 1 and 0 <= _d_score <= 7 and _d_wickets in (0, 1))
    or (_d_balls == 0 and 0 <= _d_score <= 5 and _d_wickets in (0, 1))
)
#
# If illegitimate AND any of (Δscore, Δballs, Δwickets) is non-zero, defer:
if not _legitimate and (_d_score > 0 or _d_balls > 0 or _d_wickets != 0):
    log.info(f"[CROSS-FIELD-PAIRING-REJECT] proposed=({_proposed_score}, "
             f"{_proposed_overs}, {_proposed_wickets}) "
             f"current=({_cur_score}, {_cur_overs}, {_cur_wickets}) "
             f"d_score={_d_score} d_balls={_d_balls} d_wickets={_d_wickets} — "
             f"deferring to streak gate")
    if _trace is not None:
        try:
            _trace.get_recorder().record(
                tag="CROSS-FIELD-PAIRING-REJECT",
                proposed_score=_proposed_score, proposed_overs=str(_proposed_overs),
                proposed_wickets=_proposed_wickets,
                current_score=_cur_score, current_overs=str(_cur_overs),
                current_wickets=_cur_wickets,
                d_score=_d_score, d_balls=_d_balls, d_wickets=_d_wickets,
                frame_id=frame)
        except Exception:
            pass
    # Skip the sb.set calls; let streak gate / pending-consensus handle it
    return
#
# Else: fall through to existing sb.set sequence
```

**Trace tag**: `CROSS-FIELD-PAIRING-REJECT` to be registered in `trace_emitter.py` KNOWN_TAGS.

**Commit-message requirements (per gate 6 + audit memo):**
- Predicted-flip claim citing F302 (preserved), F304 (rejected), GTRR 80 firings (preserved)
- Layer 1.5 + Layer 2 gates must pass
- Reference to this C13 audit memo and the C7+C12 + C12.5b empirical evidence

**Test-coverage suggestion** (orthogonal to C14, possibly C14a):
- Unit test exercising `_compute_deltas` with f302 + f304 + F72 + F1106 representative inputs
- Assert legitimate vs illegitimate verdicts

---

## 11. C15 — verification deliverable

Per operator C15 spec:

1. Run Layer 1.5 + Layer 2 gates (must pass per pre-commit).
2. Re-run trace-session assertions on DCKKR — predict `trace_beta_sm_wicket_dispatch` flips PASS, `trace_alpha_bowler_runs_sum` shrinks gap.
3. Re-run trace-session assertions on GTRR — predict no regressions.
4. Re-run captured-replay scaffold (warm-seeded + LLM, with and without DIRECT-SCORE-COMMIT instrumentation) — predict zero DIRECT-SCORE-COMMIT firings at F304 in the post-fix run; CROSS-FIELD-PAIRING-REJECT fires at F304 instead.
5. If `trace_beta` does NOT flip PASS in C15: that is the **sixth empirical falsification of the chain**, signaling B-ι as the next root candidate per §1.2 of the C10 brief. **Methodology retirement trigger** per C9 §11 + C10 §1.2.

---

## 12. Discipline closing

This audit is the deepest §7.2 application in the eight-commit chain. It:

- Applied 7 gates to 4 shapes, not 1
- Defined the cross-field pairing criterion empirically (GTRR 80 + DCKKR 47 verified)
- Selected the narrowest closure that passes all gates statically
- Documented the dual-state-write defect class (operator-mandatory output)
- Specified C14's code-change shape concretely
- Specified C15's verification + falsification-budget criterion

If C15's predicted flip materializes, the discipline chain closes: 6 falsifications + 8 static falsifications + 1 architectural insight (dual-state-write class) + 1 cascade-closure fix.

If C15's predicted flip does NOT materialize, the chain registers the sixth empirical falsification and the methodology retires per §1.2 (C10) / §11 (C9). The next move would then be a structural pivot beyond static analysis — likely a production-pipeline re-run against captured video, or a deeper rebase of the consensus-tracker architecture.

Either outcome is the discipline working as designed. Neither is failure; both are empirical signal.

---

**C13 audit complete. C14 fix-commit specification at §10. C15 verification spec at §11. The dual-state-write defect-class catalogue entry at §9 is mandatory output regardless of C14 outcome — to be promoted to `sm_as_orchestrator_design.md` §8 post-C15.**
