"""Tests for the BOWLER-OVERRIDE consensus requirement + BOWLER-AUTO
attribution-freeze (investigation 5, 2026-05-14).

The previous single-read override on ``must_change=True`` flipped
``current_bowler`` to the wrong player on a single VLM hallucination,
then the BOWLER-AUTO cascade credited every subsequent team-score delta
to the now-wrong bowler.  Two changes paired in one commit:

  A. Override requires ≥2-frame consensus (≥3 if leader is well-
     established, lowered by 1 on must_change=True but never below 2).
  B. While override is pending (a candidate is accumulating reads but
     consensus hasn't fired), team-score deltas are buffered and flushed
     to the resolved bowler on consensus-fire / consensus-dissipate.

Run from repo root:
    pytest files/tests/test_bowler_override_consensus.py -q
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
    sb._tracker.confirmed["score"] = 0
    sb._tracker.confirmed["wickets"] = 0
    sb._tracker.confirmed["overs"] = "0.0"
    return sb


def _seed_xi(sb: Scoreboard, name: str, *, overs: str = "0.0",
             runs: int = 0, wickets: int = 0) -> None:
    """Add a bowler to bowling_card with playing-XI flags set so
    update_bowler doesn't early-exit on name-lookup / XI gates."""
    sb.bowling_card[name] = {
        "overs": overs, "runs": runs, "wickets": wickets,
        "maidens": 0, "is_playing_xi": True,
    }
    sb._name_lookup[name.upper()] = name
    sb._name_lookup[name] = name


def _seed_bowler(sb: Scoreboard, name: str, overs: str = "1.0",
                 runs: int = 7, wickets: int = 0) -> None:
    _seed_xi(sb, name, overs=overs, runs=runs, wickets=wickets)
    sb._inn["current_bowler"] = name
    sb._tracker.confirmed["current_bowler"] = name


# -- Change A: override consensus requirement ----------------------------

def test_must_change_single_read_no_longer_flips():
    """Investigation 5 regression: must_change=True + single read of a
    different name used to immediately flip current_bowler.  Must now
    accumulate ≥2 reads before flip."""
    sb = _sb()
    _seed_bowler(sb, "Vaibhav Arora", overs="1.0", runs=7)
    _seed_xi(sb, "Sunil Narine")
    _seed_xi(sb, "Kartik Tyagi")
    _seed_xi(sb, "Anukul Roy", overs="1.0", runs=7)
    sb._bowler_must_change = True
    sb._prev_over_bowler = "Anukul Roy"
    # Single VLM read of a new name — must NOT flip yet.
    sb.update_bowler("Sunil Narine", overs="0.1", runs=0, wickets=0, frame=100)
    assert sb._inn["current_bowler"] == "Vaibhav Arora"
    assert sb._pending_bowler_name == "Sunil Narine"
    assert sb._pending_bowler_count == 1


def test_must_change_second_consistent_read_fires_override():
    """Two consecutive reads of the same candidate satisfy the floor."""
    sb = _sb()
    _seed_bowler(sb, "Vaibhav Arora", overs="1.0", runs=7)
    _seed_xi(sb, "Sunil Narine")
    _seed_xi(sb, "Kartik Tyagi")
    _seed_xi(sb, "Anukul Roy", overs="1.0", runs=7)
    sb._bowler_must_change = True
    sb._prev_over_bowler = "Anukul Roy"
    sb.update_bowler("Sunil Narine", overs="0.1", runs=0, wickets=0, frame=100)
    sb.update_bowler("Sunil Narine", overs="0.2", runs=0, wickets=0, frame=101)
    assert sb._inn["current_bowler"] == "Sunil Narine"


