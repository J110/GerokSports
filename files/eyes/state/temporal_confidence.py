"""Temporal confidence state machine — hold/resume/new match detection."""
from __future__ import annotations

import time

from eyes.cricket_logger import CricketLogger

log = CricketLogger("TEMPO")


class TemporalConfidence:
    """Tracks match state confidence across frames.

    States:
        SEARCHING       — no match detected yet
        TENTATIVE       — cricket data seen, building confidence
        CONFIRMED_MATCH — stable match tracking
        INTERRUPTION    — ad break / timeout / non-cricket content
        NEW_MATCH       — different teams detected for sustained period

    No single frame changes state. Requires sustained evidence.
    """

    TENTATIVE_THRESHOLD = 3        # consecutive cricket frames to confirm
    INTERRUPTION_THRESHOLD = 5     # consecutive non-cricket frames for interruption
    NEW_MATCH_THRESHOLD = 60       # seconds of different teams = new match
    RESUME_THRESHOLD = 2           # cricket frames to resume from interruption

    def __init__(self):
        self.state = "SEARCHING"
        self.confidence = 0.0
        self._cricket_streak = 0
        self._no_data_streak = 0
        self._current_teams: tuple[str, str] | None = None
        self._different_teams_since: float | None = None
        self._state_history: list[dict] = []
        self._last_transition = time.time()

    def on_cricket_data(self, scoreboard: dict):
        """Called when a frame yields valid cricket data."""
        self._no_data_streak = 0
        self._cricket_streak += 1

        teams = self._extract_teams(scoreboard)

        if self.state == "SEARCHING":
            if self._cricket_streak >= self.TENTATIVE_THRESHOLD:
                self._transition("CONFIRMED_MATCH")
                self.confidence = 1.0
                if teams:
                    self._current_teams = teams
            elif self._cricket_streak >= 1:
                self._transition("TENTATIVE")
                self.confidence = self._cricket_streak / self.TENTATIVE_THRESHOLD

        elif self.state == "TENTATIVE":
            if self._cricket_streak >= self.TENTATIVE_THRESHOLD:
                self._transition("CONFIRMED_MATCH")
                self.confidence = 1.0
                if teams:
                    self._current_teams = teams
            else:
                self.confidence = self._cricket_streak / self.TENTATIVE_THRESHOLD

        elif self.state == "INTERRUPTION":
            if self._cricket_streak >= self.RESUME_THRESHOLD:
                if teams and self._current_teams and teams != self._current_teams:
                    log.warn(f"→ INTERRUPTION: different teams detected ({teams[0]} vs {teams[1]}) — holding")
                    self._check_new_match(teams)
                else:
                    duration = time.time() - self._last_transition
                    team_str = f"{self._current_teams[0]} {scoreboard.get('score', '?')}-{scoreboard.get('wickets', '?')}" if self._current_teams else "?"
                    log.info(f"Resumed match after {duration:.0f}s interruption — {team_str} consistent")
                    self._transition("CONFIRMED_MATCH")
                    self.confidence = 1.0
                    self._different_teams_since = None

        elif self.state == "CONFIRMED_MATCH":
            self.confidence = 1.0
            if teams and self._current_teams and teams != self._current_teams:
                self._check_new_match(teams)
            else:
                self._different_teams_since = None

        elif self.state == "NEW_MATCH":
            if teams:
                self._current_teams = teams
            self._transition("CONFIRMED_MATCH")
            self.confidence = 1.0

    def on_no_data(self):
        """Called when a frame has no cricket data (ad, non-cricket, etc.)."""
        self._cricket_streak = 0
        self._no_data_streak += 1

        if self.state in ("CONFIRMED_MATCH", "TENTATIVE"):
            if self._no_data_streak >= self.INTERRUPTION_THRESHOLD:
                log.warn(f"→ INTERRUPTION: no scoreboard for {self._no_data_streak}s")
                self._transition("INTERRUPTION")
                self.confidence = 0.5

        elif self.state == "INTERRUPTION":
            self.confidence = max(0.1, self.confidence - 0.01)
            duration = time.time() - self._last_transition
            if duration > 30 and self._no_data_streak % 30 == 0:
                teams_str = f"{self._current_teams[0]} vs {self._current_teams[1]}" if self._current_teams else "?"
                log.warn(f"Interruption for {duration:.0f}s — still holding {teams_str} state")
            if duration > 180:
                log.error(f"Interruption for {duration:.0f}s — unusually long, possible stream issue")

        elif self.state == "SEARCHING":
            pass

    def _check_new_match(self, teams: tuple[str, str]):
        now = time.time()
        if self._different_teams_since is None:
            self._different_teams_since = now
        elif now - self._different_teams_since > self.NEW_MATCH_THRESHOLD:
            log.error(f"→ NEW_MATCH: {teams[0]} vs {teams[1]} persistent for {self.NEW_MATCH_THRESHOLD}s with advancing score")
            self._transition("NEW_MATCH")
            self._current_teams = teams
            self._different_teams_since = None

    def _transition(self, new_state: str):
        if new_state == self.state:
            return
        now = time.time()
        self._state_history.append({
            "from": self.state,
            "to": new_state,
            "timestamp": now,
            "duration_in_prev": now - self._last_transition,
        })
        log.info(f"State: {new_state} (confidence {self.confidence:.1f})")
        self.state = new_state
        self._last_transition = now

    @staticmethod
    def _extract_teams(scoreboard: dict) -> tuple[str, str] | None:
        bat = scoreboard.get("batting_team")
        bowl = scoreboard.get("bowling_team")
        if bat and bowl:
            return (str(bat).upper(), str(bowl).upper())
        return None

    @property
    def current_teams(self) -> tuple[str, str] | None:
        return self._current_teams

    @property
    def is_confirmed(self) -> bool:
        return self.state == "CONFIRMED_MATCH"

    @property
    def is_interrupted(self) -> bool:
        return self.state == "INTERRUPTION"

    def get_state_summary(self) -> dict:
        return {
            "state": self.state,
            "confidence": round(self.confidence, 2),
            "teams": self._current_teams,
            "cricket_streak": self._cricket_streak,
            "no_data_streak": self._no_data_streak,
            "transitions": len(self._state_history),
        }

    def reset(self):
        self.state = "SEARCHING"
        self.confidence = 0.0
        self._cricket_streak = 0
        self._no_data_streak = 0
        self._current_teams = None
        self._different_teams_since = None
        self._state_history.clear()
        self._last_transition = time.time()
