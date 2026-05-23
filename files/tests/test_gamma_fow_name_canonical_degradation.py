"""Workstream H step-5c Shape A — γ-fow-name graceful-degradation gate.

Persistent gate-6 regression detector for the
`trace_gamma_fow_name_matches_striker_at_wicket` assertion-side
tightening at `files/tests/trace_session_assertions.py:425-:454`.
When pipeline.striker is None at the prev-frame snapshot but the
current wicket-commit frame carries a canonical-resolution trace tag
(`WICKET-RESOLVED-FROM-DETERMINISTIC-STRIKER` or
`WICKET-RESOLVED-FROM-PENDING`) whose `dismissed` payload matches the
detected dismissed name, the assertion graceful-degrades to PASS
rather than emitting the `no_prev_striker` FAIL terminal.

Four cases — three cohort instances (F679 DETERMINISTIC, F948
DETERMINISTIC, F1017 PENDING) + one negative (no canonical-resolution
tag → existing FAIL preserved). Cross-references WS-H step-5b memo
§9 (S21 — Assertion-expectation vs. pipeline-state defect class) +
§10.2 test plan.

Wired into pre-commit Layer 1.5 via `test_sm_derivation_ledger.main()`
after the WS-H wickets_regressed-guard chain.
"""
from __future__ import annotations

import sys
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FILES_DIR))
sys.path.insert(0, str(FILES_DIR / "tests"))

from trace_session_assertions import (  # noqa: E402
    assert_fow_name_matches_striker_at_wicket,
)


def _build_records(prev_striker: str | None,
                   dismissed: str,
                   canonical_tag: str | None,
                   canonical_dismissed: str | None) -> list[dict]:
    prev_record = {
        "frame": 678,
        "pipeline": {"striker": prev_striker},
    }
    wicket_decisions = [
        {"tag": "trace_beta_sm_wicket_dispatch",
         "dismissed": dismissed,
         "overs": "8.0"},
    ]
    if canonical_tag:
        wicket_decisions.append({
            "tag": canonical_tag,
            "dismissed": canonical_dismissed,
            "frame_id": 679,
        })
    wicket_record = {
        "frame": 679,
        "pipeline": {"striker": canonical_dismissed},
        "scorer": {"decisions": wicket_decisions},
    }
    return [prev_record, wicket_record]


def _run_case(label: str, *,
              prev_striker: str | None,
              dismissed: str,
              canonical_tag: str | None,
              canonical_dismissed: str | None,
              expect_pass: bool) -> int:
    records = _build_records(prev_striker, dismissed,
                             canonical_tag, canonical_dismissed)
    ok, div = assert_fow_name_matches_striker_at_wicket(records)
    div = div or {}
    if expect_pass:
        if not ok:
            print(f"FAIL {label}: expected PASS, got FAIL "
                  f"with div={div}")
            return 1
        print(f"  PASS {label} (graceful-degrade): canonical tag "
              f"{canonical_tag!r} matched dismissed={dismissed!r}")
        return 0
    if ok:
        print(f"FAIL {label}: expected FAIL, got PASS")
        return 1
    samples = div.get("samples", [])
    if not samples:
        print(f"FAIL {label}: FAIL but no samples emitted")
        return 1
    reason = samples[0].get("reason")
    if reason != "no_prev_striker":
        print(f"FAIL {label}: expected reason=no_prev_striker, "
              f"got reason={reason!r}")
        return 1
    print(f"  PASS {label} (FAIL preserved): reason=no_prev_striker "
          f"with no canonical-resolution alternate")
    return 0


def run_all() -> int:
    cases = [
        dict(label="T-1 F679 analog (DETERMINISTIC, Pathum Nissanka)",
             prev_striker=None,
             dismissed="Pathum Nissanka",
             canonical_tag="WICKET-RESOLVED-FROM-DETERMINISTIC-STRIKER",
             canonical_dismissed="Pathum Nissanka",
             expect_pass=True),
        dict(label="T-2 F948 analog (DETERMINISTIC, KL Rahul)",
             prev_striker=None,
             dismissed="KL Rahul",
             canonical_tag="WICKET-RESOLVED-FROM-DETERMINISTIC-STRIKER",
             canonical_dismissed="KL Rahul",
             expect_pass=True),
        dict(label="T-3 F1017 analog (PENDING, Pathum Nissanka)",
             prev_striker=None,
             dismissed="Pathum Nissanka",
             canonical_tag="WICKET-RESOLVED-FROM-PENDING",
             canonical_dismissed="Pathum Nissanka",
             expect_pass=True),
        dict(label="T-4 negative (no canonical-resolution alternate)",
             prev_striker=None,
             dismissed="Pathum Nissanka",
             canonical_tag=None,
             canonical_dismissed=None,
             expect_pass=False),
    ]
    rc = 0
    for case in cases:
        case_rc = _run_case(**case)
        if case_rc != 0:
            rc = case_rc
    if rc == 0:
        print("PASS — all 4 γ-fow-name graceful-degradation cases hold")
    return rc


def test_gamma_fow_name_canonical_degradation() -> None:
    assert run_all() == 0, (
        "γ-fow-name graceful-degradation regression — see stdout.")


if __name__ == "__main__":
    sys.exit(run_all())
