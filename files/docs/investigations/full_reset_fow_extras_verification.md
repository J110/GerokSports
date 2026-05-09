# Verification: `ScoreManager.full_reset()` → FOW / extras clearing vs production POISON-RECAL

**Date:** 2026-04-29  
**Scope:** Documentation-only verification (no code changes). Confirms whether `_clear_per_innings_sm_surface` clearing **`scoreboard.fall_of_wickets`** and resetting **`scoreboard.extras`** when a scoreboard is attached is consistent with production **`[POISON-RECAL]`** behavior and downstream consumers.

**Related code (reference):**

- `ScoreManager.full_reset` → `force_cold_start_recalibration` + `_clear_per_innings_sm_surface`
- Item 3 Path B: SM FOW/extras read-through uses SB when attached; clear path mutates `scoreboard.fall_of_wickets` / `scoreboard.extras` when attached.

---

## 1. Production / executable `full_reset(` callsites

| # | File | Line | Caller context | Caller expectation (cleared vs preserved) |
|---|------|------|----------------|-------------------------------------------|
| 1 | `files/test_pipeline.py` | 7445–7449 | **`[POISON-RECAL]`** streak: tracker headline (`_inn` score/wickets/overs) cleared to `None` immediately before `full_reset(reason="poison_recal_consensus …")`. | **Nuclear recal:** SM per-innings cache cleared; operator intent is cold-start escape from stale baseline. With Item 3, SB **FOW + extras** cleared in `_clear` as well. Headline strip already nulled in same block (7441–7443). |
| 2 | `files/test_pipeline.py` | 2625 | **`STATE_RECOVERY_PHASE_2_ENABLED`**: `_apply_state_recovery_phase2_mutation` calls `score_mgr.full_reset(reason="state_recovery_consensus_override")`. | Same Fix-16 / nuclear semantics: wipe SM (and, with current `_clear`, SB FOW + extras when attached) then patch `_inn` from candidate (2629–2636). **Default repo:** Phase 2 is **off** (`STATE_RECOVERY_PHASE_2_ENABLED is False`); callsite is latent. |
| 3 | `files/score_manager.py` | 776 | Method definition + docstring only. | — |
| 4 | `files/test_recent_fixes.py` | 5079, 5112, 5147, 5278 | Unit tests: Fix-16 surface, cold bookkeeping, match-context preservation, poison fixture. | Assert SM fields; not production. |
| 5 | `files/test_recent_fixes.py` | 5264 | Source guard: `full_reset(` appears near `[POISON-RECAL]`. | — |

**Accounted:** All Python `full_reset(` invocations under `files/` are listed above (also confirmed with repo-wide `rg 'full_reset\('` excluding `venv`).

**Production-relevant:** **#1** (always when threshold hits) and **#2** (only if Phase 2 flag enabled).

---

## 2. Downstream consumers of `scoreboard.fall_of_wickets` and `scoreboard.extras`

### 2.1 `scoreboard.fall_of_wickets`

| Consumer | Location | Reads after `full_reset` in same session? | Expected value | Clearing breaks logic? |
|----------|----------|-------------------------------------------|----------------|------------------------|
| **`project_fow_for_payload`** | `test_pipeline.py` ~4813 | Yes — every `build_full_payload` | Trimmed / visible FOW for WS | **No** if list repopulates via `sync_fow_to_wickets` once `wickets` commits; **transient empty** acceptable during headline `None` window. |
| **WS payload** | `test_pipeline.py` ~5156–5157 (`fall_of_wickets`, internal count) | Yes | Aligned to physics after recovery | Same as above. |
| **`sync_fow_to_wickets`** | `eyes/scoreboard.py` ~3247 | Yes — called before DETAIL `_fow_count` (~9723–9730) | Length `≥ wickets` via placeholders | **Critical interaction** (see §3.1). |
| **First-frame INIT** | `test_pipeline.py` ~7895–7907 | Only when `_first_frame_initialized` is False | Pre-populate placeholders if `wickets > 0` and list empty | **Not re-run** after session boot. After `full_reset`, **repopulation is via `sync_fow_to_wickets`**, not INIT. |
| **Scorer prompt** | `test_pipeline.py` ~7956–7973 (`fow=fow_str`) | Yes | String snapshot for LLM | Empty `"None yet"` briefly after clear — acceptable for poison window. |
| **DETAIL (DRS branch)** | `test_pipeline.py` ~7351 | Same frame as poison possible | `len(fall_of_wickets)` | Reflects post-`full_reset` list when DETAIL runs after reset. |
| **DETAIL (main)** | `test_pipeline.py` ~9730, ~9768 | Every normal frame | After `sync_fow_to_wickets` | Placeholders added when `wickets` > 0 and list shorter than `wickets`. |
| **`eyes/main.py`** | ~469–470 | Logging only | FOW tail | Same as payload semantics. |
| **`parity_monitor` / `element_checker`** | `parity_monitor.py` ~44; `element_checker.py` ~485+ | Consume WS / snapshot | Expect eventual consistency | Transient gap possible. |

