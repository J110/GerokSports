"""ChunkerV3 fixture tests against the 18 cached clips.

Acceptance: ≥13/18 MATCH (IoU ≥ 0.6) AND 0 FPs (None-truth clips MUST
produce None).  Baseline before the three fixes is 10/7/1/0 — see
``/Users/anmolmohan/Projects/SportsComm/v3_simulation_results.txt``.

Fixture data: ``files/scripts/broadcast_mode_tuning/
chunk_v1_combined_data.csv``.  3204 rows; 18 clips of ~10 s each at
3 fps.

The CSV column order is::

    clip_id,session,ts,prod_cam,prod_phase,v2_broadcast_tag,v2_class,open_desc

``open_desc`` may contain embedded newlines and CSV-escaped quotes; the
standard ``csv`` module handles both.
"""
from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Optional

import pytest

from eyes.chunker_v3 import FrameInput, find_consequential_window

FIXTURE_CSV = (
    Path(__file__).resolve().parents[1]
    / "scripts" / "broadcast_mode_tuning" / "chunk_v1_combined_data.csv"
)

# Ground truth from v3_simulation_results.txt; matches the spec body.
GROUND_TRUTH: dict[tuple[str, str], Optional[tuple[float, float]]] = {
    ("20260503_205835", "d001"): None,
    ("20260503_205835", "d002"): None,
    ("20260503_205835", "d003"): None,
    ("20260503_205835", "d004"): (1.0, 8.0),
    ("20260503_205835", "d005"): (5.0, 9.0),
    ("20260503_205835", "d006"): None,
    ("20260503_205835", "d007"): (0.0, 5.0),
    ("20260503_205835", "d008"): None,
    ("20260421_195050", "d046"): (2.0, 12.0),
    ("20260421_195050", "d059"): (0.0, 11.0),
    ("20260421_195050", "d051"): (0.0, 8.0),
    ("20260420_202239", "d015"): (8.0, 18.0),
    ("20260420_202239", "d004"): (7.0, 18.0),
    ("20260420_202239", "d036"): (12.0, 20.0),
    ("20260420_202239", "d032"): (12.0, 22.0),
    ("20260420_202239", "d029"): (8.0, 13.0),
    ("20260420_202239", "d018"): (8.0, 22.0),
    ("20260420_202239", "d014"): (0.0, 7.0),
}

ACCEPTANCE_MATCH_MIN = 13
ACCEPTANCE_FP_MAX = 0
IOU_MATCH_THRESHOLD = 0.6
IOU_PARTIAL_THRESHOLD = 0.3


def _iou(a: tuple[float, float], b: tuple[float, float]) -> float:
    inter = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return inter / union if union > 0 else 0.0


def _verdict(truth: Optional[tuple[float, float]],
             pred: Optional[tuple[float, float]]) -> tuple[str, float]:
    if truth is None and pred is None:
        return "MATCH", 1.0
    if truth is None and pred is not None:
        return "FP", 0.0
    if truth is not None and pred is None:
        return "WRONG", 0.0
    iou = _iou(truth, pred)
    if iou >= IOU_MATCH_THRESHOLD:
        return "MATCH", iou
    if iou >= IOU_PARTIAL_THRESHOLD:
        return "PARTIAL", iou
    return "WRONG", iou


