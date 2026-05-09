# Lever 1 PR2 — MI vs SRH match-day analysis (2026-04-29)

**Match:** MI vs SRH, IPL 2026 match 151954  
**Log:** `logs/pipeline-2026-04-29-194416-mi-srh-live.log`  
**Window:** 19:44:25 → 21:32:51 (108.4 min), F0 → F2346+  
**Result:** MI 239-5 (20.0 overs); innings 1 complete  
**Status:** HYPOTHESIS REFUTED (W8 not dominant source); residual rate explained; PR3 implications documented.

---

## 1. Original hypothesis

From `sm_rotation_atomicity_design.md` §7 and §8:

| Claim | Original value |
|---|---|
| Dominant `[WS-SLOT-INVARIANT]` source | W8 `_identify_and_set_striker` — canon-collision path (§3.3) |
| Predicted PR2 reduction | **40–60%** of fires (mid 50%) |
| Combined PR1+PR2 reduction | **50–75%** |
| Key telemetry signal | `[SM-SLOT-INVARIANT]` fires with `source=_identify_and_set_striker.*` |

PR1 (helper + post-condition) and PR2 (W8 migration) both shipped 2026-04-29.

---

## 2. Measured outcome — innings 1

| Metric | Value | vs. baseline |
|---|---|---|
| `[WS-SLOT-INVARIANT]` total fires | **122** | PBKS 2.4/min ≈ 260/108min |
| `[WS-SLOT-INVARIANT]` rate | **1.13/min** | **~53% reduction** |
| `[SM-SLOT-INVARIANT]` fires (W8 helper repairs) | **0** | expected >0 if W8 was dominant |
| `[SM-SLOT-INVARIANT-PAYLOAD]` fires (payload backstop) | **0** | expected >0 if bypass exists |
| Fire composition: "cleared" (no alternate active) | 29 / 122 = **24%** | |
| Fire composition: "rebuilt" (alternate from active card) | 93 / 122 = **76%** | |

### 2.1 Critical finding: `[SM-SLOT-INVARIANT] = 0`

W8's `_set_slot_pair` helper was never triggered to repair a duplicate. This directly refutes the §3.3 canon-collision hypothesis as the dominant source. Possible explanations:

**(a) W8 ran but never produced a duplicate.** The explicit `else` branch in PR2 resolved the partner correctly on every frame. This means the pre-PR2 W8 _was_ leaving `non_striker` at a stale value, but the stale value didn't canonicalize to the same name as `new_striker` in this match (different squad names; IPL 2026 MI/SRH squad doesn't have the shared-surname ambiguity seen in PBKS-vs-RR).

**(b) The PBKS baseline 2.4/min was inflated by match-specific conditions** (multi-batter surname overlaps, extractor instability), not by the W8 canon-collision mode specifically.

Either way: **the `[SM-SLOT-INVARIANT]=0` is strong evidence that the 53% reduction is NOT attributable to W8 migration.**

### 2.2 Where the 53% reduction came from

Decomposition based on fire message content:

| Source class | Count | Notes |
|---|---|---|
| `rebuilt non_striker='X' from active card` | 93 | WS-SCRUB Cause (C) — alternate found |
| `cleared non_striker (no alternate active batter)` | 29 | WS-SCRUB Cause (C) — no alternate |
| SM-internal duplicate reaching WS (Causes A/B) | 0 | Confirmed by SM-SLOT-INVARIANT=0 |

**All 122 fires are WS-SCRUB Cause (C).** The reduction vs PBKS baseline most likely reflects:

1. **Match characteristics:** MI vs SRH had a more stable extractor (squad names unambiguous), fewer sustained duplicate windows than PBKS-vs-RR.
2. **Lever 2 contribution underestimated:** `get_broadcast_state` cleanup (alias + shadow projection uniformity) may have reduced Cause (B) fires more than the predicted ~0%.
3. **W8 explicit `else` branch**: Prevented canon-collision duplicate production even in the cases where W8 ran with `bat1/bat2=None` — confirmed safe by zero `[SM-SLOT-INVARIANT]` fires.

---

## 3. Reframed hypothesis

| Component | New assessment |
|---|---|
| **W8 as dominant source** | **REFUTED.** `[SM-SLOT-INVARIANT]=0` is direct evidence. W8 was not the dominant source in production with real IPL squad data. |
| **Cause (C) as dominant source** | **CONFIRMED.** 122/122 fires are WS-SCRUB rebuild class. SM `non_striker` holds stale dismissed-batter name → WS-SCRUB replaces with sole active survivor = striker → duplicate. |
| **53% reduction attribution** | Match-characteristics variance + possible Lever 2 contribution > predicted; NOT W8 migration. |
| **`[SM-SLOT-INVARIANT-PAYLOAD]=0`** | Defense-in-depth backstop functioning; no bypass sites found. |

### 3.1 Mechanism of remaining 122 fires (all Cause C)

```
Wicket event:
  SM.non_striker = <dismissed batter> (stale; no write until STRIKER-SM-CUTOVER)
  STRIKER-SM-CUTOVER fires only at OVER-END boundaries
  →  For N frames until next over-end, SM.non_striker stays stale

_project_active_batters:
  state["non_striker"] = canon(SM.non_striker)  # stale dismissed name
  WS-SCRUB: dismissed name has status=out → replace with only active = striker
  → state["non_striker"] = state["striker"]     # DUPLICATE
  enforce_ws_slot_invariant fires → repair
```

