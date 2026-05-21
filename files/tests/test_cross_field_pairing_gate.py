"""C14 Shape B — cross-field pairing gate at apply_scorer_decision.

Persistent gate-6 verification for the B-η F304 cascade-root fix
shipped in commit `ad151fd`. Six behavioral cases cover the
legitimate_pair predicate's accept/reject boundary:

- F302 legitimate (Δscore=+4, Δballs=+1): accept (legal-delivery shape)
- F304 cascade root (Δscore=+5, Δballs=+10): REJECT (multi-ball-gap
  signature)
- GTRR f72 heavy-extras (Δscore=+5, Δballs=0): accept (extras-only shape)
- Over rollover (X.5→(X+1).0, Δscore=+1): accept
- Six off a ball (Δscore=+6, Δballs=+1): accept
- Wicket-on-ball (Δscore=0, Δballs=+1, Δwickets=+1): accept

Pairing criterion per c13_fc5_audit_memo.md §2.1:

  legitimate_pair(d_score, d_balls, d_wickets) ≡
      (d_balls == 1 AND 0 ≤ d_score ≤ 7 AND d_wickets ∈ {0, 1})
    OR
      (d_balls == 0 AND 0 ≤ d_score ≤ 5 AND d_wickets ∈ {0, 1})

Empirically grounded: GTRR 80 + DCKKR 47 benign DIRECT-SCORE-COMMIT
firings all satisfy the predicate; F304's bad PANT/WARD/SHAMI
overlay frame fails it (Δscore=+5 paired with Δballs=+10).

Wired into pre-commit Layer 1.5 via test_sm_derivation_ledger.main()
so the gate-6 evidence persists for every future commit.
"""
from __future__ import annotations

import sys
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FILES_DIR))
sys.path.insert(0, str(FILES_DIR / "tests"))

from test_pipeline import apply_scorer_decision  # noqa: E402
from test_sm_derivation_ledger import build_sm  # noqa: E402


def _run_case(name: str, cur_score: int, cur_overs: str, cur_wkts: int,
              prop_score: int, prop_overs: str, prop_wkts: int,
              expect_reject: bool) -> tuple[bool, str]:
    sm, sb = build_sm()
    sb._inn["score"] = cur_score
    sb._inn["overs"] = str(cur_overs)
    sb._inn["wickets"] = cur_wkts
    sb._tracker.confirmed["score"] = cur_score
    sb._tracker.confirmed["overs"] = str(cur_overs)
    sb._tracker.confirmed["wickets"] = cur_wkts
    decision = {
        "score_update": {"accepted": True, "to": prop_score},
        "overs_update": {"accepted": True, "to": str(prop_overs)},
        "wickets_update": {"accepted": True, "to": prop_wkts},
        "batter_updates": {"Pathum Nissanka": {
            "accepted": True, "runs": 26, "balls": 16}},
        "bowler_update": {"name": "Kartik Tyagi", "accepted": True},
    }
    extracted = {
        "score": prop_score, "match_overs": prop_overs,
        "wickets": prop_wkts,
        "batters": [{"name": "Pathum Nissanka", "runs": 26, "balls": 16}],
    }
    changes = apply_scorer_decision(
        sb, decision, 304, None,
        batting_team="DC", extracted=extracted,
        frame_type="SCOREBOARD", score_mgr=sm)
    rejected = any(
        "CROSS-FIELD-PAIRING-REJECT" in str(c) for c in (changes or []))
    ok = (rejected == expect_reject)
    detail = (f"rejected={rejected} expect={expect_reject} "
              f"changes_sample={str(changes)[:120]}")
    return ok, detail


CASES: list[tuple] = [
    # (name, cur_score, cur_overs, cur_wkts,
    #  prop_score, prop_overs, prop_wkts, expect_reject)
    ("F302 legitimate (Δscore=+4, Δballs=+1)",
     45, "4.4", 0, 49, "4.5", 0, False),
    ("F304 CASCADE ROOT (Δscore=+5, Δballs=+10)",
     49, "4.5", 0, 54, "6.3", 0, True),
    ("GTRR f72 heavy-extras (Δscore=+5, Δballs=0)",
     7, "0.3", 0, 12, "0.3", 0, False),
    ("Over rollover (5.5→6.0, Δscore=+1)",
     80, "5.5", 0, 81, "6.0", 0, False),
    ("Six (Δscore=+6, Δballs=+1)",
     20, "2.2", 0, 26, "2.3", 0, False),
    ("Wicket-on-ball (Δscore=0, Δballs=+1, Δwkt=+1)",
     49, "4.5", 0, 49, "4.6", 1, False),
]


def run_all() -> int:
    """Run all cross-field pairing gate cases. Return 0 on PASS."""
    print(f"\n=== CROSS-FIELD-PAIRING gate (C14) — {len(CASES)} cases ===")
    fails = 0
    for case in CASES:
        name = case[0]
        ok, detail = _run_case(*case)
        verdict = "PASS" if ok else "FAIL"
        print(f"  {verdict} {name}: {detail}")
        if not ok:
            fails += 1
    if fails:
        print(f"\nFAIL — {fails}/{len(CASES)} cross-field pairing cases regressed")
        return 1
    print(f"\nPASS — all {len(CASES)} cross-field pairing cases hold")
    return 0


def test_cross_field_pairing_gate_holds() -> None:
    """pytest entry — Shape B gate must hold on all 6 representative cases."""
    rc = run_all()
    assert rc == 0, (
        "Cross-field pairing gate regressed; see stdout for the "
        "first failing case.")


if __name__ == "__main__":
    sys.exit(run_all())
