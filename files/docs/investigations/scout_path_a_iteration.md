# Scout Path A iteration — v2 prompt + classifier negation guard

Date: 2026-05-03
Author: agent (follow-up to `scout_detection_baseline.md`)
Status: experiment landed alongside v1; **not yet shipped to production**.
Inputs: same 105-clip regression set as the v1 baseline.
Artifacts:
- `files/eyes/open_scout.py` — added `OPEN_PROMPT_V2`, `_active_prompt()` resolver gated on `OPEN_SCOUT_PROMPT_VERSION` (default `v1` → byte-identical production behaviour).
- `files/eyes/open_scout_classify.py` — `is_replay_pattern` now matches v2 BROADCAST tag, expanded substring list, plus negation guard.
- `files/scripts/path_a_baseline/run_scout_baseline.py` — `--prompt-version {v1,v2}` flag, parametric output paths.
- `files/scripts/path_a_baseline/scout_results_v2.jsonl` (1851 frames, 14 missing tags = 0.8% format-compliance miss).
- `files/scripts/path_a_baseline/clip_aggregates_v2.csv`.

---

## §1 Audit findings (Phase A)

Hand-checked the 81 frames in clips manually labelled `replay`:

| signal in v1 prose                   | hits / 81 |
|--------------------------------------|-----------|
| any of: `replay`, `slow`, `slo-mo`, `slow motion`, `SLOW`, `REPLAY` | **1** |
| `graphic` or `overlay`               | 81        |
| `sponsor`                            | 41        |

The single replay-class hit (`d057 f001`) was a **false positive** — Scout's prose
contained `"there is no indication of replay or slow-motion"` and the
substring matcher fired on `replay` without a negation guard.

Failure mode: **(a) the prompt asks the wrong question, plus (c) the
classifier needs negation handling.** Scout describes the cricket
content of a replay angle exactly the way it describes a live
delivery — the visual content is the same kinetic footage. v1's open-
prose prompt only invites Scout to mention "REPLAY tags" once in a
list of overlay examples and Scout effectively never volunteers
that observation when no explicit on-screen REPLAY label is present.
The persistent score-bar / sponsor graphics that fire on every frame
are not replay markers.

## §2 v2 prompt design rationale

Three things changed:

1. **Front-loaded broadcast-mode probe.** Before describing cricket,
   Scout must decide whether the frame is non-live based on a fixed
   menu of visual cues.
2. **Structured tag output.** First line of the response is one of
   `[BROADCAST: REPLAY | SLO-MO | TELESTRATOR | SPLIT-SCREEN | LIVE]`
   on a line by itself. This sidesteps the negation hazard — Scout's
   verdict is in a deterministic token, not buried in prose.
3. **Action description preserved.** The follow-on instruction still
   asks for camera framing and player kinetic verbs (`mid-stride`,
   `mid-swing`, …) so the existing rule-v2 binary classifier
   (`classify_v2_final`) keeps its signal.

Tag compliance: **1837 / 1851 frames (99.2%)** emit a well-formed tag
on the first line. The 14 misses are concentrated in eight clips
spread evenly across labels — Scout occasionally writes `[REPLAY]`
or omits the brackets. These fall through to the substring matcher
as in v1.

## §3 Keyword expansion rationale

`is_replay_pattern` was extended with three layers:

1. **High-precision tag match** for v2 BROADCAST tags. `[BROADCAST:
   REPLAY]`, `[BROADCAST: SLO-MO]`, `[BROADCAST: TELESTRATOR]`,
   `[BROADCAST: SPLIT-SCREEN]` map to `replay`; `[BROADCAST: LIVE]`
   short-circuits to non-replay.
2. **Substring expansion** to catch v2-style phrases when the tag is
   missing or v1 prose drifts toward the v2 vocabulary: `slo-mo`,
   `slo mo`, `telestrator`, `telestrator overlay`, `split-screen
   replay`, `slow-motion overlay`, `slow-motion footage`,
   `slow-motion replay`, `replay graphic`. Each was directly observed
   in v2 raw descriptions.
3. **Negation guard** — `is_replay_pattern` now refuses to match the
   substring layer if the prose contains any of `no indication of
   replay`, `no replay`, `no visible indicators of replay`, `without
   replay`, `not a replay`, `no slow(-)motion`, `no signs of replay`,
   `absent of replay`. Patches the v1 false positive observed in
   audit. The tag layer (1) is exempt — `[BROADCAST: REPLAY]` is a
   positive assertion regardless of the prose that follows.

`is_ad_pattern` was **not** expanded: only 3 ad clips (43 frames) in
the regression set, too small to fit reliable keywords. Deferred.

## §4 v1 vs v2 comparison

v1 numbers below are reproduced from `scout_results.jsonl` after the
classifier change (negation guard + tag matchers) — the v1 jsonl is
frozen so this is purely a re-aggregation.

### §4.1 Per-frame Scout-class confusion vs manual label

|               | v1                                             | v2                                                     |
|---------------|-----------------------------------------------|--------------------------------------------------------|
| real_delivery (n=1566) | action 56% / other 41% / replay 1% / umpire 1% | action **69%** / other 24% / **replay 6%** / null 1% |
| replay (n=81)          | action 53% / other 44% / replay **1%** / umpire 1% | action 38% / **replay 33%** / other 28%                |
| noise (n=161)          | other 62% / action 34% / replay 4%             | action 55% / other 35% / **replay 10%**                |
| ad (n=43)              | other 77% / action 21% / replay 2%             | action 56% / other 21% / **replay 19%** / null 5%      |

