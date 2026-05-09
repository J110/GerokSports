"""Reproduces the three state-loss bugs from the 2026-04-17 IPL match
(GT vs KKR, screenshot at 9.5 overs in chase) and proves the
history-preserving `_accept_initial` + immutable-FOW patch fixes them.

Bugs from screenshot:
  1. This Over showed `[., ?, ?, ?, 1]` — middle balls lost as
     placeholders despite no pipeline restart.
  2. Partnership = 1 run / 1 ball — Gill (48) and Sundar (2) were both
     well into their innings; running counter had been reset.
  3. Fall of Wickets showed two identical entries:
     `95/1 (Buttler, 9.1)` and `95/2 (Buttler, 9.1)` — same player,
     same score, same overs.  System rewrote / duplicated history.

All three traced to `_accept_initial` clobbering historical fields on
re-WARM after stale recovery.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from score_manager import FrameInput, ScoreManager


def _frame(fid: str, t: float, *, score=None, wkt=None, overs=None,
           bat1=None, bat2=None, target=181) -> FrameInput:
    return FrameInput(
        frame_id=fid, timestamp=t,
        ext_score=score, ext_wickets=wkt, ext_overs=overs,
        ext_bat1_name=bat1, ext_bat2_name=bat2,
        broadcast_target=target,
    )


# ─────────────────────────────────────────────────────────────────────
# Direct bug reproductions via _accept_initial
# ─────────────────────────────────────────────────────────────────────

def test_reentry_preserves_observed_this_over():
    """Bug 1 replay.  SM has [., 1, .] from real observations, then
    re-enters COLD_START and re-WARMs at the same overs.  All observed
    balls must survive."""
    sm = ScoreManager(shadow=False)
    sm.score, sm.wickets, sm.overs = 50, 2, 9.3
    sm.this_over = [".", "1", "."]
    sm.this_over_src = ["obs", "obs", "obs"]

    sm._accept_initial(
        {"score": 50, "wickets": 2, "overs": 9.3},
        FrameInput(frame_id="re", timestamp=0.0))

    assert sm.this_over == [".", "1", "."], (
        f"REGRESSION (bug 1): re-WARM wiped observed balls; "
        f"this_over={sm.this_over}")
    assert sm.this_over_src == ["obs", "obs", "obs"], sm.this_over_src


def test_reentry_pads_this_over_for_advanced_overs():
    """Re-WARM at a later overs reading must pad missing slots with
    placeholders, never truncate or wipe observations."""
    sm = ScoreManager(shadow=False)
    sm.score, sm.wickets, sm.overs = 50, 2, 9.1
    sm.this_over = ["."]
    sm.this_over_src = ["obs"]

    sm._accept_initial(
        {"score": 51, "wickets": 2, "overs": 9.5},
        FrameInput(frame_id="re", timestamp=0.0))

    assert len(sm.this_over) == 5, (
        f"expected 5 slots, got {sm.this_over}")
    assert sm.this_over[0] == ".", (
        f"observed dot at ball 1 lost: {sm.this_over}")
    assert sm.this_over[1:] == ["?"] * 4
    assert sm.this_over_src == ["obs", "bcast", "bcast", "bcast", "bcast"]


def test_reentry_preserves_partnership():
    """Bug 2 replay.  Partnership of 47/30 must survive a re-WARM."""
    sm = ScoreManager(shadow=False)
    sm.score, sm.wickets, sm.overs = 50, 2, 9.3
    sm.partnership_runs = 47
    sm.partnership_balls = 30

    sm._accept_initial(
        {"score": 50, "wickets": 2, "overs": 9.3},
        FrameInput(frame_id="re", timestamp=0.0))

    assert sm.partnership_runs == 47, (
        f"REGRESSION (bug 2): partnership_runs reset to "
        f"{sm.partnership_runs} on re-WARM")
    assert sm.partnership_balls == 30, sm.partnership_balls


def test_reentry_preserves_confirmed_fow_history():
    """Bug 3 replay (foundation).  FOW history must be immutable across
    re-WARM.  Buttler@95/9.1 must NOT be replaced by a placeholder."""
    sm = ScoreManager(shadow=False)
    sm.score, sm.wickets, sm.overs = 95, 1, 9.3
    sm.fow_list = [{
        "score": 95, "overs": 9.1,
        "dismissed": "Buttler", "bowler": "Chakaravarthy",
        "wicket_type": "stumped",
    }]

    sm._accept_initial(
        {"score": 95, "wickets": 1, "overs": 9.3},
        FrameInput(frame_id="re", timestamp=0.0))

    assert len(sm.fow_list) == 1, sm.fow_list
    assert sm.fow_list[0]["dismissed"] == "Buttler", (
        f"REGRESSION (bug 3): confirmed FOW entry overwritten with "
        f"placeholder: {sm.fow_list[0]}")
    assert sm.fow_list[0]["score"] == 95


def test_reentry_pads_fow_when_more_wickets_fell():
    """Re-entry sees wickets=2 but we only have 1 confirmed entry —
    pad with one placeholder, never overwrite the confirmed."""
    sm = ScoreManager(shadow=False)
    sm.score, sm.wickets, sm.overs = 95, 1, 9.3
    sm.fow_list = [{"score": 95, "overs": 9.1, "dismissed": "Buttler"}]

    sm._accept_initial(
        {"score": 100, "wickets": 2, "overs": 9.5},
        FrameInput(frame_id="re", timestamp=0.0))

    assert len(sm.fow_list) == 2
    assert sm.fow_list[0]["dismissed"] == "Buttler"
    assert sm.fow_list[1] == {"score": "?", "overs": "?"}


def test_reentry_never_shrinks_fow_history():
    """Defensive: even if scoreboard misreads wickets DOWN, never drop
    a confirmed FOW entry."""
    sm = ScoreManager(shadow=False)
    sm.score, sm.wickets, sm.overs = 95, 2, 9.3
    sm.fow_list = [
        {"score": 90, "overs": 8.5, "dismissed": "Buttler"},
        {"score": 95, "overs": 9.1, "dismissed": "Rahane"},
    ]

    sm._accept_initial(
        {"score": 95, "wickets": 1, "overs": 9.3},
        FrameInput(frame_id="re", timestamp=0.0))

    assert len(sm.fow_list) == 2, (
        f"REGRESSION: FOW list shrank to {sm.fow_list}")


# ─────────────────────────────────────────────────────────────────────
# WICKET event handler — placeholder upgrade + immutability
# ─────────────────────────────────────────────────────────────────────

def test_wicket_event_upgrades_placeholder_slot():
    """When a WICKET fires and slot N-1 is a placeholder, upgrade it
    in place rather than appending a new (duplicate) entry."""
    sm = ScoreManager(shadow=False)
    # Drive to WARM at 50/0 (10.0).
    for i in range(3):
        sm.on_frame(_frame(f"f{i}", float(i),
                           score=50, wkt=0, overs=10.0,
                           bat1="Gill", bat2="Buttler"))
    assert sm.mode == "WARM"

    # Inject a placeholder FOW entry as if re-WARM had padded for a
    # wicket we'd missed.
    sm.fow_list = [{"score": "?", "overs": "?"}]
    sm.wickets = 1
    sm.bat2_name = "Buttler"  # restore in case _accept_update changed it

    # Now a real wicket fires (wickets 1 → 2 with Buttler dismissed).
    sm.on_frame(_frame("wkt", 4.0,
                       score=50, wkt=2, overs=10.1,
                       bat1="Gill", bat2="Sundar"))

    assert len(sm.fow_list) == 2, (
        f"expected 2 entries, got {len(sm.fow_list)}: {sm.fow_list}")
    # Slot 0 (placeholder) is untouched — we don't know who got out.
    assert sm.fow_list[0]["score"] == "?"
    # Slot 1 (the new wicket) carries the real data.
    assert sm.fow_list[1]["dismissed"] == "Buttler", sm.fow_list[1]


def test_wicket_event_refuses_to_overwrite_confirmed_entry():
    """If the slot for this wicket is already a confirmed entry,
    refuse the rewrite — confirmed FOW is immutable."""
    sm = ScoreManager(shadow=False)
    for i in range(3):
        sm.on_frame(_frame(f"f{i}", float(i),
                           score=50, wkt=1, overs=10.0,
                           bat1="Gill", bat2="Sundar"))
    assert sm.mode == "WARM"

    # Pre-existing confirmed FOW entry for wicket 1.
    sm.fow_list = [{
        "score": 50, "overs": 10.0,
        "dismissed": "Buttler", "bowler": "Chakaravarthy",
        "wicket_type": "caught",
    }]
    sm.wickets = 1

    # Now re-process a "wicket 1" event (e.g. a glitch where the
    # current dismissed = Sundar somehow gets routed to slot 0).
    # Must NOT overwrite Buttler.
    fake_event = {
        "type": "WICKET", "runs": 0, "dismissed": "Sundar",
        "bowler": "Chakaravarthy", "wicket_type": "bowled",
    }
    prev = sm._snapshot()
    sm._apply_event(fake_event, prev,
                    {"score": 50, "wickets": 1, "overs": 10.0},
                    FrameInput(frame_id="x", timestamp=5.0))

    assert sm.fow_list[0]["dismissed"] == "Buttler", (
        f"REGRESSION: confirmed FOW W1 was overwritten: {sm.fow_list[0]}")


# ─────────────────────────────────────────────────────────────────────
# End-to-end: reproduce the exact screenshot scenario
# ─────────────────────────────────────────────────────────────────────

def test_screenshot_scenario_no_phantom_buttler_duplicate():
    """Full reproduction:
      - Real Buttler wicket at 95/1 (9.1) — wkt 1.
      - Sundar comes in.
      - Brief stale-recovery re-WARM mid-innings (e.g. an ad break
        that triggered the overs-regression path at the resume frame).
      - Real second wicket at 95/2 (9.2) — Sundar this time.
      - Confirmed FOW must be: [Buttler@95/9.1, Sundar@95/9.2].
        NOT [{?,?}, Buttler@95/9.1] and NOT
        [Buttler@95/9.1, Buttler@95/9.1].
    """
    sm = ScoreManager(shadow=False)
    sm.target = 181
    sm.innings = 2

    # Warm at 95/0 (9.0) with Gill / Buttler at the crease.
    for i in range(3):
        sm.on_frame(_frame(f"f{i}", float(i),
                           score=95, wkt=0, overs=9.0,
                           bat1="Gill", bat2="Buttler"))
    assert sm.mode == "WARM"

    # Buttler dismissed at 95/1 (9.1) — single-ball wicket, no runs.
    sm.on_frame(_frame("wkt1", 5.0,
                       score=95, wkt=1, overs=9.1,
                       bat1="Gill", bat2="Sundar"))
    assert sm.wickets == 1
    assert len(sm.fow_list) == 1, sm.fow_list
    assert sm.fow_list[0]["dismissed"] == "Buttler", sm.fow_list

    # Simulate a stale-recovery re-init: pretend SM re-entered
    # COLD_START, then re-WARMs via _accept_initial at the same state.
    sm._accept_initial(
        {"score": 95, "wickets": 1, "overs": 9.1,
         "bat1_name": "Gill", "bat2_name": "Sundar"},
        FrameInput(frame_id="rewarm", timestamp=6.0))
    assert sm.fow_list[0]["dismissed"] == "Buttler", (
        f"REGRESSION: re-WARM clobbered Buttler entry: {sm.fow_list}")

    # Second real wicket: Sundar dismissed at 95/2 (9.2).
    sm.on_frame(_frame("wkt2", 7.0,
                       score=95, wkt=2, overs=9.2,
                       bat1="Gill", bat2="Tewatia"))
    assert sm.wickets == 2
    assert len(sm.fow_list) == 2, sm.fow_list
    # Slot 0 still carries Buttler — IMMUTABLE.
    assert sm.fow_list[0]["dismissed"] == "Buttler", sm.fow_list[0]
    # Slot 1 carries the new dismissal.  Sundar departed in this diff.
    assert sm.fow_list[1]["dismissed"] == "Sundar", sm.fow_list[1]


if __name__ == "__main__":
    g = globals()
    tests = [(name, fn) for name, fn in g.items()
             if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}\n        {e}")
        except Exception as e:
            failed += 1
            print(f"  ERR   {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed"
          + (f", {failed} failed" if failed else ""))
    sys.exit(1 if failed else 0)
