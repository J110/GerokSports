"""Trace anomaly detection — nine internal-consistency rules (P1-P9)
plus P4 in advisory mode.

Per `files/docs/investigations/trace_and_detect_system_design.md` §4.
Each rule is a pure function of a sliding window of trace records;
returns zero or more ``Anomaly`` instances. The analyzer (`files/
analyze_trace.py`) walks the JSONL once, maintains per-rule state, and
collects fired anomalies into the report + the per-record
``anomalies[]`` field.

Mode-aware suppression (§4.2): rules consult ``record.pipeline.mode``
and the surrounding ``frame_type`` / ``capture.force_processed`` /
``scout.cam`` / ``ball_event`` fields before firing. COLD_START and
INNINGS_HANDOFF windows suppress most rules.

Severity labels:
    "advisory" — P4 only (per operator decision Q4); separated in
                 report; does NOT count toward Errors/Warnings.
    "info"     — P9 stuck-state.
    "warn"     — typical P1/P3/P6/P8 first-trip.
    "error"    — sustained or invariant-breaking firings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

# ── Thresholds (operator-tunable; first-cut from §4.2) ────────────


THRESHOLDS: dict[str, Any] = {
    # P1 — batter persistence after wicket (frames since wicket).
    "P1_WARN_FRAMES": 8,
    "P1_ERROR_FRAMES": 30,
    # P3 — stale bowler (overs of unchanged bowler during apparent play).
    "P3_WARN_OVERS": 2,
    "P3_ERROR_OVERS": 3,
    # P4 — partnership math tolerance (runs).
    "P4_TOLERANCE": 2,
    "P4_MIN_RECORDS": 3,
    # P5 — wickets-up without WICKET event.
    "P5_LOOKAROUND_FRAMES": 2,
    # P6 — extras inconsistency tolerance.
    "P6_TOLERANCE": 1,
    # P8 — this_over ball mismatch.
    "P8_DELTA_WARN": 2,
    "P8_DELTA_ERROR": 3,
    "P8_SUSTAIN_RECORDS": 2,
    # P9 — stuck UI field (per-field stale records before fire).
    "P9_STALE_RECORDS_SCORE": 12,
    "P9_STALE_RECORDS_THIS_OVER": 30,
    "P9_STALE_RECORDS_STRIKER": 30,
    "P9_STALE_RECORDS_NON_STRIKER": 30,
    "P9_STALE_RECORDS_BOWLER": 36,
    # Mode suppression.
    "MODE_HANDOFF_SUPPRESS_RECORDS": 60,
    "FORCE_PROCESSED_RELAX_FACTOR": 1.5,
}


# ── Anomaly + AnalyzerState ───────────────────────────────────────


@dataclass
class Anomaly:
    id: str
    severity: str  # "advisory" | "info" | "warn" | "error"
    fired_at_frame: int
    first_evidence_frame: int
    duration_frames: int
    evidence: dict[str, Any]
    verdict: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "fired_at_frame": self.fired_at_frame,
            "first_evidence_frame": self.first_evidence_frame,
            "duration_frames": self.duration_frames,
            "evidence": self.evidence,
            "verdict": self.verdict,
        }


@dataclass
class AnalyzerState:
    """Per-pipeline state carried across records."""

    last_wicket_frame: int | None = None
    last_wicket_dismissed: str | None = None
    last_wicket_at_crease: list[str] = field(default_factory=list)
    p1_open: bool = False
    p1_first_frame: int | None = None

    last_bowler_name: str | None = None
    last_bowler_change_over: float | None = None
    last_bowler_change_frame: int | None = None

    p8_delta_streak: int = 0

    field_last_changed: dict[str, int] = field(default_factory=dict)
    field_last_value: dict[str, Any] = field(default_factory=dict)
    p9_open: dict[str, bool] = field(default_factory=dict)

    last_innings: int | None = None
    last_innings_handoff_frame: int | None = None

    fired_once: set[str] = field(default_factory=set)

    # 2026-05-04 round 2/3 fix counters (Batches F/G/H/J + SHADOW).
    r23_wicket_count: int = 0
    r23_incoming_promoted_count: int = 0
    r23_overlay_lockout_breakout_count: int = 0
    r23_bowler_stats_regression_count: int = 0
    r23_undismiss_refusal_count: int = 0
    r23_shadow_score_events_zero_streak: int = 0
    r23_shadow_last_frames_received: int | None = None
    r23_shadow_last_heartbeat_frame: int | None = None


# ── Helpers ────────────────────────────────────────────────────────


def _path(rec: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = rec
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _frame(rec: dict[str, Any]) -> int:
    return int(rec.get("frame") or 0)


def _mode(rec: dict[str, Any]) -> str:
    return _path(rec, "pipeline", "mode", default="WARM") or "WARM"


def _ball_event_type(rec: dict[str, Any]) -> str | None:
    bt = _path(rec, "ball_event", "type")
    if bt in (None, "", "—"):
        return None
    return str(bt)


def _ui_at_crease_names(rec: dict[str, Any]) -> tuple[str, ...]:
    arr = _path(rec, "ui_after", "batting_card_at_crease", default=[]) or []
    return tuple(sorted(b.get("name") for b in arr if b.get("name")))


def _decisions_with_tag(rec: dict[str, Any], *tags: str) -> list[dict]:
    out = []
    for d in _path(rec, "scorer", "decisions", default=[]) or []:
        if d.get("tag") in tags:
            out.append(d)
    return out


_OVERS_RE = re.compile(r"^(\d+)\.(\d+)$")


def _ball_within_over(overs: Any) -> int | None:
    if isinstance(overs, (int, float)):
        return 0
    if not isinstance(overs, str):
        return None
    m = _OVERS_RE.match(overs)
    if not m:
        return None
    return int(m.group(2))


def _overs_to_balls(overs: Any) -> int | None:
    if isinstance(overs, (int, float)):
        return int(overs) * 6
    if not isinstance(overs, str):
        return None
    m = _OVERS_RE.match(overs)
    if not m:
        return None
    return int(m.group(1)) * 6 + int(m.group(2))


def _suppressed(rec: dict[str, Any], *, modes: tuple[str, ...]) -> bool:
    if _mode(rec) in modes:
        return True
    return False


def _bowler_name(rec: dict[str, Any]) -> str | None:
    bc = _path(rec, "ui_after", "bowling_current") or {}
    return bc.get("name")


def _score(rec: dict[str, Any]) -> int | None:
    s = _path(rec, "ui_after", "scorecard", "score")
    return int(s) if isinstance(s, (int, float)) else None


def _wickets(rec: dict[str, Any]) -> int | None:
    w = _path(rec, "ui_after", "scorecard", "wickets")
    return int(w) if isinstance(w, (int, float)) else None


def _innings(rec: dict[str, Any]) -> int | None:
    i = _path(rec, "ui_after", "innings") or _path(
        rec, "pipeline", "innings")
    return int(i) if isinstance(i, (int, float)) else None


# ── Rules ──────────────────────────────────────────────────────────


def update_innings_tracking(state: AnalyzerState,
                            rec: dict[str, Any]) -> None:
    inn = _innings(rec)
    if inn is None:
        return
    if state.last_innings is None:
        state.last_innings = inn
        return
    if inn != state.last_innings:
        state.last_innings_handoff_frame = _frame(rec)
        state.last_innings = inn


def rule_p1(state: AnalyzerState,
            rec: dict[str, Any],
            window: list[dict[str, Any]]) -> list[Anomaly]:
    """Batter persistence after wicket."""
    if _suppressed(rec, modes=("COLD_START", "INNINGS_HANDOFF")):
        state.p1_open = False
        state.p1_first_frame = None
        return []
    bt = _ball_event_type(rec)
    if bt == "WICKET":
        state.last_wicket_frame = _frame(rec)
        state.last_wicket_dismissed = _path(
            rec, "ball_event", "dismissed") or _path(
                rec, "ball_event", "striker_this_ball")
        state.last_wicket_at_crease = list(_ui_at_crease_names(rec))
        state.p1_open = True
        state.p1_first_frame = None
        return []
    if not state.p1_open or state.last_wicket_frame is None:
        return []
    current = list(_ui_at_crease_names(rec))
    if current and tuple(current) != tuple(state.last_wicket_at_crease):
        state.p1_open = False
        state.p1_first_frame = None
        return []
    if state.p1_first_frame is None:
        state.p1_first_frame = _frame(rec)
    duration = _frame(rec) - state.last_wicket_frame
    relax = (THRESHOLDS["FORCE_PROCESSED_RELAX_FACTOR"]
             if _path(rec, "capture", "force_processed") else 1.0)
    warn_thr = THRESHOLDS["P1_WARN_FRAMES"] * relax
    err_thr = THRESHOLDS["P1_ERROR_FRAMES"] * relax
    if duration < warn_thr:
        return []
    severity = "error" if duration >= err_thr else "warn"
    fire_key = f"P1@{state.last_wicket_frame}:{severity}"
    if fire_key in state.fired_once:
        return []
    state.fired_once.add(fire_key)
    proposed_in_window = []
    rejected_in_window = []
    for r in window:
        for u in _path(r, "scorer", "proposed", "batter_updates",
                       default=[]) or []:
            proposed_in_window.append(
                {"frame": _frame(r), "name": u.get("name")})
        for d in _path(r, "scorer", "decisions", default=[]) or []:
            if d.get("tag") in (
                    "GUARD-BATTER-NOT-IN-EXTRACTOR",
                    "SCORER-INVARIANT-FILTER", "SM-DROP-WITNESSED-OUT",
                    "BOARD-INVARIANT-NO-UNDISMISS"):
                rejected_in_window.append({"frame": _frame(r),
                                           "tag": d.get("tag"),
                                           "name": d.get("name")})
    has_proposals = bool(proposed_in_window)
    if has_proposals and rejected_in_window:
        verdict = ("Scorer/extractor proposed new batter rows in the "
                   "post-wicket window but every proposal was rejected "
                   "by SM/board guards. Likely cause: extractor reading "
                   "stale strip graphic of the dismissed batter. Inspect "
                   "scout.raw_text_120 in the cited frames.")
    elif not has_proposals:
        verdict = ("No new batter row reached the scorer in the post-"
                   "wicket window. Cause is upstream of the scorer — "
                   "Scout pre-gate or extractor missed the new pair.")
    else:
        verdict = ("Scorer proposed new batter rows but commit path "
                   "failed silently. Inspect scorer.committed_changes vs "
                   "scorer.proposed in the window.")
    return [Anomaly(
        id="P1",
        severity=severity,
        fired_at_frame=_frame(rec),
        first_evidence_frame=state.last_wicket_frame,
        duration_frames=duration,
        evidence={
            "wicket_frame": state.last_wicket_frame,
            "dismissed": state.last_wicket_dismissed,
            "ui_at_crease_unchanged": list(state.last_wicket_at_crease),
            "proposals_in_window": proposed_in_window[-12:],
            "rejections_in_window": rejected_in_window[-12:],
        },
        verdict=verdict,
    )]


def rule_p2(state: AnalyzerState,
            rec: dict[str, Any],
            window: list[dict[str, Any]]) -> list[Anomaly]:
    """Score regression within the same innings."""
    if _suppressed(rec, modes=("COLD_START", "INNINGS_HANDOFF")):
        return []
    if len(window) < 2:
        return []
    prev = window[-2]
    if _innings(prev) != _innings(rec):
        return []
    s_prev = _score(prev)
    s_curr = _score(rec)
    if s_prev is None or s_curr is None:
        return []
    if s_curr >= s_prev:
        return []
    fire_key = f"P2@{_frame(rec)}"
    if fire_key in state.fired_once:
        return []
    state.fired_once.add(fire_key)
    committed = _path(rec, "scorer", "committed_changes", default=[]) or []
    poison_in_window = bool(_decisions_with_tag(rec, "POISON-RECAL"))
    if any("score→" in str(c) for c in committed):
        verdict = ("Scorer accepted a regressing extractor read; "
                   "POISON-RECAL did NOT pre-empt despite |Δ|=" +
                   f"{s_prev - s_curr}. Inspect extractor.score in this "
                   "frame and the POISON-RECAL streak counter.")
    else:
        verdict = ("Score dropped without an explicit scorer commit — "
                   "mutation came from a non-scorer path "
                   "(full_reset / cache restore / innings clear).")
    return [Anomaly(
        id="P2",
        severity="error",
        fired_at_frame=_frame(rec),
        first_evidence_frame=_frame(prev),
        duration_frames=1,
        evidence={
            "from_score": s_prev,
            "to_score": s_curr,
            "delta": s_curr - s_prev,
            "extractor_score": _path(rec, "extractor", "score"),
            "committed_changes": committed,
            "poison_recal_fired": poison_in_window,
            "innings": _innings(rec),
        },
        verdict=verdict,
    )]


def rule_p3(state: AnalyzerState,
            rec: dict[str, Any],
            window: list[dict[str, Any]]) -> list[Anomaly]:
    """Stale bowler across ≥ 2 overs of apparent play."""
    if _suppressed(rec, modes=("COLD_START", "INNINGS_HANDOFF")):
        return []
    name = _bowler_name(rec)
    overs = _path(rec, "ui_after", "scorecard", "overs")
    cur_over_int = (_overs_to_balls(overs) or 0) // 6
    if name and name != state.last_bowler_name:
        state.last_bowler_name = name
        state.last_bowler_change_over = cur_over_int
        state.last_bowler_change_frame = _frame(rec)
        return []
    if state.last_bowler_change_over is None or name is None:
        return []
    overs_unchanged = cur_over_int - state.last_bowler_change_over
    warn_thr = THRESHOLDS["P3_WARN_OVERS"]
    err_thr = THRESHOLDS["P3_ERROR_OVERS"]
    if overs_unchanged < warn_thr:
        return []
    severity = "error" if overs_unchanged >= err_thr else "warn"
    fire_key = (f"P3@{state.last_bowler_change_frame or 0}:"
                f"{name}:{cur_over_int}:{severity}")
    if fire_key in state.fired_once:
        return []
    state.fired_once.add(fire_key)
    leads = _decisions_with_tag(
        rec,
        "BOWLER",
        "BOWLER-OVERRIDE",
        "BOWLER-CONSENSUS-INCONSISTENT",
        "BOWLER-CONSENSUS-INCONSISTENT-OVERRIDE",
        "BOWLER-LOCK-RELEASED",
        "BOWLER-LOCK-ACQUIRED",
        "BOWLER-BOOTSTRAP-REJECT",
        "GUARD",
        "GUARD-RELEASE",
    )
    return [Anomaly(
        id="P3",
        severity=severity,
        fired_at_frame=_frame(rec),
        first_evidence_frame=state.last_bowler_change_frame or _frame(rec),
        duration_frames=overs_unchanged,
        evidence={
            "bowler": name,
            "overs_unchanged": overs_unchanged,
            "current_over": cur_over_int,
            "bowler_decisions_in_window": leads[-8:],
        },
        verdict=("UI bowler unchanged across 2+ overs of apparent play. "
                 "Inspect BOWLER, BOWLER-OVERRIDE, "
                 "BOWLER-CONSENSUS-INCONSISTENT arbitrations and "
                 "BOWLER-LOCK-RELEASED/ACQUIRED counts."),
    )]


def _p4_extras_total(rec: dict[str, Any]) -> int:
    """Read ``extras_total`` from the trace record (0 if absent).

    Cricket: partnership_runs ≡ Σbatter_runs + extras_during_partnership.
    When no wicket has fallen, the current partnership covers the whole
    innings, so ``extras_total`` equals ``extras_during_partnership``.
    """
    et = _path(rec, "ui_after", "extras_total")
    if isinstance(et, (int, float)):
        return int(et)
    return 0


def _p4_fow_count(rec: dict[str, Any]) -> int:
    fc = _path(rec, "ui_after", "fow_count")
    if isinstance(fc, (int, float)):
        return int(fc)
    return 0


def rule_p4_advisory(state: AnalyzerState,
                     rec: dict[str, Any],
                     window: list[dict[str, Any]]) -> list[Anomaly]:
    """Partnership math sanity (advisory only per Q4).

    Cricket-correct identity:
        partnership_runs ≟ Σ at-crease batter_runs + extras_during_partnership

    The earlier naive identity (without the extras term) produced 100%
    false positives on trace ``866ce150`` — see
    ``files/docs/investigations/p4_diagnosis.md`` §6 (option a, lean).

    Lean approximation: when ``fow_count == 0`` the current pair has been
    at the crease since the innings started, so
    ``extras_during_partnership == ui_after.extras_total``. After ≥ 1
    wicket we cannot derive ``extras_at_partnership_start`` from the
    trace alone, so the rule defers (returns no fire) until the SM
    exposes a per-partnership extras snapshot.
    """
    if _suppressed(rec, modes=("COLD_START", "INNINGS_HANDOFF")):
        return []
    p = _path(rec, "ui_after", "partnership_current") or {}
    runs = p.get("runs")
    batters = p.get("batters") or []
    if runs is None or len(batters) < 2:
        return []
    if _p4_fow_count(rec) > 0:
        return []
    crease = _path(rec, "ui_after", "batting_card_at_crease", default=[]) or []
    by_name = {b.get("name"): b for b in crease}
    sum_batter_runs = 0
    contributors = []
    for n in batters:
        b = by_name.get(n)
        if b and isinstance(b.get("runs"), (int, float)):
            sum_batter_runs += int(b["runs"])
            contributors.append({"name": n, "runs": int(b["runs"])})
    extras_total = _p4_extras_total(rec)
    expected = sum_batter_runs + extras_total
    delta = (abs(int(runs) - expected)
             if isinstance(runs, (int, float)) else 0)
    if delta <= THRESHOLDS["P4_TOLERANCE"]:
        return []
    fire_key = f"P4@{_frame(rec)}"
    if fire_key in state.fired_once:
        return []
    sustained = 0
    for r in window[-THRESHOLDS["P4_MIN_RECORDS"]:]:
        if _p4_fow_count(r) > 0:
            continue
        rp = _path(r, "ui_after", "partnership_current") or {}
        rr = rp.get("runs")
        rc = _path(r, "ui_after", "batting_card_at_crease", default=[]) or []
        rby = {b.get("name"): b for b in rc}
        rsum = sum(int(rby.get(n, {}).get("runs") or 0)
                   for n in (rp.get("batters") or []))
        rexp = rsum + _p4_extras_total(r)
        if (isinstance(rr, (int, float))
                and abs(int(rr) - rexp) > THRESHOLDS["P4_TOLERANCE"]):
            sustained += 1
    if sustained < THRESHOLDS["P4_MIN_RECORDS"]:
        return []
    state.fired_once.add(fire_key)
    return [Anomaly(
        id="P4",
        severity="advisory",
        fired_at_frame=_frame(rec),
        first_evidence_frame=_frame(rec),
        duration_frames=sustained,
        evidence={
            "partnership_runs": int(runs),
            "sum_batter_runs": sum_batter_runs,
            "extras_total": extras_total,
            "expected_partnership": expected,
            "delta": delta,
            "contributors": contributors,
        },
        verdict=("Partnership total disagrees with "
                 "(Σbatter_runs + extras_total) by >tolerance. With "
                 "extras now correctly included, this indicates a real "
                 "SM feeder or partnership-tracker bug. Advisory only."),
    )]


def rule_p5(state: AnalyzerState,
            rec: dict[str, Any],
            window: list[dict[str, Any]]) -> list[Anomaly]:
    """Wickets-up without a WICKET ball event nearby."""
    if _suppressed(rec, modes=("COLD_START", "INNINGS_HANDOFF")):
        return []
    if len(window) < 2:
        return []
    prev = window[-2]
    if _innings(prev) != _innings(rec):
        return []
    w_prev = _wickets(prev)
    w_curr = _wickets(rec)
    if w_prev is None or w_curr is None or w_curr <= w_prev:
        return []
    n = THRESHOLDS["P5_LOOKAROUND_FRAMES"]
    look = window[max(0, len(window) - 1 - n):]
    saw_wicket = any(
        _ball_event_type(r) == "WICKET" for r in look)
    auto = []
    for r in look:
        auto.extend(_decisions_with_tag(r, "WICKET-AUTO", "WICKET-TRACK"))
    if saw_wicket or auto:
        return []
    fire_key = f"P5@{_frame(rec)}"
    if fire_key in state.fired_once:
        return []
    state.fired_once.add(fire_key)
    return [Anomaly(
        id="P5",
        severity="error",
        fired_at_frame=_frame(rec),
        first_evidence_frame=_frame(prev),
        duration_frames=1,
        evidence={
            "from_wickets": w_prev,
            "to_wickets": w_curr,
            "extractor_wickets_prev": _path(prev, "extractor", "wickets"),
            "extractor_wickets_curr": _path(rec, "extractor", "wickets"),
            "ball_event": _path(rec, "ball_event", "type"),
        },
        verdict=("Wickets jumped without WICKET ball-detector event or "
                 "WICKET-AUTO/TRACK decision. Likely phantom — extractor "
                 "mis-read or graphic transition not filtered."),
    )]


def rule_p6(state: AnalyzerState,
            rec: dict[str, Any],
            window: list[dict[str, Any]]) -> list[Anomaly]:
    """Extras inconsistency: components do not sum to total."""
    extras = _path(rec, "ui_after", "extras_total")
    full = (_path(rec, "ui_after_full") or {}).get("extras") if False else None
    e = (rec.get("ui_after_state") or {}).get("extras") if False else None
    raw = _path(rec, "ui_extras_full") or {}
    if not raw:
        # Build from per-known fields if writer supplied them in the
        # compact ``ui_after``. Without per-component values we cannot
        # assert sum-equality; quietly skip.
        return []
    components = sum(int(raw.get(k) or 0) for k in
                    ("wides", "no_balls", "byes", "leg_byes", "penalties"))
    total = int(raw.get("total") or 0)
    if abs(components - total) <= THRESHOLDS["P6_TOLERANCE"]:
        return []
    fire_key = f"P6@{_frame(rec)}"
    if fire_key in state.fired_once:
        return []
    state.fired_once.add(fire_key)
    inf = _decisions_with_tag(rec, "EXTRAS-INF", "EXTRAS-INF-GATE", "EXTRAS")
    return [Anomaly(
        id="P6",
        severity="warn",
        fired_at_frame=_frame(rec),
        first_evidence_frame=_frame(rec),
        duration_frames=1,
        evidence={
            "components_sum": components,
            "total": total,
            "delta": components - total,
            "raw": raw,
            "extras_decisions_this_frame": inf,
        },
        verdict=("Extras component-sum disagrees with reported total. "
                 "Inspect EXTRAS-INF / EXTRAS-INF-GATE on this frame; "
                 "absent reconciliation is the typical cause."),
    )]


def rule_p7(state: AnalyzerState,
            rec: dict[str, Any],
            window: list[dict[str, Any]]) -> list[Anomaly]:
    """Score reset to zero without innings counter advancing."""
    if len(window) < 2:
        return []
    prev = window[-2]
    s_prev = _score(prev) or 0
    s_curr = _score(rec) or 0
    w_curr = _wickets(rec) or 0
    if s_prev <= 5:
        return []
    if not (s_curr == 0 or w_curr == 0):
        return []
    if _innings(prev) != _innings(rec):
        return []
    fire_key = f"P7@{_frame(rec)}"
    if fire_key in state.fired_once:
        return []
    state.fired_once.add(fire_key)
    return [Anomaly(
        id="P7",
        severity="error",
        fired_at_frame=_frame(rec),
        first_evidence_frame=_frame(prev),
        duration_frames=1,
        evidence={
            "score_before": s_prev,
            "score_after": s_curr,
            "wickets_after": w_curr,
            "innings": _innings(rec),
            "committed_changes": _path(rec, "scorer", "committed_changes"),
        },
        verdict=("Score / wickets reset to zero with same innings "
                 "counter — full_reset called without a corresponding "
                 "set_innings_2 transition. Inspect scorer.committed_"
                 "changes and pipeline.mode."),
    )]


def rule_p8(state: AnalyzerState,
            rec: dict[str, Any],
            window: list[dict[str, Any]]) -> list[Anomaly]:
    """this_over ball count vs over.ball arithmetic mismatch."""
    if _suppressed(rec, modes=("COLD_START", "INNINGS_HANDOFF")):
        state.p8_delta_streak = 0
        return []
    overs = _path(rec, "ui_after", "scorecard", "overs")
    bwo = _ball_within_over(overs)
    this_over = _path(rec, "ui_after", "this_over") or []
    if bwo is None:
        state.p8_delta_streak = 0
        return []
    delta = abs(len(this_over) - bwo)
    if delta < THRESHOLDS["P8_DELTA_WARN"]:
        state.p8_delta_streak = 0
        return []
    state.p8_delta_streak += 1
    if state.p8_delta_streak < THRESHOLDS["P8_SUSTAIN_RECORDS"]:
        return []
    severity = ("error"
                if delta >= THRESHOLDS["P8_DELTA_ERROR"]
                else "warn")
    fire_key = f"P8@{_frame(rec)}:{severity}"
    if fire_key in state.fired_once:
        return []
    state.fired_once.add(fire_key)
    return [Anomaly(
        id="P8",
        severity=severity,
        fired_at_frame=_frame(rec),
        first_evidence_frame=_frame(rec) - state.p8_delta_streak + 1,
        duration_frames=state.p8_delta_streak,
        evidence={
            "overs": overs,
            "ball_within_over": bwo,
            "this_over": list(this_over),
            "delta": delta,
        },
        verdict=("this_over ball count drifted from overs-string "
                 "arithmetic for ≥ sustain window. Likely missed "
                 "rollover or a stale append."),
    )]


def rule_p9(state: AnalyzerState,
            rec: dict[str, Any],
            window: list[dict[str, Any]]) -> list[Anomaly]:
    """Stuck UI fields during apparent active play."""
    if _suppressed(rec, modes=("COLD_START", "INNINGS_HANDOFF")):
        for k in list(state.field_last_changed.keys()):
            state.field_last_changed[k] = _frame(rec)
            state.p9_open[k] = False
        return []
    if _path(rec, "scout", "phase") not in (None, "active_play"):
        return []
    if _path(rec, "scout", "cam") in ("ad", "graphic"):
        return []
    fields = {
        "score": _score(rec),
        "this_over": tuple(_path(rec, "ui_after", "this_over") or ()),
        "striker": _path(rec, "ui_after", "scorecard", "striker"),
        "non_striker": _path(rec, "ui_after", "scorecard", "non_striker"),
        "current_bowler": _bowler_name(rec),
    }
    thresholds = {
        "score": THRESHOLDS["P9_STALE_RECORDS_SCORE"],
        "this_over": THRESHOLDS["P9_STALE_RECORDS_THIS_OVER"],
        "striker": THRESHOLDS["P9_STALE_RECORDS_STRIKER"],
        "non_striker": THRESHOLDS["P9_STALE_RECORDS_NON_STRIKER"],
        "current_bowler": THRESHOLDS["P9_STALE_RECORDS_BOWLER"],
    }
    fired: list[Anomaly] = []
    for k, v in fields.items():
        if state.field_last_value.get(k, "<init>") != v:
            state.field_last_value[k] = v
            state.field_last_changed[k] = _frame(rec)
            state.p9_open[k] = False
            continue
        first = state.field_last_changed.setdefault(k, _frame(rec))
        stale = _frame(rec) - first
        if stale < thresholds[k]:
            continue
        if state.p9_open.get(k):
            continue
        state.p9_open[k] = True
        fire_key = f"P9@{first}:{k}"
        if fire_key in state.fired_once:
            continue
        state.fired_once.add(fire_key)
        rejections = []
        for r in window[-12:]:
            for d in _path(r, "scorer", "decisions", default=[]) or []:
                if d.get("tag") in ("GUARD", "GRAPHIC-FILTER",
                                    "SCORER-INVARIANT-FILTER",
                                    "SM-DROP-WITNESSED-OUT"):
                    rejections.append({"frame": _frame(r),
                                       "tag": d.get("tag")})
        fired.append(Anomaly(
            id="P9",
            severity="info",
            fired_at_frame=_frame(rec),
            first_evidence_frame=first,
            duration_frames=stale,
            evidence={
                "field": k,
                "stuck_value": v,
                "stale_records": stale,
                "rejections_in_window": rejections[-12:],
            },
            verdict=(f"UI field {k!r} unchanged across {stale} active-"
                     "play records. Inspect rejections in the window — "
                     "GUARD / GRAPHIC-FILTER suppressions are the "
                     "common cause."),
        ))
    return fired


def rule_p19(state: AnalyzerState,
             rec: dict[str, Any],
             window: list[dict[str, Any]]) -> list[Anomaly]:
    """Strip-overlay batter rejections — split between sentinel /
    active-batting pre-filter (``STRIP-OVERLAY-DETECTED``) and the
    backstop row-pair runs-delta guard (``STRIP-ROWS-MISALIGNED``).

    Informational: counts pre-filter coverage so we can verify the
    sentinels are catching the bulk of overlay frames before the
    backstop kicks in.  Fires once per matching record.
    """
    pre = _decisions_with_tag(rec, "STRIP-OVERLAY-DETECTED")
    backstop = _decisions_with_tag(rec, "STRIP-ROWS-MISALIGNED")
    if not pre and not backstop:
        return []
    if pre:
        d = pre[0]
        return [Anomaly(
            id="P19",
            severity="info",
            fired_at_frame=_frame(rec),
            first_evidence_frame=_frame(rec),
            duration_frames=0,
            evidence={
                "branch": "OVERLAY-PRE-FILTERED",
                "reason": d.get("reason"),
                "sentinel": d.get("sentinel"),
            },
            verdict=("Strip overlay rejected by pre-filter "
                     f"(reason={d.get('reason')!r})."),
        )]
    d = backstop[0]
    return [Anomaly(
        id="P19",
        severity="warn",
        fired_at_frame=_frame(rec),
        first_evidence_frame=_frame(rec),
        duration_frames=0,
        evidence={
            "branch": "ROW-DELTA-FALLBACK",
            "row_pair": d.get("row_pair"),
            "row_delta": d.get("row_delta"),
        },
        verdict=("Strip overlay slipped past pre-filters and was "
                 "rejected by the row-pair runs-delta backstop."),
    )]


# ── 2026-05-03 typed tag rules (P10/P12/P14/P15/P16/P20) ──────────
#
# Follows the P19 pattern: each fired ``Anomaly`` carries a
# ``branch`` evidence field naming the source tag and a fixed
# severity per the consolidation memo.  No state, no thresholds,
# no fired-once dedup — these rules surface every emission so the
# post-match histogram and per-frame counts match the raw log.


_TAG_2026_05_03_SPEC: dict[str, tuple[str, str, str]] = {
    "TIMEOUT-GAP-INFER": (
        "P10", "info",
        "Strip-OCR gap inferred after timeout — advisory only; "
        "anomaly only on frequent bursts."),
    "INN2-TRANSITION-REJECT": (
        "P12", "warn",
        "INN2 transition gate caught suspicious data."),
    "INN2-TRANSITION-NULL-TEAM": (
        "P12", "info",
        "INN2 transition observed null-team frame (advisory)."),
    "INN2-COLD-START-LOCKOUT": (
        "P12", "warn",
        "Cold-start commit blocked during INN2 consensus window."),
    "INN2-COLD-START-CONSENSUS": (
        "P12", "info",
        "INN2 cold-start consensus progressing."),
    "INN2-TRANSITION-PHANTOM-STORM": (
        "P12", "error",
        "PHANTOM-STORM: ≥5 inn2 rejects within 60 s; cumulative "
        "+60 s window extension applied."),
    "BATTER-CONSENSUS-RESET": (
        "P14", "info",
        "Batter slot identity consensus reset on legitimate slot "
        "change (1–2 per over typical)."),
    "BOWLER-STATS-SANITY-REJECT": (
        "P15", "warn",
        "Stale bowler spell stats rejected (replaces legacy "
        "``[GUARD]`` for this path)."),
    "SCORE-OVERS-RR-REJECT": (
        "P16", "warn",
        "DIRECT score/overs proposal rejected on RR plausibility."),
    "BOWLER-LATENCY-HARDCAP": (
        "P20", "warn",
        "Bowler cleared after 20-frame latency hardcap timeout."),
    "LATENCY-STUCK": (
        "P20", "info",
        ">8 frames stuck on bowler latency (not yet hardcap)."),
}


def rule_tags_2026_05_03(state: AnalyzerState,
                         rec: dict[str, Any],
                         window: list[dict[str, Any]]) -> list[Anomaly]:
    """Tag-driven rules shipped 2026-05-03 (P10/P12/P14/P15/P16/P20).

    One ``Anomaly`` per matching decision entry on the record.  The
    ``branch`` evidence field names the source tag so the analyzer
    report renders each branch separately even though they share an
    anomaly id (e.g. P12 has 5 branches).
    """
    out: list[Anomaly] = []
    for d in _path(rec, "scorer", "decisions", default=[]) or []:
        tag = d.get("tag")
        spec = _TAG_2026_05_03_SPEC.get(tag)
        if spec is None:
            continue
        anomaly_id, severity, verdict = spec
        out.append(Anomaly(
            id=anomaly_id,
            severity=severity,
            fired_at_frame=_frame(rec),
            first_evidence_frame=_frame(rec),
            duration_frames=0,
            evidence={
                "branch": tag,
                "raw_message": d.get("raw_message"),
                "log_level": d.get("log_level"),
            },
            verdict=verdict,
        ))
    return out


def rule_round_2_3_fixes(state: AnalyzerState,
                         rec: dict[str, Any],
                         window: list[dict[str, Any]]) -> list[Anomaly]:
    """2026-05-04 round 2/3 fix monitoring (Batches F/G/H/I/J).

    Counts six tag-driven signals over the trace and fires anomalies
    when thresholds documented in
    ``files/docs/investigations/match_monitoring_plan_pre_live.md`` §8
    are exceeded.  Each anomaly fires once per match via ``fired_once``.

    Branches:
        A: WICKETS_WITHOUT_INCOMING_PROMOTION (HIGH) — Batch J wiring
        B: OVERLAY_LOCKOUT_BREAKOUT_FREQUENT (MEDIUM)
        C: BOWLER_STATS_REGRESSION_FREQUENT (MEDIUM)
        D: SCORE_EVENTS_NOT_ADVANCING (HIGH) — E.2 wiring
        E: SHADOW_FRAMES_LOW (MEDIUM) — Option α throughput
        F: UN_DISMISS_REFUSAL_FREQUENT (LOW) — informational
    """
    out: list[Anomaly] = []

    if _ball_event_type(rec) == "WICKET":
        state.r23_wicket_count += 1
    for d in _path(rec, "scorer", "decisions", default=[]) or []:
        tag = d.get("tag")
        if tag == "INCOMING-BATTER-PROMOTED":
            state.r23_incoming_promoted_count += 1
        elif tag == "OVERLAY-LOCKOUT-BREAKOUT":
            state.r23_overlay_lockout_breakout_count += 1
        elif tag == "BOWLER-STATS-REGRESSION":
            state.r23_bowler_stats_regression_count += 1
        elif tag == "INVARIANT":
            msg = (d.get("raw_message") or "")
            if "Refusing to un-dismiss" in msg:
                state.r23_undismiss_refusal_count += 1
        elif tag == "SHADOW-STATS":
            raw = d.get("raw_message") or ""
            ev_m = re.search(r"score_events_marked['\"]?\s*[:=]\s*(\d+)", raw)
            fr_m = re.search(r"frames_received['\"]?\s*[:=]\s*(\d+)", raw)
            if ev_m:
                if int(ev_m.group(1)) == 0:
                    state.r23_shadow_score_events_zero_streak += 1
                else:
                    state.r23_shadow_score_events_zero_streak = 0
                if (state.r23_shadow_score_events_zero_streak > 3
                        and "R23-D" not in state.fired_once):
                    state.fired_once.add("R23-D")
                    out.append(Anomaly(
                        id="R23-D",
                        severity="error",
                        fired_at_frame=_frame(rec),
                        first_evidence_frame=_frame(rec),
                        duration_frames=state
                            .r23_shadow_score_events_zero_streak,
                        evidence={
                            "branch": "SCORE_EVENTS_NOT_ADVANCING",
                            "consecutive_zero_heartbeats":
                                state.r23_shadow_score_events_zero_streak,
                        },
                        verdict=("SHADOW-STATS score_events_marked stayed at "
                                 "0 across >3 heartbeats during active play. "
                                 "Batch E.2 wiring likely broken — verify "
                                 "score-event emitter into the shadow lane."),
                    ))
            if fr_m:
                cur = int(fr_m.group(1))
                cur_frame = _frame(rec)
                prev = state.r23_shadow_last_frames_received
                prev_frame = state.r23_shadow_last_heartbeat_frame
                if (prev is not None and prev_frame is not None
                        and cur_frame > prev_frame
                        and cur - prev < 200
                        and "R23-E" not in state.fired_once):
                    state.fired_once.add("R23-E")
                    out.append(Anomaly(
                        id="R23-E",
                        severity="warn",
                        fired_at_frame=cur_frame,
                        first_evidence_frame=prev_frame,
                        duration_frames=cur_frame - prev_frame,
                        evidence={
                            "branch": "SHADOW_FRAMES_LOW",
                            "frames_delta": cur - prev,
                            "expected_min_per_30s": 200,
                        },
                        verdict=("SHADOW-STATS frames_received delta "
                                 f"{cur - prev} between heartbeats < 200. "
                                 "Option α not delivering at 15 fps capture; "
                                 "investigate shadow ingest throttle."),
                    ))
                state.r23_shadow_last_frames_received = cur
                state.r23_shadow_last_heartbeat_frame = cur_frame

    expected_promotions = max(0, state.r23_wicket_count - 1)
    if (state.r23_wicket_count > 0
            and state.r23_incoming_promoted_count < expected_promotions
            and "R23-A" not in state.fired_once):
        state.fired_once.add("R23-A")
        out.append(Anomaly(
            id="R23-A",
            severity="error",
            fired_at_frame=_frame(rec),
            first_evidence_frame=_frame(rec),
            duration_frames=0,
            evidence={
                "branch": "WICKETS_WITHOUT_INCOMING_PROMOTION",
                "wickets_seen": state.r23_wicket_count,
                "incoming_promoted_seen":
                    state.r23_incoming_promoted_count,
                "expected_promotions": expected_promotions,
            },
            verdict=("Wicket events outpaced INCOMING-BATTER-PROMOTED "
                     "emissions by more than the per-innings tail. "
                     "Batch J wiring likely broken — verify the SM "
                     "promotion hook fires on wicket commit."),
        ))
    if (state.r23_overlay_lockout_breakout_count > 5
            and "R23-B" not in state.fired_once):
        state.fired_once.add("R23-B")
        out.append(Anomaly(
            id="R23-B",
            severity="warn",
            fired_at_frame=_frame(rec),
            first_evidence_frame=_frame(rec),
            duration_frames=0,
            evidence={
                "branch": "OVERLAY_LOCKOUT_BREAKOUT_FREQUENT",
                "count": state.r23_overlay_lockout_breakout_count,
            },
            verdict=("OVERLAY-LOCKOUT-BREAKOUT fired >5 times. Batch G "
                     "fallback running often — Batch J should be "
                     "pre-empting the lockouts but is not."),
        ))
    if (state.r23_bowler_stats_regression_count > 3
            and "R23-C" not in state.fired_once):
        state.fired_once.add("R23-C")
        out.append(Anomaly(
            id="R23-C",
            severity="warn",
            fired_at_frame=_frame(rec),
            first_evidence_frame=_frame(rec),
            duration_frames=0,
            evidence={
                "branch": "BOWLER_STATS_REGRESSION_FREQUENT",
                "count": state.r23_bowler_stats_regression_count,
            },
            verdict=("BOWLER-STATS-REGRESSION fired >3 times. Either "
                     "real cross-match contamination or a Batch H "
                     "regression-guard FP — manual review required."),
        ))
    if (state.r23_undismiss_refusal_count > 5
            and "R23-F" not in state.fired_once):
        state.fired_once.add("R23-F")
        out.append(Anomaly(
            id="R23-F",
            severity="info",
            fired_at_frame=_frame(rec),
            first_evidence_frame=_frame(rec),
            duration_frames=0,
            evidence={
                "branch": "UN_DISMISS_REFUSAL_FREQUENT",
                "count": state.r23_undismiss_refusal_count,
            },
            verdict=("[INVARIANT] Refusing to un-dismiss fired >5 "
                     "times. Strip flapping post-wicket — broadcaster "
                     "timing issue or extractor flap. Informational."),
        ))

    return out


def rule_shadow(state: AnalyzerState,
                rec: dict[str, Any],
                window: list[dict[str, Any]]) -> list[Anomaly]:
    """OpenScout shadow runner exception surfacing.

    Only fires on ``[SHADOW] ...`` lines whose payload contains
    ``fail`` / ``exception`` / ``error`` (case-insensitive).  Routine
    start/stop/heartbeat lines are ignored; a separate heartbeat tag
    (``SHADOW-STATS``) carries the structured queue-depth signal.
    """
    out: list[Anomaly] = []
    for d in _decisions_with_tag(rec, "SHADOW"):
        msg = (d.get("raw_message") or "").lower()
        if "fail" in msg or "exception" in msg or "error" in msg:
            out.append(Anomaly(
                id="SHADOW",
                severity="warn",
                fired_at_frame=_frame(rec),
                first_evidence_frame=_frame(rec),
                duration_frames=0,
                evidence={
                    "branch": "EXCEPTION",
                    "raw_message": d.get("raw_message"),
                },
                verdict=("Shadow component reported an exception; main "
                         "pipeline unaffected (shadow is read-only)."),
            ))
    return out


# ── Chunker v3 divergence advisory (2026-05-05) ───────────────────


_CHUNKER_V3_FIELD_RE = re.compile(
    r"(legacy_start|legacy_end|v3_start|v3_end|drove_cut)"
    r"\s*=\s*([-\w\.]+)")
_V3_DIVERGENCE_THRESHOLD_S = 2.0


def _parse_v3_window_payload(raw: str | None) -> dict[str, Any]:
    """Extract the window-resolution fields from the
    ``[CHUNKER-V3-WINDOW] ...`` log message text."""
    out: dict[str, Any] = {}
    if not raw:
        return out
    for m in _CHUNKER_V3_FIELD_RE.finditer(raw):
        k, v = m.group(1), m.group(2)
        if k == "drove_cut":
            out[k] = v
        else:
            try:
                out[k] = float(v) if v not in ("None", "none", "null") else None
            except ValueError:
                out[k] = None
    return out


def rule_chunker_v3_divergence(
        state: AnalyzerState,
        rec: dict[str, Any],
        window: list[dict[str, Any]]) -> list[Anomaly]:
    """Advisory — flag delivery-window resolutions where v3's bounds
    differ from legacy by more than ±2 s on either side.

    Useful for identifying mismatch hotspots during shadow rollout.
    Severity is always ``advisory`` — does NOT count toward
    errors/warnings (matches P4 treatment).
    """
    decisions = _decisions_with_tag(rec, "CHUNKER-V3-WINDOW")
    if not decisions:
        return []
    out: list[Anomaly] = []
    for d in decisions:
        parsed = _parse_v3_window_payload(d.get("raw_message"))
        ls = parsed.get("legacy_start")
        le = parsed.get("legacy_end")
        v3s = parsed.get("v3_start")
        v3e = parsed.get("v3_end")
        if v3s is None and v3e is None:
            # v3 returned no window — not a divergence event itself
            # (the legacy path is unaffected).
            continue
        if ls is None and le is None:
            continue
        diverge_start = (
            ls is not None and v3s is not None
            and abs(v3s - ls) > _V3_DIVERGENCE_THRESHOLD_S
        )
        diverge_end = (
            le is not None and v3e is not None
            and abs(v3e - le) > _V3_DIVERGENCE_THRESHOLD_S
        )
        if not (diverge_start or diverge_end):
            continue
        out.append(Anomaly(
            id="P21",
            severity="advisory",
            fired_at_frame=_frame(rec),
            first_evidence_frame=_frame(rec),
            duration_frames=0,
            evidence={
                "legacy_start": ls,
                "legacy_end": le,
                "v3_start": v3s,
                "v3_end": v3e,
                "drove_cut": parsed.get("drove_cut"),
                "diverge_start_s": (
                    round(abs(v3s - ls), 2)
                    if (ls is not None and v3s is not None) else None),
                "diverge_end_s": (
                    round(abs(v3e - le), 2)
                    if (le is not None and v3e is not None) else None),
                "threshold_s": _V3_DIVERGENCE_THRESHOLD_S,
            },
            verdict=("Chunker v3 window diverges from legacy by "
                     f">{_V3_DIVERGENCE_THRESHOLD_S:.1f}s on either "
                     "bound — review the delivery clip."),
        ))
    return out


# ── Chunker v3 None-fallback usage (2026-05-05) ──────────────────


_CHUNKER_V3_FALLBACK_RE = re.compile(
    r"event_ts\s*=\s*([-\d\.]+)\s+window\s*=\s*"
    r"\(\s*([-\d\.]+)\s*,\s*([-\d\.]+)\s*\)"
)


def rule_chunker_v3_fallback_used(
        state: AnalyzerState,
        rec: dict[str, Any],
        window: list[dict[str, Any]]) -> list[Anomaly]:
    """Fires when ``CHUNKER-V3-FALLBACK`` is captured in
    ``decisions[]`` — v3 + legacy both returned None and the fixed-
    window fallback was used to produce a clip.

    Severity ``warn``: fallback usage is by design (better a slightly-
    off window than no window) but each firing is operator-actionable
    (audit the clip, tune lookback/forward if systematically off).
    """
    decisions = _decisions_with_tag(rec, "CHUNKER-V3-FALLBACK")
    if not decisions:
        return []
    out: list[Anomaly] = []
    for d in decisions:
        raw = d.get("raw_message") or ""
        m = _CHUNKER_V3_FALLBACK_RE.search(raw)
        if m:
            ev_ts = float(m.group(1))
            start = float(m.group(2))
            end = float(m.group(3))
        else:
            ev_ts = None
            start = None
            end = None
        out.append(Anomaly(
            id="P22",
            severity="warn",
            fired_at_frame=_frame(rec),
            first_evidence_frame=_frame(rec),
            duration_frames=0,
            evidence={
                "event_ts": ev_ts,
                "window_start": start,
                "window_end": end,
                "raw_message": raw[:200],
            },
            verdict=(f"v3 + legacy both returned None; fixed-window "
                     f"fallback applied at event_ts={ev_ts} "
                     f"window=({start}, {end})"
                     if ev_ts is not None else
                     "v3 + legacy both returned None; fixed-window "
                     "fallback applied (payload unparsed)."),
        ))
    return out


# ── Rule registry ──────────────────────────────────────────────────


RULES: list[tuple[str, Callable[..., list[Anomaly]]]] = [
    ("P1", rule_p1),
    ("P2", rule_p2),
    ("P3", rule_p3),
    ("P4", rule_p4_advisory),
    ("P5", rule_p5),
    ("P6", rule_p6),
    ("P7", rule_p7),
    ("P8", rule_p8),
    ("P9", rule_p9),
    ("P19", rule_p19),
    ("P10/12/14/15/16/20", rule_tags_2026_05_03),
    ("SHADOW", rule_shadow),
    ("R23 (Batches F/G/H/I/J)", rule_round_2_3_fixes),
    ("P21 (chunker v3 divergence)", rule_chunker_v3_divergence),
    ("P22 (chunker v3 fallback used)", rule_chunker_v3_fallback_used),
]


def evaluate(records: list[dict[str, Any]]) -> tuple[
        list[Anomaly], dict[int, list[Anomaly]]]:
    """Walk the records, fire all rules, return:
       - flat list of all fired anomalies
       - mapping ``frame -> [anomalies fired at that frame]``
    """
    state = AnalyzerState()
    all_fired: list[Anomaly] = []
    by_frame: dict[int, list[Anomaly]] = {}
    window: list[dict[str, Any]] = []
    WIN = 64
    for rec in records:
        update_innings_tracking(state, rec)
        window.append(rec)
        if len(window) > WIN:
            window = window[-WIN:]
        for _id, fn in RULES:
            try:
                anoms = fn(state, rec, window)
            except Exception as e:  # noqa: BLE001
                anoms = [Anomaly(
                    id=_id,
                    severity="warn",
                    fired_at_frame=_frame(rec),
                    first_evidence_frame=_frame(rec),
                    duration_frames=0,
                    evidence={"_rule_error": str(e)},
                    verdict="Rule raised; record skipped.",
                )]
            for a in anoms:
                all_fired.append(a)
                by_frame.setdefault(a.fired_at_frame, []).append(a)
    return all_fired, by_frame
