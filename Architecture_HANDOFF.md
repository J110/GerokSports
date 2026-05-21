# Handoff — derive-not-detect branch

**Session date.** 2026-05-20.
**Branch.** `derive-not-detect` (current HEAD: `40b14c7`).
**Session ledger.** 17 commits this session. Layer 1.5 (36/36) + Layer 2
(30 balls) held on every one. Predicted-flip claims empirically validated
at each step.

---

## 1. Workstream goal

Improve the cricket scoreboard pipeline's correctness by replacing
*speculative deletion + speculative fixes* with **empirically-grounded
audit-driven discipline**. Every classification (bug-class hypothesis,
NOT-A-DEFECT verdict, fix-feasibility claim, "already addressed" verdict)
is a hypothesis pending empirical verification against captured trace data.

The §7 "candidate deletion list" framing in
`files/docs/investigations/sm_as_orchestrator_design.md` is **officially
retired** as of this session. The new framing: **empirically-grounded bug
classes with their own design memos, per-class fix sequencing, and trace-
session assertions as regression detectors**.

---

## 2. Session architectural-significance milestone

**F1 (commit `437d952`) — a one-line field-name fix in `_accept_initial`
— closed at minimum FOUR bug classes** when measured against the captured
Scout dump for `validate_gtrr_20260520_180715`:

1. **B-ε direct fix**: cold-start initial-striker mis-resolution
2. **B-β cascade closure**: SM wicket dispatch missed (both wickets at
   frames 979 and 1190 now dispatch correctly)
3. **Multi-ball decomposition collapse**: 5 false-positive gaps → 0
4. **Compound tokens (`Wd+N`) collapse**: 2 emitted → 0

The cross-credit cascade (Gill credited Sai's runs throughout pre-F1
session) collapsed entirely. **The cross-fixture verification step that
revealed this is now §7.2 gate 7** — every fix commit must be followed
by replay against captured data to identify cascade-closure findings.

**Meta-lesson permanently baked into the workstream.** Empirically
validated discipline saves engineering work. Without gate 7, this session
would have spent capacity on operationally-redundant B-β / compound-token
/ B-α-rotation fix memos. Gate 7 caught the cascade and saved that work.

---

## 3. What we did (commit chain)

| # | Commit | Scope | Outcome |
|---|---|---|---|
| 1 | `192be39` | Stale-test cleanup | 8 dead tests removed |
| 2 | `8f8a7c7` | Memo §7.1–§7.4 + dispatch scoping doc | Queue B / `_ScoutRetryBuffer` reclassified Keep |
| 3 | `95e6ff5` | Dispatch-loop scaffold | `SM_INLINE_MULTI_BALL` flag + `DISPATCH-LOOP-SHADOW-COMPARISON` trace |
| 4 | `83ebda7` | S5a closure | NOT-A-DEFECT (broadcast_extra vs extras_type are not aliases) |
| 5 | `79989b8` | S5b memo | broadcast_striker Split S5b-1/2/3 |
| 6 | `a7306cd` | S5b-2 instrumentation | `STRIKER-IDENTIFY-FALLBACK-INVOKED` trace |
| 7 | `3dbace9` | **S5b-2 deletion shipped** | Broadcast fallback at `_identify_striker:4689-4698` removed (corpus showed 0 load-bearing invocations) |
| 8 | `dd0fdde` | S5b-3 design memo | Three-phase refactor proposed |
| 9 | `6aea92f` | S5b-3a scaffold | Post-wicket slot-diff + `STRIKER-POST-WICKET-DERIVATION` trace |
| 10 | `696b7e4` | **Lag bound shrink shipped** | `_PENDING_BOWLER_BALL_CREDIT_MAX_LAG` 40 → 20 (production data: 0 orphans, max lag 13) |
| 11 | `1d92101` | Trace assertion library | Five empirically-grounded invariants + broken-but-known baseline |
| 12 | `ea27ba5` | S5b-3 Context A re-audit | Failure mechanism: `card.get("broadcast")` is unwritten dead field |
| 13 | `437d952` | **F1 ship** | `card.get("broadcast")` → `card.get("broadcast_striker")` in `_accept_initial:2789-2808` |
| 14 | `fcbd5ef` | B-α memo + B-ζ falsification | Two bugs (real B-α + shadow snapshot) + recursive gate-6 |
| 15 | `37f63ad` | **F-α-shadow shipped** | Snapshot reads `sb.bowling_card` not `sb._inn["bowling_card"]` |
| 16 | `4d3fb33` | **F-α-queue shipped** | Queue B extends to ABSORBED_LEGAL when bowler_name=None |
| 17 | `c0f30cf` | B-β cascade closure memo | Empirically confirmed; no separate fix needed |
| 18 | `40b14c7` | Cascade pattern + gate 7 | §7.2 hardened from 6 → 7 gates; cross-fixture verification standing |

