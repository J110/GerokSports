from __future__ import annotations

import os
import sys
from copy import deepcopy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from eyes.commentary import BallEventDetector  # noqa: E402


class _Tracker(dict):
    def get(self, key, default=None):
        return super().get(key, default)


def _balls(overs) -> int:
    whole, ball = str(overs).split(".", 1)
    return int(whole) * 6 + int(ball[:1])


def _over_label(total_balls: int) -> str:
    return f"{total_balls // 6}.{total_balls % 6}"


def _rows(*rows):
    return {
        name: {"runs": runs, "balls": balls, "striker": striker}
        for name, runs, balls, striker in rows
    }


def _bowler(name="Saurabh Dubey", runs=1, overs="0.4"):
    return {"name": name, "runs": runs, "balls": _balls(overs), "overs": overs}


def _label(event):
    event_type = event["type"]
    if event_type.endswith("_RUNS"):
        event_type = "RUNS"
    return f"{event['over']} {event_type}"


class _KkrDcHarness:
    def __init__(self):
        self.detector = BallEventDetector()
        self.events = []
        self.score = 10
        self.wickets = 0
        self.overs = "1.0"
        self.raw_batters = _rows(
            ("Abishek Porel", 9, 5, True),
            ("KL Rahul", 1, 2, False),
        )
        self.raw_bowler = _bowler(runs=0, overs="0.0")
        self.detector.detect(self._tracker(
            score=10,
            overs="1.0",
            striker="Abishek Porel",
            batter_runs=9,
            batter_balls=5,
            bowler="Saurabh Dubey",
            bowler_runs=0,
        ))

    def _tracker(
            self,
            *,
            score,
            overs,
            striker,
            batter_runs,
            batter_balls,
            bowler,
            bowler_runs=0):
        return _Tracker({
            "score": score,
            "wickets": self.wickets,
            "overs": overs,
            "striker": striker,
            f"bat:{striker}:runs": batter_runs,
            f"bat:{striker}:balls": batter_balls,
            "current_bowler": bowler,
            f"bowl:{bowler}:runs": bowler_runs,
        })

    def legal(
            self,
            *,
            score,
            overs,
            striker="Abishek Porel",
            batter_runs=9,
            batter_balls=5,
            bowler="Saurabh Dubey",
            bowler_runs=0,
            allow_scoreless_legal=True):
        event = self.detector.detect(
            self._tracker(
                score=score,
                overs=overs,
                striker=striker,
                batter_runs=batter_runs,
                batter_balls=batter_balls,
                bowler=bowler,
                bowler_runs=bowler_runs,
            ),
            allow_scoreless_legal=allow_scoreless_legal,
        )
        self.score = score
        self.overs = overs
        if event is not None:
            self.events.append(event)
        return event

    def scoreonly_extra(self, *, score, raw_batters, raw_bowler):
        assert score == self.score + 1
        assert raw_batters == self.raw_batters
        assert raw_bowler["name"] == self.raw_bowler["name"]
        assert raw_bowler["balls"] == self.raw_bowler["balls"]
        assert raw_bowler["runs"] == self.raw_bowler["runs"] + 1
        event = {
            "type": "EXTRA",
            "extra_type": "wide",
            "runs": 1,
            "certain": True,
            "over": _over_label(_balls(self.overs) + 1),
            "bowler": raw_bowler["name"],
        }
        self.events.append(event)
        self.score = score
        self.raw_batters = deepcopy(raw_batters)
        self.raw_bowler = deepcopy(raw_bowler)
        self.detector.prev_score = score
        self.detector.prev_wickets = self.wickets
        self.detector.prev_overs = self.overs
        self.detector.prev_bowler = raw_bowler["name"]
        self.detector.prev_bowler_runs = raw_bowler["runs"]
        return event

    def stripped_batteronly_wide_dot(self, *, raw_batters, raw_bowler):
        changed = [
            name for name, row in raw_batters.items()
            if self.raw_batters.get(name) != row
        ]
        if raw_bowler is None:
            return []
        if self.score <= sum(row["runs"] for row in raw_batters.values()):
            return []
        if raw_bowler["name"] != self.raw_bowler["name"]:
            return []
        if raw_bowler["balls"] != self.raw_bowler["balls"] + 1:
            return []
        if len(changed) != 1:
            return []
        name = changed[0]
        prev = self.raw_batters[name]
        row = raw_batters[name]
        if row["runs"] != prev["runs"] or row["balls"] != prev["balls"] + 1:
            return []
        over = _over_label(_balls(self.overs) + 1)
        extra = {
            "type": "EXTRA",
            "extra_type": "wide",
            "runs": 1,
            "certain": True,
            "over": over,
            "bowler": raw_bowler["name"],
        }
        dot = {
            "type": "DOT",
            "runs": 0,
            "certain": True,
            "over": over,
            "batter": name,
            "bowler": raw_bowler["name"],
        }
        self.events.extend([extra, dot])
        self.raw_batters = deepcopy(raw_batters)
        self.raw_bowler = deepcopy(raw_bowler)
        self.detector.prev_score = self.score
        self.detector.prev_wickets = self.wickets
        self.detector.prev_overs = over
        self.detector.prev_bowler = raw_bowler["name"]
        self.detector.prev_bowler_runs = raw_bowler["runs"]
        return [extra, dot]

    def standings_no_progress(self, *, raw_batters, raw_bowler=None):
        before = deepcopy(self.raw_batters)
        emitted = self.stripped_batteronly_wide_dot(
            raw_batters=raw_batters,
            raw_bowler=raw_bowler,
        )
        if not emitted:
            self.raw_batters = before
        return emitted

    def dead_view_graphic(self, *, score, overs, camera_view):
        real_progress = score != self.score or _balls(overs) != _balls(self.overs)
        if camera_view == "other" and real_progress:
            return self.legal(score=score, overs=overs, batter_balls=7)
        return None


