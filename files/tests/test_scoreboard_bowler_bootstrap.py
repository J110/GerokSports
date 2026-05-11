"""Scoreboard.update_bowler bootstrap-bypass tests.

Verifies the fix for the secondary bug in
``files/docs/investigations/p3_diagnosis.md`` §4 / §6 Part B: when
``_bowler_must_change`` is True and ``current_bowler`` was just cleared by
the over-rollover handler, the bootstrap branch must not re-install the
just-finished bowler.

Run from repo root:
    pytest files/tests/test_scoreboard_bowler_bootstrap.py -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest  # noqa: E402

from eyes.scoreboard import Scoreboard  # noqa: E402


def _blank_bowler_entry() -> dict:
    return {
        "runs": None, "wickets": None, "overs": None, "maidens": None,
        "is_playing_xi": True,
    }


def _setup_sb(*, current_bowler, prev_over_bowler, must_change,
              bowlers=("Akeal Hosein", "Shamar Joseph")):
    sb = Scoreboard()
    sb.batting_team = "South Africa"
    sb.bowling_team = "West Indies"
    sb.current_innings = 1
    sb._inn["overs"] = "1.0"
    sb._inn["score"] = 4
    sb._inn["wickets"] = 0
    sb._inn["current_bowler"] = current_bowler
    sb._prev_over_bowler = prev_over_bowler
    sb._bowler_must_change = must_change
    for b in bowlers:
        sb.bowling_card[b] = _blank_bowler_entry()
        sb._name_lookup[b.upper()] = b
        last = b.split()[-1].upper()
        sb._name_lookup.setdefault(last, b)
    return sb


def test_bootstrap_rejects_just_finished_bowler():
    sb = _setup_sb(current_bowler=None,
                   prev_over_bowler="Akeal Hosein",
                   must_change=True)
    sb.update_bowler("Hosein", overs="0.1", runs=0, wickets=0, frame=160)
    assert sb._inn.get("current_bowler") is None, (
        "must_change + same-name must NOT bootstrap the just-finished bowler")
    assert sb._bowler_must_change is True


def test_bootstrap_accepts_different_bowler_under_must_change():
    sb = _setup_sb(current_bowler=None,
                   prev_over_bowler="Akeal Hosein",
                   must_change=True)
    sb.update_bowler("Shamar Joseph", overs="0.1", runs=0, wickets=0,
                     frame=160)
    assert sb._inn.get("current_bowler") == "Shamar Joseph"


def test_bootstrap_accepts_first_bowler_at_cold_start():
    sb = _setup_sb(current_bowler=None,
                   prev_over_bowler=None,
                   must_change=False)
    sb._inn["overs"] = "0.0"
    sb.update_bowler("Akeal Hosein", overs="0.1", runs=0, wickets=0,
                     frame=1)
    assert sb._inn.get("current_bowler") == "Akeal Hosein"


# ---------------------------------------------------------------------
# Fix #26: pin str→int coercion regression in update_bowler (F651 hotfix).
# Yesterday's crash trace: extractor proposed bowler runs/wickets/maidens
# as string-numeric values which fed straight into int() arithmetic
# downstream — TypeError on comparison. Hotfix wraps the casts in
# try/except; these tests pin both the success and crash-free failure
# paths.
# ---------------------------------------------------------------------
def test_update_bowler_coerces_string_numeric_fields():
    sb = _setup_sb(current_bowler="Akeal Hosein",
                   prev_over_bowler=None, must_change=False)
    # Team overs must lead bowler overs to clear the sanity gate.
    sb._inn["overs"] = "5.0"
    # Pre-confirm tracker so single-frame string-numeric kwargs commit.
    sb._tracker.confirmed["bowl:Akeal Hosein:runs"] = 1
    sb._tracker.confirmed["bowl:Akeal Hosein:wickets"] = 0
    sb.update_bowler("Akeal Hosein", overs="3.0",
                     runs="1", wickets="0", maidens="0", frame=200)
    entry = sb.bowling_card["Akeal Hosein"]
    assert entry["runs"] == 1 and isinstance(entry["runs"], int)
    assert entry["wickets"] == 0 and isinstance(entry["wickets"], int)
    assert entry["maidens"] == 0 and isinstance(entry["maidens"], int)


def test_update_bowler_handles_unparseable_strings():
    sb = _setup_sb(current_bowler="Akeal Hosein",
                   prev_over_bowler=None, must_change=False)
    sb.update_bowler("Akeal Hosein", overs="3.0",
                     runs="invalid", wickets="abc", maidens="??",
                     frame=201)
    entry = sb.bowling_card["Akeal Hosein"]
    # No TypeError on unparseable strings — that's the regression.
    # Unparseable values coerce to None and never reach tracker.update,
    # so the entry's int fields stay at their None defaults.
    assert entry.get("runs") is None
    assert entry.get("wickets") is None
    assert entry.get("maidens") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
