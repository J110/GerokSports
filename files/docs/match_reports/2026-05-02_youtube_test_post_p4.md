# Match trace report — `866ce150`
**Trace:** `logs/trace/866ce150.jsonl` — 174 records, 2026-05-02 12:25:31 → 2026-05-02 12:44:07 (duration 1116s, 0.16 fps mean)
**Schema version:** 1 (reader: 1)

## Summary
- Records: **174**
- Decisions captured: **66** (7 distinct tags)
- Anomalies: **145 error**, 0 warn, 12 info, 0 advisory
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
- Verdict: UI bowler unchanged across 2+ overs of apparent play. Inspect BOWLER, BOWLER-OVERRIDE, BOWLER-CONSENSUS-INCONSISTENT arbitrations and BOWLER-LOCK-RELEASED/ACQUIRED counts.
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

### P7 — `error` at frame 201
- First evidence frame: 198
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
    "bat:Reeza Hendricks=6(5)",
    "bowl:Akeal Hosein"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 196 and .frame <= 203)' <session>.jsonl`

### P8 — `error` at frame 201
- First evidence frame: 194
- Duration: 8 frames
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
- Trace pointer: `jq -c 'select(.frame >= 192 and .frame <= 203)' <session>.jsonl`

### P7 — `error` at frame 202
- First evidence frame: 201
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
    "SCORE-INF-GATE:proposed=8<bat_sum=8+extras=3",
    "wickets\u21920",
    "bat:Quinton de Kock=2(3)",
    "bat:Reeza Hendricks=6(5)",
    "bowl:Shamar Joseph"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 199 and .frame <= 204)' <session>.jsonl`

### P8 — `error` at frame 202
- First evidence frame: 194
- Duration: 9 frames
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
- Trace pointer: `jq -c 'select(.frame >= 192 and .frame <= 204)' <session>.jsonl`

### P7 — `error` at frame 203
- First evidence frame: 202
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
    "SCORE-INF-GATE:proposed=8<bat_sum=8+extras=3",
    "wickets\u21920",
    "bat:Quinton de Kock=2(3)",
    "bat:Reeza Hendricks=6(5)",
    "bowl:Shamar Joseph"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 200 and .frame <= 205)' <session>.jsonl`

### P8 — `error` at frame 203
- First evidence frame: 194
- Duration: 10 frames
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
- Trace pointer: `jq -c 'select(.frame >= 192 and .frame <= 205)' <session>.jsonl`

### P7 — `error` at frame 204
- First evidence frame: 203
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
    "SCORE-INF-GATE:proposed=8<bat_sum=8+extras=3",
    "wickets\u21920",
    "bat:Quinton de Kock=2(3)",
    "bat:Reeza Hendricks=6(5)",
    "bowl:Shamar Joseph"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 201 and .frame <= 206)' <session>.jsonl`

### P8 — `error` at frame 204
- First evidence frame: 194
- Duration: 11 frames
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
- Trace pointer: `jq -c 'select(.frame >= 192 and .frame <= 206)' <session>.jsonl`

### P7 — `error` at frame 205
- First evidence frame: 204
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
- Trace pointer: `jq -c 'select(.frame >= 202 and .frame <= 207)' <session>.jsonl`

### P8 — `error` at frame 205
- First evidence frame: 194
- Duration: 12 frames
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
- Trace pointer: `jq -c 'select(.frame >= 192 and .frame <= 207)' <session>.jsonl`

### P7 — `error` at frame 206
- First evidence frame: 205
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
    "SCORE-INF-GATE:proposed=9<bat_sum=8+extras=3",
    "bat:Quinton de Kock=2(3)",
    "bat:Reeza Hendricks=6(5)",
    "bowl:Shamar Joseph"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 203 and .frame <= 208)' <session>.jsonl`

### P8 — `error` at frame 206
- First evidence frame: 194
- Duration: 13 frames
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
- Trace pointer: `jq -c 'select(.frame >= 192 and .frame <= 208)' <session>.jsonl`

### P7 — `error` at frame 207
- First evidence frame: 206
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
    "SCORE-INF-GATE:proposed=9<bat_sum=8+extras=3",
    "wickets\u21920",
    "bat:Quinton de Kock=2(3)",
    "bat:Reeza Hendricks=6(5)",
    "bowl:Shamar Joseph"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 204 and .frame <= 209)' <session>.jsonl`