def _prime_at_1_4():
    h = _KkrDcHarness()
    h.legal(score=10, overs="1.1", batter_balls=6)
    h.legal(score=11, overs="1.2", batter_runs=10, batter_balls=6)
    h.legal(score=11, overs="1.3", batter_balls=7)
    h.legal(score=11, overs="1.4", batter_balls=7, bowler_runs=1)
    h.raw_batters = _rows(
        ("Abishek Porel", 9, 7, False),
        ("KL Rahul", 2, 3, False),
    )
    h.raw_bowler = _bowler(runs=1, overs="0.4")
    return h


def _add_1_5_extra(h):
    return h.scoreonly_extra(
        score=12,
        raw_batters=deepcopy(h.raw_batters),
        raw_bowler=_bowler(runs=2, overs="0.4"),
    )


def test_kkrdc_600s_track1_fixture_sequence():
    h = _prime_at_1_4()
    _add_1_5_extra(h)
    h.legal(score=12, overs="1.5", batter_balls=8, bowler_runs=2)
    h.legal(score=12, overs="2.0", batter_balls=9, bowler_runs=2)
    h.legal(
        score=13,
        overs="2.1",
        striker="KL Rahul",
        batter_runs=3,
        batter_balls=4,
        bowler="Cameron Green",
        bowler_runs=1,
    )
    h.legal(
        score=15,
        overs="2.2",
        striker="KL Rahul",
        batter_runs=5,
        batter_balls=5,
        bowler="Cameron Green",
        bowler_runs=3,
    )
    h.legal(
        score=15,
        overs="2.3",
        striker="KL Rahul",
        batter_runs=5,
        batter_balls=6,
        bowler="Cameron Green",
        bowler_runs=3,
    )
    h.legal(
        score=21,
        overs="2.4",
        striker="KL Rahul",
        batter_runs=11,
        batter_balls=7,
        bowler="Cameron Green",
        bowler_runs=9,
    )

    assert [_label(event) for event in h.events] == [
        "1.1 DOT",
        "1.2 RUNS",
        "1.3 DOT",
        "1.4 DOT",
        "1.5 EXTRA",
        "1.5 DOT",
        "2.0 DOT",
        "2.1 RUNS",
        "2.2 RUNS",
        "2.3 DOT",
        "2.4 SIX",
    ]


def test_score_plus_one_same_over_bowler_only_extra_not_1_4_runs():
    h = _prime_at_1_4()

    event = _add_1_5_extra(h)

    assert _label(event) == "1.5 EXTRA"
    assert "1.4 RUNS" not in [_label(e) for e in h.events]


def test_next_tick_after_scoreonly_extra_is_1_5_dot():
    h = _prime_at_1_4()
    _add_1_5_extra(h)

    event = h.legal(score=12, overs="1.5", batter_balls=8, bowler_runs=2)

    assert _label(event) == "1.5 DOT"


def test_over_closing_tick_1_5_to_2_0_unchanged_score_is_dot():
    h = _prime_at_1_4()
    _add_1_5_extra(h)
    h.legal(score=12, overs="1.5", batter_balls=8, bowler_runs=2)

    event = h.legal(score=12, overs="2.0", batter_balls=9, bowler_runs=2)

    assert _label(event) == "2.0 DOT"


def test_score_plus_one_2_0_to_2_1_with_batter_bowler_increment_is_runs():
    h = _prime_at_1_4()
    _add_1_5_extra(h)
    h.legal(score=12, overs="1.5", batter_balls=8, bowler_runs=2)
    h.legal(score=12, overs="2.0", batter_balls=9, bowler_runs=2)

    event = h.legal(
        score=13,
        overs="2.1",
        striker="KL Rahul",
        batter_runs=3,
        batter_balls=4,
        bowler="Cameron Green",
        bowler_runs=1,
    )

    assert _label(event) == "2.1 RUNS"


def test_standings_row_batteronly_no_progress_does_not_poison_memory():
    h = _prime_at_1_4()
    stale_rows = deepcopy(h.raw_batters)

    assert h.standings_no_progress(
        raw_batters=stale_rows,
        raw_bowler=_bowler(runs=1, overs="0.4"),
    ) == []
    h.score = 12
    h.detector.prev_score = 12
    emitted = h.stripped_batteronly_wide_dot(
        raw_batters=_rows(
            ("Abishek Porel", 9, 8, False),
            ("KL Rahul", 2, 3, False),
        ),
        raw_bowler=_bowler(runs=2, overs="0.5"),
    )

    assert [_label(event) for event in emitted] == ["1.5 EXTRA", "1.5 DOT"]


def test_dead_view_other_progress_feeds_state_but_no_progress_does_not_emit():
    h = _KkrDcHarness()

    event = h.dead_view_graphic(score=10, overs="1.1", camera_view="other")
    no_progress = h.dead_view_graphic(score=10, overs="1.1", camera_view="other")
    dead_view = h.dead_view_graphic(score=10, overs="1.2", camera_view="graphic")

    assert _label(event) == "1.1 DOT"
    assert no_progress is None
    assert dead_view is None

