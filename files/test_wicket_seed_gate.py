"""
Test suite for Fix #1: wicket seed gate (cold-start vs live wicket).

Root cause: the original auto-dismiss cold-start seed fired on any
``old == 0 → value > 0`` wicket transition, which pre-armed the
dismissal gate the FIRST time a real wicket was taken during a live
session — silently dropping the genuine dismissal event.  Observed on
Sarfaraz, MI vs CSK 2026-04-23, F11: live wicket seeded the gate, all
subsequent dismissals (F12+) rejected as "wickets counter has not
advanced since last auto-dismiss".

Fix: seed ONLY when wickets were never confirmed (``old is None``,
genuine mid-match attach) OR when we've seen fewer than 2 frames
confirming ``wickets=0``.  Once we've seen 2+ confirmed zero frames,
any subsequent 0→1 is a real event and must NOT pre-arm the gate.

Covered cases (per user spec):
  1. Cold start with wickets=None → seed fires (historical protection).
  2. wickets=0 confirmed on 2+ frames → subsequent 0→1 does NOT seed
     (the live-wicket happy path — the bug we are fixing).
  3. wickets=0 confirmed once → 0→1 STILL seeds (too new to be sure;
     could be pre-match strip settling in).
  4. Cold start with wickets=5 (mid-match attach past several wickets)
     → seed fires (historical attribution gap).
  5. set_innings_2 resets the zero-streak (new innings restart).
  6. start_new_innings resets the zero-streak (live innings
     transition — innings 2 starts at wickets=0 and must have a
     fresh counter).
  7. Cache restore primes the zero-streak past threshold so a
     subsequent 0→1 on the restored session counts as live.
  8. Raw Scout read at 0 increments the per-observation counter.

Run: python3 test_wicket_seed_gate.py
"""

import sys

from eyes.scoreboard import Scoreboard


def _fresh_sb() -> Scoreboard:
    sb = Scoreboard()
    sb.batting_team = "Chennai Super Kings"
    sb.bowling_team = "Mumbai Indians"
    sb.current_innings = 1
    sb.innings[1] = {
        "score": None,
        "wickets": None,
        "overs": None,
        "target": None,
        "batting_team": "Chennai Super Kings",
        "bowling_team": "Mumbai Indians",
        "striker": None,
        "non": None,
        "current_bowler": None,
        "run_rate": None,
    }
    # Ensure the seed gate is at 0 (normally set by setup_innings /
    # set_innings_2 / start_new_innings).
    sb._last_autodismiss_wickets = 0
    return sb


def _force_state(sb: Scoreboard, *, wickets, zero_streak: int,
                 gate_seed: int = 0) -> None:
    """Prime wickets state bypassing the consensus tracker."""
    sb._inn["wickets"] = wickets
    sb._tracker.force_set("wickets", wickets)
    sb._wickets_confirmed_frames_at_zero = zero_streak
    sb._last_autodismiss_wickets = gate_seed


def case1_cold_start_none() -> bool:
    """wickets=None → >0 : seed must fire (historical attach)."""
    sb = _fresh_sb()
    # _inn["wickets"] is None, zero_streak is 0, gate is 0.
    _force_state(sb, wickets=None, zero_streak=0, gate_seed=0)

    # Prime tracker consensus to commit value=3 on the first call.
    sb._tracker.force_set("wickets", 3)
    # Route through set() to exercise the seed logic.  Bypass the
    # tracker by forcing it to already-confirmed, then call set so
    # the post-commit block runs.
    sb.set("wickets", 3, frame=1)
    ok = sb._last_autodismiss_wickets == 3
    print(f"  [case1] cold-start None→3: gate="
          f"{sb._last_autodismiss_wickets} (expect 3) "
          f"{'OK' if ok else 'FAIL'}")
    return ok


def case2_confirmed_zero_then_live_wicket() -> bool:
    """wickets=0 confirmed on 2+ frames, then 0→1: seed must NOT fire."""
    sb = _fresh_sb()
    _force_state(sb, wickets=0, zero_streak=3, gate_seed=0)

    # Commit the live wicket transition.
    sb._tracker.force_set("wickets", 1)
    sb.set("wickets", 1, frame=4)
    ok = sb._last_autodismiss_wickets == 0
    print(f"  [case2] 0 confirmed x3 then 0→1: gate="
          f"{sb._last_autodismiss_wickets} (expect 0 — live event) "
          f"{'OK' if ok else 'FAIL'}")
    return ok


def case3_one_zero_then_wicket() -> bool:
    """wickets=0 confirmed just ONCE, then 0→1: seed still fires (too new)."""
    sb = _fresh_sb()
    _force_state(sb, wickets=0, zero_streak=1, gate_seed=0)

    sb._tracker.force_set("wickets", 1)
    sb.set("wickets", 1, frame=2)
    ok = sb._last_autodismiss_wickets == 1
    print(f"  [case3] 0 confirmed x1 then 0→1: gate="
          f"{sb._last_autodismiss_wickets} (expect 1 — conservative) "
          f"{'OK' if ok else 'FAIL'}")
    return ok


