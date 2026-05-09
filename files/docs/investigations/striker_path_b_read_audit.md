# Striker Path B — `_inn["striker"]` / `["non_striker"]` read audit

**Status (2026-04-29):** AUDIT ONLY — no code changes in this task.
**Scope:** every production read site of `scoreboard._inn["striker"]`
or `scoreboard._inn["non_striker"]` (and `.get(...)` equivalents) under
`files/`. Test-fixture writes (`sb._inn["striker"] = "X"` in
`test_recent_fixes.py` / `test_pipeline.py:_make_sb_for_*`) are
**out of scope** — they are intentional legacy-projection seeds.
**Predecessor:** the partial table in `files/docs/backlog.md` under
**“Striker Path B — `_inn[striker/non_striker]` READ audit
(2026-04-29)”**; this document supersedes that table with the
per-site Composer-2-ready specs the migration phase will need.

---

## 0. Architecture context (locked, do not re-litigate)

- **Path A (Fix 5 collision guard, `eyes/scoreboard.py:update_batter`,
  L2148–L2165):** stays as a defensive `update_batter` invariant.
  Refuses `striker == non_striker` writes regardless of caller.
- **Cluster 1 (shipped 2026-04-28):** SM-first reads at projection
  sites; `[STRIKER-SM-CUTOVER]` mirror writes via
  `_set_inn_slot_with_sm_mirror` (`test_pipeline.py:2300`); SCORER
  pre-gate (`_scorer_batter_update_allowed` /
  `_scorer_batter_row_is_dismissed_resurrection`).
- **Item 3 Path B LOW-risk batch (shipped 2026-04-29):** 12+
  `ScoreManager` properties read-through to `Scoreboard`; striker /
  non_striker explicitly excluded per
  `dual_broadcaster_substrate_audit.md` (FEEDER-existing field;
  needs this dedicated audit).
- **Item 2 PR 1 (shipped 2026-04-29):** `[BATTERS-INVARIANT]`
  backstop reads canonical slot via `_canonical_active_slot`
  (already SM-first); no change required by this audit.
- **`SM.full_reset` and the State Recovery aggregator are
  out-of-scope** for any subsequent migration PR (per task
  constraints + Item 3 deferral).

---

## 1. Production read-site inventory

The pattern set used to enumerate sites:

```text
rg "_inn\[(['\"])(striker|non_striker)\1\]|_inn\.get\(\s*(['\"])(striker|non_striker)\3" \
   files/ --type py
```

Every comment, write-site assignment, and test fixture has been
filtered out. Below is the **complete set of production read
sites** with category, current pattern, and SM-first equivalent.

### 1.1 Master table

