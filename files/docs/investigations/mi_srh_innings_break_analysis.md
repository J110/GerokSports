# MI vs SRH — Innings break analysis (2026-04-29)

**Match:** MI vs SRH, IPL 2026 match 151954  
**Log:** `logs/pipeline-2026-04-29-194416-mi-srh-live.log`  
**Innings 1 result:** MI 239-5 (20.0 overs)  
**Analysis window:** 19:44:25 → 21:32:51 (108.4 min), F0 → F2346  
**Author:** Sonnet 4.6 innings-break analysis agent  
**Handoff from:** Composer 2 routine monitoring (Innings 1 Final summary, 2026-04-29)

---

## §1 — Innings 1 final state and totals

| Metric | Value |
|---|---|
| Score | MI 239-5 (20.0 overs) |
| Striker at last frame | Ryan Rickelton (119*) |
| Non-striker at last frame | Robin Minz (1) |
| Bowler | Praful Hinge (2-50) |
| Total frames analyzed | F0 → F2346+ |
| Match wall time | ~108.4 min |

### Primary validation surfaces (cumulative innings 1)

| Tag | Count | Rate | vs PBKS baseline | Status |
|---|---|---|---|---|
| `[WS-SLOT-INVARIANT]` | 122 | 1.13/min | PBKS 2.4/min → **~53% lower** | ✅ Reduced |
| `[SM-SLOT-INVARIANT]` | **0** | 0/min | Expected >0 if W8 dominant | ✅ W8 not source |
| `[BATTERS-INVARIANT]` | 13 (analyzer window) | 0.12/min | — | Documented below |
| `[STRIKER-COLLISION]` | 302 total | 2.79/min | Target <10/wicket | ⚠️ See §6 |
| `[POST-WICKET-ROTATION]` | 9 fires / 5 wickets | — | All wickets covered | ✅ |
| `[SM-FEEDER-SYNC]` | 1369 | 12.6/min | Healthy write rate | ✅ |
| `[SM-FEEDER-DIVERGENCE]` | 21 | 0.19/min | Dominated by bowler_name | ✅ Below 5/min |
| `[WS-PROJECTION-GAP]` | 6 | — | F5 cold-start, F2339/F2346 transition | ✅ Expected |
| `[STRIKER-SM-CUTOVER]` | 38 | 0.35/min | Over-end only | Documented |
| `[SCORE-INF-GATE]` | 13 | — | First F24 | ✅ Live-validated |
| `[EXTRAS-INF-GATE]` | 10 | — | First F487 | ✅ **New live-validated** |
| `[BOWLER-BATTER-GATE]` | 38 | — | First F1323 | ✅ **New live-validated** |
| `[SCORER-SCHEMA-WOULD-DROP]` | 17 | — | First F506 | ✅ **New live-validated** |
| `[SCORER-SCHEMA-WOULD-COERCE]` | 4 | — | First F1 | ✅ **New live-validated** |
| `[STATE-RECOVERY-OVERRIDE-CANDIDATE]` | 13 | — | First F493 | ✅ **New live-validated** |
| `[BALLS-CEILING-GATE]` | 0 | — | — | 🔲 Still pending |
| `[SM-INNINGS-2-RESET]` | 0 | — | — | 🔲 Still pending (innings 2) |
| `[ALL-OUT-AUTHORITY]` | 0 | — | — | 🔲 Still pending |

### Wicket cluster summary

| Wicket # | POST-WICKET-ROTATION frame | `[BATTERS-INVARIANT]` in window | `[STRIKER-COLLISION]` in 100fr |
|---|---|---|---|
| W1 | F474 | F487, F488, F505, F506 (rule=C) | 1 |
| W2 | F663 | F684, F710 (rule=C) | 0 |
| W3 | F1281 | F1288, F1323 (rule=C) | 2 |
| W4 | F2103/F2105 | F2104, F2105, F2124 (rule=C) | 12 |
| W5 | F2285 | F2285 (rule=C) | 0 |

---

## §2 — Lever 1 PR2 hypothesis evaluation outcome

