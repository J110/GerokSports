"""Workstream H P1 — wickets_regressed team-change-corroboration guard.

Persistent gate-6 regression detector for the `_detect_innings_change`
`wickets_regressed` branch at `files/score_manager.py:4454-4486`.
Mirrors the 2026-05-19 score_reset_from_progress hardening (architectural
parity with the `INN2-SCORE-RESET-TEAM-CHANGE-REQUIRED-REJECTED` guard
at `:4423-4447`).

Six cases — five reject + one accept — derived from the empirical anchor
in `files/docs/investigations/workstream_h_cold_start_reentry_root_
cause.md` §1:

  H-1 (F462 analog): prev=54/3 (5.2) team=DC, cand=14/0 team=None     REJECT
  H-2 (F690 analog): prev=74/2 (8.0) team=DC, cand=0/0  team=None     REJECT
  H-3 (F801 analog): prev=77/2 (9.0) team=DC, cand=67/0 team=DC       REJECT (team unchanged)
  H-4 (F859 analog): prev=80/3 (9.5) team=DC, cand=47/0 team=None     REJECT
  H-5 (F992 analog): prev=86/4 (4.2) team=None, cand=49/0 team=None   REJECT (no team evidence)
  H-6 (legit inn-2): prev=180/8 (20.0) team=DC, cand=12/1 team=KKR    ACCEPT

Wired into pre-commit Layer 1.5 via `test_sm_derivation_ledger.main()`
after the WS-G Shape A `_run_pcd_gate`, mirroring the C15/C31 chain.
"""
from __future__ import annotations

import sys
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FILES_DIR))
sys.path.insert(0, str(FILES_DIR / "tests"))

import trace_emitter  # noqa: E402
from score_manager import FrameInput, ScoreManager  # noqa: E402


REJECT_TAG = "WICKETS-REGRESS-TEAM-CHANGE-REQUIRED-REJECTED"


def _frame(frame_id: int, broadcast_team: str | None,
           broadcast_target: int | None = None) -> FrameInput:
    return FrameInput(
        frame_id=frame_id,
        timestamp=float(frame_id),
        broadcast_team=broadcast_team,
        broadcast_target=broadcast_target,
    )


def _seed(prev_score: int | None, prev_wickets: int | None,
          prev_overs: float | None, prev_team: str | None,
          team_change_streak: int = 0,
          team_change_candidate: str | None = None):
    sm = ScoreManager(shadow=False)
    sm.innings = 1
    if prev_score is not None:
        sm._sm_scalar_fallback["score"] = int(prev_score)
    if prev_wickets is not None:
        sm._sm_scalar_fallback["wickets"] = int(prev_wickets)
    if prev_overs is not None:
        sm._sm_scalar_fallback["overs"] = float(prev_overs)
    if prev_team is not None:
        sm._sm_scalar_fallback["batting_team"] = prev_team
    sm.target = None
    sm._team_change_streak = int(team_change_streak)
    sm._team_change_candidate = team_change_candidate
    return sm


def _drain_for_tag(tag: str) -> list[dict]:
    return [r for r in trace_emitter.get_recorder().drain()
            if r.get("tag") == tag]