def test_must_change_alternating_names_never_fires():
    """A flapping candidate (different name each frame) must not fire."""
    sb = _sb()
    _seed_bowler(sb, "Vaibhav Arora", overs="1.0", runs=7)
    _seed_xi(sb, "Sunil Narine")
    _seed_xi(sb, "Kartik Tyagi")
    _seed_xi(sb, "Anukul Roy", overs="1.0", runs=7)
    sb._bowler_must_change = True
    sb._prev_over_bowler = "Anukul Roy"
    sb.update_bowler("Sunil Narine", overs="0.1", runs=0, wickets=0, frame=100)
    sb.update_bowler("Kartik Tyagi", overs="0.1", runs=0, wickets=0, frame=101)
    sb.update_bowler("Sunil Narine", overs="0.1", runs=0, wickets=0, frame=102)
    # Each different-name read resets the pending streak to 1 — no flip.
    assert sb._inn["current_bowler"] == "Vaibhav Arora"


def test_match_to_current_bowler_clears_pending():
    """If the VLM read returns to matching the current bowler, the
    pending override candidate is discarded."""
    sb = _sb()
    _seed_bowler(sb, "Vaibhav Arora", overs="1.0", runs=7)
    _seed_xi(sb, "Sunil Narine")
    _seed_xi(sb, "Kartik Tyagi")
    _seed_xi(sb, "Anukul Roy", overs="1.0", runs=7)
    sb._bowler_must_change = True
    sb._prev_over_bowler = "Anukul Roy"
    sb.update_bowler("Sunil Narine", overs="0.1", runs=0, wickets=0, frame=100)
    assert sb._pending_bowler_name == "Sunil Narine"
    # Next read shows current bowler again
    sb.update_bowler("Vaibhav Arora", overs="1.1", runs=8, wickets=0, frame=101)
    assert sb._pending_bowler_name is None
    assert sb._pending_bowler_count == 0
    assert sb._inn["current_bowler"] == "Vaibhav Arora"


def test_high_weight_leader_requires_3_frames():
    """When the current bowler has ≥3 legal balls of accumulated stats
    (high weight), require 3 reads of the candidate (lowered to 2 by
    must_change=True)."""
    sb = _sb()
    _seed_bowler(sb, "Vaibhav Arora", overs="0.5", runs=7)
    # No must_change — pure plain-consensus path. Override threshold
    # falls through to the existing N=3 check.  Two reads must NOT
    # flip even with high-weight leader.
    sb.update_bowler("Sunil Narine", overs="0.1", runs=0, wickets=0, frame=100)
    sb.update_bowler("Sunil Narine", overs="0.2", runs=0, wickets=0, frame=101)
    assert sb._inn["current_bowler"] == "Vaibhav Arora"


# -- Change B: attribution freeze ----------------------------------------

def test_pending_override_freezes_score_attribution():
    """While override is pending, team-score deltas buffer instead of
    crediting the (now-uncertain) current bowler."""
    sb = _sb()
    _seed_bowler(sb, "Vaibhav Arora", overs="1.0", runs=7)
    _seed_xi(sb, "Sunil Narine")
    _seed_xi(sb, "Kartik Tyagi")
    _seed_xi(sb, "Anukul Roy", overs="1.0", runs=7)
    sb._bowler_must_change = True
    sb._prev_over_bowler = "Anukul Roy"
    # Read a different name — override now pending streak=1
    sb.update_bowler("Sunil Narine", overs="0.1", runs=0, wickets=0, frame=100)
    assert sb._pending_bowler_name == "Sunil Narine"
    # Team boundary +4 — must NOT credit Vaibhav (the leader who's
    # being displaced) while override resolution is ambiguous.
    sb._inn["overs"] = "1.1"  # within-over (not boundary skip)
    sb._mirror_team_delta_to_bowler("score", 7, 11, frame=101)
    assert sb.bowling_card["Vaibhav Arora"]["runs"] == 7  # unchanged
    assert sb._bowler_attribution_freeze_runs == 4


