"""Unit tests for ScoreManager pending-ball queue (B1.1).

Exercises the queue lifecycle methods added by the no-MULTI_BALL
architecture: enqueue, resweep, drain, overflow, and placeholder
token rewrite. Tracker on_lock callbacks are wired in B1.3; here
the resweep is invoked manually to simulate a LOCK transition.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from score_manager import PendingBall, ScoreManager


@pytest.fixture
def sm() -> ScoreManager:
    return ScoreManager(shadow=True)


def _enqueue(sm: ScoreManager, *, runs: int, frame_id: int,
             slot_idx: int | None = None,
             wickets: int = 0) -> PendingBall:
    return sm._enqueue_pending_ball(
        runs_delta=runs,
        wickets_delta=wickets,
        frame_id=frame_id,
        slot_idx=slot_idx,
    )


def test_drain_after_both_trackers_lock_credits_all_fifo(sm: ScoreManager):
    e1 = _enqueue(sm, runs=1, frame_id=100, slot_idx=0)
    e2 = _enqueue(sm, runs=4, frame_id=101, slot_idx=1)
    e3 = _enqueue(sm, runs=0, frame_id=102, slot_idx=2)

    assert sm._resweep_pending_attribution("Roy", "bowler") == 3
    assert sm._drain_pending_queue("bowler-lock") == 0
    assert len(sm._pending_ball_queue) == 3

    assert sm._resweep_pending_attribution("Pathum", "striker") == 3
    assert sm._drain_pending_queue("striker-lock") == 3
    assert len(sm._pending_ball_queue) == 0
    for e in (e1, e2, e3):
        assert e.committed
        assert e.bowler == "Roy"
        assert e.striker == "Pathum"


def test_drain_halts_on_missing_striker_keeps_depth(sm: ScoreManager):
    _enqueue(sm, runs=1, frame_id=200, slot_idx=0)
    _enqueue(sm, runs=2, frame_id=201, slot_idx=1)

    sm._resweep_pending_attribution("Roy", "bowler")
    drained = sm._drain_pending_queue("test-halt")

    assert drained == 0
    assert len(sm._pending_ball_queue) == 2
    for e in sm._pending_ball_queue:
        assert not e.committed
        assert e.bowler == "Roy"
        assert e.striker is None


def test_resweep_skips_committed_entries(sm: ScoreManager):
    _enqueue(sm, runs=1, frame_id=300, slot_idx=0)
    _enqueue(sm, runs=4, frame_id=301, slot_idx=1)
    sm._resweep_pending_attribution("Roy", "bowler")
    sm._resweep_pending_attribution("Pathum", "striker")
    assert sm._drain_pending_queue("setup-drain") == 2
    assert len(sm._pending_ball_queue) == 0

    e3 = _enqueue(sm, runs=0, frame_id=302, slot_idx=2)
    e4 = _enqueue(sm, runs=6, frame_id=303, slot_idx=3)
    updated = sm._resweep_pending_attribution("Tyagi", "bowler")

    assert updated == 2
    assert e3.bowler == "Tyagi"
    assert e4.bowler == "Tyagi"


def test_overflow_emits_trace_warning(monkeypatch, sm: ScoreManager):
    captured: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        sm, "_emit_pending_trace",
        lambda tag, **payload: captured.append((tag, payload)),
    )

    for i in range(6):
        _enqueue(sm, runs=1, frame_id=400 + i, slot_idx=i)
    captured.clear()

    _enqueue(sm, runs=1, frame_id=406, slot_idx=6)

    tags = [t for t, _ in captured]
    assert "PENDING-BALL-QUEUE-OVERFLOW" in tags
    overflow_payload = next(
        p for t, p in captured if t == "PENDING-BALL-QUEUE-OVERFLOW"
    )
    assert overflow_payload["queue_depth"] == 6
    assert overflow_payload["incoming_frame_id"] == 406


def test_bind_pending_slot_assigns_to_head_unbound_entry(sm: ScoreManager):
    e1 = _enqueue(sm, runs=0, frame_id=600, slot_idx=None)
    e2 = _enqueue(sm, runs=0, frame_id=601, slot_idx=None)
    e3 = _enqueue(sm, runs=0, frame_id=602, slot_idx=None)

    assert sm.bind_pending_slot(7) is True
    assert e1.slot_idx == 7
    assert e2.slot_idx is None
    assert e3.slot_idx is None

    assert sm.bind_pending_slot(8) is True
    assert e2.slot_idx == 8
    assert e3.slot_idx is None

    assert sm.bind_pending_slot(9) is True
    assert e3.slot_idx == 9


def test_bind_pending_slot_skips_already_bound_entries(sm: ScoreManager):
    e1 = _enqueue(sm, runs=0, frame_id=700, slot_idx=3)  # pre-bound
    e2 = _enqueue(sm, runs=0, frame_id=701, slot_idx=None)

    assert sm.bind_pending_slot(99) is True
    # First unbound is e2, so e2 gets the new slot.
    assert e1.slot_idx == 3
    assert e2.slot_idx == 99


def test_bind_pending_slot_orphan_returns_false(sm: ScoreManager):
    # No pending entries.
    assert sm.bind_pending_slot(5) is False
    assert len(sm._pending_ball_queue) == 0


def test_bind_pending_slot_skips_committed_entries(sm: ScoreManager):
    e1 = _enqueue(sm, runs=0, frame_id=800, slot_idx=None)
    e2 = _enqueue(sm, runs=0, frame_id=801, slot_idx=None)
    # Manually mark e1 committed (simulating prior drain).
    e1.committed = True
    e1.slot_idx = 0
    e1.bowler = "Roy"
    e1.striker = "Pathum"

    assert sm.bind_pending_slot(42) is True
    assert e2.slot_idx == 42
    assert e1.slot_idx == 0  # unchanged


def test_drain_rewrites_placeholder_in_over_mgr(sm: ScoreManager):
    rewrites: list[tuple[int, str]] = []

    class _StubOverMgr:
        def rewrite_token(self, slot_idx: int, token: str) -> None:
            rewrites.append((slot_idx, token))

    sm.over_mgr = _StubOverMgr()

    _enqueue(sm, runs=4, frame_id=500, slot_idx=0)
    _enqueue(sm, runs=0, frame_id=501, slot_idx=1)
    e3 = sm._enqueue_pending_ball(
        runs_delta=0,
        wickets_delta=1,
        frame_id=502,
        slot_idx=2,
    )

    sm._resweep_pending_attribution("Roy", "bowler")
    sm._resweep_pending_attribution("Pathum", "striker")
    drained = sm._drain_pending_queue("test-rewrite")

    assert drained == 3
    assert rewrites == [(0, "4"), (1, "."), (2, "W")]
    assert e3.committed
