"""Validation system: cricket rules + monotonic progress (no majority vote)."""
from __future__ import annotations

import time
from collections import deque

from eyes.state.match_validator import MatchStateValidator, ValidationIssue
from eyes.cricket_logger import CricketLogger

log = CricketLogger("AUTOVAL")


class AutoValidator:
    """Two-level validation:
    Level 1: Internal consistency (cricket math) — via MatchStateValidator
    Level 2: Monotonic progress — score/overs/wickets can only go forward
    Level 3: Cross-source (compare against broadcast scorecards)

    NO majority-vote consensus. It locks on wrong values and creates
    a death spiral where correct readings get rejected.

    Instead: accept any reading that moves FORWARD. Reject anything
    that moves backward (misread). For score, require 3+ sightings
    of a higher value before accepting a jump.
    """

    SCORE_BREAKOUT_COUNT = 2  # accept higher score after seeing it N times

    def __init__(self, match_format: str = "T20"):
        self._match_validator = MatchStateValidator(match_format)

        # Confirmed state (only moves forward)
        self._confirmed_score: int = 0
        self._confirmed_wickets: int = 0
        self._confirmed_overs: str = "0.0"

        # Pending higher score (breakout mechanism)
        self._pending_score: int | None = None
        self._pending_score_count: int = 0

        # Accuracy tracking
        self._total_frames = 0
        self._accepted_frames = 0
        self._rejected_frames = 0
        self._broadcast_corrections: list[dict] = []

    def on_frame(self, scoreboard: dict) -> tuple[dict, list[ValidationIssue]]:
        """Validate and accept/reject a frame's scoreboard reading."""
        self._total_frames += 1

        # Level 1: cricket rules
        validated, issues = self._match_validator.validate(scoreboard)

        if validated.get("score") is None:
            return validated, issues

        try:
            score = int(validated.get("score", 0))
            validated["score"] = score
        except (ValueError, TypeError):
            return validated, issues
        try:
            wickets = int(validated.get("wickets", 0))
            validated["wickets"] = wickets
        except (ValueError, TypeError):
            wickets = 0
        overs = str(validated.get("overs", "")) if validated.get("overs") else None

        # --- SCORE: breakout mechanism ---
        # Accept any higher score once we've seen a "higher than confirmed" reading
        # N times. The readings don't have to be identical — 115 then 116 both count
        # because the score only goes up.
        if score > self._confirmed_score:
            if self._pending_score is not None and score >= self._pending_score:
                self._pending_score_count += 1
                self._pending_score = score  # track the latest high
            else:
                self._pending_score = score
                self._pending_score_count = 1

            if self._pending_score_count >= self.SCORE_BREAKOUT_COUNT:
                log.info(f"Score advanced: {self._confirmed_score} → {score} (seen {self._pending_score_count}x)")
                self._confirmed_score = score
                self._pending_score = None
                self._pending_score_count = 0
            else:
                log.info(f"Score {score} pending ({self._pending_score_count}/{self.SCORE_BREAKOUT_COUNT} sightings)")
        elif score < self._confirmed_score:
            log.warn(f"Score decreased {self._confirmed_score}→{score} — using confirmed")
            issues.append(ValidationIssue(
                "score_decreased", f"Read {score} < confirmed {self._confirmed_score}", "warning"))
            self._rejected_frames += 1

        validated["score"] = self._confirmed_score

        # --- WICKETS: accept any forward movement ---
        if wickets >= self._confirmed_wickets:
            if wickets > self._confirmed_wickets:
                log.info(f"Wickets advanced: {self._confirmed_wickets} → {wickets}")
            self._confirmed_wickets = wickets
        else:
            log.warn(f"Wickets decreased {self._confirmed_wickets}→{wickets} — using confirmed")
            self._rejected_frames += 1

        validated["wickets"] = self._confirmed_wickets

        # --- OVERS: accept any valid forward movement ---
        if overs and self._is_valid_over(overs):
            if self._overs_ge(overs, self._confirmed_overs):
                if overs != self._confirmed_overs:
                    log.info(f"Overs advanced: {self._confirmed_overs} → {overs}")
                self._confirmed_overs = overs
            else:
                log.warn(f"Overs went backward {self._confirmed_overs}→{overs} — using confirmed")
                self._rejected_frames += 1

        validated["overs"] = self._confirmed_overs
        self._accepted_frames += 1
        return validated, issues

    @staticmethod
    def _is_valid_over(ov: str) -> bool:
        """Check if an overs string is structurally valid (e.g. '7.4')."""
        try:
            if "." in ov:
                whole, ball = ov.split(".")
                return 0 <= int(whole) <= 50 and 0 <= int(ball) <= 5
            else:
                return 0 <= int(ov) <= 50
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _overs_ge(a: str, b: str) -> bool:
        """Return True if overs 'a' >= overs 'b'."""
        try:
            def to_balls(ov: str) -> int:
                if "." in ov:
                    whole, ball = ov.split(".")
                    return int(whole) * 6 + int(ball)
                return int(ov) * 6
            return to_balls(a) >= to_balls(b)
        except (ValueError, TypeError):
            return True

    def on_broadcast_scorecard(
        self, broadcast_data: dict, current_innings: dict
    ) -> list[dict]:
        """Level 3: Cross-validate against a broadcast scorecard graphic."""
        corrections = []

        if not broadcast_data or not current_innings:
            return corrections

        broadcast_batters = broadcast_data.get("batters", [])
        if isinstance(broadcast_batters, list):
            for b_entry in broadcast_batters:
                name = b_entry.get("name", "")
                runs = b_entry.get("runs")
                if name and runs is not None:
                    our_batter = current_innings.get("batting_card", {}).get(name)
                    if our_batter:
                        our_runs = our_batter.get("runs")
                        if our_runs is not None and our_runs != runs:
                            corrections.append({
                                "type": "batter_runs", "name": name,
                                "our_value": our_runs, "broadcast_value": runs,
                                "source": "broadcast_scorecard",
                            })

        broadcast_bowlers = broadcast_data.get("bowlers", [])
        if isinstance(broadcast_bowlers, list):
            for b_entry in broadcast_bowlers:
                name = b_entry.get("name", "")
                runs = b_entry.get("runs")
                if name and runs is not None:
                    our_bowler = current_innings.get("bowling_card", {}).get(name)
                    if our_bowler:
                        our_runs = our_bowler.get("runs")
                        if our_runs is not None and our_runs != runs:
                            corrections.append({
                                "type": "bowler_runs", "name": name,
                                "our_value": our_runs, "broadcast_value": runs,
                                "source": "broadcast_scorecard",
                            })

        if corrections:
            for c in corrections:
                log.warn(f"Broadcast correction: {c['name']}.{c['type'].split('_')[-1]} ours={c['our_value']} broadcast={c['broadcast_value']}")
            self._broadcast_corrections.extend(corrections)

        return corrections

    def get_accuracy_report(self) -> dict:
        total = max(self._total_frames, 1)
        return {
            "total_frames": self._total_frames,
            "accepted_frames": self._accepted_frames,
            "rejected_frames": self._rejected_frames,
            "acceptance_rate": self._accepted_frames / total,
            "broadcast_corrections": len(self._broadcast_corrections),
            "rule_violations": self._match_validator.get_issues_count(),
            "confirmed": {
                "score": self._confirmed_score,
                "wickets": self._confirmed_wickets,
                "overs": self._confirmed_overs,
            },
        }

    def reset(self):
        self._match_validator.reset()
        self._confirmed_score = 0
        self._confirmed_wickets = 0
        self._confirmed_overs = "0.0"
        self._pending_score = None
        self._pending_score_count = 0
        self._total_frames = 0
        self._accepted_frames = 0
        self._rejected_frames = 0
        self._broadcast_corrections.clear()
