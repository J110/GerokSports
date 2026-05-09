# `execute_innings_change` extraction design contract

Status: **SHIPPED** (2026-04-30) — module-level `_execute_innings_change_from_state`, replay harness, E2E regression + `files/f2660_f2900_transition_signature.txt`.

This contract defines extraction of `execute_innings_change` from the `run_test()` closure into a module-level function so Composer 2 can implement a comprehensive MI-vs-SRH F2660-F2900 transition regression without architectural improvisation.

---

## §1 Executive summary

- Scope: `execute_innings_change` was originally inside `run_test()` (~151 LOC); it is now a wrapper calling module-level `_execute_innings_change_from_state` (~170 LOC). Complexity vs `build_full_payload` extraction: materially smaller function body (151 vs 511 LOC), but higher transition-critical nonlocal writeback density because innings transition mutates 13 closure scalars and relies on two closure helpers (`assign_teams`, `reset_for_innings`) plus P0-C latch semantics.
- Complexity vs `build_full_payload` extraction: materially smaller function body (151 vs 511 LOC), but higher transition-critical nonlocal writeback density because innings transition mutates 13 closure scalars and relies on two closure helpers (`assign_teams`, `reset_for_innings`) plus P0-C latch semantics.
- Recommendation: same 3-commit shape as `build_full_payload` extraction, but with callback binders (instead of helper extraction) to avoid exploding scope.
- Predicted execution: ~220-320 LOC touched in `test_pipeline.py` + ~180-260 LOC in `test_recent_fixes.py`; 3 commits over ~3-4 hours including test stabilization.

---

## §2 Current implementation analysis

### 2.1 Location and call surface

- Definition: module-level `_execute_innings_change_from_state` in `files/test_pipeline.py` (~4504); thin closure wrapper `execute_innings_change` inside `run_test()` (~5434).
- Call sites in `run_test()`:
  - innings-break resolved path: `8718`
  - high-confidence `TO WIN N OFF M`: `9234`
  - target + innings-1-done fast-path: `9256`
  - toss-backed scorer-target path: `9270`
- Structural dependencies:
  - calls closure helper `assign_teams(...)` (`4839`)
  - calls closure helper `reset_for_innings(...)` (`5232`)
  - mutates closure booleans/counters that govern deferred transition flow.

### 2.2 Closure-captured variable inventory

#### a) STATE (pass-through required)

- object state reads/writes:
  - `scoreboard`
  - `score_mgr`
  - `ball_analyzer`
  - `frame_count`
  - `log`
- closure scalar state currently read and/or mutated:
  - `team_locked`
  - `_bowling_team_strip_count`
  - `pending_innings_2`
  - `pending_target`
  - `_inn2_consecutive`
  - `batting_team`
  - `bowling_team`
  - `_inn_break_pending`
  - `_inn_break_pending_frame`
  - `_inn_break_pending_source`
  - `_inn1_batting_team_latched`
  - `_inn1_bowling_team_latched`
  - `_inn1_completed_deterministic`

#### b) CONFIG (module-level constant candidates)

- No direct constant gates inside this function body that must be passed in.
- P0-C telemetry constants (`_POISON_RATE_WINDOW`, `_FRAME_POISONED_STRIP_TRUST_THRESHOLD`) are outside this function and can remain module-local to `run_test()`/adjacent logic.

#### c) HELPER (closure functions invoked from body)

- `assign_teams(new_bat, new_bowl, innings=2)` (closure with many captures).
- `reset_for_innings(2, overs_reset_source=source)` (closure with tracker reset side-effects).
- These should be injected as callables from wrapper, not extracted in this PR.

#### d) NONLOCAL write-back set

- Exact nonlocal writeback set declared in function:
  - `team_locked`
  - `_bowling_team_strip_count`
  - `pending_innings_2`
  - `pending_target`
  - `_inn2_consecutive`
  - `batting_team`
  - `bowling_team`
  - `_inn_break_pending`
  - `_inn_break_pending_frame`
  - `_inn_break_pending_source`
  - `_inn1_batting_team_latched`
  - `_inn1_bowling_team_latched`
  - `_inn1_completed_deterministic`

