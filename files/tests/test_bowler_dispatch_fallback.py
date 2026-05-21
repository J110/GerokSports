"""C28 H-D1 fix — dual-source consensus at wicket-dispatch bowler read.

Persistent gate-6 verification for the BW07 em-dash sentinel fix
inside `_apply_wicket_fall_only`. Three cases cover the
fallback-trigger boundary:

- canonical populated (self.bowler_name="Sunil Narine") → canonical
  wins, fallback does not fire (mid-over wicket — F855 / F1017 shape).
- canonical None → tracker LEADER fallback fires (post-BW07 over-end
  wicket — F400 / F679 shape; em-dash sentinel surface as None).
- canonical em-dash ("—") → tracker LEADER fallback fires (em-dash
  sentinel surface as the literal placeholder; observed in
  pipeline.current_bowler at F400 / F679 of
  validate_dckkr_20260521_155356).

Predicted-flip claim per workstream_d_rotation_root_investigation.md
§2.3 / §6: with this fallback wired, `trace_gamma_bowler_w_increment
_on_dispatch` FAIL×4 → FAIL×2 on next DCKKR replay (F400 + F679 close
via tracker fallback; F855 + F1017 remain FAIL pending H-D2-Layer-1).

Wired into pre-commit Layer 1.5 via test_sm_derivation_ledger.main()
after the cross-field-pairing gate, mirroring the C15 pattern.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

FILES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FILES_DIR))
sys.path.insert(0, str(FILES_DIR / "tests"))

from test_sm_derivation_ledger import build_sm  # noqa: E402


def _prep_sm_for_wicket(canonical_bowler: str | None,
                        tracker_leader: str | None):
    sm, sb = build_sm()
    sm.bat1_name = "Pathum Nissanka"
    sm.bat2_name = "KL Rahul"
    sm.striker = "KL Rahul"
    sm.non = "Pathum Nissanka"
    sm.score = 49
    sm.overs = "5.0"
    sm.wickets = 1
    sm.bowler_name = canonical_bowler
    sm._bowler_tracker = SimpleNamespace(leader=tracker_leader)
    sm._current_frame = 400
    return sm, sb


def _run_case(name: str, canonical: str | None, leader: str | None,
              expect_bowler: str | None,
              expect_fallback_fired: bool) -> tuple[bool, str]:
    sm, sb = _prep_sm_for_wicket(canonical, leader)
    event = {
        "type": "WICKET",
        "dismissed": "KL Rahul",
        "striker": "KL Rahul",
        "wicket_type": "bowled",
        "legal": True,
    }
    frame = SimpleNamespace(frame_id=400, broadcast_striker=None,
                            delivery_info=None)
    sm._apply_wicket_fall_only(event, frame)
    fow = sm._fow_writable()
    if not fow:
        return False, "FOW list empty after dispatch"
    entry = fow[-1]
    got_bowler = entry.get("bowler")
    ok_bowler = (got_bowler == expect_bowler)
    detail = (f"canonical={canonical!r} leader={leader!r} "
              f"fow_bowler={got_bowler!r} expect={expect_bowler!r} "
              f"fallback_fired_expected={expect_fallback_fired}")
    return ok_bowler, detail


CASES: list[tuple] = [
    # (name, canonical_bowler, tracker_leader,
    #  expect_fow_bowler, expect_fallback_fired)
    ("canonical populated → canonical wins (mid-over shape)",
     "Sunil Narine", "Tracker Leader", "Sunil Narine", False),
    ("canonical None → tracker LEADER fallback (BW07 em-dash shape)",
     None, "Kartik Tyagi", "Kartik Tyagi", True),
    ("canonical em-dash → tracker LEADER fallback (literal sentinel)",
     "—", "Cameron Green", "Cameron Green", True),
]


def run_all() -> int:
    """Run all bowler-dispatch fallback cases. Return 0 on PASS."""
    print(f"\n=== BOWLER-DISPATCH-FALLBACK gate (C28 / H-D1) "
          f"— {len(CASES)} cases ===")
    fails = 0
    for case in CASES:
        name = case[0]
        ok, detail = _run_case(*case)
        verdict = "PASS" if ok else "FAIL"
        print(f"  {verdict} {name}: {detail}")
        if not ok:
            fails += 1
    if fails:
        print(f"\nFAIL — {fails}/{len(CASES)} bowler-dispatch "
              f"fallback cases regressed")
        return 1
    print(f"\nPASS — all {len(CASES)} bowler-dispatch fallback "
          f"cases hold")
    return 0


def test_bowler_dispatch_fallback_holds() -> None:
    """pytest entry — H-D1 fallback must hold on all 3 cases."""
    rc = run_all()
    assert rc == 0, (
        "Bowler-dispatch fallback regressed; see stdout for the "
        "first failing case.")


if __name__ == "__main__":
    sys.exit(run_all())
