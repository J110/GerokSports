"""Symptom-class assertion library — Stage 4 prep.

Each function encodes one observed-class invariant against the ledger
ground truth and the SM-emitted WS payload. Returns
(pass: bool, divergence: dict | None) for use in test harnesses.

Classes 1-12 per the conversation enumeration. A fix to a given class
is verified by:
  (a) baseline L2 captured-replay stays 30/30 green
  (b) the specific symptom assertion flips from FAIL to PASS

Convention: each function takes (ledger_ball, ws_payload) plus optional
history (prior balls + payloads) for class-9-style cross-ball checks.
"""
from __future__ import annotations

import re
from typing import Any, Optional


Result = tuple[bool, Optional[dict]]


def _ok() -> Result:
    return True, None


def _fail(**kw) -> Result:
    return False, dict(kw)


def _ball_in_over(ball_id: str) -> tuple[int, int]:
    """'3.2' → (3, 2)."""
    m = re.match(r"^(\d+)\.(\d+)$", str(ball_id))
    if not m:
        return -1, -1
    return int(m.group(1)), int(m.group(2))


def _legal_balls_of(ball_id: str) -> int:
    o, b = _ball_in_over(ball_id)
    if o < 0:
        return -1
    return o * 6 + b


# ------------------------------------------------------------------
# Class 1 — cold-start phantom
# ------------------------------------------------------------------

def assert_no_cold_start_phantom(
    ledger_ball: dict, ws_payload: dict,
) -> Result:
    """After cold-start exit, this_over length must match ball_in_over.

    At ball N.M, this_over should have exactly M legal entries
    (1-indexed). A 'phantom' is an extra token beyond the actual
    M committed balls.
    """
    ball_id = ledger_ball.get("ball_id") or ""
    over_n, ball_in_over = _ball_in_over(ball_id)
    if over_n < 0:
        return _ok()
    this_over = ws_payload.get("this_over") or []
    # Filter out legal-ball tokens only (drop Wd/Nb extras — they
    # don't increment legal-ball count). Tokens are in
    # {".", "1", "2", "3", "4", "5", "6", "W", "Wd", "Nb"}.
    legal_tokens = [t for t in this_over
                    if t not in ("Wd", "Nb", "?")]
    if len(legal_tokens) != ball_in_over:
        return _fail(
            class_name="cold_start_phantom",
            ball_id=ball_id,
            expected_legal_tokens=ball_in_over,
            actual_legal_tokens=len(legal_tokens),
            this_over=this_over,
        )
    return _ok()


# ------------------------------------------------------------------
# Class 2 — bowler totals consistent
# ------------------------------------------------------------------

def assert_bowler_totals_consistent(
    ledger_ball: dict, ws_payload: dict,
) -> Result:
    """sum(bowling_card[*].balls) == total team legal balls so far."""
    ball_id = ledger_ball.get("ball_id") or ""
    legal_so_far = _legal_balls_of(ball_id)
    if legal_so_far < 0:
        return _ok()
    bowling_card = (
        ws_payload.get("bowling_card")
        or (ws_payload.get("expected_state_after") or {}).get("bowling_card")
        or {})
    if not bowling_card:
        return _ok()
    total = 0
    for _, row in bowling_card.items():
        b = row.get("balls") or 0
        try:
            total += int(b)
        except (TypeError, ValueError):
            pass
    if total != legal_so_far:
        return _fail(
            class_name="bowler_totals_inconsistent",
            ball_id=ball_id,
            expected_total_balls=legal_so_far,
            actual_total_balls=total,
            bowling_card_balls={
                name: row.get("balls")
                for name, row in bowling_card.items()},
        )
    return _ok()


# ------------------------------------------------------------------
# Class 3 / 12 — wicket token in this_over (when wicket)
# ------------------------------------------------------------------

def assert_wicket_token_in_this_over(
    ledger_ball: dict, ws_payload: dict,
) -> Result:
    if not ledger_ball.get("wicket"):
        return _ok()
    ball_id = ledger_ball.get("ball_id") or ""
    over_n, ball_in_over = _ball_in_over(ball_id)
    if ball_in_over < 1:
        return _ok()
    this_over = ws_payload.get("this_over") or []
    # Locate the slot for this ball (filter to legal tokens only)
    legal_only = [t for t in this_over if t not in ("Wd", "Nb", "?")]
    if len(legal_only) < ball_in_over:
        return _fail(
            class_name="wicket_token_missing_short_this_over",
            ball_id=ball_id,
            this_over=this_over,
        )
    token = legal_only[ball_in_over - 1]
    if token != "W":
        return _fail(
            class_name="wicket_token_missing",
            ball_id=ball_id,
            expected_token="W",
            actual_token=token,
            this_over=this_over,
        )
    return _ok()


