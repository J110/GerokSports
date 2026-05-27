# KKR/DC 10-Minute Track 1 Root Cause

Inputs:

- Diff: `files/docs/replay_live_kkrdc_20260526_10min_diff.md`
- Pipeline snapshots: `files/logs/deliveries/replay_kkrdc_10min_20260526_193747/ui_snapshots.jsonl`
- GT snapshots: `files/logs/deliveries/replay_kkrdc_10min_20260526_193747/gt_trimmed_1p1_to_2p5.jsonl`
- Replay log: `/tmp/replay_kkrdc_10min_20260526_193747.log`
- Trace: not present at `logs/trace/replay_kkrdc_10min_20260526_193747.jsonl` in the accessible tree
- Delivery windows: `files/logs/deliveries/20260526_193750/d001` through `d011`

## Summary

The dominant Track 1 diff is cold-start/snapshot pollution from starting the clip at `DC 10-0 (1.0)`, not at innings ball `0.1`.

The runtime log shows a cleaner live state than the offline `ui_snapshots.jsonl` diff input in several places. In particular, the log at `1.1` has runtime `AFTER_this_over=['.']`, while the pipeline snapshot line for `1.1` contains inherited synthetic first-over tokens. Treat the diff as a snapshotter/cold-start forensic signal, not as a pure live-runtime state dump.

## Evidence Inventory

- Diff summary: matched `12`, missing `0`, phantom `2`, divergences `148`; phantom keys are `0.6` and `1.4#1` (`files/docs/replay_live_kkrdc_20260526_10min_diff.md` lines 3-5 and 287-290).
- Pipeline snapshot line 1 is a synthetic `0.6`: score `10`, balls `6`, tokens `["1","1","1","1","1","5"]`.
- Pipeline snapshot line 2 is `1.1`: striker `Porel`, non-striker `Rahul`, tokens `["1","1","1","1","1","5","."]`.
- GT line 1 is `1.1`: striker `Rahul`, non-striker `Porel`, tokens `["."]`, recent previous over `[".",".","4","4","1","1"]`.
- Runtime cold start begins at frame F1/F2 with score `10-0 (1.0)`, not the actual first ball: log lines 107-142 and 151-193.
- Trace decision tags were not available from a trace JSONL file; the decision tags cited below are log-emitted tags from the replay log.

## 1. Wrong Striker At 1.1

Root-cause candidate: polluted cold-start anchoring. The clip begins after the first over at `DC 10-0 (1.0)`, and `_auto_anchor_check` locks the openers in broadcast/deterministic order before the pipeline has a real delivery history.

Evidence:

- Pipeline snapshot line 2: `over_ball=1.1`, `striker_name=Porel`, `non_striker_name=Rahul`.
- GT line 1: `over_ball=1.1`, `striker_name=Rahul`, `non_striker_name=Porel`.
- Log lines 143-145: `[STRIKER-WRITE] ... striker None->Abishek Porel`, `non None->KL Rahul`, then `[AUTO-ANCHOR] batters locked`.
- Log line 173: `[STRIKER-BROADCAST-DISAGREES-DETERMINISTIC] broadcast='KL Rahul' deterministic='Abishek Porel' - keeping deterministic`.
- Log line 187: state is already `Bat: Abishek Porel*(0) KL Rahul(0)`.

Conclusion: the wrong striker is not caused by a 1.1 delivery read. It is inherited from cold-start deterministic anchoring after the clip starts at `1.0`.

## 2. Polluted `this_over_tokens` At 1.1

Root-cause candidate: the offline snapshot stream carries a synthetic `0.6` first-over reconstruction into the next over.

Evidence:

- Pipeline snapshot line 1: phantom `0.6` with `this_over_tokens=["1","1","1","1","1","5"]`.
- Pipeline snapshot line 2: `1.1` appends `"."` to those same six tokens.
- GT line 1: `1.1` has `this_over_tokens=["."]` and keeps the previous over separately in `recent_over_n_minus_1`.
- Runtime log line 529 for F14 shows `AFTER_this_over=['.']` and `AFTER_this_over_src=.(bcast)`, not the polluted seven-token list.
- Runtime log lines 504-508 show `['?']` was corrected to a single dot and the cold-start placeholder was suppressed.

Conclusion: this is primarily a snapshotter/cold-start export issue. The runtime state at F14 did not contain `["1","1","1","1","1","5","."]`; that token list is introduced by the offline snapshot stream from the synthetic `0.6` event.

## 3. Phantom Pipeline Events

