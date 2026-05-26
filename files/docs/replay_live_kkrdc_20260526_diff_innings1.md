# Differential diff report

- Pipeline: `files/logs/deliveries/replay_live_kkrdc_20260526_115105/ui_snapshots.jsonl`
- Ground truth: `files/tests/fixtures/kkr_dc_20260524_innings1_gt_snapshots.jsonl`
- Matched balls: 72 | missing-in-pipeline: 57 | phantom-in-pipeline: 13 | total divergences: 1019

## 1. Per-surface incident counts

| Surface | Count | First example (over.ball) |
|---|---|---|
| Extras-counter-drop | 150 | 1.5 |
| F-A-commit-lag | 65 | 0.2 |
| G-pipeline-lag | 57 | 0.1 |
| E3-wicket-frame-misalign | 55 | 1.1 |
| D-post-FoW-striker | 43 | 4.3 |
| F-B-ad-occlusion | 33 | 0.2 |
| Boundary-counter-double-increment | 28 | 2.2 |
| Bowler-W-credit-failure | 13 | 4.3 |
| Recent-overs-drop | 10 | 1.1 |
| C21b-symbol-revert | 10 | 4.3 |
| Multi-ball-compression | 6 | 0.5 |
| E2-phantom-runs | 2 | 9.6 |
| Silent-wicket-absorption | 1 | 9.3 |

## 2. Per-ball divergences

