# Match trace report — `866ce150`
**Match:** WI vs RSA 2024 (YouTube test)
**Trace:** `logs/trace/866ce150.jsonl` — 74 records, 2026-05-02 12:25:31 → 2026-05-02 12:33:43 (duration 492s, 0.15 fps mean)
**Schema version:** 1 (reader: 1)

## Summary
- Records: **74**
- Decisions captured: **38** (7 distinct tags)
- Anomalies: **26 error**, 0 warn, 4 info, 7 advisory
- Mode windows: COLD_START×1, WARM×1

## Errors (operator action required)

### P8 — `error` at frame 158
- First evidence frame: 157
- Duration: 2 frames
- Verdict: this_over ball count drifted from overs-string arithmetic for ≥ sustain window. Likely missed rollover or a stale append.
- Evidence:
```json
{
  "overs": "1.0",
  "ball_within_over": 0,
  "this_over": [
    "100",
    ".",
    ".",
    ".",
    ".",
    "."
  ],
  "delta": 6
}
```
- Trace pointer: `jq -c 'select(.frame >= 155 and .frame <= 160)' <session>.jsonl`

### P8 — `error` at frame 159
- First evidence frame: 157
- Duration: 3 frames
- Verdict: this_over ball count drifted from overs-string arithmetic for ≥ sustain window. Likely missed rollover or a stale append.
- Evidence:
```json
{
  "overs": "1.0",
  "ball_within_over": 0,
  "this_over": [
    "100",
    ".",
    ".",
    ".",
    ".",
    "."
  ],
  "delta": 6
}
```
- Trace pointer: `jq -c 'select(.frame >= 155 and .frame <= 161)' <session>.jsonl`

### P8 — `error` at frame 170
- First evidence frame: 167
- Duration: 4 frames
- Verdict: this_over ball count drifted from overs-string arithmetic for ≥ sustain window. Likely missed rollover or a stale append.
- Evidence:
```json
{
  "overs": "1.0",
  "ball_within_over": 0,
  "this_over": [
    "100",
    ".",
    ".",
    ".",
    ".",
    "."
  ],
  "delta": 6
}
```
- Trace pointer: `jq -c 'select(.frame >= 165 and .frame <= 172)' <session>.jsonl`

### P8 — `error` at frame 171
- First evidence frame: 167
- Duration: 5 frames
- Verdict: this_over ball count drifted from overs-string arithmetic for ≥ sustain window. Likely missed rollover or a stale append.
- Evidence:
```json
{
  "overs": "1.0",
  "ball_within_over": 0,
  "this_over": [
    "100",
    ".",
    ".",
    ".",
    ".",
    "."
  ],
  "delta": 6
}
```
- Trace pointer: `jq -c 'select(.frame >= 165 and .frame <= 173)' <session>.jsonl`

### P8 — `error` at frame 172
- First evidence frame: 167
- Duration: 6 frames
- Verdict: this_over ball count drifted from overs-string arithmetic for ≥ sustain window. Likely missed rollover or a stale append.
- Evidence:
```json
{
  "overs": "1.0",
  "ball_within_over": 0,
  "this_over": [
    "100",
    ".",
    ".",
    ".",
    ".",
    "."
  ],
  "delta": 6
}
```
- Trace pointer: `jq -c 'select(.frame >= 165 and .frame <= 174)' <session>.jsonl`

### P8 — `error` at frame 173
- First evidence frame: 167
- Duration: 7 frames
- Verdict: this_over ball count drifted from overs-string arithmetic for ≥ sustain window. Likely missed rollover or a stale append.
- Evidence:
```json
{
  "overs": "1.0",
  "ball_within_over": 0,
  "this_over": [
    "100",
    ".",
    ".",
    ".",
    ".",
    "."
  ],
  "delta": 6
}
```
- Trace pointer: `jq -c 'select(.frame >= 165 and .frame <= 175)' <session>.jsonl`

### P8 — `error` at frame 174
- First evidence frame: 167
- Duration: 8 frames
- Verdict: this_over ball count drifted from overs-string arithmetic for ≥ sustain window. Likely missed rollover or a stale append.
- Evidence:
```json
{
  "overs": "1.0",
  "ball_within_over": 0,
  "this_over": [
    "100",
    ".",
    ".",
    ".",
    ".",
    "."
  ],
  "delta": 6
}
```
- Trace pointer: `jq -c 'select(.frame >= 165 and .frame <= 176)' <session>.jsonl`

