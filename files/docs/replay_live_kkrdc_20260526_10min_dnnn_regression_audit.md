# KKR/DC 10-Minute dNNN Regression Audit

No fixes or reruns were performed for this audit.

## Inputs

- GOOD baseline: `replay_kkrdc_10min_20260526_204204`, log `/tmp/replay_kkrdc_10min_20260526_204204.log`, windows `files/logs/deliveries/replay_kkrdc_10min_20260526_204204/d*/window_debug.json`.
- REGRESSED: `replay_kkrdc_10min_combined_20260526_222335`, log `/tmp/replay_kkrdc_10min_combined_20260526_222335.log`, windows `files/logs/deliveries/replay_kkrdc_10min_combined_20260526_222335/d*/window_debug.json`, snapshots `files/logs/deliveries/replay_kkrdc_10min_combined_20260526_222335/ui_snapshots.jsonl`.

## Method

- `event_ts` values are wall-clock timestamps from `window_debug.json`; absolute values are not comparable across sessions, so relative `event_ts` is also shown as seconds since each run's `d001`.
- Log evidence uses the `BALL EVENT` line number and matching `DETAIL|F...` line number from the replay log.
- `dead/live` is derived from the Scout camera/phase on the emitting frame: `ad`, `graphic`, `replay`, `other`, `advertisement`, or `graphic` are `dead`; `closeup`/`between_play` are marked `between/dead-risk`; live action views are `live`.

## GOOD dNNN Table

