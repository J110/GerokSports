# `build_full_payload` extraction design contract

**Status (2026-04-29):** DESIGN ONLY — no code changes in this task.
This document is the Composer-2-executable contract for extracting
`build_full_payload` from the `run_test()` closure into a module-
level `_build_full_payload_from_state` function. Mirrors the
structure of `dual_broadcaster_path_b_migration_contract.md`.

**Predecessors:**
- `dual_broadcaster_path_b_migration_contract.md` §12.5 — flagged the
  extraction as a prerequisite for the Path A snapshot regression
  test; deferred to follow-up.
- `striker_path_b_read_audit.md` — cross-references §12.5 as Lever 2
  for `[WS-SLOT-INVARIANT]` reduction.
- `get_broadcast_state_path_b_audit.md` — cross-references §12.5;
  Option A of that audit's cleanup PR depends on this extraction.

---

## 0. Locked context

- The function lives at `files/test_pipeline.py:4826–5337` (~511
  LOC) inside `async def run_test()` (the contract historically
  refers to this as `main_loop`; the actual symbol is `run_test`).
  This document uses **`run_test()`** as the canonical name.
- Four production call sites: L5347 (`broadcast_base`), L6266
  (`run_test`-internal), L7386 (`run_test`-internal),
  L9489 (`run_test`-internal). All four are inside `run_test()`.
- Out-of-scope: Path A WS-payload assembly correctness; Cluster 1
  `_project_active_batters`; Item 3 LOW-risk batch SM properties;
  Fix 5 collision guard; `SM.full_reset`; State Recovery aggregator
  internals.

---

## 1. Closure inventory

### 1.1 Methodology

Read every line of `build_full_payload` (4826–5337) and the helper
closures it transitively calls (`_canon_player_name`,
`_record_state_recovery_guard`, `_assert_payload_invariants`).
Categorize each captured name as **STATE** (must be passed),
**SHARED-MUTABLE** (mutable container; reference-passed),
**FUNCTION-CLOSURE** (helper closure that itself captures
`run_test()` state — must also be extracted or factored), or
**MODULE-GLOBAL** (already module-level, no action needed).

### 1.2 Closure-captured names (full inventory)

