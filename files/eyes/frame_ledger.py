"""Frame Fate Ledger — tracks every frame's outcome through SM.

See files/docs/investigations/sm_as_orchestrator_design.md §4.

Stage 2c first commit: in-memory singleton ledger keyed by frame_id.
Records sm_outcome at every commit-success or guard-rejection site.

Dispatch-side wiring (Vision.describe → PENDING/TIMEOUT/RESPONDED) is
deferred to a follow-up commit. The MVP here surfaces SM-level fates
which is where the refresh-audit gap (REJECTED_SCORE_CONSENSUS +
REJECTED_TEAM_CHANGE_PENDING) lives — invisible without this ledger.

Hook pattern (additive; no behavior change):

    from eyes.frame_ledger import (
        get_ledger, SmOutcome, ScoutResponseClass, ExtractorOutcome,
    )
    get_ledger().record_sm_outcome(frame_id, SmOutcome.ACCEPTED_COMMIT,
                                   payload={...})
"""
from __future__ import annotations

import enum
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional


class ScoutStatus(str, enum.Enum):
    PENDING = "PENDING"
    RESPONDED = "RESPONDED"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"
    CORRUPT = "CORRUPT"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"


class ScoutResponseClass(str, enum.Enum):
    SCOREBOARD = "SCOREBOARD"
    GRAPHIC = "GRAPHIC"
    REPLAY = "REPLAY"
    OTHER = "OTHER"
    DEGENERATE_NULL = "DEGENERATE_NULL"


class ExtractorOutcome(str, enum.Enum):
    PARSED = "PARSED"
    NULL_OVERS = "NULL_OVERS"
    NULL_SCORE = "NULL_SCORE"
    NULL_BOTH = "NULL_BOTH"
    REJECTED = "REJECTED"


class SmOutcome(str, enum.Enum):
    NOT_YET_SEEN = "NOT_YET_SEEN"
    ACCEPTED_COMMIT = "ACCEPTED_COMMIT"
    ACCEPTED_NOOP = "ACCEPTED_NOOP"
    ACCEPTED_NOOP_NULL_OVERS = "ACCEPTED_NOOP_NULL_OVERS"
    REJECTED_COLD_EXIT = "REJECTED_COLD_EXIT"
    REJECTED_WARM_CONSENSUS = "REJECTED_WARM_CONSENSUS"
    REJECTED_SB_JUMP_LIMIT = "REJECTED_SB_JUMP_LIMIT"
    REJECTED_DISMISSED_GUARD = "REJECTED_DISMISSED_GUARD"
    REJECTED_STRIP_ROW_MISMATCH = "REJECTED_STRIP_ROW_MISMATCH"
    REJECTED_SCORE_CONSENSUS = "REJECTED_SCORE_CONSENSUS"
    REJECTED_TEAM_CHANGE_PENDING = "REJECTED_TEAM_CHANGE_PENDING"


@dataclass
class FrameLedgerEntry:
    frame_id: int
    dispatched_at: float = field(default_factory=time.time)
    scout_status: ScoutStatus = ScoutStatus.PENDING
    scout_response_class: Optional[ScoutResponseClass] = None
    extractor_outcome: Optional[ExtractorOutcome] = None
    sm_outcome: SmOutcome = SmOutcome.NOT_YET_SEEN
    rejection_payload: Optional[dict] = None
    resolved_at: Optional[float] = None


class FrameLedger:
    def __init__(self, capacity: int = 5000):
        self._entries: OrderedDict[int, FrameLedgerEntry] = OrderedDict()
        self._capacity = capacity

    def _entry(self, frame_id: int) -> FrameLedgerEntry:
        if frame_id not in self._entries:
            self._entries[frame_id] = FrameLedgerEntry(frame_id=frame_id)
            if len(self._entries) > self._capacity:
                self._entries.popitem(last=False)
        return self._entries[frame_id]

    def record_dispatch(self, frame_id: int) -> None:
        e = self._entry(frame_id)
        e.scout_status = ScoutStatus.PENDING
        e.dispatched_at = time.time()

    def record_scout_response(
        self, frame_id: int,
        response_class: ScoutResponseClass,
        status: ScoutStatus = ScoutStatus.RESPONDED,
    ) -> None:
        e = self._entry(frame_id)
        e.scout_status = status
        e.scout_response_class = response_class
        e.resolved_at = time.time()

    def record_extractor_outcome(
        self, frame_id: int, outcome: ExtractorOutcome,
    ) -> None:
        self._entry(frame_id).extractor_outcome = outcome

    def record_sm_outcome(
        self, frame_id: int, outcome: SmOutcome,
        payload: Optional[dict] = None,
    ) -> None:
        e = self._entry(frame_id)
        e.sm_outcome = outcome
        if payload is not None:
            e.rejection_payload = payload

    def all_entries(self) -> list[FrameLedgerEntry]:
        return list(self._entries.values())

    def get(self, frame_id: int) -> Optional[FrameLedgerEntry]:
        return self._entries.get(frame_id)

    def clear(self) -> None:
        self._entries.clear()


_ledger: Optional[FrameLedger] = None


def get_ledger() -> FrameLedger:
    global _ledger
    if _ledger is None:
        _ledger = FrameLedger()
    return _ledger


def reset_ledger() -> None:
    global _ledger
    _ledger = None


def _coerce_frame_id(frame) -> Optional[int]:
    if frame is None:
        return None
    try:
        return int(frame)
    except (TypeError, ValueError):
        try:
            return int(getattr(frame, "frame_id", None))
        except (TypeError, ValueError):
            return None
