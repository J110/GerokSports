"""B5: ConsistentReadTracker cross-field consensus gate tests."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eyes.consistent_tracker import ConsistentReadTracker  # noqa: E402


def _feed_frame(t, frame, score=None, wickets=None, overs=None):
    if score is not None:
        t.update("score", score, frame_count=frame)
    if wickets is not None:
        t.update("wickets", wickets, frame_count=frame)
    if overs is not None:
        t.update("overs", overs, frame_count=frame)


def test_all_three_confirm_together(capsys):
    t = ConsistentReadTracker()
    for f in (1, 2, 3):
        _feed_frame(t, f, score=10, wickets=0, overs=1.0)

    out = capsys.readouterr().out
    assert t.get("score") == 10
    assert t.get("wickets") == 0
    assert t.get("overs") == 1.0

    assert out.count("cross-field gate satisfied:") == 1
    assert "score=10 wickets=0 overs=1.0 (all confirmed)" in out

    holding_lines = [
        ln for ln in out.splitlines()
        if "holding for cross-field gate" in ln
    ]
    assert len(holding_lines) == 2
    assert any("score:" in ln for ln in holding_lines)
    assert any("wickets:" in ln for ln in holding_lines)
    assert not any("overs:" in ln for ln in holding_lines)


def test_wickets_holds_when_score_flips(capsys):
    t = ConsistentReadTracker()
    _feed_frame(t, 1, score=10, wickets=0, overs=1.0)
    _feed_frame(t, 2, score=11, wickets=0, overs=1.0)
    _feed_frame(t, 3, score=10, wickets=0, overs=1.0)

    out = capsys.readouterr().out
    assert "wickets" not in t.confirmed
    assert "score" not in t.confirmed
    assert "overs" not in t.confirmed

    wickets_holding = [
        ln for ln in out.splitlines()
        if "wickets:" in ln and "holding for cross-field gate" in ln
    ]
    assert len(wickets_holding) == 1

    overs_holding = [
        ln for ln in out.splitlines()
        if "overs:" in ln and "holding for cross-field gate" in ln
    ]
    assert len(overs_holding) == 1


def test_pre_match_graphic_no_partial_commit(capsys):
    t = ConsistentReadTracker()
    score_seq = [47, 48, 49, 50, 51]
    overs_seq = [3.2, 3.3, 3.4, 3.5, 4.0]
    for i, (s, o) in enumerate(zip(score_seq, overs_seq), start=1):
        _feed_frame(t, i, score=s, wickets=3, overs=o)

    capsys.readouterr()

    assert "wickets" not in t.confirmed
    assert "score" not in t.confirmed
    assert "overs" not in t.confirmed
    assert t.get("wickets") is None
    assert t.get("score") is None
    assert t.get("overs") is None


def test_real_match_start(capsys):
    t = ConsistentReadTracker()
    for f in (1, 2, 3):
        _feed_frame(t, f, score=0, wickets=0, overs=0.0)

    out = capsys.readouterr().out
    assert t.get("score") == 0
    assert t.get("wickets") == 0
    assert t.get("overs") == 0.0
    assert "cross-field gate satisfied:" in out
    assert "score=0 wickets=0 overs=0.0 (all confirmed)" in out


def test_late_third_field_unblocks(capsys):
    t = ConsistentReadTracker()
    for f in (1, 2, 3):
        _feed_frame(t, f, score=10, wickets=0)

    assert "score" not in t.confirmed
    assert "wickets" not in t.confirmed
    assert "overs" not in t.confirmed

    for f in (4, 5, 6):
        _feed_frame(t, f, overs=1.0)

    out = capsys.readouterr().out
    assert t.get("score") == 10
    assert t.get("wickets") == 0
    assert t.get("overs") == 1.0
    assert "cross-field gate satisfied:" in out
    assert "score=10 wickets=0 overs=1.0 (all confirmed)" in out


def test_non_gated_field_confirms_independently(capsys):
    t = ConsistentReadTracker()
    for f in (1, 2, 3):
        t.update("bowler_name", "Bumrah", frame_count=f)

    assert t.get("bowler_name") == "Bumrah"


def test_post_hold_flip_resets_quietly(capsys):
    t = ConsistentReadTracker()
    for f in (1, 2, 3):
        t.update("wickets", 3, frame_count=f)

    out_before = capsys.readouterr().out
    holding_before = [
        ln for ln in out_before.splitlines()
        if "wickets:" in ln and "holding for cross-field gate" in ln
    ]
    assert len(holding_before) == 1
    assert 3 in [v for v in (t._gate_holding.get("wickets"),) if v is not None]

    t.update("wickets", 5, frame_count=4)
    out_after = capsys.readouterr().out

    assert "wickets" not in t._gate_holding
    assert t._initial_consensus.get("wickets") == [5, 1]
    assert "wickets" not in t.confirmed

    flip_logs = [
        ln for ln in out_after.splitlines()
        if "wickets:" in ln and (
            "holding for cross-field gate" in ln
            or "initial proposal flipped" in ln
        )
    ]
    assert flip_logs == []
