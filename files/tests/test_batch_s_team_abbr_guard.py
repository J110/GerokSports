"""Batch S — batting_team abbreviation re-detection guard.

Reproduces tonight's MI-vs-LSG telemetry where a strip-OCR misread
on F56 set ``batting_team`` to "RCB" while the locked full name was
"Lucknow Super Giants". The SM-FEEDER-SYNC handler must reject
abbreviations whose mapped full name conflicts with the currently
locked team.

Run from repo root:
    pytest files/tests/test_batch_s_team_abbr_guard.py -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from eyes.scoreboard import Scoreboard  # noqa: E402
from score_manager import (  # noqa: E402
    ScoreManager,
    _BATTING_TEAM_ABBR_TO_FULL,
    _conflicts_with_locked_team,
)


def _make_sm_with_locked_team(full: str) -> ScoreManager:
    sm = ScoreManager(shadow=False)
    sb = Scoreboard()
    sb.batting_team = full
    sm.scoreboard = sb
    return sm


def test_batch_s_reject_conflicting_abbreviation():
    sm = _make_sm_with_locked_team("Lucknow Super Giants")

    sm.batting_team = "RCB"

    assert sm.scoreboard.batting_team == "Lucknow Super Giants"


def test_batch_s_accepts_matching_abbreviation():
    sm = _make_sm_with_locked_team("Lucknow Super Giants")

    sm.batting_team = "LSG"

    assert sm.scoreboard.batting_team == "LSG"


def test_batch_s_accepts_unrelated_string():
    sm = _make_sm_with_locked_team("Lucknow Super Giants")

    sm.batting_team = "Lucknow Super Giants"

    assert sm.scoreboard.batting_team == "Lucknow Super Giants"


def test_batch_s_first_assignment_unrestricted():
    sm = ScoreManager(shadow=False)
    sm.scoreboard = Scoreboard()

    sm.batting_team = "RCB"

    assert sm.scoreboard.batting_team == "RCB"


def test_batch_s_helper_detects_conflict():
    assert _conflicts_with_locked_team("RCB", "Lucknow Super Giants")
    assert _conflicts_with_locked_team(
        "lsg", "Royal Challengers Bengaluru")


def test_batch_s_helper_passes_unknown_token():
    assert not _conflicts_with_locked_team("XYZ", "Lucknow Super Giants")


def test_batch_s_abbr_table_covers_ipl_teams():
    assert _BATTING_TEAM_ABBR_TO_FULL["RCB"] == "Royal Challengers Bengaluru"
    assert _BATTING_TEAM_ABBR_TO_FULL["LSG"] == "Lucknow Super Giants"
