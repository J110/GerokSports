"""Cricket-rules diff validator.

Replaces the accumulated heuristics around score / wicket / overs jumps
with an exhaustive table of legal cricket events.  Every accepted diff
between two consecutive scoreboard reads must either:

  (a) match exactly one event template (when all 8 deltas are known), or
  (b) pass the hard invariants and be classifiable from partial data
      (Δscore, Δlegal_balls, Δwickets), or
  (c) be a multi-ball gap (frame skipped during ad / DRS) within
      bounded ceilings.

Everything else is OCR garbage and is rejected with a specific reason.

Cold-start (first read after pipeline boot) is handled by
`validate_absolute()` — only ceilings on the absolute values, no diff
context required.

This module is intentionally self-contained and free of side-effects so
it can be unit-tested in isolation.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Callable, Optional

# ── Hard ceilings (apply in COLD_START and WARM) ─────────────────────
T20_MAX_SCORE = 320        # men's T20I record is 287 (Zimbabwe vs Gambia)
T20_MAX_OVERS = 20.0
T20_MAX_BALL_DIGIT = 5     # overs format is X.0 .. X.5 (base 6)
MAX_WICKETS = 10
CHASE_CEILING_BUFFER = 4   # 2nd innings: score <= target + 4 (OCR jitter)

# ── Per-event ceilings (apply in WARM only) ──────────────────────────
SINGLE_BALL_MAX_SCORE = 10  # 6 + 4 overthrow extras (extreme upper bound)
NO_LEGAL_BALL_MAX_SCORE = 7  # NB + 6 off the bat
MULTI_BALL_MAX_BALLS = 12   # cricket-rules internal cap on Δballs between consecutive reads
MULTI_BALL_MAX_WKT = 2      # max wickets between consecutive reads


def proposed_score_overs_rr_plausible(score: int, overs: float) -> bool:
    """P16: strip (score, overs) pairs with impossible team run rate."""
    if overs < 2.0 or score < 6:
        return True
    rr = score / overs
    return 2.0 <= rr <= 20.0


# ─────────────────────────────────────────────────────────────────────
# Public dataclasses
# ─────────────────────────────────────────────────────────────────────

@dataclass
class Diff:
    """Delta between two scoreboard reads.

    Any of `d_str_*` / `d_bwl_*` may be None when the broadcast strip
    didn't show that information for the relevant entity (occluded by a
    graphic, name mismatch from extractor noise, etc.).  In that case
    the validator gracefully degrades to invariants-only mode and lets
    ScoreManager classify the event from the available fields.

    `d_balts` is the legal-balls delta (overs_to_balls(new) - prev).
    Wide / no-ball do not increment legal balls.
    """
    d_score: int
    d_balts: int
    d_wkt: int
    d_str_runs: Optional[int] = None
    d_str_balls: Optional[int] = None
    d_bwl_runs: Optional[int] = None
    d_bwl_wkt: Optional[int] = None
    d_bwl_balls: Optional[int] = None

    def is_complete(self) -> bool:
        return all(getattr(self, f.name) is not None
                   for f in fields(self))

    def signature(self) -> str:
        """Compact human-readable signature for logs / reject reasons."""
        def s(v):
            return "?" if v is None else str(v)
        return (f"score+{self.d_score}/balts+{self.d_balts}/"
                f"wkt+{self.d_wkt}/str+{s(self.d_str_runs)}r"
                f"+{s(self.d_str_balls)}b/bwl+{s(self.d_bwl_runs)}r"
                f"+{s(self.d_bwl_wkt)}w+{s(self.d_bwl_balls)}b")


@dataclass
class ValidationResult:
    ok: bool
    event_type: Optional[str] = None
    matched_templates: list[str] = field(default_factory=list)
    reject_reason: Optional[str] = None
    partial: bool = False     # template-match skipped due to None fields
    ambiguous: bool = False   # multiple templates matched (e.g. WIDE vs NB)


# ─────────────────────────────────────────────────────────────────────
# Templates — exhaustive table of legal single-event signatures
# ─────────────────────────────────────────────────────────────────────
#
# Each predicate assumes Diff.is_complete() (all 8 fields non-None).
# Order matters only for tie-breaking when reporting matched_templates;
# disambiguation between truly ambiguous templates (WIDE_1 vs NB_NO_BAT)
# happens upstream via broadcast_extra hints.
#
# Notation in comments:
#   d.d_score      = team score delta
#   d.d_balts      = legal balls delta
#   d.d_wkt        = team wickets delta
#   d.d_str_runs   = striker's runs delta
#   d.d_str_balls  = striker's balls delta
#   d.d_bwl_runs   = bowler's runs conceded delta
#   d.d_bwl_wkt    = bowler's wickets delta
#   d.d_bwl_balls  = bowler's balls delta

TemplatePredicate = Callable[["Diff"], bool]


def _t_dot(d: Diff) -> bool:
    """No score, no wicket, one legal ball faced."""
    return (d.d_score == 0 and d.d_balts == 1 and d.d_wkt == 0
            and d.d_str_runs == 0 and d.d_str_balls == 1
            and d.d_bwl_runs == 0 and d.d_bwl_wkt == 0
            and d.d_bwl_balls == 1)


def _t_runs(d: Diff) -> bool:
    """1, 2, or 3 runs off the bat (legal delivery)."""
    return (d.d_balts == 1 and d.d_wkt == 0
            and 1 <= d.d_score <= 3
            and d.d_str_runs == d.d_score
            and d.d_str_balls == 1
            and d.d_bwl_runs == d.d_score
            and d.d_bwl_wkt == 0
            and d.d_bwl_balls == 1)


def _t_four(d: Diff) -> bool:
    return (d.d_score == 4 and d.d_balts == 1 and d.d_wkt == 0
            and d.d_str_runs == 4 and d.d_str_balls == 1
            and d.d_bwl_runs == 4 and d.d_bwl_wkt == 0
            and d.d_bwl_balls == 1)


def _t_five(d: Diff) -> bool:
    """5 runs off the bat (rare — usually involves overthrows)."""
    return (d.d_score == 5 and d.d_balts == 1 and d.d_wkt == 0
            and d.d_str_runs == 5 and d.d_str_balls == 1
            and d.d_bwl_runs == 5 and d.d_bwl_wkt == 0
            and d.d_bwl_balls == 1)


def _t_six(d: Diff) -> bool:
    return (d.d_score == 6 and d.d_balts == 1 and d.d_wkt == 0
            and d.d_str_runs == 6 and d.d_str_balls == 1
            and d.d_bwl_runs == 6 and d.d_bwl_wkt == 0
            and d.d_bwl_balls == 1)


def _t_overthrow(d: Diff) -> bool:
    """Overthrows: 7-10 runs on a single legal ball."""
    return (7 <= d.d_score <= SINGLE_BALL_MAX_SCORE
            and d.d_balts == 1 and d.d_wkt == 0
            and d.d_str_runs is not None
            and 0 <= d.d_str_runs <= d.d_score
            and d.d_str_balls == 1
            and d.d_bwl_runs == d.d_score
            and d.d_bwl_wkt == 0
            and d.d_bwl_balls == 1)


def _t_bye_or_legbye(d: Diff) -> bool:
    """Byes / leg-byes: 1-4 runs, legal ball, no batter or bowler credit."""
    return (1 <= d.d_score <= 4
            and d.d_balts == 1 and d.d_wkt == 0
            and d.d_str_runs == 0 and d.d_str_balls == 1
            and d.d_bwl_runs == 0
            and d.d_bwl_wkt == 0 and d.d_bwl_balls == 1)


def _t_wide(d: Diff) -> bool:
    """Wide: 1-5 runs (1 penalty + 0-4 actual runs), not a legal ball."""
    return (1 <= d.d_score <= 5
            and d.d_balts == 0 and d.d_wkt == 0
            and d.d_str_runs == 0 and d.d_str_balls == 0
            and d.d_bwl_runs == d.d_score
            and d.d_bwl_wkt == 0
            and d.d_bwl_balls == 0)


def _t_no_ball_no_bat(d: Diff) -> bool:
    """No-ball, batter didn't make contact (or got a single off pads)."""
    return (d.d_score == 1
            and d.d_balts == 0 and d.d_wkt == 0
            and d.d_str_runs == 0 and d.d_str_balls == 0
            and d.d_bwl_runs == 1
            and d.d_bwl_wkt == 0 and d.d_bwl_balls == 0)


