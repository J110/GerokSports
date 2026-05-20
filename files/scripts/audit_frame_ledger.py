#!/usr/bin/env python3
"""Stage 2c validation — drive 9 Tier-1 fixtures through SM with the
Frame Fate Ledger active, aggregate entries by sm_outcome, report
per-fixture + global distribution.

Confirms wiring coverage: every frame that reaches SM should produce
a known sm_outcome (no NOT_YET_SEEN leakage means wiring is complete).
"""
from __future__ import annotations

import collections
import contextlib
import importlib
import io
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "files"))
sys.path.insert(0, str(ROOT / "files" / "tests"))

from eyes.extract_regex import parse_strip  # noqa: E402
from eyes.frame_ledger import (  # noqa: E402
    get_ledger, reset_ledger, SmOutcome,
)

FIXTURES = [
    ("watch_20260519_121701", "DC vs KKR"),
    ("watch_20260514_161246", "DC vs KKR"),
    ("watch_20260515_161437", "DC vs KKR"),
    ("watch_20260514_171851", "DC vs KKR"),
    ("watch_20260519_175143", "DC vs KKR"),
    ("watch_20260519_082523", "DC vs KKR"),
    ("watch_20260514_120538", "DC vs KKR"),
    ("watch_20260514_105917", "DC vs KKR"),
    ("8a0c6c14",              "GT vs RR"),
]
DELIV = ROOT / "files" / "logs" / "deliveries"


def run_fixture(session: str, team_a: str, team_b: str) -> dict:
    from score_manager import ScoreManager
    from eyes.scoreboard import Scoreboard
    import test_pipeline_captured_replay as tcr
    importlib.reload(tcr)

    reset_ledger()
    sb = Scoreboard()
    sb.setup_innings(
        batting_team=team_a, bowling_team=team_b,
        batting_squad=["P"+str(i) for i in range(15)],
        bowling_squad=["B"+str(i) for i in range(15)],
        batting_xi=None, bowling_xi=None,
    )
    sm = ScoreManager(shadow=False)
    sm.scoreboard = sb

    p = DELIV / session / "scout_raw.jsonl"
    if not p.exists():
        return {"session": session, "error": "no_scout_raw"}
    frames_processed = 0
    parse_strip_results = collections.Counter()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        for line in p.open():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                fid = int(rec["frame_id"])
                ts = float(rec["ts"])
            except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                continue
            extracted = parse_strip(
                rec.get("raw_response", "") or "", team_a, team_b)
            if not extracted:
                parse_strip_results["parse_None"] += 1
                continue
            if not extracted.get("has_scorecard_data"):
                parse_strip_results["no_scorecard_data"] += 1
                continue
            parse_strip_results["parsed_ok"] += 1
            try:
                fi = tcr.extracted_to_frame_input(fid, ts, extracted)
            except Exception:
                continue
            try:
                if fi.ext_score is not None:
                    sb.set("score", fi.ext_score, frame=fid)
                if fi.ext_wickets is not None:
                    sb.set("wickets", fi.ext_wickets, frame=fid)
                if fi.ext_overs is not None:
                    sb.set("overs", fi.ext_overs, frame=fid)
            except Exception:
                pass
            try:
                sm.on_frame(fi)
                frames_processed += 1
            except Exception:
                continue

    entries = get_ledger().all_entries()
    by_outcome = collections.Counter(e.sm_outcome.value for e in entries)
    return {
        "session": session,
        "frames_processed": frames_processed,
        "parse_strip": dict(parse_strip_results),
        "ledger_total": len(entries),
        "by_outcome": dict(by_outcome),
        "sample_rejections": [
            {"frame_id": e.frame_id, "outcome": e.sm_outcome.value,
             "payload": e.rejection_payload}
            for e in entries
            if e.sm_outcome.value.startswith("REJECTED_")
        ][:8],
    }


def main():
    results = []
    global_by_outcome = collections.Counter()
    global_processed = 0
    global_ledger = 0
    for sess, label in FIXTURES:
        team_a, team_b = (
            ("Delhi Capitals", "Kolkata Knight Riders")
            if "DC" in label
            else ("Gujarat Titans", "Rajasthan Royals"))
        r = run_fixture(sess, team_a, team_b)
        results.append(r)
        if "error" in r:
            continue
        for o, c in r["by_outcome"].items():
            global_by_outcome[o] += c
        global_processed += r["frames_processed"]
        global_ledger += r["ledger_total"]

    print("=" * 80)
    print("STAGE 2c — FRAME FATE LEDGER VALIDATION (9 fixtures)")
    print("=" * 80)
    print()
    print(f"{'session':<26} {'on_frame':>9} {'ledger':>7} "
          f"{'commits':>8} {'rejects':>8} {'noop_null':>10}")
    print("-" * 80)
    for r in results:
        if "error" in r:
            print(f"{r['session']:<26} SKIP ({r['error']})")
            continue
        by = r["by_outcome"]
        commits = by.get("ACCEPTED_COMMIT", 0)
        rejects = sum(c for o, c in by.items()
                      if o.startswith("REJECTED_"))
        noop_null = by.get("ACCEPTED_NOOP_NULL_OVERS", 0)
        print(f"{r['session']:<26} {r['frames_processed']:>9} "
              f"{r['ledger_total']:>7} {commits:>8} "
              f"{rejects:>8} {noop_null:>10}")
    print(f"{'TOTAL':<26} {global_processed:>9} {global_ledger:>7}")
    print()

    print("Global sm_outcome distribution:")
    total = sum(global_by_outcome.values()) or 1
    for outcome, c in global_by_outcome.most_common():
        print(f"  {outcome:<32} {c:>6} ({100*c/total:>5.1f}%)")
    print()

    # Wiring-coverage check
    not_yet_seen = global_by_outcome.get("NOT_YET_SEEN", 0)
    print(f"WIRING COVERAGE: {not_yet_seen} frames with NOT_YET_SEEN "
          f"(should be 0 if wiring is complete; >0 = "
          f"frames reaching SM without a recorded outcome)")
    print()

    print("Per-fixture rejection samples (first 3 rejections per fixture):")
    for r in results:
        if "error" in r:
            continue
        if not r.get("sample_rejections"):
            continue
        print(f"  {r['session']}:")
        for s in r["sample_rejections"][:3]:
            print(f"    frame={s['frame_id']:>4} "
                  f"outcome={s['outcome']:<32} "
                  f"payload={s.get('payload')}")


if __name__ == "__main__":
    main()
