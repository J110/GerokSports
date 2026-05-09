"""Cricket-logic-first field tracking.

Always maintains exactly 11 players (9 fielders + keeper + bowler).
Uses template-based defaults adjusted by YOLO/vision observations.
"""
from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# Named position coordinates  (x, y on 0-1 scale)
# SVG viewBox 0-100, pitch center (50,50). Batter ~y=0.57, bowler ~y=0.38.
# OFF SIDE = LEFT (x < 0.50), LEG SIDE = RIGHT (x > 0.50).
# ---------------------------------------------------------------------------
POSITIONS: dict[str, tuple[float, float]] = {
    # Keeper and bowler (always present)
    "keeper":            (0.50, 0.60),
    "bowler":            (0.50, 0.38),

    # Close catchers — off side, behind batter
    "slip_1":            (0.42, 0.58),
    "slip_2":            (0.38, 0.60),
    "slip_3":            (0.34, 0.62),
    "gully":             (0.32, 0.55),
    "leg_slip":          (0.58, 0.60),

    # Close catchers — attacking
    "silly_point":       (0.42, 0.48),
    "silly_mid_off":     (0.45, 0.42),
    "silly_mid_on":      (0.55, 0.42),
    "short_leg":         (0.60, 0.55),

    # Inner ring — OFF SIDE (x < 0.50)
    "point":             (0.20, 0.50),
    "cover_point":       (0.22, 0.42),
    "cover":             (0.25, 0.35),
    "extra_cover":       (0.32, 0.28),
    "mid_off":           (0.42, 0.25),
    "backward_point":    (0.22, 0.58),

    # Inner ring — LEG SIDE (x > 0.50)
    "mid_on":            (0.58, 0.25),
    "midwicket":         (0.72, 0.35),
    "square_leg":        (0.80, 0.50),
    "forward_short_leg": (0.65, 0.45),
    "short_fine_leg":    (0.65, 0.65),

    # Outer ring — OFF SIDE
    "third_man":         (0.18, 0.75),
    "deep_point":        (0.10, 0.50),
    "deep_cover":        (0.12, 0.35),
    "deep_extra_cover":  (0.20, 0.22),
    "long_off":          (0.38, 0.10),
    "deep_backward_pt":  (0.15, 0.65),

    # Outer ring — LEG SIDE
    "long_on":           (0.62, 0.10),
    "deep_midwicket":    (0.82, 0.25),
    "deep_square_leg":   (0.90, 0.50),
    "deep_backward_sq":  (0.85, 0.65),
    "deep_fine_leg":     (0.78, 0.75),
    "fine_leg":          (0.72, 0.72),
}

_OUTSIDE_POSITIONS = frozenset({
    "third_man", "deep_point", "deep_cover", "deep_extra_cover",
    "long_off", "long_on", "deep_midwicket", "deep_square_leg",
    "deep_backward_sq", "deep_backward_pt", "deep_fine_leg", "fine_leg",
})

_CLOSE_POSITIONS = frozenset({
    "slip_1", "slip_2", "slip_3", "gully", "leg_slip",
    "silly_point", "silly_mid_off", "silly_mid_on", "short_leg",
})

_DEATH_BANNED = frozenset({
    "slip_1", "slip_2", "slip_3", "gully",
    "silly_point", "silly_mid_off", "silly_mid_on",
    "short_leg", "leg_slip",
})

_OUTER_TO_INNER: dict[str, str] = {
    "deep_point": "point",
    "deep_cover": "cover",
    "deep_extra_cover": "extra_cover",
    "long_off": "mid_off",
    "long_on": "mid_on",
    "deep_midwicket": "midwicket",
    "deep_square_leg": "square_leg",
    "deep_fine_leg": "short_fine_leg",
    "deep_backward_pt": "backward_point",
    "third_man": "backward_point",
    "deep_backward_sq": "square_leg",
    "fine_leg": "short_fine_leg",
}

