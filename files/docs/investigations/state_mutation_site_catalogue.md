# State-mutation site catalogue

**Status.** C9 deliverable, post-C8 brief reframe (see `dckkr_20260521_cc_investigation_brief.md` §0).
**Date.** 2026-05-21
**Author.** J110 via Claude Code
**Scope.** Pure observability of the system surface. **No fixes proposed.** Per C7 memo §12.3, this catalogue is the static-analysis pivot after five empirical falsifications in the B-η investigation chain.

---

## 1. Purpose and methodology

The B-η investigation chain produced five empirical falsifications (see C7 memo §11-§13). The defect-class signature is **temporal / async coupling** — interactions between consensus-tracker confirmation across UDP-stream-frozen windows, Scout 429-retry ordering, and `_handle_warm`'s streak-gate state — not a single localizable code site.

The strategy pivot at C7 §12.3 calls for a static catalogue of every write site for the five primitive fields (`score`, `wickets`, `overs`, batter identities, bowler identity), classified on four dimensions:

1. **Mutation target** — which underlying state (`sm.score`, `sb._inn["score"]`, `sb.batting_card[name]["runs"]`, etc.)
2. **Gate protection** — which validation gates fire before the write; which sites bypass which gates
3. **Invocation pattern** — sync inline, async via callback, external-event-driven
4. **Source of authority** — extractor reading, SM derivation, broadcast indicator, scout retry-buffer drain, cached restore, etc.

The output is the table in §2-§6 below. §7 identifies gate-bypass / invariant-violation classes — the candidate temporal-coupling defect sites. §8 names the next move.

### 1.1 Methodology limitations to surface up front

- **Catalogue is exhaustive for the three primary files** (`score_manager.py`, `test_pipeline.py`, `eyes/scoreboard.py`) but may miss writes via reflection / dynamic attribute setting. None observed in the grep pass.
- **Five-primitive scope only.** Auxiliary state (`self.frames_since_event`, `self.last_cold_start_verdict_implausible`, etc.) is not enumerated.
- **Classification calls some sites that take multiple values in one assignment** (e.g., `_set_slot_pair` writes both `self.striker` and `self.non` in one call) as single sites with multi-target mutation.
- **Test fixtures and `.bak*` files are excluded** — production code only.
- **Read-only or coercion sites** (e.g., `self.score = int(self.score)` at lines 2959-2960 — type coercion, not state advance) are listed but flagged as `coerce` not `mutate`.

---

## 2. Catalogue — `score` field

| # | Site | Mutation target | Gate protection | Invocation pattern | Source of authority |
|---|---|---|---|---|---|
| S01 | `score_manager.py:1170` | `sb.set("score", iv, frame)` → `sb._inn["score"]` via tracker | `sb.set` runs T20 ceiling (320) + per-update jump guard (Δ≤100) + chase ceiling (target+4) + tracker consensus (`self._tracker.update`) | sync inline within `_handle_warm` cadence | SM-derived (post-`_apply_event` reconciliation) |
| S02 | `score_manager.py:1397` | `self.score = None` | none — reset path | sync inline within `_reset` | reset / innings transition |
| S03 | `score_manager.py:2660` | `self.score = cached.get("score")` | none — direct attribute assign | sync inline within `hot_resume_from_cache` | match-state cache (`files/match_state_cache.json`) |
| S04 | `score_manager.py:2744` | `self.score = card.get("score")` | upstream `_accept_initial` cricket-rules check (line 2595) | sync inline within `_accept_initial` (cold-start exit) | extractor reading (SCOREBOARD frame) |
| S05 | `score_manager.py:2959-2960` | `self.score = int(self.score)` / `= 0` | none — type coercion, not advance | sync inline | type-safety guard |
| S06 | `score_manager.py:4031` | `self.score = card["score"]` | `_accept_update`'s upstream `_handle_warm` runs streak gate (line 3061) + cricket-rules validate_diff (line 2595 reused) | sync inline within `_accept_update` (warm path) | extractor reading + `_infer_event` derivation |
| S07 | `test_pipeline.py:3620` | `scoreboard._inn["score"] = int(cand["score"])` — **direct dict write** | **NONE — bypasses sb.set entirely**; only protected by the upstream `STATE_RECOVERY_PHASE_2_ENABLED` flag check + Phase-1 consensus | sync inline within `_apply_state_recovery_phase_2` | Phase-2 state-recovery aggregator consensus |
| S08 | `test_pipeline.py:4658` | `sb.set("score", _proposed_score, frame)` | sb.set's full guard chain (S01) | sync inline within `commit_decision` (main pipeline loop) | scorer decisions[]'s `score_update` field |
| S09 | `test_pipeline.py:8986` | `sb.set("score", _cu_si, frame_count)` | sb.set's full guard chain | sync inline within the catch-up extractor branch | catch-up Scout response after `OPEN-SCOUT-LOOP` resume |
| S10 | `test_pipeline.py:10941` | `scoreboard._inn["score"] = None` — **direct dict write** | **NONE — bypasses sb.set entirely** | sync inline within `[POISON-RECAL]` consensus trigger | poison-recal forced reset (≥N consecutive POISON reads) |
| S11 | `score_manager.py:2218-2219` | (read only — assignment to local `_cand_score`) | n/a | n/a | not a mutation site (false positive of grep pattern) |

