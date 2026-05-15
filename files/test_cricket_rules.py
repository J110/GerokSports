"""Unit tests for cricket_rules.py.

Run with:
    python -m pytest files/test_cricket_rules.py -v
or standalone:
    python files/test_cricket_rules.py

Covers every event template, the hard-invariant rejections, the
multi-ball gap path, the partial-data fallback, ambiguity reporting,
absolute / chase ceilings, and the live-bug replay (95 → 446).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cricket_rules import (
    CHASE_CEILING_BUFFER,
    Diff,
    T20_MAX_SCORE,
    validate_absolute,
    validate_diff,
)


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def D(**kw) -> Diff:
    """Diff factory with sensible defaults (all zeros)."""
    base = dict(d_score=0, d_balts=0, d_wkt=0,
                d_str_runs=0, d_str_balls=0,
                d_bwl_runs=0, d_bwl_wkt=0, d_bwl_balls=0)
    base.update(kw)
    return Diff(**base)


def V(diff: Diff, *,
      new_score=100, new_wkt=2, new_overs=10.0,
      target=None, innings=1):
    return validate_diff(
        diff,
        new_score=new_score, new_wickets=new_wkt, new_overs=new_overs,
        target=target, innings=innings)


# ─────────────────────────────────────────────────────────────────────
# Templates — positive cases
# ─────────────────────────────────────────────────────────────────────

def test_dot():
    r = V(D(d_balts=1, d_str_balls=1, d_bwl_balls=1))
    assert r.ok and r.event_type == "DOT", r


def test_single_run():
    r = V(D(d_score=1, d_balts=1,
            d_str_runs=1, d_str_balls=1,
            d_bwl_runs=1, d_bwl_balls=1))
    assert r.ok and r.event_type == "RUNS", r


def test_two_runs():
    r = V(D(d_score=2, d_balts=1,
            d_str_runs=2, d_str_balls=1,
            d_bwl_runs=2, d_bwl_balls=1))
    assert r.ok and r.event_type == "RUNS", r


def test_three_runs():
    r = V(D(d_score=3, d_balts=1,
            d_str_runs=3, d_str_balls=1,
            d_bwl_runs=3, d_bwl_balls=1))
    assert r.ok and r.event_type == "RUNS", r


def test_four():
    r = V(D(d_score=4, d_balts=1,
            d_str_runs=4, d_str_balls=1,
            d_bwl_runs=4, d_bwl_balls=1))
    assert r.ok and r.event_type == "FOUR", r


def test_five_off_bat():
    r = V(D(d_score=5, d_balts=1,
            d_str_runs=5, d_str_balls=1,
            d_bwl_runs=5, d_bwl_balls=1))
    assert r.ok and r.event_type == "FIVE", r


def test_six():
    r = V(D(d_score=6, d_balts=1,
            d_str_runs=6, d_str_balls=1,
            d_bwl_runs=6, d_bwl_balls=1))
    assert r.ok and r.event_type == "SIX", r


def test_overthrow_seven():
    """Boundary + 3 overthrows = 7 on the ball."""
    r = V(D(d_score=7, d_balts=1,
            d_str_runs=4, d_str_balls=1,
            d_bwl_runs=7, d_bwl_balls=1))
    assert r.ok and r.event_type == "OVERTHROW_BOUNDARY", r


def test_bye_one():
    r = V(D(d_score=1, d_balts=1,
            d_str_runs=0, d_str_balls=1,
            d_bwl_runs=0, d_bwl_balls=1))
    assert r.ok and r.event_type == "BYE_OR_LEG_BYE", r


def test_legbye_three():
    r = V(D(d_score=3, d_balts=1,
            d_str_runs=0, d_str_balls=1,
            d_bwl_runs=0, d_bwl_balls=1))
    assert r.ok and r.event_type == "BYE_OR_LEG_BYE", r


def test_wide_one():
    r = V(D(d_score=1, d_balts=0,
            d_str_runs=0, d_str_balls=0,
            d_bwl_runs=1, d_bwl_balls=0))
    # Ambiguous with NO_BALL_NO_BAT — both have identical signatures.
    assert r.ok, r
    assert r.ambiguous, r
    assert "WIDE" in r.matched_templates
    assert "NO_BALL_NO_BAT" in r.matched_templates


def test_wide_four():
    r = V(D(d_score=4, d_balts=0,
            d_str_runs=0, d_str_balls=0,
            d_bwl_runs=4, d_bwl_balls=0))
    assert r.ok and r.event_type == "WIDE", r
    assert not r.ambiguous, r


def test_no_ball_with_four():
    """NB + 4 off the bat → Δscore=5, Δstr_runs=4, Δbwl_runs=5."""
    r = V(D(d_score=5, d_balts=0,
            d_str_runs=4, d_str_balls=0,
            d_bwl_runs=5, d_bwl_balls=0))
    assert r.ok and r.event_type == "NO_BALL_WITH_BAT", r


def test_no_ball_with_six():
    r = V(D(d_score=7, d_balts=0,
            d_str_runs=6, d_str_balls=0,
            d_bwl_runs=7, d_bwl_balls=0))
    assert r.ok and r.event_type == "NO_BALL_WITH_BAT", r


def test_no_ball_with_byes():
    """NB + 2 leg-byes → Δscore=3, Δstr_runs=0, Δbwl_runs=1 (only penalty)."""
    r = V(D(d_score=3, d_balts=0,
            d_str_runs=0, d_str_balls=0,
            d_bwl_runs=1, d_bwl_balls=0))
    assert r.ok and r.event_type == "NO_BALL_BYES", r


def test_wicket_bowled():
    r = V(D(d_score=0, d_balts=1, d_wkt=1,
            d_str_runs=0, d_str_balls=1,
            d_bwl_runs=0, d_bwl_wkt=1, d_bwl_balls=1))
    assert r.ok and r.event_type == "WICKET_BOWLER_CREDITED", r


def test_wicket_runout_no_runs():
    r = V(D(d_score=0, d_balts=1, d_wkt=1,
            d_str_runs=0, d_str_balls=1,
            d_bwl_runs=0, d_bwl_wkt=0, d_bwl_balls=1))
    assert r.ok and r.event_type == "WICKET_RUNOUT_NO_RUNS", r


def test_wicket_runout_with_two_runs_crossed():
    """Run-out attempting third — two runs completed, batsmen had crossed."""
    r = V(D(d_score=2, d_balts=1, d_wkt=1,
            d_str_runs=2, d_str_balls=1,
            d_bwl_runs=2, d_bwl_wkt=0, d_bwl_balls=1))
    assert r.ok and r.event_type == "WICKET_RUNOUT_WITH_RUNS", r


def test_wicket_runout_with_two_runs_not_crossed():
    """Run-out at the strikers' end after 2 runs — striker wasn't the
    one out, so Δstr_runs may be 0."""
    r = V(D(d_score=2, d_balts=1, d_wkt=1,
            d_str_runs=0, d_str_balls=1,
            d_bwl_runs=2, d_bwl_wkt=0, d_bwl_balls=1))
    assert r.ok and r.event_type == "WICKET_RUNOUT_WITH_RUNS", r


def test_wicket_stumped_off_wide():
    """Stumping off a wide credits the bowler (laws of cricket)."""
    r = V(D(d_score=1, d_balts=0, d_wkt=1,
            d_str_runs=0, d_str_balls=0,
            d_bwl_runs=1, d_bwl_wkt=1, d_bwl_balls=0))
    assert r.ok and r.event_type == "WICKET_STUMPED_OFF_WIDE", r


def test_wicket_runout_off_no_ball():
    """Run-out off a no-ball does NOT credit the bowler."""
    r = V(D(d_score=1, d_balts=0, d_wkt=1,
            d_str_runs=0, d_str_balls=0,
            d_bwl_runs=1, d_bwl_wkt=0, d_bwl_balls=0))
    assert r.ok and r.event_type == "WICKET_RUNOUT_OFF_NO_BALL", r


# ─────────────────────────────────────────────────────────────────────
# Multi-ball gap (frame skipped during ad / DRS)
# ─────────────────────────────────────────────────────────────────────

def test_multi_ball_gap_two_balls():
    r = V(D(d_score=4, d_balts=2,
            d_str_runs=4, d_str_balls=1,
            d_bwl_runs=4, d_bwl_balls=2))
    assert r.ok and r.event_type == "DEFERRED_MULTI", r


def test_multi_ball_gap_six_balls_over_change():
    """Full over missed.  New bowler shows Δbwl_balls=1, total Δbalts=6."""
    r = V(D(d_score=12, d_balts=6,
            d_str_runs=2, d_str_balls=2,
            d_bwl_runs=0, d_bwl_balls=1),
          new_overs=11.1)
    assert r.ok and r.event_type == "DEFERRED_MULTI", r


def test_multi_ball_gap_too_many_balls():
    r = V(D(d_score=12, d_balts=7))
    assert not r.ok, r
    assert "multi_max" in r.reject_reason, r


# ─────────────────────────────────────────────────────────────────────
# Hard invariants — negative cases
# ─────────────────────────────────────────────────────────────────────

def test_negative_score_diff_rejected():
    r = V(D(d_score=-1, d_balts=1))
    assert not r.ok and "negative" in r.reject_reason, r


def test_d_score_too_large_single_ball():
    """11 runs on one ball is impossible (max overthrow is 10)."""
    r = V(D(d_score=11, d_balts=1,
            d_str_runs=4, d_str_balls=1,
            d_bwl_runs=11, d_bwl_balls=1))
    assert not r.ok and "max_10" in r.reject_reason, r


def test_d_score_too_large_zero_balls():
    """8 runs without a legal ball — impossible (max NB+6 = 7)."""
    r = V(D(d_score=8, d_balts=0,
            d_bwl_runs=8))
    assert not r.ok and "max_7" in r.reject_reason, r


def test_d_wkt_three_in_one_diff_rejected():
    r = V(D(d_score=0, d_balts=1, d_wkt=3))
    assert not r.ok and "multi_max" in r.reject_reason, r


def test_d_bwl_runs_exceeds_d_score():
    """Bowler can't concede more than the team scored."""
    r = V(D(d_score=2, d_balts=1,
            d_str_runs=2, d_str_balls=1,
            d_bwl_runs=4, d_bwl_balls=1))
    assert not r.ok and "d_bwl_runs" in r.reject_reason, r


