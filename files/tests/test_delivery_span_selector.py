"""Unit + replay tests for DeliverySpanSelector (Stage 2 streaming).

Run:
    cd /Users/anmolmohan/Projects/SportsComm/files
    python3 tests/test_delivery_span_selector.py

Sections:
  1. Synthetic-stream unit tests covering the closure rule, hard-close
     pre-pass, post-filters, and bounded memory.
  2. Equivalence test against the v4 research baseline
     (``files/scripts/sub_clip_isolation_v4/span_selection.csv``):
     replay each labeled clip's Scout JSONL frames through the
     streaming selector and assert ≥85 % of v4-selected clips are
     reproduced within 1 s tolerance on padded bounds.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

THIS = Path(__file__).resolve().parent
ROOT = THIS.parent
sys.path.insert(0, str(ROOT))

from eyes.delivery_span_selector import (  # noqa: E402
    DeliverySpan,
    DeliverySpanSelector,
)

SCOUT_JSONL = ROOT / "scripts" / "path_a_baseline" / "scout_results_v2.jsonl"
V4_CSV = ROOT / "scripts" / "sub_clip_isolation_v4" / "span_selection.csv"


def _make_selector(emitted: list[DeliverySpan], **kwargs) -> DeliverySpanSelector:
    return DeliverySpanSelector(
        on_span_emitted=lambda d: emitted.append(d),
        **kwargs,
    )


def _frame(ts: float, cls: str | None) -> dict:
    return {"ts": float(ts), "frame_class": cls, "raw_description": ""}


# ── 1. Synthetic-stream unit tests ─────────────────────────────────

def test_single_delivery_span() -> None:
    emitted: list[DeliverySpan] = []
    sel = _make_selector(emitted)
    seq = (["other"] * 2) + (["action"] * 7) + (["other"] * 2)
    for i, c in enumerate(seq):
        sel.add_scout_result(_frame(i, c))
    sel.flush()
    assert len(emitted) == 1, emitted
    d = emitted[0]
    # Dissent absorption: ts=2 swallowed as gap_obs=1; the action
    # span actually starts at the t=3 transition.
    assert d.frame_count == 6
    assert d.raw_start_ts == 3.0
    assert d.raw_end_ts == 8.0
    # Padding: raw_end+1=9, last_observed_ts=10 → padded_end=9
    assert d.start_ts == 2.0
    assert d.end_ts == 9.0
    assert d.selection_basis == "fallback_no_event"
    assert d.hard_close_count == 0
    print("ok test_single_delivery_span")


def test_two_consecutive_deliveries() -> None:
    emitted: list[DeliverySpan] = []
    sel = _make_selector(emitted)
    seq = (["action"] * 6 + ["other"] * 3
           + ["action"] * 6 + ["other"] * 3)
    for i, c in enumerate(seq):
        sel.add_scout_result(_frame(i, c))
    sel.flush()
    assert len(emitted) == 2, [(d.raw_start_ts, d.raw_end_ts)
                                for d in emitted]
    a, b = emitted
    # First span: t=0..5 (6 obs). Second span: starts at the t=10
    # transition after one dissent absorption, so n=5 over t=10..14.
    assert a.frame_count == 6
    assert b.frame_count == 5
    assert a.raw_end_ts < b.raw_start_ts
    print("ok test_two_consecutive_deliveries")


def test_replay_hard_close() -> None:
    emitted: list[DeliverySpan] = []
    sel = _make_selector(emitted)
    seq = ["action"] * 6 + ["replay"] * 1 + ["action"] * 3
    for i, c in enumerate(seq):
        sel.add_scout_result(_frame(i, c))
    sel.flush()
    assert len(emitted) == 1, emitted
    d = emitted[0]
    assert d.frame_count == 6
    assert d.hard_close_count == 1
    print("ok test_replay_hard_close")


def test_short_span_below_min_run_frames() -> None:
    emitted: list[DeliverySpan] = []
    sel = _make_selector(emitted)
    # 4 action frames < min_run_frames=5
    seq = ["other"] * 2 + ["action"] * 4 + ["other"] * 3
    for i, c in enumerate(seq):
        sel.add_scout_result(_frame(i, c))
    sel.flush()
    assert emitted == [], emitted
    print("ok test_short_span_below_min_run_frames")


def test_short_span_below_min_span_duration() -> None:
    emitted: list[DeliverySpan] = []
    # Tighten min_run_frames so the duration filter is the gate.
    sel = _make_selector(emitted, min_run_frames=2,
                         min_span_duration_s=2.0)
    # Two action obs at ts=0,1 → duration=1 s < 2 s
    seq = [(0, "action"), (1, "action"), (2, "other"), (3, "other"),
           (10, "other")]
    for ts, c in seq:
        sel.add_scout_result(_frame(ts, c))
    sel.flush()
    assert emitted == [], emitted
    print("ok test_short_span_below_min_span_duration")


def test_memory_management_bounded_buffer() -> None:
    emitted: list[DeliverySpan] = []
    sel = _make_selector(emitted, max_buffered_frames=50,
                         rolling_window_s=20.0)
    for ts in range(200):
        sel.add_scout_result(_frame(ts, "other"))
    # Hard cap from deque maxlen
    assert len(sel._frame_buffer) <= 50
    # Rolling-window prune is more aggressive (20 s window at 1 fps)
    assert len(sel._frame_buffer) <= 21
    print(f"ok test_memory_management_bounded_buffer "
          f"(buffer={len(sel._frame_buffer)})")


def test_closure_hold_emits_during_stream() -> None:
    """A span should emit mid-stream once 3 s of post-frames pass,
    not only at flush()."""
    emitted: list[DeliverySpan] = []
    sel = _make_selector(emitted)
    seq = ["action"] * 6 + ["other"] * 6
    seen_at = None
    for i, c in enumerate(seq):
        sel.add_scout_result(_frame(i, c))
        if emitted and seen_at is None:
            seen_at = i
    assert len(emitted) == 1, emitted
    # Span commits at the second 'other' (transition fires at ts=7
    # because 'other' at ts=6 is absorbed as gap_obs=1 then the
    # second dissent transitions).  Closure hold = 3 s, so emission
    # fires when ts >= 10.
    assert seen_at is not None and seen_at >= 10, seen_at
    print(f"ok test_closure_hold_emits_during_stream (at ts={seen_at})")


# ── 1b. mark_score_event temporal anchoring ────────────────────────

def test_score_event_anchored_span_selection() -> None:
    """Two qualifying spans bracket a score event: emit only the one
    that ends within the anchor window before the event; drop the one
    that starts after it (post-event replay/celebration)."""
    emitted: list[DeliverySpan] = []
    sel = _make_selector(emitted)

    seq_a = (["other"] * 2) + (["action"] * 7) + (["other"] * 2)
    for i, c in enumerate(seq_a):
        sel.add_scout_result(_frame(i, c))

    event_ts = 14.0
    sel.mark_score_event(event_ts)

    seq_b = (["action"] * 7) + (["other"] * 6)
    for off, c in enumerate(seq_b):
        sel.add_scout_result(_frame(18 + off, c))

    sel.flush()
    assert len(emitted) == 1, [(d.raw_start_ts, d.raw_end_ts,
                                d.selection_basis) for d in emitted]
    d = emitted[0]
    assert d.selection_basis == "anchored_to_event_ts"
    assert d.raw_end_ts < event_ts
    print("ok test_score_event_anchored_span_selection")


def test_score_event_rejects_post_event_span() -> None:
    """Only span available starts after event_ts → no emission."""
    emitted: list[DeliverySpan] = []
    sel = _make_selector(emitted)

    event_ts = 2.0
    sel.mark_score_event(event_ts)

    seq = ["other"] * 5 + ["action"] * 7 + ["other"] * 6
    for i, c in enumerate(seq):
        sel.add_scout_result(_frame(i, c))
    sel.flush()
    assert emitted == [], [(d.raw_start_ts, d.raw_end_ts,
                            d.selection_basis) for d in emitted]
    print("ok test_score_event_rejects_post_event_span")


def test_no_score_event_falls_back_to_longest() -> None:
    """No mark_score_event call → emit qualifying spans tagged
    ``fallback_no_event`` (legacy behaviour)."""
    emitted: list[DeliverySpan] = []
    sel = _make_selector(emitted)
    seq = (["other"] * 2) + (["action"] * 7) + (["other"] * 6)
    for i, c in enumerate(seq):
        sel.add_scout_result(_frame(i, c))
    sel.flush()
    assert len(emitted) == 1, emitted
    assert emitted[0].selection_basis == "fallback_no_event"
    print("ok test_no_score_event_falls_back_to_longest")


# ── 2. Equivalence vs v4 ───────────────────────────────────────────

def _load_v4_selections() -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    with V4_CSV.open() as f:
        for row in csv.DictReader(f):
            out[(row["session"], row["clip_id"])] = row
    return out


def _load_scout_frames_by_clip() -> dict[tuple[str, str], list[dict]]:
    by_clip: dict[tuple[str, str], list[dict]] = defaultdict(list)
    with SCOUT_JSONL.open() as f:
        for line in f:
            r = json.loads(line)
            by_clip[(r["session"], r["clip_id"])].append(r)
    for k in by_clip:
        by_clip[k].sort(key=lambda r: r["frame_index"])
    return by_clip


def _replay_clip(frames: list[dict]) -> list[DeliverySpan]:
    emitted: list[DeliverySpan] = []
    sel = DeliverySpanSelector(
        on_span_emitted=lambda d: emitted.append(d),
    )
    for fr in frames:
        sel.add_scout_result({
            "ts": float(fr["frame_index"]),
            "frame_class": fr.get("scout_class"),
            "raw_description": fr.get("raw_description"),
        })
    sel.flush()
    return emitted


def test_streaming_equivalence_with_v4() -> None:
    if not SCOUT_JSONL.exists() or not V4_CSV.exists():
        print(f"skip test_streaming_equivalence_with_v4 "
              f"(missing data: {SCOUT_JSONL.exists()=} "
              f"{V4_CSV.exists()=})")
        return

    v4 = _load_v4_selections()
    scout = _load_scout_frames_by_clip()

    tol = 1.0
    matched = 0
    total = 0
    misses: list[str] = []
    for key, row in v4.items():
        sel_frames = int(row.get("selected_frames") or 0)
        if sel_frames == 0:
            continue
        total += 1
        v4_start = float(row["padded_start_s"])
        v4_end = float(row["padded_end_s"])
        frames = scout.get(key, [])
        if not frames:
            misses.append(f"{key}: no scout frames")
            continue
        emitted = _replay_clip(frames)
        hit = any(abs(d.start_ts - v4_start) <= tol
                  and abs(d.end_ts - v4_end) <= tol
                  for d in emitted)
        if hit:
            matched += 1
        else:
            best = ""
            if emitted:
                d = min(emitted,
                        key=lambda d: (abs(d.start_ts - v4_start)
                                       + abs(d.end_ts - v4_end)))
                best = (f" closest=[{d.start_ts:.2f}-{d.end_ts:.2f}]"
                        f" raw=[{d.raw_start_ts:.2f}-{d.raw_end_ts:.2f}]")
            misses.append(
                f"{key}: v4=[{v4_start:.2f}-{v4_end:.2f}]{best}")

    rate = matched / total if total else 0.0
    print(f"streaming↔v4 equivalence: {matched}/{total} "
          f"({rate:.0%}) within ±{tol}s")
    for m in misses:
        print(f"  miss {m}")
    assert rate >= 0.85, (
        f"equivalence {rate:.0%} below 0.85 threshold "
        f"({matched}/{total})")
    print("ok test_streaming_equivalence_with_v4")


# ── Driver ─────────────────────────────────────────────────────────

TESTS = [
    test_single_delivery_span,
    test_two_consecutive_deliveries,
    test_replay_hard_close,
    test_short_span_below_min_run_frames,
    test_short_span_below_min_span_duration,
    test_memory_management_bounded_buffer,
    test_closure_hold_emits_during_stream,
    test_score_event_anchored_span_selection,
    test_score_event_rejects_post_event_span,
    test_no_score_event_falls_back_to_longest,
    test_streaming_equivalence_with_v4,
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
