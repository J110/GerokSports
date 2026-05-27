from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ScorerReplayHit:
    requested: int
    matched: int
    delta: int
    decision: dict[str, Any]
    committed_changes: list[str]


class ScorerReplay:
    def __init__(self, records: dict[int, dict[str, Any]], *,
                 tolerance: int = 2, strict: bool = True):
        self.records = records
        self.tolerance = max(0, int(tolerance))
        self.strict = bool(strict)

    @classmethod
    def from_env(cls) -> ScorerReplay | None:
        path = os.environ.get("SCORER_REPLAY_LOG")
        if not path:
            return None
        tolerance = int(os.environ.get(
            "SCORER_REPLAY_NEAREST_TOLERANCE",
            os.environ.get("SCOUT_REPLAY_NEAREST_TOLERANCE", "2")))
        strict = os.environ.get("SCORER_REPLAY_STRICT", "1") == "1"
        return cls.from_path(path, tolerance=tolerance, strict=strict)

    @classmethod
    def from_path(cls, path: str | os.PathLike[str], *,
                  tolerance: int = 2,
                  strict: bool = True) -> ScorerReplay:
        records: dict[int, dict[str, Any]] = {}
        p = Path(path)
        if not p.exists():
            return cls(records, tolerance=tolerance, strict=strict)
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                scorer = rec.get("scorer")
                if not isinstance(scorer, dict):
                    continue
                frame = rec.get("frame")
                if not isinstance(frame, int):
                    continue
                records[frame] = scorer
        return cls(records, tolerance=tolerance, strict=strict)

    def lookup(self, requested: int) -> ScorerReplayHit | None:
        if not self.records:
            return None
        matched = min(self.records, key=lambda k: (abs(k - requested), k))
        delta = abs(matched - requested)
        if delta > self.tolerance:
            return None
        scorer = self.records[matched]
        decision = self._decision_from_proposed(scorer.get("proposed"))
        committed = scorer.get("committed_changes")
        return ScorerReplayHit(
            requested=requested,
            matched=matched,
            delta=delta,
            decision=decision,
            committed_changes=list(committed)
            if isinstance(committed, list) else [],
        )

    @staticmethod
    def _decision_from_proposed(proposed: Any) -> dict[str, Any]:
        if not isinstance(proposed, dict):
            return {}
        if any(k in proposed for k in (
                "score_update", "overs_update", "wickets_update",
                "bowler_update", "team_assignment")):
            return copy.deepcopy(proposed)

        decision: dict[str, Any] = {
            "team_assignment": {
                "batting_team": None,
                "bowling_team": None,
                "innings": None,
                "target": None,
            },
            "score_update": {
                "from": None,
                "to": proposed.get("score"),
                "accepted": proposed.get("score") is not None,
            },
            "overs_update": {
                "from": None,
                "to": proposed.get("overs"),
                "accepted": proposed.get("overs") is not None,
            },
            "wickets_update": {
                "from": None,
                "to": proposed.get("wickets"),
                "accepted": proposed.get("wickets") is not None,
            },
            "batter_updates": {},
            "bowler_update": {},
            "dismissal": None,
            "ball_event": None,
            "ground_truth_applied": None,
            "rejected": {},
            "deferred": {},
            "innings_change": False,
            "vision_hint": None,
        }

        batters = proposed.get("batter_updates")
        if isinstance(batters, list):
            for row in batters:
                if not isinstance(row, dict):
                    continue
                name = row.get("name")
                if not isinstance(name, str) or not name.strip():
                    continue
                update = copy.deepcopy(row)
                update.pop("name", None)
                update.pop("_raw_name", None)
                update.setdefault("accepted", True)
                decision["batter_updates"][name] = update
        elif isinstance(batters, dict):
            decision["batter_updates"] = copy.deepcopy(batters)

        bowler = proposed.get("bowler")
        if isinstance(bowler, dict) and bowler.get("name"):
            bowler_update = copy.deepcopy(bowler)
            bowler_update.setdefault("accepted", True)
            decision["bowler_update"] = bowler_update

        return decision
