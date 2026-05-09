"""Delivery classification from ball trajectory data.

All classifiers accept raw pixel coordinates from the pitch crop and
return human-readable labels for commentary.

Label taxonomy (cricket commentary terminology):
  ANGLE:     over, round
  LENGTH:    bouncer, short, back_of_length, good_length, full, overpitched, yorker, full_toss
  LINE:      wide_outside_off, outside_off, off_stump, on_stumps, leg_stump, on_pads, down_leg
  BOUNCE:    bouncer, sharp_bounce, good_bounce, normal, stayed_low, skidded_through
  SHOT TYPE: along_ground, in_the_air, defended, missed, left_alone
  DIRECTION: fine_leg, square_leg, midwicket, mid_on, straight, mid_off,
             cover, point, third_man, no_shot
"""
from __future__ import annotations

import math


# ── Length ────────────────────────────────────────────────────────────

def classify_length(bounce_y: int, pitch_height: int,
                     pitch_top: int = 0,
                     speed_kph: float | None = None) -> str:
    """Classify delivery length from bounce-point y in the pitch crop.

    Calibrated from 51 manually-tagged IPL deliveries (Apr 2026).

    frac 0.0 = bowler's end (short), 1.0 = batter's feet (yorker).

    Key rules:
    - frac < 0.15: only "bouncer" if pace > 130 kph, else "short"
    - 0.15-0.35: "short" (back of a length territory)
    - 0.35-0.60: "good_length" (the hardest to score off)
    - 0.60-0.80: "full" (driving length)
    - 0.80+: "yorker"
    """
    if pitch_height <= 0:
        return "unknown"
    frac = 1.0 - (bounce_y - pitch_top) / pitch_height
    frac = max(0.0, min(1.0, frac))

    # Spinner adjustment: spinners have higher bounce points due to
    # slower speed + more loop, which shifts frac toward "short".
    # Compensate by shifting frac +0.10 for sub-120 kph deliveries.
    if speed_kph is not None and speed_kph < 120:
        frac = min(1.0, frac + 0.10)

    if frac < 0.15:
        if speed_kph is not None and speed_kph >= 130:
            return "bouncer"
        return "short"
    if frac < 0.35:
        return "short"
    if frac < 0.60:
        return "good_length"
    if frac < 0.80:
        return "full"
    return "yorker"


# ── Line ─────────────────────────────────────────────────────────────

def classify_line(ball_x: int, pitch_width: int,
                   center_x: int | None = None) -> str:
    """Classify line from ball x at the batting crease.

    With Moondream-centred ROI, center_x is the true stump line —
    no systematic bias compensation needed.  Thresholds are symmetric.

    Convention (bowler's-end camera, right-handed batter):
      LEFT in frame  (negative offset) = OFF side
      RIGHT in frame (positive offset) = LEG side
    """
    centre = center_x if center_x is not None else pitch_width / 2
    half_w = pitch_width / 2
    if half_w == 0:
        return "unknown"
    offset_frac = (ball_x - centre) / half_w

    if offset_frac < -0.25:
        return "wide_outside_off"
    if offset_frac < -0.10:
        return "outside_off"
    if offset_frac < -0.03:
        return "off_stump"
    if offset_frac < 0.03:
        return "on_stumps"
    if offset_frac < 0.10:
        return "leg_stump"
    if offset_frac < 0.25:
        return "on_pads"
    return "down_leg"


# ── Bowling angle ────────────────────────────────────────────────────

def classify_bowling_angle(first_x: int, center_in_crop: int) -> str:
    """Over or round the wicket based on ball's entry x relative to stumps.

    100% accuracy on tagged data — no changes needed.
    """
    if first_x < center_in_crop - 15:
        return "over"
    if first_x > center_in_crop + 15:
        return "round"
    return "over"


# ── Bounce height ────────────────────────────────────────────────────

