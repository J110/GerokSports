# `get_broadcast_state` Path B audit & migration contract

**Status (2026-04-29):** AUDIT ONLY — no migrations, no production code
edits in this task. The migration shape is documented as a Composer-2-
ready contract in §6 / §7.

**Predecessor:** `striker_path_b_read_audit.md` — concluded that the
two levers for `[WS-SLOT-INVARIANT]` reduction are (1) SM rotation
atomicity and (2) `get_broadcast_state` ↔ `_project_active_batters`
collapse. This document audits **Lever 2**.

---

## 0. Architecture context (locked)

- `[WS-SLOT-INVARIANT]` fires originate inside `enforce_ws_slot_invariant`
  in `test_pipeline.py:2230`, called from `build_full_payload` after
  the SM cutover writes.
- The WS payload’s **active-batter projection** flows through three
  phases inside `build_full_payload` (`test_pipeline.py:4826`):
  1. `state = scoreboard.get_broadcast_state()` — legacy projection
     plus Scoreboard-local active-list scrub.
  2. `_project_active_batters(state, score_mgr, scoreboard, …)` —
     SM-first cutover; overwrites `state["striker"]` / `["non_striker"]`
     when the live SM is non-shadow (`if state and not score_mgr.shadow`).
  3. WS-SCRUB loop + `enforce_ws_slot_invariant` — admission and
     duplicate-collision protection.
- Phase **2** is the canonical projection introduced by Cluster 1
  (Fix 7 / WS-PROJECTION-GAP). Phase **1** therefore acts as a
  parallel, pre-Cluster-1 projection whose output is *immediately
  overwritten on the live path*. The audit confirms this overlap is
  architectural debt rather than a `[WS-SLOT-INVARIANT]` driver
  (see §3 and §8).
- Out-of-scope: Path A WS-payload assembly; `_project_active_batters`
  itself; Cluster 1 already-shipped helpers; Item 3 LOW-risk batch;
  `SM.full_reset`; State Recovery aggregator.

---

## 1. `get_broadcast_state` implementation

**File:** `files/eyes/scoreboard.py:3570–3579`.

```3570:3579:files/eyes/scoreboard.py
    def get_broadcast_state(self) -> dict:
        """State for WS broadcast — validates striker/non-striker."""
        state = self.get_live_state()
        active = [k for k, v in self.batting_card.items()
                  if v.get("status") == "batting"]
        if state.get("striker") and state["striker"] not in active:
            state["striker"] = active[0] if active else None
        if state.get("non_striker") and state["non_striker"] not in active:
            state["non_striker"] = active[1] if len(active) > 1 else None
        return state
```

### 1.1 What it returns

`get_broadcast_state` returns the full `get_live_state()` dict
(see §2.1 below) with **two extra mutations** applied to the
`striker` / `non_striker` slots:

1. If `state["striker"]` is set **and** the named player is **not**
   currently `status == "batting"` in `batting_card`, replace it
   with `active[0]` (the first batting-status name, by insertion
   order on the dict).
2. Same rule for `non_striker` → `active[1]` (second batting-status
   name; **None** when only one or zero batters are batting).

Note: this is a **silent in-place rewrite**. There is no telemetry,
no `[WS-...]` tag, no log. If both slots are stale and `active` has
length 1, `non_striker` is silently set to `None` (loss-of-information
event with no observability).

### 1.2 Caller(s)

```text
rg "get_broadcast_state" files/ --type py
files/test_pipeline.py:4828:        state = scoreboard.get_broadcast_state() if scoreboard._inn else {}
files/eyes/scoreboard.py:3570:    def get_broadcast_state(self) -> dict:
```

There is exactly **one production caller**: `build_full_payload`
in `test_pipeline.py:4828`. No tests, no `eyes/main.py` consumer,
no `parity_monitor.py` reference (parity reads the post-WS payload
via the broadcast feed, not `get_broadcast_state` directly), no
external API import. The function is effectively *internal to the
WS broadcast pipeline*, despite living on the public `Scoreboard`
class.

### 1.3 Why a separate function? (historical context, still valid?)

