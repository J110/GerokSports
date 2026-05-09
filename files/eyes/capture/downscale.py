"""Downscale utility for broadcast frames."""

import cv2
import numpy as np


def downscale(frame: np.ndarray, max_width: int = 1280) -> np.ndarray:
    """Resize frame so its width is at most max_width, preserving aspect ratio."""
    h, w = frame.shape[:2]
    if w <= max_width:
        return frame
    scale = max_width / w
    new_w = max_width
    new_h = int(h * scale)
    return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
