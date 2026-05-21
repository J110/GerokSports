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
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FILES_DIR))
sys.path.insert(0, str(FILES_DIR / "tests"))

import trace_emitter  # noqa: E402
from eyes.extract_regex import parse_strip  # noqa: E402
from test_pipeline_captured_replay import (  # noqa: E402
    BATTING_TEAM, BOWLING_TEAM, build_sm, extracted_to_frame_input,
)


def run(dump_path: Path, session_id: str, trace_dir: Path) -> int:
    sm, sb = build_sm()

    trace_dir.mkdir(parents=True, exist_ok=True)
    out_path = trace_dir / f"{session_id}.jsonl"
    if out_path.exists():
        out_path.unlink()
    writer = trace_emitter.TraceWriter(
        session_id=session_id, trace_dir=str(trace_dir))
    recorder = trace_emitter.get_recorder()
    log_handler = trace_emitter.install_log_handler(logging.getLogger())
    logging.getLogger().setLevel(logging.INFO)

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
    }
    for f in frames:
        try:
            frame_id = int(f.get("frame_id"))
        except (TypeError, ValueError):
            continue
        ts = float(f.get("ts") or time.time())
        raw = f.get("raw_response") or ""
        recorder.begin_frame(frame_id)
        try:
            extracted = parse_strip(raw, BATTING_TEAM, BOWLING_TEAM)
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
    logging.getLogger().removeHandler(log_handler)

    print(f"Frames: {len(frames)} | parsed: {parsed} | skipped: {skipped}")
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
    args = p.parse_args()
    return run(args.dump, args.session_id, args.trace_dir)


if __name__ == "__main__":
    sys.exit(main())
