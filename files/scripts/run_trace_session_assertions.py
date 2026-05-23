#!/usr/bin/env python3
"""Run the five trace-session assertions against a session's trace
JSONL and a per-session context (expected initial striker).

Usage:
  python files/scripts/run_trace_session_assertions.py [TRACE_PATH]

Defaults to logs/trace/validate_gtrr_20260520_180715.jsonl — the
session that produced the broken-but-known baseline documented in
files/docs/investigations/sm_as_orchestrator_design.md.

The runner prints per-assertion pass/fail with divergence details
and a summary line. Exit status 0 always — the script is a
diagnostic tool, not a gate. Pre-commit gating is a separate concern
(see commit body for context).
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "files"))
sys.path.insert(0, str(ROOT / "files" / "tests"))

from trace_session_assertions import (  # noqa: E402
    TRACE_ASSERTIONS, run_all_trace_assertions,
)


DEFAULT_TRACE = (
    ROOT / "logs" / "trace" / "validate_gtrr_20260520_180715.jsonl")

# Per-session context. Indexed by trace filename stem.
#
# Cascade-closure note (2026-05-20). The validate_gtrr_20260520_180715
# baseline below is the broken-but-known state captured BEFORE the F1
# cold-start initial-striker fix (commit 437d952) shipped. F1's
# subsequent cross-fixture verification (see B-β audit memo
# files/docs/investigations/sm_wicket_dispatch_design.md §7) showed F1
# closes at least four bug classes simultaneously: B-ε (direct),
# B-β (cascade), multi-ball decomposition false positives (cascade),
# and compound tokens (cascade). On the next fresh production trace
# captured AFTER F1 ships, the expected flips are:
#
#   trace_epsilon_initial_striker     FAIL → PASS  (direct)
#   trace_beta_sm_wicket_dispatch     FAIL → PASS  (cascade closure)
#   trace_compound_tokens             FAIL → PASS  (cascade closure, observed
#                                                   in post-F1 captured-replay)
#   trace_alpha_bowler_runs_sum       FAIL → significant reduction (cascade
#                                                   contributors collapsed;
#                                                   residual depends on
#                                                   remaining bye/extras
#                                                   classification work)
#   trace_extras_total                FAIL → unchanged or improved (UI render
#                                                   layer, separate scope)
#
# When a fresh production trace lands, the natural validation step is
# to add its filename stem to SESSION_CONTEXT below with the same
# expected_initial_striker (Sai Sudharsan) AND run the assertions to
# empirically confirm the predicted flips. Unflipped assertions on
# fresh data become the next concrete engineering targets.
SESSION_CONTEXT: dict[str, dict] = {
    "validate_gtrr_20260520_180715": {
        # Per Cricbuzz commentary (
        # files/tests/fixtures/gt_vs_rr_2026_commentary_first_innings.md):
        # "Opening pair: Sai Sudharsan on strike, Shubman Gill non-striker."
        "expected_initial_striker": "Sai Sudharsan",
        # The session's final ui_after.extras_total = 1, but archived
        # Wd/Nb token count is much higher (see assertion's own
        # computation). Leaving None so the assertion uses the
        # session's own extras_total as the upper bound.
        "max_acceptable_extras": None,
    },
    "validate_dckkr_20260521_070545": {
        # Per ground-truth ledger
        # (files/tests/fixtures/dc_vs_kkr_2026_152064_overs_1_6_ground_truth.md):
        # "Initial state: Pathum Nissanka on strike, KL Rahul non-striker."
        "expected_initial_striker": "Pathum Nissanka",
        "max_acceptable_extras": None,
    },
    "validate_surface_b_121222": {
        # Workstream G step-8 re-validation replay against the
        # captured-Scout dump from validate_dckkr_20260521_155356,
        # under Surface B code 50af67e (cold-start lifecycle closure).
        # Same-fixture as step-5 validate_shape_a_114349; isolates the
        # f09fc38 → 50af67e delta as the only independent variable.
        #
        # All four lifecycle predictions per workstream_g_cold_drain_
        # surface_audit.md §5 LANDED:
        #   POST-WICKET-CASCADE-ENQUEUED × 2
        #     F679 reason=wicket_non_striker_stays (Nitish Rana)
        #     F855 reason=wicket_new_batter (Pathum Nissanka)
        #   POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START × 2
        #     F690 age=11 site=set_innings_2:wickets_regressed
        #     F859 age=4  site=set_innings_2:wickets_regressed
        #   POST-WICKET-CASCADE-DRAIN-FIRED × 0
        #   CASCADE-DRAIN-EXPIRED × 0
        #   trace_eta_post_wicket_cascade_drains: PASS (orphan 2 → 0)
        #
        # Insight #18 scope: D-post-FoW-striker remains at 20.
        # Primary objective deferred to Workstream H (cold-start
        # re-entry frequency root cause; HANDOFF §17.3 items 2/3/4).
        "expected_initial_striker": "Pathum Nissanka",
        "max_acceptable_extras": None,
    },
    "validate_ws_h_step3_20260523_164642": {
        # Workstream H step-3 P1 empirical validation replay against
        # the same captured-Scout dump as WS-G steps 5/8
        # (files/logs/deliveries/validate_dckkr_20260521_155356/
        # scout_raw.jsonl). Single independent variable: P1 patch
        # ef0860d (team-change-corroboration guard on the
        # wickets_regressed branch of _detect_innings_change).
        # WS-H primary objective CLOSED on this trace:
        #   SM-INNINGS-2-RESET reason=wickets_regressed:  5  → 1 (F939 only;
        #                                                        inherited
        #                                                        sibling-asymmetry
        #                                                        per S16)
        #   WICKETS-REGRESS-TEAM-CHANGE-REQUIRED-REJECTED: 0 → 19 structured
        #   POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START: 2 → 0
        #   POST-WICKET-CASCADE-DRAIN-FIRED:               0 → 2 (F680, F858)
        #   D-post-FoW-striker surface count:             20 → 2
        #   trace_gamma_bowler_w_increment_on_dispatch:   FAIL×4 → PASS
        #                                                 (composite-fix per S18)
        #   trace_gamma_fow_name_matches_striker_at_wicket: PASS → FAIL × 1
        #                                                 (F679; per S17)
        #   trace_eta_post_wicket_cascade_drains:         PASS × 2 (terminal
        #                                                 distribution shifted
        #                                                 WIPED → FIRED)
        # See files/docs/investigations/workstream_h_cold_start_
        # reentry_root_cause.md §8-§11.
        "expected_initial_striker": "Pathum Nissanka",
        "max_acceptable_extras": None,
    },
    "validate_ws_h_step7": {
        # Workstream H step-7 H1 empirical validation replay against
        # the same captured-Scout dump as WS-H step-3
        # (files/logs/deliveries/validate_dckkr_20260521_155356/
        # scout_raw.jsonl). Single independent variable: H1 patch
        # 832d376 (consensus-parity gate on _team_changed at the
        # _detect_innings_change derivation site :4417-:4420).
        "expected_initial_striker": "Pathum Nissanka",
        "max_acceptable_extras": None,
    },
    "validate_dckkr_20260521_155356": {
        # C14 Shape B validation-gate replay (DCKKR 09:30 through
        # ov 11.5). 4 wicket events. C24 wicket-correctness γ-bundle
        # empirical baseline (post-C19/C20/C21/C22/C23):
        #   trace_gamma_w_symbol_at_wicket:                 FAIL × 2
        #   trace_gamma_fow_name_matches_striker_at_wicket: PASS
        #   trace_gamma_bowler_w_increment_on_dispatch:     FAIL × 4
        # Detection on this trace uses the ball_event.type==WICKET
        # fallback because the trace was captured before C19A3's
        # trace_beta_sm_wicket_dispatch emission landed.
        "expected_initial_striker": "Pathum Nissanka",
        "max_acceptable_extras": None,
    },
}


def load_records(path: pathlib.Path) -> list[dict]:
    out: list[dict] = []
    with path.open() as fh:
        # First line is the schema header.
        fh.readline()
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        trace_path = pathlib.Path(argv[1])
    else:
        trace_path = DEFAULT_TRACE
    if not trace_path.exists():
        print(f"trace not found: {trace_path}")
        return 1
    records = load_records(trace_path)
    print(f"Loaded {len(records)} frame records from {trace_path}")
    print()

    session_id = trace_path.stem
    context = SESSION_CONTEXT.get(session_id, {})

    results = run_all_trace_assertions(records, context=context)

    print("=" * 78)
    print(f"TRACE-SESSION ASSERTION RESULTS — {session_id}")
    print("=" * 78)
    for name, ok, div in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
        if div:
            for k, v in div.items():
                if isinstance(v, list):
                    print(f"      {k}: list[{len(v)}]")
                    for s in v[:3]:
                        print(f"        - {s}")
                else:
                    print(f"      {k}: {v}")
    print()
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    print(f"Summary: {passed} PASS / {failed} FAIL out of {len(results)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
