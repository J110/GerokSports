# Fix 4 — overs CONSENSUS-BLOCKED regression guard

**Bug**: P0 — match-`overs` consensus override accepts hallucinated regression
**Backlog ref**: `files/docs/backlog.md` "match-`overs` consensus override accepts hallucinated regression (6.0 → 0.5)"
**Trace**: F3117–F3120 — broadcast strip read `(POWERPLAY)` for 4 frames; Scout misparsed `(POWERPLAY)` slot as `(0.5)`; consensus override committed `confirmed[overs] = 0.5` despite 8 prior `[SUSPICIOUS] backwards` warnings; cascading state corruption (frozen batters, phantom over, target=640 + RRR nonsense) until pipeline restart.

## Files modified

| file | lines added | net |
|------|-------------|-----|
| `files/eyes/consistent_tracker.py` | +27 (2 guard blocks) | +27 |
| `files/test_recent_fixes.py` | +99 (4 tests + helper) | +99 |

## Source changes (consistent_tracker.py)

Two new `[CONSENSUS-BLOCKED]` guard blocks, mirroring the existing
bowler-stats and batter-stats regression guards already in this file:

1. **Reject-streak / consensus-override path** (after the bowler-stats
   guard at L270-281): when `field == "overs"` and the new value is
   numerically lower than the confirmed value, reject and pop the
   reject-streak. Returns `current`.

2. **Pending-promotion path** (after the bowler-stats pending-path
   guard at L341-352): same predicate, same rejection, on the
   alternate promotion branch — closes the SRH-vs-DC F113 leak class
   that historically allowed regressions to slip through `count=3/3`
   while a streak was active.

Both blocks log `[CONSENSUS-BLOCKED] overs: {old}→{new} — match overs cannot regress within an innings ...`.

## Tests added (test_recent_fixes.py)

Helper: `_confirm_overs_via_cold_start(tracker, value)` — pushes a
value through the 3-frame cold-start consensus to land it in
`confirmed`. Reused across all 4 tests.

1. `test_overs_consensus_blocked_rejects_powerplay_regression` — F3117–F3120 replay (confirmed 6.0 → 4 reads of 0.5 → still 6.0)
2. `test_overs_consensus_blocked_progression_still_accepted` — legitimate 6.0 → 6.1 promotion (2 matching reads through pending path)
3. `test_overs_consensus_blocked_set_innings_2_path_still_works` — innings transition: clear-confirmed + cold-start to 0.0 unaffected
4. `test_overs_consensus_blocked_other_fields_unaffected` — cross-field independence: `score` regression still goes through (no field-specific guard for raw score regression)

## Test results

```
PASS 153 / FAIL 2 (both pre-existing, unrelated to Fix 4)
```

All 4 Fix-4 tests PASS. Existing 118 baseline (and Fix-1's 6 new
tests) unaffected.
