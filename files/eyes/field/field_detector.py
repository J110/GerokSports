from __future__ import annotations

import math

import cv2
import numpy as np
from ultralytics import YOLO

# 16 inside-circle sectors (22.5° each)
_IC_ZONES = [
    (349, 11,  "IC-mid_off"),
    (11,  34,  "IC-extra_cover"),
    (34,  56,  "IC-cover"),
    (56,  79,  "IC-cover_point"),
    (79,  101, "IC-point"),
    (101, 124, "IC-backward_point"),
    (124, 146, "IC-gully"),
    (146, 169, "IC-slip_region"),
    (169, 191, "IC-behind_keeper_off"),
    (191, 214, "IC-leg_slip_region"),
    (214, 236, "IC-short_leg_area"),
    (236, 259, "IC-backward_square"),
    (259, 281, "IC-square_leg"),
    (281, 304, "IC-midwicket"),
    (304, 326, "IC-wide_mid_on"),
    (326, 349, "IC-mid_on"),
]

# 24 outside-circle sectors (15° each)
_OC_ZONES = [
    (353, 8,   "OC-long_off"),
    (8,   23,  "OC-wide_long_off"),
    (23,  38,  "OC-deep_extra_cover"),
    (38,  53,  "OC-deep_cover"),
    (53,  68,  "OC-deep_cover_point"),
    (68,  83,  "OC-deep_point"),
    (83,  98,  "OC-deep_backward_point"),
    (98,  113, "OC-deep_gully"),
    (113, 128, "OC-third_man_square"),
    (128, 143, "OC-third_man_fine"),
    (143, 158, "OC-deep_third_man"),
    (158, 173, "OC-fine_third_man"),
    (173, 188, "OC-behind_keeper"),
    (188, 203, "OC-fine_leg_fine"),
    (203, 218, "OC-fine_leg"),
    (218, 233, "OC-deep_fine_leg"),
    (233, 248, "OC-deep_backward_square"),
    (248, 263, "OC-deep_square_leg"),
    (263, 278, "OC-deep_midwicket_sq"),
    (278, 293, "OC-deep_midwicket"),
    (293, 308, "OC-deep_mid_on_area"),
    (308, 323, "OC-wide_long_on"),
    (323, 338, "OC-long_on"),
    (338, 353, "OC-straight_long_on"),
]


def _match_sector(angle: float, table: list[tuple[int, int, str]],
                  fallback: str) -> str:
    for start, end, name in table:
        if start > end:
            if angle >= start or angle < end:
                return name
        elif start <= angle < end:
            return name
    return fallback


