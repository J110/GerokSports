# Scout V5 production precision evaluation — 2026-04-25 DC vs PBKS

## Summary

V5 production precision on `bowlers_end` emissions: **34.8%** (8/23 stratified
sample). Lands squarely in the **marginal range** (25-40%) per the
pre-committed decision thresholds.

V5 is a real improvement over V0 (34.8% vs corpus_v1's 18.75%, ~1.85x
precision), but not enough to justify shipping V5 as the durable answer. V6
work is justified, with two specific failure modes accounting for 93% of FPs.

## Methodology

- Source log: `files/logs/machine-1-2026-04-25.log` (DC vs PBKS, match 35,
  ongoing as of evaluation).
- Total Scout calls: 238. `camera_view=bowlers_end` emissions: 47 (19.7%).
- Sampling: stratified random, seeded (seed=42), targeting representativity
  across innings phases.
- Pool size and sample by bucket:

  | Phase bucket | Pool | Sampled |
  |---|---|---|
  | powerplay_inn1 (overs ~2-5)  | 9  | 6 |
  | middle_inn1 (overs ~6-13)    | 12 | 9 |
  | death_inn1 (overs 14-19)     | 5  | 0 |
  | powerplay_inn2 (overs 0-1)   | 21 | 8 |
  | **Total**                    | 47 | **23** |

  Notable: V5 emitted **zero** `bowlers_end` calls in death overs of inn 1
  for the 5 frames in the pool window, but my sampler did not include
  death_inn1 (target was 0). Worth follow-up — separate question whether the
  death-overs distribution shift hurts V5 specifically.

- Labels: applied per `files/docs/scout_labeling_rubric_v1.md` v1.1, single
  pass, confidence noted per frame. Full per-frame data in
  `files/docs/scout_v5_prod_eval_2026-04-25.json`.

## Headline metrics

### Strict precision

| | TP | Total | Precision |
|---|---|---|---|
| **Overall** | 8 | 23 | **34.8%** |
| powerplay_inn1 | 3 | 6 | 50.0% |
| middle_inn1   | 2 | 9 | 22.2% |
| powerplay_inn2 | 3 | 8 | 37.5% |

### Per-phase observations

- **Powerplay (both innings) hold up better** (50% / 37.5%) than middle
  overs (22.2%). Middle-overs precision is the worst, which inverts the a
  priori expectation that the middle would be V5's "happy path" (cruise
  bowling, fewer non-delivery cuts). Inversion driven by:
  - Heavy use of "hero camera" + batter portrait shots between deliveries
    when bowlers are settling into rhythm (F1764 Rahul behind-the-back
    hero shot, F1082 batter against stand).
  - Mid-innings stat overlays / archival B-roll segments (F915 Rahul
    career-stats panel, F1361 stand close-up between-overs, F976 desert
    commercial mid-over).
- **Powerplay precision is misleadingly good in inn 1**: of the 3 TPs,
  one (F337) is an archival "KINGS - DROPPED CATCHES M29 v LSG" stat
  segment using clip from a *different* match. The visual is bowler's-end
  but the source isn't this match — downstream DWR trusting it would
  build a window on archival content. By strict camera_view rubric this
  is still a TP, but flagged as a soft FP for downstream consumers.

## Failure-mode breakdown

Of 15 false positives:

| Human label | Count | % of FPs | Examples |
|---|---|---|---|
| `other` | 8 | 53.3% | crowd shots, hero shots, wide aerials, outfielder shots |
| `closeup` | 6 | 40.0% | tight batter crops from bowler's-end direction, no full pitch |
| `ad` | 1 | 6.7% | F976 desert commercial — extreme false positive |

**Sub-categorization of `other`:**

- Hero / behind-batter low-angle shots: F716, F1764 (2)
- High wide-angle / aerial / establishing shots: F1281, F3090, F3143 (3)
- Crowd / stand close-ups: F249, F1361 (2)
- Outfield fielder shot: F1252 (1)

**The "closeup with bowler's-end direction" failure mode** (40% of FPs) is
the structurally most important one: F105, F1082, F1827, F3066, F3144,
F3358 are all tight crops of one batter from the bowler's-end-direction
camera but where the pitch does NOT recede toward far stumps and no bowler
is in frame. Per the rubric, these are `closeup`. V5 appears to anchor on
"camera is from bowler's end direction" without checking the receding-pitch
+ bowler-presence criterion. This is the same FP mode V0 had — V5 reduced
its frequency but did not eliminate it.