### 2.2 `scoreboard.extras`

| Consumer | Location | Reads after reset? | Expected | Clearing breaks logic? |
|----------|----------|-------------------|----------|------------------------|
| **`build_full_payload`** | `test_pipeline.py` ~5072 (`extras` dict copy) | Yes | Parity / UI extras breakdown | **Transient zeros** after reset until strip/Scorer repopulates — same class as headline cold-start. |
| **`_score_inf_floor_components`** | `test_pipeline.py` ~2648+ doc; usage ~5764–5822 | Yes | Floor gate / inferred totals | Short window of `total=0` may affect gates until extras recover — **same order as other poison window effects** (score also `None`). |
| **Logging** | `test_pipeline.py` ~9857–9861 | Diagnostics | Rebuilt from live reads | No hard dependency on preserving pre-poison extras. |
| **`parity_monitor`** | Doc reference to extras shape | WS parity | — | Observational. |

---

## 3. Log evidence: `[POISON-RECAL]` and post-fire FOW / extras

### 3.1 Counts (host `rg`, 2026-04-29)

| Log file | `[POISON-RECAL]` count | Notes |
|----------|------------------------|-------|
| `logs/pipeline-2026-04-28-pbks-rr-live.log` | **7** | Matches user reference (~164 min PBKS vs RR). |
| `files/logs/machine-1-2026-04-28.log` | **11** total | **7** events mirror PBKS RR timestamps/frames; **4** additional in **22:xx IST** post-restart window (F122, F162, F221, F319). User’s “3 fires” may refer to a **subset** (e.g. post-restart only) or a different slice — file as a whole has **11** matches. |

### 3.2 Interpreting `AFTER_fow_count` on the poison frame (pre– vs post–Item 3)

On **`[POISON-RECAL]`**, `test_pipeline.py` sets `scoreboard._inn["wickets"] = None` (with score/overs None) **before** `full_reset`.

**`Scoreboard.sync_fow_to_wickets()`** (`eyes/scoreboard.py` ~3261–3266) when `wickets` is missing/`0`:

- If **`len(fall_of_wickets) > wk`** (e.g. list has 4 rows, `wk = 0`), it **does not delete** rows — it logs that the wickets counter likely regressed and **keeps all FOW entries** (immutability).

**Therefore, historical logs** where **`AFTER_fow_count=4`** appear together with **`AFTER_score=None-None(None)`** on the **same frame as** `[SM-FULL-RESET]` are consistent with:

- **`fall_of_wickets` on the scoreboard was not cleared** (pre–Item-3 behavior: only SM’s copy was wiped), **and**
- **sync** refused to shorten the list while `wickets` was `0`.

**After Item 3** (SB list cleared inside `_clear_per_innings_sm_surface`):

- Same frame: `len(fall_of_wickets) == 0`, `wk == 0` → no “keep all” branch in the destructive sense; list stays **empty** until `wickets` commits again.
- Next frames: `sync_fow_to_wickets` **pads** placeholders with `while len(self.fall_of_wickets) < wk` when `wickets` returns to the true count (~3305–3311).

So **post–Item-3 `AFTER_fow_count` on the poison frame** is expected to drop to **0** (until repopulation), which is **more honest** than showing four rows while the headline says no confirmed wickets.

### 3.3 Sample: `machine-1-2026-04-28.log` post-restart `F122`

- **Line ~61275:** `[POISON-RECAL] … stuck_tracker=151→live=66`
- **Immediately after:** `[SM-FULL-RESET] reason=poison_recal_consensus …`
- **Same-frame DETAIL:** `AFTER_score=None-None(None)`, **`AFTER_fow_count=4`**

This pattern matches **§3.2 “pre–Item-3 / SB list not cleared”** (or build without SB FOW clear). It is **not** proof of incorrect post–Item-3 behavior.

### 3.4 Sample: `pipeline-2026-04-28-pbks-rr-live.log` `F2354`