### 2.3 P0-C state interactions (must preserve)

- latch declarations in `run_test()`:
  - `_inn1_batting_team_latched`, `_inn1_bowling_team_latched`, `_inn1_completed_deterministic` at `4717-4719`
- deterministic latch set at innings-break edge:
  - `8599-8602`
- transition usage in `execute_innings_change`:
  - cold-start override via `and not _inn1_completed_deterministic` (`5312-5314`)
  - cricket-rules swap using latched teams (`5365-5374`)
- poison telemetry data path exists outside function:
  - `_poisoned_in_window` + `_FRAME_POISONED_STRIP_TRUST_THRESHOLD` at `4724-4725`, telemetry emit around `8889-8900`

---

## §3 Module-level signature design

### 3.1 Proposed function

```python
def _execute_innings_change_from_state(
    *,
    # trigger inputs
    source: str,
    target: int | None,

    # core objects (mutated in place)
    scoreboard,
    score_mgr,
    ball_analyzer,
    log,

    # snapshot values
    frame_count: int,

    # closure scalar state (rebind-on-return)
    team_locked: bool,
    bowling_team_strip_count: int,
    pending_innings_2: bool,
    pending_target: int | None,
    inn2_consecutive: int,
    batting_team: str | None,
    bowling_team: str | None,
    inn_break_pending: bool,
    inn_break_pending_frame: int,
    inn_break_pending_source: str | None,
    inn1_batting_team_latched: str | None,
    inn1_bowling_team_latched: str | None,
    inn1_completed_deterministic: bool,

    # closure helpers (binder callbacks)
    assign_teams_cb,         # callable(new_bat, new_bowl, innings=2)
    reset_for_innings_cb,    # callable(new_innings, overs_reset_source=...)
) -> dict:
    ...
```

### 3.2 Return type contract

Return a dict with:

- `did_change: bool`
- scalar rebinds:
  - `team_locked`
  - `bowling_team_strip_count`
  - `pending_innings_2`
  - `pending_target`
  - `inn2_consecutive`
  - `batting_team`
  - `bowling_team`
  - `inn_break_pending`
  - `inn_break_pending_frame`
  - `inn_break_pending_source`
  - `inn1_batting_team_latched`
  - `inn1_bowling_team_latched`
  - `inn1_completed_deterministic`

Objects (`scoreboard`, `score_mgr`, `ball_analyzer`) remain in-place mutation surfaces as today.

### 3.3 Parameter documentation intent

- Keep keyword-only args mandatory to prevent positional drift.
- Split mutable-object parameters from scalar-rebind parameters so reviewers can visually verify semantic preservation.
- Explicitly document that wrapper call snapshots values exactly as closure did at call-time.

---

## §4 Helper closure handling

- Do not extract `assign_teams` or `reset_for_innings` in this change.
- Use binder callback pattern (same principle as `build_full_payload` `record_state_recovery_guard` binder):
  - wrapper passes `assign_teams_cb=assign_teams`
  - wrapper passes `reset_for_innings_cb=reset_for_innings`
- This preserves rebind-by-name semantics and existing side-effect topology.
- If later full harness purity is needed, extract helpers in a separate PR; not required for F2660-F2900 replay unlock.

---

## §5 P0-C state preservation

### 5.1 `_inn1_bowling_team_latched`

- Must remain the primary source for innings-2 batting team in deterministic transition path.
- Extraction must not reorder: latch assignment (`8599-8602`) occurs before any call to extracted transition function in break-resolve path.

### 5.2 `_inn1_completed_deterministic`

- Must remain one-way boolean override of cold-start branch in extracted function:
  - `cold_start_inn2 = (...) and not inn1_completed_deterministic`
- Regression check: no alternate branch may bypass this gate.

### 5.3 `_poisoned_in_window` deque

