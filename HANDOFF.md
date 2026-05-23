# Handoff — Session continuation document

**Last update**: 2026-05-23 (WS-L primary CLOSED — assertion-side discriminator shipped + downstream fix surface localized to over_mgr orphan-bind via step-1b refinement; S28 PROMOTED to numbered insight; WS-M opens as pipeline-plumbing follow-on with inherited 4 LIVE-FAIL cohort).
**Branch**: `derive-not-detect` (HEAD = WS-Surface-E retirement docs commit). Feature branch `rewrite/wicket-striker-this_over-canonical` deleted local + remote.
**Status**: **WS-I ARC FULLY CLOSED.** Primary objective (γ-w-symbol UNIFIED-4 cohort closure on `validate_ws_h_step7`) CLOSED at step-2 via Shape B patch `a459713` (assertion-side trace-schema-precondition graceful-skip at `trace_session_assertions.py:335-346`). Gate-7 cross-fixture verified budget-neutrally across all 166 on-disk traces in `logs/trace/`: **REPLAY-cohort (49 traces, 0% `ui_after`) closed to 0 FAILs (49 latent schema-noise FAILs swept including the UNIFIED-4 cohort)** + **LIVE-cohort (117 traces, 100% `ui_after`) 17 FAILs PRESERVED across 15 fixtures** (C21 baseline FAIL × 2 on `validate_dckkr_20260521_155356` Rahul + Rana intact; 15 mixed live-cohort fixtures deferred to workstream D rotation-root / UI render-layer C21 case-by-case classification). **0 regressions, 0 new FAILs on live-pipeline traces** — cleanest signal-vs-noise separation the trace assertion library has produced. **WS-H ARC remains FULLY CLOSED** (P1 `ef0860d` + H1 `832d376` + Shape A `1dbba14` STAY LANDED — NO reverts). Empirical budget **2/5 remaining** (WS-I consumed 0/5 across 3-step arc — fully static + on-disk gate-7 re-count). Seven sub-findings landed across WS-H + WS-I: S16/S17/S18 (step-3/4) + S19 (step-5) + S20 (step-7/8) + S21 (step-5b) + S22 (WS-H step-9 arc-level meta-finding) + **S23 (WS-I step-3 — trace-schema heterogeneity as assertion-precondition; pairs with S21 as two-shape family Shape A canonical-resolution graceful-degrade + Shape B schema-precondition graceful-skip)**. **Candidate S24 noted (NOT yet promoted)**: arc length scales with fix-surface category — pipeline-side ~9 steps + 1/5 budget vs assertion-side ~3 steps + 0/5 budget; awaits 3rd-instance confirmation.

**§15 fence count correction.** Post-merge `grep -c 'self.striker = None' files/score_manager.py` returns **7**, not the "8" claimed in pre-merge HANDOFF/Architecture_HANDOFF copy. The discrepancy was an off-by-one descriptive shorthand carried from the original §15-arc docs; the structural fence invariant ("no non-canonical name writes") holds — non-None writes are exclusively from the three canonical methods (`apply_striker_event:945`, `apply_striker_identity_resolved:980`, `apply_striker_identity_proposed:1211/1213`).

**Next session's first action: WS-M step-2 patch authorization** (gated on WS-M step-1 investigation outcome — companion commit this session opens orphan-bind pipeline-plumbing audit on the 4 LIVE-FAIL cohort inherited from WS-L step-3). WS-L primary objective CLOSED at step-2 (`110026d`) + step-1b refinement (`394ed58`) — `trace_alpha_batter_runs_sum` discriminator shipped + downstream fix surface localized to `eyes.over_mgr.ABSORBED_LEGAL_handler` + PendingBall queue drain logic. WS-M fix surface category: pipeline-plumbing-required per S28; 1-2/5 budget cost expected at WS-M step-3 empirical validation. S28 PROMOTED to numbered insight (two-instance threshold met). F1017 phantom-wicket cohort REMAINS architectural-known-defect (Phase 2 KF Cricbuzz-corroboration deferral queue). S23-corollary + S23-extension Phase 4 catalogue items unchanged. S26-v2 candidate surfaces at WS-L step-1b (first-instance; awaits second). S27 + S25 candidates unchanged.

**Prior session context** (workstream D fix-chain, 2026-05-21): D1 (bowler em-dash sentinel) + D2-Layer-1a (broadcast-vs-deterministic dismissed-name) shipped as code; empirical validation gated on next DCKKR replay. See "## Session continuation — C26–C31" section below.

Entry point for next Cowork session. Read this file first, then `CLAUDE.md`, then `Architecture_HANDOFF.md`, then the design memos at:
- `files/docs/investigations/temporal_coupling_investigation_brief.md` (C10–C12.5b: the static-analysis methodology + cascade-root localization)
- `files/docs/investigations/c13_fc5_audit_memo.md` (the §7.2 7-gate audit on 4 shapes + Shape B selection)
- `files/docs/investigations/stream_gap_reconciliation_design.md` (B-η chain §1–§13: 5 empirical falsifications + investigation-strategy pivot)
- `files/docs/investigations/state_mutation_site_catalogue.md` (C9: 38 mutation sites + 2 async callbacks)
- `files/docs/investigations/dckkr_20260521_cc_investigation_brief.md` (the operator-side brief + §0 reframe)
- `files/docs/investigations/sm_as_orchestrator_design.md` §7 (the standing 7-gate audit framework) + §12 (dual-state-write defect-class catalogue — C17, cross-referenced from §12.7 to the new memo below)
- **`files/docs/investigations/surface_pair_defect_class_family.md`** (NEW C20: family-level instance catalogue, 9 placeholder rows from DCKKR replay, per-row populate deferred to C20b)
- **`validate_dckkr_replay_observations.md`** (21-frame observation log — entry data for workstream D)

## Session continuation — Workstream G lifecycle closure (2026-05-22 → 2026-05-23)

Workstream G chain closed at commit `50af67e` (Surface B cold-start lifecycle closure) + step-8 re-validation. 8-step arc spanning two days; 0/5 → 1/5 empirical-falsification budget consumed (preserved at 4/5 remaining). Lifecycle objective closed; primary objective (D-post-FoW-striker drop) deferred to Workstream H per insight #18 scope-separation.

### Workstream G commit ledger (steps 1–8)