- **Line ~27266:** `[POISON-RECAL]` (stale 222 vs poison 0)
- **DETAIL:** `AFTER_score=None-None(None)`, **`AFTER_fow_count=4`** with pre-poison batter rows still in BEFORE/AFTER bat slots for that frame

Same conclusion: consistent with **immutable FOW + wickets forced to 0** without list truncation.

### 3.5 Extras

Neither `[POISON-RECAL]` block nor `full_reset` in logs was cross-correlated with a dedicated **`EXTRAS:`** line in the narrow grep window. **Extras** clearing on `full_reset` was **not** contradicted by log lines in this pass; **post–Item-3 live confirmation** remains useful (see §5).

---

## 4. Categorization

| Area | Verdict | Rationale |
|------|---------|-----------|
| **Callsite intent (POISON-RECAL)** | **CORRECT** | Nuclear recal explicitly clears tracker headline and forces SM cold-start; extending that to SB **FOW + extras** matches “wipe denormalized display caches” and aligns SM read-through with SB. |
| **Consumer `sync_fow_to_wickets`** | **CORRECT** | After list cleared and `wickets` repopulates, placeholders are re-added; no consumer requires preserving old SB list through a poison recal. |
| **INIT pre-populate** | **CORRECT** | One-shot; recovery after `full_reset` does not depend on INIT. |
| **Historical log `AFTER_fow_count=4`** | **UNCLEAR → explained** | Logged behavior matches **legacy** SB list + immutability rule, **not** post–Item-3 cleared SB list. **Not** an anomaly for Item 3; **re-verify** on first post-deploy log with Item 3 binary (`AFTER_fow_count` → **0** on poison frame). |
| **Extras + Layer 1.5 floor** | **UNCLEAR** | Theoretically parallel to headline `None` window; needs **match-day** samples if floor fires spike after poison. |

**Overall:** **CORRECT** for design intent and consumer wiring, with **UNCLEAR** limited to **extras** under stress and **empirical confirmation of `AFTER_fow_count==0` on poison frame** post-deploy.

**No ANOMALY** filed from static analysis + log replay: nothing shows Item 3 clearing **breaks** an invariant that the old behavior preserved correctly; the old behavior **hid** inconsistency (FOW count vs `None` wickets).

---

## 5. Follow-ups (no implementation in this task)

### 5.1 If post-deploy logs show **ANOMALY**

- **Symptom:** `AFTER_fow_count` stays **> 0** while `AFTER_wickets=None` after `[SM-FULL-RESET]` when SB clear is expected (partial reset or double attachment).
- **Symptom:** Permanent loss of **confirmed** FOW rows after recovery (not placeholders) — would contradict `_add_fow` / dismiss upgrades; treat as separate scoreboard bug.

**Proposed fix direction (backlog only):** gate SB FOW/extras clear on `reason` prefix or add “preserve canonical FOW when …” — **only** if post-deploy evidence requires it.

### 5.2 Live monitoring (UNCLEAR burn-down)

1. **First match-day after Item 3:** grep `[POISON-RECAL]` and, on the **same frame**, assert `AFTER_fow_count=0` in DETAIL (or document if second path omits DETAIL).
2. **`[FOW]`** logs: spikes of “Length N > wickets counter 0 — keeping all” **after** Item 3 on poison frames would indicate **SB list not cleared** (regression in `_clear`).
3. **`EXTRAS` / SCORE-INF floor:** compare rate of floor gates in ±50 frames around `[POISON-RECAL]` vs baseline.

---

## 6. References

- `files/docs/investigations/dual_broadcaster_path_b_migration_contract.md` (Item 3)
- `files/score_manager.py` — `_clear_per_innings_sm_surface`, `full_reset`
- `files/test_pipeline.py` — `[POISON-RECAL]` (~7434+), INIT FOW (~7888+), DETAIL `_fow_count`, `sync_fow_to_wickets` (~9723)
- `files/eyes/scoreboard.py` — `sync_fow_to_wickets`

---

## 7. Conclusion

Clearing **`scoreboard.fall_of_wickets`** and resetting **`scoreboard.extras`** during **`full_reset`** when a scoreboard is attached is **semantically aligned** with production **`[POISON-RECAL]`** (nuclear baseline reset) and **downstream FOW logic** (sync repads from `wickets`). Historical PBKS / machine-1 logs showing **non-zero `AFTER_fow_count`** with **cleared headline** reflect **pre–Item-3 SB FOW persistence** and **`sync_fow_to_wickets` immutability**, not a contradiction of the new clear. **Post–Item-3 empirical confirmation** and **extras/floor** spot-checks remain **recommended** on the next match-day.
