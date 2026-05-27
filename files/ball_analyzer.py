"""Ball delivery analyzer — wraps rolling buffer + Moondream + Scout VLM.

Usage:
    analyzer = BallAnalyzer(window_id=12345)
    analyzer.start()  # background thread, ~26fps capture

    # When a ball event fires:
    result = analyzer.analyze_last_delivery(runs=4)
    # result = {"length": "good_length", "line": "outside_off", ...} or None

    analyzer.stop()

Architecture (default VLM mode):
    Capture: every screen frame → rolling frame buffer (1200 frames,
        ~45s at 26fps).  The previous is_wide_shot gate at capture
        time was removed 2026-04-20 because it was dropping ~60% of
        frames and starving downstream window assembly.  is_wide_shot
        is still used as a CONSUMPTION-time filter when selecting
        frames for analysis, but no longer at the buffer boundary.
    Ball event fires → slice buffer [T-15s, T-2s] → narrow + Moondream
    stumps detection on every delivery (no cache) → 8 evenly-spaced
    frames → Scout vision model with comprehensive prompt → semantic
    classification (length, line, shot, direction, swing, speed).

    No coordinate math, no broadcaster calibration, no ROI cache.

Legacy trajectory mode (USE_TRAJECTORY_ANALYSIS=1):
    Same up through Moondream; then ball detection + phase separation
    + coordinate-based classifier.  Kept behind a flag for A/B work.
"""
from __future__ import annotations

import collections
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

try:
    import Quartz.CoreGraphics as CG
except ImportError:
    CG = None

from eyes.capture.frame_source import CaptureCardFrameSource

FRAME_SOURCE = os.environ.get("FRAME_SOURCE", "capture_card").lower()
CAPTURE_DEVICE_INDEX = int(os.environ.get("CAPTURE_DEVICE_INDEX", "0"))
# See operations doc + eyes/config.py: default 0 preserves the
# pipeline-wide RGB-as-bgr quirk every consumer was tuned against.
FRAME_COLOR_TRUE_BGR = os.environ.get("FRAME_COLOR_TRUE_BGR", "0") == "1"

from ball_detection_utils import detect_white_ball, find_video_region, is_wide_shot
from pitch_detector import is_delivery_frame
from pitch_grounder import (
    detect_pitch_in_frame, ground_pitch_in_frames,
    narrow_to_delivery_block, PitchBox, PitchROICache,
)


def _ground_single_frame_safe(bgr: np.ndarray) -> "PitchBox | None":
    """Best-effort single-frame Moondream grounding.

    Used as the OPTIONAL parallel enrichment call alongside Scout VLM
    classification.  Returns None on any failure — never raises.  The
    Scout classification result is the source of truth; stump_cx is a
    bonus when available.
    """
    try:
        return detect_pitch_in_frame(bgr)
    except Exception as e:
        log.info("[GROUNDER] single-frame call swallowed: %s", e)
        return None
from phase_separator import separate_phases
from ball_classifier import (
    classify_length, classify_line, classify_bowling_angle,
    classify_bounce, classify_shot_direction, classify_shot_elevation,
    infer_shot_direction_from_context,
    build_commentary_line, _shot_type_from_runs, _is_full_toss_trajectory,
)
from vlm_delivery_classifier import VLMDeliveryClassifier
from gemini_delivery_classifier import (
    GeminiDeliveryClassifier,
    _build_commentary_line as _gemini_build_commentary_line,
    _unknown_result as _gemini_unknown_result,
)
from delivery_window_recorder import DeliveryWindowRecorder
from eyes.config import (
    USE_OPEN_SCOUT,
    USE_OPEN_SCOUT_SPANS,
    USE_V3_CHUNKER,
    USE_V3_CHUNKER_SPANS,
)
from eyes.chunker_v3_aggregator import V3SpanAggregator
from eyes.span_aggregator import SpanAggregator

USE_TRAJECTORY_ANALYSIS = os.environ.get(
    "USE_TRAJECTORY_ANALYSIS", "0") == "1"
# 2026-04-20: Gemini-3-flash-preview now owns delivery action
# classification (length / line / handedness / shot / bounce /
# narrative) via DeliveryWindowRecorder.  Scout still owns scoreboard
# / camera_view tagging.  Set USE_LEGACY_VLM=1 to fall back to the
# old Scout-3-frame VLM path for emergency rollback.
USE_LEGACY_VLM = os.environ.get("USE_LEGACY_VLM", "0") == "1"
# 2026-04-20 (Layer 2): swap the primary classifier from Gemini-only
# cricket-schema to Qwen+Gemini routed spatial (Layer2Classifier).
# Both expose the same classify_frames/classify_video/available
# surface so the DWR layer doesn't notice.  Default ON; set
# USE_LAYER2=0 to fall back to Gemini-only.
USE_LAYER2 = os.environ.get("USE_LAYER2", "1") == "1"
# Moondream pitch grounding (2026-04-18): now OPT-IN.  Scout's
# semantic classification (`line=on_stumps|outside_off|...`) replaces
# the geometric stump_cx that Moondream used to compute, so the
# per-delivery path no longer needs Moondream at all.  Set
# USE_VLM_GROUNDING=1 to re-enable as parallel optional enrichment
# (useful for offline calibration / debugging).
USE_VLM_GROUNDING = os.environ.get("USE_VLM_GROUNDING", "0") == "1"
# Number of frames Scout sees per delivery (capped at 5 in classifier)
VLM_FRAMES_PER_DELIVERY = int(
    os.environ.get("VLM_FRAMES_PER_DELIVERY", "5"))
# How many frames to save to disk per delivery for offline labeling/sweeps
SAVE_FRAMES_PER_DELIVERY = int(
    os.environ.get("SAVE_FRAMES_PER_DELIVERY", "8"))

log = logging.getLogger("ball_analyzer")

# Wire ball_analyzer logs into the CricketLogger file handler
try:
    from eyes.cricket_logger import _ensure_file_handler
    _fh = _ensure_file_handler()
    log.addHandler(_fh)
    log.setLevel(logging.DEBUG)
except Exception:
    pass

# 1200 frames ≈ 45s at the ~26 fps screen-capture rate (post 2026-04-20
# is_wide_shot decoupling — the buffer now stores EVERY frame, not only
# wide-shot frames, so the effective buffered duration is ~half what it
# was under the old filtered regime).  45s of headroom is enough for a
# typical delivery window (8-15s) plus a few seconds of pre/post slop;
# bump this if you start hitting empty buffers across long replay or
# DRS sequences.  Memory: ~2 GB at 960×540×3 bytes/frame.
FRAME_BUFFER_MAXLEN = 1200
TAGGED_BUFFER_RETENTION_S = 90.0
# Downscale buffer frames to this width to reduce memory pressure.
# 960px (half of 1080p) cuts memory ~4x while retaining enough detail
# for ball detection.  Moondream further downscales to 384px anyway.
BUFFER_FRAME_WIDTH = 960


def _unknown_result(runs: int, *,
                    skip_reason: str | None = None) -> dict:
    result = {
        "length": "unknown", "line": "unknown",
        "bowling_angle": "unknown", "bounce": "unknown",
        "shot_type": _shot_type_from_runs(runs),
        "shot_elevation": _shot_type_from_runs(runs),
        "shot_direction": {"side": "unknown", "confidence": "none"},
        "runs": runs, "detections": 0,
        "detection_rate": 0.0,
        "commentary_line": "",
    }
    if skip_reason:
        result["_untrackable"] = True
        result["_skip_reason"] = skip_reason
    return result


# Burst tracker tuning (2026-04-19).  Time-based, not frame-count-based,
# so the same thresholds work whether capture FPS is 20 or 30.
#   MIN_DURATION  filters out side-on flashes / brief graphics overlays
#                 that happen to look like a pitch+figures pattern for a
#                 few frames.  Real bowler's-end deliveries always run
#                 ≥ 2-3 s of continuous camera.
#   GAP_TOLERANCE swallows brief filter misses inside a real burst — the
#                 bowler's-end camera often pans slightly during run-up
#                 and is_delivery_frame can drop out for 100-200 ms
#                 without the broadcast actually cutting away.
BURST_MIN_DURATION_S = float(
    os.environ.get("BURST_MIN_DURATION_S", "1.0"))
BURST_GAP_TOLERANCE_S = float(
    os.environ.get("BURST_GAP_TOLERANCE_S", "0.3"))
BURST_KEEP_N = int(os.environ.get("BURST_KEEP_N", "6"))


class DeliveryBurstTracker:
    """Track contiguous bursts of bowler's-end (delivery-view) frames.

    Architectural rationale (2026-04-19): the scoreboard updates AFTER
    the broadcast has already cut away from the live action, so any
    capture window anchored on the score event misses the actual
    delivery moment.  But the broadcast DOES show the delivery — for
    a contiguous 3-5 s window of bowler's-end camera — just earlier
    than the score event by some unknown lag.

    Run is_delivery_frame() on every wide-shot frame in the capture
    loop (benchmarked at 0.35 ms/call → ~1% CPU at 30 fps).  Track
    each contiguous run of passing frames as a "burst".  Tolerate
    short gaps (BURST_GAP_TOLERANCE_S) so a momentary filter miss
    during a real delivery doesn't prematurely close the burst.  When
    the gap exceeds tolerance the burst is closed; if its duration is
    >= BURST_MIN_DURATION_S we commit it to a ring of recent bursts.

    When a score event fires, the most recent committed burst that
    ended within max_age_s IS the delivery.  Already captured, already
    filtered, no temporal slicing or motion-biased frame picking
    needed — Scout sees the actual delivery sequence directly.

    Thread-safety: on_frame() runs on the capture thread; the readers
    run on the main pipeline thread.  All access is serialised via
    _lock.  Lock hold times are sub-millisecond.
    """

    def __init__(self,
                 min_duration_s: float = BURST_MIN_DURATION_S,
                 gap_tolerance_s: float = BURST_GAP_TOLERANCE_S,
                 keep_n: int = BURST_KEEP_N) -> None:
        self._min_duration_s = min_duration_s
        self._gap_tolerance_s = gap_tolerance_s
        self._current: list[tuple[float, np.ndarray]] = []
        self._last_match_ts: float = 0.0
        self._completed: collections.deque[
            tuple[float, float, list[tuple[float, np.ndarray]]]] = (
            collections.deque(maxlen=keep_n))
        self._lock = threading.Lock()
        self._stats = {"frames": 0, "passing": 0,
                       "bursts_committed": 0,
                       "bursts_dropped_short": 0}

    def on_frame(self, ts: float, frame: np.ndarray,
                 is_delivery: bool) -> None:
        with self._lock:
            self._stats["frames"] += 1
            if is_delivery:
                self._stats["passing"] += 1
                self._current.append((ts, frame))
                self._last_match_ts = ts
                return

            if not self._current:
                return

            if ts - self._last_match_ts > self._gap_tolerance_s:
                self._close_burst_locked()

    def _close_burst_locked(self) -> None:
        if not self._current:
            return
        burst = self._current
        duration = burst[-1][0] - burst[0][0]
        accepted = duration >= self._min_duration_s
        if accepted:
            self._completed.append((burst[0][0], burst[-1][0], burst))
            self._stats["bursts_committed"] += 1
        else:
            self._stats["bursts_dropped_short"] += 1
        # Per-burst log so a human can audit at a glance whether
        # tuning is right after one innings: ~120 bursts → one per
        # delivery; 80 → missing 1/3; 200 → splitting incorrectly.
        log.info(
            f"  [BURST] closed duration={duration:.2f}s "
            f"frames={len(burst)} last_match_ts={burst[-1][0]:.1f} "
            f"({'ACCEPTED' if accepted else 'rejected (<' + format(self._min_duration_s, '.1f') + 's)'})")
        self._current = []

    def get_burst_for_event(self, event_ts: float,
                            max_age_s: float = 30.0,
                            ) -> tuple[
                                list[tuple[float, np.ndarray]] | None,
                                dict]:
        """Return the most recent burst whose end is within max_age_s.

        Returns (burst, info) — burst is None if no eligible burst.
        info carries diagnostic fields for logging.

        We also flush the in-progress burst before searching: a burst
        may still be "open" at the moment a score event fires (broadcast
        hasn't cut away yet).  Treating it as a candidate would bias
        toward incomplete bursts, so we leave the active burst alone
        unless it already meets the duration threshold — in which case
        we commit it so the score event can use it.
        """
        with self._lock:
            # Promote a long-enough in-progress burst so the score
            # event can pick it up.  Don't reset on commit — the
            # bowler's-end shot might continue and the next event
            # would then see an even longer burst.  But we do snapshot
            # to avoid the burst growing past the snapshot we return.
            if (self._current
                    and (self._current[-1][0] - self._current[0][0])
                    >= self._min_duration_s):
                snap = list(self._current)
                # Treat the snapshot as a virtual completed burst for
                # this event without consuming the active one.
                committed = list(self._completed) + [
                    (snap[0][0], snap[-1][0], snap)]
            else:
                committed = list(self._completed)
            active_len = len(self._current)

        for start_ts, end_ts, burst in reversed(committed):
            age = event_ts - end_ts
            if 0.0 <= age <= max_age_s:
                return burst, {
                    "burst_len": len(burst),
                    "burst_dur_s": round(end_ts - start_ts, 2),
                    "burst_age_s": round(age, 2),
                    "active_burst_len": active_len,
                    "committed_bursts": len(self._completed),
                }

        return None, {
            "burst_len": 0,
            "burst_dur_s": 0.0,
            "burst_age_s": -1,
            "active_burst_len": active_len,
            "committed_bursts": len(self._completed),
        }

    @staticmethod
    def select_middle(burst: list[tuple[float, np.ndarray]],
                      n: int) -> list[np.ndarray]:
        """Pick `n` frames centred on the burst midpoint.

        The midpoint of a 3-5 s bowler's-end burst is reliably near
        ball release / pitch / contact.  Picking middle-N frames gives
        Scout the moment-of-action sequence without padding from
        run-up or follow-through.
        """
        if not burst:
            return []
        if n >= len(burst):
            return [f for _, f in burst]
        mid = len(burst) // 2
        half = n // 2
        lo = max(0, mid - half)
        hi = min(len(burst), lo + n)
        lo = max(0, hi - n)
        return [burst[i][1] for i in range(lo, hi)]

    def snapshot_stats(self) -> dict:
        with self._lock:
            s = dict(self._stats)
            s["active_burst_len"] = len(self._current)
            s["committed_bursts"] = len(self._completed)
            s["pass_rate_pct"] = round(
                s["passing"] / max(s["frames"], 1) * 100, 1)
            return s


