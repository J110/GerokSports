"""Unit tests for files/score_manager_derivation.py.

§15 Session A step 1 deliverable. Covers happy paths + every edge case
named in §12.2, §13.6, §14.7 of the design memo. All tests are pure —
no SM instantiation, no scoreboard, no trace recorder.

Run: `files/.venv/bin/python -m pytest files/tests/test_score_manager_derivation.py -v`
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from score_manager_derivation import (  # noqa: E402
    SnapshotPrimitives,
    StrikerEvent,
    ThisOverToken,
    WicketAmbiguousDualChange,
    WicketEvent,
    derive_striker_event,
    derive_this_over_token,
    derive_wicket_event,
)


def snap(**overrides) -> SnapshotPrimitives:
    base = dict(
        score=0,
        wickets=0,
        overs="0.0",
        bat1_name="A",
        bat2_name="B",
        bowler_name="Bowler",
        striker="A",
        non_striker="B",
        extras_total=0,
        extras_wd=0,
        extras_nb=0,
        extras_b=0,
        extras_lb=0,
        first_striker=None,
        legal_balls_in_over=0,
    )
    base.update(overrides)
    return SnapshotPrimitives(**base)


# ─────────────────────────────────────────────────────────────────────
# derive_wicket_event — §12.2
# ─────────────────────────────────────────────────────────────────────


class TestDeriveWicketEvent:
    def test_no_wicket_returns_none(self):
        prior = snap(wickets=0)
        current = snap(wickets=0, score=4, overs="0.1")
        assert derive_wicket_event(prior, current, "Bowler") is None

    def test_standard_wicket_single_slot_change(self):
        prior = snap(wickets=0, bat1_name="Striker", bat2_name="Partner")
        current = snap(
            wickets=1, bat1_name="NewBat", bat2_name="Partner",
            overs="4.6")
        ev = derive_wicket_event(prior, current, "Bowler")
        assert ev is not None
        assert ev.delta_wickets == 1
        assert ev.dismissed_batter == "Striker"
        assert ev.bowler_name == "Bowler"
        assert ev.over_ball == "4.6"
        assert ev.this_over_token == "W"

    def test_runout_on_scoring_ball_yields_N_plus_W(self):
        prior = snap(wickets=0, score=10, bat1_name="A", bat2_name="B")
        current = snap(
            wickets=1, score=11, bat1_name="A", bat2_name="C",
            overs="5.3")
        ev = derive_wicket_event(prior, current, "Bowler")
        assert ev is not None
        assert ev.dismissed_batter == "B"
        assert ev.is_runout_speculative is True
        assert ev.this_over_token == "1+W"

    def test_wide_with_stumping_yields_Wd_plus_W(self):
        prior = snap(
            wickets=3, score=80, bat1_name="A", bat2_name="B",
            extras_total=5, extras_wd=5)
        current = snap(
            wickets=4, score=81, bat1_name="C", bat2_name="B",
            overs="10.1", extras_total=6, extras_wd=6)
        ev = derive_wicket_event(prior, current, "Roy")
        assert ev is not None
        assert ev.dismissed_batter == "A"
        assert ev.this_over_token == "Wd+W"
        assert ev.is_extras_dismissal is True

    def test_noball_with_wicket_yields_Nb_plus_W(self):
        prior = snap(
            score=50, wickets=2, bat1_name="A", bat2_name="B",
            extras_total=2, extras_nb=2)
        current = snap(
            score=51, wickets=3, bat1_name="A", bat2_name="C",
            overs="8.3", extras_total=3, extras_nb=3)
        ev = derive_wicket_event(prior, current, "Bowler")
        assert ev is not None
        assert ev.this_over_token == "Nb+W"

    def test_edge_case_2_no_slot_change_dismissed_None(self):
        prior = snap(wickets=0, bat1_name="A", bat2_name="B")
        current = snap(
            wickets=1, bat1_name="A", bat2_name="B", overs="3.4")
        ev = derive_wicket_event(prior, current, "Bowler")
        assert ev is not None
        assert ev.dismissed_batter is None

    def test_edge_case_3_dual_slot_change_raises(self):
        prior = snap(wickets=0, bat1_name="A", bat2_name="B")
        current = snap(
            wickets=1, bat1_name="X", bat2_name="Y", overs="3.4")
        with pytest.raises(WicketAmbiguousDualChange):
            derive_wicket_event(prior, current, "Bowler")

    def test_bowler_name_propagated_from_tracker(self):
        prior = snap(wickets=0)
        current = snap(wickets=1, overs="2.4")
        ev = derive_wicket_event(prior, current, "Pat Cummins")
        assert ev.bowler_name == "Pat Cummins"

    def test_bowler_name_None_propagates(self):
        prior = snap(wickets=0)
        current = snap(wickets=1, overs="2.4")
        ev = derive_wicket_event(prior, current, None)
        assert ev.bowler_name is None

    def test_multi_wicket_delta(self):
        prior = snap(wickets=1, bat1_name="A", bat2_name="B")
        current = snap(
            wickets=3, bat1_name="C", bat2_name="D", overs="5.3")
        with pytest.raises(WicketAmbiguousDualChange):
            derive_wicket_event(prior, current, "Bowler")


# ─────────────────────────────────────────────────────────────────────
# derive_striker_event — §13.2 + §13.6
# ─────────────────────────────────────────────────────────────────────


class TestDeriveStrikerEvent:
    def test_cold_start_first_striker_init(self):
        prior = snap(striker=None, non_striker=None)
        current = snap(striker=None, non_striker=None, first_striker="A")
        ev = derive_striker_event(
            prior, current, None,
            over_boundary_crossed=False, legal_ball_completed=False)
        assert ev.reason == "first_striker_init"
        assert ev.next_striker == "A"
        # B-2: cold-start init sets non-striker to the partner at crease
        assert ev.next_non_striker == "B"

    def test_cold_start_no_primitive_no_change(self):
        prior = snap(striker=None, non_striker=None)
        current = snap(striker=None, non_striker=None, first_striker=None)
        ev = derive_striker_event(
            prior, current, None,
            over_boundary_crossed=False, legal_ball_completed=False)
        assert ev.reason == "no_change"
        assert ev.next_striker is None

    def test_post_wicket_striker_None_does_not_trigger_cold_start_init(self):
        # Mid-innings post-wicket: striker cleared by wicket dispatch,
        # non-striker remains as the surviving batter. Rule 1 must NOT
        # re-seed striker from self.first_striker (innings opener) —
        # that's wrong-batter attribution. Discovered as +2 Boundary
        # regression at over_ball 8.5 during §15 step-7 attempt.
        prior = snap(
            striker=None, non_striker="Nissanka",
            bat1_name=None, bat2_name="Nissanka",
            first_striker="Nissanka")
        current = snap(
            striker=None, non_striker="Nissanka",
            bat1_name=None, bat2_name="Nissanka",
            first_striker="Nissanka", overs="8.1")
        ev = derive_striker_event(
            prior, current, None,
            over_boundary_crossed=False, legal_ball_completed=True)
        assert ev.reason == "no_change"
        assert ev.next_striker is None
        # non-striker is preserved
        assert ev.next_non_striker == "Nissanka"

    def test_odd_run_rotates_strike(self):
        prior = snap(
            striker="A", bat1_name="A", bat2_name="B", score=10,
            overs="3.3")
        current = snap(
            striker="A", bat1_name="A", bat2_name="B", score=11,
            overs="3.4")
        ev = derive_striker_event(
            prior, current, None,
            over_boundary_crossed=False, legal_ball_completed=True)
        assert ev.reason == "odd_run_rotation"
        assert ev.next_striker == "B"
        # B-2: pair swap is atomic — non-striker becomes the prior striker
        assert ev.next_non_striker == "A"
        assert ev.prev_striker == "A"
        assert ev.prev_non_striker == "B"

    def test_even_run_no_rotation(self):
        prior = snap(striker="A", score=10, overs="3.3")
        current = snap(striker="A", score=12, overs="3.4")
        ev = derive_striker_event(
            prior, current, None,
            over_boundary_crossed=False, legal_ball_completed=True)
        assert ev.reason == "no_change"

    def test_dot_ball_no_rotation(self):
        prior = snap(striker="A", score=10, overs="3.3")
        current = snap(striker="A", score=10, overs="3.4")
        ev = derive_striker_event(
            prior, current, None,
            over_boundary_crossed=False, legal_ball_completed=True)
        assert ev.reason == "no_change"

    def test_end_of_over_swap(self):
        prior = snap(
            striker="A", bat1_name="A", bat2_name="B", score=10,
            overs="3.5")
        current = snap(
            striker="A", bat1_name="A", bat2_name="B", score=10,
            overs="4.0")
        ev = derive_striker_event(
            prior, current, None,
            over_boundary_crossed=True, legal_ball_completed=True)
        assert ev.reason == "end_of_over_swap"
        assert ev.next_striker == "B"
        assert ev.next_non_striker == "A"

    def test_wicket_striker_dismissed_new_batter_takes_strike(self):
        we = WicketEvent(
            delta_wickets=1, over_ball="4.6", bowler_name="Bowler",
            dismissed_batter="A", delta_score=0, delta_extras=0,
            this_over_token="W", is_extras_dismissal=False,
            is_runout_speculative=False)
        prior = snap(
            striker="A", non_striker="B",
            bat1_name="A", bat2_name="B")
        current = snap(
            striker="A", non_striker="B",
            bat1_name="NewBat", bat2_name="B",
            wickets=1, overs="4.6")
        ev = derive_striker_event(
            prior, current, we,
            over_boundary_crossed=False, legal_ball_completed=True)
        assert ev.reason == "wicket_new_batter"
        assert ev.next_striker == "NewBat"
        # B-2: surviving partner becomes the non-striker
        assert ev.next_non_striker == "B"

    def test_wicket_non_striker_dismissed_striker_stays(self):
        we = WicketEvent(
            delta_wickets=1, over_ball="4.3", bowler_name="Bowler",
            dismissed_batter="B", delta_score=0, delta_extras=0,
            this_over_token="W", is_extras_dismissal=False,
            is_runout_speculative=False)
        prior = snap(
            striker="A", non_striker="B",
            bat1_name="A", bat2_name="B")
        current = snap(
            striker="A", non_striker="B",
            bat1_name="A", bat2_name="NewBat",
            wickets=1, overs="4.3")
        ev = derive_striker_event(
            prior, current, we,
            over_boundary_crossed=False, legal_ball_completed=True)
        assert ev.reason == "wicket_non_striker_stays"
        assert ev.next_striker == "A"
        # B-2: new batter becomes the non-striker
        assert ev.next_non_striker == "NewBat"

    def test_runout_ambiguous_default_parity_with_odd_runs(self):
        we = WicketEvent(
            delta_wickets=1, over_ball="5.3", bowler_name="Bowler",
            dismissed_batter=None, delta_score=1, delta_extras=0,
            this_over_token="1+W", is_extras_dismissal=False,
            is_runout_speculative=True)
        prior = snap(striker="A", bat1_name="A", bat2_name="B", score=10)
        current = snap(
            striker="A", bat1_name="A", bat2_name="B", score=11,
            wickets=1, overs="5.3")
        ev = derive_striker_event(
            prior, current, we,
            over_boundary_crossed=False, legal_ball_completed=True)
        assert ev.reason == "runout_ambiguous_default_parity"
        assert ev.next_striker == "B"

    def test_wide_with_stumping_no_legal_ball_rotation(self):
        # §13.6.3 — wicket-on-wide. Extras only; no rotation rule 4.
        we = WicketEvent(
            delta_wickets=1, over_ball="10.1", bowler_name="Roy",
            dismissed_batter="A", delta_score=1, delta_extras=1,
            this_over_token="Wd+W", is_extras_dismissal=True,
            is_runout_speculative=False)
        prior = snap(
            striker="A", bat1_name="A", bat2_name="B", score=80,
            extras_total=5, extras_wd=5)
        current = snap(
            striker="A", bat1_name="C", bat2_name="B",
            wickets=1, score=81, overs="10.1",
            extras_total=6, extras_wd=6)
        ev = derive_striker_event(
            prior, current, we,
            over_boundary_crossed=False, legal_ball_completed=False)
        assert ev.reason == "wicket_new_batter"
        assert ev.next_striker == "C"

    def test_leg_byes_odd_runs_DO_rotate_strike(self):
        # §13.6 #4 — byes/leg-byes ARE legal-ball deliveries where
        # batters cross on odd runs. The runs go to extras, but rotation
        # still fires. (Distinguish from wides/no-balls — no crossing.)
        prior = snap(
            striker="A", bat1_name="A", bat2_name="B", score=10,
            overs="3.4", extras_total=0, extras_lb=0)
        current = snap(
            striker="A", bat1_name="A", bat2_name="B", score=13,
            overs="3.5", extras_total=3, extras_lb=3)
        ev = derive_striker_event(
            prior, current, None,
            over_boundary_crossed=False, legal_ball_completed=True)
        assert ev.reason == "odd_run_rotation"
        assert ev.next_striker == "B"

    def test_b2_atomic_pair_via_apply_striker_event(self):
        # B-2: apply_striker_event must mutate BOTH self.striker AND
        # self.non in a single call — no caller-side mirror needed.
        # Discovered as +2 Boundary-counter-double-increment at over_ball
        # 8.5 during §15 step-5 wire-through (commit f233217).
        import sys as _sys
        from pathlib import Path as _P
        _sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
        import score_manager  # noqa: E402
        sm = score_manager.ScoreManager(shadow=True)
        sm.striker = "A"
        sm.non = "B"
        from score_manager_derivation import StrikerEvent as _SE
        ev = _SE(
            prev_striker="A", next_striker="B",
            prev_non_striker="B", next_non_striker="A",
            reason="odd_run_rotation")
        sm.apply_striker_event(ev)
        assert sm.striker == "B"
        assert sm.non == "A"
        # no_change reason must NOT mutate
        sm.striker = "X"; sm.non = "Y"
        ev2 = _SE(
            prev_striker="X", next_striker="X",
            prev_non_striker="Y", next_non_striker="Y",
            reason="no_change")
        sm.apply_striker_event(ev2)
        assert sm.striker == "X"
        assert sm.non == "Y"

    def test_odd_run_on_end_of_over_cancels_to_no_change(self):
        # Cricket rule: 1 run on last ball of over = batters cross (run)
        # + switch ends (over-end) = net same striker continues.
        # Discovered as +19 Boundary-counter-double-increment regression
        # at §15 step-5 harness diff.
        prior = snap(
            striker="A", bat1_name="A", bat2_name="B", score=10,
            overs="3.5")
        current = snap(
            striker="A", bat1_name="A", bat2_name="B", score=11,
            overs="4.0")
        ev = derive_striker_event(
            prior, current, None,
            over_boundary_crossed=True, legal_ball_completed=True)
        assert ev.reason == "no_change"
        assert ev.next_striker == "A"

    def test_even_run_on_end_of_over_swaps(self):
        # 2 runs on last ball of over = no crossing + switch ends =
        # net rotation (over-end swap only).
        prior = snap(
            striker="A", bat1_name="A", bat2_name="B", score=10,
            overs="3.5")
        current = snap(
            striker="A", bat1_name="A", bat2_name="B", score=12,
            overs="4.0")
        ev = derive_striker_event(
            prior, current, None,
            over_boundary_crossed=True, legal_ball_completed=True)
        assert ev.reason == "end_of_over_swap"
        assert ev.next_striker == "B"

    def test_lost_frames_striker_ambiguous(self):
        # §13.6 #5 — multiple legal balls in one snapshot transition.
        # Refuse to derive rotation; emit lost_frames_ambiguous.
        prior = snap(
            striker="A", bat1_name="A", bat2_name="B", score=10,
            overs="3.2")
        current = snap(
            striker="A", bat1_name="A", bat2_name="B", score=15,
            overs="3.5")
        ev = derive_striker_event(
            prior, current, None,
            over_boundary_crossed=False, legal_ball_completed=True)
        assert ev.reason == "lost_frames_ambiguous"
        assert ev.next_striker == "A"

    def test_legal_ball_drift_returns_prev(self):
        # Striker isn't in current crease set — pipeline drift case.
        prior = snap(
            striker="X", bat1_name="A", bat2_name="B", score=10,
            overs="3.3")
        current = snap(
            striker="X", bat1_name="A", bat2_name="B", score=11,
            overs="3.4")
        ev = derive_striker_event(
            prior, current, None,
            over_boundary_crossed=False, legal_ball_completed=True)
        # _swap_partner returns prev when prev isn't in either slot
        assert ev.reason == "odd_run_rotation"
        assert ev.next_striker == "X"


# ─────────────────────────────────────────────────────────────────────
# derive_this_over_token — §14.2 + §14.7
# ─────────────────────────────────────────────────────────────────────


class TestDeriveThisOverToken:
    def test_idle_frame_returns_none(self):
        prior = snap(score=10, wickets=1, overs="3.4")
        current = snap(score=10, wickets=1, overs="3.4")
        assert derive_this_over_token(prior, current, None) is None

    def test_dot_ball(self):
        prior = snap(score=10, overs="3.4")
        current = snap(score=10, overs="3.5")
        tok = derive_this_over_token(prior, current, None)
        assert tok is not None
        assert tok.raw == "."

    def test_single_run(self):
        prior = snap(score=10, overs="3.4")
        current = snap(score=11, overs="3.5")
        tok = derive_this_over_token(prior, current, None)
        assert tok.raw == "1"

    def test_four(self):
        prior = snap(score=10, overs="3.4")
        current = snap(score=14, overs="3.5")
        tok = derive_this_over_token(prior, current, None)
        assert tok.raw == "4"

    def test_six(self):
        prior = snap(score=10, overs="3.4")
        current = snap(score=16, overs="3.5")
        tok = derive_this_over_token(prior, current, None)
        assert tok.raw == "6"

    def test_wide_no_legal_ball(self):
        prior = snap(score=10, overs="3.4", extras_total=0, extras_wd=0)
        current = snap(
            score=11, overs="3.4", extras_total=1, extras_wd=1)
        tok = derive_this_over_token(prior, current, None)
        assert tok.raw == "Wd"
        assert tok.delta_legal_balls == 0
        assert tok.extras_type == "wd"

    def test_no_ball(self):
        prior = snap(score=10, overs="3.4", extras_total=0, extras_nb=0)
        current = snap(
            score=11, overs="3.4", extras_total=1, extras_nb=1)
        tok = derive_this_over_token(prior, current, None)
        assert tok.raw == "Nb"
        assert tok.extras_type == "nb"

    def test_leg_bye_legal_ball(self):
        prior = snap(score=10, overs="3.4", extras_total=0, extras_lb=0)
        current = snap(
            score=11, overs="3.5", extras_total=1, extras_lb=1)
        tok = derive_this_over_token(prior, current, None)
        assert tok.raw == "1lb"
        assert tok.delta_legal_balls == 1
        assert tok.extras_type == "lb"

    def test_wicket_plain_W(self):
        we = WicketEvent(
            delta_wickets=1, over_ball="4.6", bowler_name="Bowler",
            dismissed_batter="A", delta_score=0, delta_extras=0,
            this_over_token="W", is_extras_dismissal=False,
            is_runout_speculative=False)
        prior = snap(score=10, wickets=0, overs="4.5")
        current = snap(score=10, wickets=1, overs="4.6")
        tok = derive_this_over_token(prior, current, we)
        assert tok.raw == "W"
        assert tok.wicket_flag is True

    def test_wicket_compound_Wd_W(self):
        we = WicketEvent(
            delta_wickets=1, over_ball="10.1", bowler_name="Roy",
            dismissed_batter="A", delta_score=1, delta_extras=1,
            this_over_token="Wd+W", is_extras_dismissal=True,
            is_runout_speculative=False)
        prior = snap(
            score=80, wickets=3, overs="10.0",
            extras_total=5, extras_wd=5)
        current = snap(
            score=81, wickets=4, overs="10.1",
            extras_total=6, extras_wd=6)
        tok = derive_this_over_token(prior, current, we)
        assert tok.raw == "Wd+W"

    def test_runout_compound_N_W(self):
        we = WicketEvent(
            delta_wickets=1, over_ball="5.3", bowler_name="Bowler",
            dismissed_batter=None, delta_score=2, delta_extras=0,
            this_over_token="2+W", is_extras_dismissal=False,
            is_runout_speculative=True)
        prior = snap(score=10, wickets=0, overs="5.2")
        current = snap(score=12, wickets=1, overs="5.3")
        tok = derive_this_over_token(prior, current, we)
        assert tok.raw == "2+W"

    def test_wicket_inferred_without_event_param(self):
        # No wicket_event passed — function derives token inline.
        prior = snap(score=10, wickets=0, overs="4.5")
        current = snap(score=10, wickets=1, overs="4.6")
        tok = derive_this_over_token(prior, current, None)
        assert tok.raw == "W"
        assert tok.wicket_flag is True

    def test_lost_frames_cluster(self):
        # §14.7 #2 — multiple legal balls in one snapshot transition
        prior = snap(score=10, overs="3.0")
        current = snap(score=16, overs="3.3")
        tok = derive_this_over_token(prior, current, None)
        assert tok.raw == "MULTI"
        assert tok.delta_legal_balls == 3
        assert tok.cluster_tokens == ["?", "?", "?"]

    def test_over_rollover_crosses(self):
        # Pipeline emits "1.0" post-rollover after the 6th ball of over 0.
        # In the ball_id convention currently rendered ("0.6"), this is
        # the same legal-ball count delta = 1.
        prior = snap(score=5, overs="0.5")
        current = snap(score=6, overs="0.6")
        tok = derive_this_over_token(prior, current, None)
        assert tok.raw == "1"
        assert tok.delta_legal_balls == 1
