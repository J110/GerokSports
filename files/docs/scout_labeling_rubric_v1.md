# Scout prompt labeling rubric — v1.2 (2026-04-25)

## Revision history

- **v1.2 (2026-04-25)**: Methodology note added — distinguish phase
  precision on camera_view TPs from phase precision on the full
  emission population; sampler bucket-coverage requirement added.
- **v1.1 (2026-04-24)**: EC-6 added (wide elevated off-axis pitch → `side_on`);
  `graphic` criterion clarified (overlay >30% applies even with live action
  visible in remaining area); interview-with-sponsor-wall note added to
  `closeup`.
- **v1 (2026-04-25)**: initial rubric.

Reusable criteria for human-labeling broadcast frames against Scout's
`camera_view` and `frame_phase` schemas. Used as ground truth for shadow-run
validation of prompt tightening variants (Part B and future prompt work).

## Purpose

Scout (Groq `groq/compound-beta` at the time of writing) classifies broadcast
frames into two enums that drive DWR window selection, AdaptiveSleep cadence,
BallAnalyzer tagged buffer admission, and the scoreboard XI-REJECT override.
Precision failures in these labels cause: phantom delivery windows, wasted
Groq calls during dead time, polluted delivery-sampling buffer, and false XI
promotions.

This rubric defines what a human labeler considers the correct `camera_view`
and `frame_phase` for any broadcast frame, so shadow-run precision/recall can
be measured against a fixed standard rather than drifting intuition.

## Labeling philosophy

Three principles, in order:

1. **Binary criteria where possible.** Each label has required conditions.
   If any fails, the label does not apply. No "mostly bowlers_end" verdicts.
2. **Consumer-aligned.** The labels describe what a downstream consumer
   *should* see. A frame is `bowlers_end` iff a downstream DWR that trusted
   this label would build a correct delivery window. Label what we want
   Scout to output, not what Scout might plausibly say.
3. **Document edge cases atomically.** If a frame doesn't match any label
   clearly, update this rubric *before* labeling the frame, and retro-apply
   the updated rubric to all previously labeled frames in the same session.

## `camera_view` labels

### `bowlers_end`

**Required (ALL must hold):**

1. Camera is positioned behind one end of the pitch, looking along the
   pitch toward the stumps at the opposite end.
2. The pitch is visible as a strip receding away from the camera toward
   the far stumps. The batter at the far crease (if present) is in the
   upper half of the frame and typically small.
3. The frame is live action or the moment immediately after (not slow-motion
   replay, not a graphic overlay, not a wide angle showing the whole field
   from the side).
4. A legal ball could be delivered on-screen from this camera angle (the
   camera is at the end the bowler is delivering from, or immediately
   behind/above it).

**Does NOT disqualify bowlers_end:**

- Non-striker or umpire partially occluding the batter
- Bowler already out of frame because the ball has been released and the
  camera has not yet panned
- Ball in flight or just struck
- Scoreboard strip visible at bottom of frame (it always is)

**Disqualifies (any one forces a different label):**

- Face or upper body of any single person fills >35% of the frame
  → `closeup`
- Pitch runs horizontally across frame, camera is square to it → `side_on`
- Slow-motion motion blur, "REPLAY" badge, spider-cam, or visible
  slow-mo artifacts → `replay`
- Any broadcaster graphic covers >30% of frame → `graphic`
- Commercial / sponsor / non-cricket content → `ad`

### `side_on`

**Required:**

1. Camera is square to the pitch from the sideline (third-man, fine-leg,
   square-leg, deep-cover) OR ground-level sideline angle.
2. Pitch runs approximately left-to-right or right-to-left across the
   frame, NOT receding away.
3. Not a slow-motion replay (even if technically a square angle).

**Typical contents:** fielder chase to the boundary, crowd-side angle of a
big hit, square-leg umpire's perspective, low-angle wide shot.

### `closeup`

