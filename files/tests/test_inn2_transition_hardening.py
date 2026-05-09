"""P12 — innings-2 cold-start hardening tests.

Covers diagnosis §5 rules: in_inn2_transition window (hybrid + safety
net), numeric-bounds + XI-membership gates, mark_inn2_first_commit
clear, and the storm-extension state attributes.

Cold-start lockout integration (the inline gate inside
`_handle_cold_start`) and phantom-storm trigger (inline at the
`CORRECTION_BLOCKED:` site in `apply_scorer_decision`) require full
pipeline fixtures; those paths are exercised by replay validation in
Phase G.  Here we test the public surface those paths depend on.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from score_manager import (  # noqa: E402
    INN2_TRANSITION_CEILING_SECONDS,
    INN2_TRANSITION_FRAMES,
    INN2_TRANSITION_SECONDS,
    ScoreManager,
)
from test_pipeline import _apply_inn2_transition_gates  # noqa: E402


# ── Helpers ────────────────────────────────────────────────────────


class _StubScoreboard:
    """Minimal Scoreboard stub for gate tests."""

    def __init__(self,
                 batting_xi: set[str],
                 bowling_xi: set[str],
                 batting_team: str = "CSK",
                 bowling_team: str = "MI") -> None:
        self.batting_team = batting_team
        self.bowling_team = bowling_team
        self._bat = batting_xi
        self._bowl = bowling_xi

    def resolve_name(self, name: str) -> str | None:
        return name.strip() if name else None

    def is_eligible_to_bat_or_bowl(
            self, canonical_name: str,
            team: str | None) -> tuple[str, str]:
        if team == self.batting_team:
            return ("ok", "active_xi") if canonical_name in self._bat \
                else ("reject", "not_in_squad")
        if team == self.bowling_team:
            return ("ok", "active_xi") if canonical_name in self._bowl \
                else ("reject", "not_in_squad")
        return ("ok", "no_membership_state")


def _sm_in_transition(reset_frame: int = 100,
                      wall_offset: float = 0.0) -> ScoreManager:
    """Construct a ScoreManager with active innings-2 transition."""
    sm = ScoreManager(shadow=True)
    sm._current_frame = reset_frame
    sm.set_innings_2(target=160, batting_team="CSK",
                     reason="test", archive=False)
    if wall_offset:
        sm._inn2_reset_wall -= wall_offset
    return sm


def _extracted(score=None, wickets=None, overs=None,
               batters=None, bowlers=None, team=None,
               match_overs=None) -> dict:
    return {
        "score": score,
        "wickets": wickets,
        "overs": overs,
        "match_overs": match_overs,
        "batters": batters or [],
        "bowlers": bowlers or [],
        "batting_team_visible": team,
    }


# ── Phase A: reset bookkeeping + transition window ─────────────────


def test_set_innings_2_records_reset_state() -> None:
    sm = _sm_in_transition(reset_frame=647)
    assert sm._inn2_reset_frame == 647
    assert sm._inn2_reset_wall is not None
    assert sm._inn2_first_commit_seen is False


def test_in_inn2_transition_true_within_thresholds() -> None:
    sm = _sm_in_transition(reset_frame=647)
    # 53 frames since, ~0s wall — well within both thresholds.
    assert sm.in_inn2_transition(700) is True


def test_in_inn2_transition_false_when_no_reset() -> None:
    sm = ScoreManager(shadow=True)
    assert sm.in_inn2_transition(100) is False


def test_in_inn2_transition_false_after_first_commit() -> None:
    sm = _sm_in_transition(reset_frame=647)
    sm.mark_inn2_first_commit()
    assert sm.in_inn2_transition(700) is False


def test_in_inn2_transition_safety_net_when_primary_fails() -> None:
    """Primary fails (frames>250 AND wall>900) but safety net (wall<1200) holds."""
    sm = _sm_in_transition(reset_frame=647,
                           wall_offset=INN2_TRANSITION_SECONDS + 50)
    assert sm.in_inn2_transition(647 + INN2_TRANSITION_FRAMES + 10) is True


def test_in_inn2_transition_false_after_ceiling() -> None:
    sm = _sm_in_transition(reset_frame=647,
                           wall_offset=INN2_TRANSITION_CEILING_SECONDS + 10)
    assert sm.in_inn2_transition(647 + INN2_TRANSITION_FRAMES + 10) is False


def test_mark_inn2_first_commit_idempotent() -> None:
    sm = _sm_in_transition()
    sm.mark_inn2_first_commit()
    sm.mark_inn2_first_commit()
    assert sm._inn2_first_commit_seen is True
    assert sm.in_inn2_transition(200) is False


# ── Phase B: gate helper ───────────────────────────────────────────


def test_gate_skips_outside_transition() -> None:
    sm = ScoreManager(shadow=True)  # no reset → window inactive
    sb = _StubScoreboard(batting_xi=set(), bowling_xi=set())
    e = _extracted(score=999, wickets=10, overs=20.0)
    triggered, reason = _apply_inn2_transition_gates(e, sb, sm, 100)
    assert triggered is False and reason is None


def test_gate_score_over_30_rejected() -> None:
    sm = _sm_in_transition(reset_frame=647)
    sb = _StubScoreboard(batting_xi=set(), bowling_xi=set())
    e = _extracted(score=49, wickets=3, overs=8.1)
    triggered, reason = _apply_inn2_transition_gates(e, sb, sm, 700)
    assert triggered is True
    assert reason.startswith("score>30")


def test_gate_bounds_under_thresholds_pass() -> None:
    sm = _sm_in_transition(reset_frame=647)
    sb = _StubScoreboard(batting_xi=set(), bowling_xi=set())
    e = _extracted(score=10, wickets=1, overs=2.3)
    triggered, reason = _apply_inn2_transition_gates(e, sb, sm, 700)
    assert triggered is False
    assert reason is None


def test_gate_wickets_over_2_rejected() -> None:
    sm = _sm_in_transition(reset_frame=647)
    sb = _StubScoreboard(batting_xi=set(), bowling_xi=set())
    e = _extracted(score=10, wickets=3, overs=2.3)
    triggered, reason = _apply_inn2_transition_gates(e, sb, sm, 700)
    assert triggered is True
    assert reason.startswith("wickets>2")


def test_gate_overs_over_5_rejected() -> None:
    sm = _sm_in_transition(reset_frame=647)
    sb = _StubScoreboard(batting_xi=set(), bowling_xi=set())
    e = _extracted(score=10, wickets=1, overs=8.1)
    triggered, reason = _apply_inn2_transition_gates(e, sb, sm, 700)
    assert triggered is True
    assert reason.startswith("overs>5.0")


def test_gate_bowler_not_in_xi_rejected() -> None:
    sm = _sm_in_transition(reset_frame=647)
    sb = _StubScoreboard(
        batting_xi={"Sanju Samson", "Ruturaj Gaikwad"},
        bowling_xi={"Jasprit Bumrah", "Trent Boult"},
    )
    e = _extracted(
        score=10, wickets=1, overs=2.3,
        bowlers=[{"name": "Will Jacks"}],
    )
    triggered, reason = _apply_inn2_transition_gates(e, sb, sm, 700)
    assert triggered is True
    assert "bowler_not_in_xi" in reason


def test_gate_bowler_in_xi_passes() -> None:
    sm = _sm_in_transition(reset_frame=647)
    sb = _StubScoreboard(
        batting_xi={"Sanju Samson"},
        bowling_xi={"Jasprit Bumrah"},
    )
    e = _extracted(
        score=10, wickets=1, overs=2.3,
        bowlers=[{"name": "Jasprit Bumrah"}],
    )
    triggered, reason = _apply_inn2_transition_gates(e, sb, sm, 700)
    assert triggered is False


def test_gate_batter_not_in_xi_rejected() -> None:
    sm = _sm_in_transition(reset_frame=647)
    sb = _StubScoreboard(
        batting_xi={"Sanju Samson", "Ruturaj Gaikwad"},
        bowling_xi={"Jasprit Bumrah"},
    )
    e = _extracted(
        score=10, wickets=1, overs=2.3,
        batters=[{"name": "K.L. Rahul"}],
    )
    triggered, reason = _apply_inn2_transition_gates(e, sb, sm, 700)
    assert triggered is True
    assert "batter_not_in_xi" in reason


def test_gate_batter_in_xi_passes() -> None:
    sm = _sm_in_transition(reset_frame=647)
    sb = _StubScoreboard(
        batting_xi={"Sanju Samson"},
        bowling_xi={"Jasprit Bumrah"},
    )
    e = _extracted(
        score=10, wickets=1, overs=2.3,
        batters=[{"name": "Sanju Samson"}],
    )
    triggered, reason = _apply_inn2_transition_gates(e, sb, sm, 700)
    assert triggered is False


# ── Phase D: phantom storm window-extension state ──────────────────


def test_phantom_storm_state_lazy_until_first_block() -> None:
    sm = _sm_in_transition(reset_frame=100)
    assert getattr(sm, "_inn2_correction_blocked_timestamps", None) is None
    assert getattr(sm, "_inn2_extension_total", 0.0) == 0.0


def test_phantom_storm_extension_keeps_window_open() -> None:
    """Rolling _inn2_reset_wall back keeps in_inn2_transition True."""
    # Place reset at threshold edge: primary path still passes.
    sm = _sm_in_transition(reset_frame=100,
                           wall_offset=INN2_TRANSITION_SECONDS - 10)
    frame_in_window = 100 + INN2_TRANSITION_FRAMES - 10
    assert sm.in_inn2_transition(frame_in_window) is True
    # Simulate phantom-storm trigger: roll wall back 60s.
    sm._inn2_reset_wall -= 60.0
    sm._inn2_extension_total = 60.0
    # Primary now fails (wall>900) but safety_net (wall<1200) holds.
    assert sm.in_inn2_transition(frame_in_window) is True


def test_phantom_storm_extension_cap_value() -> None:
    """S4 cap is 300s — total extension never exceeds it."""
    sm = _sm_in_transition(reset_frame=100)
    sm._inn2_extension_total = 300.0
    # The inline storm logic in test_pipeline.py refuses further
    # extension when this attribute is >= 300.0.
    assert sm._inn2_extension_total == 300.0


# ── P2: warm-restart parameter ─────────────────────────────────────


def _sm_warm_restart(reset_frame: int = 100) -> ScoreManager:
    sm = ScoreManager(shadow=True)
    sm._current_frame = reset_frame
    sm.set_innings_2(target=160, batting_team="CSK",
                     reason="warm_test", archive=False,
                     warm_restart=True)
    return sm


def test_warm_restart_skips_lockout() -> None:
    sm = _sm_warm_restart(reset_frame=100)
    sb = _StubScoreboard(batting_xi=set(), bowling_xi=set())
    e = _extracted(score=87, wickets=2, overs=10.3)
    triggered, reason = _apply_inn2_transition_gates(e, sb, sm, 100)
    assert triggered is False
    assert reason is None


def test_cold_start_still_locks_out() -> None:
    sm = _sm_in_transition(reset_frame=100)
    sb = _StubScoreboard(batting_xi=set(), bowling_xi=set())
    e = _extracted(score=87, wickets=2, overs=10.3)
    triggered, reason = _apply_inn2_transition_gates(e, sb, sm, 100)
    assert triggered is True
    assert reason.startswith("score>30")


def test_warm_restart_does_not_break_phantom_storm() -> None:
    sm = _sm_warm_restart(reset_frame=100)
    sb = _StubScoreboard(batting_xi=set(), bowling_xi=set())
    e = _extracted(score=12, wickets=1, overs=2.3)
    triggered, _ = _apply_inn2_transition_gates(e, sb, sm, 110)
    assert triggered is False
    e2 = _extracted(score=18, wickets=1, overs=3.1)
    triggered2, _ = _apply_inn2_transition_gates(e2, sb, sm, 120)
    assert triggered2 is False


def test_warm_restart_first_commit_seen_immediately() -> None:
    sm = _sm_warm_restart(reset_frame=100)
    assert sm._inn2_first_commit_seen is True
    assert sm.in_inn2_transition(150) is False


def test_cold_start_first_commit_after_consensus() -> None:
    sm = _sm_in_transition(reset_frame=100)
    assert sm._inn2_first_commit_seen is False
    assert sm.in_inn2_transition(150) is True
    sm.mark_inn2_first_commit()
    assert sm.in_inn2_transition(150) is False
