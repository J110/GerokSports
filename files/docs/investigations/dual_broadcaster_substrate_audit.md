# Dual-broadcaster substrate audit (2026-04-29)

Audit-only companion to **Item 3 (Dual-broadcaster Path B)**. Maps every instance field on `ScoreManager` (SM, `files/score_manager.py`) and `Scoreboard` (SB, `files/eyes/scoreboard.py`), categorizes each overlapping field, and gives Path B migration recommendations with risk + scope estimates.

**Path A status (already shipped, baseline for this audit):** `build_full_payload` (`files/test_pipeline.py:4689-…`) builds the WS payload starting from `scoreboard.get_broadcast_state()` (SB-canonical for score / wickets / overs / run_rate / target / batting_card / bowling_card / fall_of_wickets / this_over / over_history / extras), then **writes through SM values** for `striker` / `non_striker` (via `_project_active_batters`) and `current_bowler` (via `score_mgr.bowler_name`). Path A is NOT removed by Path B; it stays as the WS-payload assembly contract while Path B converts SM-internal parallel state into either FEEDERs or removes it.

**Path A also has a PROJECTION-GAP diagnostic (~L4815-4886)** that compares SM-vs-SB for the three already-bridged fields and emits `[WS-PROJECTION-GAP]` on signature change. This is the existing telemetry surface for divergence; Path B should preserve it (it remains useful as a regression detector).

---

## 1. ScoreManager field inventory (62 fields)

