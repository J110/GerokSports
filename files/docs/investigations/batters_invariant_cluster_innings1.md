# `[BATTERS-INVARIANT]` cluster — MI vs SRH innings 1 (2026-04-29)

**Match:** MI vs SRH, IPL 2026 match 151954  
**Log:** `logs/pipeline-2026-04-29-194416-mi-srh-live.log`  
**Analyzer window:** 19:44:25 → 21:32:51 (108.4 min)  
**Total fires (analyzer window):** 13 (12 × rule=C + 1 × rule=A)  
**Total fires (full log incl. post-innings-break):** 21

---

## 1. Full fire inventory

### 1.1 Innings 1 fires (F0–F2346, within analyzer window)

| Frame | Time | Rule | Violation | Active batters | Striker slot | Non-striker slot | Step3 fired? | Step3 tags | Nearest wicket | Δ frames | Category |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F487 | 20:09:39 | C | striker_non_collision | Will Jacks, Rohit Sharma | Will Jacks | Will Jacks | No | — | F488 | 1 | ADMISSION-WINDOW |
| F488 | 20:09:46 | C | striker_non_collision | Will Jacks, Naman Dhir | Will Jacks | Will Jacks | No | — | F488 | 0 | ADMISSION-WINDOW |
| F505 | 20:10:35 | C | striker_non_collision | Will Jacks, Naman Dhir | Will Jacks | Will Jacks | Yes | SCORER-DISMISSED-RESURRECT, SCORER-INVARIANT-FILTER | F488 | 17 | ADMISSION-WINDOW |
| F506 | 20:10:43 | C | striker_non_collision | Will Jacks, Naman Dhir | Will Jacks | Will Jacks | Yes | GUARD_BATTER_EXTRACTOR, SCORER-DISMISSED-RESURRECT | F488 | 18 | ADMISSION-WINDOW |
| F684 | 20:18:55 | C | striker_non_collision | Will Jacks, Suryakumar Yadav | Will Jacks | Will Jacks | No | — | F663 | 21 | ADMISSION-WINDOW |
| F710 | 20:19:46 | C | striker_non_collision | Will Jacks, Suryakumar Yadav | Will Jacks | Will Jacks | No | — | F724 | 14 | ADMISSION-WINDOW |
| F1288 | 20:48:26 | C | striker_non_collision | Naman Dhir, Suryakumar Yadav | Naman Dhir | Naman Dhir | No | — | F1281 | 7 | ADMISSION-WINDOW |
| F1323 | 20:49:22 | C | striker_non_collision | Naman Dhir, Suryakumar Yadav | Naman Dhir | Naman Dhir | Yes | GUARD_BATTER_EXTRACTOR | F1348 | 25 | ADMISSION-WINDOW |
| F2104 | 21:20:34 | C | striker_non_collision | Hardik Pandya | Hardik Pandya | Hardik Pandya | No | — | F2103 | 1 | ADMISSION-WINDOW |
| F2105 | 21:20:39 | C | striker_non_collision | Ryan Rickelton, Tilak Varma | Ryan Rickelton | Ryan Rickelton | No | — | F2105 | 0 | ADMISSION-WINDOW |
| F2124 | 21:21:46 | C | striker_non_collision | Ryan Rickelton, Tilak Varma | Ryan Rickelton | Ryan Rickelton | No | — | F2105 | 19 | ADMISSION-WINDOW |
| F2167 | 21:24:35 | **A** | **active_set_max_two** | **Ryan Rickelton, Tilak Varma, Hardik Pandya** | Ryan Rickelton | Hardik Pandya | No | — | F2105 | **62** | **NON-ADMISSION** |
| F2285 | 21:30:34 | C | striker_non_collision | Ryan Rickelton | Ryan Rickelton | Ryan Rickelton | Yes | SCORER-INVARIANT-FILTER | F2285 | 0 | ADMISSION-WINDOW |

**Analyzer window summary:** 12 × rule=C (ADMISSION-WINDOW), 1 × rule=A (NON-ADMISSION at F2167).

### 1.2 Post-innings-break fires (F2347+, outside analyzer window)

