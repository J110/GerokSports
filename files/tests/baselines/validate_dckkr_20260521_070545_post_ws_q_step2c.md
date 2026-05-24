# Differential diff report

- Pipeline: `/tmp/validate_dckkr_20260521_070545_snapshots.jsonl`
- Ground truth: `files/tests/fixtures/dckkr_ground_truth_ui_snapshots.jsonl`
- Matched balls: 67 | missing-in-pipeline: 55 | phantom-in-pipeline: 3 | total divergences: 551

## 1. Per-surface incident counts

| Surface | Count | First example (over.ball) |
|---|---|---|
| G-pipeline-lag | 55 | 1.3 |
| F-A-commit-lag | 50 | 0.6 |
| Boundary-counter-double-increment | 41 | 5.2 |
| E3-wicket-frame-misalign | 40 | 5.1 |
| D-post-FoW-striker | 36 | 5.2 |
| Extras-counter-drop | 36 | 10.2 |
| F-B-ad-occlusion | 21 | 0.6 |
| Bowler-W-credit-failure | 13 | 9.5 |
| Recent-overs-drop | 12 | 1.1 |
| Silent-wicket-absorption | 2 | 9.5 |
| E2-phantom-runs | 2 | 6.4 |
| Compound-with-wicket-token | 2 | 10.2 |
| C21b-symbol-revert | 1 | 9.5 |

## 2. Per-ball divergences

