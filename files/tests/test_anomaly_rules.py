"""Trace-and-Detect v1 tests.

Covers:
- Anomaly rules P1, P2, P3, P4 (advisory), P5, P6, P7, P8, P9 — synthetic
  frame fixtures replay each rule's trigger + each rule's suppression
  cases.
- ``UIMirror`` parity vs the client `useMatchSocket.deepMerge` semantics
  documented at scorecard-ui/app/hooks/useMatchSocket.ts:L5-L36.
- Trace schema header round-trip (writer → reader; mismatched version
  is rejected).
- ``DecisionLogHandler`` auto-promotion of ``[TAG]`` log lines.

Run from repo root:
    pytest files/tests/test_anomaly_rules.py -q
"""

from __future__ import annotations

import json
import logging
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest  # noqa: E402

import trace_emitter  # noqa: E402
from anomaly_rules import (  # noqa: E402
    AnalyzerState,
    THRESHOLDS,
    evaluate,
    rule_p1,
    rule_p2,
    rule_p3,
    rule_p4_advisory,
    rule_p5,
    rule_p6,
    rule_p7,
    rule_p8,
    rule_p9,
    update_innings_tracking,
)
from trace_emitter import (  # noqa: E402
    DecisionLogHandler,
    DecisionRecorder,
    TraceWriter,
    UIMirror,
    compute_ui_diff,
    deep_merge_ui,
    derive_pipeline_mode,
    ModeContext,
    read_trace,
)


# ── Fixtures ──────────────────────────────────────────────────────


def mkframe(*, frame, mode="WARM", innings=1, score=10, wickets=1,
            overs="2.3", striker="A", non_striker="B",
            bowler="X", bowler_runs=12, bowler_wkts=0, bowler_overs="2.3",
            this_over=("1", "0", "1"), at_crease=None, ball_event=None,
            decisions=None, scorer_proposed=None,
            committed=None, extras_full=None, scout_phase="active_play",
            scout_cam="wide", force_processed=False,
            extractor_score=None, extractor_wickets=None):
    if at_crease is None:
        at_crease = [
            {"name": striker, "runs": 5, "balls": 6, "is_striker": True,
             "status": "batting"},
            {"name": non_striker, "runs": 3, "balls": 6, "is_striker": False,
             "status": "batting"},
        ]
    rec = {
        "frame": frame,
        "ts_wall": 1700000000.0 + frame,
        "frame_type": "SCOREBOARD",
        "session": "testsess",
        "pipeline": {"mode": mode, "innings": innings},
        "capture": {"force_processed": bool(force_processed)},
        "scout": {"phase": scout_phase, "cam": scout_cam,
                  "raw_text_120": "STRIP: ..."},
        "extractor": {"score": extractor_score if extractor_score is not None
                      else score,
                      "wickets": extractor_wickets if extractor_wickets is not None
                      else wickets,
                      "match_overs": overs,
                      "batters": [{"name": striker}, {"name": non_striker}],
                      "bowler": {"name": bowler}},
        "scorer": {
            "proposed": scorer_proposed or {},
            "decisions": decisions or [],
            "committed_changes": committed or [],
        },
        "ball_event": ball_event or {},
        "ui_after": {
            "scorecard": {"score": score, "wickets": wickets,
                          "overs": overs, "striker": striker,
                          "non_striker": non_striker,
                          "current_bowler": bowler, "run_rate": 5.0},
            "batting_card_at_crease": at_crease,
            "bowling_current": {"name": bowler, "runs": bowler_runs,
                                "wickets": bowler_wkts,
                                "overs": bowler_overs},
            "this_over": list(this_over),
            "extras_total": (extras_full or {}).get("total", 0),
            "partnership_current": None,
            "fow_count": wickets,
            "innings": innings,
        },
        "lat_ms": {"vision": 800, "extract": 1100, "scorer": 900,
                   "total": 3000},
    }
    if extras_full is not None:
        rec["ui_extras_full"] = extras_full
    return rec


