"""Extras source-of-truth tests.

Verifies the fix in
``files/docs/investigations/extras_source_of_truth_diagnosis.md``:

* The post-commit inference at ``test_pipeline.py:~6510`` writes to
  ``extras['inferred_total']``, not ``extras['total']``.
* ``extras['total']`` is mutated only by ``Scoreboard.record_extra``
  (and ``full_reset`` on innings boundary), making it monotonic
  within an innings.
* ``_score_inf_floor_components`` continues to operate when
  ``extras['total']`` is under-counted relative to the inferred
  value.

Run from repo root:
    pytest files/tests/test_extras_source.py -q
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


_TEST_PIPELINE_PATH = os.path.join(ROOT, "test_pipeline.py")


def _inference_block_source() -> str:
    src = open(_TEST_PIPELINE_PATH, encoding="utf-8").read()
    m = re.search(
        r"# === EXTRAS INFERENCE ===.*?# === DRS STATE MACHINE ===",
        src, re.DOTALL)
    assert m is not None, "EXTRAS INFERENCE block not found in test_pipeline.py"
    return m.group(0)


def test_extras_inference_writes_to_inferred_total_key() -> None:
    block = _inference_block_source()
    assert 'scoreboard.extras["inferred_total"]' in block, (
        "inference must write to extras['inferred_total']")
    assert re.search(r'scoreboard\.extras\["total"\]\s*=', block) is None, (
        "inference must not assign extras['total'] (only record_extra "
        "should mutate that key)")


def test_extras_total_monotonic_via_record_extra() -> None:
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])

    history = [sb.extras["total"]]
    sb.record_extra("wide", 1)
    history.append(sb.extras["total"])
    sb.record_extra("no_ball", 1)
    history.append(sb.extras["total"])
    sb.record_extra("leg_bye", 4)
    history.append(sb.extras["total"])

    assert history == sorted(history), (
        f"extras['total'] must be monotonic non-decreasing, got {history}")
    assert sb.extras["total"] == 6
    assert sb.extras["wides"] == 1
    assert sb.extras["no_balls"] == 1
    assert sb.extras["leg_byes"] == 4


def test_score_inf_floor_handles_undercounted_extras() -> None:
    from test_pipeline import _score_inf_floor_components
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb.batting_card["A"]["status"] = "batting"
    sb.batting_card["A"]["runs"] = 4
    sb.batting_card["B"]["status"] = "batting"
    sb.batting_card["B"]["runs"] = 4
    sb.extras["inferred_total"] = 7

    bat_sum, extras_total, complete = _score_inf_floor_components(sb)

    assert complete is True
    assert bat_sum == 8
    assert extras_total == 0, (
        "floor must read extras['total'] (record_extra-counted), "
        "not extras['inferred_total']")


def test_score_inf_floor_reads_record_extra_total() -> None:
    from test_pipeline import _score_inf_floor_components
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb.batting_card["A"]["status"] = "batting"
    sb.batting_card["A"]["runs"] = 4
    sb.record_extra("wide", 3)

    bat_sum, extras_total, complete = _score_inf_floor_components(sb)

    assert complete is True
    assert bat_sum == 4
    assert extras_total == 3