`0.6` is polluted cold-start state, not a real broadcast-score delivery event.

Evidence:

- Diff lines 287-290 list phantom `0.6`.
- Pipeline snapshot line 1 has `over_ball=0.6`, score `10`, tokens `["1","1","1","1","1","5"]`.
- There is no `0.6` delivery folder; `d001/window_debug.json` starts at `over_number=1.1`.
- Log line 232: `[SM] cold-start candidate seeded 10/0 (1.0)`.
- Log line 286: partnership anchored with `team=10/6`, a clue that the first six balls are inferred from the already-visible `10-0 (1.0)` state.

`1.4#1` is a real extra observation, but keyed to the wrong over-ball convention.

Evidence:

- Diff lines 287-290 list phantom `1.4#1`.
- Pipeline snapshot line 6 has duplicate key `1.4`, `event_index=1`, score `12`, appended token `"1"`.
- Pipeline snapshot line 8 later has `1.5`, `event_index=1`, appended token `"Wd"`, but extras counters remain zero.
- GT line 5 represents the wide as `over_ball=1.5`, `event_index=0`, score `12`, `balls_total=10`, token `"Wd"`.
- `d005/window_debug.json` records `delivery_num=5`, `over_number=1.4`, `event_type=EXTRA`, `runs=1`.
- Runtime log line 2350 shows the over state includes `['.', '1', '.', '.', 'Wd', '.']`.

Conclusion: the first phantom is synthetic cold-start pollution. The second is a real wide/extra event represented under the previous legal-ball key (`1.4#1`) instead of the GT convention (`1.5#0` with unchanged legal-ball count).

## 4. Bowler Attribution Missing Or Lagging

Root-cause candidate: bowler identity exists in runtime trackers, but the offline UI snapshot stream either drops it or emits it from a lagging ledger.

Evidence for Dubey:

- Pipeline snapshot lines 2-11 have `bowler_name=null` through `2.2`.
- GT lines 1-7 expect `bowler_name=Dubey`.
- Log line 171: `[BOWLER SEED] Saurabh Dubey figures seeded`.
- Log lines 188 and 191: `[BOWLER-TRACKER-RESEED]` and `[BOWLER-OBSERVE] ... Saurabh Dubey ... LOCKED`.
- Log line 523: `[BOWL-DELTA] Saurabh Dubey +runs=0 +balls=1 ... overs=1.1`.
- Log lines 518-519 and 2356-2357 show repeated stat-guard suppression of broadcast bowler figure regressions.

Evidence for Green:

- GT line 8 expects Green at `2.1`, but pipeline snapshot line 10 still has `bowler_name=null`.
- Pipeline snapshot line 12 first emits `bowler_name=Green` at `2.3`, with `bowler_overs=0.2` while GT expects `0.3`.
- Log line 2993 records `bowl:Cameron Green` in scorer changes at `2.1`.
- Log line 3140 records `[BOWL-DELTA] Cameron Green +runs=1 +balls=1 ... overs=0.3` at F124.
- Log lines 3184 and 3186 show Green is observed but broadcast figure regression is suppressed.

Conclusion: this is not a pure recognizer miss. Runtime sees Dubey and Green, but snapshot emission lags or omits bowler fields while stat guards suppress regressing broadcast figures.

## 5. Wide At 1.5 Missing From Extras Counters

Root-cause candidate: the token-level wide is recorded, but extras counters are not updated in the snapshot ledger when the wide comes through `this_over_tokens`/observed-token flow rather than direct extras counters.

Evidence:

- Pipeline snapshot line 8 has token `"Wd"` but `extras_total=0` and `extras_wd=0`.
- GT line 5 has token `"Wd"`, `extras_total=1`, and `extras_wd=1`.
- Runtime log line 2350 shows `[THIS OVER] ['.', '1', '.', '.', 'Wd', '.']`.
- Runtime log line 2360 has `AFTER_this_over_src=.(bcast),1(obs),.(obs),.(obs),Wd(obs),.(obs)`.
- The strip at log lines 2327-2333 still says `extras=null`, so the explicit scoreboard extras field did not feed the counters.

Conclusion: the pipeline detects the wide token but fails to reflect it in `extras_total` / `extras_wd` in the snapshot output. The token path and extras-counter path are split.

## 6. 2.3 Score Mismatch

Root-cause candidate: snapshot alignment / stale-score inference, not a duplicate token.

Evidence:

- Diff line 130: at `2.3`, pipeline score `16` vs GT score `14`.
- Diff line 142: pipeline tokens `["1","1","2"]` vs GT `["1","1","."]`.
- Pipeline snapshot line 12: `2.3`, score `16`, token `"2"`, `event_index=0`.
- GT line 10: `2.3`, score `14`, token `"."`.
- `d008/window_debug.json` records `delivery_num=8`, `over_number=2.3`, `event_type=2_RUNS`, `runs=2`.
- Log line 3910 is the key contradiction: the visible text is already `DC 20-0 (2.4) ... GREEN 1 1 6`, but the same detail row has `scorer_changes=['score->16', 'overs->2.3', ...]` and `AFTER_this_over=['?', '1', '2']`.
- Log line 3909: `[SM] Overs regression (2.4->2.3) - deferred (1/2), ignoring frame`.
- Log lines 3897-3901 show `EXTRAS-INF-GATE`, score `16`, over `2.3`, and `THIS OVER ['?', '1', '2']`.

Conclusion: the `2.3` mismatch is a snapshot/event alignment failure. A later scoreboard read around `2.4`/`20-0` is being reconciled as a `2.3` `+2` event. It is not a duplicate token; it is a wrong token attached to the wrong delivery boundary.

## Delivery Folder Notes

- `d001/window_debug.json`: `over_number=1.1`, `event_type=DOT`, fallback window, no OpenScout match.
- `d002/window_debug.json`: `over_number=1.2`, `event_type=1_RUNS`, retrospective span.
- `d005/window_debug.json`: `over_number=1.4`, `event_type=EXTRA`, confirming the `1.4#1` phantom is a real extra keyed differently than GT.
- `d006/window_debug.json`: `over_number=1.5`, `event_type=DOT`, the legal ball after the wide.
- `d008/window_debug.json`: `over_number=2.3`, `event_type=2_RUNS`, confirming the incorrect `2` was emitted as a delivery event.
- `d009/window_debug.json`: `over_number=2.4`, `event_type=FOUR`.
- `d010/window_debug.json`: `over_number=2.5`, `event_type=FOUR`.
- `d011/window_debug.json`: `over_number=3.0`, outside the trimmed GT slice.

## Fix Surface Candidates

No fixes made.

1. Snapshotter warm-seed should initialize from a known GT/live state when the clip begins mid-innings, or avoid emitting inferred pre-roll balls such as synthetic `0.6`.
2. Snapshot export should move completed-over tokens into `recent_over_n_minus_1` at the over boundary instead of carrying synthetic first-over tokens into `1.1`.
3. Extra keying should align non-legal events with the GT convention: a wide after `1.4` should key as `1.5#0` with unchanged `balls_total`, not as `1.4#1`.
4. Snapshot ledger should increment `extras_total` and `extras_wd` whenever `this_over_tokens` receives `Wd`.
5. Bowler fields should be emitted from the same runtime bowler ledger that logs `BOWLER-OBSERVE` / `BOWL-DELTA`, not from a lagging or nullable snapshot path.
6. The snapshot/event aligner should reject a `2.3` event inferred from frames whose visible strip has already advanced to `2.4`.

## Fixed-Session Rerun Comparison

Rerun session: `replay_kkrdc_10min_20260526_200243`.

Artifact checks:

- `files/logs/deliveries/replay_kkrdc_10min_20260526_200243/d*/delivery_window.mp4`: present per corrected artifact path.
- `files/logs/deliveries/replay_kkrdc_10min_20260526_200243/d*/window_debug.json`: present per corrected artifact path.
- `files/logs/openscout_deliveries/replay_kkrdc_10min_20260526_200243/`: present per corrected artifact path.
- `logs/openscout-replay_kkrdc_10min_20260526_200243.jsonl`: present.
- `logs/trace/replay_kkrdc_10min_20260526_200243.jsonl`: present per corrected artifact path.
- `/tmp/replay_kkrdc_10min_20260526_200243.log`: present.
- `files/logs/deliveries/replay_kkrdc_10min_20260526_200243/ui_snapshots.jsonl`: not present, so no new Track 1 diff was run.

Evidence from the rerun log:

- Log confirms the intended session id via `[SESSION-CONFIG] session_id=replay_kkrdc_10min_20260526_200243`.
- Match recorder wrote to `files/logs/deliveries/replay_kkrdc_10min_20260526_200243/match_replay_kkrdc_10min_20260526_200243.mp4`.
- Runtime delivery events still fired: 13 `[DELIVERY ENQUEUED]` lines and `[MATCH-SUMMARY] events_seen=13 spans_committed=12`.
- Corrected artifact paths show delivery windows, OpenScout deliveries, OpenScout JSONL, and trace output exist under the fixed session id.

