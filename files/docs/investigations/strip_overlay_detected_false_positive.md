# STRIP-OVERLAY-DETECTED false-positive on wicket transitions

**Status:** investigation-only (no production code changes)
**Match:** GT vs PBKS innings 1, 2026-05-03 (log `pipeline-2026-05-03-2058--stage1ready.log`)
**Fires this match:** 61 × `[STRIP-OVERLAY-DETECTED]`
**Linked issues:** U1 (no second batter on top strip), U4 (batters stuck after over change), U5 (state-lock 18.0–18.2–19.2), bug A (wicket-on-wicket regression)

---

## 1. Context — observed timeline (PBKS late innings)

| Frame | Time | Event |
|-------|------|-------|
| F107  | 21:04:23 | **Wicket 7**: Stoinis dismissed at 17.4. Pipeline state: bat1=Jansen, bat2 cleared. |
| F127  | 21:05:30 | Strip read carries stale `Stoinis 40(31) | M Jansen 0(2)`; `Bartlett` mis-read as bowler (`[BOWLER-BATTER-GATE]`). |
| F128  | 21:05:35 | **Wicket 8**: Jansen dismissed at 17.5. *Same frame fires* `[UN-DISMISS] Marcus Stoinis appeared on strip for 2 consecutive frames — reactivating` → bug A re-marks Stoinis `status="batting"`. Active set = `{Stoinis}` (incorrect ground truth). |
| F132  | 21:05:50 | Real strip `Bartlett 0(1) | M Jansen 2(2)` → `[STRIP-OVERLAY-DETECTED] reason=active_batting popped=batters` (1st in chain). |
| F133  | 21:05:54 | Same strip pair → reject. |
| F169–F181 | 21:07:16–21:07:49 | Real strip `[Vyshak, Jansen]` (Vyshak is the legitimate W9 replacement) → 8 consecutive rejects. |
| F208–F247 | 21:08:33–21:11:06 | Same `[Vyshak, Jansen]` pair → ~16 further rejects. |

The pair `[Vyshak, Jansen]` was the actual on-field batting partnership during PBKS overs 18–19. Every legitimate read was popped; the active set never updated.

## 2. Heuristic — `_detect_overlay_via_active_batting`

`files/test_pipeline.py:3244-3271` (called from `apply_strip_overlay_prefilters`, line 3302).

Decision rule:

```
active = {n for n,c in batting_card if c.status == "batting"}
if not active:                       # cold-start: skip
    return False
for be in extracted_batters:
    if scoreboard.resolve_name(be.name) in active:
        return False                 # any match → not overlay
return True                          # NONE match → overlay → pop
```

Inputs inspected: `extracted["batters"]` and `scoreboard.batting_card`.
Threshold: **all-mismatch** (zero of N strip names resolve into the active set).
Downstream effect when `True`: `extracted.pop("batters")` plus `record_state_recovery_guard("batter_row_rejected", proposed_reset=["bat:not_in_active_batting"])`. Strip-derived batter rows are denied to ScoreManager, the SM feeder, the consensus tracker, and the WS publisher for that frame. Sentinel-text path (`reason=sentinel`) shares the same emit site but uses different signal.

`[GRAPHIC-FILTER]` (28 fires) is a separate code path — Mode-C inset / team-null delta detector that poisons the *whole* strip read; it is stacked before this filter, not the same logic. Logs confirm both fired at distinct frames (e.g. F129 GRAPHIC-FILTER, F132 STRIP-OVERLAY).

## 3. Root cause — lockout mechanism

