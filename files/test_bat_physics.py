"""Unit tests for ConsistentReadTracker batter-runs physics bound (Fix #1).

Protects the behaviour shipped on 2026-04-24 in response to the
RCB-vs-GT F24 row-swap investigation: any batter-runs proposal whose
upward delta exceeds BATTER_SINGLE_BALL_RUN_MAX + BATTER_NO_BALL_ADDITIONAL
(= 6 + 1 = 7) must be routed through the 3/4-frame consensus paths
rather than fast-confirmed.

Run:
    cd /Users/anmolmohan/Projects/SportsComm/files
    python test_bat_physics.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from eyes.consistent_tracker import ConsistentReadTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_eq(got, expected, msg: str = "") -> None:
    assert got == expected, f"{msg}: got={got!r} expected={expected!r}"


def _seed_batter(tracker: ConsistentReadTracker, name: str,
                 runs: int, balls: int, start_frame: int = 0) -> int:
    """Push `runs`/`balls` through INITIAL_CONSENSUS_FRAMES identical
    readings so they're promoted to `confirmed`. Returns the next
    free frame_count the caller should use."""
    runs_field = f"bat:{name}:runs"
    balls_field = f"bat:{name}:balls"
    f = start_frame
    for _ in range(ConsistentReadTracker.INITIAL_CONSENSUS_FRAMES):
        tracker.update(runs_field, runs, frame_count=f)
        tracker.update(balls_field, balls, frame_count=f)
        f += 1
    # Sanity: both fields must be confirmed now.
    assert tracker.confirmed.get(runs_field) == runs, (
        f"seed failed: {runs_field} confirmed="
        f"{tracker.confirmed.get(runs_field)!r}, expected {runs}")
    assert tracker.confirmed.get(balls_field) == balls, (
        f"seed failed: {balls_field} confirmed="
        f"{tracker.confirmed.get(balls_field)!r}, expected {balls}")
    return f


# ---------------------------------------------------------------------------
# Constant / API surface
# ---------------------------------------------------------------------------

def test_constants_locked_in():
    """The physics bounds are class-level constants so future edits are
    explicit. Lock them to the values derived from cricket rules."""
    _assert_eq(ConsistentReadTracker.BATTER_SINGLE_BALL_RUN_MAX, 6,
               "SIX is the max single-ball credit to a batter")
    _assert_eq(ConsistentReadTracker.BATTER_NO_BALL_ADDITIONAL, 1,
               "NB adds one run of slack for the strip-lag edge case")


# ---------------------------------------------------------------------------
# F24 replay — the canonical case the fix was written for
# ---------------------------------------------------------------------------

def test_f24_row_swap_single_frame_rejected():
    """RCB-vs-GT F24: Gill 2(3) → strip misread reports 16(13) on ONE
    frame only. Must not commit — the misread is a Scout row-swap,
    not a legal +14 scoring event."""
    t = ConsistentReadTracker()
    runs_field = "bat:Shubman Gill:runs"
    next_f = _seed_batter(t, "Shubman Gill", runs=2, balls=3)

    # F24: the scramble.
    out = t.update(runs_field, 16, frame_count=next_f)
    _assert_eq(out, 2, "single-frame +14 must be rejected (returns current)")
    _assert_eq(t.confirmed[runs_field], 2,
               "confirmed state must not change on single-frame scramble")


def test_f24_scramble_then_correction_converges():
    """F25+: Scout returns to the correct read (Gill 2(3)) on the next
    frame. The pending/reject-streak state must clear cleanly so that
    subsequent legitimate +1/+2 increments fast-confirm."""
    t = ConsistentReadTracker()
    runs_field = "bat:Shubman Gill:runs"
    next_f = _seed_batter(t, "Shubman Gill", runs=2, balls=3)

    # Scramble frame.
    t.update(runs_field, 16, frame_count=next_f)
    _assert_eq(t.confirmed[runs_field], 2, "scramble rejected")

    # Correction frame — Scout reads 2 again.
    t.update(runs_field, 2, frame_count=next_f + 1)
    # reject_streak and pending should be cleared by the value==current
    # + not-suspicious branches; nothing changes on confirmed side.
    _assert_eq(t.confirmed[runs_field], 2, "correction is a no-op commit")
    assert runs_field not in t.pending, (
        f"pending should have cleared after correction, "
        f"got pending={t.pending.get(runs_field)!r}")

    # And a legal +1 (single) should fast-confirm on the NEXT read
    # — the natural-increment path at L138.
    out = t.update(runs_field, 3, frame_count=next_f + 2)
    _assert_eq(out, 3, "legal +1 single fast-confirms after scramble clears")
    _assert_eq(t.confirmed[runs_field], 3, "runs promoted to 3")


# ---------------------------------------------------------------------------
# Legal scoring must still pass
# ---------------------------------------------------------------------------

def test_legal_single_fast_confirms():
    """+1 is a natural cricket increment — must fast-confirm."""
    t = ConsistentReadTracker()
    field = "bat:Virat Kohli:runs"
    next_f = _seed_batter(t, "Virat Kohli", runs=10, balls=7)
    out = t.update(field, 11, frame_count=next_f)
    _assert_eq(out, 11, "+1 must fast-confirm")
    _assert_eq(t.confirmed[field], 11, "confirmed updated")


def test_legal_four_fast_confirms():
    t = ConsistentReadTracker()
    field = "bat:Virat Kohli:runs"
    next_f = _seed_batter(t, "Virat Kohli", runs=10, balls=7)
    out = t.update(field, 14, frame_count=next_f)
    _assert_eq(out, 14, "+4 must fast-confirm")


def test_legal_six_fast_confirms():
    """+6 (SIX) is the largest legal single-ball delta — sits exactly
    at the fast-confirm upper bound of _is_natural_batter_increment."""
    t = ConsistentReadTracker()
    field = "bat:Suryakumar Yadav:runs"
    next_f = _seed_batter(t, "Suryakumar Yadav", runs=14, balls=8)
    out = t.update(field, 20, frame_count=next_f)
    _assert_eq(out, 20, "+6 SIX must fast-confirm")


# ---------------------------------------------------------------------------
# Physics violations — must route through consensus, not fast-commit
# ---------------------------------------------------------------------------

def test_plus_eight_routed_to_consensus():
    """+8 is one run above the cap — must be rejected by the physics
    guard and require multi-frame consensus before committing."""
    t = ConsistentReadTracker()
    field = "bat:X:runs"
    next_f = _seed_batter(t, "X", runs=10, balls=5)
    out = t.update(field, 18, frame_count=next_f)
    _assert_eq(out, 10, "single-frame +8 must not commit")
    _assert_eq(t.confirmed[field], 10, "confirmed stays at 10")


def test_plus_fourteen_single_frame_rejected():
    """Direct mirror of F24 sans the Gill-specific framing — any +14
    on a single frame is physically impossible and must be rejected."""
    t = ConsistentReadTracker()
    field = "bat:X:runs"
    next_f = _seed_batter(t, "X", runs=2, balls=3)
    out = t.update(field, 16, frame_count=next_f)
    _assert_eq(out, 2, "single-frame +14 rejected")


def test_plus_eight_persistent_four_frames_promotes_via_consensus():
    """If Scout reports the same supposedly-impossible value on FOUR
    consecutive frames, the CONSENSUS path (L198-263) should override
    and accept — this is the safety valve for cases where the tracker
    has drifted stale and the extractor is actually correct."""
    t = ConsistentReadTracker()
    field = "bat:X:runs"
    next_f = _seed_batter(t, "X", runs=10, balls=5)
    # Need CONSENSUS_THRESHOLD (=4) consistent rejected reads.
    for i in range(ConsistentReadTracker.CONSENSUS_THRESHOLD):
        t.update(field, 18, frame_count=next_f + i)
    _assert_eq(t.confirmed[field], 18,
               "persistent read must eventually promote via consensus")


# ---------------------------------------------------------------------------
# Same-frame multi-caller scenario (architectural-note check)
# ---------------------------------------------------------------------------

def test_same_frame_two_callers_does_not_fast_confirm():
    """Two callers submitting the same scramble value on the same
    frame must NOT collude into an immediate commit via the
    pending-match fast-path. This was the architectural hazard
    surfaced during the F24 investigation; Fix #1 closes it by
    making the value suspicious at the _is_suspicious gate.
    """
    t = ConsistentReadTracker()
    field = "bat:Shubman Gill:runs"
    next_f = _seed_batter(t, "Shubman Gill", runs=2, balls=3)

    # Caller 1 on frame next_f.
    r1 = t.update(field, 16, frame_count=next_f)
    # Caller 2 on the SAME frame.
    r2 = t.update(field, 16, frame_count=next_f)

    _assert_eq(r1, 2, "caller 1 must not commit")
    _assert_eq(r2, 2, "caller 2 must not commit (no fast-confirm collusion)")
    _assert_eq(t.confirmed[field], 2, "confirmed unchanged after 2 callers")


# ---------------------------------------------------------------------------
# Downward / regression is handled by a different guard — verify Fix #1
# didn't accidentally affect it
# ---------------------------------------------------------------------------

def test_regression_rejected_by_monotonic_guard():
    """Batter runs can never decrease within an innings. The physics
    cap addresses the UPWARD direction only; downward must still be
    caught by the existing monotonic guard at L439."""
    t = ConsistentReadTracker()
    field = "bat:X:runs"
    next_f = _seed_batter(t, "X", runs=30, balls=20)
    out = t.update(field, 25, frame_count=next_f)
    _assert_eq(out, 30, "regression rejected")
    _assert_eq(t.confirmed[field], 30, "confirmed stays at 30")


# ---------------------------------------------------------------------------
# Cold start — the physics cap applies to DELTAS; cold-start has no
# old value, so it should be untouched by this fix.
# ---------------------------------------------------------------------------

def test_cold_start_unaffected_by_physics_cap():
    """First reading for a batter goes through INITIAL_CONSENSUS, not
    _is_suspicious. A reading of 50 on first contact must converge
    via 3-frame cold-start consensus as before."""
    t = ConsistentReadTracker()
    field = "bat:NewBatter:runs"
    # Three consecutive reads of 50 — cold-start consensus.
    for i in range(ConsistentReadTracker.INITIAL_CONSENSUS_FRAMES):
        t.update(field, 50, frame_count=i)
    _assert_eq(t.confirmed.get(field), 50,
               "cold-start consensus must promote regardless of magnitude")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_constants_locked_in,
        test_f24_row_swap_single_frame_rejected,
        test_f24_scramble_then_correction_converges,
        test_legal_single_fast_confirms,
        test_legal_four_fast_confirms,
        test_legal_six_fast_confirms,
        test_plus_eight_routed_to_consensus,
        test_plus_fourteen_single_frame_rejected,
        test_plus_eight_persistent_four_frames_promotes_via_consensus,
        test_same_frame_two_callers_does_not_fast_confirm,
        test_regression_rejected_by_monotonic_guard,
        test_cold_start_unaffected_by_physics_cap,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"[PASS] {t.__name__}")
            passed += 1
        except AssertionError as exc:
            print(f"[FAIL] {t.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"[ERR ] {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{passed}/{len(tests)} tests passed")
    sys.exit(0 if passed == len(tests) else 1)
