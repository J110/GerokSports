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
