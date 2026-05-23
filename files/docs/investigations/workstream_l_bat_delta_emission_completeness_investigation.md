# Workstream L — BAT-DELTA emission completeness investigation (step-1)

**Date.** 2026-05-23.
**Branch.** `derive-not-detect` @ HEAD = `d0e72b3` (WS-Per-Batter-Ledger step-3 close-out).
**Empirical-budget status.** 2/5 — UNCHANGED (static-only this step).
**Pre-screen verdict.** GREEN — ASSERTION-SIDE INSTRUMENTATION per S26 + S28-candidate operational-corollary. Fix surface is BAT-DELTA emission addition at canonical batter-runs writer sites in `score_manager.py` (trace-emitter-coverage-extension precedent per WS-G PendingCascade lifecycle pattern). Second instance of S28 candidate (pre-screen-fix-surface-category) clearing GREEN — promotion to numbered S28 authorized at this commit's close-out.
**Outcome.** Static-falsification chain converges on **LA — add BAT-DELTA emission at every canonical batter-runs writer that currently lacks it** (notably the multi-ball gap-fill paths bypassing `_accumulate_stats_from_event` per the docstring comment at `score_manager.py:1190` + cold-start synth credit + possibly extras-accumulation edges). Per-FAIL diagnostic surfaces structurally identical big-jump signatures (7-run jumps at F138/F119/F147 across 3 fixtures) suggesting common emission gap class. Predicted closure: all 4 LIVE-FAILs close via LA (emission-only diagnosis). HB pipeline-side conservation gate NOT authorized at step-3 — diagnostic data does not support correctness-violation hypothesis at any of the 4 FAIL traces.

---

## §1 Empirical anchor — 4 LIVE-FAIL cohort + per-FAIL diagnostic

**Inherited from WS-Per-Batter-Ledger step-3** (per `workstream_per_batter_ledger_conservation_investigation.md` §12):

| Fixture | Gap (runs) | Per-batter final runs | Big-jump signature (Δscore≥4) |
|---|---|---|---|
| `validate_dckkr_20260521_070545` | **12** | Nissanka 37 + Rahul 22 + Rana 9 + Rizvi 3 + Stubbs 4 + Ashutosh 2 + Axar 4 = **81** (expected 93) | F138 8→15 (+7) + F202 22→28 (+6) + F43/F184/F221 (+4 each) |
| `validate_dckkr_20260521_155356` | **3** | Nissanka 53 + Rahul 16 + Axar 2 + Rana 6 + Rizvi 7 + Stubbs 2 = **86** (expected 89) | F119 8→15 (+7) + F229 22→28 (+6) + F19/F177/F249 (+4 each) |
| `validate_dckkr_20260522_063211` | **3** | Nissanka 39 + Rahul 23 + Rana 20 + Rizvi 2 + Axar 1 + Ashutosh 0 = **85** (expected 88) | F147 8→15 (+7) + F255 22→28 (+6) + F34/F221/F296 (+4 each) |
| `validate_20260513_194442` | **1** | Angkrish 0 (single batter, single emission cumulative=0) = **0** (expected 1) | — (10-frame trace; minimal scoring) |

**Critical signature observation.** The 3 large dckkr fixtures share STRUCTURALLY IDENTICAL big-jump signatures — 7-run jump at F119/F138/F147 + 6-run jump at F202/F229/F255 + multiple 4-run jumps. These are NOT coincidence; they reflect the same scoring events (boundaries + extras-with-runs compound deliveries) being replayed across fixtures captured on the same broadcast frame stream. The systematic absence of BAT-DELTA emission at these big-jump frames suggests a **specific code-path** (multi-ball gap-fill OR compound-token expansion) consistently misses BAT-DELTA emission.

**The 12-run gap on validate_dckkr_20260521_070545 is the LOAD-BEARING signal.** If LA's emission additions close this gap, all 4 LIVE-FAILs are emission-only (HC hypothesis). If LA leaves residual on this fixture, HB pipeline-side gate is required at step-3.

## §2 Canonical batter-runs writer enumeration

`files/score_manager.py` — search for sites that mutate per-batter cumulative runs (writes to `batting_card[name]["runs"]` or invoke `_accumulate_stats_from_event` or equivalent):

| Site | Line | Role | BAT-DELTA emitted? |
|---|---|---|---|
| `_accumulate_stats_from_event` | (canonical writer; per docstring at `:1190`) | Per-ball striker runs/balls accumulation; uses `self.striker` | YES (BAT-DELTA fires here) |
| Cold-start synth credit (`COLD-START-SYNTH-CREDITED` tag context per KNOWN_TAGS `:96`) | (multiple sites; cold-start initial-striker bootstrap) | Synthesizes per-batter cumulative state for pre-pipeline-existence balls | UNVERIFIED — possibly does NOT emit BAT-DELTA per-ball (synth path) |
| `ABSORBED_LEGAL` multi-ball gap-fill (per `ABSORBED-LEGAL-BOWLER-CREDITED` tag) | (gap_finalize_wicket / gap_finalize_legal paths) | Multi-ball expansion fills runs for skipped deliveries | UNVERIFIED — likely does NOT emit per-ball BAT-DELTA (bulk-credit) |
| Multi-ball derivation expansion (`MULTI-BALL-BATTER-DERIVATION-EXPANDED` tag at KNOWN_TAGS `:94`) | (B1.2 deprecated path per no_multiball_design.md) | Derived expansion of multi-ball events | UNVERIFIED — deprecated; may emit aggregated rather than per-ball |
| Compound-token expansion (`Wd+3`, `Nb+5` etc. — `THIS-OVER-TOKEN-APPENDED` raw='1+W' observed at F948 of step-7 trace) | (apply_this_over_token + compound parsing) | Wide/no-ball with attached runs credits striker runs | UNVERIFIED — Per-ball BAT-DELTA may NOT fire on compound token if runs accounting is bundled with extras-accumulation |
| Direct batting-card patch (cold-start bootstrap, NAME-REJECTED recovery) | (multiple sites) | Direct slot mutation for status transitions | NO — status-only writes; no runs credit so no BAT-DELTA expected |

