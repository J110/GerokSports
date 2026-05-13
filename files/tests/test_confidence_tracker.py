"""ConfidenceTracker unit tests.

Run from repo root:
    pytest files/tests/test_confidence_tracker.py -q
"""
from __future__ import annotations

import math
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from confidence_tracker import (
    ConfidenceTracker,
    STATE_FIRM,
    STATE_IMMUTABLE,
    STATE_LOCKED,
    STATE_NONE,
    STATE_PUBLISHABLE,
    STATE_TENTATIVE,
)


def _drive_to_firm(tracker: ConfidenceTracker, name: str, *,
                   weight: float = 1.0) -> int:
    """Observe `name` at `weight` until tracker reaches FIRM/LOCKED."""
    count = 0
    while tracker.state not in (STATE_FIRM, STATE_LOCKED, STATE_IMMUTABLE):
        tracker.observe(name, weight=weight)
        count += 1
        if count > 1000:
            raise RuntimeError("loop guard")
    return count


# ── LOCKED (auto-lock on FIRM) ──────────────────────────────────────


def test_auto_lock_default_off() -> None:
    clk = FakeClock()
    bt = ConfidenceTracker("batting_team", clock=clk)
    _drive_to_firm(bt, "MI")
    assert bt.state == STATE_FIRM
    bt.observe("RCB", weight=100.0)
    assert bt.leader == "RCB", "default tracker should flip on big evidence"


def test_auto_lock_holds_leader_after_firm() -> None:
    clk = FakeClock()
    bt = ConfidenceTracker(
        "batting_team", firm=3.0, auto_lock_on_firm=True, clock=clk)
    bt.observe("MI", weight=1.0)
    bt.observe("MI", weight=1.0)
    bt.observe("MI", weight=1.0)
    assert bt.state == STATE_LOCKED
    assert bt.leader == "MI"
    bt.observe("RCB", weight=100.0)
    assert bt.leader == "MI", "LOCKED tracker must not flip"
    assert bt.state == STATE_LOCKED


def test_locked_state_records_evidence_for_telemetry() -> None:
    clk = FakeClock()
    bt = ConfidenceTracker(
        "batting_team", firm=3.0, auto_lock_on_firm=True, clock=clk)
    _drive_to_firm(bt, "MI")
    r = bt.observe("RCB", weight=2.0)
    assert "RCB" in r.scores, "LOCKED state should still record evidence"
    assert r.leader == "MI", "LOCKED state should not move the leader"
    assert r.state == STATE_LOCKED


def test_unlock_releases_for_innings_2() -> None:
    clk = FakeClock()
    bt = ConfidenceTracker(
        "batting_team", firm=3.0, auto_lock_on_firm=True, clock=clk)
    _drive_to_firm(bt, "MI")
    assert bt.state == STATE_LOCKED
    bt.unlock()
    bt.reset()
    assert bt.state == STATE_NONE
    bt.observe("RCB", weight=1.0)
    assert bt.leader == "RCB"


def test_locked_below_firm_threshold_is_unreachable() -> None:
    """Threshold raise to 10.0 means 2 weight-1 observations cannot
    reach LOCKED — recap-frame poisoning protection."""
    clk = FakeClock()
    bt = ConfidenceTracker(
        "batting_team", firm=10.0, auto_lock_on_firm=True, clock=clk)
    bt.observe("RCB", weight=1.0)
    bt.observe("RCB", weight=1.0)
    assert bt.state != STATE_LOCKED


def test_immutable_takes_precedence_over_locked() -> None:
    clk = FakeClock()
    bt = ConfidenceTracker(
        "batting_team", firm=3.0, auto_lock_on_firm=True, clock=clk)
    _drive_to_firm(bt, "MI")
    assert bt.state == STATE_LOCKED
    bt.set_immutable("RCB")
    assert bt.state == STATE_IMMUTABLE
    assert bt.leader == "RCB"


def test_unlock_and_reset_clears_everything() -> None:
    clk = FakeClock()
    bt = ConfidenceTracker(
        "striker", firm=3.0, auto_lock_on_firm=True, clock=clk)
    _drive_to_firm(bt, "NAMAN")
    assert bt.state == STATE_LOCKED
    bt.unlock_and_reset()
    assert bt.state == STATE_NONE
    assert bt.leader is None
    bt.observe("SURYAKUMAR", weight=1.0)
    assert bt.leader == "SURYAKUMAR"