### P8 — `error` at frame 175
- First evidence frame: 167
- Duration: 9 frames
- Verdict: this_over ball count drifted from overs-string arithmetic for ≥ sustain window. Likely missed rollover or a stale append.
- Evidence:
```json
{
  "overs": "1.0",
  "ball_within_over": 0,
  "this_over": [
    "100",
    ".",
    ".",
    ".",
    ".",
    "."
  ],
  "delta": 6
}
```
- Trace pointer: `jq -c 'select(.frame >= 165 and .frame <= 177)' <session>.jsonl`

### P8 — `error` at frame 176
- First evidence frame: 167
- Duration: 10 frames
- Verdict: this_over ball count drifted from overs-string arithmetic for ≥ sustain window. Likely missed rollover or a stale append.
- Evidence:
```json
{
  "overs": "1.0",
  "ball_within_over": 0,
  "this_over": [
    "100",
    ".",
    ".",
    ".",
    ".",
    "."
  ],
  "delta": 6
}
```
- Trace pointer: `jq -c 'select(.frame >= 165 and .frame <= 178)' <session>.jsonl`

### P8 — `error` at frame 177
- First evidence frame: 167
- Duration: 11 frames
- Verdict: this_over ball count drifted from overs-string arithmetic for ≥ sustain window. Likely missed rollover or a stale append.
- Evidence:
```json
{
  "overs": "1.0",
  "ball_within_over": 0,
  "this_over": [
    "100",
    ".",
    ".",
    ".",
    ".",
    "."
  ],
  "delta": 6
}
```
- Trace pointer: `jq -c 'select(.frame >= 165 and .frame <= 179)' <session>.jsonl`

### P8 — `error` at frame 178
- First evidence frame: 167
- Duration: 12 frames
- Verdict: this_over ball count drifted from overs-string arithmetic for ≥ sustain window. Likely missed rollover or a stale append.
- Evidence:
```json
{
  "overs": "1.0",
  "ball_within_over": 0,
  "this_over": [
    "100",
    ".",
    ".",
    ".",
    ".",
    "."
  ],
  "delta": 6
}
```
- Trace pointer: `jq -c 'select(.frame >= 165 and .frame <= 180)' <session>.jsonl`

### P7 — `error` at frame 180
- First evidence frame: 179
- Duration: 1 frames
- Verdict: Score / wickets reset to zero with same innings counter — full_reset called without a corresponding set_innings_2 transition. Inspect scorer.committed_changes and pipeline.mode.
- Evidence:
```json
{
  "score_before": 11,
  "score_after": 11,
  "wickets_after": 0,
  "innings": 1,
  "committed_changes": [
    "score\u219211",
    "overs\u21922.4",
    "wickets\u21920",
    "bat:Quinton de Kock=2(3)",
    "bat:Reeza Hendricks=2(4)"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 177 and .frame <= 182)' <session>.jsonl`

### P7 — `error` at frame 181
- First evidence frame: 180
- Duration: 1 frames
- Verdict: Score / wickets reset to zero with same innings counter — full_reset called without a corresponding set_innings_2 transition. Inspect scorer.committed_changes and pipeline.mode.
- Evidence:
```json
{
  "score_before": 11,
  "score_after": 11,
  "wickets_after": 0,
  "innings": 1,
  "committed_changes": [
    "score\u219211",
    "overs\u21924.0",
    "wickets\u21920",
    "bat:Quinton de Kock=2(2)",
    "bat:Reeza Hendricks=2(4)"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 178 and .frame <= 183)' <session>.jsonl`

### P3 — `error` at frame 182
- First evidence frame: 127
- Duration: 4 frames
- Verdict: UI bowler unchanged across 2+ overs of apparent play. Inspect BOWLER-LEAD arbitrations and BOWLER-LOCK-RELEASED/ACQUIRED counts.
- Evidence:
```json
{
  "bowler": "Akeal Hosein",
  "overs_unchanged": 4,
  "current_over": 4,
  "bowler_decisions_in_window": []
}
```
- Trace pointer: `jq -c 'select(.frame >= 125 and .frame <= 184)' <session>.jsonl`

### P7 — `error` at frame 182
- First evidence frame: 181
- Duration: 1 frames
- Verdict: Score / wickets reset to zero with same innings counter — full_reset called without a corresponding set_innings_2 transition. Inspect scorer.committed_changes and pipeline.mode.
- Evidence:
```json
{
  "score_before": 11,
  "score_after": 11,
  "wickets_after": 0,
  "innings": 1,
  "committed_changes": [
    "score\u219211",
    "overs\u21924.0",
    "wickets\u21920",
    "bat:Quinton de Kock=2(3)",
    "bat:Reeza Hendricks=2(4)",
    "bowl:Akeal Hosein"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 179 and .frame <= 184)' <session>.jsonl`

