"""Unit tests for ThisOverManager pending-slot lifecycle (B1.2b).

Covers the no-MULTI_BALL architecture token-rewrite path:
- ABSORBED_LEGAL events with placeholder="?" record slot_idx in
  `_pending_slots`.
- MULTI_BALL events append N "?" placeholders (no infer_gap_tokens
  synthesis) and record each slot.
- `rewrite_token(slot_idx, token)` updates in place and pops the slot.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eyes.this_over import ThisOverManager


@pytest.fixture
def om() -> ThisOverManager:
    return ThisOverManager()


def test_absorbed_legal_records_pending_slot(om: ThisOverManager):
    om.on_ball_event(
        {"type": "ABSORBED_LEGAL", "ball_index": 0,
         "certain": False, "legal": True},
        score=0,
    )
    assert om.this_over == ["?"]
    assert om.this_over_sources == ["obs_pending"]
    assert 0 in om._pending_slots
    assert om._pending_slots[0]["source"] == "absorbed_legal"
    assert om._pending_slots[0]["ball_index"] == 0


def test_absorbed_legal_with_wicket_appends_W_not_pending(om: ThisOverManager):
    om.on_ball_event(
        {"type": "ABSORBED_LEGAL", "ball_index": 0,
         "gap_finalize_wicket": True, "certain": False, "legal": True},
        score=0,
    )
    assert om.this_over == ["W"]
    assert om._pending_slots == {}


def test_multi_ball_appends_n_placeholders_no_synthesis(om: ThisOverManager):
    om.on_ball_event(
        {"type": "MULTI_BALL", "balls_missed": 3, "total_runs": 5,
         "certain": False},
        score=0,
    )
    assert om.this_over == ["?", "?", "?"]
    assert om.this_over_sources == ["multi_ball_pending"] * 3
    assert set(om._pending_slots.keys()) == {0, 1, 2}
    for slot in om._pending_slots.values():
        assert slot["source"] == "multi_ball"


def test_multi_ball_caps_at_six_balls(om: ThisOverManager):
    # Pre-fill 4 slots so only 2 remain in the over.
    for i in range(4):
        om.this_over.append(str(i))
        om.this_over_sources.append("obs")

    om.on_ball_event(
        {"type": "MULTI_BALL", "balls_missed": 5, "total_runs": 4,
         "certain": False},
        score=0,
    )
    # 4 pre-existing + 2 placeholders capped to remaining over slots.
    assert len(om.this_over) == 6
    assert om.this_over[-2:] == ["?", "?"]
    assert set(om._pending_slots.keys()) == {4, 5}


def test_rewrite_token_updates_in_place_and_pops_slot(om: ThisOverManager):
    om.on_ball_event(
        {"type": "MULTI_BALL", "balls_missed": 2, "total_runs": 4,
         "certain": False},
        score=0,
    )
    assert om.this_over == ["?", "?"]
    assert set(om._pending_slots.keys()) == {0, 1}

    om.rewrite_token(0, "4")
    assert om.this_over == ["4", "?"]
    assert om.this_over_sources[0] == "obs"
    assert 0 not in om._pending_slots
    assert 1 in om._pending_slots

    om.rewrite_token(1, ".")
    assert om.this_over == ["4", "."]
    assert om._pending_slots == {}


def test_rewrite_token_out_of_range_is_safe_noop(om: ThisOverManager):
    om.this_over = ["?"]
    om._pending_slots = {0: {"source": "test"}}

    om.rewrite_token(99, "4")
    assert om.this_over == ["?"]
    assert om._pending_slots == {0: {"source": "test"}}
