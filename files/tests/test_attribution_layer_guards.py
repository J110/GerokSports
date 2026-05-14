"""Tests for the attribution-layer guards (investigations 7 + 8,
2026-05-14).

Three guards added to `Scoreboard`:

  - `BOWLER-ROW-JUNK-REJECT` (Change F, investigation 7A): a strip read
    that proposes wickets +N>1 in one observation is column-scrambled
    OCR; suppress the wicket field but keep runs/overs.

  - `BOWLER-WICKET-DELTA-SUPPRESSED-NO-EVENT` (Change G, 7B): a strip
    delta that bumps wickets > 0 for a bowler with no FOW credit yet is
    either a misread or a backfill from an unattributed wicket;
    suppress until a real dismissal-event commits.

  - `BATTER-BALLS-INVARIANT-FREEZE` + `BATTER-BALLS-DOUBLE-INCREMENT-FRAME`
    (Changes H + I, investigation 8): the sum of batters' balls cannot
    exceed team legal balls, and one delivery can only increment one
    batter's balls (one striker per ball).

Run from repo root:
    pytest files/tests/test_attribution_layer_guards.py -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from eyes.scoreboard import Scoreboard  # noqa: E402


def _sb() -> Scoreboard:
    sb = Scoreboard()
    sb.batting_team = "DC"
    sb.bowling_team = "KKR"
    inn = sb.innings[sb.current_innings]
    inn["score"] = 0
    inn["wickets"] = 0
    inn["overs"] = "0.0"
    return sb


def _seed_bowler(sb: Scoreboard, name: str, *, overs: str = "0.0",
                 runs: int = 0, wickets: int = 0,
                 current: bool = False) -> None:
    sb.bowling_card[name] = {
        "overs": overs, "runs": runs, "wickets": wickets,
        "maidens": 0, "is_playing_xi": True,
    }
    sb._name_lookup[name.upper()] = name
    sb._name_lookup[name] = name
    if current:
        sb._inn["current_bowler"] = name


def _seed_batter(sb: Scoreboard, name: str, *, runs: int = 0,
                 balls: int = 0) -> None:
    sb.batting_card[name] = {
        "runs": runs, "balls": balls, "fours": 0, "sixes": 0,
        "status": "batting", "is_playing_xi": True,
    }
    sb._name_lookup[name.upper()] = name
    sb._name_lookup[name] = name
    # Pre-seed the consensus tracker so first-sight reads don't fall
    # into the 2-frame pending defer.
    sb._tracker.confirmed[f"bat:{name}:runs"] = runs
    sb._tracker.confirmed[f"bat:{name}:balls"] = balls


# -- Change F: bowler-row junk physics ----------------------------------

def test_wickets_jump_more_than_one_in_single_read_suppressed():
    """F438 case — VLM emits VAIBHAV 4-1 (1.2) (column-scrambled).
    Suppress the wickets field; accept runs/overs."""
    sb = _sb()
    _seed_bowler(sb, "Vaibhav Arora", overs="1.2", runs=15, wickets=0,
                 current=True)
    # Strip claims wickets=4 (impossible jump from 0)
    sb.update_bowler("Vaibhav Arora", overs="1.2", runs=15, wickets=4,
                     frame=438)
    assert sb.bowling_card["Vaibhav Arora"]["wickets"] == 0
    # Runs/overs accepted normally
    assert sb.bowling_card["Vaibhav Arora"]["runs"] == 15


def test_wickets_plus_one_accepted_when_fow_credits_bowler():
    """Legitimate +1 on a bowler with a FOW event commits."""
    sb = _sb()
    _seed_bowler(sb, "Kartik Tyagi", overs="1.0", runs=8, wickets=0,
                 current=True)
    # Simulate a dismissal-event commit crediting Tyagi
    sb.fall_of_wickets.append({
        "wicket": 1, "score": 49, "overs": "5.0",
        "batter": "KL Rahul", "bowler": "Kartik Tyagi",
    })
    sb.update_bowler("Kartik Tyagi", overs="1.0", runs=8, wickets=1,
                     frame=381)
    assert sb.bowling_card["Kartik Tyagi"]["wickets"] == 1


# -- Change G: wicket requires dismissal event --------------------------

def test_wicket_delta_suppressed_when_no_fow_credit():
    """F438 again — even after the junk-reject reduces 4→1, the +1
    must be blocked because Arora has no FOW entry."""
    sb = _sb()
    _seed_bowler(sb, "Vaibhav Arora", overs="1.2", runs=15, wickets=0,
                 current=True)
    # No FOW entries — Arora has no event-credited wicket
    sb.update_bowler("Vaibhav Arora", overs="1.2", runs=15, wickets=1,
                     frame=438)
    assert sb.bowling_card["Vaibhav Arora"]["wickets"] == 0


def test_wicket_delta_accepted_when_fow_credit_exists():
    """Bowler has an FOW entry → strip wickets=1 commits normally."""
    sb = _sb()
    _seed_bowler(sb, "Kartik Tyagi", overs="1.0", runs=8, wickets=0,
                 current=True)
    sb.fall_of_wickets.append({
        "wicket": 1, "score": 49, "overs": "5.0",
        "batter": "KL Rahul", "bowler": "Kartik Tyagi",
    })
    sb.update_bowler("Kartik Tyagi", overs="1.0", runs=8, wickets=1,
                     frame=381)
    assert sb.bowling_card["Kartik Tyagi"]["wickets"] == 1


# -- Change H: batter-balls sum invariant -------------------------------

def test_balls_sum_invariant_freezes_when_exceeds_team_legal_balls():
    """Team at 1.0 (6 legal balls).  Pathum 5(5), Rahul 1(2) sum=7
    already > 6+1=7, but +1 to anyone would exceed."""
    sb = _sb()
    sb._inn["overs"] = "1.0"
    _seed_batter(sb, "Pathum Nissanka", runs=5, balls=5)
    _seed_batter(sb, "KL Rahul", runs=1, balls=2)
    # Sum=7 already at the +1 slack ceiling.  Bumping Pathum to 6 balls
    # would push sum to 8 > team_legal (6) + 1.  Freeze.
    sb.update_batter("Pathum Nissanka", runs=5, balls=6, frame=100)
    assert sb.batting_card["Pathum Nissanka"]["balls"] == 5  # unchanged


def test_balls_sum_invariant_allows_normal_update():
    """Below the cap, normal updates commit."""
    sb = _sb()
    sb._inn["overs"] = "2.0"  # 12 legal balls — plenty of slack
    _seed_batter(sb, "Pathum Nissanka", runs=5, balls=4)
    _seed_batter(sb, "KL Rahul", runs=1, balls=2)
    sb.update_batter("Pathum Nissanka", runs=5, balls=5, frame=100)
    assert sb.batting_card["Pathum Nissanka"]["balls"] == 5


# -- Change I: double-increment guard -----------------------------------

def test_double_increment_in_one_frame_suppresses_second():
    """One delivery → one striker → one batter's balls increments.
    A second update_batter on the same frame for a different batter
    that also bumps balls must be suppressed."""
    sb = _sb()
    sb._inn["overs"] = "2.0"  # generous slack to keep sum-invariant quiet
    _seed_batter(sb, "Pathum Nissanka", runs=5, balls=4)
    _seed_batter(sb, "KL Rahul", runs=1, balls=2)
    # First update_batter on frame 100 — accepted.
    sb.update_batter("Pathum Nissanka", runs=5, balls=5, frame=100)
    assert sb.batting_card["Pathum Nissanka"]["balls"] == 5
    # Second update on same frame for the other batter — suppressed.
    sb.update_batter("KL Rahul", runs=1, balls=3, frame=100)
    assert sb.batting_card["KL Rahul"]["balls"] == 2  # unchanged


def test_double_increment_clears_on_new_frame():
    """Per-frame state must reset on frame boundary — each new frame
    can accept its own striker's balls bump."""
    sb = _sb()
    sb._inn["overs"] = "2.0"
    _seed_batter(sb, "Pathum Nissanka", runs=5, balls=4)
    _seed_batter(sb, "KL Rahul", runs=1, balls=2)
    sb.update_batter("Pathum Nissanka", runs=5, balls=5, frame=100)
    # New frame: striker swapped, Rahul faces a ball
    sb.update_batter("KL Rahul", runs=1, balls=3, frame=101)
    assert sb.batting_card["KL Rahul"]["balls"] == 3


def test_no_double_increment_when_balls_unchanged():
    """Updating the same batter's runs without bumping balls on the
    same frame as another batter's bump is fine — only ball-bumps
    count toward the per-frame quota."""
    sb = _sb()
    sb._inn["overs"] = "2.0"
    _seed_batter(sb, "Pathum Nissanka", runs=5, balls=4)
    _seed_batter(sb, "KL Rahul", runs=1, balls=2)
    sb.update_batter("Pathum Nissanka", runs=5, balls=5, frame=100)
    # Same frame, Rahul: runs change but balls unchanged → allowed.
    sb.update_batter("KL Rahul", runs=1, balls=2, frame=100)
    assert sb.batting_card["KL Rahul"]["balls"] == 2