def test_freeze_flushes_to_new_bowler_when_override_fires():
    """When the override fires after consensus, buffered runs apply to
    the newly-installed bowler."""
    sb = _sb()
    _seed_bowler(sb, "Vaibhav Arora", overs="1.0", runs=7)
    _seed_xi(sb, "Sunil Narine")
    _seed_xi(sb, "Kartik Tyagi")
    _seed_xi(sb, "Anukul Roy", overs="1.0", runs=7)
    sb._bowler_must_change = True
    sb._prev_over_bowler = "Anukul Roy"
    # Frame 100: 1st read of new name → freeze starts
    sb.update_bowler("Sunil Narine", overs="0.1", runs=0, wickets=0, frame=100)
    # Team boundary while pending
    sb._inn["overs"] = "1.1"
    sb._mirror_team_delta_to_bowler("score", 7, 11, frame=101)
    assert sb._bowler_attribution_freeze_runs == 4
    # Frame 102: 2nd read of same name → override fires
    sb.update_bowler("Sunil Narine", overs="0.2", runs=0, wickets=0, frame=102)
    assert sb._inn["current_bowler"] == "Sunil Narine"
    # Buffered 4 runs flushed to Narine (he just took over)
    assert sb.bowling_card["Sunil Narine"]["runs"] == 4
    assert sb._bowler_attribution_freeze_runs == 0


def test_freeze_flushes_to_leader_when_override_dissipates():
    """When the pending candidate is abandoned (VLM read returns to
    matching current bowler), buffered runs go to the leader who
    successfully defended."""
    sb = _sb()
    _seed_bowler(sb, "Vaibhav Arora", overs="1.0", runs=7)
    _seed_xi(sb, "Sunil Narine")
    _seed_xi(sb, "Kartik Tyagi")
    _seed_xi(sb, "Anukul Roy", overs="1.0", runs=7)
    sb._bowler_must_change = True
    sb._prev_over_bowler = "Anukul Roy"
    sb.update_bowler("Sunil Narine", overs="0.1", runs=0, wickets=0, frame=100)
    sb._inn["overs"] = "1.1"
    sb._mirror_team_delta_to_bowler("score", 7, 11, frame=101)
    assert sb._bowler_attribution_freeze_runs == 4
    # Next read returns to Vaibhav — override dissipates
    sb.update_bowler("Vaibhav Arora", overs="1.1", runs=8, wickets=0, frame=102)
    assert sb._pending_bowler_name is None
    # Buffered runs applied to Vaibhav (the defended leader)
    assert sb.bowling_card["Vaibhav Arora"]["runs"] == 7 + 4


def test_no_freeze_when_no_pending_override():
    """When no override is pending, BOWLER-AUTO behaves as before."""
    sb = _sb()
    _seed_bowler(sb, "Vaibhav Arora", overs="1.0", runs=7)
    assert sb._pending_bowler_name is None
    sb._inn["overs"] = "1.1"
    sb._mirror_team_delta_to_bowler("score", 7, 8, frame=100)
    # Normal credit — Vaibhav gets the +1
    assert sb.bowling_card["Vaibhav Arora"]["runs"] == 8
    assert sb._bowler_attribution_freeze_runs == 0


def test_freeze_handles_multiple_deltas_while_pending():
    """Multiple team-score increments during the pending window all
    accumulate into the buffer."""
    sb = _sb()
    _seed_bowler(sb, "Vaibhav Arora", overs="1.0", runs=7)
    _seed_xi(sb, "Sunil Narine")
    _seed_xi(sb, "Kartik Tyagi")
    _seed_xi(sb, "Anukul Roy", overs="1.0", runs=7)
    sb._bowler_must_change = True
    sb._prev_over_bowler = "Anukul Roy"
    sb.update_bowler("Sunil Narine", overs="0.1", runs=0, wickets=0, frame=100)
    sb._inn["overs"] = "1.1"
    sb._mirror_team_delta_to_bowler("score", 7, 8, frame=101)
    sb._mirror_team_delta_to_bowler("score", 8, 12, frame=102)
    assert sb._bowler_attribution_freeze_runs == 5
    # Override fires
    sb.update_bowler("Sunil Narine", overs="0.2", runs=0, wickets=0, frame=103)
    assert sb._inn["current_bowler"] == "Sunil Narine"
    assert sb.bowling_card["Sunil Narine"]["runs"] == 5
