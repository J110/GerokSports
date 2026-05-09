# LOG 2: Actual Broadcast Data — What the Frames Actually Showed
## 5-min test 21:01:36 – 21:08:35 | GT vs DC, innings 1

### Data Source
These are the EXACT values the Vision+Extractor read from the broadcast frames. This is ground truth.

---

### Broadcast Reads Timeline

| Time  | Frame | Broadcast Score    | Batter 1 (broadcast) | Batter 2 (broadcast) | Bowler (broadcast)     | Notes |
|-------|-------|--------------------|----------------------|----------------------|------------------------|-------|
| 01:41 | F2    | (comparison strip) | Sai Sudharsan 37(30) | Shubman Gill 24(19)  | Mukesh 1-43 (1)        | **STALE** — this is old/comparison data, not current match state |
| 01:52 | F4    | (comparison strip) | Shubman Gill 49(35)  | Wriyan Sundar 1(5)   | Mukesh 1-43 (1)        | **STALE** — more comparison/highlight reel data |
| 01:56 | F5    | GT 182-2 (17)      | Washington 43(26)    | Gill 70(43)           | Ngidi 0-21 (3)         | First real current scoreboard |
| 02:01 | F6    | GT 182-2 (17)      | Washington 43(26)    | Gill 70(43)           | Ngidi 0-21 (3)         | Same |
| 02:05 | F7    | GT 183-2 (17.1)    | S Sundar 0(0)*       | Shubman Gill 0(0)     | L Ngidi 0-0 (0)        | **BAD READ** — vision returned 0(0) for both batters |
| 02:24 | F11   | GT 183-2 (17.1)    | Gill 0(3)            | Sundar 2(4)           | Ngidi 0-22 (3.1)       | **BAD READ** — wrong batter stats (0 and 2 instead of 70 and 44) |
| 02:31 | F12   | GT 183-2 (17.1)    | Washington 44(27)    | Gill 70(43)*          | Ngidi 0-22 (3.1)       | **GOOD READ** — this is the real data |
| 02:37 | F13   | GT 183-2 (17.1)    | Washington 44(27)    | Gill 70(43)           | Ngidi 0-22 (3.1)       | Confirmed |
| 02:41 | F14   | GT 183-2 (17.1)    | Washington 44(27)    | Gill 70(43)*          | Ngidi 1-22 (3.1)       | Ngidi wickets flipped 0→1 |
| 02:46 | F15   | GT 183-2 (17.2)    | Gill 70(44)          | Washington 44(27)     | Ngidi 1-22 (3.2)       | Overs advanced. Gill +1 ball |
| 03:00 | F19   | (comparison strip) | Gill 33(20)*         | Washington 4(7)       | Ngidi 2-17 (2.3)       | **STALE** — comparison strip with old/wrong data |
| 03:05 | F20   | GT 183-2 (17.2)    | Gill 70(44)          | Washington 44(27)     | Ngidi 1-22 (3.2)       | Good read |
| 03:12 | F21   | GT 183-2 (17.2)    | Washington 44(27)    | Gill 70(44)           | Ngidi 0-22 (3.2)       | Ngidi wickets flipped back 1→0 |
| 03:34 | F26   | (comparison strip) | Gill 23(20)          | Sundar 6(7)           | Ngidi 0-23 (4)         | **STALE** — comparison strip |
| 04:00 | F31   | GT 183-3 (17.3)    | Gill 62(40)          | Sudharsan 31(23)      | Ngidi 1-37 (3.3)       | **WICKET!** 2→3. But Sudharsan shown instead of Phillips? Old data mixed in |
| 04:05 | F32   | GT 183-3 (17.3)    | Shubman Gill 70(45)  | (partial)             | (none)                 | Gill still shown, dismissal graphic |
| 04:09 | F33   | GT 183-3 (17.3)    | Washington 44(27)    | Phillips 0(0)         | Ngidi 1-22 (3.3)       | New batter Phillips confirmed |
| 04:44 | F43   | GT 183-3 (17.3)    | Washington 44(27)    | Phillips 0(0)         | broadcast this-over: [4,.,1,6,wd,4] | Broadcast this-over! Data from EARLIER in over 17 |
| 04:48 | F44   | GT 183-3 (17.3)    | Washington 44(27)    | Phillips 0(0)         | broadcast: [1,6,wd,4]  | Trimmed broadcast this-over |
| 05:22 | F53   | GT 183-3 (17.4)    | Washington 44(27)    | Phillips 0(1)         | (none)                 | Phillips faced a ball |
| 05:31 | F55   | GT **184**-3 (17.4)| Washington 44(27)    | Phillips 0(1)         | Ngidi 1-23 (3.4)       | **Score finally moved!** 183→184 |
| 06:09 | F62   | GT 184-3 (17.5)    | (partial)            | (partial)             | Ngidi 1-23 (3.4)       | Overs advanced |
| 06:40 | F73   | GT 184-3 (17.5)    | Washington 44(27)    | Phillips 0(2)         | Ngidi 1-23 (3.5)       | Phillips 2 balls |
| 06:43 | F74   | GT 184-3 (17.5)    | Washington 44(27)    | Phillips 0(2)         | (not explicit)         | Same |
| 06:48 | F75   | GT 185-3 (18)      | Washington 44(27)    | Phillips 1(3)         | (from broadcast)       | **Over 18 started.** Score 184→185. Phillips 0→1 |
| 06:53 | F76   | GT 185-3 (18)      | Washington 44(27)    | Phillips 1(3)         | Ngidi 1-24 (4)         | Ngidi figures for complete over |
| 07:08 | F79   | (comparison strip) | Sundar 15(11)        | Phillips 5(6)         | Ngidi 1-12 (2.4)       | **STALE** — comparison or projection data |
| 07:40 | F86   | GT 185-3 (18)      | Washington 44(27)    | (partial)             | (bowler change)        | — |
| 07:45 | F87   | GT 185-3 (18)      | Washington 44(27)    | Phillips 1(3)         | Natarajan 1-3 (1)      | **New bowler: T Natarajan** |
| 07:55 | F89   | GT 185-3 (18)      | Washington 44(27)*   | Phillips 1(3)         | Natarajan None         | — |
| 08:00 | F90   | GT 185-3 (18.1)    | Washington 44(27)*   | (partial)             | Natarajan 0-22 (3.1)   | Overs advanced to 18.1 |