def _t_no_ball_with_bat(d: Diff) -> bool:
    """No-ball + bat runs (1-6).  Δscore = 1 (penalty) + bat runs."""
    return (d.d_balts == 0 and d.d_wkt == 0
            and d.d_str_runs is not None
            and 1 <= d.d_str_runs <= 6
            and d.d_score == 1 + d.d_str_runs
            and d.d_str_balls == 0
            and d.d_bwl_runs == d.d_score
            and d.d_bwl_wkt == 0
            and d.d_bwl_balls == 0)


def _t_no_ball_byes(d: Diff) -> bool:
    """No-ball + byes / leg-byes (1-4).  Bowler only charged the 1 penalty."""
    return (d.d_balts == 0 and d.d_wkt == 0
            and 2 <= d.d_score <= 5
            and d.d_str_runs == 0 and d.d_str_balls == 0
            and d.d_bwl_runs == 1
            and d.d_bwl_wkt == 0 and d.d_bwl_balls == 0)


def _t_wicket_bowler(d: Diff) -> bool:
    """Bowled / caught / lbw / stumped on legal ball — bowler credited."""
    return (d.d_score == 0 and d.d_balts == 1 and d.d_wkt == 1
            and d.d_str_runs == 0 and d.d_str_balls == 1
            and d.d_bwl_runs == 0
            and d.d_bwl_wkt == 1
            and d.d_bwl_balls == 1)


