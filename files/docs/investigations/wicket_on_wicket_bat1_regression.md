# Wicket-on-wicket bat1 regression

**Status:** Diagnosed, fix not applied.
**Log:** `logs/pipeline-2026-05-03-2058--stage1ready.log` (PBKS innings, F107 / F128).
**Code:** `files/eyes/scoreboard.py:1929-1977` (UN-DISMISS branch in `update_batter`).

## Context — F107 → F128 timeline

| Frame | Event | bat1 BEFORE → AFTER | bat2 | Notes |
|---|---|---|---|---|
| F107 | WICKET 17.4 (wkts 6→7). Striker=Stoinis dismissed. | Marcus Stoinis → Marco Jansen | "—" | `[POST-WICKET-ROTATION] non 'Marcus Stoinis' dismissed → slot cleared`. FOW W7 written as `_unwitnessed` placeholder. |
| F108–F126 | Stable. No new batter admitted (Bartlett not yet on strip). | Marco Jansen 7(6) | "—" | Repeated `[WS-SCRUB] non='Priyansh Arya' rejected reason=status_yet_to_bat`. |
| F127 | Strip still shows `Stoinis 40(31)` + `M Jansen 0(2)` (stale; Jansen has just walked to crease but strip cache lags). | Marco Jansen 7(6) | "—" | `BOARD WARN: Batter Marcus Stoinis dismissed but seen again (1/2) — waiting for consensus`. |
| F128 | Strip again shows `Stoinis 40(31)` + `M Jansen 1(2)`. WICKET 17.5 (wkts 7→8) fires, dismissing Jansen. | Marco Jansen 7(6) → **Marcus Stoinis 36(34)** ❌ | "—" | `BOARD INFO: [UN-DISMISS] Marcus Stoinis appeared on strip for 2 consecutive frames — reactivating`. Then `[POST-WICKET-ROTATION] striker 'Marco Jansen' dismissed → rotated non 'None' into striker slot`. |
| F129+ | Stoinis stays locked on bat1 for the next 100+ frames. | Marcus Stoinis 36(34) | "—" | `[WS-SCRUB] striker='Marco Jansen' rejected reason=status_out` repeats; `SM` keeps dropping `bat1_name='Marco Jansen'`. |

The hypothesis in the brief (BATTER REPLACEMENT promoting a dismissed candidate) is **wrong**. The REPLACE block at `test_pipeline.py:9185-9243` filters candidates by `status == "yet_to_bat"`, so a dismissed name cannot enter that path.

## Root cause

Within the F128 frame, the DIRECT batter-update loop (`test_pipeline.py:9077-9106`) calls `scoreboard.update_batter("Marcus Stoinis", runs=40, balls=31)` *before* the WICKET ball-event for Jansen fires.

`scoreboard.update_batter` at `files/eyes/scoreboard.py:1929` enters the UN-DISMISS branch when `entry["status"] == "out"`:

1. Line 1939 calls `_is_witnessed_dismissal(name)` — the **only** safety gate. Stoinis's W7 was written as `_unwitnessed` at F107 (no dismissal mode / fielder enrichment yet), so the gate **passes**.
2. `_dismissed_recovery["Marcus Stoinis"]` increments F127 → 1, F128 → 2. Threshold is 2 (line 1954).
3. UN-DISMISS fires: `entry["status"] = "batting"`, `entry["dismissal"] = None`. Stoinis is now active again.
4. The "deactivate the other batter" cleanup at lines 1965-1977 only runs when `len(active) > 2`. At F128 only Jansen is active before this point, so it's a no-op — and Jansen has not yet been dismissed by this frame's WICKET event.
5. The DIRECT loop then updates Jansen, then the WICKET event lands and dismisses Jansen via `[POST-WICKET-ROTATION]`. Net result: bat1=Stoinis (un-dismissed), bat2="—" (Jansen now out).

The UN-DISMISS path was added for *auto-dismiss-of-wrong-batter* recovery — when the system heuristically picks the wrong member of a pair on a wicket. Stoinis's F107 dismissal was **not** a heuristic: the wicket ball-event committed and `[WICKET-ATTRIB] Dismissed batter set from scoreboard striker: Marcus Stoinis` is logged at F107:2015. The dismissal attribution is canonical; the strip is just stale.

The witnessed-FOW gate (Fix 1, 2026-04-25) was meant to plug this kind of resurrection but only triggers on FOW entries that have been enriched past `_unwitnessed`. Between the wicket landing and CB-scrape enrichment / dismissal-mode resolution, the FOW row stays `_unwitnessed` for many seconds — exactly the window in which the strip cache flaps and the UN-DISMISS counter trips.

## Recommended fix

**Option (a) extended:** track `dismissal_source` on each batting-card entry and refuse UN-DISMISS when source is authoritative.

In `update_batter` POST-WICKET-ROTATION (and any other writer that flips a card to `status=out`), record:

```
entry["dismissal_source"] = "wicket_ball_event"   # vs "auto_inference"
```

Then in the UN-DISMISS branch (line 1929 onward), reject early when source is `wicket_ball_event`, regardless of FOW witness state:

```
if entry.get("dismissal_source") == "wicket_ball_event":
    log.warn(f"[INVARIANT] Refusing to un-dismiss '{name}' "
             f"— dismissal sourced from wicket ball event "
             f"(strip read suppressed)")
    return False
```

This is preferred over (b) "broaden `_is_witnessed_dismissal`" because the witnessed-FOW machinery is already overloaded with placeholder vs. enriched semantics, and over (c) "patch a specific writer" because the same race can recur from any DIRECT/REPLACE/SCORER writer that calls `update_batter` while the strip is stale. The new gate is orthogonal to the FOW pipeline and doesn't depend on enrichment timing.

**Diagnostic logging:** the rejection branch already returns `False` with a `WARN` log line, mirroring the existing `[INVARIANT]` pattern. No additional plumbing required to satisfy the B2 risk note.

**Compatibility with the legitimate use case:** the original auto-dismiss-of-wrong-batter scenario writes `entry["status"] = "out"` from heuristic inference (e.g., `_pr3_batter_arrival_slot_cutover`, post-wicket pair-diff). Those writers should record `dismissal_source = "auto_inference"`, leaving the UN-DISMISS path open for them — its intended purpose.

## Linked issues

- **U3 (striker tag wrong):** the F128 UN-DISMISS keeps `AFTER_striker=Marco Jansen` while bat1 reads Stoinis, because the un-dismiss writer doesn't reconcile the striker slot. Fixing the regression at the source removes the divergence trigger.
- **U5 (state-lock cascade):** with bat1 frozen on a dismissed batter, every subsequent frame trips `[WS-SCRUB] striker=... rejected reason=status_out` and `[SM] dropping bat1_name=... — scoreboard shows status=out`. The 100+ frame state-lock observed live is downstream of this single F128 write.
- **Bug B (compounding):** the strip's persistent display of Stoinis is what feeds the UN-DISMISS counter. Even with this fix, B's stale-strip suppression remains valuable defence-in-depth, but is no longer load-bearing for correctness.
