"""Thread-safe latest-frame-only capture.

Three backends:

* ``FrameSource`` — macOS Quartz ``CGWindowListCreateImage`` (browser
  window). Throttled by macOS when target window is occluded /
  backgrounded — a single Firefox tab on a non-foreground Space can
  drop sustained capture from 14 fps target to ~0.5 fps.
* ``CaptureCardFrameSource`` — ``cv2.VideoCapture(N)``, e.g. UGREEN
  HDMI→USB. Hardware-rate (~30 fps) and independent of any browser
  state. Production default (2026-05-02).
* ``FileFrameSource`` — ``cv2.VideoCapture(path)`` against an mp4,
  paced to the file's native fps so wall-clock semantics match a
  live broadcast. Used for offline replay of recorded matches
  through the live pipeline (fix-verification at volume).

Pick at runtime with ``make_frame_source(...)`` which honours the
``FRAME_SOURCE`` env var (``capture_card`` | ``window`` | ``file``).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    import Quartz
    import Quartz.CoreGraphics as CG
    HAS_QUARTZ = True
except ImportError:
    HAS_QUARTZ = False

log = logging.getLogger("frame_source")

# Off by default — preserves the legacy RGB-as-bgr quirk that all
# downstream consumers (HSV thresholds, vision-API JPEG encoders)
# were implicitly tuned against. See operations doc for the audit.
FRAME_COLOR_TRUE_BGR = os.environ.get("FRAME_COLOR_TRUE_BGR", "0") == "1"


class FrameSource:
    """Captures frames from a macOS window via Quartz.

    The capture thread writes at a target FPS. Readers always get the
    most recent frame — no queue, no backlog.
    """

    def __init__(self, window_id: int | None = None, fps: int = 2):
        self._window_id = window_id
        self._fps = fps
        self._latest_frame: np.ndarray | None = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._frame_count = 0
        self._last_capture_time = 0.0

    @property
    def window_id(self) -> int | None:
        return self._window_id

    @window_id.setter
    def window_id(self, wid: int):
        self._window_id = wid

    def start(self):
        if self._running:
            return
        if not HAS_QUARTZ:
            raise RuntimeError("pyobjc-framework-Quartz required for screen capture")
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def get_latest(self) -> np.ndarray | None:
        with self._lock:
            return self._latest_frame

    def get_frame_count(self) -> int:
        return self._frame_count

    def _capture_loop(self):
        interval = 1.0 / self._fps
        while self._running:
            start = time.monotonic()
            frame = self._capture_window()
            if frame is not None:
                with self._lock:
                    self._latest_frame = frame
                    self._frame_count += 1
                    self._last_capture_time = time.time()
            elapsed = time.monotonic() - start
            sleep_time = max(0, interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _capture_window(self) -> np.ndarray | None:
        if self._window_id is None:
            return self._capture_full_screen()
        return self._capture_by_window_id(self._window_id)

    def _capture_full_screen(self) -> np.ndarray | None:
        image = CG.CGWindowListCreateImage(
            CG.CGRectInfinite,
            CG.kCGWindowListOptionOnScreenOnly,
            CG.kCGNullWindowID,
            CG.kCGWindowImageDefault,
        )
        return self._cgimage_to_numpy(image)

    def _capture_by_window_id(self, window_id: int) -> np.ndarray | None:
        bounds = CG.CGRectNull
        image = CG.CGWindowListCreateImage(
            bounds,
            CG.kCGWindowListOptionIncludingWindow,
            window_id,
            CG.kCGWindowImageBoundsIgnoreFraming,
        )
        return self._cgimage_to_numpy(image)

    @staticmethod
    def _cgimage_to_numpy(image) -> np.ndarray | None:
        if image is None:
            return None
        width = CG.CGImageGetWidth(image)
        height = CG.CGImageGetHeight(image)
        if width == 0 or height == 0:
            return None

        bytes_per_row = CG.CGImageGetBytesPerRow(image)
        data_provider = CG.CGImageGetDataProvider(image)
        data = CG.CGDataProviderCopyData(data_provider)

        arr = np.frombuffer(data, dtype=np.uint8)
        arr = arr.reshape((height, bytes_per_row // 4, 4))
        arr = arr[:height, :width, :3]
        # CGImage memory layout on macOS is BGRA (kCGBitmapByteOrder32-
        # Little + AlphaPremultipliedFirst). The legacy `[:, :, ::-1]`
        # flip therefore produced RGB pixels into a variable named
        # `bgr` — a project-wide misnomer downstream code has been
        # tuned against. Preserve it unless FRAME_COLOR_TRUE_BGR=1.
        if FRAME_COLOR_TRUE_BGR:
            return arr.copy()
        return arr[:, :, ::-1].copy()

    @staticmethod
    def list_windows() -> list[dict]:
        """List visible windows with their IDs and titles."""
        if not HAS_QUARTZ:
            return []
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID,
        )
        result = []
        for w in windows:
            owner = w.get(Quartz.kCGWindowOwnerName, "")
            name = w.get(Quartz.kCGWindowName, "")
            wid = w.get(Quartz.kCGWindowNumber, 0)
            bounds = w.get(Quartz.kCGWindowBounds, {})
            width = bounds.get("Width", 0)
            height = bounds.get("Height", 0)
            if width > 200 and height > 200:
                result.append({
                    "id": wid,
                    "owner": owner,
                    "name": name,
                    "width": width,
                    "height": height,
                })
        return result


class CaptureCardFrameSource:
    """USB capture-card source via ``cv2.VideoCapture(device_index)``.

    Verified on M1 Max with UGREEN HDMI→USB at cv2 index 0 (note:
    ffmpeg's avfoundation enumerator lists the same device at [1] —
    cv2 and ffmpeg disagree on macOS device ordering; see
    ``files/docs/operations/frame_source_setup.md`` for the gotcha).
    Returns (1080, 1920, 3) BGR uint8 frames at ~30 fps; fully
    independent of macOS window state — no throttling when Firefox
    is backgrounded.

    A dedicated daemon thread continuously drains ``cap.read()`` so
    consumers always get the freshest frame regardless of their poll
    rate (matches legacy ``FrameSource`` semantics).

    Color order note
    ----------------
    The legacy Quartz ``FrameSource.get_latest()`` returns an array
    whose pixel bytes are in **RGB** order even though downstream
    code variously names it ``bgr``. ``get_latest()`` here mirrors
    that quirk for drop-in compatibility. ``get_latest_bgr()``
    returns the native BGR straight from cv2 — use it when you want
    true BGR (e.g. ``cv2.cvtColor(..., COLOR_BGR2GRAY)``).
    """

    READ_FAILURE_BACKOFF_S = 0.05
    REOPEN_AFTER_CONSEC_FAILURES = 60
    PERSISTENT_FAILURE_LOG_S = 30.0

    def __init__(self, device_index: int = 0, fps: int | None = None):
        self._device_index = int(device_index)
        self._fps = fps
        self._latest_bgr: np.ndarray | None = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._cap = None
        self._frame_count = 0
        self._last_capture_time = 0.0
        self._consec_failures = 0
        self._first_failure_time: float | None = None
        self._persistent_logged = False

    @property
    def window_id(self) -> int | None:
        return self._device_index

    @window_id.setter
    def window_id(self, v):
        self._device_index = int(v)

    @property
    def device_index(self) -> int:
        return self._device_index

    def start(self):
        if self._running:
            return
        if not HAS_CV2:
            raise RuntimeError(
                "opencv-python required for CaptureCardFrameSource")
        self._open()
        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop, daemon=True,
            name=f"capture-card-{self._device_index}")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._release()

    def get_latest(self) -> np.ndarray | None:
        """Default-mode: matches legacy ``FrameSource.get_latest`` byte
        order (RGB pixels under the ``bgr`` name, R/B swapped through
        every downstream cv2 call). With FRAME_COLOR_TRUE_BGR=1,
        returns native BGR — requires consumer re-tuning before flip."""
        bgr = self.get_latest_bgr()
        if bgr is None:
            return None
        if FRAME_COLOR_TRUE_BGR:
            return bgr.copy()
        return bgr[:, :, ::-1].copy()

    def get_latest_bgr(self) -> np.ndarray | None:
        """Native BGR straight from cv2.VideoCapture, no flip."""
        with self._lock:
            return self._latest_bgr

    def get_frame_count(self) -> int:
        return self._frame_count

    def _open(self):
        cap = cv2.VideoCapture(self._device_index)
        if not cap.isOpened():
            cap.release()
            raise RuntimeError(
                f"cv2.VideoCapture({self._device_index}) failed to open. "
                "Confirm the capture card is plugged in and visible "
                "(e.g. `ffmpeg -f avfoundation -list_devices true -i ''`).")
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        self._cap = cap
        log.info(
            "[capture_card] opened device %d (%dx%d @ %.1f fps reported)",
            self._device_index,
            int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0),
            int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0),
            float(cap.get(cv2.CAP_PROP_FPS) or 0.0))

    def _release(self):
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def _reopen(self):
        log.warning("[capture_card] reopening device %d after %d "
                    "consecutive read failures",
                    self._device_index, self._consec_failures)
        self._release()
        try:
            self._open()
            self._consec_failures = 0
            self._first_failure_time = None
            self._persistent_logged = False
        except Exception as e:
            log.error("[capture_card] reopen failed: %s", e)

    def _capture_loop(self):
        interval = (1.0 / self._fps) if self._fps else 0.0
        while self._running:
            t0 = time.monotonic()
            ok, frame = (False, None)
            if self._cap is not None:
                try:
                    ok, frame = self._cap.read()
                except Exception as e:
                    log.warning("[capture_card] cap.read raised: %s", e)
                    ok = False
            if not ok or frame is None:
                self._on_read_failure()
                time.sleep(self.READ_FAILURE_BACKOFF_S)
                continue
            self._on_read_success(frame)
            if interval > 0:
                elapsed = time.monotonic() - t0
                sleep_time = max(0.0, interval - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)

    def _on_read_success(self, frame: np.ndarray):
        with self._lock:
            self._latest_bgr = frame
            self._frame_count += 1
            self._last_capture_time = time.time()
        self._consec_failures = 0
        self._first_failure_time = None
        self._persistent_logged = False

    def _on_read_failure(self):
        self._consec_failures += 1
        now = time.time()
        if self._first_failure_time is None:
            self._first_failure_time = now
        if (not self._persistent_logged
                and now - (self._first_failure_time or now)
                > self.PERSISTENT_FAILURE_LOG_S):
            log.error("[capture_card] no frames for >%.0fs on device %d "
                      "— pipeline holding last known frame",
                      self.PERSISTENT_FAILURE_LOG_S, self._device_index)
            self._persistent_logged = True
        if self._consec_failures % self.REOPEN_AFTER_CONSEC_FAILURES == 0:
            self._reopen()

    @staticmethod
    def list_windows() -> list[dict]:
        """No-op for cv2 sources; kept for API parity with FrameSource."""
        return []


class FileFrameSource:
    """Plays back an mp4 at real-time pace as if live broadcast.

    Uses ``cv2.VideoCapture`` on a file path. A daemon thread drains
    the file and sleeps between reads so the per-frame interval
    matches the file's native fps — wall-clock semantics are
    therefore preserved for cadence-sensitive downstream consumers
    (delivery span timing, OpenScout pacing, etc.).

    API mirrors ``CaptureCardFrameSource`` for drop-in compatibility:
    ``get_latest()`` honours the legacy RGB-as-bgr quirk (toggled
    by ``FRAME_COLOR_TRUE_BGR``); ``get_latest_bgr()`` returns the
    native cv2 BGR.

    On EOF, either loops back to the start (``loop=True``) or stops
    the capture thread; subsequent ``get_latest`` calls return the
    last buffered frame until the consumer notices and shuts down.

    ``start_offset_s`` skips ahead via ``CAP_PROP_POS_MSEC`` (set
    once at open time) — operator-supplied to skip pre-match intros
    or jump to a specific over.
    """

    def __init__(self,
                 video_path: str | Path,
                 fps: int | None = None,
                 start_offset_s: float = 0.0,
                 loop: bool = False):
        self._video_path = str(video_path)
        self._fps_override = fps
        self._start_offset_s = float(start_offset_s)
        self._loop = bool(loop)
        self._latest_bgr: np.ndarray | None = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._cap = None
        self._file_fps: float = 0.0
        self._frame_count = 0
        self._last_capture_time = 0.0
        self._eof_reached = False

    @property
    def window_id(self) -> int | None:
        return None

    @window_id.setter
    def window_id(self, v):
        # No-op: file source has no window concept; setter retained
        # for API parity with the live sources.
        pass

    @property
    def video_path(self) -> str:
        return self._video_path

    @property
    def file_fps(self) -> float:
        return self._file_fps

    def start(self):
        if self._running:
            return
        if not HAS_CV2:
            raise RuntimeError(
                "opencv-python required for FileFrameSource")
        self._open()
        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop, daemon=True,
            name=f"file-frame-source-{Path(self._video_path).name}")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._release()

    def get_latest(self) -> np.ndarray | None:
        bgr = self.get_latest_bgr()
        if bgr is None:
            return None
        if FRAME_COLOR_TRUE_BGR:
            return bgr.copy()
        return bgr[:, :, ::-1].copy()

    def get_latest_bgr(self) -> np.ndarray | None:
        with self._lock:
            return self._latest_bgr

    def get_latest_with_ts(self) -> tuple[float, np.ndarray] | None:
        """Return ``(ts, bgr)`` where ``ts`` is the replay wall-clock
        ``time.time()`` recorded at the moment the frame was read from
        the file — NOT the recording's original capture time and NOT
        ``cv2.CAP_PROP_POS_MSEC`` (which is recording-position, wrong
        domain).

        The whole point of real-time pacing is for downstream consumers
        to see the replay as if it were live; the timestamp domain has
        to match.  Without this, ContinuousChunker emits events stamped
        with replay wall-clock while ball_analyzer._frame_buffer_raw
        stamps with current wall-clock — and the two never intersect.
        """
        with self._lock:
            if self._latest_bgr is None:
                return None
            return (self._last_capture_time, self._latest_bgr)

    def get_frame_count(self) -> int:
        return self._frame_count

    def _open(self):
        cap = cv2.VideoCapture(self._video_path)
        if not cap.isOpened():
            cap.release()
            raise RuntimeError(
                f"cv2.VideoCapture({self._video_path!r}) failed to open. "
                "Confirm the file exists and is a readable video format.")
        meta_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        if meta_fps > 0:
            self._file_fps = meta_fps
        elif self._fps_override:
            self._file_fps = float(self._fps_override)
        else:
            self._file_fps = 25.0
            log.warning("[file_frame_source] %s: no fps metadata and no "
                        "fps override; defaulting to 25.0",
                        self._video_path)
        if self._start_offset_s > 0:
            cap.set(cv2.CAP_PROP_POS_MSEC, self._start_offset_s * 1000.0)
        self._cap = cap
        log.info(
            "[file_frame_source] opened %s (%dx%d @ %.2f fps, "
            "offset=%.2fs, loop=%s)",
            self._video_path,
            int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0),
            int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0),
            self._file_fps, self._start_offset_s, self._loop)

    def _release(self):
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def _capture_loop(self):
        interval = 1.0 / self._file_fps if self._file_fps > 0 else 1.0 / 25.0
        while self._running:
            t0 = time.monotonic()
            ok, frame = (False, None)
            if self._cap is not None:
                try:
                    ok, frame = self._cap.read()
                except Exception as e:
                    log.warning("[file_frame_source] cap.read raised: %s", e)
                    ok = False
            if not ok or frame is None:
                self._on_eof()
                if not self._loop or not self._running:
                    return
                # Looped: rewind and continue without sleeping the
                # cadence — next iteration starts fresh.
                continue
            with self._lock:
                self._latest_bgr = frame
                self._frame_count += 1
                self._last_capture_time = time.time()
            elapsed = time.monotonic() - t0
            sleep_time = max(0.0, interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _on_eof(self):
        self._eof_reached = True
        log.info("[FILE-FRAME-SOURCE-EOF] %s reached end-of-file "
                 "(frames_read=%d, loop=%s)",
                 self._video_path, self._frame_count, self._loop)
        if self._loop and self._cap is not None:
            self._cap.set(cv2.CAP_PROP_POS_MSEC,
                          self._start_offset_s * 1000.0)
            self._eof_reached = False
            return
        self._running = False

    @staticmethod
    def list_windows() -> list[dict]:
        return []


def make_frame_source(window_id: int | None = None,
                      fps: int = 2,
                      source: str | None = None,
                      device_index: int | None = None,
                      video_path: str | Path | None = None):
    """Pick the frame-source backend based on the ``FRAME_SOURCE`` env
    var (default ``capture_card``).

    * ``capture_card`` → ``CaptureCardFrameSource`` (production).
      Device index defaults to ``CAPTURE_DEVICE_INDEX`` env (default
      ``0`` — the verified UGREEN slot on the M1 Max rig).
    * ``window`` → legacy ``FrameSource`` (Quartz). Kept for fallback
      and offline testing.
    * ``file`` → ``FileFrameSource``. Path resolved from
      ``video_path`` arg or ``FRAME_SOURCE_FILE`` env;
      ``FRAME_SOURCE_FILE_LOOP=1`` enables looping;
      ``FRAME_SOURCE_FILE_OFFSET_S`` seeks past pre-match intro.
    """
    src = (source or os.environ.get("FRAME_SOURCE", "capture_card")).lower()
    if src == "capture_card":
        idx = (device_index if device_index is not None
               else int(os.environ.get("CAPTURE_DEVICE_INDEX", "0")))
        return CaptureCardFrameSource(device_index=idx, fps=fps)
    if src == "window":
        return FrameSource(window_id=window_id, fps=fps)
    if src == "file":
        path = video_path or os.environ.get("FRAME_SOURCE_FILE")
        if not path:
            raise ValueError(
                "FRAME_SOURCE_FILE env var or video_path required "
                "for file mode")
        loop = os.environ.get("FRAME_SOURCE_FILE_LOOP", "0") == "1"
        offset = float(os.environ.get("FRAME_SOURCE_FILE_OFFSET_S", "0"))
        return FileFrameSource(
            video_path=path,
            fps=fps,
            start_offset_s=offset,
            loop=loop)
    raise ValueError(
        f"Unknown FRAME_SOURCE={src!r}; expected "
        "'capture_card', 'window', or 'file'")
