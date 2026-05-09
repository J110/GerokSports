"""Rolling 60-second tokens-per-minute budget tracker.

Used by the decoupled OpenScout loop to back off before the Groq Developer
plan TPM cap (300K for ``meta-llama/llama-4-scout-17b-16e-instruct``)
forces a 429.  Default cap is 240K (80% of 300K) to leave burst headroom
for prompt-cache misses or temporary token-count drift.

Usage::

    budget = TPMBudget(cap=240_000)
    if budget.exhausted():
        await asyncio.sleep(budget.reset_in_s())
        continue
    resp = await client.call(...)
    budget.record(resp.usage.total_tokens)

The budget is monotonic-clock based so behavior is independent of wall
clock skew.  Records older than 60 s are evicted lazily on each query.
"""
from __future__ import annotations

import collections
import threading
import time
from typing import Deque, Tuple


class TPMBudget:
    """Rolling 60s token spend cap."""

    def __init__(self, *, cap: int = 240_000, window_s: float = 60.0):
        self._cap = int(cap)
        self._window_s = float(window_s)
        self._records: Deque[Tuple[float, int]] = collections.deque()
        self._lock = threading.Lock()

    @property
    def cap(self) -> int:
        return self._cap

    def _evict(self, now: float) -> None:
        cutoff = now - self._window_s
        while self._records and self._records[0][0] < cutoff:
            self._records.popleft()

    def record(self, tokens: int) -> None:
        if tokens <= 0:
            return
        now = time.monotonic()
        with self._lock:
            self._evict(now)
            self._records.append((now, int(tokens)))

    def current_spend(self) -> int:
        now = time.monotonic()
        with self._lock:
            self._evict(now)
            return sum(t for _, t in self._records)

    def utilization(self) -> float:
        if self._cap <= 0:
            return 0.0
        return self.current_spend() / float(self._cap)

    def exhausted(self, *, projected_call_tokens: int = 0) -> bool:
        return (self.current_spend() + max(0, int(projected_call_tokens))
                >= self._cap)

    def reset_in_s(self) -> float:
        """Seconds until enough headroom exists to fit one more call.

        Returns 0 if not currently exhausted.  Otherwise returns the time
        until the oldest record falls out of the rolling window.
        """
        now = time.monotonic()
        with self._lock:
            self._evict(now)
            if sum(t for _, t in self._records) < self._cap:
                return 0.0
            if not self._records:
                return 0.0
            oldest_ts = self._records[0][0]
            return max(0.0, (oldest_ts + self._window_s) - now)


__all__ = ["TPMBudget"]
