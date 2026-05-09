"""Stage-1 streaming motion-signal filter (Component 2).

Consumes broadcast frames in real time and emits callbacks when the
feed enters or leaves an "active broadcast candidate window" — a
period during which Stage 2 (DeliverySpanSelector) is allowed to
dispatch Scout.

**Architectural role (2026-05-03)**: Stage 1 is the **ad-suppression
filter**. It does *not* attempt to separate replays from live play
— per-frame motion signal fundamentally cannot do that because a
replay angle IS cricket content. Replay handling lives in Stage 2
via Scout's ``[BROADCAST: REPLAY]`` classification and
``SpanAggregator``'s hard-close logic. See
``files/docs/investigations/broadcast_mode_filter_tuning.md`` §10
for the decision record.

Signals (per frame-pair, on grayscale):

* ``flow_magnitude`` — mean pixelwise optical-flow magnitude
  (``cv2.calcOpticalFlowFarneback``). Computed on a frame downsampled
  to fit within ``(640, 360)`` for perf — flow is the dominant cost.
* ``strip_diff``    — mean ``absdiff`` over the bottom ``strip_roi_
  fraction`` of the **full-resolution** grayscale frame. Low values
  indicate a stable score strip (live broadcast); high values
  indicate overlays / transitions (ad, replay, graphic).
* ``frame_diff``    — mean ``absdiff`` over the full-resolution
  grayscale frame. Kept for ``stats()`` diagnostics only; not used
  by the state machine.

Sliding window (``window_s`` seconds) aggregates:

* ``strip_mean``      — mean of ``strip_diff`` samples in window.
* ``flow_peak_count`` — count of ``flow_magnitude`` samples in the
  window above ``median(flow) + std(flow)`` (same definition as in
  ``files/scripts/motion_baseline/compute_motion_signals.py``).

Hysteresis state machine with min-duration debounce — see
``BroadcastModeFilter`` docstring for the precise transition rules.

API mirrors ``DeliverySpanSelector``: caller pumps frames via
``add_frame()`` and is notified of transitions through the
``on_window_open`` / ``on_window_close`` callbacks. ``current_state()``
exposes a synchronous poll for the Stage-2 dispatch gate.

This module is pure computation (no I/O, no threads, no globals) so
it can be unit-tested headlessly and replayed from pre-computed
signal traces. See ``files/tests/test_broadcast_mode_filter.py``.
"""
from __future__ import annotations

import atexit
import collections
import json
import logging
import math
import os
from pathlib import Path
from typing import Callable, Deque, Dict, Optional, Tuple

import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

log = logging.getLogger("broadcast_mode_filter")

STATE_INACTIVE = "inactive"
STATE_ACTIVE = "active"

_DEFAULT_DEBUG_PATH = "files/logs/bmf_debug/bmf_{session_id}.jsonl"
_BMF_DEBUG_OPEN_FILES: list = []
_BMF_DEBUG_ATEXIT_REGISTERED = False

# Batch T (2026-05-04): strip ROI is now a (top, bot) Y-band so it can
# land ABOVE the always-on score overlay rather than measuring the
# overlay itself. The bottom-12% legacy default measured ON the score
# strip, which on capture-card feeds animates every frame and pinned
# strip_diff baseline at ~35× the offline corpus median (memo §13
# Phase D). Default band 0.78–0.88 sits in the lower-pitch / ad-band
# region: mostly grass during live play, ad/transition pixels during
# breaks.
_DEFAULT_STRIP_ROI_TOP_FRACTION = 0.78
_DEFAULT_STRIP_ROI_BOT_FRACTION = 0.88


def _bmf_debug_atexit() -> None:
    while _BMF_DEBUG_OPEN_FILES:
        fh = _BMF_DEBUG_OPEN_FILES.pop()
        try:
            fh.close()
        except Exception:
            pass

MAX_DIM_DEFAULT: Tuple[int, int] = (640, 360)

_FARNEBACK_KWARGS = dict(
    pyr_scale=0.5, levels=3, winsize=15, iterations=3,
    poly_n=5, poly_sigma=1.2, flags=0,
)