|dNNN|over|type|runs|event_ts(rel)|source|clip offsets|manual|log frame/line|score/over|cam/phase|this_over before -> after|score before -> after|dead/live|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|d001|1.1|DOT|0|1779799367.189 (0.000)|v3_chunker_fallback|-24.000/-4.000|not explicitly recorded; baseline described mostly good|F8 L482 / detail L483|10-0(1.1)|closeup/between_play|[] -> ['.']|10-0(1.0) -> 10-0(1.1)|between/dead-risk|
|d002|1.2|1_RUNS|1|1779799405.634 (38.445)|retrospective_span|-7.108/-3.608|known miss under review|F16 L768 / detail L769|11-0(1.2)|closeup/between_play|['.'] -> ['.', '1']|10-0(1.1) -> 11-0(1.2)|between/dead-risk|
|d003|1.3|DOT|0|1779799465.482 (98.293)|retrospective_span|-6.778/-3.278|known miss under review|F29 L1244 / detail L1245|11-0(1.3)|closeup/between_play|['.', '1'] -> ['.', '1', '.']|11-0(1.2) -> 11-0(1.3)|between/dead-risk|
|d004|1.4|DOT|0|1779799510.092 (142.903)|v3_chunker_fallback|-24.000/-4.000|not explicitly recorded; baseline described mostly good|F39 L1513 / detail L1514|11-0(1.4)|closeup/between_play|['.', '1', '.'] -> ['.', '1', '.', '.']|11-0(1.3) -> 11-0(1.4)|between/dead-risk|
|d005|1.4|EXTRA|1|1779799558.669 (191.480)|v3_chunker_fallback|-24.000/-4.000|not explicitly recorded; baseline described mostly good|F52 L1817 / detail L1818|12-0(1.4)|closeup/between_play|['.', '1', '.', '.'] -> ['.', '1', '.', '.', 'Wd']|12-0(1.4) -> 12-0(1.4)|between/dead-risk|
|d006|1.5|DOT|0|1779799592.137 (224.948)|v3_chunker_fallback|-24.000/-4.000|not explicitly recorded; baseline described mostly good|F69 L1986 / detail L1987|None-None(None)|closeup/between_play|['.', '1', '.', '.', 'Wd'] -> ['.', '1', '.', '.', 'Wd', '.']|12-0(1.4) -> 12-0(1.5)|between/dead-risk|
|d007|1.5|EXTRA|1|1779799637.636 (270.446)|retrospective_span|-10.409/-4.486|known overlap/split candidate|F87 L2533 / detail L2534|12-0(2.0)|closeup/between_play|['.', '1', '.', '.', 'Wd', '.'] -> ['.', '1', '.', '.', 'Wd', '.', 'Wd']|12-0(1.5) -> 12-0(2.0)|between/dead-risk|
|d008|2.0|DOT|0|1779799640.921 (273.732)|v3_chunker_fallback|-24.000/-4.000|known overlap/split candidate|F88 L2580 / detail L2581|None-None(None)|closeup/between_play|['.', '1', '.', '.', 'Wd', '.', 'Wd'] -> ['.', '1', '.', '.', 'Wd', '.', 'Wd', '.']|12-0(2.0) -> 12-0(2.0)|between/dead-risk|
|d009|2.1|1_RUNS|1|1779799725.512 (358.323)|v3_chunker_fallback|-24.000/-4.000|not explicitly recorded; baseline described mostly good|F103 L2816 / detail L2817|13-0(2.1)|closeup/between_play|[] -> ['1']|12-0(2.0) -> 13-0(2.1)|between/dead-risk|
|d010|2.2|1_RUNS|1|1779799772.401 (405.212)|retrospective_span|-9.559/-4.665|not explicitly recorded; baseline described mostly good|F124 L3141 / detail L3147|14-0(2.2)|bowlers_end/between_play|['1'] -> ['1', '1']|13-0(2.1) -> 14-0(2.2)|between/dead-risk|
|d011|2.3|DOT|0|1779799827.668 (460.478)|v3_chunker_fallback|-24.000/-4.000|not explicitly recorded; baseline described mostly good|F135 L3703 / detail L3704|14-0(2.3)|closeup/between_play|['1', '1'] -> ['1', '1', '.']|14-0(2.2) -> 14-0(2.3)|between/dead-risk|
|d012|2.4|SIX|6|1779799865.708 (498.518)|v3_chunker_fallback|-24.000/-4.000|not explicitly recorded; baseline described mostly good|F150 L3998 / detail L4001|20-0(2.4)|closeup/between_play|['1', '1', '.'] -> ['1', '1', '.', '6']|14-0(2.3) -> 20-0(2.4)|between/dead-risk|
|d013|2.5|FOUR|4|1779799924.651 (557.462)|v3_chunker_fallback|-24.000/-4.000|not explicitly recorded; baseline described mostly good|F169 L4399 / detail L4401|24-0(2.5)|side_on/between_play|['1', '1', '.', '6'] -> ['1', '1', '.', '6', '4']|20-0(2.4) -> 24-0(2.5)|between/dead-risk|
|d014|3.0|2_RUNS|2|1779799970.550 (603.361)|v3_chunker_fallback|-24.000/-4.000|not explicitly recorded; baseline described mostly good|F185 L4811 / detail L4816|None-None(None)|bowlers_end/between_play|['1', '1', '.', '6', '4'] -> ['1', '1', '.', '6', '4', '2']|24-0(2.5) -> 26-0(3.0)|between/dead-risk|

## REGRESSED dNNN Table

