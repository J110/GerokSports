"""Pure-derivation module for the triple-subsystem greenfield rewrite.

Specifies `SnapshotPrimitives` and three derivation functions used by
the canonical commit paths (`apply_wicket_event`, `apply_striker_event`,
`apply_this_over_token`) introduced by §12 / §13 / §14 of
`files/docs/investigations/differential_testing_methodology_design.md`.

The functions here are PURE — no side effects, no SM access, no
scoreboard access, no logging, no trace emission. They take two
`SnapshotPrimitives` (prior + current) and return event objects (or
None when no event is implied by the delta). The commit functions
(landed in subsequent §15 commits) consume these events and perform
the actual state mutations.

§15 Session A step 1 deliverable: this module + unit tests in
`files/tests/test_score_manager_derivation.py`. No call-site changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


class WicketAmbiguousDualChange(Exception):
    """Raised when both batter slots changed between prior + current,
    making the dismissed-batter set-difference ambiguous (Edge Case 3
    in §12.2). Callers must defer the wicket dispatch until a confident
    single-slot change is observed."""


@dataclass(frozen=True)
class SnapshotPrimitives:
    """Single immutable input to all three derivation functions.

    Field set is the UNION of what wicket / striker / this_over
    derivations need. Per §12.2 plus §13.2 first_striker plus §14.2
    extras-type breakdown + legal-ball counter.
    """
    score: int
    wickets: int
    overs: str                    # "10.5" — ball_id convention, NOT post-rollover float
    bat1_name: Optional[str]      # at-the-crease set, position-agnostic
    bat2_name: Optional[str]
    bowler_name: Optional[str]
    striker: Optional[str]        # current pointer (None on cold-start)
    extras_total: int             # sum of wd+nb+b+lb
    non_striker: Optional[str] = None  # partner pointer (None on cold-start)
    extras_wd: int = 0
    extras_nb: int = 0
    extras_b: int = 0
    extras_lb: int = 0
    first_striker: Optional[str] = None  # Scout primitive for cold-start init
    legal_balls_in_over: int = 0  # 0-5; rolls over to 0 after 6th legal ball


_NON_BOWLER_DISMISSALS = {
    "run_out", "runout", "obstructed_field", "retired", "retired_hurt",
    "timed_out", "handled_ball", "hit_ball_twice",
}


def is_bowler_attributable(wicket_type: Optional[str]) -> bool:
    """Cricket rule: bowler is credited for caught / bowled / lbw /
    stumped / hit-wicket / bowler_wicket (and any other dismissal
    not on the explicit non-bowler list). NOT credited for run-out /
    obstructed-field / timed-out / handled-ball / retired. Unknown /
    None defaults to attributable (matches the pre-rewrite default
    in _accumulate_stats_from_event)."""
    if not wicket_type:
        return True
    return wicket_type.lower().replace(" ", "_") not in _NON_BOWLER_DISMISSALS


@dataclass(frozen=True)
class WicketEvent:
    delta_wickets: int                   # >= 1 (function returns None if 0)
    over_ball: str                       # current.overs at dispatch
    bowler_name: Optional[str]           # tracker-locked current bowler
    dismissed_batter: Optional[str]      # None on Edge Case 2 (deferred)
    delta_score: int                     # current.score - prior.score
    delta_extras: int                    # current.extras_total - prior.extras_total
    this_over_token: str                 # composed per §12.2 rules below
    is_extras_dismissal: bool            # delta_extras > 0 same frame
    is_runout_speculative: bool          # delta_score > 0 same frame
    wicket_type: Optional[str] = None    # caught/bowled/lbw/stumped/run_out/...
    wicket_number: Optional[int] = None  # 1-indexed wicket # (for FoW slot)
    new_batter: Optional[str] = None     # current_at_crease - prior_at_crease - {dismissed}


@dataclass(frozen=True)
class StrikerEvent:
    prev_striker: Optional[str]
    next_striker: Optional[str]
    prev_non_striker: Optional[str]
    next_non_striker: Optional[str]
    reason: str
    # reason ∈ {"first_striker_init", "odd_run_rotation",
    #          "end_of_over_swap", "wicket_new_batter",
    #          "wicket_non_striker_stays", "no_change",
    #          "runout_ambiguous_default_parity",
    #          "lost_frames_ambiguous"}


@dataclass(frozen=True)
class PendingCascade:
    """Workstream G Shape A — deferred post-wicket striker cascade.

    Populated by `_apply_post_wicket_striker_rotation` when
    `event.new_batter` is None at wicket-commit (G2 strip-render-lag root
    per `workstream_g_scout_extraction_timing.md` §3.3). Drained by
    `_attempt_pending_cascade_drain` once Scout slot-diff resolves the
    new batter or the TTL expires.

    Mitigation A (audit §2.3.1): captures `prev_striker` /
    `prev_non_striker` BEFORE the `_apply_wicket_fall_only` fallback at
    `score_manager.py:5768-5776` nulls the dismissed slot. The drain
    rebuilds the StrikerEvent from this captured pair, not from the
    live `self.striker` / `self.non` (which have been nulled by drain
    time).
    """
    wicket_event: WicketEvent
    dismissed: str
    survivor: Optional[str]
    reason: str  # "wicket_new_batter" | "wicket_non_striker_stays"
    prev_striker: Optional[str]
    prev_non_striker: Optional[str]
    frame_set_at: int
    wicket_frame_for_history: int
    ttl_frames: int = 80


@dataclass(frozen=True)
class ThisOverToken:
    raw: str                             # "." | "1"-"6" | "W" | "Wd"...
    delta_score: int
    delta_legal_balls: int               # 0 or 1 for normal cases
    wicket_flag: bool
    extras_type: Optional[str]           # "wd" | "nb" | "b" | "lb" | None
    cluster_tokens: list[str] = field(default_factory=list)
    # cluster_tokens populated only for "MULTI" raw (lost-frames case
    # per §14.7 #2). Caller decides how to render — Recent-Overs panel
    # shows '?' per Obs 11b's existing behavior.


# ─────────────────────────────────────────────────────────────────────
# §12.2 — derive_wicket_event
# ─────────────────────────────────────────────────────────────────────


def _at_crease(snap: SnapshotPrimitives) -> set[str]:
    return {n for n in (snap.bat1_name, snap.bat2_name) if n}


def _compose_wicket_token(
    delta_score: int,
    delta_extras: int,
    prior_wd: int,
    prior_nb: int,
    current_wd: int,
    current_nb: int,
) -> str:
    """§12.2 token composition rules."""
    if delta_extras > 0 and delta_score == delta_extras:
        # Wicket-on-extras (e.g. 10.2 wide-stumping). Disambiguate
        # wd vs nb via per-type delta.
        d_wd = current_wd - prior_wd
        d_nb = current_nb - prior_nb
        if d_nb > 0:
            return "Nb+W"
        if d_wd > 0:
            return "Wd+W"
        # Fallback when type unknown (shouldn't happen if primitives
        # are well-formed); emit generic compound.
        return "Wd+W"
    if delta_score > 0:
        return f"{delta_score}+W"
    return "W"


def derive_wicket_event(
    prior: SnapshotPrimitives,
    current: SnapshotPrimitives,
    tracker_locked_bowler: Optional[str],
) -> Optional[WicketEvent]:
    """Pure derivation per §12.2. Returns None on no-wicket transitions.

    Set-difference rule:
      diff = prior_at_crease - current_at_crease
      if len(diff) == 1: dismissed = diff.pop()
      if len(diff) == 0: dismissed = None  (Edge Case 2 — caller defers)
      if len(diff) >= 2: raise WicketAmbiguousDualChange  (Edge Case 3)
    """
    delta_w = current.wickets - prior.wickets
    if delta_w <= 0:
        return None

    prior_set = _at_crease(prior)
    current_set = _at_crease(current)
    diff = prior_set - current_set
    if len(diff) == 1:
        dismissed = next(iter(diff))
    elif len(diff) == 0:
        dismissed = None
    else:
        raise WicketAmbiguousDualChange(
            f"Both batter slots changed between prior "
            f"{sorted(prior_set)} and current {sorted(current_set)} — "
            f"cannot resolve dismissed batter from set-difference alone")

    delta_score = current.score - prior.score
    delta_extras = current.extras_total - prior.extras_total
    token = _compose_wicket_token(
        delta_score=delta_score,
        delta_extras=delta_extras,
        prior_wd=prior.extras_wd,
        prior_nb=prior.extras_nb,
        current_wd=current.extras_wd,
        current_nb=current.extras_nb,
    )
    # §12.3 step 5 (commit 8/N): new_batter via reverse set-difference.
    # The current at-crease set minus the prior set minus the dismissed
    # batter = the post-wicket arrival. None when Scout primitive lags
    # (new batter slot not yet observable); caller defers cascade.
    arrived = current_set - prior_set
    if dismissed is not None:
        arrived = arrived - {dismissed}
    new_batter = next(iter(arrived)) if len(arrived) == 1 else None

    return WicketEvent(
        delta_wickets=delta_w,
        over_ball=current.overs,
        bowler_name=tracker_locked_bowler,
        dismissed_batter=dismissed,
        delta_score=delta_score,
        delta_extras=delta_extras,
        this_over_token=token,
        is_extras_dismissal=delta_extras > 0,
        is_runout_speculative=delta_score > 0,
        new_batter=new_batter,
    )


# ─────────────────────────────────────────────────────────────────────
# §13.2 — derive_striker_event
# ─────────────────────────────────────────────────────────────────────


def derive_striker_event(
    prior: SnapshotPrimitives,
    current: SnapshotPrimitives,
    wicket_event: Optional[WicketEvent],
    over_boundary_crossed: bool,
    legal_ball_completed: bool,
) -> StrikerEvent:
    """Pure derivation per §13.2.

    Rule order matters — earlier rules short-circuit:
      1. Cold-start (prior.striker is None) → first_striker_init.
      2. Wicket event with set-difference dismissed → wicket_new_batter
         or wicket_non_striker_stays (cascades into end-of-over swap
         if the wicket ball also completed an over).
      3. Over-boundary crossed by a legal ball → end_of_over_swap.
      4. Legal-ball with delta_score odd (excludes extras-only Δ) →
         odd_run_rotation.
      5. Else → no_change.

    Returns the full rotation pair (striker, non_striker). B-2 contract:
    apply_striker_event mutates both atomically.
    """
    prev = prior.striker
    prev_non = prior.non_striker or _other_at_crease(prior, prev)

    # Rule 1: cold-start init. Gated on BOTH striker AND non-striker
    # being None — that's the true innings-start state. A mid-innings
    # post-wicket striker=None (slot cleared by wicket dispatch, non
    # remains the survivor) must NOT trigger cold-start init: that
    # would re-seed striker from self.first_striker (the innings
    # opener), causing wrong-batter attribution from the wicket frame
    # onward. Discovered as +2 Boundary-counter-double-increment at
    # over_ball 8.5 during §15 step-7 wire-through attempt.
    if prev is None and prior.non_striker is None:
        if current.first_striker:
            new_non = _other_at_crease(current, current.first_striker)
            return StrikerEvent(
                prev_striker=None,
                next_striker=current.first_striker,
                prev_non_striker=prev_non,
                next_non_striker=new_non,
                reason="first_striker_init",
            )
        # No Scout primitive — leave None for caller to defer
        return StrikerEvent(
            prev_striker=None,
            next_striker=None,
            prev_non_striker=prev_non,
            next_non_striker=prev_non,
            reason="no_change",
        )
    if prev is None:
        # Post-wicket slot-clear or pipeline drift — striker is None
        # but non-striker is populated. Refuse to derive a new striker
        # from cold-start primitives; let upstream wicket-event /
        # Scout-read resolve it.
        return StrikerEvent(
            prev_striker=None,
            next_striker=None,
            prev_non_striker=prev_non,
            next_non_striker=prev_non,
            reason="no_change",
        )

    # Rule 2: wicket-driven
    if wicket_event is not None and wicket_event.delta_wickets > 0:
        dismissed = wicket_event.dismissed_batter
        if dismissed is None:
            # Edge Case §13.6.1 — run-out-on-completed-Nth-run with
            # ambiguous resolution. Fall through to standard parity
            # rotation; flag the ambiguity for telemetry.
            if legal_ball_completed and wicket_event.delta_score % 2 == 1:
                return StrikerEvent(
                    prev_striker=prev,
                    next_striker=_swap_partner(prior, prev),
                    prev_non_striker=prev_non,
                    next_non_striker=prev,
                    reason="runout_ambiguous_default_parity",
                )
            return StrikerEvent(
                prev_striker=prev,
                next_striker=prev,
                prev_non_striker=prev_non,
                next_non_striker=prev_non,
                reason="runout_ambiguous_default_parity",
            )

        # New batter = (current_at_crease - prior_at_crease).pop()
        new_at_crease = _at_crease(current) - _at_crease(prior)
        new_batter = next(iter(new_at_crease)) if len(new_at_crease) == 1 else None
        survivor = prev_non if dismissed == prev else prev

        if dismissed == prev:
            # Striker dismissed → new batter takes strike
            base_next = new_batter
            base_non = survivor
            base_reason = "wicket_new_batter"
        else:
            # Non-striker dismissed → striker stays; new batter is non-striker
            base_next = prev
            base_non = new_batter
            base_reason = "wicket_non_striker_stays"

        # Cascade end-of-over swap when the wicket-ball also rolled the over
        if legal_ball_completed and over_boundary_crossed and base_next and base_non:
            return StrikerEvent(
                prev_striker=prev,
                next_striker=base_non,
                prev_non_striker=prev_non,
                next_non_striker=base_next,
                reason=base_reason,
            )
        return StrikerEvent(
            prev_striker=prev,
            next_striker=base_next,
            prev_non_striker=prev_non,
            next_non_striker=base_non,
            reason=base_reason,
        )

    # §13.6 #5 — lost-frames guard. If multiple legal balls passed
    # between snapshots, striker rotation cannot be derived. Refuse;
    # let the next confident snapshot re-anchor.
    if legal_ball_completed and _legal_balls_delta(prior, current) > 1:
        return StrikerEvent(
            prev_striker=prev,
            next_striker=prev,
            prev_non_striker=prev_non,
            next_non_striker=prev_non,
            reason="lost_frames_ambiguous",
        )

    # Rules 3 + 4 combined — cricket rules cascade via XOR.
    if legal_ball_completed:
        delta_score = current.score - prior.score
        non_crossing_extras = (
            (current.extras_wd - prior.extras_wd)
            + (current.extras_nb - prior.extras_nb))
        crossing_runs = delta_score - non_crossing_extras
        swap_for_runs = (crossing_runs % 2 == 1)
        swap_for_over_end = over_boundary_crossed
        if swap_for_runs ^ swap_for_over_end:
            # Cricket swap = (striker ↔ non_striker) pair exchange.
            # Pure pointer swap — works for (X, None) just as for
            # (X, Y). Mirrors the original inline
            # `self.striker, self.non = self.non, self.striker`
            # exactly, including the (Nissanka, None) → (None,
            # Nissanka) case that step-7c surfaced at over 8.4.
            return StrikerEvent(
                prev_striker=prev,
                next_striker=prev_non,
                prev_non_striker=prev_non,
                next_non_striker=prev,
                reason="end_of_over_swap" if swap_for_over_end
                else "odd_run_rotation",
            )
        if swap_for_runs and swap_for_over_end:
            # Two swaps cancel — net no rotation.
            return StrikerEvent(
                prev_striker=prev,
                next_striker=prev,
                prev_non_striker=prev_non,
                next_non_striker=prev_non,
                reason="no_change",
            )

    return StrikerEvent(
        prev_striker=prev,
        next_striker=prev,
        prev_non_striker=prev_non,
        next_non_striker=prev_non,
        reason="no_change",
    )


def _other_at_crease(
    snap: SnapshotPrimitives, name: Optional[str]
) -> Optional[str]:
    """Return the at-crease batter who isn't `name`."""
    if not name:
        if snap.bat1_name:
            return snap.bat1_name
        return snap.bat2_name
    if snap.bat1_name == name:
        return snap.bat2_name
    if snap.bat2_name == name:
        return snap.bat1_name
    if snap.bat1_name:
        return snap.bat1_name
    return snap.bat2_name


