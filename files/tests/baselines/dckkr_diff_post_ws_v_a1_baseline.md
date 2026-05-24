# Differential diff report

- Pipeline: `/tmp/dckkr_post_ws_v_a1_pipeline_snapshots.jsonl`
- Ground truth: `files/tests/fixtures/dckkr_ground_truth_ui_snapshots.jsonl`
- Matched balls: 28 | missing-in-pipeline: 94 | phantom-in-pipeline: 3 | total divergences: 93

## 1. Per-surface incident counts

| Surface | Count | First example (over.ball) |
|---|---|---|
| G-pipeline-lag | 94 | 0.1 |
| F-A-commit-lag | 10 | 0.6 |
| F-B-ad-occlusion | 8 | 0.6 |
| Per-batter-ledger-drift | 5 | 4.1 |
| Recent-overs-drop | 4 | 1.1 |
| E2-phantom-runs | 3 | 4.2 |
| Boundary-counter-double-increment | 1 | 0.6 |

## 2. Per-ball divergences

| over.ball | field | pipeline | ground-truth | surface |
|---|---|---|---|---|
| 0.2 | non_striker_name | Rahul | — | _unclassified_ |
| 0.3 | striker_name | Rahul | — | _unclassified_ |
| 0.6 | striker_name | Nissanka | Rahul | _unclassified_ |
| 0.6 | striker_runs | 6 | 1 | _unclassified_ |
| 0.6 | striker_balls | 4 | 2 | _unclassified_ |
| 0.6 | striker_fours | 1 | 0 | Boundary-counter-double-increment |
| 0.6 | non_striker_name | Rahul | Nissanka | _unclassified_ |
| 0.6 | non_striker_runs | 1 | 6 | _unclassified_ |
| 0.6 | non_striker_balls | 2 | 4 | _unclassified_ |
| 0.6 | non_striker_fours | 0 | 1 | _unclassified_ |
| 0.6 | bowler_name | — | Roy | F-B-ad-occlusion |
| 0.6 | bowler_overs | — | 1.0 | F-A-commit-lag |
| 0.6 | bowler_runs | 0 | 7 | _unclassified_ |
| 1.1 | recent_over_n_minus_1 | [] | [".", "4", "1", ".", "1", "1"] | Recent-overs-drop |
| 1.6 | striker_name | Rahul | Nissanka | _unclassified_ |
| 1.6 | striker_runs | 3 | 14 | _unclassified_ |
| 1.6 | striker_balls | 4 | 8 | _unclassified_ |
| 1.6 | striker_fours | 0 | 1 | _unclassified_ |
| 1.6 | striker_sixes | 0 | 1 | _unclassified_ |
| 1.6 | non_striker_name | Nissanka | Rahul | _unclassified_ |
| 1.6 | non_striker_runs | 14 | 3 | _unclassified_ |
| 1.6 | non_striker_balls | 8 | 4 | _unclassified_ |
| 1.6 | non_striker_fours | 1 | 0 | _unclassified_ |
| 1.6 | non_striker_sixes | 1 | 0 | _unclassified_ |
| 1.6 | bowler_name | — | Arora | F-B-ad-occlusion |
| 1.6 | bowler_overs | — | 1.0 | F-A-commit-lag |
| 1.6 | bowler_runs | 0 | 10 | _unclassified_ |
| 2.1 | recent_over_n_minus_1 | [] | [".", "1", "1", "6", "1", "1"] | Recent-overs-drop |
| 2.6 | striker_name | Rahul | Nissanka | _unclassified_ |
| 2.6 | striker_runs | 8 | 20 | _unclassified_ |
| 2.6 | striker_balls | 7 | 11 | _unclassified_ |
| 2.6 | striker_sixes | 0 | 2 | _unclassified_ |
| 2.6 | non_striker_name | Nissanka | Rahul | _unclassified_ |
| 2.6 | non_striker_runs | 20 | 8 | _unclassified_ |
| 2.6 | non_striker_balls | 11 | 7 | _unclassified_ |
| 2.6 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 2.6 | bowler_name | — | Roy | F-B-ad-occlusion |
| 2.6 | bowler_overs | — | 2.0 | F-A-commit-lag |
| 2.6 | bowler_runs | 0 | 18 | _unclassified_ |
| 3.1 | bowler_name | — | Narine | F-B-ad-occlusion |
| 3.1 | bowler_overs | — | 0.1 | F-A-commit-lag |
| 3.1 | bowler_runs | 0 | 1 | _unclassified_ |
| 3.1 | recent_over_n_minus_1 | [] | [".", "4", "1", ".", ".", "6"] | Recent-overs-drop |
| 3.6 | striker_name | Rahul | Nissanka | _unclassified_ |
| 3.6 | striker_runs | 14 | 25 | _unclassified_ |
| 3.6 | striker_balls | 10 | 14 | _unclassified_ |
| 3.6 | striker_sixes | 0 | 2 | _unclassified_ |
| 3.6 | non_striker_name | Nissanka | Rahul | _unclassified_ |
| 3.6 | non_striker_runs | 25 | 14 | _unclassified_ |
| 3.6 | non_striker_balls | 14 | 10 | _unclassified_ |
| 3.6 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 3.6 | bowler_name | — | Narine | F-B-ad-occlusion |
| 3.6 | bowler_overs | — | 1.0 | F-A-commit-lag |
| 3.6 | bowler_runs | 0 | 11 | _unclassified_ |
| 4.1 | score | 63 | 43 | _unclassified_ |
| 4.1 | bowler_name | — | Tyagi | F-B-ad-occlusion |
| 4.1 | bowler_overs | — | 0.1 | F-A-commit-lag |
| 4.1 | bowler_runs | 0 | 4 | _unclassified_ |
| 4.1 | recent_over_n_minus_1 | [] | ["1", "4", ".", "1", "4", "1"] | Recent-overs-drop |
| 4.2 | score | 63 | 44 | E2-phantom-runs |
| 4.2 | bowler_name | — | Tyagi | F-B-ad-occlusion |
| 4.2 | bowler_overs | — | 0.2 | F-A-commit-lag |
| 4.2 | bowler_runs | 0 | 5 | _unclassified_ |
| 4.3 | score | 63 | 44 | E2-phantom-runs |
| 4.3 | striker_name | Rahul | Nissanka | _unclassified_ |
| 4.3 | striker_runs | 19 | 25 | _unclassified_ |
| 4.3 | striker_balls | 12 | 15 | _unclassified_ |
| 4.3 | striker_fours | 3 | 2 | _unclassified_ |
| 4.3 | striker_sixes | 0 | 2 | _unclassified_ |
| 4.3 | non_striker_name | Nissanka | Rahul | _unclassified_ |
| 4.3 | non_striker_runs | 25 | 19 | _unclassified_ |
| 4.3 | non_striker_balls | 15 | 12 | _unclassified_ |
| 4.3 | non_striker_fours | 2 | 3 | _unclassified_ |
| 4.3 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 4.3 | bowler_name | — | Tyagi | F-B-ad-occlusion |
| 4.3 | bowler_overs | — | 0.3 | F-A-commit-lag |
| 4.3 | bowler_runs | 0 | 5 | _unclassified_ |
| 4.4 | score | 64 | 45 | E2-phantom-runs |
| 4.4 | striker_name | Nissanka | Rahul | _unclassified_ |
| 4.4 | striker_runs | 26 | 19 | _unclassified_ |
| 4.4 | striker_balls | 16 | 12 | _unclassified_ |
| 4.4 | striker_fours | 2 | 3 | _unclassified_ |
| 4.4 | striker_sixes | 2 | 0 | _unclassified_ |
| 4.4 | non_striker_name | Rahul | Nissanka | _unclassified_ |
| 4.4 | non_striker_runs | 19 | 26 | _unclassified_ |
| 4.4 | non_striker_balls | 12 | 16 | _unclassified_ |
| 4.4 | non_striker_fours | 3 | 2 | _unclassified_ |
| 4.4 | non_striker_sixes | 0 | 2 | _unclassified_ |
| 4.4 | bowler_overs | 0.2 | 0.4 | F-A-commit-lag |
| 4.4 | bowler_runs | 1 | 6 | _unclassified_ |
| 4.5 | score | 64 | 49 | _unclassified_ |
| 4.5 | bowler_overs | 0.3 | 0.5 | F-A-commit-lag |
| 4.5 | bowler_runs | 5 | 10 | _unclassified_ |