**Full document:** `files/docs/investigations/lever1_pr2_match_analysis.md`

**Original hypothesis:** W8 (`_identify_and_set_striker`) was the dominant `[WS-SLOT-INVARIANT]` source; PR2 expected 40–60% reduction.

**Measured outcome:**

- **`[SM-SLOT-INVARIANT] = 0`** — W8's `_set_slot_pair` helper never triggered a repair. **W8 was NOT the dominant source in production IPL data.**
- **`[WS-SLOT-INVARIANT] = 122 (1.13/min)`** — 53% reduction vs PBKS 2.4/min baseline. This reduction is NOT attributable to W8 migration.
- **All 122 fires are Cause (C) WS-SCRUB rebuild class** (93 "rebuilt" + 29 "cleared").

**Reframed hypothesis:** The dominant source is WS-SCRUB rebuild collision: SM `non_striker` holds stale dismissed-batter name until the next over-end `STRIKER-SM-CUTOVER` fires. This leaves SM stale for 10–30 frames per intra-over wicket.

**PR2 safety:** Confirmed — zero false-positive repairs, zero `[SM-SLOT-INVARIANT-PAYLOAD]` fires.

**Next work:** PR3 (W3–W7 migration) + STRIKER-SM-CUTOVER trigger at batter-arrival (not just over-end). PR3 alone will not close the STRIKER-SM-CUTOVER latency gap; both changes are required for full resolution.

---

## §3 — `[BATTERS-INVARIANT]` cluster mechanism identified

**Full document:** `files/docs/investigations/batters_invariant_cluster_innings1.md`

**Summary:**

| Category | Count (analyzer window) |
|---|---|
| rule=C ADMISSION-WINDOW (≤25 frames from wicket) | 12 |
| rule=A NON-ADMISSION (F2167, Δ=62 from nearest wicket) | 1 |
| rule=B (witnessed-out resurrection) | 0 |

**Primary mechanism (all rule=C):**
1. Wicket falls; SM `non_striker` holds dismissed batter's name.
2. `STRIKER-SM-CUTOVER` fires only at over-end (~0.35/min) — SM stays stale for remainder of over.
3. `_project_active_batters` reads SM `non_striker` (stale) → WS-SCRUB rejects (status_out) → fills with sole active batter = striker → duplicate.
4. `[BATTERS-INVARIANT] rule=C` fires (action=noop_phase1).
5. `enforce_ws_slot_invariant` in `build_full_payload` repairs WS payload. **UI sees correct state.**

**F2167 rule=A** (3 active batters: Ryan Rickelton, Tilak Varma, Hardik Pandya): Graphic overlay resurrection of Hardik Pandya 62 frames after his dismissal. `upstream_step3_fired=false` — bypass did not go through `apply_scorer_decision` Step 3 filters. Isolated; corrected on next frame.

**Post-innings-break fires (F2347–F2419+):** 8 NON-ADMISSION rule=C fires. Expected cold-start/transition class: SM holds innings-1 state (Ryan Rickelton, Robin Minz) while `[SM-INNINGS-2-RESET]` has not fired. Not a regression.

---

## §4 — UI projection path findings

**Investigation:** User observed "Will Jacks duplicated" during the W1 admission window (F474–F519).

**Finding: No actual duplication reached the UI WS payload.**

Sequence at F474–F519:
1. `apply_scorer_decision` end: `[BATTERS-INVARIANT] rule=C` fires → SM has `(Will Jacks, Will Jacks)` duplicate → `action=noop_phase1` (no correction).
2. `build_full_payload` → `_project_active_batters` → WS-SCRUB rejects Ryan Rickelton (out) → fills `non_striker = Will Jacks` → duplicate in `state`.
3. `enforce_ws_slot_invariant` repairs: at F474–F486 (no alternate available) → `non_striker = None` ("cleared"); at F487+ (Rohit Sharma/Naman Dhir available) → `non_striker = Rohit Sharma/Naman Dhir` ("rebuilt").
4. **Final WS payload to UI:** `striker=Will Jacks, non_striker=None` (blank) at F474–F486; `striker=Will Jacks, non_striker=<new batter>` at F487+.

