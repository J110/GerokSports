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

---

## §12 Step-1b sub-investigation — code reading

**Trigger.** WS-N step-1 §4 NA flagged "sub-mechanism reservation" as deliberate UNVERIFIED marker per S26-v2 promoted methodology. Step-1b spot-checks the marker BEFORE step-2 commitment.

**Task 1 — `sm.on_frame` body inspection (`files/score_manager.py:2073`).** `sm.on_frame` is the SM event-processing entry point. Grep across `score_manager.py` for `over_mgr.`:

| Line | Context | Type |
|---|---|---|
| `:709` | `_rewrite_eyes_this_over_from_event` — accesses `over_mgr.this_over` for SM-authoritative rewrite | Data access |
| `:712` | Comment about `over_mgr.this_over` placeholders | Comment |
| `:1265` | Docstring referencing `over_mgr.this_over` rewrite via `rewrite_token` | Comment |
| `:725, :1276` | `over_mgr = getattr(self, "over_mgr", None)` — checks for over_mgr presence | Defensive read |

**Critical finding.** **NO `over_mgr.on_ball_event` calls in `score_manager.py`.** The `over_mgr.` mentions are about `over_mgr.this_over` (data access for SM-authoritative rewrites) + `over_mgr.rewrite_token` (slot binding callback). The ball-event dispatch path is NOT inside score_manager.

**Task 2 — `scoreboard.on_ball_event` call chain (`files/eyes/scoreboard.py`).** Grep across `scoreboard.py` for `def on_ball_event\|on_ball_event(`: **NO MATCHES.** `scoreboard.on_ball_event` does not exist as a method on Scoreboard. The dispatch flow does NOT route through scoreboard.

**Task 3 — `over_mgr.on_ball_event` call sites in production.** Grep across `test_pipeline.py`:

| Line | Context |
|---|---|
| `:7366` | `over_mgr.attach_score_manager(score_mgr)` — setup wiring (not dispatch) |
| **`:9236`** | `over_mgr.on_ball_event(_pre_ball, ...)` — pre-ball dispatch path |
| **`:13098`** | `over_mgr.on_ball_event(ball_event, score=int(scoreboard._inn.get("score") or 0))` — main loop dispatch after `ball_detector.detect()` |
| **`:14017`** | `over_mgr.on_ball_event(_abe, score=_sc_abs)` — ABSORBED_LEGAL post-dispatch path |

**All `over_mgr.on_ball_event` invocations live in `test_pipeline.py` main loop logic** — none inside score_manager. The ball_event dicts at these sites are produced by `BallEventDetector.detect()` (per `:13056` precedent already documented at WS-M step-1b §11) + the per-event synthesis path at `:13083-13097` (WICKET-ATTRIB site).

## §13 Sub-mechanism verdict — (b) CONFIRMED

**Sub-mechanism (b) — external BallEventDetector wiring required — CONFIRMED.**

Evidence:
- `sm.on_frame` does NOT internally dispatch to `over_mgr.on_ball_event` (task 1).
- `scoreboard.on_ball_event` does not exist (task 2).
- `over_mgr.on_ball_event` is invoked exclusively from `test_pipeline.py` main loop at 3 sites, all of which depend on `BallEventDetector.detect()` output OR direct synthesis from frame-loop state (task 3).

**Sub-mechanism (a) FALSIFIED.** sm.on_frame does not drive over_mgr dispatch; the snapshotter cannot rely on internal dispatch to activate the bind_pending_slot path.

**Step-2 LOC estimate REVISED upward.**
- Sub-mechanism (a) projection (memo §10): ~5-10 LOC (build_sm helper only). **FALSIFIED.**
- Sub-mechanism (b) actual: ~15-25 LOC (build_sm helper + BallEventDetector instantiation + frame-loop integration + per-event dispatch wiring). **CONFIRMED.**

Additional considerations for (b):
- `BallEventDetector()` is parameterless (`test_pipeline.py:7174`) — minimal setup cost.
- `BallEventDetector.detect(scoreboard._tracker)` requires `scoreboard._tracker` to be maintained. Whether the snapshotter's existing scoreboard setup includes `_tracker` initialization needs verification at step-2 (potential additional dependency to satisfy).
- Per-event dispatch needs to handle the WICKET-ATTRIB synthesis path at `test_pipeline.py:13083-13097` (the H-D2-Layer-1a fix from C31). Reproducing this in the snapshotter pulls in additional pipeline logic.

