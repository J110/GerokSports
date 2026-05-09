# Frame-by-Frame Pipeline Analysis

**Total frames logged**: 22

**Pipeline**: ConsistentReadTracker + CricketChecker + BallEventDetector + ThisOverManager + Commentary

**Test duration**: ~5 minutes



## Executive Summary

### Score Progression

`None-None(None)` → `6-0(1.0)` → `7-0(1.1)` → `8-0(1.1)` → `8-0(1.2)` → `9-0(1.3)` → `10-0(1.4)` → `11-0(1.5)` → `12-0(1.5)` → `13-0(2.0)` → `17-0(2.1)`


### Bowler Progression

`Anukul Roy 0-0 (0)` → `Anukul Roy 0-0 (0.1)` → `Anukul Roy 0-1 (0.1)` → `Anukul Roy 0-1 (1.1)` → `Anukul Roy 0-3 (0.3)` → `Anukul Roy 0-4 (0.4)` → `Anukul Roy 0-4 (0.5)` → `Anukul Roy 0-5 (0.5)` → `Navdeep Saini 0-0 (0)`


### Batter 1 Progression

`Mitchell Marsh 5(3)` → `Mitchell Marsh 0(1)` → `Mitchell Marsh 8(1)` → `Mitchell Marsh 5(4)` → `Mitchell Marsh 2(4)` → `Mitchell Marsh 6(5)` → `Mitchell Marsh 6(6)`


### Batter 2 Progression

`Aiden Markram 1(3)` → `Aiden Markram 2(4)` → `Aiden Markram 6(4)` → `Aiden Markram 0(0)` → `Aiden Markram 0(4)` → `Aiden Markram 4(2)` → `Aiden Markram 3(5)` → `Aiden Markram 4(6)` → `Aiden Markram 8(7)`


### Latency Summary (ms)

| Step | Avg | P95 | Max |

|------|-----|-----|-----|

| Vision | 2023 | 3010 | 3161 |

| Extractor | 1255 | 2314 | 2370 |

| Scorer | 1875 | 2009 | 16541 |

| Field/YOLO | 117 | 140 | 263 |

| Code | 0 | 0 | 0 |

| Commentary | 258 | 722 | 1961 |

| **Total** | 5425 | 6328 | 18809 |



### Commentary Summary

| Persona | Fires | Avg Latency | P95 Latency |

|---------|-------|-------------|-------------|

| Wire | 7 | 407ms | 502ms |

| Storyteller | 7 | 807ms | 1959ms |

| Analyst | 1 | 481ms | 481ms |

| Colour | 0 | 0ms | 0ms |



## Column Definitions


### Input / Processing Columns

| Column | Description |

|--------|-------------|

| **Qwen** | Frame type classified by Qwen3-VL vision model (scoreboard, ad, closeup, etc.) |

| **Scout** | Raw text description from Groq Scout 17B — what it sees on the broadcast strip |

| **Extractor** | Structured data parsed from Scout output: `ext_score` (score-wickets(overs)), `ext_bat` (batter names + runs(balls)), `ext_bowl` (bowler name + wickets-runs(overs)) |

| **Scorer changes** | What fields the Scorer LLM decided to update this frame (e.g. score, overs, batter runs) |

| **YOLO** | Number of persons detected by local YOLO model for field tracking |


### UI State Columns (Before vs After)

| Column | Description |

|--------|-------------|

| **BEFORE_score** | Team score-wickets(overs) *before* this frame was processed by the pipeline |

| **BEFORE_bat1 / bat2** | Active batter stats (name runs(balls)) *before* processing |

| **BEFORE_bowl** | Current bowler stats (name wickets-runs(overs)) *before* processing |

| **BEFORE_this_over** | Ball-by-ball display for current over *before* processing |

| **AFTER_score** | Team score-wickets(overs) *after* all pipeline processing (tracker + invariant checks) |

| **AFTER_bat1 / bat2** | Active batter stats *after* processing |

| **AFTER_bowl** | Current bowler stats *after* processing |

| **AFTER_this_over** | Ball-by-ball display for current over *after* processing |

| **AFTER_field** | Cricket field template name, frozen state, and fielder positions *after* processing |


### Event Columns

| Column | Description |

|--------|-------------|

| **Ball Event** | Detected ball event type: DOT, FOUR, SIX, WICKET, EXTRA, MULTI_BALL, or — (none) |

| **Corrections** | Cricket invariant corrections applied by CricketChecker (e.g. wicket reverts, bowler caps) |


### Latency Columns (all in milliseconds)

| Column | Description |

|--------|-------------|

| **lat_vision** | Time for Groq Scout vision call (frame classification + strip reading) |

| **lat_extract** | Time for Extractor LLM call (structured data parsing from Scout text) |

| **lat_scorer** | Time for Scorer LLM call (deciding which fields to update) |

| **lat_field** | Time for local YOLO field detection (person detection + zone classification) |

| **lat_code** | Time for non-API code: tracker updates, invariant checks, over management, field merge, WS broadcast |

| **lat_comm** | Time for commentary generation (all triggered narrators in parallel via Groq) |

| **lat_total** | Wall-clock time for the entire frame (from before-snapshot to log line) |


### Commentary Columns

| Column | Description |

|--------|-------------|

| **comm_wire** | Wire narrator output — factual ball-by-ball, 2-3 sentences (fires every ball event) |

| **comm_storyteller** | Storyteller narrator output — radio-style narrative, 3-5 sentences (fires every ball event) |

| **comm_analyst** | Analyst narrator output — tactical/statistical insight (fires on over-end, wickets, milestones) |

| **comm_colour** | Colour narrator output — big-moment drama (fires on milestones, set-batter dismissals, last-over, RRR thresholds) |