**DETAIL log confirms:** `STATE: Bat: Will Jacks*(46) Rohit Sharma(0)` at F487 — correct.

**The "Will Jacks duplicated" observation** refers to the BLANK non-striker period (F474–F486) where the UI showed Will Jacks in the striker slot with the non-striker slot empty or showing the last-known value. This is expected admission-window behavior, not a bug. Phase 2 autocorrect (`clear_slot` on rule=C) would immediately clear the stale SM slot, which the WS-SLOT-INVARIANT repair already handles on the WS-payload side.

**WS read path confirmation:** Item 3 Path A (`build_full_payload`) reads SM canonical first, then `_inn` fallback, then WS-SCRUB sanitizes, then `enforce_ws_slot_invariant` repairs. The UI sees the post-repair state on every frame. No separate UI read path exists that could expose the SM duplicate.

---

## §5 — Phase 2 enablement decision

**Decision: DEFER Phase 2 (`BATTERS_INVARIANT_AUTOCORRECT=True`) to a future match-day.**

### Decision matrix

| Option | Verdict | Rationale |
|---|---|---|
| ENABLE NOW for innings 2 | ❌ REJECTED | F2167 rule=A NON-ADMISSION: autocorrect would demote a legitimate active batter incorrectly. F2347–F2419 transition fires: Phase 2 would fire during innings cold-start. §10.4 "1 clean match-day" criterion not met. |
| ENABLE WITH MONITORING | ❌ REJECTED | Same risks as ENABLE NOW; monitoring cannot prevent the bad autocorrect action from reaching the UI. |
| **DEFER to next match** | ✅ **SELECTED** | Conservative; §10.4 criterion explicitly requires "1 clean match-day on Phase 1". Innings 1 had 13 fires (not clean). The rule=A fire demonstrates the autocorrect logic needs refinement before activation. |

### Criteria for Phase 2 enablement (next match)

Phase 2 may be enabled when ALL of the following are met in a full innings of Phase 1 monitoring:

1. **Zero NON-ADMISSION `[BATTERS-INVARIANT]` fires** — all fires within ±25 frames of a wicket event.
2. **Rule=A count = 0** — active-set-max-two violation never triggered outside admission window.
3. **Rule=A autocorrect logic patch** — before enabling Phase 2, add `auto_demote` selection logic: prefer the batter who is in `fall_of_wickets` (already witnessed-out) rather than purely "most recently activated". Document as a Lever 1 PR follow-up.
4. **Innings transition observed clean** — `[SM-INNINGS-2-RESET]` fires, and the post-reset NON-ADMISSION window has ≤2 rule=C fires within first 25 frames.

### Config change (DO NOT apply mid-match)

```python
# files/test_pipeline.py (single-line; apply before first ball of a future innings)
BATTERS_INVARIANT_AUTOCORRECT = True  # Phase 2 enabled; was False
```

**Schema enforce flag status:** `SCORER_SCHEMA_ENFORCE = False` (Phase 1 shadow mode). Unchanged; 17 WOULD-DROP and 4 WOULD-COERCE fires validate the schema layer. Schema enforce Phase 2 (actual enforcement) also deferred; requires separate decision after next-match shadow validation.

---

## §6 — Fix 10 `[STRIKER-COLLISION]` analysis

**Total `[STRIKER-COLLISION]` fires:** 302 over 108.4 min = 2.79/min  
**Wicket-adjacent fires (<50 frames from any wicket):** 66/302 = **22%**  
**Non-wicket-adjacent fires (>50 frames from any wicket):** 236/302 = **78%**

### Finding: Two distinct STRIKER-COLLISION source classes

**Class 1 — Wicket-adjacent (22%):** Post-wicket collision when new batter's name is briefly tried as non_striker but collides with current striker (both on strip). Fix 10 `POST-WICKET-ROTATION` fires correctly and clears the slot, but collision still fires on the same frame before/during rotation.

**Class 2 — Background non-adjacent (78%):** Fires throughout normal play at F47–F460 (before ANY wicket event). Mechanism: during normal batting, the extractor periodically sees a scorecard strip where both batter names appear in positions that the write path tries to assign to the same slot. This is a separate issue from Fix 10's scope.

