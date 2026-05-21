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


def assert_w_symbol_at_wicket(records: list) -> Result:
    """B1 / surface_pair_defect_class_family §2.1 detector. For every
    wicket event, the This Over panel symbol at the wicket-ball
    coordinate must remain ``W`` in the immediately following trace
    record (i.e., not revert to ``.`` or ``?`` post-commit).

    Wicket-event detection has two paths:

    - **Primary:** ``scorer.decisions[].tag == 'trace_beta_sm_wicket_dispatch'``
      with ``overs`` payload (typed emission restored in C19A3,
      populated by replays captured after that commit).
    - **Fallback:** ``ui_after.fow_count`` strictly increased relative
      to the previous record. Used for traces captured before C19A3
      landed (including validate_dckkr_20260521_155356, the C20-anchor
      replay). The wicket's over.ball is read from
      ``ui_after.scorecard.overs`` on the same record.

    Baseline expectation against validate_dckkr_20260521_155356:
    FAIL with 3 W→· (or W→?) reverts (Rahul ov 5.0, Rana ov 8.0,
    Rizvi ov 9.5 — observed at Obs 4 / Obs 11 / Obs 17b in
    validate_dckkr_replay_observations.md).
    """
    failures: list[dict] = []
    for i, rec in enumerate(records):
        detected_overs: str | None = None
        for dec in _decisions(rec):
            if dec.get("tag") == "trace_beta_sm_wicket_dispatch":
                detected_overs = str(dec.get("overs") or "") or None
                break
        if detected_overs is None:
            be = rec.get("ball_event") or {}
            if be.get("type") == "WICKET":
                ov_val = be.get("over")
                if ov_val:
                    detected_overs = str(ov_val)

        if not detected_overs or "." not in detected_overs:
            continue
        try:
            ball_within = int(detected_overs.split(".", 1)[1])
        except (ValueError, IndexError):
            continue
        # X.0 notation in pipeline means end-of-over wicket (6th legal
        # ball of the just-completed over). Treat as last array slot.
        expected_position = 5 if ball_within == 0 else ball_within - 1
        if expected_position < 0:
            continue

        if i + 1 >= len(records):
            failures.append({
                "frame": rec.get("frame"),
                "overs": detected_overs,
                "reason": "no_next_record",
            })
            continue
        next_this_over = (
            (records[i + 1].get("ui_after") or {}).get("this_over") or [])
        # Lenient position check: extras (Wd/Nb) shift the wicket ball's
        # array position downstream. W must appear at expected_position
        # OR later in the array (i.e., the wicket symbol is preserved
        # somewhere at-or-past the legal-ball coordinate).
        window = next_this_over[expected_position:]
        if "W" not in window:
            failures.append({
                "frame": rec.get("frame"),
                "overs": detected_overs,
                "expected_position": expected_position,
                "expected": "W",
                "next_this_over": next_this_over,
                "window": window,
            })

    if failures:
        return _fail(
            class_name="w_symbol_at_wicket_revert",
            count=len(failures),
            samples=failures[:5])
    return _ok()