def _resolve_strip_band(
    strip_roi_fraction: Optional[float],
    strip_roi_top_fraction: Optional[float],
    strip_roi_bot_fraction: Optional[float],
) -> Tuple[float, float]:
    """Resolve the (top, bot) strip-ROI band from the available inputs.

    Precedence:
      1. Explicit ``strip_roi_top_fraction`` / ``strip_roi_bot_fraction``
         (either or both; missing side falls back to its default).
      2. Legacy ``strip_roi_fraction`` (deprecated): preserved as
         ``top = 1.0 - fraction, bot = 1.0`` so existing call sites
         retain bottom-fraction behavior.
      3. Env vars ``BMF_STRIP_ROI_TOP`` / ``BMF_STRIP_ROI_BOT``.
      4. Module defaults.
    """
    if (strip_roi_top_fraction is not None
            or strip_roi_bot_fraction is not None):
        top = (float(strip_roi_top_fraction)
               if strip_roi_top_fraction is not None
               else _DEFAULT_STRIP_ROI_TOP_FRACTION)
        bot = (float(strip_roi_bot_fraction)
               if strip_roi_bot_fraction is not None
               else _DEFAULT_STRIP_ROI_BOT_FRACTION)
    elif strip_roi_fraction is not None:
        top = 1.0 - float(strip_roi_fraction)
        bot = 1.0
    else:
        top_env = os.environ.get("BMF_STRIP_ROI_TOP")
        bot_env = os.environ.get("BMF_STRIP_ROI_BOT")
        top = (float(top_env) if top_env is not None
               else _DEFAULT_STRIP_ROI_TOP_FRACTION)
        bot = (float(bot_env) if bot_env is not None
               else _DEFAULT_STRIP_ROI_BOT_FRACTION)
    if not (0.0 <= top < bot <= 1.0):
        raise ValueError(
            f"strip ROI band invalid: top={top}, bot={bot}; "
            "expected 0.0 <= top < bot <= 1.0")
    return top, bot


def _downsample_if_larger(gray: np.ndarray,
                          max_dim: Tuple[int, int] = MAX_DIM_DEFAULT
                          ) -> np.ndarray:
    """Resize ``gray`` so neither dimension exceeds ``max_dim``."""
    h, w = gray.shape[:2]
    if w <= max_dim[0] and h <= max_dim[1]:
        return gray
    scale = min(max_dim[0] / w, max_dim[1] / h)
    new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
    return cv2.resize(gray, (new_w, new_h))


def compute_frame_signals(
    prev_gray: np.ndarray,
    cur_gray: np.ndarray,
    *,
    strip_roi_fraction: Optional[float] = None,
    strip_roi_top_fraction: Optional[float] = None,
    strip_roi_bot_fraction: Optional[float] = None,
    max_dim: Tuple[int, int] = MAX_DIM_DEFAULT,
) -> Dict[str, float]:
    """Compute (flow_magnitude, frame_diff, strip_diff) for a
    consecutive grayscale pair.

    Both inputs must be the same shape and 2-D ``uint8``.

    All three signals are computed on the same downsampled grayscale
    pair (≤``max_dim``). The reference baseline in
    ``files/scripts/motion_baseline/compute_motion_signals.py`` also
    downsamples first, so filter signals remain comparable to the
    tuning JSONLs under ``files/scripts/motion_baseline/raw/``. Tasks
    that need full-resolution ``frame_diff`` / ``strip_diff`` should
    not go through this helper.
    """
    if not HAS_CV2:
        raise RuntimeError("opencv-python is required for BroadcastModeFilter")
    if prev_gray.shape != cur_gray.shape:
        raise ValueError(
            f"shape mismatch: prev={prev_gray.shape} cur={cur_gray.shape}")

    prev_small = _downsample_if_larger(prev_gray, max_dim)
    cur_small = _downsample_if_larger(cur_gray, max_dim)

    flow = cv2.calcOpticalFlowFarneback(
        prev_small, cur_small, None, **_FARNEBACK_KWARGS)
    mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
    flow_magnitude = float(mag.mean())

    diff_small = cv2.absdiff(prev_small, cur_small)
    frame_diff = float(diff_small.mean())

    top_frac, bot_frac = _resolve_strip_band(
        strip_roi_fraction,
        strip_roi_top_fraction,
        strip_roi_bot_fraction,
    )
    sh_s = cur_small.shape[0]
    strip_y_top = int(sh_s * top_frac)
    strip_y_bot = int(sh_s * bot_frac)
    if strip_y_bot <= strip_y_top:
        strip_y_bot = strip_y_top + 1
    strip_diff = float(diff_small[strip_y_top:strip_y_bot, :].mean())

    return {
        "flow_magnitude": flow_magnitude,
        "frame_diff": frame_diff,
        "strip_diff": strip_diff,
    }


