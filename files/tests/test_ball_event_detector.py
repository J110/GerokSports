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


def _overs_to_balls(value):
    if value is None:
        return 0
    text = str(value).strip()
    if "." in text:
        whole, ball = text.split(".", 1)
        return int(whole) * 6 + int(ball[0] if ball else 0)
    return int(float(text)) * 6


def _fast_path_placeholder_evidence(
        extracted,
        detector,
        this_over_tokens,
        camera_view,
        frame_phase,
        broadcast_extra):
    if detector is None or broadcast_extra:
        return False
    if camera_view in ("ad", "graphic", "replay", "other"):
        return False
    if frame_phase in ("advertisement", "graphic", "replay"):
        return False
    if "?" not in list(this_over_tokens or []):
        return False

    score = extracted.get("score")
    wickets = extracted.get("wickets")
    overs = extracted.get("match_overs")
    if score is None or wickets is None or overs is None:
        return False
    if detector.prev_score is None or detector.prev_wickets is None:
        return False
    if int(score) != int(detector.prev_score):
        return False
    if int(wickets) != int(detector.prev_wickets):
        return False
    if _overs_to_balls(overs) - _overs_to_balls(detector.prev_overs) != 1:
        return False

    bowler = extracted.get("bowler")
    if not isinstance(bowler, dict) or not bowler.get("name"):
        return False
    if bowler.get("runs") is None or bowler.get("wickets") is None:
        return False
    if bowler.get("overs") is None:
        return False
    return _overs_to_balls(bowler["overs"]) % 6 == _overs_to_balls(overs) % 6


def _fast_path_over_closing_evidence(
        extracted,
        detector,
        this_over_tokens,
        camera_view,
        frame_phase,
        broadcast_extra):
    if detector is None or broadcast_extra:
        return False
    if camera_view in ("ad", "graphic", "replay", "other"):
        return False
    if frame_phase in ("advertisement", "graphic", "replay"):
        return False

    tokens = list(this_over_tokens or [])
    if any(str(token) == "?" for token in tokens):
        return False
    legal_count = sum(
        1 for token in tokens
        if str(token).strip().lower() not in {"wd", "wide", "nb", "no ball"})
    if legal_count != 5:
        return False

    score = extracted.get("score")
    wickets = extracted.get("wickets")
    overs = extracted.get("match_overs")
    if score is None or wickets is None or overs is None:
        return False
    batters = [
        row for row in extracted.get("batters") or []
        if isinstance(row, dict)
        and row.get("name")
        and row.get("balls") is not None
    ]
    if len(batters) < 2:
        return False
    if detector.prev_score is None or detector.prev_wickets is None:
        return False
    if int(score) != int(detector.prev_score):
        return False
    if int(wickets) != int(detector.prev_wickets):
        return False

    current_balls = _overs_to_balls(overs)
    previous_balls = _overs_to_balls(detector.prev_overs)
    if current_balls - previous_balls != 1:
        return False
    return previous_balls % 6 == 5 and current_balls % 6 == 0


def _caller_allows_scoreless_legal(
        camera_view,
        frame_phase,
        action,
        extracted,
        detector=None,
        this_over_tokens=None,
        broadcast_extra=None):
    live_legal_evidence = (
        camera_view in ("bowlers_end", "side_on")
        and frame_phase in ("release", "flight", "shot", "post_shot")
    )
    strong_live_strip_evidence = (
        has_strong_live_strip_scoreless_legal_evidence(extracted)
        and camera_view not in ("ad", "graphic", "replay", "other")
        and frame_phase not in ("advertisement", "graphic", "replay")
    )
    placeholder_evidence = _fast_path_placeholder_evidence(
        extracted,
        detector,
        this_over_tokens,
        camera_view,
        frame_phase,
        broadcast_extra,
    )
    over_closing_evidence = _fast_path_over_closing_evidence(
        extracted,
        detector,
        this_over_tokens,
        camera_view,
        frame_phase,
        broadcast_extra,
    )
    guard_override = (
        live_legal_evidence
        or strong_live_strip_evidence
        or placeholder_evidence
        or over_closing_evidence)
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


