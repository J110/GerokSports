"""GPU Monitor — measures idle time available for future Qwen 3.

Tracks when the GPU is busy (Qwen 1/2 running) vs idle (OCR only).
Prints stats every 30 seconds so we know exactly how much headroom
Qwen 3 would have for between-delivery analysis.
"""
from __future__ import annotations

import time

from eyes.cricket_logger import CricketLogger

log = CricketLogger("GPU")


class GPUMonitor:
    """Tracks GPU busy/idle time for capacity planning."""

    PRINT_INTERVAL = 30.0  # seconds between stat prints

    def __init__(self):
        self._start_time = time.time()
        self._busy_seconds: float = 0.0
        self._idle_seconds: float = 0.0
        self._current_start: float | None = None
        self._current_role: str | None = None
        self._last_end: float = time.time()
        self._last_print: float = time.time()

        self._calls: list[dict] = []  # [{role, start, end, duration}]
        self._idle_gaps: list[float] = []  # seconds between Qwen calls

    def on_qwen_start(self, role: str, frame: int):
        """Called when a Qwen model call begins."""
        now = time.time()
        if self._current_start is None:
            idle_gap = now - self._last_end
            self._idle_seconds += idle_gap
            if idle_gap > 0.5:
                self._idle_gaps.append(idle_gap)
        self._current_start = now
        self._current_role = role
        log.info(f"Qwen {role} started (frame {frame})")

    def on_qwen_end(self, role: str, frame: int, duration: float):
        """Called when a Qwen model call finishes."""
        now = time.time()
        self._busy_seconds += duration
        self._last_end = now
        self._calls.append({
            "role": role,
            "frame": frame,
            "duration": duration,
            "timestamp": now,
        })
        self._current_start = None
        self._current_role = None
        log.info(f"Qwen {role} finished in {duration:.1f}s (frame {frame})")

    def on_frame_end(self, frame: int):
        """Called at end of each frame to accumulate idle time."""
        now = time.time()
        if self._current_start is None:
            # GPU is idle right now
            pass

        if now - self._last_print >= self.PRINT_INTERVAL:
            self.print_stats()
            self._last_print = now

    def print_stats(self):
        elapsed = time.time() - self._start_time
        if elapsed < 1.0:
            return

        total = self._busy_seconds + self._idle_seconds
        if total < 1.0:
            total = elapsed

        busy_pct = (self._busy_seconds / total) * 100
        idle_pct = (self._idle_seconds / total) * 100
        avg_gap = (sum(self._idle_gaps) / len(self._idle_gaps)) if self._idle_gaps else 0

        log.info(
            f"Busy: {self._busy_seconds:.1f}s ({busy_pct:.0f}%) | "
            f"Idle: {self._idle_seconds:.1f}s ({idle_pct:.0f}%) | "
            f"Avg gap: {avg_gap:.1f}s | "
            f"Calls: {len(self._calls)}"
        )

    def get_stats(self) -> dict:
        elapsed = time.time() - self._start_time
        total = max(self._busy_seconds + self._idle_seconds, elapsed, 1.0)
        avg_gap = (sum(self._idle_gaps) / len(self._idle_gaps)) if self._idle_gaps else 0
        return {
            "busy_seconds": round(self._busy_seconds, 1),
            "idle_seconds": round(self._idle_seconds, 1),
            "busy_pct": round((self._busy_seconds / total) * 100, 1),
            "idle_pct": round((self._idle_seconds / total) * 100, 1),
            "avg_idle_gap": round(avg_gap, 1),
            "total_calls": len(self._calls),
            "elapsed": round(elapsed, 1),
        }

    def reset(self):
        self.__init__()