| Field | Type | Purpose | Mutation sites (representative) | Read sites | SB equivalent | Category |
|---|---|---|---|---|---|---|
| `shadow` | bool | Mode flag — when True, SM does not own WS payload | `__init__` | many | — | **SM-ONLY** (mode flag) |
| `scoreboard` | Scoreboard \| None | Back-reference for canonicalization | `__init__`, attached at startup | `_canonicalize_name` | — | **SM-ONLY** (back-ref) |
| `mode` | str | `"COLD_START"` / `"WARM"` | `_handle_cold_start`, `_handle_warm`, `force_cold_start_recalibration`, `set_innings_2`, `full_reset` | many | — | **SM-ONLY** (consensus state) |
| `cold_candidate` | dict\|None | Pending cold-start candidate | many | `_handle_cold_start` | — | **SM-ONLY** |
| `cold_candidate_streak` | int | Cold-start consensus counter | many | `_handle_cold_start` | — | **SM-ONLY** |
| `cold_frames` | int | Cold-start frame budget | several | `_handle_cold_start` | — | **SM-ONLY** |
| `COLD_START_CONSENSUS_FRAMES` | int | Threshold | `__init__` | `_handle_cold_start` | — | **SM-ONLY** (constant) |
| `score` | int\|None | Accepted innings score | `_accept_update` (~L1268), `__init__`, `_clear_per_innings_sm_surface`, `set_innings_2` | `_build_payload`, all SM clients | `SB._inn["score"]` (via `Scoreboard.set("score", …)`) | **PARALLEL** |
| `wickets` | int\|None | Accepted innings wickets | `_accept_update` (~L1270), reset paths | `_build_payload` | `SB._inn["wickets"]` | **PARALLEL** |
| `overs` | float\|None | Accepted innings overs | `_accept_update` (~L1272), reset paths | `_build_payload`, `_handle_warm` | `SB._inn["overs"]` | **PARALLEL** |
| `bat1_name` | str\|None | Slot-1 batter name | `_update_batters`, `_handle_innings_change`, `set_innings_2`, `full_reset` | `_build_payload` | derivable from `SB.batting_card[name].status=="batting"` | **PARALLEL** (slot-vs-card mapping) |
| `bat1_runs` | int\|None | Slot-1 runs | `_update_batters` | `_build_payload` | `SB.batting_card[bat1].runs` | **PARALLEL** |
| `bat1_balls` | int\|None | Slot-1 balls | `_update_batters` | `_build_payload` | `SB.batting_card[bat1].balls` | **PARALLEL** |
| `bat2_name` | str\|None | Slot-2 batter name | `_update_batters` | `_build_payload` | derivable | **PARALLEL** |
| `bat2_runs` | int\|None | Slot-2 runs | `_update_batters` | `_build_payload` | `SB.batting_card[bat2].runs` | **PARALLEL** |
| `bat2_balls` | int\|None | Slot-2 balls | `_update_batters` | `_build_payload` | `SB.batting_card[bat2].balls` | **PARALLEL** |
| `bowler_name` | str\|None | Current spell bowler | `_accept_update`, `set_innings_2` | `build_full_payload` (Path A: `state["current_bowler"]=score_mgr.bowler_name`) | `SB._inn["current_bowler"]` | **FEEDER** (SM is canonical for WS, SB also tracks; lockstep needed) |
| `bowler_wickets` | int\|None | Spell wickets | `_accept_update` | `_build_payload` | `SB.bowling_card[name].wickets` | **PARALLEL** |
| `bowler_runs` | int\|None | Spell runs | `_accept_update` | `_build_payload` | `SB.bowling_card[name].runs` | **PARALLEL** |
| `bowler_overs` | float\|None | Spell overs | `_accept_update` | `_build_payload` | `SB.bowling_card[name].overs` | **PARALLEL** |
| `striker` | str\|None | Crease striker | `_update_batters` (auto-rotation), `set_striker`, `set_innings_2`, `full_reset`, `_handle_innings_change` | `_build_payload`, `_canonical_active_slot`, `build_full_payload` (Path A canonical), DETAIL log | `SB._inn["striker"]` (mirrored via `_set_inn_slot_with_sm_mirror`) | **FEEDER (existing)** — already in lockstep via `[STRIKER-SM-CUTOVER]` |
| `non_striker` | str\|None | Crease non-striker | same as striker | same | `SB._inn["non_striker"]` | **FEEDER (existing)** |
| `batting_team` | str\|None | Currently batting team name | `_accept_update` (~L813), `set_innings_2`, `_handle_innings_change` | several | `SB.batting_team` | **PARALLEL** |
| `target` | int\|None | Innings-2 target | `set_innings_2`, `_accept_update` | many | `SB._inn["target"]` (per-innings dict) | **PARALLEL** |
| `venue` | str\|None | Match venue | `_accept_update` (frame.broadcast_venue) | `_build_payload` | — (broadcast cache only) | **SM-ONLY** |
| `match_info` | str\|None | Match-info string | `_accept_update` | `_build_payload` | — | **SM-ONLY** |
| `innings` | int (1\|2) | Current innings | `_handle_innings_change`, `set_innings_2`, `_accept_update` | many | `SB.current_innings` | **PARALLEL** |
| `run_rate` | float\|None | Computed RR | derived, `_accept_update` | `_build_payload` | `SB._inn["run_rate"]` | **PARALLEL** (both compute) |
| `required_run_rate` | float\|None | Computed RRR | derived | `_build_payload` | — | **SM-ONLY** (computed) |
| `balls_remaining` | int\|None | Computed | derived | `_build_payload` | — | **SM-ONLY** (computed) |
| `match_phase` | str\|None | Powerplay/middle/death | derived | `_build_payload` | — | **SM-ONLY** (computed) |
| `bat1_sr` | float\|None | Strike rate | derived | `_build_payload` | — | **SM-ONLY** (computed) |
| `bat2_sr` | float\|None | Strike rate | derived | `_build_payload` | — | **SM-ONLY** (computed) |
| `bowler_economy` | float\|None | Economy | derived | `_build_payload` | — | **SM-ONLY** (computed) |
| `this_over` | list[str] | Token list for current over | `_handle_warm` (~L1821, 1846), over rollover | `_build_payload`, `completed_over` snapshot | `SB.this_over` + `over_mgr.this_over` (third tracker) | **PARALLEL** (3 sources!) |
| `this_over_src` | list[str] | Token sources | same as this_over | same | `over_mgr.this_over_sources` | **PARALLEL** |
| `over_history` | dict[int, list] | Past overs | `_handle_warm`, over rollover | `_build_payload` | `SB.over_history` | **PARALLEL** |
| `completed_over` | list\|None | Last completed over snapshot | over rollover (~L1835) | `_build_payload` | derivable from `SB.over_history` | **PARALLEL** |
| `completed_over_runs` | int\|None | Runs in last completed over | over rollover | `_build_payload` | derivable | **PARALLEL** |
| `partnership_runs` | int | Current partnership runs | `_handle_warm`, wicket reset | `_build_payload` | `SB.current_partnership.runs` + `partnership_tracker` (third source) | **PARALLEL** (3 sources) |
| `partnership_balls` | int | Current partnership balls | same | `_build_payload` | same | **PARALLEL** |
| `partnership_known` | bool | Whether partnership data is reliable post-restart | same | `_build_payload` | — | **SM-ONLY** |
| `fow_list` | list[dict] | SM-side FOW snapshot | `_accept_update` | `_build_payload` | `SB.fall_of_wickets` | **PARALLEL** (SM is denormalized read of SB) |
| `free_hit_next` | bool | Free-hit flag | `_handle_warm` (~L1855, 1859) | `_build_payload` | — | **SM-ONLY** |
| `innings_extras` | int | SM extras counter | `_handle_warm` | `_build_payload` | `SB.extras["total"]` | **PARALLEL** |
| `this_over_extras` | int | Per-over extras | over rollover (~L1845) | `_build_payload` | `SB.extras["this_over"]` | **PARALLEL** |
| `extras_log` | list[dict] | Chronological extras log | `_handle_warm` | `_build_payload` | `SB.extras["log"]` | **PARALLEL** |
| `last_speed` | float\|None | Last delivery speed | `_accept_update` (~L881) | `_build_payload` | `SB.bowler_speeds[name]` (per-bowler list) | **PARALLEL-WITH-PROJECTION** (SM holds `last`, SB holds `per-bowler`) |
| `pending_extra` | dict\|None | Pending extra for resolution | `_handle_warm` | `_try_resolve_pending` | — | **SM-ONLY** |
| `pending_extra_frames` | int | Pending counter | same | same | — | **SM-ONLY** |
| `pending_wicket` | dict\|None | Pending wicket for resolution | `_handle_warm` (~L1781) | same | — | **SM-ONLY** |
| `pending_wicket_frames` | int | Counter | same | same | — | **SM-ONLY** |
| `recent_frames` | list[FrameInput] | Last-5 frame buffer | `on_frame` | `_handle_warm` | — | **SM-ONLY** (consensus history) |
| `last_event` | dict\|None | Last delivery event | `_handle_warm` (~L1076) | `_build_payload` | derivable from `SB.this_over` last token | **PARALLEL-WITH-PROJECTION** |
| `frames_since_event` | int | Counter | many | `_handle_warm` | — | **SM-ONLY** |
| `_stale_reject_count` | int | Stale-frame counter | several | `_handle_warm` | — | **SM-ONLY** |
| `_last_warm_state` | dict\|None | Snapshot at WARM exit | `_snapshot`, reset paths | cold-start re-validation | — | **SM-ONLY** |
| `_deferred_score` | int | Deferred-score-change buffer | `_handle_warm` | resolution | — | **SM-ONLY** |
| `_deferred_frames` | int | Counter | same | same | — | **SM-ONLY** |
| `_overs_regress_streak` | int | Overs-regress consensus | `_handle_warm` (~L937, 972) | `_handle_warm` | — | **SM-ONLY** (consensus) |
| `_overs_regress_from` | float\|None | Regress baseline | same | same | — | **SM-ONLY** |
| `_OVERS_REGRESS_THRESHOLD` | int | Constant | `__init__` | same | — | **SM-ONLY** (constant) |
| `innings_history` | list[dict] | Innings-1 archive on innings-2 boot | `set_innings_2` | end-of-match summary | `SB.innings[1]` (per-innings dict) | **PARALLEL** (SM denormalizes SB) |