|dNNN|over|type|runs|event_ts(rel)|source|clip offsets|manual|log frame/line|score/over|cam/phase|this_over before -> after|score before -> after|dead/live|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|d001|1.1|DOT|0|1779805546.137 (0.000)|v3_chunker_fallback|-24.000/-4.000|needs review / duplicate-check candidate where noted|F11 L437 / detail L442|10-0(1.1)|bowlers_end/release|['?'] -> ['.']|10-0(1.1) -> 10-0(1.1)|live|
|d002|1.2|1_RUNS|1|1779805565.788 (19.651)|v3_chunker_fallback|-24.000/-4.000|needs review / duplicate-check candidate where noted|F13 L541 / detail L542|11-0(1.2)|closeup/between_play|['.'] -> ['.', '1']|10-0(1.1) -> 11-0(1.2)|between/dead-risk|
|d003|1.3|DOT|0|1779805648.702 (102.565)|v3_chunker_fallback|-24.000/-4.000|needs review / duplicate-check candidate where noted|F36 L1154 / detail L1156|11-0(1.3)|closeup/between_play|['.', '1', '?'] -> ['.', '1', '.']|11-0(1.3) -> 11-0(1.3)|between/dead-risk|
|d004|1.4|DOT|0|1779805672.836 (126.699)|v3_chunker_fallback|-24.000/-4.000|needs review / duplicate-check candidate where noted|F41 L1356 / detail L1357|11-0(1.4)|closeup/between_play|['.', '1', '.'] -> ['.', '1', '.', '.']|11-0(1.3) -> 11-0(1.4)|between/dead-risk|
|d005|1.4|EXTRA|1|1779805716.322 (170.185)|v3_chunker_fallback|-24.000/-4.000|not recorded|F46 L1565 / detail L1566|None-None(None)|closeup/between_play|['.', '1', '.', '.'] -> ['.', '1', '.', '.', 'Wd']|12-0(1.4) -> 12-0(1.4)|between/dead-risk|
|d006|1.5|DOT|0|1779805777.823 (231.686)|v3_chunker_fallback|-24.000/-4.000|needs review / duplicate-check candidate where noted|F68 L1911 / detail L1913|12-0(1.5)|closeup/between_play|['.', '1', '.', '.', 'Wd', '?'] -> ['.', '1', '.', '.', 'Wd', '.']|12-0(1.5) -> 12-0(1.5)|between/dead-risk|
|d007|1.5|EXTRA|1|1779805795.638 (249.501)|v3_chunker_fallback|-24.000/-4.000|needs review / duplicate-check candidate where noted|F72 L2095 / detail L2096|12-0(2.0)|closeup/between_play|['.', '1', '.', '.', 'Wd', '.'] -> ['.', '1', '.', '.', 'Wd', '.', 'Wd']|12-0(1.5) -> 12-0(2.0)|between/dead-risk|
|d008|2.0|DOT|0|1779805874.192 (328.055)|v3_chunker_fallback|-24.000/-4.000|needs review / duplicate-check candidate where noted|F84 L2191 / detail L2197|12-0(2.0)|bowlers_end/release|['.', '1', '.', '.', 'Wd', '.', 'Wd'] -> ['.', '1', '.', '.', 'Wd', '.', 'Wd', '.']|12-0(2.0) -> 12-0(2.0)|live|
|d009|2.1|1_RUNS|1|1779805881.570 (335.433)|retrospective_span|-7.836/-4.336|not recorded|F86 L2300 / detail L2303|13-0(2.1)|bowlers_end/between_play|[] -> ['1']|12-0(2.0) -> 13-0(2.1)|between/dead-risk|
|d010|2.2|1_RUNS|1|1779805931.797 (385.659)|v3_chunker_fallback|-24.000/-4.000|needs review / duplicate-check candidate where noted|F103 L2661 / detail L2662|14-0(2.2)|closeup/between_play|['1'] -> ['1', '1']|13-0(2.1) -> 14-0(2.2)|between/dead-risk|
|d011|2.3|DOT|0|1779805986.117 (439.980)|v3_chunker_fallback|-24.000/-4.000|needs review / duplicate-check candidate where noted|F110 L3010 / detail L3011|14-0(2.3)|closeup/between_play|['1', '1'] -> ['1', '1', '.']|14-0(2.2) -> 14-0(2.3)|between/dead-risk|
|d012|2.4|SIX|6|1779806029.346 (483.209)|v3_chunker_fallback|-24.000/-4.000|needs review / duplicate-check candidate where noted|F125 L3251 / detail L3254|20-0(2.4)|closeup/between_play|['1', '1', '.'] -> ['1', '1', '.', '6']|14-0(2.3) -> 20-0(2.4)|between/dead-risk|
|d013|2.5|SIX|6|1779806076.910 (530.772)|v3_chunker_fallback|-24.000/-4.000|needs review / duplicate-check candidate where noted|F137 L3421 / detail L3423|None-None(None)|closeup/between_play|['1', '1', '.', '6'] -> ['1', '1', '.', '6', '6']|20-0(2.4) -> 26-0(2.5)|between/dead-risk|