| over.ball | field | pipeline | ground-truth | surface |
|---|---|---|---|---|
| 0.2 | striker_balls | 0 | 2 | _unclassified_ |
| 0.2 | non_striker_name | Rahul | — | _unclassified_ |
| 0.2 | bowler_name | — | Roy | F-B-ad-occlusion |
| 0.2 | bowler_overs | — | 0.2 | F-A-commit-lag |
| 0.3 | striker_balls | 1 | 3 | _unclassified_ |
| 0.3 | non_striker_name | Rahul | — | _unclassified_ |
| 0.3 | bowler_overs | 0.1 | 0.3 | F-A-commit-lag |
| 0.5 | striker_name | Rahul | — | _unclassified_ |
| 0.5 | non_striker_balls | 3 | 5 | _unclassified_ |
| 0.5 | non_striker_fours | 1 | 2 | _unclassified_ |
| 0.5 | bowler_overs | 0.3 | 0.5 | F-A-commit-lag |
| 0.5 | this_over_tokens | [".", ".", "4"] | [".", ".", "4", "4", "1"] | Multi-ball-compression |
| 0.6 | non_striker_balls | 3 | 5 | _unclassified_ |
| 0.6 | non_striker_fours | 1 | 2 | _unclassified_ |
| 0.6 | bowler_overs | 0.4 | 1.0 | F-A-commit-lag |
| 0.6 | this_over_tokens | [".", ".", "4", "1"] | [".", ".", "4", "4", "1", "1"] | Multi-ball-compression |
| 1.1 | score | 5 | 10 | _unclassified_ |
| 1.1 | striker_name | — | Rahul | _unclassified_ |
| 1.1 | striker_runs | 0 | 1 | _unclassified_ |
| 1.1 | striker_balls | 0 | 2 | _unclassified_ |
| 1.1 | non_striker_name | — | Porel | _unclassified_ |
| 1.1 | non_striker_runs | 0 | 9 | _unclassified_ |
| 1.1 | non_striker_balls | 0 | 5 | _unclassified_ |
| 1.1 | non_striker_fours | 0 | 2 | _unclassified_ |
| 1.1 | bowler_name | Chakaravarthy | Dubey | F-B-ad-occlusion |
| 1.1 | bowler_overs | 4.5 | 0.1 | F-A-commit-lag |
| 1.1 | bowler_runs | 36 | 0 | _unclassified_ |
| 1.1 | bowler_wickets | 1 | 0 | _unclassified_ |
| 1.1 | this_over_tokens | [".", ".", "1", "1", "1", "1", "1"] | ["."] | _unclassified_ |
| 1.1 | recent_over_n_minus_1 | [] | [".", ".", "4", "4", "1", "1"] | Recent-overs-drop |
| 1.1 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [] | E3-wicket-frame-misalign |
| 1.2 | striker_balls | 3 | 5 | _unclassified_ |
| 1.2 | striker_fours | 1 | 2 | _unclassified_ |
| 1.2 | bowler_name | Roy | Dubey | F-B-ad-occlusion |
| 1.2 | bowler_overs | 1.0 | 0.2 | F-A-commit-lag |
| 1.2 | bowler_runs | 11 | 1 | _unclassified_ |
| 1.2 | this_over_tokens | [".", ".", "4", "1"] | [".", "1"] | _unclassified_ |
| 1.3 | striker_balls | 4 | 6 | _unclassified_ |
| 1.3 | striker_fours | 1 | 2 | _unclassified_ |
| 1.3 | bowler_name | Roy | Dubey | F-B-ad-occlusion |
| 1.3 | bowler_overs | 1.1 | 0.3 | F-A-commit-lag |
| 1.3 | bowler_runs | 11 | 1 | _unclassified_ |
| 1.3 | this_over_tokens | ["?", "?", "."] | [".", "1", "."] | _unclassified_ |
| 1.4 | striker_balls | 5 | 7 | _unclassified_ |
| 1.4 | striker_fours | 1 | 2 | _unclassified_ |
| 1.4 | bowler_name | Roy | Dubey | F-B-ad-occlusion |
| 1.4 | bowler_overs | 1.2 | 0.4 | F-A-commit-lag |
| 1.4 | bowler_runs | 11 | 1 | _unclassified_ |
| 1.4 | this_over_tokens | ["?", "?", ".", "."] | [".", "1", ".", "."] | _unclassified_ |
| 1.5 | balls_total | 11 | 10 | _unclassified_ |
| 1.5 | striker_name | Rahul | Porel | _unclassified_ |
| 1.5 | striker_runs | 2 | 9 | _unclassified_ |
| 1.5 | striker_balls | 3 | 7 | _unclassified_ |
| 1.5 | striker_fours | 0 | 2 | _unclassified_ |
| 1.5 | non_striker_name | Porel | Rahul | _unclassified_ |
| 1.5 | non_striker_runs | 10 | 2 | _unclassified_ |
| 1.5 | non_striker_balls | 6 | 3 | _unclassified_ |
| 1.5 | non_striker_fours | 1 | 0 | _unclassified_ |
| 1.5 | bowler_name | Roy | Dubey | F-B-ad-occlusion |
| 1.5 | bowler_overs | 1.3 | 0.4 | F-A-commit-lag |
| 1.5 | bowler_runs | 12 | 2 | _unclassified_ |
| 1.5 | extras_total | 0 | 1 | Extras-counter-drop |
| 1.5 | extras_wd | 0 | 1 | Extras-counter-drop |
| 1.5 | this_over_tokens | ["?", "?", ".", ".", "1"] | [".", "1", ".", ".", "Wd"] | _unclassified_ |
| 2.1 | striker_name | Rahul | Porel | _unclassified_ |
| 2.1 | striker_runs | 2 | 9 | _unclassified_ |
| 2.1 | striker_balls | 4 | 9 | _unclassified_ |
| 2.1 | striker_fours | 0 | 2 | _unclassified_ |
| 2.1 | non_striker_name | Porel | Rahul | _unclassified_ |
| 2.1 | non_striker_runs | 11 | 3 | _unclassified_ |
| 2.1 | non_striker_balls | 7 | 4 | _unclassified_ |
| 2.1 | non_striker_fours | 1 | 0 | _unclassified_ |
| 2.1 | bowler_name | — | Green | F-B-ad-occlusion |
| 2.1 | bowler_overs | — | 0.1 | F-A-commit-lag |
| 2.1 | bowler_runs | 0 | 1 | _unclassified_ |
| 2.1 | extras_total | 0 | 1 | Extras-counter-drop |
| 2.1 | extras_wd | 0 | 1 | Extras-counter-drop |
| 2.1 | recent_over_n_minus_1 | [] | [".", "1", ".", ".", "Wd", ".", "."] | Recent-overs-drop |
| 2.2 | striker_name | Porel | Rahul | _unclassified_ |
| 2.2 | striker_runs | 11 | 3 | _unclassified_ |
| 2.2 | striker_balls | 7 | 4 | _unclassified_ |
| 2.2 | striker_fours | 1 | 0 | Boundary-counter-double-increment |
| 2.2 | non_striker_name | Rahul | Porel | _unclassified_ |
| 2.2 | non_striker_runs | 3 | 10 | _unclassified_ |
| 2.2 | non_striker_balls | 5 | 10 | _unclassified_ |
| 2.2 | non_striker_fours | 0 | 2 | _unclassified_ |
| 2.2 | bowler_name | — | Green | F-B-ad-occlusion |
| 2.2 | bowler_overs | — | 0.2 | F-A-commit-lag |
| 2.2 | bowler_runs | 0 | 2 | _unclassified_ |
| 2.2 | extras_total | 0 | 1 | Extras-counter-drop |
| 2.2 | extras_wd | 0 | 1 | Extras-counter-drop |
| 2.3 | striker_name | Porel | Rahul | _unclassified_ |
| 2.3 | striker_runs | 11 | 3 | _unclassified_ |
| 2.3 | striker_balls | 8 | 5 | _unclassified_ |
| 2.3 | striker_fours | 1 | 0 | Boundary-counter-double-increment |
| 2.3 | non_striker_name | Rahul | Porel | _unclassified_ |
| 2.3 | non_striker_runs | 3 | 10 | _unclassified_ |
| 2.3 | non_striker_balls | 5 | 10 | _unclassified_ |
| 2.3 | non_striker_fours | 0 | 2 | _unclassified_ |
| 2.3 | bowler_name | — | Green | F-B-ad-occlusion |
| 2.3 | bowler_overs | — | 0.3 | F-A-commit-lag |
| 2.3 | bowler_runs | 0 | 2 | _unclassified_ |
| 2.3 | extras_total | 0 | 1 | Extras-counter-drop |
| 2.3 | extras_wd | 0 | 1 | Extras-counter-drop |
| 2.4 | striker_name | Porel | Rahul | _unclassified_ |
| 2.4 | striker_runs | 11 | 9 | _unclassified_ |
| 2.4 | striker_balls | 8 | 6 | _unclassified_ |
| 2.4 | striker_fours | 1 | 0 | Boundary-counter-double-increment |
| 2.4 | striker_sixes | 0 | 1 | _unclassified_ |
| 2.4 | non_striker_name | Rahul | Porel | _unclassified_ |
| 2.4 | non_striker_runs | 9 | 10 | _unclassified_ |
| 2.4 | non_striker_balls | 6 | 10 | _unclassified_ |
| 2.4 | non_striker_fours | 0 | 2 | _unclassified_ |
| 2.4 | non_striker_sixes | 1 | 0 | _unclassified_ |
| 2.4 | bowler_overs | 0.3 | 0.4 | F-A-commit-lag |
| 2.4 | bowler_runs | 7 | 8 | _unclassified_ |
| 2.4 | extras_total | 0 | 1 | Extras-counter-drop |
| 2.4 | extras_wd | 0 | 1 | Extras-counter-drop |
| 2.5 | score | 22 | 24 | _unclassified_ |
| 2.5 | striker_name | — | Rahul | _unclassified_ |
| 2.5 | striker_runs | 0 | 13 | _unclassified_ |
| 2.5 | striker_balls | 0 | 7 | _unclassified_ |
| 2.5 | striker_fours | 0 | 1 | _unclassified_ |
| 2.5 | striker_sixes | 0 | 1 | _unclassified_ |
| 2.5 | non_striker_name | — | Porel | _unclassified_ |
| 2.5 | non_striker_runs | 0 | 10 | _unclassified_ |
| 2.5 | non_striker_balls | 0 | 10 | _unclassified_ |
| 2.5 | non_striker_fours | 0 | 2 | _unclassified_ |
| 2.5 | bowler_name | Chakaravarthy | Green | F-B-ad-occlusion |
| 2.5 | bowler_overs | 4.5 | 0.5 | F-A-commit-lag |
| 2.5 | bowler_runs | 36 | 12 | _unclassified_ |
| 2.5 | bowler_wickets | 1 | 0 | _unclassified_ |
| 2.5 | extras_total | 0 | 1 | Extras-counter-drop |
| 2.5 | extras_wd | 0 | 1 | Extras-counter-drop |
| 2.5 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | ["1", "1", ".", "6", "4"] | _unclassified_ |
| 2.5 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [] | E3-wicket-frame-misalign |
| 2.6 | striker_runs | 17 | 10 | _unclassified_ |
| 2.6 | striker_fours | 1 | 2 | _unclassified_ |
| 2.6 | striker_sixes | 1 | 0 | Boundary-counter-double-increment |
| 2.6 | non_striker_runs | 9 | 15 | _unclassified_ |
| 2.6 | non_striker_balls | 6 | 8 | _unclassified_ |
| 2.6 | non_striker_fours | 0 | 1 | _unclassified_ |
| 2.6 | bowler_name | Tyagi | Green | F-B-ad-occlusion |
| 2.6 | bowler_overs | 0.2 | 1.0 | F-A-commit-lag |
| 2.6 | bowler_runs | 6 | 14 | _unclassified_ |
| 2.6 | extras_total | 0 | 1 | Extras-counter-drop |
| 2.6 | extras_wd | 0 | 1 | Extras-counter-drop |
| 2.6 | this_over_tokens | ["1", "1", ".", "6"] | ["1", "1", ".", "6", "4", "2"] | Multi-ball-compression |
| 3.1 | striker_runs | 21 | 14 | _unclassified_ |
| 3.1 | striker_fours | 2 | 3 | _unclassified_ |
| 3.1 | striker_sixes | 1 | 0 | Boundary-counter-double-increment |
| 3.1 | non_striker_runs | 9 | 15 | _unclassified_ |
| 3.1 | non_striker_balls | 6 | 8 | _unclassified_ |
| 3.1 | non_striker_fours | 0 | 1 | _unclassified_ |
| 3.1 | bowler_overs | 0.3 | 0.1 | F-A-commit-lag |
| 3.1 | bowler_runs | 10 | 4 | _unclassified_ |
| 3.1 | extras_total | 0 | 1 | Extras-counter-drop |
| 3.1 | extras_wd | 0 | 1 | Extras-counter-drop |
| 3.1 | this_over_tokens | ["1", "1", ".", "6", "4"] | ["4"] | _unclassified_ |
| 3.1 | recent_over_n_minus_1 | [] | ["1", "1", ".", "6", "4", "2"] | Recent-overs-drop |
| 3.3 | score | 30 | 34 | _unclassified_ |
| 3.3 | striker_name | — | Porel | _unclassified_ |
| 3.3 | striker_runs | 0 | 18 | _unclassified_ |
| 3.3 | striker_balls | 0 | 13 | _unclassified_ |
| 3.3 | striker_fours | 0 | 4 | _unclassified_ |
| 3.3 | non_striker_name | — | Rahul | _unclassified_ |
| 3.3 | non_striker_runs | 0 | 15 | _unclassified_ |
| 3.3 | non_striker_balls | 0 | 8 | _unclassified_ |
| 3.3 | non_striker_fours | 0 | 1 | _unclassified_ |
| 3.3 | non_striker_sixes | 0 | 1 | _unclassified_ |
| 3.3 | bowler_name | Chakaravarthy | Tyagi | F-B-ad-occlusion |
| 3.3 | bowler_overs | 4.5 | 0.3 | F-A-commit-lag |
| 3.3 | bowler_runs | 36 | 8 | _unclassified_ |
| 3.3 | bowler_wickets | 1 | 0 | _unclassified_ |
| 3.3 | extras_total | 0 | 1 | Extras-counter-drop |
| 3.3 | extras_wd | 0 | 1 | Extras-counter-drop |
| 3.3 | this_over_tokens | ["?", "?", "."] | ["4", "4", "."] | _unclassified_ |
| 3.3 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [] | E3-wicket-frame-misalign |
| 3.4 | striker_runs | 9 | 15 | _unclassified_ |
| 3.4 | striker_balls | 6 | 8 | _unclassified_ |
| 3.4 | striker_fours | 0 | 1 | _unclassified_ |
| 3.4 | non_striker_runs | 28 | 21 | _unclassified_ |
| 3.4 | non_striker_fours | 2 | 4 | _unclassified_ |
| 3.4 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 3.4 | bowler_overs | 1.0 | 0.4 | F-A-commit-lag |
| 3.4 | bowler_runs | 17 | 11 | _unclassified_ |
| 3.4 | extras_total | 0 | 1 | Extras-counter-drop |
| 3.4 | extras_wd | 0 | 1 | Extras-counter-drop |
| 3.4 | this_over_tokens | ["1", "1", ".", "6", "4", "1"] | ["4", "4", ".", "3"] | _unclassified_ |
| 4.1 | striker_name | Rahul | Porel | _unclassified_ |
| 4.1 | striker_runs | 10 | 22 | _unclassified_ |
| 4.1 | striker_balls | 7 | 16 | _unclassified_ |
| 4.1 | striker_fours | 0 | 4 | _unclassified_ |
| 4.1 | striker_sixes | 1 | 0 | Boundary-counter-double-increment |
| 4.1 | non_striker_name | Porel | Rahul | _unclassified_ |
| 4.1 | non_striker_runs | 29 | 16 | _unclassified_ |
| 4.1 | non_striker_balls | 16 | 9 | _unclassified_ |
| 4.1 | non_striker_fours | 2 | 1 | _unclassified_ |
| 4.1 | non_striker_sixes | 2 | 1 | _unclassified_ |
| 4.1 | bowler_name | Tyagi | Dubey | F-B-ad-occlusion |
| 4.1 | bowler_overs | 1.3 | 1.1 | F-A-commit-lag |
| 4.1 | bowler_runs | 19 | 2 | _unclassified_ |
| 4.1 | extras_total | 0 | 1 | Extras-counter-drop |
| 4.1 | extras_wd | 0 | 1 | Extras-counter-drop |
| 4.1 | recent_over_n_minus_1 | [] | ["4", "4", ".", "3", "1", "1"] | Recent-overs-drop |
| 4.2 | balls_total | 26 | 25 | _unclassified_ |
| 4.2 | striker_runs | 30 | 22 | _unclassified_ |
| 4.2 | striker_balls | 17 | 16 | _unclassified_ |
| 4.2 | striker_fours | 2 | 4 | _unclassified_ |
| 4.2 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 4.2 | non_striker_runs | 10 | 16 | _unclassified_ |
| 4.2 | non_striker_balls | 7 | 9 | _unclassified_ |
| 4.2 | non_striker_fours | 0 | 1 | _unclassified_ |
| 4.2 | bowler_name | Tyagi | Dubey | F-B-ad-occlusion |
| 4.2 | bowler_overs | 1.4 | 1.1 | F-A-commit-lag |
| 4.2 | bowler_runs | 20 | 3 | _unclassified_ |
| 4.2 | extras_total | 0 | 2 | Extras-counter-drop |
| 4.2 | extras_wd | 0 | 2 | Extras-counter-drop |
| 4.2 | this_over_tokens | [".", "1"] | [".", "Wd"] | _unclassified_ |
| 4.3 | striker_name | Porel | — | D-post-FoW-striker |
| 4.3 | striker_runs | 30 | 0 | _unclassified_ |
| 4.3 | striker_balls | 17 | 0 | _unclassified_ |
| 4.3 | striker_fours | 2 | 0 | Boundary-counter-double-increment |
| 4.3 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 4.3 | non_striker_runs | 10 | 16 | _unclassified_ |
| 4.3 | non_striker_balls | 7 | 9 | _unclassified_ |
| 4.3 | non_striker_fours | 0 | 1 | _unclassified_ |
| 4.3 | bowler_name | Tyagi | Dubey | F-B-ad-occlusion |
| 4.3 | bowler_overs | 1.5 | 1.3 | F-A-commit-lag |
| 4.3 | bowler_runs | 20 | 3 | _unclassified_ |
| 4.3 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 4.3 | extras_total | 0 | 2 | Extras-counter-drop |
| 4.3 | extras_wd | 0 | 2 | Extras-counter-drop |
| 4.3 | this_over_tokens | [".", "1", "."] | [".", "Wd", ".", "W"] | C21b-symbol-revert |
| 4.3 | fow_entries | [[54, 1, "Porel", "4.3"]] | [[40, 1, "Porel", "4.3"]] | E3-wicket-frame-misalign |
| 4.4 | striker_runs | 10 | 16 | _unclassified_ |
| 4.4 | striker_balls | 7 | 9 | _unclassified_ |
| 4.4 | striker_fours | 0 | 1 | _unclassified_ |
| 4.4 | non_striker_name | Porel | Parakh | _unclassified_ |
| 4.4 | non_striker_runs | 30 | 1 | _unclassified_ |
| 4.4 | non_striker_balls | 17 | 1 | _unclassified_ |
| 4.4 | non_striker_fours | 2 | 0 | _unclassified_ |
| 4.4 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 4.4 | bowler_name | Tyagi | Dubey | F-B-ad-occlusion |
| 4.4 | bowler_overs | 2.0 | 1.4 | F-A-commit-lag |
| 4.4 | bowler_runs | 21 | 4 | _unclassified_ |
| 4.4 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 4.4 | extras_total | 0 | 2 | Extras-counter-drop |
| 4.4 | extras_wd | 0 | 2 | Extras-counter-drop |
| 4.4 | this_over_tokens | [".", "1", ".", "1"] | [".", "Wd", ".", "W", "1"] | C21b-symbol-revert |
| 4.4 | fow_entries | [[54, 1, "Porel", "4.3"]] | [[40, 1, "Porel", "4.3"]] | E3-wicket-frame-misalign |
| 4.5 | striker_runs | 10 | 16 | _unclassified_ |
| 4.5 | striker_balls | 8 | 10 | _unclassified_ |
| 4.5 | striker_fours | 0 | 1 | _unclassified_ |
| 4.5 | non_striker_name | Porel | Parakh | _unclassified_ |
| 4.5 | non_striker_runs | 30 | 1 | _unclassified_ |
| 4.5 | non_striker_balls | 17 | 1 | _unclassified_ |
| 4.5 | non_striker_fours | 2 | 0 | _unclassified_ |
| 4.5 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 4.5 | bowler_name | Tyagi | Dubey | F-B-ad-occlusion |
| 4.5 | bowler_overs | 2.1 | 1.5 | F-A-commit-lag |
| 4.5 | bowler_runs | 21 | 4 | _unclassified_ |
| 4.5 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 4.5 | extras_total | 0 | 2 | Extras-counter-drop |
| 4.5 | extras_wd | 0 | 2 | Extras-counter-drop |
| 4.5 | this_over_tokens | [".", "1", ".", "1", "."] | [".", "Wd", ".", "W", "1", "."] | C21b-symbol-revert |
| 4.5 | fow_entries | [[54, 1, "Porel", "4.3"]] | [[40, 1, "Porel", "4.3"]] | E3-wicket-frame-misalign |
| 5.3 | striker_name | Rahul | Parakh | D-post-FoW-striker |
| 5.3 | striker_runs | 17 | 7 | _unclassified_ |
| 5.3 | striker_balls | 10 | 3 | _unclassified_ |
| 5.3 | striker_sixes | 2 | 1 | Boundary-counter-double-increment |
| 5.3 | non_striker_name | Porel | Rahul | _unclassified_ |
| 5.3 | non_striker_runs | 30 | 18 | _unclassified_ |
| 5.3 | non_striker_balls | 17 | 12 | _unclassified_ |
| 5.3 | non_striker_fours | 2 | 1 | _unclassified_ |
| 5.3 | non_striker_sixes | 2 | 1 | _unclassified_ |
| 5.3 | extras_total | 0 | 2 | Extras-counter-drop |
| 5.3 | extras_wd | 0 | 2 | Extras-counter-drop |
| 5.3 | this_over_tokens | ["?", "?", "6"] | ["1", ".", "6"] | _unclassified_ |
| 5.3 | fow_entries | [[54, 1, "Porel", "4.3"]] | [[40, 1, "Porel", "4.3"]] | E3-wicket-frame-misalign |
| 5.4 | striker_name | Rahul | Parakh | D-post-FoW-striker |
| 5.4 | striker_runs | 17 | 7 | _unclassified_ |
| 5.4 | striker_balls | 11 | 4 | _unclassified_ |
| 5.4 | striker_sixes | 2 | 1 | Boundary-counter-double-increment |
| 5.4 | non_striker_name | Porel | Rahul | _unclassified_ |
| 5.4 | non_striker_runs | 30 | 18 | _unclassified_ |
| 5.4 | non_striker_balls | 17 | 12 | _unclassified_ |
| 5.4 | non_striker_fours | 2 | 1 | _unclassified_ |
| 5.4 | non_striker_sixes | 2 | 1 | _unclassified_ |
| 5.4 | extras_total | 0 | 2 | Extras-counter-drop |
| 5.4 | extras_wd | 0 | 2 | Extras-counter-drop |
| 5.4 | this_over_tokens | ["?", "?", "6", "."] | ["1", ".", "6", "."] | _unclassified_ |
| 5.4 | fow_entries | [[54, 1, "Porel", "4.3"]] | [[40, 1, "Porel", "4.3"]] | E3-wicket-frame-misalign |
| 5.5 | striker_name | Rahul | Parakh | D-post-FoW-striker |
| 5.5 | striker_runs | 17 | 7 | _unclassified_ |
| 5.5 | striker_balls | 12 | 5 | _unclassified_ |
| 5.5 | striker_sixes | 2 | 1 | Boundary-counter-double-increment |
| 5.5 | non_striker_name | Porel | Rahul | _unclassified_ |
| 5.5 | non_striker_runs | 30 | 18 | _unclassified_ |
| 5.5 | non_striker_balls | 17 | 12 | _unclassified_ |
| 5.5 | non_striker_fours | 2 | 1 | _unclassified_ |
| 5.5 | non_striker_sixes | 2 | 1 | _unclassified_ |
| 5.5 | extras_total | 0 | 2 | Extras-counter-drop |
| 5.5 | extras_wd | 0 | 2 | Extras-counter-drop |
| 5.5 | this_over_tokens | ["?", "?", "6", ".", "."] | ["1", ".", "6", ".", "."] | _unclassified_ |
| 5.5 | fow_entries | [[54, 1, "Porel", "4.3"]] | [[40, 1, "Porel", "4.3"]] | E3-wicket-frame-misalign |
| 5.6 | score | 55 | 53 | _unclassified_ |
| 5.6 | striker_name | — | Rahul | D-post-FoW-striker |
| 5.6 | striker_runs | 0 | 18 | _unclassified_ |
| 5.6 | striker_balls | 0 | 12 | _unclassified_ |
| 5.6 | striker_fours | 0 | 1 | _unclassified_ |
| 5.6 | striker_sixes | 0 | 1 | _unclassified_ |
| 5.6 | non_striker_name | — | Parakh | _unclassified_ |
| 5.6 | non_striker_runs | 0 | 11 | _unclassified_ |
| 5.6 | non_striker_balls | 0 | 6 | _unclassified_ |
| 5.6 | non_striker_fours | 0 | 1 | _unclassified_ |
| 5.6 | non_striker_sixes | 0 | 1 | _unclassified_ |
| 5.6 | bowler_name | Chakaravarthy | Narine | F-B-ad-occlusion |
| 5.6 | bowler_overs | 4.5 | 1.0 | F-A-commit-lag |
| 5.6 | bowler_runs | 36 | 11 | _unclassified_ |
| 5.6 | bowler_wickets | 1 | 0 | _unclassified_ |
| 5.6 | extras_total | 0 | 2 | Extras-counter-drop |
| 5.6 | extras_wd | 0 | 2 | Extras-counter-drop |
| 5.6 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | ["1", ".", "6", ".", ".", "4"] | _unclassified_ |
| 5.6 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"]] | E3-wicket-frame-misalign |
| 6.4 | striker_runs | 22 | 19 | _unclassified_ |
| 6.4 | striker_balls | 15 | 14 | _unclassified_ |
| 6.4 | striker_sixes | 2 | 1 | Boundary-counter-double-increment |
| 6.4 | non_striker_name | Porel | Parakh | _unclassified_ |
| 6.4 | non_striker_runs | 30 | 12 | _unclassified_ |
| 6.4 | non_striker_balls | 17 | 8 | _unclassified_ |
| 6.4 | non_striker_fours | 2 | 1 | _unclassified_ |
| 6.4 | non_striker_sixes | 2 | 1 | _unclassified_ |
| 6.4 | bowler_overs | 0.2 | 0.4 | F-A-commit-lag |
| 6.4 | bowler_runs | 1 | 2 | _unclassified_ |
| 6.4 | extras_total | 0 | 2 | Extras-counter-drop |
| 6.4 | extras_wd | 0 | 2 | Extras-counter-drop |
| 6.4 | this_over_tokens | ["?", "?", "6", ".", ".", "4"] | [".", "1", ".", "1"] | _unclassified_ |
| 6.4 | fow_entries | [[54, 1, "Porel", "4.3"]] | [[40, 1, "Porel", "4.3"]] | E3-wicket-frame-misalign |
| 6.5 | striker_name | Porel | Parakh | D-post-FoW-striker |
| 6.5 | striker_runs | 30 | 12 | _unclassified_ |
| 6.5 | striker_balls | 17 | 8 | _unclassified_ |
| 6.5 | striker_fours | 2 | 1 | Boundary-counter-double-increment |
| 6.5 | striker_sixes | 2 | 1 | Boundary-counter-double-increment |
| 6.5 | non_striker_runs | 23 | 20 | _unclassified_ |
| 6.5 | non_striker_balls | 16 | 15 | _unclassified_ |
| 6.5 | non_striker_sixes | 2 | 1 | _unclassified_ |
| 6.5 | bowler_overs | 0.3 | 0.5 | F-A-commit-lag |
| 6.5 | bowler_runs | 2 | 3 | _unclassified_ |
| 6.5 | extras_total | 0 | 2 | Extras-counter-drop |
| 6.5 | extras_wd | 0 | 2 | Extras-counter-drop |
| 6.5 | this_over_tokens | ["?", "?", "?", "?", "1"] | [".", "1", ".", "1", "1"] | _unclassified_ |
| 6.5 | fow_entries | [[54, 1, "Porel", "4.3"]] | [[40, 1, "Porel", "4.3"]] | E3-wicket-frame-misalign |
| 7.1 | striker_name | Porel | Rahul | D-post-FoW-striker |
| 7.1 | striker_runs | 30 | 20 | _unclassified_ |
| 7.1 | striker_balls | 17 | 15 | _unclassified_ |
| 7.1 | striker_fours | 2 | 1 | Boundary-counter-double-increment |
| 7.1 | striker_sixes | 2 | 1 | Boundary-counter-double-increment |
| 7.1 | non_striker_name | Rahul | Parakh | _unclassified_ |
| 7.1 | non_striker_runs | 24 | 14 | _unclassified_ |
| 7.1 | non_striker_balls | 17 | 10 | _unclassified_ |
| 7.1 | non_striker_sixes | 2 | 1 | _unclassified_ |
| 7.1 | bowler_overs | 1.4 | 1.1 | F-A-commit-lag |
| 7.1 | bowler_runs | 14 | 12 | _unclassified_ |
| 7.1 | extras_total | 0 | 2 | Extras-counter-drop |
| 7.1 | extras_wd | 0 | 2 | Extras-counter-drop |
| 7.1 | this_over_tokens | ["?", "?", "?", "?", "1"] | ["1"] | _unclassified_ |
| 7.1 | recent_over_n_minus_1 | [] | [".", "1", ".", "1", "1", "1"] | Recent-overs-drop |
| 7.1 | fow_entries | [[54, 1, "Porel", "4.3"]] | [[40, 1, "Porel", "4.3"]] | E3-wicket-frame-misalign |
| 7.2 | score | 66 | 64 | _unclassified_ |
| 7.2 | striker_name | Porel | Rahul | D-post-FoW-striker |
| 7.2 | striker_runs | 30 | 26 | _unclassified_ |
| 7.2 | striker_balls | 17 | 16 | _unclassified_ |
| 7.2 | striker_fours | 2 | 1 | _unclassified_ |
| 7.2 | non_striker_name | Rahul | Parakh | _unclassified_ |
| 7.2 | non_striker_runs | 24 | 14 | _unclassified_ |
| 7.2 | non_striker_balls | 17 | 10 | _unclassified_ |
| 7.2 | non_striker_sixes | 2 | 1 | _unclassified_ |
| 7.2 | bowler_overs | 1.5 | 1.2 | F-A-commit-lag |
| 7.2 | bowler_runs | 22 | 18 | _unclassified_ |
| 7.2 | extras_total | 0 | 2 | Extras-counter-drop |
| 7.2 | extras_wd | 0 | 2 | Extras-counter-drop |
| 7.2 | this_over_tokens | ["?", "?", "?", "?", "1", "8"] | ["1", "6"] | _unclassified_ |
| 7.2 | fow_entries | [[54, 1, "Porel", "4.3"]] | [[40, 1, "Porel", "4.3"]] | E3-wicket-frame-misalign |
| 7.3 | striker_name | Porel | Rahul | D-post-FoW-striker |
| 7.3 | non_striker_name | Rahul | Parakh | _unclassified_ |
| 7.3 | non_striker_runs | 24 | 14 | _unclassified_ |
| 7.3 | non_striker_balls | 17 | 10 | _unclassified_ |
| 7.3 | non_striker_sixes | 2 | 1 | _unclassified_ |
| 7.3 | bowler_overs | 2.0 | 1.3 | F-A-commit-lag |
| 7.3 | bowler_runs | 24 | 22 | _unclassified_ |
| 7.3 | extras_total | 0 | 2 | Extras-counter-drop |
| 7.3 | extras_wd | 0 | 2 | Extras-counter-drop |
| 7.3 | this_over_tokens | ["?", "?", "?", "?", "1", "8", "2"] | ["1", "6", "4"] | _unclassified_ |
| 7.3 | fow_entries | [[54, 1, "Porel", "4.3"]] | [[40, 1, "Porel", "4.3"]] | E3-wicket-frame-misalign |
| 7.5 | striker_name | Porel | Rahul | D-post-FoW-striker |
| 7.5 | striker_runs | 30 | 31 | _unclassified_ |
| 7.5 | striker_balls | 17 | 18 | _unclassified_ |
| 7.5 | non_striker_name | Rahul | Parakh | _unclassified_ |
| 7.5 | non_striker_runs | 25 | 15 | _unclassified_ |
| 7.5 | non_striker_balls | 18 | 11 | _unclassified_ |
| 7.5 | non_striker_sixes | 2 | 1 | _unclassified_ |
| 7.5 | bowler_overs | 2.2 | 1.5 | F-A-commit-lag |
| 7.5 | bowler_runs | 26 | 24 | _unclassified_ |
| 7.5 | extras_total | 0 | 2 | Extras-counter-drop |
| 7.5 | extras_wd | 0 | 2 | Extras-counter-drop |
| 7.5 | this_over_tokens | ["?", "?", "?", "?", "1", "8", "2"] | ["1", "6", "4", "1", "1"] | _unclassified_ |
| 7.5 | fow_entries | [[54, 1, "Porel", "4.3"]] | [[40, 1, "Porel", "4.3"]] | E3-wicket-frame-misalign |
| 7.6 | striker_name | Porel | Parakh | D-post-FoW-striker |
| 7.6 | striker_runs | 30 | 15 | _unclassified_ |
| 7.6 | striker_balls | 17 | 11 | _unclassified_ |
| 7.6 | striker_fours | 2 | 1 | Boundary-counter-double-increment |
| 7.6 | striker_sixes | 2 | 1 | Boundary-counter-double-increment |
| 7.6 | non_striker_runs | 25 | 31 | _unclassified_ |
| 7.6 | non_striker_fours | 1 | 2 | _unclassified_ |
| 7.6 | bowler_overs | 2.3 | 2.0 | F-A-commit-lag |
| 7.6 | bowler_runs | 26 | 24 | _unclassified_ |
| 7.6 | extras_total | 0 | 2 | Extras-counter-drop |
| 7.6 | extras_wd | 0 | 2 | Extras-counter-drop |
| 7.6 | this_over_tokens | ["?", "?", "?", "?", "1", "8", "2", "."] | ["1", "6", "4", "1", "1", "."] | _unclassified_ |
| 7.6 | fow_entries | [[54, 1, "Porel", "4.3"]] | [[40, 1, "Porel", "4.3"]] | E3-wicket-frame-misalign |
| 8.5 | striker_runs | 25 | 31 | _unclassified_ |
| 8.5 | striker_fours | 1 | 2 | _unclassified_ |
| 8.5 | non_striker_name | Porel | Parakh | _unclassified_ |
| 8.5 | non_striker_runs | 30 | 24 | _unclassified_ |
| 8.5 | non_striker_balls | 17 | 16 | _unclassified_ |
| 8.5 | non_striker_fours | 2 | 3 | _unclassified_ |
| 8.5 | non_striker_sixes | 2 | 1 | _unclassified_ |
| 8.5 | bowler_overs | 1.2 | 1.5 | F-A-commit-lag |
| 8.5 | bowler_runs | 11 | 13 | _unclassified_ |
| 8.5 | extras_total | 0 | 2 | Extras-counter-drop |
| 8.5 | extras_wd | 0 | 2 | Extras-counter-drop |
| 8.5 | this_over_tokens | ["?", "?", "?", "?", "1"] | [".", "4", ".", "4", "1"] | _unclassified_ |
| 8.5 | fow_entries | [[54, 1, "Porel", "4.3"]] | [[40, 1, "Porel", "4.3"]] | E3-wicket-frame-misalign |
| 9.3 | striker_name | Rahul | — | D-post-FoW-striker |
| 9.3 | striker_runs | 32 | 0 | _unclassified_ |
| 9.3 | striker_balls | 21 | 0 | _unclassified_ |
| 9.3 | striker_fours | 1 | 0 | Boundary-counter-double-increment |
| 9.3 | striker_sixes | 3 | 0 | Boundary-counter-double-increment |
| 9.3 | non_striker_name | Porel | Rahul | _unclassified_ |
| 9.3 | non_striker_runs | 30 | 39 | _unclassified_ |
| 9.3 | non_striker_balls | 17 | 22 | _unclassified_ |
| 9.3 | non_striker_sixes | 2 | 3 | _unclassified_ |
| 9.3 | bowler_overs | 3.1 | 2.3 | F-A-commit-lag |
| 9.3 | bowler_runs | 34 | 31 | _unclassified_ |
| 9.3 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 9.3 | extras_total | 0 | 2 | Extras-counter-drop |
| 9.3 | extras_wd | 0 | 2 | Extras-counter-drop |
| 9.3 | this_over_tokens | ["?", "?", "?", "?", "1", "."] | ["6", "1", "W"] | C21b-symbol-revert |
| 9.3 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"]] | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"]] | E3-wicket-frame-misalign |
| 9.6 | score | 89 | 88 | E2-phantom-runs |
| 9.6 | striker_name | Rahul | Patel | D-post-FoW-striker |
| 9.6 | striker_runs | 32 | 1 | _unclassified_ |
| 9.6 | striker_balls | 21 | 3 | _unclassified_ |
| 9.6 | striker_fours | 1 | 0 | _unclassified_ |
| 9.6 | striker_sixes | 3 | 0 | _unclassified_ |
| 9.6 | non_striker_name | Porel | Rahul | _unclassified_ |
| 9.6 | non_striker_runs | 30 | 39 | _unclassified_ |
| 9.6 | non_striker_balls | 17 | 22 | _unclassified_ |
| 9.6 | non_striker_sixes | 2 | 3 | _unclassified_ |
| 9.6 | bowler_overs | 3.4 | 3.0 | F-A-commit-lag |
| 9.6 | bowler_runs | 36 | 32 | _unclassified_ |
| 9.6 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 9.6 | extras_total | 0 | 2 | Extras-counter-drop |
| 9.6 | extras_wd | 0 | 2 | Extras-counter-drop |
| 9.6 | this_over_tokens | ["?", "?", "?", "?", "1", "."] | ["6", "1", "W", ".", ".", "1"] | C21b-symbol-revert |
| 9.6 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"]] | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"]] | E3-wicket-frame-misalign |
| 10.2 | striker_runs | 32 | 43 | _unclassified_ |
| 10.2 | striker_balls | 21 | 23 | _unclassified_ |
| 10.2 | striker_fours | 1 | 3 | _unclassified_ |
| 10.2 | non_striker_name | Porel | Patel | _unclassified_ |
| 10.2 | non_striker_runs | 30 | 2 | _unclassified_ |
| 10.2 | non_striker_balls | 17 | 4 | _unclassified_ |
| 10.2 | non_striker_fours | 2 | 0 | _unclassified_ |
| 10.2 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 10.2 | bowler_overs | 2.4 | 1.2 | F-A-commit-lag |
| 10.2 | bowler_runs | 26 | 18 | _unclassified_ |
| 10.2 | extras_total | 0 | 2 | Extras-counter-drop |
| 10.2 | extras_wd | 0 | 2 | Extras-counter-drop |
| 10.2 | this_over_tokens | ["?", "?", "?", "?", "1", ".", "4"] | ["1", "4"] | _unclassified_ |
| 10.2 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"]] | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"]] | E3-wicket-frame-misalign |
| 10.3 | striker_runs | 32 | 49 | _unclassified_ |
| 10.3 | striker_balls | 21 | 24 | _unclassified_ |
| 10.3 | striker_fours | 1 | 3 | _unclassified_ |
| 10.3 | striker_sixes | 3 | 4 | _unclassified_ |
| 10.3 | non_striker_name | Porel | Patel | _unclassified_ |
| 10.3 | non_striker_runs | 30 | 2 | _unclassified_ |
| 10.3 | non_striker_balls | 17 | 4 | _unclassified_ |
| 10.3 | non_striker_fours | 2 | 0 | _unclassified_ |
| 10.3 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 10.3 | bowler_overs | 2.5 | 1.3 | F-A-commit-lag |
| 10.3 | bowler_runs | 32 | 24 | _unclassified_ |
| 10.3 | extras_total | 0 | 2 | Extras-counter-drop |
| 10.3 | extras_wd | 0 | 2 | Extras-counter-drop |
| 10.3 | this_over_tokens | ["?", "?", "?", "?", "1", ".", "4", "6"] | ["1", "4", "6"] | _unclassified_ |
| 10.3 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"]] | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"]] | E3-wicket-frame-misalign |
| 10.4 | striker_name | Porel | Patel | D-post-FoW-striker |
| 10.4 | striker_runs | 30 | 2 | _unclassified_ |
| 10.4 | striker_balls | 17 | 4 | _unclassified_ |
| 10.4 | striker_fours | 2 | 0 | Boundary-counter-double-increment |
| 10.4 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 10.4 | non_striker_runs | 32 | 50 | _unclassified_ |
| 10.4 | non_striker_balls | 21 | 25 | _unclassified_ |
| 10.4 | non_striker_fours | 1 | 3 | _unclassified_ |
| 10.4 | non_striker_sixes | 3 | 4 | _unclassified_ |
| 10.4 | bowler_overs | 3.0 | 1.4 | F-A-commit-lag |
| 10.4 | bowler_runs | 33 | 25 | _unclassified_ |
| 10.4 | extras_total | 0 | 2 | Extras-counter-drop |
| 10.4 | extras_wd | 0 | 2 | Extras-counter-drop |
| 10.4 | this_over_tokens | ["?", "?", "?", "?", "1", ".", "4", "6", "1"] | ["1", "4", "6", "1"] | _unclassified_ |
| 10.4 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"]] | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"]] | E3-wicket-frame-misalign |
| 10.5 | striker_name | Porel | Patel | D-post-FoW-striker |
| 10.5 | striker_runs | 30 | 6 | _unclassified_ |
| 10.5 | striker_balls | 17 | 5 | _unclassified_ |
| 10.5 | striker_fours | 2 | 1 | Boundary-counter-double-increment |
| 10.5 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 10.5 | non_striker_runs | 32 | 50 | _unclassified_ |
| 10.5 | non_striker_balls | 21 | 25 | _unclassified_ |
| 10.5 | non_striker_fours | 1 | 3 | _unclassified_ |
| 10.5 | non_striker_sixes | 3 | 4 | _unclassified_ |
| 10.5 | bowler_overs | 3.1 | 1.5 | F-A-commit-lag |
| 10.5 | bowler_runs | 37 | 29 | _unclassified_ |
| 10.5 | extras_total | 0 | 2 | Extras-counter-drop |
| 10.5 | extras_wd | 0 | 2 | Extras-counter-drop |
| 10.5 | this_over_tokens | ["?", "?", "?", "?", "1", ".", "4", "6", "1", "4"] | ["1", "4", "6", "1", "4"] | _unclassified_ |
| 10.5 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"]] | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"]] | E3-wicket-frame-misalign |
| 10.6 | striker_name | Porel | Rahul | D-post-FoW-striker |
| 10.6 | striker_runs | 30 | 50 | _unclassified_ |
| 10.6 | striker_balls | 17 | 25 | _unclassified_ |
| 10.6 | striker_fours | 2 | 3 | _unclassified_ |
| 10.6 | striker_sixes | 2 | 4 | _unclassified_ |
| 10.6 | non_striker_name | Rahul | Patel | _unclassified_ |
| 10.6 | non_striker_runs | 32 | 10 | _unclassified_ |
| 10.6 | non_striker_balls | 21 | 6 | _unclassified_ |
| 10.6 | non_striker_fours | 1 | 2 | _unclassified_ |
| 10.6 | non_striker_sixes | 3 | 0 | _unclassified_ |
| 10.6 | bowler_overs | 3.2 | 2.0 | F-A-commit-lag |
| 10.6 | bowler_runs | 41 | 33 | _unclassified_ |
| 10.6 | extras_total | 0 | 2 | Extras-counter-drop |
| 10.6 | extras_wd | 0 | 2 | Extras-counter-drop |
| 10.6 | this_over_tokens | ["?", "?", "?", "?", "1", ".", "4", "6", "1", "4", "4"] | ["1", "4", "6", "1", "4", "4"] | _unclassified_ |
| 10.6 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"]] | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"]] | E3-wicket-frame-misalign |
| 11.3 | striker_name | Rahul | Patel | D-post-FoW-striker |
| 11.3 | striker_runs | 32 | 12 | _unclassified_ |
| 11.3 | striker_balls | 21 | 8 | _unclassified_ |
| 11.3 | striker_fours | 1 | 2 | _unclassified_ |
| 11.3 | striker_sixes | 3 | 0 | Boundary-counter-double-increment |
| 11.3 | non_striker_name | Porel | Rahul | _unclassified_ |
| 11.3 | non_striker_runs | 30 | 51 | _unclassified_ |
| 11.3 | non_striker_balls | 17 | 26 | _unclassified_ |
| 11.3 | non_striker_fours | 2 | 3 | _unclassified_ |
| 11.3 | non_striker_sixes | 2 | 4 | _unclassified_ |
| 11.3 | bowler_name | Tyagi | Narine | F-B-ad-occlusion |
| 11.3 | bowler_overs | 3.5 | 3.3 | F-A-commit-lag |
| 11.3 | bowler_runs | 44 | 35 | _unclassified_ |
| 11.3 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 11.3 | extras_total | 0 | 2 | Extras-counter-drop |
| 11.3 | extras_wd | 0 | 2 | Extras-counter-drop |
| 11.3 | this_over_tokens | ["?", "?", "?", "?", "1", ".", "4", "6", "1", "4", "4"] | ["1", "2", "."] | _unclassified_ |
| 11.3 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"]] | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"]] | E3-wicket-frame-misalign |
| 11.4 | striker_name | Porel | Rahul | D-post-FoW-striker |
| 11.4 | striker_runs | 30 | 51 | _unclassified_ |
| 11.4 | striker_balls | 17 | 26 | _unclassified_ |
| 11.4 | striker_fours | 2 | 3 | _unclassified_ |
| 11.4 | striker_sixes | 2 | 4 | _unclassified_ |
| 11.4 | non_striker_name | Rahul | Patel | _unclassified_ |
| 11.4 | non_striker_runs | 32 | 13 | _unclassified_ |
| 11.4 | non_striker_balls | 21 | 9 | _unclassified_ |
| 11.4 | non_striker_fours | 1 | 2 | _unclassified_ |
| 11.4 | non_striker_sixes | 3 | 0 | _unclassified_ |
| 11.4 | bowler_name | Tyagi | Narine | F-B-ad-occlusion |
| 11.4 | bowler_overs | 4.0 | 3.4 | F-A-commit-lag |
| 11.4 | bowler_runs | 45 | 36 | _unclassified_ |
| 11.4 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 11.4 | extras_total | 0 | 2 | Extras-counter-drop |
| 11.4 | extras_wd | 0 | 2 | Extras-counter-drop |
| 11.4 | this_over_tokens | ["?", "?", "?", "1"] | ["1", "2", ".", "1"] | _unclassified_ |
| 11.4 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"]] | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"]] | E3-wicket-frame-misalign |
| 11.5 | striker_name | Rahul | Patel | D-post-FoW-striker |
| 11.5 | striker_runs | 32 | 13 | _unclassified_ |
| 11.5 | striker_balls | 21 | 9 | _unclassified_ |
| 11.5 | striker_fours | 1 | 2 | _unclassified_ |
| 11.5 | striker_sixes | 3 | 0 | Boundary-counter-double-increment |
| 11.5 | non_striker_name | Porel | Rahul | _unclassified_ |
| 11.5 | non_striker_runs | 30 | 52 | _unclassified_ |
| 11.5 | non_striker_balls | 17 | 27 | _unclassified_ |
| 11.5 | non_striker_fours | 2 | 3 | _unclassified_ |
| 11.5 | non_striker_sixes | 2 | 4 | _unclassified_ |
| 11.5 | bowler_name | Tyagi | Narine | F-B-ad-occlusion |
| 11.5 | bowler_overs | 4.1 | 3.5 | F-A-commit-lag |
| 11.5 | bowler_runs | 46 | 37 | _unclassified_ |
| 11.5 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 11.5 | extras_total | 0 | 2 | Extras-counter-drop |
| 11.5 | extras_wd | 0 | 2 | Extras-counter-drop |
| 11.5 | this_over_tokens | ["?", "?", "?", "1", "1"] | ["1", "2", ".", "1", "1"] | _unclassified_ |
| 11.5 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"]] | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"]] | E3-wicket-frame-misalign |
| 11.6 | striker_name | Rahul | Patel | D-post-FoW-striker |
| 11.6 | striker_runs | 32 | 14 | _unclassified_ |
| 11.6 | striker_balls | 21 | 10 | _unclassified_ |
| 11.6 | striker_fours | 1 | 2 | _unclassified_ |
| 11.6 | striker_sixes | 3 | 0 | Boundary-counter-double-increment |
| 11.6 | non_striker_name | Porel | Rahul | _unclassified_ |
| 11.6 | non_striker_runs | 30 | 52 | _unclassified_ |
| 11.6 | non_striker_balls | 17 | 27 | _unclassified_ |
| 11.6 | non_striker_fours | 2 | 3 | _unclassified_ |
| 11.6 | non_striker_sixes | 2 | 4 | _unclassified_ |
| 11.6 | bowler_name | — | Narine | F-B-ad-occlusion |
| 11.6 | bowler_overs | — | 4.0 | F-A-commit-lag |
| 11.6 | bowler_runs | 0 | 38 | _unclassified_ |
| 11.6 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 11.6 | extras_total | 0 | 2 | Extras-counter-drop |
| 11.6 | extras_wd | 0 | 2 | Extras-counter-drop |
| 11.6 | this_over_tokens | ["?", "?", "?", "1", "1", "1"] | ["1", "2", ".", "1", "1", "1"] | _unclassified_ |
| 11.6 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"]] | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"]] | E3-wicket-frame-misalign |
| 12.1 | score | 116 | 115 | E2-phantom-runs |
| 12.1 | striker_runs | 32 | 52 | _unclassified_ |
| 12.1 | striker_balls | 21 | 27 | _unclassified_ |
| 12.1 | striker_fours | 1 | 3 | _unclassified_ |
| 12.1 | striker_sixes | 3 | 4 | _unclassified_ |
| 12.1 | non_striker_name | Porel | Patel | _unclassified_ |
| 12.1 | non_striker_runs | 30 | 15 | _unclassified_ |
| 12.1 | non_striker_balls | 17 | 11 | _unclassified_ |
| 12.1 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 12.1 | bowler_name | — | Roy | F-B-ad-occlusion |
| 12.1 | bowler_overs | — | 1.1 | F-A-commit-lag |
| 12.1 | bowler_runs | 0 | 11 | _unclassified_ |
| 12.1 | extras_total | 0 | 2 | Extras-counter-drop |
| 12.1 | extras_wd | 0 | 2 | Extras-counter-drop |
| 12.1 | this_over_tokens | ["2"] | ["1"] | _unclassified_ |
| 12.1 | recent_over_n_minus_1 | [] | ["1", "2", ".", "1", "1", "1"] | Recent-overs-drop |
| 12.1 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"]] | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"]] | E3-wicket-frame-misalign |
| 12.4 | non_striker_name | Porel | Patel | _unclassified_ |
| 12.4 | non_striker_runs | 30 | 15 | _unclassified_ |
| 12.4 | non_striker_balls | 17 | 11 | _unclassified_ |
| 12.4 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 12.4 | bowler_name | — | Roy | F-B-ad-occlusion |
| 12.4 | bowler_overs | — | 1.4 | F-A-commit-lag |
| 12.4 | bowler_runs | 0 | 21 | _unclassified_ |
| 12.4 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 12.4 | extras_total | 0 | 4 | Extras-counter-drop |
| 12.4 | extras_wd | 0 | 4 | Extras-counter-drop |
| 12.4 | this_over_tokens | ["2"] | ["1", "Wd", "4", "Wd", "4", "W"] | C21b-symbol-revert |
| 12.4 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 12.5 | striker_name | — | Patel | D-post-FoW-striker |
| 12.5 | striker_runs | 0 | 15 | _unclassified_ |
| 12.5 | striker_balls | 0 | 11 | _unclassified_ |
| 12.5 | striker_fours | 0 | 2 | _unclassified_ |
| 12.5 | non_striker_name | Porel | Miller | _unclassified_ |
| 12.5 | non_striker_runs | 30 | 1 | _unclassified_ |
| 12.5 | non_striker_balls | 17 | 1 | _unclassified_ |
| 12.5 | non_striker_fours | 2 | 0 | _unclassified_ |
| 12.5 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 12.5 | bowler_overs | 2.2 | 1.5 | F-A-commit-lag |
| 12.5 | bowler_runs | 15 | 22 | _unclassified_ |
| 12.5 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 12.5 | extras_total | 0 | 4 | Extras-counter-drop |
| 12.5 | extras_wd | 0 | 4 | Extras-counter-drop |
| 12.5 | this_over_tokens | ["2", "?", "?", "?", "1"] | ["1", "Wd", "4", "Wd", "4", "W", "1"] | C21b-symbol-revert |
| 12.5 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 12.6 | striker_name | — | Patel | D-post-FoW-striker |
| 12.6 | striker_runs | 0 | 16 | _unclassified_ |
| 12.6 | striker_balls | 0 | 12 | _unclassified_ |
| 12.6 | striker_fours | 0 | 2 | _unclassified_ |
| 12.6 | non_striker_name | Porel | Miller | _unclassified_ |
| 12.6 | non_striker_runs | 30 | 1 | _unclassified_ |
| 12.6 | non_striker_balls | 17 | 1 | _unclassified_ |
| 12.6 | non_striker_fours | 2 | 0 | _unclassified_ |
| 12.6 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 12.6 | bowler_overs | 2.3 | 2.0 | F-A-commit-lag |
| 12.6 | bowler_runs | 16 | 23 | _unclassified_ |
| 12.6 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 12.6 | extras_total | 0 | 4 | Extras-counter-drop |
| 12.6 | extras_wd | 0 | 4 | Extras-counter-drop |
| 12.6 | this_over_tokens | ["2", "?", "?", "?", "1", "1"] | ["1", "Wd", "4", "Wd", "4", "W", "1", "1"] | C21b-symbol-revert |
| 12.6 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 13.1 | striker_name | — | Patel | D-post-FoW-striker |
| 13.1 | striker_runs | 0 | 16 | _unclassified_ |
| 13.1 | striker_balls | 0 | 13 | _unclassified_ |
| 13.1 | striker_fours | 0 | 2 | _unclassified_ |
| 13.1 | non_striker_name | Porel | Miller | _unclassified_ |
| 13.1 | non_striker_runs | 30 | 1 | _unclassified_ |
| 13.1 | non_striker_balls | 17 | 1 | _unclassified_ |
| 13.1 | non_striker_fours | 2 | 0 | _unclassified_ |
| 13.1 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 13.1 | bowler_name | Roy | Green | F-B-ad-occlusion |
| 13.1 | bowler_overs | 2.4 | 1.1 | F-A-commit-lag |
| 13.1 | bowler_runs | 17 | 14 | _unclassified_ |
| 13.1 | extras_total | 0 | 5 | Extras-counter-drop |
| 13.1 | extras_wd | 0 | 4 | Extras-counter-drop |
| 13.1 | extras_lb | 0 | 1 | Extras-counter-drop |
| 13.1 | this_over_tokens | ["1"] | ["1lb"] | _unclassified_ |
| 13.1 | recent_over_n_minus_1 | [] | ["1", "Wd", "4", "Wd", "4", "W", "1", "1"] | Recent-overs-drop |
| 13.1 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 13.3 | striker_name | — | Miller | D-post-FoW-striker |
| 13.3 | striker_runs | 0 | 2 | _unclassified_ |
| 13.3 | striker_balls | 0 | 2 | _unclassified_ |
| 13.3 | non_striker_name | Porel | Patel | _unclassified_ |
| 13.3 | non_striker_runs | 30 | 17 | _unclassified_ |
| 13.3 | non_striker_balls | 17 | 14 | _unclassified_ |
| 13.3 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 13.3 | bowler_name | Roy | Green | F-B-ad-occlusion |
| 13.3 | bowler_overs | 3.0 | 1.3 | F-A-commit-lag |
| 13.3 | bowler_runs | 19 | 16 | _unclassified_ |
| 13.3 | extras_total | 0 | 5 | Extras-counter-drop |
| 13.3 | extras_wd | 0 | 4 | Extras-counter-drop |
| 13.3 | extras_lb | 0 | 1 | Extras-counter-drop |
| 13.3 | this_over_tokens | ["1"] | ["1lb", "1", "1"] | Multi-ball-compression |
| 13.3 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 13.4 | striker_name | — | Miller | D-post-FoW-striker |
| 13.4 | striker_runs | 0 | 2 | _unclassified_ |
| 13.4 | striker_balls | 0 | 3 | _unclassified_ |
| 13.4 | non_striker_name | Porel | Patel | _unclassified_ |
| 13.4 | non_striker_runs | 30 | 17 | _unclassified_ |
| 13.4 | non_striker_balls | 17 | 14 | _unclassified_ |
| 13.4 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 13.4 | bowler_name | Roy | Green | F-B-ad-occlusion |
| 13.4 | bowler_overs | 3.1 | 1.4 | F-A-commit-lag |
| 13.4 | bowler_runs | 19 | 16 | _unclassified_ |
| 13.4 | extras_total | 0 | 5 | Extras-counter-drop |
| 13.4 | extras_wd | 0 | 4 | Extras-counter-drop |
| 13.4 | extras_lb | 0 | 1 | Extras-counter-drop |
| 13.4 | this_over_tokens | ["1", "?", "?", "."] | ["1lb", "1", "1", "."] | _unclassified_ |
| 13.4 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 14.2 | striker_name | — | Patel | D-post-FoW-striker |
| 14.2 | striker_runs | 0 | 21 | _unclassified_ |
| 14.2 | striker_balls | 0 | 16 | _unclassified_ |
| 14.2 | striker_fours | 0 | 3 | _unclassified_ |
| 14.2 | non_striker_name | Porel | Miller | _unclassified_ |
| 14.2 | non_striker_runs | 30 | 4 | _unclassified_ |
| 14.2 | non_striker_balls | 17 | 5 | _unclassified_ |
| 14.2 | non_striker_fours | 2 | 0 | _unclassified_ |
| 14.2 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 14.2 | bowler_overs | 2.0 | 2.2 | F-A-commit-lag |
| 14.2 | bowler_runs | 17 | 15 | _unclassified_ |
| 14.2 | extras_total | 0 | 5 | Extras-counter-drop |
| 14.2 | extras_wd | 0 | 4 | Extras-counter-drop |
| 14.2 | extras_lb | 0 | 1 | Extras-counter-drop |
| 14.2 | this_over_tokens | ["1", "?", "?", "."] | ["1", "."] | _unclassified_ |
| 14.2 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 14.3 | striker_name | — | Miller | D-post-FoW-striker |
| 14.3 | striker_runs | 0 | 4 | _unclassified_ |
| 14.3 | striker_balls | 0 | 5 | _unclassified_ |
| 14.3 | non_striker_name | Porel | Patel | _unclassified_ |
| 14.3 | non_striker_runs | 30 | 22 | _unclassified_ |
| 14.3 | non_striker_fours | 2 | 3 | _unclassified_ |
| 14.3 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 14.3 | bowler_overs | 2.1 | 2.3 | F-A-commit-lag |
| 14.3 | bowler_runs | 18 | 16 | _unclassified_ |
| 14.3 | extras_total | 0 | 5 | Extras-counter-drop |
| 14.3 | extras_wd | 0 | 4 | Extras-counter-drop |
| 14.3 | extras_lb | 0 | 1 | Extras-counter-drop |
| 14.3 | this_over_tokens | ["1", "?", "?", ".", "1"] | ["1", ".", "1"] | _unclassified_ |
| 14.3 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 14.4 | striker_name | — | Miller | D-post-FoW-striker |
| 14.4 | striker_runs | 0 | 4 | _unclassified_ |
| 14.4 | striker_balls | 0 | 6 | _unclassified_ |
| 14.4 | non_striker_name | Porel | Patel | _unclassified_ |
| 14.4 | non_striker_runs | 30 | 22 | _unclassified_ |
| 14.4 | non_striker_fours | 2 | 3 | _unclassified_ |
| 14.4 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 14.4 | bowler_overs | 2.2 | 2.4 | F-A-commit-lag |
| 14.4 | bowler_runs | 19 | 16 | _unclassified_ |
| 14.4 | extras_total | 0 | 6 | Extras-counter-drop |
| 14.4 | extras_wd | 0 | 4 | Extras-counter-drop |
| 14.4 | extras_lb | 0 | 2 | Extras-counter-drop |
| 14.4 | this_over_tokens | ["1", "?", "?", ".", "1"] | ["1", ".", "1", "1lb"] | _unclassified_ |
| 14.4 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 14.5 | striker_name | — | Miller | D-post-FoW-striker |
| 14.5 | striker_runs | 0 | 4 | _unclassified_ |
| 14.5 | striker_balls | 0 | 6 | _unclassified_ |
| 14.5 | non_striker_name | Porel | Patel | _unclassified_ |
| 14.5 | non_striker_runs | 30 | 23 | _unclassified_ |
| 14.5 | non_striker_balls | 17 | 18 | _unclassified_ |
| 14.5 | non_striker_fours | 2 | 3 | _unclassified_ |
| 14.5 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 14.5 | bowler_overs | 2.3 | 2.5 | F-A-commit-lag |
| 14.5 | bowler_runs | 20 | 17 | _unclassified_ |
| 14.5 | extras_total | 0 | 6 | Extras-counter-drop |
| 14.5 | extras_wd | 0 | 4 | Extras-counter-drop |
| 14.5 | extras_lb | 0 | 2 | Extras-counter-drop |
| 14.5 | this_over_tokens | ["1", "?", "?", ".", "1"] | ["1", ".", "1", "1lb", "1"] | _unclassified_ |
| 14.5 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 14.6 | striker_name | — | Miller | D-post-FoW-striker |
| 14.6 | striker_runs | 0 | 5 | _unclassified_ |
| 14.6 | striker_balls | 0 | 7 | _unclassified_ |
| 14.6 | non_striker_name | Porel | Patel | _unclassified_ |
| 14.6 | non_striker_runs | 30 | 23 | _unclassified_ |
| 14.6 | non_striker_balls | 17 | 18 | _unclassified_ |
| 14.6 | non_striker_fours | 2 | 3 | _unclassified_ |
| 14.6 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 14.6 | bowler_overs | 2.4 | 3.0 | F-A-commit-lag |
| 14.6 | bowler_runs | 21 | 18 | _unclassified_ |
| 14.6 | extras_total | 0 | 6 | Extras-counter-drop |
| 14.6 | extras_wd | 0 | 4 | Extras-counter-drop |
| 14.6 | extras_lb | 0 | 2 | Extras-counter-drop |
| 14.6 | this_over_tokens | ["1", "?", "?", ".", "1", "1"] | ["1", ".", "1", "1lb", "1", "1"] | _unclassified_ |
| 14.6 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 15.1 | striker_name | — | Patel | D-post-FoW-striker |
| 15.1 | striker_runs | 0 | 23 | _unclassified_ |
| 15.1 | striker_balls | 0 | 18 | _unclassified_ |
| 15.1 | striker_fours | 0 | 3 | _unclassified_ |
| 15.1 | non_striker_name | Porel | Miller | _unclassified_ |
| 15.1 | non_striker_runs | 30 | 6 | _unclassified_ |
| 15.1 | non_striker_balls | 17 | 8 | _unclassified_ |
| 15.1 | non_striker_fours | 2 | 0 | _unclassified_ |
| 15.1 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 15.1 | bowler_overs | 4.3 | 2.1 | F-A-commit-lag |
| 15.1 | bowler_runs | 48 | 34 | _unclassified_ |
| 15.1 | extras_total | 0 | 6 | Extras-counter-drop |
| 15.1 | extras_wd | 0 | 4 | Extras-counter-drop |
| 15.1 | extras_lb | 0 | 2 | Extras-counter-drop |
| 15.1 | recent_over_n_minus_1 | [] | ["1", ".", "1", "1lb", "1", "1"] | Recent-overs-drop |
| 15.1 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 15.2 | striker_name | — | Miller | D-post-FoW-striker |
| 15.2 | striker_runs | 0 | 6 | _unclassified_ |
| 15.2 | striker_balls | 0 | 8 | _unclassified_ |
| 15.2 | non_striker_name | Porel | Patel | _unclassified_ |
| 15.2 | non_striker_runs | 30 | 24 | _unclassified_ |
| 15.2 | non_striker_balls | 17 | 19 | _unclassified_ |
| 15.2 | non_striker_fours | 2 | 3 | _unclassified_ |
| 15.2 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 15.2 | bowler_overs | 4.4 | 2.2 | F-A-commit-lag |
| 15.2 | bowler_runs | 49 | 35 | _unclassified_ |
| 15.2 | extras_total | 0 | 6 | Extras-counter-drop |
| 15.2 | extras_wd | 0 | 4 | Extras-counter-drop |
| 15.2 | extras_lb | 0 | 2 | Extras-counter-drop |
| 15.2 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 15.3 | striker_name | — | Miller | D-post-FoW-striker |
| 15.3 | striker_runs | 0 | 12 | _unclassified_ |
| 15.3 | striker_balls | 0 | 9 | _unclassified_ |
| 15.3 | striker_sixes | 0 | 1 | _unclassified_ |
| 15.3 | non_striker_name | Porel | Patel | _unclassified_ |
| 15.3 | non_striker_runs | 30 | 24 | _unclassified_ |
| 15.3 | non_striker_balls | 17 | 19 | _unclassified_ |
| 15.3 | non_striker_fours | 2 | 3 | _unclassified_ |
| 15.3 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 15.3 | bowler_overs | 4.5 | 2.3 | F-A-commit-lag |
| 15.3 | bowler_runs | 55 | 41 | _unclassified_ |
| 15.3 | extras_total | 0 | 6 | Extras-counter-drop |
| 15.3 | extras_wd | 0 | 4 | Extras-counter-drop |
| 15.3 | extras_lb | 0 | 2 | Extras-counter-drop |
| 15.3 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 15.4 | striker_name | — | Miller | D-post-FoW-striker |
| 15.4 | striker_runs | 0 | 12 | _unclassified_ |
| 15.4 | striker_balls | 0 | 10 | _unclassified_ |
| 15.4 | striker_sixes | 0 | 1 | _unclassified_ |
| 15.4 | non_striker_name | Porel | Patel | _unclassified_ |
| 15.4 | non_striker_runs | 30 | 24 | _unclassified_ |
| 15.4 | non_striker_balls | 17 | 19 | _unclassified_ |
| 15.4 | non_striker_fours | 2 | 3 | _unclassified_ |
| 15.4 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 15.4 | bowler_overs | 5.0 | 2.4 | F-A-commit-lag |
| 15.4 | bowler_runs | 55 | 41 | _unclassified_ |
| 15.4 | extras_total | 0 | 6 | Extras-counter-drop |
| 15.4 | extras_wd | 0 | 4 | Extras-counter-drop |
| 15.4 | extras_lb | 0 | 2 | Extras-counter-drop |
| 15.4 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 15.6 | striker_name | — | Patel | D-post-FoW-striker |
| 15.6 | striker_runs | 0 | 25 | _unclassified_ |
| 15.6 | striker_balls | 0 | 20 | _unclassified_ |
| 15.6 | striker_fours | 0 | 3 | _unclassified_ |
| 15.6 | non_striker_name | Porel | Miller | _unclassified_ |
| 15.6 | non_striker_runs | 30 | 13 | _unclassified_ |
| 15.6 | non_striker_balls | 17 | 11 | _unclassified_ |
| 15.6 | non_striker_fours | 2 | 0 | _unclassified_ |
| 15.6 | non_striker_sixes | 2 | 1 | _unclassified_ |
| 15.6 | bowler_name | Chakaravarthy | Tyagi | F-B-ad-occlusion |
| 15.6 | bowler_runs | 23 | 43 | _unclassified_ |
| 15.6 | extras_total | 0 | 6 | Extras-counter-drop |
| 15.6 | extras_wd | 0 | 4 | Extras-counter-drop |
| 15.6 | extras_lb | 0 | 2 | Extras-counter-drop |
| 15.6 | this_over_tokens | ["1", "1", "6", "."] | ["1", "1", "6", ".", "1", "1"] | Multi-ball-compression |
| 15.6 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 16.3 | striker_name | — | Patel | D-post-FoW-striker |
| 16.3 | striker_runs | 0 | 37 | _unclassified_ |
| 16.3 | striker_balls | 0 | 23 | _unclassified_ |
| 16.3 | striker_fours | 0 | 3 | _unclassified_ |
| 16.3 | striker_sixes | 0 | 2 | _unclassified_ |
| 16.3 | non_striker_name | Porel | Miller | _unclassified_ |
| 16.3 | non_striker_runs | 30 | 13 | _unclassified_ |
| 16.3 | non_striker_balls | 17 | 11 | _unclassified_ |
| 16.3 | non_striker_fours | 2 | 0 | _unclassified_ |
| 16.3 | non_striker_sixes | 2 | 1 | _unclassified_ |
| 16.3 | bowler_runs | 31 | 30 | _unclassified_ |
| 16.3 | extras_total | 0 | 6 | Extras-counter-drop |
| 16.3 | extras_wd | 0 | 4 | Extras-counter-drop |
| 16.3 | extras_lb | 0 | 2 | Extras-counter-drop |
| 16.3 | this_over_tokens | ["1", "1", "6", "."] | ["6", ".", "6"] | _unclassified_ |
| 16.3 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 16.5 | non_striker_name | Porel | Miller | _unclassified_ |
| 16.5 | non_striker_runs | 30 | 13 | _unclassified_ |
| 16.5 | non_striker_balls | 17 | 11 | _unclassified_ |
| 16.5 | non_striker_fours | 2 | 0 | _unclassified_ |
| 16.5 | non_striker_sixes | 2 | 1 | _unclassified_ |
| 16.5 | bowler_runs | 31 | 34 | _unclassified_ |
| 16.5 | extras_total | 0 | 8 | Extras-counter-drop |
| 16.5 | extras_wd | 0 | 6 | Extras-counter-drop |
| 16.5 | extras_lb | 0 | 2 | Extras-counter-drop |
| 16.5 | this_over_tokens | ["1", "1", "6", "."] | ["6", ".", "6", "Wd", "Wd", "2", "W"] | C21b-symbol-revert |
| 16.5 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 16.6 | striker_name | — | Sharma | D-post-FoW-striker |
| 16.6 | striker_runs | 0 | 1 | _unclassified_ |
| 16.6 | striker_balls | 0 | 1 | _unclassified_ |
| 16.6 | non_striker_name | Porel | Miller | _unclassified_ |
| 16.6 | non_striker_runs | 30 | 13 | _unclassified_ |
| 16.6 | non_striker_balls | 17 | 11 | _unclassified_ |
| 16.6 | non_striker_fours | 2 | 0 | _unclassified_ |
| 16.6 | non_striker_sixes | 2 | 1 | _unclassified_ |
| 16.6 | bowler_runs | 32 | 35 | _unclassified_ |
| 16.6 | extras_total | 0 | 8 | Extras-counter-drop |
| 16.6 | extras_wd | 0 | 6 | Extras-counter-drop |
| 16.6 | extras_lb | 0 | 2 | Extras-counter-drop |
| 16.6 | this_over_tokens | ["1", "1", "6", ".", "1"] | ["6", ".", "6", "Wd", "Wd", "2", "W", "1"] | C21b-symbol-revert |
| 16.6 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 17.1 | striker_name | — | Miller | D-post-FoW-striker |
| 17.1 | striker_runs | 0 | 13 | _unclassified_ |
| 17.1 | striker_balls | 0 | 11 | _unclassified_ |
| 17.1 | striker_sixes | 0 | 1 | _unclassified_ |
| 17.1 | non_striker_name | Porel | Sharma | _unclassified_ |
| 17.1 | non_striker_runs | 30 | 2 | _unclassified_ |
| 17.1 | non_striker_balls | 17 | 2 | _unclassified_ |
| 17.1 | non_striker_fours | 2 | 0 | _unclassified_ |
| 17.1 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 17.1 | bowler_name | Chakaravarthy | Dubey | F-B-ad-occlusion |
| 17.1 | bowler_overs | 4.1 | 2.1 | F-A-commit-lag |
| 17.1 | bowler_runs | 33 | 6 | _unclassified_ |
| 17.1 | extras_total | 0 | 8 | Extras-counter-drop |
| 17.1 | extras_wd | 0 | 6 | Extras-counter-drop |
| 17.1 | extras_lb | 0 | 2 | Extras-counter-drop |
| 17.1 | recent_over_n_minus_1 | [] | ["6", ".", "6", "Wd", "Wd", "2", "W", "1"] | Recent-overs-drop |
| 17.1 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 17.3 | wickets | 6 | 4 | _unclassified_ |
| 17.3 | striker_name | — | Sharma | D-post-FoW-striker |
| 17.3 | striker_runs | 0 | 2 | _unclassified_ |
| 17.3 | striker_balls | 0 | 2 | _unclassified_ |
| 17.3 | non_striker_name | Porel | Miller | _unclassified_ |
| 17.3 | non_striker_runs | 30 | 14 | _unclassified_ |
| 17.3 | non_striker_balls | 17 | 13 | _unclassified_ |
| 17.3 | non_striker_fours | 2 | 0 | _unclassified_ |
| 17.3 | non_striker_sixes | 2 | 1 | _unclassified_ |
| 17.3 | bowler_name | Chakaravarthy | Dubey | F-B-ad-occlusion |
| 17.3 | bowler_overs | 4.3 | 2.3 | F-A-commit-lag |
| 17.3 | bowler_runs | 34 | 7 | _unclassified_ |
| 17.3 | extras_total | 0 | 8 | Extras-counter-drop |
| 17.3 | extras_wd | 0 | 6 | Extras-counter-drop |
| 17.3 | extras_lb | 0 | 2 | Extras-counter-drop |
| 17.3 | this_over_tokens | ["1"] | ["1", ".", "1"] | Multi-ball-compression |
| 17.3 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 17.4 | wickets | 6 | 4 | _unclassified_ |
| 17.4 | striker_name | — | Miller | D-post-FoW-striker |
| 17.4 | striker_runs | 0 | 14 | _unclassified_ |
| 17.4 | striker_balls | 0 | 13 | _unclassified_ |
| 17.4 | striker_sixes | 0 | 1 | _unclassified_ |
| 17.4 | non_striker_name | Porel | Sharma | _unclassified_ |
| 17.4 | non_striker_runs | 30 | 3 | _unclassified_ |
| 17.4 | non_striker_balls | 17 | 3 | _unclassified_ |
| 17.4 | non_striker_fours | 2 | 0 | _unclassified_ |
| 17.4 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 17.4 | bowler_name | Chakaravarthy | Dubey | F-B-ad-occlusion |
| 17.4 | bowler_overs | 4.4 | 2.4 | F-A-commit-lag |
| 17.4 | bowler_runs | 35 | 8 | _unclassified_ |
| 17.4 | extras_total | 0 | 8 | Extras-counter-drop |
| 17.4 | extras_wd | 0 | 6 | Extras-counter-drop |
| 17.4 | extras_lb | 0 | 2 | Extras-counter-drop |
| 17.4 | this_over_tokens | ["1", "?", "?", "1"] | ["1", ".", "1", "1"] | _unclassified_ |
| 17.4 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 17.5 | wickets | 6 | 4 | _unclassified_ |
| 17.5 | striker_name | — | Sharma | D-post-FoW-striker |
| 17.5 | striker_runs | 0 | 3 | _unclassified_ |
| 17.5 | striker_balls | 0 | 3 | _unclassified_ |
| 17.5 | non_striker_name | Porel | Miller | _unclassified_ |
| 17.5 | non_striker_runs | 30 | 15 | _unclassified_ |
| 17.5 | non_striker_balls | 17 | 14 | _unclassified_ |
| 17.5 | non_striker_fours | 2 | 0 | _unclassified_ |
| 17.5 | non_striker_sixes | 2 | 1 | _unclassified_ |
| 17.5 | bowler_name | Chakaravarthy | Dubey | F-B-ad-occlusion |
| 17.5 | bowler_overs | 4.5 | 2.5 | F-A-commit-lag |
| 17.5 | bowler_runs | 36 | 9 | _unclassified_ |
| 17.5 | extras_total | 0 | 8 | Extras-counter-drop |
| 17.5 | extras_wd | 0 | 6 | Extras-counter-drop |
| 17.5 | extras_lb | 0 | 2 | Extras-counter-drop |
| 17.5 | this_over_tokens | ["1", "?", "?", "1", "1"] | ["1", ".", "1", "1", "1"] | _unclassified_ |
| 17.5 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 17.6 | wickets | 6 | 4 | _unclassified_ |
| 17.6 | striker_name | — | Miller | D-post-FoW-striker |
| 17.6 | striker_runs | 0 | 15 | _unclassified_ |
| 17.6 | striker_balls | 0 | 14 | _unclassified_ |
| 17.6 | striker_sixes | 0 | 1 | _unclassified_ |
| 17.6 | non_striker_name | Porel | Sharma | _unclassified_ |
| 17.6 | non_striker_runs | 30 | 7 | _unclassified_ |
| 17.6 | non_striker_balls | 17 | 4 | _unclassified_ |
| 17.6 | non_striker_fours | 2 | 1 | _unclassified_ |
| 17.6 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 17.6 | bowler_name | Tyagi | Dubey | F-B-ad-occlusion |
| 17.6 | bowler_overs | 5.1 | 3.0 | F-A-commit-lag |
| 17.6 | bowler_runs | 59 | 13 | _unclassified_ |
| 17.6 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 17.6 | extras_total | 0 | 8 | Extras-counter-drop |
| 17.6 | extras_wd | 0 | 6 | Extras-counter-drop |
| 17.6 | extras_lb | 0 | 2 | Extras-counter-drop |
| 17.6 | this_over_tokens | ["1", "?", "?", "1", "1", "4"] | ["1", ".", "1", "1", "1", "4"] | _unclassified_ |
| 17.6 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |
| 18.1 | wickets | 6 | 4 | _unclassified_ |
| 18.1 | striker_name | — | Sharma | D-post-FoW-striker |
| 18.1 | striker_runs | 0 | 7 | _unclassified_ |
| 18.1 | striker_balls | 0 | 4 | _unclassified_ |
| 18.1 | striker_fours | 0 | 1 | _unclassified_ |
| 18.1 | non_striker_name | Porel | Miller | _unclassified_ |
| 18.1 | non_striker_runs | 30 | 16 | _unclassified_ |
| 18.1 | non_striker_balls | 17 | 15 | _unclassified_ |
| 18.1 | non_striker_fours | 2 | 0 | _unclassified_ |
| 18.1 | non_striker_sixes | 2 | 1 | _unclassified_ |
| 18.1 | bowler_overs | 5.2 | 3.1 | F-A-commit-lag |
| 18.1 | bowler_runs | 60 | 44 | _unclassified_ |
| 18.1 | extras_total | 0 | 8 | Extras-counter-drop |
| 18.1 | extras_wd | 0 | 6 | Extras-counter-drop |
| 18.1 | extras_lb | 0 | 2 | Extras-counter-drop |
| 18.1 | recent_over_n_minus_1 | [] | ["1", ".", "1", "1", "1", "4"] | Recent-overs-drop |
| 18.1 | fow_entries | [[54, 1, "Porel", "4.3"], [88, 2, "Rahul", "9.3"], [125, … | [[40, 1, "Porel", "4.3"], [87, 2, "Parakh", "9.3"], [125,… | E3-wicket-frame-misalign |

## 3. Conservation invariants

All conservation checks passed.

## 4. Unclassified divergences

| over.ball | field | pipeline | ground-truth |
|---|---|---|---|
| 0.2 | striker_balls | 0 | 2 |
| 0.2 | non_striker_name | Rahul | — |
| 0.3 | striker_balls | 1 | 3 |
| 0.3 | non_striker_name | Rahul | — |
| 0.5 | striker_name | Rahul | — |
| 0.5 | non_striker_balls | 3 | 5 |
| 0.5 | non_striker_fours | 1 | 2 |
| 0.6 | non_striker_balls | 3 | 5 |
| 0.6 | non_striker_fours | 1 | 2 |
| 1.1 | score | 5 | 10 |
| 1.1 | striker_name | — | Rahul |
| 1.1 | striker_runs | 0 | 1 |
| 1.1 | striker_balls | 0 | 2 |
| 1.1 | non_striker_name | — | Porel |
| 1.1 | non_striker_runs | 0 | 9 |
| 1.1 | non_striker_balls | 0 | 5 |
| 1.1 | non_striker_fours | 0 | 2 |
| 1.1 | bowler_runs | 36 | 0 |
| 1.1 | bowler_wickets | 1 | 0 |
| 1.1 | this_over_tokens | [".", ".", "1", "1", "1", "1", "1"] | ["."] |
| 1.2 | striker_balls | 3 | 5 |
| 1.2 | striker_fours | 1 | 2 |
| 1.2 | bowler_runs | 11 | 1 |
| 1.2 | this_over_tokens | [".", ".", "4", "1"] | [".", "1"] |
| 1.3 | striker_balls | 4 | 6 |
| 1.3 | striker_fours | 1 | 2 |
| 1.3 | bowler_runs | 11 | 1 |
| 1.3 | this_over_tokens | ["?", "?", "."] | [".", "1", "."] |
| 1.4 | striker_balls | 5 | 7 |
| 1.4 | striker_fours | 1 | 2 |
| 1.4 | bowler_runs | 11 | 1 |
| 1.4 | this_over_tokens | ["?", "?", ".", "."] | [".", "1", ".", "."] |
| 1.5 | balls_total | 11 | 10 |
| 1.5 | striker_name | Rahul | Porel |
| 1.5 | striker_runs | 2 | 9 |
| 1.5 | striker_balls | 3 | 7 |
| 1.5 | striker_fours | 0 | 2 |
| 1.5 | non_striker_name | Porel | Rahul |
| 1.5 | non_striker_runs | 10 | 2 |
| 1.5 | non_striker_balls | 6 | 3 |
| 1.5 | non_striker_fours | 1 | 0 |
| 1.5 | bowler_runs | 12 | 2 |
| 1.5 | this_over_tokens | ["?", "?", ".", ".", "1"] | [".", "1", ".", ".", "Wd"] |
| 2.1 | striker_name | Rahul | Porel |
| 2.1 | striker_runs | 2 | 9 |
| 2.1 | striker_balls | 4 | 9 |
| 2.1 | striker_fours | 0 | 2 |
| 2.1 | non_striker_name | Porel | Rahul |
| 2.1 | non_striker_runs | 11 | 3 |
| 2.1 | non_striker_balls | 7 | 4 |
| 2.1 | non_striker_fours | 1 | 0 |
| 2.1 | bowler_runs | 0 | 1 |
| 2.2 | striker_name | Porel | Rahul |
| 2.2 | striker_runs | 11 | 3 |
| 2.2 | striker_balls | 7 | 4 |
| 2.2 | non_striker_name | Rahul | Porel |
| 2.2 | non_striker_runs | 3 | 10 |
| 2.2 | non_striker_balls | 5 | 10 |
| 2.2 | non_striker_fours | 0 | 2 |
| 2.2 | bowler_runs | 0 | 2 |
| 2.3 | striker_name | Porel | Rahul |
| 2.3 | striker_runs | 11 | 3 |
| 2.3 | striker_balls | 8 | 5 |
| 2.3 | non_striker_name | Rahul | Porel |
| 2.3 | non_striker_runs | 3 | 10 |
| 2.3 | non_striker_balls | 5 | 10 |
| 2.3 | non_striker_fours | 0 | 2 |
| 2.3 | bowler_runs | 0 | 2 |
| 2.4 | striker_name | Porel | Rahul |
| 2.4 | striker_runs | 11 | 9 |
| 2.4 | striker_balls | 8 | 6 |
| 2.4 | striker_sixes | 0 | 1 |
| 2.4 | non_striker_name | Rahul | Porel |
| 2.4 | non_striker_runs | 9 | 10 |
| 2.4 | non_striker_balls | 6 | 10 |
| 2.4 | non_striker_fours | 0 | 2 |
| 2.4 | non_striker_sixes | 1 | 0 |
| 2.4 | bowler_runs | 7 | 8 |
| 2.5 | score | 22 | 24 |
| 2.5 | striker_name | — | Rahul |
| 2.5 | striker_runs | 0 | 13 |
| 2.5 | striker_balls | 0 | 7 |
| 2.5 | striker_fours | 0 | 1 |
| 2.5 | striker_sixes | 0 | 1 |
| 2.5 | non_striker_name | — | Porel |
| 2.5 | non_striker_runs | 0 | 10 |
| 2.5 | non_striker_balls | 0 | 10 |
| 2.5 | non_striker_fours | 0 | 2 |
| 2.5 | bowler_runs | 36 | 12 |
| 2.5 | bowler_wickets | 1 | 0 |
| 2.5 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | ["1", "1", ".", "6", "4"] |
| 2.6 | striker_runs | 17 | 10 |
| 2.6 | striker_fours | 1 | 2 |
| 2.6 | non_striker_runs | 9 | 15 |
| 2.6 | non_striker_balls | 6 | 8 |
| 2.6 | non_striker_fours | 0 | 1 |
| 2.6 | bowler_runs | 6 | 14 |
| 3.1 | striker_runs | 21 | 14 |
| 3.1 | striker_fours | 2 | 3 |
| 3.1 | non_striker_runs | 9 | 15 |
| 3.1 | non_striker_balls | 6 | 8 |
| 3.1 | non_striker_fours | 0 | 1 |
| 3.1 | bowler_runs | 10 | 4 |
| 3.1 | this_over_tokens | ["1", "1", ".", "6", "4"] | ["4"] |
| 3.3 | score | 30 | 34 |
| 3.3 | striker_name | — | Porel |
| 3.3 | striker_runs | 0 | 18 |
| 3.3 | striker_balls | 0 | 13 |
| 3.3 | striker_fours | 0 | 4 |
| 3.3 | non_striker_name | — | Rahul |
| 3.3 | non_striker_runs | 0 | 15 |
| 3.3 | non_striker_balls | 0 | 8 |
| 3.3 | non_striker_fours | 0 | 1 |
| 3.3 | non_striker_sixes | 0 | 1 |
| 3.3 | bowler_runs | 36 | 8 |
| 3.3 | bowler_wickets | 1 | 0 |
| 3.3 | this_over_tokens | ["?", "?", "."] | ["4", "4", "."] |
| 3.4 | striker_runs | 9 | 15 |
| 3.4 | striker_balls | 6 | 8 |
| 3.4 | striker_fours | 0 | 1 |
| 3.4 | non_striker_runs | 28 | 21 |
| 3.4 | non_striker_fours | 2 | 4 |
| 3.4 | non_striker_sixes | 2 | 0 |
| 3.4 | bowler_runs | 17 | 11 |
| 3.4 | this_over_tokens | ["1", "1", ".", "6", "4", "1"] | ["4", "4", ".", "3"] |
| 4.1 | striker_name | Rahul | Porel |
| 4.1 | striker_runs | 10 | 22 |
| 4.1 | striker_balls | 7 | 16 |
| 4.1 | striker_fours | 0 | 4 |
| 4.1 | non_striker_name | Porel | Rahul |
| 4.1 | non_striker_runs | 29 | 16 |
| 4.1 | non_striker_balls | 16 | 9 |
| 4.1 | non_striker_fours | 2 | 1 |
| 4.1 | non_striker_sixes | 2 | 1 |
| 4.1 | bowler_runs | 19 | 2 |
| 4.2 | balls_total | 26 | 25 |
| 4.2 | striker_runs | 30 | 22 |
| 4.2 | striker_balls | 17 | 16 |
| 4.2 | striker_fours | 2 | 4 |
| 4.2 | non_striker_runs | 10 | 16 |
| 4.2 | non_striker_balls | 7 | 9 |
| 4.2 | non_striker_fours | 0 | 1 |
| 4.2 | bowler_runs | 20 | 3 |
| 4.2 | this_over_tokens | [".", "1"] | [".", "Wd"] |
| 4.3 | striker_runs | 30 | 0 |
| 4.3 | striker_balls | 17 | 0 |
| 4.3 | non_striker_runs | 10 | 16 |
| 4.3 | non_striker_balls | 7 | 9 |
| 4.3 | non_striker_fours | 0 | 1 |
| 4.3 | bowler_runs | 20 | 3 |
| 4.4 | striker_runs | 10 | 16 |
| 4.4 | striker_balls | 7 | 9 |
| 4.4 | striker_fours | 0 | 1 |
| 4.4 | non_striker_name | Porel | Parakh |
| 4.4 | non_striker_runs | 30 | 1 |
| 4.4 | non_striker_balls | 17 | 1 |
| 4.4 | non_striker_fours | 2 | 0 |
| 4.4 | non_striker_sixes | 2 | 0 |
| 4.4 | bowler_runs | 21 | 4 |
| 4.5 | striker_runs | 10 | 16 |
| 4.5 | striker_balls | 8 | 10 |
| 4.5 | striker_fours | 0 | 1 |
| 4.5 | non_striker_name | Porel | Parakh |
| 4.5 | non_striker_runs | 30 | 1 |
| 4.5 | non_striker_balls | 17 | 1 |
| 4.5 | non_striker_fours | 2 | 0 |
| 4.5 | non_striker_sixes | 2 | 0 |
| 4.5 | bowler_runs | 21 | 4 |
| 5.3 | striker_runs | 17 | 7 |
| 5.3 | striker_balls | 10 | 3 |
| 5.3 | non_striker_name | Porel | Rahul |
| 5.3 | non_striker_runs | 30 | 18 |
| 5.3 | non_striker_balls | 17 | 12 |
| 5.3 | non_striker_fours | 2 | 1 |
| 5.3 | non_striker_sixes | 2 | 1 |
| 5.3 | this_over_tokens | ["?", "?", "6"] | ["1", ".", "6"] |
| 5.4 | striker_runs | 17 | 7 |
| 5.4 | striker_balls | 11 | 4 |
| 5.4 | non_striker_name | Porel | Rahul |
| 5.4 | non_striker_runs | 30 | 18 |
| 5.4 | non_striker_balls | 17 | 12 |
| 5.4 | non_striker_fours | 2 | 1 |
| 5.4 | non_striker_sixes | 2 | 1 |
| 5.4 | this_over_tokens | ["?", "?", "6", "."] | ["1", ".", "6", "."] |
| 5.5 | striker_runs | 17 | 7 |
| 5.5 | striker_balls | 12 | 5 |
| 5.5 | non_striker_name | Porel | Rahul |
| 5.5 | non_striker_runs | 30 | 18 |
| 5.5 | non_striker_balls | 17 | 12 |
| 5.5 | non_striker_fours | 2 | 1 |
| 5.5 | non_striker_sixes | 2 | 1 |
| 5.5 | this_over_tokens | ["?", "?", "6", ".", "."] | ["1", ".", "6", ".", "."] |
| 5.6 | score | 55 | 53 |
| 5.6 | striker_runs | 0 | 18 |
| 5.6 | striker_balls | 0 | 12 |
| 5.6 | striker_fours | 0 | 1 |
| 5.6 | striker_sixes | 0 | 1 |
| 5.6 | non_striker_name | — | Parakh |
| 5.6 | non_striker_runs | 0 | 11 |
| 5.6 | non_striker_balls | 0 | 6 |
| 5.6 | non_striker_fours | 0 | 1 |
| 5.6 | non_striker_sixes | 0 | 1 |
| 5.6 | bowler_runs | 36 | 11 |
| 5.6 | bowler_wickets | 1 | 0 |
| 5.6 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | ["1", ".", "6", ".", ".", "4"] |
| 6.4 | striker_runs | 22 | 19 |
| 6.4 | striker_balls | 15 | 14 |
| 6.4 | non_striker_name | Porel | Parakh |
| 6.4 | non_striker_runs | 30 | 12 |
| 6.4 | non_striker_balls | 17 | 8 |
| 6.4 | non_striker_fours | 2 | 1 |
| 6.4 | non_striker_sixes | 2 | 1 |
| 6.4 | bowler_runs | 1 | 2 |
| 6.4 | this_over_tokens | ["?", "?", "6", ".", ".", "4"] | [".", "1", ".", "1"] |
| 6.5 | striker_runs | 30 | 12 |
| 6.5 | striker_balls | 17 | 8 |
| 6.5 | non_striker_runs | 23 | 20 |
| 6.5 | non_striker_balls | 16 | 15 |
| 6.5 | non_striker_sixes | 2 | 1 |
| 6.5 | bowler_runs | 2 | 3 |
| 6.5 | this_over_tokens | ["?", "?", "?", "?", "1"] | [".", "1", ".", "1", "1"] |
| 7.1 | striker_runs | 30 | 20 |
| 7.1 | striker_balls | 17 | 15 |
| 7.1 | non_striker_name | Rahul | Parakh |
| 7.1 | non_striker_runs | 24 | 14 |
| 7.1 | non_striker_balls | 17 | 10 |
| 7.1 | non_striker_sixes | 2 | 1 |
| 7.1 | bowler_runs | 14 | 12 |
| 7.1 | this_over_tokens | ["?", "?", "?", "?", "1"] | ["1"] |
| 7.2 | score | 66 | 64 |
| 7.2 | striker_runs | 30 | 26 |
| 7.2 | striker_balls | 17 | 16 |
| 7.2 | striker_fours | 2 | 1 |
| 7.2 | non_striker_name | Rahul | Parakh |
| 7.2 | non_striker_runs | 24 | 14 |
| 7.2 | non_striker_balls | 17 | 10 |
| 7.2 | non_striker_sixes | 2 | 1 |
| 7.2 | bowler_runs | 22 | 18 |
| 7.2 | this_over_tokens | ["?", "?", "?", "?", "1", "8"] | ["1", "6"] |
| 7.3 | non_striker_name | Rahul | Parakh |
| 7.3 | non_striker_runs | 24 | 14 |
| 7.3 | non_striker_balls | 17 | 10 |
| 7.3 | non_striker_sixes | 2 | 1 |
| 7.3 | bowler_runs | 24 | 22 |
| 7.3 | this_over_tokens | ["?", "?", "?", "?", "1", "8", "2"] | ["1", "6", "4"] |
| 7.5 | striker_runs | 30 | 31 |
| 7.5 | striker_balls | 17 | 18 |
| 7.5 | non_striker_name | Rahul | Parakh |
| 7.5 | non_striker_runs | 25 | 15 |
| 7.5 | non_striker_balls | 18 | 11 |
| 7.5 | non_striker_sixes | 2 | 1 |
| 7.5 | bowler_runs | 26 | 24 |
| 7.5 | this_over_tokens | ["?", "?", "?", "?", "1", "8", "2"] | ["1", "6", "4", "1", "1"] |
| 7.6 | striker_runs | 30 | 15 |
| 7.6 | striker_balls | 17 | 11 |
| 7.6 | non_striker_runs | 25 | 31 |
| 7.6 | non_striker_fours | 1 | 2 |
| 7.6 | bowler_runs | 26 | 24 |
| 7.6 | this_over_tokens | ["?", "?", "?", "?", "1", "8", "2", "."] | ["1", "6", "4", "1", "1", "."] |
| 8.5 | striker_runs | 25 | 31 |
| 8.5 | striker_fours | 1 | 2 |
| 8.5 | non_striker_name | Porel | Parakh |
| 8.5 | non_striker_runs | 30 | 24 |
| 8.5 | non_striker_balls | 17 | 16 |
| 8.5 | non_striker_fours | 2 | 3 |
| 8.5 | non_striker_sixes | 2 | 1 |
| 8.5 | bowler_runs | 11 | 13 |
| 8.5 | this_over_tokens | ["?", "?", "?", "?", "1"] | [".", "4", ".", "4", "1"] |
| 9.3 | striker_runs | 32 | 0 |
| 9.3 | striker_balls | 21 | 0 |
| 9.3 | non_striker_name | Porel | Rahul |
| 9.3 | non_striker_runs | 30 | 39 |
| 9.3 | non_striker_balls | 17 | 22 |
| 9.3 | non_striker_sixes | 2 | 3 |
| 9.3 | bowler_runs | 34 | 31 |
| 9.6 | striker_runs | 32 | 1 |
| 9.6 | striker_balls | 21 | 3 |
| 9.6 | striker_fours | 1 | 0 |
| 9.6 | striker_sixes | 3 | 0 |
| 9.6 | non_striker_name | Porel | Rahul |
| 9.6 | non_striker_runs | 30 | 39 |
| 9.6 | non_striker_balls | 17 | 22 |
| 9.6 | non_striker_sixes | 2 | 3 |
| 9.6 | bowler_runs | 36 | 32 |
| 10.2 | striker_runs | 32 | 43 |
| 10.2 | striker_balls | 21 | 23 |
| 10.2 | striker_fours | 1 | 3 |
| 10.2 | non_striker_name | Porel | Patel |
| 10.2 | non_striker_runs | 30 | 2 |
| 10.2 | non_striker_balls | 17 | 4 |
| 10.2 | non_striker_fours | 2 | 0 |
| 10.2 | non_striker_sixes | 2 | 0 |
| 10.2 | bowler_runs | 26 | 18 |
| 10.2 | this_over_tokens | ["?", "?", "?", "?", "1", ".", "4"] | ["1", "4"] |
| 10.3 | striker_runs | 32 | 49 |
| 10.3 | striker_balls | 21 | 24 |
| 10.3 | striker_fours | 1 | 3 |
| 10.3 | striker_sixes | 3 | 4 |
| 10.3 | non_striker_name | Porel | Patel |
| 10.3 | non_striker_runs | 30 | 2 |
| 10.3 | non_striker_balls | 17 | 4 |
| 10.3 | non_striker_fours | 2 | 0 |
| 10.3 | non_striker_sixes | 2 | 0 |
| 10.3 | bowler_runs | 32 | 24 |
| 10.3 | this_over_tokens | ["?", "?", "?", "?", "1", ".", "4", "6"] | ["1", "4", "6"] |
| 10.4 | striker_runs | 30 | 2 |
| 10.4 | striker_balls | 17 | 4 |
| 10.4 | non_striker_runs | 32 | 50 |
| 10.4 | non_striker_balls | 21 | 25 |
| 10.4 | non_striker_fours | 1 | 3 |
| 10.4 | non_striker_sixes | 3 | 4 |
| 10.4 | bowler_runs | 33 | 25 |
| 10.4 | this_over_tokens | ["?", "?", "?", "?", "1", ".", "4", "6", "1"] | ["1", "4", "6", "1"] |
| 10.5 | striker_runs | 30 | 6 |
| 10.5 | striker_balls | 17 | 5 |
| 10.5 | non_striker_runs | 32 | 50 |
| 10.5 | non_striker_balls | 21 | 25 |
| 10.5 | non_striker_fours | 1 | 3 |
| 10.5 | non_striker_sixes | 3 | 4 |
| 10.5 | bowler_runs | 37 | 29 |
| 10.5 | this_over_tokens | ["?", "?", "?", "?", "1", ".", "4", "6", "1", "4"] | ["1", "4", "6", "1", "4"] |
| 10.6 | striker_runs | 30 | 50 |
| 10.6 | striker_balls | 17 | 25 |
| 10.6 | striker_fours | 2 | 3 |
| 10.6 | striker_sixes | 2 | 4 |
| 10.6 | non_striker_name | Rahul | Patel |
| 10.6 | non_striker_runs | 32 | 10 |
| 10.6 | non_striker_balls | 21 | 6 |
| 10.6 | non_striker_fours | 1 | 2 |
| 10.6 | non_striker_sixes | 3 | 0 |
| 10.6 | bowler_runs | 41 | 33 |
| 10.6 | this_over_tokens | ["?", "?", "?", "?", "1", ".", "4", "6", "1", "4", "4"] | ["1", "4", "6", "1", "4", "4"] |
| 11.3 | striker_runs | 32 | 12 |
| 11.3 | striker_balls | 21 | 8 |
| 11.3 | striker_fours | 1 | 2 |
| 11.3 | non_striker_name | Porel | Rahul |
| 11.3 | non_striker_runs | 30 | 51 |
| 11.3 | non_striker_balls | 17 | 26 |
| 11.3 | non_striker_fours | 2 | 3 |
| 11.3 | non_striker_sixes | 2 | 4 |
| 11.3 | bowler_runs | 44 | 35 |
| 11.3 | this_over_tokens | ["?", "?", "?", "?", "1", ".", "4", "6", "1", "4", "4"] | ["1", "2", "."] |
| 11.4 | striker_runs | 30 | 51 |
| 11.4 | striker_balls | 17 | 26 |
| 11.4 | striker_fours | 2 | 3 |
| 11.4 | striker_sixes | 2 | 4 |
| 11.4 | non_striker_name | Rahul | Patel |
| 11.4 | non_striker_runs | 32 | 13 |
| 11.4 | non_striker_balls | 21 | 9 |
| 11.4 | non_striker_fours | 1 | 2 |
| 11.4 | non_striker_sixes | 3 | 0 |
| 11.4 | bowler_runs | 45 | 36 |
| 11.4 | this_over_tokens | ["?", "?", "?", "1"] | ["1", "2", ".", "1"] |
| 11.5 | striker_runs | 32 | 13 |
| 11.5 | striker_balls | 21 | 9 |
| 11.5 | striker_fours | 1 | 2 |
| 11.5 | non_striker_name | Porel | Rahul |
| 11.5 | non_striker_runs | 30 | 52 |
| 11.5 | non_striker_balls | 17 | 27 |
| 11.5 | non_striker_fours | 2 | 3 |
| 11.5 | non_striker_sixes | 2 | 4 |
| 11.5 | bowler_runs | 46 | 37 |
| 11.5 | this_over_tokens | ["?", "?", "?", "1", "1"] | ["1", "2", ".", "1", "1"] |
| 11.6 | striker_runs | 32 | 14 |
| 11.6 | striker_balls | 21 | 10 |
| 11.6 | striker_fours | 1 | 2 |
| 11.6 | non_striker_name | Porel | Rahul |
| 11.6 | non_striker_runs | 30 | 52 |
| 11.6 | non_striker_balls | 17 | 27 |
| 11.6 | non_striker_fours | 2 | 3 |
| 11.6 | non_striker_sixes | 2 | 4 |
| 11.6 | bowler_runs | 0 | 38 |
| 11.6 | this_over_tokens | ["?", "?", "?", "1", "1", "1"] | ["1", "2", ".", "1", "1", "1"] |
| 12.1 | striker_runs | 32 | 52 |
| 12.1 | striker_balls | 21 | 27 |
| 12.1 | striker_fours | 1 | 3 |
| 12.1 | striker_sixes | 3 | 4 |
| 12.1 | non_striker_name | Porel | Patel |
| 12.1 | non_striker_runs | 30 | 15 |
| 12.1 | non_striker_balls | 17 | 11 |
| 12.1 | non_striker_sixes | 2 | 0 |
| 12.1 | bowler_runs | 0 | 11 |
| 12.1 | this_over_tokens | ["2"] | ["1"] |
| 12.4 | non_striker_name | Porel | Patel |
| 12.4 | non_striker_runs | 30 | 15 |
| 12.4 | non_striker_balls | 17 | 11 |
| 12.4 | non_striker_sixes | 2 | 0 |
| 12.4 | bowler_runs | 0 | 21 |
| 12.5 | striker_runs | 0 | 15 |
| 12.5 | striker_balls | 0 | 11 |
| 12.5 | striker_fours | 0 | 2 |
| 12.5 | non_striker_name | Porel | Miller |
| 12.5 | non_striker_runs | 30 | 1 |
| 12.5 | non_striker_balls | 17 | 1 |
| 12.5 | non_striker_fours | 2 | 0 |
| 12.5 | non_striker_sixes | 2 | 0 |
| 12.5 | bowler_runs | 15 | 22 |
| 12.6 | striker_runs | 0 | 16 |
| 12.6 | striker_balls | 0 | 12 |
| 12.6 | striker_fours | 0 | 2 |
| 12.6 | non_striker_name | Porel | Miller |
| 12.6 | non_striker_runs | 30 | 1 |
| 12.6 | non_striker_balls | 17 | 1 |
| 12.6 | non_striker_fours | 2 | 0 |
| 12.6 | non_striker_sixes | 2 | 0 |
| 12.6 | bowler_runs | 16 | 23 |
| 13.1 | striker_runs | 0 | 16 |
| 13.1 | striker_balls | 0 | 13 |
| 13.1 | striker_fours | 0 | 2 |
| 13.1 | non_striker_name | Porel | Miller |
| 13.1 | non_striker_runs | 30 | 1 |
| 13.1 | non_striker_balls | 17 | 1 |
| 13.1 | non_striker_fours | 2 | 0 |
| 13.1 | non_striker_sixes | 2 | 0 |
| 13.1 | bowler_runs | 17 | 14 |
| 13.1 | this_over_tokens | ["1"] | ["1lb"] |
| 13.3 | striker_runs | 0 | 2 |
| 13.3 | striker_balls | 0 | 2 |
| 13.3 | non_striker_name | Porel | Patel |
| 13.3 | non_striker_runs | 30 | 17 |
| 13.3 | non_striker_balls | 17 | 14 |
| 13.3 | non_striker_sixes | 2 | 0 |
| 13.3 | bowler_runs | 19 | 16 |
| 13.4 | striker_runs | 0 | 2 |
| 13.4 | striker_balls | 0 | 3 |
| 13.4 | non_striker_name | Porel | Patel |
| 13.4 | non_striker_runs | 30 | 17 |
| 13.4 | non_striker_balls | 17 | 14 |
| 13.4 | non_striker_sixes | 2 | 0 |
| 13.4 | bowler_runs | 19 | 16 |
| 13.4 | this_over_tokens | ["1", "?", "?", "."] | ["1lb", "1", "1", "."] |
| 14.2 | striker_runs | 0 | 21 |
| 14.2 | striker_balls | 0 | 16 |
| 14.2 | striker_fours | 0 | 3 |
| 14.2 | non_striker_name | Porel | Miller |
| 14.2 | non_striker_runs | 30 | 4 |
| 14.2 | non_striker_balls | 17 | 5 |
| 14.2 | non_striker_fours | 2 | 0 |
| 14.2 | non_striker_sixes | 2 | 0 |
| 14.2 | bowler_runs | 17 | 15 |
| 14.2 | this_over_tokens | ["1", "?", "?", "."] | ["1", "."] |
| 14.3 | striker_runs | 0 | 4 |
| 14.3 | striker_balls | 0 | 5 |
| 14.3 | non_striker_name | Porel | Patel |
| 14.3 | non_striker_runs | 30 | 22 |
| 14.3 | non_striker_fours | 2 | 3 |
| 14.3 | non_striker_sixes | 2 | 0 |
| 14.3 | bowler_runs | 18 | 16 |
| 14.3 | this_over_tokens | ["1", "?", "?", ".", "1"] | ["1", ".", "1"] |
| 14.4 | striker_runs | 0 | 4 |
| 14.4 | striker_balls | 0 | 6 |
| 14.4 | non_striker_name | Porel | Patel |
| 14.4 | non_striker_runs | 30 | 22 |
| 14.4 | non_striker_fours | 2 | 3 |
| 14.4 | non_striker_sixes | 2 | 0 |
| 14.4 | bowler_runs | 19 | 16 |
| 14.4 | this_over_tokens | ["1", "?", "?", ".", "1"] | ["1", ".", "1", "1lb"] |
| 14.5 | striker_runs | 0 | 4 |
| 14.5 | striker_balls | 0 | 6 |
| 14.5 | non_striker_name | Porel | Patel |
| 14.5 | non_striker_runs | 30 | 23 |
| 14.5 | non_striker_balls | 17 | 18 |
| 14.5 | non_striker_fours | 2 | 3 |
| 14.5 | non_striker_sixes | 2 | 0 |
| 14.5 | bowler_runs | 20 | 17 |
| 14.5 | this_over_tokens | ["1", "?", "?", ".", "1"] | ["1", ".", "1", "1lb", "1"] |
| 14.6 | striker_runs | 0 | 5 |
| 14.6 | striker_balls | 0 | 7 |
| 14.6 | non_striker_name | Porel | Patel |
| 14.6 | non_striker_runs | 30 | 23 |
| 14.6 | non_striker_balls | 17 | 18 |
| 14.6 | non_striker_fours | 2 | 3 |
| 14.6 | non_striker_sixes | 2 | 0 |
| 14.6 | bowler_runs | 21 | 18 |
| 14.6 | this_over_tokens | ["1", "?", "?", ".", "1", "1"] | ["1", ".", "1", "1lb", "1", "1"] |
| 15.1 | striker_runs | 0 | 23 |
| 15.1 | striker_balls | 0 | 18 |
| 15.1 | striker_fours | 0 | 3 |
| 15.1 | non_striker_name | Porel | Miller |
| 15.1 | non_striker_runs | 30 | 6 |
| 15.1 | non_striker_balls | 17 | 8 |
| 15.1 | non_striker_fours | 2 | 0 |
| 15.1 | non_striker_sixes | 2 | 0 |
| 15.1 | bowler_runs | 48 | 34 |
| 15.2 | striker_runs | 0 | 6 |
| 15.2 | striker_balls | 0 | 8 |
| 15.2 | non_striker_name | Porel | Patel |
| 15.2 | non_striker_runs | 30 | 24 |
| 15.2 | non_striker_balls | 17 | 19 |
| 15.2 | non_striker_fours | 2 | 3 |
| 15.2 | non_striker_sixes | 2 | 0 |
| 15.2 | bowler_runs | 49 | 35 |
| 15.3 | striker_runs | 0 | 12 |
| 15.3 | striker_balls | 0 | 9 |
| 15.3 | striker_sixes | 0 | 1 |
| 15.3 | non_striker_name | Porel | Patel |
| 15.3 | non_striker_runs | 30 | 24 |
| 15.3 | non_striker_balls | 17 | 19 |
| 15.3 | non_striker_fours | 2 | 3 |
| 15.3 | non_striker_sixes | 2 | 0 |
| 15.3 | bowler_runs | 55 | 41 |
| 15.4 | striker_runs | 0 | 12 |
| 15.4 | striker_balls | 0 | 10 |
| 15.4 | striker_sixes | 0 | 1 |
| 15.4 | non_striker_name | Porel | Patel |
| 15.4 | non_striker_runs | 30 | 24 |
| 15.4 | non_striker_balls | 17 | 19 |
| 15.4 | non_striker_fours | 2 | 3 |
| 15.4 | non_striker_sixes | 2 | 0 |
| 15.4 | bowler_runs | 55 | 41 |
| 15.6 | striker_runs | 0 | 25 |
| 15.6 | striker_balls | 0 | 20 |
| 15.6 | striker_fours | 0 | 3 |
| 15.6 | non_striker_name | Porel | Miller |
| 15.6 | non_striker_runs | 30 | 13 |
| 15.6 | non_striker_balls | 17 | 11 |
| 15.6 | non_striker_fours | 2 | 0 |
| 15.6 | non_striker_sixes | 2 | 1 |
| 15.6 | bowler_runs | 23 | 43 |
| 16.3 | striker_runs | 0 | 37 |
| 16.3 | striker_balls | 0 | 23 |
| 16.3 | striker_fours | 0 | 3 |
| 16.3 | striker_sixes | 0 | 2 |
| 16.3 | non_striker_name | Porel | Miller |
| 16.3 | non_striker_runs | 30 | 13 |
| 16.3 | non_striker_balls | 17 | 11 |
| 16.3 | non_striker_fours | 2 | 0 |
| 16.3 | non_striker_sixes | 2 | 1 |
| 16.3 | bowler_runs | 31 | 30 |
| 16.3 | this_over_tokens | ["1", "1", "6", "."] | ["6", ".", "6"] |
| 16.5 | non_striker_name | Porel | Miller |
| 16.5 | non_striker_runs | 30 | 13 |
| 16.5 | non_striker_balls | 17 | 11 |
| 16.5 | non_striker_fours | 2 | 0 |
| 16.5 | non_striker_sixes | 2 | 1 |
| 16.5 | bowler_runs | 31 | 34 |
| 16.6 | striker_runs | 0 | 1 |
| 16.6 | striker_balls | 0 | 1 |
| 16.6 | non_striker_name | Porel | Miller |
| 16.6 | non_striker_runs | 30 | 13 |
| 16.6 | non_striker_balls | 17 | 11 |
| 16.6 | non_striker_fours | 2 | 0 |
| 16.6 | non_striker_sixes | 2 | 1 |
| 16.6 | bowler_runs | 32 | 35 |
| 17.1 | striker_runs | 0 | 13 |
| 17.1 | striker_balls | 0 | 11 |
| 17.1 | striker_sixes | 0 | 1 |
| 17.1 | non_striker_name | Porel | Sharma |
| 17.1 | non_striker_runs | 30 | 2 |
| 17.1 | non_striker_balls | 17 | 2 |
| 17.1 | non_striker_fours | 2 | 0 |
| 17.1 | non_striker_sixes | 2 | 0 |
| 17.1 | bowler_runs | 33 | 6 |
| 17.3 | wickets | 6 | 4 |
| 17.3 | striker_runs | 0 | 2 |
| 17.3 | striker_balls | 0 | 2 |
| 17.3 | non_striker_name | Porel | Miller |
| 17.3 | non_striker_runs | 30 | 14 |
| 17.3 | non_striker_balls | 17 | 13 |
| 17.3 | non_striker_fours | 2 | 0 |
| 17.3 | non_striker_sixes | 2 | 1 |
| 17.3 | bowler_runs | 34 | 7 |
| 17.4 | wickets | 6 | 4 |
| 17.4 | striker_runs | 0 | 14 |
| 17.4 | striker_balls | 0 | 13 |
| 17.4 | striker_sixes | 0 | 1 |
| 17.4 | non_striker_name | Porel | Sharma |
| 17.4 | non_striker_runs | 30 | 3 |
| 17.4 | non_striker_balls | 17 | 3 |
| 17.4 | non_striker_fours | 2 | 0 |
| 17.4 | non_striker_sixes | 2 | 0 |
| 17.4 | bowler_runs | 35 | 8 |
| 17.4 | this_over_tokens | ["1", "?", "?", "1"] | ["1", ".", "1", "1"] |
| 17.5 | wickets | 6 | 4 |
| 17.5 | striker_runs | 0 | 3 |
| 17.5 | striker_balls | 0 | 3 |
| 17.5 | non_striker_name | Porel | Miller |
| 17.5 | non_striker_runs | 30 | 15 |
| 17.5 | non_striker_balls | 17 | 14 |
| 17.5 | non_striker_fours | 2 | 0 |
| 17.5 | non_striker_sixes | 2 | 1 |
| 17.5 | bowler_runs | 36 | 9 |
| 17.5 | this_over_tokens | ["1", "?", "?", "1", "1"] | ["1", ".", "1", "1", "1"] |
| 17.6 | wickets | 6 | 4 |
| 17.6 | striker_runs | 0 | 15 |
| 17.6 | striker_balls | 0 | 14 |
| 17.6 | striker_sixes | 0 | 1 |
| 17.6 | non_striker_name | Porel | Sharma |
| 17.6 | non_striker_runs | 30 | 7 |
| 17.6 | non_striker_balls | 17 | 4 |
| 17.6 | non_striker_fours | 2 | 1 |
| 17.6 | non_striker_sixes | 2 | 0 |
| 17.6 | bowler_runs | 59 | 13 |
| 17.6 | this_over_tokens | ["1", "?", "?", "1", "1", "4"] | ["1", ".", "1", "1", "1", "4"] |
| 18.1 | wickets | 6 | 4 |
| 18.1 | striker_runs | 0 | 7 |
| 18.1 | striker_balls | 0 | 4 |
| 18.1 | striker_fours | 0 | 1 |
| 18.1 | non_striker_name | Porel | Miller |
| 18.1 | non_striker_runs | 30 | 16 |
| 18.1 | non_striker_balls | 17 | 15 |
| 18.1 | non_striker_fours | 2 | 0 |
| 18.1 | non_striker_sixes | 2 | 1 |
| 18.1 | bowler_runs | 60 | 44 |

## 5. Missing / phantom balls

- Missing-in-pipeline (57): 0.1, 0.4, 1.5#1, 1.6, 3.2, 3.5, 3.6, 4.2#1, 4.6, 5.1, 5.2, 6.1, 6.2, 6.3, 6.6, 7.4, 8.1, 8.2, 8.3, 8.4, 8.6, 9.1, 9.2, 9.4, 9.5, 10.1, 11.1, 11.2, 12.2, 12.2#1, 12.3, 12.3#1, 13.2, 13.5, 13.6, 14.1, 15.5, 16.1, 16.2, 16.4, 16.4#1, 16.4#2, 17.2, 18.2, 18.3, 18.4, 18.4#1, 18.5, 18.6, 19.1, 19.2, 19.3, 19.4, 19.4#1, 19.4#2, 19.5, 19.6
- Phantom-in-pipeline (13): 0.6#1, 1.2#1, 1.3#1, 1.4#1, 2.1#1, 2.2#1, 2.3#1, 2.4#1, 2.6#1, 2.6#2, 3.4#1, 10.2#1, 11.3#1
