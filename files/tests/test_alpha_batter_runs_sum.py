"""Workstream Per-Batter-Ledger step-2 — α-batter conservation assertion.

Persistent gate-6 regression detector for
`trace_alpha_batter_runs_sum` (assertion at
`files/tests/trace_session_assertions.py`). Verifies cricket-physics
conservation invariant: team_score = sum(per-batter runs) + extras.

Five cases:
  T-1 LIVE-path coverage above floor + sum matches → PASS.
  T-2 LIVE-path coverage above floor + sum MISMATCHES (off by 5) →
      FAIL with informative payload (unaccounted_runs + batter_totals).
  T-3 REPLAY-path schema-absence (no ui_after) → SKIP via Shape B
      precondition (final_score / extras unobservable).
  T-4 LIVE-path coverage BELOW floor (early small fixture analog) →
      SKIP via coverage gate (signal insufficient for discrimination).
  T-5 Extras-only innings (no BAT-DELTA emissions) → SKIP via
      coverage gate (n_emissions / expected = 0/0 → 0 < floor).

Cross-references WS-Per-Batter-Ledger step-1 memo
`workstream_per_batter_ledger_conservation_investigation.md` §5 (HA) +
§7 (gate-6 plan) + step-2 BAT-DELTA cross-cohort coverage census.

Wired into pre-commit Layer 1.5 via `test_sm_derivation_ledger.main()`
after the WS-K phantom-wicket-consensus gate.
"""
from __future__ import annotations

import sys
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FILES_DIR))
sys.path.insert(0, str(FILES_DIR / "tests"))

from trace_session_assertions import (  # noqa: E402
    assert_batter_runs_sum_matches_team_score,
)


def _bat_delta(name: str, cum_runs: int, cum_balls: int = 1) -> dict:
    return {
        "tag": "BAT-DELTA",
        "raw_message": (
            f"  [BAT-DELTA] {name} +runs=1 +balls=1 +4s=0 +6s=0 → "
            f"runs={cum_runs} balls={cum_balls} frame=1"),
    }


def _ts_match(score: int, wickets: int) -> dict:
    return {
        "tag": "SCOREBOARD",
        "raw_message": f"team {score}/{wickets}",
    }


def _live_record(frame: int, score: int, wickets: int,
                 extras_total: int) -> dict:
    return {
        "frame": frame,
        "ts_match": f"team {score}-{wickets}",
        "scorer": {"decisions": []},
        "ui_after": {
            "scorecard": {"score": score, "wickets": wickets},
            "extras_total": extras_total,
        },
    }


def _decisions_record(frame: int, decisions: list[dict]) -> dict:
    return {"frame": frame, "scorer": {"decisions": decisions}}


def _build_live(score: int, extras: int, batter_runs: list[tuple[str, int]],
                extra_dot_emissions: int = 0) -> list[dict]:
    """LIVE-path records: BAT-DELTA emissions (one per cumulative-runs
    increment) + optional dot-ball BAT-DELTAs (no cumulative increment)
    + final ui_after snapshot.

    `extra_dot_emissions` simulates dot-balls: extra BAT-DELTA lines
    that repeat the latest cumulative count for some batter without
    advancing the total. Used to drive coverage above floor when
    batter_runs sum is intentionally short of expected.
    """
    records: list[dict] = []
    decs: list[dict] = []
    per_name_emitted = {n: 0 for n, _ in batter_runs}
    for name, total in batter_runs:
        for cum in range(1, total + 1):
            per_name_emitted[name] = cum
            decs.append(_bat_delta(name, cum))
    if batter_runs and extra_dot_emissions > 0:
        last_name = batter_runs[-1][0]
        last_cum = per_name_emitted[last_name]
        for _ in range(extra_dot_emissions):
            decs.append(_bat_delta(last_name, last_cum))
    records.append(_decisions_record(1, decs))
    records.append(_live_record(2, score, len(batter_runs), extras))
    return records


def _build_replay(batter_runs: list[tuple[str, int]]) -> list[dict]:
    """REPLAY-path records: BAT-DELTA emissions but NO ui_after."""
    decs = []
    for name, total in batter_runs:
        for cum in range(1, total + 1):
            decs.append(_bat_delta(name, cum))
    return [_decisions_record(1, decs)]


def _case(label: str, records: list, expect_pass: bool,
          expect_class: str | None = None) -> int:
    ok, div = assert_batter_runs_sum_matches_team_score(records)
    div = div or {}
    if expect_pass:
        if not ok:
            print(f"FAIL {label}: expected PASS, got FAIL with div={div}")
            return 1
        print(f"  PASS {label}")
        return 0
    if ok:
        print(f"FAIL {label}: expected FAIL, got PASS")
        return 1
    cls = (div.get("samples") or [{}])[0].get("class_name") if div.get("samples") else div.get("class_name")
    if expect_class and cls != expect_class:
        cls_from_div = div.get("class_name")
        if cls_from_div != expect_class:
            print(f"FAIL {label}: expected class={expect_class!r}, got div={div}")
            return 1
    print(f"  PASS {label} (FAIL preserved): unaccounted={div.get('unaccounted_runs')}")
    return 0


def _case_t1_pass() -> int:
    # score=10, extras=0 → expected=10; sum_batter=10; coverage 10/10=100%
    records = _build_live(10, 0, [("Alice", 6), ("Bob", 4)])
    return _case("T-1 LIVE coverage-high + sum-matches",
                 records, expect_pass=True)


def _case_t2_fail_mismatch() -> int:
    # score=10, extras=0 → expected=10; sum_batter=5; coverage 10/10
    # (5 cumulative emissions + 5 dot-ball emissions = 10 ≥ 7 floor);
    # gap=5 → FAIL.
    records = _build_live(10, 0, [("Alice", 3), ("Bob", 2)],
                          extra_dot_emissions=5)
    return _case("T-2 LIVE coverage-high + sum-mismatch",
                 records, expect_pass=False,
                 expect_class="batter_runs_sum_short")


def _case_t3_replay_skip() -> int:
    # REPLAY: no ui_after → final_score=None → SKIP via Shape B
    records = _build_replay([("Alice", 6), ("Bob", 4)])
    return _case("T-3 REPLAY no-ui_after → SKIP",
                 records, expect_pass=True)


def _case_t4_coverage_below_floor_skip() -> int:
    # score=100, extras=0 → expected=100; only 10 emissions (cumulative)
    # → coverage 10/100=10% below 70% floor → SKIP.
    records = _build_live(100, 0, [("Alice", 6), ("Bob", 4)])
    return _case("T-4 LIVE coverage-below-floor → SKIP",
                 records, expect_pass=True)


def _case_t5_extras_only_innings_skip() -> int:
    # score=5, extras=5 → expected=0; SKIP via expected<=0 early-return.
    records = _build_live(5, 5, [])
    return _case("T-5 extras-only innings → SKIP",
                 records, expect_pass=True)


def run_all() -> int:
    cases = [
        _case_t1_pass,
        _case_t2_fail_mismatch,
        _case_t3_replay_skip,
        _case_t4_coverage_below_floor_skip,
        _case_t5_extras_only_innings_skip,
    ]
    rc = 0
    for case in cases:
        case_rc = case()
        if case_rc != 0:
            rc = case_rc
    if rc == 0:
        print("PASS — all 5 α-batter-runs-sum cases hold")
    return rc


def test_alpha_batter_runs_sum() -> None:
    assert run_all() == 0, (
        "α-batter-runs-sum regression — see stdout.")


if __name__ == "__main__":
    sys.exit(run_all())
