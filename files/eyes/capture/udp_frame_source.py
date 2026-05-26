"""UDP MPEG-TS frame source via an ffmpeg subprocess pipe.

DRAFT 2026-05-12 — design choices below need OK before wiring into
``make_frame_source()``.  Replaces the production hack
``FRAME_SOURCE=file`` + ``FRAME_SOURCE_FILE=udp://...`` →
``cv2.VideoCapture(url)`` which loses SPS/PPS on UDP packet loss and
silently buffers stale frames behind the latest-frame contract.

Design choices (marked DC1..DC4 — flag for review)
==================================================

DC1. Decode path: ffmpeg subprocess → stdin pipe → rawvideo bytes.

  Rejected alternatives:
    * ``cv2.VideoCapture("udp://...")`` — what we have now.  Internal
      buffering hides packet loss until decode catches up, then
      delivers stale frames; SPS/PPS recovery is opaque.
    * PyAV — clean API but adds a heavy C extension dep; ffmpeg is
      already on the install path (recorder.service uses it).

  Why ffmpeg subprocess:
    * Same binary the recorder uses — proven on this exact UDP feed.
    * Full CLI control over robustness flags (``-fflags +discardcorrupt``,
      ``-err_detect ignore_err``, fifo / buffer / overrun nonfatal).
    * Subprocess crash is observable and respawnable.

  Probe before pipe: ffprobe the stream once at start() to discover
  actual width/height (silent ``-vf scale=…`` would mask Mac-side
  regressions and waste CPU).  Validate against
  ``FRAME_SOURCE_UDP_ALLOWED_DIMENSIONS`` (default
  ``1920x1080,1280x720``); raise RuntimeError with the observed
  dimensions if unexpected.  The read loop then chunks stdout in
  ``W*H*3``-byte slices with W,H learned from the probe.

DC2. Reconnect strategy: watchdog + exponential backoff.

  * A watchdog thread tracks ``last_frame_wall``.  If
    ``WATCHDOG_S`` seconds elapse without a fresh frame, kill the
    ffmpeg subprocess and respawn.
  * Backoff between respawns: 0.5s → 1s → 2s → 4s → 8s (cap).
    Resets to 0.5s on first successful frame after a respawn.
  * No max-retry — UDP ingest is supposed to be eternally available;
    we log loudly but never give up.
  * Cumulative ``frames_dropped`` (= bytes received but not delivered
    cleanly) + ``reconnect_count`` exposed via ``stats()`` and
    snapshotted in pipeline log every ``LOG_EVERY_N`` frames.

DC3. SPS/PPS recovery: rely on Mac-side ``repeat-headers=1`` keyframes.

  The Mac encoder is configured (per HANDOFF) to emit SPS/PPS on
  every keyframe.  ffmpeg's H.264 decoder picks them up automatically;
  we don't need a hand-rolled recovery loop.  What we DO need is to
  notice when the *stream* stops producing decodable frames — DC2's
  watchdog catches that.  ``-fflags +discardcorrupt`` drops
  partial-frame corruption silently rather than blocking the decoder.

DC4. Backpressure: latest-slot-only, drop intermediates.

  Mirrors ``CaptureCardFrameSource`` exactly — daemon thread
  continuously drains ffmpeg stdout, overwriting a single locked
  slot.  Slow consumers see fresh frames; old frames are dropped at
  the slot, not buffered in ffmpeg's stdout pipe.  Pipe pressure is
  handled by reading as fast as bytes arrive; the read loop blocks
  on the pipe only when ffmpeg itself is starved, in which case the
  watchdog kicks in.

  This is the critical real-time-first property.  cv2.VideoCapture
  cannot deliver it — its internal buffer is invisible from Python
  and grows under load.

API
===
Mirrors ``CaptureCardFrameSource`` / ``FileFrameSource`` for drop-in
compatibility with the existing ``make_frame_source()`` selector.
``get_latest()`` honours the legacy RGB-as-bgr quirk (toggle with
``FRAME_COLOR_TRUE_BGR``); ``get_latest_bgr()`` returns native BGR
straight from ffmpeg's ``-pix_fmt bgr24`` output.

Env vars
========
* ``FRAME_SOURCE=udp`` — selects this backend.
* ``FRAME_SOURCE_UDP_URL`` — full ffmpeg input URL, e.g.
  ``udp://0.0.0.0:9999?fifo_size=10000000&buffer_size=2097152&overrun_nonfatal=1``.
* ``FRAME_SOURCE_UDP_ALLOWED_DIMENSIONS`` — comma-separated
  ``WxH`` allowlist for observed stream dimensions (default
  ``1920x1080,1280x720``).  Probe-and-reject prevents silent
  rescaling masking Mac-side resolution drift.
* ``FRAME_SOURCE_UDP_PROBE_TIMEOUT_S`` — ffprobe timeout per try
  (default 10.0); ffprobe is retried up to 3 times with 1s sleep.
* ``FRAME_SOURCE_UDP_WATCHDOG_S`` — stall threshold (default 5.0).
* ``FRAME_SOURCE_UDP_LOG_EVERY_N`` — periodic stats log cadence
  (default 600 frames ≈ every 20s @ 30 fps).
"""
from __future__ import annotations