**Score-write site count (real mutations): 9 sites. Sites that bypass `sb.set`'s tracker consensus: S07, S10.**

---

## 3. Catalogue — `wickets` field

| # | Site | Mutation target | Gate protection | Invocation pattern | Source of authority |
|---|---|---|---|---|---|
| W01 | `score_manager.py:1222` | `sb.set("wickets", iv, frame)` → `sb._inn["wickets"]` via tracker | `sb.set` runs 0-10 ceiling + per-update +1 jump guard + all-out lock + regression-3-consensus path + tracker consensus | sync inline within `_handle_warm` | SM-derived |
| W02 | `score_manager.py:1398` | `self.wickets = None` | none — reset | sync inline within `_reset` | innings transition |
| W03 | `score_manager.py:2661` | `self.wickets = cached.get("wickets")` | none | sync inline within `hot_resume_from_cache` | match-state cache |
| W04 | `score_manager.py:2745` | `self.wickets = card.get("wickets")` | upstream `_accept_initial` cricket-rules check | sync inline within `_accept_initial` (cold-start exit) | extractor reading |
| W05 | `score_manager.py:2962-2963` | `self.wickets = int(...)` / `= 0` | none — coercion | sync inline | type-safety guard |
| W06 | `score_manager.py:4033` | `self.wickets = card["wickets"]` | `_accept_update`'s upstream gates | sync inline within `_accept_update` | extractor + `_infer_event` |
| W07 | `test_pipeline.py:3622` | `scoreboard._inn["wickets"] = int(cand["wickets"])` — **direct dict write** | **NONE — bypasses sb.set**; only Phase-2 flag protection | sync inline within `_apply_state_recovery_phase_2` | Phase-2 state-recovery consensus |
| W08 | `test_pipeline.py:4679` | `sb.set("wickets", wickets_up["to"], frame)` | sb.set's full guard chain | sync inline | scorer decisions[] |
| W09 | `test_pipeline.py:9006` | `sb.set("wickets", _cu_wi, frame_count)` | sb.set's full guard chain | sync inline within catch-up branch | catch-up Scout response |
| W10 | `test_pipeline.py:10942` | `scoreboard._inn["wickets"] = None` — **direct dict write** | **NONE — bypasses sb.set** | sync inline within `[POISON-RECAL]` | poison-recal forced reset |
| W11 | `test_pipeline.py:11759` | `sb.set("wickets", _ewi, frame_count)` | sb.set's full guard chain | sync inline (end-of-over wicket commit hook) | end-of-over reconciliation |
| W12 | `eyes/scoreboard.py:89, :97, :180` | `self.wickets = new_w` (Scoreboard-class wickets, distinct from `_inn["wickets"]`) | per-method | sync inline (constructor + reset) | per-call argument |

**Wickets-write site count (real mutations): 10 sites. Bypass `sb.set`: W07, W10. Distinct Scoreboard-class attribute writes: W12.**

---

## 4. Catalogue — `overs` field