class BroadcastModeFilter:
    """Streaming motion-signal filter with hysteresis + debounce.

    Caller pumps frames via ``add_frame(ts, frame_bgr)``. The filter
    derives ``(flow_magnitude, strip_diff)`` per pair, buffers the
    last ``window_s`` seconds, and runs the hysteresis rule:

    ``INACTIVE → ACTIVE``
        ``window_strip_mean ≤ open_strip_mean_max`` **and**
        ``window_flow_peak_count ≥ open_flow_peak_min``, held
        continuously for at least ``min_active_s``.

    ``ACTIVE → INACTIVE``
        ``window_strip_mean > close_strip_mean_max`` **or**
        ``window_flow_peak_count < close_flow_peak_min``, held
        continuously for at least ``min_inactive_s``.

    The open/close threshold pairs form the hysteresis band: the
    close thresholds are strictly looser than the open thresholds so
    a brief dip below / spike above the open band does not cause an
    immediate re-transition.

    Transition timestamps fed to the callbacks are the ``ts`` of the
    frame that completed the debounce (i.e. the first frame after
    the condition has held for the full min-duration window). The
    filter is single-threaded: ``add_frame`` and the callbacks run
    on the caller's thread.

    For replay / tuning without OpenCV work, ``ingest_signals(ts,
    flow_magnitude, strip_diff)`` bypasses the per-frame compute and
    feeds signals directly.
    """

    def __init__(
        self,
        on_window_open: Callable[[float], None],
        on_window_close: Callable[[float], None],
        *,
        # Production defaults are the v1 sweep optimum
        # (``score = rd × (1 − ad)``) at the broad grid: rd=69%,
        # ad=0%, replay=71%. See tuning memo §9-§10 at
        # ``files/docs/investigations/broadcast_mode_filter_tuning.md``.
        #
        # Stage 1's role is **ad suppression**, not replay
        # suppression. The v2 replay-aware re-tune achieved 12×
        # replay suppression but dropped 10% of real_delivery clips
        # to zero ACTIVE and 24% below the 5 s span-formation floor
        # — per-frame motion signal cannot separate slow-motion
        # replay from live cricket play because a replay angle IS
        # cricket content. Replay handling is Stage 2
        # (``DeliverySpanSelector``) via Scout's
        # ``[BROADCAST: REPLAY]`` class + SpanAggregator hard-close.
        #
        # Reproduce: ``tune_thresholds.py --broad --score v1``.
        # Timing params (window_s, min_*_s) preserved from v2
        # because they are score-agnostic.
        window_s: float = 10.0,
        open_strip_mean_max: float = 0.35,
        open_flow_peak_min: int = 10,
        close_strip_mean_max: float = 0.475,
        close_flow_peak_min: int = 5,
        min_active_s: float = 1.5,
        min_inactive_s: float = 3.0,
        strip_roi_fraction: Optional[float] = None,
        strip_roi_top_fraction: Optional[float] = None,
        strip_roi_bot_fraction: Optional[float] = None,
        max_flow_dim: Tuple[int, int] = MAX_DIM_DEFAULT,
    ):
        if window_s <= 0:
            raise ValueError("window_s must be > 0")
        strip_roi_top, strip_roi_bot = _resolve_strip_band(
            strip_roi_fraction,
            strip_roi_top_fraction,
            strip_roi_bot_fraction,
        )
        if close_strip_mean_max < open_strip_mean_max:
            raise ValueError(
                "close_strip_mean_max must be ≥ open_strip_mean_max "
                "(hysteresis band)")
        if close_flow_peak_min > open_flow_peak_min:
            raise ValueError(
                "close_flow_peak_min must be ≤ open_flow_peak_min "
                "(hysteresis band)")

        self._on_open = on_window_open
        self._on_close = on_window_close
        self._window_s = float(window_s)
        self._open_strip = float(open_strip_mean_max)
        self._open_flow = int(open_flow_peak_min)
        self._close_strip = float(close_strip_mean_max)
        self._close_flow = int(close_flow_peak_min)
        self._min_active_s = float(min_active_s)
        self._min_inactive_s = float(min_inactive_s)
        self._strip_roi_top = strip_roi_top
        self._strip_roi_bot = strip_roi_bot
        self._max_flow_dim = max_flow_dim

        self._prev_gray: Optional[np.ndarray] = None
        # (ts, flow_magnitude, strip_diff)
        self._buf: Deque[Tuple[float, float, float]] = collections.deque()

        self._state: str = STATE_INACTIVE
        self._pending_state: Optional[str] = None
        self._pending_since_ts: Optional[float] = None
        self._last_transition_ts: Optional[float] = None
        self._last_ts: Optional[float] = None

        self._last_flow_mag: float = 0.0
        self._last_strip_diff: float = 0.0
        self._last_frame_diff: float = 0.0
        self._last_strip_mean: float = 0.0
        self._last_flow_peak_count: int = 0

        self._frames_ingested: int = 0
        self._signals_ingested: int = 0

        self._debug_enabled = (
            os.environ.get("BMF_DEBUG_TELEMETRY", "0") == "1")
        self._debug_path_template = os.environ.get(
            "BMF_DEBUG_PATH", _DEFAULT_DEBUG_PATH)
        self._debug_session_id = os.environ.get("BMF_SESSION_ID", "unknown")
        self._debug_fp = None
        self._debug_frame_idx: int = 0
        self._score_event_ts: Deque[float] = collections.deque(maxlen=64)

    # ── public API ───────────────────────────────────────────────

    def add_frame(self, ts: float, frame_bgr: np.ndarray) -> None:
        """Ingest a BGR frame at wall-clock ``ts`` (seconds)."""
        if not HAS_CV2:
            raise RuntimeError("opencv-python is required for add_frame")
        self._frames_ingested += 1
        if frame_bgr is None or frame_bgr.size == 0:
            return
        if frame_bgr.ndim == 2:
            gray = frame_bgr
        else:
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        if self._prev_gray is None or self._prev_gray.shape != gray.shape:
            self._prev_gray = gray
            return
        sig = compute_frame_signals(
            self._prev_gray, gray,
            strip_roi_top_fraction=self._strip_roi_top,
            strip_roi_bot_fraction=self._strip_roi_bot,
            max_dim=self._max_flow_dim,
        )
        self._prev_gray = gray
        self._last_frame_diff = sig["frame_diff"]
        self.ingest_signals(
            ts, sig["flow_magnitude"], sig["strip_diff"])

    def ingest_signals(
        self,
        ts: float,
        flow_magnitude: float,
        strip_diff: float,
    ) -> None:
        """Feed pre-computed per-frame signals (replay / tuning)."""
        self._signals_ingested += 1
        self._last_ts = ts
        self._last_flow_mag = float(flow_magnitude)
        self._last_strip_diff = float(strip_diff)
        self._buf.append((ts, float(flow_magnitude), float(strip_diff)))
        self._evict_stale(ts)
        self._evaluate(ts)
        if self._debug_enabled:
            self._emit_debug_row(
                ts, float(flow_magnitude), float(strip_diff))

    def mark_score_event(self, ts: float) -> None:
        """Record a pipeline score-commit timestamp for telemetry labeling.

        Used by the debug telemetry layer (``BMF_DEBUG_TELEMETRY=1``) to
        tag each emitted row with ``score_event_within_5s``, enabling
        downstream label inference for ``tune_thresholds.py``.
        """
        self._score_event_ts.append(float(ts))

    def current_state(self) -> str:
        return self._state

    def stats(self) -> Dict:
        return {
            "state": self._state,
            "pending_state": self._pending_state,
            "pending_since_ts": self._pending_since_ts,
            "last_transition_ts": self._last_transition_ts,
            "last_ts": self._last_ts,
            "buffer_samples": len(self._buf),
            "window_span_s": (
                (self._buf[-1][0] - self._buf[0][0]) if self._buf else 0.0),
            "last_flow_magnitude": self._last_flow_mag,
            "last_strip_diff": self._last_strip_diff,
            "last_frame_diff": self._last_frame_diff,
            "window_strip_mean": self._last_strip_mean,
            "window_flow_peak_count": self._last_flow_peak_count,
            "frames_ingested": self._frames_ingested,
            "signals_ingested": self._signals_ingested,
            "params": {
                "window_s": self._window_s,
                "open_strip_mean_max": self._open_strip,
                "open_flow_peak_min": self._open_flow,
                "close_strip_mean_max": self._close_strip,
                "close_flow_peak_min": self._close_flow,
                "min_active_s": self._min_active_s,
                "min_inactive_s": self._min_inactive_s,
                "strip_roi_top_fraction": self._strip_roi_top,
                "strip_roi_bot_fraction": self._strip_roi_bot,
            },
        }

    def reset(self) -> None:
        """Clear buffers and return to INACTIVE (no callback fired)."""
        self._prev_gray = None
        self._buf.clear()
        self._state = STATE_INACTIVE
        self._pending_state = None
        self._pending_since_ts = None
        self._last_transition_ts = None
        self._last_ts = None
        self._last_flow_mag = 0.0
        self._last_strip_diff = 0.0
        self._last_frame_diff = 0.0
        self._last_strip_mean = 0.0
        self._last_flow_peak_count = 0

    # ── internals ─────────────────────────────────────────────────

    def _score_event_recent(
            self, ts: float, window_s: float = 5.0) -> bool:
        cutoff = ts - window_s
        return any(t >= cutoff for t in self._score_event_ts)

    def _emit_debug_row(
            self,
            ts: float,
            flow_magnitude: float,
            strip_diff: float,
    ) -> None:
        global _BMF_DEBUG_ATEXIT_REGISTERED
        if self._debug_fp is None:
            resolved = self._debug_path_template.replace(
                "{session_id}", self._debug_session_id)
            path = Path(resolved)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                self._debug_fp = open(path, "a", buffering=1)
            except Exception:
                log.exception("[bmf] debug telemetry open failed: %s", path)
                self._debug_enabled = False
                return
            _BMF_DEBUG_OPEN_FILES.append(self._debug_fp)
            if not _BMF_DEBUG_ATEXIT_REGISTERED:
                atexit.register(_bmf_debug_atexit)
                _BMF_DEBUG_ATEXIT_REGISTERED = True
        row = {
            "frame_idx": self._debug_frame_idx,
            "ts_s": ts,
            "flow_magnitude": flow_magnitude,
            "strip_diff": strip_diff,
            "bmf_state": self._state,
            "score_event_within_5s": self._score_event_recent(ts),
            "strip_roi_top": self._strip_roi_top,
            "strip_roi_bot": self._strip_roi_bot,
        }
        try:
            self._debug_fp.write(json.dumps(row) + "\n")
        except Exception:
            log.exception("[bmf] debug telemetry write failed")
            self._debug_enabled = False
            return
        self._debug_frame_idx += 1

    def _evict_stale(self, now_ts: float) -> None:
        cutoff = now_ts - self._window_s
        while self._buf and self._buf[0][0] < cutoff:
            self._buf.popleft()

    def _window_aggregates(self) -> Tuple[float, int]:
        if not self._buf:
            return 0.0, 0
        flows = np.fromiter((s[1] for s in self._buf),
                            dtype=np.float64, count=len(self._buf))
        strips = np.fromiter((s[2] for s in self._buf),
                             dtype=np.float64, count=len(self._buf))
        strip_mean = float(strips.mean())
        if flows.size < 3:
            peak_count = 0
        else:
            thr = float(np.median(flows) + np.std(flows))
            peak_count = int(np.sum(flows > thr))
        return strip_mean, peak_count

    def _evaluate(self, ts: float) -> None:
        strip_mean, peak_count = self._window_aggregates()
        self._last_strip_mean = strip_mean
        self._last_flow_peak_count = peak_count

        if self._state == STATE_INACTIVE:
            active_cond = (
                strip_mean <= self._open_strip
                and peak_count >= self._open_flow)
            target = STATE_ACTIVE if active_cond else STATE_INACTIVE
            debounce = self._min_active_s
        else:
            inactive_cond = (
                strip_mean > self._close_strip
                or peak_count < self._close_flow)
            target = STATE_INACTIVE if inactive_cond else STATE_ACTIVE
            debounce = self._min_inactive_s

        if target == self._state:
            self._pending_state = None
            self._pending_since_ts = None
            return

        if self._pending_state != target:
            self._pending_state = target
            self._pending_since_ts = ts
            return

        assert self._pending_since_ts is not None
        if ts - self._pending_since_ts < debounce:
            return

        prev_state = self._state
        self._state = target
        self._last_transition_ts = ts
        self._pending_state = None
        self._pending_since_ts = None
        log.debug(
            "[bmf] transition %s→%s ts=%.3f strip_mean=%.3f peak=%d",
            prev_state, target, ts, strip_mean, peak_count)
        try:
            if target == STATE_ACTIVE:
                self._on_open(ts)
            else:
                self._on_close(ts)
        except Exception:
            log.exception("[bmf] callback raised on %s transition", target)