| # | File / function | Line(s) | Pattern | Category | Already migrated? |
|---|-----------------|---------|---------|----------|-------------------|
| **R1** | `eyes/scoreboard.py` `update_batter` (Fix 5 collision guard) | **2153** | `self._inn.get("non_striker") == name` | **AUTHORITATIVE** (write-site precondition; `update_batter` is the writer for the legacy slot here) | n/a |
| **R2** | `eyes/scoreboard.py` `update_batter` (Fix 5 collision guard) | **2160** | `self._inn.get("striker") == name` | **AUTHORITATIVE** (same as R1; mirror branch for `striker=False` flag) | n/a |
| **R3** | `eyes/scoreboard.py` `_post_witnessed_dismissal_slot_rotation` | **3153** | `self._inn.get("striker") == dismissed` | **AUTHORITATIVE** (function is the legacy-slot writer; reads pick the rotation target) | n/a |
| **R4** | `eyes/scoreboard.py` `_post_witnessed_dismissal_slot_rotation` | **3155** | `self._inn.get("non_striker") == dismissed` | **AUTHORITATIVE** (same as R3) | n/a |
| **R5** | `eyes/scoreboard.py` `_post_witnessed_dismissal_slot_rotation` | **3187** | `_surviving = self._inn.get("non_striker")` | **AUTHORITATIVE** (read used to select the surviving batter to rotate into striker; immediately written back to both slots) | n/a |
| **R6** | `eyes/scoreboard.py` `dismiss_batter` | **3402** | `if self._inn.get("striker") == name:` | **AUTHORITATIVE** (write path; reads to decide which slot to clear) | n/a |
| **R7** | `eyes/scoreboard.py` `dismiss_batter` | **3404** | `if self._inn.get("non_striker") == name:` | **AUTHORITATIVE** (same as R6) | n/a |
| **R8** | `eyes/scoreboard.py` `get_live_state` | **3548–3549** | `inn.get("striker")` / `inn.get("non_striker")` returned in dict | **AUTHORITATIVE** (legacy projection consumer; consumed by `MatchStateAgent.validate` prompt + `eyes/main.py` log line + WS payload via `get_broadcast_state`) | n/a |
| **R9** | `eyes/scoreboard.py` `get_summary` | **3640–3641** | `inn.get("striker")` / `inn.get("non_striker")` returned in dict | **AUTHORITATIVE** (legacy projection snapshot; consumed by `eyes/main.py:556`) | n/a |
| **R10** | `eyes/scoreboard.py` `get_cache_dict` | **3862–3863** | `self._inn.get("striker")` / `("non_striker")` saved to disk cache | **AUTHORITATIVE** (snapshot of legacy projection for restore symmetry — must match what `_inn` will be re-hydrated to on next boot) | n/a |
| **R11** | `eyes/scoreboard.py` `get_current_batters` | **4212** | `striker = self._inn.get("striker")` (display marker) | **AUTHORITATIVE / DEFER** (display helper; scoreboard has no `score_mgr` reference — would require an optional parameter or moving the formatter to caller) | n/a |
| **R12** | `eyes/scoreboard.py` `get_current_batsman_handed` | **4260** | `striker = self._inn.get("striker")` (handedness lookup) | **AUTHORITATIVE / DEFER** (delivery-classifier handedness lookup; same scoreboard-internal constraint as R11) | n/a |
| **R13** | `test_pipeline.py` `_canonical_active_slot` | **2296–2297** | `sb.get(slot)` (the helper itself; SM-first, `_inn` fallback) | **BACKSTOP** (this *is* the documented helper; the read is the fallback by design) | n/a (the helper) |
| **R14** | `test_pipeline.py` `_project_active_batters` | **2209, 2214** | `_sb = scoreboard._inn or {}; _sb.get(_slot)` | **BACKSTOP** (`[WS-PROJECTION-FALLBACK]` — fires only when SM slot is null AND value is in `active_batting`; gated against `striker==non_striker` collision) | n/a (the helper) |
| **R15** | `test_pipeline.py` `_build_state_recovery_current` | **2552–2553** | `inn.get("striker")` / `inn.get("non_striker")` in candidate snapshot | **AUTHORITATIVE** (state-recovery aggregator compares against the **legacy projection** by contract — reading SM here would defeat the consensus check) | n/a (out-of-scope) |
| **R16** | `test_pipeline.py` DETAIL `_after_striker` / `_after_non_striker` (DRS-freeze branch) | **7427–7440** | `_inn.get("striker") / ("non_striker")` with SM-first override + `[STRIKER-READ-SM-CANONICAL]` divergence telemetry | **MIGRATED (Cluster 1)** | ✅ shipped |
| **R17** | `test_pipeline.py` DETAIL `_striker` / `_non_striker` (canonical branch, `state.get(...)`) | **9846–9848** | `score_mgr.striker or state.get("striker")` (and same for non) | **MIGRATED (Cluster 1)** — `state.get(...)` reads the `_inn`-derived projection but only as fallback after SM | ✅ shipped |

There are **no** `UNCLEAR` sites at the end of this audit. Every
production read traces to one of the four categories.

### 1.2 What is **not** in this table

- **Comments** at `test_pipeline.py:492, 4832, 7921, 9551, 9841` and
  `score_manager.py:2419` — documentation/log strings that contain
  the literal `_inn["striker"]` for grep-ability; no read.
- **Test fixtures** in `test_recent_fixes.py` (≈90 hits) and
  `test_pipeline.py:_make_sb_for_*` (4298–4300) — intentional
  legacy-projection seeds for tests that exercise rotation /
  collision behaviour. These will outlive any production
  migration; they are not callers of the live SM authority.
- **`get_broadcast_state`** (`scoreboard.py:3570`) — itself reads
  through `get_live_state()`; it’s a downstream consumer of R8,
  not a separate read site. Already covered by Cluster 1
  WS-payload handling (`_project_active_batters` +
  `enforce_ws_slot_invariant` in `test_pipeline.py:build_full_payload`).

---

## 2. Per-category rationale

### 2.1 AUTHORITATIVE (R1–R12)

These reads must keep `_inn` semantics. Three reasons appear:

1. **Write-site precondition (R1, R2, R3, R4, R5, R6, R7).** The
   function itself is the writer of the legacy slot it reads — it
   is choosing **which legacy slot to mutate** based on what the
   legacy projection currently holds. Reading SM here would either
   (a) cause SM and `_inn` to diverge further, because the
   write-side branch would be selected from a different source
   than the value being mutated; or (b) require a follow-up SM
   write that duplicates `_set_inn_slot_with_sm_mirror`'s
   responsibility. Cluster 1 already routes scorer-side writes
   through `_set_inn_slot_with_sm_mirror`; these scoreboard-internal
   write paths are the **other** writer and must keep operating on
   their own projection.
2. **Legacy projection consumer (R8, R9).** `get_live_state` /
   `get_summary` are documented projection snapshots returned to
   the LLM scorer prompt (`eyes/match_state.py`), the periodic
   `eyes/main.py:556` log line, and (transitively) the WS payload
   via `get_broadcast_state`. The WS payload is then re-projected
   through `_project_active_batters` (Cluster 1) which **does** put
   SM first; downstream consumers therefore already see the
   SM-canonical view. Migrating R8/R9 to read SM would either
   require attaching `score_mgr` to `Scoreboard` (rejected in the
   `dual_broadcaster_substrate_audit.md` Item 3 scoping pass) or
   removing the helpers entirely (a much larger refactor than this
   audit covers).
3. **Persistence symmetry (R10).** `get_cache_dict` writes the
   on-disk cache that `cache_restore` re-hydrates into `_inn` on
   the next boot. Reading SM here would create an asymmetry where
   the saved value differs from the value `_inn` will be restored
   to, breaking the round-trip property the cache test suite
   guards.
4. **Diagnostic “differs from SM” aggregator (R15).** The
   state-recovery aggregator’s entire purpose is to detect when
   the **legacy projection** has gone stale relative to candidate
   evidence. Reading SM in `_build_state_recovery_current` would
   make the aggregator unable to see the divergence it is
   designed to catch (an aggregator that compares SM-vs-SM tells
   you nothing).

#### 2.1.a `DEFER` sub-category (R11, R12)

`get_current_batters` and `get_current_batsman_handed` are
**display / lookup helpers on `Scoreboard`**. To read SM they
would need either:

- an optional `score_mgr` parameter (changes a public API), **or**
- attaching `score_mgr` to `Scoreboard` (rejected in Item 3 audit
  for symmetry / lifecycle reasons), **or**
- moving the formatters to the caller (`eyes/main.py:556` and
  `delivery_classifier`) so they can read SM directly.

The third option is the right fix but is **larger than the
striker-read scope** (it touches the delivery classifier’s
handedness path). Recommend leaving R11/R12 as
**AUTHORITATIVE / DEFER** and revisiting in a small dedicated PR
after the migration PR lands. No `[WS-SLOT-INVARIANT]` fires
trace to either site.

### 2.2 BACKSTOP (R13, R14)

Both are intentional fallbacks that already key on SM first:

- **R13 `_canonical_active_slot`:** `getattr(score_mgr, slot,
  None)`; only consults `_inn` when SM returned a non-batting /
  None value. This is the helper Cluster 1 introduced — by design.
- **R14 `_project_active_batters`:** `state["striker"]` /
  `state["non_striker"]` are seeded from SM (`canon_fn(score_mgr.
  striker)` etc.); the `_inn` read inside the loop fires only when
  the SM slot is `None` AND the value is currently
  `status="batting"` AND it doesn’t collide with the other slot.
  The fallback is the documented Fix 7 / WS-PROJECTION-GAP
  close-out (test coverage:
  `test_ws_projection_fallback_*` in `test_recent_fixes.py`).

**Documentation comment recommended (cleanup PR, not migration
PR):** add a one-line `# AUTHORITATIVE-BACKSTOP: see
striker_path_b_read_audit.md §2.2` above each read so future
contributors don’t mistake them for migration candidates. Sites
already carry long block comments explaining the intent; the
recommended one-liner is purely a grep anchor.

### 2.3 MIGRATED (R16, R17)

Both DETAIL log read sites in `test_pipeline.py` are already
SM-first; R16 emits `[STRIKER-READ-SM-CANONICAL]` divergence
telemetry. No further action. Test coverage:

- `test_path_b_striker_read_sm_canonical_drs_detail_present_in_source`
- `test_path_b_striker_read_sm_canonical_returns_sm_value_on_divergence`