| # | Site | Mutation target | Gate protection | Invocation pattern | Source of authority |
|---|---|---|---|---|---|
| O01 | `score_manager.py:1399` | `self.overs = None` | none — reset | sync inline within `_reset` | innings transition |
| O02 | `score_manager.py:2663` | `self.overs = cached.get("overs")` | none | sync inline within `hot_resume_from_cache` | match-state cache |
| O03 | `score_manager.py:2746` | `self.overs = card.get("overs")` | upstream `_accept_initial` cricket-rules check | sync inline within `_accept_initial` | extractor reading |
| O04 | `score_manager.py:2965-2966` | `self.overs = float(...)` / `= 0.0` | none — coercion | sync inline | type-safety guard |
| O05 | `score_manager.py:4036` | `self.overs = card["overs"]` | `_accept_update`'s upstream gates including streak gate (the gate that fired at f304) | sync inline within `_accept_update` | extractor + `_infer_event` |
| O06 | `test_pipeline.py:3625` | `scoreboard._inn["overs"] = (str-formatted ov)` — **direct dict write** | **NONE — bypasses sb.set** | sync inline within `_apply_state_recovery_phase_2` | Phase-2 state-recovery consensus |
| O07 | `test_pipeline.py:4669` | `sb.set("overs", overs_up["to"], frame)` | sb.set's overs jump guard (Δ ≤ 2 whole overs) + tracker consensus | sync inline | scorer decisions[] |
| O08 | `test_pipeline.py:8998` | `sb.set("overs", _cu_os, frame_count)` | sb.set's overs guards | sync inline within catch-up branch | catch-up Scout response |
| O09 | `test_pipeline.py:10943` | `scoreboard._inn["overs"] = None` — **direct dict write** | **NONE — bypasses sb.set** | sync inline within `[POISON-RECAL]` | poison-recal forced reset |
| O10 | `test_pipeline.py:11750` | `sb.set("overs", _eos, frame_count)` | sb.set's overs guards | sync inline (end-of-over hook) | end-of-over reconciliation |

**Overs-write site count (real mutations): 8 sites. Bypass `sb.set`: O06, O09. The streak gate (the f304 actor) protects S06/O05 but NOT S07/O06/W07 (state-recovery direct dict writes).**

---

## 5. Catalogue — batter identity (`striker`, `non`, `bat1_name`, `bat2_name`)

| # | Site | Mutation target | Gate protection | Invocation pattern | Source of authority |
|---|---|---|---|---|---|
| B01 | `score_manager.py:1402-1408` | `self.bat1_name = None / self.bat2_name = None / self.striker = None / self.non = None` | none — reset | sync inline within `_reset` | innings transition |
| B02 | `score_manager.py:1791` (def) → `:1815` | `_set_slot_pair`: `self.striker, self.non = _s, _ns` | deterministic-rotation override (line 4295-4325) gates broadcast writes; `_set_slot_pair` itself is the post-gate writer | sync inline | varied — see callers |
| B03 | `score_manager.py:2042` | `sb.update_batter(...)` → `sb.batting_card[name]["runs", "balls", "fours", "sixes"]` | per-update delta API; `update_batter_card` has its own per-field guards | sync inline within `_apply_event` | event-driven per-ball credit |
| B04 | `score_manager.py:2080` | `self._set_slot_pair(...)` post-wicket pair-rebind | as B02 | sync inline within `_apply_event`'s wicket branch | event-driven (wicket dispatch) |
| B05 | `score_manager.py:2477, :2494, :2505, :2516, :2621` | `self.striker = None` — guard-triggered clears | varied per-site (cold-start rejection paths) | sync inline | guard rejection (cold-start retry) |
| B06 | `score_manager.py:2697, :2699, :2703, :2707` | `self.bat1_name = / self.bat2_name = / _set_slot_pair(source="hot_resume")` | none in this path | sync inline within `hot_resume_from_cache` | match-state cache |
| B07 | `score_manager.py:2805-2807` | `self.bat1_name = card.get("bat1_name") / .bat2_name = card.get("bat2_name")` | upstream `_accept_initial` cricket-rules + squad-canonical resolver (`9856fd6`) | sync inline within `_accept_initial` (cold-start exit) | extractor + F1 broadcast_striker field |
| B08 | `score_manager.py:2829-2845` | `_set_slot_pair(... source="cold_start_*")` — striker identification at cold-exit | F1 (`437d952`) fixed the `broadcast` → `broadcast_striker` field name | sync inline within `_accept_initial` | F1 path |
| B09 | `score_manager.py:4166-4167, :4169` | `self.bat1_name = card_b1 / .bat2_name = card_b2 / _set_slot_pair(source="warm_update")` | `_accept_update`'s upstream gates + deterministic-rotation override | sync inline within `_accept_update` | extractor reading post-cold-start |
| B10 | `score_manager.py:4191+` | `self.bat1_name = None` (dismissed-batter slot clear) | wicket-dispatch path; canonical-name squad resolver | sync inline within `_apply_wicket_fall_only` | wicket event |
| B11 | Tracker on_lock callbacks (`test_pipeline.py:7211-7234`) | `_set_slot_pair(source="striker_tracker_lock")` | tracker consensus (3-frame striker confirmation) | **async callback** from `ConfidenceTracker.on_lock` | broadcast `>` indicator consensus |