---

## 4. Pipeline architecture (next-agent essentials)

### 4.1 Top-level flow

```
Vision (Scout VLM)
  → extract_regex.parse_strip (per-frame OCR → structured dict)
  → test_pipeline.run_test main loop
  → ScoreManager.on_frame (the SM, in score_manager.py)
  → Scoreboard (eyes/scoreboard.py — separate tracking layer)
  → WebSocket UI payload (build_full_payload at output boundary)
```

**Key separation**: `ScoreManager` (SM) maintains its own state
(`self.striker`, `self.bowler_name`, `self.bat1_name`, etc.). The
`Scoreboard` maintains its own state (`scoreboard.batting_card`,
`scoreboard.bowling_card`, `scoreboard._inn` — running innings dict).
**These two layers can diverge.** Most B-class bugs this session
traced to SM state diverging from Scoreboard tracking.

### 4.2 The 5-primitive contract

The pipeline derives UI state from five primitives:
- `score` (int)
- `wickets` (int)
- `overs` (decimal like `5.3`)
- `bat1_name`, `bat2_name` (str — the two at-the-crease batters)
- `bowler_name` (str)

Plus `extras_type` (event-level subtype label for bye/leg-bye)
and `broadcast_extra` (frame-level WD/NB OCR signal). These two are
**parallel fields with different semantics**, NOT aliases — see §7.5
of `sm_as_orchestrator_design.md`.

### 4.3 Deterministic rotation override (commit 2105463)

`score_manager.py:4295-4325`. Once `self.striker is not None`, any
broadcast-derived striker write is **rejected** with a
`STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC` trace. SM owns the
striker once locked; broadcast indicators are corroboration only,
not authority.

**Implication**: cold-start initial-striker assignment is the
critical correctness point. If wrong at first WARM entry, the
override prevents any subsequent broadcast-driven correction. This
is exactly the failure mode B-ε exhibited; F1 fixes it.

### 4.4 Queue B (canonical 3-way-race resolver)

`_pending_bowler_ball_credits` at `score_manager.py:5283` (producer)
and `:5714` (consumer). Resolves the race between:
- Bowler name resolution
- Legal ball commit
- Bowler-tracker `on_lock` callback

Two drain triggers: D1 inline (next ball commit) + D2 (tracker
on_lock callback at `test_pipeline.py:7223`). F-α-queue (commit
`4d3fb33`) extended Queue B to ABSORBED_LEGAL events when
bowler_name=None at gap commit.

**Important**: §7.1 of the main memo reclassifies Queue B from
"scar tissue to delete" to **load-bearing Keep**. The mechanism is
canonical, not scar; the original §7 framing was wrong.

### 4.5 Trace infrastructure

- **Trace JSONL**: `logs/trace/<SESSION_ID>.jsonl` per session, written by
  `files/trace_emitter.py`'s `TraceWriter`. Schema: header line +
  per-frame records with nested `scorer.decisions` array.
- **DecisionLogHandler**: auto-promotes `log.info("[TAG] ...")` lines
  to decision entries. Most tags are auto-captured.
- **KNOWN_TAGS registry** at `trace_emitter.py:57`. Tags not in this
  set are still captured but flagged `known=False`.
- **Per-site `_trace.get_recorder().record(tag=..., **payload)`** for
  richer typed payloads.

### 4.6 Test harness layers

| Layer | File | Purpose | Pre-commit gate |
|---|---|---|---|
| L1.5 | `files/tests/test_sm_derivation_ledger.py` | 36-ball ledger, hand-derived FrameInputs, fast SM-derivation check | YES |
| L2 | `files/tests/test_pipeline_captured_replay.py` | 29-ball ledger-matched commits, real captured Scout dump (dc-vs-kkr) | YES |
| Trace assertions | `files/tests/trace_session_assertions.py` | Session-aggregate empirically-grounded invariants | runner only (no gate yet) |
| Per-ball assertions | `files/tests/symptom_class_assertions.py` | 12-class symptom library (L2-integrated) | via L2 |

