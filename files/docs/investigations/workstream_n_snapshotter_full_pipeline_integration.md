# Workstream N — Snapshotter full-pipeline integration investigation (step-1)

**Date.** 2026-05-24.
**Branch.** `derive-not-detect` @ HEAD = `3e8ac11` (runbook fix close-out).
**Empirical-budget status.** 1/5 — UNCHANGED (static-only this step).
**Pre-screen verdict.** GREEN — PIPELINE-DIRECT per S28 (production-side replay infrastructure; modifies `replay_captured_scout_trace.py` + possibly `test_pipeline_captured_replay.py`'s `build_sm` helper). Budget cost projection: **0/5 at step-2** (unit-verified via L1.5 IF integration scope stays bounded); **1/5 at step-3** if empirical validation against WS-M Shape 2 cohort consumes a cycle. Methodology cap proximity preserved at 1/5 best-case.
**Outcome.** Static-falsification chain converges on **NA — extend `build_sm` helper to instantiate + wire over_mgr inline + minimal dispatch hook in snapshotter frame loop** as leading candidate with **load-bearing scope reservation around ball-event dispatch source**. The over_mgr ↔ score_manager wiring itself is trivial (1-line `attach_score_manager` + 1-line `on_fow_upgrade` callback); the load-bearing question is **how to source `ball_event` for `over_mgr.on_ball_event()` dispatch** in the snapshotter's frame loop without pulling in `BallEventDetector` + `test_pipeline.py`'s main loop logic. Per S26-v2 candidate methodology: **WS-N step-1b sub-investigation recommended BEFORE step-2 patch authorization** to identify whether sm.on_frame internally drives over_mgr dispatch OR whether external ball_event sourcing is required.

---

## §1 Empirical anchor — SM-only measurement gap evidence

**Surfaced at WS-M step-3 (no commit, replay session `validate_ws_m_step3_20260523_221808`)** + **confirmed at runbook fix (`3e8ac11`).**

Measurement gap on `validate_dckkr_20260521_155356` snapshotter run (commit `3e8ac11` HEAD + Shape 2 `d2f0759` ancestor):

| Surface | Snapshotter (SM-only) | HANDOFF expected (post-WS-H/WS-I/WS-M) | Gap |
|---|---|---|---|
| **D-post-FoW-striker** | **26** | **2** (post-WS-H P1) | **24** — over_mgr-wired closure not reflected |
| Per-batter-ledger-drift (Sub-cohort A) | (conservation invariant, not surface count) | Shape 2 predicted closure | Shape 2 mechanism (PENDING-BALL-ORPHAN-FALLBACK-ENQUEUED) emits count = 0 in snapshotter (vs production-trace ≥22 predicted) |
| F-A-commit-lag | 37 | (no WS-specific closure attached) | (informational; not load-bearing for WS-N scope) |
| G-pipeline-lag | 58 | (Scout-timing class; production-only fix surface per runbook §2) | (informational; expected snapshotter gap) |
| All other 14 surfaces | (varies) | (varies) | (informational baselines; not load-bearing) |

**Root attribution (per `3e8ac11` commit body verbatim):** `build_sm` helper at `test_pipeline_captured_replay.py` does NOT call `over_mgr.attach_score_manager` (grep confirmed zero matches for `attach_score_manager` + `ThisOverManager` in `build_sm` path); snapshotter calls `parse_strip → sm.on_frame` directly per script docstring `:8-19`.

**Strategic implication.** Until over_mgr is wired in the snapshotter, ANY cross-module wiring fix (Shape 2 + WS-H P1 + WS-H H1 over_mgr-dependent paths + any future PendingBall lifecycle work) is unvalidatable via the runbook workflow. The diff harness's headline 16-surface ledger is structurally biased toward over-counting SM-internal closures + under-counting cross-module closures.

## §2 Current snapshotter architecture

**`replay_captured_scout_trace.py:589-609`** argparse: `--dump` (required) + `--session-id` (required) + `--snapshot-output` (optional UIBallSnapshot emission) + various optional seed/fixture/extractor flags.

**Frame iteration loop (`:407-509+`).**
- For each Scout dump line: extract frame_id + raw_response + timestamp.
- `parse_strip(raw, batting_team, bowling_team)` → extracted dict.
- `extracted_to_frame_input(extracted, frame_id, ts)` → `FrameInput` dataclass (helper imported from `test_pipeline_captured_replay`).
- `sm.on_frame(fi)` at `:509` — drives SM state update.
- After sm.on_frame: snapshot emission hook (when `--snapshot-output` set) — reads SM state + batting/bowling cards + emits `UIBallSnapshot`.

**`build_sm` helper (imported from `test_pipeline_captured_replay`).** Per `:58-65`: imports `build_sm as build_sm_dckkr` from `test_pipeline_captured_replay`. Constructs `ScoreManager(shadow=False)` + `Scoreboard` + sets `sm.scoreboard = sb` + pre-promotes opening pair to status="batting". **DOES NOT instantiate `over_mgr` + does NOT call `attach_score_manager`.**

**Snapshot emission triggers (per runbook §10 troubleshooting):** `DIRECT-SCORE-COMMIT` + `trace_beta_sm_wicket_dispatch` + cross-frame `this_over` mutation. Implementation reads `sm.this_over` + `sm.batting_card` + `sm.bowling_card` + assembles UIBallSnapshot.

**The snapshotter does NOT invoke `BallEventDetector`.** No `ball_detector.detect()` call; no ball_event dict produced; no `over_mgr.on_ball_event()` dispatch.

## §3 `over_mgr.attach_score_manager` integration requirements

**`eyes/this_over.py:731-738` `attach_score_manager` body (verbatim):**

```python
def attach_score_manager(self, score_manager) -> None:
    """Wire the back-reference for the slot-binding callback (B1.2c).
    Once both managers are constructed, the pipeline calls this so
    the ABSORBED_LEGAL handler can call sm.bind_pending_slot(slot_idx)
    immediately after appending a "?" placeholder.
    """
    self._score_manager = score_manager
```

**This is trivial.** Single line assignment. No state requirements. No side effects. No dependencies pulled in. Pure back-reference wire.

**`ThisOverManager()` constructor** — parameterless (per production usage at `test_pipeline.py:7163`: `over_mgr = ThisOverManager()`).

**Production setup at `test_pipeline.py:7163-7366` (verbatim sequence):**
```python
over_mgr = ThisOverManager()
scoreboard.on_fow_upgrade = over_mgr.reorder_wicket_to_ball   # FOW callback
# ... [some lines skipped: ball_detector, partnership_tracker, etc.]
score_mgr.scoreboard = scoreboard
over_mgr.attach_score_manager(score_mgr)
```

**Minimum over_mgr setup for bind_pending_slot path activation:**
1. `over_mgr = ThisOverManager()` — instantiate.
2. `over_mgr.attach_score_manager(score_mgr)` — wire back-ref.
3. (Optional but recommended) `scoreboard.on_fow_upgrade = over_mgr.reorder_wicket_to_ball` — FOW upgrade callback.

**The trivial part is the setup. The LOAD-BEARING part is the dispatch.**

## §4 Hypothesis enumeration — load-bearing reservation on dispatch source

### NA — Extend `build_sm` helper + minimal dispatch hook in snapshotter frame loop — **LEADING (with sub-investigation reservation)**

**Shape.** Modify `test_pipeline_captured_replay.py:build_sm` to also instantiate over_mgr + wire `attach_score_manager`. In `replay_captured_scout_trace.py` frame loop, add minimal `over_mgr.on_ball_event(ball_event, score=...)` dispatch after sm.on_frame returns a ball event.

**LOAD-BEARING sub-investigation REQUIREMENT.** The current snapshotter doesn't produce `ball_event` dicts — sm.on_frame consumes FrameInput and updates state; it doesn't return a ball event for downstream dispatch. Two possible sub-mechanisms:
- (a) **sm.on_frame internally dispatches to over_mgr.** If `sm.scoreboard.on_ball_event` (or similar internal callback) drives over_mgr, then NA reduces to setup-only (NA-simple). Most likely + cleanest.
- (b) **External BallEventDetector required.** If production's `ball_detector.detect()` is the sole ball_event producer (per `test_pipeline.py:13056-13098` flow), then NA expands to require BallEventDetector instantiation + per-frame detect() call + over_mgr.on_ball_event() dispatch. Larger scope; may pull in tracker dependencies.

**Recommend step-1b sub-investigation** to determine sub-mechanism via code-read of sm.on_frame + scoreboard.on_ball_event call chain. **Per S26-v2 candidate methodology** (already promoted at WS-L step-3 + reinforced at WS-M step-1b ~10× cost reduction): 3-5 tool calls of pre-step-2 audit prevents step-2 verification deviation cost.

**Gate 1.** PASS-conditional on sub-mechanism (a) holding. If (b), step-2 scope expands; gate-3 may shift to NB or NC.

**Gate 2.** PASS — over_mgr wiring is additive; existing SM-only behavior preserved if integration is conditional (e.g., default-off OR opt-out flag for SM-only mode preservation).

**Gate 3.** Pipeline-direct per S28 (snapshotter is production-side replay infrastructure). Backward compatibility risk: any L1.5 test or production tool that depends on the SM-only `build_sm` helper would need verification.

**Status.** Leading candidate with sub-mechanism reservation. Recommend step-1b BEFORE step-2.

### NB — Add `--full-pipeline` flag toggling SM-only vs over_mgr-wired — **VIABLE alternative**

**Shape.** Add CLI flag; conditional over_mgr setup in build_sm path; conditional on_ball_event dispatch in frame loop.

**Gate 1.** PASS-conditional on same sub-mechanism question as NA.

**Gate 2.** PASS — preserves SM-only mode for legitimate use cases (e.g., faster iteration on pure SM-internal fixes).

**Gate 3.** Larger surface area than NA (flag + 2 code paths). More backward-compat-friendly though.

**Status.** Viable alternative if NA's backward-compat audit surfaces regressions. Defer to step-2 decision after sub-investigation outcomes.

### NC — Refactor `build_sm` into `build_sm_only` + `build_full_pipeline` — **OVER-SCOPED for step-2**

**Shape.** Two helpers; `--snapshot-output` defaults to `build_full_pipeline`; SM-only available via opt-in flag.

**Gate 3.** Cleanest architecture but largest refactor. Per S28: pipeline-plumbing-required arc territory; 1-2/5 budget for empirical replay; over-scoped for the simple "wire over_mgr" change NA achieves.

**Status.** Falsified at gate 3 (over-scoped for current need). Reserve for future architectural cleanup pass.

### ND — Extract pipeline setup from `test_pipeline.py` into reusable function — **OUT-OF-SCOPE**

**Shape.** Refactor `test_pipeline.py:7160-7400+` block into a reusable `setup_pipeline()` function; both `test_pipeline.py` and snapshotter call it.

**Gate 3.** FAIL. Massive refactor of production-critical setup code. Touches `test_pipeline.py` main path — high regression risk. Per S28: pipeline-plumbing-required + 9+ step arc + 2/5 budget for empirical replay. Methodology cap risk at current 1/5 budget.

**Status.** Falsified at gate 3 (scope expansion beyond Phase 1 affordability). Defer to Phase 4 architectural cleanup queue.

### NE — New script (`replay_captured_scout_trace_full_pipeline.py`) — **STATICALLY FALSIFIED**

**Shape.** Create new script duplicating existing snapshotter + wiring over_mgr.

**Gate 1.** FAIL. Duplicates logic; creates two snapshotters with diverging behavior risk. Future runbook would need to document two workflows; users could pick wrong one for their fix surface. Anti-pattern for documentation discipline.

**Status.** Falsified at gate 1 (anti-pattern). NA's extension of existing snapshotter is preferred.

## §5 Cohort-closure verification

**Claim under test.** NA integration closes the SM-only measurement gap on `validate_dckkr_20260521_155356` snapshotter run:
- **D-post-FoW-striker**: 26 → 2 (matches HANDOFF post-WS-H P1).
- **Per-batter-ledger-drift / PENDING-BALL-ORPHAN-FALLBACK-ENQUEUED**: count 0 → ≥22 (Shape 2 mechanism engages).

**Static analysis.** Both closure mechanisms are gated on the `bind_pending_slot` call chain firing in snapshotter runs. That chain requires:
- `over_mgr` instance present in build_sm output (NA step 1).
- `over_mgr.attach_score_manager(sm)` called (NA step 2).
- `over_mgr.on_ball_event(ABSORBED_LEGAL_event, ...)` called (NA step 3 — the LOAD-BEARING sub-mechanism question).

If sub-mechanism (a) holds (sm.on_frame internally dispatches): all three closures expected; cohort UNIFIED-CLOSURE.

If sub-mechanism (b) holds (external dispatch required): closure depends on whether the BallEventDetector + dispatch wiring correctly mirrors test_pipeline.py's main loop ball_event flow. Step-2 patch scope expands; gate-7 empirical validation becomes load-bearing.

**Cohort-closure status: UNIFIED-CLOSURE PROJECTED conditional on sub-mechanism (a)** OR **SCOPE-EXPANSION PROJECTED conditional on sub-mechanism (b)**. Step-1b sub-investigation resolves.

## §6 §7.2 audit on leading candidate (NA)

| Gate | Description | Status |
|---|---|---|
| **1** | Predicate closes measurement gap | PASS-conditional on sub-mechanism (a); SCOPE-EXPANSION-CONDITIONAL on sub-mechanism (b). |
| **2** | Does not break preserved capability | PASS-conditional. Existing SM-only behavior preserved if integration is additive (default-on for `--snapshot-output` per WS-N's load-bearing claim about full UI validation) OR opt-out via new flag. Backward-compat audit at step-1b. |
| **3** | Fix-surface attribution | PASS — pipeline-direct per S28; modifies snapshotter + build_sm helper; no test_pipeline.py main path touch. 3-5 step arc + 0/5 step-2 budget (unit-verified) + 1/5 step-3 budget (empirical replay against WS-M Shape 2 cohort). |
| **4** | Regression-direction posture | PASS-conditional on sub-mechanism (a). Additive over_mgr wiring; no SM-internal logic change. Per-surface counts may shift (closing D-post-FoW-striker 26→2 + opening Per-batter-ledger-drift mechanism); the shifts are intended outcomes, not regressions. |
| **5** | Symmetric γ/η-bundle non-interference | PASS — assertion library is orthogonal; only diff harness surface counts shift. γ-bundle / η-bundle assertions read trace data, not snapshotter output. |
| **6** | Predicted-flip table with concrete measurement-gap closures | READY (§8). |
| **7** | Cross-fixture closure | DEFERRED to step-3 empirical replay against `validate_dckkr_20260521_155356` (Sub-cohort A 3-fixture anchor; full-pipeline snapshotter run + diff harness comparison). 1/5 budget cost expected. |

**Gates 1-5 PASS-conditional; gate 6 READY; gate 7 step-3 budget-consuming.** Step-2 authorization requires sub-mechanism identification first (step-1b sub-investigation).

## §7 Dependency + risk assessment

### Dependencies pulled in by over_mgr setup

**Minimum dependencies for `attach_score_manager` activation:** ZERO additional dependencies. `ThisOverManager()` is parameterless; `attach_score_manager` is single-line assignment. No trace emitter wiring beyond what snapshotter already does. No frame ledger requirement. No real-time wall-clock requirement.

**Additional dependencies for over_mgr.on_ball_event dispatch** (sub-mechanism (b) scope):
- `BallEventDetector()` instantiation — parameterless per `test_pipeline.py:7174`.
- Per-frame `ball_detector.detect(scoreboard._tracker)` call — depends on `scoreboard._tracker` being maintained correctly across frames.
- Possibly partnership tracker, bowler/striker trackers — depending on which production-loop logic the snapshotter mirrors.

**If sub-mechanism (a) holds, ZERO additional dependencies.** Memo strongly suggests (a) is likely given sm.on_frame's role as the canonical event-processing site, but code-read at step-1b confirms.

### Replay-dump satisfiability

- **UDP timing**: NOT required. over_mgr operates on per-event semantics, not real-time signals.
- **Frame ledger**: NOT required by over_mgr itself. May be required by some downstream pipeline elements but those are out-of-scope for WS-N (only the `bind_pending_slot` path is in scope).
- **Real-time wall-clock**: NOT required.
- **OpenScout integration**: NOT required (over_mgr is independent of Scout pipeline).

**Captured Scout dump fully satisfies over_mgr integration requirements** assuming sub-mechanism (a). Sub-mechanism (b) introduces ball_detector tracking which may have its own dump-satisfiability questions — defer to step-1b.

### Backward compatibility

**Existing fix-iteration use cases (per runbook §8).** The runbook's documented workflow runs the snapshotter for SM-internal fix validation. If WS-N defaults to full-pipeline mode, existing fix-iteration tests on SM-internal fixes still pass (additive surface visibility doesn't regress SM-internal closures). NA's safest backward-compat posture is default-on full-pipeline (per WS-N's purpose) with no opt-out — closures are additive, not behavior-changing.