import hashlib
import logging
import os
import shlex
import subprocess
import sys
import threading
import time
from typing import Optional

import numpy as np

try:
    import trace_emitter as _trace
except ImportError:
    _trace = None

log = logging.getLogger("udp_frame_source")

# H.264 / decoder failure signatures worth surfacing from the ffmpeg
# subprocess stderr — the rest stays at DEBUG.  ``_drain_stderr``
# greps for these substrings (case-insensitive) and emits the matching
# lines via WARN-level print so they reach the captured pipeline log
# regardless of how the Python logging module is configured.
_FFMPEG_STDERR_WARN_HINTS: tuple[str, ...] = (
    "error",
    "non-existing pps",
    "non-existing sps",
    "decode_slice_header",
    "reference picture missing",
    "invalid nal",
    "concealing",
    "no frame!",
)

# Frozen-stream detection — how many consecutive consumer reads must
# return byte-identical content before we trip ``UDP-STREAM-FROZEN``.
_FROZEN_STREAM_THRESHOLD: int = 5

# Hash sample stride — every Nth byte of the 6.22 MB raw frame.  Spreads
# the ~65 KB sample evenly across the whole frame so identical letterbox
# borders at the top/bottom can't produce false-positive freeze
# detections.  Validated 2026-05-14 against the 4621b9f8 recording.
_HASH_SAMPLE_STRIDE: int = 95

FRAME_COLOR_TRUE_BGR = os.environ.get("FRAME_COLOR_TRUE_BGR", "0") == "1"

DEFAULT_URL = (
    "udp://0.0.0.0:9999"
    "?fifo_size=10000000&buffer_size=2097152&overrun_nonfatal=1"
)
DEFAULT_ALLOWED_DIMENSIONS = ((1920, 1080), (1280, 720))
DEFAULT_WATCHDOG_S = 5.0
# After respawning ffmpeg we wait longer for the first frame than for
# steady-state stalls: a fresh decoder typically needs 3-6s to sync
# on a mid-stream UDP join (PPS dropouts until the next keyframe).
# Empirically ~6s in lab tests; default 15s leaves headroom for slow
# networks. Steady-state ``watchdog_s`` kicks in once the first frame
# has been delivered after a spawn.
DEFAULT_STARTUP_GRACE_S = 15.0
DEFAULT_PROBE_TIMEOUT_S = 10.0
DEFAULT_PROBE_RETRIES = 3
DEFAULT_LOG_EVERY_N = 600

# Exponential backoff between ffmpeg respawns.
_BACKOFF_START_S = 0.5
_BACKOFF_MAX_S = 8.0