def _load_fixture(path: Path) -> dict[tuple[str, str], list[FrameInput]]:
    """Group CSV rows by (session, clip_id) and return sorted FrameInputs."""
    out: dict[tuple[str, str], list[FrameInput]] = {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            session = row["session"]
            clip_id = row["clip_id"]
            try:
                ts = float(row["ts"])
            except (TypeError, ValueError):
                continue
            f = FrameInput(
                ts=ts,
                prod_cam=row.get("prod_cam") or "",
                prod_phase=row.get("prod_phase") or "",
                v2_broadcast_tag=row.get("v2_broadcast_tag") or "",
                v2_class=row.get("v2_class") or "",
                open_desc=row.get("open_desc") or "",
            )
            out.setdefault((session, clip_id), []).append(f)
    for k in out:
        out[k].sort(key=lambda x: x.ts)
    return out


@pytest.fixture(scope="module")
def fixtures() -> dict[tuple[str, str], list[FrameInput]]:
    if not FIXTURE_CSV.exists():
        pytest.skip(f"fixture CSV not found at {FIXTURE_CSV}")
    return _load_fixture(FIXTURE_CSV)


@pytest.mark.parametrize("session,clip_id,truth",
                         [(s, c, t) for (s, c), t in GROUND_TRUTH.items()])
def test_clip_no_false_positive(fixtures, session, clip_id, truth):
    """Hard requirement: every None-truth clip MUST predict None.
    Any FP is a regression.
    """
    if truth is not None:
        pytest.skip("only None-truth clips checked here")
    frames = fixtures.get((session, clip_id))
    assert frames is not None, f"missing fixture {session}/{clip_id}"
    pred = find_consequential_window(frames)
    assert pred is None, (
        f"FP on {session}/{clip_id}: predicted {pred}, truth=None")


def test_match_rate_meets_acceptance(fixtures):
    """Aggregate: ≥13/18 MATCH, 0 FPs."""
    counts = {"MATCH": 0, "PARTIAL": 0, "WRONG": 0, "FP": 0}
    failures: list[str] = []
    for (session, clip_id), truth in GROUND_TRUTH.items():
        frames = fixtures.get((session, clip_id))
        if frames is None:
            failures.append(f"missing {session}/{clip_id}")
            continue
        pred = find_consequential_window(frames)
        verdict, iou = _verdict(truth, pred)
        counts[verdict] += 1
        if verdict in ("WRONG", "FP", "PARTIAL"):
            failures.append(
                f"{session}/{clip_id} truth={truth} pred={pred} "
                f"verdict={verdict} iou={iou:.2f}")
    summary = (
        f"MATCH={counts['MATCH']} PARTIAL={counts['PARTIAL']} "
        f"WRONG={counts['WRONG']} FP={counts['FP']} / 18\n"
        + "\n".join(failures))
    assert counts["FP"] <= ACCEPTANCE_FP_MAX, (
        f"FP regression — {summary}")
    assert counts["MATCH"] >= ACCEPTANCE_MATCH_MIN, (
        f"MATCH below threshold ({ACCEPTANCE_MATCH_MIN}) — {summary}")


# ── Predicate / unit smoke tests ───────────────────────────────────


def test_score_frame_priority_ad_wins_over_replay():
    """A frame with both AD signals (ad cam) and replay signals (slowmo
    text) must label AD per the priority ladder."""
    from eyes.chunker_v3 import label_frame, score_frame
    f = FrameInput(
        ts=0.0, prod_cam="ad", prod_phase="advertisement",
        v2_broadcast_tag="REPLAY", v2_class="other",
        open_desc="slow motion of an earlier moment",
    )
    ev = score_frame(f)
    assert label_frame(f, ev) == "AD"


def test_celebration_player_alone_is_not_replay():
    """Fix #2: celeb_player without crowd-as-subject → not REPLAY."""
    from eyes.chunker_v3 import label_frame, score_frame
    f = FrameInput(
        ts=0.0, prod_cam="bowlers_end", prod_phase="post_shot",
        v2_broadcast_tag="LIVE", v2_class="action",
        open_desc=(
            "The batter has just played the shot, arm raised in "
            "celebration as the ball travels toward the boundary."),
    )
    ev = score_frame(f)
    label = label_frame(f, ev)
    assert label != "REPLAY", f"celeb_player alone fired REPLAY ({label})"


def test_celebration_with_crowd_subject_is_replay():
    """Crowd-as-subject + celebration → REPLAY (Fix #2 keeps this path)."""
    from eyes.chunker_v3 import label_frame, score_frame
    f = FrameInput(
        ts=10.0, prod_cam="closeup", prod_phase="between_play",
        v2_broadcast_tag="REPLAY", v2_class="other",
        open_desc=("The crowd is cheering wildly with fans visible in "
                   "the foreground."),
    )
    ev = score_frame(f)
    assert label_frame(f, ev) == "REPLAY"


def test_hypothetical_umpire_rejected():
    """Section A: 'possibly the umpire' must NOT trigger UMPIRE_SIGNAL."""
    from eyes.chunker_v3 import label_frame, score_frame
    f = FrameInput(
        ts=10.0, prod_cam="side_on", prod_phase="post_shot",
        v2_broadcast_tag="LIVE", v2_class="action",
        open_desc=("A fielder is signaling, possibly the umpire, with "
                   "an arm raised."),
    )
    ev = score_frame(f)
    assert label_frame(f, ev) != "UMPIRE_SIGNAL"


def test_v2_broadcast_tag_replay_triggers_replay_label():
    """v2_broadcast_tag='REPLAY' with neutral prose must label REPLAY
    via the is_replay_tag predicate alone.  Closes the previous
    plumbing gap where vision.last_v2_broadcast_tag was always None
    and is_replay_tag never fired."""
    from eyes.chunker_v3 import label_frame, score_frame
    f = FrameInput(
        ts=5.0, prod_cam="side_on", prod_phase="between_play",
        v2_broadcast_tag="REPLAY", v2_class="other",
        open_desc=("A wide field view with players in position."),
    )
    ev = score_frame(f)
    assert ev["is_replay_tag"] is True
    assert label_frame(f, ev) == "REPLAY"


def test_extract_v2_broadcast_tag():
    """The OpenScout V2 prompt's first-line tag is parsed back to a
    bare uppercase token; missing / unknown returns ""."""
    from eyes.open_scout import extract_v2_broadcast_tag
    assert extract_v2_broadcast_tag(
        "[BROADCAST: REPLAY]\nThe batter raises bat.") == "REPLAY"
    assert extract_v2_broadcast_tag(
        "[BROADCAST: SLO-MO] slow motion shot") == "SLO-MO"
    assert extract_v2_broadcast_tag(
        "  [BROADCAST: TELESTRATOR]  arrows on screen") == "TELESTRATOR"
    assert extract_v2_broadcast_tag(
        "[BROADCAST: LIVE] bowler running in") == "LIVE"
    assert extract_v2_broadcast_tag(
        "Plain v1 prose with no tag.") == ""
    assert extract_v2_broadcast_tag("") == ""
    assert extract_v2_broadcast_tag(None) == ""


def test_open_scout_result_carries_v2_tag():
    """OpenScoutResult exposes v2_broadcast_tag so the result_sink
    has access without hitting Vision."""
    from eyes.open_scout import OpenScoutResult
    r = OpenScoutResult(
        timestamp=1.0, frame_class="replay", raw_description="x",
        tokens_total=100, v2_broadcast_tag="REPLAY")
    assert r.v2_broadcast_tag == "REPLAY"
    # Backward-compatible default when not specified.
    r2 = OpenScoutResult(
        timestamp=1.0, frame_class="action", raw_description="x")
    assert r2.v2_broadcast_tag == ""


def test_drs_keyword_outranks_replay():
    """DRS > REPLAY in the priority order."""
    from eyes.chunker_v3 import label_frame, score_frame
    f = FrameInput(
        ts=15.0, prod_cam="graphic", prod_phase="between_play",
        v2_broadcast_tag="REPLAY", v2_class="other",
        open_desc="Hawkeye ball-tracking trajectory shown in slow motion.",
    )
    ev = score_frame(f)
    assert label_frame(f, ev) == "DRS"


def test_empty_frames_returns_none():
    assert find_consequential_window([]) is None


def test_aggregator_basic_roundtrip():
    from eyes.chunker_v3_aggregator import V3SpanAggregator
    agg = V3SpanAggregator()
    # Empty buffer → None.
    assert agg.find_span(event_ts=10.0) is None
    # Add a few delivery-action frames; pure-prose path with
    # bowlers_end + batter mention + action verb.
    for ts in (5.0, 6.0, 7.0):
        agg.add_frame(
            ts,
            prod_cam="bowlers_end",
            prod_phase="release",
            v2_broadcast_tag="LIVE",
            v2_class="action",
            open_desc=("The bowler is running in toward the batter at "
                       "the crease, mid-stride with stumps visible."),
        )
    # Padding frames so anchor confirmation has neighbors.
    agg.add_frame(
        4.0, prod_cam="bowlers_end", prod_phase="between_play",
        v2_broadcast_tag="LIVE", v2_class="other",
        open_desc="A wide field view between deliveries.")
    agg.add_frame(
        8.0, prod_cam="side_on", prod_phase="between_play",
        v2_broadcast_tag="LIVE", v2_class="other",
        open_desc="Mid-shot fielders walking back to position.")
    span = agg.find_span(event_ts=10.0)
    assert span is not None
    assert span[0] <= 7.0 <= span[1]


def test_aggregator_drops_blank_frames():
    from eyes.chunker_v3_aggregator import V3SpanAggregator
    agg = V3SpanAggregator()
    agg.add_frame(
        1.0, prod_cam=None, prod_phase=None,
        v2_broadcast_tag=None, v2_class=None, open_desc=None)
    s = agg.stats()
    assert s["adds_dropped_invalid"] == 1
    assert s["adds_total"] == 0


# ── P21 anomaly-rule unit tests ─────────────────────────────────────


def test_p21_fires_on_divergence():
    from anomaly_rules import (
        AnalyzerState,
        rule_chunker_v3_divergence,
    )
    rec = {
        "frame": 100,
        "scorer": {"decisions": [{
            "tag": "CHUNKER-V3-WINDOW",
            "raw_message": (
                "[CHUNKER-V3-WINDOW] legacy_start=10.0 legacy_end=18.0 "
                "v3_start=14.5 v3_end=21.5 drove_cut=legacy"),
            "_auto": True,
        }]},
    }
    state = AnalyzerState()
    fired = rule_chunker_v3_divergence(state, rec, [rec])
    assert len(fired) == 1
    a = fired[0]
    assert a.id == "P21"
    assert a.severity == "advisory"
    assert a.evidence["diverge_start_s"] == 4.5
    assert a.evidence["diverge_end_s"] == 3.5


def test_p21_silent_when_within_threshold():
    from anomaly_rules import (
        AnalyzerState,
        rule_chunker_v3_divergence,
    )
    rec = {
        "frame": 100,
        "scorer": {"decisions": [{
            "tag": "CHUNKER-V3-WINDOW",
            "raw_message": (
                "[CHUNKER-V3-WINDOW] legacy_start=10.0 legacy_end=18.0 "
                "v3_start=10.5 v3_end=18.5 drove_cut=legacy"),
            "_auto": True,
        }]},
    }
    state = AnalyzerState()
    fired = rule_chunker_v3_divergence(state, rec, [rec])
    assert fired == []


def test_p22_fires_on_fallback_log():
    from anomaly_rules import (
        AnalyzerState,
        rule_chunker_v3_fallback_used,
    )
    rec = {
        "frame": 100,
        "scorer": {"decisions": [{
            "tag": "CHUNKER-V3-FALLBACK",
            "raw_message": (
                "[CHUNKER-V3-FALLBACK] event_ts=120.50 window=(114.50, "
                "124.50) lookback_s=6.00 forward_s=4.00"),
            "_auto": True,
        }]},
    }
    state = AnalyzerState()
    fired = rule_chunker_v3_fallback_used(state, rec, [rec])
    assert len(fired) == 1
    a = fired[0]
    assert a.id == "P22"
    assert a.severity == "warn"
    assert a.evidence["event_ts"] == 120.5
    assert a.evidence["window_start"] == 114.5
    assert a.evidence["window_end"] == 124.5


def test_p22_silent_when_no_fallback_decision():
    from anomaly_rules import (
        AnalyzerState,
        rule_chunker_v3_fallback_used,
    )
    rec = {"frame": 100, "scorer": {"decisions": []}}
    state = AnalyzerState()
    assert rule_chunker_v3_fallback_used(state, rec, [rec]) == []


# ── DWR V3 None-fallback integration tests ─────────────────────────


class _StubClassifier:
    def __init__(self):
        self.calls: list[dict] = []

    def classify_frames(self, frames, runs=0, save_dir=None, **kw):
        self.calls.append({"n_frames": len(frames), "runs": runs})
        return {"_method": "stub_dwr_v3_test"}


class _StubV3Aggregator:
    """Always returns None so DWR's else branch fires."""

    def find_span(self, event_ts, **kw):
        return None

    def snapshot_frames(self):
        return []


def _build_recorder_for_fallback_test(tmp_path,
                                      *,
                                      v3_fallback_enabled: bool | None = None,
                                      v3_fallback_lookback_s: float | None = None,
                                      v3_fallback_forward_s: float | None = None):
    """Construct a DWR with stubs that force the else branch.

    No tagged frames → legacy `_find_span` returns None.
    Stub v3_aggregator → v3 returns None.
    Frame source returns synthetic frames so we clear MIN_FRAMES_FOR_
    CLASSIFICATION.
    """
    from delivery_window_recorder import DeliveryWindowRecorder
    import numpy as np

    def frame_source(start, end):
        # 6 synthetic frames spaced 0.5 s — clears min_frames=4.
        n = 6
        out = []
        for i in range(n):
            t = float(start) + (float(end) - float(start)) * (i / max(n - 1, 1))
            out.append((t, np.zeros((4, 4, 3), dtype=np.uint8)))
        return out

    def tagged_source(start, end, allowed_views):
        return []

    return DeliveryWindowRecorder(
        classifier=_StubClassifier(),
        frame_source_fn=frame_source,
        tagged_source_fn=tagged_source,
        save_root=tmp_path,
        span_aggregator=None,
        use_open_scout_spans=False,
        stage2_span_lookup=None,
        v3_aggregator=_StubV3Aggregator(),
        use_v3_chunker_spans=True,
        v3_fallback_enabled=v3_fallback_enabled,
        v3_fallback_lookback_s=v3_fallback_lookback_s,
        v3_fallback_forward_s=v3_fallback_forward_s,
    )


def test_fallback_when_v3_and_legacy_both_none(tmp_path):
    """v3 and legacy both None + fallback enabled → fallback window
    (event_ts−6, event_ts+4) drives the cut."""
    rec = _build_recorder_for_fallback_test(
        tmp_path,
        v3_fallback_enabled=True,
        v3_fallback_lookback_s=6.0,
        v3_fallback_forward_s=4.0,
    )
    event_ts = 100.0
    result = rec.classify_for_score_event(
        runs=1, event_ts=event_ts, save_dir=str(tmp_path / "win_a"))
    assert result is not None
    assert result["_window_source"] == "v3_chunker_fallback"
    assert result["_window_start_ts"] == 94.0
    assert result["_window_end_ts"] == 104.0
    # window_debug.json should record the fallback.
    import json
    debug = json.loads(
        (tmp_path / "win_a" / "window_debug.json").read_text())
    assert debug["window_source"] == "v3_chunker_fallback"
    assert debug["fallback"]["used"] is True
    assert debug["fallback"]["lookback_s"] == 6.0
    assert debug["fallback"]["forward_s"] == 4.0
    assert debug["v3_chunker"]["drove_cut"] == "fallback"


def test_fallback_disabled(tmp_path):
    """V3_FALLBACK_ENABLED=0 → behavior reverts to legacy
    fallback_pre_event_window; v3_chunker.drove_cut stays bool."""
    rec = _build_recorder_for_fallback_test(
        tmp_path, v3_fallback_enabled=False)
    event_ts = 100.0
    result = rec.classify_for_score_event(
        runs=1, event_ts=event_ts, save_dir=str(tmp_path / "win_b"))
    assert result is not None
    assert result["_window_source"] == "fallback_pre_event_window"
    import json
    debug = json.loads(
        (tmp_path / "win_b" / "window_debug.json").read_text())
    assert debug["window_source"] == "fallback_pre_event_window"
    assert debug["fallback"]["used"] is False
    # drove_cut is bool when fallback didn't fire.
    assert debug["v3_chunker"]["drove_cut"] is False


def test_fallback_lookback_override(tmp_path):
    """V3_FALLBACK_LOOKBACK_S override propagates to the cut bounds."""
    rec = _build_recorder_for_fallback_test(
        tmp_path,
        v3_fallback_enabled=True,
        v3_fallback_lookback_s=8.0,
        v3_fallback_forward_s=4.0,
    )
    event_ts = 100.0
    result = rec.classify_for_score_event(
        runs=1, event_ts=event_ts, save_dir=str(tmp_path / "win_c"))
    assert result is not None
    assert result["_window_start_ts"] == 92.0
    assert result["_window_end_ts"] == 104.0
    import json
    debug = json.loads(
        (tmp_path / "win_c" / "window_debug.json").read_text())
    assert debug["fallback"]["lookback_s"] == 8.0


def test_p21_silent_when_v3_returns_none():
    from anomaly_rules import (
        AnalyzerState,
        rule_chunker_v3_divergence,
    )
    rec = {
        "frame": 100,
        "scorer": {"decisions": [{
            "tag": "CHUNKER-V3-WINDOW",
            "raw_message": (
                "[CHUNKER-V3-WINDOW] legacy_start=10.0 legacy_end=18.0 "
                "v3_start=None v3_end=None drove_cut=legacy"),
            "_auto": True,
        }]},
    }
    state = AnalyzerState()
    fired = rule_chunker_v3_divergence(state, rec, [rec])
    assert fired == []


# ── v3.1 replay-filter additions ───────────────────────────────────


def test_v31_replay_overlay_text_forces_replay_label():
    """Bulletproof override: open_desc containing literal replay overlay
    text (e.g. "INSTANT REPLAY") labels REPLAY even when production tags
    say live cam."""
    from eyes.chunker_v3 import label_frame, score_frame
    f = FrameInput(
        ts=5.0, prod_cam="bowlers_end", prod_phase="release",
        v2_broadcast_tag="LIVE", v2_class="action",
        open_desc=(
            "INSTANT REPLAY graphic in the corner; the batter is "
            "mid-swing at the crease."),
    )
    ev = score_frame(f)
    assert ev["has_replay_overlay"] is True
    assert label_frame(f, ev) == "REPLAY"


def test_v31_analysis_graphic_counts_as_replay_overlay():
    """ANALYSIS only fires when described as a graphic / overlay /
    letters — bare "analysis" in commentary should NOT promote."""
    from eyes.chunker_v3 import label_frame, score_frame
    f_graphic = FrameInput(
        ts=5.0, prod_cam="closeup", prod_phase="between_play",
        v2_broadcast_tag="LIVE", v2_class="other",
        open_desc=(
            "ANALYSIS graphic overlay with stats letters across the "
            "lower third of the screen."),
    )
    ev = score_frame(f_graphic)
    assert ev["has_replay_overlay"] is True
    assert label_frame(f_graphic, ev) == "REPLAY"

    f_commentary = FrameInput(
        ts=5.0, prod_cam="bowlers_end", prod_phase="release",
        v2_broadcast_tag="LIVE", v2_class="action",
        open_desc=(
            "The bowler runs in for analysis of the previous over; "
            "batter at the crease."),
    )
    ev2 = score_frame(f_commentary)
    assert ev2["has_replay_overlay"] is False


def test_v31_close_up_demotes_to_replay_lean_off_live_cam():
    """Off-live-cam close-up with neither wide-field text NOR
    pitch-context terms (stumps / crease / wicket / pitch) demotes
    to REPLAY_LEAN.  Pitch-context creates a fallback escape from
    demotion (recovers d004-class truncated deliveries)."""
    from eyes.chunker_v3 import label_frame, score_frame
    # Pure single-player close-up — no pitch context; v3.1 demotes.
    f = FrameInput(
        ts=5.0, prod_cam="closeup", prod_phase="release",
        v2_broadcast_tag="LIVE", v2_class="other",
        open_desc=(
            "Close-up shot of a single cricket player from behind, "
            "facing away from the camera with helmet visible."),
    )
    ev = score_frame(f)
    assert ev["is_single_player_focus"] is True
    assert ev["has_pitch_context"] is False
    assert label_frame(f, ev) == "REPLAY_LEAN"


def test_v31_pitch_context_protects_close_up_from_demotion():
    """When ``has_pitch_context`` (stumps / crease / wicket / pitch)
    fires alongside a close-up framing, the v3.1 close-up demotion
    is bypassed and the frame stays DELIVERY_ACTION."""
    from eyes.chunker_v3 import label_frame, score_frame
    f = FrameInput(
        ts=5.0, prod_cam="closeup", prod_phase="release",
        v2_broadcast_tag="LIVE", v2_class="other",
        open_desc=(
            "Close-up shot of a single cricket player from behind, "
            "stumps visible just over the shoulder."),
    )
    ev = score_frame(f)
    assert ev["is_single_player_focus"] is True
    assert ev["has_pitch_context"] is True
    assert label_frame(f, ev) == "DELIVERY_ACTION"


def test_v31_close_up_does_not_demote_live_cam_delivery():
    """Live-cam (bowlers_end) frames with delivery_b satisfied stay
    DELIVERY even if open_desc reads as a close-up — production tags
    already vet live."""
    from eyes.chunker_v3 import label_frame, score_frame
    f = FrameInput(
        ts=5.0, prod_cam="bowlers_end", prod_phase="release",
        v2_broadcast_tag="LIVE", v2_class="action",
        open_desc=(
            "Close-up shot of the batter at the crease; bowler running "
            "in, stumps visible."),
    )
    ev = score_frame(f)
    assert label_frame(f, ev) == "DELIVERY_ACTION"


def test_v31_wide_field_signal_recognised():
    """``has_wide_field`` fires for both literal wide-field text and
    multi-actor mentions."""
    from eyes.chunker_v3 import score_frame
    f1 = FrameInput(
        ts=0.0, prod_cam="other", prod_phase="other",
        v2_broadcast_tag="LIVE", v2_class="other",
        open_desc="A wide field view of the cricket pitch.")
    assert score_frame(f1)["has_wide_field"] is True

    f2 = FrameInput(
        ts=0.0, prod_cam="other", prod_phase="other",
        v2_broadcast_tag="LIVE", v2_class="other",
        open_desc=(
            "The bowler is running in toward the batter; the "
            "wicketkeeper is crouched behind the stumps."))
    assert score_frame(f2)["has_wide_field"] is True

    f3 = FrameInput(
        ts=0.0, prod_cam="other", prod_phase="other",
        v2_broadcast_tag="LIVE", v2_class="other",
        open_desc="A spectator drinks water in the stand.")
    assert score_frame(f3)["has_wide_field"] is False


def test_v31_helpers_19_clip_per_clip_acceptance():
    """Per-clip precision check using the v3.2 confidence helpers
    (``score_frame_confidence`` + ``cluster_rejection_v31``) on the
    cached 96b39448 sidecar windows.  This is a per-clip ACCEPT/REJECT
    spot-check on the rejection helpers; the streaming end-to-end
    pipeline assertion lives in
    ``test_continuous_chunker.py:test_19_clip_live_continuous_chunker_precision_and_recall``.
    Asserts ≥85% precision.
    """
    import json
    from eyes.chunker_v3 import (
        cluster_rejection_v31, score_frame_confidence,
    )

    sidecar = (Path(__file__).resolve().parents[2]
               / "logs" / "openscout-96b39448.jsonl")
    auto_dir = (Path(__file__).resolve().parents[1]
                / "logs" / "deliveries" / "96b39448" / "auto")
    if not sidecar.exists() or not auto_dir.exists():
        pytest.skip("19-clip fixture not available in this checkout")

    truth = {
        "d001": "real",   "d002": "real",   "d003": "real",
        "d004": "trunc",  "d005": "pre",    "d006": "post",
        "d007": "trunc",  "d008": "replay", "d009": "replay",
        "d010": "replay", "d011": "replay", "d012": "replay",
        "d013": "real",   "d014": "real",   "d015": "replay",
        "d016": "replay", "d017": "replay", "d018": "real",
        "d019": "real",
    }
    entries = []
    with open(sidecar) as fp:
        for line in fp:
            try:
                r = json.loads(line)
                if r.get("ts"):
                    entries.append(r)
            except Exception:
                pass
    entries.sort(key=lambda r: r["ts"])

    def decide(frame_records: list[dict]) -> str:
        if not frame_records:
            return "REJECT"
        scored = [{
            "ts": float(r.get("ts", 0.0)),
            "desc": r.get("raw_text") or "",
            "score": score_frame_confidence(
                r.get("raw_text") or "",
                r.get("v2_broadcast_tag") or ""),
        } for r in frame_records]
        # Need at least 1 strong DELIVERY frame to even consider ACCEPT.
        if not any(f["score"]["DELIVERY"] >= 0.5 for f in scored):
            return "REJECT"
        verdict = cluster_rejection_v31(scored, 0, len(scored) - 1)
        return "REJECT" if verdict is not None else "ACCEPT"

    accepted_truth: list[str] = []
    rejected_real: list[str] = []
    n_real = 0
    for clip_id, t in sorted(truth.items()):
        meta_path = auto_dir / clip_id / "metadata.json"
        if not meta_path.exists():
            continue
        m = json.loads(meta_path.read_text())
        s, e = m["start_ts"], m["end_ts"]
        frame_records = [r for r in entries
                         if s - 0.5 <= r["ts"] <= e + 0.5]
        verdict = decide(frame_records)
        is_real = t in ("real", "trunc")
        if is_real:
            n_real += 1
        if verdict == "ACCEPT":
            accepted_truth.append(t)
        elif is_real:
            rejected_real.append(clip_id)

    n_accepted = len(accepted_truth)
    n_tp = sum(1 for t in accepted_truth if t in ("real", "trunc"))
    precision = (100.0 * n_tp / n_accepted) if n_accepted else 0.0
    recall = (100.0 * n_tp / n_real) if n_real else 0.0
    assert precision >= 85.0, (
        f"v3.1 helper precision regressed: {precision:.1f}% < 85%, "
        f"accepted={accepted_truth}, "
        f"rejected_real={rejected_real}, recall={recall:.1f}%")


# ── Speed-overlay isolation classifier ────────────────────────────


def test_speed_with_score_detects_score_context():
    from eyes.chunker_v3 import has_speed_alone, has_speed_with_score
    desc = "143 kph DC 145/3 (12.4)"
    assert has_speed_with_score(desc) is True
    assert has_speed_alone(desc) is False


def test_speed_with_score_detects_batter_stat_context():
    from eyes.chunker_v3 import has_speed_alone, has_speed_with_score
    desc = "BUMRAH 142 kph KOHLI 67(45) leg side"
    assert has_speed_with_score(desc) is True
    assert has_speed_alone(desc) is False


def test_speed_with_score_detects_team_abbrev_context():
    from eyes.chunker_v3 import has_speed_alone, has_speed_with_score
    desc = "138 kph CSK leading the over"
    assert has_speed_with_score(desc) is True
    assert has_speed_alone(desc) is False


def test_speed_alone_detects_isolated_speed_overlay():
    from eyes.chunker_v3 import has_speed_alone, has_speed_with_score
    desc = "Slow motion replay overlay 142 kph"
    assert has_speed_alone(desc) is True
    assert has_speed_with_score(desc) is False


def test_speed_helpers_silent_without_speed_text():
    from eyes.chunker_v3 import has_speed_alone, has_speed_with_score
    desc = "The bowler runs in toward the batter at the crease"
    assert has_speed_alone(desc) is False
    assert has_speed_with_score(desc) is False


def test_score_frame_confidence_speed_with_score_boosts_delivery():
    from eyes.chunker_v3 import score_frame_confidence
    base = score_frame_confidence(
        "Wide field view of the cricket pitch with players positioned"
        " on the field; the batter is at the crease, stumps visible",
        "")
    boosted = score_frame_confidence(
        "Wide field view of the cricket pitch with players positioned"
        " on the field; the batter is at the crease, stumps visible."
        " 143 kph DC 145/3 (12.4)",
        "")
    assert boosted["DELIVERY"] > base["DELIVERY"]
    assert boosted["DELIVERY"] >= base["DELIVERY"] + 0.4


def test_score_frame_confidence_speed_alone_boosts_replay():
    from eyes.chunker_v3 import score_frame_confidence
    s = score_frame_confidence(
        "An isolated frame showing 142 kph in white text on black", "")
    assert s["REPLAY"] >= 0.5


def test_v31_post_action_evidence_set_but_not_label_override():
    """``has_post_action`` is captured as evidence so the cluster
    filter can use it, but it does NOT promote the per-frame label
    to REPLAY (would shrink v3 windows on live-cam frames)."""
    from eyes.chunker_v3 import label_frame, score_frame
    f = FrameInput(
        ts=5.0, prod_cam="bowlers_end", prod_phase="between_play",
        v2_broadcast_tag="LIVE", v2_class="other",
        open_desc=(
            "post-action moment as the bowler walks back; minimal "
            "graphical overlays."),
    )
    ev = score_frame(f)
    assert ev["has_post_action"] is True
    assert label_frame(f, ev) != "REPLAY"
