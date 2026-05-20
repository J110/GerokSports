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
    ScoutResponseClass, ScoutStatus,
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
            # Simulate the dispatch + response that Vision.describe would
            # do in production. Cached responses are RESPONDED by
            # definition; classify based on parse_strip's frame_type.
            get_ledger().record_dispatch(fid)
            extracted = parse_strip(
                rec.get("raw_response", "") or "", team_a, team_b,
                frame_id=fid)
            if not extracted:
                parse_strip_results["parse_None"] += 1
                get_ledger().record_scout_response(
                    fid, ScoutResponseClass.OTHER,
                    status=ScoutStatus.RESPONDED)
                continue
            # Map parse_strip's frame_type → ScoutResponseClass
            ft = (extracted.get("frame_type") or "").lower()
            rc = {
                "scoreboard": ScoutResponseClass.SCOREBOARD,
                "graphic":    ScoutResponseClass.GRAPHIC,
                "closeup":    ScoutResponseClass.OTHER,
                "ad":         ScoutResponseClass.OTHER,
            }.get(ft, ScoutResponseClass.OTHER)
            # parse_strip already may have stamped DEGENERATE_NULL via
            # frame_id; don't overwrite if so.
            existing = get_ledger().get(fid)
            if existing and existing.scout_response_class is None:
                get_ledger().record_scout_response(
                    fid, rc, status=ScoutStatus.RESPONDED)
            else:
                # Just mark RESPONDED without overwriting class
                if existing is not None:
                    existing.scout_status = ScoutStatus.RESPONDED
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
    by_scout_status = collections.Counter(
        e.scout_status.value for e in entries)
    by_response_class = collections.Counter(
        e.scout_response_class.value if e.scout_response_class else "NONE"
        for e in entries)
    by_extractor = collections.Counter(
        e.extractor_outcome.value if e.extractor_outcome else "NONE"
        for e in entries)
    raw_path = DELIV / session / "scout_raw.jsonl"
    expected = 0
    if raw_path.exists():
        with raw_path.open() as fh:
            expected = sum(1 for line in fh if line.strip())
    silent_drops = get_ledger().compute_silent_drops(expected)
    return {
        "session": session,
        "frames_processed": frames_processed,
        "expected_frame_count": expected,
        "silent_drops": silent_drops,
        "by_scout_status": dict(by_scout_status),
        "by_response_class": dict(by_response_class),
        "by_extractor": dict(by_extractor),
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

    # Aggregate scout-side telemetry (Stage 2d additions)
    print("Global scout_status distribution:")
    by_scout_status_global = collections.Counter()
    by_response_class_global = collections.Counter()
    by_extractor_global = collections.Counter()
    silent_drops_total = 0
    expected_total = 0
    for r in results:
        if "error" in r:
            continue
        for k, v in r.get("by_scout_status", {}).items():
            by_scout_status_global[k] += v
        for k, v in r.get("by_response_class", {}).items():
            by_response_class_global[k] += v
        for k, v in r.get("by_extractor", {}).items():
            by_extractor_global[k] += v
        silent_drops_total += r.get("silent_drops", 0)
        expected_total += r.get("expected_frame_count", 0)
    for k, v in by_scout_status_global.most_common():
        print(f"  {k:<32} {v:>6}")
    print()
    print("Global scout_response_class distribution:")
    for k, v in by_response_class_global.most_common():
        print(f"  {k:<32} {v:>6}")
    print()
    print("Global extractor_outcome distribution:")
    for k, v in by_extractor_global.most_common():
        print(f"  {k:<32} {v:>6}")
    print()
    print(f"SILENT DROPS (Mode 1): "
          f"{silent_drops_total} of {expected_total} expected frames "
          f"({100*silent_drops_total/expected_total:.2f}%)" if expected_total else
          f"SILENT DROPS: {silent_drops_total}")
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
