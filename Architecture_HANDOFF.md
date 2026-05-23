# Handoff — derive-not-detect branch (Architecture)

**Last update.** 2026-05-23 (WS-H step-9 arc close-out — WS-H FULLY RETIRED + S22 static-investigation-first protocol meta-finding).
**Branch.** `derive-not-detect` (HEAD = WS-H step-9 docs commit). Feature branch `rewrite/wicket-striker-this_over-canonical` deleted local + remote.
**Session ledger.** **60 cumulative commits** across five consecutive sessions on `derive-not-detect` lineage: 16 B-η + 8 C19-C24 + 8 C26-C31 + C32 docs + 10 §15 arc (9 feat + 1 docs) + 8 Workstream G + 1 pre-merge gitignore + 1 merge commit + 9 Workstream H (step-1 memo + P1 patch + step-4 close-out + step-5 memo + H1 patch + step-8 close-out + step-5b memo + Shape A patch + step-9 arc close-out). Layer 1.5 (36 ledger balls + 6 cross-field pairing + 3 D1 bowler-dispatch + 3 D2 WICKET-ATTRIB + 6 pending-cascade + 9 WS-H wickets_regressed guard + 4 WS-H γ-fow-name graceful-degradation = **67 cases**) + Layer 2 (30 balls) held on every commit. Derivation unit tests at 48/48. **Empirical-falsification budget: 2/5 remaining** (1/5 consumed across entire 9-step WS-H arc at step-7; load-bearing artifact = S22 static-investigation-first protocol verified at arc scale, plus S16/S17/S18 step-4 + S19 step-5 + S20 step-8 + S21 step-5b). **WS-H ARC FULLY CLOSED** — primary objective + step-5 + step-5b all CLOSED. D-post-FoW-striker 20 → 2 (step-3 P1); F939 SM-INNINGS-2-RESET 1 → 0 (step-7 H1); γ-fow-name `no_prev_striker` cohort F679+F948+F1017 + 4 bonus pre-existing across historical traces all closed (step-5c Shape A; gate-7 cross-fixture budget-neutral). γ-w-symbol parallel surface OUT-OF-SCOPE (deferred to workstream D rotation-root revisit). WS-G primary objective RETROACTIVELY DELIVERED via WS-H per insight #18 scope-separation.

**§15 fence count correction.** The post-merge `grep -c 'self.striker = None' files/score_manager.py` returns **7**, not the "8 invalidation-only writes" referenced in the original §15 fence documentation below. The discrepancy is descriptive shorthand; the structural fence invariant ("no non-canonical name writes") holds — non-None writes occur exclusively in the three canonical methods (`apply_striker_event:945`, `apply_striker_identity_resolved:980`, `apply_striker_identity_proposed:1211/1213`). Future docs should cite the structural invariant rather than the count.

## Architectural fence — post-Workstream-G (2026-05-23)

Building on the §15 fence (three canonical `self.striker` writers; canonical wicket dispatch; deterministic-rotation override removed), Workstream G adds the **PendingCascade lifecycle** as a fully observable state machine:

- **State.** `self._pending_post_wicket_cascade: list[PendingCascade]` — FIFO queue bounded at 3 (audit Q1).
- **Producer.** `apply_wicket_event` cascade-defer path enqueues when `event.new_batter` is None (Mitigation A captures pre-fallback `(prev_striker, prev_non_striker)`).
- **Consumers — drain hook.** `_attempt_pending_cascade_drain` runs at top of `_handle_warm` (the original f09fc38 wire-up) AND at C1-C6 COLD→WARM transitions (50af67e Surface B defense-in-depth).
- **Consumers — wipe sites.** `_clear_per_innings_sm_surface` (f09fc38) + W1-W4 cold-entry sites (50af67e Surface B). All wipes emit `POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START` with the pre-wipe queue state captured.
- **Terminal-state trace tags.** `POST-WICKET-CASCADE-DRAIN-FIRED` (resolved), `CASCADE-DRAIN-EXPIRED` (TTL hit), `POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START` (cold-entry wipe). Insight #17 mandate: every cold-entry reset path is empirically verified to emit a structured tag with positive trace evidence; silent `__init__` default-inits are eliminated by the W4 pre-`__init__` ordering at `set_innings_2`.