# ── P1 — batter persistence after wicket ──────────────────────────


def test_p1_fires_when_batters_unchanged_after_wicket():
    state = AnalyzerState()
    window = []
    # Wicket fires
    w = mkframe(frame=100, ball_event={"type": "WICKET"},
                striker="JAISWAL", non_striker="JUREL",
                at_crease=[
                    {"name": "JAISWAL", "is_striker": True,
                     "status": "batting", "runs": 10},
                    {"name": "JUREL", "is_striker": False,
                     "status": "batting", "runs": 18}])
    window.append(w)
    update_innings_tracking(state, w)
    rule_p1(state, w, window)
    fired = []
    for f in range(101, 140):
        # at_crease unchanged (the bug)
        rec = mkframe(frame=f, striker="JAISWAL", non_striker="JUREL",
                      at_crease=[
                          {"name": "JAISWAL", "is_striker": True,
                           "status": "batting", "runs": 10},
                          {"name": "JUREL", "is_striker": False,
                           "status": "batting", "runs": 18}],
                      decisions=[
                          {"tag": "GUARD-BATTER-NOT-IN-EXTRACTOR",
                           "name": "PARAG"}])
        window.append(rec)
        fired.extend(rule_p1(state, rec, window))
    ids = [a.id for a in fired]
    assert "P1" in ids, "P1 must fire when at-crease is unchanged"
    severities = {a.severity for a in fired if a.id == "P1"}
    assert severities & {"warn", "error"}


def test_p1_clears_when_batters_change():
    state = AnalyzerState()
    window = []
    w = mkframe(frame=100, ball_event={"type": "WICKET"},
                at_crease=[{"name": "A", "is_striker": True,
                            "status": "batting"}])
    window.append(w)
    rule_p1(state, w, window)
    # Next frame, new batter walks in.
    rec = mkframe(frame=105, at_crease=[{"name": "C", "is_striker": True,
                                         "status": "batting"}])
    window.append(rec)
    out = rule_p1(state, rec, window)
    assert out == []
    assert state.p1_open is False


def test_p1_suppressed_during_cold_start():
    state = AnalyzerState()
    window = []
    w = mkframe(frame=100, mode="COLD_START",
                ball_event={"type": "WICKET"})
    window.append(w)
    out = rule_p1(state, w, window)
    assert out == []


# ── P2 — score regression ────────────────────────────────────────


def test_p2_fires_on_regression():
    state = AnalyzerState()
    window = []
    a = mkframe(frame=10, score=87)
    b = mkframe(frame=11, score=82, committed=["score→82"])
    window.extend([a, b])
    out = rule_p2(state, b, window)
    assert len(out) == 1 and out[0].id == "P2" and out[0].severity == "error"
    assert out[0].evidence["delta"] == -5


def test_p2_does_not_fire_on_increase():
    state = AnalyzerState()
    window = [mkframe(frame=10, score=87), mkframe(frame=11, score=89)]
    assert rule_p2(state, window[-1], window) == []


def test_p2_skips_innings_change():
    state = AnalyzerState()
    window = [mkframe(frame=10, score=200, innings=1),
              mkframe(frame=11, score=0, innings=2)]
    update_innings_tracking(state, window[1])
    assert rule_p2(state, window[-1], window) == []


# ── P3 — stale bowler ─────────────────────────────────────────────


def test_p3_fires_after_two_overs_unchanged():
    state = AnalyzerState()
    window = []
    rec = mkframe(frame=10, bowler="X", overs="0.0")
    window.append(rec)
    rule_p3(state, rec, window)
    # Walk through 3 overs with same bowler.
    fired = []
    for over in range(0, 4):
        for ball in range(0, 6):
            f = 100 + over * 10 + ball
            rec = mkframe(frame=f, bowler="X",
                          overs=f"{over}.{ball}")
            window.append(rec)
            fired.extend(rule_p3(state, rec, window))
    assert any(a.id == "P3" for a in fired)