Interpretation:

- The session-id split is fixed for match recording, delivery-window artifacts, OpenScout delivery artifacts, OpenScout JSONL naming, and trace naming.
- The absence of UI snapshots blocks fixed-session Track 1 comparison. No Track 1 behavior fixes should be made from this rerun alone.
- Trace is present at the corrected fixed-session path; no trace-code change is indicated from this check.
- Because this diagnostic clip still starts at `DC 10-0 (1.0)`, any next Track 1 diagnostic intended to validate cold-start behavior should start from `0.0`, not `1.0`.
- No fixes should be made until manual Track 2 labels from this fixed-session run are reviewed.

## Runtime-vs-GT Table (Fixed Session)

Inputs: `/tmp/replay_kkrdc_10min_20260526_200243.log`,
`logs/trace/replay_kkrdc_10min_20260526_200243.jsonl`, and
`files/logs/deliveries/replay_kkrdc_10min_20260526_193747/gt_trimmed_1p1_to_2p5.jsonl`.
This table uses fixed-session runtime events, not the stale `193747` UI diff. The replay log confirms the source used for this run was the derived clip
`files/logs/deliveries/kkrdc_20260524_10min_source/kkrdc_20260524_first10.ts` with replay `offset_s=0`, so the full-recording clip cut point is not re-verified by this runtime log alone.

| over.ball | GT token | runtime ball_event | runtime score | runtime striker/non-striker | bowler | extras | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1.1 | `.` | F8 `DOT \| 1.1` | `10-0 (1.1)` | Abishek Porel / KL Rahul | Saurabh Dubey | - | Event and score match, but striker/non-striker are reversed vs GT because runtime cold-started at `10-0 (1.0)` and seeded the opening state from the already-in-progress overlay. |
| 1.2 | `1` | F17 `1_RUNS \| 1.2` | `11-0 (1.2)` | Abishek Porel / KL Rahul | Saurabh Dubey | - | Event and score match; player and bowler ledgers remain polluted from the `10-0` cold start (`Saurabh Dubey 0-11` instead of GT `0-1`). |
| 1.3 | `.` | F37 `DOT \| 1.3` | `11-0 (1.3)` | Abishek Porel / KL Rahul | Saurabh Dubey | - | Event and score match; log shows `STAT-GUARD` suppressing scoreboard regressions caused by the cold-start ledger. |
| 1.4 | `.` | F41 `DOT \| 1.4` | `11-0 (1.4)` | Abishek Porel / KL Rahul | Saurabh Dubey | - | Event and score match; bowler export still carries the inflated same-over baseline. |
| 1.5 wide | `Wd` | F51 `EXTRA \| 1.4` | `12-0 (1.4)` | Abishek Porel / KL Rahul | Saurabh Dubey | `Wd`, innings extras `1` | Wide is detected and `Wd` is appended, but runtime keys it to `1.4`; GT convention records the wide at the next ball slot `1.5` with no legal ball consumed. |
| 1.5 legal | `.` | F70 `DOT \| 1.5` | `12-0 (1.5)` | Abishek Porel / KL Rahul | Saurabh Dubey | `Wd` in this_over | Legal dot and score match after the wide, but the cold-start player ledger remains wrong. |
| 1.6 | `.` | F103 duplicate `EXTRA \| 1.5`, then F104 queued `DOT \| 2.0` | `12-0 (2.0)` | Abishek Porel / KL Rahul | Saurabh Dubey | second `Wd`, innings extras `2` | GT closing dot is not emitted as `1.6`; runtime decomposes rollover into a duplicate wide and a queued dot at `2.0`, creating the extras-counter inconsistency. |
| 2.1 | `1` | F105 `1_RUNS \| 2.1` | `13-0 (2.1)` | Abishek Porel / KL Rahul | Saurabh Dubey, then Cameron Green at F106 | extras floor now `2` | Event and score match, but bowler attribution lags: the delivery is logged under Saurabh Dubey and the Green swap is picked up one frame later. |
| 2.2 | `1` | F119 `1_RUNS \| 2.2` | `14-0 (2.2)` | Abishek Porel / KL Rahul | Cameron Green | extras floor `2` | Event, score, and bowler identity match; batter totals are still guarded because the runtime ledger began from polluted 1.0 state. |
| 2.3 | `.` | F129 `DOT \| 2.3` | `14-0 (2.3)` | Abishek Porel / KL Rahul | Cameron Green | extras floor `2` | Event and score match; `SCORE-INF-GATE`/`EXTRAS-INF-GATE` continue to reject impossible scoreboard-derived batter sums. |
| 2.4 | `6` | F148 `SIX \| 2.4` | `20-0 (2.4)` | Abishek Porel / KL Rahul | Cameron Green | extras floor `2` | Event and score match GT. Runtime credits the six to KL Rahul in `BAT-DELTA` while `striker_this_ball` remains Abishek Porel, so striker attribution is internally inconsistent. |
| 2.5 | `4` | F161 `SIX \| 2.5` | `26-0 (2.5)` | Abishek Porel / KL Rahul | Cameron Green | extras inferred as `7` next frame | Runtime does not match the GT slice. The frame text also shows `DC 26-0 (2.5)` and `this_over=1 1 6 4`, so this row needs source-clip cut verification before declaring a Track 1 scoring bug. |

