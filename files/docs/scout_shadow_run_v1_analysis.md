# Part B shadow-run v1 — analysis

Corpus: `docs/scout_corpus_v1.json` (vv1.1, 41 frames)
Shadow run: `docs/shadow_run_v1.json` (984 calls = 41×8×3 reps)

Baseline (V0) = `scout_cam_original` stored in the corpus (what Scout emitted on the live RC9 run).  V1–V3 = majority-vote cam across 3 replicates at temperature=0.

## 1. Precision by camera_view tag

Strict precision: of frames the variant tagged X, fraction where the human label is X.  N = frames emitted by the variant.

| Variant | bowlers_end | closeup | side_on | graphic | other | ad | replay | Coverage-weighted |
|---|---|---|---|---|---|---|---|---|
| V0 | 15.2% (33) | 100.0% (6) | n/a | 100.0% (2) | n/a | n/a | n/a | 28.2% |
| V1 | 15.2% (33) | 100.0% (6) | n/a | 100.0% (2) | n/a | n/a | n/a | 28.2% |
| V2a | 14.7% (34) | 100.0% (5) | n/a | 100.0% (2) | n/a | n/a | n/a | 27.8% |
| V2b | 16.1% (31) | 75.0% (8) | n/a | 100.0% (1) | 100.0% (1) | n/a | n/a | 26.1% |
| V3 | 14.7% (34) | 71.4% (7) | n/a | n/a | n/a | n/a | n/a | 22.6% |
| V4 | n/a | 100.0% (4) | n/a | 100.0% (1) | 27.8% (36) | n/a | n/a | 96.7% |
| V4b | n/a | 100.0% (3) | n/a | n/a | 26.3% (38) | n/a | n/a | 96.2% |
| V5 | 31.2% (16) | 62.5% (16) | n/a | 42.9% (7) | 100.0% (2) | n/a | n/a | 36.2% |
| V6c | 33.3% (15) | 55.6% (18) | n/a | 50.0% (6) | 100.0% (2) | n/a | n/a | 37.1% |

Coverage-weighted precision is the sum of per-label precision weighted by Scout's pipeline-wide emission share for that label (from the 5-session A3 audit: bowlers_end 83.8%, closeup 13.5%, graphic 1.7%, other/ad 0.9%).  It estimates how much of Scout's real-world emission volume the variant would get right.

## 2. Recall by human label

Of frames HUMAN-labeled X, fraction the variant tagged X.  N = number of human-labeled frames with that label.

| Variant | closeup (N=12) | other (N=10) | graphic (N=7) | side_on (N=7) | bowlers_end (N=5) |
|---|---|---|---|---|---|
| V0 | 50.0% | 0.0% | 28.6% | 0.0% | 100.0% |
| V1 | 50.0% | 0.0% | 28.6% | 0.0% | 100.0% |
| V2a | 41.7% | 0.0% | 28.6% | 0.0% | 100.0% |
| V2b | 50.0% | 10.0% | 14.3% | 0.0% | 100.0% |
| V3 | 41.7% | 0.0% | 0.0% | 0.0% | 100.0% |
| V4 | 33.3% | 100.0% | 14.3% | 0.0% | 0.0% |
| V4b | 25.0% | 100.0% | 0.0% | 0.0% | 0.0% |
| V5 | 83.3% | 20.0% | 42.9% | 0.0% | 100.0% |
| V6c | 83.3% | 20.0% | 42.9% | 0.0% | 100.0% |

## 3. Emission distribution (cam counts per variant)

Where does each variant place the 41 frames?

| Variant | bowlers_end | closeup | graphic | other |
|---|---|---|---|---|
| V0 | 33 | 6 | 2 | 0 |
| V1 | 33 | 6 | 2 | 0 |
| V2a | 34 | 5 | 2 | 0 |
| V2b | 31 | 8 | 1 | 1 |
| V3 | 34 | 7 | 0 | 0 |
| V4 | 0 | 4 | 1 | 36 |
| V4b | 0 | 3 | 0 | 38 |
| V5 | 16 | 16 | 7 | 2 |
| V6c | 15 | 18 | 6 | 2 |

## 4. Per-subset `bowlers_end` precision

Strict precision on bowlers_end tag, broken out by corpus subset.  N in each cell = frames the variant tagged bowlers_end within that subset.

| Variant | active_play_recall | batter_closeup_with_background | disambiguation | overall |
|---|---|---|---|---|
| V0 | 18.2% (11) | 16.7% (18) | 0.0% (4) | 15.2% (33) |
| V1 | 18.2% (11) | 16.7% (18) | 0.0% (4) | 15.2% (33) |
| V2a | 18.2% (11) | 16.7% (18) | 0.0% (5) | 14.7% (34) |
| V2b | 20.0% (10) | 16.7% (18) | 0.0% (3) | 16.1% (31) |
| V3 | 18.2% (11) | 16.7% (18) | 0.0% (5) | 14.7% (34) |
| V4 | n/a | n/a | n/a | n/a |
| V4b | n/a | n/a | n/a | n/a |
| V5 | 40.0% (5) | 30.0% (10) | 0.0% (1) | 31.2% (16) |
| V6c | 50.0% (4) | 27.3% (11) | n/a | 33.3% (15) |

