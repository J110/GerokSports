"""ConfidenceTracker — accumulating-evidence state for ambiguous facts.

Replaces the one-way ratchet locks that broke the 2026-05-11/12 PBKS-DC
replay (test_pipeline.py L6122–6125: `if team_locked and bat_name !=
batting_team: return`).  A pre-match graphic locked `batting_team='RCB'`
on three opening frames; subsequent MI scoreboard frames were silently
dropped by the guard and the pipeline never recovered.

Model
-----
Each fact (e.g. batting_team) gets its own tracker.  Observations add
weighted evidence to a candidate.  Scores decay exponentially in wall-
clock time (half-life), so old evidence fades while sustained contrary
evidence can overtake the leader.

States, derived from the leader's current score:
    NONE         — no observations yet (leader is None).
    TENTATIVE    — leader score in (0, PUBLISH).
    PUBLISHABLE  — leader score in [PUBLISH, FIRM).
    FIRM         — leader score in [FIRM, IMMUTABLE).
    IMMUTABLE    — explicitly locked (innings-end / match-end /
                   operator override).  No further flips.

Flip rule (when not IMMUTABLE):
    A contender becomes the new leader when its score is
    `leader_score + flip_margin` or higher.  Without the margin a
    single contradictory observation could ping-pong leadership at
    near-tie scores.

Tuning defaults (operator-tunable per tracker):
    PUBLISH = 2.0        — ~2 strong observations to publish to UI.
    FIRM    = 5.0        — ~5 strong observations to stop downstream
                           "low confidence" annotations.
    FLIP_MARGIN = 1.0    — contender must beat leader by 1.0 to flip.
    HALF_LIFE_S = 60.0   — score halves every 60 s wall-clock.

Usage
-----
    bt = ConfidenceTracker("batting_team")
    bt.observe("Mumbai Indians", weight=1.0)
    bt.observe("Mumbai Indians", weight=1.0)
    bt.leader            # → "Mumbai Indians"
    bt.state             # → "PUBLISHABLE"

    # 60 s later, contradictory evidence accumulates...
    bt.observe("Royal Challengers Bengaluru", weight=1.0)
    # ... after enough RCB observations to exceed MI + 1.0:
    bt.state             # → "PUBLISHABLE" (RCB is now leader)
    bt.leader            # → "Royal Challengers Bengaluru"

    # End of innings: pin and forbid further flips.
    bt.set_immutable()
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


DEFAULT_PUBLISH = 2.0
DEFAULT_FIRM = 5.0
DEFAULT_FLIP_MARGIN = 1.0
DEFAULT_HALF_LIFE_S = 60.0

STATE_NONE = "NONE"
STATE_TENTATIVE = "TENTATIVE"
STATE_PUBLISHABLE = "PUBLISHABLE"
STATE_FIRM = "FIRM"
STATE_LOCKED = "LOCKED"
STATE_IMMUTABLE = "IMMUTABLE"


@dataclass
class ObserveResult:
    """One observe() return.  Telemetry-shaped for log emission."""

    candidate: str
    weight: float
    leader: str | None
    leader_score: float
    state: str
    scores: dict[str, float]
    old_leader: str | None = None
    flipped: bool = False


class ConfidenceTracker:
    """Accumulating-evidence tracker for a single ambiguous fact."""

    def __init__(
        self,
        name: str = "",
        *,
        publish: float = DEFAULT_PUBLISH,
        firm: float = DEFAULT_FIRM,
        flip_margin: float = DEFAULT_FLIP_MARGIN,
        half_life_s: float = DEFAULT_HALF_LIFE_S,
        auto_lock_on_firm: bool = False,
        clock: Any = None,
    ) -> None:
        """``auto_lock_on_firm``: when True, the leader is one-way
        committed the moment its score crosses ``firm``.  Subsequent
        observations are still recorded in ``_scores`` for telemetry
        but do not move the leader.  ``unlock()`` releases the lock —
        for batting_team, that is the innings-2 transition path.
        Trackers whose fact legitimately changes during the match
        (striker, non_striker, bowler) leave this False so over-end
        and odd-run swaps still flip naturally.
        """
        self.name = name
        self._publish = publish
        self._firm = firm
        self._flip_margin = flip_margin
        self._half_life = half_life_s
        self._auto_lock_on_firm = auto_lock_on_firm
        self._clock = clock or time.time
        self._scores: dict[str, float] = {}
        self._last_t: float = 0.0
        self._leader: str | None = None
        self._immutable: bool = False
        self._locked: bool = False
        # B1.3 (no_multiball_design.md §2.8): single optional callback
        # fired on the state transition into LOCKED. SM wires this to
        # drive _resweep_pending_attribution + _drain_pending_queue.
        # Re-entrancy: callback runs synchronously in observe(); the
        # drain path calls _apply_bowler_delta / _apply_batter_delta
        # which do NOT invoke the tracker (verified pre-B1.3 per §6.3).
        self.on_lock: Any = None

    # ── public observe ────────────────────────────────────────────
    def observe(
        self,
        candidate: str,
        weight: float = 1.0,
        *,
        t: float | None = None,
    ) -> ObserveResult:
        """Add `weight` evidence to `candidate`.  Decays existing
        scores by half-life since the last observation."""
        now = float(t) if t is not None else float(self._clock())
        if self._scores:
            self._apply_decay(now)
        self._last_t = now
        self._scores[candidate] = (
            self._scores.get(candidate, 0.0) + weight)
        old_leader = self._leader
        flipped = False
        if not self._immutable and not self._locked:
            new_leader, new_score = max(
                self._scores.items(), key=lambda kv: kv[1])
            if self._leader is None:
                self._leader = new_leader
            elif new_leader != self._leader:
                leader_score = self._scores.get(self._leader, 0.0)
                if new_score >= leader_score + self._flip_margin:
                    self._leader = new_leader
                    flipped = True
            # Auto-lock on FIRM: one-way commit for facts that don't
            # change during an innings (batting_team).  After lock the
            # leader is fixed until unlock() — typically called by the
            # innings-2 detection path with a reset() + reseed.
            _pre_locked = self._locked
            if (self._auto_lock_on_firm
                    and self._leader is not None
                    and self._scores.get(self._leader, 0.0) >= self._firm):
                self._locked = True
            # B1.3 §2.8: fire on_lock on False→True transition of _locked.
            if (self.on_lock is not None and not _pre_locked
                    and self._locked and self._leader is not None):
                try:
                    self.on_lock(self._leader)
                except Exception:
                    pass
        return ObserveResult(
            candidate=candidate,
            weight=weight,
            leader=self._leader,
            leader_score=self.leader_score,
            state=self.state,
            scores=dict(self._scores),
            old_leader=old_leader,
            flipped=flipped,
        )

    # ── snapshot / state ──────────────────────────────────────────
    def snapshot(self, *, t: float | None = None) -> dict[str, Any]:
        """Read-only state at time `t` (default: now).  Applies decay
        so callers see the same scores observe() would compute."""
        now = float(t) if t is not None else float(self._clock())
        if self._scores:
            self._apply_decay(now)
            self._last_t = now
        return {
            "leader": self._leader,
            "leader_score": self.leader_score,
            "scores": dict(self._scores),
            "state": self.state,
            "immutable": self._immutable,
        }

    @property
    def leader(self) -> str | None:
        return self._leader

    @property
    def leader_score(self) -> float:
        if self._leader is None:
            return 0.0
        return self._scores.get(self._leader, 0.0)

    @property
    def state(self) -> str:
        if self._immutable:
            return STATE_IMMUTABLE
        if self._locked:
            return STATE_LOCKED
        if self._leader is None:
            return STATE_NONE
        s = self.leader_score
        if s <= 0.0:
            return STATE_NONE
        if s >= self._firm:
            return STATE_FIRM
        if s >= self._publish:
            return STATE_PUBLISHABLE
        return STATE_TENTATIVE

    def set_immutable(self, candidate: str | None = None) -> None:
        """Pin the leader and forbid further flips.  Pass `candidate`
        to override the current leader before locking (e.g. for an
        operator-driven correction)."""
        if candidate is not None:
            self._leader = candidate
            self._scores.setdefault(candidate, self._firm)
        self._immutable = True

    def reset(self) -> None:
        """Drop all evidence and unlock.  Use at innings transitions
        or explicit recalibration events."""
        self._scores.clear()
        self._leader = None
        self._immutable = False
        self._locked = False
        self._last_t = 0.0

    def unlock(self) -> None:
        """Release the auto-lock without dropping evidence.  Caller is
        expected to ``reset()`` and re-seed when the new leader is
        known (e.g. innings-2 batting-team transition)."""
        self._locked = False

    def unlock_and_reset(self) -> None:
        """Combined release-and-clear for event-driven re-detection
        (wicket, over end, innings transition).  No-op on IMMUTABLE
        trackers — IMMUTABLE is the operator/innings-end commitment
        and innings-3 is not a thing.  Returns True when state
        actually cleared, False when it was a no-op (caller can log)."""
        if self._immutable:
            return False
        self._locked = False
        self._scores.clear()
        self._leader = None
        self._last_t = 0.0
        return True

    def swap_with(self, other: "ConfidenceTracker") -> None:
        """Swap leader values with another tracker.  Both remain
        LOCKED; only the named candidates exchange.  Used by the
        striker/non_striker odd-run / over-end rotation where the
        identities are already firm but the slot ordering inverts.
        Score dicts swap too so subsequent observations keep weighing
        the right candidate per slot."""
        self._leader, other._leader = other._leader, self._leader
        self._scores, other._scores = other._scores, self._scores

    # ── internal ──────────────────────────────────────────────────
    def _apply_decay(self, now: float) -> None:
        dt = now - self._last_t
        if dt <= 0.0:
            return
        factor = 0.5 ** (dt / self._half_life)
        for k in list(self._scores.keys()):
            self._scores[k] *= factor
            if self._scores[k] < 1e-6:
                self._scores[k] = 0.0