### P8 — `error` at frame 207
- First evidence frame: 194
- Duration: 14 frames
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
- Trace pointer: `jq -c 'select(.frame >= 192 and .frame <= 209)' <session>.jsonl`

### P7 — `error` at frame 208
- First evidence frame: 207
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
    "SCORE-INF-GATE:proposed=9<bat_sum=8+extras=3",
    "wickets\u21920",
    "bat:Quinton de Kock=2(3)",
    "bat:Reeza Hendricks=6(5)",
    "bowl:Shamar Joseph"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 205 and .frame <= 210)' <session>.jsonl`

### P8 — `error` at frame 208
- First evidence frame: 194
- Duration: 15 frames
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
- Trace pointer: `jq -c 'select(.frame >= 192 and .frame <= 210)' <session>.jsonl`

### P7 — `error` at frame 209
- First evidence frame: 208
- Duration: 1 frames
- Verdict: Score / wickets reset to zero with same innings counter — full_reset called without a corresponding set_innings_2 transition. Inspect scorer.committed_changes and pipeline.mode.
- Evidence:
```json
{
  "score_before": 11,
  "score_after": 12,
  "wickets_after": 0,
  "innings": 1,
  "committed_changes": [
    "score\u219212",
    "wickets\u21920",
    "bat:Quinton de Kock=2(2)",
    "bat:Reeza Hendricks=6(6)"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 206 and .frame <= 211)' <session>.jsonl`

### P8 — `error` at frame 209
- First evidence frame: 194
- Duration: 16 frames
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
- Trace pointer: `jq -c 'select(.frame >= 192 and .frame <= 211)' <session>.jsonl`

### P7 — `error` at frame 210
- First evidence frame: 209
- Duration: 1 frames
- Verdict: Score / wickets reset to zero with same innings counter — full_reset called without a corresponding set_innings_2 transition. Inspect scorer.committed_changes and pipeline.mode.
- Evidence:
```json
{
  "score_before": 12,
  "score_after": 12,
  "wickets_after": 0,
  "innings": 1,
  "committed_changes": [
    "SCORE-INF-GATE:proposed=9<bat_sum=8+extras=4",
    "wickets\u21920",
    "bat:Quinton de Kock=2(3)",
    "bat:Reeza Hendricks=6(5)"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 207 and .frame <= 212)' <session>.jsonl`

### P8 — `error` at frame 210
- First evidence frame: 194
- Duration: 17 frames
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
- Trace pointer: `jq -c 'select(.frame >= 192 and .frame <= 212)' <session>.jsonl`

### P7 — `error` at frame 211
- First evidence frame: 210
- Duration: 1 frames
- Verdict: Score / wickets reset to zero with same innings counter — full_reset called without a corresponding set_innings_2 transition. Inspect scorer.committed_changes and pipeline.mode.
- Evidence:
```json
{
  "score_before": 12,
  "score_after": 12,
  "wickets_after": 0,
  "innings": 1,
  "committed_changes": [
    "SCORE-INF-GATE:proposed=9<bat_sum=8+extras=4",
    "wickets\u21920",
    "bat:Quinton de Kock=2(3)",
    "bat:Reeza Hendricks=6(5)"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 208 and .frame <= 213)' <session>.jsonl`

### P8 — `error` at frame 211
- First evidence frame: 194
- Duration: 18 frames
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
- Trace pointer: `jq -c 'select(.frame >= 192 and .frame <= 213)' <session>.jsonl`

### P7 — `error` at frame 212
- First evidence frame: 211
- Duration: 1 frames
- Verdict: Score / wickets reset to zero with same innings counter — full_reset called without a corresponding set_innings_2 transition. Inspect scorer.committed_changes and pipeline.mode.
- Evidence:
```json
{
  "score_before": 12,
  "score_after": 12,
  "wickets_after": 0,
  "innings": 1,
  "committed_changes": [
    "FRAME_POISONED:None"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 209 and .frame <= 214)' <session>.jsonl`

### P8 — `error` at frame 212
- First evidence frame: 194
- Duration: 19 frames
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
- Trace pointer: `jq -c 'select(.frame >= 192 and .frame <= 214)' <session>.jsonl`