## Direct Sequence Comparison

|dNNN|GOOD event/source/offset|REGRESSED event/source/offset|Evidence|
|---|---|---|---|
|`d001`|1.1 DOT r0 / v3_chunker_fallback / -24.000/-4.000|1.1 DOT r0 / v3_chunker_fallback / -24.000/-4.000|GOOD d001 window_debug + log L482; REG d001 window_debug + log L437|
|`d002`|1.2 1_RUNS r1 / retrospective_span / -7.108/-3.608|1.2 1_RUNS r1 / v3_chunker_fallback / -24.000/-4.000|GOOD d002 window_debug + log L768; REG d002 window_debug + log L541|
|`d003`|1.3 DOT r0 / retrospective_span / -6.778/-3.278|1.3 DOT r0 / v3_chunker_fallback / -24.000/-4.000|GOOD d003 window_debug + log L1244; REG d003 window_debug + log L1154|
|`d004`|1.4 DOT r0 / v3_chunker_fallback / -24.000/-4.000|1.4 DOT r0 / v3_chunker_fallback / -24.000/-4.000|GOOD d004 window_debug + log L1513; REG d004 window_debug + log L1356|
|`d005`|1.4 EXTRA r1 / v3_chunker_fallback / -24.000/-4.000|1.4 EXTRA r1 / v3_chunker_fallback / -24.000/-4.000|GOOD d005 window_debug + log L1817; REG d005 window_debug + log L1565|
|`d006`|1.5 DOT r0 / v3_chunker_fallback / -24.000/-4.000|1.5 DOT r0 / v3_chunker_fallback / -24.000/-4.000|GOOD d006 window_debug + log L1986; REG d006 window_debug + log L1911|
|`d007`|1.5 EXTRA r1 / retrospective_span / -10.409/-4.486|1.5 EXTRA r1 / v3_chunker_fallback / -24.000/-4.000|GOOD d007 window_debug + log L2533; REG d007 window_debug + log L2095|
|`d008`|2.0 DOT r0 / v3_chunker_fallback / -24.000/-4.000|2.0 DOT r0 / v3_chunker_fallback / -24.000/-4.000|GOOD d008 window_debug + log L2580; REG d008 window_debug + log L2191|
|`d009`|2.1 1_RUNS r1 / v3_chunker_fallback / -24.000/-4.000|2.1 1_RUNS r1 / retrospective_span / -7.836/-4.336|GOOD d009 window_debug + log L2816; REG d009 window_debug + log L2300|
|`d010`|2.2 1_RUNS r1 / retrospective_span / -9.559/-4.665|2.2 1_RUNS r1 / v3_chunker_fallback / -24.000/-4.000|GOOD d010 window_debug + log L3141; REG d010 window_debug + log L2661|
|`d011`|2.3 DOT r0 / v3_chunker_fallback / -24.000/-4.000|2.3 DOT r0 / v3_chunker_fallback / -24.000/-4.000|GOOD d011 window_debug + log L3703; REG d011 window_debug + log L3010|
|`d012`|2.4 SIX r6 / v3_chunker_fallback / -24.000/-4.000|2.4 SIX r6 / v3_chunker_fallback / -24.000/-4.000|GOOD d012 window_debug + log L3998; REG d012 window_debug + log L3251|
|`d013`|2.5 FOUR r4 / v3_chunker_fallback / -24.000/-4.000|2.5 SIX r6 / v3_chunker_fallback / -24.000/-4.000|GOOD d013 window_debug + log L4399; REG d013 window_debug + log L3421|
|`d014`|3.0 2_RUNS r2 / v3_chunker_fallback / -24.000/-4.000|—|GOOD d014 window_debug + log L4811|

## Answers