# ---------------------------------------------------------------------------
# Templates  (each is a list of 9 fielder position names)
# ---------------------------------------------------------------------------
PACE_POWERPLAY = [
    "slip_1",        # catching, off side behind batter
    "gully",         # catching, wider off side
    "point",         # square off side, saving single
    "cover",         # in front of square, off side
    "mid_off",       # straight, off side
    "mid_on",        # straight, leg side
    "midwicket",     # in front of square, leg side
    "square_leg",    # square, leg side
    "fine_leg",      # boundary, behind square leg side (1 outside)
]

PACE_MIDDLE = [
    "point",             # inside, off
    "cover",             # inside, off
    "mid_off",           # inside, off
    "mid_on",            # inside, leg
    "midwicket",         # inside, leg
    "deep_square_leg",   # boundary, leg
    "deep_midwicket",    # boundary, leg
    "long_on",           # boundary, straight leg
    "third_man",         # boundary, behind off
]

PACE_DEATH = [
    "point",             # inside, off — yorker field
    "cover",             # inside, off
    "mid_off",           # inside, off
    "mid_on",            # inside, leg
    "long_off",          # boundary, straight off
    "long_on",           # boundary, straight leg
    "deep_midwicket",    # boundary, leg
    "deep_square_leg",   # boundary, leg
    "fine_leg",          # boundary, behind leg
]

SPIN_POWERPLAY = [
    "slip_1",        # catching, off side
    "point",         # inside, off
    "cover",         # inside, off
    "mid_off",       # inside, off
    "mid_on",        # inside, leg
    "midwicket",     # inside, leg
    "square_leg",    # inside, leg
    "short_leg",     # close catching, leg
    "fine_leg",      # boundary, behind leg (1 outside)
]

SPIN_MIDDLE = [
    "slip_1",            # catching, off
    "point",             # inside, off
    "cover",             # inside, off
    "mid_off",           # inside, off
    "mid_on",            # inside, leg
    "midwicket",         # inside, leg
    "deep_midwicket",    # boundary, leg
    "long_on",           # boundary, straight leg
    "deep_square_leg",   # boundary, leg
]

SPIN_DEATH = [
    "point",             # inside, off
    "cover",             # inside, off
    "mid_off",           # inside, off
    "mid_on",            # inside, leg
    "long_off",          # boundary, off
    "long_on",           # boundary, leg
    "deep_midwicket",    # boundary, leg
    "deep_square_leg",   # boundary, leg
    "deep_cover",        # boundary, off — sweeper
]

_TEMPLATES: dict[str, list[str]] = {
    "pace_powerplay": PACE_POWERPLAY,
    "pace_middle":    PACE_MIDDLE,
    "pace_death":     PACE_DEATH,
    "spin_powerplay": SPIN_POWERPLAY,
    "spin_middle":    SPIN_MIDDLE,
    "spin_death":     SPIN_DEATH,
}


KNOWN_SPINNERS = frozenset({
    "Kuldeep Yadav", "Yuzvendra Chahal", "Ravi Bishnoi",
    "Ravindra Jadeja", "Axar Patel", "Rashid Khan",
    "Varun Chakravarthy", "Ravichandran Ashwin",
    "Washington Sundar", "Manimaran Siddharth",
    "Mitchell Santner", "Ish Sodhi", "Adil Rashid",
    "Sunil Narine", "Krunal Pandya", "Shahbaz Ahmed",
    "Adam Zampa", "Noor Ahmad", "Rahul Chahar",
    "Piyush Chawla", "Amit Mishra", "Wanindu Hasaranga",
    "Prashant Solanki", "Anukul Roy", "Daksh Kamra",
})

_KNOWN_SPINNERS_UPPER = frozenset(n.upper() for n in KNOWN_SPINNERS)


