"""Finds the broadcast video rectangle within a browser window frame."""

import cv2
import numpy as np

from eyes.cricket_logger import CricketLogger

log = CricketLogger("BCAST")


class BroadcastDetector:
    """Detects the broadcast video region by finding green field pixels.

    Runs once, locks the region. Re-detects only on explicit request
    (e.g. window resize). Before green is found, returns the full frame
    so the LLM can handle pre-match graphics.
    """

    HSV_GREEN_LOW = np.array([30, 30, 40])
    HSV_GREEN_HIGH = np.array([85, 255, 255])
    MIN_GREEN_RATIO = 0.02
    ASPECT_TOLERANCE = 0.25  # 16:9 = 1.78, allow 1.33–2.22

    NO_GREEN_RESET_FRAMES = 30  # re-detect after this many frames with no green

    def __init__(self):
        self._region: tuple[int, int, int, int] | None = None  # x, y, w, h
        self._detected = False
        self._no_green_count = 0

    @property
    def detected(self) -> bool:
        return self._detected

    @property
    def region(self) -> tuple[int, int, int, int] | None:
        return self._region

    def detect(self, frame: np.ndarray) -> bool:
        """Attempt to detect the broadcast rectangle in the frame."""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.HSV_GREEN_LOW, self.HSV_GREEN_HIGH)

        green_ratio = np.count_nonzero(mask) / mask.size
        if green_ratio < self.MIN_GREEN_RATIO:
            return False

        log.info(f"Green field detected: {green_ratio*100:.0f}% of frame")

        # Find contours of green regions
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return False

        # Merge all green contours into a bounding box
        all_points = np.vstack(contours)
        x, y, w, h = cv2.boundingRect(all_points)

        # Expand to likely broadcast rectangle
        x, y, w, h = self._expand_to_broadcast(frame, x, y, w, h)

        # Validate aspect ratio (~16:9)
        aspect = w / max(h, 1)
        if not (1.78 - self.ASPECT_TOLERANCE * 1.78 <= aspect <= 1.78 + self.ASPECT_TOLERANCE * 1.78):
            return False

        # Must be a reasonable size (at least 40% of frame width)
        if w < frame.shape[1] * 0.4:
            return False

        self._region = (x, y, w, h)
        self._detected = True
        log.info(f"Broadcast region locked: ({x}, {y}, {w}, {h}) aspect={aspect:.2f}")
        return True

    def crop(self, frame: np.ndarray) -> np.ndarray:
        """Crop frame to the detected broadcast region, or return full frame."""
        if not self._detected or self._region is None:
            return frame
        x, y, w, h = self._region
        h_frame, w_frame = frame.shape[:2]
        x = max(0, x)
        y = max(0, y)
        x2 = min(x + w, w_frame)
        y2 = min(y + h, h_frame)
        cropped = frame[y:y2, x:x2]

        # Verify green field still present in cropped region
        hsv = cv2.cvtColor(cropped, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.HSV_GREEN_LOW, self.HSV_GREEN_HIGH)
        green_ratio = np.count_nonzero(mask) / max(mask.size, 1)
        if green_ratio < self.MIN_GREEN_RATIO:
            self._no_green_count += 1
            if self._no_green_count >= self.NO_GREEN_RESET_FRAMES:
                log.warn(f"No green field for {self._no_green_count} frames — re-detecting")
                self.reset()
        else:
            self._no_green_count = 0

        return cropped

    def reset(self):
        """Force re-detection (e.g. on window resize)."""
        log.warn("Window resized — re-detecting")
        self._region = None
        self._detected = False

    def _expand_to_broadcast(
        self, frame: np.ndarray, x: int, y: int, w: int, h: int
    ) -> tuple[int, int, int, int]:
        """Expand the green bounding box to the full broadcast rectangle.

        Green is only the field — the broadcast includes scoreboard bars
        above/below. We expand vertically to content boundaries.
        """
        fh, fw = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Expand upward: find where content starts (non-uniform rows)
        top = y
        for row in range(y, -1, -1):
            row_std = np.std(gray[row, x:x + w].astype(float))
            if row_std < 5:  # uniform row = browser chrome or black bar
                break
            top = row

        # Expand downward
        bottom = y + h
        for row in range(y + h, fh):
            row_std = np.std(gray[row, x:x + w].astype(float))
            if row_std < 5:
                break
            bottom = row

        # Expand left/right similarly
        left = x
        for col in range(x, -1, -1):
            col_std = np.std(gray[top:bottom, col].astype(float))
            if col_std < 5:
                break
            left = col

        right = x + w
        for col in range(x + w, fw):
            col_std = np.std(gray[top:bottom, col].astype(float))
            if col_std < 5:
                break
            right = col

        return (left, top, right - left, bottom - top)