def _t_wicket_runout_no_runs(d: Diff) -> bool:
    """Run-out with 0 runs completed (rare — caught short of crease)."""
    return (d.d_score == 0 and d.d_balts == 1 and d.d_wkt == 1
            and d.d_str_runs == 0 and d.d_str_balls == 1
            and d.d_bwl_runs == 0
            and d.d_bwl_wkt == 0
            and d.d_bwl_balls == 1)


def _t_wicket_runout_with_runs(d: Diff) -> bool:
    """Run-out with N completed runs (1-3).  Striker may or may not have
    crossed before the dismissal — Δstr_runs ∈ [0, N]."""
    return (1 <= d.d_score <= 3
            and d.d_balts == 1 and d.d_wkt == 1
            and d.d_str_runs is not None
            and 0 <= d.d_str_runs <= d.d_score
            and d.d_str_balls == 1
            and d.d_bwl_runs == d.d_score
            and d.d_bwl_wkt == 0
            and d.d_bwl_balls == 1)


def _t_wicket_stumped_off_wide(d: Diff) -> bool:
    """Stumping off a wide.  Wide isn't a legal ball but stumping
    credits the bowler (laws of cricket)."""
    return (d.d_score == 1 and d.d_balts == 0 and d.d_wkt == 1
            and d.d_str_runs == 0 and d.d_str_balls == 0
            and d.d_bwl_runs == 1
            and d.d_bwl_wkt == 1
            and d.d_bwl_balls == 0)


def _t_wicket_runout_off_no_ball(d: Diff) -> bool:
    """Run-out off a no-ball.  No legal ball, bowler not credited."""
    return (d.d_score == 1 and d.d_balts == 0 and d.d_wkt == 1
            and d.d_str_runs == 0 and d.d_str_balls == 0
            and d.d_bwl_runs == 1
            and d.d_bwl_wkt == 0
            and d.d_bwl_balls == 0)


# Order matters only for ambiguity reporting — most-specific first.
_TEMPLATES: list[tuple[str, TemplatePredicate]] = [
    ("DOT",                         _t_dot),
    ("WICKET_BOWLER_CREDITED",      _t_wicket_bowler),
    ("WICKET_RUNOUT_NO_RUNS",       _t_wicket_runout_no_runs),
    ("WICKET_RUNOUT_WITH_RUNS",     _t_wicket_runout_with_runs),
    ("WICKET_STUMPED_OFF_WIDE",     _t_wicket_stumped_off_wide),
    ("WICKET_RUNOUT_OFF_NO_BALL",   _t_wicket_runout_off_no_ball),
    ("FOUR",                        _t_four),
    ("SIX",                         _t_six),
    ("FIVE",                        _t_five),
    ("OVERTHROW_BOUNDARY",          _t_overthrow),
    ("RUNS",                        _t_runs),
    ("BYE_OR_LEG_BYE",              _t_bye_or_legbye),
    ("WIDE",                        _t_wide),
    ("NO_BALL_NO_BAT",              _t_no_ball_no_bat),
    ("NO_BALL_WITH_BAT",            _t_no_ball_with_bat),
    ("NO_BALL_BYES",                _t_no_ball_byes),
]


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────

