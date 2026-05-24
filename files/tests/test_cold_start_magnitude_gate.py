"""WS-O O1 OA — cold-start magnitude gate + force_reset_score regression-correction primitive.

Persistent gate-6 verification for the WS-O O1 patch shipped on top
of WS-O step-1 memo (`c81c100`). Four contract cases cover the
cold-start overread + Scoreboard regression-rejection composite:

- O-1 cold-start overread rejected: synthetic Scout misread of
  score=49 at overs=0.0 → magnitude gate at
  `score_manager.py:_handle_cold_start` rejects + emits
  COLD-START-OVERREAD-REJECTED trace; `cold_candidate` stays None;
  `cold_frames` decremented (mirrors the existing skeleton-strip /
  pre-match-cue reject pattern at :2738-2747).

- O-2 cold-start legitimate high-score start: synthetic mid-innings
  resume with score=49 at overs=4.0 (~12 RPO, within plausibility
  cap) → gate accepts; `cold_candidate` seeded.

- O-3 negative-token regression-signal consumption: stuck-at-49
  baseline + PendingBall(runs_delta=-27) → drain loop invokes
  `Scoreboard.force_reset_score(22, ...)` → SCORE-FORCE-RESET trace
  fires; SM.score walked back to 22; sb._inn["score"] walked back
  to 22; token replaced with "." rather than the legacy "-27".

- O-4 standard regression-rejection unchanged: a normal
  `sb.set("score", 15, frame)` call against a current score of 22
  still rejects (preserves the existing regression-rejection
  semantics at `scoreboard.py:1224`); only force_reset_score
  bypasses.

Wired into pre-commit Layer 1.5 via test_sm_derivation_ledger.main()
after the test_snapshotter_full_pipeline_integration gate.
"""
from __future__ import annotations

import sys
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FILES_DIR))

from eyes.scoreboard import Scoreboard  # noqa: E402
from score_manager import (  # noqa: E402
    FrameInput,
    PendingBall,
    ScoreManager,
)


def _make_sm() -> tuple[ScoreManager, Scoreboard]:
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="DC",
        bowling_team="KKR",
        batting_squad=["Nissanka", "Rahul", "Stubbs", "Porel", "Dhull",
                        "Axar", "Stoinis", "Ashutosh", "Mukesh", "Roy",
                        "Tyagi"],
        bowling_squad=["Roy", "Arora", "Narine", "Tyagi", "Russell",
                        "Varun", "Starc", "Ramandeep", "Salt", "Iyer",
                        "Rinku"],
        batting_xi=["Nissanka", "Rahul", "Stubbs", "Porel", "Dhull",
                     "Axar", "Stoinis", "Ashutosh", "Mukesh", "Roy",
                     "Tyagi"],
        bowling_xi=["Roy", "Arora", "Narine", "Tyagi", "Russell",
                     "Varun", "Starc", "Ramandeep", "Salt", "Iyer",
                     "Rinku"],
    )
    sm = ScoreManager(shadow=False)
    sm.scoreboard = sb
    return sm, sb


def _make_frame(frame_id: int = 1, scout_text: str = "DC 49-0 (0.0)") -> FrameInput:
    return FrameInput(
        frame_id=str(frame_id),
        timestamp=float(frame_id),
        ext_score=None,
        ext_wickets=None,
        ext_overs=None,
        scout_text=scout_text,
    )


def _case_o1_cold_start_overread_rejected() -> tuple[bool, str]:
    sm, _ = _make_sm()
    frame = _make_frame(frame_id=1, scout_text="DC 49-0 (0.0)")
    card = {"score": 49, "wickets": 0, "overs": 0.0,
            "this_over": [], "completed_over": []}
    cold_frames_before = sm.cold_frames
    sm._handle_cold_start(card, frame)
    # _handle_cold_start internally does cold_frames += 1 at the top;
    # the magnitude gate does cold_frames -= 1 on reject — net delta 0.
    ok = (
        sm.cold_candidate is None
        and sm.mode == "COLD_START"
        and sm.cold_frames == cold_frames_before)
    detail = (
        f"cold_candidate={sm.cold_candidate} "
        f"mode={sm.mode} cold_frames_delta="
        f"{sm.cold_frames - cold_frames_before}")
    return ok, detail