Runtime defects supported by this table:

- Cold-start from `10-0 (1.0)` pollutes striker/non-striker and individual ledgers from the first emitted delivery.
- The first wide is detected, but it is emitted at `1.4` while GT keys it as `1.5`; rollover then creates a second wide at F103.
- `Wd` appears in `this_over`, but extras counters diverge from GT after F103 (`innings_total=2` vs GT `extras_wd=1`).
- Bowler recognition sees both Saurabh Dubey and Cameron Green, but the exported bowler lags through the first ball of Green's over.
- The `2.5` mismatch is not yet a proven pipeline bug because the fixed-session log only proves replay offset `0` within the derived 10-minute clip, not the full-recording cut alignment.

## Combined Replay Root Cause (20260526_222335)

Inputs: `files/docs/replay_live_kkrdc_20260526_10min_combined_diff.md`,
`files/logs/deliveries/replay_kkrdc_10min_combined_20260526_222335/ui_snapshots.jsonl`,
`/tmp/replay_kkrdc_10min_combined_20260526_222335.log`,
`logs/trace/replay_kkrdc_10min_combined_20260526_222335.jsonl`, and
`files/logs/deliveries/replay_kkrdc_10min_20260526_193747/gt_trimmed_1p1_to_2p5.jsonl`.

Combined diff summary: `matched=12`, `missing=0`, `phantom=1`, `divergences=132`. Top classified surfaces are `F-B-ad-occlusion=12`, `F-A-commit-lag=12`, `Per-batter-ledger-drift=6`, and `Recent-overs-drop=2`. The large unclassified remainder is still the known mid-innings cold-start ledger: the clip begins at `DC 10-0 (1.0)`, so the runtime seeds Abishek Porel / KL Rahul and Saurabh Dubey totals from an already-in-progress overlay rather than from innings start.

The single phantom is `2.1#1`. This is not a new missing-delivery class. The combined UI stream first emits a duplicate/rollover wide snapshot at `over_ball=2.1`, `score=12`, `extras_total=2`, `this_over_tokens=[".","1",".",".","Wd",".","Wd"]`; the real `2.1 1_RUNS` snapshot then lands at the same key with `event_index=1`, so the diff marks it phantom. Runtime still has the duplicate second wide/rollover artifact recorded in the match summary (`1.5 EXTRA`, then `2.0 DOT`) before the real `2.1`.

`Wd` propagation is fixed for the first accepted wide: combined UI snapshot line 5 exports `over_ball=1.5`, unchanged legal-ball count `balls_total=10`, `this_over_tokens=[".","1",".",".","Wd"]`, `extras_total=1`, and `extras_wd=1`, matching the GT convention. The remaining extras divergence starts only after the duplicate second wide: pipeline exports `extras_total=2` / `extras_wd=2` from `1.6` onward while GT stays at `1`.

Bowler fields are still lagging/polluted. First-over bowler identity is present but full-name canonicalization and cold-start figures still produce `Saurabh Dubey 1.x / 10+ runs` versus GT `Dubey 0.x / 0-2 runs`; at the over break the combined UI has `1.6` under `Ajinkya Rahane` and the first real `2.1` run under `Ajinkya Rahane` before later rows switch to Cameron Green. This is runtime/export state, not a Track 2 issue.

Striker/non-striker divergence is still consistent with the mid-innings cold-start at `10-0 (1.0)`. The log shows the auto-anchor setting `striker None->Abishek Porel` and `non None->KL Rahul` during cold start, while GT expects Rahul/Porel at `1.1` and later deterministic rotations from a clean innings ledger. This pass intentionally did not fix cold-start striker pollution.