| Name | Kind | Mutable? | Category | Notes |
|---|---|---|---|---|
| `scoreboard` | `Scoreboard` | yes (mutated by pipeline) | **STATE** | Pass by reference; `_inn`, `batting_card`, `bowling_card`, `extras`, `fall_of_wickets`, `current_innings`, `_find_card_key`, `resolve_name` all read/used. |
| `score_mgr` | `ScoreManager` | yes | **STATE** | Read: `striker`, `non_striker`, `bowler_name`, `shadow`, `completed_over`, `completed_over_runs`, `frames_since_event`. |
| `over_mgr` | `ThisOverManager` | yes | **STATE** | Read: `get_display(overs)`, `over_history`. |
| `partnership_tracker` | `PartnershipTracker \| None` | yes | **STATE** | Optional; nullable in early frames. Read + `update()` + `current()`. |
| `cricket_field` | `CricketField` | yes | **STATE** | Read: `get_display_positions()`, `template_name`, `inside_count`, `outside_count`, `phase`, `confidence_label`. |
| `batting_team`, `bowling_team` | `str \| None` | yes (re-assigned) | **STATE** | Re-assigned at L4135 (toss-set), L5381 (cache-replay). For extracted form, pass by value at call site (Python re-binds; closure capture is by name, not value). See §3.3 closure-binding semantics. |
| `team_names` | `list[str]` | mostly stable after squad-scrape | **STATE** | Pass by reference (list). |
| `toss_winner_name` | `str \| None` | yes | **STATE** | Same re-assign concern as `batting_team`. |
| `toss_decision_str` | `str \| None` | yes | **STATE** | Same. |
| `_broadcast_cache` | `dict` | yes | **SHARED-MUTABLE** | Read: `.get("venue")`, `.get("match_info")`. Pass by reference. |
| `_last_delivery_info` | `dict \| None` | yes (re-assigned in scanner loop) | **STATE** | Re-assigned at L9151, L9480. Bind-by-name: see §3.3. |
| `frame_count` | `int` | yes (incremented per frame) | **STATE-VALUE** | Pass by value at call site (Python int is immutable; closure captures the **name**, so it sees the latest value at call time. After extraction we must pass the int value at the call site each frame.) |
| `last_broadcast_time` | `float` | yes (re-assigned by `broadcast_base`) | NOT USED | Captured by `broadcast_base` only, not `build_full_payload`. Skip. |
| `_canon_player_name` | function (closure over `scoreboard`) | no | **FUNCTION-CLOSURE** | Trivially extractable: factor to module-level `_canon_player_name(raw, *, scoreboard, bowler=False)`. |
| `_record_state_recovery_guard` | function (closure over `_state_recovery`, `frame_count`, `_state_recovery_frame_candidate`, `_state_recovery_current`, `_state_recovery_suppressed`, `score_mgr`, `scoreboard`) | no | **FUNCTION-CLOSURE** | Non-trivial; captures 7 closure names, four of which are mutable rebound-by-name (`frame_count`, `_state_recovery_frame_candidate`, `_state_recovery_current`, `_state_recovery_suppressed`). See §1.4. |
| `_assert_payload_invariants` | function (pure of `log` only) | no | **FUNCTION-CLOSURE** | Already pure-ish; trivially extractable to module level. NOT called inside `build_full_payload` body — verify before extracting. |
| `SESSION_ID` | str | no | **MODULE-GLOBAL** | Already module-level (L685). Reference unchanged. |
| `log` | logger | no | **MODULE-GLOBAL** | Module-level; unchanged. |
| `enforce_ws_slot_invariant`, `_project_active_batters`, `project_fow_for_payload`, `get_match_situation`, `overs_to_balls`, `_reconcile_bowler_overs` | functions | no | **MODULE-GLOBAL** | All already module-level. No action. |

**Captured-name count requiring explicit pass-through:** **13**
(`scoreboard`, `score_mgr`, `over_mgr`, `partnership_tracker`,
`cricket_field`, `batting_team`, `bowling_team`, `team_names`,
`toss_winner_name`, `toss_decision_str`, `_broadcast_cache`,
`_last_delivery_info`, `frame_count`).

Plus **1 helper closure** (`_record_state_recovery_guard`)
called from `build_full_payload` body via the WS-SCRUB and slot-
invariant branches (L4939, L4945) — must be addressed (§1.4).

### 1.3 Read-only vs. mutated by `build_full_payload`

`build_full_payload` reads from all 13 STATE names. It **mutates
in place** only:
- `state` dict (local to function — no closure leak)
- `_scrub_counts` dict via `setattr(build_full_payload, …)` (the
  function-attribute idiom, used as a per-frame counter; see
  §3.4 — must move to a module-level dict or a passed-in counter)
- `build_full_payload._last_gap_sig` (same idiom; §3.4)
- `build_full_payload._last_feeder_div_sig` (same idiom; §3.4)