def _parse_dimensions_allowlist(s: str) -> tuple[tuple[int, int], ...]:
    out: list[tuple[int, int]] = []
    for token in s.split(","):
        token = token.strip().lower()
        if not token:
            continue
        if "x" not in token:
            raise ValueError(
                f"invalid dimension token {token!r}; expected 'WxH'")
        w_s, h_s = token.split("x", 1)
        out.append((int(w_s), int(h_s)))
    if not out:
        raise ValueError("dimension allowlist is empty")
    return tuple(out)


class UDPFrameSource:
    """UDP MPEG-TS ingest via an ffmpeg subprocess; latest-slot delivery."""

    def __init__(
        self,
        url: str = DEFAULT_URL,
        allowed_dimensions: tuple[tuple[int, int], ...] = DEFAULT_ALLOWED_DIMENSIONS,
        watchdog_s: float = DEFAULT_WATCHDOG_S,
        startup_grace_s: float = DEFAULT_STARTUP_GRACE_S,
        probe_timeout_s: float = DEFAULT_PROBE_TIMEOUT_S,
        probe_retries: int = DEFAULT_PROBE_RETRIES,
        log_every_n: int = DEFAULT_LOG_EVERY_N,
        ffmpeg_bin: str = "ffmpeg",
        ffprobe_bin: str = "ffprobe",
    ) -> None:
        self._url = url
        self._allowed_dimensions = tuple(allowed_dimensions)
        self._watchdog_s = float(watchdog_s)
        self._startup_grace_s = float(startup_grace_s)
        self._probe_timeout_s = float(probe_timeout_s)
        self._probe_retries = int(probe_retries)
        self._log_every_n = int(log_every_n)
        self._ffmpeg_bin = ffmpeg_bin
        self._ffprobe_bin = ffprobe_bin

        # Dimensions learned from ffprobe at start(); _frame_bytes
        # set then too.  Until probe completes these are None.
        self._width: Optional[int] = None
        self._height: Optional[int] = None
        self._frame_bytes: Optional[int] = None

        self._latest_bgr: Optional[np.ndarray] = None
        self._latest_md5: Optional[str] = None
        self._lock = threading.Lock()
        self._running = False
        self._frame_count = 0
        self._last_capture_time = 0.0
        self._last_frame_wall = 0.0
        self._reconnect_count = 0
        self._bytes_dropped = 0
        self._proc: Optional[subprocess.Popen] = None
        self._proc_lock = threading.Lock()
        self._reader_thread: Optional[threading.Thread] = None
        self._watchdog_thread: Optional[threading.Thread] = None
        # Watchdog state: distinguish "first frame not yet seen since
        # last spawn" (use startup_grace_s) from "frames were flowing
        # and stopped" (use watchdog_s). Set at spawn, cleared at
        # first successful frame after the spawn.
        self._spawn_wall = 0.0
        self._got_frame_since_spawn = False
        # Frozen-stream detection state — owned by get_latest_bgr.
        # Tracks the streak of consecutive byte-identical reads to
        # surface a decoder-stuck symptom that all other instrumentation
        # in this module misses (frame-age stays near 0 even when the
        # underlying pixel content is frozen).
        self._consumer_last_md5: Optional[str] = None
        self._consumer_md5_streak: int = 0
        self._frozen_alerted: bool = False
        self._first_seen_frozen_age_ms: int = -1

    # ------- API parity with other FrameSource implementations -------

    @property
    def window_id(self) -> Optional[int]:
        return None

    @window_id.setter
    def window_id(self, v) -> None:
        pass  # no-op; API parity

    def start(self) -> None:
        if self._running:
            return
        # Probe dimensions BEFORE marking running so a refusal aborts
        # start() cleanly without leaving zombie threads.
        w, h = self._probe_dimensions()
        if (w, h) not in self._allowed_dimensions:
            allowed = ", ".join(
                f"{aw}x{ah}" for aw, ah in self._allowed_dimensions)
            raise RuntimeError(
                f"UDP stream at {self._url} has dimensions {w}x{h}; "
                f"not in FRAME_SOURCE_UDP_ALLOWED_DIMENSIONS allowlist "
                f"[{allowed}]. Refusing to start — silent rescaling "
                f"would mask a Mac-side regression.")
        self._width = w
        self._height = h
        self._frame_bytes = w * h * 3
        log.info(
            "[udp_frame_source] probed %dx%d (frame_bytes=%d)",
            w, h, self._frame_bytes)
        self._running = True
        self._last_frame_wall = time.monotonic()
        self._spawn_ffmpeg()
        self._reader_thread = threading.Thread(
            target=self._read_loop, daemon=True, name="udp-frame-reader")
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, daemon=True,
            name="udp-frame-watchdog")
        self._reader_thread.start()
        self._watchdog_thread.start()

    def stop(self) -> None:
        self._running = False
        self._kill_ffmpeg()
        for t in (self._reader_thread, self._watchdog_thread):
            if t is not None:
                t.join(timeout=2.0)
        self._reader_thread = None
        self._watchdog_thread = None

    def get_latest(self) -> Optional[np.ndarray]:
        """Legacy RGB-as-bgr default for drop-in compat with the rest of
        the FrameSource family.  With FRAME_COLOR_TRUE_BGR=1, returns
        native BGR straight from ffmpeg.
        """
        bgr = self.get_latest_bgr()
        if bgr is None:
            return None
        if FRAME_COLOR_TRUE_BGR:
            return bgr.copy()
        return bgr[:, :, ::-1].copy()

    def get_latest_bgr(self) -> Optional[np.ndarray]:
        with self._lock:
            frame = self._latest_bgr
            cap_ts = self._last_capture_time
            seq = self._frame_count
            md5_now = self._latest_md5
        if frame is None:
            return None
        age_ms = int((time.time() - cap_ts) * 1000) if cap_ts > 0 else -1
        if os.environ.get("UDP_FRAME_AGE_DEBUG", "0") == "1":
            print(
                f"[FRAME-AGE] consumer_get seq={seq} age_ms={age_ms} "
                f"cap_ts={cap_ts:.3f} md5={md5_now}",
                flush=True)
        # Frozen-stream detection.  When N consecutive consumer reads
        # return byte-identical content, surface a single
        # UDP-STREAM-FROZEN tag so a stuck-decoder symptom is visible
        # without waiting for VLM hallucinations downstream.
        if md5_now is not None:
            if md5_now == self._consumer_last_md5:
                self._consumer_md5_streak += 1
            else:
                self._consumer_md5_streak = 1
                self._consumer_last_md5 = md5_now
                self._frozen_alerted = False
                self._first_seen_frozen_age_ms = age_ms
            if (self._consumer_md5_streak >= _FROZEN_STREAM_THRESHOLD
                    and not self._frozen_alerted):
                self._frozen_alerted = True
                print(
                    f"[UDP-STREAM-FROZEN] md5={md5_now} "
                    f"frozen_for_reads={self._consumer_md5_streak} "
                    f"first_seen_age_ms={self._first_seen_frozen_age_ms} "
                    f"producer_seq={seq}",
                    flush=True)
                if _trace is not None:
                    try:
                        _trace.get_recorder().record(
                            tag="UDP-STREAM-FROZEN",
                            md5=md5_now,
                            frozen_for_reads=self._consumer_md5_streak,
                            first_seen_age_ms=self._first_seen_frozen_age_ms,
                            producer_seq=seq,
                        )
                    except Exception:
                        pass
        # Dump every Nth delivered frame for visual audit.
        _dump_every = int(os.environ.get("UDP_FRAME_DUMP_EVERY", "0"))
        if _dump_every > 0 and (seq % _dump_every == 0):
            try:
                import cv2 as _cv2
                _dump_path = os.path.join(
                    "/tmp", "frame_dump",
                    f"seq_{seq:06d}_ts_{int(cap_ts)}.jpg")
                os.makedirs(os.path.dirname(_dump_path), exist_ok=True)
                _cv2.imwrite(_dump_path, frame,
                             [_cv2.IMWRITE_JPEG_QUALITY, 70])
                print(f"[FRAME-DUMP] wrote {_dump_path}", flush=True)
            except Exception as _exc:
                print(f"[FRAME-DUMP] error: {_exc!r}", flush=True)
        return frame

    def get_latest_with_ts(self) -> Optional[tuple[float, np.ndarray]]:
        with self._lock:
            if self._latest_bgr is None:
                return None
            return (self._last_capture_time, self._latest_bgr)

    def get_frame_count(self) -> int:
        return self._frame_count

    def stats(self) -> dict:
        return {
            "frames": self._frame_count,
            "reconnects": self._reconnect_count,
            "bytes_dropped": self._bytes_dropped,
            "last_frame_age_s": (
                time.monotonic() - self._last_frame_wall
                if self._last_frame_wall else None),
        }

    @staticmethod
    def list_windows() -> list[dict]:
        return []

    # ----------------- ffmpeg subprocess management -----------------

    def _probe_dimensions(self) -> tuple[int, int]:
        """Run ffprobe against the URL, return (width, height).

        Retries up to ``self._probe_retries`` times with 1s sleeps —
        a probe attempted before the sender is live will simply
        timeout; the caller may want to retry the whole start().
        """
        argv = [
            self._ffprobe_bin,
            "-hide_banner",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0:s=x",
            # ffmpeg/ffprobe -timeout is in microseconds for UDP.
            "-timeout", str(int(self._probe_timeout_s * 1_000_000)),
            self._url,
        ]
        last_err: Optional[str] = None
        for attempt in range(1, self._probe_retries + 1):
            log.info(
                "[udp_frame_source] ffprobe attempt %d/%d: %s",
                attempt, self._probe_retries,
                " ".join(shlex.quote(a) for a in argv))
            try:
                cp = subprocess.run(
                    argv, capture_output=True,
                    timeout=self._probe_timeout_s + 2.0)
            except subprocess.TimeoutExpired:
                last_err = (
                    f"ffprobe timed out after "
                    f"{self._probe_timeout_s:.1f}s")
            except FileNotFoundError:
                raise RuntimeError(
                    f"ffprobe binary not found at "
                    f"{self._ffprobe_bin!r}")
            else:
                if cp.returncode != 0:
                    last_err = (
                        f"ffprobe rc={cp.returncode}; "
                        f"stderr={cp.stderr.decode(errors='replace').strip()[:200]}")
                else:
                    out = cp.stdout.decode(errors="replace").strip()
                    # csv=p=0:s=x → first line is "WxH" (csv may add
                    # a trailing 'x' field separator after the last
                    # value, and multi-stream sources can emit one
                    # record per stream — take the first parseable).
                    try:
                        first_line = out.splitlines()[0].strip().rstrip("x")
                        w_s, h_s = first_line.split("x", 1)
                        w_i, h_i = int(w_s), int(h_s)
                    except Exception:
                        last_err = (
                            f"ffprobe stdout unparseable: {out!r}")
                    else:
                        # ffprobe can return 0x0 when it sees packets
                        # but cannot identify stream params (e.g. the
                        # sender did `-c copy` from an mp4 without
                        # `-bsf:v dump_extra` so in-stream SPS/PPS
                        # never arrived). Treat as a failed probe and
                        # retry rather than handing 0x0 downstream.
                        if w_i > 0 and h_i > 0:
                            return (w_i, h_i)
                        last_err = (
                            f"ffprobe reported zero dimensions {w_i}x{h_i} "
                            f"(stream params not yet decodable; sender may "
                            f"need `-bsf:v dump_extra`)")
            if attempt < self._probe_retries:
                time.sleep(1.0)
        raise RuntimeError(
            f"ffprobe failed for {self._url} after "
            f"{self._probe_retries} attempts: {last_err}")

    def _ffmpeg_argv(self) -> list[str]:
        # ``-vsync cfr -r 30`` pins decoder output to source frame rate
        # (verified 30/1 fps on the 4621b9f8 recording, also matches
        # capture-card output of ``scripts/stream_to_server.sh``).  Without
        # it, the decoder emits dup frames at unbounded rate when input
        # gaps occur (observed 376 fps writes against a 30 fps source —
        # see ``files/scripts/vlm_diag/udp_frame_age_report.md``).
        return [
            self._ffmpeg_bin,
            "-hide_banner",
            "-loglevel", "warning",
            "-fflags", "+genpts+discardcorrupt+nobuffer",
            "-flags", "low_delay",
            "-max_delay", "0",
            "-err_detect", "ignore_err",
            "-use_wallclock_as_timestamps", "1",
            "-i", self._url,
            "-vsync", "cfr",
            "-r", "30",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-an",
            "-",
        ]

    def _spawn_ffmpeg(self) -> None:
        with self._proc_lock:
            argv = self._ffmpeg_argv()
            log.info(
                "[udp_frame_source] spawning ffmpeg: %s",
                " ".join(shlex.quote(a) for a in argv))
            self._proc = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                # Default bufsize so stdout is a BufferedReader —
                # ``read(N)`` then blocks until N bytes are available
                # (raw pipe reads otherwise return whatever's in the
                # OS buffer immediately, typically 32-64KB chunks).
                # We additionally re-accumulate in the read loop to
                # guard against partial frames on subprocess exit.
            )
            self._spawn_wall = time.monotonic()
            self._got_frame_since_spawn = False
            # Drain stderr in a side thread so a noisy decoder can't
            # block the process via pipe backpressure.
            threading.Thread(
                target=self._drain_stderr, args=(self._proc,),
                daemon=True, name="udp-frame-stderr").start()

    def _kill_ffmpeg(self) -> None:
        with self._proc_lock:
            proc = self._proc
            self._proc = None
        if proc is None:
            return
        try:
            proc.kill()
            proc.wait(timeout=2.0)
        except Exception as e:  # noqa: BLE001
            log.warning(
                "[udp_frame_source] error killing ffmpeg pid=%s: %s",
                getattr(proc, "pid", "?"), e)

    def _drain_stderr(self, proc: subprocess.Popen) -> None:
        if proc.stderr is None:
            return
        try:
            for line in iter(proc.stderr.readline, b""):
                if not line:
                    break
                msg = line.decode("utf-8", errors="replace").rstrip()
                low = msg.lower()
                if any(h in low for h in _FFMPEG_STDERR_WARN_HINTS):
                    # Surface decoder failure signatures via stderr-print
                    # so they reach the captured pipeline log regardless
                    # of how ``logging`` is configured for this module.
                    print(
                        f"[udp_frame_source] ffmpeg WARN: {msg}",
                        file=sys.stderr, flush=True)
                else:
                    log.debug("[udp_frame_source] ffmpeg: %s", msg)
        except Exception:  # noqa: BLE001
            pass

    # --------------------- read + watchdog loops ---------------------

    def _read_loop(self) -> None:
        backoff = _BACKOFF_START_S
        while self._running:
            with self._proc_lock:
                proc = self._proc
                stdout = proc.stdout if proc is not None else None
            if proc is None or stdout is None:
                time.sleep(0.05)
                continue
            # Accumulate until we have a full frame's worth of bytes
            # or hit EOF. With the default BufferedReader, ``read(N)``
            # usually fills N in one call; with raw pipes we may get
            # short reads of 32-64KB. Loop is the safe shape.
            buf = bytearray()
            need = self._frame_bytes
            eof = False
            while len(buf) < need:
                try:
                    chunk = stdout.read(need - len(buf))
                except Exception as e:  # noqa: BLE001
                    log.warning(
                        "[udp_frame_source] stdout.read raised: %s", e)
                    chunk = b""
                if not chunk:
                    eof = True
                    break
                buf.extend(chunk)
                # Bail out early if a respawn has killed the process
                # mid-read so we don't sit forever on a dead pipe.
                if not self._running:
                    break
                with self._proc_lock:
                    if self._proc is not proc:
                        break
            if eof or len(buf) < self._frame_bytes:
                # ffmpeg exited (EOF) or we were torn down mid-frame.
                # Discard partial, let watchdog handle respawn.
                self._bytes_dropped += len(buf)
                time.sleep(0.05)
                continue
            try:
                frame = np.frombuffer(
                    bytes(buf), dtype=np.uint8).reshape(
                    (self._height, self._width, 3))
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "[udp_frame_source] reshape failed: %s", e)
                self._bytes_dropped += len(buf)
                continue
            now = time.monotonic()
            _new_md5 = hashlib.md5(
                frame.ravel()[::_HASH_SAMPLE_STRIDE].tobytes()).hexdigest()
            with self._lock:
                self._latest_bgr = frame
                self._latest_md5 = _new_md5
                self._frame_count += 1
                self._last_capture_time = time.time()
                _seq = self._frame_count
                _cap_ts = self._last_capture_time
            self._last_frame_wall = now
            self._got_frame_since_spawn = True
            backoff = _BACKOFF_START_S
            if (os.environ.get("UDP_FRAME_AGE_DEBUG", "0") == "1"
                    and (_seq <= 5 or _seq % 25 == 0)):
                print(
                    f"[FRAME-AGE] producer_write seq={_seq} "
                    f"cap_ts={_cap_ts:.3f} wall_mono={now:.3f}",
                    flush=True)
            if (self._log_every_n > 0
                    and self._frame_count % self._log_every_n == 0):
                log.info(
                    "[udp_frame_source] frames=%d reconnects=%d "
                    "bytes_dropped=%d",
                    self._frame_count, self._reconnect_count,
                    self._bytes_dropped)
            # backoff variable retained for symmetry; respawn handled
            # in watchdog so the read loop only consumes bytes.
            _ = backoff

    def _watchdog_loop(self) -> None:
        backoff = _BACKOFF_START_S
        while self._running:
            time.sleep(0.5)
            with self._proc_lock:
                proc = self._proc
            proc_alive = (proc is not None and proc.poll() is None)
            # Pre-first-frame: use startup grace (tolerates mid-stream
            # UDP join sync time). Post-first-frame: use the steady-
            # state watchdog (catches mid-stream stalls quickly).
            if self._got_frame_since_spawn:
                threshold = self._watchdog_s
                age_anchor = self._last_frame_wall
            else:
                threshold = self._startup_grace_s
                age_anchor = self._spawn_wall
            stalled = (time.monotonic() - age_anchor) > threshold
            if proc_alive and not stalled:
                backoff = _BACKOFF_START_S
                continue
            if not self._running:
                return
            reason = (
                "ffmpeg exited" if not proc_alive
                else f"no frames for >{threshold:.1f}s")
            log.warning(
                "[udp_frame_source] %s — respawning ffmpeg "
                "(reconnect #%d, backoff=%.1fs)",
                reason, self._reconnect_count + 1, backoff)
            self._kill_ffmpeg()
            time.sleep(backoff)
            if not self._running:
                return
            try:
                self._spawn_ffmpeg()
                self._reconnect_count += 1
                self._last_frame_wall = time.monotonic()
                backoff = min(_BACKOFF_MAX_S, backoff * 2.0)
            except Exception as e:  # noqa: BLE001
                log.error(
                    "[udp_frame_source] ffmpeg respawn failed: %s", e)
                backoff = min(_BACKOFF_MAX_S, backoff * 2.0)