Before Cluster 1 (Fix 7, 2026-04-26), there was no SM-first
projection inside `build_full_payload`. The WS payload was assembled
directly from `get_broadcast_state`'s output, and the active-list
scrub was the **only** WS-side defense against `_inn` holding a
dismissed name. After Cluster 1, `_project_active_batters` runs on
every non-shadow frame and **overwrites** `state["striker"]` /
`state["non_striker"]` with `canon(score_mgr.striker)` /
`canon(score_mgr.non_striker)` — the legacy active-list rebuild
inside `get_broadcast_state` therefore has no live-path effect on
the slot values that ship.

The historical separation rationale is **stale**. Today the
function exists for exactly two reasons:

- **Shadow mode (`score_mgr.shadow=True`)** — `_project_active_batters`
  is gated behind `if state and not score_mgr.shadow` at L4837. In
  shadow mode the WS payload would broadcast whatever `state[slot]`
  contains coming out of `get_broadcast_state`. Production runs with
  `shadow=False` (`test_pipeline.py:4521`); shadow mode is a
  developer-only / test path.
- **Defensive scrub** — the active-list rebuild guards against
  a hypothetical regression in `_project_active_batters` writing a
  not-currently-batting name. The downstream WS-SCRUB loop
  (`test_pipeline.py:4914–4942`) **already provides this defense**
  with explicit telemetry (`[WS-SCRUB] {slot}=...`), so the
  Scoreboard-side rebuild is duplicative on the live path.

---

## 2. `_project_active_batters` and the WS-SLOT pipeline

**File:** `files/test_pipeline.py:2164–2227`.

### 2.1 What it returns

Mutates `state` in place; returns a list of `(slot, _inn_value)`
fallback events for telemetry. Pseudocode:

```text
state["striker"]     := canon_fn(score_mgr.striker)
state["non_striker"] := canon_fn(score_mgr.non_striker)

for slot in ("striker", "non_striker"):
    if state[slot] is set: continue        # SM-first wins
    sb_val = scoreboard._inn.get(slot)
    if not sb_val: continue
    card = batting_card.get(resolve_name(sb_val))
    if card.status != "batting": continue
    if sb_val == state[other_slot]: continue   # collision guard
    state[slot] = canon_fn(sb_val)
    events.append((slot, sb_val))
```

**Key contracts (locked by Cluster 1 tests):**

- **SM-first.** SM provides the value; `_inn` is fallback only when
  the SM slot is `None`.
- **Active-batting gate.** Fallback only fires when the `_inn`
  value is currently a `status="batting"` card (defends against
  dismissed-leak).
- **Self-collision guard.** Fallback skips if the value would equal
  the other slot.
- **Canonicalization** on every write (raw scout names → squad keys).

Telemetry: `[WS-PROJECTION-FALLBACK]` per fallback event in
`build_full_payload` (`test_pipeline.py:4866–4869`).

### 2.2 The three-phase pipeline (summary)

| Phase | Function (file:line) | Source of slot | Telemetry on rewrite |
|---|---|---|---|
| **P1** | `Scoreboard.get_broadcast_state` (`eyes/scoreboard.py:3570`) | `_inn["striker"]` / `_inn["non_striker"]` (via `get_live_state`) | **none** (silent rebuild from `active`) |
| **P2 (live only)** | `_project_active_batters` (`test_pipeline.py:2164`) | `score_mgr.striker` / `score_mgr.non_striker`; fallback to `_inn` if SM null | `[WS-PROJECTION-FALLBACK]` |
| **P3 (live only)** | WS-SCRUB loop + `enforce_ws_slot_invariant` (`test_pipeline.py:4914`, `2230`) | active-list of `batting_card[name].status == "batting"` | `[WS-SCRUB]`, `[WS-SLOT-INVARIANT]` |

---

## 3. Field-by-field divergence between P1 and P2

### 3.1 Slot fields

| Field | P1 (`get_broadcast_state`) | P2 (`_project_active_batters`) | Divergence on live path? |
|---|---|---|---|
| `striker` | `_inn["striker"]`; if not in active → `active[0] or None`; **no canonicalization** | `canon(sm.striker)`; fallback canon(`_inn["striker"]`) iff in active and not = other slot | **P2 always wins** on non-shadow. P1 output is overwritten. |
| `non_striker` | `_inn["non_striker"]`; if not in active → `active[1] or None`; **no canonicalization** | `canon(sm.non_striker)`; fallback canon(`_inn["non_striker"]`) iff in active and not = striker | Same — P2 overwrites. |
| `current_bowler` | `_inn["current_bowler"]` (no rewrite) | `canon(sm.bowler_name)` written outside the helper at L4863–L4865 | P2 (via L4863–L4865) overrides on live path. |

