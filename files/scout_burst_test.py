"""Scout + Rolling Buffer — look-backward ball analysis.

Architecture (look-backward):
  1. RollingBuffer: Quartz window capture at ~25fps into a deque (last 8s)
  2. Scout: reads scoreboard every ~3s via same FrameSource at low fps
  3. Ball event: scoreboard overs/wickets change → freeze the buffer
  4. Process: extract last 6s, find wide-shot segment, run diff pipeline

The delivery already happened 1–2s ago and the frames are sitting in memory.
No prediction needed.  No trigger timing.  No ffmpeg dependency.

Usage:
  python scout_burst_test.py --max-deliveries 18
  python scout_burst_test.py --duration 300
  python scout_burst_test.py --replay /path/to/burst_frames/
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, ".")

from eyes.capture.frame_source import FrameSource
from eyes.vision import Vision
from eyes.config import CAPTURE_FPS

from ball_detection_utils import (
    detect_white_ball, find_pitch_crop, find_video_region, is_wide_shot,
)
from pitch_detector import find_pitch_region, PitchRegion
from phase_separator import separate_phases
from ball_classifier import (
    classify_length, classify_line, classify_bowling_angle,
    classify_bounce, build_commentary_line,
)

try:
    import Quartz
    import Quartz.CoreGraphics as CG
    HAS_QUARTZ = True
except ImportError:
    HAS_QUARTZ = False


# ── Helpers ──────────────────────────────────────────────────────────

def _find_delivery_window(
    frames: list[np.ndarray],
    window_frames: int = 30,
) -> tuple[int, int]:
    """Find the ~1-second delivery window within a buffer of wide-shot frames.

    For each frame pair, computes diff energy in the center pitch strip
    but ONLY if the frame is a true behind-stumps view (bilateral green).
    Closeup frames that leaked through the relaxed wide-shot filter get
    zero energy so they can't steal the window from the real delivery.
    """
    if len(frames) < window_frames + 2:
        return 0, len(frames)

    h, w = frames[0].shape[:2]
    x0 = int(w * 0.40)
    x1 = int(w * 0.60)

    energies = []
    for i in range(len(frames) - 1):
        frame = frames[i]
        # Quick bilateral green gate — reject closeups
        hsv = cv2.cvtColor(
            frame[int(h * 0.2):int(h * 0.75), :], cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, (25, 30, 40), (85, 255, 200))
        rh, rw = green.shape[:2]
        left = green[:, :rw // 3].sum() / 255 / (rh * (rw // 3)) * 100
        right = green[:, 2 * rw // 3:].sum() / 255 / (rh * (rw - 2 * rw // 3)) * 100
        if left < 15 or right < 15:
            energies.append(0.0)
            continue

        prev_gray = cv2.cvtColor(frames[i][:, x0:x1], cv2.COLOR_BGR2GRAY)
        curr_gray = cv2.cvtColor(frames[i + 1][:, x0:x1], cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(prev_gray, curr_gray)
        energies.append(float(diff.sum()))

    # Scan backward: the delivery is always the LAST motion peak
    # before the scoreboard trigger, not the global maximum.
    threshold = np.median(energies) * 3 if energies else 0
    window_end = len(energies) - 1
    for i in range(len(energies) - 1, -1, -1):
        if energies[i] > threshold:
            window_end = i
            break

    window_start = max(0, window_end - window_frames + 1)
    return window_start, min(window_start + window_frames, len(frames))


def _shot_type_from_runs(runs: int) -> str:
    """Determine shot type from scoreboard runs scored."""
    if runs == 0:
        return "defended"
    if runs == 6:
        return "in_the_air"
    if runs == 4:
        return "unknown"
    return "along_ground"


def _find_firefox_window() -> tuple[int | None, str]:
    """Return (window_id, status) for Firefox, preferring on-screen."""
    for w in FrameSource.list_windows():
        if "firefox" in w["owner"].lower():
            print(f"  Firefox window: id={int(w['id'])} "
                  f"{int(w['width'])}x{int(w['height'])} "
                  f"\"{str(w['name'])[:60]}\"")
            return int(w["id"]), "on-screen"

    if HAS_QUARTZ:
        wins = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionAll
            | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID,
        )
        for w in (wins or []):
            owner = w.get(Quartz.kCGWindowOwnerName, "")
            bounds = w.get(Quartz.kCGWindowBounds, {})
            width = bounds.get("Width", 0)
            if "firefox" in owner.lower() and width > 500:
                wid = int(w.get(Quartz.kCGWindowNumber, 0))
                print(f"  Firefox (off-screen): id={wid}")
                return wid, "off-screen"
    return None, "not-found"


# ── Rolling Buffer (Quartz-based) ────────────────────────────────────

class RollingBuffer:
    """Two-buffer continuous capture: all-frames + wide-shot-only.

    Every captured frame goes into the all-frames buffer (short window).
    Frames that pass is_wide_shot also go into a second, larger buffer
    that only holds pitch views.  When a ball event fires, we freeze
    from the wide-shot buffer — so replays/closeups that flood the feed
    after a delivery never overwrite the actual delivery frames.
    """

    WIDE_MAXLEN = 300  # ~30s of wide shots at ~10fps effective rate

    def __init__(self, window_id: int, max_seconds: int = 8):
        self._window_id = window_id
        self.max_seconds = max_seconds
        self._buffer: collections.deque[tuple[float, np.ndarray]] = (
            collections.deque(maxlen=25 * max_seconds))
        self._wide_buffer: collections.deque[tuple[float, np.ndarray]] = (
            collections.deque(maxlen=self.WIDE_MAXLEN))
        self._thread: threading.Thread | None = None
        self._running = False
        self._frames_read = 0
        self._wide_count = 0
        self._out_w = 0
        self._out_h = 0
        self._actual_fps = 0.0
        self._content_y = 0

    def start(self):
        self._content_y = self._detect_content_top()
        if self._content_y > 0:
            print(f"  Content area starts at y={self._content_y} "
                  f"(cropping app chrome)")
        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop, daemon=True, name="rolling-buf")
        self._thread.start()

    def _detect_content_top(self) -> int:
        """Find where the main content starts by detecting app chrome.

        Looks for the last dark horizontal band in the top 30% of the
        frame. The content area starts just below it.  Works generically
        for any windowed application (browser, streaming app, etc.).
        """
        image = CG.CGWindowListCreateImage(
            CG.CGRectNull,
            CG.kCGWindowListOptionIncludingWindow,
            self._window_id,
            CG.kCGWindowImageBoundsIgnoreFraming,
        )
        if image is None:
            return 0
        w = CG.CGImageGetWidth(image)
        h = CG.CGImageGetHeight(image)
        bpr = CG.CGImageGetBytesPerRow(image)
        data = CG.CGDataProviderCopyData(CG.CGImageGetDataProvider(image))
        arr = np.frombuffer(data, dtype=np.uint8).reshape((h, bpr // 4, 4))
        gray = cv2.cvtColor(arr[:h, :w, :3], cv2.COLOR_BGRA2GRAY)

        scan_limit = int(h * 0.30)
        dark_threshold = 20
        min_band = 5
        last_dark_end = 0
        run_len = 0
        for y in range(scan_limit):
            row_mean = gray[y, w // 4: 3 * w // 4].mean()
            if row_mean < dark_threshold:
                run_len += 1
            else:
                if run_len >= min_band:
                    last_dark_end = y
                run_len = 0
        if run_len >= min_band:
            last_dark_end = scan_limit
        return last_dark_end

    def freeze_wide(self, max_frames: int = 150
                    ) -> list[tuple[float, np.ndarray]]:
        """Grab the last *max_frames* from the wide-shot buffer."""
        snapshot = list(self._wide_buffer)
        return snapshot[-max_frames:]

    @property
    def frame_count(self) -> int:
        return len(self._buffer)

    @property
    def wide_count(self) -> int:
        return len(self._wide_buffer)

    @property
    def fps(self) -> float:
        return self._actual_fps

    @property
    def alive(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        print(f"  Rolling buffer stopped "
              f"({self._frames_read} total, {self._wide_count} wide, "
              f"~{self._actual_fps:.0f} fps)")

    def _capture_loop(self):
        import traceback
        t_start = time.time()
        try:
            while self._running:
                image = CG.CGWindowListCreateImage(
                    CG.CGRectNull,
                    CG.kCGWindowListOptionIncludingWindow,
                    self._window_id,
                    CG.kCGWindowImageBoundsIgnoreFraming,
                )
                if image is None:
                    time.sleep(0.01)
                    continue

                w = CG.CGImageGetWidth(image)
                h = CG.CGImageGetHeight(image)
                if w == 0 or h == 0:
                    time.sleep(0.01)
                    continue

                bpr = CG.CGImageGetBytesPerRow(image)
                data = CG.CGDataProviderCopyData(
                    CG.CGImageGetDataProvider(image))
                arr = np.frombuffer(data, dtype=np.uint8).reshape(
                    (h, bpr // 4, 4))
                bgr = arr[self._content_y:h, :w, :3][:, :, ::-1].copy()

                now = time.time()
                self._buffer.append((now, bgr))
                self._frames_read += 1
                self._out_w = bgr.shape[1]
                self._out_h = bgr.shape[0]

                if is_wide_shot(bgr):
                    self._wide_buffer.append((now, bgr))
                    self._wide_count += 1

                elapsed = now - t_start
                if elapsed > 0:
                    self._actual_fps = self._frames_read / elapsed
        except Exception:
            print(f"  ROLLING BUFFER ERROR: {traceback.format_exc()}",
                  flush=True)
            self._running = False


# ── Main Test Runner ─────────────────────────────────────────────────

class ScoutBurstTest:
    """Look-backward architecture: Scout detects ball events from scoreboard
    changes, then grabs the last N seconds from the rolling buffer."""

    COOLDOWN_SECONDS = 8.0

    def __init__(
        self,
        output_dir: str = "scout_burst_results",
        buffer_seconds: int = 8,
        freeze_seconds: float = 6.0,
        scout_interval: float = 3.0,
        diff_threshold: int = 20,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        self.buffer_seconds = buffer_seconds
        self.freeze_seconds = freeze_seconds
        self.scout_interval = scout_interval
        self.diff_threshold = diff_threshold

        self.delivery_count = 0
        self.results: list[dict] = []
        self.pitch_crop: tuple[int, int, int, int] | None = None

        self._vision: Vision | None = None
        self._frames: FrameSource | None = None
        self._rolling: RollingBuffer | None = None
        self._scout_count = 0

        self._last_overs: str | None = None
        self._last_score: int | None = None
        self._last_wickets: int | None = None
        self._last_delivery_time = 0.0
        self._runs_scored: int | None = None
        self._scout_context: dict = {}

    # ── Lifecycle ────────────────────────────────────────────────────

    async def run(self, max_deliveries: int = 18,
                  max_duration: float | None = None):
        print("=== Scout + Rolling Buffer Test ===")
        print(f"Target: {max_deliveries} deliveries, "
              f"buffer={self.buffer_seconds}s, freeze={self.freeze_seconds}s")

        import subprocess as _sp
        _sp.run(["osascript", "-e",
                 'tell application "Firefox" to activate'],
                capture_output=True, timeout=3)
        await asyncio.sleep(0.5)

        wid, status = _find_firefox_window()
        if not wid:
            print("  Firefox not found — cannot proceed")
            return

        # Rolling buffer: Quartz capture at ~25fps into deque
        self._rolling = RollingBuffer(
            window_id=wid, max_seconds=self.buffer_seconds)
        self._rolling.start()
        await asyncio.sleep(3.0)
        print(f"  Buffer primed: {self._rolling.frame_count} total, "
              f"{self._rolling.wide_count} wide "
              f"(~{self._rolling.fps:.0f} fps)")

        # Scout: FrameSource at low fps for scoreboard reading
        self._frames = FrameSource(window_id=wid, fps=CAPTURE_FPS)
        self._frames.start()
        await asyncio.sleep(1.0)

        self._vision = Vision()

        t_start = time.time()
        try:
            while self.delivery_count < max_deliveries:
                if max_duration and (time.time() - t_start) > max_duration:
                    print(f"\nDuration limit ({max_duration}s) reached.")
                    break
                await self._scout_step()
        except KeyboardInterrupt:
            print("\nStopped by user.")

        self._frames.stop()
        self._rolling.stop()
        await self._vision.close()
        self._save_summary()
        elapsed = time.time() - t_start
        print(f"\nDone. {self.delivery_count} deliveries in {elapsed:.0f}s.")
        print(f"Results: {self.output_dir}/")

    # ── Scout step ───────────────────────────────────────────────────

    async def _scout_step(self):
        frame = self._capture()
        if frame is None:
            await asyncio.sleep(0.5)
            return

        h, w = frame.shape[:2]
        if w > 2500:
            frame = cv2.resize(frame, (w // 2, h // 2),
                               interpolation=cv2.INTER_AREA)

        self._scout_count += 1
        frame_type, description, action = await self._vision.describe(frame)

        action_preview = (action or "")[:60]
        strip_preview = (description or "")[:80].replace("\n", " ")
        print(f"  [SCOUT #{self._scout_count}] {frame_type} | "
              f"{strip_preview} | action: {action_preview}")

        if frame_type != "SCOREBOARD":
            await asyncio.sleep(self.scout_interval)
            return

        overs, score, wickets = self._parse_scoreboard(description)
        if overs is not None and self._check_ball_event(overs, score, wickets):
            self._scout_context = {
                "strip_after": description,
                "overs": overs,
                "score": f"{score}-{wickets}",
                "runs": self._runs_scored,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._on_ball_event()

        await asyncio.sleep(self.scout_interval)

    def _parse_scoreboard(self, description: str
                          ) -> tuple[str | None, int | None, int | None]:
        """Extract (overs, runs, wickets) from the team score segment."""
        if not description:
            return None, None, None
        first_seg = description.split("|")[0].strip()
        m = re.search(r"(\d+)-(\d+)\s*\((\d+\.?\d*)\)", first_seg)
        if m:
            return m.group(3), int(m.group(1)), int(m.group(2))
        return None, None, None

    def _check_ball_event(self, overs: str, score: int | None,
                          wickets: int | None) -> bool:
        if self._last_overs is None:
            self._last_overs = overs
            self._last_score = score
            self._last_wickets = wickets
            return False

        if time.time() - self._last_delivery_time < self.COOLDOWN_SECONDS:
            self._last_overs = overs
            self._last_score = score
            self._last_wickets = wickets
            return False

        # Reject unrealistic jumps (ads, scene changes, misreads)
        try:
            new_ov = float(overs)
            old_ov = float(self._last_overs)
            delta = new_ov - old_ov
            if delta < 0 or delta > 1.0:
                self._last_overs = overs
                self._last_score = score
                self._last_wickets = wickets
                return False
        except (ValueError, TypeError):
            pass

        changed = overs != self._last_overs
        if wickets is not None and self._last_wickets is not None:
            if wickets != self._last_wickets:
                changed = True

        if changed:
            prev_score = self._last_score
            self._runs_scored = (
                (score - prev_score)
                if score is not None and prev_score is not None
                else None)

        self._last_overs = overs
        self._last_score = score
        self._last_wickets = wickets
        return changed

    # ── Ball event handling ──────────────────────────────────────────

    def _on_ball_event(self):
        runs = self._runs_scored if self._runs_scored is not None else 0
        print(f"  >>> BALL EVENT: "
              f"{self._last_score}-{self._last_wickets} "
              f"({self._last_overs} ov) | {runs} runs")
        self._last_delivery_time = time.time()

        frozen = self._rolling.freeze_wide(max_frames=150)
        if len(frozen) < 10:
            print(f"  Wide buffer too small ({len(frozen)} frames) — skipping")
            return

        frames = [f for _, f in frozen]
        timestamps = [t for t, _ in frozen]
        span = timestamps[-1] - timestamps[0] if len(timestamps) > 1 else 0
        print(f"  Frozen {len(frames)} wide-shot frames "
              f"(spanning {span:.1f}s)")

        self._process_delivery(frames, timestamps, runs)

    # ── Delivery processing (pipeline) ───────────────────────────────

    def _process_delivery(self, frames: list[np.ndarray],
                          timestamps: list[float],
                          runs: int = 0):
        self.delivery_count += 1
        del_dir = self.output_dir / f"delivery_{self.delivery_count:03d}"
        del_dir.mkdir(exist_ok=True)

        if len(frames) < 10:
            print(f"  Only {len(frames)} frames — skipping")
            return

        step = max(1, len(frames) // 10)
        for i in range(0, len(frames), step):
            cv2.imwrite(str(del_dir / f"raw_{i:03d}.jpg"), frames[i])

        # Strip black letterbox bars if present
        vx, vy, vw, vh = find_video_region(frames[len(frames) // 2])
        if vx > 0 or vy > 0 or vw < frames[0].shape[1] or vh < frames[0].shape[0]:
            print(f"  Video region: x={vx} y={vy} w={vw} h={vh}")
            frames = [f[vy:vy + vh, vx:vx + vw] for f in frames]

        # Find the ~1 second delivery window (highest motion in center strip)
        win_start, win_end = _find_delivery_window(frames)
        print(f"  Delivery window: frames {win_start}-{win_end} "
              f"({win_end - win_start} of {len(frames)})")
        del_frames = frames[win_start:win_end]
        del_timestamps = timestamps[win_start:win_end]
        h, w = del_frames[0].shape[:2]

        # Detect pitch region from the delivery window
        pitch_region: PitchRegion | None = None
        for f in del_frames[len(del_frames) // 4::5]:
            pitch_region = find_pitch_region(f)
            if pitch_region.method != "fallback":
                break
            pitch_region = None

        if pitch_region is None:
            for f in del_frames[::10]:
                pitch_region = find_pitch_region(f)
                if pitch_region.edges_detected:
                    break

        if (pitch_region and pitch_region.method != "fallback"
                and pitch_region.bbox[2] > 50 and pitch_region.bbox[3] > 50):
            burst_crop = pitch_region.bbox
            print(f"  Pitch crop ({pitch_region.method}): {burst_crop}")
        else:
            burst_crop = (int(w * 0.15), int(h * 0.05),
                          int(w * 0.55), int(h * 0.65))
            print(f"  Pitch crop (fallback): {burst_crop}")

        px, py, pw, ph = burst_crop

        min_h = int(h * 0.40)
        if ph < min_h:
            extra = min_h - ph
            expand_top = int(extra * 0.65)
            py = max(0, py - expand_top)
            ph = min(h - py, ph + extra)
            print(f"  Expanded crop: y={py} h={ph}")

        self.pitch_crop = (px, py, pw, ph)

        # Ball detection on delivery-window frames only
        detections: list[dict] = []
        for i in range(len(del_frames) - 1):
            prev_crop = del_frames[i][py:py + ph, px:px + pw]
            curr_crop = del_frames[i + 1][py:py + ph, px:px + pw]
            candidates = detect_white_ball(
                prev_crop, curr_crop, threshold=self.diff_threshold)
            if candidates:
                best = candidates[0]
                detections.append({
                    "frame": i + 1,
                    "x": best["x"], "y": best["y"],
                    "area": best["area"],
                    "timestamp": del_timestamps[i + 1],
                })

        print(f"  Ball detected in {len(detections)}/{len(del_frames) - 1} pairs")

        if len(detections) < 3:
            print(f"  Insufficient detections for trajectory")
            self._save_result(del_dir, detections, None, len(frames))
            return

        # Phase separation + classification (flight phase only)
        phases = separate_phases(detections, ph)

        cl: dict = {}
        flight = phases.get("flight", [])
        bp = phases.get("bounce_point")

        center_in_crop = (pitch_region.pitch_center_x_top - px
                          if pitch_region else pw // 2)
        cl["bowling_angle"] = (
            classify_bowling_angle(flight[0]["x"], center_in_crop)
            if len(flight) >= 2 else "unknown")
        cl["length"] = (
            classify_length(bp["y"], ph) if bp else "unknown")
        cl["line"] = (
            classify_line(flight[-1]["x"], pw)
            if len(flight) >= 2 else "unknown")
        cl["bounce"] = (
            classify_bounce(flight, bp)
            if bp and len(flight) >= 3 else "unknown")
        cl["shot_type"] = _shot_type_from_runs(runs)
        cl["runs"] = runs
        cl["commentary_feed"] = build_commentary_line(cl)

        if pitch_region and pitch_region.method != "fallback":
            cl["pitch_info"] = {
                "method": pitch_region.method,
                "bowling_crease_y": pitch_region.bowling_crease_y,
                "batting_crease_y": pitch_region.batting_crease_y,
                "pitch_center_top": pitch_region.pitch_center_x_top,
                "pitch_center_bottom": pitch_region.pitch_center_x_bottom,
            }

        print(f"  DELIVERY #{self.delivery_count}:")
        print(f"    Angle:  {cl['bowling_angle']}")
        print(f"    Length: {cl['length']}")
        print(f"    Line:   {cl['line']}")
        print(f"    Bounce: {cl['bounce']}")
        print(f"    Shot:   {cl['shot_type']} ({runs} runs)")
        print(f"    >> {cl['commentary_feed']}")

        bg_frame = del_frames[len(del_frames) // 2]
        self._save_result(del_dir, detections, cl, len(frames))
        self._save_trajectory(del_dir, bg_frame, detections, phases)
        self.results.append(cl)

    # ── Capture ──────────────────────────────────────────────────────

    def _capture(self) -> np.ndarray | None:
        if self._frames is None:
            return None
        return self._frames.get_latest()

    # ── Persistence ──────────────────────────────────────────────────

    def _save_result(self, del_dir: Path, detections: list,
                     cl: dict | None, total_frames: int):
        result = {
            "delivery_number": self.delivery_count,
            "frozen_frames": total_frames,
            "detections_count": len(detections),
            "classification": cl,
            "scout_context": self._scout_context,
        }
        with open(del_dir / "result.json", "w") as f:
            json.dump(result, f, indent=2, default=str)

    def _save_trajectory(self, del_dir: Path, base_frame: np.ndarray,
                         detections: list, phases: dict):
        if self.pitch_crop is None:
            return
        px, py, pw, ph = self.pitch_crop
        viz = base_frame[py:py + ph, px:px + pw].copy()

        flight_frames = {d["frame"] for d in phases.get("flight", [])}
        post_frames = {d["frame"] for d in phases.get("post_shot", [])}

        for d in detections:
            if d["frame"] in flight_frames:
                color, tag = (0, 255, 0), "F"
            elif d["frame"] in post_frames:
                color, tag = (255, 165, 0), "S"
            else:
                color, tag = (128, 128, 128), "?"
            cv2.circle(viz, (d["x"], d["y"]), 6, color, 2)
            cv2.putText(viz, f'{tag}{d["frame"]}',
                        (d["x"] + 8, d["y"] - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.3, color, 1)

        bp = phases.get("bounce_point")
        if bp:
            cv2.circle(viz, (bp["x"], bp["y"]), 10, (0, 0, 255), 3)
            cv2.putText(viz, "BOUNCE", (bp["x"] + 12, bp["y"]),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

        cv2.imwrite(str(del_dir / "trajectory.png"), viz)

    def _save_summary(self):
        summary = {
            "total_deliveries": self.delivery_count,
            "pitch_crop": self.pitch_crop,
            "results": self.results,
        }
        with open(self.output_dir / "summary.json", "w") as f:
            json.dump(summary, f, indent=2, default=str)


# ── Replay mode (offline, no Scout) ─────────────────────────────────

def run_replay(frames_dir: str, output_dir: str, diff_threshold: int = 20,
               region: str | None = None):
    """Process pre-recorded burst frames without Scout."""
    from glob import glob

    out = Path(output_dir)
    out.mkdir(exist_ok=True)

    paths = sorted(glob(os.path.join(frames_dir, "*.png")))
    if not paths:
        paths = sorted(glob(os.path.join(frames_dir, "*.jpg")))
    frames = [cv2.imread(p) for p in paths]
    print(f"Replay: {len(frames)} frames from {frames_dir}")

    if len(frames) < 10:
        print("Need at least 10 frames")
        return

    h, w = frames[0].shape[:2]

    if region:
        crop = tuple(int(x) for x in region.split(","))
    else:
        crop = None
        for f in frames[len(frames) // 4: 3 * len(frames) // 4: 5]:
            if is_wide_shot(f):
                crop = find_pitch_crop(f)
                break
        if crop is None:
            crop = (int(w * 0.1), int(h * 0.05),
                    int(w * 0.55), int(h * 0.65))
    px, py, pw, ph = crop
    print(f"Crop: {crop}")

    detections: list[dict] = []
    for i in range(len(frames) - 1):
        prev_c = frames[i][py:py + ph, px:px + pw]
        curr_c = frames[i + 1][py:py + ph, px:px + pw]
        cands = detect_white_ball(prev_c, curr_c, threshold=diff_threshold)
        if cands:
            best = cands[0]
            detections.append({"frame": i + 1, "x": best["x"],
                               "y": best["y"], "area": best["area"]})
        if (i + 1) % 20 == 0:
            print(f"  Processed {i + 1}/{len(frames) - 1}...")

    print(f"Detections: {len(detections)}/{len(frames) - 1}")

    if len(detections) < 3:
        print("Insufficient detections")
        return

    phases = separate_phases(detections, ph)
    flight = phases.get("flight", [])
    bp = phases.get("bounce_point")
    post = phases.get("post_shot", [])

    cl: dict = {}
    cl["bowling_angle"] = (classify_bowling_angle(flight[0]["x"], pw // 2)
                           if len(flight) >= 2 else "unknown")
    cl["length"] = classify_length(bp["y"], ph) if bp else "unknown"
    cl["line"] = (classify_line(flight[-1]["x"], pw)
                  if len(flight) >= 2 else "unknown")
    cl["bounce"] = (classify_bounce(flight, bp)
                    if bp and len(flight) >= 3 else "unknown")
    cl["shot_type"] = (classify_shot_elevation(post)
                       if len(post) >= 3 else "unknown")
    batter_pos = (pw // 2, int(ph * 0.85))
    cl["shot_direction"] = (classify_shot_direction(batter_pos, post)
                            if len(post) >= 2
                            else {"zone": "unknown", "side": "unknown"})
    cl["offside_legside"] = cl.get("shot_direction", {}).get("side", "unknown")
    cl["commentary_feed"] = build_commentary_line(cl)

    print(f"\nClassification:")
    for k, v in cl.items():
        print(f"  {k}: {v}")

    result = {"detections": len(detections), "classification": cl,
              "phases": {k: len(v) if isinstance(v, list) else v
                         for k, v in phases.items()}}
    with open(out / "result.json", "w") as f:
        json.dump(result, f, indent=2, default=str)

    viz = frames[0][py:py + ph, px:px + pw].copy()
    for d in detections:
        color = (0, 255, 0) if d in flight else (255, 165, 0)
        cv2.circle(viz, (d["x"], d["y"]), 6, color, 2)
    if bp:
        cv2.circle(viz, (bp["x"], bp["y"]), 10, (0, 0, 255), 3)
    cv2.imwrite(str(out / "trajectory.png"), viz)
    print(f"Results: {out}/")


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scout + Rolling Buffer ball analysis")
    parser.add_argument("--max-deliveries", type=int, default=18)
    parser.add_argument("--duration", type=float, default=None,
                        help="Max runtime in seconds")
    parser.add_argument("--output", type=str, default="scout_burst_results")
    parser.add_argument("--diff-threshold", type=int, default=20)
    parser.add_argument("--buffer-seconds", type=int, default=8,
                        help="Rolling buffer window in seconds")
    parser.add_argument("--freeze-seconds", type=float, default=6.0,
                        help="Seconds to grab on ball event")
    parser.add_argument("--scout-interval", type=float, default=3.0,
                        help="Seconds between Scout calls")
    parser.add_argument("--replay", type=str, default=None,
                        help="Replay: process pre-recorded burst frames")
    parser.add_argument("--region", type=str, default=None,
                        help="Pitch crop as x,y,w,h (replay only)")
    args = parser.parse_args()

    if args.replay:
        run_replay(args.replay, args.output, args.diff_threshold, args.region)
        return

    test = ScoutBurstTest(
        output_dir=args.output,
        buffer_seconds=args.buffer_seconds,
        freeze_seconds=args.freeze_seconds,
        diff_threshold=args.diff_threshold,
        scout_interval=args.scout_interval,
    )
    asyncio.run(test.run(
        max_deliveries=args.max_deliveries,
        max_duration=args.duration,
    ))


if __name__ == "__main__":
    main()
