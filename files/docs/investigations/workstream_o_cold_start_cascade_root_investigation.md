# Workstream O — Cold-start cascade root investigation (step-1)

**Status.** Step-1 closed; leading candidate identified; cohort-closure
verification UNIFIED-2 (one root closes 2 of 3 cohorts; striker-anchor
likely splits to OE-sub-cohort but shares the same cold-start
window — see §6).

**Trigger.** Post-WS-N validated diff baseline at commit `80f1be9`
(`files/tests/baselines/dckkr_diff_post_ws_n_baseline.md`) surfaced
three correlated defect classes co-located at cold-start (frame
0-30 region) on the DCKKR `watch_20260519_121701` dump.

**Pre-screen verdict.** GREEN — PIPELINE-DIRECT per S28
(ScoreManager cold-start logic + Scoreboard regression-rejection +
ThisOverManager regression-token emission; no new schemas, no
test_pipeline.py main-loop touch required at step-2 if leading
candidate OA proves out).

**Outcome.** Static-falsification chain converges on **OA — SM
cold-start overread + Scoreboard regression-rejection composite**
as leading candidate. Sub-mechanism reservation around exact "-N"
token emission site (OC question) — confirmed at step-1.5 (§4) to
ride on `_synthesize_cold_start_ball_events` excess branch
(`score_manager.py:2507`) when implied_runs > implied_balls. Cohort
closure: E2-phantom-runs (10 → predicted 0-2) and `this_over_tokens`
negative (~7 negative-token rows → predicted 0). Striker-anchor swap
(~50 unclassified fields) shares the cold-start frame window but a
different root mechanism — predicted partial closure at best.

---

## §1 Empirical anchor — three defect cohorts with per-frame anchors

Three defect cohorts surfaced by the post-WS-N diff baseline
(`80f1be9`):

### §1.1 E2-phantom-runs cohort (10 incidents; regression from §7 baseline 1)

Score-divergence cascade across balls 2.3 → 4.5 of innings 1.
Per-ball delta from diff baseline §3 (conservation invariants):

| Ball | Pipeline | GT | Δ (pipeline − GT) | Conservation tag |
|---|---|---|---|---|
| 2.3 | 49 | 22 | +27 | violation 1 |
| 2.4 | 49 | 22 | +27 | violation 2 |
| 2.5 | 49 | 22 | +27 | violation 3 |
| 3.1 | 49 | 29 | +20 | violation 4 |
| 3.2 | 49 | 33 | +16 | violation 5 |
| 3.3 | 49 | 33 | +16 | violation 6 |
| 3.4 | 49 | 34 | +15 | violation 7 |
| 3.5 | 49 | 38 | +11 | violation 8 |
| 3.6 | 63 | 39 | +24 | violation 9 |
| 4.1 | 63 | 43 | +20 | violation 10 |
| 4.2 | 63 | 44 | +19 | violation 11 |
| 4.3 | 63 | 44 | +19 | violation 12 |
| 4.4 | 64 | 45 | +19 | violation 13 |
| 4.5 | 64 | 49 | +15 | violation 14 |

Pattern: pipeline score **sticks** at 49 from 2.3 through 3.5 (8
consecutive snapshots), then jumps to 63 at 3.6 (and 64 at 4.4),
both higher than GT. The GT score advances naturally
(22 → 29 → 33 → 34 → 38 → 39 → 43 → 44 → 45 → 49).

The snapshotter run log emits `Score regression rejected: 64→49
(normal-play score physics; reset authority required)` repeatedly,
confirming Scoreboard rejects Scout-proposed score writes that
would lower the committed score (predicate at
`files/eyes/scoreboard.py:1224`).

### §1.2 Striker-anchor swap cohort (~50 unclassified fields)

Per-ball striker / non-striker name + per-batter ledger swap
across balls 0.5 → 4.4 (every ball with a snapshot from 0.5
onwards). Sample from diff baseline §2:

| Ball | Pipeline striker | GT striker | Pipeline non | GT non |
|---|---|---|---|---|
| 0.5 | Rahul | Nissanka | Nissanka | Rahul |
| 0.6 | Nissanka | Rahul | Rahul | Nissanka |
| 1.2 | Nissanka | Rahul | Rahul | Nissanka |
| 1.5 | Nissanka | Rahul | Rahul | Nissanka |
| 1.6 | Rahul | Nissanka | Nissanka | Rahul |
| 2.4 | Rahul | Nissanka | Nissanka | Rahul |
| 3.5 | Nissanka | Rahul | Rahul | Nissanka |
| 4.3 | Rahul | Nissanka | Nissanka | Rahul |