These frames correspond to the innings transition / early innings 2 cold-start period. All show stale MI batter names persisting before innings 2 state fully resets.

| Frame | Time | Rule | Active (stale) | Category |
|---|---|---|---|---|
| F2347 | 21:33:13 | C | Ryan Rickelton, Robin Minz | NON-ADMISSION (innings transition) |
| F2405 | 21:35:24 | C | Ryan Rickelton, Robin Minz | NON-ADMISSION (innings transition) |
| F2406 | 21:35:29 | C | Ryan Rickelton, Robin Minz | NON-ADMISSION (innings transition) |
| F2407 | 21:35:34 | C | Ryan Rickelton, Robin Minz | NON-ADMISSION (innings transition) |
| F2416 | 21:36:13 | C | Ryan Rickelton, Robin Minz | NON-ADMISSION (innings transition) |
| F2418 | 21:36:23 | C | Ryan Rickelton, Robin Minz | NON-ADMISSION (innings transition) |
| F2419 | 21:36:28 | C | Ryan Rickelton, Robin Minz | NON-ADMISSION (innings transition) |
| F2423 | 21:36:28+ | C | Ryan Rickelton, Robin Minz | NON-ADMISSION (innings transition) |

These 8 fires are expected: SM holds innings-1 state (Ryan Rickelton, Robin Minz) while `SM.set_innings_2()` / `[SM-INNINGS-2-RESET]` has not fired yet in the log window. **Not a regression; expected cold-start class.**

---

## 2. Wicket correlation map

MI innings 1 had 5 wickets. POST-WICKET-ROTATION fired on 9 frames (double-fire on some wickets):

| Wicket # | POST-WICKET-ROTATION frame(s) | Dismissed batter (inferred) | BATTERS-INVARIANT fires in window | Frames with fires |
|---|---|---|---|---|
| W1 (Ryan Rickelton dismissed, ~over end) | F474 | Ryan Rickelton's non-striker | F487, F488, F505, F506 | Within ±25 of F488 |
| W2 (Will Jacks dismissed?) | F663 | Previous non-striker | F684, F710 | Within ±25 of F663/F724 |
| W3 (Naman Dhir dismissed?) | F1281 | Previous non-striker | F1288, F1323 | Within ±25 of F1281/F1348 |
| W4 (Suryakumar Yadav + Hardik cluster) | F2103, F2105 | Both batters rotated | F2104, F2105, F2124 | Within ±25 of F2103/F2105 |
| W5 (Tilak Varma dismissed) | F2285 | Tilak out → Ryan Rickelton sole | F2285 | Same frame |

**F2167 rule=A:** Falls **62 frames** after the nearest wicket event (F2105). This is a genuine multi-batter state where the batting card simultaneously showed 3 active batters. Likely cause: a graphic overlay or extractor read that briefly inserted Hardik Pandya back into the active set when the strip showed a past stat. The `_scorer_batter_update_allowed` gate should have blocked this, but `upstream_step3_fired=false` indicates the SCORER decision on that frame did not trigger any Step-3 filter — meaning Hardik Pandya's card flipped active through a path that bypassed `apply_scorer_decision` (likely a direct `batting_card` write in the ground-truth or extractor path).

---

## 3. Categorization summary

| Category | Count (analyzer window) | Count (full log) |
|---|---|---|
| ADMISSION-WINDOW (rule=C, ≤25 frames from wicket) | 12 | 12 |
| NON-ADMISSION rule=A (F2167) | 1 | 1 |
| NON-ADMISSION innings-transition rule=C (F2347+) | 0 | 8 |
| **Total** | **13** | **21** |

**RULE-A count:** 1 (F2167 only). Not near-zero as expected; but isolated and explainable (graphic overlay resurrection).  
**RULE-B count:** 0. Witnessed-out batter resurrection filter working as designed.  
**RULE-C count:** 20/21. Dominant class; all rule=C; consistent admission-window mechanism.

---

## 4. Mechanism identification

### 4.1 Primary mechanism (rule=C admission-window fires)

