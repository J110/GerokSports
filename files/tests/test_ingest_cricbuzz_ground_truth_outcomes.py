from files.scripts.ingest_cricbuzz_ground_truth import _classify_outcome


def test_bye_textual_one_run() -> None:
    parsed = _classify_outcome("bye")
    assert parsed["legal_ball"] is True
    assert parsed["total_runs"] == 1
    assert parsed["bye"] == 1


def test_leg_bye_numeric_one_run() -> None:
    parsed = _classify_outcome("1 leg bye")
    assert parsed["legal_ball"] is True
    assert parsed["total_runs"] == 1
    assert parsed["leg_bye"] == 1


def test_plural_wides_are_illegal_multi_run_extras() -> None:
    parsed = _classify_outcome("2 wides")
    assert parsed["legal_ball"] is False
    assert parsed["wide"] is True
    assert parsed["total_runs"] == 2


def test_run_out_with_completed_run() -> None:
    parsed = _classify_outcome("out Rovman Powell Run Out!! 1 run completed.")
    assert parsed["legal_ball"] is True
    assert parsed["wicket"] is True
    assert parsed["runs_off_bat"] == 1
    assert parsed["total_runs"] == 1


def test_run_out_is_not_bowler_wicket() -> None:
    parsed = _classify_outcome("out Rovman Powell Run Out!! 1 run completed.")
    assert parsed["bowler_wicket"] is False


def test_caught_is_bowler_wicket() -> None:
    parsed = _classify_outcome("out Caught by Axar Patel!!")
    assert parsed["wicket"] is True
    assert parsed["bowler_wicket"] is True