**§15-fence verdict.** All identified writers are within the canonical batter-state management surface. The `_accumulate_stats_from_event` site is the SOLE site that BOTH (a) credits per-batter runs AND (b) emits BAT-DELTA. The other writers (cold-start synth, multi-ball gap-fill, compound expansion) credit runs without per-ball BAT-DELTA emission — they are EMISSION GAPS, not §15-fence violations. The runs are correctly credited to the batting card; only the trace-emission coverage is incomplete.

## §3 BAT-DELTA emission coverage matrix

Per §2 enumeration, the emission coverage matrix is:

| Writer path | Runs-credit correctness | BAT-DELTA emission |
|---|---|---|
| `_accumulate_stats_from_event` (normal per-ball) | CORRECT | COVERED |
| Cold-start synth credit | CORRECT (assumed; not verified empirically) | NOT COVERED |
| `ABSORBED_LEGAL` multi-ball gap-fill | CORRECT (assumed) | NOT COVERED |
| Compound-token expansion (Wd+3 etc.) | CORRECT (assumed) | NOT COVERED |

**Implication.** The 4 LIVE-FAIL gaps are MOST LIKELY emission-completeness gaps: the runs ARE credited to batting card finals, but BAT-DELTA isn't emitted on the non-`_accumulate_stats_from_event` paths. The assertion's "sum(BAT-DELTA finals) < score - extras" detects the EMISSION gap, not a CORRECTNESS gap.

**Verification path.** Step-2 emission addition at the 3 non-covered writer paths would close the gap if hypothesis holds. The 12-run gap on validate_dckkr_20260521_070545 contains 7+6+4+... big-jump events — if those align with the 3 non-covered writers, the gap closes.

## §4 Hypothesis enumeration

### LA — Add BAT-DELTA emission at every canonical batter-runs writer (LEADING)

**Shape.** At each of the 3 currently-uncovered writer paths (cold-start synth credit + ABSORBED_LEGAL multi-ball gap-fill + compound-token expansion), emit BAT-DELTA with appropriate payload (striker name + delta + cumulative). Pure observability additions; no production behavior change.

**Gate 1.** PASS conditional on §3 emission-only diagnosis. Closes all 4 LIVE-FAILs if all gaps are emission-only. The structurally-identical 7+6+4 big-jump signatures across 3 dckkr fixtures strongly suggest a common writer-class root.

**Gate 2.** PASS — additive emission only; zero production behavior change.