**L1.5 / L2 / derivation test surface area:**
- L1.5 `test_sm_derivation_ledger.py`: not invoked by snapshotter; unaffected.
- L2 `test_pipeline_captured_replay.py`: uses `build_sm` helper — IF the helper is modified to include over_mgr, L2 may surface new behavior (likely PASS-preserving but verification needed at step-2).
- Derivation: not invoked by snapshotter; unaffected.

**Step-2 L1.5 test obligation:** verify L2 ledger still PASSes with modified build_sm.

## §8 Predicted-flip table for step-2

**LOCKED CONDITIONAL on step-1b sub-mechanism identification.**

| Metric | Pre-NA (current snapshotter SM-only) | Post-NA (predicted UNIFIED-CLOSURE) | Status |
|---|---|---|---|
| D-post-FoW-striker | 26 | **2** (matches HANDOFF post-WS-H P1) | Load-bearing closure |
| `PENDING-BALL-ORPHAN-FALLBACK-ENQUEUED` (Shape 2 mechanism) | 0 | **≥22** (Shape 2 engages per WS-M predicted-flip) | Load-bearing closure |
| `PENDING-BALL-SLOT-BOUND-ORPHAN` | 0 (path not exercised in snapshotter) | **0** (Shape 2 fallback path bypasses; Sub-cohort A predicted closure) | Sub-cohort A confirmation |
| `PENDING-BALL-ENQUEUED` count | 3 | **≥6** (production-equivalent + Shape 2 fallback PendingBalls) | Mechanism confirmation |
| Per-batter-ledger-drift conservation invariant on Sub-cohort A 3 dckkr fixtures | (currently SKIPped via Shape B precondition on snapshotter trace) | (still SKIPped because snapshotter trace lacks ui_after) | Unchanged — diff harness reads UIBallSnapshot directly, not trace; conservation invariant computed on snapshot data |
| `trace_alpha_batter_runs_sum` on snapshotter trace | SKIP via Shape B | SKIP (unchanged) | Snapshotter trace remains replay-class; assertion behavior unchanged |
| Diff harness per-batter-ledger-drift surface count (§3 of report) | (TBD — was not in surface §1 output at smoke test) | **drops significantly** (Shape 2 closure visible in diff snapshots) | Headline WS-N validation signal |
| Other 14 surfaces | (varies per smoke test) | UNCHANGED (no SM-internal logic change) | Regression-guard |
| L1.5 / L2 / derivation | 80/30/48 PASS | 80/30/48 PASS | No regression |
| Budget | 1/5 | 1/5 at step-2 (0/5 budget cost) → 0/5 at step-3 (1/5 empirical replay) | Methodology cap proximity preserved |