### 3.2 All other live-state fields (unchanged by P1/P2)

These flow through P1 unchanged and are not touched by P2 or
WS-SCRUB:

- `score`, `wickets`, `overs`, `run_rate`, `target`
- `batting_team`, `bowling_team`
- `active_batters` (dict from `batting_card`)
- `innings`
- `match_complete`, `match_end_reason`, `match_result`

P2 has **no equivalent** for any of these. They are *required* for
the WS payload (Path A consumers + `parity_monitor` correlation
keys).

### 3.3 Edge cases

| Case | P1 behaviour | P2 behaviour | Effect on shipped payload |
|---|---|---|---|
| Both `_inn` slots = dismissed names | both rewritten to `active[0]` / `active[1]` | overwritten by SM (which after a witnessed wicket is `None`); fallback skipped because dismissed names fail active-status gate | identical (both produce `None` slots which downstream WS-SCRUB then re-seeds) |
| `_inn["striker"] == _inn["non_striker"]` (collision; rare — Fix 5 prevents) | first slot rewritten, second slot rewritten — but rewrite uses positional `active[0]` / `active[1]` so collision can re-form if active has only one batting name | overwritten by SM; fallback collision-guarded by `_other_slot` check | P2 strictly safer in collision case. |
| `score_mgr.shadow == True` | active-list rebuild is the only protection | **P2 does not run** (gated) | **P1 is load-bearing** in shadow only. |
| `score_mgr.striker is None` (post-wicket gap) | `_inn["striker"]` wins (possibly dismissed) → rewritten to `active[0]` if not in active | falls back to `_inn["striker"]` only when in active; else `None` | P2 strictly safer (no dismissed-leak risk via positional). |
| `len(active) == 0` (e.g., between innings) | both slots `None` | both slots `None` (SM also None or stale) | identical |
| `len(active) == 1` (mid-rotation) | striker → that name; non_striker → `None` (silently) | striker = `canon(sm.striker)` or `None`; non_striker likely `None` | comparable; P2 does not silently force a name. |
| Raw scout name in `_inn` (`"N RANA"` not yet resolved to `"Nitish Rana"`) | rebuild uses raw key; comparison `state["striker"] not in active` will be True since `active` holds canonical names | `canon_fn` resolves to canonical name | P2 fixes the rare canon-mismatch path (P1 then either rewrites to `active[0]` or — if `active[0]` is the same canonical — to the raw key, leaking an inconsistent name briefly) |

**No correctness regression** is introduced by removing P1 from the
live path. The only place P1 is load-bearing is **shadow mode**
(developer/test). P1 has *no* divergence-source role under the
live `[WS-SLOT-INVARIANT]` data we’ve been seeing.

---

## 4. Per-caller analysis of `get_broadcast_state`

The call graph is trivial:

```text
build_full_payload  (test_pipeline.py:4826)
  └── scoreboard.get_broadcast_state()      [P1]
  └── _project_active_batters(...)           [P2 — overrides P1 slots]
  └── WS-SCRUB loop                          [P3]
  └── enforce_ws_slot_invariant(...)         [P3]
  └── ... rest of payload assembly
broadcast_state(payload)                     [WS emit]
```

### Caller risk matrix