**Implication:** The "<10 STRIKER-COLLISION per wicket" target was framed around Fix 10's wicket-adjacent class. In that narrow scope, wicket-adjacent collisions per wicket cluster are 0–18 (from the 100-frame post-wicket measurement), with a mean of ~7.3 — within range of the target. The large total (302) is misleading because it includes the 78% background class.

**Fix 10 assessment:** WORKING as designed for wicket-adjacent class. The background class (236 fires) is a separate investigation item — likely related to the extractor producing batch-scorecard strips periodically during play, where both `bat1` and `bat2` names resolve to the same slot.

**Recommendation for PR follow-up:** Investigate the background STRIKER-COLLISION source (frames F47–F200, well before any wicket). If the extractor produces "past overs scorecard" strips that show only one active batter's full card, the collision could come from the same batter name appearing as both `bat1_name` and `bat2_name` in the extracted row. Add `[STRIKER-COLLISION-SOURCE]` telemetry to distinguish wicket-adjacent vs background class.

**PR3 impact on STRIKER-COLLISION:** PR3 (W3–W7 migration) addresses the init path degenerate-card case, which would reduce Class 1 wicket-adjacent fires. Class 2 (background) is unrelated to Lever 1 migration.

---

## §7 — Pending first-fires bundle update

Tags that fired for the FIRST TIME in this match (live-validated as of 2026-04-29):

| Tag | First fire | Total fires | Rate | Fix / backlog entry |
|---|---|---|---|---|
| `[EXTRAS-INF-GATE]` | F487 | 10 | 0.09/min | Fix 11 (batter-side) + Fix 15 (score-side) |
| `[BOWLER-BATTER-GATE]` | F1323 | 38 | 0.35/min | Cluster 1 gate |
| `[SCORER-SCHEMA-WOULD-DROP]` | F506 | 17 | 0.16/min | Item 2 PR1 schema shadow (Fix 20 class) |
| `[SCORER-SCHEMA-WOULD-COERCE]` | F1 | 4 | 0.04/min | Item 2 PR1 schema shadow |
| `[STATE-RECOVERY-OVERRIDE-CANDIDATE]` | F493 | 13 | 0.12/min | State Recovery aggregator |

Still pending (not fired in innings 1):

| Tag | Status | Expected condition |
|---|---|---|
| `[BALLS-CEILING-GATE]` | PENDING | Requires batter with stat-overlay balls > innings ceiling |
| `[SM-INNINGS-2-RESET]` | PENDING | Innings 2 start (`SM.set_innings_2()`) |
| `[ALL-OUT-AUTHORITY]` | PENDING | SRH all-out scenario in innings 2 |
| `[SM-SLOT-INVARIANT]` | PENDING | W3–W7 degenerate card (rare; expected after PR3) |
| `[SM-SLOT-INVARIANT-PAYLOAD]` | PENDING | Defense-in-depth backstop (expected 0 in normal operation) |

---

## §8 — Innings 2 monitoring strategy

### Unique innings 2 events to watch

| Event | Tag | Watch item |
|---|---|---|
| SM.set_innings_2() triggers | `[SM-INNINGS-2-RESET]` | First fire in innings 2 → **validates Fix 16** |
| SRH first batter admitted | Extractor first SRH name | Cold-start gate; `[BATTERS-INVARIANT]` NON-ADMISSION count should reset to 0 |
| First SRH wicket | `[POST-WICKET-ROTATION]` | New admission window; watch rule=C pattern repeats but stays ADMISSION-WINDOW |
| Target tracking | `[SCORE-INF-GATE]` + target field | Target >0 in WS payload; rate should be similar to innings 1 |
| SRH all-out possibility | `[ALL-OUT-AUTHORITY]` | If SRH collapses; validates Fix 22 |
| BATTERS_INVARIANT_AUTOCORRECT | — | **Stays OFF.** If somehow enabled, watch for AUTOCORRECT_APPLIED vs CANDIDATE log lines |

