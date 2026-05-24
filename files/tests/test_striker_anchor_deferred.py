"""WS-P P1 QA+QE — _accept_initial deferred-anchor + snapshotter None-passthrough mirror.

Persistent gate-6 verification for the WS-P P1 patch shipped on
top of step-1 memo (`52754c7`). Four contract cases cover the
QA+QE composite root WS-O.b step-3 (`c275807`) confirmed as SPLIT
from the WARM-mode score cascade:

- P-1: Production-side `_accept_initial` with broadcast_striker=None
  at cold-start → defers anchor + STRIKER-ANCHOR-DEFERRED-NO-ASTERISK
  fires + no striker pointer committed (self.striker stays None).
- P-2: Production-side `_accept_initial` with broadcast_striker set
  (e.g. "Nissanka") at cold-start → F1 algorithm at :3498-3520
  matches and anchors Nissanka=striker correctly (legitimate signal
  path preserved; deferred-anchor only fires in the else branch).
- P-3: Helper-side `extracted_to_frame_input` passes None for
  broadcast_striker when neither bat has Scout's `striker` flag
  (mirrors production semantics; replaces the legacy bat1.name
  default that caused the WS-P cascade).
- P-4: Helper-side passes broadcast_striker correctly when bat1 has
  Scout's `striker` flag (legitimate asterisk-detected signal
  preserved).

Wired into pre-commit Layer 1.5 via test_sm_derivation_ledger.main()
after the test_warm_mode_magnitude_gate gate (WS-O.b O.b1).
"""
from __future__ import annotations

import sys
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FILES_DIR))
sys.path.insert(0, str(FILES_DIR / "tests"))

from eyes.scoreboard import Scoreboard  # noqa: E402
from score_manager import (  # noqa: E402
    FrameInput,
    ScoreManager,
)
from test_pipeline_captured_replay import (  # noqa: E402
    extracted_to_frame_input,
)


def _make_sm() -> tuple[ScoreManager, Scoreboard]:
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="DC",
        bowling_team="KKR",
        batting_squad=["Pathum Nissanka", "KL Rahul"]
                       + [f"P{i}" for i in range(9)],
        bowling_squad=["Anukul Roy", "Vaibhav Arora"]
                       + [f"B{i}" for i in range(9)],
        batting_xi=["Pathum Nissanka", "KL Rahul"]
                    + [f"P{i}" for i in range(9)],
        bowling_xi=["Anukul Roy", "Vaibhav Arora"]
                    + [f"B{i}" for i in range(9)],
    )
    sm = ScoreManager(shadow=False)
    sm.scoreboard = sb
    return sm, sb


def _make_card(*, broadcast_striker, bat1_name="Pathum Nissanka",
               bat2_name="KL Rahul"):
    return {
        "score": 0,
        "wickets": 0,
        "overs": 0.0,
        "bat1_name": bat1_name,
        "bat1_runs": 0,
        "bat1_balls": 0,
        "bat2_name": bat2_name,
        "bat2_runs": 0,
        "bat2_balls": 0,
        "bowler_name": "Anukul Roy",
        "broadcast_striker": broadcast_striker,
        "this_over": [],
        "completed_over": [],
    }


def _make_frame(frame_id: int = 1) -> FrameInput:
    return FrameInput(
        frame_id=str(frame_id),
        timestamp=float(frame_id),
        ext_score=0,
        ext_wickets=0,
        ext_overs=0.0,
        scout_text="DC 0-0 (0.0)",
    )


def _case_p1_squad_convention_corrects_scout_swap() -> tuple[bool, str]:
    sm, _ = _make_sm()
    # Scout MISORDERS rows: bat1=Rahul (off-strike per cricket
    # truth), bat2=Nissanka (BATTING_SQUAD[0], the opener-on-
    # strike facing ball 1). Pre-WS-P the legacy bat1-default
    # anchored Rahul as striker (the ~50-field swap cohort).
    # Post-WS-P the squad-convention catches bat2==squad[0]
    # and anchors bat2=Nissanka=striker.
    card = _make_card(broadcast_striker=None,
                      bat1_name="KL Rahul", bat2_name="Pathum Nissanka")
    frame = _make_frame(frame_id=1)
    sm._accept_initial(card, frame)
    ok = (
        sm.striker == "Pathum Nissanka"
        and sm.non == "KL Rahul")
    detail = (
        f"sm.striker={sm.striker!r} sm.non={sm.non!r} "
        f"(expected: Nissanka=striker via squad convention, "
        f"Scout-bat1=Rahul demoted to non)")
    return ok, detail