### P8 — `error` at frame 182
- First evidence frame: 181
- Duration: 2 frames
- Verdict: this_over ball count drifted from overs-string arithmetic for ≥ sustain window. Likely missed rollover or a stale append.
- Evidence:
```json
{
  "overs": "4.0",
  "ball_within_over": 0,
  "this_over": [
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?"
  ],
  "delta": 12
}
```
- Trace pointer: `jq -c 'select(.frame >= 179 and .frame <= 184)' <session>.jsonl`

### P7 — `error` at frame 183
- First evidence frame: 182
- Duration: 1 frames
- Verdict: Score / wickets reset to zero with same innings counter — full_reset called without a corresponding set_innings_2 transition. Inspect scorer.committed_changes and pipeline.mode.
- Evidence:
```json
{
  "score_before": 11,
  "score_after": 11,
  "wickets_after": 0,
  "innings": 1,
  "committed_changes": [
    "score\u219211",
    "overs\u21924.0",
    "bat:Quinton de Kock=2(3)",
    "bat:Reeza Hendricks=2(4)",
    "bowl:Akeal Hosein"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 180 and .frame <= 185)' <session>.jsonl`

### P8 — `error` at frame 183
- First evidence frame: 181
- Duration: 3 frames
- Verdict: this_over ball count drifted from overs-string arithmetic for ≥ sustain window. Likely missed rollover or a stale append.
- Evidence:
```json
{
  "overs": "4.0",
  "ball_within_over": 0,
  "this_over": [
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?"
  ],
  "delta": 12
}
```
- Trace pointer: `jq -c 'select(.frame >= 179 and .frame <= 185)' <session>.jsonl`

### P7 — `error` at frame 184
- First evidence frame: 183
- Duration: 1 frames
- Verdict: Score / wickets reset to zero with same innings counter — full_reset called without a corresponding set_innings_2 transition. Inspect scorer.committed_changes and pipeline.mode.
- Evidence:
```json
{
  "score_before": 11,
  "score_after": 11,
  "wickets_after": 0,
  "innings": 1,
  "committed_changes": [
    "FRAME_POISONED:None"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 181 and .frame <= 186)' <session>.jsonl`

### P8 — `error` at frame 184
- First evidence frame: 181
- Duration: 4 frames
- Verdict: this_over ball count drifted from overs-string arithmetic for ≥ sustain window. Likely missed rollover or a stale append.
- Evidence:
```json
{
  "overs": "4.0",
  "ball_within_over": 0,
  "this_over": [
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?"
  ],
  "delta": 12
}
```
- Trace pointer: `jq -c 'select(.frame >= 179 and .frame <= 186)' <session>.jsonl`

### P7 — `error` at frame 185
- First evidence frame: 184
- Duration: 1 frames
- Verdict: Score / wickets reset to zero with same innings counter — full_reset called without a corresponding set_innings_2 transition. Inspect scorer.committed_changes and pipeline.mode.
- Evidence:
```json
{
  "score_before": 11,
  "score_after": 11,
  "wickets_after": 0,
  "innings": 1,
  "committed_changes": [
    "SCORE-INF-GATE:proposed=11<bat_sum=8+extras=7",
    "overs\u21924.0",
    "wickets\u21920",
    "bat:Quinton de Kock=2(3)",
    "bat:Reeza Hendricks=6(5)",
    "bowl:Akeal Hosein"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 182 and .frame <= 187)' <session>.jsonl`

### P8 — `error` at frame 185
- First evidence frame: 181
- Duration: 5 frames
- Verdict: this_over ball count drifted from overs-string arithmetic for ≥ sustain window. Likely missed rollover or a stale append.
- Evidence:
```json
{
  "overs": "4.0",
  "ball_within_over": 0,
  "this_over": [
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?"
  ],
  "delta": 12
}
```
- Trace pointer: `jq -c 'select(.frame >= 179 and .frame <= 187)' <session>.jsonl`

### P7 — `error` at frame 186
- First evidence frame: 185
- Duration: 1 frames
- Verdict: Score / wickets reset to zero with same innings counter — full_reset called without a corresponding set_innings_2 transition. Inspect scorer.committed_changes and pipeline.mode.
- Evidence:
```json
{
  "score_before": 11,
  "score_after": 11,
  "wickets_after": 0,
  "innings": 1,
  "committed_changes": [
    "score\u219211",
    "overs\u21924.0",
    "wickets\u21920",
    "bat:Quinton de Kock=0(0)",
    "bat:Reeza Hendricks=0(0)",
    "bowl:Akeal Hosein"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 183 and .frame <= 188)' <session>.jsonl`

