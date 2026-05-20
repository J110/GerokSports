#!/usr/bin/env python3
"""Stage S0 — scar-tissue deletion plan validation.

Walks the live codebase and confirms every deletion target's location
matches the plan in commit message of S0. Reports any drift between
plan and reality before the per-stage deletions execute.

Also captures the symptom-assertion-library baseline (per-class fail
counts) as the reference point for predicted-flip verification at
each subsequent stage.

No behavior change; this script is read-only validation.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


# (label, file, pattern, expected_line_range)
TARGETS = [
    ("PendingBall dataclass",
     "files/score_manager.py", r"^class PendingBall:", (240, 290)),
    ("_pending_ball_queue init",
     "files/score_manager.py", r"self\._pending_ball_queue", (445, 455)),
    ("_decompose_multi_ball",
     "files/score_manager.py", r"def _decompose_multi_ball", (4300, 4340)),
    ("_apply_absorbed_event",
     "files/score_manager.py", r"def _apply_absorbed_event", (4810, 4840)),
    ("_synthesize_cold_start_ball_events",
     "files/score_manager.py",
     r"def _synthesize_cold_start_ball_events", (1830, 1860)),
    ("_maybe_synthesize_cold_start_gap",
     "files/score_manager.py",
     r"def _maybe_synthesize_cold_start_gap", (2060, 2090)),
    ("COLD_START_SYNTH event handler (apply_event branch)",
     "files/score_manager.py",
     r"if etype == \"COLD_START_SYNTH\"", (5040, 5060)),
    ("on_broadcast_override",
     "files/eyes/this_over.py",
     r"def on_broadcast_override", (790, 820)),
    ("_pending_slots init",
     "files/eyes/this_over.py",
     r"self\._pending_slots", (85, 100)),
    ("_merge_broadcast",
     "files/eyes/this_over.py",
     r"def _merge_broadcast", (1120, 1170)),
    ("MAX_THIS_OVER_LEN constant",
     "files/eyes/this_over.py",
     r"MAX_THIS_OVER_LEN", (1075, 1130)),
    ("_ScoutRetryBuffer",
     "files/eyes/openscout_loop.py",
     r"class _ScoutRetryBuffer", (65, 90)),
    ("MULTI-BALL-DERIVATION-EXPANDED trace tag",
     "files/trace_emitter.py",
     r"MULTI-BALL-DERIVATION-EXPANDED", (60, 80)),
    ("broadcast_this_over field (extract_regex)",
     "files/eyes/extract_regex.py",
     r"this_over_broadcast", (380, 400)),
    ("broadcast_striker field (extract_regex)",
     "files/eyes/extract_regex.py",
     r"\"striker\":\s*", (300, 330)),
    ("broadcast_extra field (extract_regex)",
     "files/eyes/extract_regex.py",
     r"extras_runs", (380, 400)),
]


def find_pattern(path: pathlib.Path, pattern: str) -> list[int]:
    if not path.exists():
        return []
    rx = re.compile(pattern)
    out: list[int] = []
    with path.open() as fh:
        for i, line in enumerate(fh, start=1):
            if rx.search(line):
                out.append(i)
    return out


def main():
    print("=" * 76)
    print("S0 — SCAR-TISSUE DELETION TARGET VALIDATION")
    print("=" * 76)
    print()
    print(f"{'Target':<46} {'File':<32} {'Status'}")
    print("-" * 100)
    ok_count = 0
    drift_count = 0
    missing_count = 0
    drift_details = []
    for label, rel_path, pattern, (lo, hi) in TARGETS:
        path = ROOT / rel_path
        matches = find_pattern(path, pattern)
        if not matches:
            status = "MISSING (already deleted?)"
            missing_count += 1
        elif any(lo <= m <= hi for m in matches):
            status = f"OK (line {matches[0]})"
            ok_count += 1
        else:
            status = f"DRIFT (found at {matches[:3]}, expected {lo}-{hi})"
            drift_count += 1
            drift_details.append((label, matches, (lo, hi)))
        file_short = rel_path.replace("files/", "")
        print(f"{label:<46} {file_short:<32} {status}")
    print()
    print(f"Summary: {ok_count} OK, {drift_count} DRIFT, {missing_count} MISSING")
    print()
    if drift_details:
        print("DRIFT DETAILS — plan locations need updating:")
        for label, found, expected in drift_details:
            print(f"  {label}: found at {found}, expected lines {expected}")
        print()

    # Capture baseline assertion-library state.
    print("=" * 76)
    print("ASSERTION-LIBRARY BASELINE (per-class fail counts)")
    print("=" * 76)
    print()
    try:
        out = subprocess.check_output(
            ["python3", "files/scripts/run_symptom_assertions.py"],
            cwd=str(ROOT), stderr=subprocess.STDOUT, timeout=600,
        ).decode("utf-8", errors="replace")
    except Exception as e:
        print(f"baseline capture failed: {e}")
        return
    # Extract the global-tally block.
    in_tally = False
    baseline_rows = []
    for line in out.splitlines():
        if "Global tally:" in line:
            in_tally = True
            continue
        if in_tally:
            if line.startswith("class_"):
                parts = line.split()
                if len(parts) >= 4:
                    name = parts[0]
                    passes = int(parts[1])
                    fails = int(parts[2])
                    baseline_rows.append({"class": name, "pass": passes, "fail": fails})
            elif "Failures bucketed" in line or not line.strip():
                if baseline_rows:
                    break
    print(f"{'Class':<36} {'Pass':>6} {'Fail':>6}")
    print("-" * 50)
    for r in baseline_rows:
        print(f"{r['class']:<36} {r['pass']:>6} {r['fail']:>6}")
    print()

    out_path = pathlib.Path("/tmp/scar_tissue_baseline.jsonl")
    with out_path.open("w") as fh:
        for r in baseline_rows:
            fh.write(json.dumps(r) + "\n")
    print(f"Baseline written to {out_path}")
    print()
    print("Next: S1 — ThisOverManager backfill deletion (predicted flip:")
    print("class_7 from 3 to 0).")


if __name__ == "__main__":
    main()