def test_swap_with_exchanges_locked_leaders() -> None:
    """Striker rotation: both trackers stay LOCKED, leaders swap."""
    clk = FakeClock()
    striker = ConfidenceTracker(
        "striker", firm=3.0, auto_lock_on_firm=True, clock=clk)
    non = ConfidenceTracker(
        "non_striker", firm=3.0, auto_lock_on_firm=True, clock=clk)
    _drive_to_firm(striker, "NAMAN")
    _drive_to_firm(non, "TILAK")
    assert striker.leader == "NAMAN" and striker.state == STATE_LOCKED
    assert non.leader == "TILAK" and non.state == STATE_LOCKED
    striker.swap_with(non)
    assert striker.leader == "TILAK" and striker.state == STATE_LOCKED
    assert non.leader == "NAMAN" and non.state == STATE_LOCKED


def test_swap_with_preserves_scores_under_new_slot() -> None:
    """After swap, NAMAN's accumulated evidence is in non, not striker.
    Subsequent same-name observations continue to weigh the right slot."""
    clk = FakeClock()
    striker = ConfidenceTracker(
        "striker", firm=3.0, auto_lock_on_firm=True, clock=clk)
    non = ConfidenceTracker(
        "non_striker", firm=3.0, auto_lock_on_firm=True, clock=clk)
    _drive_to_firm(striker, "NAMAN")
    _drive_to_firm(non, "TILAK")
    striker.swap_with(non)
    # NAMAN's evidence dict should now live in `non`.
    assert "NAMAN" in non.snapshot()["scores"]
    assert "TILAK" in striker.snapshot()["scores"]


# ── IMMUTABLE (innings-2 / operator commit) ─────────────────────────


def test_immutable_blocks_observe_even_at_high_weight() -> None:
    clk = FakeClock()
    bt = ConfidenceTracker(
        "batting_team", firm=3.0, auto_lock_on_firm=True, clock=clk)
    bt.set_immutable("MI")
    assert bt.state == STATE_IMMUTABLE
    assert bt.leader == "MI"
    bt.observe("RCB", weight=10000.0)
    assert bt.leader == "MI"
    assert bt.state == STATE_IMMUTABLE


def test_immutable_observe_of_same_value_still_immutable() -> None:
    clk = FakeClock()
    bt = ConfidenceTracker(
        "batting_team", firm=3.0, auto_lock_on_firm=True, clock=clk)
    bt.set_immutable("MI")
    bt.observe("MI", weight=1.0)
    assert bt.leader == "MI"
    assert bt.state == STATE_IMMUTABLE


def test_locked_unlock_and_reset_returns_to_none() -> None:
    clk = FakeClock()
    bt = ConfidenceTracker(
        "striker", firm=3.0, auto_lock_on_firm=True, clock=clk)
    _drive_to_firm(bt, "NAMAN")
    assert bt.state == STATE_LOCKED
    did_clear = bt.unlock_and_reset()
    assert did_clear is True
    assert bt.state == STATE_NONE
    assert bt.leader is None
    assert bt.snapshot()["scores"] == {}


def test_immutable_unlock_and_reset_is_noop() -> None:
    """innings-3 isn't a thing — IMMUTABLE must not be cleared."""
    clk = FakeClock()
    bt = ConfidenceTracker(
        "batting_team", firm=3.0, auto_lock_on_firm=True, clock=clk)
    bt.set_immutable("MI")
    assert bt.state == STATE_IMMUTABLE
    did_clear = bt.unlock_and_reset()
    assert did_clear is False
    assert bt.state == STATE_IMMUTABLE
    assert bt.leader == "MI"


def test_set_immutable_on_locked_tracker_takes_precedence() -> None:
    """innings-2 path: tracker is LOCKED on innings-1 team, then
    set_immutable seeds the new chasing team."""
    clk = FakeClock()
    bt = ConfidenceTracker(
        "batting_team", firm=3.0, auto_lock_on_firm=True, clock=clk)
    _drive_to_firm(bt, "MI")
    assert bt.state == STATE_LOCKED and bt.leader == "MI"
    bt.set_immutable("RCB")
    assert bt.state == STATE_IMMUTABLE
    assert bt.leader == "RCB"
    # Further observations of either side cannot move the leader.
    bt.observe("MI", weight=10.0)
    assert bt.leader == "RCB"


class FakeClock:
    """Manual wall-clock for deterministic decay tests."""

    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


# ── state machine ───────────────────────────────────────────────────