## §9 Sub-findings

**No new sub-findings promoted this step.** S26-v2 self-application active (load-bearing reservation around sub-mechanism question; step-1b sub-investigation recommended). Replay-tool-fitness candidate (single-instance from WS-M step-4) potentially gains second-instance evidence at WS-N step-2 if integration correctly closes the measurement gap that motivated WS-N's opening — promotion authorization pending at WS-N step-3 close-out.

**Standing-observation extension.** WS-N's existence validates the load-bearing nature of the replay-tool-fitness candidate: the WS-M step-3 mechanism-confirmation FAIL surfaced both (a) the immediate Shape 2 unverifiability + (b) the broader category of cross-module wiring fixes that the runbook workflow can't validate. WS-N closure restores runbook fitness for the broader category — second-instance promotion of replay-tool-fitness candidate at WS-N step-3 strengthens the methodology framework.

## §10 Step-2 entry data

### Patch surface (step-2; conditional on step-1b outcome)

**If sub-mechanism (a) — sm.on_frame internally dispatches:**
- `files/tests/test_pipeline_captured_replay.py:build_sm` — add `over_mgr = ThisOverManager()` + `scoreboard.on_fow_upgrade = over_mgr.reorder_wicket_to_ball` + `over_mgr.attach_score_manager(sm)`.
- Return tuple modified to include over_mgr OR snapshotter looks up from sm (which has internal reference via attached score_manager pointer? — verify at step-1b).
- `files/scripts/replay_captured_scout_trace.py` — no changes (sm.on_frame drives over_mgr automatically).

