"""
Test suite for Fix A + Fix B: innings-2 end detection + match_complete.

Test cases (per user spec):
  1. Normal innings 2 ending at target (target_reached)
  2. Normal innings 2 ending at 10 wickets (all_out)
  3. Normal innings 2 ending at 20 overs (overs_exhausted)
  4. Transient misread: single-frame wickets flicker must NOT fire

Additionally:
  5. finalize_match is idempotent
  6. set_innings_2 post-finalize is refused
  7. start_new_innings post-finalize is refused
  8. Match result margin computation (wickets / runs)

Run: python3 test_match_complete.py
"""

import sys
from eyes.scoreboard import Scoreboard


def make_scoreboard_in_innings_2(
    target: int = 160,
    score: int = 0,
    wickets: int = 0,
    overs: str = "0.0",
    batting: str = "Lucknow Super Giants",
    bowling: str = "Rajasthan Royals",
) -> Scoreboard:
    """Construct a Scoreboard primed into a specific innings-2 state."""
    sb = Scoreboard()
    sb.batting_team = batting
    sb.bowling_team = bowling
    sb.current_innings = 2
    sb.innings[2] = {
        "score": score,
        "wickets": wickets,
        "overs": overs,
        "target": target,
        "batting_team": batting,
        "bowling_team": bowling,
        "striker": None,
        "non": None,
        "current_bowler": None,
        "run_rate": None,
    }
    return sb


def simulate_match_end_consensus(sb: Scoreboard, frames: list[tuple],
                                  confirm_frames: int = 2) -> list[tuple]:
    """Mirror the Fix A consensus logic from test_pipeline.py.

    frames: list of (score, wickets, overs_f, target) tuples per frame.
    Returns: list of (frame_idx, state_before_finalize,
                      end_reason_pending, consecutive, fired) tuples.
    """
    results = []
    consecutive = 0
    reason_pending: str | None = None

    for idx, (score, wkts, overs_f, target) in enumerate(frames):
        sb.innings[2]["score"] = score
        sb.innings[2]["wickets"] = wkts
        sb.innings[2]["overs"] = f"{overs_f}"
        sb.innings[2]["target"] = target

        if sb.match_complete:
            results.append((idx, "already_complete", None, 0, False))
            continue

        target_reached = target > 0 and score >= target
        all_out = wkts >= 10
        overs_exhausted = overs_f >= 20.0
        end_now = target_reached or all_out or overs_exhausted

        if end_now:
            reason = ("target_reached" if target_reached
                      else "all_out" if all_out
                      else "overs_exhausted")
            if reason_pending == reason:
                consecutive += 1
            else:
                reason_pending = reason
                consecutive = 1
            fired = consecutive >= confirm_frames
            if fired:
                sb.finalize_match(reason)
            results.append(
                (idx, f"{score}/{wkts} ({overs_f}) t={target}",
                 reason_pending, consecutive, fired))
        else:
            if consecutive > 0:
                results.append(
                    (idx, f"{score}/{wkts} ({overs_f}) reset",
                     None, 0, False))
            else:
                results.append(
                    (idx, f"{score}/{wkts} ({overs_f})",
                     None, 0, False))
            consecutive = 0
            reason_pending = None

    return results


FAILURES = 0


def check(cond: bool, name: str, detail: str = "") -> None:
    global FAILURES
    if cond:
        print(f"  PASS  {name}")
    else:
        FAILURES += 1
        print(f"  FAIL  {name}  {detail}")


def test_1_target_reached():
    print("\n[1] Normal innings 2 ending at target")
    sb = make_scoreboard_in_innings_2(
        target=160, score=159, wickets=4, overs="18.5")
    frames = [
        (159, 4, 18.5, 160),
        (160, 4, 18.6, 160),
        (160, 4, 18.6, 160),
    ]
    results = simulate_match_end_consensus(sb, frames)
    check(sb.match_complete, "match_complete set")
    check(sb.match_end_reason == "target_reached",
          "reason == target_reached", f"got {sb.match_end_reason}")
    check(sb.match_result is not None, "match_result populated")
    if sb.match_result:
        check(sb.match_result["winner"] == "Lucknow Super Giants",
              "winner is batting team",
              f"got {sb.match_result['winner']}")
        check("wicket" in (sb.match_result["margin"] or ""),
              "margin in wickets",
              f"got {sb.match_result['margin']}")
        check(sb.match_result["balls_remaining"] is not None,
              "balls_remaining set")
        check(sb.match_result["balls_remaining"] >= 0
              and sb.match_result["balls_remaining"] <= 120,
              "balls_remaining in valid range",
              f"got {sb.match_result['balls_remaining']}")


def test_2_all_out():
    print("\n[2] Normal innings 2 ending at 10 wickets")
    sb = make_scoreboard_in_innings_2(
        target=160, score=98, wickets=9, overs="15.3")
    frames = [
        (98, 9, 15.3, 160),
        (98, 10, 15.4, 160),
        (98, 10, 15.4, 160),
    ]
    results = simulate_match_end_consensus(sb, frames)
    check(sb.match_complete, "match_complete set")
    check(sb.match_end_reason == "all_out",
          "reason == all_out", f"got {sb.match_end_reason}")
    if sb.match_result:
        check(sb.match_result["winner"] == "Rajasthan Royals",
              "winner is bowling team")
        check("run" in (sb.match_result["margin"] or ""),
              "margin in runs",
              f"got {sb.match_result['margin']}")
        # target=160, score=98 → losing margin = 160-1-98 = 61 runs
        check("61" in (sb.match_result["margin"] or ""),
              "margin == 61 runs",
              f"got {sb.match_result['margin']}")