**Replay-tag fire rate on replay-labelled frames: 1.2% → 33%** (27×
lift). Decomposed: 8/81 (10%) emit explicit `REPLAY`, 19/81 (23%)
emit `TELESTRATOR`, 54/81 (67%) still emit `LIVE`. Target was 70%+ —
**not hit**.

False-positive cost on real_delivery: replay class fires on 6% of
delivery frames vs 1.3% in v1. 65 of those 94 false positives are
`TELESTRATOR`-tagged — Scout reads the persistent IPL `LEG/OFF` wagon
dial and the "8.7 Cr Views" overlay as analyst telestrator markings.

### §4.2 Per-clip aggregates

| label          | n  | action_ratio v1 | action_ratio v2 | max_run v1 | max_run v2 |
|----------------|----|-----------------|-----------------|------------|------------|
| ad             | 3  | 0.211           | 0.608           | 1.33       | 3.67       |
| noise          | 14 | 0.346           | 0.556           | 2.50       | 4.14       |
| replay         | 5  | 0.516           | **0.393**       | 6.00       | 4.40       |
| real_delivery  | 83 | 0.569           | **0.702**       | 6.52       | **9.76**   |

Direction-correct: v2 widens the delivery-vs-replay gap from
**0.05 → 0.31** mean ratio and from **0.52 → 5.36** mean max-run.
But ad and noise also drift upward — Scout's kinetic vocabulary
("mid-stride", "mid-swing") is more eagerly fired by the v2 prompt's
explicit list, which inflates `action` on borderline frames.

### §4.3 Per-clip non-LIVE tag ratio (v2 only — new signal)

Mean fraction of frames per clip whose first line is a non-`LIVE`
tag:

| label          | any non-LIVE (incl TELESTRATOR) | REPLAY+SLO-MO+SPLIT only |
|----------------|---------------------------------|---------------------------|
| ad             | 0.21                             | 0.21                      |
| noise          | 0.11                             | 0.09                      |
| real_delivery  | 0.05                             | 0.02                      |
| replay         | **0.30**                         | 0.11                      |

Excluding TELESTRATOR cleans the delivery side (max 0.14 across all
83 deliveries) but flattens replay (mean 0.11). With TELESTRATOR
included the replay mean is 0.30 but some delivery clips reach 0.73.

### §4.4 Threshold sweep (best F1)

| metric                                   | v1                          | v2                          |
|------------------------------------------|-----------------------------|-----------------------------|
| delivery vs all non-delivery, action_ratio | 0.911 @ T=0.19 (P 0.85, R 0.99) | 0.894 @ T=0.32 (P 0.83, R 0.96) |
| delivery vs all non-delivery, max_run    | 0.920 @ K=3 (P 0.88, R 0.96) | **0.934 @ K=5 (P 0.93, R 0.94)** |
| delivery vs ad+noise only, max_run       | 0.941 @ K=3                 | 0.940 @ K=5                 |
| delivery vs replay only, max_run         | 0.971 @ K=0 (label imbalance dominates) | 0.971 @ K=0 (same) |

`max_consecutive_action ≥ 5` on v2 is the new best operating point —
**F1 0.934 vs v1's 0.920**, ~1.4 pp absolute lift.

## §5 Verdict

**(b) Partial success.**

v2 is a clear net win along three axes and a clear miss on one:

- **Wins**:
  - Replay-tag fire rate 1.2% → 33% on replay frames (27× lift).
  - Delivery-vs-replay separation widens from 0.05 to 0.31 mean
    action_ratio gap.
  - Best aggregate F1 0.920 → 0.934 with `max_consecutive_action ≥ 5`.
  - Negation guard kills the v1 substring false-positive class;
    structured tag is robust to negated prose.
- **Misses**:
  - Did not hit the 70% target replay-tag fire rate. 67% of replay
    frames still emit `[BROADCAST: LIVE]` because the underlying
    cricket content of a replay angle is visually indistinguishable
    from a live delivery in a single frame.
  - TELESTRATOR is too aggressive on real_delivery (4% FP), driven
    by IPL persistent `LEG/OFF` wagon dial and view-count overlays.
  - Action vocabulary leaks: ad clips' action_ratio rose from 0.211
    to 0.608, noise from 0.346 to 0.556. v2 prompt's kinetic verb
    list nudges Scout to over-call `mid-stride` etc.

Recommendation:

1. **Land v2 prompt under the env-var flag in `BallAnalyzer`** and
   shadow-evaluate against live matches before flipping the default
   from `v1` → `v2`. The lift is real but partial.
2. **Tighten TELESTRATOR criteria** — either drop TELESTRATOR from
   `REPLAY_TAGS_V2` (replay-frame tag rate falls to 10%, but
   delivery FP drops from 6% to 1.9%), or rephrase the prompt to
   distinguish "drawn analyst telestrator" from "persistent
   broadcast dial graphic".
3. **Acknowledge the per-frame ceiling.** The 67% LIVE-tagged replay
   floor is a Scout-single-frame architecture limit, not a prompt
   bug. Closing the rest needs:
   - **temporal context** (ask Scout about a frame *and* its 1-2 s
     neighbours, or run multi-frame Scout), or
   - **motion-signal fusion** (slow-motion footage has distinctive
     optical-flow magnitude — cheap to measure with cv2 dense flow
     and combine with Scout's per-frame call), or
   - **Path B local CNN** seeded on this 105-label set.
4. **Do not rerun the v1→v2 prompt sharpening loop alone.** Future
   prompt edits will hit diminishing returns against the LIVE-tag
   ceiling. Allocate next bandwidth to (3) above.
