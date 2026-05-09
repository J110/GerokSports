# LOG 2: Scorecard Analysis — What Actually Happened (20:41–20:48)

## Match Context
GT vs DC, IPL 2026, 14th match. Gujarat Titans batting, 1st innings.
Pipeline joined at ~over 14.0. Score: 152-2.

## What The Broadcast Showed (Ground Truth from Vision Reads)

### Over 14 (Bowler: Lungi Ngidi, replacing Kuldeep)
| Ball | Broadcast Read          | Score After | Batters After          |
|------|-------------------------|-------------|------------------------|
| 14.0 | Start of over           | 152-2       | Sundar 39(20), Gill 45(31) |
| 14.1 | Dot (no score change)   | 152-2       | Sundar 39(21), Gill 45(31) |
| 14.2 | 1 run (Sundar)          | 153-2       | Sundar 40(22), Gill 45(31) |
| 14.3 | 1 run (Gill)            | 154-2       | Sundar 40(22), Gill 46(32) |
| 14.4 | 1 run + wide            | 156-2       | Sundar 41(23), Gill 46(32) |
| 14.5 | 4 runs (boundary)       | 160-2       | Sundar 41(23), Gill 50(33) |
| 15.0 | 1 run (Gill)            | 161-2       | Sundar 41(23), Gill 51(34) |

**Over 14 total: 9 runs (7 off bat + wide + 1 extra?) = [., 1, 1, 1, wd, 4] = 7 bat runs + 1 wide**
**Pipeline recorded: ['.', '1', '1', '1', 'wd', '4'] = 7 runs** ✅

### After Over 14 → Over Break + Ads (20:46:29 – 20:47:39)
- Long ad break (~70 seconds, F71-F95)
- No balls bowled during this time
- Pipeline correctly held state at 161-2 (15.0)

## What The Pipeline Tracked vs Reality

### Batter 1: Washington Sundar
| Metric     | Broadcast (actual) | Pipeline tracked | Match? |
|------------|-------------------|------------------|--------|
| Start      | 39(20)            | 16(13) → 39(20)  | ✅ After F6 (SR guard removed!) |
| After 14.1 | 39(21)            | 39(21)            | ✅ |
| After 14.2 | 40(22)            | 40(22)            | ✅ |
| After 14.3 | 40(22)            | 40(22)            | ✅ |
| After 14.4 | 41(23)            | 41(23)            | ✅ |
| End        | 41(23)            | 41(23)            | ✅ |

**SUNDAR: PERFECT** — SR guard removal fixed the previous blockage.

### Batter 2: Shubman Gill
| Metric     | Broadcast (actual) | Pipeline tracked | Match? |
|------------|-------------------|------------------|--------|
| Start      | 45(31)            | 36(24) → 45(31) by F7 | ✅ |
| After 14.3 | 46(32)            | 46(32)            | ✅ |
| After 14.5 | 50(33)            | 50(33)            | ✅ |
| 15.0       | 51(34)            | 51(34)            | ✅ |

**GILL: PERFECT** — 50 reached at 14.5 (boundary), updated correctly.

### Bowler: Lungi Ngidi
| Metric     | Broadcast (actual)                | Pipeline tracked      | Match? |
|------------|-----------------------------------|-----------------------|--------|
| F10        | "NGIDI REPLACES KULDEEP" (no figs)| 0-0 (0)               | ✅ Expected |
| F12        | 0-12 (2.0)                        | 0-0 (still)           | ❌ Runs not accepted |
| F14        | 0-12 (2.1)                        | 0-0 (2.1)             | ❌ Overs up, runs stuck at 0 |
| F22        | 0-13 (2.2)                        | 0-0 (2.2)             | ❌ |
| F38        | 0-14 (2.3)                        | 0-1 (2.3)             | ❌ Runs way off |
| F52        | 1-16 (2.4)                        | 1-1 (2.4)             | ❌ Wickets OK but runs wrong |
| F70        | 0-21 (3.0)                        | 0-1 (3.0)             | ❌ Runs 21 vs 1 |
| F96        | (comparison strip contamination)   | 2-18                  | ❌ Wickets jumped to 2 |

**NGIDI: MAJOR PROBLEM** — Bowler runs are stuck near 0 while broadcast shows 12→21.
Root cause: LiveMatchTracker initialized Ngidi with 0 runs, then tracker's bounding logic
prevented the jump from 0→12 (too large a delta per ball).

### Team Score
| Time  | Broadcast | Pipeline | Match? |
|-------|-----------|----------|--------|
| 41:23 | 152-2     | 152-2    | ✅ |
| 42:39 | 153-2     | 153-2    | ✅ |
| 43:31 | 154-2     | 154-2    | ✅ |
| 44:55 | 156-2     | 156-2    | ✅ |
| 45:49 | 160-2     | 160-2    | ✅ |
| 46:29 | 161-2     | 161-2    | ✅ |

**SCORE: PERFECT** — Every increment tracked correctly.

### Ball Events
| Ball | Pipeline Detection | Actual | Match? |
|------|-------------------|--------|--------|
| 14.1 | DOT               | Dot    | ✅ |
| 14.2 | 1_RUNS            | 1 run  | ✅ (was "EXTRA" before fix!) |
| 14.3 | 1_RUNS            | 1 run  | ✅ |
| 14.4 | 1_RUNS            | 1 run  | ✅ |
| 14.4 | EXTRA             | Wide   | ✅ (overs didn't advance) |
| 14.5 | FOUR              | 4 runs | ✅ |
| 15.0 | 1_RUNS            | 1 run  | ✅ |

**BALL EVENTS: PERFECT** — No more false wides! The fix is working.

## Issues Found

### CRITICAL
1. **Bowler runs stuck at 0-1**: Ngidi's runs should be ~21 but pipeline shows 1.
   LiveMatchTracker initialized at 0 and its per-ball jump limit prevents catching up.
   Bowler runs need a different bounding strategy — possibly accept first reading unconditionally.

2. **Bowler stat contamination from comparison strip**: At F96, DC's comparison
   strip (DC 52-0, 5.5) was correctly identified as bowling team... but Ngidi's
   figures were still extracted (0-18, 3.0 → triggered update to 2-18).
   The wickets jumped from 0 to 2 because the comparison strip shows DC's bowling figures
   against GT which accumulate differently.

### MODERATE
3. **Bowler wickets oscillation**: Ngidi wickets went 0→1→2→0→1→0→2 across frames.
   The LiveMatchTracker should enforce monotonicity for bowler wickets.

4. **First-frame Gill name miss**: F6 parsed "45(31)" as a batter name "45" instead
   of recognizing it as Gill's stats. Fuzzy match failed. Fixed by F7 when Gill's
   name appeared properly.

### MINOR
5. **Comparison strip still extracts bowler data**: When the pipeline detects a
   comparison strip (bowling team visible), it correctly strips score/batters but
   still processes bowler stats. Should also strip bowler figures from comparison strips.