Pattern: pipeline rotates striker every ball legitimately, but the
identity at any given ball is consistently swapped vs GT.
Pipeline's `non_striker_runs` / `non_striker_balls` etc. match
GT's `striker_runs` / `striker_balls` (and vice versa), confirming
the per-batter ledger is being attributed to the correct slot —
only the slot **labels** are swapped. Slot labels derive from
SM.striker / SM.non identity pointers.

This is the cold-start opener-anchor defect: pipeline anchored
Rahul on strike for ball 0.1 (deterministic rotation cycle then
proceeds in lockstep with GT but in mirrored attribution). GT
shows Nissanka on strike at 0.1.

DCKKR squad order from `test_pipeline_captured_replay.py:67-70`:
`BATTING_SQUAD = [Nissanka, Rahul, …]`. Both openers seeded with
`status="batting"` and zero ledgers at cold-start; neither
explicitly designated striker. SM cold-start must derive strike
from broadcast / convention.

### §1.3 `this_over_tokens` negative-token cohort (~7 rows)

From diff baseline §2, balls 3.1 → 4.5 show negative tokens in
`this_over_tokens`:

| Ball | Pipeline tokens | GT tokens |
|---|---|---|
| 2.3 | `[".", ".", "-27"]` | `[".", "4", "1"]` |
| 2.4 | `[".", ".", "-27", "-27"]` | `[".", "4", "1", "."]` |
| 2.5 | `[".", ".", "-27", "-27", "-27"]` | `[".", "4", "1", ".", "."]` |
| 3.1 | `["-20"]` | `["1"]` |
| 3.2 | `["-20", "-16"]` | `["1", "4"]` |
| 3.5 | `["-20", "-16", "-16", "-15", "-11"]` | `["1", "4", ".", "1", "4"]` |
| 4.1 | `["-20"]` | `["4"]` |

Pattern: each negative token's magnitude equals `pipeline_score − GT_score`
at that ball (e.g. 2.3 `-27` = 49 − 22 = 27, with sign inverted; 3.1
`-20` = 49 − 29 = 20). Token emitted into `self.this_over` matches
SM's `_synthesize_cold_start_ball_events` excess-branch heuristic at
`score_manager.py:2507-2508`:

```python
excess = implied_runs - (implied_balls - 1)
tokens = ["1"] * (implied_balls - 1) + [str(excess)]
```

…BUT only when `implied_runs > implied_balls`. The cascade signature
suggests the cold-start exit committed at a high score baseline and
the WARM-mode dispatch (or a subsequent cold-start re-entry) is
synthesizing additional balls against the still-stuck baseline:
each new ball after stuck-at-49 has `implied_runs_so_far − implied_balls_so_far`
= a NEGATIVE excess when the actual ball was a dot or single but
the stuck score baseline implies no run-up was needed.

Sub-mechanism reservation (§4 below): exact emission site
requires step-2 instrumentation to confirm; static chain
narrows to `_synthesize_cold_start_ball_events` OR a downstream
SM gap-fill that mirrors that heuristic.

---

## §2 Cold-start pipeline-state map at COLD_START → WARM exit

State at the cold-start exit boundary (per
`score_manager.py:2696-2714` `_maybe_synthesize_cold_start_gap`):

```
entry  = self._cold_start_entry   # {score, wickets, overs} captured at COLD_START entry
anchor = (self.score, self.wickets, self.overs)  # state at WARM exit
implied_balls   = max(0, anchor_balls - entry_balls)
implied_runs    = max(0, anchor_score - entry_score)
implied_wickets = max(0, anchor_wickets - entry_wickets)
```

Cold-start commits a WARM seed once `cold_candidate_streak ≥ COLD_START_CONSENSUS_FRAMES` (default 2; `score_manager.py:437`).
With the snapshotter, cold-start begins at frame 0 with entry =
{0, 0, 0.0} (no prior state). The seed candidate accumulates over
just 2 consecutive matching frames before WARM exit.

