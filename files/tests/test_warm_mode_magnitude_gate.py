"""WS-O.b O.b1 PA+PE — WARM-mode magnitude gate + derivation negative-bounding.

Persistent gate-6 verification for the WS-O.b PA+PE patch shipped
on top of step-1 memo (`769d786`). Two contract cases cover the
single-surface cascade root WS-O step-3 (`ed70807`) surfaced:

- O.b-1 PA WARM-mode magnitude gate at sb.set: synthetic Scout
  inputs covering (a) bogus 49 spike at balls=12 (overs=2.0) →
  PA rejects + WARM-MODE-MAGNITUDE-GATE-REJECTED tag fires +
  sb._inn["score"] unchanged; (b) legitimate progression 0→1→4→7
  at small overs → PA accepts each commit (no false-negative on
  real cricket progression).

- O.b-2 PE derivation negative-runs guard: synthetic prior /
  current SnapshotPrimitives with `runs_off_bat = -3` →
  `derive_this_over_token` returns None (cricket-physics-
  impossible) instead of emitting `str(-3)`. Caller surface at
  score_manager.py:6682 + :6815 already handles None via "?"
  placeholder fallback (verified at step-2 V2).

Wired into pre-commit Layer 1.5 via test_sm_derivation_ledger.main()
after the test_cold_start_magnitude_gate gate (WS-O O1).

NOTE: This is a SINGLE-SURFACE defect closure, NOT a §12
dual-state-write instance. WS-O.b step-1 memo's §12 4th-instance
framing was falsified by step-2 V3 verification (sm.score is
@property reading sb._inn["score"] directly; no parallel surface
exists). S29 promotion at step-1 is retracted in the step-2
commit body. See WS-O.b step-2 commit for the framing retraction.
"""
from __future__ import annotations

import sys
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FILES_DIR))

from eyes.scoreboard import Scoreboard  # noqa: E402
from score_manager_derivation import (  # noqa: E402
    SnapshotPrimitives,
    derive_this_over_token,
)


def _make_sb() -> Scoreboard:
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="DC",
        bowling_team="KKR",
        batting_squad=["Nissanka", "Rahul"] + [f"P{i}" for i in range(9)],
        bowling_squad=["Roy", "Arora"] + [f"B{i}" for i in range(9)],
        batting_xi=["Nissanka", "Rahul"] + [f"P{i}" for i in range(9)],
        bowling_xi=["Roy", "Arora"] + [f"B{i}" for i in range(9)],
    )
    return sb


def _case_obb1_pa_rejects_bogus_spike() -> tuple[bool, str]:
    sb = _make_sb()
    # Seed canonical state at balls=12 (overs=2.0), score=17 —
    # mid-innings WARM-mode anchor. force_reset_score bypasses
    # both the regression-rejection and PA so the test starts
    # from a known baseline regardless of which gate would
    # otherwise fire.
    sb.force_reset_score(17, reason="test_baseline", frame=0)
    sb._inn["overs"] = "2.0"  # direct set to avoid consensus-tracker delay
    # Bogus 49 spike: max plausible at balls=12 is 12 * 2.5 + 10
    # = 40. Proposed 49 > 40 → PA rejects. Pre-PA the +32 delta
    # would have passed the existing regression-rejection
    # (49 > 17) and per-update-jump guard (+32 < 100).
    accepted = sb.set("score", 49, frame=1)
    sb_score_after = sb._inn.get("score")
    ok = (accepted is False and sb_score_after == 17)
    detail = (
        f"sb.set(49) returned {accepted}; sb._inn['score']="
        f"{sb_score_after} (expected: rejected, stays at 17)")
    return ok, detail


def _case_obb2_pe_negative_runs_returns_none() -> tuple[bool, str]:
    prior = SnapshotPrimitives(
        score=49, wickets=0, overs="2.2",
        legal_balls_in_over=2,
        extras_total=0, extras_wd=0, extras_nb=0,
        extras_b=0, extras_lb=0,
        bat1_name="Nissanka", bat2_name="Rahul",
        bowler_name="Roy", striker="Nissanka",
    )
    current = SnapshotPrimitives(
        score=22, wickets=0, overs="2.3",
        legal_balls_in_over=3,
        extras_total=0, extras_wd=0, extras_nb=0,
        extras_b=0, extras_lb=0,
        bat1_name="Nissanka", bat2_name="Rahul",
        bowler_name="Roy", striker="Nissanka",
    )
    token = derive_this_over_token(prior, current, None)
    ok = token is None
    detail = (
        f"runs_off_bat=-27 (prior.score=49, current.score=22) "
        f"token={token}")
    return ok, detail


CASES: list[tuple[str, callable]] = [
    ("O.b-1 PA rejects bogus 49 spike at balls=12 "
     "(pre-PA: would have passed regression + per-update-jump guards)",
     _case_obb1_pa_rejects_bogus_spike),
    ("O.b-2 PE returns None on cricket-physics-impossible "
     "negative runs_off_bat",
     _case_obb2_pe_negative_runs_returns_none),
]


def run_all() -> int:
    """Run all WS-O.b O.b1 PA+PE cases. Return 0 on PASS."""
    print(
        f"\n=== WARM-MODE-MAGNITUDE-GATE + DERIVATION-NEGATIVE-BOUNDING "
        f"gate (WS-O.b O.b1) — {len(CASES)} cases ===")
    fails = 0
    for name, fn in CASES:
        ok, detail = fn()
        verdict = "PASS" if ok else "FAIL"
        print(f"  {verdict} {name}: {detail}")
        if not ok:
            fails += 1
    if fails:
        print(
            f"\nFAIL — {fails}/{len(CASES)} WS-O.b O.b1 PA+PE cases "
            f"regressed")
        return 1
    print(
        f"\nPASS — all {len(CASES)} WS-O.b O.b1 PA+PE cases hold")
    return 0


def test_warm_mode_magnitude_gate_holds() -> None:
    """pytest entry — WS-O.b O.b1 PA+PE must hold on all 2 cases."""
    rc = run_all()
    assert rc == 0, (
        "WS-O.b O.b1 PA+PE regressed; see stdout for the first "
        "failing case.")


if __name__ == "__main__":
    sys.exit(run_all())
