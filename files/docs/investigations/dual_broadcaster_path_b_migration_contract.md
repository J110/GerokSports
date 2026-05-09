# Dual-broadcaster Path B — LOW-risk batch migration contract (2026-04-29)

This document is the **executable spec** for Item 3's first PR (LOW-risk batch + `bowler_name` divergence telemetry). Composer 2 should not need to make architectural decisions while implementing — every decision is resolved here, with reasoning so future agents can reconstruct intent.

**Scope:** 12 LOW-risk fields + 1 FEEDER-existing (`bowler_name`) verification.
**Out of scope:** the 2 MEDIUM-risk fields (`SM.overs` consensus baseline, `SM.bat1_name`/`bat2_name` slot ordering) and the 2 HIGH-risk surfaces (`this_over`, `partnership_*`). Those get their own dedicated PRs after this batch lands cleanly on a match log.

**Companion documents:**
- `files/docs/investigations/dual_broadcaster_substrate_audit.md` (the audit that produced the categorization)
- `files/docs/backlog.md` (record of what's in flight)

---

## 0. Recategorization vs the audit

After deeper analysis of `_accept_update`, three line items in the audit's LOW-risk classification need adjustment. **None move to MEDIUM-risk**, but the migration shape of two changes from the audit's "@property" suggestion to a hybrid (read-property + lockstep-write feeder), and one is split.

| Audit item | Audit shape | Contract shape | Why |
|---|---|---|---|
| `SM.bat1_runs/balls`, `SM.bat2_runs/balls` | "Property derived from `SB.batting_card[bat1_name]`" | **Read-only property; no SM-side write at all.** The setter form (`self.bat1_runs = X`) becomes a no-op (kept syntactically; setter writes nothing). | SB's `update_batter` is the canonical writer. SM has no consensus authority over per-batter runs/balls. SM was a denormalized cache only. |
| `SM.bowler_wickets/runs/overs` | Same | Same — read-only property, no SM-side write | SB's `update_bowler` is the canonical writer. |
| `SM.fow_list` (already noted "denormalized view") | Same | Same — read-only property reading `SB.fall_of_wickets` | SM never appended to fow_list authoritatively; it cached SB's. |

The other 9 LOW-risk fields keep the audit's recommended shape (read-through property + feeder write on SM accept).

**No fields are recategorized to MEDIUM-risk.** Audit classification holds.

---

## 1. Decision points (resolve once, apply everywhere)

These four decisions affect every field in the batch. Resolved here so the per-field spec stays terse.

### Decision A — Read caching: **READ-THROUGH every time, no caching.**

- **Resolution:** Every property access reads `Scoreboard` directly. No memoization, no per-frame cache.
- **Reasoning:** Parallel/cached state is the bug class Path B exists to eliminate. A dict lookup on `_inn` or `batting_card[name]` is O(1) — the ~100ns cost is invisible against a 50ms frame budget. Adding a cache would re-introduce the divergence-window risk we're trying to remove.
- **Implication:** Properties are stateless wrappers. SM gains no `@cached_property` decorators.

### Decision B — Write order: **SB.set() FIRST, then SM bookkeeping.**

- **Resolution:** Wherever SM `_accept_update` (or any SM mutation site) writes a LOW-risk field, the SB setter is called **before** any SM-internal bookkeeping that might depend on the value being committed.
- **Reasoning:** SB has its own consensus tracker (`ConsistentReadTracker`) that validates `set("score", ...)`. If SB rejects, SM's "accept" never happened in the canonical store — and SM's downstream consumers (which now read from SB via property) will correctly see the un-accepted state. Writing SM first then SB would create an asymmetric window where SM thinks the value is X but SB hasn't agreed.
- **Atomicity note:** This is intentionally NOT atomic — SB consensus may still reject. The contract is "SM defers to SB"; SM accept attempts are SB-feeder writes, and SM treats SB's accept/reject as the truth.
- **Telemetry:** `[SM-FEEDER-SYNC] field=X value=Y sb_accepted=true|false reason=...` — see Decision F below.

### Decision C — Failure mode (SB accessor raises / returns None / rejects): **READ returns None; WRITE logs and continues.**

- **Resolution:** 
  - **Read path:** if `self.scoreboard is None`, or `scoreboard._inn` is `{}`, or the looked-up key is missing, the property returns `None` (matching pre-migration behavior of `self.score = None` at construction).
  - **Write path (`_accept_update` calling `SB.set(...)`):**
    - If `self.scoreboard is None` → log `[SM-FEEDER-SYNC] sb_attached=false` once per session, do nothing.
    - If `SB.set(...)` returns `False` (consensus rejected, validation failed) → log `[SM-FEEDER-SYNC] field=X value=Y sb_accepted=false` and continue. SM does NOT abort; SM does NOT raise.
    - If `SB.set(...)` raises → log `[SM-FEEDER-SYNC] field=X value=Y sb_error=...` and continue. SM does NOT propagate.
- **Reasoning:** SM's contract today is "best-effort accept based on consensus". Path B preserves that contract — a SB-rejected write is the same observable outcome as the existing "SM consensus failed" path: the value isn't visible to downstream readers. Raising from SM would change the upstream `on_frame` contract.

### Decision D — `SM.shadow` mode: **Same property semantics; emit divergence telemetry instead of mutating.**

- **Resolution:**
  - In `shadow=True`, the property still reads SB (so `SM.score` returns SB's value, just like in non-shadow).
  - In `shadow=True`, the **write side** does NOT call `SB.set(...)` (we are not the active writer). Instead, the write attempts emit `[SM-SHADOW-PARITY] field=X sm_would_accept=Y sb_value=Z divergence=true|false` so we can compare what SM would have accepted vs what SB has.
  - Non-shadow (`shadow=False`) does call `SB.set(...)` (acts as feeder).
- **Reasoning:** Today, shadow SM tracks its own state in parallel for parity comparison. Path B preserves the parity-monitoring use-case by emitting divergence telemetry — but stops the shadow SM from holding its own ghost copy of the canonical fields. In production, SM is `shadow=False` (live), so `SB.set(...)` is the normal path.
- **Caveat:** Existing pipeline already calls `SB.set(...)` for these fields independently of SM. So in `shadow=False`, the SM-side SB.set call may be redundant (SB will return False on the second call if the value didn't change, or accept if it did). This is harmless — SB.set is idempotent on identical values. Telemetry will flag it once per redundant call so the cleanup of the upstream redundant write site can be done in a follow-up if noise becomes a problem.

### Decision E — Frame-number threading

- **Resolution:** `_accept_update` is called from `_handle_warm` / `_handle_cold_start`, which receive `frame: FrameInput`. `_accept_update` already needs `frame` to call `SB.set(...)` (which requires a frame argument). Thread `frame: FrameInput` (or `frame.frame_number: int`) into `_accept_update`'s signature.
- **Reasoning:** SB consensus tracking is frame-keyed. Without a frame number, `SB.set(...)` cannot increment its tracker correctly.
- **Backward compatibility:** Existing tests that call `_accept_update(card)` directly need the new `frame=...` arg. Default value `frame=0` is acceptable for tests; production callsites must pass the real frame.

### Decision F — Telemetry tag conventions

| Tag | When to emit | Format |
|---|---|---|
| `[SM-FEEDER-SYNC]` | Every time SM writes a LOW-risk field (one log per write attempt; non-shadow) | `[SM-FEEDER-SYNC] field=<name> value=<v> sb_accepted=<true\|false> [reason=<...>]` |
| `[SM-FEEDER-DIVERGENCE]` | On read, when SM's would-be-internal value would differ from SB. Only relevant for `bowler_name` (FEEDER-existing). For LOW-risk batch, SM no longer has internal value to compare → tag does not apply. | `[SM-FEEDER-DIVERGENCE] field=bowler_name sm_value=<x> sb_value=<y>` |
| `[SM-SHADOW-PARITY]` | In `shadow=True` mode, when `_accept_update` would have written a value | `[SM-SHADOW-PARITY] field=<name> sm_would_accept=<v> sb_value=<sb_v> divergence=<true\|false>` |

All three should be `log.info` (not `log.warn`) for the steady-state case. The analyzer adds three regex labels for production monitoring.

---

## 2. Per-field migration spec table

For each field below:
- **Type** = Python type annotation (today's value)
- **SM impl today** = where `self.<field>` is initialized + mutated
- **SB accessor** = how to read SB's canonical value (USE-AS-IS unless otherwise noted)
- **Migration shape** = `READ-ONLY-PROPERTY` (no setter; SM never writes) or `READ-PROPERTY + FEEDER-WRITE` (property reads SB; setter calls `SB.set(...)`) or `HYBRID` (custom)
- **Existing SB writer** = the canonical writer the pipeline calls today
- **Risk** = LOW (per audit) — additional notes if any
- **Callsites (estimate)** = number of files × sites Composer 2 should expect

| # | SM field | Type | SM impl today | SB accessor | Existing SB writer | Migration shape | Risk | Callsites |
|---:|---|---|---|---|---|---|---|---:|
| 1 | `SM.score` | `int \| None` | init at L106; written `_accept_update:1268`, reset paths | `self.scoreboard._inn.get("score")` (USE-AS-IS) | `Scoreboard.set("score", v, frame)` (USE-AS-IS) | **READ-PROPERTY + FEEDER-WRITE** | LOW | ~25 reads, 6 writes |
| 2 | `SM.wickets` | `int \| None` | init at L107; `_accept_update:1270` | `self.scoreboard._inn.get("wickets")` (USE-AS-IS) | `Scoreboard.set("wickets", v, frame)` (USE-AS-IS) | **READ-PROPERTY + FEEDER-WRITE** | LOW | ~20 reads, 6 writes |
| 3 | `SM.run_rate` | `float \| None` | init at L142; written when computed | `self.scoreboard._inn.get("run_rate")` (USE-AS-IS) | `Scoreboard.set("run_rate", v, frame)` (USE-AS-IS) | **READ-PROPERTY + FEEDER-WRITE** | LOW | ~5 reads, 4 writes |
| 4 | `SM.target` | `int \| None` | init at L127; written `_accept_update:1349`, `set_innings_2:1245` | `self.scoreboard._inn.get("target")` (USE-AS-IS) | `Scoreboard.set("target", v, frame)` (USE-AS-IS; innings-2 only — innings-1 returns False, log.warn) | **READ-PROPERTY + FEEDER-WRITE** | LOW | ~6 reads, 3 writes — **see Note A** |
| 5 | `SM.batting_team` | `str \| None` | init at L126; `_accept_update:813` (frame.broadcast_team), `set_innings_2:1247` | `self.scoreboard.batting_team` (USE-AS-IS, top-level attr — **NOT** in `_inn`) | `Scoreboard.setup_innings(...)` / direct attr write in `Scoreboard.set_innings_2` (USE-AS-IS) | **READ-PROPERTY + FEEDER-WRITE** | LOW | ~12 reads, 4 writes — **see Note B** |
| 6 | `SM.innings` | `int (1\|2)` | init at L130; `set_innings_2:1243`, `_handle_innings_change`, `_accept_update:818` | `self.scoreboard.current_innings` (USE-AS-IS, top-level attr) | `Scoreboard.set_innings_2(...)` (USE-AS-IS) | **READ-ONLY-PROPERTY** | LOW | ~30 reads, 4 writes — **see Note C** |
| 7 | `SM.bat1_runs` | `int \| None` | init at L111; `_update_batters` | `self.scoreboard.batting_card.get(self.bat1_name, {}).get("runs")` (USE-AS-IS) | `Scoreboard.update_batter(name, runs, balls, ...)` (USE-AS-IS) | **READ-ONLY-PROPERTY** (write side becomes no-op; SM has no consensus authority over per-batter runs) | LOW | ~10 reads, 5 writes — **see Note D** |
| 8 | `SM.bat1_balls` | `int \| None` | init at L112; `_update_batters` | `self.scoreboard.batting_card.get(self.bat1_name, {}).get("balls")` (USE-AS-IS) | `Scoreboard.update_batter` (USE-AS-IS) | **READ-ONLY-PROPERTY** | LOW | ~10 reads, 5 writes |
| 9 | `SM.bat2_runs` | `int \| None` | init at L114; `_update_batters` | `self.scoreboard.batting_card.get(self.bat2_name, {}).get("runs")` (USE-AS-IS) | `Scoreboard.update_batter` (USE-AS-IS) | **READ-ONLY-PROPERTY** | LOW | ~10 reads, 5 writes |
| 10 | `SM.bat2_balls` | `int \| None` | init at L115; `_update_batters` | `self.scoreboard.batting_card.get(self.bat2_name, {}).get("balls")` (USE-AS-IS) | `Scoreboard.update_batter` (USE-AS-IS) | **READ-ONLY-PROPERTY** | LOW | ~10 reads, 5 writes |
| 11 | `SM.bowler_wickets` | `int \| None` | init at L118; `_accept_update:1330, 1337` | `self.scoreboard.bowling_card.get(self.bowler_name, {}).get("wickets")` (USE-AS-IS) | `Scoreboard.update_bowler(...)` (USE-AS-IS) | **READ-ONLY-PROPERTY** | LOW | ~6 reads, 6 writes |
| 12 | `SM.bowler_runs` | `int \| None` | init at L119; `_accept_update:1331, 1338` | `self.scoreboard.bowling_card.get(self.bowler_name, {}).get("runs")` (USE-AS-IS) | `Scoreboard.update_bowler` (USE-AS-IS) | **READ-ONLY-PROPERTY** | LOW | ~6 reads, 6 writes |
| 13 | `SM.bowler_overs` | `float \| None` | init at L120; `_accept_update:1333, 1340` | `self.scoreboard.bowling_card.get(self.bowler_name, {}).get("overs")` (USE-AS-IS) | `Scoreboard.update_bowler` (USE-AS-IS) | **READ-ONLY-PROPERTY** | LOW | ~6 reads, 6 writes |
| 14 | `SM.fow_list` | `list[dict]` | init at L163; `_accept_update` (~L827 in shadow init) | `list(self.scoreboard.fall_of_wickets or [])` (USE-AS-IS) | `Scoreboard._add_fow(...)` / dismiss path (USE-AS-IS) | **READ-ONLY-PROPERTY** | LOW | ~5 reads, 1 write |
| 15 | `SM.innings_extras` | `int` | init at L174; `_handle_warm` extras path | `self.scoreboard.extras.get("total", 0)` (USE-AS-IS) | `Scoreboard` extras-update path (USE-AS-IS) | **READ-ONLY-PROPERTY** | LOW | ~3 reads, 3 writes |
| 16 | `SM.this_over_extras` | `int` | init at L175; over-rollover (~L1845) | `self.scoreboard.extras.get("this_over", 0)` (USE-AS-IS) | `Scoreboard` extras-update path (USE-AS-IS) | **READ-ONLY-PROPERTY** | LOW | ~3 reads, 3 writes |
| 17 | `SM.extras_log` | `list[dict]` | init at L176; `_handle_warm` extras path | `list(self.scoreboard.extras.get("log", []))` (USE-AS-IS) | `Scoreboard` extras-update path (USE-AS-IS) | **READ-ONLY-PROPERTY** | LOW | ~3 reads, 3 writes |

**Total batch:** **17 SM field migrations** (the audit grouped some related fields; this contract enumerates each separately for clarity). Estimated touches: **~165 reads + ~70 writes across `score_manager.py` and `test_pipeline.py`** (plus ~15 test-file references in `test_recent_fixes.py` that need updating to use the new property surface — most are read-style and continue to work unchanged through the property).

### Notes

- **Note A (`target`):** `Scoreboard.set("target", v, frame)` returns `False` and `log.warn`s if `current_innings == 1`. SM's `_accept_update` already gates `target` writes on `card.get("broadcast_target") and not self.target`; that gate stays. SM's read property returns `None` in innings 1 (because SB._inn["target"] is `None` in innings 1), which matches today's behavior.
- **Note B (`batting_team`):** Lives at `Scoreboard.batting_team` (top-level attribute), NOT `_inn["batting_team"]`. Property reads `self.scoreboard.batting_team` directly. Feeder write is `self.scoreboard.batting_team = value` if `self.scoreboard is not None`. There is no `Scoreboard.set("batting_team", ...)` API and we DO NOT add one — direct attribute write matches existing pipeline pattern (e.g. `setup_innings`, `set_innings_2`).
- **Note C (`innings` is read-only):** SM's writes to `self.innings` today (`set_innings_2:1243`, `_handle_innings_change`, `_accept_update:818`) become no-ops. The canonical innings flip is `Scoreboard.set_innings_2(...)`, called from `apply_scorer_decision` separately. SM's previous `self.innings = 2` writes were redundant mirrors. Telemetry: emit `[SM-FEEDER-SYNC] field=innings sm_would_set=2 sb_value=<current> note=read_only_now` once per call.
- **Note D (`bat*_runs/balls`, `bowler_*` are read-only):** Setter form (`self.bat1_runs = X`) is preserved syntactically (so existing pipeline code doesn't break), but the setter is a no-op that logs `[SM-FEEDER-SYNC] field=bat1_runs note=read_only_now sb_value=<v>` once per call (rate-limit may apply if the log gets noisy in the first match-day). The actual SB-side update is via `Scoreboard.update_batter(...)` / `update_bowler(...)`, which the pipeline already calls.

---

## 3. `bowler_name` — FEEDER-existing verification

**Categorization (audit-confirmed):** `SM.bowler_name` ↔ `SB._inn["current_bowler"]` is FEEDER-existing. Path A's `build_full_payload` writes `state["current_bowler"] = score_mgr.bowler_name` directly — SM is the canonical for the WS payload, SB tracks `current_bowler` on its own consensus path (with BOWLER-STALE / rotation guards / 3-frame consensus).

**No code change needed beyond telemetry add.** SM stays as the WS-canonical writer for `current_bowler`. The lockstep is maintained today by virtue of Path A's projection + SB's independent consensus.

**`[SM-FEEDER-DIVERGENCE]` telemetry shape:**

```
[SM-FEEDER-DIVERGENCE] field=bowler_name sm_value=<name|None> sb_value=<name|None> sb_consensus_state=<active|pending|locked> frames_since_sm_update=<n>
```

- **Where to emit:** at the bottom of `build_full_payload`, after `state["current_bowler"]` is written, compare `score_mgr.bowler_name` vs `scoreboard._inn.get("current_bowler")`. Emit only on signature change (similar to existing `[WS-PROJECTION-GAP]` pattern at L4815-4886) so steady-state divergence is logged once, not every frame.
- **Expected divergence rate:** ~0 in steady state. Acceptable transient divergence:
  - During BOWLER-STALE windows, SB's `current_bowler` may lag SM's by 1-3 frames (3-frame consensus). This is benign.
  - During `_bowler_must_change` grace, SM's `bowler_name` may transition to the new bowler before SB confirms. Also benign.
- **What divergence rate signals a real problem:** persistent (> 5-frame) divergence between SM and SB on `bowler_name` while neither side is in a documented grace window indicates a real lockstep gap. Document the threshold in the analyzer label so post-deploy monitoring can flag it.
- **Analyzer label:** add `bowler_name_feeder_divergence` to `bundle_bc_events` (analyzer regex: `\[SM-FEEDER-DIVERGENCE\]\s+field=bowler_name`). Self-test fixture line: extend `test_analyzer_bundle_bc_signature_report_counts_new_guards` with one fixture line firing `[SM-FEEDER-DIVERGENCE] field=bowler_name sm_value='X' sb_value='Y' sb_consensus_state=active frames_since_sm_update=2`.

---

## 4. Migration order (sequence within the PR)

Composer 2 should land migrations in this order. Each step is independently testable; the PR can be split into 5 commits if reviewability is preferred.

### Step 1 — Read-only properties for **denormalized cache** fields (no SM writes today; lowest risk)

**Fields:** #14 `fow_list`, #15 `innings_extras`, #16 `this_over_extras`, #17 `extras_log`.

**Why first:** These fields have no SM-side authoritative write — SM was always a denormalized cache. Removing the cache and reading SB directly is the closest thing to a no-op. Zero behavioral risk.

**What changes:**
- Remove the four instance-variable initializations (L163, L174, L175, L176).
- Add four `@property` definitions reading SB.
- Update `_clear_per_innings_sm_surface` (L263, L266, L267, L268) to remove these field resets (properties have no state to clear).
- Update `_handle_warm`'s extras path to call SB's extras update API (already happens via pipeline, verify).

**Tests to add:**
- `test_pathb_low_fow_list_property_reads_scoreboard`: SB has 3 FOW entries, SM property returns the same 3 entries.
- `test_pathb_low_extras_total_property_reads_scoreboard`: SB.extras["total"] = 7, SM.innings_extras returns 7.
- `test_pathb_low_extras_property_returns_empty_when_sb_unattached`: `SM(scoreboard=None).innings_extras == 0`.

### Step 2 — Read-only properties for **per-batter / per-bowler stats** fields

**Fields:** #7-#10 `bat1_runs`, `bat1_balls`, `bat2_runs`, `bat2_balls`; #11-#13 `bowler_wickets`, `bowler_runs`, `bowler_overs`.

**Why second:** SM has a setter today (`self.bat1_runs = X`), but it's a denormalized cache write — pipeline already calls `update_batter` / `update_bowler` separately. The migration converts SM's setter to a no-op (logs `[SM-FEEDER-SYNC] note=read_only_now`). This step has higher write-callsite count (~30 sites) but the writes are all redundant cache mirrors.

**Dependency:** depends on `bat1_name` / `bat2_name` / `bowler_name` continuing to exist as SM-internal — they do (out of scope for this batch). Property read is `SB.batting_card.get(self.bat1_name, {}).get("runs")` — `self.bat1_name` is the SM-internal name field, untouched.

**What changes:**
- Remove instance-variable initializations (L111, L112, L114, L115, L118, L119, L120).
- Add 7 `@property` definitions.
- Add 7 `@<field>.setter` decorators that emit `[SM-FEEDER-SYNC] note=read_only_now` and DO NOT write SM state. Setters are kept (not removed) so `self.bat1_runs = X` callsites in `_update_batters` / `_handle_innings_change` / `set_innings_2` / `full_reset` continue to compile and run; their effect is now a log-only noop.
- `_snapshot()` (L1254) reads via property — works unchanged.
- `_clear_per_innings_sm_surface` (L231-240) — remove these field resets (properties have no state).

**Tests to add:**
- `test_pathb_low_bat1_runs_property_reads_card`: `SB.batting_card["A"]["runs"] = 42`, set `sm.bat1_name = "A"`, assert `sm.bat1_runs == 42`.
- `test_pathb_low_bat1_runs_setter_is_noop_with_telemetry`: assign `sm.bat1_runs = 99`; assert SB unchanged AND `[SM-FEEDER-SYNC] note=read_only_now` logged.
- Same pattern for bowler: `sm.bowler_runs == SB.bowling_card[sm.bowler_name]["runs"]`.

### Step 3 — Read-only property for **`SM.innings`** (with no-op writes + telemetry)

**Field:** #6 `innings`.

**Why third:** Innings is a top-level integer that SM had been mirror-writing on innings transitions. The canonical writer is `Scoreboard.set_innings_2(...)`. SM's writes were redundant. Migration is mechanically simple but touches `set_innings_2` and `_handle_innings_change` — both are well-tested already.

**What changes:**
- Remove L130 init.
- Add `@property innings(self)` reading `self.scoreboard.current_innings if self.scoreboard else 1`.
- Add no-op `@innings.setter` that emits `[SM-FEEDER-SYNC] field=innings note=read_only_now sb_value=<n>`.
- Update `set_innings_2` (~L1243, L1248) to drop `self.innings = 2` and `self.mode = "COLD_START"` is unchanged (mode IS SM-internal).

**Tests:**
- `test_pathb_low_innings_property_reflects_scoreboard`: SB.current_innings = 2 → SM.innings == 2.
- `test_pathb_low_innings_setter_is_noop_with_telemetry`.
- Regression: `test_set_innings_2_sequence` (existing) still passes.

### Step 4 — `READ-PROPERTY + FEEDER-WRITE` for **`SM.score`, `SM.wickets`, `SM.run_rate`, `SM.target`**

**Fields:** #1, #2, #3, #4.

**Why fourth:** Largest behavioural risk in the batch. SM is a writer (via `_accept_update`); the migration converts the write into `SB.set(...)` feeder. Requires Decision E (frame threading).

**What changes:**
- Remove L106-108 inits (score, wickets, overs — wait, **`SM.overs` is MEDIUM-risk and out of scope; do NOT remove L108**). Remove only score (L106), wickets (L107). For `target` (L127) and `run_rate` (L142), remove inits.
- Add 4 properties reading `self.scoreboard._inn.get("score")` etc.
- Add 4 setters that:
  1. If `self.shadow`: emit `[SM-SHADOW-PARITY]` and return.
  2. If `self.scoreboard is None`: emit `[SM-FEEDER-SYNC] sb_attached=false` (rate-limited) and return.
  3. Call `ok = self.scoreboard.set("score", value, self._current_frame)` and emit `[SM-FEEDER-SYNC] field=score value=<v> sb_accepted=<ok>`.
- Thread `frame: int` parameter into `_accept_update` signature; update callers (`_handle_warm`, `_handle_cold_start`) to pass `frame.frame_number`.
- Add `self._current_frame: int = 0` instance variable initialized in `__init__`, updated at top of `on_frame` from `frame.frame_number`. The setters use this to call SB.set without needing the frame in the setter signature (Python property setters take only `self, value`).
- Update `_clear_per_innings_sm_surface` (L226-228) — remove `self.score = None` etc. for migrated fields; keep `self.overs = None` (out of scope).

**Tests:**
- `test_pathb_low_score_setter_calls_sb_set_with_telemetry`: assign `sm.score = 42`, assert `SB._inn["score"] == 42` (after frame increments enough for SB consensus) AND `[SM-FEEDER-SYNC]` line emitted.
- `test_pathb_low_score_setter_in_shadow_emits_parity_only`: `sm = SM(shadow=True)`, assign `sm.score = 42`; assert SB unchanged, `[SM-SHADOW-PARITY]` logged.
- `test_pathb_low_score_setter_handles_sb_unattached`: `sm.scoreboard = None`, assign — no exception, telemetry logged once.
- `test_pathb_low_score_setter_continues_on_sb_reject`: SB rejects (e.g. score regression); assert SM does not raise, telemetry logs `sb_accepted=false`.

### Step 5 — `READ-PROPERTY + FEEDER-WRITE` for **`SM.batting_team`**

**Field:** #5.

**Why last:** `batting_team` is a top-level `Scoreboard` attribute (NOT in `_inn`). Migration shape is similar to Step 4 but the SB write is direct attribute assignment, not `SB.set(...)`. Isolated last so the SB-set pattern from Step 4 is fully validated before this variant lands.

**What changes:**
- Remove L126 init.
- Add `@property batting_team(self)` reading `self.scoreboard.batting_team if self.scoreboard else None`.
- Add `@batting_team.setter` that:
  1. If `self.shadow`: emit `[SM-SHADOW-PARITY]` and return.
  2. If `self.scoreboard is None`: log once and return.
  3. `self.scoreboard.batting_team = value` and emit `[SM-FEEDER-SYNC] field=batting_team value=<v> sb_accepted=true`.
- Update `_accept_update` (~L813), `set_innings_2` (~L1247) to write through the setter (which is the existing assignment syntax — no callsite changes needed if the setter has the same name).

**Tests:**
- `test_pathb_low_batting_team_property_reads_scoreboard`.
- `test_pathb_low_batting_team_setter_writes_scoreboard`.
- `test_pathb_low_batting_team_setter_in_shadow_emits_parity_only`.

### Step 6 — `bowler_name` divergence telemetry add (no SM change)

**Field:** `bowler_name`.

**Why last (independent of Steps 1-5):** This is the only change to `test_pipeline.py` (specifically, `build_full_payload`). Mechanically simple, but lives in a different file from Steps 1-5 (which are all in `score_manager.py`). Land last so the PR diff is reviewable file-by-file.

**What changes:**
- In `build_full_payload`, after `state["current_bowler"] = _canon_player_name(score_mgr.bowler_name, bowler=True)` (~L4727-4728), add a divergence check:
  - Compare `score_mgr.bowler_name` vs `scoreboard._inn.get("current_bowler")`.
  - Emit `[SM-FEEDER-DIVERGENCE] field=bowler_name sm_value=<a> sb_value=<b> sb_consensus_state=<...> frames_since_sm_update=<n>` only on signature change (mirror `[WS-PROJECTION-GAP]` rate-limit pattern, ~L4849).
- Add `STRIKER_FEEDER_DIVERGENCE = re.compile(r"\[SM-FEEDER-DIVERGENCE\]\s+field=bowler_name")` to `analyze_match_telemetry.py` and corresponding bundle B/C label.
- Extend self-test fixture in `test_analyzer_bundle_bc_signature_report_counts_new_guards` with one synthetic fire.

**Tests:**
- `test_pathb_bowler_name_divergence_telemetry_present_in_source`: source-level wiring guard checking `[SM-FEEDER-DIVERGENCE]` substring + `field=bowler_name` substring + `_last_divergence_sig`-style rate-limit check.
- (No behavioural test required — telemetry-only.)

---

## 5. Per-step test count target

| Step | New tests |
|---|---:|
| 1 | 4 |
| 2 | 8 (1 read + 1 noop-setter per of 4 batter fields, but bowler stats can share 3 read + 1 noop-setter) → realistically 8 |
| 3 | 3 |
| 4 | 6 (4 setter behaviours + 2 read property) |
| 5 | 3 |
| 6 | 1 + analyzer self-test fixture extension |
| **Total** | **~25** |

Expected post-PR test count: **648** (623 today + 25). All existing tests must continue to PASS.

---

## 6. Constraints (apply to every step)

- **DOES NOT** modify `eyes/scoreboard.py` canonical semantics. Properties are pure read wrappers; setters are pure feeder writes. No new SB methods.
- **DOES NOT** change observable behavior outside SM. WS payload assembly (Path A) sees the same values; only the SM-internal storage shape changes.
- **DOES NOT** touch `SM.full_reset` (shipped 2026-04-28). The fields it clears via `_clear_per_innings_sm_surface` are removed from the clear list as they migrate (because there's no SM state to clear), but the method's call surface stays.
- **DOES NOT** touch `StateRecoveryAggregator` (Phase 1 active, Phase 2 staged). Its `_build_state_recovery_current` reads `scoreboard._inn` directly (AUTHORITATIVE per Item 1 audit) — it does NOT read `score_mgr.score` etc., so this PR has no interaction surface.
- **DOES NOT** touch the 3 FEEDER-existing fields' write semantics: `striker`, `non_striker`, `bowler_name` continue to be SM-canonical writers; only `bowler_name` gains divergence telemetry (Step 6).
- **DOES** preserve Path A WS-payload correctness. Path A reads SB for everything except `striker` / `non_striker` / `current_bowler` (which it pulls from SM). After this PR, `score_mgr.score` / `wickets` etc. return SB's value — same as Path A would read directly. Net effect on Path A: unchanged. Verify by replaying a recorded match log and diffing the WS-payload signature pre-vs-post.

---

## 7. Risk notes per field beyond audit's LOW-risk classification

| Field | Additional risk surfaced by this analysis | Mitigation |
|---|---|---|
| `score`, `wickets`, `run_rate`, `target` | SB.set may reject due to consensus tracker, but SM today does NOT consult that consensus on accept. Post-migration, SM-side accepts that SB rejects become silent (logged as `sb_accepted=false`). This is a behavioural change: SM `score` will report `None` (or stale value) instead of the rejected new value. | Telemetry surfaces every reject; analyzer monitors. If `sb_accepted=false` rate climbs, Composer 2 / future agent investigates. The original SM-internal accept was a parallel-state bug; SB-rejection-visible-to-SM is the correct behavior. |
| `target` | `Scoreboard.set("target", v, frame)` returns False with `log.warn` in innings 1. SM today writes target into its own `self.target` regardless of innings. Post-migration, SM.target in innings 1 stays `None` (correct — there is no target in innings 1). | `_accept_update`'s existing gate `if card.get("broadcast_target") and not self.target` continues to fire only when SM-side `self.target` is None — but with the property reading SB, this gate now reads SB's None, which is correct. Verify via test. |
| `batting_team` | Direct attribute write to `Scoreboard.batting_team`; bypasses any SB-side setter validation (there isn't one today). Future SB hardening to validate batting_team writes would need to add a setter. | Mark as known-future-work in backlog. Today's contract is direct attribute access, which matches existing pipeline pattern. |
| `innings` | SM's `self.mode = "COLD_START"` write at L1248 (in SM's `set_innings_2`) MUST stay — `mode` is SM-only and the cold-start re-entry logic depends on it. Only the `self.innings = 2` write becomes a no-op. | Step 3 explicitly preserves the mode write; only the innings line is removed. |
| `bat*_runs/balls`, `bowler_*` | Setter is no-op + telemetry. If a callsite was relying on the setter side-effect (it shouldn't — these are denormalized caches), the bug becomes a silent miss. | Composer 2 grep audit: every `self.bat*_runs = X` and `self.bowler_*_X = Y` write site must be reviewed to confirm the corresponding `Scoreboard.update_batter` / `update_bowler` is also called nearby. If not, that's a pre-existing pipeline bug to flag separately, NOT a migration regression. |
| `fow_list`, `extras_log` | `list[dict]` returns a copy or a reference? **Decision: return a fresh list copy each time** (`list(self.scoreboard.fall_of_wickets or [])`). Mutating the returned list does not mutate SB. | This is stricter than today's behavior (today's `self.fow_list` was mutable and shared). If any callsite mutates `sm.fow_list` to add an entry, it would have been broken pre-migration too (SM.fow_list was already a denormalized snapshot). Composer 2 verifies no caller mutates the returned list. |
| `bowler_name` divergence | Telemetry-only. Risk: log volume in steady-state if signature changes too often (e.g. on every frame). | Use `_last_divergence_sig` rate-limit pattern from `[WS-PROJECTION-GAP]` (~L4849). Emit only on signature change. Worst case: ~1 log per consensus transition (rare). |

---

## 8. New scoreboard methods needed

**None.** Every accessor already exists:

- `Scoreboard.set(field, value, frame)` for score / wickets / run_rate / target.
- `Scoreboard.batting_team` (top-level attr) — direct read/write.
- `Scoreboard.current_innings` (top-level attr) — direct read.
- `Scoreboard.batting_card[name]` / `.bowling_card[name]` — direct dict access.
- `Scoreboard.fall_of_wickets` — direct list access.
- `Scoreboard.extras` — direct dict access.
- `Scoreboard._inn` (property) — for `target` and other innings-keyed reads.

The contract uses public APIs where they exist (`.set()`, `.update_batter()`, `.update_bowler()`) and direct attribute/dict access for fields without setters (`batting_team`, `current_innings`, `batting_card`, `bowling_card`, `fall_of_wickets`, `extras`).

---

## 9. Validation checklist (post-implementation)

Composer 2 confirms before opening the PR:

- [ ] All 17 fields have property + (where applicable) setter as specified
- [ ] `_clear_per_innings_sm_surface` field clears removed for migrated fields; non-migrated fields (`overs`, `bat1_name`, `bat2_name`, etc.) retained
- [ ] `_accept_update` signature gains `frame: int` (or `frame: FrameInput` if frame-number extraction is non-trivial); all callers updated
- [ ] `self._current_frame` instance variable added and updated in `on_frame`
- [ ] Telemetry emits exactly as specified — `[SM-FEEDER-SYNC]`, `[SM-SHADOW-PARITY]`, `[SM-FEEDER-DIVERGENCE]`
- [ ] Analyzer regex labels added for all 3 tags + 1 `bowler_name` divergence sub-label; Bundle B/C self-test fixture extended
- [ ] `python -m py_compile files/score_manager.py files/test_pipeline.py files/test_recent_fixes.py files/analyze_match_telemetry.py` clean
- [ ] `just test` passes — 623 + ~25 = ~648 PASS / 0 FAIL
- [ ] Path A regression: replay a recorded match log; diff WS payload signature → must be identical

---

## 10. Files touched (final — Composer 2 reference)

| File | Change |
|---|---|
| `files/score_manager.py` | 17 properties + setters added; 17 instance-variable inits removed; `_clear_per_innings_sm_surface` updated; `_accept_update` gets `frame` param + threading; `on_frame` updates `_current_frame` |
| `files/test_pipeline.py` | `build_full_payload` adds `[SM-FEEDER-DIVERGENCE]` divergence-only telemetry for `bowler_name` (Step 6 only) |
| `files/test_recent_fixes.py` | ~25 new tests; `test_analyzer_bundle_bc_signature_report_counts_new_guards` fixture extended with new tags |
| `files/analyze_match_telemetry.py` | 3 new regex labels (`SM_FEEDER_SYNC`, `SM_SHADOW_PARITY`, `SM_FEEDER_DIVERGENCE`); bundle B/C labels added |
| `files/docs/backlog.md` | Item 3 LOW-risk batch shipped record; remaining MEDIUM/HIGH items listed |
| `files/docs/investigations/dual_broadcaster_path_b_migration_contract.md` | (this file — already exists from this design pass) |

**No changes to `files/eyes/scoreboard.py`** — this is a contract preservation guarantee.

---

## 11. Estimated execution

For Composer 2 / equivalent implementer following this contract:

- **Step 1 (denormalized cache properties):** ~30 min
- **Step 2 (per-batter / per-bowler stats properties):** ~45 min
- **Step 3 (`innings` no-op):** ~20 min
- **Step 4 (`score`/`wickets`/`run_rate`/`target` feeder):** ~75 min (frame threading + setter wiring + tests)
- **Step 5 (`batting_team` feeder):** ~25 min
- **Step 6 (`bowler_name` divergence telemetry + analyzer):** ~30 min
- **Test fixture + final regression:** ~30 min

**Total: ~4 hours of focused implementation** (matches audit's "single coherent PR" recommendation; broken into 5-6 reviewable commits per step boundary).

---

This contract is the executable spec. Composer 2 should not need to make architectural decisions; if a question arises that this contract doesn't answer, that's a contract bug to fix here first, not a decision to make ad-hoc during implementation.

---

# Section 12 — Clarifications addendum (2026-04-29)

Five clarifications added after a second review pass. Sections 1-11 above remain authoritative; this addendum only **extends** with concrete details. Where a contradiction exists, this addendum supersedes (one such case found and called out below).

## 12.1 — SB.set() rejection handling: SM-side bookkeeping skip semantics

**Statement:** When `SB.set(field, value, frame)` returns `False` (consensus rejected, validation failed, regression rejected), the SM-side write attempt is treated as **non-occurring** for downstream SM bookkeeping purposes. There is no SM-internal value to roll back (post-migration, SM has no internal copy of the field), and the property continues to return the SB-canonical pre-write value.

**Why this matches Decision B:** Decision B says "SB first, then SM bookkeeping". The follow-up clarification: "SM bookkeeping" in the post-migration world is **just the property read on next access**. Because the property reads SB live, SB's reject = property still returns the old value = downstream SM logic correctly sees the un-accepted state. No explicit skip code is required in `_accept_update` for the four feeder-write fields (`score`, `wickets`, `run_rate`, `target`).

**Concrete shape inside `_accept_update`:**

```python
if card.get("score") is not None:
    self.score = card["score"]   # Setter: calls SB.set; logs sb_accepted=true|false.
                                  # If rejected, SB unchanged; self.score property returns old value.
                                  # No side-effect on subsequent lines below.
if card.get("wickets") is not None:
    self.wickets = card["wickets"]   # Same pattern; independent of score's accept/reject outcome.
```

**Caller-side rejection inspection (when needed):** The Python property-setter API does not expose `SB.set`'s bool return through the assignment statement (`self.score = X` returns `None`, not the SB result). If a future SM code path needs to branch on accept/reject, it must call `self.scoreboard.set(...)` directly:

```python
ok = self.scoreboard.set("score", value, self._current_frame)
if not ok:
    # custom skip logic
    return
```

**For Composer 2:** **No `_accept_update` call site in this PR needs the bool-return path.** Every existing assignment (`self.score = X`, etc.) becomes a property-setter call; the field-by-field independence in `_accept_update` is preserved, and downstream `_handle_warm` reads via property (which returns SB-canonical → correct after reject).

**Constraint preserved:** This semantics matches Decision C ("SM does NOT abort; SM does NOT raise") and Decision B ("SM defers to SB consensus") without requiring new control-flow code.

---

## 12.2 — Test naming convention

**Pattern:** `test_path_b_<field>_<scenario>` (snake_case throughout). Tests live in `files/test_recent_fixes.py` and are appended to the `TESTS` list at module bottom.

**Concrete scenario names** (use exactly these; consistency lets the analyzer / PR review tooling group them):

| Scenario name | Meaning | Required for which step |
|---|---|---|
| `_property_reads_scoreboard` | SM property returns SB's canonical value | Steps 1-5 |
| `_property_returns_none_when_sb_unattached` | `SM(scoreboard=None).<field>` returns `None` (or empty list / 0 per type) | Steps 1-5 |
| `_setter_calls_sb_set_with_telemetry` | Setter invokes `SB.set(field, value, frame)` and emits `[SM-FEEDER-SYNC]` | Step 4, Step 5 |
| `_setter_handles_sb_unattached` | Setter with `self.scoreboard is None` does not raise; logs once | Step 4, Step 5 |
| `_setter_continues_on_sb_reject` | SB.set returns `False`; SM does not raise; telemetry logs `sb_accepted=false`; property returns old value | Step 4, Step 5 |
| `_setter_in_shadow_emits_parity_only` | `shadow=True`; setter does NOT call SB.set; emits `[SM-SHADOW-PARITY]` | Step 4, Step 5 |
| `_setter_is_noop_with_telemetry` | Read-only field; setter is no-op + `[SM-FEEDER-SYNC] note=read_only_now` | Steps 2-3 |
| `_setter_clears_per_innings_surface_no_op` | Verify `_clear_per_innings_sm_surface` no longer touches migrated fields directly (reads through property OK) | Step 1, Step 2, Step 4 |
| `_divergence_telemetry_present_in_source` | Source-level wiring guard checking `[SM-FEEDER-DIVERGENCE]` substring + rate-limit pattern | Step 6 |

**Worked examples (full test names):**

| Step | Field | Test names |
|---|---|---|
| 1 | `fow_list` | `test_path_b_fow_list_property_reads_scoreboard`, `test_path_b_fow_list_property_returns_none_when_sb_unattached` |
| 1 | `innings_extras` | `test_path_b_innings_extras_property_reads_scoreboard`, `test_path_b_innings_extras_property_returns_none_when_sb_unattached` |
| 2 | `bat1_runs` | `test_path_b_bat1_runs_property_reads_scoreboard`, `test_path_b_bat1_runs_setter_is_noop_with_telemetry` |
| 2 | `bowler_runs` | `test_path_b_bowler_runs_property_reads_scoreboard`, `test_path_b_bowler_runs_setter_is_noop_with_telemetry` |
| 3 | `innings` | `test_path_b_innings_property_reads_scoreboard`, `test_path_b_innings_setter_is_noop_with_telemetry`, `test_path_b_innings_setter_clears_per_innings_surface_no_op` |
| 4 | `score` | `test_path_b_score_property_reads_scoreboard`, `test_path_b_score_setter_calls_sb_set_with_telemetry`, `test_path_b_score_setter_handles_sb_unattached`, `test_path_b_score_setter_continues_on_sb_reject`, `test_path_b_score_setter_in_shadow_emits_parity_only` |
| 5 | `batting_team` | `test_path_b_batting_team_property_reads_scoreboard`, `test_path_b_batting_team_setter_calls_sb_set_with_telemetry`, `test_path_b_batting_team_setter_in_shadow_emits_parity_only` |
| 6 | `bowler_name` | `test_path_b_bowler_name_divergence_telemetry_present_in_source`, `test_path_b_bowler_name_divergence_rate_limited_in_source` |

**Naming exception:** the source-level wiring guard tests (Step 6) follow the `_present_in_source` suffix established by Item 1 (`test_path_b_striker_read_sm_canonical_drs_detail_present_in_source`); keep that suffix for consistency.

---

## 12.3 — Step 4 frame-threading specifics

**Contract bug surfaced:** Section 1 Decision E and Section 4 Step 4 referenced `frame.frame_number`. **`FrameInput` has no `frame_number` field.** It has `frame_id: str`. The production pipeline at `test_pipeline.py:9225` builds `FrameInput(frame_id=str(frame_count), ...)` — the integer frame counter is encoded as a string.

**Corrected resolution (supersedes the `frame.frame_number` reference in Decision E and Step 4):**

### 12.3.1 — Frame source at each callsite

| Callsite | Source of `frame` (int) | How to extract |
|---|---|---|
| Production: `test_pipeline.py:9225-9271` (`score_mgr.on_frame(_sm_frame)`) | `frame_count` (the loop integer) is stringified into `_sm_frame.frame_id`. SM converts back. | `int(frame.frame_id)` with `try/except ValueError` fallback |
| Test fixtures: `test_recent_fixes.py:135, 161, 313, 677, 690` (`FrameInput(frame_id=frame_id, ...)`) | Test fixtures pass `frame_id=str(int)` (numeric strings, e.g. `"42"`) | Same `int(frame.frame_id)` |
| Hypothetical future caller passing non-numeric `frame_id` (e.g. `"test_001"`) | No int frame available | Fallback path — see 12.3.2 |

### 12.3.2 — `int(frame.frame_id)` extraction helper

Add a private helper on `ScoreManager`:

```python
def _frame_int(self, frame: FrameInput) -> int:
    """Extract integer frame counter from FrameInput.frame_id.

    Production callers pass `frame_id=str(frame_count)` (numeric).
    Falls back to `_current_frame` if the id is non-numeric (test
    fixtures, future callers).  Updates `_current_frame` so that
    property setters called after `_accept_update` returns can still
    invoke `SB.set(field, value, self._current_frame)` with a sensible
    frame number.
    """
    try:
        n = int(frame.frame_id)
    except (TypeError, ValueError):
        n = self._current_frame
    self._current_frame = n
    return n
```

Called once at the top of `on_frame` (before `_handle_warm` / `_handle_cold_start`). Both paths receive the integer via `_accept_update(card, frame_int)`.

### 12.3.3 — `_accept_update` signature

```python
def _accept_update(self, card: dict, frame: int = 0) -> None:
```

- **Default `frame=0`** so existing tests calling `_accept_update(card)` without the new arg continue to work. The tests that need to verify SB.set frame-keying must pass `frame=N` explicitly.
- **Production callers** (`_handle_warm`, `_handle_cold_start`) **must pass** the int from `self._frame_int(frame)`. Composer 2 audits both call sites; ensure `frame_int` is computed before either branch.

### 12.3.4 — Default behavior when `frame` is `None`

The setter implementation:

```python
@score.setter
def score(self, value):
    if value is None:
        return
    if self.shadow:
        log.info(f"  [SM-SHADOW-PARITY] field=score sm_would_accept={value} "
                 f"sb_value={self._sb_get('score')} ...")
        return
    if self.scoreboard is None:
        log.info("  [SM-FEEDER-SYNC] field=score sb_attached=false")
        return
    frame = self._current_frame  # always int (init=0); never None
    ok = self.scoreboard.set("score", value, frame)
    log.info(f"  [SM-FEEDER-SYNC] field=score value={value} "
             f"sb_accepted={str(ok).lower()}")
```

`self._current_frame` is **always an int** (initialized to `0` in `__init__`, updated by `_frame_int` on every `on_frame` entry). The setter never sees `None` for frame.

**Edge case — assignment outside `on_frame`:** if a caller assigns `sm.score = X` before any `on_frame` has been called, `_current_frame` is `0`. `SB.set("score", X, 0)` is harmless (frame `0` is the cold-start frame; `SB._tracker` accepts the first reading). Document this in test `test_path_b_score_setter_handles_sb_unattached` — if `scoreboard is None`, no SB call; if attached but no frames yet, frame=0 is correct.

### 12.3.5 — `_current_frame` lifetime

| Phase | Value | Where set |
|---|---|---|
| `__init__` | `0` | `self._current_frame: int = 0` after L88 (next to `self.scoreboard = None`) |
| `on_frame(frame)` entry | `int(frame.frame_id)` (or stays at last known if non-numeric) | `self._frame_int(frame)` first line of `on_frame` |
| `set_innings_2`, `_handle_innings_change`, `force_cold_start_recalibration` | **PRESERVED** (not reset) | These are reset paths for SM scalar state; `_current_frame` is a tracking counter, not scalar state. Resetting it would break the next `_accept_update` call's frame argument. |
| `full_reset` | **PRESERVED** | Same reasoning. `full_reset` clears domain state; frame counter is meta-state. |
| `stop()` / `start()` | reset to `0` (because they call `__init__`) | Existing behavior preserved; restart context is cold-start from frame `0` |

**`_current_frame` belongs in the `# Optional Scoreboard reference` block (~L88-89), not in the per-innings surface block.** Confirm in the diff that `_clear_per_innings_sm_surface` does NOT touch it.

---

## 12.4 — Per-step commit boundaries

**Decision:** the PR ships as **3 commits**, not 6. Commit boundaries cluster steps that share semantics; Step 4 stands alone because it introduces the `_accept_update` signature change (Decision E + 12.3 above), which is a discrete diff worth isolating.

### Commit 1 — "SM read-only properties for denormalized cache fields" (Steps 1 + 2 + 3)

**Bundles:** Steps 1 (denormalized cache), 2 (per-batter / per-bowler stats), 3 (`innings` no-op).
**Why bundle:** all three are READ-ONLY-PROPERTY migrations with no signature changes, no frame threading, and identical telemetry shape (`[SM-FEEDER-SYNC] note=read_only_now`). The diff is mechanical (init removal + property/setter add).
**Tests added in this commit:** Steps 1+2+3 → ~15 new tests.
**Files touched:** `files/score_manager.py` (only).
**Reviewability:** ~12 fields, ~30 setter no-ops + ~15 read property additions; reviewer can scan systematically.

### Commit 2 — "SM feeder-write properties for SB-set fields (frame threading)" (Step 4)

**Standalone.** Touches `_accept_update` signature (Decision E), introduces `_frame_int` helper, adds `_current_frame` instance variable, threads frame into `_handle_warm` / `_handle_cold_start` callsites.
**Why standalone:** signature changes and the frame-threading helper are higher review-attention; isolating them lets reviewers confirm the `_handle_warm` / `_handle_cold_start` callsites pass the int correctly without distraction from Commit 1's mechanical changes.
**Tests added in this commit:** Step 4 → ~6 new tests (4 setter scenarios × 1 score field, plus property reads for all 4 fields with the same scenarios collapsed where possible).
**Files touched:** `files/score_manager.py` (only).

### Commit 3 — "SM batting_team feeder + bowler_name divergence telemetry + analyzer" (Steps 5 + 6)

**Bundles:** Steps 5 (`batting_team` direct-attr feeder) and 6 (`bowler_name` divergence telemetry + analyzer label).
**Why bundle:** Step 5 is a tiny diff in `score_manager.py` (one property + one setter, ~25 LOC). Step 6 is in `test_pipeline.py` + `analyze_match_telemetry.py`. The two together represent the "rest of the world" outside `score_manager.py`'s SM-internal-only changes; reviewers see all cross-file changes in one commit.
**Tests added in this commit:** Step 5 → 3 tests; Step 6 → 1 source-test + analyzer fixture line (in `test_analyzer_bundle_bc_signature_report_counts_new_guards`).
**Files touched:** `files/score_manager.py`, `files/test_pipeline.py`, `files/analyze_match_telemetry.py`, `files/test_recent_fixes.py` (analyzer self-test fixture).

### Commit summary

| Commit | Scope | Files | New tests | LOC (rough) |
|---|---|---|---:|---:|
| 1 | Steps 1+2+3 (read-only properties) | `score_manager.py` | 15 | ~120 |
| 2 | Step 4 (feeder-writes + frame threading) | `score_manager.py` | 6 | ~80 |
| 3 | Steps 5+6 (batting_team + bowler_name divergence + analyzer) | `score_manager.py`, `test_pipeline.py`, `analyze_match_telemetry.py`, `test_recent_fixes.py` (fixture) | 4 | ~50 |
| **Total** | — | 4 files | **25** | **~250** |

### What MUST NOT be combined

- Commits 1 and 2 must NOT merge: Commit 2 introduces the signature change to `_accept_update`. Combining would hide the signature delta inside the larger Commit 1 diff.
- Commit 3 must NOT merge into 1 or 2: it's the only commit that touches files outside `score_manager.py`. The cross-file boundary is the review hand-off.

### What CAN be combined (if PR review pressure demands a single squash)

All three can squash into one PR commit titled "Item 3 LOW-risk batch (Path B substrate cutover)" — but the per-commit boundaries above SHOULD be preserved through PR review for reviewability.

---

## 12.5 — Path A regression check format

Path A is the WS-payload assembly contract (`build_full_payload` in `test_pipeline.py:4689-4886`). The Path B LOW-risk batch must not change Path A's output. This section specifies the regression check.

### 12.5.1 — Regression check approach: deterministic snapshot test (NOT log replay)

**Decision:** **Do NOT** attempt log replay for the regression check. Pipeline replay requires LLM calls (Scorer, Storyteller, etc.) which are non-deterministic — even with the same scout reads, two runs produce slightly different outputs. Frame-by-frame replay is unreliable for byte-identical regression.

**Use instead:** a deterministic snapshot test that constructs `Scoreboard` + `ScoreManager` in a known state, calls `build_full_payload(speed_kph=None)`, and asserts the returned dict matches a frozen baseline computed from the same fixture.

### 12.5.2 — `build_full_payload` test entry point

**`build_full_payload` is currently a closure inside `main_loop`** (`test_pipeline.py:4689`, defined inside the `async def main_loop` body). Composer 2's regression test cannot call it directly today.

**Solution (acceptable scope creep for this contract):** in Commit 3, extract `build_full_payload`'s body into a module-level function `_build_full_payload_from_state(scoreboard, score_mgr, speed_kph, _broadcast_cache, ...)` that takes its dependencies as arguments. The closure inside `main_loop` becomes a one-line wrapper. This is a refactor, not a behaviour change — verified by the same regression test asserting pre-vs-post output identity.

**If Composer 2 finds the extraction too invasive** (the closure currently captures ~12 outer-scope variables): fall back to **Option B**: add a hidden `build_full_payload` reference accessible from the test via `pickle`-able state, or skip the snapshot test entirely and rely on `[WS-PROJECTION-GAP]` post-deploy monitoring for regression detection. Document the choice in the PR description.

### 12.5.3 — Fixture: "WS payload signature"

**Definition:** "WS payload signature" = `json.dumps(payload, sort_keys=True, separators=(",", ":"))` of the dict returned by `build_full_payload(speed_kph=None)`. The signature is a deterministic string — substring-comparable, hash-comparable, byte-comparable.

**Fixture content (test setup):**

```python
def _path_b_regression_fixture() -> tuple[Scoreboard, ScoreManager]:
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B", "C", "D"], bowling_squad=["X", "Y"],
        batting_xi=["A", "B", "C", "D"], bowling_xi=["X", "Y"])
    sb.set("score", 87, frame=10)
    sb.set("wickets", 2, frame=10)
    sb.set("overs", 9.4, frame=10)
    sb.set("run_rate", 9.16, frame=10)
    sb.batting_card["A"]["status"] = "batting"
    sb.batting_card["A"]["runs"] = 42
    sb.batting_card["A"]["balls"] = 28
    sb.batting_card["B"]["status"] = "batting"
    sb.batting_card["B"]["runs"] = 31
    sb.batting_card["B"]["balls"] = 22
    sb._inn["striker"] = "A"
    sb._inn["non_striker"] = "B"
    sb._inn["current_bowler"] = "X"
    sb.bowling_card["X"]["runs"] = 38
    sb.bowling_card["X"]["wickets"] = 1
    sb.bowling_card["X"]["overs"] = "2.4"

    sm = ScoreManager(shadow=False)
    sm.scoreboard = sb
    sm.striker = "A"
    sm.non_striker = "B"
    sm.bowler_name = "X"
    return sb, sm
```

This fixture exercises every LOW-risk-batch field plus the `bowler_name` FEEDER-existing path.

### 12.5.4 — Baseline capture (one-time, pre-PR)

**Capture:** before any Commit 1-3 work lands, Composer 2 runs the fixture against the unmodified `build_full_payload` and captures the signature:

```python
sb, sm = _path_b_regression_fixture()
payload = build_full_payload(speed_kph=None)  # via test entry point
baseline_signature = json.dumps(payload, sort_keys=True, separators=(",", ":"))
print(repr(baseline_signature))
```

The captured string is pasted into the test as `_PATH_B_REGRESSION_BASELINE_SIGNATURE = "..."` (committed alongside Commit 3).

### 12.5.5 — Regression test

**Test name:** `test_path_b_low_risk_batch_path_a_regression_signature_match`.

```python
def test_path_b_low_risk_batch_path_a_regression_signature_match() -> None:
    header("Item 3 LOW-risk batch: Path A WS-payload signature unchanged")
    sb, sm = _path_b_regression_fixture()
    payload = _build_full_payload_from_state(sb, sm, speed_kph=None, ...)
    sig = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    check("WS payload signature matches pre-migration baseline",
          sig == _PATH_B_REGRESSION_BASELINE_SIGNATURE,
          f"diff:\n  expected: {_PATH_B_REGRESSION_BASELINE_SIGNATURE[:200]}...\n"
          f"  actual:   {sig[:200]}...")
```

**Acceptance:** the baseline signature must match exactly. If it doesn't, Composer 2 diffs the two JSONs (a tiny script: `json.loads(baseline) vs json.loads(sig)` deep-diff) to identify which field changed and why. Any difference is a Path A regression and must be resolved before the PR ships.

### 12.5.6 — Post-deploy live verification

After the PR lands and runs against a live match (or replays a logged match through the production pipeline):

1. **Monitor `[WS-PROJECTION-GAP]` rate.** The pre-PR rate on `machine-1-2026-04-28.log` is established baseline (run analyzer on that log; record count). Post-PR rate must be `≤ baseline + 5 %` (allow small delta for telemetry-tag-induced changes).
2. **Monitor `[SM-FEEDER-SYNC] sb_accepted=false` rate.** If > 1 % of writes are rejected by SB, that signals SM is producing values SB legitimately rejects (a pipeline-level issue, not a migration regression — but worth flagging to ops). Document the threshold in the analyzer and surface in `report_bundle_bc`.
3. **Compare Path A WS payload against pre-PR DETAIL log lines.** The DETAIL log captures `AFTER_score`, `AFTER_bat1`, `AFTER_striker` etc. Post-PR these values must match what they would have been pre-PR for the same scout-read sequence. Sample-spot-check 5 frames per match-day for the first 3 days post-deploy.

### 12.5.7 — Recommended log for sample-spot-check

**Log:** `files/logs/machine-1-2026-04-28.log` (PBKS vs RR; ~164-min window; rich state-recovery + POISON-RECAL + extras + bowler-rotation events).
**Why this log:** it stresses every dual-broadcaster-relevant code path (state-recovery candidates, POISON-RECAL full_reset, BOWLER-AUTO race, extras log accumulation, FOW upgrades). If any LOW-risk-batch field has a regression that escapes the snapshot test, this log surfaces it.
**Comparison surface:** `DETAIL` log lines (`AFTER_score`, `AFTER_bat1`, `AFTER_striker`, `AFTER_run_rate`, `AFTER_target`, `AFTER_innings`, `AFTER_field`). Frame-by-frame sample at F100, F500, F1000, F2000, F3000, F3700, plus all frames within ±20 of any `[POISON-RECAL]` or `[STATE-RECOVERY-OVERRIDE-CANDIDATE]` event.

---

## 12.6 — Updates to earlier sections (back-references)

Where this addendum supersedes earlier text:

- **Section 1, Decision E (frame-number threading):** the reference to `frame.frame_number` is incorrect. Use `int(frame.frame_id)` via the `_frame_int(frame)` helper specified in 12.3.2.
- **Section 4, Step 4:** the line "update callers (`_handle_warm`, `_handle_cold_start`) to pass `frame.frame_number`" should read "pass `self._frame_int(frame)`".
- **Section 4, Step 4:** the line "updated at top of `on_frame` from `frame.frame_number`" should read "updated at top of `on_frame` from `self._frame_int(frame)` which performs the int-extraction".
- **Section 9, Validation checklist:** add bullet "`_current_frame` initialized in `__init__` and updated at top of `on_frame`; `_frame_int` helper present; `_accept_update` accepts `frame: int = 0` argument".
- **Section 11, Estimated execution:** Step 4 estimate stays at ~75 min; the `_frame_int` helper is ~10 LOC (tiny), the regression-test entry-point extraction in 12.5.2 may add 30-45 min if the closure-extraction is taken — total now ~4-4.5 hours.

These back-references are clarifications only; the underlying decisions (read-through, SB-first, no-raise-on-failure, shadow-mode parity telemetry) are unchanged.
