# Fix 3 — this_over chronological reorder on FOW upgrade

**Bug**: P1 — `this_over` token order reflects detection time, not chronological ball time
**Backlog ref**: `files/docs/backlog.md` "this_over token order reflects detection time"
**Trace**: F2048 (W detected) → F2068 (boundary 6 caught up) → F2117 (FOW upgrade pins wicket to 0.5). Real chronological order `[., ., ., Wd, 6, W]`, observed `[., ., ., Wd, W, 6]`.

## Files modified

| file | lines added | net |
|------|-------------|-----|
| `files/eyes/this_over.py` | +75 (`reorder_wicket_to_ball` method) | +75 |
| `files/eyes/scoreboard.py` | +27 (callback attr + fire on upgrade) | +27 |
| `files/test_pipeline.py` | +9 (callback wiring) | +9 |
| `files/test_recent_fixes.py` | +120 (6 tests) | +120 |

## Source changes

### `this_over.py` — `OverManager.reorder_wicket_to_ball(ball_index)`
New public method. Logic:
1. If no `W` in `this_over` or `target ≤ 0`, return `False` (no-op).
2. Compute current legal-ball position of `W` (counting `.`, `0..7`,
   `W`, byes, leg-byes; skipping `Wd`, `Nb`, `Wd+N`, `Nb+N`).
3. If already at `target`, return `False` (no-op).
4. Pop `W` (and its source slot).
5. Find smallest insertion index `i` where exactly `target-1` legal
   balls precede `i` — inserting `W` at `i` makes it the target-th
   legal ball.
6. Log `[FOW-REORDER] W repositioned from legal-ball X → Y` and
   return `True`.

### `scoreboard.py` — `on_fow_upgrade` callback hook
1. New attribute `Scoreboard.on_fow_upgrade: callable | None = None`
   in `__init__` (default no-op preserves existing test compatibility).
2. In `_add_fow`, the placeholder-upgrade branch (right after the
   `[FOW] Upgraded placeholder W{wk}: ...` log) parses ball-index
   from `overs="X.Y"` and fires `self.on_fow_upgrade(_ball_y)` if
   the callback is wired. Wrapped in `try/except` so a misbehaving
   consumer cannot poison the FOW write itself.
3. Callback does NOT fire on:
   - witnessed-FOW immutable refuses (no upgrade happened)
   - idempotent re-adds (no upgrade happened)
   - placeholder→placeholder rewrites (no real overs to pin to)

### `test_pipeline.py` — wiring at construction time
Added one line just after `over_mgr = ThisOverManager()`:
```python
scoreboard.on_fow_upgrade = over_mgr.reorder_wicket_to_ball
```

## Tests added (test_recent_fixes.py)

1. `test_this_over_reorder_w_after_boundary_to_correct_ball` — F2068 replay (`[., ., ., Wd, W, 6]` + target=5 → `[., ., ., Wd, 6, W]`)
2. `test_this_over_reorder_no_op_when_position_already_correct` — already-correct returns False, list unchanged
3. `test_this_over_reorder_handles_no_w_gracefully` — no-W returns False
4. `test_this_over_reorder_extras_are_skipped_in_legal_count` — compound extras (`Wd+4`, `Nb+1`) and pure extras (`Wd`, `Nb`) don't advance legal-ball counter; backward-reorder case included
5. `test_scoreboard_fow_upgrade_callback_fires_on_upgrade` — wiring test: callback fires with parsed ball-index on placeholder upgrade
6. `test_scoreboard_fow_upgrade_callback_no_fire_on_immutable_skip` — callback does NOT fire when `_add_fow` refuses a witnessed rewrite

## Test results

```
PASS 186 / FAIL 2 (both pre-existing, unrelated to Fix 3)
```

All 6 Fix-3 tests PASS. Existing 118 baseline + Fix 1's 6 + Fix 2's
5 + Fix 4's 4 unaffected.

## Residual edge case (acknowledged in backlog)

Wicket on **ball X.6** (last legal ball of over) could theoretically
have FOW upgrade race over completion — Fix 3 only fires while the
W token is still in `this_over` (i.e. before `_complete_over` archives
it). Empirical 2026-04-25 cadence (6/6 wickets had FOW upgrades fire
**before** over completion, lead 19s–4m04s) suggests this race is
rare in practice. Backup defensive sort inside `_complete_over` is
documented as a 3-line follow-up if production data ever shows the
race firing.
