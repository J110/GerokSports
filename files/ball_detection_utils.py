"""Ball detection via white-ball color filter + frame differencing + player masking.

Extracted from ball_diff_test_v2.py for use by the live Scout+Burst pipeline.
"""
from __future__ import annotations

import cv2
import numpy as np


def detect_white_ball(
    prev_crop: np.ndarray,
    curr_crop: np.ndarray,
    threshold: int = 20,
    white_hsv_low: tuple = (0, 0, 180),
    white_hsv_high: tuple = (180, 80, 255),
    min_blob: int = 5,
    max_blob: int = 500,
    player_area_min: int = 2000,
) -> list[dict]:
    """Detect white ball candidates between two pre-cropped frames.

    Returns list of dicts sorted by area (smallest first):
        [{"x": int, "y": int, "area": float, "w": int, "h": int}, ...]
    """
    gray_prev = cv2.GaussianBlur(
        cv2.cvtColor(prev_crop, cv2.COLOR_BGR2GRAY), (3, 3), 1)
    gray_curr = cv2.GaussianBlur(
        cv2.cvtColor(curr_crop, cv2.COLOR_BGR2GRAY), (3, 3), 1)

    diff = cv2.absdiff(gray_curr, gray_prev)
    _, diff_mask = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)

    # White ball mask in both frames
    white_curr = cv2.inRange(
        cv2.cvtColor(curr_crop, cv2.COLOR_BGR2HSV),
        white_hsv_low, white_hsv_high)
    white_prev = cv2.inRange(
        cv2.cvtColor(prev_crop, cv2.COLOR_BGR2HSV),
        white_hsv_low, white_hsv_high)
    white_either = cv2.bitwise_or(white_curr, white_prev)

    ball_mask = cv2.bitwise_and(diff_mask, white_either)

    # Remove large motion blobs (players/fielders)
    pk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
    player_mask = cv2.erode(cv2.dilate(diff_mask, pk, iterations=2),
                            pk, iterations=2)
    contours_p, _ = cv2.findContours(
        player_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    large_mask = np.zeros_like(diff_mask)
    for c in contours_p:
        if cv2.contourArea(c) > player_area_min:
            cv2.drawContours(large_mask, [c], -1, 255, -1)

    ball_clean = cv2.morphologyEx(
        cv2.bitwise_and(ball_mask, cv2.bitwise_not(large_mask)),
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
    )

    contours, _ = cv2.findContours(
        ball_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates: list[dict] = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < min_blob or area > max_blob:
            continue
        bx, by, bw, bh = cv2.boundingRect(c)
        aspect = bw / max(bh, 1)
        if aspect < 0.25 or aspect > 4.0:
            continue
        candidates.append({
            "x": bx + bw // 2,
            "y": by + bh // 2,
            "area": area,
            "w": bw,
            "h": bh,
        })

    candidates.sort(key=lambda c: c["area"])
    return candidates


def find_pitch_crop(frame: np.ndarray) -> tuple[int, int, int, int]:
    """Auto-detect pitch region from a wide-shot broadcast frame.

    Uses the PitchRegion detector (green-gap + crease lines) for accurate
    perspective-aware detection.  Falls back to a center crop if detection
    fails or if pitch_detector is unavailable.

    Returns (x, y, w, h) bounding box.
    """
    try:
        from pitch_detector import find_pitch_region
        region = find_pitch_region(frame)
        return region.bbox
    except Exception:
        pass

    # Fallback: generous center crop
    h, w = frame.shape[:2]
    return (int(w * 0.15), int(h * 0.05), int(w * 0.55), int(h * 0.65))


def find_video_region(frame: np.ndarray) -> tuple[int, int, int, int]:
    """Find the video player content area within a full-screen capture.

    Strips black letterbox borders.
    Returns (x, y, w, h) of the video content rectangle.
    """
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Scan from top to find first row with significant content (>20% bright)
    y_top = 0
    for y in range(min(200, h)):
        row_mean = gray[y, w // 4: 3 * w // 4].mean()
        if row_mean > 25:
            y_top = y
            break

    # Scan from bottom
    y_bot = h
    for y in range(h - 1, max(h - 200, 0), -1):
        row_mean = gray[y, w // 4: 3 * w // 4].mean()
        if row_mean > 25:
            y_bot = y + 1
            break

    # Left/right (check for black bars)
    x_left = 0
    for x in range(min(200, w)):
        col_mean = gray[h // 3: 2 * h // 3, x].mean()
        if col_mean > 20:
            x_left = x
            break

    x_right = w
    for x in range(w - 1, max(w - 200, 0), -1):
        col_mean = gray[h // 3: 2 * h // 3, x].mean()
        if col_mean > 20:
            x_right = x + 1
            break

    vw = x_right - x_left
    vh = y_bot - y_top
    if vw < w * 0.5 or vh < h * 0.3:
        return (0, 0, w, h)
    return (x_left, y_top, vw, vh)


def is_wide_shot(frame: np.ndarray) -> bool:
    """Heuristic: does this frame show a wide/outdoor pitch-area view?

    Tuned for RECALL over precision.  False positives are acceptable
    (the diff pipeline will find zero ball candidates and skip them).
    False negatives lose delivery frames forever — so keep thresholds
    low.  Checks for green outfield on both sides of the frame.
    """
    h, w = frame.shape[:2]
    region = frame[int(h * 0.2):int(h * 0.75), :]
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, (25, 30, 40), (85, 255, 200))
    green_pct = green.sum() / 255 / green.size * 100

    if green_pct < 15:
        return False

    rh, rw = green.shape[:2]
    left_green = green[:, :rw // 3].sum() / 255 / (rh * (rw // 3)) * 100
    right_green = green[:, 2 * rw // 3:].sum() / 255 / (rh * (rw - 2 * rw // 3)) * 100
    return left_green >= 8 and right_green >= 8
