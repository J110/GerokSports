#!/usr/bin/env python3
"""Run the 12-class symptom assertion library against the
DC-vs-KKR Tier 1 fixtures via L2-style replay. Aggregates pass/fail
per assertion class per fixture; reports which symptoms reproduce.
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
from symptom_class_assertions import run_all_assertions  # noqa: E402

FIXTURES = [
    "watch_20260519_121701",
    "watch_20260514_161246",
    "watch_20260515_161437",
    "watch_20260514_171851",
    "watch_20260519_175143",
    "watch_20260519_082523",
    "watch_20260514_120538",
    "watch_20260514_105917",
]
DELIV = ROOT / "files" / "logs" / "deliveries"
LEDGER = ROOT / "files" / "tests" / "fixtures" / (
    "dc_vs_kkr_2026_152064_ledger.json")


def snapshot_ws(sm) -> dict:
    """Build a UI-payload-shaped snapshot from current SM state.

    Matches the structure the L2 harness uses; only the fields the
    assertion library reads need to be populated.
    """
    sb = getattr(sm, "scoreboard", None)
    batting_card = {}
    bowling_card = {}
    fow = []
    if sb is not None:
        try:
            batting_card = dict(sb.batting_card or {})
            bowling_card = dict(sb.bowling_card or {})
            fow = list(sb._inn.get("fow") or [])
        except Exception:
            pass
    over_history = dict(getattr(sm, "over_history", {}) or {})
    this_over = list(getattr(sm, "this_over", []) or [])
    partnership = {}
    try:
        partnership = {
            "runs": int(getattr(sm, "partnership_runs", 0) or 0),
            "balls": int(getattr(sm, "partnership_balls", 0) or 0),
        }
    except Exception:
        pass
    return {
        "score": getattr(sm, "score", None),
        "wickets": getattr(sm, "wickets", None),
        "overs": getattr(sm, "overs", None),
        "striker": getattr(sm, "striker", None),
        "non_striker": getattr(sm, "non", None),
        "this_over": this_over,
        "over_history": over_history,
        "batting_card": batting_card,
        "bowling_card": bowling_card,
        "fall_of_wickets": fow,
        "partnership_current": partnership,
    }


def ball_key(b: dict) -> tuple:
    exp = b.get("expected_state_after") or {}
    return (exp.get("score"), exp.get("wickets"), exp.get("overs"))


def overs_to_legal(v) -> int | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    w = int(f); r = round((f - w) * 10)
    return w * 6 + r if 0 <= r <= 9 else None


def sm_key(sm) -> tuple:
    overs = getattr(sm, "overs", None)
    overs_str = None
    if overs is not None:
        w = int(overs); r = round((overs - w) * 10)
        overs_str = f"{w}.{r}"
    return (
        getattr(sm, "score", None),
        getattr(sm, "wickets", None),
        overs_str,
    )


def run_fixture(session: str, ledger: dict) -> dict:
    from score_manager import ScoreManager  # noqa: F401
    from eyes.scoreboard import Scoreboard
    import test_pipeline_captured_replay as tcr
    importlib.reload(tcr)

    sm, sb = tcr.build_sm()
    p = DELIV / session / "scout_raw.jsonl"
    if not p.exists():
        return {"session": session, "error": "no_scout_raw"}

    frames = []
    for line in p.open():
        line = line.strip()
        if not line:
            continue
        try:
            frames.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    BT = "Delhi Capitals"; BO = "Kolkata Knight Riders"

    # Per-ball results: ledger_ball.ball_id → {class_name: (pass, div)}
    ball_results: dict[str, list] = {}
    prior_wickets: list[dict] = []
    last_wicket_score = 0

    prev_key = (None, None, None)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        for f in frames:
            try:
                fid = int(f["frame_id"]); ts = float(f["ts"])
            except (KeyError, ValueError, TypeError):
                continue
            extracted = parse_strip(
                f.get("raw_response", "") or "", BT, BO)
            if not extracted or not extracted.get("has_scorecard_data"):
                continue
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
            except Exception:
                continue

            cur_key = sm_key(sm)
            if cur_key == prev_key or cur_key[0] is None:
                continue
            # Try to match against any ledger ball
            matched = None
            for b in ledger["balls"]:
                if ball_key(b) == cur_key:
                    matched = b
                    break
            prev_key = cur_key
            if matched is None:
                continue

            ws = snapshot_ws(sm)
            ctx = {
                "prior_wickets": list(prior_wickets),
                "last_wicket_score": last_wicket_score,
            }
            assertions = run_all_assertions(matched, ws, context=ctx)
            ball_results[matched["ball_id"]] = assertions

            if matched.get("wicket"):
                prior_wickets.append({
                    "overs": matched["ball_id"],
                    "score": (matched.get("expected_state_after") or {})
                             .get("score"),
                    "dismissed_name": (matched.get("wicket") or {})
                                       .get("dismissed_name"),
                })
                last_wicket_score = (
                    matched.get("expected_state_after") or {}).get(
                    "score") or last_wicket_score

    # Aggregate by class
    by_class = collections.defaultdict(
        lambda: {"pass": 0, "fail": 0, "fails": []})
    for ball_id, results in ball_results.items():
        for name, ok, div in results:
            if ok:
                by_class[name]["pass"] += 1
            else:
                by_class[name]["fail"] += 1
                by_class[name]["fails"].append({
                    "ball_id": ball_id, "div": div,
                })
    return {
        "session": session,
        "matched_balls": len(ball_results),
        "by_class": {k: dict(v) for k, v in by_class.items()},
    }


def main():
    ledger = json.loads(LEDGER.read_text())

    results = []
    global_by_class: dict[str, dict] = collections.defaultdict(
        lambda: {"pass": 0, "fail": 0})
    for session in FIXTURES:
        r = run_fixture(session, ledger)
        results.append(r)
        if "error" in r:
            continue
        for cname, stats in r["by_class"].items():
            global_by_class[cname]["pass"] += stats["pass"]
            global_by_class[cname]["fail"] += stats["fail"]

    print("=" * 80)
    print("SYMPTOM-CLASS ASSERTION RESULTS (Tier 1 DC-vs-KKR fixtures)")
    print("=" * 80)
    print()
    print(f"{'fixture':<26} {'balls':>6}", end="")
    classes = sorted(global_by_class.keys())
    for c in classes:
        short = c.replace("class_", "c").replace("_", " ")[:14]
        print(f" {short:>14}", end="")
    print()
    print("-" * (32 + 15 * len(classes)))
    for r in results:
        if "error" in r:
            continue
        print(f"{r['session']:<26} {r['matched_balls']:>6}", end="")
        for c in classes:
            stats = r["by_class"].get(c, {"pass": 0, "fail": 0})
            p = stats["pass"]; f = stats["fail"]
            cell = f"{p}P/{f}F"
            print(f" {cell:>14}", end="")
        print()
    print()
    print("Global tally:")
    print(f"{'class':<35} {'pass':>6} {'fail':>6} {'fail %':>8}")
    print("-" * 60)
    for c in classes:
        s = global_by_class[c]
        tot = s["pass"] + s["fail"]
        pct = (100 * s["fail"] / tot) if tot else 0.0
        print(f"{c:<35} {s['pass']:>6} {s['fail']:>6} {pct:>7.1f}%")
    print()
    print("Top failing classes (first 3 divergences each):")
    print("-" * 60)
    for c in sorted(classes,
                    key=lambda k: -global_by_class[k]["fail"])[:6]:
        s = global_by_class[c]
        if s["fail"] == 0:
            continue
        print(f"\n[{c}]  ({s['fail']} fails)")
        shown = 0
        for r in results:
            if "error" in r or shown >= 3:
                continue
            for fail in r["by_class"].get(c, {}).get("fails", [])[:3]:
                if shown >= 3:
                    break
                print(f"  {r['session']} ball={fail['ball_id']}: "
                      f"{fail['div']}")
                shown += 1


if __name__ == "__main__":
    main()
