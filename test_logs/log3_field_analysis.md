# LOG 3: Field Tracking Analysis — 5 min test (20:41–20:48)

## Match Context
- Overs 14.0–15.0, pace bowler Lungi Ngidi
- Middle overs phase (overs 14-15)
- Template should be: PACE_MIDDLE (5 inside + 4 outside = 9)

## Field Updates Per Frame

### Early Frames (14.0–14.1): Field Settling
| Frame | YOLO Detections | Changes |
|-------|----------------|---------|
| F13   | scoreboard frame | Slip removed, short_leg pushed back, mid_off→deep, long_off→deep_mid_on |
| F14   | scoreboard frame | backward_square brought in, deep_mid_on→deep_midwicket_sq |

Template starting to adjust from the default. YOLO seeing players and updating positions.

### Mid-Over (14.2–14.3): Active Field Changes
| Frame | Changes |
|-------|---------|
| F19   | Short leg SET, slip ADDED, mid_off brought in — looks like attacking setup |
| F29   | deep_cover→straight_long_on, cover_point brought in, point→cover_point |
| F30   | Slip removed, short_leg pushed back, mid_off→wide_mid_on, cover brought in |
| F31   | square_leg brought in, mid_on→square_leg, point in, cover pushed back |
| F32   | point/square_leg pushed back, deep_cover→third_man, deep_cover→deep_square_leg |

**Analysis**: Field is changing every frame (every ~4-5 seconds). This is too volatile for
real cricket — a captain doesn't change the field between every ball. The YOLO detections
are noisy, causing the field to "jitter" rather than hold a stable configuration.

### Ball 14.4 (Wide + Run)
| Frame | Changes |
|-------|---------|
| F39   | behind_keeper_off brought in, wide_mid_on ×3 brought in (duplicate!) |
| F40   | Slip added, wide_mid_on→cover, deep_extra_cover→deep_cover_point |

**Issue**: F39 shows "wide_mid_on brought in — attacking" THREE times. This means the same
position is being added multiple times, which shouldn't happen. The field update logic
has a duplicate detection gap.

### Ball 14.5 (Boundary — 4 runs)
| Frame | Summary |
|-------|---------|
| F57   | short_leg in, backward_point in, square_leg→mid_off |
| F60   | **balanced | total:11 (yolo:5, vis:6) | slips:0 in:4 out:1 | keeper:back | conf:1.0** |
| F61   | backward_point pushed back, short_leg pushed back, mid_off pushed back |
| F62   | third_man→fine, behind_keeper_off back, midwicket in |

**Key observation**: F60 shows the field summary: 11 total (5 from YOLO + 6 from template),
4 inner circle + 1 outer circle + keeper + bowler + striker + non-striker = 4+1+4 = 9 fielders.
Only 1 outer fielder detected? For middle overs (14.5), there should be 4-5 boundary riders.

### Over Break (15.0): Ad Break
| Frame | Changes |
|-------|---------|
| F67   | Slip added, short_leg in, square_leg→cover_point |
| F69   | Slip removed, short_leg back, mid_off→mid_on, cover_point→point |

Field changing during ad break when no cricket is happening — YOLO is detecting ads.

### Post-Over (15.0+): Contaminated by Ads
| Frame | Warning |
|-------|---------|
| F96   | [FIELD WARN] Middle overs but **7 outside circle** (max 5) |
| F100  | [FIELD WARN] Middle overs but **8 outside circle** (max 5) |
| F102  | [FIELD WARN] Middle overs but **6 outside circle** (max 5) |

Field positions drifted during the long ad break (F71-F95), causing most fielders to
be classified as outer circle. The field rule enforcement warns but doesn't fix it.

## Problems Identified

### CRITICAL
1. **Field jitter — too many changes per over**: The field changed on nearly every
   frame (30+ changes in ~6 minutes). Real cricket has 1-2 field changes per over max.
   **Fix**: Implement a cooldown: only allow field updates when overs change OR when
   a significant YOLO shift happens (e.g., ≥3 players moved significantly).

2. **Ad break contamination**: YOLO runs during ad breaks and closeups, pushing field
   positions to nonsensical locations. When scorecard frames resume, the field is
   corrupted.
   **Fix**: Freeze field updates during non-SCOREBOARD frames. Only update field
   on SCOREBOARD or GAMEPLAY frames.

### MODERATE
3. **Duplicate position additions**: F39 shows "wide_mid_on brought in" 3 times.
   The merge logic should deduplicate before adding.
   
4. **Inner/outer ratio wrong**: At 15.0 overs (middle phase), field shows 7-8 outside
   circle. PACE_MIDDLE template expects 4 outside + 5 inside. The field rule check
   warns but doesn't cap or redistribute.
   **Fix**: After warning, enforce the maximum by moving excess outer-circle fielders
   to inner circle positions from the template.

5. **Slip/short_leg toggling**: Slip and short_leg are being added and removed every
   2-3 frames. This doesn't match real cricket where these positions are steady.
   **Fix**: Add hysteresis — once a slip/short_leg is added, keep it for at least
   3 frames (or until over changes) before allowing removal.

### MINOR
6. **Field summary only logged occasionally**: The "balanced" summary line (showing
   YOLO count, in/out split, keeper stance, confidence) only appears on ~2 frames.
   Should log on every scoreboard frame for debugging.

## Positive Observations
- Keeper stance correctly detected as "back" (appropriate for pace)
- YOLO detecting 5-11 people per frame (reasonable)
- Template-based fallback filling gaps (vis:6 = template positions)
- Over change correctly triggers field recalculation
- Position names are meaningful (not random coordinates)