# ------------------------------------------------------------------
# Class 4 — wicket overs match ledger
# ------------------------------------------------------------------

def assert_wicket_overs_match(
    ledger_ball: dict, ws_payload: dict,
    prior_wickets: list[dict] | None = None,
) -> Result:
    fow = ws_payload.get("fall_of_wickets") or []
    if not fow:
        return _ok()
    expected_overs = [
        w.get("overs") for w in (prior_wickets or [])
        if w.get("overs")
    ]
    if ledger_ball.get("wicket"):
        expected_overs.append(ledger_ball.get("ball_id"))
    actual_overs = [str(e.get("overs")) for e in fow if e.get("overs")]
    if len(actual_overs) != len(expected_overs):
        return _fail(
            class_name="wicket_overs_count_mismatch",
            expected_count=len(expected_overs),
            actual_count=len(actual_overs),
            expected_overs=expected_overs,
            actual_overs=actual_overs,
        )
    for exp, got in zip(expected_overs, actual_overs):
        if str(exp) != str(got):
            return _fail(
                class_name="wicket_overs_value_mismatch",
                expected=exp, actual=got,
            )
    return _ok()


# ------------------------------------------------------------------
# Class 5 — bowler card continuity
# ------------------------------------------------------------------

def assert_bowler_card_continuity(
    ledger_ball: dict, ws_payload: dict,
) -> Result:
    bowling_card = ws_payload.get("bowling_card") or {}
    placeholders = []
    for name, row in bowling_card.items():
        nm = str(name).strip().lower()
        if not nm or nm in ("awaiting", "—", "?", "none", "null"):
            placeholders.append(name)
        rn = (row.get("name") if isinstance(row, dict) else None)
        if rn and str(rn).strip().lower() in ("awaiting", "—", "?"):
            placeholders.append(rn)
    if placeholders:
        return _fail(
            class_name="bowler_card_placeholder",
            placeholders=placeholders,
            bowling_card_keys=list(bowling_card.keys()),
        )
    return _ok()


# ------------------------------------------------------------------
# Class 6 — over_history matches ledger
# ------------------------------------------------------------------

def assert_over_history_matches_ledger(
    ledger_ball: dict, ws_payload: dict,
) -> Result:
    ledger_oh = (
        (ledger_ball.get("expected_state_after") or {})
        .get("over_history") or {})
    ws_oh = ws_payload.get("over_history") or {}
    ball_id = ledger_ball.get("ball_id") or ""
    over_n, _ = _ball_in_over(ball_id)
    if over_n < 0:
        return _ok()
    # Only compare completed overs (< current over).
    mismatches = {}
    for k in range(0, over_n):
        exp = ledger_oh.get(str(k)) or ledger_oh.get(k)
        got = ws_oh.get(str(k)) or ws_oh.get(k)
        if exp is None:
            continue
        if got != exp:
            mismatches[k] = {"expected": exp, "actual": got}
    if mismatches:
        return _fail(
            class_name="over_history_mismatch",
            ball_id=ball_id,
            mismatches=mismatches,
        )
    return _ok()


# ------------------------------------------------------------------
# Class 7 — this_over real-time (no permanent ?)
# ------------------------------------------------------------------

def assert_this_over_real_time(
    ledger_ball: dict, ws_payload: dict,
) -> Result:
    this_over = ws_payload.get("this_over") or []
    placeholders = [i for i, t in enumerate(this_over) if t == "?"]
    if placeholders:
        return _fail(
            class_name="this_over_placeholder",
            ball_id=ledger_ball.get("ball_id"),
            placeholder_slots=placeholders,
            this_over=this_over,
        )
    return _ok()


# ------------------------------------------------------------------
# Class 8 — partnership matches score
# ------------------------------------------------------------------

def assert_partnership_matches_score(
    ledger_ball: dict, ws_payload: dict,
    last_wicket_score: int = 0,
) -> Result:
    score = ws_payload.get("score")
    if score is None:
        score = (ws_payload.get("expected_state_after") or {}).get("score")
    partnership = ws_payload.get("partnership_current") or {}
    p_runs = partnership.get("runs")
    if score is None or p_runs is None:
        return _ok()
    expected = int(score) - int(last_wicket_score)
    if int(p_runs) != expected:
        return _fail(
            class_name="partnership_score_mismatch",
            ball_id=ledger_ball.get("ball_id"),
            score=score,
            last_wicket_score=last_wicket_score,
            partnership_runs=p_runs,
            expected_partnership=expected,
        )
    return _ok()