def test_d_str_runs_exceeds_d_score():
    r = V(D(d_score=2, d_balts=1,
            d_str_runs=4, d_str_balls=1,
            d_bwl_runs=2, d_bwl_balls=1))
    assert not r.ok and "d_str_runs" in r.reject_reason, r


def test_d_bwl_balls_exceeds_d_balts():
    r = V(D(d_score=0, d_balts=1,
            d_str_runs=0, d_str_balls=1,
            d_bwl_runs=0, d_bwl_balls=2))
    assert not r.ok and "d_bwl_balls" in r.reject_reason, r


def test_d_bwl_wkt_exceeds_d_wkt():
    r = V(D(d_score=0, d_balts=1, d_wkt=0,
            d_str_runs=0, d_str_balls=1,
            d_bwl_runs=0, d_bwl_wkt=1, d_bwl_balls=1))
    assert not r.ok and "d_bwl_wkt" in r.reject_reason, r


def test_no_template_match_garbage():
    """Score went up by 4 on a single legal ball but striker only got
    1 — doesn't match FOUR (str_runs=4) or anything else."""
    r = V(D(d_score=4, d_balts=1,
            d_str_runs=1, d_str_balls=1,
            d_bwl_runs=4, d_bwl_balls=1))
    assert not r.ok and "no_template_match" in r.reject_reason, r


