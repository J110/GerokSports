"""Decoupled OpenScout async loop.

Runs OpenScout in a dedicated coroutine that polls a
:class:`LatestFrameSlot` directly, independent of the main pipeline's
iteration cadence.  Targets ~1.0s effective Scout cadence on the Groq
Developer plan (1K RPM / 500K RPD / 300K TPM for
``meta-llama/llama-4-scout-17b-16e-instruct``).

Why decouple: the main pipeline gates on pixel-skip, strip-presence
detection, and a ~1.3s blocking vision call, which pushes inline
OpenScout cadence to ~6 s median.  See
``files/docs/investigations/openscout_span_formation_diagnosis.md``.

Behavior:
  * Reads latest frame from slot every iteration; skips when same frame
    object as last (stale frame guard).
  * Honors :class:`OpenScoutRateGate` (per-state cadence) — does NOT
    bypass paused-view / camera-view throttling.
  * Honors :class:`TPMBudget` — sleeps until headroom rather than
    issuing calls that will 429.
  * On Groq 429: parses ``x-ratelimit-reset-tokens`` /
    ``x-ratelimit-reset-requests`` headers when available; otherwise
    sleeps a default 5 s before retrying.
  * Auto-derate: if observed TPM exceeds 80% of cap over a 60 s window,
    bumps target_interval_s by 0.25 s and logs a warning.  Restores the
    original target after 5 minutes if utilization drops below 60%.
  * Logs effective cadence + token usage every 30 s.
  * On cancel: returns cleanly via ``asyncio.CancelledError``.

The loop is fire-and-forget from the caller's perspective: failures
within an iteration are logged but never propagate.
"""
from __future__ import annotations

import asyncio
import collections
import logging
import re
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Deque, Optional

from eyes.cricket_logger import CricketLogger
from eyes.latest_frame_slot import LatestFrameSlot
from eyes.open_scout import OpenScout, OpenScoutRateGate
from eyes.tpm_budget import TPMBudget

log = CricketLogger("OPEN-SCOUT-LOOP")
_log_std = logging.getLogger("open_scout_loop")

_DEFAULT_429_BACKOFF_S = 5.0
_DERATE_STEP_S = 0.25
_DERATE_HIGH = 0.80
_DERATE_LOW = 0.60
_DERATE_RESTORE_AFTER_S = 300.0
_LOG_INTERVAL_S = 30.0
_STALE_FRAME_SLEEP_S = 0.10
_THROTTLED_SLEEP_S = 0.05

_RETRY_BUFFER_CAPACITY = 3
_RETRY_BUFFER_STALENESS_S = 5.0
_RETRY_MAX_ATTEMPTS = 2


@dataclass
class _RetryEntry:
    frame: object
    ts: float
    retry_count: int
    queued_monotonic: float
    frame_id: int


class _ScoutRetryBuffer:
    """Bounded ring of frames awaiting scout retry after a 429.

    Replaces the latest_frame_slot single-slot overwrite during
    Groq backoff: the un-scouted frame is held here instead of being
    clobbered by the next captured frame on the producer side.

    Capacity is intentionally tiny (3): bigger buffers add staleness
    without adding live-commentary value — a frame older than the
    backoff window is no longer worth scouting.
    """

    def __init__(self, capacity: int = _RETRY_BUFFER_CAPACITY,
                 staleness_s: float = _RETRY_BUFFER_STALENESS_S):
        self._capacity = capacity
        self._staleness_s = staleness_s
        self._q: Deque[_RetryEntry] = collections.deque()

    def __len__(self) -> int:
        return len(self._q)

    def is_empty(self) -> bool:
        return not self._q

    def push(self, frame, ts: float, *,
             retry_count: int) -> tuple[_RetryEntry, Optional[int]]:
        """Append a frame for retry. If full, evicts oldest and returns
        its frame_id for SCOUT-RETRY-BUFFER-OVERFLOW telemetry."""
        dropped_fid: Optional[int] = None
        if len(self._q) >= self._capacity:
            dropped_fid = self._q.popleft().frame_id
        entry = _RetryEntry(
            frame=frame, ts=ts, retry_count=retry_count,
            queued_monotonic=time.monotonic(), frame_id=id(frame))
        self._q.append(entry)
        return entry, dropped_fid

    def peek_oldest(self) -> Optional[_RetryEntry]:
        return self._q[0] if self._q else None

    def pop_oldest(self) -> Optional[_RetryEntry]:
        return self._q.popleft() if self._q else None

    def drop_stale(self, now_monotonic: float) -> list[_RetryEntry]:
        out: list[_RetryEntry] = []
        while self._q and (now_monotonic - self._q[0].queued_monotonic
                           ) > self._staleness_s:
            out.append(self._q.popleft())
        return out


