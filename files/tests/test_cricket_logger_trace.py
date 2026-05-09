"""CricketLogger → trace recorder auto-promotion tests.

Verifies the fix for P3 trace blindness documented in
``files/docs/investigations/p3_diagnosis.md`` §6 Part A: any
``[TAG]``-prefixed CricketLogger emission must land in the active
``DecisionRecorder`` bucket so trace records contain the
``BOWLER`` / ``GUARD`` / ``WICKET`` / etc. decisions.

Run from repo root:
    pytest files/tests/test_cricket_logger_trace.py -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest  # noqa: E402

import trace_emitter  # noqa: E402
import eyes.cricket_logger as cricket_logger  # noqa: E402
from eyes.cricket_logger import CricketLogger  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_recorder():
    trace_emitter.reset_singletons()
    cricket_logger._TRACE_RECORDER = None
    cricket_logger._TRACE_IMPORT_ATTEMPTED = False
    cricket_logger._TRACE_KNOWN_TAGS = frozenset()
    yield
    trace_emitter.reset_singletons()
    cricket_logger._TRACE_RECORDER = None
    cricket_logger._TRACE_IMPORT_ATTEMPTED = False
    cricket_logger._TRACE_KNOWN_TAGS = frozenset()


def test_cricket_logger_emits_to_recorder():
    rec = trace_emitter.get_recorder()
    rec.begin_frame(123)
    log = CricketLogger("TEST")
    log.info("  [BOWLER] New bowler confirmed: Akeal Hosein (was Joseph)")
    out = rec.drain()
    tags = [d["tag"] for d in out]
    assert "BOWLER" in tags
    entry = next(d for d in out if d["tag"] == "BOWLER")
    assert entry["_auto"] is True
    assert entry["log_level"] == "INFO"
    assert entry["logger"] == "TEST"
    assert entry["known"] is True


def test_cricket_logger_emits_renamed_tag():
    rec = trace_emitter.get_recorder()
    rec.begin_frame(200)
    log = CricketLogger("BOARD")
    log.info("[BOWLER-OVERRIDE] None → Akeal Hosein (reads=1, "
             "must_change=True)")
    out = rec.drain()
    tags = [d["tag"] for d in out]
    assert "BOWLER-OVERRIDE" in tags


def test_cricket_logger_no_tag_no_record():
    rec = trace_emitter.get_recorder()
    rec.begin_frame(7)
    log = CricketLogger("TEST")
    log.info("Generic info message no tag")
    log.info("lowercase [tag] should not match")
    log.info("trailing brackets without uppercase token: (foo)")
    out = rec.drain()
    assert out == []


def test_cricket_logger_warn_level_recorded():
    rec = trace_emitter.get_recorder()
    rec.begin_frame(42)
    log = CricketLogger("BOARD")
    log.warn("  [BOWLER-CONSENSUS-INCONSISTENT] refusing flip "
             "to 'Shamar Joseph'")
    out = rec.drain()
    assert len(out) == 1
    assert out[0]["tag"] == "BOWLER-CONSENSUS-INCONSISTENT"
    assert out[0]["log_level"] == "WARN"


def test_cricket_logger_unknown_tag_marked_unknown():
    rec = trace_emitter.get_recorder()
    rec.begin_frame(1)
    log = CricketLogger("TEST")
    log.info("[NOVEL-TAG-NEVER-SEEN] payload")
    out = rec.drain()
    assert len(out) == 1
    assert out[0]["tag"] == "NOVEL-TAG-NEVER-SEEN"
    assert out[0]["known"] is False
