"""End-to-end replay of yesterday's 95→446 score-jump bug.

Drives a real ScoreManager through:
  1. Three frames at 95/3 (10.0) with target=181, innings=2 → reaches WARM.
  2. One frame with the OCR misread 446/3 (10.0) → must be REJECTED.
  3. One more frame at 95/3 (10.0) → state must be unchanged.
  4. A frame at 96/3 (10.1) → must be ACCEPTED (legal +1 run).

Plus a fresh-cold-start variant proving 446/3 isn't even adoptable as the
very first scorecard the pipeline sees in a chase.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from score_manager import FrameInput, ScoreManager


def _frame(fid: str, t: float, score: int, wkt: int, overs: float,
           target: int = 181) -> FrameInput:
    return FrameInput(
        frame_id=fid, timestamp=t,
        ext_score=score, ext_wickets=wkt, ext_overs=overs,
        broadcast_target=target,
    )


def _drive(sm: ScoreManager, frames: list[FrameInput]) -> None:
    for f in frames:
        sm.on_frame(f)


def test_446_jump_rejected_when_warm():
    """Sequence: warm at 95/3, then OCR misread to 446 must not corrupt state."""
    sm = ScoreManager(shadow=False)

    # Three matching frames to reach WARM consensus.
    _drive(sm, [
        _frame("f1", 0.0, 95, 3, 10.0),
        _frame("f2", 0.5, 95, 3, 10.0),
        _frame("f3", 1.0, 95, 3, 10.0),
    ])
    assert sm.mode == "WARM", f"expected WARM, got {sm.mode}"
    assert sm.score == 95, sm.score

    # The bug: OCR reads 446/3.  Must be rejected by cricket-rules
    # chase ceiling (score > target+4).
    sm.on_frame(_frame("bug", 1.5, 446, 3, 10.0))
    assert sm.score == 95, (
        f"REGRESSION: 446 was accepted into state, score is now {sm.score}")
    assert sm.mode == "WARM", sm.mode

    # Sanity: legal next-ball update still works.
    sm.on_frame(_frame("f5", 2.0, 96, 3, 10.1))
    assert sm.score == 96, f"expected 96 after legal +1, got {sm.score}"


def test_446_rejected_at_cold_start():
    """Even on a fresh cold-start chase, 446/3 with target=181 is impossible."""
    sm = ScoreManager(shadow=False)
    # Pre-set target so the chase ceiling is in scope on the very first frame.
    sm.target = 181
    sm.innings = 2

    _drive(sm, [
        _frame("f1", 0.0, 446, 3, 10.0),
        _frame("f2", 0.5, 446, 3, 10.0),
        _frame("f3", 1.0, 446, 3, 10.0),
    ])
    assert sm.mode != "WARM", (
        f"REGRESSION: 446/3 reached WARM at cold-start; mode={sm.mode}, "
        f"score={sm.score}")
    assert sm.score is None, (
        f"REGRESSION: 446 was adopted as initial score: {sm.score}")


def test_legitimate_cold_start_chase_still_works():
    """Sanity: 95/3 (10.0) with target=181 should reach WARM cleanly."""
    sm = ScoreManager(shadow=False)
    sm.target = 181
    sm.innings = 2

    _drive(sm, [
        _frame("f1", 0.0, 95, 3, 10.0),
        _frame("f2", 0.5, 95, 3, 10.0),
        _frame("f3", 1.0, 95, 3, 10.0),
    ])
    assert sm.mode == "WARM", f"expected WARM, got {sm.mode}"
    assert sm.score == 95


def test_bogus_overs_rejected_at_cold_start():
    """Overs of 18.7 (ball digit > 5) is impossible — must be rejected."""
    sm = ScoreManager(shadow=False)
    _drive(sm, [
        _frame("f1", 0.0, 150, 4, 18.7, target=180),
        _frame("f2", 0.5, 150, 4, 18.7, target=180),
        _frame("f3", 1.0, 150, 4, 18.7, target=180),
    ])
    assert sm.score is None, (
        f"REGRESSION: 18.7 overs accepted; score={sm.score}, "
        f"overs={sm.overs}")


if __name__ == "__main__":
    g = globals()
    tests = [(name, fn) for name, fn in g.items()
             if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}\n        {e}")
        except Exception as e:
            failed += 1
            print(f"  ERR   {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed"
          + (f", {failed} failed" if failed else ""))
    sys.exit(1 if failed else 0)