The heuristic assumes the active-batting card is ground truth. During a wicket-to-replacement transition (or after a stale-state corruption like bug A's UN-DISMISS), the active set is wrong:

1. State desync: active = `{Stoinis}` even though Stoinis is dismissed and Bartlett/Vyshak/Jansen are on the field.
2. Real strip read arrives → none of the strip names resolve to `{Stoinis}` → classified as overlay → popped.
3. The pop denies the only signal capable of correcting active. The card row for the new batter is never inserted; `[POST-WICKET-ROTATION]` left the slot pending new-batter admission, and admission is gated on the strip read that just got popped.
4. Next frame: same active set, same real strip, same rejection. Self-perpetuating. 27+ consecutive frames in this match.

The detector cannot distinguish "overlay graphic with cross-match names" from "real strip with new batter the active set hasn't learned about yet" because both produce the same all-mismatch pattern.

## 4. Fix options

### (a) Bypass detector for N frames after a `WICKET` ball_event
- **False-positive risk reduction:** high — covers the exact transition window.
- **False-negative risk:** moderate — comparison/career-stat overlays that happen to land in the bypass window will leak through. In this match, post-wicket overlays are common (player intro graphic shown ~5–15 s after dismissal).
- **Test gap:** no fixture exercises post-wicket overlay graphics inside the bypass window.

### (b) Require additional overlay cues beyond batter mismatch
- Add: `frame_class != SCOREBOARD`, `cam in {graphic, replay}`, presence of cross-match team token, or `scout_strip_text` containing a sentinel.
- **False-positive risk reduction:** high if cues are reliable.
- **False-negative risk:** low — overlays generally trip at least one secondary cue.
- **Test gap:** sentinel list (`STRIP_OVERLAY_SENTINELS`) is the existing path; this option mostly demotes the active-batting branch from "sole signal" to "tiebreaker" — and most existing-overlay test fixtures are sentinel-driven, so coverage already exists.

### (c) Soft mode — downgrade confidence instead of popping
- Tag batters with `confidence="suspect_overlay"`; let SM and consensus decide.
- **False-positive risk reduction:** highest — never silently drops real data.
- **False-negative risk:** depends on how downstream consumers honour the flag. Risk that current code paths ignore the flag and write through unchanged.
- **Test gap:** every downstream batter consumer needs a test that respects the suspect flag. Larger surface than (a) or (b).

### (d) Lockout breakout — count consecutive identical rejections
- After K consecutive `STRIP-OVERLAY-DETECTED` fires with the *same* batter pair, treat the (K+1)th read as authoritative and force-update the active set.
- **False-positive risk reduction:** high — by construction, a stuck active set self-heals.
- **False-negative risk:** low — a real overlay is ephemeral (~1–3 s, ≤2 frames at the cadence here); it won't repeat K=3+ times unchanged.
- **Test gap:** need a fixture where a real overlay does repeat (e.g., an on-screen player-intro graphic held for 6+ seconds during dead time).

## 5. Recommendation — option (b) primary, (d) safety net

Single recommendation: **option (b)** — require a secondary cue alongside batter mismatch before classifying as overlay. Concretely, gate the `reason=active_batting` branch on at least one of:

- `frame_class != SCOREBOARD`, or
- `cam in {graphic, replay, ad}`, or
- `scout_strip_text` matched a sentinel (already a separate `reason=sentinel` branch — promote it to *required* for the active-batting branch).

The active-batting mismatch alone is too weak a signal: it has the wicket-transition false-positive mode demonstrated above and offers no recovery path. Genuine overlays that warrant popping reliably trip at least one secondary cue (cam class, frame class, or a sentinel token); the active-batting test then becomes confirmation rather than the sole basis.

Pair with **option (d)** as a defensive backstop, threshold K=3 consecutive identical `(strip_batters, active_set)` tuples → force-update active. This guarantees no lockout can outlive ~10 s even if a future heuristic regresses. Option (a) was considered but is subsumed by (d) and adds a hard-coded post-wicket window that needs tuning per cadence.

## 6. Out-of-scope (deferred)

- Bug A — wicket-on-wicket UN-DISMISS regression (F128). Independent fix; addressing it would *reduce* but not eliminate the lockout because rotation/admission gaps are still possible without UN-DISMISS.
- Bug D — cross-match graphic overlays (separate sentinel set).
- GRAPHIC-FILTER redesign.