def test_p3_clears_on_bowler_change():
    state = AnalyzerState()
    window = []
    rule_p3(state, mkframe(frame=1, bowler="X"), window)
    rec = mkframe(frame=2, bowler="Y")
    window.append(rec)
    out = rule_p3(state, rec, window)
    assert out == []
    assert state.last_bowler_name == "Y"


def test_p3_evidence_uses_correct_bowler_tags():
    state = AnalyzerState()
    window = []
    rec0 = mkframe(frame=10, bowler="X", overs="0.0")
    window.append(rec0)
    rule_p3(state, rec0, window)
    fired = []
    for over in range(0, 4):
        for ball in range(0, 6):
            f = 100 + over * 10 + ball
            decisions = [
                {"tag": "BOWLER", "raw_message": "[BOWLER] confirmed"},
                {"tag": "BOWLER-OVERRIDE", "raw_message": "X → Y"},
                {"tag": "BOWLER-CONSENSUS-INCONSISTENT",
                 "raw_message": "refusing flip"},
                {"tag": "BOWLER-LEAD", "raw_message": "runs vs score"},
            ]
            rec = mkframe(frame=f, bowler="X", overs=f"{over}.{ball}",
                          decisions=decisions)
            window.append(rec)
            fired.extend(rule_p3(state, rec, window))
    p3 = [a for a in fired if a.id == "P3"]
    assert p3, "P3 must fire on stale-bowler"
    evidence_tags: set[str] = set()
    for a in p3:
        for d in a.evidence.get("bowler_decisions_in_window", []):
            evidence_tags.add(d["tag"])
    assert "BOWLER" in evidence_tags
    assert "BOWLER-OVERRIDE" in evidence_tags
    assert "BOWLER-CONSENSUS-INCONSISTENT" in evidence_tags
    assert "BOWLER-LEAD" not in evidence_tags
    for a in p3:
        assert "BOWLER-LEAD" not in a.verdict
        assert "BOWLER-OVERRIDE" in a.verdict


def test_p3_evidence_empty_when_no_bowler_decisions():
    state = AnalyzerState()
    window = []
    rec0 = mkframe(frame=10, bowler="X", overs="0.0")
    window.append(rec0)
    rule_p3(state, rec0, window)
    fired = []
    for over in range(0, 4):
        for ball in range(0, 6):
            f = 100 + over * 10 + ball
            rec = mkframe(frame=f, bowler="X", overs=f"{over}.{ball}")
            window.append(rec)
            fired.extend(rule_p3(state, rec, window))
    p3 = [a for a in fired if a.id == "P3"]
    assert p3
    for a in p3:
        assert a.evidence["bowler_decisions_in_window"] == []


# ── P4 — partnership math (advisory) ──────────────────────────────


def test_p4_advisory_fires_on_sustained_mismatch():
    state = AnalyzerState()
    window = []
    crease = [{"name": "A", "runs": 30, "is_striker": True,
               "status": "batting"},
              {"name": "B", "runs": 20, "is_striker": False,
               "status": "batting"}]
    fired = []
    for i in range(20):
        rec = mkframe(frame=200 + i, wickets=0, at_crease=crease)
        rec["ui_after"]["partnership_current"] = {
            "batters": ["A", "B"], "runs": 100, "balls": 30}
        rec["ui_after"]["extras_total"] = 0
        window.append(rec)
        fired.extend(rule_p4_advisory(state, rec, window))
    assert any(a.id == "P4" and a.severity == "advisory" for a in fired)


def test_p4_no_fire_when_extras_explains_delta():
    """866ce150 frames 179-184: partnership=11, batters=4, extras=7."""
    state = AnalyzerState()
    window = []
    crease = [{"name": "QdK", "runs": 2, "is_striker": True,
               "status": "batting"},
              {"name": "RH", "runs": 2, "is_striker": False,
               "status": "batting"}]
    fired = []
    for i in range(20):
        rec = mkframe(frame=300 + i, wickets=0, at_crease=crease)
        rec["ui_after"]["partnership_current"] = {
            "batters": ["QdK", "RH"], "runs": 11, "balls": 16}
        rec["ui_after"]["extras_total"] = 7
        window.append(rec)
        fired.extend(rule_p4_advisory(state, rec, window))
    assert not any(a.id == "P4" for a in fired)


