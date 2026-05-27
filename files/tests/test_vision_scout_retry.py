"""Track 1 (Vision._scout_call) 429-retry tests — F130-class fix.

Pattern A: in-call retry once on Groq 429. Validates:
  - SCOUT-RETRY-IN-CALL-QUEUED fires on the 429
  - SCOUT-RETRY-IN-CALL-SUCCESS fires after the backoff retry
  - The returned content is from the SECOND (successful) call
  - Clean call: zero SCOUT-RETRY-IN-CALL-* tags
  - Two consecutive 429s: SCOUT-RETRY-IN-CALL-EXHAUSTED fires
  - Non-429 first failure: no retry path
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from eyes.tpm_budget import TPMBudget
from eyes.vision import Vision


def _make_vision_stub() -> Vision:
    """Build a Vision without invoking __init__ (which constructs
    AsyncGroq from env). Only the fields _scout_call touches are set."""
    v = Vision.__new__(Vision)
    v._replay_cache = {}
    v._replay_cap_idx_cache = {}
    v._replay_sequence = []
    v._replay_sequence_index = 0
    v._replay_mode = "frame_id"
    v._replay_strict = False
    v._replay_nearest_tolerance = 2
    v._replay_log_enabled = False
    v._scout_tpm_budget = None
    v._scout_tpm_estimate = 6000
    v._scout_tpm_on_exhaust = "sleep"
    v._raw_dump_fp = None
    return v


class _FakeUsage:
    total_tokens = 420
    completion_tokens = 42


class _FakeChoice:
    def __init__(self, content: str):
        self.message = SimpleNamespace(content=content)
        self.finish_reason = "stop"


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage()


class _StubGroq:
    """AsyncGroq stand-in. ``script`` is a list of "raise|return" items
    consumed left-to-right per call."""

    def __init__(self, script):
        self.script = list(script)
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create))
        self.calls = 0

    async def _create(self, **_kwargs):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def _retry_tags(records):
    return [r["tag"] for r in records
            if r["tag"].startswith("SCOUT-RETRY-IN-CALL-")]


def _make_429(msg: str = "Rate limit reached. Please try again in 0.05s"):
    err = RuntimeError(msg)
    err.status_code = 429
    return err


def test_scout_replay_log_indexes_frame_id_and_cap_idx(tmp_path, monkeypatch):
    replay_log = tmp_path / "scout_raw.jsonl"
    replay_log.write_text(
        json.dumps({
            "frame_id": 10,
            "cap_idx": 20,
            "raw_response": "CACHED_WITH_BOTH",
        }) + "\n"
        + json.dumps({
            "cap_idx": 21,
            "raw_response": "CACHED_CAP_ONLY",
        }) + "\n")

    monkeypatch.setenv("SCOUT_REPLAY_LOG", str(replay_log))
    monkeypatch.setenv("SCOUT_REPLAY_MODE", "nearest_cap_idx")
    monkeypatch.delenv("SCOUT_RAW_DUMP", raising=False)

    with patch("eyes.vision.AsyncGroq", return_value=SimpleNamespace()):
        v = Vision()

    assert v._replay_mode == "nearest_cap_idx"
    assert v._replay_cache == {10: "CACHED_WITH_BOTH"}
    assert v._replay_cap_idx_cache == {
        20: "CACHED_WITH_BOTH",
        21: "CACHED_CAP_ONLY",
    }
    assert v._replay_sequence == [
        (10, "CACHED_WITH_BOTH"),
        (None, "CACHED_CAP_ONLY"),
    ]


@pytest.mark.asyncio
async def test_scout_call_429_then_success():
    from trace_emitter import get_recorder
    rec = get_recorder()
    rec.begin_frame(0)
    v = _make_vision_stub()
    v._groq = _StubGroq([_make_429(), _FakeResponse("OK_AFTER_RETRY")])
    with patch("eyes.vision.get_global_frame", return_value=42):
        out = await v._scout_call("ABC", "prompt")
    assert out == "OK_AFTER_RETRY"
    assert v._groq.calls == 2
    tags = _retry_tags(rec.drain())
    assert "SCOUT-RETRY-IN-CALL-QUEUED" in tags
    assert "SCOUT-RETRY-IN-CALL-SUCCESS" in tags
    assert tags.index("SCOUT-RETRY-IN-CALL-QUEUED") < \
        tags.index("SCOUT-RETRY-IN-CALL-SUCCESS")


@pytest.mark.asyncio
async def test_scout_call_clean_emits_no_retry_tags():
    from trace_emitter import get_recorder
    rec = get_recorder()
    rec.begin_frame(0)
    v = _make_vision_stub()
    v._groq = _StubGroq([_FakeResponse("FIRST_TRY_OK")])
    with patch("eyes.vision.get_global_frame", return_value=7):
        out = await v._scout_call("ABC", "prompt")
    assert out == "FIRST_TRY_OK"
    assert v._groq.calls == 1
    tags = _retry_tags(rec.drain())
    assert tags == [], f"unexpected retry tags: {tags}"


@pytest.mark.asyncio
async def test_scout_call_two_429s_exhausted():
    from trace_emitter import get_recorder
    rec = get_recorder()
    rec.begin_frame(0)
    v = _make_vision_stub()
    v._groq = _StubGroq([_make_429(), _make_429()])
    with patch("eyes.vision.get_global_frame", return_value=9):
        out = await v._scout_call("ABC", "prompt")
    assert out is None
    assert v._groq.calls == 2
    tags = _retry_tags(rec.drain())
    assert "SCOUT-RETRY-IN-CALL-QUEUED" in tags
    assert "SCOUT-RETRY-IN-CALL-EXHAUSTED" in tags
    assert "SCOUT-RETRY-IN-CALL-SUCCESS" not in tags


@pytest.mark.asyncio
async def test_scout_call_non_429_no_retry():
    from trace_emitter import get_recorder
    rec = get_recorder()
    rec.begin_frame(0)
    v = _make_vision_stub()
    v._groq = _StubGroq([RuntimeError("connection reset")])
    with patch("eyes.vision.get_global_frame", return_value=11):
        out = await v._scout_call("ABC", "prompt")
    assert out is None
    assert v._groq.calls == 1
    tags = _retry_tags(rec.drain())
    assert tags == [], f"non-429 must not trigger retry path: {tags}"


@pytest.mark.asyncio
async def test_scout_replay_strict_frame_id_miss_does_not_call_groq():
    v = _make_vision_stub()
    v._groq = _StubGroq([_FakeResponse("LIVE_SHOULD_NOT_RUN")])
    v._replay_log_enabled = True
    v._replay_strict = True
    v._replay_cache = {99: "CACHED_OTHER_FRAME"}

    with patch("eyes.vision.get_global_frame", return_value=42):
        out = await v._scout_call("ABC", "prompt")

    assert out is None
    assert v._groq.calls == 0


@pytest.mark.asyncio
async def test_scout_replay_sequence_consumes_in_file_order_without_groq():
    v = _make_vision_stub()
    v._groq = _StubGroq([_FakeResponse("LIVE_SHOULD_NOT_RUN")])
    v._replay_log_enabled = True
    v._replay_mode = "sequence"
    v._replay_sequence = [(10, "CACHED_FIRST"), (20, "CACHED_SECOND")]

    with patch("eyes.vision.get_global_frame", return_value=101):
        first = await v._scout_call("ABC", "prompt")
    with patch("eyes.vision.get_global_frame", return_value=102):
        second = await v._scout_call("ABC", "prompt")

    assert first == "CACHED_FIRST"
    assert second == "CACHED_SECOND"
    assert v._replay_sequence_index == 2
    assert v._groq.calls == 0


@pytest.mark.asyncio
async def test_scout_replay_sequence_strict_exhausted_does_not_call_groq():
    v = _make_vision_stub()
    v._groq = _StubGroq([_FakeResponse("LIVE_SHOULD_NOT_RUN")])
    v._replay_log_enabled = True
    v._replay_mode = "sequence"
    v._replay_strict = True
    v._replay_sequence = []

    with patch("eyes.vision.get_global_frame", return_value=7):
        out = await v._scout_call("ABC", "prompt")

    assert out is None
    assert v._groq.calls == 0


@pytest.mark.asyncio
async def test_scout_replay_nearest_frame_uses_close_cached_response():
    v = _make_vision_stub()
    v._groq = _StubGroq([_FakeResponse("LIVE_SHOULD_NOT_RUN")])
    v._replay_log_enabled = True
    v._replay_mode = "nearest_frame"
    v._replay_cache = {40: "CACHED_40", 44: "CACHED_44"}

    with patch("eyes.vision.get_global_frame", return_value=42):
        out = await v._scout_call("ABC", "prompt")

    assert out == "CACHED_40"
    assert v._groq.calls == 0


@pytest.mark.asyncio
async def test_scout_replay_nearest_strict_miss_returns_empty_without_groq():
    v = _make_vision_stub()
    v._groq = _StubGroq([_FakeResponse("LIVE_SHOULD_NOT_RUN")])
    v._replay_log_enabled = True
    v._replay_mode = "nearest_frame"
    v._replay_strict = True
    v._replay_cache = {39: "TOO_FAR"}

    with patch("eyes.vision.get_global_frame", return_value=42):
        out = await v._scout_call("ABC", "prompt")

    assert out == ""
    assert v._groq.calls == 0


@pytest.mark.asyncio
async def test_scout_replay_nearest_cap_idx_prefers_cap_idx_cache():
    v = _make_vision_stub()
    v._groq = _StubGroq([_FakeResponse("LIVE_SHOULD_NOT_RUN")])
    v._replay_log_enabled = True
    v._replay_mode = "nearest_cap_idx"
    v._replay_cache = {42: "FRAME_CACHE"}
    v._replay_cap_idx_cache = {43: "CAP_CACHE"}

    with patch("eyes.vision.get_global_frame", return_value=42):
        out = await v._scout_call("ABC", "prompt")

    assert out == "CAP_CACHE"
    assert v._groq.calls == 0


@pytest.mark.asyncio
async def test_scout_tpm_budget_waits_before_groq_when_exceeded():
    v = _make_vision_stub()
    v._groq = _StubGroq([_FakeResponse("AFTER_GATE")])
    v._scout_tpm_budget = TPMBudget(cap=100)
    v._scout_tpm_budget.record(80)
    v._scout_tpm_estimate = 50
    sleeps: list[float] = []

    async def _fake_sleep(seconds: float):
        assert v._groq.calls == 0
        sleeps.append(seconds)
        with v._scout_tpm_budget._lock:
            v._scout_tpm_budget._records.clear()

    with patch("eyes.vision.asyncio.sleep", _fake_sleep):
        with patch("eyes.vision.get_global_frame", return_value=42):
            out = await v._scout_call("ABC", "prompt")

    assert out == "AFTER_GATE"
    assert sleeps and sleeps[0] > 0
    assert v._groq.calls == 1
    assert v._scout_tpm_budget.current_spend() == 50


@pytest.mark.asyncio
async def test_scout_tpm_budget_reserves_estimate_before_next_call():
    v = _make_vision_stub()
    v._groq = _StubGroq([
        _FakeResponse("FIRST"),
        _FakeResponse("SECOND"),
    ])
    v._scout_tpm_budget = TPMBudget(cap=100)
    v._scout_tpm_estimate = 60
    sleeps: list[float] = []

    async def _fake_sleep(seconds: float):
        assert v._groq.calls == 1
        sleeps.append(seconds)
        with v._scout_tpm_budget._lock:
            v._scout_tpm_budget._records.clear()

    with patch("eyes.vision.asyncio.sleep", _fake_sleep):
        with patch("eyes.vision.get_global_frame", return_value=42):
            first = await v._scout_call("ABC", "prompt")
            second = await v._scout_call("ABC", "prompt")

    assert first == "FIRST"
    assert second == "SECOND"
    assert sleeps and sleeps[0] > 0
    assert v._groq.calls == 2
    assert v._scout_tpm_budget.current_spend() == 60


@pytest.mark.asyncio
async def test_scout_tpm_budget_default_off_does_not_sleep():
    v = _make_vision_stub()
    v._groq = _StubGroq([_FakeResponse("NO_GATE")])

    async def _unexpected_sleep(_seconds: float):
        raise AssertionError("default Scout TPM gate must not sleep")

    with patch("eyes.vision.asyncio.sleep", _unexpected_sleep):
        with patch("eyes.vision.get_global_frame", return_value=42):
            out = await v._scout_call("ABC", "prompt")

    assert out == "NO_GATE"
    assert v._groq.calls == 1


@pytest.mark.asyncio
async def test_scout_tpm_budget_empty_mode_skips_without_sleep_or_groq():
    v = _make_vision_stub()
    v._groq = _StubGroq([_FakeResponse("SHOULD_NOT_CALL")])
    v._scout_tpm_budget = TPMBudget(cap=100)
    v._scout_tpm_budget.record(80)
    v._scout_tpm_estimate = 50
    v._scout_tpm_on_exhaust = "empty"

    async def _unexpected_sleep(_seconds: float):
        raise AssertionError("empty mode must not sleep")

    with patch("eyes.vision.asyncio.sleep", _unexpected_sleep):
        with patch("eyes.vision.get_global_frame", return_value=42):
            out = await v._scout_call("ABC", "prompt")

    assert out == ""
    assert v._groq.calls == 0
    assert v._scout_tpm_budget.current_spend() == 80


@pytest.mark.asyncio
async def test_scout_tpm_budget_empty_mode_allows_when_under_budget():
    v = _make_vision_stub()
    v._groq = _StubGroq([_FakeResponse("UNDER_BUDGET")])
    v._scout_tpm_budget = TPMBudget(cap=100)
    v._scout_tpm_estimate = 50
    v._scout_tpm_on_exhaust = "empty"

    async def _unexpected_sleep(_seconds: float):
        raise AssertionError("under-budget empty mode must not sleep")

    with patch("eyes.vision.asyncio.sleep", _unexpected_sleep):
        with patch("eyes.vision.get_global_frame", return_value=42):
            out = await v._scout_call("ABC", "prompt")

    assert out == "UNDER_BUDGET"
    assert v._groq.calls == 1
    assert v._scout_tpm_budget.current_spend() == 50