Pre-commit hook at `.git/hooks/pre-commit` runs L1.5 + L2 on every
commit. **Never bypass with `--no-verify`** unless user explicitly
authorizes.

### 4.7 Feature flags

- `SM_INLINE_MULTI_BALL` (default off): inline multi-ball gap path
  scaffold (commit `95e6ff5`). Shadow comparison fires regardless.
- `SM_POST_WICKET_SLOT_DIFF` (default off): post-wicket slot-diff
  scaffold (commit `6aea92f`). Shadow comparison fires regardless.
- `USE_OPEN_SCOUT` / `USE_OPEN_SCOUT_SPANS`: pre-existing parallel-Scout
  flags. See `CLAUDE.md` for details.

---

## 5. §7.2 audit checklist (standing precondition — 7 gates)

Before any §7 deletion OR fix commits:

1. **Enumerate all callers** of the symbol under change (Grep, exhaustive).
2. **Classify each caller** (init / transition / preserved / consumer / producer).
3. **Cross-reference with adjacent state mechanisms** (queues, drains,
   tracker callbacks, archive hooks). Enumerate every race ordering.
4. **Equivalence proof** for proposed replacement.
5. **State variable lifecycle** — reset / clear / accumulation points.
6. **Predicted flip gate** — predict the assertion-library flip count
   BEFORE the dry-run, citing **concrete frame numbers from captured
   trace data**, not qualitative code-path reasoning. **Gate 6 applies
   recursively to ALL classifications** — bug-class hypotheses,
   NOT-A-DEFECT verdicts, fix-feasibility claims, "already addressed"
   verdicts.
7. **Cross-fixture verification** — after the fix lands, replay the
   relevant captured Scout dump and re-run trace-session assertions to
   check which OTHER reported bug-class hypotheses still reproduce.
   Cascade-closure findings update the **workstream queue**, not the
   engineering queue.

**Track record** demonstrating discipline pays off:
- Queue B reclassified Keep (saved a wrong deletion attempt)
- `_ScoutRetryBuffer` reclassified Keep (same)
- S5a NOT-A-DEFECT (saved a misguided rename effort)
- S5b-2 deletion shipped after corpus check (zero load-bearing invocations)
- B-ζ falsified one turn after gate 6 baked in (saved a fix memo)
- B-β cascade-closed by F1 (saved a fix memo)
- F-α-shadow self-catch (caught false positives in my own tooling)

---

## 6. Five observability streams (data-collection mechanism)

Each stream answers a different decision; together they converge into
one production session's data:

| Stream | Question | Gate decision |
|---|---|---|
| `PATH-B-FIRED` | Is `COLD_START_PHYSICS_PROMOTE` dead code? | S4a step (ii) Path B deletion |
| `PENDING-BOWLER-BALL-CREDIT-ORPHANED` | Is the lag bound over-provisioned? | Lag-bound tune (`696b7e4` shipped) |
| `DISPATCH-LOOP-SHADOW-COMPARISON` | Does inline multi-ball-gap match dispatch loop? | `SM_INLINE_MULTI_BALL` flag flip |
| `STRIKER-IDENTIFY-FALLBACK-INVOKED` | Does state_fallback remain authoritative post-S5b-2? | Regression detector for S5b-2 deletion |
| `STRIKER-POST-WICKET-DERIVATION` | Does slot-diff match broadcast Priority 3 in post-wicket gap? | `SM_POST_WICKET_SLOT_DIFF` flag flip |

Plus `ABSORBED-LEGAL-BOWLER-QUEUED` (new this session, F-α-queue's
queuing path).

---

## 7. Trace-session assertions (regression detectors)

Five empirically-grounded invariants at
`files/tests/trace_session_assertions.py`. Each fires against a session's
captured trace JSONL:

| Assertion | Bug class | Pre-F1 baseline | Post-F1 expected |
|---|---|---|---|
| `trace_alpha_bowler_runs_sum` | B-α (multi-ball gap bowler credit) | gap=25 runs | significant reduction |
| `trace_beta_sm_wicket_dispatch` | B-β (SM wicket dispatch missed) | 2 misses | PASS (cascade closed by F1) |
| `trace_epsilon_initial_striker` | B-ε (cold-start striker mis-resolution) | FAIL @ frame 12 | PASS (F1 direct fix) |
| `trace_compound_tokens` | Compound `Wd+N` encoding | 2 emissions | PASS (cascade closed) |
| `trace_extras_total` | UI extras_total inconsistency | gap=9 | UI render layer; separate scope |