## 3. Conservation invariants

1. 4.1: pipeline score(63) exceeds GT(43) by 20
2. 4.2: pipeline score(63) exceeds GT(44) by 19
3. 4.3: pipeline score(63) exceeds GT(44) by 19
4. 4.4: pipeline score(64) exceeds GT(45) by 19
5. 4.5: pipeline score(64) exceeds GT(49) by 15

## 4. Unclassified divergences

| over.ball | field | pipeline | ground-truth |
|---|---|---|---|
| 0.2 | non_striker_name | Rahul | — |
| 0.3 | striker_name | Rahul | — |
| 0.6 | striker_name | Nissanka | Rahul |
| 0.6 | striker_runs | 6 | 1 |
| 0.6 | striker_balls | 4 | 2 |
| 0.6 | non_striker_name | Rahul | Nissanka |
| 0.6 | non_striker_runs | 1 | 6 |
| 0.6 | non_striker_balls | 2 | 4 |
| 0.6 | non_striker_fours | 0 | 1 |
| 0.6 | bowler_runs | 0 | 7 |
| 1.6 | striker_name | Rahul | Nissanka |
| 1.6 | striker_runs | 3 | 14 |
| 1.6 | striker_balls | 4 | 8 |
| 1.6 | striker_fours | 0 | 1 |
| 1.6 | striker_sixes | 0 | 1 |
| 1.6 | non_striker_name | Nissanka | Rahul |
| 1.6 | non_striker_runs | 14 | 3 |
| 1.6 | non_striker_balls | 8 | 4 |
| 1.6 | non_striker_fours | 1 | 0 |
| 1.6 | non_striker_sixes | 1 | 0 |
| 1.6 | bowler_runs | 0 | 10 |
| 2.6 | striker_name | Rahul | Nissanka |
| 2.6 | striker_runs | 8 | 20 |
| 2.6 | striker_balls | 7 | 11 |
| 2.6 | striker_sixes | 0 | 2 |
| 2.6 | non_striker_name | Nissanka | Rahul |
| 2.6 | non_striker_runs | 20 | 8 |
| 2.6 | non_striker_balls | 11 | 7 |
| 2.6 | non_striker_sixes | 2 | 0 |
| 2.6 | bowler_runs | 0 | 18 |
| 3.1 | bowler_runs | 0 | 1 |
| 3.6 | striker_name | Rahul | Nissanka |
| 3.6 | striker_runs | 14 | 25 |
| 3.6 | striker_balls | 10 | 14 |
| 3.6 | striker_sixes | 0 | 2 |
| 3.6 | non_striker_name | Nissanka | Rahul |
| 3.6 | non_striker_runs | 25 | 14 |
| 3.6 | non_striker_balls | 14 | 10 |
| 3.6 | non_striker_sixes | 2 | 0 |
| 3.6 | bowler_runs | 0 | 11 |
| 4.1 | score | 63 | 43 |
| 4.1 | bowler_runs | 0 | 4 |
| 4.2 | bowler_runs | 0 | 5 |
| 4.3 | striker_name | Rahul | Nissanka |
| 4.3 | striker_runs | 19 | 25 |
| 4.3 | striker_balls | 12 | 15 |
| 4.3 | striker_fours | 3 | 2 |
| 4.3 | striker_sixes | 0 | 2 |
| 4.3 | non_striker_name | Nissanka | Rahul |
| 4.3 | non_striker_runs | 25 | 19 |
| 4.3 | non_striker_balls | 15 | 12 |
| 4.3 | non_striker_fours | 2 | 3 |
| 4.3 | non_striker_sixes | 2 | 0 |
| 4.3 | bowler_runs | 0 | 5 |
| 4.4 | striker_name | Nissanka | Rahul |
| 4.4 | striker_runs | 26 | 19 |
| 4.4 | striker_balls | 16 | 12 |
| 4.4 | striker_fours | 2 | 3 |
| 4.4 | striker_sixes | 2 | 0 |
| 4.4 | non_striker_name | Rahul | Nissanka |
| 4.4 | non_striker_runs | 19 | 26 |
| 4.4 | non_striker_balls | 12 | 16 |
| 4.4 | non_striker_fours | 3 | 2 |
| 4.4 | non_striker_sixes | 0 | 2 |
| 4.4 | bowler_runs | 1 | 6 |
| 4.5 | score | 64 | 49 |
| 4.5 | bowler_runs | 5 | 10 |

## 5. Missing / phantom balls

- Missing-in-pipeline (94): 0.1, 4.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 10.1, 10.2, 10.2#1, 10.2#2, 10.3, 10.4, 10.5, 10.6, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 19.1, 19.2, 19.3, 19.4, 19.5, 19.6
- Phantom-in-pipeline (3): 3.6#1, 3.6#2, 4.3#1
