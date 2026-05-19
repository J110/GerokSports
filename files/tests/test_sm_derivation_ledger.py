"""SM derivation ledger replay harness — Phase 1 of derive-not-detect.

Drives ``ScoreManager`` through a deterministic ball-by-ball ledger and
asserts SM's derived state matches ground truth after each commit.
Catches the silent-skip bug classes (NO-SCOREBOARD, striker dispatch,
archive timing, partnership) that historically required full pipeline
replays to surface.

Usage:
    python files/tests/test_sm_derivation_ledger.py
    python files/tests/test_sm_derivation_ledger.py --start-at-ball 0.3
    pytest files/tests/test_sm_derivation_ledger.py -v

Ledger: files/tests/fixtures/dc_vs_kkr_2026_152064_ledger.json (Phase 0).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FILES_DIR))

from score_manager import ScoreManager, FrameInput  # noqa: E402
from eyes.scoreboard import Scoreboard  # noqa: E402

DEFAULT_LEDGER = (
    FILES_DIR / "tests" / "fixtures"
    / "dc_vs_kkr_2026_152064_ledger.json")

BATTING_TEAM = "DC"
BOWLING_TEAM = "KKR"
BATTING_SQUAD = [
    "Pathum Nissanka", "KL Rahul", "Nitish Rana",
    "Tristan Stubbs", "Axar Patel", "Abishek Porel",
    "Kuldeep Yadav", "Mukesh Kumar", "Ishant Sharma",
    "T Natarajan", "Mohit Sharma",
]
BOWLING_SQUAD = [
    "Anukul Roy", "Vaibhav Arora", "Sunil Narine", "Kartik Tyagi",
    "Andre Russell", "Varun Chakaravarthy", "Cameron Green",
    "Venkatesh Iyer", "Rinku Singh", "Quinton de Kock",
    "Ajinkya Rahane",
]

# Fields where order is semantically irrelevant (compare as sorted lists).
_ORDER_INSENSITIVE_PATHS = frozenset({
    "partnership.batters",
})


def load_ledger(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def build_sm() -> tuple[ScoreManager, Scoreboard]:
    sb = Scoreboard()
    sb.setup_innings(
        batting_team=BATTING_TEAM,
        bowling_team=BOWLING_TEAM,
        batting_squad=BATTING_SQUAD,
        bowling_squad=BOWLING_SQUAD,
        batting_xi=BATTING_SQUAD[:11],
        bowling_xi=BOWLING_SQUAD[:11],
    )
    # Pre-promote the opening pair to status="batting" so SM sees them
    # at the crease from frame 1. In the live pipeline this happens via
    # broadcast/strip reads that bump the status; in the harness we wire
    # it directly since synthetic FrameInputs don't drive the same path.
    for opener in (BATTING_SQUAD[0], BATTING_SQUAD[1]):
        slot = sb.batting_card.get(opener)
        if slot is not None:
            slot["status"] = "batting"
            slot["runs"] = 0
            slot["balls"] = 0
            slot["fours"] = 0
            slot["sixes"] = 0

    sm = ScoreManager(shadow=False)
    sm.scoreboard = sb
    return sm, sb


def _overs_to_float(overs_str: str) -> float:
    o, b = overs_str.split(".")
    return float(o) + float(b) / 10.0


def synthesize_frame_input(ball: dict, ts: float) -> FrameInput:
    """Build a FrameInput representing the extractor's view AFTER the ball."""
    exp = ball["expected_state_after"]
    bowling = exp["bowling_card"][ball["bowler_name"]]
    striker = exp["striker_after_rotation"]
    non = exp["non_striker_after_rotation"]
    striker_card = exp["batting_card"].get(striker, {})
    non_card = exp["batting_card"].get(non, {})

    return FrameInput(
        frame_id=ball["ball_id"],
        timestamp=ts,
        ext_score=exp["score"],
        ext_wickets=exp["wickets"],
        ext_overs=_overs_to_float(exp["overs"]),
        ext_bat1_name=striker,
        ext_bat1_runs=striker_card.get("runs"),
        ext_bat1_balls=striker_card.get("balls_faced"),
        ext_bat2_name=non,
        ext_bat2_runs=non_card.get("runs"),
        ext_bat2_balls=non_card.get("balls_faced"),
        ext_bowler_name=ball["bowler_name"],
        ext_bowler_wickets=bowling["wickets"],
        ext_bowler_runs=bowling["runs"],
        ext_bowler_overs=_overs_to_float(bowling["overs"]),
        broadcast_striker=striker,
        broadcast_this_over=list(exp["this_over"]),
        broadcast_team=BATTING_TEAM,
        scout_text=(
            f"{BATTING_TEAM} {exp['score']}-{exp['wickets']} "
            f"({exp['overs']})"),
    )