1. First divergence: if window reason is included, `d001` differs (`GOOD` reason `v3_and_legacy_returned_none`; `REGRESSED` reason `retrospective_span_rejected_too_close_to_event`) while both still use delayed fallback with `-24/-4` offsets. The first source/clip-strategy divergence is `d002`: GOOD `d002` is `1.2 1_RUNS` from `retrospective_span` with offsets `-7.108/-3.608`; REGRESSED `d002` is the same score event from `v3_chunker_fallback` with offsets `-24.000/-4.000`. Evidence: GOOD `d002/window_debug.json` and log line 768; REGRESSED `d002/window_debug.json` and log line 541.
2. The REGRESSED run did not create an additional early `dNNN` event relative to GOOD through `2.4`: both runs contain `1.1 DOT`, `1.2 1_RUNS`, `1.3 DOT`, `1.4 DOT`, `1.4 EXTRA`, `1.5 DOT`, `1.5 EXTRA`, `2.0 DOT`, `2.1 1_RUNS`, `2.2 1_RUNS`, `2.3 DOT`, `2.4 SIX`. The event-sequence divergence appears at `d013`: GOOD has `2.5 FOUR`, REGRESSED has `2.5 SIX`; GOOD then emits `d014 3.0 2_RUNS`, while REGRESSED has no `d014`.
3. For the same over.ball, absolute `event_ts` shifts by the different session wall-clock start, so relative timing is the comparable evidence. Relative to `d001`, event timing already shifts at `d002`: GOOD `+38.445s`, REGRESSED `+19.651s`. Later differences are larger; e.g. `2.1` is GOOD `+358.323s`, REGRESSED `+316.381s`.
4. The same over.ball generally maps to the same `dNNN` through `2.4`. The content diverges at `d013`: both are `d013`, but GOOD maps `d013` to `2.5 FOUR` and REGRESSED maps `d013` to `2.5 SIX`. GOOD has the extra later `d014 3.0 2_RUNS`.
5. Fallback clip bounds did not change for events that use delayed fallback: both runs use `clip_start_ts=event_ts-24s` and `clip_end_ts=event_ts-4s`. The changed clips are those whose source changed, especially `d002`, `d003`, `d007`, `d009`, and `d010`, where GOOD sometimes used `retrospective_span` and REGRESSED often used delayed fallback or a different retrospective selection.
6. From the available evidence, manual bad clips in the REGRESSED duplicate-check document correspond to both sources: bad Track 1 event boundaries are present (`1.5 EXTRA`, `2.0 DOT`, later duplicate/split candidates), and Track 2 selection differs for the same events (`d002` source changes from retrospective span to fallback). This audit does not assign manual visual labels beyond those already recorded; the first measured regression is a Track 2 source/selection change at `d002`, while later recorded duplicate/split candidates also ride on Track 1 event-boundary artifacts.
7. Code-change implication from evidence: first measured divergence (`d002` source change) implicates Track 2 selection logic between the runs, specifically the retrospective-span safe-cutoff rejection path in `files/delivery_window_recorder.py` if it was present for REGRESSED and absent for GOOD. Track 1 event-stream changes are implicated later by the documented duplicate `Wd` / stale legal `DOT` surfaces, but they are not the first measured `dNNN` divergence in this audit.

## Changed Files in Current Working Tree

Exact historical diff between the `204204` run state and current working tree is not reconstructable from these artifacts alone unless the run state was tagged/committed. Current `git diff --name-only` reports:

- `files/ball_analyzer.py`
- `files/delivery_window_recorder.py`
- `files/eyes/agent.py`
- `files/eyes/commentary.py`
- `files/eyes/openscout_persistence.py`
- `files/match_state_cache.json`
- `files/scripts/replay_captured_scout_trace.py`
- `files/test_pipeline.py`
- `files/tests/test_chunker_v3.py`
- `files/tests/test_extras_source.py`

Current `git status --short` also includes many untracked research/docs artifacts; this audit does not treat untracked unrelated files as implicated.