| **comm_wire_ms / comm_story_ms / comm_analyst_ms / comm_colour_ms** | Individual Groq latency per narrator (0 if narrator didn't fire) |


---



## F6 — GRAPHIC

**Latency**: V:`1656ms` E:`2248ms` S:`784ms` Field:`99ms` Code:`0ms` Comm:`0ms` **Total:`4701ms`**


**Qwen**: `GRAPHIC`


**Scout**:
```
STRIP: LSG 6-0 (1) |
```


**Extractor**: score=`None-None(None)` bat=`—` bowl=`—`


**Scorer changes**: `[]`


**YOLO**: `0` persons


**UI State — Before vs After**:

| Element | Before | After | Changed? |

|---------|--------|-------|----------|

| Score | `None-None(None)` | `None-None(None)` |  |

| Batter 1 | `—` | `—` |  |

| Batter 2 | `—` | `—` |  |

| Bowler | `— ?-? (?)` | `— ?-? (?)` |  |

| This Over | `[]` | `[]` |  |

| Field | | `pace_powerplay` frozen=`False` | |


**Ball Event**: `—`


**Corrections**: none


**Commentary**: —


**Analysis**:

- Slow frame: 4701ms total


---


## F7 — SCOREBOARD

**Latency**: V:`1912ms` E:`2370ms` S:`1546ms` Field:`123ms` Code:`0ms` Comm:`0ms` **Total:`5841ms`**


**Qwen**: `SCOREBOARD`


**Scout**:
```
STRIP: LSG 6-0 (1) | M MARSH 5(3) | MARKRAM 1(3) | ANUKUL 0-0 (0)
```


**Extractor**: score=`6-0(1)` bat=`M MARSH 5(3) | MARKRAM 1(3)` bowl=`ANUKUL 0-0 (0)`


**Scorer changes**: `['score→6', 'overs→1.0', 'wickets→0', 'bat:Mitchell Marsh=5(3)', 'bat:Aiden Markram=1(3)', 'bowl:Anukul Roy']`


**YOLO**: `6` persons


**UI State — Before vs After**:

| Element | Before | After | Changed? |

|---------|--------|-------|----------|

| Score | `None-None(None)` | `6-0(1.0)` | **YES** |

| Batter 1 | `—` | `Mitchell Marsh 5(3)` | **YES** |

| Batter 2 | `—` | `Aiden Markram 1(3)` | **YES** |

| Bowler | `— ?-? (?)` | `Anukul Roy 0-0 (0)` | **YES** |

| This Over | `[]` | `[]` |  |

| Field | | `spin_powerplay` frozen=`True` | |


**Ball Event**: `—`


**Corrections**: none


**Commentary**: —


**Analysis**:

- State changed: score None-None(None)→6-0(1.0), bat1 —→Mitchell Marsh 5(3), bat2 —→Aiden Markram 1(3), bowl — ?-? (?)→Anukul Roy 0-0 (0)

- Slow frame: 5841ms total


---


## F8 — SCOREBOARD

**Latency**: V:`2085ms` E:`1461ms` S:`940ms` Field:`119ms` Code:`0ms` Comm:`0ms` **Total:`4498ms`**


**Qwen**: `SCOREBOARD`


**Scout**:
```
STRIP: LSG 6-0 (1) | M MARSH 5(3) | MARKRAM 1(3) | ANUKUL 0-0 (0)
```


**Extractor**: score=`6-0(1)` bat=`M MARSH 5(3) | MARKRAM 1(3)` bowl=`ANUKUL 0-0 (0)`


**Scorer changes**: `['score→6', 'overs→1.0', 'wickets→0', 'bat:Mitchell Marsh=5(3)', 'bat:Aiden Markram=1(3)', 'bowl:Anukul Roy']`


**YOLO**: `8` persons


**UI State — Before vs After**:

| Element | Before | After | Changed? |

|---------|--------|-------|----------|

| Score | `6-0(1.0)` | `6-0(1.0)` |  |

| Batter 1 | `Mitchell Marsh 5(3)` | `Mitchell Marsh 5(3)` |  |

| Batter 2 | `Aiden Markram 1(3)` | `Aiden Markram 1(3)` |  |

| Bowler | `Anukul Roy 0-0 (0)` | `Anukul Roy 0-0 (0)` |  |

| This Over | `[]` | `[]` |  |

| Field | | `spin_powerplay` frozen=`True` | |


**Ball Event**: `—`


**Corrections**: none


**Commentary**: —


**Analysis**:

- Slow frame: 4498ms total


---


## F9 — SCOREBOARD

**Latency**: V:`1223ms` E:`988ms` S:`858ms` Field:`140ms` Code:`0ms` Comm:`1961ms` **Total:`5044ms`**


**Qwen**: `SCOREBOARD`


**Scout**:
```
STRIP: LSG 7-0 (1.1) | M MARSH 5(3) | MARKRAM 2(4) | ANUKUL 0-1 (0.1)
```


**Extractor**: score=`7-0(1.1)` bat=`M MARSH 5(3) | MARKRAM 2(4)` bowl=`ANUKUL 1-0 (0.1)`


**Scorer changes**: `['score→7', 'overs→1.1', 'wickets→0', 'bat:Mitchell Marsh=5(3)', 'bat:Aiden Markram=2(4)', 'bowl:Anukul Roy']`


**YOLO**: `2` persons


**UI State — Before vs After**:

| Element | Before | After | Changed? |

|---------|--------|-------|----------|

| Score | `6-0(1.0)` | `7-0(1.1)` | **YES** |

| Batter 1 | `Mitchell Marsh 5(3)` | `Mitchell Marsh 5(3)` |  |

| Batter 2 | `Aiden Markram 1(3)` | `Aiden Markram 2(4)` | **YES** |

| Bowler | `Anukul Roy 0-0 (0)` | `Anukul Roy 0-0 (0.1)` | **YES** |

| This Over | `[]` | `['1']` | **YES** |

| Field | | `spin_powerplay` frozen=`True` | |


**Ball Event**: `1_RUNS`


**Corrections**: none


**Commentary**:

| Persona | Latency | Text |

|---------|---------|------|

| Wire | `352ms` | 1.2: Anukul Roy to Aiden Markram, full length outside off, driven through covers for a single. Markram on 3, Marsh on 5. Score 8/0. |

| Storyteller | `1959ms` | And we're underway here at the Ekana Stadium, the Lucknow Super Giants looking to get off to a flying start against the Kolkata Knight Riders. Aiden Markram and Mitchell Marsh are the two batters at t |



**Analysis**:

- State changed: score 6-0(1.0)→7-0(1.1), bat2 Aiden Markram 1(3)→Aiden Markram 2(4), bowl Anukul Roy 0-0 (0)→Anukul Roy 0-0 (0.1), this_over []→['1']

- Ball event: 1_RUNS

- Slow frame: 5044ms total


---


## F10 — SCOREBOARD

**Latency**: V:`2059ms` E:`1200ms` S:`1391ms` Field:`118ms` Code:`0ms` Comm:`0ms` **Total:`4662ms`**


**Qwen**: `SCOREBOARD`


**Scout**:
```
STRIP: LSG 7-0 (1.1) | M MARSH 5(3) | MARKRAM 2(4) | ANUKUL 0-1 (0.1)
```


**Extractor**: score=`7-0(1.1)` bat=`M MARSH 5(3) | MARKRAM 2(4)` bowl=`ANUKUL 0-1 (0.1)`


**Scorer changes**: `['score→7', 'overs→1.1', 'wickets→0', 'bat:Mitchell Marsh=5(3)', 'bat:Aiden Markram=2(4)', 'bowl:Anukul Roy']`


**YOLO**: `0` persons


**UI State — Before vs After**:

| Element | Before | After | Changed? |

|---------|--------|-------|----------|

| Score | `7-0(1.1)` | `7-0(1.1)` |  |

| Batter 1 | `Mitchell Marsh 5(3)` | `Mitchell Marsh 5(3)` |  |

| Batter 2 | `Aiden Markram 2(4)` | `Aiden Markram 2(4)` |  |

| Bowler | `Anukul Roy 0-0 (0.1)` | `Anukul Roy 0-1 (0.1)` | **YES** |

| This Over | `['1']` | `['1']` |  |

| Field | | `spin_powerplay` frozen=`True` | |


**Ball Event**: `—`


**Corrections**: none


**Commentary**: —


**Analysis**:

- State changed: bowl Anukul Roy 0-0 (0.1)→Anukul Roy 0-1 (0.1)

- Slow frame: 4662ms total


---


## F20 — UNKNOWN

**Latency**: V:`3010ms` E:`1178ms` S:`1145ms` Field:`110ms` Code:`0ms` Comm:`0ms` **Total:`5346ms`**


**Qwen**: `UNKNOWN`


**Scout**:
```
STRIP: LSG 7-0 (1.1) | MITCHELL MARSH 0(1) | MARKRAM 6(4) | ANUKUL 0-7 (1.1)
```


**Extractor**: score=`7-0(1.1)` bat=`MITCHELL MARSH 0(1) | MARKRAM 6(4)` bowl=`ANUKUL 0-7 (1.1)`


**Scorer changes**: `['score→7', 'overs→1.1', 'wickets→0', 'bat:MITCHELL MARSH=0(1)', 'bat:AIDEN MARKRAM=6(4)', 'bowl:ANUKUL']`


**YOLO**: `0` persons


**UI State — Before vs After**:

| Element | Before | After | Changed? |

|---------|--------|-------|----------|

| Score | `7-0(1.1)` | `7-0(1.1)` |  |

| Batter 1 | `Mitchell Marsh 5(3)` | `Mitchell Marsh 0(1)` | **YES** |

| Batter 2 | `Aiden Markram 2(4)` | `Aiden Markram 6(4)` | **YES** |

| Bowler | `Anukul Roy 0-1 (0.1)` | `Anukul Roy 0-1 (1.1)` | **YES** |

| This Over | `['1']` | `['1']` |  |

| Field | | `spin_powerplay` frozen=`True` | |


**Ball Event**: `—`


**Corrections**: none


**Commentary**: —


**Analysis**:

- State changed: bat1 Mitchell Marsh 5(3)→Mitchell Marsh 0(1), bat2 Aiden Markram 2(4)→Aiden Markram 6(4), bowl Anukul Roy 0-1 (0.1)→Anukul Roy 0-1 (1.1)

- Slow frame: 5346ms total


---


## F30 — SCOREBOARD

**Latency**: V:`1493ms` E:`1226ms` S:`1126ms` Field:`105ms` Code:`0ms` Comm:`0ms` **Total:`3858ms`**


**Qwen**: `SCOREBOARD`


**Scout**:
```
STRIP: LSG 8-0 (1.1) | MARSH 8(1) | MARKRAM 0(0) | ANUKUL 0-8 (1.1)
```


**Extractor**: score=`8-0(1.1)` bat=`MARSH 8(1) | MARKRAM 0(0)` bowl=`ANUKUL 0-8 (1.1)`


**Scorer changes**: `['score→8', 'overs→1.1', 'wickets→0', 'bat:Mitchell Marsh=8(1)', 'bat:Aiden Markram=0(0)', 'bowl:Anukul Roy']`


**YOLO**: `0` persons


**UI State — Before vs After**:

| Element | Before | After | Changed? |

|---------|--------|-------|----------|

| Score | `7-0(1.1)` | `8-0(1.1)` | **YES** |

| Batter 1 | `Mitchell Marsh 0(1)` | `Mitchell Marsh 8(1)` | **YES** |

| Batter 2 | `Aiden Markram 6(4)` | `Aiden Markram 0(0)` | **YES** |

| Bowler | `Anukul Roy 0-1 (1.1)` | `Anukul Roy 0-1 (1.1)` |  |

| This Over | `['1']` | `['1']` |  |

| Field | | `spin_powerplay` frozen=`True` | |


**Ball Event**: `—`


**Corrections**: none


**Commentary**: —


**Analysis**:

- State changed: score 7-0(1.1)→8-0(1.1), bat1 Mitchell Marsh 0(1)→Mitchell Marsh 8(1), bat2 Aiden Markram 6(4)→Aiden Markram 0(0)

- Slow frame: 3858ms total


---


## F40 — SCOREBOARD

**Latency**: V:`3161ms` E:`1377ms` S:`1732ms` Field:`106ms` Code:`0ms` Comm:`0ms` **Total:`6287ms`**


**Qwen**: `SCOREBOARD`


**Scout**:
```
STRIP: LSG 8-0 (1.1) | M MARSH 5(3) | MARKRAM 2(4) | ANUKUL 0-2 (0.1)
```


**Extractor**: score=`8-0(1.1)` bat=`M MARSH 5(3) | MARKRAM 2(4)` bowl=`ANUKUL 0-2 (0.1)`


**Scorer changes**: `['score→8', 'overs→1.1', 'wickets→0', 'bat:Mitchell Marsh=8(1)', 'bat:Aiden Markram=0(0)', 'bowl:Anukul Roy']`


**YOLO**: `7` persons


**UI State — Before vs After**:

| Element | Before | After | Changed? |

|---------|--------|-------|----------|

| Score | `8-0(1.1)` | `8-0(1.1)` |  |

| Batter 1 | `Mitchell Marsh 8(1)` | `Mitchell Marsh 8(1)` |  |

| Batter 2 | `Aiden Markram 0(0)` | `Aiden Markram 0(0)` |  |

| Bowler | `Anukul Roy 0-1 (1.1)` | `Anukul Roy 0-1 (1.1)` |  |

| This Over | `['1']` | `['1']` |  |

| Field | | `spin_powerplay` frozen=`True` | |


**Ball Event**: `—`


**Corrections**: none


**Commentary**: —


**Analysis**:

- Slow frame: 6287ms total


---


## F50 — SCOREBOARD

**Latency**: V:`1915ms` E:`977ms` S:`1258ms` Field:`113ms` Code:`0ms` Comm:`638ms` **Total:`4803ms`**


**Qwen**: `SCOREBOARD`


**Scout**:
```
STRIP: LSG 8-0 (1.2) | M MARSH 5(4) | MARKRAM 2(4) | ANUKUL 0-2 (0.2)
```


**Extractor**: score=`8-0(1.2)` bat=`M MARSH 5(4) | MARKRAM 2(4)` bowl=`ANUKUL 0-0 (0.2)`


**Scorer changes**: `['score→8', 'overs→1.2', 'wickets→0', 'bat:Mitchell Marsh=5(4)', 'bat:Aiden Markram=2(4)', 'bowl:Anukul Roy']`


**YOLO**: `5` persons


**UI State — Before vs After**:

| Element | Before | After | Changed? |

|---------|--------|-------|----------|

| Score | `8-0(1.1)` | `8-0(1.2)` | **YES** |

| Batter 1 | `Mitchell Marsh 8(1)` | `Mitchell Marsh 5(4)` | **YES** |

| Batter 2 | `Aiden Markram 0(0)` | `Aiden Markram 0(4)` | **YES** |

| Bowler | `Anukul Roy 0-1 (1.1)` | `Anukul Roy 0-1 (1.1)` |  |

| This Over | `['1']` | `['1', '.']` | **YES** |

| Field | | `spin_powerplay` frozen=`True` | |


**Ball Event**: `DOT`


**Corrections**: none


**Commentary**:

| Persona | Latency | Text |

|---------|---------|------|

| Wire | `380ms` | 1.2: Anukul Roy to Mitchell Marsh, good length delivery outside off, Marsh watches it closely and lets it go through to the keeper. Dot ball to end th |

| Storyteller | `633ms` | And Anukul Roy comes back for his second over, running in with a smooth stride, the crowd buzzing with anticipation. He starts with a good-length delivery, just outside the off stump, Mitchell Marsh w |



**Analysis**:

- State changed: score 8-0(1.1)→8-0(1.2), bat1 Mitchell Marsh 8(1)→Mitchell Marsh 5(4), bat2 Aiden Markram 0(0)→Aiden Markram 0(4), this_over ['1']→['1', '.']

- Ball event: DOT

- Slow frame: 4803ms total


---


## F60 — UNKNOWN

**Latency**: V:`3010ms` E:`774ms` S:`1221ms` Field:`108ms` Code:`0ms` Comm:`559ms` **Total:`5581ms`**


**Qwen**: `UNKNOWN`


**Scout**:
```
STRIP: LSG 9-0 (1.3) | M MARSH 2(4) | MARKRAM 4(2) | ANUKUL 0-3 (0.3)
```


**Extractor**: score=`9-0(1.3)` bat=`M MARSH 2(4) | MARKRAM 4(2)` bowl=`ANUKUL 0-0 (0.3)`


**Scorer changes**: `['score→9', 'overs→1.3', 'wickets→0', 'bat:Mitchell Marsh=2(4)', 'bat:Aiden Markram=4(2)', 'bowl:Anukul Roy']`


**YOLO**: `0` persons


**UI State — Before vs After**:

| Element | Before | After | Changed? |

|---------|--------|-------|----------|

| Score | `8-0(1.2)` | `9-0(1.3)` | **YES** |

| Batter 1 | `Mitchell Marsh 5(4)` | `Mitchell Marsh 2(4)` | **YES** |

| Batter 2 | `Aiden Markram 0(4)` | `Aiden Markram 4(2)` | **YES** |

| Bowler | `Anukul Roy 0-1 (1.1)` | `Anukul Roy 0-1 (1.1)` |  |

| This Over | `['1', '.']` | `['1', '.', '1']` | **YES** |

| Field | | `spin_powerplay` frozen=`True` | |


**Ball Event**: `1_RUNS`


**Corrections**: none


**Commentary**:

| Persona | Latency | Text |

|---------|---------|------|

| Wire | `356ms` | 1.4: Anukul Roy to Aiden Markram, short of a length, Markram clips off the pads to fine leg for a single. The batter works it away to the leg side. Sc |

| Storyteller | `557ms` | And here comes Anukul Roy for his second over, running in with a smooth stride, eyes fixed intently on the batsmen. He starts his run-up, a tall, lanky figure, and delivers a full-toss, swinging in a |



**Analysis**:

- State changed: score 8-0(1.2)→9-0(1.3), bat1 Mitchell Marsh 5(4)→Mitchell Marsh 2(4), bat2 Aiden Markram 0(4)→Aiden Markram 4(2), this_over ['1', '.']→['1', '.', '1']

- Ball event: 1_RUNS

- Slow frame: 5581ms total


---


## F70 — SCOREBOARD

**Latency**: V:`1573ms` E:`1178ms` S:`1432ms` Field:`263ms` Code:`0ms` Comm:`0ms` **Total:`4196ms`**


**Qwen**: `SCOREBOARD`


**Scout**:
```
STRIP: LSG 9-0 (1.3) | M MARSH 6(5) | MARKRAM 2(4) | ANUKUL 0-3 (0.3)
```


**Extractor**: score=`9-0(1.3)` bat=`M MARSH 6(5) | MARKRAM 2(4)` bowl=`ANUKUL 0-3 (0.3)`


**Scorer changes**: `['score→9', 'overs→1.3', 'wickets→0', 'bat:Mitchell Marsh=6(5)', 'bat:Aiden Markram=2(4)', 'bowl:Anukul Roy']`


**YOLO**: `3` persons


**UI State — Before vs After**:

| Element | Before | After | Changed? |

|---------|--------|-------|----------|

| Score | `9-0(1.3)` | `9-0(1.3)` |  |

| Batter 1 | `Mitchell Marsh 2(4)` | `Mitchell Marsh 6(5)` | **YES** |

| Batter 2 | `Aiden Markram 4(2)` | `Aiden Markram 2(4)` | **YES** |

| Bowler | `Anukul Roy 0-1 (1.1)` | `Anukul Roy 0-3 (0.3)` | **YES** |

| This Over | `['1', '.', '1']` | `['1', '.', '1']` |  |

| Field | | `spin_powerplay` frozen=`True` | |


**Ball Event**: `—`


**Corrections**: none


**Commentary**: —


**Analysis**:

- State changed: bat1 Mitchell Marsh 2(4)→Mitchell Marsh 6(5), bat2 Aiden Markram 4(2)→Aiden Markram 2(4), bowl Anukul Roy 0-1 (1.1)→Anukul Roy 0-3 (0.3)

- Slow frame: 4196ms total


---


## F80 — SCOREBOARD

**Latency**: V:`1487ms` E:`1069ms` S:`950ms` Field:`122ms` Code:`0ms` Comm:`659ms` **Total:`4177ms`**


**Qwen**: `SCOREBOARD`


**Scout**:
```
STRIP: LSG 10-0 (1.4) | M MARSH 6(5) | MARKRAM 3(5) | 1 WD 1 1
```


**Extractor**: score=`10-0(1.4)` bat=`M MARSH 6(5) | MARKRAM 3(5)` bowl=`—`


**Scorer changes**: `['score→10', 'overs→1.4', 'wickets→0', 'bat:Mitchell Marsh=6(5)', 'bat:Aiden Markram=3(5)']`


**YOLO**: `0` persons


**UI State — Before vs After**:

| Element | Before | After | Changed? |

|---------|--------|-------|----------|

| Score | `9-0(1.3)` | `10-0(1.4)` | **YES** |

| Batter 1 | `Mitchell Marsh 6(5)` | `Mitchell Marsh 6(5)` |  |

| Batter 2 | `Aiden Markram 2(4)` | `Aiden Markram 3(5)` | **YES** |

| Bowler | `Anukul Roy 0-3 (0.3)` | `Anukul Roy 0-3 (0.3)` |  |

| This Over | `['1', '.', '1']` | `['1', '.', '1', '1']` | **YES** |

| Field | | `spin_powerplay` frozen=`True` | |


**Ball Event**: `1_RUNS`


**Corrections**: none


**Commentary**:

| Persona | Latency | Text |

|---------|---------|------|

| Wire | `434ms` | 1.4: Anukul Roy to Mitchell Marsh, full-toss on the stumps, Marsh drives through covers for a single, runs to the non-striker's end. Score: 11/0. |

| Storyteller | `656ms` | And Anukul Roy is back for his second over, the young left-arm spinner looking to stem the flow of runs. He runs in with a smooth stride, his eyes fixed intently on Mitchell Marsh. The crowd is on the |



**Analysis**:

- State changed: score 9-0(1.3)→10-0(1.4), bat2 Aiden Markram 2(4)→Aiden Markram 3(5), this_over ['1', '.', '1']→['1', '.', '1', '1']

- Ball event: 1_RUNS

- Slow frame: 4177ms total


---


## F100 — SCOREBOARD

**Latency**: V:`1988ms` E:`2314ms` S:`1010ms` Field:`104ms` Code:`0ms` Comm:`0ms` **Total:`5327ms`**


**Qwen**: `SCOREBOARD`


**Scout**:
```
STRIP: LSG 10-0 (1.4) | M MARSH 6(5) | MARKRAM 3(5) | ANUKUL 0-4 (0.4)
```


**Extractor**: score=`10-0(1.4)` bat=`M MARSH 6(5) | MARKRAM 3(5)` bowl=`ANUKUL 0-4 (0.4)`


**Scorer changes**: `['score→10', 'overs→1.4', 'wickets→0', 'bat:Mitchell Marsh=6(5)', 'bat:Aiden Markram=3(5)', 'bowl:Anukul Roy']`


**YOLO**: `4` persons


**UI State — Before vs After**:

| Element | Before | After | Changed? |

|---------|--------|-------|----------|

| Score | `10-0(1.4)` | `10-0(1.4)` |  |

| Batter 1 | `Mitchell Marsh 6(5)` | `Mitchell Marsh 6(5)` |  |

| Batter 2 | `Aiden Markram 3(5)` | `Aiden Markram 3(5)` |  |

| Bowler | `Anukul Roy 0-3 (0.3)` | `Anukul Roy 0-4 (0.4)` | **YES** |

| This Over | `['1', '.', '1', '1']` | `['1', '.', '1', '1']` |  |

| Field | | `spin_powerplay` frozen=`True` | |


**Ball Event**: `—`


**Corrections**: none


**Commentary**: —


**Analysis**:

- State changed: bowl Anukul Roy 0-3 (0.3)→Anukul Roy 0-4 (0.4)

- Slow frame: 5327ms total


---


## F110 — SCOREBOARD

**Latency**: V:`1859ms` E:`1336ms` S:`1037ms` Field:`101ms` Code:`0ms` Comm:`564ms` **Total:`4808ms`**


**Qwen**: `SCOREBOARD`


**Scout**:
```
STRIP: LSG 11-0 (1.5) | M MARSH 6(6) | MARKRAM 3(5) | ANUKUL 0-4 (0.5)
```


**Extractor**: score=`11-0(1.5)` bat=`M MARSH 6(6) | MARKRAM 3(5)` bowl=`ANUKUL 0-4 (0.5)`


**Scorer changes**: `['score→11', 'overs→1.5', 'wickets→0', 'bat:Mitchell Marsh=6(6)', 'bat:Aiden Markram=3(5)', 'bowl:Anukul Roy']`


**YOLO**: `0` persons


**UI State — Before vs After**:

| Element | Before | After | Changed? |

|---------|--------|-------|----------|

| Score | `10-0(1.4)` | `11-0(1.5)` | **YES** |

| Batter 1 | `Mitchell Marsh 6(5)` | `Mitchell Marsh 6(6)` | **YES** |

| Batter 2 | `Aiden Markram 3(5)` | `Aiden Markram 3(5)` |  |

| Bowler | `Anukul Roy 0-4 (0.4)` | `Anukul Roy 0-4 (0.5)` | **YES** |

| This Over | `['1', '.', '1', '1']` | `['1', '.', '1', '1', '1']` | **YES** |

| Field | | `spin_powerplay` frozen=`True` | |


**Ball Event**: `1_RUNS`


**Corrections**: none


**Commentary**:

| Persona | Latency | Text |

|---------|---------|------|

| Wire | `427ms` | 1.6: Anukul Roy to Aiden Markram, full length outside off, Markram drives through covers for a single. The batter takes a quick run, bringing Markram |

| Storyteller | `560ms` | And Anukul Roy is back for his second over, the young left-arm spinner looking to stem the flow of runs here at Ekana Stadium. He runs in, a smooth, effortless stride, and delivers a full-toss, slight |



**Analysis**:

- State changed: score 10-0(1.4)→11-0(1.5), bat1 Mitchell Marsh 6(5)→Mitchell Marsh 6(6), bowl Anukul Roy 0-4 (0.4)→Anukul Roy 0-4 (0.5), this_over ['1', '.', '1', '1']→['1', '.', '1', '1', '1']

- Ball event: 1_RUNS

- Slow frame: 4808ms total


---


## F120 — SCOREBOARD

**Latency**: V:`1354ms` E:`765ms` S:`1012ms` Field:`98ms` Code:`0ms` Comm:`0ms` **Total:`3144ms`**


**Qwen**: `SCOREBOARD`


**Scout**:
```
STRIP: LSG 11-0 (1.5) | M MARSH 6(6) | MARKRAM 3(5) | ANUKUL 0-4 (0.5)
```


**Extractor**: score=`11-0(1.5)` bat=`M MARSH 6(6) | MARKRAM 3(5)` bowl=`ANUKUL 0-4 (0.5)`


**Scorer changes**: `['score→11', 'overs→1.5', 'wickets→0', 'bat:Mitchell Marsh=6(6)', 'bat:Aiden Markram=3(5)', 'bowl:Anukul Roy']`


**YOLO**: `5` persons


**UI State — Before vs After**:

| Element | Before | After | Changed? |

|---------|--------|-------|----------|

| Score | `11-0(1.5)` | `11-0(1.5)` |  |

| Batter 1 | `Mitchell Marsh 6(6)` | `Mitchell Marsh 6(6)` |  |

| Batter 2 | `Aiden Markram 3(5)` | `Aiden Markram 3(5)` |  |

| Bowler | `Anukul Roy 0-4 (0.5)` | `Anukul Roy 0-4 (0.5)` |  |

| This Over | `['1', '.', '1', '1', '1']` | `['1', '.', '1', '1', '1']` |  |

| Field | | `spin_powerplay` frozen=`True` | |


**Ball Event**: `—`


**Corrections**: none


**Commentary**: —


**Analysis**:

- Slow frame: 3144ms total


---


## F130 — SCOREBOARD

**Latency**: V:`2724ms` E:`1582ms` S:`2009ms` Field:`93ms` Code:`0ms` Comm:`0ms` **Total:`6328ms`**


**Qwen**: `SCOREBOARD`


**Scout**:
```
STRIP: LSG 12-0 (1.5) | M MARSH 6(6) | MARKRAM 3(5) | ANUKUL 0-5 (0.5)
```


**Extractor**: score=`12-0(1.5)` bat=`M MARSH 6(6) | MARKRAM 3(5)` bowl=`ANUKUL 0-5 (0.5)`


**Scorer changes**: `['score→12', 'overs→1.5', 'wickets→0', 'bat:Mitchell Marsh=6(6)', 'bat:Aiden Markram=3(5)', 'bowl:Anukul Roy']`


**YOLO**: `0` persons


**UI State — Before vs After**:

| Element | Before | After | Changed? |

|---------|--------|-------|----------|

| Score | `11-0(1.5)` | `12-0(1.5)` | **YES** |

| Batter 1 | `Mitchell Marsh 6(6)` | `Mitchell Marsh 6(6)` |  |

| Batter 2 | `Aiden Markram 3(5)` | `Aiden Markram 3(5)` |  |

| Bowler | `Anukul Roy 0-4 (0.5)` | `Anukul Roy 0-5 (0.5)` | **YES** |

| This Over | `['1', '.', '1', '1', '1']` | `['1', '.', '1', '1', '1']` |  |

| Field | | `spin_powerplay` frozen=`True` | |


**Ball Event**: `—`


**Corrections**: none


**Commentary**: —


**Analysis**:

- State changed: score 11-0(1.5)→12-0(1.5), bowl Anukul Roy 0-4 (0.5)→Anukul Roy 0-5 (0.5)

- Slow frame: 6328ms total


---


## F140 — SCOREBOARD

**Latency**: V:`2317ms` E:`1155ms` S:`943ms` Field:`107ms` Code:`0ms` Comm:`574ms` **Total:`5006ms`**


**Qwen**: `SCOREBOARD`


**Scout**:
```
STRIP: LSG 13-0 (2) | M MARSH 6(6) | MARKRAM 4(6) | ANUKUL
```


**Extractor**: score=`13-0(2)` bat=`M MARSH 6(6) | MARKRAM 4(6)` bowl=`—`


**Scorer changes**: `['score→13', 'overs→2', 'wickets→0', 'bat:Mitchell Marsh=6(6)', 'bat:Aiden Markram=4(6)']`


**YOLO**: `0` persons


**UI State — Before vs After**:

| Element | Before | After | Changed? |

|---------|--------|-------|----------|

| Score | `12-0(1.5)` | `13-0(2.0)` | **YES** |

| Batter 1 | `Mitchell Marsh 6(6)` | `Mitchell Marsh 6(6)` |  |

| Batter 2 | `Aiden Markram 3(5)` | `Aiden Markram 4(6)` | **YES** |

| Bowler | `Anukul Roy 0-5 (0.5)` | `Anukul Roy 0-5 (0.5)` |  |

| This Over | `['1', '.', '1', '1', '1']` | `[]` | **YES** |

| Field | | `spin_powerplay` frozen=`False` | |


**Ball Event**: `1_RUNS`


**Corrections**: none


**Commentary**:

| Persona | Latency | Text |

|---------|---------|------|

| Wire | `404ms` | 2.1: Anukul Roy to Mitchell Marsh, full toss on the stumps, Marsh drives through covers for a single, runs to mid-off. Score 14/0. |

| Storyteller | `569ms` | And Anukul Roy is back for his second over, the young left-arm spinner looking to weave his magic here at Ekana Stadium. He runs in, a smooth, rhythmic approach, and delivers a full-toss, just outside |

| Analyst | `481ms` | Anukul Roy's second over has started with a single, and Mitchell Marsh is taking the charge with a strike rate of 100. Aiden Markram is cautious at the other end, scoring at a rate of 66.7. The partne |



**Analysis**:

- State changed: score 12-0(1.5)→13-0(2.0), bat2 Aiden Markram 3(5)→Aiden Markram 4(6), this_over ['1', '.', '1', '1', '1']→[]

- Ball event: 1_RUNS

- Slow frame: 5006ms total


---


## F150 — SCOREBOARD

**Latency**: V:`3010ms` E:`989ms` S:`1183ms` Field:`129ms` Code:`0ms` Comm:`0ms` **Total:`5197ms`**


**Qwen**: `SCOREBOARD`


**Scout**:
```
Unfortunately, I don't see a scoreboard strip at the bottom of the screen, and I see an advertisement instead.
```


**Extractor**: score=`None-None(None)` bat=`—` bowl=`—`


**Scorer changes**: `['bat:Mitchell Marsh=6(6)', 'bat:Aiden Markram=4(6)', 'bowl:Anukul Roy']`


**YOLO**: `4` persons


**UI State — Before vs After**:

| Element | Before | After | Changed? |

|---------|--------|-------|----------|

| Score | `13-0(2.0)` | `13-0(2.0)` |  |

| Batter 1 | `Mitchell Marsh 6(6)` | `Mitchell Marsh 6(6)` |  |

| Batter 2 | `Aiden Markram 4(6)` | `Aiden Markram 4(6)` |  |

| Bowler | `Anukul Roy 0-5 (0.5)` | `Anukul Roy 0-5 (0.5)` |  |

| This Over | `[]` | `[]` |  |

| Field | | `spin_powerplay` frozen=`True` | |


**Ball Event**: `—`


**Corrections**: none


**Commentary**: —


**Analysis**:

- Slow frame: 5197ms total


---


## F160 — GRAPHIC

**Latency**: V:`1360ms` E:`602ms` S:`1217ms` Field:`115ms` Code:`0ms` Comm:`0ms` **Total:`3196ms`**


**Qwen**: `GRAPHIC`


**Scout**:
```
STRIP: Chennai 84-8 ( Yet to bat ) | KP  | NPG |
```


**Extractor**: score=`None-None(None)` bat=`—` bowl=`—`


**Scorer changes**: `['bat:Mitchell Marsh=6(6)', 'bat:Aiden Markram=4(6)', 'bowl:Anukul Roy']`


**YOLO**: `0` persons


**UI State — Before vs After**:

| Element | Before | After | Changed? |

|---------|--------|-------|----------|

| Score | `13-0(2.0)` | `13-0(2.0)` |  |

| Batter 1 | `Mitchell Marsh 6(6)` | `Mitchell Marsh 6(6)` |  |

| Batter 2 | `Aiden Markram 4(6)` | `Aiden Markram 4(6)` |  |

| Bowler | `Anukul Roy 0-5 (0.5)` | `Anukul Roy 0-5 (0.5)` |  |

| This Over | `[]` | `[]` |  |

| Field | | `spin_powerplay` frozen=`True` | |


**Ball Event**: `—`


**Corrections**: none


**Commentary**: —


**Analysis**:

- Slow frame: 3196ms total


---


## F180 — GRAPHIC

**Latency**: V:`1425ms` E:`829ms` S:`16541ms` Field:`105ms` Code:`0ms` Comm:`0ms` **Total:`18809ms`**


**Qwen**: `GRAPHIC`


**Scout**:
```
STRIP: LSG 13-0 (2)
```


**Extractor**: score=`13-0(2)` bat=`—` bowl=`—`


**Scorer changes**: `['score→13', 'overs→2.0', 'wickets→0', 'bat:Mitchell Marsh=6(6)', 'bat:Aiden Markram=4(6)', 'bowl:Anukul Roy']`


**YOLO**: `2` persons


**UI State — Before vs After**:

| Element | Before | After | Changed? |

|---------|--------|-------|----------|

| Score | `13-0(2.0)` | `13-0(2.0)` |  |

| Batter 1 | `Mitchell Marsh 6(6)` | `Mitchell Marsh 6(6)` |  |

| Batter 2 | `Aiden Markram 4(6)` | `Aiden Markram 4(6)` |  |

| Bowler | `Anukul Roy 0-5 (0.5)` | `Anukul Roy 0-5 (0.5)` |  |

| This Over | `[]` | `[]` |  |

| Field | | `spin_powerplay` frozen=`True` | |


**Ball Event**: `—`


**Corrections**: none


**Commentary**: —


**Analysis**:

- Slow frame: 18809ms total


---


## F190 — SCOREBOARD

**Latency**: V:`2054ms` E:`793ms` S:`978ms` Field:`107ms` Code:`0ms` Comm:`0ms` **Total:`3837ms`**


**Qwen**: `SCOREBOARD`


**Scout**:
```
STRIP: LSG 13-0 (2) | M MARSH 6(6) | MARKRAM 4(6) | SAINI 0-0 (0)
```


**Extractor**: score=`13-0(2)` bat=`M MARSH 6(6) | MARKRAM 4(6)` bowl=`SAINI 0-0 (0)`


**Scorer changes**: `['score→13', 'overs→2.0', 'wickets→0', 'bat:Mitchell Marsh=6(6)', 'bat:Aiden Markram=4(6)', 'bowl:Navdeep Saini']`


**YOLO**: `7` persons


**UI State — Before vs After**:

| Element | Before | After | Changed? |

|---------|--------|-------|----------|

| Score | `13-0(2.0)` | `13-0(2.0)` |  |

| Batter 1 | `Mitchell Marsh 6(6)` | `Mitchell Marsh 6(6)` |  |

| Batter 2 | `Aiden Markram 4(6)` | `Aiden Markram 4(6)` |  |

| Bowler | `Anukul Roy 0-5 (0.5)` | `Navdeep Saini 0-0 (0)` | **YES** |

| This Over | `[]` | `[]` |  |

| Field | | `pace_powerplay` frozen=`True` | |


**Ball Event**: `—`


**Corrections**: none


**Commentary**: —


**Analysis**:

- State changed: bowl Anukul Roy 0-5 (0.5)→Navdeep Saini 0-0 (0)

- Slow frame: 3837ms total


---


## F200 — SCOREBOARD

**Latency**: V:`1836ms` E:`1206ms` S:`939ms` Field:`94ms` Code:`0ms` Comm:`722ms` **Total:`4721ms`**


**Qwen**: `SCOREBOARD`


**Scout**:
```
STRIP: LSG 17-0 (2.1) | M MARSH 6(6) | MARKRAM 8(7) |
```


**Extractor**: score=`17-0(2.1)` bat=`M MARSH 6(6) | MARKRAM 8(7)` bowl=`—`


**Scorer changes**: `['score→17', 'overs→2.1', 'wickets→0', 'bat:Mitchell Marsh=6(6)', 'bat:Aiden Markram=8(7)']`


**YOLO**: `0` persons


**UI State — Before vs After**:

| Element | Before | After | Changed? |

|---------|--------|-------|----------|

| Score | `13-0(2.0)` | `17-0(2.1)` | **YES** |

| Batter 1 | `Mitchell Marsh 6(6)` | `Mitchell Marsh 6(6)` |  |

| Batter 2 | `Aiden Markram 4(6)` | `Aiden Markram 8(7)` | **YES** |

| Bowler | `Navdeep Saini 0-0 (0)` | `Navdeep Saini 0-0 (0)` |  |

| This Over | `[]` | `['4']` | **YES** |

| Field | | `pace_powerplay` frozen=`True` | |


**Ball Event**: `FOUR`


**Corrections**: none


**Commentary**:

| Persona | Latency | Text |

|---------|---------|------|

| Wire | `502ms` | 2.2: Navdeep Saini to Mitchell Marsh, full toss on the stumps, driven through covers for a single. Marsh takes a single to get off the mark on the sco |

| Storyteller | `720ms` | And we're underway here with Navdeep Saini taking over the bowling duties for Kolkata Knight Riders. The field is set with a deep point on the off side and a square leg on the leg side. Saini runs in, |



**Analysis**:

- State changed: score 13-0(2.0)→17-0(2.1), bat2 Aiden Markram 4(6)→Aiden Markram 8(7), this_over []→['4']

- Ball event: FOUR

- Slow frame: 4721ms total


---