def test_p4_fires_on_real_divergence():
    state = AnalyzerState()
    window = []
    crease = [{"name": "A", "runs": 2, "is_striker": True,
               "status": "batting"},
              {"name": "B", "runs": 2, "is_striker": False,
               "status": "batting"}]
    fired = []
    for i in range(20):
        rec = mkframe(frame=400 + i, wickets=0, at_crease=crease)
        rec["ui_after"]["partnership_current"] = {
            "batters": ["A", "B"], "runs": 15, "balls": 16}
        rec["ui_after"]["extras_total"] = 7
        window.append(rec)
        fired.extend(rule_p4_advisory(state, rec, window))
    p4 = [a for a in fired if a.id == "P4"]
    assert p4 and p4[0].severity == "advisory"
    ev = p4[0].evidence
    assert ev["partnership_runs"] == 15
    assert ev["sum_batter_runs"] == 4
    assert ev["extras_total"] == 7
    assert ev["expected_partnership"] == 11
    assert ev["delta"] == 4


def test_p4_skips_post_wicket():
    """Post-wicket: rule defers until SM exposes per-pship extras snapshot."""
    state = AnalyzerState()
    window = []
    crease = [{"name": "C", "runs": 0, "is_striker": True,
               "status": "batting"},
              {"name": "D", "runs": 0, "is_striker": False,
               "status": "batting"}]
    fired = []
    for i in range(20):
        rec = mkframe(frame=500 + i, wickets=1, at_crease=crease)
        rec["ui_after"]["partnership_current"] = {
            "batters": ["C", "D"], "runs": 5, "balls": 4}
        rec["ui_after"]["extras_total"] = 8
        window.append(rec)
        fired.extend(rule_p4_advisory(state, rec, window))
    assert not any(a.id == "P4" for a in fired)


# ── P5 — phantom wicket ───────────────────────────────────────────


def test_p5_fires_when_wickets_jump_no_event():
    state = AnalyzerState()
    window = [mkframe(frame=10, wickets=2),
              mkframe(frame=11, wickets=3, extractor_wickets=3)]
    out = rule_p5(state, window[-1], window)
    assert len(out) == 1 and out[0].id == "P5" and out[0].severity == "error"


def test_p5_silent_when_wicket_event_present():
    state = AnalyzerState()
    a = mkframe(frame=10, wickets=2)
    b = mkframe(frame=11, wickets=3, ball_event={"type": "WICKET"})
    window = [a, b]
    assert rule_p5(state, b, window) == []


# ── P6 — extras inconsistency ────────────────────────────────────


def test_p6_fires_when_components_mismatch_total():
    state = AnalyzerState()
    rec = mkframe(frame=10, extras_full={
        "wides": 3, "no_balls": 1, "byes": 0, "leg_byes": 2,
        "penalties": 0, "total": 10})
    out = rule_p6(state, rec, [rec])
    assert len(out) == 1 and out[0].id == "P6"
    assert out[0].evidence["delta"] == -4


def test_p6_silent_when_within_tolerance():
    state = AnalyzerState()
    rec = mkframe(frame=10, extras_full={
        "wides": 3, "no_balls": 1, "byes": 0, "leg_byes": 2,
        "penalties": 0, "total": 6})
    assert rule_p6(state, rec, [rec]) == []


# ── P7 — innings score reset ─────────────────────────────────────


def test_p7_fires_on_score_reset_within_innings():
    state = AnalyzerState()
    window = [mkframe(frame=10, score=87, wickets=4),
              mkframe(frame=11, score=0, wickets=0)]
    out = rule_p7(state, window[-1], window)
    assert len(out) == 1 and out[0].id == "P7" and out[0].severity == "error"


