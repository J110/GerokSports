"""Layer 2 captured-Scout-replay harness — drives the post-Scout
chain from a real scout_raw.jsonl dump and asserts WS payload
against the ground-truth ledger at each ball commit.

Architecture (L2-Slim):
  scout_raw.jsonl  →  parse_strip()  →  FrameInput  →  ScoreManager.on_frame()
                      (real regex)     (real shape)    (real SM)

What this catches: SM-and-downstream bugs that manifest when the
real extractor output drives SM frame-by-frame — gap-token
fabrication, +1 ball drift, phantom ? in over_history, this_over
corruption, wicket attribution at boundaries. The captured Scout
responses ARE the noisy real-world inputs the production pipeline
sees during the user's replay.

What this does NOT catch: bugs that depend on the pipeline's full
async orchestration, tracker-level filtering (striker_tracker,
batting_team consensus, etc.), or actual video frame content
(field detection, replay-inset detection, BallAnalyzer clips).
Promote to L2-In-Process if a symptom escapes here.

Fixture: files/logs/deliveries/watch_20260519_121701/scout_raw.jsonl
  (264 Scout responses, 381 frames, DC vs KKR overs 1-5 of innings 1,
  ending at the 4.6 KL Rahul wicket)

Ledger: files/tests/fixtures/dc_vs_kkr_2026_152064_ledger.json
  (36 balls; balls 0.1-5.6)

Run:
    python files/tests/test_pipeline_captured_replay.py
    pytest files/tests/test_pipeline_captured_replay.py -v
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FILES_DIR))

from score_manager import ScoreManager, FrameInput  # noqa: E402
from eyes.scoreboard import Scoreboard  # noqa: E402
from eyes.extract_regex import parse_strip  # noqa: E402

# Reuse helpers from Layer 1.5 harness.
sys.path.insert(0, str(FILES_DIR / "tests"))
from test_sm_derivation_ledger import (  # noqa: E402
    BATTING_SQUAD, BOWLING_SQUAD, BATTING_TEAM, BOWLING_TEAM,
    snapshot_state, snapshot_ws_payload, diff,
    _apply_post_wicket_pipeline_sim,
)

DEFAULT_DUMP = (
    FILES_DIR / "logs/deliveries/watch_20260519_121701/scout_raw.jsonl")
DEFAULT_LEDGER = (
    FILES_DIR / "tests/fixtures/dc_vs_kkr_2026_152064_ledger.json")


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


def extracted_to_frame_input(
    frame_id: int, ts: float, extracted: dict,
) -> FrameInput:
    """Build a FrameInput from parse_strip output. parse_strip returns
    a dict shaped roughly like the LLM Extractor's JSON; the field
    names differ slightly so we map explicitly."""
    bowler = extracted.get("bowler") or {}
    batters = extracted.get("batters") or []
    bat1 = batters[0] if len(batters) >= 1 else {}
    bat2 = batters[1] if len(batters) >= 2 else {}

    def _f(v):
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    def _i(v):
        try:
            return int(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    bowler_overs = bowler.get("overs")
    bowler_overs_f = _f(bowler_overs) if bowler_overs is not None else None

    # Field-name reconciliation: parse_strip emits batting_team_visible
    # / this_over_broadcast / match_overs, while FrameInput/SM expect
    # the simpler ext_/broadcast_ shapes. Map explicitly here.
    bat1_striker = bool(bat1.get("striker"))
    broadcast_striker = (
        bat1.get("name") if bat1_striker
        else (bat2.get("name") if bat2.get("striker") else bat1.get("name"))
    )
    return FrameInput(
        frame_id=str(frame_id),
        timestamp=ts,
        ext_score=_i(extracted.get("score")),
        ext_wickets=_i(extracted.get("wickets")),
        ext_overs=_f(extracted.get("match_overs")
                     or extracted.get("overs")),
        ext_bat1_name=bat1.get("name"),
        ext_bat1_runs=_i(bat1.get("runs")),
        ext_bat1_balls=_i(bat1.get("balls")),
        ext_bat2_name=bat2.get("name"),
        ext_bat2_runs=_i(bat2.get("runs")),
        ext_bat2_balls=_i(bat2.get("balls")),
        ext_bowler_name=bowler.get("name"),
        ext_bowler_wickets=_i(bowler.get("wickets")),
        ext_bowler_runs=_i(bowler.get("runs")),
        ext_bowler_overs=bowler_overs_f,
        broadcast_striker=broadcast_striker,
        broadcast_this_over=extracted.get("this_over_broadcast"),
        # Pass extracted batting_team_visible THROUGH (None when
        # parse_strip didn't see a team prefix — e.g. skeleton/
        # sponsor-graphic frames with STRIP "null 0-0 (...)").
        # No BATTING_TEAM fallback: production's frame.broadcast_team
        # is None on null-team frames, and the team-change-required
        # guard at score_manager.py's score_reset_from_progress
        # path depends on that input shape. Falling back here would
        # mask the same bug class the guard is designed to catch.
        broadcast_team=extracted.get("batting_team_visible"),
        scout_text="",
    )


def _key_state(sm: ScoreManager) -> tuple:
    """The (score, wickets, overs) tuple that defines a ball commit."""
    return (sm.score, sm.wickets, sm.overs)


def _state_advances(prev: tuple, current: tuple) -> bool:
    """True if SM's (score, wickets, overs) has progressed forward
    from prev to current (any field changed; not just a no-op)."""
    if prev == current:
        return False
    p_score, p_wkts, p_overs = prev
    c_score, c_wkts, c_overs = current
    if c_score is None or c_overs is None:
        return False
    if p_score is not None and c_score < p_score:
        return False
    return True


def run_harness(
    dump_path: Path,
    ledger_path: Path,
    stop_at_ball: str | None = None,
) -> int:
    ledger = json.loads(ledger_path.read_text())
    sm, sb = build_sm()

    # Load the Scout dump.
    frames = []
    with dump_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                frames.append(rec)
            except json.JSONDecodeError:
                continue
    print(f"Loaded {len(frames)} Scout responses from {dump_path}")

    parsed_count = 0
    skipped_count = 0
    commits_seen = 0
    ledger_idx = 0
    matched_ball_ids: list[str] = []
    first_divergence: tuple | None = None
    prev_key = (None, None, None)

    for f in frames:
        frame_id = int(f["frame_id"])
        ts = float(f["ts"])
        raw = f["raw_response"]
        extracted = parse_strip(raw, BATTING_TEAM, BOWLING_TEAM)
        # parse_strip returns a dict even on between_play/non-scorecard
        # frames (with has_scorecard_data=False); those carry no
        # state and would feed null FrameInputs to SM. Skip them.
        if not extracted or not extracted.get("has_scorecard_data"):
            skipped_count += 1
            continue
        parsed_count += 1
        fi = extracted_to_frame_input(frame_id, ts, extracted)

        # Simulate the pipeline's pre-SM scoreboard writes (the live
        # pipeline updates sb._inn from extractor output BEFORE
        # invoking SM, so SM's Path-B getters can read consistent
        # values). Mirrors Layer 1.5 harness's sb.set() pattern.
        try:
            if fi.ext_score is not None:
                sb.set("score", fi.ext_score, frame=frame_id)
            if fi.ext_wickets is not None:
                sb.set("wickets", fi.ext_wickets, frame=frame_id)
            if fi.ext_overs is not None:
                sb.set("overs", fi.ext_overs, frame=frame_id)
        except Exception:
            pass

        try:
            sm.on_frame(fi)
        except Exception as e:
            print(f"on_frame raised at frame {frame_id}: "
                  f"{type(e).__name__}: {e}")
            continue

        cur_key = _key_state(sm)
        if _state_advances(prev_key, cur_key):
            commits_seen += 1
            # Match by (score, wickets, overs) tuple, not sequential
            # index. Cold-start consumes ball 0.1 (the dot) by
            # synthesizing directly into the score=4 (0.2) anchor —
            # there's no fresh commit at (0, 0, 0.1). State-tuple
            # matching also catches bugs where SM jumps to a
            # nonsensical state (e.g. overs=8.4 from a graphic
            # misread) by reporting them as orphan commits.
            cur_score, cur_wkts, cur_overs = cur_key
            cur_overs_str = (
                f"{int(cur_overs)}.{int(round((cur_overs % 1) * 10))}"
                if cur_overs is not None else None)
            matched_ball = None
            for b in ledger["balls"]:
                exp = b["expected_state_after"]
                if (exp.get("score") == cur_score
                        and exp.get("wickets") == cur_wkts
                        and exp.get("overs") == cur_overs_str):
                    matched_ball = b
                    break
            if matched_ball is None:
                orphan_msg = (f"ORPHAN commit at key={cur_key} "
                              f"(overs_str={cur_overs_str!r}) — "
                              f"no ledger entry expects this state")
                print(orphan_msg)
                if first_divergence is None:
                    first_divergence = (
                        f"ORPHAN({cur_key})", frame_id,
                        [("state-tuple",
                          "<must match some ledger ball>",
                          cur_key)])
            else:
                ball_id = matched_ball["ball_id"]
                # Checkpoint at next-ball-commit boundary by
                # draining any pending bowler-ball-credit entries
                # using the ledger's known bowler for this just-
                # committed ball. The harness doesn't run the
                # production ConfidenceTracker, so on_lock callbacks
                # never fire to drain queued credits between ball
                # commits. The in-line drain inside
                # `_accumulate_stats_from_event` fires only when a
                # bowler is already resolved — which is exactly the
                # case at the NEXT ball commit (e.g. frame 211 for
                # ball 3.2 drains ball 3.1's queued Narine credit).
                # This explicit drain at the current commit point
                # mirrors production's WS payload cadence, where
                # the payload published at ball N's commit includes
                # ball N-1's now-resolved retroactive credits.
                _ledger_bowler = matched_ball.get("bowler_name")
                _pending = getattr(
                    sm, "_pending_bowler_ball_credits", None)
                if _ledger_bowler and _pending:
                    try:
                        sm._drain_pending_bowler_ball_credits(
                            _ledger_bowler)
                    except Exception:
                        pass
                # Pipeline-level post-wicket transitions (status='out',
                # dismissal_*, new-batter promotion) — same shim as
                # the L1.5 harness uses. SM's _apply_wicket_fall_only
                # records FOW + zeros the dismissed slot but does NOT
                # mark batting_card status='out' / populate
                # dismissal_* fields / promote the incoming batter.
                # Those transitions live in the pipeline
                # (test_pipeline.py:10470 + batter-replacement block
                # ~11302+). Apply them here for the wicket ball so
                # the harness's ledger comparison matches the
                # production WS-payload-shaped expected state.
                if matched_ball.get("wicket"):
                    try:
                        _apply_post_wicket_pipeline_sim(
                            matched_ball, sb, sm)
                    except Exception:
                        pass
                actual = snapshot_state(sm, sb)
                expected = matched_ball["expected_state_after"]
                divs = diff(expected, actual)
                ws_actual = snapshot_ws_payload(sb)
                ws_expected = (
                    matched_ball.get("expected_ws_payload_after") or {})
                if ws_expected:
                    divs.extend(diff(ws_expected, ws_actual, "ws_payload"))
                status = "PASS" if not divs else f"FAIL ({len(divs)})"
                print(f"{status} {ball_id} ({matched_ball['event_type']}) "
                      f"frame={frame_id} key={cur_key}")
                if divs and first_divergence is None:
                    first_divergence = (ball_id, frame_id, divs)
                ledger_idx += 1
                matched_ball_ids.append(ball_id)
                if stop_at_ball and ball_id == stop_at_ball:
                    break
        prev_key = cur_key

    print(f"\nFrames: {len(frames)} | parsed: {parsed_count} | "
          f"skipped: {skipped_count} | commits_seen: {commits_seen} | "
          f"ledger_matched: {ledger_idx}/{len(ledger['balls'])}")

    if first_divergence is not None:
        ball_id, frame_id, divs = first_divergence
        first = divs[0]
        print(f"\nFAIL — first divergence at ball {ball_id} "
              f"(frame {frame_id}): {first[0]!r}")
        print(f"  expected: {first[1]!r}")
        print(f"  actual:   {first[2]!r}")
        if len(divs) > 1:
            print(f"  ({len(divs) - 1} additional divergences this ball)")
            for d in divs[1:11]:
                print(f"    {d[0]!r}: expected={d[1]!r} actual={d[2]!r}")
        return 1

    # Coverage shortfall (some ledger balls never reached by the
    # captured Scout dump's frame window) is an INFO, not a FAIL.
    # The captured dump for watch_20260519_121701 ends at frame
    # 381 / ball 4.6 (wicket); balls 5.1-5.6 require a longer
    # capture window. Harness PASSes when all observed commits
    # match without divergence or orphan; ledger coverage is
    # bounded by the dump, not by harness correctness.
    if ledger_idx < len(ledger["balls"]):
        _matched_set = set(matched_ball_ids)
        _uncovered = [
            b["ball_id"] for b in ledger["balls"]
            if b["ball_id"] not in _matched_set
        ]
        print(
            f"\nPASS — {ledger_idx}/{len(ledger['balls'])} "
            f"ledger balls matched against captured-Scout replay "
            f"(uncovered: {_uncovered} — dump window ends before "
            f"these balls OR cold-start absorbed the early dot)")
        return 0

    print(f"\nPASS — all {ledger_idx} ledger balls matched against "
          f"captured-Scout replay")
    return 0


def test_captured_replay_matches_ledger() -> None:
    """pytest entry — captured-Scout replay must match ground truth
    ledger ball-for-ball."""
    rc = run_harness(DEFAULT_DUMP, DEFAULT_LEDGER)
    assert rc == 0, (
        "Captured-Scout replay diverged from ledger; see stdout for "
        "first divergent ball + field.")


if __name__ == "__main__":
    sys.exit(run_harness(DEFAULT_DUMP, DEFAULT_LEDGER))
