"""Trace-session assertion library — empirically grounded invariants.

Five session-aggregate assertions surfaced from the post-session
analysis of `validate_gtrr_20260520_180715` (see
`files/docs/investigations/sm_as_orchestrator_design.md` for the
audit chain that produced these). Each captures one bug class that
production data showed exists right now:

- B-α  multi-ball gap bowler credit lost
- B-β  SM-side wicket dispatch missed (BED detects, SM emits DOT/None)
- B-ε  cold-start initial-striker mis-resolution
- (compound-token encoding artifact, e.g. `Wd+3`, `Wd+5`)
- (extras_total UI inconsistency with archived wide/no-ball tokens)

Granularity: each function takes a list of trace records (one per
processed frame) plus optional ledger context, walks the records,
and returns `Result = (pass: bool, divergence: dict | None)`.

Baseline against `validate_gtrr_20260520_180715` is broken-but-known.
Each assertion documents the expected baseline failure shape. Future
commits gate against not-getting-worse — see
`files/scripts/run_trace_session_assertions.py` for the runner.

Cascade-closure pattern (2026-05-20). These assertions are
empirically-grounded regression detectors, NOT independent bug
classes. Some may flip simultaneously when a root-cause fix lands.
Most notable demonstration: F1 (commit 437d952) — a one-line
field-name fix in `_accept_initial` — closes at minimum FOUR bug
classes when measured against the captured Scout dump for
validate_gtrr_20260520_180715:

  1. B-ε direct (initial striker mis-resolution)
  2. B-β cascade (SM wicket dispatch missed)
  3. Multi-ball decomposition false positives (5 events → 0)
  4. Compound tokens (`Wd+N`) (2 → 0)

The audit-driven discipline that produced this result has a
documented track record of preventing engineering capacity from
being spent on cascade symptoms (Queue B reclassified Keep,
_ScoutRetryBuffer Keep, S5a NOT-A-DEFECT, S5b-2 deletion shipped,
B-ζ falsified, B-β cascade closed via F1).

Cross-fixture verification step (now standing precondition per
sm_as_orchestrator_design.md §7.2 gate 7): when a fix commit
lands, replay the relevant captured Scout dump and re-run these
assertions to check which OTHER bug-class hypotheses no longer
reproduce. Cascade-closure findings update the workstream queue,
not the engineering queue. Each assertion's flip should be
cross-verified against captured replay before declaring resolved.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional


Result = tuple[bool, Optional[dict]]


def _ok() -> Result:
    return True, None


def _fail(**kw) -> Result:
    return False, dict(kw)


def _decisions(rec: dict) -> Iterable[dict]:
    return ((rec.get("scorer") or {}).get("decisions") or [])


def _last_ts_match(records: list) -> str | None:
    for r in reversed(records):
        tm = r.get("ts_match")
        if tm:
            return tm
    return None


def _team_score_wickets(ts_match: str | None) -> tuple[int | None, int | None]:
    if not ts_match:
        return None, None
    m = re.search(r"(\d+)-(\d+)", ts_match)
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def _final_extras_total(records: list) -> int | None:
    for r in reversed(records):
        ui = r.get("ui_after") or {}
        et = ui.get("extras_total")
        if et is not None:
            return int(et)
    return None


def _running_bowler_runs(records: list) -> dict[str, int]:
    """Latest BOWL-DELTA → runs per bowler."""
    pat = re.compile(
        r"BOWL-DELTA\] (\S.+?) \+runs=(-?\d+) \+balls=(-?\d+) "
        r"\+wkts=(-?\d+) → runs=(\d+) overs=(\S+) wkts=(\d+)")
    totals: dict[str, int] = {}
    for r in records:
        for d in _decisions(r):
            if d.get("tag") != "BOWL-DELTA":
                continue
            msg = d.get("raw_message", "") or ""
            mm = pat.search(msg)
            if mm:
                totals[mm.group(1).strip()] = int(mm.group(5))
    return totals


def _count_wd_nb_tokens_in_archives(records: list) -> int:
    """Sum of Wd/Nb tokens written via OVER-ARCHIVE-WRITE."""
    n = 0
    for r in records:
        for d in _decisions(r):
            if d.get("tag") != "OVER-ARCHIVE-WRITE":
                continue
            tokens = d.get("tokens") or []
            for t in tokens:
                s = str(t)
                if s in ("Wd", "Nb"):
                    n += 1
                if "+" in s:
                    n += 1
    return n


def assert_bowler_runs_sum_matches_team_score(
        records: list,
        max_acceptable_extras: int | None = None) -> Result:
    """B-α detector. Sum of per-bowler runs + extras should equal team score.

    A gap larger than the documented extras count signals lost-credit
    cases (typically multi-ball gap bowler-credit drops). The
    ``max_acceptable_extras`` parameter is the upper bound on extras
    we tolerate; if None, we use the trace's own
    ``ui_after.extras_total`` final value.
    """
    score, _ = _team_score_wickets(_last_ts_match(records))
    if score is None:
        return _ok()
    bowler_totals = _running_bowler_runs(records)
    sum_bowler = sum(bowler_totals.values())
    extras = _final_extras_total(records)
    if max_acceptable_extras is None:
        max_acceptable_extras = extras if extras is not None else 0
    gap = score - sum_bowler - max_acceptable_extras
    if gap > 0:
        return _fail(
            class_name="bowler_runs_sum_short",
            team_score=score,
            bowler_runs_sum=sum_bowler,
            assumed_extras=max_acceptable_extras,
            unaccounted_runs=gap,
            bowler_totals=bowler_totals)
    return _ok()


def assert_sm_wicket_dispatch_invariant(records: list) -> Result:
    """B-β detector. Every BED-detected wicket should trigger SM's
    ``_apply_wicket_fall_only`` (signalled by
    ``WICKET-FALL-ONLY-CALLED`` tag) in the same frame.

    Cross-source comparison: a ``ball_event.type == "WICKET"`` on the
    frame means BED classified a wicket; absence of
    ``WICKET-FALL-ONLY-CALLED`` on that same frame means SM did not
    enter the FOW-recording path. Either SM dispatched as DOT/None
    (mismatch) or SM was in cold-start (missed).
    """
    misses: list[dict] = []
    for r in records:
        be = r.get("ball_event") or {}
        if be.get("type") != "WICKET":
            continue
        decs = _decisions(r)
        wfoc = any(d.get("tag") == "WICKET-FALL-ONLY-CALLED" for d in decs)
        if not wfoc:
            misses.append({
                "frame": r.get("frame"),
                "ts_match": r.get("ts_match"),
                "ball_event": be,
            })
    if misses:
        return _fail(
            class_name="sm_wicket_dispatch_missed",
            count=len(misses),
            samples=misses[:5])
    return _ok()


def assert_initial_striker_matches_ledger(
        records: list,
        expected_initial_striker: str | None) -> Result:
    """B-ε detector. The first BAT-DELTA event in the session should
    credit the ground-truth initial striker.

    Caller supplies ``expected_initial_striker`` (canonical full name).
    Failure means the cold-start initial-striker resolution path picked
    the wrong batter — falsifies the S5b-3 design memo's Context A
    "already addressed" classification.
    """
    if not expected_initial_striker:
        return _ok()
    pat = re.compile(
        r"BAT-DELTA\] (\S.+?) \+runs=(-?\d+) \+balls=(-?\d+)")
    for r in records:
        for d in _decisions(r):
            if d.get("tag") != "BAT-DELTA":
                continue
            mm = pat.search(d.get("raw_message", "") or "")
            if mm and int(mm.group(3)) > 0:
                actual = mm.group(1).strip()
                if actual.lower() != expected_initial_striker.lower():
                    return _fail(
                        class_name="initial_striker_mismatch",
                        frame=r.get("frame"),
                        expected=expected_initial_striker,
                        actual=actual)
                return _ok()
    return _ok()


def assert_no_compound_tokens(records: list) -> Result:
    """Compound-token encoding artifact detector. Any
    ``THIS-OVER-APPEND`` token containing ``+`` is the artifact.

    Examples observed in validate_gtrr_20260520_180715: ``Wd+3`` at
    frame 286, ``Wd+5`` at frame 303. The pipeline should canonicalize
    these into separate per-ball events (or accept the wide as a
    single token with the runs as a separate signal), not emit a
    compound token shape.
    """
    found: list[dict] = []
    for r in records:
        for d in _decisions(r):
            if d.get("tag") != "THIS-OVER-APPEND":
                continue
            tok = str(d.get("token") or "")
            if "+" in tok:
                found.append({
                    "frame": r.get("frame"),
                    "slot_idx": d.get("slot_idx"),
                    "token": tok,
                })
    if found:
        return _fail(
            class_name="compound_token_emitted",
            count=len(found),
            samples=found[:10])
    return _ok()


def assert_extras_total_consistent(records: list) -> Result:
    """Extras-total UI inconsistency detector. The final
    ``ui_after.extras_total`` should be at least as large as the number
    of Wd/Nb/compound tokens written via ``OVER-ARCHIVE-WRITE`` across
    the session.

    Catches the case from validate_gtrr_20260520_180715 where the UI
    rendered ``extras_total=1`` while the over_history archive contained
    multiple ``Wd`` tokens.
    """
    et = _final_extras_total(records)
    archived_extras = _count_wd_nb_tokens_in_archives(records)
    if et is None:
        return _ok()
    if et < archived_extras:
        return _fail(
            class_name="extras_total_below_archived_count",
            ui_extras_total=et,
            archived_wd_nb_tokens=archived_extras,
            gap=archived_extras - et)
    return _ok()


TRACE_ASSERTIONS = [
    ("trace_alpha_bowler_runs_sum",
     assert_bowler_runs_sum_matches_team_score),
    ("trace_beta_sm_wicket_dispatch",
     assert_sm_wicket_dispatch_invariant),
    ("trace_epsilon_initial_striker",
     assert_initial_striker_matches_ledger),
    ("trace_compound_tokens",
     assert_no_compound_tokens),
    ("trace_extras_total",
     assert_extras_total_consistent),
]


def run_all_trace_assertions(
        records: list,
        context: dict | None = None,
) -> list[tuple[str, bool, Optional[dict]]]:
    """Run every trace-session assertion. Returns
    [(name, pass, divergence), ...]."""
    ctx = context or {}
    out: list[tuple[str, bool, Optional[dict]]] = []
    for name, fn in TRACE_ASSERTIONS:
        try:
            sig = fn.__code__.co_varnames[:fn.__code__.co_argcount]
            kwargs: dict[str, Any] = {}
            if "expected_initial_striker" in sig:
                kwargs["expected_initial_striker"] = ctx.get(
                    "expected_initial_striker")
            if "max_acceptable_extras" in sig:
                kwargs["max_acceptable_extras"] = ctx.get(
                    "max_acceptable_extras")
            ok, div = fn(records, **kwargs)
            out.append((name, bool(ok), div))
        except Exception as e:
            out.append((name, False, {
                "class_name": "assertion_exception",
                "error": f"{type(e).__name__}: {e}",
            }))
    return out