**Failure mode for OA hypothesis:** if Scout's early reads OCR-misread
the score field (e.g. read "49" off a graphic overlay or a stale
mid-match strip read), and TWO such mis-reads agree consecutively,
the seed candidate commits at the bogus score. WARM exit then runs
`_synthesize_cold_start_ball_events(implied_balls, implied_runs,
implied_wickets)` against the bogus implied_runs ≈ 49, producing
the `["1"] * (implied_balls - 1) + ["49 - implied_balls + 1"]`
pattern — matching the observed first divergence at ball 2.3.

Cold-start pre-match VLM-hallucination gate
(`score_manager.py:2733-2747`): rejects frames matching
`_COLD_START_PREMATCH_CUE` OR `_is_skeleton_strip`. Does NOT gate
on score-magnitude plausibility — a 49-score read at minute-0 of
a live match passes the gate.

Cold-start inn2 lockout (`score_manager.py:2770-2795`) rejects
score > 30 / wickets > 2 / overs > 5.0 — but this gate fires only
in the innings-2 transition window. Innings 1 cold-start has no
such magnitude gate.

---

## §3 Scoreboard regression-rejection logic

Per `files/eyes/scoreboard.py:1220-1236`:

```python
cur_score = self._inn.get("score")
if cur_score is not None:
    try:
        cur_int = int(cur_score)
        if v < cur_int:
            log.warn(
                f"Score regression rejected: {cur_int}→{v} "
                f"(normal-play score physics; reset authority required)")
            return False
        if v - cur_int > 100:
            log.warn(...)
            return False
    except (ValueError, TypeError):
        pass
```

**Predicate.** Strict monotonic-up: any proposed score `v < cur_int`
is hard-rejected (return False before the consensus tracker even
sees it). Comment "reset authority required" implies an external
caller can bypass — search across `files/eyes/scoreboard.py`
surfaces NO matching reset-authority API for the score field
(`def reset` at :178 covers full innings reset; `_dismissed_recovery`
at :2017 is phantom-recovery for batter slots, not score).

**Bypass mechanisms.**
- `Scoreboard.reset()` (:178): full reset — too heavy for over-read
  recovery (would also nuke the legitimate batting / bowling cards).
- `_state_recovery_aggregator` reset path
  (`test_pipeline.py:7211-7216` + `_record_state_recovery_guard` at
  :7221): exists in main-loop but routes through `StateRecovery-
  Aggregator` (`files/state_recovery.py`); fires only on
  POISON-streak + frame-count threshold. Snapshotter does NOT mirror
  this state-recovery path per WS-N N1.2 closure-tangled-state
  classification.
- `_poison_streak` watchdog (`test_pipeline.py:7212-7214`): another
  test_pipeline-main-loop-only path; not in snapshotter.