class BallAnalyzer:
    """Continuous background capture + on-demand delivery analysis."""

    def __init__(self, window_id: int, *, file_frame_source=None,
                 session_id: str | None = None):
        self._window_id = window_id
        self._frame_source_mode = FRAME_SOURCE
        self._capture_card: CaptureCardFrameSource | None = (
            CaptureCardFrameSource(device_index=CAPTURE_DEVICE_INDEX)
            if FRAME_SOURCE == "capture_card" else None)
        # File-replay path: when FRAME_SOURCE=file, callers pass the
        # already-started FileFrameSource here so _grab_full_frame_bgr
        # can pull from it instead of falling through to the unavailable
        # Quartz path (which would leave _frame_buffer_raw empty).
        self._file_frame_source = file_frame_source
        self._frame_buffer: collections.deque[tuple[float, np.ndarray]] = (
            collections.deque(maxlen=FRAME_BUFFER_MAXLEN))
        self._frame_buffer_raw: collections.deque[
            tuple[float, np.ndarray]] = collections.deque(
                maxlen=FRAME_BUFFER_MAXLEN)
        # Scout-tagged frame buffer (camera_view + frame_phase aware).
        # Architecture (2026-04-18, extended 2026-04-19):
        #   v1: Scout already classifies every frame it reads for
        #       scoreboard data — we add `camera_view` tagging at
        #       zero extra Scout cost.
        #   v2: prompt extended to also return `frame_phase`
        #       (release / flight / shot / post_shot / ...).  Lets
        #       analyze_last_delivery sample the moment-of-action
        #       instead of the post-action camera dwell.
        # Tuple shape: (ts, frame, camera_view, frame_phase).
        # Capacity 240 = ~10 min at Scout's 0.4 Hz cadence; plenty of
        # headroom even with active-play burst-mode tagging.
        self._tagged_buffer: collections.deque[
            tuple[float, np.ndarray, str, str | None]] = (
                collections.deque(maxlen=240))
        self._tagged_lock = threading.Lock()
        # Burst tracker (2026-04-19): runs is_delivery_frame on every
        # captured wide-shot frame, accumulates contiguous delivery-
        # view bursts.  Replaces the score-event-anchored temporal
        # slice + motion-biased frame picking that was sending Scout
        # frames from BEFORE/AFTER the actual delivery.
        self._burst_tracker = DeliveryBurstTracker()
        # Stats logged every 30 s
        self._burst_last_log = 0.0
        self._thread: threading.Thread | None = None
        self._running = False
        self._frames_read = 0
        self._buf_count = 0
        self._content_y = 0
        self._actual_fps = 0.0
        self._delivery_count = 0
        self._last_buf_stats: dict = {}
        self._roi_cache = PitchROICache()  # legacy; unused in VLM mode
        self._current_innings = 1
        # session id keeps delivery folders from colliding across runs
        self._session_id = session_id or time.strftime("%Y%m%d_%H%M%S")
        # OpenScout output persistence (Layer A sidecar + decoupled
        # delivery clip writer).  Wired in via ``attach_open_scout_sidecar``
        # from the pipeline boot path; left None when OpenScout is
        # disabled or the boot path doesn't construct a sidecar.
        self._open_scout_sidecar = None
        self._open_scout_delivery_writer = None
        # DRS freeze: when DRS goes IN_PROGRESS we snapshot the buffer so
        # the original delivery frames aren't lost while the review runs.
        self._drs_frozen_snapshot: list[tuple[float, np.ndarray]] | None = None
        self._drs_freeze_at: float | None = None
        # Async delivery classification (2026-04-20):
        # Scoreboard fires ball events while the broadcast is still live.
        # Blocking the main pipeline on a 10-25s Gemini call causes score-
        # event detection to fall ~20s behind reality, which in turn makes
        # retrospective lookback grab post-ball replays/aftermath instead
        # of the live delivery.  Solution: hand each analysis to a single-
        # worker background thread and return a pending stub immediately.
        # WS broadcasts pick up the latest completed result via
        # last_completed_delivery_info().
        self._analysis_executor: ThreadPoolExecutor | None = None
        self._analysis_slot_lock = threading.Lock()
        self._last_completed_delivery_info: dict | None = None
        self._pending_analyses = 0
        self._analysis_stats = {
            "submitted": 0, "completed": 0, "failed": 0}
        # VLM classifier (lazily initialized — only construct if needed)
        self._vlm: VLMDeliveryClassifier | None = (
            None if (USE_TRAJECTORY_ANALYSIS or not USE_LEGACY_VLM)
            else VLMDeliveryClassifier())
        # Parallel-Scout SpanAggregator (design memo §4).  Constructed
        # unconditionally so shadow telemetry can run even when
        # USE_OPEN_SCOUT_SPANS=0 (default).  When USE_OPEN_SCOUT=0 the
        # aggregator simply receives no observations.
        self._span_aggregator: SpanAggregator = SpanAggregator()
        # Chunker v3 (rule-based, time-based delivery-window detection).
        # Constructed unconditionally — feeds get no observations when
        # USE_V3_CHUNKER=0 and the v3_aggregator passed to DWR remains
        # idle.  See files/docs/algorithms/chunker_v3.md.
        self._v3_aggregator: V3SpanAggregator | None = (
            V3SpanAggregator() if USE_V3_CHUNKER else None)
        # Stage 2 (DeliverySpanSelector) lookup callable.  Wired in
        # post-boot via ``attach_stage2_span_lookup`` once the
        # OpenScout shadow runner is constructed; remains None when
        # USE_OPEN_SCOUT=0 or no shadow runner is available.
        self._stage2_span_lookup: Callable[
            [float], tuple[float, float] | None] | None = None
        # Gemini delivery classifier + Scout-triggered window recorder
        # (2026-04-20).  Replaces VLMDeliveryClassifier as the primary
        # delivery-action source; the Scout pipeline keeps owning
        # camera_view tagging, scoreboard, names, and speed.  Build
        # eagerly so on_scout_tag() works before the first delivery.
        self._gemini_clf = None  # duck-typed: Gemini or Layer2 classifier
        self._recorder: DeliveryWindowRecorder | None = None
        if not USE_TRAJECTORY_ANALYSIS and not USE_LEGACY_VLM:
            if USE_LAYER2:
                try:
                    from layer2_classifier import Layer2Classifier
                    self._gemini_clf = Layer2Classifier()
                    if not self._gemini_clf.available():
                        log.warning(
                            "[L2] classifier unavailable at boot: "
                            f"{self._gemini_clf._init_error} — "
                            "delivery_info will be 'unknown' until fixed")
                except Exception as e:  # noqa: BLE001
                    log.warning(f"[L2] init failed: {e}")
                    self._gemini_clf = None
            else:
                try:
                    self._gemini_clf = GeminiDeliveryClassifier()
                    if not self._gemini_clf.available():
                        log.warning(
                            "[GEMINI] classifier unavailable at boot: "
                            f"{self._gemini_clf._init_error} — "
                            "delivery_info will be 'unknown' until fixed")
                except Exception as e:  # noqa: BLE001
                    log.warning(f"[GEMINI] init failed: {e}")
                    self._gemini_clf = None
            if self._gemini_clf is not None:
                save_root = Path("logs") / "deliveries" / self._session_id
                self._recorder = DeliveryWindowRecorder(
                    classifier=self._gemini_clf,
                    frame_source_fn=self._frame_source,
                    tagged_source_fn=self._snapshot_tagged,
                    save_root=save_root,
                    span_aggregator=self._span_aggregator,
                    use_open_scout_spans=USE_OPEN_SCOUT_SPANS,
                    stage2_span_lookup=self._stage2_span_lookup_proxy,
                    v3_aggregator=self._v3_aggregator,
                    use_v3_chunker_spans=USE_V3_CHUNKER_SPANS,
                )

        _mode = (
            "TRAJECTORY" if USE_TRAJECTORY_ANALYSIS
            else "LEGACY_VLM" if USE_LEGACY_VLM
            else ("LAYER2" if USE_LAYER2 else "GEMINI")
            if self._recorder is not None
            else "UNKNOWN_NO_CLASSIFIER")
        log.info(f"BallAnalyzer mode: {_mode} "
                 f"(session={self._session_id}, "
                 f"vlm_frames={VLM_FRAMES_PER_DELIVERY}, "
                 f"save_frames={SAVE_FRAMES_PER_DELIVERY})")

    def start(self):
        if self._capture_card is not None:
            try:
                self._capture_card.start()
            except Exception as e:
                log.error(
                    "[capture_card] start failed (%s); BallAnalyzer disabled. "
                    "Set FRAME_SOURCE=window to fall back to Quartz.", e)
                return
            log.info(
                f"BallAnalyzer frame source: capture_card "
                f"(device={CAPTURE_DEVICE_INDEX})")
        elif self._file_frame_source is not None:
            log.info(
                f"BallAnalyzer frame source: file "
                f"(path={getattr(self._file_frame_source, 'video_path', '?')})")
        else:
            if CG is None:
                log.warning("Quartz not available — BallAnalyzer disabled")
                return
            log.info(
                f"BallAnalyzer frame source: window "
                f"(window_id={self._window_id})")
        self._content_y = self._detect_content_top()
        self._running = True
        # 2-worker executor: L2 classification averages ~15-25 s per
        # delivery (Qwen + Gemini in parallel inside the classifier);
        # at typical T20 cadence of one ball every ~25 s a single
        # worker would queue up.  Two workers lets L2 keep up with a
        # burst (e.g. 2 balls in quick succession plus replay), while
        # still bounded so Gemini/Fireworks quotas aren't hammered.
        if (self._recorder is not None and self._gemini_clf is not None
                and self._analysis_executor is None):
            self._analysis_executor = ThreadPoolExecutor(
                max_workers=2, thread_name_prefix="dwr-worker")
        self._thread = threading.Thread(
            target=self._capture_loop, daemon=True, name="ball-analyzer")
        self._thread.start()
        log.info(f"BallAnalyzer started (window={self._window_id}, "
                 f"content_y={self._content_y})")

        # Warm Moondream BEFORE the first real delivery to avoid the
        # 5-10s/call MLX JIT-compile cost on the first 2-3 deliveries.
        # Done in a background thread so it doesn't block pipeline boot.
        # 2026-04-18: only warm if USE_VLM_GROUNDING is enabled —
        # otherwise we never call Moondream and JIT cost is wasted.
        if USE_VLM_GROUNDING or USE_TRAJECTORY_ANALYSIS:
            threading.Thread(
                target=self._warmup_grounder,
                daemon=True, name="moondream-warmup",
            ).start()
        else:
            log.info("Moondream warmup SKIPPED (USE_VLM_GROUNDING=0). "
                     "Set USE_VLM_GROUNDING=1 to re-enable parallel "
                     "stump-grounding enrichment per delivery.")

    def _warmup_grounder(self):
        try:
            from pitch_grounder import warmup
            warmup(dummy_size=(540, BUFFER_FRAME_WIDTH))
        except Exception as e:
            log.warning(f"Moondream warmup failed: {e}")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._capture_card is not None:
            try:
                self._capture_card.stop()
            except Exception as e:
                log.debug(f"[capture_card] stop swallowed: {e}")
        self._roi_cache.clear()
        # Let in-flight delivery analyses drain — Gemini is slow so give
        # them a generous window, but don't hang forever if one is stuck.
        if self._analysis_executor is not None:
            try:
                self._analysis_executor.shutdown(
                    wait=True, cancel_futures=False)
            except Exception as e:  # noqa: BLE001
                log.debug(f"[ASYNC-DA] executor shutdown swallowed: {e}")
            self._analysis_executor = None
        if self._recorder is not None:
            try:
                self._recorder.shutdown()
            except Exception as e:  # noqa: BLE001
                log.debug(f"[DWR] shutdown swallowed: {e}")
        # Layer2Classifier owns its own 2-worker Q+G pool; flush it.
        if self._gemini_clf is not None and hasattr(
                self._gemini_clf, "shutdown"):
            try:
                self._gemini_clf.shutdown()
            except Exception as e:  # noqa: BLE001
                log.debug(f"[L2] classifier shutdown swallowed: {e}")
        log.info(f"BallAnalyzer stopped ({self._frames_read} total, "
                 f"{self._buf_count} buffered, "
                 f"~{self._actual_fps:.0f} fps, "
                 f"async_da submitted={self._analysis_stats['submitted']} "
                 f"completed={self._analysis_stats['completed']} "
                 f"failed={self._analysis_stats['failed']})")

    @property
    def alive(self) -> bool:
        return (self._running and self._thread is not None
                and self._thread.is_alive())

    def freeze_buffer_for_drs(self) -> None:
        """Snapshot the rolling buffer so the delivery under review is
        preserved while the review runs (often 30-60s).  Without this,
        the original delivery frames roll out of the buffer before the
        DRS event fires and we're left with replay/review footage.

        Idempotent — calling twice keeps the FIRST snapshot.
        """
        if self._drs_frozen_snapshot is not None:
            return
        self._drs_frozen_snapshot = list(self._frame_buffer)
        self._drs_freeze_at = time.time()
        log.info(f"[DRS FREEZE] Buffer snapshot taken "
                 f"({len(self._drs_frozen_snapshot)} frames)")

    def unfreeze_buffer_for_drs(self) -> None:
        """Drop any frozen DRS snapshot.  Call when DRS resolves WITHOUT
        having issued a delivery analysis (e.g. NOT_OUT, no event)."""
        if self._drs_frozen_snapshot is not None:
            log.info(f"[DRS FREEZE] Snapshot discarded "
                     f"({len(self._drs_frozen_snapshot)} frames, "
                     f"{time.time() - (self._drs_freeze_at or 0):.0f}s old)")
        self._drs_frozen_snapshot = None
        self._drs_freeze_at = None

    def _frame_source(self,
                      start_ts: float,
                      end_ts: float,
                      ) -> list[tuple[float, np.ndarray]]:
        """Slice the rolling capture buffer by absolute timestamps.

        Used by DeliveryWindowRecorder to compile delivery windows.
        list() is atomic on a deque so we can snapshot without taking
        a lock, then filter at our leisure.
        """
        snap = list(self._frame_buffer_raw)
        return [(ts, fr) for ts, fr in snap
                if start_ts <= ts <= end_ts]

    def on_scout_tag(self, ts: float, camera_view: str | None) -> None:
        """Forward a Scout camera_view observation to the recorder.

        Called by the main pipeline after each Scout describe() call.
        Drives the window state machine that defines delivery clip
        boundaries for the Gemini classifier.

        No-op when running in LEGACY_VLM / TRAJECTORY mode (the
        recorder isn't constructed in those modes).
        """
        if self._recorder is None:
            return
        if not self.alive:
            return
        try:
            self._recorder.on_scout_tag(ts, camera_view)
        except Exception as e:  # noqa: BLE001
            log.debug(f"[DWR] on_scout_tag swallowed: {e}")

    def recorder_tick(self, now: float | None = None) -> None:
        """Drive the recorder's MAX_WINDOW_S timeout check.

        Call ~once per main-loop iteration.
        """
        if self._recorder is None:
            return
        try:
            self._recorder.tick(now=now)
        except Exception as e:  # noqa: BLE001
            log.debug(f"[DWR] tick swallowed: {e}")

    def record_open_classification(self,
                                   ts: float,
                                   frame_class: str | None,
                                   text: str | None = None) -> None:
        """Forward an OpenScout per-frame classification to the
        SpanAggregator.

        Called fire-and-forget by the per-frame loop after each
        OpenScout coroutine completes.  No-op if frame_class is None
        / empty so the caller doesn't have to special-case API
        failures.
        """
        if not frame_class:
            return
        try:
            self._span_aggregator.add_classification(ts, frame_class, text)
        except Exception as e:  # noqa: BLE001
            log.debug(f"[OPEN-SCOUT] aggregator add swallowed: {e}")

    @property
    def span_aggregator(self) -> SpanAggregator:
        return self._span_aggregator

    @property
    def v3_aggregator(self) -> V3SpanAggregator | None:
        return self._v3_aggregator

    def record_v3_frame(self,
                        ts: float,
                        *,
                        prod_cam: str | None,
                        prod_phase: str | None,
                        v2_broadcast_tag: str | None,
                        v2_class: str | None,
                        open_desc: str | None) -> None:
        """Feed one per-frame Scout payload into the v3 aggregator.

        No-op when ``USE_V3_CHUNKER=0`` (aggregator not constructed).
        Failures are swallowed so the caller's fire-and-forget loop
        never raises.
        """
        agg = self._v3_aggregator
        if agg is None:
            return
        try:
            agg.add_frame(
                ts,
                prod_cam=prod_cam,
                prod_phase=prod_phase,
                v2_broadcast_tag=v2_broadcast_tag,
                v2_class=v2_class,
                open_desc=open_desc,
            )
        except Exception as e:  # noqa: BLE001
            log.debug(f"[CHUNKER-V3] aggregator add swallowed: {e}")

    def attach_stage2_span_lookup(
            self,
            lookup: Callable[[float], tuple[float, float] | None] | None,
    ) -> None:
        """Wire a Stage-2 (DeliverySpanSelector) span lookup callable.

        Called from the pipeline boot path after ``OpenScoutShadowRunner``
        is constructed.  When ``USE_OPEN_SCOUT_SPANS=1`` and the lookup
        returns a span for a score event, ``DeliveryWindowRecorder``
        prefers it over the legacy SpanAggregator-direct path (see
        ``files/docs/investigations/sub_clip_delivery_isolation_v4.md``
        §8).  Idempotent.
        """
        self._stage2_span_lookup = lookup

    def _stage2_span_lookup_proxy(
            self, event_ts: float,
    ) -> tuple[float, float] | None:
        """Late-binding proxy installed at DWR construction time.

        DWR is built before the shadow runner exists; this proxy lets
        ``attach_stage2_span_lookup`` swap in the real callable without
        rebuilding DWR.
        """
        cb = self._stage2_span_lookup
        if cb is None:
            return None
        try:
            return cb(event_ts)
        except Exception as e:  # noqa: BLE001
            log.warning(
                f"[OPEN-SCOUT-SPAN] stage2 lookup proxy raised: {e}")
            return None

    def attach_open_scout_sidecar(self, sidecar) -> None:
        """Wire Layer A sidecar + :class:`OpenScoutDeliveryWriter` on the
        SpanAggregator committed callback (validation clips under
        ``files/logs/openscout_deliveries/``).

        Idempotent — calling twice with the same sidecar is a no-op;
        calling with a different sidecar replaces the writer.

        See ``files/eyes/openscout_persistence.py`` and
        ``files/docs/operations/parallel_scout_setup.md``.
        """
        existing = getattr(self, "_open_scout_sidecar", None)
        if existing is sidecar and getattr(
                self, "_open_scout_delivery_writer", None) is not None:
            return
        try:
            from eyes.openscout_persistence import OpenScoutDeliveryWriter
        except Exception as e:  # noqa: BLE001
            log.warning(
                f"[OPEN-SCOUT-DELIVERY] import failed: {e}; "
                f"validation clips disabled")
            return
        writer = OpenScoutDeliveryWriter(
            session_id=self._session_id,
            frame_source_fn=self._frame_source,
            sidecar=sidecar,
        )
        self._open_scout_sidecar = sidecar
        self._open_scout_delivery_writer = writer
        try:
            self._span_aggregator.set_committed_callback(
                writer.on_span_committed)
        except Exception as e:  # noqa: BLE001
            log.warning(
                f"[OPEN-SCOUT-DELIVERY] set_committed_callback "
                f"failed: {e}")

    def record_tagged_frame(self, frame: np.ndarray,
                            camera_view: str | None,
                            timestamp: float | None = None,
                            frame_phase: str | None = None) -> None:
        """Stash a Scout-classified frame for later delivery analysis.

        Called by the main loop after each Scout `describe()` call.
        We retain the key delivery-adjacent views needed for
        retrospective span lookup and post-ball replay harvesting.

        Args:
            frame: BGR full broadcast frame as Scout saw it.
            camera_view: Scout's normalised camera_view tag.
            timestamp: optional epoch ts; defaults to now.
            frame_phase: Scout's normalised frame_phase tag (release
                / flight / shot / post_shot / runup / etc).  Drives
                downstream frame selection in analyze_last_delivery.
                Pass None for back-compat callers.
        """
        if camera_view not in ("bowlers_end", "side_on", "replay"):
            return
        if frame is None or frame.size == 0:
            return
        ts = timestamp if timestamp is not None else time.time()
        with self._tagged_lock:
            self._tagged_buffer.append((ts, frame, camera_view, frame_phase))
            cutoff = ts - TAGGED_BUFFER_RETENTION_S
            while self._tagged_buffer and self._tagged_buffer[0][0] < cutoff:
                self._tagged_buffer.popleft()

    def _snapshot_tagged(self,
                         lo_ts: float,
                         hi_ts: float,
                         views: tuple[str, ...] | None = ("bowlers_end",),
                         phases: tuple[str, ...] | None = None,
                         ) -> list[tuple[float, np.ndarray, str, str | None]]:
        """Return tagged frames within [lo_ts, hi_ts] matching views.

        Bounds are absolute epoch seconds.  Returned in chronological
        order.  Holding the lock for the deque copy is cheap (≪1ms).

        Args:
            lo_ts, hi_ts: absolute epoch-second window bounds.
            views: camera_view tags to keep.
            phases: optional frame_phase filter — when set, only
                frames whose phase is in this tuple are returned
                (None-phase frames are dropped).  Used by
                analyze_last_delivery to grab release/flight/shot
                frames specifically.
        """
        with self._tagged_lock:
            snap = list(self._tagged_buffer)
        out = []
        for ts, f, v, p in snap:
            if not (lo_ts <= ts <= hi_ts):
                continue
            if views is not None and v not in views:
                continue
            if phases is not None and p not in phases:
                continue
            out.append((ts, f, v, p))
        return out

    def on_innings_change(self, new_innings: int) -> None:
        """Invalidate cached ROIs for the new innings.

        Call when the scoreboard detects an innings change.  The
        bowler's-end camera may shift between innings, so fresh
        VLM calibration is needed for both ends.
        """
        self._current_innings = new_innings
        self._roi_cache.invalidate_innings(new_innings)

    def _run_gemini_delivery_analysis(
            self,
            runs: int,
            speed_kph: float | None,
            over_number: float | None,
            innings: int,
            event_type: str | None,
            event_ts: float,
            delivery_num: int,
            delivery_dir: Path,
            known_batsman_handed: str = "unknown",
            known_bowling_arm: str = "unknown",
    ) -> dict:
        """Run the DWR + Gemini classification and build the final
        delivery_info dict.  Synchronous — callable from either the
        main thread (analyze_last_delivery) or the dwr-worker thread
        (enqueue_delivery_analysis).  Does not mutate class counters
        (delivery_count was already bumped by the caller)."""
        dnum = delivery_num
        t0 = event_ts
        result = self._recorder.classify_for_score_event(
            runs=runs,
            over_number=over_number,
            innings=innings,
            event_type=event_type,
            event_ts=t0,
            delivery_num=dnum,
            save_dir=delivery_dir,
            await_timeout_s=20.0,
            known_batsman_handed=known_batsman_handed,
            known_bowling_arm=known_bowling_arm,
        )
        wall = (time.time() - t0) * 1000

        if result is None:
            log.warning(
                f"  [D#{dnum}] [GEMINI] no usable retrospective clip "
                f"for this score event — emitting unknown")
            result = _gemini_unknown_result(
                runs, "no_window_captured")
            result["_event_type"] = event_type
            result["_from_cache"] = False

        if speed_kph is not None:
            result["ball_speed_kph_vlm"] = float(speed_kph)
            result["ball_speed_visible"] = True
        result["runs"] = runs
        result["_session"] = self._session_id
        result["_wall_ms"] = round(wall)
        result["_innings"] = innings
        result["_over_number"] = over_number
        # Overlay squad-resolved handedness/arm on top of the
        # classifier's "unknown" defaults (those fields are no longer
        # visually detected — see eyes/player_enrichment.py).
        if known_batsman_handed in ("left", "right"):
            result["batsman_handed"] = known_batsman_handed
        if known_bowling_arm in ("left", "right"):
            result["bowling_arm"] = known_bowling_arm
        try:
            result["commentary_line"] = (
                _gemini_build_commentary_line(result))
        except Exception as e:  # noqa: BLE001
            log.debug(f"[GEMINI] commentary build swallowed: {e}")

        self._log_gemini_result(dnum, result)
        try:
            self._persist_predictions_summary(
                runs, speed_kph, result, dnum)
        except Exception as e:  # noqa: BLE001
            log.debug(f"[GEMINI] persist swallowed: {e}")
        return result

    def enqueue_delivery_analysis(
            self,
            runs: int = 0,
            speed_kph: float | None = None,
            over_number: float | None = None,
            innings: int | None = None,
            event_age_hint: str | None = None,
            event_type: str | None = None,
            known_batsman_handed: str = "unknown",
            known_bowling_arm: str = "unknown",
    ) -> dict:
        """Hand a delivery classification off to the background worker
        and return an optimistic stub IMMEDIATELY.  Replaces the
        blocking analyze_last_delivery() call in the main pipeline.

        The stub carries `_pending=True` and the event metadata; the
        main loop can log "(analysis pending)" without waiting.  When
        the worker finishes (10-25 s later) it publishes the real
        result via last_completed_delivery_info(); WS broadcasts pick
        it up on the next cycle.

        Legacy VLM / trajectory modes, and the case where the recorder
        isn't available, fall back to the synchronous path so their
        semantics are unchanged.
        """
        self._last_speed_kph = speed_kph

        gemini_async_ok = (
            self.alive
            and self._recorder is not None
            and self._gemini_clf is not None
            and self._analysis_executor is not None
            and not USE_TRAJECTORY_ANALYSIS
            and not USE_LEGACY_VLM)

        if not gemini_async_ok:
            sync_result = self.analyze_last_delivery(
                runs=runs, speed_kph=speed_kph,
                over_number=over_number, innings=innings,
                event_age_hint=event_age_hint,
                event_type=event_type,
                known_batsman_handed=known_batsman_handed,
                known_bowling_arm=known_bowling_arm)
            if sync_result is not None:
                with self._analysis_slot_lock:
                    if not sync_result.get("_untrackable"):
                        self._last_completed_delivery_info = sync_result
            return sync_result or {}

        self._delivery_count += 1
        dnum = self._delivery_count
        inn = innings if innings is not None else self._current_innings
        event_ts = time.time()
        delivery_dir = self._delivery_folder()

        stub = {
            "_method": "gemini_async",
            "_pending": True,
            "_delivery_num": dnum,
            "_event_ts": event_ts,
            "_event_type": event_type,
            "_innings": inn,
            "_over_number": over_number,
            "_from_cache": False,
            "runs": runs,
            "ball_speed_kph_vlm": (
                float(speed_kph) if speed_kph is not None else None),
            "ball_speed_visible": speed_kph is not None,
            "commentary_line": "(analysis pending)",
            "detections": 0,
            "detection_rate": 0.0,
        }
        self._pending_analyses += 1
        self._analysis_stats["submitted"] += 1
        log.info(
            f"  [D#{dnum}] [ASYNC-DA] submitted "
            f"(pending={self._pending_analyses}, "
            f"event_type={event_type}, over={over_number}, "
            f"runs={runs})")

        def _worker() -> None:
            w_t0 = time.time()
            try:
                worker_result = self._run_gemini_delivery_analysis(
                    runs=runs, speed_kph=speed_kph,
                    over_number=over_number, innings=inn,
                    event_type=event_type, event_ts=event_ts,
                    delivery_num=dnum, delivery_dir=delivery_dir,
                    known_batsman_handed=known_batsman_handed,
                    known_bowling_arm=known_bowling_arm)
                self._analysis_stats["completed"] += 1
            except Exception as e:  # noqa: BLE001
                log.warning(
                    f"  [D#{dnum}] [ASYNC-DA] worker crashed: "
                    f"{type(e).__name__}: {e}")
                worker_result = _gemini_unknown_result(
                    runs, f"worker_exception:{type(e).__name__}")
                worker_result["_event_type"] = event_type
                worker_result["_innings"] = inn
                worker_result["_over_number"] = over_number
                self._analysis_stats["failed"] += 1
            finally:
                self._pending_analyses = max(
                    0, self._pending_analyses - 1)

            worker_ms = (time.time() - w_t0) * 1000
            log.info(
                f"  [D#{dnum}] [ASYNC-DA] completed "
                f"({worker_ms:.0f}ms, "
                f"pending_after={self._pending_analyses}, "
                f"submitted={self._analysis_stats['submitted']}, "
                f"completed={self._analysis_stats['completed']}, "
                f"failed={self._analysis_stats['failed']})")

            if worker_result and not worker_result.get("_untrackable"):
                with self._analysis_slot_lock:
                    self._last_completed_delivery_info = worker_result

        try:
            self._analysis_executor.submit(_worker)
        except RuntimeError as e:
            # Executor already shut down (e.g. stop() mid-match).
            log.warning(
                f"  [D#{dnum}] [ASYNC-DA] executor rejected submit: {e} "
                f"— falling back to synchronous classify")
            self._pending_analyses = max(0, self._pending_analyses - 1)
            return self.analyze_last_delivery(
                runs=runs, speed_kph=speed_kph,
                over_number=over_number, innings=innings,
                event_age_hint=event_age_hint,
                event_type=event_type,
                known_batsman_handed=known_batsman_handed,
                known_bowling_arm=known_bowling_arm) or stub

        return stub

    def last_completed_delivery_info(self) -> dict | None:
        """Return the most recently completed async delivery result.

        Non-blocking; safe to call from the main pipeline loop on every
        cycle.  Returns None until the first delivery has finished
        classifying."""
        with self._analysis_slot_lock:
            return self._last_completed_delivery_info

    def async_delivery_stats(self) -> dict:
        """Snapshot of enqueue/complete/fail counters for monitoring."""
        return {
            "pending": self._pending_analyses,
            "submitted": self._analysis_stats["submitted"],
            "completed": self._analysis_stats["completed"],
            "failed": self._analysis_stats["failed"],
        }

    def analyze_last_delivery(self, runs: int = 0,
                              speed_kph: float | None = None,
                              over_number: float | None = None,
                              innings: int | None = None,
                              event_age_hint: str | None = None,
                              event_type: str | None = None,
                              known_batsman_handed: str = "unknown",
                              known_bowling_arm: str = "unknown",
                              ) -> dict | None:
        """Classify the last delivery.

        Default (Gemini) path:
            DeliveryWindowRecorder owns the Scout-triggered window;
            this method just consumes the in-flight or cached result
            and merges runs/speed/event metadata.

        Legacy paths (USE_LEGACY_VLM=1 or USE_TRAJECTORY_ANALYSIS=1):
            falls through to the prior Scout-3-frame VLM / trajectory
            implementation below.

        Args:
            runs: score delta for this delivery.
            speed_kph: ball speed if available from broadcast.
            over_number: current over as float (e.g. 7.3).
            innings: current innings (1 or 2).
            event_age_hint: "older" for extras detected from a multi-event
                diff — shifts the legacy buffer slice to [T-30s, T-15s].
            event_type: ScoreManager event label (DOT/RUNS/FOUR/SIX/...)
        """
        self._last_speed_kph = speed_kph
        if not self.alive:
            return None

        # ── Gemini path (default) ────────────────────────────────
        if (self._recorder is not None and self._gemini_clf is not None
                and not USE_TRAJECTORY_ANALYSIS and not USE_LEGACY_VLM):
            self._delivery_count += 1
            dnum = self._delivery_count
            inn = innings if innings is not None else self._current_innings
            event_ts = time.time()
            delivery_dir = self._delivery_folder()
            return self._run_gemini_delivery_analysis(
                runs=runs, speed_kph=speed_kph,
                over_number=over_number, innings=inn,
                event_type=event_type, event_ts=event_ts,
                delivery_num=dnum, delivery_dir=delivery_dir,
                known_batsman_handed=known_batsman_handed,
                known_bowling_arm=known_bowling_arm)

        # ── Legacy paths fall through ────────────────────────────
        self._delivery_count += 1
        dnum = self._delivery_count
        inn = innings if innings is not None else self._current_innings
        over_int = int(over_number) if over_number is not None else None

        # Buffer source: prefer DRS frozen snapshot if one exists (the
        # original delivery is in there, the live buffer has the review).
        # Snapshot is single-use — consumed here so all return paths
        # naturally clear it.  Snapshots older than 120s are discarded
        # as a safety net (DRS reviews almost never run that long).
        _DRS_SNAPSHOT_TTL_S = 120.0
        if (self._drs_frozen_snapshot is not None
                and self._drs_freeze_at is not None
                and time.time() - self._drs_freeze_at > _DRS_SNAPSHOT_TTL_S):
            log.warning(f"  [D#{dnum}] DRS snapshot stale "
                        f"({time.time() - self._drs_freeze_at:.0f}s) — "
                        f"discarding")
            self._drs_frozen_snapshot = None
            self._drs_freeze_at = None

        if self._drs_frozen_snapshot is not None:
            buffer_snapshot = self._drs_frozen_snapshot
            now = self._drs_freeze_at or time.time()
            _src = "drs_frozen"
            log.info(f"  [D#{dnum}] Using DRS frozen snapshot "
                     f"({len(buffer_snapshot)} frames, frozen "
                     f"{time.time() - now:.0f}s ago)")
            self._drs_frozen_snapshot = None
            self._drs_freeze_at = None
        else:
            buffer_snapshot = list(self._frame_buffer)
            now = time.time()
            _src = "live"

        # Temporal slice window:
        #   default       → [T-15s, T-2s]
        #   wicket/4/6    → [T-15s, T-1s] (broadcast cuts to celebration
        #                   within ~1s on exciting events; the standard
        #                   2s cutoff loses the contact frames)
        #   extras hint   → [T-30s, T-15s] (older event from multi-diff)
        if event_age_hint == "older":
            _window_lo, _window_hi = 30, 15
        elif event_type in ("WICKET", "FOUR", "SIX") or runs in (4, 6):
            _window_lo, _window_hi = 15, 1
        else:
            _window_lo, _window_hi = 15, 2
        temporal_slice = [(t, f) for t, f in buffer_snapshot
                          if now - _window_lo <= t <= now - _window_hi]

        self._last_buf_stats = {
            "buffer_total": len(buffer_snapshot),
            "temporal_slice": len(temporal_slice),
            "window": f"T-{_window_lo}..T-{_window_hi}",
            "source": _src,
        }

        log.info(f"  [D#{dnum}] Buffer: {len(buffer_snapshot)} frames, "
                 f"slice [{_window_lo},{_window_hi}]: "
                 f"{len(temporal_slice)} frames")

        if len(temporal_slice) < 3:
            log.warning(f"  [D#{dnum}] Too few frames in temporal slice")
            self._save_failed([], runs, speed_kph, "buffer_empty",
                              extra=self._last_buf_stats)
            result = _unknown_result(runs, skip_reason="buffer_empty")
            result["_method"] = "moondream"
            result["_buffer_stats"] = self._last_buf_stats
            return result

        # ── Source: Scout-tagged bowlers_end buffer, sliced by phase
        #    (2026-04-19 v3 — phase-aware selection).
        #
        # Background: Scout's existing camera_view tag is 97% accurate
        # at identifying the bowler's-end camera, but the camera holds
        # for several seconds AFTER the action — a delivery hit for
        # four shows the bowler's end during runup → release → flight
        # → contact → 3-4 s of post-action dwell, all tagged
        # bowlers_end.  Selecting the LAST N tagged frames biased
        # toward post-action celebration / fielder retrieval, hurting
        # length/line classification.
        #
        # Fix: extended Scout's prompt with `frame_phase`
        # (release / flight / shot / post_shot / runup / between_play
        # /...).  Validation on 115 frames from 31 confirmed deliveries
        # showed 100% of deliveries get >=1 release/flight/shot frame
        # — so we can sample the moment-of-action directly.
        #
        # Selection priority (per-delivery):
        #   1. release / flight / shot   — true delivery moment
        #   2. post_shot                 — fallback when broadcast
        #                                  cuts away mid-delivery
        #   3. any bowlers_end (no phase) — back-compat / phase tag
        #                                   missing from old frames
        narrow_ms = 0.0
        _TAG_MAX_AGE_S = float(
            os.environ.get("TAG_MAX_AGE_S", str(float(_window_lo))))
        _tag_lo = now - _TAG_MAX_AGE_S
        _tag_hi = now - float(_window_hi)
        action_phases = ("release", "flight", "shot")
        post_phases = ("post_shot",)
        action_tagged = self._snapshot_tagged(
            _tag_lo, _tag_hi,
            views=("bowlers_end",), phases=action_phases)
        post_tagged = self._snapshot_tagged(
            _tag_lo, _tag_hi,
            views=("bowlers_end",), phases=post_phases)
        any_tagged = self._snapshot_tagged(
            _tag_lo, _tag_hi, views=("bowlers_end",))

        if len(action_tagged) >= 2:
            tagged = action_tagged
            phase_source = "action"
        elif (len(action_tagged) + len(post_tagged)) >= 2:
            # Mix: keep all action frames + top up with post_shot.
            tagged = action_tagged + post_tagged
            phase_source = "action+post_shot"
        elif len(post_tagged) >= 2:
            tagged = post_tagged
            phase_source = "post_shot_only"
        elif len(any_tagged) >= 2:
            # Last-resort: phase tag missing or all between_play /
            # runup.  Use whatever bowlers_end frames we have.
            tagged = any_tagged
            phase_source = "bowlers_end_any"
        else:
            tagged = any_tagged
            phase_source = "none"

        phase_breakdown = {
            "action_release_flight_shot": len(action_tagged),
            "post_shot": len(post_tagged),
            "any_bowlers_end": len(any_tagged),
        }
        burst_info = {
            "tagged_count": len(tagged),
            "tag_window": f"T-{_TAG_MAX_AGE_S:.0f}..T-{_window_hi}",
            "buffer_total_tagged": len(self._tagged_buffer),
            "phase_source": phase_source,
            "phase_breakdown": phase_breakdown,
        }

        if len(tagged) < 2:
            log.warning(
                f"  [D#{dnum}] No bowlers_end-tagged frames within "
                f"{_TAG_MAX_AGE_S:.0f}s "
                f"(buffer_total_tagged={burst_info['buffer_total_tagged']}) "
                f"— broadcast did not show this delivery on the "
                f"bowler's-end camera; returning unknown")
            self._save_failed([], runs, speed_kph, "no_tagged_bowlers_end",
                              extra={**self._last_buf_stats,
                                     "burst_info": burst_info})
            result = _unknown_result(
                runs, skip_reason="no_tagged_bowlers_end")
            result["_method"] = "vlm"
            result["_buffer_stats"] = self._last_buf_stats
            result["_frames_source"] = "none"
            result["_burst_info"] = burst_info
            self._persist_predictions_summary(
                runs, speed_kph, result, dnum)
            return result

        # Selection rule depends on phase_source:
        #   * action: take all action frames (release/flight/shot),
        #     up to VLM_FRAMES_PER_DELIVERY.  These are THE delivery
        #     moment — order within doesn't matter, all are useful.
        #   * action+post_shot: action frames first, then top up with
        #     EARLIEST post_shot frames (closest to the action).
        #     Gives Scout the moment of release plus the immediate
        #     aftermath — useful for shot direction and reaction.
        #   * post_shot_only (D#11-style case): all post_shot frames.
        #     Live run will show whether Scout returns useful partial
        #     classifications (e.g. shot direction yes, length no) or
        #     all-unknown.  If all-unknown, demote to skip in next
        #     iteration.
        #   * bowlers_end_any: back-compat path for frames buffered
        #     before the phase prompt rolled out (phase=None) — also
        #     fires when Scout only tagged runup/between_play.  Take
        #     the EARLIEST N as those are closer to the action than
        #     the post-event camera dwell.
        for t in (action_tagged, post_tagged, any_tagged, tagged):
            t.sort(key=lambda x: x[0])
        if phase_source == "action":
            picks = action_tagged[:VLM_FRAMES_PER_DELIVERY]
        elif phase_source == "action+post_shot":
            picks = action_tagged[:VLM_FRAMES_PER_DELIVERY]
            remaining = VLM_FRAMES_PER_DELIVERY - len(picks)
            if remaining > 0:
                picks = picks + post_tagged[:remaining]
        elif phase_source == "post_shot_only":
            picks = post_tagged[:VLM_FRAMES_PER_DELIVERY]
        else:  # bowlers_end_any (back-compat / no useful phase)
            picks = tagged[:VLM_FRAMES_PER_DELIVERY]
        picks.sort(key=lambda x: x[0])
        n_take = len(picks)
        del_frames = [f for _, f, _, _ in picks]
        timestamps = [ts for ts, _, _, _ in picks]
        pick_phases = [p for _, _, _, p in picks]
        _frames_source = f"tagged_bowlers_end:{phase_source}"
        log.info(
            f"  [D#{dnum}] Using {_frames_source} "
            f"n={n_take} (action={phase_breakdown['action_release_flight_shot']} "
            f"post={phase_breakdown['post_shot']} "
            f"any={phase_breakdown['any_bowlers_end']}) "
            f"phases={pick_phases} "
            f"window={burst_info['tag_window']} "
            f"buffer_total_tagged={burst_info['buffer_total_tagged']}")

        # Strip letterbox borders (cosmetic; Scout doesn't care but
        # smaller payload = faster)
        if del_frames:
            vx, vy, vw, vh = find_video_region(
                del_frames[len(del_frames) // 2])
            if vx > 0 or vy > 0:
                del_frames = [f[vy:vy + vh, vx:vx + vw] for f in del_frames]

        # ── Parallel: Moondream(1 frame) || Scout VLM ───────────────
        # Moondream is OPTIONAL enrichment — runs on a single best frame
        # to extract stump_cx for line refinement.  We launch it in
        # parallel with Scout so it doesn't add to wall time
        # (Scout ~1.5s, Moondream(1) ~2.5s → total ≈ 2.5s).
        from concurrent.futures import ThreadPoolExecutor

        if USE_TRAJECTORY_ANALYSIS:
            # Legacy path needs grounded frames for trajectory math.
            # Fall back to old behaviour when explicitly enabled.
            grounded = ground_pitch_in_frames(
                temporal_slice, is_wide_fn=is_wide_shot)
            if len(grounded) < 5:
                result = _unknown_result(runs,
                                         skip_reason="trajectory_insufficient")
                result["_method"] = "trajectory"
                return result
            tdel_frames = [bgr for _, bgr, _ in grounded]
            ttimestamps = [ts for ts, _, _ in grounded]
            pitch_box = grounded[0][2]
            vx, vy, vw, vh = find_video_region(
                tdel_frames[len(tdel_frames) // 2])
            if vx > 0 or vy > 0:
                tdel_frames = [f[vy:vy + vh, vx:vx + vw] for f in tdel_frames]
                pitch_box = PitchBox(x=pitch_box.x - vx, y=pitch_box.y - vy,
                                     w=pitch_box.w, h=pitch_box.h)
            self._save_delivery_frames(tdel_frames, runs, speed_kph,
                                       pitch_box=pitch_box,
                                       buffer_stats=self._last_buf_stats,
                                       grounding_ms=0)
            result = self._classify_delivery(
                tdel_frames, ttimestamps, 0, runs, pitch_box=pitch_box)
            result["_method"] = "trajectory"
            result["_buffer_stats"] = self._last_buf_stats
            return result

        # VLM path — submit Scout + Moondream(1) in parallel
        if not del_frames:
            log.warning(f"  [D#{dnum}] No frames at all — score-only result")
            self._save_failed([], runs, speed_kph, "no_frames",
                              extra=self._last_buf_stats)
            result = _unknown_result(runs, skip_reason="no_frames")
            result["_method"] = "vlm"
            result["_buffer_stats"] = self._last_buf_stats
            return result

        # 2026-04-18: Scout's semantic line classification supplants
        # Moondream's geometric stump_cx for the per-delivery path.
        # Default path (USE_VLM_GROUNDING=0): call Scout synchronously
        # — no thread pool, no Moondream, no JIT contention.  Opt-in
        # path (USE_VLM_GROUNDING=1): keep the parallel enrichment
        # for offline calibration / debugging.
        pitch_box = None
        t_par = time.time()
        if USE_VLM_GROUNDING:
            moondream_frame = del_frames[len(del_frames) // 2]
            with ThreadPoolExecutor(max_workers=2) as pool:
                scout_fut = pool.submit(
                    self._vlm.classify,
                    del_frames, runs, speed_kph,
                    VLM_FRAMES_PER_DELIVERY,
                )
                moon_fut = pool.submit(
                    _ground_single_frame_safe, moondream_frame)

                try:
                    result = scout_fut.result(timeout=15.0)
                except Exception as e:
                    log.warning(f"  [D#{dnum}] Scout error: {e}")
                    result = _unknown_result(runs,
                                             skip_reason="vlm_error")
                    result["_method"] = "vlm"

                try:
                    pitch_box = moon_fut.result(timeout=8.0)
                except Exception as e:
                    log.info(f"  [D#{dnum}] Moondream optional call "
                             f"error (non-fatal): {e}")
                    pitch_box = None
        else:
            try:
                _save_dir = self._delivery_folder()
                result = self._vlm.classify(
                    del_frames, runs, speed_kph,
                    VLM_FRAMES_PER_DELIVERY,
                    save_dir=_save_dir,
                )
            except Exception as e:
                log.warning(f"  [D#{dnum}] Scout error: {e}")
                result = _unknown_result(runs, skip_reason="vlm_error")
                result["_method"] = "vlm"
        par_ms = (time.time() - t_par) * 1000

        # Merge: Scout classification + optional stump position
        if pitch_box is not None:
            result["_stump_cx"] = pitch_box.x + pitch_box.w // 2
            result["_pitch_box"] = {"x": pitch_box.x, "y": pitch_box.y,
                                    "w": pitch_box.w, "h": pitch_box.h}
            result["_moondream_grounded"] = True
        else:
            result["_moondream_grounded"] = False

        result["_vlm_wall_ms"] = round(par_ms)
        result["_frames_source"] = _frames_source
        result["_narrow_ms"] = round(narrow_ms)
        result["_burst_info"] = burst_info
        self._last_buf_stats["burst_info"] = burst_info
        self._last_buf_stats["frames_source"] = _frames_source

        # Soft-reject all-unknown Scout responses (2026-04-19).
        # When the burst was a false positive (e.g. fielder-catch
        # silhouette tricking is_delivery_frame), Scout correctly
        # returns "unknown" for every classification field with low
        # confidence — that IS the false-positive filter (per
        # Direction 2: trust Scout to reject what it can't see).  But
        # without this guard such results would still overwrite
        # `_last_delivery_info` on the UI/commentary side, replacing
        # the previous good classification with all-blanks.  Mark them
        # untrackable so the downstream logic preserves the last known
        # state instead.
        if not result.get("_untrackable"):
            _key_fields = (result.get("bowling_angle"),
                           result.get("length"),
                           result.get("line"))
            _all_unknown = all(
                str(v).lower() in ("unknown", "none", "")
                for v in _key_fields)
            _low_conf = (str(result.get("_vlm_confidence", "")).lower()
                         == "low")
            if _all_unknown and _low_conf:
                log.info(
                    f"  [D#{dnum}] Soft-rejecting all-unknown "
                    f"low-confidence Scout result "
                    f"(burst likely false positive); "
                    f"preserving last delivery_info on UI")
                result["_untrackable"] = True
                result["_skip_reason"] = "vlm_all_unknown"
        self._log_vlm_result(dnum, result)

        # Persist frames for offline review (after classification, so
        # the saved metadata can include the result)
        self._save_delivery_frames(del_frames, runs, speed_kph,
                                   pitch_box=pitch_box,
                                   buffer_stats=self._last_buf_stats,
                                   grounding_ms=0)

        result["_buffer_stats"] = self._last_buf_stats
        result["_grounding_ms"] = 0  # decoupled; tracked via _moondream_grounded
        result["_roi_cache_hit"] = False
        result["_session"] = self._session_id

        self._persist_vlm_record(runs, speed_kph, result)
        self._persist_predictions_summary(runs, speed_kph, result, dnum)

        return result

    @staticmethod
    def _log_gemini_result(dnum: int, r: dict) -> None:
        if r.get("_untrackable"):
            log.info(f"  [D#{dnum}] GEMINI REJECT: "
                     f"{r.get('_skip_reason','?')} "
                     f"window_dur={r.get('_window_dur_s','?')}s "
                     f"frames={r.get('_window_frames','?')}")
            return
        sd = r.get("shot_direction", {})
        log.info(
            f"  [D#{dnum}] GEMINI OK ({r.get('_gemini_ms','?')}ms): "
            f"hand={r.get('batsman_handed','?')} "
            f"arm={r.get('bowling_arm','?')} "
            f"type={r.get('bowling_type','?')}/{r.get('bowling_angle','?')} "
            f"len={r.get('length','?')} line={r.get('line','?')} "
            f"bounce={r.get('bounce','?')} "
            f"shot={r.get('shot_action','?')} "
            f"({sd.get('side','?')}/{sd.get('zone','?')}, "
            f"{r.get('shot_elevation','?')}) "
            f"contact={r.get('contact_quality','?')} "
            f"conf={r.get('_gemini_confidence','?')} "
            f"window={r.get('_window_dur_s','?')}s/"
            f"{r.get('_window_frames','?')}f "
            f"reason={r.get('_window_reason','?')}")
        if r.get("commentary_line"):
            log.info(f"  >> {r['commentary_line']}")
        if r.get("narrative"):
            log.info(f"  ~~ {r['narrative']}")

    @staticmethod
    def _log_vlm_result(dnum: int, r: dict) -> None:
        if r.get("_untrackable"):
            log.info(f"  [D#{dnum}] VLM REJECT: {r.get('_skip_reason','?')} "
                     f"({r.get('_vlm_ms','?')}ms, "
                     f"conf={r.get('_vlm_confidence','?')})")
        else:
            sd = r.get("shot_direction", {})
            log.info(
                f"  [D#{dnum}] VLM OK ({r.get('_vlm_ms','?')}ms): "
                f"{r.get('bowling_angle','?')}/{r.get('length','?')}/"
                f"{r.get('line','?')} — "
                f"{r.get('shot_action','?')} "
                f"({sd.get('zone','?')}, {r.get('shot_elevation','?')}) "
                f"swing={r.get('swing_or_seam','?')} "
                f"speed={r.get('ball_speed_kph_vlm') or '?'} "
                f"conf={r.get('_vlm_confidence','?')}")
            log.info(f"  >> {r.get('commentary_line','')}")

    # ── Classification ──────────────────────────────────────────────

    def _classify_delivery(
        self,
        del_frames: list[np.ndarray],
        timestamps: list[float],
        win_start: int,
        runs: int,
        pitch_box: PitchBox | None = None,
    ) -> dict:
        h, w = del_frames[0].shape[:2]

        if pitch_box:
            px, py, pw, ph = pitch_box.x, pitch_box.y, pitch_box.w, pitch_box.h
        else:
            px, py = int(w * 0.15), int(h * 0.05)
            pw, ph = int(w * 0.55), int(h * 0.65)

        min_h = int(h * 0.40)
        if ph < min_h:
            extra = min_h - ph
            py = max(0, py - int(extra * 0.65))
            ph = min(h - py, ph + extra)

        detections: list[dict] = []
        for i in range(len(del_frames) - 1):
            prev_crop = del_frames[i][py:py + ph, px:px + pw]
            curr_crop = del_frames[i + 1][py:py + ph, px:px + pw]
            candidates = detect_white_ball(prev_crop, curr_crop, threshold=25)
            if candidates:
                best = candidates[0]
                detections.append({
                    "frame": i + 1,
                    "x": best["x"], "y": best["y"],
                    "area": best["area"],
                    "timestamp": timestamps[min(win_start + i + 1,
                                                len(timestamps) - 1)],
                })

        log.info(f"Delivery #{self._delivery_count}: "
                 f"{len(detections)}/{len(del_frames)-1} detections, "
                 f"crop=({px},{py},{pw},{ph})")

        if detections:
            _det_coords = [(d["frame"], d["x"], d["y"], d["area"])
                           for d in detections]
            log.info(f"  [DETS] {_det_coords}")

        if len(detections) < 2:
            self._save_failed(del_frames, runs,
                              getattr(self, '_last_speed_kph', None),
                              "insufficient_detections",
                              extra={"num_detections": len(detections),
                                     "crop": {"x": px, "y": py,
                                              "w": pw, "h": ph}})
            return _unknown_result(runs, skip_reason="too_few_detections")

        # ── Trajectory validation (pre-phase) ─────────────────────
        if len(detections) >= 3:
            _traj_ys = [d["y"] for d in detections]
            _traj_xs = [d["x"] for d in detections]
            _y_range = max(_traj_ys) - min(_traj_ys)
            _x_range = max(_traj_xs) - min(_traj_xs)

            if _y_range < ph * 0.05 and _x_range < pw * 0.05:
                log.info(f"  [TRAJ-REJECT] Static detections: "
                         f"y_range={_y_range} x_range={_x_range}")
                self._save_failed(del_frames, runs,
                                  getattr(self, '_last_speed_kph', None),
                                  "trajectory_static",
                                  extra={"y_range": _y_range,
                                         "x_range": _x_range})
                return _unknown_result(runs, skip_reason="too_few_detections")

            if _y_range < ph * 0.10 and _x_range > _y_range * 2:
                log.info(
                    f"  [TRAJ-REJECT] Horizontal movement: "
                    f"y_range={_y_range} ({_y_range/ph*100:.0f}% of pitch) "
                    f"x_range={_x_range}")
                self._save_failed(del_frames, runs,
                                  getattr(self, '_last_speed_kph', None),
                                  "trajectory_horizontal",
                                  extra={"y_range": _y_range,
                                         "x_range": _x_range})
                return _unknown_result(runs, skip_reason="too_few_detections")

        phases = separate_phases(detections, ph)
        flight = phases.get("flight", [])
        bp = phases.get("bounce_point")

        log.info(f"  [PHASES] flight={len(flight)} bounce={'yes' if bp else 'no'} "
                 f"post_shot={len(phases.get('post_shot', []))} "
                 f"gap={phases.get('gap_frames')}")

        # ── Trajectory validation (post-phase): flight must progress
        # top-to-bottom (y increasing from bowler toward batsman)
        if len(flight) >= 3:
            _fly_y_first = flight[0]["y"]
            _fly_y_last = flight[-1]["y"]
            _fly_y_range = max(d["y"] for d in flight) - min(d["y"] for d in flight)
            if _fly_y_last <= _fly_y_first and _fly_y_range < ph * 0.08:
                log.info(
                    f"  [TRAJ-REJECT] Flight not progressing downward: "
                    f"y_first={_fly_y_first} y_last={_fly_y_last} "
                    f"range={_fly_y_range}")
                self._save_failed(del_frames, runs,
                                  getattr(self, '_last_speed_kph', None),
                                  "trajectory_no_progression",
                                  extra={"flight_y_first": _fly_y_first,
                                         "flight_y_last": _fly_y_last,
                                         "flight_y_range": _fly_y_range})
                return _unknown_result(runs, skip_reason="too_few_detections")

        # Pitch ROI center-x is the best available proxy for stump line.
        # When using Moondream box, ROI center IS the pitch center.
        center_in_crop = pw // 2

        # With Moondream ROI, the box height IS the pitch length
        pitch_length = ph
        pitch_top_in_crop = 0

        last_flight = flight[-1] if len(flight) >= 2 else None

        cl: dict = {}
        cl["bowling_angle"] = (
            classify_bowling_angle(flight[0]["x"], center_in_crop)
            if len(flight) >= 2 else "unknown")
        if bp:
            cl["length"] = classify_length(
                bp["y"], pitch_length or ph,
                pitch_top=pitch_top_in_crop,
                speed_kph=getattr(self, '_last_speed_kph', None))
        elif len(flight) >= 6 and _is_full_toss_trajectory(flight):
            cl["length"] = "full_toss"
        else:
            cl["length"] = "unknown"
        cl["line"] = (
            classify_line(last_flight["x"], pw,
                          center_x=center_in_crop)
            if last_flight else "unknown")
        cl["bounce"] = (classify_bounce(flight, bp)
                        if bp and len(flight) >= 3 else "normal")

        post_shot = phases.get("post_shot", [])
        if len(post_shot) >= 2:
            batter_pos = (pw // 2, int(ph * 0.85))
            dir_result = classify_shot_direction(batter_pos, post_shot)
            cl["shot_direction"] = dir_result
            cl["shot_elevation"] = classify_shot_elevation(post_shot)
            cl["shot_type"] = cl["shot_elevation"]
        else:
            cl["shot_type"] = _shot_type_from_runs(runs)
            cl["shot_elevation"] = cl["shot_type"]
            cl["shot_direction"] = infer_shot_direction_from_context(
                cl.get("line", "unknown"), cl["shot_type"], runs)

        cl["runs"] = runs
        cl["commentary_line"] = build_commentary_line(cl)
        cl["detections"] = len(detections)
        cl["detection_rate"] = len(detections) / max(1, len(del_frames) - 1)

        _offset_frac = ((last_flight["x"] - center_in_crop) / (pw / 2)
                        if last_flight and pw > 0 else 0)
        _len_frac = ((bp["y"] - pitch_top_in_crop)
                     / (pitch_length or ph)
                     if bp and (pitch_length or ph) > 0 else 0)
        _bp_str = f"({bp['x']},{bp['y']})" if bp else "None"
        _lf_str = (f"({last_flight['x']},{last_flight['y']})"
                   if last_flight else "None")
        _dir_side = cl["shot_direction"].get("side", "?")
        _elev = cl["shot_elevation"]
        log.info(
            f"  [CLASSIFY] crop=({px},{py},{pw},{ph}) "
            f"center={center_in_crop} pitch_len={pitch_length or 'crop'} "
            f"bounce={_bp_str} last_flight={_lf_str} "
            f"offset={_offset_frac:.3f} len_frac={_len_frac:.3f} "
            f"post_shot={len(post_shot)} "
            f"→ {cl['length']}/{cl['line']}/{cl['bowling_angle']}"
            f"/{_dir_side}/{_elev}")
        log.info(f"  >> {cl['commentary_line']}")

        # Persist raw features for classifier calibration
        _raw = {
            "delivery_num": self._delivery_count,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "crop": {"x": px, "y": py, "w": pw, "h": ph},
            "pitch_length": pitch_length,
            "pitch_top_in_crop": pitch_top_in_crop,
            "center_in_crop": center_in_crop,
            "bounce_point": ({"x": bp["x"], "y": bp["y"],
                              "frame": bp["frame"],
                              "area": bp.get("area", 0)}
                             if bp else None),
            "last_flight_point": ({"x": last_flight["x"],
                                   "y": last_flight["y"]}
                                  if last_flight else None),
            "first_flight_point": ({"x": flight[0]["x"],
                                    "y": flight[0]["y"]}
                                   if len(flight) >= 2 else None),
            "flight_points": [{"x": d["x"], "y": d["y"],
                               "frame": d["frame"],
                               "area": d.get("area", 0)}
                              for d in flight],
            "post_shot_points": [{"x": d["x"], "y": d["y"],
                                  "frame": d["frame"],
                                  "area": d.get("area", 0)}
                                 for d in post_shot],
            "num_detections": len(detections),
            "num_flight": len(flight),
            "num_post_shot": len(post_shot),
            "contact_frame_idx": (phases["gap_frames"][0]
                                  if phases.get("gap_frames") else None),
            "gap_frames": list(phases["gap_frames"])
                          if phases.get("gap_frames") else None,
            "offset_frac": round(_offset_frac, 4),
            "len_frac": round(_len_frac, 4),
            "speed_kph": getattr(self, '_last_speed_kph', None),
            "runs": runs,
            "buffer_stats": getattr(self, '_last_buf_stats', {}),
            "predicted": {
                "bowling_angle": cl["bowling_angle"],
                "length": cl["length"],
                "line": cl["line"],
                "bounce": cl["bounce"],
                "shot_elevation": cl["shot_elevation"],
                "shot_direction_side": cl["shot_direction"].get("side"),
                "shot_direction_zone": cl["shot_direction"].get("zone"),
                "shot_direction_angle": cl["shot_direction"].get(
                    "angle_degrees"),
                "shot_direction_conf": cl["shot_direction"].get(
                    "confidence"),
            },
        }
        try:
            import json as _json, os as _os
            _dir = _os.path.join(_os.path.dirname(__file__),
                                 "logs", "deliveries")
            _os.makedirs(_dir, exist_ok=True)
            _path = _os.path.join(_dir, "raw_features.jsonl")
            with open(_path, "a") as _f:
                _f.write(_json.dumps(_raw) + "\n")
        except Exception as _e:
            log.warning(f"Could not persist delivery features: {_e}")

        # Save annotated trajectory frames for trajectory mode only
        # (VLM mode handles frame saving in _save_delivery_frames)
        if USE_TRAJECTORY_ANALYSIS:
            self._save_trajectory_annotation(
                del_frames, bp, flight, post_shot,
                px, py, pw, ph, center_in_crop)

        return cl

    def _save_trajectory_annotation(self, del_frames, bp, flight, post_shot,
                                    px, py, pw, ph, center_in_crop):
        """Save trajectory-annotated pitch crop (legacy trajectory mode)."""
        try:
            _fdir = self._delivery_folder()
            _key_idx = bp["frame"] if bp else len(del_frames) // 2
            _key_idx = min(_key_idx, len(del_frames) - 1)
            _annot = del_frames[_key_idx][py:py+ph, px:px+pw].copy()
            for _d in flight:
                cv2.circle(_annot, (_d["x"], _d["y"]), 4, (0, 255, 0), -1)
            if bp:
                cv2.circle(_annot, (bp["x"], bp["y"]), 6, (0, 0, 255), -1)
            for _d in post_shot:
                cv2.circle(_annot, (_d["x"], _d["y"]), 4, (255, 0, 0), -1)
            if center_in_crop > 0:
                cv2.line(_annot, (center_in_crop, 0),
                         (center_in_crop, ph), (255, 255, 0), 1)
            cv2.imwrite(os.path.join(_fdir, "pitch_annotated.jpg"), _annot)
        except Exception as _e:
            log.warning(f"Could not save trajectory annotation: {_e}")

    # ── Per-delivery folder + frame saving (session-prefixed) ────────

    def _delivery_folder(self) -> str:
        """Return the session-scoped folder for the current delivery.

        Folder name: ``logs/deliveries/<session>/d<NNN>``.  Session prefix
        prevents pipeline restarts from clobbering prior runs' frames.
        """
        base = os.path.join(os.path.dirname(__file__), "logs", "deliveries",
                            self._session_id)
        fdir = os.path.join(base, f"d{self._delivery_count:03d}")
        os.makedirs(fdir, exist_ok=True)
        return fdir

    def _save_delivery_frames(self, del_frames: list[np.ndarray],
                              runs: int, speed_kph: float | None,
                              pitch_box: PitchBox | None,
                              buffer_stats: dict,
                              grounding_ms: float):
        """Save N evenly-spaced frames + metadata for offline labeling."""
        if not del_frames:
            return
        try:
            fdir = self._delivery_folder()
            n_save = max(1, min(SAVE_FRAMES_PER_DELIVERY, len(del_frames)))
            if n_save == 1:
                idxs = [len(del_frames) // 2]
            else:
                step = (len(del_frames) - 1) / (n_save - 1)
                idxs = [int(round(i * step)) for i in range(n_save)]
                seen: set[int] = set()
                idxs = [i for i in idxs if not (i in seen or seen.add(i))]
            for k, i in enumerate(idxs):
                cv2.imwrite(os.path.join(fdir, f"frame_{k:02d}.jpg"),
                            del_frames[i])
            mid = len(del_frames) // 2
            cv2.imwrite(os.path.join(fdir, "wide_shot.jpg"), del_frames[mid])

            meta = {
                "delivery_num": self._delivery_count,
                "session": self._session_id,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "runs": runs,
                "speed_kph": speed_kph,
                "n_frames_total": len(del_frames),
                "n_frames_saved": len(idxs),
                "saved_indices": idxs,
                "pitch_box": ({"x": pitch_box.x, "y": pitch_box.y,
                               "w": pitch_box.w, "h": pitch_box.h}
                              if pitch_box is not None else None),
                "buffer_stats": buffer_stats,
                "grounding_ms": round(grounding_ms),
            }
            import json as _json
            with open(os.path.join(fdir, "meta.json"), "w") as f:
                _json.dump(meta, f, indent=2)
            log.info(f"  [FRAMES] Saved {len(idxs)} frames "
                     f"(of {len(del_frames)}) to {fdir}")
        except Exception as e:
            log.warning(f"Could not save delivery frames: {e}")

    def _persist_vlm_record(self, runs: int, speed_kph: float | None,
                            result: dict):
        """Append a VLM classification record to raw_features.jsonl."""
        try:
            sd = result.get("shot_direction", {})
            rec = {
                "delivery_num": self._delivery_count,
                "session": self._session_id,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "method": "vlm",
                "runs": runs,
                "speed_kph": speed_kph,
                "status": result.get("_skip_reason"),  # None if accepted
                "vlm_ms": result.get("_vlm_ms"),
                "vlm_confidence": result.get("_vlm_confidence"),
                "buffer_stats": result.get("_buffer_stats", {}),
                "grounding_ms": result.get("_grounding_ms"),
                "predicted": {
                    "bowling_angle": result.get("bowling_angle"),
                    "length": result.get("length"),
                    "line": result.get("line"),
                    "pitch_position": result.get("pitch_position"),
                    "shot_action": result.get("shot_action"),
                    "shot_direction_zone": sd.get("zone"),
                    "shot_direction_side": sd.get("side"),
                    "shot_elevation": result.get("shot_elevation"),
                    "swing_or_seam": result.get("swing_or_seam"),
                    "ball_speed_visible": result.get("ball_speed_visible"),
                    "ball_speed_kph_vlm": result.get("ball_speed_kph_vlm"),
                },
                "commentary_line": result.get("commentary_line", ""),
            }
            _dir = os.path.join(os.path.dirname(__file__),
                                "logs", "deliveries")
            os.makedirs(_dir, exist_ok=True)
            import json as _json
            with open(os.path.join(_dir, "raw_features.jsonl"), "a") as f:
                f.write(_json.dumps(rec) + "\n")
        except Exception as e:
            log.warning(f"Could not persist VLM record: {e}")

    def _persist_predictions_summary(self, runs: int,
                                     speed_kph: float | None,
                                     result: dict, dnum: int) -> None:
        """Write the 10-component delivery prediction next to scout frames.

        Co-locates Scout's input (scout_pick_*.jpg) and output
        (predictions.json) so a human reviewer can flip through one folder
        per delivery and judge each prediction against the source frames.
        """
        try:
            sd = result.get("shot_direction", {}) or {}
            preds = {
                "delivery_num": dnum,
                "session": self._session_id,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "runs": runs,
                "broadcast_speed_kph": speed_kph,
                "components": {
                    "1_bowling_angle": result.get("bowling_angle"),
                    "2_length": result.get("length"),
                    "3_line": result.get("line"),
                    "4_shot_intent": result.get("shot_intent"),
                    "5_shot_action": result.get("shot_action"),
                    "6_shot_side": sd.get("side"),
                    "7_shot_zone": sd.get("zone"),
                    "8_elevation": result.get("shot_elevation"),
                    "9_swing_or_seam": result.get("swing_or_seam"),
                    "10_ball_speed_kph_vlm": result.get("ball_speed_kph_vlm"),
                },
                "commentary_line": result.get("commentary_line"),
                "vlm_confidence": result.get("_vlm_confidence"),
                "gemini_confidence": result.get("_gemini_confidence"),
                "gemini_raw": result.get("_gemini_raw"),
                "vlm_ms": result.get("_vlm_ms"),
                "gemini_ms": result.get("_gemini_ms"),
                "frames_source": result.get("_frames_source"),
                "window_source": result.get("_window_source"),
                "window_reason": result.get("_window_reason"),
                "window_dur_s": result.get("_window_dur_s"),
                "window_frames": result.get("_window_frames"),
                "window_start_ts": result.get("_window_start_ts"),
                "window_end_ts": result.get("_window_end_ts"),
                "event_type": result.get("_event_type"),
                "over_number": result.get("_over_number"),
                "innings": result.get("_innings"),
                "skip_reason": result.get("_skip_reason"),
                "untrackable": bool(result.get("_untrackable")),
            }
            import json as _json
            fdir = self._delivery_folder()
            with open(os.path.join(fdir, "predictions.json"), "w") as f:
                _json.dump(preds, f, indent=2)
        except Exception as e:
            log.warning(f"Could not persist predictions summary: {e}")

    # ── Diagnostic frame saving ──────────────────────────────────────

    def _save_failed(self, frames: list[np.ndarray], runs: int,
                     speed_kph: float | None, status: str,
                     extra: dict | None = None):
        try:
            _fdir = self._delivery_folder()
            if frames:
                # Save up to 8 evenly-spaced frames so a human reviewer can
                # see what the slice actually looked like — the previous
                # 3-frame save was too sparse to diagnose whether the
                # broadcast cut away or the narrowing filters were over-
                # zealous.
                n = len(frames)
                if n <= 8:
                    picks = list(range(n))
                else:
                    step = (n - 1) / 7
                    picks = [int(round(i * step)) for i in range(8)]
                for _i, _fi in enumerate(picks):
                    cv2.imwrite(
                        os.path.join(_fdir, f"failed_{_i:02d}.jpg"),
                        frames[_fi])
                # Keep the legacy start/mid/end aliases for tools that
                # still grep for them.
                _mid = n // 2
                for _label, _fi in [("start", 0), ("mid", _mid),
                                    ("end", n - 1)]:
                    if 0 <= _fi < n:
                        cv2.imwrite(
                            os.path.join(_fdir, f"failed_{_label}.jpg"),
                            frames[_fi])

            record = {
                "delivery_num": self._delivery_count,
                "session": self._session_id,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "method": "trajectory" if USE_TRAJECTORY_ANALYSIS else "vlm",
                "status": status,
                "speed_kph": speed_kph,
                "runs": runs,
                "buffer_stats": getattr(self, '_last_buf_stats', {}),
            }
            if extra:
                record.update(extra)
            import json as _json
            _dir = os.path.join(os.path.dirname(__file__),
                                "logs", "deliveries")
            with open(os.path.join(_dir, "raw_features.jsonl"), "a") as _f:
                _f.write(_json.dumps(record) + "\n")
        except Exception:
            pass

    # ── Background capture ────────────────────────────────────────────

    def _grab_full_frame_bgr(self) -> np.ndarray | None:
        """Latest broadcast frame as native BGR (H, W, 3) uint8.

        Pre-``_content_y`` trim. Backed by either Quartz CGWindowList
        (window mode) or cv2.VideoCapture (capture-card mode) per the
        ``FRAME_SOURCE`` env. Returns ``None`` if no frame is yet
        available — caller should retry.
        """
        if self._capture_card is not None:
            return self._capture_card.get_latest_bgr()
        if self._file_frame_source is not None:
            entry = self._file_frame_source.get_latest_with_ts()
            if entry is None:
                return None
            _ts, bgr = entry
            return bgr
        if CG is None:
            return None
        image = CG.CGWindowListCreateImage(
            CG.CGRectNull,
            CG.kCGWindowListOptionIncludingWindow,
            self._window_id,
            CG.kCGWindowImageBoundsIgnoreFraming,
        )
        if image is None:
            return None
        w = CG.CGImageGetWidth(image)
        h = CG.CGImageGetHeight(image)
        if w == 0 or h == 0:
            return None
        bpr = CG.CGImageGetBytesPerRow(image)
        data = CG.CGDataProviderCopyData(CG.CGImageGetDataProvider(image))
        arr = np.frombuffer(data, dtype=np.uint8).reshape((h, bpr // 4, 4))
        return arr[:h, :w, :3]

    def _capture_loop(self):
        t_start = time.time()
        last_seen_capture_count = -1
        try:
            while self._running:
                # Capture-card path: skip iterations where the underlying
                # frame slot hasn't advanced since the last append.  Without
                # this gate the loop polls faster than the device produces
                # frames and appends 4-10× duplicates per real frame, which
                # inflates compile_frames_to_mp4's inferred fps and breaks
                # playback timing.  See files/docs/investigations/
                # slow_motion_clip_playback_root_cause.md.
                if self._capture_card is not None:
                    cnt = self._capture_card.get_frame_count()
                    if cnt == last_seen_capture_count:
                        time.sleep(0.005)
                        continue
                    last_seen_capture_count = cnt
                elif self._file_frame_source is not None:
                    cnt = self._file_frame_source.get_frame_count()
                    if cnt == last_seen_capture_count:
                        time.sleep(0.005)
                        continue
                    last_seen_capture_count = cnt

                raw_bgr = self._grab_full_frame_bgr()
                if raw_bgr is None:
                    time.sleep(0.01)
                    continue

                h, w = raw_bgr.shape[:2]
                if w == 0 or h == 0:
                    time.sleep(0.01)
                    continue

                # Legacy Quartz path historically wrote pixel bytes in
                # RGB order into a variable named `bgr` (the trailing
                # `[:, :, ::-1]` flip on BGRA-in-memory data). Default
                # behaviour preserves that swap so HSV thresholds and
                # vision-API JPEG encodings keep matching what
                # consumers were tuned against. Set FRAME_COLOR_TRUE_BGR=1
                # to ship true BGR — see operations doc for the
                # required consumer re-tuning.
                cropped = raw_bgr[self._content_y:h, :w, :]
                bgr = (cropped.copy() if FRAME_COLOR_TRUE_BGR
                       else cropped[:, :, ::-1].copy())

                self._frames_read += 1
                now = time.time()

                # 2026-04-20: ALWAYS buffer.  Previously gated on
                # is_wide_shot, which dropped ~60% of frames during
                # post-boundary celebrations, replays, and crowd
                # cuts — meaning windows that closed across those
                # cuts ended up with only the tail of the action and
                # the bounce moment frequently missing.  is_wide_shot
                # is a consumption-time filter (apply when SELECTING
                # frames for a window), not a capture-time gate.
                if bgr.shape[1] > BUFFER_FRAME_WIDTH:
                    scale = BUFFER_FRAME_WIDTH / bgr.shape[1]
                    new_h = int(bgr.shape[0] * scale)
                    bgr = cv2.resize(bgr, (BUFFER_FRAME_WIDTH, new_h),
                                     interpolation=cv2.INTER_AREA)
                self._frame_buffer.append((now, bgr))
                self._frame_buffer_raw.append((now, raw_bgr.copy()))
                self._buf_count += 1

                # Per-frame is_delivery_frame + DeliveryBurstTracker
                # remain deprecated (Scout's camera_view tag has 97%
                # recall vs ~30% for the heuristic).  See
                # `_tagged_buffer` for the primary burst signal.

                elapsed = time.time() - t_start
                if elapsed > 0:
                    self._actual_fps = self._frames_read / elapsed

                if now - self._burst_last_log >= 30:
                    self._burst_last_log = now
                    with self._tagged_lock:
                        _tag_n = len(self._tagged_buffer)
                        _tag_be = 0
                        _phase_action = 0
                        _phase_post = 0
                        _phase_other = 0
                        _phase_none = 0
                        for _, _, v, p in self._tagged_buffer:
                            if v == "bowlers_end":
                                _tag_be += 1
                            if p in ("release", "flight", "shot"):
                                _phase_action += 1
                            elif p == "post_shot":
                                _phase_post += 1
                            elif p is None:
                                _phase_none += 1
                            else:
                                _phase_other += 1
                    log.info(
                        f"  [TAGS] tagged_buffer={_tag_n} "
                        f"bowlers_end={_tag_be} "
                        f"phases(action={_phase_action} "
                        f"post={_phase_post} "
                        f"other={_phase_other} "
                        f"none={_phase_none})")
        except Exception:
            import traceback
            log.error(f"Capture loop error: {traceback.format_exc()}")
            self._running = False

    def _detect_content_top(self) -> int:
        # Capture-card path may not have a frame ready immediately
        # after start(); poll briefly so the first frame doesn't get
        # the default content_y=0.
        raw_bgr = None
        for _ in range(50):
            raw_bgr = self._grab_full_frame_bgr()
            if raw_bgr is not None:
                break
            time.sleep(0.05)
        if raw_bgr is None:
            return 0
        h, w = raw_bgr.shape[:2]
        gray = cv2.cvtColor(raw_bgr, cv2.COLOR_BGR2GRAY)

        scan_limit = int(h * 0.30)
        last_dark_end = 0
        run_len = 0
        for y in range(scan_limit):
            row_mean = gray[y, w // 4: 3 * w // 4].mean()
            if row_mean < 20:
                run_len += 1
            else:
                if run_len >= 5:
                    last_dark_end = y
                run_len = 0
        if run_len >= 5:
            last_dark_end = scan_limit
        return last_dark_end