### P7 — `error` at frame 213
- First evidence frame: 212
- Duration: 1 frames
- Verdict: Score / wickets reset to zero with same innings counter — full_reset called without a corresponding set_innings_2 transition. Inspect scorer.committed_changes and pipeline.mode.
- Evidence:
```json
{
  "score_before": 12,
  "score_after": 12,
  "wickets_after": 0,
  "innings": 1,
  "committed_changes": [
    "SCORE-INF-GATE:proposed=12<bat_sum=11+extras=4",
    "wickets\u21920",
    "bat:Quinton de Kock=2(6)",
    "bat:Reeza Hendricks=9(5)",
    "bowl:Shamar Joseph"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 210 and .frame <= 215)' <session>.jsonl`

### P8 — `error` at frame 213
- First evidence frame: 194
- Duration: 20 frames
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
- Trace pointer: `jq -c 'select(.frame >= 192 and .frame <= 215)' <session>.jsonl`

### P7 — `error` at frame 214
- First evidence frame: 213
- Duration: 1 frames
- Verdict: Score / wickets reset to zero with same innings counter — full_reset called without a corresponding set_innings_2 transition. Inspect scorer.committed_changes and pipeline.mode.
- Evidence:
```json
{
  "score_before": 12,
  "score_after": 12,
  "wickets_after": 0,
  "innings": 1,
  "committed_changes": [
    "score\u219212",
    "overs\u21924.0",
    "wickets\u21920",
    "bat:Quinton de Kock=2(3)",
    "bat:Reeza Hendricks=6(5)",
    "bowl:Shamar Joseph"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 211 and .frame <= 216)' <session>.jsonl`

### P8 — `error` at frame 214
- First evidence frame: 194
- Duration: 21 frames
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
- Trace pointer: `jq -c 'select(.frame >= 192 and .frame <= 216)' <session>.jsonl`

### P7 — `error` at frame 215
- First evidence frame: 214
- Duration: 1 frames
- Verdict: Score / wickets reset to zero with same innings counter — full_reset called without a corresponding set_innings_2 transition. Inspect scorer.committed_changes and pipeline.mode.
- Evidence:
```json
{
  "score_before": 12,
  "score_after": 12,
  "wickets_after": 0,
  "innings": 1,
  "committed_changes": [
    "score\u219212",
    "overs\u21924.0",
    "bat:Quinton de Kock=2(2)",
    "bat:Reeza Hendricks=6(6)",
    "bowl:Shamar Joseph"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 212 and .frame <= 217)' <session>.jsonl`

### P8 — `error` at frame 215
- First evidence frame: 194
- Duration: 22 frames
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
- Trace pointer: `jq -c 'select(.frame >= 192 and .frame <= 217)' <session>.jsonl`

### P7 — `error` at frame 217
- First evidence frame: 215
- Duration: 1 frames
- Verdict: Score / wickets reset to zero with same innings counter — full_reset called without a corresponding set_innings_2 transition. Inspect scorer.committed_changes and pipeline.mode.
- Evidence:
```json
{
  "score_before": 12,
  "score_after": 12,
  "wickets_after": 0,
  "innings": 1,
  "committed_changes": [
    "bat:Quinton de Kock=2(6)",
    "bat:Reeza Hendricks=9(6)",
    "bowl:Shamar Joseph"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 213 and .frame <= 219)' <session>.jsonl`

### P8 — `error` at frame 217
- First evidence frame: 195
- Duration: 23 frames
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
- Trace pointer: `jq -c 'select(.frame >= 193 and .frame <= 219)' <session>.jsonl`

### P7 — `error` at frame 219
- First evidence frame: 217
- Duration: 1 frames
- Verdict: Score / wickets reset to zero with same innings counter — full_reset called without a corresponding set_innings_2 transition. Inspect scorer.committed_changes and pipeline.mode.
- Evidence:
```json
{
  "score_before": 12,
  "score_after": 12,
  "wickets_after": 0,
  "innings": 1,
  "committed_changes": [
    "FRAME_POISONED:None"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 215 and .frame <= 221)' <session>.jsonl`

### P8 — `error` at frame 219
- First evidence frame: 196
- Duration: 24 frames
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
- Trace pointer: `jq -c 'select(.frame >= 194 and .frame <= 221)' <session>.jsonl`