### P8 — `error` at frame 186
- First evidence frame: 181
- Duration: 6 frames
- Verdict: this_over ball count drifted from overs-string arithmetic for ≥ sustain window. Likely missed rollover or a stale append.
- Evidence:
```json
{
  "overs": "4.0",
  "ball_within_over": 0,
  "this_over": [
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?"
  ],
  "delta": 12
}
```
- Trace pointer: `jq -c 'select(.frame >= 179 and .frame <= 188)' <session>.jsonl`

### P7 — `error` at frame 198
- First evidence frame: 186
- Duration: 1 frames
- Verdict: Score / wickets reset to zero with same innings counter — full_reset called without a corresponding set_innings_2 transition. Inspect scorer.committed_changes and pipeline.mode.
- Evidence:
```json
{
  "score_before": 11,
  "score_after": 11,
  "wickets_after": 0,
  "innings": 1,
  "committed_changes": [
    "CORRECTION_BLOCKED:29"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 184 and .frame <= 200)' <session>.jsonl`

### P8 — `error` at frame 198
- First evidence frame: 192
- Duration: 7 frames
- Verdict: this_over ball count drifted from overs-string arithmetic for ≥ sustain window. Likely missed rollover or a stale append.
- Evidence:
```json
{
  "overs": "4.0",
  "ball_within_over": 0,
  "this_over": [
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?",
    "?"
  ],
  "delta": 12
}
```
- Trace pointer: `jq -c 'select(.frame >= 190 and .frame <= 200)' <session>.jsonl`

## Info

### P9 — `info` at frame 157
- First evidence frame: 127
- Duration: 30 frames
- Verdict: UI field 'striker' unchanged across 30 active-play records. Inspect rejections in the window — GUARD / GRAPHIC-FILTER suppressions are the common cause.
- Evidence:
```json
{
  "field": "striker",
  "stuck_value": "Quinton de Kock",
  "stale_records": 30,
  "rejections_in_window": []
}
```
- Trace pointer: `jq -c 'select(.frame >= 125 and .frame <= 159)' <session>.jsonl`

### P9 — `info` at frame 157
- First evidence frame: 127
- Duration: 30 frames
- Verdict: UI field 'non_striker' unchanged across 30 active-play records. Inspect rejections in the window — GUARD / GRAPHIC-FILTER suppressions are the common cause.
- Evidence:
```json
{
  "field": "non_striker",
  "stuck_value": null,
  "stale_records": 30,
  "rejections_in_window": []
}
```
- Trace pointer: `jq -c 'select(.frame >= 125 and .frame <= 159)' <session>.jsonl`

### P9 — `info` at frame 170
- First evidence frame: 157
- Duration: 13 frames
- Verdict: UI field 'score' unchanged across 13 active-play records. Inspect rejections in the window — GUARD / GRAPHIC-FILTER suppressions are the common cause.
- Evidence:
```json
{
  "field": "score",
  "stuck_value": 4,
  "stale_records": 13,
  "rejections_in_window": []
}
```
- Trace pointer: `jq -c 'select(.frame >= 155 and .frame <= 172)' <session>.jsonl`

### P9 — `info` at frame 198
- First evidence frame: 179
- Duration: 19 frames
- Verdict: UI field 'score' unchanged across 19 active-play records. Inspect rejections in the window — GUARD / GRAPHIC-FILTER suppressions are the common cause.
- Evidence:
```json
{
  "field": "score",
  "stuck_value": 11,
  "stale_records": 19,
  "rejections_in_window": []
}
```
- Trace pointer: `jq -c 'select(.frame >= 177 and .frame <= 200)' <session>.jsonl`

## Advisory (not counted toward errors/warnings — Q4)

### P4 — `advisory` at frame 181
- First evidence frame: 181
- Duration: 3 frames
- Verdict: Partnership total disagrees with sum of at-crease batter runs by >tolerance. Advisory only — partnership tracker / SM feeder divergence likely.
- Evidence:
```json
{
  "partnership_runs": 11,
  "sum_batter_runs": 4,
  "delta": 7,
  "contributors": [
    {
      "name": "Quinton de Kock",
      "runs": 2
    },
    {
      "name": "Reeza Hendricks",
      "runs": 2
    }
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 179 and .frame <= 183)' <session>.jsonl`