It does **not** mutate any closure-captured name in place.
(The `_record_state_recovery_guard` call mutates `_state_recovery`
and `score_mgr` indirectly; that's the helper closure's
responsibility, not `build_full_payload`'s.)

### 1.4 Helper-closure dependency: `_record_state_recovery_guard`

**Body** (L4355–L4366) reads four mutably-rebound names from
`run_test()`:

```text
_record_state_recovery_guard:
    closure-reads: _state_recovery (object — stable),
                   frame_count (int — rebound per frame),
                   _state_recovery_frame_candidate (dict|None — rebound),
                   _state_recovery_current (dict|None — rebound),
                   _state_recovery_suppressed (bool — rebound),
                   score_mgr, scoreboard (object — stable)
    side effects: writes to _state_recovery; logs; mutates
                  score_mgr / scoreboard via
                  _apply_state_recovery_phase2_mutation.
```

The four rebound names are not directly visible to a module-level
extraction. **Extraction strategy (recommended):**

- Convert `_record_state_recovery_guard` to module-level with
  signature
  `_record_state_recovery_guard(family, proposed_reset, *,
  state_recovery, score_mgr, scoreboard, frame_count,
  frame_candidate, current, suppressed, log)`.
- Inside `run_test()`, define a tiny wrapper that supplies the
  per-frame values: `def _rsrg(family, proposed_reset=None):
  return _record_state_recovery_guard(family, proposed_reset,
  state_recovery=_state_recovery, score_mgr=score_mgr,
  scoreboard=scoreboard, frame_count=frame_count,
  frame_candidate=_state_recovery_frame_candidate,
  current=_state_recovery_current,
  suppressed=_state_recovery_suppressed, log=log)`.
- Pass `_rsrg` into `_build_full_payload_from_state` as the
  `record_state_recovery_guard=…` parameter.

This keeps the rebind-by-name semantics intact at the wrapper
boundary (the wrapper is itself a closure that re-reads the four
rebound names every call).

---

## 2. Module-level signature

### 2.1 `_build_full_payload_from_state` signature

```python
def _build_full_payload_from_state(
    *,
    # Core state
    scoreboard,                     # Scoreboard
    score_mgr,                      # ScoreManager
    over_mgr,                       # ThisOverManager
    partnership_tracker,            # PartnershipTracker | None
    cricket_field,                  # CricketField

    # Match metadata (snapshot at call time)
    team_names: list[str],
    batting_team: str | None,
    bowling_team: str | None,
    toss_winner_name: str | None,
    toss_decision_str: str | None,

    # Per-frame state (snapshot at call time)
    frame_count: int,
    last_delivery_info: dict | None,

    # Shared-mutable caches (reference-passed)
    broadcast_cache: dict,

    # Optional per-call override
    speed_kph: float | None = None,

    # Wired helpers (avoid re-importing log; keep call-site control)
    canon_player_name=None,         # callable(raw, *, bowler=False)
    record_state_recovery_guard=None,  # callable(family, proposed_reset)
    assert_payload_invariants=None, # callable(payload) | None
) -> dict:
    """Build the SINGLE canonical WS-broadcast payload.

    Extracted from `run_test()` closure 2026-04-NN. The wrapper at
    `run_test().build_full_payload` snapshots its closure state and
    forwards. Behaviour is byte-identical (Path A snapshot test in
    test_recent_fixes.py guarantees this).
    """
```

**Parameter classification:**

- **STATE objects** (5): `scoreboard`, `score_mgr`, `over_mgr`,
  `partnership_tracker`, `cricket_field`.
- **Snapshot-at-call** (5): `team_names`, `batting_team`,
  `bowling_team`, `toss_winner_name`, `toss_decision_str` —
  Python rebinds these inside `run_test()`; the extracted form
  must accept the latest value at call time, not bind-by-name.
- **Snapshot ints/dicts** (2): `frame_count`, `last_delivery_info`
  — same rebind concern.
- **Shared-mutable** (1): `broadcast_cache` — passed by reference.
- **Helpers** (3): `canon_player_name`,
  `record_state_recovery_guard`, `assert_payload_invariants`.
- **Per-call override** (1): `speed_kph`.

Total: **17 keyword-only parameters**. Keyword-only is mandatory
to prevent positional drift on future additions.

### 2.2 Return type

Unchanged: `dict`. Shape documented at L5123–L5337 (the existing
`return { "type": "state_update", ... }` literal).

The shape is implicitly the WS payload contract. The Path A
snapshot regression test (§4) freezes a baseline signature and
catches any field reordering or value change.

### 2.3 Side effects

`build_full_payload` today has these side effects:

1. **`log.info` / `log.warn`** — telemetry (`[WS-PROJECTION-FALLBACK]`,
   `[WS-SCRUB]`, `[WS-SLOT-INVARIANT]`, `[SM-FEEDER-DIVERGENCE]`,
   `[WS-PROJECTION-GAP]`, `[INVARIANT]`). Module-level `log` is
   imported at the top of `test_pipeline.py`; no change.
2. **`record_state_recovery_guard(...)`** at L4939, L4945. Wired
   via the helper parameter (§1.4).
3. **Function-attribute mutations** — `build_full_payload._ws_scrub_counts`,
   `build_full_payload._last_gap_sig`,
   `build_full_payload._last_feeder_div_sig`. **Three sites**
   that write to `build_full_payload.<attr>`. After extraction,
   these become attributes on `_build_full_payload_from_state`
   itself. Move them to module-level dicts keyed nothing
   (single-pipeline assumption already holds; tests reset). See
   §3.4 for the recommended migration.
4. **Mutates `state` in place** via `_project_active_batters`,
   bowler override, WS-SCRUB loop, `enforce_ws_slot_invariant` —
   all mutations are on the local `state` dict, which is then
   incorporated into the returned payload.

---

## 3. Wrapper transition

### 3.1 Target shape inside `run_test()`

```python
def build_full_payload(speed_kph=None):
    """Closure wrapper around _build_full_payload_from_state.

    Snapshots the seven rebind-by-name run_test() locals
    (batting_team, bowling_team, toss_*, frame_count,
    last_delivery_info) at call time so the extracted module-
    level function sees the current values."""
    return _build_full_payload_from_state(
        scoreboard=scoreboard,
        score_mgr=score_mgr,
        over_mgr=over_mgr,
        partnership_tracker=partnership_tracker,
        cricket_field=cricket_field,
        team_names=team_names,
        batting_team=batting_team,
        bowling_team=bowling_team,
        toss_winner_name=toss_winner_name,
        toss_decision_str=toss_decision_str,
        frame_count=frame_count,
        last_delivery_info=_last_delivery_info,
        broadcast_cache=_broadcast_cache,
        speed_kph=speed_kph,
        canon_player_name=_canon_player_name,
        record_state_recovery_guard=_record_state_recovery_guard,
        assert_payload_invariants=_assert_payload_invariants,
    )
```

The wrapper is **~17 lines**. Existing call sites
(L5347, L6266, L7386, L9489) keep `build_full_payload(speed_kph=…)`
unchanged — **zero call-site changes**.

### 3.2 `_canon_player_name` extraction

```python
# module-level
def _canon_player_name(raw, *, scoreboard, bowler: bool = False):
    if not raw:
        return raw
    try:
        resolved = scoreboard.resolve_name(raw)
        if not resolved:
            return raw
        card = (scoreboard.bowling_card if bowler
                else scoreboard.batting_card)
        if not card:
            return raw
        key = scoreboard._find_card_key(resolved, card)
        return key or raw
    except Exception:
        return raw
```

Inside `run_test()`, replace the existing closure with a tiny
binder so existing in-`run_test` callers keep their old signature:

```python
def _canon_player_name(raw, *, bowler=False):
    return scoreboard_canon_player_name(raw, scoreboard=scoreboard,
                                         bowler=bowler)
```

(Or rename one of them to avoid the shadowing; the contract uses
`_canon_player_name_extracted` as the module-level symbol and
keeps the closure form named `_canon_player_name` for back-compat
inside `run_test()`. Composer 2's call: pick one; document.)

### 3.3 Bind-by-name vs. snapshot semantics — the subtle bug class

Python closures capture **names**, not values. The closure form
of `build_full_payload` re-reads `frame_count`, `batting_team`,
`bowling_team`, `toss_winner_name`, `toss_decision_str`,
`_last_delivery_info` on every call — picking up whatever value
they currently hold in `run_test()`'s scope.

The extracted form passes those values **at call time**, in the
wrapper. This is **semantically equivalent** for the per-call
read pattern: each call to `build_full_payload(...)` performs the
read at the point of call, then forwards the snapshotted value.
There is no async-aware re-read between wrapper entry and
`_build_full_payload_from_state` body — these are synchronous
plain function calls.

**Risk:** if any code path inside `_build_full_payload_from_state`
depends on the value mutating *during* the function's execution
(e.g., a callback that updates `frame_count` mid-build), the
extraction would freeze the value. **Audit confirms no such path
exists** — `build_full_payload` is synchronous, single-threaded,
and does not invoke pipeline-stage callbacks that would mutate
`run_test()` state.

### 3.4 Function-attribute idiom migration

Three sites use the `setattr(build_full_payload, "_attr", val)`
idiom for cross-frame state:

| Attribute | Purpose | Migration |
|---|---|---|
| `_ws_scrub_counts` (L4895) | dict counting WS-SCRUB events by `slot:reason` | Move to module-level: `_ws_scrub_counts: dict[str, int] = {}`. Reset in tests via `_ws_scrub_counts.clear()`. |
| `_last_gap_sig` (L5014, L5041, L5048) | rate-limit signature for `[WS-PROJECTION-GAP]` | Move to module-level mutable container: `_ws_projection_gap_state: dict = {"last_sig": None}`. |
| `_last_feeder_div_sig` (L4958, L4972, L4974) | rate-limit signature for `[SM-FEEDER-DIVERGENCE]` | Same: `_sm_feeder_divergence_state: dict = {"last_sig": None}`. |

These containers are module-level dicts — the single-pipeline
assumption already in force (`run_test()` is the only caller; one
match per process). Tests that rely on rate-limit reset call
`_ws_projection_gap_state["last_sig"] = None` or `_ws_scrub_counts.clear()`.

---

## 4. Path A regression test integration

### 4.1 Test fixture (per §12.5.3 of the migration contract)

The fixture is **already specified** in `dual_broadcaster_path_b_migration_contract.md`
§12.5.3 (lines ~602–636 of that document). It constructs:
`Scoreboard` + `ScoreManager` + minimal `ThisOverManager` +
`PartnershipTracker` + `CricketField`, drives a deterministic
sequence of `update_batter` / `update_bowler` / `_apply_event`
calls, and snapshots the payload.

### 4.2 Test entry point (now unblocked)

```python
def test_path_b_low_risk_batch_path_a_regression_signature_match():
    header("Item 3 LOW-risk batch: Path A WS-payload signature unchanged")
    sb, sm = _path_b_regression_fixture()  # per §12.5.3
    over_mgr = ThisOverManager()
    pt = PartnershipTracker()
    cf = CricketField()
    payload = _build_full_payload_from_state(
        scoreboard=sb, score_mgr=sm,
        over_mgr=over_mgr, partnership_tracker=pt,
        cricket_field=cf,
        team_names=["TeamA", "TeamB"],
        batting_team="TeamA", bowling_team="TeamB",
        toss_winner_name="TeamA", toss_decision_str="bat",
        frame_count=42,
        last_delivery_info=None,
        broadcast_cache={"venue": "Wankhede"},
        speed_kph=None,
        canon_player_name=lambda raw, *, bowler=False: raw,
        record_state_recovery_guard=lambda *a, **k: None,
        assert_payload_invariants=None,
    )
    sig = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    check("WS payload signature matches pre-migration baseline",
          sig == _PATH_B_REGRESSION_BASELINE_SIGNATURE,
          f"len(sig)={len(sig)} expected_len={len(_PATH_B_REGRESSION_BASELINE_SIGNATURE)}")
```

### 4.3 Baseline capture (one-time, pre-PR)

Per §12.5.4: before extraction lands, run a tiny harness that
mounts `build_full_payload` from inside `run_test()` (e.g., add a
temporary module-level alias `_capture_build_full_payload =
build_full_payload` inside `run_test()` and read it via a test
hook), call it against the fixture, and capture
`json.dumps(payload, sort_keys=True, separators=(",", ":"))`.
Paste into the test as `_PATH_B_REGRESSION_BASELINE_SIGNATURE = "..."`.

**Alternative (simpler):** capture the baseline *immediately
after* extraction in the same PR: the extraction is a pure
refactor, so the post-extraction signature IS the baseline. The
regression test then guards future PRs, not the extraction PR
itself. **Recommended.** Capture-step: run the test once, copy
the failing-actual signature into the constant, re-run.

### 4.4 Test fixture location

`files/test_recent_fixes.py` — the fixture helper
(`_path_b_regression_fixture`) goes near other Path-B-related
fixtures (search for `_path_b_` prefix). The test itself goes
in the analyzer/path-B test cluster.

---

## 5. WS-PROJECTION-GAP integration

### 5.1 Does extraction close the WS-PROJECTION-GAP?

**No.** Extraction alone is a pure refactor — byte-identical
output. The `[WS-PROJECTION-GAP]` telemetry continues to fire at
the same rate.

### 5.2 What extraction unlocks

After extraction, `_build_full_payload_from_state` is **directly
unit-testable**:

- Write tests that construct a fixture where SM has
  `striker = None` but `_inn["striker"]` holds a still-batting
  name. Assert payload `striker` is filled by
  `_project_active_batters` fallback.
- Write tests that construct the inverse: SM has a name but the
  fallback is rejected by `_other_slot` collision guard.
- Write tests for `[WS-PROJECTION-GAP]` rate-limit signature
  toggling.

These tests give us **precision tooling** to identify the actual
[WS-SLOT-INVARIANT] driver. Hypotheses currently unverifiable
without extraction:

- **H1 (SM rotation atomicity)** — `score_mgr.striker ==
  score_mgr.non_striker` for a frame window mid-rotation. With
  extraction we can write `assert
  not (sm.striker and sm.non_striker and sm.striker == sm.non_striker)`
  as a pre-call invariant test against fixtured SM-rotation
  sequences.
- **H2 (canon collision)** — two different raw scout names
  canonicalising to the same squad key. Test by fixturing a
  squad with two players whose surnames collide.
- **H3 (`_other_slot` guard miss)** — `_project_active_batters`
  fallback fires for both slots simultaneously when SM is fully
  null. Already covered by Cluster 1 tests; extraction lets us
  confirm under more fixtures.

### 5.3 Cleanup PR enablement

Per `get_broadcast_state_path_b_audit.md` §6.4: Option A of that
PR requires a regression test that shadow-mode WS payload also
flows through `_project_active_batters`. **That test requires
this extraction.** Without extraction, shadow-mode behaviour is
buried inside the closure and cannot be exercised by a unit test.

### 5.4 Predicted `[WS-SLOT-INVARIANT]` rate reduction

**From extraction alone: 0%.** From extraction + downstream
unblocked work:

- Path A snapshot regression test: 0% (regression catcher only).
- Cleanup PR Option A: 0% (per `get_broadcast_state_path_b_audit.md` §7).
- SM rotation atomicity fix (Lever 1): unknown — *the extraction
  lets us measure it*, then design a fix. Plausible upper bound
  from striker audit: significant fraction of the 387 + 26 fires.

The honest framing: **extraction is enabling infrastructure, not
a fix**. Its value is *measurement precision* for Lever 1.

---

## 6. Risk assessment

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| Bind-by-name regression (frozen value mid-call) | HIGH | LOW | §3.3 audit confirmed no path requires re-read mid-call. Path A snapshot test catches any value drift. |
| Function-attribute migration drops state mid-pipeline | MEDIUM | LOW | §3.4 migration moves all three to module-level dicts; tests reset. Worst case: rate-limit signature resets to `None` once on PR deploy → one extra log line. Acceptable. |
| `_record_state_recovery_guard` wrapper miss | HIGH | MEDIUM | §1.4 wrapper preserves rebind semantics. Add a unit test that drives the wrapper across a fake frame-counter increment and asserts the inner module-level helper receives the latest value. |
| Closure helpers (`_canon_player_name`, `_record_state_recovery_guard`) extracted but in-`run_test()` callers (other than `build_full_payload`) break | MEDIUM | MEDIUM | Search for all in-`run_test()` callers of these two helpers; if any caller passes them with different argument shapes, leave a binder closure in `run_test()` so the call sites don't change. |
| Path A WS-payload assembly disturbed | CRITICAL | LOW | Path A snapshot regression test (§4) catches byte-level changes. The extraction is mechanical (move the function body verbatim, change `name` references to parameter names). No logic changes. |
| Test count regression | LOW | LOW | Add 2 tests (snapshot regression + wrapper-rebind sanity); expected count delta +2. |
| Performance regression from keyword-only call overhead | NEGLIGIBLE | NONE | One call per WS broadcast (~1 Hz). 17 keyword args is microseconds. |
| Reviewer-unfriendly diff (511 LOC moved + 17 new params) | MEDIUM | HIGH | Recommend §7 incremental approach: extract helpers first, then top-level. Each commit reviewable independently. |
| Extraction reveals an undocumented closure-capture | HIGH | LOW | §1.2 inventory was built from line-by-line read of body + helper closures. Composer 2 verifies on extraction by adding `nonlocal`-equivalent linting (e.g., temporarily prefix all body name reads with a sentinel and grep — out of scope for this contract; reviewer call). |

**Overall risk:** **MEDIUM-LOW**. The extraction is mechanical;
the closure inventory is well-bounded; the snapshot regression
test catches byte-level deviations. The biggest single risk is
the `_record_state_recovery_guard` rebind semantics, which is
fully addressed by §1.4's wrapper pattern.

### Rollback

Revert the extraction commit. The wrapper restores. No data-loss
or state-corruption surface area (the function is read-only on
its inputs).

---

## 7. Migration approach

### 7.1 Recommended: **incremental, three-commit sequence**

Rationale: 511 LOC moved in a single diff is reviewer-unfriendly
and hides bind-by-name regressions. Splitting into three commits
keeps each diff under ~200 LOC and lets the snapshot regression
test land before the highest-risk change.

#### Commit 1 — Extract pure helpers + add baseline capture

- Extract `_canon_player_name` to module-level
  `_canon_player_name(raw, *, scoreboard, bowler=False)`.
- Extract `_assert_payload_invariants` to module-level
  `_assert_payload_invariants(payload, *, log)` (pure of `log`).
- Convert `_record_state_recovery_guard` to module-level + keep a
  binder closure in `run_test()` (§1.4).
- Migrate function-attribute idiom to module-level dicts (§3.4).
- Add `_path_b_regression_fixture` to `test_recent_fixes.py`.
- Add a temporary helper that captures the current
  `build_full_payload` signature and pastes it as
  `_PATH_B_REGRESSION_BASELINE_SIGNATURE`.
- Validation: `just test` (expect existing count + 1 PASS).

**Diff size:** ~150 LOC. Reviewer-friendly.

#### Commit 2 — Extract `_build_full_payload_from_state` + wrap

- Move the body of `build_full_payload` (4826–5337) to module-
  level `_build_full_payload_from_state(...)` with the §2.1
  signature.
- Replace the closure body with the §3.1 wrapper.
- Rename inner reads of closure names to parameter names
  (mechanical sed-like changes; `scoreboard` → `scoreboard`
  trivially since the parameter has the same name; the only
  actual rename is `_last_delivery_info` → `last_delivery_info`).
- Validation: `just test` — Path A snapshot regression test
  must pass. **If it fails, the diff broke Path A**: bisect by
  function section.

**Diff size:** ~520 LOC (bulk move + wrapper). Reviewable as a
"move + parameterize" diff (most reviewers can scan move-only).

#### Commit 3 — Add Path A snapshot regression test (sentinel)

- Add `test_path_b_low_risk_batch_path_a_regression_signature_match`
  per §4.2.
- Write the baseline-signature constant (post-Commit-2 capture).
- Add wrapper-rebind sanity test (`test_build_full_payload_wrapper_rebinds_frame_count`).
- Validation: `just test` (expect +2 PASS).

**Diff size:** ~50 LOC. Reviewer-friendly.

### 7.2 Alternative: all-at-once

Single commit: do everything in §7.1's three commits at once.
Pros: one PR, one review cycle. Cons: 750 LOC diff, no
intermediate validation. **Not recommended** unless reviewer
explicitly prefers single-PR review.

---

## 8. Decision points (resolved)

| Question | Resolution |
|---|---|
| Preserve `build_full_payload` as wrapper, or fully replace? | **Wrapper.** Existing call sites at L5347 / L6266 / L7386 / L9489 are all inside `run_test()` and use the closure form; preserving the wrapper avoids touching those four lines and keeps the closure-side ergonomic. The wrapper is ~17 lines and self-documenting. |
| Logger references in extracted form? | **Module-level `log` import already exists** in `test_pipeline.py`; the extracted function references the same module-level `log` directly. No parameter needed. |
| Effect on existing tests beyond Path A snapshot? | **None.** The closure-form `build_full_payload` is referenced only inside `run_test()`; no external test imports it. Wrapper preserves the closure-side API. Module-level dicts in §3.4 may need test-side `.clear()` calls if a future test asserts on rate-limit state — none today. |
| Backwards compatibility guarantees? | **In-tree only.** No out-of-tree callers exist (the function is `def build_full_payload` inside `async def run_test`, not part of the package surface). Public surface unchanged. |
| `[WS-SLOT-INVARIANT]` reduction expected from extraction alone? | **Zero (honest framing).** Extraction is enabling infrastructure for Lever 1 measurement (SM rotation atomicity) and for the cleanup PR Option A (`get_broadcast_state_path_b_audit.md` §6). Genuine rate reduction requires those follow-ups. |
| Path A WS payload assembly preserved? | **Yes — guaranteed by snapshot regression test.** The extraction is mechanical (body move + parameterize); no projection-logic edits. |
| Extraction INFEASIBLE? | **No.** All 13 STATE captures + 1 helper closure are mechanically extractable per the §1 / §2 / §3 contracts. The biggest hairy case (`_record_state_recovery_guard` rebind semantics) has a clean wrapper pattern in §1.4. |

---

## 9. Files

| File | Change | Size |
|---|---|---|
| `files/test_pipeline.py` | Extract `build_full_payload` to module-level `_build_full_payload_from_state`; extract `_canon_player_name`, `_assert_payload_invariants`, `_record_state_recovery_guard` to module-level with binder closures in `run_test()`; convert function-attribute idiom to module-level dicts; replace `build_full_payload` body with wrapper. | ~750 LOC moved/added |
| `files/test_recent_fixes.py` | Add `_path_b_regression_fixture` helper + snapshot regression test + wrapper-rebind sanity test. | ~80 LOC |
| `files/docs/backlog.md` | Cross-reference this contract; mark §12.5 deferral resolved. | docs only |

No analyzer change. No telemetry tag changes. No `score_manager.py`
changes. No `eyes/scoreboard.py` changes.

---

## 10. Cross-references

- **`files/docs/investigations/dual_broadcaster_path_b_migration_contract.md`**
  §12.5 — original deferral and snapshot-test specification.
- **`files/docs/investigations/striker_path_b_read_audit.md`** — §3
  Lever 2 framing; §8 attribution of rate-reduction levers.
- **`files/docs/investigations/get_broadcast_state_path_b_audit.md`**
  §6.4 — Option A of cleanup PR depends on this extraction.
- **`files/docs/investigations/scorer_invariants_categorization.md`**
  §10.1 — Item 2 PR 1 backstop fires inside `apply_scorer_decision`,
  not `build_full_payload`; unaffected by this extraction.

---

## 11. Estimated execution

- **Commit 1** (helpers + fixture): ~75 min.
- **Commit 2** (extract + wrap): ~120 min including validation
  bisect contingency.
- **Commit 3** (snapshot test + sanity test): ~30 min.
- **Total:** ~3.5–4 h Composer-2 execution. Matches §12.5's
  "30–45 min" deferral estimate inflated by the helper-extraction
  scope creep (originally counted as zero).