| over.ball | field | pipeline | ground-truth | surface |
|---|---|---|---|---|
| 0.1 | non_striker_name | Rahul | — | _unclassified_ |
| 0.2 | non_striker_name | Rahul | — | _unclassified_ |
| 0.3 | striker_name | Rahul | — | _unclassified_ |
| 0.6 | bowler_name | — | Roy | F-B-ad-occlusion |
| 0.6 | bowler_overs | — | 1.0 | F-A-commit-lag |
| 0.6 | bowler_runs | 0 | 7 | _unclassified_ |
| 1.1 | bowler_name | — | Arora | F-B-ad-occlusion |
| 1.1 | bowler_overs | — | 0.1 | F-A-commit-lag |
| 1.1 | recent_over_n_minus_1 | [] | [".", "4", "1", ".", "1", "1"] | Recent-overs-drop |
| 1.5 | this_over_tokens | [".", "1", "?", "?", "1"] | [".", "1", "1", "6", "1"] | _unclassified_ |
| 1.6 | bowler_name | Roy | Arora | F-B-ad-occlusion |
| 1.6 | bowler_overs | 1.1 | 1.0 | F-A-commit-lag |
| 1.6 | bowler_runs | 8 | 10 | _unclassified_ |
| 1.6 | this_over_tokens | [".", "1", "?", "?", "1", "1"] | [".", "1", "1", "6", "1", "1"] | _unclassified_ |
| 2.1 | bowler_overs | 1.2 | 1.1 | F-A-commit-lag |
| 2.1 | bowler_runs | 8 | 7 | _unclassified_ |
| 2.1 | recent_over_n_minus_1 | [] | [".", "1", "1", "6", "1", "1"] | Recent-overs-drop |
| 2.2 | bowler_overs | 1.3 | 1.2 | F-A-commit-lag |
| 2.2 | bowler_runs | 12 | 11 | _unclassified_ |
| 2.3 | bowler_overs | 1.4 | 1.3 | F-A-commit-lag |
| 2.3 | bowler_runs | 13 | 12 | _unclassified_ |
| 2.4 | bowler_overs | 1.5 | 1.4 | F-A-commit-lag |
| 2.4 | bowler_runs | 13 | 12 | _unclassified_ |
| 2.5 | bowler_overs | 2.0 | 1.5 | F-A-commit-lag |
| 2.5 | bowler_runs | 13 | 12 | _unclassified_ |
| 2.6 | bowler_name | — | Roy | F-B-ad-occlusion |
| 2.6 | bowler_overs | — | 2.0 | F-A-commit-lag |
| 2.6 | bowler_runs | 0 | 18 | _unclassified_ |
| 3.1 | bowler_name | — | Narine | F-B-ad-occlusion |
| 3.1 | bowler_overs | — | 0.1 | F-A-commit-lag |
| 3.1 | bowler_runs | 0 | 1 | _unclassified_ |
| 3.1 | recent_over_n_minus_1 | [] | [".", "4", "1", ".", ".", "6"] | Recent-overs-drop |
| 3.6 | bowler_name | — | Narine | F-B-ad-occlusion |
| 3.6 | bowler_overs | — | 1.0 | F-A-commit-lag |
| 3.6 | bowler_runs | 0 | 11 | _unclassified_ |
| 4.1 | bowler_name | — | Tyagi | F-B-ad-occlusion |
| 4.1 | bowler_overs | — | 0.1 | F-A-commit-lag |
| 4.1 | bowler_runs | 0 | 4 | _unclassified_ |
| 4.1 | recent_over_n_minus_1 | [] | ["1", "4", ".", "1", "4", "1"] | Recent-overs-drop |
| 4.2 | bowler_name | — | Tyagi | F-B-ad-occlusion |
| 4.2 | bowler_overs | — | 0.2 | F-A-commit-lag |
| 4.2 | bowler_runs | 0 | 5 | _unclassified_ |
| 4.3 | bowler_name | — | Tyagi | F-B-ad-occlusion |
| 4.3 | bowler_overs | — | 0.3 | F-A-commit-lag |
| 4.3 | bowler_runs | 0 | 5 | _unclassified_ |
| 4.4 | bowler_name | — | Tyagi | F-B-ad-occlusion |
| 4.4 | bowler_overs | — | 0.4 | F-A-commit-lag |
| 4.4 | bowler_runs | 0 | 6 | _unclassified_ |
| 4.5 | bowler_name | — | Tyagi | F-B-ad-occlusion |
| 4.5 | bowler_overs | — | 0.5 | F-A-commit-lag |
| 4.5 | bowler_runs | 0 | 10 | _unclassified_ |
| 5.1 | non_striker_name | Rahul | — | _unclassified_ |
| 5.1 | non_striker_runs | 23 | 0 | _unclassified_ |
| 5.1 | non_striker_balls | 13 | 0 | _unclassified_ |
| 5.1 | non_striker_fours | 4 | 0 | _unclassified_ |
| 5.1 | bowler_name | — | Arora | F-B-ad-occlusion |
| 5.1 | bowler_overs | — | 1.1 | F-A-commit-lag |
| 5.1 | bowler_runs | 0 | 14 | _unclassified_ |
| 5.1 | recent_over_n_minus_1 | [] | ["4", "1", ".", "1", "4", "W"] | Recent-overs-drop |
| 5.1 | fow_entries | [[63, 1, "Rahul", "4.6"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 5.2 | striker_name | Rahul | — | D-post-FoW-striker |
| 5.2 | striker_runs | 23 | 0 | _unclassified_ |
| 5.2 | striker_balls | 13 | 0 | _unclassified_ |
| 5.2 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 5.2 | bowler_name | — | Arora | F-B-ad-occlusion |
| 5.2 | bowler_overs | — | 1.2 | F-A-commit-lag |
| 5.2 | bowler_runs | 0 | 15 | _unclassified_ |
| 5.2 | fow_entries | [[63, 1, "Rahul", "4.6"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 5.3 | striker_name | Rahul | Rana | D-post-FoW-striker |
| 5.3 | striker_runs | 23 | 0 | _unclassified_ |
| 5.3 | striker_balls | 13 | 1 | _unclassified_ |
| 5.3 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 5.3 | bowler_name | — | Arora | F-B-ad-occlusion |
| 5.3 | bowler_overs | — | 1.3 | F-A-commit-lag |
| 5.3 | bowler_runs | 0 | 15 | _unclassified_ |
| 5.3 | fow_entries | [[63, 1, "Rahul", "4.6"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 5.4 | striker_name | Rahul | Rana | D-post-FoW-striker |
| 5.4 | striker_runs | 23 | 0 | _unclassified_ |
| 5.4 | striker_balls | 13 | 2 | _unclassified_ |
| 5.4 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 5.4 | bowler_name | — | Arora | F-B-ad-occlusion |
| 5.4 | bowler_overs | — | 1.4 | F-A-commit-lag |
| 5.4 | bowler_runs | 0 | 15 | _unclassified_ |
| 5.4 | fow_entries | [[63, 1, "Rahul", "4.6"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 5.5 | striker_name | Rahul | Rana | D-post-FoW-striker |
| 5.5 | striker_runs | 23 | 0 | _unclassified_ |
| 5.5 | striker_balls | 13 | 3 | _unclassified_ |
| 5.5 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 5.5 | bowler_name | — | Arora | F-B-ad-occlusion |
| 5.5 | bowler_overs | — | 1.5 | F-A-commit-lag |
| 5.5 | bowler_runs | 0 | 15 | _unclassified_ |
| 5.5 | fow_entries | [[63, 1, "Rahul", "4.6"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 6.1 | non_striker_name | Rahul | Rana | _unclassified_ |
| 6.1 | non_striker_runs | 23 | 2 | _unclassified_ |
| 6.1 | non_striker_balls | 13 | 5 | _unclassified_ |
| 6.1 | non_striker_fours | 4 | 0 | _unclassified_ |
| 6.1 | recent_over_n_minus_1 | [] | ["4", "1", ".", ".", ".", "1"] | Recent-overs-drop |
| 6.1 | fow_entries | [[63, 1, "Rahul", "4.6"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 6.2 | non_striker_name | Rahul | Rana | _unclassified_ |
| 6.2 | non_striker_runs | 23 | 2 | _unclassified_ |
| 6.2 | non_striker_balls | 13 | 5 | _unclassified_ |
| 6.2 | non_striker_fours | 4 | 0 | _unclassified_ |
| 6.2 | fow_entries | [[63, 1, "Rahul", "4.6"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 6.3 | striker_name | Rahul | Rana | D-post-FoW-striker |
| 6.3 | striker_runs | 23 | 2 | _unclassified_ |
| 6.3 | striker_balls | 13 | 5 | _unclassified_ |
| 6.3 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 6.3 | fow_entries | [[63, 1, "Rahul", "4.6"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 6.4 | score | 59 | 58 | E2-phantom-runs |
| 6.4 | striker_name | Rahul | Nissanka | D-post-FoW-striker |
| 6.4 | striker_runs | 23 | 32 | _unclassified_ |
| 6.4 | striker_balls | 13 | 20 | _unclassified_ |
| 6.4 | striker_fours | 4 | 3 | _unclassified_ |
| 6.4 | striker_sixes | 0 | 2 | _unclassified_ |
| 6.4 | non_striker_name | Nissanka | Rana | _unclassified_ |
| 6.4 | non_striker_runs | 32 | 3 | _unclassified_ |
| 6.4 | non_striker_balls | 20 | 6 | _unclassified_ |
| 6.4 | non_striker_fours | 3 | 0 | _unclassified_ |
| 6.4 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 6.4 | bowler_runs | 4 | 3 | _unclassified_ |
| 6.4 | this_over_tokens | ["1", ".", "1", "2"] | ["1", ".", "1", "1"] | _unclassified_ |
| 6.4 | fow_entries | [[63, 1, "Rahul", "4.6"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 7.1 | striker_name | Rahul | Nissanka | D-post-FoW-striker |
| 7.1 | striker_runs | 23 | 36 | _unclassified_ |
| 7.1 | striker_balls | 13 | 22 | _unclassified_ |
| 7.1 | striker_sixes | 0 | 2 | _unclassified_ |
| 7.1 | non_striker_name | Nissanka | Rana | _unclassified_ |
| 7.1 | non_striker_runs | 33 | 4 | _unclassified_ |
| 7.1 | non_striker_balls | 21 | 7 | _unclassified_ |
| 7.1 | non_striker_fours | 3 | 0 | _unclassified_ |
| 7.1 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 7.1 | bowler_name | Chakaravarthy | Green | F-B-ad-occlusion |
| 7.1 | bowler_overs | 1.1 | 0.1 | F-A-commit-lag |
| 7.1 | bowler_runs | 8 | 1 | _unclassified_ |
| 7.1 | this_over_tokens | ["1", ".", "1", "2", "1"] | ["1"] | _unclassified_ |
| 7.1 | recent_over_n_minus_1 | [] | ["1", ".", "1", "1", ".", "4"] | Recent-overs-drop |
| 7.1 | fow_entries | [[63, 1, "Rahul", "4.6"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 7.2 | striker_name | Rahul | Nissanka | D-post-FoW-striker |
| 7.2 | striker_runs | 23 | 42 | _unclassified_ |
| 7.2 | striker_balls | 13 | 23 | _unclassified_ |
| 7.2 | striker_sixes | 0 | 3 | _unclassified_ |
| 7.2 | non_striker_name | Nissanka | Rana | _unclassified_ |
| 7.2 | non_striker_runs | 33 | 4 | _unclassified_ |
| 7.2 | non_striker_balls | 21 | 7 | _unclassified_ |
| 7.2 | non_striker_fours | 3 | 0 | _unclassified_ |
| 7.2 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 7.2 | bowler_name | Chakaravarthy | Green | F-B-ad-occlusion |
| 7.2 | bowler_overs | 1.2 | 0.2 | F-A-commit-lag |
| 7.2 | bowler_runs | 14 | 7 | _unclassified_ |
| 7.2 | this_over_tokens | ["1", ".", "1", "2", "1", "6"] | ["1", "6"] | _unclassified_ |
| 7.2 | fow_entries | [[63, 1, "Rahul", "4.6"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 7.3 | striker_name | Nissanka | Rana | D-post-FoW-striker |
| 7.3 | striker_runs | 33 | 4 | _unclassified_ |
| 7.3 | striker_balls | 21 | 7 | _unclassified_ |
| 7.3 | striker_fours | 3 | 0 | Boundary-counter-double-increment |
| 7.3 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 7.3 | non_striker_name | Rahul | Nissanka | _unclassified_ |
| 7.3 | non_striker_runs | 23 | 43 | _unclassified_ |
| 7.3 | non_striker_balls | 13 | 24 | _unclassified_ |
| 7.3 | non_striker_sixes | 0 | 3 | _unclassified_ |
| 7.3 | bowler_overs | 0.1 | 0.3 | F-A-commit-lag |
| 7.3 | bowler_runs | 1 | 8 | _unclassified_ |
| 7.3 | this_over_tokens | ["1", ".", "1", "2", "1", "6", "1"] | ["1", "6", "1"] | _unclassified_ |
| 7.3 | fow_entries | [[63, 1, "Rahul", "4.6"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 7.4 | striker_name | Nissanka | Rana | D-post-FoW-striker |
| 7.4 | striker_runs | 37 | 8 | _unclassified_ |
| 7.4 | striker_balls | 22 | 8 | _unclassified_ |
| 7.4 | striker_fours | 4 | 1 | Boundary-counter-double-increment |
| 7.4 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 7.4 | non_striker_name | Rahul | Nissanka | _unclassified_ |
| 7.4 | non_striker_runs | 23 | 43 | _unclassified_ |
| 7.4 | non_striker_balls | 13 | 24 | _unclassified_ |
| 7.4 | non_striker_sixes | 0 | 3 | _unclassified_ |
| 7.4 | bowler_overs | 0.2 | 0.4 | F-A-commit-lag |
| 7.4 | bowler_runs | 5 | 12 | _unclassified_ |
| 7.4 | this_over_tokens | ["1", ".", "1", "2", "1", "6", "1", "4"] | ["1", "6", "1", "4"] | _unclassified_ |
| 7.4 | fow_entries | [[63, 1, "Rahul", "4.6"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 7.5 | striker_name | Nissanka | Rana | D-post-FoW-striker |
| 7.5 | striker_runs | 37 | 8 | _unclassified_ |
| 7.5 | striker_balls | 23 | 9 | _unclassified_ |
| 7.5 | striker_fours | 4 | 1 | Boundary-counter-double-increment |
| 7.5 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 7.5 | non_striker_name | Rahul | Nissanka | _unclassified_ |
| 7.5 | non_striker_runs | 23 | 43 | _unclassified_ |
| 7.5 | non_striker_balls | 13 | 24 | _unclassified_ |
| 7.5 | non_striker_sixes | 0 | 3 | _unclassified_ |
| 7.5 | bowler_overs | 0.3 | 0.5 | F-A-commit-lag |
| 7.5 | bowler_runs | 5 | 12 | _unclassified_ |
| 7.5 | this_over_tokens | ["1", ".", "1", "2", "1", "6", "1", "4", "."] | ["1", "6", "1", "4", "."] | _unclassified_ |
| 7.5 | fow_entries | [[63, 1, "Rahul", "4.6"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 8.1 | striker_name | Rahul | — | D-post-FoW-striker |
| 8.1 | striker_runs | 23 | 0 | _unclassified_ |
| 8.1 | striker_balls | 13 | 0 | _unclassified_ |
| 8.1 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 8.1 | non_striker_runs | 37 | 44 | _unclassified_ |
| 8.1 | non_striker_balls | 23 | 25 | _unclassified_ |
| 8.1 | non_striker_sixes | 2 | 3 | _unclassified_ |
| 8.1 | bowler_name | Green | Chakaravarthy | F-B-ad-occlusion |
| 8.1 | bowler_overs | 0.5 | 1.1 | F-A-commit-lag |
| 8.1 | bowler_runs | 6 | 8 | _unclassified_ |
| 8.1 | recent_over_n_minus_1 | [] | ["1", "6", "1", "4", ".", "W"] | Recent-overs-drop |
| 8.1 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"]] | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"]] | E3-wicket-frame-misalign |
| 8.2 | striker_name | Rahul | Rizvi | D-post-FoW-striker |
| 8.2 | striker_runs | 23 | 0 | _unclassified_ |
| 8.2 | striker_balls | 13 | 1 | _unclassified_ |
| 8.2 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 8.2 | non_striker_runs | 37 | 44 | _unclassified_ |
| 8.2 | non_striker_balls | 23 | 25 | _unclassified_ |
| 8.2 | non_striker_sixes | 2 | 3 | _unclassified_ |
| 8.2 | bowler_name | Green | Chakaravarthy | F-B-ad-occlusion |
| 8.2 | bowler_overs | 1.0 | 1.2 | F-A-commit-lag |
| 8.2 | bowler_runs | 6 | 8 | _unclassified_ |
| 8.2 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"]] | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"]] | E3-wicket-frame-misalign |
| 8.3 | striker_name | Rahul | Rizvi | D-post-FoW-striker |
| 8.3 | striker_runs | 23 | 0 | _unclassified_ |
| 8.3 | striker_balls | 13 | 2 | _unclassified_ |
| 8.3 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 8.3 | non_striker_runs | 37 | 44 | _unclassified_ |
| 8.3 | non_striker_balls | 23 | 25 | _unclassified_ |
| 8.3 | non_striker_sixes | 2 | 3 | _unclassified_ |
| 8.3 | bowler_runs | 14 | 8 | _unclassified_ |
| 8.3 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"]] | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"]] | E3-wicket-frame-misalign |
| 8.4 | striker_runs | 37 | 44 | _unclassified_ |
| 8.4 | striker_balls | 23 | 25 | _unclassified_ |
| 8.4 | striker_sixes | 2 | 3 | _unclassified_ |
| 8.4 | non_striker_name | Rahul | Rizvi | _unclassified_ |
| 8.4 | non_striker_runs | 23 | 1 | _unclassified_ |
| 8.4 | non_striker_balls | 13 | 3 | _unclassified_ |
| 8.4 | non_striker_fours | 4 | 0 | _unclassified_ |
| 8.4 | bowler_runs | 15 | 9 | _unclassified_ |
| 8.4 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"]] | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"]] | E3-wicket-frame-misalign |
| 9.3 | striker_name | Rahul | Rizvi | D-post-FoW-striker |
| 9.3 | striker_runs | 23 | 1 | _unclassified_ |
| 9.3 | striker_balls | 13 | 5 | _unclassified_ |
| 9.3 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 9.3 | non_striker_runs | 37 | 46 | _unclassified_ |
| 9.3 | non_striker_balls | 23 | 28 | _unclassified_ |
| 9.3 | non_striker_sixes | 2 | 3 | _unclassified_ |
| 9.3 | bowler_overs | 1.5 | 1.3 | F-A-commit-lag |
| 9.3 | bowler_runs | 13 | 12 | _unclassified_ |
| 9.3 | this_over_tokens | ["1", ".", ".", "1", "."] | [".", "1", "."] | _unclassified_ |
| 9.3 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"], [76… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"]] | E3-wicket-frame-misalign |
| 9.4 | striker_name | Rahul | Rizvi | D-post-FoW-striker |
| 9.4 | striker_runs | 23 | 3 | _unclassified_ |
| 9.4 | striker_balls | 13 | 6 | _unclassified_ |
| 9.4 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 9.4 | non_striker_runs | 37 | 46 | _unclassified_ |
| 9.4 | non_striker_balls | 23 | 28 | _unclassified_ |
| 9.4 | non_striker_sixes | 2 | 3 | _unclassified_ |
| 9.4 | bowler_overs | 2.0 | 1.4 | F-A-commit-lag |
| 9.4 | bowler_runs | 15 | 14 | _unclassified_ |
| 9.4 | this_over_tokens | ["1", ".", ".", "1", ".", "2"] | [".", "1", ".", "2"] | _unclassified_ |
| 9.4 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"], [76… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"]] | E3-wicket-frame-misalign |
| 9.5 | striker_name | Rahul | — | D-post-FoW-striker |
| 9.5 | striker_runs | 23 | 0 | _unclassified_ |
| 9.5 | striker_balls | 13 | 0 | _unclassified_ |
| 9.5 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 9.5 | non_striker_runs | 37 | 46 | _unclassified_ |
| 9.5 | non_striker_balls | 23 | 28 | _unclassified_ |
| 9.5 | non_striker_sixes | 2 | 3 | _unclassified_ |
| 9.5 | bowler_overs | 2.1 | 1.5 | F-A-commit-lag |
| 9.5 | bowler_runs | 15 | 14 | _unclassified_ |
| 9.5 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 9.5 | this_over_tokens | ["1", ".", ".", "1", ".", "2", "."] | [".", "1", ".", "2", "W"] | C21b-symbol-revert |
| 9.5 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"], [76… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 10.1 | striker_name | Rahul | Nissanka | D-post-FoW-striker |
| 10.1 | striker_runs | 23 | 50 | _unclassified_ |
| 10.1 | striker_balls | 13 | 29 | _unclassified_ |
| 10.1 | striker_fours | 4 | 5 | _unclassified_ |
| 10.1 | striker_sixes | 0 | 3 | _unclassified_ |
| 10.1 | non_striker_name | Nissanka | Stubbs | _unclassified_ |
| 10.1 | non_striker_runs | 37 | 0 | _unclassified_ |
| 10.1 | non_striker_balls | 23 | 1 | _unclassified_ |
| 10.1 | non_striker_fours | 4 | 0 | _unclassified_ |
| 10.1 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 10.1 | bowler_overs | 2.2 | 2.1 | F-A-commit-lag |
| 10.1 | bowler_runs | 23 | 22 | _unclassified_ |
| 10.1 | recent_over_n_minus_1 | [] | [".", "1", ".", "2", "W", "."] | Recent-overs-drop |
| 10.1 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"], [76… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 10.2 | score | 87 | 85 | E2-phantom-runs |
| 10.2 | balls_total | 62 | 61 | _unclassified_ |
| 10.2 | striker_name | Nissanka | — | D-post-FoW-striker |
| 10.2 | striker_runs | 37 | 0 | _unclassified_ |
| 10.2 | striker_balls | 23 | 0 | _unclassified_ |
| 10.2 | striker_fours | 4 | 0 | _unclassified_ |
| 10.2 | striker_sixes | 2 | 0 | _unclassified_ |
| 10.2 | non_striker_name | Rahul | Stubbs | _unclassified_ |
| 10.2 | non_striker_runs | 23 | 0 | _unclassified_ |
| 10.2 | non_striker_balls | 13 | 1 | _unclassified_ |
| 10.2 | non_striker_fours | 4 | 0 | _unclassified_ |
| 10.2 | bowler_overs | 2.3 | 2.1 | F-A-commit-lag |
| 10.2 | bowler_runs | 26 | 23 | _unclassified_ |
| 10.2 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 10.2 | extras_total | 0 | 1 | Extras-counter-drop |
| 10.2 | extras_wd | 0 | 1 | Extras-counter-drop |
| 10.2 | this_over_tokens | ["4", "Wd", "1"] | ["4", "Wd+W"] | Compound-with-wicket-token |
| 10.2 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"], [76… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 10.3 | striker_name | Nissanka | Stubbs | D-post-FoW-striker |
| 10.3 | striker_runs | 37 | 2 | _unclassified_ |
| 10.3 | striker_balls | 23 | 2 | _unclassified_ |
| 10.3 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 10.3 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 10.3 | non_striker_name | Rahul | Patel | _unclassified_ |
| 10.3 | non_striker_runs | 23 | 1 | _unclassified_ |
| 10.3 | non_striker_balls | 13 | 1 | _unclassified_ |
| 10.3 | non_striker_fours | 4 | 0 | _unclassified_ |
| 10.3 | bowler_overs | 2.4 | 2.3 | F-A-commit-lag |
| 10.3 | bowler_runs | 28 | 27 | _unclassified_ |
| 10.3 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 10.3 | extras_total | 0 | 2 | Extras-counter-drop |
| 10.3 | extras_wd | 0 | 2 | Extras-counter-drop |
| 10.3 | this_over_tokens | ["4", "Wd", "1", "2"] | ["4", "Wd+W", "Wd", "1", "2"] | Compound-with-wicket-token |
| 10.3 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"], [76… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 11.1 | striker_name | Rahul | Patel | D-post-FoW-striker |
| 11.1 | striker_runs | 23 | 1 | _unclassified_ |
| 11.1 | striker_balls | 13 | 2 | _unclassified_ |
| 11.1 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 11.1 | non_striker_name | Nissanka | Sharma | _unclassified_ |
| 11.1 | non_striker_runs | 37 | 0 | _unclassified_ |
| 11.1 | non_striker_balls | 23 | 1 | _unclassified_ |
| 11.1 | non_striker_fours | 4 | 0 | _unclassified_ |
| 11.1 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 11.1 | bowler_overs | 2.3 | 2.1 | F-A-commit-lag |
| 11.1 | bowler_runs | 15 | 14 | _unclassified_ |
| 11.1 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 11.1 | extras_total | 0 | 2 | Extras-counter-drop |
| 11.1 | extras_wd | 0 | 2 | Extras-counter-drop |
| 11.1 | recent_over_n_minus_1 | [] | ["4", "Wd+W", "Wd", "1", "2", ".", "W", "."] | Recent-overs-drop |
| 11.1 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"], [76… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 11.2 | striker_name | Rahul | Patel | D-post-FoW-striker |
| 11.2 | striker_runs | 23 | 1 | _unclassified_ |
| 11.2 | striker_balls | 13 | 3 | _unclassified_ |
| 11.2 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 11.2 | non_striker_name | Nissanka | Sharma | _unclassified_ |
| 11.2 | non_striker_runs | 37 | 0 | _unclassified_ |
| 11.2 | non_striker_balls | 23 | 1 | _unclassified_ |
| 11.2 | non_striker_fours | 4 | 0 | _unclassified_ |
| 11.2 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 11.2 | bowler_overs | 2.4 | 2.2 | F-A-commit-lag |
| 11.2 | bowler_runs | 15 | 14 | _unclassified_ |
| 11.2 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 11.2 | extras_total | 0 | 2 | Extras-counter-drop |
| 11.2 | extras_wd | 0 | 2 | Extras-counter-drop |
| 11.2 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"], [76… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 11.3 | striker_name | Rahul | Patel | D-post-FoW-striker |
| 11.3 | striker_runs | 23 | 1 | _unclassified_ |
| 11.3 | striker_balls | 13 | 4 | _unclassified_ |
| 11.3 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 11.3 | non_striker_name | Nissanka | Sharma | _unclassified_ |
| 11.3 | non_striker_runs | 37 | 0 | _unclassified_ |
| 11.3 | non_striker_balls | 23 | 1 | _unclassified_ |
| 11.3 | non_striker_fours | 4 | 0 | _unclassified_ |
| 11.3 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 11.3 | bowler_overs | 2.5 | 2.3 | F-A-commit-lag |
| 11.3 | bowler_runs | 15 | 14 | _unclassified_ |
| 11.3 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 11.3 | extras_total | 0 | 2 | Extras-counter-drop |
| 11.3 | extras_wd | 0 | 2 | Extras-counter-drop |
| 11.3 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"], [76… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 11.4 | striker_name | Rahul | Patel | D-post-FoW-striker |
| 11.4 | striker_runs | 23 | 1 | _unclassified_ |
| 11.4 | striker_balls | 13 | 5 | _unclassified_ |
| 11.4 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 11.4 | non_striker_name | Nissanka | Sharma | _unclassified_ |
| 11.4 | non_striker_runs | 37 | 0 | _unclassified_ |
| 11.4 | non_striker_balls | 23 | 1 | _unclassified_ |
| 11.4 | non_striker_fours | 4 | 0 | _unclassified_ |
| 11.4 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 11.4 | bowler_overs | 3.0 | 2.4 | F-A-commit-lag |
| 11.4 | bowler_runs | 15 | 14 | _unclassified_ |
| 11.4 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 11.4 | extras_total | 0 | 2 | Extras-counter-drop |
| 11.4 | extras_wd | 0 | 2 | Extras-counter-drop |
| 11.4 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"], [76… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 11.5 | striker_name | Nissanka | Sharma | D-post-FoW-striker |
| 11.5 | striker_runs | 37 | 0 | _unclassified_ |
| 11.5 | striker_balls | 23 | 1 | _unclassified_ |
| 11.5 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 11.5 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 11.5 | non_striker_name | Rahul | Patel | _unclassified_ |
| 11.5 | non_striker_runs | 23 | 2 | _unclassified_ |
| 11.5 | non_striker_balls | 13 | 6 | _unclassified_ |
| 11.5 | non_striker_fours | 4 | 0 | _unclassified_ |
| 11.5 | bowler_overs | 3.1 | 2.5 | F-A-commit-lag |
| 11.5 | bowler_runs | 16 | 15 | _unclassified_ |
| 11.5 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 11.5 | extras_total | 0 | 2 | Extras-counter-drop |
| 11.5 | extras_wd | 0 | 2 | Extras-counter-drop |
| 11.5 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"], [76… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 12.1 | striker_name | Nissanka | Sharma | D-post-FoW-striker |
| 12.1 | striker_runs | 37 | 0 | _unclassified_ |
| 12.1 | striker_balls | 23 | 2 | _unclassified_ |
| 12.1 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 12.1 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 12.1 | non_striker_name | Rahul | Patel | _unclassified_ |
| 12.1 | non_striker_runs | 23 | 3 | _unclassified_ |
| 12.1 | non_striker_balls | 13 | 7 | _unclassified_ |
| 12.1 | non_striker_fours | 4 | 0 | _unclassified_ |
| 12.1 | bowler_overs | 3.2 | 3.1 | F-A-commit-lag |
| 12.1 | bowler_runs | 29 | 28 | _unclassified_ |
| 12.1 | bowler_wickets | 0 | 2 | Bowler-W-credit-failure |
| 12.1 | extras_total | 0 | 2 | Extras-counter-drop |
| 12.1 | extras_wd | 0 | 2 | Extras-counter-drop |
| 12.1 | recent_over_n_minus_1 | [] | [".", ".", ".", ".", "1", "."] | Recent-overs-drop |
| 12.1 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"], [76… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 12.2 | striker_name | Nissanka | Sharma | D-post-FoW-striker |
| 12.2 | striker_runs | 37 | 0 | _unclassified_ |
| 12.2 | striker_balls | 23 | 3 | _unclassified_ |
| 12.2 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 12.2 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 12.2 | non_striker_name | Rahul | Patel | _unclassified_ |
| 12.2 | non_striker_runs | 23 | 3 | _unclassified_ |
| 12.2 | non_striker_balls | 13 | 7 | _unclassified_ |
| 12.2 | non_striker_fours | 4 | 0 | _unclassified_ |
| 12.2 | bowler_overs | 3.3 | 3.2 | F-A-commit-lag |
| 12.2 | bowler_runs | 29 | 28 | _unclassified_ |
| 12.2 | bowler_wickets | 0 | 2 | Bowler-W-credit-failure |
| 12.2 | extras_total | 0 | 2 | Extras-counter-drop |
| 12.2 | extras_wd | 0 | 2 | Extras-counter-drop |
| 12.2 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"], [76… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 12.3 | striker_name | Nissanka | Sharma | D-post-FoW-striker |
| 12.3 | striker_runs | 37 | 0 | _unclassified_ |
| 12.3 | striker_balls | 23 | 4 | _unclassified_ |
| 12.3 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 12.3 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 12.3 | non_striker_name | Rahul | Patel | _unclassified_ |
| 12.3 | non_striker_runs | 23 | 3 | _unclassified_ |
| 12.3 | non_striker_balls | 13 | 7 | _unclassified_ |
| 12.3 | non_striker_fours | 4 | 0 | _unclassified_ |
| 12.3 | bowler_overs | 3.4 | 3.3 | F-A-commit-lag |
| 12.3 | bowler_runs | 29 | 28 | _unclassified_ |
| 12.3 | bowler_wickets | 0 | 2 | Bowler-W-credit-failure |
| 12.3 | extras_total | 0 | 2 | Extras-counter-drop |
| 12.3 | extras_wd | 0 | 2 | Extras-counter-drop |
| 12.3 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"], [76… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 12.4 | striker_name | Rahul | Patel | D-post-FoW-striker |
| 12.4 | striker_runs | 23 | 3 | _unclassified_ |
| 12.4 | striker_balls | 13 | 7 | _unclassified_ |
| 12.4 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 12.4 | non_striker_name | Nissanka | Sharma | _unclassified_ |
| 12.4 | non_striker_runs | 37 | 1 | _unclassified_ |
| 12.4 | non_striker_balls | 23 | 5 | _unclassified_ |
| 12.4 | non_striker_fours | 4 | 0 | _unclassified_ |
| 12.4 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 12.4 | bowler_overs | 3.5 | 3.4 | F-A-commit-lag |
| 12.4 | bowler_runs | 30 | 29 | _unclassified_ |
| 12.4 | bowler_wickets | 0 | 2 | Bowler-W-credit-failure |
| 12.4 | extras_total | 0 | 2 | Extras-counter-drop |
| 12.4 | extras_wd | 0 | 2 | Extras-counter-drop |
| 12.4 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"], [76… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 12.5 | striker_name | Nissanka | Sharma | D-post-FoW-striker |
| 12.5 | striker_runs | 37 | 1 | _unclassified_ |
| 12.5 | striker_balls | 23 | 5 | _unclassified_ |
| 12.5 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 12.5 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 12.5 | non_striker_name | Rahul | Patel | _unclassified_ |
| 12.5 | non_striker_runs | 23 | 4 | _unclassified_ |
| 12.5 | non_striker_balls | 13 | 8 | _unclassified_ |
| 12.5 | non_striker_fours | 4 | 0 | _unclassified_ |
| 12.5 | bowler_overs | 4.0 | 3.5 | F-A-commit-lag |
| 12.5 | bowler_runs | 31 | 30 | _unclassified_ |
| 12.5 | bowler_wickets | 0 | 2 | Bowler-W-credit-failure |
| 12.5 | extras_total | 0 | 2 | Extras-counter-drop |
| 12.5 | extras_wd | 0 | 2 | Extras-counter-drop |
| 12.5 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"], [76… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 13.1 | striker_name | Nissanka | Sharma | D-post-FoW-striker |
| 13.1 | striker_runs | 37 | 2 | _unclassified_ |
| 13.1 | striker_balls | 23 | 7 | _unclassified_ |
| 13.1 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 13.1 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 13.1 | non_striker_name | Rahul | Patel | _unclassified_ |
| 13.1 | non_striker_runs | 23 | 4 | _unclassified_ |
| 13.1 | non_striker_balls | 13 | 8 | _unclassified_ |
| 13.1 | non_striker_fours | 4 | 0 | _unclassified_ |
| 13.1 | bowler_overs | 1.5 | 2.1 | F-A-commit-lag |
| 13.1 | bowler_runs | 15 | 10 | _unclassified_ |
| 13.1 | extras_total | 0 | 2 | Extras-counter-drop |
| 13.1 | extras_wd | 0 | 2 | Extras-counter-drop |
| 13.1 | recent_over_n_minus_1 | [] | ["1", ".", ".", "1", "1", "1"] | Recent-overs-drop |
| 13.1 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"], [76… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 13.2 | striker_name | Rahul | Patel | D-post-FoW-striker |
| 13.2 | striker_runs | 23 | 4 | _unclassified_ |
| 13.2 | striker_balls | 13 | 8 | _unclassified_ |
| 13.2 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 13.2 | non_striker_name | Nissanka | Sharma | _unclassified_ |
| 13.2 | non_striker_runs | 37 | 3 | _unclassified_ |
| 13.2 | non_striker_balls | 23 | 8 | _unclassified_ |
| 13.2 | non_striker_fours | 4 | 0 | _unclassified_ |
| 13.2 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 13.2 | bowler_overs | 2.0 | 2.2 | F-A-commit-lag |
| 13.2 | bowler_runs | 16 | 11 | _unclassified_ |
| 13.2 | extras_total | 0 | 2 | Extras-counter-drop |
| 13.2 | extras_wd | 0 | 2 | Extras-counter-drop |
| 13.2 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"], [76… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 13.3 | striker_name | Rahul | Patel | D-post-FoW-striker |
| 13.3 | striker_runs | 23 | 4 | _unclassified_ |
| 13.3 | striker_balls | 13 | 9 | _unclassified_ |
| 13.3 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 13.3 | non_striker_name | Nissanka | Sharma | _unclassified_ |
| 13.3 | non_striker_runs | 37 | 3 | _unclassified_ |
| 13.3 | non_striker_balls | 23 | 8 | _unclassified_ |
| 13.3 | non_striker_fours | 4 | 0 | _unclassified_ |
| 13.3 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 13.3 | bowler_overs | 2.1 | 2.3 | F-A-commit-lag |
| 13.3 | bowler_runs | 16 | 11 | _unclassified_ |
| 13.3 | extras_total | 0 | 2 | Extras-counter-drop |
| 13.3 | extras_wd | 0 | 2 | Extras-counter-drop |
| 13.3 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"], [76… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 13.4 | striker_name | Rahul | Patel | D-post-FoW-striker |
| 13.4 | striker_runs | 23 | 4 | _unclassified_ |
| 13.4 | striker_balls | 13 | 10 | _unclassified_ |
| 13.4 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 13.4 | non_striker_name | Nissanka | Sharma | _unclassified_ |
| 13.4 | non_striker_runs | 37 | 3 | _unclassified_ |
| 13.4 | non_striker_balls | 23 | 8 | _unclassified_ |
| 13.4 | non_striker_fours | 4 | 0 | _unclassified_ |
| 13.4 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 13.4 | bowler_overs | 2.2 | 2.4 | F-A-commit-lag |
| 13.4 | bowler_runs | 16 | 11 | _unclassified_ |
| 13.4 | extras_total | 0 | 2 | Extras-counter-drop |
| 13.4 | extras_wd | 0 | 2 | Extras-counter-drop |
| 13.4 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"], [76… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 13.5 | striker_name | Rahul | Patel | D-post-FoW-striker |
| 13.5 | striker_runs | 23 | 4 | _unclassified_ |
| 13.5 | striker_balls | 13 | 11 | _unclassified_ |
| 13.5 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 13.5 | non_striker_name | Nissanka | Sharma | _unclassified_ |
| 13.5 | non_striker_runs | 37 | 3 | _unclassified_ |
| 13.5 | non_striker_balls | 23 | 8 | _unclassified_ |
| 13.5 | non_striker_fours | 4 | 0 | _unclassified_ |
| 13.5 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 13.5 | bowler_overs | 2.3 | 2.5 | F-A-commit-lag |
| 13.5 | bowler_runs | 16 | 11 | _unclassified_ |
| 13.5 | extras_total | 0 | 2 | Extras-counter-drop |
| 13.5 | extras_wd | 0 | 2 | Extras-counter-drop |
| 13.5 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"], [76… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 13.6 | striker_name | Rahul | Patel | D-post-FoW-striker |
| 13.6 | striker_runs | 23 | 5 | _unclassified_ |
| 13.6 | striker_balls | 13 | 12 | _unclassified_ |
| 13.6 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 13.6 | non_striker_name | Nissanka | Sharma | _unclassified_ |
| 13.6 | non_striker_runs | 37 | 3 | _unclassified_ |
| 13.6 | non_striker_balls | 23 | 8 | _unclassified_ |
| 13.6 | non_striker_fours | 4 | 0 | _unclassified_ |
| 13.6 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 13.6 | bowler_name | — | Chakaravarthy | F-B-ad-occlusion |
| 13.6 | bowler_overs | — | 3.0 | F-A-commit-lag |
| 13.6 | bowler_runs | 0 | 12 | _unclassified_ |
| 13.6 | extras_total | 0 | 2 | Extras-counter-drop |
| 13.6 | extras_wd | 0 | 2 | Extras-counter-drop |
| 13.6 | fow_entries | [[63, 1, "Rahul", "4.6"], [74, 2, "Nissanka", "7.6"], [76… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |

## 3. Conservation invariants

All conservation checks passed.

## 4. Unclassified divergences

| over.ball | field | pipeline | ground-truth |
|---|---|---|---|
| 0.1 | non_striker_name | Rahul | — |
| 0.2 | non_striker_name | Rahul | — |
| 0.3 | striker_name | Rahul | — |
| 0.6 | bowler_runs | 0 | 7 |
| 1.5 | this_over_tokens | [".", "1", "?", "?", "1"] | [".", "1", "1", "6", "1"] |
| 1.6 | bowler_runs | 8 | 10 |
| 1.6 | this_over_tokens | [".", "1", "?", "?", "1", "1"] | [".", "1", "1", "6", "1", "1"] |
| 2.1 | bowler_runs | 8 | 7 |
| 2.2 | bowler_runs | 12 | 11 |
| 2.3 | bowler_runs | 13 | 12 |
| 2.4 | bowler_runs | 13 | 12 |
| 2.5 | bowler_runs | 13 | 12 |
| 2.6 | bowler_runs | 0 | 18 |
| 3.1 | bowler_runs | 0 | 1 |
| 3.6 | bowler_runs | 0 | 11 |
| 4.1 | bowler_runs | 0 | 4 |
| 4.2 | bowler_runs | 0 | 5 |
| 4.3 | bowler_runs | 0 | 5 |
| 4.4 | bowler_runs | 0 | 6 |
| 4.5 | bowler_runs | 0 | 10 |
| 5.1 | non_striker_name | Rahul | — |
| 5.1 | non_striker_runs | 23 | 0 |
| 5.1 | non_striker_balls | 13 | 0 |
| 5.1 | non_striker_fours | 4 | 0 |
| 5.1 | bowler_runs | 0 | 14 |
| 5.2 | striker_runs | 23 | 0 |
| 5.2 | striker_balls | 13 | 0 |
| 5.2 | bowler_runs | 0 | 15 |
| 5.3 | striker_runs | 23 | 0 |
| 5.3 | striker_balls | 13 | 1 |
| 5.3 | bowler_runs | 0 | 15 |
| 5.4 | striker_runs | 23 | 0 |
| 5.4 | striker_balls | 13 | 2 |
| 5.4 | bowler_runs | 0 | 15 |
| 5.5 | striker_runs | 23 | 0 |
| 5.5 | striker_balls | 13 | 3 |
| 5.5 | bowler_runs | 0 | 15 |
| 6.1 | non_striker_name | Rahul | Rana |
| 6.1 | non_striker_runs | 23 | 2 |
| 6.1 | non_striker_balls | 13 | 5 |
| 6.1 | non_striker_fours | 4 | 0 |
| 6.2 | non_striker_name | Rahul | Rana |
| 6.2 | non_striker_runs | 23 | 2 |
| 6.2 | non_striker_balls | 13 | 5 |
| 6.2 | non_striker_fours | 4 | 0 |
| 6.3 | striker_runs | 23 | 2 |
| 6.3 | striker_balls | 13 | 5 |
| 6.4 | striker_runs | 23 | 32 |
| 6.4 | striker_balls | 13 | 20 |
| 6.4 | striker_fours | 4 | 3 |
| 6.4 | striker_sixes | 0 | 2 |
| 6.4 | non_striker_name | Nissanka | Rana |
| 6.4 | non_striker_runs | 32 | 3 |
| 6.4 | non_striker_balls | 20 | 6 |
| 6.4 | non_striker_fours | 3 | 0 |
| 6.4 | non_striker_sixes | 2 | 0 |
| 6.4 | bowler_runs | 4 | 3 |
| 6.4 | this_over_tokens | ["1", ".", "1", "2"] | ["1", ".", "1", "1"] |
| 7.1 | striker_runs | 23 | 36 |
| 7.1 | striker_balls | 13 | 22 |
| 7.1 | striker_sixes | 0 | 2 |
| 7.1 | non_striker_name | Nissanka | Rana |
| 7.1 | non_striker_runs | 33 | 4 |
| 7.1 | non_striker_balls | 21 | 7 |
| 7.1 | non_striker_fours | 3 | 0 |
| 7.1 | non_striker_sixes | 2 | 0 |
| 7.1 | bowler_runs | 8 | 1 |
| 7.1 | this_over_tokens | ["1", ".", "1", "2", "1"] | ["1"] |
| 7.2 | striker_runs | 23 | 42 |
| 7.2 | striker_balls | 13 | 23 |
| 7.2 | striker_sixes | 0 | 3 |
| 7.2 | non_striker_name | Nissanka | Rana |
| 7.2 | non_striker_runs | 33 | 4 |
| 7.2 | non_striker_balls | 21 | 7 |
| 7.2 | non_striker_fours | 3 | 0 |
| 7.2 | non_striker_sixes | 2 | 0 |
| 7.2 | bowler_runs | 14 | 7 |
| 7.2 | this_over_tokens | ["1", ".", "1", "2", "1", "6"] | ["1", "6"] |
| 7.3 | striker_runs | 33 | 4 |
| 7.3 | striker_balls | 21 | 7 |
| 7.3 | non_striker_name | Rahul | Nissanka |
| 7.3 | non_striker_runs | 23 | 43 |
| 7.3 | non_striker_balls | 13 | 24 |
| 7.3 | non_striker_sixes | 0 | 3 |
| 7.3 | bowler_runs | 1 | 8 |
| 7.3 | this_over_tokens | ["1", ".", "1", "2", "1", "6", "1"] | ["1", "6", "1"] |
| 7.4 | striker_runs | 37 | 8 |
| 7.4 | striker_balls | 22 | 8 |
| 7.4 | non_striker_name | Rahul | Nissanka |
| 7.4 | non_striker_runs | 23 | 43 |
| 7.4 | non_striker_balls | 13 | 24 |
| 7.4 | non_striker_sixes | 0 | 3 |
| 7.4 | bowler_runs | 5 | 12 |
| 7.4 | this_over_tokens | ["1", ".", "1", "2", "1", "6", "1", "4"] | ["1", "6", "1", "4"] |
| 7.5 | striker_runs | 37 | 8 |
| 7.5 | striker_balls | 23 | 9 |
| 7.5 | non_striker_name | Rahul | Nissanka |
| 7.5 | non_striker_runs | 23 | 43 |
| 7.5 | non_striker_balls | 13 | 24 |
| 7.5 | non_striker_sixes | 0 | 3 |
| 7.5 | bowler_runs | 5 | 12 |
| 7.5 | this_over_tokens | ["1", ".", "1", "2", "1", "6", "1", "4", "."] | ["1", "6", "1", "4", "."] |
| 8.1 | striker_runs | 23 | 0 |
| 8.1 | striker_balls | 13 | 0 |
| 8.1 | non_striker_runs | 37 | 44 |
| 8.1 | non_striker_balls | 23 | 25 |
| 8.1 | non_striker_sixes | 2 | 3 |
| 8.1 | bowler_runs | 6 | 8 |
| 8.2 | striker_runs | 23 | 0 |
| 8.2 | striker_balls | 13 | 1 |
| 8.2 | non_striker_runs | 37 | 44 |
| 8.2 | non_striker_balls | 23 | 25 |
| 8.2 | non_striker_sixes | 2 | 3 |
| 8.2 | bowler_runs | 6 | 8 |
| 8.3 | striker_runs | 23 | 0 |
| 8.3 | striker_balls | 13 | 2 |
| 8.3 | non_striker_runs | 37 | 44 |
| 8.3 | non_striker_balls | 23 | 25 |
| 8.3 | non_striker_sixes | 2 | 3 |
| 8.3 | bowler_runs | 14 | 8 |
| 8.4 | striker_runs | 37 | 44 |
| 8.4 | striker_balls | 23 | 25 |
| 8.4 | striker_sixes | 2 | 3 |
| 8.4 | non_striker_name | Rahul | Rizvi |
| 8.4 | non_striker_runs | 23 | 1 |
| 8.4 | non_striker_balls | 13 | 3 |
| 8.4 | non_striker_fours | 4 | 0 |
| 8.4 | bowler_runs | 15 | 9 |
| 9.3 | striker_runs | 23 | 1 |
| 9.3 | striker_balls | 13 | 5 |
| 9.3 | non_striker_runs | 37 | 46 |
| 9.3 | non_striker_balls | 23 | 28 |
| 9.3 | non_striker_sixes | 2 | 3 |
| 9.3 | bowler_runs | 13 | 12 |
| 9.3 | this_over_tokens | ["1", ".", ".", "1", "."] | [".", "1", "."] |
| 9.4 | striker_runs | 23 | 3 |
| 9.4 | striker_balls | 13 | 6 |
| 9.4 | non_striker_runs | 37 | 46 |
| 9.4 | non_striker_balls | 23 | 28 |
| 9.4 | non_striker_sixes | 2 | 3 |
| 9.4 | bowler_runs | 15 | 14 |
| 9.4 | this_over_tokens | ["1", ".", ".", "1", ".", "2"] | [".", "1", ".", "2"] |
| 9.5 | striker_runs | 23 | 0 |
| 9.5 | striker_balls | 13 | 0 |
| 9.5 | non_striker_runs | 37 | 46 |
| 9.5 | non_striker_balls | 23 | 28 |
| 9.5 | non_striker_sixes | 2 | 3 |
| 9.5 | bowler_runs | 15 | 14 |
| 10.1 | striker_runs | 23 | 50 |
| 10.1 | striker_balls | 13 | 29 |
| 10.1 | striker_fours | 4 | 5 |
| 10.1 | striker_sixes | 0 | 3 |
| 10.1 | non_striker_name | Nissanka | Stubbs |
| 10.1 | non_striker_runs | 37 | 0 |
| 10.1 | non_striker_balls | 23 | 1 |
| 10.1 | non_striker_fours | 4 | 0 |
| 10.1 | non_striker_sixes | 2 | 0 |
| 10.1 | bowler_runs | 23 | 22 |
| 10.2 | balls_total | 62 | 61 |
| 10.2 | striker_runs | 37 | 0 |
| 10.2 | striker_balls | 23 | 0 |
| 10.2 | striker_fours | 4 | 0 |
| 10.2 | striker_sixes | 2 | 0 |
| 10.2 | non_striker_name | Rahul | Stubbs |
| 10.2 | non_striker_runs | 23 | 0 |
| 10.2 | non_striker_balls | 13 | 1 |
| 10.2 | non_striker_fours | 4 | 0 |
| 10.2 | bowler_runs | 26 | 23 |
| 10.3 | striker_runs | 37 | 2 |
| 10.3 | striker_balls | 23 | 2 |
| 10.3 | non_striker_name | Rahul | Patel |
| 10.3 | non_striker_runs | 23 | 1 |
| 10.3 | non_striker_balls | 13 | 1 |
| 10.3 | non_striker_fours | 4 | 0 |
| 10.3 | bowler_runs | 28 | 27 |
| 11.1 | striker_runs | 23 | 1 |
| 11.1 | striker_balls | 13 | 2 |
| 11.1 | non_striker_name | Nissanka | Sharma |
| 11.1 | non_striker_runs | 37 | 0 |
| 11.1 | non_striker_balls | 23 | 1 |
| 11.1 | non_striker_fours | 4 | 0 |
| 11.1 | non_striker_sixes | 2 | 0 |
| 11.1 | bowler_runs | 15 | 14 |
| 11.2 | striker_runs | 23 | 1 |
| 11.2 | striker_balls | 13 | 3 |
| 11.2 | non_striker_name | Nissanka | Sharma |
| 11.2 | non_striker_runs | 37 | 0 |
| 11.2 | non_striker_balls | 23 | 1 |
| 11.2 | non_striker_fours | 4 | 0 |
| 11.2 | non_striker_sixes | 2 | 0 |
| 11.2 | bowler_runs | 15 | 14 |
| 11.3 | striker_runs | 23 | 1 |
| 11.3 | striker_balls | 13 | 4 |
| 11.3 | non_striker_name | Nissanka | Sharma |
| 11.3 | non_striker_runs | 37 | 0 |
| 11.3 | non_striker_balls | 23 | 1 |
| 11.3 | non_striker_fours | 4 | 0 |
| 11.3 | non_striker_sixes | 2 | 0 |
| 11.3 | bowler_runs | 15 | 14 |
| 11.4 | striker_runs | 23 | 1 |
| 11.4 | striker_balls | 13 | 5 |
| 11.4 | non_striker_name | Nissanka | Sharma |
| 11.4 | non_striker_runs | 37 | 0 |
| 11.4 | non_striker_balls | 23 | 1 |
| 11.4 | non_striker_fours | 4 | 0 |
| 11.4 | non_striker_sixes | 2 | 0 |
| 11.4 | bowler_runs | 15 | 14 |
| 11.5 | striker_runs | 37 | 0 |
| 11.5 | striker_balls | 23 | 1 |
| 11.5 | non_striker_name | Rahul | Patel |
| 11.5 | non_striker_runs | 23 | 2 |
| 11.5 | non_striker_balls | 13 | 6 |
| 11.5 | non_striker_fours | 4 | 0 |
| 11.5 | bowler_runs | 16 | 15 |
| 12.1 | striker_runs | 37 | 0 |
| 12.1 | striker_balls | 23 | 2 |
| 12.1 | non_striker_name | Rahul | Patel |
| 12.1 | non_striker_runs | 23 | 3 |
| 12.1 | non_striker_balls | 13 | 7 |
| 12.1 | non_striker_fours | 4 | 0 |
| 12.1 | bowler_runs | 29 | 28 |
| 12.2 | striker_runs | 37 | 0 |
| 12.2 | striker_balls | 23 | 3 |
| 12.2 | non_striker_name | Rahul | Patel |
| 12.2 | non_striker_runs | 23 | 3 |
| 12.2 | non_striker_balls | 13 | 7 |
| 12.2 | non_striker_fours | 4 | 0 |
| 12.2 | bowler_runs | 29 | 28 |
| 12.3 | striker_runs | 37 | 0 |
| 12.3 | striker_balls | 23 | 4 |
| 12.3 | non_striker_name | Rahul | Patel |
| 12.3 | non_striker_runs | 23 | 3 |
| 12.3 | non_striker_balls | 13 | 7 |
| 12.3 | non_striker_fours | 4 | 0 |
| 12.3 | bowler_runs | 29 | 28 |
| 12.4 | striker_runs | 23 | 3 |
| 12.4 | striker_balls | 13 | 7 |
| 12.4 | non_striker_name | Nissanka | Sharma |
| 12.4 | non_striker_runs | 37 | 1 |
| 12.4 | non_striker_balls | 23 | 5 |
| 12.4 | non_striker_fours | 4 | 0 |
| 12.4 | non_striker_sixes | 2 | 0 |
| 12.4 | bowler_runs | 30 | 29 |
| 12.5 | striker_runs | 37 | 1 |
| 12.5 | striker_balls | 23 | 5 |
| 12.5 | non_striker_name | Rahul | Patel |
| 12.5 | non_striker_runs | 23 | 4 |
| 12.5 | non_striker_balls | 13 | 8 |
| 12.5 | non_striker_fours | 4 | 0 |
| 12.5 | bowler_runs | 31 | 30 |
| 13.1 | striker_runs | 37 | 2 |
| 13.1 | striker_balls | 23 | 7 |
| 13.1 | non_striker_name | Rahul | Patel |
| 13.1 | non_striker_runs | 23 | 4 |
| 13.1 | non_striker_balls | 13 | 8 |
| 13.1 | non_striker_fours | 4 | 0 |
| 13.1 | bowler_runs | 15 | 10 |
| 13.2 | striker_runs | 23 | 4 |
| 13.2 | striker_balls | 13 | 8 |
| 13.2 | non_striker_name | Nissanka | Sharma |
| 13.2 | non_striker_runs | 37 | 3 |
| 13.2 | non_striker_balls | 23 | 8 |
| 13.2 | non_striker_fours | 4 | 0 |
| 13.2 | non_striker_sixes | 2 | 0 |
| 13.2 | bowler_runs | 16 | 11 |
| 13.3 | striker_runs | 23 | 4 |
| 13.3 | striker_balls | 13 | 9 |
| 13.3 | non_striker_name | Nissanka | Sharma |
| 13.3 | non_striker_runs | 37 | 3 |
| 13.3 | non_striker_balls | 23 | 8 |
| 13.3 | non_striker_fours | 4 | 0 |
| 13.3 | non_striker_sixes | 2 | 0 |
| 13.3 | bowler_runs | 16 | 11 |
| 13.4 | striker_runs | 23 | 4 |
| 13.4 | striker_balls | 13 | 10 |
| 13.4 | non_striker_name | Nissanka | Sharma |
| 13.4 | non_striker_runs | 37 | 3 |
| 13.4 | non_striker_balls | 23 | 8 |
| 13.4 | non_striker_fours | 4 | 0 |
| 13.4 | non_striker_sixes | 2 | 0 |
| 13.4 | bowler_runs | 16 | 11 |
| 13.5 | striker_runs | 23 | 4 |
| 13.5 | striker_balls | 13 | 11 |
| 13.5 | non_striker_name | Nissanka | Sharma |
| 13.5 | non_striker_runs | 37 | 3 |
| 13.5 | non_striker_balls | 23 | 8 |
| 13.5 | non_striker_fours | 4 | 0 |
| 13.5 | non_striker_sixes | 2 | 0 |
| 13.5 | bowler_runs | 16 | 11 |
| 13.6 | striker_runs | 23 | 5 |
| 13.6 | striker_balls | 13 | 12 |
| 13.6 | non_striker_name | Nissanka | Sharma |
| 13.6 | non_striker_runs | 37 | 3 |
| 13.6 | non_striker_balls | 23 | 8 |
| 13.6 | non_striker_fours | 4 | 0 |
| 13.6 | non_striker_sixes | 2 | 0 |
| 13.6 | bowler_runs | 0 | 12 |

## 5. Missing / phantom balls

- Missing-in-pipeline (55): 1.3, 1.4, 4.6, 5.6, 6.5, 6.6, 7.6, 8.5, 8.6, 9.1, 9.2, 9.6, 10.2#1, 10.2#2, 10.4, 10.5, 10.6, 11.6, 12.6, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 19.1, 19.2, 19.3, 19.4, 19.5, 19.6
- Phantom-in-pipeline (3): 8.4#1, 10.1#1, 10.1#2