**Batter-identity sites: 11 categories. Mix of sync inline + async on_lock callbacks. The deterministic-rotation override at `score_manager.py:4295-4325` (post-F1) is the standing gate; broadcast writes via B11 are suppressed once `self.striker is not None`.**

---

## 6. Catalogue — bowler identity (`bowler_name` + bowling card)

| # | Site | Mutation target | Gate protection | Invocation pattern | Source of authority |
|---|---|---|---|---|---|
| BW01 | `score_manager.py:1405` | `self.bowler_name = None` | none — reset | sync inline within `_reset` | innings transition |
| BW02 | `score_manager.py:2032` | `sb.update_bowler(...)` → `sb.bowling_card[name]["runs", "balls", "wickets"]` | per-update delta API + F-α-shadow fix (`37f63ad`) | sync inline within `_apply_event` | event-driven per-ball credit |
| BW03 | `score_manager.py:2711` | `self.bowler_name = cached.get("current_bowler")` | none | sync inline within `hot_resume_from_cache` | match-state cache |
| BW04 | `score_manager.py:2809` | `self.bowler_name = card.get("bowler_name")` | `_accept_initial` cricket-rules + squad resolver | sync inline within `_accept_initial` | extractor reading |
| BW05 | `score_manager.py:4051` | `self.bowler_name = card["bowler_name"]` | `_accept_update`'s upstream gates | sync inline within `_accept_update` | extractor reading + bowler-tracker on_lock |
| BW06 | `score_manager.py:5397, :5632, :5708, :5794, :6208, :6289, :6517` | `sb.update_bowler(...)` — multiple absorb/credit/queue-drain paths | varied per-site (F-α-queue at `:5311+` adds Queue B routing) | sync inline within various event handlers | varied (ABSORBED_LEGAL, queue drain, ball commit, post-wicket) |
| BW07 | `score_manager.py:5950` | `self.bowler_name = None` | dispatch loop's intra-frame clear when over rolls over and new bowler observed | sync inline within `_handle_warm`'s over-boundary handler | over-rollover trigger |
| BW08 | `test_pipeline.py:7220+` | `self.bowler_name = ...` via tracker on_lock callback (D2 drain for Queue B) | tracker consensus | **async callback** from `ConfidenceTracker.on_lock` | broadcast bowler-strip consensus |

**Bowler-identity sites: 8 categories. BW02 / BW06 are per-ball credit paths through `sb.update_bowler` (the F-α-shadow site). BW07 (`self.bowler_name = None` at over rollover) is the structural point where bowler attribution transitions — relevant for B-θ over-boundary if/when that returns to the engineering queue.**

---

## 7. Gate-bypass / invariant-violation candidate classes

The catalogue surfaces three distinct gate-bypass patterns. Per C7 §12.3 / §13 the candidates here are **observations, not fixes** — each needs a separate audit before any code-shape decision.

### 7.1 The `_inn[*]` direct-write bypass (sites S07, S10, W07, W10, O06, O09)

**Pattern.** Six sites mutate `scoreboard._inn["score"]`, `..["wickets"]`, `..["overs"]` via direct dict assignment, bypassing `sb.set()`'s tracker consensus + jump guards + cricket-physics checks.

**Authorities.** Two of the three callers gate this bypass:
- S07 / W07 / O06: `_apply_state_recovery_phase_2` — protected by `STATE_RECOVERY_PHASE_2_ENABLED` flag (off by default per `test_pipeline.py:3605`)
- S10 / W10 / O09: `[POISON-RECAL]` forced reset — fires when `_poison_streak_count >= _POISON_RECAL_THRESHOLD`

**Observation.** Both bypass paths are intentional resets, not sneaky writes. Neither directly explains the f304→f318 cascade where SM committed `score=54` despite the streak gate's rejection. **But** the existence of these bypass classes means: any future "tracker said reject but state advanced anyway" symptom should check first whether one of these sites fired. Worth a fourth diagnostic trace tag (`INN-DIRECT-WRITE`) covering all six sites.

### 7.2 The async-callback writes (B11, BW08)

**Pattern.** Two sites mutate identity state via `ConfidenceTracker.on_lock` callbacks fired asynchronously from `test_pipeline.py:7211-7234`. These run outside the main `on_frame` cadence; they can mutate `self.striker / .non / .bowler_name` between SM cadence points.

**Observation.** This is the most direct match for "temporal coupling defect" the C7 §12 pivot named. The on_lock callbacks are **gate-protected at consensus level** (3-frame confirmation) but the **callback firing time is decoupled from the main loop's frame-arrival ordering**. Under Scout 429-retry windows or UDP-stream-frozen sequences, the on_lock could fire at a frame boundary that the streak gate did not anticipate, mutating identity state mid-cadence.

