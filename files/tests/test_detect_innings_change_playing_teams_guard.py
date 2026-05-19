"""Focused unit test for the playing-teams sanity check in
ScoreManager._detect_innings_change.

Surfaced by the diagnostic on watch_20260519_090844.jsonl frame 8:
Scout VLM misread "LSG" as broadcast_team in a DC vs KKR match,
score_manager._detect_innings_change accepted it without checking
against the playing teams, three consecutive misreads committed a
spurious team-change → _reset_for_innings_2 → mode-revert latency
+ NO-SCOREBOARD credit-skip cascade (latter previously patched at
6881476).

Run:
    python files/tests/test_detect_innings_change_playing_teams_guard.py
    pytest files/tests/test_detect_innings_change_playing_teams_guard.py -v
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FILES_DIR))

from score_manager import ScoreManager, FrameInput  # noqa: E402
from eyes.scoreboard import Scoreboard  # noqa: E402


def _build_sm_for_dc_kkr() -> tuple[ScoreManager, Scoreboard]:
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="DC", bowling_team="KKR",
        batting_squad=["Pathum Nissanka", "KL Rahul"],
        bowling_squad=["Anukul Roy"],
        batting_xi=["Pathum Nissanka", "KL Rahul"],
        bowling_xi=["Anukul Roy"],
    )
    sm = ScoreManager(shadow=False)
    sm.scoreboard = sb
    sm.batting_team = "DC"
    sm.innings = 1
    sm.score = 5
    sm.wickets = 0
    sm.overs = 0.3
    return sm, sb


def _frame_with_team(team: str, frame_id: str) -> FrameInput:
    return FrameInput(
        frame_id=frame_id,
        timestamp=time.time(),
        ext_score=5,
        ext_wickets=0,
        ext_overs=0.3,
        broadcast_team=team,
        scout_text=f"DC 5-0 (0.3) {team} POINTS TABLE",
    )


def test_lsg_misread_rejected_in_dc_kkr_match() -> None:
    """Three consecutive frames with broadcast_team='LSG' in a DC vs
    KKR match must NOT trigger an innings change. Pre-fix: the
    team-change consensus accumulated to 3 and committed a spurious
    transition. Post-fix: the playing-teams guard rejects LSG before
    the streak accumulates."""
    sm, _sb = _build_sm_for_dc_kkr()
    card = {"score": 5, "wickets": 0, "overs": 0.3}

    for i in range(5):
        frame = _frame_with_team("LSG", f"F{i}")
        changed = sm._detect_innings_change(card, frame)
        assert changed is False, (
            f"Frame {i}: spurious innings change accepted for "
            f"broadcast_team='LSG' in DC vs KKR match")

    assert sm.innings == 1, (
        f"Expected innings=1 after 5 LSG misreads; got {sm.innings}")
    assert sm.batting_team == "DC", (
        f"Expected batting_team='DC' after 5 LSG misreads; "
        f"got {sm.batting_team!r}")


def test_legitimate_dc_to_kkr_change_still_works() -> None:
    """When DC innings ends and KKR comes in to chase, the
    broadcast_team will legitimately switch to KKR. Three consecutive
    frames must still trigger the innings-change path."""
    sm, _sb = _build_sm_for_dc_kkr()
    card = {"score": 0, "wickets": 0, "overs": 0.0}

    changed_any = False
    for i in range(sm.TEAM_CHANGE_CONSENSUS_FRAMES + 1):
        frame = _frame_with_team("KKR", f"F{i}")
        if sm._detect_innings_change(card, frame):
            changed_any = True
            break

    assert changed_any is True, (
        "Legitimate DC → KKR team change rejected by the playing-"
        "teams guard; the guard must allow opposite-team transitions.")


def test_no_playing_teams_falls_back_to_permissive() -> None:
    """If scoreboard hasn't locked teams yet (pre-cold-start), the
    guard must not block — fall back to original D7-consensus
    behavior."""
    sb = Scoreboard()
    sb.setup_innings(
        batting_team=None, bowling_team=None,
        batting_squad=["A"], bowling_squad=["X"],
        batting_xi=["A"], bowling_xi=["X"],
    )
    sm = ScoreManager(shadow=False)
    sm.scoreboard = sb
    sm.batting_team = "TEAM_A"
    sm.innings = 1
    sm.score = 5
    sm.wickets = 0
    sm.overs = 0.3
    card = {"score": 5, "wickets": 0, "overs": 0.3}

    changed_any = False
    for i in range(sm.TEAM_CHANGE_CONSENSUS_FRAMES + 1):
        frame = _frame_with_team("TEAM_B", f"F{i}")
        if sm._detect_innings_change(card, frame):
            changed_any = True
            break

    assert changed_any is True, (
        "When scoreboard has no locked teams, guard must permit "
        "team-change accumulation; got blocked.")


def _run_all() -> int:
    tests = [
        test_lsg_misread_rejected_in_dc_kkr_match,
        test_legitimate_dc_to_kkr_change_still_works,
        test_no_playing_teams_falls_back_to_permissive,
    ]
    failures = []
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            print(f"FAIL {t.__name__}: {e}")
            failures.append(t.__name__)
        except Exception as e:
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            failures.append(t.__name__)
    if failures:
        print(f"\nFAIL — {len(failures)}/{len(tests)} test(s) failed")
        return 1
    print(f"\nPASS — all {len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(_run_all())