def _case_o2_legitimate_high_score_accepted() -> tuple[bool, str]:
    sm, _ = _make_sm()
    frame = _make_frame(frame_id=1, scout_text="DC 49-1 (4.0)")
    card = {"score": 49, "wickets": 1, "overs": 4.0,
            "this_over": [], "completed_over": []}
    sm._handle_cold_start(card, frame)
    ok = (
        sm.cold_candidate is not None
        and sm.cold_candidate.get("score") == 49
        and sm.cold_candidate.get("overs") == 4.0)
    detail = f"cold_candidate={sm.cold_candidate}"
    return ok, detail


def _case_o3_negative_token_force_reset() -> tuple[bool, str]:
    sm, sb = _make_sm()
    sm.score = 49
    sb._inn["score"] = 49
    try:
        sb._tracker.confirmed["score"] = 49
    except (AttributeError, KeyError, TypeError):
        pass
    entry = PendingBall(
        frame_id=100,
        runs_delta=-27,
        balls_delta=1,
        wickets_delta=0,
        bowler="Roy",
        striker="Nissanka",
    )
    sm._pending_ball_queue.append(entry)
    drained = sm._drain_pending_queue("test_o3_negative_token")
    ok = (
        drained == 1
        and sm.score == 22
        and sb._inn.get("score") == 22
        and entry.committed)
    detail = (
        f"drained={drained} sm.score={sm.score} "
        f"sb_score={sb._inn.get('score')} committed={entry.committed}")
    return ok, detail


def _case_o4_standard_regression_rejection_unchanged() -> tuple[bool, str]:
    _, sb = _make_sm()
    sb._inn["score"] = 22
    try:
        sb._tracker.confirmed["score"] = 22
    except (AttributeError, KeyError, TypeError):
        pass
    accepted = sb.set("score", 15, frame=10)
    ok = (
        accepted is False
        and sb._inn.get("score") == 22)
    detail = (
        f"accepted={accepted} sb_score={sb._inn.get('score')} "
        f"(expected: rejected; score stays at 22)")
    return ok, detail


CASES: list[tuple[str, callable]] = [
    ("O-1 cold-start overread rejected (score=49 at overs=0.0)",
     _case_o1_cold_start_overread_rejected),
    ("O-2 cold-start legitimate high-score accepted (score=49 at overs=4.0)",
     _case_o2_legitimate_high_score_accepted),
    ("O-3 PendingBall negative-runs-delta drives force_reset_score",
     _case_o3_negative_token_force_reset),
    ("O-4 standard regression-rejection unchanged (sb.set rejects v<cur)",
     _case_o4_standard_regression_rejection_unchanged),
]


def run_all() -> int:
    """Run all WS-O O1 cold-start magnitude / regression-correction
    cases. Return 0 on PASS."""
    print(
        f"\n=== COLD-START-MAGNITUDE-GATE + FORCE-RESET-SCORE gate "
        f"(WS-O O1) — {len(CASES)} cases ===")
    fails = 0
    for name, fn in CASES:
        ok, detail = fn()
        verdict = "PASS" if ok else "FAIL"
        print(f"  {verdict} {name}: {detail}")
        if not ok:
            fails += 1
    if fails:
        print(
            f"\nFAIL — {fails}/{len(CASES)} WS-O O1 cold-start cases "
            f"regressed")
        return 1
    print(
        f"\nPASS — all {len(CASES)} WS-O O1 cold-start cases hold")
    return 0


def test_cold_start_magnitude_gate_holds() -> None:
    """pytest entry — WS-O O1 cold-start gate must hold on all 4 cases."""
    rc = run_all()
    assert rc == 0, (
        "WS-O O1 cold-start magnitude gate regressed; see stdout for "
        "the first failing case.")


if __name__ == "__main__":
    sys.exit(run_all())