# ------------------------------------------------------------------
# Class 9 — striker indicator matches deterministic rotation
# ------------------------------------------------------------------

def assert_striker_indicator_matches_rotation(
    ledger_ball: dict, ws_payload: dict,
) -> Result:
    expected_striker = (
        (ledger_ball.get("expected_state_after") or {})
        .get("striker_after_rotation"))
    actual_striker = (
        ws_payload.get("striker")
        or (ws_payload.get("scorecard") or {}).get("striker"))
    if not expected_striker or not actual_striker:
        return _ok()
    if str(actual_striker).strip() != str(expected_striker).strip():
        return _fail(
            class_name="striker_rotation_mismatch",
            ball_id=ledger_ball.get("ball_id"),
            expected=expected_striker,
            actual=actual_striker,
        )
    return _ok()


# ------------------------------------------------------------------
# Class 10 / 11 — score matches ledger at each ball
# ------------------------------------------------------------------

def assert_score_matches_ledger(
    ledger_ball: dict, ws_payload: dict,
) -> Result:
    expected = (
        ledger_ball.get("expected_state_after") or {}).get("score")
    actual = ws_payload.get("score")
    if actual is None:
        actual = (ws_payload.get("expected_state_after") or {}).get("score")
    if expected is None or actual is None:
        return _ok()
    if int(actual) != int(expected):
        return _fail(
            class_name="score_mismatch",
            ball_id=ledger_ball.get("ball_id"),
            expected=expected, actual=actual,
        )
    return _ok()


# ------------------------------------------------------------------
# Class 12 — dismissed batter identity correct
# ------------------------------------------------------------------

def assert_dismissed_batter_correct(
    ledger_ball: dict, ws_payload: dict,
) -> Result:
    if not ledger_ball.get("wicket"):
        return _ok()
    expected_name = (
        (ledger_ball.get("wicket") or {}).get("dismissed_name"))
    fow = ws_payload.get("fall_of_wickets") or []
    if not fow or not expected_name:
        return _ok()
    last = fow[-1]
    actual = (last.get("batter") or last.get("batter_name")
              or last.get("dismissed_name"))
    if not actual:
        return _ok()
    if str(actual).strip().lower() != str(expected_name).strip().lower():
        return _fail(
            class_name="dismissed_batter_mismatch",
            ball_id=ledger_ball.get("ball_id"),
            expected=expected_name,
            actual=actual,
        )
    return _ok()


# ------------------------------------------------------------------
# Orchestrator
# ------------------------------------------------------------------

ASSERTIONS = [
    ("class_1_cold_start_phantom", assert_no_cold_start_phantom),
    ("class_2_bowler_totals", assert_bowler_totals_consistent),
    ("class_3_12_wicket_token", assert_wicket_token_in_this_over),
    ("class_4_wicket_overs", assert_wicket_overs_match),
    ("class_5_bowler_card_continuity", assert_bowler_card_continuity),
    ("class_6_over_history", assert_over_history_matches_ledger),
    ("class_7_this_over_realtime", assert_this_over_real_time),
    ("class_8_partnership", assert_partnership_matches_score),
    ("class_9_striker_rotation",
     assert_striker_indicator_matches_rotation),
    ("class_10_11_score", assert_score_matches_ledger),
    ("class_12_dismissed_batter", assert_dismissed_batter_correct),
]


def run_all_assertions(
    ledger_ball: dict, ws_payload: dict,
    context: dict | None = None,
) -> list[tuple[str, bool, Optional[dict]]]:
    """Run every assertion. Returns list of (name, pass, divergence)."""
    ctx = context or {}
    out: list[tuple[str, bool, Optional[dict]]] = []
    for name, fn in ASSERTIONS:
        try:
            sig = fn.__code__.co_varnames[:fn.__code__.co_argcount]
            kwargs: dict[str, Any] = {}
            if "prior_wickets" in sig:
                kwargs["prior_wickets"] = ctx.get("prior_wickets") or []
            if "last_wicket_score" in sig:
                kwargs["last_wicket_score"] = ctx.get(
                    "last_wicket_score", 0)
            res = fn(ledger_ball, ws_payload, **kwargs)
            ok, div = res
            out.append((name, bool(ok), div))
        except Exception as e:
            out.append((name, False, {
                "class_name": "assertion_exception",
                "error": f"{type(e).__name__}: {e}",
            }))
    return out
