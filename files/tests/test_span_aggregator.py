"""Unit tests + replay validation for SpanAggregator (design memo §9).

Run:
    cd /Users/anmolmohan/Projects/SportsComm/files
    python3 tests/test_span_aggregator.py

Sections:
  1. State-machine unit tests (in-memory, deterministic).
  2. Score-event matcher tests (n=0 / n=1 / n>=2).
  3. Replay validation against scout_responses_open.jsonl — feeds the
     247 frozen-corpus open-prose descriptions through classify_full +
     SpanAggregator and asserts ≥13/15 clips behave correctly per the
     §11.7 binary v2 baseline (positive: at least one action span;
     negative: no spurious action span).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

THIS = Path(__file__).resolve().parent
ROOT = THIS.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "scout_validation_research"))

from eyes.open_scout_classify import classify_full
from eyes.span_aggregator import (
    MIN_ACTION_SPAN_S,
    SOFT_GAP_TOLERANCE_S,
    SPAN_RETENTION_S,
    Span,
    SpanAggregator,
)


# ── 1. State-machine unit tests ────────────────────────────────────

def _spans_of(agg: SpanAggregator, force_close_ts: float | None = None
              ) -> list[Span]:
    """Commit any open span, but skip prune (tests use synthetic
    timestamps so the 90 s retention would wipe everything)."""
    del force_close_ts
    agg.force_close(now=None)
    return agg.snapshot()


def test_continuous_span() -> None:
    agg = SpanAggregator()
    for i in range(5):
        agg.add_classification(100.0 + i, "action")
    spans = _spans_of(agg, force_close_ts=200.0)
    assert len(spans) == 1, spans
    s = spans[0]
    assert s.frame_class == "action"
    assert s.frame_count == 5
    assert s.start_ts == 100.0
    assert s.end_ts == 104.0
    print("ok test_continuous_span")


def test_class_transitions() -> None:
    agg = SpanAggregator()
    # action × 3, then other × 3, then action × 3 — should yield three
    # spans (gap tolerance=1 absorbs only single dissenting frames).
    seq = [
        (1.0, "action"), (2.0, "action"), (3.0, "action"),
        (4.0, "other"), (5.0, "other"), (6.0, "other"),
        (7.0, "action"), (8.0, "action"), (9.0, "action"),
    ]
    for ts, cls in seq:
        agg.add_classification(ts, cls)
    spans = _spans_of(agg, force_close_ts=20.0)
    assert len(spans) == 3, spans
    assert [s.frame_class for s in spans] == ["action", "other", "action"]
    print("ok test_class_transitions")


def test_gap_tolerance_absorbs_single_dissent() -> None:
    agg = SpanAggregator()
    # action, action, [other], action, action — single dissenting
    # frame is absorbed; result is one action span with frame_count=4.
    for ts, cls in [(1.0, "action"), (2.0, "action"),
                    (3.0, "other"),
                    (4.0, "action"), (5.0, "action")]:
        agg.add_classification(ts, cls)
    spans = _spans_of(agg, force_close_ts=10.0)
    assert len(spans) == 1, spans
    assert spans[0].frame_class == "action"
    assert spans[0].frame_count == 4
    print("ok test_gap_tolerance_absorbs_single_dissent")


def test_two_dissents_force_close() -> None:
    agg = SpanAggregator()
    for ts, cls in [(1.0, "action"), (2.0, "action"),
                    (3.0, "other"), (4.0, "other"),
                    (5.0, "other")]:
        agg.add_classification(ts, cls)
    spans = _spans_of(agg, force_close_ts=10.0)
    assert len(spans) == 2, spans
    assert spans[0].frame_class == "action"
    assert spans[1].frame_class == "other"
    print("ok test_two_dissents_force_close")


def test_min_span_filter_drops_singleton() -> None:
    agg = SpanAggregator()
    # Single isolated action followed by sustained other.  The lone
    # action must be dropped via the 2-dissents force-close (not via
    # the 2.5s soft gap, so we keep timestamps tight).
    for ts, cls in [(1.0, "action"),
                    (2.0, "other"), (3.0, "other"),
                    (4.0, "other"), (5.0, "other")]:
        agg.add_classification(ts, cls)
    spans = _spans_of(agg, force_close_ts=10.0)
    classes = [s.frame_class for s in spans]
    assert "action" not in classes, classes
    assert agg.stats()["singletons_dropped"] >= 1
    print("ok test_min_span_filter_drops_singleton")


def test_soft_gap_force_close() -> None:
    agg = SpanAggregator()
    agg.add_classification(1.0, "action")
    agg.add_classification(2.0, "action")
    # Gap > SOFT_GAP_TOLERANCE_S (default 2.5s) — even a same-class
    # follow-up should NOT extend the span; instead the prior span is
    # committed and a new one opens.
    agg.add_classification(2.0 + SOFT_GAP_TOLERANCE_S + 1.0, "action")
    agg.add_classification(2.0 + SOFT_GAP_TOLERANCE_S + 2.0, "action")
    spans = _spans_of(agg, force_close_ts=20.0)
    assert len(spans) == 2, spans
    assert all(s.frame_class == "action" for s in spans)
    print("ok test_soft_gap_force_close")


def test_retention_pruning() -> None:
    agg = SpanAggregator()
    for ts in (1.0, 2.0, 3.0):
        agg.add_classification(ts, "action")
    # First add_classification at far future will trigger prune.
    far = 3.0 + SPAN_RETENTION_S + 5.0
    agg.add_classification(far, "other")
    agg.add_classification(far + 1.0, "other")
    agg.force_close(now=None)
    spans = agg.snapshot()
    # The original action span (end_ts=3.0) must have been pruned
    # because cutoff = (far − 90s) > 3.0.
    assert all(s.frame_class != "action" for s in spans), spans
    print("ok test_retention_pruning")


# ── 2. Score-event matcher tests ────────────────────────────────────

def _action_span_at(agg: SpanAggregator, t0: float, dur: float = 4.0,
                    cls: str = "action") -> None:
    """Inject ``dur+1`` obs at 1 fps cadence so the resulting span
    has duration ≥ MIN_ACTION_SPAN_S regardless of MIN_SPAN_FRAMES."""
    n = max(2, int(dur) + 1)
    for i in range(n):
        agg.add_classification(t0 + i, cls)
    agg.force_close(now=None)


def test_match_no_candidates() -> None:
    agg = SpanAggregator()
    verdict, bounds = agg.match_span_to_event(event_ts=1000.0)
    assert verdict == "no_match"
    assert bounds is None
    print("ok test_match_no_candidates")


def test_match_short_action_filtered() -> None:
    agg = SpanAggregator()
    # 2 obs at 0.5 s spacing → duration 0.5 s, below MIN_ACTION_SPAN_S.
    agg.add_classification(990.0, "action")
    agg.add_classification(990.5, "action")
    agg.force_close(now=None)
    verdict, bounds = agg.match_span_to_event(event_ts=1000.0)
    assert verdict == "no_match", (verdict, bounds, MIN_ACTION_SPAN_S)
    print("ok test_match_short_action_filtered")


def test_match_single_candidate() -> None:
    agg = SpanAggregator()
    _action_span_at(agg, t0=990.0, dur=4.0)
    verdict, bounds = agg.match_span_to_event(event_ts=1000.0)
    assert verdict == "open_scout_span", (verdict, bounds)
    assert bounds is not None
    assert bounds[0] == 990.0
    assert bounds[1] == 994.0
    print("ok test_match_single_candidate")


def test_match_stale_span_rejected() -> None:
    agg = SpanAggregator()
    # Span ends 12 s before event → > MAX_END_TO_EVENT_GAP_S (8).
    _action_span_at(agg, t0=983.0, dur=4.0)
    verdict, bounds = agg.match_span_to_event(event_ts=1000.0)
    assert verdict == "no_match", (verdict, bounds)
    print("ok test_match_stale_span_rejected")


def test_match_multi_defers() -> None:
    agg = SpanAggregator()
    # Two action spans, both ending within MAX_END_TO_EVENT_GAP_S=8 of
    # event_ts=1000.  First span ends at 994, second at 998.5 — both
    # in [event-8, event-1.5].
    _action_span_at(agg, t0=991.0, dur=3.0)   # ends 994
    for ts in (994.5, 995.0, 995.5):          # break with other×3
        agg.add_classification(ts, "other")
    _action_span_at(agg, t0=995.5, dur=3.0)   # ends 998.5
    verdict, bounds = agg.match_span_to_event(event_ts=1000.0)
    assert verdict == "defer_to_legacy", (verdict, bounds, agg.snapshot())
    assert bounds is None
    print("ok test_match_multi_defers")


# ── 3. Replay validation against scout_responses_open.jsonl ────────

VALIDATION_JSONL = (
    ROOT / "scripts" / "scout_validation_research"
    / "output" / "scout_responses_open.jsonl"
)


def _load_clip_rows() -> dict[str, list[dict]]:
    rows_by_clip: dict[str, list[dict]] = {}
    with VALIDATION_JSONL.open() as fh:
        for line in fh:
            rec = json.loads(line)
            clip = rec.get("source_clip") or ""
            rows_by_clip.setdefault(clip, []).append(rec)
    for clip in rows_by_clip:
        rows_by_clip[clip].sort(
            key=lambda r: float(r.get("time_in_clip_s") or 0.0))
    return rows_by_clip


def test_replay_validation_clip_qc() -> None:
    """Per §E1: ≥13/15 clip QC.

    For each clip, replay its frames through SpanAggregator + the
    rule-v2 classifier, then check:
      * positive (any GT==action frame) → aggregator emits ≥1 action span
      * negative (no GT==action frame)  → aggregator emits 0 action spans
    """
    if not VALIDATION_JSONL.is_file():
        print(f"SKIP test_replay_validation_clip_qc — "
              f"missing {VALIDATION_JSONL}")
        return

    rows_by_clip = _load_clip_rows()
    n_clips = len(rows_by_clip)
    passes = 0
    per_clip_summary: list[tuple[str, str, int, int, bool]] = []

    for clip, rows in sorted(rows_by_clip.items()):
        is_positive = any(
            (r.get("ground_truth") or "").strip() == "action"
            for r in rows
        )
        agg = SpanAggregator()
        for r in rows:
            ts = float(r.get("time_in_clip_s") or 0.0)
            desc = r.get("open_description") or ""
            cls = classify_full(desc)
            agg.add_classification(ts, cls)
        # Force-close the trailing span; skip prune (synthetic ts).
        agg.force_close(now=None)
        action_spans = [s for s in agg.snapshot()
                        if s.frame_class == "action"
                        and s.duration_s >= MIN_ACTION_SPAN_S]
        if is_positive:
            ok = len(action_spans) >= 1
        else:
            ok = len(action_spans) == 0
        per_clip_summary.append(
            (clip, "POS" if is_positive else "NEG",
             len(rows), len(action_spans), ok))
        if ok:
            passes += 1

    print(f"\n[REPLAY-QC] {passes}/{n_clips} clips passed:")
    for clip, kind, n, n_spans, ok in per_clip_summary:
        marker = "PASS" if ok else "FAIL"
        print(f"  [{marker}] {clip:40s} {kind} "
              f"frames={n:3d} action_spans={n_spans}")
    assert passes >= 13, (
        f"expected ≥13/{n_clips} clips to pass, got {passes}")
    print(f"ok test_replay_validation_clip_qc ({passes}/{n_clips})")


# ── Driver ─────────────────────────────────────────────────────────

TESTS = [
    test_continuous_span,
    test_class_transitions,
    test_gap_tolerance_absorbs_single_dissent,
    test_two_dissents_force_close,
    test_min_span_filter_drops_singleton,
    test_soft_gap_force_close,
    test_retention_pruning,
    test_match_no_candidates,
    test_match_short_action_filtered,
    test_match_single_candidate,
    test_match_stale_span_rejected,
    test_match_multi_defers,
    test_replay_validation_clip_qc,
]


def main() -> int:
    failed = 0
    for fn in TESTS:
        try:
            fn()
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {fn.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
