"""Separate ball detections into flight / bounce / post-shot phases."""
from __future__ import annotations


def separate_phases(
    detections: list[dict],
    pitch_height: int,
) -> dict:
    """Split detections into delivery phases.

    Each detection is ``{"frame": int, "x": int, "y": int, "area": float, ...}``.

    Returns::

        {
            "flight":       [detection, ...],   # ball from bowler to batter
            "bounce_point": detection | None,
            "post_shot":    [detection, ...],   # ball after batter plays
            "gap_frames":   (start, end) | None
        }
    """
    if not detections:
        return {}

    # Filter out edge detections (bottom 5% = bowler zone noise,
    # top 3% = ad board reflections)
    y_min = int(pitch_height * 0.03)
    y_max = int(pitch_height * 0.95)
    detections = [d for d in detections if y_min <= d["y"] <= y_max]
    if len(detections) < 2:
        return {}

    # --- find the longest gap (consecutive missing frames) ---
    frames_present = {d["frame"] for d in detections}
    f_min, f_max = detections[0]["frame"], detections[-1]["frame"]

    gap_start = gap_end = None
    cur_start = None
    longest = 0

    for f in range(f_min, f_max + 1):
        if f not in frames_present:
            if cur_start is None:
                cur_start = f
        else:
            if cur_start is not None:
                length = f - cur_start
                if length > longest:
                    longest = length
                    gap_start = cur_start
                    gap_end = f
                cur_start = None

    # --- split into flight / post-shot ---
    if gap_start is not None and longest >= 5:
        flight = [d for d in detections if d["frame"] < gap_start]
        post_shot = [d for d in detections if d["frame"] >= gap_end]
    else:
        # No clear gap — try splitting by area (post-shot blobs are larger)
        areas = sorted(d["area"] for d in detections)
        median = areas[len(areas) // 2]
        flight = [d for d in detections if d["area"] <= median * 2]
        post_shot = [d for d in detections if d["area"] > median * 2]
        if not post_shot:
            flight = detections
            post_shot = []

    # --- find bounce point within flight ---
    bounce_point = None
    if len(flight) >= 3:
        for i in range(1, len(flight) - 1):
            if (flight[i]["y"] >= flight[i - 1]["y"]
                    and flight[i]["y"] >= flight[i + 1]["y"]):
                bounce_point = flight[i]
                break
        if bounce_point is None:
            bounce_point = max(flight, key=lambda d: d["y"])

    return {
        "flight": flight,
        "bounce_point": bounce_point,
        "post_shot": post_shot,
        "gap_frames": (gap_start, gap_end) if gap_start else None,
    }