### P7 — `error` at frame 224
- First evidence frame: 219
- Duration: 1 frames
- Verdict: Score / wickets reset to zero with same innings counter — full_reset called without a corresponding set_innings_2 transition. Inspect scorer.committed_changes and pipeline.mode.
- Evidence:
```json
{
  "score_before": 12,
  "score_after": 12,
  "wickets_after": 0,
  "innings": 1,
  "committed_changes": [
    "CORRECTION_BLOCKED:46"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 217 and .frame <= 226)' <session>.jsonl`

### P8 — `error` at frame 224
- First evidence frame: 200
- Duration: 25 frames
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
- Trace pointer: `jq -c 'select(.frame >= 198 and .frame <= 226)' <session>.jsonl`

### P7 — `error` at frame 225
- First evidence frame: 224
- Duration: 1 frames
- Verdict: Score / wickets reset to zero with same innings counter — full_reset called without a corresponding set_innings_2 transition. Inspect scorer.committed_changes and pipeline.mode.
- Evidence:
```json
{
  "score_before": 12,
  "score_after": 12,
  "wickets_after": 0,
  "innings": 1,
  "committed_changes": [
    "bat:Quinton de Kock=2(6)",
    "bat:Reeza Hendricks=9(6)",
    "bowl:Shamar Joseph"
  ]
}
```
- Trace pointer: `jq -c 'select(.frame >= 222 and .frame <= 227)' <session>.jsonl`

### P8 — `error` at frame 225
- First evidence frame: 200
- Duration: 26 frames
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
- Trace pointer: `jq -c 'select(.frame >= 198 and .frame <= 227)' <session>.jsonl`

### P8 — `error` at frame 226
- First evidence frame: 200
- Duration: 27 frames
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
- Trace pointer: `jq -c 'select(.frame >= 198 and .frame <= 228)' <session>.jsonl`

### P8 — `error` at frame 227
- First evidence frame: 200
- Duration: 28 frames
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
- Trace pointer: `jq -c 'select(.frame >= 198 and .frame <= 229)' <session>.jsonl`

### P8 — `error` at frame 228
- First evidence frame: 200
- Duration: 29 frames
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
- Trace pointer: `jq -c 'select(.frame >= 198 and .frame <= 230)' <session>.jsonl`

### P8 — `error` at frame 229
- First evidence frame: 200
- Duration: 30 frames
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
- Trace pointer: `jq -c 'select(.frame >= 198 and .frame <= 231)' <session>.jsonl`

### P8 — `error` at frame 230
- First evidence frame: 200
- Duration: 31 frames
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
- Trace pointer: `jq -c 'select(.frame >= 198 and .frame <= 232)' <session>.jsonl`

### P8 — `error` at frame 231
- First evidence frame: 200
- Duration: 32 frames
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
- Trace pointer: `jq -c 'select(.frame >= 198 and .frame <= 233)' <session>.jsonl`

### P8 — `error` at frame 232
- First evidence frame: 200
- Duration: 33 frames
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
- Trace pointer: `jq -c 'select(.frame >= 198 and .frame <= 234)' <session>.jsonl`

### P8 — `error` at frame 233
- First evidence frame: 200
- Duration: 34 frames
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
- Trace pointer: `jq -c 'select(.frame >= 198 and .frame <= 235)' <session>.jsonl`

### P8 — `error` at frame 239
- First evidence frame: 205
- Duration: 35 frames
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
- Trace pointer: `jq -c 'select(.frame >= 203 and .frame <= 241)' <session>.jsonl`

### P8 — `error` at frame 251
- First evidence frame: 216
- Duration: 36 frames
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
- Trace pointer: `jq -c 'select(.frame >= 214 and .frame <= 253)' <session>.jsonl`

### P8 — `error` at frame 256
- First evidence frame: 220
- Duration: 37 frames
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
- Trace pointer: `jq -c 'select(.frame >= 218 and .frame <= 258)' <session>.jsonl`

### P8 — `error` at frame 257
- First evidence frame: 220
- Duration: 38 frames
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
- Trace pointer: `jq -c 'select(.frame >= 218 and .frame <= 259)' <session>.jsonl`

### P8 — `error` at frame 258
- First evidence frame: 220
- Duration: 39 frames
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
- Trace pointer: `jq -c 'select(.frame >= 218 and .frame <= 260)' <session>.jsonl`