---

### Actual Score Progression (from broadcast)
```
F5:  GT 182-2 (17.0)   ← score on broadcast at start
F12: GT 183-2 (17.1)   ← +1 run
F15: GT 183-2 (17.2)   ← dot
F31: GT 183-3 (17.3)   ← WICKET (Gill out, score unchanged)
F55: GT 184-3 (17.4)   ← +1 run
F62: GT 184-3 (17.5)   ← dot
F75: GT 185-3 (18.0)   ← +1 run (last ball of over 17)
F90: GT 185-3 (18.1)   ← dot (first ball of over 18, Natarajan bowling)
```

### Actual Batter Stats (from broadcast, best reads only)
| Player             | Start of window | End of window | Change |
|--------------------|-----------------|---------------|--------|
| Shubman Gill       | 70(43)          | OUT at 17.3   | Dismissed (70 off 45 balls) |
| Washington Sundar  | 43(26)→44(27)   | 44(27)        | +1 run, +1 ball |
| Glenn Phillips     | 0(0) at 17.3    | 1(3) at 18.0  | +1 run, +3 balls |

### Actual Bowler Stats (from broadcast)
| Bowler         | Start        | End          | Notes |
|----------------|-------------|--------------|-------|
| Lungi Ngidi    | 0-21 (3.0)  | 1-24 (4.0)  | Completed over 17: 1 wicket, +3 runs |
| T Natarajan    | —           | 0-22 (3.1)  | Started bowling over 18 |

### Actual This-Over (from broadcast)
Over 17 broadcast indicator showed: `[4, ., 1, 6, wd, 4]` then later `[1, 6, wd, 4]`
This data is from BEFORE the pipeline joined — balls 17.1–17.3 were dots/wicket AFTER the broadcast indicator was showing earlier ball results.

---

### KEY MISMATCHES: Pipeline vs Broadcast

| Element | Pipeline Showed | Broadcast Showed | Mismatch? |
|---------|----------------|------------------|-----------|
| **Score** | **186** stuck entire test | 182→183→184→185 | **YES — CRITICAL.** Pipeline cached 186 from previous session but broadcast shows 182-185. Pipeline score is AHEAD of reality by ~3 runs |
| Gill runs | 70(43)→scaled to 60 | 70(43)→70(45) then OUT | Partially correct. 70 right but invariant kept scaling down |
| Sundar runs | 44(27)→scaled to 37-38 | 43(26)→44(27) | Close. But invariant scaling corrupts display |
| Phillips runs | 0(0)→1(3) | 0(0)→1(3) | ✅ Correct |
| Ngidi figures | Oscillates 0-2 wkts, 21-24 runs | 0-21→1-24 (4.0) | Runs OK (first reading fix worked!), wickets oscillate |
| Wicket detection | ✅ Detected at F33 | At 17.3 | ✅ Correct |
| This-over | ['1','6','wd','4','.','.'] | From broadcast: [1,6,wd,4] + 2 dots | Mixed source. Broadcast data + local dots. The 1,6,wd,4 are from EARLIER in the over, not matching the pipeline's joined window |