# Type aliases for the optional sinks the caller may inject.
ResultSink = Callable[[object], Awaitable[None]]
PausedFn = Callable[[], bool]
CameraViewFn = Callable[[], Optional[str]]
FramePhaseFn = Callable[[], Optional[str]]


def _parse_reset_seconds(err_text: str) -> Optional[float]:
    """Extract a sleep-until value from a Groq 429 error body / message.

    Groq surfaces reset hints in two forms:
      * ``Please try again in 12.345s``
      * ``x-ratelimit-reset-tokens: 4.2s`` (in headers; the SDK often
        stitches them into the exception text)

    Returns the largest match found, or None if nothing parseable.
    """
    if not err_text:
        return None
    candidates: list[float] = []
    for pat in (r"try again in\s+([0-9]+(?:\.[0-9]+)?)\s*s",
                r"reset[-_]?(?:tokens|requests)[^0-9]*([0-9]+(?:\.[0-9]+)?)\s*s",
                r"retry[-_ ]?after[^0-9]*([0-9]+(?:\.[0-9]+)?)"):
        for m in re.finditer(pat, err_text, flags=re.IGNORECASE):
            try:
                candidates.append(float(m.group(1)))
            except (TypeError, ValueError):
                pass
    if not candidates:
        return None
    return min(60.0, max(candidates))


def _is_rate_limit(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    if "ratelimit" in name:
        return True
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status == 429:
        return True
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg or "too many requests" in msg


class _CadenceTracker:
    """Sliding window of inter-call gaps + tokens-per-call for logging."""

    def __init__(self, max_samples: int = 240):
        self._gaps: Deque[float] = collections.deque(maxlen=max_samples)
        self._tokens: Deque[int] = collections.deque(maxlen=max_samples)
        self._last_call_monotonic: Optional[float] = None
        self._calls_total = 0
        self._calls_429 = 0
        self._calls_failed = 0
        self._slot_miss = 0
        # Cumulative gap history for the [MATCH-SUMMARY] roll-up.
        self.all_gaps_s: list[float] = []

    def note_call(self, tokens: int) -> None:
        now = time.monotonic()
        if self._last_call_monotonic is not None:
            gap = now - self._last_call_monotonic
            self._gaps.append(gap)
            self.all_gaps_s.append(gap)
        self._last_call_monotonic = now
        self._tokens.append(int(tokens))
        self._calls_total += 1

    def note_429(self) -> None:
        self._calls_429 += 1

    def note_fail(self) -> None:
        self._calls_failed += 1

    def note_slot_miss(self) -> None:
        self._slot_miss += 1

    @staticmethod
    def _median(seq: list[float]) -> float:
        if not seq:
            return 0.0
        s = sorted(seq)
        n = len(s)
        return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])

    @staticmethod
    def _p90(seq: list[float]) -> float:
        if not seq:
            return 0.0
        s = sorted(seq)
        k = (len(s) - 1) * 0.9
        lo = int(k)
        hi = min(lo + 1, len(s) - 1)
        frac = k - lo
        return s[lo] + (s[hi] - s[lo]) * frac

    def snapshot(self) -> dict:
        gaps = list(self._gaps)
        tokens = list(self._tokens)
        return {
            "calls": self._calls_total,
            "calls_429": self._calls_429,
            "calls_failed": self._calls_failed,
            "slot_miss": self._slot_miss,
            "gap_mean_s": (sum(gaps) / len(gaps)) if gaps else 0.0,
            "gap_median_s": self._median([float(g) for g in gaps]),
            "gap_p90_s": self._p90([float(g) for g in gaps]),
            "tokens_mean": (sum(tokens) / len(tokens)) if tokens else 0.0,
        }


