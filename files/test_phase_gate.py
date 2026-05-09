"""Unit tests for DeliveryWindowRecorder RC-7 phase gate (Part A).

Protects the behaviour shipped on 2026-04-23 in response to the
window-selection investigation: `_find_span` must reject bowlers_end
anchor tags whose frame_phase is NOT one of release/flight/shot/runup.

Run:
    cd /Users/anmolmohan/Projects/SportsComm/files
    python test_phase_gate.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import delivery_window_recorder as dwr_mod
from delivery_window_recorder import DeliveryWindowRecorder, _ACTION_PHASES


def _fresh() -> DeliveryWindowRecorder:
    """Build a DWR with stubbed deps — _find_span needs nothing real."""
    # Tag source is injected per-test via monkey-patching the instance.
    rec = DeliveryWindowRecorder.__new__(DeliveryWindowRecorder)
    rec._clf = None
    rec._get_frames = lambda a, b: []
    rec._get_tags = lambda a, b, _v=None: []
    rec._save_root = None
    rec._pre_padding_s = dwr_mod.PRE_PADDING_S
    rec._post_padding_s = dwr_mod.POST_PADDING_S
    rec._lookback_s = dwr_mod.LOOKBACK_S
    rec._fallback_lookback_s = dwr_mod.FALLBACK_LOOKBACK_S
    rec._replay_capture_s = dwr_mod.REPLAY_CAPTURE_S
    rec._min_frames = dwr_mod.MIN_FRAMES_FOR_CLASSIFICATION
    rec._post_event_exclusion_s = dwr_mod.POST_EVENT_EXCLUSION_S
    rec._max_end_to_event_gap_s = dwr_mod.MAX_END_TO_EVENT_GAP_S
    rec._max_contiguous_gap_s = dwr_mod.MAX_CONTIGUOUS_GAP_S
    rec._min_inter_delivery_s = dwr_mod.MIN_INTER_DELIVERY_S
    rec._max_span_overlap_ratio = dwr_mod.MAX_SPAN_OVERLAP_RATIO
    rec._window_id = 0
    import collections as _c
    rec._stats = _c.Counter()
    rec._pending_replay_jobs = []
    rec._last_accepted_event_ts = 0.0
    rec._last_consumed_span = None
    return rec


def _tags(*rows: tuple[float, str, str | None]) -> list:
    """Build tag tuples matching _snapshot_tagged's shape: (ts, frame, view, phase)."""
    return [(ts, None, view, phase) for (ts, view, phase) in rows]