```
Post-wicket gap (SM non_striker = dismissed batter name):
  _project_active_batters:
    state["striker"]     = canon(SM.striker)     # correct
    state["non_striker"] = canon(SM.non_striker)  # STALE (dismissed batter)
  WS-SCRUB (test_pipeline.py:4914+):
    non_striker card status = "out" → reject → find alternate in active card
    Only one active batter (striker) → sub striker into non_striker slot
    → state["non_striker"] = state["striker"]     # DUPLICATE
  _canonical_active_slot("non_striker"):
    SM.non_striker is stale (dismissed) → skip SM → check _inn["non_striker"]
    _inn["non_striker"] is None or in transition
    → both slots resolve to striker's name
  [BATTERS-INVARIANT] rule=C fires: striker == non_striker (both = current striker)
  action=noop_phase1 (Phase 2 autocorrect off)
```

### 4.2 SM update latency — root cause of window duration

`STRIKER-SM-CUTOVER` fires **only at over-end boundaries** (38 fires in 108 min = 0.35/min). After a wicket, SM `non_striker` stays stale until the NEXT over-end triggers a `STRIKER-SM-CUTOVER`. Intra-over wickets produce gaps of 10–30 frames (the remaining balls of the current over) during which rule=C fires on every scorer frame.

### 4.3 W-site correlation via `[STRIKER-WRITE]` telemetry

Key writes from `[STRIKER-WRITE]` adjacent to BATTERS-INVARIANT clusters:

| Frame | Source line | Write | Effect |
|---|---|---|---|
| F449 | L2408 `_set_inn_slot_with_sm_mirror` | striker→Will Jacks, non_striker→Ryan Rickelton | Over-end SM+`_inn` lockstep; SM correct |
| F474 | L9020 `run_test` | `_inn["non_striker"]` Ryan Rickelton→None | `_inn` cleared; SM `non_striker` stays `Ryan Rickelton` |
| F487 | L7881 `run_test` | `_inn["non_striker"]` None→Rohit Sharma | `_inn` updated; SM `non_striker` still stale Ryan Rickelton |
| F638 | L2408 `_set_inn_slot_with_sm_mirror` | Over-end rotation | SM finally updated; BATTERS-INVARIANT stops |

**Write-site attribution:** The BATTERS-INVARIANT fires arise from **SM `non_striker` NOT being updated** between F474 (wicket) and F638 (next over-end). The `_inn` SB side is updated (L9020, L7881) but SM remains stale. This is the STRIKER-SM-CUTOVER latency window.

The `_inn` writes at L7881 and L9020 are from the `run_test` (extraction / extractor path), not from `_set_inn_slot_with_sm_mirror`. They update SB `_inn` without mirroring to SM, creating the SB/SM desynchronization window.

**Implication:** The Lever 1 fix that actually closes this window is not W3–W7 migration per se, but rather **ensuring SM `non_striker` is cleared immediately after a wicket dismissal** rather than waiting for the next over-end `STRIKER-SM-CUTOVER`. W11/W12 migration to `_set_slot_pair` (PR4 in the Lever 1 sequence) plus a `STRIKER-SM-CUTOVER` trigger at batter-arrival time would close this gap.

---

## 5. F2167 rule=A deep-dive

**Frame:** F2167 at 21:24:35  
**Active set:** `Ryan Rickelton, Tilak Varma, Hardik Pandya` (3 batters)  
**Striker:** Ryan Rickelton | **Non-striker:** Hardik Pandya  
**upstream_step3_fired:** false — Step 3 SCORER filters did not flag this frame  
**Nearest wicket:** F2105 (Δ=62 frames)  

Hardik Pandya was dismissed earlier (wicket at F2103 → POST-WICKET-ROTATION at F2103/F2105). 62 frames after his dismissal, his batting card re-appeared as `status=batting`. The likely cause: a graphic strip frame briefly showed Hardik's season stats or scorecard overlay which the extractor misread as a live batting row; since `upstream_step3_fired=false`, the SCORER decision on F2167 did NOT include a batter_updates entry for Hardik — the card flip was direct (ground-truth or extractor applied without going through `apply_scorer_decision`'s watched-out filters).

