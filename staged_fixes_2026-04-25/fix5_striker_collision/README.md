# Fix 5 — Striker self-collision guard in `update_batter`

**Bug**: P1 — `Scoreboard._inn["striker"] == _inn["non_striker"]` after
a transitional review-graphic misread following a legitimate swap.
**Backlog ref**: `files/docs/backlog.md` "Striker self-collision in
`update_batter`".
**Trace**: 2026-04-25 RR-vs-SRH match-2 innings 2; 27 / ~340 telemetry
frames (~7.9 %) emitted DETAIL lines with `AFTER_striker ==
AFTER_non_striker`. Concrete examples: F174–F176 and F290+ all show
`AFTER_striker=Vaibhav Sooryavanshi | AFTER_non_striker=Vaibhav
Sooryavanshi` while the simultaneous STATE renderer prints
`Bat: Vaibhav Sooryavanshi(103) Riyan Parag*(2)` — i.e. ScoreManager
holds the correct pair but `sb._inn` is collided.

## Files modified

| file                              | lines added | net  |
|-----------------------------------|-------------|------|
| `files/eyes/scoreboard.py`        | +18 (collision guard + comment) | +18 |
| `files/test_recent_fixes.py`      | +148 (4 tests + helper + TESTS wiring) | +148 |

## Source change (`scoreboard.py:update_batter`)

The legacy striker writes at the bottom of `update_batter` (the four
lines that pre-fix unconditionally wrote `_inn["striker"]` /
`_inn["non_striker"]`) now refuse the write when it would create
`striker == non_striker`. **Fix Path A — Conservative collision guard**
from the backlog draft.

Logic:

```python
if striker is True:
    if self._inn.get("non_striker") == name:
        log.warn(f"  [STRIKER-COLLISION] Refusing striker={name} "
                 f"— already non_striker; would self-collide")
    else:
        self._inn["striker"] = name
elif striker is False:
    if self._inn.get("striker") == name:
        log.warn(f"  [STRIKER-COLLISION] Refusing non_striker="
                 f"{name} — already striker; would self-collide")
    else:
        self._inn["non_striker"] = name
```

The guard is deliberately conservative:

- **Idempotent re-assertions are no-ops, not refusals.** Production
  calls `update_batter(name, striker=True/False, ...)` on every clean
  strip read to re-confirm asterisk position. When the asserted role
  already matches the current slot, the write goes through (no
  collision) and the slot is unchanged.
- **The legitimate swap path is independent.** End-of-over rotation
  is performed by atomic direct writes to `_inn["striker"]` /
  `_inn["non_striker"]` at `test_pipeline.py:6228-6237` (the broadcast-
  indicator flip introduced 2026-04-21), not by two consecutive
  `update_batter` calls. The conservative guard at this site does not
  interact with that path.
- **`update_batter` returns `True` even when the collision write is
  refused.** The stats portion of the call (runs / balls / fours /
  sixes) has already landed; the role assertion is the only thing
  refused. Surface area is identical to a re-assertion no-op.

The fix does NOT delete the legacy striker writes (Path B "finish the
SM cutover" in the backlog). That is the longer-arc cleanup; Path A is
the bounded-risk patch that closes the F173-class collision while the
legacy block remains.

## Tests added (`test_recent_fixes.py`)

Helper: `_setup_striker_collision_sb()` — fresh `Scoreboard` with
RR-vs-SRH-shaped squads and two batters mid-innings. Reused across
all four tests.

1. `test_striker_collision_refuses_non_striker_write_when_same_as_striker`
   — pre: `striker=Parag, non_striker=Sooryavanshi`. Call
   `update_batter("Parag", striker=False)`. Asserts striker /
   non_striker unchanged, `update_batter` still returns `True`,
   invariant `striker != non_striker` held. Confirms `[STRIKER-
   COLLISION]` log fires (visible in test output).
2. `test_striker_collision_refuses_striker_write_when_same_as_non_striker`
   — symmetric: pre `striker=Parag, non_striker=Sooryavanshi`, call
   `update_batter("Sooryavanshi", striker=True)`. Same assertions on
   the opposite slot.
3. `test_striker_collision_idempotent_self_writes_unaffected` — pre
   `striker=Sooryavanshi, non_striker=Parag`. Call
   `update_batter("Sooryavanshi", striker=True)` then
   `update_batter("Parag", striker=False)`. Both must accept (no
   collision), state unchanged.
4. `test_striker_collision_f170_f173_replay` — F170 ending state
   constructed directly (`striker=Sooryavanshi, non_striker=Parag`,
   matching the post-legacy-reset state from the backlog trace), then
   F173 misread `update_batter("Sooryavanshi", striker=False)` is
   called. Asserts striker / non_striker unchanged and the bug-class
   invariant `striker != non_striker` held.

## Test results

```
PASS 204 / FAIL 2 (both pre-existing, unrelated to Fix 5)
```

All 4 Fix-5 tests PASS (16 sub-checks). Existing 200-test baseline
unaffected. The 2 pre-existing failures are documented in
`files/docs/backlog.md` "Test hygiene (P3)" — `test_this_over_late
_boundary_ball_appends_to_held` and `test_twenty_over_invariant_check
_in_source` — and have been carried through every recent fix
landing.

## Bundling note

This is fix #5 in the inter-match commit bundle. File overlap with the
existing four fixes is minor — `scoreboard.py` is also touched by Fix
3 (FOW-upgrade callback hook); the changes are in different methods
(`update_batter` here vs `_add_fow` for Fix 3) and do not interact.

## Residual / known limits

- **Path B (full SM cutover) is still queued.** The legacy striker
  writes at this callsite have been flagged for removal since the SM
  cutover but remain in place. The conservative guard closes the
  collision class without touching the cutover work.
- **Commentary subsystems already collided through 2026-04-25 match-2
  cannot be retroactively corrected.** ~8 % of frames during that
  innings persisted to DETAIL telemetry with collided slots; the fix
  takes effect at next pipeline restart (the inter-match seam).
- **The guard is silent on the underlying upstream misread.** A
  transitional review-graphic that swaps batter-row order is still
  parsed by Scout; the guard prevents the downstream collision but
  does not surface the misread itself. Existing extractor / consensus
  defenses cover the scout-level mitigation independently.