def test_3_overs_exhausted_loss():
    print("\n[3a] Innings 2 ending at 20 overs — clear loss")
    sb = make_scoreboard_in_innings_2(
        target=160, score=145, wickets=6, overs="19.5")
    frames = [
        (145, 6, 19.5, 160),
        (150, 6, 20.0, 160),
        (150, 6, 20.0, 160),
    ]
    results = simulate_match_end_consensus(sb, frames)
    check(sb.match_complete, "match_complete set")
    check(sb.match_end_reason == "overs_exhausted",
          "reason == overs_exhausted", f"got {sb.match_end_reason}")
    if sb.match_result:
        check(sb.match_result["winner"] == "Rajasthan Royals",
              "winner is bowling team (defended)")
        # target=160, score=150 → margin = 160-1-150 = 9 runs
        check("9 runs" in (sb.match_result["margin"] or ""),
              "margin == 9 runs",
              f"got {sb.match_result['margin']}")


def test_3b_tie():
    print("\n[3b] Innings 2 ending at 20 overs — TIE (scores level)")
    sb = make_scoreboard_in_innings_2(
        target=160, score=155, wickets=6, overs="19.5")
    frames = [
        (155, 6, 19.5, 160),
        (159, 6, 20.0, 160),
        (159, 6, 20.0, 160),
    ]
    results = simulate_match_end_consensus(sb, frames)
    check(sb.match_complete, "match_complete set on tie")
    if sb.match_result:
        check(sb.match_result["winner"] is None,
              "no winner on tie",
              f"got {sb.match_result['winner']}")
        check(sb.match_result["margin"] == "tied",
              "margin == 'tied'",
              f"got {sb.match_result['margin']}")


def test_4_transient_misread():
    print("\n[4] Transient single-frame misread MUST NOT fire")
    sb = make_scoreboard_in_innings_2(
        target=160, score=80, wickets=8, overs="14.2")
    frames = [
        (80, 8, 14.2, 160),
        (80, 10, 14.2, 160),   # MISREAD: 10 wickets
        (80, 8, 14.3, 160),    # reverted
        (84, 8, 14.4, 160),
    ]
    results = simulate_match_end_consensus(sb, frames)
    check(not sb.match_complete,
          "match_complete NOT set after single-frame flicker")
    check(sb.match_end_reason is None,
          "no end reason set", f"got {sb.match_end_reason}")


def test_5_finalize_match_idempotent():
    print("\n[5] finalize_match is idempotent")
    sb = make_scoreboard_in_innings_2(
        target=160, score=160, wickets=4, overs="19.0")
    r1 = sb.finalize_match("target_reached")
    r2 = sb.finalize_match("target_reached")
    r3 = sb.finalize_match("all_out")  # different reason, still no-op
    check(r1 == r2, "calling twice returns same result")
    check(r1 == r3, "calling with different reason still returns first")
    check(sb.match_end_reason == "target_reached",
          "reason not overwritten on second call")


def test_6_set_innings_2_refused_post_finalize():
    print("\n[6] set_innings_2 refused after finalize_match")
    sb = make_scoreboard_in_innings_2(
        target=160, score=160, wickets=4, overs="19.0")
    sb.finalize_match("target_reached")
    inn2_target_before = sb.innings[2].get("target")
    sb.set_innings_2(target=999)
    inn2_target_after = sb.innings[2].get("target")
    check(inn2_target_before == inn2_target_after,
          "innings 2 target unchanged",
          f"before={inn2_target_before} after={inn2_target_after}")
    check(sb.match_complete, "match_complete still true")


def test_7_start_new_innings_refused_post_finalize():
    print("\n[7] start_new_innings refused after finalize_match")
    sb = Scoreboard()
    sb.batting_team = "A"
    sb.bowling_team = "B"
    sb.innings[1] = {
        "score": 150, "wickets": 10, "overs": "18.3",
        "target": None, "batting_team": "A", "bowling_team": "B",
        "striker": None, "non": None,
        "current_bowler": None, "run_rate": None,
    }
    sb.finalize_match("all_out")  # hypothetical direct call
    initial_inn = sb.current_innings
    sb.start_new_innings(batting_squad=["X"], bowling_squad=["Y"])
    check(sb.current_innings == initial_inn,
          "current_innings did not advance",
          f"before={initial_inn} after={sb.current_innings}")


def test_8_live_state_exposes_match_complete():
    print("\n[8] get_live_state exposes match_complete fields")
    sb = make_scoreboard_in_innings_2(
        target=160, score=160, wickets=4, overs="19.0")
    state_before = sb.get_live_state()
    check(state_before["match_complete"] is False,
          "match_complete=False before finalize")
    check(state_before["match_end_reason"] is None,
          "match_end_reason=None before finalize")
    sb.finalize_match("target_reached")
    state_after = sb.get_live_state()
    check(state_after["match_complete"] is True,
          "match_complete=True after finalize")
    check(state_after["match_end_reason"] == "target_reached",
          "reason propagated")
    check(state_after["match_result"] is not None,
          "match_result propagated")


if __name__ == "__main__":
    test_1_target_reached()
    test_2_all_out()
    test_3_overs_exhausted_loss()
    test_3b_tie()
    test_4_transient_misread()
    test_5_finalize_match_idempotent()
    test_6_set_innings_2_refused_post_finalize()
    test_7_start_new_innings_refused_post_finalize()
    test_8_live_state_exposes_match_complete()
    print(f"\n{'=' * 50}")
    print(f"Total failures: {FAILURES}")
    print(f"{'=' * 50}")
    sys.exit(1 if FAILURES else 0)