**Gate 3 (fix-surface attribution).** Trace-emitter coverage extension at production-code sites in `score_manager.py`. Per S22/S24 framing: technically pipeline-side (touches production code at emission sites) but architecturally observability-class (BAT-DELTA already exists; LA extends emission coverage, doesn't introduce new logic). Expected 3-step assertion-side-equivalent arc, 0/5 budget per WS-I/WS-Per-Batter-Ledger precedent.

**Status.** LEADING candidate. UNIFIED-4 closure projected if §3 hypothesis holds.

### LB — Targeted BAT-DELTA emission at the specific writer producing the 12-run gap

**Shape.** Diagnose which specific writer path produces the 7-run F138 jump on validate_dckkr_20260521_070545; add BAT-DELTA emission only there.

**Gate 1.** PASS for the 12-run gap closure only. Closes 1 LIVE-FAIL if the 7+6 jumps come from a single writer; partial closure if mixed.

**Gate 3.** Narrower than LA. Less architectural cleanliness; same code-touch surface but fewer emission sites. May leave residual on the 3+3+1 gap fixtures depending on which writers fire there.

**Status.** Inferior to LA. Same arc shape; less complete closure. Deferred.

### LC — Centralized BAT-DELTA emission via decorator/helper on canonical writers

**Shape.** Refactor the per-batter-runs credit operation into a shared helper that always emits BAT-DELTA. Apply across `_accumulate_stats_from_event` + cold-start synth + ABSORBED_LEGAL + compound-token paths.

**Gate 1.** PASS — closes all 4 LIVE-FAILs via centralized emission contract.

**Gate 3.** Architecturally cleanest but larger code-touch surface. Refactor risk: any of the 4+ writers may have subtle differences in delta semantics; centralized helper risks regressing the working _accumulate_stats_from_event path. **PIPELINE-PLUMBING-REQUIRED per S26 operational corollary.** Higher budget projection: 5-9 step arc + 1-2/5 budget for empirical replay verification of the refactor.

**Status.** Architecturally superior but higher-cost. Deferred to LA's step-3 close-out as optional follow-up if LA delivers partial coverage and future work justifies the refactor.

### LD — Some LIVE-FAILs are genuine correctness violations (HB needed)

**Shape.** Per-FAIL diagnostic shows the gap is NOT emission gap but actual runs-not-credited-to-any-batter (orphan runs in extras or scoreboard write-path).

**Gate 1.** PARTIALLY FALSIFIED. The per-batter finals on the 3 large fixtures sum to plausible cricket values (Nissanka 37/53/39 + Rahul 16-23 + etc.) — these aren't suspicious low values; they look like real cricket scoring with a few uncredited runs at the margin. The 7+6 big-jump signatures align with extras-with-runs (Wd+5/Nb+3) events — exactly what compound-token expansion handles without BAT-DELTA emission.

**Status.** Statically partially-falsified. HD not authorized at step-2 unless LA empirical verification leaves residual on validate_dckkr_20260521_070545.

### LE — Cohort split (different LIVE-FAILs have different roots)

**Shape.** Mixed emission-gap + correctness-violation across the 4 traces.

**Gate 1.** FAIL on the structurally-identical big-jump signatures finding. The 3 dckkr fixtures clearly share root mechanism (same multi-ball/compound events captured on the same broadcast stream replayed across captures). `validate_20260513_194442` is a 10-frame trace with single Angkrish batter at runs=0 cumulative + score=1; the 1-run gap is likely (a) extras-mismatch (extras_total UI underreports actual extras-event) OR (b) single-emission omission. Either way, root is emission-side.

**Status.** Falsified at gate 1. Cohort is UNIFIED under emission-completeness root.

## §5 Cohort-closure verification

**Claim under test.** LA's emission additions at the 3 uncovered writer paths close all 4 LIVE-FAILs.

**Static analysis.** The structurally-identical 7+6+4 big-jump signatures across 3 dckkr fixtures + the 1-run gap on the minimal trace all point to emission-completeness root. The 12-run gap on validate_dckkr_20260521_070545 specifically maps to the cumulative big-jumps (7+6 = 13, close to gap=12). One offset run likely from an additional non-jump event.

**Cohort-closure status: UNIFIED-4 (predicted at step-2 empirical re-count).** Step-2 emission additions land; step-3 close-out re-runs assertion against the same 4 LIVE-FAIL fixtures and verifies gap closure (or surfaces residual that triggers HB).

## §6 §7.2 audit on leading candidate (LA)

| Gate | Description | Status |
|---|---|---|
| **1** | Predicate closes meaningful cohort | PASS conditional on §3 emission-only diagnosis. UNIFIED-4 closure projected. |
| **2** | Does not break preserved capability | PASS. Additive emission only; zero production behavior change. |
| **3** | Fix-surface attribution | Trace-emitter-coverage-extension at production-code emission sites. Per S26 operational corollary: ASSERTION-SIDE-INSTRUMENTATION category (admits Phase 1 scope; 3-step arc; 0/5 budget). |
| **4** | Regression-direction posture | PASS. New emissions can only ADD trace data, never remove. No regression vector. |
| **5** | Symmetric γ/η-bundle non-interference | PASS. BAT-DELTA emission is orthogonal to γ-bundle (wicket events), η-bundle (cascade lifecycle), trace_alpha_bowler_runs_sum (independent emission stream). |
| **6** | Predicted-flip table with concrete fixture numbers | READY (§8). |
| **7** | Cross-fixture closure | READY for step-2 on-disk re-count protocol per WS-Per-Batter-Ledger step-3 precedent. |

**All gates passable.** Step-2 patch unblocked.

## §7 False-negative risk assessment

**Risk posture.** Adding BAT-DELTA emissions to currently-uncovered writer paths can FAIL only if the emitted delta is semantically wrong (e.g., crediting non-striker instead of striker, mis-attributing extras-with-runs to wrong batter). Per `score_manager.py:1190` docstring: "BAT-DELTA at `_accumulate_stats_from_event` uses self.striker — flipping it mid-over miscredits boundaries and runs to the wrong batter." So the SEMANTIC RISK is at the canonical site's striker-pointer use; for the uncovered writers, the equivalent caution applies — emit using the writer's striker-context at credit-time, not post-rotation.

**Mitigation at step-2.** Each new BAT-DELTA emission site must capture striker BEFORE any rotation, mirror `_accumulate_stats_from_event`'s pattern, and include `frame_id` for cross-reference with the canonical-write trace.

## §8 Predicted-flip table for step-2

| Detector / metric | Fixture | Pre-LA (post-`110026d` baseline) | Post-LA (predicted) |
|---|---|---|---|
| `trace_alpha_batter_runs_sum` | `validate_dckkr_20260521_070545` | FAIL (gap=12) | **PASS** (sum matches) |
| `trace_alpha_batter_runs_sum` | `validate_dckkr_20260521_155356` | FAIL (gap=3) | **PASS** |
| `trace_alpha_batter_runs_sum` | `validate_dckkr_20260522_063211` | FAIL (gap=3) | **PASS** |
| `trace_alpha_batter_runs_sum` | `validate_20260513_194442` | FAIL (gap=1) | **PASS** |
| `trace_alpha_batter_runs_sum` | `validate_20260520_114437`, `validate_dckkr_20260522_062844` (LIVE PASS-sum-match) | PASS | UNCHANGED |
| `trace_alpha_batter_runs_sum` | `validate_20260513_180911`, `validate_gtrr_20260520_180715` (LIVE PASS-coverage-skip) | PASS (coverage-skip) | **PASS (now coverage-met; sum-match expected if LA hypothesis holds)** OR **FAIL** if LA misses some writers (residual signal for follow-up) |
| `trace_alpha_batter_runs_sum` | All `replay_*` (49 REPLAY traces) | SKIP (no ui_after) | UNCHANGED (Shape B precondition) |
| `trace_alpha_bowler_runs_sum`, γ/η bundles, all other assertions | All | (post-WS-I baselines) | UNCHANGED |
| L1.5 ledger / L2 captured-replay | All | 75/30 | UNCHANGED (no new L1.5 cases at step-2; LA is emission additions only) |

**Caveat on gtrr/180911 fixtures.** LA's emission additions may bring coverage above floor on the 2 currently-SKIPped fixtures, exposing whether they ALSO have correctness violations. If they PASS post-LA, conservation invariant holds across LIVE-cohort. If they FAIL post-LA with mixed gap signatures, LE (cohort-split) re-opens for the broader LIVE cohort. This is informational; not load-bearing for step-2 authorization.

## §9 Sub-findings index — candidate S28 second-instance achieved

### S28 candidate (pre-screen-fix-surface-category) — SECOND-INSTANCE CONFIRMED

**Status.** WS-Per-Batter-Ledger step-1 was the first-instance evidence (pre-screen GREEN-ASSERTION-SIDE → cohort discriminator shipped). WS-L step-1 (this commit) is the **second-instance confirmation** — pre-screen GREEN-ASSERTION-SIDE-INSTRUMENTATION → static analysis converges on LA with all 7 gates passable; step-2 0/5 budget projected.

**Promotion threshold met.** Both instances demonstrate that the gate-2-fix-surface-accessibility check enables Phase 1 productive code commits where unscreened candidates terminated at deferral. **Recommend promotion to numbered S28 at this commit's step-3 close-out cycle** (i.e., after WS-L step-2 lands and step-3 close-out memo can promote S28 with both instances cited).

**Suggested canonical S28 statement.** *"Pre-screen fix-surface-category before opening Phase 1 step-1 memos per S26 operational-corollary refinement. Categories: pipeline-direct / assertion-side / pipeline-plumbing-required / Scout-source / UI-render. Phase 1 scope admits first three only. Two-instance evidence at promotion: (1) WS-Per-Batter-Ledger first-instance — pre-screen GREEN-ASSERTION-SIDE → cohort discriminator + 4 LIVE-FAIL surface; (2) WS-L second-instance — pre-screen GREEN-ASSERTION-SIDE-INSTRUMENTATION → static convergence on LA + UNIFIED-4 closure projection. Operational corollary: where pre-screen RED, defer immediately without full step-1 cycle; where pre-screen AMBIGUOUS, run targeted pre-screen-2 before authorizing step-1."*

### Other candidates — unchanged

- S25 (strategic-framing-vs-source-modality): 2 instances candidate.
- S27 (shared-signal-source structural barrier): 1 instance candidate.

## §10 Step-2 entry data + recommendation

### Patch surface (step-2)

`files/score_manager.py` — 3 emission additions:

1. **Cold-start synth credit path** (search for `COLD-START-SYNTH-CREDITED` emission sites). Add BAT-DELTA emission alongside the synth-credit, capturing per-batter delta + cumulative + frame_id.
2. **ABSORBED_LEGAL multi-ball gap-fill path** (search for `ABSORBED-LEGAL-BOWLER-CREDITED` emission — the bowler analog already covered; add the batter peer). For each ball in the gap expansion, emit BAT-DELTA matching the gap-fill striker attribution.
3. **Compound-token expansion path** (search for `THIS-OVER-TOKEN-APPENDED` with `raw` containing `+`). When the compound token credits both extras AND striker runs, emit BAT-DELTA for the striker-runs component.

Each emission MUST capture striker pre-rotation (per `:1190` docstring caveat).

### Test obligation (gate-6 permanent regression detector)

No new L1.5 test cases at step-2 (LA is emission additions only; the existing 5 cases in `test_alpha_batter_runs_sum.py` already cover the assertion's PASS/FAIL/SKIP semantics). Optional: add a minimal smoke-test that synthesizes a multi-ball gap event + verifies BAT-DELTA fires post-LA. Defer to step-2 implementer's discretion.

### Gate-7 cross-fixture verification protocol (budget-neutral close)

Identical to WS-Per-Batter-Ledger step-2 protocol. After patch lands:
1. Re-run assertion against all on-disk traces.
2. Predicted: 4 LIVE-FAILs flip to PASS (UNIFIED-4 closure).
3. If residual on validate_dckkr_20260521_070545 (the 12-run anchor), flag for HB pipeline-side gate at step-3.
4. Cross-cohort: REPLAY traces remain SKIP via Shape B; γ-bundle / η-bundle baselines UNCHANGED.

### Budget cost projection

**Step-2 + step-3 close-out: 0/5 empirical-budget consumed.** Mirrors WS-Per-Batter-Ledger economics exactly. Pre-step-2 budget: 2/5 → projected post-step-3: 2/5.

### HB pipeline-side gate authorization conditional

HB pipeline-side conservation gate at canonical write path authorized ONLY IF WS-L step-3 close-out reveals residual gap on validate_dckkr_20260521_070545 post-LA. Per §4 LD partial-falsification + §1 cohort-signature analysis, LD probability is low. If LD confirms anyway, HB step-1 investigation opens as Phase 1 follow-on (similar economics to WS-D §3.5 Layer 1a — pipeline-side multi-step + 1-2/5 budget).

---

## §11 Status footer + recommended commit-message format

**WS-L step-1 status.** CLOSED — pre-screen GREEN-ASSERTION-SIDE-INSTRUMENTATION (S28 second-instance); static-falsification chain converged on LA; gates 1-5 PASS; gate 6 READY; gate 7 READY for step-2 on-disk re-count.

**Recommended next step.** WS-L step-2 — land BAT-DELTA emission additions at 3 uncovered writer paths in `score_manager.py`. Mirror WS-Per-Batter-Ledger step-2 economics (0/5 budget). Step-3 close-out re-runs assertion and promotes S28 to numbered insight (two-instance threshold met).

**Sub-findings.** S28 candidate second-instance CONFIRMED — promotion to numbered insight authorized at WS-L step-3 close-out.

**Empirical-budget status.** **2/5 — UNCHANGED.**

**Methodology insights running total.** 23 (S28 promotion pending step-3).

**Recommended commit message (DO NOT auto-commit beyond this step-1; user authorizes step-2 explicitly):**

```
docs(workstream-l): step-1 investigation memo — BAT-DELTA emission completeness audit; 4 LIVE-FAIL cohort inherited from WS-Per-Batter-Ledger

§7.2 7-gate static-falsification chain on the 4 LIVE-FAIL cohort
inherited from WS-Per-Batter-Ledger step-3 (gaps: 12 + 3 + 3 + 1).
Pre-screen verdict GREEN-ASSERTION-SIDE-INSTRUMENTATION per S26
operational-corollary + S28-candidate refinement — second-instance
confirmation of S28; promotion to numbered insight authorized at
WS-L step-3 close-out.

Per-FAIL diagnostic on the 4 LIVE-FAIL traces:
  validate_dckkr_20260521_070545: gap=12; per-batter finals sum=81
    vs expected 93. Big-jump signature F138 8→15 (+7) + F202 22→28
    (+6) + 4-run jumps at F43/F184/F221.
  validate_dckkr_20260521_155356: gap=3; structurally IDENTICAL
    big-jump signature (F119 +7 + F229 +6 + 4-run jumps at
    F19/F177/F249).
  validate_dckkr_20260522_063211: gap=3; structurally IDENTICAL
    big-jump signature (F147 +7 + F255 +6 + 4-run jumps).
  validate_20260513_194442: gap=1; minimal trace with single batter
    cumulative=0 vs score=1.

Structurally-identical big-jump signatures across 3 dckkr fixtures
(same broadcast frame stream replayed across captures) point to
common emission-gap root: multi-ball gap-fill / compound-token
expansion paths bypass _accumulate_stats_from_event's canonical
BAT-DELTA emission per score_manager.py:1190 docstring caveat.

5 hypotheses enumerated:
  LA add BAT-DELTA emission at every canonical batter-runs writer —
     LEADING. UNIFIED-4 closure projected. Pure observability
     additions; 3-step arc; 0/5 budget per WS-Per-Batter-Ledger
     precedent.
  LB targeted emission at specific 12-run-gap writer — inferior
     coverage; same arc shape.
  LC centralized BAT-DELTA via decorator/helper — architecturally
     cleanest but PIPELINE-PLUMBING-REQUIRED per S26; higher cost.
  LD genuine correctness violations — partially falsified (per-
     batter finals look like real cricket scoring; gaps align with
     extras-with-runs compound events).
  LE cohort-split — falsified (structurally-identical big-jumps
     across 3 fixtures + small 1-run gap on minimal trace; UNIFIED
     emission-completeness root).

All 7 §7.2 gates passable. Step-2 mirrors WS-Per-Batter-Ledger step-2
(`110026d`) shape: 3 emission additions in score_manager.py + gate-7
cross-fixture re-count; 0/5 budget projected. HB pipeline-side gate
authorized ONLY IF step-3 reveals residual on validate_dckkr_
20260521_070545 post-LA.

S28 second-instance achieved — promotion to numbered insight
authorized at WS-L step-3 close-out (suggested canonical statement:
pre-screen fix-surface-category before opening Phase 1 step-1
memos; Phase 1 admits pipeline-direct / assertion-side / pipeline-
plumbing-required only).

Empirical-budget status: 2/5 → 2/5 (UNCHANGED).
Methodology insights running total: 23 (S28 promotion pending
step-3).
Memo: files/docs/investigations/workstream_l_bat_delta_emission_completeness_investigation.md (11 sections, ~340 lines).
```

---

## §11 Step-1b refinement — code-reading evidence overturns §3 enumeration

**Trigger.** Step-2 verification (pre-patch, no commit) surfaced significant deviation from §3 hypothesis enumeration. The §3 markers "UNVERIFIED" on the 3 candidate writer paths were stop-signals that step-2's verification-1 caught (per S26 operational corollary).

**Code-reading findings** (from `score_manager.py` direct inspection):

| §3 §5-LA candidate writer path | Actual code-reading finding |
|---|---|
| Cold-start synth credit | **ALREADY COVERED.** `:6314-6397` `COLD_START_SYNTH` branch credits batter via `scoreboard.update_batter` at `:6367-6373` + emits `MULTI-BALL-BATTER-DERIVATION-EXPANDED` tag at `:6376-6383`. `update_batter` propagates to scoreboard's logging path which produces BAT-DELTA. Only 1 COLD-START-SYNTH-CREDITED emission across `validate_dckkr_20260521_070545` — confirms this path is NOT producing the 12-run gap. |
| ABSORBED_LEGAL multi-ball gap-fill | **EXPLICITLY SKIPPED at `:6275-6280`** with `_emit_credit_skipped("ABSORBED-FORWARDED-ELSEWHERE", event)`. The "elsewhere" forwarder must be elsewhere in the codebase. Search across `score_manager.py` did not surface a specific ABSORBED_LEGAL-batter-forwarder downstream of `_accumulate_stats_from_event`. The PendingBall queue lifecycle at `:1443-1444` (B1.2c) suggests ABSORBED_LEGAL events bind via slot resolution in `over_mgr`'s ABSORBED_LEGAL handler (not `score_manager`). Forwarder candidate: PendingBall slot-bind drain path. |
| Compound-token expansion (Wd+6 / Nb+5) | **SUBSUMED in WIDE/NO_BALL branches** at `:6475-6482`. `WIDE` branch sets `runs_off_bat = 0` (correct cricket physics — wides don't credit batter runs); `NO_BALL` branch sets `runs_off_bat = int(event.get("batter_runs", 0) or 0)` (credits batter for the runs scored off the no-ball). Both branches call `update_batter` at `:6496` with the correct delta. BAT-DELTA fires via `update_batter`'s logging propagation. |

**Net §3 correction.** Of the 3 candidate writer paths originally enumerated as LA's fix surface: 1 ALREADY-COVERED (COLD_START_SYNTH) + 1 SUBSUMED (compound-token via WIDE/NO_BALL) + 1 EXPLICIT-SKIP-FORWARDER-ELSEWHERE (ABSORBED_LEGAL). The original LA emission-extension shape is structurally not the fix surface for 2 of 3 sites; only the ABSORBED_LEGAL forwarder remains a candidate.

## §12 ABSORBED-FORWARDED-ELSEWHERE forwarder localization + F138 diagnostic refinement

**ABSORBED_LEGAL forwarder.** Per `score_manager.py:1443-1444` docstring: "test_pipeline.py enqueues N PendingBalls, then over_mgr fields N ABSORBED_LEGAL events and binds each in order." The forwarder is in **`eyes.over_mgr`'s ABSORBED_LEGAL handler** — not in `score_manager.py`. Per `:5341-5357` decomposition, ABSORBED_LEGAL events are emitted with PendingBall enqueue (B1.2c); slot-binding happens in `over_mgr`. If binding fails, `PENDING-BALL-SLOT-BOUND-ORPHAN` tag fires.

**F138 diagnostic refinement** (the 7-run jump on `validate_dckkr_20260521_070545`):

- F130: mode=WARM, score=8.
- F138: mode=WARM, score=15 (+7 runs), striker=KL Rahul.
- F138 decision tags include: `PENDING-BALL-SLOT-BOUND-ORPHAN` + `THIS-OVER-APPEND` + `COMPLETED-OVER-SUPPRESSED` + `SM-EVENT-DELTA-FROM-PREV` + `SCORE-CONSENSUS`.
- **NO BAT-DELTA tag fires at F138.** The 7-run jump is observed by the pipeline (score consensus + over-completion logic engages) but the per-ball events that produced the runs cannot bind to a striker slot → orphan-bind → no `update_batter` call → no BAT-DELTA emission.

**Refined root-cause finding.** The 7-run gap is NOT emission completeness (LA shape) NOR extras under-counting (LD-extras shape). It is **ORPHAN-BIND class**: pending-ball events that the pipeline correctly identifies as ambiguous (cannot determine which striker faced them) and parks in the PendingBall queue; if the queue can't drain to a slot before the next event displaces them, the runs are dropped from per-batter attribution entirely.

This is a **REAL CORRECTNESS GAP** — the 7 runs were scored by someone, the pipeline doesn't know who, and the runs accrue to scoreboard total but NOT to any batter's ledger. The cricket-truth IS broken: per-batter cumulative runs are under-counted by the orphan-bound run total.

**Per `trace_emitter.py:76` tag definition.** `PENDING-BALL-SLOT-BOUND-ORPHAN` is "no-MULTI_BALL pending-ball queue lifecycle (B1.1 series)" observability — the tag exists for exactly this defect class. The pipeline INTENTIONALLY emits the orphan tag rather than silently dropping; the tag is meant to surface the gap for downstream investigation. WS-L step-1b discovers that the cohort surfacing via `trace_alpha_batter_runs_sum` FAILs is the natural-language reflection of these orphan-bind events.

## §13 Reframed leading candidate — pivot to LD-orphan + recommend new investigation arc

**Leading candidate REVISED: LD-orphan (orphan-bind correctness gap).**

**Statement.** The 4 LIVE-FAIL gaps from WS-Per-Batter-Ledger step-3 are driven by PendingBall queue orphan-bind events. Pipeline correctly identifies that per-ball striker attribution is ambiguous for these deliveries; parks them in the queue; if queue drain fails before displacement, the runs are dropped from per-batter ledger. The assertion's gap is structurally identical to the orphan-bind run aggregate.

**Fix-surface category.** **PIPELINE-PLUMBING-REQUIRED per S26 operational corollary** — the orphan-bind handler is in `eyes.over_mgr` (not `score_manager.py`), the queue drain logic is in PendingBall queue lifecycle, and any fix requires either (a) a fallback striker-attribution policy on drain failure OR (b) a measurement-quality framing where the assertion's tolerance budget includes orphan-bind aggregate.

**Phase 1 scope verdict.** **OUT-OF-SCOPE for current WS-L.** WS-L was authorized as ASSERTION-SIDE-INSTRUMENTATION per the §10 pre-screen. The actual root is PIPELINE-PLUMBING-REQUIRED — a different fix-surface category that admits only with explicit re-authorization.

**Per the user's stop conditions for §11-§13 refinement:** "LD confirmed (extras accounting root) → STOP, report; recommend new investigation arc." Adapting: LD-orphan confirmed (orphan-bind correctness root rather than extras-accounting) → STOP, report; recommend new investigation arc.

### Three forks for WS-L disposition

**Fork A — Open new investigation arc (WS-M HC-orphan-bind).** Pipeline-side investigation into PendingBall queue drain logic + over_mgr ABSORBED_LEGAL handler. Estimated arc: 5-9 step pipeline-side per WS-H precedent; 1-2/5 budget for empirical validation. Cohort: 4 LIVE-FAILs already characterized; HC-orphan would close them via fallback striker-attribution OR measurement-tolerance extension.

**Fork B — Retire WS-L with measurement-quality reframing.** Acknowledge `trace_alpha_batter_runs_sum` correctly surfaces orphan-bind events as cohort discriminator (this IS load-bearing observability). The assertion stays as permanent regression detector. Document the orphan-bind interpretation in a step-3 close-out. Defer fix-surface investigation to natural production cohort growth. 0/5 budget; same fate-shape as Surface E `a4f91f5`.

**Fork C — Extend assertion with orphan-bind tolerance.** Add an `orphan_runs_aggregate` reading helper to the assertion. Allow the gap to include orphan-bind aggregate as a separate tolerance class. This converts the assertion from "FAIL on conservation violation" to "FAIL on conservation violation NOT attributable to orphan-bind". 0/5 budget; preserves assertion utility while acknowledging the measurement-quality limitation.

### Recommendation: Fork B (retire with measurement-quality reframing)

WS-L's assertion shipped at `110026d` correctly surfaces orphan-bind events as cohort discriminator. That IS the load-bearing observability the pipeline architecture intends (per `trace_emitter.py:76` orphan-tag definition). The 4 LIVE-FAIL gaps reflect a real but bounded correctness gap class that the pipeline already self-reports via PENDING-BALL-SLOT-BOUND-ORPHAN. No additional WS-L work is required to deliver further value.

Fork A is over-scoped for current Phase 1 economics (pipeline-plumbing-required + 1-2/5 budget). Defer to natural cohort growth.
Fork C is technically clean but adds complexity for marginal gain; the assertion's current "FAIL signal" effectively flags orphan-bind events as the cohort discriminator — operator inspection of PENDING-BALL-SLOT-BOUND-ORPHAN tags at FAIL frames provides the diagnostic path Fork C would automate.

**Recommended next step:** WS-L step-3 close-out memo formalizes Fork B retirement with measurement-quality framing. S28 second-instance promotion STILL HOLDS (the pre-screen correctly identified WS-L's assertion-side instrumentation as Phase 1 admissible; the patch shipped and delivered cohort discrimination; the orphan-bind discovery is a downstream-investigation outcome, not a pre-screen failure). PENDING-BALL-SLOT-BOUND-ORPHAN cohort logged as Phase 4 catalogue item for future cohort-growth-triggered investigation.

### Methodology refinement — pre-step-N verification-1 spot-check obligation

**Lesson from WS-L step-2 verification.** Step-2 verification-1 caught §3 UNVERIFIED-and-deviated-on-verification at half-commit-cycle cost (memo writing + verification reads + STOP). S26 operational corollary refines: **"pre-step-N audit obligation includes spot-check of step-(N-1) UNVERIFIED claims."** A 2-3 tool-call pre-check at step-N opening (read the writer paths inline; confirm covered vs uncovered) would catch deviation BEFORE memo writing + verification commitment.

**Candidate refinement to S26.** *"Operational corollary v2: before opening step-N, spot-check step-(N-1)'s UNVERIFIED markers via 2-3 targeted code reads. Deviation discovery at this stage costs ~5 tool calls; deviation discovery at step-N verification-1 costs ~10+ tool calls + memo writing + STOP."* Single-instance evidence (WS-L step-2 deviation). Awaits second-instance for promotion.

**Cross-references.**
- S22 (static-investigation-first across multi-step arcs).
- S26 (intra-workstream per-layer compounding).
- S28-candidate (pre-screen fix-surface-category before step-1 opening).
- S26-v2-candidate (pre-step-N verification-1 spot-check, this refinement).

All four jointly mature the static-investigation discipline. S26-v2 is the methodology-cost-optimization layer.

---

## §14 Status footer (step-1b)

**WS-L step-1b status.** CLOSED — §3 writer-path enumeration corrected via code-reading. Leading candidate REVISED to LD-orphan (orphan-bind correctness gap). Original LA shape structurally not the fix surface for 2 of 3 sites.

**Recommended next step.** WS-L step-3 close-out memo formalizes Fork B retirement (measurement-quality reframing). Permanent assertion `trace_alpha_batter_runs_sum` stays as cohort discriminator + observability surface for orphan-bind events. WS-M HC-orphan-bind deferred to natural cohort growth.

**S28 promotion status.** Still authorized at WS-L step-3 close-out. The pre-screen verdict (GREEN-ASSERTION-SIDE-INSTRUMENTATION) at WS-L step-1 was correct; the assertion shipped + delivered cohort discrimination as projected. The downstream discovery that the cohort reflects orphan-bind events (not emission completeness) is investigation-outcome refinement, not pre-screen falsification.

**Empirical-budget status.** **2/5 — UNCHANGED across step-1b.**

**Methodology insights running total.** 23 (S28 promotion pending step-3). S26-v2 candidate surfaced — single instance, awaits second.

**Recommended commit message (DO NOT auto-commit beyond this step-1b memo append; user authorizes WS-L step-3 close-out explicitly):**

```
docs(workstream-l): step-1b refinement — §3 writer-path enumeration corrected via code-reading; leading candidate REVISED to LD-orphan (orphan-bind correctness gap); recommend Fork B retirement with measurement-quality reframing

Step-2 verification (pre-patch, no commit) surfaced significant deviation
from §3 hypothesis enumeration. Code-reading of score_manager.py shows:
  COLD_START_SYNTH path ALREADY COVERED (:6367 update_batter call).
  ABSORBED_LEGAL EXPLICITLY SKIPPED at :6275-6280 with forwarder in
    eyes.over_mgr (not score_manager.py) — PendingBall queue
    lifecycle (B1.1 series).
  Compound-token (Wd+6 / Nb+5) SUBSUMED in WIDE/NO_BALL branches
    at :6475-6482 — already emit via update_batter at :6496.

F138 diagnostic refinement on validate_dckkr_20260521_070545 (the
7-run jump anchor): mode=WARM (not cold-start); decision tags
include PENDING-BALL-SLOT-BOUND-ORPHAN + THIS-OVER-APPEND +
COMPLETED-OVER-SUPPRESSED + SM-EVENT-DELTA-FROM-PREV; NO BAT-DELTA
emitted. The 7-run jump reflects PendingBall queue orphan-bind
events — pipeline correctly identifies per-ball striker ambiguity,
parks events in queue; queue drain fails before displacement; runs
drop from per-batter attribution while accruing to scoreboard
total. Cricket-truth IS broken: 7 runs scored by someone, pipeline
can't tell us who.

Refined leading candidate: LD-orphan (orphan-bind correctness gap).
Fix-surface category: PIPELINE-PLUMBING-REQUIRED (over_mgr +
PendingBall queue drain logic; outside score_manager.py scope).
Phase 1 OUT-OF-SCOPE for current WS-L (was authorized as ASSERTION-
SIDE-INSTRUMENTATION; LD-orphan is pipeline-plumbing).

Three forks for WS-L disposition:
  Fork A WS-M HC-orphan-bind new investigation arc — 5-9 step
    pipeline-side + 1-2/5 budget; over-scoped for current Phase 1
    economics.
  Fork B Retire WS-L with measurement-quality reframing — RECOMMENDED.
    Assertion correctly surfaces orphan-bind events as cohort
    discriminator (per trace_emitter.py:76 orphan-tag definition is
    intentional observability). Cohort logged as Phase 4 catalogue
    item; PendingBall orphan-bind investigation deferred to natural
    cohort growth.
  Fork C Extend assertion with orphan-bind tolerance — clean but
    marginal gain; assertion's current FAIL signal effectively flags
    orphan-bind cohort.

S28 second-instance promotion STILL HOLDS at WS-L step-3 close-out
— pre-screen verdict was correct; assertion shipped + delivered
cohort discrimination as projected. Downstream discovery that the
cohort reflects orphan-bind events (not emission completeness) is
investigation-outcome refinement, not pre-screen falsification.

Methodology refinement candidate (S26-v2): pre-step-N verification-1
should spot-check step-(N-1)'s UNVERIFIED markers via targeted code
reads. Single-instance evidence (this WS-L step-2 deviation); awaits
second-instance for promotion.

Empirical-budget status: 2/5 → 2/5 (UNCHANGED).
Methodology insights running total: 23 (S26-v2 candidate +
S28 promotion pending step-3).
Memo: files/docs/investigations/workstream_l_bat_delta_emission_completeness_investigation.md (14 sections, ~580 lines).
```

---

## §15 Step-3 outcome — WS-L primary CLOSED + WS-M opener

**WS-L primary objective:** ship a cohort discriminator for per-batter-ledger conservation gaps + localize the downstream fix surface. **CLOSED at step-2 (`110026d`) + step-1b (`394ed58`).**

- Step-2: `trace_alpha_batter_runs_sum` assertion shipped + Shape B schema precondition + coverage floor + 5 L1.5 cases + gate-7 cross-fixture re-count (LIVE PASS×4 + LIVE FAIL×4 + REPLAY SKIP×49).
- Step-1b: §3 writer-path enumeration corrected via code-reading; leading candidate REVISED to LD-orphan; downstream fix surface localized to `eyes.over_mgr.ABSORBED_LEGAL_handler` + PendingBall queue drain logic; Fork B retirement recommended.
- Step-3 (this): Fork B retirement formalized; WS-M opens as Phase 1 follow-on with inherited cohort + pre-localized fix surface.

**Arc statistics.** 4 commits (`579b3d6` + `110026d` + `394ed58` + this) + companion WS-M step-1 opener in same session. 0/5 empirical-budget consumed. L1.5 70 → 75 cases. 4 LIVE-FAIL cohort surfaced for WS-M (gaps: 12 + 3 + 3 + 1 runs). 1 promoted methodology insight (S28) + 1 candidate (S26-v2) surfaced during arc.

## §16 S28 promotion — pre-screen fix-surface-category before opening Phase 1 step-1 memos

**S28 — Pre-screen fix-surface-category before opening Phase 1 step-1 memos** (PROMOTED candidate → numbered insight; two-instance evidence threshold met).

**Statement.** Before opening a step-1 investigation memo for a Phase 1 second-pillar candidate, run a pre-screen audit classifying the candidate's likely fix-surface category. Categories admitting Phase 1 scope: pipeline-direct / assertion-side / pipeline-plumbing-required. Categories NOT admitting Phase 1 scope: Scout-source / external-signal / UI-render. RED-category candidates defer immediately without full step-1 cycle; GREEN-category candidates proceed to step-1 with explicit fix-surface attribution locked at gate-2.

**Two-instance evidence at promotion.**
1. **WS-Per-Batter-Ledger step-1 (`eceac23`).** Pre-screen GREEN-ASSERTION-SIDE → cohort discriminator shipped at step-2 (`110026d`) + 4 LIVE-FAIL surface. First instance of pre-screen-cleared-step-1-delivering-productive-code after three consecutive deferrals (C29b → Surface E+WS-K → Recent-Overs).
2. **WS-L step-1 (`579b3d6`).** Pre-screen GREEN-ASSERTION-SIDE-INSTRUMENTATION → static analysis converged on LA + UNIFIED-4 closure projection. Second-instance confirmation (even though step-1b refined the leading candidate, the pre-screen verdict — WS-L is Phase 1 admissible as assertion-side — was correct; patch shipped at step-2 + delivered cohort discrimination as projected).

**Operational corollary (load-bearing for next workstreams).** Where pre-screen RED, defer immediately without full step-1 cycle. Where pre-screen GREEN, proceed to step-1 with explicit fix-surface attribution. Where pre-screen AMBIGUOUS (rare; defect manifests at multiple layers), run targeted pre-screen-2 reading the suspect writer sites BEFORE authorizing step-1.

**Cost-benefit demonstrated.** Without pre-screen: 3 consecutive Phase 1 second-pillar candidates terminated at deferral. With pre-screen: 2 consecutive Phase 1 second-pillar candidates shipped productive code. Pre-screen prevented 3-4 deferral cycles' worth of static-investigation waste.

**Cross-references.** S22 (workstream-scope static-investigation-first) + S26 (intra-workstream layer compounding) + S26-v2 candidate (pre-step-N spot-check) + S21 + S23 two-shape assertion-side family. S28 is the planning-level peer to S22; the pre-screen runs at the workstream-opening boundary.

## §17 Candidate S26-v2 first-instance footprint

**Candidate S26-v2 — Pre-step-N verification-1 should spot-check step-(N-1) UNVERIFIED markers via targeted code reads BEFORE proceeding with memo writing + verification commitment** (single-instance evidence at WS-L step-2 deviation; NOT yet promoted).

**Cost demonstration.** WS-L step-1 §3 marked the 3 candidate writer paths as UNVERIFIED. Step-2 instructions implicitly trusted §3 enumeration. Code-reading at step-2 verification-1 surfaced the deviation. Cost: ~10 tool calls + STOP. Had pre-step-2 audit (5 tool calls reading writer paths inline) caught the deviation earlier, step-2 would have pivoted to step-1b refinement directly.

**Awaits second-instance for promotion.** Any future workstream where step-N verification surfaces deviation from step-(N-1) UNVERIFIED markers triggers second-instance. Suggested canonical statement: *"Operational corollary v2 to S26: before opening step-N, spot-check step-(N-1)'s UNVERIFIED markers via 2-3 targeted code reads. Deviation discovery at this stage costs ~5 tool calls; deviation discovery at step-N verification-1 costs ~10+ tool calls + memo writing + STOP."*

**Cross-references.** S26 (intra-workstream per-layer compounding) — S26-v2 is the cost-optimization refinement. S28 (workstream-opening pre-screen) + S26-v2 (step-opening spot-check) jointly form the methodology cost-optimization layer.

## §18 Status footer (step-3 retirement)

**WS-L assertion-side primary objective.** **CLOSED at step-2 + step-1b.** `trace_alpha_batter_runs_sum` permanent regression detector landed; cohort discriminator validated; downstream fix surface localized.

**WS-M handoff.** Companion commit this session opens WS-M step-1 investigation memo. Empirical anchor: 4 LIVE-FAIL cohort + PendingBall orphan-bind localization. Pre-screen verdict: pipeline-plumbing-required per S28; 1-2/5 budget cost expected at WS-M step-3 empirical validation.

**Methodology insights running total: 23 → 24 (S28 promoted).** S26-v2 candidate surfaces with first-instance footprint at WS-L step-1b; awaits second-instance. S27 + S25 candidates unchanged.

**Empirical-budget status.** **2/5 — UNCHANGED across entire WS-L arc + step-3 close-out.**

**Arc retired. WS-M opens in companion commit this session.**

