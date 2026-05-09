from __future__ import annotations


class FieldState:
    """Persistent field tracking. Updated every frame.
    Maintained like the scoreboard — only grows, never loses data."""

    def __init__(self):
        self.positions: list[dict] = []
        self.keeper_position: str | None = None  # "up" | "back"
        self.formation: str | None = None
        self.slips = 0
        self.close_catchers = 0
        self.inside_circle = 0
        self.outside_circle = 0

        self.history: list[dict] = []
        self.over_snapshots: list[dict] = []
        self.changes_log: list[dict] = []

        self.calibrated = False
        self.pitch_center: tuple[float, float] | None = None
        self.confidence = 0.0
        self.validated = False

        self.balls_since_observation = 0
        self.last_observed_frame = 0

        self.vision_zones: list[str | None] = []
        self.field_per_bowler: dict[str, list[dict]] = {}

    def update(self, positions: list[dict], frame_count: int,
               match_overs: str | None):
        old = self.positions
        self.positions = positions

        self._update_counts()
        self._classify_formation()

        keeper_pos = [p for p in positions if p.get("depth") == "keeper"]
        if keeper_pos:
            k = keeper_pos[0]
            self.keeper_position = "up" if k["distance"] < 0.04 else "back"

        if old:
            changes = self._detect_changes(old, positions)
            if changes:
                for c in changes:
                    c["frame"] = frame_count
                    c["over"] = match_overs
                    c["meaning"] = self._tactical_meaning(c)
                self.changes_log.extend(changes)

        self.confidence = min(len(positions) / 9.0, 1.0)
        self.validated = self.validate_against_rules(match_overs)

    def _update_counts(self):
        yolo_pos = [p for p in self.positions if p.get("x") is not None]
        self.slips = sum(1 for p in yolo_pos
                         if "slip" in p.get("zone", ""))
        self.close_catchers = sum(1 for p in yolo_pos
                                  if p.get("depth") == "close_catcher")
        self.inside_circle = sum(1 for p in yolo_pos
                                 if p.get("depth") == "inside_circle")
        self.outside_circle = sum(1 for p in yolo_pos
                                  if p.get("depth") == "outside_circle")
        self.vision_zones = [p.get("zone") for p in self.positions
                             if p.get("x") is None]

    # ------------------------------------------------------------------

    def _classify_formation(self):
        if self.close_catchers >= 2:
            self.formation = "attacking"
        elif self.outside_circle >= 5:
            self.formation = "defensive"
        else:
            self.formation = "balanced"

    def _detect_changes(self, old: list[dict],
                        new: list[dict]) -> list[dict]:
        changes: list[dict] = []
        used_new: set[int] = set()

        for o in old:
            if o.get("x") is None or o.get("y") is None:
                continue
            best_match = None
            best_dist = float("inf")
            for i, n in enumerate(new):
                if i in used_new:
                    continue
                if n.get("x") is None or n.get("y") is None:
                    continue
                dist = ((o["x"] - n["x"]) ** 2
                        + (o["y"] - n["y"]) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_match = i

            if best_match is not None:
                used_new.add(best_match)
                n = new[best_match]
                if o.get("zone") != n.get("zone"):
                    changes.append({
                        "from_zone": o["zone"],
                        "to_zone": n["zone"],
                        "from_depth": o.get("depth"),
                        "to_depth": n.get("depth"),
                        "distance_moved": best_dist,
                    })

        return changes

    def _tactical_meaning(self, change: dict) -> str:
        f = change.get("from_zone", "")
        t = change.get("to_zone", "")
        fd = change.get("from_depth", "")
        td = change.get("to_depth", "")

        if "slip" in f and "slip" not in t:
            return "slip removed — less catching pressure"
        if "slip" not in f and "slip" in t:
            return "slip added — expecting edge"
        if fd == "inside_circle" and td == "outside_circle":
            return f"{f} pushed back — defensive"
        if fd == "outside_circle" and td == "inside_circle":
            return f"{t} brought in — attacking"
        if "short_leg" in t:
            return "short leg set — expecting bat-pad"
        if "short_leg" in f:
            return "short leg removed"
        if "fine_leg" in t and td == "outside_circle":
            return "deep fine leg — protecting against top edges"
        return f"{f} moved to {t}"

    # ------------------------------------------------------------------

    def validate_against_rules(self, match_overs: str | None) -> bool:
        try:
            overs = float(match_overs) if match_overs else 0.0
        except (ValueError, TypeError):
            return True

        outside = self.outside_circle
        if overs <= 6 and outside > 2:
            if not getattr(self, "_pp_warned", False):
                print(f"[FIELD WARN] Powerplay but {outside} outside circle "
                      f"(max 2). Possible misclassification.")
                self._pp_warned = True
            return False
        else:
            self._pp_warned = False
        if 6 < overs <= 16 and outside > 5:
            if not getattr(self, "_mid_warned", False):
                print(f"[FIELD WARN] Middle overs but {outside} outside circle "
                      f"(max 5). Possible misclassification.")
                self._mid_warned = True
            return False
        else:
            self._mid_warned = False
        return True

    # ------------------------------------------------------------------

    def snapshot_over(self, match_overs: str | None,
                      bowler_name: str | None = None):
        snap = {
            "over": match_overs,
            "positions": [p.copy() for p in self.positions],
            "formation": self.formation,
            "slips": self.slips,
            "close": self.close_catchers,
            "inside": self.inside_circle,
            "outside": self.outside_circle,
        }
        self.over_snapshots.append(snap)

        if bowler_name:
            if bowler_name not in self.field_per_bowler:
                self.field_per_bowler[bowler_name] = []
            self.field_per_bowler[bowler_name].append(snap)

    def calibrate(self, broadcast_positions: list[dict]):
        self.positions = broadcast_positions
        self._update_counts()
        self._classify_formation()
        self.calibrated = True
        self.confidence = 1.0
        print(f"[FIELD] Calibrated from broadcast: {self.formation}, "
              f"{self.slips} slips, {len(broadcast_positions)} fielders")

    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        fielders_no_keeper = [p for p in self.positions
                              if p.get("depth") != "keeper"]
        keeper_data = None
        for p in self.positions:
            if p.get("depth") == "keeper":
                keeper_data = {"position": self.keeper_position,
                               "distance": p.get("distance")}
                break

        return {
            "positions": self.positions,
            "keeper": keeper_data,
            "formation": self.formation,
            "inside_circle": self.inside_circle,
            "outside_circle": self.outside_circle,
            "close_catchers": self.close_catchers,
            "slips": self.slips,
            "confidence": self.confidence,
            "fielders_detected": len(fielders_no_keeper),
            "calibrated": self.calibrated,
            "validated": self.validated,
        }

    def on_ball_event(self):
        """Track how stale the field data is."""
        self.balls_since_observation += 1

    def get_freshness(self) -> str:
        if self.balls_since_observation == 0:
            return "live"
        if self.balls_since_observation <= 2:
            return "recent"
        return "stale"

    def get_changes_since(self, frame_count: int) -> list[dict]:
        return [c for c in self.changes_log
                if c.get("frame", 0) >= frame_count - 20]

    def get_evolution(self) -> list[dict]:
        return self.over_snapshots
