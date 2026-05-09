from __future__ import annotations


ZONE_MAP = {
    "mid-off": "IC-mid_off",
    "mid off": "IC-mid_off",
    "extra cover": "IC-extra_cover",
    "cover": "IC-cover",
    "cover point": "IC-cover_point",
    "point": "IC-point",
    "backward point": "IC-backward_point",
    "gully": "IC-gully",
    "slip": "CC-slip_1",
    "first slip": "CC-slip_1",
    "second slip": "CC-slip_2",
    "third slip": "CC-slip_2",
    "silly point": "CC-silly_point",
    "short leg": "CC-short_leg",
    "leg slip": "CC-leg_slip",
    "square leg": "IC-square_leg",
    "midwicket": "IC-midwicket",
    "mid-on": "IC-mid_on",
    "mid on": "IC-mid_on",
    "deep cover": "OC-deep_cover",
    "deep point": "OC-deep_point",
    "deep midwicket": "OC-deep_midwicket",
    "deep square leg": "OC-deep_square_leg",
    "deep fine leg": "OC-deep_fine_leg",
    "long off": "OC-long_off",
    "long-off": "OC-long_off",
    "long on": "OC-long_on",
    "long-on": "OC-long_on",
    "third man": "OC-third_man_square",
    "fine leg": "OC-fine_leg",
    "deep extra cover": "OC-deep_extra_cover",
    "deep backward point": "OC-deep_backward_point",
    "deep backward square": "OC-deep_backward_square",
    "backward square leg": "IC-backward_square",
    "short fine leg": "OC-fine_leg_fine",
    "deep mid-on": "OC-deep_mid_on_area",
    "deep mid on": "OC-deep_mid_on_area",
    "wide long-on": "OC-wide_long_on",
    "wide long on": "OC-wide_long_on",
    "wide long-off": "OC-wide_long_off",
    "wide long off": "OC-wide_long_off",
}


def _infer_depth(zone_name: str) -> str:
    if zone_name.startswith("CC-"):
        return "close_catcher"
    if zone_name.startswith("IC-"):
        return "inside_circle"
    if zone_name.startswith("OC-"):
        return "outside_circle"
    return "unknown"


class FieldMerger:
    """Combines YOLO dot detection with vision descriptions
    to produce the best possible field picture per frame."""

    def __init__(self):
        self.last_merged: dict | None = None

    def merge(self, yolo_positions: list[dict] | None,
              vision_field: dict | None,
              frame_count: int) -> dict:
        """Merge YOLO positions with vision observations.

        YOLO: precise coordinates, but misses fielders on closeups.
        Vision: natural language positions, sees background fielders.

        Strategy:
        - If YOLO has 6+: trust YOLO, supplement with vision
        - If YOLO has 3-5: partial YOLO, fill gaps from vision
        - If YOLO has 0-2: trust vision entirely
        """
        yolo_count = len(yolo_positions) if yolo_positions else 0
        vision_count = 0
        vision_positions: list[str] = []

        if vision_field and vision_field.get("visible_fielders"):
            vision_count = vision_field["visible_fielders"]
            vision_positions = vision_field.get("positions", [])

        merged: dict = {
            "positions": [],
            "source": "none",
            "yolo_count": yolo_count,
            "vision_count": vision_count,
            "keeper": None,
            "confidence": 0.0,
        }

        if yolo_count >= 6:
            merged["positions"] = list(yolo_positions or [])
            merged["source"] = "yolo"
            merged["confidence"] = yolo_count / 9.0
            self._supplement_from_vision(
                merged["positions"], vision_positions, conf=0.5)

        elif yolo_count >= 3:
            merged["positions"] = list(yolo_positions or [])
            merged["source"] = "yolo+vision"
            self._supplement_from_vision(
                merged["positions"], vision_positions, conf=0.4)
            merged["confidence"] = len(merged["positions"]) / 9.0

        elif vision_count > 0:
            for vz in vision_positions:
                zone_name = self._normalize_vision_zone(vz)
                if zone_name:
                    merged["positions"].append({
                        "zone": zone_name,
                        "depth": _infer_depth(zone_name),
                        "source": "vision",
                        "x": None, "y": None,
                        "conf": 0.3,
                    })
            merged["source"] = "vision_only"
            merged["confidence"] = len(merged["positions"]) / 9.0

        else:
            if self.last_merged:
                merged = {**self.last_merged}
                merged["source"] = "held"
                merged["confidence"] = max(
                    0.0, merged.get("confidence", 0.0) - 0.1)
            else:
                merged["source"] = "none"
                merged["confidence"] = 0.0

        if vision_field and vision_field.get("keeper_visible"):
            merged["keeper"] = vision_field.get("keeper_position")

        if merged["source"] != "held":
            self.last_merged = {**merged}

        return merged

    # ------------------------------------------------------------------

    def _supplement_from_vision(self, positions: list[dict],
                                vision_positions: list[str],
                                conf: float):
        """Add vision-observed zones that YOLO missed."""
        yolo_zones = {p["zone"] for p in positions}
        for vz in vision_positions:
            zone_name = self._normalize_vision_zone(vz)
            if zone_name and not any(zone_name in yz for yz in yolo_zones):
                positions.append({
                    "zone": zone_name,
                    "depth": _infer_depth(zone_name),
                    "source": "vision",
                    "x": None, "y": None,
                    "conf": conf,
                })

    @staticmethod
    def _normalize_vision_zone(zone_text) -> str | None:
        """Map vision's natural language to our zone system."""
        if not zone_text or not isinstance(zone_text, str):
            return None
        return ZONE_MAP.get(zone_text.lower().strip())