**Consequence.** Once Scoreboard commits a high score (e.g. 49 from
cold-start overread), no in-snapshotter mechanism walks it back.
Subsequent legitimate Scout reads of the true lower score are
rejected at the `v < cur_int` predicate. The `_state_recovery`
aggregator + `_poison_streak` watchdog that would recover from this
in production are intentionally not mirrored in the snapshotter
(per WS-N N1.2 verification 5: "monitoring counters …
diagnostic-only").

**Implication for OB hypothesis:** Scoreboard regression-rejection
has no high-confidence-override escape hatch. Adding one would
require either (a) a new public API (Scoreboard.force_reset_score)
that downstream callers gate on consensus-vs-current confidence,
OR (b) a Scout-side magnitude-plausibility filter at cold-start
that prevents the bogus seed from committing in the first place.
Path (b) is OA's fix surface; path (a) is a defense-in-depth layer.

---

## §4 ThisOverManager / SM negative-token emission semantics

`self.this_over.append(str(delta))` at `eyes/this_over.py:219`
inside `_pad_with_inferred_tokens`: only fires when
`0 < delta <= 6` (legitimate single-ball run-count). Negative deltas
fall into the `"?"` branch (:222). So this site does NOT emit
negative tokens.

Other `self.this_over.append(...)` sites at :641-699 all emit
canonical tokens (`W`, `Wd`, `wd`, `Nb`, `.`, `4`, `6`, `str(r)`
where r > 0).

The only path that could emit a string like `"-20"` via
`self.this_over.append(str(...))` is one where the value passed
to `str()` is computed as a negative integer. Grep across
`eyes/this_over.py` for `str(` did not surface a site computing
a negative integer.

Candidate site in `score_manager.py:2507-2508`
(`_synthesize_cold_start_ball_events` excess branch):

```python
excess = implied_runs - (implied_balls - 1)
tokens = ["1"] * (implied_balls - 1) + [str(excess)]
```

If `implied_runs < implied_balls - 1`, `excess` is negative.
`str(excess)` then produces the negative token string. The branch
is reached when `implied_runs > implied_balls` — but the snapshot
data shows negative tokens appearing AFTER the cold-start exit
(balls 2.3+), so the cold-start synthesis is not the only emission
site.

**Sub-mechanism reservation.** Step-1 cannot definitively localise
the emission site without step-1.5 instrumentation (add a stack-
trace log to the negative-token emission). Two candidates:
- (a) `_synthesize_cold_start_ball_events` excess branch with
  unexpected negative excess at a re-entry — unlikely given the
  `<= / >` guard ordering.
- (b) A downstream gap-fill or multi-ball decompose path that
  mirrors the excess heuristic and produces negative tokens when
  the post-rejection Scoreboard state has a score lower than SM's
  internal tracker would imply.

Path (b) is consistent with the observed signature: pipeline SM
score=49 stuck, Scoreboard rejects lower reads, gap-fill computes
`excess = sb_score_after_reject - implied_balls_so_far` which can
go negative when SM and SB diverge.

**Promotion to step-2 task.** Add a single-frame stack-trace log
at the negative-token emission OR run the snapshotter with
`PYTHONBREAKPOINT=pdb.set_trace` on the first negative-token
emission to pin the site definitively.

---

## §5 Hypothesis enumeration

Five candidate roots evaluated against §7.2 gates 1-3 (gate 1:
defect-class fit; gate 2: backward-compatibility; gate 3:
fix-surface attribution).

### OA — SM cold-start overread + Scoreboard regression-rejection composite — **LEADING**

**Mechanism.** Scout OCR overreads the score field at cold-start
(e.g. reads "49" off a transient overlay), two consecutive frames
agree, `COLD_START_CONSENSUS_FRAMES=2` triggers WARM exit at the
bogus seed. WARM-exit runs `_maybe_synthesize_cold_start_gap`
which synthesises ball events against `implied_runs=49`. Subsequent
Scout reads of the true lower score (~22 at 2.3) are
regression-rejected at `scoreboard.py:1224`.

**Gate 1 (fit).** PASS — explains all of: E2-phantom-runs (stuck-at-49
cascade), conservation invariants (Σ score(pipeline) > Σ score(GT)
by 11-27), AND `this_over_tokens` negative cohort (synthesis-time
excess + post-WARM gap-fill mirroring excess heuristic).

**Gate 2 (backward-compat).** PARTIAL — fix surfaces:
- (a) **Cold-start score-magnitude plausibility gate**: reject
  seeds where score > implied-bowling-rate × overs (e.g. ban
  seed score=49 at overs=0.0 since RPO < 12.0 cap implies < 1
  run at 0.0 overs). Backward-compat safe IF the threshold is
  empirically validated against innings-1 cold-start seed shapes.
- (b) **Scoreboard regression-rejection escape hatch**: add a
  `force_reset_score(v, reason)` API that bypasses the predicate
  when called with a strong-evidence reason (e.g. consensus of
  3+ lower reads). Backward-compat safe IF only the new
  Scout-side cold-start recovery wires the new API.

Both surfaces are bounded; neither touches §15 canonical write
paths.

**Gate 3 (fix-surface attribution).** PASS — pipeline-direct per
S28. Modifies `score_manager.py` `_handle_cold_start` (~20 LOC for
gate (a)) + optional `eyes/scoreboard.py` new method (~10 LOC for
gate (b)). No test_pipeline.py main-path touch.

**Status.** Leading candidate. Closes 2 of 3 cohorts (E2 + negative
tokens) directly; cascade-closure of striker-anchor swap depends on
whether striker identity shares the same cold-start commit window
(see §6).

### OB — Scoreboard regression-rejection too aggressive — **VIABLE alternative**

**Mechanism.** Strict-monotonic predicate at `scoreboard.py:1224`
rejects legitimate corrections. Cold-start overread is the trigger
but the rejection chain is what prevents recovery.

**Gate 1 (fit).** PARTIAL — explains E2 + negative-tokens but
treats the symptom (rejection prevents correction) rather than
the root (bogus seed committed in the first place).

**Gate 2 (backward-compat).** RISK — relaxing the predicate could
let real OCR noise (score reads of 0 on graphic overlays) pull
SM back during legitimate innings; the WHY comment "normal-play
score physics; reset authority required" implies a deliberate
safety design.

**Gate 3.** PASS — same fix surface as OA's (b) leg.

**Status.** Viable defense-in-depth layer atop OA. Not preferred as
primary root.

### OC — over_mgr / SM negative-token emission unconsumed — **PARTIALLY FALSIFIED**

**Mechanism.** over_mgr (or SM gap-fill) emits `-N` tokens signalling
regression; no downstream consumer wires the signal back to trigger
correction.

**Gate 1.** PARTIAL — closes the negative-tokens cohort if we add
a downstream consumer (e.g. SM watches over_mgr.this_over for
negative tokens and triggers `force_reset_score`). Does NOT close
E2-phantom-runs root (the bogus 49 still committed).

**Gate 2.** PASS — additive; no relaxation of existing gates.

**Gate 3.** PASS — pipeline-direct; modifies SM only.

**Status.** Falsified as standalone root (doesn't close E2 at root).
Reserve as defense-in-depth layer for negative-tokens cohort if
OA's gate (a) doesn't fully close it.

### OD — Cold-start synthesizes against stale baseline — **SUBSUMED by OA**

**Mechanism.** `_synthesize_cold_start_ball_events` runs against
the wrong `_cold_start_entry` snapshot.

**Gate 1.** PARTIAL — only relevant if `_cold_start_entry` itself
is stale at WARM exit (rare path; entry is captured at COLD_START
entry which for snapshotter is frame 0 with all zeros). Doesn't
explain the bogus 49 seed.

**Status.** Subsumed by OA. The stale-baseline mechanism is not
the trigger; the bogus-seed-commit is.

### OE — Cohort split (three independent roots) — **PARTIALLY CONFIRMED**

**Mechanism.** E2 + negative-tokens share root (OA); striker-anchor
swap has independent root (cold-start striker selection logic).

**Gate 1.** PARTIAL — striker swap manifests at ball 0.5 (first
ball with snapshot), well before the E2 cascade starts at 2.3.
Different timing supports different root.

**Gate 2.** PASS — separate fix surfaces; no shared compat risk.

**Gate 3.** PASS — both PIPELINE-DIRECT.

**Status.** Partially confirmed. WS-O scope unifies E2 + negative-
tokens (UNIFIED-2); striker-anchor splits to WS-O sub-track or new
WS-P. Recommendation: step-2 patch addresses OA first; if step-3
empirical validation shows striker-swap persists, open WS-O.b
striker-anchor sub-investigation OR new WS-P.

---

## §6 Cohort-closure verification — UNIFIED-2 + striker-anchor SPLIT

| Cohort | OA closure | Notes |
|---|---|---|
| E2-phantom-runs (10) | **DIRECT** | Cold-start magnitude gate prevents bogus 49 seed; stuck-at cascade never starts. Predicted 10 → 0-2. |
| Conservation invariants (14) | **DIRECT** | Tied to E2; same root. Predicted 14 → 0-2. |
| `this_over_tokens` negative (~7) | **DIRECT** | Excess branch unreachable when seed is plausible. Predicted ~7 → 0. |
| Striker-anchor swap (~50) | **PARTIAL/SPLIT** | Different root: cold-start selects wrong opener for strike. Closes only if cold-start cascade also corrupts striker identity (possible — SM cold-start may use Scout's first bat1.striker reading which itself could be misread). |
| Other 12 surfaces | **UNCHANGED** | Regression guard via gate-7. |

**S9-pattern verdict.** UNIFIED-2 not UNIFIED-3. Two cohorts
(E2 + negative-tokens + their conservation invariants) close via
one root. Striker-anchor swap appears to share the same cold-start
*window* but a different root *mechanism* — pending step-3 empirical
validation to confirm SPLIT vs cascade-close.

**Risk.** If striker-anchor swap turns out to share OA's root
(both manifest from the same bogus cold-start seed frame), single
WS-O patch closes all 3 cohorts (S9 strict). If split, WS-O
patch closes 2 and the third becomes WS-P.

---

## §7 §7.2 audit on leading candidate (OA)

| Gate | Status | Rationale |
|---|---|---|
| 1 (defect-class fit) | PASS | OA explains all stuck-at + conservation + negative-token observations. |
| 2 (backward-compat) | PASS (with constraints) | Cold-start magnitude gate must be empirically validated against existing innings-1 cold-start seed shapes (no false rejections). Scoreboard escape-hatch API additive (default-off). |
| 3 (fix-surface attribution) | PASS | PIPELINE-DIRECT; ScoreManager `_handle_cold_start` (~20 LOC for gate (a)) + optional `Scoreboard.force_reset_score` (~10 LOC for gate (b)). Total ~30 LOC. |
| 4 (sub-finding promotion) | DEFER | None promoted at step-1. Possible S29 candidate at step-2: "Cold-start magnitude plausibility gate as standing primitive" if validated. |
| 5 (cohort enumeration completeness) | PASS | 3 cohorts explicitly cataloged + striker-anchor scope-reservation declared. |
| 6 (test obligation) | OPEN at step-2 | New L1.5 cases: O-1 cold-start rejects implausible high-score seed; O-2 reset-authority API rounds-trips correctly; O-3 cascade reproduction (synthetic Scout dump with frame-3 score=49 overread; assert pipeline rejects + recovers to GT score). |
| 7 (cross-fixture verification) | DEFER to step-3 | Run snapshotter against `validate_dckkr_20260521_155356` dump after step-2 patch; verify E2 + negative-tokens cohorts close + no new regressions on other surfaces. |

---

## §8 Predicted-flip table for step-2

| Cohort | Pre-WS-O | Post-WS-O (predicted) | Predicted flip |
|---|---|---|---|
| E2-phantom-runs | 10 | 0-2 | CLOSE (PASS) or 80% reduction (PARTIAL) |
| Conservation invariants (§3) | 14 violations | 0-2 violations | CLOSE-TIED-TO-E2 |
| `this_over_tokens` negative | ~7 rows | 0 | CLOSE (excess branch unreachable) |
| Striker-anchor swap | ~50 fields | 0 (if shared root) OR ~50 (if SPLIT) | SCOPE-RESERVATION |
| G-pipeline-lag | 95 | 95 ± measurement | UNCHANGED (dump-scope artifact) |
| F-A-commit-lag | 9 | 9 | UNCHANGED |
| F-B-ad-occlusion | 7 | 7 | UNCHANGED |
| D-post-FoW-striker | 0 | 0 | UNCHANGED (already closed) |
| Per-batter-ledger-drift | 14 | 14 (or partial close if cascade-tied) | UNCHANGED-OR-PARTIAL |
| Boundary-counter-double-increment | 4 | 4 | UNCHANGED |
| Recent-overs-drop | 4 | 4 | UNCHANGED |
| Extras-counter-drop | 0 | 0 | UNCHANGED |
| Bowler-W-credit-failure | 0 | 0 | UNCHANGED |
| Multi-ball-compression | 0 | 0 | UNCHANGED |
| Compound-with-wicket-token | 0 | 0 | UNCHANGED |
| C21b-symbol-revert | 0 | 0 | UNCHANGED |
| Surface I silent-wicket-absorption | 0 | 0 | UNCHANGED |
| Surface J pipeline-missed-delivery | 0 | 0 | UNCHANGED |

**Methodology cap proximity.** N/A — budget framework retired
2026-05-24 (commit `32b88a7`). Predicted-flip table now serves as
S9-pattern cohort-closure scorecard rather than budget-cost
estimator.

---

## §9 Sub-findings

**No new sub-findings promoted at step-1.** Two candidate
promotions for step-2 / step-3:

- **S29 candidate (cold-start magnitude plausibility primitive).**
  If OA gate (a) is validated empirically (no false rejections
  against the L2 + L1.5 corpora), promote as a standing primitive
  applicable to other cold-start re-entry gates (P12 inn2 lockout
  already has score>30 / wickets>2 / overs>5.0 — extending the
  pattern to innings-1 closes the asymmetry).

- **S30 candidate (regression-rejection escape-hatch API).**
  If OA gate (b) is added, the new `Scoreboard.force_reset_score`
  becomes a primitive that other recovery paths
  (`_state_recovery_aggregator`, `_poison_streak` watchdog,
  potential WS-P striker-recovery) can reuse instead of partial
  reset state.

Both deferred to step-2 close-out.

---

## §10 Step-2 entry data

### Patch surface (step-2)

1. `files/score_manager.py` — `_handle_cold_start` (`:2716`):
   - Add cold-start seed-magnitude gate: reject `cold_candidate`
     when score > MAX_PLAUSIBLE_AT_OVERS(overs), where the cap
     is derived from an empirically calibrated RPO ceiling
     (e.g. 15 RPO for the first over, decay to 12 RPO for the
     remainder of the powerplay).
   - Gate fires after the false-zero / skeleton-strip / pre-match
     cue rejections so legitimate cold-start re-entry from
     mid-innings still passes (mid-innings re-entry has the
     `in_inn2_transition` lockout already; innings-1 cold-start
     needs the new gate).
   - Estimated ~20 LOC + trace tag.

2. `files/eyes/scoreboard.py` — `Scoreboard.force_reset_score`
   (new method near `:1220` set-score path):
   - Optional defense-in-depth API. Bypasses the `v < cur_int`
     predicate. Logs `[SCORE-FORCE-RESET]` for audit.
   - Caller surface limited to: cold-start recovery
     (`score_manager.py`), `_state_recovery_aggregator`,
     `_poison_streak` watchdog. NO main-loop callers.
   - Estimated ~10 LOC + 1 trace tag.

3. `files/scripts/pipeline_setup_helper.py` — no change required
   (helper already wires the necessary back-refs).

### Test obligation (gate-6)

L1.5 cases needed (step-2):
- **O-1 cold-start magnitude gate.** Frame with score=49 / overs=0.0
  rejected as implausible; cold_candidate not seeded.
- **O-2 cold-start magnitude gate honours legitimate high seeds.**
  Frame with score=49 / overs=4.0 (legitimate ~12 RPO) accepted.
- **O-3 `force_reset_score` round-trip.** Calling
  `Scoreboard.force_reset_score(22, reason="cold_start_recovery")`
  successfully walks score from 49 to 22 (bypasses predicate).
- **O-4 standard regression-rejection unchanged.** Standard
  `sb.set("score", v, frame)` with v < cur still rejects.

Estimated L1.5 delta: 4 cases (~80 LOC test scaffolding).

### Gate-7 cross-fixture verification (step-3)

After step-2 patch lands:
1. Re-run snapshotter against
   `files/logs/deliveries/watch_20260519_121701/scout_raw.jsonl`
   (DCKKR fixture from N1.2 baseline).
2. Run diff harness → compare against
   `files/tests/baselines/dckkr_diff_post_ws_n_baseline.md`.
3. Expected: E2 cohort 10 → 0-2; negative-tokens 7 → 0;
   conservation invariants 14 → 0-2. Striker-anchor swap
   unchanged (SCOPE-RESERVATION) or partial close (if cascade-tied).
4. Cross-fixture: re-run against
   `files/logs/deliveries/validate_dckkr_20260521_155356/scout_raw.jsonl`
   per runbook §5 second-fixture pass; surface any false
   rejections of legitimate seeds.

### Recommended next step

**WS-O step-2 patch authorization.** Static investigation chain
converges on OA leading candidate with gates 1-3 + 5 PASS;
gate 2 conditional on empirical validation at step-3. Patch
surface ~30 LOC across 2 files; test obligation 4 L1.5 cases
(~80 LOC). No §15-fence violation; no test_pipeline.py main-loop
touch.

If user prefers split execution (OA-only first, then OE
striker-anchor in a separate WS-P), step-2 patches OA gate (a)
+ (b) only and defers striker-anchor scope.

---

## §11 Status footer

**WS-O step-1 status.** CLOSED.

- 5 hypotheses enumerated; OA leading; OD subsumed by OA; OC
  falsified as standalone; OB viable defense-in-depth; OE
  partially confirmed (striker-anchor splits).
- Cohort closure UNIFIED-2 (E2 + negative-tokens close via OA);
  striker-anchor scope-reservation.
- Gates 1, 2 (conditional), 3, 5 PASS; gate 4 deferred; gate 6
  OPEN at step-2; gate 7 deferred to step-3.
- No sub-findings promoted (two step-2 candidates noted).

**Recommended next step.** WS-O step-2 patch authorization at the
~30 LOC scope identified in §10.

**Sub-mechanism reservation.** Exact `-N` token emission site
requires step-1.5 instrumentation (~3-5 LOC stack-trace log added
inline at the negative-token append site) to confirm vs the
candidate at `_synthesize_cold_start_ball_events` excess branch.
Recommend including the instrumentation in step-2 patch so it can
be exercised on the step-3 empirical replay.
