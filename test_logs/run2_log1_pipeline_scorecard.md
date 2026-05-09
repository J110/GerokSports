# LOG 1: Pipeline Scorecard Output — What the UI Displayed
## 5-min test 21:01:36 – 21:08:35 | GT vs DC, innings 1

### UI Elements Tracked
- Team score (score-wickets, overs)
- Batter 1 name, runs(balls), status
- Batter 2 name, runs(balls), status
- Current bowler name, wickets-runs (overs)
- This-over array
- Ball events
- Invariant corrections per frame

---

### State Timeline (what UI showed)

| Time  | Frame | Score     | Overs | Batter 1              | Batter 2                | Bowler                | This Over                    | Events / Notes |
|-------|-------|-----------|-------|-----------------------|-------------------------|-----------------------|------------------------------|----------------|
| 01:36 | F1    | 186-2     | 17.0  | Gill 60(?)            | Sundar* 37(?)           | Kuldeep None          | —                            | Cache restored. Invariant scaled Gill down |
| 01:42 | F2    | 186-2     | 17.0  | Gill 60(?)            | Sundar* 37(?)           | Mukesh 1-43           | —                            | Comparison strip data leaked (Mukesh=prev bowler) |
| 01:57 | F5    | 186-2     | 17.0  | Gill 70(43)           | Sundar* 43(26)          | Ngidi 0-21            | —                            | Gill 60→70, Sundar 37→43. Invariant: total 216 > 186+15, scaled to 60+37 |
| 02:06 | F7    | 186-2     | 17.1  | Gill 70(43)           | Sundar* 43(26)          | Ngidi 0-21            | ['?']                        | Mid-over join: pre-filled 1 ball. BALL: DOT 17.1 |
| 02:25 | F11   | 186-2     | 17.1  | Gill 70(43)→60(33)    | Sundar 44(27)→37(20)    | Ngidi 0-22            | ['.']                        | Invariant scaled down again: 70+44=214 > 201 |
| 02:47 | F15   | 186-2     | 17.2  | Gill* 70(44)          | Sundar 44(27)           | Ngidi 1-22            | ['.']                        | BALL: DOT 17.2 |
| 03:42 | F27   | 186-2     | 17.2  | Gill* 60(?)           | Sundar 37(?)            | Ngidi 0-23            | ['.','.']                    | Invariant scaled batters DOWN to 60+37 |
| 04:01 | F31   | 186-3     | 17.3  | Gill* 70(?)           | Sundar 37(?)            | Ngidi 1-23            | ['.','.']                    | Wickets 2→3! BALL: DOT 17.3 |
| 04:10 | F33   | 186-3     | 17.3  | Sundar 44(27)         | Phillips 0(0)           | Ngidi 1-23            | ['.','.','.']→['.','.',W']   | Auto-dismissed Gill, activated Phillips. BALL: WICKET 17.3 |
| 04:44 | F43   | 186-3     | 17.3  | Sundar 44(27)         | Phillips 0(0)           | Ngidi 1-23            | ['1','6','wd','4']           | Broadcast this-over arrived! Trimmed 5 legal→3 |
| 05:23 | F53   | 186-3     | 17.4  | Sundar 44(27)         | Phillips 0(1)           | Ngidi 0-23            | ['1','6','wd','4']           | BALL: DOT 17.4. Phillips balls 0→1 |
| 05:28 | F54   | 186-3     | 17.4  | Sundar 44(27)         | Phillips 0(1)           | Ngidi 1-23            | ['1','6','wd','4','.']       | — |
| 06:09 | F62   | 186-3     | 17.5  | Sundar 44(27)         | Phillips 0(2)           | Ngidi 1-23            | ['1','6','wd','4','.']       | BALL: DOT 17.5. Phillips balls 1→2 |
| 06:41 | F73   | 186-3     | 17.5  | Sundar 44(27)         | Phillips 0(2)           | Ngidi 1-23            | ['1','6','wd','4','.','.']   | — |
| 06:49 | F75   | 186-3     | 18.0  | Sundar 44(27)         | Phillips 1(3)           | Ngidi 1-24            | Over 17 complete: ['1','6','wd','4','.','.'] = 11 runs |  BALL: DOT 18.0 |
| 07:41 | F86   | 186-3     | 18.0  | Sundar 44(27)         | Phillips 1(3)           | Natarajan 1-27        | ['.']                        | New bowler Natarajan |
| 07:46 | F87   | 186-3     | 18.0  | Sundar 44(27)         | Phillips 1(3)           | Natarajan 1-3         | ['.']                        | Natarajan runs corrected 27→3 |
| 08:02 | F90   | 186-3     | 18.1  | Sundar 44(27)         | Phillips 1(3)           | Natarajan 0-22        | ['.']                        | BALL: DOT 18.1 |

### Invariant Corrections (every frame)
- **Batter total > score+15**: Triggered on almost EVERY frame. Gill(70)+Sundar(44)+dismissed batters = ~210-216 vs score 186. Invariant scales current batters down to ~60+37.
- **Batter balls > match balls+5**: Also triggered every frame.
- **Result**: UI alternates between showing true stats (70, 44) and scaled stats (60, 37) depending on frame.

### Ball Events Detected
| Ball  | Type   | Striker           | Bowler      | Runs | Notes |
|-------|--------|-------------------|-------------|------|-------|
| 17.1  | DOT    | Shubman Gill      | Ngidi       | 0    | — |
| 17.2  | DOT    | None              | Ngidi       | 0    | — |
| 17.3  | DOT    | Shubman Gill      | Ngidi       | 0    | Score didn't change |
| 17.3  | WICKET | Washington Sundar | Ngidi       | 0    | Gill dismissed (auto-detected from new batter) |
| 17.4  | DOT    | Glenn Phillips    | Ngidi       | 0    | — |
| 17.5  | DOT    | None              | Ngidi       | 0    | — |
| 18.0  | DOT    | Glenn Phillips    | Ngidi       | 0    | Over complete |
| 18.1  | DOT    | None              | Natarajan   | 0    | New over, new bowler |

### Over 17 Recorded
```
['1', '6', 'wd', '4', '.', '.'] = 11 runs, 0 wickets (by Lungi Ngidi)
```
Note: The '1', '6', 'wd', '4' came from broadcast. The '.', '.' came from ball event detector. The 'W' from wicket detection was somehow not in the final over — likely trimmed.

### Score Progression
```
186-2 → 186-2 → 186-2 → 186-3 → 186-3 → 186-3 → 186-3
(17.0)   (17.1)   (17.2)   (17.3)   (17.4)   (17.5)   (18.0)
```
**Score stuck at 186 for the entire 5 minutes.** Over 17 broadcast says 11 runs were scored but score didn't advance from 186.
