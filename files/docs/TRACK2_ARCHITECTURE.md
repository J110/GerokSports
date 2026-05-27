# Track 2 Architecture

Track 2 is the video-delivery side of the system. Its job is to create
inspectable delivery clips from the broadcast video and, eventually, a
delivery stream that can be joined to Track 1 ball events.

Current architecture has two different artifact families:

1. **OpenScout continuous clips** under
   `files/logs/openscout_deliveries/<session>/delivery_*.mp4`.
   These are the intended decoupled Track 2 stream. They are produced from
   OpenScout action spans and do not require Track 1 to emit a ball event.
2. **Score-event `dNNN` windows** under
   `files/logs/deliveries/<session>/dNNN/delivery_window.mp4`.
   These are triggered by Track 1 score events. They are useful for debugging
   and were validated on the KKR/DC 10-minute slice, but they are not a fully
   decoupled Track 2 source of truth.

## Current Flow

```text
Broadcast video
  |
  +-- FrameSource -> Track 1 scoreboard/state pipeline
  |      |
  |      +-- emits ball events
  |      +-- writes files/logs/deliveries/<session>/scout_raw.jsonl
  |      +-- triggers dNNN delivery-window cuts
  |
  +-- OpenScout decoupled loop
         |
         +-- writes logs/openscout-<session>.jsonl
         +-- writes files/logs/openscout_deliveries/<session>/delivery_*.mp4
```

## Track 1 Event Windows

`dNNN` windows are created by `DeliveryWindowRecorder` when Track 1 emits a
ball event. The event timestamp is used to select a video span:

- a retrospective bowler/action span when one is safe enough;
- otherwise a delayed-score fallback window from `event_ts - 24s` to
  `event_ts - 4s`;
- skipped only for rejected phantom events.

This path is intentionally still tied to Track 1. If Track 1 misses a ball,
there is no corresponding `dNNN` clip. If Track 1 emits a false event, `dNNN`
can contain a non-delivery even when Track 2’s lower-level detection is fine.

## OpenScout Continuous Clips

OpenScout runs in a decoupled loop and classifies frames as action, replay,
ad, umpire, other, or null. Committed action spans are written by
`OpenScoutDeliveryWriter`.

The writer now persists audit metadata with every span:

- `clip_start_ts`
- `clip_end_ts`
- `mp4_path`
- `frames_written`
- `mp4_exists`
- `frame_source_error`
- `compile_error`
- `note`

This makes it possible to distinguish “span existed but frame buffer was
empty” from “mp4 compilation failed.”

OpenScout continuous clips are the right foundation for a truly decoupled
Track 2 stream, but their quality still needs separate validation. Recent
manual review found that OpenScout can still include pre-delivery,
post-delivery, replay, or partial-delivery clips.

## Desired End State

Track 1 and Track 2 should produce independent streams:

```text
Track 1 ball events
  over.ball, score delta, extras, batters, bowler

Track 2 delivery clips
  delivery clip, action span, timing, visual metadata

Join table
  Track 1 event <-> nearest Track 2 delivery clip
```

With this design:

- a Track 1 false event does not create a Track 2 delivery;
- a Track 2 delivery can exist even when Track 1 misses the ball;
- mismatches become join/audit rows instead of hidden coupling.

## Validated 10-Minute Slice

Clean validation session:
`replay_kkrdc_10min_guardstrip_clean_20260527_100933`.

Track 1 result:

- `matched=11`
- `missing=1`
- `phantom=1`
- `divergences=111`
- duplicate `Wd` absent
- false post-ad scoreless `2.1 DOT` gone
- real `2.1 1_RUNS` emitted correctly
- remaining missing ball: `1.1`

Track 2 `dNNN` manual review:

- `d001=1.2` OK; `1.1` missing because Track 1 did not emit it
- `d002=1.3` OK
- `d003=1.4` OK
- `d004=1.5` OK
- `d005=1.5` extra ball OK
- `d006=2.0` OK
- `d007=2.1` OK
- `d008=2.2` OK
- `d009=2.3` OK
- `d010=2.4` OK
- `d011=2.5` OK
- `d012=3.0` OK

OpenScout and rate-limit result:

- `loop_e429_total=0`
- OpenScout audit metadata present
- delivery mp4s exist for all delivery artifacts
- one non-action mp4 missing, low-priority audit cleanup

## Configuration

Recommended bounded-replay profile:

```bash
export USE_OPEN_SCOUT=1
export OPENSCOUT_DECOUPLED=1
export USE_OPEN_SCOUT_SPANS=0
export OPENSCOUT_TPM_BUDGET=30000
export OPENSCOUT_DECOUPLED_TARGET_INTERVAL_S=5.0
export OPEN_SCOUT_MAX_TOKENS=120
export SCOUT_RAW_DUMP=1
```

`USE_OPEN_SCOUT_SPANS=0` remains the safe default. OpenScout should continue
to run as shadow telemetry until the continuous delivery stream and join table
are validated.

## Next Work

1. Fix the Track 1 missing first visible ball (`1.1`) in mid-innings
   cold-start slices.
2. Improve OpenScout continuous clip quality so it rejects replay,
   pre-delivery, post-delivery, and partial spans.
3. Build the Track 1/Track 2 join table.
4. Promote OpenScout continuous clips to the primary Track 2 artifact only
   after manual clip quality is acceptable.
5. Scale from the 10-minute KKR/DC slice to longer replay and then full-match
   validation.