def classify_bounce(
    flight: list[dict],
    bounce_point: dict,
) -> str:
    """Classify bounce height from pre/post bounce y-change ratio.

    Calibrated labels using commentary terminology:
    - bouncer:       ratio > 0.50 (ball reared up sharply — pace only)
    - sharp_bounce:  ratio > 0.35 (extra bounce, uncomfortable)
    - good_bounce:   ratio > 0.20 (carries nicely to keeper/slips)
    - normal:        ratio > 0.10 (standard bounce)
    - stayed_low:    ratio > 0.05 (kept low, dangerous)
    - skidded_through: ratio <= 0.05 (barely bounced, skidded on)
    """
    bp_idx = None
    for i, d in enumerate(flight):
        if d["frame"] == bounce_point["frame"]:
            bp_idx = i
            break

    if bp_idx is None or bp_idx < 1:
        return "normal"

    pre_descent = bounce_point["y"] - flight[0]["y"]
    if pre_descent <= 0:
        return "normal"

    post_points = flight[bp_idx + 1:] if bp_idx + 1 < len(flight) else []
    if not post_points:
        return "normal"

    max_rise = bounce_point["y"] - min(p["y"] for p in post_points)
    ratio = max_rise / pre_descent

    if ratio > 0.50:
        return "bouncer"
    if ratio > 0.35:
        return "sharp_bounce"
    if ratio > 0.20:
        return "good_bounce"
    if ratio > 0.10:
        return "normal"
    if ratio > 0.05:
        return "stayed_low"
    return "skidded_through"


# ── Shot elevation ───────────────────────────────────────────────────

