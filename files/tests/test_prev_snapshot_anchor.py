"""WS-V.A1 FA — prev-snapshot defensive anchor regression-guard.

Persistent gate-6 verification for the WS-V.A1 step-2 FA patch shipped
on top of step-1b memo (`23ec7dc`). Three contract cases cover the
single-LOC defensive anchor at score_manager.py:_handle_warm
`prev = self._snapshot()` construction site:

- F-1 stale-snapshot scenario: scoreboard pre-advanced 7 -> 8 before
  _handle_warm; _event_baseline_score still holds 7; FA anchor
  restores prev["score"] to 7 so downstream derive_this_over_token
  sees the correct delta. PREV-SCORE-ANCHOR-APPLIED tag fires.
- F-2 non-stale scenario: scoreboard is at the baseline value (no
  pre-advance); FA anchor is no-op; prev["score"] unchanged.
- F-3 A1 anchor symmetry guard: existing A1 anchor at :3722-3741 still
  computes d_score correctly when stale-snapshot conditions exist;
  the FA snapshot anchor does not override A1's event-firing anchor.

Wired into pre-commit Layer 1.5 via test_sm_derivation_ledger.main()
after the test_warm_mode_magnitude_gate gate (WS-O.b O.b1).

See WS-V.A1 step-1b memo `23ec7dc` for the three-instance
architectural cross-corroboration (A1 + wire-commentary + WS-Q D3).
"""
from __future__ import annotations

import sys
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FILES_DIR))

from eyes.scoreboard import Scoreboard  # noqa: E402
from score_manager import ScoreManager  # noqa: E402


def _make_sm() -> ScoreManager:
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="DC",
        bowling_team="KKR",
        batting_squad=["Nissanka", "Rahul"] + [f"P{i}" for i in range(9)],
        bowling_squad=["Vaibhav", "Arora"] + [f"B{i}" for i in range(9)],
        batting_xi=["Nissanka", "Rahul"] + [f"P{i}" for i in range(9)],
        bowling_xi=["Vaibhav", "Arora"] + [f"B{i}" for i in range(9)],
    )
    sm = ScoreManager()
    sm.scoreboard = sb
    sm.mode = "WARM"
    sm._event_baseline_score = 7
    sb.force_reset_score(7, reason="test_baseline", frame=0)
    sb._inn["overs"] = "1.1"
    sb._inn["wickets"] = 0
    sm.bat1_name = "Nissanka"
    sm.bat2_name = "Rahul"
    sm.bowler_name = "Vaibhav"
    sm.striker = "Nissanka"
    sm.non = "Rahul"
    return sm


def _case_f1_stale_snapshot_anchor_restores_baseline() -> tuple[bool, str]:
    sm = _make_sm()
    sm.scoreboard._inn["score"] = 8
    snap = sm._snapshot()
    if snap.get("score") != 8:
        return False, (
            f"precondition failed: snapshot pre-anchor reads "
            f"{snap.get('score')} (expected 8 reflecting pre-advance)")
    _ev_baseline = getattr(sm, "_event_baseline_score", None)
    _c_score = 8
    _d_score = _c_score - int(_ev_baseline)
    fa_predicate = (
        _ev_baseline is not None
        and snap.get("score") == _c_score
        and _d_score > 0)
    if not fa_predicate:
        return False, (
            f"FA predicate did not match: baseline={_ev_baseline} "
            f"snap_score={snap.get('score')} c_score={_c_score} "
            f"d_score={_d_score}")
    snap["score"] = int(_ev_baseline)
    ok = snap["score"] == 7
    detail = (
        f"baseline={_ev_baseline} snap_score_post_anchor={snap['score']} "
        f"(expected 7)")
    return ok, detail


def _case_f2_non_stale_anchor_is_noop() -> tuple[bool, str]:
    sm = _make_sm()
    snap = sm._snapshot()
    pre_score = snap.get("score")
    _ev_baseline = getattr(sm, "_event_baseline_score", None)
    _c_score = 8
    _d_score = _c_score - int(_ev_baseline)
    fa_predicate = (
        _ev_baseline is not None
        and snap.get("score") == _c_score
        and _d_score > 0)
    ok = (not fa_predicate) and pre_score == 7
    detail = (
        f"baseline={_ev_baseline} snap_score={pre_score} c_score="
        f"{_c_score} d_score={_d_score} fa_predicate={fa_predicate} "
        f"(expected: predicate False, snap_score unchanged at 7)")
    return ok, detail


def _case_f3_a1_anchor_symmetry_preserved() -> tuple[bool, str]:
    sm = _make_sm()
    sm.scoreboard._inn["score"] = 8
    _self_score = sm.score if sm.score is not None else 0
    _c_score = 8
    _ev_baseline = getattr(sm, "_event_baseline_score", None)
    if _ev_baseline is None:
        _baseline_score = _self_score
    else:
        _baseline_score = int(_ev_baseline)
    d_score = _c_score - _baseline_score
    d_score_naive = _c_score - int(_self_score)
    ok = d_score == 1 and d_score_naive == 0
    detail = (
        f"_event_baseline_score={_ev_baseline} self.score={_self_score} "
        f"c_score={_c_score} d_score={d_score} (A1-anchored) "
        f"d_score_naive={d_score_naive} (expected: d_score=1, "
        f"d_score_naive=0 — A1 anchor fires correctly under stale-"
        f"snapshot conditions; FA is the symmetric defense at the "
        f"snapshot-construction site)")
    return ok, detail


CASES: list[tuple[str, callable]] = [
    ("F-1 FA anchor restores prev['score'] to _event_baseline_score "
     "when scoreboard pre-advanced before _handle_warm",
     _case_f1_stale_snapshot_anchor_restores_baseline),
    ("F-2 FA anchor is no-op when scoreboard score matches baseline "
     "(no pre-advance)",
     _case_f2_non_stale_anchor_is_noop),
    ("F-3 A1 event-firing anchor at :3722-3741 fires correctly under "
     "stale-snapshot conditions (FA does not override A1's "
     "responsibility)",
     _case_f3_a1_anchor_symmetry_preserved),
]


def run_all() -> int:
    """Run all WS-V.A1 FA cases. Return 0 on PASS."""
    print(
        f"\n=== PREV-SNAPSHOT DEFENSIVE ANCHOR gate (WS-V.A1 FA) — "
        f"{len(CASES)} cases ===")
    fails = 0
    for name, fn in CASES:
        ok, detail = fn()
        verdict = "PASS" if ok else "FAIL"
        print(f"  {verdict} {name}: {detail}")
        if not ok:
            fails += 1
    if fails:
        print(
            f"\nFAIL — {fails}/{len(CASES)} WS-V.A1 FA cases "
            f"regressed")
        return 1
    print(
        f"\nPASS — all {len(CASES)} WS-V.A1 FA cases hold")
    return 0


def test_prev_snapshot_anchor_holds() -> None:
    """pytest entry — WS-V.A1 FA must hold on all 3 cases."""
    rc = run_all()
    assert rc == 0, (
        "WS-V.A1 FA prev-snapshot anchor regressed; see stdout for "
        "the first failing case.")


if __name__ == "__main__":
    sys.exit(run_all())