def test_post_dead_time_guard_allows_first_ball_with_fast_path_placeholder_and_bowler_strip():
    detector = BallEventDetector()
    detector.detect(_Tracker({
        "score": 10,
        "wickets": 0,
        "overs": "1.0",
        "striker": "Abishek Porel",
        "bat:Abishek Porel:balls": 3,
        "current_bowler": "Saurabh Dubey",
    }))
    detector.prev_striker = "Abishek Porel"
    detector.prev_striker_balls = 3

    extracted = {
        "score": 10,
        "wickets": 0,
        "match_overs": 1.1,
        "batters": [
            {"name": "KL Rahul", "runs": 1, "balls": 2},
        ],
        "bowler": {
            "name": "DUBE",
            "wickets": 0,
            "runs": 0,
            "overs": "0.1",
        },
    }
    allow_scoreless_legal = _caller_allows_scoreless_legal(
        "closeup",
        "between_play",
        None,
        extracted,
        detector=detector,
        this_over_tokens=["?"],
        broadcast_extra=None,
    )
    event = detector.detect(
        _Tracker({
            "score": 10,
            "wickets": 0,
            "overs": "1.1",
            "striker": "Abishek Porel",
            "bat:Abishek Porel:balls": 3,
            "current_bowler": "Saurabh Dubey",
        }),
        allow_scoreless_legal=allow_scoreless_legal,
    )

    assert allow_scoreless_legal is True
    assert event is not None
    assert event["type"] == "DOT"
    assert event["over"] == "1.1"


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
        detector=detector,
        this_over_tokens=[],
        broadcast_extra=None,
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


def test_post_dead_time_guard_allows_source_run_1_6_over_closing_ball():
    detector = BallEventDetector()
    detector.detect(_Tracker({
        "score": 12,
        "wickets": 0,
        "overs": "1.5",
        "striker": "Abishek Porel",
        "bat:Abishek Porel:balls": 8,
        "current_bowler": "Saurabh Dubey",
    }))
    detector.prev_striker = "Abishek Porel"
    detector.prev_striker_balls = 8

    extracted = {
        "score": 12,
        "wickets": 0,
        "match_overs": 2.0,
        "batters": [
            {"name": "Abishek Porel", "runs": 9, "balls": 9},
            {"name": "KL Rahul", "runs": 2, "balls": 3},
        ],
        "bowler": None,
    }
    allow_scoreless_legal = _caller_allows_scoreless_legal(
        "closeup",
        "between_play",
        "The players are taking a break between play.",
        extracted,
        detector=detector,
        this_over_tokens=[".", "1", ".", ".", "Wd", "."],
        broadcast_extra=None,
    )
    event = detector.detect(
        _Tracker({
            "score": 12,
            "wickets": 0,
            "overs": "2.0",
            "striker": "Abishek Porel",
            "bat:Abishek Porel:balls": 8,
            "current_bowler": "Saurabh Dubey",
        }),
        allow_scoreless_legal=allow_scoreless_legal,
    )

    assert allow_scoreless_legal is True
    assert event is not None
    assert event["type"] == "DOT"
    assert event["over"] == "2.0"


def test_post_dead_time_guard_does_not_use_over_closing_override_for_replay_bad_gap():
    detector = BallEventDetector()
    detector.detect(_Tracker({
        "score": 12,
        "wickets": 0,
        "overs": "1.4",
        "striker": "Abishek Porel",
        "bat:Abishek Porel:balls": 7,
        "current_bowler": "Saurabh Dubey",
    }))
    detector.prev_striker = "Abishek Porel"
    detector.prev_striker_balls = 7

    extracted = {
        "score": 12,
        "wickets": 0,
        "match_overs": 2.0,
        "batters": [
            {"name": "Abishek Porel", "runs": 9, "balls": 9},
            {"name": "KL Rahul", "runs": 2, "balls": 3},
        ],
        "bowler": None,
    }
    tokens = [".", "1", "?", "?", "Wd"]

    assert _fast_path_over_closing_evidence(
        extracted,
        detector,
        tokens,
        "closeup",
        "between_play",
        None,
    ) is False
    assert _caller_allows_scoreless_legal(
        "closeup",
        "between_play",
        "The players are taking a break between play.",
        extracted,
        detector=detector,
        this_over_tokens=tokens,
        broadcast_extra=None,
    ) is False


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