def _case_p2_anchors_correctly_when_broadcast_striker_set() -> tuple[bool, str]:
    sm, _ = _make_sm()
    card = _make_card(broadcast_striker="Nissanka")
    frame = _make_frame(frame_id=1)
    sm._accept_initial(card, frame)
    ok = (
        sm.striker == "Pathum Nissanka"
        and sm.non == "KL Rahul")
    detail = (
        f"sm.striker={sm.striker!r} sm.non={sm.non!r} "
        f"(expected: Nissanka=striker, Rahul=non)")
    return ok, detail


def _case_p3_helper_passes_none_when_neither_has_striker_flag() -> tuple[bool, str]:
    extracted = {
        "score": 0,
        "wickets": 0,
        "overs": "0.0",
        "match_overs": "0.0",
        "bowler": {"name": "Anukul Roy"},
        "batters": [
            {"name": "Pathum Nissanka", "runs": 0, "balls": 0,
             "striker": False},
            {"name": "KL Rahul", "runs": 0, "balls": 0,
             "striker": False},
        ],
    }
    fi = extracted_to_frame_input(frame_id=1, ts=1.0, extracted=extracted)
    ok = fi.broadcast_striker is None
    detail = (
        f"fi.broadcast_striker={fi.broadcast_striker!r} "
        f"(expected: None — mirrors production semantics)")
    return ok, detail


def _case_p4_helper_passes_bat1_when_bat1_has_striker_flag() -> tuple[bool, str]:
    extracted = {
        "score": 4,
        "wickets": 0,
        "overs": "0.2",
        "match_overs": "0.2",
        "bowler": {"name": "Anukul Roy"},
        "batters": [
            {"name": "Pathum Nissanka", "runs": 4, "balls": 2,
             "striker": True},
            {"name": "KL Rahul", "runs": 0, "balls": 0,
             "striker": False},
        ],
    }
    fi = extracted_to_frame_input(frame_id=2, ts=2.0, extracted=extracted)
    ok = fi.broadcast_striker == "Pathum Nissanka"
    detail = (
        f"fi.broadcast_striker={fi.broadcast_striker!r} "
        f"(expected: 'Pathum Nissanka' — bat1 has striker flag)")
    return ok, detail


CASES: list[tuple[str, callable]] = [
    ("P-1 squad convention corrects Scout bat1/bat2 swap when broadcast_striker=None",
     _case_p1_squad_convention_corrects_scout_swap),
    ("P-2 production _accept_initial anchors correctly when broadcast_striker set",
     _case_p2_anchors_correctly_when_broadcast_striker_set),
    ("P-3 helper passes None when neither bat has Scout striker flag",
     _case_p3_helper_passes_none_when_neither_has_striker_flag),
    ("P-4 helper passes bat1.name when bat1 has Scout striker flag",
     _case_p4_helper_passes_bat1_when_bat1_has_striker_flag),
]


def run_all() -> int:
    """Run all WS-P P1 QA+QE cases. Return 0 on PASS."""
    print(
        f"\n=== STRIKER-ANCHOR-DEFERRED + HELPER-NONE-PASSTHROUGH gate "
        f"(WS-P P1) — {len(CASES)} cases ===")
    fails = 0
    for name, fn in CASES:
        ok, detail = fn()
        verdict = "PASS" if ok else "FAIL"
        print(f"  {verdict} {name}: {detail}")
        if not ok:
            fails += 1
    if fails:
        print(
            f"\nFAIL — {fails}/{len(CASES)} WS-P P1 QA+QE cases regressed")
        return 1
    print(f"\nPASS — all {len(CASES)} WS-P P1 QA+QE cases hold")
    return 0


def test_striker_anchor_deferred_holds() -> None:
    """pytest entry — WS-P P1 QA+QE must hold on all 4 cases."""
    rc = run_all()
    assert rc == 0, (
        "WS-P P1 QA+QE regressed; see stdout for the first failing case.")


if __name__ == "__main__":
    sys.exit(run_all())
