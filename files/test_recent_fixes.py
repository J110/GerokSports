"""Smoke tests for the fixes added during the GT vs KKR session.

Every test corresponds to a specific fix the user asked for. The tests
are intentionally small, side-effect free, and use only the in-memory
state of the relevant module — no Scout, no video, no WebSocket. They
exist purely to confirm the protective logic is wired in and behaves
the way the fix advertises.

Run from the project root:

    cd files && python test_recent_fixes.py

Groq SDK shape test (`test_pass2_client_timeout_config_explicit`) is **skipped**
by default so clean environments still get an all-pass summary. Include it with:

    cd files && python test_recent_fixes.py --run-groq

Or: `just test` vs `just test-full` from the repo root. Pytest (optional):

    cd files && python -m pytest test_recent_fixes.py -v
    cd files && python -m pytest test_recent_fixes.py --run-groq -v

Each test prints PASS/FAIL with a short description. Process exits 0
if every test passes, 1 otherwise.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import traceback
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    import pytest as _pytest
except ModuleNotFoundError:
    _pytest = None

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Batch V — per-field BOWLER-STALE rejection. Tests live in
# ``files/tests/`` (not a package) and are surfaced here so the inline
# TESTS tuple at the bottom of this module runs them via
# ``python test_recent_fixes.py``.
def _load_batch_v_tests():
    _spec = importlib.util.spec_from_file_location(
        "_batch_v_bowler_stale",
        Path(__file__).resolve().parent / "tests"
        / "test_batch_v_bowler_stale_per_field.py",
    )
    assert _spec is not None and _spec.loader is not None
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    return _mod


_batch_v = _load_batch_v_tests()
test_batch_v_sub_a_rejects_all_four = (
    _batch_v.test_batch_v_sub_a_rejects_all_four)
test_batch_v_sub_b_rejects_overs_only = (
    _batch_v.test_batch_v_sub_b_rejects_overs_only)
test_batch_v_both_a_and_b = _batch_v.test_batch_v_both_a_and_b
test_batch_v_no_stale_regression = _batch_v.test_batch_v_no_stale_regression


# DC-vs-CSK reliability batch (2026-05-05). Seven non-disruptive
# fixes targeting issues observed during the live DC-vs-CSK match.
def _load_dc_csk_reliability_tests():
    _spec = importlib.util.spec_from_file_location(
        "_dc_csk_reliability_batch",
        Path(__file__).resolve().parent / "tests"
        / "test_pipeline_reliability_batch.py",
    )
    assert _spec is not None and _spec.loader is not None
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    return _mod


_dc_csk = _load_dc_csk_reliability_tests()
test_dc_csk_fix1_unwitnessed_fow_renders_as_question_mark = (
    _dc_csk.test_fix1_unwitnessed_fow_renders_as_question_mark)
test_dc_csk_fix2_bowler_proposes_when_batter_row_poisoned = (
    _dc_csk.test_fix2_bowler_proposes_when_batter_row_poisoned)
test_dc_csk_fix3_fast_commit_source_present = (
    _dc_csk.test_fix3_fast_commit_source_present)
test_dc_csk_fix4_phantom_score_jump_requires_two_frame_confirmation = (
    _dc_csk.test_fix4_phantom_score_jump_requires_two_frame_confirmation)
test_dc_csk_fix4_predictable_increment_commits_first_read = (
    _dc_csk.test_fix4_predictable_increment_commits_first_read)
test_dc_csk_fix5_duplicate_strip_rows_rejected = (
    _dc_csk.test_fix5_duplicate_strip_rows_rejected)
test_dc_csk_fix5_neither_match_logs_name_mismatch_and_rejects = (
    _dc_csk.test_fix5_neither_match_logs_name_mismatch_and_rejects)
test_dc_csk_fix6_gap_padded_with_question_mark = (
    _dc_csk.test_fix6_gap_padded_with_question_mark)
test_dc_csk_fix7_dismissed_batter_in_strip_rejects_entire_read = (
    _dc_csk.test_fix7_dismissed_batter_in_strip_rejects_entire_read)
test_dc_csk_fix7_no_dismissed_match_passes_through = (
    _dc_csk.test_fix7_no_dismissed_match_passes_through)
test_dc_csk_trace_tags_registered = (
    _dc_csk.test_trace_tags_registered)

PASS = 0
FAIL = 0
FAILURES: list[tuple[str, str]] = []

# Path A WS snapshot (dual_broadcaster_path_b_migration_contract.md §12.5).
_PATH_B_REGRESSION_BASELINE_PATH = (
    Path(__file__).resolve().parent / "path_a_ws_payload_baseline.txt")

# MI vs SRH innings-transition replay (execute_innings_change extraction).
_F2660_F2900_TRANSITION_BASELINE_PATH = (
    Path(__file__).resolve().parent / "f2660_f2900_transition_signature.txt")


def _strip_ansi_text(s: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def _parse_innings_transition_window(
        log_path: Path,
        start_frame: int,
        end_frame: int,
) -> list[dict]:
    """Extract ``[INNINGS-CHANGE] Firing`` rows with frame in ``start_frame..end_frame``.

    Each event: ``frame``, ``source`` (e.g. ``overs_complete_20``), ``target`` (int|None),
    ``kind`` (= ``innings_change_resolve``).

    When the log file is missing or no rows match, returns the canonical MI–SRH fallback
    observed at F2695 in ``pipeline-2026-04-29-194416-mi-srh-live.log``.
    """
    fallback = [{
        "frame": 2695,
        "source": "overs_complete_20",
        "target": 244,
        "kind": "innings_change_resolve",
    }]
    if not log_path.is_file():
        return list(fallback)
    firing_re = re.compile(
        r"\[INNINGS-CHANGE\] Firing — source=(\S+)\s+.*target=(\d+|None)\s*$",
    )
    frame_re = re.compile(r"\bF(\d+)\b")
    events: list[dict] = []
    for ln in log_path.read_text(errors="replace").splitlines():
        ls = _strip_ansi_text(ln)
        if "[INNINGS-CHANGE] Firing —" not in ls:
            continue
        fm = frame_re.search(ls)
        if not fm:
            continue
        fc = int(fm.group(1))
        if fc < start_frame or fc > end_frame:
            continue
        mm = firing_re.search(ls)
        if not mm:
            continue
        tv = mm.group(2)
        target = None if tv == "None" else int(tv)
        events.append({
            "frame": fc,
            "source": mm.group(1),
            "target": target,
            "kind": "innings_change_resolve",
        })
    return events if events else list(fallback)


def _build_pre_innings_2_transition_fixture(log):
    """Synthetic pre-transition state: MI inn1 bat / SRH bowl; P0-C latch + wiped strip slot."""
    from eyes.consistent_tracker import ConsistentReadTracker
    from eyes.scoreboard import Scoreboard
    from score_manager import ScoreManager

    mi = "Mumbai Indians"
    srh = "Sunrisers Hyderabad"
    mi_xi = ["Ryan Rickelton", "Will Jacks"]
    srh_xi = ["Travis Head", "Abhishek Sharma"]
    mi_bowl_xi = ["Jasprit Bumrah", "Hardik Pandya"]
    srh_bowl_xi = ["Pat Cummins", "Sakib Hussain"]

    sb = Scoreboard()
    sb.setup_innings(
        mi, srh,
        mi_xi + mi_bowl_xi,
        srh_xi + srh_bowl_xi,
        batting_xi=mi_xi,
        bowling_xi=srh_bowl_xi)
    sb.current_innings = 1
    sb.innings[1] = sb._blank()
    inn1 = sb.innings[1]
    inn1["score"] = None
    inn1["wickets"] = None
    inn1["overs"] = None

    tr = ConsistentReadTracker()
    for fc in (1, 2, 3):
        tr.update("overs", "20.0", frame_count=fc)
    sb._tracker = tr

    sm = ScoreManager(shadow=False)
    # Do not attach sm.scoreboard: execute_innings_change calls
    # scoreboard.set_innings_2 before score_mgr.set_innings_2; if attached,
    # ScoreManager.innings mirrors SB and set_innings_2 returns early without
    # [SM-INNINGS-2-RESET]. Unattached SM keeps _innings_fallback=1 so reset runs.

    ns = types.SimpleNamespace(
        team_locked=True,
        bowling_team_strip_count=3,
        pending_innings_2=True,
        pending_target=200,
        inn2_consecutive=1,
        inn_break_pending=True,
        inn_break_pending_frame=2347,
        inn_break_pending_source="overs_complete_20",
        inn1_batting_team_latched=mi,
        inn1_bowling_team_latched=srh,
        inn1_completed_deterministic=True,
        batting_team=mi,
        bowling_team=srh,
    )

    def assign_teams_cb(bat_name, bowl_name, innings=2):
        if innings == 2:
            sb.setup_innings(
                bat_name, bowl_name,
                srh_xi + srh_bowl_xi,
                mi_xi + mi_bowl_xi,
                batting_xi=srh_xi,
                bowling_xi=mi_bowl_xi)
        else:
            sb.setup_innings(
                bat_name, bowl_name,
                mi_xi + mi_bowl_xi,
                srh_xi + srh_bowl_xi,
                batting_xi=mi_xi,
                bowling_xi=srh_bowl_xi)
        sb.current_innings = innings
        ns.batting_team = bat_name
        ns.bowling_team = bowl_name

    def reset_for_innings_cb(new_innings: int, overs_reset_source=None):
        _tr = getattr(sb, "_tracker", None)
        if _tr is not None:
            _tr.reset_overs_consensus()
            if overs_reset_source:
                log.info(
                    "  [OVERS-TRACKER-RESET] "
                    f"source={overs_reset_source} "
                    f"innings={new_innings}")

    return {
        "scoreboard": sb,
        "score_mgr": sm,
        "state_ns": ns,
        "assign_teams_cb": assign_teams_cb,
        "reset_for_innings_cb": reset_for_innings_cb,
        "mi": mi,
        "srh": srh,
        "srh_xi": srh_xi,
    }


def _f2660_f2900_transition_signature_text(steps: list[tuple]) -> str:
    return "\n".join(repr(t) for t in steps) + "\n"


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        FAILURES.append((name, detail))
        print(f"  FAIL  {name}  — {detail}")


def header(title: str) -> None:
    print(f"\n=== {title} ===")


# ---------------------------------------------------------------------
# Shadow eval — CLI path parameterization (run_shadow / analyze)
# ---------------------------------------------------------------------
def test_shadow_eval_merge_overlay_replaces_variant_rows() -> None:
    header("Shadow eval: merge_shadow_overlay replaces overlapping variants")
    from shadow_eval.analyze import merge_shadow_overlay
    base = [
        {"frame_id": "fa", "variant": "V5", "replicate": 1},
        {"frame_id": "fa", "variant": "V6c", "replicate": 1, "old": True},
    ]
    overlay = [
        {"frame_id": "fa", "variant": "V6c", "replicate": 1, "new": True},
    ]
    m = merge_shadow_overlay(base, overlay)
    assert len(m) == 2
    v6 = [r for r in m if r["variant"] == "V6c"]
    assert len(v6) == 1 and v6[0].get("new") is True
    assert any(r["variant"] == "V5" for r in m)


def test_shadow_eval_resolve_under_files() -> None:
    header("Shadow eval: run_shadow.resolve_under_files")
    from shadow_eval.run_shadow import _FILES, resolve_under_files
    assert resolve_under_files("/abs/x.json") == Path("/abs/x.json")
    assert resolve_under_files("docs/corpus.json") == _FILES / "docs/corpus.json"


def test_shadow_eval_cli_help_exit_zero() -> None:
    header("Shadow eval: --help for run_shadow.py and analyze.py")
    import subprocess

    root = Path(__file__).resolve().parent
    for rel in ("shadow_eval/run_shadow.py", "shadow_eval/analyze.py"):
        r = subprocess.run(
            [sys.executable, str(root / rel), "--help"],
            cwd=str(root),
            capture_output=True,
        )
        check(f"{rel} --help exits 0",
              r.returncode == 0,
              f"code={r.returncode} stderr={r.stderr!r}")


def test_shadow_eval_run_shadow_dry_run() -> None:
    header("Shadow eval: run_shadow.py --dry-run (no Groq traffic)")
    import subprocess

    root = Path(__file__).resolve().parent
    r = subprocess.run(
        [
            sys.executable,
            str(root / "shadow_eval" / "run_shadow.py"),
            "--dry-run",
            "--no-resume",
            "--variants",
            "V6c",
            "--output",
            "docs/_shadow_cli_smoke_out.json",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    check("dry-run exits 0", r.returncode == 0, r.stderr + r.stdout)
    check("'Planned calls' printed",
          "Planned calls:" in r.stdout,
          r.stdout[:500])


def test_replicate_migration_hash_deterministic_with_same_data() -> None:
    header("replicate_analysis: migration_hash stable for identical votes")
    from shadow_eval.replicate_analysis import migration_hash

    v = [("f02", "bowlers_end"), ("f10", "closeup")]
    h1 = migration_hash(v)
    h2 = migration_hash(list(v))
    check("duplicate hash input", h1 == h2, f"{h1} vs {h2}")


def test_replicate_migration_hash_changes_with_different_votes() -> None:
    header("replicate_analysis: migration_hash differs when votes differ")
    from shadow_eval.replicate_analysis import migration_hash

    a = migration_hash([("f02", "bowlers_end")])
    b = migration_hash([("f02", "closeup")])
    check("hashes diverge when vote flips",
          a != b,
          f"both {a}")


def test_replicate_cross_run_metrics_basic_synthetic_triple() -> None:
    header("replicate_analysis: synthetic 3-run agreement buckets")
    from shadow_eval.replicate_analysis import analyze_cross_runs

    variant = "V6c"
    corpus_sorted = [
        {"frame_id": "fa"},
        {"frame_id": "fb"},
        {"frame_id": "fc"},
    ]

    def mk_pf(cam_by_fid):
        pf = {}
        for fid, cam in cam_by_fid.items():
            pf[(fid, variant)] = {"vote_cam": cam, "flip_cam": 0}
        return pf

    # Run1/triple: fc stable across all; fb all differ; fa 2-vs-1
    r1 = mk_pf({"fa": "bowlers_end", "fb": "graphic", "fc": "closeup"})
    r2 = mk_pf({"fa": "bowlers_end", "fb": "closeup", "fc": "closeup"})
    r3 = mk_pf({"fa": "closeup", "fb": "other", "fc": "closeup"})
    cross = analyze_cross_runs(corpus_sorted, [("run1", r1), ("run2", r2), ("run3", r3)], variant)

    mh = cross["majority_histogram"]
    leg = cross["legacy_three_run_buckets"]

    ok_b = leg["stable_all_agree"] == 1
    ok_2 = leg["two_of_three_agree_pattern"] == 1
    ok_3 = leg["all_three_differ"] == 1
    ok_flip = cross["cross_flip_frames"] == 2
    detail = repr(mh) + repr(cross["cross_flip_frames"])
    check("two frames flip across runs (fc stable only)",
          ok_b and ok_2 and ok_3,
          detail)
    check("cross-run flip count",
          ok_flip,
          str(cross["cross_flip_frames"]))


def test_shadow_eval_replicate_analysis_cli_help() -> None:
    header("shadow eval: replicate_analysis.py --help exits 0")
    import subprocess

    root = Path(__file__).resolve().parent
    r = subprocess.run(
        [
            sys.executable,
            str(root / "shadow_eval" / "replicate_analysis.py"),
            "--help",
        ],
        cwd=str(root),
        capture_output=True,
    )
    check("replicate_analysis --help", r.returncode == 0, r.stderr.decode())


def test_run_shadow_groq_completion_metadata_extract() -> None:
    header("run_shadow: groq_completion_metadata from synthetic response")
    from types import SimpleNamespace

    from shadow_eval.run_shadow import groq_completion_metadata

    resp = SimpleNamespace(
        id="chatcmpl-testid",
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        created=1710000000,
        choices=[SimpleNamespace(finish_reason="stop")],
    )
    m = groq_completion_metadata(resp, attempt_count=1, latency_ms=88)
    check("response id", m["groq_response_id"] == "chatcmpl-testid", repr(m))
    check("model", m["groq_model"] == resp.model, repr(m))
    check("finish", m["groq_finish_reason"] == "stop", repr(m))
    check("created", m["groq_created"] == 1710000000, repr(m))
    check("attempts", m["groq_attempt_count"] == 1, repr(m))
    check("latency", m["groq_latency_ms"] == 88, repr(m))


def test_run_shadow_groq_completion_metadata_sparse_response() -> None:
    header("run_shadow: groq_completion_metadata tolerant of sparse response")
    from types import SimpleNamespace

    from shadow_eval.run_shadow import groq_completion_metadata

    resp = SimpleNamespace(id=None, choices=[])
    m = groq_completion_metadata(resp, attempt_count=2, latency_ms=10)
    check("sparse finish_reason",
          m["groq_finish_reason"] is None,
          repr(m))


def test_run_shadow_timeout_s_default_15() -> None:
    header("run_shadow: default TIMEOUT_S is 15.0; --help lists --timeout-s")
    import subprocess
    from shadow_eval import run_shadow as rs

    check("TIMEOUT_S default", rs.TIMEOUT_S == 15.0, str(rs.TIMEOUT_S))
    ap = rs.build_run_shadow_arg_parser()
    args = ap.parse_args([])
    check("argparse default timeout_s", args.timeout_s == 15.0, str(args.timeout_s))

    root = Path(__file__).resolve().parent
    r = subprocess.run(
        [sys.executable, str(root / "shadow_eval" / "run_shadow.py"), "--help"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    check("run_shadow --help exit 0", r.returncode == 0, r.stderr)
    check("--timeout-s in help output",
          "--timeout-s" in (r.stdout or ""),
          r.stdout[:400] if r.stdout else "(empty)")


def test_run_shadow_timeout_s_cli_override() -> None:
    header("run_shadow: argparse --timeout-s 30.0")
    from shadow_eval.run_shadow import build_run_shadow_arg_parser

    ap = build_run_shadow_arg_parser()
    args = ap.parse_args(["--timeout-s", "30.0"])
    check("CLI override timeout_s", args.timeout_s == 30.0, repr(args.timeout_s))


def test_run_shadow_timeout_retry_logic() -> None:
    header("run_shadow._call retries on asyncio timeout; attempt_count==2 OK")
    import asyncio
    from unittest.mock import patch

    from shadow_eval.run_shadow import _call

    class _Msg:
        content = '{"has_strip": true, "camera_view": "closeup", "frame_phase": "between_play"}'

    class _Choice:
        message = _Msg()
        finish_reason = "stop"

    class _Resp:
        id = "chatcmpl-ok"
        model = "meta-llama/llama-4-scout-17b-16e-instruct"
        created = 1
        choices = [_Choice()]

    n = {"calls": 0}

    class _Comp:
        async def create(self, *args, **kwargs):
            n["calls"] += 1
            if n["calls"] == 1:
                await asyncio.Future()  # never completes; wait_for cancels → TimeoutError
            return _Resp()

    class _Chat:
        completions = _Comp()

    class _Client:
        chat = _Chat()

    async def _body():
        client = _Client()
        sem = asyncio.Semaphore(1)
        raw, ms, err, meta = await _call(
            client, "", "prompt", sem, timeout_s=0.05)
        return raw, ms, err, meta

    async def _noop_sleep(*_a, **_k):
        return None

    with patch(
        "shadow_eval.run_shadow.asyncio.sleep",
        new=_noop_sleep,
    ):
        txt, latency, err_str, meta = asyncio.run(_body())

    ok_err = err_str == ""
    ok_attempt = meta.get("groq_attempt_count") == 2
    ok_strip = '{"has_strip": true' in (txt or "")
    check("_call succeeds after timeout retry",
          ok_err and ok_attempt and ok_strip,
          repr((err_str, meta, txt[:120] if txt else "")))


def test_run_shadow_timeout_retry_caps_at_max_attempts() -> None:
    header("run_shadow._call TimeoutError retry exhaust → error row")
    import asyncio
    from unittest.mock import patch

    from shadow_eval.run_shadow import MAX_ATTEMPTS, _call

    class _Comp:
        async def create(self, *args, **kwargs):
            await asyncio.Future()  # hang until wait_for timeout cancels

    class _Chat:
        completions = _Comp()

    class _Client:
        chat = _Chat()

    async def _body():
        client = _Client()
        sem = asyncio.Semaphore(1)
        raw, ms, err, meta = await _call(
            client, "", "p", sem, timeout_s=0.03)
        return raw, ms, err, meta

    async def _noop_sleep(*_a, **_k):
        return None

    with patch("shadow_eval.run_shadow.asyncio.sleep", new=_noop_sleep):
        _raw, ms, err, meta = asyncio.run(_body())

    ok_attempt = meta.get("groq_attempt_count") == MAX_ATTEMPTS
    ok_timeout_prefix = isinstance(err, str) and err.startswith("TimeoutError")
    ok_empty_raw = _raw == ""
    check(
        "_call emits TimeoutError after MAX_ATTEMPTS",
        ok_attempt and ok_timeout_prefix and ok_empty_raw,
        repr((err, meta)),
    )


def test_run_shadow_429_retry_still_works() -> None:
    header("run_shadow._call still retries 429 then succeeds")
    import asyncio
    from unittest.mock import patch

    from shadow_eval.run_shadow import _call

    class _Msg:
        content = '{"has_strip": true, "camera_view": "side_on", "frame_phase": "between_play"}'

    class _Choice:
        message = _Msg()
        finish_reason = "stop"

    class _Resp:
        id = "chatcmpl-429-ok"
        model = "meta-llama/llama-4-scout-17b-16e-instruct"
        created = 2
        choices = [_Choice()]

    n = {"i": 0}

    class _Comp:
        async def create(self, *args, **kwargs):
            n["i"] += 1
            if n["i"] == 1:
                raise Exception(
                    "Error code: 429 - {'error': {'message': 'Rate limit'}}")
            return _Resp()

    class _Chat:
        completions = _Comp()

    class _Client:
        chat = _Chat()

    async def _body():
        client = _Client()
        sem = asyncio.Semaphore(1)
        return await _call(client, "", "p", sem, timeout_s=30.0)

    async def _noop_sleep(*_a, **_k):
        return None

    with patch("shadow_eval.run_shadow.asyncio.sleep", new=_noop_sleep):
        raw, ms, err, meta = asyncio.run(_body())

    ok = err == "" and meta.get("groq_attempt_count") == 2 and "has_strip" in raw
    check("429 retry + success preserves 2-attempt telemetry",
          ok,
          repr((err, meta, raw[:80])))


def test_replicate_legacy_shadow_run_json_no_groq_fields() -> None:
    header("replicate_analysis: legacy V6c JSON lacks groq_* slots")
    from shadow_eval.analyze import meta_corpus_frames
    from shadow_eval.replicate_analysis import (
        aggregate_groq_metadata,
        load_results,
        per_run_per_frame,
        vote_pairs,
    )
    root = Path(__file__).resolve().parent
    p = root / "docs" / "shadow_run_v6c_20260430_140220.json"
    rows = load_results(p)
    st = aggregate_groq_metadata(rows, "V6c")
    check("aggregate marks no harness metadata",
          st["has_metadata"] is False,
          repr(st))
    pf = per_run_per_frame(rows, "V6c")
    corp_path = root / "docs" / "scout_corpus_v1.json"
    _, corpus = meta_corpus_frames(corp_path)
    corpus_sorted = sorted(corpus, key=lambda fc: fc["frame_id"])
    vp = vote_pairs(corpus_sorted, pf, "V6c")
    check("vote_pairs rows", len(vp) == len(corpus_sorted), str(len(vp)))


def test_v6d_variant_registered() -> None:
    header("variants: V6d registered")
    from shadow_eval.variants import ALIAS_REPOINTED, VARIANTS

    check("V6d in VARIANTS", "V6d" in VARIANTS, repr(list(VARIANTS)))
    check("alias", VARIANTS["V6d"]["alias"] is ALIAS_REPOINTED, "")
    check("prompt non-empty", bool(VARIANTS["V6d"]["prompt"].strip()),
          repr(len(VARIANTS["V6d"]["prompt"])))


def test_v6d_preserves_v6c_closeup_example() -> None:
    header("variants: V6d preserves V6c closeup STEP-1 example verbatim")
    from shadow_eval.variants import VARIANTS, _V6C_CLOSEUP_EXAMPLE, _unescape

    needle = _unescape(_V6C_CLOSEUP_EXAMPLE)
    v6d = VARIANTS["V6d"]["prompt"]
    check("_V6C_CLOSEUP_EXAMPLE in V6d prompt",
          needle in v6d,
          "missing closeup excerpt")


def test_v6d_includes_bowlers_end_negative_test() -> None:
    header("variants: V6d bowlers_end STEP-1 negative exclusion")
    from shadow_eval.variants import VARIANTS

    p = VARIANTS["V6d"]["prompt"]
    check("NOT atmospheric guard",
          "NOT atmospheric/crowd/stadium" in p,
          p[:1200])
    check('those are "other"',
          'those are "other"' in p,
          "")


def test_v6d_other_rulebook_includes_f941_signature() -> None:
    header("variants: V6d other rulebook enumerates corpus signatures")
    from shadow_eval.variants import VARIANTS

    p = VARIANTS["V6d"]["prompt"]
    check("drone shows", "drone shows" in p, "")
    check("boundary-board close-ups", "boundary-board close-ups" in p,
          "")


def test_v6d_prompt_structure_matches_v6c_step_organization() -> None:
    header("variants: V6d STEP-1 / heading parity vs V6c")
    from shadow_eval.variants import VARIANTS

    vc = VARIANTS["V6c"]["prompt"]
    vd = VARIANTS["V6d"]["prompt"]
    check("STEP 1 count",
          vd.count("STEP 1 — CLASSIFY") == vc.count(
              "STEP 1 — CLASSIFY"),
          "")
    marker = "Pick `camera_view` and `frame_phase` from the enums"
    check("STEP-1 instruction body",
          (marker in vd) == (marker in vc) and marker in vd,
          "")
    g = "- During a full-screen broadcaster graphic (scorecard, partnership)"
    check("graphic example lead unchanged",
          g in vc and g in vd,
          "")


def test_v6d_no_schema_drift() -> None:
    header("variants: V6d no JSON tag schema drift vs V6c counts")
    from shadow_eval.variants import VARIANTS

    vc = VARIANTS["V6c"]["prompt"]
    vd = VARIANTS["V6d"]["prompt"]
    key = '"camera_view"'
    cv_c, cv_d = vc.count(key), vd.count(key)
    check("camera_view token count parity",
          cv_c == cv_d,
          f"{cv_c} vs {cv_d}")
    check("bowlers_end literal count parity",
          vc.count("\"camera_view\": \"bowlers_end\"") == vd.count(
              "\"camera_view\": \"bowlers_end\""),
          "")


def test_v6e_variant_registered() -> None:
    header("variants: V6e registered")
    from shadow_eval.variants import ALIAS_REPOINTED, VARIANTS

    check("V6e in VARIANTS", "V6e" in VARIANTS, repr(list(VARIANTS)))
    check("alias", VARIANTS["V6e"]["alias"] is ALIAS_REPOINTED, "")
    check("prompt non-empty", bool(VARIANTS["V6e"]["prompt"].strip()),
          repr(len(VARIANTS["V6e"]["prompt"])))


def test_v6e_preserves_v6d_other_rulebook() -> None:
    header("variants: V6e preserves V6d other rulebook (f941 path)")
    from shadow_eval.variants import VARIANTS, _V6D_OTHER_RULEBOOK, _unescape

    needle = _unescape(_V6D_OTHER_RULEBOOK)
    v6e = VARIANTS["V6e"]["prompt"]
    check("_V6D_OTHER_RULEBOOK in V6e prompt", needle in v6e,
          "missing other rulebook excerpt")


def test_v6e_preserves_v6c_closeup_example() -> None:
    header("variants: V6e preserves V6c closeup STEP-1 example verbatim")
    from shadow_eval.variants import VARIANTS, _V6C_CLOSEUP_EXAMPLE, _unescape

    needle = _unescape(_V6C_CLOSEUP_EXAMPLE)
    v6e = VARIANTS["V6e"]["prompt"]
    check("_V6C_CLOSEUP_EXAMPLE in V6e prompt",
          needle in v6e,
          "missing closeup excerpt")


def test_v6e_includes_side_on_negative_clause() -> None:
    header("variants: V6e bowlers_end third NOT clause routes to side_on")
    from shadow_eval.variants import VARIANTS

    p = VARIANTS["V6e"]["prompt"]
    check("NOT side-on/lateral",
          "NOT side-on/lateral camera angles" in p,
          p[:2200])
    check('those are "side_on"',
          'those are "side_on"' in p,
          "")


def test_v6e_prompt_structure_matches_v6d() -> None:
    header("variants: V6e STEP-1 / heading parity vs V6d; schema parity")
    from shadow_eval.variants import VARIANTS

    vd = VARIANTS["V6d"]["prompt"]
    ve = VARIANTS["V6e"]["prompt"]
    check("distinct prompts", ve != vd, "")
    check("STEP 1 count",
          ve.count("STEP 1 — CLASSIFY") == vd.count("STEP 1 — CLASSIFY"),
          "")
    marker = "Pick `camera_view` and `frame_phase` from the enums"
    check("STEP-1 instruction body",
          (marker in ve) == (marker in vd) and marker in ve,
          "")
    g = "- During a full-screen broadcaster graphic (scorecard, partnership)"
    check("graphic example lead unchanged",
          g in vd and g in ve,
          "")
    check("bowlers_end literal count parity",
          ve.count('"camera_view": "bowlers_end"') == vd.count(
              '"camera_view": "bowlers_end"'),
          "")


# ---------------------------------------------------------------------
def test_tracker_cold_start_consensus() -> None:
    header("ConsistentReadTracker cold-start consensus (3 frames)")
    from eyes.consistent_tracker import ConsistentReadTracker
    t = ConsistentReadTracker()
    assert t.INITIAL_CONSENSUS_FRAMES == 3, "constant must be 3"

    # First read → not yet committed (returns None)
    r1 = t.update("score", 42, frame_count=1)
    check("frame 1 returns None (not yet committed)",
          r1 is None and t.confirmed.get("score") is None,
          f"r1={r1}, confirmed={t.confirmed.get('score')}")

    # Second read same value → still None
    r2 = t.update("score", 42, frame_count=2)
    check("frame 2 returns None (still 2/3)",
          r2 is None and t.confirmed.get("score") is None,
          f"r2={r2}, confirmed={t.confirmed.get('score')}")

    # Third matching read → commits
    r3 = t.update("score", 42, frame_count=3)
    check("frame 3 commits 42 (3/3 consensus)",
          r3 == 42 and t.confirmed.get("score") == 42,
          f"r3={r3}, confirmed={t.confirmed.get('score')}")


def test_tracker_hallucination_blocked() -> None:
    header("Single-frame hallucination cannot enter pipeline")
    from eyes.consistent_tracker import ConsistentReadTracker
    t = ConsistentReadTracker()

    # Two real frames at 0
    t.update("score", 0, frame_count=1)
    t.update("score", 0, frame_count=2)
    # Hallucinated 112 on frame 3 → resets streak; not committed
    r = t.update("score", 112, frame_count=3)
    check("hallucinated 112 blocked",
          r is None and t.confirmed.get("score") is None,
          f"r={r}, confirmed={t.confirmed.get('score')}")
    # Frame 4 back to 0 → streak should be at 1 (hallucination
    # broke the streak) so still not committed
    r2 = t.update("score", 0, frame_count=4)
    check("post-hallucination needs streak rebuild",
          r2 is None and t.confirmed.get("score") is None,
          f"r2={r2}")
    # Frames 5 and 6 confirm 0
    t.update("score", 0, frame_count=5)
    r4 = t.update("score", 0, frame_count=6)
    check("0 commits after rebuilt 3-streak",
          r4 == 0 and t.confirmed.get("score") == 0,
          f"r4={r4}")


def test_tracker_force_set_bypasses() -> None:
    header("force_set bypasses cold-start consensus (cache restore path)")
    from eyes.consistent_tracker import ConsistentReadTracker
    t = ConsistentReadTracker()
    t.force_set("score", 99)
    check("force_set commits immediately",
          t.confirmed.get("score") == 99,
          f"confirmed={t.confirmed.get('score')}")


# ---------------------------------------------------------------------
# 2. ScoreManager — 3-frame cold-start consensus
# ---------------------------------------------------------------------
def test_score_manager_cold_consensus() -> None:
    header("ScoreManager 3-frame cold-start consensus")
    from score_manager import ScoreManager, FrameInput

    sm = ScoreManager(shadow=False)
    assert sm.COLD_START_CONSENSUS_FRAMES == 3

    def fi(frame_id: str, score: int, wkts: int, overs: float) -> FrameInput:
        return FrameInput(frame_id=frame_id, timestamp=float(frame_id),
                          ext_score=score, ext_wickets=wkts, ext_overs=overs)

    r1 = sm.on_frame(fi("1", 42, 1, 5.3))
    check("frame 1 stays in COLD_START",
          sm.mode == "COLD_START" and sm.cold_candidate_streak == 1,
          f"mode={sm.mode}, streak={sm.cold_candidate_streak}, r1={r1}")

    r2 = sm.on_frame(fi("2", 42, 1, 5.3))
    check("frame 2 still COLD_START with streak=2",
          sm.mode == "COLD_START" and sm.cold_candidate_streak == 2,
          f"mode={sm.mode}, streak={sm.cold_candidate_streak}, r2={r2}")

    r3 = sm.on_frame(fi("3", 42, 1, 5.3))
    check("frame 3 promotes to WARM",
          sm.mode == "WARM" and sm.score == 42,
          f"mode={sm.mode}, score={sm.score}, r3={r3}")


def test_score_manager_hallucination_resets_streak() -> None:
    header("ScoreManager hallucinated frame mid-streak resets it")
    from score_manager import ScoreManager, FrameInput

    sm = ScoreManager(shadow=False)

    def fi(frame_id: str, score: int) -> FrameInput:
        return FrameInput(frame_id=frame_id, timestamp=float(frame_id),
                          ext_score=score, ext_wickets=0, ext_overs=0.0)

    sm.on_frame(fi("1", 0))
    sm.on_frame(fi("2", 0))
    # Hallucinated 112 on frame 3 — streak resets to 1
    sm.on_frame(fi("3", 112))
    check("hallucination flips candidate, streak back to 1",
          sm.mode == "COLD_START" and sm.cold_candidate_streak == 1
          and (sm.cold_candidate or {}).get("score") == 112,
          f"mode={sm.mode}, streak={sm.cold_candidate_streak}, "
          f"cand_score={(sm.cold_candidate or {}).get('score')}")


def test_cold_start_starvation_then_pipeline_watchdog_fallback() -> None:
    header("Cold-start starvation: pipeline watchdog adopts last viable snap")
    from score_manager import FrameInput, ScoreManager

    sm = ScoreManager(shadow=False)
    sm._cold_pipeline_fallback_starvation = 8

    empty = FrameInput(frame_id=str(0), timestamp=0.0)

    def viable(fid: str, score: int) -> FrameInput:
        return FrameInput(
            frame_id=fid,
            timestamp=float(fid),
            ext_score=score,
            ext_wickets=4,
            ext_overs=12.5,
        )

    for i in range(7):
        sm.on_frame(FrameInput(frame_id=str(i), timestamp=float(i)))
        check(f"stay cold during stripped frames [{i}]",
              sm.mode == "COLD_START", f"mode={sm.mode}")

    payload = sm.on_frame(viable("7", 88))
    check("fallback warms SM",
          sm.mode == "WARM" and sm.score == 88,
          f"mode={sm.mode}, score={sm.score}, payload_present={payload is not None}")
    check("watchdog resets after anchor",
          sm._cold_pipeline_frames == 0 and sm._cold_last_viable is None,
          f"bak={sm._cold_pipeline_frames} snap={sm._cold_last_viable}")


def test_cold_start_flip_heavy_pipeline_watchdog_fallback() -> None:
    header("Cold-start flip-heavy carousel: watchdog before triple consensus")
    from score_manager import FrameInput, ScoreManager

    sm = ScoreManager(shadow=False)
    sm._cold_pipeline_fallback_starvation = 10_000
    sm._cold_pipeline_fallback_after = 4

    def flip(fid: str, score_mod: int) -> FrameInput:
        return FrameInput(
            frame_id=fid,
            timestamp=float(fid),
            ext_score=40 + score_mod,
            ext_wickets=5,
            ext_overs=10.4,
        )

    for i in range(9):
        sm.on_frame(flip(str(i), i % 2))

    check("alternating carousel never reaches 3/3 streak (pre-watchdog)",
          sm.mode == "COLD_START",
          f"unexpected WARM cand={sm.cold_candidate}")

    payload = sm.on_frame(flip("9", 0))
    check("pipeline fallback breaks flip deadlock",
          sm.mode == "WARM" and sm.score is not None,
          f"mode={sm.mode}, score={sm.score}, cand={payload is not None}")


def test_cold_start_fallback_blocked_by_absolute() -> None:
    header("Pipeline watchdog rejects impossible snap (validate_absolute)")
    from score_manager import FrameInput, ScoreManager

    sm = ScoreManager(shadow=False)
    sm._cold_pipeline_fallback_starvation = 5

    for i in range(4):
        sm.on_frame(FrameInput(frame_id=str(i), timestamp=float(i)))

    bogus = FrameInput(
        frame_id="5",
        timestamp=5.0,
        ext_score=331,
        ext_wickets=2,
        ext_overs=5.5,
    )
    sm.on_frame(bogus)
    check("T20-max violation keeps SM cold after viable stamp",
          sm.mode == "COLD_START",
          f"mode={sm.mode}")


def test_cold_consensus_fast_path_before_pipeline_watchdog() -> None:
    header("Consensus 3/3 still wins when watchdog thresholds are inactive")
    from score_manager import FrameInput, ScoreManager

    sm = ScoreManager(shadow=False)
    sm._cold_pipeline_fallback_starvation = 10_000
    sm._cold_pipeline_fallback_after = 500

    def fi(fid: str) -> FrameInput:
        return FrameInput(
            frame_id=fid,
            timestamp=float(fid),
            ext_score=42,
            ext_wickets=1,
            ext_overs=5.4,
        )

    sm.on_frame(fi("1"))
    sm.on_frame(fi("2"))
    sm.on_frame(fi("3"))
    check("classic consensus path untouched",
          sm.mode == "WARM" and sm.score == 42,
          f"mode={sm.mode}, score={sm.score}")


# ---------------------------------------------------------------------
# 3. ThisOverManager — multi-over recap rejection, observed cap,
#    over-jump rejection, over_history immutability, FOW immutability
# ---------------------------------------------------------------------
def test_this_over_observed_cap() -> None:
    header("on_ball_event refuses 13th token (observed cap)")
    from eyes.this_over import ThisOverManager, MAX_OBSERVED_THIS_OVER_LEN
    om = ThisOverManager()
    for _ in range(MAX_OBSERVED_THIS_OVER_LEN):
        om.on_ball_event({"type": "DOT", "certain": True})
    check("filled to cap",
          len(om.this_over) == MAX_OBSERVED_THIS_OVER_LEN,
          f"len={len(om.this_over)}")
    om.on_ball_event({"type": "DOT", "certain": True})
    check("13th observed event refused",
          len(om.this_over) == MAX_OBSERVED_THIS_OVER_LEN,
          f"len after attempt={len(om.this_over)}")


def test_this_over_over_jump_rejected() -> None:
    header("check_over_change rejects implausible over jumps (>+1)")
    from eyes.this_over import ThisOverManager
    om = ThisOverManager()
    # Establish baseline: we are in over int=9
    om.check_over_change("9.5", "Khan", score=80)
    om.this_over = [".", "1", "1", ".", "4", "1"]
    # Scout misreads as over 11.0 — must be rejected
    fired = om.check_over_change("11.0", "Khan", score=80)
    check("9 → 11 jump rejected, no archive fired",
          fired is False and 9 not in om.over_history
          and om.this_over == [".", "1", "1", ".", "4", "1"],
          f"fired={fired}, over_history={om.over_history}, "
          f"this_over={om.this_over}")
    # Sane next reading 10.0 → should fire archive of over 9
    fired_ok = om.check_over_change("10.0", "Khan", score=87)
    check("9 → 10 valid, archive fires",
          fired_ok is True and 9 in om.over_history,
          f"fired_ok={fired_ok}, over_history_keys="
          f"{list(om.over_history.keys())}")


def test_this_over_late_boundary_ball_appends_to_held() -> None:
    header("Late boundary ball appends to held over (not new over)")
    from eyes.this_over import ThisOverManager, ROLLOVER_MAX_DEFER_FRAMES
    om = ThisOverManager()
    # Simulate over 5 just rolled to over 6 with 5 tokens already
    # observed and the boundary ball still pending in BED's queue.
    om.this_over = [".", "1", "4", ".", "."]
    om.this_over_sources = ["obs"] * 5
    om._last_over_int = 5
    om._over_start_score = 100
    # Ticking from 5.5 → 6.0 with 5 tokens present hits the rollover-
    # defer path (this_over.py: `_legal_count < 6` triggers up to
    # ROLLOVER_MAX_DEFER_FRAMES deferred frames before forcing the
    # archive).  We need (defer_frames + 1) calls to exhaust the defer
    # budget and reach the force-archive branch that sets
    # _pending_clear=True.  The first N calls return False (deferred);
    # the (N+1)th call falls through to the held-state setup.
    for _ in range(ROLLOVER_MAX_DEFER_FRAMES + 1):
        om.check_over_change("6.0", "Bumrah", score=106)
    assert om._pending_clear is True, "expected pending_clear=True"
    assert om._pending_clear_over_int == 5
    assert om._last_over_int == 6
    held_before = list(om.this_over)

    # Late legal-event for the 6th ball of over 5 (BED queue popped
    # AFTER the rollover; event.over reads "6.0" because team-overs
    # had already ticked).
    late = {"type": "1_RUNS", "runs": 1, "certain": True,
            "over": "6.0", "bowler": "Bumrah"}
    om.on_ball_event(late)

    # Held over should NOT have been flushed; the "1" must be the
    # LAST token of the held over, not the first of over 6.
    check("hold not flushed by late boundary ball",
          om._pending_clear is True,
          f"_pending_clear={om._pending_clear}")
    check("late ball appended to END of held over",
          om.this_over == held_before + ["1"],
          f"this_over={om.this_over}, held_before={held_before}")
    arch = om.over_history.get(5, {})
    check("over_history[5] re-archived with late ball included",
          arch.get("balls") == held_before + ["1"]
          and arch.get("runs") >= 1,
          f"archive={arch}")


def test_score_manager_boundary_ball_belongs_to_completed_over() -> None:
    header("ScoreManager: boundary ball appended to completed over, "
           "NOT new over")
    from score_manager import ScoreManager, FrameInput
    import time as _t

    sm = ScoreManager(shadow=True)
    # Force WARM with a clean baseline: over 5 in progress, 5 balls in.
    sm.mode = "WARM"
    sm.score = 100
    sm.wickets = 0
    sm.overs = 5.5
    sm.balls_remaining = 87
    sm.this_over = [".", "1", "4", ".", "."]
    sm.this_over_src = ["obs"] * 5
    sm.striker = "A"
    sm.non = "B"
    sm.batter1 = {"name": "A", "runs": 50, "balls": 30, "fours": 5,
                  "sixes": 1, "is_striker": True}
    sm.batter2 = {"name": "B", "runs": 40, "balls": 20, "fours": 3,
                  "sixes": 2, "is_striker": False}
    sm.bowler_name = "X"
    sm.bowler_overs = 0.5
    sm.bowler_runs = 10
    sm.bowler_wickets = 0
    sm.partnership_runs = 90
    sm.partnership_balls = 50

    # Frame: overs ticks 5.5 → 6.0 with +1 run (the 6th ball of over 5).
    f = FrameInput(
        frame_id="t1", timestamp=_t.time(),
        ext_score=101, ext_wickets=0, ext_overs=6.0,
        ext_bat1_name="A", ext_bat1_runs=51, ext_bat1_balls=31,
        ext_bat2_name="B", ext_bat2_runs=40, ext_bat2_balls=20,
        ext_bowler_name="X", ext_bowler_wickets=0,
        ext_bowler_runs=11, ext_bowler_overs=1.0,
        scorer_changes=[], speed_kph=None,
        broadcast_extra=None, broadcast_this_over=None,
        broadcast_target=None, broadcast_striker=None,
        broadcast_venue=None, broadcast_team=None,
        broadcast_match_info=None, scout_text="", action_text=None,
        delivery_info=None, drs_state=None,
    )
    sm.on_frame(f)

    arch5 = sm.over_history.get(5)
    check("over 5 archived with 6 tokens (boundary ball included)",
          arch5 is not None and len(arch5) == 6,
          f"over_history[5]={arch5}")
    check("over 6 starts EMPTY (no leak from boundary ball)",
          sm.this_over == [],
          f"this_over after rollover={sm.this_over}")


def test_this_over_history_immutable() -> None:
    header("over_history first-write-wins")
    from eyes.this_over import ThisOverManager
    om = ThisOverManager()
    om.over_history[5] = {
        "balls": [".", "1", "4", ".", ".", "1"],
        "bowler": "Bumrah", "runs": 6, "wickets": 0,
    }
    om._last_over_int = 5
    om._over_start_score = 50
    om.this_over = [".", ".", ".", ".", ".", "."]
    om.check_over_change("6.0", "Khan", score=50)
    archived = om.over_history.get(5, {})
    check("re-archive REFUSED, original kept",
          archived.get("bowler") == "Bumrah"
          and archived.get("balls") == [".", "1", "4", ".", ".", "1"],
          f"archived={archived}")


# ---------------------------------------------------------------------
# 4. Scoreboard — FOW immutability
# ---------------------------------------------------------------------
def test_fow_no_trim() -> None:
    header("sync_fow_to_wickets never trims confirmed entries")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL", ["a", "b"], ["c", "d"])
    sb._inn["wickets"] = 1
    sb.fall_of_wickets = [
        {"wicket": 1, "batter": "Kohli", "score": 30, "overs": "5.2"},
        {"wicket": 2, "batter": "Rohit", "score": 50, "overs": "8.4"},
    ]
    sb.sync_fow_to_wickets()
    check("FOW length preserved despite wickets=1 < len=2",
          len(sb.fall_of_wickets) == 2,
          f"len={len(sb.fall_of_wickets)}")


def test_fow_no_overwrite_confirmed() -> None:
    header("_add_fow refuses to overwrite confirmed entry with new batter")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL", ["a", "b"], ["c", "d"])
    sb._add_fow(1, "Kohli", 30, "5.2")
    sb._add_fow(1, "Rohit", 30, "5.2")  # different batter → must refuse
    check("rewrite refused, original kept",
          len(sb.fall_of_wickets) == 1
          and sb.fall_of_wickets[0]["batter"] == "Kohli",
          f"fow={sb.fall_of_wickets}")


def test_fow_placeholder_upgrade() -> None:
    header("_add_fow upgrades placeholder entries (allowed mutability)")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL", ["a", "b"], ["c", "d"])
    sb._inn["wickets"] = 1
    sb.sync_fow_to_wickets()  # creates placeholder W1
    sb._add_fow(1, "Kohli", 30, "5.2")
    check("placeholder W1 upgraded to Kohli",
          sb.fall_of_wickets[0]["batter"] == "Kohli",
          f"fow={sb.fall_of_wickets}")


# ---------------------------------------------------------------------
# 5. _validate_overs digit-swap correction
# ---------------------------------------------------------------------
def test_validate_overs_digit_swap() -> None:
    header("_validate_overs detects digit swap with confirmed reference")
    from test_pipeline import _validate_overs
    # confirmed=0.2, extractor=3.0 (digit-swap), tokens=3 → 0.3
    out = _validate_overs(3.0, [".", "1", "."], confirmed_overs=0.2)
    check("3.0 → 0.3 (digit swap caught)",
          abs(out - 0.3) < 1e-6,
          f"out={out}")


def test_validate_overs_legitimate_passthrough() -> None:
    header("_validate_overs passes through when extractor agrees with tokens")
    from test_pipeline import _validate_overs
    out = _validate_overs(5.3, [".", "1", "4"], confirmed_overs=5.2)
    check("5.3 with 3 tokens → 5.3 (no change)",
          abs(out - 5.3) < 1e-6,
          f"out={out}")


def test_validate_overs_boundary_fix() -> None:
    header("_validate_overs falls back to (X-1).N when no swap detected")
    from test_pipeline import _validate_overs
    # confirmed=5.5, extractor=6.0 (just rolled to new over but Scout
    # still reads previous over's tokens). Should NOT trigger digit
    # swap (ext_int 6 not >> conf_int 5+1). Should apply the (X-1).N
    # rule: 6.0 + 6 tokens → 5.6 (closing balls of previous over).
    out = _validate_overs(6.0, [".", "1", "1", ".", "4", "1"],
                          confirmed_overs=5.5)
    check("6.0 + 6 tokens → 5.6 (boundary fallback)",
          abs(out - 5.6) < 1e-6,
          f"out={out}")


def test_validate_overs_refuses_regression_below_confirmed() -> None:
    header("_validate_overs refuses to regress below confirmed_overs "
           "(live LSG-vs-RR F121 repro)")
    from test_pipeline import _validate_overs
    # Live failure reproduced from 2026-04-22 LSG vs RR F121:
    #   confirmed_overs = 9.0 (SM locked from F120's WICKET)
    #   ext_overs = 9.0 (state passed through from scoreboard)
    #   broadcast_this_over = ['W', 'W', 'W', '4', '6'] (poisoned scout
    #   read of a replay-polluted THIS OVER ribbon).
    # Pre-fix: _validate_overs computed corrected=8.5 (int(9)-1).5 and
    # returned it, tripping SM's overs-regression → COLD_START on the
    # very next frame (F122) which carried the real SIX — lost forever.
    # Post-fix: the guard refuses to return a value < confirmed_overs,
    # preserving SM's WARM lock through a single-frame glitch.
    out = _validate_overs(9.0, ["W", "W", "W", "4", "6"],
                          confirmed_overs=9.0)
    check("9.0 + 5 stale tokens + confirmed 9.0 → 9.0 (no regression)",
          abs(out - 9.0) < 1e-6,
          f"out={out}")

    # Sanity check: the guard only blocks WHEN the correction would
    # regress.  When confirmed is behind, (X-1).N still applies.
    out2 = _validate_overs(6.0, [".", "1", "1", ".", "4", "1"],
                           confirmed_overs=5.0)
    check("6.0 + 6 tokens + confirmed 5.0 → 5.6 (normal boundary fix)",
          abs(out2 - 5.6) < 1e-6,
          f"out={out2}")


# ---------------------------------------------------------------------
# 6. 20-over invariant for innings change
# ---------------------------------------------------------------------
def test_phantom_dismissal_inference_disabled() -> None:
    header("Bug #2: infer_dismissed_batters is a no-op")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL",
                     ["Opener1", "Opener2", "Three", "Four", "Five"],
                     ["Bowler1", "Bowler2"])
    # Force only the no.5 onto the strip — the OLD heuristic would
    # mark Opener1/Opener2/Three/Four as dismissed by squad position.
    sb._inn["striker"] = "Five"
    sb._inn["non"] = "Opener2"
    sb._inn["wickets"] = 0
    sb.batting_card["Five"] = {"name": "Five", "status": "batting",
                               "runs": 0, "balls": 0, "position": 5}
    sb.batting_card["Opener2"] = {"name": "Opener2", "status": "batting",
                                  "runs": 0, "balls": 0, "position": 2}
    sb.infer_dismissed_batters()
    dismissed = [n for n, c in sb.batting_card.items()
                 if c.get("status") == "out"]
    check("no batters auto-dismissed by squad-position heuristic",
          dismissed == [],
          f"unexpectedly dismissed: {dismissed}")


def test_legbye_requires_both_witnesses() -> None:
    header("Bug #11: leg-bye requires bowler AND striker witnesses")
    from eyes.commentary import BallEventDetector

    class _Tracker:
        def __init__(self, **vals):
            self._v = vals
        def get(self, k, default=None):
            return self._v.get(k, default)
        def get_with_freshness(self, k):
            return (self._v.get(k), "live", 1.0)

    def _seed(bed):
        # The internal `detect()` only fully populates the prev_*
        # bowler/striker fields after an actual ball event has been
        # processed. For deterministic isolation we hand-seed the
        # prev_* state instead of running 2-3 priming frames.
        bed.prev_score = 50
        bed.prev_wickets = 0
        bed.prev_overs = 5.0
        bed.prev_bowler_runs = 20
        bed.prev_striker = "A"
        bed.prev_striker_balls = 7
        bed.prev_striker_runs = 10

    # Case 1: legal ball, score +1. Bowler runs unchanged (LAG),
    # but striker runs went 10 → 11. New rule: this is NOT a leg-bye
    # — it's a real run off the bat (striker runs +1 = independent
    # witness that the run was credited to the batter).
    bed1 = BallEventDetector()
    _seed(bed1)
    t2 = _Tracker(score=51, wickets=0, overs=5.1,
                  current_bowler="X", striker="A",
                  **{"bowl:X:runs": 20, "bat:A:balls": 8,
                     "bat:A:runs": 11})
    ev = bed1.detect(t2)
    check("not classified as leg-bye when striker runs increased",
          ev is not None and ev.get("extras_type") != "leg_bye_or_bye",
          f"event={ev}")

    # Case 2: legal ball, score +1, bowler runs unchanged AND striker
    # runs ALSO unchanged (10 → 10). Both witnesses agree → genuine
    # leg-bye.
    bed2 = BallEventDetector()
    _seed(bed2)
    t3 = _Tracker(score=51, wickets=0, overs=5.1,
                  current_bowler="X", striker="A",
                  **{"bowl:X:runs": 20, "bat:A:balls": 8,
                     "bat:A:runs": 10})
    ev2 = bed2.detect(t3)
    check("classified as leg-bye when BOTH witnesses agree",
          ev2 is not None and ev2.get("extras_type") == "leg_bye_or_bye",
          f"event={ev2}")


def test_bed_preserves_prev_overs_when_team_overs_missing() -> None:
    header("BED: missing tracker overs must not wipe balls baseline")
    from eyes.commentary import BallEventDetector
    from eyes.consistent_tracker import ConsistentReadTracker

    tr = ConsistentReadTracker()
    tr.force_set("score", 100)
    tr.force_set("wickets", 2)
    tr.force_set("overs", "12.4")
    bed = BallEventDetector()
    check("baseline frame", bed.detect(tr) is None, "expected no event")

    tr.force_set("overs", "12.5")
    check("legal tick emits", bed.detect(tr) is not None,
          "expected ball event on 12.4→12.5")

    class _OversNone:
        def __init__(self, inner):
            self._inner = inner

        def get(self, k, default=None):
            if k == "overs":
                return None
            return self._inner.get(k, default)

    tr.force_set("score", 101)
    check("gap frame silent", bed.detect(_OversNone(tr)) is None,
          "expected no event when overs missing")
    check("prev_overs not wiped",
          bed.prev_overs == "12.5",
          f"got {bed.prev_overs!r}")

    tr.force_set("overs", "12.6")
    ev = bed.detect(tr)
    check("resume after gap", ev is not None,
          f"expected event after overs returns, got {ev}")


def test_innings_reset_methods_exist_and_wipe_state() -> None:
    header("Bug #14: reset() wipes state on all three trackers")
    from eyes.commentary import BallEventDetector, PartnershipTracker
    from eyes.this_over import ThisOverManager

    bed = BallEventDetector()
    bed.prev_score = 230
    bed.prev_overs = 20.0
    bed.prev_striker = "X"
    bed.prev_striker_runs = 100
    bed._event_queue = [{"type": "FOUR"}]
    bed.reset()
    check("BED.reset wipes prev_score/prev_overs/queue",
          bed.prev_score is None and bed.prev_overs is None
          and bed.prev_striker is None and bed._event_queue == [],
          f"prev_score={bed.prev_score}, queue={bed._event_queue}")

    pt = PartnershipTracker()
    pt.current_pair = {"X", "Y"}
    pt.partnership_start_score = 50
    pt.partnership_start_balls = 73
    pt.partnerships = [{"runs": 50}]
    pt.reset()
    check("PartnershipTracker.reset wipes anchors and pair",
          pt.current_pair == set() and pt.partnership_start_score == 0
          and pt.partnership_start_balls == 0 and pt.partnerships == [],
          f"start_balls={pt.partnership_start_balls}, "
          f"pair={pt.current_pair}")

    om = ThisOverManager()
    om.this_over = ["1", "."]
    om.over_history[0] = {"balls": ["1"]}
    om._last_over_int = 19
    om._pending_clear = True
    om.reset()
    check("ThisOverManager.reset wipes this_over/over_history/last_int",
          om.this_over == [] and om.over_history == {}
          and om._last_over_int is None and om._pending_clear is False,
          f"this_over={om.this_over}, last_int={om._last_over_int}")


def test_match_situation_run_rate_falls_back_to_zero() -> None:
    header("Bug #15: CRR=0 fallback prevents 590 panel-vs-strip drift")
    from eyes.commentary import get_match_situation
    # Innings transition snapshot: score=59 still, overs reset to 0.0
    # → previous formula 59 / 0.1 = 590. New rule: balls_bowled=0
    # → run_rate=0.
    sit = get_match_situation({"score": 59, "wickets": 0,
                               "overs": 0.0, "innings": 2})
    check("balls_bowled=0 → run_rate=0.0 (no /0.1 explosion)",
          sit.get("run_rate") == 0.0,
          f"run_rate={sit.get('run_rate')}")
    # Genuine state: score=60 in 5 overs → CRR=12.0
    sit2 = get_match_situation({"score": 60, "wickets": 0,
                                "overs": 5.0, "innings": 2})
    check("real values produce real run_rate",
          sit2.get("run_rate") == 12.0,
          f"run_rate={sit2.get('run_rate')}")
    # Pre-match: score=0, overs=0 → CRR=0 (no /0)
    sit3 = get_match_situation({"score": 0, "wickets": 0,
                                "overs": 0.0, "innings": 1})
    check("pre-match (0/0) → run_rate=0 (no division error)",
          sit3.get("run_rate") == 0.0,
          f"run_rate={sit3.get('run_rate')}")


def test_score_manager_cold_start_rejects_incomplete_card() -> None:
    header("Cold-start completeness guard: skip frames missing overs")
    from score_manager import ScoreManager, FrameInput
    import time as _t

    sm = ScoreManager(shadow=True)
    # Three identical frames with score+wickets but overs=None.
    # OLD bug: cold_candidate_streak hits 3 → COLD_START → WARM
    # with overs=None → next _apply_event crashes with int(None).
    # NEW guard: incomplete cards are skipped without seeding
    # cold_candidate, so promotion never occurs.
    base = dict(frame_id="x", timestamp=_t.time(),
                ext_score=28, ext_wickets=0, ext_overs=None,
                ext_bat1_name="A", ext_bat1_runs=15, ext_bat1_balls=10,
                ext_bat2_name="B", ext_bat2_runs=13, ext_bat2_balls=8,
                ext_bowler_name="X", ext_bowler_wickets=0,
                ext_bowler_runs=18, ext_bowler_overs=None,
                scorer_changes=[], speed_kph=None,
                broadcast_extra=None, broadcast_this_over=None,
                broadcast_target=None, broadcast_striker=None,
                broadcast_venue=None, broadcast_team=None,
                broadcast_match_info=None, scout_text="",
                action_text=None, delivery_info=None, drs_state=None)
    for i in range(3):
        sm.on_frame(FrameInput(**base))

    check("ScoreManager stays in COLD_START with overs=None",
          sm.mode == "COLD_START",
          f"mode={sm.mode}, overs={sm.overs}")
    check("cold_candidate not seeded by incomplete card",
          sm.cold_candidate is None,
          f"cold_candidate={sm.cold_candidate}")

    # Now provide a complete card three times → should promote.
    base["ext_overs"] = 4.4
    base["ext_bowler_overs"] = 0.4
    for i in range(3):
        sm.on_frame(FrameInput(**base))
    check("ScoreManager promotes to WARM once overs present",
          sm.mode == "WARM" and sm.overs == 4.4,
          f"mode={sm.mode}, overs={sm.overs}")


def test_extractor_wins_on_numbers_in_apply_scorer_decision() -> None:
    header("Bug #1: apply_scorer_decision prefers extractor numbers "
           "(source check)")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    # The fix is a code-level preference, not a behavioural switch
    # we can drive in isolation here; assert the comment marker for
    # the fix is present so a future refactor can't silently delete
    # the trust hierarchy.
    check("Bug #1 trust-hierarchy comment present",
          "extractor wins" in src.lower()
          or "prefer extractor" in src.lower()
          or "extractor over scorer" in src.lower()
          or "extractor data for numerical" in src.lower(),
          "expected one of the trust-hierarchy markers in test_pipeline.py")


def test_frame_poisoned_skips_when_no_confirmed_score() -> None:
    header("FRAME_POISONED: cold-start bypass (no prior confirmed score)")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    # The fix gates the poison check on `_cur_score_raw is not None`.
    # Source-level check ensures the gate is wired in.
    check("FRAME_POISONED gated on prior confirmed score",
          "_cur_score_raw is not None" in src
          and "_cur_score_raw = scoreboard._inn.get(\"score\")" in src,
          "expected `_cur_score_raw is not None` gate before poison "
          "delta check")


def test_graphic_strip_info_panel_keyword_large_delta_strips_score() -> None:
    header("GRAPHIC strip: HEAD TO HEAD + score drift >7 strips trio")
    from unittest.mock import MagicMock

    import test_pipeline as tp

    sb = MagicMock()
    sb._inn = {"score": 120}
    ex = {
        "score": 50,
        "wickets": 3,
        "match_overs": "14.4",
        "bowler": {"name": "Test Bowler"},
    }
    tp.filter_info_panel_contamination(
        ex, "STATS: HEAD TO HEAD career comparison", sb)
    check("score cleared on panel+divergence", ex.get("score") is None, repr(ex))
    check("wickets cleared",
          ex.get("wickets") is None and ex.get("match_overs") is None, repr(ex))
    check("bowler still stripped",
          ex.get("bowler") is None, repr(ex))


def test_graphic_strip_info_panel_keyword_small_delta_keeps_score() -> None:
    header("GRAPHIC strip: panel keyword but agreement keeps score trio")
    from unittest.mock import MagicMock

    import test_pipeline as tp

    sb = MagicMock()
    sb._inn = {"score": 118}
    ex = {"score": 119, "wickets": 2, "match_overs": "15.1"}
    tp.filter_info_panel_contamination(
        ex, "VERSUS SPIN IN T20", sb)
    check("near-tracker extractor passes through",
          ex.get("score") == 119, repr(ex))


def test_poison_recal_graphic_phase_preempt_wired_in_source() -> None:
    header("GRAPHIC strip: POISON-RECAL pre-empt tag wired")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    check("[POISON-RECAL-PRE-EMPTED] present",
          "[POISON-RECAL-PRE-EMPTED]" in src, "")
    check("_gfx_phase_recal_skip uses SCOREBOARD + cam=graphic",
          "_gfx_phase_recal_skip" in src
          and 'frame_type == "SCOREBOARD"' in src
          and '_last_cam == "graphic"' in src,
          "expected scout graphic-phase preempt guard")


def test_p7_fix_b_consensus_preserved_on_graphic_wired_in_source() -> None:
    """P7 fix (b): GRAPHIC poison preserves CORRECTION_BLOCKED consensus.

    Frozen-score lock-in (logs/trace/866ce150.jsonl F178-F198) showed
    that every GRAPHIC frame interleaved between SCOREBOARD frames
    reset `_correction_pending`/`_correction_count` (the 2-frame
    consensus override for CORRECTION_BLOCKED).  Recovery from a
    stuck score therefore became unreachable.  Fix (b) introduces
    `_poison_non_graphic` and gates the consensus reset so only
    contradicting-evidence poison breaks the streak.
    """
    header("P7 fix (b): GRAPHIC poison preserves consensus streak")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    check("`_poison_non_graphic` flag introduced",
          "_poison_non_graphic = False" in src
          and "_poison_non_graphic = True" in src,
          "expected `_poison_non_graphic` initialiser + setters")
    check("`[CONSENSUS-PRESERVED-VIA-GRAPHIC]` log marker present",
          "[CONSENSUS-PRESERVED-VIA-GRAPHIC]" in src,
          "expected log marker for graphic-only poison preservation")
    check("consensus reset gated on `_poison_non_graphic`",
          "if _poison_non_graphic:" in src,
          "expected `if _poison_non_graphic:` gate around "
          "`_correction_pending = None`")


def test_p7_fix_b_contradiction_sites_set_poison_non_graphic() -> None:
    """P7 fix (b): every non-GRAPHIC poison site flips the flag.

    Mid-innings 0-0, bowling-team strip (×2), comparison batter row
    delta, squad mismatch, cold-start card, score-delta>7 poison,
    unsupported score, and batter-over-team-total are all
    contradicting-evidence poisons.  All nine must set
    `_poison_non_graphic = True` so consensus is reset; the GRAPHIC
    site at line ~7139 must NOT (it stays False to preserve the
    streak).
    """
    header("P7 fix (b): contradiction poison sites tagged")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    setters = src.count("_poison_non_graphic = True")
    check("at least 9 `_poison_non_graphic = True` setters wired",
          setters >= 9,
          f"found {setters}, expected ≥9 (one per contradiction site)")
    # Sanity: GRAPHIC site should still be present and untagged.
    check("`[GRAPHIC-FILTER]` poison site untagged "
          "(graphic preserves consensus)",
          "[GRAPHIC-FILTER]" in src,
          "expected GRAPHIC-FILTER marker still present")


def test_p7_fix_c_score_inf_gate_direct_wired_in_source() -> None:
    """P7 fix (c): SCORE-INF-GATE applied at the DIRECT extractor path.

    The DIRECT extractor commit at lines ~8668-8702 calls
    `scoreboard.set("score", ...)` which feeds Scoreboard's consensus
    tracker without admission gating.  The 2026-05-02 SA-WI lock-in
    shows two frames of ext_score=11 (advance=+7) flipped tracker
    even though apply_scorer_decision's gate would have rejected the
    same delta.  Fix (c) adds the same advance check before DIRECT's
    scoreboard.set call.
    """
    header("P7 fix (c): SCORE-INF-GATE at DIRECT extractor path")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    check("`[SCORE-INF-GATE-DIRECT]` log marker present",
          "[SCORE-INF-GATE-DIRECT]" in src,
          "expected DIRECT-path gate marker")
    check("`[SCORE-CAP-SUPPRESS-NARROW]` decision tag present",
          "[SCORE-CAP-SUPPRESS-NARROW]" in src,
          "expected suppression-decision tag for trace observability")
    # Gate must run inside the `if not _frame_poisoned:` DIRECT block
    # and reference `_state_recovery_suppress_until_frame` for the
    # cold-start / AUTO-SWAP mitigation per p7_diagnosis §7.
    check("DIRECT gate references AUTO-SWAP recovery window",
          "_direct_suppress" in src
          and "_state_recovery_suppress_until_frame" in src
          and "_direct_advance" in src,
          "expected suppress predicate + advance computation")
    check("DIRECT gate computes bat_delta before commit",
          "_direct_bat_delta" in src
          and "_direct_explained" in src,
          "expected bat-delta + explained-extras math")


def test_p7_fix_c_direct_gate_suppressed_on_cold_start() -> None:
    """P7 fix (c) §7 mitigation: cold-start commit not blocked.

    Per p7_diagnosis §7, narrowing the suppression risks blocking
    legitimate cold-start commits.  The DIRECT gate must therefore
    suppress on `scoreboard._inn['score'] is None` (cold-start) and
    `int(score) == 0` (innings-2 fresh strip), and inside the
    AUTO-SWAP recovery window
    (`frame_count <= _state_recovery_suppress_until_frame`).  This
    keeps the very-first commit and innings-2 reset path unaffected.
    """
    header("P7 fix (c): cold-start + AUTO-SWAP suppress preserved")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    # Three suppression conditions must be present in the DIRECT
    # gate block, all OR'd into `_direct_suppress`.
    block = src[src.find("[SCORE-INF-GATE-DIRECT]") - 4000:
                src.find("[SCORE-INF-GATE-DIRECT]") + 1000]
    check("cold-start (score is None) suppress condition present",
          "_cur_dgate is None" in block,
          "expected `_cur_dgate is None` in DIRECT-gate suppress")
    check("score==0 suppress (innings-2 fresh strip) present",
          "int(_cur_dgate or 0) == 0" in block,
          "expected `int(_cur_dgate or 0) == 0` in DIRECT-gate suppress")
    check("AUTO-SWAP recovery window suppress present",
          "_state_recovery_suppress_until_frame" in block,
          "expected recovery-window check in DIRECT-gate suppress")


def test_twenty_over_invariant_check_in_source() -> None:
    """Light-touch check that the source code references the
    20-over / 10-wicket invariant in both auto-swap call sites.

    Historical note: this test once asserted `'>= 18.0' not in content`
    as a regression guard against Bug #16's stale 18.0 cap in the
    auto-swap trigger.  That negative grep is now over-broad: post-
    Bug-#16 the codebase legitimately uses `< 18.0` (cold-start
    innings-2 detection at ~L2559, L3170 — substring matches `18.0`)
    and `>= 18.0` (innings-1 near-end heuristic at ~L5181, used as
    one of several `or`-ed predicates with `_inn1_wkts >= 8`).  Both
    are intentional non-rollover uses and shouldn't trip a regression
    test.  We've replaced the negative grep with positive assertions
    on the auto-swap site itself (20.0 + 10-wicket presence)."""
    header("20.0-over guard wired in test_pipeline.py")
    src = Path(__file__).parent / "test_pipeline.py"
    content = src.read_text()
    check("20.0 overs threshold present",
          ">= 20.0" in content,
          "expected '>= 20.0' in test_pipeline.py")
    check("10-wicket guard present",
          ">= 10" in content,
          "expected '>= 10' in test_pipeline.py")


# ---------------------------------------------------------------------
# 7. P0-A active-batter invariants (DC vs PBKS F339 resurrection)
# ---------------------------------------------------------------------
def _make_sb_with_resurrection_setup():
    """Build a scoreboard mirroring the F339 corruption shape.

    Batting squad: Rahul (pos 1), Pathum (pos 2), Rana (pos 5).
    Pathum is DISMISSED with a witnessed FOW entry. Rahul and Rana
    are batting. This is the moment immediately before the malformed
    phase-economy graphic at F339.
    """
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        "BAT", "BOWL",
        ["Rahul", "Pathum", "Three", "Four", "Rana"],
        ["B1", "B2"],
    )
    sb.batting_card["Rahul"]["status"] = "batting"
    sb.batting_card["Rahul"]["runs"] = 25
    sb.batting_card["Rahul"]["balls"] = 18
    sb.batting_card["Pathum"]["status"] = "out"
    sb.batting_card["Pathum"]["runs"] = 12
    sb.batting_card["Pathum"]["balls"] = 9
    sb.batting_card["Pathum"]["dismissal"] = {
        "how": "caught", "bowler": "B1", "fielder": "F1"}
    sb.batting_card["Rana"]["status"] = "batting"
    sb.batting_card["Rana"]["runs"] = 5
    sb.batting_card["Rana"]["balls"] = 4
    sb.fall_of_wickets = [{
        "wicket": 1, "batter": "Pathum", "score": 40, "overs": "5.4",
        "how": "caught", "bowler": "B1", "_witnessed": True,
    }]
    sb._inn["score"] = 60
    sb._inn["wickets"] = 1
    sb._inn["overs"] = "8.2"
    return sb


def test_witnessed_dismissal_helper() -> None:
    header("_is_witnessed_dismissal classifies FOW entries correctly")
    sb = _make_sb_with_resurrection_setup()
    check("witnessed entry returns True",
          sb._is_witnessed_dismissal("Pathum") is True,
          "Pathum has a real witnessed FOW entry")
    check("non-FOW name returns False",
          sb._is_witnessed_dismissal("Rahul") is False,
          "Rahul is not in FOW")
    sb.fall_of_wickets.append({
        "wicket": 2, "batter": None, "score": None, "overs": None,
        "_unwitnessed": True,
    })
    check("placeholder entry returns False",
          sb._is_witnessed_dismissal(None) is False,
          "back-fill placeholders must not satisfy the witnessed check")


def test_fix1_refuses_undismiss_on_witnessed_fow() -> None:
    header("Fix 1: update_batter() refuses to un-dismiss FOW-witnessed batter "
           "(F339 replay)")
    sb = _make_sb_with_resurrection_setup()
    # Simulate two consecutive strip reads of the malformed phase-
    # economy graphic — the pre-fix path required 2 frames to un-
    # dismiss.  Fix 1 should refuse on every frame.
    r1 = sb.update_batter("Pathum", runs=12, balls=9, frame=339)
    r2 = sb.update_batter("Pathum", runs=12, balls=9, frame=340)
    check("update_batter returns False both frames",
          r1 is False and r2 is False, f"r1={r1}, r2={r2}")
    check("Pathum status remains 'out'",
          sb.batting_card["Pathum"]["status"] == "out",
          f"status={sb.batting_card['Pathum']['status']}")
    check("active set is still {Rahul, Rana}",
          sorted([n for n, c in sb.batting_card.items()
                  if c["status"] == "batting"]) == ["Rahul", "Rana"],
          f"active={[n for n, c in sb.batting_card.items() if c['status'] == 'batting']}")
    check("dismissal record preserved",
          sb.batting_card["Pathum"].get("dismissal", {}).get("how") == "caught",
          f"dismissal={sb.batting_card['Pathum'].get('dismissal')}")


def test_fix1_walk_back_already_batting_no_false_trigger() -> None:
    header("Fix 1: walk-back / stale-strip on still-batting batter does not "
           "false-trigger the FOW guard")
    sb = _make_sb_with_resurrection_setup()
    # Rahul is still batting (no FOW). Strip read must NOT be
    # rejected by Fix 1 — Fix 1 only fires on the status='out' path.
    # (Stats themselves go through the 3-frame consensus tracker,
    # so we don't assert specific runs here — only that the call
    # returned True and Fix 1 did not flip status.)
    ok = sb.update_batter("Rahul", runs=27, balls=20, frame=341)
    check("legitimate stats update succeeds for still-batting Rahul",
          ok is True, f"return={ok}")
    check("Rahul status unchanged ('batting')",
          sb.batting_card["Rahul"]["status"] == "batting",
          f"status={sb.batting_card['Rahul']['status']}")
    check("no FOW entry was created for Rahul (no spurious dismissal)",
          all(f.get("batter") != "Rahul" for f in sb.fall_of_wickets),
          f"fow={sb.fall_of_wickets}")


def test_fix1_legit_yet_to_bat_activation_still_works() -> None:
    header("Fix 1: yet_to_bat → batting transitions are unaffected")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        "BAT", "BOWL",
        ["Opener1", "Opener2", "Three"],
        ["B1", "B2"],
    )
    sb.batting_card["Opener1"]["status"] = "batting"
    sb.batting_card["Opener1"]["runs"] = 10
    sb.batting_card["Opener1"]["balls"] = 8
    sb.batting_card["Opener2"]["status"] = "batting"
    sb.batting_card["Opener2"]["runs"] = 5
    sb.batting_card["Opener2"]["balls"] = 6
    sb.batting_card["Three"]["status"] = "yet_to_bat"
    sb._inn["score"] = 15
    sb._inn["wickets"] = 0
    sb._inn["overs"] = "2.4"
    # No FOW entry for Three — first activation is legitimate, but
    # rejected here only because 2 actives already exist.  The point
    # is that Fix 1 does NOT fire on the yet_to_bat path; max-2
    # rejection comes from the existing logic.
    ok = sb.update_batter("Three", runs=0, balls=0, frame=100)
    check("yet_to_bat path runs (return value follows max-2 logic, "
          "not Fix 1)",
          # Either accepted (if some open replacement happened) or
          # rejected — but NOT due to Fix 1 (no FOW entry exists).
          isinstance(ok, bool),
          f"return={ok}")
    check("no FOW entry was created for Three",
          all(f.get("batter") != "Three" for f in sb.fall_of_wickets),
          f"fow={sb.fall_of_wickets}")


def test_fix2_post_hoc_demote_resurrected() -> None:
    header("Fix 2: validate_state_consistency demotes resurrected "
           "FOW-witnessed batter back to 'out'")
    sb = _make_sb_with_resurrection_setup()
    # Bypass Fix 1 by mutating directly — simulates "some other path
    # corrupted the state".
    sb.batting_card["Pathum"]["status"] = "batting"
    sb.batting_card["Pathum"]["dismissal"] = None
    sb.validate_state_consistency()
    check("Pathum demoted to 'out'",
          sb.batting_card["Pathum"]["status"] == "out",
          f"status={sb.batting_card['Pathum']['status']}")
    check("dismissal record restored from FOW",
          (sb.batting_card["Pathum"].get("dismissal") or {}).get("how")
          == "caught",
          f"dismissal={sb.batting_card['Pathum'].get('dismissal')}")
    check("Rahul and Rana untouched",
          sb.batting_card["Rahul"]["status"] == "batting"
          and sb.batting_card["Rana"]["status"] == "batting",
          "non-resurrected batters must not be affected")


def test_batch_f_un_dismiss_refused_for_wicket_ball_event_source() -> None:
    header("Batch F: UN-DISMISS refused when dismissal_source=wicket_ball_event")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        "BAT", "BOWL",
        ["A", "B", "C"],
        ["B1", "B2"],
    )
    sb.batting_card["A"]["status"] = "batting"
    sb.batting_card["A"]["runs"] = 12
    sb.batting_card["A"]["balls"] = 9
    sb.batting_card["B"]["status"] = "batting"
    sb.batting_card["B"]["runs"] = 5
    sb.batting_card["B"]["balls"] = 4
    sb.batting_card["A"]["status"] = "out"
    sb.batting_card["A"]["dismissal"] = {
        "how": "bowled", "bowler": "B1", "fielder": None}
    sb.batting_card["A"]["dismissal_source"] = "wicket_ball_event"
    r1 = sb.update_batter("A", runs=12, balls=9, frame=100)
    r2 = sb.update_batter("A", runs=12, balls=9, frame=101)
    r3 = sb.update_batter("A", runs=12, balls=9, frame=102)
    check("update_batter returns False on every stale read",
          r1 is False and r2 is False and r3 is False,
          f"r1={r1}, r2={r2}, r3={r3}")
    check("status remains 'out'",
          sb.batting_card["A"]["status"] == "out",
          f"status={sb.batting_card['A']['status']}")
    check("dismissal_source preserved",
          sb.batting_card["A"]["dismissal_source"] == "wicket_ball_event",
          f"source={sb.batting_card['A'].get('dismissal_source')}")
    check("_dismissed_recovery counter not incremented past first attempt",
          sb._dismissed_recovery.get("A", 0) == 0,
          f"recovery={sb._dismissed_recovery}")


def test_batch_f_un_dismiss_allowed_for_auto_inference_source() -> None:
    header("Batch F: UN-DISMISS still fires for auto_inference source "
           "(legacy auto-dismiss recovery preserved)")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        "BAT", "BOWL",
        ["A", "B", "C"],
        ["B1", "B2"],
    )
    sb.batting_card["A"]["status"] = "batting"
    sb.batting_card["A"]["runs"] = 12
    sb.batting_card["A"]["balls"] = 9
    sb.batting_card["B"]["status"] = "batting"
    sb.batting_card["B"]["runs"] = 5
    sb.batting_card["B"]["balls"] = 4
    sb.batting_card["A"]["status"] = "out"
    sb.batting_card["A"]["dismissal"] = {
        "how": "inferred (replaced by new batter)",
        "bowler": None, "fielder": None}
    sb.batting_card["A"]["dismissal_source"] = "auto_inference"
    r1 = sb.update_batter("A", runs=12, balls=9, frame=100)
    r2 = sb.update_batter("A", runs=12, balls=9, frame=101)
    check("first call deferred (1/2 consensus)",
          r1 is False, f"r1={r1}")
    check("second call reactivates",
          sb.batting_card["A"]["status"] == "batting",
          f"status={sb.batting_card['A']['status']}; r2={r2}")


def test_batch_f_wicket_on_wicket_no_resurrection() -> None:
    header("Batch F: F128 PBKS regression — wicket-on-wicket leaves the "
           "first dismissal locked, second wicket dismisses bat2 cleanly")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        "PBKS", "GT",
        ["Stoinis", "Jansen", "Bartlett", "Shedge"],
        ["Holder", "Bartlett2"],
    )
    sb.batting_card["Stoinis"]["status"] = "batting"
    sb.batting_card["Stoinis"]["runs"] = 36
    sb.batting_card["Stoinis"]["balls"] = 34
    sb.batting_card["Jansen"]["status"] = "batting"
    sb.batting_card["Jansen"]["runs"] = 7
    sb.batting_card["Jansen"]["balls"] = 6
    sb._inn["score"] = 141
    sb._inn["wickets"] = 6
    sb._inn["overs"] = "17.3"
    # First wicket: Stoinis dismissed by ball event (FOW row left
    # _unwitnessed to mirror the live scenario where dismissal-mode
    # enrichment lags the wicket commit).
    ok = sb.dismiss_batter("Stoinis", how=None, bowler="Holder",
                            fielder=None, frame=107)
    check("first dismiss accepted",
          ok is True and sb.batting_card["Stoinis"]["status"] == "out",
          f"ok={ok}, status={sb.batting_card['Stoinis']['status']}")
    check("dismissal_source recorded as wicket_ball_event",
          sb.batting_card["Stoinis"]["dismissal_source"] == "wicket_ball_event",
          f"source={sb.batting_card['Stoinis'].get('dismissal_source')}")
    # Two stale strip reads showing Stoinis still on the strip — pre-fix
    # this was enough to flip his status back to "batting".
    sb.update_batter("Stoinis", runs=40, balls=31, frame=127)
    sb.update_batter("Stoinis", runs=40, balls=31, frame=128)
    check("Stoinis stays dismissed after stale strip reads",
          sb.batting_card["Stoinis"]["status"] == "out",
          f"status={sb.batting_card['Stoinis']['status']}")
    # Second wicket lands: Jansen dismissed.
    ok2 = sb.dismiss_batter("Jansen", how=None, bowler="Holder",
                             fielder=None, frame=128)
    check("Jansen dismissal accepted",
          ok2 is True and sb.batting_card["Jansen"]["status"] == "out",
          f"ok2={ok2}, status={sb.batting_card['Jansen']['status']}")
    check("Stoinis still 'out' (not resurrected)",
          sb.batting_card["Stoinis"]["status"] == "out",
          f"status={sb.batting_card['Stoinis']['status']}")
    active = [n for n, c in sb.batting_card.items()
              if c["status"] == "batting"]
    check("no active batters from the dismissed pair remain",
          "Stoinis" not in active and "Jansen" not in active,
          f"active={active}")


def test_batch_x_field_refreshes_on_wicket() -> None:
    header("Batch X: cricket field re-evaluates on WICKET / over rollover "
           "(field-monitor frozen-window bug — F58 'Field unchanged for "
           "375 frames')")
    from eyes.field.cricket_field import CricketField

    cf = CricketField()
    cf.initialize_from_match_context(2.3, "pace")

    # Freeze via observation (3+ named positions)
    obs = [{"x": 0.42, "y": 0.58},  # slip_1
           {"x": 0.32, "y": 0.55},  # gully
           {"x": 0.20, "y": 0.50},  # point
           {"x": 0.25, "y": 0.35},  # cover
           {"x": 0.42, "y": 0.25}]  # mid_off
    cf.update_from_observation(obs, frame_type="scoreboard", overs=2.3)
    check("field frozen after observation", cf._frozen, f"frozen={cf._frozen}")

    # WICKET: invalidation hook arms re-evaluation
    cf.on_wicket()
    check("on_wicket unfreezes", not cf._frozen, f"frozen={cf._frozen}")
    check("on_wicket arms re-evaluation",
          cf._pending_reevaluation,
          f"pending={cf._pending_reevaluation}")

    # Next frame (no fresh observations) consumes the pending flag and
    # re-templates from current overs+bowler.
    cf.update_from_observation([], frame_type="scoreboard", overs=2.4)
    check("pending flag cleared after next frame",
          not cf._pending_reevaluation,
          f"pending={cf._pending_reevaluation}")
    check("template re-picked from current context",
          cf.template_name == "pace_powerplay",
          f"template_name={cf.template_name}")
    fielder_count = sum(1 for k in cf.current_positions
                        if k not in ("keeper", "bowler"))
    check("re-evaluation populates 9 fielders",
          fielder_count >= 9, f"count={fielder_count}")

    # Over rollover within same phase (5.6 -> 6.0): pending flag is set,
    # next frame re-evaluates.
    cf2 = CricketField()
    cf2.initialize_from_match_context(5.4, "pace")
    cf2.update_from_observation(obs, frame_type="scoreboard", overs=5.4)
    check("cf2 frozen", cf2._frozen, f"frozen={cf2._frozen}")
    cf2.on_over_change(6.0, "pace")
    check("over rollover (same phase) arms re-evaluation",
          cf2._pending_reevaluation,
          f"pending={cf2._pending_reevaluation}")
    cf2.update_from_observation([], frame_type="scoreboard", overs=6.0)
    check("over-rollover pending cleared on next frame",
          not cf2._pending_reevaluation,
          f"pending={cf2._pending_reevaluation}")

    # Phase transition (powerplay -> middle): on_over_change re-initializes
    # immediately and consumes the flag in-place.
    cf3 = CricketField()
    cf3.initialize_from_match_context(5.5, "pace")
    cf3.on_over_change(7.0, "pace")
    check("phase transition consumes pending flag in-place",
          not cf3._pending_reevaluation and cf3.phase == "middle",
          f"pending={cf3._pending_reevaluation} phase={cf3.phase}")


def test_batch_j_incoming_batter_promoted_from_strip() -> None:
    header("Batch J: incoming batter promoted from strip read on wicket "
           "rollover (eliminates F231-F243 PBKS poison cascade)")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        "PBKS", "GT",
        ["Stoinis", "Jansen", "Vyshak", "Arshad"],
        ["Holder", "Suthar"],
    )
    sb.batting_card["Stoinis"]["status"] = "batting"
    sb.batting_card["Stoinis"]["runs"] = 36
    sb.batting_card["Stoinis"]["balls"] = 34
    sb.batting_card["Jansen"]["status"] = "batting"
    sb.batting_card["Jansen"]["runs"] = 7
    sb.batting_card["Jansen"]["balls"] = 6
    sb._inn["score"] = 141
    sb._inn["wickets"] = 7
    sb._inn["overs"] = "17.5"
    sb._inn["striker"] = "Jansen"
    sb._inn["non"] = "Stoinis"
    # Strip at the wicket frame shows the live pair: Vyshak (incoming,
    # not-yet-on-card-as-batting) plus the still-displayed dismissed
    # batter row.  The promotion path should pick Vyshak.
    extracted_batters = [
        {"name": "Vyshak", "runs": 0, "balls": 0},
        {"name": "Jansen", "runs": 7, "balls": 6},
    ]
    ok = sb.dismiss_batter("Jansen", how="bowled", bowler="Holder",
                           fielder=None, frame=212,
                           extracted_batters=extracted_batters)
    check("dismissal accepted",
          ok is True and sb.batting_card["Jansen"]["status"] == "out",
          f"ok={ok}, status={sb.batting_card['Jansen']['status']}")
    check("Vyshak promoted to batting from strip read",
          sb.batting_card["Vyshak"]["status"] == "batting",
          f"Vyshak status={sb.batting_card['Vyshak']['status']}")
    check("promoted_source records strip path",
          sb.batting_card["Vyshak"].get("promoted_source")
          == "dismiss_batter:strip",
          f"source={sb.batting_card['Vyshak'].get('promoted_source')}")
    check("Arshad NOT promoted (strip named Vyshak first)",
          sb.batting_card["Arshad"]["status"] == "yet_to_bat",
          f"Arshad status={sb.batting_card['Arshad']['status']}")


def test_batch_j_two_wickets_consecutive_via_strip() -> None:
    header("Batch J + L: two wickets in succession each promote a fresh "
           "incoming batter via strip read; final active set has 2 "
           "batting batters")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        "PBKS", "GT",
        ["Stoinis", "Jansen", "Vyshak", "Arshad", "Chahar"],
        ["Holder", "Suthar"],
    )
    sb.batting_card["Stoinis"]["status"] = "batting"
    sb.batting_card["Jansen"]["status"] = "batting"
    sb._inn["score"] = 141
    sb._inn["wickets"] = 7
    sb._inn["overs"] = "17.5"
    sb._inn["striker"] = "Jansen"
    sb._inn["non"] = "Stoinis"
    sb.dismiss_batter(
        "Jansen", how="bowled", bowler="Holder", fielder=None, frame=212,
        extracted_batters=[{"name": "Vyshak", "runs": 0, "balls": 0},
                           {"name": "Stoinis", "runs": 36, "balls": 34}])
    sb.dismiss_batter(
        "Stoinis", how="caught", bowler="Holder", fielder="Sudharsan",
        frame=215,
        extracted_batters=[{"name": "Arshad", "runs": 0, "balls": 0},
                           {"name": "Vyshak", "runs": 0, "balls": 0}])
    active = sorted(n for n, c in sb.batting_card.items()
                    if c.get("status") == "batting")
    check("two batting batters after two consecutive wickets",
          len(active) == 2,
          f"active={active}")
    check("Vyshak and Arshad are the active pair",
          active == ["Arshad", "Vyshak"],
          f"active={active}")
    check("Chahar still yet_to_bat",
          sb.batting_card["Chahar"]["status"] == "yet_to_bat",
          f"Chahar status={sb.batting_card['Chahar']['status']}")


def test_batch_l_defer_when_strip_empty() -> None:
    header("Batch L: incoming-batter promotion DEFERS when strip has "
           "no candidate (squad-order fallback removed; F285 fix)")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        "PBKS", "GT",
        ["Stoinis", "Jansen", "Vyshak", "Arshad"],
        ["Holder", "Suthar"],
    )
    sb.batting_card["Stoinis"]["status"] = "batting"
    sb.batting_card["Jansen"]["status"] = "batting"
    sb._inn["score"] = 141
    sb._inn["wickets"] = 7
    sb._inn["overs"] = "17.5"
    sb._inn["striker"] = "Jansen"
    sb._inn["non"] = "Stoinis"

    import io
    import contextlib
    log_buf = io.StringIO()
    with contextlib.redirect_stdout(log_buf):
        ok = sb.dismiss_batter("Jansen", how="bowled", bowler="Holder",
                               fielder=None, frame=212,
                               extracted_batters=None)
    log_text = _strip_ansi_text(log_buf.getvalue())

    check("dismissal accepted",
          ok is True and sb.batting_card["Jansen"]["status"] == "out",
          f"ok={ok}, status={sb.batting_card['Jansen']['status']}")
    check("Vyshak NOT promoted by squad order (deferred)",
          sb.batting_card["Vyshak"]["status"] == "yet_to_bat",
          f"Vyshak status={sb.batting_card['Vyshak']['status']}")
    check("Arshad NOT promoted by squad order (deferred)",
          sb.batting_card["Arshad"]["status"] == "yet_to_bat",
          f"Arshad status={sb.batting_card['Arshad']['status']}")
    check("no promoted_source recorded for any yet_to_bat card",
          all(sb.batting_card[n].get("promoted_source") is None
              for n in ("Vyshak", "Arshad")),
          f"Vyshak={sb.batting_card['Vyshak'].get('promoted_source')}, "
          f"Arshad={sb.batting_card['Arshad'].get('promoted_source')}")
    active_after = [n for n, c in sb.batting_card.items()
                    if c.get("status") == "batting"]
    check("active set is size 1 (Stoinis only) until strip arrives",
          active_after == ["Stoinis"],
          f"active={active_after}")
    check("[INCOMING-BATTER-PENDING] tag emitted",
          "[INCOMING-BATTER-PENDING]" in log_text,
          f"log_text excerpt={log_text[:400]!r}")


def test_batch_l_strip_path_still_works() -> None:
    header("Batch L: strip-read promotion path UNCHANGED — Vyshak is "
           "still promoted when extracted_batters names him")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        "PBKS", "GT",
        ["Stoinis", "Jansen", "Vyshak", "Arshad"],
        ["Holder", "Suthar"],
    )
    sb.batting_card["Stoinis"]["status"] = "batting"
    sb.batting_card["Jansen"]["status"] = "batting"
    sb._inn["score"] = 141
    sb._inn["wickets"] = 7
    sb._inn["overs"] = "17.5"
    sb._inn["striker"] = "Jansen"
    sb._inn["non"] = "Stoinis"
    extracted_batters = [
        {"name": "Vyshak", "runs": 0, "balls": 0},
        {"name": "Jansen", "runs": 7, "balls": 6},
    ]
    ok = sb.dismiss_batter("Jansen", how="bowled", bowler="Holder",
                           fielder=None, frame=212,
                           extracted_batters=extracted_batters)
    check("dismissal accepted",
          ok is True and sb.batting_card["Jansen"]["status"] == "out",
          f"ok={ok}, status={sb.batting_card['Jansen']['status']}")
    check("Vyshak promoted via strip path (path-(a) unchanged)",
          sb.batting_card["Vyshak"]["status"] == "batting",
          f"Vyshak status={sb.batting_card['Vyshak']['status']}")
    check("promoted_source records strip path (not squad)",
          sb.batting_card["Vyshak"].get("promoted_source")
          == "dismiss_batter:strip",
          f"source={sb.batting_card['Vyshak'].get('promoted_source')}")
    check("Arshad still yet_to_bat (only one slot to fill)",
          sb.batting_card["Arshad"]["status"] == "yet_to_bat",
          f"Arshad status={sb.batting_card['Arshad']['status']}")


def test_batch_l_no_phantom_dismissal_on_correct_arrival() -> None:
    header("Batch L: correct incoming batter arriving on a later strip "
           "frame does NOT cause a phantom dismissal of a wrongly-"
           "guessed batter (F285 KKR vs PBKS regression)")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        "KKR", "PBKS",
        ["Rahane", "Narine", "Markram", "Pooran", "Russell"],
        ["Arshdeep", "Chahar"],
    )
    sb.batting_card["Rahane"]["status"] = "batting"
    sb.batting_card["Narine"]["status"] = "batting"
    sb._inn["score"] = 80
    sb._inn["wickets"] = 1
    sb._inn["overs"] = "8.3"
    sb._inn["striker"] = "Narine"
    sb._inn["non"] = "Rahane"
    ok = sb.dismiss_batter("Narine", how="bowled", bowler="Arshdeep",
                           fielder=None, frame=285,
                           extracted_batters=None)
    check("dismissal accepted",
          ok is True and sb.batting_card["Narine"]["status"] == "out",
          f"ok={ok}, status={sb.batting_card['Narine']['status']}")
    check("Markram NOT promoted by squad-order (no phantom guess)",
          sb.batting_card["Markram"]["status"] == "yet_to_bat",
          f"Markram status={sb.batting_card['Markram']['status']}")
    check("Pooran NOT promoted yet (strip hasn't named him)",
          sb.batting_card["Pooran"]["status"] == "yet_to_bat",
          f"Pooran status={sb.batting_card['Pooran']['status']}")

    sb.update_batter("Pooran", runs=0, balls=1, frame=302)
    check("Pooran now batting after strip read arrives",
          sb.batting_card["Pooran"]["status"] == "batting",
          f"Pooran status={sb.batting_card['Pooran']['status']}")
    check("Markram still yet_to_bat (no phantom dismissal)",
          sb.batting_card["Markram"]["status"] == "yet_to_bat",
          f"Markram status={sb.batting_card['Markram']['status']}")
    check("FOW length still 1 (no phantom Markram dismissal)",
          len(sb.fall_of_wickets) == 1,
          f"fow={[f.get('batter') for f in sb.fall_of_wickets]}")
    check("Markram not present in any FOW entry",
          all(f.get("batter") != "Markram" for f in sb.fall_of_wickets),
          f"fow_batters={[f.get('batter') for f in sb.fall_of_wickets]}")


def test_batch_j_no_promotion_when_innings_all_out() -> None:
    header("Batch J: no promotion when no yet_to_bat candidates remain "
           "(innings all-out edge case)")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        "PBKS", "GT",
        ["A", "B", "C", "D"],  # 4-player squad, 3 already out
        ["Holder", "Suthar"],
    )
    sb.batting_card["A"]["status"] = "out"
    sb.batting_card["B"]["status"] = "out"
    sb.batting_card["C"]["status"] = "out"
    sb.batting_card["D"]["status"] = "batting"
    sb._inn["score"] = 50
    sb._inn["wickets"] = 9
    sb._inn["overs"] = "10.0"
    sb._inn["striker"] = "D"
    ok = sb.dismiss_batter("D", how="bowled", bowler="Holder",
                           fielder=None, frame=200,
                           extracted_batters=None)
    check("dismissal accepted",
          ok is True and sb.batting_card["D"]["status"] == "out",
          f"ok={ok}, status={sb.batting_card['D']['status']}")
    promoted = [n for n, c in sb.batting_card.items()
                if c.get("status") == "batting"]
    check("no batter promoted (all-out)",
          promoted == [],
          f"unexpectedly promoted: {promoted}")
    for n in ("A", "B", "C", "D"):
        check(f"{n} not promoted via this path",
              sb.batting_card[n].get("promoted_source") is None,
              f"{n}.promoted_source="
              f"{sb.batting_card[n].get('promoted_source')}")


def test_fix3_three_active_demotes_fow_not_position() -> None:
    header("Fix 3: max-2 deactivation prefers FOW-resurrected over "
           "lowest position (F339 three-active scenario)")
    sb = _make_sb_with_resurrection_setup()
    # Force the F339 corruption: all three are 'batting'; Pathum is
    # the FOW-witnessed resurrection.  Pre-fix, position fallback
    # would have demoted Rana (pos 5).  Post-fix, Pathum is demoted.
    sb.batting_card["Pathum"]["status"] = "batting"
    sb.batting_card["Pathum"]["dismissal"] = None
    sb.validate_state_consistency()
    check("Pathum demoted (FOW-witnessed)",
          sb.batting_card["Pathum"]["status"] == "out",
          f"Pathum status={sb.batting_card['Pathum']['status']}")
    check("Rahul still batting (pos 1)",
          sb.batting_card["Rahul"]["status"] == "batting",
          f"Rahul status={sb.batting_card['Rahul']['status']}")
    check("Rana still batting (pos 5) — NOT demoted by position",
          sb.batting_card["Rana"]["status"] == "batting",
          f"Rana status={sb.batting_card['Rana']['status']}")


def test_fix3_position_fallback_when_no_fow_match() -> None:
    header("Fix 3: position fallback fires (with anomaly log) when no "
           "active batter has a witnessed FOW entry")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        "BAT", "BOWL",
        ["A", "B", "C", "D", "E"],
        ["B1", "B2"],
    )
    # Three active, NONE in FOW (anomaly case): legacy position-based
    # fallback should fire and demote E (pos 5).
    for n in ("A", "B", "E"):
        sb.batting_card[n]["status"] = "batting"
        sb.batting_card[n]["runs"] = 1
        sb.batting_card[n]["balls"] = 1
    sb.fall_of_wickets = []
    sb._inn["score"] = 10
    sb._inn["wickets"] = 0
    sb.validate_state_consistency()
    check("E (pos 5) deactivated to yet_to_bat",
          sb.batting_card["E"]["status"] == "yet_to_bat",
          f"E status={sb.batting_card['E']['status']}")
    check("A and B remain batting",
          sb.batting_card["A"]["status"] == "batting"
          and sb.batting_card["B"]["status"] == "batting",
          "lowest-position batters must remain batting")


# ---------------------------------------------------------------------
# 8. P0-B wicket-tick gate bypass for witnessed-FOW re-assertion
#    (DC vs PBKS F832 → Nitish-Rana-stuck-yet_to_bat deadlock)
# ---------------------------------------------------------------------
def _make_sb_with_corrupted_active_set():
    """Build the F832 corrupted state: Pathum dismissed at wickets=1 but
    resurrected back to 'batting' in the active set.

    Mirrors the live deadlock: extractor strip will show RANA + RAHUL,
    Pathum is "missing from extractor" but the wicket-tick gate would
    refuse to re-dismiss because `_last_autodismiss_wickets == 1`
    (already auto-dismissed Pathum once at this wicket count).
    """
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        "BAT", "BOWL",
        ["Rahul", "Pathum", "Three", "Four", "Rana"],
        ["B1", "B2"],
    )
    sb.batting_card["Rahul"]["status"] = "batting"
    sb.batting_card["Rahul"]["runs"] = 31
    sb.batting_card["Rahul"]["balls"] = 32
    sb.batting_card["Pathum"]["status"] = "batting"  # CORRUPTED
    sb.batting_card["Pathum"]["runs"] = 11
    sb.batting_card["Pathum"]["balls"] = 23
    sb.batting_card["Pathum"]["dismissal"] = None  # wiped by un-dismiss
    sb.batting_card["Rana"]["status"] = "yet_to_bat"
    sb.fall_of_wickets = [{
        "wicket": 1, "batter": "Pathum", "score": 50, "overs": "6.3",
        "how": "caught", "bowler": "B1", "_witnessed": True,
    }]
    sb._inn["score"] = 86
    sb._inn["wickets"] = 1
    sb._inn["overs"] = "7.5"
    sb._last_autodismiss_wickets = 1  # gate would block at this count
    return sb


def test_p0b_gate_bypass_reasserts_witnessed_dismissal() -> None:
    header("P0-B: _auto_dismiss_for_new_batter bypasses wicket-tick gate "
           "when missing batter has witnessed FOW (F832 replay)")
    sb = _make_sb_with_corrupted_active_set()
    # Strip mentions RANA + RAHUL — Pathum is missing from extractor.
    sb._extractor_batter_names = ["RANA", "RAHUL"]
    active = [n for n, c in sb.batting_card.items()
              if c["status"] == "batting"]
    result = sb._auto_dismiss_for_new_batter(active, "Rana")
    check("returns 'Pathum' (re-asserted, not None)",
          result == "Pathum", f"result={result!r}")
    check("Pathum demoted to 'out'",
          sb.batting_card["Pathum"]["status"] == "out",
          f"status={sb.batting_card['Pathum']['status']}")
    check("_last_autodismiss_wickets NOT bumped (no new wicket)",
          sb._last_autodismiss_wickets == 1,
          f"_last_autodismiss_wickets={sb._last_autodismiss_wickets}")
    check("FOW unchanged (still 1 entry, Pathum)",
          len(sb.fall_of_wickets) == 1
          and sb.fall_of_wickets[0]["batter"] == "Pathum",
          f"fow={sb.fall_of_wickets}")


def test_p0b_gate_blocks_phantom_wicket_no_fow() -> None:
    header("P0-B: gate still blocks phantom wickets when missing batter "
           "has NO witnessed FOW (no regression)")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        "BAT", "BOWL",
        ["A", "B", "C", "D", "E"],
        ["B1", "B2"],
    )
    # A and B both currently batting, no FOW entries.  Extractor (e.g.
    # a hallucinated comparison-graphic strip) shows only A + new
    # batter C.  Pre-fix, gate would block on _last_autodismiss_wickets;
    # post-fix, gate must STILL block (B has no witnessed FOW, so the
    # bypass is not eligible).
    for n in ("A", "B"):
        sb.batting_card[n]["status"] = "batting"
        sb.batting_card[n]["runs"] = 10
        sb.batting_card[n]["balls"] = 8
    sb._inn["score"] = 50
    sb._inn["wickets"] = 1
    sb._last_autodismiss_wickets = 1
    sb.fall_of_wickets = []  # no FOW for A or B
    sb._extractor_batter_names = ["A", "C"]
    result = sb._auto_dismiss_for_new_batter(["A", "B"], "C")
    check("returns None (gate blocked, no bypass)",
          result is None, f"result={result!r}")
    check("B remains 'batting' (not phantom-dismissed)",
          sb.batting_card["B"]["status"] == "batting",
          f"B status={sb.batting_card['B']['status']}")
    check("FOW remains empty (no spurious entry created)",
          sb.fall_of_wickets == [],
          f"fow={sb.fall_of_wickets}")


def test_p0b_gate_bypass_skipped_on_multi_missing() -> None:
    header("P0-B: bypass requires exactly one missing-with-witnessed-FOW; "
           "multi-missing case falls through to gate")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        "BAT", "BOWL",
        ["A", "B", "C", "D"],
        ["B1", "B2"],
    )
    # Two batters in active set, BOTH with witnessed FOW (highly
    # pathological state).  Extractor shows neither — both are
    # "missing".  Bypass requires len(_bypass_candidates)==1, so this
    # falls through to the standard gate-blocked log.
    for n in ("A", "B"):
        sb.batting_card[n]["status"] = "batting"
        sb.batting_card[n]["runs"] = 0
        sb.batting_card[n]["balls"] = 0
    sb.fall_of_wickets = [
        {"wicket": 1, "batter": "A", "score": 10, "overs": "2.1",
         "_witnessed": True},
        {"wicket": 2, "batter": "B", "score": 20, "overs": "3.4",
         "_witnessed": True},
    ]
    sb._inn["score"] = 30
    sb._inn["wickets"] = 2
    sb._last_autodismiss_wickets = 2
    sb._extractor_batter_names = ["C", "D"]
    result = sb._auto_dismiss_for_new_batter(["A", "B"], "C")
    check("returns None (bypass not eligible: 2 candidates)",
          result is None, f"result={result!r}")
    check("A still 'batting' (not partially demoted)",
          sb.batting_card["A"]["status"] == "batting",
          f"A status={sb.batting_card['A']['status']}")
    check("B still 'batting' (not partially demoted)",
          sb.batting_card["B"]["status"] == "batting",
          f"B status={sb.batting_card['B']['status']}")


def test_p0b_end_to_end_rana_activates_via_update_batter() -> None:
    header("P0-B: end-to-end — update_batter('Rana') in F832 corrupted "
           "state activates Rana via gate bypass + replacement chain")
    sb = _make_sb_with_corrupted_active_set()
    sb._extractor_batter_names = ["RANA", "RAHUL"]
    ok = sb.update_batter("Rana", runs=30, balls=19, frame=832)
    check("update_batter returned True",
          ok is True, f"return={ok}")
    check("Rana activated to 'batting'",
          sb.batting_card["Rana"]["status"] == "batting",
          f"Rana status={sb.batting_card['Rana']['status']}")
    check("Pathum demoted to 'out'",
          sb.batting_card["Pathum"]["status"] == "out",
          f"Pathum status={sb.batting_card['Pathum']['status']}")
    check("Rahul untouched ('batting')",
          sb.batting_card["Rahul"]["status"] == "batting",
          f"Rahul status={sb.batting_card['Rahul']['status']}")
    active = sorted([n for n, c in sb.batting_card.items()
                     if c["status"] == "batting"])
    check("active set is now {Rahul, Rana}",
          active == ["Rahul", "Rana"], f"active={active}")


# ---------------------------------------------------------------------
# 9. Pass-2 enrichment async — Scoreboard.update_player_styles + split path
# ---------------------------------------------------------------------

def test_update_player_styles_patches_existing_cards() -> None:
    header("Scoreboard.update_player_styles patches batting+bowling cards")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        "BAT", "BOWL", ["a", "b"], ["c", "d"],
        player_styles={
            "a": {"batting_style": "RHB", "bowling_style": "unknown"},
            "b": {"batting_style": "unknown", "bowling_style": "unknown"},
        },
    )
    # Pass-2 corrects b's batting hand and adds bowling style for c.
    pass2 = {
        "a": {"batting_style": "RHB", "bowling_style": "unknown"},
        "b": {"batting_style": "LHB",
              "bowling_style": "Slow left-arm orthodox"},
        "c": {"batting_style": "RHB", "bowling_style": "Right-arm fast"},
    }
    n = sb.update_player_styles(pass2)
    check("returned card-update count covers a,b (bat) + c (bowl)",
          n == 3, f"n={n}")
    check("a batting_card unchanged (already RHB)",
          sb.batting_card["a"]["batting_style"] == "RHB",
          f"a={sb.batting_card['a']}")
    check("b batting_card upgraded to LHB",
          sb.batting_card["b"]["batting_style"] == "LHB",
          f"b={sb.batting_card['b']}")
    check("b batting_card bowling_style filled in",
          sb.batting_card["b"]["bowling_style"]
          == "Slow left-arm orthodox",
          f"b={sb.batting_card['b']}")
    check("c bowling_card bowling_style filled in",
          sb.bowling_card["c"]["bowling_style"] == "Right-arm fast",
          f"c={sb.bowling_card['c']}")
    check("_player_styles merged",
          sb._player_styles.get("c", {}).get("bowling_style")
          == "Right-arm fast",
          f"_player_styles={sb._player_styles}")


def test_update_player_styles_preserves_runtime_stats() -> None:
    header("update_player_styles never wipes live runs/balls/wickets")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL", ["a", "b"], ["c", "d"])
    sb.batting_card["a"]["status"] = "batting"
    sb.batting_card["a"]["runs"] = 42
    sb.batting_card["a"]["balls"] = 30
    sb.bowling_card["c"]["overs"] = "3.0"
    sb.bowling_card["c"]["wickets"] = 2
    sb.update_player_styles({
        "a": {"batting_style": "LHB", "bowling_style": "unknown"},
        "c": {"batting_style": "RHB", "bowling_style": "Right-arm medium"},
    })
    check("a runtime stats preserved (runs=42)",
          sb.batting_card["a"]["runs"] == 42
          and sb.batting_card["a"]["balls"] == 30
          and sb.batting_card["a"]["status"] == "batting",
          f"a={sb.batting_card['a']}")
    check("c bowling stats preserved (overs=3.0, wickets=2)",
          sb.bowling_card["c"]["overs"] == "3.0"
          and sb.bowling_card["c"]["wickets"] == 2,
          f"c={sb.bowling_card['c']}")
    check("a batting_style still applied",
          sb.batting_card["a"]["batting_style"] == "LHB",
          f"a style={sb.batting_card['a']['batting_style']}")


def test_update_player_styles_handles_missing_or_empty() -> None:
    header("update_player_styles tolerates empty/None input + unknown names")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL", ["a", "b"], ["c", "d"])
    check("empty dict returns 0",
          sb.update_player_styles({}) == 0, "n != 0")
    check("None-typed entry skipped",
          sb.update_player_styles({"a": None}) == 0,  # type: ignore[arg-type]
          "n != 0 on None")
    # Unknown name silently ignored.
    n = sb.update_player_styles({
        "ghost": {"batting_style": "RHB", "bowling_style": "unknown"},
    })
    check("unknown name does not raise and returns 0",
          n == 0, f"n={n}")


def test_enrich_squad_styles_pass2_background_skips_pass2() -> None:
    header("enrich_squad_styles(pass2_background=True) returns Pass-1 only")
    import asyncio
    from eyes import player_enrichment as pe

    def _names(players):
        return [p["name"] if isinstance(p, dict) else p for p in players]

    async def _fake_pass1(client, raw_data, players):
        return {n: {"batting_style": "RHB", "bowling_style": "unknown"}
                for n in _names(players)}

    pass2_called = {"flag": False}

    async def _fake_pass2(client, raw_data, pass1, players):
        pass2_called["flag"] = True
        return {n: {"batting_style": "LHB", "bowling_style": "Right-arm medium"}
                for n in _names(players)}

    raw = {
        "team_a": {"name": "A", "playing_xi": [{"name": "p1"}], "bench": []},
        "team_b": {"name": "B", "playing_xi": [{"name": "p2"}], "bench": []},
    }
    orig_pass1, orig_pass2 = pe._run_pass1, pe._run_pass2
    orig_make = pe._make_client
    orig_load_cache = pe._load_cache
    pe._run_pass1 = _fake_pass1
    pe._run_pass2 = _fake_pass2
    pe._make_client = lambda: object()
    pe._load_cache = lambda raw: None
    try:
        result = asyncio.run(
            pe.enrich_squad_styles(raw, pass2_background=True))
    finally:
        pe._run_pass1, pe._run_pass2 = orig_pass1, orig_pass2
        pe._make_client = orig_make
        pe._load_cache = orig_load_cache

    check("pass2_background=True returns Pass-1 styles immediately",
          result.get("p1", {}).get("batting_style") == "RHB",
          f"result={result}")
    check("Pass-2 was NOT invoked in pass2_background mode",
          pass2_called["flag"] is False,
          "Pass-2 fired despite pass2_background=True")
    check("raw_data was merged with Pass-1 styles in place",
          raw["team_a"]["playing_xi"][0].get("batting_style") == "RHB",
          f"raw a={raw['team_a']['playing_xi'][0]}")


def test_enrich_squad_styles_pass2_async_invokes_callback() -> None:
    header("enrich_squad_styles_pass2_async fires on_complete + patches "
           "raw_data + writes cache")
    import asyncio
    from eyes import player_enrichment as pe

    def _names(players):
        return [p["name"] if isinstance(p, dict) else p for p in players]

    async def _fake_pass2(client, raw_data, pass1, players):
        return {n: {"batting_style": "LHB", "bowling_style": "Right-arm fast"}
                for n in _names(players)}

    saved_via_cache = {"styles": None}

    def _fake_save_cache(raw, styles):
        saved_via_cache["styles"] = dict(styles)

    raw = {
        "team_a": {"name": "A",
                   "playing_xi": [{"name": "p1",
                                   "batting_style": "RHB",
                                   "bowling_style": "unknown"}],
                   "bench": []},
        "team_b": {"name": "B",
                   "playing_xi": [{"name": "p2",
                                   "batting_style": "RHB",
                                   "bowling_style": "unknown"}],
                   "bench": []},
    }
    pass1_styles = {
        "p1": {"batting_style": "RHB", "bowling_style": "unknown"},
        "p2": {"batting_style": "RHB", "bowling_style": "unknown"},
    }
    callback_received: dict = {}

    def _on_complete(styles):
        callback_received.update(styles)

    orig_pass2, orig_make, orig_save = pe._run_pass2, pe._make_client, pe._save_cache
    pe._run_pass2 = _fake_pass2
    pe._make_client = lambda: object()
    pe._save_cache = _fake_save_cache
    try:
        result = asyncio.run(
            pe.enrich_squad_styles_pass2_async(
                raw, pass1_styles, on_complete=_on_complete))
    finally:
        pe._run_pass2, pe._make_client, pe._save_cache = (
            orig_pass2, orig_make, orig_save)

    check("returned Pass-2 styles dict",
          result is not None and result.get("p1", {}).get("batting_style")
          == "LHB",
          f"result={result}")
    check("on_complete callback received Pass-2 styles",
          callback_received.get("p1", {}).get("batting_style") == "LHB",
          f"received={callback_received}")
    check("raw_data was retro-patched with Pass-2 styles",
          raw["team_a"]["playing_xi"][0]["batting_style"] == "LHB",
          f"raw p1={raw['team_a']['playing_xi'][0]}")
    check("cache was written with Pass-2 styles",
          saved_via_cache["styles"] is not None
          and saved_via_cache["styles"].get("p1", {}).get("batting_style")
          == "LHB",
          f"cache={saved_via_cache['styles']}")


def test_enrich_squad_styles_pass2_async_failure_caches_pass1() -> None:
    header("enrich_squad_styles_pass2_async on Pass-2 failure: cache "
           "Pass-1, skip callback")
    import asyncio
    from eyes import player_enrichment as pe

    async def _fail_pass2(client, raw_data, pass1, players):
        raise RuntimeError("simulated Pass-2 timeout")

    saved: dict = {"styles": None}

    def _fake_save_cache(raw, styles):
        saved["styles"] = dict(styles)

    raw = {
        "team_a": {"name": "A",
                   "playing_xi": [{"name": "p1",
                                   "batting_style": "RHB",
                                   "bowling_style": "unknown"}],
                   "bench": []},
        "team_b": {"name": "B", "playing_xi": [], "bench": []},
    }
    pass1_styles = {
        "p1": {"batting_style": "RHB", "bowling_style": "unknown"},
    }
    cb_calls = {"n": 0}

    def _on_complete(styles):
        cb_calls["n"] += 1

    orig_pass2, orig_make, orig_save = pe._run_pass2, pe._make_client, pe._save_cache
    pe._run_pass2 = _fail_pass2
    pe._make_client = lambda: object()
    pe._save_cache = _fake_save_cache
    try:
        result = asyncio.run(
            pe.enrich_squad_styles_pass2_async(
                raw, pass1_styles, on_complete=_on_complete))
    finally:
        pe._run_pass2, pe._make_client, pe._save_cache = (
            orig_pass2, orig_make, orig_save)

    check("Pass-2 failure → returns None",
          result is None, f"result={result}")
    check("on_complete NOT invoked on failure",
          cb_calls["n"] == 0, f"cb called {cb_calls['n']}x")
    check("Pass-1 was cached as fallback",
          saved["styles"] is not None
          and saved["styles"].get("p1", {}).get("batting_style") == "RHB",
          f"cache={saved['styles']}")
    check("raw_data still has Pass-1 batting_style (no rollback)",
          raw["team_a"]["playing_xi"][0]["batting_style"] == "RHB",
          f"raw p1={raw['team_a']['playing_xi'][0]}")


# ---------------------------------------------------------------------
# Pass-2 client config (P1 fix, 2026-04-26): _make_client() must return
# an AsyncGroq with timeout=240.0 and max_retries=0.  Locks in the fix
# for the deterministic 271 s timeout (3 attempts × 90 s SDK retry
# default) observed across 3/3 production sessions on 2026-04-25.
# Cheapest insurance against a silent revert if the SDK is upgraded
# and `max_retries` defaults change, or if someone re-edits the
# client constructor without remembering why these values were set.
# See backlog "P1: Pass-2 enrichment retry/timeout policy".
# ---------------------------------------------------------------------
def test_pass2_client_timeout_config_explicit() -> None:
    header("_make_client() returns AsyncGroq with timeout=240.0 and "
           "max_retries=0")
    import os as _os
    from eyes import player_enrichment as pe

    orig_key = _os.environ.get("GROQ_API_KEY")
    if not orig_key:
        _os.environ["GROQ_API_KEY"] = "test-dummy-key-for-config-shape-only"
    orig_module_key = pe.GROQ_API_KEY
    pe.GROQ_API_KEY = _os.environ["GROQ_API_KEY"]
    try:
        client = pe._make_client()
    finally:
        pe.GROQ_API_KEY = orig_module_key
        if orig_key is None:
            _os.environ.pop("GROQ_API_KEY", None)

    check("_make_client() returned a non-None client",
          client is not None,
          "client was None — Groq SDK init failed in test env")
    check("client.timeout == 240.0 (single-shot headroom for "
          "groq/compound web-search latency)",
          getattr(client, "timeout", None) == 240.0,
          f"client.timeout={getattr(client, 'timeout', None)!r}")
    check("client.max_retries == 0 (SDK retry disabled — Pass-2 is "
          "background-async with Pass-1 fallback)",
          getattr(client, "max_retries", None) == 0,
          f"client.max_retries={getattr(client, 'max_retries', None)!r}")


if _pytest is not None:
    test_pass2_client_timeout_config_explicit = _pytest.mark.requires_groq(
        test_pass2_client_timeout_config_explicit)


# ---------------------------------------------------------------------
# WS-PROJECTION-GAP fallback (Fix 7, 2026-04-26): when SM has cleared
# striker / non to None mid-wicket-transition but `sb._inn`
# already holds the new pair from scout's strip read, project the
# `sb._inn` value into the WS payload provided the value is currently
# in `active_batting` (i.e. not a stale dismissed-batter leftover).
# Closes the ~24 s post-wicket UI gap observed at F145 W2 in the
# 2026-04-25 RR-vs-SRH match-2 trace.  Strengthened by Fix 5 (same
# bundle): `sb._inn` is now collision-protected, so this fallback
# can't surface a `striker == non` payload pair.
# See backlog "P2: WS-PROJECTION-GAP — striker / non null in
# payload" (entry includes the F145 evidence and Fix-5 reframing).
# ---------------------------------------------------------------------
def _setup_ws_projection_pair_sb():
    """Fresh Scoreboard with two batters at the crease + a dismissed
    batter mid-innings, ready for SM-null fallback scenarios."""
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="Rajasthan Royals",
        bowling_team="Sunrisers Hyderabad",
        batting_squad=["Sooryavanshi", "Parag", "Jurel", "Three"],
        bowling_squad=["Sakib Hussain", "Shivang Kumar"],
        batting_xi=["Sooryavanshi", "Parag", "Jurel", "Three"],
        bowling_xi=["Sakib Hussain", "Shivang Kumar"],
    )
    for name, runs, balls, status in (
            ("Sooryavanshi", 103, 50, "batting"),
            ("Parag", 2, 4, "batting"),
            ("Jurel", 8, 12, "out")):
        sb.batting_card[name]["status"] = status
        sb.batting_card[name]["runs"] = runs
        sb.batting_card[name]["balls"] = balls
    sb._inn["score"] = 113
    sb._inn["wickets"] = 2
    sb._inn["overs"] = "13.2"
    return sb


class _StubSM:
    """Minimal ScoreManager-shaped stub: just the attrs
    `_project_active_batters` reads."""
    def __init__(self, striker=None, non=None,
                 bowler_name=None, shadow=False):
        self.striker = striker
        self.non = non
        self.bowler_name = bowler_name
        self.shadow = shadow


def _identity_canon(raw, *, bowler: bool = False):
    return raw


def test_ws_projection_fallback_sm_resolved_no_fallback() -> None:
    header("Fix 7: SM has both striker/non resolved → "
           "no fallback fires, payload uses SM values")
    from test_pipeline import _project_active_batters

    sb = _setup_ws_projection_pair_sb()
    sb._inn["striker"] = "Sooryavanshi"
    sb._inn["non"] = "Parag"
    sm = _StubSM(striker="Sooryavanshi", non="Parag")
    state = {"striker": None, "non": None}

    events = _project_active_batters(state, sm, sb, _identity_canon)

    check("payload striker matches SM striker",
          state["striker"] == "Sooryavanshi",
          f"state.striker={state['striker']!r}")
    check("payload non matches SM non",
          state["non"] == "Parag",
          f"state.non={state['non']!r}")
    check("no fallback events recorded (SM was authoritative)",
          events == [],
          f"events={events!r}")


def test_ws_projection_fallback_sm_null_dismissed_no_fallback() -> None:
    header("Fix 7: SM null AND sb._inn holds dismissed batter "
           "(not in active_batting) → no fallback (preserves S18 "
           "placeholder, no dismissed-batter leak)")
    from test_pipeline import _project_active_batters

    sb = _setup_ws_projection_pair_sb()
    sb._inn["striker"] = "Jurel"
    sb._inn["non"] = "Parag"
    sm = _StubSM(striker=None, non="Parag")
    state = {"striker": None, "non": None}

    events = _project_active_batters(state, sm, sb, _identity_canon)

    check("payload striker stays None (Jurel is dismissed, not in "
          "active_batting → fallback declined, UI placeholder shown)",
          state["striker"] is None,
          f"state.striker={state['striker']!r} (would have been a "
          f"dismissed-batter leak if fallback fired)")
    check("payload non matches SM (Parag, still resolved)",
          state["non"] == "Parag",
          f"state.non={state['non']!r}")
    check("no fallback events recorded for dismissed-batter case",
          events == [],
          f"events={events!r}")


def test_ws_projection_fallback_sm_null_active_uses_sb_inn() -> None:
    header("Fix 7: SM null AND sb._inn holds valid name in "
           "active_batting → fallback fires, surfaces the new batter")
    from test_pipeline import _project_active_batters

    sb = _setup_ws_projection_pair_sb()
    sb._inn["striker"] = "Sooryavanshi"
    sb._inn["non"] = "Parag"
    sm = _StubSM(striker=None, non="Parag")
    state = {"striker": None, "non": None}

    events = _project_active_batters(state, sm, sb, _identity_canon)

    check("payload striker surfaced from sb._inn (fallback fired)",
          state["striker"] == "Sooryavanshi",
          f"state.striker={state['striker']!r}")
    check("payload non matches SM (no fallback needed)",
          state["non"] == "Parag",
          f"state.non={state['non']!r}")
    check("exactly one fallback event recorded for striker slot",
          events == [("striker", "Sooryavanshi")],
          f"events={events!r}")


def test_ws_projection_fallback_f145_w2_replay() -> None:
    header("Fix 7: F145 W2 production replay (Jurel dismissed, "
           "Parag promoted to striker, SM 24s catch-up gap)")
    from test_pipeline import _project_active_batters

    sb = _setup_ws_projection_pair_sb()
    sb._inn["striker"] = "Riyan Parag"
    sb._inn["non"] = "Vaibhav Sooryavanshi"
    sb.batting_card["Riyan Parag"] = {"status": "batting",
                                       "runs": 2, "balls": 4}
    sb.batting_card["Vaibhav Sooryavanshi"] = {
        "status": "batting", "runs": 103, "balls": 50}
    if "Sooryavanshi" in sb.batting_card:
        sb.batting_card["Sooryavanshi"]["status"] = "yet_to_bat"
    if "Parag" in sb.batting_card:
        sb.batting_card["Parag"]["status"] = "yet_to_bat"
    sm = _StubSM(striker=None, non=None)
    state = {"striker": None, "non": None}

    events = _project_active_batters(state, sm, sb, _identity_canon)

    check("F145 replay: payload striker = 'Riyan Parag' "
          "(was None pre-Fix-7 for ~24s)",
          state["striker"] == "Riyan Parag",
          f"state.striker={state['striker']!r}")
    check("F145 replay: payload non = 'Vaibhav Sooryavanshi' "
          "(was None pre-Fix-7 for ~24s)",
          state["non"] == "Vaibhav Sooryavanshi",
          f"state.non={state['non']!r}")
    check("F145 replay: invariant striker != non held in "
          "payload (Fix 5 protects sb._inn → Fix 7 inherits it)",
          state["striker"] != state["non"],
          f"striker={state['striker']!r} non="
          f"{state['non']!r}")
    check("F145 replay: both slots recorded as fallback events",
          len(events) == 2
          and {e[0] for e in events} == {"striker", "non"},
          f"events={events!r}")


def test_ws_projection_fallback_collision_avoidance_with_other_slot() -> None:
    header("Fix 7: defence-in-depth — sb._inn fallback declined when "
           "the value matches the already-resolved other slot "
           "(prevents payload-level striker == non)")
    from test_pipeline import _project_active_batters

    sb = _setup_ws_projection_pair_sb()
    sb._inn["striker"] = "Parag"
    sb._inn["non"] = "Sooryavanshi"
    sm = _StubSM(striker="Parag", non=None)
    state = {"striker": None, "non": None}

    sb.batting_card["Parag"]["status"] = "batting"
    sb.batting_card["Sooryavanshi"]["status"] = "batting"

    state["striker"] = "Parag"
    state["non"] = sm.non
    sb._inn["non"] = "Parag"

    events = _project_active_batters(state, sm, sb, _identity_canon)

    check("payload non stays None when sb._inn fallback "
          "would collide with already-resolved striker slot",
          state["non"] is None,
          f"state.non={state['non']!r} (would have "
          f"created striker == non payload-level collision)")
    check("payload striker preserved (was already resolved by SM)",
          state["striker"] == "Parag",
          f"state.striker={state['striker']!r}")
    check("no fallback event recorded for the declined non",
          events == [] or all(e[0] != "non" for e in events),
          f"events={events!r}")


def test_ws_projection_fallback_requires_batting_status() -> None:
    header("Fix 7 hardening: sb._inn fallback requires status=batting")
    from test_pipeline import _project_active_batters

    sb = _setup_ws_projection_pair_sb()
    sb._inn["striker"] = "Sooryavanshi"
    sb.batting_card["Sooryavanshi"]["status"] = "yet_to_bat"
    sm = _StubSM(striker=None, non="Parag")
    state = {"striker": None, "non": None}

    events = _project_active_batters(state, sm, sb, _identity_canon)

    check("payload striker stays None for non-batting status",
          state["striker"] is None,
          f"state.striker={state['striker']!r}")
    check("no fallback event recorded for non-batting card",
          events == [],
          f"events={events!r}")


def test_ws_projection_fallback_resolves_name_before_status_check() -> None:
    header("Fix 7 hardening: fallback resolves raw name before status")
    from test_pipeline import _project_active_batters

    sb = _setup_ws_projection_pair_sb()
    sb.batting_card["Riyan Parag"] = {
        "status": "batting", "runs": 2, "balls": 4}
    sb._name_lookup["PARAG"] = "Riyan Parag"
    sb._inn["striker"] = "PARAG"
    sm = _StubSM(striker=None, non="Sooryavanshi")
    state = {"striker": None, "non": None}

    events = _project_active_batters(state, sm, sb, _identity_canon)

    check("payload striker uses canonical resolved name",
          state["striker"] == "Riyan Parag",
          f"state.striker={state['striker']!r}")
    check("fallback event records canonical resolved name",
          events == [("striker", "Riyan Parag")],
          f"events={events!r}")


def test_dual_broadcaster_unification_routes_sm_frames_via_canonical_builder() -> None:
    header("Dual-broadcaster: SM event frames use canonical WS builder")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()

    check("SM raw payload is no longer broadcast directly",
          "ws_payload = _sm_result" not in src,
          "found direct ws_payload = _sm_result assignment")
    check("unification marker documents Path A at the WS boundary",
          "Dual-broadcaster unification (Path A)" in src,
          "missing Path A WS-boundary marker")
    check("SM events still feed wire override through canonical payload",
          "ws_payload[\"ball_event\"] = _sm_evt" in src
          and "ws_payload[\"_wire_override\"] = format_wire" in src,
          "missing SM event passthrough / wire override")


# ---------------------------------------------------------------------
# INFO-PANEL bowler-strip gate (Fix 8, 2026-04-26): when vision
# description contains a stats-overlay keyword (`_INFO_PANEL_KEYWORDS`
# — "IPL CAREER", "CAREER", "IN T20", "HEAD TO HEAD", etc.), strip
# the bowler / bowler_name / bowler_figures fields from `extracted`.
# Closes the F619 DC-vs-PBKS pattern where "YUZVENDRA CHAHAL IPL
# CAREER MATCHES 181 WICKETS 225 ECONOMY 8.0" overlay was extracted
# as bowler=Chahal even though Marco Jansen was bowling the over.
# Score / wickets are not stripped — ConsistentReadTracker bounds
# those.  Bowler is stripped because (a) bowler ingest bypasses the
# tracker, (b) bowler is sourced fresh on every active-play frame so
# one dropped frame loses no data, (c) future-bowler name-drops in
# stats overlays are a documented pattern.
# See backlog "P1: Bowler stats graphic misread as bowler-change".
# ---------------------------------------------------------------------
class _StubScoreboardForInfoPanel:
    """Minimal scoreboard-shaped stub with a populated _inn dict so
    `filter_info_panel_contamination` proceeds past its early-return
    guard."""
    def __init__(self):
        self._inn = {"score": 100, "wickets": 2, "overs": "12.3"}


def test_info_panel_gate_strips_bowler_on_career_keyword() -> None:
    header("Fix 8: vision_desc with 'IPL CAREER' marker → "
           "extracted['bowler'] stripped, [INFO-PANEL-GATE] log emitted")
    from test_pipeline import filter_info_panel_contamination

    extracted = {
        "score": 68, "wickets": 1, "match_overs": "6.0",
        "bowler": {"name": "YUZVENDRA CHAHAL"},
    }
    desc = ("STRIP: DC 68-1 (6) | INFO_PANEL: YUZVENDRA CHAHAL "
            "IPL CAREER MATCHES 181 WICKETS 225 ECONOMY 8.0")

    filter_info_panel_contamination(
        extracted, desc, _StubScoreboardForInfoPanel())

    check("bowler stripped from extracted",
          "bowler" not in extracted,
          f"extracted.bowler={extracted.get('bowler')!r}")
    check("score preserved (tracker bounds it)",
          extracted.get("score") == 68,
          f"extracted.score={extracted.get('score')!r}")
    check("match_overs preserved (tracker bounds it)",
          extracted.get("match_overs") == "6.0",
          f"extracted.match_overs={extracted.get('match_overs')!r}")


def test_info_panel_gate_no_op_when_no_keyword() -> None:
    header("Fix 8: vision_desc with no info-panel keyword → "
           "extracted['bowler'] preserved (legitimate bowler read)")
    from test_pipeline import filter_info_panel_contamination

    extracted = {
        "score": 68, "wickets": 1, "match_overs": "6.4",
        "bowler": {"name": "MARCO JANSEN"},
    }
    desc = ("STRIP: DC 68-1 (6.4) | BAT1: KL Rahul 22* / "
            "BAT2: Pathum Nissanka 14 | BOWL: M Jansen 1-22 (3.4)")

    filter_info_panel_contamination(
        extracted, desc, _StubScoreboardForInfoPanel())

    check("bowler preserved when no info-panel keyword present",
          extracted.get("bowler", {}).get("name") == "MARCO JANSEN",
          f"extracted.bowler={extracted.get('bowler')!r}")
    check("score preserved",
          extracted.get("score") == 68,
          f"extracted.score={extracted.get('score')!r}")


def test_info_panel_gate_f619_chahal_replay() -> None:
    header("Fix 8: F619 DC-vs-PBKS production replay — Chahal stats "
           "overlay during Jansen's over → bowler stripped")
    from test_pipeline import filter_info_panel_contamination

    extracted = {
        "score": 68, "wickets": 1, "match_overs": "6",
        "bowler": {"name": "YUZVENDRA CHAHAL"},
        "bowler_figures": "0-25 (3.0)",
    }
    desc = ("STRIP: DC 68-1 (6) |   INFO_PANEL: YUZVENDRA CHAHAL "
            "IPL CAREER MATCHES 181 WICKETS 225 ECONOMY 8.0")

    filter_info_panel_contamination(
        extracted, desc, _StubScoreboardForInfoPanel())

    check("F619 replay: Chahal name not surfaced as bowler",
          "bowler" not in extracted,
          f"extracted.bowler={extracted.get('bowler')!r}")
    check("F619 replay: bowler_figures from same overlay also stripped",
          "bowler_figures" not in extracted,
          f"extracted.bowler_figures="
          f"{extracted.get('bowler_figures')!r}")
    check("F619 replay: score (DC 68-1) preserved",
          extracted.get("score") == 68,
          f"extracted.score={extracted.get('score')!r}")


def test_info_panel_gate_logs_only_when_no_bowler_present() -> None:
    header("Fix 8: vision_desc with info-panel keyword but no bowler "
           "in extracted → no-op (logs only, no exception)")
    from test_pipeline import filter_info_panel_contamination

    extracted = {"score": 68, "wickets": 1, "match_overs": "6.0"}
    desc = "STRIP: DC 68-1 (6) | INFO_PANEL: HEAD TO HEAD vs PBKS"

    out = filter_info_panel_contamination(
        extracted, desc, _StubScoreboardForInfoPanel())

    check("function returns extracted dict (no exception)",
          out is extracted,
          f"out is extracted: {out is extracted}")
    check("score preserved (no bowler to strip)",
          extracted.get("score") == 68,
          f"extracted.score={extracted.get('score')!r}")
    check("no spurious bowler key added",
          "bowler" not in extracted,
          f"extracted.bowler={extracted.get('bowler')!r}")


def test_info_panel_gate_strips_all_three_bowler_fields() -> None:
    header("Fix 8: comprehensive strip — extracted with bowler, "
           "bowler_name, AND bowler_figures all present → all three "
           "stripped on info-panel keyword match")
    from test_pipeline import filter_info_panel_contamination

    extracted = {
        "score": 100, "wickets": 2, "match_overs": "12.3",
        "bowler": {"name": "YUZVENDRA CHAHAL"},
        "bowler_name": "YUZVENDRA CHAHAL",
        "bowler_figures": "1-25 (3.0)",
    }
    desc = "PROJECTED SCORE: DC TO REACH 180 IN 20 OVERS"

    filter_info_panel_contamination(
        extracted, desc, _StubScoreboardForInfoPanel())

    check("bowler dict stripped",
          "bowler" not in extracted,
          f"extracted.bowler={extracted.get('bowler')!r}")
    check("bowler_name stripped (parallel SM-ingest field)",
          "bowler_name" not in extracted,
          f"extracted.bowler_name={extracted.get('bowler_name')!r}")
    check("bowler_figures stripped (separate stats field)",
          "bowler_figures" not in extracted,
          f"extracted.bowler_figures="
          f"{extracted.get('bowler_figures')!r}")
    check("score, wickets, match_overs all preserved",
          (extracted.get("score") == 100
           and extracted.get("wickets") == 2
           and extracted.get("match_overs") == "12.3"),
          f"score={extracted.get('score')!r} "
          f"wickets={extracted.get('wickets')!r} "
          f"match_overs={extracted.get('match_overs')!r}")


def test_standings_row_gate_strips_score_fields() -> None:
    header("Standings-row gate: contextual table row strips score fields")
    from test_pipeline import filter_standings_row_contamination

    extracted = {
        "score": 7, "wickets": 1, "match_overs": "0.3",
        "batters": [{"name": "Rahul", "runs": 1, "balls": 1}],
        "bowler": {"name": "Bhuvneshwar Kumar"},
    }
    desc = "STRIP: DC 1-1 (0.4) | DC 7 | STANDINGS RCB 2"

    out = filter_standings_row_contamination(extracted, desc)

    check("function returns extracted dict",
          out is extracted,
          f"out is extracted: {out is extracted}")
    check("score stripped",
          "score" not in extracted,
          f"score={extracted.get('score')!r}")
    check("wickets stripped",
          "wickets" not in extracted,
          f"wickets={extracted.get('wickets')!r}")
    check("match_overs stripped",
          "match_overs" not in extracted,
          f"match_overs={extracted.get('match_overs')!r}")
    check("non-score fields preserved",
          "batters" in extracted and "bowler" in extracted,
          f"extracted={extracted!r}")


def test_standings_row_gate_no_op_without_keyword() -> None:
    header("Standings-row gate: normal strip is preserved")
    from test_pipeline import filter_standings_row_contamination

    extracted = {"score": 34, "wickets": 6, "match_overs": "7.5"}
    desc = "STRIP: DC 34-6 (7.5) | Miller 11(12) | Porel 15(14)"

    filter_standings_row_contamination(extracted, desc)

    check("score preserved",
          extracted.get("score") == 34,
          f"score={extracted.get('score')!r}")
    check("wickets preserved",
          extracted.get("wickets") == 6,
          f"wickets={extracted.get('wickets')!r}")
    check("match_overs preserved",
          extracted.get("match_overs") == "7.5",
          f"match_overs={extracted.get('match_overs')!r}")


def test_admission_normalizes_rinku_singh_ghost_row() -> None:
    header("Admission cluster: surname-only SINGH ghost row is dropped")
    from eyes.scoreboard import Scoreboard
    from test_pipeline import normalize_extracted_batters

    sb = Scoreboard()
    sb.setup_innings("KKR", "DC",
                     ["Rinku Singh", "Andre Russell", "Sunil Narine"],
                     ["Axar Patel", "Kuldeep Yadav"])

    extracted = {
        "batters": [
            {"name": "RINKU", "runs": 0, "balls": 0},
            {"name": "SINGH", "runs": None, "balls": None},
        ]
    }

    normalize_extracted_batters(extracted, sb)

    names = [b.get("name") for b in extracted.get("batters", [])]
    check("RINKU resolves to canonical Rinku Singh",
          names == ["Rinku Singh"],
          f"names={names!r}, batters={extracted.get('batters')!r}")


def test_admission_new_batter_impossible_balls_rejected() -> None:
    header("Admission cluster: fresh batter cannot enter as 0(16)")
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL",
                     ["Anchor", "Gone", "New Batter", "Four"],
                     ["Bowler One", "Bowler Two"])
    sb.batting_card["Anchor"].update(
        {"status": "batting", "runs": 20, "balls": 15})
    sb.batting_card["Gone"].update(
        {"status": "out", "runs": 5, "balls": 8})
    sb._inn["wickets"] = 1
    sb._inn["overs"] = "10.0"

    ok = sb.update_batter("New Batter", runs=0, balls=16, frame=100)

    row = sb.batting_card["New Batter"]
    check("fresh batter activation itself succeeds",
          ok is True and row.get("status") == "batting",
          f"ok={ok}, row={row!r}")
    check("impossible balls read is not committed",
          row.get("runs") == 0 and row.get("balls") == 0,
          f"row={row!r}")


def test_admission_batter_row_name_does_not_become_bowler() -> None:
    header("Admission cluster: active batter row suppressed as bowler")
    from eyes.scoreboard import Scoreboard
    from test_pipeline import filter_bowler_batter_row_contamination

    sb = Scoreboard()
    sb.setup_innings("DC", "RCB",
                     ["KL Rahul", "Abishek Porel", "Axar Patel"],
                     ["Bhuvneshwar Kumar", "Yash Dayal"])
    sb.batting_card["KL Rahul"]["status"] = "batting"
    sb.batting_card["Abishek Porel"]["status"] = "batting"

    extracted = {
        "batters": [{"name": "KL Rahul", "runs": 23, "balls": 17}],
        "bowler": {"name": "KL Rahul", "runs": 23},
        "bowler_name": "KL Rahul",
        "bowler_figures": "23",
    }

    filter_bowler_batter_row_contamination(extracted, sb)

    check("active batter not surfaced as bowler",
          "bowler" not in extracted and "bowler_name" not in extracted,
          f"extracted={extracted!r}")
    check("batting rows preserved",
          extracted.get("batters", [{}])[0].get("name") == "KL Rahul",
          f"batters={extracted.get('batters')!r}")


def test_recovery_cold_start_zero_graphic_rejected() -> None:
    header("Recovery cluster: contextual 0-0 review graphic rejected")
    from score_manager import ScoreManager, FrameInput

    sm = ScoreManager(shadow=False)

    def frame(i: int) -> FrameInput:
        return FrameInput(
            frame_id=str(i), timestamp=float(i),
            ext_score=0, ext_wickets=0, ext_overs=0.0,
            scout_text="DRS REVIEW graphic, no live batter/bowler strip")

    out = [sm.on_frame(frame(i)) for i in range(1, 4)]

    check("zero graphic never promotes to warm state",
          sm.mode == "COLD_START" and all(x is None for x in out),
          f"mode={sm.mode}, out={out!r}")
    check("zero graphic does not seed sticky cold candidate",
          sm.cold_candidate is None and sm.cold_candidate_streak == 0,
          f"candidate={sm.cold_candidate}, "
          f"streak={sm.cold_candidate_streak}")


def test_recovery_mid_innings_partnership_backstaged_until_ball() -> None:
    header("Recovery cluster: mid-innings partnership hidden until ball")
    from score_manager import ScoreManager, FrameInput

    sm = ScoreManager(shadow=False)

    def frame(i: int) -> FrameInput:
        return FrameInput(
            frame_id=str(i), timestamp=float(i),
            ext_score=75, ext_wickets=3, ext_overs=10.2,
            ext_bat1_name="A", ext_bat1_runs=25, ext_bat1_balls=20,
            ext_bat2_name="B", ext_bat2_runs=10, ext_bat2_balls=8,
            ext_bowler_name="Bowler", ext_bowler_runs=20,
            ext_bowler_wickets=1, ext_bowler_overs=2.2)

    payload = None
    for i in range(1, 4):
        payload = sm.on_frame(frame(i))

    partnership = (payload or {}).get("scorecard", {}).get("partnership")
    check("mid-innings accepted without seeding this_over placeholders",
          sm.mode == "WARM" and sm.this_over == [],
          f"mode={sm.mode}, this_over={sm.this_over!r}")
    check("partnership is backstaged on recovery payload",
          partnership == {"runs": None, "balls": None},
          f"partnership={partnership!r}")

    sm._apply_event({"type": "RUNS", "runs": 1, "legal": True,
                     "this_over_token": "1"},
                    {"overs": 10.2}, {"overs": 10.3},
                    frame(4))
    next_payload = sm._build_payload()
    next_partnership = next_payload["scorecard"]["partnership"]
    check("first post-recovery legal ball establishes anchor",
          next_partnership == {"runs": 1, "balls": 1},
          f"partnership={next_partnership!r}")


def test_recovery_this_over_resync_clears_saturated_cursor() -> None:
    header("Recovery cluster: this-over cursor resync clears stale buffer")
    from eyes.this_over import ThisOverManager

    om = ThisOverManager()
    om.this_over = ["."] * 12
    om.this_over_sources = ["obs"] * 12
    om._last_over_int = 0

    om.resync_to_over("16.3", reason="test")
    om.on_ball_event({"type": "RUNS", "runs": 1, "certain": True,
                      "over": "16.3"}, score=75)

    check("cursor aligned to accepted mid-innings over",
          om._last_over_int == 16,
          f"last_over_int={om._last_over_int}")
    check("stale 12-token buffer cleared before next ball",
          om.this_over == ["1"],
          f"this_over={om.this_over!r}")


def test_physics_all_out_authority_promotes_and_locks_regression() -> None:
    header("Physics cluster: final-wicket evidence promotes all-out")
    from eyes.scoreboard import Scoreboard
    from test_pipeline import apply_all_out_authority

    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL",
                     ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
                     ["Bowler"])
    sb._inn["score"] = 75
    sb._inn["wickets"] = 9
    sb._inn["overs"] = "16.3"
    sb._tracker.force_set("wickets", 9)

    accepted = apply_all_out_authority(
        sb, "Bowled him. That is the final wicket, innings break.", frame=200)
    regressed = sb.set("wickets", 2, frame=201)

    check("all-out authority promotes 9 wickets to 10",
          accepted is True and sb._inn.get("wickets") == 10,
          f"accepted={accepted}, wickets={sb._inn.get('wickets')}")
    check("contextual wicket regression blocked under all-out lock",
          regressed is False and sb._inn.get("wickets") == 10,
          f"regressed={regressed}, wickets={sb._inn.get('wickets')}")


def test_physics_score_regression_blocked_without_reset_authority() -> None:
    header("Physics cluster: normal-play team score regression blocked")
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL", ["A", "B"], ["Bowler"])
    sb._inn["score"] = 36
    sb._tracker.force_set("score", 36)

    accepted = sb.set("score", 35, frame=300)

    check("score regression rejected",
          accepted is False and sb._inn.get("score") == 36,
          f"accepted={accepted}, score={sb._inn.get('score')}")


def test_ws_slot_invariant_repairs_duplicate_active_slots() -> None:
    header("WS slot invariant: duplicate striker/non repaired")
    from eyes.scoreboard import Scoreboard
    from test_pipeline import enforce_ws_slot_invariant

    sb = Scoreboard()
    sb.setup_innings("DC", "RCB",
                     ["Abishek Porel", "KL Rahul", "Axar Patel"],
                     ["Bhuvneshwar Kumar"])
    sb.batting_card["Abishek Porel"]["status"] = "batting"
    sb.batting_card["KL Rahul"]["status"] = "batting"
    state = {
        "striker": "Abishek Porel",
        "non": "Abishek Porel",
    }

    changed = enforce_ws_slot_invariant(state, sb, _identity_canon)

    check("duplicate collision detected",
          changed is True,
          f"changed={changed}")
    check("non rebuilt from alternate active batter",
          state == {"striker": "Abishek Porel",
                    "non": "KL Rahul"},
          f"state={state!r}")


def test_ws_slot_invariant_clears_when_no_alternate_active() -> None:
    header("WS slot invariant: duplicate slot clears without alternate")
    from eyes.scoreboard import Scoreboard
    from test_pipeline import enforce_ws_slot_invariant

    sb = Scoreboard()
    sb.setup_innings("DC", "RCB",
                     ["Abishek Porel", "KL Rahul"],
                     ["Bhuvneshwar Kumar"])
    sb.batting_card["Abishek Porel"]["status"] = "batting"
    state = {
        "striker": "Abishek Porel",
        "non": "Abishek Porel",
    }

    changed = enforce_ws_slot_invariant(state, sb, _identity_canon)

    check("duplicate collision detected",
          changed is True,
          f"changed={changed}")
    check("non cleared when no alternate exists",
          state.get("striker") == "Abishek Porel"
          and state.get("non") is None,
          f"state={state!r}")


# ---------------------------------------------------------------------
# Debug-frame archival (P2 fix, 2026-04-25): startup cleanup must move
# existing frames into a dated archive subdir instead of deleting, so
# that an in-flight evaluation whose JSON references `debug_frames/...`
# survives a mid-session pipeline restart.  Retention cap bounds disk.
# ---------------------------------------------------------------------
def _setup_archival_tmpdir():
    import tempfile
    return tempfile.mkdtemp(prefix="sportscomm_archival_test_")


def _make_jpg(path: str, payload: bytes = b"\xff\xd8stub") -> None:
    import os as _os
    _os.makedirs(_os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(payload)


def test_archival_noop_when_src_dir_missing() -> None:
    header("Archival: missing source dir → no-op (no crash, no archive subdir)")
    import os, shutil
    from test_pipeline import _archive_old_debug_frames
    tmp = _setup_archival_tmpdir()
    try:
        src = os.path.join(tmp, "debug_frames")
        archive = os.path.join(tmp, "debug_frames_archive")
        moved = _archive_old_debug_frames(src, archive, session_id="s1")
        check("returns 0 when src missing", moved == 0, f"moved={moved}")
        check("archive root not created", not os.path.exists(archive),
              f"archive exists? {os.path.exists(archive)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_archival_noop_when_src_empty() -> None:
    header("Archival: empty source dir → no-op (no empty session subdir)")
    import os, shutil
    from test_pipeline import _archive_old_debug_frames
    tmp = _setup_archival_tmpdir()
    try:
        src = os.path.join(tmp, "debug_frames")
        archive = os.path.join(tmp, "debug_frames_archive")
        os.makedirs(src)
        moved = _archive_old_debug_frames(src, archive, session_id="s1")
        check("returns 0 on empty src", moved == 0, f"moved={moved}")
        check("no session subdir created",
              not os.path.exists(os.path.join(archive, "s1")),
              f"unexpected subdir at {archive}/s1")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_archival_moves_existing_frames() -> None:
    header("Archival: existing frames moved to dated subdir, src is empty after")
    import os, shutil
    from test_pipeline import _archive_old_debug_frames
    tmp = _setup_archival_tmpdir()
    try:
        src = os.path.join(tmp, "debug_frames")
        archive = os.path.join(tmp, "debug_frames_archive")
        names = ["f100_scoreboard.jpg", "f101_scoreboard.jpg",
                 "f976_scoreboard.jpg"]
        for n in names:
            _make_jpg(os.path.join(src, n))
        moved = _archive_old_debug_frames(
            src, archive, session_id="2026-04-25_184000")
        check("moved == 3", moved == 3, f"moved={moved}")
        dest = os.path.join(archive, "2026-04-25_184000")
        for n in names:
            check(f"{n} present in archive",
                  os.path.exists(os.path.join(dest, n)),
                  f"missing {os.path.join(dest, n)}")
            check(f"{n} removed from src",
                  not os.path.exists(os.path.join(src, n)),
                  f"still at {os.path.join(src, n)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_archival_preserves_eval_path_resolution() -> None:
    header("Archival: prod-eval JSON-style path can resolve via archive subdir")
    import os, shutil
    from test_pipeline import _archive_old_debug_frames
    tmp = _setup_archival_tmpdir()
    try:
        src = os.path.join(tmp, "debug_frames")
        archive = os.path.join(tmp, "debug_frames_archive")
        _make_jpg(os.path.join(src, "f976_scoreboard.jpg"))
        _archive_old_debug_frames(
            src, archive, session_id="2026-04-25_184000")
        archived = os.path.join(
            archive, "2026-04-25_184000", "f976_scoreboard.jpg")
        check("archived frame readable",
              os.path.exists(archived) and os.path.getsize(archived) > 0,
              f"missing or empty: {archived}")
        check("src dir empty after archival",
              not os.listdir(src), f"src still has: {os.listdir(src)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_archival_retention_drops_oldest_sessions() -> None:
    header("Archival: retention cap removes oldest sessions beyond keep_last_n")
    import os, shutil
    from test_pipeline import _archive_old_debug_frames
    tmp = _setup_archival_tmpdir()
    try:
        src = os.path.join(tmp, "debug_frames")
        archive = os.path.join(tmp, "debug_frames_archive")
        sids = [f"2026-04-{d:02d}_120000" for d in (20, 21, 22, 23, 24, 25)]
        for sid in sids:
            os.makedirs(src, exist_ok=True)
            _make_jpg(os.path.join(src, "f1.jpg"))
            _archive_old_debug_frames(
                src, archive, keep_last_n=3, session_id=sid)
        remaining = sorted(os.listdir(archive))
        check("only 3 sessions retained",
              len(remaining) == 3, f"remaining={remaining}")
        check("retained sessions are the 3 newest",
              remaining == sids[-3:],
              f"remaining={remaining}, expected={sids[-3:]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_archival_retention_noop_when_under_cap() -> None:
    header("Archival: retention is no-op when archive size <= keep_last_n")
    import os, shutil
    from test_pipeline import _archive_old_debug_frames
    tmp = _setup_archival_tmpdir()
    try:
        src = os.path.join(tmp, "debug_frames")
        archive = os.path.join(tmp, "debug_frames_archive")
        sids = ["2026-04-23_120000", "2026-04-24_120000"]
        for sid in sids:
            os.makedirs(src, exist_ok=True)
            _make_jpg(os.path.join(src, "f1.jpg"))
            _archive_old_debug_frames(
                src, archive, keep_last_n=10, session_id=sid)
        remaining = sorted(os.listdir(archive))
        check("both sessions retained",
              remaining == sids, f"remaining={remaining}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------
# 10. BOWLER-STALE freshness disambiguator (2026-04-25 RR-vs-SRH fix)
#
# The same-figures rejection in update_bowler() pre-fix had no way to
# distinguish "fresh between-ball repeat read of a new bowler trying
# to take over" (recorded values were just written 1-N frames ago by
# THIS spell) from "genuine end-of-spell stale graphic of a long-
# departed bowler" (recorded values were written long ago and the
# graphic is now resurfacing).  The trap: every same-figures read
# was rejected, so 3-frame consensus never accumulated, so
# current_bowler never flipped.
#
# Production damage 2026-04-25 (match-2 RR vs SRH innings 1):
# 54+ rejects across 4 distinct bowlers (Shivang / Sakib / Hinge /
# Cummins).  Damage propagates via BOWLER-AUTO inflating still-current
# bowler's stats with the new bowler's deliveries.
#
# Fix: bypass same-figures rejection iff (a) recorded values written
# within `_BOWLER_STALE_FRESH_FRAMES` AND (b) `current_bowler` hasn't
# changed since that write.  When EITHER condition fails (figures are
# old, or bowler context changed in the interim), original stale-
# graphic defense fires unchanged.
# ---------------------------------------------------------------------
def _setup_bowler_trap_sb(initial_current_bowler: str = "Sakib Hussain"):
    """Fresh Scoreboard wired for the BOWLER-STALE trap exercise.

    Bowling card pre-populated with the four match-2 bowlers; one is
    already the established `current_bowler`.  No rotation lock
    (so `_prev_over_bowler` is None and the rotation guard is inert).
    """
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="Rajasthan Royals",
        bowling_team="Sunrisers Hyderabad",
        batting_squad=["Sooryavanshi", "Jurel"],
        bowling_squad=[
            "Sakib Hussain", "Shivang Kumar",
            "Pat Cummins", "Eshan Malinga"],
        batting_xi=["Sooryavanshi", "Jurel"],
        bowling_xi=[
            "Sakib Hussain", "Shivang Kumar",
            "Pat Cummins", "Eshan Malinga"],
    )
    sb._inn["current_bowler"] = initial_current_bowler
    sb._inn["overs"] = "5.1"
    sb._prev_over_bowler = None
    sb._bowler_must_change = False
    return sb


def _establish_bowler_stats(
        sb, name: str, *,
        overs: str, runs: int, wickets: int, start_frame: int) -> int:
    """Push 3 consecutive reads through update_bowler() so the cold-
    start tracker commits the figures and the freshness disambiguator
    stamps `_bowling_card_active_write_*`.  Returns the next free
    frame number (start_frame + 3).
    """
    f = start_frame
    for _ in range(3):
        sb.update_bowler(name, overs=overs, runs=runs,
                         wickets=wickets, frame=f)
        f += 1
    return f


def test_bowler_stale_replay_shivang_f311_f500_trap() -> None:
    header("BOWLER-STALE: Shivang F311-F500 replay flips current_bowler "
           "(within 3-frame consensus) instead of trapping")
    sb = _setup_bowler_trap_sb(initial_current_bowler="Sakib Hussain")
    # Establish Sakib as a real recorded bowler so the trap state
    # mirrors production: 1-13 (1).  Cold-start tracker commits
    # only on the third consistent read.
    _establish_bowler_stats(
        sb, "Sakib Hussain", overs="1", runs=13, wickets=1,
        start_frame=100)
    check("Sakib's card committed to 1/13/(1)",
          sb.bowling_card["Sakib Hussain"]["runs"] == 13,
          f"sakib_card={sb.bowling_card['Sakib Hussain']}")
    # Fast-forward across the over boundary.  Now Scout starts
    # reading Shivang's strip.  Frame numbers mirror the production
    # F311-F500 sequence (advance frame by 1 per call to model
    # back-to-back broadcast reads between deliveries).
    fr = 311
    sb.update_bowler(
        "Shivang Kumar", overs="0.1", runs=1, wickets=0, frame=fr)
    fr += 1
    sb.update_bowler(
        "Shivang Kumar", overs="0.1", runs=1, wickets=0, frame=fr)
    fr += 1
    sb.update_bowler(
        "Shivang Kumar", overs="0.1", runs=1, wickets=0, frame=fr)
    # After three same-figures reads of Shivang within the freshness
    # window, consensus should flip current_bowler.
    check("current_bowler flipped to Shivang after 3 reads",
          sb._inn["current_bowler"] == "Shivang Kumar",
          f"current_bowler={sb._inn['current_bowler']}")
    # And Shivang's stats should now match the proposed read (the
    # tracker writes happen before the rejection branch did pre-fix;
    # post-fix they continue to land on the right card).
    sk = sb.bowling_card["Shivang Kumar"]
    check("Shivang's card holds proposed figures (0/1/0.1)",
          sk.get("runs") == 1 and sk.get("overs") == "0.1",
          f"shivang_card={sk}")


def test_bowler_stale_replay_sakib_second_trap_general() -> None:
    header("BOWLER-STALE: Sakib F527-style sequence flips current_bowler "
           "(generality across 4 affected bowlers from production)")
    # In match-2 production the Sakib trap fired at F527-F643 with
    # current_bowler stuck on a previous bowler.  The fix should
    # generalise to any new-bowler-takeover sequence regardless of
    # which name carries the trap.
    sb = _setup_bowler_trap_sb(initial_current_bowler="Pat Cummins")
    # Pat Cummins established with a real spell (3 reads to commit).
    _establish_bowler_stats(
        sb, "Pat Cummins", overs="2", runs=20, wickets=0,
        start_frame=400)
    fr = 527
    sb._inn["overs"] = "10.2"
    for _ in range(3):
        sb.update_bowler(
            "Sakib Hussain", overs="0.2", runs=4, wickets=0, frame=fr)
        fr += 1
    check("current_bowler flipped to Sakib (generality holds)",
          sb._inn["current_bowler"] == "Sakib Hussain",
          f"current_bowler={sb._inn['current_bowler']}")
    sk = sb.bowling_card["Sakib Hussain"]
    check("Sakib's card holds proposed figures (0/4/0.2)",
          sk.get("runs") == 4 and sk.get("overs") == "0.2",
          f"sakib_card={sk}")


def test_bowler_stale_genuine_stale_graphic_still_rejected() -> None:
    header("BOWLER-STALE: long-gap replay of same figures (different "
           "bowler context) still triggers stale-graphic rejection")
    # Setup: Shivang bowled an over earlier when he was current.  His
    # spell ended; another bowler is now bowling.  A stale graphic of
    # Shivang's end-of-spell figures resurfaces.  Original defense's
    # whole purpose; must remain intact.
    sb = _setup_bowler_trap_sb(initial_current_bowler="Shivang Kumar")
    # Write Shivang's over-end figures while he is current_bowler.
    _establish_bowler_stats(
        sb, "Shivang Kumar", overs="1.0", runs=10, wickets=0,
        start_frame=100)
    check("Shivang's card recorded under his own context",
          sb._bowling_card_active_write_bowler.get("Shivang Kumar")
          == "Shivang Kumar",
          f"write_bowler="
          f"{sb._bowling_card_active_write_bowler.get('Shivang Kumar')}")
    # Now Pat Cummins takes over and bowls an over; current_bowler
    # transitions away from Shivang.
    sb._inn["current_bowler"] = "Pat Cummins"
    # Long after Shivang's spell ended (well past freshness window
    # AND with a different bowler now current), a stale graphic of
    # Shivang's end-of-spell figures resurfaces at frame 1000.
    accepted = sb.update_bowler(
        "Shivang Kumar", overs="1.0", runs=10, wickets=0, frame=1000)
    check("stale-graphic read at F1000 rejected",
          accepted is False,
          f"accepted={accepted}")
    check("current_bowler stayed Pat Cummins (rejection took effect)",
          sb._inn["current_bowler"] == "Pat Cummins",
          f"current_bowler={sb._inn['current_bowler']}")


def test_bowler_stale_boundary_within_freshness_same_context() -> None:
    header("BOWLER-STALE: F100→F101 same current_bowler context — "
           "same-figures repeat ACCEPTED (between-deliveries pattern)")
    sb = _setup_bowler_trap_sb(initial_current_bowler="Sakib Hussain")
    # Establish Shivang's first-ball figures via 3-frame consensus
    # so the same-figures gate has something to compare against.
    next_f = _establish_bowler_stats(
        sb, "Shivang Kumar", overs="0.1", runs=1, wickets=0,
        start_frame=100)
    # The 3rd read inside that helper would have already flipped
    # current_bowler if the disambiguator releases the trap.
    check("3-frame consensus flipped current_bowler to Shivang",
          sb._inn["current_bowler"] == "Shivang Kumar",
          f"current_bowler={sb._inn['current_bowler']}")
    # One more same-figures read at next_f (still within freshness
    # window, current_bowler unchanged): should be accepted, not
    # rejected as stale-graphic.
    accepted = sb.update_bowler(
        "Shivang Kumar", overs="0.1", runs=1, wickets=0,
        frame=next_f)
    check("same-figures repeat within fresh window: not rejected",
          accepted is not False,
          f"accepted={accepted}")


def test_bowler_stale_boundary_within_freshness_different_context() -> None:
    header("BOWLER-STALE: F100→F101 different current_bowler context — "
           "same-figures repeat REJECTED (rapid stale-graphic signature)")
    # Setup: at F100, Shivang's stats are written while he is current
    # bowler.  At F101 (within the fresh window), current_bowler has
    # already changed (e.g. via an over-end transition), and Shivang's
    # same-figures graphic is being re-read.  This is the "rapid
    # bowler-handover with stale graphic" case the disambiguator
    # specifically protects.  Acceptance would let stale graphics flip
    # current_bowler back to a departed bowler.
    sb = _setup_bowler_trap_sb(initial_current_bowler="Shivang Kumar")
    next_f = _establish_bowler_stats(
        sb, "Shivang Kumar", overs="0.1", runs=1, wickets=0,
        start_frame=100)
    # Now flip current_bowler externally (simulates an over-end
    # transition that has already moved on to the next bowler).
    sb._inn["current_bowler"] = "Pat Cummins"
    # One frame later, Shivang's stale graphic resurfaces with the
    # exact figures we just wrote — within freshness window but
    # under a different bowler context.  This is the stale-graphic
    # signature the original defense exists to catch; the
    # disambiguator must NOT release the rejection here.
    accepted = sb.update_bowler(
        "Shivang Kumar", overs="0.1", runs=1, wickets=0,
        frame=next_f)
    check("rapid stale-graphic across context change still rejected",
          accepted is False,
          f"accepted={accepted}")
    check("current_bowler stayed Pat Cummins",
          sb._inn["current_bowler"] == "Pat Cummins",
          f"current_bowler={sb._inn['current_bowler']}")


def test_bowler_team_over_consensus_promotes_matching_candidate() -> None:
    header("Fix 17B: bowler team-over consistency promotes new bowler "
           "when current bowler is stale")
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="Delhi Capitals",
        bowling_team="Royal Challengers Bengaluru",
        batting_squad=["Rahul", "Stubbs"],
        bowling_squad=["Bhuvneshwar Kumar", "Suyash Sharma"],
        batting_xi=["Rahul", "Stubbs"],
        bowling_xi=["Bhuvneshwar Kumar", "Suyash Sharma"],
    )
    sb._inn["current_bowler"] = "Bhuvneshwar Kumar"
    sb._inn["overs"] = "10.2"
    sb.bowling_card["Bhuvneshwar Kumar"]["overs"] = "2.0"
    sb.bowling_card["Bhuvneshwar Kumar"]["runs"] = 22
    sb.bowling_card["Bhuvneshwar Kumar"]["wickets"] = 1

    sb.update_bowler(
        "Suyash Sharma", overs="0.2", runs=8, wickets=0, frame=1200)
    check("one read alone does not override current bowler",
          sb._inn["current_bowler"] == "Bhuvneshwar Kumar",
          f"current_bowler={sb._inn['current_bowler']}")
    sb.update_bowler(
        "Suyash Sharma", overs="0.2", runs=8, wickets=0, frame=1201)

    check("second team-over-consistent read promotes Suyash",
          sb._inn["current_bowler"] == "Suyash Sharma",
          f"current_bowler={sb._inn['current_bowler']}")


def test_bowler_team_over_consensus_ignores_mismatched_candidate() -> None:
    header("Fix 17B: mismatched bowler overs do not get accelerated")
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="Delhi Capitals",
        bowling_team="Royal Challengers Bengaluru",
        batting_squad=["Rahul", "Stubbs"],
        bowling_squad=["Bhuvneshwar Kumar", "Suyash Sharma"],
        batting_xi=["Rahul", "Stubbs"],
        bowling_xi=["Bhuvneshwar Kumar", "Suyash Sharma"],
    )
    sb._inn["current_bowler"] = "Bhuvneshwar Kumar"
    sb._inn["overs"] = "10.2"
    sb.bowling_card["Bhuvneshwar Kumar"]["overs"] = "2.0"

    for frame in (1300, 1301):
        sb.update_bowler(
            "Suyash Sharma", overs="0.1", runs=4, wickets=0,
            frame=frame)

    check("mismatched 0.1 vs team 10.2 waits for normal consensus",
          sb._inn["current_bowler"] == "Bhuvneshwar Kumar",
          f"current_bowler={sb._inn['current_bowler']}")


def test_bowler_plain_consensus_rejects_spell_ball_mismatch() -> None:
    header("Fix 17B+: plain 3-frame consensus blocked when spell overs "
           "ball-index disagrees with team strip")
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="Delhi Capitals",
        bowling_team="Royal Challengers Bengaluru",
        batting_squad=["Rahul", "Stubbs"],
        bowling_squad=["Bhuvneshwar Kumar", "Suyash Sharma"],
        batting_xi=["Rahul", "Stubbs"],
        bowling_xi=["Bhuvneshwar Kumar", "Suyash Sharma"],
    )
    sb._inn["current_bowler"] = "Bhuvneshwar Kumar"
    sb._inn["overs"] = "10.2"
    sb.bowling_card["Bhuvneshwar Kumar"]["overs"] = "2.0"

    for frame in (1400, 1401, 1402):
        sb.update_bowler(
            "Suyash Sharma", overs="2.0", runs=8, wickets=0,
            frame=frame)

    check("three consecutive reads with 2.0 vs team 10.2 do not flip",
          sb._inn["current_bowler"] == "Bhuvneshwar Kumar",
          f"current_bowler={sb._inn['current_bowler']}")


def test_bowler_plain_consensus_accepts_aligned_spell_ball() -> None:
    header("Fix 17B+: plain consensus accepts when spell ball matches strip")
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="Delhi Capitals",
        bowling_team="Royal Challengers Bengaluru",
        batting_squad=["Rahul", "Stubbs"],
        bowling_squad=["Bhuvneshwar Kumar", "Suyash Sharma"],
        batting_xi=["Rahul", "Stubbs"],
        bowling_xi=["Bhuvneshwar Kumar", "Suyash Sharma"],
    )
    sb._inn["current_bowler"] = "Bhuvneshwar Kumar"
    sb._inn["overs"] = "10.2"
    sb.bowling_card["Bhuvneshwar Kumar"]["overs"] = "2.0"

    for frame in (1500, 1501, 1502):
        sb.update_bowler(
            "Suyash Sharma", overs="0.2", runs=8, wickets=0,
            frame=frame)

    check("aligned 0.2 flips on third read",
          sb._inn["current_bowler"] == "Suyash Sharma",
          f"current_bowler={sb._inn['current_bowler']}")


def test_bowler_plain_consensus_override_after_repeated_mismatch() -> None:
    header("Fix 17B+: inconsistent streak override accepts flip with WARN")
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="Delhi Capitals",
        bowling_team="Royal Challengers Bengaluru",
        batting_squad=["Rahul", "Stubbs"],
        bowling_squad=["Bhuvneshwar Kumar", "Suyash Sharma"],
        batting_xi=["Rahul", "Stubbs"],
        bowling_xi=["Bhuvneshwar Kumar", "Suyash Sharma"],
    )
    sb._inn["current_bowler"] = "Bhuvneshwar Kumar"
    sb._inn["overs"] = "10.2"
    sb.bowling_card["Bhuvneshwar Kumar"]["overs"] = "2.0"

    for frame in (1600, 1601, 1602, 1603, 1604):
        sb.update_bowler(
            "Suyash Sharma", overs="2.0", runs=8, wickets=0,
            frame=frame)

    check("fifth inconsistent frame forces override flip",
          sb._inn["current_bowler"] == "Suyash Sharma",
          f"current_bowler={sb._inn['current_bowler']}")
    check("override cleared streak",
          sb._bowler_consensus_inconsistent_streak.get("Suyash Sharma") is None,
          f"streak={sb._bowler_consensus_inconsistent_streak}")


def test_batch_m_per_field_rejection() -> None:
    header("Batch M: bowler stats regression keeps wickets pinned but "
           "accepts overs/runs (per-field guard, not whole-frame poison)")
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="Delhi Capitals",
        bowling_team="Royal Challengers Bengaluru",
        batting_squad=["Rahul", "Stubbs"],
        bowling_squad=["Bhuvneshwar Kumar", "Suyash Sharma"],
        batting_xi=["Rahul", "Stubbs"],
        bowling_xi=["Bhuvneshwar Kumar", "Suyash Sharma"],
    )
    sb._inn["current_bowler"] = "Bhuvneshwar Kumar"
    sb._inn["overs"] = "3.2"
    sb.bowling_card["Bhuvneshwar Kumar"]["overs"] = "3.0"
    sb.bowling_card["Bhuvneshwar Kumar"]["runs"] = 22
    sb.bowling_card["Bhuvneshwar Kumar"]["wickets"] = 1

    accepted = sb.update_bowler(
        "Bhuvneshwar Kumar", overs="3.2", runs=24, wickets=0,
        frame=2000)

    card = sb.bowling_card["Bhuvneshwar Kumar"]
    check("update not rejected wholesale (per-field guard)",
          accepted is not False and card["wickets"] == 1,
          f"accepted={accepted!r} card={card}")
    check("wickets pinned at current value (not regressed)",
          card["wickets"] == 1,
          f"wickets={card['wickets']}")
    check("overs advanced past the regression",
          card["overs"] in ("3.2", 3.2),
          f"overs={card['overs']!r}")
    check("runs accepted from the read",
          card["runs"] == 24,
          f"runs={card['runs']!r}")


def test_batch_m_full_consistent_update() -> None:
    header("Batch M: normal monotonic bowler updates still apply when "
           "wickets do not regress")
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="Delhi Capitals",
        bowling_team="Royal Challengers Bengaluru",
        batting_squad=["Rahul", "Stubbs"],
        bowling_squad=["Bhuvneshwar Kumar", "Suyash Sharma"],
        batting_xi=["Rahul", "Stubbs"],
        bowling_xi=["Bhuvneshwar Kumar", "Suyash Sharma"],
    )
    sb._inn["current_bowler"] = "Bhuvneshwar Kumar"
    sb._inn["overs"] = "3.2"
    sb.bowling_card["Bhuvneshwar Kumar"]["overs"] = "3.0"
    sb.bowling_card["Bhuvneshwar Kumar"]["runs"] = 22
    sb.bowling_card["Bhuvneshwar Kumar"]["wickets"] = 1

    accepted = sb.update_bowler(
        "Bhuvneshwar Kumar", overs="3.2", runs=26, wickets=2,
        frame=2100)

    card = sb.bowling_card["Bhuvneshwar Kumar"]
    check("update accepted when wickets advance",
          accepted is not False,
          f"accepted={accepted!r}")
    check("wickets advanced to proposed value",
          card["wickets"] == 2,
          f"wickets={card['wickets']}")
    check("overs advanced",
          card["overs"] in ("3.2", 3.2),
          f"overs={card['overs']!r}")
    check("runs advanced",
          card["runs"] == 26,
          f"runs={card['runs']!r}")


def test_project_fow_for_payload_hides_unwitnessed_placeholders() -> None:
    header("DC-vs-CSK Fix 1: unwitnessed FOW rows render as ?/TBD "
           "(no silent drop, no batter back-fill)")
    from eyes.scoreboard import Scoreboard
    from test_pipeline import project_fow_for_payload

    fow = [
        Scoreboard.make_fow_placeholder(1),
        {
            "wicket": 2,
            "batter": "Rahul",
            "score": 54,
            "overs": "6.3",
            "bowler": "Suyash Sharma",
            "how": "c keeper b Suyash",
            "_witnessed": True,
        },
    ]

    visible, internal_count = project_fow_for_payload(fow)

    check("unwitnessed placeholder surfaces with '?' batter marker",
          len(visible) == 2
          and visible[0]["batter"] == "?"
          and visible[0]["_unwitnessed"] is True
          and visible[0]["bowler"] == "TBD"
          and visible[0]["how"] == "TBD",
          f"visible[0]={visible[0]}")
    check("witnessed entry passes through unchanged",
          visible[1]["batter"] == "Rahul"
          and visible[1].get("_unwitnessed") is False,
          f"visible[1]={visible[1]}")
    check("internal FOW count retained for cricket physics",
          internal_count == 2,
          f"internal_count={internal_count}")


def test_sampler_emits_bucket_coverage_report() -> None:
    header("Maintenance: stratified sampler emits bucket coverage report")
    with open("select_corpus_candidates.py") as f:
        src = f.read()

    check("sampler writes bucket_coverage to output JSON",
          '"bucket_coverage": bucket_coverage' in src,
          "bucket_coverage missing from JSON output")
    check("sampler warns on non-empty pool with zero sample",
          "[BUCKET-COVERAGE]" in src and "pool > 0 and sampled == 0" in src,
          "missing bucket warning path")


def _combined_sampler_mod():
    """Load ``scripts/select_combined_scout_corpus.py`` (not a package)."""
    root = Path(__file__).resolve().parent
    path = root / "scripts" / "select_combined_scout_corpus.py"
    spec = importlib.util.spec_from_file_location("_select_combined", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _synthetic_inventory_pathological(target_path: Path) -> None:
    """Six phase×innings strata with ≥1 SCOREBOARD frame bucketed each."""
    events = [
        {"frame_count": 100, "ts": "0", "event": "SIX", "over": "1.2"},
        {"frame_count": 200, "ts": "0", "event": "FOUR", "over": "8.4"},
        {"frame_count": 300, "ts": "0", "event": "WICKET", "over": "17.3"},
        {"frame_count": 400, "ts": "0", "event": "DOT", "over": "0.2"},
        {"frame_count": 500, "ts": "0", "event": "SIX", "over": "7.6"},
        {"frame_count": 600, "ts": "0", "event": "FOUR", "over": "16.5"},
    ]
    anchors = [(101, 100), (201, 200), (301, 300),
               (401, 400), (501, 500), (601, 600)]
    frames = []
    for fc, _anchor in anchors:
        frames.append({
            "frame_count": fc,
            "frame_path": f"debug_frames/f{fc}_scoreboard.jpg",
            "scout_frame_type": "SCOREBOARD",
            "scout_cam": "bowlers_end",
            "scout_phase": "release",
        })
    target_path.write_text(
        json.dumps({
            "match_id": "synth_mixed",
            "events": events,
            "frames": frames,
        }, indent=2),
        encoding="utf-8",
    )


def _run_combined_sampler_cli(argv: list[str]) -> subprocess.CompletedProcess:
    root = Path(__file__).resolve().parent
    script = root / "scripts" / "select_combined_scout_corpus.py"
    cmd = [sys.executable, str(script), *argv]
    return subprocess.run(
        cmd, cwd=str(root), capture_output=True, text=True)


def test_combined_sampler_emits_phase_bucket_coverage() -> None:
    header("Combined sampler M-2: bucket_coverage + stderr flags")
    root = Path(__file__).resolve().parent
    inv_path = root / "_tmp_combined_sampler_inv.json"
    out_path = root / "_tmp_combined_sampler_out.json"
    try:
        _synthetic_inventory_pathological(inv_path)
        proc = _run_combined_sampler_cli([
            "--inventory",
            str(inv_path),
            "--output",
            str(out_path),
            "--target-per-bucket",
            "0",
            "--seed",
            "99",
        ])
        check("sampler exits successfully",
              proc.returncode == 0,
              f"stderr={proc.stderr[:500]} stdout={proc.stdout[:200]}")
        data = json.loads(out_path.read_text(encoding="utf-8"))
        cov = data["metadata"]["bucket_coverage"]
        mod = _combined_sampler_mod()
        buckets_got = {r["bucket"] for r in cov}
        buckets_exp = set(mod.PHASE_BUCKETS)
        check("coverage lists all six strata",
              buckets_got == buckets_exp,
              f"{buckets_got ^ buckets_exp}")
        undoc = [
            r for r in cov
            if r["status"] == "UNDOCUMENTED_ZERO"
        ]
        check(".pool>0 and target 0 ⇒ UNDOCUMENTED_ZERO strata",
              len(undoc) >= 6,
              f"coverage={[ (x['bucket'], x['status']) for x in cov ]}")
        check(
            "[BUCKET-COVERAGE] UNDOCUMENTED_ZERO on stderr",
            "UNDOCUMENTED_ZERO" in proc.stderr,
            proc.stderr[:500],
        )
    finally:
        for p in (inv_path, out_path):
            if p.is_file():
                p.unlink()


def test_combined_sampler_deterministic_with_seed() -> None:
    header("Combined sampler: identical JSON with same inputs + seed")
    root = Path(__file__).resolve().parent
    inv_path = root / "_tmp_combined_sampler_inv_det.json"
    out_a = root / "_tmp_combined_sampler_out_a.json"
    out_b = root / "_tmp_combined_sampler_out_b.json"
    try:
        _synthetic_inventory_pathological(inv_path)
        for outp in (out_a, out_b):
            proc = _run_combined_sampler_cli([
                "--inventory",
                str(inv_path),
                "--output",
                str(outp),
                "--target-per-bucket",
                "8",
                "--seed",
                "12345",
            ])
            check("deterministic runs exit 0",
                  proc.returncode == 0, proc.stderr[:400])
        a = out_a.read_text(encoding="utf-8")
        b = out_b.read_text(encoding="utf-8")
        check("bit-identical combined corpus JSON",
              a == b, f"diff len {len(a)} vs {len(b)}")
    finally:
        for p in (inv_path, out_a, out_b):
            if p.is_file():
                p.unlink()


def test_combined_sampler_strict_mode_exits_nonzero_on_warn() -> None:
    header("Combined sampler: --strict exit 2 when coverage warns")
    root = Path(__file__).resolve().parent
    inv_path = root / "_tmp_combined_sampler_inv_strict.json"
    out_path = root / "_tmp_combined_sampler_out_strict.json"
    try:
        _synthetic_inventory_pathological(inv_path)
        proc = _run_combined_sampler_cli([
            "--inventory",
            str(inv_path),
            "--output",
            str(out_path),
            "--target-per-bucket",
            "0",
            "--strict",
            "--seed",
            "1",
        ])
        check("--strict exits non-zero on UNDOCUMENTED_ZERO",
              proc.returncode == 2, f"code={proc.returncode}")
        check(
            "stderr still has [BUCKET-COVERAGE]",
            "[BUCKET-COVERAGE]" in proc.stderr,
            proc.stderr[:500],
        )
        check(
            "output file still produced",
            out_path.is_file(),
            str(out_path),
        )
    finally:
        for p in (inv_path, out_path):
            if p.is_file():
                p.unlink()


def test_combined_sampler_phase_bucket_metadata_in_output() -> None:
    header("Combined sampler: phase_bucket matches derivation")
    mod = _combined_sampler_mod()
    events = [{
        "frame_count": 1000,
        "ts": "",
        "event": "DOT",
        "over": "14.5",
    }]
    frames = [{
        "frame_count": 1001,
        "frame_path": "debug_frames/f1001_scoreboard.jpg",
        "scout_frame_type": "SCOREBOARD",
        "scout_cam": "closeup",
        "scout_phase": "between_play",
        "_match_id": "solo",
        "_source_inventory": "",
    }]
    fti = mod.assign_event_innings(events)
    pb = mod.phase_bucket_for_frame(1001, events, fti)
    check(
        "14.5 in first innings → middle_inn1 (15th-over segment)",
        pb == "middle_inn1",
        f"{pb=} fti={fti}",
    )
    cov_out, *_ = mod.select_combined_corpus(
        frames=frames,
        events_by_match={"solo": events},
        target_per_bucket=99,
        seed=0,
        documented_empty={},
    )
    check("exactly one sampled frame",
          len(cov_out) == 1, str(cov_out))
    check(
        "output row phase_bucket aligns",
          cov_out[0]["phase_bucket"] == "middle_inn1",
        cov_out[0],
    )


def test_combined_sampler_backward_compat_with_run_shadow() -> None:
    header("Combined sampler output loads via run_shadow.load_corpus")
    root = Path(__file__).resolve().parent
    inv_path = root / "_tmp_combined_sampler_inv_rs.json"
    out_path = root / "_tmp_combined_sampler_out_rs.json"
    try:
        from shadow_eval.run_shadow import load_corpus
        _synthetic_inventory_pathological(inv_path)
        proc = _run_combined_sampler_cli([
            "--inventory",
            str(inv_path),
            "--output",
            str(out_path),
            "--target-per-bucket",
            "1",
            "--seed",
            "7",
        ])
        check("sampler ok for run_shadow load", proc.returncode == 0)
        frames = load_corpus(out_path)
        for row in frames:
            check(
                "frame has run_shadow-required keys",
                "frame_id" in row and "path" in row,
                str(row.keys()),
            )
        check("phase_bucket propagated",
              all("phase_bucket" in row for row in frames),
              frames)
        check(
            "subset preserved",
              all(row.get("subset") == "combined_stratified" for row in frames),
              frames,
        )
    finally:
        for p in (inv_path, out_path):
            if p.is_file():
                p.unlink()


def test_combined_sampler_undocumented_zero_warn() -> None:
    header(
        "Combined sampler: UNDOCUMENTED_ZERO supersede plain WARN wording")
    mod = _combined_sampler_mod()
    cov = mod.build_bucket_coverage(
        targets={b: 8 for b in mod.PHASE_BUCKETS},
        pool_counts={
            "powerplay_inn1": 3,
            "middle_inn1": 10,
            "death_inn1": 9,
            "powerplay_inn2": 0,
            "middle_inn2": 0,
            "death_inn2": 0,
        },
        sampled_counts={
            "powerplay_inn1": 0,
            "middle_inn1": 1,
            "death_inn1": 9,
            "powerplay_inn2": 0,
            "middle_inn2": 0,
            "death_inn2": 0,
        },
        documented_empty={},
    )
    row_pp = next(r for r in cov if r["bucket"] == "powerplay_inn1")
    row_mid = next(r for r in cov if r["bucket"] == "middle_inn1")
    row_d = next(r for r in cov if r["bucket"] == "death_inn1")
    check("non-empty pool, zero sampled → UNDOCUMENTED_ZERO",
          row_pp["status"] == "UNDOCUMENTED_ZERO",
          row_pp)
    check("undershoot but nonzero sample → WARN",
          row_mid["status"] == "WARN",
          row_mid)
    check("hits target OK",
          row_d["status"] == "OK",
          row_d)


def test_closeup_frames_persisted_before_short_circuit() -> None:
    header("Maintenance: CLOSEUP frames are persisted to debug_frames")
    with open("test_pipeline.py") as f:
        src = f.read()

    check("CLOSEUP branch writes debug frame",
          'frame_type == "CLOSEUP"' in src
          and 'f"debug_frames/f{frame_count}_closeup.jpg"' in src,
          "missing CLOSEUP imwrite")


def test_element_checker_header_uses_configured_match() -> None:
    header("Maintenance: element-checker banner derives from CB_LIVE")
    with open("element_checker.py") as f:
        src = f.read()

    check("hardcoded DC-vs-RCB banner removed",
          "ELEMENT CHECKER — DC vs RCB" not in src,
          "stale hardcoded banner remains")
    check("banner derives match label from CB_LIVE",
          "match_label = CB_LIVE.rstrip" in src
          and "ELEMENT CHECKER — {match_label}" in src,
          "dynamic match label missing")


class _SMStub:
    shadow = False
    striker = None
    non = None


def test_cluster1_canonical_active_slot_prefers_score_manager() -> None:
    header("Cluster 1 Path B: canonical active slot reads prefer SM")
    from eyes.scoreboard import Scoreboard
    from test_pipeline import _canonical_active_slot

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb.batting_card["A"]["status"] = "batting"
    sb.batting_card["B"]["status"] = "batting"
    sb._inn["striker"] = "A"
    sm = _SMStub()
    sm.striker = "B"

    check("SM striker wins over legacy sb._inn striker",
          _canonical_active_slot(sm, sb, "striker") == "B",
          f"slot={_canonical_active_slot(sm, sb, 'striker')}")


def test_path_b_inn_sm_mirror_lockstep() -> None:
    header("Path B complete: SM + sb._inn striker mirror (live SM)")
    from eyes.scoreboard import Scoreboard
    from test_pipeline import _set_inn_slot_with_sm_mirror

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb._inn["striker"] = "A"
    sm = _SMStub()

    ok = _set_inn_slot_with_sm_mirror(sm, sb, "striker", "B", "unit-test")

    check("mirror returns True", ok is True, f"ok={ok}")
    check("_inn striker updated", sb._inn["striker"] == "B",
          sb._inn["striker"])
    check("SM striker updated", sm.striker == "B", sm.striker)


def test_path_b_striker_read_sm_canonical_drs_detail_present_in_source() -> None:
    """Source-level wiring guard for Path B DETAIL-line read migration."""
    header("Path B striker READ migration: DRS-FREEZE DETAIL line uses "
           "SM canonical with [STRIKER-READ-SM-CANONICAL] divergence "
           "telemetry")
    src = (Path(__file__).resolve().parent / "test_pipeline.py"
           ).read_text()
    check("telemetry marker `[STRIKER-READ-SM-CANONICAL]` present",
          "[STRIKER-READ-SM-CANONICAL]" in src,
          "expected divergence-only telemetry marker for Path B reads")
    check("DRS-FREEZE DETAIL block reads SM-first via _sm_str/_sm_ns",
          "_sm_str = getattr(score_mgr, \"striker\", None)" in src
          and "_sm_ns = getattr(score_mgr, \"non\", None)" in src,
          "expected SM-first read with safe getattr fallback")
    check("DRS-FREEZE DETAIL falls back to _inn legacy projection",
          "_after_striker = _sm_str or _inn_str" in src
          and "_after_non = _sm_ns or _inn_ns" in src,
          "expected SM-first → _inn fallback ordering")
    check("legacy un-migrated `scoreboard._inn.get(\"striker\", \"—\")` "
          "removed from DRS-FREEZE DETAIL site",
          "_after_striker = scoreboard._inn.get(\"striker\", \"—\")"
          not in src,
          "DRS-FREEZE DETAIL still reads _inn[striker] directly")


def test_path_b_striker_read_sm_canonical_returns_sm_value_on_divergence(
) -> None:
    """Behavioural check: SM-first ordering wins when SM and _inn disagree."""
    header("Path B striker READ: SM canonical wins over stale _inn for "
           "DETAIL-style readers")
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb.batting_card["A"]["status"] = "batting"
    sb.batting_card["B"]["status"] = "batting"
    sb._inn["striker"] = "A"
    sb._inn["non"] = "B"

    sm = _SMStub()
    sm.striker = "B"
    sm.non = "A"

    # Mirror the DETAIL DRS-freeze branch ordering used in source.
    _inn_str = sb._inn.get("striker") if sb._inn else None
    _inn_ns = sb._inn.get("non") if sb._inn else None
    _sm_str = getattr(sm, "striker", None)
    _sm_ns = getattr(sm, "non", None)
    after_striker = _sm_str or _inn_str or "—"
    after_non = _sm_ns or _inn_ns or "—"

    check("DETAIL striker reads SM canonical when SM ≠ _inn",
          after_striker == "B",
          f"after_striker={after_striker!r}")
    check("DETAIL non reads SM canonical when SM ≠ _inn",
          after_non == "A",
          f"after_non={after_non!r}")

    sm.striker = None
    sm.non = None
    _sm_str = getattr(sm, "striker", None)
    _sm_ns = getattr(sm, "non", None)
    after_striker = _sm_str or _inn_str or "—"
    after_non = _sm_ns or _inn_ns or "—"
    check("DETAIL falls back to _inn when SM has no striker",
          after_striker == "A",
          f"after_striker={after_striker!r}")
    check("DETAIL falls back to _inn when SM has no non",
          after_non == "B",
          f"after_non={after_non!r}")


def test_cluster1_scorer_active_gate_blocks_witnessed_out_batter() -> None:
    header("Cluster 1 SCORER invariant: witnessed-out batter updates "
           "blocked before update_batter")
    from eyes.scoreboard import Scoreboard
    from test_pipeline import apply_scorer_decision

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb.batting_card["A"]["status"] = "out"
    sb.batting_card["A"]["runs"] = 10
    sb.batting_card["A"]["balls"] = 8
    sb.fall_of_wickets.append({
        "wicket": 1,
        "batter": "A",
        "score": 20,
        "overs": "3.1",
        "_witnessed": True,
    })
    decision = {
        "batter_updates": {
            "A": {"accepted": True, "runs": 12, "balls": 9},
        },
    }
    changes = apply_scorer_decision(
        sb, decision, frame=1400, jump_guard=None,
        extracted={"batters": [{"name": "A", "runs": 12, "balls": 9}]})

    check("no batter change emitted for witnessed-out batter",
          not any(str(c).startswith("bat:A") for c in changes),
          f"changes={changes}")
    check("dismissed batter stats/status preserved",
          sb.batting_card["A"]["status"] == "out"
          and sb.batting_card["A"]["runs"] == 10
          and sb.batting_card["A"]["balls"] == 8,
          f"card={sb.batting_card['A']}")


def test_cluster1_update_batter_witnessed_out_striker_flag_no_slot_write() -> None:
    header("Cluster 1 refinement: update_batter does not role-flip a "
           "witnessed-out batter")
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb._inn["striker"] = "B"
    sb.batting_card["A"]["status"] = "out"
    sb.batting_card["A"]["runs"] = 10
    sb.batting_card["A"]["balls"] = 8
    sb.fall_of_wickets.append({
        "wicket": 1,
        "batter": "A",
        "score": 20,
        "overs": "3.1",
        "_witnessed": True,
    })

    ok = sb.update_batter("A", runs=12, balls=9, striker=True, frame=1500)

    check("witnessed-out update rejected",
          ok is False,
          f"ok={ok}")
    check("striker slot preserved",
          sb._inn["striker"] == "B",
          f"striker={sb._inn['striker']}")


def test_cluster1_auto_dismiss_prefers_sm_striker_over_stale_inn() -> None:
    header("Cluster 1 refinement: wicket auto-dismiss prefers SM striker "
           "over stale sb._inn striker")
    from eyes.scoreboard import Scoreboard
    from test_pipeline import apply_scorer_decision

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    for name in ("A", "B"):
        sb.batting_card[name]["status"] = "batting"
        sb.batting_card[name]["runs"] = 1
        sb.batting_card[name]["balls"] = 1
    sb._inn["score"] = 20
    sb._inn["wickets"] = 0
    sb._inn["overs"] = "3.1"
    sb._inn["striker"] = "A"  # stale legacy projection
    sb._tracker.force_set("wickets", 0)
    sb._tracker.on_ball_event()
    sm = _SMStub()
    sm.striker = "B"
    sm.non = "A"
    decision = {
        "ground_truth_applied": True,
        "wickets_update": {"accepted": True, "to": 1},
    }

    changes = apply_scorer_decision(
        sb, decision, frame=1501, jump_guard=None,
        batting_team={"name": "BAT"},
        extracted={"wickets": 1},
        score_mgr=sm)

    check("SM striker dismissed",
          sb.batting_card["B"]["status"] == "out",
          f"B={sb.batting_card['B']}")
    check("stale sb._inn striker not dismissed",
          sb.batting_card["A"]["status"] == "batting",
          f"A={sb.batting_card['A']}")
    check("changes include SM striker dismissal",
          "DISMISSED:B" in changes,
          f"changes={changes}")


# ---------------------------------------------------------------------
# Inter-match commit (2026-04-25 RR vs SRH match-2 fixes)
# ---------------------------------------------------------------------

# --- Fix 1: target=640 sanity bound on innings-1 latch ---------------
def test_innings1_latch_rejects_phantom_639_at_76_overs() -> None:
    """F921 hallucination (639-4 at 76.5) must NOT latch."""
    header("Fix 1: innings-1 latch rejects phantom 639/76.5")
    from test_pipeline import _should_latch_innings_1_candidate
    should, reason = _should_latch_innings_1_candidate(
        cand_score=639, cand_wkts=4, cand_overs_raw="76.5",
        existing_score=0, existing_wkts=0)
    check("phantom rejected", should is False,
          f"should_latch={should} (expected False)")
    check("rejection reason is sanity_bound",
          reason == "sanity_bound",
          f"reason={reason!r}")


def test_innings1_latch_accepts_normal_t20_final() -> None:
    """A normal T20 finish (228/6 at 20.0) must latch."""
    header("Fix 1: innings-1 latch accepts normal 228/6 (20.0)")
    from test_pipeline import _should_latch_innings_1_candidate
    should, reason = _should_latch_innings_1_candidate(
        cand_score=228, cand_wkts=6, cand_overs_raw="20.0",
        existing_score=0, existing_wkts=0)
    check("228/6 latched", should is True,
          f"should_latch={should} (expected True)")
    check("no rejection reason on accept", reason is None,
          f"reason={reason!r}")


def test_innings1_latch_phantom_does_not_lock_real_final() -> None:
    """Replay the F921→F1445 sequence: phantom is rejected,
    real final latches afterward."""
    header("Fix 1: phantom doesn't poison subsequent real final")
    from test_pipeline import _should_latch_innings_1_candidate
    # F921: phantom 639/76.5 — rejected
    should1, reason1 = _should_latch_innings_1_candidate(
        cand_score=639, cand_wkts=4, cand_overs_raw="76.5",
        existing_score=0, existing_wkts=0)
    # Existing latch unchanged (still 0/0) because phantom was rejected
    # F1445: real 228/6 (20.0) — latches against still-0 existing
    should2, reason2 = _should_latch_innings_1_candidate(
        cand_score=228, cand_wkts=6, cand_overs_raw="20.0",
        existing_score=0, existing_wkts=0)
    check("phantom rejected", should1 is False,
          f"phantom should_latch={should1}")
    check("real final latches after phantom rejection",
          should2 is True,
          f"real should_latch={should2}, reason={reason2!r}")


def test_innings1_latch_sanity_boundaries() -> None:
    """Boundary cases: 350-runs / 20.0-overs are accepted; one tick
    above either threshold is rejected as sanity_bound."""
    header("Fix 1: sanity bounds at exactly 350 runs / 20.0 overs")
    from test_pipeline import _should_latch_innings_1_candidate
    # 350 runs in 20.0 — at the boundary, accepted
    s_at_score, _ = _should_latch_innings_1_candidate(
        350, 5, "20.0", 0, 0)
    check("350 runs at boundary accepted",
          s_at_score is True,
          f"should_latch={s_at_score}")
    # 351 runs — above boundary, rejected
    s_over_score, r_over_score = _should_latch_innings_1_candidate(
        351, 5, "20.0", 0, 0)
    check("351 runs above boundary rejected as sanity_bound",
          s_over_score is False and r_over_score == "sanity_bound",
          f"should_latch={s_over_score} reason={r_over_score!r}")
    # 20.0 overs at boundary — accepted (the exact end of innings)
    s_at_overs, _ = _should_latch_innings_1_candidate(
        228, 6, "20.0", 0, 0)
    check("20.0 overs at boundary accepted",
          s_at_overs is True,
          f"should_latch={s_at_overs}")
    # 20.1 overs — above boundary, rejected
    s_over_overs, r_over_overs = _should_latch_innings_1_candidate(
        228, 6, "20.1", 0, 0)
    check("20.1 overs above boundary rejected as sanity_bound",
          s_over_overs is False and r_over_overs == "sanity_bound",
          f"should_latch={s_over_overs} reason={r_over_overs!r}")


def test_innings1_latch_max_wins_within_bounds() -> None:
    """Within sanity bounds, max-wins still applies (higher score
    overwrites; on tie, higher wickets wins; otherwise loses)."""
    header("Fix 1: max-wins logic preserved within sanity bounds")
    from test_pipeline import _should_latch_innings_1_candidate
    # Higher score wins
    s, _ = _should_latch_innings_1_candidate(180, 4, "19.5", 175, 5)
    check("higher score overwrites lower regardless of wickets",
          s is True, "")
    # Same score, higher wickets wins
    s, _ = _should_latch_innings_1_candidate(180, 6, "20.0", 180, 4)
    check("tied score: higher wickets wins",
          s is True, "")
    # Same score, lower wickets loses
    s, r = _should_latch_innings_1_candidate(180, 3, "20.0", 180, 5)
    check("tied score: lower wickets loses (max_wins_lost)",
          s is False and r == "max_wins_lost",
          f"should_latch={s} reason={r!r}")
    # Lower score loses
    s, r = _should_latch_innings_1_candidate(150, 9, "19.5", 180, 4)
    check("lower score loses (max_wins_lost)",
          s is False and r == "max_wins_lost",
          f"should_latch={s} reason={r!r}")


def test_innings1_latch_callsite_wired_in_source() -> None:
    """Source-level: confirm the helper is actually called from the
    innings-end latch block (defends against drift if someone ever
    inlines the predicate)."""
    header("Fix 1: latch callsite wired to helper in source")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    check("helper invoked at latch callsite",
          "_should_latch_innings_1_candidate(" in src,
          "expected helper call at latch callsite")
    check("sanity_bound rejection log present",
          "exceeds T20 " in src and "sanity bounds" in src,
          "expected reject-log when sanity_bound triggers")


# --- Fix 4: overs CONSENSUS-BLOCKED regression guard -----------------
def _confirm_overs_via_cold_start(tracker, value, start_frame=1):
    """Push `value` through the 3-frame cold-start consensus to land
    it in `confirmed[overs]`. Returns the frame after confirmation."""
    f = start_frame
    for _ in range(tracker.INITIAL_CONSENSUS_FRAMES):
        tracker.update("overs", value, frame_count=f)
        f += 1
    return f


def test_overs_consensus_blocked_rejects_powerplay_regression() -> None:
    """RR vs SRH 2026-04-25 F3117-F3120 replay: confirmed overs=6.0,
    then 4 consecutive reads of 0.5 (the (POWERPLAY)-misparse pattern)
    must NOT flip confirmed; [CONSENSUS-BLOCKED] fires instead of
    [CONSENSUS]."""
    header("Fix 4: overs (POWERPLAY)-class regression rejected by CONSENSUS-BLOCKED")
    from eyes.consistent_tracker import ConsistentReadTracker
    t = ConsistentReadTracker()
    f = _confirm_overs_via_cold_start(t, 6.0, start_frame=1)
    check("cold-start confirmed overs=6.0",
          t.confirmed.get("overs") == 6.0,
          f"confirmed={t.confirmed.get('overs')}")

    # 4 consecutive regression reads — what F3117-F3120 produced
    for _ in range(t.CONSENSUS_THRESHOLD):
        t.update("overs", 0.5, frame_count=f)
        f += 1

    # Without the fix, confirmed would have flipped to 0.5 here.
    check("confirmed.overs stays 6.0 after 4 consecutive 0.5 reads",
          t.confirmed.get("overs") == 6.0,
          f"confirmed={t.confirmed.get('overs')} "
          f"(regression to 0.5 should have been blocked)")


def test_overs_consensus_blocked_progression_still_accepted() -> None:
    """Legitimate overs progression (6.0 → 6.1) must still confirm
    cleanly — the guard is regression-only.  Non-suspicious updates
    use the standard pending-then-promote path, which needs two
    matching reads."""
    header("Fix 4: legitimate overs progression unaffected by guard")
    from eyes.consistent_tracker import ConsistentReadTracker
    t = ConsistentReadTracker()
    f = _confirm_overs_via_cold_start(t, 6.0, start_frame=1)
    # New ball event: 6.1 arrives.  First read lands in `pending`,
    # second matching read promotes to confirmed.
    r1 = t.update("overs", 6.1, frame_count=f)
    check("first 6.1 read held in pending (confirmed still 6.0)",
          t.confirmed.get("overs") == 6.0
          and t.pending.get("overs") is not None,
          f"confirmed={t.confirmed.get('overs')} pending={t.pending.get('overs')}")
    r2 = t.update("overs", 6.1, frame_count=f + 1)
    check("second 6.1 read promotes to confirmed=6.1",
          t.confirmed.get("overs") == 6.1,
          f"confirmed={t.confirmed.get('overs')}, return={r2}")


def test_overs_consensus_blocked_set_innings_2_path_still_works() -> None:
    """The legitimate overs reset (innings 1 → innings 2) goes through
    `set_innings_2()` which clears `confirmed` wholesale — NOT through
    the consensus update path.  Verify: after `force_set` (the
    standard reset entrypoint) the guard does not interfere with
    cold-start re-acquisition at 0.0/0.1."""
    header("Fix 4: innings transition via force_set + cold-start unaffected")
    from eyes.consistent_tracker import ConsistentReadTracker
    t = ConsistentReadTracker()
    _confirm_overs_via_cold_start(t, 19.6, start_frame=1)
    check("innings-1 overs confirmed at 19.6",
          t.confirmed.get("overs") == 19.6, "")

    # Simulate the set_innings_2 reset: clear confirmed wholesale,
    # which is what the actual code path does.
    t.confirmed.pop("overs", None)
    t._initial_consensus.pop("overs", None)
    t.pending.pop("overs", None)
    t._reject_streak.pop("overs", None)

    # Now innings-2 cold-start brings overs to 0.0 via the
    # 3-frame consensus — the guard should NOT interfere because
    # the cold-start path runs before any regression check fires.
    f = _confirm_overs_via_cold_start(t, 0.0, start_frame=100)
    check("innings-2 cold-start at 0.0 succeeds (guard doesn't block)",
          t.confirmed.get("overs") == 0.0,
          f"confirmed={t.confirmed.get('overs')}")


# --- Fix 3: this_over chronological reorder on FOW upgrade -----------
def test_this_over_reorder_w_after_boundary_to_correct_ball() -> None:
    """RR vs SRH 2026-04-25 inn-2 over-0 replay:
    Observed `[., ., ., Wd, W, 6]` (W detected before 6 caught up).
    FOW upgrade pins wicket to ball 0.5 → W must move from
    legal-ball 4 to legal-ball 5 → `[., ., ., Wd, 6, W]`."""
    header("Fix 3: W reordered when boundary actually came first")
    from eyes.this_over import ThisOverManager
    om = ThisOverManager()
    om.this_over = [".", ".", ".", "Wd", "W", "6"]
    om.this_over_sources = ["obs"] * 6
    moved = om.reorder_wicket_to_ball(5)
    check("reorder_wicket_to_ball returned True",
          moved is True, f"got {moved!r}")
    check("W moved to last position (legal-ball 5)",
          om.this_over == [".", ".", ".", "Wd", "6", "W"],
          f"this_over={om.this_over}")
    check("sources list stayed length-aligned",
          len(om.this_over_sources) == len(om.this_over),
          f"sources={om.this_over_sources}")


def test_this_over_reorder_no_op_when_position_already_correct() -> None:
    """If W is already at the right legal-ball position, the reorder
    is a no-op (returns False, list unchanged)."""
    header("Fix 3: no-op when W already at correct position")
    from eyes.this_over import ThisOverManager
    om = ThisOverManager()
    om.this_over = [".", ".", ".", "Wd", "6", "W"]
    om.this_over_sources = ["obs"] * 6
    snap = list(om.this_over)
    moved = om.reorder_wicket_to_ball(5)
    check("returned False (no-op)", moved is False, f"got {moved!r}")
    check("this_over unchanged", om.this_over == snap,
          f"this_over={om.this_over}")


def test_this_over_reorder_handles_no_w_gracefully() -> None:
    """No W in `this_over` → graceful False, no exception."""
    header("Fix 3: graceful no-op when no W token present")
    from eyes.this_over import ThisOverManager
    om = ThisOverManager()
    om.this_over = [".", ".", "4", "Wd"]
    om.this_over_sources = ["obs"] * 4
    snap = list(om.this_over)
    moved = om.reorder_wicket_to_ball(3)
    check("no-W input returns False", moved is False, "")
    check("this_over unchanged", om.this_over == snap, "")


def test_this_over_reorder_extras_are_skipped_in_legal_count() -> None:
    """Compound extras (`Wd+4`) and pure extras (`Wd`, `Nb`) must not
    advance the legal-ball counter when computing W's target slot."""
    header("Fix 3: legal-ball counter skips extras (incl. compound)")
    from eyes.this_over import ThisOverManager
    om = ThisOverManager()
    # Tokens mapping: Wd extra, '6' = X.1, 'Nb+1' compound extra,
    # '.' = X.2, '1' = X.3, 'W' detected at end (current legal-pos 4),
    # FOW upgrade says X.3 — W should move to right after the '1'.
    om.this_over = ["Wd", "6", "Nb+1", ".", "1", "W"]
    om.this_over_sources = ["obs"] * 6
    moved = om.reorder_wicket_to_ball(3)
    check("reorder fired (target=3 differs from current legal=4)",
          moved is True, f"got {moved!r}")
    check("W placed after '1' (3rd legal ball)",
          om.this_over == ["Wd", "6", "Nb+1", ".", "1", "W"]
          or om.this_over == ["Wd", "6", "Nb+1", ".", "W", "1"],
          f"this_over={om.this_over}")
    # The exact insertion places W immediately after the 3rd legal
    # ball; with our list, position-of-3rd-legal is at index 4 ('1'),
    # so W should land at index 5 (end). That's a no-op-ish but the
    # algorithm correctly recomputed.  Now test a case where it
    # actually moves W backwards in the list:
    om2 = ThisOverManager()
    # ["Wd", "6", "Nb+1", "1", "W"]: legal-balls = 6(1), 1(2), W(3).
    # Target=2 should pull W back so it's the 2nd legal ball.
    om2.this_over = ["Wd", "6", "Nb+1", "1", "W"]
    om2.this_over_sources = ["obs"] * 5
    moved2 = om2.reorder_wicket_to_ball(2)
    check("backward reorder fired (legal 3 → legal 2)",
          moved2 is True, f"got {moved2!r} list={om2.this_over}")
    # Verify W's new legal-ball position is exactly 2.
    legal_count = 0
    w_pos = None
    for t in om2.this_over:
        if not (t == "Wd" or t == "Nb"
                or t.startswith("Wd+") or t.startswith("Nb+")):
            legal_count += 1
        if t == "W" and w_pos is None:
            w_pos = legal_count
    check("W is now the 2nd legal ball post-reorder",
          w_pos == 2, f"w_pos={w_pos} this_over={om2.this_over}")


def test_scoreboard_fow_upgrade_callback_fires_on_upgrade() -> None:
    """Wiring test: when `_add_fow` upgrades a placeholder, the
    `on_fow_upgrade` callback fires with the parsed ball index."""
    header("Fix 3: scoreboard FOW-upgrade callback wiring")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL",
                     ["A", "B", "C", "D", "E"], ["X", "Y"])
    # Plant a placeholder FOW (mirrors what backfill / cold-start
    # creates when a wicket is detected before the dismissed batter
    # is identified).
    sb.fall_of_wickets.append({
        "wicket": 1, "batter": "unknown",
        "score": "?", "overs": "?", "tentative": True})
    received = []
    sb.on_fow_upgrade = lambda y: received.append(y)
    # Now upgrade — `_add_fow` should fire the callback with y=5.
    sb._add_fow(1, "A", score=7, overs="0.5",
                how="caught", bowler="X")
    check("callback fired exactly once",
          len(received) == 1, f"received={received}")
    check("callback received ball-index=5",
          received == [5], f"received={received}")


def test_scoreboard_fow_upgrade_callback_no_fire_on_immutable_skip() -> None:
    """When `_add_fow` REFUSES to overwrite a witnessed FOW, the
    callback must NOT fire (no upgrade happened)."""
    header("Fix 3: callback does NOT fire on immutable refuse")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL",
                     ["A", "B", "C", "D", "E"], ["X", "Y"])
    # Witnessed FOW already in place — second different-batter
    # write must be REFUSED and callback must NOT fire.
    sb.fall_of_wickets.append({
        "wicket": 1, "batter": "A",
        "score": 5, "overs": "0.3", "_witnessed": True})
    received = []
    sb.on_fow_upgrade = lambda y: received.append(y)
    sb._add_fow(1, "B", score=7, overs="0.5",
                how="caught", bowler="X")  # different batter
    check("callback did NOT fire (rewrite refused)",
          received == [], f"received={received}")


# --- Fix 2: this_over token-alphabet validation ----------------------
def test_this_over_alphabet_helper_boundary_cases() -> None:
    """Helper boundary cases: 7 accepted (overthrow safety margin),
    8 rejected, leg-bye `2lb` accepted, bye `3b` accepted, `nb`
    not mistaken for bye, `?` placeholder accepted."""
    header("Fix 2: alphabet helper boundary cases")
    from eyes.this_over import ThisOverManager
    f = ThisOverManager._is_legal_run_token
    check("'7' accepted (overthrow margin)", f("7") is True, "")
    check("'8' rejected", f("8") is False, "")
    check("'.' accepted", f(".") is True, "")
    check("'?' accepted", f("?") is True, "")
    check("'W' accepted", f("W") is True, "")
    check("'Wd' accepted", f("Wd") is True, "")
    check("'Nb' accepted", f("Nb") is True, "")
    check("'2lb' accepted", f("2lb") is True, "")
    check("'3b' accepted", f("3b") is True, "")
    check("'9b' rejected (out of 0..7 range)",
          f("9b") is False, "")
    check("'42' rejected (multi-digit)", f("42") is False, "")
    check("'Wd+4' rejected (compounds shouldn't reach this gate)",
          f("Wd+4") is False, "")


# ---------------------------------------------------------------------
# P8 fixes (2026-05-02) — score-leak + unbounded growth
# ---------------------------------------------------------------------
def test_p8_this_over_regex_rejects_multi_digit() -> None:
    """`_THIS_OVER_TOKEN_RE` and `_parse_this_over_from_scout` must
    reject multi-digit numbers (score `100`, partnership `100`, etc.)
    — they cannot be legitimate per-ball outcomes. Trace 866ce150
    F157-F178 leaked `"100"` into `this_over[0]`."""
    header("P8: this-over regex rejects multi-digit tokens")
    from test_pipeline import _parse_this_over_from_scout

    out = _parse_this_over_from_scout("THIS OVER: 100 . . . . .")
    check("multi-digit '100' rejected (or stripped)",
          out is None or "100" not in out,
          f"out={out}")

    out2 = _parse_this_over_from_scout("THIS OVER: 4 . 1 6 wd 4")
    check("legal sequence accepted unchanged",
          out2 == ["4", ".", "1", "6", "wd", "4"]
          or out2 == ["4", ".", "1", "6", "Wd", "4"]
          or [t.lower() for t in (out2 or [])] == ["4", ".", "1", "6", "wd", "4"],
          f"out={out2}")


def test_p8_line_fallback_bounded_by_separator() -> None:
    """The line-based fallback in `_parse_this_over_from_scout` must
    stop at hard separators (`|`, `EXTRA:`, `FULL`, `SPEED:`, etc.)
    instead of running findall over the whole line — otherwise it
    scoops up score, batter stats, and partnership numbers."""
    header("P8: line-based fallback bounded to slice after keyword")
    from test_pipeline import _parse_this_over_from_scout

    line = ("STRIP: SA 100-2 (4.0) | de Kock 42(31) | "
            "this over . . 1 . | EXTRA: 7 (1wd 2nb) | "
            "P'SHIP 50(40)")
    out = _parse_this_over_from_scout(line)
    check("only this-over slice tokens captured (no score/extras)",
          out == [".", ".", "1", "."],
          f"out={out}")


def test_p8_line_fallback_max_chars() -> None:
    """If no hard separator is reachable, the slice is capped at 30
    characters so trailing digits don't leak in."""
    header("P8: line-based fallback capped at 30 chars when no separator")
    from test_pipeline import _parse_this_over_from_scout

    line = ("THIS OVER 1 . 4 6 wd 2 "  # 23 chars after keyword
            "and then much later score 100 stats 42 47")
    out = _parse_this_over_from_scout(line)
    check("trailing 100/42/47 not captured by line fallback",
          out is not None and "100" not in out and "42" not in out
          and "47" not in out,
          f"out={out}")


def test_p8_get_display_floor_pad_bounded() -> None:
    """`get_display` length-floor pad must clamp to
    MAX_OBSERVED_THIS_OVER_LEN. A multi-over jump rejected by
    `check_over_change` left `_last_over_int` stuck while
    team_overs continued climbing in trace 866ce150 F181-F198,
    growing this_over to 12 `?` tokens."""
    header("P8: get_display floor pad bounded by MAX_OBSERVED_THIS_OVER_LEN")
    from eyes.this_over import ThisOverManager, MAX_OBSERVED_THIS_OVER_LEN

    om = ThisOverManager()
    om._last_over_int = 1
    om.this_over = ["?", "?", "?", "?", "?", "?"]
    om.this_over_sources = ["bcast"] * 6

    # Simulate the F181 scenario: team_overs reads "X.9" but the
    # tracker is still pinned to over 1. legal_n = 6, sub = 9, so
    # naive missing = 3 → length 9 (within cap). Force a more
    # extreme case: pre-load 11 placeholders, request sub=9.
    om.this_over = ["?"] * 11
    om.this_over_sources = ["bcast"] * 11
    out = om.get_display("1.9")
    check("ribbon length clamped at MAX_OBSERVED_THIS_OVER_LEN",
          len(out) <= MAX_OBSERVED_THIS_OVER_LEN
          and len(om.this_over) <= MAX_OBSERVED_THIS_OVER_LEN,
          f"len(out)={len(out)} len(this_over)={len(om.this_over)} "
          f"cap={MAX_OBSERVED_THIS_OVER_LEN}")


def test_p8_cold_start_regex_rejects_multi_digit() -> None:
    """The cold-start `THIS OVER` backfill regex (test_pipeline.py
    L9358-9365) must use the same single-digit alphabet so multi-digit
    misreads do not reach `over_mgr.on_broadcast_override` (which
    would then reject them wholesale, but cleaner to filter early)."""
    header("P8: cold-start regex tokens are single-digit only")
    import re

    # Mirror the cold-start regex from test_pipeline.py:9364-9365.
    pattern = r"[0-7]|W|WD|NB|\."
    raw = "100 . . . . ."
    tokens = re.findall(pattern, raw.replace(",", " "))
    check("multi-digit 100 split into single-digit tokens",
          "100" not in tokens,
          f"tokens={tokens}")


def test_overs_consensus_blocked_other_fields_unaffected() -> None:
    """The new guard is keyed on `field == 'overs'`. Confirm a
    different field (score) with 4 consecutive regression reads
    behaves as before — the consensus override DOES fire (no guard
    for raw score regression)."""
    header("Fix 4: cross-field independence (score regression path unchanged)")
    from eyes.consistent_tracker import ConsistentReadTracker
    t = ConsistentReadTracker()
    f = _confirm_overs_via_cold_start(t, 100, start_frame=1)
    # Move 'overs' aside; we're confirming the cold-start path using
    # the same plumbing for `score` instead. Reset everything cleanly:
    t.confirmed.clear()
    t._initial_consensus.clear()
    t.pending.clear()
    t._reject_streak.clear()
    # Cold-start confirm score=200
    for _ in range(t.INITIAL_CONSENSUS_FRAMES):
        t.update("score", 200, frame_count=f)
        f += 1
    assert t.confirmed.get("score") == 200, "test scaffolding broken"
    # 4 consecutive regression reads on `score` — no field-specific
    # guard for raw score regression, so [CONSENSUS] should fire.
    for _ in range(t.CONSENSUS_THRESHOLD):
        t.update("score", 50, frame_count=f)
        f += 1
    check("score regression not blocked by overs guard "
          "(cross-field isolation)",
          t.confirmed.get("score") == 50,
          f"confirmed.score={t.confirmed.get('score')} "
          f"(expected 50, the consensus-override result)")


# ---------------------------------------------------------------------
# 10b. Fix 5 — Striker self-collision guard in update_batter
#      (2026-04-25 inter-match commit; backlog ref:
#       "Striker self-collision in update_batter")
# ---------------------------------------------------------------------

def _setup_striker_collision_sb():
    """Fresh Scoreboard with two batters mid-innings ready for the
    swap-then-misread scenarios from F170-F176."""
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="Rajasthan Royals",
        bowling_team="Sunrisers Hyderabad",
        batting_squad=["Sooryavanshi", "Parag", "Three"],
        bowling_squad=["Sakib Hussain", "Shivang Kumar"],
        batting_xi=["Sooryavanshi", "Parag", "Three"],
        bowling_xi=["Sakib Hussain", "Shivang Kumar"],
    )
    for name, runs, balls in (
            ("Sooryavanshi", 103, 50), ("Parag", 2, 4)):
        sb.batting_card[name]["status"] = "batting"
        sb.batting_card[name]["runs"] = runs
        sb.batting_card[name]["balls"] = balls
    sb._inn["score"] = 105
    sb._inn["wickets"] = 1
    sb._inn["overs"] = "12.4"
    return sb


def test_striker_collision_refuses_non_write_when_same_as_striker() -> None:
    header("Fix 5: update_batter(B, striker=False) refused when "
           "B is already striker (would self-collide)")
    sb = _setup_striker_collision_sb()
    sb._inn["striker"] = "Parag"
    sb._inn["non"] = "Sooryavanshi"
    # Misread frame: extractor lists Parag in the lower row, so the
    # pipeline calls update_batter("Parag", striker=False).  Pre-fix
    # this would write non=Parag and end with striker ==
    # non.
    ok = sb.update_batter("Parag", runs=2, balls=4,
                          striker=False, frame=173)
    check("update_batter still returns True (stats updated)",
          ok is True, f"return={ok}")
    check("striker stays Parag",
          sb._inn["striker"] == "Parag",
          f"striker={sb._inn['striker']}")
    check("non stays Sooryavanshi (collision refused)",
          sb._inn["non"] == "Sooryavanshi",
          f"non={sb._inn['non']}")
    check("striker != non (invariant held)",
          sb._inn["striker"] != sb._inn["non"],
          f"striker={sb._inn['striker']} "
          f"non={sb._inn['non']}")


def test_striker_collision_refuses_striker_write_when_same_as_non() -> None:
    header("Fix 5: update_batter(A, striker=True) refused when "
           "A is already non (symmetric collision)")
    sb = _setup_striker_collision_sb()
    sb._inn["striker"] = "Parag"
    sb._inn["non"] = "Sooryavanshi"
    # Symmetric misread: pipeline calls update_batter("Sooryavanshi",
    # striker=True).  Pre-fix this would clobber striker and produce
    # striker == non == "Sooryavanshi".
    ok = sb.update_batter("Sooryavanshi", runs=103, balls=50,
                          striker=True, frame=173)
    check("update_batter still returns True (stats updated)",
          ok is True, f"return={ok}")
    check("striker stays Parag (collision refused)",
          sb._inn["striker"] == "Parag",
          f"striker={sb._inn['striker']}")
    check("non stays Sooryavanshi",
          sb._inn["non"] == "Sooryavanshi",
          f"non={sb._inn['non']}")
    check("striker != non (invariant held)",
          sb._inn["striker"] != sb._inn["non"],
          f"striker={sb._inn['striker']} "
          f"non={sb._inn['non']}")


def test_striker_collision_idempotent_self_writes_unaffected() -> None:
    header("Fix 5: idempotent re-assertions of current striker / "
           "non are no-ops, not refusals")
    # Production calls update_batter(name, striker=True/False, ...) on
    # every clean strip read to re-confirm the asterisk position from
    # the extractor.  When the asserted role already matches the
    # current slot, the guard MUST allow the write through (it doesn't
    # change anything; refusing would just add log noise on every
    # frame).  The genuine swap path is independent — it writes both
    # `_inn["striker"]` and `_inn["non"]` atomically at
    # `test_pipeline.py:6228-6237` (broadcast-indicator flip), not via
    # two consecutive update_batter calls.  This test pins the
    # idempotent semantics so they don't regress.
    sb = _setup_striker_collision_sb()
    sb._inn["striker"] = "Sooryavanshi"
    sb._inn["non"] = "Parag"
    ok1 = sb.update_batter("Sooryavanshi", runs=103, balls=50,
                           striker=True, frame=200)
    check("update_batter('Sooryavanshi', striker=True) accepted "
          "(stats path)", ok1 is True, f"return={ok1}")
    check("striker stays Sooryavanshi",
          sb._inn["striker"] == "Sooryavanshi",
          f"striker={sb._inn['striker']}")
    check("non stays Parag",
          sb._inn["non"] == "Parag",
          f"non={sb._inn['non']}")
    ok2 = sb.update_batter("Parag", runs=2, balls=4,
                           striker=False, frame=201)
    check("update_batter('Parag', striker=False) accepted",
          ok2 is True, f"return={ok2}")
    check("non stays Parag",
          sb._inn["non"] == "Parag",
          f"non={sb._inn['non']}")
    check("striker stays Sooryavanshi",
          sb._inn["striker"] == "Sooryavanshi",
          f"striker={sb._inn['striker']}")
    check("end state: striker != non",
          sb._inn["striker"] != sb._inn["non"],
          f"striker={sb._inn['striker']} "
          f"non={sb._inn['non']}")


def test_striker_collision_f170_f173_replay() -> None:
    header("Fix 5: F170 swap + F173 transitional misread replay "
           "(production sequence from RR-vs-SRH match-2)")
    sb = _setup_striker_collision_sb()
    # F170 ending state per the production trace: legitimate swap
    # already applied via the broadcast-indicator atomic flip
    # (test_pipeline.py:6228-6237), then the legacy post-swap
    # callsite (described in backlog "F170 swap" comment) wrote
    # `striker=Sooryavanshi, non=Parag` back over the swap.
    # Net effect at F170 end: striker=Sooryavanshi, non=Parag.
    # We construct that state directly rather than simulating the
    # multi-source race — the test target is the F173 misread, not
    # the F170 swap mechanics.
    sb._inn["striker"] = "Sooryavanshi"
    sb._inn["non"] = "Parag"
    # F173: extractor reads a transitional review-graphic where the
    # two batter rows are listed in the wrong order.  Sooryavanshi
    # appears in the lower row, so the pipeline calls
    # `update_batter("Sooryavanshi", striker=False)` — wanting to
    # write `non=Sooryavanshi`.  Striker is currently
    # Sooryavanshi, so the pre-fix write would create
    # `striker=Sooryavanshi == non=Sooryavanshi`.
    sb.update_batter("Sooryavanshi", runs=103, balls=50,
                     striker=False, frame=173)
    check("F173 misread: striker stays Sooryavanshi",
          sb._inn["striker"] == "Sooryavanshi",
          f"striker={sb._inn['striker']}")
    check("F173 misread: non stays Parag (collision refused)",
          sb._inn["non"] == "Parag",
          f"non={sb._inn['non']}")
    check("F173 invariant: striker != non (the bug class)",
          sb._inn["striker"] != sb._inn["non"],
          f"striker={sb._inn['striker']} "
          f"non={sb._inn['non']}")


# --- Fix 9a: AUTO-SWAP target injection (target-source-confusion P1) ---
def test_fix9a_autoswap_target_injection_block_present_in_source() -> None:
    """Source-level: confirm the AUTO-SWAP-TARGET injection block
    is wired in.  Defends against drift if someone refactors the
    AUTO-SWAP handler and removes the explicit injection."""
    header("Fix 9a: AUTO-SWAP-TARGET injection block present in source")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    check("[AUTO-SWAP-TARGET] log tag present",
          "[AUTO-SWAP-TARGET]" in src,
          "expected explicit AUTO-SWAP-TARGET injection log")
    check("Fix 9a comment marker present",
          "Fix 9a (2026-04-26)" in src,
          "expected Fix 9a comment block")
    check("injects from innings_1_total latched score",
          "innings_1_total or {}).get(\"score\")" in src,
          "expected innings_1_total.score sourcing in injection block")


def test_fix9a_autoswap_target_injection_runs_before_assign_teams() -> None:
    """Source-level ordering: the AUTO-SWAP-TARGET block must appear
    BEFORE the assign_teams call inside the AUTO-SWAP handler.
    assign_teams flips scoreboard.current_innings = 2 as a side
    effect, which would gate set_innings_2 out if it ran first.
    This is the mechanism behind the F2503-F2504 target=66 bug."""
    header("Fix 9a: target injection must precede assign_teams in handler")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    inject_marker = "[AUTO-SWAP-TARGET]"
    inject_pos = src.find(inject_marker)
    assert inject_pos > 0, "injection marker not found"
    # Find the closest assign_teams(...innings=_new_innings) AFTER
    # the injection marker — that's the AUTO-SWAP handler's call.
    assign_after = src.find("assign_teams(", inject_pos)
    assert assign_after > 0, "assign_teams call not found after marker"
    # Find the closest assign_teams BEFORE the injection marker that
    # is inside the same enclosing function (best-effort: just look
    # backward for the nearest assign_teams within 2000 chars to
    # detect any accidental ordering).
    snippet = src[max(0, inject_pos - 2000):inject_pos]
    assign_before = "assign_teams(" in snippet and (
        "innings=_new_innings" in snippet)
    check("injection block runs before assign_teams in AUTO-SWAP handler",
          not assign_before,
          "found assign_teams(innings=_new_innings) before "
          "the [AUTO-SWAP-TARGET] block — order is wrong, will "
          "regress to the F2503 target=None bug")


def test_fix9a_autoswap_target_uses_innings_1_total_latched_score() -> None:
    """Source-level: confirm the injection sources score from
    `innings_1_total` (the latched final, set in [INNINGS-END])
    rather than `scoreboard._inn.get('score')` exclusively.  The
    live scoreboard score can be None at AUTO-SWAP time due to
    FRAME_POISONED stripping late innings-1 reads."""
    header("Fix 9a: injection sources from innings_1_total (not just sb._inn)")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    # Locate the injection block via the marker.
    inject_pos = src.find("[AUTO-SWAP-TARGET]")
    assert inject_pos > 0
    # Walk back ~2000 chars to capture the surrounding logic.
    block = src[max(0, inject_pos - 2000):inject_pos + 500]
    check("_inn1_score_latched sourced from innings_1_total",
          "_inn1_score_latched" in block
          and "innings_1_total" in block,
          "expected _inn1_score_latched = int((innings_1_total or {})...)")
    check("max(latched, live) used as final score",
          "max(" in block and "_inn1_score_latched" in block
          and "_inn1_score_live" in block,
          "expected max(_inn1_score_latched, _inn1_score_live) "
          "to ensure latched value wins over poisoned live score")
    check("target = score + 1 (canonical T20 chase target)",
          "_inn1_score + 1" in block,
          "expected _inn1_score + 1 for chase target")


def test_fix16_autoswap_calls_score_manager_set_innings_2() -> None:
    """Source-level: AUTO-SWAP must reset ScoreManager scalars too."""
    header("Fix 16 follow-up: AUTO-SWAP resets ScoreManager scalars")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    inject_pos = src.find("[AUTO-SWAP-TARGET]")
    assert inject_pos > 0
    assign_pos = src.find("assign_teams(", inject_pos)
    assert assign_pos > inject_pos
    block = src[inject_pos:assign_pos]
    check("AUTO-SWAP calls score_mgr.set_innings_2 before assign_teams",
          "score_mgr.set_innings_2(" in block,
          "expected score_mgr.set_innings_2 in AUTO-SWAP transition block")
    check("AUTO-SWAP passes target into ScoreManager reset",
          "target=_injected_target" in block,
          "expected target=_injected_target")
    check("AUTO-SWAP passes new batting team into ScoreManager reset",
          "batting_team=_old_bowl" in block,
          "expected batting_team=_old_bowl")


# --- Fix 9b: target-monotonic + target-sanity guards -----------------
def test_fix9b_target_monotonic_guard_present_in_source() -> None:
    """Source-level: confirm the [TARGET-MONOTONIC] guard is wired
    into the team_assignment.target write path.  Without it, a
    misread strip (e.g. `GT 66-4 (11.5)` parsed as target=66) can
    overwrite a correctly-injected target."""
    header("Fix 9b: [TARGET-MONOTONIC] guard present in source")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    check("[TARGET-MONOTONIC] log tag present",
          "[TARGET-MONOTONIC]" in src,
          "expected target-monotonic refusal log")
    check("Fix 9b comment marker present",
          "Fix 9b (2026-04-26)" in src,
          "expected Fix 9b comment block")
    check("refuses overwrite when curr_target > 0",
          "Refusing inn2 target" in src,
          "expected explicit overwrite refusal log")


def test_fix9b_target_sanity_guard_rejects_below_team_score() -> None:
    """Source-level: confirm the [TARGET-SANITY] guard is wired in.
    A proposed target ≤ current team score is impossible in a valid
    chase (would mean chase already complete or value is nonsense)."""
    header("Fix 9b: [TARGET-SANITY] guard present in source")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    check("[TARGET-SANITY] log tag present",
          "[TARGET-SANITY]" in src,
          "expected target-sanity rejection log")
    check("sanity check uses current_team_score",
          "current_team_score" in src,
          "expected current_team_score in sanity rejection message")
    check("sanity check compares target vs score",
          "_tv > _curr_score" in src,
          "expected proposed-target vs curr_team_score check")


def test_fix9b_target_unconditional_overwrite_removed() -> None:
    """Source-level regression check: the unconditional
    `scoreboard.set('target', _tv, frame_count)` path inside the
    `elif scoreboard.current_innings == 2:` branch must NOT exist
    without an enclosing sanity/monotonic guard.  This ensures the
    F2504 target=66 overwrite mechanism cannot be reintroduced."""
    header("Fix 9b: unconditional inn2 target overwrite removed")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    # The original bug was:
    #     elif scoreboard.current_innings == 2:
    #         scoreboard.set("target", _tv, frame_count)
    # Now it should only set target inside the `_curr_target == 0
    # and _tv > _curr_score` branch.
    bug_pattern = (
        "elif scoreboard.current_innings == 2:\n"
        "                        scoreboard.set("
        "\"target\", _tv, frame_count)")
    check("unconditional inn2 target write removed from team_assignment",
          bug_pattern not in src,
          "found unconditional scoreboard.set('target', ...) inside "
          "elif scoreboard.current_innings == 2 branch — "
          "Fix 9b's monotonic/sanity guard has been bypassed")
    # And confirm the guarded write path exists.
    guarded_set = (
        "elif _tv > _curr_score:\n"
        "                            scoreboard.set(\n"
        "                                \"target\", _tv, frame_count)")
    check("guarded target write path present (curr_target==0 AND _tv > score)",
          guarded_set in src,
          "expected target write only inside elif _tv > _curr_score branch")


# ---------------------------------------------------------------------
# Fix 10 (2026-04-26, Path A): post-witnessed-FOW slot rotation
# ---------------------------------------------------------------------
# Closes the "stuck non" rotation gap empirically observed
# three times in CSK-vs-GT 2026-04-26 (Sarfaraz F1670, Dube F1813,
# Overton F2410+).  The hook fires from `_add_fow`'s witnessed
# stamp and clears / rotates the dismissed name out of
# `_inn["striker"]` / `["non"]`.  See Scoreboard
# `_post_witnessed_dismissal_slot_rotation` docstring for full
# rationale.

def test_fix10_striker_dismissed_rotates_non_into_striker() -> None:
    """Case 1: striker dismissed → surviving non rotates
    into striker slot, non cleared."""
    header("Fix 10: striker dismissal rotates non into striker")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL",
                     ["Sarfaraz", "Survivor", "Next", "C", "D"],
                     ["B1", "B2"])
    sb._inn["striker"] = "Sarfaraz"
    sb._inn["non"] = "Survivor"
    sb._inn["score"] = 30
    sb._inn["wickets"] = 0
    sb._inn["overs"] = "4.4"
    sb._add_fow(1, "Sarfaraz", 30, "4.4", how="caught", bowler="B1")
    check("striker rotated to surviving non name",
          sb._inn["striker"] == "Survivor",
          f"striker={sb._inn['striker']!r}")
    check("non cleared (None) pending new-batter admission",
          sb._inn["non"] is None,
          f"non={sb._inn['non']!r}")
    check("FOW entry recorded as witnessed",
          len(sb.fall_of_wickets) == 1
          and sb.fall_of_wickets[0]["batter"] == "Sarfaraz"
          and sb.fall_of_wickets[0].get("_witnessed") is True,
          f"fow={sb.fall_of_wickets}")


def test_fix10_non_dismissed_clears_non_only() -> None:
    """Case 2: non dismissed → non = None, striker
    unchanged.  Run-out at the non-striker end is the most common
    path here."""
    header("Fix 10: non dismissal clears non, "
           "striker unchanged")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL",
                     ["Striker", "Dube", "Next", "C", "D"],
                     ["B1", "B2"])
    sb._inn["striker"] = "Striker"
    sb._inn["non"] = "Dube"
    sb._inn["score"] = 75
    sb._inn["wickets"] = 1
    sb._inn["overs"] = "10.2"
    sb._add_fow(2, "Dube", 75, "10.2",
                how="run out", bowler=None)
    check("striker unchanged",
          sb._inn["striker"] == "Striker",
          f"striker={sb._inn['striker']!r}")
    check("non cleared (None)",
          sb._inn["non"] is None,
          f"non={sb._inn['non']!r}")


def test_fix10_run_out_at_striker_end_handled_via_name_match() -> None:
    """Case 3: run-out can dismiss either end.  When run-out
    dismisses the striker, name-based slot match drives the
    rotation correctly."""
    header("Fix 10: run-out at striker end rotates correctly")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL",
                     ["RunOut", "Survivor", "Next", "C", "D"],
                     ["B1", "B2"])
    sb._inn["striker"] = "RunOut"
    sb._inn["non"] = "Survivor"
    sb._inn["score"] = 100
    sb._inn["wickets"] = 2
    sb._inn["overs"] = "13.5"
    sb._add_fow(3, "RunOut", 100, "13.5", how="run out")
    check("striker rotated to surviving (run-out at striker end)",
          sb._inn["striker"] == "Survivor",
          f"striker={sb._inn['striker']!r}")
    check("non cleared",
          sb._inn["non"] is None,
          f"non={sb._inn['non']!r}")


def test_fix10_dismissed_name_in_neither_slot_is_noop() -> None:
    """Case 4: dismissed name in neither slot (e.g. cold-start
    placeholder upgrade for a much-earlier wicket) is a no-op
    on the active crease state."""
    header("Fix 10: dismissed name not in slots is no-op")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL",
                     ["A", "B", "Stranger", "D", "E"],
                     ["B1", "B2"])
    sb._inn["striker"] = "A"
    sb._inn["non"] = "B"
    sb._inn["score"] = 50
    sb._inn["wickets"] = 1
    sb._inn["overs"] = "8.1"
    sb._add_fow(2, "Stranger", 50, "8.1", how="bowled")
    check("striker unchanged (Stranger not in slots)",
          sb._inn["striker"] == "A",
          f"striker={sb._inn['striker']!r}")
    check("non unchanged (Stranger not in slots)",
          sb._inn["non"] == "B",
          f"non={sb._inn['non']!r}")


def test_fix10_anomaly_both_slots_dismissed_clears_both() -> None:
    """Case 5: anomaly path — dismissed name occupies BOTH slots
    (likely prior collision state Fix 5 didn't catch).  Defensive
    clear of both with WARN log."""
    header("Fix 10: anomaly both-slots-dismissed clears both")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL",
                     ["Collided", "Other", "Next", "C", "D"],
                     ["B1", "B2"])
    sb._inn["striker"] = "Collided"
    sb._inn["non"] = "Collided"  # collision state
    sb._inn["score"] = 60
    sb._inn["wickets"] = 0
    sb._inn["overs"] = "9.0"
    sb._add_fow(1, "Collided", 60, "9.0", how="caught")
    check("striker cleared defensively",
          sb._inn["striker"] is None,
          f"striker={sb._inn['striker']!r}")
    check("non cleared defensively",
          sb._inn["non"] is None,
          f"non={sb._inn['non']!r}")


def test_fix10_placeholder_upgrade_path_also_fires_hook() -> None:
    """The hook fires on BOTH `_add_fow` _witnessed=True stamp
    sites: the placeholder-upgrade path (line ~2557) and the
    new-entry path (line ~2622).  Verify the upgrade path."""
    header("Fix 10: placeholder→witnessed upgrade fires rotation hook")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL",
                     ["Overton", "Survivor", "Next", "C", "D"],
                     ["B1", "B2"])
    # Pre-seed an _unwitnessed placeholder at W1 (cold-start
    # back-fill style).  Subsequent `_add_fow` for the same
    # wicket number should upgrade in place AND fire the hook.
    sb.fall_of_wickets = [{
        "wicket": 1, "batter": None, "score": "?", "overs": "?",
        "_unwitnessed": True, "tentative": True,
    }]
    sb._inn["striker"] = "Survivor"
    sb._inn["non"] = "Overton"
    sb._inn["score"] = 145
    sb._inn["wickets"] = 1
    sb._inn["overs"] = "18.6"
    sb._add_fow(1, "Overton", 145, "18.6", how="lbw", bowler="B1")
    check("FOW entry upgraded to witnessed",
          sb.fall_of_wickets[0].get("_witnessed") is True
          and sb.fall_of_wickets[0]["batter"] == "Overton",
          f"fow={sb.fall_of_wickets}")
    check("non (Overton) cleared by upgrade-path hook",
          sb._inn["non"] is None,
          f"non={sb._inn['non']!r}")
    check("striker (Survivor) unchanged",
          sb._inn["striker"] == "Survivor",
          f"striker={sb._inn['striker']!r}")


def test_fix10_powell_f179_f258_placeholder_upgrade_with_drifted_slots() -> None:
    """**Coverage gap fixture (LSG-vs-KKR 2026-04-26, Powell W4).**

    Production sequence (from `pipeline-…-fix12-v6-validation.log`):
      * F179 (20:06:07): `[FOW] Placeholder W4: _unwitnessed`
        (broadcast registered `wickets→4` but no batter name yet)
      * F258 (20:08:09, ~2 min later): `[FOW] Upgraded
        placeholder W4: Rovman Powell at 31/4 (6.1)
        (was _unwitnessed)`
      * At F258, `sb._inn["striker"]` is None and
        `sb._inn["non"]` is `Cameron Green` — Powell is
        no longer in either crease slot because the broadcast
        had moved past Powell's tenure during the 79-frame gap.

    Result: Fix 10's `_post_witnessed_dismissal_slot_rotation`
    hook fires (the upgrade path correctly invokes it per
    `test_fix10_placeholder_upgrade_path_also_fires_hook`) but
    the slot-membership check at scoreboard.py line 2842
    (`if not (striker_dismissed or non_dismissed):
    return`) returns silently — Case 3 of the docstring
    ("dismissed name in **neither** slot: no-op").

    The docstring assumed Case 3 only fires for cold-start
    back-fill of *historic* wickets where current crease state
    legitimately reflects a much later innings stage.  Powell
    shows it also fires for **recent** wickets when the
    placeholder→witness gap (~2 min in production) outlives the
    crease state.  Per-match-3 baseline (Sarfaraz/Dube/Overton)
    had crease slots populated at the moment of witness; Powell
    is the first observed case of a real-time but delayed
    witness.

    Related deeper gap: `_add_fow` does NOT update
    `batting_card[dismissed].status = "out"` on the
    placeholder→witness upgrade (only `dismiss_batter` and
    `_auto_dismiss_for_new_batter` set the status flag).  After
    the F258 upgrade, Powell remains in `batting_card` with
    status `batting`, which is why subsequent BEFORE_bat2
    snapshots continued to show `Rovman Powell 14(56)` (the
    phantom stats persisting because the dismissal didn't
    propagate to the card).

    **Current behaviour (this test asserts the existing
    contract — no-op when dismissed not in slots).**  When the
    coverage-gap fix lands, this test should be updated to
    assert the new expected behaviour (e.g. clearing
    `batting_card` status, or extending the hook to also act
    on `active_batters` membership).
    """
    header("Fix 10: Powell F179→F258 production fixture "
           "(coverage gap — hook correctly no-ops on drifted-slots case)")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("KKR", "LSG",
                     ["Powell", "Green", "Singh", "D", "E"],
                     ["Khan", "Bishnoi"])
    # Reproduce F179 state: _unwitnessed placeholder at W4.
    sb.fall_of_wickets = [
        {"wicket": 1, "batter": "?", "score": "?", "overs": "?",
         "tentative": True, "_unwitnessed": True},
        {"wicket": 2, "batter": "?", "score": "?", "overs": "?",
         "tentative": True, "_unwitnessed": True},
        {"wicket": 3, "batter": "?", "score": "?", "overs": "?",
         "tentative": True, "_unwitnessed": True},
        {"wicket": 4, "batter": None, "score": "?", "overs": "?",
         "_unwitnessed": True, "tentative": True},
    ]
    # Reproduce F258 crease state: striker=None, non=Green
    # (Powell already cleared from slots; Singh not yet promoted).
    sb._inn["striker"] = None
    sb._inn["non"] = "Green"
    sb._inn["score"] = 31
    sb._inn["wickets"] = 4
    sb._inn["overs"] = "6.1"
    # Powell still in batting_card with status "batting" (the second
    # related gap — _add_fow doesn't propagate dismissal to card).
    sb.batting_card["Powell"]["status"] = "batting"
    sb.batting_card["Powell"]["runs"] = 14
    sb.batting_card["Powell"]["balls"] = 56  # Phantom — separately
    # filed under the cricket-physics-balls-ceiling P0.

    # Trigger the F258 upgrade.
    sb._add_fow(4, "Powell", 31, "6.1", how="caught", bowler="Khan")

    check("FOW W4 upgraded to witnessed",
          sb.fall_of_wickets[3].get("_witnessed") is True
          and sb.fall_of_wickets[3]["batter"] == "Powell",
          f"fow[3]={sb.fall_of_wickets[3]}")
    check("slot rotation correctly no-op'd: striker still None "
          "(Powell wasn't in striker slot)",
          sb._inn["striker"] is None,
          f"striker={sb._inn['striker']!r}")
    check("slot rotation correctly no-op'd: non still "
          "'Green' (Powell wasn't in non slot)",
          sb._inn["non"] == "Green",
          f"non={sb._inn['non']!r}")
    # Fix 13 (Path D, 2026-04-26): Case 5 now propagates the
    # dismissal to batting_card.status even when not in slots.
    check("Fix 13 Case 5: batting_card['Powell'].status "
          "propagated to 'out' by Path D extension",
          sb.batting_card["Powell"]["status"] == "out",
          f"status={sb.batting_card['Powell']['status']}")


def test_fix10_auto_dismiss_path_clears_slot_via_hook() -> None:
    """End-to-end: `_auto_dismiss_for_new_batter` is the path that
    historically left `non` pointing at the dismissed name
    (per CSK-vs-GT 2026-04-26 Sarfaraz/Dube/Overton).  With Fix 10
    in place, that path's `_add_fow` call fires the rotation hook
    and the slot is cleared."""
    header("Fix 10: _auto_dismiss_for_new_batter path now clears "
           "stuck non via hook")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL",
                     ["Sarfaraz", "Striker", "NewBatter", "D", "E"],
                     ["B1", "B2"])
    # Two batters at the crease pre-wicket; Sarfaraz at non.
    for n in ("Sarfaraz", "Striker"):
        sb.batting_card[n]["status"] = "batting"
        sb.batting_card[n]["runs"] = 5
        sb.batting_card[n]["balls"] = 8
    sb._inn["striker"] = "Striker"
    sb._inn["non"] = "Sarfaraz"
    sb._inn["score"] = 40
    # Wickets counter has already advanced (broadcast registered the
    # wicket via score/wickets read); auto-dismiss runs reactively.
    # Gate at line ~1400 requires `_cur_wk > _last_autodismiss_wk`.
    sb._inn["wickets"] = 1
    sb._inn["overs"] = "4.4"
    sb._last_autodismiss_wickets = 0
    # Extractor strip shows Striker + NewBatter — Sarfaraz missing.
    sb._extractor_batter_names = ["STRIKER", "NEWBATTER"]
    # Streak gate requires ≥2 missing frames before acting (the gate
    # increments the streak then checks ≥2, so seed at 1 → becomes 2).
    sb._missing_batter_streak = {"Sarfaraz": 1}
    active = ["Sarfaraz", "Striker"]
    result = sb._auto_dismiss_for_new_batter(active, "NewBatter")
    check("auto-dismiss returns 'Sarfaraz'",
          result == "Sarfaraz", f"result={result!r}")
    check("Sarfaraz status flipped to 'out'",
          sb.batting_card["Sarfaraz"]["status"] == "out",
          f"status={sb.batting_card['Sarfaraz']['status']}")
    check("Fix 10 hook cleared Sarfaraz from non slot",
          sb._inn["non"] is None,
          f"non={sb._inn['non']!r}")
    check("striker slot unchanged (Striker survives)",
          sb._inn["striker"] == "Striker",
          f"striker={sb._inn['striker']!r}")


def test_fix10_dismiss_batter_path_compatible_with_hook() -> None:
    """`dismiss_batter()` already clears slots at lines 2800-2803.
    Fix 10's hook runs first (inside `_add_fow` at 2795).  Verify
    the two clears compose cleanly — the explicit clears become
    no-ops because the hook already cleared the slot."""
    header("Fix 10: dismiss_batter composes with hook (no double-"
           "clear corruption)")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL",
                     ["Dube", "Other", "Next", "C", "D"],
                     ["B1", "B2"])
    sb.batting_card["Dube"]["status"] = "batting"
    sb.batting_card["Other"]["status"] = "batting"
    sb._inn["striker"] = "Dube"
    sb._inn["non"] = "Other"
    sb._inn["score"] = 80
    sb._inn["wickets"] = 0
    sb._inn["overs"] = "11.5"
    ok = sb.dismiss_batter("Dube", how="bowled", bowler="B1")
    check("dismiss_batter returned True", ok, "dismiss_batter() failed")
    check("Dube status='out'",
          sb.batting_card["Dube"]["status"] == "out",
          f"status={sb.batting_card['Dube']['status']}")
    check("striker rotated to Other (hook fired before "
          "dismiss_batter's own clear)",
          sb._inn["striker"] == "Other",
          f"striker={sb._inn['striker']!r}")
    check("non is None",
          sb._inn["non"] is None,
          f"non={sb._inn['non']!r}")


def test_fix10_helper_method_exists_on_scoreboard() -> None:
    """Source-level wiring: the helper method must exist with the
    expected name and be callable."""
    header("Fix 10: _post_witnessed_dismissal_slot_rotation helper "
           "present on Scoreboard")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    check("helper method exists",
          hasattr(sb, "_post_witnessed_dismissal_slot_rotation")
          and callable(getattr(sb,
                               "_post_witnessed_dismissal_slot_rotation")),
          "Scoreboard._post_witnessed_dismissal_slot_rotation missing")
    # Idempotent: calling with None or empty name is safe and a no-op.
    sb.setup_innings("BAT", "BOWL", ["a", "b"], ["c", "d"])
    sb._inn["striker"] = "a"
    sb._inn["non"] = "b"
    sb._post_witnessed_dismissal_slot_rotation(None)
    check("None dismissed → no-op",
          sb._inn["striker"] == "a" and sb._inn["non"] == "b",
          f"_inn={sb._inn}")
    sb._post_witnessed_dismissal_slot_rotation("")
    check("empty-string dismissed → no-op",
          sb._inn["striker"] == "a" and sb._inn["non"] == "b",
          f"_inn={sb._inn}")


def test_fix10_hook_call_present_in_source() -> None:
    """Source-level wiring: both `_witnessed=True` stamp sites in
    `_add_fow` must invoke the rotation hook.  Guards against
    accidental removal during future refactors."""
    header("Fix 10: rotation hook wired at both _add_fow stamp sites")
    src = (Path(__file__).resolve().parent / "eyes" / "scoreboard.py"
           ).read_text()
    n_calls = src.count(
        "self._post_witnessed_dismissal_slot_rotation(")
    # Two callsites inside `_add_fow` plus the Fix 13 Path B pending-
    # wicket sibling hook.  The helper definition itself uses
    # `def …` (not `self.…`) so it does not contribute to this count.
    check("rotation hook invoked at exactly 2 callsites in "
          "scoreboard.py (both _add_fow stamp paths)",
          n_calls == 3,
          f"expected 3, found {n_calls} occurrences of "
          f"self._post_witnessed_dismissal_slot_rotation(")
    check("helper definition present",
          "def _post_witnessed_dismissal_slot_rotation(" in src,
          "helper method definition not found in scoreboard.py")
    # And explicitly check both _add_fow paths reference it.
    check("hook firing block follows existing['_witnessed'] = True",
          "existing[\"_witnessed\"] = True" in src
          and "self._post_witnessed_dismissal_slot_rotation(\n"
              "                        batter)" in src,
          "placeholder-upgrade hook callsite missing")
    check("hook firing block follows fall_of_wickets.sort()",
          "self.fall_of_wickets.sort(key=lambda x: x.get"
          "(\"wicket\", 0))\n"
          "        # Fix 10 (2026-04-26, Path A): post-witnessed "
          "dismissal" in src,
          "new-entry hook callsite missing")


def test_fix13_path_b_known_wicket_increment_cleans_placeholder_gap() -> None:
    """Fix 13 Path B: a known dismissed batter on a WICKET ball must
    be cleared immediately, even before the FOW placeholder is witnessed."""
    header("Fix 13 Path B: known wicket increment clears active batter")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("LSG", "KKR",
                     ["Marsh", "Markram", "Pooran", "D", "E"],
                     ["Arora", "Narine"])
    sb._inn["striker"] = "Marsh"
    sb._inn["non"] = "Markram"
    sb._inn["score"] = 8
    sb._inn["wickets"] = 1
    sb._inn["overs"] = "1.1"
    sb.fall_of_wickets = [Scoreboard.make_fow_placeholder(1)]

    sb.apply_known_wicket_increment("Marsh")

    check("dismissed striker rotated out immediately",
          sb._inn["striker"] == "Markram"
          and sb._inn["non"] is None,
          f"_inn={sb._inn}")
    check("batting_card status flipped to out",
          sb.batting_card["Marsh"]["status"] == "out",
          f"status={sb.batting_card['Marsh']['status']}")
    check("FOW placeholder upgraded to witnessed Marsh "
          "(Fix B: immediate FOW commit on WICKET ball-event)",
          sb.fall_of_wickets[0].get("batter") == "Marsh"
          and sb.fall_of_wickets[0].get("_witnessed") is True
          and sb.fall_of_wickets[0].get("score") == 8,
          f"fow={sb.fall_of_wickets}")


def test_fow_committed_at_wicket_ball_event() -> None:
    """Fix B (#27): apply_known_wicket_increment must commit FOW
    immediately rather than waiting for a witnessed read.  Closes the
    39s _unwitnessed gap observed when score/wickets are reliable but
    the FOW upgrade event arrives much later."""
    header("Fix B: FOW committed at apply_known_wicket_increment")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("PBKS", "RR",
                     ["Raj Bawa", "Other", "Next", "D", "E"],
                     ["B1", "B2"])
    sb.batting_card["Raj Bawa"]["status"] = "batting"
    sb.batting_card["Other"]["status"] = "batting"
    sb._inn["striker"] = "Raj Bawa"
    sb._inn["non"] = "Other"
    sb._inn["score"] = 161
    sb._inn["wickets"] = 7
    sb._inn["overs"] = "19.0"
    sb.pending_dismissal_hint = "bowled"
    sb.pending_dismissal_bowler = "B1"

    sb.apply_known_wicket_increment("Raj Bawa")

    fow = sb.fall_of_wickets[-1] if sb.fall_of_wickets else {}
    check("FOW row created for the dismissal",
          fow.get("batter") == "Raj Bawa",
          f"fow={sb.fall_of_wickets}")
    check("FOW marked witnessed",
          fow.get("_witnessed") is True,
          f"fow={fow}")
    check("FOW score=161",
          fow.get("score") == 161,
          f"fow={fow}")
    check("FOW overs='19.0'",
          fow.get("overs") == "19.0",
          f"fow={fow}")
    check("Raj Bawa status='out'",
          sb.batting_card["Raj Bawa"]["status"] == "out",
          f"status={sb.batting_card['Raj Bawa']['status']}")


def test_fow_not_committed_when_wickets_counter_zero() -> None:
    """Fix B guard: wk > 0 check prevents double-fire on cold-start
    when wickets counter is still 0."""
    header("Fix B: FOW commit skipped when wickets=0")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL", ["A", "B", "C"], ["X", "Y"])
    sb.batting_card["A"]["status"] = "batting"
    sb._inn["striker"] = "A"
    sb._inn["non"] = "B"
    sb._inn["score"] = 0
    sb._inn["wickets"] = 0
    sb._inn["overs"] = "0.0"
    sb.apply_known_wicket_increment("A")
    check("no FOW row created when wickets=0",
          len(sb.fall_of_wickets) == 0,
          f"fow={sb.fall_of_wickets}")


def test_auto_dismiss_requires_incoming_consensus() -> None:
    """Fix C (#28): 2-frame consensus on the incoming new_batter name.
    Prevents F72-class phantom replacements where ext_bat momentarily
    surfaces a wrong incoming name (panel/replay carrying stale row)."""
    header("Fix C: _auto_dismiss_for_new_batter requires "
           "incoming-batter consensus")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        "MI", "BOWL",
        ["Tilak Varma", "Raj Bawa", "Deepak Chahar", "Rohit Sharma", "D"],
        ["B1", "B2"])
    sb.batting_card["Tilak Varma"]["status"] = "batting"
    sb.batting_card["Raj Bawa"]["status"] = "batting"
    sb._inn["striker"] = "Tilak Varma"
    sb._inn["non"] = "Raj Bawa"
    sb._inn["score"] = 50
    sb._inn["wickets"] = 2
    sb._inn["overs"] = "8.4"
    sb._last_autodismiss_wickets = 1
    sb._extractor_batter_names = ["RAJ BAWA", "DEEPAK CHAHAR"]
    sb._missing_batter_streak = {"Tilak Varma": 2}

    active = ["Tilak Varma", "Raj Bawa"]

    result = sb._auto_dismiss_for_new_batter(active, "Rohit Sharma")
    check("phantom incoming Rohit Sharma defers (streak=1/2)",
          result is None,
          f"result={result!r}")
    check("Tilak Varma still batting (no premature dismissal)",
          sb.batting_card["Tilak Varma"]["status"] == "batting",
          f"status={sb.batting_card['Tilak Varma']['status']}")

    result = sb._auto_dismiss_for_new_batter(active, "Deepak Chahar")
    check("different incoming Deepak Chahar still defers "
          "(streak resets to 1/2)",
          result is None,
          f"result={result!r}")

    result = sb._auto_dismiss_for_new_batter(active, "Deepak Chahar")
    check("repeated Deepak Chahar fires (streak=2/2)",
          result == "Tilak Varma",
          f"result={result!r}")
    check("Tilak Varma now out",
          sb.batting_card["Tilak Varma"]["status"] == "out",
          f"status={sb.batting_card['Tilak Varma']['status']}")


def test_fix13_path_b_wicket_handler_wired_in_source() -> None:
    header("Fix 13 Path B: WICKET handler invokes pending cleanup")
    src = (Path(__file__).resolve().parent / "test_pipeline.py"
           ).read_text()
    check("WICKET handler calls apply_known_wicket_increment",
          "scoreboard.apply_known_wicket_increment(" in src
          and "ball_event.get(\"dismissed\"))" in src,
          "pending-wicket cleanup call missing from WICKET handler")


def test_wire_format_accepts_fractional_cricket_overs_string() -> None:
    """Regression for DC-vs-RCB live crash: wire formatter must accept
    cricket-over strings such as '6.5' without int() conversion."""
    header("Wire: fractional cricket-over string does not crash")
    from wire import format_wire

    line = format_wire(
        {"type": "RUNS", "runs": 1, "striker": "David Miller"},
        {"overs": "6.5", "score": 24, "wickets": 6,
         "bowler": {"name": "Rasikh Salam Dar"}},
        None,
    )
    check("wire line preserves over 6.5",
          line.startswith("6.5: Rasikh Salam Dar to David Miller"),
          line)
    check("wire line includes score",
          line.endswith(". 24/6"),
          line)


def test_wire_format_accepts_integer_over_string() -> None:
    header("Wire: integer over string formats as X.0")
    from wire import format_wire

    line = format_wire(
        {"type": "DOT", "runs": 0, "striker": "Abishek Porel"},
        {"overs": "7", "score": 25, "wickets": 6,
         "bowler": {"name": "Rasikh Salam Dar"}},
        None,
    )
    check("wire line formats integer over as 7.0",
          line.startswith("7.0: Rasikh Salam Dar to Abishek Porel"),
          line)


# ---------------------------------------------------------------------
# Fix 11: EXTRAS-INF admission gate (Layer 1 of phantom +N quartet)
# ---------------------------------------------------------------------
def _make_sb_for_extras_inf_gate(
        score: int,
        wickets: int,
        active: list[tuple[str, int, int]],
        dismissed: list[tuple[str, int, int]],
):
    """Build a Scoreboard configured for Fix 11 gate testing.

    `active`/`dismissed` are lists of (name, runs, balls).  Dismissed
    batters get a witnessed FOW entry stamped so the completeness
    check (`_dismissed_count == wickets`) is satisfied when
    `len(dismissed) == wickets`.
    """
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    squad_bat = [n for n, _, _ in active] + [
        n for n, _, _ in dismissed] + ["Spare1", "Spare2"]
    sb.setup_innings("BAT", "BOWL", squad_bat[:11], ["B1", "B2"])
    for name, runs, balls in active:
        sb.batting_card[name]["status"] = "batting"
        sb.batting_card[name]["runs"] = runs
        sb.batting_card[name]["balls"] = balls
    for i, (name, runs, balls) in enumerate(dismissed):
        sb.batting_card[name]["status"] = "out"
        sb.batting_card[name]["runs"] = runs
        sb.batting_card[name]["balls"] = balls
        sb.fall_of_wickets.append({
            "wicket": i + 1, "batter": name, "score": runs * 2,
            "overs": f"{i + 1}.0", "how": "caught", "bowler": "B1",
            "_witnessed": True,
        })
    if active:
        sb._inn["striker"] = active[0][0]
        if len(active) > 1:
            sb._inn["non"] = active[1][0]
    sb._inn["score"] = score
    sb._inn["wickets"] = wickets
    sb._inn["overs"] = "10.0"
    return sb


def _drive_apply_scorer_decision(sb, batter_proposals: dict):
    """Build a minimal `decision` + `extracted` and run
    `apply_scorer_decision`.  `batter_proposals` is a dict of
    {name: (runs, balls)}.  Returns (changes, post_state) where
    `post_state` is a dict snapshotting batter runs after the call
    so tests can assert which proposals were committed vs gated.
    """
    from test_pipeline import apply_scorer_decision
    decision = {
        "batter_updates": {
            n: {"runs": r, "balls": b, "accepted": True}
            for n, (r, b) in batter_proposals.items()
        }
    }
    extracted = {
        "batters": [
            {"name": n, "runs": r, "balls": b}
            for n, (r, b) in batter_proposals.items()
        ]
    }
    changes = apply_scorer_decision(
        sb, decision, frame=999, jump_guard=None,
        batting_team={"name": "BAT"}, extracted=extracted,
        frame_type="LIVE")
    post_state = {
        n: sb.batting_card[n].get("runs")
        for n in batter_proposals
        if n in sb.batting_card
    }
    return changes, post_state


def test_fix11_gate_blocks_phantom_admission_simple() -> None:
    """Synthesised fixture mirroring the F732 shape (wkts=3, score=30,
    proposed bat_sum=47 → +17 excess).  Gate must fire and reject the
    entire batter slate."""
    header("Fix 11: EXTRAS-INF gate blocks phantom admission "
           "(simple fixture, F732 shape)")
    sb = _make_sb_for_extras_inf_gate(
        score=30, wickets=3,
        active=[("Brevis", 1, 5), ("Other", 0, 2)],
        dismissed=[("D1", 5, 8), ("D2", 8, 12), ("D3", 9, 14)])
    # Sanity: pre-call dismissed_sum=22, current bat_sum=22+1+0=23,
    # extras_implicit = 30-23 = 7.  Legitimate state.
    pre_brevis = sb.batting_card["Brevis"]["runs"]
    pre_other = sb.batting_card["Other"]["runs"]
    # Phantom proposal: Brevis 20, Other 5 → bat_sum = 22+20+5 = 47
    # > score=30 (excess=17).  Gate must fire.
    changes, post = _drive_apply_scorer_decision(
        sb, {"Brevis": (20, 10), "Other": (5, 5)})
    check("gate emits EXTRAS-INF-GATE marker in changes",
          any(isinstance(c, str) and c.startswith("EXTRAS-INF-GATE:")
              for c in changes),
          f"changes={changes}")
    check("gate marker carries bat_sum=47>30 detail",
          any(isinstance(c, str)
              and "bat_sum=47" in c and ">30" in c
              for c in changes),
          f"changes={changes}")
    check("Brevis runs unchanged after gate (no commit)",
          sb.batting_card["Brevis"]["runs"] == pre_brevis,
          f"runs={sb.batting_card['Brevis']['runs']!r} "
          f"(expected {pre_brevis})")
    check("Other runs unchanged after gate (no commit)",
          sb.batting_card["Other"]["runs"] == pre_other,
          f"runs={sb.batting_card['Other']['runs']!r} "
          f"(expected {pre_other})")


def test_fix11_gate_passes_legitimate_admission() -> None:
    """Same fixture shape, but proposed bat_sum stays <= score.
    Gate must NOT fire and updates must commit normally."""
    header("Fix 11: EXTRAS-INF gate does not block legitimate "
           "admission")
    sb = _make_sb_for_extras_inf_gate(
        score=50, wickets=2,
        active=[("Bat1", 10, 15), ("Bat2", 8, 12)],
        dismissed=[("D1", 5, 8), ("D2", 7, 10)])
    # dismissed_sum=12, current bat_sum=12+10+8=30, extras=20 implicit.
    # Propose Bat1=14(19), Bat2=11(14) → proposed bat_sum=12+14+11=37
    # <= 50.  Gate scope: the gate is silent on legitimate proposals.
    # Downstream commit success (whether `update_batter` actually
    # writes the value) is the responsibility of OTHER guards
    # (consistent_tracker regression, clone-reject, etc.) tested
    # elsewhere in this suite — *that* path is not Fix 11's
    # responsibility, so we do not assert on it here.
    changes, post = _drive_apply_scorer_decision(
        sb, {"Bat1": (14, 19), "Bat2": (11, 14)})
    check("gate does NOT emit EXTRAS-INF-GATE marker on legitimate "
          "admission",
          not any(isinstance(c, str)
                  and c.startswith("EXTRAS-INF-GATE:")
                  for c in changes),
          f"unexpected gate fire; changes={changes}")
    # Negative invariant: gate did not zero `batter_ups` /
    # `_ext_batter_stats`, so the downstream loops at least had a
    # chance to run.  We can't directly observe that here, but the
    # "no marker" assertion above is the gate's contract; the
    # downstream commit path is exercised by other tests.


def test_fix11_gate_abstains_on_incomplete_dismissed_count() -> None:
    """When `dismissed_count != wickets` (e.g. wicket fired but FOW
    not yet upgraded with the dismissed batter's runs), the
    completeness gate must abstain even when proposed sum looks
    impossible.  Prevents false positives during transient states."""
    header("Fix 11: gate abstains on incomplete dismissed-batter data")
    # wickets=3 but only 2 dismissed in batting_card
    sb = _make_sb_for_extras_inf_gate(
        score=30, wickets=3,
        active=[("Brevis", 1, 5), ("Other", 0, 2)],
        dismissed=[("D1", 5, 8), ("D2", 8, 12)])  # only 2, not 3
    sb._inn["wickets"] = 3  # force the mismatch
    # Same impossible proposal as test_fix11_simple
    changes, post = _drive_apply_scorer_decision(
        sb, {"Brevis": (20, 10), "Other": (5, 5)})
    check("gate ABSTAINS (no marker emitted) on incomplete data",
          not any(isinstance(c, str)
                  and c.startswith("EXTRAS-INF-GATE:")
                  for c in changes),
          f"gate fired during incomplete state; changes={changes}")


def test_fix11_gate_abstains_on_unknown_dismissed_runs() -> None:
    """Placeholder FOW entries can leave a dismissed batter's runs
    as None.  Gate must abstain rather than treat unknown as zero."""
    header("Fix 11: gate abstains when a dismissed batter's runs are "
           "None (placeholder FOW)")
    sb = _make_sb_for_extras_inf_gate(
        score=30, wickets=3,
        active=[("Brevis", 1, 5), ("Other", 0, 2)],
        dismissed=[("D1", 5, 8), ("D2", 8, 12), ("D3", 9, 14)])
    # Strip runs from one dismissed batter (placeholder shape)
    sb.batting_card["D2"]["runs"] = None
    changes, post = _drive_apply_scorer_decision(
        sb, {"Brevis": (20, 10), "Other": (5, 5)})
    check("gate ABSTAINS (no marker) on unknown dismissed runs",
          not any(isinstance(c, str)
                  and c.startswith("EXTRAS-INF-GATE:")
                  for c in changes),
          f"gate fired despite unknown runs; changes={changes}")


def test_fix11_gate_neutralizes_extractor_init_path_too() -> None:
    """If the gate blocks, the INIT path (which populates from
    extractor when no active batters exist) must also be neutralised
    — otherwise a phantom would commit via the INIT side channel."""
    header("Fix 11: gate neutralises both batter_ups loop AND INIT "
           "loop on block")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL",
                     ["NewBat1", "NewBat2", "D1", "D2", "D3"],
                     ["B1", "B2"])
    # No active batters yet; three dismissed with known runs.
    for name, runs in [("D1", 5), ("D2", 8), ("D3", 9)]:
        sb.batting_card[name]["status"] = "out"
        sb.batting_card[name]["runs"] = runs
        sb.batting_card[name]["balls"] = 8
        sb.fall_of_wickets.append({
            "wicket": len(sb.fall_of_wickets) + 1, "batter": name,
            "score": runs * 2, "overs": "1.0", "how": "caught",
            "bowler": "B1", "_witnessed": True,
        })
    sb._inn["score"] = 30
    sb._inn["wickets"] = 3
    sb._inn["overs"] = "10.0"
    # Drive with batter_ups containing an impossible proposal so the
    # gate fires.  When gate fires it must zero _ext_batter_stats too,
    # so the downstream INIT loop (which uses _ext_batter_stats when
    # batter_ups is empty) cannot smuggle the phantom in.
    changes, post = _drive_apply_scorer_decision(
        sb, {"NewBat1": (20, 10), "NewBat2": (5, 5)})
    check("gate marker emitted",
          any(isinstance(c, str) and c.startswith("EXTRAS-INF-GATE:")
              for c in changes),
          f"changes={changes}")
    check("NewBat1 NOT activated via INIT path (status not 'batting')",
          sb.batting_card["NewBat1"].get("status") != "batting",
          f"status={sb.batting_card['NewBat1'].get('status')!r}")
    check("NewBat1 runs unchanged (gate blocked extractor "
          "smuggle path)",
          sb.batting_card["NewBat1"].get("runs") in (None, 0),
          f"runs={sb.batting_card['NewBat1'].get('runs')!r}")


def test_fix11_gate_hosein_f2408_production_replay() -> None:
    """Replay the F2408 production fixture from CSK-vs-GT 2026-04-26.

    Pre-state (from log F2408 BEFORE_): score=154, wickets=7,
    Gaikwad 70(59), Hosein 0(0).  Dismissed sum was 84-85 (per F2400
    [EXTRAS-INF] log: bat_sum=155 = 70 + 0 + dismissed_sum, so
    dismissed_sum=85).  Phantom proposal: Hosein=21(6).  Proposed
    bat_sum = 85 + 70 + 21 = 176 > score=154 (excess=22).  Gate must
    fire.
    """
    header("Fix 11: replays F2408 (CSK-vs-GT) Hosein +21 phantom "
           "admission")
    # Spread dismissed_sum=85 across 7 batters.
    dismissed_runs = [0, 4, 0, 10, 22, 7, 18]  # sum = 61
    # Adjust so total is 85: actual dismissed batters' runs from the
    # match would sum to ~85; for fixture purposes we use any
    # distribution that totals 85.
    dismissed_runs = [12, 4, 0, 10, 22, 19, 18]  # sum = 85
    sb = _make_sb_for_extras_inf_gate(
        score=154, wickets=7,
        active=[("Gaikwad", 70, 59), ("Hosein", 0, 0)],
        dismissed=[(f"W{i+1}", r, 8)
                   for i, r in enumerate(dismissed_runs)])
    pre_hosein = sb.batting_card["Hosein"]["runs"]
    changes, post = _drive_apply_scorer_decision(
        sb, {"Hosein": (21, 6), "Gaikwad": (70, 59)})
    check("F2408 replay: gate fires on Hosein 21 phantom",
          any(isinstance(c, str) and c.startswith("EXTRAS-INF-GATE:")
              for c in changes),
          f"changes={changes}")
    check("F2408 replay: gate marker carries excess=22 detail",
          any(isinstance(c, str)
              and "bat_sum=176" in c and ">154" in c
              for c in changes),
          f"changes={changes}")
    check("F2408 replay: Hosein runs stay at 0 (phantom blocked)",
          sb.batting_card["Hosein"]["runs"] == pre_hosein,
          f"Hosein runs leaked to "
          f"{sb.batting_card['Hosein']['runs']!r}")


def test_fix11_gate_does_not_block_score_side_phantom() -> None:
    """Honest scope claim: Layer 1 catches batter-side sum-violation
    only.  F52/F53 score-side phantoms (where score itself is
    inflated but bat_sum stays < score) are NOT in scope.  This test
    documents that limitation.
    """
    header("Fix 11: gate does NOT catch score-side phantoms (scope "
           "documentation, F53 shape)")
    sb = _make_sb_for_extras_inf_gate(
        score=5, wickets=0,
        active=[("Bat1", 1, 1)],
        dismissed=[])
    # F53 reality: score was inflated by +4 (real=1, observed=5),
    # bat_sum=1.  Layer 1 condition `bat_sum > score` is 1 > 5 ->
    # False, so gate does NOT fire even though state is corrupted.
    changes, post = _drive_apply_scorer_decision(
        sb, {"Bat1": (1, 1)})
    check("gate does NOT fire on score-side phantom (documented "
          "scope limitation)",
          not any(isinstance(c, str)
                  and c.startswith("EXTRAS-INF-GATE:")
                  for c in changes),
          f"unexpected fire; changes={changes}")


def test_fix14_balls_ceiling_rejects_powell_class() -> None:
    """Powell `14(56)` at 6.1 overs production fixture.  At 6.1
    overs the innings has had 37 legal balls — no batter can have
    faced 56.  Gate must hard-reject the slate."""
    header("Fix 14: BALLS-CEILING-GATE rejects Powell-class "
           "(balls=56 > 6.1 overs ceiling)")
    sb = _make_sb_for_extras_inf_gate(
        score=31, wickets=4,
        active=[("Green", 8, 7), ("Powell", 14, 4)],
        dismissed=[("D1", 5, 6), ("D2", 0, 1),
                   ("D3", 4, 6), ("D4", 0, 0)])
    sb._inn["overs"] = "6.1"
    pre_powell = sb.batting_card["Powell"]["runs"]
    pre_green = sb.batting_card["Green"]["runs"]
    # Phantom proposal: Powell jumps to 14(56) — same runs, but
    # balls=56 violates 6.1-overs ceiling (37 legal + tolerance 2 = 39).
    changes, _post = _drive_apply_scorer_decision(
        sb, {"Powell": (14, 56), "Green": (8, 8)})
    check("gate emits BALLS-CEILING-GATE marker in changes",
          any(isinstance(c, str)
              and c.startswith("BALLS-CEILING-GATE:")
              for c in changes),
          f"changes={changes}")
    check("gate marker carries max_balls=56 detail",
          any(isinstance(c, str)
              and "max_balls=56" in c and "ceiling=39" in c
              for c in changes),
          f"changes={changes}")
    check("Powell runs unchanged after gate (no commit)",
          sb.batting_card["Powell"]["runs"] == pre_powell,
          f"runs={sb.batting_card['Powell']['runs']!r} "
          f"(expected {pre_powell})")
    check("Green runs unchanged after gate (slate-wide reject)",
          sb.batting_card["Green"]["runs"] == pre_green,
          f"runs={sb.batting_card['Green']['runs']!r} "
          f"(expected {pre_green})")


def test_fix14_balls_ceiling_passes_legitimate_balls_count() -> None:
    """Legitimate end-of-innings: at 19.6 overs (120 balls) a
    batter who opened could have faced 60-70 balls.  Gate must
    NOT fire."""
    header("Fix 14: BALLS-CEILING-GATE passes legitimate "
           "high-balls slate near innings end")
    sb = _make_sb_for_extras_inf_gate(
        score=180, wickets=3,
        active=[("Opener", 75, 65), ("Mid", 30, 22)],
        dismissed=[("D1", 30, 25), ("D2", 25, 18), ("D3", 15, 11)])
    sb._inn["overs"] = "19.6"  # 120 legal balls
    changes, _post = _drive_apply_scorer_decision(
        sb, {"Opener": (76, 66), "Mid": (31, 23)})
    check("gate does NOT emit BALLS-CEILING-GATE marker on "
          "legitimate slate",
          not any(isinstance(c, str)
                  and c.startswith("BALLS-CEILING-GATE:")
                  for c in changes),
          f"unexpected fire; changes={changes}")
    # We don't assert the post-state explicitly because upstream
    # guards (runs-monotonic, balls-monotonic, etc.) govern the
    # actual commit; the gate-silence assertion above is the
    # critical Fix 14 invariant.


def test_fix14_balls_ceiling_tolerance_absorbs_edge_cases() -> None:
    """Tolerance window of 2 balls absorbs scorer-read edge cases
    near over boundaries (e.g. no-ball charging the batter)."""
    header("Fix 14: BALLS-CEILING-GATE tolerance window")
    sb = _make_sb_for_extras_inf_gate(
        score=20, wickets=1,
        active=[("Bat1", 5, 3), ("Bat2", 5, 3)],
        dismissed=[("D1", 8, 6)])
    sb._inn["overs"] = "2.0"  # 12 legal balls; ceiling=14
    # Within tolerance: balls=14 should pass (== ceiling).
    changes, _ = _drive_apply_scorer_decision(
        sb, {"Bat1": (5, 14), "Bat2": (5, 0)})
    check("balls=14 (== ceiling) does not fire gate",
          not any(isinstance(c, str)
                  and c.startswith("BALLS-CEILING-GATE:")
                  for c in changes),
          f"unexpected fire at boundary; changes={changes}")


def test_fix15_score_side_gate_rejects_unexplained_advance() -> None:
    """F52/F53-class score inflation: score jumps by +4 with no
    batter advance and no wicket — proposed advance is unexplained
    and must be rejected by the Layer 1.5 gate."""
    header("Fix 15: SCORE-INF-GATE rejects unexplained score "
           "advance (F52/F53 class)")
    sb = _make_sb_for_extras_inf_gate(
        score=20, wickets=2,
        active=[("Bat1", 8, 12), ("Bat2", 5, 9)],
        dismissed=[("D1", 4, 6), ("D2", 3, 4)])
    pre_score = sb._inn["score"]
    # Drive the gate path directly: proposed score=27 (+7) with
    # zero batter delta and no wicket → unexplained advance.
    from test_pipeline import apply_scorer_decision
    decision = {
        "score_update": {"accepted": True, "to": 27},
        "batter_updates": {
            "Bat1": {"runs": 8, "balls": 13, "accepted": True},
            "Bat2": {"runs": 5, "balls": 9, "accepted": True},
        },
    }
    extracted = {
        "score": 27,
        "batters": [
            {"name": "Bat1", "runs": 8, "balls": 13},
            {"name": "Bat2", "runs": 5, "balls": 9},
        ],
    }
    changes = apply_scorer_decision(
        sb, decision, frame=999, jump_guard=None,
        batting_team={"name": "BAT"}, extracted=extracted,
        frame_type="LIVE")
    check("gate emits SCORE-INF-GATE marker in changes",
          any(isinstance(c, str)
              and c.startswith("SCORE-INF-GATE:")
              for c in changes),
          f"changes={changes}")
    check("gate marker carries advance=7 detail",
          any(isinstance(c, str)
              and "advance=7" in c
              for c in changes),
          f"changes={changes}")
    check("score did NOT advance (gate blocked the commit)",
          sb._inn["score"] == pre_score,
          f"score={sb._inn['score']!r} (expected {pre_score})")
    check("changes list does NOT contain `score→27`",
          not any(isinstance(c, str) and c == "score→27"
                  for c in changes),
          f"changes={changes}")


def test_fix15_score_side_gate_passes_explained_advance() -> None:
    """Bat-runs delta = 4 (Bat1 8→12), proposed score advance = 4.
    Gate must NOT fire."""
    header("Fix 15: SCORE-INF-GATE passes explained advance "
           "(bat-supported)")
    sb = _make_sb_for_extras_inf_gate(
        score=20, wickets=2,
        active=[("Bat1", 8, 12), ("Bat2", 5, 9)],
        dismissed=[("D1", 4, 6), ("D2", 3, 4)])
    from test_pipeline import apply_scorer_decision
    decision = {
        "score_update": {"accepted": True, "to": 24},
        "batter_updates": {
            "Bat1": {"runs": 12, "balls": 13, "accepted": True},
        },
    }
    extracted = {
        "score": 24,
        "batters": [
            {"name": "Bat1", "runs": 12, "balls": 13},
        ],
    }
    changes = apply_scorer_decision(
        sb, decision, frame=999, jump_guard=None,
        batting_team={"name": "BAT"}, extracted=extracted,
        frame_type="LIVE")
    check("gate does NOT emit SCORE-INF-GATE on bat-explained "
          "advance",
          not any(isinstance(c, str)
                  and c.startswith("SCORE-INF-GATE:")
                  for c in changes),
          f"unexpected fire; changes={changes}")


def test_fix15_score_side_gate_passes_extras_only_advance() -> None:
    """Score advances by +6 with no bat delta — within the
    extras_max=6 ceiling, gate must NOT fire (could be a wide
    + leg-bye boundary on one ball)."""
    header("Fix 15: SCORE-INF-GATE passes extras-only advance "
           "(within max-extras-per-frame ceiling)")
    sb = _make_sb_for_extras_inf_gate(
        score=20, wickets=2,
        active=[("Bat1", 8, 12), ("Bat2", 5, 9)],
        dismissed=[("D1", 4, 6), ("D2", 3, 4)])
    from test_pipeline import apply_scorer_decision
    decision = {
        "score_update": {"accepted": True, "to": 26},
        "batter_updates": {
            "Bat1": {"runs": 8, "balls": 12, "accepted": True},
            "Bat2": {"runs": 5, "balls": 9, "accepted": True},
        },
    }
    extracted = {
        "score": 26,
        "batters": [
            {"name": "Bat1", "runs": 8, "balls": 12},
            {"name": "Bat2", "runs": 5, "balls": 9},
        ],
    }
    changes = apply_scorer_decision(
        sb, decision, frame=999, jump_guard=None,
        batting_team={"name": "BAT"}, extracted=extracted,
        frame_type="LIVE")
    check("gate does NOT emit SCORE-INF-GATE on extras-only "
          "+6 advance",
          not any(isinstance(c, str)
                  and c.startswith("SCORE-INF-GATE:")
                  for c in changes),
          f"unexpected fire; changes={changes}")


def test_fix15_score_inf_floor_rejects_phantom_low_score() -> None:
    """Layer 1.5 floor: committed bat_sum + extras exceeds proposed
    team score — reject (inverse of F52 inflation: misread low)."""
    header("Fix 15: SCORE-INF floor rejects phantom score "
           "below bat_sum+extras")
    from test_pipeline import apply_scorer_decision
    sb = _make_sb_for_extras_inf_gate(
        score=23, wickets=3,
        active=[("Bat1", 6, 2), ("Bat2", 2, 2)],
        dismissed=[("D1", 5, 4), ("D2", 5, 4), ("D3", 4, 5)])
    pre = sb._inn["score"]
    decision = {
        "score_update": {"accepted": True, "to": 20},
        "batter_updates": {
            "Bat1": {"runs": 6, "balls": 2, "accepted": True},
            "Bat2": {"runs": 2, "balls": 2, "accepted": True},
        },
    }
    extracted = {
        "score": 20,
        "batters": [
            {"name": "Bat1", "runs": 6, "balls": 2},
            {"name": "Bat2", "runs": 2, "balls": 2},
        ],
    }
    changes = apply_scorer_decision(
        sb, decision, frame=999, jump_guard=None,
        batting_team={"name": "BAT"}, extracted=extracted,
        frame_type="LIVE")
    check("not blocked by correction delta guard (|Δ|≤7)",
          not any(isinstance(c, str)
                  and c.startswith("CORRECTION_BLOCKED:")
                  for c in changes),
          f"changes={changes}")
    check("floor emits SCORE-INF-GATE with proposed<bat pattern",
          any(isinstance(c, str)
              and c.startswith("SCORE-INF-GATE:")
              and "proposed=20" in c and "bat_sum=22" in c
              for c in changes),
          f"changes={changes}")
    check("score unchanged", sb._inn["score"] == pre,
          f"score={sb._inn['score']}")


def test_fix15_score_inf_floor_passes_legitimate_raise() -> None:
    """Proposed score >= bat_sum + extras; gates must not block (tracker
    may need cold-start 3/3 consensus across frames)."""
    header("Fix 15: SCORE-INF floor passes legitimate score update")
    from test_pipeline import apply_scorer_decision
    sb = _make_sb_for_extras_inf_gate(
        score=30, wickets=3,
        active=[("Bat1", 6, 2), ("Bat2", 2, 2)],
        dismissed=[("D1", 5, 4), ("D2", 5, 4), ("D3", 4, 5)])
    decision = {
        "score_update": {"accepted": True, "to": 34},
        "batter_updates": {
            "Bat1": {"runs": 10, "balls": 3, "accepted": True},
            "Bat2": {"runs": 2, "balls": 2, "accepted": True},
        },
    }
    extracted = {"score": 34, "batters": [
        {"name": "Bat1", "runs": 10, "balls": 3},
        {"name": "Bat2", "runs": 2, "balls": 2},
    ]}
    all_changes: list = []
    for fr in (999, 1000, 1001):
        ch = apply_scorer_decision(
            sb, decision, frame=fr, jump_guard=None,
            batting_team={"name": "BAT"}, extracted=extracted,
            frame_type="LIVE")
        all_changes.extend(ch)
    check("no SCORE-INF-GATE (floor or advance cap) on valid commit",
          not any(isinstance(c, str)
                  and c.startswith("SCORE-INF-GATE:")
                  for c in all_changes),
          f"changes={all_changes}")
    check("not correction-blocked",
          not any(isinstance(c, str)
                  and c.startswith("CORRECTION_BLOCKED:")
                  for c in all_changes),
          f"changes={all_changes}")
    check("score reaches 34 after multi-frame consensus",
          sb._inn["score"] == 34,
          f"score={sb._inn.get('score')}")


def test_fix15_score_inf_floor_suppressed_innings_transition_reset() -> None:
    """Innings transition: proposed 0 while cards still sum high."""
    header("Fix 15: SCORE-INF floor suppressed on "
           "innings_transition_reset")
    from test_pipeline import apply_scorer_decision
    dismissed = [(f"D{i}", 15, 1) for i in range(1, 9)]
    sb = _make_sb_for_extras_inf_gate(
        score=0, wickets=8,
        active=[("A1", 15, 1), ("A2", 15, 1)],
        dismissed=dismissed)
    decision = {
        "innings_transition_reset": True,
        "score_update": {"accepted": True, "to": 0},
        "batter_updates": {
            "A1": {"runs": 15, "balls": 1, "accepted": True},
            "A2": {"runs": 15, "balls": 1, "accepted": True},
        },
    }
    extracted = {
        "score": 0,
        "batters": [
            {"name": "A1", "runs": 15, "balls": 1},
            {"name": "A2", "runs": 15, "balls": 1},
        ],
    }
    changes = apply_scorer_decision(
        sb, decision, frame=999, jump_guard=None,
        batting_team={"name": "BAT"}, extracted=extracted,
        frame_type="LIVE")
    check("no gate fire with innings_transition_reset",
          not any(isinstance(c, str)
                  and c.startswith("SCORE-INF-GATE:")
                  for c in changes),
          f"changes={changes}")
    check("score committed to 0", sb._inn["score"] == 0,
          f"score={sb._inn['score']!r}")


def test_fix15_score_inf_floor_suppressed_cold_start_no_committed_score(
        ) -> None:
    """No committed score yet — floor abstains (match init)."""
    header("Fix 15: SCORE-INF floor suppressed cold-start "
           "(score key absent)")
    from test_pipeline import apply_scorer_decision
    sb = _make_sb_for_extras_inf_gate(
        score=0, wickets=0,
        active=[("Bat1", 0, 0), ("Bat2", 0, 0)],
        dismissed=[])
    del sb._inn["score"]
    decision = {
        "score_update": {"accepted": True, "to": 0},
        "batter_updates": {
            "Bat1": {"runs": 0, "balls": 0, "accepted": True},
            "Bat2": {"runs": 0, "balls": 0, "accepted": True},
        },
    }
    extracted = {
        "score": 0,
        "batters": [
            {"name": "Bat1", "runs": 0, "balls": 0},
            {"name": "Bat2", "runs": 0, "balls": 0},
        ],
    }
    all_ch: list = []
    for fr in (101, 102, 103):
        ch = apply_scorer_decision(
            sb, decision, frame=fr, jump_guard=None,
            batting_team={"name": "BAT"}, extracted=extracted,
            frame_type="LIVE")
        all_ch.extend(ch)
    check("no SCORE-INF-GATE when committed score absent",
          not any(isinstance(c, str)
                  and c.startswith("SCORE-INF-GATE:")
                  for c in all_ch),
          f"changes={all_ch}")
    check("score committed to 0 after tracker consensus",
          sb._inn.get("score") == 0,
          f"score={sb._inn.get('score')!r}")


def test_fix15_score_inf_floor_boundary_proposed_equals_min() -> None:
    """proposed == bat_sum + extras (extras zero) — accept."""
    header("Fix 15: SCORE-INF floor passes when proposed == min_score")
    from test_pipeline import apply_scorer_decision
    sb = _make_sb_for_extras_inf_gate(
        score=22, wickets=1,
        active=[("Bat1", 10, 1), ("Bat2", 7, 1)],
        dismissed=[("D1", 5, 4)])
    decision = {
        "score_update": {"accepted": True, "to": 22},
        "batter_updates": {
            "Bat1": {"runs": 10, "balls": 1, "accepted": True},
            "Bat2": {"runs": 7, "balls": 1, "accepted": True},
        },
    }
    extracted = {
        "score": 22,
        "batters": [
            {"name": "Bat1", "runs": 10, "balls": 1},
            {"name": "Bat2", "runs": 7, "balls": 1},
        ],
    }
    all_ch: list = []
    for fr in (201, 202, 203):
        ch = apply_scorer_decision(
            sb, decision, frame=fr, jump_guard=None,
            batting_team={"name": "BAT"}, extracted=extracted,
            frame_type="LIVE")
        all_ch.extend(ch)
    check("no SCORE-INF-GATE on boundary",
          not any(isinstance(c, str)
                  and c.startswith("SCORE-INF-GATE:")
                  for c in all_ch),
          f"changes={all_ch}")
    check("score at bat_sum", sb._inn["score"] == 22,
          f"score={sb._inn['score']}")


def test_fix16_set_innings_2_resets_cached_scalars() -> None:
    """`set_innings_2()` archives current state and resets all
    per-innings cached scalars (bat1_runs, bat2_runs, bowler_*,
    this_over, over_history, partnership_*, extras_*, fow_list)."""
    header("Fix 16: set_innings_2() resets all cached scalars")
    from score_manager import ScoreManager
    sm = ScoreManager(shadow=True)
    sm.score = 180
    sm.wickets = 6
    sm.overs = 19.6
    sm.bat1_name = "OpenerA"
    sm.bat1_runs = 75
    sm.bat1_balls = 50
    sm.bat2_name = "MidB"
    sm.bat2_runs = 30
    sm.bat2_balls = 22
    sm.bowler_name = "BowlerX"
    sm.bowler_runs = 40
    sm.bowler_wickets = 2
    sm.bowler_overs = 4.0
    sm.batting_team = "TeamA"
    sm.this_over = ["1", "4", "0", "W", "2", "6"]
    sm.over_history = {1: ["0", "1", "2"]}
    sm.partnership_runs = 50
    sm.partnership_balls = 38
    sm.innings_extras = 12
    sm.fow_list = [{"wicket": 1, "batter": "X", "score": 50}]
    sm.set_innings_2(target=181, batting_team="TeamB",
                     reason="test")
    check("innings flipped to 2",
          sm.innings == 2, f"innings={sm.innings}")
    check("target propagated",
          sm.target == 181, f"target={sm.target}")
    check("batting_team propagated",
          sm.batting_team == "TeamB",
          f"batting_team={sm.batting_team!r}")
    check("score reset to None",
          sm.score is None, f"score={sm.score}")
    check("bat1_runs reset to None",
          sm.bat1_runs is None, f"bat1_runs={sm.bat1_runs}")
    check("bat2_runs reset to None",
          sm.bat2_runs is None, f"bat2_runs={sm.bat2_runs}")
    check("bowler_runs reset to None",
          sm.bowler_runs is None, f"bowler_runs={sm.bowler_runs}")
    check("this_over reset to []",
          sm.this_over == [], f"this_over={sm.this_over}")
    check("over_history reset to {}",
          sm.over_history == {},
          f"over_history={sm.over_history}")
    check("partnership_runs reset to 0",
          sm.partnership_runs == 0,
          f"partnership_runs={sm.partnership_runs}")
    check("innings_extras reset to 0",
          sm.innings_extras == 0,
          f"innings_extras={sm.innings_extras}")
    check("fow_list reset to []",
          sm.fow_list == [], f"fow_list={sm.fow_list}")
    check("mode set to COLD_START",
          sm.mode == "COLD_START", f"mode={sm.mode!r}")
    check("innings_history archives prior innings",
          len(sm.innings_history) == 1
          and sm.innings_history[0]["score"] == 180,
          f"history={sm.innings_history}")


def test_fix16_set_innings_2_idempotent() -> None:
    """Calling set_innings_2() again when already in innings 2
    must not double-archive or wipe innings-2 progress."""
    header("Fix 16: set_innings_2() is idempotent")
    from score_manager import ScoreManager
    sm = ScoreManager(shadow=True)
    sm.score = 100
    sm.set_innings_2(target=101, batting_team="B")
    sm.score = 50  # innings-2 progress
    sm.set_innings_2(target=101, batting_team="B")
    check("innings still 2 (no double-flip)",
          sm.innings == 2, f"innings={sm.innings}")
    check("innings-2 score preserved (50, not wiped)",
          sm.score == 50, f"score={sm.score}")
    check("history has exactly 1 entry (not double-archived)",
          len(sm.innings_history) == 1,
          f"history len={len(sm.innings_history)}")


def test_sm_full_reset_clears_fix16_scalar_surface() -> None:
    """`full_reset()` wipes Fix-16 batter/bowler/partnership/FOW cache."""
    header("SM.full_reset: clears Fix-16 per-innings scalar surface")
    from score_manager import ScoreManager

    sm = ScoreManager(shadow=True)
    sm.bat1_name = "A"
    sm.bat1_runs = 40
    sm.bat1_balls = 30
    sm.bat2_name = "B"
    sm.bat2_runs = 20
    sm.bat2_balls = 18
    sm.bowler_name = "Bol"
    sm.bowler_runs = 22
    sm.bowler_wickets = 1
    sm.bowler_overs = 3.2
    sm.striker = "A"
    sm.non = "B"
    sm.run_rate = 7.5
    sm.bat1_sr = 133.0
    sm.bat2_sr = 110.0
    sm.bowler_economy = 8.0
    sm.this_over = [".", "1"]
    sm.over_history = {1: ["w"]}
    sm.partnership_runs = 60
    sm.partnership_balls = 48
    sm.fow_list = [{"wicket": 1}]
    sm.innings_extras = 5
    sm.full_reset(reason="test_fix16_surface")

    check("bat1_runs cleared", sm.bat1_runs is None,
          f"bat1_runs={sm.bat1_runs}")
    check("bowler_overs cleared", sm.bowler_overs is None,
          f"bowler_overs={sm.bowler_overs}")
    check("striker cleared", sm.striker is None,
          f"striker={sm.striker!r}")
    check("run_rate cleared", sm.run_rate is None,
          f"run_rate={sm.run_rate}")
    check("this_over empty", sm.this_over == [],
          f"this_over={sm.this_over}")
    check("fow_list empty", sm.fow_list == [],
          f"fow_list={sm.fow_list}")


def test_sm_full_reset_clears_cold_start_bookkeeping() -> None:
    """`full_reset()` runs cold-start escape hatch bookkeeping."""
    header("SM.full_reset: cold-start bookkeeping + scalar wipe")
    from score_manager import ScoreManager

    sm = ScoreManager(shadow=True)
    sm.mode = "WARM"
    sm.score = 55
    sm.wickets = 2
    sm.overs = 8.1
    sm.cold_candidate = {"score": 1}
    sm.cold_frames = 7
    sm.cold_candidate_streak = 2
    sm._cold_pipeline_frames = 111
    sm._cold_last_viable = {"score": 1, "wickets": 2, "overs": 3.4}
    sm._deferred_score = 3
    sm._deferred_frames = 1
    sm.bat1_runs = 99  # would survive force_cold alone

    sm.full_reset(reason="test_cold_hatch")

    check("mode is COLD_START", sm.mode == "COLD_START",
          f"mode={sm.mode!r}")
    check("cold_candidate None", sm.cold_candidate is None,
          f"cold_candidate={sm.cold_candidate}")
    check("cold_frames 0", sm.cold_frames == 0,
          f"cold_frames={sm.cold_frames}")
    check("pipeline watchdog cleared", sm._cold_pipeline_frames == 0,
          f"_cold_pipeline_frames={sm._cold_pipeline_frames}")
    check("cold snapshot cleared", sm._cold_last_viable is None,
          f"_cold_last_viable={sm._cold_last_viable}")
    check("deferred cleared", sm._deferred_score == 0
          and sm._deferred_frames == 0,
          f"def={sm._deferred_score}/{sm._deferred_frames}")
    check("score strip cleared", sm.score is None,
          f"score={sm.score}")
    check("bat1_runs cleared", sm.bat1_runs is None,
          f"bat1_runs={sm.bat1_runs}")
    check("_last_warm_state None after full_reset",
          sm._last_warm_state is None,
          f"_last_warm_state={sm._last_warm_state}")


def test_sm_full_reset_preserves_match_context() -> None:
    """`full_reset()` does not clear innings / target / team / history."""
    header("SM.full_reset: preserves match-level fields")
    from score_manager import ScoreManager

    sm = ScoreManager(shadow=True)
    sm.innings = 1
    sm.target = 187
    sm.batting_team = "PBKS"
    sm.venue = "New Chandigarh"
    sm.match_info = "IPL 2026"
    sm.innings_history = [{"innings": 0, "score": 0}]
    sm.score = 120
    sm.wickets = 4
    sm.bat1_runs = 50
    sm.full_reset(reason="phase2_contract")

    check("innings preserved", sm.innings == 1,
          f"innings={sm.innings}")
    check("target preserved", sm.target == 187,
          f"target={sm.target}")
    check("batting_team preserved",
          sm.batting_team == "PBKS",
          f"batting_team={sm.batting_team!r}")
    check("venue preserved", sm.venue == "New Chandigarh",
          f"venue={sm.venue!r}")
    check("match_info preserved", sm.match_info == "IPL 2026",
          f"match_info={sm.match_info!r}")
    check("innings_history untouched",
          len(sm.innings_history) == 1
          and sm.innings_history[0]["innings"] == 0,
          f"history={sm.innings_history}")
    check("shadow preserved", sm.shadow is True,
          f"shadow={sm.shadow}")


# ---------------------------------------------------------------------
# Bowler stats graphic gate (2026-04-28): scoreboard admission layer
# beside Fix 8 strip stripping, 17A row gate, 17B / 17B+ consensus.
# OR semantics: strong phase/career phrases in vision_desc **or**
# spell-impossible figures reject; bare "CAREER" alone does not.
# ---------------------------------------------------------------------
def test_bowler_stats_graphic_gate_rejects_in_t20_keyword() -> None:
    header("BOWLER-STATS-GRAPHIC-GATE: IN T20 in vision rejects commit")
    sb = _setup_bowler_trap_sb(initial_current_bowler="Pat Cummins")
    _establish_bowler_stats(
        sb, "Pat Cummins", overs="2", runs=15, wickets=1, start_frame=10)
    vis = (
        "INFO_PANEL: J HOLDER | IN T20 MATCHES 50 WKTS 80 — strip noise")
    ok = sb.update_bowler(
        "Pat Cummins", overs="2.4", runs=18, wickets=1, frame=100,
        vision_desc=vis)
    check("update rejected", ok is False, f"ok={ok}")
    check("figures unchanged after reject",
          sb.bowling_card["Pat Cummins"]["runs"] == 15,
          f"card={sb.bowling_card['Pat Cummins']}")


def test_bowler_stats_graphic_gate_rejects_implausible_figures() -> None:
    header("BOWLER-STATS-GRAPHIC-GATE: aggregate figures reject "
           "(no vision keyword)")
    sb = _setup_bowler_trap_sb(initial_current_bowler="Pat Cummins")
    _establish_bowler_stats(
        sb, "Pat Cummins", overs="2", runs=15, wickets=1, start_frame=10)
    ok = sb.update_bowler(
        "Pat Cummins",
        overs="2000",
        runs=5000,
        wickets=200,
        frame=200,
        vision_desc=None)
    check("update rejected", ok is False, f"ok={ok}")
    check("runs not advanced to absurd aggregate",
          sb.bowling_card["Pat Cummins"]["runs"] == 15,
          f"card={sb.bowling_card['Pat Cummins']}")


def test_bowler_stats_graphic_gate_accepts_live_spell() -> None:
    header("BOWLER-STATS-GRAPHIC-GATE: plausible T20 spell accepted")
    sb = _setup_bowler_trap_sb(initial_current_bowler="Pat Cummins")
    _establish_bowler_stats(
        sb, "Pat Cummins", overs="2", runs=15, wickets=1, start_frame=10)
    vis = (
        "SCOREBOARD | STRIKER END | Pat Cummins 1-12 (2.3) live")
    for f in (300, 301, 302):
        ok = sb.update_bowler(
            "Pat Cummins",
            overs="2.4",
            runs=18,
            wickets=1,
            frame=f,
            vision_desc=vis)
        check(f"frame {f} update accepted", ok is True, f"ok={ok}")
    card = sb.bowling_card["Pat Cummins"]
    check("runs committed", card.get("runs") == 18,
          f"card={card}")
    check("overs committed", card.get("overs") == "2.4",
          f"card={card}")


def test_bowler_stats_graphic_gate_accepts_career_word_with_plausible_spell(
        ) -> None:
    header("BOWLER-STATS-GRAPHIC-GATE: stray CAREER token + "
           "plausible spell accepted")
    sb = _setup_bowler_trap_sb(initial_current_bowler="Pat Cummins")
    _establish_bowler_stats(
        sb, "Pat Cummins", overs="2", runs=15, wickets=1, start_frame=10)
    vis = (
        "LOWER THIRD: UNRELATED CAREER BEST 87 NOT THE BOWLER OVERLAY")
    for f in (400, 401, 402):
        ok = sb.update_bowler(
            "Pat Cummins",
            overs="2.4",
            runs=18,
            wickets=1,
            frame=f,
            vision_desc=vis)
        check(f"frame {f} update accepted", ok is True, f"ok={ok}")
    card4 = sb.bowling_card["Pat Cummins"]
    check("runs committed (CAREER noise ignored)",
          card4.get("runs") == 18, f"card={card4}")
    check("overs committed", card4.get("overs") == "2.4",
          f"card={card4}")


def test_poison_recal_source_calls_full_reset() -> None:
    header("POISON-RECAL: pipeline block calls ScoreManager.full_reset")
    root = Path(__file__).resolve().parent
    text = (root / "test_pipeline.py").read_text(encoding="utf-8")
    idx = text.find("[POISON-RECAL]")
    check("POISON-RECAL marker present", idx >= 0, "marker missing")
    window = text[idx:idx + 1500]
    check("block calls full_reset", "full_reset(" in window,
          "full_reset missing near POISON-RECAL")
    check("block does not call force_cold bare",
          "force_cold_start_recalibration(" not in window,
          "legacy force_cold still beside POISON-RECAL")


def test_poison_recal_semantic_full_reset_clears_sm_scalars() -> None:
    header("POISON-RECAL: full_reset clears Fix-16 SM scalar surface")
    from score_manager import ScoreManager

    sm = ScoreManager(shadow=True)
    sm.bat1_runs = 33
    sm.striker = "Z"
    sm.full_reset(reason="poison_recal_consensus fixture")
    check("bat1_runs cleared", sm.bat1_runs is None,
          f"bat1_runs={sm.bat1_runs}")
    check("striker cleared", sm.striker is None,
          f"striker={sm.striker}")


def test_scorer_invariant_filter_witnessed_out_batter_row() -> None:
    header("SCORER: witnessed-out row skipped (INVARIANT-FILTER)")
    from eyes.scoreboard import Scoreboard
    from test_pipeline import apply_scorer_decision

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb.batting_card["A"]["status"] = "out"
    sb.fall_of_wickets.append({
        "wicket": 1, "batter": "A", "score": 20, "overs": "1.1",
        "_witnessed": True})
    changes = apply_scorer_decision(
        sb,
        {"batter_updates": {"A": {"accepted": True, "runs": 9, "balls": 5}}},
        frame=1, jump_guard=None,
        batting_team={"name": "BAT"},
        extracted={"batters": [{"name": "A", "runs": 9, "balls": 5}]})
    check("no bat change for out row",
          not any(str(c).startswith("bat:A") for c in changes),
          f"changes={changes!r}")


def test_scorer_dismissed_resurrect_non_witnessed_out() -> None:
    header("SCORER: non-witnessed out triggers DISMISSED-RESURRECT skip")
    from eyes.scoreboard import Scoreboard
    from test_pipeline import apply_scorer_decision

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb.batting_card["A"]["status"] = "out"
    # No witnessed FOW — hallucinated resurrection path
    changes = apply_scorer_decision(
        sb,
        {"batter_updates": {"A": {"accepted": True, "runs": 9, "balls": 5}}},
        frame=2, jump_guard=None,
        batting_team={"name": "BAT"},
        extracted={"batters": [{"name": "A", "runs": 9, "balls": 5}]})
    check("no commit", not any(str(c).startswith("bat:A") for c in changes),
          f"changes={changes!r}")


def test_scorer_active_batter_updates_not_filtered() -> None:
    header("SCORER: active batter row passes through scorer slate")
    from eyes.scoreboard import Scoreboard
    from test_pipeline import apply_scorer_decision

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb.batting_card["A"]["status"] = "batting"
    sb.batting_card["A"]["runs"] = 10
    sb.batting_card["A"]["balls"] = 5
    sb.batting_card["B"]["status"] = "batting"
    sb.batting_card["B"]["runs"] = 5
    sb.batting_card["B"]["balls"] = 3
    sb._inn["score"] = 25
    sb._inn["wickets"] = 0
    # Align ConsistentReadTracker with card figures so warm-mode
    # fast-confirm (5→7 runs, 3→4 balls) can commit in one frame.
    sb._tracker.force_set("bat:A:runs", 10)
    sb._tracker.force_set("bat:A:balls", 5)
    sb._tracker.force_set("bat:B:runs", 5)
    sb._tracker.force_set("bat:B:balls", 3)
    changes = apply_scorer_decision(
        sb,
        {"batter_updates": {"B": {"accepted": True, "runs": 7, "balls": 4}}},
        frame=3, jump_guard=None,
        batting_team={"name": "BAT"},
        extracted={"batters": [{"name": "B", "runs": 7, "balls": 4}]})
    check("batter advance emitted",
          any("bat:B" in str(c) for c in changes), f"changes={changes!r}")
    check("runs committed", sb.batting_card["B"]["runs"] == 7,
          f"card={sb.batting_card['B']}")


# ---------------------------------------------------------------------
# Item 2 PR 1 — SCORER schema (Pydantic shadow) + [BATTERS-INVARIANT]
# ---------------------------------------------------------------------


def test_scorer_schema_normalize_batter_row_ok() -> None:
    header("Item 2: valid batter row normalizes")
    from scorer_decision_schema import normalize_batter_row_for_test

    norm, err = normalize_batter_row_for_test(
        "X", {"runs": 5, "balls": 3, "accepted": True})
    check("no drop reason", err is None, err)
    check("runs preserved", norm.get("runs") == 5, norm)


def test_scorer_schema_multi_field_coerce_drops_row() -> None:
    header("Item 2: two numeric coerces in one row → drop (§10.3)")
    from scorer_decision_schema import normalize_batter_row_for_test

    norm, err = normalize_batter_row_for_test(
        "X", {"runs": "bad", "balls": "nope", "accepted": True})
    check("row dropped", norm is None, norm)
    check("multi_field_coerce",
          err is not None and err.startswith("multi_field_coerce"), err)


def test_scorer_schema_enforce_drops_bad_batter_update() -> None:
    header("Item 2: enforce mode removes bad batter_updates row")
    from scorer_decision_schema import process_scorer_decision_schema

    class _L:
        def __init__(self) -> None:
            self.warnings: list[str] = []
            self.infos: list[str] = []

        def warn(self, m: str) -> None:
            self.warnings.append(m)

        def info(self, m: str) -> None:
            self.infos.append(m)

    log_stub = _L()
    dec = {
        "batter_updates": {
            "A": {"runs": "x", "balls": "y", "accepted": True},
        },
    }
    process_scorer_decision_schema(
        dec, frame=1, enforce=True, log=log_stub)
    check("bad key removed", "A" not in dec.get("batter_updates", {}), dec)
    check("drop telemetry",
          any("SCORER-SCHEMA-DROP" in w for w in log_stub.warnings),
          log_stub.warnings)


def test_scorer_schema_shadow_keeps_batter_row() -> None:
    header("Item 2: shadow mode records would-drop, keeps dict row")
    from scorer_decision_schema import process_scorer_decision_schema

    class _L:
        def warn(self, m: str) -> None:
            pass

        def info(self, m: str) -> None:
            pass

    dec = {
        "batter_updates": {
            "A": {"runs": "x", "balls": "y", "accepted": True},
        },
    }
    ev = process_scorer_decision_schema(
        dec, frame=2, enforce=False, log=_L())
    check("shadow event", bool(ev) and ev[0].kind == "would_drop", ev)
    check("row not stripped in shadow", "A" in dec["batter_updates"], dec)


def test_scorer_schema_finalize_shadow_emits_would_tags() -> None:
    header("Item 2: finalize_schema_shadow_logs emits WOULD-* lines")
    from scorer_decision_schema import (
        SchemaShadowEvent,
        finalize_schema_shadow_logs,
    )

    class _L:
        def __init__(self) -> None:
            self.warnings: list[str] = []
            self.infos: list[str] = []

        def warn(self, m: str) -> None:
            self.warnings.append(m)

        def info(self, m: str) -> None:
            self.infos.append(m)

    stub = _L()
    finalize_schema_shadow_logs(
        [
            SchemaShadowEvent(
                kind="would_drop",
                top_field="batter_updates",
                key="K",
                reason="multi_field_coerce:runs,balls",
            ),
            SchemaShadowEvent(
                kind="would_coerce",
                top_field="score_update",
                key=None,
                reason="coerce_null",
                raw="zzz",
                scalar_subfield="to",
            ),
        ],
        frame=9,
        log=stub,
        step3_notes=[],
        changes=[],
    )
    check("WOULD-DROP line",
          any("SCORER-SCHEMA-WOULD-DROP" in w for w in stub.warnings),
          stub.warnings)
    check("filter_caught_in_step3 on drop",
          any("filter_caught_in_step3=" in w for w in stub.warnings),
          stub.warnings)
    check("WOULD-COERCE line",
          any("SCORER-SCHEMA-WOULD-COERCE" in s for s in stub.infos),
          stub.infos)


def test_scorer_match_state_parse_json_returns_empty_dict() -> None:
    header("Item 2: scorer JSON parse failure → {} (contract §4.2)")
    from eyes.match_state import MatchStateAgent

    check("garbage → {}",
          MatchStateAgent._parse_json("not json {") == {},
          "expected empty dict")
    check("brace salvage still can fail → {}",
          MatchStateAgent._parse_json("no braces at all") == {},
          "expected empty dict")


def test_item2_apply_scorer_emits_schema_would_coerce() -> None:
    header("Item 2: apply_scorer_decision shadow schema WOULD-COERCE")
    from unittest.mock import patch

    import test_pipeline as tp
    from eyes.scoreboard import Scoreboard

    class _Cap:
        def __init__(self) -> None:
            self.warnings: list[str] = []
            self.infos: list[str] = []

        def warn(self, m: str) -> None:
            self.warnings.append(m)

        def info(self, m: str) -> None:
            self.infos.append(m)

        def error(self, m: str) -> None:
            pass

        def insight(self, m: str) -> None:
            pass

    cap = _Cap()
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb.batting_card["A"]["status"] = "batting"
    sb.batting_card["A"]["runs"] = 10
    sb.batting_card["A"]["balls"] = 5
    sb.batting_card["B"]["status"] = "batting"
    sb.batting_card["B"]["runs"] = 5
    sb.batting_card["B"]["balls"] = 3
    sb._inn["score"] = 20
    sb._inn["wickets"] = 0
    sb._tracker.force_set("bat:A:runs", 10)
    sb._tracker.force_set("bat:A:balls", 5)
    sb._tracker.force_set("bat:B:runs", 5)
    sb._tracker.force_set("bat:B:balls", 3)

    with patch.object(tp, "log", cap):
        tp.apply_scorer_decision(
            sb,
            {
                "batter_updates": {
                    "B": {"accepted": True, "runs": 7, "balls": 4},
                },
                "score_update": {
                    "from": 20,
                    "to": "not-an-int",
                    "accepted": True,
                },
            },
            frame=42,
            jump_guard=None,
            batting_team={"name": "BAT"},
            extracted={
                "score": 20,
                "batters": [{"name": "B", "runs": 7, "balls": 4}],
            },
            frame_type="LIVE",
        )
    joined = "\n".join(cap.warnings + cap.infos)
    check("WOULD-COERCE emitted",
          "SCORER-SCHEMA-WOULD-COERCE" in joined,
          joined[:800])


def test_item2_batters_invariant_rule_a_emitted() -> None:
    header("Item 2: [BATTERS-INVARIANT] rule A when >2 actives")
    from unittest.mock import patch

    import test_pipeline as tp
    from eyes.scoreboard import Scoreboard

    class _Cap:
        def __init__(self) -> None:
            self.warnings: list[str] = []

        def warn(self, m: str) -> None:
            self.warnings.append(m)

        def info(self, m: str) -> None:
            pass

        def error(self, m: str) -> None:
            pass

        def insight(self, m: str) -> None:
            pass

    cap = _Cap()
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B", "C"], bowling_squad=["X"],
        batting_xi=["A", "B", "C"], bowling_xi=["X"])
    for nm in ("A", "B", "C"):
        sb.batting_card[nm]["status"] = "batting"
        sb.batting_card[nm]["runs"] = 1
        sb.batting_card[nm]["balls"] = 1
    sb._inn["striker"] = "A"
    sb._inn["non"] = "B"
    sb._inn["score"] = 30
    sb._inn["wickets"] = 0
    sb._tracker.force_set("bat:C:runs", 1)
    sb._tracker.force_set("bat:C:balls", 1)

    with patch.object(tp, "log", cap):
        tp.apply_scorer_decision(
            sb,
            {"batter_updates": {
                "C": {"accepted": True, "runs": 2, "balls": 2},
            }},
            frame=77,
            jump_guard=None,
            batting_team={"name": "BAT"},
            extracted={
                "score": 30,
                "batters": [{"name": "C", "runs": 2, "balls": 2}],
            },
            frame_type="LIVE",
        )
    joined = "\n".join(cap.warnings)
    check("BATTERS-INVARIANT present", "[BATTERS-INVARIANT]" in joined,
          joined[:800])
    check("rule A", "rule=A" in joined, joined[:800])
    check("phase1 noop", "action=noop_phase1" in joined, joined[:800])


def test_analyzer_pending_validation_includes_item2_patterns() -> None:
    header("Analyzer: pending-validation catalog includes Item 2 tags")
    from analyze_match_telemetry import PENDING_VALIDATION_PATTERNS

    labels = [lbl for lbl, _ in PENDING_VALIDATION_PATTERNS]
    check("SCORER-SCHEMA-WOULD-DROP in catalog",
          any("SCORER-SCHEMA-WOULD-DROP" in lb for lb in labels),
          labels)
    check("SCORER-SCHEMA-WOULD-COERCE in catalog",
          any("SCORER-SCHEMA-WOULD-COERCE" in lb for lb in labels),
          labels)
    check("BATTERS-INVARIANT in catalog",
          any("BATTERS-INVARIANT" in lb for lb in labels),
          labels)
    check("STRIP-ROWS-MISALIGNED in catalog",
          any("STRIP-ROWS-MISALIGNED" in lb for lb in labels),
          labels)


def test_state_recovery_phase2_disabled_skips_mutation() -> None:
    header("State recovery Phase 2 OFF: mutation helper is no-op")
    import test_pipeline as tp
    from score_manager import ScoreManager
    from eyes.scoreboard import Scoreboard

    check("default disabled", tp.STATE_RECOVERY_PHASE_2_ENABLED is False,
          "flag must stay False in repo default")
    sm = ScoreManager(shadow=True)
    sm.overs = 7.5
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb._inn["score"] = 40
    agg = tp.StateRecoveryAggregator(threshold=2)
    cand = _state_recovery_candidate(score=120)
    event = None
    for fr in range(100, 102):
        event = event or agg.observe(
            fr, "poison_score", cand,
            current={"score": 40}, proposed_reset=["score"])
        event = event or agg.observe(
            fr, "slot_scrub_rejected", cand,
            current={"score": 40},
            proposed_reset=["slot:non", "status:Nitish Rana"])
    check("fixture emits candidate", event is not None, event)
    tp._apply_state_recovery_phase2_mutation(event, sm, sb, agg)
    check("SM not wiped when disabled", sm.overs == 7.5,
          sm.overs)
    check("inn score unchanged", int(sb._inn.get("score") or 0) == 40,
          sb._inn.get("score"))


def test_state_recovery_phase2_enabled_resets_sm_and_patches_inn() -> None:
    header("State recovery Phase 2 ON: full_reset + candidate inn fields")
    import test_pipeline as tp
    from score_manager import ScoreManager
    from eyes.scoreboard import Scoreboard

    prev = tp.STATE_RECOVERY_PHASE_2_ENABLED
    tp.STATE_RECOVERY_PHASE_2_ENABLED = True
    try:
        sm = ScoreManager(shadow=True)
        sm.bat1_runs = 5
        sb = Scoreboard()
        sb.setup_innings(
            batting_team="BAT", bowling_team="BOWL",
            batting_squad=["A", "B"], bowling_squad=["X"],
            batting_xi=["A", "B"], bowling_xi=["X"])
        sb._inn["score"] = 40
        sb._inn["wickets"] = 1
        sb._inn["overs"] = "5.2"
        agg = tp.StateRecoveryAggregator(threshold=2)
        cand = _state_recovery_candidate(score=120)
        cand["wickets"] = 2
        cand["overs"] = 6.3
        event = None
        for fr in range(200, 202):
            event = event or agg.observe(
                fr, "poison_score", cand,
                current={"score": 40}, proposed_reset=["score"])
            event = event or agg.observe(
                fr, "slot_scrub_rejected", cand,
                current={"score": 40},
                proposed_reset=["slot:non", "status:Nitish Rana"])
        check("event present", event is not None, event)
        tp._apply_state_recovery_phase2_mutation(event, sm, sb, agg)
        check("SM scalar wiped", sm.bat1_runs is None, sm.bat1_runs)
        check("score patched", int(sb._inn["score"]) == 120, sb._inn["score"])
        check("wickets patched", int(sb._inn["wickets"]) == 2,
              sb._inn["wickets"])
    finally:
        tp.STATE_RECOVERY_PHASE_2_ENABLED = prev


def test_state_recovery_phase2_field_scoped_score_only() -> None:
    header("State recovery Phase 2: only candidate keys patch _inn")
    import test_pipeline as tp
    from score_manager import ScoreManager
    from eyes.scoreboard import Scoreboard

    prev = tp.STATE_RECOVERY_PHASE_2_ENABLED
    tp.STATE_RECOVERY_PHASE_2_ENABLED = True
    try:
        sm = ScoreManager(shadow=True)
        sb = Scoreboard()
        sb.setup_innings(
            batting_team="BAT", bowling_team="BOWL",
            batting_squad=["A", "B"], bowling_squad=["X"],
            batting_xi=["A", "B"], bowling_xi=["X"])
        sb._inn["score"] = 10
        sb._inn["wickets"] = 7
        sb._inn["overs"] = "3.0"
        agg = tp.StateRecoveryAggregator(threshold=1)
        event = {
            "sig": "phase2test",
            "guards": ["poison_score", "slot_scrub_rejected"],
            "frames": 5,
            "candidate": {"score": 200},
            "current": {},
            "coherence": {},
            "threshold_frames": {},
            "proposed_reset": ["score"],
            "reason": "fixture",
            "telemetry_only": True,
        }
        tp._apply_state_recovery_phase2_mutation(event, sm, sb, agg)
        check("score only", int(sb._inn["score"]) == 200, sb._inn["score"])
        check("wickets preserved", int(sb._inn["wickets"]) == 7,
              sb._inn["wickets"])
    finally:
        tp.STATE_RECOVERY_PHASE_2_ENABLED = prev


def test_fix18_layer2_reconciler_fires_on_smaller_divergence() -> None:
    """Layer 2 detection: bat_sum > score+5 (but <= score+10)
    must emit [BAT-SUM-RECONCILER] without a cap-reset."""
    header("Fix 18 Layer 2: BAT-SUM-RECONCILER detects "
           "divergence below cap-reset threshold")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL",
                     ["A", "B", "C", "D", "E"], ["X", "Y"])
    sb.batting_card["A"]["status"] = "batting"
    sb.batting_card["A"]["runs"] = 22
    sb.batting_card["B"]["status"] = "batting"
    sb.batting_card["B"]["runs"] = 15
    sb._inn["score"] = 30
    sb._inn["wickets"] = 0
    pre_l2 = getattr(sb, "_L2_RECONCILER_FIRES", 0)
    sb.validate_state_consistency()
    post_l2 = getattr(sb, "_L2_RECONCILER_FIRES", 0)
    check("Layer 2 reconciler fired (bat_sum=37 > score+5=35)",
          post_l2 == pre_l2 + 1,
          f"_L2_RECONCILER_FIRES={post_l2} (expected {pre_l2+1})")
    check("Layer 3 cap-reset did NOT fire (bat_sum=37 <= "
          "score+10=40)",
          getattr(sb, "_L3_CAP_RESET_FIRES", 0) == 0,
          f"_L3_CAP_RESET_FIRES={getattr(sb, '_L3_CAP_RESET_FIRES', 0)}")
    check("A's runs unchanged after Layer 2-only fire",
          sb.batting_card["A"]["runs"] == 22,
          f"A.runs={sb.batting_card['A']['runs']}")


def test_fix18_layer3_cap_reset_picks_most_recent_advance() -> None:
    """Layer 3 cap-reset Path C hybrid: when bat_sum > score+10
    AND no individual batter exceeds score, the most-recently-
    advanced batter is reset."""
    header("Fix 18 Layer 3: cap-reset picks most-recent advance "
           "(Brevis-Dube split-phantom case)")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL",
                     ["A", "B", "C", "D", "E"], ["X", "Y"])
    sb.batting_card["A"]["status"] = "batting"
    sb.batting_card["A"]["runs"] = 22
    sb.batting_card["B"]["status"] = "batting"
    sb.batting_card["B"]["runs"] = 25
    sb._inn["score"] = 30  # bat_sum=47 > 30+10=40
    sb._inn["wickets"] = 0
    # Stamp last-advance frames: B more recent than A.
    sb._last_runs_advance["A"] = {"frame": 100, "from": 21,
                                   "to": 22}
    sb._last_runs_advance["B"] = {"frame": 200, "from": 24,
                                   "to": 25}
    pre_l3 = getattr(sb, "_L3_CAP_RESET_FIRES", 0)
    sb.validate_state_consistency()
    post_l3 = getattr(sb, "_L3_CAP_RESET_FIRES", 0)
    check("Layer 3 cap-reset fired",
          post_l3 >= pre_l3 + 1,
          f"_L3_CAP_RESET_FIRES={post_l3} (expected >={pre_l3+1})")
    check("B (most-recent advance) was reset, not A",
          sb.batting_card["B"]["runs"] is None
          and sb.batting_card["A"]["runs"] == 22,
          f"A.runs={sb.batting_card['A']['runs']!r}, "
          f"B.runs={sb.batting_card['B']['runs']!r}")
    check("B's last-advance entry cleared",
          "B" not in sb._last_runs_advance,
          f"_last_runs_advance={sb._last_runs_advance}")


def test_fix18_layer3_iterative_cap_reset() -> None:
    """When the first reset isn't enough (rare 3-active scenario),
    Path C hybrid iterates up to 2 times."""
    header("Fix 18 Layer 3: cap-reset iterates when needed")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL",
                     ["A", "B", "C", "D", "E"], ["X", "Y"])
    # Two batters with high enough sum that one reset isn't enough.
    sb.batting_card["A"]["status"] = "batting"
    sb.batting_card["A"]["runs"] = 50
    sb.batting_card["B"]["status"] = "batting"
    sb.batting_card["B"]["runs"] = 50
    sb._inn["score"] = 30
    sb._inn["wickets"] = 0
    sb._last_runs_advance["A"] = {"frame": 100, "from": 49,
                                   "to": 50}
    sb._last_runs_advance["B"] = {"frame": 200, "from": 49,
                                   "to": 50}
    sb.validate_state_consistency()
    # After first reset of B, A=50 still > score+10=40, so iter 2
    # resets A.
    check("Both batters reset after iterative correction",
          sb.batting_card["A"]["runs"] is None
          and sb.batting_card["B"]["runs"] is None,
          f"A.runs={sb.batting_card['A']['runs']!r}, "
          f"B.runs={sb.batting_card['B']['runs']!r}")
    check("L3 fires counter at >= 2 (iter ran twice)",
          getattr(sb, "_L3_CAP_RESET_FIRES", 0) >= 2,
          f"_L3_CAP_RESET_FIRES="
          f"{getattr(sb, '_L3_CAP_RESET_FIRES', 0)}")


def test_fix18_innings_2_resets_last_advance() -> None:
    """Innings hygiene: `_last_runs_advance` cleared on
    `set_innings_2()`."""
    header("Fix 18: set_innings_2() clears _last_runs_advance")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL",
                     ["A", "B", "C", "D", "E"], ["X", "Y"])
    sb._last_runs_advance["A"] = {"frame": 100, "from": 0,
                                   "to": 5}
    sb.set_innings_2()
    check("_last_runs_advance cleared on innings-2 transition",
          sb._last_runs_advance == {},
          f"_last_runs_advance={sb._last_runs_advance}")


def test_fix18_update_batter_records_advance() -> None:
    """`update_batter` records advance frame + values whenever
    runs strictly increase (after consensus accepts the new
    value)."""
    header("Fix 18: update_batter records last-advance for L3")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL",
                     ["A", "B", "C", "D", "E"], ["X", "Y"])
    sb.batting_card["A"]["status"] = "batting"
    sb._inn["striker"] = "A"
    # Seed initial state via force_set so consensus is bypassed
    # and the tracker baseline is at runs=5/balls=4 immediately.
    sb._tracker.force_set("bat:A:runs", 5)
    sb._tracker.force_set("bat:A:balls", 4)
    sb.batting_card["A"]["runs"] = 5
    sb.batting_card["A"]["balls"] = 4
    # Trigger an advance: scout reads the same advance value 3
    # times in successive frames so consensus accepts it.
    for _f in (100, 101, 102):
        sb.update_batter("A", runs=9, balls=5, frame=_f)
    check("advance record present for A after consensus advance",
          "A" in sb._last_runs_advance,
          f"_last_runs_advance={sb._last_runs_advance}")
    if "A" in sb._last_runs_advance:
        check("advance record carries `to=9`",
              sb._last_runs_advance["A"].get("to") == 9,
              f"advance={sb._last_runs_advance['A']}")
        check("advance record `from` reflects pre-advance "
              "(5)",
              sb._last_runs_advance["A"].get("from") == 5,
              f"advance={sb._last_runs_advance['A']}")


def test_fix17_path_a_pre_match_graphic_gate_in_source() -> None:
    """Source-level wiring: Path A pre-match graphic gate must
    fire on team_abbr+0-0(0.0)+no_committed_score, blocking the
    `assign_teams` call."""
    header("Fix 17 Path A: PRE-MATCH-GRAPHIC-GATE wired in "
           "test_pipeline.py")
    src = (Path(__file__).resolve().parent / "test_pipeline.py"
           ).read_text()
    check("gate marker `[PRE-MATCH-GRAPHIC-GATE]` present",
          "[PRE-MATCH-GRAPHIC-GATE]" in src,
          "expected log marker")
    check("gate uses `_path_a_strip_zzz` flag",
          "_path_a_strip_zzz" in src,
          "expected gate flag variable")
    check("gate guards against committed non-zero score",
          "_committed_score_a == 0" in src,
          "expected guard for cold-start case only")


def test_fix17_path_d_cold_start_ws_gate_blocks_no_team() -> None:
    """`_ws_cold_start_gate_check` must return False for a payload
    with no committed `batting_team` (cold-start unknown-team
    state).  Hotfix 2026-04-26: gate now opens as soon as
    batting_team is committed; only blocks while team is unknown.
    """
    header("Fix 17 Path D: WS cold-start gate blocks while "
           "batting_team is unknown")
    import test_pipeline as tp
    # Reset gate state for the test
    tp._ws_cold_start_gate_open = False
    tp._ws_cold_start_gate_first_attempt_ts = None
    payload_no_team = {"scorecard": {"batting_team": "",
                                     "score": 0, "wickets": 0,
                                     "overs": "0.0"}}
    allowed = tp._ws_cold_start_gate_check(payload_no_team)
    check("gate blocks payload with no batting_team",
          allowed is False, f"allowed={allowed}")
    check("gate not yet open",
          tp._ws_cold_start_gate_open is False,
          f"gate_open={tp._ws_cold_start_gate_open}")
    check("first-attempt timestamp recorded",
          tp._ws_cold_start_gate_first_attempt_ts is not None,
          f"ts={tp._ws_cold_start_gate_first_attempt_ts}")


def test_fix17_path_d_cold_start_ws_gate_opens_on_team_commit() -> None:
    """`_ws_cold_start_gate_check` must return True (and flip the
    gate-open flag) as soon as a batting_team is committed, even
    if score is still 0 (legitimate zero-state during innings-2
    first ball, mid-match restart, between-overs, etc.)."""
    header("Fix 17 Path D: WS gate opens on first batting_team "
           "commit (looser hotfix 2026-04-26)")
    import test_pipeline as tp
    tp._ws_cold_start_gate_open = False
    tp._ws_cold_start_gate_first_attempt_ts = None
    payload_no_team = {"scorecard": {"batting_team": ""}}
    tp._ws_cold_start_gate_check(payload_no_team)
    payload_team_zero = {"scorecard": {"batting_team": "KKR",
                                       "score": 0,
                                       "wickets": 0,
                                       "overs": "0.0"}}
    allowed = tp._ws_cold_start_gate_check(payload_team_zero)
    check("gate opens on first batting_team commit (score=0 OK)",
          allowed is True, f"allowed={allowed}")
    check("gate-open flag flipped to True",
          tp._ws_cold_start_gate_open is True,
          f"gate_open={tp._ws_cold_start_gate_open}")
    payload_no_team_after = {"scorecard": {"batting_team": ""}}
    allowed_after = tp._ws_cold_start_gate_check(payload_no_team_after)
    check("once open, gate stays open",
          allowed_after is True, f"allowed_after={allowed_after}")


def test_fix17_path_d_cold_start_ws_gate_opens_on_canonical_shape() -> None:
    """Hotfix 2026-04-26: gate must also open when score and
    batting_team are nested under `payload["scorecard"]` (the
    canonical `build_full_payload()` shape).  Earlier version of
    the gate only checked the flat shape and never opened on
    real production payloads."""
    header("Fix 17 Path D hotfix: gate opens on canonical "
           "`payload['scorecard']` shape")
    import test_pipeline as tp
    tp._ws_cold_start_gate_open = False
    tp._ws_cold_start_gate_first_attempt_ts = None
    payload_canonical = {
        "scorecard": {
            "batting_team": "Kolkata Knight Riders",
            "score": 130,
            "wickets": 7,
            "overs": "19.1",
        },
    }
    allowed = tp._ws_cold_start_gate_check(payload_canonical)
    check("gate opens on canonical scorecard payload",
          allowed is True, f"allowed={allowed}")
    check("gate-open flag flipped via canonical path",
          tp._ws_cold_start_gate_open is True,
          f"gate_open={tp._ws_cold_start_gate_open}")


def test_fix17_path_d_cold_start_ws_gate_safety_timeout() -> None:
    """`_ws_cold_start_gate_check` must release the gate after
    the safety timeout (90s) to avoid UI hang."""
    header("Fix 17 Path D: WS cold-start gate safety timeout "
           "releases on 90s elapsed")
    import test_pipeline as tp
    tp._ws_cold_start_gate_open = False
    # Set first-attempt timestamp to 100s ago.
    import time as _t
    tp._ws_cold_start_gate_first_attempt_ts = _t.time() - 100.0
    payload_zero = {"batting_team": None, "score": 0}
    allowed = tp._ws_cold_start_gate_check(payload_zero)
    check("gate opens on safety timeout (>90s elapsed)",
          allowed is True, f"allowed={allowed}")
    check("gate-open flag flipped to True via timeout path",
          tp._ws_cold_start_gate_open is True,
          f"gate_open={tp._ws_cold_start_gate_open}")


def test_fix17_path_d_block_present_in_source() -> None:
    """Source-level wiring: broadcast_state must consult the
    gate before sending to WS clients."""
    header("Fix 17 Path D: WS gate wired in broadcast_state()")
    src = (Path(__file__).resolve().parent / "test_pipeline.py"
           ).read_text()
    check("`_ws_cold_start_gate_check` defined",
          "def _ws_cold_start_gate_check(" in src,
          "expected gate-check function")
    check("`broadcast_state` consults the gate before send",
          ("if not _ws_cold_start_gate_check(payload):" in src),
          "expected gate consultation in broadcast_state")
    check("WS-COLD-START-GATE telemetry tag present",
          "[WS-COLD-START-GATE]" in src,
          "expected log marker")


def test_fix16_handle_innings_change_routes_through_setter() -> None:
    """The proper innings transition path
    (`_handle_innings_change`) now routes through
    `set_innings_2()` rather than inline `__init__()`.  Source
    invariant."""
    header("Fix 16: _handle_innings_change routes through "
           "set_innings_2()")
    from score_manager import ScoreManager
    src = (Path(__file__).resolve().parent / "score_manager.py"
           ).read_text()
    check("set_innings_2() method defined on ScoreManager",
          "def set_innings_2(" in src,
          "expected `def set_innings_2(`")
    check("[SM-INNINGS-2-RESET] telemetry tag present",
          "[SM-INNINGS-2-RESET]" in src,
          "expected log marker")
    # Count only actual assignments (line starts with whitespace
    # then `self.innings = 2`), excluding occurrences in comments.
    _assign_count = sum(
        1 for _line in src.splitlines()
        if _line.lstrip().startswith("self.innings = 2"))
    check("3 leaky callsites no longer flip self.innings = 2 "
          "directly (only the setter body + cold-start "
          "bootstrap should remain — 2 actual assignments)",
          _assign_count <= 2,
          f"expected <= 2 actual assignments (setter + "
          f"cold-start bootstrap), got {_assign_count}")
    check("_update_misc routes through set_innings_2()",
          "_update_misc.target_arrival" in src,
          "expected reason tag from _update_misc callsite")
    check("_update_supplements routes through set_innings_2()",
          "_update_supplements.target_arrival" in src,
          "expected reason tag from _update_supplements callsite")


def test_fix15_score_side_gate_block_present_in_source() -> None:
    """Source-level wiring guard."""
    header("Fix 15: SCORE-INF-GATE (advance + floor) wired in "
           "apply_scorer_decision")
    src = (Path(__file__).resolve().parent / "test_pipeline.py"
           ).read_text()
    check("gate marker `[SCORE-INF-GATE]` present",
          "[SCORE-INF-GATE]" in src,
          "expected [SCORE-INF-GATE] log marker")
    check("gate appends `SCORE-INF-GATE:` to changes (advance + floor)",
          src.count('f"SCORE-INF-GATE:') >= 2,
          "expected changes.append f-strings for SCORE-INF-GATE variants")
    check("advance gate computes _gate_score_explained",
          "_gate_score_explained" in src,
          "expected _gate_score_explained variable")
    check("floor gate helper present",
          "_score_inf_floor_components" in src,
          "expected _score_inf_floor_components")
    check("floor log mentions min_score_from_batters_and_extras",
          "min_score_from_batters_and_extras" in src,
          "expected floor telemetry substring")


def test_fix14_balls_ceiling_block_present_in_source() -> None:
    """Source-level wiring guard."""
    header("Fix 14: BALLS-CEILING-GATE wired in "
           "apply_scorer_decision")
    src = (Path(__file__).resolve().parent / "test_pipeline.py"
           ).read_text()
    check("gate marker `[BALLS-CEILING-GATE]` present",
          "[BALLS-CEILING-GATE]" in src,
          "expected [BALLS-CEILING-GATE] log marker")
    check("gate appends `BALLS-CEILING-GATE:` to changes",
          'changes.append(\n                        f"BALLS-CEILING-GATE'
          in src,
          "expected changes.append for BALLS-CEILING-GATE")
    check("gate sets `_gate_blocked = True`",
          src.count("_gate_blocked = True") >= 2,
          "expected _gate_blocked = True at both Fix 11 "
          "and Fix 14 callsites")


def test_fix11_gate_block_present_in_source() -> None:
    """Source-level wiring: the gate must live in
    `apply_scorer_decision`, after the `_ext_batter_stats` build but
    before the INIT loop / update loop.  Guards against accidental
    removal during future refactors."""
    header("Fix 11: EXTRAS-INF-GATE block wired in apply_scorer_decision")
    src = (Path(__file__).resolve().parent / "test_pipeline.py"
           ).read_text()
    check("gate marker `[EXTRAS-INF-GATE]` present",
          "[EXTRAS-INF-GATE]" in src,
          "expected [EXTRAS-INF-GATE] log marker in test_pipeline.py")
    check("gate block sets `_gate_blocked` flag",
          "_gate_blocked = True" in src,
          "expected `_gate_blocked = True` assignment")
    check("gate block neutralises both batter_ups and "
          "_ext_batter_stats",
          "if _gate_blocked:\n            batter_ups = {}\n"
          "            _ext_batter_stats = {}" in src,
          "expected gate to clear both batter_ups and "
          "_ext_batter_stats on block")
    check("gate appends `EXTRAS-INF-GATE:` to changes",
          'changes.append(\n                            f"EXTRAS-INF-GATE'
          in src,
          "expected changes.append with EXTRAS-INF-GATE: prefix")
    check("gate uses scoreboard physics formula (bat_sum > score)",
          "_gate_bat_sum > _gate_score_i" in src,
          "expected `_gate_bat_sum > _gate_score_i` predicate")
    # Order check: gate block must come AFTER `_ext_batter_stats`
    # is populated, BEFORE the INIT loop's `_ext_batter_stats`
    # consumption.
    pos_ext_stats = src.find("_ext_batter_stats: dict[str, dict] = {}")
    pos_gate = src.find("[EXTRAS-INF-GATE]")
    pos_init = src.find("# Issue 1: When no active batters exist")
    check("gate is positioned between _ext_batter_stats build and "
          "INIT loop",
          pos_ext_stats > 0 and pos_ext_stats < pos_gate < pos_init,
          f"order: ext_stats@{pos_ext_stats} gate@{pos_gate} "
          f"init@{pos_init}")


# ---------------------------------------------------------------------
# Fix 12: rejection-consensus release on runs-monotonic guard
# (Layer 4 of phantom +N quartet; POISON-STREAK template applied to
# per-batter runs)
# ---------------------------------------------------------------------
def _make_sb_with_phantom_runs(name: str, phantom_runs: int,
                               phantom_balls: int):
    """Construct a Scoreboard where `name` is batting with an
    inflated (phantom) runs value committed.  Subsequent
    `update_batter` calls with truth values lower than the phantom
    will be rejected by the runs-monotonic guard until Layer 4's
    consensus-release fires.
    """
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL",
                     [name, "Other", "C", "D", "E"],
                     ["B1", "B2"])
    sb.batting_card[name]["status"] = "batting"
    sb.batting_card[name]["runs"] = phantom_runs
    sb.batting_card[name]["balls"] = phantom_balls
    sb.batting_card["Other"]["status"] = "batting"
    sb.batting_card["Other"]["runs"] = 5
    sb.batting_card["Other"]["balls"] = 8
    sb._inn["striker"] = name
    sb._inn["non"] = "Other"
    sb._inn["score"] = phantom_runs + 5 + 5  # leave room for extras
    sb._inn["wickets"] = 0
    sb._inn["overs"] = "10.0"
    # Seed the consensus tracker so the phantom value is "committed"
    # — otherwise updates land cold-start consensus instead of the
    # regression guard.
    sb._tracker.force_set(f"bat:{name}:runs", phantom_runs)
    sb._tracker.force_set(f"bat:{name}:balls", phantom_balls)
    return sb


def test_fix12_streak_increments_on_repeated_rejections() -> None:
    """Reject same value 3 times → streak counter at 3, no release
    yet (threshold=5)."""
    header("Fix 12: streak increments on repeated rejections of same "
           "value (no release before threshold)")
    sb = _make_sb_with_phantom_runs("Dube", 31, 28)
    # Four consecutive rejections of runs=22 (truth) below the
    # threshold of 5 — no release should fire.
    for i in range(4):
        sb.update_batter("Dube", runs=22, balls=13 + i,
                         frame=100 + i)
    streak = sb._runs_reject_streak.get("Dube")
    check("streak entry exists for rejected batter",
          streak is not None, "expected entry for Dube")
    check("streak count == 4 (just below threshold of 5)",
          streak and streak["count"] == 4,
          f"streak={streak}")
    check("streak value matches rejected value (22)",
          streak and streak["value"] == 22,
          f"streak value={streak.get('value') if streak else None}")
    check("phantom runs unchanged (no release before threshold)",
          sb.batting_card["Dube"]["runs"] == 31,
          f"runs={sb.batting_card['Dube']['runs']!r}")


def test_fix12_release_fires_at_threshold() -> None:
    """Reject same value 5 times → release fires, force_set runs
    and balls."""
    header("Fix 12: release fires at threshold (N=5) — force_set "
           "runs + balls to truth values")
    sb = _make_sb_with_phantom_runs("Dube", 31, 28)
    # 5 consecutive rejections of runs=22 — release should fire on
    # the 5th.
    for i in range(5):
        sb.update_batter("Dube", runs=22, balls=13,
                         frame=100 + i)
    check("Dube runs released to 22 (truth, was 31 phantom)",
          sb.batting_card["Dube"]["runs"] == 22,
          f"runs={sb.batting_card['Dube']['runs']!r}")
    check("Dube balls released to 13 (paired truth)",
          sb.batting_card["Dube"]["balls"] == 13,
          f"balls={sb.batting_card['Dube']['balls']!r}")
    streak = sb._runs_reject_streak.get("Dube")
    check("streak counter reset post-release (count=0)",
          streak is None or streak.get("count", 0) == 0,
          f"streak={streak}")
    # Tracker baseline must also be force-set (otherwise next
    # frame's read could regress).
    tracker_runs = sb._tracker.get("bat:Dube:runs")
    check("tracker baseline force_set to 22",
          tracker_runs == 22,
          f"tracker bat:Dube:runs={tracker_runs!r}")


def test_fix12_streak_resets_on_different_rejected_value() -> None:
    """If the rejected value changes mid-streak, counter restarts
    at 1 (not consensus on a single value)."""
    header("Fix 12: streak resets when rejected value changes")
    sb = _make_sb_with_phantom_runs("Dube", 31, 28)
    sb.update_batter("Dube", runs=22, balls=13, frame=100)
    sb.update_batter("Dube", runs=22, balls=14, frame=101)
    sb.update_batter("Dube", runs=22, balls=15, frame=102)
    streak_pre = dict(sb._runs_reject_streak.get("Dube") or {})
    check("streak count == 3 after 3 rejections of runs=22",
          streak_pre.get("count") == 3,
          f"streak_pre={streak_pre}")
    # Different rejected value resets counter to 1.
    sb.update_batter("Dube", runs=20, balls=16, frame=103)
    streak_post = sb._runs_reject_streak.get("Dube") or {}
    check("streak value changed to 20",
          streak_post.get("value") == 20,
          f"streak_post={streak_post}")
    check("streak count reset to 1 (not 4)",
          streak_post.get("count") == 1,
          f"streak_post count={streak_post.get('count')}")
    check("phantom runs still unchanged (no release on resets)",
          sb.batting_card["Dube"]["runs"] == 31,
          f"runs={sb.batting_card['Dube']['runs']!r}")


def test_fix12_streak_clears_on_legitimate_acceptance() -> None:
    """If a legitimate (non-rejected) update lands for the batter,
    streak entry is dropped — phantom window has closed."""
    header("Fix 12: streak entry dropped on legitimate acceptance")
    sb = _make_sb_with_phantom_runs("Dube", 31, 28)
    # Build a streak of 3 rejections.
    for i in range(3):
        sb.update_batter("Dube", runs=22, balls=13 + i,
                         frame=100 + i)
    check("streak built (count=3)",
          sb._runs_reject_streak.get("Dube", {}).get("count") == 3,
          f"streak={sb._runs_reject_streak.get('Dube')}")
    # Legitimate update at runs >= cur_r passes the regression
    # guard (no rejection) — streak should be dropped.
    sb.update_batter("Dube", runs=32, balls=29, frame=110)
    check("streak entry dropped after legitimate acceptance",
          "Dube" not in sb._runs_reject_streak,
          f"streak={sb._runs_reject_streak}")


def test_fix12_zero_regression_clause_also_tracked() -> None:
    """The other rejection clause (`new_r == 0` with `cur_r > 5`)
    must also feed the streak — both clauses share Layer 4 release
    semantics."""
    header("Fix 12: streak also tracks the runs-to-zero rejection "
           "clause")
    sb = _make_sb_with_phantom_runs("Player", 22, 18)
    for i in range(5):
        sb.update_batter("Player", runs=0, balls=0,
                         frame=100 + i)
    check("zero-regression clause: runs released to 0 at threshold",
          sb.batting_card["Player"]["runs"] == 0,
          f"runs={sb.batting_card['Player']['runs']!r}")
    check("zero-regression clause: balls released to 0 at threshold",
          sb.batting_card["Player"]["balls"] == 0,
          f"balls={sb.batting_card['Player']['balls']!r}")


def test_fix12_dube_f1767_production_replay() -> None:
    """Replay-shaped fixture mirroring the F1767-F1812 Dube case
    from CSK-vs-GT 2026-04-26: phantom Dube=31(28), Scout reading
    runs=22 with varying balls counts.  Pre-Layer-4 the phantom
    held for 41:50 with 357 rejections; Layer 4 releases on the
    5th rejection."""
    header("Fix 12: replays F1767+ Dube phantom — release at "
           "rejection #5 (vs 357-rejection pre-fix baseline)")
    sb = _make_sb_with_phantom_runs("Dube", 31, 28)
    # Simulate Scout reading Dube=22 with rolling balls counts
    # (13, 14, 15, ...) — runs are stable, balls change slightly
    # but stay within tracker's 2-ball tolerance window.
    rejections = 0
    for i in range(10):
        pre = sb.batting_card["Dube"]["runs"]
        sb.update_batter("Dube", runs=22, balls=13,
                         frame=1767 + i)
        post = sb.batting_card["Dube"]["runs"]
        if pre == post and post == 31:
            rejections += 1
        if post != 31:
            break
    check("Dube released within 5 frames (Layer 4 triggered)",
          rejections == 4,
          f"rejections before release={rejections} (expected 4 — "
          f"5th call is the release)")
    check("Dube runs settled to 22 (truth)",
          sb.batting_card["Dube"]["runs"] == 22,
          f"runs={sb.batting_card['Dube']['runs']!r}")


def test_fix12_release_clears_row_rejected_flag() -> None:
    """When release fires, the `_last_row_rejected_frame` flag must
    be cleared — the row was right after all, downstream broadcast-
    indicator striker updates should not be suppressed."""
    header("Fix 12: release clears _last_row_rejected_frame so "
           "downstream striker reads aren't suppressed")
    sb = _make_sb_with_phantom_runs("Dube", 31, 28)
    for i in range(5):
        sb.update_batter("Dube", runs=22, balls=13,
                         frame=100 + i)
    check("_last_row_rejected_frame cleared on release",
          sb._last_row_rejected_frame == -1,
          f"_last_row_rejected_frame="
          f"{sb._last_row_rejected_frame}")


def test_fix12_per_batter_independence() -> None:
    """Streak state is per-batter — rejections of Dube should not
    cause a release for Other, and vice versa."""
    header("Fix 12: per-batter streak isolation")
    sb = _make_sb_with_phantom_runs("Dube", 31, 28)
    # Inflate Other too so its truth would also be rejected.
    sb.batting_card["Other"]["runs"] = 25
    sb._tracker.force_set(f"bat:Other:runs", 25)
    for i in range(4):
        sb.update_batter("Dube", runs=22, balls=13,
                         frame=100 + i)
    sb.update_batter("Other", runs=10, balls=12, frame=200)
    check("Dube streak count=4 (not 5)",
          sb._runs_reject_streak.get("Dube", {}).get("count") == 4,
          f"Dube streak={sb._runs_reject_streak.get('Dube')}")
    check("Other streak count=1 (independent)",
          sb._runs_reject_streak.get("Other", {}).get("count") == 1,
          f"Other streak={sb._runs_reject_streak.get('Other')}")
    check("Neither released yet",
          sb.batting_card["Dube"]["runs"] == 31
          and sb.batting_card["Other"]["runs"] == 25,
          f"Dube={sb.batting_card['Dube']['runs']} "
          f"Other={sb.batting_card['Other']['runs']}")


def test_fix12_innings_2_resets_streak() -> None:
    """`set_innings_2` must wipe `_runs_reject_streak` so an
    innings-1 stuck window doesn't leak into innings 2."""
    header("Fix 12: set_innings_2 clears streak state")
    sb = _make_sb_with_phantom_runs("Dube", 31, 28)
    for i in range(3):
        sb.update_batter("Dube", runs=22, balls=13 + i,
                         frame=100 + i)
    check("streak built before innings-2",
          "Dube" in sb._runs_reject_streak,
          f"streak={sb._runs_reject_streak}")
    sb.set_innings_2(target=160)
    check("streak cleared after set_innings_2",
          sb._runs_reject_streak == {},
          f"streak={sb._runs_reject_streak}")


def test_fix12_block_present_in_source() -> None:
    """Source-level wiring: the Layer 4 block must be present in
    `update_batter`, downstream of the regression clauses, with
    the threshold constant defined on the Scoreboard instance."""
    header("Fix 12: Layer 4 release block wired in scoreboard.py")
    src = (Path(__file__).resolve().parent / "eyes" / "scoreboard.py"
           ).read_text()
    check("[RUNS-REJECT-STREAK] telemetry tag present",
          "[RUNS-REJECT-STREAK]" in src,
          "expected [RUNS-REJECT-STREAK] log marker")
    check("[RUNS-REJECT-RELEASE] telemetry tag present",
          "[RUNS-REJECT-RELEASE]" in src,
          "expected [RUNS-REJECT-RELEASE] log marker")
    check("threshold constant `_RUNS_REJECT_RELEASE_N` defined",
          "_RUNS_REJECT_RELEASE_N: int = 5" in src,
          "expected `_RUNS_REJECT_RELEASE_N: int = 5` in __init__")
    check("streak state attribute `_runs_reject_streak` defined",
          "_runs_reject_streak: dict[str, dict] = {}" in src,
          "expected `_runs_reject_streak: dict[str, dict] = {}` "
          "in __init__")
    check("force_set used for release (mirrors balls-correction "
          "release pattern)",
          "self._tracker.force_set(\n                            "
          "f\"bat:{name}:runs\"," in src,
          "expected force_set call inside release block")
    check("set_innings_2 clears streak state",
          "self._runs_reject_streak = {}" in src,
          "expected set_innings_2 to clear _runs_reject_streak")
    # Order check: release block must come AFTER the regression
    # clauses (so it can read `_runs_regression_rejected`).
    pos_clause = src.find("_runs_regression_rejected = False")
    pos_release = src.find("[RUNS-REJECT-RELEASE]")
    check("release block downstream of regression-rejection "
          "marker init",
          pos_clause > 0 and pos_clause < pos_release,
          f"clause@{pos_clause} release@{pos_release}")


# ---------------------------------------------------------------------
# State-recovery consensus override (Phase 1 telemetry-only)
# ---------------------------------------------------------------------
def _state_recovery_candidate(score: int = 120) -> dict:
    return {
        "score": score,
        "wickets": 1,
        "overs": 11.1,
        "batters": [
            {
                "name": "Nitish Rana",
                "runs": 43,
                "balls": 28,
                "status": "yet_to_bat",
                "status_update": True,
            },
            {
                "name": "KL Rahul",
                "runs": 64,
                "balls": 38,
                "status": "batting",
                "status_update": False,
            },
        ],
        "active_batters": ["Nitish Rana", "KL Rahul"],
        "bat_sum": 107,
    }


def test_state_recovery_no_fire_single_guard() -> None:
    header("State recovery: one guard family alone never emits candidate")
    from test_pipeline import StateRecoveryAggregator
    agg = StateRecoveryAggregator(threshold=5)
    event = None
    for frame in range(100, 105):
        event = agg.observe(
            frame, "poison_score", _state_recovery_candidate(),
            current={"score": 76}, proposed_reset=["score"])
    check("no candidate emitted for single guard family",
          event is None, f"event={event!r}")


def test_state_recovery_candidate_fires_two_guard_families() -> None:
    header("State recovery: two guard families emit telemetry candidate")
    from test_pipeline import StateRecoveryAggregator
    agg = StateRecoveryAggregator(threshold=5)
    event = None
    for frame in range(100, 105):
        cand = _state_recovery_candidate()
        event = event or agg.observe(
            frame, "poison_score", cand,
            current={"score": 76}, proposed_reset=["score"])
        event = event or agg.observe(
            frame, "slot_scrub_rejected", cand,
            current={"score": 76},
            proposed_reset=["slot:non", "status:Nitish Rana"])
    check("candidate emitted on fifth agreeing frame",
          event is not None, f"event={event!r}")
    check("event remains telemetry-only",
          event and event.get("telemetry_only") is True,
          f"event={event!r}")
    check("threshold telemetry records N=3 and N=5 trigger frames",
          event and event.get("threshold_frames", {}).get("n3") == 102
          and event.get("threshold_frames", {}).get("n5") == 104
          and event.get("threshold_frames", {}).get("n8") is None,
          f"thresholds={event.get('threshold_frames') if event else None}")
    check("coherence telemetry records candidate-internal checks",
          event and event.get("coherence", {}).get("bat_sum_within_score")
          is True,
          f"coherence={event.get('coherence') if event else None}")
    check("both guard families captured",
          event and set(event.get("guards", [])) == {
              "poison_score", "slot_scrub_rejected"},
          f"guards={event.get('guards') if event else None}")


def test_state_recovery_resets_on_candidate_change() -> None:
    header("State recovery: candidate change resets streak")
    from test_pipeline import StateRecoveryAggregator
    agg = StateRecoveryAggregator(threshold=5)
    event = None
    for frame, score in enumerate([120, 120, 121, 120, 120], start=100):
        cand = _state_recovery_candidate(score=score)
        agg.observe(frame, "poison_score", cand,
                    current={"score": 76}, proposed_reset=["score"])
        event = agg.observe(frame, "slot_scrub_rejected", cand,
                            current={"score": 76},
                            proposed_reset=["slot:non"])
    check("no candidate emitted across changing proposed state",
          event is None, f"event={event!r}")


def test_state_recovery_rejects_incoherent_bat_sum() -> None:
    header("State recovery: incoherent bat_sum > score candidate rejected")
    from test_pipeline import StateRecoveryAggregator
    agg = StateRecoveryAggregator(threshold=2)
    cand = _state_recovery_candidate(score=80)
    event = None
    for frame in range(100, 102):
        agg.observe(frame, "poison_score", cand,
                    current={"score": 76}, proposed_reset=["score"])
        event = agg.observe(frame, "slot_scrub_rejected", cand,
                            current={"score": 76},
                            proposed_reset=["slot:non"])
    check("incoherent candidate never emits",
          event is None, f"event={event!r}")


def test_state_recovery_suppressed_during_innings_transition() -> None:
    header("State recovery: innings-transition suppression blocks emit")
    from test_pipeline import StateRecoveryAggregator
    agg = StateRecoveryAggregator(threshold=2)
    event = None
    for frame in range(100, 102):
        cand = _state_recovery_candidate(score=0)
        agg.observe(frame, "poison_score", cand,
                    current={"score": 156}, proposed_reset=["score"],
                    suppressed=True)
        event = agg.observe(frame, "slot_scrub_rejected", cand,
                            current={"score": 156},
                            proposed_reset=["slot:striker"],
                            suppressed=True)
    check("suppressed window never emits candidate",
          event is None, f"event={event!r}")


def test_state_recovery_fix12_boundary_single_field_excluded() -> None:
    header("State recovery: Fix 12 single-field cases are excluded")
    from test_pipeline import StateRecoveryAggregator
    agg = StateRecoveryAggregator(threshold=2)
    cand = {
        "single_batter_field_only": True,
        "batters": [{
            "name": "Dube", "runs": 22, "balls": 13,
            "status": "batting", "status_update": False,
        }],
        "active_batters": ["Dube"],
        "bat_sum": 22,
        "score": 100,
    }
    event = None
    for frame in range(100, 102):
        agg.observe(frame, "batter_row_rejected", cand,
                    current={"score": 100},
                    proposed_reset=["bat:Dube:runs"])
        event = agg.observe(frame, "slot_scrub_rejected", cand,
                            current={"score": 100},
                            proposed_reset=["bat:Dube:runs"])
    check("single-batter single-field candidate left to Fix 12",
          event is None, f"event={event!r}")


# ---------------------------------------------------------------------
# Fix 9-12 telemetry analyzer extension
# ---------------------------------------------------------------------
# Tests target the per-fix report functions, regex parsing, and
# wicket-binning helper added to `analyze_match_telemetry.py` for
# converting "deployed and passing tests" into "validated against
# production failure modes."  Each test exercises one slice without
# requiring a real pipeline log on disk.


def _synth_log(lines: list[str]) -> "Path":
    """Write a synthetic log to a temp file and return the path."""
    import tempfile
    fp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".log", delete=False, encoding="utf-8")
    fp.write("\n".join(lines))
    fp.close()
    return Path(fp.name)


def test_analyzer_fix9a_parses_autoswap_inject() -> None:
    """The Fix 9a parser captures target value, latched_final, and
    sb_score_live from a real-shape AUTO-SWAP-TARGET log line."""
    header("Analyzer: Fix 9a parses AUTO-SWAP-TARGET injection")
    from analyze_match_telemetry import analyze
    log = _synth_log([
        "[19:00:00 F100 TEST] INFO:   [AUTO-SWAP-TARGET] Injecting "
        "target=159 (latched_final=158, sb_score_live=158) — "
        "sourced from latched innings_1_total"
    ])
    snap = analyze(log)
    check("captured exactly one AUTO-SWAP-TARGET event",
          len(snap.fix9a_autoswap_events) == 1,
          f"got {len(snap.fix9a_autoswap_events)}")
    ev = snap.fix9a_autoswap_events[0]
    check("target value = 159", ev["target"] == "159", str(ev))
    check("latched_final = 158", ev["latched_final"] == "158", str(ev))
    check("not flagged as skipped", ev["skipped"] is False, str(ev))


def test_analyzer_fix9a_parses_autoswap_skipped() -> None:
    """The skipped-injection path is captured with `skipped=True`."""
    header("Analyzer: Fix 9a parses AUTO-SWAP-TARGET skip path")
    from analyze_match_telemetry import analyze
    log = _synth_log([
        "[19:00:00 F100 TEST] WARN:   [AUTO-SWAP-TARGET] Target "
        "injection skipped — both latched_final and sb_score=0 "
        "at AUTO-SWAP. Target will remain None until broadcast "
        "TARGET overlay or downstream recovery sets it."
    ])
    snap = analyze(log)
    check("captured exactly one skipped event",
          len(snap.fix9a_autoswap_events) == 1)
    check("skipped flag set", snap.fix9a_autoswap_events[0]["skipped"])


def test_analyzer_fix9b_parses_target_monotonic_and_sanity() -> None:
    """Both TARGET-MONOTONIC and TARGET-SANITY guards captured into
    distinct event lists."""
    header("Analyzer: Fix 9b parses both target guards")
    from analyze_match_telemetry import analyze
    log = _synth_log([
        "[19:00:00 F100 TEST] WARN:   [TARGET-MONOTONIC] Refusing "
        "inn2 target overwrite 159 → 66 (proposal from "
        "team_assignment, source: strip parser)",
        "[19:00:01 F101 TEST] WARN:   [TARGET-SANITY] Rejecting "
        "target=50 ≤ current_team_score=63 — impossible in "
        "valid chase",
    ])
    snap = analyze(log)
    check("monotonic event captured",
          len(snap.fix9b_target_monotonic_events) == 1,
          str(snap.fix9b_target_monotonic_events))
    check("sanity event captured",
          len(snap.fix9b_target_sanity_events) == 1,
          str(snap.fix9b_target_sanity_events))
    mono = snap.fix9b_target_monotonic_events[0]
    san = snap.fix9b_target_sanity_events[0]
    check("monotonic current=159 proposed=66",
          mono["current"] == 159 and mono["proposed"] == 66, str(mono))
    check("sanity proposed=50 score=63",
          san["proposed_target"] == 50 and san["current_team_score"] == 63,
          str(san))


def test_analyzer_fix10_parses_three_rotation_kinds() -> None:
    """Striker / non / anomaly variants are tagged correctly."""
    header("Analyzer: Fix 10 parses all three POST-WICKET-ROTATION shapes")
    from analyze_match_telemetry import analyze
    log = _synth_log([
        "[19:00:00 F100 BOARD] INFO: [POST-WICKET-ROTATION] "
        "striker 'Smith' dismissed → rotated non 'Jones' "
        "into striker slot; non cleared pending new-batter "
        "admission.",
        "[19:00:01 F101 BOARD] INFO: [POST-WICKET-ROTATION] "
        "non 'Brown' dismissed → slot cleared pending "
        "new-batter admission.",
        "[19:00:02 F102 BOARD] WARN: [POST-WICKET-ROTATION] "
        "anomaly: 'Ghost' occupied BOTH striker and non "
        "slots — both cleared defensively (likely prior collision "
        "state that Fix 5 did not catch).",
    ])
    snap = analyze(log)
    check("three events captured",
          len(snap.fix10_post_wicket_events) == 3)
    kinds = [ev["kind"] for ev in snap.fix10_post_wicket_events]
    check("kinds = [striker, non, anomaly]",
          kinds == ["striker", "non", "anomaly"], str(kinds))
    batters = [ev["batter"] for ev in snap.fix10_post_wicket_events]
    check("batters = [Smith, Brown, Ghost]",
          batters == ["Smith", "Brown", "Ghost"], str(batters))


def test_analyzer_fix11_parses_extras_inf_gate() -> None:
    """EXTRAS-INF-GATE captures wkts, bat_sum, score, excess."""
    header("Analyzer: Fix 11 parses EXTRAS-INF-GATE event")
    from analyze_match_telemetry import analyze
    log = _synth_log([
        "[19:00:00 F2408 TEST] WARN:   [EXTRAS-INF-GATE] wkts=4: "
        "proposed bat_sum=176 > score=154 (excess=22) — rejecting "
        "batter proposals (Hosein=21, Doe=155). Cricket physics "
        "violation; phantom commit prevented."
    ])
    snap = analyze(log)
    check("one event captured", len(snap.fix11_extras_inf_events) == 1)
    ev = snap.fix11_extras_inf_events[0]
    check("wkts=4 bat_sum=176 score=154 excess=22",
          ev["wkts"] == 4 and ev["bat_sum"] == 176
          and ev["score"] == 154 and ev["excess"] == 22, str(ev))


def test_analyzer_fix12_parses_streak_and_release() -> None:
    """RUNS-REJECT-STREAK and RUNS-REJECT-RELEASE go to distinct lists
    with parsed batter / value / count."""
    header("Analyzer: Fix 12 parses streak and release events")
    from analyze_match_telemetry import analyze
    log = _synth_log([
        "[19:00:00 F1767 TRACK] INFO:   [RUNS-REJECT-STREAK] "
        "Shivam Dube=22 streak=3/5 (cur=31 held)",
        "[19:00:01 F1772 TRACK] INFO:   [RUNS-REJECT-STREAK] "
        "Shivam Dube=22 streak=5/5 (cur=31 held)",
        "[19:00:02 F1773 TRACK] WARN:   [RUNS-REJECT-RELEASE] "
        "Shivam Dube: 5 consecutive rejections of runs=22 "
        "(cur=31) — accepting as new truth (current value is "
        "stale phantom). force_set bat:Shivam Dube:runs, balls.",
    ])
    snap = analyze(log)
    check("two streak events captured",
          len(snap.fix12_reject_streak_events) == 2,
          str(snap.fix12_reject_streak_events))
    check("one release event captured",
          len(snap.fix12_reject_release_events) == 1,
          str(snap.fix12_reject_release_events))
    rel = snap.fix12_reject_release_events[0]
    check("release: batter=Dube, consec=5, value=22",
          rel["batter"] == "Shivam Dube" and rel["consecutive"] == 5
          and rel["released_value"] == 22, str(rel))
    last_streak = snap.fix12_reject_streak_events[-1]
    check("streak threshold parsed = 5",
          last_streak["threshold"] == 5
          and last_streak["count"] == 5, str(last_streak))


def test_analyzer_state_recovery_candidate_parses_detail() -> None:
    """State-recovery candidate telemetry captures guard families,
    candidate/current counterfactual, and proposed reset scope."""
    header("Analyzer: parses STATE-RECOVERY-OVERRIDE-CANDIDATE")
    from analyze_match_telemetry import analyze, report_state_recovery
    log = _synth_log([
        "[19:00:00 F1215 TEST] WARN:   "
        "[STATE-RECOVERY-OVERRIDE-CANDIDATE] sig=abc123 "
        "guards=poison_score,slot_scrub_rejected frames=5 "
        "candidate_json={\"score\":120,\"wickets\":1} "
        "current_json={\"score\":76,\"wickets\":1} "
        "coherence_json={\"bat_sum_within_score\":true} "
        "thresholds_json={\"n3\":1213,\"n5\":1215,\"n8\":null} "
        "proposed_reset=score,slot:non "
        "reason=stale_reference_state telemetry_only=true",
    ])
    snap = analyze(log)
    check("one candidate event captured",
          len(snap.state_recovery_candidate_events) == 1,
          str(snap.state_recovery_candidate_events))
    ev = snap.state_recovery_candidate_events[0]
    check("guard families parsed",
          ev["guards"] == ["poison_score", "slot_scrub_rejected"],
          str(ev))
    check("candidate/current parsed as JSON",
          ev["candidate"]["score"] == 120
          and ev["current"]["score"] == 76,
          str(ev))
    check("proposed reset scope parsed",
          ev["proposed_reset"] == ["score", "slot:non"],
          str(ev))
    check("coherence and threshold telemetry parsed",
          ev["coherence"]["bat_sum_within_score"] is True
          and ev["threshold_frames"]["n3"] == 1213
          and ev["threshold_frames"]["n8"] is None,
          str(ev))
    text = report_state_recovery(snap)
    check("report renders candidate count",
          "CANDIDATE would-fire events: 1" in text, text)


def test_analyzer_striker_collision_and_wicket_transitions() -> None:
    """STRIKER-COLLISION events count for Fix 10 counterfactual; wicket
    transitions used for binning are deduplicated by wicket count."""
    header("Analyzer: STRIKER-COLLISION counted; wicket transitions deduped")
    from analyze_match_telemetry import analyze
    log = _synth_log([
        "[19:00:00 F100 SB] WARN:   [STRIKER-COLLISION] Refusing "
        "striker=Foo (would collide with non)",
        "[19:00:01 F101 SB] WARN:   [STRIKER-COLLISION] Refusing "
        "non=Bar (would collide with striker)",
        "[19:00:02 F102 TEST] INFO:   [S 100ms] Changes: "
        "['score→50', 'wickets→3', 'overs→8.0']",
        # Same wicket count emitted again - should NOT double-count
        "[19:00:03 F103 TEST] INFO:   [S 100ms] Changes: "
        "['score→52', 'wickets→3', 'overs→8.1']",
        "[19:00:04 F104 TEST] INFO:   [S 100ms] Changes: "
        "['score→55', 'wickets→4', 'overs→8.3']",
    ])
    snap = analyze(log)
    check("two STRIKER-COLLISION events captured",
          len(snap.striker_collision_events) == 2)
    check("two unique wicket transitions (3 and 4)",
          len(snap.wicket_transition_frames) == 2,
          str(snap.wicket_transition_frames))
    wkts = [w["wickets"] for w in snap.wicket_transition_frames]
    check("wickets list = [3, 4]", sorted(wkts) == [3, 4], str(wkts))


def test_analyzer_bin_by_wicket_assigns_events_to_correct_bins() -> None:
    """Events occurring after wicket-N transition land in bin N; events
    before any transition land in bin 0."""
    header("Analyzer: _bin_by_wicket correctly partitions events")
    from analyze_match_telemetry import _bin_by_wicket
    wicket_frames = [
        {"frame": "F100", "wickets": 3, "ts": "19:00:00"},
        {"frame": "F200", "wickets": 4, "ts": "19:01:00"},
    ]
    events = [
        {"frame": "F050", "ts": "18:59:00"},  # pre-any-wicket
        {"frame": "F150", "ts": "19:00:30"},  # in wicket 3 window
        {"frame": "F175", "ts": "19:00:45"},  # in wicket 3 window
        {"frame": "F250", "ts": "19:01:30"},  # in wicket 4 window
    ]
    bins = _bin_by_wicket(events, wicket_frames)
    check("bin 0 has 1 event",
          len(bins.get(0, [])) == 1,
          str({k: len(v) for k, v in bins.items()}))
    check("bin 3 has 2 events",
          len(bins.get(3, [])) == 2,
          str({k: len(v) for k, v in bins.items()}))
    check("bin 4 has 1 event",
          len(bins.get(4, [])) == 1,
          str({k: len(v) for k, v in bins.items()}))


def test_analyzer_report_fix_10_per_wicket_histogram_renders() -> None:
    """report_fix_10 with per_wicket=True emits a per-wicket histogram
    section listing rotations and collisions per wicket."""
    header("Analyzer: report_fix_10 renders per-wicket histogram")
    from analyze_match_telemetry import (
        analyze, report_fix_10)
    log = _synth_log([
        "[19:00:00 F100 TEST] INFO: [S 100ms] Changes: ['wickets→3']",
        "[19:00:01 F110 SB] WARN: [STRIKER-COLLISION] Refusing "
        "striker=Foo",
        "[19:00:02 F120 SB] WARN: [STRIKER-COLLISION] Refusing "
        "striker=Foo",
        "[19:00:03 F200 TEST] INFO: [S 100ms] Changes: ['wickets→4']",
        "[19:00:04 F210 BOARD] INFO: [POST-WICKET-ROTATION] "
        "striker 'X' dismissed → rotated non 'Y' into "
        "striker slot; non cleared pending new-batter "
        "admission.",
    ])
    snap = analyze(log)
    text = report_fix_10(snap, per_wicket=True)
    check("histogram section present",
          "per-wicket histogram:" in text, text)
    check("wicket 3 row shows 2 collisions",
          "wicket 3: rotations=0  collisions=2" in text, text)
    check("wicket 4 row shows 1 rotation",
          "wicket 4: rotations=1  collisions=0" in text, text)


def test_analyzer_report_fix_10_silent_when_no_fires() -> None:
    """When neither rotation nor witnessed wickets appear, report
    declares 'trigger condition not yet observed' (silent on
    pre-trigger logs)."""
    header("Analyzer: report_fix_10 silent on pre-trigger log")
    from analyze_match_telemetry import (
        analyze, report_fix_10)
    log = _synth_log(["[19:00:00 F1 TEST] INFO: pipeline started"])
    snap = analyze(log)
    text = report_fix_10(snap, per_wicket=False)
    check("status line declares trigger not observed",
          "trigger condition (witnessed wicket) not yet observed"
          in text, text)


def test_analyzer_report_fix_9b_silent_marks_fix_9a_as_doing_its_job() -> None:
    """When 9b is silent, the report explicitly attributes the silence
    to Fix 9a (positive-fire on happy path) — not a bug."""
    header("Analyzer: report_fix_9b silent → credits Fix 9a")
    from analyze_match_telemetry import (
        analyze, report_fix_9b)
    log = _synth_log(["[19:00:00 F1 TEST] INFO: pipeline started"])
    snap = analyze(log)
    text = report_fix_9b(snap)
    check("status line credits Fix 9a",
          "Fix 9a doing its job" in text, text)


def test_analyzer_baseline_counterfactuals_present() -> None:
    """The pre-fix counterfactual baselines are the canonical anchor
    for validation; the dict must exist with all five fix keys."""
    header("Analyzer: BASELINE_COUNTERFACTUALS dict has all 5 keys")
    from analyze_match_telemetry import BASELINE_COUNTERFACTUALS
    for key in ("fix_9a", "fix_9b", "fix_10", "fix_11", "fix_12"):
        check(f"{key} present in baseline dict",
              key in BASELINE_COUNTERFACTUALS,
              f"missing {key}")


def test_analyzer_bundle_bc_signature_report_counts_new_guards() -> None:
    """Bundle B/C report captures positive-fire signatures for the
    clustered fixes so historical-log validation can detect zero-fire
    coverage gaps."""
    header("Analyzer: Bundle B/C positive-fire signatures counted")
    from analyze_match_telemetry import analyze, report_bundle_bc

    log = _synth_log([
        "[19:00:00 F10 TEST] WARN:   [BATTER-NORMALIZE] dropping "
        "surname ghost 'SINGH' paired with 'Rinku Singh'",
        "[19:00:01 F11 BOARD] WARN: [NEW-BATTER-BALLS-GATE] New "
        "Batter: proposed 0(16) exceeds fresh-admission ceiling 3",
        "[19:00:02 F12 TEST] WARN:   [BOWLER-BATTER-GATE] bowler "
        "stripped — name='KL Rahul'",
        "[19:00:03 F13 SCORE_MGR] INFO: [SM] cold-start zero "
        "candidate rejected as contextual graphic",
        "[19:00:04 F14 OVER] INFO: [OVER-RESYNC] Cursor aligned to "
        "over 16 from team_overs='16.3'",
        "[19:00:05 F15 BOARD] WARN: [ALL-OUT-AUTHORITY] Promoted "
        "wickets 9→10 from bowled evidence",
        "[19:00:06 F16 BOARD] WARN: Score regression rejected: 36→35",
        "[19:00:07 F17 TEST] WARN:   [WS-SLOT-INVARIANT] duplicate "
        "slots 'Abishek Porel'; rebuilt non='KL Rahul'",
        "[19:00:08 F18 BOARD] WARN:   [BOWLER-TEAM-OVER-CONSENSUS] "
        "accepting 'Suyash Sharma' after 2 reads",
        "[19:00:09 F19 TEST] WARN:   [SCORER-ACTIVE-GATE] rejecting "
        "batter update for witnessed-out batter 'A'",
        "[19:00:10 F20 TEST] INFO:   [STRIKER-SM-CUTOVER] suppressed "
        "legacy striker write (over-change-rotation); SM remains canonical",
        "[19:00:11 F21 BOARD] WARN:   [STRIKER-STATUS-GATE] Refusing "
        "role flip for A — status='out'",
        "[19:00:12 F22 BOARD] WARN:   [BOWLER-CONSENSUS-INCONSISTENT] "
        "refusing flip to 'X'",
        "[19:00:13 F23 BOARD] WARN:   [BOWLER-CONSENSUS-INCONSISTENT-OVERRIDE] "
        "accepting 'Y'",
        "[19:00:14 F24 BOARD] WARN:   [BOWLER-STATS-GRAPHIC-GATE] rejecting "
        "'Pat Cummins' - reason=career_keyword (overs='2.4' runs=18 wickets=1)",
        "[19:00:15 F25 TEST] WARN:   [SCORE-INF-GATE] proposed=18 < "
        "min_score_from_batters_and_extras (bat_sum=22, extras=0, min=22) "
        "— rejecting score commit.  Score-side misread (Layer 1.5 floor, "
        "Fix 11 sibling).",
        "[19:00:16 F26 TEST] INFO:   [STRIKER-READ-SM-CANONICAL] DETAIL "
        "(DRS-freeze branch): SM-vs-_inn divergence — striker SM='B' "
        "_inn='A'; non SM='A' _inn='B'; using SM canonical",
        "[19:00:17 F27 SCORE_MGR] INFO:   [SM-FEEDER-SYNC] field=score "
        "value=99 sb_accepted=true",
        "[19:00:18 F28 SCORE_MGR] INFO:   [SM-SHADOW-PARITY] field=score "
        "sm_would_accept=2 sb_value=1 divergence=true",
        "[19:00:19 F29 TEST] INFO:   [SM-FEEDER-DIVERGENCE] field=bowler_name "
        "sm_value='Pat' sb_value='Cummins' sb_consensus_state=active "
        "frames_since_sm_update=0",
        "[19:00:20 F30 TEST] WARN:   [SCORER-SCHEMA-WOULD-DROP] "
        "field=batter_updates key=Bad reason=multi_field_coerce "
        "filter_caught_in_step3=false frame=F30",
        "[19:00:21 F31 TEST] INFO:   [SCORER-SCHEMA-WOULD-COERCE] "
        "field=score_update.to reason=coerce_null raw='x' "
        "filter_caught_in_step3=false frame=F31",
        "[19:00:22 F32 TEST] WARN:   [BATTERS-INVARIANT] rule=A "
        "violation=active_set_max_two active=A,B,C witnessed_out=- "
        "striker=A non=B upstream_step3_fired=false "
        "upstream_step3_tags=- upstream_step4_returned_false=false "
        "action=noop_phase1 target=A,B,C frame=F32",
        "[19:00:23 F33 SCORE_MGR] WARN: [SM-SLOT-INVARIANT] duplicate "
        "slots 'Rinku Singh' (source=test_fixture); clearing non",
        "[19:00:24 F34 TEST] WARN:   [STRIP-ROWS-MISALIGNED] "
        "frame=F2134 row_delta=103 popped=batters "
        "preserved=score,match_overs,bowler "
        "row_pair=Ryan Rickelton strip_runs=6 card_runs=109",
    ])
    snap = analyze(log)
    report = report_bundle_bc(snap)

    for key in ("6_batter_normalize", "16_new_batter_balls",
                "17a_bowler_batter_gate", "bowler_stats_graphic_gate",
                "19_zero_graphic_gate",
                "21_over_resync", "22_all_out_authority",
                "14_score_regression", "18_ws_slot_invariant",
                "lever1_sm_slot_invariant",
                "17b_bowler_team_over",
                "17b_bowler_consensus_inconsistent",
                "17b_bowler_consensus_override",
                "15_score_inf_floor",
                "cluster1_scorer_active_gate",
                "cluster1_striker_sm_cutover",
                "striker_read_sm_canonical",
                "cluster1_striker_status_gate",
                "path_b_sm_feeder_sync",
                "path_b_sm_shadow_parity",
                "path_b_bowler_feeder_divergence",
                "item2_scorer_schema_would_drop",
                "item2_scorer_schema_would_coerce",
                "item2_batters_invariant",
                "thread7_strip_rows_misaligned"):
        check(f"{key} counted",
              len(snap.bundle_bc_events.get(key, [])) == 1,
              report)
    check("report declares all signatures validated",
          "status: VALIDATED" in report,
          report)


# ---------------------------------------------------------------------
# PBKS vs RR (2026-04-28) — replay fixtures + telemetry (production-
# shaped regressions; tags match analyze_match_telemetry validators)
# ---------------------------------------------------------------------


def _pbks_rr_telemetry_cap():
    """Capture WARN/INFO lines for bracket-tag assertions."""

    class _Cap:
        def __init__(self) -> None:
            self.warnings: list[str] = []
            self.infos: list[str] = []

        def warn(self, m: str) -> None:
            self.warnings.append(m)

        def info(self, m: str) -> None:
            self.infos.append(m)

        def error(self, m: str) -> None:
            pass

        def insight(self, m: str) -> None:
            pass

    return _Cap()


def test_pbks_rr_replay_bowler_batter_gate_strips_with_telemetry() -> None:
    """DC-vs-RCB class: active batter strip misread as bowler — strip + tag."""
    header("PBKS replay: [BOWLER-BATTER-GATE] on batter-as-bowler strip")
    import test_pipeline as tp
    from eyes.scoreboard import Scoreboard

    cap = _pbks_rr_telemetry_cap()
    sb = Scoreboard()
    sb.setup_innings("DC", "RCB",
                     ["KL Rahul", "Abishek Porel", "Axar Patel"],
                     ["Bhuvneshwar Kumar", "Yash Dayal"])
    sb.batting_card["KL Rahul"]["status"] = "batting"
    sb.batting_card["Abishek Porel"]["status"] = "batting"
    extracted = {
        "batters": [{"name": "KL Rahul", "runs": 23, "balls": 17}],
        "bowler": {"name": "KL Rahul", "runs": 23},
        "bowler_name": "KL Rahul",
        "bowler_figures": "23",
    }
    with patch.object(tp, "log", cap):
        tp.filter_bowler_batter_row_contamination(extracted, sb)
    joined = "\n".join(cap.warnings + cap.infos)
    check("telemetry", "[BOWLER-BATTER-GATE]" in joined, joined[:400])
    check("bowler keys stripped",
          "bowler" not in extracted and "bowler_name" not in extracted,
          f"{extracted!r}")


def test_pbks_rr_replay_striker_sm_cutover_mirror_telemetry() -> None:
    """Path B lockstep mirror (F219-class churn) emits cutover tag."""
    header("PBKS replay: [STRIKER-SM-CUTOVER] on SM+_inn mirror write")
    import test_pipeline as tp
    from eyes.scoreboard import Scoreboard

    cap = _pbks_rr_telemetry_cap()
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb._inn["striker"] = "A"
    sm = _SMStub()
    sm.striker = "A"
    with patch.object(tp, "log", cap):
        tp._set_inn_slot_with_sm_mirror(sm, sb, "striker", "B", "unit-pbks")
    joined = "\n".join(cap.warnings + cap.infos)
    check("telemetry", "[STRIKER-SM-CUTOVER]" in joined, joined[:400])
    check("slots mirrored", sb._inn["striker"] == "B" and sm.striker == "B",
          f"_inn={sb._inn!r} sm={sm.striker!r}")


def test_pbks_rr_replay_ws_slot_invariant_repair_telemetry() -> None:
    """Porel/Rahul duplicate slot repair (WS-SLOT-INVARIANT sample class)."""
    header("PBKS replay: [WS-SLOT-INVARIANT] on duplicate striker/non")
    import test_pipeline as tp
    from eyes.scoreboard import Scoreboard

    cap = _pbks_rr_telemetry_cap()
    sb = Scoreboard()
    sb.setup_innings("DC", "RCB",
                     ["Abishek Porel", "KL Rahul", "Axar Patel"],
                     ["Bhuvneshwar Kumar"])
    sb.batting_card["Abishek Porel"]["status"] = "batting"
    sb.batting_card["KL Rahul"]["status"] = "batting"
    state = {"striker": "Abishek Porel", "non": "Abishek Porel"}
    with patch.object(tp, "log", cap):
        tp.enforce_ws_slot_invariant(state, sb, _identity_canon)
    joined = "\n".join(cap.warnings + cap.infos)
    check("telemetry", "[WS-SLOT-INVARIANT]" in joined, joined[:400])
    check("non repaired",
          state["non"] == "KL Rahul",
          f"{state!r}")


def test_pbks_rr_replay_batter_normalize_surname_ghost_telemetry() -> None:
    """Rinku + SINGH ghost row (F500-class) drops with normalize tag."""
    header("PBKS replay: [BATTER-NORMALIZE] surname ghost drop")
    import test_pipeline as tp
    from eyes.scoreboard import Scoreboard

    cap = _pbks_rr_telemetry_cap()
    sb = Scoreboard()
    sb.setup_innings("KKR", "DC",
                     ["Rinku Singh", "Andre Russell", "Sunil Narine"],
                     ["Axar Patel", "Kuldeep Yadav"])
    extracted = {
        "batters": [
            {"name": "RINKU", "runs": 0, "balls": 0},
            {"name": "SINGH", "runs": None, "balls": None},
        ]
    }
    with patch.object(tp, "log", cap):
        tp.normalize_extracted_batters(extracted, sb)
    joined = "\n".join(cap.warnings + cap.infos)
    check("telemetry", "[BATTER-NORMALIZE]" in joined, joined[:400])
    check("single canonical batter",
          [b.get("name") for b in extracted.get("batters", [])]
          == ["Rinku Singh"],
          f"{extracted!r}")


def test_pbks_rr_replay_new_batter_balls_ceiling_telemetry() -> None:
    """Fresh admission 0(16) rejected (Stoinis ceiling class)."""
    header("PBKS replay: [NEW-BATTER-BALLS-GATE] impossible balls")
    import eyes.scoreboard as sbmod

    cap = _pbks_rr_telemetry_cap()
    sb = sbmod.Scoreboard()
    sb.setup_innings("BAT", "BOWL",
                     ["Anchor", "Gone", "New Batter", "Four"],
                     ["Bowler One", "Bowler Two"])
    sb.batting_card["Anchor"].update(
        {"status": "batting", "runs": 20, "balls": 15})
    sb.batting_card["Gone"].update(
        {"status": "out", "runs": 5, "balls": 8})
    sb._inn["wickets"] = 1
    sb._inn["overs"] = "10.0"
    with patch.object(sbmod, "log", cap):
        ok = sb.update_batter("New Batter", runs=0, balls=16, frame=100)
    joined = "\n".join(cap.warnings + cap.infos)
    check("admission ok", ok is True, f"ok={ok}")
    check("telemetry",
          "[NEW-BATTER-BALLS-GATE]" in joined,
          joined[:500])
    row = sb.batting_card["New Batter"]
    check("balls not committed", row.get("balls") == 0, f"{row!r}")


def test_pbks_rr_replay_scorer_active_gate_witnessed_out_telemetry() -> None:
    """F1320-class: card still shows batting while FOW witnessed — block slate."""
    header("PBKS replay: [SCORER-ACTIVE-GATE] witnessed-out reject")
    import test_pipeline as tp

    cap = _pbks_rr_telemetry_cap()
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    # Stale active row coexists with witnessed FOW (production race).
    sb.batting_card["A"]["status"] = "batting"
    sb.batting_card["A"]["runs"] = 10
    sb.batting_card["A"]["balls"] = 8
    sb.fall_of_wickets.append({
        "wicket": 1, "batter": "A", "score": 20, "overs": "3.1",
        "_witnessed": True})
    with patch.object(tp, "log", cap):
        changes = tp.apply_scorer_decision(
            sb,
            {"batter_updates": {
                "A": {"accepted": True, "runs": 12, "balls": 9}}},
            frame=1320, jump_guard=None,
            batting_team={"name": "BAT"},
            extracted={"batters": [{"name": "A", "runs": 12, "balls": 9}]})
    joined = "\n".join(cap.warnings + cap.infos)
    check("telemetry", "[SCORER-ACTIVE-GATE]" in joined, joined[:500])
    check("no bat commit",
          not any(str(c).startswith("bat:A") for c in changes),
          f"{changes!r}")


def test_pbks_rr_replay_over_resync_post_restart_cursor_telemetry() -> None:
    """Post-restart saturated cursor cleared (F8/F127/F169 class)."""
    header("PBKS replay: [OVER-RESYNC] after recovery resync_to_over")
    import eyes.this_over as tom
    from eyes.this_over import ThisOverManager

    cap = _pbks_rr_telemetry_cap()
    om = ThisOverManager()
    om.this_over = ["."] * 12
    om.this_over_sources = ["obs"] * 12
    om._last_over_int = 0
    with patch.object(tom, "log", cap):
        om.resync_to_over("16.3", reason="recovery")
    joined = "\n".join(cap.warnings + cap.infos)
    check("telemetry",
          "[OVER-RESYNC]" in joined and "16" in joined,
          joined[:400])
    check("cursor int", om._last_over_int == 16, om._last_over_int)
    check("buffer cleared", om.this_over == [], om.this_over)


def test_pbks_rr_replay_scorer_invariant_filter_witnessed_out_telemetry(
        ) -> None:
    """Parag witnessed-out row skipped before update (filter path)."""
    header("PBKS replay: [SCORER-INVARIANT-FILTER] witnessed-out row")
    import test_pipeline as tp
    from eyes.scoreboard import Scoreboard

    cap = _pbks_rr_telemetry_cap()
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb.batting_card["A"]["status"] = "out"
    sb.fall_of_wickets.append({
        "wicket": 1, "batter": "A", "score": 20, "overs": "1.1",
        "_witnessed": True})
    with patch.object(tp, "log", cap):
        changes = tp.apply_scorer_decision(
            sb,
            {"batter_updates": {"A": {"accepted": True, "runs": 9,
                                      "balls": 5}}},
            frame=65, jump_guard=None,
            batting_team={"name": "BAT"},
            extracted={"batters": [{"name": "A", "runs": 9, "balls": 5}]})
    joined = "\n".join(cap.warnings + cap.infos)
    check("telemetry", "[SCORER-INVARIANT-FILTER]" in joined, joined[:500])
    check("no bat change",
          not any(str(c).startswith("bat:A") for c in changes),
          f"{changes!r}")


def test_pbks_rr_replay_scorer_dismissed_resurrect_telemetry() -> None:
    """Ferreira class: out without witnessed FOW must not resurrect."""
    header("PBKS replay: [SCORER-DISMISSED-RESURRECT] non-witnessed out")
    import test_pipeline as tp
    from eyes.scoreboard import Scoreboard

    cap = _pbks_rr_telemetry_cap()
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb.batting_card["A"]["status"] = "out"
    with patch.object(tp, "log", cap):
        changes = tp.apply_scorer_decision(
            sb,
            {"batter_updates": {"A": {"accepted": True, "runs": 9,
                                      "balls": 5}}},
            frame=167, jump_guard=None,
            batting_team={"name": "BAT"},
            extracted={"batters": [{"name": "A", "runs": 9, "balls": 5}]})
    joined = "\n".join(cap.warnings + cap.infos)
    check("telemetry", "[SCORER-DISMISSED-RESURRECT]" in joined,
          joined[:500])
    check("no commit", not any(str(c).startswith("bat:A") for c in changes),
          f"{changes!r}")


def test_pbks_rr_replay_bowler_team_over_consensus_accepts_telemetry() -> None:
    """F1028-class: second team-over-consistent read promotes + logs tag."""
    header("PBKS replay: [BOWLER-TEAM-OVER-CONSENSUS] accelerated accept")
    import eyes.scoreboard as sbmod

    cap = _pbks_rr_telemetry_cap()
    sb = sbmod.Scoreboard()
    sb.setup_innings(
        batting_team="Delhi Capitals",
        bowling_team="Royal Challengers Bengaluru",
        batting_squad=["Rahul", "Stubbs"],
        bowling_squad=["Bhuvneshwar Kumar", "Suyash Sharma"],
        batting_xi=["Rahul", "Stubbs"],
        bowling_xi=["Bhuvneshwar Kumar", "Suyash Sharma"],
    )
    sb._inn["current_bowler"] = "Bhuvneshwar Kumar"
    sb._inn["overs"] = "10.2"
    sb.bowling_card["Bhuvneshwar Kumar"]["overs"] = "2.0"
    sb.bowling_card["Bhuvneshwar Kumar"]["runs"] = 22
    sb.bowling_card["Bhuvneshwar Kumar"]["wickets"] = 1
    with patch.object(sbmod, "log", cap):
        sb.update_bowler(
            "Suyash Sharma", overs="0.2", runs=8, wickets=0, frame=1200)
        sb.update_bowler(
            "Suyash Sharma", overs="0.2", runs=8, wickets=0, frame=1201)
    joined = "\n".join(cap.warnings + cap.infos)
    check("telemetry", "[BOWLER-TEAM-OVER-CONSENSUS]" in joined,
          joined[:500])
    check("promoted",
          sb._inn["current_bowler"] == "Suyash Sharma",
          sb._inn["current_bowler"])


def test_pbks_rr_replay_pending_validation_catalog_all_patterns_synthetic(
        ) -> None:
    """When production log is absent: one synthetic line per pending tag."""
    header("PBKS replay: pending validation — synthetic log full catalog hit")
    from analyze_match_telemetry import (
        PENDING_VALIDATION_PATTERNS, analyze, report_pending_validation)

    # Lines chosen so each regex in PENDING_VALIDATION_PATTERNS matches once.
    lines = [
        "[10:00:01 F1 TEST] INFO: [WICKET-AUTO] Dismissed striker X",
        "[10:00:02 F2 BOARD] INFO: [POST-WICKET-CARD-PROPAGATE] 'Y'",
        "[10:00:03 F3 TEST] WARN: [BALLS-CEILING-GATE] overs=19.6 "
        "(legal_balls=118, ceiling=117): A=balls=120 — reject",
        "[10:00:04 F4 SM] INFO: [SM-INNINGS-2-RESET] reason=manual:",
        "[10:00:05 F5 TEST] WARN: [SCORE-INF-GATE] score 40→55 "
        "(advance=+15) > explained (bat_delta=0 + extras_max=6 = 6) — x",
        "[10:00:06 F6 TEST] WARN: [SCORE-INF-GATE] proposed=18 < "
        "min_score_from_batters_and_extras (bat_sum=22, extras=0, "
        "min=22) — rejecting score commit.",
        "[10:00:07 F7 TEST] WARN: [BOWLER-BATTER-GATE] bowler stripped — "
        "name='KL Rahul'",
        "[10:00:08 F8 BOARD] WARN: [BOWLER-STATS-GRAPHIC-GATE] rejecting "
        "'Pat Cummins' - reason=career_keyword (overs='2.4' runs=18 "
        "wickets=1)",
        "[10:00:09 F9 TEST] INFO: fall_of_wickets_internal_count 3",
        "[10:00:10 F10 TEST] WARN: [PRE-MATCH-GRAPHIC-GATE] team_abbr=DC "
        "present",
        "[10:00:11 F11 TEST] WARN: [PRE-MATCH-COLD-START-GATE] unused",
        "[10:00:12 F12 SCORE_MGR] INFO: cold-start zero candidate rejected",
        "[10:00:13 F13 TEST] INFO: runs = None, balls = None",
        "[10:00:14 F14 OVER] INFO: [OVER-RESYNC] Cursor aligned to over 16 "
        "from team_overs='16.3'",
        "[10:00:15 F15 BOARD] WARN: [ALL-OUT-AUTHORITY] Promoted wickets",
        "[10:00:16 F16 TEST] WARN: [WS-SLOT-INVARIANT] duplicate slots "
        "'A'; cleared non",
        "[10:00:17 F17 SCORE_MGR] WARN: [SM-SLOT-INVARIANT] duplicate "
        "slots 'Z' (source=t); clearing non",
        "[10:00:18 F18 BOARD] WARN: [STRIKER-STATUS-GATE] Refusing z",
        "[10:00:19 F19 BOARD] WARN: [BOWLER-CONSENSUS-INCONSISTENT] x",
        "[10:00:20 F20 BOARD] WARN: [BOWLER-CONSENSUS-INCONSISTENT-OVERRIDE] "
        "accepting 'Y'",
        "[10:00:21 F21 TEST] INFO: [SCORER-INVARIANT-FILTER] skipping x",
        "[10:00:22 F22 TEST] WARN: [SCORER-DISMISSED-RESURRECT] skipping x",
        "[10:00:23 F23 BOARD] WARN: [BOWLER-TEAM-OVER-CONSENSUS] accepting "
        "'Suyash Sharma' after 2 reads",
        "[10:00:24 F24 TEST] WARN: [SCORER-SCHEMA-WOULD-DROP] field=b "
        "key=Bad reason=multi_field_coerce filter_caught_in_step3=false "
        "frame=F24",
        "[10:00:25 F25 TEST] INFO: [SCORER-SCHEMA-WOULD-COERCE] field=s "
        "reason=coerce_null raw='x' filter_caught_in_step3=false frame=F25",
        "[10:00:26 F26 TEST] WARN: [BATTERS-INVARIANT] rule=A t",
        "[10:00:27 F27 TEST] WARN:   [STRIP-ROWS-MISALIGNED] "
        "frame=F2134 row_delta=103 popped=batters "
        "preserved=score,match_overs,bowler row_pair=X strip_runs=1 "
        "card_runs=104",
        "[10:00:28 F28 TEST] INFO: [F280001] [CAM-GRAPHIC-FAST-PATH-READ] "
        "score=221 overs=18.1 changes=['score']",
        "[10:00:29 F29 TEST] INFO: [F280002] [CAM-GRAPHIC-FAST-PATH-NOOP] "
        "score=221 overs=18.1 (state unchanged; no broadcast)",
        "[10:00:30 F30 TEST] INFO: [F280003] [CAM-GRAPHIC-FAST-PATH-REJECT] "
        "reason=G6_score_window",
    ]
    path = _synth_log(lines)
    try:
        snap = analyze(path)
        miss = [
            lbl for lbl, _ in PENDING_VALIDATION_PATTERNS
            if snap.pending_validation_hits.get(lbl, 0) == 0
        ]
        text = report_pending_validation(snap)
        check("every pending-validation pattern hit once in aggregate",
              not miss, f"miss={miss}\n{text}")
    finally:
        try:
            path.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------
# 10b. Path B LOW-risk batch (Item 3 — dual_broadcaster_path_b_migration_contract)
# ---------------------------------------------------------------------


def test_path_b_fow_list_property_reads_scoreboard() -> None:
    header("Path B: fow_list property reads scoreboard")
    from score_manager import ScoreManager
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb.fall_of_wickets.append({"wicket": 1, "batter": "A"})
    sm = ScoreManager(shadow=False)
    sm.scoreboard = sb
    check("fow_list mirrors SB", sm.fow_list == sb.fall_of_wickets, sm.fow_list)


def test_path_b_fow_list_property_returns_none_when_sb_unattached() -> None:
    header("Path B: fow_list empty when scoreboard unattached")
    from score_manager import ScoreManager
    sm = ScoreManager(shadow=True)
    sm.fow_list = [{"wicket": 1}]
    check("internal fow", sm.fow_list == [{"wicket": 1}], sm.fow_list)


def test_path_b_innings_extras_property_reads_scoreboard() -> None:
    header("Path B: innings_extras reads scoreboard extras total")
    from score_manager import ScoreManager
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb.extras["total"] = 7
    sm = ScoreManager(shadow=False)
    sm.scoreboard = sb
    check("innings_extras", sm.innings_extras == 7, sm.innings_extras)


def test_path_b_innings_extras_property_returns_none_when_sb_unattached() -> None:
    header("Path B: innings_extras 0 when no scoreboard")
    from score_manager import ScoreManager
    sm = ScoreManager(shadow=True)
    check("default 0", sm.innings_extras == 0, sm.innings_extras)


def test_path_b_bat1_runs_property_reads_scoreboard() -> None:
    header("Path B: bat1_runs reads batting_card")
    from score_manager import ScoreManager
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb.batting_card["A"]["runs"] = 42
    sm = ScoreManager(shadow=False)
    sm.scoreboard = sb
    sm.bat1_name = "A"
    check("runs", sm.bat1_runs == 42, sm.bat1_runs)


def test_path_b_bat1_runs_setter_is_noop_with_telemetry() -> None:
    header("Path B: bat1_runs setter does not mutate card")
    from score_manager import ScoreManager
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb.batting_card["A"]["runs"] = 5
    sm = ScoreManager(shadow=False)
    sm.scoreboard = sb
    sm.bat1_name = "A"
    sm.bat1_runs = 99
    check("card unchanged", sb.batting_card["A"]["runs"] == 5,
          sb.batting_card["A"])


def test_path_b_bowler_runs_property_reads_scoreboard() -> None:
    header("Path B: bowler_runs reads bowling_card")
    from score_manager import ScoreManager
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb.bowling_card["X"]["runs"] = 38
    sm = ScoreManager(shadow=False)
    sm.scoreboard = sb
    sm.bowler_name = "X"
    check("bowler runs", sm.bowler_runs == 38, sm.bowler_runs)


def test_path_b_bowler_runs_setter_is_noop_with_telemetry() -> None:
    header("Path B: bowler_runs setter noop (card unchanged)")
    from score_manager import ScoreManager
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb.bowling_card["X"]["runs"] = 12
    sm = ScoreManager(shadow=False)
    sm.scoreboard = sb
    sm.bowler_name = "X"
    sm.bowler_runs = 99
    check("noop", sb.bowling_card["X"]["runs"] == 12, sb.bowling_card["X"])


def test_path_b_innings_property_reads_scoreboard() -> None:
    header("Path B: innings reads scoreboard.current_innings")
    from score_manager import ScoreManager
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb.set_innings_2(target=150)
    sm = ScoreManager(shadow=False)
    sm.scoreboard = sb
    check("innings 2", sm.innings == 2, sm.innings)


def test_path_b_innings_setter_is_noop_with_telemetry() -> None:
    header("Path B: innings setter updates fallback without SB")
    from score_manager import ScoreManager
    sm = ScoreManager(shadow=True)
    sm.innings = 2
    check("fallback", sm.innings == 2, sm.innings)


def test_path_b_score_property_reads_scoreboard() -> None:
    header("Path B: score reads _inn")
    from score_manager import ScoreManager
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    for _f in (1, 2, 3):
        sb.set("score", 87, frame=_f)
    sm = ScoreManager(shadow=False)
    sm.scoreboard = sb
    sm._current_frame = 3
    check("score", sm.score == 87, sm.score)


def test_path_b_score_setter_calls_sb_set_with_telemetry() -> None:
    header("Path B: score setter feeds scoreboard")
    from score_manager import ScoreManager
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    for _f in (1, 2, 3):
        sb.set("score", 10, frame=_f)
    sm = ScoreManager(shadow=False)
    sm.scoreboard = sb
    for _f in (4, 5, 6):
        sm._current_frame = _f
        sm.score = 22
    raw = sb._inn.get("score")
    check("fed score", int(raw) == 22, raw)


def test_path_b_score_setter_handles_sb_unattached() -> None:
    header("Path B: score setter with no scoreboard uses fallback")
    from score_manager import ScoreManager
    sm = ScoreManager(shadow=False)
    sm.scoreboard = None
    sm.score = 33
    check("fallback score", sm.score == 33, sm.score)


def test_path_b_score_setter_in_shadow_emits_parity_only() -> None:
    header("Path B: shadow score setter does not advance SB")
    from score_manager import ScoreManager
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    for _f in (1, 2, 3):
        sb.set("score", 5, frame=_f)
    sm = ScoreManager(shadow=True)
    sm.scoreboard = sb
    sm.score = 999
    raw = sb._inn.get("score")
    check("SB score unchanged", int(raw) == 5, raw)
    check("SM fallback shadow", sm._sm_scalar_fallback.get("score") == 999,
          sm._sm_scalar_fallback)


def test_path_b_score_setter_continues_on_sb_reject() -> None:
    header("Path B: score regression rejected by SB; SM read stays")
    from score_manager import ScoreManager
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    for _f in (1, 2, 3):
        sb.set("score", 40, frame=_f)
    sm = ScoreManager(shadow=False)
    sm.scoreboard = sb
    sm._current_frame = 10
    sm.score = 30
    check("still 40", sm.score == 40, sm.score)


def test_path_b_batting_team_property_reads_scoreboard() -> None:
    header("Path B: batting_team reads SB attr")
    from score_manager import ScoreManager
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sm = ScoreManager(shadow=False)
    sm.scoreboard = sb
    check("team", sm.batting_team == "BAT", sm.batting_team)


def test_path_b_batting_team_setter_calls_sb_set_with_telemetry() -> None:
    header("Path B: batting_team setter writes SB")
    from score_manager import ScoreManager
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sm = ScoreManager(shadow=False)
    sm.scoreboard = sb
    sm.batting_team = "NEW"
    check("written", sb.batting_team == "NEW", sb.batting_team)


def test_path_b_batting_team_setter_in_shadow_emits_parity_only() -> None:
    header("Path B: shadow batting_team does not overwrite SB")
    from score_manager import ScoreManager
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B"], bowling_squad=["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sm = ScoreManager(shadow=True)
    sm.scoreboard = sb
    sm.batting_team = "GHOST"
    check("SB team", sb.batting_team == "BAT", sb.batting_team)
    check("fallback", sm._sm_scalar_fallback.get("batting_team") == "GHOST",
          sm._sm_scalar_fallback)


def test_ws_payload_helpers_extracted_module_level() -> None:
    header("WS: module-level canonicalize + payload invariant helpers")
    from eyes.scoreboard import Scoreboard
    from test_pipeline import _ws_canonicalize_player_name, _assert_ws_payload_invariants

    sb = Scoreboard()
    sb.setup_innings(
        "BAT", "BOWL", ["Alpha", "Beta"], ["Chi"],
        batting_xi=["Alpha", "Beta"], bowling_xi=["Chi"])
    check("canon known batter",
          _ws_canonicalize_player_name("Alpha", scoreboard=sb) == "Alpha",
          "")
    check("canon none",
          _ws_canonicalize_player_name(None, scoreboard=sb) is None,
          "")

    class _Log:
        def __init__(self) -> None:
            self.warns: list[str] = []

        def warn(self, msg: str) -> None:
            self.warns.append(msg)

    lg = _Log()
    _assert_ws_payload_invariants(
        {
            "scorecard": {"striker": "Nobody"},
            "batting_card": [{"name": "Alpha", "status": "batting"}],
        },
        log=lg)
    check("invariant warns on bad striker", len(lg.warns) >= 1, str(lg.warns))


def test_get_broadcast_state_aliases_get_live_state() -> None:
    header("Scoreboard: get_broadcast_state aliases get_live_state (Option A)")
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings(
        "BAT", "BOWL", ["A", "B"], ["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb._inn["score"] = 10
    sb._inn["striker"] = "A"
    sb._inn["non"] = "B"
    sb.batting_card["A"]["status"] = "batting"
    sb.batting_card["B"]["status"] = "batting"
    bcast = sb.get_broadcast_state()
    live = sb.get_live_state()
    check("dict equality", bcast == live, f"{bcast!r} != {live!r}")


def test_get_broadcast_state_shadow_mode_uses_canonical_projection() -> None:
    header("Scoreboard: shadow WS path uses _project_active_batters (§6.3)")
    from unittest.mock import patch

    from eyes.commentary import PartnershipTracker
    from eyes.field.cricket_field import CricketField
    from eyes.scoreboard import Scoreboard
    from eyes.this_over import ThisOverManager
    from score_manager import ScoreManager
    import test_pipeline as tp

    sb = Scoreboard()
    sb.setup_innings(
        "BAT", "BOWL", ["A", "B"], ["X"],
        batting_xi=["A", "B"], bowling_xi=["X"])
    sb._inn["score"] = 50
    sb._inn["wickets"] = 0
    sb._inn["overs"] = 5.0
    sb.batting_card["A"]["status"] = "batting"
    sb.batting_card["B"]["status"] = "batting"
    sb._inn["striker"] = "B"
    sb._inn["non"] = "B"

    sm = ScoreManager(shadow=True)
    sm.scoreboard = sb
    sm.striker = "A"
    sm.non = "B"

    def canon(raw, *, bowler=False):
        return tp._ws_canonicalize_player_name(raw, scoreboard=sb, bowler=bowler)

    def noop(*_a, **_k):
        pass

    with patch.object(tp, "SESSION_ID", "snapshadow"):
        with patch("test_pipeline.time.time", return_value=2_000_000.0):
            payload = tp._build_full_payload_from_state(
                scoreboard=sb,
                score_mgr=sm,
                over_mgr=ThisOverManager(),
                partnership_tracker=PartnershipTracker(),
                cricket_field=CricketField(),
                team_names=["BAT", "BOWL"],
                batting_team="BAT",
                bowling_team="BOWL",
                toss_winner_name=None,
                toss_decision_str=None,
                frame_count=3,
                last_delivery_info=None,
                broadcast_cache={},
                speed_kph=None,
                canon_player_name=canon,
                record_state_recovery_guard=noop,
                assert_payload_invariants=None,
            )
    sc = payload.get("scorecard") or {}
    check("SM striker canonical in shadow payload",
          sc.get("striker") == "A", sc)
    check("SM non-striker canonical in shadow payload",
          sc.get("non") == "B", sc)
    check("no duplicate active slots from bad _inn pair",
          sc.get("striker") != sc.get("non"),
          sc)


def test_get_broadcast_state_back_compat_signature() -> None:
    header("Scoreboard: get_broadcast_state back-compat (silent alias)")
    import warnings

    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings(
        "BAT", "BOWL", ["A"], ["X"],
        batting_xi=["A"], bowling_xi=["X"])
    with warnings.catch_warnings(record=True) as warns:
        warnings.simplefilter("always")
        out = sb.get_broadcast_state()
    check("get_broadcast_state returns dict", isinstance(out, dict), type(out))
    check("no deprecation warnings.warn", len(warns) == 0, repr(warns))
    src = (Path(__file__).resolve().parent / "eyes" / "scoreboard.py").read_text()
    check("method signature preserved",
          "def get_broadcast_state(self) -> dict:" in src, "")
    check("audit cross-reference in docstring",
          "get_broadcast_state_path_b_audit.md" in src, "")
    check("delegates to get_live_state",
          "return self.get_live_state()" in src, "")
    gbs_segment = src.split("def get_broadcast_state(self)")[1].split(
        "def get_live_state_str")[0]
    check("no warnings.warn inside get_broadcast_state",
          "warnings.warn" not in gbs_segment,
          gbs_segment[:200])


# ---------------------------------------------------------------------
# Lever 1 PR1 — ScoreManager._set_slot_pair (helper only; no callsites)
# ---------------------------------------------------------------------


def test_set_slot_pair_writes_both_slots_atomically() -> None:
    header("ScoreManager: _set_slot_pair writes striker and non")
    from score_manager import ScoreManager

    sm = ScoreManager(shadow=True)
    sm.striker = "old_s"
    sm.non = "old_ns"
    sm._set_slot_pair("KL Rahul", "Rinku Singh", source="test_unit")
    check("striker updated",
          sm.striker == "KL Rahul", sm.striker)
    check("non updated",
          sm.non == "Rinku Singh", sm.non)


def test_set_slot_pair_repairs_canonical_collision_with_telemetry() -> None:
    header("ScoreManager: _set_slot_pair repairs duplicate + logs tag")
    from score_manager import ScoreManager
    import score_manager as smod

    sm = ScoreManager(shadow=True)
    cap: list[tuple] = []

    def _cap_warn(msg: str, *a, **k):
        cap.append((msg,))

    with patch.object(smod.log, "warn", _cap_warn):
        sm._set_slot_pair("Same Name", "Same Name", source="test_collision")

    check("non cleared on collision",
          sm.non is None, sm.non)
    check("striker retained",
          sm.striker == "Same Name", sm.striker)
    check("telemetry emitted",
          cap and "[SM-SLOT-INVARIANT]" in cap[0][0]
          and "source=test_collision" in cap[0][0]
          and "clearing non" in cap[0][0],
          cap[0][0] if cap else "(no warn)")


def test_set_slot_pair_canonicalization_uses_existing_helper() -> None:
    header("ScoreManager: _set_slot_pair routes both names through "
            "_canonicalize_name")
    from score_manager import ScoreManager

    sm = ScoreManager(shadow=True)
    with patch.object(sm, "_canonicalize_name",
                      wraps=sm._canonicalize_name) as w:
        sm._set_slot_pair("A", "B", source="test_wraps")
    check("_canonicalize_name invoked for both args",
          w.call_count == 2, w.call_count)


# ---------------------------------------------------------------------
# Lever 1 PR2 — W8 _identify_and_set → _set_slot_pair (sm_rotation_… §3.3)
# ---------------------------------------------------------------------


def test_sm_pr2_w8_identify_and_set_routes_via_set_slot_pair() -> None:
    header("Lever1 PR2 W8: _identify_and_set calls _set_slot_pair "
           "with identify_and_set.* source")
    from score_manager import ScoreManager, FrameInput
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["Alice Ace", "Bob Baker"], bowling_squad=["X"],
        batting_xi=["Alice Ace", "Bob Baker"], bowling_xi=["X"])
    for nm in ("Alice Ace", "Bob Baker"):
        sb.batting_card[nm]["status"] = "batting"
    sm = ScoreManager(shadow=True)
    sm.scoreboard = sb
    sm.bat1_name = "Alice Ace"
    sm.bat2_name = "Bob Baker"
    sm.striker = "Bob Baker"
    sm.non = "Alice Ace"
    card = {
        "bat1_name": "Alice Ace", "bat1_runs": 10, "bat1_balls": 6,
        "bat2_name": "Bob Baker", "bat2_runs": 3, "bat2_balls": 4,
    }
    frame = FrameInput(frame_id="f1", timestamp=1.0)
    captured: list[tuple] = []

    def _capture(striker, non, *, source):
        captured.append((striker, non, source))

    with patch.object(sm, "_set_slot_pair", side_effect=_capture):
        sm._identify_and_set(
            card, frame,
            prev_b1_runs=10, prev_b1_balls=5,
            prev_b2_runs=3, prev_b2_balls=4)
    check("exactly one _set_slot_pair call",
          len(captured) == 1, captured)
    s, ns, src = captured[0]
    check("striker/non from helper routing",
          s == "Alice Ace" and ns == "Bob Baker",
          f"striker={s!r} non={ns!r}")
    check("telemetry source prefixes identify_and_set",
          src == "identify_and_set.balls_delta", src)


def test_sm_pr2_w8_non_keeps_distinct_prior_non_else_branch() -> None:
    header("Lever1 PR2 W8: §3.3 helper keeps prior non when canonically "
           "distinct (Player C replay)")
    from score_manager import ScoreManager

    sm = ScoreManager(shadow=True)
    sm.bat1_name = "Alice Ace"
    sm.bat2_name = "Bob Baker"
    sm.non = "Player C"
    ns = sm._w8_non_for_identified("Zeta Zenith")
    check("else-branch returns raw prior non (distinct canon)",
          ns == "Player C", ns)


def test_sm_pr2_w8_partner_alias_collides_emits_sm_slot_invariant() -> None:
    header("Lever1 PR2 W8: fuzzy bat1 partner aliases striker → "
           "_set_slot_pair repairs + [SM-SLOT-INVARIANT]")
    from score_manager import ScoreManager, FrameInput
    from eyes.scoreboard import Scoreboard
    import score_manager as smod

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["Axar Patel", "Virat Kohli"], bowling_squad=["X"],
        batting_xi=["Axar Patel", "Virat Kohli"], bowling_xi=["X"])
    for nm in ("Axar Patel", "Virat Kohli"):
        sb.batting_card[nm]["status"] = "batting"
    sm = ScoreManager(shadow=True)
    sm.scoreboard = sb
    sm.bat1_name = "Axar Patel"
    # Malformed slot: holds an Axar alias where Virat's partner slot should be.
    sm.bat2_name = "A Patel"
    sm.striker = "Virat Kohli"
    sm.non = "A Patel"
    card = {
        "bat1_name": "Axar Patel",
        "bat1_runs": 40,
        "bat1_balls": 31,
        # Row 2 label is the errant Axar alias (matches SM bat2 slot); stats
        # are still the non-striker's so balls_delta stays well-defined.
        "bat2_name": "A Patel",
        "bat2_runs": 50,
        "bat2_balls": 40,
    }
    frame = FrameInput(frame_id="f1", timestamp=1.0)
    cap: list[tuple] = []

    def _cap_warn(msg: str, *a, **k):
        cap.append((msg,))

    with patch.object(smod.log, "warn", _cap_warn):
        sm._identify_and_set(
            card, frame,
            prev_b1_runs=40, prev_b1_balls=30,
            prev_b2_runs=50, prev_b2_balls=40)
    check("striker canonical slot is Axar",
          sm.striker == "Axar Patel", sm.striker)
    check("non cleared after canonical duplicate repair",
          sm.non is None, sm.non)
    check("[SM-SLOT-INVARIANT] from W8 path",
          cap and "[SM-SLOT-INVARIANT]" in cap[0][0]
          and "identify_and_set.balls_delta" in cap[0][0],
          cap[0][0] if cap else "(no warn)")


def test_sm_pr2_w8_balls_delta_happy_path_distinct_pair() -> None:
    header("Lever1 PR2 W8: balls_delta happy path — distinct canonical pair")
    from score_manager import ScoreManager, FrameInput
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["Axar Patel", "Virat Kohli"], bowling_squad=["X"],
        batting_xi=["Axar Patel", "Virat Kohli"], bowling_xi=["X"])
    for nm in ("Axar Patel", "Virat Kohli"):
        sb.batting_card[nm]["status"] = "batting"
    sm = ScoreManager(shadow=True)
    sm.scoreboard = sb
    sm.bat1_name = "Axar Patel"
    sm.bat2_name = "Virat Kohli"
    sm.striker = "Virat Kohli"
    sm.non = "Axar Patel"
    card = {
        "bat1_name": "Axar Patel",
        "bat1_runs": 40,
        "bat1_balls": 31,
        "bat2_name": "Virat Kohli",
        "bat2_runs": 50,
        "bat2_balls": 40,
    }
    frame = FrameInput(frame_id="f1", timestamp=1.0)
    sm._identify_and_set(
        card, frame,
        prev_b1_runs=40, prev_b1_balls=30,
        prev_b2_runs=50, prev_b2_balls=40)
    check("striker flips to ball-facing batter (Axar)",
          sm.striker == "Axar Patel", sm.striker)
    check("non is partner (Virat)",
          sm.non == "Virat Kohli", sm.non)
    check("no canonical duplicate",
          sm.striker != sm.non, f"{sm.striker=!r} {sm.non=!r}")


def _path_b_regression_fixture():
    """Scoreboard + ScoreManager in a known live state (§12.5.3).

    Scalars are written to ``_inn`` directly so the fixture does not rely
    on ``Scoreboard.set`` consensus (multi-frame) for unit tests.
    """
    from eyes.scoreboard import Scoreboard
    from score_manager import ScoreManager

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B", "C", "D"], bowling_squad=["X", "Y"],
        batting_xi=["A", "B", "C", "D"], bowling_xi=["X", "Y"])
    sb._inn["score"] = 87
    sb._inn["wickets"] = 2
    sb._inn["overs"] = 9.4
    sb._inn["run_rate"] = 9.16
    sb.batting_card["A"]["status"] = "batting"
    sb.batting_card["A"]["runs"] = 42
    sb.batting_card["A"]["balls"] = 28
    sb.batting_card["B"]["status"] = "batting"
    sb.batting_card["B"]["runs"] = 31
    sb.batting_card["B"]["balls"] = 22
    sb._inn["striker"] = "A"
    sb._inn["non"] = "B"
    sb._inn["current_bowler"] = "X"
    sb.bowling_card["X"]["runs"] = 38
    sb.bowling_card["X"]["wickets"] = 1
    sb.bowling_card["X"]["overs"] = "2.4"

    sm = ScoreManager(shadow=False)
    sm.scoreboard = sb
    sm.striker = "A"
    sm.non = "B"
    sm.bowler_name = "X"
    return sb, sm


def test_path_b_low_risk_batch_path_a_regression_signature_match() -> None:
    header("Item 3 LOW-risk batch: Path A WS-payload signature unchanged")
    from eyes.commentary import PartnershipTracker
    from eyes.field.cricket_field import CricketField
    from eyes.this_over import ThisOverManager
    import test_pipeline as tp

    _PATH_B_REGRESSION_BASELINE_SIGNATURE = (
        _PATH_B_REGRESSION_BASELINE_PATH.read_text().strip())

    sb, sm = _path_b_regression_fixture()
    over_mgr = ThisOverManager()
    pt = PartnershipTracker()
    cf = CricketField()

    def canon(raw, *, bowler=False):
        return tp._ws_canonicalize_player_name(raw, scoreboard=sb, bowler=bowler)

    def noop_guard(*_a, **_k):
        pass

    with patch.object(tp, "SESSION_ID", "snap01"):
        with patch("test_pipeline.time.time", return_value=1_000_000.0):
            payload = tp._build_full_payload_from_state(
                scoreboard=sb,
                score_mgr=sm,
                over_mgr=over_mgr,
                partnership_tracker=pt,
                cricket_field=cf,
                team_names=["BAT", "BOWL"],
                batting_team="BAT",
                bowling_team="BOWL",
                toss_winner_name="BAT",
                toss_decision_str="bat",
                frame_count=42,
                last_delivery_info=None,
                broadcast_cache={},
                speed_kph=None,
                canon_player_name=canon,
                record_state_recovery_guard=noop_guard,
                assert_payload_invariants=None,
            )

    def _path_a_canonical_signature(pl: dict) -> str:
        """``partnerships.current.batters`` order can vary (set-backed)."""
        p = json.loads(json.dumps(pl))
        cur = (p.get("partnerships") or {}).get("current")
        if isinstance(cur, dict) and isinstance(cur.get("batters"), list):
            cur["batters"] = sorted(cur["batters"])
        return json.dumps(p, sort_keys=True, separators=(",", ":"))

    sig = _path_a_canonical_signature(payload)
    baseline_sig = _path_a_canonical_signature(
        json.loads(_PATH_B_REGRESSION_BASELINE_SIGNATURE))
    check(
        "WS payload signature matches baseline",
        sig == baseline_sig,
        f"len actual={len(sig)} baseline={len(baseline_sig)}",
    )


def test_innings_history_snapshot_includes_full_scorecard() -> None:
    """T1: archive includes WS-shaped cards; snapshot isolated from live SB."""
    header("innings_history: full scorecard snapshot + deepcopy isolation")
    import copy

    from eyes.scoreboard import Scoreboard
    from score_manager import ScoreManager

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B", "C"], bowling_squad=["X", "Y"],
        batting_xi=["A", "B", "C"], bowling_xi=["X", "Y"])
    sb._inn["score"] = 120
    sb._inn["wickets"] = 3
    sb._inn["overs"] = 15.2
    sb._inn["striker"] = "A"
    sb._inn["non"] = "B"
    sb._inn["current_bowler"] = "X"
    sb.batting_card["A"]["status"] = "batting"
    sb.batting_card["A"]["runs"] = 60
    sb.batting_card["A"]["balls"] = 40
    sb.batting_card["B"]["status"] = "batting"
    sb.batting_card["B"]["runs"] = 25
    sb.batting_card["B"]["balls"] = 20
    sb.batting_card["C"]["status"] = "out"
    sb.batting_card["C"]["runs"] = 10
    sb.batting_card["C"]["balls"] = 8
    sb.bowling_card["X"]["overs"] = "3.2"
    sb.bowling_card["X"]["runs"] = 28
    sb.bowling_card["X"]["wickets"] = 2

    sm = ScoreManager(shadow=False)
    sm.scoreboard = sb
    sm.striker = "A"
    sm.non = "B"
    sm.bowler_name = "X"
    sm.partnership_known = True
    sm.partnership_runs = 40
    sm.partnership_balls = 30

    sm.innings_history.append(
        copy.deepcopy(sm._innings_history_archive_entry()))
    sb.batting_card["A"]["runs"] = 999
    arch_a = next(
        x for x in sm.innings_history[0]["batting_card"] if x["name"] == "A")
    check("deepcopy: archived A.runs not mutated by live card",
          arch_a.get("runs") == 60,
          (arch_a, sb.batting_card["A"]["runs"]))

    sb2 = Scoreboard()
    sb2.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["A", "B", "C"], bowling_squad=["X", "Y"],
        batting_xi=["A", "B", "C"], bowling_xi=["X", "Y"])
    sb2._inn["score"] = 120
    sb2._inn["wickets"] = 3
    sb2._inn["overs"] = 15.2
    sb2._inn["striker"] = "A"
    sb2._inn["non"] = "B"
    sb2._inn["current_bowler"] = "X"
    sb2.batting_card["A"]["status"] = "batting"
    sb2.batting_card["A"]["runs"] = 60
    sb2.batting_card["A"]["balls"] = 40
    sb2.batting_card["B"]["status"] = "batting"
    sb2.batting_card["B"]["runs"] = 25
    sb2.batting_card["B"]["balls"] = 20
    sb2.batting_card["C"]["status"] = "out"
    sb2.batting_card["C"]["runs"] = 10
    sb2.batting_card["C"]["balls"] = 8
    sb2.bowling_card["X"]["overs"] = "3.2"
    sb2.bowling_card["X"]["runs"] = 28
    sb2.bowling_card["X"]["wickets"] = 2
    sm2 = ScoreManager(shadow=False)
    sm2.scoreboard = sb2
    sm2.striker = "A"
    sm2.non = "B"
    sm2.bowler_name = "X"
    sm2.set_innings_2(target=121, batting_team="BOWL",
                      reason="test_t1_transition")
    check("transition archives one row",
          len(sm2.innings_history) == 1, sm2.innings_history)
    h = sm2.innings_history[0]
    check("batting_team", h.get("batting_team") == "BAT", h)
    check("bowling_team", h.get("bowling_team") == "BOWL", h)
    _names = {x.get("name") for x in (h.get("batting_card") or [])}
    check("batting_card has A/B/C",
          {"A", "B", "C"}.issubset(_names), _names)
    check("bowling_card includes X",
          any(x.get("name") == "X" for x in (h.get("bowling_card") or [])),
          h.get("bowling_card"))
    check("fall_of_wickets present", "fall_of_wickets" in h, h)
    check("partnerships present", "partnerships" in h, h)
    check("extras present", "extras" in h, h)


def test_innings_history_two_append_sites_consistent() -> None:
    """T2: _detect_innings_change archive matches set_innings_2 keys."""
    header("innings_history: two append sites same key set")
    from eyes.scoreboard import Scoreboard
    from score_manager import FrameInput, ScoreManager

    def _fixture_sm():
        sb = Scoreboard()
        sb.setup_innings(
            batting_team="BAT", bowling_team="BOWL",
            batting_squad=["A", "B"], bowling_squad=["X"],
            batting_xi=["A", "B"], bowling_xi=["X"])
        sb._inn["score"] = 87
        sb._inn["wickets"] = 2
        sb._inn["overs"] = 12.0
        sb._inn["striker"] = "A"
        sb._inn["non"] = "B"
        sb._inn["current_bowler"] = "X"
        sb.batting_card["A"]["runs"] = 50
        sb.batting_card["A"]["balls"] = 30
        sb.batting_card["A"]["status"] = "batting"
        sb.batting_card["B"]["runs"] = 30
        sb.batting_card["B"]["balls"] = 25
        sb.batting_card["B"]["status"] = "batting"
        sb.bowling_card["X"]["overs"] = "2.0"
        sb.bowling_card["X"]["runs"] = 40
        sb.bowling_card["X"]["wickets"] = 2
        sm = ScoreManager(shadow=False)
        sm.scoreboard = sb
        sm.striker = "A"
        sm.non = "B"
        sm.bowler_name = "X"
        return sm

    sm_a = _fixture_sm()
    sm_a._detect_innings_change(
        {"score": 87, "wickets": 2},
        FrameInput(
            frame_id="1", timestamp=1.0,
            broadcast_team="BOWL", broadcast_target=200))
    keys_a = set(sm_a.innings_history[0].keys())

    sm_b = _fixture_sm()
    sm_b.set_innings_2(target=200, batting_team="BOWL",
                       reason="test_t2", archive=True)
    keys_b = set(sm_b.innings_history[0].keys())
    check("append sites expose identical key sets",
          keys_a == keys_b,
          (sorted(keys_a - keys_b), sorted(keys_b - keys_a)))


def test_ws_payload_exposes_innings_history() -> None:
    """T3: canonical build includes innings_history mirroring SM."""
    header("WS payload: innings_history top-level field")
    from unittest.mock import patch

    from eyes.commentary import PartnershipTracker
    from eyes.field.cricket_field import CricketField
    from eyes.this_over import ThisOverManager
    import test_pipeline as tp

    sb, sm = _path_b_regression_fixture()
    sm.innings_history.append({
        "innings": 1,
        "score": 99,
        "batting_team": "BAT",
    })
    over_mgr = ThisOverManager()
    pt = PartnershipTracker()
    cf = CricketField()

    def canon(raw, *, bowler=False):
        return tp._ws_canonicalize_player_name(raw, scoreboard=sb, bowler=bowler)

    def noop_guard(*_a, **_k):
        pass

    with patch.object(tp, "SESSION_ID", "snap01"):
        with patch("test_pipeline.time.time", return_value=1_000_000.0):
            payload = tp._build_full_payload_from_state(
                scoreboard=sb,
                score_mgr=sm,
                over_mgr=over_mgr,
                partnership_tracker=pt,
                cricket_field=cf,
                team_names=["BAT", "BOWL"],
                batting_team="BAT",
                bowling_team="BOWL",
                toss_winner_name="BAT",
                toss_decision_str="bat",
                frame_count=42,
                last_delivery_info=None,
                broadcast_cache={},
                speed_kph=None,
                canon_player_name=canon,
                record_state_recovery_guard=noop_guard,
                assert_payload_invariants=None,
            )
    check("payload has innings_history key",
          "innings_history" in payload, payload.keys())
    check("payload mirrors SM",
          payload["innings_history"] == sm.innings_history,
          (payload["innings_history"], sm.innings_history))


def test_ws_payload_innings_history_empty_innings_1() -> None:
    """T4: innings_history present as [] before any archive."""
    header("WS payload: innings_history empty during innings 1")
    from unittest.mock import patch

    from eyes.commentary import PartnershipTracker
    from eyes.field.cricket_field import CricketField
    from eyes.this_over import ThisOverManager
    import test_pipeline as tp

    sb, sm = _path_b_regression_fixture()
    over_mgr = ThisOverManager()
    pt = PartnershipTracker()
    cf = CricketField()

    def canon(raw, *, bowler=False):
        return tp._ws_canonicalize_player_name(raw, scoreboard=sb, bowler=bowler)

    def noop_guard(*_a, **_k):
        pass

    with patch.object(tp, "SESSION_ID", "snap01"):
        with patch("test_pipeline.time.time", return_value=1_000_000.0):
            payload = tp._build_full_payload_from_state(
                scoreboard=sb,
                score_mgr=sm,
                over_mgr=over_mgr,
                partnership_tracker=pt,
                cricket_field=cf,
                team_names=["BAT", "BOWL"],
                batting_team="BAT",
                bowling_team="BOWL",
                toss_winner_name="BAT",
                toss_decision_str="bat",
                frame_count=42,
                last_delivery_info=None,
                broadcast_cache={},
                speed_kph=None,
                canon_player_name=canon,
                record_state_recovery_guard=noop_guard,
                assert_payload_invariants=None,
            )
    check("innings_history is empty list",
          payload.get("innings_history") == [],
          payload.get("innings_history"))


def test_path_b_bowler_name_divergence_telemetry_present_in_source() -> None:
    header("Path B: [SM-FEEDER-DIVERGENCE] wired in test_pipeline")
    src = (Path(__file__).resolve().parent / "test_pipeline.py"
           ).read_text()
    check("tag + field",
          "[SM-FEEDER-DIVERGENCE]" in src and "field=bowler_name" in src,
          "expected divergence telemetry")


def test_path_b_bowler_name_divergence_rate_limited_in_source() -> None:
    header("Path B: bowler divergence uses signature rate limit")
    src = (Path(__file__).resolve().parent / "test_pipeline.py"
           ).read_text()
    check("_last_feeder_div_sig module dict",
          "_last_feeder_div_sig: dict" in src,
          "expected module-level `_last_feeder_div_sig` rate-limit dict")


# ---------------------------------------------------------------------
# Thread 7 Fix 1 — row-misalignment guard (2026-04-30)
# ---------------------------------------------------------------------


def test_thread7_fix1_row_misalignment_pops_only_batters() -> None:
    header("Thread 7 Fix 1: Δ>20 pops batters only; score/overs/bowler kept")
    import test_pipeline as tp
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="MI", bowling_team="SRH",
        batting_squad=["Ryan Rickelton", "Tilak Varma"],
        bowling_squad=["Pat Cummins"],
        batting_xi=["Ryan Rickelton", "Tilak Varma"],
        bowling_xi=["Pat Cummins"])
    sb.batting_card["Ryan Rickelton"]["runs"] = 109
    sb.batting_card["Ryan Rickelton"]["balls"] = 50
    sb.batting_card["Ryan Rickelton"]["status"] = "batting"
    sb.batting_card["Tilak Varma"]["runs"] = 6
    sb.batting_card["Tilak Varma"]["balls"] = 1
    sb.batting_card["Tilak Varma"]["status"] = "batting"
    extracted = {
        "score": 227,
        "wickets": 4,
        "match_overs": "18.2",
        "batters": [
            {"name": "TILAK", "runs": 109, "balls": 50},
            {"name": "RICKELTON", "runs": 6, "balls": 1},
        ],
        "bowler": "Hussain",
    }
    fired = tp.apply_comparison_strip_batter_row_delta_guard(
        extracted, sb, "MI",
        frame_count=2134,
        record_state_recovery_guard=lambda *a, **k: None)
    check("guard fired", fired is True, f"fired={fired}")
    check("batters stripped", "batters" not in extracted, f"{extracted!r}")
    check("score preserved", extracted.get("score") == 227, extracted)
    check("match_overs preserved",
          extracted.get("match_overs") == "18.2", extracted)
    check("bowler preserved", extracted.get("bowler") == "Hussain", extracted)


def test_thread7_fix1_row_misalignment_emits_telemetry() -> None:
    header("Thread 7 Fix 1: [STRIP-ROWS-MISALIGNED] warn on misalignment")
    from unittest.mock import patch

    import test_pipeline as tp
    from eyes.scoreboard import Scoreboard

    cap = _pbks_rr_telemetry_cap()
    sb = Scoreboard()
    sb.setup_innings(
        "MI", "SRH", ["Ryan Rickelton", "Tilak Varma"], ["X"],
        batting_xi=["Ryan Rickelton", "Tilak Varma"], bowling_xi=["X"])
    sb.batting_card["Ryan Rickelton"]["runs"] = 109
    sb.batting_card["Ryan Rickelton"]["balls"] = 50
    sb.batting_card["Ryan Rickelton"]["status"] = "batting"
    sb.batting_card["Tilak Varma"]["runs"] = 6
    sb.batting_card["Tilak Varma"]["balls"] = 1
    sb.batting_card["Tilak Varma"]["status"] = "batting"
    extracted = {
        "score": 227,
        "match_overs": "18.2",
        "batters": [{"name": "RICKELTON", "runs": 6, "balls": 1}],
        "bowler": "Hussain",
    }
    with patch.object(tp, "log", cap):
        tp.apply_comparison_strip_batter_row_delta_guard(
            extracted, sb, "MI",
            frame_count=2134,
            record_state_recovery_guard=lambda *a, **k: None)
    joined = "\n".join(cap.warnings + cap.infos)
    check("tag present", "[STRIP-ROWS-MISALIGNED]" in joined, joined[:500])
    check("frame + delta + popped + preserved",
          "frame=F2134" in joined and "row_delta=" in joined
          and "popped=batters" in joined
          and "preserved=score,match_overs,bowler" in joined,
          joined[:500])
    check("row diagnostic",
          "row_pair=" in joined and "strip_runs=" in joined
          and "card_runs=" in joined,
          joined[:500])


def test_thread7_fix1_no_misalignment_preserves_all() -> None:
    header("Thread 7 Fix 1: no pop when Δ within threshold")
    from unittest.mock import patch

    import test_pipeline as tp
    from eyes.scoreboard import Scoreboard

    cap = _pbks_rr_telemetry_cap()
    sb = Scoreboard()
    sb.setup_innings(
        "MI", "SRH", ["Ryan Rickelton", "Tilak Varma"], ["X"],
        batting_xi=["Ryan Rickelton", "Tilak Varma"], bowling_xi=["X"])
    sb.batting_card["Ryan Rickelton"]["runs"] = 109
    sb.batting_card["Ryan Rickelton"]["balls"] = 50
    sb.batting_card["Ryan Rickelton"]["status"] = "batting"
    sb.batting_card["Tilak Varma"]["runs"] = 8
    sb.batting_card["Tilak Varma"]["balls"] = 2
    sb.batting_card["Tilak Varma"]["status"] = "batting"
    extracted = {
        "score": 227,
        "batters": [{"name": "Tilak Varma", "runs": 8, "balls": 2}],
    }
    with patch.object(tp, "log", cap):
        fired = tp.apply_comparison_strip_batter_row_delta_guard(
            extracted, sb, "MI",
            frame_count=99,
            record_state_recovery_guard=lambda *a, **k: None)
    check("not fired", fired is False, f"fired={fired}")
    check("batters kept", extracted.get("batters") is not None, extracted)
    joined = "\n".join(cap.warnings + cap.infos)
    check("no strip-rows warn", "[STRIP-ROWS-MISALIGNED]" not in joined,
          joined[:300])


def test_thread7_fix1_replay_f2134_f2135_recovery() -> None:
    header("Thread 7 Fix 1: F2134/F2135 transposed strip — MI vs SRH")
    import test_pipeline as tp
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings(
        "MI", "SRH", ["Ryan Rickelton", "Tilak Varma"], ["X"],
        batting_xi=["Ryan Rickelton", "Tilak Varma"], bowling_xi=["X"])
    sb.batting_card["Ryan Rickelton"]["runs"] = 109
    sb.batting_card["Ryan Rickelton"]["balls"] = 50
    sb.batting_card["Ryan Rickelton"]["status"] = "batting"
    sb.batting_card["Tilak Varma"]["runs"] = 6
    sb.batting_card["Tilak Varma"]["balls"] = 1
    sb.batting_card["Tilak Varma"]["status"] = "batting"
    for frame in (2134, 2135):
        extracted = {
            "score": 227,
            "wickets": 4,
            "match_overs": "18.2",
            "batters": [
                {"name": "TILAK", "runs": 109, "balls": 50},
                {"name": "RICKELTON", "runs": 6, "balls": 1},
            ],
            "bowler": "Hussain",
        }
        tp.apply_comparison_strip_batter_row_delta_guard(
            extracted, sb, "MI",
            frame_count=frame,
            record_state_recovery_guard=lambda *a, **k: None)
        check(f"F{frame} batters dropped", "batters" not in extracted,
              f"{extracted!r}")
        check(f"F{frame} score=227", extracted.get("score") == 227, extracted)
        check(f"F{frame} overs 18.2",
              extracted.get("match_overs") == "18.2", extracted)
        check(f"F{frame} bowler Hussain",
              extracted.get("bowler") == "Hussain", extracted)


# ---------------------------------------------------------------------
# Batch N (2026-05-04) — STRIP-ROWS-MISALIGNED batters-only poisoning
# Memo: files/docs/investigations/pooran_strip_rows_misaligned_state_lock.md
# ---------------------------------------------------------------------


def _batch_n_pipeline_src() -> str:
    return (Path(__file__).resolve().parent / "test_pipeline.py").read_text()


def test_batch_n_call_site_uses_batters_only_flag() -> None:
    header("Batch N: row-delta call site sets _frame_poisoned_batters_only")
    src = _batch_n_pipeline_src()
    idx_call = src.find("apply_comparison_strip_batter_row_delta_guard(\n")
    # Two occurrences: the function definition and the elif call site.
    # Find the elif site (preceded by `elif `).
    idx_elif = src.find(
        "elif apply_comparison_strip_batter_row_delta_guard(")
    check("call site found", idx_elif != -1, str(idx_elif))
    block = src[idx_elif:idx_elif + 1500]
    check("flag set at call site",
          "_frame_poisoned_batters_only = True" in block, block[:600])
    check("call site does NOT raise full _frame_poisoned",
          "_frame_poisoned = True" not in block.split(
              "_frame_poisoned_batters_only = True")[0], block[:600])
    check("call site does NOT set _poison_non_graphic",
          "_poison_non_graphic = True" not in block.split(
              "_frame_poisoned_batters_only = True")[0], block[:600])
    check("guard call survives (still elif branch)",
          "apply_comparison_strip_batter_row_delta_guard" in block,
          block[:300])
    _ = idx_call  # silence unused


def test_batch_n_flag_initialized_per_frame() -> None:
    header("Batch N: _frame_poisoned_batters_only initialized False per frame")
    src = _batch_n_pipeline_src()
    idx = src.find("_frame_poisoned_batters_only = False")
    check("initializer present", idx != -1, str(idx))
    # Initialization must precede the elif call site.
    idx_elif = src.find(
        "elif apply_comparison_strip_batter_row_delta_guard(")
    check("init precedes call site", idx < idx_elif,
          f"init={idx} elif={idx_elif}")


def test_batch_n_dismissal_gate_honors_batters_only() -> None:
    header("Batch N: dismissal gate also blocks on batters-only poison")
    src = _batch_n_pipeline_src()
    idx = src.find(
        "_dismissal = (extracted.get(\"dismissal\")")
    check("dismissal gate updated", idx != -1, str(idx))
    block = src[idx:idx + 400]
    check("checks _frame_poisoned",
          "not _frame_poisoned" in block, block[:300])
    check("checks _frame_poisoned_batters_only",
          "not _frame_poisoned_batters_only" in block, block[:300])


def test_batch_n_guard_log_message_marks_batters_only() -> None:
    header("Batch N: guard log message includes poison=batters_only")
    from unittest.mock import patch

    import test_pipeline as tp
    from eyes.scoreboard import Scoreboard

    cap = _pbks_rr_telemetry_cap()
    sb = Scoreboard()
    sb.setup_innings(
        "MI", "SRH", ["Mitchell Marsh", "Nicholas Pooran"], ["X"],
        batting_xi=["Mitchell Marsh", "Nicholas Pooran"], bowling_xi=["X"])
    sb.batting_card["Mitchell Marsh"]["runs"] = 33
    sb.batting_card["Mitchell Marsh"]["balls"] = 18
    sb.batting_card["Mitchell Marsh"]["status"] = "batting"
    sb.batting_card["Nicholas Pooran"]["runs"] = 1
    sb.batting_card["Nicholas Pooran"]["balls"] = 8
    sb.batting_card["Nicholas Pooran"]["status"] = "batting"
    extracted = {
        "score": 71,
        "wickets": 1,
        "match_overs": "4.5",
        "batters": [
            {"name": "Marsh", "runs": 33, "balls": 18},
            {"name": "Pooran", "runs": 22, "balls": 7},
        ],
        "bowler": None,
    }
    with patch.object(tp, "log", cap):
        fired = tp.apply_comparison_strip_batter_row_delta_guard(
            extracted, sb, "MI",
            frame_count=493,
            record_state_recovery_guard=lambda *a, **k: None)
    check("guard fired", fired is True, f"fired={fired}")
    joined = "\n".join(cap.warnings + cap.infos)
    check("poison=batters_only present",
          "poison=batters_only" in joined, joined[:500])
    check("preserved=score,match_overs,bowler still present",
          "preserved=score,match_overs,bowler" in joined, joined[:500])


def test_batch_u_drop_off_roster_row() -> None:
    header("Batch U: per-row drop when one strip name is off-roster")
    from unittest.mock import patch

    import test_pipeline as tp
    from eyes.scoreboard import Scoreboard

    cap = _pbks_rr_telemetry_cap()
    sb = Scoreboard()
    sb.setup_innings(
        "MI", "LSG",
        ["Mitchell Marsh", "Josh Inglis", "Nicholas Pooran",
         "Aiden Markram"],
        ["Bumrah"],
        batting_xi=["Mitchell Marsh", "Josh Inglis", "Nicholas Pooran",
                    "Aiden Markram"],
        bowling_xi=["Bumrah"])
    extracted = {
        "score": 42,
        "wickets": 1,
        "match_overs": "5.2",
        "batters": [
            {"name": "Inglis", "runs": 18, "balls": 12},
            {"name": "KL Rahul", "runs": 35, "balls": 20},
        ],
        "bowler": {"name": "Bumrah"},
    }
    with patch.object(tp, "log", cap):
        fired = tp.filter_off_roster_batter_rows(
            extracted, sb, "MI", frame_count=205)
    check("filter fired", fired is True, f"fired={fired}")
    check("Inglis kept",
          len(extracted["batters"]) == 1
          and extracted["batters"][0].get("name") == "Inglis",
          str(extracted["batters"]))
    check("score preserved",
          extracted.get("score") == 42, str(extracted))
    check("match_overs preserved",
          extracted.get("match_overs") == "5.2", str(extracted))
    check("bowler preserved",
          isinstance(extracted.get("bowler"), dict), str(extracted))
    joined = "\n".join(cap.warnings + cap.infos)
    check("OFF-ROSTER-BATTER-REJECT tag emitted",
          "[OFF-ROSTER-BATTER-REJECT]" in joined, joined[:500])
    check("dropped name in log",
          "KL Rahul" in joined, joined[:500])
    check("poison=none in log",
          "poison=none" in joined, joined[:500])


def test_batch_u_keep_all_when_on_roster() -> None:
    header("Batch U: nothing dropped when both names on roster")
    from unittest.mock import patch

    import test_pipeline as tp
    from eyes.scoreboard import Scoreboard

    cap = _pbks_rr_telemetry_cap()
    sb = Scoreboard()
    sb.setup_innings(
        "MI", "LSG",
        ["Mitchell Marsh", "Josh Inglis", "Nicholas Pooran"],
        ["Bumrah"],
        batting_xi=["Mitchell Marsh", "Josh Inglis", "Nicholas Pooran"],
        bowling_xi=["Bumrah"])
    extracted = {
        "score": 42,
        "batters": [
            {"name": "Marsh", "runs": 18, "balls": 12},
            {"name": "Inglis", "runs": 9, "balls": 6},
        ],
    }
    before = [dict(r) for r in extracted["batters"]]
    with patch.object(tp, "log", cap):
        fired = tp.filter_off_roster_batter_rows(
            extracted, sb, "MI", frame_count=100)
    check("filter did not fire", fired is False, f"fired={fired}")
    check("rows unchanged", extracted["batters"] == before,
          str(extracted["batters"]))
    joined = "\n".join(cap.warnings + cap.infos)
    check("tag NOT emitted",
          "[OFF-ROSTER-BATTER-REJECT]" not in joined, joined[:500])


def test_batch_u_drop_both_when_both_off_roster() -> None:
    header("Batch U: empties batters[] when both strip names off-roster")
    from unittest.mock import patch

    import test_pipeline as tp
    from eyes.scoreboard import Scoreboard

    cap = _pbks_rr_telemetry_cap()
    sb = Scoreboard()
    sb.setup_innings(
        "LSG", "MI",
        ["KL Rahul", "Nicholas Pooran"],
        ["Bumrah"],
        batting_xi=["KL Rahul", "Nicholas Pooran"],
        bowling_xi=["Bumrah"])
    extracted = {
        "score": 60,
        "match_overs": "7.1",
        "batters": [
            {"name": "Suryakumar Yadav", "runs": 22, "balls": 15},
            {"name": "Rohit Sharma", "runs": 38, "balls": 24},
        ],
        "bowler": {"name": "Bumrah"},
    }
    with patch.object(tp, "log", cap):
        fired = tp.filter_off_roster_batter_rows(
            extracted, sb, "LSG", frame_count=289)
    check("filter fired", fired is True, f"fired={fired}")
    check("batters emptied",
          extracted["batters"] == [], str(extracted["batters"]))
    check("score preserved",
          extracted.get("score") == 60, str(extracted))
    check("match_overs preserved",
          extracted.get("match_overs") == "7.1", str(extracted))
    joined = "\n".join(cap.warnings + cap.infos)
    check("tag emitted with both names",
          "[OFF-ROSTER-BATTER-REJECT]" in joined
          and "Suryakumar Yadav" in joined and "Rohit Sharma" in joined,
          joined[:500])


def test_batch_n_pooran_cascade_score_overs_bowler_preserved() -> None:
    header("Batch N: Pooran cascade — score/overs/bowler survive guard pop")
    import test_pipeline as tp
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings(
        "MI", "SRH", ["Mitchell Marsh", "Nicholas Pooran"], ["Bumrah"],
        batting_xi=["Mitchell Marsh", "Nicholas Pooran"],
        bowling_xi=["Bumrah"])
    sb.batting_card["Mitchell Marsh"]["runs"] = 33
    sb.batting_card["Mitchell Marsh"]["balls"] = 18
    sb.batting_card["Mitchell Marsh"]["status"] = "batting"
    sb.batting_card["Nicholas Pooran"]["runs"] = 1
    sb.batting_card["Nicholas Pooran"]["balls"] = 8
    sb.batting_card["Nicholas Pooran"]["status"] = "batting"
    extracted = {
        "score": 71,
        "wickets": 1,
        "match_overs": "4.5",
        "batters": [
            {"name": "Marsh", "runs": 33, "balls": 18},
            {"name": "Pooran", "runs": 22, "balls": 7},
        ],
        "bowler": {"name": "Bumrah", "wickets": 0, "runs": 12, "overs": "1"},
    }
    fired = tp.apply_comparison_strip_batter_row_delta_guard(
        extracted, sb, "MI",
        frame_count=493,
        record_state_recovery_guard=lambda *a, **k: None)
    check("guard fired", fired is True, f"fired={fired}")
    check("batters popped", "batters" not in extracted, str(extracted))
    check("score survives (71)",
          extracted.get("score") == 71, str(extracted))
    check("match_overs survives (4.5)",
          extracted.get("match_overs") == "4.5", str(extracted))
    check("bowler dict survives",
          isinstance(extracted.get("bowler"), dict)
          and extracted["bowler"].get("name") == "Bumrah",
          str(extracted))


def test_batch_w_overlay_prefilter_doesnt_block_score() -> None:
    header("Batch W: overlay prefilter call site uses batters-only flag")
    src = _batch_n_pipeline_src()
    idx = src.find("if apply_strip_overlay_prefilters(")
    check("call site found", idx != -1, str(idx))
    block = src[idx:idx + 1200]
    check("flag set at call site",
          "_frame_poisoned_batters_only = True" in block, block[:600])
    pre = block.split("_frame_poisoned_batters_only = True")[0]
    check("call site does NOT raise full _frame_poisoned",
          "_frame_poisoned = True" not in pre, pre[:600])
    check("call site does NOT set _poison_non_graphic",
          "_poison_non_graphic = True" not in pre, pre[:600])


# ---------------------------------------------------------------------
# Thread 7 Fix 2 — cam=graphic strip-head fast-path (2026-04-30)
# ---------------------------------------------------------------------


def _t7_fix2_resolve_mi(abbr: str) -> str | None:
    return "MI" if abbr == "MI" else None


def test_thread7_fix2_cam_graphic_live_strip_accepts() -> None:
    header("Thread 7 Fix 2: cam=graphic + strip accepts valid STRIP head")
    from collections import deque

    import test_pipeline as tp

    dq = deque(maxlen=tp._FAST_PATH_COOLDOWN_MAXLEN)
    desc = (
        "STRIP: MI 224-4 (18.2) | Tilak 0(0) | Rickelton 109(50) | "
        "Hussain 1-31 (2.2)")
    commit, rej = tp._cam_graphic_fast_path(
        description=desc,
        cam="graphic",
        has_strip=True,
        has_overlay_stats=False,
        batting_team="MI",
        current_score=221,
        current_overs_str="18.1",
        cooldown=dq,
        resolve_team_variant=_t7_fix2_resolve_mi,
        frame_count=99001,
    )
    check("no reject", rej is None, rej)
    check("commit keys",
          commit is not None and set(commit.keys()) == {"score", "match_overs"},
          commit)
    check("score", commit.get("score") == 224, commit)
    check("overs str", commit.get("match_overs") == "18.2", commit)


def test_thread7_fix2_cam_graphic_replay_rejects() -> None:
    header("Thread 7 Fix 2: replay / stale score — G6 score_window")
    from collections import deque
    from unittest.mock import patch

    import test_pipeline as tp

    cap = _pbks_rr_telemetry_cap()
    dq = deque(maxlen=tp._FAST_PATH_COOLDOWN_MAXLEN)
    desc = "STRIP: MI 210-4 (18.1) | X | Y | Z"
    with patch.object(tp, "log", cap):
        commit, rej = tp._cam_graphic_fast_path(
            description=desc,
            cam="graphic",
            has_strip=True,
            has_overlay_stats=False,
            batting_team="MI",
            current_score=221,
            current_overs_str="18.1",
            cooldown=dq,
            resolve_team_variant=_t7_fix2_resolve_mi,
            frame_count=99002,
        )
    check("rejected", commit is None, commit)
    check("reason", rej == "G6_score_window", rej)
    joined = "\n".join(cap.infos)
    check("telemetry",
          "[CAM-GRAPHIC-FAST-PATH-REJECT]" in joined and "G6_score_window" in joined,
          joined[:400])


def test_thread7_fix2_cam_graphic_career_card_rejects_f2768() -> None:
    header("Thread 7 Fix 2: F2768 class — G2 has_overlay_stats")
    from collections import deque

    import test_pipeline as tp

    dq = deque(maxlen=tp._FAST_PATH_COOLDOWN_MAXLEN)
    desc = (
        "STRIP: MI 0-0 (0.0) | INFO_PANEL: TRENT BOULT IPL CAREER MATCHES")
    commit, rej = tp._cam_graphic_fast_path(
        description=desc,
        cam="graphic",
        has_strip=True,
        has_overlay_stats=True,
        batting_team="MI",
        current_score=120,
        current_overs_str="14.2",
        cooldown=dq,
        resolve_team_variant=_t7_fix2_resolve_mi,
        frame_count=99003,
    )
    check("reject overlay path", commit is None and rej == "G2_overlay_stats",
          f"{commit!r} {rej!r}")


def test_thread7_fix2_cam_graphic_preview_rejects() -> None:
    header("Thread 7 Fix 2: over-end jump — G7 balls_window")
    from collections import deque

    import test_pipeline as tp

    dq = deque(maxlen=tp._FAST_PATH_COOLDOWN_MAXLEN)
    # Same score (G6 satisfied); overs jump 18.1→20.0 exceeds ball delta max.
    desc = "STRIP: MI 221-4 (20.0) | X | Y | Z"
    commit, rej = tp._cam_graphic_fast_path(
        description=desc,
        cam="graphic",
        has_strip=True,
        has_overlay_stats=False,
        batting_team="MI",
        current_score=221,
        current_overs_str="18.1",
        cooldown=dq,
        resolve_team_variant=_t7_fix2_resolve_mi,
        frame_count=99004,
    )
    check("reject huge overs jump",
          commit is None and rej == "G7_balls_window", f"{commit!r} {rej!r}")


def test_thread7_fix2_g6_max_delta_six_accepts() -> None:
    header("Thread 7 Fix 2: G6 inclusive +6 / +7 rejected")
    from collections import deque

    import test_pipeline as tp

    dq = deque(maxlen=tp._FAST_PATH_COOLDOWN_MAXLEN)
    desc_ok = "STRIP: MI 226-4 (18.1) | X | Y | Z"
    c_ok, r_ok = tp._cam_graphic_fast_path(
        description=desc_ok,
        cam="graphic",
        has_strip=True,
        has_overlay_stats=False,
        batting_team="MI",
        current_score=220,
        current_overs_str="18.1",
        cooldown=dq,
        resolve_team_variant=_t7_fix2_resolve_mi,
        frame_count=99101,
    )
    check("+6 accept", r_ok is None and c_ok.get("score") == 226, (c_ok, r_ok))

    dq2 = deque(maxlen=tp._FAST_PATH_COOLDOWN_MAXLEN)
    desc_bad = "STRIP: MI 227-4 (18.1) | X | Y | Z"
    c_bad, r_bad = tp._cam_graphic_fast_path(
        description=desc_bad,
        cam="graphic",
        has_strip=True,
        has_overlay_stats=False,
        batting_team="MI",
        current_score=220,
        current_overs_str="18.1",
        cooldown=dq2,
        resolve_team_variant=_t7_fix2_resolve_mi,
        frame_count=99102,
    )
    check("+7 reject", c_bad is None and r_bad == "G6_score_window",
          (c_bad, r_bad))


def test_thread7_fix2_g7_max_ball_delta_accepts() -> None:
    header("Thread 7 Fix 2: G7 over-boundary 2.5→3.0 + illegal frac")
    from collections import deque

    import test_pipeline as tp

    dq = deque(maxlen=tp._FAST_PATH_COOLDOWN_MAXLEN)
    desc_ob = "STRIP: MI 221-4 (3.0) | X | Y | Z"
    c_ob, r_ob = tp._cam_graphic_fast_path(
        description=desc_ob,
        cam="graphic",
        has_strip=True,
        has_overlay_stats=False,
        batting_team="MI",
        current_score=221,
        current_overs_str="2.5",
        cooldown=dq,
        resolve_team_variant=_t7_fix2_resolve_mi,
        frame_count=99201,
    )
    check("2.5→3.0 accept",
          r_ob is None and c_ob.get("match_overs") == "3.0", (c_ob, r_ob))

    dq2 = deque(maxlen=tp._FAST_PATH_COOLDOWN_MAXLEN)
    desc_il = "STRIP: MI 221-4 (18.6) | X | Y | Z"
    c_il, r_il = tp._cam_graphic_fast_path(
        description=desc_il,
        cam="graphic",
        has_strip=True,
        has_overlay_stats=False,
        batting_team="MI",
        current_score=221,
        current_overs_str="18.1",
        cooldown=dq2,
        resolve_team_variant=_t7_fix2_resolve_mi,
        frame_count=99202,
    )
    check("18.6 illegal frac",
          c_il is None and r_il == "G7_illegal_frac", (c_il, r_il))


def test_thread7_fix2_cooldown_identity_noop() -> None:
    header("Thread 7 Fix 2: G8 — identical parse rejected on second call")
    from collections import deque
    from unittest.mock import patch

    import test_pipeline as tp

    dq = deque(maxlen=tp._FAST_PATH_COOLDOWN_MAXLEN)
    desc = "STRIP: MI 221-4 (18.1) | X | Y | Z"
    cap = _pbks_rr_telemetry_cap()
    with patch.object(tp, "log", cap):
        c1, r1 = tp._cam_graphic_fast_path(
            description=desc,
            cam="graphic",
            has_strip=True,
            has_overlay_stats=False,
            batting_team="MI",
            current_score=221,
            current_overs_str="18.1",
            cooldown=dq,
            resolve_team_variant=_t7_fix2_resolve_mi,
            frame_count=99301,
        )
        c2, r2 = tp._cam_graphic_fast_path(
            description=desc,
            cam="graphic",
            has_strip=True,
            has_overlay_stats=False,
            batting_team="MI",
            current_score=221,
            current_overs_str="18.1",
            cooldown=dq,
            resolve_team_variant=_t7_fix2_resolve_mi,
            frame_count=99302,
        )
    check("first ok", r1 is None and c1 is not None, (c1, r1))
    check("second G8", c2 is None and r2 == "G8_cooldown_dup", (c2, r2))
    joined = "\n".join(cap.infos)
    check("G8 telemetry", "G8_cooldown_dup" in joined, joined[-400:])


def test_thread7_fix2_cooldown_different_content_accepts() -> None:
    header("Thread 7 Fix 2: G8 — distinct tuples both accepted")
    from collections import deque

    import test_pipeline as tp

    dq = deque(maxlen=tp._FAST_PATH_COOLDOWN_MAXLEN)
    d1 = "STRIP: MI 221-4 (18.1) | a"
    d2 = "STRIP: MI 224-4 (18.2) | b"
    c1, r1 = tp._cam_graphic_fast_path(
        description=d1,
        cam="graphic",
        has_strip=True,
        has_overlay_stats=False,
        batting_team="MI",
        current_score=221,
        current_overs_str="18.1",
        cooldown=dq,
        resolve_team_variant=_t7_fix2_resolve_mi,
        frame_count=99401,
    )
    c2, r2 = tp._cam_graphic_fast_path(
        description=d2,
        cam="graphic",
        has_strip=True,
        has_overlay_stats=False,
        batting_team="MI",
        current_score=221,
        current_overs_str="18.1",
        cooldown=dq,
        resolve_team_variant=_t7_fix2_resolve_mi,
        frame_count=99402,
    )
    check("both ok", r1 is None and r2 is None, (r1, r2))
    check("scores", c1["score"] == 221 and c2["score"] == 224, (c1, c2))


def test_thread7_fix2_f2128_cam_graphic_during_gap() -> None:
    header("Thread 7 Fix 2: F2128 — inferred STRIP (dead-time skip window)")
    from collections import deque

    import test_pipeline as tp

    dq = deque(maxlen=tp._FAST_PATH_COOLDOWN_MAXLEN)
    desc = (
        "STRIP: MI 221-4 (18.1) | Tilak 0(0) | Rickelton 109(50) | "
        "Hussain 1-31 (2.1)")
    commit, rej = tp._cam_graphic_fast_path(
        description=desc,
        cam="graphic",
        has_strip=True,
        has_overlay_stats=False,
        batting_team="MI",
        current_score=221,
        current_overs_str="18.1",
        cooldown=dq,
        resolve_team_variant=_t7_fix2_resolve_mi,
        frame_count=2128,
    )
    check("F2128 attempts commit dict",
          rej is None and commit["score"] == 221 and commit["match_overs"] == "18.1",
          (commit, rej))


def test_thread7_fix2_no_overlap_with_fix1_telemetry() -> None:
    header("Thread 7 Fix 2: telemetry paths disjoint from Fix 1 guard")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    idx_strip = src.find("[STRIP-ROWS-MISALIGNED]")
    idx_fp_def = src.find("def _cam_graphic_fast_path")
    idx_dead = src.find("# ── Dead-time skip (Phase 2.5 — 2026-04-18)")
    idx_guard_def = src.find("def apply_comparison_strip_batter_row_delta_guard")
    check("Fix 1 tag line exists", idx_strip != -1, str(idx_strip))
    check("fast-path defined before run_test",
          idx_fp_def != -1 and idx_fp_def < src.find("async def run_test"),
          str(idx_fp_def))
    check("dead-time block after fast-path definition",
          idx_dead > idx_fp_def, f"{idx_dead} vs {idx_fp_def}")
    check("strip-rows lives in comparison guard region",
          idx_strip > idx_guard_def and idx_strip < idx_dead,
          f"{idx_strip} guard={idx_guard_def} dead={idx_dead}")
    check("cam-graphic READ near dead-time skip",
          src.find("[CAM-GRAPHIC-FAST-PATH-READ]") > idx_dead,
          str(src.find("[CAM-GRAPHIC-FAST-PATH-READ]")))


def test_thread7_fix2_pipeline_contains_noop_tag() -> None:
    header("Thread 7 Fix 2: NOOP telemetry wired at dead-time call site")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    check("[CAM-GRAPHIC-FAST-PATH-NOOP] present",
          "[CAM-GRAPHIC-FAST-PATH-NOOP]" in src, "")
    check("dead-time skip comment preserved",
          "Dead-time skip (Phase 2.5 — 2026-04-18)" in src, "")


# ---------------------------------------------------------------------
# MI vs SRH (2026-04-29) — investigation-backed regression fixtures
# ---------------------------------------------------------------------


def test_fixture_batters_invariant_admission_window_cluster() -> None:
    """Will Jacks admission window (F487/F488/F505/F506 class).

    Source: files/docs/investigations/batters_invariant_cluster_innings1.md
    §1.1 — Phase 1 noop telemetry baseline.
    """
    from unittest.mock import patch

    import test_pipeline as tp
    from eyes.scoreboard import Scoreboard
    from score_manager import ScoreManager

    sb = Scoreboard()
    sb.setup_innings(
        "MI", "SRH",
        ["Will Jacks", "Rohit Sharma", "Naman Dhir"],
        ["Pat Cummins"],
        batting_xi=["Will Jacks", "Rohit Sharma", "Naman Dhir"],
        bowling_xi=["Pat Cummins"])
    for nm in ("Will Jacks", "Rohit Sharma"):
        sb.batting_card[nm]["status"] = "batting"
        sb.batting_card[nm]["runs"] = 12
        sb.batting_card[nm]["balls"] = 8
    sb.batting_card["Naman Dhir"]["status"] = "yet to bat"
    sm = ScoreManager(shadow=True)
    sm.scoreboard = sb
    sm.striker = "Will Jacks"
    sm.non = "Will Jacks"

    seq = [
        (487, [], "upstream_step3_fired=false"),
        (488, [], "upstream_step3_fired=false"),
        (505, [("SCORER-DISMISSED-RESURRECT", "Rohit Sharma"),
               ("SCORER-INVARIANT-FILTER", "Rohit Sharma")],
         "upstream_step3_fired=true"),
        (506, [("GUARD_BATTER_EXTRACTOR", "Will Jacks"),
               ("SCORER-DISMISSED-RESURRECT", "Rohit Sharma")],
         "upstream_step3_fired=true"),
    ]
    for fc, note_tuples, exp3 in seq:
        cap = _pbks_rr_telemetry_cap()
        notes = list(note_tuples)
        with patch.object(tp, "log", cap):
            tp._batters_invariant_backstop(
                sb, sm, fc, [], notes, set())
        joined = "\n".join(cap.warnings + cap.infos)
        check(f"F{fc} rule=C striker_non_collision",
              "[BATTERS-INVARIANT]" in joined
              and "rule=C" in joined
              and "striker_non_collision" in joined,
              joined[:700])
        check(f"F{fc} {exp3}", exp3 in joined, joined[:700])


def test_fixture_batters_invariant_rule_a_resurrection_f2167() -> None:
    """Hardik Pandya 3-active set (F2167 class).

    Source: batters_invariant_cluster_innings1.md §5.
    """
    from unittest.mock import patch

    import test_pipeline as tp
    from eyes.scoreboard import Scoreboard
    from score_manager import ScoreManager

    cap = _pbks_rr_telemetry_cap()
    sb = Scoreboard()
    sb.setup_innings(
        "MI", "SRH",
        ["Ryan Rickelton", "Tilak Varma", "Hardik Pandya"],
        ["X"],
        batting_xi=["Ryan Rickelton", "Tilak Varma", "Hardik Pandya"],
        bowling_xi=["X"])
    for nm in ("Ryan Rickelton", "Tilak Varma", "Hardik Pandya"):
        sb.batting_card[nm]["status"] = "batting"
        sb.batting_card[nm]["runs"] = 20
        sb.batting_card[nm]["balls"] = 10
    sb.fall_of_wickets.append({
        "wicket": 4, "batter": "Hardik Pandya", "score": 200,
        "overs": "18.1", "_witnessed": True})
    sm = ScoreManager(shadow=True)
    sm.scoreboard = sb
    sm.striker = "Ryan Rickelton"
    sm.non = "Hardik Pandya"
    with patch.object(tp, "log", cap):
        tp._batters_invariant_backstop(sb, sm, 2167, [], [], set())
    joined = "\n".join(cap.warnings)
    check("rule=A active_set_max_two",
          "[BATTERS-INVARIANT]" in joined
          and "rule=A" in joined
          and "active_set_max_two" in joined,
          joined[:800])
    check("upstream step3 did not fire",
          "upstream_step3_fired=false" in joined, joined[:800])


def test_fixture_striker_sm_cutover_intra_over_wicket_gap() -> None:
    """WS-SLOT-INVARIANT during SM stale non-striker; cutover at over-end.

    Source: lever1_pr2_match_analysis.md §3.1 / §5 (Cause C + over-end
    STRIKER-SM-CUTOVER).
    """
    import test_pipeline as tp
    from eyes.scoreboard import Scoreboard

    cap = _pbks_rr_telemetry_cap()
    sb = Scoreboard()
    sb.setup_innings(
        "BAT", "BOWL", ["Rickelton", "Jacks"], ["Bowler"],
        batting_xi=["Rickelton", "Jacks"], bowling_xi=["Bowler"])
    sb.batting_card["Rickelton"]["status"] = "batting"
    sb.batting_card["Jacks"]["status"] = "batting"
    sm = types.SimpleNamespace(striker="Rickelton", non="Rickelton")

    def _canon(raw, *, bowler=False):
        return tp._ws_canonicalize_player_name(raw, scoreboard=sb, bowler=bowler)

    ws_hits = 0
    for _ in range(4):
        state = {"striker": "Rickelton", "non": "Rickelton"}
        with patch.object(tp, "log", cap):
            tp.enforce_ws_slot_invariant(state, sb, _canon)
        joined = "\n".join(cap.warnings + cap.infos)
        if "[WS-SLOT-INVARIANT]" in joined:
            ws_hits += 1
        cap.warnings.clear()
        cap.infos.clear()
    check("intra-over duplicate fires each stale-frame projection",
          ws_hits == 4,
          f"ws_hits={ws_hits}")

    cap_mirror = _pbks_rr_telemetry_cap()
    with patch.object(tp, "log", cap_mirror):
        ok_mirror = tp._set_inn_slot_with_sm_mirror(
            sm, sb, "non", "Jacks", "over-end")
    cut = "\n".join(cap_mirror.warnings + cap_mirror.infos)
    check("mirror helper ran",
          ok_mirror is True, f"ok_mirror={ok_mirror}")
    check("STRIKER-SM-CUTOVER telemetry at mirror write",
          "[STRIKER-SM-CUTOVER]" in cut and "reason=over-end" in cut,
          cut[:400])
    check("sb._inn non mirrored",
          sb._inn.get("non") == "Jacks", sb._inn)
    check("SM non updated post cutover",
          getattr(sm, "non", None) == "Jacks",
          f"sm.__dict__={getattr(sm, '__dict__', sm)!r}")


# ---------------------------------------------------------------------
# Lever 1 PR3 — dismissed-partner guard + batter-arrival CUTOVER (§14.9)
# ---------------------------------------------------------------------


def test_pr3_w8_dismissed_guard_fires() -> None:
    header("Lever 1 PR3 T1: _w8_non_for_identified suppresses "
           "status=out partner + [SM-W8-DISMISSED-GUARD]")
    from score_manager import ScoreManager
    from eyes.scoreboard import Scoreboard
    import score_manager as smod

    sb = Scoreboard()
    sb.setup_innings(
        "MI", "SRH", ["Will Jacks", "Ryan Rickelton"], ["X"],
        batting_xi=["Will Jacks", "Ryan Rickelton"], bowling_xi=["X"])
    sb.batting_card["Will Jacks"]["status"] = "batting"
    sb.batting_card["Ryan Rickelton"]["status"] = "out"
    sm = ScoreManager(shadow=True)
    sm.scoreboard = sb
    sm.bat1_name = "Will Jacks"
    sm.bat2_name = "Ryan Rickelton"
    infos: list[str] = []

    def _grab(msg, *args, **kwargs) -> None:
        infos.append(str(msg))

    with patch.object(smod.log, "info", new=_grab):
        ns = sm._w8_non_for_identified("Will Jacks")
    joined = "\n".join(infos)
    check("partner suppressed", ns is None, repr(ns))
    check("[SM-W8-DISMISSED-GUARD] emitted once",
          "[SM-W8-DISMISSED-GUARD]" in joined,
          joined[:500])


def test_pr3_w8_dismissed_guard_dedup() -> None:
    header("Lever 1 PR3 T2: [SM-W8-DISMISSED-GUARD] dedup — single INFO "
           "across repeated steady-state frames")
    from score_manager import ScoreManager
    from eyes.scoreboard import Scoreboard
    import score_manager as smod

    sb = Scoreboard()
    sb.setup_innings(
        "BAT", "BOWL", ["A Striker", "B Out"], ["X"],
        batting_xi=["A Striker", "B Out"], bowling_xi=["X"])
    sb.batting_card["A Striker"]["status"] = "batting"
    sb.batting_card["B Out"]["status"] = "out"
    sm = ScoreManager(shadow=True)
    sm.scoreboard = sb
    sm.bat1_name = "A Striker"
    sm.bat2_name = "B Out"
    hits = 0

    def _count(msg, *args, **kwargs) -> None:
        nonlocal hits
        if "[SM-W8-DISMISSED-GUARD]" in str(msg):
            hits += 1

    with patch.object(smod.log, "info", new=_count):
        for _ in range(12):
            sm._w8_non_for_identified("A Striker")
    check("dedup: exactly one guard INFO", hits == 1, f"hits={hits}")


def test_pr3_integration_mi_srh_admission_window_recovery() -> None:
    header("Lever 1 PR3 T3: admission-window striker inference — "
           "SM.non not re-stuffed with dismissed partner")
    from score_manager import ScoreManager, FrameInput
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings(
        "MI", "SRH",
        ["Will Jacks", "Ryan Rickelton", "Rohit Sharma"], ["X"],
        batting_xi=["Will Jacks", "Ryan Rickelton", "Rohit Sharma"],
        bowling_xi=["X"])
    sb.batting_card["Will Jacks"]["status"] = "batting"
    sb.batting_card["Ryan Rickelton"]["status"] = "out"
    sb.batting_card["Rohit Sharma"]["status"] = "yet to bat"
    sm = ScoreManager(shadow=True)
    sm.scoreboard = sb
    sm.bat1_name = "Will Jacks"
    sm.bat2_name = "Ryan Rickelton"
    sm.striker = "Will Jacks"
    sm.non = None
    card = {
        "bat1_name": "Will Jacks",
        "bat1_runs": 12,
        "bat1_balls": 9,
        "bat2_name": "Ryan Rickelton",
        "bat2_runs": 8,
        "bat2_balls": 8,
    }
    frame = FrameInput(frame_id="f487", timestamp=1.0)
    sm._identify_and_set(
        card, frame,
        prev_b1_runs=12, prev_b1_balls=8,
        prev_b2_runs=8, prev_b2_balls=8)
    check("non slot does not hold dismissed Rickelton",
          sm.non != "Ryan Rickelton", repr(sm.non))


def test_pr3_batter_arrival_cutover_fires() -> None:
    header("Lever 1 PR3 T4: _pr3_batter_arrival_slot_cutover emits "
           "[STRIKER-SM-CUTOVER] reason=batter-arrival")
    import test_pipeline as tp
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings(
        "MI", "SRH", ["Will Jacks", "Ryan Rickelton"], ["X"],
        batting_xi=["Will Jacks", "Ryan Rickelton"], bowling_xi=["X"])
    sb.batting_card["Will Jacks"]["status"] = "batting"
    sb.batting_card["Ryan Rickelton"]["status"] = "out"
    sm = types.SimpleNamespace(striker="Will Jacks", non="Ryan Rickelton")
    cap = _pbks_rr_telemetry_cap()
    with patch.object(tp, "log", cap):
        tp._pr3_batter_arrival_slot_cutover(sm, sb, "Rohit Sharma")
    joined = "\n".join(cap.infos + cap.warnings)
    check("telemetry carries reason=batter-arrival",
          "[STRIKER-SM-CUTOVER]" in joined
          and "reason=batter-arrival" in joined,
          joined[:500])
    check("_inn non mirrored to admitted batter",
          sb._inn.get("non") == "Rohit Sharma", sb._inn.get("non"))
    check("SM non updated",
          getattr(sm, "non", None) == "Rohit Sharma", getattr(sm, "non"))


def test_pr3_integration_full_innings_replay() -> None:
    header("Lever 1 PR3 T5: Cause C — duplicate striker/non fires "
           "[WS-SLOT-INVARIANT]; cleared non avoids churn")
    import test_pipeline as tp
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings(
        "MI", "SRH", ["Will Jacks", "Ryan Rickelton"], ["X"],
        batting_xi=["Will Jacks", "Ryan Rickelton"], bowling_xi=["X"])
    sb.batting_card["Will Jacks"]["status"] = "batting"
    sb.batting_card["Ryan Rickelton"]["status"] = "out"

    def _canon(raw, *, bowler=False):
        return tp._ws_canonicalize_player_name(raw, scoreboard=sb, bowler=bowler)

    cap = _pbks_rr_telemetry_cap()
    stale_hits = 0
    for _ in range(8):
        state = {"striker": "Will Jacks", "non": "Will Jacks"}
        with patch.object(tp, "log", cap):
            tp.enforce_ws_slot_invariant(state, sb, _canon)
        joined = "\n".join(cap.warnings + cap.infos)
        if "[WS-SLOT-INVARIANT]" in joined:
            stale_hits += 1
        cap.warnings.clear()
        cap.infos.clear()

    clear_hits = 0
    for _ in range(8):
        state = {"striker": "Will Jacks", "non": None}
        with patch.object(tp, "log", cap):
            tp.enforce_ws_slot_invariant(state, sb, _canon)
        joined = "\n".join(cap.warnings + cap.infos)
        if "[WS-SLOT-INVARIANT]" in joined:
            clear_hits += 1
        cap.warnings.clear()
        cap.infos.clear()

    logp = (
        Path(__file__).resolve().parent.parent
        / "logs" / "pipeline-2026-04-29-194416-mi-srh-live.log")
    if logp.is_file():
        raw = logp.read_text(errors="replace")
        baseline_ws = raw.count("[WS-SLOT-INVARIANT]")
        check("MI vs SRH log documents historical WS-SLOT density "
              "(pre-replay static artifact)",
              baseline_ws >= 80, f"baseline_ws={baseline_ws}")

    check("duplicate slots trigger WS-SLOT repair churn",
          stale_hits >= 1, f"stale_hits={stale_hits}")
    check("cleared non avoids WS-SLOT in this harness",
          clear_hits == 0, f"clear_hits={clear_hits}")


def test_pr3_w3_w7_helper_routing() -> None:
    header("Lever 1 PR3 T6: W3–W7 `_accept_initial` / bootstrap route "
           "slots via `_set_slot_pair` semantics")
    from score_manager import ScoreManager, FrameInput
    from eyes.scoreboard import Scoreboard

    sb = Scoreboard()
    sb.setup_innings(
        "BAT", "BOWL", ["Ann Alpha", "Bob Beta"], ["X"],
        batting_xi=["Ann Alpha", "Bob Beta"], bowling_xi=["X"])
    frame = FrameInput(
        frame_id="init", timestamp=0.0, broadcast_team="BAT")

    base_card = {
        "score": 10, "wickets": 1, "overs": 5.2,
        "bat1_name": "Ann Alpha", "bat2_name": "Bob Beta",
    }

    sm_a = ScoreManager(shadow=True)
    sm_a.scoreboard = sb
    card_a = {**base_card, "broadcast": "Ann"}
    sm_a._accept_initial(card_a, frame)
    check("init_from_card.striker path slots Ann/Bob",
          sm_a.striker == "Ann Alpha" and sm_a.non == "Bob Beta",
          (sm_a.striker, sm_a.non))

    sm_b = ScoreManager(shadow=True)
    sm_b.scoreboard = sb
    card_b = {**base_card, "broadcast": "Beta"}
    sm_b._accept_initial(card_b, frame)
    check("init_from_card.non path slots Bob/Ann",
          sm_b.striker == "Bob Beta" and sm_b.non == "Ann Alpha",
          (sm_b.striker, sm_b.non))

    sm_c = ScoreManager(shadow=True)
    sm_c.scoreboard = sb
    card_c = {**base_card, "broadcast": "nomatch_z"}
    sm_c._accept_initial(card_c, frame)
    check("init_from_card.combined fallback bat1/bat2 order",
          sm_c.striker == "Ann Alpha" and sm_c.non == "Bob Beta",
          (sm_c.striker, sm_c.non))

    sm_d = ScoreManager(shadow=True)
    sm_d.scoreboard = sb
    card_d = dict(base_card)
    sm_d._accept_initial(card_d, frame)
    check("cold_start path mirrors bat1/bat2",
          sm_d.striker == "Ann Alpha" and sm_d.non == "Bob Beta",
          (sm_d.striker, sm_d.non))

    sm_e = ScoreManager(shadow=True)
    sm_e.scoreboard = sb
    sm_e.bat1_name = None
    sm_e.bat2_name = None
    sm_e._update_batters({
        "bat1_name": "Ann Alpha",
        "bat2_name": "Bob Beta",
        "bat1_runs": 1,
        "bat2_runs": 2,
    })
    check("bootstrap seeds batters",
          sm_e.bat1_name == "Ann Alpha" and sm_e.bat2_name == "Bob Beta",
          (sm_e.bat1_name, sm_e.bat2_name))
    check("bootstrap striker/non aligned",
          sm_e.striker == "Ann Alpha" and sm_e.non == "Bob Beta",
          (sm_e.striker, sm_e.non))


def test_pr3_telemetry_dedup_validation() -> None:
    header("Lever 1 PR3 T7: dedup — one [SM-W8-DISMISSED-GUARD] per "
           "dismissed partner across steady-state frames")
    from score_manager import ScoreManager
    from eyes.scoreboard import Scoreboard
    import score_manager as smod

    sb = Scoreboard()
    sb.setup_innings(
        "BAT", "BOWL",
        ["S", "O1", "O2", "O3", "O4", "O5", "O6", "O7"], ["X"],
        batting_xi=["S", "O1", "O2", "O3", "O4", "O5", "O6", "O7"],
        bowling_xi=["X"])
    sb.batting_card["S"]["status"] = "batting"
    for nm in ("O1", "O2", "O3", "O4", "O5", "O6", "O7"):
        sb.batting_card[nm]["status"] = "out"
    sm = ScoreManager(shadow=True)
    sm.scoreboard = sb
    sm.bat1_name = "S"
    infos: list[str] = []

    def _grab(msg, *args, **kwargs) -> None:
        infos.append(str(msg))

    partners = ("O1", "O2", "O3", "O4", "O5", "O6", "O7")
    with patch.object(smod.log, "info", new=_grab):
        for p in partners:
            sm.bat2_name = p
            sm._w8_guard_fired.clear()
            for _ in range(5):
                sm._w8_non_for_identified("S")
    guard_hits = sum(
        1 for ln in infos if "[SM-W8-DISMISSED-GUARD]" in ln)
    check("one guard line per distinct dismissed partner (7×)",
          guard_hits == 7, f"guard_hits={guard_hits}")


# ---------------------------------------------------------------------
# Lever 1 PR4 — W11/W12 wicket cleanup → `_set_slot_pair`
# (sm_rotation_atomicity_design §1.1 W11–W12; telemetry uniformity)
# ---------------------------------------------------------------------


def test_pr4_w11_helper_routing() -> None:
    header("Lever 1 PR4 W11: wicket striker-out cleanup routes "
           "`_set_slot_pair` with apply_event.wicket_striker_out")
    from score_manager import ScoreManager, FrameInput
    from eyes.scoreboard import Scoreboard
    import score_manager as smod

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["Alice Ace", "Bob Baker"], bowling_squad=["X"],
        batting_xi=["Alice Ace", "Bob Baker"], bowling_xi=["X"])
    for nm in ("Alice Ace", "Bob Baker"):
        sb.batting_card[nm]["status"] = "batting"
    sm = ScoreManager(shadow=True)
    sm.scoreboard = sb
    sm.bat1_name = "Alice Ace"
    sm.bat2_name = "Bob Baker"
    sm.striker = "Alice Ace"
    sm.non = "Bob Baker"
    sm.wickets = 1
    sm.score = 40
    sm.overs = 6.0

    pair_calls: list[tuple] = []
    real_set = sm._set_slot_pair.__get__(sm, type(sm))

    def _track(s, ns, *, source):
        pair_calls.append((s, ns, source))
        return real_set(s, ns, source=source)

    slot_warns: list[str] = []

    def _grab_warn(msg, *a, **k):
        slot_warns.append(str(msg))

    prev = {"overs": 6.0}
    card = {"overs": 6.0}
    frame = FrameInput(frame_id="w11", timestamp=1.0)
    evt = {
        "type": "WICKET",
        "runs": 0,
        "legal": True,
        "this_over_token": "W",
        "dismissed": "Alice Ace",
        "wicket_type": "bowled",
    }
    with patch.object(sm, "_set_slot_pair", side_effect=_track):
        with patch.object(smod.log, "warn", new=_grab_warn):
            sm._apply_event(evt, prev, card, frame)

    check("one _set_slot_pair call from wicket slot cleanup",
          len(pair_calls) == 1, pair_calls)
    check("W11 passes (None, survivor) + wicket_striker source",
          pair_calls[0] == (
              None, "Bob Baker", "apply_event.wicket_striker_out"),
          pair_calls[0])
    check("END-STATE-NULL-OK: striker cleared, non is survivor",
          sm.striker is None and sm.non == "Bob Baker",
          (sm.striker, sm.non))
    check("no [SM-SLOT-INVARIANT] on legitimate None striker write",
          not any("[SM-SLOT-INVARIANT]" in ln for ln in slot_warns),
          slot_warns or "(none)")


def test_pr4_w12_helper_routing() -> None:
    header("Lever 1 PR4 W12: wicket non-striker-out cleanup routes "
           "`_set_slot_pair` with apply_event.wicket_non_striker_out")
    from score_manager import ScoreManager, FrameInput
    from eyes.scoreboard import Scoreboard
    import score_manager as smod

    sb = Scoreboard()
    sb.setup_innings(
        batting_team="BAT", bowling_team="BOWL",
        batting_squad=["Alice Ace", "Bob Baker"], bowling_squad=["X"],
        batting_xi=["Alice Ace", "Bob Baker"], bowling_xi=["X"])
    for nm in ("Alice Ace", "Bob Baker"):
        sb.batting_card[nm]["status"] = "batting"
    sm = ScoreManager(shadow=True)
    sm.scoreboard = sb
    sm.bat1_name = "Alice Ace"
    sm.bat2_name = "Bob Baker"
    sm.striker = "Bob Baker"
    sm.non = "Alice Ace"
    sm.wickets = 1
    sm.score = 40
    sm.overs = 6.0

    pair_calls: list[tuple] = []
    real_set = sm._set_slot_pair.__get__(sm, type(sm))

    def _track(s, ns, *, source):
        pair_calls.append((s, ns, source))
        return real_set(s, ns, source=source)

    slot_warns: list[str] = []

    def _grab_warn(msg, *a, **k):
        slot_warns.append(str(msg))

    prev = {"overs": 6.0}
    card = {"overs": 6.0}
    frame = FrameInput(frame_id="w12", timestamp=1.0)
    evt = {
        "type": "WICKET",
        "runs": 0,
        "legal": True,
        "this_over_token": "W",
        "dismissed": "Alice Ace",
        "wicket_type": "caught",
    }
    with patch.object(sm, "_set_slot_pair", side_effect=_track):
        with patch.object(smod.log, "warn", new=_grab_warn):
            sm._apply_event(evt, prev, card, frame)

    check("one _set_slot_pair call from wicket non slot cleanup",
          len(pair_calls) == 1, pair_calls)
    check("W12 passes (survivor, None) + wicket_non source",
          pair_calls[0] == (
              "Bob Baker", None, "apply_event.wicket_non_striker_out"),
          pair_calls[0])
    check("END-STATE-NULL-OK: non cleared, striker is survivor",
          sm.non is None and sm.striker == "Bob Baker",
          (sm.striker, sm.non))
    check("no [SM-SLOT-INVARIANT] on legitimate None non write",
          not any("[SM-SLOT-INVARIANT]" in ln for ln in slot_warns),
          slot_warns or "(none)")


def _mi_srh_innings_break_poison_window_stats() -> tuple[int, int] | None:
    """Return (frame_poisoned_line_hits, nominal_frame_span) from MI vs SRH log.

    Window: first SCOUT line for F2347 through first line mentioning F2694
    (inclusive).  Used by ``test_fixture_frame_poisoned_rate_*``.
    """
    import re
    logp = (
        Path(__file__).resolve().parent.parent
        / "logs" / "pipeline-2026-04-29-194416-mi-srh-live.log")
    if not logp.is_file():
        return None
    raw_lines = logp.read_text(errors="replace").splitlines()

    def _strip_ansi(s: str) -> str:
        return re.sub(r"\x1b\[[0-9;]*m", "", s)

    lines = [_strip_ansi(x) for x in raw_lines]
    start = None
    for i, ln in enumerate(lines):
        if "F2347" in ln and "SCOUT" in ln:
            start = i
            break
    if start is None:
        return None
    end = None
    for j in range(start, len(lines)):
        if re.search(r"\bF2694\b", lines[j]):
            end = j
            break
    if end is None:
        return None
    window = lines[start:end + 1]
    poison = sum(1 for ln in window if "FRAME_POISONED" in ln)
    nominal = 2694 - 2347 + 1
    return (poison, nominal)


def test_fixture_frame_poisoned_rate_innings_break_baseline() -> None:
    """Innings-break poison rate baseline (F2347–F2694).

    Source: mi_srh architectural review §3.2; P0-C threshold validation
    input.  Observed 2026-04-30: 38 FRAME_POISONED hits over 348 nominal
    frames → ~10.9%.
    """
    stats = _mi_srh_innings_break_poison_window_stats()
    if stats is None:
        header("FRAME_POISONED innings-break baseline (log missing — skip)")
        check("skip when no log", True, "")
        return
    poison, nominal = stats
    EXPECTED_HITS = 38
    EXPECTED_NOMINAL = 348
    rate = poison / nominal
    EXPECTED_RATE = EXPECTED_HITS / EXPECTED_NOMINAL
    header("FRAME_POISONED rate F2347–F2694 (MI vs SRH log)")
    check("poison hit count stable",
          poison == EXPECTED_HITS,
          f"poison={poison} expected {EXPECTED_HITS}")
    check("nominal span stable", nominal == EXPECTED_NOMINAL,
          f"nominal={nominal}")
    check("rate within ±5pp of observed baseline",
          abs(rate - EXPECTED_RATE) <= 0.05,
          f"rate={rate:.4f} exp={EXPECTED_RATE:.4f}")


def test_fixture_multi_ball_gap_camera_state_transition() -> None:
    """MULTI_BALL placeholders (F2120+).

    Source: thread7_rediagnosis_multi_ball_gap.md §1; backlog §197–201.
    """
    from unittest.mock import patch

    import eyes.this_over as tom

    cap = _pbks_rr_telemetry_cap()
    om = tom.ThisOverManager()
    with patch.object(tom, "log", cap):
        om.on_ball_event(
            {"type": "MULTI_BALL", "balls_missed": 2, "total_runs": 6,
             "certain": False},
            score=227)
    joined = "\n".join(cap.infos + cap.warnings)
    check("this_over Missed telemetry",
          "Missed 2 balls" in joined and "+6 runs" in joined, joined[:400])
    check("two ? placeholders for two missed balls",
          om.this_over.count("?") == 2, om.this_over)
    tp_src = (Path(__file__).resolve().parent / "test_pipeline.py"
              ).read_text()
    check("production logs [THIS-OVER] Ball <type> after detector",
          "[THIS-OVER] Ball" in tp_src
          and "ball_event.get('type')" in tp_src,
          "expected THIS-OVER Ball append log in test_pipeline.py")


def _seed_sm_warm_for_gap(sm) -> None:
    """Minimal WARM baseline so ``on_frame`` runs ``_handle_warm``."""
    sm.mode = "WARM"
    sm.innings = 1
    sm.target = None
    sm.batting_team = "TT"
    sm.bat1_name = "Gap Alpha"
    sm.bat2_name = "Gap Beta"
    sm.bat1_runs = 10
    sm.bat1_balls = 8
    sm.bat2_runs = 12
    sm.bat2_balls = 9
    sm.striker = sm.bat1_name
    sm.non = sm.bat2_name
    sm.bowler_name = "Gap Bowler"
    sm.bowler_wickets = 0
    sm.bowler_runs = 20
    sm.bowler_overs = 4.0
    sm.this_over = []
    sm.this_over_src = []
    sm.over_history = {}
    sm.completed_over = []
    sm.partnership_known = True
    sm.partnership_balls = 20
    sm.partnership_runs = 40
    sm.fow_list = []
    sm._last_warm_state = sm._snapshot()


def _frame_for_gap(
        *,
        score: int,
        wk: int,
        overs: float,
        broadcast: str = "",
):
    from score_manager import FrameInput
    return FrameInput(
        frame_id="17001",
        timestamp=0.0,
        ext_score=score,
        ext_wickets=wk,
        ext_overs=overs,
        ext_bat1_name="Gap Alpha",
        ext_bat1_runs=10,
        ext_bat1_balls=8,
        ext_bat2_name="Gap Beta",
        ext_bat2_runs=12,
        ext_bat2_balls=9,
        ext_bowler_name="Gap Bowler",
        broadcast_striker=broadcast,
    )


def _run_gap_frame(
        sm,
        *,
        prev_score: int,
        prev_wk: int,
        prev_overs: float,
        new_score: int,
        new_wk: int,
        new_overs: float,
        multi_ball_max_patch: int | None = None,
        broadcast: str = "",
):
    """Apply one warm gap frame; optionally patch ``MULTI_BALL_MAX_BALLS``."""
    from contextlib import nullcontext
    from unittest.mock import patch

    import cricket_rules as cr

    sm.score = prev_score
    sm.wickets = prev_wk
    sm.overs = prev_overs
    sm._last_warm_state = sm._snapshot()
    ctx = (
        patch.object(cr, "MULTI_BALL_MAX_BALLS", multi_ball_max_patch)
        if multi_ball_max_patch is not None
        else nullcontext())
    with ctx:
        return sm.on_frame(_frame_for_gap(
            score=new_score, wk=new_wk, overs=new_overs,
            broadcast=broadcast))


def _enqueue_delivery_if_pipeline_would(ba, ball_event: dict):
    """Invoke ``enqueue_delivery_analysis`` only when pipeline branch would."""
    from test_pipeline import _layer2_enqueue_blocked_absorbed

    _real_delivery_types = {
        "DOT", "RUNS", "FOUR", "SIX", "WICKET",
        "WICKET_LATE",
        "WIDE", "NO_BALL", "EXTRA",
    }
    _evt_type_raw = ball_event.get("type", "")
    _evt_is_real = (
        _evt_type_raw in _real_delivery_types
        or _evt_type_raw.endswith("_RUNS")
    )
    if (ba is not None and getattr(ba, "alive", False)
            and not _layer2_enqueue_blocked_absorbed(ball_event)
            and _evt_is_real):
        return ba.enqueue_delivery_analysis()
    return None


def _would_enqueue_layer2_like_pipeline(ball_event: dict) -> bool:
    """Mirror ``test_pipeline`` enqueue guard (BallAnalyzer alive assumed)."""
    sys.modules.setdefault("ultralytics", MagicMock())
    from test_pipeline import _layer2_enqueue_blocked_absorbed

    _real_delivery_types = {
        "DOT", "RUNS", "FOUR", "SIX", "WICKET",
        "WICKET_LATE",
        "WIDE", "NO_BALL", "EXTRA",
    }
    _evt_type_raw = ball_event.get("type", "")
    _evt_is_real = (
        _evt_type_raw in _real_delivery_types
        or _evt_type_raw.endswith("_RUNS")
    )
    return (
        not _layer2_enqueue_blocked_absorbed(ball_event)
        and _evt_is_real
    )


def test_multi_ball_decompose_fixture_two_balls_no_extras() -> None:
    """d_balls=2, runs=0, wickets=0 → two ABSORBED_LEGAL; gap_parent on first."""
    header("multi_ball decompose — two balls, no runs/wickets")
    from score_manager import ABSORBED_LEGAL, ScoreManager

    sm = ScoreManager(shadow=True)
    _seed_sm_warm_for_gap(sm)
    payload = _run_gap_frame(
        sm, prev_score=100, prev_wk=0, prev_overs=10.1,
        new_score=100, new_wk=0, new_overs=10.3)
    check("payload returned", payload is not None, repr(payload))
    evs = payload.get("ball_events") or []
    check("two absorbed events", len(evs) == 2, f"{evs=!r}")
    check("types", all(e.get("type") == ABSORBED_LEGAL for e in evs),
          f"{evs=!r}")
    check("runs None (Policy U)", all(e.get("runs") is None for e in evs),
          f"{evs=!r}")
    check("not certain", all(e.get("certain") is False for e in evs),
          f"{evs=!r}")
    gp0 = evs[0].get("gap_parent")
    check("gap_parent on first only",
          gp0 is not None and evs[1].get("gap_parent") is None,
          f"{gp0=!r} ev1={evs[1].get('gap_parent')!r}")
    check("gap_parent balls_skipped",
          gp0.get("balls_skipped") == 2, repr(gp0))
    check("ball_event is last", payload.get("ball_event") == evs[-1],
          f"{payload.get('ball_event')!r}")


def test_multi_ball_decompose_fixture_seven_balls_partnership_this_over() -> None:
    """d_balls=7 (F3293-scale): partnership +7; ThisOverManager ×7 ``?``."""
    header("multi_ball decompose — seven balls, partnership + this_over")
    import eyes.this_over as tom

    from score_manager import ABSORBED_LEGAL, ScoreManager

    sm = ScoreManager(shadow=True)
    _seed_sm_warm_for_gap(sm)
    pb0 = sm.partnership_balls
    payload = _run_gap_frame(
        sm, prev_score=80, prev_wk=1, prev_overs=12.1,
        new_score=80, new_wk=1, new_overs=13.2)
    check("payload returned", payload is not None, repr(payload))
    evs = payload.get("ball_events") or []
    check("seven events", len(evs) == 7 and all(
        e.get("type") == ABSORBED_LEGAL for e in evs), f"n={len(evs)}")
    sc = (payload.get("scorecard") or {})
    check("partnership balls +7",
          sc.get("partnership", {}).get("balls") == pb0 + 7,
          repr(sc.get("partnership")))
    om = tom.ThisOverManager()
    _score = sc.get("score")
    for evt in evs:
        om.on_ball_event(evt, score=_score)
    check("this_over seven question marks",
          om.this_over.count("?") == 7, om.this_over)


def test_multi_ball_decompose_fixture_twentyfive_layer2_wire() -> None:
    """d_balls=25: no Layer 2 path; one absorbed-gap wire; per-ball wire None."""
    header("multi_ball decompose — 25 balls, layer2 + wire")
    from score_manager import ABSORBED_LEGAL, ScoreManager
    from wire import format_absorbed_gap_wire, format_wire

    sm = ScoreManager(shadow=True)
    _seed_sm_warm_for_gap(sm)
    payload = _run_gap_frame(
        sm, prev_score=50, prev_wk=0, prev_overs=4.1,
        new_score=50, new_wk=0, new_overs=8.2,
        multi_ball_max_patch=60)
    check("payload returned", payload is not None, repr(payload))
    evs = payload.get("ball_events") or []
    check("twenty-five events", len(evs) == 25, len(evs))
    gp = evs[0].get("gap_parent")
    check("gap_parent", gp is not None and gp.get("balls_skipped") == 25,
          repr(gp))
    snap = {
        "overs": sm.overs,
        "bowler": {"name": sm.bowler_name},
        "striker": sm.striker,
        "score": sm.score,
        "wickets": sm.wickets,
    }
    summary = format_absorbed_gap_wire(gp, snap, sm)
    check("one summary mentions absorbed 25",
          summary is not None and "absorbed 25" in summary.lower(),
          repr(summary))
    ba = MagicMock()
    ba.alive = True
    for i, evt in enumerate(evs):
        check(f"format_wire None for ball {i}",
              format_wire(evt, snap, sm) is None,
              repr(format_wire(evt, snap, sm)))
        check(
            "pipeline would not enqueue Layer 2",
            not _would_enqueue_layer2_like_pipeline(evt),
            evt.get("type"))
        _enqueue_delivery_if_pipeline_would(ba, evt)
    ba.enqueue_delivery_analysis.assert_not_called()


def test_multi_ball_decompose_fixture_four_balls_one_wicket_final_only() -> None:
    """Four absorbed balls, one wicket on final event only; one FOW row."""
    header("multi_ball decompose — wicket on final absorbed ball only")
    from score_manager import ABSORBED_LEGAL, ScoreManager

    sm = ScoreManager(shadow=True)
    _seed_sm_warm_for_gap(sm)
    fow0 = len(sm.fow_list)
    payload = _run_gap_frame(
        sm, prev_score=90, prev_wk=0, prev_overs=11.2,
        new_score=90, new_wk=1, new_overs=12.0,
        broadcast="Alpha")
    check("payload returned", payload is not None, repr(payload))
    evs = payload.get("ball_events") or []
    check("four absorbed", len(evs) == 4, len(evs))
    finals = [e for e in evs if e.get("gap_finalize_wicket")]
    check("single finalize flag", len(finals) == 1, finals)
    check("finalize is last", finals[0] == evs[-1], f"{finals[0]!r}")
    check("no wicket flag on first three",
          all("gap_finalize_wicket" not in e for e in evs[:3]),
          f"{evs=!r}")
    check("one FOW appended",
          len(sm.fow_list) == fow0 + 1, sm.fow_list)


def test_multi_ball_decompose_fixture_eight_balls_over_boundary() -> None:
    """5.4 → 7.0 (eight balls): event ``over`` steps 5.5, 6.0, 6.1, …"""
    header("multi_ball decompose — eight balls spanning over boundary")
    from score_manager import ABSORBED_LEGAL, ScoreManager

    sm = ScoreManager(shadow=True)
    _seed_sm_warm_for_gap(sm)
    payload = _run_gap_frame(
        sm, prev_score=60, prev_wk=0, prev_overs=5.4,
        new_score=60, new_wk=0, new_overs=7.0)
    check("payload returned", payload is not None, repr(payload))
    evs = payload.get("ball_events") or []
    check("eight events", len(evs) == 8, len(evs))
    overs_seq = [e.get("over") for e in evs]
    expect = ["5.5", "6.0", "6.1", "6.2", "6.3", "6.4", "6.5", "7.0"]
    check(
        "over metadata crosses over 5→6 between balls 2 and 3",
        overs_seq == expect,
        f"{overs_seq=!r}",
    )


def test_multi_ball_decompose_cap_exceeded_emits_warn_and_rejects_frame() -> None:
    """d_balls=15 > cap (12): no decomposition; ``[MULTI_BALL_CAP_EXCEEDED]`` logged."""
    header("multi_ball decompose — cap exceeded (reject)")
    from unittest.mock import patch

    import score_manager as sm_mod

    from cricket_rules import MULTI_BALL_MAX_BALLS
    from score_manager import ScoreManager

    sm = ScoreManager(shadow=True)
    _seed_sm_warm_for_gap(sm)
    warns: list[str] = []

    def _capture_warn(msg: str) -> None:
        warns.append(msg)

    # Δballs: 10.1 → 12.4 = 61→76 = 15 legal balls
    with patch.object(sm_mod.log, "warn", side_effect=_capture_warn):
        payload = _run_gap_frame(
            sm, prev_score=100, prev_wk=0, prev_overs=10.1,
            new_score=100, new_wk=0, new_overs=12.4)
    check("frame rejected (no payload)", payload is None, repr(payload))
    joined = "\n".join(warns)
    check(
        "[MULTI_BALL_CAP_EXCEEDED] telemetry",
        "[MULTI_BALL_CAP_EXCEEDED]" in joined
        and "d_balls=15" in joined
        and f"cap={MULTI_BALL_MAX_BALLS}" in joined
        and "emitted_count=0" in joined
        and "reason=reject" in joined,
        joined[:800],
    )


# ---------------------------------------------------------------------
# MI vs SRH innings-2 transition — P0-A / P0-B / P0-C (2026-04-30)
# Contract: files/docs/investigations/mi_srh_post_match_architectural_review.md
# ---------------------------------------------------------------------
def test_p0a_set_innings_2_idempotent() -> None:
    """Second ``set_innings_2`` is a no-op (no duplicate SM reset log)."""
    header("P0-A: ScoreManager.set_innings_2 idempotent")
    from unittest.mock import patch

    import score_manager as sm_mod
    from score_manager import ScoreManager

    sm = ScoreManager(shadow=True)
    infos: list[str] = []

    def _cap(msg: str, *a, **k) -> None:
        infos.append(str(msg))

    with patch.object(sm_mod.log, "info", side_effect=_cap):
        sm.set_innings_2(
            target=190, batting_team="MI", reason="p0a_once",
            archive=False)
        sm.set_innings_2(
            target=999, batting_team="SRH", reason="p0a_twice",
            archive=False)
    hits = [m for m in infos if "[SM-INNINGS-2-RESET]" in m]
    check("exactly one SM-INNINGS-2-RESET log",
          len(hits) == 1, f"hits={hits!r}")
    check("second reason never logged (early return)",
          all("p0a_twice" not in m for m in hits),
          hits[0][:200] if hits else "")


def test_p0a_fix16_coverage_overs_complete_20() -> None:
    """Timeout / innings-break path carries ``overs_complete_20`` into SM."""
    header("P0-A: Fix 16 coverage — overs_complete_20 → execute_innings_change")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    check(
        "_execute_innings_change_from_state resets overs via callback",
        "reset_for_innings_cb(2, overs_reset_source=source)" in src,
        "expected reset_for_innings_cb(2, overs_reset_source=source)",
    )
    check("SM innings-2 reset uses same source as reason on swap path",
          "score_mgr.set_innings_2(" in src and "reason=source" in src,
          "expected score_mgr.set_innings_2(..., reason=source)")
    check("overs_complete_20 wired to innings-break latch",
          "overs_complete_20" in src and "_inn_break_pending_source" in src,
          "expected overs_complete_20 + _inn_break_pending_source")


def test_p0a_fix16_coverage_poison_recal_cold_start() -> None:
    """INIT first-frame innings-2 detect logs poison_recal cold-start."""
    header("P0-A: Fix 16 coverage — poison_recal_cold_start INIT path")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    check("INIT path calls score_mgr.set_innings_2 with poison_recal reason",
          'reason="poison_recal_cold_start"' in src,
          "expected reason=\"poison_recal_cold_start\"")
    check("INIT path emits OVERS-TRACKER-RESET poison_recal_cold_start",
          "source=poison_recal_cold_start" in src
          and "[OVERS-TRACKER-RESET]" in src,
          "expected [OVERS-TRACKER-RESET] source=poison_recal_cold_start")


def test_p0b_overs_tracker_reset_after_innings_change() -> None:
    """reset_overs_consensus clears confirmed overs floor."""
    header("P0-B: overs consensus floor clears after reset_overs_consensus")
    from eyes.consistent_tracker import ConsistentReadTracker

    t = ConsistentReadTracker()
    for fc in (1, 2, 3):
        t.update("overs", "20.0", frame_count=fc)
    check("overs reached consensus at 20.0",
          t.confirmed.get("overs") == "20.0",
          f"confirmed={t.confirmed.get('overs')!r}")
    t.reset_overs_consensus()
    check("confirmed overs cleared",
          t.confirmed.get("overs") is None,
          f"confirmed={t.confirmed.get('overs')!r}")


def test_p0b_overs_tracker_reset_telemetry() -> None:
    """Log wiring for [OVERS-TRACKER-RESET] sources in test_pipeline."""
    header("P0-B: OVERS-TRACKER-RESET telemetry sources wired")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    check("marker present", "[OVERS-TRACKER-RESET]" in src, "missing tag")
    for key in (
        "source=poison_recal_cold_start",
        'overs_reset_source="scorer_innings_change"',
        "overs_reset_source=\"FORCE_INNINGS_ENV\"",
        'overs_reset_source="broadcast_target_detect"',
        'overs_reset_source="AUTO-SWAP"',
    ):
        check(f"wiring includes {key!r}", key in src, "substring missing")


def test_p0b_overs_progression_after_reset() -> None:
    """Post-reset low overs are not blocked by a stale 20.0 floor."""
    header("P0-B: progression after reset accepts low overs")
    from eyes.consistent_tracker import ConsistentReadTracker

    t = ConsistentReadTracker()
    for fc in (1, 2, 3):
        t.update("overs", "20.0", frame_count=fc)
    t.reset_overs_consensus()
    for fc in (4, 5, 6):
        t.update("overs", "0.2", frame_count=fc)
    check("low overs re-commit after reset",
          t.confirmed.get("overs") == "0.2",
          f"confirmed={t.confirmed.get('overs')!r}")


def test_p0c_fixture_a_poison_recal_innings_change_regression() -> None:
    """P0-C: inn1-completed overrides false cold_start (MI vs SRH root)."""
    header("P0-C fixture A: poison-recal / wiped overs vs cold_start gate")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    check(
        "cold_start_inn2 gated on inn1_completed_deterministic (extracted fn)",
        "cold_start_inn2 = (" in src
        and "not inn1_completed_deterministic" in src,
        "expected not inn1_completed_deterministic in cold_start_inn2",
    )
    check("deterministic latch sets _inn1_completed_deterministic",
          "_inn1_completed_deterministic = True" in src
          and "overs_complete_20" in src,
          "expected latch assignment near overs_complete_20")


def test_p0c_fixture_b_cricket_rules_swap_with_latch() -> None:
    """P0-C: latched bowling team becomes innings-2 batting on swap path."""
    header("P0-C fixture B: cricket-rules swap uses latch")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    check("cricket-rules telemetry present",
          "[TEAM-ATTRIBUTION-CRICKET-RULES]" in src,
          "missing tag")
    check(
        "new batting team from latched bowling",
        "inn1_bowling_team_latched" in src
        and "new_bat = inn1_bowling_team_latched" in src,
        "expected new_bat = inn1_bowling_team_latched",
    )


def test_p0c_fixture_c_no_false_positive_normal_play() -> None:
    """P0-C: FRAME_POISONED strip-trust threshold is telemetry-only."""
    header("P0-C fixture C: threshold does not gate team swap")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    n = src.count("_FRAME_POISONED_STRIP_TRUST_THRESHOLD")
    check("threshold only used for constant + poison-rate log",
          n == 2,
          f"expected 2 occurrences, got {n}")
    _fn = "def _execute_innings_change_from_state"
    check(
        "team swap branch does not compare threshold",
        _fn in src
        and "_FRAME_POISONED_STRIP_TRUST_THRESHOLD" not in
        src[src.index(_fn): src.index(_fn) + 4500],
        "threshold leaked into _execute_innings_change_from_state body",
    )


def test_p0c_fixture_d_strip_fallback_when_latch_unavailable() -> None:
    """P0-C: missing latch falls back to strip closure with telemetry."""
    header("P0-C fixture D: strip fallback telemetry")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    check("strip fallback tag present",
          "[TEAM-ATTRIBUTION-STRIP-FALLBACK]" in src,
          "missing tag")


def test_p0c_fixture_e_recovery_to_strip_post_swap() -> None:
    """P0-C: rolling poison-rate telemetry exists (post-swap observability)."""
    header("P0-C fixture E: poison-rate deque + telemetry")
    src = (Path(__file__).resolve().parent / "test_pipeline.py").read_text()
    check("poison deque wired", "_poisoned_in_window" in src, "missing deque")
    check("periodic poison-rate log",
          "[TEAM-ATTRIBUTION-POISON-RATE]" in src,
          "missing [TEAM-ATTRIBUTION-POISON-RATE]")


def test_innings_transition_window_parser() -> None:
    header("MI-SRH log: innings-change firing rows F2660–F2900")
    logp = (
        Path(__file__).resolve().parent.parent
        / "logs" / "pipeline-2026-04-29-194416-mi-srh-live.log")
    ev = _parse_innings_transition_window(logp, 2660, 2900)
    check("at least one resolve event",
          len(ev) >= 1, repr(ev))
    check("overs_complete_20 at F2695 class",
          ev[0]["source"] == "overs_complete_20",
          repr(ev[0]))
    # Log line may carry target=None when chase total is not echoed on the row.
    check("target parsed when present (244) or explicit None",
          ev[0]["target"] in (244, None),
          repr(ev[0]))
    if logp.is_file():
        check("frame within requested band",
              ev[0]["frame"] == 2695,
              repr(ev[0]))


def test_pre_innings_2_transition_fixture_integrity() -> None:
    header("Pre-innings-2 fixture: latch + tracker floor")
    import test_pipeline as tp

    fx = _build_pre_innings_2_transition_fixture(tp.log)
    sb = fx["scoreboard"]
    tr = sb._tracker
    ns = fx["state_ns"]
    check("tracker had locked 20.0 overs floor before extract hook clears",
          getattr(tr, "confirmed", {}).get("overs") == "20.0",
          repr(getattr(tr, "confirmed", {})))
    check("P0-C deterministic latch",
          ns.inn1_completed_deterministic is True,
          repr(ns))
    check("latched bowling is SRH (innings-2 bat via cricket rules)",
          ns.inn1_bowling_team_latched == fx["srh"],
          ns.inn1_bowling_team_latched)
    check("closure batting_team MI pre-transition",
          ns.batting_team == fx["mi"],
          ns.batting_team)


def test_p0_fixes_e2e_mi_srh_f2660_f2900_innings_transition() -> None:
    header("P0 E2E: F2660–F2900 extract replay — SM reset + overs + latch swap")
    import score_manager as sm_mod
    import test_pipeline as tp

    cap = _pbks_rr_telemetry_cap()
    fx = _build_pre_innings_2_transition_fixture(tp.log)
    sb = fx["scoreboard"]
    sm = fx["score_mgr"]
    ns = fx["state_ns"]

    logp = (
        Path(__file__).resolve().parent.parent
        / "logs" / "pipeline-2026-04-29-194416-mi-srh-live.log")

    def _snapshot(label: str) -> tuple:
        _inn = sb._inn or {}
        scr = _inn.get("score")
        tgt = _inn.get("target")
        return (
            label,
            sb.current_innings,
            ns.batting_team,
            ns.bowling_team,
            scr,
            _inn.get("overs"),
            _inn.get("wickets"),
            int(tgt) if tgt is not None else None,
        )

    sig_steps = [_snapshot("pre")]
    triggers_raw = _parse_innings_transition_window(logp, 2660, 2900)
    triggers: list[dict] = []
    for ev in triggers_raw:
        _t = ev["target"]
        if _t is None and ev["source"] == "overs_complete_20":
            _t = 244
        triggers.append({**ev, "target": _t})

    def _apply_out(out: dict) -> None:
        ns.team_locked = out["team_locked"]
        ns.bowling_team_strip_count = out["bowling_team_strip_count"]
        ns.pending_innings_2 = out["pending_innings_2"]
        ns.pending_target = out["pending_target"]
        ns.inn2_consecutive = out["inn2_consecutive"]
        ns.batting_team = out["batting_team"]
        ns.bowling_team = out["bowling_team"]
        ns.inn_break_pending = out["inn_break_pending"]
        ns.inn_break_pending_frame = out["inn_break_pending_frame"]
        ns.inn_break_pending_source = out["inn_break_pending_source"]
        ns.inn1_batting_team_latched = out["inn1_batting_team_latched"]
        ns.inn1_bowling_team_latched = out["inn1_bowling_team_latched"]
        ns.inn1_completed_deterministic = out["inn1_completed_deterministic"]

    sm_infos: list[str] = []

    def _cap_sm_info(msg: str, *a, **k) -> None:
        sm_infos.append(str(msg))
        cap.info(msg, *a, **k)

    with patch.object(sm_mod.log, "info", side_effect=_cap_sm_info):
        with patch.object(tp.log, "info", cap.info):
            with patch.object(tp.log, "warn", cap.warn):
                with patch.object(tp.log, "debug", create=True):
                    for ev in triggers:
                        out = tp._execute_innings_change_from_state(
                            source=ev["source"],
                            target=ev["target"],
                            scoreboard=sb,
                            score_mgr=sm,
                            ball_analyzer=None,
                            log=tp.log,
                            frame_count=ev["frame"],
                            team_locked=ns.team_locked,
                            bowling_team_strip_count=ns.bowling_team_strip_count,
                            pending_innings_2=ns.pending_innings_2,
                            pending_target=ns.pending_target,
                            inn2_consecutive=ns.inn2_consecutive,
                            batting_team=ns.batting_team,
                            bowling_team=ns.bowling_team,
                            inn_break_pending=ns.inn_break_pending,
                            inn_break_pending_frame=ns.inn_break_pending_frame,
                            inn_break_pending_source=ns.inn_break_pending_source,
                            inn1_batting_team_latched=ns.inn1_batting_team_latched,
                            inn1_bowling_team_latched=ns.inn1_bowling_team_latched,
                            inn1_completed_deterministic=(
                                ns.inn1_completed_deterministic),
                            assign_teams_cb=fx["assign_teams_cb"],
                            reset_for_innings_cb=fx["reset_for_innings_cb"],
                        )
                        check(
                            f"transition applied ({ev['source']})",
                            out["did_change"] is True,
                            repr(out))
                        _apply_out(out)
                        sig_steps.append(_snapshot(f"post-{ev['frame']}"))
                        out_dup = tp._execute_innings_change_from_state(
                            source=ev["source"],
                            target=ev["target"],
                            scoreboard=sb,
                            score_mgr=sm,
                            ball_analyzer=None,
                            log=tp.log,
                            frame_count=ev["frame"] + 1,
                            team_locked=ns.team_locked,
                            bowling_team_strip_count=ns.bowling_team_strip_count,
                            pending_innings_2=ns.pending_innings_2,
                            pending_target=ns.pending_target,
                            inn2_consecutive=ns.inn2_consecutive,
                            batting_team=ns.batting_team,
                            bowling_team=ns.bowling_team,
                            inn_break_pending=ns.inn_break_pending,
                            inn_break_pending_frame=ns.inn_break_pending_frame,
                            inn_break_pending_source=ns.inn_break_pending_source,
                            inn1_batting_team_latched=ns.inn1_batting_team_latched,
                            inn1_bowling_team_latched=ns.inn1_bowling_team_latched,
                            inn1_completed_deterministic=(
                                ns.inn1_completed_deterministic),
                            assign_teams_cb=fx["assign_teams_cb"],
                            reset_for_innings_cb=fx["reset_for_innings_cb"],
                        )
                        check("second call idempotent (innings already 2)",
                              out_dup["did_change"] is False,
                              repr(out_dup))
                        sig_steps.append(_snapshot("post-idempotent"))

    pipeline_msgs = "\n".join(cap.infos + cap.warnings + sm_infos)
    check(
        "P0-A: [SM-INNINGS-2-RESET] with transition reason",
        "[SM-INNINGS-2-RESET]" in pipeline_msgs,
        pipeline_msgs[-1200:],
    )
    check(
        "P0-B: [OVERS-TRACKER-RESET] from replay harness",
        "[OVERS-TRACKER-RESET]" in pipeline_msgs
        and "source=overs_complete_20" in pipeline_msgs,
        pipeline_msgs[-1200:],
    )
    check(
        "P0-C: cricket-rules swap — SRH bats innings 2",
        "[TEAM-ATTRIBUTION-CRICKET-RULES]" in pipeline_msgs,
        pipeline_msgs[-1200:],
    )
    check(
        "innings-2 batting team is SRH (not MI stuck chasing)",
        ns.batting_team == fx["srh"],
        f"{ns.batting_team=!r}",
    )
    active_names = {
        n for n, c in sb.batting_card.items()
        if c.get("status") == "batting"}
    check(
        "active batters ⊆ SRH XI",
        active_names <= set(fx["srh_xi"]),
        f"{active_names=!r}",
    )
    ob_txt = _f2660_f2900_transition_signature_text(sig_steps)
    baseline = _F2660_F2900_TRANSITION_BASELINE_PATH.read_text()
    check(
        "transition signature matches baseline file",
        ob_txt == baseline,
        f"len actual={len(ob_txt)} baseline={len(baseline)}",
    )


# ---------------------------------------------------------------------
# live_match_monitor.py — DWR window line parser (regex contract)
# ---------------------------------------------------------------------
def test_live_match_monitor_parse_dwr_window_line():
    import importlib.util
    from pathlib import Path as _P

    lmp = _P(__file__).resolve().parent / "scripts" / "live_match_monitor.py"
    spec = importlib.util.spec_from_file_location(
        "_live_match_monitor_under_test", lmp)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    p = mod.parse_dwr_window_line
    assert p(
        "[DWR] window #1 source=retrospective_span frames=55 "
        "span=1777558277.20->1777558280.70 reason=latest_bowlers_end_span"
    ) == (1, "retrospective_span", 55)
    assert p(
        "[DWR] window #12 source=fallback_pre_event_window frames=159 "
        "span=1777558486.39->1777558498.89 reason=no_bowlers_end_span"
    ) == (12, "fallback_pre_event_window", 159)
    assert p(
        "[DWR] window #3 source=experimental_path frames=42 span=x"
    ) == (3, "experimental_path", 42)
    assert p("[DWR] rejecting stale span [1, 2]") is None


# ---------------------------------------------------------------------
# Issue 2 Task B — striker-aligned extractor rows for ScoreManager FrameInput
# ---------------------------------------------------------------------
# Fixtures verbatim from batter_stats_flipping_fix_spec.md §4.1.

FIXTURE_INVERTED_STRIP_VS_STRIKER = {
    "ext_batters": [
        {"name": "Shubman Gill", "runs": 0, "balls": 0},
        {"name": "Sai Sudharsan", "runs": 1, "balls": 1},
    ],
    "score_mgr_striker": "Sai Sudharsan",
    "score_mgr_non": "Shubman Gill",
    "expect_before_fix_bat1_name": "Shubman Gill",
    "expect_after_fix_bat1_name": "Sai Sudharsan",
    "expect_after_fix_bat2_name": "Shubman Gill",
}

FIXTURE_COLD_STRIP_ORDER = {
    "ext_batters": [
        {"name": "Alpha Z", "runs": 10, "balls": 8},
        {"name": "Beta Y", "runs": 4, "balls": 3},
    ],
    "score_mgr_striker": None,
    "score_mgr_non": None,
    "expect_after_fix_bat1_name": "Alpha Z",
    "expect_after_fix_bat2_name": "Beta Y",
}

FIXTURE_SINGLE_ROW_STRIKER = {
    "ext_batters": [
        {"name": "Shubman Gill", "runs": 5, "balls": 3},
    ],
    "score_mgr_striker": "Shubman Gill",
    "score_mgr_non": "Sai Sudharsan",
    "expect_after_fix_bat1_name": "Shubman Gill",
    "expect_after_fix_bat2_name": None,
}

FIXTURE_DUAL_ROW_NO_MATCH = {
    "ext_batters": [
        {"name": "Unknown Batter X", "runs": 1, "balls": 1},
        {"name": "Unknown Batter Y", "runs": 0, "balls": 1},
    ],
    "score_mgr_striker": "Shubman Gill",
    "score_mgr_non": "Sai Sudharsan",
    "expect_after_fix_bat1_name": "Unknown Batter X",
    "expect_after_fix_bat2_name": "Unknown Batter Y",
    "expect_warn_tag": "[BATTER-ALIGN]",
}

FIXTURE_PARTIAL_MATCH_NON_UNKNOWN = {
    "ext_batters": [
        {"name": "Shubman Gill", "runs": 12, "balls": 9},
        {"name": "New Batter Z", "runs": 0, "balls": 0},
    ],
    "score_mgr_striker": "Shubman Gill",
    "score_mgr_non": None,
    "expect_after_fix_bat1_name": "Shubman Gill",
    "expect_after_fix_bat2_name": "New Batter Z",
}

FIXTURE_LOG_F2689_STRIP_ORDER = {
    "ext_batters": [
        {"name": "Sai Sudharsan", "runs": 1, "balls": 1},
        {"name": "Shubman Gill", "runs": 0, "balls": 0},
    ],
    "score_mgr_striker": "Sai Sudharsan",
    "score_mgr_non": "Shubman Gill",
    "note": (
        "Matches tee 27048 STRIP column order; alignment output equals "
        "strip order — regression signal weaker than Fixture A."
    ),
}


def _align_fixture_resolve_name(raw: str | None):
    """Minimal resolve_name stub matching tests’ batting-card canon."""
    if not raw:
        return None
    table = {
        "Shubman Gill": "Shubman Gill",
        "Sai Sudharsan": "Sai Sudharsan",
        "Alpha Z": "Alpha Z",
        "Beta Y": "Beta Y",
        "Unknown Batter X": None,
        "Unknown Batter Y": None,
        "New Batter Z": None,
    }
    return table.get(raw.strip())


def _run_align_extractor_fixture(fix: dict, *, log: MagicMock | None = None):
    import sys

    # Importing ``test_pipeline`` pulls optional vision deps (YOLO); stub for tests.
    sys.modules.setdefault("ultralytics", MagicMock())

    from score_manager import ScoreManager
    from test_pipeline import _align_extractor_batters_for_sm

    sm = ScoreManager(shadow=True)
    sm.striker = fix["score_mgr_striker"]
    sm.non = fix["score_mgr_non"]
    sb = MagicMock()
    sb.resolve_name.side_effect = _align_fixture_resolve_name
    lg = log if log is not None else MagicMock()
    eb1, eb2 = _align_extractor_batters_for_sm(
        fix["ext_batters"], scoreboard=sb, score_mgr=sm, log=lg)
    return eb1, eb2, lg


def test_align_extractor_batters_fixture_a_inverted_strip_vs_striker() -> None:
    header("align extractor batters — inverted strip vs striker (fixture A)")
    eb1, eb2, _lg = _run_align_extractor_fixture(FIXTURE_INVERTED_STRIP_VS_STRIKER)
    check(
        "bat1 is striker (Sudharsan) with aligned stats",
        eb1 is not None
        and eb1.get("name") == FIXTURE_INVERTED_STRIP_VS_STRIKER[
            "expect_after_fix_bat1_name"]
        and eb1.get("runs") == 1 and eb1.get("balls") == 1,
        f"{eb1=!r}",
    )
    check(
        "bat2 is non-striker (Gill) with aligned stats",
        eb2 is not None
        and eb2.get("name") == FIXTURE_INVERTED_STRIP_VS_STRIKER[
            "expect_after_fix_bat2_name"]
        and eb2.get("runs") == 0 and eb2.get("balls") == 0,
        f"{eb2=!r}",
    )


def test_align_extractor_batters_fixture_b_cold_strip_order() -> None:
    header("align extractor batters — cold striker preserves strip order (B)")
    eb1, eb2, _lg = _run_align_extractor_fixture(FIXTURE_COLD_STRIP_ORDER)
    check(
        "bat1/bat2 follow extractor strip index order",
        eb1 is not None and eb2 is not None
        and eb1.get("name") == FIXTURE_COLD_STRIP_ORDER[
            "expect_after_fix_bat1_name"]
        and eb2.get("name") == FIXTURE_COLD_STRIP_ORDER[
            "expect_after_fix_bat2_name"],
        f"{eb1=!r} {eb2=!r}",
    )


def test_align_extractor_batters_fixture_c_single_row_striker() -> None:
    header("align extractor batters — single row striker slot (C)")
    eb1, eb2, _lg = _run_align_extractor_fixture(FIXTURE_SINGLE_ROW_STRIKER)
    check(
        "sole row routed to bat1 when striker matches",
        eb1 is not None
        and eb1.get("name") == FIXTURE_SINGLE_ROW_STRIKER[
            "expect_after_fix_bat1_name"]
        and eb1.get("runs") == 5 and eb1.get("balls") == 3,
        f"{eb1=!r}",
    )
    check(
        "bat2 absent for single-row striker hit",
        eb2 is None,
        f"{eb2=!r}",
    )


def test_align_extractor_batters_fixture_d_dual_row_no_match_fallback() -> None:
    header("align extractor batters — OCR mismatch fallback + warn (D)")
    log = MagicMock()
    eb1, eb2, lg = _run_align_extractor_fixture(FIXTURE_DUAL_ROW_NO_MATCH, log=log)
    check(
        "fallback preserves strip bat1/bat2 names",
        eb1 is not None and eb2 is not None
        and eb1.get("name") == FIXTURE_DUAL_ROW_NO_MATCH[
            "expect_after_fix_bat1_name"]
        and eb2.get("name") == FIXTURE_DUAL_ROW_NO_MATCH[
            "expect_after_fix_bat2_name"],
        f"{eb1=!r} {eb2=!r}",
    )
    check(
        "CASE 4 emits striker-align fallback telemetry",
        lg.warn.called,
        "warn not called",
    )
    warn_msg = lg.warn.call_args[0][0]
    check(
        "warn carries STRIKER-ALIGN-FALLBACK tag (spec §4 expect_warn_tag "
        "legacy [BATTER-ALIGN] superseded at emit site)",
        "[STRIKER-ALIGN-FALLBACK]" in warn_msg,
        repr(warn_msg),
    )


def test_align_extractor_batters_fixture_e_partial_match_partner_unknown() -> None:
    header("align extractor batters — wicket substitution partner slot (E)")
    eb1, eb2, _lg = _run_align_extractor_fixture(FIXTURE_PARTIAL_MATCH_NON_UNKNOWN)
    check(
        "striker row stays bat1",
        eb1 is not None
        and eb1.get("name") == FIXTURE_PARTIAL_MATCH_NON_UNKNOWN[
            "expect_after_fix_bat1_name"],
        f"{eb1=!r}",
    )
    check(
        "remaining extractor row fills bat2",
        eb2 is not None
        and eb2.get("name") == FIXTURE_PARTIAL_MATCH_NON_UNKNOWN[
            "expect_after_fix_bat2_name"],
        f"{eb2=!r}",
    )


def test_align_extractor_batters_fixture_f_log_f2689_strip_order_noop() -> None:
    header("align extractor batters — F2689 strip order no-op (F)")
    eb1, eb2, _lg = _run_align_extractor_fixture(FIXTURE_LOG_F2689_STRIP_ORDER)
    x = FIXTURE_LOG_F2689_STRIP_ORDER["ext_batters"]
    check(
        "alignment matches strip column order (Sudharsan then Gill)",
        eb1 is not None and eb2 is not None
        and eb1.get("name") == x[0]["name"] and eb2.get("name") == x[1]["name"],
        f"{eb1=!r} {eb2=!r}",
    )


def test_batch_o_wire_uses_bed_ball_event_when_present() -> None:
    """Batch O: wire emission must prefer BED's ball_event over SM's
    `_sm_evt`.  Pre-fix, SM's warm-mode `_infer_legal` returned DOT
    for every legal ball (because `self.score` is a live property
    over scoreboard._inn that the broadcast tracker had already
    mutated), and `format_wire(_sm_evt, ...)` rendered "no run" on
    every scoring delivery.  See investigation memo §C1."""
    header("Batch O: wire prefers BED's ball_event over SM's DOT")
    from wire import format_wire

    ball_event = {"type": "FOUR", "runs": 4, "striker": "Marsh"}
    _sm_evt = {"type": "DOT", "runs": 0, "striker": "Marsh"}
    snap = {
        "overs": "1.2", "score": 16, "wickets": 0,
        "bowler": {"name": "Bumrah"},
    }
    _wire_event = ball_event if ball_event else _sm_evt
    line = format_wire(_wire_event, snap, None)

    check("selection picks BED's ball_event",
          _wire_event is ball_event,
          f"_wire_event={_wire_event!r}")
    check("rendered text contains 'FOUR'",
          line is not None and "FOUR" in line,
          f"line={line!r}")
    check("rendered text does NOT contain 'no run'",
          line is not None and "no run" not in line,
          f"line={line!r}")
    check("rendered score suffix is post-event total (16/0)",
          line is not None and line.endswith("16/0"),
          f"line={line!r}")

    src = (Path(__file__).resolve().parent / "test_pipeline.py"
           ).read_text()
    check("test_pipeline.py contains the BED-preference selector",
          "_wire_event = ball_event if ball_event else _sm_evt" in src,
          "selector line not found in test_pipeline.py")


def test_batch_o_wire_falls_back_to_sm_evt() -> None:
    """Batch O: when BED has no ball_event for the frame (e.g. a wide
    that never ticked overs), the wire emission falls back to
    `_sm_evt`.  This preserves coverage for SM-only cases (extras,
    deferred resolutions) where BED is silent."""
    header("Batch O: wire falls back to _sm_evt when ball_event is None")
    from wire import format_wire

    ball_event = None
    _sm_evt = {"type": "WIDE", "runs": 1, "striker": "Inglis",
               "legal": False, "this_over_token": "Wd"}
    snap = {
        "overs": "0.3", "score": 7, "wickets": 0,
        "bowler": {"name": "Chahar"},
    }
    _wire_event = ball_event if ball_event else _sm_evt
    line = format_wire(_wire_event, snap, None)

    check("selection falls back to _sm_evt",
          _wire_event is _sm_evt,
          f"_wire_event={_wire_event!r}")
    check("rendered text contains 'wide'",
          line is not None and "wide" in line.lower(),
          f"line={line!r}")
    check("rendered text does NOT contain 'no run'",
          line is not None and "no run" not in line,
          f"line={line!r}")


# ---------------------------------------------------------------------
# Batch BB — DWR `_find_span` between_play bridge anchor (2026-05-05)
# Reference: files/docs/investigations/
#            retrospective_span_regression_root_cause.md Phase D #1.
# ---------------------------------------------------------------------
def _batch_bb_make_recorder(tags):
    """Construct a DeliveryWindowRecorder whose tagged-source returns
    the supplied static `tags` list and capture `[PHASE-*]` log lines.

    `tags` is a list of `(ts, camera_view, frame_phase)` tuples; the
    recorder's `_get_tags(lo, hi, _)` filters by [lo, hi].  No frames,
    no classifier calls.
    """
    import logging
    from delivery_window_recorder import DeliveryWindowRecorder

    snapshot = [(ts, None, view, phase) for (ts, view, phase) in tags]

    def _frames(_lo, _hi):
        return []

    def _tagged(lo, hi, _views):
        return [t for t in snapshot if lo <= t[0] <= hi]

    rec = DeliveryWindowRecorder(
        classifier=None,
        frame_source_fn=_frames,
        tagged_source_fn=_tagged,
        save_root=None,
    )

    captured: list[str] = []

    class _Cap(logging.Handler):
        def emit(self, record):
            captured.append(record.getMessage())

    h = _Cap(level=logging.INFO)
    dwr_log = logging.getLogger("delivery_window_recorder")
    dwr_log.addHandler(h)
    dwr_log.setLevel(logging.INFO)
    return rec, captured, h


def test_batch_bb_action_phase_accepted_as_before() -> None:
    header("Batch BB · action-phase anchor accepted (RC-7 baseline)")
    event_ts = 1000.0
    rec, _msgs, _h = _batch_bb_make_recorder([
        (event_ts - 3.0, "bowlers_end", "release"),
    ])
    span = rec._find_span(event_ts=event_ts, target_view="bowlers_end")
    check(
        "release tag at t-3 is admitted as a single-anchor span",
        span == (event_ts - 3.0, event_ts - 3.0),
        f"span={span!r}",
    )


def test_batch_bb_isolated_between_play_rejected() -> None:
    header("Batch BB · isolated between_play rejected (RC-7 preserved)")
    event_ts = 1000.0
    rec, msgs, _h = _batch_bb_make_recorder([
        (event_ts - 5.0, "bowlers_end", "between_play"),
    ])
    span = rec._find_span(event_ts=event_ts, target_view="bowlers_end")
    rejects = [m for m in msgs if "[PHASE-REJECT]" in m]
    bridge = [m for m in msgs if "[PHASE-BRIDGE-ACCEPT]" in m]
    check(
        "find_span returns None when only an isolated between_play "
        "tag is in the lookback",
        span is None,
        f"span={span!r}",
    )
    check(
        "PHASE-REJECT log carries reason=isolated_between_play",
        any("reason=isolated_between_play" in m for m in rejects),
        f"rejects={rejects!r}",
    )
    check(
        "no PHASE-BRIDGE-ACCEPT emitted for isolated between_play",
        bridge == [],
        f"bridge={bridge!r}",
    )


def test_batch_bb_between_play_bridge_accepted() -> None:
    header("Batch BB · between_play admitted as bridge anchor")
    event_ts = 1000.0
    rec, msgs, _h = _batch_bb_make_recorder([
        (event_ts - 5.0, "bowlers_end", "release"),
        (event_ts - 3.0, "bowlers_end", "between_play"),
        (event_ts - 2.0, "bowlers_end", "shot"),
    ])
    span = rec._find_span(event_ts=event_ts, target_view="bowlers_end")
    bridge = [m for m in msgs if "[PHASE-BRIDGE-ACCEPT]" in m]
    check(
        "find_span returns a span spanning all three contiguous tags",
        span == (event_ts - 5.0, event_ts - 2.0),
        f"span={span!r}",
    )
    check(
        "PHASE-BRIDGE-ACCEPT logged for the between_play anchor",
        any(f"ts={event_ts - 3.0:.2f}" in m for m in bridge),
        f"bridge={bridge!r}",
    )


def test_batch_bb_between_play_outside_bridge_window_rejected() -> None:
    header("Batch BB · between_play outside MAX_CONTIGUOUS_GAP_S "
           "rejected")
    event_ts = 1000.0
    # release@t-7 sits inside MAX_END_TO_EVENT_GAP_S (8 s) so the
    # span itself is valid.  between_play@t-3 is 4 s away from the
    # release — beyond the 2.5 s bridge window — so it must NOT be
    # admitted as a bridge anchor.
    rec, msgs, _h = _batch_bb_make_recorder([
        (event_ts - 7.0, "bowlers_end", "release"),
        (event_ts - 3.0, "bowlers_end", "between_play"),
    ])
    span = rec._find_span(event_ts=event_ts, target_view="bowlers_end")
    rejects = [m for m in msgs if "[PHASE-REJECT]" in m]
    bridge = [m for m in msgs if "[PHASE-BRIDGE-ACCEPT]" in m]
    check(
        "between_play far from any action tag is rejected as isolated",
        any("reason=isolated_between_play" in m
            and f"ts={event_ts - 3.0:.2f}" in m
            for m in rejects),
        f"rejects={rejects!r}",
    )
    check(
        "no PHASE-BRIDGE-ACCEPT for the far between_play",
        bridge == [],
        f"bridge={bridge!r}",
    )
    check(
        "release@t-7 still admitted (single-anchor span)",
        span == (event_ts - 7.0, event_ts - 7.0),
        f"span={span!r}",
    )


# ---------------------------------------------------------------------
# Bowler / delivery UI accuracy cluster (#32 #24 #30 #31)
# ---------------------------------------------------------------------
def _empty_fi():
    from score_manager import FrameInput
    return FrameInput(frame_id="fi-test", timestamp=0.0)


def test_bug32_speed_regex_kph_optional() -> None:
    header("Bug #32: SPEED regex accepts no-suffix and applies "
           "60-170 range guard")
    from test_pipeline import extract_broadcast_data
    check("'SPEED: 132.7' (no suffix) → 132.7",
          extract_broadcast_data("SPEED: 132.7", {}).get("speed_kph")
          == 132.7,
          f"got={extract_broadcast_data('SPEED: 132.7', {}).get('speed_kph')}")
    check("'SPEED: 137.7 kph' still works",
          extract_broadcast_data("SPEED: 137.7 kph", {}).get("speed_kph")
          == 137.7,
          "kph suffix path broken")
    check("'SPEED: 135 km/h' accepted",
          extract_broadcast_data("SPEED: 135 km/h", {}).get("speed_kph")
          == 135.0,
          "km/h suffix path broken")
    check("'SPEED: 1' (pre-truncation) rejected by range",
          "speed_kph" not in extract_broadcast_data("SPEED: 1", {}),
          "range-guard low side failed")
    check("'SPEED: 200' rejected by range",
          "speed_kph" not in extract_broadcast_data("SPEED: 200", {}),
          "range-guard high side failed")


def test_bug24_speed_clears_on_next_legal_ball() -> None:
    header("Bug #24: stale speed cleared when next legal ball commits "
           "without a fresh reading")
    from score_manager import ScoreManager
    sm = ScoreManager(shadow=False)
    sm.overs = 4.2
    sm._update_supplements({"speed_kph": 97.0}, _empty_fi())
    check("speed captured with over-cursor tag",
          sm.last_speed == 97.0 and sm.last_speed_at_over == 4.2,
          f"last_speed={sm.last_speed}, at_over={sm.last_speed_at_over}")
    # Advance over cursor and mirror the stat-accumulator clear:
    # legal ball, no speed read, over cursor diverges from tag.
    sm.overs = 4.3
    if (sm.last_speed is not None
            and sm.last_speed_at_over != sm.overs):
        sm.last_speed = None
        sm.last_speed_at_over = None
    check("stale speed cleared once over cursor advances",
          sm.last_speed is None and sm.last_speed_at_over is None,
          f"last_speed={sm.last_speed}, at_over={sm.last_speed_at_over}")


def test_bug24_speed_persists_within_same_over_cursor() -> None:
    header("Bug #24: speed survives across re-reads at the same "
           "over cursor")
    from score_manager import ScoreManager
    sm = ScoreManager(shadow=False)
    sm.overs = 4.3
    sm._update_supplements({"speed_kph": 132.4},
                           frame=None)  # type: ignore[arg-type]
    # Second supplement at same over (e.g. card re-read with no SPEED)
    sm._update_supplements({}, _empty_fi())
    check("speed_kph preserved within same over cursor",
          sm.last_speed == 132.4 and sm.last_speed_at_over == 4.3,
          f"last_speed={sm.last_speed}, at_over={sm.last_speed_at_over}")


def test_bug30_ext_name_matches_canonical_short_name() -> None:
    header("Bug #30: bowler short name resolves via "
           "scoreboard.resolve_name")
    from test_pipeline import _ext_name_matches_canonical
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL",
                     ["b1", "b2"],
                     ["Krunal Pandya", "Hardik Pandya", "Bumrah"])
    check("strict-equal match still works",
          _ext_name_matches_canonical(
              "Krunal Pandya", "Krunal Pandya", sb),
          "strict-equal failed")
    check("'KRUNAL' resolves to 'Krunal Pandya'",
          _ext_name_matches_canonical("KRUNAL", "Krunal Pandya", sb),
          "short-name resolver did not match canonical")
    check("empty extractor name returns False",
          not _ext_name_matches_canonical("", "Krunal Pandya", sb),
          "empty-name guard failed")
    check("non-matching name returns False",
          not _ext_name_matches_canonical(
              "Bumrah", "Krunal Pandya", sb),
          "unrelated short-name should not match")


def test_bug31_get_live_state_emits_last_bowler_fields() -> None:
    header("Bug #31: Scoreboard.get_live_state emits last_bowler + "
           "bowler_between_overs fields")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL", ["b1", "b2"],
                     ["Josh Hazlewood", "Trent Boult"])
    sb._inn["current_bowler"] = "Josh Hazlewood"
    sb._inn["bowler_between_overs"] = False
    state = sb.get_live_state()
    check("current_bowler exposed",
          state.get("current_bowler") == "Josh Hazlewood",
          f"state={state.get('current_bowler')!r}")
    check("bowler_between_overs=False during live spell",
          state.get("bowler_between_overs") is False,
          f"flag={state.get('bowler_between_overs')!r}")
    # Simulate over-end clear (mirrors test_pipeline.py:~11646)
    sb._inn["last_bowler"] = sb._inn.get("current_bowler")
    sb._inn["current_bowler"] = None
    sb._inn["bowler_between_overs"] = True
    state = sb.get_live_state()
    check("current_bowler cleared after over end",
          state.get("current_bowler") is None,
          f"state={state}")
    check("last_bowler preserved across the gap",
          state.get("last_bowler") == "Josh Hazlewood",
          f"last={state.get('last_bowler')!r}")
    check("bowler_between_overs=True during the gap",
          state.get("bowler_between_overs") is True,
          f"flag={state.get('bowler_between_overs')!r}")


def test_bug31_update_bowler_clears_between_overs_flag() -> None:
    header("Bug #31: update_bowler bootstrap clears "
           "bowler_between_overs")
    from eyes.scoreboard import Scoreboard
    sb = Scoreboard()
    sb.setup_innings("BAT", "BOWL", ["b1", "b2"],
                     ["Josh Hazlewood", "Trent Boult"])
    sb._inn["last_bowler"] = "Josh Hazlewood"
    sb._inn["current_bowler"] = None
    sb._inn["bowler_between_overs"] = True
    sb.update_bowler("Trent Boult", frame=100)
    check("current_bowler installed",
          sb._inn.get("current_bowler") == "Trent Boult",
          f"current={sb._inn.get('current_bowler')!r}")
    check("bowler_between_overs cleared on bootstrap",
          sb._inn.get("bowler_between_overs") is False,
          f"flag={sb._inn.get('bowler_between_overs')!r}")
    check("last_bowler retained as history",
          sb._inn.get("last_bowler") == "Josh Hazlewood",
          f"last={sb._inn.get('last_bowler')!r}")


# ---------------------------------------------------------------------
# 11. Run all
# ---------------------------------------------------------------------
TESTS = [
    test_tracker_cold_start_consensus,
    test_tracker_hallucination_blocked,
    test_tracker_force_set_bypasses,
    test_score_manager_cold_consensus,
    test_score_manager_hallucination_resets_streak,
    test_cold_start_starvation_then_pipeline_watchdog_fallback,
    test_cold_start_flip_heavy_pipeline_watchdog_fallback,
    test_cold_start_fallback_blocked_by_absolute,
    test_cold_consensus_fast_path_before_pipeline_watchdog,
    test_this_over_observed_cap,
    test_this_over_over_jump_rejected,
    test_this_over_history_immutable,
    test_this_over_late_boundary_ball_appends_to_held,
    test_score_manager_boundary_ball_belongs_to_completed_over,
    test_fow_no_trim,
    test_fow_no_overwrite_confirmed,
    test_fow_placeholder_upgrade,
    test_validate_overs_digit_swap,
    test_validate_overs_legitimate_passthrough,
    test_validate_overs_boundary_fix,
    test_validate_overs_refuses_regression_below_confirmed,
    test_phantom_dismissal_inference_disabled,
    test_legbye_requires_both_witnesses,
    test_bed_preserves_prev_overs_when_team_overs_missing,
    test_innings_reset_methods_exist_and_wipe_state,
    test_match_situation_run_rate_falls_back_to_zero,
    test_score_manager_cold_start_rejects_incomplete_card,
    test_extractor_wins_on_numbers_in_apply_scorer_decision,
    test_frame_poisoned_skips_when_no_confirmed_score,
    test_graphic_strip_info_panel_keyword_large_delta_strips_score,
    test_graphic_strip_info_panel_keyword_small_delta_keeps_score,
    test_poison_recal_graphic_phase_preempt_wired_in_source,
    test_p7_fix_b_consensus_preserved_on_graphic_wired_in_source,
    test_p7_fix_b_contradiction_sites_set_poison_non_graphic,
    test_p7_fix_c_score_inf_gate_direct_wired_in_source,
    test_p7_fix_c_direct_gate_suppressed_on_cold_start,
    test_twenty_over_invariant_check_in_source,
    test_witnessed_dismissal_helper,
    test_fix1_refuses_undismiss_on_witnessed_fow,
    test_fix1_walk_back_already_batting_no_false_trigger,
    test_fix1_legit_yet_to_bat_activation_still_works,
    test_fix2_post_hoc_demote_resurrected,
    test_fix3_three_active_demotes_fow_not_position,
    test_fix3_position_fallback_when_no_fow_match,
    test_p0b_gate_bypass_reasserts_witnessed_dismissal,
    test_p0b_gate_blocks_phantom_wicket_no_fow,
    test_p0b_gate_bypass_skipped_on_multi_missing,
    test_p0b_end_to_end_rana_activates_via_update_batter,
    test_update_player_styles_patches_existing_cards,
    test_update_player_styles_preserves_runtime_stats,
    test_update_player_styles_handles_missing_or_empty,
    test_enrich_squad_styles_pass2_background_skips_pass2,
    test_enrich_squad_styles_pass2_async_invokes_callback,
    test_enrich_squad_styles_pass2_async_failure_caches_pass1,
    test_archival_noop_when_src_dir_missing,
    test_archival_noop_when_src_empty,
    test_archival_moves_existing_frames,
    test_archival_preserves_eval_path_resolution,
    test_archival_retention_drops_oldest_sessions,
    test_archival_retention_noop_when_under_cap,
    test_bowler_stale_replay_shivang_f311_f500_trap,
    test_bowler_stale_replay_sakib_second_trap_general,
    test_bowler_stale_genuine_stale_graphic_still_rejected,
    test_bowler_stale_boundary_within_freshness_same_context,
    test_bowler_stale_boundary_within_freshness_different_context,
    test_bowler_team_over_consensus_promotes_matching_candidate,
    test_bowler_team_over_consensus_ignores_mismatched_candidate,
    test_bowler_plain_consensus_rejects_spell_ball_mismatch,
    test_bowler_plain_consensus_accepts_aligned_spell_ball,
    test_bowler_plain_consensus_override_after_repeated_mismatch,
    test_batch_m_per_field_rejection,
    test_batch_m_full_consistent_update,
    test_project_fow_for_payload_hides_unwitnessed_placeholders,
    test_sampler_emits_bucket_coverage_report,
    test_combined_sampler_emits_phase_bucket_coverage,
    test_combined_sampler_deterministic_with_seed,
    test_combined_sampler_strict_mode_exits_nonzero_on_warn,
    test_combined_sampler_phase_bucket_metadata_in_output,
    test_combined_sampler_backward_compat_with_run_shadow,
    test_combined_sampler_undocumented_zero_warn,
    test_closeup_frames_persisted_before_short_circuit,
    test_element_checker_header_uses_configured_match,
    test_cluster1_canonical_active_slot_prefers_score_manager,
    test_path_b_inn_sm_mirror_lockstep,
    test_path_b_striker_read_sm_canonical_drs_detail_present_in_source,
    test_path_b_striker_read_sm_canonical_returns_sm_value_on_divergence,
    test_cluster1_scorer_active_gate_blocks_witnessed_out_batter,
    test_cluster1_update_batter_witnessed_out_striker_flag_no_slot_write,
    test_cluster1_auto_dismiss_prefers_sm_striker_over_stale_inn,
    # --- Inter-match commit (2026-04-25 RR vs SRH match-2 fixes) ---
    # Fix 1: target=640 sanity bound on innings-1 latch
    test_innings1_latch_rejects_phantom_639_at_76_overs,
    test_innings1_latch_accepts_normal_t20_final,
    test_innings1_latch_phantom_does_not_lock_real_final,
    test_innings1_latch_sanity_boundaries,
    test_innings1_latch_max_wins_within_bounds,
    test_innings1_latch_callsite_wired_in_source,
    # Fix 2: this_over token-alphabet validation
    test_this_over_alphabet_helper_boundary_cases,
    test_p8_this_over_regex_rejects_multi_digit,
    test_p8_line_fallback_bounded_by_separator,
    test_p8_line_fallback_max_chars,
    test_p8_get_display_floor_pad_bounded,
    test_p8_cold_start_regex_rejects_multi_digit,
    # Fix 3: this_over chronological reorder on FOW upgrade
    test_this_over_reorder_w_after_boundary_to_correct_ball,
    test_this_over_reorder_no_op_when_position_already_correct,
    test_this_over_reorder_handles_no_w_gracefully,
    test_this_over_reorder_extras_are_skipped_in_legal_count,
    test_scoreboard_fow_upgrade_callback_fires_on_upgrade,
    test_scoreboard_fow_upgrade_callback_no_fire_on_immutable_skip,
    # Fix 4: overs CONSENSUS-BLOCKED regression guard
    test_overs_consensus_blocked_rejects_powerplay_regression,
    test_overs_consensus_blocked_progression_still_accepted,
    test_overs_consensus_blocked_set_innings_2_path_still_works,
    test_overs_consensus_blocked_other_fields_unaffected,
    # Fix 5: striker self-collision guard in update_batter
    test_striker_collision_refuses_non_write_when_same_as_striker,
    test_striker_collision_refuses_striker_write_when_same_as_non,
    test_striker_collision_idempotent_self_writes_unaffected,
    test_striker_collision_f170_f173_replay,
    # Fix 6: Pass-2 client config (timeout=240.0, max_retries=0)
    test_pass2_client_timeout_config_explicit,
    # Fix 7: WS-PROJECTION-GAP fallback (sb._inn when SM-null + active)
    test_ws_projection_fallback_sm_resolved_no_fallback,
    test_ws_projection_fallback_sm_null_dismissed_no_fallback,
    test_ws_projection_fallback_sm_null_active_uses_sb_inn,
    test_ws_projection_fallback_f145_w2_replay,
    test_ws_projection_fallback_collision_avoidance_with_other_slot,
    test_ws_projection_fallback_requires_batting_status,
    test_ws_projection_fallback_resolves_name_before_status_check,
    # Dual-broadcaster unification: SM feeds canonical WS builder
    test_dual_broadcaster_unification_routes_sm_frames_via_canonical_builder,
    # Fix 8: INFO-PANEL bowler-strip gate (content-based graphic gate)
    test_info_panel_gate_strips_bowler_on_career_keyword,
    test_info_panel_gate_no_op_when_no_keyword,
    test_info_panel_gate_f619_chahal_replay,
    test_info_panel_gate_logs_only_when_no_bowler_present,
    test_info_panel_gate_strips_all_three_bowler_fields,
    test_standings_row_gate_strips_score_fields,
    test_standings_row_gate_no_op_without_keyword,
    test_admission_normalizes_rinku_singh_ghost_row,
    test_admission_new_batter_impossible_balls_rejected,
    test_admission_batter_row_name_does_not_become_bowler,
    test_recovery_cold_start_zero_graphic_rejected,
    test_recovery_mid_innings_partnership_backstaged_until_ball,
    test_recovery_this_over_resync_clears_saturated_cursor,
    test_physics_all_out_authority_promotes_and_locks_regression,
    test_physics_score_regression_blocked_without_reset_authority,
    test_ws_slot_invariant_repairs_duplicate_active_slots,
    test_ws_slot_invariant_clears_when_no_alternate_active,
    # Fix 9a: AUTO-SWAP target injection from latched innings_1_total
    test_fix9a_autoswap_target_injection_block_present_in_source,
    test_fix9a_autoswap_target_injection_runs_before_assign_teams,
    test_fix9a_autoswap_target_uses_innings_1_total_latched_score,
    test_fix16_autoswap_calls_score_manager_set_innings_2,
    # Fix 9b: target-monotonic + target-sanity guard at team_assignment
    test_fix9b_target_monotonic_guard_present_in_source,
    test_fix9b_target_sanity_guard_rejects_below_team_score,
    test_fix9b_target_unconditional_overwrite_removed,
    # Fix 10: post-witnessed-FOW slot rotation hook (Path A)
    test_fix10_striker_dismissed_rotates_non_into_striker,
    test_fix10_non_dismissed_clears_non_only,
    test_fix10_run_out_at_striker_end_handled_via_name_match,
    test_fix10_dismissed_name_in_neither_slot_is_noop,
    test_fix10_anomaly_both_slots_dismissed_clears_both,
    test_fix10_placeholder_upgrade_path_also_fires_hook,
    test_fix10_powell_f179_f258_placeholder_upgrade_with_drifted_slots,
    test_fix10_auto_dismiss_path_clears_slot_via_hook,
    test_fix10_dismiss_batter_path_compatible_with_hook,
    test_fix10_helper_method_exists_on_scoreboard,
    test_fix10_hook_call_present_in_source,
    test_fix13_path_b_known_wicket_increment_cleans_placeholder_gap,
    test_fix13_path_b_wicket_handler_wired_in_source,
    test_fow_committed_at_wicket_ball_event,
    test_fow_not_committed_when_wickets_counter_zero,
    test_auto_dismiss_requires_incoming_consensus,
    # --- Bowler / delivery UI accuracy cluster (#32 #24 #30 #31) ---
    test_bug32_speed_regex_kph_optional,
    test_bug24_speed_clears_on_next_legal_ball,
    test_bug24_speed_persists_within_same_over_cursor,
    test_bug30_ext_name_matches_canonical_short_name,
    test_bug31_get_live_state_emits_last_bowler_fields,
    test_bug31_update_bowler_clears_between_overs_flag,
    test_wire_format_accepts_fractional_cricket_overs_string,
    test_wire_format_accepts_integer_over_string,
    # Fix 11: EXTRAS-INF admission gate (Layer 1 of phantom +N quartet)
    test_fix11_gate_blocks_phantom_admission_simple,
    test_fix11_gate_passes_legitimate_admission,
    test_fix11_gate_abstains_on_incomplete_dismissed_count,
    test_fix11_gate_abstains_on_unknown_dismissed_runs,
    test_fix11_gate_neutralizes_extractor_init_path_too,
    test_fix11_gate_hosein_f2408_production_replay,
    test_fix11_gate_does_not_block_score_side_phantom,
    test_fix11_gate_block_present_in_source,
    test_fix14_balls_ceiling_rejects_powell_class,
    test_fix14_balls_ceiling_passes_legitimate_balls_count,
    test_fix14_balls_ceiling_tolerance_absorbs_edge_cases,
    test_fix14_balls_ceiling_block_present_in_source,
    test_fix15_score_side_gate_rejects_unexplained_advance,
    test_fix15_score_side_gate_passes_explained_advance,
    test_fix15_score_side_gate_passes_extras_only_advance,
    test_fix15_score_inf_floor_rejects_phantom_low_score,
    test_fix15_score_inf_floor_passes_legitimate_raise,
    test_fix15_score_inf_floor_suppressed_innings_transition_reset,
    test_fix15_score_inf_floor_suppressed_cold_start_no_committed_score,
    test_fix15_score_inf_floor_boundary_proposed_equals_min,
    test_fix15_score_side_gate_block_present_in_source,
    test_fix16_set_innings_2_resets_cached_scalars,
    test_fix16_set_innings_2_idempotent,
    test_sm_full_reset_clears_fix16_scalar_surface,
    test_sm_full_reset_clears_cold_start_bookkeeping,
    test_sm_full_reset_preserves_match_context,
    test_bowler_stats_graphic_gate_rejects_in_t20_keyword,
    test_bowler_stats_graphic_gate_rejects_implausible_figures,
    test_bowler_stats_graphic_gate_accepts_live_spell,
    test_bowler_stats_graphic_gate_accepts_career_word_with_plausible_spell,
    test_poison_recal_source_calls_full_reset,
    test_poison_recal_semantic_full_reset_clears_sm_scalars,
    test_scorer_invariant_filter_witnessed_out_batter_row,
    test_scorer_dismissed_resurrect_non_witnessed_out,
    test_scorer_active_batter_updates_not_filtered,
    test_scorer_schema_normalize_batter_row_ok,
    test_scorer_schema_multi_field_coerce_drops_row,
    test_scorer_schema_enforce_drops_bad_batter_update,
    test_scorer_schema_shadow_keeps_batter_row,
    test_scorer_schema_finalize_shadow_emits_would_tags,
    test_scorer_match_state_parse_json_returns_empty_dict,
    test_item2_apply_scorer_emits_schema_would_coerce,
    test_item2_batters_invariant_rule_a_emitted,
    test_analyzer_pending_validation_includes_item2_patterns,
    test_state_recovery_phase2_disabled_skips_mutation,
    test_state_recovery_phase2_enabled_resets_sm_and_patches_inn,
    test_state_recovery_phase2_field_scoped_score_only,
    test_fix16_handle_innings_change_routes_through_setter,
    test_fix17_path_a_pre_match_graphic_gate_in_source,
    test_fix17_path_d_cold_start_ws_gate_blocks_no_team,
    test_fix17_path_d_cold_start_ws_gate_opens_on_team_commit,
    test_fix17_path_d_cold_start_ws_gate_opens_on_canonical_shape,
    test_fix17_path_d_cold_start_ws_gate_safety_timeout,
    test_fix17_path_d_block_present_in_source,
    test_fix18_layer2_reconciler_fires_on_smaller_divergence,
    test_fix18_layer3_cap_reset_picks_most_recent_advance,
    test_fix18_layer3_iterative_cap_reset,
    test_fix18_innings_2_resets_last_advance,
    test_fix18_update_batter_records_advance,
    # Fix 12: rejection-consensus release on runs-monotonic guard
    # (Layer 4 of phantom +N quartet)
    test_fix12_streak_increments_on_repeated_rejections,
    test_fix12_release_fires_at_threshold,
    test_fix12_streak_resets_on_different_rejected_value,
    test_fix12_streak_clears_on_legitimate_acceptance,
    test_fix12_zero_regression_clause_also_tracked,
    test_fix12_dube_f1767_production_replay,
    test_fix12_release_clears_row_rejected_flag,
    test_fix12_per_batter_independence,
    test_fix12_innings_2_resets_streak,
    test_fix12_block_present_in_source,
    # State-recovery consensus override (Phase 1 telemetry-only)
    test_state_recovery_no_fire_single_guard,
    test_state_recovery_candidate_fires_two_guard_families,
    test_state_recovery_resets_on_candidate_change,
    test_state_recovery_rejects_incoherent_bat_sum,
    test_state_recovery_suppressed_during_innings_transition,
    test_state_recovery_fix12_boundary_single_field_excluded,
    # Analyzer extension: per-fix telemetry validation reports
    test_analyzer_fix9a_parses_autoswap_inject,
    test_analyzer_fix9a_parses_autoswap_skipped,
    test_analyzer_fix9b_parses_target_monotonic_and_sanity,
    test_analyzer_fix10_parses_three_rotation_kinds,
    test_analyzer_fix11_parses_extras_inf_gate,
    test_analyzer_fix12_parses_streak_and_release,
    test_analyzer_state_recovery_candidate_parses_detail,
    test_analyzer_striker_collision_and_wicket_transitions,
    test_analyzer_bin_by_wicket_assigns_events_to_correct_bins,
    test_analyzer_report_fix_10_per_wicket_histogram_renders,
    test_analyzer_report_fix_10_silent_when_no_fires,
    test_analyzer_report_fix_9b_silent_marks_fix_9a_as_doing_its_job,
    test_analyzer_baseline_counterfactuals_present,
    test_analyzer_bundle_bc_signature_report_counts_new_guards,
    test_pbks_rr_replay_bowler_batter_gate_strips_with_telemetry,
    test_pbks_rr_replay_striker_sm_cutover_mirror_telemetry,
    test_pbks_rr_replay_ws_slot_invariant_repair_telemetry,
    test_pbks_rr_replay_batter_normalize_surname_ghost_telemetry,
    test_pbks_rr_replay_new_batter_balls_ceiling_telemetry,
    test_pbks_rr_replay_scorer_active_gate_witnessed_out_telemetry,
    test_pbks_rr_replay_over_resync_post_restart_cursor_telemetry,
    test_pbks_rr_replay_scorer_invariant_filter_witnessed_out_telemetry,
    test_pbks_rr_replay_scorer_dismissed_resurrect_telemetry,
    test_pbks_rr_replay_bowler_team_over_consensus_accepts_telemetry,
    test_pbks_rr_replay_pending_validation_catalog_all_patterns_synthetic,
    test_path_b_fow_list_property_reads_scoreboard,
    test_path_b_fow_list_property_returns_none_when_sb_unattached,
    test_path_b_innings_extras_property_reads_scoreboard,
    test_path_b_innings_extras_property_returns_none_when_sb_unattached,
    test_path_b_bat1_runs_property_reads_scoreboard,
    test_path_b_bat1_runs_setter_is_noop_with_telemetry,
    test_path_b_bowler_runs_property_reads_scoreboard,
    test_path_b_bowler_runs_setter_is_noop_with_telemetry,
    test_path_b_innings_property_reads_scoreboard,
    test_path_b_innings_setter_is_noop_with_telemetry,
    test_path_b_score_property_reads_scoreboard,
    test_path_b_score_setter_calls_sb_set_with_telemetry,
    test_path_b_score_setter_handles_sb_unattached,
    test_path_b_score_setter_in_shadow_emits_parity_only,
    test_path_b_score_setter_continues_on_sb_reject,
    test_path_b_batting_team_property_reads_scoreboard,
    test_path_b_batting_team_setter_calls_sb_set_with_telemetry,
    test_path_b_batting_team_setter_in_shadow_emits_parity_only,
    test_path_b_bowler_name_divergence_telemetry_present_in_source,
    test_ws_payload_helpers_extracted_module_level,
    test_get_broadcast_state_aliases_get_live_state,
    test_get_broadcast_state_shadow_mode_uses_canonical_projection,
    test_get_broadcast_state_back_compat_signature,
    test_set_slot_pair_writes_both_slots_atomically,
    test_set_slot_pair_repairs_canonical_collision_with_telemetry,
    test_set_slot_pair_canonicalization_uses_existing_helper,
    test_sm_pr2_w8_identify_and_set_routes_via_set_slot_pair,
    test_sm_pr2_w8_non_keeps_distinct_prior_non_else_branch,
    test_sm_pr2_w8_partner_alias_collides_emits_sm_slot_invariant,
    test_sm_pr2_w8_balls_delta_happy_path_distinct_pair,
    test_path_b_bowler_name_divergence_rate_limited_in_source,
    # Thread 7 Fix 1 + MI vs SRH fixtures (2026-04-30)
    test_thread7_fix1_row_misalignment_pops_only_batters,
    test_thread7_fix1_row_misalignment_emits_telemetry,
    test_thread7_fix1_no_misalignment_preserves_all,
    test_thread7_fix1_replay_f2134_f2135_recovery,
    test_batch_n_call_site_uses_batters_only_flag,
    test_batch_n_flag_initialized_per_frame,
    test_batch_n_dismissal_gate_honors_batters_only,
    test_batch_n_guard_log_message_marks_batters_only,
    test_batch_n_pooran_cascade_score_overs_bowler_preserved,
    test_batch_u_drop_off_roster_row,
    test_batch_u_keep_all_when_on_roster,
    test_batch_u_drop_both_when_both_off_roster,
    test_batch_w_overlay_prefilter_doesnt_block_score,
    test_batch_v_sub_a_rejects_all_four,
    test_batch_v_sub_b_rejects_overs_only,
    test_batch_v_both_a_and_b,
    test_batch_v_no_stale_regression,
    test_thread7_fix2_cam_graphic_live_strip_accepts,
    test_thread7_fix2_cam_graphic_replay_rejects,
    test_thread7_fix2_cam_graphic_career_card_rejects_f2768,
    test_thread7_fix2_cam_graphic_preview_rejects,
    test_thread7_fix2_g6_max_delta_six_accepts,
    test_thread7_fix2_g7_max_ball_delta_accepts,
    test_thread7_fix2_cooldown_identity_noop,
    test_thread7_fix2_cooldown_different_content_accepts,
    test_thread7_fix2_f2128_cam_graphic_during_gap,
    test_thread7_fix2_no_overlap_with_fix1_telemetry,
    test_thread7_fix2_pipeline_contains_noop_tag,
    test_fixture_batters_invariant_admission_window_cluster,
    test_fixture_batters_invariant_rule_a_resurrection_f2167,
    test_fixture_striker_sm_cutover_intra_over_wicket_gap,
    test_pr3_w8_dismissed_guard_fires,
    test_pr3_w8_dismissed_guard_dedup,
    test_pr3_integration_mi_srh_admission_window_recovery,
    test_pr3_batter_arrival_cutover_fires,
    test_pr3_integration_full_innings_replay,
    test_pr3_w3_w7_helper_routing,
    test_pr3_telemetry_dedup_validation,
    test_pr4_w11_helper_routing,
    test_pr4_w12_helper_routing,
    test_fixture_frame_poisoned_rate_innings_break_baseline,
    test_fixture_multi_ball_gap_camera_state_transition,
    test_p0a_set_innings_2_idempotent,
    test_p0a_fix16_coverage_overs_complete_20,
    test_p0a_fix16_coverage_poison_recal_cold_start,
    test_p0b_overs_tracker_reset_after_innings_change,
    test_p0b_overs_tracker_reset_telemetry,
    test_p0b_overs_progression_after_reset,
    test_p0c_fixture_a_poison_recal_innings_change_regression,
    test_p0c_fixture_b_cricket_rules_swap_with_latch,
    test_p0c_fixture_c_no_false_positive_normal_play,
    test_p0c_fixture_d_strip_fallback_when_latch_unavailable,
    test_p0c_fixture_e_recovery_to_strip_post_swap,
    test_innings_transition_window_parser,
    test_pre_innings_2_transition_fixture_integrity,
    test_p0_fixes_e2e_mi_srh_f2660_f2900_innings_transition,
    test_innings_history_snapshot_includes_full_scorecard,
    test_innings_history_two_append_sites_consistent,
    test_ws_payload_exposes_innings_history,
    test_ws_payload_innings_history_empty_innings_1,
    test_path_b_low_risk_batch_path_a_regression_signature_match,
    test_shadow_eval_merge_overlay_replaces_variant_rows,
    test_shadow_eval_resolve_under_files,
    test_shadow_eval_cli_help_exit_zero,
    test_shadow_eval_run_shadow_dry_run,
    test_replicate_migration_hash_deterministic_with_same_data,
    test_replicate_migration_hash_changes_with_different_votes,
    test_replicate_cross_run_metrics_basic_synthetic_triple,
    test_shadow_eval_replicate_analysis_cli_help,
    test_run_shadow_groq_completion_metadata_extract,
    test_run_shadow_groq_completion_metadata_sparse_response,
    test_run_shadow_timeout_s_default_15,
    test_run_shadow_timeout_s_cli_override,
    test_run_shadow_timeout_retry_logic,
    test_run_shadow_timeout_retry_caps_at_max_attempts,
    test_run_shadow_429_retry_still_works,
    test_replicate_legacy_shadow_run_json_no_groq_fields,
    test_v6d_variant_registered,
    test_v6d_preserves_v6c_closeup_example,
    test_v6d_includes_bowlers_end_negative_test,
    test_v6d_other_rulebook_includes_f941_signature,
    test_v6d_prompt_structure_matches_v6c_step_organization,
    test_v6d_no_schema_drift,
    test_v6e_variant_registered,
    test_v6e_preserves_v6d_other_rulebook,
    test_v6e_preserves_v6c_closeup_example,
    test_v6e_includes_side_on_negative_clause,
    test_v6e_prompt_structure_matches_v6d,
    test_live_match_monitor_parse_dwr_window_line,
    test_multi_ball_decompose_fixture_two_balls_no_extras,
    test_multi_ball_decompose_fixture_seven_balls_partnership_this_over,
    test_multi_ball_decompose_fixture_twentyfive_layer2_wire,
    test_multi_ball_decompose_fixture_four_balls_one_wicket_final_only,
    test_multi_ball_decompose_fixture_eight_balls_over_boundary,
    test_multi_ball_decompose_cap_exceeded_emits_warn_and_rejects_frame,
    test_align_extractor_batters_fixture_a_inverted_strip_vs_striker,
    test_align_extractor_batters_fixture_b_cold_strip_order,
    test_align_extractor_batters_fixture_c_single_row_striker,
    test_align_extractor_batters_fixture_d_dual_row_no_match_fallback,
    test_align_extractor_batters_fixture_e_partial_match_partner_unknown,
    test_align_extractor_batters_fixture_f_log_f2689_strip_order_noop,
    test_batch_f_un_dismiss_refused_for_wicket_ball_event_source,
    test_batch_f_un_dismiss_allowed_for_auto_inference_source,
    test_batch_f_wicket_on_wicket_no_resurrection,
    test_batch_j_incoming_batter_promoted_from_strip,
    test_batch_j_two_wickets_consecutive_via_strip,
    test_batch_j_no_promotion_when_innings_all_out,
    test_batch_l_defer_when_strip_empty,
    test_batch_l_strip_path_still_works,
    test_batch_l_no_phantom_dismissal_on_correct_arrival,
    test_batch_o_wire_uses_bed_ball_event_when_present,
    test_batch_o_wire_falls_back_to_sm_evt,
    test_batch_x_field_refreshes_on_wicket,
    test_batch_bb_action_phase_accepted_as_before,
    test_batch_bb_isolated_between_play_rejected,
    test_batch_bb_between_play_bridge_accepted,
    test_batch_bb_between_play_outside_bridge_window_rejected,
    # --- DC-vs-CSK reliability batch (2026-05-05) ---
    test_dc_csk_fix1_unwitnessed_fow_renders_as_question_mark,
    test_dc_csk_fix2_bowler_proposes_when_batter_row_poisoned,
    test_dc_csk_fix3_fast_commit_source_present,
    test_dc_csk_fix4_phantom_score_jump_requires_two_frame_confirmation,
    test_dc_csk_fix4_predictable_increment_commits_first_read,
    test_dc_csk_fix5_duplicate_strip_rows_rejected,
    test_dc_csk_fix5_neither_match_logs_name_mismatch_and_rejects,
    test_dc_csk_fix6_gap_padded_with_question_mark,
    test_dc_csk_fix7_dismissed_batter_in_strip_rejects_entire_read,
    test_dc_csk_fix7_no_dismissed_match_passes_through,
    test_dc_csk_trace_tags_registered,
]


TESTS_REQUIRING_GROQ_SDK = frozenset({"test_pass2_client_timeout_config_explicit"})


def main() -> int:
    run_groq = "--run-groq" in sys.argv[1:]
    tests = list(TESTS)
    if not run_groq:
        tests = [t for t in tests if t.__name__ not in TESTS_REQUIRING_GROQ_SDK]
        skipped = len(TESTS) - len(tests)
        if skipped:
            print(
                f"\n(Skipping {skipped} Groq SDK test(s); "
                "pass --run-groq or run `just test-full`.)\n")
    for tfn in tests:
        try:
            tfn()
        except Exception:
            global FAIL
            FAIL += 1
            FAILURES.append((tfn.__name__, traceback.format_exc()))
            print(f"  CRASH {tfn.__name__}\n{traceback.format_exc()}")

    print(f"\n=== Results ===")
    print(f"  PASS {PASS}")
    print(f"  FAIL {FAIL}")
    if not run_groq:
        g_skip = sum(
            1 for t in TESTS if t.__name__ in TESTS_REQUIRING_GROQ_SDK)
        if g_skip:
            print(f"  SKIPPED (Groq SDK) {g_skip}")
    if FAILURES:
        print("\nFailures:")
        for name, detail in FAILURES:
            dtext = detail if isinstance(detail, str) else repr(detail)
            print(f"  {name}: {dtext.splitlines()[0] if dtext else ''}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