async def openscout_loop(
        *,
        slot: LatestFrameSlot,
        open_scout: OpenScout,
        gate: Optional[OpenScoutRateGate],
        tpm_budget: TPMBudget,
        target_interval_s: float = 1.0,
        result_sink: Optional[Callable[..., None]] = None,
        capture_alive_fn: Optional[Callable[[], bool]] = None,
        camera_view_fn: Optional[CameraViewFn] = None,
        frame_phase_fn: Optional[FramePhaseFn] = None,
        stop_event: Optional[asyncio.Event] = None,
) -> None:
    """Long-running coroutine.  Cancel the task to stop.

    ``result_sink`` is invoked synchronously (NOT awaited) with the
    :class:`OpenScoutResult` after each successful classify.  It MUST
    NOT block — typically a small forwarding lambda into
    ``ball_analyzer.record_open_classification`` and the shadow runner.
    """
    base_target = max(0.1, float(target_interval_s))
    current_target = base_target
    derated_until_monotonic: float = 0.0
    last_log_monotonic: float = time.monotonic()
    last_frame_id: Optional[int] = None
    tracker = _CadenceTracker()
    retry_buf = _ScoutRetryBuffer()
    try:
        from trace_emitter import get_recorder as _get_rec
    except Exception:  # noqa: BLE001
        _get_rec = None  # type: ignore[assignment]
    # Expose for match-end summary roll-up.
    try:
        open_scout._loop_tracker = tracker  # noqa: SLF001
    except Exception:  # noqa: BLE001
        pass
    # Live-monitoring v1: window-local counters reset each 30 s
    # emission so the [OPEN-SCOUT-LOOP-STATS] log line reflects the
    # window, not lifetime totals.
    from monitoring_emitters import (
        OpenScoutLoopStatsCounters, emit_open_scout_loop_stats)
    window_stats = OpenScoutLoopStatsCounters()
    last_call_monotonic_window: Optional[float] = None

    log.info(
        f"[OPEN-SCOUT-LOOP] starting, target_interval_s={base_target:.2f}, "
        f"tpm_cap={tpm_budget.cap}")

    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                break
            iter_t0 = time.monotonic()

            # Drain any retry entries that aged past the staleness window
            # during backoff. Emit EXHAUSTED so the analyzer can correlate.
            for stale in retry_buf.drop_stale(iter_t0):
                if _get_rec is not None:
                    try:
                        _get_rec().record(
                            tag="SCOUT-RETRY-EXHAUSTED",
                            frame_id=stale.frame_id,
                            retry_count=stale.retry_count,
                            reason="stale")
                    except Exception:  # noqa: BLE001
                        pass

            # Prefer a buffered (previously 429-throttled) frame over the
            # live slot. Backoff timing is unchanged; this only buys
            # survival of the un-scouted frame across the sleep. The
            # entry is peeked here and popped only at the classify
            # point — so a tpm-budget or rate-gate block on this iter
            # leaves the buffered frame intact for the next tick.
            buffered = retry_buf.peek_oldest()
            is_retry = buffered is not None
            if is_retry:
                frame = buffered.frame
                ts = buffered.ts
                frame_id = buffered.frame_id
                retry_count_in = buffered.retry_count
            else:
                latest = await slot.get_latest()
                if latest is None:
                    tracker.note_slot_miss()
                    window_stats.note_slot_miss()
                    await asyncio.sleep(_STALE_FRAME_SLEEP_S)
                    continue
                frame, ts, _set_t = latest
                frame_id = id(frame)
                if frame_id == last_frame_id:
                    tracker.note_slot_miss()
                    window_stats.note_slot_miss()
                    await asyncio.sleep(_STALE_FRAME_SLEEP_S)
                    continue
                retry_count_in = 0

            if gate is not None:
                cap_alive = True
                if capture_alive_fn is not None:
                    try:
                        cap_alive = bool(capture_alive_fn())
                    except Exception:  # noqa: BLE001
                        cap_alive = True
                cam_view = None
                phase = None
                if camera_view_fn is not None:
                    try:
                        cam_view = camera_view_fn()
                    except Exception:  # noqa: BLE001
                        cam_view = None
                if frame_phase_fn is not None:
                    try:
                        phase = frame_phase_fn()
                    except Exception:  # noqa: BLE001
                        phase = None
                if not gate.allow(time.time(),
                                  camera_view=cam_view,
                                  frame_phase=phase,
                                  capture_alive=cap_alive):
                    await asyncio.sleep(_THROTTLED_SLEEP_S)
                    continue

            wait_s = tpm_budget.reset_in_s()
            if wait_s > 0:
                log.warn(
                    f"[OPEN-SCOUT-LOOP] tpm budget exhausted, sleeping "
                    f"{wait_s:.2f}s (spend={tpm_budget.current_spend()})")
                await asyncio.sleep(min(wait_s, 5.0))
                continue

            # Consume the buffered entry now (after all gates passed).
            if is_retry:
                retry_buf.pop_oldest()
            t_call0 = time.monotonic()
            try:
                res = await open_scout.classify(frame, ts)
            except asyncio.CancelledError:
                raise
            except BaseException as exc:  # noqa: BLE001
                if _is_rate_limit(exc):
                    tracker.note_429()
                    window_stats.note_429()
                    sleep_for = (_parse_reset_seconds(str(exc))
                                 or _DEFAULT_429_BACKOFF_S)
                    log.warn(
                        f"[OPEN-SCOUT-LOOP] 429 rate-limit, sleeping "
                        f"{sleep_for:.2f}s ({exc!r})")
                    new_retry = retry_count_in + 1 if is_retry else 0
                    if new_retry >= _RETRY_MAX_ATTEMPTS:
                        if _get_rec is not None:
                            try:
                                _get_rec().record(
                                    tag="SCOUT-RETRY-EXHAUSTED",
                                    frame_id=frame_id,
                                    retry_count=new_retry,
                                    reason="max_retries")
                            except Exception:  # noqa: BLE001
                                pass
                    else:
                        _, dropped_fid = retry_buf.push(
                            frame, ts, retry_count=new_retry)
                        if _get_rec is not None:
                            try:
                                if dropped_fid is not None:
                                    _get_rec().record(
                                        tag="SCOUT-RETRY-BUFFER-OVERFLOW",
                                        dropped_frame_id=dropped_fid,
                                        current_size=len(retry_buf))
                                _get_rec().record(
                                    tag="SCOUT-RETRY-QUEUED",
                                    frame_id=frame_id,
                                    retry_count=new_retry)
                            except Exception:  # noqa: BLE001
                                pass
                    await asyncio.sleep(sleep_for)
                    continue
                tracker.note_fail()
                _log_std.exception("openscout loop classify error")
                await asyncio.sleep(0.5)
                continue
            if is_retry and _get_rec is not None:
                try:
                    _get_rec().record(
                        tag="SCOUT-RETRY-SUCCESS",
                        frame_id=frame_id,
                        retry_count=retry_count_in,
                        latency_ms=int((time.monotonic() - t_call0) * 1000))
                except Exception:  # noqa: BLE001
                    pass

            last_frame_id = frame_id
            if res is not None:
                tokens = int(getattr(res, "tokens_total", 0) or 0)
                if tokens > 0:
                    tpm_budget.record(tokens)
                tracker.note_call(tokens)
                _now_w = time.monotonic()
                _gap_w = (None if last_call_monotonic_window is None
                          else _now_w - last_call_monotonic_window)
                last_call_monotonic_window = _now_w
                window_stats.note_call(gap_s=_gap_w, tokens=tokens)
                if result_sink is not None:
                    try:
                        result_sink(res)
                    except Exception:  # noqa: BLE001
                        _log_std.exception(
                            "openscout loop result_sink error")

            now = time.monotonic()
            util = tpm_budget.utilization()
            if (util >= _DERATE_HIGH
                    and current_target < base_target + 1.5):
                current_target = round(
                    current_target + _DERATE_STEP_S, 3)
                derated_until_monotonic = now + _DERATE_RESTORE_AFTER_S
                log.warn(
                    f"[OPEN-SCOUT-LOOP] tpm util={util:.0%} >= "
                    f"{_DERATE_HIGH:.0%}, derate target_interval_s -> "
                    f"{current_target:.2f}")
            elif (current_target > base_target
                  and util < _DERATE_LOW
                  and now >= derated_until_monotonic):
                log.info(
                    f"[OPEN-SCOUT-LOOP] tpm util={util:.0%} < "
                    f"{_DERATE_LOW:.0%}, restore target_interval_s -> "
                    f"{base_target:.2f}")
                current_target = base_target

            if (now - last_log_monotonic) >= _LOG_INTERVAL_S:
                derate_active = current_target > base_target
                util_tpm_pct = util * 100.0
                from monitoring_emitters import (
                    check_tpm_alarm as _check_tpm_alarm,
                    _median as _gap_median)
                _median_gap_s = _gap_median(window_stats.gaps_s)
                _alarm_msg = _check_tpm_alarm(
                    util_tpm_pct=util_tpm_pct,
                    median_gap_s=_median_gap_s,
                    derate_active=derate_active,
                    window_s=int(_LOG_INTERVAL_S))
                emit_open_scout_loop_stats(
                    window_stats,
                    window_s=int(_LOG_INTERVAL_S),
                    target_s=current_target,
                    util_tpm_pct=util_tpm_pct,
                    derate_active=derate_active,
                    logger=_log_std,
                )
                if _alarm_msg is not None:
                    _log_std.warning(_alarm_msg)
                last_log_monotonic = now

            elapsed = time.monotonic() - iter_t0
            if elapsed < current_target:
                await asyncio.sleep(current_target - elapsed)
    except asyncio.CancelledError:
        log.info("[OPEN-SCOUT-LOOP] cancelled, shutting down cleanly")
        raise


__all__ = ["openscout_loop"]