def _run_case(label: str, *,
              prev: tuple[int | None, int | None,
                          float | None, str | None],
              cand: tuple[int | None, int | None,
                          float | None, str | None],
              broadcast_target: int | None,
              expect_accept: bool,
              frame_id: int,
              team_change_streak: int = 0,
              team_change_candidate: str | None = None,
              expected_reject_tag: str = REJECT_TAG) -> int:
    prev_score, prev_wickets, prev_overs, prev_team = prev
    cand_score, cand_wickets, cand_overs, cand_team = cand
    sm = _seed(prev_score, prev_wickets, prev_overs, prev_team,
               team_change_streak=team_change_streak,
               team_change_candidate=team_change_candidate)
    trace_emitter.get_recorder().begin_frame(frame_id)
    card = {
        "score": cand_score,
        "wickets": cand_wickets,
        "overs": cand_overs,
    }
    frame = _frame(frame_id, broadcast_team=cand_team,
                   broadcast_target=broadcast_target)
    result = sm._detect_innings_change(card, frame)
    reject_records = _drain_for_tag(expected_reject_tag)
    if expect_accept:
        if result is not True:
            print(f"FAIL {label}: expected ACCEPT (True), got {result}")
            return 1
        if sm.innings != 2:
            print(f"FAIL {label}: expected innings=2 post-accept, "
                  f"got innings={sm.innings}")
            return 1
        if reject_records:
            print(f"FAIL {label}: ACCEPT path should not emit "
                  f"{expected_reject_tag}; got "
                  f"{len(reject_records)} records")
            return 1
        print(f"  PASS {label} (ACCEPT): innings → 2; no "
              f"rejection telemetry on {expected_reject_tag}")
        return 0
    if result is not False:
        print(f"FAIL {label}: expected REJECT (False), got {result}")
        return 1
    if sm.innings != 1:
        print(f"FAIL {label}: expected innings to stay at 1, "
              f"got innings={sm.innings}")
        return 1
    structured = [r for r in reject_records if not r.get("_auto")]
    if len(structured) != 1:
        print(f"FAIL {label}: expected exactly 1 structured "
              f"{expected_reject_tag} record, got {len(structured)}: "
              f"{structured}")
        return 1
    rec = structured[0]
    if expected_reject_tag == REJECT_TAG:
        if rec.get("prev_wickets") != prev_wickets:
            print(f"FAIL {label}: prev_wickets payload mismatch "
                  f"expected={prev_wickets} "
                  f"got={rec.get('prev_wickets')}")
            return 1
        if rec.get("cand_wickets") != cand_wickets:
            print(f"FAIL {label}: cand_wickets payload mismatch "
                  f"expected={cand_wickets} "
                  f"got={rec.get('cand_wickets')}")
            return 1
        print(f"  PASS {label} (REJECT): innings stays 1; "
              f"{expected_reject_tag} structured-payload emitted "
              f"prev_wickets={prev_wickets} cand_wickets={cand_wickets}")
    else:
        if rec.get("prev_score") != prev_score:
            print(f"FAIL {label}: prev_score payload mismatch "
                  f"expected={prev_score} "
                  f"got={rec.get('prev_score')}")
            return 1
        if rec.get("cand_score") != cand_score:
            print(f"FAIL {label}: cand_score payload mismatch "
                  f"expected={cand_score} "
                  f"got={rec.get('cand_score')}")
            return 1
        print(f"  PASS {label} (REJECT): innings stays 1; "
              f"{expected_reject_tag} structured-payload emitted "
              f"prev_score={prev_score} cand_score={cand_score}")
    return 0


_SCORE_RESET_TAG = "INN2-SCORE-RESET-TEAM-CHANGE-REQUIRED-REJECTED"


def run_all() -> int:
    rc = 0
    for case in [
        dict(label="H-1 F462 analog (team=None)",
             prev=(54, 3, 5.2, "DC"),
             cand=(14, 0, None, None),
             broadcast_target=None, expect_accept=False, frame_id=462),
        dict(label="H-2 F690 analog (skeleton 0/0, team=None)",
             prev=(74, 2, 8.0, "DC"),
             cand=(0, 0, None, None),
             broadcast_target=None, expect_accept=False, frame_id=690),
        dict(label="H-3 F801 analog (team unchanged DC→DC)",
             prev=(77, 2, 9.0, "DC"),
             cand=(67, 0, None, "DC"),
             broadcast_target=None, expect_accept=False, frame_id=801),
        dict(label="H-4 F859 analog (team=None post-wicket window)",
             prev=(80, 3, 9.5, "DC"),
             cand=(47, 0, None, None),
             broadcast_target=None, expect_accept=False, frame_id=859),
        dict(label="H-5 F992 analog (prev_team=None, no team evidence)",
             prev=(86, 4, 4.2, None),
             cand=(49, 0, None, None),
             broadcast_target=None, expect_accept=False, frame_id=992),
        dict(label="H-6 legitimate inn-2 (DC → KKR consensus-committed)",
             prev=(180, 8, 20.0, "DC"),
             cand=(12, 1, 0.1, "KKR"),
             broadcast_target=None, expect_accept=True, frame_id=1000,
             team_change_streak=2, team_change_candidate="KKR"),
        dict(label="H-7 F939 analog (single-frame KKR flip, no consensus)",
             prev=(84, 3, 10.1, "DC"),
             cand=(51, 0, None, "KKR"),
             broadcast_target=None, expect_accept=False, frame_id=939),
        dict(label="H-8 KKR flip mid-consensus (streak 1→2, still defer)",
             prev=(84, 3, 10.1, "DC"),
             cand=(51, 0, None, "KKR"),
             broadcast_target=None, expect_accept=False, frame_id=940,
             team_change_streak=1, team_change_candidate="KKR"),
        dict(label="H-9 score_reset sibling parity (KKR flip + 0/0, no consensus)",
             prev=(86, 3, 9.0, "DC"),
             cand=(0, 0, None, "KKR"),
             broadcast_target=None, expect_accept=False, frame_id=941,
             expected_reject_tag=_SCORE_RESET_TAG),
    ]:
        case_rc = _run_case(**case)
        if case_rc != 0:
            rc = case_rc
    if rc == 0:
        print("PASS — all 9 wickets_regressed-guard cases hold "
              "(6 P1 + 3 H1 consensus-parity)")
    return rc


def test_wickets_regressed_guard_holds() -> None:
    assert run_all() == 0, (
        "wickets_regressed team-change guard regression — see stdout.")


if __name__ == "__main__":
    sys.exit(run_all())
