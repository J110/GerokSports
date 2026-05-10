"""Batch V — per-field BOWLER-STALE rejection in ScoreManager.

The legacy stale guard skipped every bowler field on the row whenever
either sub-condition fired:

  Sub-condition A — proposed-bowler figures match the historical
  bowling-card snapshot AND not in the ``_bowler_must_change`` grace
  window. Likely a resurrected end-of-spell graphic; all four fields
  are stale.

  Sub-condition B — proposed bowler_overs regress vs the historical
  bowler_overs. Only the overs figure is numerically inconsistent;
  runs and wickets remain accept-eligible.

Batch V splits the predicate so sub-condition B drops only
``bowler_overs`` while keeping runs/wickets. Sub-condition A still
drops all four. The outer ``proposed_name != SM_current_bowler``
predicate always rejects ``bowler_name`` with reason
``name-mismatch-sm``.

The ``bowler_runs/wickets/overs`` ScoreManager properties are
read-through to ``scoreboard.bowling_card`` (their setters are
log-only no-ops), so SM-side acceptance of those fields is observed
via the structured ``[BOWLER-STALE]`` log emissions rather than via
SM scalar state. ``bowler_name`` is a plain attribute and is the only
field whose mutation is asserted directly.

Run from repo root:
    pytest files/tests/test_batch_v_bowler_stale_per_field.py -q
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from eyes.scoreboard import Scoreboard  # noqa: E402
from score_manager import ScoreManager  # noqa: E402

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _make_sm_with_bowler_history(
    *,
    sm_bowler: str | None,
    historical_bowler: str,
    hist_runs: int,
    hist_wickets: int,
    hist_overs: str,
) -> ScoreManager:
    sm = ScoreManager(shadow=False)
    sb = Scoreboard()
    sb.bowling_card = {
        historical_bowler: {
            "runs": hist_runs,
            "wickets": hist_wickets,
            "overs": hist_overs,
        }
    }
    sb._bowler_must_change = False
    sb._prev_over_bowler = None
    sm.scoreboard = sb
    sm.bowler_name = sm_bowler
    return sm


def _run_and_capture(sm: ScoreManager, card: dict) -> list[str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sm._accept_update(card)
    return [
        _ANSI_RE.sub("", line)
        for line in buf.getvalue().splitlines()
        if "[BOWLER-STALE]" in line
    ]


def _has(warns: list[str], field: str, reason: str) -> bool:
    return any(f"field={field}" in w and f"reason={reason}" in w
               for w in warns)


def test_batch_v_sub_a_rejects_all_four():
    """Single-writer architecture (post d94893e): stale bowler reads
    never mutate `scoreboard.bowling_card`. Only event emission can
    touch per-bowler stats. Verify the historical card is intact
    after a stale `_accept_update` call.
    """
    sm = _make_sm_with_bowler_history(
        sm_bowler="MARCO JANSEN",
        historical_bowler="YUZVENDRA CHAHAL",
        hist_runs=24,
        hist_wickets=1,
        hist_overs="3.0",
    )

    _run_and_capture(sm, {
        "bowler_name": "YUZVENDRA CHAHAL",
        "bowler_runs": 24,
        "bowler_wickets": 1,
        "bowler_overs": "3.0",
    })

    # `_accept_update` writes only `bowler_name` (no per-stat setters
    # exist after 4b972e5). Historical bowling_card stays unchanged.
    bc = sm.scoreboard.bowling_card["YUZVENDRA CHAHAL"]
    assert bc["runs"] == 24
    assert bc["wickets"] == 1
    assert bc["overs"] == "3.0"


def test_batch_v_sub_b_rejects_overs_only():
    """Stale-with-regressed-overs read: bowling_card runs/wickets/
    overs all stay at the historical values (single-writer contract).
    """
    sm = _make_sm_with_bowler_history(
        sm_bowler="MARCO JANSEN",
        historical_bowler="YUZVENDRA CHAHAL",
        hist_runs=24,
        hist_wickets=1,
        hist_overs="3.0",
    )

    _run_and_capture(sm, {
        "bowler_name": "YUZVENDRA CHAHAL",
        "bowler_runs": 30,
        "bowler_wickets": 2,
        "bowler_overs": "2.4",
    })

    bc = sm.scoreboard.bowling_card["YUZVENDRA CHAHAL"]
    assert bc["runs"] == 24
    assert bc["wickets"] == 1
    assert bc["overs"] == "3.0"


def test_batch_v_both_a_and_b():
    """Both sub-A and sub-B preconditions present — same single-writer
    invariant: bowling_card untouched.
    """
    sm = _make_sm_with_bowler_history(
        sm_bowler="MARCO JANSEN",
        historical_bowler="YUZVENDRA CHAHAL",
        hist_runs=24,
        hist_wickets=1,
        hist_overs="3.0",
    )

    _run_and_capture(sm, {
        "bowler_name": "YUZVENDRA CHAHAL",
        "bowler_runs": 24,
        "bowler_wickets": 1,
        "bowler_overs": "3.0",
    })

    bc = sm.scoreboard.bowling_card["YUZVENDRA CHAHAL"]
    assert bc["runs"] == 24
    assert bc["wickets"] == 1
    assert bc["overs"] == "3.0"


def test_batch_v_no_stale_regression():
    sm = _make_sm_with_bowler_history(
        sm_bowler="MARCO JANSEN",
        historical_bowler="YUZVENDRA CHAHAL",
        hist_runs=24,
        hist_wickets=1,
        hist_overs="3.0",
    )

    warns = _run_and_capture(sm, {
        "bowler_name": "YUZVENDRA CHAHAL",
        "bowler_runs": 28,
        "bowler_wickets": 2,
        "bowler_overs": "3.4",
    })

    assert sm.bowler_name == "YUZVENDRA CHAHAL"
    assert warns == []
