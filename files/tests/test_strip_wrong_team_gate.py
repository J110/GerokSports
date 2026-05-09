"""Wrong-team strip-read gate.

Rejects strip reads where ``batting_team_visible`` doesn't match the
committed ``batting_team``. Catches OCR misreads like "Delhi Capitals"
appearing during CSK's chase (session 61dfce3a F3).

Run: pytest files/tests/test_strip_wrong_team_gate.py -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from test_pipeline import filter_strip_wrong_team  # noqa: E402


def test_gate_rejects_dc_during_csk_innings(caplog) -> None:
    rejected = filter_strip_wrong_team(
        visible_team="Delhi Capitals",
        batting_team="Chennai Super Kings",
        innings=1,
        frame_count=42)
    assert rejected is True


def test_gate_accepts_csk_during_csk_innings() -> None:
    assert filter_strip_wrong_team(
        visible_team="Chennai Super Kings",
        batting_team="Chennai Super Kings",
        innings=1,
        frame_count=42) is False


def test_gate_accepts_csk_abbreviation_during_csk_full() -> None:
    assert filter_strip_wrong_team(
        visible_team="CSK",
        batting_team="Chennai Super Kings",
        innings=1,
        frame_count=42) is False


def test_gate_accepts_full_during_abbreviation_batting() -> None:
    assert filter_strip_wrong_team(
        visible_team="Mumbai Indians",
        batting_team="MI",
        innings=2,
        frame_count=99) is False


def test_gate_rejects_unknown_team() -> None:
    assert filter_strip_wrong_team(
        visible_team="XYZ",
        batting_team="Chennai Super Kings",
        innings=1,
        frame_count=42) is True


def test_gate_silent_when_no_innings() -> None:
    assert filter_strip_wrong_team(
        visible_team="Delhi Capitals",
        batting_team=None,
        innings=0,
        frame_count=42) is False


def test_gate_silent_when_visible_team_none() -> None:
    assert filter_strip_wrong_team(
        visible_team=None,
        batting_team="Chennai Super Kings",
        innings=1,
        frame_count=42) is False


def test_gate_silent_when_batting_team_none() -> None:
    assert filter_strip_wrong_team(
        visible_team="Delhi Capitals",
        batting_team=None,
        innings=1,
        frame_count=42) is False


def test_gate_silent_pre_innings_commit() -> None:
    assert filter_strip_wrong_team(
        visible_team="Delhi Capitals",
        batting_team="Chennai Super Kings",
        innings=0,
        frame_count=42) is False


def test_abbreviation_cross_match_dc_vs_delhi() -> None:
    assert filter_strip_wrong_team(
        visible_team="Delhi Capitals",
        batting_team="DC",
        innings=1,
        frame_count=1) is False


def test_substring_match_within_strip_text() -> None:
    assert filter_strip_wrong_team(
        visible_team="CSK 87-5",
        batting_team="CSK",
        innings=2,
        frame_count=1) is False
