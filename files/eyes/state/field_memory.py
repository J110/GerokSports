"""Persistent field tracking — merges YOLO dots with LLM-named positions."""
from __future__ import annotations

import time
from collections import defaultdict

from eyes.cricket_logger import CricketLogger

log = CricketLogger("FIELD")


STANDARD_POSITIONS = [
    "slip", "second_slip", "third_slip", "gully", "point", "cover",
    "extra_cover", "mid-off", "mid-on", "midwicket", "square_leg",
    "fine_leg", "third_man", "long_on", "long_off", "deep_cover",
    "deep_point", "deep_midwicket", "deep_square_leg", "short_leg",
    "silly_point", "silly_mid-on", "silly_mid-off", "leg_slip",
    "short_fine_leg", "short_third_man",
]


class FieldMemory:
    """Persistent field state, merging YOLO person dots with LLM field analysis.

    YOLO gives fast, continuous dot positions (every frame).
    LLM gives named positions (every extraction, ~1fps).
    Together: accurate real-time field tracking.
    """

    def __init__(self):
        self._yolo_dots: list[dict] = []
        self._llm_positions: list[str] = []
        self._keeper_position: str | None = None
        self._attacking_or_defensive: str | None = None
        self._changes_history: list[dict] = []
        self._evolution: list[dict] = []  # per-over snapshots
        self._last_yolo_frame = 0
        self._last_llm_frame = 0
        self._broadcast_field_graphic: dict | None = None

    def update_from_yolo(self, dots: list[dict], frame_number: int):
        """Update dot positions from YOLO person detection."""
        self._yolo_dots = dots
        self._last_yolo_frame = frame_number
        count = len(dots)
        if count > 0:
            log.info(f"YOLO: {count} fielders detected")
            if count > 13:
                log.warn(f"YOLO detected {count} people — includes batters/umpires, filtering")
        elif count == 0 and frame_number > 10:
            log.error("YOLO detected 0 people — not a field view frame")

    def update_from_llm(self, field_data: dict, frame_number: int):
        """Update named positions from LLM extraction."""
        if not field_data:
            return

        prev_positions = set(self._llm_positions)

        positions = field_data.get("positions", [])
        if isinstance(positions, list):
            self._llm_positions = [str(p) for p in positions if p]
            if self._llm_positions:
                log.info(f"LLM positions: {', '.join(self._llm_positions)}")

                # Warn on mismatch with YOLO
                yolo_count = len(self._yolo_dots)
                llm_count = len(self._llm_positions)
                if yolo_count > 0 and abs(llm_count - yolo_count) > 3:
                    log.warn(f"LLM field doesn't match YOLO dots — {llm_count} LLM vs {yolo_count} YOLO visible")

        keeper = field_data.get("keeper_position")
        if keeper and keeper != "null":
            self._keeper_position = keeper

        style = field_data.get("attacking_or_defensive")
        if style and style != "null":
            self._attacking_or_defensive = style

        # Track changes
        changes = field_data.get("changes_from_last_ball")
        if changes and changes != "null":
            log.info(f"Change: {changes}")
            self._changes_history.append({
                "frame": frame_number,
                "change": changes,
                "timestamp": time.time(),
            })

        # Detect position changes
        new_positions = set(self._llm_positions)
        if prev_positions and new_positions != prev_positions:
            added = new_positions - prev_positions
            removed = prev_positions - new_positions
            if added or removed:
                self._changes_history.append({
                    "frame": frame_number,
                    "added": list(added),
                    "removed": list(removed),
                    "timestamp": time.time(),
                })

        # Broadcast field graphic override
        graphic = field_data.get("broadcast_field_graphic")
        if graphic and graphic != "null":
            self._broadcast_field_graphic = graphic

        self._last_llm_frame = frame_number

    def snapshot_for_over(self, over_number: str):
        """Take a snapshot of the current field for evolution tracking."""
        log.info(f"New over: field snapshot saved (over {over_number}, {len(self._llm_positions)} positions)")
        self._evolution.append({
            "over": over_number,
            "positions": list(self._llm_positions),
            "keeper": self._keeper_position,
            "style": self._attacking_or_defensive,
            "dot_count": len(self._yolo_dots),
            "timestamp": time.time(),
        })

    def get_current(self) -> dict:
        return {
            "yolo_dots": self._yolo_dots,
            "positions": self._llm_positions,
            "keeper_position": self._keeper_position,
            "style": self._attacking_or_defensive,
            "dot_count": len(self._yolo_dots),
        }

    def get_current_positions(self) -> list[str]:
        return list(self._llm_positions)

    def get_full_state(self) -> dict:
        return {
            "current": self.get_current(),
            "changes_history": self._changes_history[-20:],
            "evolution": self._evolution,
            "broadcast_graphic": self._broadcast_field_graphic,
            "last_yolo_frame": self._last_yolo_frame,
            "last_llm_frame": self._last_llm_frame,
        }

    def get_change_summary(self, last_n: int = 5) -> list[dict]:
        return self._changes_history[-last_n:]

    def reset(self):
        self.__init__()