def validate_absolute(score: int | None, wickets: int | None,
                      overs: float | None,
                      target: int | None,
                      innings: int) -> ValidationResult:
    """Hard ceilings on absolute values.  No diff context required.

    Used in COLD_START to gate the very first scorecard accepted into
    state, and in WARM as the first sanity filter before diff checks.
    """
    if score is not None:
        if score < 0:
            return ValidationResult(
                ok=False, reject_reason=f"score_{score}_negative")
        # Chase ceiling fires before the absolute T20 ceiling so the
        # rejection reason carries match context when both apply.
        if (innings >= 2 and target is not None
                and score > target + CHASE_CEILING_BUFFER):
            return ValidationResult(
                ok=False,
                reject_reason=(f"chase_score_{score}_>_target_{target}"
                               f"+{CHASE_CEILING_BUFFER}"))
        if score > T20_MAX_SCORE:
            return ValidationResult(
                ok=False,
                reject_reason=f"score_{score}_>_T20_max_{T20_MAX_SCORE}")

    if wickets is not None:
        if wickets < 0 or wickets > MAX_WICKETS:
            return ValidationResult(
                ok=False, reject_reason=f"wickets_{wickets}_invalid")

    if overs is not None:
        if overs < 0 or overs > T20_MAX_OVERS:
            return ValidationResult(
                ok=False, reject_reason=f"overs_{overs}_invalid")
        ball_digit = round((overs - int(overs)) * 10)
        if ball_digit > T20_MAX_BALL_DIGIT:
            return ValidationResult(
                ok=False,
                reject_reason=(f"overs_{overs}_ball_digit_"
                               f"{ball_digit}>{T20_MAX_BALL_DIGIT}"))

    return ValidationResult(ok=True)


def validate_diff(diff: Diff, *,
                  new_score: int | None,
                  new_wickets: int | None,
                  new_overs: float | None,
                  target: int | None,
                  innings: int) -> ValidationResult:
    """Validate a diff against cricket rules.

    Three stages, short-circuiting on first failure:
      1. Absolute ceilings on the new state (validate_absolute).
      2. Hard invariants on the diff (negativity, multi-ball ceilings,
         cross-field consistency).
      3. Template match — only when the diff is complete.  Partial
         diffs (any None field) accept after invariants pass and let
         the caller infer the event type from the available fields.
    """
    abs_check = validate_absolute(new_score, new_wickets, new_overs,
                                  target, innings)
    if not abs_check.ok:
        return abs_check

    inv = _check_invariants(diff)
    if not inv.ok:
        return inv

    # Multi-ball gap: skip frame(s).  No template applies to a stack
    # of unknown events; the gate is the multi-ball ceilings already
    # enforced in _check_invariants.
    if diff.d_balts > 1:
        return ValidationResult(ok=True, event_type="DEFERRED_MULTI")

    # Partial data: template match is a best-effort bonus, not a gate.
    if not diff.is_complete():
        return ValidationResult(
            ok=True, partial=True,
            event_type=_infer_partial_event(diff))

    matches = [name for name, pred in _TEMPLATES if pred(diff)]
    if not matches:
        return ValidationResult(
            ok=False,
            reject_reason=f"no_template_match[{diff.signature()}]")

    return ValidationResult(
        ok=True,
        event_type=matches[0],
        matched_templates=matches,
        ambiguous=len(matches) > 1)


