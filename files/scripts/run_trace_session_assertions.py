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