**Gap:** `STRIKER-SM-CUTOVER` only fires at over-end (38 times in 108 min = ~0.35/min). Wickets that fall intra-over leave SM stale for 10–30 frames (remainder of current over) before the next STRIKER-SM-CUTOVER.

---

## 4. Implications for PR3

### 4.1 W3–W7 are the remaining Lever 1 targets

W3–W6 (`_init_from_card`) and W7 (`_update_batters` bootstrap) write SM slot pairs during cold-start / new-batter admission. Currently they may write:
- `striker=new_batter, non_striker=<bat_from_card>` where bat_from_card matches striker → END-STATE-DUPLICATE-RISK

PR3 migrates W3–W7 to `_set_slot_pair`, which:
1. Canonicalizes at write time → closes §3.3 for init paths
2. Emits `[SM-SLOT-INVARIANT source=_init_from_card]` on degenerate cards → directly observable
3. Post-condition clears the duplicate → SM never enters a stale-duplicate end state

### 4.2 Expected PR3 impact

| Fire class | Before PR3 | After PR3 (predicted) |
|---|---|---|
| Cause (C) WS-SCRUB — admission window | 29–93 / 108 min | 15–60% reduction (admission windows shorter) |
| Cause (C) WS-SCRUB — background (non-wicket) | Already low | No change (background comes from strike-rotation lag, not init paths) |
| Cause (A/B) SM internal (W3-W7) | 0 fires (unconfirmed zero) | Confirmed zero after PR3 |

**Confidence: MEDIUM.** STRIKER-SM-CUTOVER will need PR3 to also cover the `_update_batters` bootstrap at batter-arrival time (not just over-end). The STRIKER-SM-CUTOVER trigger condition should be reviewed: if it fires only at over-end, W7 bootstrap runs but SM won't be synced until over-end regardless of W7 migration. PR3 implementation must ensure `_set_slot_pair` in W7 also triggers an immediate `_set_inn_slot_with_sm_mirror` so the `_inn` SB side is synchronised — not just the SM property.

### 4.3 Fire prediction after PR3

If `STRIKER-SM-CUTOVER` latency (over-end only) is the binding constraint, PR3 reduces `[WS-SLOT-INVARIANT]` by only **5–20%** unless the trigger is also updated to fire at batter-arrival time. The **binding fix for Cause (C) is a `STRIKER-SM-CUTOVER` trigger at new-batter admission**, not just at over-end. This is a separate scoping item from W3–W7 migration per se.

### 4.4 The `[SM-SLOT-INVARIANT]` zero finding as positive signal

`[SM-SLOT-INVARIANT]=0` across 108 min of live IPL match data is strong evidence that:
- W8's explicit `else` branch is functioning correctly (partner resolved, no stale-non_striker duplicate produced at the SM level)
- The §3.3 canon-collision hypothesis was over-weighted in the original audit (canon mismatches are rare with resolved IPL squad names)
- PR2 is **safe** — zero repairs means no false-positive corrections occurred

This is an important green-light: PR2 can be left as shipped with confidence.

---

## 5. Test fixture candidates from innings 1

| Test name (proposed) | Frame range | Description |
|---|---|---|
| `test_lever1_ws_scrub_cause_c_over_end_sync_latency` | F474–F519 | Post-wicket admission window: SM holds stale non_striker until F519 (next STRIKER-SM-CUTOVER at F638); verify `[WS-SLOT-INVARIANT]` rate drops after SM-CUTOVER fires |
| `test_lever1_pr2_sm_slot_invariant_never_triggers` | Full log | Regression: feed the full MI-SRH log through analyzer; assert `[SM-SLOT-INVARIANT]=0` (confirms W8 never needed repair on real IPL squad data) |
| `test_lever1_striker_sm_cutover_intra_over_wicket_gap` | F474–F638 | Capture: wicket at F474, CUTOVER at F638 (intra-over gap); count `[WS-SLOT-INVARIANT]` in gap; this is the test fixture for a future "CUTOVER trigger at batter-arrival" PR |

---

## 6. Summary for next session

| Item | Value |
|---|---|
| PR2 hypothesis | REFUTED (W8 not dominant source) |
| PR2 safety | CONFIRMED (zero repairs, zero false-positives) |
| Dominant source | Cause (C) WS-SCRUB + STRIKER-SM-CUTOVER over-end-only trigger |
| Next architectural work | PR3 W3–W7 migration + STRIKER-SM-CUTOVER trigger at batter-arrival |
| Expected residual after PR3+trigger fix | <0.3/min (`[WS-SLOT-INVARIANT]`), target <0.1/min |
| `[SM-SLOT-INVARIANT]` in next match (PR3 live) | Expected 0 still (W3-W7 degenerate cards rare); non-zero = degenerate card found |

---

**Cross-references:**
- `sm_rotation_atomicity_design.md` — original Lever 1 audit, §7 predictions updated here
- `batters_invariant_cluster_innings1.md` — BATTERS-INVARIANT cluster using same Cause (C) mechanism
- `backlog.md` — MI vs SRH monitoring section; Lever 1 PR3 backlog item