| Step | Commit | Scope | Outcome |
|---|---|---|---|
| 1 | (docs) | Scout-extraction timing audit memo (`workstream_g_scout_extraction_timing.md`) — G1-G5 hypothesis enumeration; G2 broadcast-strip render lag surviving | F679→F708 (29 frames), F855→F892 (37 frames) static evidence; gates 1-5 falsified except G2 |
| 2 | (docs) | Shape A §7.2 audit (`workstream_g_shape_a_pending_cascade_audit.md`) — green-light + Mitigation A (capture pre-fallback pair) | All 7 gates PASS-WITH-MITIGATION; FIFO queue bounded at 3; TTL=80; Q1-Q5 answered |
| 3 | `f09fc38` | feat(workstream-g): Shape A pending-cascade scaffold + Mitigation A | `PendingCascade` dataclass + helper + 5 trace tags registered; L1.5 51 cases |
| 4 | `2ea930f` + `d4dd8ee` | test(L1.5): G-1/G-2/G-3 + trace_eta_post_wicket_cascade_drains assertion + DCKKR/GTRR baselines | trace assertion library 8 → 9; PASS trivially on pre-Shape-A traces (0 enqueues) |
| 5 | `5484cdb` | docs(workstream-g): step-5 validation addendum — Shape A drain falsified | Outcome 2; 0/5 → 1/5 empirical consumed; H-Vα + H-Vβ + H-Vδ co-survive; insight candidate #17 surfaced (gate-5 lifecycle empirical verification) |
| 6 | `cc21d03` + `4f14dee` | docs(workstream-g): transition-site catalogue + Surface A vs B audit (deliverables A + B) | Catalogue: 4 WARM→COLD + 6 COLD→WARM sites; Surface A red-light (3 gate failures); Surface B green-light for lifecycle closure |
| 7 | `50af67e` | feat(workstream-g): Surface B cold-start lifecycle closure (audit 4f14dee) | Helper `_wipe_pending_cascade_on_cold_entry`; W1-W4 wipe-emit sites; C1-C6 drain-trigger sites; L1.5 51 → 54 (G-4/G-5/G-6) |
| 8 | `324e788` | docs(workstream-g): step-8 validation + lifecycle closure | All four audit §5 predictions LANDED on `validate_surface_b_121222`; trace_eta PASS; insight #17 + #18 retrospectives |
| pre-merge | `29b239c` | chore(gitignore): expand to cover env noise pre-merge | Env-noise patterns added (worktrees/wrangler/_tmp/trace/machine logs/etc); real-WIP set preserved as untracked |
| merge | `5206885` | merge: rewrite/wicket-striker-this_over-canonical → derive-not-detect | --no-ff merge bringing 19 commits onto `derive-not-detect`; L1.5 54/54 + L2 30/30 + 9 trace assertions (trace_eta PASS); §15 fence verified canonical-only |
| post-merge docs | `22877c5` | docs(post-merge): HANDOFF + Architecture_HANDOFF status update | Header + ledger reflect merged state; §15 fence None-write count corrected 8→7 (descriptive shorthand was off-by-one; structural invariant holds) |
| WS-H step 1 | `9b2afc5` | docs(workstream-h): step-1 investigation memo — 4 hypotheses + S13/S14/S15 sub-findings | Static-falsification chain converges on P1 team-change-corroboration parity for `_detect_innings_change` wickets_regressed branch; empirical budget 4/5 unchanged |
| WS-H step 2 | `ef0860d` | feat(workstream-h): P1 — team-change-corroboration guard on _detect_innings_change wickets_regressed branch | Mirrors 2026-05-19 score_reset_from_progress hardening at `:4423`; new tag `WICKETS-REGRESS-TEAM-CHANGE-REQUIRED-REJECTED`; L1.5 54 → 60 cases (6 new in `test_innings_change_wickets_regressed_guard.py`); empirical budget 4/5 unchanged |
| WS-H step 3 | (validation — no code commit) | Empirical replay against captured-Scout dump | `validate_ws_h_step3_20260523_164642` (749 frames; single-independent-variable vs. `validate_surface_b_121222`): D-post-FoW-striker 20 → **2**; WIPED-BY-COLD-START 2 → **0**; DRAIN-FIRED 0 → **2** (F680, F858); γ-bowler-w FAIL×4 → **PASS** (composite-fix closure with D1); residuals 1× SM-INNINGS-2-RESET at F939 + 1× γ-fow-name FAIL at F679; budget 4/5 → **3/5** (load-bearing artifact: S16/S17/S18) |
| WS-H step 4 | `113b747` | docs(workstream-h): step-4 close-out — primary objective CLOSED (D-post-FoW-striker 20→2) + S16/S17/S18 sub-findings + step-5/5b openers | Memo §8-§12 appended; HANDOFF + Architecture_HANDOFF status; SESSION_CONTEXT entry for the validation trace |
| WS-H step 5 | `28d28b4` | docs(workstream-h): step-5 investigation memo — H1 derivation-site consensus gate + S19 cascade-closure-degeneracy sub-finding | 474-line static-falsification memo; 3 hypotheses (H1 leading; H3 falsified at gate 3; H2 inferior); S19 surfaced |
| WS-H step 6 | `832d376` | feat(workstream-h): H1 — _team_changed consensus-parity gate at _detect_innings_change derivation site | Single-line tightening at `:4417-4420` propagates to both consumers; L1.5 60 → 63 cases (H-7/H-8/H-9 + H-6 refactor in test_innings_change_wickets_regressed_guard.py); empirical budget 3/5 unchanged |
| WS-H step 7 | (validation — no code commit) | Empirical replay against captured-Scout dump | `validate_ws_h_step7_20260523_172140` (749 frames; single-independent-variable vs. step-3): F939 SM-INNINGS-2-RESET 1 → **0**; score_reset baseline 0 → **0** (S19 held); sibling deferrals 2 → 3 (S18 propagation); DRAIN-FIRED 2 → **4**; CASCADE-EXPIRED 0 → **1** (first observation); γ-bundle COHORT EXPOSURE (γ-fow-name FAIL 1 → 3 at F679/F948/F1017 reason=`no_prev_striker`; γ-w-symbol FAIL 2 → 4 at same wicket frames); budget 3/5 → **2/5** (load-bearing artifact: S20) |
| WS-H step 8 | `6d80c57` | docs(workstream-h): step-8 close-out — step-5 CLOSED (F939 → 0 + S18 dividend confirmed) + S20 cohort-exposure sub-finding + step-5b cohort extension | Root-cause memo §13-§15 appended; step-5 memo §11 appended; HANDOFF + Architecture_HANDOFF status; methodology insights 19 → 20 |
| WS-H step 5b | `031d221` | docs(workstream-h): step-5b investigation memo — H3 assertion-side fix surface + S21 assertion-expectation defect class + UNIFIED 3-frame cohort | 424-line static-falsification memo; 4 hypotheses (H3 leading; H1/H2/H4 falsified at gates 1-3); fix-surface attribution = assertion-side per §15-fence enumeration; S21 surfaced |
| WS-H step 5c | `1dbba14` | feat(workstream-h): H3 Shape A — γ-fow-name graceful-degradation on canonical-dismissed-resolution | Assertion-side patch at `trace_session_assertions.py:425-:454`; 4 new L1.5 cases (T-1/T-2/T-3/T-4 in test_gamma_fow_name_canonical_degradation.py); L1.5 63 → 67; gate-7 cross-fixture verified budget-neutrally across 13 traces (7 closures across 5 traces + 4 bonus pre-existing + 0 regressions); empirical budget 2/5 unchanged |
| WS-H step 9 | `f6cbcbd` | docs(workstream-h): step-9 arc close-out — WS-H fully retired (primary + step-5 + step-5b CLOSED) + S22 static-investigation-first protocol meta-finding | Root-cause memo §16-§17 appended (arc retrospective + S22); step-5b memo §12 appended; HANDOFF + Architecture_HANDOFF status; methodology insights 20 → 21; next-session retargeted to §11.3 surgical items 3-7 |
| WS-I step 1 | `efe7d20` | docs(workstream-i): step-1 investigation memo — UNIFIED-4 cohort + HA Shape B + S23 trace-schema-precondition sub-finding | 330-line static-falsification memo; 5 hypotheses (HA leading; HB/HC/HD/HE statically falsified at gate 1); fix-surface attribution = assertion-side via cross-fixture `ui_after` population audit (replay-cohort 0% / live-cohort 100%); HC C21 UI-layer Phase 3 escalation NOT triggered; S23 surfaced + S23 cross-assertion audit obligation declared; empirical budget 2/5 unchanged |
| WS-I step 2 | `a459713` | feat(workstream-i): I1 Shape B — γ-w-symbol trace-schema-precondition skip closes UNIFIED-4 cohort | Assertion-side patch at `trace_session_assertions.py:335-346`; 3 new L1.5 cases (T-1/T-2/T-3 in `test_gamma_w_symbol_schema_precondition.py`); L1.5 67 → 70; gate-7 cross-fixture verified budget-neutrally across 166 traces (REPLAY-cohort 49 → 0 FAILs full closure + LIVE-cohort 17 FAILs PRESERVED across 15 fixtures + 0 regressions); empirical budget 2/5 unchanged; S23 cross-assertion audit discharged inline (`_final_extras_total` flagged as S23-extension Phase 4 candidate; `assert_extras_total_consistent` already correct PASS-by-precondition pattern) |
| WS-I step 3 | `0a1b4d2` | docs(workstream-i): step-3 close-out — WS-I primary retired (UNIFIED-4 cohort closed + 49-trace bonus) + S23 schema-precondition family landed | WS-I memo §12-§15 appended (step-2 outcome + arc closure + S23 family canonical landing + arc-level meta-finding candidate S24); HANDOFF + Architecture_HANDOFF status; methodology insights 21 → 22; next-session retargeted to C29b Scout schema extension as Phase 1 second pillar; S23-corollary + S23-extension catalogued under Phase 4 (NOT opened as workstreams) |
| WS-C29b step 1 | `d40e2b9` | docs(workstream-c29b): step-1 static investigation — C29b FALSIFIED on source-modality blocker + cascade-closure misframing; recommend defer + re-select Phase 1 second pillar | 429-line static-falsification memo; 4 hypotheses falsified at gate 1 (HA + HB source-modality blocker — bottom-strip pixels don't render dismissed names; HC collapses to HE; HD multi-prompt orthogonal). Cascade-closure verification 0/3 targets close (surface E phantom-wicket / phantom-runs / WS-F bowler-misattribution all on different code paths). C29b strategic value collapses; recommend defer + re-select Phase 1 second pillar to Surface E. Candidate S25 (strategic-framing-vs-source-modality) surfaced — single instance. First fully-static workstream-level falsification on derive-not-detect lineage; zero budget consumed |
| WS-Surface-E step 1 | `b7089a8` | docs(workstream-surface-e): step-1 investigation memo — phantom-wicket cohort + HA' detection-predicate consensus + candidate S25 second-instance confirmation | 353-line static-falsification memo; cohort 1 confirmed F1017 + 1 candidate F1017-ghost (small-cohort scope); HA' N=3 consensus + overs-advance gate leading; HB/HC/HD/HE statically falsified. Candidate S25 gains second-instance confirmation. Gate 4 (false-negative risk on genuine cohort) flagged as LOAD-BEARING — static verification incomplete |
| WS-Surface-E step 2 | `65ef9c9` | feat(workstream-surface-e): E1 HA' — N=3 consensus + overs-advance gate + PHANTOM-WICKET-SUSPECT observability at ball_detector wicket predicate | HA' patch landed at ball_detector.py:96+ + PHANTOM-WICKET-SUSPECT tag registered in trace_emitter KNOWN_TAGS + 7 new L1.5 cases (test_phantom_wicket_consensus.py P-1 through P-7); L1.5 70 → 77. **SUBSEQUENTLY STATICALLY FALSIFIED** at step-2.5 (F1018=5 reading + HA' admits phantom at F1019) + step-2.6 (cricket-physics-gate Option Y falsified — OCR-noise envelope uniform across phantom + genuine cohort). Reverted at next commit |
| WS-Surface-E step 2 revert | `061c77d` | revert "feat(workstream-surface-e): E1 HA' — ..." | Full revert of 65ef9c9 per Option X-naked authorization. L1.5 77 → 70. Restores baseline pre-HA' functionality. Two-layer static falsification chain at memo §14 + §15 established detection-layer impossibility |
| WS-Surface-E retirement | `a4f91f5` | docs(workstream-surface-e): retirement close-out — phantom-wicket as architectural-known-defect + S26 promotion | Memo §13-§18 appended (step-2 outcome + step-2.5 F1018 falsification + step-2.6 cricket-physics-gate falsification + retirement declaration + S26 promotion + Phase 1 re-selection candidates); surface_pair §2.10 added (phantom-wicket-detection-class with F1017 anchor + architectural-known-defect framing); HANDOFF + Architecture_HANDOFF status; methodology insights 22 → 23 (S26 promoted); next-session retargeted to Phase 1 re-selection (§11.3 item 5 Recent-Overs partial-render recommended) |
| WS-K step 1 | `8f79b03` | docs(workstream-k): step-1 investigation memo — phantom-wicket state-machine cricket-physics; F1017 inherited from Surface E retirement | 323-line static-falsification memo; 5 candidates (KA at-crease-name-equality + KB striker-pointer-stability + KC at-crease-pair-change + KD bowler-tracker-consistency + KE bat-slot-churn) all statically falsified at gate 1 on F1017 phantom. KF Cricbuzz-corroboration survives gate 1 but fails gate 3 (Phase 2 architectural investment); KG cohort-split inapplicable on single-instance cohort. Architectural finding: OCR-noise-uniformity from Surface E §15 GENERALIZES to state-machine layer — every state-machine signal downstream of strip OCR via §15 canonical write-path fence. Surface E `a4f91f5` architectural-known-defect framing VALIDATED. S27 candidate surfaced (shared-signal-source structural barrier) — single instance. No WS-K step-2. Zero budget consumed |
| WS-K retirement | `df64e84` | docs(workstream-k): retirement close-out — universal-candidate-exhaustion + S27 candidate (shared-signal-source structural barrier) + KF Phase 2 deferral | Memo §12-§14 appended (retirement declaration + S27 candidate consolidation + future re-investigation prerequisites enumerated); surface_pair §2.10 updated (multi-layer convergent falsification cited; KF re-investigation prereqs catalogued); HANDOFF + Architecture_HANDOFF status; methodology insights 23 (unchanged — S27 stays candidate awaiting second instance). Next-session retargeted away from Recent-Overs (Phase 3 UI scope per HANDOFF line 725) to §11.3 item 4 (Per-batter-ledger conservation) OR WS-D §3.5 Layer 1a OR WS-F bowler-misattribution |
| WS-Recent-Overs step 1 | `e7c51b9` | docs(workstream-recent-overs): step-1 investigation memo — B-γ Recent Overs partial-render DEFERRED to Phase 3 UI scope per standing classification + ambiguous correspondence | 199-line deferral memo; HANDOFF line 725 standing classification confirmed; pipeline-side over_history anomaly cohort (OVER-ARCHIVE-INVALID-TOKEN-COUNT × 2-3 per fixture) exists but B-γ UI-correspondence unverified; HC (UI-render-layer-only per C21 pattern) recommended deferral pivot. Phase 4 catalogue candidate logged for trace_recent_overs_history_consistent assertion. No commits beyond deferral memo |
| WS-Per-Batter-Ledger step 1 | `eceac23` | docs(workstream-per-batter-ledger): step-1 investigation memo — assertion-side trace_alpha_batter_runs_sum addition; budget-neutral closure projected | 225-line static-falsification memo; pre-screen verdict GREEN-ASSERTION-SIDE per S28 candidate refinement; first Phase 1 second-pillar candidate to clear pre-screen without immediate deferral after three consecutive deferrals (C29b → Surface E+WS-K → Recent-Overs); HA leading + HB deferred + HC follow-up + HD partially falsified + HE disambiguated by HA outcome |
| WS-Per-Batter-Ledger step 2 | `110026d` | feat(workstream-per-batter-ledger): I2 — trace_alpha_batter_runs_sum assertion mirroring bowler-runs-sum + Shape B schema-precondition | Assertion + 5 L1.5 cases + on-disk gate-7 re-count. L1.5 70 → 75. Gate-7 cross-fixture: LIVE PASS×4 (2 sum-match + 2 coverage-skip) + LIVE FAIL×4 (validate_dckkr_20260521_070545 gap=12 + validate_dckkr_20260521_155356 gap=3 + validate_dckkr_20260522_063211 gap=3 + validate_20260513_194442 gap=1) + REPLAY SKIP×49. Cohort discriminator delivered. Zero budget consumed |
| WS-Per-Batter-Ledger step 3 | `d0e72b3` | docs(workstream-per-batter-ledger): step-3 close-out — primary CLOSED (assertion shipped + 4 LIVE-FAIL cohort discriminated) + WS-L HC opener | Memo §11-§14 appended (step-2 outcome + gate-7 cross-fixture full table + cohort discrimination + workstream primary CLOSED + S28-candidate-validated framing); HANDOFF + Architecture_HANDOFF status; methodology insights 23 (unchanged; S28 stays candidate); next-session retargeted to WS-L step-2 authorization decision |
| WS-L step 1 | `579b3d6` | docs(workstream-l): step-1 investigation memo — BAT-DELTA emission completeness audit; 4 LIVE-FAIL cohort inherited from WS-Per-Batter-Ledger | 273-line step-1 memo; pre-screen GREEN-ASSERTION-SIDE-INSTRUMENTATION; LA leading candidate + LB/LC/LD/LE statically falsified; 5 hypotheses; S28-candidate second-instance achieved (pending step-3 promotion) |
| WS-L step 2 | (no commit — STOP at verification) | feat(workstream-l): L1 — BAT-DELTA emission at 3 canonical batter-runs writer paths (DEFERRED) | Verification step 1-4 surfaced significant deviation from §3 enumeration: COLD_START_SYNTH already covered (:6367); compound-token subsumed in WIDE/NO_BALL branches (:6475-6502); ABSORBED_LEGAL forwarder lives in eyes.over_mgr (not score_manager). STOPPED per verification step 4 + S26 operational corollary; refinement deferred to step-1b |
| WS-L step 1b | `394ed58` | docs(workstream-l): step-1b refinement — §3 writer-path enumeration corrected via code-reading; leading candidate REVISED to LD-orphan (orphan-bind correctness gap); recommend Fork B retirement with measurement-quality reframing | Memo §11-§14 appended (code-reading evidence + ABSORBED-FORWARDED-ELSEWHERE forwarder localization + F138 diagnostic refinement showing PENDING-BALL-SLOT-BOUND-ORPHAN at WARM mode + reframed LD-orphan leading candidate + three-fork disposition); Fork B (retire with measurement-quality reframing) recommended; S26-v2 candidate surfaced (single-instance footprint) |
| WS-L step 3 | (this) | docs(workstream-l): step-3 close-out — primary CLOSED (assertion shipped + cohort discriminated) + S28 promotion + WS-M opener | Memo §15-§18 appended (Fork B retirement formalized + S28 promotion to numbered insight with two-instance evidence + S26-v2 candidate first-instance footprint + WS-M handoff); HANDOFF + Architecture_HANDOFF status; methodology insights 23 → 24 (S28 promoted); next-session retargeted to WS-M step-2 patch authorization |

### Step-8 re-validation evidence

Re-validation replay `logs/trace/validate_surface_b_121222.jsonl` against the same captured-Scout dump as step 5 (`files/logs/deliveries/validate_dckkr_20260521_155356/scout_raw.jsonl`). Single independent variable: `f09fc38` → `50af67e` code delta. Predicted lifecycle outcomes per audit §5:

```
POST-WICKET-CASCADE-ENQUEUED × 2
  F679 frame_set_at=679 reason=wicket_non_striker_stays dismissed=Nitish Rana    ✓
  F855 frame_set_at=855 reason=wicket_new_batter        dismissed=Pathum Nissanka ✓

POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START × 2
  F690 site=set_innings_2:wickets_regressed age=11 dismissed=Nitish Rana       ✓
  F859 site=set_innings_2:wickets_regressed age=4  dismissed=Pathum Nissanka   ✓

POST-WICKET-CASCADE-DRAIN-FIRED × 0    ✓
CASCADE-DRAIN-EXPIRED × 0              ✓

trace_eta_post_wicket_cascade_drains: PASS (orphan count 2 → 0)    ✓
```

Gate-bundle delta vs step-5 baseline (`validate_shape_a_114349`): single load-bearing flip — `trace_eta` FAIL × 2 orphans → PASS. All other 8 assertions identical (no regression). Gate-4 equivalence proof empirically verified.

**Insight #18 scope holds.** `STRIKER-EVENT-DISPATCHED` count unchanged at 19 (no new cascade-resolved rotations because wipes always fire before drain on this dump). D-post-FoW-striker surface count remains at 20. Workstream G primary objective remains open.

### Trace assertion library — substantive trace_eta baseline

Library count unchanged at 9. The `trace_eta_post_wicket_cascade_drains` row updates from "PASS trivially (pre-Shape-A; 0 enqueues)" to **substantive PASS × 2** on `validate_surface_b_121222`: 2 enqueues matched by 2 WIPED-BY-COLD-START terminals.

### Architectural fence — post-Workstream-G

The PendingCascade lifecycle now covers:

| Reset path | Trace tag | Coverage |
|---|---|---|
| `__init__` (constructor) | (none — pre-session) | Default-init only |
| `_clear_per_innings_sm_surface` direct call | `POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START` | f09fc38 path; observability via existing emit |
| `set_innings_2` pre-`__init__` (W4) | `POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START` site=set_innings_2:<reason> | 50af67e PRE-__init__ ordering — load-bearing per insight #17 |
| `force_cold_start_recalibration` (W3) | `POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START` site=force_cold_start_recalibration:<reason> | 50af67e |
| `_handle_warm` overs-regress (W1) | `POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START` site=_handle_warm_overs_regress | 50af67e |
| `_handle_warm` stale-reject (W2) | `POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START` site=_handle_warm_stale_reject | 50af67e |
| COLD→WARM (C1-C6) | (drain attempt; emits `POST-WICKET-CASCADE-DRAIN-FIRED` only when slot-diff resolves) | 50af67e; defense-in-depth no-op on step-8 dump |
| `apply_wicket_event` defer | `POST-WICKET-STRIKER-CASCADE-DEFERRED` + `POST-WICKET-CASCADE-ENQUEUED` | f09fc38 |
| Drain success | `POST-WICKET-CASCADE-DRAIN-FIRED` | f09fc38 |
| TTL expiry | `CASCADE-DRAIN-EXPIRED` | f09fc38 |

Insight #17 protocol applied: every cold-entry reset path is now empirically verified to emit a structured tag with the queue state captured before any wipe. Silent `__init__` default-inits (the step-5 falsification root) are eliminated as the dominant W4 wipe path now runs pre-`__init__`.

### Methodology track record — insights #17 and #18

**Insight #17 retrospective.** *Audit gate-5 lifecycle enumeration must empirically verify each reset path's trace observability before declaring the lifecycle closed.* Surfaced in step 5 when a green-light audit (7/7 gates + Mitigation A) was overturned by empirical evidence — the gate-5 enumeration identified the correct number of reset paths but mis-attributed which path the cold-start re-entry actually uses. Static analysis from `_clear_per_innings_sm_surface` callers led to a wipe-site assumption (`full_reset`) that did not match the dominant production path (`set_innings_2` → `__init__` re-run, which bypasses `_clear_per_innings_sm_surface`). First instance in the discipline of a green-light audit overturned by empirical falsification; the methodology insight is itself the load-bearing artifact of the 1/5 budget consumed.

**Insight #18 retrospective.** *A green-light audit can deliver lifecycle closure without delivering the original predicted-flip outcomes. Scope-separation discipline required.* Surfaced in step 6 audit §5 when Surface B was identified as gate-5-closing but predicted-flip-table-orthogonal. Empirically confirmed in step 8: `trace_eta` flips PASS as predicted; D-post-FoW-striker remains at 20 as predicted. The discipline now treats "lifecycle closure" and "primary-objective closure" as separable audit deliverables; surfaces declare scope explicitly; re-validation verifies only the scoped objective.

Running total: **18 transferable methodology insights** across 5 sessions on `derive-not-detect` lineage.

## §17.10 WS-L PRIMARY CLOSED (step-3 retrospective)

WS-L assertion-side primary objective CLOSED at step-2 (`110026d`) + step-1b refinement (`394ed58`). `trace_alpha_batter_runs_sum` permanent regression detector landed; cohort discriminator validated (4 LIVE-FAILs surfaced); downstream fix surface localized to `eyes.over_mgr.ABSORBED_LEGAL_handler` + PendingBall queue drain logic via step-1b code-reading. WS-M opens in companion commit this session as Phase 1 follow-on.

**Arc statistics.** 4 commits (step-1 `579b3d6` + step-2 `110026d` + step-1b `394ed58` + step-3 this) + companion WS-M step-1 opener. 0/5 empirical-budget consumed. L1.5 70 → 75 cases. 1 promoted methodology insight (S28) + 1 candidate (S26-v2) surfaced during arc.

**S28 PROMOTED to numbered insight (candidate → standing).** Pre-screen fix-surface-category before opening Phase 1 step-1 memos. Categories admitting Phase 1 scope: pipeline-direct / assertion-side / pipeline-plumbing-required. Categories NOT admitting: Scout-source / external-signal / UI-render. Two-instance evidence: WS-Per-Batter-Ledger step-1 + WS-L step-1 both cleared GREEN and shipped productive code. Operational corollary: where pre-screen RED, defer immediately without full step-1 cycle; where GREEN, proceed with explicit fix-surface attribution. Cost-benefit demonstrated: prevented 3-4 deferral cycles' worth of static-investigation waste (vs the prior C29b → Surface E+WS-K → Recent-Overs streak).

**S26-v2 candidate first-instance footprint.** Pre-step-N verification-1 should spot-check step-(N-1) UNVERIFIED markers via targeted code reads BEFORE proceeding with memo writing + verification commitment. WS-L step-2 verification caught §3 deviation at half-commit-cycle cost (~10 tool calls + STOP) vs ~5 tool calls if pre-step-2 audit had run. Awaits second-instance for promotion.

**Methodology insights running total: 23 → 24 (S28 promoted).** S26-v2 candidate (1 instance) + S27 (1 instance) + S25 (2 instances) + S24 (2 instances) all awaiting respective promotion thresholds.

**Phase 1 second-pillar slot disposition.** WS-L primary CLOSED + WS-M opens immediately (companion commit). The WS-Per-Batter-Ledger → WS-L → WS-M chain represents the first sustained Phase 1 second-pillar productive-work streak after the prior three-deferral pattern. S28 pre-screen methodology validated as the load-bearing process refinement enabling this streak.

Full retrospective in `files/docs/investigations/workstream_l_bat_delta_emission_completeness_investigation.md` §15-§18.

---

## §17.9 WS-Per-Batter-Ledger PRIMARY CLOSED (step-3 retrospective)

WS-Per-Batter-Ledger primary objective CLOSED at step-2 (`110026d`) — trace_alpha_batter_runs_sum cohort discriminator shipped. Step-3 (this commit) retires the workstream's primary objective and opens WS-L HC observability-completeness audit as Phase 1 follow-on.

**Arc statistics.**
- 3 steps + 3 commits (`eceac23` step-1 + `110026d` step-2 + this step-3 + companion WS-L step-1 opener in same session).
- 0/5 empirical-budget consumed across entire arc.
- L1.5 70 → 75 cases (5 new in `test_alpha_batter_runs_sum.py` — T-1 PASS / T-2 FAIL-mismatch / T-3 REPLAY-SKIP / T-4 coverage-floor-SKIP / T-5 extras-only-SKIP).
- Gate-7 cross-fixture: LIVE PASS×4 + LIVE FAIL×4 + REPLAY SKIP×49.
- 4 LIVE-FAIL cohort surfaced for WS-L HC observability-completeness audit (gaps: 12 + 3 + 3 + 1 runs).

**Cohort discrimination outcome.** First Phase 1 second-pillar arc to ship productive code post-WS-I. The discipline cost of three consecutive deferrals (C29b → Surface E + WS-K → Recent-Overs) was vindicated by the S28-candidate pre-screen methodology refinement, which enabled Per-Batter-Ledger to clear pre-screen on first attempt and deliver the cohort discriminator + 4 LIVE-FAIL cohort for downstream HC audit.

**S28 candidate (pre-screen-fix-surface-category) — single-instance validated.** Per-Batter-Ledger is the first-instance evidence that the gate-2-fix-surface-accessibility check works as designed. Promotion to numbered insight awaits second-instance confirmation — WS-L step-1 pre-screen clearing GREEN as assertion-side-instrumentation would be the second instance.

**Next-session pivot.** WS-L step-2 authorization decision gated on WS-L step-1 outcome. If WS-L step-1 confirms HC closes 3-of-4 or 4-of-4 LIVE-FAILs via emission-completeness extension, step-2 lands the BAT-DELTA emission additions (0/5 budget). If WS-L step-1 confirms the 12-run gap on `validate_dckkr_20260521_070545` is genuine correctness violation, HB pipeline-side gate authorized at WS-L step-3 (1-2/5 budget).

Full retrospective in `files/docs/investigations/workstream_per_batter_ledger_conservation_investigation.md` §11-§14.

---

## §17.8 WS-K RETIRED AT UNIVERSAL-CANDIDATE-EXHAUSTION (retirement retrospective)

WS-K state-machine layer investigation opened to test whether F1017 phantom-wicket could be discriminated at a layer downstream of detection (Surface E). Static-falsification chain at step-1 (commit `8f79b03`) revealed: **state-machine layer signals are downstream of strip OCR via the §15 canonical write-path fence; the OCR-noise-uniformity finding from Surface E §15 GENERALIZES upward.** All 5 within-Phase-1-scope candidates (KA / KB / KC / KD / KE) statically falsified at gate 1. KF (Cricbuzz-commentary external corroboration) survives gate 1 (external signal IS discriminating) but fails gate 3 (Phase 2 architectural-pivot investment — `files/scripts/ingest_cricbuzz_ground_truth.py` already ingests for post-hoc regression but real-time wiring requires new latency-tolerance + failure-mode + cost-commitment architecture). KG (cohort-split) inapplicable on single-instance cohort.

**Multi-layer convergent falsification CONFIRMS F1017 as architectural-known-defect at every pipeline-internal layer.** Surface E `a4f91f5` retirement framing VALIDATED by WS-K step-1 outcome.

**Arc statistics.**
- 2 steps (step-1 investigation + retirement docs).
- 0/5 empirical-budget consumed.
- 2 commits (`8f79b03` step-1 memo + this retirement docs).
- Cost: one static-investigation cycle.
- Returns: (1) confirmation that F1017 is structurally undiscriminable at state-machine layer, (2) S27 candidate surfaced as transferable methodology insight.

**S27 candidate — Shared-signal-source structural barrier (single instance — NOT yet promoted).** When sequential investigation layers all derive their signals from a shared upstream source, falsifications at any layer propagate upward into all downstream layers. The "multi-frame resilience" / "downstream filtering" / "cross-component reconciliation" framing of higher layers is illusory at the discriminator level — every signal is ultimately bounded by the upstream source's discriminative capacity. The structural barrier is the shared source itself; investigation layers cannot exceed its discriminative ceiling. **Distinction from S26 (process-level peer):** S26 describes the discipline (more static layers → higher confidence); S27 describes the structural cause (shared-source convergence). Single-instance evidence (this step); awaits second-instance confirmation before promotion.

**KF Cricbuzz-corroboration Phase 2 architectural-pivot deferral queue.** Re-opening prerequisites: (1) phantom-wicket cohort grows beyond 1-confirmed via natural production accumulation, OR (2) independent strategic justification surfaces for real-time Cricbuzz commentary integration, OR (3) new Scout primitive emerges that provides discriminating signal NOT downstream of strip OCR. Defer until at least one prerequisite triggers.

**Phase 1 second-pillar re-selection (refined per HANDOFF line 725 standing classification).** Recent-Overs / B-γ classified as Phase 3 UI render layer scope, NOT pipeline. Phase 1 candidates narrow to: §11.3 item 4 (Per-batter-ledger conservation) OR WS-D §3.5 Layer 1a (HE survivor from C29b — pipeline-side, S12 plumbing concern) OR WS-F bowler-misattribution. Recommend opening §11.3 item 4 step-1 investigation memo at next session.

Full retrospective in `files/docs/investigations/workstream_k_phantom_wicket_state_machine_investigation.md` §12-§14.

---

## §17.7 WS-Surface-E RETIRED WITHOUT UI CLOSURE (retirement retrospective)

WS-Surface-E retires without UI closure delivered. F1017 phantom-wicket on `validate_dckkr_20260521_155356` remains as architectural-known-defect catalogued at `surface_pair_defect_class_family.md` §2.10. The architectural finding is the load-bearing artifact: **OCR-noise envelope around wicket events is uniform across phantom and genuine cohort**, making detection-layer discrimination structurally impossible within the current Scout primitive set.

**Arc statistics.**
- 5 steps (step-1 investigation + step-2 patch + step-2.5 falsification + step-2.6 falsification + retirement).
- 3 commits + 1 revert (`b7089a8` step-1 memo + `65ef9c9` HA' patch + `061c77d` revert + this retirement docs).
- 0/5 empirical-budget consumed — entire arc was static + on-disk inspection.
- 1 confirmed phantom + 1 candidate (small-cohort scope; not Phase 1 second-pillar weight).
- F1017 cohort: ZERO closure delivered.

**Two-layer pre-empirical falsification chain (zero budget cost).**
- Step-2.5: F1018=5 reading from `files/logs/deliveries/validate_dckkr_20260521_155356/scout_raw.jsonl` confirmed 3-frame persistent OCR jump (F1017+F1018+F1019 all = 5) + overs-advance satisfied at F1017 (10.4→10.5). HA' simulation showed phantom ADMITS at F1019 (closure falsified).
- Step-2.6: Cricket-physics-gate (Option Y) verified across genuine cohort — Rana F679 has prior regression F673 wkts=3→1, Nissanka F855 has prior regression F853 wkts=8→2. OCR-noise envelope identical to phantom F1015 wkts=6→F1016 wkts=4. **Gate cannot discriminate.**

**S26 promotion — static-investigation-rounds compound.** Three-instance evidence (C29b step-1 source-modality falsification + Surface E step-2.5 HA' falsification + Surface E step-2.6 cricket-physics-gate falsification). Promoted from candidate to numbered methodology insight. Canonical statement: each layer of static analysis can falsify the prior layer's strategic framing; more static layers → more falsification of intermediate claims → higher confidence in surviving conclusions. **Operational corollary: "gate-4 incomplete = STOP, do not proceed to patch-and-verify-empirically-later."** S22 (static-investigation-first across multi-step arcs) is the workstream-scope insight; S26 is the per-layer corollary at intra-workstream scope.

**Methodology insights running total: 22 → 23 (S26 promoted).** S25 (strategic-framing-vs-source-modality) remains a candidate at 2 instances (C29b + Surface E step-1 cohort sizing).

**Future re-investigation prerequisites for F1017 closure.** None of these are in Phase 1 scope. Phase 1 second-pillar slot re-opens for re-selection — **recommended: §11.3 item 5 (Recent-Overs partial-render)** as possibly assertion-side per WS-I pattern reuse.

Full retrospective in `files/docs/investigations/workstream_surface_e_phantom_wicket_investigation.md` §13-§18.

---

## §17.6 WS-I ARC FULLY CLOSED (step-3 retrospective)

WS-I primary objective CLOSED at step-2 (γ-w-symbol UNIFIED-4 cohort closure on `validate_ws_h_step7_20260523_172140` — F679 Pathum Nissanka + F855 Nitish Rana + F948 KL Rahul + F1017 Pathum Nissanka — all retired via Shape B schema-precondition graceful-skip at `a459713`). **49 latent FAILs swept across the entire on-disk replay-cohort** (38 `replay_dckkr_*` + 1 `replay_gtrr_*` + 2 `validate_shape_a_*` + 1 `validate_surface_b_*` + 1 `validate_ws_h_step3` + 1 `validate_ws_h_step7` + 5 `replay_dckkr_*` step variants). **17 LIVE-cohort FAILs preserved across 15 fixtures** including C21 baseline FAIL × 2 on `validate_dckkr_20260521_155356` (Rahul ov 5.0 + Rana ov 8.0). **0 regressions** — cleanest signal-vs-noise separation the trace assertion library has produced. **No WS-I follow-on workstream open.** Two diagnostic refinements catalogued under Phase 4 architectural cleanup (S23-corollary multi-wicket-per-frame undercount at `trace_session_assertions.py:308` + S23-extension `_final_extras_total` silent-stricter-bound at `:89-95`) — NOT opened as workstreams. Next session: **C29b Scout schema extension** as Phase 1 second pillar (cascade-closure target: surface E phantom-wicket + phantom-runs + WS-F bowler-misattribution dividends).

**Arc statistics.**
- 3 steps (memo + patch + close-out — the structurally minimum arc length for an assertion-side workstream).
- 1 patch (Shape B at `a459713`).
- 3 commits (`efe7d20`, `a459713`, this).
- 0/5 empirical-budget consumption across the entire arc.
- 49 latent FAILs swept (replay-cohort retirement).
- 17 live-cohort FAILs preserved (discriminative power intact).
- 22 cumulative methodology insights on `derive-not-detect` lineage post-S23.

**S21 + S23 two-shape family canonical landing.** Two assertion-side fix shapes now established as peer disciplines alongside the §15 pipeline-side canonical write-path fence:
- **Shape A (S21, WS-H step-5c, `1dbba14`):** Canonical-resolution graceful-degrade. When the assertion's expected reconstruction path is invalidated mid-frame (cascade-drain wipes prev_striker), graceful-degrade by reading the canonical alternate source.
- **Shape B (S23, WS-I step-2, `a459713`):** Schema-precondition graceful-skip. When the assertion's read-surface schema is not populated by the trace producer (replay-cohort), skip the predicate; do not fail on degenerate-default data.

Both preserve discriminative power on live-path data and retire false-positives via on-disk gate-7 re-count (zero empirical-budget cost).

**Candidate S24 — fix-surface category drives arc length.** NOT yet promoted to numbered methodology insight. Two confirmed instances (WS-H pipeline-side 9 steps + 1/5 budget; WS-I assertion-side 3 steps + 0/5 budget) suggest arc length scales with fix-surface category. Awaits 3rd-instance confirmation (e.g., a future Phase 4 S23-corollary or S23-extension patch landing as a small assertion-side arc would empirically establish the pattern).

**Cross-arc retroactive closures.** None. WS-I scope was structurally distinct from prior workstreams.

Full retrospective in `files/docs/investigations/workstream_i_gamma_w_symbol_cohort_investigation.md` §12-§15. Do not re-enter on WS-I surfaces.

---

## §17.5 WS-H ARC FULLY CLOSED (step-9 retrospective)

WS-H primary objective CLOSED at step-4 (D-post-FoW-striker 20 → 2). Step-5 CLOSED at step-8 (F939 SM-INNINGS-2-RESET 1 → 0). Step-5b CLOSED at step-9 (γ-fow-name cohort F679+F948+F1017 + 4 bonus pre-existing across historical traces — all closed via Shape A graceful-degrade at `1dbba14`). **No WS-H follow-on workstream open.** Next session: §11.3 surgical items 3-7. Original entry data preserved below for arc continuity; do not re-enter on WS-H surfaces.

### §17.5.1 WS-H step-5 — CLOSED (retrospective)

Original entry data (S16 surface) → H1 patch landed at `832d376` (step-6) → step-7 empirical replay on `validate_ws_h_step7_20260523_172140` confirmed F939 closure + S18 dividend + S19 degeneracy. Budget 3/5 → 2/5 consumed via γ-bundle cohort exposure (per S20 — cohort REVEALED, not INTRODUCED; promoted step-5b empirical anchor from 1 to 3 frames). Full retrospective in `workstream_h_cold_start_reentry_root_cause.md` §13 + `workstream_h_step5_team_changed_consensus_parity.md` §11. Do not re-enter on this objective.

### §17.5.2 WS-H step-5b — γ-bundle cohort drain-awareness (S17 + S20 surface)

**Objective.** Make γ-fow-name prev_striker resolution drain-aware so cascade DRAIN-FIRED at the wicket-commit window does not invalidate the assertion's reconstruction.

**Empirical anchor.** 1× `trace_gamma_fow_name_matches_striker_at_wicket` FAIL at F679 (reason=`no_prev_striker`) on the same trace.

**Sites.** γ-fow-name assertion in `files/tests/trace_session_assertions.py` (prev_striker reconstruction path — exact location TBD via step-5b static analysis); likely also prev_striker tracking in the `SmDispatchSummary` / `WicketEvent` chain.

**Objective.** Make γ-fow-name prev_striker resolution drain-aware so cascade DRAIN-FIRED at the wicket-commit window does not invalidate the assertion's reconstruction. Scope extended from 1-frame to **3-frame cohort** per step-7 cohort-exposure (S20): all three instances share root reason=`no_prev_striker`.

**Empirical anchor (cohort).** 3× `trace_gamma_fow_name_matches_striker_at_wicket` FAIL on `logs/trace/validate_ws_h_step7_20260523_172140.jsonl`:
- F679 — dismissed=Pathum Nissanka, prev_frame=678, reason=`no_prev_striker` (original S17 anchor; pre-H1 visible).
- F948 — dismissed=KL Rahul, prev_frame=947, reason=`no_prev_striker` (new post-H1; previously masked by F939 reset).
- F1017 — dismissed=Pathum Nissanka, prev_frame=1016, reason=`no_prev_striker` (new post-H1; same masking root).

Plus 4× `trace_gamma_w_symbol_at_wicket` FAIL at the same wicket-commit frames (F679, F855, F948, F1017) — these are the same wicket events failing two different γ-bundle sub-assertions. Cohort is 3 wicket-commit frames each failing both checks.

**Sites.** γ-fow-name assertion in `files/tests/trace_session_assertions.py` (prev_striker reconstruction path — exact location TBD via step-5b static analysis); likely also prev_striker tracking in the `SmDispatchSummary` / `WicketEvent` chain. γ-w-symbol assertion in the same file is a parallel surface — investigate whether one fix closes both.

**Reading list.**
1. `files/docs/investigations/workstream_h_cold_start_reentry_root_cause.md` §9.2 + §10 S17 + §13.2 + §14 S20.
2. `files/docs/investigations/workstream_h_step5_team_changed_consensus_parity.md` §11.4 (cohort context).
3. `workstream_g_cold_drain_surface_audit.md` §3 (lifecycle table).

**Predicted-flip framing.** γ-fow-name FAIL: 3 → 0 (cohort closure); γ-w-symbol FAIL: 4 → 2 (closes F948 + F1017 if shared root with γ-fow-name; F679 + F855 may persist as separate defect class). No other regression expected across the assertion library.

**Discipline.** Per WS-H step-1 precedent: static investigation memo FIRST; do not commit empirical replay until static-falsification chain converges. Per S20: expect cohort-growth predictions in any further lifecycle-enabling fix landed before step-5b closes.

### §17.5.3 Sequencing note

Step-5b is now the only remaining WS-H follow-on (step-5 closed at step-8). Cohort scope makes it higher-leverage than the single-frame original — 3 instances of the same defect class, two new ones (F948, F1017) confirmed via S20 cohort-exposure pattern.

## §17.4 Workstream H entry data (CLOSED — WS-H step-1 through step-4 complete)

**Closure note (2026-05-23, WS-H step-4).** Original §17.4 entry data drove WS-H step-1 (memo at `9b2afc5`) → step-2 patch P1 (`ef0860d`) → step-3 empirical validation (D-post-FoW-striker 20 → 2; budget 4/5 → 3/5; load-bearing artifact S16/S17/S18) → step-4 docs close-out (this commit). Primary objective CLOSED. Two follow-on workstreams open per §17.5. The original entry data preserved below for reference; do not re-enter on this objective.

---

**Objective.** Localize the cold-start re-entry frequency root cause and propose a fix for the `_detect_innings_change` predicate's handling of `wickets_regressed` triggers during the post-wicket hot window.

**Empirical anchor.** `logs/trace/validate_surface_b_121222.jsonl` shows 5× `SM-INNINGS-2-RESET reason=wickets_regressed` at frames F462, F690, F801, F859, F992 across a 749-frame replay. Each is triggered by `_detect_innings_change` at `score_manager.py:3578` (call site) / `:4307` (predicate body). The predicate is reading a wicket-counter regression as innings-2 transition; in the regime the catalogue documented, this is a Scout-misread artifact, not a legitimate innings boundary.

**Reading list (sequence).**

1. `files/docs/investigations/workstream_g_cold_start_transition_catalogue.md` §5 — Item 1 ↔ Item 2 ↔ Item 3 coupling analysis.
2. `files/docs/investigations/workstream_g_shape_a_validation_addendum.md` §4 — recommended sequence for Workstream H.
3. `files/docs/investigations/workstream_g_cold_drain_surface_audit.md` §4.1 — scope-separation rationale.
4. `differential_testing_methodology_design.md` §14.5.2 — COLD-START-EXIT semantics redesign discussion.

**Entry sites.**

- `_detect_innings_change` predicate body at `files/score_manager.py:4307` — the `wickets_regressed` branch.
- `set_innings_2` callers + their `reason` parameter at `:4427+` — five call sites in `_accept_update`, `_update_misc`, `_update_supplements`, `_handle_innings_change` per the docstring at `:4432-4441`.
- Step-5 finding: cold-start re-entry violates the `§16.2` "once per pipeline boot" assumption (`differential_testing_methodology_design.md` §16.2). The assumption is documented as retired in §17.3 Item 2 and is the natural target for the COLD-START-EXIT tag bifurcation work.

**Predicted-flip framing for Workstream H.** If the `_detect_innings_change` predicate is tightened to reject `wickets_regressed` triggers within an N-frame post-wicket hot window:

- `SM-INNINGS-2-RESET reason=wickets_regressed` count: 5 → ≤2 (only legitimate innings transitions remain).
- `POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START` count: 2 → 0 (cascade survives past F690 and F859).
- Cascade drains on COLD→WARM at C5 (`COLD-START-FORCED-RECOVER`) instances OR via the existing warm-side drain hook if SM stays WARM long enough for bat slots to refresh.
- `POST-WICKET-CASCADE-DRAIN-FIRED` count: 0 → ≥1 (provisional; depends on bat-slot resolution timing).
- `D-post-FoW-striker` surface count: 20 → drops materially (target: per the original step-2 audit §5 prediction, 5–10).

**Budget.** 4/5 empirical-falsification slots remaining. Workstream H's first empirical replay will consume 1/5 if the predicted predicate-tightening doesn't deliver the cold-start re-entry reduction. Conservative discipline: open Workstream H as static investigation first; do not commit empirical replay until a static-falsification chain converges on a candidate predicate change.

**Do NOT in Workstream H:**

- Reopen Surface A (red-lighted on gate 3 / gate 5 / gate 6 in step 6 audit).
- Adjust TTL=80, Mitigation A capture site, or any audit-locked Shape A parameter.
- Touch the W1-W4 wipe-emit sites or C1-C6 drain-trigger sites unless Workstream H's static analysis surfaces a defect in the catalogue's per-site classification.
- Open the Workstream H investigation in this session — that's a fresh-session entry point. The close-out commit positions H without starting it.

## Session continuation — §15 triple-subsystem rewrite arc (2026-05-22 evening, prior session)

§15 arc structurally complete at commit (8/N) `1af2bd9`. Branch `obs/silent-wicket-absorption` carries 9 commits (8 §15 + this docs). Full retrospective in `files/docs/investigations/differential_testing_methodology_design.md` §17; summary below.

### What §15 accomplished (commits 1/N–8/N)

| # | Commit | Scope | Outcome |
|---|---|---|---|
| 1/N | `4b30503` | obs(workstream-i): SILENT-WICKET-ABSORPTION trace tag + Surface I classifier + differential-testing harness bring-up | 15-surface coverage on DCKKR dump; Surface I detects 2 instances (Rahul 4.6, Stubbs 10.5) |
| 2/N | `dc9d580` | feat(derivation): pure functions + canonical commit paths for wicket/striker/this_over (no call-site changes) | New module `files/score_manager_derivation.py` (~340 LOC); 37 unit tests green |
| 3/N | `f233217` | feat(_apply_event wire-through): this_over token → apply_this_over_token (step 5 partial) | Striker wire-through deferred to 7a (atomic-pair contract); wicket wire-through deferred to 7b |
| 4/N | `531d6f8` | feat(B-2 + Rule 1): StrikerEvent atomic pair + post-wicket cold-start guard | derive_striker_event Rule 1 tightened (post-wicket striker=None doesn't trigger cold-start re-seed) |
| 5/N | `7e63373` | feat(7a): striker ROTATION consolidation through apply_striker_event | `:6341-6343` inline swap replaced with apply_striker_event; +2 boundary regression at over_ball 8.5 documented as ROTATION ↔ IDENTITY race (§13.8 entry point) |
| 6/N | `6d1f0cd` | feat(7c): identity-resolution canonical path + early-return fix | apply_striker_identity_resolved per §13.8; `_set_slot_pair` routed through it; +2 regression closed |
| 7/N | `68acda4` | feat(7b): apply_wicket_event subsumes _apply_wicket_fall_only FoW + bowler-W | **Bowler-W-credit-failure 7 → 1 (-6)**; F-A 50→49 (-1); F-B 27→23 (-4); `_last_bowler_at_wicket_commit` sibling field |
| 8/N | `2ad432f` | feat(9): apply_striker_identity_proposed — third canonical striker path | _identify_and_set override at `:4700-4736` replaced; 88× STRIKER-IDENTITY-PROPOSAL-REFUSED fires confirm semantic preserved |
| 9/N | `1af2bd9` | feat(8): post-wicket striker cascade wired into apply_wicket_event | Cascade structurally wired; 100% defer rate in DCKKR dump (Scout new_batter primitive lag — Workstream G adjacent signal) |

### What §15 did NOT accomplish (and why)

§14.5 step 11 cold-start no-backfill attempted (commit 9/N candidate) and **reverted** — empirically falsified on this dump:
- **C21b at 10.5 still fires** — root cause is Scout-extraction timing at wicket-commit, not cold-start synthesizer.
- **Multi-ball-compression stays at 4** — driven by per-event this_over delta logic, not cold-start backfill.
- **D-post-FoW-striker stays at 20** — cascade structurally wired but 100% deferred in dump due to Scout-new-batter-read lag.
- **Surface count: 14 → 14 net.** Structural cleanup is real; empirical-drop-on-this-dump is not.

The predicted drops await **Workstream G** (Scout-extraction timing + cold-start re-entry frequency). Live-replay validation per §10.4 still mandatory.

### Architectural fence (post-§15)

Three canonical write paths for `self.striker`:
1. `apply_striker_event` (rotation per §13/§13.3)
2. `apply_striker_identity_resolved` (authoritative identity per §13.8)
3. `apply_striker_identity_proposed` (conservative-refuse per §13.8.1)

All 8 remaining `self.striker = None` writes are invalidation-only (cold-start invalidation / innings reset / NAME-REJECTED). No non-canonical name writes remain.

Canonical wicket dispatch path: `apply_wicket_event` is sole FoW + bowler-W writer. `_apply_wicket_fall_only` retained as thin shim; full deletion deferred until partnership/slot-clearing have canonical paths.

Deterministic-rotation override at `score_manager.py:4700-4736` (was at `:4295-4325` pre-7c line range) **REMOVED** — replaced by `apply_striker_identity_proposed`. The S12 non-discriminable-predicate-signature defect (C30b) surface eliminated.

### Test infrastructure

- `files/score_manager_derivation.py` — pure derivation module (~480 LOC, 3 derive functions + 4 dataclasses + 1 helper + 1 exception).
- `files/tests/test_score_manager_derivation.py` — 48 unit tests across 3 classes covering happy paths + every §12.2/§13.6/§13.8/§14.7 edge case named in the spec.
- `files/scripts/replay_diff_harness.py` — 15-surface classifier (Silent-wicket-absorption added in commit 1/N; C21b-symbol-revert added by snapshot extension + classifier in 5b.4).
- `files/scripts/ingest_cricbuzz_ground_truth.py` — dual-mode (curated ledger + Cricbuzz commentary), 122 events for full DC innings.
- `files/scripts/replay_captured_scout_trace.py` — extended with `--snapshot-output` flag, wicket-dispatch + mutation triggers, FoW key/overs normalization, `_last_bowler_at_wicket_commit` sibling-field fallback.

### Workstream G investigation queue (next session)

Per §17.3 — promoted from §11.3 item #2 to item #1:

1. **Scout extraction timing at wicket-commit frames.** Cascade defer rate 100% in DCKKR dump (2/2). Candidates: extraction cadence too low / broadcast-strip render lag / VLM prompt not asking for new-batter / lock-mechanism gating identity reads.
2. **Cold-start re-entry frequency root cause.** 12 COLD-START-EXIT fires in dump (6+ re-entries) vs the "once per pipeline boot" assumption in §16.2.
3. **COLD-START-EXIT semantics redesign** per §14.5.2 — bifurcate tags or treat all cold-start as benign.
4. **§14.5 step 11 retry** AFTER 1+2+3 close.
5. **C21b + Multi-ball-compression + D-post-FoW-striker validation** — predicted drops materialize once Workstream G closes upstream signals.

---

## Session continuation — C19–C24 (workstream B closure)

This session ran 2026-05-21 post-C18. Eight commits landed
(C19A1/A3/A4/A5, C20, C21, C22, C23). Session opened with operational
validation of the C14 Shape B fix and closes with workstream B's
wicket-correctness γ-bundle landed at empirical baseline.

### Validation gate result — DCKKR 2026-05-21 (validate_dckkr_20260521_155356)

Two distinct CROSS-FIELD-PAIRING-REJECT events fired in production
during the validation replay (~58 min wall time, ov 0.0 → 11.5):

- **F210** at 16:06:35 — Δscore=+6 / Δballs=-8 (backwards-overs
  cross-field; proposed 28-0(1.3) vs current 22-0(2.5))
- **F1015** at 16:47:14 — Δscore=0 / Δballs=0 / Δwkts=+2
  (zero-time double-wicket; proposed 89-6(10.4) vs current 89-4(10.4))

C14 Shape B predicate is doing load-bearing work — caught two
orthogonal Shape-B-class defects (backwards-overs + zero-time
double-wicket). The F-η-pattern (forward Δscore=+5, Δballs=+10) did
NOT surface in this replay window; the gate caught different defect
classes than its design memo emphasized. C14 sign-off accepted on
"predicate is correct, gate position is correct, gate is reachable
via apply_scorer_decision call site" basis.

Three trace-emission gaps surfaced during validation diagnostics:
- DIRECT-SCORE-COMMIT emissions = 0 (BOARD-side path not exercised)
- trace_beta_sm_wicket_dispatch tag absent from codebase (deleted
  between C15 authoring and HEAD)
- No typed wicket-event trace tags emitted

All three addressed in C19A1–A5 (counterfactual framing tightened on
the legitimate_pair comment, trace_beta restored at
_apply_wicket_fall_only, trace schema note added to operations doc,
preflight tag-existence check added as a launch-checklist step).

### Gate bundle baseline (validate_dckkr_20260521_155356)

```
4 trace_beta_sm_wicket_dispatch emissions detected via
  ball_event.type == "WICKET" fallback (captured trace pre-dates
  C19A3's typed emission landing).

trace_gamma_w_symbol_at_wicket:                 FAIL × 2  (Rahul, Rana)
trace_gamma_fow_name_matches_striker_at_wicket: PASS      (internal-consistency only)
trace_gamma_bowler_w_increment_on_dispatch:     FAIL × 4
```

Total: **5 PASS / 3 FAIL across 8 assertions** (3 existing + 3 new γ
+ 2 reused existing as gate-bundle members). Detection in the new
assertions uses fallback paths for the pre-C19A3 captured trace;
future replays will exercise the C19A3 typed emission path.

### Three forcing-function findings — skeleton-then-assertion methodology

- **C21 — Nissanka W→· revert is UI-layer, not state-layer
  (refines §2.1).** The trace's `ui_after.this_over` preserved W
  correctly at frame 855 position 4 in `next_this_over[4:]`. The UI
  revert observed at Obs 17b happens downstream of trace emission, in
  the WebSocket-render layer. The §2.1 surface-pair scope therefore
  splits: Surface B canonical (pipeline state, holds) vs Surface A
  weaker (UI render path, reverts) — not within the pipeline state
  itself. (Distinct from Obs 4 / Obs 11 reverts which ARE in trace
  state — those remain in §2.1 proper.)
- **C22 — both surfaces stale at same striker pointer value
  (refines §2.5).** `trace_gamma_fow_name_matches_striker_at_wicket`
  PASS × all detected wickets — pipeline-internal consistency holds
  even though cricket reality diverged 3/3 times per Obs 16/18/19/21.
  Rotation-lock-starvation corrupts both adjacent surfaces
  (`ball_event.striker_this_ball` at wicket frame N AND
  `pipeline.striker` at frame N-1) at the SAME stale value.
  Cricket-vs-pipeline divergence requires ground-truth assertion
  infrastructure outside the trace data — scoped as workstream D.
- **C23 — bowler identity = em-dash sentinel at 2/3 captured wicket frames
  (refines §2.6).** At wicket frames the pipeline's
  `current_bowler` often reads as the literal `—` placeholder
  (frame 400 Rahul, frame 679 Rana). Only frame 855 (Nissanka)
  resolved a real bowler name (`Sunil Narine`). The
  rotation-lock-starvation root therefore extends to BOWLER identity,
  not just batter-striker. Surfaced via the assertion's FAIL output
  itself — would not have been visible from the observation log alone.

### Workstream D — promoted to highest-impact unblocked workstream

**Original framing** (per the C19/B2 scope note): D = rotation-root
revisit (batter-striker pointer staleness causing FOW name swap per
Obs 16/18/19/21).

**Expanded scope after C22 + C23 findings:** D now encompasses
- Batter-striker pointer staleness at wicket frames (original scope)
- Bowler identity unresolved (em-dash sentinel) at wicket frames (new)
- Both share the same upstream root — rotation-lock fires on neither
  pointer at wicket-event boundaries.

**C23b (bowler-W fix) is BLOCKED on D.** Adding `update_bowler` at
the wicket-dispatch path would credit an em-dash entry in 2/3 of
captured cases — worse than no credit (pollutes bowler-card
namespace with a sentinel). The bowler-identity-resolution defect
must close before C23b can land cleanly.

Workstream D's entry data:
- `files/logs/deliveries/validate_dckkr_20260521_155356/` — full
  captured artifact (trace JSONL, pipeline.log, scout dump, mp4)
- `validate_dckkr_replay_observations.md` — 21-frame replay log
- C19A3's `trace_beta_sm_wicket_dispatch.resolution_src` payload
  discriminates P2 (event.dismissed) vs P3 (SM.self.striker fallback)
  attribution paths — informs root localization
- `files/docs/investigations/state_mutation_site_catalogue.md` (C9)
  — candidate sites for bowler-identity-lock failures

### Methodology track record — 7 transferable insights across 3 sessions

The discipline's insight-accumulation rate is itself load-bearing.
Four insights from prior sessions; three new this session:

**Prior sessions:**
1. **F1 cascade-closure pattern** — one-edit fix can close N bug
   classes (F1 session).
2. **Predicate-trail / static-analysis methodology** — full
   cascade-root localization at near-zero commit cost (B-η session).
3. **Commit-design drift** — design memos can predict FAIL→PASS
   flips on tags that have been deleted between memo-authoring and
   HEAD; pre-validation tag-existence check needed. C19A5 delivers
   the preflight check; the meta-finding was the C14 validation's
   trace_beta-absent surprise.
4. **Budget-class mismatch in brief authoring** — code sub-tasks
   fit 5-call budgets; memo/comparative-analysis sub-tasks need
   8–12. Brief authoring needs to differentiate; this session's
   Phase 1 split into 1a/1b after the budget exceeded.

**New (this session, C19–C24):**
5. **Skeleton-then-populate forcing function** — instance-catalogue
   skeletons surface observation-discipline gaps when populate-time
   work discovers Obs entries lack data for (a)-(e) axes. Demonstrated
   3× in C21/C22/C23 findings above; planned populate path for C20b.
6. **UI-layer vs state-layer disambiguation via trace** — operator
   observations from UI render may not match trace state; assertions
   that read trace data exclude UI-render defects. C21's Nissanka
   case is the canonical example.
7. **Both-surfaces-stale-at-same-value** — internal-consistency
   assertions PASS when rotation-lock corrupts adjacent surfaces in
   sync; cricket-vs-pipeline ground-truth assertions are a separate
   infrastructure layer not in trace scope. C22's finding scopes
   workstream D and bounds B2's value as a regression detector.

Pattern continues to accumulate at the meaningful rate flagged in
prior HANDOFFs. Each session contributes 1–3 transferable insights;
the track record is itself a load-bearing artifact.

### This session's commits

```
4f79613 C23: B3 — trace_gamma_bowler_w_increment_on_dispatch assertion (no fix; deferred to C23b)
6817481 C22: B2 — trace_gamma_fow_name_matches_striker_at_wicket assertion
b327ed1 C21: B1 — trace_gamma_w_symbol_at_wicket assertion (surface_pair_defect_class_family §2.1)
e051cfa C20: surface_pair_defect_class_family.md skeleton — 9 instance placeholders
74e90dd C19A5: preflight tag-existence check before validation launch
ceeb4e0 C19A4: schema note — tags nested under scorer.decisions[].tag
7557d47 C19A3: restore trace_beta_sm_wicket_dispatch emission at _apply_wicket_fall_only
5a80b8f C19A1: tighten counterfactual framing on legitimate_pair predicate provenance
```

### Next session's first action — SUPERSEDES PRIOR "Next session's first action" SECTION

The prior "If a fresh production trace exists..." framing further
down in this document is superseded: **open workstream D investigation.**
No fresh-replay-as-validation-gate is the unblocked next move —
the gate already fired on DCKKR 2026-05-21 with results above.

Workstream D entry session sequence:
1. Read `surface_pair_defect_class_family.md` §2.5 + §2.6 plus the
   three forcing-function findings above
2. Read `validate_dckkr_replay_observations.md` Obs 2/3/9/16/17/18/19/21
   (the rotation-lock and bowler-identity moments)
3. Examine the captured trace for `resolution_src` distribution
   across wicket events — how many P2 vs P3 attributions?
4. Examine `pipeline.current_bowler` transitions across the captured
   trace — when does it enter/exit the em-dash sentinel?
5. Derive candidate root-localization hypotheses per the standard
   temporal-coupling investigation methodology (C10 brief + C9
   mutation-site catalogue), with §12.4 detection methodology + §12.6
   audit obligation cross-referenced

Deferred work tracked elsewhere:
- **C20b** — per-row (a)-(e) populate of `surface_pair_defect_class_family.md`
  §2.1–§2.9 with full evidence from Obs N anchors. Independent of D;
  can land anytime; will likely produce more forcing-function findings.
- **C21b** — W→· revert site identification in the symbol-commit path.
  Most plausible candidate per static analysis:
  `_rewrite_eyes_this_over_from_event` at `score_manager.py:695`
  ("Fix A: SM-authoritative rewrite of eyes-side `over_mgr.this_over`").
  Needs fresh replay with C19A3 emission firing for per-frame
  `this_over` diff inspection.
- **C23b** — bowler-W increment in the actual wicket-dispatch path
  (NOT `_apply_wicket_fall_only`, which the trace confirms is not
  being reached for these captured wickets — they dispatch via
  ABSORBED_LEGAL gap_finalize_wicket per the docstring). BLOCKED on
  workstream D resolving the em-dash bowler-identity case.

## Session continuation — C26–C31 (workstream D fix chain)

This chain ran 2026-05-21 post-C25. **8 commits landed** (C26, C27, C28, C29, C30, C30b, C31, C32). Pre-commit Layer 1.5 (now 36 ledger + 6 cross-field + 3 D1 + 3 D2 = 48 cases) + Layer 2 (30 balls) held on every commit. **Falsification budget unconsumed: 0/5 empirical cap across the entire chain.** All advances static (predicate-trail, cross-fixture grep, structural-surface check) per Meta-finding #1 (static-analysis methodology at near-zero commit cost).

### Workstream D chain — commit ledger

```
e04324f C31:  H-D2-Layer-1a fix — broadcast-vs-deterministic override at WICKET-ATTRIB
4c50344 C30b: D2-fix structural-surface check — override gate ruled out, WICKET-ATTRIB site confirmed single-site
d7c7bdf C30:  D2-prelim refinement — Signal 1 falsified, fix surface relocated, S8/S9/S10
151ee49 C29:  D2-prelim — Scout dismissed-field cross-fixture absence verified, H-D2-Layer-1 bifurcated
7553473 C28:  H-D1 fix — Candidate C dual-source consensus at wicket-dispatch bowler read
6d0bac9 C27:  D1-prelim — static-falsification verdicts on Candidates A/B/C
85b3169 C26:  workstream D investigation memo — 2 hypotheses + sub-finding S1
```

### Predicted-flip claims (locked at §6 of workstream_d memo; gated on next DCKKR replay)

| Assertion | Pre-fix baseline (C24) | Post-C31 predicted (next replay) |
|---|---|---|
| `trace_gamma_bowler_w_increment_on_dispatch` | FAIL × 4 | **FAIL × 2** (F400 + F679 close via tracker fallback; F855 + F1017 require D2 ladder + W-W7 phantom-wicket split-off) |
| `trace_gamma_w_symbol_at_wicket` | FAIL × 2 | **PASS** + cricket-truth FOW flips at F855 (direct broadcast-override) + F983 (S9 cascade closure). F1017 unchanged (workstream surface E split-off per S10). |
| `trace_gamma_fow_name_matches_striker_at_wicket` | PASS (internal-consistency) | PASS (unchanged — invariant tests internal consistency, not cricket truth) |

### Sub-findings index (S5–S12, all static)

- **S5** — Scout-contract gap is architecturally distinct from rotation-lock-starvation root. Two non-overlapping fixes (Layer 1a downstream / Layer 1b upstream).
- **S6** — Predicate-trail static-falsification at zero empirical cost extends beyond temporal-coupling defect class to Scout-contract gaps. Audit pattern transferable across hypothesis types.
- **S7** — D-chain empirical-falsification budget unconsumed (0/5 cap) across ~2.6k frames surveyed read-only.
- **S8** — Signal 1 (tracker LEADER cross-check) statically falsified at F855/F983/F1017. Trackers are NOT independent of the rotation-lock-starvation root; deterministic-rotation override is the BW07-analog for the striker side.
- **S9** — F855 → F983 cascade closure. F855 misattribution makes F983 structurally underivable; closing F855 auto-closes F983 with no independent fix surface. **Second instance of F1-session cascade-closure-via-one-edit pattern** (Meta-finding #1 from prior session).
- **S10** — F1017 is phantom-wicket detection, not misattribution. Qualitatively different defect class. Split off to workstream surface E candidate.
- **S11** — Signal/site decoupling pattern. Predicate-trail reformulation can move the predictive signal (tracker LEADER → broadcast-striker) without moving the implementation surface (`test_pipeline.py:13063` stable from §3.5 through C31). Transferable across audits where the predicate-trail produces a "wrong signal, right site" finding.
- **S12** — Non-discriminable-predicate-signature defect-class pattern. When two cases (one regression-protected, one investigation-target) share the same observable predicate at a site, single-site fix is structurally impossible without plumbing. Peer entry to dual-state-write in `sm_as_orchestrator_design.md` §12.

### Deferred-work index update

- **C29b (or successor)** — Scout prompt schema extension to emit structured `dismissed` field. Closes contract gap at source. OUT of D-scope; candidate for separate workstream surface. Empirical basis: 0/182 wicket-signal frames across 4 fixtures.
- **Workstream surface E** — phantom-wicket detection (F1017 case). Defect class qualitatively distinct from F855/F983 misattribution. Root-localization needed on the wicket-event-detection path (`ball_detector.detect` or upstream wicket-signal aggregation).
- **§12 catalogue extensions** — (a) `STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC` override as the 4th instance of dual-state-write (after F-α-shadow / F1-B-ε / B-η-FC5 / D1-BW07-bowler-em-dash); (b) S12 non-discriminable-predicate-signature as a new peer defect-class entry.
- **C23b** — bowler-W increment in the wicket-dispatch path. Unblocked once next replay validates D1 + D2-Layer-1a predicted flips.

### Methodology track record extension

Four new transferable insights from this chain bring the running total to **11** (7 from prior sessions + 4 from C26-C31):

- **S6** — predicate-trail extends beyond temporal-coupling defect class to Scout-contract gaps.
- **S9** — cascade-closure-via-one-edit pattern, second instance. F1 was first; S9 is the second.
- **S11** — signal/site decoupling pattern.
- **S12** — non-discriminable-predicate-signature defect class.

## The objective

Shift the pipeline from a detection-heavy architecture to a derivation-first architecture that consumes a strict 5-primitive Scout contract:
1. Runs (cumulative score)
2. Overs (current over notation)
3. Batter identities (names from squad list, not raw OCR strings)
4. Bowler identity
5. First striker after innings start / new batter after wicket

Everything else on the UI is deducible from these primitives plus per-frame deltas. The session's discipline: any classification of code as "scar tissue" or "defect class" is a hypothesis pending the §7.2 seven-gate audit. The audit is the load-bearing safety mechanism.

## Headline result this session — F-η cascade-root localization via static analysis + Shape B fix

**Shape B cross-field pairing gate (`ad151fd`)** at `apply_scorer_decision` (test_pipeline.py:4517) closes the B-η cascade root that produced the DC vs KKR session's f304 anchor corruption + downstream wicket-dispatch failures.

**Cascade root concretely localized via production `/tmp/pipeline.log` audit (C12.5b):**

```
F302 TRACK score: 45 → 49 (post-event immediate, grace=1)
F302 TRACK overs: 4.4 → 4.5 (fast-confirm, natural overs increment F302)
F303 POISONED                                                  (upstream block)
F304 TRACK score: 49 → 54 (post-event immediate, grace=1)      ← CASCADE ROOT
F304 TRACK overs: 4.5 → 6.3 (post-event immediate, grace=0)    ← CASCADE ROOT
```

The `(post-event immediate, grace=N)` suffix is the FC5 log signature from `consistent_tracker.py:304-305`. Two FC5 fires at F304 admit both halves of the bad PANT/WARD/SHAMI overlay frame's reading via `_post_event_grace=2` inherited from f302's `on_ball_event()` reset, combined with `_is_suspicious` returning False for upward score jumps under +30 and forward overs jumps.

**Empirical pairing criterion (C13 §2.1):**

```
legitimate_pair(d_score, d_balls, d_wickets) ≡
    (d_balls == 1 AND 0 ≤ d_score ≤ 7 AND d_wickets ∈ {0, 1})  -- legal delivery
  OR
    (d_balls == 0 AND 0 ≤ d_score ≤ 5 AND d_wickets ∈ {0, 1})  -- extras-only
```

Verified empirically: 127/127 benign DIRECT-SCORE-COMMIT firings (GTRR 80 + DCKKR 47) satisfy `legitimate_pair`. F304 fails (d_balls=10, d_score=+5).

## Session meta-findings — two architectural insights worth headlining

This session's accumulating discipline track record produced two transferable methodology insights, alongside the prior session's F1 cascade-closure headline:

### Meta-finding 1 — Static-analysis methodology at near-zero commit cost

Predicate-trail reading + cross-fixture empirical verification produces full cascade-root localization without an instrumentation cycle per hypothesis. The C9 catalogue + C10 static analysis + C11 predicate semantics + C12 sub-candidate elimination + C12.5b pipeline.log parse = **full cascade-root localization at near-zero commit cost** (5 docs commits, zero behavior change), followed by C13 audit + C14 fix at 2 functional commits.

The previous methodology (instrument → replay → fix) had a budget cost of one diagnostic commit per hypothesis. The static-analysis methodology had a budget cost of one docs commit per hypothesis-class. **This is a defect-class identification methodology distinct from "instrument-replay-then-fix", suited specifically to temporal-coupling defect classes that captured-replay flattens (per §0.3 of the C8 brief reframe).**

### Meta-finding 2 — Falsification cascade as methodology signal-of-correctness

Five empirical + eight static falsifications + one acceptance is the methodology's signal of correctness, not its signal of failure. The discipline rule "every classification is a hypothesis pending empirical verification" produces a falsification cascade BY DESIGN; the budget mechanism (5-empirical-falsification methodology-retirement trigger from C9 §11 + C10 §1.2) ensures the cascade terminates productively rather than open-loop. **A complete falsification chain is an architectural finding, not a failure.**

These two meta-findings join F1's cascade-closure (prior session) and the §7.2 7-gate audit (prior session) as the workstream's accumulating discipline track record.

## Architectural posture

### Detection vs Derivation (unchanged from prior session)
- **Detection (5 primitives only)**: vision provides runs, overs, batter names, bowler name, first-striker/new-batter signals.
- **Derivation (everything else)**: this_over tokens derive from per-frame (Δruns, Δovers, wicket events). Striker rotation derives deterministically from first-striker + per-ball runs sequence + wicket events.
- Squad-canonical name resolver enforces that raw Scout name tokens get rejected if they don't fuzzy-match to a squad member.

### SM as sole UI authority (unchanged + reinforced)
- WS payload reads Recent Overs from SM's `over_history`.
- Striker rotation determined by SM; broadcast indicator is corroboration only.
- Squad-canonical name resolver enforced at all bat1_name / bat2_name / broadcast_striker / bowler_name commit sites.
- Initial striker at cold-start exit reads `broadcast_striker` field correctly (F1, `437d952`).
- **New (C14): cross-field pairing gate at `apply_scorer_decision` rejects single-frame commits whose (Δscore, Δballs, Δwickets) tuple violates `legitimate_pair`.**

### No-speculative-fixes discipline (refined further this session)
Every fix commit must cite specific trace evidence — concrete frame numbers — that proves the diagnosed cause. "Likely" / "probably" language is investigation-only, never authorization to commit. If diagnosis can't be confirmed from existing data, add static-analysis + pipeline.log audit first, re-run, then fix.

**The "captured-replay drives investigation" assumption is RETIRED** for temporal-coupling defects (per C8 §0.3). Captured-replay remains canonical as a falsification mechanism and regression-detection substrate; it does NOT drive root-localization for defect classes where the temporal signature flattens under deterministic replay.

### §7.2 seven-gate audit checklist (standing precondition; gates 1–7 unchanged)

The framework added gate 7 (cross-fixture verification) in the prior session per F1 closure. This session applied all 7 gates to 4 candidate shapes (A/B/C/D) at C13 — first deep multi-shape audit in the chain. Gate-6 (predicted-flip with concrete frame numbers, applied recursively) is non-negotiable per the falsification track record.

**New discipline nuance — static vs empirical falsification:**

- **Empirical falsification** counts against the methodology-retirement budget (5-falsification cap per C9 §11 / C10 §1.2). Replay or instrumentation cycle empirically disproves a hypothesis.
- **Static falsification** does NOT count against the budget. Code-reading or predicate-trail pass conclusively proves a hypothesis is impossible at the proposed site. Zero-cost; apply liberally before any instrumentation commit.

This session: 5 empirical falsifications (B-η chain) + 8 static falsifications (C10 + C11 + C12) + 1 acceptance (Shape B). Without the static-vs-empirical distinction, the chain would have hit the retirement budget at C11.

## This session's commit ledger — chronological

This session ran 2026-05-21. **16 commits total.** Pre-commit gate (Layer 1.5 + Layer 2) held on every commit. Predicted-flip claims empirically validated or statically falsified at each step.

```
b49e48b chore(diagnostics): B-η instrumentation pass — three additive trace tags + replay scaffold
e3171eb chore(diagnostics): replay-scaffold warm-seed mode for f304-anchor reproduction
86299e0 docs(design): B-η stream-gap reconciliation memo + post-instrumentation empirical findings
78b4835 chore(diagnostics): replay-only LLM-extractor fallback for f304-anchor reproduction
ac06fa6 docs(design): B-η memo §10 — empirical f304 evidence + cascade-root pivot
237d227 chore(diagnostics): DIRECT-SCORE-COMMIT instrumentation + GTRR fixture support
e19f72a docs(design): B-η memo §11-§13 — fifth falsification + investigation-strategy pivot + meta-finding
a99d82c docs(brief): C8 reframe — Step 1 retarget + temporal-coupling block on Steps 2/3
af19dd2 docs(design): C9 state-mutation site catalogue — 38 write sites + 2 async callbacks
2df4061 docs(brief): C10 temporal-coupling investigation — sixth hypothesis, static analysis
5833857 docs(brief): C11 static-analysis pass — Outcome A (qualified) on FC5 post-event grace
b6e3c70 docs(brief): C12 overs-side static-analysis closure — score-side fully localized, overs-side narrowed
c05c4b6 docs(brief): C12.5b — pipeline.log audit closes gate 6 with concrete frame numbers
639fa4a docs(audit): C13 §7.2 7-gate audit on FC5 candidate fix shapes — Shape B selected
ad151fd fix(test_pipeline): C14 cross-field pairing gate at apply_scorer_decision — closes B-η F304 cascade root
770db98 test(C15): permanent gate-6 verification + baseline + predicted-flip claim for C14 fix
```

## Trace assertion library (UPDATED post-C24, +trace_eta 2026-05-22)

Nine empirically-grounded invariants in `files/tests/trace_session_assertions.py` (5 existing + 3 γ-bundle from C21/C22/C23 + 1 η-bundle from Workstream G step 4). Baseline on `validate_dckkr_20260521_155356`:

| Assertion | Pre-C19 baseline | Post-C24 baseline on DCKKR 2026-05-21 |
|---|---|---|
| `trace_alpha_bowler_runs_sum` | FAIL gap=4 (DCKKR pre-fix) | PASS |
| `trace_beta_sm_wicket_dispatch` | FAIL — 3 misses | FAIL × 4 (4 wickets detected via ball_event fallback; typed emission landed C19A3 — next replay validates) |
| `trace_epsilon_initial_striker` | PASS | PASS |
| `trace_compound_tokens` | PASS | PASS |
| `trace_extras_total` | PASS | PASS |
| `trace_gamma_w_symbol_at_wicket` (NEW C21) | — | **FAIL × 2** (Rahul ov 5.0 / Rana ov 8.0 — W→· revert in this_over state) |
| `trace_gamma_fow_name_matches_striker_at_wicket` (NEW C22) | — | PASS (internal-consistency only; cricket-vs-pipeline divergence undetectable here, scoped to D) |
| `trace_gamma_bowler_w_increment_on_dispatch` (NEW C23) | — | **FAIL × 4** (no bowler-W increment within 30-frame lookahead at any captured wicket) |
| `trace_eta_post_wicket_cascade_drains` (NEW WS-G step 4) | — | PASS trivially on pre-Shape-A traces (0 enqueues; tag wasn't in KNOWN_TAGS until f09fc38). Post-Shape-A replay predicted: 2 enqueues (F679, F855) → 2 DRAIN-FIRED terminals (F709 age=30, F893 age=38) per audit §5 |

**Total post-C24: 6 PASS / 3 FAIL across 9 assertions.** The γ-bundle (3 assertions) tests wicket-dispatch correctness across W-symbol, FOW-name, and bowler-W surfaces. The η-bundle (1 assertion) tests post-wicket cascade lifecycle: every `POST-WICKET-CASCADE-ENQUEUED` must reach one of three terminal states (DRAIN-FIRED / DRAIN-EXPIRED / WIPED-BY-COLD-START) by end-of-session, else orphan-FAIL per audit §2.5 lifecycle table.

Runner: `python files/scripts/run_trace_session_assertions.py <trace.jsonl>`.

## Validation gate — STATUS: FIRED on DCKKR 2026-05-21 (see top-of-document Session continuation section)

The C14 validation gate **already fired** on `validate_dckkr_20260521_155356` (full results in the C19–C24 session continuation section above). C14 sign-off accepted on "predicate is correct, gate reachable, two distinct Shape-B-class defects caught" basis — F-η pattern specifically did not surface but the predicate's generality is empirically established.

Standing pattern for future sessions remains: ship with predicted-flip claim, validate on next natural production session. The original "predicted: PASS on trace_beta" framing is **SUPERSEDED** by the γ-bundle baseline above — the new gate signal is FAIL × 2 (w_symbol) + FAIL × 4 (bowler_w) → expected PASS after workstream D resolves the rotation-lock-starvation root and C21b/C23b land. C19's "extend Shape B coverage to catch-up branch + end-of-over hook" alternative is also retired: empirical evidence from DCKKR shows the root is upstream (rotation pointer staleness at wicket frames), not coverage gaps in the gate's call sites.

## Workstream status by area

### F-η Shape B fix (shipped C14, VALIDATED 2026-05-21)
Cross-field pairing gate at `apply_scorer_decision` (test_pipeline.py:4602/4617/4631). Empirically validated on DCKKR 2026-05-21 — 2 distinct CROSS-FIELD-PAIRING-REJECT events fired in production (F210 backwards-overs, F1015 zero-time double-wicket). The gate's call site is `test_pipeline.py:12466` (non-poisoned SCORER path). DSC path was NOT exercised in the validation replay; gate-coverage of DSC remains counterfactual per C19A1's tightened comment. Permanent gate-6 test at `files/tests/test_cross_field_pairing_gate.py` (6 cases) wired into Layer 1.5.

### B-ι (locked-SM-state prevents resync) — RETIRED as standalone workstream
Per DCKKR 2026-05-21 evidence: `trace_alpha_bowler_runs_sum` flipped PASS post-C14, indicating no resync-prevention symptom in production. B-ι hypothesis dissolved as cascade symptom of B-η, consistent with the dual-state-write defect-class pattern. **No standalone B-ι memo needed.**

### B-θ (over-boundary bowler credit) — RETIRED as standalone workstream
Same as B-ι. trace_alpha gap closed post-C14. B-θ collapsed as cascade symptom of B-η. The bowler-W increment defect surfaced via `trace_gamma_bowler_w_increment_on_dispatch` is a SEPARATE defect (wicket-event commit path, not over-boundary bowler credit) and is the target of workstream D + C23b, not a B-θ reopening.

### Workstream D (rotation-root revisit) — D1 + D2-Layer-1a CODE SHIPPED (empirical validation gated on next replay)
See "Session continuation — C26-C31" section above for full chain. D1 (over-end-coincident bowler em-dash sentinel at `_apply_wicket_fall_only`) and D2-Layer-1a (broadcast-vs-deterministic dismissed-name attribution at WICKET-ATTRIB) both shipped as code. Predicted flips: `trace_gamma_bowler_w_increment_on_dispatch` FAIL×4 → FAIL×2; `trace_gamma_w_symbol_at_wicket` FAIL×2 → PASS + cricket-truth FOW at F855 + F983 (S9 cascade closure). F1017 split off to workstream surface E (S10 phantom-wicket detection class). C23b (bowler-W increment in wicket-dispatch path) unblocked once next replay validates these predicted flips.

### Captured-replay scaffold (commits b49e48b–237d227)
- `files/scripts/replay_captured_scout_trace.py` — captured-Scout replay scaffold
- Supports `--seed-frame / --seed-striker / --seed-non-striker / --seed-bowler` (warm-seed mode)
- Supports `--enable-llm-extractor` (production Extractor.extract() via Groq Llama)
- Supports `--fixture {dckkr, gtrr}` (cross-fixture)
- Emits four observation tags: `FRAME-TRUST-GATE`, `OVERS-JUMP-STREAK-STATE`, `POISON-STREAK-AT-COMMIT`, `DIRECT-SCORE-COMMIT`
- **Limitation (§0.3 retired-assumption):** does NOT drive `apply_scorer_decision` — only SM-side `on_frame()`. Captured-replay cannot reproduce temporal-coupling defects; serves as falsification mechanism + regression detector, not localization tool.

### State-mutation-site catalogue (C9)
`files/docs/investigations/state_mutation_site_catalogue.md`: 38 write sites + 2 async callbacks across `score_manager.py`, `test_pipeline.py`, `eyes/scoreboard.py`. Score, wickets, overs, batter-identity, bowler-identity primitives.

**Three gate-bypass classes surfaced:**
- §7.1 `_inn[*]` direct-write bypass (6 sites) — state-recovery Phase-2 + POISON-RECAL forced reset
- §7.2 async-callback writes (2 sites: striker/bowler on_lock) — falsified statically in C10 §3 (not actually async)
- §7.3 hot-resume path (5 sites) — startup-only, deprioritized

**Catalogue is itself a gate-6 instrument** (per C9 §11): future "the defect is at site X" hypotheses can be checked against the table for whether X is a real mutation site, what gates protect it, what the invocation pattern is.

### UI render layer bugs (separate workstream — unchanged from prior session)
- B-γ (Recent Overs panel drops entries), B-δ (UI bottom-strip striker), `trace_extras_total` UI inconsistency — out of scope for SM/pipeline workstream.

## Pipeline tracks (unchanged)

### Track 1 — State derivation (production pipeline)
Entry: `files/test_pipeline.py` main loop. Frame source: `files/eyes/capture/udp_frame_source.py` (UDP MPEG-TS via ffmpeg subprocess).

Status: C14 fix in place; operational validation pending; cascade-root localized at F302/F304 via static analysis + pipeline.log empirical evidence.

### Track 2 — Clip extraction (OpenScout)
Disabled (`USE_OPEN_SCOUT=0`). Will not enable until Track 1 fully validated.

## File paths

```
files/test_pipeline.py             # Main pipeline; apply_scorer_decision at :4356
                                   # C14 cross-field pairing gate at :4517
files/score_manager.py             # State machine (~6500 lines)
files/eyes/scoreboard.py           # Scoreboard + sb.set bottleneck at :1188-1481
                                   # DIRECT-SCORE-COMMIT emission at :1481 (C6)
files/eyes/consistent_tracker.py   # ConsistentReadTracker — 5 fast-confirm paths
                                   # FC5 post-event grace at :294-306 (cascade root)
files/eyes/scoreboard.py           # batting_card / bowling_card / squad resolution
files/confidence_tracker.py        # ConfidenceTracker (team / striker / bowler)
                                   # NOT the FC5 site (don't confuse with consistent_tracker.py)
files/eyes/vision.py               # SCOUT_PROMPT_SHORT (default), SCOUT_PROMPT (verbose)
files/eyes/agent.py                # Extractor.extract() — LLM fallback path
                                   # Uses int|None syntax (Python 3.10+)
files/eyes/extract_regex.py        # Regex-primary parse_strip (returns None on STRIP miss)
files/eyes/frame_ledger.py         # Frame Fate Ledger
files/eyes/udp_frame_source.py     # UDP MPEG-TS frame source
files/cricket_rules.py             # validate_diff invariants
files/trace_emitter.py             # KNOWN_TAGS registry (180+ tags incl. C6/C10/C14)

scorecard-ui/app/page.tsx          # Main UI
scorecard-ui/app/components/BattingCard.tsx

files/tests/symptom_class_assertions.py    # 11 assertion functions (12 classes)
files/tests/trace_session_assertions.py    # 5 trace-session assertions
files/tests/test_sm_derivation_ledger.py   # Layer 1.5 — 36 balls + 6 cross-field gate cases
files/tests/test_pipeline_captured_replay.py  # Layer 2 — captured-Scout replay
files/tests/test_cross_field_pairing_gate.py  # C15 permanent gate-6 (6 cases)
files/tests/fixtures/dc_vs_kkr_2026_152064_ledger.json
files/tests/fixtures/gt_vs_rr_2026_commentary_first_innings.md

files/scripts/run_trace_session_assertions.py     # Trace session assertion runner
files/scripts/replay_captured_scout_trace.py      # Captured-replay scaffold (C-commits)
files/scripts/analyze_gap_detected_retro.py
files/scripts/audit_scar_tissue_targets.py

files/docs/investigations/temporal_coupling_investigation_brief.md  # C10–C12.5b chain
files/docs/investigations/c13_fc5_audit_memo.md                     # C13 7-gate audit
files/docs/investigations/stream_gap_reconciliation_design.md       # B-η chain §1–§13
files/docs/investigations/state_mutation_site_catalogue.md          # C9 catalogue
files/docs/investigations/dckkr_20260521_cc_investigation_brief.md  # operator brief + §0 reframe
files/docs/investigations/dckkr_20260521_session_observations.md    # observations + C15 §
files/docs/investigations/sm_as_orchestrator_design.md              # §7 framework + §12 (C17 dual-state-write catalogue)

deploy/systemd/*.service           # pipeline, recorder, live-clips, ui
deploy/Caddyfile
.github/workflows/deploy.yml
.git/hooks/pre-commit              # Layer 1.5 + Layer 2 gate; venv-Python preference (C15)
```

## Launch sequence (operational reference, unchanged)

```bash
cd ~/Projects/SportsComm

# Clear stale state
rm -f files/match_state_cache.json logs/openscout-local_*.jsonl
rm -f /tmp/pipeline.log /tmp/ffmpeg.log

# Terminal A — UI
cd ~/Projects/SportsComm/scorecard-ui && npm run dev

# Terminal B — pipeline (Python 3.12 venv)
cd ~/Projects/SportsComm
export FRAME_SOURCE=udp
export FRAME_SOURCE_UDP_URL='udp://0.0.0.0:9999?fifo_size=10000000&buffer_size=2097152&overrun_nonfatal=1'
export FRAME_SOURCE_UDP_ALLOWED_DIMENSIONS='1920x1080,1280x720'
export CRICBUZZ_MATCH_ID=<match_id>
export CRICBUZZ_MATCH_SLUG=<slug>
export BMF_SESSION_ID="validate_$(date +%Y%m%d_%H%M%S)"
export USE_OPEN_SCOUT=0
export SCOUT_PROMPT_MODE=verbose
export SCOUT_RAW_DUMP=1
export PYTHONUNBUFFERED=1
export SCOUT_DEDUP_SHADOW=1
export SKIP_PREMATCH_S=0
files/.venv/bin/python files/test_pipeline.py 2>&1 | tee /tmp/pipeline.log

# Terminal C, D — see prior HANDOFF for ffplay viewer + ffmpeg dual-output stream
```

UI: http://localhost:3000. Validation fixtures:
- DC vs KKR (`files/logs/deliveries/20260508_191946/match_4621b9f8.mp4`, start ~09:30)
- GT vs RR (`files/logs/deliveries/8a0c6c14/match_8a0c6c14.mp4`, start ~40:30)

## Fresh-checkout setup

The pre-commit hook at `.git/hooks/pre-commit` prefers the project venv Python (`files/.venv/bin/python`, 3.12) over system `python3` (3.9 on most macOS). This is necessary because the C15 cross-field-pairing-gate test imports `eyes/agent.py` which uses `int | None` syntax (Python 3.10+).

The hook lives outside the tracked git tree (`.git/hooks/` is gitignored). **Run `scripts/setup_precommit.sh` after a fresh clone** (or after the canonical hook content changes). The script:

- Verifies `files/.venv/bin/python` exists; fails loudly with a clear setup-instruction message if not (does NOT silently fall back to system `python3`)
- Writes the canonical hook content (Layer 1.5 + Layer 2 + venv preference) idempotently to `.git/hooks/pre-commit`
- Marks it executable
- Prints verification instructions

Verify post-install by running any `git commit` (hook fires automatically) OR by invoking the harnesses directly under venv:

```sh
files/.venv/bin/python files/tests/test_sm_derivation_ledger.py
files/.venv/bin/python files/tests/test_pipeline_captured_replay.py
```

## What NOT to touch

Per prior session + this session's findings:

- Queue B (`_pending_bowler_ball_credits`) — load-bearing 3-way-race resolver per §7.1
- `_ScoutRetryBuffer` — active queue across Groq 429 backoff per §7.1
- `broadcast_extra` / `extras_type` — parallel fields per §7.5
- Cold-start synth token-distribution heuristic in `_synthesize_cold_start_ball_events`
- `confidence_tracker.py` ConfidenceTracker class — battle-tested, foundational
- Existing deterministic-rotation override at `score_manager.py:4295-4325` — load-bearing
- **NEW: C14 cross-field pairing gate at `apply_scorer_decision` (`test_pipeline.py:4517`)** — the cascade-closer for B-η
- **NEW: Permanent gate-6 test at `files/tests/test_cross_field_pairing_gate.py`** — the empirical regression detector for C14
- F1's field-name fix at `_accept_initial:2789-2808`
- F-α-shadow fix in `_capture_multi_ball_shadow_state:4515+`
- F-α-queue in `_apply_absorbed_event` (5310-5358)
- Pre-commit hook venv preference — deviating from this will silently break L1.5 imports

## What's in flight behind feature flags (unchanged)

- `SM_INLINE_MULTI_BALL` — default off
- `SM_POST_WICKET_SLOT_DIFF` — default off
- `USE_OPEN_SCOUT` / `USE_OPEN_SCOUT_SPANS`

## Next session's first action

1. Read this HANDOFF.md
2. Read `Architecture_HANDOFF.md` + `CLAUDE.md`
3. Read `files/docs/investigations/workstream_d_rotation_root_investigation.md` (the C26-C31 investigation memo, ~10kB)
4. `git log --oneline derive-not-detect | head -15` for full session context — expected HEAD chain: C32 → C31 → C30b → C30 → C29 → C28 → C27 → C26 → C25 → C24

**Primary unblocked path — empirical validation of D1 + D2 predicted flips on next DCKKR replay.** Run a fresh DCKKR replay (or any fixture with sufficient wicket density) and check the γ-bundle assertions:
- `trace_gamma_bowler_w_increment_on_dispatch` — predicted FAIL × 4 → FAIL × 2 (F400 + F679 close via D1 tracker fallback)
- `trace_gamma_w_symbol_at_wicket` — predicted FAIL × 2 → PASS + cricket-truth FOW name flips at F855 (D2 broadcast-override direct) + F983 (S9 cascade closure)
- If predicted flips land → C23b unblocks; close D chain in a C33-tier docs commit
- If predicted flips do not land → **first empirical falsification** for the D chain (budget cap 5/5 still open); next move is plumbing at `score_manager.py:4411` (the override gate ruled out as single-site at C30b, but the empirical falsification authorizes the escalation per §3.4d.6)

**Secondary unblocked paths (independent of replay status; all static, all C20b-tier):**
- **§12 catalogue extension** — landed in `sm_as_orchestrator_design.md`: (a) `STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC` override as 4th dual-state-write instance, (b) S12 non-discriminable-predicate-signature as new peer defect-class entry. Skeleton-then-populate pattern (Meta-finding #5).
- **C20b** — `surface_pair_defect_class_family.md` §2.1–§2.9 per-row (a)-(e) populate. Independent of D; can land anytime; will likely produce more forcing-function findings (the skeleton-then-populate pattern was the #5 meta-finding source — populate-time discovers Obs gaps).
- **Workstream surface E skeleton** — F1017 phantom-wicket detection class memo (parallels C26's structure: open a `workstream_e_phantom_wicket_detection.md`, hypothesis-then-fix discipline).
- **C29b** — Scout prompt schema extension (`dismissed_batter` field). Out of D-scope but unblocked.

**Do NOT:** open B-ι / B-θ memos (retired pre-C26); attempt C23b before D1 + D2 empirical validation; touch BW07 clear ordering at `score_manager.py:5965` (Candidate A territory, retired by risk-surface argument at C27); attempt single-site fix at `score_manager.py:4411` without the empirical-falsification trigger from a failed replay (ruled out by S12 / non-discriminable predicate signature at C30b).

## Standing discipline (refined this session)

Architecture principles user repeatedly enforces (carried from prior session, refined this session):

- "Detection establishes identity, derivation maintains state"
- "SM is the final authority on the UI; everything else should not have a say"
- "Once high confidence reached, LOCKED — only explicit events unlock"
- "Real-time first, no offline-only solutions"
- "Consolidate and validate together — minimize ping-pong validation cycles"
- **"No speculative fixes. Find the root cause and confirm. Always."** — this session: 5 empirical + 8 static falsifications enforced the rule recursively across 16 commits.
- **"Every delivery must be accounted for."** Added 2026-05-22 (post-replay session). The pipeline does NOT silently skip deliveries. If Δballs > 1 in any state transition during operation, that is a P0 bug to raise and resolve immediately — NOT a case to silently handle with defensive defaults. Build no logic that assumes the pipeline may miss a delivery; silent fallbacks normalize the failure mode. Workstream G (pipeline-lag / missed-deliveries) is therefore a correctness workstream, not a performance one. Pre-pipeline-existence balls (mid-match cold-start) are a separate regime — they didn't happen during operation, so don't count as "missed"; cold-start exit emits an explicit `COLD-START-EXIT` boundary tag so subsequent missed-delivery events are unambiguously bugs.
- Any "scar tissue" / "defect class" label is a hypothesis pending the §7.2 audit.
- **Static-falsification ≠ empirical-falsification.** Static is zero-cost; apply liberally before any instrumentation commit. Empirical counts against the methodology-retirement budget (cap: 5 per session per defect-class chain).
- **Captured-replay does NOT drive root-localization for temporal-coupling defects.** It remains canonical as falsification + regression-detection substrate.
- **A complete falsification chain is an architectural finding, not a failure.** Document each chain's meta-finding in HANDOFF alongside the positive cascade-closure findings (F1, etc.).

## Trace-and-Detect (v1, unchanged)

Per CLAUDE.md trace-and-detect section. Per-frame trace records to `logs/trace/<SESSION_ID>.jsonl`. New trace tags this session:

- `FRAME-TRUST-GATE`, `OVERS-JUMP-STREAK-STATE`, `POISON-STREAK-AT-COMMIT` (C6 instrumentation pass)
- `DIRECT-SCORE-COMMIT` (C12 — at sb.set bottleneck)
- `CROSS-FIELD-PAIRING-REJECT` (C14 — at apply_scorer_decision gate)
- `REPLAY-LLM-EXTRACT-RECOVERED` (replay-scaffold-only, not in production)

## Pipeline feature flags (unchanged)

- `USE_OPEN_SCOUT` (default 0): disabled until Track 1 fully validated
- `USE_OPEN_SCOUT_SPANS` (default 0)
- `SM_INLINE_MULTI_BALL` (default 0): flag flip blocked pending fresh trace
- `SM_POST_WICKET_SLOT_DIFF` (default 0)

## Working venv

Project venv at `files/.venv/bin/python` (Python 3.12). **Pre-commit hook uses this venv** (C15 change). System `python3` (Python 3.9 on macOS) does not support the Python 3.10+ syntax used in `eyes/agent.py`.

## Session-end architectural insight

This session's most important architectural insights, validated empirically across 16 commits:

**(1) Static-analysis methodology + predicate-trail reading + pipeline.log audit produces full cascade-root localization at near-zero commit cost.** The chain C9 + C10 + C11 + C12 + C12.5b produced 8 static falsifications and concrete F302/F304 localization with zero behavior change. Followed by C13 audit + C14 fix at 2 functional commits.

**(2) A complete falsification cascade is an architectural finding, not a failure.** Five empirical + eight static falsifications + one acceptance is the discipline working as designed. The budget mechanism (5-empirical-falsification cap per defect-class chain) ensures the cascade terminates productively rather than open-loop.

**(3) Two-parallel-state-surfaces is a recurring defect class.** Three instances confirmed across two sessions: F-α-shadow (`sb.bowling_card` vs `sb._inn["bowling_card"]`), F1/B-ε (`card.get("broadcast")` vs `card.get("broadcast_striker")`), B-η/FC5 (`sb._tracker.confirmed` vs SM `_handle_warm` streak gate). To be catalogued in `sm_as_orchestrator_design.md` §12 in C17 with detection-signal + remediation-pattern documented.

The workstream pauses cleanly at the operational validation gate. Next move is operational, not engineering. The trace assertion library + 16-commit investigation chain are the standing data-collection + verification mechanisms for any future production session.

Track record of architectural insights accumulated across sessions (**16 transferable insights total**):

- **F1 session (4 sessions back)**: cascade-closure pattern — one-edit fix can close N bug classes; §7.2 gate 7 (cross-fixture verification) catches cascade reach.
- **B-η session (3 sessions back)**: static-analysis-with-predicate-trail methodology + falsification-chain-as-architectural-finding + dual-state-write defect class.
- **C19-C24 session (2 sessions back)**: commit-design drift (preflight tag-existence check) + budget-class mismatch (memo work needs 8–12 calls, code work fits 5) + skeleton-then-populate forcing function + UI-layer vs state-layer disambiguation via trace + both-surfaces-stale-at-same-value (internal-consistency PASS when rotation-lock corrupts adjacent surfaces in sync).
- **C26-C31 session (prior — workstream D fix chain)**:
  - **S6** — predicate-trail static-falsification extends beyond temporal-coupling defect class to Scout-contract gaps.
  - **S9** — cascade-closure-via-one-edit pattern, second instance (F1 was first); F855 fix auto-closes F983 with no independent surface.
  - **S11** — signal/site decoupling pattern: predicate-trail reformulation moves the predictive signal but not necessarily the fix site.
  - **S12** — non-discriminable-predicate-signature defect class: when two cases share an observable predicate at a site, single-site fix structurally impossible without plumbing.
- **§15 triple-subsystem rewrite session (this one)**:
  - **#13 — A single struct field can carry multiple orthogonal write semantics; audit before consolidation.** Surfaced commit (5/N) ROTATION-vs-IDENTITY split for `self.striker` (+24 boundary regression caught the missed sub-semantic) and confirmed commit (7/N) IDENTITY-RESOLVED-vs-PROPOSED split (+24/+9 regression caught the second missed sub-semantic). Canonical-path consolidation is iterative; the harness's diff-by-diff localizes the missed sub-semantic via specific surface-class regression.
  - **#14 — Silently-no-op bugs (NameError swallowed under try/except, attribute lookups returning None) hide downstream effects until harness diff aggregates them across surfaces.** Surfaced commit (7/N) — `trace_beta_sm_wicket_dispatch` had been silently failing because a stale `target_idx` reference raised NameError inside a try/except that caught and discarded it. Operational corollary: re-raise NameError + AttributeError specifically, only catch domain exceptions explicitly.
  - **#15 — Layer 1.5 catches isolated mutation-correctness regressions; harness diff catches emergent cross-surface composition regressions. Both are necessary; harness is the higher-signal layer during multi-component wire-throughs.** Surfaced commit (8/N) cascade wire-through — 4 iterations, all caught by harness diff, zero by Layer 1.5. The harness is doing the load-bearing detection as multi-component changes compose.
  - **#16 — Multi-component rewrites can produce structurally-correct commits that don't deliver predicted empirical drops. That's empirical falsification of the prediction's hypothesis, not failure of the rewrite. Close the arc honestly; pivot to the actual root cause.** Surfaced commit (9/N) attempt — §14.5 hypothesis falsified by data (cold-start no-backfill didn't close C21b in DCKKR dump because Scout-extraction-timing at wicket-commit is the actual root); arc closed at structural completion (commit 8/N), Workstream G promoted to next-session priority #1.
- **Workstream H session (2026-05-23)**:
  - **S16 — Parity-precedent inheritance.** When a fix mirrors a hardened-sibling structurally, it inherits the sibling's residual gaps. Surfaced WS-H step-3 (F939): P1's mirror of `score_reset_from_progress :4423` inherited the sibling's single-frame `_team_changed` consensus gap. Operational corollary: parity-mirror audits must extend to the precedent's known-residual list AND the parity input's own derivation site BEFORE declaring the mirror as a closed fix. Remediation at the precedent (consensus-gate `_team_changed`) closes both consumers simultaneously. See `files/docs/investigations/workstream_h_cold_start_reentry_root_cause.md` §10 S16.
  - **S17 — Cascade-lifecycle second-order regression class.** When a lifecycle fix enables a previously-blocked drain path, downstream assertions that implicitly assumed the drain was blocked may regress. Surfaced WS-H step-3 (F679): γ-fow-name's prev_striker reconstruction assumed cascade-blocked-drain semantics; cascade DRAIN-FIRED exposed the dependency. Operational corollary: gate-5 (lifecycle) must extend to "lifecycle-enabling-of-blocked-paths" as a distinct audit row, separate from "lifecycle-correctness-of-the-newly-enabled-path." See WS-H memo §10 S17.
  - **S18 — Composite-fix cascade closure (third instance of F1 pattern).** D1 (C28 em-dash bowler-tracker) + P1 (ef0860d) compose to close γ-bowler-w which D1 alone could not (predicted FAIL × 2; actual PASS). Pattern recap: F1 single-edit closing N classes (first), S9 F855→F983 (second), now S18 D1+P1 → γ-bowler-w (third). Operational corollary: when a downstream assertion stays FAIL after its "direct" fix lands, prefer an upstream lifecycle audit before declaring the assertion's own surface as the residual root. Each workstream's gate-6 should explicitly include a "but if upstream lifecycle X lands first, residual may collapse" annotation. See WS-H memo §10 S18.
  - **S19 — Cascade-closure dividend can be architecturally real but empirically degenerate.** When a fix mirrors a sibling-parity surface and the sibling's existing protection has already rejected 100% of the captured misread cohort, the cascade-closure dividend is architecturally real (closes hypothetical future variants) but empirically degenerate-on-current-data (no positive baseline fires to suppress). Surfaced WS-H step-5 §5 (cross-fixture survey: zero positive `score_reset_from_progress` fires across all 12 captured traces) + confirmed at WS-H step-7 (zero fires preserved under H1-tightened regime). Operational corollary: gate-6 predicted-flip tables should split into "architectural surface closed" (yes/no) vs. "empirical baseline reduction" (count delta, possibly 0). Both states are valid closure shapes. Cross-references S16 + S18. See `workstream_h_step5_team_changed_consensus_parity.md` §8.
  - **S20 — Cohort-exposure pattern (second instance: WS-H step-7 H1).** When an upstream closure prevents state corruption that previously masked downstream defects, the downstream measurement layer observes a regression — but the regression is REVEALED, not INTRODUCED. The cohort size is a measurement-quality signal: a one-instance "regression" pre-closure becomes an N-instance cohort post-closure as more frames reach the downstream code path. Strengthens the downstream investigation's empirical anchor; weakens the case for reverting the upstream closure. First instance: WS-H step-3 P1 → F679 single γ-fow-name FAIL revealed (S17 authored). Second instance: WS-H step-7 H1 → F679 + F948 + F1017 cohort revealed (same `no_prev_striker` root). Step-5c cross-fixture verification subsequently revealed FOUR additional bonus closures across historical traces (validate_shape_a_114349, validate_shape_a_20260523_114053, validate_surface_b_121222, validate_ws_h_step3) — confirming S20 operates ACROSS traces, not just within a single trace's defect set. Operational corollary: gate-6 regression-guard tables should distinguish Δ count of NEW defect-class instances (true regression) vs. Δ count of EXISTING defect-class instances (cohort exposure). Type (b) is closure progress; score the upstream fix on its primary objective; defer the downstream cohort to its own scoped workstream. S17 + S20 jointly graduate the cascade-lifecycle-enabling-fix audit pattern from single-instance heuristic to multi-trace reproducible discipline. See `workstream_h_cold_start_reentry_root_cause.md` §14 + §16.1.
  - **S21 — Assertion-expectation vs. pipeline-state defect class.** When a trace-assertion's reconstruction depends on a specific pipeline-state invariant that's actually *optional* (e.g., pipeline's canonical invalidation paths can legitimately produce the "broken" state), the failure is in the assertion's expectation, not the pipeline. Three-step diagnostic protocol: (1) trace failing pipeline-state read back to its writers — if ≥50% are in canonical invalidation paths (cold-start reject, NAME-REJECTED, post-wicket-survivor-unresolved, §15-fence cleanup), the "broken" state is architectural-invariant behavior; (2) verify the assertion has an alternate authoritative source at the failure frame (e.g., WICKET-RESOLVED-FROM-DETERMINISTIC-STRIKER + WICKET-RESOLVED-FROM-PENDING tags emit at F<wicket>); (3) cross-check against §15 fence — if state is documented as a canonical write, pipeline cannot be fix site without fence violation, so assertion must adapt. Surfaced WS-H step-5b: pipeline.striker=None at F<wicket-1> is §15-fence-correct cold-start invalidation (5 of 7 None-writers in score_manager.py:3074-:3118); γ-fow-name assertion's expectation of non-None was the defect. **Third instance of fix-surface-attribution discipline** after C21 (UI vs. state) and C22 (both-surfaces-stale vs. one-divergent) — now a standing audit obligation, not a one-off finding. See `workstream_h_step5b_fow_trail_drain_awareness.md` §9 + §12.3.
  - **S22 — Static-investigation-first protocol holds across 9-step arcs (WS-H arc-level meta-finding).** WS-H opened per HANDOFF §17.4 as static investigation, not patch. Across 9 numbered steps (memo + 4 patches + 2 empirical validations + 2 close-outs + 1 arc retirement = 9 commits total) the static-vs-empirical budget distinction held: only step-7's empirical-validation-of-patch-chain consumed 1/5 budget. The other 8 steps held static-falsification discipline including step-5c's gate-7 cross-fixture closure (assertion re-run on on-disk traces, no pipeline execution). Three transferable principles: (a) **arc-length is not a budget-consumption multiplier when static-vs-empirical is rigorously separated** — WS-G consumed 1/5 across 8 steps, WS-H consumed 1/5 across 9 steps; consumption rate is constant per arc, not per step; (b) **gate-7 closure can be budget-neutral when the fix surface is assertion-side rather than pipeline-side** — pipeline-side fixes require empirical replay per fresh fixture (1/5 each); assertion-side fixes verify cross-fixture by re-running the modified assertion against existing trace snapshots (0/5); (c) **assertion-side fix surface is a peer fix-class to pipeline-side** with distinct verification economics. Forms post-WS-H fix-surface audit pair with S21 (S21 attribution + S22 economics). Operational corollary: when a workstream's gate-6 cites cross-fixture verification, the gate-7 cost depends on the fix surface — pipeline-side = 1/5 per replay; assertion-side = 0/5 per on-disk re-run. See `workstream_h_cold_start_reentry_root_cause.md` §16.4 + §17.

Each session contributes one or more transferable methodology insights that survive into the next session's discipline. **The discipline track record is itself a load-bearing artifact** — preserve it; document new insights as they accumulate. Cumulative running total: **21 insights** (#1-#16 prior + S16/S17/S18 step-4 + S19 step-5 + S20 step-8 + S21 step-5b + S22 step-9 arc-retirement).
