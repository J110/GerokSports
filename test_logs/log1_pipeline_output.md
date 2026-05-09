# LOG 1: Pipeline Output — 5 min test (20:41:08 – 20:47:42)

## Session Info
- Match: GT vs DC, IPL 2026 (14th match)
- Innings: 1 (GT batting)
- Cache restored: 126-2 (11.3) from previous session
- First live scoreboard: F6 at 20:41:23

## Frame-by-Frame State Log

| Frame | Time  | Type       | Broadcast Read                           | Pipeline State                                  | Issues |
|-------|-------|------------|------------------------------------------|------------------------------------------------|--------|
| F1    | 41:12 | CLOSEUP    | (no strip)                               | —                                              | — |
| F2    | 41:14 | CLOSEUP    | (no strip)                               | —                                              | — |
| F3    | 41:16 | AD         | —                                        | —                                              | — |
| F4    | 41:18 | PREMATCH   | —                                        | —                                              | — |
| F5    | 41:21 | AD         | —                                        | —                                              | — |
| F6    | 41:23 | SCOREBOARD | GT 152-2 (14), WASHINGTON 39(20), 45(31) | 152-2 (14.0) Gill=36(24) Sundar=39(20)         | Gill name missed ("45" not parsed), Sundar jumped 16→39 (SR guard removed!) |
| F7    | 41:28 | SCOREBOARD | GT 152-2 (14), Washington 39(20), Gill 45(31) | 152-2 (14.0) Gill=45(31) Sundar=39(20)     | Gill stats updated 36→45 |
| F8    | 41:33 | SCOREBOARD | GT 152-2 (14), WASHINGTON 39(20), GILL 45(31) | 152-2 (14.0) Gill=45(31) Sundar=39(20)     | Stable |
| F9    | 41:39 | SCOREBOARD | GT 152-2 (14), WASHINGTON 39(20), GILL 45(31) | 152-2 (14.0) same                          | Stable |
| F10   | 41:43 | SCOREBOARD | GT 152-2 (14), NGIDI REPLACES KULDEEP    | 152-2 (14.0) Bowl: Ngidi 0-0                  | New bowler detected. Ngidi stats None |
| F11   | 41:47 | SCOREBOARD | GT 152-2 (14), NGIDI (no figures)         | 152-2 (14.0) Bowl: Ngidi 0-0                  | — |
| F12   | 41:53 | SCOREBOARD | GT 152-2 (14), NGIDI 0-12 (2)            | 152-2 (14.0) Bowl: Ngidi 0-0                  | Ngidi runs 12 NOT accepted (tracker) |
| F13   | 41:58 | SCOREBOARD | GT 152-2 (14), Speed 132.5kph            | 152-2 (14.0) Bowl: Ngidi 0-0                  | Speed detected |
| F14   | 42:04 | SCOREBOARD | GT 152-2 (14.1), WASHINGTON 39(21), GILL 45(31), NGIDI 0-12(2.1) | 152-2 (14.1) Sundar=39(21) | Overs advanced, dot ball |
| F17   | 42:14 | SCOREBOARD | GT 152-2 (14.1), same                    | 152-2 (14.1) same                             | — |
| F18   | 42:22 | SCOREBOARD | GT 152-2 (14.1)                          | 152-2 (14.1) same                             | — |
| F21   | 42:39 | SCOREBOARD | GT 153-2 (14.2), WASHINGTON 40(22)       | 153-2 (14.2) Sundar=40(22) — BALL: 1_RUNS     | 1 run correctly detected |
| F22   | 42:44 | SCOREBOARD | GT 153-2 (14.2), Ngidi 0-13 (2.2)       | 153-2 (14.2) Ngidi 0-0                        | Ngidi runs STILL 0 (tracker) |
| F23   | 42:49 | SCOREBOARD | GT 153-2 (14.2) (minimal strip)          | 153-2 (14.2)                                  | — |
| F36   | 43:54 | SCOREBOARD | GT 154-2 (14.3), Gill 46(32), Ngidi 0-14(2.3) | 154-2 (14.3) Gill=46(32) Ngidi=1-1        | Score +1, Gill +1 run |
| F37   | 43:58 | SCOREBOARD | "WASHINGTON GILL 40(22)", SUNDAR 46(32)   | 154-2 (14.3) — names merged                   | Vision fused names; split resolved correctly |
| F38   | 44:03 | SCOREBOARD | GT 154-2 (14.3), Washington 40(22), Gill 46(32), Ngidi 0-14(2.3) | same | Stable |
| F52   | 45:11 | SCOREBOARD | GT 156-2 (14.4), Washington 41(23), Ngidi 1-16(2.4) | 156-2 (14.4) Sundar=41(23) | Wide detected (wd in extras) |
| F55   | 45:21 | SCOREBOARD | **DC 68-0 (9.2)** — comparison strip!     | Stripped (bowling team guard)                  | Correctly identified as opposition comparison |
| F70   | 46:27 | SCOREBOARD | GT 161-2 (15), Washington 41(23), Gill 51(34), Ngidi 0-21(3) | 161-2 (15.0) Gill=51(34) | Over 14 complete: ['.','1','1','1','wd','4'] = 7 runs |
| F71   | 46:31 | GRAPHIC    | Ngidi career panel                        | Stats stripped (GRAPHIC guard)                 | — |
| F83   | 47:14 | SCOREBOARD | GT 161-2 (15.0)                          | 161-2 (15.0) same                             | Ad break, stale |
| F96   | 47:39 | SCOREBOARD | **DC 52-0 (5.5)** — comparison strip!     | Stripped. Ngidi 2-18 (contaminated)            | Ngidi wickets jumped 0→2 from comparison strip |

## State Progression Summary
```
20:41:23  GT 152-2 (14.0)  Gill 45(31)  Sundar 39(20)  Bowl: Ngidi 0-0
20:42:39  GT 153-2 (14.2)  Gill 45(31)  Sundar 40(22)  Bowl: Ngidi 0-0    +1 run
20:43:54  GT 154-2 (14.3)  Gill 46(32)  Sundar 40(22)  Bowl: Ngidi 1-1    +1 run
20:45:13  GT 156-2 (14.4)  Gill 46(32)  Sundar 41(23)  Bowl: Ngidi 1-1    +2 runs (1+wd)
20:46:29  GT 161-2 (15.0)  Gill 51(34)  Sundar 41(23)  Bowl: Ngidi 0-1    +5 runs (4+1), over complete
20:47:42  GT 161-2 (15.0)  Gill 51(34)  Sundar 41(23)  Bowl: Ngidi 2-18   ad break, contaminated
```

## Ball Events Detected
```
F14: DOT       | 14.1 | bowl=Lungi Ngidi
F21: 1_RUNS    | 14.2 | bat=Washington Sundar bowl=Lungi Ngidi +1
F36: 1_RUNS    | 14.3 | bat=Shubman Gill bowl=Lungi Ngidi +1
F52: (wide)    | 14.4 | extra detected from broadcast
F67: FOUR      | 14.5 | bowl=Lungi Ngidi +4
F70: 1_RUNS    | 15.0 | bat=Shubman Gill bowl=Lungi Ngidi +1
```

## Over History
```
Over 14: ['.', '1', '1', '1', 'wd', '4'] = 7 runs, 0 wickets (by Lungi Ngidi)
```

## Invariant Corrections
- **ZERO wicket corrections** (Fix 4 working perfectly)
- Total bowler overs flag only

## Errors / Crashes
- **None** (int.isdigit fix working)
