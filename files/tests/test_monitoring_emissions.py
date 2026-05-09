"""Live-monitoring v1 — emit-format unit tests.

Validates the five aggregate tag emitters in
``files/monitoring_emitters.py`` produce the log shapes documented in
the task spec, and that ``OPEN-SCOUT-LOOP-STATS`` is suppressed when
``OPENSCOUT_DECOUPLED=0``.  Log-only — no integration with the
pipeline.

Run from repo root:
    pytest files/tests/test_monitoring_emissions.py -q
"""
from __future__ import annotations

import logging
import os
import sys
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest  # noqa: E402

from monitoring_emitters import (  # noqa: E402
    ChunkerV3StatsCounters,
    MatchSummaryInputs,
    OpenScoutLoopStatsCounters,
    OpenScoutStatsCounters,
    RetroCounters,
    SessionConfigInputs,
    check_consecutive_none_alarm,
    check_tpm_alarm,
    check_v3_fallback_alarm,
    emit_chunker_v3_stats,
    emit_match_summary,
    emit_open_scout_loop_stats,
    emit_open_scout_stats,
    emit_retro_summary,
    format_chunker_v3_stats,
    format_match_summary,
    format_open_scout_loop_stats,
    format_open_scout_stats,
    format_retro_summary,
    format_session_config,
    verify_clip_write,
)


@pytest.fixture
def caplog_info(caplog):
    caplog.set_level(logging.INFO, logger="monitoring_emitters")
    return caplog


# ── 1. RETRO-SUMMARY ───────────────────────────────────────────────


def test_retro_summary_format_and_emit(caplog_info):
    c = RetroCounters(
        events_seen=120, spans_committed=110, spans_fallback=8)
    msg = format_retro_summary(2, c)
    assert msg.startswith("[RETRO-SUMMARY] ")
    assert "innings=2" in msg
    assert "events_seen=120" in msg
    assert "spans_committed=110" in msg
    assert "spans_fallback=8" in msg
    # 110/120 = 91.67%
    assert "hit_rate=91.7%" in msg

    emit_retro_summary(2, c)
    assert any("[RETRO-SUMMARY]" in r.getMessage()
               for r in caplog_info.records)


def test_retro_summary_zero_events_is_zero_pct():
    c = RetroCounters()
    msg = format_retro_summary(1, c)
    assert "hit_rate=0.0%" in msg
    assert "events_seen=0" in msg


# ── 2. OPEN-SCOUT-STATS ────────────────────────────────────────────


