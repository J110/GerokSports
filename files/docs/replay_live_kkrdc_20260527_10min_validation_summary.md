# KKR/DC 10-Minute Validation Summary

Final clean session: `replay_kkrdc_10min_guardstrip_clean_20260527_100933`.

The prior `replay_kkrdc_10min_guardstrip_20260527_022855` run is discarded for
validation because it hot-resumed from `files/match_state_cache.json` at
`24/0 (2.5)`.

## Clean Run Preflight

- `files/match_state_cache.json` was removed before replay.
- Immediate cache check passed: `CACHE_PREFLIGHT=absent`.
- Replay logged `[CACHE] No cached state found — starting fresh`.
- No `HOT-RESUME` marker appeared.

## Track 1 Result

- Diff: `matched=11`, `missing=1`, `phantom=1`, `divergences=111`.
- `1.3 DOT` emits.
- False post-ad scoreless `2.1 DOT` is gone.
- `2.1 1_RUNS` emits correctly.
- Duplicate `Wd` is absent.
- Remaining missing GT ball: `1.1`.
- Remaining phantom: `2.6`.

## Track 2 dNNN Manual Review

- `d001=1.2` OK; `1.1` is missing because there is no Track 1 event.
- `d002=1.3` OK.
- `d003=1.4` OK.
- `d004=1.5` OK.
- `d005=1.5` extra ball OK.
- `d006=2.0` OK.
- `d007=2.1` OK.
- `d008=2.2` OK.
- `d009=2.3` OK.
- `d010=2.4` OK.
- `d011=2.5` OK.
- `d012=3.0` OK.

dNNN source counts: `v3_chunker_fallback=11`, `retrospective_span=1`.
Delivery-window mp4 count: `12`.

## OpenScout / TPM

- `loop_e429_total=0`.
- OpenScout audit metadata is present.
- Delivery mp4s exist for all `12/12` delivery artifacts.
- One non-action mp4 is missing; treat as low-priority audit cleanup.

## Important Caveat

dNNN is still Track 1-triggered, not a fully decoupled Track 2 source of truth.
OpenScout continuous quality remains separate future work.

## Recommended Next Work

1. Fix first-ball / mid-innings cold-start missing `1.1`.
2. Design a true decoupled Track 2 delivery stream and join table.
3. Only then scale to a longer replay or full match.

## Commit Summary Draft

This work validates the 10-minute KKR/DC guard-strip fixes with a clean cache
preflight. It confirms the missed `1.3 DOT`, false post-ad `2.1 DOT`, real
`2.1 1_RUNS`, and duplicate `Wd` regressions are resolved in the bounded clip,
while documenting the remaining `1.1` Track 1 gap and the Track 2 decoupling
boundary.
