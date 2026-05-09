"""Issue #28 — innings-2 restart bootstrap.

When the pipeline starts mid-match (innings 2 already in progress),
the first observed strip read with score>0 + broadcast_target>0
should seed innings=2 directly rather than waiting for the 3-frame
in_inn2_transition consensus.

Run: pytest files/tests/test_innings_restart_bootstrap.py -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from score_manager import FrameInput, ScoreManager  # noqa: E402


def _frame(fid: int, *, ext_score: int | None = None,
           ext_wickets: int | None = None,
           ext_overs: float | None = None,
           broadcast_target: int | None = None) -> FrameInput:
    return FrameInput(
        frame_id=str(fid),
        timestamp=float(fid),
        ext_score=ext_score,
        ext_wickets=ext_wickets,
        ext_overs=ext_overs,
        broadcast_target=broadcast_target,
    )


def _count_bootstrap_lines(captured: str) -> int:
    return sum(1 for line in captured.splitlines()
               if "[INNINGS-2-BOOTSTRAP]" in line)


def test_bootstrap_fires_on_midmatch_restart(capsys) -> None:
    sm = ScoreManager(shadow=True)
    assert sm.innings == 1

    sm.on_frame(_frame(
        1, ext_score=25, ext_wickets=1, ext_overs=4.1,
        broadcast_target=180))

    assert sm.innings == 2
    assert sm.target == 180
    assert sm._inn2_bootstrap_attempted is True

    captured = capsys.readouterr().out
    assert "[INNINGS-2-BOOTSTRAP]" in captured
    assert "target=180" in captured


def test_bootstrap_does_not_fire_on_innings_1_fresh_start() -> None:
    sm = ScoreManager(shadow=True)
    sm.on_frame(_frame(
        1, ext_score=0, ext_wickets=0, ext_overs=0.0,
        broadcast_target=None))
    assert sm.innings == 1
    assert sm._inn2_bootstrap_attempted is False


def test_bootstrap_does_not_fire_during_innings_1_restart() -> None:
    sm = ScoreManager(shadow=True)
    sm.on_frame(_frame(
        1, ext_score=87, ext_wickets=3, ext_overs=14.1,
        broadcast_target=None))
    assert sm.innings == 1
    assert sm._inn2_bootstrap_attempted is False


def test_bootstrap_re_armed_if_target_observed_late() -> None:
    sm = ScoreManager(shadow=True)
    for fid in (1, 2):
        sm.on_frame(_frame(
            fid, ext_score=25, ext_wickets=1, ext_overs=4.1,
            broadcast_target=None))
        assert sm.innings == 1
        assert sm._inn2_bootstrap_attempted is False

    sm.on_frame(_frame(
        3, ext_score=25, ext_wickets=1, ext_overs=4.1,
        broadcast_target=180))
    assert sm.innings == 2
    assert sm.target == 180
    assert sm._inn2_bootstrap_attempted is True


def test_bootstrap_fires_only_once(capsys) -> None:
    sm = ScoreManager(shadow=True)
    for fid in (1, 2, 3, 4):
        sm.on_frame(_frame(
            fid, ext_score=25 + fid, ext_wickets=1, ext_overs=4.1,
            broadcast_target=180))

    captured = capsys.readouterr().out
    assert _count_bootstrap_lines(captured) == 1
    assert sm.innings == 2
