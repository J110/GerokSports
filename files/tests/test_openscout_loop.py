"""Unit tests for the decoupled OpenScout async loop.

Stubs OpenScout + frame source so the loop can be exercised at high
speed (target_interval_s=0.05) without hitting Groq.  Verifies:
  * cadence stays within tolerance under nominal latency
  * 429 backoff path doesn't crash and resumes the loop
  * TPM auto-derate fires when budget is exhausted
  * graceful shutdown via task.cancel()
  * stale-frame guard skips when the slot returns the same object
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

import numpy as np
import pytest

from eyes.latest_frame_slot import LatestFrameSlot
from eyes.openscout_loop import (
    _is_rate_limit,
    _parse_reset_seconds,
    openscout_loop,
)
from eyes.tpm_budget import TPMBudget


class _StubResult:
    def __init__(self, ts: float, tokens_total: int = 1000):
        self.timestamp = ts
        self.frame_class = "action"
        self.raw_description = "stub"
        self.tokens_total = tokens_total


class _StubScout:
    def __init__(self,
                 *,
                 latency_s: float = 0.01,
                 tokens_per_call: int = 1000,
                 raise_429_for_n_calls: int = 0,
                 raise_other_for_n_calls: int = 0):
        self.latency_s = latency_s
        self.tokens_per_call = tokens_per_call
        self._429_left = raise_429_for_n_calls
        self._other_left = raise_other_for_n_calls
        self.calls = 0

    async def classify(self, frame, ts, frame_idx=None):
        self.calls += 1
        await asyncio.sleep(self.latency_s)
        if self._429_left > 0:
            self._429_left -= 1
            err = RuntimeError("429 too many requests, try again in 0.05s")
            err.status_code = 429
            raise err
        if self._other_left > 0:
            self._other_left -= 1
            raise RuntimeError("transient")
        return _StubResult(ts, tokens_total=self.tokens_per_call)


class _Slot:
    """Minimal LatestFrameSlot stand-in that cycles unique frames."""

    def __init__(self, *, static: bool = False):
        self._static = static
        self._counter = 0
        self._fixed = np.zeros((4, 4, 3), dtype=np.uint8)

    async def get_latest(self):
        if self._static:
            return (self._fixed, time.time(), time.monotonic())
        self._counter += 1
        f = np.full((4, 4, 3), self._counter % 255, dtype=np.uint8)
        return (f, time.time(), time.monotonic())


def test_parse_reset_seconds():
    assert _parse_reset_seconds(
        "Rate limit reached. Please try again in 1.5s.") == pytest.approx(1.5)
    assert _parse_reset_seconds(
        "x-ratelimit-reset-tokens: 0.8s") == pytest.approx(0.8)
    assert _parse_reset_seconds("retry-after: 12") == pytest.approx(12.0)
    assert _parse_reset_seconds("nothing here") is None


def test_is_rate_limit_detects_429():
    err = RuntimeError("429 too many requests")
    assert _is_rate_limit(err)
    err2 = RuntimeError("connection reset")
    assert not _is_rate_limit(err2)
    err3 = RuntimeError("nope")
    err3.status_code = 429
    assert _is_rate_limit(err3)


@pytest.mark.asyncio
async def test_loop_cadence_within_tolerance():
    slot = _Slot()
    scout = _StubScout(latency_s=0.005, tokens_per_call=100)
    budget = TPMBudget(cap=1_000_000)
    target = 0.05
    task = asyncio.create_task(openscout_loop(
        slot=slot, open_scout=scout, gate=None, tpm_budget=budget,
        target_interval_s=target))
    await asyncio.sleep(0.6)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    expected = 0.6 / target
    assert scout.calls >= int(expected * 0.7), (
        f"too few calls: got {scout.calls}, expected ~{int(expected)}")
    assert scout.calls <= int(expected * 1.4), (
        f"too many calls: got {scout.calls}, expected ~{int(expected)}")


@pytest.mark.asyncio
async def test_loop_survives_429_and_resumes():
    slot = _Slot()
    scout = _StubScout(latency_s=0.005, raise_429_for_n_calls=2)
    budget = TPMBudget(cap=1_000_000)
    task = asyncio.create_task(openscout_loop(
        slot=slot, open_scout=scout, gate=None, tpm_budget=budget,
        target_interval_s=0.05))
    await asyncio.sleep(0.5)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert scout.calls >= 3, (
        f"loop did not resume after 429: {scout.calls} calls")


@pytest.mark.asyncio
async def test_loop_survives_generic_exception():
    slot = _Slot()
    scout = _StubScout(latency_s=0.005, raise_other_for_n_calls=2)
    budget = TPMBudget(cap=1_000_000)
    task = asyncio.create_task(openscout_loop(
        slot=slot, open_scout=scout, gate=None, tpm_budget=budget,
        target_interval_s=0.05))
    await asyncio.sleep(0.5)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert scout.calls >= 3


@pytest.mark.asyncio
async def test_tpm_budget_blocks_calls_when_exhausted():
    """If budget is pre-filled to the cap, loop must back off and
    not call classify before headroom returns."""
    slot = _Slot()
    scout = _StubScout(latency_s=0.005, tokens_per_call=10)
    budget = TPMBudget(cap=100, window_s=60.0)
    budget.record(150)
    task = asyncio.create_task(openscout_loop(
        slot=slot, open_scout=scout, gate=None, tpm_budget=budget,
        target_interval_s=0.05))
    await asyncio.sleep(0.3)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert scout.calls == 0, (
        f"loop should have backed off; got {scout.calls} calls")


@pytest.mark.asyncio
async def test_graceful_shutdown_via_cancel():
    slot = _Slot()
    scout = _StubScout(latency_s=0.01)
    budget = TPMBudget(cap=1_000_000)
    task = asyncio.create_task(openscout_loop(
        slot=slot, open_scout=scout, gate=None, tpm_budget=budget,
        target_interval_s=0.05))
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_stale_frame_skipped():
    slot = _Slot(static=True)
    scout = _StubScout(latency_s=0.005)
    budget = TPMBudget(cap=1_000_000)
    task = asyncio.create_task(openscout_loop(
        slot=slot, open_scout=scout, gate=None, tpm_budget=budget,
        target_interval_s=0.05))
    await asyncio.sleep(0.5)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert scout.calls == 1, (
        f"stale-frame guard failed: expected 1 call, got {scout.calls}")


@pytest.mark.asyncio
async def test_result_sink_invoked():
    slot = _Slot()
    scout = _StubScout(latency_s=0.005)
    budget = TPMBudget(cap=1_000_000)
    received: list = []
    task = asyncio.create_task(openscout_loop(
        slot=slot, open_scout=scout, gate=None, tpm_budget=budget,
        target_interval_s=0.05,
        result_sink=lambda r: received.append(r)))
    await asyncio.sleep(0.3)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert len(received) >= 1
    assert received[0].frame_class == "action"


@pytest.mark.asyncio
async def test_latest_frame_slot_set_get_roundtrip():
    slot = LatestFrameSlot()
    f = np.zeros((2, 2, 3), dtype=np.uint8)
    assert await slot.get_latest() is None
    slot.set(f, ts=12.5)
    got = await slot.get_latest()
    assert got is not None
    frame, ts, _set_t = got
    assert frame is f
    assert ts == 12.5


@pytest.mark.asyncio
async def test_latest_frame_slot_pull_mode():
    f = np.zeros((2, 2, 3), dtype=np.uint8)
    calls = {"n": 0}

    def _src():
        calls["n"] += 1
        return f

    slot = LatestFrameSlot(source_fn=_src)
    got = await slot.get_latest()
    assert got is not None
    assert got[0] is f
    assert calls["n"] == 1


def _retry_tags(records: list[dict]) -> list[str]:
    return [r["tag"] for r in records if r["tag"].startswith("SCOUT-RETRY-")]


@pytest.mark.asyncio
async def test_429_buffer_queued_then_success(monkeypatch):
    """One 429 then success: SCOUT-RETRY-QUEUED on the failure,
    SCOUT-RETRY-SUCCESS on the retry of the SAME frame (not the
    overwriting next-tick frame)."""
    from trace_emitter import get_recorder
    rec = get_recorder()
    rec.begin_frame(0)
    slot = _Slot()
    scout = _StubScout(latency_s=0.005, raise_429_for_n_calls=1)
    budget = TPMBudget(cap=1_000_000)
    task = asyncio.create_task(openscout_loop(
        slot=slot, open_scout=scout, gate=None, tpm_budget=budget,
        target_interval_s=0.05))
    await asyncio.sleep(0.4)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    tags = _retry_tags(rec.drain())
    assert "SCOUT-RETRY-QUEUED" in tags, tags
    assert "SCOUT-RETRY-SUCCESS" in tags, tags
    # Order: QUEUED must precede SUCCESS for the same frame_id.
    assert tags.index("SCOUT-RETRY-QUEUED") < tags.index("SCOUT-RETRY-SUCCESS")


@pytest.mark.asyncio
async def test_429_buffer_exhausted_after_max_retries():
    """A frame that keeps 429-ing must eventually drop with
    SCOUT-RETRY-EXHAUSTED. With _RETRY_MAX_ATTEMPTS=2 the retry_count
    reaches 2 after the second queue, so the third 429 on that same
    frame trips the exhaust path."""
    from trace_emitter import get_recorder
    rec = get_recorder()
    rec.begin_frame(0)
    slot = _Slot()
    scout = _StubScout(latency_s=0.005, raise_429_for_n_calls=3)
    budget = TPMBudget(cap=1_000_000)
    import eyes.openscout_loop as loop_mod
    orig = loop_mod._DEFAULT_429_BACKOFF_S
    loop_mod._DEFAULT_429_BACKOFF_S = 0.02
    try:
        task = asyncio.create_task(openscout_loop(
            slot=slot, open_scout=scout, gate=None, tpm_budget=budget,
            target_interval_s=0.05))
        await asyncio.sleep(0.4)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    finally:
        loop_mod._DEFAULT_429_BACKOFF_S = orig
    tags = _retry_tags(rec.drain())
    assert "SCOUT-RETRY-QUEUED" in tags, tags
    assert "SCOUT-RETRY-EXHAUSTED" in tags, tags


@pytest.mark.asyncio
async def test_clean_run_emits_no_retry_tags():
    """No 429s, no SCOUT-RETRY-* tags. The buffer must stay empty
    on the happy path."""
    from trace_emitter import get_recorder
    rec = get_recorder()
    rec.begin_frame(0)
    slot = _Slot()
    scout = _StubScout(latency_s=0.005)
    budget = TPMBudget(cap=1_000_000)
    task = asyncio.create_task(openscout_loop(
        slot=slot, open_scout=scout, gate=None, tpm_budget=budget,
        target_interval_s=0.05))
    await asyncio.sleep(0.3)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    tags = _retry_tags(rec.drain())
    assert tags == [], f"unexpected retry tags on clean run: {tags}"


def test_retry_buffer_unit():
    """Direct unit test of the buffer ring semantics."""
    from eyes.openscout_loop import _ScoutRetryBuffer
    buf = _ScoutRetryBuffer(capacity=3, staleness_s=0.5)
    a, b, c, d = object(), object(), object(), object()
    assert buf.is_empty()
    e1, drop1 = buf.push(a, ts=1.0, retry_count=0)
    e2, drop2 = buf.push(b, ts=2.0, retry_count=0)
    e3, drop3 = buf.push(c, ts=3.0, retry_count=0)
    assert drop1 is drop2 is drop3 is None
    assert len(buf) == 3
    # 4th push must evict the oldest (a)
    e4, drop4 = buf.push(d, ts=4.0, retry_count=0)
    assert drop4 == id(a)
    assert len(buf) == 3
    # peek+pop ordering: b is now oldest
    assert buf.peek_oldest().frame is b
    assert buf.pop_oldest().frame is b
    assert buf.pop_oldest().frame is c
    assert buf.pop_oldest().frame is d
    assert buf.is_empty()


def test_tpm_budget_basic():
    b = TPMBudget(cap=1000, window_s=60.0)
    assert not b.exhausted()
    assert b.reset_in_s() == 0.0
    b.record(500)
    assert b.current_spend() == 500
    b.record(600)
    assert b.exhausted()
    assert b.reset_in_s() > 0