### P8 — `error` at frame 259
- First evidence frame: 220
- Duration: 40 frames
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
- Trace pointer: `jq -c 'select(.frame >= 218 and .frame <= 261)' <session>.jsonl`

### P8 — `error` at frame 260
- First evidence frame: 220
- Duration: 41 frames
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
- Trace pointer: `jq -c 'select(.frame >= 218 and .frame <= 262)' <session>.jsonl`

### P8 — `error` at frame 261
- First evidence frame: 220
- Duration: 42 frames
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
- Trace pointer: `jq -c 'select(.frame >= 218 and .frame <= 263)' <session>.jsonl`

### P8 — `error` at frame 262
- First evidence frame: 220
- Duration: 43 frames
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
- Trace pointer: `jq -c 'select(.frame >= 218 and .frame <= 264)' <session>.jsonl`

### P8 — `error` at frame 263
- First evidence frame: 220
- Duration: 44 frames
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
- Trace pointer: `jq -c 'select(.frame >= 218 and .frame <= 265)' <session>.jsonl`

### P8 — `error` at frame 264
- First evidence frame: 220
- Duration: 45 frames
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
- Trace pointer: `jq -c 'select(.frame >= 218 and .frame <= 266)' <session>.jsonl`

### P8 — `error` at frame 272
- First evidence frame: 227
- Duration: 46 frames
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
- Trace pointer: `jq -c 'select(.frame >= 225 and .frame <= 274)' <session>.jsonl`

### P8 — `error` at frame 273
- First evidence frame: 227
- Duration: 47 frames
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
- Trace pointer: `jq -c 'select(.frame >= 225 and .frame <= 275)' <session>.jsonl`

### P8 — `error` at frame 274
- First evidence frame: 227
- Duration: 48 frames
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
- Trace pointer: `jq -c 'select(.frame >= 225 and .frame <= 276)' <session>.jsonl`

### P8 — `error` at frame 275
- First evidence frame: 227
- Duration: 49 frames
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
- Trace pointer: `jq -c 'select(.frame >= 225 and .frame <= 277)' <session>.jsonl`

### P8 — `error` at frame 276
- First evidence frame: 227
- Duration: 50 frames
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
- Trace pointer: `jq -c 'select(.frame >= 225 and .frame <= 278)' <session>.jsonl`

### P8 — `error` at frame 277
- First evidence frame: 227
- Duration: 51 frames
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
- Trace pointer: `jq -c 'select(.frame >= 225 and .frame <= 279)' <session>.jsonl`

### P8 — `error` at frame 278
- First evidence frame: 227
- Duration: 52 frames
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
- Trace pointer: `jq -c 'select(.frame >= 225 and .frame <= 280)' <session>.jsonl`

### P8 — `error` at frame 279
- First evidence frame: 227
- Duration: 53 frames
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
- Trace pointer: `jq -c 'select(.frame >= 225 and .frame <= 281)' <session>.jsonl`

### P8 — `error` at frame 280
- First evidence frame: 227
- Duration: 54 frames
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
- Trace pointer: `jq -c 'select(.frame >= 225 and .frame <= 282)' <session>.jsonl`

### P8 — `error` at frame 281
- First evidence frame: 227
- Duration: 55 frames
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
- Trace pointer: `jq -c 'select(.frame >= 225 and .frame <= 283)' <session>.jsonl`

### P8 — `error` at frame 282
- First evidence frame: 227
- Duration: 56 frames
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
- Trace pointer: `jq -c 'select(.frame >= 225 and .frame <= 284)' <session>.jsonl`

### P8 — `error` at frame 283
- First evidence frame: 227
- Duration: 57 frames
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
- Trace pointer: `jq -c 'select(.frame >= 225 and .frame <= 285)' <session>.jsonl`

### P8 — `error` at frame 286
- First evidence frame: 229
- Duration: 58 frames
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
- Trace pointer: `jq -c 'select(.frame >= 227 and .frame <= 288)' <session>.jsonl`

### P8 — `error` at frame 287
- First evidence frame: 229
- Duration: 59 frames
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
- Trace pointer: `jq -c 'select(.frame >= 227 and .frame <= 289)' <session>.jsonl`

### P8 — `error` at frame 288
- First evidence frame: 229
- Duration: 60 frames
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
- Trace pointer: `jq -c 'select(.frame >= 227 and .frame <= 290)' <session>.jsonl`