def test_initial_state_is_none() -> None:
    bt = ConfidenceTracker("batting_team")
    assert bt.leader is None
    assert bt.state == STATE_NONE
    assert bt.leader_score == 0.0


def test_first_observation_is_tentative() -> None:
    clk = FakeClock()
    bt = ConfidenceTracker("batting_team", clock=clk)
    r = bt.observe("MI", weight=1.0)
    assert r.leader == "MI"
    assert r.state == STATE_TENTATIVE
    assert math.isclose(r.leader_score, 1.0)
    assert r.flipped is False


def test_reaches_publishable_at_publish_threshold() -> None:
    clk = FakeClock()
    bt = ConfidenceTracker("batting_team", clock=clk, publish=2.0)
    bt.observe("MI", weight=1.0)
    r = bt.observe("MI", weight=1.0)
    assert r.state == STATE_PUBLISHABLE
    assert math.isclose(r.leader_score, 2.0)


def test_reaches_firm_at_firm_threshold() -> None:
    clk = FakeClock()
    bt = ConfidenceTracker(
        "batting_team", clock=clk, publish=2.0, firm=5.0)
    for _ in range(5):
        bt.observe("MI", weight=1.0)
    assert bt.state == STATE_FIRM
    assert math.isclose(bt.leader_score, 5.0)


# ── flip logic ──────────────────────────────────────────────────────


def test_flip_requires_margin_over_leader() -> None:
    """The PBKS-DC bug: contender at equal score must NOT flip."""
    clk = FakeClock()
    bt = ConfidenceTracker(
        "batting_team", clock=clk, flip_margin=1.0, half_life_s=1e9)
    bt.observe("RCB", weight=2.0)
    r = bt.observe("MI", weight=2.0)
    # Equal scores → RCB stays leader.
    assert r.leader == "RCB"
    assert r.flipped is False


def test_flip_fires_when_contender_beats_margin() -> None:
    clk = FakeClock()
    bt = ConfidenceTracker(
        "batting_team", clock=clk, flip_margin=1.0, half_life_s=1e9)
    bt.observe("RCB", weight=2.0)
    bt.observe("MI", weight=2.0)
    r = bt.observe("MI", weight=1.5)
    # MI=3.5 ≥ RCB=2.0 + 1.0 → flip.
    assert r.leader == "MI"
    assert r.flipped is True
    assert r.old_leader == "RCB"


def test_sustained_contradictory_evidence_flips_lock() -> None:
    """Tonight's replay scenario: pre-match graphic locks RCB on
    3 frames, then MI strip arrives for 5 consecutive frames."""
    clk = FakeClock()
    bt = ConfidenceTracker(
        "batting_team", clock=clk, flip_margin=1.0,
        publish=2.0, half_life_s=1e9)
    # 3 RCB frames from pre-match graphic
    for _ in range(3):
        bt.observe("RCB", weight=1.0)
        clk.advance(0.5)
    assert bt.leader == "RCB"
    assert bt.state == STATE_PUBLISHABLE
    # 5 MI frames from live strip
    flipped_at = -1
    for i in range(5):
        r = bt.observe("MI", weight=1.0)
        clk.advance(0.5)
        if r.flipped and flipped_at < 0:
            flipped_at = i
    assert bt.leader == "MI"
    # Flipped on the 4th MI obs (MI=4.0 ≥ RCB=3.0 + 1.0).
    assert flipped_at == 3


# ── decay ───────────────────────────────────────────────────────────


def test_decay_halves_score_at_half_life() -> None:
    clk = FakeClock()
    bt = ConfidenceTracker(
        "batting_team", clock=clk, half_life_s=60.0)
    bt.observe("MI", weight=4.0)
    snap0 = bt.snapshot()
    assert math.isclose(snap0["leader_score"], 4.0)
    clk.advance(60.0)
    snap1 = bt.snapshot()
    assert math.isclose(snap1["leader_score"], 2.0, rel_tol=1e-9)
    clk.advance(60.0)
    snap2 = bt.snapshot()
    assert math.isclose(snap2["leader_score"], 1.0, rel_tol=1e-9)