def test_open_scout_stats_format_and_reset(caplog_info):
    c = OpenScoutStatsCounters(
        class_counts=Counter({
            "action": 12, "replay": 5, "umpire": 1, "ad": 0, "other": 2}),
        latencies_ms=[100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
        inter_call_gaps_s=[1.0, 1.2, 0.9, 1.1],
    )
    msg = format_open_scout_stats(c, window_min=5)
    assert msg.startswith("[OPEN-SCOUT-STATS] ")
    assert "window_min=5" in msg
    assert "action=12" in msg
    assert "replay=5" in msg
    assert "umpire=1" in msg
    assert "ad=0" in msg
    assert "other=2" in msg
    assert "total=20" in msg
    # p50 of 100..1000 with linear interp = 550
    assert "lat_p50_ms=550" in msg
    # cadence median of [0.9,1.0,1.1,1.2] = 1.05
    assert "cadence_median_s=1.05" in msg

    emit_open_scout_stats(c, window_min=5)
    assert any("[OPEN-SCOUT-STATS]" in r.getMessage()
               for r in caplog_info.records)
    # emit() resets the counter window-locally.
    assert sum(c.class_counts.values()) == 0
    assert c.latencies_ms == []
    assert c.inter_call_gaps_s == []


# ── 3. OPEN-SCOUT-LOOP-STATS ───────────────────────────────────────


def test_open_scout_loop_stats_skipped_when_decoupled_off(
        caplog_info, monkeypatch):
    monkeypatch.setenv("OPENSCOUT_DECOUPLED", "0")
    c = OpenScoutLoopStatsCounters()
    c.note_call(gap_s=1.0, tokens=400)
    c.note_429()
    c.note_slot_miss()
    out = emit_open_scout_loop_stats(
        c, window_s=30, target_s=1.0, util_tpm_pct=42.0,
        derate_active=False)
    assert out is None
    assert not any("[OPEN-SCOUT-LOOP-STATS]" in r.getMessage()
                   for r in caplog_info.records)


def test_open_scout_loop_stats_emit_full_format(
        caplog_info, monkeypatch):
    monkeypatch.setenv("OPENSCOUT_DECOUPLED", "1")
    c = OpenScoutLoopStatsCounters()
    for gap, tok in [(1.0, 400), (1.2, 410), (1.1, 405), (1.3, 420),
                     (1.0, 415)]:
        c.note_call(gap_s=gap, tokens=tok)
    c.note_429()
    c.note_429()
    c.note_slot_miss()
    msg = format_open_scout_loop_stats(
        c, window_s=30, target_s=1.0, util_tpm_pct=72.5,
        derate_active=True)
    assert msg.startswith("[OPEN-SCOUT-LOOP-STATS] ")
    assert "window_s=30" in msg
    assert "calls=5" in msg
    assert "target_s=1.00" in msg
    assert "util_tpm_pct=72.5" in msg
    assert "derate_active=1" in msg
    assert "frame_slot_miss=1" in msg
    assert "e429_count=2" in msg
    out = emit_open_scout_loop_stats(
        c, window_s=30, target_s=1.0, util_tpm_pct=72.5,
        derate_active=True)
    assert out is not None
    # Reset on emit.
    assert c.tokens == []
    assert c.e429_count == 0
    assert c.frame_slot_miss == 0


# ── 4. CHUNKER-V3-STATS ────────────────────────────────────────────


def test_chunker_v3_stats_format_and_emit(caplog_info):
    c = ChunkerV3StatsCounters()
    # 4 events: 3 v3-resolved, 1 none. 1 of the resolved drove cut.
    c.note_outcome(v3_bounds=(10.0, 14.0),
                   legacy_bounds=(10.5, 14.5),
                   fallback_used=False, drove_cut=True)
    c.note_outcome(v3_bounds=(20.0, 25.0),
                   legacy_bounds=(20.0, 25.0),
                   fallback_used=False, drove_cut=False)
    c.note_outcome(v3_bounds=(30.0, 36.0),
                   legacy_bounds=None,
                   fallback_used=False, drove_cut=False)
    c.note_outcome(v3_bounds=None, legacy_bounds=None,
                   fallback_used=True, drove_cut=False)
    msg = format_chunker_v3_stats(c, window_min=5)
    assert msg.startswith("[CHUNKER-V3-STATS] ")
    assert "resolved=3" in msg
    assert "none=1" in msg
    assert "fallback=1" in msg
    # mean dur of 4,5,6 = 5.0
    assert "mean_dur_s=5.00" in msg
    # 1 drove cut out of 4 total = 25.0%
    assert "drove_cut_pct=25.0" in msg

    emit_chunker_v3_stats(c, window_min=5)
    assert any("[CHUNKER-V3-STATS]" in r.getMessage()
               for r in caplog_info.records)
    # Reset on emit.
    assert c.resolved_count == 0
    assert c.none_count == 0


# ── 5. MATCH-SUMMARY ───────────────────────────────────────────────


def test_match_summary_combines_sub_counters(caplog_info):
    retro = RetroCounters(events_seen=240, spans_committed=230,
                          spans_fallback=12)
    s = MatchSummaryInputs(
        duration_min=215.4,
        retro=retro,
        scout_class_totals=Counter({
            "action": 800, "replay": 200, "umpire": 50, "ad": 30,
            "other": 20}),
        scout_lat_ms_all=[300] * 100 + [900] * 100,
        loop_gaps_s_all=[1.0, 1.1, 1.2, 1.0, 0.9, 1.05],
        loop_e429_total=7,
        v3_resolved=180,
        v3_none=60,
        v3_fallback=15,
        v3_drove_cut=120,
    )
    msg = format_match_summary(s)
    assert msg.startswith("[MATCH-SUMMARY] ")
    assert "duration_min=215.4" in msg
    assert "events_seen=240" in msg
    assert "spans_committed=230" in msg
    # 230/240 = 95.83%
    assert "hit_rate=95.8%" in msg
    assert "scout_calls=1100" in msg
    # 800/1100 = 72.73
    assert "scout_action_pct=72.7" in msg
    assert "loop_e429_total=7" in msg
    assert "v3_resolved=180" in msg
    assert "v3_none=60" in msg
    assert "v3_fallback=15" in msg
    # 120 / (180+60) = 50.0%
    assert "v3_drove_cut_pct=50.0" in msg

    emit_match_summary(s)
    assert any("[MATCH-SUMMARY]" in r.getMessage()
               for r in caplog_info.records)


def test_match_summary_handles_empty_inputs():
    """Zero scout calls and zero v3 events must not divide by zero."""
    s = MatchSummaryInputs(
        duration_min=0.0,
        retro=RetroCounters(),
        scout_class_totals=Counter(),
        scout_lat_ms_all=[],
        loop_gaps_s_all=[],
        loop_e429_total=0,
        v3_resolved=0, v3_none=0, v3_fallback=0, v3_drove_cut=0,
    )
    msg = format_match_summary(s)
    assert "scout_action_pct=0.0" in msg
    assert "v3_drove_cut_pct=0.0" in msg
    assert "scout_lat_p50_ms=0" in msg


# ── 6. SESSION-CONFIG ──────────────────────────────────────────────


def test_session_config_emit_format():
    s = SessionConfigInputs(
        session_id="abc12345",
        use_v3_chunker=True,
        use_v3_chunker_spans=False,
        v3_fallback_enabled=True,
        v3_fallback_lookback_s=6.0,
        v3_fallback_forward_s=4.0,
        openscout_decoupled=True,
        openscout_target_s=1.0,
        openscout_tpm_budget=240000,
        use_open_scout=True,
        use_open_scout_spans=False,
    )
    msg = format_session_config(s)
    assert msg.startswith("[SESSION-CONFIG] ")
    assert "session_id=abc12345" in msg
    assert "use_v3_chunker=1" in msg
    assert "use_v3_chunker_spans=0" in msg
    assert "v3_fallback_enabled=1" in msg
    assert "v3_fallback_lookback_s=6.0" in msg
    assert "v3_fallback_forward_s=4.0" in msg
    assert "openscout_decoupled=1" in msg
    assert "openscout_target_s=1.00" in msg
    assert "openscout_tpm_budget=240000" in msg
    assert "use_open_scout=1" in msg
    assert "use_open_scout_spans=0" in msg


# ── 7. ALARM-V3-FALLBACK-HIGH (boundary) ──────────────────────────


def test_alarm_v3_fallback_fires_at_31_pct():
    """31/100 = 31% > 30% threshold → alarm fires.
    30/100 = 30% (boundary, not strictly greater) → no alarm."""
    c = ChunkerV3StatsCounters(
        resolved_count=69, none_count=0, fallback_count=31)
    msg = check_v3_fallback_alarm(c, window_min=5)
    assert msg is not None
    assert msg.startswith("[ALARM-V3-FALLBACK-HIGH] ")
    assert "fallback_count=31" in msg
    assert "total_events=69" in msg
    # 31/69 = 44.93%
    assert "pct=44.9%" in msg
    assert "USE_V3_CHUNKER_SPANS=0" in msg

    # Boundary: exactly 30/100 = 30.0% must NOT fire (strictly > thr).
    c_at = ChunkerV3StatsCounters(
        resolved_count=100, none_count=0, fallback_count=30)
    assert check_v3_fallback_alarm(c_at, window_min=5) is None

    # 31/100 = 31.0% > 30% → fires.
    c_just_over = ChunkerV3StatsCounters(
        resolved_count=100, none_count=0, fallback_count=31)
    assert check_v3_fallback_alarm(c_just_over, window_min=5) is not None

    # Empty counter: no alarm, no division-by-zero.
    assert check_v3_fallback_alarm(
        ChunkerV3StatsCounters(), window_min=5) is None


# ── 8. ALARM-OPEN-SCOUT-TPM-HIGH ───────────────────────────────────


def test_alarm_tpm_high_fires_at_81_pct():
    """81% > 80% threshold → alarm fires.
    80% (boundary) → no alarm."""
    msg = check_tpm_alarm(
        util_tpm_pct=81.0, median_gap_s=1.05,
        derate_active=True, window_s=30)
    assert msg is not None
    assert msg.startswith("[ALARM-OPEN-SCOUT-TPM-HIGH] ")
    assert "window_s=30" in msg
    assert "util_tpm_pct=81.0" in msg
    assert "median_gap_s=1.05" in msg
    assert "derate_active=1" in msg
    assert "auto-derate" in msg

    # Boundary: exactly 80% must NOT fire.
    assert check_tpm_alarm(
        util_tpm_pct=80.0, median_gap_s=1.0,
        derate_active=False, window_s=30) is None


# ── 9. ALARM-V3-CONSECUTIVE-NONE (multiples of 5) ─────────────────


def test_alarm_consecutive_none_fires_at_5_and_10():
    """Fires at 5, 10, 15; silent at 1-4, 6-9, 11-14."""
    # Below threshold — silent.
    for n in (0, 1, 2, 3, 4):
        assert check_consecutive_none_alarm(n, last_event_ts=12.0) is None
    # 5 — fires.
    msg5 = check_consecutive_none_alarm(5, last_event_ts=12.34)
    assert msg5 is not None
    assert msg5.startswith("[ALARM-V3-CONSECUTIVE-NONE] ")
    assert "consecutive_none=5" in msg5
    assert "last_event_ts=12.34" in msg5

    # 6-9 silent.
    for n in (6, 7, 8, 9):
        assert check_consecutive_none_alarm(n, last_event_ts=15.0) is None

    # 10 fires again.
    msg10 = check_consecutive_none_alarm(10, last_event_ts=20.0)
    assert msg10 is not None
    assert "consecutive_none=10" in msg10

    # 11-14 silent, 15 fires.
    for n in (11, 12, 13, 14):
        assert check_consecutive_none_alarm(n, last_event_ts=25.0) is None
    assert check_consecutive_none_alarm(
        15, last_event_ts=30.0) is not None


# ── 10. CLIP-WRITE verification ────────────────────────────────────


def test_clip_write_ok_emits_when_file_valid(caplog_info, tmp_path):
    """Real file with size > 1KB → CLIP-WRITE-OK with bytes field."""
    mp4 = tmp_path / "delivery_window.mp4"
    mp4.write_bytes(b"\0" * 200_000)  # 200KB sentinel
    msg = verify_clip_write(
        mp4_path=mp4, delivery_id=42,
        window_start=10.0, window_end=22.5,
        source="v3_chunker_span",
    )
    assert msg.startswith("[CLIP-WRITE-OK] ")
    assert "delivery_id=42" in msg
    assert "bytes=200000" in msg
    assert "duration_s=12.50" in msg
    assert "source=v3_chunker_span" in msg
    assert "span=(10.00,22.50)" in msg
    assert any("[CLIP-WRITE-OK]" in r.getMessage()
               for r in caplog_info.records)


def test_clip_write_fail_missing_file(caplog_info, tmp_path):
    """No file written → CLIP-WRITE-FAIL with reason=missing."""
    mp4 = tmp_path / "delivery_window.mp4"  # not created
    msg = verify_clip_write(
        mp4_path=mp4, delivery_id=7,
        window_start=5.0, window_end=15.0,
        source="retrospective_span",
    )
    assert msg.startswith("[CLIP-WRITE-FAIL] ")
    assert "delivery_id=7" in msg
    assert "reason=missing" in msg
    assert "source=retrospective_span" in msg
    assert "span=(5.00,15.00)" in msg
    assert any("[CLIP-WRITE-FAIL]" in r.getMessage()
               and r.levelname == "WARNING"
               for r in caplog_info.records)


def test_clip_write_fail_too_small(caplog_info, tmp_path):
    """File present but only 512 bytes → reason=too_small_512_bytes."""
    mp4 = tmp_path / "delivery_window.mp4"
    mp4.write_bytes(b"\0" * 512)
    msg = verify_clip_write(
        mp4_path=mp4, delivery_id="d013",
        window_start=20.0, window_end=32.0,
        source="fallback_pre_event_window",
    )
    assert msg.startswith("[CLIP-WRITE-FAIL] ")
    assert "delivery_id=d013" in msg
    assert "reason=too_small_512_bytes" in msg
    assert "source=fallback_pre_event_window" in msg
    assert "span=(20.00,32.00)" in msg
