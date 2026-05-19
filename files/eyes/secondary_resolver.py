"""Secondary text-LLM resolver for SM-orchestrator multi-ball gaps.

See files/docs/investigations/sm_as_orchestrator_design.md §4.

Stage 2b first commit: interface + mock implementation only. The
mock reads canned responses from a JSONL fixture file specified by
the TEST_SECONDARY_LLM_REPLAY env var, keyed by
(frame_id, expected_ball.legal_ball_count). On miss or no fixture
configured, returns UNRESOLVED with confidence 0.0. Δballs<2
requests are rejected as preconditions, never reach lookup.

The real Anthropic Haiku call goes in a later commit behind a
feature flag; this module gives SM a callable surface to wire
against without committing to live infrastructure yet.
"""
from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExpectedBallContext:
    over: int
    ball: int
    legal_ball_count: int


@dataclass
class ScoutContext:
    visible_text: Optional[str] = None
    info_panel: Optional[str] = None
    strip: Optional[str] = None
    frame_type: Optional[str] = None
    camera_view: Optional[str] = None
    frame_phase: Optional[str] = None


@dataclass
class MatchState:
    innings: Optional[int] = None
    score_before: Optional[int] = None
    wickets_before: Optional[int] = None
    overs_before: Optional[float] = None
    score_after: Optional[int] = None
    wickets_after: Optional[int] = None
    overs_after: Optional[float] = None
    striker: Optional[str] = None
    non_striker: Optional[str] = None
    bowler: Optional[str] = None


@dataclass
class DeltaObserved:
    runs: int = 0
    wickets: int = 0
    balls: int = 0


@dataclass
class SecondaryResolveRequest:
    frame_id: int
    expected_ball: ExpectedBallContext
    scout_context: ScoutContext
    match_state: MatchState
    delta_observed: DeltaObserved


@dataclass
class WicketInfo:
    dismissed: Optional[str] = None
    type: Optional[str] = None
    fielder: Optional[str] = None


@dataclass
class ExtrasInfo:
    type: Optional[str] = None
    runs: int = 0


@dataclass
class SecondaryResolveResponse:
    event_type: str
    runs_off_bat: int = 0
    extras: ExtrasInfo = field(default_factory=ExtrasInfo)
    wicket: Optional[WicketInfo] = None
    confidence: float = 0.0
    rationale: str = ""
    source: str = "mock"


class SecondaryResolver:
    def __init__(self, replay_path: Optional[str] = None):
        self._cache: dict[tuple[int, int], dict] = {}
        if replay_path is None:
            replay_path = os.environ.get("TEST_SECONDARY_LLM_REPLAY")
        if replay_path:
            self._load_replay(pathlib.Path(replay_path))

    def _load_replay(self, path: pathlib.Path) -> None:
        if not path.exists():
            return
        with path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    fid = int(rec["frame_id"])
                    lbc = int(rec["legal_ball_count"])
                    self._cache[(fid, lbc)] = rec.get("response", {})
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue

    def resolve(
        self, req: SecondaryResolveRequest
    ) -> SecondaryResolveResponse:
        if req.delta_observed.balls < 2:
            return SecondaryResolveResponse(
                event_type="UNRESOLVED",
                confidence=0.0,
                rationale=(
                    "precondition: Δballs<2 is not a gap event"),
                source="precondition",
            )
        key = (req.frame_id, req.expected_ball.legal_ball_count)
        canned = self._cache.get(key)
        if canned is None:
            return SecondaryResolveResponse(
                event_type="UNRESOLVED",
                confidence=0.0,
                rationale=(
                    "no replay entry; stage 2b mock returns unresolved"),
                source="mock",
            )
        wkt = canned.get("wicket")
        extras = canned.get("extras") or {}
        return SecondaryResolveResponse(
            event_type=canned.get("event_type", "UNRESOLVED"),
            runs_off_bat=int(canned.get("runs_off_bat", 0)),
            extras=ExtrasInfo(
                type=extras.get("type"),
                runs=int(extras.get("runs", 0)),
            ),
            wicket=(WicketInfo(
                dismissed=wkt.get("dismissed"),
                type=wkt.get("type"),
                fielder=wkt.get("fielder"),
            ) if wkt else None),
            confidence=float(canned.get("confidence", 0.0)),
            rationale=canned.get("rationale", ""),
            source="replay",
        )


_singleton: Optional[SecondaryResolver] = None


def get_resolver() -> SecondaryResolver:
    global _singleton
    if _singleton is None:
        _singleton = SecondaryResolver()
    return _singleton


def reset_resolver() -> None:
    global _singleton
    _singleton = None
