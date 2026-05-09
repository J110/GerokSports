"""Batch Y — vision-hint surname canonicalisation.

Reproduces tonight's MI-vs-LSG F287 hint where the scorer LLM emitted
'Current batters: MARSH and ING LIS' — Josh Inglis's surname split by
a spurious internal space. The sanitiser must collapse fragments back
to canonical surnames sourced from the scoreboard's batting/bowling
cards, and strip stray initials before known surnames.

Run from repo root:
    pytest files/tests/test_batch_y_hint_canonical_name.py -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from test_pipeline import _sanitize_vision_hint_names  # noqa: E402


class _StubScoreboard:
    def __init__(self, batters, bowlers):
        self.batting_card = {n: {} for n in batters}
        self.bowling_card = {n: {} for n in bowlers}


def _lsg_mi_scoreboard():
    return _StubScoreboard(
        batters=[
            "Mitchell Marsh", "Josh Inglis", "Aiden Markram",
            "Nicholas Pooran",
        ],
        bowlers=["Deepak Chahar", "Jasprit Bumrah", "Mujeeb Ur Rahman"],
    )


def test_batch_y_hint_uses_canonical_name():
    sb = _lsg_mi_scoreboard()
    out = _sanitize_vision_hint_names(
        "Current batters: MARSH and ING LIS. Bowler: BUMRAH. "
        "Read their stats from the scoreboard.",
        sb,
    )
    assert "ING LIS" not in out
    assert "INGLIS" in out
    assert "MARSH" in out
    assert "BUMRAH" in out


def test_batch_y_hint_strips_initial_before_surname():
    sb = _lsg_mi_scoreboard()
    out = _sanitize_vision_hint_names(
        "Current batters: POORAN and M MARSH. Bowler: BUMRAH.",
        sb,
    )
    assert "M MARSH" not in out
    assert "MARSH" in out
    assert "POORAN" in out


def test_batch_y_hint_merges_with_trailing_punctuation():
    sb = _lsg_mi_scoreboard()
    out = _sanitize_vision_hint_names(
        "Current batters: ING LIS, MARSH. Bowler: CHAHAR",
        sb,
    )
    assert out.startswith("Current batters: INGLIS, MARSH.")


def test_batch_y_hint_preserves_full_first_name():
    sb = _lsg_mi_scoreboard()
    out = _sanitize_vision_hint_names(
        "Current batters: MITCHELL MARSH, JOSH INGLIS. Bowler: CHAHAR",
        sb,
    )
    assert "MITCHELL MARSH" in out
    assert "JOSH INGLIS" in out


def test_batch_y_hint_noop_when_clean():
    sb = _lsg_mi_scoreboard()
    clean = "Current batters: Marsh and Inglis. Bowler: Bumrah."
    assert _sanitize_vision_hint_names(clean, sb) == clean


def test_batch_y_hint_noop_without_cards():
    sb = _StubScoreboard(batters=[], bowlers=[])
    raw = "Current batters: MARSH and ING LIS. Bowler: BUMRAH."
    assert _sanitize_vision_hint_names(raw, sb) == raw


def test_batch_y_hint_handles_none():
    sb = _lsg_mi_scoreboard()
    assert _sanitize_vision_hint_names(None, sb) is None
    assert _sanitize_vision_hint_names("", sb) == ""
