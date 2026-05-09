# Fix 2 — this_over token-alphabet validation

**Bug**: P0 — `this_over` ingests 3-digit speed values as run-tokens
**Backlog ref**: `files/docs/backlog.md` "this_over ingests 3-digit speed values as run-tokens (no token-alphabet validation)"
**Trace**: F2461 (RR vs SRH 2026-04-25) — broadcast strip rendered the per-ball-speed track with literal `THIS OVER:` field name; `_merge_broadcast` passed `[139, 148, 143, 147, 145, 140]` through verbatim; archived as nonsense over (`862 runs/over 2`). Defect class active intermittently since 2026-04-16 (earlier garbage payloads `['2161']`, `['11', '.', '41']`).

## Files modified

| file | lines added | net |
|------|-------------|-----|
| `files/eyes/this_over.py` | +69 (helper +47, gate +22) | +69 |
| `files/test_recent_fixes.py` | +96 (5 tests) | +96 |

## Source changes (this_over.py)

1. **New static helper `_is_legal_run_token(t)`** added directly above
   `_merge_broadcast` (~L635). Validates against the cricket-scorecard
   alphabet that `_merge_broadcast` is permitted to emit:
   - `.`, `?`, `W`, `Wd`, `Nb`
   - single-digit runs `0..7` (7 covers overthrow / wide+6)
   - `{N}b` byes and `{N}lb` leg-byes for N in `0..7`
   - **Compound tokens `Wd+N`/`Nb+N` deliberately excluded** — they
     originate in observed `on_ball_event` and bypass this gate, so
     they cannot legally arrive via `_merge_broadcast`.

2. **Single early-gate** in `on_broadcast_override` (~L527) right
   after `_merge_broadcast()`: if **any** token in the merged
   broadcast fails the alphabet check, reject the entire list and
   log `[TOKEN-VALIDATE] Rejecting broadcast tokens ...`. One gate
   covers all four downstream `self.this_over = broadcast`
   assignment sites (cold-start, warm-mode wholesale, all-placeholder
   replace, gap-fill).

   Wholesale-rejection rationale: a single illegal token is a strong
   signal the entire strip was misread. Partial acceptance leaves a
   silently-truncated over with the same UX-bug surface.

## Tests added (test_recent_fixes.py)

1. `test_this_over_alphabet_rejects_speed_tokens_f2461` — F2461 replay
2. `test_this_over_alphabet_rejects_2026_04_16_garbage` — `['2161']` and `['11', '.', '41']`
3. `test_this_over_alphabet_accepts_legal_sequence` — `['1', '.', '4', 'wd', 'w', '6']` lands as `['1', '.', '4', 'Wd', 'W', '6']`
4. `test_this_over_alphabet_rejects_mixed_list` — single illegal token rejects the whole list
5. `test_this_over_alphabet_helper_boundary_cases` — 7/8 boundary, `2lb`, `3b`, `9b`, `42`, `Wd+4`, etc.

## Test results

```
PASS 172 / FAIL 2 (both pre-existing, unrelated to Fix 2)
```

All 5 Fix-2 tests PASS. Existing 118 baseline + Fix 1's 6 + Fix 4's
4 unaffected.
