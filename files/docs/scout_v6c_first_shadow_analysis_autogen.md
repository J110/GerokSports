# Part B shadow-run v1 — analysis

Corpus: `docs/scout_corpus_v1.json` (vv1.1, 41 frames)
Shadow inputs: overlay `docs/shadow_run_v6c_20260430_140220.json` on `docs/shadow_run_v1.json` — **`984`** API result rows.

Baseline (V0) = `scout_cam_original` stored in the corpus (what Scout emitted on the live RC9 run).  V1–V3 = majority-vote cam across 3 replicates at temperature=0.

## 1. Precision by camera_view tag

Strict precision: of frames the variant tagged X, fraction where the human label is X.  N = frames emitted by the variant.

| Variant | bowlers_end | closeup | side_on | graphic | other | ad | replay | Coverage-weighted |
|---|---|---|---|---|---|---|---|---|
| V0 | 15.2% (33) | 100.0% (6) | n/a | 100.0% (2) | n/a | n/a | n/a | 28.2% |
| V5 | 31.2% (16) | 62.5% (16) | n/a | 42.9% (7) | 100.0% (2) | n/a | n/a | 36.2% |
| V6c | 33.3% (15) | 55.6% (18) | n/a | 42.9% (7) | 100.0% (1) | n/a | n/a | 37.0% |

Coverage-weighted precision is the sum of per-label precision weighted by Scout's pipeline-wide emission share for that label (from the 5-session A3 audit: bowlers_end 83.8%, closeup 13.5%, graphic 1.7%, other/ad 0.9%).  It estimates how much of Scout's real-world emission volume the variant would get right.

## 2. Recall by human label

Of frames HUMAN-labeled X, fraction the variant tagged X.  N = number of human-labeled frames with that label.

| Variant | closeup (N=12) | other (N=10) | graphic (N=7) | side_on (N=7) | bowlers_end (N=5) |
|---|---|---|---|---|---|
| V0 | 50.0% | 0.0% | 28.6% | 0.0% | 100.0% |
| V5 | 83.3% | 20.0% | 42.9% | 0.0% | 100.0% |
| V6c | 83.3% | 10.0% | 42.9% | 0.0% | 100.0% |

## 3. Emission distribution (cam counts per variant)

Where does each variant place the 41 frames?

| Variant | bowlers_end | closeup | graphic | other |
|---|---|---|---|---|
| V0 | 33 | 6 | 2 | 0 |
| V5 | 16 | 16 | 7 | 2 |
| V6c | 15 | 18 | 7 | 1 |

## 4. Per-subset `bowlers_end` precision

Strict precision on bowlers_end tag, broken out by corpus subset.  N in each cell = frames the variant tagged bowlers_end within that subset.

| Variant | active_play_recall | batter_closeup_with_background | disambiguation | overall |
|---|---|---|---|---|
| V0 | 18.2% (11) | 16.7% (18) | 0.0% (4) | 15.2% (33) |
| V5 | 40.0% (5) | 30.0% (10) | 0.0% (1) | 31.2% (16) |
| V6c | 40.0% (5) | 30.0% (10) | n/a | 33.3% (15) |

## 5. Per-subset `bowlers_end` recall (human-labeled denominator)

Of HUMAN-labeled bowlers_end frames in each subset, fraction the variant tagged bowlers_end.  Recall denominator is small for non-active-play subsets because human-labeled bowlers_end frames concentrate in `active_play_recall`.

| Variant | active_play_recall | batter_closeup_with_background | disambiguation | overall |
|---|---|---|---|---|
| V0 | 100.0% (2) | 100.0% (3) | n/a | 100.0% (5) |
| V5 | 100.0% (2) | 100.0% (3) | n/a | 100.0% (5) |
| V6c | 100.0% (2) | 100.0% (3) | n/a | 100.0% (5) |

## 6. Replicate variance (Scout stability)

Fraction of frames where the variant produced >1 distinct camera_view across its 3 replicates.  High values indicate Scout is uncertain — flagging potential boundary cases the prompt doesn't fully resolve.

| Variant | cam flip rate | phase flip rate |
|---|---|---|
| V5 | 7.3% | 12.2% |
| V6c | 14.6% | 7.3% |

## 7. Recall floor on HUMAN-labeled bowlers_end (strict)

N = 5 human-labeled bowlers_end frames: f169, f955, f754, f945, f946

| Variant | caught | missed | recall |
|---|---|---|---|
| V0 | 5 (f169, f955, f754, f945, f946) | 0 (-) | 100.0% |
| V5 | 5 (f169, f955, f754, f945, f946) | 0 (-) | 100.0% |
| V6c | 5 (f169, f955, f754, f945, f946) | 0 (-) | 100.0% |

## 8. `frame_phase` precision when variant tagged bowlers_end

Of frames the variant tagged `bowlers_end` where the human label is also `bowlers_end`, fraction whose `frame_phase` matches the human phase.  Phase comparison is case-insensitive equality on the vote_phase; `None` phase counts as mismatch.

| Variant | phase matches / TP frames |
|---|---|
| V5 | 0/5 = 0.0% |
| V6c | 0/5 = 0.0% |

## 9. Decision summary

Precision targets: ≥90% strict bowlers_end precision + coverage-weighted ≥90%.  Recall floor: ≥90% strict recall on human-labeled bowlers_end frames (N=5).

| Variant | BE strict prec | BE recall (strict, N=5) | Coverage-wtd | Cam flip rate | Meets targets? |
|---|---|---|---|---|---|
| V0 | 15.2% (33) | 100.0% (5/5) | 28.2% | n/a | no |
| V5 | 31.2% (16) | 100.0% (5/5) | 36.2% | 7.3% | no |
| V6c | 33.3% (15) | 100.0% (5/5) | 37.0% | 14.6% | no |

