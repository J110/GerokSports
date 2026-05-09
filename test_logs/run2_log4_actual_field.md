# LOG 4: Actual Field Data — What the Frames Actually Showed
## 5-min test 21:01:36 – 21:08:35 | GT vs DC, innings 1

### Match Context for Field Expectations
- **Overs 17-18**: Death overs in T20
- **Bowler**: Lungi Ngidi (pace), then T Natarajan (pace)
- **Score**: ~183-185 at 17-18 overs, batting team accelerating
- **Expected field**: Mostly boundary riders (4-5 outside), few in circle

### What a Death Overs Pace Field SHOULD Look Like

For death overs with a pace bowler (overs 17-18), a typical T20 field:
```
                    long_off
          deep_cover          long_on
                                        deep_midwicket
    deep_point    mid_off   mid_on
                  BOWLER
    point                     square_leg
                                        deep_square_leg
                  KEEPER
                  BATTER
    third_man                            fine_leg
```
- **Inside circle (3-4)**: mid_off, mid_on, point, possibly cover
- **Outside circle (5-6)**: long_off, long_on, deep_midwicket, deep_square_leg, fine_leg, third_man
- **Keeper**: Standing BACK (pace bowling in death overs)
- **Slips**: NONE (not used in death overs against set batsmen)

### What YOLO Actually Detected

| Frame | YOLO People | Field Positions Mapped | Notes |
|-------|------------|------------------------|-------|
| F6    | ~5         | backward_square, deep_fine_leg, CC-silly_point | Closeup frames — low detection count |
| F8    | ~5-6       | cover_point, wide_mid_on, midwicket, deep areas | Gameplay frame with fielders visible |
| F28   | ~4         | slip, mid_off, gully | Unlikely for death overs — probably misclassified |
| F32   | ~4         | deep_third_man, deep_backward_point, deep_square_leg | More boundary riders — plausible |
| F53   | ~4-5       | gully (×2), mid_off, deep_fine_leg | Gully at death overs is wrong |
| F60   | 4          | 1 inner, 3 outer | Low count. Many fielders not visible |
| F73   | ~4         | fine_third_man, behind_keeper, deep_third_man | Behind the wicket region |
| F80   | ~4         | deep_fine_leg (×2), deep_square_leg | Boundary riders on leg side |
| F87   | ~5         | deep_backward_square, deep_fine_leg | Leg side boundary |
| F89   | ~6         | backward_square, deep_square_leg, deep_midwicket, deep_third_man | Spread around boundary |
| F90   | 8          | 2 inner + 6 outer | Best detection frame. Mostly boundary riders |

### YOLO vs Reality Comparison

| Aspect | YOLO Detected | Expected Reality | Match? |
|--------|--------------|------------------|--------|
| Total fielders visible | 4-8 per frame | 9 fielders always on field | ❌ Low — camera angles hide fielders |
| Keeper detected | Never ("?") | Standing back, behind stumps | ❌ Keeper not detected by YOLO |
| Slips | Added F28, removed F53, removed F89 | None — death overs, no slips | ❌ False slip detections |
| Gully | Added F53 (×2 duplicate) | None — not used in death overs | ❌ Misclassification |
| Silly point | Mapped at F6 | None — never used in death overs | ❌ Misclassification |
| Deep fielders | 3-6 per frame | 5-6 on boundary | ✅ Roughly correct |
| Inner circle | 1-2 per frame | 3-4 in circle | ❌ Under-detected |
| Behind_keeper | Mapped F51, F73 | Not a real position | ❌ YOLO mapping to wrong name |

### Problems Identified

#### 1. **YOLO Detection Count Too Low**
Average 4-5 detections per frame. With camera zoomed on bowler/batter, only nearby fielders are visible. The 9th fielder (at deep point, deep cover, etc.) is off-screen.

**Impact**: Template must fill 4-5 missing positions. Template accuracy is critical.

#### 2. **Wrong Positions for Match Phase**
- Slip, gully, silly_point are close-catching positions used in Test matches or early overs against new batters
- At overs 17-18 with set batsmen scoring ~10 RPO, these positions make no sense
- YOLO sees a person near the wicket area → maps to "slip" when it's probably the wicketkeeper

**Impact**: UI shows unrealistic field for the match situation.

#### 3. **Keeper Not Detected**
YOLO never identifies the keeper. The keeper_position stays "?" throughout.

**Impact**: UI can't show keeper stance (which is useful context — standing up for spin, back for pace).

#### 4. **Duplicate Position Mappings**
F6: backward_square ×2, F32: fine_leg ×2, F53: gully ×2. Same YOLO detection mapped to same position twice.

**Impact**: Template fill uses wrong count of "empty" positions.

#### 5. **Field Freeze Working but Still Too Frequent**
13 updates in 5 minutes = ~1.5 per over. Real field changes maybe once per over or after a wicket. The freeze triggers on every over sub-ball change (17.1, 17.2, 17.3, etc.) rather than just on full over changes.

**Impact**: Field still jitters ball-by-ball, just less than before.

### Positive Observations
- Boundary riders correctly detected as "deep_*" positions
- Field freeze reduced updates from 30+ to 13 (~57% reduction)
- Over change correctly triggers field recalculation
- Wicket at F32 triggered field update (field unfroze for new batter)
- No FIELD WARN about outside-circle count (previous bug fixed)
- F90 summary shows 8 detections with 0.9 confidence — best frame had good data
