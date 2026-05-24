# Differential diff report

- Pipeline: `/tmp/validate_dckkr_20260521_155356_snapshots.jsonl`
- Ground truth: `files/tests/fixtures/dckkr_ground_truth_ui_snapshots.jsonl`
- Matched balls: 61 | missing-in-pipeline: 61 | phantom-in-pipeline: 5 | total divergences: 444

## 1. Per-surface incident counts

| Surface | Count | First example (over.ball) |
|---|---|---|
| G-pipeline-lag | 61 | 2.6 |
| F-A-commit-lag | 35 | 0.1 |
| E3-wicket-frame-misalign | 33 | 5.1 |
| D-post-FoW-striker | 28 | 5.2 |
| Boundary-counter-double-increment | 27 | 5.2 |
| F-B-ad-occlusion | 23 | 0.6 |
| Extras-counter-drop | 18 | 10.2 |
| Recent-overs-drop | 11 | 1.1 |
| Bowler-W-credit-failure | 7 | 9.5 |
| Compound-with-wicket-token | 3 | 10.2 |
| Silent-wicket-absorption | 2 | 7.6 |
| C21b-symbol-revert | 2 | 9.5 |
| E2-phantom-runs | 1 | 10.2 |

## 2. Per-ball divergences

| over.ball | field | pipeline | ground-truth | surface |
|---|---|---|---|---|
| 0.1 | striker_name | — | Nissanka | _unclassified_ |
| 0.1 | striker_balls | 0 | 1 | _unclassified_ |
| 0.1 | bowler_overs | — | 0.1 | F-A-commit-lag |
| 0.2 | striker_balls | 1 | 2 | _unclassified_ |
| 0.2 | non_striker_name | Rahul | — | _unclassified_ |
| 0.2 | bowler_overs | 0.1 | 0.2 | F-A-commit-lag |
| 0.3 | striker_name | Rahul | — | _unclassified_ |
| 0.3 | non_striker_balls | 2 | 3 | _unclassified_ |
| 0.3 | bowler_overs | 0.2 | 0.3 | F-A-commit-lag |
| 0.4 | non_striker_balls | 2 | 3 | _unclassified_ |
| 0.4 | bowler_overs | 0.3 | 0.4 | F-A-commit-lag |
| 0.5 | striker_balls | 2 | 3 | _unclassified_ |
| 0.5 | bowler_overs | 0.4 | 0.5 | F-A-commit-lag |
| 0.6 | striker_balls | 3 | 4 | _unclassified_ |
| 0.6 | bowler_name | — | Roy | F-B-ad-occlusion |
| 0.6 | bowler_overs | — | 1.0 | F-A-commit-lag |
| 0.6 | bowler_runs | 0 | 7 | _unclassified_ |
| 1.1 | striker_balls | 4 | 5 | _unclassified_ |
| 1.1 | bowler_name | — | Arora | F-B-ad-occlusion |
| 1.1 | bowler_overs | — | 0.1 | F-A-commit-lag |
| 1.1 | recent_over_n_minus_1 | [] | [".", "4", "1", ".", "1", "1"] | Recent-overs-drop |
| 1.2 | non_striker_balls | 5 | 6 | _unclassified_ |
| 1.3 | striker_balls | 5 | 6 | _unclassified_ |
| 1.4 | striker_balls | 6 | 7 | _unclassified_ |
| 1.5 | non_striker_balls | 7 | 8 | _unclassified_ |
| 1.6 | non_striker_balls | 7 | 8 | _unclassified_ |
| 1.6 | bowler_name | — | Arora | F-B-ad-occlusion |
| 1.6 | bowler_overs | — | 1.0 | F-A-commit-lag |
| 1.6 | bowler_runs | 0 | 10 | _unclassified_ |
| 2.1 | non_striker_balls | 7 | 8 | _unclassified_ |
| 2.1 | bowler_overs | 1.0 | 1.1 | F-A-commit-lag |
| 2.1 | recent_over_n_minus_1 | [] | [".", "1", "1", "6", "1", "1"] | Recent-overs-drop |
| 2.2 | non_striker_balls | 7 | 8 | _unclassified_ |
| 2.2 | bowler_overs | 1.1 | 1.2 | F-A-commit-lag |
| 2.3 | striker_balls | 7 | 8 | _unclassified_ |
| 2.3 | bowler_overs | 1.2 | 1.3 | F-A-commit-lag |
| 2.4 | striker_balls | 8 | 9 | _unclassified_ |
| 2.4 | bowler_overs | 1.3 | 1.4 | F-A-commit-lag |
| 2.5 | striker_balls | 9 | 10 | _unclassified_ |
| 2.5 | bowler_overs | 1.4 | 1.5 | F-A-commit-lag |
| 3.1 | striker_balls | 10 | 11 | _unclassified_ |
| 3.1 | bowler_name | — | Narine | F-B-ad-occlusion |
| 3.1 | bowler_overs | — | 0.1 | F-A-commit-lag |
| 3.1 | bowler_runs | 0 | 1 | _unclassified_ |
| 3.1 | recent_over_n_minus_1 | [] | [".", "4", "1", ".", ".", "6"] | Recent-overs-drop |
| 3.2 | striker_balls | 11 | 12 | _unclassified_ |
| 3.3 | striker_balls | 12 | 13 | _unclassified_ |
| 3.4 | non_striker_balls | 13 | 14 | _unclassified_ |
| 3.5 | non_striker_balls | 13 | 14 | _unclassified_ |
| 3.6 | non_striker_balls | 13 | 14 | _unclassified_ |
| 3.6 | bowler_name | — | Narine | F-B-ad-occlusion |
| 3.6 | bowler_overs | — | 1.0 | F-A-commit-lag |
| 3.6 | bowler_runs | 0 | 11 | _unclassified_ |
| 4.1 | non_striker_balls | 13 | 14 | _unclassified_ |
| 4.1 | bowler_name | — | Tyagi | F-B-ad-occlusion |
| 4.1 | bowler_overs | — | 0.1 | F-A-commit-lag |
| 4.1 | bowler_runs | 0 | 4 | _unclassified_ |
| 4.1 | recent_over_n_minus_1 | [] | ["1", "4", ".", "1", "4", "1"] | Recent-overs-drop |
| 4.2 | striker_balls | 13 | 14 | _unclassified_ |
| 4.2 | bowler_name | — | Tyagi | F-B-ad-occlusion |
| 4.2 | bowler_overs | — | 0.2 | F-A-commit-lag |
| 4.2 | bowler_runs | 0 | 5 | _unclassified_ |
| 4.3 | striker_balls | 14 | 15 | _unclassified_ |
| 4.3 | bowler_name | — | Tyagi | F-B-ad-occlusion |
| 4.3 | bowler_overs | — | 0.3 | F-A-commit-lag |
| 4.3 | bowler_runs | 0 | 5 | _unclassified_ |
| 4.4 | non_striker_balls | 15 | 16 | _unclassified_ |
| 4.4 | bowler_name | — | Tyagi | F-B-ad-occlusion |
| 4.4 | bowler_overs | — | 0.4 | F-A-commit-lag |
| 4.4 | bowler_runs | 0 | 6 | _unclassified_ |
| 4.5 | non_striker_balls | 15 | 16 | _unclassified_ |
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
| 5.1 | fow_entries | [[69, 1, "Rahul", "4.6"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 5.2 | striker_name | Rahul | — | D-post-FoW-striker |
| 5.2 | striker_runs | 23 | 0 | _unclassified_ |
| 5.2 | striker_balls | 13 | 0 | _unclassified_ |
| 5.2 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 5.2 | bowler_name | — | Arora | F-B-ad-occlusion |
| 5.2 | bowler_overs | — | 1.2 | F-A-commit-lag |
| 5.2 | bowler_runs | 0 | 15 | _unclassified_ |
| 5.2 | fow_entries | [[69, 1, "Rahul", "4.6"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 6.1 | non_striker_name | Rahul | Rana | _unclassified_ |
| 6.1 | non_striker_runs | 23 | 2 | _unclassified_ |
| 6.1 | non_striker_balls | 13 | 5 | _unclassified_ |
| 6.1 | non_striker_fours | 4 | 0 | _unclassified_ |
| 6.1 | recent_over_n_minus_1 | [] | ["4", "1", ".", ".", ".", "1"] | Recent-overs-drop |
| 6.1 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 6.2 | non_striker_name | Rahul | Rana | _unclassified_ |
| 6.2 | non_striker_runs | 23 | 2 | _unclassified_ |
| 6.2 | non_striker_balls | 13 | 5 | _unclassified_ |
| 6.2 | non_striker_fours | 4 | 0 | _unclassified_ |
| 6.2 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 6.3 | striker_name | Rahul | Rana | D-post-FoW-striker |
| 6.3 | striker_runs | 23 | 2 | _unclassified_ |
| 6.3 | striker_balls | 13 | 5 | _unclassified_ |
| 6.3 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 6.3 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 6.4 | non_striker_name | Rahul | Rana | _unclassified_ |
| 6.4 | non_striker_runs | 23 | 3 | _unclassified_ |
| 6.4 | non_striker_balls | 13 | 6 | _unclassified_ |
| 6.4 | non_striker_fours | 4 | 0 | _unclassified_ |
| 6.4 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 6.5 | non_striker_name | Rahul | Rana | _unclassified_ |
| 6.5 | non_striker_runs | 23 | 3 | _unclassified_ |
| 6.5 | non_striker_balls | 13 | 6 | _unclassified_ |
| 6.5 | non_striker_fours | 4 | 0 | _unclassified_ |
| 6.5 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 6.6 | score | 59 | 62 | _unclassified_ |
| 6.6 | striker_name | Nissanka | Rana | D-post-FoW-striker |
| 6.6 | striker_runs | 33 | 3 | _unclassified_ |
| 6.6 | striker_balls | 22 | 6 | _unclassified_ |
| 6.6 | striker_fours | 3 | 0 | _unclassified_ |
| 6.6 | striker_sixes | 2 | 0 | _unclassified_ |
| 6.6 | non_striker_name | Rahul | Nissanka | _unclassified_ |
| 6.6 | non_striker_runs | 23 | 36 | _unclassified_ |
| 6.6 | non_striker_balls | 13 | 22 | _unclassified_ |
| 6.6 | non_striker_sixes | 0 | 2 | _unclassified_ |
| 6.6 | bowler_name | — | Chakaravarthy | F-B-ad-occlusion |
| 6.6 | bowler_overs | — | 1.0 | F-A-commit-lag |
| 6.6 | bowler_runs | 0 | 7 | _unclassified_ |
| 6.6 | this_over_tokens | ["1", ".", "1", "1", ".", "1"] | ["1", ".", "1", "1", ".", "4"] | _unclassified_ |
| 6.6 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 7.1 | striker_name | Rahul | Nissanka | D-post-FoW-striker |
| 7.1 | striker_runs | 23 | 36 | _unclassified_ |
| 7.1 | striker_balls | 13 | 22 | _unclassified_ |
| 7.1 | striker_sixes | 0 | 2 | _unclassified_ |
| 7.1 | non_striker_name | Nissanka | Rana | _unclassified_ |
| 7.1 | non_striker_runs | 34 | 4 | _unclassified_ |
| 7.1 | non_striker_balls | 23 | 7 | _unclassified_ |
| 7.1 | non_striker_fours | 3 | 0 | _unclassified_ |
| 7.1 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 7.1 | bowler_name | — | Green | F-B-ad-occlusion |
| 7.1 | bowler_overs | — | 0.1 | F-A-commit-lag |
| 7.1 | bowler_runs | 0 | 1 | _unclassified_ |
| 7.1 | this_over_tokens | ["Wd", "1"] | ["1"] | _unclassified_ |
| 7.1 | recent_over_n_minus_1 | [] | ["1", ".", "1", "1", ".", "4"] | Recent-overs-drop |
| 7.1 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 7.2 | striker_name | Rahul | Nissanka | D-post-FoW-striker |
| 7.2 | striker_runs | 23 | 42 | _unclassified_ |
| 7.2 | striker_balls | 13 | 23 | _unclassified_ |
| 7.2 | striker_sixes | 0 | 3 | _unclassified_ |
| 7.2 | non_striker_name | Nissanka | Rana | _unclassified_ |
| 7.2 | non_striker_runs | 34 | 4 | _unclassified_ |
| 7.2 | non_striker_balls | 23 | 7 | _unclassified_ |
| 7.2 | non_striker_fours | 3 | 0 | _unclassified_ |
| 7.2 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 7.2 | bowler_name | — | Green | F-B-ad-occlusion |
| 7.2 | bowler_overs | — | 0.2 | F-A-commit-lag |
| 7.2 | bowler_runs | 0 | 7 | _unclassified_ |
| 7.2 | this_over_tokens | ["Wd", "1", "6"] | ["1", "6"] | _unclassified_ |
| 7.2 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 7.3 | striker_name | Nissanka | Rana | D-post-FoW-striker |
| 7.3 | striker_runs | 35 | 4 | _unclassified_ |
| 7.3 | striker_balls | 24 | 7 | _unclassified_ |
| 7.3 | striker_fours | 3 | 0 | Boundary-counter-double-increment |
| 7.3 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 7.3 | non_striker_name | Rahul | Nissanka | _unclassified_ |
| 7.3 | non_striker_runs | 23 | 43 | _unclassified_ |
| 7.3 | non_striker_balls | 13 | 24 | _unclassified_ |
| 7.3 | non_striker_sixes | 0 | 3 | _unclassified_ |
| 7.3 | this_over_tokens | ["Wd", "1", "6", "1"] | ["1", "6", "1"] | _unclassified_ |
| 7.3 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 7.4 | striker_name | Nissanka | Rana | D-post-FoW-striker |
| 7.4 | striker_runs | 39 | 8 | _unclassified_ |
| 7.4 | striker_balls | 25 | 8 | _unclassified_ |
| 7.4 | striker_fours | 4 | 1 | Boundary-counter-double-increment |
| 7.4 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 7.4 | non_striker_name | Rahul | Nissanka | _unclassified_ |
| 7.4 | non_striker_runs | 23 | 43 | _unclassified_ |
| 7.4 | non_striker_balls | 13 | 24 | _unclassified_ |
| 7.4 | non_striker_sixes | 0 | 3 | _unclassified_ |
| 7.4 | this_over_tokens | ["Wd", "1", "6", "1", "4"] | ["1", "6", "1", "4"] | _unclassified_ |
| 7.4 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 7.5 | striker_name | Nissanka | Rana | D-post-FoW-striker |
| 7.5 | striker_runs | 39 | 8 | _unclassified_ |
| 7.5 | striker_balls | 26 | 9 | _unclassified_ |
| 7.5 | striker_fours | 4 | 1 | Boundary-counter-double-increment |
| 7.5 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 7.5 | non_striker_name | Rahul | Nissanka | _unclassified_ |
| 7.5 | non_striker_runs | 23 | 43 | _unclassified_ |
| 7.5 | non_striker_balls | 13 | 24 | _unclassified_ |
| 7.5 | non_striker_sixes | 0 | 3 | _unclassified_ |
| 7.5 | this_over_tokens | ["Wd", "1", "6", "1", "4", "."] | ["1", "6", "1", "4", "."] | _unclassified_ |
| 7.5 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 8.1 | striker_name | Nissanka | — | D-post-FoW-striker |
| 8.1 | striker_runs | 39 | 0 | _unclassified_ |
| 8.1 | striker_balls | 27 | 0 | _unclassified_ |
| 8.1 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 8.1 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 8.1 | non_striker_name | Rahul | Nissanka | _unclassified_ |
| 8.1 | non_striker_runs | 23 | 44 | _unclassified_ |
| 8.1 | non_striker_balls | 13 | 25 | _unclassified_ |
| 8.1 | non_striker_sixes | 0 | 3 | _unclassified_ |
| 8.1 | bowler_name | — | Chakaravarthy | F-B-ad-occlusion |
| 8.1 | bowler_overs | — | 1.1 | F-A-commit-lag |
| 8.1 | bowler_runs | 0 | 8 | _unclassified_ |
| 8.1 | recent_over_n_minus_1 | [] | ["1", "6", "1", "4", ".", "W"] | Recent-overs-drop |
| 8.1 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"]] | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"]] | E3-wicket-frame-misalign |
| 8.2 | striker_name | Nissanka | Rizvi | D-post-FoW-striker |
| 8.2 | striker_runs | 39 | 0 | _unclassified_ |
| 8.2 | striker_balls | 28 | 1 | _unclassified_ |
| 8.2 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 8.2 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 8.2 | non_striker_name | Rahul | Nissanka | _unclassified_ |
| 8.2 | non_striker_runs | 23 | 44 | _unclassified_ |
| 8.2 | non_striker_balls | 13 | 25 | _unclassified_ |
| 8.2 | non_striker_sixes | 0 | 3 | _unclassified_ |
| 8.2 | bowler_runs | 5 | 8 | _unclassified_ |
| 8.2 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"]] | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"]] | E3-wicket-frame-misalign |
| 8.3 | striker_name | Nissanka | Rizvi | D-post-FoW-striker |
| 8.3 | striker_runs | 39 | 0 | _unclassified_ |
| 8.3 | striker_balls | 29 | 2 | _unclassified_ |
| 8.3 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 8.3 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 8.3 | non_striker_name | Rahul | Nissanka | _unclassified_ |
| 8.3 | non_striker_runs | 23 | 44 | _unclassified_ |
| 8.3 | non_striker_balls | 13 | 25 | _unclassified_ |
| 8.3 | non_striker_sixes | 0 | 3 | _unclassified_ |
| 8.3 | bowler_runs | 5 | 8 | _unclassified_ |
| 8.3 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"]] | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"]] | E3-wicket-frame-misalign |
| 8.4 | striker_name | Rahul | Nissanka | D-post-FoW-striker |
| 8.4 | striker_runs | 23 | 44 | _unclassified_ |
| 8.4 | striker_balls | 13 | 25 | _unclassified_ |
| 8.4 | striker_sixes | 0 | 3 | _unclassified_ |
| 8.4 | non_striker_name | Nissanka | Rizvi | _unclassified_ |
| 8.4 | non_striker_runs | 40 | 1 | _unclassified_ |
| 8.4 | non_striker_balls | 30 | 3 | _unclassified_ |
| 8.4 | non_striker_fours | 4 | 0 | _unclassified_ |
| 8.4 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 8.4 | bowler_runs | 6 | 9 | _unclassified_ |
| 8.4 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"]] | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"]] | E3-wicket-frame-misalign |
| 8.5 | striker_name | Nissanka | Rizvi | D-post-FoW-striker |
| 8.5 | striker_runs | 40 | 1 | _unclassified_ |
| 8.5 | striker_balls | 30 | 3 | _unclassified_ |
| 8.5 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 8.5 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 8.5 | non_striker_name | Rahul | Nissanka | _unclassified_ |
| 8.5 | non_striker_runs | 23 | 45 | _unclassified_ |
| 8.5 | non_striker_balls | 13 | 26 | _unclassified_ |
| 8.5 | non_striker_sixes | 0 | 3 | _unclassified_ |
| 8.5 | bowler_runs | 7 | 10 | _unclassified_ |
| 8.5 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"]] | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"]] | E3-wicket-frame-misalign |
| 9.1 | striker_name | Rahul | Nissanka | D-post-FoW-striker |
| 9.1 | striker_runs | 23 | 45 | _unclassified_ |
| 9.1 | striker_balls | 13 | 27 | _unclassified_ |
| 9.1 | striker_sixes | 0 | 3 | _unclassified_ |
| 9.1 | non_striker_name | Nissanka | Rizvi | _unclassified_ |
| 9.1 | non_striker_runs | 40 | 1 | _unclassified_ |
| 9.1 | non_striker_balls | 31 | 4 | _unclassified_ |
| 9.1 | non_striker_fours | 4 | 0 | _unclassified_ |
| 9.1 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 9.1 | bowler_name | — | Narine | F-B-ad-occlusion |
| 9.1 | bowler_overs | — | 1.1 | F-A-commit-lag |
| 9.1 | bowler_runs | 0 | 11 | _unclassified_ |
| 9.1 | recent_over_n_minus_1 | [] | ["1", ".", ".", "1", "1", "."] | Recent-overs-drop |
| 9.1 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"]] | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"]] | E3-wicket-frame-misalign |
| 9.2 | striker_name | Nissanka | Rizvi | D-post-FoW-striker |
| 9.2 | striker_runs | 40 | 1 | _unclassified_ |
| 9.2 | striker_balls | 31 | 4 | _unclassified_ |
| 9.2 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 9.2 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 9.2 | non_striker_name | Rahul | Nissanka | _unclassified_ |
| 9.2 | non_striker_runs | 23 | 46 | _unclassified_ |
| 9.2 | non_striker_balls | 13 | 28 | _unclassified_ |
| 9.2 | non_striker_sixes | 0 | 3 | _unclassified_ |
| 9.2 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"]] | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"]] | E3-wicket-frame-misalign |
| 9.3 | striker_name | Nissanka | Rizvi | D-post-FoW-striker |
| 9.3 | striker_runs | 40 | 1 | _unclassified_ |
| 9.3 | striker_balls | 32 | 5 | _unclassified_ |
| 9.3 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 9.3 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 9.3 | non_striker_name | Rahul | Nissanka | _unclassified_ |
| 9.3 | non_striker_runs | 23 | 46 | _unclassified_ |
| 9.3 | non_striker_balls | 13 | 28 | _unclassified_ |
| 9.3 | non_striker_sixes | 0 | 3 | _unclassified_ |
| 9.3 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"]] | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"]] | E3-wicket-frame-misalign |
| 9.4 | striker_name | Nissanka | Rizvi | D-post-FoW-striker |
| 9.4 | striker_runs | 42 | 3 | _unclassified_ |
| 9.4 | striker_balls | 33 | 6 | _unclassified_ |
| 9.4 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 9.4 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 9.4 | non_striker_name | Rahul | Nissanka | _unclassified_ |
| 9.4 | non_striker_runs | 23 | 46 | _unclassified_ |
| 9.4 | non_striker_balls | 13 | 28 | _unclassified_ |
| 9.4 | non_striker_sixes | 0 | 3 | _unclassified_ |
| 9.4 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"]] | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"]] | E3-wicket-frame-misalign |
| 9.5 | striker_name | Nissanka | — | D-post-FoW-striker |
| 9.5 | striker_runs | 42 | 0 | _unclassified_ |
| 9.5 | striker_balls | 33 | 0 | _unclassified_ |
| 9.5 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 9.5 | striker_sixes | 2 | 0 | Boundary-counter-double-increment |
| 9.5 | non_striker_name | Rahul | Nissanka | _unclassified_ |
| 9.5 | non_striker_runs | 23 | 46 | _unclassified_ |
| 9.5 | non_striker_balls | 13 | 28 | _unclassified_ |
| 9.5 | non_striker_sixes | 0 | 3 | _unclassified_ |
| 9.5 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 9.5 | this_over_tokens | [".", "1", ".", "2", "."] | [".", "1", ".", "2", "W"] | C21b-symbol-revert |
| 9.5 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"]] | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 10.1 | striker_name | Rahul | Nissanka | D-post-FoW-striker |
| 10.1 | striker_runs | 23 | 50 | _unclassified_ |
| 10.1 | striker_balls | 13 | 29 | _unclassified_ |
| 10.1 | striker_fours | 4 | 5 | _unclassified_ |
| 10.1 | striker_sixes | 0 | 3 | _unclassified_ |
| 10.1 | non_striker_name | Nissanka | Stubbs | _unclassified_ |
| 10.1 | non_striker_runs | 42 | 0 | _unclassified_ |
| 10.1 | non_striker_balls | 33 | 1 | _unclassified_ |
| 10.1 | non_striker_fours | 4 | 0 | _unclassified_ |
| 10.1 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 10.1 | bowler_name | — | Roy | F-B-ad-occlusion |
| 10.1 | bowler_overs | — | 2.1 | F-A-commit-lag |
| 10.1 | bowler_runs | 0 | 22 | _unclassified_ |
| 10.1 | recent_over_n_minus_1 | [] | [".", "1", ".", "2", "W", "."] | Recent-overs-drop |
| 10.1 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"]] | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 10.2 | score | 87 | 85 | E2-phantom-runs |
| 10.2 | balls_total | 62 | 61 | _unclassified_ |
| 10.2 | striker_name | Rahul | — | D-post-FoW-striker |
| 10.2 | striker_runs | 23 | 0 | _unclassified_ |
| 10.2 | striker_balls | 13 | 0 | _unclassified_ |
| 10.2 | striker_fours | 4 | 0 | _unclassified_ |
| 10.2 | non_striker_name | Nissanka | Stubbs | _unclassified_ |
| 10.2 | non_striker_runs | 42 | 0 | _unclassified_ |
| 10.2 | non_striker_balls | 33 | 1 | _unclassified_ |
| 10.2 | non_striker_fours | 4 | 0 | _unclassified_ |
| 10.2 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 10.2 | bowler_name | — | Roy | F-B-ad-occlusion |
| 10.2 | bowler_overs | — | 2.1 | F-A-commit-lag |
| 10.2 | bowler_runs | 0 | 23 | _unclassified_ |
| 10.2 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 10.2 | extras_total | 0 | 1 | Extras-counter-drop |
| 10.2 | extras_wd | 0 | 1 | Extras-counter-drop |
| 10.2 | this_over_tokens | ["4", "Wd", "2"] | ["4", "Wd+W"] | Compound-with-wicket-token |
| 10.2 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"], [110, … | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 10.3 | striker_name | Rahul | Stubbs | D-post-FoW-striker |
| 10.3 | striker_runs | 23 | 2 | _unclassified_ |
| 10.3 | striker_balls | 13 | 2 | _unclassified_ |
| 10.3 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 10.3 | non_striker_name | Nissanka | Patel | _unclassified_ |
| 10.3 | non_striker_runs | 42 | 1 | _unclassified_ |
| 10.3 | non_striker_balls | 33 | 1 | _unclassified_ |
| 10.3 | non_striker_fours | 4 | 0 | _unclassified_ |
| 10.3 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 10.3 | bowler_name | — | Roy | F-B-ad-occlusion |
| 10.3 | bowler_overs | — | 2.3 | F-A-commit-lag |
| 10.3 | bowler_runs | 0 | 27 | _unclassified_ |
| 10.3 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 10.3 | extras_total | 0 | 2 | Extras-counter-drop |
| 10.3 | extras_wd | 0 | 2 | Extras-counter-drop |
| 10.3 | this_over_tokens | ["4", "Wd", "2", "2"] | ["4", "Wd+W", "Wd", "1", "2"] | Compound-with-wicket-token |
| 10.3 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"], [110, … | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 10.4 | striker_name | Rahul | Stubbs | D-post-FoW-striker |
| 10.4 | striker_runs | 23 | 2 | _unclassified_ |
| 10.4 | striker_balls | 13 | 3 | _unclassified_ |
| 10.4 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 10.4 | non_striker_name | Nissanka | Patel | _unclassified_ |
| 10.4 | non_striker_runs | 42 | 1 | _unclassified_ |
| 10.4 | non_striker_balls | 33 | 1 | _unclassified_ |
| 10.4 | non_striker_fours | 4 | 0 | _unclassified_ |
| 10.4 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 10.4 | bowler_overs | 2.2 | 2.4 | F-A-commit-lag |
| 10.4 | bowler_runs | 22 | 27 | _unclassified_ |
| 10.4 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 10.4 | extras_total | 0 | 2 | Extras-counter-drop |
| 10.4 | extras_wd | 0 | 2 | Extras-counter-drop |
| 10.4 | this_over_tokens | ["4", "Wd", "2", "2", "."] | ["4", "Wd+W", "Wd", "1", "2", "."] | Compound-with-wicket-token |
| 10.4 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"], [110, … | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 10.5 | striker_name | Rana | — | D-post-FoW-striker |
| 10.5 | striker_balls | 1 | 0 | _unclassified_ |
| 10.5 | non_striker_name | — | Patel | _unclassified_ |
| 10.5 | non_striker_runs | 0 | 1 | _unclassified_ |
| 10.5 | non_striker_balls | 0 | 1 | _unclassified_ |
| 10.5 | bowler_overs | 2.3 | 2.5 | F-A-commit-lag |
| 10.5 | bowler_runs | 22 | 27 | _unclassified_ |
| 10.5 | bowler_wickets | 1 | 2 | Bowler-W-credit-failure |
| 10.5 | extras_total | 0 | 2 | Extras-counter-drop |
| 10.5 | extras_wd | 0 | 2 | Extras-counter-drop |
| 10.5 | this_over_tokens | ["4", "Wd", "2", "2", ".", "."] | ["4", "Wd+W", "Wd", "1", "2", ".", "W"] | C21b-symbol-revert |
| 10.5 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"], [110, … | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 11.1 | striker_name | Rana | Patel | D-post-FoW-striker |
| 11.1 | striker_runs | 0 | 1 | _unclassified_ |
| 11.1 | non_striker_name | Rahul | Sharma | _unclassified_ |
| 11.1 | non_striker_runs | 23 | 0 | _unclassified_ |
| 11.1 | non_striker_balls | 13 | 1 | _unclassified_ |
| 11.1 | non_striker_fours | 4 | 0 | _unclassified_ |
| 11.1 | bowler_name | Roy | Narine | F-B-ad-occlusion |
| 11.1 | bowler_overs | 2.4 | 2.1 | F-A-commit-lag |
| 11.1 | bowler_runs | 22 | 14 | _unclassified_ |
| 11.1 | extras_total | 0 | 2 | Extras-counter-drop |
| 11.1 | extras_wd | 0 | 2 | Extras-counter-drop |
| 11.1 | recent_over_n_minus_1 | [] | ["4", "Wd+W", "Wd", "1", "2", ".", "W", "."] | Recent-overs-drop |
| 11.1 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"], [110, … | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 11.2 | striker_name | Rana | Patel | D-post-FoW-striker |
| 11.2 | striker_runs | 0 | 1 | _unclassified_ |
| 11.2 | non_striker_name | Rahul | Sharma | _unclassified_ |
| 11.2 | non_striker_runs | 23 | 0 | _unclassified_ |
| 11.2 | non_striker_balls | 13 | 1 | _unclassified_ |
| 11.2 | non_striker_fours | 4 | 0 | _unclassified_ |
| 11.2 | bowler_name | Roy | Narine | F-B-ad-occlusion |
| 11.2 | bowler_overs | 2.4 | 2.2 | F-A-commit-lag |
| 11.2 | bowler_runs | 22 | 14 | _unclassified_ |
| 11.2 | extras_total | 0 | 2 | Extras-counter-drop |
| 11.2 | extras_wd | 0 | 2 | Extras-counter-drop |
| 11.2 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"], [110, … | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 11.3 | striker_name | Rana | Patel | D-post-FoW-striker |
| 11.3 | striker_runs | 0 | 1 | _unclassified_ |
| 11.3 | non_striker_name | Rahul | Sharma | _unclassified_ |
| 11.3 | non_striker_runs | 23 | 0 | _unclassified_ |
| 11.3 | non_striker_balls | 13 | 1 | _unclassified_ |
| 11.3 | non_striker_fours | 4 | 0 | _unclassified_ |
| 11.3 | bowler_name | Roy | Narine | F-B-ad-occlusion |
| 11.3 | bowler_overs | 2.4 | 2.3 | F-A-commit-lag |
| 11.3 | bowler_runs | 22 | 14 | _unclassified_ |
| 11.3 | extras_total | 0 | 2 | Extras-counter-drop |
| 11.3 | extras_wd | 0 | 2 | Extras-counter-drop |
| 11.3 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"], [110, … | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 11.4 | striker_name | Rana | Patel | D-post-FoW-striker |
| 11.4 | striker_runs | 0 | 1 | _unclassified_ |
| 11.4 | non_striker_name | Rahul | Sharma | _unclassified_ |
| 11.4 | non_striker_runs | 23 | 0 | _unclassified_ |
| 11.4 | non_striker_balls | 13 | 1 | _unclassified_ |
| 11.4 | non_striker_fours | 4 | 0 | _unclassified_ |
| 11.4 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 11.4 | extras_total | 0 | 2 | Extras-counter-drop |
| 11.4 | extras_wd | 0 | 2 | Extras-counter-drop |
| 11.4 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"], [110, … | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 11.5 | striker_name | Rahul | Sharma | D-post-FoW-striker |
| 11.5 | striker_runs | 23 | 0 | _unclassified_ |
| 11.5 | striker_balls | 13 | 1 | _unclassified_ |
| 11.5 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 11.5 | non_striker_name | Rana | Patel | _unclassified_ |
| 11.5 | non_striker_runs | 1 | 2 | _unclassified_ |
| 11.5 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 11.5 | extras_total | 0 | 2 | Extras-counter-drop |
| 11.5 | extras_wd | 0 | 2 | Extras-counter-drop |
| 11.5 | fow_entries | [[69, 1, "Rahul", "4.6"], [69, 3, "Rahul", "5.2"], [110, … | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |

## 3. Conservation invariants

All conservation checks passed.

## 4. Unclassified divergences

| over.ball | field | pipeline | ground-truth |
|---|---|---|---|
| 0.1 | striker_name | — | Nissanka |
| 0.1 | striker_balls | 0 | 1 |
| 0.2 | striker_balls | 1 | 2 |
| 0.2 | non_striker_name | Rahul | — |
| 0.3 | striker_name | Rahul | — |
| 0.3 | non_striker_balls | 2 | 3 |
| 0.4 | non_striker_balls | 2 | 3 |
| 0.5 | striker_balls | 2 | 3 |
| 0.6 | striker_balls | 3 | 4 |
| 0.6 | bowler_runs | 0 | 7 |
| 1.1 | striker_balls | 4 | 5 |
| 1.2 | non_striker_balls | 5 | 6 |
| 1.3 | striker_balls | 5 | 6 |
| 1.4 | striker_balls | 6 | 7 |
| 1.5 | non_striker_balls | 7 | 8 |
| 1.6 | non_striker_balls | 7 | 8 |
| 1.6 | bowler_runs | 0 | 10 |
| 2.1 | non_striker_balls | 7 | 8 |
| 2.2 | non_striker_balls | 7 | 8 |
| 2.3 | striker_balls | 7 | 8 |
| 2.4 | striker_balls | 8 | 9 |
| 2.5 | striker_balls | 9 | 10 |
| 3.1 | striker_balls | 10 | 11 |
| 3.1 | bowler_runs | 0 | 1 |
| 3.2 | striker_balls | 11 | 12 |
| 3.3 | striker_balls | 12 | 13 |
| 3.4 | non_striker_balls | 13 | 14 |
| 3.5 | non_striker_balls | 13 | 14 |
| 3.6 | non_striker_balls | 13 | 14 |
| 3.6 | bowler_runs | 0 | 11 |
| 4.1 | non_striker_balls | 13 | 14 |
| 4.1 | bowler_runs | 0 | 4 |
| 4.2 | striker_balls | 13 | 14 |
| 4.2 | bowler_runs | 0 | 5 |
| 4.3 | striker_balls | 14 | 15 |
| 4.3 | bowler_runs | 0 | 5 |
| 4.4 | non_striker_balls | 15 | 16 |
| 4.4 | bowler_runs | 0 | 6 |
| 4.5 | non_striker_balls | 15 | 16 |
| 4.5 | bowler_runs | 0 | 10 |
| 5.1 | non_striker_name | Rahul | — |
| 5.1 | non_striker_runs | 23 | 0 |
| 5.1 | non_striker_balls | 13 | 0 |
| 5.1 | non_striker_fours | 4 | 0 |
| 5.1 | bowler_runs | 0 | 14 |
| 5.2 | striker_runs | 23 | 0 |
| 5.2 | striker_balls | 13 | 0 |
| 5.2 | bowler_runs | 0 | 15 |
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
| 6.4 | non_striker_name | Rahul | Rana |
| 6.4 | non_striker_runs | 23 | 3 |
| 6.4 | non_striker_balls | 13 | 6 |
| 6.4 | non_striker_fours | 4 | 0 |
| 6.5 | non_striker_name | Rahul | Rana |
| 6.5 | non_striker_runs | 23 | 3 |
| 6.5 | non_striker_balls | 13 | 6 |
| 6.5 | non_striker_fours | 4 | 0 |
| 6.6 | score | 59 | 62 |
| 6.6 | striker_runs | 33 | 3 |
| 6.6 | striker_balls | 22 | 6 |
| 6.6 | striker_fours | 3 | 0 |
| 6.6 | striker_sixes | 2 | 0 |
| 6.6 | non_striker_name | Rahul | Nissanka |
| 6.6 | non_striker_runs | 23 | 36 |
| 6.6 | non_striker_balls | 13 | 22 |
| 6.6 | non_striker_sixes | 0 | 2 |
| 6.6 | bowler_runs | 0 | 7 |
| 6.6 | this_over_tokens | ["1", ".", "1", "1", ".", "1"] | ["1", ".", "1", "1", ".", "4"] |
| 7.1 | striker_runs | 23 | 36 |
| 7.1 | striker_balls | 13 | 22 |
| 7.1 | striker_sixes | 0 | 2 |
| 7.1 | non_striker_name | Nissanka | Rana |
| 7.1 | non_striker_runs | 34 | 4 |
| 7.1 | non_striker_balls | 23 | 7 |
| 7.1 | non_striker_fours | 3 | 0 |
| 7.1 | non_striker_sixes | 2 | 0 |
| 7.1 | bowler_runs | 0 | 1 |
| 7.1 | this_over_tokens | ["Wd", "1"] | ["1"] |
| 7.2 | striker_runs | 23 | 42 |
| 7.2 | striker_balls | 13 | 23 |
| 7.2 | striker_sixes | 0 | 3 |
| 7.2 | non_striker_name | Nissanka | Rana |
| 7.2 | non_striker_runs | 34 | 4 |
| 7.2 | non_striker_balls | 23 | 7 |
| 7.2 | non_striker_fours | 3 | 0 |
| 7.2 | non_striker_sixes | 2 | 0 |
| 7.2 | bowler_runs | 0 | 7 |
| 7.2 | this_over_tokens | ["Wd", "1", "6"] | ["1", "6"] |
| 7.3 | striker_runs | 35 | 4 |
| 7.3 | striker_balls | 24 | 7 |
| 7.3 | non_striker_name | Rahul | Nissanka |
| 7.3 | non_striker_runs | 23 | 43 |
| 7.3 | non_striker_balls | 13 | 24 |
| 7.3 | non_striker_sixes | 0 | 3 |
| 7.3 | this_over_tokens | ["Wd", "1", "6", "1"] | ["1", "6", "1"] |
| 7.4 | striker_runs | 39 | 8 |
| 7.4 | striker_balls | 25 | 8 |
| 7.4 | non_striker_name | Rahul | Nissanka |
| 7.4 | non_striker_runs | 23 | 43 |
| 7.4 | non_striker_balls | 13 | 24 |
| 7.4 | non_striker_sixes | 0 | 3 |
| 7.4 | this_over_tokens | ["Wd", "1", "6", "1", "4"] | ["1", "6", "1", "4"] |
| 7.5 | striker_runs | 39 | 8 |
| 7.5 | striker_balls | 26 | 9 |
| 7.5 | non_striker_name | Rahul | Nissanka |
| 7.5 | non_striker_runs | 23 | 43 |
| 7.5 | non_striker_balls | 13 | 24 |
| 7.5 | non_striker_sixes | 0 | 3 |
| 7.5 | this_over_tokens | ["Wd", "1", "6", "1", "4", "."] | ["1", "6", "1", "4", "."] |
| 8.1 | striker_runs | 39 | 0 |
| 8.1 | striker_balls | 27 | 0 |
| 8.1 | non_striker_name | Rahul | Nissanka |
| 8.1 | non_striker_runs | 23 | 44 |
| 8.1 | non_striker_balls | 13 | 25 |
| 8.1 | non_striker_sixes | 0 | 3 |
| 8.1 | bowler_runs | 0 | 8 |
| 8.2 | striker_runs | 39 | 0 |
| 8.2 | striker_balls | 28 | 1 |
| 8.2 | non_striker_name | Rahul | Nissanka |
| 8.2 | non_striker_runs | 23 | 44 |
| 8.2 | non_striker_balls | 13 | 25 |
| 8.2 | non_striker_sixes | 0 | 3 |
| 8.2 | bowler_runs | 5 | 8 |
| 8.3 | striker_runs | 39 | 0 |
| 8.3 | striker_balls | 29 | 2 |
| 8.3 | non_striker_name | Rahul | Nissanka |
| 8.3 | non_striker_runs | 23 | 44 |
| 8.3 | non_striker_balls | 13 | 25 |
| 8.3 | non_striker_sixes | 0 | 3 |
| 8.3 | bowler_runs | 5 | 8 |
| 8.4 | striker_runs | 23 | 44 |
| 8.4 | striker_balls | 13 | 25 |
| 8.4 | striker_sixes | 0 | 3 |
| 8.4 | non_striker_name | Nissanka | Rizvi |
| 8.4 | non_striker_runs | 40 | 1 |
| 8.4 | non_striker_balls | 30 | 3 |
| 8.4 | non_striker_fours | 4 | 0 |
| 8.4 | non_striker_sixes | 2 | 0 |
| 8.4 | bowler_runs | 6 | 9 |
| 8.5 | striker_runs | 40 | 1 |
| 8.5 | striker_balls | 30 | 3 |
| 8.5 | non_striker_name | Rahul | Nissanka |
| 8.5 | non_striker_runs | 23 | 45 |
| 8.5 | non_striker_balls | 13 | 26 |
| 8.5 | non_striker_sixes | 0 | 3 |
| 8.5 | bowler_runs | 7 | 10 |
| 9.1 | striker_runs | 23 | 45 |
| 9.1 | striker_balls | 13 | 27 |
| 9.1 | striker_sixes | 0 | 3 |
| 9.1 | non_striker_name | Nissanka | Rizvi |
| 9.1 | non_striker_runs | 40 | 1 |
| 9.1 | non_striker_balls | 31 | 4 |
| 9.1 | non_striker_fours | 4 | 0 |
| 9.1 | non_striker_sixes | 2 | 0 |
| 9.1 | bowler_runs | 0 | 11 |
| 9.2 | striker_runs | 40 | 1 |
| 9.2 | striker_balls | 31 | 4 |
| 9.2 | non_striker_name | Rahul | Nissanka |
| 9.2 | non_striker_runs | 23 | 46 |
| 9.2 | non_striker_balls | 13 | 28 |
| 9.2 | non_striker_sixes | 0 | 3 |
| 9.3 | striker_runs | 40 | 1 |
| 9.3 | striker_balls | 32 | 5 |
| 9.3 | non_striker_name | Rahul | Nissanka |
| 9.3 | non_striker_runs | 23 | 46 |
| 9.3 | non_striker_balls | 13 | 28 |
| 9.3 | non_striker_sixes | 0 | 3 |
| 9.4 | striker_runs | 42 | 3 |
| 9.4 | striker_balls | 33 | 6 |
| 9.4 | non_striker_name | Rahul | Nissanka |
| 9.4 | non_striker_runs | 23 | 46 |
| 9.4 | non_striker_balls | 13 | 28 |
| 9.4 | non_striker_sixes | 0 | 3 |
| 9.5 | striker_runs | 42 | 0 |
| 9.5 | striker_balls | 33 | 0 |
| 9.5 | non_striker_name | Rahul | Nissanka |
| 9.5 | non_striker_runs | 23 | 46 |
| 9.5 | non_striker_balls | 13 | 28 |
| 9.5 | non_striker_sixes | 0 | 3 |
| 10.1 | striker_runs | 23 | 50 |
| 10.1 | striker_balls | 13 | 29 |
| 10.1 | striker_fours | 4 | 5 |
| 10.1 | striker_sixes | 0 | 3 |
| 10.1 | non_striker_name | Nissanka | Stubbs |
| 10.1 | non_striker_runs | 42 | 0 |
| 10.1 | non_striker_balls | 33 | 1 |
| 10.1 | non_striker_fours | 4 | 0 |
| 10.1 | non_striker_sixes | 2 | 0 |
| 10.1 | bowler_runs | 0 | 22 |
| 10.2 | balls_total | 62 | 61 |
| 10.2 | striker_runs | 23 | 0 |
| 10.2 | striker_balls | 13 | 0 |
| 10.2 | striker_fours | 4 | 0 |
| 10.2 | non_striker_name | Nissanka | Stubbs |
| 10.2 | non_striker_runs | 42 | 0 |
| 10.2 | non_striker_balls | 33 | 1 |
| 10.2 | non_striker_fours | 4 | 0 |
| 10.2 | non_striker_sixes | 2 | 0 |
| 10.2 | bowler_runs | 0 | 23 |
| 10.3 | striker_runs | 23 | 2 |
| 10.3 | striker_balls | 13 | 2 |
| 10.3 | non_striker_name | Nissanka | Patel |
| 10.3 | non_striker_runs | 42 | 1 |
| 10.3 | non_striker_balls | 33 | 1 |
| 10.3 | non_striker_fours | 4 | 0 |
| 10.3 | non_striker_sixes | 2 | 0 |
| 10.3 | bowler_runs | 0 | 27 |
| 10.4 | striker_runs | 23 | 2 |
| 10.4 | striker_balls | 13 | 3 |
| 10.4 | non_striker_name | Nissanka | Patel |
| 10.4 | non_striker_runs | 42 | 1 |
| 10.4 | non_striker_balls | 33 | 1 |
| 10.4 | non_striker_fours | 4 | 0 |
| 10.4 | non_striker_sixes | 2 | 0 |
| 10.4 | bowler_runs | 22 | 27 |
| 10.5 | striker_balls | 1 | 0 |
| 10.5 | non_striker_name | — | Patel |
| 10.5 | non_striker_runs | 0 | 1 |
| 10.5 | non_striker_balls | 0 | 1 |
| 10.5 | bowler_runs | 22 | 27 |
| 11.1 | striker_runs | 0 | 1 |
| 11.1 | non_striker_name | Rahul | Sharma |
| 11.1 | non_striker_runs | 23 | 0 |
| 11.1 | non_striker_balls | 13 | 1 |
| 11.1 | non_striker_fours | 4 | 0 |
| 11.1 | bowler_runs | 22 | 14 |
| 11.2 | striker_runs | 0 | 1 |
| 11.2 | non_striker_name | Rahul | Sharma |
| 11.2 | non_striker_runs | 23 | 0 |
| 11.2 | non_striker_balls | 13 | 1 |
| 11.2 | non_striker_fours | 4 | 0 |
| 11.2 | bowler_runs | 22 | 14 |
| 11.3 | striker_runs | 0 | 1 |
| 11.3 | non_striker_name | Rahul | Sharma |
| 11.3 | non_striker_runs | 23 | 0 |
| 11.3 | non_striker_balls | 13 | 1 |
| 11.3 | non_striker_fours | 4 | 0 |
| 11.3 | bowler_runs | 22 | 14 |
| 11.4 | striker_runs | 0 | 1 |
| 11.4 | non_striker_name | Rahul | Sharma |
| 11.4 | non_striker_runs | 23 | 0 |
| 11.4 | non_striker_balls | 13 | 1 |
| 11.4 | non_striker_fours | 4 | 0 |
| 11.5 | striker_runs | 23 | 0 |
| 11.5 | striker_balls | 13 | 1 |
| 11.5 | non_striker_name | Rana | Patel |
| 11.5 | non_striker_runs | 1 | 2 |

## 5. Missing / phantom balls

- Missing-in-pipeline (61): 2.6, 4.6, 5.3, 5.4, 5.5, 5.6, 7.6, 8.6, 9.6, 10.2#1, 10.2#2, 10.6, 11.6, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 19.1, 19.2, 19.3, 19.4, 19.5, 19.6
- Phantom-in-pipeline (5): 4.5#1, 6.6#1, 6.6#2, 10.1#1, 10.1#2
