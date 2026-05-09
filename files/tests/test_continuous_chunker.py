"""ContinuousChunker — confidence-walk streaming detector tests.

Covers the v3.2 confidence pipeline: per-frame
:func:`score_frame_confidence`, anchor + sandwich correction,
:func:`walk_chunk` inertia, :func:`find_clusters`, and the cluster-
level rejection rules (structural sandwich + v3.1 in-cluster).  Also
verifies the streaming gate (frames must arrive after a cluster's end
before the cluster is emitted).

The 19-clip cached fixture validation is at the bottom — runs the live
:class:`ContinuousChunker` ingest path end-to-end and asserts ≥60 %
precision and ≥95 % recall against the user-labeled truth.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pytest

from eyes.continuous_chunker import (
    ContinuousChunker,
    DeliveryDetectedEvent,
)


# ── Frame helpers — confidence-pipeline-aware ──────────────────────


def _delivery_frame() -> dict:
    """Strong delivery: ``mid-action`` + multi-actor wide framing +
    pitch context.  Scores DELIVERY ≈ 0.85, anchors above 0.50."""
    return {
        "prod_cam": "bowlers_end",
        "prod_phase": "release",
        "v2_broadcast_tag": "LIVE",
        "v2_class": "action",
        "open_desc": (
            "The bowler is mid-action releasing the ball; "
            "the batter is at the crease, stumps visible, "
            "wide field view of the cricket pitch with players."
        ),
    }


def _non_delivery_frame() -> dict:
    """Filler frame — no action, no replay signal.  Scores NON_DELIVERY
    via the others_max < 0.30 fallback."""
    return {
        "prod_cam": "wide",
        "prod_phase": "between_play",
        "v2_broadcast_tag": "LIVE",
        "v2_class": "static",
        "open_desc": (
            "An empty cricket field with the scoreboard visible "
            "and stadium lights on."
        ),
    }


def _replay_frame() -> dict:
    """Replay overlay — ``slow motion`` adds 0.70 to REPLAY and hard-
    disqualifies DELIVERY."""
    return {
        "prod_cam": "wide",
        "prod_phase": "replay",
        "v2_broadcast_tag": "REPLAY",
        "v2_class": "replay",
        "open_desc": (
            "Slow motion replay of the previous shot from a low angle."
        ),
    }


def _crowd_frame() -> dict:
    """Crowd-prominent — disqualifies delivery via cricket invariant."""
    return {
        "prod_cam": "wide",
        "prod_phase": "between_play",
        "v2_broadcast_tag": "LIVE",
        "v2_class": "other",
        "open_desc": (
            "A large crowd in the background watches the bowler "
            "running in toward the batter."
        ),
    }


def _delivery_frame_with_speed_score() -> dict:
    """Strong delivery frame whose Scout description ALSO carries
    the speed + score / overs broadcast overlay."""
    base = _delivery_frame()
    base = dict(base)
    base["open_desc"] = (
        base["open_desc"]
        + " Speed shown: 143 kph DC 145/3 (12.4) on the corner overlay."
    )
    return base


def _replay_frame_speed_alone() -> dict:
    """Frame containing speed text ONLY (no score, overs, batter
    stats, team abbreviation) — bare replay overlay signal."""
    return {
        "prod_cam": "wide",
        "prod_phase": "between_play",
        "v2_broadcast_tag": "LIVE",
        "v2_class": "other",
        "open_desc": (
            "The frame shows an isolated speed indicator reading "
            "142 kph in white block text against a darkened backdrop."
        ),
    }


def _close_up_frame() -> dict:
    """Single-player close-up — used for cluster-rejection tests."""
    return {
        "prod_cam": "closeup",
        "prod_phase": "between_play",
        "v2_broadcast_tag": "LIVE",
        "v2_class": "other",
        "open_desc": (
            "Close-up shot of a single cricket player from behind."
        ),
    }


def _feed(chunker: ContinuousChunker,
          stream: Iterable[tuple[float, dict]]
          ) -> list[DeliveryDetectedEvent]:
    events: list[DeliveryDetectedEvent] = []
    for ts, fields in stream:
        ev = chunker.ingest(ts, **fields)
        if ev is not None:
            events.append(ev)
    return events


def _filler_tail(start_ts: float, count: int = 6,
                 step: float = 1.0) -> list[tuple[float, dict]]:
    """Trailing non-delivery frames so the stability gate can release
    a cluster (walk lookahead is up to 3 frames)."""
    return [(start_ts + i * step, _non_delivery_frame())
            for i in range(count)]


# ── Basic smoke tests ──────────────────────────────────────────────


def test_no_event_without_delivery_anchor():
    cc = ContinuousChunker(
        min_clip_duration_s=1.0, min_event_gap_s=0.0,
        min_confidence=0.0)
    events = _feed(cc, [(t, _non_delivery_frame()) for t in range(8)])
    assert events == []


def test_state_property_is_idle_compat_shim():
    cc = ContinuousChunker(min_confidence=0.0)
    assert cc.state == "IDLE"
    cc.ingest(0.0, **_delivery_frame())
    assert cc.state == "IDLE"


def test_replay_frame_does_not_count_as_delivery():
    cc = ContinuousChunker(min_confidence=0.0)
    events = _feed(cc, [
        (0.0, _replay_frame()),
        (1.0, _replay_frame()),
        (2.0, _replay_frame()),
    ] + _filler_tail(3.0))
    assert events == []


# ── Walk-with-inertia / cluster formation ──────────────────────────


def test_single_strong_anchor_emits_after_stability_margin():
    cc = ContinuousChunker(
        min_clip_duration_s=1.0,
        min_event_gap_s=0.0,
        min_confidence=0.5,
    )
    stream = [(0.0, _delivery_frame())] + _filler_tail(1.0)
    events = _feed(cc, stream)
    assert len(events) == 1
    assert events[0].confidence_score >= 0.5


def test_walk_inertia_extends_through_supporting_neighbour():
    """Two consecutive strong DELIVERY frames build cluster strength
    (anchor 0.85 + 0.20 per neighbour) and emit one event."""
    cc = ContinuousChunker(
        min_clip_duration_s=1.0,
        min_event_gap_s=0.0,
        min_confidence=0.5,
    )
    stream = [
        (0.0, _delivery_frame()),
        (1.0, _delivery_frame()),
        (2.0, _delivery_frame()),
    ] + _filler_tail(3.0)
    events = _feed(cc, stream)
    assert len(events) == 1
    assert events[0].confidence_score > 0.85


def test_cluster_does_not_emit_until_stability_margin_received():
    """Until at least 3 frames have arrived after the walk's end, the
    cluster is held back to give walk_chunk's lookahead a chance to
    extend it."""
    cc = ContinuousChunker(
        min_clip_duration_s=1.0,
        min_event_gap_s=0.0,
        min_confidence=0.5,
    )
    # Two delivery frames and only one trailing non-delivery — not
    # enough margin for the gate to release.
    cc.ingest(0.0, **_delivery_frame())
    cc.ingest(1.0, **_delivery_frame())
    cc.ingest(2.0, **_non_delivery_frame())
    assert cc.stats()["events_emitted"] == 0
    # Adding more trailing frames lets the cluster close.
    cc.ingest(3.0, **_non_delivery_frame())
    cc.ingest(4.0, **_non_delivery_frame())
    cc.ingest(5.0, **_non_delivery_frame())
    assert cc.stats()["events_emitted"] >= 1


def test_lone_low_score_anchor_does_not_form_cluster():
    """A single weak NON_DELIVERY-leaning frame between deliveries
    will be sandwich-corrected; a stream of pure non-delivery never
    forms a cluster."""
    cc = ContinuousChunker(
        min_clip_duration_s=1.0,
        min_event_gap_s=0.0,
        min_confidence=0.5,
    )
    events = _feed(cc, [
        (0.0, _non_delivery_frame()),
        (1.0, _non_delivery_frame()),
        (2.0, _non_delivery_frame()),
        (3.0, _non_delivery_frame()),
        (4.0, _non_delivery_frame()),
    ])
    assert events == []


# ── Duration clamping + dedup ──────────────────────────────────────


def test_min_duration_clamping_extends_short_clusters():
    cc = ContinuousChunker(
        min_clip_duration_s=4.0,
        max_clip_duration_s=20.0,
        min_event_gap_s=0.0,
        min_confidence=0.5,
    )
    stream = [
        (0.0, _delivery_frame()),
        (0.5, _delivery_frame()),
    ] + _filler_tail(1.0)
    events = _feed(cc, stream)
    assert len(events) == 1
    assert events[0].duration_s >= 4.0


def test_max_duration_clamping_caps_long_clusters():
    cc = ContinuousChunker(
        min_clip_duration_s=1.0,
        max_clip_duration_s=8.0,
        min_event_gap_s=0.0,
        min_confidence=0.5,
    )
    stream: list[tuple[float, dict]] = [
        (float(i), _delivery_frame()) for i in range(20)
    ] + _filler_tail(20.0)
    events = _feed(cc, stream)
    assert len(events) >= 1
    for ev in events:
        assert ev.duration_s <= 8.0 + 1e-6


def test_dedup_within_min_event_gap():
    cc = ContinuousChunker(
        min_clip_duration_s=1.0,
        min_event_gap_s=20.0,
        min_confidence=0.5,
    )
    stream: list[tuple[float, dict]] = [
        (0.0, _delivery_frame()), (1.0, _delivery_frame()),
        (2.0, _delivery_frame()),
    ] + _filler_tail(3.0) + [
        (8.0, _delivery_frame()), (9.0, _delivery_frame()),
        (10.0, _delivery_frame()),
    ] + _filler_tail(11.0)
    events = _feed(cc, stream)
    assert len(events) == 1
    assert cc.stats()["events_suppressed_dedup"] >= 1


# ── Confidence floor (cluster walk strength) ───────────────────────


def test_threshold_configurable_lets_weaker_walks_through():
    """Lowering ``min_confidence`` admits clusters whose walk strength
    falls below the default 0.65 floor."""
    weak_stream = [
        (0.0, _delivery_frame()),
    ] + _filler_tail(1.0)

    strict = ContinuousChunker(
        min_clip_duration_s=1.0,
        min_event_gap_s=0.0,
        min_confidence=2.0,  # well above any practical S
    )
    assert _feed(strict, weak_stream) == []
    assert strict.stats()["events_suppressed_low_confidence"] >= 1

    permissive = ContinuousChunker(
        min_clip_duration_s=1.0,
        min_event_gap_s=0.0,
        min_confidence=0.0,
    )
    events = _feed(permissive, weak_stream)
    assert len(events) == 1


# ── Cluster-level rejection (structural sandwich + v3.1) ──────────


def test_v31_replay_overlay_in_cluster_rejects():
    """A replay-overlay frame in the cluster window invalidates the
    whole cluster (cluster_rejection_v31 rule 1)."""
    cc = ContinuousChunker(
        min_clip_duration_s=1.0,
        min_event_gap_s=0.0,
        min_confidence=0.0,
    )
    events = _feed(cc, [
        (0.0, _delivery_frame()),
        (1.0, _delivery_frame()),
        (2.0, _replay_frame()),
        (3.0, _delivery_frame()),
    ] + _filler_tail(4.0))
    assert events == []
    assert cc.stats()["events_suppressed_v31"] >= 1


def test_v31_crowd_sandwich_rejects_single_delivery():
    """One DELIVERY anchor adjacent to crowd-prominent frames is
    rejected by the v3.1 crowd-sandwich rule."""
    cc = ContinuousChunker(
        min_clip_duration_s=1.0,
        min_event_gap_s=0.0,
        min_confidence=0.0,
    )
    events = _feed(cc, [
        (0.0, _crowd_frame()),
        (1.0, _delivery_frame()),
        (2.0, _crowd_frame()),
    ] + _filler_tail(3.0))
    assert events == []


def test_speed_with_score_confirms_cluster_bypassing_v31():
    """A speed-with-score frame inside the cluster CONFIRMs the
    cluster as a real delivery and bypasses v3.1 in-cluster
    rejection."""
    cc = ContinuousChunker(
        min_clip_duration_s=1.0,
        min_event_gap_s=0.0,
        min_confidence=0.0,
    )
    # Crowd-prominent frames + 1 delivery would normally trigger v3.1
    # crowd-sandwich; a speed-with-score frame in the window flips it.
    events = _feed(cc, [
        (0.0, _crowd_frame()),
        (1.0, _delivery_frame_with_speed_score()),
        (2.0, _crowd_frame()),
    ] + _filler_tail(3.0))
    assert len(events) == 1
    assert cc.stats()["events_confirmed_speed_with_score"] >= 1


def test_speed_alone_majority_rejects_cluster():
    """A cluster whose speed-bearing frames are dominated by
    speed-alone (no speed-with-score companion) is rejected even when
    v3.1 would have admitted it."""
    cc = ContinuousChunker(
        min_clip_duration_s=1.0,
        min_event_gap_s=0.0,
        min_confidence=0.0,
    )
    events = _feed(cc, [
        (0.0, _delivery_frame()),
        (1.0, _delivery_frame()),
        (2.0, _replay_frame_speed_alone()),
        (3.0, _replay_frame_speed_alone()),
    ] + _filler_tail(4.0))
    assert events == []
    assert cc.stats()["events_suppressed_speed_alone"] >= 1


def test_clean_strong_cluster_passes_all_filters():
    cc = ContinuousChunker(
        min_clip_duration_s=1.0,
        min_event_gap_s=0.0,
        min_confidence=0.0,
    )
    events = _feed(cc, [
        (0.0, _delivery_frame()),
        (1.0, _delivery_frame()),
        (2.0, _delivery_frame()),
        (3.0, _delivery_frame()),
    ] + _filler_tail(4.0))
    assert len(events) == 1
    s = cc.stats()
    assert s["events_suppressed_v31"] == 0
    assert s["events_suppressed_cluster_sandwich"] == 0


# ── Event sink + label payload ─────────────────────────────────────


def test_event_sink_callback_invoked():
    captured: list[DeliveryDetectedEvent] = []
    cc = ContinuousChunker(
        min_clip_duration_s=1.0,
        min_event_gap_s=0.0,
        min_confidence=0.0,
        event_sink=captured.append,
    )
    _feed(cc, [
        (0.0, _delivery_frame()),
        (1.0, _delivery_frame()),
    ] + _filler_tail(2.0))
    assert len(captured) == 1


def test_labels_field_uses_confidence_label_names():
    cc = ContinuousChunker(
        min_clip_duration_s=1.0,
        min_event_gap_s=0.0,
        min_confidence=0.0,
    )
    events = _feed(cc, [
        (0.0, _delivery_frame()),
        (1.0, _delivery_frame()),
    ] + _filler_tail(2.0))
    assert len(events) == 1
    labels = events[0].labels
    assert all("ts" in r and "label" in r for r in labels)
    seen = {r["label"] for r in labels}
    # v3.2 confidence pipeline labels are the CONF_LABELS set.
    assert seen.issubset({"DELIVERY", "REPLAY", "AD",
                          "DRS", "UMPIRE", "NON_DELIVERY"})
    assert "DELIVERY" in seen


# ── 19-clip live-pipeline precision/recall validation ─────────────


def test_19_clip_live_continuous_chunker_precision_and_recall():
    """Run the LIVE :class:`ContinuousChunker` end-to-end on the
    cached 96b39448 sidecar and verify against user-labeled truth.

    Acceptance per task memo:
      * precision ≥ 60 %
      * recall    ≥ 95 % on the 9 real/trunc clips

    Skips when the sidecar / metadata fixture isn't checked in.
    """
    import json

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

    captured: list[DeliveryDetectedEvent] = []
    cc = ContinuousChunker(
        min_clip_duration_s=1.0,
        min_event_gap_s=4.0,
        min_confidence=0.65,
        event_sink=captured.append,
    )
    for r in entries:
        cc.ingest(
            r["ts"],
            v2_broadcast_tag=r.get("v2_broadcast_tag", ""),
            open_desc=r.get("raw_text") or "",
        )

    # For each labeled clip, ACCEPT if any emitted event overlaps it.
    accepted_truth: list[str] = []
    rejected_real: list[str] = []
    n_real = 0
    for clip_id, t in sorted(truth.items()):
        meta_path = auto_dir / clip_id / "metadata.json"
        if not meta_path.exists():
            continue
        m = json.loads(meta_path.read_text())
        s, e = m["start_ts"], m["end_ts"]
        is_real = t in ("real", "trunc")
        if is_real:
            n_real += 1
        accepted = any(
            ev.start_ts <= e and ev.end_ts >= s for ev in captured)
        if accepted:
            accepted_truth.append(t)
        elif is_real:
            rejected_real.append(clip_id)

    n_accepted = len(accepted_truth)
    n_tp = sum(1 for t in accepted_truth if t in ("real", "trunc"))
    precision = (100.0 * n_tp / n_accepted) if n_accepted else 0.0
    recall = (100.0 * n_tp / n_real) if n_real else 0.0

    # Speed isolation lifts precision from the v3.2-pre-speed
    # baseline (≈64 %) by adding the speed-with-score CONFIRM and
    # speed-alone REJECT overrides.  The remaining FPs (d005, d010,
    # d016 in the 96b39448 fixture) carry no speed text at all and
    # require a second-stage filter (motion / Gemini) to reject —
    # explicit out-of-scope per the task memo.
    assert recall >= 95.0, (
        f"19-clip recall {recall:.1f}% < 95% — rejected reals: "
        f"{rejected_real}, total events emitted: {len(captured)}")
    assert precision >= 75.0, (
        f"19-clip precision {precision:.1f}% < 75% — accepted: "
        f"{accepted_truth}, total events emitted: {len(captured)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