def _assert_eq(actual, expected, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def test_pure_action_phase_accepted():
    """Baseline: a single release-phase bowlers_end tag produces a span."""
    rec = _fresh()
    event_ts = 100.0
    # Need end_ts > start_ts: lookback ~8s, exclusion ~1.5s default.
    rec._get_tags = lambda a, b, _v=None: _tags(
        (event_ts - 3.0, "bowlers_end", "release"),
    )
    span = rec._find_span(event_ts, "bowlers_end")
    assert span is not None, "action-phase anchor should produce a span"
    _assert_eq(rec._stats["anchor_phase_reject"], 0,
               "no phase rejections expected")


def test_between_play_rejected():
    """A between_play tag must NOT seed a span (PHASE-REJECT)."""
    rec = _fresh()
    event_ts = 100.0
    rec._get_tags = lambda a, b, _v=None: _tags(
        (event_ts - 3.0, "bowlers_end", "between_play"),
    )
    span = rec._find_span(event_ts, "bowlers_end")
    assert span is None, (
        f"between_play anchor should NOT produce a span, got {span}")
    _assert_eq(rec._stats["anchor_phase_reject"], 1,
               "one phase rejection expected")
    _assert_eq(rec._stats["anchor_phase_reject_between_play"], 1,
               "between_play counter expected")


def test_post_shot_rejected():
    rec = _fresh()
    event_ts = 100.0
    rec._get_tags = lambda a, b, _v=None: _tags(
        (event_ts - 3.0, "bowlers_end", "post_shot"),
    )
    assert rec._find_span(event_ts, "bowlers_end") is None
    _assert_eq(rec._stats["anchor_phase_reject"], 1, "rejected")
    _assert_eq(rec._stats["anchor_phase_reject_post_shot"], 1, "post_shot")


def test_fielder_reaction_rejected():
    rec = _fresh()
    event_ts = 100.0
    rec._get_tags = lambda a, b, _v=None: _tags(
        (event_ts - 3.0, "bowlers_end", "fielder_reaction"),
    )
    assert rec._find_span(event_ts, "bowlers_end") is None
    _assert_eq(rec._stats["anchor_phase_reject"], 1, "rejected")


def test_none_phase_rejected():
    """Missing phase (None) should be rejected — Scout told us nothing."""
    rec = _fresh()
    event_ts = 100.0
    rec._get_tags = lambda a, b, _v=None: _tags(
        (event_ts - 3.0, "bowlers_end", None),
    )
    assert rec._find_span(event_ts, "bowlers_end") is None
    _assert_eq(rec._stats["anchor_phase_reject"], 1, "rejected")
    _assert_eq(rec._stats["anchor_phase_reject_none"], 1,
               "none-phase counter expected")


def test_rejected_tag_falls_through_to_earlier_action_phase():
    """Scenario: recent post_shot tag + older release tag.

    Historically _find_span would pin on the recent post_shot tag and
    ship a non-delivery clip.  After RC-7, the post_shot tag is skipped
    and the older release tag seeds the span.  (The fall-through is
    bounded by LOOKBACK_S and by MAX_END_TO_EVENT_GAP_S downstream.)
    """
    rec = _fresh()
    event_ts = 100.0
    rec._get_tags = lambda a, b, _v=None: _tags(
        (event_ts - 5.0, "bowlers_end", "release"),    # real delivery
        (event_ts - 3.0, "bowlers_end", "post_shot"),  # reaction shot
    )
    span = rec._find_span(event_ts, "bowlers_end")
    assert span is not None, "expected fall-through to release anchor"
    # Span should cover only the release tag, NOT the post_shot ts.
    _assert_eq(span, (event_ts - 5.0, event_ts - 5.0),
               "span should be pinned on the release tag")
    _assert_eq(rec._stats["anchor_phase_reject"], 1, "one rejection")


def test_rejected_tag_closes_open_span():
    """A release tag followed (in ts order) by a post_shot tag: span
    should end at the release tag and NOT extend into the post_shot.
    (Reversed iteration: post_shot seen first.)  Equivalent to the
    pre-RC-7 "non-target view breaks the span" semantics.
    """
    rec = _fresh()
    event_ts = 100.0
    # ts order: release at t-5, release at t-4.5, post_shot at t-4
    # Reversed walk: post_shot first → rejected, no span yet → continue.
    # Then release → start span. Then earlier release → extend span back.
    rec._get_tags = lambda a, b, _v=None: _tags(
        (event_ts - 5.0, "bowlers_end", "release"),
        (event_ts - 4.5, "bowlers_end", "release"),
        (event_ts - 4.0, "bowlers_end", "post_shot"),
    )
    span = rec._find_span(event_ts, "bowlers_end")
    assert span is not None, f"expected valid span, got {span}"
    # Span should be [t-5, t-4.5], excluding the post_shot at t-4.
    _assert_eq(span, (event_ts - 5.0, event_ts - 4.5),
               "span must not extend into post_shot tag")
    _assert_eq(rec._stats["anchor_phase_reject"], 1, "post_shot rejected")


def test_mid_span_rejection_breaks():
    """release at t-6, post_shot at t-5, release at t-4.

    Reversed walk: release(t-4) starts span → post_shot(t-5) rejected +
    closes the span → release(t-6) never reached.  Span = [t-4, t-4].
    This is the bug-safe behaviour: don't silently span across a
    non-action phase tag as if it were contiguous live action.
    """
    rec = _fresh()
    event_ts = 100.0
    rec._get_tags = lambda a, b, _v=None: _tags(
        (event_ts - 6.0, "bowlers_end", "release"),
        (event_ts - 5.0, "bowlers_end", "post_shot"),
        (event_ts - 4.0, "bowlers_end", "release"),
    )
    span = rec._find_span(event_ts, "bowlers_end")
    _assert_eq(span, (event_ts - 4.0, event_ts - 4.0),
               "span must stop at the post_shot tag")
    _assert_eq(rec._stats["anchor_phase_reject"], 1, "one rejection")


def test_all_action_phases_accepted():
    """release/flight/shot/runup must all pass the gate."""
    for phase in ("release", "flight", "shot", "runup"):
        rec = _fresh()
        event_ts = 100.0
        rec._get_tags = lambda a, b, _v=None, _p=phase: _tags(
            (event_ts - 3.0, "bowlers_end", _p),
        )
        span = rec._find_span(event_ts, "bowlers_end")
        assert span is not None, f"phase={phase} should seed a span"
        _assert_eq(rec._stats["anchor_phase_reject"], 0,
                   f"phase={phase} should not trigger PHASE-REJECT")


def test_non_target_view_not_counted_as_phase_reject():
    """A side_on tag must NOT increment the phase-reject counter —
    that's a view mismatch, a different code path.
    """
    rec = _fresh()
    event_ts = 100.0
    rec._get_tags = lambda a, b, _v=None: _tags(
        (event_ts - 3.0, "side_on", "release"),
    )
    assert rec._find_span(event_ts, "bowlers_end") is None
    _assert_eq(rec._stats["anchor_phase_reject"], 0,
               "side_on is a view miss, not a phase reject")


def test_action_phases_constant_contents():
    """Lock in the exact action-phase set so future edits are explicit."""
    _assert_eq(_ACTION_PHASES,
               frozenset({"release", "flight", "shot", "runup"}),
               "action phase set")


if __name__ == "__main__":
    tests = [
        test_action_phases_constant_contents,
        test_pure_action_phase_accepted,
        test_all_action_phases_accepted,
        test_between_play_rejected,
        test_post_shot_rejected,
        test_fielder_reaction_rejected,
        test_none_phase_rejected,
        test_rejected_tag_falls_through_to_earlier_action_phase,
        test_rejected_tag_closes_open_span,
        test_mid_span_rejection_breaks,
        test_non_target_view_not_counted_as_phase_reject,
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
