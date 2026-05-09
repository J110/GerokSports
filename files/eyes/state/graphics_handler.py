"""Processes full-screen broadcast graphics detected by the LLM."""
from __future__ import annotations

from eyes.cricket_logger import CricketLogger

log = CricketLogger("GFX")


class GraphicsHandler:
    """Routes broadcast graphics (scorecards, lineups, etc.) to the scorecard.

    When the broadcast shows a full batting/bowling scorecard, team lineup,
    boundary map, etc., the LLM extracts it and this handler syncs it to
    our state as ground truth.
    """

    def process(self, extraction: dict, scorecard) -> dict | None:
        """Process a graphics extraction, update scorecard, return event."""
        graphics = extraction.get("graphics", {})
        if not isinstance(graphics, dict):
            return None

        gtype = graphics.get("type")
        data = graphics.get("data")

        if not gtype or gtype == "null":
            return None
        if not data:
            log.error(f"Graphics data is null despite frame_type={extraction.get('frame_type')}")
            return None

        if gtype == "batting_scorecard":
            batters = data.get("batters", [])
            extras = data.get("extras", {})
            total = data.get("total", "?")
            log.info(f"Detected: batting_scorecard — {len(batters)} batters, extras {extras.get('total', '?')}, total {total}")
            scorecard.sync_batting_card(data)
            return {"type": "batting_card", "data": data}

        elif gtype == "bowling_scorecard":
            bowlers = data.get("bowlers", [])
            log.info(f"Detected: bowling_scorecard — {len(bowlers)} bowlers")
            scorecard.sync_bowling_card(data)
            return {"type": "bowling_card", "data": data}

        elif gtype == "team_lineup":
            team = data.get("team", "?")
            players = data.get("players", [])
            log.info(f"Detected: team_lineup — {team} {len(players)} players")
            scorecard.set_squad(data)
            return {"type": "squad", "data": data}

        elif gtype == "bowling_options":
            log.info(f"Detected: bowling_options")
            scorecard.update_bowling_options(data)
            return {"type": "bowling_options", "data": data}

        elif gtype == "player_comparison":
            log.info(f"Detected: player_comparison")
            scorecard.store_career_stats(data)
            return {"type": "career_stats", "data": data}

        elif gtype == "boundary_map":
            log.info(f"Detected: boundary_map")
            scorecard.set_boundary_distances(data)
            return {"type": "boundary_map", "data": data}

        elif gtype == "fall_of_wickets":
            log.info(f"Detected: fall_of_wickets")
            scorecard.sync_fow(data)
            return {"type": "fow", "data": data}

        elif gtype == "toss_result":
            log.info(f"Detected: toss_result — {data}")
            scorecard.set_toss(data)
            return {"type": "toss", "data": data}

        elif gtype == "countdown":
            log.info(f"Detected: countdown — {data}")
            return {"type": "countdown", "value": data}

        elif gtype in ("bowler_overlay", "batter_overlay"):
            role = self._assign_role(data, scorecard)
            name = data.get("name", "?")
            log.info(f"Player card {name} → assigned as {role.upper()} ({'over just changed' if role == 'new_bowler' else 'wicket fell' if role == 'new_batter' else 'no wicket/over change'})")
            scorecard.on_player_card(data, role)
            return {"type": "player_card", "data": data, "role": role}

        log.info(f"Detected: {gtype}")
        return {"type": gtype, "data": data}

    def _assign_role(self, data: dict, scorecard) -> str:
        """Context-aware role assignment for player cards.

        Wicket just fell → new batter. Over changed → new bowler.
        """
        name = data.get("name", "")
        if not name:
            return "featured"

        if scorecard.wicket_fell_recently(60):
            if name not in scorecard.current_batter_names():
                return "new_batter"

        if scorecard.over_changed_recently(30):
            if name != scorecard.previous_bowler():
                return "new_bowler"

        if name not in scorecard.all_squad_names():
            log.warn(f"Player card {name} → NON_PLAYER (not in either squad)")
            return "non_player"

        return "featured"
