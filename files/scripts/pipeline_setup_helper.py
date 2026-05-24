"""Clean-extractable pipeline setup primitives.

Extracted from `test_pipeline.py` main loop (pre-refactor sites:
:7163 `over_mgr`, :7171 on_fow_upgrade wire, :7174 `ball_detector`,
:7175 `partnership_tracker`, :7362 `score_mgr.scoreboard`, :7366
`over_mgr.attach_score_manager`) so the same instantiation + wiring
can be reused by the snapshotter at WS-N N1.2 (closes the SM-only
measurement gap documented in
`files/docs/investigations/workstream_n_snapshotter_full_pipeline_integration.md`).

Closure-tangled state — `reset_for_innings`, `_on_bowler_lock` /
`_on_striker_lock`, monitoring counters, `_pending_bcast_striker_key`
— intentionally remains in `test_pipeline.py` main loop and is
mirrored separately inside the snapshotter loop at N1.2 (per memo
§16-§17 component classification).
"""
from __future__ import annotations

from typing import NamedTuple

from eyes.commentary import BallEventDetector, PartnershipTracker
from eyes.scoreboard import Scoreboard
from eyes.this_over import ThisOverManager
from score_manager import ScoreManager


class PipelineComponents(NamedTuple):
    over_mgr: ThisOverManager
    ball_detector: BallEventDetector
    partnership_tracker: PartnershipTracker


def build_pipeline_components(
        score_mgr: ScoreManager,
        scoreboard: Scoreboard) -> PipelineComponents:
    """Instantiate over_mgr + ball_detector + partnership_tracker and
    wire the score_mgr <-> over_mgr <-> scoreboard back-references.

    - `scoreboard.on_fow_upgrade` -> `over_mgr.reorder_wicket_to_ball`
      (Fix 3: keeps W token at correct legal-ball position when
      `_add_fow` upgrades placeholder W{n} entries).
    - `score_mgr.scoreboard` -> scoreboard (Issue 1: canonicalises raw
      Scout names against the squad inside `_build_scorecard`).
    - `over_mgr.attach_score_manager(score_mgr)` (B1.2c: slot-binding
      back-ref so `ABSORBED_LEGAL` handlers can call
      `sm.bind_pending_slot`).
    """
    over_mgr = ThisOverManager()
    scoreboard.on_fow_upgrade = over_mgr.reorder_wicket_to_ball
    ball_detector = BallEventDetector()
    partnership_tracker = PartnershipTracker()
    score_mgr.scoreboard = scoreboard
    over_mgr.attach_score_manager(score_mgr)
    return PipelineComponents(
        over_mgr=over_mgr,
        ball_detector=ball_detector,
        partnership_tracker=partnership_tracker,
    )