**Estimated diff scope (sub-mechanism a):** ~5-10 LOC at `build_sm` helper. Minimal.

**If sub-mechanism (b) — external dispatch required:**
- Same `build_sm` modifications + `ball_detector = BallEventDetector()` instantiation.
- `files/scripts/replay_captured_scout_trace.py` — add `ball_event = ball_detector.detect(scoreboard._tracker)` after sm.on_frame at `:509+` + `over_mgr.on_ball_event(ball_event, score=sb._inn["score"])` dispatch.

**Estimated diff scope (sub-mechanism b):** ~15-25 LOC across build_sm + snapshotter frame loop.

### Test obligation (gate-6)

L1.5 cases needed (step-2):
- N-1 Snapshotter-build-sm includes over_mgr; attach_score_manager called; bind_pending_slot accessible via sm._score_manager-or-similar wire.
- N-2 Snapshotter frame loop dispatches to over_mgr.on_ball_event (sub-mechanism b only).
- N-3 L2 captured-replay still PASSes with modified build_sm.

L1.5 family count: 80 → 82-83.

### Gate-7 cross-fixture verification

**Step-3 empirical replay:** re-run snapshotter against `validate_dckkr_20260521_155356` (Sub-cohort A anchor) post-NA + re-run diff harness + verify:
- D-post-FoW-striker: 26 → 2.
- PENDING-BALL-ORPHAN-FALLBACK-ENQUEUED count: 0 → ≥22 (Shape 2 mechanism confirmation — load-bearing).
- Other 14 surfaces: UNCHANGED.