- Not a function input to extracted transition; keep in outer loop telemetry path.
- Extraction must not move or couple this deque into decision branch logic.

### 5.4 `_FRAME_POISONED_STRIP_TRUST_THRESHOLD`

- Accessibility remains unchanged (outer-scope telemetry constant).
- Keep telemetry-only role; extracted transition function should not compare against threshold.

---

## §6 Wrapper transition

### 6.1 Wrapper shape (inside `run_test`)

- Keep a small closure wrapper named `execute_innings_change(...)` to preserve all existing call sites byte-identically.
- Wrapper responsibilities:
  1. snapshot current closure state
  2. call `_execute_innings_change_from_state(...)`
  3. rebind returned scalar state back to nonlocals
  4. return `did_change`

### 6.2 Call-site preservation

- Preserve existing call text at lines:
  - `8645`
  - `9161`
  - `9183`
  - `9197`
- No call-site argument edits.

### 6.3 Byte-identity verification

- Preserve behavioral byte identity by:
  - unchanged wrapper signature and source tags
  - unchanged logging tags and text fields in function body
  - snapshot sentinel test (see §7.4) comparing pre/post extraction transition trace over same synthetic fixture.

---

## §7 F2660-F2900 regression test design

### 7.1 Test name

`test_p0_fixes_e2e_mi_srh_f2660_f2900_innings_transition`

### 7.2 Structure

1. Build pre-F2660 state fixture:
   - innings 1 finalized or break-pending state equivalent
   - `batting_team="Mumbai Indians"`, `bowling_team="Sunrisers Hyderabad"`
   - overs tracker floor at `20.0` equivalent before reset
   - latch state primed from deterministic edge
2. Replay transition window script derived from log frame facts.
3. Drive extracted transition function via same source triggers observed in log.
4. Assert P0-A/B/C outcomes and final innings-2 integrity.

### 7.3 Per-fix assertions

- P0-A:
  - `[SM-INNINGS-2-RESET]` emitted with transition source.
- P0-B:
  - `[OVERS-TRACKER-RESET]` emitted and overs floor reset behavior observed (`20.0 -> 0.x` progression allowed).
- P0-C:
  - latched team swap honored (`_inn1_bowling_team_latched == "MI"` implies innings-2 batting = `SRH` in that match context).
  - no persistent `"MI 0/0"` state.
  - innings-2 active batters belong to SRH side.

### 7.4 Additional sentinel assertion

- Add a compact transition signature (ordered tuple list per frame: innings, batting_team, bowling_team, score, overs, wickets, target) over F2660-F2900 replay.
- Freeze as regression baseline for this window.

---

## §8 Migration shape

### Commit 1 — extract + wrapper (structural)

- Add `_execute_innings_change_from_state(...)` at module level.
- Replace closure body with wrapper/rebind.
- Keep helper callbacks injected, no helper extraction.
- Validation: existing `test_recent_fixes` suite unchanged.

### Commit 2 — replay harness utilities

- Add log-window parser helper for MI-SRH F2660-F2900 in `test_recent_fixes.py` (using existing local parsing patterns already present in repo).
- Add fixture constructor for pre-F2660 state.
- Validation: helper unit tests for parser and fixture integrity.

### Commit 3 — end-to-end regression test + sentinel

- Add `test_p0_fixes_e2e_mi_srh_f2660_f2900_innings_transition`.
- Add transition signature baseline assertion.
- Validation: all P0-A/B/C assertions + final state checks pass.

---

## §9 Risk assessment

### 9.1 Failure modes

- Unreturned scalar state causes wrapper drift (missed rebind variable).
- Subtle reference/value mismatch (bool/int scalars frozen).
- Accidental helper callback ordering change (`assign_teams` vs `score_mgr.set_innings_2` path).
- P0-C gate regression (`inn1_completed_deterministic` not honored).

### 9.2 Edge cases

- deterministic latch unavailable (`None` latch fallback path).
- `scoreboard.current_innings >= 2` idempotency early return.
- `target is None` path must remain valid.

### 9.3 Mitigations