Runner: `python files/scripts/run_trace_session_assertions.py [TRACE_PATH]`.
Defaults to `logs/trace/validate_gtrr_20260520_180715.jsonl`.

`SESSION_CONTEXT` map in the runner: per-session-stem dict with
`expected_initial_striker`, etc. When a fresh session lands, add its
filename stem with the canonical opening pair and run the assertions.

---

## 8. What's pending

### 8.1 Operational gate (not engineering)

**Natural production session.** Run the pipeline normally on the next
match. The session's trace gets captured automatically to
`logs/trace/<SESSION_ID>.jsonl`. F1 + F-α-shadow + F-α-queue are in
production code (post-commit `4d3fb33`).

### 8.2 Validation step (after operational gate)

1. Add the new session's filename stem to `SESSION_CONTEXT` in
   `files/scripts/run_trace_session_assertions.py` with the canonical
   `expected_initial_striker` for that match.
2. Run `python files/scripts/run_trace_session_assertions.py
   logs/trace/<NEW_SESSION>.jsonl`.
3. Confirm predicted flips materialize:
   - `trace_epsilon_initial_striker` FAIL → PASS
   - `trace_beta_sm_wicket_dispatch` FAIL → PASS
   - `trace_compound_tokens` FAIL → PASS (likely)
   - `trace_alpha_bowler_runs_sum` significant reduction
   - `trace_extras_total` may stay FAIL (UI render layer, separate scope)
4. Any **unflipped assertions** become the next concrete engineering
   targets — empirically grounded, not speculative.

### 8.3 Deferred latent fixes (no current empirical pressure)

- **F-α-rotation**: striker rotation skipped when bowler=None in
  ABSORBED_LEGAL. Same architectural gate as F-α-queue's bowler-credit
  fix but the rotation logic uses `gap_meta` state tracking. Separate
  audit needed; lower priority post-F1-cascade.
- **`SM_INLINE_MULTI_BALL` flag flip**: requires dispatch-loop shadow
  comparison data on a session with non-zero multi-ball gaps. Post-F1
  the validate_gtrr replay shows zero such gaps; need a different
  fixture or a fresh session.
- **`SM_POST_WICKET_SLOT_DIFF` flag flip**: requires
  `STRIKER-POST-WICKET-DERIVATION` shadow data accumulating in
  production. validate_gtrr session yielded zero events because both
  wickets bypassed `_apply_wicket_fall_only` pre-F1; post-F1 the
  dispatches happen so future sessions should produce shadow data.
- **S4a step (ii) Path B deletion**: BLOCKED. 3 production firings of
  `PATH-B-FIRED` in validate_gtrr session. The "Path B dead in test
  corpus" claim was falsified. Re-audit needed.
- **`_PENDING_BOWLER_BALL_CREDIT_MAX_LAG`**: shrunk 40 → 20 this
  session. Could shrink further if production data shows max lag stays
  well below 20. Re-evaluate after several sessions.

### 8.4 UI render layer (separate workstream)

- **Recent Overs panel drops entries**: `over_history` has all 14
  archived overs; UI drops some at render time. Frontend bug.
- **UI bottom-strip striker diverges from SM striker**: two parallel
  render paths, two different answers. Frontend bug.
- **`extras_total` UI inconsistency**: UI's `extras_total=1` vs archived
  10 Wd/Nb tokens. UI render layer.

These are out of scope for the SM/pipeline workstream.

### 8.5 §7 candidate list status (post-sweep)

The §7 list is now a dependency graph, not a deletion queue. See §7.4
of `sm_as_orchestrator_design.md` for the full candidate table. Most
items are now classified Keep, Done, Conditional, or Deferred.

---

## 9. Key files for next agent

### 9.1 Production code (touch carefully)

