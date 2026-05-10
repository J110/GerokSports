"""$0 smoke for the Vision SCOUT_RAW_DUMP / SCOUT_REPLAY_LOG paths.

Patches `Vision._groq.chat.completions.create` to return a fake
response so we can exercise the dump + replay code paths without
hitting Groq. Verifies:
  1. Setting SCOUT_RAW_DUMP=1 creates the JSONL and writes a record
     with the same raw_response Groq returned.
  2. Setting SCOUT_REPLAY_LOG=<path> bypasses Groq for cached frame_ids.
  3. Cache miss falls through to Groq.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _fake_groq_response(text: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content=text),
            finish_reason="stop",
        )],
        usage=SimpleNamespace(completion_tokens=42),
    )


def _new_vision(env: dict):
    for k, v in env.items():
        os.environ[k] = v
    # Re-import each call to pick up env changes.
    if "eyes.vision" in sys.modules:
        del sys.modules["eyes.vision"]
    from eyes.vision import Vision  # noqa: WPS433
    return Vision()


async def main():
    tmp = tempfile.mkdtemp(prefix="scout_smoke_")
    sid = "smoke_test"
    os.environ["BMF_SESSION_ID"] = sid
    # Redirect dump dir to tmp by chdir-ing; vision writes to
    # files/logs/deliveries/<sid>/ relative to CWD.
    os.chdir(tmp)

    # ── 1. dump path ────────────────────────────────────────────────
    v = _new_vision({"SCOUT_RAW_DUMP": "1"})
    v._groq = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=AsyncMock(return_value=_fake_groq_response(
                    "FAKE_RAW_RESPONSE_DUMP_TEST")))))
    from eyes import cricket_logger as cl
    cl.set_global_frame(101)
    out = await v._scout_call("img_b64", "prompt")
    assert out == "FAKE_RAW_RESPONSE_DUMP_TEST", out
    v._raw_dump_fp.flush()

    dump_path = os.path.join(
        tmp, "files", "logs", "deliveries", sid, "scout_raw.jsonl")
    assert os.path.exists(dump_path), dump_path
    with open(dump_path) as fh:
        rec = json.loads(fh.readline())
    assert rec["frame_id"] == 101, rec
    assert rec["raw_response"] == "FAKE_RAW_RESPONSE_DUMP_TEST", rec
    print(f"[1] dump OK → {dump_path}")

    # ── 2. replay hit ───────────────────────────────────────────────
    os.environ.pop("SCOUT_RAW_DUMP", None)
    v2 = _new_vision({"SCOUT_REPLAY_LOG": dump_path})
    v2._groq = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=AsyncMock(return_value=_fake_groq_response(
                    "SHOULD_NOT_BE_CALLED")))))
    cl.set_global_frame(101)
    out2 = await v2._scout_call("img", "prompt")
    assert out2 == "FAKE_RAW_RESPONSE_DUMP_TEST", out2
    assert v2._groq.chat.completions.create.await_count == 0, (
        "Groq was called on replay-cache hit")
    print("[2] replay-cache hit OK (0 Groq calls)")

    # ── 3. replay miss → falls through to Groq ─────────────────────
    cl.set_global_frame(999)
    out3 = await v2._scout_call("img", "prompt")
    assert out3 == "SHOULD_NOT_BE_CALLED", out3
    assert v2._groq.chat.completions.create.await_count == 1
    print("[3] replay-cache miss → Groq fallback OK")

    print("ALL SMOKE CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
