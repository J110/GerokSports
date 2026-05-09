# LOG 3: Pipeline Field Output — What the UI Displayed
## 5-min test 21:01:36 – 21:08:35 | GT vs DC, innings 1

### Field Configuration
- Phase: Death overs (17-18)
- Bowler type: Pace (Lungi Ngidi, then T Natarajan)
- Template: pace_death
- Freeze enabled: YES (new fix)

---

### Field Updates (only frames where field changed)

| Time  | Frame | Trigger           | Changes |
|-------|-------|-------------------|---------|
| 02:02 | F6    | First scoreboard  | IC-backward_square brought in (×2 duplicate). Deep fine leg added. OC-deep_midwicket_sq→CC-silly_point |
| 02:11 | F8    | Overs 17.1        | Deep fine leg. IC-point→cover_point. CC-silly_point→IC-wide_mid_on. OC-deep_backward_square→deep_midwicket_sq. OC-deep_backward_point→third_man_square. IC-backward_square→midwicket |
| 03:49 | F28   | Overs 17.2        | Slip added. IC-mid_off pushed back. IC-gully pushed back |
| 04:06 | F32   | Overs 17.3 (wkt)  | OC-deep_third_man→deep_backward_point. OC-fine_leg→deep_square_leg (×2 duplicate) |
| 05:17 | F51   | Overs 17.3 still  | OC-fine_third_man→behind_keeper |
| 05:23 | F53   | Overs 17.4        | Slip removed. Deep fine leg. IC-gully brought in (×2 duplicate). IC-midwicket→mid_off |
| 06:00 | F60   | Overs 17.4        | IC-behind_keeper_off pushed back. IC-gully pushed back. **Summary: total:4 (yolo:4 vis:0), slips:0, in:1, out:3, keeper:?, conf:0.4** |
| 06:09 | F62   | Overs 17.5        | OC-behind_keeper→fine_third_man. OC-deep_third_man→third_man_fine. IC-mid_off pushed back |
| 06:41 | F73   | Overs 17.5 still  | OC-fine_third_man→behind_keeper. OC-third_man_fine→deep_third_man |
| 07:15 | F80   | Overs 18.0        | Deep fine leg (×2 duplicate). OC-deep_third_man→deep_square_leg |
| 07:46 | F87   | Overs 18.0 (new bowler) | OC-deep_fine_leg→deep_backward_square. OC-deep_square_leg→deep_backward_square. Deep fine leg |
| 07:56 | F89   | Overs 18.0        | IC-backward_square in. OC-deep_backward_square→deep_square_leg. OC-deep_backward_square→deep_midwicket. OC-deep_gully→deep_third_man. Slip removed |
| 08:02 | F90   | Overs 18.1        | **Summary: total:8 (yolo:8 vis:0), slips:0, in:2, out:6, keeper:?, conf:0.9** |

### Field Summary Stats
- **Total field update frames**: 13 (down from 30+ in previous test — freeze working!)
- **YOLO detections**: 4-8 people per frame (low, many closeups)
- **Inner/outer ratio**: Mostly 1-2 inner, 3-6 outer (too defensive for death overs)
- **Keeper stance**: Unknown ("?") — YOLO not detecting keeper
- **Duplicate additions**: 3 instances (F6, F32, F53 — same position added twice)
- **No FIELD WARN messages** (no outside-circle limit breach this time)

### Field Positions at Key Moments

**At over 17.1 (F8):** After initial settling
- IC: cover_point, wide_mid_on, midwicket
- OC: deep_midwicket_sq, third_man_square
- Plus: keeper, bowler
- Missing: Several positions — low YOLO count

**At over 17.4 (F60):** After wicket + dots
- IC: 1 fielder only
- OC: 3 fielders
- Total: 4 from YOLO + template fill
- Confidence: 0.4 (low)

**At over 18.1 (F90):** New bowler Natarajan
- IC: 2 fielders
- OC: 6 fielders (defensive)
- Total: 8 from YOLO
- Confidence: 0.9 (high)
- Formation: "defensive"