def validate_direct_proposal(*,
                             cur_score: int | None,
                             cur_overs: float | str | None,
                             cur_wickets: int | None,
                             new_score: int | None,
                             new_overs: float | str | None,
                             new_wickets: int | None,
                             target: int | None,
                             innings: int) -> ValidationResult:
    """Cricket-rules pre-check for the DIRECT extractor → tracker path.

    P0 fix (2026-05-02 CSK vs MI post-mortem §Issue 2): the DIRECT
    block in the pipeline used to commit each of score/overs/wickets
    independently, with the SM cricket_rules evaluator running only
    *after* the commit landed (observability, not veto).  At F500
    19:57:07 a recap-overlay frame proposed overs 5.2→7.5 (Δ_balts=15
    > MULTI_BALL_MAX_BALLS=12); the DIRECT path accepted overs→7.5
    and SM logged a REJECT one frame later, with state already
    poisoned for the rest of the session.

    This helper builds the same Diff the SM would build and returns
    the same ValidationResult, so the DIRECT path can short-circuit
    *before* mutating ``scoreboard._inn``.

    P16 (2026-05-03): run-rate sanity on the proposed (score, overs)
    pair even on cold-start so e.g. 9/7 from strip misparse is vetoed.
    """
    if new_score is None and new_overs is None and new_wickets is None:
        return ValidationResult(ok=True)

    if cur_score is None or cur_overs is None or cur_wickets is None:
        if new_score is not None and new_overs is not None:
            try:
                _ns = int(new_score)
                _no = float(str(new_overs).split("/")[0].strip())
            except (ValueError, TypeError) as e:
                return ValidationResult(
                    ok=False,
                    reject_reason=f"invalid_cold_proposal:{e}")
            if not proposed_score_overs_rr_plausible(_ns, _no):
                return ValidationResult(
                    ok=False,
                    reject_reason=(
                        f"[SCORE-OVERS-RR-REJECT] score={_ns} "
                        f"overs={_no}"))
        return ValidationResult(ok=True)
    try:
        cur_score_i = int(cur_score)
        cur_wkts_i = int(cur_wickets)
        cur_overs_f = float(str(cur_overs).split("/")[0].strip())
    except (ValueError, TypeError) as e:
        return ValidationResult(
            ok=False, reject_reason=f"invalid_current_state:{e}")
    try:
        new_score_i = (int(new_score)
                       if new_score is not None else cur_score_i)
        new_wkts_i = (int(new_wickets)
                      if new_wickets is not None else cur_wkts_i)
        if new_overs is not None:
            _ostr = str(new_overs).split("/")[0].strip()
            new_overs_f = float(_ostr)
        else:
            new_overs_f = cur_overs_f
    except (ValueError, TypeError) as e:
        return ValidationResult(
            ok=False, reject_reason=f"invalid_proposed_state:{e}")

    _rsi = new_score_i if new_score is not None else cur_score_i
    _rof = new_overs_f if new_overs is not None else cur_overs_f
    if (new_score is not None or new_overs is not None):
        if not proposed_score_overs_rr_plausible(_rsi, _rof):
            return ValidationResult(
                ok=False,
                reject_reason=(
                    f"[SCORE-OVERS-RR-REJECT] score={_rsi} "
                    f"overs={_rof}"))

    def _to_balls(ov: float) -> int:
        full = int(ov)
        part = round((ov - full) * 10)
        return full * 6 + part

    diff = Diff(
        d_score=new_score_i - cur_score_i,
        d_balts=_to_balls(new_overs_f) - _to_balls(cur_overs_f),
        d_wkt=new_wkts_i - cur_wkts_i)
    return validate_diff(
        diff,
        new_score=new_score_i,
        new_wickets=new_wkts_i,
        new_overs=new_overs_f,
        target=target,
        innings=innings)


# ─────────────────────────────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────────────────────────────

