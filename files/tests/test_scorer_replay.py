from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scorer_replay import ScorerReplay  # noqa: E402


def _write_trace(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


def test_scorer_replay_loads_trace_and_converts_proposed_shape(tmp_path):
    trace = tmp_path / "trace.jsonl"
    _write_trace(trace, [
        {"_schema_version": 1},
        {
            "frame": 10,
            "scorer": {
                "proposed": {
                    "score": 12,
                    "wickets": 0,
                    "overs": 1.5,
                    "batter_updates": [
                        {
                            "name": "KL Rahul",
                            "runs": 7,
                            "balls": 3,
                            "_raw_name": "RAHUL",
                        }
                    ],
                    "bowler": {
                        "name": "Saurabh Dubey",
                        "runs": 12,
                        "overs": "1.5",
                        "wickets": 0,
                    },
                },
                "committed_changes": ["score->12"],
            },
        },
    ])

    replay = ScorerReplay.from_path(trace, tolerance=2, strict=True)
    hit = replay.lookup(10)

    assert hit is not None
    assert hit.matched == 10
    assert hit.delta == 0
    assert hit.committed_changes == ["score->12"]
    assert hit.decision["score_update"] == {
        "from": None,
        "to": 12,
        "accepted": True,
    }
    assert hit.decision["overs_update"]["to"] == 1.5
    assert hit.decision["batter_updates"]["KL Rahul"]["runs"] == 7
    assert "_raw_name" not in hit.decision["batter_updates"]["KL Rahul"]
    assert hit.decision["bowler_update"]["name"] == "Saurabh Dubey"


def test_scorer_replay_uses_nearest_frame_with_tolerance(tmp_path):
    trace = tmp_path / "trace.jsonl"
    _write_trace(trace, [
        {
            "frame": 20,
            "scorer": {
                "proposed": {"score": 13},
                "committed_changes": [],
            },
        },
    ])

    replay = ScorerReplay.from_path(trace, tolerance=2, strict=True)
    hit = replay.lookup(22)

    assert hit is not None
    assert hit.requested == 22
    assert hit.matched == 20
    assert hit.delta == 2
    assert hit.decision["score_update"]["to"] == 13


def test_scorer_replay_miss_outside_tolerance_returns_none(tmp_path):
    trace = tmp_path / "trace.jsonl"
    _write_trace(trace, [
        {
            "frame": 20,
            "scorer": {
                "proposed": {"score": 13},
                "committed_changes": [],
            },
        },
    ])

    replay = ScorerReplay.from_path(trace, tolerance=1, strict=True)

    assert replay.lookup(22) is None
