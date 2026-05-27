# Track 2 Status

Status date: 2026-05-27.

Track 2 is usable for score-event-indexed `dNNN` clip review on the validated
10-minute KKR/DC slice, but it is not yet a fully decoupled delivery source of
truth.

## Current Verdict

Validated:

- Track 1-triggered `dNNN` windows can produce correct delivery clips when
  Track 1 emits the right event.
- The delayed-score fallback window is effective for this broadcast shape.
- The over-broad retrospective-span rejection regression was fixed.
- OpenScout can run with throttling and no TPM cascade.
- OpenScout delivery metadata is now auditable.

Not yet validated:

- OpenScout continuous clips as the primary decoupled Track 2 stream.
- A join table between Track 1 ball events and Track 2 delivery clips.
- Full-match behavior.

## Latest Clean Validation

Clean validation session:
`replay_kkrdc_10min_guardstrip_clean_20260527_100933`.

Preflight:

- `files/match_state_cache.json` was absent before replay.
- Replay logged no `HOT-RESUME`.

Track 1:

- `matched=11`
- `missing=1`
- `phantom=1`
- `divergences=111`
- `1.3 DOT` emitted
- false post-ad scoreless `2.1 DOT` gone
- `2.1 1_RUNS` emitted correctly
- duplicate `Wd` absent
- remaining missing ball: `1.1`

Track 2 `dNNN` review:

- `12/12` delivery-window mp4s exist.
- Manual review found all emitted `dNNN` windows contain deliveries.
- `1.1` has no clip because Track 1 did not emit that ball.
- `d001` starts at `1.2`.
- `d002` through `d012` cover `1.3` through `3.0`.

OpenScout / TPM:

- `loop_e429_total=0`
- OpenScout audit metadata present
- delivery mp4s exist for all delivery artifacts
- one non-action mp4 missing, low priority

## What Changed In This Validation Batch

Track 1 guard fixes:

- duplicate wide signature removed;
- false post-ad scoreless legal tick suppressed;
- normal scoreless legal ticks allowed again when strong live strip evidence
  is present;
- advertisement frames now arm the dead-time guard before early continue.

Track 2 fixes:

- delayed-score fallback window changed to `event_ts - 24s` through
  `event_ts - 4s`;
- retrospective-span rejection changed from a hard `event_ts - 4s` cutoff to a
  `2.5s` safe-margin threshold plus dead/replay/post-action rejection;
- `window_debug.json` records retrospective safe margin and rejection
  threshold;
- OpenScout delivery writer metadata now records clip bounds, mp4 path,
  frames written, mp4 existence, and errors.

## Known Residuals

1. Track 1 misses `1.1` in the 10-minute mid-innings clip.
2. `dNNN` windows remain Track 1-triggered; they are not the final decoupled
   Track 2 architecture.
3. OpenScout continuous clip quality still needs work. Manual review of the
   newly visible continuous clips found pre-delivery, post-delivery, replay,
   and partial-delivery artifacts.
4. No full-match validation has been run after these fixes.

## Operational Guidance

For bounded replay validation, use:

```bash
export USE_OPEN_SCOUT=1
export OPENSCOUT_DECOUPLED=1
export USE_OPEN_SCOUT_SPANS=0
export OPENSCOUT_TPM_BUDGET=30000
export OPENSCOUT_DECOUPLED_TARGET_INTERVAL_S=5.0
export OPEN_SCOUT_MAX_TOKENS=120
export SCOUT_RAW_DUMP=1
```

Before every replay:

```bash
rm -f files/match_state_cache.json
test ! -e files/match_state_cache.json
```

Treat any replay that hot-resumes from `files/match_state_cache.json` as
invalid for Track 1/Track 2 validation.

## Recommended Next Work

1. Fix Track 1 cold-start handling for the missing first visible ball (`1.1`).
2. Audit and tighten OpenScout continuous span quality.
3. Build a Track 1/Track 2 join table.
4. Validate a longer replay only after the 10-minute residuals are understood.
5. Promote Track 2 from score-event-indexed `dNNN` windows to a true decoupled
   delivery stream only after continuous clip quality is acceptable.
