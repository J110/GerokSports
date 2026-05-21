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

import trace_emitter  # noqa: E402
from score_manager import ScoreManager  # noqa: E402
from eyes.extract_regex import parse_strip  # noqa: E402
from eyes.scoreboard import Scoreboard  # noqa: E402
from test_pipeline_captured_replay import (  # noqa: E402
    BATTING_TEAM as DCKKR_BATTING_TEAM,
    BOWLING_TEAM as DCKKR_BOWLING_TEAM,
    build_sm as build_sm_dckkr,
    extracted_to_frame_input,
)


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


def run(dump_path: Path, session_id: str, trace_dir: Path,
        seed_frame: int | None = None,
        seed_striker: str | None = None,
        seed_non_striker: str | None = None,
        seed_bowler: str | None = None,
        enable_llm_extractor: bool = False,
        fixture: str = "dckkr") -> int:
    builder, batting_team, bowling_team = FIXTURE_BUILDERS[fixture]
    sm, sb = builder()
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
               fixture=args.fixture)


if __name__ == "__main__":
    sys.exit(main())