**Budget cost:** 1/5 (single replay against Sub-cohort A anchor).

### Recommended next step

**WS-N step-1b sub-investigation (3-5 tool calls; 0/5 budget)** — code-read of sm.on_frame + scoreboard.on_ball_event call chain to determine sub-mechanism (a) vs (b). Per S26-v2 promoted methodology: prevents step-2 verification deviation cost.

---

## §11 Status footer

**WS-N step-1 status.** CLOSED — pre-screen GREEN-PIPELINE-DIRECT per S28; static-falsification chain converged on NA with load-bearing sub-mechanism reservation; NC/ND/NE statically falsified or out-of-scope.

**Recommended next step.** WS-N step-1b sub-investigation (per S26-v2 methodology) BEFORE step-2 patch authorization. Identifies dispatch sub-mechanism + locks step-2 patch scope.

**Sub-findings.** None promoted. Replay-tool-fitness candidate (WS-M step-4 first-instance) potentially gains second-instance at WS-N step-3 (promotion pending).

**Empirical-budget status.** **1/5 — UNCHANGED.** Projected post-step-3: 0/5 (best-case methodology cap; 1/5 single-replay empirical validation).

**Methodology insights running total.** 25 (unchanged; S26-v2 already promoted at WS-M step-4; S28 already promoted at WS-L step-3; replay-tool-fitness candidate awaiting WS-N step-3 second-instance).