**Required:**

1. A player's face or upper body is the dominant visual element, filling
   >35% of the frame.
2. The pitch does NOT recede from the camera toward far stumps. (If it
   did, the label would be `bowlers_end` with a partial occlusion; see
   bowlers_end rule.)

**Explicit:** stumps visible in the background does NOT disqualify from
closeup. A batter at the striker's end with stumps visible behind them is
`closeup`, because the pitch is going toward the camera (or sideways), not
away from it.

**Examples:**

- Batter face close-up between deliveries
- Bowler walking back to mark, face/shoulders dominant
- Fielder reaction after a dropped catch or dismissal
- Captain directing the field
- Coach in the dugout
- Crowd individual
- **Post-match / pitch-side reporter interview with a player**, even if the
  background is a dense wall of sponsor logos. The subject is a human in
  closeup; a logo wall does not promote the frame to `graphic`.

### `replay`

**Required:**

1. Slow-motion motion blur, "REPLAY" badge, spider-cam swoop, super-slow
   ball-contact shot, OR visual signature of a replay (hawkeye-like
   reconstruction, wagon-wheel overlay, ball-tracker).
2. OR: identical action to a frame seen ≤5s earlier, shown from a
   different angle.

Replay overrides bowlers_end: a slow-mo bowler delivery shot is `replay`,
not `bowlers_end`.

### `graphic`

**Required:**

1. A broadcaster graphic covers >30% of the frame, OR the frame is
   substantially a score summary / partnership stats / player profile /
   sponsor card / ball-by-ball graphic / hawkeye pitch-map.
2. Not a commercial break (those are `ad`).

Partial overlay graphics (speed gun, run rate corner badge, tournament
logo) do NOT qualify as `graphic` — they coexist with other labels.

**Clarification (v1.1):** Persistent broadcaster overlays (projected
score panel, stats strip, tournament graphic) that cover >30% of frame
area qualify as `graphic` **even if live cricket action is partially
visible in the remaining frame area**. The threshold applies to the
rendered overlay, not just the amount of action it obstructs.

**Rationale:** Consumer alignment — when an overlay occupies ~35-40% of
the frame (typical projected-score strip), Scout and downstream
consumers cannot reliably extract bowler motion, batter position, or
pitch geometry from the remaining area. DWR would open a delivery
window on a frame where it has incomplete visual information, producing
a corrupted clip. Tag as `graphic` to force downstream fallback.

### `ad`

**Required:**

1. Commercial content with no cricket action on-screen.
2. Sponsor placeholder between deliveries with no pitch visible.

### `other`

Anything else: pre-match presenters, drinks break with no cricket action,
post-match presentation ceremony, technical difficulty cards.

## `frame_phase` labels

Only meaningful for frames where `camera_view` is `bowlers_end` or (with
caveats) `closeup`-adjacent. For `side_on`, `replay`, `graphic`, `ad`,
`other`, the phase label is forced to the matching non-action value.

### `runup`

Camera behind the bowler. Bowler is walking or running toward the crease,
ball in hand, BEFORE entering the delivery stride. Batter typically taking
guard at far crease.

### `release`

**Required:**

1. Camera is behind the bowler looking down the pitch.
2. Bowler is in the delivery stride: front foot about to land OR
   has just landed, arm coming through OR at the top of the action.
3. Ball may still be in the hand or just released.

Does NOT require batter visible in frame (bowler's delivery action can be
close-framed just before release).

### `flight`

Camera behind the bowler. Ball has visibly left the bowler's hand and is
traveling toward the batter (or the bowler is in follow-through, implying
ball is in flight). Batter preparing to play.

### `shot`

Camera behind the bowler (or tight over-the-shoulder behind stumps). Bat
is in motion through the shot OR just after contact. Ball may be visible
heading toward the field.

### `post_shot`