The PendingCascade lifecycle is regression-detected by `trace_eta_post_wicket_cascade_drains` (the η-bundle's single assertion). Baseline shift across the WS-H arc:
- `validate_surface_b_121222` (pre-P1) = 2 enqueues + 2 WIPED terminals (PASS).
- `validate_ws_h_step3_20260523_164642` (post-P1) = 2 enqueues + 2 DRAIN-FIRED terminals (F680, F858) + 0 WIPED + 0 EXPIRED (PASS).
- `validate_ws_h_step7_20260523_172140` (post-H1) = **5 enqueues + 4 DRAIN-FIRED + 1 CASCADE-DRAIN-EXPIRED + 0 WIPED** (PASS).

All three terminal classes empirically observed for the first time in the step-7 trace; η-bundle conservation invariant (`ENQUEUED = FIRED + EXPIRED + WIPED`) holds exactly. Cascade lifecycle is now fully exercised across its terminal-state space.

**Workstream G + H ARCS FULLY CLOSED.** WS-G closed the lifecycle gap at `50af67e` (Surface B; WIPED-BY-COLD-START tags wire up). WS-H closed the D-post-FoW-striker primary objective at step-3 (P1 `ef0860d`: team-change-corroboration guard on wickets_regressed branch; D-post-FoW-striker **20 → 2**, exceeds 5-10 prediction per insight #18 scope). WS-H closed step-5 at step-7 (H1 `832d376`: consensus-parity gate on `_team_changed` derivation site; **F939 SM-INNINGS-2-RESET 1 → 0**; S18 cascade-closure dividend structurally confirmed via sibling deferral count 2 → 3; S19 empirical-degeneracy held — zero positive `score_reset_from_progress` fires preserved under H1). WS-H closed step-5b at step-5c (Shape A patch `1dbba14`: γ-fow-name graceful-degradation on canonical-resolution alternate; **7 `no_prev_striker` FAILs across 5 traces → all closed** including 3 cohort F679+F948+F1017 + 4 bonus pre-existing on historical traces; 2 true-mismatch FAILs preserved as workstream D scope; 0 regressions). Composite-fix closure as side effect from step-3: γ-bowler-w FAIL × 4 → PASS (cascade DRAIN-FIRED enables D1's resolved bowler identity to propagate; S18 in WS-H memo §10).

**Trace assertion library baseline post-WS-H closure** (validate_ws_h_step7_20260523_172140 + 12 other on-disk traces):

- γ-fow-name: PASS on 11 of 13 traces; 2 remaining FAILs are true-mismatch class at validate_20260513_180911 F407 + validate_dckkr_20260522_063211 F1196 (workstream D rotation-root revisit scope).
- γ-w-symbol: FAIL × 4 baseline preserved on validate_ws_h_step7 (parallel surface — different read path; workstream D revisit scope).
- γ-bowler-w: PASS preserved across all traces.
- η-cascade: PASS preserved; all 3 terminal classes (DRAIN-FIRED + DRAIN-EXPIRED + WIPED-BY-COLD-START) now empirically observed in the step-7 trace.
- α/β/ε/compound/extras: all PASS preserved.

**Architectural-fence + fix-surface fence (post-WS-H).** Pipeline-side fix surface (P1, H1 at score_manager.py) remains §15-fence-correct. Assertion-side fix surface (Shape A at trace_session_assertions.py) is a peer fix-class per S21/S22 — distinct verification economics: pipeline-side gate-7 = 1/5 budget per empirical replay; assertion-side gate-7 = 0/5 per on-disk re-run. Future investigations should classify fix surface at gate-2 and route gate-7 verification accordingly.

**Next session: §11.3 surgical items 3-7** (Workstream F bowler misattribution, Per-batter-ledger conservation, Recent-Overs partial-render, phantom-runs root-localize). No WS-H follow-on workstream open. The architectural-fence invariants from WS-G + §15 are unchanged.

## Architectural fence — post-§15 (2026-05-22 evening, still active)

(The §15 fence below remains canonical for striker-write semantics. Workstream G extends it with the PendingCascade lifecycle in the preceding section; the §15 fence itself is unchanged.)

**Three canonical write paths for `self.striker`** (§13 / §13.8 / §13.8.1 in the design memo):

1. `apply_striker_event(event: StrikerEvent)` — ROTATION semantic (batters cross during a delivery). XOR rule 3+4 handles cricket double-swap cancellation.
2. `apply_striker_identity_resolved(name, source)` — AUTHORITATIVE identity write. Proceeds best-effort with `STRIKER-IDENTITY-CONFLICT` alert. Used by `_set_slot_pair` callers (post-wicket survivor, NAME-REJECTED recovery, cold-start init).
3. `apply_striker_identity_proposed(name, source)` — CONSERVATIVE-REFUSE identity proposal. Refuses when `self.striker` is set; accepts only when None. Used by `_identify_and_set` per-frame Scout/broadcast reads. Fires `STRIKER-IDENTITY-PROPOSAL-REFUSED` on refuse, `STRIKER-IDENTITY-PROPOSAL-ACCEPTED` on accept.

All 8 remaining `self.striker = None` writes are invalidation-only (cold-start invalidation / innings reset / NAME-REJECTED). No non-canonical name writes remain. **Any new code that writes `self.striker` directly is a regression. Future writes must route through ONE of the three canonical paths based on semantic.**

**Canonical wicket dispatch path** (§12 / §12.10): `apply_wicket_event(event: WicketEvent)` is the sole FoW + bowler-W writer + post-wicket striker-rotation cascade dispatcher. `_apply_wicket_fall_only` retained as thin shim that builds the WicketEvent and delegates to `apply_wicket_event`; full deletion deferred until partnership/slot-clearing have canonical paths.

**Deterministic-rotation override at `score_manager.py:4700-4736`** (was at `:4295-4325` pre-7c line range) **REMOVED.** Replaced by `apply_striker_identity_proposed` per §15 step 9 retry. The S12 non-discriminable-predicate-signature defect (C30b) surface is eliminated.

---

## §15 — Session continuation: triple-subsystem rewrite arc (2026-05-22 evening)

§15 arc structurally complete at commit (8/N) `1af2bd9`. Full retrospective + commit ledger + methodology insights in `files/docs/investigations/differential_testing_methodology_design.md` §17 and the matching section in HANDOFF.md. Summary:

**Surface drops (commit 7b `68acda4`):**
- Bowler-W-credit-failure 7 → 1 (-6)
- F-A-commit-lag 50 → 49 (-1) — cross-surface bonus from bowler-identity fidelity
- F-B-ad-occlusion 27 → 23 (-4) — same bonus mechanism

**Surface drops NOT achieved (Workstream G dependency):**
- C21b-symbol-revert: stays at 1 (10.5 wicket is Scout-extraction-timing not cold-start subcase)
- Multi-ball-compression: stays at 4 (per-event delta logic, not cold-start backfill)
- D-post-FoW-striker: stays at 20 (cascade structurally wired but 100% deferred — Scout new_batter primitive lag)
- Compound-with-wicket-token: stays at 2 (Scout timing again)

**Net surface count: 14 → 14.** Structural cleanup is real; empirical-drop-on-this-dump is not. Live-replay validation per §10.4 still mandatory.

**Next session priority #1: Workstream G investigation** (Scout-extraction timing + cold-start re-entry frequency + COLD-START-EXIT semantics redesign + §14.5 step 11 retry).

---

## 0. Session continuation — C19–C24 (workstream B closure, 2026-05-21 PM)

Eight commits landed after C18 in a single session focused on workstream B (UI surface-pair taxonomy + wicket-correctness γ-bundle). All Layer 1.5 + Layer 2 pre-commit hooks green across all 8 commits.

### 0.1 What happened

- **C14 validation fired on DCKKR 2026-05-21** (`validate_dckkr_20260521_155356`, ov 0.0 → 11.5, ~58 min wall). Two distinct CROSS-FIELD-PAIRING-REJECT events caught in production: F210 (backwards-overs, Δscore=+6/Δballs=-8) and F1015 (zero-time double-wicket, Δwkts=+2/Δscore=0/Δballs=0). C14 predicate is doing load-bearing work but caught defects of classes orthogonal to F-η. Sign-off accepted on "predicate correct, gate reachable, two Shape-B-class defects caught" basis.
- **Three trace-emission gaps surfaced**: DIRECT-SCORE-COMMIT = 0 firings (BOARD-side path not exercised in replay), `trace_beta_sm_wicket_dispatch` deleted from codebase between C15 authoring and HEAD, no typed wicket-event trace tags emitted. All three closed by C19A1–A5 (counterfactual comment tightening, trace_beta restoration, schema documentation, preflight tag-existence check).
- **Workstream B closed at the wicket-correctness γ-bundle baseline**: 3 new assertions (`trace_gamma_w_symbol_at_wicket`, `trace_gamma_fow_name_matches_striker_at_wicket`, `trace_gamma_bowler_w_increment_on_dispatch`) at C21/C22/C23 + family-level memo skeleton at C20 + gate-bundle codification + HANDOFF rewrite at C24. **Workstream D promoted to highest-priority unblocked workstream.**

### 0.2 Architectural-significance commits

| # | Commit | Scope | Outcome |
|---|---|---|---|
| 17 | `5a80b8f` | **C19A1** — tighten counterfactual framing on `legitimate_pair` predicate provenance | The 127-event DSC evidence is BACKWARD-LOOKING; DSC is BOARD-side independent of this SCORER-side gate. C19A1 makes that explicit. |
| 18 | `7557d47` | **C19A3** — restore `trace_beta_sm_wicket_dispatch` emission at `_apply_wicket_fall_only` | Tag was deleted between C15 authoring and HEAD. Restored as additive emission at score_manager.py:5334 with `resolution_src` payload differentiating P2 (event.dismissed) vs P3 (SM.self.striker fallback) attribution. |
| 19 | `ceeb4e0` | **C19A4** — schema note in `trace_and_detect_setup.md` | Tags live under `scorer.decisions[].tag`, not flat top-level `.tag`. Saves the next grep an hour. |
| 20 | `74e90dd` | **C19A5** — preflight tag-existence check (`scripts/preflight_validation_tags.sh`) | Surfaces commit-design drift before launch. Default tag set covers the 5 tags this validation cared about. |
| 21 | `e051cfa` | **C20** — `surface_pair_defect_class_family.md` skeleton (9 instance placeholders) | Family-level memo distinct from sm_as_orchestrator_design.md §12 — instance accretion moves to the new memo, §12 retains the structural theory. C20b (per-row populate) deferred. |
| 22 | `b327ed1` | **C21** — `trace_gamma_w_symbol_at_wicket` assertion (B1) | FAIL × 2 baseline on DCKKR (Rahul ov 5.0, Rana ov 8.0 W→· revert in this_over state). Nissanka's revert is UI-layer only — first forcing-function finding. |
| 23 | `6817481` | **C22** — `trace_gamma_fow_name_matches_striker_at_wicket` assertion (B2) | PASS × all detected wickets — internal-consistency invariant holds even when cricket reality diverges. Both pipeline surfaces stale at SAME striker pointer value — second forcing-function finding, scopes workstream D. |
| 24 | `4f79613` | **C23** — `trace_gamma_bowler_w_increment_on_dispatch` assertion (B3) | FAIL × 4 baseline. Surfaces em-dash sentinel for `pipeline.current_bowler` at 2/3 wicket frames — third forcing-function finding, BLOCKS C23b on D. |
| 25 | `c671cb2` | **C24** — gate bundle codification + HANDOFF rewrite | Wicket-correctness γ-bundle (3 assertions × wickets observed) supersedes `trace_beta_sm_wicket_dispatch` as cascade-closure signal. Workstream D promoted. |

### 0.3 Gate bundle baseline (validate_dckkr_20260521_155356)

```
Total: 5 PASS / 3 FAIL across 8 assertions.

Pre-existing (5 assertions, 2 still relevant to wicket-correctness):
  trace_alpha_bowler_runs_sum                      PASS  (flipped post-C14)
  trace_beta_sm_wicket_dispatch                    FAIL × 4 (existing assertion;
                                                   typed emission lands C19A3
                                                   — next replay validates)
  trace_epsilon_initial_striker                    PASS
  trace_compound_tokens                            PASS
  trace_extras_total                               PASS

New γ-bundle (3 assertions, all three test wicket-event correctness):
  trace_gamma_w_symbol_at_wicket                   FAIL × 2 (Rahul, Rana)
  trace_gamma_fow_name_matches_striker_at_wicket   PASS    (internal-consistency only)
  trace_gamma_bowler_w_increment_on_dispatch       FAIL × 4
```

The γ-bundle replaces `trace_beta_sm_wicket_dispatch` as the wicket-correctness gate signal. `trace_beta` tests dispatch OCCURRENCE; the γ-bundle tests dispatch CORRECTNESS across the three downstream invariants (W symbol, FOW name, bowler-W increment). Workstream D resolution should flip `trace_gamma_bowler_w_increment_on_dispatch` and (after C21b) `trace_gamma_w_symbol_at_wicket`. `trace_gamma_fow_name_matches_striker_at_wicket` will continue to PASS while the rotation root remains unresolved (internal-consistency invariant; cricket-vs-pipeline divergence is outside trace scope).

### 0.4 Three forcing-function findings — skeleton-then-assertion methodology

This session's transferable methodology insight: an instance-catalogue skeleton with placeholder rows is a forcing function for evidence-discipline. Each of the 3 γ-assertions surfaced a finding that observation alone did not produce:

1. **C21 — UI-layer vs state-layer disambiguation.** Nissanka's W→· revert at Obs 17b was in the WebSocket-render path, not the pipeline state. Trace state preserved W correctly at frame 855 position 4. §2.1 surface-pair scope refined: state-layer reverts (Rahul/Rana) vs UI-render-layer reverts (Nissanka) are distinct sub-cases.
2. **C22 — both-surfaces-stale-at-same-value.** `trace_gamma_fow_name_matches_striker_at_wicket` PASS × all wickets. Pipeline's two adjacent surfaces (`ball_event.striker_this_ball` at wicket frame, `pipeline.striker` at preceding frame) stay aligned in error because rotation-lock corrupts both simultaneously. Cricket-vs-pipeline divergence is structural, not surfaceable from trace data alone.
3. **C23 — em-dash sentinel at wicket frames.** Pipeline's `current_bowler` reads as literal `—` placeholder at 2/3 captured wicket frames (Rahul fr 400, Rana fr 679; only Nissanka fr 855 had a real bowler name). The rotation-lock-starvation root extends to BOTH batter-striker AND bowler-identity pointers at wicket boundaries. Direct consequence: C23b cannot land cleanly until D resolves the em-dash case.

### 0.5 Workstream D scope (next session's entry point)

**Objective:** localize and close the rotation-lock-starvation root that causes both batter-striker AND bowler-identity pointers to be stale (or em-dash) at wicket-event boundaries.

**Entry data:**
- `files/logs/deliveries/validate_dckkr_20260521_155356/` — full captured artifact (trace JSONL, pipeline.log, scout dump, mp4)
- `validate_dckkr_replay_observations.md` — 21-frame UI observation log, Obs 2/3/9/16/17/18/19/21 cover the rotation-lock and bowler-identity moments
- C19A3's `resolution_src` payload on `trace_beta_sm_wicket_dispatch` discriminates P2 (event.dismissed) vs P3 (SM.self.striker fallback) attribution paths
- `state_mutation_site_catalogue.md` (C9) — candidate sites for bowler-identity-lock failures
- `surface_pair_defect_class_family.md` §2.5 + §2.6 (skeleton rows; C20b populate produces evidence anchors)

**Next session sequence:** read the three forcing-function findings above, examine `resolution_src` distribution across the 4 captured wickets, examine `pipeline.current_bowler` transitions for em-dash entry/exit timing, derive root-localization hypotheses per the standard temporal-coupling investigation methodology (C10 brief + C9 mutation-site catalogue), with §12.4 detection methodology + §12.6 audit obligation cross-referenced.

### 0.6 Deferred work tracked elsewhere

- **C20b** — per-row (a)-(e) populate of `surface_pair_defect_class_family.md` §2.1–§2.9 with full evidence from Obs N anchors. Independent of D; can land anytime.
- **C21b** — W→· revert site identification in the symbol-commit path. Most plausible candidate per static analysis: `_rewrite_eyes_this_over_from_event` at `score_manager.py:695`. Needs fresh replay with C19A3 emission firing for per-frame `this_over` diff inspection.
- **C23b** — bowler-W increment in the actual wicket-dispatch path. The `_apply_wicket_fall_only` function is NOT reached for the captured wickets (they dispatch via `ABSORBED_LEGAL` gap_finalize_wicket per docstring). BLOCKED on workstream D resolving the em-dash bowler-identity case.
- **C29b (or successor C-number)** — Scout prompt schema extension to emit a structured `dismissed` / `dismissed_batter` field on WICKET-shaped frames. Closes the Scout-contract gap at the source. Non-overlapping with H-D2-Layer-1a (downstream `_derive_dismissed_name`). OUT of workstream D scope; candidate for a separate workstream surface. Empirical basis: `workstream_d_rotation_root_investigation.md` §3.4b cross-fixture survey, 0/182 wicket-signal frames across 4 substantive captures.
- **Workstream surface E candidate — phantom-wicket detection.** F1017 (per `validate_dckkr_20260521_155356`) emits POST-WICKET-ROTATION on `Axar Patel` against cricket truth (Obs 21 broadcast strip shows Axar at-the-crease at replay-end). Defect class is qualitatively distinct from F855/F983 misattribution: no cricket wicket occurred, a dismissal event was fabricated. Root-localization needed on the wicket-event-detection path (`ball_detector.detect` or upstream wicket-signal aggregation), not the dismissed-name derivation path that H-D2 lives on. OUT of workstream D scope. Empirical basis: `workstream_d_rotation_root_investigation.md` §3.4c.3.
- **§12 catalogue extension — STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC override.** Fourth instance of the dual-state-write defect class catalogued in `sm_as_orchestrator_design.md` §12 (after F-α-shadow / F1-B-ε / B-η-FC5 / D1-BW07-bowler-em-dash). Catalogue-entry-only follow-up commit; out of D-scope. Empirical basis: `workstream_d_rotation_root_investigation.md` §3.4c.4.
- **§12 catalogue extension — non-discriminable-predicate-signature defect class (S12).** Peer entry to dual-state-write: when two cases (one regression-protected, one investigation-target) arrive at the same site with the same observable predicate, single-site fix is structurally impossible without plumbing (lookahead / persistence / drift detection). Catalogue-entry-only follow-up commit; out of D-scope. Empirical basis: `workstream_d_rotation_root_investigation.md` §3.4d.5.
- **score_manager.py:4411 STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC override gate — explicitly ruled out as D2 fix candidate.** Plumbing-required (discriminator); not single-site. Gate is load-bearing protection against DC-vs-KKR ball-4.6 regression (Rahul-dismissed-attribution case). Re-investigation authorized only if WICKET-ATTRIB fix at `test_pipeline.py:13063` proves insufficient on next replay — equivalent to consuming the first empirical-falsification slot in the D chain's 5-cap budget. Empirical basis: `workstream_d_rotation_root_investigation.md` §3.4d.1–3.4d.6.

### 0.7 Methodology track record — 7 transferable insights across 3 sessions

Pattern continues at the accumulation rate flagged in prior HANDOFFs. Each session contributes 1–3 transferable insights:

- **F1 session (3 sessions back):** F1 cascade-closure (one-edit fix closes N bug classes), §7.2 gate 7 (cross-fixture verification) baked into the audit framework.
- **B-η session (2 sessions back):** Static-analysis-with-predicate-trail methodology (full cascade-root localization at near-zero commit cost), falsification-chain-as-architectural-finding, dual-state-write defect class confirmed across 3 instances.
- **C19-C24 session (this one):** Commit-design drift (briefs can predict flips on tags deleted between authoring and HEAD; preflight tag-existence check needed) + budget-class mismatch (memo work needs 8–12 calls, code work fits 5) + skeleton-then-populate forcing function (instance-catalogue skeletons surface observation-discipline gaps when populate-time work discovers Obs entries lack data for (a)-(e) axes) + UI-layer vs state-layer disambiguation via trace + both-surfaces-stale-at-same-value (internal-consistency PASS when rotation-lock corrupts adjacent surfaces in sync).

7 transferable methodology insights total. **The discipline track record is itself a load-bearing artifact.**

---

## 0a. Session continuation — C26–C31 (workstream D fix chain, 2026-05-21 evening)

Eight commits landed after C25 in a focused chain on workstream D's two hypotheses + their sub-findings. Pre-commit Layer 1.5 + Layer 2 green across all 8. **0/5 empirical-falsification budget consumed across the entire chain** — all advances static (predicate-trail, cross-fixture grep, structural-surface check).

### 0a.1 What happened

- **C26 memo skeleton** — `workstream_d_rotation_root_investigation.md` (~7.5kB) opened with 2 hypotheses (H-D1 bowler em-dash root; H-D2 striker fallback monoculture) + sub-finding S1 (γ-bundle invisibility of striker-path wickets like F983). Cross-references §2.5 / §2.6 of `surface_pair_defect_class_family.md` + C9 BW07 row + C19A3 `resolution_src` schema.
- **C27 D1-prelim** — static gates 1/2/3 audit on 3 candidates (A defer-clear / B re-source-from-tracker / C dual-source-consensus). All three survive gates. Candidate C selected on regression-risk surface (lowest of the three). S3 (methodology cross-validation: H-D1 reaches the same C9 BW07 row that retired B-θ investigation flagged) + S4 (budget unconsumed).
- **C28 D1-fix code** — Candidate C landed at `_apply_wicket_fall_only` (`score_manager.py:5262–5286` + trace_beta emission). β plumbing addition: `score_mgr._bowler_tracker = bowler_tracker` at `test_pipeline.py:7334` + SM `__init__` slot. New trace tag `BOWLER-DISPATCH-FALLBACK-FIRED` registered in `KNOWN_TAGS`. Permanent test at `test_bowler_dispatch_fallback.py` (3 cases) wired into Layer 1.5.
- **C29 D2-prelim cross-fixture** — Scout `dismissed` field absence verified at 0/182 wicket-signal frames across 4 substantive captures (GTRR + 2× DCKKR + validate_20260520). H-D2-Layer-1 bifurcates into Layer 1a (downstream `_derive_dismissed_name`) + Layer 1b (Scout prompt schema extension). S5 (Scout-contract gap distinct from rotation-lock-starvation root) + S6 (predicate-trail extends beyond temporal-coupling) + S7 (budget unconsumed).
- **C30 D2-prelim refinement** — Signal 1 (tracker LEADER cross-check) statically falsified at F855/F983/F1017. S8 (deterministic-rotation override is BW07-analog for striker side) + S9 (F855 → F983 cascade closure; second instance of F1-pattern) + S10 (F1017 phantom-wicket split off to workstream surface E candidate). Predicted-flip claim reformulated.
- **C30b D2-fix structural-surface check** — override gate at `score_manager.py:4411` ruled out as fix surface due to non-discriminable predicate signature against DC-vs-KKR ball-4.6 regression case. S11 (signal/site decoupling pattern) + S12 (non-discriminable-predicate-signature defect class). WICKET-ATTRIB at `test_pipeline.py:13062–13068` confirmed single-site no-plumbing surface.
- **C31 D2-fix code** — single-site change at WICKET-ATTRIB with helper extraction (`_attribute_dismissed_with_broadcast_override` at module scope). §3.4e memo addendum corrected the broadcast-striker access path (`_pending_bcast_striker_key`, not `card["broadcast_striker"]`). New trace tag `WICKET-ATTRIB-BROADCAST-OVERRIDE-APPLIED` registered. Permanent test at `test_wicket_attrib_broadcast_override.py` (3 cases) wired into Layer 1.5.
- **C32 docs close-out** — this commit.

### 0a.2 Architectural-significance commits

| # | Commit | Scope | Outcome |
|---|---|---|---|
| 26 | `85b3169` | **C26** — workstream D investigation memo skeleton | 2 hypotheses (H-D1 / H-D2) + S1 sub-finding; D-chain audit-trail anchor. |
| 27 | `6d0bac9` | **C27** — D1-prelim static gates on 3 candidates | Candidate C selected; S3 (methodology cross-validation) + S4. |
| 28 | `7553473` | **C28** — D1-fix dual-source consensus at `_apply_wicket_fall_only` | Em-dash em-dash sentinel closed at over-end-coincident wickets; β plumbing for tracker access. |
| 29 | `151ee49` | **C29** — D2-prelim cross-fixture Scout-dismissed absence | 0/182 wicket-signal frames; H-D2-Layer-1 bifurcation; S5/S6/S7. |
| 30 | `d7c7bdf` | **C30** — D2-prelim refinement | Signal 1 falsified; cascade-closure + phantom-wicket sub-findings; S8/S9/S10. |
| 30b | `4c50344` | **C30b** — D2-fix structural-surface check | Override gate ruled out; WICKET-ATTRIB site confirmed; S11/S12. |
| 31 | `e04324f` | **C31** — D2-fix broadcast-vs-deterministic override at WICKET-ATTRIB | Helper extraction; single-site fix; §3.4e access-path correction. |
| 32 | (this) | **C32** — HANDOFF + Architecture_HANDOFF close-out | Docs commit; chain wrap. |

### 0a.3 Predicted-flip table (gated on next DCKKR replay)

```
Pre-fix baseline (C24)                            Post-C31 predicted (next replay)
  trace_gamma_bowler_w_increment_on_dispatch:       FAIL × 4   →   FAIL × 2
    F400 + F679 close via D1 tracker fallback (over-end-coincident em-dash window).
    F855 + F1017 still FAIL pending downstream cascade closure + workstream E.
  trace_gamma_w_symbol_at_wicket:                   FAIL × 2   →   PASS
    F855 closes via D2 broadcast-override at WICKET-ATTRIB (direct).
    F983 closes via S9 cascade (F855 close repairs pipeline's at-the-crease set).
    F1017 unchanged — split off to workstream surface E per S10 phantom-wicket class.
  trace_gamma_fow_name_matches_striker_at_wicket:   PASS       →   PASS (unchanged)
    Internal-consistency invariant — tests pipeline-self-agreement, not cricket truth.
```

If predicted flips land: C23b unblocks; close D chain in a C33-tier docs commit. If predicted flips do not land: first empirical falsification for the D chain (budget cap 5/5 still open); escalation path is plumbing at `score_manager.py:4411` (the override gate ruled out as single-site at C30b but the empirical falsification authorizes the escalation per §3.4d.6).

### 0a.4 Sub-findings index (S5–S12, all static — falsification budget unconsumed)

| Sub-finding | Description | Source |
|---|---|---|
| S5 | Scout-contract gap is architecturally distinct from rotation-lock-starvation root. Two non-overlapping fixes (Layer 1a / Layer 1b). | C29 §3.4b |
| S6 | Predicate-trail extends beyond temporal-coupling defect class to Scout-contract gaps. | C29 §3.4b |
| S7 | D-chain empirical-falsification budget unconsumed (~2.6k frames surveyed read-only). | C29 §3.4b |
| S8 | Trackers not independent of rotation-lock-starvation root. Deterministic-rotation override is BW07-analog for striker side. | C30 §3.4c.1 |
| S9 | F855 → F983 cascade closure. Second instance of F1-session cascade-closure-via-one-edit pattern. | C30 §3.4c.2 |
| S10 | F1017 phantom-wicket detection — workstream surface E candidate. | C30 §3.4c.3 |
| S11 | Signal/site decoupling pattern. Predicate-trail reformulation moves the predictive signal but not necessarily the fix site. | C30b §3.4d.4 |
| S12 | Non-discriminable-predicate-signature defect class. Single-site fix structurally impossible without plumbing when two cases share an observable predicate. | C30b §3.4d.5 |

### 0a.5 Methodology track record — 11 transferable insights across 4 sessions

C26–C31 chain contributes 4 new insights: S6, S9, S11, S12 (see §0a.4). Combined with the prior 7 insights documented in §0.7, the running total stands at **11 transferable methodology insights**. The discipline track record continues to accumulate at the 1–3-insights-per-session rate flagged in prior HANDOFFs.

Notable: S9 is the second instance of the F1 cascade-closure-via-one-edit pattern (F1 was first, 3 sessions back). The pattern's reproducibility is itself a meta-finding — Meta-finding #1 (static-analysis-at-near-zero-commit-cost) is the methodology; F1 + S9 are its first two reproductions.

### 0a.6 Deferred-work index update (additions from C26-C31)

- **C29b (or successor C-number)** — Scout prompt schema extension to emit `dismissed` / `dismissed_batter` field. Out of D-scope; candidate for new workstream surface.
- **Workstream surface E** — phantom-wicket detection (F1017 case). Root-localization needed on the wicket-event-detection path.
- **§12 catalogue extension #1** — `STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC` override as the 4th dual-state-write instance.
- **§12 catalogue extension #2** — S12 non-discriminable-predicate-signature as a new peer defect-class entry.
- **C23b** — bowler-W increment in wicket-dispatch path. Unblocked once next replay validates D1 + D2-Layer-1a predicted flips.

---

## 1. Workstream goal

Improve the cricket scoreboard pipeline's correctness by replacing *speculative deletion + speculative fixes* with **empirically-grounded audit-driven discipline**. Every classification (bug-class hypothesis, NOT-A-DEFECT verdict, "already addressed" verdict, **defect-class label**) is a hypothesis pending empirical verification against captured trace data + production pipeline.log.

The §7 "candidate deletion list" framing in `sm_as_orchestrator_design.md` remains officially retired (prior session). The current framing: **empirically-grounded bug classes with their own design memos, per-class fix sequencing, and trace-session assertions as regression detectors. New this session: defect-class catalogue at §8 (dual-state-write pattern) — C17 deliverable.**

---

## 2. Session architectural-significance milestone

**Shape B cross-field pairing gate (commit `ad151fd`) at `apply_scorer_decision` (`test_pipeline.py:4517`)** closes the B-η F304 cascade root that produced the DC vs KKR session's overlay corruption + downstream wicket-dispatch failures.

**Cascade root concretely localized via static analysis + production pipeline.log audit:**

```
F302 TRACK score: 45 → 49 (post-event immediate, grace=1)    -- legitimate ball
F302 TRACK overs: 4.4 → 4.5 (fast-confirm, natural overs)
F303 POISONED                                                 -- upstream block
F304 TRACK score: 49 → 54 (post-event immediate, grace=1)    -- CASCADE ROOT (FC5)
F304 TRACK overs: 4.5 → 6.3 (post-event immediate, grace=0)  -- CASCADE ROOT (FC5)
```

The `(post-event immediate, grace=N)` suffix is the FC5 log signature from `consistent_tracker.py:304-305`. The mechanism is the **dual-state-write defect class**: two parallel state surfaces with different invariants — `sb._tracker.confirmed` (weaker, permissive `_is_suspicious`) admits the bad overlay reading at F304; SM `_handle_warm` streak gate (stronger, `_BALLS_JUMP_TOLERANCE=3`) rejects when SM reads the proposal from `sb._inn`. Both surfaces stay live → f318 divergence signature `tracker_score=54 tracker_overs=6.3` vs `sm.self.overs=4.5`.

**Cross-fixture preservation:** 127/127 benign DIRECT-SCORE-COMMIT firings (GTRR 80 + DCKKR 47) satisfy the `legitimate_pair(d_score, d_balls, d_wickets)` predicate that Shape B uses to admit/reject. F304 fails (d_balls=10, d_score=+5, d_wickets=0). The fix is empirically-anchored on both sides of the gate boundary.

---

## 3. The two meta-findings to carry forward

This session produced two architectural insights that join F1's cascade-closure (prior session) as the workstream's accumulating discipline track record:

### 3.1 Static-analysis methodology produces full cascade-root localization at near-zero commit cost

The chain **C9 + C10 + C11 + C12 + C12.5b** produced:
- 8 static falsifications (zero behavior change)
- Concrete F302/F304 localization via production `/tmp/pipeline.log` parse (C12.5b — zero-commit)
- Full pairing-criterion derivation with 127/127 cross-fixture empirical verification

Cost: 5 docs commits + 1 instrumentation commit (C6's DIRECT-SCORE-COMMIT). Behavior change: zero.

Followed by **C13 audit + C14 fix + C15 permanent gate-6 test**: 3 functional commits.

**The methodology distinct from "instrument-replay-then-fix"**:
- "instrument-replay-then-fix" costs one diagnostic commit per hypothesis (the F1 session pattern)
- "static-analysis + predicate-trail + pipeline.log audit" costs one docs commit per hypothesis-class (this session pattern)

The static-analysis methodology is the right tool for **temporal-coupling defect classes** that captured-replay flattens. Captured-replay remains canonical as a **falsification mechanism** and **regression-detection substrate** (per `temporal_coupling_investigation_brief.md` §12.4) — it does not drive root-localization for this defect class.

### 3.2 Falsification cascade as methodology signal-of-correctness

This session: **5 empirical falsifications + 8 static falsifications + 1 acceptance**. The discipline rule "every classification is a hypothesis pending empirical verification" produces a falsification cascade BY DESIGN.

The **5-empirical-falsification budget cap** (per C9 §11 + C10 §1.2) ensures the cascade terminates productively. Without that cap, the discipline could spiral open-loop. Without the static-vs-empirical distinction (per C10 operator directive), the chain would have hit the cap at C11 and retired the methodology prematurely.

**Architectural reframe:** a complete falsification chain is an architectural finding, not a failure. Document each chain's meta-finding in HANDOFF alongside positive cascade-closure findings.

---

## 4. What we did (commit chain)

Sixteen commits this session. Layer 1.5 + Layer 2 gates held on every one.

| # | Commit | Scope | Outcome |
|---|---|---|---|
| 1 | `b49e48b` | B-η instrumentation pass (3 trace tags + replay scaffold) | C6 instrumentation; FRAME-TRUST-GATE / OVERS-JUMP-STREAK-STATE / POISON-STREAK-AT-COMMIT |
| 2 | `e3171eb` | Replay-scaffold warm-seed mode | f304-anchor reproduction setup |
| 3 | `86299e0` | B-η memo §1-§9 (5 falsifications documented) | First memo + first 5 falsifications |
| 4 | `78b4835` | LLM-extractor fallback (replay-only) | f303/f304 LLM reads recovered |
| 5 | `ac06fa6` | B-η memo §10 (cascade-root pivot) | Link D hypothesis surfaced |
| 6 | `237d227` | DIRECT-SCORE-COMMIT instrumentation + GTRR fixture | 48 + 81 firings, no anomaly observed in replay |
| 7 | `e19f72a` | B-η memo §11-§13 (5th falsification + strategy pivot) | Investigation-strategy pivot to static analysis |
| 8 | `a99d82c` | C8 brief reframe (Step 1 retargeted) | Captured-replay-drives-investigation retired |
| 9 | `af19dd2` | C9 state-mutation site catalogue (38 sites + 2 callbacks) | Static catalogue surfaces async-on-lock candidate |
| 10 | `2df4061` | C10 temporal-coupling brief (hypothesis #6) | on_lock async-decoupling proposed |
| 11 | `5833857` | C11 predicate semantics — 4 static falsifications | FC1/FC4/FC5 narrowed via static analysis |
| 12 | `b6e3c70` | C12 overs-side closure — 3 more static falsifications | Score-side localized; overs-side narrowed |
| 13 | `c05c4b6` | C12.5b pipeline.log audit | Both halves localized at F302/F304 via TRACK log signatures |
| 14 | `639fa4a` | **C13 §7.2 7-gate audit on 4 shapes — Shape B selected** | Audit memo with empirical pairing criterion |
| 15 | `ad151fd` | **C14 cross-field pairing gate at apply_scorer_decision** | Cascade root closed; 6/6 behavioral PASS |
| 16 | `770db98` | **C15 permanent gate-6 test + baseline + predicted-flip claim** | Pre-commit L1.5 expanded to 36+6 |

---

## 5. Pipeline architecture (next-agent essentials)

### 5.1 Top-level flow (unchanged from prior session)

```
Vision (Scout VLM)
  → extract_regex.parse_strip (regex) OR eyes/agent.Extractor.extract (LLM fallback)
  → test_pipeline.run_test main loop
  → apply_scorer_decision  ← C14 cross-field pairing gate sits HERE before sb.set calls
  → ScoreManager.on_frame (the SM)
  → Scoreboard.set (sb.set bottleneck; ConsistentReadTracker.update inside)
  → WebSocket UI payload (build_full_payload at output boundary)
```

**Key separation**: `ScoreManager` (SM) maintains its own state (`self.striker`, `self.score`, `self.overs`, ...). The `Scoreboard` maintains its own state (`scoreboard.batting_card`, `scoreboard.bowling_card`, `scoreboard._inn`). **These two layers can diverge** — this session's B-η cascade root was a dual-state divergence at F302/F304 between `sb._tracker.confirmed` and SM's `_handle_warm` invariants.

### 5.2 The 5-primitive contract (unchanged)

The pipeline derives UI state from five primitives:
- `score` (int)
- `wickets` (int)
- `overs` (decimal like `5.3`)
- `bat1_name`, `bat2_name` (str)
- `bowler_name` (str)

Plus `extras_type` (event-level) and `broadcast_extra` (frame-level WD/NB OCR signal). Parallel fields with different semantics per §7.5.

### 5.3 ConsistentReadTracker fast-confirm paths (new architectural surface — formally documented this session)

`eyes/consistent_tracker.py` is the per-field consensus tracker called from `sb.set`. **Five fast-confirm paths** that can commit a value on a single read:

| # | Site | Trigger | Decrements grace? |
|---|---|---|---|
| FC1 | line 114 — DRS grace | `_post_gap_grace > 0` AND `_is_drs_pattern` matches | No |
| FC2 | line 228 — batter natural increment | `_is_natural_batter_increment` matches | No |
| FC3 | line 252 — bowler natural increment | `_is_natural_bowler_increment` matches | No |
| FC4 | line 273 — match-overs natural increment | `_is_natural_overs_increment` matches (X.Y→X.(Y+1) or X.5→(X+1).0) | No |
| FC5 | line 294 — **post-event grace** | `_post_event_grace > 0` AND `not _is_suspicious` | YES (per fire) |

**`on_ball_event()` at line 786** sets `_post_event_grace = 2` on every legal-ball commit. **This is the FC5 grace-priming mechanism that produces the F302→F304 cascade.**

### 5.4 Cross-field pairing gate (C14, new this session)

`apply_scorer_decision` at `test_pipeline.py:4517` now contains a cross-field pairing gate that rejects single-frame commits whose `(Δscore, Δballs, Δwickets)` tuple violates the `legitimate_pair` predicate:

```python
legitimate_pair(d_score, d_balls, d_wickets) ≡
    (d_balls == 1 AND 0 ≤ d_score ≤ 7 AND d_wickets ∈ {0, 1})  -- legal delivery
  OR
    (d_balls == 0 AND 0 ≤ d_score ≤ 5 AND d_wickets ∈ {0, 1})  -- extras-only
```

On rejection: emits `[CROSS-FIELD-PAIRING-REJECT]` log + `CROSS-FIELD-PAIRING-REJECT` trace tag + applies cleanup + returns. The streak-gate / consensus paths handle the proposal on subsequent frames.

**Coverage caveat:** the gate is at `apply_scorer_decision`'s DIRECT-path. Two other sb.set call sites are NOT gated:
- `test_pipeline.py:8986+` (catch-up branch — after `OPEN-SCOUT-LOOP` resume)
- `test_pipeline.py:11750` (end-of-over hook)

Per the operator's C14 directive: ship the narrow closure. If C15's predicted flip materializes on next session, the narrow gate is sufficient. If not, **C19 extends coverage with empirical justification on disk**.

### 5.5 Queue B (unchanged) — canonical 3-way-race resolver

`_pending_bowler_ball_credits` at `score_manager.py:5283` (producer) and `:5714` (consumer). F-α-queue extension at ABSORBED_LEGAL events when bowler_name=None.

### 5.6 Trace infrastructure (extended this session)

New trace tags this session, all registered in `files/trace_emitter.py` KNOWN_TAGS:

- `FRAME-TRUST-GATE` (C6) — at `_decompose_multi_ball` entry; observability for multi-ball gap commits
- `OVERS-JUMP-STREAK-STATE` (C6) — both accept and reject branches of the streak gate
- `POISON-STREAK-AT-COMMIT` (C6) — at gap-commit time
- `DIRECT-SCORE-COMMIT` (C12) — at sb.set bottleneck, per score-write
- `CROSS-FIELD-PAIRING-REJECT` (C14) — at apply_scorer_decision gate, per illegitimate-pair reject

### 5.7 Test harness layers (extended this session)

| Layer | File | Purpose | Pre-commit gate |
|---|---|---|---|
| L1.5 | `files/tests/test_sm_derivation_ledger.py` | **36-ball ledger + 6 cross-field pairing cases** (NEW) | YES |
| L2 | `files/tests/test_pipeline_captured_replay.py` | 29-ball ledger-matched commits, real captured Scout dump | YES |
| C15 gate-6 | `files/tests/test_cross_field_pairing_gate.py` | 6 behavioral cases for Shape B's accept/reject boundary | Via L1.5 import |
| Trace assertions | `files/tests/trace_session_assertions.py` | Session-aggregate invariants | runner only |
| Per-ball assertions | `files/tests/symptom_class_assertions.py` | 12-class symptom library | via L2 |

**Pre-commit hook** at `.git/hooks/pre-commit` now **prefers the project venv Python** (`files/.venv/bin/python`, 3.12) over system `python3` (3.9). Required because C15's cross-field test imports `apply_scorer_decision` → `eyes/agent` → `int | None` (3.10+ syntax). **Hook is local-only (gitignored); C18 will ship a tracked setup script.**

### 5.8 Feature flags (unchanged)

- `SM_INLINE_MULTI_BALL` (default off)
- `SM_POST_WICKET_SLOT_DIFF` (default off)
- `USE_OPEN_SCOUT` / `USE_OPEN_SCOUT_SPANS`

---

## 6. §7.2 audit checklist (standing precondition — 7 gates; refined this session)

Before any §7 deletion OR fix commits:

1. **Enumerate all callers** of the symbol under change (Grep, exhaustive).
2. **Classify each caller** (init / transition / preserved / consumer / producer / **async**).
3. **Cross-reference with adjacent state mechanisms** (queues, drains, tracker callbacks, archive hooks, **dual-state surfaces**). Enumerate every race ordering.
4. **Equivalence proof** for proposed replacement.
5. **State variable lifecycle** — reset / clear / accumulation points.
6. **Predicted flip gate** — predict the assertion-library flip count BEFORE the dry-run, citing **concrete frame numbers** from captured trace data + production pipeline.log. Gate 6 applies recursively to ALL classifications.
7. **Cross-fixture verification** — after the fix lands, replay against captured data + run trace-session assertions to check which OTHER bug-class hypotheses still reproduce. **Or use the cross-fixture data for empirical predicate-criterion derivation** (C13 §2 introduced this: 127/127 firings across GTRR + DCKKR validated `legitimate_pair`).

**Track record extended this session:**
- C13 first **deep multi-shape audit** in the chain (4 shapes A/B/C/D against all 7 gates, with empirical pairing-criterion derivation)
- C10 §3 demonstrated **static gate-1/2/3 application** can falsify a hypothesis at zero cost (on_lock async-decoupling disproved by reading observe() callsites)
- C14 demonstrated **gate-6 closure via production pipeline.log audit** (no instrumentation commit needed when the operator-side artifact is on disk)

**New discipline rule (operator directive at C10):**

- **Empirical falsification** counts against budget (5-cap per defect-class chain)
- **Static falsification** does NOT count against budget (zero-cost; apply liberally)

This distinction enabled the C11/C12 chain to surface 8 static falsifications without hitting the methodology-retirement trigger.

---

## 7. Trace-session assertions (regression detectors — unchanged from prior session)

Five empirically-grounded invariants. Baselines:

| Assertion | Bug class | DCKKR (pre-fix) | GTRR baseline | Predicted post-C14 |
|---|---|---|---|---|
| `trace_alpha_bowler_runs_sum` | B-α / B-θ | FAIL gap=4 | FAIL (pre-F1) | gap reduces or PASS |
| `trace_beta_sm_wicket_dispatch` | B-β / F-η cascade | FAIL — 3 misses (f371, f521, f636) | FAIL — 2 misses | **PASS** (predicted) |
| `trace_epsilon_initial_striker` | B-ε | PASS | FAIL (pre-F1) | PASS (unchanged) |
| `trace_compound_tokens` | Compound `Wd+N` | PASS | FAIL (pre-F1) | PASS (unchanged) |
| `trace_extras_total` | UI extras_total | PASS | FAIL (UI render layer) | PASS (unchanged) |

Runner: `python files/scripts/run_trace_session_assertions.py [TRACE_PATH]`. `SESSION_CONTEXT` map.

---

## 8. What's pending

### 8.1 Operational gate (not engineering)

**Natural production session.** Run the pipeline normally on the next match. The session's trace gets captured automatically. C14 + C15 gate-6 test are in production code.

### 8.2 Validation step (after operational gate)

1. Add the new session's filename stem to `SESSION_CONTEXT`.
2. Run `python files/scripts/run_trace_session_assertions.py logs/trace/<NEW_SESSION>.jsonl`.
3. Observe whether `trace_beta_sm_wicket_dispatch` flips PASS.

**Two outcomes:**
- **YES:** F-η cascade closure confirmed end-to-end. Workstream cycle complete. C19 = next-session HANDOFF documenting closure.
- **NO:** Sixth empirical falsification. C19 = extend Shape B coverage to `test_pipeline.py:8986+` (catch-up branch) and `:11750` (end-of-over hook), with the empirical justification (trace_beta still fails despite C14) on disk.

### 8.3 Deferred latent fixes (no current empirical pressure)

- **B-ι (locked-SM-state prevents resync)**: original §7.2 plan was separate memo; per dual-state-write pattern + C14 coverage, may collapse as cascade symptom. **Wait for next session's trace_beta verdict before opening B-ι memo.**
- **B-θ (over-boundary bowler credit)**: same — may collapse if `trace_alpha` gap reduces post-C14.
- **F-α-rotation**, **`SM_INLINE_MULTI_BALL` flag flip**, **`SM_POST_WICKET_SLOT_DIFF` flag flip**, **S4a step (ii) Path B deletion**, **`_PENDING_BOWLER_BALL_CREDIT_MAX_LAG` further tightening** — unchanged from prior session.

### 8.4 Shape C dual-state-write unification — DEFERRED engineering workstream

Per C13 §5 audit: Shape C (route `sb._inn` writes through SM `_handle_warm` semantics) is the architecturally cleanest answer but cannot be statically audited to gate-4/7 closure. **Deferred as a follow-up engineering workstream** if Shape B's narrow coverage proves insufficient (sixth empirical falsification trigger).

### 8.5 §12 dual-state-write defect-class catalogue (C17 — landed)

`sm_as_orchestrator_design.md` §12 — new section catalogueing the three confirmed instances of the dual-state-write pattern:

1. F-α-shadow (F1 session): `sb._inn["bowling_card"]` vs `sb.bowling_card`
2. F1/B-ε (F1 session): `card.get("broadcast")` vs `card.get("broadcast_striker")`
3. B-η/FC5 (this session): `sb._tracker.confirmed` via FC5 vs SM `_handle_warm` streak gate

Per C13 §9: catalogue entry is mandatory output of this session regardless of which Shape ships. To be drafted in C17.

### 8.6 Setup-script for pre-commit hook (C18 deliverable)

Pre-commit hook lives at `.git/hooks/pre-commit` (gitignored). C15 modified it to prefer venv Python. Fresh checkouts will silently use system `python3` and L1.5 will fail with `int | None` syntax error.

**C18 ships `scripts/setup_precommit.sh`** (or equivalent) that installs the hook with venv preference. HANDOFF references this script as the one-time fresh-checkout setup action.

### 8.7 UI render layer (separate workstream — unchanged)

- B-γ Recent Overs panel drops entries
- B-δ UI bottom-strip striker
- `trace_extras_total` UI inconsistency

Out of scope for SM/pipeline workstream.

---

## 9. Key files for next agent

### 9.1 Production code (touch carefully)

- `files/test_pipeline.py` — main pipeline. **NEW: C14 cross-field pairing gate at `apply_scorer_decision:4517`**. Critical sections:
  - `:4356` apply_scorer_decision (entry)
  - `:4517` **C14 gate** (cross-field pairing reject)
  - `:7211-7234` bowler/striker tracker on_lock callbacks (synchronous per C10 §3.4)
  - `:8986+` catch-up branch — NOT covered by C14 gate
  - `:11750` end-of-over hook — NOT covered by C14 gate
  - `:12466` apply_scorer_decision call site
  - `:12953` `scoreboard._tracker.on_ball_event()` — primes FC5 grace
- `files/score_manager.py` — SM (`~6500 lines`). Critical sections per prior HANDOFF + B-η chain:
  - `:1170` SM-side `sb.set("score", iv, frame)` call
  - `:2789-2808` F1 fix (cold-start striker)
  - `:4295-4325` deterministic-rotation override
  - `:4515+` F-α-shadow fix
  - `:3061-3134` `_handle_warm` streak gate (OVERS-JUMP-IMPLAUSIBLE-REJECTED)
  - `:4634` `_decompose_multi_ball`
  - `:5176+` `_apply_absorbed_event` (F-α-queue at `:5310+`)
- `files/eyes/scoreboard.py` — Scoreboard. **NEW: DIRECT-SCORE-COMMIT trace emission at `:1481`** (C6 instrumentation). `sb.set` bottleneck at `:1188`.
- `files/eyes/consistent_tracker.py` — **NEW THIS SESSION**: the per-field consensus tracker called from sb.set. Five fast-confirm paths (FC1–FC5) documented in C10 §4. FC5 post-event grace at `:294-306` is the cascade root mechanism.
- `files/confidence_tracker.py` — `ConfidenceTracker` (team/striker/bowler). Distinct from `consistent_tracker.py`. Synchronous on_lock callbacks (C10 §3 verified).
- `files/eyes/agent.py` — `Extractor.extract()` LLM fallback. Uses Python 3.10+ syntax (`int | None`). Triggers venv-preference in pre-commit hook.
- `files/trace_emitter.py` — KNOWN_TAGS. New this session: FRAME-TRUST-GATE, OVERS-JUMP-STREAK-STATE, POISON-STREAK-AT-COMMIT, DIRECT-SCORE-COMMIT, CROSS-FIELD-PAIRING-REJECT.

### 9.2 Tests and harness (extended this session)

- `files/tests/test_sm_derivation_ledger.py` (L1.5 gate) — **NEW: invokes test_cross_field_pairing_gate.run_all() after the 36-ball replay**
- `files/tests/test_pipeline_captured_replay.py` (L2 gate)
- `files/tests/test_cross_field_pairing_gate.py` (NEW C15 — 6 cases for Shape B accept/reject)
- `files/tests/trace_session_assertions.py` (session-level invariants)
- `files/tests/symptom_class_assertions.py` (per-ball invariants)
- `files/scripts/run_trace_session_assertions.py` (runner)
- `files/scripts/replay_captured_scout_trace.py` (NEW C-commits — captured-replay scaffold with warm-seed + LLM + cross-fixture support)
- `files/scripts/run_symptom_assertions.py`
- `files/tests/fixtures/dc_vs_kkr_2026_152064_ledger.json`
- `files/tests/fixtures/gt_vs_rr_2026_commentary_first_innings.md`

### 9.3 Design memos (read in this order)

1. **`temporal_coupling_investigation_brief.md`** (C10-C12.5b chain) — static-analysis methodology + cascade-root localization
2. **`c13_fc5_audit_memo.md`** (C13 §7.2 7-gate audit on 4 shapes) — Shape B selection + dual-state-write catalogue
3. **`stream_gap_reconciliation_design.md`** (B-η chain §1-§13) — 5 empirical falsifications + investigation-strategy pivot
4. **`state_mutation_site_catalogue.md`** (C9) — 38 mutation sites + 2 async callbacks; gate-bypass classes
5. `sm_as_orchestrator_design.md` — main memo. §7 audit framework; §12 dual-state-write defect-class catalogue (C17 landed)
6. `dckkr_20260521_cc_investigation_brief.md` — operator-side brief + §0 reframe (C8 retired Step 1 framing)
7. `dckkr_20260521_session_observations.md` — observations + C15 predicted-flip claim section

### 9.4 Captured data

- `files/logs/deliveries/validate_gtrr_20260520_180715/scout_raw.jsonl` (841 frames, GT vs RR)
- `logs/trace/validate_gtrr_20260520_180715.jsonl` (489 trace records, pre-F1)
- `files/logs/deliveries/validate_dckkr_20260521_070545/scout_raw.jsonl` (375 KB, 1000+ frames)
- `logs/trace/validate_dckkr_20260521_070545.jsonl` (341 trace records, pre-C14)
- **`/tmp/pipeline.log` (2.9 MB) — the C12.5b empirical-localization artifact**. May not persist across reboots. Critical for future cascade-root audits if available.

---

## 10. Discipline lessons (do not forget — extended this session)

Prior session lessons retained:

1. **Every classification is a hypothesis.** Bug-class declarations, NOT-A-DEFECT verdicts, "already addressed" verdicts, fix-feasibility claims — all hypotheses. Gate 6 applies recursively.
2. **Predicted flips must cite concrete frame numbers.** Qualitative reasoning doesn't satisfy gate 6.
3. **Cross-fixture verification before declaring a fix shipped.** F1 closed 4+ bug classes via gate 7.
4. **Observability tooling is subject to the same empirical verification as production code.** F-α-shadow demonstrated this.
5. **The §7 candidate-deletion list framing was the wrong starting question.** Empirically-grounded bug classes with their own design memos.
6. **One-edit fixes can close multiple bug classes.** F1 demonstrated this at scale.
7. **Pre-commit gates are non-negotiable.** Never `--no-verify` unless explicit authorization.
8. **No-speculative-fixes discipline.** Multiple times this session: the audit caught hypotheses before they became commits.

**New lessons this session:**

9. **Static analysis + predicate-trail reading + production pipeline.log audit can localize temporal-coupling defects without an instrumentation cycle per hypothesis.** Use when captured-replay flattens the defect's temporal signature.
10. **Static falsification ≠ empirical falsification.** Static is zero-cost; apply liberally. Empirical counts against the methodology-retirement budget (5-cap per defect-class chain).
11. **Captured-replay does NOT drive root-localization for temporal-coupling defects** (per C8 §0.3). Remains canonical as falsification + regression-detection substrate.
12. **A complete falsification chain is an architectural finding, not a failure.** The discipline produces falsification cascades by design; the budget cap ensures productive termination.
13. **Audit §7.2 gate 3 (cross-reference adjacent state) must check for the dual-state-write pattern** when any candidate fix is proposed. Two parallel state surfaces with different invariants — weaker admits what stronger rejects — is the structural signature.
14. **Multi-shape audit (4 shapes against all 7 gates) is the right approach when more than one candidate has structural merit.** C13 introduced the pattern; promote it as a standing audit mode for cascade-root fixes.

---

## 11. Next agent's first move (UPDATED post-C32 — see §0a for C26-C31 chain context)

1. Check `git log --oneline -15` to confirm branch state. Expected HEAD: C32 docs. Expected chain: C32 → C31 → C30b → C30 → C29 → C28 → C27 → C26 → C25 → C24.
2. Run `bash scripts/preflight_validation_tags.sh` to confirm tag presence (deliverable from C19A5; should now include `BOWLER-DISPATCH-FALLBACK-FIRED` + `WICKET-ATTRIB-BROADCAST-OVERRIDE-APPLIED` registered in C28/C31).
3. **Primary unblocked path — empirical validation of D1 + D2 predicted flips on next DCKKR replay.** Run a fresh DCKKR replay (or any fixture with sufficient wicket density). Check the γ-bundle assertions:
   - `trace_gamma_bowler_w_increment_on_dispatch` — predicted FAIL × 4 → FAIL × 2 (F400 + F679 close via D1).
   - `trace_gamma_w_symbol_at_wicket` — predicted FAIL × 2 → PASS + cricket-truth FOW name flips at F855 (D2 direct) + F983 (S9 cascade closure).
   - If predicted flips land → C23b unblocks; close D chain in a C33-tier docs commit.
   - If predicted flips do not land → **first empirical falsification** for the D chain (budget cap 5/5 still open); next move is plumbing at `score_manager.py:4411` per §3.4d.6 of `workstream_d_rotation_root_investigation.md`.
4. **Secondary unblocked paths (independent of replay; all static):**
   - §12 catalogue extension — land (a) `STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC` override as 4th dual-state-write instance, (b) S12 non-discriminable-predicate-signature as new peer defect-class entry, in `sm_as_orchestrator_design.md`.
   - C20b — per-row populate of `surface_pair_defect_class_family.md` §2.1–§2.9 (skeleton-then-populate pattern likely surfaces more forcing-function findings).
   - Workstream surface E skeleton — open `workstream_e_phantom_wicket_detection.md` for the F1017 case.
   - C29b — Scout prompt schema extension (`dismissed_batter` field).
5. **DO NOT** open B-ι / B-θ memos (retired pre-C26). **DO NOT** attempt C23b before D1 + D2 empirical validation. **DO NOT** touch BW07 clear ordering at `score_manager.py:5965` (Candidate A territory, retired by risk-surface argument at C27). **DO NOT** attempt single-site fix at `score_manager.py:4411` without the empirical-falsification trigger from a failed replay (ruled out by S12 / non-discriminable predicate signature at C30b).
6. Read order for D entry / continuation: §0a above → `workstream_d_rotation_root_investigation.md` (the C26-C31 investigation memo) → §0 above (C19-C24 context) → `surface_pair_defect_class_family.md` §2.5 + §2.6 → C9 mutation-site catalogue (BW07 row for D1, BW02/BW06 for C23b downstream).

---

## 12. Quick reference — the meta-finding chain

Each session contributes one or more transferable methodology insights. **11 transferable insights total across 4 sessions:**

- **F1 session (3 sessions back)**: F1 cascade-closure demonstrated one-edit fix can close 4+ bug classes. §7.2 gate 7 (cross-fixture verification) baked into the audit framework.
- **B-η session (2 sessions back)**: Static-analysis-with-predicate-trail methodology produces full cascade-root localization at near-zero commit cost. Falsification-chain-as-architectural-finding. Dual-state-write defect class confirmed across 3 instances.
- **C19-C24 session (prior)**: Commit-design drift detection (preflight tag-existence check). Budget-class mismatch (memo work needs 8–12 calls; code work fits 5). Skeleton-then-populate forcing-function pattern. UI-layer vs state-layer disambiguation via trace. Both-surfaces-stale-at-same-value pattern (internal-consistency PASS when rotation-lock corrupts adjacent surfaces in sync).
- **C26-C31 session (this one — workstream D fix chain)**:
  - **S6** — predicate-trail extends beyond temporal-coupling defect class to Scout-contract gaps.
  - **S9** — cascade-closure-via-one-edit pattern, second instance (F1 was first); F855 fix auto-closes F983.
  - **S11** — signal/site decoupling pattern: predicate-trail reformulation moves the predictive signal but not necessarily the fix site.
  - **S12** — non-discriminable-predicate-signature defect class: single-site fix structurally impossible without plumbing when two cases share an observable predicate.

**The discipline track record is itself a load-bearing artifact.** Preserve it; document new insights as they accumulate.

Empirically validated discipline saves engineering work. F1 demonstrated the positive case (cascade closure of separate workstreams). B-η demonstrated the negative case (5 empirical + 8 static falsifications prevented 5 wrong fixes from landing). Both outcomes are the discipline working as designed.

Welcome to the branch. Read the discipline lessons (§10) before touching anything. Layer 1.5 (now 36 ledger + 6 cross-field) + Layer 2 gates protect you. Read C13 audit memo + C10/C11/C12/C12.5b briefs to understand the static-analysis methodology before defaulting to instrument-replay-then-fix on the next defect class.