### P8 — `error` at frame 290
- First evidence frame: 230
- Duration: 61 frames
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
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 292)' <session>.jsonl`

### P8 — `error` at frame 291
- First evidence frame: 230
- Duration: 62 frames
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
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 293)' <session>.jsonl`

### P8 — `error` at frame 292
- First evidence frame: 230
- Duration: 63 frames
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
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 294)' <session>.jsonl`

### P8 — `error` at frame 293
- First evidence frame: 230
- Duration: 64 frames
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
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 295)' <session>.jsonl`

### P8 — `error` at frame 294
- First evidence frame: 230
- Duration: 65 frames
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
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 296)' <session>.jsonl`

### P8 — `error` at frame 295
- First evidence frame: 230
- Duration: 66 frames
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
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 297)' <session>.jsonl`

### P8 — `error` at frame 296
- First evidence frame: 230
- Duration: 67 frames
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
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 298)' <session>.jsonl`

### P8 — `error` at frame 297
- First evidence frame: 230
- Duration: 68 frames
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
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 299)' <session>.jsonl`

### P8 — `error` at frame 298
- First evidence frame: 230
- Duration: 69 frames
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
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 300)' <session>.jsonl`

### P8 — `error` at frame 299
- First evidence frame: 230
- Duration: 70 frames
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
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 301)' <session>.jsonl`

### P8 — `error` at frame 300
- First evidence frame: 230
- Duration: 71 frames
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
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 302)' <session>.jsonl`

### P8 — `error` at frame 301
- First evidence frame: 230
- Duration: 72 frames
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
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 303)' <session>.jsonl`

### P8 — `error` at frame 302
- First evidence frame: 230
- Duration: 73 frames
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
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 304)' <session>.jsonl`

### P8 — `error` at frame 303
- First evidence frame: 230
- Duration: 74 frames
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
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 305)' <session>.jsonl`

### P8 — `error` at frame 304
- First evidence frame: 230
- Duration: 75 frames
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
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 306)' <session>.jsonl`

### P8 — `error` at frame 305
- First evidence frame: 230
- Duration: 76 frames
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
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 307)' <session>.jsonl`

### P8 — `error` at frame 306
- First evidence frame: 230
- Duration: 77 frames
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
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 308)' <session>.jsonl`

### P8 — `error` at frame 307
- First evidence frame: 230
- Duration: 78 frames
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
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 309)' <session>.jsonl`

### P8 — `error` at frame 308
- First evidence frame: 230
- Duration: 79 frames
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
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 310)' <session>.jsonl`

### P8 — `error` at frame 309
- First evidence frame: 230
- Duration: 80 frames
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
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 311)' <session>.jsonl`

### P8 — `error` at frame 310
- First evidence frame: 230
- Duration: 81 frames
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
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 312)' <session>.jsonl`

### P8 — `error` at frame 311
- First evidence frame: 230
- Duration: 82 frames
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
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 313)' <session>.jsonl`

### P8 — `error` at frame 312
- First evidence frame: 230
- Duration: 83 frames
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
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 314)' <session>.jsonl`

### P8 — `error` at frame 314
- First evidence frame: 231
- Duration: 84 frames
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
- Trace pointer: `jq -c 'select(.frame >= 229 and .frame <= 316)' <session>.jsonl`

### P8 — `error` at frame 315
- First evidence frame: 231
- Duration: 85 frames
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
- Trace pointer: `jq -c 'select(.frame >= 229 and .frame <= 317)' <session>.jsonl`

### P8 — `error` at frame 316
- First evidence frame: 231
- Duration: 86 frames
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
- Trace pointer: `jq -c 'select(.frame >= 229 and .frame <= 318)' <session>.jsonl`

### P8 — `error` at frame 317
- First evidence frame: 231
- Duration: 87 frames
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
- Trace pointer: `jq -c 'select(.frame >= 229 and .frame <= 319)' <session>.jsonl`

### P8 — `error` at frame 321
- First evidence frame: 234
- Duration: 88 frames
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
- Trace pointer: `jq -c 'select(.frame >= 232 and .frame <= 323)' <session>.jsonl`

### P8 — `error` at frame 322
- First evidence frame: 234
- Duration: 89 frames
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
- Trace pointer: `jq -c 'select(.frame >= 232 and .frame <= 324)' <session>.jsonl`