Shot completed. Batter has completed shot motion. Camera may still be
behind the bowler briefly, or has cut to follow the ball, or to a
reaction. Pre-fielder-reaction window.

### `fielder_reaction`

Camera on a fielder chasing, diving, catching, throwing, OR celebration
huddle at stumps.

### `replay`, `graphic`, `advertisement`, `between_play`, `other`

Forced from the `camera_view` context when applicable. `between_play` is
the catchall for "cricket is happening but no delivery is in progress" —
bowler walking back, field changes, drinks, umpire consultation.

## Confidence flagging

Each label carries one of three confidence levels:

- **high**: rubric applies unambiguously. If the rubric says
  "pitch recedes toward far stumps" and the frame clearly shows this,
  the label is high-confidence.
- **medium**: rubric applies, but near a boundary. Example: pitch recedes
  but batter is so occluded by umpire it could be argued the frame is a
  wider `bowlers_end` or a `closeup`. Label stays as written but worth
  flagging.
- **low**: rubric is ambiguous for this frame. Needs human discussion
  before being used as ground truth. Expected to be ≤10% of corpus; if
  higher, rubric is insufficiently specified.

Low-confidence frames are excluded from precision/recall calculation and
reported separately as a "labeler uncertainty" rate.

## Edge cases (update atomically)

Each entry below is a concrete edge case encountered during corpus
labeling, with the decision and the rationale. This section is expected
to grow as new corpora are labeled.

### EC-1 — Bowler close-up at start of run-up, pitch visible behind

Frame shows bowler's face/torso filling ~50% of frame, pitch and far
stumps visible in the upper background. Bowler is not yet in delivery
stride.

**Label:** `closeup` + `runup` (NOT `bowlers_end`, because face is the
visual subject even though pitch is visible).

**Rationale:** Consumer alignment — this frame should not open a DWR
delivery window. It should signal "bowler is preparing" (runup), not
"active delivery camera" (bowlers_end).

### EC-2 — Batter close-up at striker's end, stumps visible behind

Frame shows striker's face/torso filling ~60% of frame, striker's end
stumps visible directly behind the batter.

**Label:** `closeup` + `post_shot` or `between_play` (depending on
whether this directly follows a delivery).

**Rationale:** Pitch is NOT receding away from the camera — it's going
toward the camera (or beyond the batter). This is a closeup, not bowlers_end.

### EC-3 — Wide drone/crane shot over field, pitch visible

Frame shows full field from elevated angle, pitch visible in the middle,
players moving.

**Label:** `side_on` (NOT `bowlers_end`, because camera is not behind the
bowler's end; it's above/side).

**Rationale:** A legal ball cannot be delivered on-screen from this
angle; the geometry is wrong for DWR.

### EC-4 — Hawkeye / wagon-wheel / pitch-map overlay on live feed

Frame is an overlay of a ball trajectory or pitch-map graphic on top of
what would otherwise be a bowlers_end live frame.

**Label:** `graphic` + `graphic` (NOT `bowlers_end`, because the graphic
is now the dominant subject).

**Rationale:** Overlay obscures enough of the active-play context that
downstream DWR should not treat this as a delivery frame.

### EC-5 — Partial replay (pitch-down-the-middle slow-mo with no badge)

Frame is behind the bowler looking down the pitch, bowler mid-action,
but motion is slow (slow-motion replay), no explicit REPLAY badge.

**Label:** `replay` (if slow-motion is visually obvious) or `bowlers_end`
(if motion rate looks normal — sometimes broadcast pacing is slower
without being a replay). Confidence: medium.

**Rationale:** Slow-motion replay of a delivery would double-count in
DWR. When in doubt, label `replay` to err on the side of exclusion.

### EC-6 — Wide elevated shots with pitch visible but off-axis

Frame shows an elevated view from the side with the pitch visible but
not receding along the camera axis. Pitch runs horizontal, diagonal, or
at an angle across the frame. Typical examples: broadcaster aerial
between deliveries, fielder-chase wide view, elevated square-leg angle.