Runtime and UI snapshots now agree on `this_over_tokens` for the fixed export path. Examples: runtime `AFTER_this_over=['.']` at `1.1` matches UI line 1, `['.','1','.','.','Wd']` at the first wide matches UI line 5, and the second-over rows match the runtime tokens (`["1","1",".","6","6"]` at `2.5`). The disagreement with GT is therefore no longer "missing UI snapshots"; it is runtime duplicate-wide/rollover state plus the known cold-start ledger.

Smallest next Track 1 fix candidate: suppress or correctly re-key duplicate non-legal extra snapshots at over rollover. Exact targets: `files/test_pipeline.py` for the bounded-replay UI snapshot emitter (`_ui_snapshot_overs_str` / the `_ui_snapshot_fh` write site) if we only suppress/export-correct the duplicate; `files/score_manager.py` if we fix the underlying duplicate wide state before export. Because the duplicate changes runtime extras counters, the safer next fix is in `files/score_manager.py`; do not paper over it only in the snapshotter unless the immediate goal is a diff-only export shim.

## Finalcheck over-suppression audit

Inputs: `files/docs/replay_live_kkrdc_20260527_10min_finalcheck_diff.md`,
`/tmp/replay_kkrdc_10min_finalcheck_20260527_005833.log`,
`files/logs/deliveries/replay_kkrdc_10min_finalcheck_20260527_005833/ui_snapshots.jsonl`,
`logs/trace/replay_kkrdc_10min_finalcheck_20260527_005833.jsonl`,
and the current `files/eyes/commentary.py` / `files/test_pipeline.py`.

Finalcheck diff summary: `matched=6`, `missing=6`, `phantom=2`,
`divergences=72`. The six missing GT balls are `1.3`, `1.4`, `1.5#1`,
`1.6`, `2.1`, and `2.3`.

Suppression evidence:

| Missing GT ball | Corresponding runtime evidence | Verdict |
|---|---|---|
| `1.3` | `F30`, log line 1034: `[BED] Suppressing scoreless legal-ball tick without live-play evidence after dead time`; same frame line 1025 advances `overs: 1.2 → 1.3`, line 1031 has `score→11`, and line 1052 has `action=The camera shows two players, likely discussing strategy during a break in play` with `AFTER_this_over=['.','1','?']`. | Suppressed by the new guard. This is the first exact over-suppression. |
| `1.4` | `F41`, log line 1345 suppresses the scoreless legal tick; line 1336 advances `overs: 1.3 → 1.4`, line 1342 keeps score at `11`, and line 1365 records `AFTER_this_over=['.','1','?','?']`. | Suppressed by the same guard. |
| `1.5#1` | The wide itself emitted at `F52` (`EXTRA | 1.4`, log lines 1621/1637). The legal re-bowl after the wide was suppressed at `F63`, line 1722; line 1710 advances `overs: 1.4 → 1.5`, line 1719 keeps score at `12`, and line 1738 records `AFTER_this_over=['.','1','?','?','Wd','?']`. | Suppressed by the same guard. |
| `1.6` | `F83`, line 2347 suppresses the over-completing legal tick; line 2337 advances `overs: 1.5 → 2.0`, line 2344 keeps score at `12`, and line 2364 records `AFTER_score=12-0(2.0)` with no `ball_event`. | Suppressed by the same guard. |
| `2.1` | `F96`, line 2535 suppresses the scoreless `2.1` legal tick; line 2518 advances `overs: 2.0 → 2.1`, line 2532 keeps score at `12`, and line 2555 has `action=The players are walking around the field between deliveries`. The later `F100` event emits `EXTRA | 2.1` at lines 2633/2646, which is not the GT `2.1` legal single. | The false `2.1 DOT` is gone, but the broad guard also leaves the real `2.1` GT ball missing/misaligned. |
| `2.3` | `F120`, line 3315 suppresses the scoreless legal tick; line 3304 advances `overs: 2.2 → 2.3`, line 3312 keeps score at `14`, and line 3333 records `AFTER_this_over=['?','Wd','1','?']` with no `ball_event`. | Suppressed by the same guard. |

The guard did not directly suppress non-dot scoring events. The suppression
branch in `BallEventDetector.detect()` only fires when `balls_delta == 1`,
`s_delta == 0`, and `w_delta == 0`; the finalcheck scoring events still fired
for `EXTRA | 1.4`, `EXTRA | 2.1`, `1_RUNS | 2.2`, `SIX | 2.4`, `FOUR | 2.5`,
and `2_RUNS | 3.0`.