def get_bowler_type(bowler_name: str | None,
                    roles: dict[str, str] | None = None) -> str:
    """Look up bowler type from known spinners list and name→role mapping."""
    if not bowler_name:
        return "pace"

    # Check known spinners first (case-insensitive)
    if bowler_name.upper() in _KNOWN_SPINNERS_UPPER:
        return "spin"

    if not roles:
        return "pace"

    name_upper = bowler_name.upper()
    for pname, role in roles.items():
        if pname.upper() == name_upper or name_upper in pname.upper():
            r = (role or "").lower()
            if any(x in r for x in ("spin", "slow", "orthodox", "wrist",
                                     "leg-break", "off-break", "sla")):
                return "spin"
            if any(x in r for x in ("fast", "pace", "seam", "medium")):
                return "pace"
    return "pace"


def _get_phase(overs: float) -> str:
    if overs <= 6:
        return "powerplay"
    if overs <= 16:
        return "middle"
    return "death"


def _pos_type(name: str) -> str:
    if name == "keeper":
        return "wk"
    if name == "bowler":
        return "bowler"
    if name in _CLOSE_POSITIONS:
        return "close"
    if name in _OUTSIDE_POSITIONS:
        return "out"
    return "in"


class CricketField:
    """Cricket-logic field state machine.

    Guarantees exactly 9 fielders + keeper + bowler at all times.
    """

    def __init__(self) -> None:
        self.current_positions: dict[str, float] = {}
        self.template: list[str] = list(PACE_POWERPLAY)
        self.template_name: str = "pace_powerplay"
        self.phase: str = "powerplay"
        self._current_overs: float = 0.0
        self._bowler_type: str = "pace"
        self.frames_with_same: int = 0
        self._frozen: bool = False
        self._last_update_over_int: int | None = None
        self._pending_reevaluation: bool = False

    # -- public properties ---------------------------------------------------

    @property
    def inside_count(self) -> int:
        return sum(1 for k in self.current_positions
                   if k not in ("keeper", "bowler")
                   and k not in _OUTSIDE_POSITIONS)

    @property
    def outside_count(self) -> int:
        return sum(1 for k in self.current_positions
                   if k in _OUTSIDE_POSITIONS)

    @property
    def confidence_label(self) -> str:
        vals = [v for k, v in self.current_positions.items()
                if k not in ("keeper", "bowler")]
        if not vals:
            return "low"
        avg = sum(vals) / len(vals)
        if avg >= 0.7:
            return "high"
        if avg >= 0.4:
            return "medium"
        return "low"

    # -- initialisation / template -------------------------------------------

    def initialize_from_match_context(self, overs: float | str | None,
                                      bowler_type: str = "pace") -> None:
        overs_f = float(overs or 0)
        self._current_overs = overs_f
        self._bowler_type = bowler_type
        self.phase = _get_phase(overs_f)

        key = f"{bowler_type}_{self.phase}"
        self.template = list(_TEMPLATES.get(key, PACE_POWERPLAY))
        self.template_name = key

        self.current_positions = {pos: 0.5 for pos in self.template}
        self.current_positions["keeper"] = 1.0
        self.current_positions["bowler"] = 1.0

    # -- observation updates -------------------------------------------------

    def update_from_observation(self, observed_positions: list,
                               frame_type: str = "scoreboard",
                               overs: float | None = None) -> None:
        """Update from YOLO / vision observations.

        Field is frozen per FULL over (int part of overs changes), or on
        wicket. Sub-ball changes (17.1→17.2) do NOT unfreeze.
        """
        if frame_type not in ("scoreboard", "SCOREBOARD"):
            return

        if self._pending_reevaluation:
            if overs is not None:
                self._current_overs = float(overs)
            self._reevaluate_template()

        if self._frozen:
            if overs is not None:
                ov_int = int(float(overs))
                if self._last_update_over_int is not None \
                        and ov_int == self._last_update_over_int:
                    return
                self._frozen = False
            else:
                return

        if not observed_positions or len(observed_positions) < 3:
            return

        xy_list: list[tuple[float, float]] = []
        for p in observed_positions:
            x = p.get("x") if isinstance(p, dict) else None
            y = p.get("y") if isinstance(p, dict) else None
            if x is not None and y is not None:
                xy_list.append((round(float(x), 2), round(float(y), 2)))
        if len(xy_list) < 3:
            return

        # Dedup YOLO observations at 2-decimal precision
        xy_list = list(set(xy_list))

        matched = self._match_to_named_positions(xy_list)

        # Ban death-over close catchers
        if self.phase == "death":
            for pos in _DEATH_BANNED:
                matched.pop(pos, None)

        if len(matched) >= 5:
            for pos_name, conf in matched.items():
                if pos_name in self.current_positions:
                    self.current_positions[pos_name] = min(
                        1.0, self.current_positions[pos_name] + 0.3)
                else:
                    self.current_positions[pos_name] = conf

            for pos_name in list(self.current_positions):
                if pos_name not in matched and pos_name not in ("keeper", "bowler"):
                    self.current_positions[pos_name] -= 0.1
                    if self.current_positions[pos_name] <= 0:
                        del self.current_positions[pos_name]

        self._enforce_cricket_rules()

        self._frozen = True
        self._last_update_over_int = int(float(overs)) if overs is not None else None

    # -- event hooks ---------------------------------------------------------

    def on_wicket(self) -> None:
        """Unfreeze field and queue re-evaluation — new batter may trigger field change."""
        self._frozen = False
        self._pending_reevaluation = True

    def on_over_change(self, new_overs: float | str | None,
                       bowler_type: str | None = None) -> None:
        self._frozen = False
        new_overs_f = float(new_overs or 0)
        old_phase = self.phase
        new_phase = _get_phase(new_overs_f)
        self._current_overs = new_overs_f
        self._last_update_over_int = int(new_overs_f)
        self.phase = new_phase
        if bowler_type is not None:
            self._bowler_type = bowler_type

        if old_phase != new_phase:
            bt = bowler_type or self._bowler_type
            high_conf = {k: v for k, v in self.current_positions.items()
                         if v >= 0.7 and k not in ("keeper", "bowler")}
            self.initialize_from_match_context(new_overs_f, bt)
            for k, v in high_conf.items():
                if k in POSITIONS:
                    self.current_positions[k] = v
            self._pending_reevaluation = False
        else:
            self._pending_reevaluation = True

    def on_bowler_change(self, new_bowler_type: str) -> None:
        if new_bowler_type != self._bowler_type:
            self._bowler_type = new_bowler_type
            self.initialize_from_match_context(
                self._current_overs, new_bowler_type)

    # -- output --------------------------------------------------------------

    def get_display_positions(self) -> list[dict]:
        """Return positions list for WebSocket payload / UI.

        Always: keeper + bowler + 2 batters = 4 fixed.
        Plus EXACTLY 9 fielders sorted by confidence, filled from template.
        """
        result: list[dict] = []

        # Fixed positions
        result.append({"name": "keeper", "x": 0.50, "y": 0.60,
                        "type": "wk", "confidence": 1.0})
        result.append({"name": "bowler", "x": 0.50, "y": 0.38,
                        "type": "bowler", "confidence": 1.0})
        result.append({"name": "striker", "x": 0.50, "y": 0.57,
                        "type": "bat", "confidence": 1.0})
        result.append({"name": "non", "x": 0.50, "y": 0.40,
                        "type": "bat", "confidence": 1.0})

        # Fielders: exactly 9, sorted by confidence (hard cap)
        fielders = {k: v for k, v in self.current_positions.items()
                    if k not in ("keeper", "bowler")}

        sorted_fielders = sorted(fielders.items(),
                                 key=lambda x: -x[1])[:9]

        added_names = set()
        for name, confidence in sorted_fielders:
            if name in POSITIONS:
                x, y = POSITIONS[name]
                result.append({
                    "name": name,
                    "x": round(x, 3),
                    "y": round(y, 3),
                    "type": _pos_type(name),
                    "confidence": round(max(0.3, confidence), 2),
                })
                added_names.add(name)

        # Fill from template if fewer than 9 fielders
        fielder_count = len(added_names)
        if fielder_count < 9:
            for tpl_pos in self.template:
                if tpl_pos not in added_names and tpl_pos in POSITIONS:
                    x, y = POSITIONS[tpl_pos]
                    result.append({
                        "name": tpl_pos,
                        "x": round(x, 3),
                        "y": round(y, 3),
                        "type": _pos_type(tpl_pos),
                        "confidence": 0.3,
                    })
                    added_names.add(tpl_pos)
                    fielder_count += 1
                    if fielder_count >= 9:
                        break

        return result

    # -- internals -----------------------------------------------------------

    def _reevaluate_template(self) -> None:
        """Force template refresh from current overs + bowler type.

        Called on the next frame after WICKET / over rollover so the field
        signature reflects the new context even when no fresh YOLO/vision
        observations are available. High-confidence positions survive.
        """
        self.phase = _get_phase(self._current_overs)
        key = f"{self._bowler_type}_{self.phase}"
        self.template = list(_TEMPLATES.get(key, PACE_POWERPLAY))
        self.template_name = key

        high_conf = {k: v for k, v in self.current_positions.items()
                     if v >= 0.7 and k not in ("keeper", "bowler")}
        self.current_positions = {pos: 0.5 for pos in self.template}
        self.current_positions["keeper"] = 1.0
        self.current_positions["bowler"] = 1.0
        for k, v in high_conf.items():
            if k in POSITIONS:
                self.current_positions[k] = v
        self._enforce_cricket_rules()
        self._pending_reevaluation = False

    def _match_to_named_positions(
        self, observed: list[tuple[float, float]]
    ) -> dict[str, float]:
        matched: dict[str, float] = {}
        used: set[str] = set()

        for ox, oy in observed:
            best_pos: str | None = None
            best_dist = float("inf")

            for pos_name, (px, py) in POSITIONS.items():
                if pos_name in used or pos_name in ("keeper", "bowler"):
                    continue
                dist = math.sqrt((ox - px) ** 2 + (oy - py) ** 2)
                if dist < best_dist and dist < 0.15:
                    best_dist = dist
                    best_pos = pos_name

            if best_pos:
                matched[best_pos] = max(0.5, 1.0 - best_dist * 5)
                used.add(best_pos)

        return matched

    def _enforce_cricket_rules(self) -> None:
        self.current_positions["keeper"] = 1.0
        self.current_positions["bowler"] = 1.0

        fielders = {k: v for k, v in self.current_positions.items()
                    if k not in ("keeper", "bowler")}

        # Death overs: remove close catchers
        if self.phase == "death":
            for pos in _DEATH_BANNED:
                fielders.pop(pos, None)

        # Fill from template if too few
        if len(fielders) < 9:
            for pos in self.template:
                if pos not in fielders and pos not in ("keeper", "bowler"):
                    fielders[pos] = 0.3
                if len(fielders) >= 9:
                    break

        # Still short? fill from all inner positions
        if len(fielders) < 9:
            for pos in POSITIONS:
                if pos not in fielders and pos not in ("keeper", "bowler"):
                    if pos not in _OUTSIDE_POSITIONS:
                        fielders[pos] = 0.3
                    if len(fielders) >= 9:
                        break

        # Trim to exactly 9
        if len(fielders) > 9:
            sorted_f = sorted(fielders.items(), key=lambda x: -x[1])
            fielders = dict(sorted_f[:9])

        # Powerplay: max 2 outside the circle
        if self._current_overs <= 6:
            outside = [k for k in fielders if k in _OUTSIDE_POSITIONS]
            if len(outside) > 2:
                extras = sorted(
                    [(k, fielders[k]) for k in outside],
                    key=lambda x: x[1],
                )
                for pos, _ in extras[:-2]:
                    inner = _OUTER_TO_INNER.get(pos)
                    if inner and inner not in fielders:
                        fielders[inner] = 0.4
                    del fielders[pos]
                # Re-trim
                if len(fielders) > 9:
                    sorted_f = sorted(fielders.items(), key=lambda x: -x[1])
                    fielders = dict(sorted_f[:9])

        self.current_positions = {"keeper": 1.0, "bowler": 1.0}
        self.current_positions.update(fielders)