- `files/score_manager.py` — main SM. Critical sections:
  - `_accept_initial:2789-2808` — F1 fix lives here (cold-start striker)
  - `_apply_wicket_fall_only:5089+` — wicket FOW recording (S5b-3a slot-capture lives here)
  - `_apply_event:5378+` — main event dispatcher
  - `_apply_absorbed_event:5176+` — ABSORBED_LEGAL handler (F-α-queue lives in the new elif branch)
  - `_identify_and_set:4201+` — striker resolution (Priority 1/2/3 + override at :4295-4325)
  - `_identify_striker:4661+` — event-inference striker resolution (S5b-2 deletion shipped here)
  - `_handle_warm:3252+` — frame dispatch + dispatch-loop scaffold
  - `_capture_multi_ball_shadow_state:4515+` — F-α-shadow fix lives here
  - `_decompose_multi_ball:4427+` — MULTI_BALL gap expander
  - Constants at top: `_PENDING_BOWLER_BALL_CREDIT_MAX_LAG=20`, `SM_INLINE_MULTI_BALL`, `SM_POST_WICKET_SLOT_DIFF`
- `files/test_pipeline.py` — main pipeline entry. Critical sections:
  - `:1781-1783` — Scout's `*`-marker extraction → `striker_broadcast`
  - `:7211-7234` — bowler/striker tracker on_lock callbacks (D2 for Queue B)
  - `:13820-13823` — FrameInput hydration from Scout `_bcast` dict
- `files/eyes/scoreboard.py` — Scoreboard. Mostly stable but
  `update_bowler_card:2926+` and `update_batter_card:2853+` are the
  per-ball write paths. **`sb.bowling_card` (attribute) vs
  `sb._inn["bowling_card"]` (unused) — always read `sb.bowling_card`!**
- `files/eyes/this_over.py` — ThisOverManager (per-over token tracking)
- `files/eyes/extract_regex.py` — Scout strip OCR parser. `:386`
  sets `striker:True` on the per-batter dict from `*`-marker detection.
- `files/trace_emitter.py` — TraceWriter, KNOWN_TAGS, DecisionRecorder.
  New tags this session: `DISPATCH-LOOP-SHADOW-COMPARISON`,
  `STRIKER-IDENTIFY-FALLBACK-INVOKED`, `STRIKER-POST-WICKET-DERIVATION`,
  `ABSORBED-LEGAL-BOWLER-QUEUED`.

### 9.2 Tests and harness

- `files/tests/test_sm_derivation_ledger.py` (L1.5 gate)
- `files/tests/test_pipeline_captured_replay.py` (L2 gate)
- `files/tests/trace_session_assertions.py` (session-level invariants)
- `files/tests/symptom_class_assertions.py` (per-ball invariants —
  12 classes, mostly L2-integrated)
- `files/scripts/run_trace_session_assertions.py` (trace-session runner)
- `files/scripts/run_symptom_assertions.py` (per-ball runner)
- `files/tests/fixtures/dc_vs_kkr_2026_152064_ledger.json` (L2 fixture)
- `files/tests/fixtures/gt_vs_rr_2026_commentary_first_innings.md`
  (Cricbuzz commentary ground truth for validate_gtrr session)

### 9.3 Design memos (read in this order)

1. `files/docs/investigations/sm_as_orchestrator_design.md` — **main memo**.
   §7 candidate list, §7.1–§7.7 audit chain, §7.2 standing audit
   checklist (7 gates).
2. `files/docs/investigations/cold_start_initial_striker_design.md` — S5b-3
   design. §11 is the post-F1 revision documenting the F1 failure
   mechanism + fix.
3. `files/docs/investigations/multi_ball_gap_bowler_credit_design.md` — B-α
   audit. §5 shadow-comparison implementation bug + §A B-ζ falsification
   + recursive gate-6 lesson.
4. `files/docs/investigations/sm_wicket_dispatch_design.md` — B-β cascade
   closure audit. §5 F1 blast radius + §9 cross-fixture verification
   pattern.
5. `files/docs/investigations/dispatch_loop_redesign_scoping.md` —
   `SM_INLINE_MULTI_BALL` scaffold design + Design B inline multi-ball
   approach.

### 9.4 Captured data

- `files/logs/deliveries/validate_gtrr_20260520_180715/scout_raw.jsonl`
  (841 frames, GT vs RR first innings)
- `logs/trace/validate_gtrr_20260520_180715.jsonl` (489 trace records,
  pre-F1 session output — this is the baseline that produced the
  broken-but-known assertion baseline)
- Earlier captured dumps in `files/logs/deliveries/` and
  `logs/trace/` for cross-fixture work

---

## 10. Discipline lessons (do not forget)