**Label:** `side_on` (NOT `bowlers_end`).

**Rationale:** Consumer alignment. DWR opening a delivery window on an
off-axis wide shot would expect subsequent frames to maintain
pitch-receding-down-axis geometry. That expectation breaks as soon as
the broadcast cuts back to live — the resulting clip would splice
incompatible camera angles. Pitch *visibility* is not sufficient for
`bowlers_end`; the camera axis must be **along** the pitch (behind one
end, looking toward the opposite stumps).

**Binary test:** trace the pitch in the frame. If it recedes from a
point near the foreground to a point deeper in the frame along the
camera's line of sight → `bowlers_end`. If it runs across the frame at
any angle (including gently diagonal) → `side_on`.

## Methodology notes

### M-1 — Phase precision: TP-conditional vs full population

When evaluating `frame_phase` accuracy, distinguish between two distinct
quantities:

- **TP-conditional phase precision** = of frames where Scout's
  `camera_view` is correct AND the human label is the same `camera_view`,
  the fraction where Scout's `frame_phase` is also correct (delivery-
  context labels {release, shot, flight} matching a delivery-context
  ground truth).
- **Population phase precision** = of frames where Scout emitted a given
  `camera_view`, the fraction where Scout's `frame_phase` matches the
  human-labeled phase (regardless of whether the camera_view itself was
  correct).

These measure different things. TP-conditional phase precision measures
the phase classifier in isolation. Population phase precision conflates
camera_view errors with phase errors: when Scout falsely emits
`bowlers_end` on a crowd shot, it usually correctly emits `between_play`
for the phase, which is "correct" given the wrong camera_view but
unhelpful as a diagnostic of the phase classifier.

**Empirical example (V5 prod eval 2026-04-25):**

- TP-conditional delivery-context rate: 6/8 = 75.0%
- Population delivery-context rate: 14/23 = 60.9%
- FP-only delivery-context rate: 8/15 = 53.3%

The 24% delivery-context figure from the v5 shadow run was a population
measurement that included FP-driven `between_play` emissions. The
75% TP-conditional figure is the correct quality metric for the phase
classifier. Carry forward both numbers when reporting; do not conflate.

### M-2 — Sampler bucket-coverage requirement

Stratified samplers must emit a bucket-coverage report alongside the
sample. For any (phase_bucket, sampling_target) pair, if the pool size is
non-zero but the sample count for that bucket is zero, the sampler must
log a warning. This prevents silent under-coverage of distribution-shift
regions (e.g. death overs, innings break) where V5 may behave differently.

Concrete: V5 prod eval 2026-04-25 had `death_inn1_pool=5` but
`death_inn1_sampled=0`. Death-overs precision is therefore unknown from
that evaluation. Future runs must either re-sample to fill the bucket or
explicitly document the gap as "pool=N, sampled=0 by design" with a
reason.

## Output format

Labeled frames stored in a JSON file (`corpus_v1.json`) with one entry
per frame:

```json
{
  "frame_id": "f123",
  "source_session": "rcb_gt_rc9_commentary_203904",
  "frame_path": "debug_frames/f123_scoreboard.jpg",
  "subset": "closeup_heavy | disambiguation | recall_control | edge_case",
  "human_camera_view": "bowlers_end | side_on | closeup | replay | graphic | ad | other",
  "human_frame_phase": "runup | release | flight | shot | post_shot | fielder_reaction | replay | between_play | graphic | advertisement | other",
  "confidence": "high | medium | low",
  "notes": "free-form justification, especially for medium/low confidence",
  "scout_camera_view_observed": "bowlers_end",
  "scout_frame_phase_observed": "release"
}
```

The last two fields capture what Scout originally tagged, so the shadow
run can replay new prompt variants against the same frames and compare
against both human ground truth and Scout's original answer.