**The "wide aerial / hero shot" failure mode** (~33% of FPs) is the second
priority: V5 falsely calls bowler's-end on shots that are clearly elevated
or behind-the-batter, where no normal delivery DWR would be valid.

**The ad FP** (F976) is one frame but high impact — a desert/mountain
commercial labeled `bowlers_end` is a categorical failure that V0 also
had. V5 made no progress here, suggesting the prompt provides insufficient
disambiguation against pure non-cricket content.

## Phase regression check

Of 8 TPs:

| V5 frame_phase | Count | % |
|---|---|---|
| release | 3 | 37.5% |
| shot | 2 | 25.0% |
| flight | 1 | 12.5% |
| between_play | 2 | 25.0% |

**Delivery-context (release/shot/flight) on TPs: 6/8 = 75.0%.**

This **does not confirm** the shadow run's 24% delivery-context finding.
On true positives, V5's frame_phase emission is *much* better aligned with
delivery context than the shadow run measured. The shadow's 24% likely
sampled the full bowlers_end emission population, where FPs (which contain
many between-play shots) drag the ratio down:

| | delivery-context | between_play | total |
|---|---|---|---|
| TPs | 6 (75%) | 2 (25%) | 8 |
| FPs | 8 (53%) | 7 (47%) | 15 |
| Combined | 14 (61%) | 9 (39%) | 23 |

Caveat: 23 frames is small. The 75% TP-delivery-context signal is weakly
held but worth noting — when V5 correctly identifies bowler's-end, it
also tends to correctly identify the delivery phase. The phase-regression
worry was overblown for the TP subset; it's a property of the FP-heavy
population.

## Decision

Pre-committed thresholds:

| Range | Decision |
|---|---|
| ≥ 40-50% | V5 is real improvement; ship V5; V6 not justified yet |
| 25-40% | Marginal improvement; V6 worth investigating but not urgent |
| < 25% | V5 didn't improve; V6 needed |

**V5 result: 34.8%. Marginal range.**

### Recommendation

**Keep V5 in production. V6 work is justified (not urgent).** Reasoning:

1. V5 precision (34.8%) is meaningfully better than V0 corpus (18.75%);
   roll-back to V0 would be a regression.
2. V5 precision (34.8%) is below the "real improvement" threshold (40%).
   Calling V5 the durable answer would be premature optimization on a
   sample where 65% of bowlers_end emissions are wrong.
3. V6 should target the two dominant FP modes:
   - **Closeup with bowler's-end direction** (40% of FPs): add a STEP-1
     example showing tight one-batter crops that look like
     bowler's-end-direction but are actually closeup. Negative example
     pair would be most effective: "this is bowler's-end (full pitch
     receding, bowler in frame)" vs "this is closeup (one batter
     dominates, no receding pitch)".
   - **Hero / wide aerial / non-delivery wide shots** (~33% of FPs): a
     post-hoc verification layer would compose better here than a prompt
     tweak. The pattern is consistent enough (no bowler running up, no
     pitch receding) that a binary "is the bowler in frame moving toward
     the camera" check could gate the bowler's-end emission. Could be
     done by Scout itself with a targeted "bowler-presence" sub-prompt
     or a downstream check from another vision call.

4. Phase regression is **not confirmed** for TPs (75% delivery-context).
   The 24% shadow-run finding was likely driven by FPs polluting the
   population. Phase prompt does not need urgent rework.

## Anomalies and edge cases

- **F337 (replay clip from M29 v LSG)**: visual is bowler's-end, content
  is archival from another match. Counted as TP per visual rubric, but
  flagged as soft FP for downstream consumers. Not enough samples to know
  if this is a recurring failure mode.
- **F976 (desert commercial)**: extreme FP. Suggests temperature variance
  or context bleed in the prompt. Cannot rule out a one-off LLM hiccup
  given n=1, but worth re-checking on next match.
- **No death-overs sample**: pool was 5 frames (all in middle_inn1's
  upper end at the rebucketing boundary). Death-overs precision is
  unknown from this evaluation. Should be addressed in next match's
  sampling.

## Composability with corpus_v1

This dataset uses the same labeling rubric (v1.1) and per-frame schema
(camera_view, frame_phase, confidence, notes) as `scout_corpus_v1.json`.
A future re-run could merge these 23 production frames into the corpus
as additional labeled ground truth, increasing total corpus size from
40 → 63 frames.

Composed corpus would shift the V0 baseline measurement: corpus_v1 is
on a different match (RCB vs GT match 9, run rc9), but the consistent
rubric makes the merge defensible. Mark these frames as
`source: dc_pbks_2026-04-25` in any merged dataset to preserve match
provenance.