def classify_shot_elevation(post_shot: list[dict]) -> str:
    """Along ground or in the air, based on area trend in post-shot phase.

    Label names match commentary:
    - "in_the_air" (not "aerial")
    - "along_ground"
    """
    if len(post_shot) < 2:
        return "unknown"

    areas = [d["area"] for d in post_shot]
    first_half = areas[: max(1, len(areas) // 2)]
    second_half = areas[max(1, len(areas) // 2):]
    avg_first = sum(first_half) / len(first_half)
    avg_second = sum(second_half) / len(second_half)

    if avg_first == 0:
        return "unknown"
    if avg_second < avg_first * 0.6:
        return "in_the_air"
    return "along_ground"


# ── Shot direction ───────────────────────────────────────────────────

FIELD_ZONES = {
    "third_man":  (20, 55),
    "point":      (55, 90),
    "cover":      (90, 130),
    "mid_off":    (130, 160),
    "straight":   (160, 200),
    "mid_on":     (200, 240),
    "midwicket":  (240, 280),
    "square_leg": (280, 310),
    "fine_leg":   (310, 340),
    "behind":     (340, 380),
}

_ZONE_SIDES = {
    "third_man": "offside", "point": "offside", "cover": "offside",
    "mid_off": "offside", "straight": "straight",
    "mid_on": "legside", "midwicket": "legside",
    "square_leg": "legside", "fine_leg": "legside",
    "behind": "behind_wicket",
}


def classify_shot_direction(
    batter_pos: tuple[int, int],
    post_shot: list[dict],
) -> dict:
    """Classify post-shot trajectory into side + zone.

    Convention: bowler's end camera, right-handed batter.
      LEFT in frame  (negative dx) = OFF side
      RIGHT in frame (positive dx) = LEG side
    """
    if len(post_shot) < 2:
        return {"zone": "unknown", "side": "unknown",
                "angle_degrees": 0, "confidence": 0}

    target = post_shot[-1]
    dx = target["x"] - batter_pos[0]
    dy = batter_pos[1] - target["y"]
    angle = math.degrees(math.atan2(dx, dy)) % 360

    if abs(dx) < 5 and abs(dy) < 5:
        side = "unknown"
    elif dy < 0 and abs(dy) > abs(dx):
        side = "behind_wicket"
    elif abs(dx) <= abs(dy) * 0.4:
        side = "straight"
    elif dx < 0:
        side = "offside"
    else:
        side = "legside"

    zone = "unknown"
    for name, (lo, hi) in FIELD_ZONES.items():
        lo_n = lo % 360
        hi_n = hi % 360
        if lo_n < hi_n:
            if lo_n <= angle < hi_n:
                zone = name
                break
        else:
            if angle >= lo_n or angle < hi_n:
                zone = name
                break

    confidence = min(1.0, len(post_shot) / 6)
    return {
        "zone": zone,
        "side": side,
        "angle_degrees": round(angle, 1),
        "confidence": round(confidence, 2),
    }


def infer_shot_direction_from_context(
    line: str, shot_type: str, runs: int
) -> dict:
    """Fallback direction inference when post-shot tracking fails.

    Uses line + shot_type + runs to infer the most probable direction.
    Only provides side (offside/legside), never fabricates a zone.
    """
    if shot_type in ("defended", "missed", "left_alone") or runs == 0:
        return {"zone": "no_shot", "side": "no_shot",
                "angle_degrees": 0, "confidence": 0.3}

    off_lines = ("wide_outside_off", "outside_off", "off_stump")
    leg_lines = ("leg_stump", "on_pads", "down_leg")

    if line in off_lines:
        side = "offside"
    elif line in leg_lines:
        side = "legside"
    else:
        side = "unknown"

    return {"zone": "unknown", "side": side,
            "angle_degrees": 0, "confidence": 0.2}


# ── Full toss detection ──────────────────────────────────────────────

def _is_full_toss_trajectory(flight: list[dict]) -> bool:
    """Detect full toss: ball descends continuously without bounce."""
    if len(flight) < 6:
        return False
    y_values = [d["y"] for d in flight]
    increasing = sum(1 for i in range(1, len(y_values))
                     if y_values[i] >= y_values[i - 1])
    return increasing >= len(y_values) * 0.75


# ── Shot type from runs (fallback) ──────────────────────────────────

def _shot_type_from_runs(runs: int) -> str:
    """Fallback shot type when post-shot tracking unavailable.

    Only 6 is definitively aerial. 4 is ambiguous (could be lofted
    or along the ground). 0 is defended. 1-3 is along the ground.
    """
    if runs == 0:
        return "defended"
    if runs == 6:
        return "in_the_air"
    if runs == 4:
        return "unknown"
    return "along_ground"


# ── Commentary builder ───────────────────────────────────────────────

_LENGTH_TEXT = {
    "bouncer": "short ball, banged in short",
    "short": "short of a length",
    "back_of_length": "back of a length",
    "good_length": "good length",
    "full": "full",
    "overpitched": "overpitched",
    "yorker": "yorker",
    "full_toss": "full toss",
}

_LINE_TEXT = {
    "wide_outside_off": "wide outside off stump",
    "outside_off": "outside off stump",
    "off_stump": "on off stump",
    "on_stumps": "on the stumps",
    "leg_stump": "on leg stump",
    "on_pads": "on the pads",
    "down_leg": "down the leg side",
}


_SHOT_TEXT = {
    "defended": "defended",
    "along_ground": "pushed along the ground",
    "in_the_air": "hit in the air",
    "missed": "beaten",
    "left_alone": "left alone",
}


def build_commentary_line(classification: dict) -> str:
    """Natural language one-liner from length, line, angle, shot type."""
    parts: list[str] = []

    if classification.get("bowling_angle") == "round":
        parts.append("round the wicket")

    lt = _LENGTH_TEXT.get(classification.get("length", ""))
    if lt:
        parts.append(lt)

    ll = _LINE_TEXT.get(classification.get("line", ""))
    if ll:
        parts.append(ll)

    st = _SHOT_TEXT.get(classification.get("shot_type", ""), "")
    if st:
        parts.append(st)

    dir_info = classification.get("shot_direction", {})
    if isinstance(dir_info, dict):
        side = dir_info.get("side", "unknown")
        if side not in ("unknown", "no_shot"):
            parts.append(f"to the {side}")

    return ", ".join(parts) or "no classification available"
