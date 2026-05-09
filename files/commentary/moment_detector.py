"""Decides WHEN each personality generates commentary."""
from __future__ import annotations


class MomentDetector:
    def __init__(self):
        self._prev_score: int = 0
        self._prev_wickets: int = 0
        self._prev_overs: str = "0"
        self._milestones_fired: set[str] = set()

    def classify(self, state: dict, ball_event: dict | None,
                 over_change: dict | None) -> list[str]:
        triggers: list[str] = []

        sc = state.get("scorecard", {})
        score = sc.get("score") or 0
        wickets = sc.get("wickets") or 0
        overs = sc.get("overs") or "0"

        if ball_event and ball_event.get("certain"):
            triggers.append("wire")
            triggers.append("storyteller")

        if over_change:
            triggers.append("analyst")

        if ball_event and ball_event.get("type") == "WICKET":
            triggers.append("analyst")

        if ball_event and ball_event.get("type") in ("DRS_WIDE", "DRS_NOT_OUT"):
            triggers.append("analyst")
            triggers.append("wire")
        if ball_event and ball_event.get("type") == "DRS_NOT_OUT":
            triggers.append("colour")

        batting_card = state.get("batting_card", [])
        if isinstance(batting_card, list):
            for b in batting_card:
                if b.get("status") != "batting":
                    continue
                name = b.get("name", "")
                runs = b.get("runs") or 0
                for milestone in [50, 100]:
                    key = f"{name}_{milestone}"
                    if runs >= milestone and key not in self._milestones_fired:
                        self._milestones_fired.add(key)
                        triggers.append("colour")
                        triggers.append("analyst")

        if ball_event and ball_event.get("type") == "WICKET":
            if isinstance(batting_card, list):
                for b in batting_card:
                    if b.get("status") == "out" and (b.get("runs") or 0) >= 30:
                        wk_key = f"wkt_{b.get('name', '')}"
                        if wk_key not in self._milestones_fired:
                            self._milestones_fired.add(wk_key)
                            triggers.append("colour")

        # Chase RRR thresholds
        match = state.get("match", {})
        if match.get("innings") == 2 and match.get("target"):
            runs_needed = int(match["target"]) - score
            overs_f = float(overs)
            balls_rem = 120 - (int(overs_f) * 6 + round((overs_f % 1) * 10))
            if balls_rem > 0:
                rrr = runs_needed / balls_rem * 6
                for threshold in [12, 15]:
                    key = f"rrr_{threshold}"
                    if rrr >= threshold and key not in self._milestones_fired:
                        self._milestones_fired.add(key)
                        triggers.append("colour")

        # Last over drama
        if float(overs) >= 19.0 and match.get("innings") == 2:
            if "last_over" not in self._milestones_fired:
                self._milestones_fired.add("last_over")
                triggers.append("colour")

        self._prev_score = score
        self._prev_wickets = wickets
        self._prev_overs = overs

        return list(set(triggers))
