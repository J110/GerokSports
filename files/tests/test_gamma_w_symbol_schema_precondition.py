"""Workstream I step-2 Shape B — γ-w-symbol trace-schema-precondition gate.

Persistent gate-6 regression detector for the
`trace_gamma_w_symbol_at_wicket` assertion-side schema-presence guard
at `files/tests/trace_session_assertions.py:335`. When the F<wicket+1>
trace record lacks `ui_after` (or `ui_after.this_over`) entirely — the
schema variant emitted by `replay_*` / `validate_ws_h_*` /
`validate_shape_*` / `validate_surface_*` traces, which bypass the
UIMirror.apply cycle — the assertion now SKIPs rather than FAILing on
the defensive `[]` degeneracy.

Three cases:
  T-1 Replay-path analog: F<wicket+1> has no `ui_after` field →
      SKIP / PASS-by-precondition.
  T-2 Live-path PASS analog: F<wicket+1>.ui_after.this_over populated
      with W at expected position → PASS via the discriminative path.
  T-3 Live-path FAIL analog: F<wicket+1>.ui_after.this_over populated
      with `.` at expected position (W missing) → FAIL with
      reason=missing (genuine state-layer revert preserved; mirrors
      C21 baseline FAIL × 2 on validate_dckkr_20260521_155356:
      F400 Rahul ov 5.0 + F679 Rana ov 8.0).

Cross-references WS-I step-1 memo
`workstream_i_gamma_w_symbol_cohort_investigation.md` §5.HA + §7 +
§10 + S23 sub-finding.

Wired into pre-commit Layer 1.5 via `test_sm_derivation_ledger.main()`
after the WS-H step-5c γ-fow-name graceful-degradation gate.
"""
from __future__ import annotations

import sys
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FILES_DIR))
sys.path.insert(0, str(FILES_DIR / "tests"))

from trace_session_assertions import (  # noqa: E402
    assert_w_symbol_at_wicket,
)


def _build_records(*, overs: str, next_this_over) -> list[dict]:
    wicket_record = {
        "frame": 679,
        "scorer": {
            "decisions": [
                {"tag": "trace_beta_sm_wicket_dispatch", "overs": overs},
            ],
        },
    }
    if next_this_over is _NO_UI_AFTER:
        next_record = {"frame": 680}
    else:
        next_record = {
            "frame": 680,
            "ui_after": {"this_over": next_this_over},
        }
    return [wicket_record, next_record]


_NO_UI_AFTER = object()


def _run_case(label: str, *,
              overs: str,
              next_this_over,
              expect_pass: bool,
              expect_reason: str | None = None) -> int:
    records = _build_records(overs=overs, next_this_over=next_this_over)
    ok, div = assert_w_symbol_at_wicket(records)
    div = div or {}
    if expect_pass:
        if not ok:
            print(f"FAIL {label}: expected PASS, got FAIL with div={div}")
            return 1
        print(f"  PASS {label} (schema-precondition skip OR W found)")
        return 0
    if ok:
        print(f"FAIL {label}: expected FAIL, got PASS")
        return 1
    samples = div.get("samples", [])
    if not samples:
        print(f"FAIL {label}: FAIL but no samples emitted")
        return 1
    sample = samples[0]
    next_arr = sample.get("next_this_over")
    if expect_reason == "missing" and "W" in (next_arr or []):
        print(f"FAIL {label}: FAIL but W present in next_this_over={next_arr!r}")
        return 1
    print(f"  PASS {label} (FAIL preserved): "
          f"next_this_over={next_arr!r}")
    return 0


def run_all() -> int:
    cases = [
        dict(label="T-1 replay-path schema-absence (ui_after missing)",
             overs="8.0",
             next_this_over=_NO_UI_AFTER,
             expect_pass=True),
        dict(label="T-2 live-path W-present at expected position",
             overs="8.0",
             next_this_over=["1", "6", "1", "4", ".", "W"],
             expect_pass=True),
        dict(label="T-3 live-path W-missing (C21 state-layer revert)",
             overs="8.0",
             next_this_over=["1", "6", "1", "4", ".", "."],
             expect_pass=False,
             expect_reason="missing"),
    ]
    rc = 0
    for case in cases:
        case_rc = _run_case(**case)
        if case_rc != 0:
            rc = case_rc
    if rc == 0:
        print("PASS — all 3 γ-w-symbol schema-precondition cases hold")
    return rc


def test_gamma_w_symbol_schema_precondition() -> None:
    assert run_all() == 0, (
        "γ-w-symbol schema-precondition regression — see stdout.")


if __name__ == "__main__":
    sys.exit(run_all())