def case4_cold_start_mid_innings() -> bool:
    """wickets=None → 5 (mid-match attach past wickets)."""
    sb = _fresh_sb()
    _force_state(sb, wickets=None, zero_streak=0, gate_seed=0)

    sb._tracker.force_set("wickets", 5)
    sb.set("wickets", 5, frame=1)
    ok = sb._last_autodismiss_wickets == 5
    print(f"  [case4] cold-start None→5: gate="
          f"{sb._last_autodismiss_wickets} (expect 5) "
          f"{'OK' if ok else 'FAIL'}")
    return ok


def case5_set_innings_2_resets_counter() -> bool:
    """set_innings_2() must reset the zero-streak counter."""
    sb = _fresh_sb()
    sb._wickets_confirmed_frames_at_zero = 7
    sb.set_innings_2(target=170)
    ok = sb._wickets_confirmed_frames_at_zero == 0
    print(f"  [case5] set_innings_2 resets counter: streak="
          f"{sb._wickets_confirmed_frames_at_zero} (expect 0) "
          f"{'OK' if ok else 'FAIL'}")
    return ok


def case6_start_new_innings_resets_counter() -> bool:
    """start_new_innings() must reset the zero-streak counter."""
    sb = _fresh_sb()
    sb._wickets_confirmed_frames_at_zero = 9
    sb._inn["score"] = 180
    sb.start_new_innings(
        batting_squad=["A Batter", "B Batter"],
        bowling_squad=["X Bowler", "Y Bowler"],
        frame=10,
    )
    ok = sb._wickets_confirmed_frames_at_zero == 0
    print(f"  [case6] start_new_innings resets counter: streak="
          f"{sb._wickets_confirmed_frames_at_zero} (expect 0) "
          f"{'OK' if ok else 'FAIL'}")
    return ok


def case7_cache_restore_primes_counter() -> bool:
    """Cache restore must prime the zero-streak past threshold."""
    sb = _fresh_sb()
    sb._inn["score"] = 45
    sb._inn["wickets"] = 0
    sb._inn["overs"] = "5.2"
    cached = {
        "score": 45,
        "wickets": 0,
        "overs": "5.2",
        "frame": 300,
        "batting_card": {},
        "bowling_card": {},
        "fall_of_wickets": [],
    }
    sb.restore_from_cache(cached)
    primed = sb._wickets_confirmed_frames_at_zero >= 2

    # Now a live 0→1 on the restored session must be treated as real.
    sb._tracker.force_set("wickets", 1)
    sb.set("wickets", 1, frame=301)
    no_seed = sb._last_autodismiss_wickets == 0

    ok = primed and no_seed
    print(f"  [case7] cache-restore primes counter: streak="
          f"{sb._wickets_confirmed_frames_at_zero} (>=2), "
          f"gate_after_live_0_to_1={sb._last_autodismiss_wickets} "
          f"(expect 0) {'OK' if ok else 'FAIL'}")
    return ok


def case8_raw_observation_counter_ticks() -> bool:
    """set('wickets', 0) must tick the counter even when tracker doesn't commit."""
    sb = _fresh_sb()
    assert sb._wickets_confirmed_frames_at_zero == 0

    # Call set() 5 times with value=0.  The tracker may reject some
    # of these (no cur_w / pending consensus) but the per-observation
    # counter should tick every time regardless.
    for f in range(1, 6):
        sb.set("wickets", 0, frame=f)
    ok = sb._wickets_confirmed_frames_at_zero == 5
    print(f"  [case8] raw observation counter: streak="
          f"{sb._wickets_confirmed_frames_at_zero} (expect 5) "
          f"{'OK' if ok else 'FAIL'}")
    return ok


def main() -> int:
    cases = [
        ("cold_start_none", case1_cold_start_none),
        ("confirmed_zero_then_live_wicket",
         case2_confirmed_zero_then_live_wicket),
        ("one_zero_then_wicket", case3_one_zero_then_wicket),
        ("cold_start_mid_innings", case4_cold_start_mid_innings),
        ("set_innings_2_resets_counter", case5_set_innings_2_resets_counter),
        ("start_new_innings_resets_counter",
         case6_start_new_innings_resets_counter),
        ("cache_restore_primes_counter", case7_cache_restore_primes_counter),
        ("raw_observation_counter_ticks", case8_raw_observation_counter_ticks),
    ]
    print("[Fix #1] Wicket seed gate test suite")
    print("=" * 60)
    results = []
    for name, fn in cases:
        try:
            ok = fn()
        except Exception as e:
            print(f"  [{name}] EXCEPTION: {e!r}")
            ok = False
        results.append((name, ok))
    print("=" * 60)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"Result: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