| Caller | Live behaviour after migration | Shadow behaviour after migration | Risk |
|---|---|---|---|
| `build_full_payload` (live, `shadow=False`) | identical (P2 always overwrites P1's slot rewrites today) | n/a | **LOW** |
| `build_full_payload` (shadow, `shadow=True`) | n/a | **regression risk** if the migration removes P1's silent rebuild without restoring an equivalent | **MEDIUM** in shadow only — addressed by §6 contract |
| `eyes/main.py:556` (`get_summary` log) | unaffected — does not call `get_broadcast_state` | unaffected | n/a |
| `parity_monitor.py` | unaffected — reads the WS payload, not `get_broadcast_state` | unaffected | n/a |

### `parity_monitor` cross-reference

`parity_monitor.py` at L73–74 reads `striker` / `non_striker` from
the **WS payload** (`ws` arg) — i.e., the post-P3 dict that was
broadcast. It also reads from a separate Cricbuzz-derived `cb`
dict for comparison. It does **not** call `get_broadcast_state`
itself. Migration is invisible to parity monitoring, by design.

---

## 5. Migration shape

### 5.1 Categorization

The shape is **PARTIAL-DELEGATION (cleanup-style)**. Justification:

- `get_broadcast_state` does **two** things: (a) returns `get_live_state()`
  unchanged (16 fields used by `build_full_payload` + downstream); and
  (b) rewrites `striker` / `non_striker`. Only (b) overlaps with
  `_project_active_batters`.
- A pure DIRECT-SUBSTITUTION (delete `get_broadcast_state`, have the
  caller use `get_live_state` directly) is **functionally correct on
  the live path** because P2 already overrides P1's slot rewrites.
  It is **not** correct in shadow mode, where P1 is the only defense.
- A WRAPPER (Scoreboard internalising `_project_active_batters`) is
  **INFEASIBLE** — `_project_active_batters` requires `score_mgr` and
  `_canon_player_name`, neither of which `Scoreboard` may take a
  reference to (rejected in `dual_broadcaster_substrate_audit.md`,
  Item 3 scoping pass).

The cleanest shape is therefore **PARTIAL-DELEGATION at the
caller**: migrate `build_full_payload` to call `get_live_state()`
directly, and have `_project_active_batters` (which already runs
on the live path) own the slot projection. `get_broadcast_state`
shrinks to a thin shim for shadow / external use, or is deprecated.

### 5.2 Two contract options

The migration has two viable end-states. The contract in §6 covers
both; the cleanup PR picks one.

| Option | End-state of `get_broadcast_state` | Pros | Cons |
|---|---|---|---|
| **A — Deprecate (recommended)** | retained as `def get_broadcast_state(self): warnings.warn(...); return self.get_live_state()` for any out-of-tree caller; the rewrite branches removed. Production caller switched to `get_live_state` | one source of truth (P2); shadow mode and live mode share one projection (P2 must lose its `if not shadow` gate for shadow correctness — see §6.4) | requires shadow-mode change in `build_full_payload` (small, isolated) |
| **B — Keep as wrapper** | `get_broadcast_state` keeps its rewrite branches but moves them into a private helper inside `Scoreboard`; production caller unchanged | zero risk to shadow mode; smallest diff | two projection paths persist; architectural debt is reduced but not removed; no `[WS-SLOT-INVARIANT]` rate change |

§6 is written assuming **Option A** as the recommended path; §6.5
sketches the Option B fallback for reviewers who prefer a smaller
PR.

---

## 6. Migration contract (Composer-2 executable, when scheduled)

> **Not for execution in this audit task.** Use this section as the
> design contract when the cleanup PR is opened, mirroring the
> structure of `dual_broadcaster_path_b_migration_contract.md`.

### 6.1 Files

| File | Change | Size |
|---|---|---|
| `files/eyes/scoreboard.py` | shrink `get_broadcast_state` to deprecated alias of `get_live_state`; remove the active-list rebuild branches | ~10 LOC removed |
| `files/test_pipeline.py` | swap `scoreboard.get_broadcast_state()` → `scoreboard.get_live_state()` at L4828; un-gate `_project_active_batters` from the `not score_mgr.shadow` clause **for slot writes only** (or move slot writes outside the shadow gate) | ~5 LOC |
| `files/test_recent_fixes.py` | add (a) test that `get_broadcast_state` returns the same dict as `get_live_state` (deprecation parity); (b) test that shadow-mode WS payload also goes through `_project_active_batters` (no regression); ensure existing `test_ws_projection_*` tests pass unchanged | +30 LOC (~3 new tests) |
| `files/docs/backlog.md` | update `## P0 — BallEventDetector` adjacent section with cleanup status; cross-reference this audit | docs only |

No analyzer change needed — no new telemetry tags.

### 6.2 Contract: `Scoreboard.get_broadcast_state`

After migration:

```python
def get_broadcast_state(self) -> dict:
    """Deprecated 2026-04-NN — use get_live_state(); WS-payload
    striker/non_striker projection now lives in
    test_pipeline._project_active_batters (Cluster 1 / Fix 7).
    Retained as alias for any out-of-tree caller."""
    return self.get_live_state()
```

Behaviour change matrix:

| Field set returned | before | after |
|---|---|---|
| identical to `get_live_state()` plus rewrite of `striker`/`non_striker` | ✓ | now identical to `get_live_state()` (no rewrite) |
| caller-visible diff in production | none — overwritten by P2 | none |
| caller-visible diff in shadow | P1 rewrote to active list | P2 will be invoked (per §6.3); identical end state |

### 6.3 Contract: `build_full_payload` slot wiring

Replace L4828 + L4837 gate:

```python
state = scoreboard.get_live_state() if scoreboard._inn else {}
if state:
    _ws_fallback_events = _project_active_batters(
        state, score_mgr, scoreboard, _canon_player_name)
    if not score_mgr.shadow and score_mgr.bowler_name:
        state["current_bowler"] = _canon_player_name(
            score_mgr.bowler_name, bowler=True)
    # WS-PROJECTION-FALLBACK telemetry, WS-SCRUB, enforce_ws_slot_invariant
    # all unchanged
```

Key change: `_project_active_batters` runs in shadow too. SM in
shadow holds the most recent `set_..` calls but does **not**
broadcast — the `_project_active_batters` write is harmless (it
writes into `state` which broadcast is not gating on shadow at
WS-emit). The bowler override stays gated on `not shadow` because
shadow SM bowler tracking lags by design.

### 6.4 Contract: shadow-mode parity

Add a regression test:

```python
def test_build_full_payload_shadow_uses_sm_first_projection() -> None:
    """Shadow-mode payload must still flow through
    _project_active_batters so striker/non_striker stay SM-canonical."""
    # Setup: ScoreManager(shadow=True), seed sm.striker, sm.non_striker
    # Drive build_full_payload (or extracted helper)
    # Assert: payload["striker"] == canon(sm.striker)
```

If the test cannot be written without exfiltrating
`build_full_payload` from `main_loop` (the WS-PROJECTION-GAP
deferral in `dual_broadcaster_path_b_migration_contract.md`
§12.5), file a follow-up: extract `build_full_payload` into a
module-level helper as a prerequisite. **Recommended:** do that
extraction first; then this migration is a 1-commit change.

### 6.5 Option B fallback (smaller PR)

If the cleanup PR cannot afford the shadow-mode test:

- Keep `get_broadcast_state` exactly as today.
- Add an explicit comment block:
  `# CLUSTER-1-OVERRIDDEN: striker/non_striker rewrite below is
  defended in shadow only; live path overwrites in
  _project_active_batters. See get_broadcast_state_path_b_audit.md §5.2.`
- Move on; revisit Option A when WS-PROJECTION-GAP extraction lands.

This is acceptable. It does **not** reduce architectural-debt
surface area, and it has the same `[WS-SLOT-INVARIANT]` impact (zero).

### 6.6 Decision points (resolved)

| Question | Resolution |
|---|---|
| Preserve `get_broadcast_state` for backwards compatibility? | **Yes**, as deprecated alias to `get_live_state`. There is one production caller and zero out-of-tree contracts that bind the rewrite behaviour, but the deprecation cost is one line. |
| Interaction with Path A WS-payload assembly? | None. Path A is in `dual_broadcaster_path_b_migration_contract.md` §12.5 territory — `build_full_payload` lives in `main_loop`. The contract above does not refactor that boundary; it only swaps the inner call. |
| Relationship to `parity_monitor` / element checker? | None. `parity_monitor` reads the post-WS payload, not `get_broadcast_state`. |
| Backwards-compatibility shape change? | None visible to consumers — migrated `get_broadcast_state` returns a strict superset of the old slot semantics (P2 already wrote SM-first; the rewrite was no-op on the live path). |

---

## 7. Predicted `[WS-SLOT-INVARIANT]` rate reduction

### 7.1 Headline number

**Predicted reduction from this migration: ≈0%.**

### 7.2 Reasoning

Every `[WS-SLOT-INVARIANT]` fire (387 + 26 in the cited windows) is
emitted by `enforce_ws_slot_invariant` only when
`state["striker"] == state["non_striker"]` after **P2**. Under the
current ordering:

- P1's slot rewrites are overwritten by P2 before the invariant runs.
- P2 writes `canon(sm.striker)` and `canon(sm.non_striker)`.
- The invariant therefore observes `state[slot] == state[other]`
  iff one of:
  1. `canon(sm.striker) == canon(sm.non_striker)` (SM-internal
     rotation gap); OR
  2. SM held one slot and `_inn` fell back the other to a value
     that canonicalised to the same name (rare — Fix 5 prevents
     same name in both `_inn` slots; canon collisions across slots
     would require two different raw scout names normalising to one
     squad key, which the squad-resolver dedupes on insert); OR
  3. WS-SCRUB rebuilt one slot from the active list to a value
     that already matched the other slot (when only one batting
     name remains).

Cause (1) is **SM-internal** — it is Lever 1 in the predecessor
audit (out of scope here). Cause (2) is rare and not addressed by
removing P1. Cause (3) is downstream of P2 and is itself triggered
by `_project_active_batters`/SM populating an inconsistent slot —
again, removing P1 does not change this.

### 7.3 What this migration **does** improve

- **One projection path instead of two.** Architectural
  simplification; less code to reason about during future audits.
- **Removes a silent rewrite.** P1's `state[slot] = active[0]`
  branches have no telemetry; their absence makes WS-SCRUB the
  single observable rewriter (with `[WS-SCRUB]` per event).
- **Closes the canon-mismatch micro-bug.** Edge case in §3.3
  (raw scout name in `_inn`): P1 may produce a non-canonical
  name; P2 always canonicalises. Effect on real traffic is small
  (sub-1% per estimate; SM canonicalises at ingest already).
- **Clarifies shadow mode.** Today shadow-mode WS payloads use a
  *different* projection from live mode. Post-migration they are
  identical (modulo the bowler override).

The honest framing for the cleanup PR description: *"architectural
debt cleanup; expected `[WS-SLOT-INVARIANT]` rate reduction is
zero. The genuine `[WS-SLOT-INVARIANT]` levers are SM rotation
atomicity (Lever 1 in striker_path_b_read_audit.md §3) and the
WS-PROJECTION-GAP `build_full_payload` extraction
(dual_broadcaster_path_b_migration_contract.md §12.5)."*

---

## 8. Risk assessment

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| Shadow-mode WS payload regression | MEDIUM | LOW | §6.4 regression test; or §6.5 Option B preserves shadow path verbatim |
| External caller of `get_broadcast_state` exists out of tree | LOW | VERY LOW (no current evidence) | Keep deprecated alias for one release cycle |
| Removing the active-list scrub re-introduces a dismissed-leak that P2 missed | LOW | LOW | WS-SCRUB at L4914–L4942 still runs and now becomes the *only* active-list defense — but it already telemeters every event, so any leak is observable. Existing tests `test_ws_projection_fallback_*` and `test_ws_slot_invariant_*` cover the boundary. |
| Test count regression | LOW | LOW | §6.1 adds 3 tests; expected count 672 → 675 PASS / 0 FAIL |
| Path A WS-payload deferral disturbed | LOW | NONE | Migration does not touch `main_loop` ordering; `build_full_payload` stays in place |
| Deferred extraction (§12.5 of contract) is a prerequisite | MEDIUM | LIKELY | Recommend §6.5 Option B until WS-PROJECTION-GAP extraction lands; revisit Option A then |

**Overall risk:** **LOW** for Option A given the regression test;
**VERY LOW** for Option B.

### Rollback

Both options are 1-commit changes. Revert restores prior behaviour
exactly. Existing tests are the safety net.

---

## 9. Cross-references

- **`files/docs/investigations/striker_path_b_read_audit.md`** — this
  audit's source. §3 (Lever 2 framing); §8 (predicted rate reduction
  attributed to SM rotation atomicity, not `get_broadcast_state`).
- **`files/docs/investigations/dual_broadcaster_path_b_migration_contract.md`**
  §12.5 — WS-PROJECTION-GAP / `build_full_payload` extraction
  deferral. Prerequisite for the cleanest version of Option A.
- **`files/docs/investigations/dual_broadcaster_substrate_audit.md`** —
  Item 3 scoping; rationale for not attaching `score_mgr` to
  `Scoreboard` (which forecloses the WRAPPER migration shape).
- **`files/docs/investigations/scorer_invariants_categorization.md`**
  §10.1 — Item 2 PR 1 backstop reads via `_canonical_active_slot`
  (SM-first); unaffected by this migration.

---

## 10. Files

- **New:** `files/docs/investigations/get_broadcast_state_path_b_audit.md`
  (this document).
- **No code changes.** The cleanup PR (Option A or B per §5.2 / §6.5)
  is the executable outcome; this audit is its design contract.