def test_p7_silent_on_innings_change():
    state = AnalyzerState()
    window = [mkframe(frame=10, score=200, innings=1),
              mkframe(frame=11, score=0, innings=2)]
    update_innings_tracking(state, window[1])
    assert rule_p7(state, window[-1], window) == []


# ── P8 — this_over ball count mismatch ───────────────────────────


def test_p8_fires_on_sustained_mismatch():
    state = AnalyzerState()
    window = []
    fired = []
    for i in range(5):
        rec = mkframe(frame=10 + i, overs="3.4", this_over=("1",))
        window.append(rec)
        fired.extend(rule_p8(state, rec, window))
    assert any(a.id == "P8" for a in fired)


def test_p8_silent_when_aligned():
    state = AnalyzerState()
    rec = mkframe(frame=10, overs="3.3", this_over=("1", "0", "1"))
    assert rule_p8(state, rec, [rec]) == []


# ── P9 — stuck UI fields ─────────────────────────────────────────


def test_p9_fires_on_stuck_score():
    state = AnalyzerState()
    window = []
    fired = []
    for i in range(THRESHOLDS["P9_STALE_RECORDS_SCORE"] + 5):
        rec = mkframe(frame=i, score=42, this_over=("1",))
        window.append(rec)
        fired.extend(rule_p9(state, rec, window))
    assert any(a.id == "P9" and a.evidence["field"] == "score"
               for a in fired)


def test_p9_silent_during_ad_window():
    state = AnalyzerState()
    window = []
    fired = []
    for i in range(40):
        rec = mkframe(frame=i, score=42, this_over=("1",), scout_cam="ad")
        window.append(rec)
        fired.extend(rule_p9(state, rec, window))
    assert fired == []


# ── UIMirror parity vs client deepMerge semantics ─────────────────


def test_uimirror_scalar_null_preserves_previous():
    """useMatchSocket: null/empty incoming keeps prev (L29-L33)."""
    out = deep_merge_ui({"a": 5}, {"a": None})
    assert out["a"] == 5
    out2 = deep_merge_ui({"a": "x"}, {"a": ""})
    assert out2["a"] == "x"


def test_uimirror_array_replace_when_nonempty():
    out = deep_merge_ui({"x": [1, 2]}, {"x": [3]})
    assert out["x"] == [3]


def test_uimirror_empty_array_keeps_prev_nonempty():
    out = deep_merge_ui({"x": [1, 2]}, {"x": []})
    assert out["x"] == [1, 2]


def test_uimirror_innings_history_replace_wholesale():
    prev = {"innings_history": [{"innings": 1, "score": 200}]}
    nxt = {"innings_history": []}
    out = deep_merge_ui(prev, nxt)
    assert out["innings_history"] == []


def test_uimirror_nested_dicts_deepmerge():
    prev = {"scorecard": {"score": 5, "wickets": 0}}
    nxt = {"scorecard": {"score": 7}}
    out = deep_merge_ui(prev, nxt)
    assert out["scorecard"] == {"score": 7, "wickets": 0}


def test_uimirror_sequence_of_payloads_matches_typescript_semantics():
    """Replay 50+ small payloads through the mirror; assert end state
    matches a hand-traced expected post-merge state."""
    mirror = UIMirror()
    payloads = [
        {"scorecard": {"score": 0, "wickets": 0}},
        {"scorecard": {"score": 4}, "this_over": ["4"]},
        {"scorecard": {"score": 6}, "this_over": ["4", "2"]},
        {"scorecard": {"score": None}},  # null preserves
        {"batting_card": [{"name": "A", "runs": 6, "is_striker": True,
                           "status": "batting"}]},
        {"batting_card": []},  # empty preserves
        {"innings_history": [{"innings": 1, "score": 200}]},
        {"innings_history": []},  # wholesale clear
        {"this_over": []},  # empty preserves
        {"scorecard": {"current_bowler": "X"}},
    ]
    for p in payloads:
        mirror.apply(p)
    snap = mirror.snapshot_full()
    assert snap["scorecard"]["score"] == 6
    assert snap["scorecard"]["wickets"] == 0
    assert snap["scorecard"]["current_bowler"] == "X"
    assert snap["this_over"] == ["4", "2"]
    assert snap["batting_card"] == [{"name": "A", "runs": 6,
                                     "is_striker": True,
                                     "status": "batting"}]
    assert snap["innings_history"] == []


