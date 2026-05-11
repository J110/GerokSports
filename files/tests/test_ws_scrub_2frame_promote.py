"""Regression tests for B2: WS-SCRUB 2-frame consensus promote.

Target: test_pipeline.py:4923-4946 (the ws_scrub for/if block) and
the module-level `_ws_scrub_consec` dict at line 2662.

The production code is inline inside `build_full_payload`, so this
test mirrors the loop body in a tiny driver function and asserts the
state mutations on `_ws_scrub_consec` and `batting_card` match the
B2 fix's intent. If the production block diverges, drift is caught
by the pipeline replay (see replay_full_pipeline_validation.md), but
this gives fast pytest coverage of the dict-promotion contract.

Run from repo root:
    pytest files/tests/test_ws_scrub_2frame_promote.py -q
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest  # noqa: E402


def _ws_scrub_one_pass(state, batting_card, scrub_consec, scrub_counts):
    """Faithful mirror of test_pipeline.py:4923-4946.

    Walks the (striker, non) slots in `state`. For names whose card
    status != 'batting', increments per-name consec counter. On the
    SECOND consecutive rejection (>= 2), flips card status to
    'batting' and pops the consec key — that's the B2 promotion.
    """
    for slot in ("striker", "non"):
        nm = state.get(slot)
        if not nm:
            continue
        c = batting_card.get(nm)
        if c and c.get("status") == "batting":
            scrub_consec.pop(f"{slot}:{nm}", None)
            continue

        reason = (
            "not_in_card" if c is None
            else f"status_{c.get('status')}"
        )
        key = f"{slot}:{reason}"
        scrub_counts[key] = scrub_counts.get(key, 0) + 1
        consec_key = f"{slot}:{nm}"
        scrub_consec[consec_key] = scrub_consec.get(consec_key, 0) + 1

        if (c is not None
                and c.get("status") in ("yet_to_bat", None)
                and scrub_consec[consec_key] >= 2):
            c["status"] = "batting"
            scrub_consec.pop(consec_key, None)


def _bc_with(*names_status):
    """Build batting_card from (name, status) pairs."""
    return {n: {"status": s} for n, s in names_status}


def test_single_reject_no_promote():
    bc = _bc_with(("Vaibhav Sooryavanshi", "yet_to_bat"))
    consec, counts = {}, {}
    _ws_scrub_one_pass(
        {"striker": "Vaibhav Sooryavanshi"}, bc, consec, counts)
    assert consec == {"striker:Vaibhav Sooryavanshi": 1}
    assert bc["Vaibhav Sooryavanshi"]["status"] == "yet_to_bat"


def test_two_consecutive_promotes_and_pops_counter():
    bc = _bc_with(("Vaibhav Sooryavanshi", "yet_to_bat"))
    consec, counts = {}, {}
    state = {"striker": "Vaibhav Sooryavanshi"}
    _ws_scrub_one_pass(state, bc, consec, counts)
    _ws_scrub_one_pass(state, bc, consec, counts)
    assert "striker:Vaibhav Sooryavanshi" not in consec
    assert bc["Vaibhav Sooryavanshi"]["status"] == "batting"


def test_different_player_resets():
    bc = _bc_with(
        ("Vaibhav Sooryavanshi", "yet_to_bat"),
        ("Dhruv Jurel", "yet_to_bat"),
    )
    consec, counts = {}, {}
    _ws_scrub_one_pass(
        {"striker": "Vaibhav Sooryavanshi"}, bc, consec, counts)
    _ws_scrub_one_pass(
        {"striker": "Dhruv Jurel"}, bc, consec, counts)
    assert consec == {
        "striker:Vaibhav Sooryavanshi": 1,
        "striker:Dhruv Jurel": 1,
    }
    assert bc["Vaibhav Sooryavanshi"]["status"] == "yet_to_bat"
    assert bc["Dhruv Jurel"]["status"] == "yet_to_bat"


def test_pass_admission_resets_counter():
    bc = _bc_with(("Vaibhav Sooryavanshi", "yet_to_bat"))
    consec, counts = {}, {}
    _ws_scrub_one_pass(
        {"striker": "Vaibhav Sooryavanshi"}, bc, consec, counts)
    assert consec.get("striker:Vaibhav Sooryavanshi") == 1
    bc["Vaibhav Sooryavanshi"]["status"] = "batting"
    _ws_scrub_one_pass(
        {"striker": "Vaibhav Sooryavanshi"}, bc, consec, counts)
    assert "striker:Vaibhav Sooryavanshi" not in consec


def test_absent_from_card_no_promote():
    bc = _bc_with(("Yashasvi Jaiswal", "batting"))
    consec, counts = {}, {}
    state = {"striker": "Phantom Stale Read"}
    _ws_scrub_one_pass(state, bc, consec, counts)
    _ws_scrub_one_pass(state, bc, consec, counts)
    # Two rejections, but card has no entry to promote — counter
    # increments but no key gets a 'status' field set to batting.
    assert consec.get("striker:Phantom Stale Read") == 2
    assert "Phantom Stale Read" not in bc


def test_does_not_promote_dismissed():
    bc = _bc_with(("Tilak Varma", "out"))
    consec, counts = {}, {}
    state = {"striker": "Tilak Varma"}
    _ws_scrub_one_pass(state, bc, consec, counts)
    _ws_scrub_one_pass(state, bc, consec, counts)
    _ws_scrub_one_pass(state, bc, consec, counts)
    assert bc["Tilak Varma"]["status"] == "out"


def test_does_not_promote_did_not_bat():
    bc = _bc_with(("Reserve Player", "did_not_bat"))
    consec, counts = {}, {}
    state = {"striker": "Reserve Player"}
    _ws_scrub_one_pass(state, bc, consec, counts)
    _ws_scrub_one_pass(state, bc, consec, counts)
    assert bc["Reserve Player"]["status"] == "did_not_bat"


def test_module_dict_exists_in_test_pipeline():
    """Smoke check that the production module-level dict still exists
    at the documented name. Drift here means the inline production
    code may have moved and this test's mirror needs re-syncing."""
    import importlib
    tp = importlib.import_module("test_pipeline")
    assert hasattr(tp, "_ws_scrub_consec")
    assert isinstance(tp._ws_scrub_consec, dict)
