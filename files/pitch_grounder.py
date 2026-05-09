"""Moondream-based pitch grounding for delivery frame detection.

Uses cheap local filters to narrow ~340 buffer frames to ~3 candidates,
then Moondream's visual grounding (model.detect) to locate cricket stumps
on those candidates only.  Finding stumps confirms a delivery-view frame
and anchors the pitch ROI for ball detection.

Narrowing pipeline (per delivery):
  Filter 1: is_wide_shot           ~0.1 ms/frame  →  ~200 of 340
  Filter 2: has_center_strip       ~1   ms/frame  →  ~100
  Filter 3: temporal clustering    ~free          →  largest block
  Pick middle 3 from block         →  3 frames (+2 fallback)
  VLM (detect stumps)              ~1.25s/frame   →  1-3 confirmed

Backend: MLX-native Moondream 3 (int4 quantised).
Warm latency: 1245 ms/frame at 384 px on M1 Max (32 GB).
Total per delivery: 3 × 1.25s = 3.75s (5 × 1.25s = 6.25s with fallback).

``narrow_to_delivery_block()`` runs just the cheap filters (no VLM).
Used on the ROI cache-hit path in ``ball_analyzer`` to reject non-delivery
camera angles without re-running Moondream.

Set USE_VLM_GROUNDING = False to skip Moondream and use static ROI only
(centre of frame, 8-85% vertical). Useful under severe memory pressure.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

log = logging.getLogger("pitch_grounder")

try:
    from eyes.cricket_logger import _ensure_file_handler
    _fh = _ensure_file_handler()
    log.addHandler(_fh)
    log.setLevel(logging.DEBUG)
except Exception:
    pass

USE_VLM_GROUNDING = os.environ.get("USE_VLM_GROUNDING", "1") != "0"

DETECT_PROMPT = os.environ.get("PITCH_PROMPT", "stumps")

# Parallel VLM grounding: serial 3x ≈ 7.5s wall (2.5s/call steady state).
# Verified empirically (2026-04-18): MLX cannot handle concurrent calls
# to the same model — Metal asserts with
# "A command encoder is already encoding to this command buffer" and
# the whole process dies.  Default disabled (workers=1).  Even if MLX
# fixes this in a future release, set workers > 1 with caution.
# Set GROUND_PARALLEL_WORKERS > 1 to attempt parallel (will likely crash).
_GROUND_PARALLEL_WORKERS = int(
    os.environ.get("GROUND_PARALLEL_WORKERS", "1"))
_grounder_pool: ThreadPoolExecutor | None = None


def _get_pool() -> ThreadPoolExecutor | None:
    """Lazy thread pool for parallel Moondream calls."""
    global _grounder_pool
    if _GROUND_PARALLEL_WORKERS <= 1:
        return None
    if _grounder_pool is None:
        _grounder_pool = ThreadPoolExecutor(
            max_workers=_GROUND_PARALLEL_WORKERS,
            thread_name_prefix="grounder",
        )
    return _grounder_pool

_MLX_BACKEND_DIR = os.path.expanduser(
    "~/.moondream-station/models/backends/mlx_backend_v2"
)

# Pin Moondream input to a single fixed shape so MLX kernels stay
# cached across calls.  Variable input shapes force MLX to recompile
# the Metal shader graph on every call which adds 1.5-2s per detect.
# 384x384 square keeps the input small enough for fast inference and
# eliminates per-call recompilation.  Verified with `pin_input_shape`
# experiment: 384x384 fixed → ~1.2s/call steady, vs 384x216 variable
# → 2.5-3s/call due to broadcast aspect-ratio jitter.
_RESIZE_WIDTH = 384
_PIN_INPUT_SHAPE = True
_PINNED_SIDE = 384

# ── Stump-box validation thresholds (normalised coords) ────────────
_MAX_STUMP_AREA = 0.03       # stumps occupy < 3 % of frame
_MAX_STUMP_WIDTH = 0.12      # width < 12 %
_MAX_STUMP_HEIGHT = 0.25     # height < 25 %
_MIN_STUMP_HEIGHT = 0.02     # avoid noise specks
_STUMP_CENTER_X_LO = 0.20
_STUMP_CENTER_X_HI = 0.85


@dataclass
class PitchBox:
    """Pixel-coordinate pitch ROI (derived from stump position)."""
    x: int
    y: int
    w: int
    h: int
    confidence: float = 1.0
    moondream_ms: float = 0.0
    stump_x_norm: float = 0.0     # stump centre-x in [0,1]
    stump_y_norm: float = 0.0     # stump centre-y in [0,1]


class PitchROICache:
    """Per-bowling-end cache that collapses VLM cost from per-delivery to per-match.

    Cricket bowls from alternating ends each over: even overs from End A,
    odd overs from End B.  The bowler's-end camera is a fixed mount that
    doesn't move during a match, so the pitch ROI is the same for all
    deliveries from the same end.

    Typical cost: 2 VLM calibrations per innings (one per end), then
    pure cache hits for the remaining ~118 deliveries.
    """

    def __init__(self):
        self._ends: dict[str, PitchBox] = {}   # "1_A", "1_B", "2_A", ...
        self._calibrating: set[str] = set()

    def _key(self, innings: int, over: int) -> str:
        end = "A" if over % 2 == 0 else "B"
        return f"{innings}_{end}"

    def get(self, innings: int, over: int) -> Optional[PitchBox]:
        """Return cached ROI for this bowling end, or None on cache miss."""
        return self._ends.get(self._key(innings, over))

    def put(self, innings: int, over: int, box: PitchBox) -> None:
        """Cache a freshly computed ROI for this bowling end."""
        key = self._key(innings, over)
        self._ends[key] = box
        self._calibrating.discard(key)
        log.info("  [ROI-CACHE] Stored %s: stump_cx=%.3f", key, box.stump_x_norm)

    def needs_calibration(self, innings: int, over: int) -> bool:
        key = self._key(innings, over)
        return key not in self._ends

    def invalidate_innings(self, innings: int) -> None:
        """Clear cache for a specific innings (call on innings change)."""
        to_remove = [k for k in self._ends if k.startswith(f"{innings}_")]
        for k in to_remove:
            del self._ends[k]
        if to_remove:
            log.info("  [ROI-CACHE] Invalidated innings %d: %s", innings, to_remove)

    def clear(self) -> None:
        """Clear all cached ROIs (call on pipeline stop)."""
        if self._ends:
            log.info("  [ROI-CACHE] Cleared %d cached ends", len(self._ends))
        self._ends.clear()
        self._calibrating.clear()

    @property
    def cached_ends(self) -> list[str]:
        return list(self._ends.keys())


# ── Model singleton ────────────────────────────────────────────────
_mlx_model = None
_model_unavailable = False


def _get_model():
    """Lazy-load Moondream 3 int4 via the MLX backend."""
    global _mlx_model, _model_unavailable
    if _model_unavailable:
        return None
    if _mlx_model is not None:
        return _mlx_model
    try:
        if _MLX_BACKEND_DIR not in sys.path:
            sys.path.insert(0, _MLX_BACKEND_DIR)
        import backend as mlx_backend
        mlx_backend.init_backend(quantize="int4")
        _mlx_model = mlx_backend._get_model()
        log.info("MLX Moondream model loaded (int4)")
        return _mlx_model
    except Exception as e:
        log.warning("Failed to load MLX Moondream model: %s", e)
        _model_unavailable = True
        return None


def check_station_available() -> bool:
    """Quick check — can we load the MLX model?"""
    return _get_model() is not None


# ── Image helpers ──────────────────────────────────────────────────

def _bgr_to_pil(bgr: np.ndarray, max_width: int = _RESIZE_WIDTH):
    """Convert BGR frame to PIL Image at a fixed shape for MLX cache reuse.

    When ``_PIN_INPUT_SHAPE`` is True (default), the image is resized to
    a fixed ``_PINNED_SIDE`` x ``_PINNED_SIDE`` square regardless of input
    aspect ratio.  This costs ~5 % geometric distortion but keeps the
    Metal shader graph cached across calls.  Without pinning, MLX would
    recompile per-call for every distinct (H, W) it sees, adding 1.5-2 s.
    """
    from PIL import Image
    if _PIN_INPUT_SHAPE:
        bgr = cv2.resize(bgr, (_PINNED_SIDE, _PINNED_SIDE),
                          interpolation=cv2.INTER_AREA)
    else:
        h, w = bgr.shape[:2]
        if w > max_width:
            scale = max_width / w
            bgr = cv2.resize(bgr, (max_width, int(h * scale)),
                              interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


# ── Cheap local filters (sub-ms) ───────────────────────────────────

def has_center_strip(frame: np.ndarray, center_width: float = 0.20,
                     min_non_green_pct: float = 0.30) -> bool:
    """Does the frame have a non-green vertical strip in the centre?

    A delivery view has the pitch strip (non-green) running down the
    centre of the frame.  Field-chase shots and wide outfield views
    have green throughout the centre.  ~1 ms per frame.
    """
    h, w = frame.shape[:2]
    cx1 = int(w * (0.5 - center_width / 2))
    cx2 = int(w * (0.5 + center_width / 2))
    center_band = frame[:, cx1:cx2]
    hsv = cv2.cvtColor(center_band, cv2.COLOR_BGR2HSV)
    green_mask = cv2.inRange(hsv, (35, 40, 40), (85, 255, 255))
    non_green_rows = (green_mask.mean(axis=1) < 128).sum()
    return non_green_rows > h * min_non_green_pct


def _find_contiguous_blocks(
    timestamps: list[float],
    gap_s: float = 0.3,
) -> list[list[int]]:
    """Group frame indices into contiguous blocks (gap < gap_s)."""
    if not timestamps:
        return []
    blocks: list[list[int]] = [[0]]
    for i in range(1, len(timestamps)):
        if timestamps[i] - timestamps[i - 1] < gap_s:
            blocks[-1].append(i)
        else:
            blocks.append([i])
    return blocks


def _pick_candidates_from_block(
    block_indices: list[int],
    n: int = 5,
) -> list[int]:
    """Pick n frames from the middle of a block."""
    mid = len(block_indices) // 2
    half = n // 2
    start = max(0, mid - half)
    end = min(len(block_indices), start + n)
    start = max(0, end - n)
    return block_indices[start:end]


# ── Stump validation & ROI computation ─────────────────────────────

def _validate_stump_box(
    x_min: float, y_min: float, x_max: float, y_max: float,
) -> bool:
    """Return True if the normalised box looks like real stumps."""
    bw = x_max - x_min
    bh = y_max - y_min
    area = bw * bh
    cx = (x_min + x_max) / 2

    if area > _MAX_STUMP_AREA:
        return False
    if bw > _MAX_STUMP_WIDTH:
        return False
    if bh > _MAX_STUMP_HEIGHT or bh < _MIN_STUMP_HEIGHT:
        return False
    if cx < _STUMP_CENTER_X_LO or cx > _STUMP_CENTER_X_HI:
        return False
    return True


def _stump_to_pitch_roi(
    x_min: float, y_min: float, x_max: float, y_max: float,
    frame_w: int, frame_h: int,
    moondream_ms: float = 0.0,
) -> PitchBox:
    """Compute a generous pitch ROI from the stump bounding box.

    Moondream may return either batting-end or bowling-end stumps
    (inconsistent across broadcasters).  However stump centre-x is
    a reliable horizontal anchor because both sets of stumps sit on
    the same vertical axis (the pitch centre-line).

    The ROI is deliberately generous: it should contain the full ball
    trajectory from bowler release to batsman contact, including wide
    deliveries and bouncers.  Eliminating crowd, boundary, ads, and
    scoreboard is the goal — not pixel-tight pitch extraction.
    """
    stump_cx = (x_min + x_max) / 2
    stump_cy = (y_min + y_max) / 2

    # Horizontal: 45 % of frame width, centred on stump cx.
    # The pitch is ~10 ft wide; a ball bowled wide of off stump can be
    # another foot outside.  On angled views the far end shifts left/right
    # relative to the near end; 45 % covers this comfortably.
    roi_w_norm = 0.45
    roi_x_min = max(0.0, stump_cx - roi_w_norm / 2)
    roi_x_max = min(1.0, roi_x_min + roi_w_norm)
    roi_x_min = max(0.0, roi_x_max - roi_w_norm)

    # Vertical: cover the full pitch area regardless of which end's
    # stumps were detected.  Top 10 % is usually sponsor board / sky;
    # bottom 15 % is usually scoreboard / UI chrome.
    roi_y_min = 0.08
    roi_y_max = 0.85

    px = int(roi_x_min * frame_w)
    py = int(roi_y_min * frame_h)
    pw = int((roi_x_max - roi_x_min) * frame_w)
    ph = int((roi_y_max - roi_y_min) * frame_h)

    return PitchBox(
        x=px, y=py, w=pw, h=ph,
        moondream_ms=moondream_ms,
        stump_x_norm=stump_cx,
        stump_y_norm=stump_cy,
    )


# ── Single-frame detection ─────────────────────────────────────────

def detect_pitch_in_frame(
    bgr: np.ndarray,
    model=None,
) -> Optional[PitchBox]:
    """Run Moondream detect('stumps') on one frame.

    Returns a PitchBox (pitch ROI derived from stumps) or None.
    """
    if model is None:
        model = _get_model()
    if model is None:
        return None

    h, w = bgr.shape[:2]
    pil_img = _bgr_to_pil(bgr)

    global _model_unavailable
    t0 = time.time()
    try:
        result = model.detect(pil_img, DETECT_PROMPT)
    except Exception as e:
        log.warning("Moondream detect failed: %s", e)
        return None
    ms = (time.time() - t0) * 1000
    log.info("[GROUNDER] detect cost %.0fms (input %dx%d, pin=%s)",
             ms, pil_img.width, pil_img.height, _PIN_INPUT_SHAPE)

    objects = result.get("objects", [])
    if not objects:
        return None

    obj = objects[0]
    xn, yn, xx, yx = (
        obj.get("x_min", 0), obj.get("y_min", 0),
        obj.get("x_max", 0), obj.get("y_max", 0),
    )

    if not _validate_stump_box(xn, yn, xx, yx):
        log.debug("Stump box rejected: [%.3f,%.3f]-[%.3f,%.3f]", xn, yn, xx, yx)
        return None

    return _stump_to_pitch_roi(xn, yn, xx, yx, w, h, moondream_ms=ms)


def warmup(dummy_size: tuple[int, int] | None = None) -> bool:
    """Warm Moondream by running 2 detect() calls on a dummy frame.

    First-call overhead on MLX is significant — the Metal kernels are
    JIT-compiled and weights are paged in.  Without warmup the first 2-3
    real deliveries pay 5-10s/call instead of the steady-state 1.25s.
    Two dummy calls (compile + cache) gets us to steady state before any
    real delivery arrives.

    The dummy frame is sized to match the production frame source.  When
    ``_PIN_INPUT_SHAPE`` is True the dummy size is irrelevant because
    every real call also gets resized to ``_PINNED_SIDE`` square — what
    matters is that warmup goes through the exact same _bgr_to_pil path
    so the cached kernel matches what production uses.

    Returns True if warmup completed, False if Moondream is unavailable.
    """
    model = _get_model()
    if model is None:
        log.warning("[WARMUP] Moondream unavailable — skipping warmup")
        return False
    if dummy_size is None:
        # 16:9 so the resize path matches what real broadcast frames hit
        dummy_size = (540, 960)
    h, w = dummy_size
    # noisy random frame so detect() actually exercises the full pipeline
    rng = np.random.default_rng(42)
    dummy = rng.integers(0, 255, (h, w, 3), dtype=np.uint8)
    log.info("[WARMUP] Warming Moondream (2 dummy calls; src=%dx%d → "
             "%dx%d after pin=%s) …",
             w, h, _PINNED_SIDE if _PIN_INPUT_SHAPE else _RESIZE_WIDTH,
             _PINNED_SIDE if _PIN_INPUT_SHAPE else int(h * _RESIZE_WIDTH / w),
             _PIN_INPUT_SHAPE)
    t0 = time.time()
    for i in range(2):
        c0 = time.time()
        try:
            detect_pitch_in_frame(dummy, model=model)
        except Exception as e:
            log.warning("[WARMUP] call %d failed: %s", i + 1, e)
            return False
        log.info("[WARMUP] call %d: %.0fms", i + 1, (time.time() - c0) * 1000)
    log.info("[WARMUP] Done in %.1fs — Moondream is hot",
             time.time() - t0)
    return True


# ── Batch grounding (narrow → VLM) ─────────────────────────────────

def narrow_to_delivery_block(
    frames: list[tuple[float, np.ndarray]],
    is_wide_fn=None,
) -> list[tuple[float, np.ndarray]]:
    """Apply cheap pre-VLM narrowing filters to find delivery frames.

    Runs is_wide_shot, has_center_strip, and temporal clustering with
    minimum block duration — everything EXCEPT the expensive Moondream
    VLM calls.  Returns all frames from the best delivery block, or []
    if no qualifying block is found.

    Used on the ROI cache-hit path where the pitch box is already known
    but we still need to reject non-bowler's-end camera angles.
    """
    if not frames:
        return []

    # ── Filter 1: is_wide_shot ──────────────────────────────
    if is_wide_fn is not None:
        wide = [(i, ts, bgr) for i, (ts, bgr) in enumerate(frames)
                if is_wide_fn(bgr)]
    else:
        wide = [(i, ts, bgr) for i, (ts, bgr) in enumerate(frames)]
    log.info("  [NARROW] Filter1 (wide_shot): %d / %d pass",
             len(wide), len(frames))

    # ── Filter 2: has_center_strip ──────────────────────────
    stripped = [(i, ts, bgr) for i, ts, bgr in wide
                if has_center_strip(bgr)]
    log.info("  [NARROW] Filter2 (center_strip): %d / %d pass",
             len(stripped), len(wide))

    if not stripped:
        log.info("  [NARROW] No frames pass both filters")
        return []

    # ── Filter 3: temporal clustering ───────────────────────
    timestamps = [ts for _, ts, _ in stripped]
    blocks = _find_contiguous_blocks(timestamps, gap_s=0.5)

    block_sizes = [(len(b), -timestamps[b[0]], bi)
                   for bi, b in enumerate(blocks)]
    block_sizes.sort(reverse=True)

    block_durations = [timestamps[b[-1]] - timestamps[b[0]]
                       for b in blocks]
    log.info("  [NARROW] Found %d temporal blocks, sizes: %s, "
             "durations: %s",
             len(blocks),
             [len(b) for b in blocks][:5],
             ["%.1fs" % d for d in block_durations][:5])

    main_block_idx = block_sizes[0][2]
    main_block = blocks[main_block_idx]

    MIN_BLOCK_DURATION_S = 1.5
    block_duration = timestamps[main_block[-1]] - timestamps[main_block[0]]
    if block_duration < MIN_BLOCK_DURATION_S:
        log.info("  [NARROW] Largest block too short (%.1fs < %.1fs) "
                 "— no bowler's-end camera hold found",
                 block_duration, MIN_BLOCK_DURATION_S)
        return []

    ts_lo = timestamps[main_block[0]]
    ts_hi = timestamps[main_block[-1]]
    log.info("  [NARROW] Selected block: %d frames in [%.1f, %.1f]s "
             "(%.1fs)",
             len(main_block), ts_lo, ts_hi, block_duration)

    return [(ts, bgr) for _, ts, bgr in
            (stripped[j] for j in main_block)]


def ground_pitch_in_frames(
    frames: list[tuple[float, np.ndarray]],
    max_vlm_calls: int = 3,
    is_wide_fn=None,
) -> list[tuple[float, np.ndarray, PitchBox]]:
    """Narrow-then-confirm pipeline for delivery frame detection.

    1. Filter 1: is_wide_shot  (~0.1 ms/frame) — eliminate non-field frames.
    2. Filter 2: has_center_strip (~1 ms/frame) — keep frames with non-green
       centre (pitch strip).
    3. Temporal clustering — find the largest contiguous block (= the delivery
       camera hold).  Prefer the earliest block (live delivery, not replays).
    4. Pick middle ``max_vlm_calls`` frames from that block.
    5. VLM: detect stumps on those candidates (~1.25 s each).

    Args:
        frames: list of (timestamp, bgr_frame) tuples from the rolling buffer.
        max_vlm_calls: max frames to spend VLM calls on (default 3).
            With 86% per-frame hit rate on delivery views,
            P(>=1 hit in 3) = 99.7%.  Falls back to 2 more if needed.
        is_wide_fn: optional callable(bgr) → bool for wide-shot filtering.
            If None, ``has_center_strip`` alone is used.
    """
    if not frames:
        return []

    # When VLM grounding is disabled, return all frames with a static ROI
    # centred at 50% horizontally, 8-85% vertically.
    if not USE_VLM_GROUNDING:
        log.info("  [NARROW] VLM grounding disabled, using static ROI")
        results = []
        for ts, bgr in frames:
            h, w = bgr.shape[:2]
            static_box = PitchBox(
                x=int(w * 0.275), y=int(h * 0.08),
                w=int(w * 0.45), h=int(h * 0.77),
                stump_x_norm=0.50, stump_y_norm=0.50,
            )
            results.append((ts, bgr, static_box))
        return results

    # ── Pre-VLM narrowing (shared with cache-hit path) ──────
    # Run the same filters, then pick VLM candidates from the block.
    if is_wide_fn is not None:
        wide = [(i, ts, bgr) for i, (ts, bgr) in enumerate(frames)
                if is_wide_fn(bgr)]
    else:
        wide = [(i, ts, bgr) for i, (ts, bgr) in enumerate(frames)]
    log.info("  [NARROW] Filter1 (wide_shot): %d / %d pass",
             len(wide), len(frames))

    stripped = [(i, ts, bgr) for i, ts, bgr in wide
                if has_center_strip(bgr)]
    log.info("  [NARROW] Filter2 (center_strip): %d / %d pass",
             len(stripped), len(wide))

    if not stripped:
        log.info("  [NARROW] No frames pass both filters")
        return []

    timestamps = [ts for _, ts, _ in stripped]
    blocks = _find_contiguous_blocks(timestamps, gap_s=0.5)

    block_sizes = [(len(b), -timestamps[b[0]], bi)
                   for bi, b in enumerate(blocks)]
    block_sizes.sort(reverse=True)

    block_durations = [timestamps[b[-1]] - timestamps[b[0]]
                       for b in blocks]
    log.info("  [NARROW] Found %d temporal blocks, sizes: %s, "
             "durations: %s",
             len(blocks),
             [len(b) for b in blocks][:5],
             ["%.1fs" % d for d in block_durations][:5])

    main_block_idx = block_sizes[0][2]
    main_block = blocks[main_block_idx]

    MIN_BLOCK_DURATION_S = 1.5
    block_duration = timestamps[main_block[-1]] - timestamps[main_block[0]]
    if block_duration < MIN_BLOCK_DURATION_S:
        log.info("  [NARROW] Largest block too short (%.1fs < %.1fs) "
                 "— no bowler's-end camera hold found",
                 block_duration, MIN_BLOCK_DURATION_S)
        return []

    candidate_indices = _pick_candidates_from_block(main_block, n=max_vlm_calls)
    candidates = [stripped[j] for j in candidate_indices]

    ts_lo = timestamps[main_block[0]]
    ts_hi = timestamps[main_block[-1]]
    log.info("  [NARROW] Selected block: %d frames in [%.1f, %.1f]s "
             "(%.1fs), picking %d candidates for VLM",
             len(main_block), ts_lo, ts_hi, block_duration,
             len(candidates))

    # ── VLM pass: detect stumps ─────────────────────────────
    model = _get_model()
    if model is None:
        log.warning("  [NARROW] Moondream unavailable — returning block "
                     "frames without VLM confirmation")
        return [(ts, bgr, PitchBox(x=0, y=0, w=bgr.shape[1], h=bgr.shape[0]))
                for _, ts, bgr in candidates]

    total_ms = 0.0
    vlm_calls = 0
    results: list[tuple[float, np.ndarray, PitchBox]] = []

    def _detect_one(item):
        orig_idx, ts, bgr = item
        return orig_idx, ts, bgr, detect_pitch_in_frame(bgr, model=model)

    pool = _get_pool()
    wall0 = time.time()
    if pool is None:
        outcomes = [_detect_one(c) for c in candidates]
    else:
        outcomes = list(pool.map(_detect_one, candidates))
    wall_ms = (time.time() - wall0) * 1000.0

    for orig_idx, ts, bgr, box in outcomes:
        vlm_calls += 1
        if box:
            total_ms += box.moondream_ms
            results.append((ts, bgr, box))
            log.info("  [NARROW] VLM[%d] t=%.1f → "
                     "stumps=(%0.2f,%0.2f) %0.0fms",
                     orig_idx, ts, box.stump_x_norm, box.stump_y_norm,
                     box.moondream_ms)
        else:
            log.info("  [NARROW] VLM[%d] t=%.1f → no stumps detected",
                     orig_idx, ts)

    if pool is not None and vlm_calls > 0:
        log.info("  [NARROW] PARALLEL pool=%d wall=%.0fms "
                 "serial_sum=%.0fms speedup=%.2fx",
                 _GROUND_PARALLEL_WORKERS, wall_ms, total_ms,
                 (total_ms / wall_ms) if wall_ms > 0 else 0.0)

    # Fallback: if primary VLM calls found nothing, try a few more from the
    # same block before giving up.  With 3 primary + 2 fallback = 5 total max.
    _FALLBACK_EXTRA = 2
    if not results and len(main_block) > max_vlm_calls:
        fallback = [stripped[j] for j in main_block
                    if j not in set(candidate_indices)][:_FALLBACK_EXTRA]
        log.info("  [NARROW] Primary VLM found nothing, trying %d fallback",
                 len(fallback))
        if pool is None:
            fb_outcomes = [_detect_one(c) for c in fallback]
        else:
            fb_outcomes = list(pool.map(_detect_one, fallback))
        for _orig_idx, ts, bgr, box in fb_outcomes:
            vlm_calls += 1
            if box:
                total_ms += box.moondream_ms
                results.append((ts, bgr, box))

    results.sort(key=lambda x: x[0])

    # Smooth with median box
    if results:
        median_box = _median_box(results)
        for i, (ts, bgr, _) in enumerate(results):
            results[i] = (ts, bgr, median_box)

    # Also include the surrounding frames from the block (they're delivery
    # views even if VLM didn't run on them) using the median box.
    if results:
        confirmed_ts = {r[0] for r in results}
        for j in main_block:
            _, ts, bgr = stripped[j]
            if ts not in confirmed_ts:
                results.append((ts, bgr, median_box))
        results.sort(key=lambda x: x[0])

    avg_ms = total_ms / max(vlm_calls, 1)
    log.info("  [NARROW] Done: %d delivery frames, %d VLM calls "
             "(avg %.0fms, total %.0fms)",
             len(results), vlm_calls, avg_ms, total_ms)

    return results


def _median_box(
    results: list[tuple[float, np.ndarray, PitchBox]],
) -> PitchBox:
    """Compute the median PitchBox to smooth jitter."""
    xs = [r[2].x for r in results]
    ys = [r[2].y for r in results]
    ws = [r[2].w for r in results]
    hs = [r[2].h for r in results]
    sx = [r[2].stump_x_norm for r in results]
    sy = [r[2].stump_y_norm for r in results]

    return PitchBox(
        x=int(np.median(xs)),
        y=int(np.median(ys)),
        w=int(np.median(ws)),
        h=int(np.median(hs)),
        stump_x_norm=float(np.median(sx)),
        stump_y_norm=float(np.median(sy)),
    )
