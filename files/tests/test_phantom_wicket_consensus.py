"""Workstream Surface E step-2 HA' — phantom-wicket consensus gate.

Persistent gate-6 regression detector for the
`BallDetector.check()` wicket-detection predicate at
`files/eyes/state/ball_detector.py:96+` — N=3 consensus + overs-advance
gate suppresses OCR-instability phantom-wicket emissions while
preserving the genuine-wicket cohort with bounded latency.

Seven cases:
  P-1 F1017 OCR oscillation analog (wickets [6, 4, 5, _, 5]) → all
      candidate readings suppressed; PHANTOM-WICKET-SUSPECT fires.
  P-2 N=3 consensus satisfied without overs-advance → SUPPRESSED
      (overs-advance gate is load-bearing against stuck-clock OCR).
  P-3 N=3 consensus + overs-advance → ADMITTED at the 3rd streak frame.
  P-4 Genuine wicket (Rahul ov 5.0 analog: wickets 0→1 + overs 4.6→5.0)
      → ADMITTED within 3-frame latency.
  P-5 Genuine wicket (Rana ov 8.0 analog: wickets 1→2 + overs 7.5→8.0)
      → ADMITTED.
  P-6 Genuine wicket (Nissanka ov 9.5 analog: wickets 2→3 + overs
      9.4→9.5) → ADMITTED.
  P-7 reset() clears both _wicket_candidate and _wicket_streak.

Cross-references WS-Surface-E step-1 memo
`workstream_surface_e_phantom_wicket_investigation.md` §5 (HA' shape)
+ §7 (gate-6 plan) + §8 (false-negative risk assessment) + §11.

Wired into pre-commit Layer 1.5 via `test_sm_derivation_ledger.main()`
after the WS-I γ-w-symbol schema-precondition gate.
"""
from __future__ import annotations

import sys
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FILES_DIR))
sys.path.insert(0, str(FILES_DIR / "eyes"))
sys.path.insert(0, str(FILES_DIR / "eyes" / "state"))

from ball_detector import BallDetector  # noqa: E402


def _sb(score: int, wickets: int, overs: str) -> dict:
    return {"score": score, "wickets": wickets, "overs": overs}


def _drive(detector: BallDetector, frames: list[dict]) -> list[dict | None]:
    """Drive detector through a frame sequence; return per-frame check() results."""
    return [detector.check(sb) for sb in frames]


def _case_p1_oscillation_suppressed() -> int:
    det = BallDetector(min_gap=0.0)
    frames = [
        _sb(89, 4, "10.4"),
        _sb(89, 6, "10.4"),
        _sb(89, 4, "10.4"),
        _sb(89, 5, "10.5"),
        _sb(90, 5, "10.5"),
    ]
    results = _drive(det, frames)
    wicket_admissions = [r for r in results if r is not None and r.get("wicket")]
    if wicket_admissions:
        print(f"FAIL P-1: expected 0 wicket-admissions on oscillation; "
              f"got {len(wicket_admissions)} — admitted={wicket_admissions}")
        return 1
    print("  PASS P-1 (F1017 oscillation analog): all candidate readings suppressed")
    return 0


def _case_p2_consensus_without_overs_advance_suppressed() -> int:
    det = BallDetector(min_gap=0.0)
    frames = [
        _sb(10, 4, "5.0"),
        _sb(11, 5, "5.0"),
        _sb(12, 5, "5.0"),
        _sb(13, 5, "5.0"),
    ]
    results = _drive(det, frames)
    wicket_admissions = [r for r in results if r is not None and r.get("wicket")]
    if wicket_admissions:
        print(f"FAIL P-2: expected 0 admissions (overs-advance gate fails); "
              f"got {len(wicket_admissions)} — admitted={wicket_admissions}")
        return 1
    print("  PASS P-2 (consensus without overs-advance): SUPPRESSED")
    return 0


def _case_p3_consensus_plus_overs_advance_admitted() -> int:
    det = BallDetector(min_gap=0.0)
    frames = [
        _sb(10, 4, "5.5"),
        _sb(11, 5, "5.6"),
        _sb(12, 5, "5.6"),
        _sb(13, 5, "6.0"),
    ]
    results = _drive(det, frames)
    admit_indices = [i for i, r in enumerate(results) if r is not None and r.get("wicket")]
    if len(admit_indices) != 1:
        print(f"FAIL P-3: expected exactly 1 wicket-admission; got {len(admit_indices)} "
              f"at indices {admit_indices}")
        return 1
    if admit_indices[0] != 3:
        print(f"FAIL P-3: expected admission at frame index 3 (streak=3); "
              f"got index {admit_indices[0]}")
        return 1
    print(f"  PASS P-3 (consensus + overs-advance): ADMITTED at frame index 3")
    return 0