def _bowling_card_entry(c: dict) -> dict:
    ovr = c.get("overs")
    balls = c.get("balls")
    if balls is None and ovr is not None:
        try:
            o, b = str(ovr).split(".")
            balls = int(o) * 6 + int(b)
        except (ValueError, TypeError):
            balls = 0
    return {
        "overs": str(ovr) if ovr is not None else None,
        "balls": balls,
        "runs": c.get("runs"),
        "wickets": c.get("wickets"),
        "maidens": c.get("maidens") or 0,
    }


def _batting_card_entry(c: dict) -> dict:
    entry = {
        "runs": c.get("runs"),
        "balls_faced": c.get("balls"),
        "fours": c.get("fours") or 0,
        "sixes": c.get("sixes") or 0,
        "status": c.get("status"),
    }
    if c.get("status") == "out":
        for k_ledger, k_sb in (
            ("dismissal_overs", "dismissal_overs"),
            ("dismissal_runs", "dismissal_runs"),
            ("dismissal_balls_faced", "dismissal_balls"),
            ("dismissal_type", "dismissal_type"),
            ("dismissal_by", "dismissal_bowler"),
            ("dismissal_fielder", "dismissal_fielder"),
        ):
            v = c.get(k_sb)
            if v is not None:
                entry[k_ledger] = v
    return entry


def snapshot_state(sm: ScoreManager, sb: Scoreboard) -> dict:
    """Pull SM/SB state into a dict matching the ledger's
    expected_state_after schema."""
    bat_card = {}
    for name, c in (sb.batting_card or {}).items():
        # Only surface batters who have actually started batting or are out.
        # `yet_to_bat` / `did_not_bat` slots are auto-populated for the
        # full XI but never appear in the ledger's expected_state_after.
        if c.get("status") not in ("batting", "out"):
            continue
        bat_card[name] = _batting_card_entry(c)

    bowl_card = {}
    for name, c in (sb.bowling_card or {}).items():
        # Only surface bowlers who have actually bowled at least one ball.
        # The full bowling XI is auto-populated by setup_innings but
        # never appears in the ledger's expected_state_after.
        entry = _bowling_card_entry(c)
        if (entry.get("balls") or 0) == 0 and entry.get("runs") in (None, 0) \
                and entry.get("wickets") in (None, 0):
            continue
        bowl_card[name] = entry

    partnership_batters: list[str] = []
    if sm.striker:
        partnership_batters.append(sm.striker)
    if sm.non:
        partnership_batters.append(sm.non)

    return {
        "score": sm.score,
        "wickets": sm.wickets,
        "overs": str(sm.overs) if sm.overs is not None else None,
        "striker_after_rotation": sm.striker,
        "non_striker_after_rotation": sm.non,
        "partnership": {
            "runs": getattr(sm, "partnership_runs", None),
            "balls": getattr(sm, "partnership_balls", None),
            "batters": partnership_batters,
        },
        "bowling_card": bowl_card,
        "batting_card": bat_card,
        "this_over": list(sm.this_over or []),
        "over_history": {
            str(k): list(v) for k, v in (sm.over_history or {}).items()},
    }


