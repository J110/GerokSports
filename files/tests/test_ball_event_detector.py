from __future__ import annotations

import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from eyes.commentary import (  # noqa: E402
    BallEventDetector,
    has_strong_live_strip_scoreless_legal_evidence,
    should_block_scoreless_legal_tick,
)


class _Tracker(dict):
    def get(self, key, default=None):
        return super().get(key, default)


def _caller_allows_scoreless_legal(camera_view, frame_phase, action, extracted):
    live_legal_evidence = (
        camera_view in ("bowlers_end", "side_on")
        and frame_phase in ("release", "flight", "shot", "post_shot")
    )
    strong_live_strip_evidence = (
        has_strong_live_strip_scoreless_legal_evidence(extracted)
        and camera_view not in ("ad", "graphic", "replay", "other")
        and frame_phase not in ("advertisement", "graphic", "replay")
    )
    guard_override = live_legal_evidence or strong_live_strip_evidence
    block = (
        should_block_scoreless_legal_tick(
            camera_view,
            frame_phase,
            action,
            post_dead_time_guard_active=True)
        and not guard_override)
    return not block and guard_override


def test_stale_broadcast_wide_on_legal_tick_does_not_decompose():
    detector = BallEventDetector()
    detector.detect(_Tracker({
        "score": 12,
        "wickets": 0,
        "overs": "1.5",
        "current_bowler": "Saurabh Dubey",
    }))

    detector.set_broadcast_extra("WD")
    event = detector.detect(_Tracker({
        "score": 12,
        "wickets": 0,
        "overs": "2.0",
        "current_bowler": "Saurabh Dubey",
    }))

    assert event is not None
    assert event["type"] == "DOT"
    assert event["over"] == "2.0"
    assert detector._event_queue == []


def test_post_dead_time_scoreless_legal_tick_without_batter_evidence_suppressed():
    detector = BallEventDetector()
    detector.detect(_Tracker({
        "score": 12,
        "wickets": 0,
        "overs": "2.0",
        "striker": "KL Rahul",
        "bat:KL Rahul:balls": 4,
        "current_bowler": "Saurabh Dubey",
    }))
    detector.prev_striker = "KL Rahul"
    detector.prev_striker_balls = 4

    event = detector.detect(
        _Tracker({
            "score": 12,
            "wickets": 0,
            "overs": "2.1",
            "striker": "KL Rahul",
            "bat:KL Rahul:balls": 4,
            "current_bowler": "Saurabh Dubey",
        }),
        allow_scoreless_legal=False,
    )

    assert event is None


def test_post_dead_time_scoreless_legal_tick_with_batter_evidence_allowed():
    detector = BallEventDetector()
    detector.detect(_Tracker({
        "score": 12,
        "wickets": 0,
        "overs": "2.0",
        "striker": "KL Rahul",
        "bat:KL Rahul:balls": 4,
        "current_bowler": "Saurabh Dubey",
    }))
    detector.prev_striker = "KL Rahul"
    detector.prev_striker_balls = 4

    event = detector.detect(
        _Tracker({
            "score": 12,
            "wickets": 0,
            "overs": "2.1",
            "striker": "KL Rahul",
            "bat:KL Rahul:balls": 5,
            "current_bowler": "Saurabh Dubey",
        }),
        allow_scoreless_legal=False,
    )

    assert event is not None
    assert event["type"] == "DOT"
    assert event["over"] == "2.1"