def _swap_partner(snap: SnapshotPrimitives, prev: str) -> Optional[str]:
    """Return the at-crease batter who isn't `prev`."""
    if snap.bat1_name == prev:
        return snap.bat2_name
    if snap.bat2_name == prev:
        return snap.bat1_name
    # Not in either slot — pipeline state drift; return prev unchanged
    return prev


def _resolve_partner(snap: SnapshotPrimitives, name: str) -> Optional[str]:
    if snap.bat1_name and snap.bat1_name != name:
        return snap.bat1_name
    if snap.bat2_name and snap.bat2_name != name:
        return snap.bat2_name
    return None


# ─────────────────────────────────────────────────────────────────────
# §14.2 — derive_this_over_token
# ─────────────────────────────────────────────────────────────────────


_EXTRAS_TYPE_PRIORITY = ("nb", "wd", "lb", "b")


def _extras_delta_breakdown(
    prior: SnapshotPrimitives,
    current: SnapshotPrimitives,
) -> tuple[int, Optional[str]]:
    """Return (delta_total, dominant_type) for the extras delta."""
    d_total = current.extras_total - prior.extras_total
    if d_total == 0:
        return 0, None
    deltas = {
        "wd": current.extras_wd - prior.extras_wd,
        "nb": current.extras_nb - prior.extras_nb,
        "b": current.extras_b - prior.extras_b,
        "lb": current.extras_lb - prior.extras_lb,
    }
    for t in _EXTRAS_TYPE_PRIORITY:
        if deltas[t] > 0:
            return d_total, t
    return d_total, None