def diff(expected, actual, path: str = "") -> list[tuple[str, object, object]]:
    """Return ordered list of (path, expected, actual) for divergent fields."""
    divs: list[tuple[str, object, object]] = []
    if isinstance(expected, dict) and isinstance(actual, dict):
        keys = sorted(set(expected.keys()) | set(actual.keys()))
        for k in keys:
            sub = f"{path}.{k}" if path else k
            if k not in expected:
                divs.append((sub, "<MISSING>", actual[k]))
            elif k not in actual:
                divs.append((sub, expected[k], "<MISSING>"))
            else:
                divs.extend(diff(expected[k], actual[k], sub))
    elif isinstance(expected, list) and isinstance(actual, list):
        if path in _ORDER_INSENSITIVE_PATHS:
            if sorted(expected) != sorted(actual):
                divs.append((path, expected, actual))
        else:
            if len(expected) != len(actual):
                divs.append((f"{path}.len", len(expected), len(actual)))
            for i, (e, a) in enumerate(zip(expected, actual)):
                divs.extend(diff(e, a, f"{path}[{i}]"))
    else:
        if expected != actual:
            divs.append((path, expected, actual))
    return divs


def run_harness(
    ledger_path: Path,
    start_at_ball: str | None = None,
) -> int:
    ledger = load_ledger(ledger_path)
    sm, sb = build_sm()
    ts = time.time()
    asserting = start_at_ball is None

    # Cold-start needs multiple consensus frames before it commits. Feed
    # each ball's frame up to COLD_START_FEED_MAX times until SM leaves
    # COLD_START; once warm, exactly one frame per ball.
    COLD_START_FEED_MAX = 5

    for ball in ledger["balls"]:
        ball_id = ball["ball_id"]
        if start_at_ball and ball_id == start_at_ball:
            asserting = True

        frame = synthesize_frame_input(ball, ts)
        ts += 1.0
        feed_count = 0
        max_feeds = (
            COLD_START_FEED_MAX
            if getattr(sm, "mode", None) == "COLD_START" else 1)
        try:
            while feed_count < max_feeds:
                # Simulate the extractor's prior writes into scoreboard so
                # SM's score/wickets/overs getters (which read from
                # scoreboard._inn under the Path-B refactor) see the
                # current values. In production these writes come from
                # Scout/Extractor before SM.on_frame.
                _frame_int = int(time.time() * 1000) + feed_count
                try:
                    sb.set("score", frame.ext_score, frame=_frame_int)
                    sb.set("wickets", frame.ext_wickets, frame=_frame_int)
                    sb.set("overs", frame.ext_overs, frame=_frame_int)
                except Exception:
                    pass
                sm.on_frame(frame)
                feed_count += 1
                if getattr(sm, "mode", None) != "COLD_START":
                    break
        except Exception as e:
            print(f"FAIL at ball {ball_id}: on_frame raised "
                  f"{type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return 1

        if not asserting:
            print(f"SKIP {ball_id} (warmup, --start-at-ball="
                  f"{start_at_ball})")
            continue

        actual = snapshot_state(sm, sb)
        expected = ball["expected_state_after"]
        divergences = diff(expected, actual)
        if divergences:
            first = divergences[0]
            print(f"FAIL at ball {ball_id} ({ball['event_type']}): "
                  f"first divergent field {first[0]!r}")
            print(f"  expected: {first[1]!r}")
            print(f"  actual:   {first[2]!r}")
            if len(divergences) > 1:
                print(f"  ({len(divergences) - 1} additional divergences "
                      f"this ball — see full diff below)")
                for d in divergences[1:11]:
                    print(f"    {d[0]!r}: expected={d[1]!r} actual={d[2]!r}")
                if len(divergences) > 11:
                    print(f"    ... ({len(divergences) - 11} more)")
            return 1

        print(f"PASS {ball_id} ({ball['event_type']})")

    print(f"\nPASS — all {len(ledger['balls'])} balls match ground truth")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ledger", default=str(DEFAULT_LEDGER),
                   help="ledger JSON path")
    p.add_argument("--start-at-ball", default=None,
                   help="skip assertions until this ball_id (warmup window)")
    args = p.parse_args(argv)
    return run_harness(Path(args.ledger), args.start_at_ball)


def test_sm_derivation_ledger_passes_through_5_6() -> None:
    """pytest entry — harness must pass through ball 5.6."""
    rc = run_harness(DEFAULT_LEDGER, start_at_ball=None)
    assert rc == 0, (
        "SM derivation diverged from ground truth ledger; "
        "see stdout for first divergent field.")


if __name__ == "__main__":
    sys.exit(main())