def _check_invariants(d: Diff) -> ValidationResult:
    """Cricket physics that hold for every event, regardless of type."""

    # Coarse non-negativity / wicket cap
    if d.d_score < 0:
        return ValidationResult(
            ok=False, reject_reason=f"d_score_{d.d_score}_negative")
    if d.d_balts < 0:
        return ValidationResult(
            ok=False, reject_reason=f"d_balts_{d.d_balts}_negative")
    if d.d_wkt < 0:
        return ValidationResult(
            ok=False, reject_reason=f"d_wkt_{d.d_wkt}_negative")

    # Multi-ball ceilings (frame-skip during ad / DRS)
    if d.d_balts > MULTI_BALL_MAX_BALLS:
        return ValidationResult(
            ok=False,
            reject_reason=(f"d_balts_{d.d_balts}_>_multi_max_"
                           f"{MULTI_BALL_MAX_BALLS}"))
    if d.d_wkt > MULTI_BALL_MAX_WKT:
        return ValidationResult(
            ok=False,
            reject_reason=(f"d_wkt_{d.d_wkt}_>_multi_max_"
                           f"{MULTI_BALL_MAX_WKT}"))

    # Per-ball score ceilings
    if d.d_balts == 0 and d.d_score > NO_LEGAL_BALL_MAX_SCORE:
        return ValidationResult(
            ok=False,
            reject_reason=(f"d_score_{d.d_score}_on_0_legal_balls_>_"
                           f"max_{NO_LEGAL_BALL_MAX_SCORE}"))
    if d.d_balts == 1 and d.d_score > SINGLE_BALL_MAX_SCORE:
        return ValidationResult(
            ok=False,
            reject_reason=(f"d_score_{d.d_score}_on_1_ball_>_"
                           f"max_{SINGLE_BALL_MAX_SCORE}"))
    if d.d_balts > 1:
        per_ball_max = 7 * d.d_balts + 5    # 7/ball + 5 stacked extras
        if d.d_score > per_ball_max:
            return ValidationResult(
                ok=False,
                reject_reason=(f"d_score_{d.d_score}_on_{d.d_balts}"
                               f"_balls_>_max_{per_ball_max}"))

    # Bowler invariants (skip if bowler strip wasn't visible)
    if d.d_bwl_balls is not None:
        if d.d_bwl_balls < 0:
            return ValidationResult(
                ok=False, reject_reason="d_bwl_balls_negative")
        # Δbwl_balls ≤ Δlegal_balls (over change can show fewer balls
        # for the new bowler than the total bowled in the gap).
        if d.d_bwl_balls > d.d_balts:
            return ValidationResult(
                ok=False,
                reject_reason=(f"d_bwl_balls_{d.d_bwl_balls}_>_"
                               f"d_balts_{d.d_balts}"))
    if d.d_bwl_wkt is not None:
        if d.d_bwl_wkt < 0:
            return ValidationResult(
                ok=False, reject_reason="d_bwl_wkt_negative")
        if d.d_bwl_wkt > d.d_wkt:
            return ValidationResult(
                ok=False,
                reject_reason=(f"d_bwl_wkt_{d.d_bwl_wkt}_>_"
                               f"d_wkt_{d.d_wkt}"))
    if d.d_bwl_runs is not None:
        if d.d_bwl_runs < 0:
            return ValidationResult(
                ok=False, reject_reason="d_bwl_runs_negative")
        # Bowler only charged for runs off the bat + wides + no-balls;
        # byes / leg-byes bypass the bowler.
        if d.d_bwl_runs > d.d_score:
            return ValidationResult(
                ok=False,
                reject_reason=(f"d_bwl_runs_{d.d_bwl_runs}_>_"
                               f"d_score_{d.d_score}"))

    # Striker invariants
    if d.d_str_runs is not None:
        if d.d_str_runs < 0:
            return ValidationResult(
                ok=False, reject_reason="d_str_runs_negative")
        if d.d_str_runs > d.d_score:
            return ValidationResult(
                ok=False,
                reject_reason=(f"d_str_runs_{d.d_str_runs}_>_"
                               f"d_score_{d.d_score}"))
    if d.d_str_balls is not None:
        if d.d_str_balls < 0:
            return ValidationResult(
                ok=False, reject_reason="d_str_balls_negative")
        # Δstr_balls ≤ Δlegal_balls.  Equality is the single-ball case;
        # in multi-ball gaps the visible striker may have only faced a
        # subset (e.g. struck a single mid-over and rotated out).
        if d.d_str_balls > d.d_balts:
            return ValidationResult(
                ok=False,
                reject_reason=(f"d_str_balls_{d.d_str_balls}_>_"
                               f"d_balts_{d.d_balts}"))

    return ValidationResult(ok=True)