The exact over-broad condition is the caller-side block added for
`should_block_scoreless_legal_tick(_last_cam, _last_phase, current_action)`.
That helper returns true for every `frame_phase == "between_play"` and for
generic break/between-delivery action text. In finalcheck, normal post-delivery
scoreboard confirmation frames are often `closeup/between_play` or
`bowlers_end/between_play`; they carry the first reliable over tick after the
delivery has already completed. Blocking every scoreless legal tick on those
frames suppresses real dots and legal re-bowls, not just the false post-ad
`2.1 DOT`.

Narrower fix direction: keep the false-post-ad suppression tied to an actual
dead-time transition or explicit dead/break evidence, not to all
`between_play`. A candidate condition is: suppress a scoreless legal tick only
when `balls_delta == 1`, `s_delta == 0`, `w_delta == 0`, no batter-ball
evidence, and either (a) the post-dead-time guard is currently active after an
ad/graphic/replay skip, or (b) action text contains hard dead-time phrases such
as `taking a break` / `no delivery happening` / `advertisement` / `replay`.
Do not block solely because `frame_phase == "between_play"` or because generic
text says `between deliveries` after an over tick.

## Current status before next rerun

- Fixed: duplicate `Wd` signature is absent after the `commentary.py` patch.
- Fixed: over-broad `between_play` scoreless-legal suppression has been narrowed so normal `between_play` frames are not blocked outside the post-dead-time guard.
- Fixed: `ADVERTISEMENT` frames now arm the dead-time guard, targeting the proven F95 false `2.1 DOT` condition.
- Still unresolved: early stream misses/miskeys `1.1` and `1.2`; finalpass emitted `1.2 EXTRA` instead of GT `1.2 1_RUN`.
- Still unresolved: `1.5` wide keying / `1.5#1` mismatch.
- Still unresolved: `2.3` / `2.4` / `2.5` content drift varies by run and may be downstream of early event alignment.
- Track 2: `d002` retrospective cutoff regression is fixed with the `2.5s` threshold; final validation is still pending after the Track 1 F95 fix.

Next replay scope: confirm the F95 false `2.1 DOT` is gone after the ad-return guard fix, not prove the whole event stream is complete.

## Adguard residual audit

Inputs: `/tmp/replay_kkrdc_10min_adguard_20260527_014643.log`,
`/tmp/replay_kkrdc_10min_adguard_20260527_014643_diff.md`,
`files/logs/deliveries/replay_kkrdc_10min_adguard_20260527_014643/ui_snapshots.jsonl`,
and `files/logs/deliveries/replay_kkrdc_10min_adguard_20260527_014643/d*/window_debug.json`.

Adguard diff headline: `matched=11`, `missing=1`, `phantom=1`,
`divergences=108`.

The single missing GT ball is `1.3`. Runtime saw the strip at `1.3` after a
graphic/dead-time sequence, padded the over with a `?`, and then suppressed the
scoreless legal tick on the resume guard path rather than emitting `DOT | 1.3`.
Evidence: F33 pads `this_over` to `['.', '1', '?']`; F37 resumes from
dead-time, logs `[BED] Suppressing scoreless legal-ball tick without live-play
evidence after dead time`, and the UI stream jumps from `1.2` to `1.4`.

The single phantom is `2.6`. It is outside the trimmed GT comparison window
(`1.1` through `2.5`) and corresponds to the pipeline continuing one later
legal event (`2_RUNS | 3.0` runtime / UI key `2.6`). Treat it as a comparison
boundary artifact unless a wider GT window proves the event itself wrong.

These are separate root causes. The missing `1.3` is a residual guard/timing
issue after graphic/dead-time resume, not the duplicate-wide bug and not the F95
ad-return bug. The `2.6` phantom is a diff-window boundary issue.

The remaining `1.3` issue is not primarily mid-innings clip start, wide keying,
or a BallEventDetector scoring error. It is the caller-side post-dead-time
scoreless-legal gate suppressing a real `1.3 DOT` after a graphic/dead-time
resume with no live evidence. Cold-start ledger pollution still explains many
field divergences, but not the missing event key itself.

Track 2 `d002` used fallback because this run's `d002` is the now-correct
`1.2 1_RUNS` event and no retrospective span candidate was available: its
`window_debug.json` has `tags=[]`, `legacy_window.span_start=null`,
`legacy_window.span_end=null`, and `window_reason=v3_and_legacy_returned_none`.
This is not the previously fixed cutoff-rejection regression.