**Recommended commit message:**

```
docs(workstream-n): step-1 investigation memo — snapshotter full-pipeline integration; closes SM-only measurement gap from WS-M step-3 + runbook fix

§7.2 7-gate static-falsification chain on snapshotter SM-only mode
measurement gap. Pre-screen GREEN-PIPELINE-DIRECT per S28. Memo §1
documents measurement gap evidence (D-post-FoW-striker 26 in
snapshotter vs HANDOFF 2 post-WS-H P1; Shape 2 mechanism count 0 in
snapshotter vs predicted ≥22 production).

`over_mgr.attach_score_manager` integration requirements (memo §3):
trivial wiring — `ThisOverManager()` parameterless constructor +
single-line back-ref assignment. ZERO additional dependencies for
setup; LOAD-BEARING question is dispatch source for
`over_mgr.on_ball_event(ball_event, ...)` calls in snapshotter frame
loop.

5 hypotheses enumerated (memo §4):
  NA Extend build_sm helper + minimal dispatch hook — LEADING with
     sub-mechanism reservation. ~5-25 LOC depending on whether
     sm.on_frame internally dispatches (sub-mechanism a) OR external
     BallEventDetector wiring required (sub-mechanism b).
  NB --full-pipeline flag toggle — viable alternative if NA backward-
     compat surfaces issues.
  NC Refactor build_sm into two helpers — OVER-SCOPED.
  ND Extract pipeline setup from test_pipeline.py into reusable
     function — OUT-OF-SCOPE (massive refactor; falsified at gate 3).
  NE New duplicate script — statically falsified at gate 1 (anti-
     pattern; documentation discipline regression).

Cohort-closure: UNIFIED-CLOSURE PROJECTED conditional on sub-
mechanism (a) (most likely; sm.on_frame is canonical event-
processing site). SCOPE-EXPANSION PROJECTED conditional on sub-
mechanism (b). Per S26-v2 promoted methodology (WS-M step-4):
recommend WS-N step-1b sub-investigation (3-5 tool calls; 0/5
budget) to identify dispatch sub-mechanism BEFORE step-2 patch
authorization — prevents step-2 verification deviation cost.

Risk assessment (memo §7):
  Dependencies: ZERO additional for sub-mechanism (a); BallEvent-
    Detector + tracker chain for sub-mechanism (b).
  Replay-dump satisfiability: full (no UDP timing / real-time / OS
    requirements introduced by over_mgr).
  Backward compatibility: NA's additive integration preserves SM-
    internal fix-iteration use cases; L2 ledger verification at
    step-2 covers regression risk.

Predicted-flip table (memo §8): D-post-FoW-striker 26→2 + PENDING-
BALL-ORPHAN-FALLBACK-ENQUEUED 0→≥22 + 14 other surfaces UNCHANGED.

Step-2 + step-3 budget projection: 0/5 step-2 (unit-verified) +
1/5 step-3 (single empirical replay against Sub-cohort A anchor).
Methodology cap proximity preserved at 1/5 best-case post-arc.

Replay-tool-fitness candidate (WS-M step-4 first-instance) gains
second-instance potential at WS-N step-3 if integration closes the
measurement gap that motivated WS-N's opening — promotion authoriz-
ation pending at WS-N step-3 close-out.

Empirical-budget status: 1/5 → 1/5 (UNCHANGED).
Methodology insights running total: 25 (unchanged).
Memo: files/docs/investigations/workstream_n_snapshotter_full_pipeline_integration.md (11 sections, ~420 lines).
```