# ─────────────────────────────────────────────────────────────────────
# Partial data — fallback path
# ─────────────────────────────────────────────────────────────────────

def test_partial_data_invariants_only_accepts():
    """Striker strip occluded — no Δstr_*.  Diff still legal."""
    r = V(D(d_score=4, d_balts=1, d_wkt=0,
            d_str_runs=None, d_str_balls=None,
            d_bwl_runs=4, d_bwl_balls=1))
    assert r.ok and r.partial and r.event_type == "FOUR", r


def test_partial_data_invariants_violated_rejects():
    """Same partial diff but bowler conceded more than team scored."""
    r = V(D(d_score=2, d_balts=1,
            d_str_runs=None, d_str_balls=None,
            d_bwl_runs=4, d_bwl_balls=1))
    assert not r.ok, r


def test_partial_data_extras_classified():
    r = V(D(d_score=1, d_balts=0,
            d_str_runs=None, d_str_balls=None,
            d_bwl_runs=None, d_bwl_balls=None))
    assert r.ok and r.partial and r.event_type == "EXTRA", r


# ─────────────────────────────────────────────────────────────────────
# Absolute / chase ceilings
# ─────────────────────────────────────────────────────────────────────

def test_absolute_ceiling_above_t20_max():
    r = validate_absolute(score=T20_MAX_SCORE + 1, wickets=2,
                          overs=15.0, target=None, innings=1)
    assert not r.ok and str(T20_MAX_SCORE) in r.reject_reason, r