class FieldDetector:
    """YOLO person detection on every frame. CPU only. ~50ms."""

    def __init__(self):
        self.yolo = YOLO("yolov8n.pt")
        self.pitch_center = {"x": 0.5, "y": 0.7}
        self.pitch_calibrated = False

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect_people(self, frame: np.ndarray) -> list[dict]:
        results = self.yolo(frame, classes=[0], conf=0.25, verbose=False)

        dots: list[dict] = []
        h, w = frame.shape[:2]

        for box in results[0].boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cx = (x1 + x2) / 2 / w
            cy = y2 / h
            conf = box.conf[0].item()
            bw = (x2 - x1) / w
            bh = (y2 - y1) / h

            dots.append({
                "x": round(cx, 3),
                "y": round(cy, 3),
                "conf": round(conf, 2),
                "width": round(bw, 3),
                "height": round(bh, 3),
            })

        return dots

    def filter_fielders(self, dots: list[dict]) -> list[dict]:
        fielders: list[dict] = []
        pitch_width = 0.03

        for dot in dots:
            if dot["height"] > 0.35:
                continue
            if dot["height"] < 0.015:
                continue

            dx = dot["x"] - self.pitch_center["x"]
            dy = dot["y"] - self.pitch_center["y"]
            dist = (dx ** 2 + dy ** 2) ** 0.5

            if dist < 0.05 and abs(dx) < pitch_width:
                continue

            fielders.append(dot)

        return fielders

    # ------------------------------------------------------------------
    # 40-sector zone classification + close catchers
    # ------------------------------------------------------------------

    def classify_zones(self, fielders: list[dict]) -> list[dict]:
        positions: list[dict] = []

        for f in fielders:
            dx = f["x"] - self.pitch_center["x"]
            dy = self.pitch_center["y"] - f["y"]

            dist = (dx ** 2 + dy ** 2) ** 0.5
            angle = math.degrees(math.atan2(dx, dy)) % 360

            if dist < 0.05:
                depth = "close_catcher"
                zone = self._close_catcher_zone(angle)
            elif dist < 0.25:
                depth = "inside_circle"
                zone = _match_sector(angle, _IC_ZONES, "IC-unknown")
            else:
                depth = "outside_circle"
                zone = _match_sector(angle, _OC_ZONES, "OC-unknown")

            positions.append({
                "zone": zone,
                "depth": depth,
                "angle": round(angle, 1),
                "distance": round(dist, 3),
                "x": f["x"],
                "y": f["y"],
                "conf": f["conf"],
            })

        self._tag_keeper(positions)
        return positions

    @staticmethod
    def _close_catcher_zone(angle: float) -> str:
        if 140 <= angle < 165:
            return "CC-slip_1"
        if 120 <= angle < 140:
            return "CC-slip_2"
        if 105 <= angle < 120:
            return "CC-gully_close"
        if 70 <= angle < 105:
            return "CC-silly_point"
        if 30 <= angle < 70:
            return "CC-silly_mid_off"
        if 210 <= angle < 240:
            return "CC-short_leg"
        if 195 <= angle < 210:
            return "CC-leg_slip"
        if angle >= 330 or angle < 30:
            return "CC-silly_mid_on"
        return "CC-unknown"

    @staticmethod
    def _tag_keeper(positions: list[dict]):
        """Tag the person closest behind the stumps as KEEPER."""
        candidates = [p for p in positions
                      if p["distance"] < 0.08 and 160 < p["angle"] < 200]
        if candidates:
            keeper = min(candidates, key=lambda p: p["distance"])
            keeper["zone"] = "KEEPER"
            keeper["depth"] = "keeper"

    # ------------------------------------------------------------------
    # Pitch detection
    # ------------------------------------------------------------------

    def set_pitch_center(self, x: float, y: float):
        self.pitch_center = {"x": x, "y": y}
        print(f"[FIELD] Pitch center set to ({x:.2f}, {y:.2f})")

    def auto_detect_pitch(self, frame: np.ndarray) -> bool:
        """Green-mask fallback — only used if people-cluster fails."""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        lower_green = np.array([30, 40, 40])
        upper_green = np.array([80, 255, 255])
        green_mask = cv2.inRange(hsv, lower_green, upper_green)

        coords = np.column_stack(np.where(green_mask > 0))
        if len(coords) > 100:
            cy, cx = coords.mean(axis=0)
            h, w = frame.shape[:2]
            self.pitch_center = {"x": cx / w, "y": cy / h}
            return True

        return False

    def auto_detect_pitch_from_people(self, dots: list[dict]) -> bool:
        """Find pitch center from the densest 4-person cluster.

        The pitch area always has the densest group of people
        (2 batters, bowler, keeper, umpires).
        """
        if len(dots) < 4:
            return False

        from itertools import combinations

        xs = [d["x"] for d in dots]
        ys = [d["y"] for d in dots]

        best_cluster: tuple | None = None
        best_spread = float("inf")

        n = len(dots)
        # Cap combinations for large counts to avoid O(n^4)
        if n > 15:
            indices = range(15)
        else:
            indices = range(n)

        for combo in combinations(indices, 4):
            cx_spread = max(xs[i] for i in combo) - min(xs[i] for i in combo)
            cy_spread = max(ys[i] for i in combo) - min(ys[i] for i in combo)
            spread = cx_spread + cy_spread
            if spread < best_spread:
                best_spread = spread
                best_cluster = combo

        if best_cluster and best_spread < 0.3:
            cx = sum(xs[i] for i in best_cluster) / 4
            cy = sum(ys[i] for i in best_cluster) / 4
            self.pitch_center = {"x": round(cx, 3), "y": round(cy, 3)}
            self.pitch_calibrated = True
            print(f"[FIELD] Pitch detected from people cluster: "
                  f"({cx:.2f}, {cy:.2f}) spread={best_spread:.3f}")
            return True

        return False