1. **Every classification is a hypothesis.** Bug-class declarations,
   NOT-A-DEFECT verdicts, "already addressed" verdicts, fix-feasibility
   claims — all are hypotheses pending empirical verification. Gate 6
   applies recursively.

2. **Predicted flips must cite concrete frame numbers.** Qualitative
   code-path reasoning ("this branch doesn't fire post-cold-start")
   doesn't satisfy gate 6. The original S5b-3 Context A "already
   addressed" verdict was reached via qualitative reasoning and
   falsified one production session later.

3. **Cross-fixture verification before declaring a fix shipped.** Replay
   the captured Scout dump and re-run trace-session assertions. F1
   closed 4+ bug classes — without gate 7, the workstream would have
   spent capacity on operationally-redundant fix memos.

4. **Observability tooling is subject to the same empirical
   verification as production code.** F-α-shadow caught a false-positive
   pattern in my own snapshot code that masked the real B-α signal
   (frames 302/1325 were tooling false positives; frame 522 was the
   real bug).

5. **The §7 candidate-deletion list framing was the wrong starting
   question.** "Fix production bugs first; scar tissue evaluation
   second" is the empirically-validated reframe. Queue B,
   `_ScoutRetryBuffer`, broadcast_extra/extras_type, P1 striker
   matcher — all reclassified Keep or already-Done after empirical
   audit. Most of the original "Delete" candidates were either Keep
   (load-bearing not visible at first read) or cascade symptoms of
   other root causes.

6. **One-edit fixes can close multiple bug classes.** F1 demonstrated
   this at scale. The audit-driven discipline now has a documented
   track record of preventing engineering capacity from being spent on
   cascade symptoms.

7. **Pre-commit gates are non-negotiable.** Layer 1.5 (36/36) + Layer 2
   (30 balls) held on all 17 commits this session. If they fail,
   investigate the underlying issue. Never bypass with `--no-verify`
   unless user explicitly authorizes.

8. **No-speculative-fixes discipline.** If predicted flip claims aren't
   backed by empirical evidence, pause and re-audit. Do not ship.
   Multiple times this session: the audit caught my own hypotheses
   before they became commits.

---

## 11. Next agent's first move

1. Check `git log --oneline -20` to confirm branch state matches this
   handoff. Expected HEAD: `40b14c7`.
2. Check whether a fresh production trace exists in `logs/trace/` newer
   than `validate_gtrr_20260520_180715.jsonl`. If yes, the validation
   gate has fired — proceed to step 3. If no, the workstream is in
   operational pause; no engineering work unblocked.
3. If new trace exists: add its filename stem to `SESSION_CONTEXT` in
   `files/scripts/run_trace_session_assertions.py` with appropriate
   `expected_initial_striker` per ground truth (Cricbuzz commentary or
   the session's known opening pair). Run the script. Observe flips.
4. **Predicted flips:** epsilon → PASS (direct), beta → PASS (cascade),
   compound_tokens → PASS (cascade), alpha → significant reduction,
   extras_total → likely unchanged (UI render layer).
5. **Any unflipped assertions are the next concrete engineering
   targets.** Open a design memo for each unflipped one using the
   §7.2 7-gate checklist. Each fix should be:
   - Empirically grounded (concrete frame numbers from new trace)
   - Predicted flip cited in commit message
   - Cross-fixture verified post-commit (gate 7)
6. **Do NOT pursue F-α-rotation, additional Queue B extensions, or any
   speculative architectural work** unless empirical pressure exists.
   The discipline saves engineering capacity for fixes that data
   demands.

---

## 12. Quick reference — the meta-lesson

**F1 demonstrated that a one-edit fix can close multiple bug classes
the §7 list framed as separate workstreams.** The audit-driven
discipline now has a documented track record (Queue B Keep,
`_ScoutRetryBuffer` Keep, S5a NOT-A-DEFECT, S5b-2 deletion shipped,
B-ζ falsification, B-β cascade closure, F-α-shadow self-catch) of
preventing engineering capacity from being spent on cascade symptoms.

**Empirically validated discipline saves engineering work.** Apply
gate 6 recursively. Apply gate 7 after every fix. The workstream's
biggest architectural insight is the discipline itself, demonstrated
at scale.

Welcome to the branch. Read the discipline lessons (§10) before
touching anything. Layer 1.5 + Layer 2 gates protect you.