### SM-internal totals

| Category | Count | Notes |
|---|---:|---|
| **PARALLEL** | **27** | Migration candidates for Path B |
| **PARALLEL-WITH-PROJECTION** | 2 | Likely retain (SM holds projection / derived form) |
| **FEEDER (existing)** | 3 | `striker`, `non_striker`, `bowler_name` already in lockstep — verify and keep |
| **SM-ONLY** | 30 | Consensus / pending-resolution / cold-start bookkeeping; legitimate SM scope |

---

## 2. Scoreboard field inventory (selected; the 38 production fields most relevant to dual-broadcaster reasoning)

The full Scoreboard field set is ~95 fields including many guard counters. The audit below filters to the ones that overlap with SM or are accessed by Path A WS payload assembly. Internal guard counters (e.g. `_pending_wickets_*`, `_bowler_consensus_inconsistent_streak`, `_xi_rejection_views`) are SB-only by construction and are not enumerated.

| Field | Type | Purpose | SM equivalent | Category |
|---|---|---|---|---|
| `match_format` | str | Format constant | — | SB-ONLY |
| `batting_team` | str\|None | Batting side name | `SM.batting_team` | **PARALLEL** |
| `bowling_team` | str\|None | Bowling side name | — | SB-ONLY |
| `current_innings` | int (1\|2) | Innings | `SM.innings` | **PARALLEL** |
| `match_complete`, `match_end_reason`, `match_result` | bool/str/dict | Terminal state | — | SB-ONLY |
| `batting_card` | dict[name → entry] | Per-batter card (runs, balls, status, fours, sixes, batting_style) | denormalized into `SM.bat1_*` / `bat2_*` | **PARALLEL (SB authoritative)** |
| `bowling_card` | dict[name → entry] | Per-bowler card | denormalized into `SM.bowler_*` for current spell | **PARALLEL (SB authoritative)** |
| `_name_lookup`, `_squad_roles`, `_player_styles` | dicts | Lookup tables | — | SB-ONLY (squad data) |
| `_dismissed_inferred` | bool | Internal flag | — | SB-ONLY |
| `innings` | dict[int → blank] | Per-innings dict (`score`, `wickets`, `overs`, `run_rate`, `target`, `extras` + dynamic `striker`/`non_striker`/`current_bowler`) | mirrored across `SM.score/wickets/overs/run_rate/target/striker/non_striker/bowler_name` | **PARALLEL (SB authoritative for WS via Path A)** |
| `_inn` (property → `innings[current_innings]`) | dict | Live alias | — | SB-ONLY accessor |
| `fall_of_wickets` | list[dict] | FOW list | `SM.fow_list` | **PARALLEL (SB authoritative)** |
| `partnerships` | list[dict] | Completed partnerships | — | SB-ONLY |
| `current_partnership` | dict\|None | Live partnership | mirrored in `SM.partnership_runs/balls/known` | **PARALLEL** |
| `_update_history` | list[dict] | Audit trail | — | SB-ONLY |
| `_tracker` | ConsistentReadTracker | Per-frame consensus | — | SB-ONLY |
| `_dismissed_recovery`, `_dismiss_attempt_count`, `_extractor_batter_names` | dicts/sets | Recovery bookkeeping | — | SB-ONLY |
| `extras` | dict (`wides`, `no_balls`, `byes`, `leg_byes`, `penalties`, `total`, `this_over`, `log`) | Per-innings extras | mirrored into `SM.innings_extras / this_over_extras / extras_log` | **PARALLEL (SB authoritative)** |
| `this_over` | list[str] | Token list | `SM.this_over` + `over_mgr.this_over` | **PARALLEL (3 sources)** |
| `over_history` | dict[int → list] | Past overs | `SM.over_history` | **PARALLEL** |
| `bowler_speeds` | dict[name → list[float]] | Per-bowler speeds | `SM.last_speed` (last only) | **PARALLEL-WITH-PROJECTION** |
| `bowler_type` | dict[name → "fast"/"spin"] | Per-bowler classification | — | SB-ONLY |
| `_last_over_num`, `_bowler_must_change`, `_prev_over_bowler`, `_bowler_locked`, `_bowler_lock_frame` | mixed | Bowler-rotation guard state | — | SB-ONLY (guard counters) |
| `_pending_bowler_name`, `_pending_bowler_count` | str/int | Bowler 3-frame consensus | — | SB-ONLY |
| `_bowler_regress_pending` | dict | Same-bowler regression consensus | — | SB-ONLY |
| `_bowler_consensus_inconsistent_streak` | dict | Fix 17B consensus state | — | SB-ONLY |
| `_pending_wickets_low/_low_count`, `_pending_wickets_high/_high_count` | int | Wickets regression / upward consensus | — | SB-ONLY |
| `_all_out_lock`, `_all_out_lock_frame`, `_all_out_lock_source` | bool/int/str | All-out latch | — | SB-ONLY |
| `_RUNS_REJECT_RELEASE_N`, `_runs_reject_streak` | int/dict | Layer-4 release | — | SB-ONLY |
| `_last_runs_advance`, `_fresh_batter_admission` | dicts | Layer-2/3 reconciler bookkeeping | — | SB-ONLY |
| `_L2_RECONCILER_THRESHOLD`, `_L3_CAP_RESET_THRESHOLD` | int | Constants | — | SB-ONLY |
| `_wickets_confirmed_frames_at_zero` | int | Wicket-seed gate | — | SB-ONLY |
| `_rotation_rejection_count` | dict | Rotation-guard override | — | SB-ONLY |
| `_last_bowler_scout_frame`, `_bowling_card_active_write_frame`, `_bowling_card_active_write_bowler`, `_BOWLER_STALE_FRESH_FRAMES` | mixed | BOWLER-AUTO/BOWLER-STALE state | — | SB-ONLY |
| `_XI_OVERRIDE_N`, `_XI_OVERRIDE_ACTION_N`, `_xi_rejection_views` | mixed | XI-REJECT override | — | SB-ONLY |
| `_last_scout_camera_view` | str\|None | Camera tag | — | SB-ONLY |
| `_innings2_reset_done` | bool | Innings-2 reset latch | — | SB-ONLY |
| `on_fow_upgrade` | callable\|None | Cross-module callback | — | SB-ONLY |