`d002` fallback is not proven to require another Track 2 selector fix. The clip
is a long delayed fallback window (`event_ts-24s` to `event_ts-4s`,
`frame_count=532`), but its classifier output is `layer2_unavailable`,
`untrackable=true`, and `commentary_line=no classification available`. Manual
clip review should decide whether it is visually acceptable; if not, the likely
fix surface is early retrospective tag availability/capture, not the 2.5s
retrospective rejection threshold.

### Adguard manual dNNN review

Manual labels for `replay_kkrdc_10min_adguard_20260527_014643`:

- Missing delivery between `d002` and `d003`: GT `1.3 DOT` is absent from the
  dNNN sequence.
- `d004` BAD: replay, not delivery.
- `d007` PARTIAL/BAD: old `2.1` window problem; starts at/near bat contact and
  misses release.
- All other dNNN windows are OK.
- `d012` is OK and corresponds to `3.0`.

The `1.3` miss was not an absence of scoreboard evidence. The run saw `1.3`
repeatedly: F30 had `VISIBLE_TEXT: DC 11-0 (1.3)`, F33 advanced/padded
`this_over` to `['.', '1', '?']`, and F37 processed `score=11-0 (1.3)`. The
event failed because the post-dead-time scoreless-legal guard suppressed the
real scoreless tick on F37: `[BED] Suppressing scoreless legal-ball tick without
live-play evidence after dead time`. This is a Track 1 guard/timing miss, not a
Track 2 selector miss.

`d004` is `1.4 EXTRA` / wide. The wide was first suspected at F50
(`score+1 at overs=1.4 — will confirm next frame`) and finally emitted at F62
after the score stayed at 12: `[BALL EVENT] EXTRA | 1.4`. Its dNNN window used
delayed fallback from `event_ts-24s` to `event_ts-4s`; that pre-event band
contains the post-action/replay/injury context around F52/F53 rather than the
wide release. This is primarily a Track 1 event timing problem: the event's
confirmation timestamp is late relative to the actual wide, so fallback cuts
replay even though the selector follows its configured rule.

`d007` is `2.1 1_RUNS`. The `2.1` event itself is now correct and emitted at
F98 after the ad block. Its window selected `retrospective_span` from a single
`bowlers_end/release` tag at `1779818074.325`, with clip
`1779818072.325-1779818075.825` and safe margin `4.677s`. Manual review says
that short span starts at/near bat contact and misses release, so this is not
the F95 false-DOT Track 1 bug. It is a Track 2 retrospective selector/cut
quality problem around a too-late or too-sparse release tag.

Smallest next fix if we patch again: address the only remaining Track 1 diff
miss first. Exact target: `files/test_pipeline.py`, the ball-detection caller
where `_post_dead_time_scoreless_legal_guard`, `_block_scoreless_legal`, and
`allow_scoreless_legal` are computed before `ball_detector.detect()`. The fix
should distinguish ad-return suppression from graphic/other resume frames that
carry real over progress; do not broaden generic `between_play` blocking.

## Clean guard-strip validation

Session: `replay_kkrdc_10min_guardstrip_clean_20260527_100933`.

Preflight passed: `files/match_state_cache.json` was removed, immediately
verified absent (`CACHE_PREFLIGHT=absent`), and the replay logged
`[CACHE] No cached state found — starting fresh`. No `HOT-RESUME` marker
appeared. Discard the prior `replay_kkrdc_10min_guardstrip_20260527_022855`
validation attempt because it hot-resumed from stale cache at `24/0 (2.5)`.

Clean Track 1 diff: `matched=11`, `missing=1`, `phantom=1`,
`divergences=111`. The guard-strip fix succeeded for the target cases:
`1.3 DOT` emitted, the false scoreless `2.1 DOT` did not appear, the real
`2.1 1_RUNS` emitted correctly, and the duplicate `Wd` signature stayed
absent. The run emitted one `Wd` / `EXTRA` only.

Residuals after the clean run:

1. Remaining missing GT ball: `1.1`.
2. Remaining phantom: `2.6`.
3. `dNNN` manual review is still pending for the clean run.
4. OpenScout has one missing non-action mp4; treat as a low-priority audit
   artifact issue, not a Track 1 blocker.

Track 2 side facts from the same run: dNNN source counts are
`v3_chunker_fallback=11` and `retrospective_span=1`, with `12` delivery-window
mp4s. `d002` is now `1.3 DOT` via fallback, not the earlier `1.2` event.
OpenScout audit fields are present, all `12/12` delivery mp4s exist, and
`loop_e429_total=0`.