def _infer_partial_event(d: Diff) -> str:
    """Best-effort event classification from (Δscore, Δbalts, Δwkt) only.

    Used when one or more striker/bowler deltas are missing.  Mirrors
    the existing ScoreManager._infer_event coarse logic so this module
    stays the single source of truth for event names.
    """
    if d.d_balts > 1:
        return "DEFERRED_MULTI"
    if d.d_wkt >= 1:
        return "WICKET"
    if d.d_balts == 0 and d.d_score > 0:
        return "EXTRA"      # WIDE / NB / NB+bat — broadcast resolves
    if d.d_balts == 1:
        if d.d_score == 0:
            return "DOT"
        if d.d_score == 4:
            return "FOUR"
        if d.d_score == 6:
            return "SIX"
        return "RUNS"
    return "UNKNOWN"



# ── Gap-token inference (2026-05-14, unified across 5 sites) ──────────
#
# When a gap is detected — cold-start mid-over join, MULTI_BALL skip,
# broadcast cutaway — we know N balls were bowled and the team-score
# delta but not the per-ball detail.  Producing ``?`` placeholders
# loses information (the score delta) and produces visually noisy UI;
# applying a cricket-domain heuristic for the most-likely distribution
# matches what a human commentator would assume.
#
# The single function below is the source of truth, called by:
#   - score_manager._accept_initial cold-start seed
#   - score_manager._apply_event MULTI_BALL handler
#   - score_manager._accumulate_stats_from_event MULTI_BALL bowler decomp
#   - eyes/this_over.initialize_mid_over cold-start seed
#   - eyes/this_over MULTI_BALL handler
#
# Heuristic (boundary-biased): for total_runs in (4, 6) attribute all
# runs to the LAST ball (matches the >85% case for those exact totals);
# for total_runs <= n_balls distribute as dots + singles; for
# intermediate cases use a single boundary + singles; cap any single
# ball at 6 (cricket legal maximum without no-ball).  Wickets are
# overlaid onto the last N positions.
try:
    import trace_emitter as _trace
except ImportError:
    _trace = None


def _cold_start_infer_gap_tokens(n_balls: int, total_runs: int,
                                 total_wickets: int = 0) -> list[str]:
    """Distribute total_runs across n_balls using a cricket-domain heuristic.

    Returns a list of length ``n_balls`` with tokens drawn from
    ``{'.', '1'-'6', 'W'}``.  Pure function; safe to call from any
    state-writer site.
    """
    if n_balls <= 0:
        return []
    total_runs = max(0, int(total_runs or 0))
    total_wickets = max(0, int(total_wickets or 0))
    tokens: list[str]
    if total_runs in (4, 6):
        tokens = ["."] * (n_balls - 1) + [str(total_runs)]
    elif total_runs <= n_balls:
        n_singles = total_runs
        n_dots = n_balls - n_singles
        tokens = ["."] * n_dots + ["1"] * n_singles
    elif total_runs <= 6 * n_balls:
        # Front-load singles, end with a single boundary that absorbs
        # whatever's left (capped at 6 per cricket legal max).
        tokens = []
        remaining = total_runs
        # Max singles before boundary: balls - 1 (last ball is boundary)
        front_singles = min(n_balls - 1, max(0, remaining - 6))
        if front_singles > 0:
            tokens.extend(["1"] * front_singles)
            remaining -= front_singles
        tokens.append(str(min(remaining, 6)))
        remaining -= min(remaining, 6)
        # Pad fronts with dots if we still have room (rare).
        while len(tokens) < n_balls:
            tokens.insert(0, ".")
        # If we somehow overflowed (shouldn't given the cap), trim.
        tokens = tokens[:n_balls]
    else:
        # Above 6 * n_balls is physically impossible without no-balls;
        # mark every ball as 6 and emit the cap so it's auditable.
        tokens = ["6"] * n_balls
    if total_wickets > 0:
        for i in range(total_wickets):
            idx = n_balls - 1 - i
            if 0 <= idx < n_balls:
                tokens[idx] = "W"
    if _trace is not None:
        try:
            _trace.get_recorder().record(
                tag="GAP-TOKEN-INFERENCE",
                n_balls=n_balls,
                total_runs=total_runs,
                total_wickets=total_wickets,
                tokens=list(tokens))
        except Exception:
            pass
    return tokens


