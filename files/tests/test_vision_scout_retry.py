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
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from eyes.vision import Vision


def _make_vision_stub() -> Vision:
    """Build a Vision without invoking __init__ (which constructs
    AsyncGroq from env). Only the fields _scout_call touches are set."""
    v = Vision.__new__(Vision)
    v._replay_cache = {}
    v._raw_dump_fp = None
    return v


class _FakeUsage:
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