def test_chase_ceiling_innings_two_target_known():
    r = validate_absolute(score=200, wickets=2, overs=15.0,
                          target=180, innings=2)
    assert not r.ok and "chase" in r.reject_reason, r


def test_chase_ceiling_buffer_allows_jitter():
    """Score = target + CHASE_CEILING_BUFFER must still pass."""
    r = validate_absolute(score=180 + CHASE_CEILING_BUFFER,
                          wickets=2, overs=15.0,
                          target=180, innings=2)
    assert r.ok, r


def test_overs_ball_digit_invalid():
    """Overs of 8.7 is impossible (base 6 — only .0 to .5)."""
    r = validate_absolute(score=80, wickets=2, overs=8.7,
                          target=None, innings=1)
    assert not r.ok and "ball_digit" in r.reject_reason, r


def test_overs_above_twenty():
    r = validate_absolute(score=180, wickets=5, overs=20.1,
                          target=None, innings=1)
    assert not r.ok and "overs" in r.reject_reason, r


def test_wickets_above_ten():
    r = validate_absolute(score=180, wickets=11, overs=15.0,
                          target=None, innings=1)
    assert not r.ok and "wickets" in r.reject_reason, r


# ─────────────────────────────────────────────────────────────────────
# Live-bug replay: 95 → 446 in innings 2 with target 181
# ─────────────────────────────────────────────────────────────────────

def test_replay_446_jump_rejected_by_chase_ceiling():
    """The exact bug from yesterday's match: prev=95/3 (10.0), target=181,
    OCR misread next read as 446/3.  Must be rejected by the chase
    ceiling before the diff check ever runs."""
    r = validate_diff(
        D(d_score=351, d_balts=0),
        new_score=446, new_wickets=3, new_overs=10.0,
        target=181, innings=2)
    assert not r.ok and "chase" in r.reject_reason, r


def test_replay_446_jump_rejected_by_absolute_even_without_target():
    """Same bug but in innings 1 with no target — still must reject
    on the absolute T20 ceiling."""
    r = validate_diff(
        D(d_score=351, d_balts=0),
        new_score=446, new_wickets=3, new_overs=10.0,
        target=None, innings=1)
    assert not r.ok and "T20_max" in r.reject_reason, r


def test_replay_score_diff_within_chase_but_impossible_per_ball():
    """Chase ceiling allows it, but +30 on 0 legal balls is impossible."""
    r = validate_diff(
        D(d_score=30, d_balts=0,
          d_str_runs=0, d_str_balls=0,
          d_bwl_runs=30, d_bwl_balls=0),
        new_score=125, new_wickets=3, new_overs=10.0,
        target=181, innings=2)
    assert not r.ok and "max_7" in r.reject_reason, r


# ─────────────────────────────────────────────────────────────────────
# Ambiguity surfacing
# ─────────────────────────────────────────────────────────────────────

def test_wide_vs_no_ball_ambiguity_reported():
    """Both WIDE and NO_BALL_NO_BAT have identical signatures at +1/0
    legal balls.  Validator must surface both for caller to pick from
    broadcast_extra hint."""
    r = V(D(d_score=1, d_balts=0,
            d_str_runs=0, d_str_balls=0,
            d_bwl_runs=1, d_bwl_balls=0))
    assert r.ok and r.ambiguous, r
    assert sorted(r.matched_templates) == ["NO_BALL_NO_BAT", "WIDE"]


# ─────────────────────────────────────────────────────────────────────
# Standalone runner (no pytest dependency)
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import inspect
    g = globals()
    tests = [(name, fn) for name, fn in g.items()
             if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}\n        {e}")
        except Exception as e:
            failed += 1
            print(f"  ERR   {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed"
          + (f", {failed} failed" if failed else ""))
    sys.exit(1 if failed else 0)