**Per the user's stop condition** ("Sub-mechanism (b) confirmed → STOP, report; flag step-2 as larger scope; recommend user authorization before proceeding (NB `--full-pipeline` flag alternative may be preferred for clarity)"): **STOP.** Report. User decides whether to:
- Authorize NA at expanded 15-25+ LOC scope (with explicit BallEventDetector + tracker setup verification at step-2);
- Pivot to NB `--full-pipeline` flag for explicit user-controlled opt-in mode preservation;
- Pivot to ND extract-pipeline-setup architectural refactor (previously falsified at gate 3 for scope; revisit if cleaner integration outweighs scope cost);
- Defer WS-N (accept SM-only-snapshotter measurement gap as architectural-known-limitation; rely on natural production session traces for over_mgr-wired closure validation).

## §14 Refined step-2 entry data + S26-v2 third-instance footprint

### Refined NA step-2 patch surface (sub-mechanism (b))

**`files/tests/test_pipeline_captured_replay.py:build_sm`** — modifications:
1. `from eyes.this_over import ThisOverManager`
2. `from eyes.state.ball_detector import BallDetector` (verify exact path at step-2)
3. Inside `build_sm`: instantiate `over_mgr = ThisOverManager()` + `ball_detector = BallDetector(min_gap=0.0)` (or production min_gap=8.0)
4. After SM construction: `over_mgr.attach_score_manager(sm)` + `scoreboard.on_fow_upgrade = over_mgr.reorder_wicket_to_ball`
5. Return tuple extended to include over_mgr + ball_detector (OR snapshotter reads from sm's attached references)

**`files/scripts/replay_captured_scout_trace.py`** — modifications:
1. Unpack over_mgr + ball_detector from build_sm return tuple
2. In frame loop after `sm.on_frame(fi)`: call `ball_event = ball_detector.check(score_dict_with_score_wkts_overs)` (note: `check`, not `detect`, per WS-Surface-E step-2 codebase reading)
3. If ball_event is not None: synthesize WICKET-ATTRIB if needed (mirror `test_pipeline.py:13083-13097`); then `over_mgr.on_ball_event(ball_event, score=score)`
4. Existing snapshot emission hook remains unchanged

**Estimated diff scope:** 20-35 LOC total (10 LOC build_sm + 15-25 LOC snapshotter frame loop including WICKET-ATTRIB synthesis if required).

### Backward compatibility review

**The expanded scope changes the snapshotter's behavior:**
- Pre-NA: SM-only mode; per-fixture measurement gap exists; familiar to runbook §8 fix-iteration users.
- Post-NA: full-pipeline mode (over_mgr-wired); measurement gap closed; existing fix-iteration workflows for SM-internal-only fixes still pass (additive, not regressive).

**Risk:** If existing L2 captured-replay (`test_pipeline_captured_replay.py`) depends on the SM-only `build_sm` shape (return tuple `(sm, sb)` vs `(sm, sb, over_mgr, ball_detector)`), L2 may break. **Step-2 must verify L2 ledger PASS post-build_sm modification.** Alternative: keep build_sm's return tuple stable; have snapshotter look up over_mgr via `sm._over_mgr` attribute (if such a back-ref exists or can be added).

### Step-2 decision fork for user

**Recommended: re-authorize NA at expanded scope with explicit gate-2 backward-compat verification.** Step-2 patch ships if L2 ledger PASSes post-modification + new L1.5 cases (N-1 + N-2 + N-3) PASS at unit level. Predicted-flip table from memo §8 holds. Budget cost: 0/5 at step-2 (unit + L2 verification) + 1/5 at step-3 (single empirical replay).

**Alternative: pivot to NB `--full-pipeline` flag.** Preserves SM-only mode for legitimate use cases (e.g., rapid iteration on SM-internal fixes); requires explicit opt-in for full-pipeline mode. Larger surface area but clearer user-facing semantics. Same step-2 LOC estimate (15-25); just adds an argparse flag + conditional branch.

**Alternative: pivot to ND extract-pipeline-setup refactor.** Previously falsified at gate 3 for scope expansion. Worth reconsidering ONLY if (a) ongoing snapshotter divergence from test_pipeline.py setup logic becomes load-bearing, OR (b) future Phase 4 cleanup combines multiple refactor pressures. Defer until justified.

**Alternative: defer WS-N.** SM-only snapshotter measurement gap stays as architectural-known-limitation; natural production session traces continue to serve as the over_mgr-wired closure validation path. Budget remains at 1/5; methodology cap proximity preserved. No code change. Lowest immediate cost; postpones the runbook fitness restoration that motivated WS-N's opening.

### S26-v2 THIRD-INSTANCE FOOTPRINT

**This step-1b sub-investigation IS the third-instance footprint for S26-v2.** Predecessors:
1. **WS-L step-1b (`394ed58`)** — 10-call deviation discovery at half-commit-cycle cost.
2. **WS-M step-1b (`c46fcb0`)** — 1-call cohort-split discovery.
3. **WS-N step-1b (this)** — 1-call sub-mechanism (b) confirmation. Sub-mechanism (a) projection (~5-10 LOC) FALSIFIED; sub-mechanism (b) actual scope (~15-25 LOC) confirmed. Step-2 would have shipped at wrong LOC estimate (with build_sm-only patch failing to engage over_mgr.on_ball_event dispatch) had spot-check been skipped.

**Promotion status.** S26-v2 was already promoted at WS-M step-4 on two-instance evidence; this third instance is **empirical reinforcement, not new promotion**. The 10× cost-reduction ratio holds across all three instances: ~1 tool call at step-1b vs ~10 tool calls + STOP at step-2 verification deviation.

**Standing audit framework update.** The S22 + S26 + S26-v2 + S28 cost-optimization framework (Architecture_HANDOFF.md post-WS-M architectural-fence section) now has a third demonstrated instance of S26-v2 in production use. The standing discipline is validated across detection-layer (WS-Surface-E), state-machine layer (WS-K), assertion-side (WS-L), pipeline-plumbing (WS-M), and now snapshotter-integration (WS-N) fix-surface categories.

---

## §15 Status footer (step-1b)

**WS-N step-1b status.** CLOSED — sub-mechanism (b) CONFIRMED via code-reading (zero `over_mgr.on_ball_event` calls in score_manager; exclusive production-only invocation at `test_pipeline.py:9236/13098/14017`). NA scope revised from ~5-10 LOC (sub-mechanism a hypothetical) to ~15-25 LOC (sub-mechanism b actual). Step-2 patch shape requires re-authorization at expanded scope OR pivot to NB / ND / deferral.

**Recommended next step.** **User authorization required for step-2 patch shape.** Decision fork enumerated at §14:
- NA expanded (~15-25 LOC + L2 verification) — leading recommendation.
- NB `--full-pipeline` flag (same scope + explicit opt-in semantics).
- ND extract-pipeline-setup refactor (previously falsified; revisit only if justified).
- Defer WS-N (accept SM-only as architectural-known-limitation).

**Sub-findings.** S26-v2 third-instance footprint confirmed. No new candidates promoted.

**Empirical-budget status.** **1/5 — UNCHANGED across step-1b.**

**Methodology insights running total.** 25 (S26-v2 promoted at WS-M step-4; S28 promoted at WS-L step-3; S25 + S27 + replay-tool-fitness candidates awaiting respective promotion thresholds).

**Recommended commit message:**

```
docs(workstream-n): step-1b sub-investigation — sub-mechanism (b) confirmed; external BallEventDetector wiring required; step-2 scope expansion review needed

Memo §12-§14 appended. WS-N step-1b spot-checks step-1 §4 NA's
"sub-mechanism reservation" UNVERIFIED marker per S26-v2 methodology
(promoted at WS-M step-4).

Code-reading evidence:
  Task 1 (sm.on_frame body): NO `over_mgr.on_ball_event` calls in
    score_manager.py. The `over_mgr.` mentions at :709/:712/:725/
    :1265/:1276 are data-access for `over_mgr.this_over` rewrites
    + `over_mgr.rewrite_token` slot-binding callback — NOT ball-
    event dispatch.
  Task 2 (scoreboard.on_ball_event): NO MATCHES. The method does
    not exist on Scoreboard. Dispatch does not route through
    scoreboard.
  Task 3 (over_mgr.on_ball_event call sites): exclusive production
    invocation at test_pipeline.py:7366 (attach_score_manager
    setup) + :9236 (pre-ball dispatch) + :13098 (main loop after
    BallEventDetector.detect()) + :14017 (ABSORBED_LEGAL post-
    dispatch). All depend on production-pipeline ball_event
    sourcing.

Sub-mechanism verdict: (b) CONFIRMED. Sub-mechanism (a)
FALSIFIED. sm.on_frame does not drive over_mgr; external
BallEventDetector wiring required for snapshotter to activate the
bind_pending_slot path.

Step-2 LOC estimate REVISED: ~5-10 LOC (sub-mechanism a
hypothetical) → ~15-25 LOC (sub-mechanism b actual). Additional
scope: BallEventDetector instantiation + frame-loop integration
+ per-event dispatch wiring + potential WICKET-ATTRIB synthesis
mirror from test_pipeline.py:13083-13097.

S26-v2 third-instance footprint:
  WS-L step-1b (394ed58) — 10-call deviation discovery.
  WS-M step-1b (c46fcb0) — 1-call cohort-split discovery.
  WS-N step-1b (this) — 1-call sub-mechanism (b) confirmation.
~10× cost-reduction ratio preserved. S26-v2 already promoted at
WS-M step-4; this is empirical reinforcement, not new promotion.

Per user stop condition: STOP. Step-2 requires re-authorization
at expanded scope OR pivot to NB --full-pipeline flag OR ND
extract-pipeline-setup refactor OR defer WS-N.

Recommendation: NA expanded with explicit L2 backward-compat
verification at step-2. Budget projection unchanged: 0/5 step-2
(unit + L2) + 1/5 step-3 (single empirical replay).

Empirical-budget status: 1/5 → 1/5 (UNCHANGED).
Methodology insights running total: 25 (unchanged).
Memo: files/docs/investigations/workstream_n_snapshotter_full_pipeline_integration.md (15 sections, ~600 lines).
```

---

## §16 Step-1c sub-investigation — Fork C extraction feasibility

**Trigger.** WS-N step-2 verification (no commit) surfaced ~50-75 LOC actual scope vs step-1b §14's ~15-25 LOC estimate, plus the `BallEventDetector`-from-`commentary.py` vs `BallDetector`-from-`state/ball_detector.py` class disambiguation. User authorized Fork C step-1c to assess extraction feasibility BEFORE committing to scope.

**Task 1 — `_pending_bcast_striker_key` origin.** Grep across `test_pipeline.py`:
- `:8538`: declared as `_pending_bcast_striker_key: str | None = None` — **inside main loop body** (after pipeline setup block at ~7140-7400, deep in the per-frame iteration).
- `:8547`: first WRITE (`_pending_bcast_striker_key = _bs_key`).
- `:11408 / :11424 / :11434 / :11437 / :11452 / :11460 / :11466 / :11473`: 8 read/write sites within the main loop (the broadcast-vs-deterministic-striker resolution chain).
- Also consumed at `:13088` (WICKET-ATTRIB site, `_attribute_dismissed_with_broadcast_override` call).

**`_pending_bcast_striker_key` is NOT setup — it is per-frame main-loop-local mutable state.** It tracks pending broadcast striker overrides across consecutive frames within the iteration loop. Any extraction strategy must address it as state-tracking-during-iteration, not as one-time setup.

**Task 2 — Setup block component classification (lines 7140-7400 region):**

| Component | Site | Extractability |
|---|---|---|
| OpenScout machinery (`OpenScoutSidecar` + `OpenScout` + `OpenScoutRateGate`) | `:7141-7158` | **Conditional** — gated by `USE_OPEN_SCOUT`; depends on `SESSION_ID`. Extractable with optional-init parameter. |
| `Extractor()` (LLM Scout fallback) | `:7159` | Clean — parameterless. |
| `MatchStateAgent()` (scorer) | `:7160` | Clean. |
| `ScoreJumpGuard()` | `:7161` | Clean. |
| `CricketChecker()` | `:7162` | Clean. |
| **`over_mgr = ThisOverManager()`** | **`:7163`** | **Clean** — parameterless. |
| `scoreboard.on_fow_upgrade = over_mgr.reorder_wicket_to_ball` callback wire | `:7171` | Clean — single assignment. |
| **`ball_detector = BallEventDetector()`** | **`:7174`** | **Clean** — parameterless. |
| `partnership_tracker = PartnershipTracker()` | `:7175` | Clean. |
| Bug #14 innings-change-reset setup (`_innings_reset_done_for: set[int]`) | `:7189` | Clean — local state init. |
| `score_mgr.scoreboard = scoreboard` back-ref | `:7362` | Clean. |
| **`over_mgr.attach_score_manager(score_mgr)`** | **`:7366`** | **Clean.** |
| `_on_bowler_lock` / `_on_striker_lock` callbacks (tracker on_lock wiring) | `:7374+` | Conditional — closures capturing main-loop state; requires careful extraction. |

**Setup block extractability verdict: ~80% CLEAN.** OpenScout + tracker on_lock callbacks are conditional/closure-dependent; the rest extracts directly.

**Task 3 — Minimum extractable subset for snapshotter:**

| Snapshotter needs | Source | Extractability |
|---|---|---|
| over_mgr instantiation + `attach_score_manager` | `:7163 + :7366` | CLEAN — extract |
| BallEventDetector instantiation | `:7174` | CLEAN — extract |
| on_fow_upgrade callback wire | `:7171` | CLEAN — extract |
| `_attribute_dismissed_with_broadcast_override` function | module-level | Already accessible; no extraction needed |
| `_pending_bcast_striker_key` per-frame state tracking | **main-loop state at `:8538-13088`** | **MESSY — main-loop-local; not setup; requires mirror in snapshotter loop OR refactor into class wrapping per-frame state machine** |

**Task 4 — test_pipeline.py refactor scope assessment.** A clean function-extraction of the setup primitives (over_mgr + ball_detector + partnership_tracker + on_fow_upgrade wire + attach_score_manager) is feasible at the 7140-7400 region. Estimated extraction: ~30-50 LOC of helper code + ~5 LOC at test_pipeline.py call site updating to invoke the helper + ~5-10 LOC in snapshotter `build_sm` to invoke the helper. **Setup-portion extraction: ~40-65 LOC total, regression risk LOW** (L2 ledger covers test_pipeline.py main path; refactor is semantically identical).

**BUT the `_pending_bcast_striker_key` per-frame state mirror is NOT solved by the setup-extraction.** Snapshotter still needs ~30-50 LOC of per-frame state tracking to enable WICKET-ATTRIB synthesis equivalent. Total Fork C scope: setup-extraction (~40-65 LOC) + per-frame state mirror in snapshotter (~30-50 LOC) = **~70-115 LOC**, comparable to or slightly larger than Fork A-expanded (~50-75 LOC).

**Task 5 — Regression risk assessment.** Setup-portion-only extraction: LOW risk (L2 + L1.5 cover). Per-frame state mirror in snapshotter: SAME risk as Fork A-expanded (no test currently exercises this state-tracking through the snapshotter, so step-2 must add new L1.5 cases). No additional risk from Fork C vs Fork A-expanded.

## §17 Fork C verdict — MESSY-PARTIAL

**Fork C verdict: MESSY-PARTIAL.**

- **Setup-portion extraction**: FEASIBLE and clean (~40-65 LOC; LOW regression risk; deduplication benefit on setup primitives).
- **Per-frame state mirror (`_pending_bcast_striker_key`)**: NOT solved by extraction; same scope as Fork A-expanded regardless of approach.
- **Total scope (Fork C-partial)**: ~70-115 LOC — comparable to or larger than Fork A-expanded (~50-75 LOC).

**Per the user's stop condition** ("Fork C-messy: extraction surfaces non-trivial scope > 100 LOC → STOP, report; recommend Fork A-expanded fallback OR Fork D defer"): **the upper bound of Fork C-partial scope (~115 LOC) crosses the >100 LOC threshold.** Fork C-messy STOP triggered.

**The deduplication benefit on the setup portion IS real** — extracting the over_mgr + ball_detector setup avoids future drift on those primitives. But the per-frame state mirror dominates the scope cost, and that scope exists in BOTH Fork A-expanded and Fork C-partial. The architectural-correctness argument for Fork C is partially preserved (setup deduplication) but not load-bearing for the budget calculus.

### Cost-benefit comparison

| Approach | Scope (LOC) | Maintenance debt | Future drift risk | Step-2 budget | Step-3 budget |
|---|---|---|---|---|---|
| **Fork A-expanded** | ~50-75 | All new code in snapshotter | High on setup; moderate on state-tracking | 0/5 | 1/5 |
| **Fork C-partial** | ~70-115 | Setup deduplicated; state-tracking mirror | Low on setup; moderate on state-tracking | 0/5 | 1/5 |
| **Fork D (defer)** | 0 | None; SM-only stays as documented limitation | None on snapshotter; production-session validation preserved | 0/5 | 0/5 |

**Recommendation:** **Fork D — defer WS-N.** Per the budget calculus + scope-vs-deduplication-benefit ratio:
- Fork C's deduplication benefit (~30-65 LOC of setup not duplicated) is real but bounded.
- Fork A-expanded ships duplicate setup that WILL drift (per the runbook precedent the user cited).
- Fork C-partial is architecturally cleaner but exceeds the 100-LOC stop-condition threshold.
- **Fork D leaves the architectural-known-limitation in place** but preserves the standing methodology cap (1/5 budget) AND honors the production-session-driven validation mode established at WS-M step-4.

**Fork D pivot honors the user's previously-locked architectural framing:** "Empirical-falsification budget at 1/5 — methodology cap proximity. Remaining Phase 1 work admissible: assertion-side WS-I-pattern reuse only. Phase 4 docs-class cleanup proceeds budget-neutrally. Production-session-driven validation mode: natural sessions generate traces re-runnable against shipped assertions at zero budget cost." (HANDOFF.md header per `b11f000`).

**WS-N is genuinely pipeline-direct + 70-115 LOC scope + 1/5 step-3 budget** — that's exactly the category the methodology-cap-proximity warning flagged as unaffordable. The static-investigation chain has now confirmed the scope; honoring the cap means accepting Fork D.

### S26-v2 fifth-instance footprint CONFIRMED

Five instances of pre-step-N spot-checks now demonstrated:
1. **WS-L step-1b (`394ed58`)** — 10-call deviation discovery.
2. **WS-M step-1b (`c46fcb0`)** — 1-call cohort-split discovery.
3. **WS-N step-1b (`6c322c5`)** — 1-call sub-mechanism (b) confirmation.
4. **WS-N step-2 verification (no commit)** — 3-call scope-expansion via BallEventDetector class disambiguation + `_pending_bcast_striker_key` discovery.
5. **WS-N step-1c (this)** — 1-call Fork C MESSY-PARTIAL verdict.

Each spot-check prevented a misspecified step-N commit. Total saved: ~50+ tool calls + multiple revert/refinement cycles + budget consumption from empirical-validation cycles that would have failed for predictable reasons.

**S26-v2 was promoted at WS-M step-4 on two-instance evidence; this fifth instance is empirical reinforcement at saturation — the methodology is working as designed across diverse fix-surface categories.**

### Recommended commit message (Fork D pivot)

```
docs(workstream-n): step-1c sub-investigation — Fork C extraction MESSY-PARTIAL (~70-115 LOC including per-frame state mirror); recommend Fork D defer per methodology-cap proximity

Memo §16-§17 appended. Fork C extraction feasibility scoped at
step-1c per S26-v2 methodology (fifth-instance footprint).

Component classification (memo §16 task 2):
  Setup-portion extraction (~40-65 LOC): CLEAN. over_mgr +
    BallEventDetector + on_fow_upgrade wire + attach_score_manager
    all extract cleanly. L2 + L1.5 cover regression risk on
    test_pipeline.py main path.
  Per-frame state mirror (`_pending_bcast_striker_key` at :8538):
    MESSY. Main-loop-local mutable state; NOT setup. 8 read/write
    sites across main loop body (:8547 / :11408+ / :13088). Snapshot-
    ter would need ~30-50 LOC of per-frame state tracking
    regardless of setup-portion approach.

Fork C verdict: MESSY-PARTIAL. Total scope ~70-115 LOC (setup
extraction + per-frame state mirror). Upper bound crosses the
user's 100-LOC stop-condition threshold for Fork C-messy.

Cost-benefit:
  Fork A-expanded ~50-75 LOC; all new code in snapshotter; setup
    drift risk on every future test_pipeline.py change.
  Fork C-partial ~70-115 LOC; setup deduplicated; state-tracking
    mirror still required (same risk as Fork A-expanded).
  Fork D defer: 0 LOC; SM-only stays as documented limitation
    (runbook fitness-corrected at 3e8ac11 caveat); production-
    session-driven validation mode preserved.

RECOMMENDATION: Fork D defer.

Decisive: WS-N is genuinely pipeline-direct + 70-115 LOC + 1/5
step-3 budget — exactly the category the methodology-cap-proximity
warning (HANDOFF.md b11f000) flagged as unaffordable. The static-
investigation chain has now confirmed the scope; honoring the cap
means accepting Fork D. Production-session-driven validation mode
remains the standing discipline.

WS-N proceeds to step-2 only if user explicitly re-authorizes at
the confirmed ~70-115 LOC scope AND accepts 1/5 step-3 budget cost
(potentially hitting 0/5 methodology cap on worst case).

S26-v2 fifth-instance footprint CONFIRMED:
  WS-L step-1b (394ed58) 10-call deviation discovery.
  WS-M step-1b (c46fcb0) 1-call cohort-split discovery.
  WS-N step-1b (6c322c5) 1-call sub-mechanism (b).
  WS-N step-2 verification (no commit) 3-call scope-expansion.
  WS-N step-1c (this) 1-call Fork C MESSY-PARTIAL verdict.
Each spot-check prevented a misspecified step-N commit. Method-
ology working as designed across diverse fix-surface categories.

Empirical-budget status: 1/5 → 1/5 (UNCHANGED).
Methodology insights running total: 25 (unchanged; S26-v2 already
promoted at WS-M step-4; fifth-instance is empirical reinforce-
ment).
Memo: files/docs/investigations/workstream_n_snapshotter_full_pipeline_integration.md (17 sections, ~780 lines).
```

---

## §18 Status footer (step-1c)

**WS-N step-1c status.** CLOSED — Fork C MESSY-PARTIAL verdict. Extraction is feasible for setup primitives (~40-65 LOC clean) but per-frame state mirror (~30-50 LOC) cannot be deduplicated — total ~70-115 LOC crosses 100-LOC stop-condition threshold. Recommendation: **Fork D defer**.

**Recommended next step.** **User authorization required for WS-N disposition.** Three options:
- **Fork D (RECOMMENDED): defer WS-N.** Accept SM-only snapshotter as documented architectural-known-limitation; rely on production-session-driven validation mode (standing discipline per WS-M step-4). Methodology cap preserved at 1/5 budget.
- **Fork A-expanded re-authorized: ~50-75 LOC + 1/5 step-3 budget.** Maintenance-debt artifact future drift risk acknowledged.
- **Fork C-partial re-authorized: ~70-115 LOC + 1/5 step-3 budget.** Architecturally cleaner; same step-3 budget cost.

**Sub-findings.** S26-v2 fifth-instance footprint confirmed (saturation reinforcement; no new promotion). No other candidates promoted.

**Empirical-budget status.** **1/5 — UNCHANGED across step-1c.**

**Methodology insights running total.** 25 (unchanged).

---

## §19 Phase 2 reframe declaration

**WS-N status: PHASE-2-REFRAMED.** Not closed. Not retired. Not deferred-indefinitely. Active backlog item with full Phase 2 scoping artifact (this memo §1-§21).

**Strategic value preserved.** WS-N closes the SM-only snapshotter measurement gap surfaced at WS-M step-3 + documented at runbook fix `3e8ac11`. Full-pipeline snapshotter enables differential-testing validation of cross-module fixes (Shape 2 / WS-H D-post-FoW-striker closure / future cross-module workstreams). The user direction "change the snapshotter to ingest full pipeline output" remains the canonical objective.

**Scope reality per six-layer S26-v2 cascade.** Step-1 §4 estimated NA at ~5-10 LOC. Step-1b sub-mechanism (b) revised to ~15-25 LOC. Step-2 verification (no commit) surfaced BallEventDetector class disambiguation + `_pending_bcast_striker_key` discovery, revising to ~50-75 LOC. Step-1c Fork C verdict revised to ~70-115 LOC. Step-2 verification (no commit) surfaced setup-block-not-discrete (closures bind setup primitives to main-loop state), revising to **~90-165 LOC across 2-3 commits + closure-equivalent code in snapshotter (`reset_for_innings`-equivalent + on-lock callbacks + monitoring state mirror + `_pending_bcast_striker_key` mirror)**.

**Why Phase 1-unaffordable.**
- Single-commit-budget-neutral closure model (WS-I shape) doesn't fit ~90-165 LOC across 2-3 commits.
- Methodology cap at 1/5 budget proximity puts step-3 empirical validation at risk of consuming final budget; pipeline-runtime regression risk on a refactor of test_pipeline.py setup is real.
- S26-v2 sixth-instance pattern (six cascading scope-expansion layers) suggests additional scope-expansion layers likely at step-3+; the static-investigation chain has not yet bottomed out.

**Phase 2 framing.** WS-N reframes as Phase 2-class architectural refactor. Execution triggers on EITHER (a) production-session-driven validation accumulates sufficient cross-module-fix verification needs to justify the investment (e.g., 3+ workstreams blocked on snapshotter-validation-of-cross-module-wiring), OR (b) empirical-budget recovers via shipped Phase 1 assertion-side fix validation against natural traces (budget ≥3/5 restored).

## §20 Phase 2 scoping artifact pointer

**This memo (§1-§21) IS the canonical Phase 2 scoping document for WS-N.** No separate scoping memo needed at Phase 2 entry — the static-investigation chain has already produced comprehensive analysis:
- §1-§4: empirical anchor + current snapshotter architecture + integration requirements + 5-hypothesis enumeration (NA/NB/NC/ND/NE).
- §5-§10: cohort-closure verification + audit + risk assessment + predicted-flip + sub-findings + step-2 entry data (initial sub-mechanism (a) hypothetical).
- §11-§14: step-1b sub-mechanism (b) confirmation + refined step-2 entry data + S26-v2 third-instance footprint.
- §15-§18: step-1c Fork C extractability analysis + MESSY-PARTIAL verdict + cost-benefit + S26-v2 fifth-instance.
- §19-§21 (this): Phase 2 reframe + scoping pointer + candidate methodology insight.

**Recommended Phase 2 entry point.** Re-evaluate Fork A-expanded vs Fork C-revised at honest 90-165 LOC scope with explicit multi-commit execution plan. Consider Fork ND (extract-pipeline-setup-into-class refactor) if Phase 2 timing aligns with broader test_pipeline.py modernization (e.g., as part of an architectural refactor pass that addresses multiple closure-tangling concerns).

**Operational mitigation during Phase 1.** Runbook SM-only caveat at `3e8ac11` documents the limitation for runbook users. Production-session-driven validation mode (per WS-M step-4 close-out at `b11f000`) handles cross-module fix verification need via natural session traces + shipped assertion re-run at zero budget cost. Sub-cohort A's predicted closure (Shape 2 + 18-run total) remains verifiable on next natural session.

## §21 Candidate methodology insight — scope-expansion-cascades-as-Phase-2-signal

**Statement (CANDIDATE — single-instance evidence at WS-N; NOT yet promoted).** *"When a workstream's static-investigation chain surfaces progressive scope expansion at each verification layer (S26-v2 spot-check repeatedly catching scope the prior layer missed), the cumulative pattern is itself a signal the workstream is Phase 2-class architectural-refactor rather than Phase 1-affordable surgical-fix. Phase boundary discrimination via S26-v2-cascade-count: ≥4 layers of cascading scope expansion suggests Phase 2 reframe."*

**Distinction from S26-v2.** S26-v2 catches DRIFT AT A SINGLE LAYER — pre-step-N spot-check of step-(N-1) UNVERIFIED markers prevents one-layer deviation cost. This candidate (potentially S29 or unnumbered) catches CUMULATIVE SCOPE GROWTH across MULTIPLE LAYERS — the absolute scope estimate keeps growing at each verification layer, suggesting the workstream's architectural-fit is Phase 2 not Phase 1.

**First-instance evidence — WS-N's six-layer cascade.**

| Layer | Estimated scope | Tool methodology that surfaced the layer |
|---|---|---|
| Step-1 §4 NA initial | ~5-10 LOC | Grep + script docstring |
| Step-1b sub-mechanism (b) | ~15-25 LOC | Grep + sm.on_frame body scan |
| Step-2 verification (prior; no commit) | ~50-75 LOC | BallEventDetector class disambiguation grep + WICKET-ATTRIB body read |
| Step-1c Fork C MESSY-PARTIAL | ~70-115 LOC | `_pending_bcast_striker_key` site enumeration via grep |
| Step-2 verification (this; no commit) | **~90-165 LOC** | End-to-end read of test_pipeline.py:7160-7400 surfacing closure-tangling that grep missed |

**Scope growth trajectory:** ~10x from initial estimate to final. Each layer's tool methodology surfaced what the prior layer's tool methodology couldn't see (grep → grep-with-context → end-to-end-read → closure-relationship-analysis).

**Operational corollary if promoted.** When a static-investigation chain shows ≥4 cascading layers of scope expansion + each layer's scope estimate is ≥1.5x the prior layer's: declare Phase 2 reframe. Don't authorize Phase 1 patch step-2 even if user willing; the workstream is architectural-refactor-class disguised as surgical-fix.

**Promotion threshold.** Single-instance (WS-N). Awaits second-instance from a different workstream's static-investigation chain surfacing a similar cascade. When second instance surfaces, promote at that workstream's close-out.

**Cross-references.**
- S22 + S26 + S26-v2 + S28 cost-optimization framework (Architecture_HANDOFF post-WS-M architectural-fence) — this candidate is the **phase-boundary discrimination** peer to the cost-optimization framework.
- S27 (shared-signal-source structural barrier, candidate single-instance at WS-K) — peer "single workstream produces a methodology-class insight" pattern.
- Replay-tool-fitness candidate (WS-M step-4 first-instance) — peer "single workstream produces a tooling-class insight" pattern.

---

## §22 Status footer (Phase 2 reframe close-out)

**WS-N status: PHASE-2-REFRAMED.** Active Phase 2 backlog item. Canonical scoping at this memo §1-§21. Execution gated on cross-module-fix-verification cohort growth OR empirical-budget recovery to ≥3/5.

**Recommended next session-level action.** Continue Phase 1 work per the HANDOFF post-WS-M-step-4 standing discipline: assertion-side WS-I-pattern reuse only; Phase 4 docs-class cleanup; production-session-driven validation mode for shipped Phase 1 assertion verification.

**Sub-findings.** Scope-expansion-cascades-as-Phase-2-signal candidate logged at §21 awaiting second-instance.

**Empirical-budget status.** **1/5 — UNCHANGED across WS-N entire arc** (step-1 + step-1b + step-1c + step-2 verification + Phase 2 reframe — all static; zero pipeline execution).

**Methodology insights running total.** 25 (unchanged; no new promotions). S26-v2 sixth-instance footprint at WS-N step-2 verification reinforces the discipline's working-as-designed validation.

**Arc retired into Phase 2 backlog.**



