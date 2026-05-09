"""Track A mechanical batch: P11/P14/P15/P16/P10/P20 unit coverage.

Run: pytest files/tests/test_track_a_mechanical_batch.py -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from cricket_rules import validate_direct_proposal  # noqa: E402
from eyes.scoreboard import Scoreboard  # noqa: E402
from eyes.squad_scraper import squad_membership_by_team_name  # noqa: E402
from eyes.this_over import ThisOverManager  # noqa: E402
from test_pipeline import _to_win_score_basis  # noqa: E402


def _sb_xi_sub() -> Scoreboard:
    xi = [f"P{i}" for i in range(11)]
    subs = [f"S{i}" for i in range(5)]
    squad = xi + subs
    sb = Scoreboard()
    sb.setup_innings(
        "CSK", "MI", squad, ["B0"],
        batting_xi=xi,
        bowling_xi=["B0"],
        batting_subs=subs,
        bowling_subs=[],
    )
    sb._inn["wickets"] = 0
    sb._inn["overs"] = "0.0"
    return sb


def test_xi_gate_accepts_active_xi_batter():
    sb = _sb_xi_sub()
    sb.batting_card["P0"]["status"] = "yet_to_bat"
    assert sb.update_batter("P0", striker=True, frame=1)


def test_xi_gate_rejects_not_in_squad():
    sb = _sb_xi_sub()
    k, r = sb.is_eligible_to_bat_or_bowl("Nobody", "CSK")
    assert k == "reject" and r == "not_in_squad"


def test_xi_gate_rejects_replaced_player():
    sb = _sb_xi_sub()
    sb.mark_player_replaced_for_testing("CSK", "P0")
    sb.batting_card["P0"]["status"] = "yet_to_bat"
    assert not sb.update_batter("P0", striker=True, frame=1)


def test_impact_player_candidate_3frame_consensus_required():
    sb = _sb_xi_sub()
    sb.batting_card["S0"]["status"] = "yet_to_bat"
    assert not sb.update_batter("S0", striker=True, frame=1)
    assert not sb.update_batter("S0", striker=True, frame=2)
    assert sb.update_batter("S0", striker=True, frame=3)
    assert "S0" in sb._team_match_membership["CSK"]["active_xi"]


def test_impact_player_activation_marks_impact_used():
    sb = _sb_xi_sub()
    sb.batting_card["S0"]["status"] = "yet_to_bat"
    for f in (1, 2, 3):
        sb.update_batter("S0", striker=True, frame=f)
    assert sb._team_match_membership["CSK"]["impact_used"]


def test_impact_player_second_activation_rejected():
    sb = _sb_xi_sub()
    sb.batting_card["S0"]["status"] = "yet_to_bat"
    sb.batting_card["S1"]["status"] = "yet_to_bat"
    for f in (1, 2, 3):
        sb.update_batter("S0", striker=True, frame=f)
    assert not sb.update_batter("S1", striker=True, frame=10)


def test_bowler_gate_uses_bowling_team_xi():
    sb = Scoreboard()
    sb.setup_innings(
        "CSK", "MI",
        ["b" + str(i) for i in range(11)] + ["bs0", "bs1"],
        ["bw0"] + ["bws0", "bws1"],
        batting_xi=["b" + str(i) for i in range(11)],
        bowling_xi=["bw0"],
        batting_subs=["bs0", "bs1"],
        bowling_subs=["bws0", "bws1"],
    )
    sb._inn["overs"] = "1.0"
    assert not sb.update_bowler("bws0", overs="0.1", runs=0, wickets=0, frame=1)
    assert not sb.update_bowler("bws0", overs="0.1", runs=0, wickets=0, frame=2)
    assert sb.update_bowler("bws0", overs="0.1", runs=0, wickets=0, frame=3)


def test_squad_scrape_captures_xi_and_subs():
    raw = {
        "team_a": {
            "name": "CSK",
            "playing_xi": [{"name": "A", "role": "Batter"}],
            "bench": [{"name": "Sub1", "role": "Bowler"}],
        },
        "team_b": {
            "name": "MI",
            "playing_xi": [{"name": "B", "role": "Bowler"}],
            "bench": [],
        },
    }
    m = squad_membership_by_team_name(raw)
    assert m["CSK"]["xi"] == ["A"] and m["CSK"]["subs"] == ["Sub1"]
    assert m["MI"]["xi"] == ["B"] and m["MI"]["subs"] == []


def test_batter_consensus_reset_on_identity_change():
    sb = _sb_xi_sub()
    sb.batting_card["P0"]["status"] = "batting"
    sb.batting_card["P1"]["status"] = "batting"
    sb.update_batter("P0", striker=True, frame=1)
    sb.update_batter("P1", striker=False, frame=2)
    sb._tracker.force_set("bat:P0:runs", 44)
    sb._tracker.force_set("bat:P0:balls", 10)
    sb.update_batter("P1", striker=True, frame=3)
    sb.update_batter("P0", striker=False, frame=4)
    assert sb._tracker.confirmed.get("bat:P0:runs") is None


def test_bowler_stats_sanity_rejects_spell_above_team_overs():
    sb = Scoreboard()
    sb.setup_innings("CSK", "MI", ["b0"], ["bw0", "bw1"],
                     batting_xi=["b0"], bowling_xi=["bw0"],
                     batting_subs=[], bowling_subs=["bw1"])
    sb._inn["overs"] = "1.1"
    sb.bowling_card["bw1"]["is_playing_xi"] = True
    assert not sb.update_bowler(
        "bw1", overs="4.0", runs=7, wickets=2, frame=1)


def test_score_overs_rr_reject_cold_start():
    r = validate_direct_proposal(
        cur_score=None,
        cur_overs=None,
        cur_wickets=None,
        new_score=9,
        new_overs=7.0,
        new_wickets=None,
        target=None,
        innings=2,
    )
    assert not r.ok and "SCORE-OVERS-RR-REJECT" in (r.reject_reason or "")


def test_this_over_timeout_gap_infer():
    om = ThisOverManager()
    om.this_over = []
    om.fill_strip_coverage_gap("16.0", "16.2", 124, 126, frame_count=10)
    # 2026-05-03 (U5): score delta +2 attributed to last padded slot.
    # Old behavior was ['?', '?']. See files/docs/investigations/
    # this_over_warm_restart_slot_misalignment.md.
    assert om.this_over == ["?", "2"]


def test_this_over_timeout_gap_infer_no_score_delta():
    """When score is unchanged, all padded slots remain '?' placeholders."""
    om = ThisOverManager()
    om.this_over = []
    om.fill_strip_coverage_gap("16.0", "16.2", 124, 124, frame_count=10)
    assert om.this_over == ["?", "?"]


def test_this_over_timeout_gap_infer_delta_too_large():
    """Score deltas > 6 runs are not attributed to a single slot."""
    om = ThisOverManager()
    om.this_over = []
    om.fill_strip_coverage_gap("16.0", "16.2", 124, 132, frame_count=10)
    assert om.this_over == ["?", "?"]


# ── N7: TO_WIN target uses strip-local score when consensus lags ────


def test_to_win_target_uses_strip_local_score_when_consensus_lags():
    upper_desc = "RCB 98-1 (8.5)  TO WIN 68 OFF 67"
    runs_needed = 68
    basis = _to_win_score_basis(upper_desc, score_now=96)
    assert basis == 98
    assert basis + runs_needed == 166


def test_to_win_target_falls_back_to_consensus_when_no_strip_score():
    upper_desc = "TO WIN 68 OFF 67"
    basis = _to_win_score_basis(upper_desc, score_now=96)
    assert basis == 96


def test_to_win_target_keeps_consensus_when_strip_score_lower():
    upper_desc = "RCB 96-1 (8.5)  TO WIN 70 OFF 67"
    basis = _to_win_score_basis(upper_desc, score_now=98)
    assert basis == 98


def test_to_win_target_rejects_invalid_strip_score():
    upper_desc = "RCB 999 RUNS  TO WIN 68 OFF 67"
    basis = _to_win_score_basis(upper_desc, score_now=96)
    assert basis == 96

