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


def _names_match(a, b):
    ta = [t for t in str(a or "").upper().split() if t]
    tb = [t for t in str(b or "").upper().split() if t]
    if ta == tb:
        return True
    if not ta or not tb:
        return False
    small, large = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return large[-len(small):] == small


class _KkrDcHarness:
    def __init__(self):
        self.detector = BallEventDetector()
        self.events = []
        self.held_transition = None
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

    def scoreonly_extra_from_progression_memory(
            self,
            *,
            score,
            raw_batters,
            raw_bowler,
            progression_bowler):
        assert score == self.score + 1
        assert raw_batters == self.raw_batters
        assert _names_match(raw_bowler["name"], progression_bowler["name"])
        assert raw_bowler["balls"] == progression_bowler["balls"]
        assert raw_bowler["runs"] == progression_bowler["runs"] + 1
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

    def graphic_score_progress_with_corrob(
            self,
            *,
            score,
            overs,
            raw_batters=None,
            raw_bowler=None,
            this_over_token=None):
        score_delta = score - self.score
        balls_delta = _balls(overs) - _balls(self.overs)
        if not (score_delta > 0 and balls_delta == 1):
            return self.legal(score=score, overs=overs)
        if this_over_token:
            return self.legal(score=score, overs=overs)
        if raw_batters and set(raw_batters) == set(self.raw_batters):
            changed = [
                (name, row, self.raw_batters[name])
                for name, row in raw_batters.items()
                if row != self.raw_batters[name]
            ]
            if len(changed) == 1:
                _name, row, prev = changed[0]
                if (
                        row["balls"] == prev["balls"] + 1
                        and row["runs"] == prev["runs"] + score_delta):
                    return self.legal(score=score, overs=overs)
        if (
                raw_bowler
                and raw_bowler["name"] == self.raw_bowler["name"]
                and raw_bowler["balls"] == self.raw_bowler["balls"] + 1
                and raw_bowler["runs"] == self.raw_bowler["runs"] + score_delta):
            return self.legal(score=score, overs=overs)
        self.held_transition = {
            "score_before": self.score,
            "score_after": score,
            "overs_before": self.overs,
            "overs_after": overs,
        }
        return None

    def later_graphic_after_held_transition(self, *, score, overs):
        if self.held_transition and _balls(overs) > _balls(
                self.held_transition["overs_after"]):
            held = self.held_transition
            held_runs = held["score_after"] - held["score_before"]
            if held_runs > 0 and score == held["score_after"]:
                held_event = {
                    "type": f"{held_runs}_RUNS",
                    "runs": held_runs,
                    "certain": True,
                    "over": held["overs_after"],
                }
                dot_event = {
                    "type": "DOT",
                    "runs": 0,
                    "certain": True,
                    "over": overs,
                }
                self.events.extend([held_event, dot_event])
                self.score = score
                self.overs = overs
                self.detector.prev_score = self.score
                self.detector.prev_wickets = self.wickets
                self.detector.prev_overs = self.overs
                self.held_transition = None
                return [held_event, dot_event]
            if held_runs > 0 and score > held["score_after"]:
                held_event = {
                    "type": f"{held_runs}_RUNS",
                    "runs": held_runs,
                    "certain": True,
                    "over": held["overs_after"],
                }
                self.events.append(held_event)
                self.score = held["score_after"]
                self.overs = held["overs_after"]
                self.detector.prev_score = self.score
                self.detector.prev_wickets = self.wickets
                self.detector.prev_overs = self.overs
                self.held_transition = None
                current_event = self.graphic_score_progress_with_corrob(
                    score=score,
                    overs=overs,
                    raw_batters=None,
                    raw_bowler=None,
                    this_over_token="1",
                )
                return [held_event, current_event]
            self.score = held["score_after"]
            self.overs = held["overs_after"]
            self.detector.prev_score = self.score
            self.detector.prev_wickets = self.wickets
            self.detector.prev_overs = self.overs
            self.held_transition = None
        return self.graphic_score_progress_with_corrob(
            score=score,
            overs=overs,
            raw_batters={},
            raw_bowler=None,
        )


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


def test_scoreonly_extra_uses_standings_row_bowler_progression_memory():
    h = _prime_at_1_4()
    h.raw_bowler = _bowler(runs=0, overs="0.3")
    progression_bowler = _bowler(runs=1, overs="0.4")

    event = h.scoreonly_extra_from_progression_memory(
        score=12,
        raw_batters=deepcopy(h.raw_batters),
        raw_bowler=_bowler(runs=2, overs="0.4"),
        progression_bowler=progression_bowler,
    )

    assert _label(event) == "1.5 EXTRA"
    assert "1.4 RUNS" not in [_label(e) for e in h.events]


def test_scoreonly_extra_matches_suffix_bowler_name_from_progression_memory():
    h = _prime_at_1_4()
    h.raw_bowler = _bowler("S DUBEY", runs=1, overs="0.4")
    progression_bowler = _bowler("S DUBEY", runs=1, overs="0.4")

    event = h.scoreonly_extra_from_progression_memory(
        score=12,
        raw_batters=deepcopy(h.raw_batters),
        raw_bowler=_bowler("DUBEY", runs=2, overs="0.4"),
        progression_bowler=progression_bowler,
    )

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


def test_graphic_score_progress_missing_batter_bowler_corrob_holds_2_3_runs():
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
        score=14,
        overs="2.2",
        striker="KL Rahul",
        batter_runs=4,
        batter_balls=5,
        bowler="Cameron Green",
        bowler_runs=2,
    )
    h.raw_batters = _rows(
        ("Abishek Porel", 9, 8, False),
        ("KL Rahul", 4, 5, True),
    )
    h.raw_bowler = _bowler("Cameron Green", runs=2, overs="0.2")

    event = h.graphic_score_progress_with_corrob(
        score=16,
        overs="2.3",
        raw_batters={},
        raw_bowler=None,
    )

    assert event is None
    assert "2.3 RUNS" not in [_label(event) for event in h.events]


def test_held_graphic_run_does_not_become_absorbed_gap_on_later_frame():
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

    held = h.graphic_score_progress_with_corrob(
        score=14,
        overs="2.2",
        raw_batters={},
        raw_bowler=None,
    )
    later = h.later_graphic_after_held_transition(score=14, overs="2.3")

    assert held is None
    assert [_label(event) for event in later] == ["2.2 RUNS", "2.3 DOT"]
    assert all(event["type"] != "ABSORBED_LEGAL" for event in h.events)
    assert "2.2 ABSORBED_LEGAL" not in [_label(event) for event in h.events]
    assert "2.3 ABSORBED_LEGAL" not in [_label(event) for event in h.events]


def test_held_graphic_run_resolves_before_later_scoring_frame():
    h = _prime_at_1_4()
    _add_1_5_extra(h)
    h.legal(score=12, overs="1.5", batter_balls=8, bowler_runs=2)
    h.legal(score=12, overs="2.0", batter_balls=9, bowler_runs=2)

    held = h.graphic_score_progress_with_corrob(
        score=13,
        overs="2.1",
        raw_batters={},
        raw_bowler=None,
    )
    later = h.later_graphic_after_held_transition(score=14, overs="2.2")

    assert held is None
    assert [_label(event) for event in later] == ["2.1 RUNS", "2.2 RUNS"]
    assert all(event["type"] != "ABSORBED_LEGAL" for event in h.events)


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