**Not yet evidence of B-η, but the most plausible candidate for further investigation** — gate-protected but temporally decoupled is exactly the signature §12 predicted.

### 7.3 The hot-resume path (S03, W03, O03, B06, BW03)

**Pattern.** Five sites mutate the five primitive fields from `match_state_cache.json` during `hot_resume_from_cache`, with no per-write gate (the cache is treated as authoritative).

**Observation.** Hot-resume runs once at pipeline startup. Not relevant to mid-session f304-class cascades. Listed for completeness; deprioritize for B-η localization.

---

## 8. Identified candidates for the next investigation step

The catalogue surfaces **two** empirically-grounded candidate sites for the next investigation pass, both at §7.2's async-callback class:

1. **`test_pipeline.py:7211-7234` — the `ConfidenceTracker.on_lock` callback bindings.** Specifically the bowler-tracker `on_lock` callback (D2 drain for Queue B per §7.1 of `sm_as_orchestrator_design.md`). The callback fires asynchronously when tracker consensus locks; the lock can fire at any frame boundary. Need to confirm: does the lock ever fire in a window where `_handle_warm`'s streak gate would otherwise reject the proposal?
2. **`ConfidenceTracker` itself in `files/eyes/confidence_tracker.py`** — the consensus state machine. What is the exact confirmation semantic across UDP-stream-frozen + Scout-429-retry windows? Does the tracker treat repeated identical reads from a graphic-overlay frame as confirming reads?

Neither is a fix proposal. Both are **observability targets**: trace tags at the on_lock entry + at the tracker confirmation site would expose the temporal-coupling interactions the C7 §12 pivot named.

**Suggested next move (post-operator-review):** open a follow-up brief at `files/docs/investigations/temporal_coupling_investigation_brief.md` targeting (1) and (2) above, with a §7.2 7-gate audit applied to whatever instrumentation candidates emerge. Do not jump to code-shape design until the temporal-coupling model is empirically grounded.

---

## 9. Catalogue summary (one-line per primitive)

- **score**: 9 mutation sites; 2 bypass `sb.set`; tracker consensus protects 7 of the 9
- **wickets**: 10 mutation sites; 2 bypass `sb.set`; tracker consensus protects 8 of the 10
- **overs**: 8 mutation sites; 2 bypass `sb.set`; tracker consensus protects 6 of the 8 (the streak gate at `score_manager.py:3061` adds an SM-side overs check)
- **batter identity**: 11 categories; 1 async (B11 via on_lock); deterministic-rotation override is the post-cold-start gate
- **bowler identity**: 8 categories; 1 async (BW08 via on_lock); per-ball credit goes through `sb.update_bowler`

Total: **38 distinct mutation sites + 2 async callback bindings**. Across-files: score_manager.py 24, test_pipeline.py 12, eyes/scoreboard.py 2 (plus the `sb.set` / `sb.update_*` writer methods themselves).

---

## 10. What this catalogue is NOT

- **Not a fix proposal.** Per C7 §12.3 / §13 / §0 of the C8 brief reframe — no code shapes proposed.
- **Not a comprehensive enumeration of the full ScoreManager surface.** Auxiliary state (cold-start guards, retry buffers, frame ledger, this_over manager, partnership tracker) is not in this catalogue's scope.
- **Not a temporal-coupling model.** The §7.2 observation that async-callback sites are the candidate temporal-coupling locus is a *hypothesis* drawn from the catalogue; verifying it needs targeted instrumentation (which itself needs §7.2 7-gate audit before landing).
- **Not a regression-detection harness.** The captured-replay scaffold + trace-session assertions remain canonical for that role.

---

## 11. Discipline footnote

This catalogue is itself a §7.2 gate-6 instrument: any future "the defect is at site X" hypothesis can be checked against the table for whether X is a real mutation site, what gates protect it, what the invocation pattern is. The catalogue exists so the **next** investigation pass does not generate a sixth falsification by proposing a fix at a non-mutation site or a site protected by a gate that already does the job.

Six falsifications across one chain would be the signal to retire the methodology entirely. The static catalogue is the discipline's bet that one of the 38 sites holds an empirically-grounded answer; if it doesn't, the next move is broader (e.g., add `files/cricket_rules.py`, `files/eyes/this_over.py`, `files/eyes/confidence_tracker.py` to the catalogue scope before any code change).