### P8 — `error` at frame 323
- First evidence frame: 234
- Duration: 90 frames
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
- Trace pointer: `jq -c 'select(.frame >= 232 and .frame <= 325)' <session>.jsonl`

### P8 — `error` at frame 324
- First evidence frame: 234
- Duration: 91 frames
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
- Trace pointer: `jq -c 'select(.frame >= 232 and .frame <= 326)' <session>.jsonl`

### P8 — `error` at frame 331
- First evidence frame: 240
- Duration: 92 frames
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
- Trace pointer: `jq -c 'select(.frame >= 238 and .frame <= 333)' <session>.jsonl`

### P8 — `error` at frame 375
- First evidence frame: 283
- Duration: 93 frames
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
- Trace pointer: `jq -c 'select(.frame >= 281 and .frame <= 377)' <session>.jsonl`

### P8 — `error` at frame 376
- First evidence frame: 283
- Duration: 94 frames
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
- Trace pointer: `jq -c 'select(.frame >= 281 and .frame <= 378)' <session>.jsonl`

### P8 — `error` at frame 377
- First evidence frame: 283
- Duration: 95 frames
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
- Trace pointer: `jq -c 'select(.frame >= 281 and .frame <= 379)' <session>.jsonl`

### P8 — `error` at frame 387
- First evidence frame: 292
- Duration: 96 frames
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
- Trace pointer: `jq -c 'select(.frame >= 290 and .frame <= 389)' <session>.jsonl`

### P8 — `error` at frame 388
- First evidence frame: 292
- Duration: 97 frames
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
- Trace pointer: `jq -c 'select(.frame >= 290 and .frame <= 390)' <session>.jsonl`

### P8 — `error` at frame 389
- First evidence frame: 292
- Duration: 98 frames
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
- Trace pointer: `jq -c 'select(.frame >= 290 and .frame <= 391)' <session>.jsonl`

### P8 — `error` at frame 390
- First evidence frame: 292
- Duration: 99 frames
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
- Trace pointer: `jq -c 'select(.frame >= 290 and .frame <= 392)' <session>.jsonl`

### P8 — `error` at frame 391
- First evidence frame: 292
- Duration: 100 frames
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
- Trace pointer: `jq -c 'select(.frame >= 290 and .frame <= 393)' <session>.jsonl`

### P8 — `error` at frame 392
- First evidence frame: 292
- Duration: 101 frames
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
- Trace pointer: `jq -c 'select(.frame >= 290 and .frame <= 394)' <session>.jsonl`

### P8 — `error` at frame 393
- First evidence frame: 292
- Duration: 102 frames
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
- Trace pointer: `jq -c 'select(.frame >= 290 and .frame <= 395)' <session>.jsonl`

### P8 — `error` at frame 406
- First evidence frame: 304
- Duration: 103 frames
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
- Trace pointer: `jq -c 'select(.frame >= 302 and .frame <= 408)' <session>.jsonl`

### P8 — `error` at frame 412
- First evidence frame: 309
- Duration: 104 frames
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
- Trace pointer: `jq -c 'select(.frame >= 307 and .frame <= 414)' <session>.jsonl`

### P8 — `error` at frame 413
- First evidence frame: 309
- Duration: 105 frames
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
- Trace pointer: `jq -c 'select(.frame >= 307 and .frame <= 415)' <session>.jsonl`

### P8 — `error` at frame 414
- First evidence frame: 309
- Duration: 106 frames
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
- Trace pointer: `jq -c 'select(.frame >= 307 and .frame <= 416)' <session>.jsonl`

### P8 — `error` at frame 415
- First evidence frame: 309
- Duration: 107 frames
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
- Trace pointer: `jq -c 'select(.frame >= 307 and .frame <= 417)' <session>.jsonl`

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

### P9 — `info` at frame 209
- First evidence frame: 179
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
- Trace pointer: `jq -c 'select(.frame >= 177 and .frame <= 211)' <session>.jsonl`

### P9 — `info` at frame 211
- First evidence frame: 181
- Duration: 30 frames
- Verdict: UI field 'this_over' unchanged across 30 active-play records. Inspect rejections in the window — GUARD / GRAPHIC-FILTER suppressions are the common cause.
- Evidence:
```json
{
  "field": "this_over",
  "stuck_value": [
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
  "stale_records": 30,
  "rejections_in_window": []
}
```
- Trace pointer: `jq -c 'select(.frame >= 179 and .frame <= 213)' <session>.jsonl`

