# Differential diff report

- Pipeline: `/tmp/dckkr_pipeline_snapshots_wsi.jsonl`
- Ground truth: `/tmp/dckkr_gt_full.jsonl`
- Matched balls: 61 | missing-in-pipeline: 61 | phantom-in-pipeline: 6 | total divergences: 475

## 1. Per-surface incident counts

| Surface | Count | First example (over.ball) |
|---|---|---|
| G-pipeline-lag | 61 | 4.6 |
| F-A-commit-lag | 50 | 0.1 |
| E3-wicket-frame-misalign | 32 | 5.1 |
| F-B-ad-occlusion | 27 | 0.6 |
| D-post-FoW-striker | 20 | 5.2 |
| Per-batter-ledger-drift | 17 | 6.1 |
| Extras-counter-drop | 16 | 10.2 |
| Boundary-counter-double-increment | 10 | 0.6 |
| Recent-overs-drop | 10 | 1.1 |
| Bowler-W-credit-failure | 7 | 7.6 |
| Multi-ball-compression | 4 | 5.6 |
| Silent-wicket-absorption | 2 | 4.6 |
| Compound-with-wicket-token | 2 | 10.2 |
| E2-phantom-runs | 1 | 10.2 |
| C21b-symbol-revert | 1 | 10.5 |

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
| 0.6 | striker_name | Nissanka | Rahul | _unclassified_ |
| 0.6 | striker_runs | 6 | 1 | _unclassified_ |
| 0.6 | striker_balls | 3 | 2 | _unclassified_ |
| 0.6 | striker_fours | 1 | 0 | Boundary-counter-double-increment |
| 0.6 | non_striker_name | Rahul | Nissanka | _unclassified_ |
| 0.6 | non_striker_runs | 1 | 6 | _unclassified_ |
| 0.6 | non_striker_balls | 2 | 4 | _unclassified_ |
| 0.6 | non_striker_fours | 0 | 1 | _unclassified_ |
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
| 1.6 | striker_name | Rahul | Nissanka | _unclassified_ |
| 1.6 | striker_runs | 3 | 14 | _unclassified_ |
| 1.6 | striker_balls | 4 | 8 | _unclassified_ |
| 1.6 | striker_fours | 0 | 1 | _unclassified_ |
| 1.6 | striker_sixes | 0 | 1 | _unclassified_ |
| 1.6 | non_striker_name | Nissanka | Rahul | _unclassified_ |
| 1.6 | non_striker_runs | 14 | 3 | _unclassified_ |
| 1.6 | non_striker_balls | 7 | 4 | _unclassified_ |
| 1.6 | non_striker_fours | 1 | 0 | _unclassified_ |
| 1.6 | non_striker_sixes | 1 | 0 | _unclassified_ |
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
| 2.6 | striker_name | Rahul | Nissanka | _unclassified_ |
| 2.6 | striker_runs | 8 | 20 | _unclassified_ |
| 2.6 | striker_balls | 7 | 11 | _unclassified_ |
| 2.6 | striker_sixes | 0 | 2 | _unclassified_ |
| 2.6 | non_striker_name | Nissanka | Rahul | _unclassified_ |
| 2.6 | non_striker_runs | 20 | 8 | _unclassified_ |
| 2.6 | non_striker_balls | 10 | 7 | _unclassified_ |
| 2.6 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 2.6 | bowler_name | — | Roy | F-B-ad-occlusion |
| 2.6 | bowler_overs | — | 2.0 | F-A-commit-lag |
| 2.6 | bowler_runs | 0 | 18 | _unclassified_ |
| 3.1 | striker_balls | 10 | 11 | _unclassified_ |
| 3.1 | bowler_name | — | Narine | F-B-ad-occlusion |
| 3.1 | bowler_overs | — | 0.1 | F-A-commit-lag |
| 3.1 | bowler_runs | 0 | 1 | _unclassified_ |
| 3.1 | recent_over_n_minus_1 | [] | [".", "4", "1", ".", ".", "6"] | Recent-overs-drop |
| 3.2 | striker_balls | 11 | 12 | _unclassified_ |
| 3.3 | striker_balls | 12 | 13 | _unclassified_ |
| 3.4 | non_striker_balls | 13 | 14 | _unclassified_ |
| 3.5 | non_striker_balls | 13 | 14 | _unclassified_ |
| 3.6 | striker_name | Rahul | Nissanka | _unclassified_ |
| 3.6 | striker_runs | 14 | 25 | _unclassified_ |
| 3.6 | striker_balls | 10 | 14 | _unclassified_ |
| 3.6 | striker_sixes | 0 | 2 | _unclassified_ |
| 3.6 | non_striker_name | Nissanka | Rahul | _unclassified_ |
| 3.6 | non_striker_runs | 25 | 14 | _unclassified_ |
| 3.6 | non_striker_balls | 13 | 10 | _unclassified_ |
| 3.6 | non_striker_sixes | 2 | 0 | _unclassified_ |
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
| 5.1 | striker_balls | 16 | 17 | _unclassified_ |
| 5.1 | non_striker_name | Rahul | — | _unclassified_ |
| 5.1 | non_striker_runs | 23 | 0 | _unclassified_ |
| 5.1 | non_striker_balls | 14 | 0 | _unclassified_ |
| 5.1 | non_striker_fours | 4 | 0 | _unclassified_ |
| 5.1 | bowler_name | — | Arora | F-B-ad-occlusion |
| 5.1 | bowler_overs | — | 1.1 | F-A-commit-lag |
| 5.1 | bowler_runs | 0 | 14 | _unclassified_ |
| 5.1 | recent_over_n_minus_1 | [] | ["4", "1", ".", "1", "4", "W"] | Recent-overs-drop |
| 5.1 | fow_entries | [] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 5.2 | striker_name | Rahul | — | D-post-FoW-striker |
| 5.2 | striker_runs | 23 | 0 | _unclassified_ |
| 5.2 | striker_balls | 14 | 0 | _unclassified_ |
| 5.2 | striker_fours | 4 | 0 | Boundary-counter-double-increment |
| 5.2 | non_striker_balls | 17 | 18 | _unclassified_ |
| 5.2 | bowler_name | — | Arora | F-B-ad-occlusion |
| 5.2 | bowler_overs | — | 1.2 | F-A-commit-lag |
| 5.2 | bowler_runs | 0 | 15 | _unclassified_ |
| 5.2 | fow_entries | [] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 5.6 | striker_name | — | Nissanka | D-post-FoW-striker |
| 5.6 | striker_runs | 0 | 31 | _unclassified_ |
| 5.6 | striker_balls | 0 | 18 | _unclassified_ |
| 5.6 | striker_fours | 0 | 3 | _unclassified_ |
| 5.6 | striker_sixes | 0 | 2 | _unclassified_ |
| 5.6 | non_striker_name | — | Rana | _unclassified_ |
| 5.6 | non_striker_runs | 0 | 1 | _unclassified_ |
| 5.6 | non_striker_balls | 0 | 4 | _unclassified_ |
| 5.6 | bowler_name | — | Arora | F-B-ad-occlusion |
| 5.6 | bowler_overs | — | 2.0 | F-A-commit-lag |
| 5.6 | bowler_runs | 0 | 16 | _unclassified_ |
| 5.6 | this_over_tokens | [] | ["4", "1", ".", ".", ".", "1"] | Multi-ball-compression |
| 5.6 | fow_entries | [] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 6.1 | striker_runs | 69 | 31 | _unclassified_ |
| 6.1 | striker_balls | 36 | 18 | _unclassified_ |
| 6.1 | non_striker_runs | 18 | 2 | _unclassified_ |
| 6.1 | non_striker_balls | 18 | 5 | _unclassified_ |
| 6.1 | bowler_overs | 6.1 | 0.1 | F-A-commit-lag |
| 6.1 | bowler_runs | 56 | 1 | _unclassified_ |
| 6.1 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | ["1"] | _unclassified_ |
| 6.1 | recent_over_n_minus_1 | [] | ["4", "1", ".", ".", ".", "1"] | Recent-overs-drop |
| 6.1 | fow_entries | [[0, 1, null, null]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 6.2 | striker_runs | 69 | 31 | _unclassified_ |
| 6.2 | striker_balls | 37 | 19 | _unclassified_ |
| 6.2 | non_striker_runs | 18 | 2 | _unclassified_ |
| 6.2 | non_striker_balls | 18 | 5 | _unclassified_ |
| 6.2 | bowler_overs | 6.2 | 0.2 | F-A-commit-lag |
| 6.2 | bowler_runs | 56 | 1 | _unclassified_ |
| 6.2 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | ["1", "."] | _unclassified_ |
| 6.2 | fow_entries | [[0, 1, null, null]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 6.3 | striker_runs | 18 | 2 | _unclassified_ |
| 6.3 | striker_balls | 18 | 5 | _unclassified_ |
| 6.3 | non_striker_runs | 70 | 32 | _unclassified_ |
| 6.3 | non_striker_balls | 38 | 20 | _unclassified_ |
| 6.3 | bowler_overs | 6.3 | 0.3 | F-A-commit-lag |
| 6.3 | bowler_runs | 57 | 2 | _unclassified_ |
| 6.3 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | ["1", ".", "1"] | _unclassified_ |
| 6.3 | fow_entries | [[0, 1, null, null]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 6.4 | striker_name | Rana | Nissanka | D-post-FoW-striker |
| 6.4 | striker_runs | 19 | 32 | _unclassified_ |
| 6.4 | striker_balls | 19 | 20 | _unclassified_ |
| 6.4 | striker_fours | 0 | 3 | _unclassified_ |
| 6.4 | striker_sixes | 0 | 2 | _unclassified_ |
| 6.4 | non_striker_name | Nissanka | Rana | _unclassified_ |
| 6.4 | non_striker_runs | 70 | 3 | _unclassified_ |
| 6.4 | non_striker_balls | 38 | 6 | _unclassified_ |
| 6.4 | non_striker_fours | 3 | 0 | _unclassified_ |
| 6.4 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 6.4 | bowler_overs | 6.4 | 0.4 | F-A-commit-lag |
| 6.4 | bowler_runs | 58 | 3 | _unclassified_ |
| 6.4 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | ["1", ".", "1", "1"] | _unclassified_ |
| 6.4 | fow_entries | [[0, 1, null, null]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 6.5 | striker_name | Rana | Nissanka | D-post-FoW-striker |
| 6.5 | striker_runs | 19 | 32 | _unclassified_ |
| 6.5 | striker_balls | 20 | 21 | _unclassified_ |
| 6.5 | striker_fours | 0 | 3 | _unclassified_ |
| 6.5 | striker_sixes | 0 | 2 | _unclassified_ |
| 6.5 | non_striker_name | Nissanka | Rana | _unclassified_ |
| 6.5 | non_striker_runs | 70 | 3 | _unclassified_ |
| 6.5 | non_striker_balls | 38 | 6 | _unclassified_ |
| 6.5 | non_striker_fours | 3 | 0 | _unclassified_ |
| 6.5 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 6.5 | bowler_overs | 6.5 | 0.5 | F-A-commit-lag |
| 6.5 | bowler_runs | 58 | 3 | _unclassified_ |
| 6.5 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | ["1", ".", "1", "1", "."] | _unclassified_ |
| 6.5 | fow_entries | [[0, 1, null, null]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 6.6 | score | 59 | 62 | _unclassified_ |
| 6.6 | striker_name | Rana | Nissanka | D-post-FoW-striker |
| 6.6 | striker_runs | 20 | 36 | _unclassified_ |
| 6.6 | striker_balls | 21 | 22 | _unclassified_ |
| 6.6 | striker_fours | 0 | 4 | _unclassified_ |
| 6.6 | striker_sixes | 0 | 2 | _unclassified_ |
| 6.6 | non_striker_name | Nissanka | Rana | _unclassified_ |
| 6.6 | non_striker_runs | 70 | 3 | _unclassified_ |
| 6.6 | non_striker_balls | 38 | 6 | _unclassified_ |
| 6.6 | non_striker_fours | 3 | 0 | _unclassified_ |
| 6.6 | non_striker_sixes | 2 | 0 | _unclassified_ |
| 6.6 | bowler_name | — | Chakaravarthy | F-B-ad-occlusion |
| 6.6 | bowler_overs | — | 1.0 | F-A-commit-lag |
| 6.6 | bowler_runs | 0 | 7 | _unclassified_ |
| 6.6 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | ["1", ".", "1", "1", ".", "4"] | _unclassified_ |
| 6.6 | fow_entries | [[0, 1, null, null]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 7.1 | striker_runs | 70 | 36 | _unclassified_ |
| 7.1 | striker_balls | 38 | 22 | _unclassified_ |
| 7.1 | striker_fours | 3 | 4 | _unclassified_ |
| 7.1 | non_striker_runs | 21 | 4 | _unclassified_ |
| 7.1 | non_striker_balls | 22 | 7 | _unclassified_ |
| 7.1 | bowler_name | — | Green | F-B-ad-occlusion |
| 7.1 | bowler_overs | — | 0.1 | F-A-commit-lag |
| 7.1 | bowler_runs | 0 | 1 | _unclassified_ |
| 7.1 | this_over_tokens | ["Wd", "1"] | ["1"] | _unclassified_ |
| 7.1 | recent_over_n_minus_1 | [] | ["1", ".", "1", "1", ".", "4"] | Recent-overs-drop |
| 7.1 | fow_entries | [[0, 1, null, null]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 7.2 | striker_runs | 76 | 42 | _unclassified_ |
| 7.2 | striker_balls | 39 | 23 | _unclassified_ |
| 7.2 | striker_fours | 3 | 4 | _unclassified_ |
| 7.2 | non_striker_runs | 21 | 4 | _unclassified_ |
| 7.2 | non_striker_balls | 22 | 7 | _unclassified_ |
| 7.2 | bowler_name | — | Green | F-B-ad-occlusion |
| 7.2 | bowler_overs | — | 0.2 | F-A-commit-lag |
| 7.2 | bowler_runs | 0 | 7 | _unclassified_ |
| 7.2 | this_over_tokens | ["Wd", "1", "6"] | ["1", "6"] | _unclassified_ |
| 7.2 | fow_entries | [[0, 1, null, null]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 7.3 | striker_runs | 21 | 4 | _unclassified_ |
| 7.3 | striker_balls | 22 | 7 | _unclassified_ |
| 7.3 | non_striker_runs | 77 | 43 | _unclassified_ |
| 7.3 | non_striker_balls | 40 | 24 | _unclassified_ |
| 7.3 | non_striker_fours | 3 | 4 | _unclassified_ |
| 7.3 | this_over_tokens | ["Wd", "1", "6", "1"] | ["1", "6", "1"] | _unclassified_ |
| 7.3 | fow_entries | [[0, 1, null, null]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 7.4 | striker_runs | 25 | 8 | _unclassified_ |
| 7.4 | striker_balls | 23 | 8 | _unclassified_ |
| 7.4 | non_striker_runs | 77 | 43 | _unclassified_ |
| 7.4 | non_striker_balls | 40 | 24 | _unclassified_ |
| 7.4 | non_striker_fours | 3 | 4 | _unclassified_ |
| 7.4 | this_over_tokens | ["Wd", "1", "6", "1", "4"] | ["1", "6", "1", "4"] | _unclassified_ |
| 7.4 | fow_entries | [[0, 1, null, null]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 7.5 | striker_runs | 25 | 8 | _unclassified_ |
| 7.5 | striker_balls | 24 | 9 | _unclassified_ |
| 7.5 | non_striker_runs | 77 | 43 | _unclassified_ |
| 7.5 | non_striker_balls | 40 | 24 | _unclassified_ |
| 7.5 | non_striker_fours | 3 | 4 | _unclassified_ |
| 7.5 | this_over_tokens | ["Wd", "1", "6", "1", "4", "."] | ["1", "6", "1", "4", "."] | _unclassified_ |
| 7.5 | fow_entries | [[0, 1, null, null]] | [[49, 1, "Rahul", "4.6"]] | E3-wicket-frame-misalign |
| 7.6 | striker_name | Nissanka | — | D-post-FoW-striker |
| 7.6 | striker_runs | 77 | 0 | _unclassified_ |
| 7.6 | striker_balls | 40 | 0 | _unclassified_ |
| 7.6 | striker_fours | 3 | 0 | Boundary-counter-double-increment |
| 7.6 | striker_sixes | 3 | 0 | Boundary-counter-double-increment |
| 7.6 | non_striker_name | — | Nissanka | _unclassified_ |
| 7.6 | non_striker_runs | 0 | 43 | _unclassified_ |
| 7.6 | non_striker_balls | 0 | 24 | _unclassified_ |
| 7.6 | non_striker_fours | 0 | 4 | _unclassified_ |
| 7.6 | non_striker_sixes | 0 | 3 | _unclassified_ |
| 7.6 | bowler_name | — | Green | F-B-ad-occlusion |
| 7.6 | bowler_overs | — | 1.0 | F-A-commit-lag |
| 7.6 | bowler_runs | 0 | 12 | _unclassified_ |
| 7.6 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 7.6 | this_over_tokens | ["Wd", "1", "6", "1", "4", ".", "W"] | ["1", "6", "1", "4", ".", "W"] | _unclassified_ |
| 7.6 | fow_entries | [[0, 1, null, null], [74, 0, "Rana", "7.6"]] | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"]] | E3-wicket-frame-misalign |
| 8.1 | non_striker_name | — | Nissanka | _unclassified_ |
| 8.1 | non_striker_runs | 0 | 44 | _unclassified_ |
| 8.1 | non_striker_balls | 0 | 25 | _unclassified_ |
| 8.1 | non_striker_fours | 0 | 4 | _unclassified_ |
| 8.1 | non_striker_sixes | 0 | 3 | _unclassified_ |
| 8.1 | bowler_name | — | Chakaravarthy | F-B-ad-occlusion |
| 8.1 | bowler_overs | — | 1.1 | F-A-commit-lag |
| 8.1 | bowler_runs | 0 | 8 | _unclassified_ |
| 8.1 | this_over_tokens | [] | ["1"] | Multi-ball-compression |
| 8.1 | recent_over_n_minus_1 | [] | ["1", "6", "1", "4", ".", "W"] | Recent-overs-drop |
| 8.1 | fow_entries | [[0, 1, null, null], [74, 0, "Rana", "7.6"]] | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"]] | E3-wicket-frame-misalign |
| 8.3 | striker_name | Nissanka | Rizvi | D-post-FoW-striker |
| 8.3 | striker_runs | 152 | 0 | _unclassified_ |
| 8.3 | striker_balls | 91 | 2 | _unclassified_ |
| 8.3 | striker_fours | 3 | 0 | Boundary-counter-double-increment |
| 8.3 | striker_sixes | 3 | 0 | Boundary-counter-double-increment |
| 8.3 | non_striker_name | — | Nissanka | _unclassified_ |
| 8.3 | non_striker_runs | 0 | 44 | _unclassified_ |
| 8.3 | non_striker_balls | 0 | 25 | _unclassified_ |
| 8.3 | non_striker_fours | 0 | 4 | _unclassified_ |
| 8.3 | non_striker_sixes | 0 | 3 | _unclassified_ |
| 8.3 | bowler_overs | 15.3 | 1.3 | F-A-commit-lag |
| 8.3 | bowler_runs | 134 | 8 | _unclassified_ |
| 8.3 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | ["1", ".", "."] | _unclassified_ |
| 8.3 | fow_entries | [[0, 1, null, null], [74, 0, "Rana", "7.6"]] | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"]] | E3-wicket-frame-misalign |
| 8.4 | striker_name | — | Nissanka | D-post-FoW-striker |
| 8.4 | striker_runs | 0 | 44 | _unclassified_ |
| 8.4 | striker_balls | 0 | 25 | _unclassified_ |
| 8.4 | striker_fours | 0 | 4 | _unclassified_ |
| 8.4 | striker_sixes | 0 | 3 | _unclassified_ |
| 8.4 | non_striker_name | Nissanka | Rizvi | _unclassified_ |
| 8.4 | non_striker_runs | 153 | 1 | _unclassified_ |
| 8.4 | non_striker_balls | 92 | 3 | _unclassified_ |
| 8.4 | non_striker_fours | 3 | 0 | _unclassified_ |
| 8.4 | non_striker_sixes | 3 | 0 | _unclassified_ |
| 8.4 | bowler_overs | 15.4 | 1.4 | F-A-commit-lag |
| 8.4 | bowler_runs | 135 | 9 | _unclassified_ |
| 8.4 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | ["1", ".", ".", "1"] | _unclassified_ |
| 8.4 | fow_entries | [[0, 1, null, null], [74, 0, "Rana", "7.6"]] | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"]] | E3-wicket-frame-misalign |
| 8.5 | striker_name | — | Rizvi | D-post-FoW-striker |
| 8.5 | striker_runs | 0 | 1 | _unclassified_ |
| 8.5 | striker_balls | 0 | 3 | _unclassified_ |
| 8.5 | non_striker_runs | 153 | 45 | _unclassified_ |
| 8.5 | non_striker_balls | 92 | 26 | _unclassified_ |
| 8.5 | non_striker_fours | 3 | 4 | _unclassified_ |
| 8.5 | bowler_overs | 15.5 | 1.5 | F-A-commit-lag |
| 8.5 | bowler_runs | 136 | 10 | _unclassified_ |
| 8.5 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | ["1", ".", ".", "1", "1"] | _unclassified_ |
| 8.5 | fow_entries | [[0, 1, null, null], [74, 0, "Rana", "7.6"]] | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"]] | E3-wicket-frame-misalign |
| 9.2 | striker_name | — | Rizvi | D-post-FoW-striker |
| 9.2 | striker_runs | 0 | 1 | _unclassified_ |
| 9.2 | striker_balls | 0 | 4 | _unclassified_ |
| 9.2 | non_striker_name | — | Nissanka | _unclassified_ |
| 9.2 | non_striker_runs | 0 | 46 | _unclassified_ |
| 9.2 | non_striker_balls | 0 | 28 | _unclassified_ |
| 9.2 | non_striker_fours | 0 | 4 | _unclassified_ |
| 9.2 | non_striker_sixes | 0 | 3 | _unclassified_ |
| 9.2 | bowler_name | — | Narine | F-B-ad-occlusion |
| 9.2 | bowler_overs | — | 1.2 | F-A-commit-lag |
| 9.2 | bowler_runs | 0 | 12 | _unclassified_ |
| 9.2 | this_over_tokens | [] | [".", "1"] | Multi-ball-compression |
| 9.2 | fow_entries | [[0, 1, null, null], [74, 0, "Rana", "7.6"]] | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"]] | E3-wicket-frame-misalign |
| 9.3 | striker_name | Nissanka | Rizvi | D-post-FoW-striker |
| 9.3 | striker_runs | 231 | 1 | _unclassified_ |
| 9.3 | striker_balls | 149 | 5 | _unclassified_ |
| 9.3 | striker_fours | 3 | 0 | Boundary-counter-double-increment |
| 9.3 | striker_sixes | 3 | 0 | Boundary-counter-double-increment |
| 9.3 | non_striker_name | — | Nissanka | _unclassified_ |
| 9.3 | non_striker_runs | 0 | 46 | _unclassified_ |
| 9.3 | non_striker_balls | 0 | 28 | _unclassified_ |
| 9.3 | non_striker_fours | 0 | 4 | _unclassified_ |
| 9.3 | non_striker_sixes | 0 | 3 | _unclassified_ |
| 9.3 | bowler_overs | 10.3 | 1.3 | F-A-commit-lag |
| 9.3 | bowler_runs | 89 | 12 | _unclassified_ |
| 9.3 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | [".", "1", "."] | _unclassified_ |
| 9.3 | fow_entries | [[0, 1, null, null], [74, 0, "Rana", "7.6"]] | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"]] | E3-wicket-frame-misalign |
| 9.4 | striker_name | Nissanka | Rizvi | D-post-FoW-striker |
| 9.4 | striker_runs | 233 | 3 | _unclassified_ |
| 9.4 | striker_balls | 150 | 6 | _unclassified_ |
| 9.4 | striker_fours | 3 | 0 | Boundary-counter-double-increment |
| 9.4 | striker_sixes | 3 | 0 | Boundary-counter-double-increment |
| 9.4 | non_striker_name | — | Nissanka | _unclassified_ |
| 9.4 | non_striker_runs | 0 | 46 | _unclassified_ |
| 9.4 | non_striker_balls | 0 | 28 | _unclassified_ |
| 9.4 | non_striker_fours | 0 | 4 | _unclassified_ |
| 9.4 | non_striker_sixes | 0 | 3 | _unclassified_ |
| 9.4 | bowler_overs | 10.4 | 1.4 | F-A-commit-lag |
| 9.4 | bowler_runs | 91 | 14 | _unclassified_ |
| 9.4 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | [".", "1", ".", "2"] | _unclassified_ |
| 9.4 | fow_entries | [[0, 1, null, null], [74, 0, "Rana", "7.6"]] | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"]] | E3-wicket-frame-misalign |
| 9.5 | non_striker_name | — | Nissanka | _unclassified_ |
| 9.5 | non_striker_runs | 0 | 46 | _unclassified_ |
| 9.5 | non_striker_balls | 0 | 28 | _unclassified_ |
| 9.5 | non_striker_fours | 0 | 4 | _unclassified_ |
| 9.5 | non_striker_sixes | 0 | 3 | _unclassified_ |
| 9.5 | bowler_overs | 10.5 | 1.5 | F-A-commit-lag |
| 9.5 | bowler_runs | 91 | 14 | _unclassified_ |
| 9.5 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | [".", "1", ".", "2", "W"] | _unclassified_ |
| 9.5 | fow_entries | [[0, 1, null, null], [74, 0, "Rana", "7.6"], [80, 0, "Nis… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 10.1 | striker_name | — | Nissanka | D-post-FoW-striker |
| 10.1 | striker_runs | 0 | 50 | _unclassified_ |
| 10.1 | striker_balls | 0 | 29 | _unclassified_ |
| 10.1 | striker_fours | 0 | 5 | _unclassified_ |
| 10.1 | striker_sixes | 0 | 3 | _unclassified_ |
| 10.1 | non_striker_name | — | Stubbs | _unclassified_ |
| 10.1 | non_striker_balls | 0 | 1 | _unclassified_ |
| 10.1 | bowler_name | — | Roy | F-B-ad-occlusion |
| 10.1 | bowler_overs | — | 2.1 | F-A-commit-lag |
| 10.1 | bowler_runs | 0 | 22 | _unclassified_ |
| 10.1 | this_over_tokens | [] | ["4"] | Multi-ball-compression |
| 10.1 | recent_over_n_minus_1 | [] | [".", "1", ".", "2", "W", "."] | Recent-overs-drop |
| 10.1 | fow_entries | [[0, 1, null, null], [74, 0, "Rana", "7.6"], [80, 0, "Nis… | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 10.2 | score | 87 | 85 | E2-phantom-runs |
| 10.2 | balls_total | 62 | 61 | _unclassified_ |
| 10.2 | non_striker_name | — | Stubbs | _unclassified_ |
| 10.2 | non_striker_balls | 0 | 1 | _unclassified_ |
| 10.2 | bowler_name | — | Roy | F-B-ad-occlusion |
| 10.2 | bowler_overs | — | 2.1 | F-A-commit-lag |
| 10.2 | bowler_runs | 0 | 23 | _unclassified_ |
| 10.2 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 10.2 | extras_total | 0 | 1 | Extras-counter-drop |
| 10.2 | extras_wd | 0 | 1 | Extras-counter-drop |
| 10.2 | this_over_tokens | [] | ["4", "Wd+W"] | Compound-with-wicket-token |
| 10.2 | fow_entries | [[74, 0, "Rana", "7.6"], [80, 0, "Nissanka", "9.5"], [0, … | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 10.3 | striker_name | — | Stubbs | D-post-FoW-striker |
| 10.3 | striker_runs | 0 | 2 | _unclassified_ |
| 10.3 | striker_balls | 0 | 2 | _unclassified_ |
| 10.3 | non_striker_name | — | Patel | _unclassified_ |
| 10.3 | non_striker_runs | 0 | 1 | _unclassified_ |
| 10.3 | non_striker_balls | 0 | 1 | _unclassified_ |
| 10.3 | bowler_name | — | Roy | F-B-ad-occlusion |
| 10.3 | bowler_overs | — | 2.3 | F-A-commit-lag |
| 10.3 | bowler_runs | 0 | 27 | _unclassified_ |
| 10.3 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 10.3 | extras_total | 0 | 2 | Extras-counter-drop |
| 10.3 | extras_wd | 0 | 2 | Extras-counter-drop |
| 10.3 | this_over_tokens | [] | ["4", "Wd+W", "Wd", "1", "2"] | Compound-with-wicket-token |
| 10.3 | fow_entries | [[74, 0, "Rana", "7.6"], [80, 0, "Nissanka", "9.5"], [0, … | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 10.5 | striker_name | Patel | — | D-post-FoW-striker |
| 10.5 | non_striker_name | — | Patel | _unclassified_ |
| 10.5 | non_striker_runs | 0 | 1 | _unclassified_ |
| 10.5 | non_striker_balls | 0 | 1 | _unclassified_ |
| 10.5 | bowler_name | — | Roy | F-B-ad-occlusion |
| 10.5 | bowler_overs | — | 2.5 | F-A-commit-lag |
| 10.5 | bowler_runs | 0 | 27 | _unclassified_ |
| 10.5 | bowler_wickets | 0 | 2 | Bowler-W-credit-failure |
| 10.5 | extras_total | 0 | 2 | Extras-counter-drop |
| 10.5 | extras_wd | 0 | 2 | Extras-counter-drop |
| 10.5 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | ["4", "Wd+W", "Wd", "1", "2", ".", "W"] | C21b-symbol-revert |
| 10.5 | fow_entries | [[74, 0, "Rana", "7.6"], [80, 0, "Nissanka", "9.5"], [0, … | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 11.1 | striker_name | — | Patel | D-post-FoW-striker |
| 11.1 | striker_runs | 0 | 1 | _unclassified_ |
| 11.1 | striker_balls | 0 | 2 | _unclassified_ |
| 11.1 | non_striker_name | Patel | Sharma | _unclassified_ |
| 11.1 | non_striker_balls | 2 | 1 | _unclassified_ |
| 11.1 | bowler_name | — | Narine | F-B-ad-occlusion |
| 11.1 | bowler_overs | — | 2.1 | F-A-commit-lag |
| 11.1 | bowler_runs | 0 | 14 | _unclassified_ |
| 11.1 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 11.1 | extras_total | 0 | 2 | Extras-counter-drop |
| 11.1 | extras_wd | 0 | 2 | Extras-counter-drop |
| 11.1 | recent_over_n_minus_1 | [] | ["4", "Wd+W", "Wd", "1", "2", ".", "W", "."] | Recent-overs-drop |
| 11.1 | fow_entries | [[74, 0, "Rana", "7.6"], [80, 0, "Nissanka", "9.5"], [0, … | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 11.2 | striker_name | — | Patel | D-post-FoW-striker |
| 11.2 | striker_runs | 0 | 1 | _unclassified_ |
| 11.2 | striker_balls | 0 | 3 | _unclassified_ |
| 11.2 | non_striker_name | Patel | Sharma | _unclassified_ |
| 11.2 | non_striker_balls | 3 | 1 | _unclassified_ |
| 11.2 | bowler_name | — | Narine | F-B-ad-occlusion |
| 11.2 | bowler_overs | — | 2.2 | F-A-commit-lag |
| 11.2 | bowler_runs | 0 | 14 | _unclassified_ |
| 11.2 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 11.2 | extras_total | 0 | 2 | Extras-counter-drop |
| 11.2 | extras_wd | 0 | 2 | Extras-counter-drop |
| 11.2 | fow_entries | [[74, 0, "Rana", "7.6"], [80, 0, "Nissanka", "9.5"], [0, … | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 11.3 | striker_name | — | Patel | D-post-FoW-striker |
| 11.3 | striker_runs | 0 | 1 | _unclassified_ |
| 11.3 | striker_balls | 0 | 4 | _unclassified_ |
| 11.3 | non_striker_name | Patel | Sharma | _unclassified_ |
| 11.3 | non_striker_balls | 4 | 1 | _unclassified_ |
| 11.3 | bowler_name | — | Narine | F-B-ad-occlusion |
| 11.3 | bowler_overs | — | 2.3 | F-A-commit-lag |
| 11.3 | bowler_runs | 0 | 14 | _unclassified_ |
| 11.3 | bowler_wickets | 0 | 1 | Bowler-W-credit-failure |
| 11.3 | extras_total | 0 | 2 | Extras-counter-drop |
| 11.3 | extras_wd | 0 | 2 | Extras-counter-drop |
| 11.3 | fow_entries | [[74, 0, "Rana", "7.6"], [80, 0, "Nissanka", "9.5"], [0, … | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 11.4 | striker_name | — | Patel | D-post-FoW-striker |
| 11.4 | striker_runs | 0 | 1 | _unclassified_ |
| 11.4 | striker_balls | 0 | 5 | _unclassified_ |
| 11.4 | non_striker_name | Patel | Sharma | _unclassified_ |
| 11.4 | non_striker_balls | 5 | 1 | _unclassified_ |
| 11.4 | bowler_overs | 11.3 | 2.4 | F-A-commit-lag |
| 11.4 | bowler_runs | 91 | 14 | _unclassified_ |
| 11.4 | extras_total | 0 | 2 | Extras-counter-drop |
| 11.4 | extras_wd | 0 | 2 | Extras-counter-drop |
| 11.4 | fow_entries | [[74, 0, "Rana", "7.6"], [80, 0, "Nissanka", "9.5"], [0, … | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |
| 11.5 | striker_name | Patel | Sharma | D-post-FoW-striker |
| 11.5 | striker_runs | 1 | 0 | _unclassified_ |
| 11.5 | striker_balls | 6 | 1 | _unclassified_ |
| 11.5 | non_striker_name | — | Patel | _unclassified_ |
| 11.5 | non_striker_runs | 0 | 2 | _unclassified_ |
| 11.5 | non_striker_balls | 0 | 6 | _unclassified_ |
| 11.5 | bowler_overs | 11.4 | 2.5 | F-A-commit-lag |
| 11.5 | bowler_runs | 92 | 15 | _unclassified_ |
| 11.5 | extras_total | 0 | 2 | Extras-counter-drop |
| 11.5 | extras_wd | 0 | 2 | Extras-counter-drop |
| 11.5 | fow_entries | [[74, 0, "Rana", "7.6"], [80, 0, "Nissanka", "9.5"], [0, … | [[49, 1, "Rahul", "4.6"], [74, 2, "Rana", "7.6"], [80, 3,… | E3-wicket-frame-misalign |

## 3. Conservation invariants

1. 6.1: striker(69)+non_striker(18)+extras(0) = 87 > score(56)
2. 6.2: striker(69)+non_striker(18)+extras(0) = 87 > score(56)
3. 6.3: striker(18)+non_striker(70)+extras(0) = 88 > score(57)
4. 6.4: striker(19)+non_striker(70)+extras(0) = 89 > score(58)
5. 6.5: striker(19)+non_striker(70)+extras(0) = 89 > score(58)
6. 6.6: striker(20)+non_striker(70)+extras(0) = 90 > score(59)
7. 7.1: striker(70)+non_striker(21)+extras(0) = 91 > score(63)
8. 7.2: striker(76)+non_striker(21)+extras(0) = 97 > score(69)
9. 7.3: striker(21)+non_striker(77)+extras(0) = 98 > score(70)
10. 7.4: striker(25)+non_striker(77)+extras(0) = 102 > score(74)
11. 7.5: striker(25)+non_striker(77)+extras(0) = 102 > score(74)
12. 7.6: striker(77)+non_striker(0)+extras(0) = 77 > score(74)
13. 8.3: striker(152)+non_striker(0)+extras(0) = 152 > score(75)
14. 8.4: striker(0)+non_striker(153)+extras(0) = 153 > score(76)
15. 8.5: striker(0)+non_striker(153)+extras(0) = 153 > score(77)
16. 9.3: striker(231)+non_striker(0)+extras(0) = 231 > score(78)
17. 9.4: striker(233)+non_striker(0)+extras(0) = 233 > score(80)

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
| 0.6 | striker_name | Nissanka | Rahul |
| 0.6 | striker_runs | 6 | 1 |
| 0.6 | striker_balls | 3 | 2 |
| 0.6 | non_striker_name | Rahul | Nissanka |
| 0.6 | non_striker_runs | 1 | 6 |
| 0.6 | non_striker_balls | 2 | 4 |
| 0.6 | non_striker_fours | 0 | 1 |
| 0.6 | bowler_runs | 0 | 7 |
| 1.1 | striker_balls | 4 | 5 |
| 1.2 | non_striker_balls | 5 | 6 |
| 1.3 | striker_balls | 5 | 6 |
| 1.4 | striker_balls | 6 | 7 |
| 1.5 | non_striker_balls | 7 | 8 |
| 1.6 | striker_name | Rahul | Nissanka |
| 1.6 | striker_runs | 3 | 14 |
| 1.6 | striker_balls | 4 | 8 |
| 1.6 | striker_fours | 0 | 1 |
| 1.6 | striker_sixes | 0 | 1 |
| 1.6 | non_striker_name | Nissanka | Rahul |
| 1.6 | non_striker_runs | 14 | 3 |
| 1.6 | non_striker_balls | 7 | 4 |
| 1.6 | non_striker_fours | 1 | 0 |
| 1.6 | non_striker_sixes | 1 | 0 |
| 1.6 | bowler_runs | 0 | 10 |
| 2.1 | non_striker_balls | 7 | 8 |
| 2.2 | non_striker_balls | 7 | 8 |
| 2.3 | striker_balls | 7 | 8 |
| 2.4 | striker_balls | 8 | 9 |
| 2.5 | striker_balls | 9 | 10 |
| 2.6 | striker_name | Rahul | Nissanka |
| 2.6 | striker_runs | 8 | 20 |
| 2.6 | striker_balls | 7 | 11 |
| 2.6 | striker_sixes | 0 | 2 |
| 2.6 | non_striker_name | Nissanka | Rahul |
| 2.6 | non_striker_runs | 20 | 8 |
| 2.6 | non_striker_balls | 10 | 7 |
| 2.6 | non_striker_sixes | 2 | 0 |
| 2.6 | bowler_runs | 0 | 18 |
| 3.1 | striker_balls | 10 | 11 |
| 3.1 | bowler_runs | 0 | 1 |
| 3.2 | striker_balls | 11 | 12 |
| 3.3 | striker_balls | 12 | 13 |
| 3.4 | non_striker_balls | 13 | 14 |
| 3.5 | non_striker_balls | 13 | 14 |
| 3.6 | striker_name | Rahul | Nissanka |
| 3.6 | striker_runs | 14 | 25 |
| 3.6 | striker_balls | 10 | 14 |
| 3.6 | striker_sixes | 0 | 2 |
| 3.6 | non_striker_name | Nissanka | Rahul |
| 3.6 | non_striker_runs | 25 | 14 |
| 3.6 | non_striker_balls | 13 | 10 |
| 3.6 | non_striker_sixes | 2 | 0 |
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
| 5.1 | striker_balls | 16 | 17 |
| 5.1 | non_striker_name | Rahul | — |
| 5.1 | non_striker_runs | 23 | 0 |
| 5.1 | non_striker_balls | 14 | 0 |
| 5.1 | non_striker_fours | 4 | 0 |
| 5.1 | bowler_runs | 0 | 14 |
| 5.2 | striker_runs | 23 | 0 |
| 5.2 | striker_balls | 14 | 0 |
| 5.2 | non_striker_balls | 17 | 18 |
| 5.2 | bowler_runs | 0 | 15 |
| 5.6 | striker_runs | 0 | 31 |
| 5.6 | striker_balls | 0 | 18 |
| 5.6 | striker_fours | 0 | 3 |
| 5.6 | striker_sixes | 0 | 2 |
| 5.6 | non_striker_name | — | Rana |
| 5.6 | non_striker_runs | 0 | 1 |
| 5.6 | non_striker_balls | 0 | 4 |
| 5.6 | bowler_runs | 0 | 16 |
| 6.1 | striker_runs | 69 | 31 |
| 6.1 | striker_balls | 36 | 18 |
| 6.1 | non_striker_runs | 18 | 2 |
| 6.1 | non_striker_balls | 18 | 5 |
| 6.1 | bowler_runs | 56 | 1 |
| 6.1 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | ["1"] |
| 6.2 | striker_runs | 69 | 31 |
| 6.2 | striker_balls | 37 | 19 |
| 6.2 | non_striker_runs | 18 | 2 |
| 6.2 | non_striker_balls | 18 | 5 |
| 6.2 | bowler_runs | 56 | 1 |
| 6.2 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | ["1", "."] |
| 6.3 | striker_runs | 18 | 2 |
| 6.3 | striker_balls | 18 | 5 |
| 6.3 | non_striker_runs | 70 | 32 |
| 6.3 | non_striker_balls | 38 | 20 |
| 6.3 | bowler_runs | 57 | 2 |
| 6.3 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | ["1", ".", "1"] |
| 6.4 | striker_runs | 19 | 32 |
| 6.4 | striker_balls | 19 | 20 |
| 6.4 | striker_fours | 0 | 3 |
| 6.4 | striker_sixes | 0 | 2 |
| 6.4 | non_striker_name | Nissanka | Rana |
| 6.4 | non_striker_runs | 70 | 3 |
| 6.4 | non_striker_balls | 38 | 6 |
| 6.4 | non_striker_fours | 3 | 0 |
| 6.4 | non_striker_sixes | 2 | 0 |
| 6.4 | bowler_runs | 58 | 3 |
| 6.4 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | ["1", ".", "1", "1"] |
| 6.5 | striker_runs | 19 | 32 |
| 6.5 | striker_balls | 20 | 21 |
| 6.5 | striker_fours | 0 | 3 |
| 6.5 | striker_sixes | 0 | 2 |
| 6.5 | non_striker_name | Nissanka | Rana |
| 6.5 | non_striker_runs | 70 | 3 |
| 6.5 | non_striker_balls | 38 | 6 |
| 6.5 | non_striker_fours | 3 | 0 |
| 6.5 | non_striker_sixes | 2 | 0 |
| 6.5 | bowler_runs | 58 | 3 |
| 6.5 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | ["1", ".", "1", "1", "."] |
| 6.6 | score | 59 | 62 |
| 6.6 | striker_runs | 20 | 36 |
| 6.6 | striker_balls | 21 | 22 |
| 6.6 | striker_fours | 0 | 4 |
| 6.6 | striker_sixes | 0 | 2 |
| 6.6 | non_striker_name | Nissanka | Rana |
| 6.6 | non_striker_runs | 70 | 3 |
| 6.6 | non_striker_balls | 38 | 6 |
| 6.6 | non_striker_fours | 3 | 0 |
| 6.6 | non_striker_sixes | 2 | 0 |
| 6.6 | bowler_runs | 0 | 7 |
| 6.6 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | ["1", ".", "1", "1", ".", "4"] |
| 7.1 | striker_runs | 70 | 36 |
| 7.1 | striker_balls | 38 | 22 |
| 7.1 | striker_fours | 3 | 4 |
| 7.1 | non_striker_runs | 21 | 4 |
| 7.1 | non_striker_balls | 22 | 7 |
| 7.1 | bowler_runs | 0 | 1 |
| 7.1 | this_over_tokens | ["Wd", "1"] | ["1"] |
| 7.2 | striker_runs | 76 | 42 |
| 7.2 | striker_balls | 39 | 23 |
| 7.2 | striker_fours | 3 | 4 |
| 7.2 | non_striker_runs | 21 | 4 |
| 7.2 | non_striker_balls | 22 | 7 |
| 7.2 | bowler_runs | 0 | 7 |
| 7.2 | this_over_tokens | ["Wd", "1", "6"] | ["1", "6"] |
| 7.3 | striker_runs | 21 | 4 |
| 7.3 | striker_balls | 22 | 7 |
| 7.3 | non_striker_runs | 77 | 43 |
| 7.3 | non_striker_balls | 40 | 24 |
| 7.3 | non_striker_fours | 3 | 4 |
| 7.3 | this_over_tokens | ["Wd", "1", "6", "1"] | ["1", "6", "1"] |
| 7.4 | striker_runs | 25 | 8 |
| 7.4 | striker_balls | 23 | 8 |
| 7.4 | non_striker_runs | 77 | 43 |
| 7.4 | non_striker_balls | 40 | 24 |
| 7.4 | non_striker_fours | 3 | 4 |
| 7.4 | this_over_tokens | ["Wd", "1", "6", "1", "4"] | ["1", "6", "1", "4"] |
| 7.5 | striker_runs | 25 | 8 |
| 7.5 | striker_balls | 24 | 9 |
| 7.5 | non_striker_runs | 77 | 43 |
| 7.5 | non_striker_balls | 40 | 24 |
| 7.5 | non_striker_fours | 3 | 4 |
| 7.5 | this_over_tokens | ["Wd", "1", "6", "1", "4", "."] | ["1", "6", "1", "4", "."] |
| 7.6 | striker_runs | 77 | 0 |
| 7.6 | striker_balls | 40 | 0 |
| 7.6 | non_striker_name | — | Nissanka |
| 7.6 | non_striker_runs | 0 | 43 |
| 7.6 | non_striker_balls | 0 | 24 |
| 7.6 | non_striker_fours | 0 | 4 |
| 7.6 | non_striker_sixes | 0 | 3 |
| 7.6 | bowler_runs | 0 | 12 |
| 7.6 | this_over_tokens | ["Wd", "1", "6", "1", "4", ".", "W"] | ["1", "6", "1", "4", ".", "W"] |
| 8.1 | non_striker_name | — | Nissanka |
| 8.1 | non_striker_runs | 0 | 44 |
| 8.1 | non_striker_balls | 0 | 25 |
| 8.1 | non_striker_fours | 0 | 4 |
| 8.1 | non_striker_sixes | 0 | 3 |
| 8.1 | bowler_runs | 0 | 8 |
| 8.3 | striker_runs | 152 | 0 |
| 8.3 | striker_balls | 91 | 2 |
| 8.3 | non_striker_name | — | Nissanka |
| 8.3 | non_striker_runs | 0 | 44 |
| 8.3 | non_striker_balls | 0 | 25 |
| 8.3 | non_striker_fours | 0 | 4 |
| 8.3 | non_striker_sixes | 0 | 3 |
| 8.3 | bowler_runs | 134 | 8 |
| 8.3 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | ["1", ".", "."] |
| 8.4 | striker_runs | 0 | 44 |
| 8.4 | striker_balls | 0 | 25 |
| 8.4 | striker_fours | 0 | 4 |
| 8.4 | striker_sixes | 0 | 3 |
| 8.4 | non_striker_name | Nissanka | Rizvi |
| 8.4 | non_striker_runs | 153 | 1 |
| 8.4 | non_striker_balls | 92 | 3 |
| 8.4 | non_striker_fours | 3 | 0 |
| 8.4 | non_striker_sixes | 3 | 0 |
| 8.4 | bowler_runs | 135 | 9 |
| 8.4 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | ["1", ".", ".", "1"] |
| 8.5 | striker_runs | 0 | 1 |
| 8.5 | striker_balls | 0 | 3 |
| 8.5 | non_striker_runs | 153 | 45 |
| 8.5 | non_striker_balls | 92 | 26 |
| 8.5 | non_striker_fours | 3 | 4 |
| 8.5 | bowler_runs | 136 | 10 |
| 8.5 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | ["1", ".", ".", "1", "1"] |
| 9.2 | striker_runs | 0 | 1 |
| 9.2 | striker_balls | 0 | 4 |
| 9.2 | non_striker_name | — | Nissanka |
| 9.2 | non_striker_runs | 0 | 46 |
| 9.2 | non_striker_balls | 0 | 28 |
| 9.2 | non_striker_fours | 0 | 4 |
| 9.2 | non_striker_sixes | 0 | 3 |
| 9.2 | bowler_runs | 0 | 12 |
| 9.3 | striker_runs | 231 | 1 |
| 9.3 | striker_balls | 149 | 5 |
| 9.3 | non_striker_name | — | Nissanka |
| 9.3 | non_striker_runs | 0 | 46 |
| 9.3 | non_striker_balls | 0 | 28 |
| 9.3 | non_striker_fours | 0 | 4 |
| 9.3 | non_striker_sixes | 0 | 3 |
| 9.3 | bowler_runs | 89 | 12 |
| 9.3 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | [".", "1", "."] |
| 9.4 | striker_runs | 233 | 3 |
| 9.4 | striker_balls | 150 | 6 |
| 9.4 | non_striker_name | — | Nissanka |
| 9.4 | non_striker_runs | 0 | 46 |
| 9.4 | non_striker_balls | 0 | 28 |
| 9.4 | non_striker_fours | 0 | 4 |
| 9.4 | non_striker_sixes | 0 | 3 |
| 9.4 | bowler_runs | 91 | 14 |
| 9.4 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | [".", "1", ".", "2"] |
| 9.5 | non_striker_name | — | Nissanka |
| 9.5 | non_striker_runs | 0 | 46 |
| 9.5 | non_striker_balls | 0 | 28 |
| 9.5 | non_striker_fours | 0 | 4 |
| 9.5 | non_striker_sixes | 0 | 3 |
| 9.5 | bowler_runs | 91 | 14 |
| 9.5 | this_over_tokens | ["1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1", "… | [".", "1", ".", "2", "W"] |
| 10.1 | striker_runs | 0 | 50 |
| 10.1 | striker_balls | 0 | 29 |
| 10.1 | striker_fours | 0 | 5 |
| 10.1 | striker_sixes | 0 | 3 |
| 10.1 | non_striker_name | — | Stubbs |
| 10.1 | non_striker_balls | 0 | 1 |
| 10.1 | bowler_runs | 0 | 22 |
| 10.2 | balls_total | 62 | 61 |
| 10.2 | non_striker_name | — | Stubbs |
| 10.2 | non_striker_balls | 0 | 1 |
| 10.2 | bowler_runs | 0 | 23 |
| 10.3 | striker_runs | 0 | 2 |
| 10.3 | striker_balls | 0 | 2 |
| 10.3 | non_striker_name | — | Patel |
| 10.3 | non_striker_runs | 0 | 1 |
| 10.3 | non_striker_balls | 0 | 1 |
| 10.3 | bowler_runs | 0 | 27 |
| 10.5 | non_striker_name | — | Patel |
| 10.5 | non_striker_runs | 0 | 1 |
| 10.5 | non_striker_balls | 0 | 1 |
| 10.5 | bowler_runs | 0 | 27 |
| 11.1 | striker_runs | 0 | 1 |
| 11.1 | striker_balls | 0 | 2 |
| 11.1 | non_striker_name | Patel | Sharma |
| 11.1 | non_striker_balls | 2 | 1 |
| 11.1 | bowler_runs | 0 | 14 |
| 11.2 | striker_runs | 0 | 1 |
| 11.2 | striker_balls | 0 | 3 |
| 11.2 | non_striker_name | Patel | Sharma |
| 11.2 | non_striker_balls | 3 | 1 |
| 11.2 | bowler_runs | 0 | 14 |
| 11.3 | striker_runs | 0 | 1 |
| 11.3 | striker_balls | 0 | 4 |
| 11.3 | non_striker_name | Patel | Sharma |
| 11.3 | non_striker_balls | 4 | 1 |
| 11.3 | bowler_runs | 0 | 14 |
| 11.4 | striker_runs | 0 | 1 |
| 11.4 | striker_balls | 0 | 5 |
| 11.4 | non_striker_name | Patel | Sharma |
| 11.4 | non_striker_balls | 5 | 1 |
| 11.4 | bowler_runs | 91 | 14 |
| 11.5 | striker_runs | 1 | 0 |
| 11.5 | striker_balls | 6 | 1 |
| 11.5 | non_striker_name | — | Patel |
| 11.5 | non_striker_runs | 0 | 2 |
| 11.5 | non_striker_balls | 0 | 6 |
| 11.5 | bowler_runs | 92 | 15 |

## 5. Missing / phantom balls

- Missing-in-pipeline (61): 4.6, 5.3, 5.4, 5.5, 8.2, 8.6, 9.1, 9.6, 10.2#1, 10.2#2, 10.4, 10.6, 11.6, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 19.1, 19.2, 19.3, 19.4, 19.5, 19.6
- Phantom-in-pipeline (6): 6.6#1, 6.6#2, 6.6#3, 4.2#1, 4.2#2, 4.2#3