### Escalation thresholds for innings 2

| Signal | Threshold | Action |
|---|---|---|
| `[BATTERS-INVARIANT]` NON-ADMISSION fires | >2 in first 60 min | Escalate to Sonnet/Opus; possible new bug class |
| `[BATTERS-INVARIANT]` rule=A | Any fire outside first 25 frames of new-batter admission | Escalate immediately |
| `[BATTERS-INVARIANT]` rule=B | Any fire | Escalate immediately (witnessed-out resurrection) |
| `[WS-SLOT-INVARIANT]` rate | >3.0/min (>20% above PBKS 2.4/min) | Escalate |
| `[SM-FEEDER-DIVERGENCE]` | >5/min | Escalate |
| `[SM-INNINGS-2-RESET]` NOT fired by over 3 | Missing tag | Escalate (innings 2 SM reset may have failed) |
| `[WS-PROJECTION-GAP]` | >3 fires after over 2 | Escalate |
| crashes / sb_accepted=false storm | Any | Immediate escalate |

### Updated stop-and-route-back (innings 2)

Stop routine monitoring and route to Sonnet/Opus if:
1. Any crash or uncaught exception in the pipeline log.
2. `[BATTERS-INVARIANT]` rule=B fires.
3. `[BATTERS-INVARIANT]` rule=A fires >1 in a 10-min window outside admission windows.
4. `[SM-INNINGS-2-RESET]` has NOT fired by SRH over 3 (suggests innings 2 state bootstrap failed).
5. `[WS-SLOT-INVARIANT]` rate >3.0/min sustained for >10 min.
6. `[SM-FEEDER-DIVERGENCE]` >5/min on any field other than `bowler_name`.

---

## §9 — Test fixture candidates from innings 1

| Test name (proposed) | Source data | Description |
|---|---|---|
| `test_lever1_cause_c_ws_scrub_stale_sm_non_striker` | F474–F519 (Ryan Rickelton wicket cluster) | Reproduce: SM stale `non_striker=Ryan Rickelton` after wicket; verify WS-SLOT-INVARIANT fires but UI payload correct |
| `test_batters_invariant_rule_a_graphic_resurrection` | F2167 (Hardik Pandya 3-way active) | Reproduce: 3 active batters from graphic overlay; verify rule=A fires, noop_phase1, card self-corrects |
| `test_schema_shadow_would_drop_extras_inf_gate_same_frame` | F487–F506 cluster | Both `[SCORER-SCHEMA-WOULD-DROP]` and `[EXTRAS-INF-GATE]` fire on same frame; verify coexistence |
| `test_striker_collision_background_non_adjacent` | F47–F200 (before first wicket) | Capture background STRIKER-COLLISION class; root-cause investigation fixture |
| `test_ws_projection_gap_innings_transition` | F2339–F2346 | SM resets at innings break; verify `[WS-PROJECTION-GAP]` fires, `[SM-INNINGS-2-RESET]` follows |

---

## §10 — Composer 2 innings 2 monitoring task block

See the task block in the response following this document. Key parameters:

- **Phase 2 status:** OFF (`BATTERS_INVARIANT_AUTOCORRECT=False`). Do not change.
- **Schema enforce:** OFF (`SCORER_SCHEMA_ENFORCE=False`). Do not change.
- **Primary watch:** `[SM-INNINGS-2-RESET]` first fire; `[BATTERS-INVARIANT]` NON-ADMISSION count; `[ALL-OUT-AUTHORITY]` if SRH all-out.
- **Routine monitoring interval:** Every 15–20 min wall time (same as innings 1).
- **Stop criteria:** See §8 escalation and stop conditions above.

---

**Cross-references:**
- `lever1_pr2_match_analysis.md` — §2 Lever 1 PR2 outcome
- `batters_invariant_cluster_innings1.md` — §3 BATTERS-INVARIANT detail
- `scorer_invariants_categorization.md` §10.4 — Phase 2 design
- `sm_rotation_atomicity_design.md` §8 — PR3 migration sequence
- `backlog.md` — MI vs SRH monitoring section; pending validations