### 2.4 No remaining MIGRATABLE sites

After this audit, there are **zero** strictly-MIGRATABLE
production read sites. The only `_inn["striker"]` /
`["non_striker"]` reads left in production paths are:

- write-site preconditions inside the legacy writers (R1–R7),
- documented projection consumers / persistence (R8–R10),
- two DEFER display/lookup helpers (R11, R12),
- two intentional BACKSTOP fallbacks already SM-first (R13, R14),
- the diagnostic aggregator (R15).

This is the contract the task asked the audit to establish.

---

## 3. `[WS-SLOT-INVARIANT]` correlation

**Source counts (per backlog `## P0 — BallEventDetector` / live
validation tables):**

- 387 fires in extended PBKS-vs-RR window (~164 min).
- 26 fires in 15-min post-restart window.
- Site of each fire: `enforce_ws_slot_invariant` in
  `test_pipeline.py:2230` (called from `build_full_payload`).

**Triggering inputs:** the WS payload reaches
`enforce_ws_slot_invariant` already populated by
`_project_active_batters` (R14, SM-first). The invariant catches
the residual case where **both slots** are non-null and equal.
That equality can arise from:

- (a) SM holding the same name in both slots (cleared briefly
  during rotation; SM-internal),
- (b) Cluster 1 backstop fallback writing the same name to
  the second slot when SM is None (R14 already gates this with
  `_other_slot` check),
- (c) `state` arriving with both slots set to the same value
  upstream of `_project_active_batters` (the `state` dict from
  `get_broadcast_state`, which itself derives from R8).

The audit confirms there is **no MIGRATABLE site whose migration
would directly reduce `[WS-SLOT-INVARIANT]` fires**. The right
follow-up is **not** a striker-read migration; it is one (or
both) of:

1. **SM-internal:** investigate the rotation paths in
   `score_manager.py` that briefly produce striker == non_striker
   between the two property writes. (Out of scope for this audit.)
2. **`get_broadcast_state` rebuild:** stop deriving the WS
   payload from `get_live_state()` (R8) and have it call
   `_project_active_batters` directly. That is a Path A
   refactor flagged in `dual_broadcaster_path_b_migration_contract.md`
   §12.5 (the **WS-PROJECTION-GAP** deferral). Also out of scope
   for this audit.

**Predicted backstop rate reduction from a striker-only read
migration: ~0%.** Documenting this explicitly so the cleanup
PR does not promise a rate reduction it cannot deliver.

---

## 4. Decision points (resolved by this audit)

> User asked four open questions in the task brief. All four are
> resolved here so the cleanup PR does not have to re-decide.

1. **Should migrated reads emit `[STRIKER-READ-SM-CANONICAL]`
   telemetry, or rely on existing coverage?**
   **No new telemetry needed.** The two MIGRATED sites (R16, R17)
   already cover divergence telemetry on the only paths where
   SM-vs-`_inn` divergence is interesting. Adding the tag to
   AUTHORITATIVE sites would create per-frame log spam (R8 fires
   every WS / log emission); adding it to BACKSTOP sites would
   double-count `[WS-PROJECTION-FALLBACK]`.
2. **How does this interact with the State Recovery aggregator?**
   R15 must keep reading `_inn` for the diagnostic to function.
   Confirmed and locked in §2.1 reason (4) above.
3. **Should AUTHORITATIVE sites get `# AUTHORITATIVE-SBINN-READ`
   comments to prevent future accidental migration?**
   **Yes, but as a docs-only follow-up PR**, not bundled into any
   migration: a one-liner `# AUTHORITATIVE-SBINN-READ: see
   striker_path_b_read_audit.md §2.1` above each of R1–R12, R15.
   This document is the canonical reference; the inline comments
   are grep anchors. AUTHORITATIVE-BACKSTOP equivalent for R13/R14
   per §2.2.
4. **Rollback plan for migration regressions?**
   **Not required for this PR.** No production migrations are
   proposed by this audit. If the docs-only cleanup ever adds
   accidental code, it can be reverted as a single commit; tests
   under `test_recent_fixes.py` (≥672 PASS / 0 FAIL today) are the
   safety net.

---

## 5. Migration order recommendation

Because there are no MIGRATABLE sites left, there is no
migration order to schedule. The recommended cleanup PR — when
someone does it — is:

1. **Docs-only sweep** (≈30 min):
   - Add `# AUTHORITATIVE-SBINN-READ` one-liners above R1–R12, R15.
   - Add `# AUTHORITATIVE-BACKSTOP` one-liners above R13, R14.
   - No behaviour change; no test count change expected.
2. **(Optional, separate PR) DEFER cleanup** for R11/R12: move
   `get_current_batters` / `get_current_batsman_handed` formatters
   to their callers so they can read SM directly. Estimated 1–2 h;
   touches `eyes/main.py:556` and `delivery_classifier`.
3. **(Out of scope) `[WS-SLOT-INVARIANT]` rate reduction:**
   investigate the SM-internal rotation gap and/or the
   `get_broadcast_state` → `_project_active_batters` direct
   wiring per §3 above. These are the actual levers for the
   387/26-fire-window data; a striker read migration would not
   help.

---

## 6. Per-MIGRATABLE site Composer-2 specs

**Empty.** No MIGRATABLE sites remain; see §1.4 / §2.4. The
template below is preserved unfilled so a future audit (e.g.
after the Path A `get_broadcast_state` rewrite) can drop new
MIGRATABLE sites into the same structure without re-deriving it.

```text
## R<N> — <file>:<func>:<line>
### Field name and type
striker | non_striker (str | None)
### Current read pattern
<rg snippet>
### SM canonical equivalent
score_mgr.striker | score_mgr.non_striker (or
_canonical_active_slot(score_mgr, scoreboard, slot))
### Migration shape
<read replacement; behavior change check; canon name path>
### Test scenarios for migration
- read returns SM canonical when SM != _inn
- read falls back to <X> when SM is None
- divergence telemetry emitted only on first divergence
### Backstop interaction
Predicted [WS-SLOT-INVARIANT] reduction: <pp>
```

---

## 7. Estimated callsite count per category

| Category | Production sites | Test fixtures (out of scope) |
|---|---:|---:|
| AUTHORITATIVE (write-site / consumer / persistence / aggregator) | **13** (R1–R12, R15) | — |
| AUTHORITATIVE / DEFER (display / lookup helpers) | **2** (R11, R12; subset of above) | — |
| BACKSTOP (intentional, SM-first) | **2** (R13, R14) | — |
| MIGRATED (Cluster 1, no further action) | **2** (R16, R17) | — |
| MIGRATABLE (this audit, after categorization) | **0** | — |
| **Test fixtures** (`sb._inn["striker"] = ...` seeds) | — | ~90 |

(R11 and R12 are counted once under AUTHORITATIVE and broken out
again as DEFER for visibility.)

---

## 8. Predicted `[WS-SLOT-INVARIANT]` rate reduction

**Predicted reduction from a striker-only read migration: ~0%.**

Justification: every fire originates inside or upstream of
`_project_active_batters`, which is already SM-first; the
remaining duplicate-slot pairings come from SM-internal rotation
gaps and from `get_broadcast_state` projecting an R8-derived
`state` dict. Neither lever is a striker `_inn` read.

**Where the rate-reduction work actually lives** (filed for the
backlog, not for this audit's PR):

- SM-internal rotation atomicity (`score_manager.py`).
- `get_broadcast_state` → direct call to
  `_project_active_batters` (Path A WS-PROJECTION-GAP follow-up,
  per `dual_broadcaster_path_b_migration_contract.md` §12.5).

---

## 9. Files

- **New:** `files/docs/investigations/striker_path_b_read_audit.md`
  (this document).
- **No code changes.** The only follow-up code work this audit
  endorses is the docs-only one-liner sweep in §5 step 1; that
  is a separate PR.

## 10. Cross-references

- `files/docs/backlog.md` — “Striker Path B — `_inn[striker/non_striker]`
  READ audit (2026-04-29)” (predecessor table; this doc supersedes).
- `files/docs/investigations/dual_broadcaster_substrate_audit.md`
  (Item 3 scoping; explains why striker/non_striker were excluded
  from the LOW-risk batch).
- `files/docs/investigations/dual_broadcaster_path_b_migration_contract.md`
  §12.5 (WS-PROJECTION-GAP / `build_full_payload` extraction
  deferral — the real lever for `[WS-SLOT-INVARIANT]` reduction).
- `files/docs/investigations/scorer_invariants_categorization.md`
  §10.1, §10.7 (Item 2 PR 1 backstop; reads through
  `_canonical_active_slot` so this audit does not affect it).
