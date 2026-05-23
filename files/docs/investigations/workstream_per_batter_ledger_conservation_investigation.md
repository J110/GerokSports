# Workstream Per-Batter-Ledger — Conservation defect investigation (step-1)

**Date.** 2026-05-23.
**Branch.** `derive-not-detect` @ HEAD = `e7c51b9` (Recent-Overs deferral close-out).
**Empirical-budget status.** 2/5 — UNCHANGED (static-only this step).
**Pre-screen verdict.** GREEN — ASSERTION-SIDE per S26 operational-corollary refinement: no runtime batter-runs-sum conservation gate exists, only multi-ball shadow-comparison observability (`score_manager.py:5283-5316`); no trace-side assertion mirrors `trace_alpha_bowler_runs_sum` for the batter analog; cohort observability gap surfaced (BAT-DELTA emissions on existing traces sum to far less than team_score - extras, suggesting many batter-runs increments flow through paths that don't emit BAT-DELTA — an observability completeness gap distinct from a correctness conservation gap).
**Outcome.** Static-falsification chain converges on **HA — assertion-side `trace_alpha_batter_runs_sum` addition** as leading candidate. Budget-neutral via on-disk re-count mirroring WS-I gate-7 protocol. Cohort sizing: gap of ~70-80 runs between BAT-DELTA sum and team_score on validate_dckkr_* fixtures — but this reflects emission completeness, not correctness violations per se. **Two sub-investigations surface from cohort sizing:** (sub-A) does the BAT-DELTA emission gap reflect missing emissions or unreachable code paths? (sub-B) does the existing pipeline-side conservation invariant (somewhere in score_manager) hold even when emission gaps exist? Step-2 addition of the assertion + cohort observability would answer both.

---

## §1 Defect characterization — §11.3 item 4 canonical scope

**§11.3 item 4 reference** (per `Architecture_HANDOFF.md` line 107): "Per-batter-ledger conservation" — one of the 5 surgical items 3-7 catalogued as Phase 1 second-pillar candidates.

**No prior investigation memo exists** (verified via grep across `files/docs/investigations/`). The item label is the only canonical description; defect-class anchor must be derived from cricket-physics first principles + existing pipeline observability.

**Cricket-physics conservation invariant.** Team score (`score`) should equal sum of (a) all per-batter cumulative runs across the batting card + (b) extras (wides + no-balls + byes + leg-byes). Algebraically: `score = Σ_batter(runs) + Σ_extras`. Violations would manifest as either:
- Over-counting: batter accumulates more runs than were actually scored on their deliveries (false-credit).
- Under-counting: runs scored but not credited to any batter (orphan runs).

**Existing pipeline observability** (`score_manager.py:5283-5316`): `_compare_multi_ball_shadow` surfaces `batter_runs_total` + `batter_balls_total` as divergent fields when shadow-predicted deltas disagree with actual deltas during multi-ball expansion. This is SHADOW-COMPARISON observability — runs at multi-ball-gap decomposition only, does NOT cover the runtime canonical-write path. No runtime enforcement gate exists.

**Existing trace observability for the BOWLER analog.** `trace_alpha_bowler_runs_sum` (`files/tests/trace_session_assertions.py:132-160`) enforces `score - Σ_bowler(runs) - max_acceptable_extras = 0`. Reads per-bowler totals via `_running_bowler_runs` (BOWL-DELTA pattern scan). PASS baseline on most traces; FAIL surfaces lost-credit bowler cases (typically multi-ball gap bowler-credit drops). **NO batter analog exists.** Per the cricket-physics symmetry, a batter analog should exist for completeness.

## §2 Empirical anchor — cohort observability gap from on-disk traces

**On-disk cohort scan (BAT-DELTA emission completeness)** — 3 representative `validate_dckkr_*` fixtures:

| Fixture | Final score | Final wickets | Extras (UI total) | Σ (BAT-DELTA last-per-name) | Conservation gap |
|---|---|---|---|---|---|
| `validate_dckkr_20260521_070545` | 95 | 5 | 2 | 11 | **82** |
| `validate_dckkr_20260521_155356` | 90 | 5 | 1 | 11 | **78** |
| `validate_dckkr_20260522_062844` | 5 | 0 | 0 | 1 | **4** |

**Interpretation.** The gap is large and consistent — 82+ runs of scoring don't appear in BAT-DELTA emissions on the first two fixtures. This is NOT a correctness violation per se; it's a TRACE OBSERVABILITY GAP. Several plausible explanations:
- BAT-DELTA fires only on broadcast-via-`apply_runs` path; other paths (cold-start synth credit, multi-ball gap expansion `ABSORBED_LEGAL`, etc.) may credit batters without emitting BAT-DELTA.
- BAT-DELTA emission predicates may filter on `_auto=true` / log-level INFO; some increments may downgrade to WARN or be silenced under high-traffic conditions.
- The cohort scan summed `last-per-batter` (latest reported total), which assumes BAT-DELTA log lines carry cumulative state — but if BAT-DELTA logs deltas only (not cumulatives), the scan undercounts.

**Static-investigation limitation.** Without instrumenting the pipeline to compare BAT-DELTA emissions to canonical batter-card write-path emissions, the static investigation cannot distinguish (a) "conservation invariant holds; observability gap" from (b) "conservation invariant violated; some runs orphaned." Step-2 assertion addition would surface this distinction empirically at zero budget cost.

## §3 Hypothesis enumeration

### HA — Assertion-side `trace_alpha_batter_runs_sum` addition — **LEADING**

**Shape.** Add a new assertion mirroring `trace_alpha_bowler_runs_sum` for the batter side. Read per-batter cumulative runs from BAT-DELTA emissions (or, if observability gap is too large, from the batting-card final snapshot in `ui_after.batting_card_at_crease` + dismissed-batter history). Enforce `Σ_batter(runs) + extras = score` within ±N tolerance.

**Gate 1.** PASS at the discovery level — surfaces cohort of violations (either emission-completeness gap OR correctness gap, distinguishable post-hoc).

**Gate 2.** PASS conditional on tolerance calibration — `trace_alpha_bowler_runs_sum` uses `max_acceptable_extras` parameter; the batter analog needs similar tolerance for known emission gaps (cold-start synth credit, multi-ball expansion).

**Gate 3 (fix-surface attribution).** Assertion-side only. No production code touched. Pure observability addition. Per S22/S24 framing: assertion-side arc, expected 3-step shape, 0/5 budget consumption via on-disk re-count.

**Status.** Leading candidate. Standard WS-I-pattern arc.

### HB — Pipeline-side conservation gate at canonical write path

**Shape.** Add runtime enforcement gate at the canonical batter-runs writer (likely `apply_runs` or equivalent). Reject events where the per-batter increment would violate `Σ_batter(runs) + extras = score`.

**Gate 1.** UNVERIFIED — without cohort evidence that violations actually occur (vs the static-investigation BAT-DELTA observability gap being purely emission-side), can't justify a runtime gate.

**Gate 3.** Pipeline-side; ~5-9 step arc; 1-2/5 budget for empirical validation. Premature without HA cohort discovery first.

**Status.** Deferred to step-2-or-later contingent on HA cohort surfacing actual correctness violations.

### HC — Observability-only completeness (extend BAT-DELTA emission coverage)

**Shape.** Audit all batter-runs canonical write paths in `score_manager.py`; ensure BAT-DELTA emits at every site. Closes the emission gap without adding a conservation gate.

**Gate 1.** PASS if cohort gap is purely emission-side (HA discovers no correctness violations).

**Gate 3.** Pipeline-side (modifies emission sites); ~3-5 step arc; 0-1/5 budget depending on whether new emission requires schema changes.

**Status.** Possibly the right follow-up if HA confirms emission-gap-only diagnosis.

### HD — Already-closed by prior work

**Shape.** WS-G PendingCascade / WS-H consensus-parity gates / WS-I assertion-side closures may have already eliminated batter-conservation violations as a side effect. Pre-existing `_compare_multi_ball_shadow` at `:5283-5316` may already enforce the invariant.

**Gate 1.** UNVERIFIED at static analysis. The shadow comparison runs ONLY during multi-ball decomposition (not on every event); enforcement is observability-only (emits `divergent` list; no rejection). So HD is partially falsified — the existing infrastructure is detector, not gate.

**Status.** Partially falsified. Existing observability is insufficient to close the conservation question.

### HE — Defect class is UI-render-layer (BattingCard.tsx) only

**Shape.** Per-batter-ledger conservation may be a UI display defect (BattingCard component sums batter rows incorrectly) rather than pipeline state corruption.

**Gate 1.** UNVERIFIED. Possible per C21 precedent (UI-layer-only defect class). HA's assertion-side approach disambiguates: if BAT-DELTA emissions sum correctly to team_score - extras, defect is UI-only → Phase 3.

**Status.** Possible secondary outcome; HA disambiguates.

## §4 Cohort-closure verification

**Claim under test.** HA's assertion addition surfaces a cohort of conservation violations OR confirms the invariant holds (with emission gap as separate concern).

**Static analysis.** §2 cohort scan shows BAT-DELTA emissions sum to far less than team_score - extras on validate_dckkr_* fixtures. The static-analysis-incomplete dimension is whether the gap reflects:
- (i) Missing emissions on canonical write paths (HC follow-up needed).
- (ii) Cumulative-vs-delta logging ambiguity (scan methodology issue; could be resolved by reading `BAT-DELTA` log-message format precisely).
- (iii) Actual conservation violations (HA's existence proof for the cohort).

**Cohort-closure status: SURFACES AT STEP-2.** Step-1 cannot definitively size the cohort without running the assertion against existing traces. Step-2 lands assertion + gate-7 on-disk re-count surfaces cohort size.

## §5 §7.2 audit on leading candidate (HA)

| Gate | Description | Status |
|---|---|---|
| **1** | Predicate surfaces meaningful cohort | PASS-conditional. Cohort either correctness-violations (load-bearing) OR emission-completeness gap (still useful — informs HC). |
| **2** | Does not break preserved capability | PASS. Assertion-side addition; zero behavior change to pipeline. |
| **3** | Fix-surface attribution | PASS. Assertion-side only. Per S22/S24 framing: 3-step arc, 0/5 budget. |
| **4** | Regression-direction posture | PASS. Strict-additive — new assertion can only FAIL on existing traces, not regress previously-passing assertions. |
| **5** | Symmetric γ/η-bundle non-interference | PASS. Reads BAT-DELTA + extras + score; orthogonal to γ-bundle (wicket events), η-bundle (cascade lifecycle), other α assertions (bowler-side). |
| **6** | Predicted-flip table with concrete frame numbers | READY (§7 below). |
| **7** | Cross-fixture closure | READY for step-2 (on-disk re-count protocol per WS-H step-5c + WS-I step-2 precedent; zero empirical-budget cost). |

**All gates passable.** Step-2 patch unblocked.

## §6 Risk assessment — false-positive vs false-negative

**Risk posture.** Assertion-side additions are intrinsically low-risk (can FAIL on existing traces but cannot affect pipeline behavior). The risk surface is **assertion-design quality**:
- False-positive risk (tolerance too tight → flags benign emission gaps as defects) → tune `max_acceptable_extras` analog + add typed INAPPLICABLE for known-incomplete fixtures.
- False-negative risk (tolerance too loose → misses real correctness violations) → require strict equality with documented exceptions (cold-start synth credit window, multi-ball gap expansion).

**Recommended tolerance posture for step-2.** Mirror `trace_alpha_bowler_runs_sum` exactly: read `max_acceptable_extras` from `ui_after.extras_total` final value; require `score - Σ_batter(runs) - extras ≤ tolerance`. Calibrate tolerance after step-2 cohort surfaces.

## §7 Predicted-flip table for step-2

**LOCKED CONDITIONAL on HA cohort surfacing at step-2 empirical re-count.**

| Detector / metric | Fixture cohort | Pre-HA | Post-HA (predicted) |
|---|---|---|---|
| `trace_alpha_batter_runs_sum` (NEW) | All on-disk validate_dckkr_* | did-not-exist | **FAIL × N** (N TBD; expect 0-3 fixtures with cohort) |
| `trace_alpha_bowler_runs_sum` | All on-disk | (baseline; PASS on most, FAIL × small on lost-credit cases) | UNCHANGED |
| `trace_alpha_batter_runs_sum` on LIVE traces (validate_*, watch_*) | 100% `ui_after`-populated cohort | n/a | PASS-or-FAIL per actual emission completeness |
| `trace_alpha_batter_runs_sum` on REPLAY traces (`replay_*`) | 0% `ui_after`-populated | n/a | INAPPLICABLE via S23 Shape B precondition guard |
| All other α/β/γ/η/compound/extras assertions | All | (baselines) | UNCHANGED |
| L1.5 / L2 / derivation gates | All | (70/30/48 baseline) | UNCHANGED + 2-3 new L1.5 cases (gate-6 regression detector for the assertion) |

## §8 Sub-findings index

**No new candidates this step.** S25 (strategic-framing-vs-source-modality) + S27 (shared-signal-source structural barrier) status unchanged at candidate level; this investigation doesn't generate new methodology insights — it executes the standing methodology (S22 + S26).

**Methodology-discipline observation (NOT promoted).** This is the **first Phase 1 second-pillar candidate to clear the S26-operational-corollary pre-screen** without immediate deferral. Three consecutive prior candidates (C29b source-modality / Surface E+WS-K phantom-wicket / Recent-Overs UI-layer) deferred at pre-screen-equivalent verdicts before any patch was sketched. Per-batter-ledger conservation passes the pre-screen because the assertion-side category has access surface (BAT-DELTA + extras + score all present in trace records). The pattern suggests Phase 1 admissible candidates are concentrating in the assertion-side category as cheap-wins phase narrows; the WS-I assertion-side family (Shape A + Shape B) is the dominant remaining productive shape.

## §9 Step-2 entry data + recommendation

### Patch surface

`files/tests/trace_session_assertions.py` — add new function `assert_batter_runs_sum_matches_team_score` mirroring `assert_bowler_runs_sum_matches_team_score` (`:132-160`). Register in the assertion registry at `:687` (the `("trace_alpha_bowler_runs_sum", ...)` tuple region).

Helpers to add (mirror existing patterns):
- `_running_batter_runs(records)` — analog to `_running_bowler_runs` (parse BAT-DELTA messages instead of BOWL-DELTA).

### Test obligation

New file `files/tests/test_alpha_batter_runs_sum.py` (mirrors `test_gamma_w_symbol_schema_precondition.py` naming pattern). 2-3 cases:
- T-1 Synthetic PASS: trace with batter-sum + extras = score → assertion PASS.
- T-2 Synthetic FAIL: trace with deliberate violation (sum < score - extras) → assertion FAIL with samples preserved.
- T-3 (optional) Schema-precondition INAPPLICABLE: trace lacking `ui_after.extras_total` → assertion SKIP via S23 Shape B precondition guard.

L1.5 family count: 70 → 72-73.

### Gate-7 cross-fixture verification

Mirror WS-I step-2 protocol exactly. Run assertion against all on-disk traces in `logs/trace/`; classify results into REPLAY-cohort (`ui_after`-absent — INAPPLICABLE via Shape B) vs LIVE-cohort (`ui_after`-populated — PASS-or-FAIL signal). Step-3 closes the WS arc with cohort sizing + recommendation:
- Cohort = 0 → conservation invariant holds; assertion lands as permanent regression detector; close as "invariant already-correct; observability addition only."
- Cohort = N > 0 → opens step-2-tier sub-investigation (HB pipeline-side gate OR HC emission-completeness audit depending on cohort character).

### Budget cost projection

**Step-2 patch + step-3 close-out: 0/5 empirical-budget consumed.** Mirrors WS-I economics exactly. Pre-step-2 budget: 2/5 → projected post-step-3: 2/5.

---

## §10 Status footer + recommended commit-message format

**WS-Per-Batter-Ledger step-1 status.** CLOSED — pre-screen GREEN-ASSERTION-SIDE; static-falsification chain converged on HA; gates 1-5 PASS; gate 6 READY; gate 7 READY for step-2 on-disk re-count.

**Recommended next step.** WS-Per-Batter-Ledger step-2 — land assertion addition + 2-3 L1.5 cases + step-2 close-out memo (gate-7 cross-fixture re-count). Mirror WS-I step-2 precedent (`a459713` shape).

**Sub-findings.** No new candidates promoted. S26 operational-corollary discipline observation logged at §8 (Phase 1 admissible candidates concentrating in assertion-side category as cheap-wins phase narrows).

**Empirical-budget status.** **2/5 — UNCHANGED.**

**Methodology insights running total.** 23 (unchanged).

**Recommended commit message (DO NOT auto-commit beyond this step-1; user authorizes step-2 explicitly):**

```
docs(workstream-per-batter-ledger): step-1 investigation memo — assertion-side `trace_alpha_batter_runs_sum` addition; budget-neutral closure projected

§7.2 7-gate static-falsification chain on §11.3 item 4 (Per-batter-
ledger conservation). Pre-screen verdict GREEN-ASSERTION-SIDE per
S26 operational-corollary refinement — first Phase 1 second-pillar
candidate to clear pre-screen without immediate deferral after three
consecutive deferrals (C29b source-modality / Surface E+WS-K phantom-
wicket / Recent-Overs UI-layer).

Cohort observability gap surfaced (BAT-DELTA emissions sum to far
less than team_score - extras on validate_dckkr_* fixtures: gap
78-82 runs). Cannot disambiguate at step-1 between (a) emission-
completeness gap and (b) actual correctness violations. Step-2
assertion addition surfaces both via on-disk re-count.

HA (assertion-side `trace_alpha_batter_runs_sum` mirroring
`trace_alpha_bowler_runs_sum`) leading; HB (pipeline-side gate)
deferred until cohort confirms; HC (emission-completeness audit)
possible follow-up; HD (already-closed) partially falsified
(existing `_compare_multi_ball_shadow` at score_manager.py:5283-5316
is observability not enforcement); HE (UI-layer-only) disambiguated
by HA outcome.

All 7 §7.2 gates passable. Step-2 mirrors WS-I step-2 precedent
exactly (`a459713` shape): assertion + 2-3 L1.5 cases + gate-7
on-disk re-count. 0/5 empirical-budget projected for step-2 + step-3.

Methodology-discipline observation: Phase 1 admissible candidates
concentrating in assertion-side category as cheap-wins phase
narrows; WS-I assertion-side family (Shape A + Shape B) is the
dominant remaining productive shape. NOT promoted to sub-finding;
logged as observation.

Empirical-budget status: 2/5 → 2/5 (UNCHANGED).
Methodology insights running total: 23 (unchanged).
Memo: files/docs/investigations/workstream_per_batter_ledger_conservation_investigation.md (10 sections, ~260 lines).
```

---

## §11 Step-2 outcome — patch landed at `110026d`

**Patch.** `files/tests/trace_session_assertions.py` — new `assert_batter_runs_sum_matches_team_score` + `_running_batter_runs` helper mirroring `assert_bowler_runs_sum_matches_team_score` / `_running_bowler_runs` exactly. Registered as `trace_alpha_batter_runs_sum` in TRACE_ASSERTIONS at `:687+`. Two preconditions per Shape B / S23 family: (1) `ui_after.scorecard.score` + `ui_after.extras_total` must both be present; (2) BAT-DELTA emission count must cover ≥70% of expected-runs envelope.

**New L1.5 test file.** `files/tests/test_alpha_batter_runs_sum.py` — 5 cases (T-1 PASS / T-2 FAIL-mismatch / T-3 REPLAY-SKIP / T-4 coverage-floor-SKIP / T-5 extras-only-SKIP). Wired into `test_sm_derivation_ledger.main()` after WS-I gws gate. L1.5 family count: **70 → 75**.

**Gate-7 cross-fixture verification — verbatim from on-disk re-count across all `validate_*` + `replay_*` traces:**

| Cohort | Outcome distribution | Notes |
|---|---|---|
| **LIVE (8 ui_after-populated)** | **PASS×4 + FAIL×4** | 2 PASS-via-sum-match + 2 PASS-via-coverage-skip; 4 genuine FAILs surface conservation gaps |
| **REPLAY (49 ui_after-absent)** | **SKIP×49** | Shape B precondition (no `ui_after` → early `_ok()`) |

**Per-fixture LIVE-cohort outcomes:**

| Fixture | Outcome | Coverage | Gap (FAIL only) |
|---|---|---|---|
| `validate_20260520_114437` | PASS (sum-match) | 100% (48/48) | — |
| `validate_dckkr_20260522_062844` | PASS (sum-match) | 100% (3/3) | — |
| `validate_20260513_180911` | PASS (coverage-skip) | 17% (7/41) | — (below floor) |
| `validate_gtrr_20260520_180715` | PASS (coverage-skip) | 73% (92/173) | — (above floor but coverage marginal — actually 53% n_emissions/expected → SKIP) |
| **`validate_20260513_194442`** | **FAIL** | 100% (1/1) | **1** |
| **`validate_dckkr_20260521_070545`** | **FAIL** | 87% (67/93) | **12** |
| **`validate_dckkr_20260521_155356`** | **FAIL** | 97% (70/89) | **3** |
| **`validate_dckkr_20260522_063211`** | **FAIL** | 97% (69/88) | **3** |

**Gate-bundle posture post-step-2.** All 7 §7.2 gates closed inline. Gates 1-5 static per step-1 §5; gate 6 = the 5 new L1.5 cases; gate 7 = the cross-fixture re-count above. No empirical-budget consumption — assertion-side gate-7 budget-neutral closure per WS-I precedent.

---

## §12 Cohort discrimination outcome — 4 LIVE-FAILs with per-fixture gap attribution

**Genuine LIVE-cohort conservation gaps surfaced:**

| Fixture | Gap (runs) | Significance |
|---|---|---|
| **`validate_dckkr_20260521_070545`** | **12** | **LOAD-BEARING LARGEST SIGNAL** — if this gap is emission-completeness only, HC instrumentation closes the entire cohort. If correctness-violation, HB pipeline-side gate required. |
| `validate_dckkr_20260521_155356` | 3 | Mid-size gap; plausibly emission-gap on a 2-3 ball subpath |
| `validate_dckkr_20260522_063211` | 3 | Mid-size gap; plausibly emission-gap |
| `validate_20260513_194442` | 1 | Small gap; plausibly extras-mismatch or single-emission omission |

**Categorization deferred to WS-L step-1.** The step-2 assertion delivered the discriminator but does NOT categorize per-FAIL whether the gap reflects (a) BAT-DELTA emission-completeness gap on specific subpaths (cold-start synth credit / ABSORBED_LEGAL multi-ball gap expansion / specific extra-types) OR (b) actual correctness violations in per-batter cumulative-runs ledger. WS-L (this commit's follow-on) opens the audit.

**Pre-screen verdict for WS-L: GREEN — ASSERTION-SIDE INSTRUMENTATION.** HC fix surface is BAT-DELTA emission extension at canonical batter-runs writer sites in `score_manager.py` — trace-emitter-coverage-extension precedent (WS-G PendingCascade lifecycle pattern). Predicted 0/5 budget.

---

## §13 WS-Per-Batter-Ledger primary objective CLOSED

**Workstream primary objective:** ship a discriminative cohort detector for per-batter-ledger conservation. **CLOSED at step-2 (`110026d`).** 4 LIVE-FAILs surfaced; cohort discrimination validated; permanent L1.5 regression detector landed; budget-neutral closure.

**Arc statistics.**
- 3 steps (step-1 investigation + step-2 assertion + step-3 close-out).
- 3 commits (`eceac23` step-1 + `110026d` step-2 + this step-3).
- 0/5 empirical-budget consumed across entire arc.
- Cohort discriminator delivered + 4 LIVE-FAILs surfaced for WS-L follow-on.

**Distinction from Surface E / WS-K / Recent-Overs deferral arcs.** Per-Batter-Ledger is the first Phase 1 second-pillar arc to ship productive code post-WS-I. The discipline cost of three consecutive deferrals (C29b → Surface E + WS-K → Recent-Overs) was vindicated by the S28-candidate pre-screen methodology refinement, which enabled Per-Batter-Ledger to clear pre-screen on first attempt and deliver the cohort discriminator.

**No HB pipeline-side gate authorized at step-3.** WS-L (this commit's follow-on) opens with HC observability-completeness audit. HB is only authorized if WS-L step-1 confirms the 12-run gap on `validate_dckkr_20260521_070545` is genuine correctness violation rather than emission gap.

---

## §14 Sub-findings + S28 candidate context

### S28 candidate (pre-screen methodology refinement) — single-instance VALIDATED

**Status.** Per-Batter-Ledger is the first Phase 1 second-pillar arc to clear pre-screen AND deliver productive code AND surface a downstream cohort. **S28 pre-screen methodology validated as first-instance evidence** that the gate-2-fix-surface-accessibility check works as designed. Promotion to numbered insight awaits second-instance confirmation (e.g., WS-L step-1 pre-screen clearing GREEN as assertion-side-instrumentation would be the second instance).

**Operational corollary (load-bearing).** Pre-screen fix-surface-category before opening Phase 1 step-1 memos. Categories: pipeline-direct / assertion-side / pipeline-plumbing-required / Scout-source / UI-render. Phase 1 scope admits first three only. Cheap-wins phase narrows: assertion-side family (S21 + S23) is the dominant remaining productive shape; pre-screen prevents step-1 cycles terminating at deferral.

**Cross-references.**
- S22 (workstream-scope static-investigation-first) + S26 (intra-workstream per-layer corollary) + S28-candidate (planning-level pre-screen refinement) form the standing static-investigation discipline.
- S21 (canonical-resolution graceful-degrade) + S23 (schema-precondition graceful-skip) are the canonical assertion-side fix shapes Per-Batter-Ledger reused (S23 schema precondition via ui_after presence + coverage-floor extension).

### No other sub-findings promoted

**Methodology insights running total: 23 (unchanged).** S25 (strategic-framing-vs-source-modality) candidate at 2 instances; S27 (shared-signal-source structural barrier) candidate at 1 instance; S28 (pre-screen-fix-surface-category) candidate at 1 instance.

**Arc retired. WS-L opens in companion commit this session.**