def derive_this_over_token(
    prior: SnapshotPrimitives,
    current: SnapshotPrimitives,
    wicket_event: Optional[WicketEvent],
) -> Optional[ThisOverToken]:
    """Pure derivation per §14.2.

    Returns None on idle frames (no Δ in score / wickets / extras).
    """
    delta_score = current.score - prior.score
    delta_wickets = current.wickets - prior.wickets
    delta_extras, extras_type = _extras_delta_breakdown(prior, current)
    runs_off_bat = delta_score - delta_extras

    # Legal-ball delta — derive from the over-ball string when possible
    # (the over.ball coordinate increments by 1 legal ball per frame
    # transition; >1 means lost frames). Fall back to legal_balls_in_over
    # delta when overs is malformed.
    delta_legal_balls = _legal_balls_delta(prior, current)

    # Idle frame: no delta in any tracked dimension
    if (delta_score == 0 and delta_wickets == 0
            and delta_extras == 0 and delta_legal_balls == 0):
        return None

    # Lost-frames cluster: multiple legal balls in one snapshot
    if delta_legal_balls > 1:
        cluster = ["?"] * delta_legal_balls
        return ThisOverToken(
            raw="MULTI",
            delta_score=delta_score,
            delta_legal_balls=delta_legal_balls,
            wicket_flag=delta_wickets > 0,
            extras_type=extras_type,
            cluster_tokens=cluster,
        )

    # Wicket-bearing frames
    if delta_wickets > 0:
        # Reuse the wicket-event token composer for consistency.
        if wicket_event is not None:
            return ThisOverToken(
                raw=wicket_event.this_over_token,
                delta_score=delta_score,
                delta_legal_balls=delta_legal_balls,
                wicket_flag=True,
                extras_type=extras_type,
            )
        # No wicket event passed — derive token inline.
        token = _compose_wicket_token(
            delta_score=delta_score,
            delta_extras=delta_extras,
            prior_wd=prior.extras_wd,
            prior_nb=prior.extras_nb,
            current_wd=current.extras_wd,
            current_nb=current.extras_nb,
        )
        return ThisOverToken(
            raw=token,
            delta_score=delta_score,
            delta_legal_balls=delta_legal_balls,
            wicket_flag=True,
            extras_type=extras_type,
        )

    # Extras-only frame (wide / no-ball — no legal ball)
    if delta_legal_balls == 0 and delta_extras > 0:
        # Wide / no-ball. Format: "Wd" / "Nb" if base 1 extra,
        # else "<N>wd" / "<N>nb" for multi-run extras.
        prefix = "Wd" if extras_type == "wd" else "Nb"
        if delta_extras == 1:
            return ThisOverToken(
                raw=prefix,
                delta_score=delta_score,
                delta_legal_balls=0,
                wicket_flag=False,
                extras_type=extras_type,
            )
        return ThisOverToken(
            raw=f"{delta_extras - 1}{prefix.lower()}"
            if extras_type in ("wd", "nb") else f"{delta_extras}{prefix.lower()}",
            delta_score=delta_score,
            delta_legal_balls=0,
            wicket_flag=False,
            extras_type=extras_type,
        )

    # Legal-ball bye / leg-bye (legal ball + extras runs, no runs off bat)
    if delta_legal_balls == 1 and delta_extras > 0 and runs_off_bat == 0:
        suffix = "b" if extras_type == "b" else "lb"
        return ThisOverToken(
            raw=f"{delta_extras}{suffix}",
            delta_score=delta_score,
            delta_legal_balls=1,
            wicket_flag=False,
            extras_type=extras_type,
        )

    # Standard legal ball
    if delta_legal_balls == 1:
        # WS-O.b PE — cricket-physics negative-runs guard. A legal
        # ball cannot produce negative off-bat runs; emitting str(-N)
        # leaked into UI snapshots as `this_over_tokens: ["-27", ...]`
        # post-WS-O step-3 baseline. Return None so the caller's
        # existing `if _wire_token is not None: ... else: append("?")`
        # fallback at score_manager.py:6682 / :6815 routes to a
        # placeholder rather than the negative string.
        if runs_off_bat < 0:
            return None
        if runs_off_bat == 0:
            raw = "."
        elif 1 <= runs_off_bat <= 6:
            raw = str(runs_off_bat)
        else:
            raw = str(runs_off_bat)  # 7+ is rare but legal (overthrows)
        return ThisOverToken(
            raw=raw,
            delta_score=delta_score,
            delta_legal_balls=1,
            wicket_flag=False,
            extras_type=None,
        )

    # Shouldn't reach here — defensive return for malformed input
    return None


def _legal_balls_delta(
    prior: SnapshotPrimitives,
    current: SnapshotPrimitives,
) -> int:
    """Compute legal-balls delta from over.ball strings.

    Handles rollover ("0.6" → "1.0" or "1.1" depending on convention).
    Falls back to legal_balls_in_over snapshot field on parse failure.
    """
    try:
        c1, b1 = prior.overs.split(".")
        c2, b2 = current.overs.split(".")
        total_prior = int(c1) * 6 + int(b1)
        total_current = int(c2) * 6 + int(b2)
        return max(0, total_current - total_prior)
    except (AttributeError, ValueError):
        return max(
            0, current.legal_balls_in_over - prior.legal_balls_in_over)