### P9 — `info` at frame 224
- First evidence frame: 209
- Duration: 15 frames
- Verdict: UI field 'score' unchanged across 15 active-play records. Inspect rejections in the window — GUARD / GRAPHIC-FILTER suppressions are the common cause.
- Evidence:
```json
{
  "field": "score",
  "stuck_value": 12,
  "stale_records": 15,
  "rejections_in_window": []
}
```
- Trace pointer: `jq -c 'select(.frame >= 207 and .frame <= 226)' <session>.jsonl`

### P9 — `info` at frame 251
- First evidence frame: 230
- Duration: 21 frames
- Verdict: UI field 'score' unchanged across 21 active-play records. Inspect rejections in the window — GUARD / GRAPHIC-FILTER suppressions are the common cause.
- Evidence:
```json
{
  "field": "score",
  "stuck_value": 13,
  "stale_records": 21,
  "rejections_in_window": []
}
```
- Trace pointer: `jq -c 'select(.frame >= 228 and .frame <= 253)' <session>.jsonl`

### P9 — `info` at frame 251
- First evidence frame: 204
- Duration: 47 frames
- Verdict: UI field 'current_bowler' unchanged across 47 active-play records. Inspect rejections in the window — GUARD / GRAPHIC-FILTER suppressions are the common cause.
- Evidence:
```json
{
  "field": "current_bowler",
  "stuck_value": "Shamar Joseph",
  "stale_records": 47,
  "rejections_in_window": []
}
```
- Trace pointer: `jq -c 'select(.frame >= 202 and .frame <= 253)' <session>.jsonl`

### P9 — `info` at frame 258
- First evidence frame: 228
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
- Trace pointer: `jq -c 'select(.frame >= 226 and .frame <= 260)' <session>.jsonl`

### P9 — `info` at frame 323
- First evidence frame: 287
- Duration: 36 frames
- Verdict: UI field 'current_bowler' unchanged across 36 active-play records. Inspect rejections in the window — GUARD / GRAPHIC-FILTER suppressions are the common cause.
- Evidence:
```json
{
  "field": "current_bowler",
  "stuck_value": "Akeal Hosein",
  "stale_records": 36,
  "rejections_in_window": []
}
```
- Trace pointer: `jq -c 'select(.frame >= 285 and .frame <= 325)' <session>.jsonl`

### P9 — `info` at frame 375
- First evidence frame: 331
- Duration: 44 frames
- Verdict: UI field 'score' unchanged across 44 active-play records. Inspect rejections in the window — GUARD / GRAPHIC-FILTER suppressions are the common cause.
- Evidence:
```json
{
  "field": "score",
  "stuck_value": 17,
  "stale_records": 44,
  "rejections_in_window": []
}
```
- Trace pointer: `jq -c 'select(.frame >= 329 and .frame <= 377)' <session>.jsonl`

## Decision-tag histogram

| Tag | Count |
|-----|-------|
| `DWR` | 16 |
| `TAGS` | 15 |
| `ASYNC-DA` | 13 |
| `OPEN-SCOUT-SELECT` | 10 |
| `PHASE-REJECT` | 6 |
| `L2` | 3 |
| `L2-DENSIFY` | 3 |

## Mode timeline (compressed)

- F2–F126: **COLD_START**
- F127–F415: **WARM**

## Latency p50/p95/p99 (ms)

| Stage | p50 | p95 | p99 | max | n |
|-------|-----|-----|-----|-----|---|
| vision | 586 | 866 | 1179 | 1929 | 174 |
| extract | 1079 | 1313 | 1492 | 1616 | 174 |
| scorer | 883 | 1094 | 1314 | 1666 | 174 |
| field | 33 | 38 | 60 | 71 | 174 |
| comm | 0 | 492 | 645 | 744 | 174 |
| code | 0 | 0 | 0 | 1 | 174 |
| total | 2582 | 3229 | 3902 | 5315 | 174 |

## Trace pointer index

Each anomaly cites a frame range. To inspect:

```
jq -c 'select(.frame >= START and .frame <= END)' logs/trace/866ce150.jsonl
```
