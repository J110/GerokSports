"""WS-N N1.2 — snapshotter full-pipeline integration contract gate.

Persistent gate-6 verification for the WS-N N1.2 snapshotter
integration shipped on top of N1.1 (`6a07a9a`). Four contract cases
cover the `build_pipeline_components` boundary that the snapshotter
(`replay_captured_scout_trace.py`) now consumes:

- N-1: helper returns NamedTuple with over_mgr / ball_detector /
  partnership_tracker of the right types.
- N-2: `scoreboard.on_fow_upgrade` callback wired to
  `over_mgr.reorder_wicket_to_ball` (Fix 3 back-ref).
- N-3: `score_mgr.scoreboard` back-ref points at the scoreboard
  passed to the helper (Issue 1 canonicalisation pathway).
- N-4: `over_mgr.attach_score_manager(score_mgr)` recorded the
  back-ref (B1.2c slot-binding pathway; verified via
  `over_mgr._score_manager`).

Closes the WS-N step-1c §16-§17 component-classification follow-up
that confirmed setup-portion extraction was clean (per-frame state
mirror in snapshotter loop carries the remaining ~30 LOC).

Wired into pre-commit Layer 1.5 via test_sm_derivation_ledger.main()
after the test_orphan_fallback_bind gate.
"""
from __future__ import annotations

import sys
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FILES_DIR))
sys.path.insert(0, str(FILES_DIR / "scripts"))
sys.path.insert(0, str(FILES_DIR / "tests"))

from eyes.commentary import BallEventDetector, PartnershipTracker  # noqa: E402
from eyes.this_over import ThisOverManager  # noqa: E402
from pipeline_setup_helper import (  # noqa: E402
    PipelineComponents,
    build_pipeline_components,
)
from test_pipeline_captured_replay import build_sm  # noqa: E402


def _build_target() -> tuple:
    sm, sb = build_sm()
    pc = build_pipeline_components(sm, sb)
    return sm, sb, pc


def _case_n1_types() -> tuple[bool, str]:
    _, _, pc = _build_target()
    ok = (
        isinstance(pc, PipelineComponents)
        and isinstance(pc.over_mgr, ThisOverManager)
        and isinstance(pc.ball_detector, BallEventDetector)
        and isinstance(pc.partnership_tracker, PartnershipTracker))
    detail = (
        f"pc={type(pc).__name__} "
        f"over_mgr={type(pc.over_mgr).__name__} "
        f"ball_detector={type(pc.ball_detector).__name__} "
        f"partnership_tracker={type(pc.partnership_tracker).__name__}")
    return ok, detail


def _case_n2_on_fow_upgrade_wired() -> tuple[bool, str]:
    _, sb, pc = _build_target()
    actual = getattr(sb, "on_fow_upgrade", None)
    # Bound-method equality: each `over_mgr.reorder_wicket_to_ball`
    # access constructs a fresh bound-method wrapper, so `is`
    # comparison fails even when the wiring is correct. Compare
    # `__self__` (the instance) and `__func__` (the underlying
    # function) directly.
    ok = (
        actual is not None
        and getattr(actual, "__self__", None) is pc.over_mgr
        and getattr(actual, "__func__", None)
            is type(pc.over_mgr).reorder_wicket_to_ball)
    detail = (
        f"sb.on_fow_upgrade={'set' if actual is not None else 'None'} "
        f"self_is_over_mgr="
        f"{getattr(actual, '__self__', None) is pc.over_mgr} "
        f"func_is_reorder="
        f"{getattr(actual, '__func__', None) is type(pc.over_mgr).reorder_wicket_to_ball}")
    return ok, detail


def _case_n3_score_mgr_scoreboard_wired() -> tuple[bool, str]:
    sm, sb, _ = _build_target()
    ok = sm.scoreboard is sb
    detail = f"sm.scoreboard is sb -> {ok}"
    return ok, detail


def _case_n4_attach_score_manager_wired() -> tuple[bool, str]:
    sm, _, pc = _build_target()
    ok = getattr(pc.over_mgr, "_score_manager", None) is sm
    detail = f"over_mgr._score_manager is sm -> {ok}"
    return ok, detail


CASES: list[tuple[str, callable]] = [
    ("N-1 helper returns PipelineComponents with correct member types",
     _case_n1_types),
    ("N-2 scoreboard.on_fow_upgrade wired to over_mgr.reorder_wicket_to_ball",
     _case_n2_on_fow_upgrade_wired),
    ("N-3 score_mgr.scoreboard back-ref points at scoreboard",
     _case_n3_score_mgr_scoreboard_wired),
    ("N-4 over_mgr.attach_score_manager recorded score_mgr back-ref",
     _case_n4_attach_score_manager_wired),
]


def run_all() -> int:
    """Run all snapshotter full-pipeline integration cases. Return 0 on PASS."""
    print(
        f"\n=== SNAPSHOTTER-FULL-PIPELINE-INTEGRATION gate (WS-N N1.2) "
        f"— {len(CASES)} cases ===")
    fails = 0
    for name, fn in CASES:
        ok, detail = fn()
        verdict = "PASS" if ok else "FAIL"
        print(f"  {verdict} {name}: {detail}")
        if not ok:
            fails += 1
    if fails:
        print(
            f"\nFAIL — {fails}/{len(CASES)} snapshotter-integration "
            f"contract cases regressed")
        return 1
    print(
        f"\nPASS — all {len(CASES)} snapshotter-integration contract "
        f"cases hold")
    return 0


def test_snapshotter_full_pipeline_integration_contract_holds() -> None:
    """pytest entry — WS-N N1.2 integration contract must hold."""
    rc = run_all()
    assert rc == 0, (
        "WS-N N1.2 snapshotter-integration contract regressed; see "
        "stdout for the first failing case.")


if __name__ == "__main__":
    sys.exit(run_all())