## 5. Per-subset `bowlers_end` recall (human-labeled denominator)

Of HUMAN-labeled bowlers_end frames in each subset, fraction the variant tagged bowlers_end.  Recall denominator is small for non-active-play subsets because human-labeled bowlers_end frames concentrate in `active_play_recall`.

| Variant | active_play_recall | batter_closeup_with_background | disambiguation | overall |
|---|---|---|---|---|
| V0 | 100.0% (2) | 100.0% (3) | n/a | 100.0% (5) |
| V1 | 100.0% (2) | 100.0% (3) | n/a | 100.0% (5) |
| V2a | 100.0% (2) | 100.0% (3) | n/a | 100.0% (5) |
| V2b | 100.0% (2) | 100.0% (3) | n/a | 100.0% (5) |
| V3 | 100.0% (2) | 100.0% (3) | n/a | 100.0% (5) |
| V4 | 0.0% (2) | 0.0% (3) | n/a | 0.0% (5) |
| V4b | 0.0% (2) | 0.0% (3) | n/a | 0.0% (5) |
| V5 | 100.0% (2) | 100.0% (3) | n/a | 100.0% (5) |
| V6c | 100.0% (2) | 100.0% (3) | n/a | 100.0% (5) |

## 6. Replicate variance (Scout stability)

Fraction of frames where the variant produced >1 distinct camera_view across its 3 replicates.  High values indicate Scout is uncertain — flagging potential boundary cases the prompt doesn't fully resolve.

| Variant | cam flip rate | phase flip rate |
|---|---|---|
| V1 | 2.4% | 12.2% |
| V2a | 7.3% | 34.1% |
| V2b | 7.3% | 14.6% |
| V3 | 7.3% | 14.6% |
| V4 | 7.3% | 14.6% |
| V4b | 2.4% | 19.5% |
| V5 | 7.3% | 12.2% |
| V6c | 9.8% | 7.3% |

## 7. Recall floor on HUMAN-labeled bowlers_end (strict)

N = 5 human-labeled bowlers_end frames: f169, f955, f754, f945, f946

| Variant | caught | missed | recall |
|---|---|---|---|
| V0 | 5 (f169, f955, f754, f945, f946) | 0 (-) | 100.0% |
| V1 | 5 (f169, f955, f754, f945, f946) | 0 (-) | 100.0% |
| V2a | 5 (f169, f955, f754, f945, f946) | 0 (-) | 100.0% |
| V2b | 5 (f169, f955, f754, f945, f946) | 0 (-) | 100.0% |
| V3 | 5 (f169, f955, f754, f945, f946) | 0 (-) | 100.0% |
| V4 | 0 (-) | 5 (f169→other, f955→other, f754→other, f945→other, f946→other) | 0.0% |
| V4b | 0 (-) | 5 (f169→other, f955→other, f754→other, f945→other, f946→other) | 0.0% |
| V5 | 5 (f169, f955, f754, f945, f946) | 0 (-) | 100.0% |
| V6c | 5 (f169, f955, f754, f945, f946) | 0 (-) | 100.0% |

## 8. `frame_phase` precision when variant tagged bowlers_end

Of frames the variant tagged `bowlers_end` where the human label is also `bowlers_end`, fraction whose `frame_phase` matches the human phase.  Phase comparison is case-insensitive equality on the vote_phase; `None` phase counts as mismatch.

| Variant | phase matches / TP frames |
|---|---|
| V1 | 2/5 = 40.0% |
| V2a | 2/5 = 40.0% |
| V2b | 2/5 = 40.0% |
| V3 | 2/5 = 40.0% |
| V4 | 0/0 = n/a |
| V4b | 0/0 = n/a |
| V5 | 0/5 = 0.0% |
| V6c | 0/5 = 0.0% |

## 9. Decision summary

Precision targets: ≥90% strict bowlers_end precision + coverage-weighted ≥90%.  Recall floor: ≥90% strict recall on human-labeled bowlers_end frames (5 of them).

| Variant | BE strict prec | BE recall (strict, N=5) | Coverage-wtd | Cam flip rate | Meets targets? |
|---|---|---|---|---|---|
| V0 | 15.2% (33) | 100.0% (5/5) | 28.2% | n/a | no |
| V1 | 15.2% (33) | 100.0% (5/5) | 28.2% | 2.4% | no |
| V2a | 14.7% (34) | 100.0% (5/5) | 27.8% | 7.3% | no |
| V2b | 16.1% (31) | 100.0% (5/5) | 26.1% | 7.3% | no |
| V3 | 14.7% (34) | 100.0% (5/5) | 22.6% | 7.3% | no |
| V4 | n/a | 0.0% (0/5) | 96.7% | 7.3% | no |
| V4b | n/a | 0.0% (0/5) | 96.2% | 2.4% | no |
| V5 | 31.2% (16) | 100.0% (5/5) | 36.2% | 7.3% | no |
| V6c | 33.3% (15) | 100.0% (5/5) | 37.1% | 9.8% | no |
