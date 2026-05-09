"""Detects new ball events from LLM extraction diffs."""
from __future__ import annotations

import time

from eyes.cricket_logger import CricketLogger

log = CricketLogger("BALL")


class BallDetector:
    """Detects when a new ball was bowled by comparing consecutive extractions.

    Uses score/wickets/overs changes with a minimum time gap to avoid
    duplicate detections from multiple frames of the same delivery.
    """

    def __init__(self, min_gap: float = 8.0):
        self.prev_score: int | None = None
        self.prev_wickets: int | None = None
        self.prev_overs: str | None = None
        self.last_ball_time: float = 0
        self.min_gap = min_gap
        self.total_detected = 0

    def check(self, scoreboard: dict) -> dict | None:
        """Returns a ball event dict if a new ball was bowled, else None."""
        if not scoreboard or scoreboard.get("score") is None:
            log.error("Score is None — can't detect ball")
            return None

        score = scoreboard["score"]
        wickets = scoreboard.get("wickets", 0)
        overs = scoreboard.get("overs")

        if not isinstance(score, (int, float)):
            try:
                score = int(score)
            except (ValueError, TypeError):
                return None

        if not isinstance(wickets, (int, float)):
            try:
                wickets = int(wickets)
            except (ValueError, TypeError):
                wickets = 0

        # First extraction — set baseline
        if self.prev_score is None:
            self.prev_score = score
            self.prev_wickets = wickets
            self.prev_overs = overs
            return None

        score_changed = score != self.prev_score
        wickets_changed = wickets != self.prev_wickets
        overs_changed = overs != self.prev_overs

        if not (score_changed or wickets_changed or overs_changed):
            return None

        now = time.time()
        if now - self.last_ball_time < self.min_gap:
            gap = now - self.last_ball_time
            log.warn(f"Rejected: only {gap:.0f}s since last ball (min {self.min_gap:.0f}s)")
            return None

        runs = score - self.prev_score
        wicket_fell = wickets > self.prev_wickets

        # Reject impossible transitions — don't create false ball events
        if score < self.prev_score:
            log.warn(f"Score decreased {self.prev_score}→{score} — misread, REJECTING")
            return None
        if overs and self.prev_overs:
            try:
                new_ball = float(overs)
                old_ball = float(self.prev_overs)
                if new_ball < old_ball and new_ball != 0.1:
                    log.warn(f"Overs went {self.prev_overs}→{overs} — backwards, REJECTING")
                    return None
            except (ValueError, TypeError):
                pass
        if runs > 7:
            if self.total_detected == 0:
                log.info(f"First baseline: {self.prev_score}→{score} (+{runs}) — accepting as startup")
                self.prev_score = score
                self.prev_wickets = wickets
                self.prev_overs = overs
                return None
            log.warn(f"Score jumped +{runs} ({self.prev_score}→{score}) — too large, REJECTING")
            return None

        runs = max(0, runs)

        if wicket_fell:
            result = "wicket"
        elif runs == 0:
            result = "dot"
        elif runs == 1:
            result = "single"
        elif runs == 2:
            result = "two"
        elif runs == 3:
            result = "three"
        elif runs == 4:
            result = "four"
        elif runs == 6:
            result = "six"
        else:
            result = f"extras_or_missed_balls_{runs}"

        ball = {
            "ball_number": overs or self.prev_overs,
            "runs": runs,
            "result": result,
            "wicket": wicket_fell,
            "prev_score": self.prev_score,
            "new_score": score,
            "timestamp": now,
        }

        # Log the ball event
        if wicket_fell:
            log.info(f"NEW BALL {overs or '?'} | {self.prev_score}→{score} (+{runs}) wickets {self.prev_wickets}→{wickets} | {result}")
        else:
            log.info(f"NEW BALL {overs or '?'} | {self.prev_score}→{score} (+{runs}) | {result}")

        self.prev_score = score
        self.prev_wickets = wickets
        self.prev_overs = overs
        self.last_ball_time = now
        self.total_detected += 1

        return ball

    def reset(self):
        self.prev_score = None
        self.prev_wickets = None
        self.prev_overs = None
        self.last_ball_time = 0