- Explicit rebind list in wrapper and return schema checklist.
- direct string-presence assertions for critical tags/log tokens.
- replay test asserts source-tagged transitions and team identity continuity.
- keep refactor structural only; no logic edits.

### 9.4 Path A byte-identity preservation

- Maintain wrapper API + unchanged call sites + unchanged source tags.
- Sentinel transition signature guards behavioral equivalence in target window.

---

## §10 Comparison with `build_full_payload` extraction

- Same patterns to reuse:
  - keyword-only module-level function
  - closure wrapper that snapshots and forwards state
  - callback binder for closure-dependent helper semantics
  - staged 3-commit rollout with regression sentinel last
- Key differences:
  - `execute_innings_change` has fewer LOC but more direct nonlocal writeback.
  - no inner helper closures to split; only external closure helpers invoked.
  - greater correctness sensitivity around team attribution and innings boundaries.

---

## §11 Decision points to resolve

1. Fixture data sourcing:
   - **Recommended:** hybrid approach.
   - Parse real F2660-F2900 log lines to derive trigger script, but keep deterministic synthetic state objects for execution speed and hermeticity.
2. Helper extraction granularity:
   - **Recommended now:** callbacks only (`assign_teams`, `reset_for_innings` not extracted).
   - **Defer:** helper extraction to later if broader harness abstraction needed.
3. Test setup construction:
   - **Recommended:** explicit fixture builder function in `test_recent_fixes.py` with MI/SRH canonical names and latch flags set as in P0-C contract.

If these constraints prove infeasible in implementation (for example, replay script cannot deterministically derive trigger edges from available log data), fallback is a log-replay integration assertion that validates transition tags and final team identity without frame-by-frame synthetic mutation.

---

## §12 Composer 2 readiness

- This contract is implementation-ready per commit:
  - clear function signature + return schema
  - explicit wrapper rebinding obligations
  - exact test name and assertion categories
  - migration sequencing and validation steps
- Stop-and-route-back conditions:
  1. Any additional nonlocal discovered during extraction not listed in §2.2(d)
  2. Helper callback requires extra closure state not representable by current binder
  3. Transition signature deviates after structural extraction (indicates accidental logic drift)
- Dependencies:
  - none expected (structural refactor + tests only)
  - no package or environment changes required.

---

## §13 Implementation notes (2026-04-30)

- **Structural extraction:** `_execute_innings_change_from_state` in `files/test_pipeline.py` (keyword-only API, callback binders for `assign_teams` / `reset_for_innings`); `execute_innings_change` closure is a thin snapshot/rebind wrapper; four `run_test()` call sites unchanged per §6.
- **Log parser (`_parse_innings_transition_window`):** firing rows include an interior `bcast_target=None` substring before the authoritative trailing `target=N`. The matcher uses the **final** `target=(\d+|None)` on the line (`.*target=…$`) so `overs_complete_20` at F2695 resolves to `244`, not `None`.
- **Pre-transition fixture:** `Scoreboard._inn` is a read-only property; priming innings-1 score line uses `sb.innings[1][…]` in place of assigning `_inn`. **`ScoreManager` is intentionally not attached** to the scoreboard in this harness: production calls `scoreboard.set_innings_2` before `score_mgr.set_innings_2`, so when SM mirrors SB innings, `set_innings_2` early-returns and never emits `[SM-INNINGS-2-RESET]`. Detaching SM restores SM-local `_innings_fallback=1` so the E2E test can assert P0-A telemetry without changing shipped ordering.
- **Regression sentinel:** ordered tuple-per-step transcript in `files/f2660_f2900_transition_signature.txt`, produced by `_f2660_f2900_transition_signature_text` after replaying parsed triggers through `_execute_innings_change_from_state`.
- **Tests added:** `test_innings_transition_window_parser`, `test_pre_innings_2_transition_fixture_integrity`, `test_p0_fixes_e2e_mi_srh_f2660_f2900_innings_transition` in `files/test_recent_fixes.py`.