def test_post_dead_time_guard_allows_scoreless_tick_with_live_bowler_strip_evidence():
    detector = BallEventDetector()
    detector.detect(_Tracker({
        "score": 11,
        "wickets": 0,
        "overs": "1.2",
        "striker": "Abishek Porel",
        "bat:Abishek Porel:balls": 5,
        "current_bowler": "Saurabh Dubey",
    }))
    detector.prev_striker = "Abishek Porel"
    detector.prev_striker_balls = 5

    extracted = {
        "score": 11,
        "wickets": 0,
        "match_overs": 1.3,
        "batters": [
            {"name": "Abishek Porel", "runs": 9, "balls": 6},
            {"name": "KL Rahul", "runs": 2, "balls": 3},
        ],
        "bowler": {
            "name": "DUBEY",
            "wickets": 0,
            "runs": 1,
            "overs": "0.3",
        },
    }
    allow_scoreless_legal = _caller_allows_scoreless_legal(
        "closeup",
        "between_play",
        "A player in a red uniform is walking on the field.",
        extracted,
    )
    event = detector.detect(
        _Tracker({
            "score": 11,
            "wickets": 0,
            "overs": "1.3",
            "striker": "Abishek Porel",
            "bat:Abishek Porel:balls": 5,
            "current_bowler": "Saurabh Dubey",
        }),
        allow_scoreless_legal=allow_scoreless_legal,
    )

    assert allow_scoreless_legal is True
    assert event is not None
    assert event["type"] == "DOT"
    assert event["over"] == "1.3"


def test_post_ad_guard_blocks_first_scoreless_tick_without_live_bowler_strip():
    detector = BallEventDetector()
    detector.detect(_Tracker({
        "score": 12,
        "wickets": 0,
        "overs": "2.0",
        "striker": "KL Rahul",
        "bat:KL Rahul:balls": 4,
        "current_bowler": "Saurabh Dubey",
    }))
    detector.prev_striker = "KL Rahul"
    detector.prev_striker_balls = 4

    extracted = {
        "score": 12,
        "wickets": 0,
        "match_overs": 2.1,
        "batters": [
            {"name": "KL Rahul", "runs": 7, "balls": 4},
            {"name": "Abishek Porel", "runs": 5, "balls": 8},
        ],
        "bowler": None,
    }
    allow_scoreless_legal = _caller_allows_scoreless_legal(
        "closeup",
        "between_play",
        "A player in a red uniform is walking on the field.",
        extracted,
    )
    event = detector.detect(
        _Tracker({
            "score": 12,
            "wickets": 0,
            "overs": "2.1",
            "striker": "KL Rahul",
            "bat:KL Rahul:balls": 4,
            "current_bowler": "Saurabh Dubey",
        }),
        allow_scoreless_legal=allow_scoreless_legal,
    )

    assert allow_scoreless_legal is False
    assert event is None


def test_post_dead_time_break_text_blocks_scoreless_legal_without_batter_evidence():
    detector = BallEventDetector()
    detector.detect(_Tracker({
        "score": 12,
        "wickets": 0,
        "overs": "2.0",
        "striker": "Abishek Porel",
        "bat:Abishek Porel:balls": 8,
        "current_bowler": "Cameron Green",
    }))
    detector.prev_striker = "Abishek Porel"
    detector.prev_striker_balls = 8

    block = should_block_scoreless_legal_tick(
        "bowlers_end",
        "between_play",
        "The players are taking a break between play.",
        post_dead_time_guard_active=True,
    )
    event = detector.detect(
        _Tracker({
            "score": 12,
            "wickets": 0,
            "overs": "2.1",
            "striker": "Abishek Porel",
            "bat:Abishek Porel:balls": 8,
            "current_bowler": "Cameron Green",
        }),
        allow_scoreless_legal=not block,
    )

    assert block is True
    assert event is None


def test_normal_between_play_scoreless_legal_tick_allowed():
    detector = BallEventDetector()
    detector.detect(_Tracker({
        "score": 11,
        "wickets": 0,
        "overs": "1.2",
        "striker": "Abishek Porel",
        "bat:Abishek Porel:balls": 5,
        "current_bowler": "Saurabh Dubey",
    }))
    detector.prev_striker = "Abishek Porel"
    detector.prev_striker_balls = 5

    block = should_block_scoreless_legal_tick(
        "bowlers_end",
        "between_play",
        "The camera shows two players during a break in play.",
        post_dead_time_guard_active=False,
    )
    event = detector.detect(
        _Tracker({
            "score": 11,
            "wickets": 0,
            "overs": "1.3",
            "striker": "Abishek Porel",
            "bat:Abishek Porel:balls": 5,
            "current_bowler": "Saurabh Dubey",
        }),
        allow_scoreless_legal=not block,
    )

    assert block is False
    assert event is not None
    assert event["type"] == "DOT"
    assert event["over"] == "1.3"