def assert_fow_name_matches_striker_at_wicket(records: list) -> Result:
    """B2 / surface_pair_defect_class_family §2.5 detector — INTERNAL-
    CONSISTENCY VARIANT. For every wicket event, the dismissed-batter
    identity recorded at the wicket frame must equal the striker pointer
    at the immediately preceding frame (i.e., the batter who faced the
    wicket ball per the pipeline's own pre-wicket state).

    Detection priority:
      1. ``scorer.decisions[].tag == 'trace_beta_sm_wicket_dispatch'``
         with payload ``dismissed`` (typed emission restored in C19A3,
         populated by replays captured after that commit).
      2. ``ball_event.type == 'WICKET'`` with
         ``ball_event.striker_this_ball`` (fallback for pre-C19A3
         captured traces — same wicket signal used by
         ``assert_sm_wicket_dispatch_invariant``).

    Striker-pointer source: previous record's ``pipeline.striker``.

    SCOPE LIMITATION — DOES NOT TEST CRICKET GROUND TRUTH.
      If pipeline's striker pointer was internally consistent with its
      FOW name commit (e.g., both surfaces stale because of rotation-
      lock starvation from sm_as_orchestrator_design.md §7.1), this
      assertion PASSES while cricket reality still diverges. The
      validate_dckkr_20260521_155356 replay observed 3/3 cricket-vs-
      pipeline misattributions (Obs 16/18/19/21 of
      validate_dckkr_replay_observations.md), but those are reality-
      vs-pipeline divergences; this assertion only measures pipeline-
      internal consistency between two adjacent state surfaces.
      Cricket ground-truth assertion infrastructure is workstream D
      (rotation-root revisit, scoped as separate from B per C19/B2
      scope note).

    Baseline expectation against validate_dckkr_20260521_155356:
      Unknown a priori — depends on whether rotation-lock starvation
      corrupts both surfaces simultaneously (PASS) or only one (FAIL).
      Treat the actual FAIL count as an empirical finding: a low
      count means internal consistency holds even when reality
      diverges, which would prioritize workstream D over further
      assertion work on this surface pair.
    """
    failures: list[dict] = []
    for i, rec in enumerate(records):
        dismissed: str | None = None
        for dec in _decisions(rec):
            if dec.get("tag") == "trace_beta_sm_wicket_dispatch":
                d_val = dec.get("dismissed")
                if d_val:
                    dismissed = str(d_val)
                break
        if dismissed is None:
            be = rec.get("ball_event") or {}
            if be.get("type") == "WICKET":
                sb_val = be.get("striker_this_ball")
                if sb_val:
                    dismissed = str(sb_val)
        if not dismissed:
            continue

        if i == 0:
            failures.append({
                "frame": rec.get("frame"),
                "dismissed": dismissed,
                "reason": "no_preceding_frame",
            })
            continue
        prev = records[i - 1]
        prev_striker = (prev.get("pipeline") or {}).get("striker")
        if not prev_striker:
            failures.append({
                "frame": rec.get("frame"),
                "dismissed": dismissed,
                "prev_frame": prev.get("frame"),
                "reason": "no_prev_striker",
            })
            continue
        if str(prev_striker).strip().lower() != dismissed.strip().lower():
            failures.append({
                "frame": rec.get("frame"),
                "ts_match": rec.get("ts_match"),
                "dismissed": dismissed,
                "prev_striker": prev_striker,
            })

    if failures:
        return _fail(
            class_name="fow_name_striker_mismatch_internal",
            count=len(failures),
            samples=failures[:5])
    return _ok()


_EXPLICITLY_NOT_BOWLER_CREDITED = frozenset({
    "run_out", "run-out", "runout",
    "retired_hurt", "retired-hurt", "retired",
    "obstructing_the_field", "obstructing-the-field",
    "hit_the_ball_twice", "hit-the-ball-twice",
    "timed_out", "timed-out",
})


