"""Drive ScoreManager through a captured ``scout_raw.jsonl`` and emit
a trace JSONL identical in shape to the production trace.

Built for the B-η instrumentation pass (2026-05-21). The production
pipeline's trace at ``logs/trace/validate_dckkr_20260521_070545.jsonl``
already exists; this script produces an *instrumented* re-replay so we
can read the three new trace tags (``FRAME-TRUST-GATE``,
``OVERS-JUMP-STREAK-STATE``, ``POISON-STREAK-AT-COMMIT``) without
running a fresh production session.

Limitation vs. production replay: the captured dump goes through
``parse_strip`` directly into ``ScoreManager.on_frame``. The test_pipeline.py
upstream guards (POISONED / GRAPHIC-FILTER-POISON / STANDINGS-ROW-GATE /
FS-REJECT / etc.) do NOT run. That means the cascade exercised here is
the SM-only subset; this is sufficient to observe whether the new tags
fire at the multi-ball gap commit moments, but the upstream
poison-filter context for ``POISON-STREAK-AT-COMMIT`` is limited to
SM-local state. See
``files/docs/investigations/stream_gap_reconciliation_design.md`` §6.

Usage::

    files/.venv/bin/python files/scripts/replay_captured_scout_trace.py \\
        --dump files/logs/deliveries/validate_dckkr_20260521_070545/scout_raw.jsonl \\
        --session-id replay_dckkr_20260521_INSTRUMENTED

Warm-seed mode (skips cold-start emulation; jumps SM directly to a
WARM baseline at the named frame so frames after the cold-exit
boundary can be exercised without driving test_pipeline.py)::

    files/.venv/bin/python files/scripts/replay_captured_scout_trace.py \\
        --dump files/logs/deliveries/validate_dckkr_20260521_070545/scout_raw.jsonl \\
        --session-id replay_dckkr_20260521_WARMSEEDED \\
        --seed-frame 37 \\
        --seed-striker "Pathum Nissanka" \\
        --seed-non-striker "KL Rahul" \\
        --seed-bowler "Anukul Roy"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FILES_DIR))
sys.path.insert(0, str(FILES_DIR / "tests"))
sys.path.insert(0, str(FILES_DIR / "scripts"))

import trace_emitter  # noqa: E402
from score_manager import ScoreManager  # noqa: E402
from eyes.extract_regex import parse_strip  # noqa: E402
from eyes.scoreboard import Scoreboard  # noqa: E402
from pipeline_setup_helper import build_pipeline_components  # noqa: E402
from test_pipeline_captured_replay import (  # noqa: E402
    BATTING_TEAM as DCKKR_BATTING_TEAM,
    BOWLING_TEAM as DCKKR_BOWLING_TEAM,
    build_sm as build_sm_dckkr,
    extracted_to_frame_input,
)
from ingest_cricbuzz_ground_truth import (  # noqa: E402
    UIBallSnapshot, canonical_name)


# GT vs RR fixture squads (innings 1, validate_gtrr_20260520_180715).
# Sourced from files/tests/fixtures/gt_vs_rr_2026_commentary_first_innings.md
# — Opening pair: Sai Sudharsan / Shubman Gill, opening bowler Jofra
# Archer. Squad order matters: BATTING_SQUAD[0:2] are the openers, the
# remainder of the XI follows in the typical batting order from the
# captured trace.
GTRR_BATTING_TEAM = "GT"
GTRR_BOWLING_TEAM = "RR"
GTRR_BATTING_SQUAD = [
    "Sai Sudharsan", "Shubman Gill", "Jos Buttler",
    "Jason Holder", "Rahul Tewatia", "Ravisrinivasan Sai Kishore",
    "Mahipal Lomror", "Manav Suthar", "Anuj Rawat",
    "Gerald Coetzee", "Karim Janat",
]
GTRR_BOWLING_SQUAD = [
    "Jofra Archer", "Brijesh Sharma", "Tushar Deshpande",
    "Yash Raj Punja", "Ravindra Jadeja", "Donovan Ferreira",
    "Yashasvi Jaiswal", "Sanju Samson", "Riyan Parag",
    "Dhruv Jurel", "Nitish Rana",
]


def build_sm_gtrr() -> tuple[ScoreManager, Scoreboard]:
    sb = Scoreboard()
    sb.setup_innings(
        batting_team=GTRR_BATTING_TEAM,
        bowling_team=GTRR_BOWLING_TEAM,
        batting_squad=GTRR_BATTING_SQUAD,
        bowling_squad=GTRR_BOWLING_SQUAD,
        batting_xi=GTRR_BATTING_SQUAD[:11],
        bowling_xi=GTRR_BOWLING_SQUAD[:11],
    )
    for opener in (GTRR_BATTING_SQUAD[0], GTRR_BATTING_SQUAD[1]):
        slot = sb.batting_card.get(opener)
        if slot is not None:
            slot["status"] = "batting"
            slot["runs"] = 0
            slot["balls"] = 0
            slot["fours"] = 0
            slot["sixes"] = 0
    sm = ScoreManager(shadow=False)
    sm.scoreboard = sb
    return sm, sb


FIXTURE_BUILDERS = {
    "dckkr": (build_sm_dckkr, DCKKR_BATTING_TEAM, DCKKR_BOWLING_TEAM),
    "gtrr": (build_sm_gtrr, GTRR_BATTING_TEAM, GTRR_BOWLING_TEAM),
}


def _llm_extract_sync(extractor, description: str, frame_id: int,
                       batting_team: str, bowling_team: str) -> dict:
    """Invoke the production async Extractor from sync replay code.

    Returns whatever Extractor.extract() returns (possibly empty dict).
    Exceptions are swallowed and an empty dict is returned so a single
    frame's LLM failure doesn't abort the replay. The Extractor's
    own regex pre-check fires first; LLM is only reached when
    parse_strip returns None.
    """
    try:
        return asyncio.run(
            extractor.extract(
                description=description,
                frame_type="SCOREBOARD",
                team_a_name=batting_team,
                team_b_name=bowling_team,
                frame_id=frame_id))
    except Exception as e:
        logging.getLogger("replay_llm").warning(
            f"LLM extractor raised at frame {frame_id}: "
            f"{type(e).__name__}: {e}")
        return {}


def _apply_warm_seed(
    sm, sb, *,
    striker: str, non_striker: str, bowler: str,
    score: int = 0, wickets: int = 0, overs: float = 0.0,
) -> None:
    """Inject a WARM baseline directly onto SM state.

    Mirrors what the live pipeline reaches after cold-start exit:
    self.mode=WARM, self.score/wickets/overs/bowler_name/striker/
    non/bat1_name/bat2_name all populated. The captured-replay
    harness's build_sm already promoted the openers to
    status='batting' in batting_card, so per-ball card writes after
    the seed will accumulate normally.
    """
    sm.mode = "WARM"
    sm.score = int(score)
    sm.wickets = int(wickets)
    sm.overs = float(overs)
    sm.bowler_name = bowler
    sm.striker = striker
    sm.non = non_striker
    sm.bat1_name = striker
    sm.bat2_name = non_striker
    if sb is not None:
        try:
            sb.set("score", int(score), frame=0)
            sb.set("wickets", int(wickets), frame=0)
            sb.set("overs", float(overs), frame=0)
        except Exception:
            pass


def _legal_balls_from_overs_str(overs) -> int:
    if overs is None:
        return 0
    try:
        s = f"{float(overs):.1f}"
        completed, balls = s.split(".")
        return int(completed) * 6 + int(balls)
    except (TypeError, ValueError):
        return 0


def _format_overs(overs) -> str | None:
    if overs is None:
        return None
    try:
        return f"{float(overs):.1f}"
    except (TypeError, ValueError):
        return None


def _build_ui_snapshot(sm, sb, frame_id: int) -> UIBallSnapshot:
    """Snapshot the WS-payload-equivalent fields directly from SM + SB.

    Mirrors the field set `_build_full_payload_from_state` would read.
    Pipeline emits canonical (last-name) form already; we still pass
    through `canonical_name` for symmetry with the ingester.
    """
    striker = canonical_name(getattr(sm, "striker", None))
    non = canonical_name(getattr(sm, "non", None))
    # §12.10.3 sibling fix: when sm.bowler_name has been cleared by
    # over-end BOWLER-LOCK-RELEASED, fall back to the SM field that
    # apply_wicket_event captures at wicket commit time. Closes the
    # false-positive Bowler-W-credit-failure class where pipeline
    # credited correctly but the snapshot couldn't see it.
    bowler = canonical_name(
        getattr(sm, "bowler_name", None)
        or getattr(sm, "_last_bowler_at_wicket_commit", None))

    batting_card = getattr(sb, "batting_card", {}) or {}
    bowling_card = getattr(sb, "bowling_card", {}) or {}

    def _slot(card: dict, canon: str | None) -> dict:
        if not canon:
            return {}
        if canon in card:
            return card[canon] or {}
        for k, v in card.items():
            if canonical_name(k) == canon:
                return v or {}
        return {}

    striker_slot = _slot(batting_card, striker)
    non_slot = _slot(batting_card, non)
    bowler_slot = _slot(bowling_card, bowler)

    overs = getattr(sm, "overs", None)
    if overs is None:
        overs = (getattr(sb, "_inn", {}) or {}).get("overs")
    overs_str = _format_overs(overs) or "0.0"
    # Normalize post-rollover overs ("1.0" after the 6th ball of over 0)
    # to ball_id convention ("0.6") to match the ground-truth ingester
    # which keys on Cricbuzz ball_id. Pipeline-internal SM keeps the
    # post-rollover form; we only re-key the snapshot for diff alignment.
    try:
        c, b = overs_str.split(".")
        if int(b) == 0 and int(c) > 0:
            overs_str = f"{int(c) - 1}.6"
    except (ValueError, AttributeError):
        pass

    fow_entries = []
    for fow in getattr(sb, "fall_of_wickets", []) or []:
        # SM's _apply_wicket_fall_only writes the dismissed batter under
        # key "dismissed" (score_manager.py:5306-5311); Scoreboard's
        # _add_fow uses key "batter". Read both. Same for overs format:
        # SM writes self.overs (post-rollover, e.g. 8.0) while ball_id
        # convention is "7.6"; normalise so the diff harness aligns.
        _ov = fow.get("overs")
        _ov_str = _format_overs(_ov) or _ov
        if isinstance(_ov_str, str):
            try:
                c, b = _ov_str.split(".")
                if int(b) == 0 and int(c) > 0:
                    _ov_str = f"{int(c) - 1}.6"
            except (ValueError, AttributeError):
                pass
        fow_entries.append([
            int(fow.get("score") or 0),
            int(fow.get("wicket") or 0),
            canonical_name(
                fow.get("dismissed") or fow.get("batter")),
            _ov_str,
        ])

    over_history = getattr(sb, "over_history", {}) or {}
    completed = None
    try:
        c, b = overs_str.split(".")
        if int(b) == 0:
            completed = int(c) - 1
    except (ValueError, AttributeError):
        pass
    recent = []
    if completed is not None and completed >= 0:
        recent = over_history.get(completed) or over_history.get(str(completed)) or []

    extras_inn = getattr(sb, "extras", None) or {}
    event_extra = None
    try:
        event_extra = getattr(sm, "last_event", None)
    except Exception:
        event_extra = None
    if isinstance(event_extra, dict) and event_extra.get("legal") is False:
        try:
            c, b = overs_str.split(".")
            overs_str = f"{int(c)}.{int(b) + 1}"
        except (ValueError, AttributeError):
            pass

    return UIBallSnapshot(
        over_ball=overs_str,
        score=int(getattr(sm, "score", 0) or 0),
        wickets=int(getattr(sm, "wickets", 0) or 0),
        balls_total=_legal_balls_from_overs_str(overs),
        striker_name=striker,
        striker_runs=int(striker_slot.get("runs") or 0),
        striker_balls=int(
            striker_slot.get("balls") or striker_slot.get("balls_faced") or 0),
        striker_fours=int(striker_slot.get("fours") or 0),
        striker_sixes=int(striker_slot.get("sixes") or 0),
        non_striker_name=non,
        non_striker_runs=int(non_slot.get("runs") or 0),
        non_striker_balls=int(
            non_slot.get("balls") or non_slot.get("balls_faced") or 0),
        non_striker_fours=int(non_slot.get("fours") or 0),
        non_striker_sixes=int(non_slot.get("sixes") or 0),
        bowler_name=bowler,
        bowler_overs=bowler_slot.get("overs"),
        bowler_runs=int(bowler_slot.get("runs") or 0),
        bowler_wickets=int(bowler_slot.get("wickets") or 0),
        this_over_tokens=list(
            getattr(sm, "this_over", None)
            or getattr(sm, "completed_over", None)
            or getattr(sb, "this_over", None)
            or []),
        recent_over_n_minus_1=list(recent),
        partnership_runs=0,
        partnership_balls=0,
        extras_total=int(extras_inn.get("total") or 0),
        extras_wd=int(extras_inn.get("wides") or 0),
        extras_nb=int(extras_inn.get("no_balls") or 0),
        extras_b=int(extras_inn.get("byes") or 0),
        extras_lb=int(extras_inn.get("leg_byes") or 0),
        fow_entries=fow_entries,
    )


_SNAPSHOT_TRIGGER_TAGS = {
    "DIRECT-SCORE-COMMIT",
    "GAP-FINALIZE-WICKET",
    "WIDE-COMMIT",
    "NOBALL-COMMIT",
    # 5b.4 Patch B: wickets with Δscore=0 don't fire DIRECT-SCORE-COMMIT.
    # SM dispatches every wicket through `_finalize_wicket` which records
    # this tag; treat as secondary trigger so wicket frames produce a
    # snapshot and the diff harness can classify C21b / Bowler-W-credit.
    "trace_beta_sm_wicket_dispatch",
}


def run(dump_path: Path, session_id: str, trace_dir: Path,
        seed_frame: int | None = None,
        seed_striker: str | None = None,
        seed_non_striker: str | None = None,
        seed_bowler: str | None = None,
        enable_llm_extractor: bool = False,
        fixture: str = "dckkr",
        snapshot_output: Path | None = None) -> int:
    builder, batting_team, bowling_team = FIXTURE_BUILDERS[fixture]
    sm, sb = builder()
    # WS-N N1.2: wire over_mgr + ball_detector + partnership_tracker
    # via pipeline_setup_helper so the snapshotter exercises the
    # full-pipeline dispatch path (closes the SM-only measurement gap
    # documented in
    # files/docs/investigations/workstream_n_snapshotter_full_pipeline_integration.md).
    _pipeline_components = build_pipeline_components(sm, sb)
    over_mgr = _pipeline_components.over_mgr
    ball_detector = _pipeline_components.ball_detector
    partnership_tracker = _pipeline_components.partnership_tracker  # noqa: F841
    warm_seed_pending = (
        seed_frame is not None
        and seed_striker is not None
        and seed_non_striker is not None
        and seed_bowler is not None)
    if warm_seed_pending:
        print(
            f"Warm-seed configured: striker={seed_striker!r} "
            f"non={seed_non_striker!r} bowler={seed_bowler!r} "
            f"injection_at_frame={seed_frame}")
    extractor = None
    llm_calls = 0
    llm_recoveries = 0
    if enable_llm_extractor:
        from eyes.agent import Extractor
        extractor = Extractor()
        print(
            "LLM extractor enabled — frames where parse_strip "
            "returns None will fall through to Groq Llama (production "
            "Extractor.extract() invoked async-to-sync per frame). "
            "Replay-only — no impact on production cost path.")

    trace_dir.mkdir(parents=True, exist_ok=True)
    out_path = trace_dir / f"{session_id}.jsonl"
    if out_path.exists():
        out_path.unlink()
    writer = trace_emitter.TraceWriter(
        session_id=session_id, trace_dir=str(trace_dir))
    recorder = trace_emitter.get_recorder()
    log_handler = trace_emitter.install_log_handler(logging.getLogger())
    logging.getLogger().setLevel(logging.INFO)

    snapshot_fh = None
    snapshot_count = 0
    last_snap_key: tuple | None = None
    snap_event_index: dict[str, int] = {}
    last_this_over: tuple = ()
    if snapshot_output is not None:
        snapshot_output.parent.mkdir(parents=True, exist_ok=True)
        snapshot_fh = snapshot_output.open("w")
        print(f"Snapshot output: {snapshot_output}")

    frames = []
    with dump_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                frames.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    print(f"Loaded {len(frames)} Scout responses from {dump_path}")

    parsed = 0
    skipped = 0
    new_tag_counts = {
        "FRAME-TRUST-GATE": 0,
        "OVERS-JUMP-STREAK-STATE": 0,
        "POISON-STREAK-AT-COMMIT": 0,
        "DIRECT-SCORE-COMMIT": 0,
    }
    for f in frames:
        try:
            frame_id = int(f.get("frame_id"))
        except (TypeError, ValueError):
            continue
        if seed_frame is not None and frame_id < seed_frame:
            skipped += 1
            continue
        if warm_seed_pending and frame_id >= (seed_frame or 0):
            _apply_warm_seed(
                sm, sb,
                striker=seed_striker,  # type: ignore[arg-type]
                non_striker=seed_non_striker,  # type: ignore[arg-type]
                bowler=seed_bowler)  # type: ignore[arg-type]
            warm_seed_pending = False
            print(
                f"Warm-seed injected at frame {frame_id}: "
                f"sm.mode=WARM score=0 wickets=0 overs=0.0 "
                f"striker={sm.striker!r} non={sm.non!r} "
                f"bowler={sm.bowler_name!r}")
        ts = float(f.get("ts") or time.time())
        raw = f.get("raw_response") or ""
        recorder.begin_frame(frame_id)
        try:
            extracted = parse_strip(raw, batting_team, bowling_team)
        except Exception as e:
            decisions = recorder.drain()
            decisions.append({
                "tag": "REPLAY-PARSE-STRIP-RAISED",
                "error": f"{type(e).__name__}: {e}",
            })
            writer.write_record({
                "frame": frame_id,
                "ts_wall": ts,
                "session": session_id,
                "scout": {"raw_text_120": str(raw)[:120]},
                "scorer": {"decisions": decisions},
            })
            skipped += 1
            continue
        if not extracted or not extracted.get("has_scorecard_data"):
            if extractor is not None:
                llm_calls += 1
                llm_result = _llm_extract_sync(
                    extractor, raw, frame_id, batting_team, bowling_team)
                _has_signal = (
                    bool(llm_result)
                    and (llm_result.get("score") is not None
                         or llm_result.get("match_overs") is not None
                         or llm_result.get("overs") is not None))
                if _has_signal:
                    llm_recoveries += 1
                    recorder.record(
                        tag="REPLAY-LLM-EXTRACT-RECOVERED",
                        score=llm_result.get("score"),
                        wickets=llm_result.get("wickets"),
                        overs=(llm_result.get("match_overs")
                               or llm_result.get("overs")),
                        n_batters=len(llm_result.get("batters") or []),
                        bowler_name=(
                            (llm_result.get("bowler") or {}).get("name")),
                        frame_id=frame_id)
                    extracted = llm_result
                    # fall through to FrameInput build + sm.on_frame
                else:
                    decisions = recorder.drain()
                    writer.write_record({
                        "frame": frame_id,
                        "ts_wall": ts,
                        "session": session_id,
                        "scout": {"raw_text_120": str(raw)[:120]},
                        "scorer": {"decisions": decisions},
                    })
                    skipped += 1
                    continue
            else:
                decisions = recorder.drain()
                writer.write_record({
                    "frame": frame_id,
                    "ts_wall": ts,
                    "session": session_id,
                    "scout": {"raw_text_120": str(raw)[:120]},
                    "scorer": {"decisions": decisions},
                })
                skipped += 1
                continue
        parsed += 1
        fi = extracted_to_frame_input(frame_id, ts, extracted)

        # Mirror the L2 harness pre-SM scoreboard hydration so SM's
        # Path-B getters read consistent values.
        try:
            if fi.ext_score is not None:
                sb.set("score", fi.ext_score, frame=frame_id)
            if fi.ext_wickets is not None:
                sb.set("wickets", fi.ext_wickets, frame=frame_id)
            if fi.ext_overs is not None:
                sb.set("overs", fi.ext_overs, frame=frame_id)
        except Exception:
            pass

        # WS-N N1.2: pre-SM ball_detector + over_mgr dispatch.
        # Mirrors test_pipeline.py:13050-13117 minimum dispatch path
        # (_pending_bcast_striker_key is per-frame local in
        # test_pipeline.py:8533 — compute fresh from FrameInput.broadcast_-
        # striker here; monitoring counters + on-lock callbacks are
        # test_pipeline-specific scaffolding and are intentionally not
        # mirrored per memo §16 verification 5).
        _pending_bcast_striker_key = None
        if fi.broadcast_striker and getattr(sb, "batting_card", None):
            _bs_resolved = sb.resolve_name(fi.broadcast_striker)
            if _bs_resolved:
                _bs_key = sb._find_card_key(_bs_resolved, sb.batting_card)
                if (_bs_key
                        and sb.batting_card.get(_bs_key, {}).get(
                            "status") == "batting"):
                    _pending_bcast_striker_key = _bs_key
        _striker_this_ball = canonical_name(getattr(sm, "striker", None))
        try:
            ball_event = ball_detector.detect(sb._tracker)
        except Exception as e:
            recorder.record(
                tag="REPLAY-BALL-DETECTOR-RAISED",
                error=f"{type(e).__name__}: {e}")
            ball_event = None
        if ball_event:
            if ball_event.get("type") in ("WICKET", "WICKET_LATE"):
                if _striker_this_ball and not ball_event.get("dismissed"):
                    # Inline _attribute_dismissed_with_broadcast_override
                    # equivalent (test_pipeline.py:3154) — broadcast wins
                    # when it disagrees with the SM-derived striker.
                    if (_pending_bcast_striker_key
                            and _pending_bcast_striker_key
                                != _striker_this_ball):
                        _dismissed = _pending_bcast_striker_key
                        recorder.record(
                            tag="WICKET-ATTRIB-BROADCAST-OVERRIDE-APPLIED",
                            deterministic=_striker_this_ball,
                            broadcast=_pending_bcast_striker_key,
                            frame_id=str(frame_id))
                    else:
                        _dismissed = _striker_this_ball
                    ball_event["dismissed"] = _dismissed
                    ball_event["striker"] = _dismissed
                sb.apply_known_wicket_increment(ball_event.get("dismissed"))
            try:
                over_mgr.on_ball_event(
                    ball_event,
                    score=int(sb._inn.get("score") or 0))
                sb._tracker.on_ball_event()
            except Exception as e:
                recorder.record(
                    tag="REPLAY-OVER-MGR-DISPATCH-RAISED",
                    error=f"{type(e).__name__}: {e}")

        try:
            sm.on_frame(fi)
        except Exception as e:
            recorder.record(
                tag="REPLAY-SM-ON-FRAME-RAISED",
                error=f"{type(e).__name__}: {e}")

        decisions = recorder.drain()
        for d in decisions:
            tag = d.get("tag")
            if tag in new_tag_counts:
                new_tag_counts[tag] += 1
        if snapshot_fh is not None:
            tag_triggered = any(
                d.get("tag") in _SNAPSHOT_TRIGGER_TAGS for d in decisions)
            # 5b.4 mutation trigger: detect this_over reversion (C21b
            # symbol-revert manifests as a token mutation between idle
            # frames, NOT at commit boundaries). Sample whenever
            # SM.this_over delta is observable.
            cur_this_over = tuple(getattr(sm, "this_over", None) or [])
            this_over_changed = (
                bool(cur_this_over) and cur_this_over != last_this_over)
            if tag_triggered or this_over_changed:
                snap = _build_ui_snapshot(sm, sb, frame_id)
                snap_key = (
                    snap.over_ball, snap.score, snap.wickets,
                    tuple(snap.this_over_tokens))
                if snap_key != last_snap_key:
                    snap.event_index = snap_event_index.get(snap.over_ball, 0)
                    snap_event_index[snap.over_ball] = snap.event_index + 1
                    from dataclasses import asdict
                    snapshot_fh.write(json.dumps(asdict(snap)) + "\n")
                    snapshot_count += 1
                    last_snap_key = snap_key
                last_this_over = cur_this_over
        writer.write_record({
            "frame": frame_id,
            "ts_wall": ts,
            "session": session_id,
            "pipeline": {
                "mode": getattr(sm, "mode", None),
                "striker": getattr(sm, "striker", None),
                "non_striker": getattr(sm, "non", None),
                "current_bowler": getattr(sm, "bowler_name", None),
                "bat1_name": getattr(sm, "bat1_name", None),
                "bat2_name": getattr(sm, "bat2_name", None),
            },
            "scout": {"raw_text_120": str(raw)[:120]},
            "extractor": {
                "score": fi.ext_score,
                "wickets": fi.ext_wickets,
                "match_overs": fi.ext_overs,
            },
            "scorer": {
                "decisions": decisions,
                "sm_state": {
                    "score": getattr(sm, "score", None),
                    "wickets": getattr(sm, "wickets", None),
                    "overs": getattr(sm, "overs", None),
                },
            },
        })

    writer.close()
    if snapshot_fh is not None:
        snapshot_fh.close()
        print(f"Snapshots written: {snapshot_count}")
    logging.getLogger().removeHandler(log_handler)

    print(f"Frames: {len(frames)} | parsed: {parsed} | skipped: {skipped}")
    if enable_llm_extractor:
        print(f"LLM extractor calls: {llm_calls} | recoveries: {llm_recoveries}")
    print(f"New tag emission counts:")
    for tag, n in new_tag_counts.items():
        print(f"  {tag}: {n}")
    print(f"Trace written to {out_path} ({writer.records_written} records)")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dump", required=True, type=Path)
    p.add_argument("--session-id", required=True)
    p.add_argument(
        "--trace-dir",
        type=Path,
        default=FILES_DIR.parent / "logs" / "trace")
    p.add_argument("--seed-frame", type=int, default=None,
                   help="Skip frames < N and inject warm seed at frame N")
    p.add_argument("--seed-striker", type=str, default=None)
    p.add_argument("--seed-non-striker", type=str, default=None)
    p.add_argument("--seed-bowler", type=str, default=None)
    p.add_argument("--enable-llm-extractor", action="store_true",
                   help=("Fall back to production Extractor.extract() "
                         "(Groq Llama) when parse_strip returns "
                         "no-scorecard-data. Replay-only; production "
                         "cost path unchanged. Requires GROQ_API_KEY."))
    p.add_argument("--fixture", choices=("dckkr", "gtrr"), default="dckkr",
                   help=("Squad/team config to load. dckkr = DC vs KKR "
                         "(default), gtrr = GT vs RR per fixtures/"
                         "gt_vs_rr_2026_commentary_first_innings.md."))
    p.add_argument("--snapshot-output", type=Path, default=None,
                   help=("If set, emit a UIBallSnapshot JSONL stream "
                         "at every legal-ball commit. Schema matches "
                         "ingest_cricbuzz_ground_truth.py output so "
                         "replay_diff_harness.py can diff line-by-line."))
    args = p.parse_args()
    seed_args = (
        args.seed_frame, args.seed_striker,
        args.seed_non_striker, args.seed_bowler)
    if any(x is not None for x in seed_args) and not all(
            x is not None for x in seed_args):
        p.error(
            "warm-seed mode requires all of --seed-frame, --seed-striker, "
            "--seed-non-striker, --seed-bowler (got "
            f"frame={args.seed_frame} striker={args.seed_striker!r} "
            f"non={args.seed_non_striker!r} bowler={args.seed_bowler!r})")
    return run(args.dump, args.session_id, args.trace_dir,
               seed_frame=args.seed_frame,
               seed_striker=args.seed_striker,
               seed_non_striker=args.seed_non_striker,
               seed_bowler=args.seed_bowler,
               enable_llm_extractor=args.enable_llm_extractor,
               fixture=args.fixture,
               snapshot_output=args.snapshot_output)


if __name__ == "__main__":
    sys.exit(main())