def _case_p4_genuine_rahul() -> int:
    det = BallDetector(min_gap=0.0)
    frames = [
        _sb(45, 0, "4.6"),
        _sb(45, 1, "5.0"),
        _sb(45, 1, "5.1"),
        _sb(46, 1, "5.2"),
    ]
    results = _drive(det, frames)
    admit_indices = [i for i, r in enumerate(results) if r is not None and r.get("wicket")]
    if len(admit_indices) != 1:
        print(f"FAIL P-4: expected exactly 1 admission; got {len(admit_indices)} at {admit_indices}")
        return 1
    if admit_indices[0] != 3:
        print(f"FAIL P-4: expected admission at frame index 3 (streak=3 after 3 wicket-fell "
              f"observations + overs-advance); got index {admit_indices[0]}")
        return 1
    print(f"  PASS P-4 (Rahul ov 5.0 genuine): ADMITTED at frame index 3 (3-frame latency)")
    return 0


def _case_p5_genuine_rana() -> int:
    det = BallDetector(min_gap=0.0)
    frames = [
        _sb(70, 1, "7.5"),
        _sb(70, 2, "8.0"),
        _sb(70, 2, "8.1"),
        _sb(71, 2, "8.2"),
    ]
    results = _drive(det, frames)
    admit_indices = [i for i, r in enumerate(results) if r is not None and r.get("wicket")]
    if len(admit_indices) != 1:
        print(f"FAIL P-5: expected exactly 1 admission; got {len(admit_indices)} at {admit_indices}")
        return 1
    print(f"  PASS P-5 (Rana ov 8.0 genuine): ADMITTED at frame index {admit_indices[0]}")
    return 0


def _case_p6_genuine_nissanka() -> int:
    det = BallDetector(min_gap=0.0)
    frames = [
        _sb(80, 2, "9.4"),
        _sb(80, 3, "9.5"),
        _sb(80, 3, "10.0"),
        _sb(81, 3, "10.1"),
    ]
    results = _drive(det, frames)
    admit_indices = [i for i, r in enumerate(results) if r is not None and r.get("wicket")]
    if len(admit_indices) != 1:
        print(f"FAIL P-6: expected exactly 1 admission; got {len(admit_indices)} at {admit_indices}")
        return 1
    print(f"  PASS P-6 (Nissanka ov 9.5 genuine): ADMITTED at frame index {admit_indices[0]}")
    return 0


def _case_p7_reset_clears_candidate_state() -> int:
    det = BallDetector(min_gap=0.0)
    det.check(_sb(10, 4, "5.0"))
    det.check(_sb(11, 5, "5.1"))
    if det._wicket_candidate != 5 or det._wicket_streak != 1:
        print(f"FAIL P-7 setup: expected candidate=5/streak=1 after second frame; "
              f"got candidate={det._wicket_candidate}/streak={det._wicket_streak}")
        return 1
    det.reset()
    if det._wicket_candidate is not None or det._wicket_streak != 0:
        print(f"FAIL P-7: reset() did not clear candidate state; "
              f"candidate={det._wicket_candidate} streak={det._wicket_streak}")
        return 1
    if det.prev_score is not None or det.prev_wickets is not None or det.prev_overs is not None:
        print(f"FAIL P-7: reset() did not clear baseline state")
        return 1
    print("  PASS P-7 (reset clears candidate state + baseline)")
    return 0


def run_all() -> int:
    cases = [
        _case_p1_oscillation_suppressed,
        _case_p2_consensus_without_overs_advance_suppressed,
        _case_p3_consensus_plus_overs_advance_admitted,
        _case_p4_genuine_rahul,
        _case_p5_genuine_rana,
        _case_p6_genuine_nissanka,
        _case_p7_reset_clears_candidate_state,
    ]
    rc = 0
    for case in cases:
        case_rc = case()
        if case_rc != 0:
            rc = case_rc
    if rc == 0:
        print("PASS — all 7 phantom-wicket consensus cases hold")
    return rc


def test_phantom_wicket_consensus() -> None:
    assert run_all() == 0, (
        "phantom-wicket consensus regression — see stdout.")


if __name__ == "__main__":
    sys.exit(run_all())