**Severity:** LOW. The card corrected on next verified frames. No `upstream_step4_returned_false` — the SB accepted the (transient) state. Phase 1 noop-phase1 was correct; Phase 2 autocorrect would have wrongly demoted Ryan Rickelton or Tilak Varma (both legitimate active batters) instead of Hardik (who was the resurrected one, but `auto_demote` demotes "most recently activated", not "most recently resurrected").

**Recommendation:** Rule=A autocorrect logic in Phase 2 should be revised to: demote the batter whose card transitioned to `batting` most recently AND who appears in `fall_of_wickets` (i.e., was already witnessed-out). If no batter in the 3-set meets both conditions, defer to `noop` and emit `[BATTERS-INVARIANT-UNRESOLVABLE-A]`. This is a Phase 2 implementation note, not a Phase 1 blocker.

---

## 6. Phase 2 readiness assessment

| Criterion | Value | Phase 2 ready? |
|---|---|---|
| "1 clean match-day" (§10.4) | 13 fires in innings 1 | ❌ NOT MET |
| All fires ADMISSION-WINDOW | 12/13 (F2167 NON-ADMISSION) | ❌ NOT MET (1 non-admission) |
| Rule=A fires = 0 outside admission window | 1 (F2167 at Δ=62) | ❌ NOT MET |
| Rule=B fires = 0 | 0 | ✅ |
| Innings transition fires = 0 | 8 NON-ADMISSION (F2347+) | ❌ NOT MET |

**Verdict: DEFER Phase 2 enablement.** See `mi_srh_innings_break_analysis.md` §5 for full decision.

---

## 7. Upstream layer state correlation

For fires where `upstream_step3_fired=true`:

| Frame | Step3 tags fired | Interpretation |
|---|---|---|
| F505 | SCORER-DISMISSED-RESURRECT, SCORER-INVARIANT-FILTER | SCORER tried to update Ryan Rickelton (dismissed) → rejected → correct |
| F506 | GUARD_BATTER_EXTRACTOR, SCORER-DISMISSED-RESURRECT | Extractor named dismissed batter → rejected → correct |
| F1323 | GUARD_BATTER_EXTRACTOR | Extractor named batter not in active set → rejected |
| F2285 | SCORER-INVARIANT-FILTER | SCORER tried to update dismissed Tilak Varma → rejected |

**Pattern:** `upstream_step3_fired=true` correlates with the tail of each admission window (F505–F506, F1323, F2285) — frames where the extractor is still showing the dismissed batter's info while the next batter is being confirmed. The upstream Step 3 filters are working correctly; they reject the bad update. The BATTERS-INVARIANT still fires because SM `non_striker` is stale (the Step 3 filter rejection doesn't force an SM slot update).

For `upstream_step3_fired=false` fires: the SCORER decision on those frames did not attempt a batter update that triggered Step 3 filters. The BATTERS-INVARIANT fires because the SM stale-state persists regardless of what SCORER does on that frame.

---

## 8. Innings 2 monitoring guidance

Based on innings 1 pattern, expect **similar ADMISSION-WINDOW rule=C fires** at:
- SRH first wicket (innings 2 first batter out)
- Each subsequent wicket where a new batter arrives intra-over

**Watch for:**
- Rule=A fires: should be zero if the F2167 Hardik-resurrection was MI-specific
- NON-ADMISSION fires (Δ>25 frames from any wicket): escalate if >0 in first 60 min of innings 2
- Fires during innings 2 cold-start (first 50 frames): expected transition-class fires; not a regression

**If `[SM-INNINGS-2-RESET]` fires:** confirms `SM.set_innings_2()` triggered; BATTERS-INVARIANT should briefly pause (SM resets to `(None, None)`) then resume with new SRH batter admission pattern.

---

**Cross-references:**
- `lever1_pr2_match_analysis.md` — Cause (C) mechanism shared with WS-SLOT-INVARIANT source
- `scorer_invariants_categorization.md` §10.1–10.4 — Phase 2 design and criteria
- `mi_srh_innings_break_analysis.md` §5 — Phase 2 enablement decision
