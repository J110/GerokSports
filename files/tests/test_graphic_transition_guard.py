"""GRAPHIC→SCOREBOARD one-frame poison (lever-2 partial fade).

See files/docs/investigations/strip_ocr_failure_mode_analysis.md §5.2.
Run: pytest files/tests/test_graphic_transition_guard.py -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from test_pipeline import _poison_scoreboard_after_graphic_transition  # noqa: E402


def test_poison_first_scoreboard_after_graphic() -> None:
    assert _poison_scoreboard_after_graphic_transition(
        prev_vision_frame_type="GRAPHIC",
        frame_type="SCOREBOARD",
        already_poisoned=False,
    )


def test_no_poison_when_not_adjacent() -> None:
    assert not _poison_scoreboard_after_graphic_transition(
        prev_vision_frame_type="SCOREBOARD",
        frame_type="SCOREBOARD",
        already_poisoned=False,
    )
    assert not _poison_scoreboard_after_graphic_transition(
        prev_vision_frame_type=None,
        frame_type="SCOREBOARD",
        already_poisoned=False,
    )
    assert not _poison_scoreboard_after_graphic_transition(
        prev_vision_frame_type="GRAPHIC",
        frame_type="GRAPHIC",
        already_poisoned=False,
    )


def test_no_double_poison_if_already_flagged() -> None:
    assert not _poison_scoreboard_after_graphic_transition(
        prev_vision_frame_type="GRAPHIC",
        frame_type="SCOREBOARD",
        already_poisoned=True,
    )
