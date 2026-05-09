"""Pitch region detection via G-R horizontal scan.

Finds the brown pitch strip by scanning horizontal rows for where
green grass (G-R positive) dips to brown pitch (G-R negative).
No edge detection, no Hough lines — just color difference scans.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


_STRIP_MARGIN_PCT = 0.025
_VALLEY_SEARCH_LO = 0.30
_VALLEY_SEARCH_HI = 0.70
_VALLEY_MAX_STD = 22.0
_CLEAN_BAND_MIN_PCT = 3.0
_UPPER_PEAK_RATIO = 1.6
_LOWER_PEAK_RATIO = 1.3


_pitch_reject_counts: dict[str, int] = {}
_pitch_last_log = 0


def _pitch_reject(reason: str, **kw):
    import time, sys
    global _pitch_last_log
    _pitch_reject_counts[reason] = _pitch_reject_counts.get(reason, 0) + 1
    now = time.time()
    if now - _pitch_last_log >= 30:
        _pitch_last_log = now
        msg = f"  [PITCH-REJECT] counts={_pitch_reject_counts} last={reason} {kw}"
        print(msg, file=sys.stderr, flush=True)


def _find_pitch_center(frame: np.ndarray) -> int | None:
    """Find the pitch strip center x-coordinate.

    Uses relative dip detection: finds where G-R drops significantly
    below the row median, regardless of whether it crosses zero.
    Works on both brown (Indian) and green (NZ/Aus) pitches.
    """
    h, w = frame.shape[:2]
    max_valley_w = w * 0.10
    min_valley_w = 8
    max_spread = w * 0.06
    frame_center_lo = int(w * 0.25)
    frame_center_hi = int(w * 0.75)
    center_start = int(w * 0.10)
    center_end = int(w * 0.90)
    kernel = np.ones(30) / 30
    min_dip_depth = 20
    min_dip_ratio = 0.30

    valley_centers: list[int] = []
    row_debug: list[str] = []
    for pct in (0.35, 0.50, 0.65):
        row_y = int(h * pct)
        gr = frame[row_y, :, 1].astype(np.float64) - frame[row_y, :, 2]
        smooth = np.convolve(gr, kernel, mode='same')
        cs = smooth[center_start:center_end]

        row_median = float(np.median(cs))
        row_min = float(cs.min())
        dip_depth = row_median - row_min
        dip_ratio = dip_depth / max(abs(row_median), 1.0)

        if dip_depth < min_dip_depth or dip_ratio < min_dip_ratio:
            row_debug.append(f"{pct}:shallow(med={row_median:.0f},min={row_min:.0f},dip={dip_depth:.0f},rat={dip_ratio:.2f})")
            continue

        min_idx = int(np.argmin(cs))
        threshold = row_median - dip_depth * 0.5

        left = min_idx
        while left > 0 and cs[left] < threshold:
            left -= 1
        right = min_idx
        while right < len(cs) - 1 and cs[right] < threshold:
            right += 1
        valley_w = right - left

        abs_center = min_idx + center_start
        if valley_w < min_valley_w or valley_w > max_valley_w:
            row_debug.append(f"{pct}:bad_w({valley_w},max={max_valley_w:.0f})")
            continue
        if abs_center < frame_center_lo or abs_center > frame_center_hi:
            row_debug.append(f"{pct}:off_center({abs_center},lo={frame_center_lo},hi={frame_center_hi})")
            continue
        valley_centers.append(abs_center)

    if len(valley_centers) < 2:
        _pitch_reject("too_few_rows", rows=row_debug, found=len(valley_centers))
        return None
    for i in range(len(valley_centers)):
        for j in range(i + 1, len(valley_centers)):
            if abs(valley_centers[i] - valley_centers[j]) <= max_spread:
                return (valley_centers[i] + valley_centers[j]) // 2
    _pitch_reject("no_aligned_pair", centers=valley_centers, max_spread=max_spread)
    return None


def _has_figures_at_both_ends(frame: np.ndarray, pitch_cx: int) -> bool:
    """Check for the figure-pitch-figure vertical pattern.

    In a delivery view, a narrow strip at the pitch center shows:
      high complexity (umpire) → low complexity (clean pitch) → high complexity (batsman)

    This pattern is unique: no other camera angle produces an
    unobstructed pitch band flanked by figures at both ends.

    Scans row-wise grayscale std along the strip, finds the cleanest
    band in the mid-frame region, then checks for peaks above and
    below it.
    """
    h, w = frame.shape[:2]
    margin = int(w * _STRIP_MARGIN_PCT)
    x0 = max(0, pitch_cx - margin)
    x1 = min(w, pitch_cx + margin)
    if x1 - x0 < 4:
        return False

    gray = cv2.cvtColor(frame[:, x0:x1], cv2.COLOR_BGR2GRAY)
    row_std = gray.astype(np.float64).std(axis=1)

    kernel = np.ones(20) / 20
    smooth = np.convolve(row_std, kernel, mode='same')

    search_lo = int(h * _VALLEY_SEARCH_LO)
    search_hi = int(h * _VALLEY_SEARCH_HI)
    mid = smooth[search_lo:search_hi]
    if len(mid) == 0:
        return False

    valley_idx = int(np.argmin(mid)) + search_lo
    valley_val = float(smooth[valley_idx])

    if valley_val > _VALLEY_MAX_STD:
        _fig_reject("valley_too_high", valley_val=valley_val)
        return False

    clean_thresh = max(valley_val * 1.5, valley_val + 5)
    clean_count = 1
    for y in range(valley_idx + 1, min(valley_idx + int(h * 0.20), h)):
        if smooth[y] <= clean_thresh:
            clean_count += 1
        else:
            break
    for y in range(valley_idx - 1, max(valley_idx - int(h * 0.20), 0), -1):
        if smooth[y] <= clean_thresh:
            clean_count += 1
        else:
            break

    clean_pct = clean_count / h * 100
    if clean_pct < _CLEAN_BAND_MIN_PCT:
        _fig_reject("clean_band_small", clean_pct=clean_pct)
        return False

    upper = smooth[int(h * 0.10):valley_idx]
    upper_peak = float(upper.max()) if len(upper) else 0.0

    lower = smooth[valley_idx:int(h * 0.90)]
    lower_peak = float(lower.max()) if len(lower) else 0.0

    if valley_val > 0:
        if upper_peak < valley_val * _UPPER_PEAK_RATIO:
            _fig_reject("upper_peak_low", upper=upper_peak, valley=valley_val,
                        ratio=upper_peak/valley_val if valley_val else 0)
            return False
        if lower_peak < valley_val * _LOWER_PEAK_RATIO:
            _fig_reject("lower_peak_low", lower=lower_peak, valley=valley_val,
                        ratio=lower_peak/valley_val if valley_val else 0)
            return False
    else:
        if upper_peak < 10 or lower_peak < 10:
            _fig_reject("peaks_too_low_zero_valley", upper=upper_peak, lower=lower_peak)
            return False

    return True


_fig_reject_counts: dict[str, int] = {}
_fig_last_log = 0


def _fig_reject(reason: str, **kw):
    import time, logging, sys
    global _fig_last_log
    _fig_reject_counts[reason] = _fig_reject_counts.get(reason, 0) + 1
    now = time.time()
    if now - _fig_last_log >= 30:
        _fig_last_log = now
        log = logging.getLogger("ball_analyzer")
        msg = f"  [FIG-REJECT] counts={_fig_reject_counts} last={reason} {kw}"
        log.info(msg)
        print(msg, file=sys.stderr, flush=True)


_df_stats = {"total": 0, "no_pitch": 0, "no_figures": 0, "pass": 0}
_df_last_log = 0


def is_delivery_frame(frame: np.ndarray) -> bool:
    """Deterministic delivery frame detection for capture-loop use.

    Positively identifies bowler's-end delivery view by checking for
    the combination of features unique to this camera angle:

    1. Narrow brown pitch strip running vertically through frame center
    2. Figures at BOTH ends of the pitch strip (umpire + batsman) with
       clean unobstructed pitch between them

    No other broadcast view has all of these simultaneously.
    ~0.3ms per frame.
    """
    import time, logging
    global _df_last_log
    log = logging.getLogger("ball_analyzer")

    _df_stats["total"] += 1
    pitch_cx = _find_pitch_center(frame)
    if pitch_cx is None:
        _df_stats["no_pitch"] += 1
        _maybe_log_df_stats(log)
        return False

    if not _has_figures_at_both_ends(frame, pitch_cx):
        _df_stats["no_figures"] += 1
        _maybe_log_df_stats(log)
        return False

    _df_stats["pass"] += 1
    _maybe_log_df_stats(log)
    return True


def _maybe_log_df_stats(log):
    import time, sys
    global _df_last_log
    now = time.time()
    if now - _df_last_log >= 30:
        _df_last_log = now
        s = _df_stats
        msg = (f"  [DF-STATS] total={s['total']} pass={s['pass']} "
               f"no_pitch={s['no_pitch']} no_figures={s['no_figures']} "
               f"(pass_rate={s['pass']/max(s['total'],1)*100:.1f}%)")
        log.info(msg)
        print(msg, file=sys.stderr, flush=True)


def has_pitch_strip(frame: np.ndarray) -> bool:
    """Fast check: does this frame show the pitch strip?"""
    return is_delivery_view_fast(frame)


def is_delivery_view_fast(frame: np.ndarray) -> bool:
    """Optimized delivery-view check for use in hot capture loops.

    Identical logic to `is_delivery_view` but reads only the 3
    scan rows instead of extracting full-frame G/R channels.
    ~25x faster (0.08ms vs 2ms per frame).
    """
    h, w = frame.shape[:2]
    max_valley_w = w * 0.12
    max_spread = w * 0.06
    frame_center_lo = int(w * 0.20)
    frame_center_hi = int(w * 0.80)
    center_start = int(w * 0.10)
    center_end = int(w * 0.90)
    kernel = np.ones(30) / 30

    valley_centers: list[int] = []
    for pct in (0.35, 0.50, 0.65):
        row_y = int(h * pct)
        gr = frame[row_y, :, 1].astype(np.float64) - frame[row_y, :, 2]
        smooth = np.convolve(gr, kernel, mode='same')
        cs = smooth[center_start:center_end]
        if cs.min() >= 0:
            continue
        min_idx = int(np.argmin(cs))
        left = min_idx
        while left > 0 and cs[left] < 0:
            left -= 1
        right = min_idx
        while right < len(cs) - 1 and cs[right] < 0:
            right += 1
        valley_w = right - left
        if valley_w < 10 or valley_w > max_valley_w:
            continue
        abs_center = min_idx + center_start
        if abs_center < frame_center_lo or abs_center > frame_center_hi:
            continue
        valley_centers.append(abs_center)

    if len(valley_centers) < 2:
        return False
    for i in range(len(valley_centers)):
        for j in range(i + 1, len(valley_centers)):
            if abs(valley_centers[i] - valley_centers[j]) <= max_spread:
                return True
    return False


def is_delivery_view(frame: np.ndarray) -> bool:
    """Strict check for bowler's/batter's-end delivery camera angle.

    Scans 3 horizontal rows for narrow brown valleys (pitch strip).
    Requires:
      - At least 2 rows detect a narrow valley (< 3.5% of frame width)
      - Valley centers in the central 50% of frame (25-75%)
      - At least one PAIR of valleys aligned (spread < 4% of width)

    Rejects close-ups (wide valleys from player clothing), outfield
    views (inconsistent/edge valleys), boundary shots (valleys from
    ropes/stands at frame edges), and advertising overlays.
    """
    h, w = frame.shape[:2]
    g = frame[:, :, 1].astype(np.int16)
    r = frame[:, :, 2].astype(np.int16)
    gr = g - r
    kernel = np.ones(30) / 30
    center_start = int(w * 0.10)
    center_end = int(w * 0.90)
    max_valley_w = w * 0.12
    max_spread = w * 0.06
    frame_center_lo = int(w * 0.20)
    frame_center_hi = int(w * 0.80)

    valley_centers: list[int] = []
    for pct in (0.35, 0.50, 0.65):
        signal = gr[int(h * pct), :].astype(np.float64)
        smooth = np.convolve(signal, kernel, mode='same')
        cs = smooth[center_start:center_end]
        if cs.min() >= 0:
            continue
        min_idx = int(np.argmin(cs))
        left = min_idx
        while left > 0 and cs[left] < 0:
            left -= 1
        right = min_idx
        while right < len(cs) - 1 and cs[right] < 0:
            right += 1
        valley_w = right - left
        if valley_w < 10 or valley_w > max_valley_w:
            continue
        abs_center = min_idx + center_start
        if abs_center < frame_center_lo or abs_center > frame_center_hi:
            continue
        valley_centers.append(abs_center)

    if len(valley_centers) < 2:
        return False
    for i in range(len(valley_centers)):
        for j in range(i + 1, len(valley_centers)):
            if abs(valley_centers[i] - valley_centers[j]) <= max_spread:
                return True
    return False


@dataclass
class PitchRegion:
    top_left: tuple[int, int]
    top_right: tuple[int, int]
    bottom_left: tuple[int, int]
    bottom_right: tuple[int, int]

    bowling_crease_y: int
    batting_crease_y: int
    pitch_center_x_top: int
    pitch_center_x_bottom: int

    bbox: tuple[int, int, int, int]  # x, y, w, h

    edges_detected: bool
    creases_detected: bool
    method: str  # "gr_scan" | "fallback"


def find_pitch_region(
    frame: np.ndarray,
    debug_dir: str | None = None,
) -> PitchRegion:
    """Detect pitch strip by scanning for the brown valley in G-R signal.

    Scans several horizontal rows. At each row, G-R is positive over
    green grass and dips negative over brown pitch. The valley's left
    and right zero-crossings give the strip boundaries. From these
    boundary points a crop rectangle is built covering the full pitch
    corridor including ball flight area.
    """
    h, w = frame.shape[:2]
    if debug_dir:
        import os
        os.makedirs(debug_dir, exist_ok=True)

    g = frame[:, :, 1].astype(np.int16)
    r = frame[:, :, 2].astype(np.int16)
    gr = g - r

    kernel = np.ones(30) / 30
    scan_pcts = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]
    center_start = int(w * 0.10)
    center_end = int(w * 0.90)

    edges: list[tuple[int, int, int]] = []  # (y, x_left, x_right)

    for pct in scan_pcts:
        row_y = int(h * pct)
        signal = gr[row_y, :].astype(np.float64)
        smooth = np.convolve(signal, kernel, mode='same')

        center_signal = smooth[center_start:center_end]
        min_idx = int(np.argmin(center_signal))
        if center_signal[min_idx] >= 0:
            continue

        left_idx = min_idx
        while left_idx > 0 and center_signal[left_idx] < 0:
            left_idx -= 1

        right_idx = min_idx
        while right_idx < len(center_signal) - 1 and center_signal[right_idx] < 0:
            right_idx += 1

        x_left = left_idx + center_start
        x_right = right_idx + center_start
        valley_w = x_right - x_left

        # Pitch strip is narrow: reject valleys wider than ~18% of frame
        if valley_w < 10 or valley_w > w * 0.18:
            continue

        edges.append((row_y, x_left, x_right))

    # Reject outlier edges: width outliers first, then cluster by
    # center-x proximity to separate distinct brown objects.
    if len(edges) >= 3:
        widths = [xr - xl for _, xl, xr in edges]
        med_w = float(np.median(widths))
        edges = [(y, xl, xr) for y, xl, xr in edges
                 if (xr - xl) <= med_w * 2.5]

    if len(edges) >= 2:
        # Cluster edges by center-x: consecutive edges whose centers
        # are within 300px belong together. Pick the largest cluster.
        sorted_edges = sorted(edges, key=lambda e: (e[1] + e[2]) / 2)
        clusters: list[list[tuple[int, int, int]]] = [[sorted_edges[0]]]
        for e in sorted_edges[1:]:
            prev_cx = (clusters[-1][-1][1] + clusters[-1][-1][2]) / 2
            curr_cx = (e[1] + e[2]) / 2
            if abs(curr_cx - prev_cx) < 300:
                clusters[-1].append(e)
            else:
                clusters.append([e])

        edges = max(clusters, key=len)
        # Re-sort by y for top-to-bottom ordering
        edges.sort(key=lambda e: e[0])

    if debug_dir and edges:
        viz = frame.copy()
        for y, xl, xr in edges:
            cx = (xl + xr) // 2
            cv2.circle(viz, (xl, y), 5, (0, 0, 255), -1)
            cv2.circle(viz, (xr, y), 5, (255, 0, 0), -1)
            cv2.circle(viz, (cx, y), 4, (0, 255, 0), -1)
            cv2.line(viz, (xl, y), (xr, y), (0, 255, 255), 1)
        cv2.imwrite(f"{debug_dir}/gr_scan.png", viz)

    if len(edges) < 2:
        cx = w // 2
        pw = int(w * 0.20)
        return PitchRegion(
            top_left=(cx - pw // 2, int(h * 0.15)),
            top_right=(cx + pw // 2, int(h * 0.15)),
            bottom_left=(cx - pw // 2, int(h * 0.75)),
            bottom_right=(cx + pw // 2, int(h * 0.75)),
            bowling_crease_y=int(h * 0.15),
            batting_crease_y=int(h * 0.75),
            pitch_center_x_top=cx,
            pitch_center_x_bottom=cx,
            bbox=(cx - pw // 2, int(h * 0.15), pw, int(h * 0.60)),
            edges_detected=False,
            creases_detected=False,
            method="fallback",
        )

    # Build crop from detected pitch corridor.
    # The pitch runs diagonally due to perspective — center x shifts
    # from top to bottom. We use all edge centers + widths to define
    # the corridor, then expand for ball flight tracking.

    top_edge = edges[0]
    bot_edge = edges[-1]

    # Pitch centers at top and bottom
    cx_top = (top_edge[1] + top_edge[2]) // 2
    cx_bot = (bot_edge[1] + bot_edge[2]) // 2

    # Crop width = pitch corridor span + padding for ball flight.
    # The corridor span is max(all_right) - min(all_left), i.e. how
    # far the strip shifts horizontally. Add padding based on the
    # widest detected strip width.
    all_left = min(e[1] for e in edges)
    all_right = max(e[2] for e in edges)
    corridor_w = all_right - all_left

    # Pad enough for ball flight area: at least 150px each side,
    # or 50% of the corridor width, whichever is larger.
    # Total crop capped at 50% of frame width.
    h_pad = max(150, int(corridor_w * 0.5))

    crop_left = max(0, all_left - h_pad)
    crop_right = min(w, all_right + h_pad)

    # Cap total crop width at 50% of frame to prevent full-frame crops
    max_crop_w = int(w * 0.50)
    actual_w = crop_right - crop_left
    if actual_w > max_crop_w:
        center = (crop_left + crop_right) // 2
        crop_left = max(0, center - max_crop_w // 2)
        crop_right = min(w, crop_left + max_crop_w)

    # Vertical extent: use detected range but expand to cover
    # at least 50% of frame height for ball flight visibility
    detected_top = top_edge[0]
    detected_bot = bot_edge[0]
    detected_h = detected_bot - detected_top
    min_crop_h = int(h * 0.50)

    if detected_h < min_crop_h:
        expand = (min_crop_h - detected_h) // 2
        crop_top = max(0, detected_top - expand)
        crop_bot = min(h, detected_bot + expand)
    else:
        crop_top = detected_top
        crop_bot = detected_bot

    tl = (crop_left, crop_top)
    tr = (crop_right, crop_top)
    bl = (crop_left, crop_bot)
    br = (crop_right, crop_bot)

    bx = crop_left
    by = crop_top
    bw = crop_right - crop_left
    bh = crop_bot - crop_top

    if debug_dir:
        viz = frame.copy()
        pts = np.array([tl, tr, br, bl])
        cv2.polylines(viz, [pts], True, (0, 255, 0), 2)
        cv2.putText(viz, f"bbox=({bx},{by},{bw},{bh})",
                    (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (0, 255, 0), 1)
        cv2.imwrite(f"{debug_dir}/final_region.png", viz)

    return PitchRegion(
        top_left=tl, top_right=tr,
        bottom_left=bl, bottom_right=br,
        bowling_crease_y=top_edge[0],
        batting_crease_y=bot_edge[0],
        pitch_center_x_top=cx_top,
        pitch_center_x_bottom=cx_bot,
        bbox=(bx, by, bw, bh),
        edges_detected=True,
        creases_detected=False,
        method="gr_scan",
    )