### SB totals (for the dual-broadcaster surface)

| Category | Count | Notes |
|---|---:|---|
| **PARALLEL** (SB is authoritative for WS via Path A) | **13** | Same fields appearing in SM.PARALLEL inventory above; this is the "other half" of the parallel pair |
| **SB-ONLY (guard / counter / lookup)** | ~50 | Consensus state, rotation guards, layer-2/3 reconcilers, XI override etc. — properly SB-internal |

---

## 3. Cross-reference — overlapping field map

The 13 fields in both inventories above (excluding the 3 already-FEEDER fields and 2 already-PROJECTION fields) form the **Path B migration surface**.

| # | SM field(s) | SB field | Read by | Risk class |
|---|---|---|---|---|
| 1 | `SM.score` | `SB._inn["score"]` (via `Scoreboard.set("score", …)`) | WS payload (Path A → SB), SM internal consensus | LOW — Path A already pulls SB; SM read can become `SB._inn.get("score")` |
| 2 | `SM.wickets` | `SB._inn["wickets"]` | WS (Path A → SB), SM internal | LOW |
| 3 | `SM.overs` | `SB._inn["overs"]` | WS (Path A → SB), SM `_handle_warm` (overs-regression consensus) | **MEDIUM** — `_overs_regress_streak` consensus uses `self.overs`; switching read source may mis-time the consensus reset |
| 4 | `SM.bat1_name`, `SM.bat2_name` | `SB.batting_card[*].status=="batting"` derivation | SM `_build_payload`, callers querying slot 1/2 | **MEDIUM** — SM's slot mapping (which "slot" is bat1 vs bat2) is implicit ordering; SB `batting_card` is dict (insertion-ordered but slot semantics undefined) |
| 5 | `SM.bat1_runs/balls`, `SM.bat2_runs/balls` | `SB.batting_card[name].runs/balls` | SM `_build_payload` | LOW — once name mapping resolved (#4), these are direct lookups |
| 6 | `SM.bowler_wickets/runs/overs` | `SB.bowling_card[bowler_name].*` | SM `_build_payload` | LOW |
| 7 | `SM.batting_team` | `SB.batting_team` | many | LOW — same value semantics |
| 8 | `SM.target` | `SB._inn["target"]` | WS, SM | LOW — Path A already uses SB |
| 9 | `SM.innings` | `SB.current_innings` | many | LOW — same value, multiple writers; SM follows SB on innings transition already |
| 10 | `SM.run_rate` | `SB._inn["run_rate"]` | WS (Path A → SB) | LOW — both compute the same formula |
| 11 | `SM.this_over`, `SM.this_over_src`, `SM.over_history`, `SM.completed_over*` | `SB.this_over` + `over_mgr.this_over` (3rd source!) | many | **HIGH** — three trackers; reconciliation surface is large; needs its own audit before migration |
| 12 | `SM.partnership_runs/balls/known` | `SB.current_partnership` (+ external `partnership_tracker`) | WS, SM `_build_payload` | **HIGH** — three sources (SM, SB, external tracker); see backlog notes on partnership reconciliation |
| 13 | `SM.fow_list`, `SM.innings_history` | `SB.fall_of_wickets`, `SB.innings` | WS, SM `_build_payload` | LOW — SM is already a denormalized view; can become a property |
| 14 | `SM.innings_extras`, `SM.this_over_extras`, `SM.extras_log` | `SB.extras["total"/"this_over"/"log"]` | WS, SM `_build_payload` | LOW — same key set; mirror trivially |

---

## 4. Path B migration recommendations per overlapping field

Each entry below specifies the recommended migration shape, blast radius, and validation surface. Estimates assume Path A remains active (WS payload assembly unchanged).

### LOW-risk (12 fields) — straightforward FEEDER conversion

For these, the recommended shape is:

- **Write path:** wherever SM mutates the field, also call the corresponding SB write (or remove SM's internal copy entirely and read from SB).
- **Read path:** SM reads via `getattr(self.scoreboard, "_inn", {}).get("score")` etc.
- **Telemetry:** add `[SM-FEEDER-SYNC]` per-write log on the lockstep sites; emit a divergence log when SM-internal value differs from SB at read time (similar to Item 1 `[STRIKER-READ-SM-CANONICAL]`).

| Field | Migration shape | Lines (est.) | Callsites (est.) | Risk |
|---|---|---:|---:|---|
| `SM.score` | Remove field; `@property score(self): return SB._inn.get("score")` | ~30 | ~25 | LOW |
| `SM.wickets` | Same pattern | ~30 | ~20 | LOW |
| `SM.run_rate` | Same pattern | ~10 | ~5 | LOW |
| `SM.target` | Same pattern | ~15 | ~6 | LOW |
| `SM.batting_team` | Same pattern | ~20 | ~12 | LOW |
| `SM.innings` | Property reading `SB.current_innings`; remove SM writes (already follow SB) | ~25 | ~30 | LOW |
| `SM.bat1_runs/balls`, `bat2_runs/balls` | Property derived from `SB.batting_card[bat1_name]` | ~50 | ~15 | LOW (depends on #4 below) |
| `SM.bowler_wickets/runs/overs` | Property derived from `SB.bowling_card[bowler_name]` | ~30 | ~10 | LOW |
| `SM.fow_list` | Property reading `SB.fall_of_wickets` (with SM-side projection if differs) | ~15 | ~5 | LOW |
| `SM.innings_extras`, `SM.this_over_extras`, `SM.extras_log` | Property reading `SB.extras["total"/"this_over"/"log"]` | ~25 | ~8 | LOW |

**Combined LOW-risk migration: ~250 LOC, ~140 callsites, single coherent PR.**

### MEDIUM-risk (2 fields) — behavioural test gates required

| Field | Concern | Migration shape | Validation gate |
|---|---|---|---|
| `SM.overs` | `_overs_regress_streak` reads `self.overs` to detect regression candidates. Switching to `SB._inn.get("overs")` could change the consensus timing (SB has its own overs-regression consensus too) | Keep `SM.overs` as the SM-internal consensus baseline (read inside `_handle_warm`); add a `[SM-FEEDER-SYNC]` write to SB on accept. SM-external readers (e.g. `_build_payload`) switch to property reading SB | New unit test: `_overs_regress_streak` triggers at the same frame count as today on a fixture set |
| `SM.bat1_name` / `SM.bat2_name` | Slot-1/2 ordering is SM-implicit (auto-rotation order based on swap detection); SB.batting_card is dict-insertion-ordered, no explicit slot | Add SB-side `_active_batters_ordered` derived list (insertion-order with auto-swap mirror); SM properties return that list[0]/[1]. **Or** keep SM as the slot authority and add `[SM-FEEDER-SYNC]` mirror to SB whenever auto-rotation flips slots | Replay `_handle_innings_change` + `set_striker` cases; assert slot ordering equivalent |

**Combined MEDIUM-risk migration: ~150 LOC, dedicated test fixture per field, separate PR per field recommended.**

### HIGH-risk (2 surfaces) — needs its own audit before migration

| Surface | Concern | Pre-migration audit |
|---|---|---|
| `this_over` (SM ↔ SB ↔ over_mgr) | Three trackers; over_mgr has authoritative token list with sources; SB.this_over has token list; SM.this_over is denormalized. Reconciliation rules differ across the three on extras / wickets / placeholders. | New audit doc: enumerate every write to all three; identify the canonical writer for each token kind (legal ball, extra, wicket placeholder, recovery resync) |
| `partnership_*` (SM ↔ SB ↔ partnership_tracker) | Three trackers; backlog already notes reconciliation gaps | New audit doc; align with existing partnership_tracker work |

**Recommendation:** **DO NOT** migrate these in Item 3. Defer to a follow-up "Path C" task. Item 3 should ship LOW-risk migrations (one PR) and stage MEDIUM-risk migrations behind an opt-in flag.

### PARALLEL-WITH-PROJECTION (2 fields) — keep as-is

| Field | Why |
|---|---|
| `SM.last_speed` | SM stores last delivery's speed; SB stores per-bowler list. Different aggregation semantics; both are valid. Document as PROJECTION |
| `SM.last_event` | SM stores structured last delivery event; SB.this_over stores tokens. Different abstraction levels. Document as PROJECTION |

### FEEDER (existing, 3 fields) — verify lockstep, no migration

| Field | Verification |
|---|---|
| `SM.striker` ↔ `SB._inn["striker"]` | `_set_inn_slot_with_sm_mirror` keeps lockstep; Item 1 added DETAIL read migration. **OK.** |
| `SM.non_striker` ↔ `SB._inn["non_striker"]` | Same. **OK.** |
| `SM.bowler_name` ↔ `SB._inn["current_bowler"]` | Path A reads `score_mgr.bowler_name` directly; SB's `current_bowler` may diverge during BOWLER-STALE windows. **VERIFY:** add a `[SM-FEEDER-SYNC]` divergence telemetry tag (similar to Item 1) so Path B tracks lockstep without forcing it |

---

## 5. Risk summary for Item 3 implementation

| Risk class | Count | Recommended PR shape | Reversibility |
|---|---:|---|---|
| LOW (FEEDER conversion via property) | 12 fields | Single PR, ~250 LOC, ~140 callsites; properties + `[SM-FEEDER-SYNC]` writes | Trivial — restore field, remove `@property`, restore field assignments from git history |
| MEDIUM (behavioural-test-gated) | 2 fields | Two separate PRs; one test fixture per field; opt-in flag (`SM_PATH_B_OVERS=true`, `SM_PATH_B_BAT_SLOTS=true`) for one match-day before flip | Reversible via flag |
| HIGH (substrate audit needed first) | 2 surfaces (this_over, partnership) | **DO NOT** include in Item 3. New audit doc per surface | N/A — deferred |
| PARALLEL-WITH-PROJECTION (keep) | 2 fields | No change | N/A |
| FEEDER (existing) | 3 fields | Verify-only; add `[SM-FEEDER-SYNC]` divergence telemetry to `bowler_name` if missing | N/A |
| SM-ONLY (legitimate scope) | 30 fields | No change | N/A |

---

## 6. Recommended Item 3 scope

Given the audit:

1. **In scope for Item 3** — LOW-risk batch (12 fields) + telemetry-only verify pass on the 3 existing FEEDERs. ~250 LOC + ~30 LOC telemetry. Path A unchanged. New tests covering: every property returns the SB value, every write triggers the lockstep `[SM-FEEDER-SYNC]` log, no Path A regression on a synthetic fixture.

2. **Stage behind opt-in flag for next session** — MEDIUM-risk pair (`SM.overs`, `SM.bat1_name`/`bat2_name`). Per-field PRs; ship after one clean match-day on the LOW-risk batch lands.

3. **Out of scope for Item 3** — HIGH-risk pair (`this_over`, `partnership_*`). Each gets its own dedicated audit doc + PR. Backlog entry created at end of Item 3 ship.

4. **Constraint preserved across Item 3** — Path A WS-payload assembly contract stays untouched. `[WS-PROJECTION-GAP]` diagnostic stays as the outer-layer divergence detector. Fix 5 / `[STRIKER-COLLISION]` / `[STRIKER-STATUS-GATE]` defensive guards remain.

---

## Files

- **New:** `files/docs/investigations/dual_broadcaster_substrate_audit.md` (this file)
- **No code changes** in this task. Output feeds Item 3.
