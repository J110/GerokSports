# Handoff — derive-not-detect branch (Architecture)

**Last update.** 2026-05-21 (post-C24, workstream B closure session).
**Branch.** `derive-not-detect` (current HEAD post-C24).
**Session ledger.** 25 cumulative commits across two consecutive sessions on this branch. Layer 1.5 (36/36 ledger balls + 6 cross-field pairing cases) + Layer 2 (29/29 commits) held on every one. Predicted-flip claims empirically validated OR statically falsified at each step.

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
- **C29b (or successor C-number)** — Scout prompt schema extension to emit a structured `dismissed` / `dismissed_batter` field on WICKET-shaped frames. Closes the Scout-contract gap at the source. Non-overlapping with H-D2-Layer-1a (downstream `_derive_dismissed_name`). OUT of workstream D scope; candidate for a separate workstream surface (E or similar). Empirical basis: `workstream_d_rotation_root_investigation.md` §3.4b cross-fixture survey, 0/182 wicket-signal frames across 4 substantive captures.

### 0.7 Methodology track record — 7 transferable insights across 3 sessions

Pattern continues at the accumulation rate flagged in prior HANDOFFs. Each session contributes 1–3 transferable insights:

- **F1 session (3 sessions back):** F1 cascade-closure (one-edit fix closes N bug classes), §7.2 gate 7 (cross-fixture verification) baked into the audit framework.
- **B-η session (2 sessions back):** Static-analysis-with-predicate-trail methodology (full cascade-root localization at near-zero commit cost), falsification-chain-as-architectural-finding, dual-state-write defect class confirmed across 3 instances.
- **C19-C24 session (this one):** Commit-design drift (briefs can predict flips on tags deleted between authoring and HEAD; preflight tag-existence check needed) + budget-class mismatch (memo work needs 8–12 calls, code work fits 5) + skeleton-then-populate forcing function (instance-catalogue skeletons surface observation-discipline gaps when populate-time work discovers Obs entries lack data for (a)-(e) axes) + UI-layer vs state-layer disambiguation via trace + both-surfaces-stale-at-same-value (internal-consistency PASS when rotation-lock corrupts adjacent surfaces in sync).

7 transferable methodology insights total. **The discipline track record is itself a load-bearing artifact.**

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

## 11. Next agent's first move (UPDATED post-C24 — see §0 for full context)

1. Check `git log --oneline -25` to confirm branch state. Expected HEAD: `c671cb2` (C24). Expected chain: C24 → C23 → C22 → C21 → C20 → C19A5 → C19A4 → C19A3 → C19A1 → C18 → ... back to C16.
2. Run `bash scripts/preflight_validation_tags.sh` to confirm all 5 expected tags are present in source (deliverable from C19A5).
3. **Open workstream D investigation** per §0.5 above. This SUPERSEDES the prior "If a fresh production trace exists..." framing — the validation gate already fired on `validate_dckkr_20260521_155356` and results are documented in §0.3. No fresh-replay-as-validation-gate is the unblocked next move.
4. **DO NOT** open B-ι / B-θ memos — both RETIRED as standalone workstreams (collapsed as B-η cascade symptoms, `trace_alpha` flipped PASS post-C14 confirms collapse).
5. **DO NOT** attempt C23b without first resolving D's em-dash bowler-identity case — crediting an em-dash sentinel to bowler-W would be worse than no credit.
6. Read order for D entry: §0 of this document → `validate_dckkr_replay_observations.md` Obs 2/3/9/16/17/18/19/21 → `surface_pair_defect_class_family.md` §2.5 + §2.6 → C19A3's `resolution_src` discriminator → C9 mutation-site catalogue → derive hypotheses per C10 static-analysis methodology.

---

## 12. Quick reference — the meta-finding chain

Each session contributes one or more transferable methodology insights:

- **F1 session (prior)**: F1 cascade-closure demonstrated one-edit fix can close 4+ bug classes. §7.2 gate 7 (cross-fixture verification) baked into the audit framework.
- **B-η session (this one)**: Static-analysis-with-predicate-trail methodology produces full cascade-root localization at near-zero commit cost. Falsification-chain-as-architectural-finding. Dual-state-write defect class confirmed across 3 instances.

**The discipline track record is itself a load-bearing artifact.** Preserve it; document new insights as they accumulate.

Empirically validated discipline saves engineering work. F1 demonstrated the positive case (cascade closure of separate workstreams). B-η demonstrated the negative case (5 empirical + 8 static falsifications prevented 5 wrong fixes from landing). Both outcomes are the discipline working as designed.

Welcome to the branch. Read the discipline lessons (§10) before touching anything. Layer 1.5 (now 36 ledger + 6 cross-field) + Layer 2 gates protect you. Read C13 audit memo + C10/C11/C12/C12.5b briefs to understand the static-analysis methodology before defaulting to instrument-replay-then-fix on the next defect class.
