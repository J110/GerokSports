# Fix 1 — target=640 sanity bound on innings-1 latch

**Bug**: P0 — Innings-1-final latch poisoned by extractor hallucination
**Backlog ref**: `files/docs/backlog.md` "Innings-1-final latch poisoned"
**Trace**: F921 (76.5 overs phantom 639/4) latched via max-wins;
F1445 real 228/6 rejected because 228 < 639 → target=640 in innings 2.

## Files modified

| file | lines added | lines removed | net |
|------|-------------|---------------|-----|
| `files/test_pipeline.py` | +43 | -5 | +38 |
| `files/test_recent_fixes.py` | +112 (6 tests) | 0 | +112 |

## Source changes (test_pipeline.py)

1. New module-level helper `_should_latch_innings_1_candidate()` near
   `_safe_int`/`_safe_float` (~L870), wrapping max-wins predicate
   inside T20 sanity bounds (≤20.0 overs, ≤350 runs).
2. Constants `_INNINGS_TOTAL_MAX_OVERS = 20.0` and
   `_INNINGS_TOTAL_MAX_SCORE = 350` (both empirically grounded:
   T20 caps at 20 overs; IPL all-time max is 287/3 SRH 2024-03-27,
   so 350 is ~22% above the historical record — comfortably above
   any legitimate score, decisively below F921-class extractor
   hallucinations).
3. Callsite at `~L5404` swapped from inline max-wins predicate to
   `_should_latch_innings_1_candidate(...)`; on `sanity_bound`
   rejection, emits `[INNINGS-END] Rejecting bogus latch candidate
   ... — exceeds T20 sanity bounds`.

## Tests added (test_recent_fixes.py)

1. `test_innings1_latch_rejects_phantom_639_at_76_overs` — F921 replay
2. `test_innings1_latch_accepts_normal_t20_final` — 228/6 (20.0)
3. `test_innings1_latch_phantom_does_not_lock_real_final` — F921→F1445 sequence
4. `test_innings1_latch_sanity_boundaries` — 350/351 runs, 20.0/20.1 overs
5. `test_innings1_latch_max_wins_within_bounds` — preserved max-wins inside bounds
6. `test_innings1_latch_callsite_wired_in_source` — source-grep guard against drift

## Test results

```
PASS 146 / FAIL 2 (both pre-existing, unrelated to Fix 1):
  - test_this_over_late_boundary_ball_appends_to_held (pre-existing)
  - 18.0 cap removed regression in test_twenty_over_invariant_check_in_source (pre-existing)
```

All 6 Fix-1 tests PASS.
