"""Full match scorecard accumulator — batting, bowling, FOW, partnerships."""
from __future__ import annotations

import time
from copy import deepcopy

from eyes.cricket_logger import CricketLogger

log = CricketLogger("SCORE")


class LiveScorecard:
    """Accumulates the complete match state across both innings.

    Confidence hierarchy: broadcast graphic > LLM extraction > inferred.
    """

    def __init__(self):
        self.current_innings = 1
        self.batting_team: str | None = None
        self.bowling_team: str | None = None
        self.total = 0
        self.wickets = 0
        self.overs: str | None = None
        self.run_rate: float | None = None
        self.target: int | None = None
        self.required_rate: float | None = None

        self._innings: dict[int, dict] = {
            1: self._new_innings(),
            2: self._new_innings(),
        }

        self._current_batter_1: dict | None = None
        self._current_batter_2: dict | None = None
        self._current_bowler: dict | None = None
        self._squads: dict[str, list[str]] = {}

        self._balls: list[dict] = []
        self._this_over: list[str] = []
        self._partnerships: list[dict] = []
        self._current_partnership: dict | None = None

        self._last_wicket_time: float = 0
        self._last_over_change_time: float = 0
        self._previous_bowler: str | None = None

    @staticmethod
    def _new_innings() -> dict:
        return {
            "batting_team": None,
            "bowling_team": None,
            "batting_card": {},   # name → {runs, balls, fours, sixes, how_out, ...}
            "bowling_card": {},   # name → {overs, maidens, runs, wickets, ...}
            "fow": [],            # [{wicket, score, overs, batter}]
            "extras": {"wides": 0, "no_balls": 0, "byes": 0, "leg_byes": 0, "total": 0},
            "total": 0,
            "wickets": 0,
            "overs": "0.0",
        }

    def update_from_scoreboard(self, scoreboard: dict):
        """Update state from a validated scoreboard extraction."""
        if not scoreboard:
            return

        if scoreboard.get("batting_team"):
            self.batting_team = scoreboard["batting_team"]
            self._innings[self.current_innings]["batting_team"] = self.batting_team
        if scoreboard.get("bowling_team"):
            self.bowling_team = scoreboard["bowling_team"]
            self._innings[self.current_innings]["bowling_team"] = self.bowling_team

        if scoreboard.get("score") is not None:
            try:
                new_total = int(scoreboard["score"])
                if new_total >= self.total:
                    self.total = new_total
            except (ValueError, TypeError):
                pass
            self._innings[self.current_innings]["total"] = self.total
        if scoreboard.get("wickets") is not None:
            try:
                new_wickets = int(scoreboard["wickets"])
                if new_wickets < self.wickets:
                    new_wickets = self.wickets
            except (ValueError, TypeError):
                new_wickets = self.wickets
            if new_wickets > self.wickets:
                self._last_wicket_time = time.time()
            self.wickets = new_wickets
            self._innings[self.current_innings]["wickets"] = self.wickets

        if scoreboard.get("overs"):
            new_overs = str(scoreboard["overs"])
            if new_overs != self.overs and self.overs is not None:
                # Check if over boundary crossed
                try:
                    new_whole = int(new_overs.split(".")[0])
                    old_whole = int(self.overs.split(".")[0]) if self.overs else 0
                    if new_whole > old_whole:
                        self._last_over_change_time = time.time()
                        if self._current_bowler:
                            self._previous_bowler = self._current_bowler.get("name")
                        self._this_over = []
                except (ValueError, IndexError):
                    pass
            self.overs = new_overs
            self._innings[self.current_innings]["overs"] = self.overs

        self.run_rate = scoreboard.get("run_rate")
        self.target = scoreboard.get("target")
        self.required_rate = scoreboard.get("required_rate")

        # Update batters
        for key in ("batter_1", "batter_2"):
            batter = scoreboard.get(key)
            if batter and isinstance(batter, dict) and batter.get("name"):
                self._update_batter(batter)
                if key == "batter_1":
                    self._current_batter_1 = batter
                else:
                    self._current_batter_2 = batter

        # Update bowler
        bowler = scoreboard.get("bowler")
        if bowler and isinstance(bowler, dict) and bowler.get("name"):
            self._update_bowler(bowler)
            self._current_bowler = bowler

        # This over balls
        if scoreboard.get("this_over") and isinstance(scoreboard["this_over"], list):
            self._this_over = scoreboard["this_over"]

    def _update_batter(self, batter: dict):
        name = batter["name"]
        card = self._innings[self.current_innings]["batting_card"]
        is_new = name not in card
        if is_new:
            card[name] = {"name": name, "runs": 0, "balls": 0, "fours": 0, "sixes": 0,
                          "how_out": "not out", "order": len(card) + 1}
            if self._squads and name not in self.all_squad_names():
                log.warn(f"Batter {name} not in known squad — adding dynamically")
        entry = card[name]
        old_runs = entry["runs"]
        old_balls = entry["balls"]
        if batter.get("runs") is not None:
            entry["runs"] = int(batter["runs"])
        if batter.get("balls") is not None:
            entry["balls"] = int(batter["balls"])
        entry["is_striker"] = batter.get("is_striker", False)
        if entry["runs"] != old_runs or entry["balls"] != old_balls:
            log.info(f"Updated: {name} {old_runs}({old_balls}) → {entry['runs']}({entry['balls']})")

    def _update_bowler(self, bowler: dict):
        name = bowler["name"]
        card = self._innings[self.current_innings]["bowling_card"]
        is_new = name not in card
        if is_new:
            card[name] = {"name": name, "overs": "0", "maidens": 0, "runs": 0,
                          "wickets": 0, "order": len(card) + 1}
            prev = self._previous_bowler
            if prev and prev != name:
                log.info(f"New bowler: {name} replacing {prev}")
        entry = card[name]
        if bowler.get("overs") is not None:
            entry["overs"] = str(bowler["overs"])
        if bowler.get("runs") is not None:
            entry["runs"] = int(bowler["runs"])
        if bowler.get("wickets") is not None:
            entry["wickets"] = int(bowler["wickets"])

    def on_ball(self, ball: dict, scoreboard: dict):
        """Record a detected ball event."""
        self._balls.append(ball)

        result = ball.get("result", "dot")
        self._this_over.append(result)

        # Update partnership
        if self._current_partnership is None:
            self._current_partnership = {
                "batters": self.current_batter_names(),
                "runs": 0,
                "balls": 0,
                "start_score": self.total - ball.get("runs", 0),
            }
        self._current_partnership["runs"] += ball.get("runs", 0)
        self._current_partnership["balls"] += 1

        if ball.get("wicket"):
            log.info(f"Wicket: FOW {self.total}/{self.wickets} ({self.overs})")
            if self._current_partnership:
                self._partnerships.append(self._current_partnership)
                self._current_partnership = None
            self._innings[self.current_innings]["fow"].append({
                "wicket": self.wickets,
                "score": self.total,
                "overs": self.overs,
                "batter": "unknown",
            })

    def on_info(self, info: dict):
        """Process info display data (partnership, run rate, etc.)."""
        info_type = info.get("type")
        value = info.get("value")
        if not info_type or not value:
            return
        if info_type == "partnership" and self._current_partnership:
            try:
                self._current_partnership["display_value"] = value
            except Exception:
                pass

    def sync_batting_card(self, data: dict):
        """Sync from a broadcast batting scorecard graphic (ground truth)."""
        batters = data.get("batters", [])
        if not isinstance(batters, list):
            return
        log.info(f"Synced from broadcast batting card — {len(batters)} batters updated")
        card = self._innings[self.current_innings]["batting_card"]
        for b in batters:
            name = b.get("name")
            if not name:
                continue
            card[name] = {
                "name": name,
                "runs": b.get("runs", 0),
                "balls": b.get("balls", 0),
                "fours": b.get("fours", 0),
                "sixes": b.get("sixes", 0),
                "how_out": b.get("how_out", "not out"),
                "strike_rate": b.get("strike_rate"),
                "order": card.get(name, {}).get("order", len(card) + 1),
                "source": "broadcast",
            }

    def sync_bowling_card(self, data: dict):
        """Sync from a broadcast bowling scorecard graphic (ground truth)."""
        bowlers = data.get("bowlers", [])
        if not isinstance(bowlers, list):
            return
        card = self._innings[self.current_innings]["bowling_card"]
        for b in bowlers:
            name = b.get("name")
            if not name:
                continue
            card[name] = {
                "name": name,
                "overs": str(b.get("overs", "0")),
                "maidens": b.get("maidens", 0),
                "runs": b.get("runs", 0),
                "wickets": b.get("wickets", 0),
                "economy": b.get("economy"),
                "order": card.get(name, {}).get("order", len(card) + 1),
                "source": "broadcast",
            }

    def sync_fow(self, data: dict):
        """Sync fall of wickets from broadcast graphic."""
        fow = data.get("fall_of_wickets", data.get("fow", []))
        if isinstance(fow, list):
            self._innings[self.current_innings]["fow"] = fow

    def set_squad(self, data: dict):
        """Set squad from team lineup graphic."""
        team = data.get("team")
        players = data.get("players", [])
        if team and players:
            self._squads[team] = [
                p.get("name", p) if isinstance(p, dict) else str(p)
                for p in players
            ]

    def set_toss(self, data: dict):
        """Record toss result."""
        self._innings[self.current_innings]["toss"] = data

    def set_boundary_distances(self, data: dict):
        self._innings[self.current_innings]["boundary_distances"] = data

    def update_bowling_options(self, data: dict):
        self._innings[self.current_innings]["bowling_options"] = data

    def store_career_stats(self, data: dict):
        self._innings[self.current_innings].setdefault("career_stats", []).append(data)

    def on_player_card(self, data: dict, role: str):
        """Process a player detail card."""
        if role == "new_batter":
            name = data.get("name")
            if name:
                self._current_partnership = {
                    "batters": [name],
                    "runs": 0,
                    "balls": 0,
                    "start_score": self.total,
                }

    def apply_corrections(self, corrections: list[dict]):
        """Apply corrections from cross-validation."""
        card = self._innings[self.current_innings]
        for c in corrections:
            if c["type"] == "batter_runs":
                name = c["name"]
                if name in card["batting_card"]:
                    old = card["batting_card"][name]["runs"]
                    card["batting_card"][name]["runs"] = c["broadcast_value"]
                    log.warn(f"Broadcast card shows {name} {c['broadcast_value']} but we had {old} — correcting")
            elif c["type"] == "bowler_runs":
                name = c["name"]
                if name in card["bowling_card"]:
                    card["bowling_card"][name]["runs"] = c["broadcast_value"]

    def current_batters(self) -> list[dict]:
        result = []
        if self._current_batter_1:
            result.append(self._current_batter_1)
        if self._current_batter_2:
            result.append(self._current_batter_2)
        return result

    def current_batter_names(self) -> list[str]:
        return [b.get("name", "") for b in self.current_batters() if b.get("name")]

    def current_bowler_summary(self) -> dict | None:
        if not self._current_bowler:
            return None
        return {
            "name": self._current_bowler.get("name"),
            "figures": f"{self._current_bowler.get('wickets', 0)}-{self._current_bowler.get('runs', 0)}",
            "overs": self._current_bowler.get("overs"),
        }

    def previous_bowler(self) -> str | None:
        return self._previous_bowler

    def all_squad_names(self) -> set[str]:
        names = set()
        for players in self._squads.values():
            names.update(players)
        return names

    def known_squads(self) -> dict:
        return deepcopy(self._squads)

    def last_n_balls(self, n: int) -> list[dict]:
        return self._balls[-n:] if self._balls else []

    def wicket_fell_recently(self, seconds: float = 60) -> bool:
        return time.time() - self._last_wicket_time < seconds

    def over_changed_recently(self, seconds: float = 30) -> bool:
        return time.time() - self._last_over_change_time < seconds

    @property
    def total_balls(self) -> int:
        return len(self._balls)

    def get_current_innings(self) -> dict:
        return self._innings[self.current_innings]

    def get_full(self) -> dict:
        return {
            "current_innings": self.current_innings,
            "batting_team": self.batting_team,
            "bowling_team": self.bowling_team,
            "total": self.total,
            "wickets": self.wickets,
            "overs": self.overs,
            "run_rate": self.run_rate,
            "target": self.target,
            "required_rate": self.required_rate,
            "batters": self.current_batters(),
            "bowler": self._current_bowler,
            "this_over": self._this_over,
            "partnerships": self._partnerships,
            "current_partnership": self._current_partnership,
            "innings_1": self._innings[1],
            "innings_2": self._innings[2],
            "total_balls_detected": len(self._balls),
            "squads": self._squads,
        }

    def start_new_innings(self):
        """Transition to innings 2."""
        if self.current_innings >= 2:
            log.error("Innings 3 detected — impossible in T20")
            return
        log.info(f"Innings change: {self.batting_team} {self.total}/{self.wickets} ({self.overs}) → {self.bowling_team} batting, target {self.total + 1}")
        self.current_innings = 2
        self.total = 0
        self.wickets = 0
        self.overs = "0.0"
        self._current_batter_1 = None
        self._current_batter_2 = None
        self._current_bowler = None
        self._balls.clear()
        self._this_over.clear()
        self._partnerships.clear()
        self._current_partnership = None
        self.batting_team, self.bowling_team = self.bowling_team, self.batting_team
        self._innings[2]["batting_team"] = self.batting_team
        self._innings[2]["bowling_team"] = self.bowling_team

    def reset(self):
        self.__init__()