def test_decay_lets_contender_overtake_after_long_silence() -> None:
    clk = FakeClock()
    bt = ConfidenceTracker(
        "batting_team", clock=clk, flip_margin=1.0,
        half_life_s=60.0)
    # RCB locks in early
    for _ in range(5):
        bt.observe("RCB", weight=1.0)
    assert bt.leader == "RCB"
    # 2 minutes pass with no RCB evidence
    clk.advance(120.0)
    # RCB decays from 5.0 → 1.25
    # Single MI observation at weight 1.0: MI=1.0 vs RCB=1.25 → no flip
    r1 = bt.observe("MI", weight=1.0)
    assert r1.leader == "RCB"
    # Second MI observation: MI=2.0 vs RCB=1.25 → still < 1.25+1.0 → no flip
    r2 = bt.observe("MI", weight=1.0)
    assert r2.leader == "RCB"
    # Third MI observation: MI=3.0 ≥ RCB=1.25 + 1.0 = 2.25 → flip
    r3 = bt.observe("MI", weight=1.0)
    assert r3.leader == "MI"
    assert r3.flipped is True


def test_state_drops_back_from_firm_on_decay() -> None:
    clk = FakeClock()
    bt = ConfidenceTracker(
        "batting_team", clock=clk, publish=2.0, firm=5.0,
        half_life_s=60.0)
    for _ in range(5):
        bt.observe("MI", weight=1.0)
    assert bt.state == STATE_FIRM
    clk.advance(60.0)
    assert bt.snapshot()["state"] == STATE_PUBLISHABLE  # 2.5
    clk.advance(60.0)
    assert bt.snapshot()["state"] == STATE_TENTATIVE  # 1.25


# ── immutability ────────────────────────────────────────────────────


def test_immutable_forbids_flips() -> None:
    clk = FakeClock()
    bt = ConfidenceTracker(
        "batting_team", clock=clk, flip_margin=1.0,
        half_life_s=1e9)
    bt.observe("MI", weight=5.0)
    bt.set_immutable()
    r = bt.observe("RCB", weight=99.0)
    assert r.leader == "MI"
    assert r.flipped is False
    assert bt.state == STATE_IMMUTABLE


def test_immutable_with_explicit_candidate_overrides_leader() -> None:
    clk = FakeClock()
    bt = ConfidenceTracker("batting_team", clock=clk)
    bt.observe("RCB", weight=2.0)
    bt.set_immutable("MI")
    assert bt.leader == "MI"
    assert bt.state == STATE_IMMUTABLE


def test_reset_clears_state_and_unlocks() -> None:
    clk = FakeClock()
    bt = ConfidenceTracker("batting_team", clock=clk)
    bt.observe("MI", weight=5.0)
    bt.set_immutable()
    bt.reset()
    assert bt.leader is None
    assert bt.state == STATE_NONE
    r = bt.observe("RCB", weight=1.0)
    assert r.leader == "RCB"


# ── weights ─────────────────────────────────────────────────────────


def test_strong_evidence_can_flip_in_one_observation() -> None:
    clk = FakeClock()
    bt = ConfidenceTracker(
        "batting_team", clock=clk, flip_margin=1.0,
        half_life_s=1e9)
    bt.observe("RCB", weight=1.0)
    # Strong evidence (e.g. graphic_team confirmation) at weight 3.0
    r = bt.observe("MI", weight=3.0)
    assert r.leader == "MI"
    assert r.flipped is True


def test_observe_result_carries_telemetry_fields() -> None:
    clk = FakeClock()
    bt = ConfidenceTracker("batting_team", clock=clk)
    r = bt.observe("MI", weight=1.5)
    assert r.candidate == "MI"
    assert r.weight == 1.5
    assert r.leader == "MI"
    assert r.old_leader is None
    assert r.scores == {"MI": 1.5}
    assert r.state == STATE_TENTATIVE


# ── edge cases ──────────────────────────────────────────────────────


def test_zero_weight_observation_does_not_change_leader() -> None:
    clk = FakeClock()
    bt = ConfidenceTracker("batting_team", clock=clk)
    bt.observe("MI", weight=1.0)
    r = bt.observe("RCB", weight=0.0)
    assert r.leader == "MI"
    assert r.flipped is False
    # RCB entry exists with 0 score
    assert r.scores.get("RCB") == 0.0


def test_snapshot_does_not_double_decay() -> None:
    clk = FakeClock()
    bt = ConfidenceTracker(
        "batting_team", clock=clk, half_life_s=60.0)
    bt.observe("MI", weight=4.0)
    clk.advance(60.0)
    s1 = bt.snapshot()
    s2 = bt.snapshot()  # immediately after, no time advance
    assert math.isclose(s1["leader_score"], s2["leader_score"])


if __name__ == "__main__":  # pragma: no cover
    import sys as _sys
    import pytest
    _sys.exit(pytest.main([__file__, "-v"]))