def assert_bowler_w_increment_on_dispatch(records: list) -> Result:
    """B3 / surface_pair_defect_class_family §2.6 detector. For every
    wicket event, a BOWL-DELTA with ``+wkts >= 1`` must fire for the
    current bowler within a frame window after the wicket dispatch,
    unless the dismissal type is explicitly NOT bowler-credited per
    cricket rules.

    Detection priority:
      1. ``scorer.decisions[].tag == 'trace_beta_sm_wicket_dispatch'``
         with payload ``dismissed`` / ``wicket_type`` / ``bowler``
         (typed emission added in C19A3).
      2. ``ball_event.type == 'WICKET'`` with
         ``ball_event.dismissal_mode`` and ``pipeline.current_bowler``
         (fallback for pre-C19A3 captured traces — same wicket signal
         as the B1/B2 fallbacks).

    Dismissal-type gating — LENIENT (intentional).
      FAILs unless the dismissal type is in an explicit
      not-bowler-credited list (run-outs, retired-hurt, obstructing-
      the-field, hit-the-ball-twice, timed-out). Unknown/None
      dismissal modes are treated as "should-be-credited" because
      pipeline's broadcast-extraction frequently emits None for
      wickets that ARE bowler-credited in cricket reality
      (Obs 17/18/19/21 of validate_dckkr_replay_observations.md
      observed 3/3 None-dismissal wickets that cricket-truth requires
      crediting). Strict gating (only the
      ``_BOWLER_CREDITED_DISMISSALS`` set from score_manager.py:71)
      would mask these by skipping them. The C19/B2 scope guard
      explicitly authorized this lenient framing.

    Window: search ``records[i..i+30]`` for a BOWL-DELTA whose bowler
    matches AND whose ``+wkts`` field is ``>= 1``. 30 frames ≈ 5-7
    cricket balls at ~1Hz scout cadence, matching
    ``_PENDING_WICKET_MAX_FRAME_LAG`` from score_manager.py.

    Baseline expectation against validate_dckkr_20260521_155356:
      Obs 17/19/21 observed 3/3 bowler-W omissions in cricket reality.
      Empirical trace count: ``+wkts >= 1`` BOWL-DELTA records = 0
      across the entire replay. Predicted FAIL = (number of detected
      wickets) minus (explicitly-not-credited cases). On this trace
      the wicket count is 4 (Rahul/Rana/Nissanka/Patel — see
      assert_sm_wicket_dispatch_invariant FAIL output) and all four
      come in with bowler-credited or None dismissal modes, so the
      lenient gate predicts FAIL × 4.
    """
    pat = re.compile(
        r"BOWL-DELTA\] (\S.+?) \+runs=(-?\d+) \+balls=(-?\d+) "
        r"\+wkts=(-?\d+) → ")
    LOOKAHEAD = 30
    failures: list[dict] = []
    for i, rec in enumerate(records):
        dismissed: str | None = None
        wicket_type: str | None = None
        bowler_from_payload: str | None = None
        for dec in _decisions(rec):
            if dec.get("tag") == "trace_beta_sm_wicket_dispatch":
                if dec.get("dismissed"):
                    dismissed = str(dec.get("dismissed"))
                if dec.get("wicket_type"):
                    wicket_type = str(dec.get("wicket_type"))
                if dec.get("bowler"):
                    bowler_from_payload = str(dec.get("bowler"))
                break
        if dismissed is None:
            be = rec.get("ball_event") or {}
            if be.get("type") == "WICKET":
                if be.get("striker_this_ball"):
                    dismissed = str(be.get("striker_this_ball"))
                if be.get("dismissal_mode"):
                    wicket_type = str(be.get("dismissal_mode"))
        if not dismissed:
            continue

        wt_norm = wicket_type.strip().lower() if wicket_type else None
        if wt_norm and wt_norm in _EXPLICITLY_NOT_BOWLER_CREDITED:
            continue

        bowler = bowler_from_payload or (
            (rec.get("pipeline") or {}).get("current_bowler"))
        if not bowler:
            failures.append({
                "frame": rec.get("frame"),
                "dismissed": dismissed,
                "wicket_type": wicket_type,
                "reason": "no_current_bowler",
            })
            continue

        bowler_norm = bowler.strip().lower()
        credited = False
        for j in range(i, min(i + LOOKAHEAD + 1, len(records))):
            for dec in _decisions(records[j]):
                if dec.get("tag") != "BOWL-DELTA":
                    continue
                msg = dec.get("raw_message") or ""
                mm = pat.search(msg)
                if not mm:
                    continue
                if mm.group(1).strip().lower() != bowler_norm:
                    continue
                if int(mm.group(4)) >= 1:
                    credited = True
                    break
            if credited:
                break

        if not credited:
            failures.append({
                "frame": rec.get("frame"),
                "ts_match": rec.get("ts_match"),
                "dismissed": dismissed,
                "wicket_type": wicket_type,
                "bowler": bowler,
            })

    if failures:
        return _fail(
            class_name="bowler_w_increment_missing_on_dispatch",
            count=len(failures),
            samples=failures[:5])
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
    ("trace_gamma_w_symbol_at_wicket",
     assert_w_symbol_at_wicket),
    ("trace_gamma_fow_name_matches_striker_at_wicket",
     assert_fow_name_matches_striker_at_wicket),
    ("trace_gamma_bowler_w_increment_on_dispatch",
     assert_bowler_w_increment_on_dispatch),
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