### P4 — `advisory` at frame 182
- First evidence frame: 182
- Duration: 3 frames
- Verdict: Partnership total disagrees with sum of at-crease batter runs by >tolerance. Advisory only — partnership tracker / SM feeder divergence likely.
- Evidence:
```json
{
  "partnership_runs": 11,
  "sum_batter_runs": 4,
  "delta": 7,
  "contributors": [
    {
      "name": "Quinton de Kock",
      "runs": 2
    },
    {
      "name": "Reeza Hendricks",
      "runs": 2
    }
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 180 and .frame <= 184)' <session>.jsonl`

### P4 — `advisory` at frame 183
- First evidence frame: 183
- Duration: 3 frames
- Verdict: Partnership total disagrees with sum of at-crease batter runs by >tolerance. Advisory only — partnership tracker / SM feeder divergence likely.
- Evidence:
```json
{
  "partnership_runs": 11,
  "sum_batter_runs": 4,
  "delta": 7,
  "contributors": [
    {
      "name": "Quinton de Kock",
      "runs": 2
    },
    {
      "name": "Reeza Hendricks",
      "runs": 2
    }
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 181 and .frame <= 185)' <session>.jsonl`

### P4 — `advisory` at frame 184
- First evidence frame: 184
- Duration: 3 frames
- Verdict: Partnership total disagrees with sum of at-crease batter runs by >tolerance. Advisory only — partnership tracker / SM feeder divergence likely.
- Evidence:
```json
{
  "partnership_runs": 11,
  "sum_batter_runs": 4,
  "delta": 7,
  "contributors": [
    {
      "name": "Quinton de Kock",
      "runs": 2
    },
    {
      "name": "Reeza Hendricks",
      "runs": 2
    }
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 182 and .frame <= 186)' <session>.jsonl`

### P4 — `advisory` at frame 185
- First evidence frame: 185
- Duration: 3 frames
- Verdict: Partnership total disagrees with sum of at-crease batter runs by >tolerance. Advisory only — partnership tracker / SM feeder divergence likely.
- Evidence:
```json
{
  "partnership_runs": 11,
  "sum_batter_runs": 8,
  "delta": 3,
  "contributors": [
    {
      "name": "Quinton de Kock",
      "runs": 2
    },
    {
      "name": "Reeza Hendricks",
      "runs": 6
    }
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 183 and .frame <= 187)' <session>.jsonl`

### P4 — `advisory` at frame 186
- First evidence frame: 186
- Duration: 3 frames
- Verdict: Partnership total disagrees with sum of at-crease batter runs by >tolerance. Advisory only — partnership tracker / SM feeder divergence likely.
- Evidence:
```json
{
  "partnership_runs": 11,
  "sum_batter_runs": 8,
  "delta": 3,
  "contributors": [
    {
      "name": "Quinton de Kock",
      "runs": 2
    },
    {
      "name": "Reeza Hendricks",
      "runs": 6
    }
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 184 and .frame <= 188)' <session>.jsonl`

### P4 — `advisory` at frame 198
- First evidence frame: 198
- Duration: 3 frames
- Verdict: Partnership total disagrees with sum of at-crease batter runs by >tolerance. Advisory only — partnership tracker / SM feeder divergence likely.
- Evidence:
```json
{
  "partnership_runs": 11,
  "sum_batter_runs": 8,
  "delta": 3,
  "contributors": [
    {
      "name": "Quinton de Kock",
      "runs": 2
    },
    {
      "name": "Reeza Hendricks",
      "runs": 6
    }
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 196 and .frame <= 200)' <session>.jsonl`

## Decision-tag histogram

| Tag | Count |
|-----|-------|
| `DWR` | 9 |
| `ASYNC-DA` | 8 |
| `TAGS` | 5 |
| `OPEN-SCOUT-SELECT` | 5 |
| `PHASE-REJECT` | 5 |
| `L2` | 3 |
| `L2-DENSIFY` | 3 |

## Mode timeline (compressed)

- F2–F126: **COLD_START**
- F127–F198: **WARM**

## Latency p50/p95/p99 (ms)

| Stage | p50 | p95 | p99 | max | n |
|-------|-----|-----|-----|-----|---|
| vision | 616 | 874 | 1007 | 1570 | 74 |
| extract | 1102 | 1327 | 1477 | 1614 | 74 |
| scorer | 872 | 1089 | 1314 | 1666 | 74 |
| field | 33 | 43 | 60 | 70 | 74 |
| comm | 0 | 529 | 700 | 744 | 74 |
| code | 0 | 0 | 0 | 0 | 74 |
| total | 2632 | 3295 | 3643 | 5315 | 74 |

## Trace pointer index

Each anomaly cites a frame range. To inspect:

```
jq -c 'select(.frame >= START and .frame <= END)' logs/trace/866ce150.jsonl
```