def test_compute_ui_diff_reports_changed_paths_only():
    before = {"scorecard": {"score": 34, "wickets": 2},
              "this_over": ["1", "4"]}
    after = {"scorecard": {"score": 35, "wickets": 2},
             "this_over": ["1", "4", "1"]}
    diffs = compute_ui_diff(before, after)
    paths = {d["path"] for d in diffs}
    assert "scorecard.score" in paths
    assert "this_over" in paths
    assert "scorecard.wickets" not in paths


# ── Schema header round-trip ──────────────────────────────────────


def test_writer_emits_schema_header_and_reader_validates(tmp_path):
    trace_emitter.reset_singletons()
    w = TraceWriter(session_id="abc12345", trace_dir=str(tmp_path))
    w.write_record({"frame": 1, "ts_wall": 1700000000.0})
    w.write_record({"frame": 2, "ts_wall": 1700000001.0})
    w.close()
    header, records = read_trace(w.path)
    assert header["_schema_version"] == 1
    assert header["session"] == "abc12345"
    assert len(records) == 2 and records[0]["frame"] == 1


def test_reader_rejects_mismatched_schema(tmp_path):
    p = tmp_path / "bad.jsonl"
    with open(p, "w") as fp:
        fp.write(json.dumps({"_schema_version": 999, "session": "x",
                             "started_ts_wall": 0.0}) + "\n")
        fp.write(json.dumps({"frame": 1}) + "\n")
    with pytest.raises(ValueError, match="schema mismatch"):
        read_trace(str(p))


def test_reader_rejects_missing_header(tmp_path):
    p = tmp_path / "noheader.jsonl"
    with open(p, "w") as fp:
        fp.write(json.dumps({"frame": 1}) + "\n")
    with pytest.raises(ValueError, match="missing schema header"):
        read_trace(str(p))


# ── Decision log handler auto-promotion ───────────────────────────


def test_decision_log_handler_promotes_known_tag():
    rec = DecisionRecorder()
    rec.begin_frame(123)
    handler = DecisionLogHandler(rec)
    test_logger = logging.getLogger("trace_test_logger")
    test_logger.handlers = [handler]
    test_logger.setLevel(logging.DEBUG)
    test_logger.propagate = False
    test_logger.info("[POISON-RECAL] streak=5 Δ=8")
    test_logger.info("nothing tagged here")
    test_logger.info("[GRAPHIC-FILTER] info_panel_keyword='wickets'")
    out = rec.drain()
    tags = [d["tag"] for d in out]
    assert "POISON-RECAL" in tags
    assert "GRAPHIC-FILTER" in tags
    assert all(d.get("_auto") for d in out)


def test_pipeline_mode_helper():
    ctx = ModeContext(cold_start_gate_open=False, current_innings=1,
                      last_innings_handoff_frame=None)
    assert derive_pipeline_mode(ctx, 5) == "COLD_START"
    ctx = ModeContext(cold_start_gate_open=True, current_innings=2,
                      last_innings_handoff_frame=100)
    assert derive_pipeline_mode(ctx, 130) == "INNINGS_HANDOFF"
    assert derive_pipeline_mode(ctx, 300) == "WARM"


# ── End-to-end: evaluate over a synthesized trace ─────────────────


def test_evaluate_runs_all_rules_without_crashing():
    records = []
    for i in range(50):
        records.append(mkframe(frame=i, score=10 + i // 5))
    fired, by_frame = evaluate(records)
    # We don't assert specific anomalies — just that the walk doesn't
    # raise and returns the correct shapes.
    assert isinstance(fired, list)
    assert isinstance(by_frame, dict)
