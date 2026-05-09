# P7 Diagnosis — Score frozen at 11 (frames 178-198)

Trace: `logs/trace/866ce150.jsonl`. P7 fired because every frame in
the window committed `score==score_before` with the same innings.
The score did not silently revert; three guards correctly refused
to commit any update, and their interaction prevents recovery.

## §1 Symptom

Frames 178-198 keep `scoreboard.score == 11`. P7's signature
(score-after equal to score-before across a sustained window)
matches exactly. No DETAIL line on the pipeline log shows a real
update during this stretch — the broadcast on screen has moved on.

## §2 Trace evidence

Reduced from `jq '... | {frame, ext, ui_after, committed}'`:

| frame | ftype       | ext.score | committed_changes (head)                                      |
|-------|-------------|-----------|---------------------------------------------------------------|
| 178   | SCOREBOARD  | 11        | `SCORE-INF-GATE:advance=7>6`, batters, bowler                  |
| 179   | SCOREBOARD  | 11        | `score→11`, `overs→2.4`, …                                    |
| 180-3 | SCOREBOARD  | 11/4/null | `score→11`, batters/bowler                                    |
| 184   | GRAPHIC     | null      | `FRAME_POISONED:None`                                         |
| 185   | SCOREBOARD  | 8         | `SCORE-INF-GATE:proposed=11<bat_sum=8+extras=7`, batters       |
| 186   | SCOREBOARD  | null      | `score→11` (no-op), batters reset to 0(0)                     |
| 198   | SCOREBOARD  | null      | `CORRECTION_BLOCKED:29`                                       |

Key state at the moment 198 fires: tracker score=11, extras=7,
batters Quinton de Kock=18(14) + Reeza Hendricks=6(7) → bat_sum=24.
The scorer proposed 29 (≈ bat_sum + small extras adjustment).
29 − 11 = 18, well over the +7 correction cap.

## §3 Per-guard analysis

### FRAME_POISONED  (`test_pipeline.py:7031,7100,9192-9209`)

**Defends against**: extractor output that has already been judged
unsafe (mid-innings 0-0(0.0), GRAPHIC frame whose score does not
match the tracker, and ~26 other upstream invariants). Once set,
`_frame_poisoned=True` causes the scorer branch to be skipped
entirely; `changes` is replaced with `["FRAME_POISONED:<raw>"]`,
and **`_correction_pending`/`_correction_count` are reset to None/0**
(lines 9207-9209).

**Why it fired at F184**: frame_type is GRAPHIC, all extractor
fields null → falls into the `else` branch at lines 7100-7112
(GRAPHIC, score does not "match" because it is None) → poisons
the frame. Behaves as designed for GRAPHIC; arguable for the
all-null sub-case.

### CORRECTION_BLOCKED  (`test_pipeline.py:3282-3293`, override at `9225-9249`)

**Defends against**: a single-frame score correction larger than
±7 runs (stale/corrupted strip OR legitimate recovery of a missed
state). Block-then-confirm: the first occurrence is rejected; if
the *same* proposed value re-appears for `_CORRECTION_CONFIRM`
consecutive frames, the override accepts it as recovery.

**Why it fired at F198**: cur=11, proposed=29, |Δ|=18 > 7. The
proposed value comes from the scorer's score_update (extractor
score is null this frame; the proposal is inferred from
bat_sum=24 + extras=5).

### SCORE-INF-GATE  (advance: `test_pipeline.py:3346-3428`; floor: `3308-3331`)

Two sibling rules sharing the marker prefix:

* **advance cap** (max +6 unsupported): `advance > bat_delta +
  extras_max` blocks. Fired at F178: cur=4, proposed=11, advance=7,
  bat_delta=0, extras_max=6 → reject. (Frame 179 committed score→11
  via a different code path — either innings_transition_suppressed,
  cold-start, or a `_state_recovery_suppress_until_frame` window;
  this is the upstream commit that planted the sticky 11.)
* **floor invariant** (proposed ≥ bat_sum + extras): fired at F185.
  Bat_sum after this frame's batter update = 8 (QDK 2 + RH 6),
  scoreboard extras.total = 7 (committed earlier), proposed = 11,
  floor = 15 > 11. Correctly identifies that score 11 is below
  the math floor implied by committed sub-totals. Note: the commit
  it blocks is a no-op (proposed equals current) — the gate
  serves as a *signal* but does not actually unstick anything.

## §4 Interaction analysis

Each guard, in isolation, is firing on a true positive:

* F184 GRAPHIC really is a frame with no usable score.
* F185 floor really is violated — 8 + 7 > 11.
* F198 +18 jump really is too large for one ball.

But they are not independent. Two coupling effects produce thrash:

1. **FRAME_POISONED resets the CORRECTION_BLOCKED consensus**
   (`9207-9209`). The 2-frame override is the *only* way out of a
   stuck high-delta state. Any GRAPHIC frame in the recovery
   window invalidates the streak, even though GRAPHIC frames are
   absence-of-evidence, not contradicting evidence. In a normal
   broadcast, GRAPHIC frames are routinely interleaved with
   SCOREBOARD frames, so the consensus rarely accumulates two in
   a row.
2. **Extractor instability prevents value-stable consensus**.
   Even when GRAPHIC frames don't intrude, the scorer's inferred
   `score_update.to` shifts as bat_sum/extras drift (frame 185
   proposes 11, frame 198 proposes 29). `_correction_pending`
   only counts identical proposals, so the set of "blocked
   proposals" never converges.

The SCORE-INF-GATE floor at F185 is informationally redundant
here (it blocks a no-op) — but it correctly indicates the bug:
score=11 was committed earlier despite being below the
bat_sum+extras floor. That is the upstream defect.

## §5 Root cause hypothesis

The persistent 11 was committed at **frame 179**, not at 198.
Frame 178 had already rejected the 4→11 advance (advance cap).
Frame 179 took a different path that bypassed the gate — most
likely `innings_transition_suppressed` or
`_state_recovery_suppress_until_frame` (gate is suppressed during
the cold-start/recovery window per lines 3308-3311). Once 11
became "tracker truth," the broadcast continued advancing while:

* extractor score readings became unreliable (null on GRAPHIC,
  stale 8 mid-stream, null again at 198),
* the +7 CORRECTION_BLOCKED guard refused the only legitimate
  recovery (jump to ~29),
* the consensus override needed to defeat that guard could not
  accumulate, because GRAPHIC frames invalidate it and
  inferred-proposal values drift.

In short: **the 11 commit at F179 was the bad commit; the three
guards F184/F185/F198 are downstream symptoms, not the cause.**
The floor at F185 is the most diagnostic of the three — it is
literally announcing "the committed score is below the math
floor."

## §6 Proposed fix

Three options, ordered by preference:

**(c) Address the upstream bad commit** — the F179 path that
allowed the +7 advance to commit. Tighten the
`innings_transition_suppressed` / state-recovery suppression so
that the SCORE-INF-GATE *advance* cap remains armed unless we
have positive evidence of a real transition (e.g., observed
innings flip, observed wickets jump, observed cold-start). This
is the root-cause fix: if 11 never lands, F185 and F198 don't
fire.

**(b) Make consensus-survive-poison the rule for GRAPHIC poison
only**. In `test_pipeline.py:9207-9209`, do not reset
`_correction_pending`/`_correction_count` when the poison reason
is "GRAPHIC frame" or "ext all-null". GRAPHIC frames carry no
contradicting evidence, only absence of evidence; they should
"skip", not "reset". Other poison reasons (mid-innings 0-0,
team-lock contradiction) keep the existing reset. This unblocks
recovery in any future stuck state without weakening the
poisoning model for genuinely bad data.

**(a) Lower-bound the CORRECTION_BLOCKED override on the
floor signal**. When the SCORE-INF-GATE floor has been firing for
N consecutive SCOREBOARD frames (proposed < bat_sum + extras),
treat that as positive evidence that the committed score is
stale and accept the next consistent CORRECTION_BLOCKED proposal
without requiring exact-value 2-frame consensus. Promotes a
diagnostic signal into a recovery signal.

(c) plus (b) is the recommended pair: (c) prevents the stick,
(b) gives a graceful exit if anything else sticks in future.

## §7 Risk

Each guard relaxation has a regression surface:

* **(c)** — narrowing the suppression window risks blocking
  legitimate cold-start commits where score genuinely advances by
  >6 in the first frame after innings start. Mitigation: gate the
  narrowing on `current_innings != 1 or scoreboard.score is not
  None`, so the very-first commit is unaffected; only subsequent
  frames inside the recovery window are re-armed.
* **(b)** — letting CORRECTION consensus survive GRAPHIC poison
  could let a wrong correction "win" if the GRAPHIC frames were
  hiding contradicting SCOREBOARD evidence. Mitigation: only
  survive GRAPHIC poison while the *clean* frames around it
  agree; require the streak frames to be SCOREBOARD-typed and
  count GRAPHICs as a hard skip (not a counted frame).
* **(a)** — using the floor as a recovery trigger weakens the
  guarantee that a single corrupted strip cannot mutate score.
  Mitigation: require N≥3 floor-violation SCOREBOARD frames AND
  the unblocking proposal to land within ±2 of (bat_sum+extras),
  matching the math floor rather than blindly trusting the
  scorer.

Existing test coverage in `test_recent_fixes.py:5789-7257`
exercises each gate's positive and negative cases independently;
adding interaction tests (poisoned-streak-during-correction-
consensus, floor-then-correction-recovery) is required before
any of these changes ship.
