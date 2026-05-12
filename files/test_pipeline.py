"""Automated pipeline test — no team assumption, auto-detect from broadcast."""
from __future__ import annotations

import asyncio
import collections
from collections.abc import Callable
from collections import deque
from typing import Any
import hashlib
import json
import os
import re
import time
import sys
import uuid

import cv2
import numpy as np
import websockets

sys.path.insert(0, ".")

from card_helpers import overs_to_balls, _reconcile_bowler_overs
from eyes.config import CAPTURE_FPS
import trace_emitter as _trace
from eyes.capture.frame_source import FrameSource, make_frame_source
from eyes.config import FRAME_SOURCE as _FRAME_SOURCE_MODE
from eyes.capture.downscale import downscale
from eyes.scoreboard import Scoreboard
from eyes.vision import Vision
from eyes.open_scout import OpenScout, OpenScoutRateGate
from eyes.config import (
    USE_OPEN_SCOUT,
    USE_OPEN_SCOUT_SPANS,
    OPENSCOUT_DECOUPLED,
    OPENSCOUT_DECOUPLED_TARGET_INTERVAL_S,
    OPENSCOUT_TPM_BUDGET,
    USE_V3_CHUNKER,
    USE_V3_CHUNKER_SPANS,
    V3_FALLBACK_ENABLED,
    V3_FALLBACK_LOOKBACK_S,
    V3_FALLBACK_FORWARD_S,
    USE_CONTINUOUS_CHUNKER,
    CONTINUOUS_CHUNKER_MIN_DURATION_S,
    CONTINUOUS_CHUNKER_MAX_DURATION_S,
    CONTINUOUS_CHUNKER_MIN_EVENT_GAP_S,
    CONTINUOUS_CHUNKER_MIN_CONFIDENCE,
)
from eyes.latest_frame_slot import LatestFrameSlot
from eyes.openscout_loop import openscout_loop
from eyes.match_recorder import match_recorder
from eyes.config import RECORD_FULL_MATCH, RECORD_FULL_MATCH_FPS
from eyes.tpm_budget import TPMBudget
from eyes.agent import Extractor
from eyes.match_state import MatchStateAgent
from eyes.squad_scraper import (
    scrape_cricbuzz_squads, squads_to_pipeline_format,
    build_name_lookup, format_squad_roles,
)
from eyes.player_enrichment import (
    enrich_squad_styles, enrich_squad_styles_pass2_async,
    build_styles_lookup,
)
from eyes.cricket_logger import CricketLogger, set_global_frame
from eyes.field.field_state import FieldState
from eyes.field.field_detector import FieldDetector
from eyes.field.field_changes import FieldChangeDetector
from eyes.field.field_merger import FieldMerger
from eyes.field.field_validator import FieldValidator
from eyes.field.cricket_field import CricketField, get_bowler_type
from eyes.invariants import CricketChecker
from eyes.consistent_tracker import ConsistentReadTracker
from eyes.this_over import ThisOverManager
from eyes.commentary import (
    BallEventDetector, PartnershipTracker,
    get_match_situation,
    get_spell_analysis, get_batter_phase,
)
from commentary.personalities import PERSONALITIES
from commentary.context_builder import ContextBuilder
from commentary.moment_detector import MomentDetector
from ball_analyzer import BallAnalyzer
from score_manager import ScoreManager, FrameInput, ABSORBED_LEGAL

from scorer_decision_schema import (
    BATTERS_INVARIANT_AUTOCORRECT,
    SCORER_SCHEMA_ENFORCE,
    finalize_schema_shadow_logs,
    process_scorer_decision_schema,
)

# ---------------------------------------------------------------------------
# State Recovery Phase 2 — mutation is STAGED only.  Keep False until Phase 1
# production telemetry validates triggers (no false positives across innings
# breaks / cold-start).  Enabling is a single-line change here after review.
# ---------------------------------------------------------------------------
STATE_RECOVERY_PHASE_2_ENABLED = False
from wire import format_absorbed_gap_wire, format_wire

# Eagerly resolve Quartz lazy imports before any threads use them
try:
    import Quartz.CoreGraphics as _CG
    _ = _CG.CGWindowListCreateImage
    _ = _CG.CGRectNull
    _ = _CG.kCGWindowListOptionIncludingWindow
    _ = _CG.kCGWindowImageBoundsIgnoreFraming
except (ImportError, AttributeError):
    pass

log = CricketLogger("TEST")
FRAME_WIDTH = 1280
TEST_DURATION = 18000  # 5 hours — full T20 match buffer
WS_PORT = 8765
COMMENTARY_PORT = 8766

# Post-processing: strip fabricated fielding positions from commentary
_FIELDING_STRIP_RE = re.compile(
    r'\b(?:to |at |through |past |towards |behind )?'
    r'(?:point|cover(?:s)?|mid[- ]?on|mid[- ]?off|mid[- ]?wicket|'
    r'square[- ]?leg|fine[- ]?leg|third[- ]?man|long[- ]?on|long[- ]?off|'
    r'deep (?:mid[- ]?wicket|square|fine|cover|point|extra)|'
    r'extra[- ]?cover|backward[- ]?point|forward[- ]?short[- ]?leg|'
    r'silly[- ]?(?:point|mid[- ]?on|mid[- ]?off)|short[- ]?leg|'
    r'leg[- ]?slip|gully|slip(?:s)?|cow[- ]?corner|sweeper|'
    r'backward[- ]?square(?:[- ]?leg)?|long[- ]?leg)\b'
    r'(?:\s*region)?',
    re.IGNORECASE,
)

_PERSONAS_TO_STRIP = {"wire", "storyteller"}

# ── Thread 7 Fix 2: cam=graphic strip-head fast-path (2026-04-30) ──
# Regex-only read — commits score + overs only (design §3.2).
_FAST_PATH_SCORE_DELTA_MAX = 6
_FAST_PATH_BALL_DELTA_MAX = 3
_FAST_PATH_COOLDOWN_MAXLEN = 4
_FAST_PATH_STRIP_HEAD_RE = re.compile(
    r"(?m)^\s*STRIP:\s+(?P<team>[A-Z]{2,4})\s+"
    r"(?P<score>\d+)-(?P<wkts>\d+)\s*\("
    r"(?P<overs>\d+(?:\.\d)?)\)",
)

# N7 — TO_WIN target uses strip-local score when consensus lags.
# See files/docs/investigations/target_detection_off_by_two.md.
_TO_WIN_STRIP_SCORE_RE = re.compile(
    r'\b(\d{1,3})\s*[-/]\s*\d{1,2}\s*\(\s*\d{1,2}\.\d\s*\)'
)


def _to_win_score_basis(upper_desc: str, score_now: int) -> int:
    m = _TO_WIN_STRIP_SCORE_RE.search(upper_desc)
    if m is None:
        return score_now
    strip_score = int(m.group(1))
    return strip_score if strip_score >= score_now else score_now


# P3 — replay/recap-inset detector (Mode-C + N-frame debounce).
# See files/docs/investigations/replay_inset_detection_diagnosis.md.
OVERLAY_WINDOW_FRAMES: int = int(
    os.environ.get("OVERLAY_WINDOW_FRAMES", "5"))
RECAP_INSET_SCORE_DELTA_THRESHOLD: int = int(
    os.environ.get("RECAP_INSET_SCORE_DELTA_THRESHOLD", "10"))
_RECAP_FINGERPRINT_PATTERN = os.environ.get("RECAP_FINGERPRINT_REGEX") or None
_RECAP_FINGERPRINT_RE = (
    re.compile(_RECAP_FINGERPRINT_PATTERN, re.IGNORECASE)
    if _RECAP_FINGERPRINT_PATTERN else None)

SHADOW_FRAME_DECIMATE = int(
    os.environ.get("SHADOW_FRAME_DECIMATE", "1"))


def _fast_path_normalize_overs(overs_raw: str) -> tuple[str, int] | None:
    """Strip-head overs token → ``(\"whole.ball\", total_balls)``.

    Returns ``None`` when fractional balls ≥ 6 (illegal cricket
    notation for team overs).
    """
    s = overs_raw.strip()
    if "." in s:
        ws, rest = s.split(".", 1)
        try:
            ball = int(rest[0]) if rest else 0
        except (ValueError, IndexError):
            return None
        try:
            whole = int(ws)
        except ValueError:
            return None
    else:
        try:
            whole = int(s)
        except ValueError:
            return None
        ball = 0
    if ball >= 6:
        return None
    return f"{whole}.{ball}", whole * 6 + ball


def _fast_path_overs_str_to_balls(overs_str: str | None) -> int:
    """Current ``scoreboard._inn[\"overs\"]`` → cumulative balls."""
    if not overs_str:
        return 0
    norm = _fast_path_normalize_overs(str(overs_str).strip())
    if norm is None:
        try:
            s = str(overs_str).strip()
            if "." in s:
                w, b = s.split(".", 1)
                return int(w) * 6 + int(b[0] if b else 0)
            return int(s) * 6
        except (ValueError, IndexError):
            return 0
    return norm[1]


def _cam_graphic_fast_path(
        *,
        description: str | None,
        cam: str | None,
        has_strip: bool,
        has_overlay_stats: bool,
        batting_team: str | None,
        current_score: int,
        current_overs_str: str | None,
        cooldown: deque,
        resolve_team_variant,
        frame_count: int,
) -> tuple[dict | None, str | None]:
    """Eight-clause AND guard — §15 readiness checklist.

    Returns ``(commit_dict, reject_reason)``. ``commit_dict`` keys:
    ``score`` (int), ``match_overs`` (str). ``reject_reason`` is ``None``
    on accept (caller decides READ vs NOOP via ``Scoreboard.set``).
    """
    def _rej(code: str) -> tuple[dict | None, str]:
        log.info(f"[F{frame_count}] [CAM-GRAPHIC-FAST-PATH-REJECT] "
                 f"reason={code}")
        return None, code

    # G1
    if cam != "graphic":
        return _rej("G1_cam_not_graphic")
    # G2 — Opportunistic: Scout ``has_overlay_stats`` drives primary pass.
    if not has_strip:
        return _rej("G2_no_strip")
    if has_overlay_stats:
        return _rej("G2_overlay_stats")

    m = _FAST_PATH_STRIP_HEAD_RE.search(description or "")
    if not m:
        return _rej("G3_strip_head_no_match")
    try:
        team_abbr = m.group("team")
        score_i = int(m.group("score"))
        wkts_i = int(m.group("wkts"))
        overs_norm = _fast_path_normalize_overs(m.group("overs"))
    except (ValueError, TypeError):
        return _rej("G3_parse_failed")
    if overs_norm is None:
        return _rej("G7_illegal_frac")

    overs_str, balls_new = overs_norm

    # G4 — mid-innings zero template (same spirit as pipeline 0-0 guard).
    if score_i == 0 and wkts_i == 0 and balls_new == 0:
        return _rej("G4_zero_template")

    # G5
    if not batting_team:
        return _rej("G5_no_batting_team")
    resolved = resolve_team_variant(team_abbr)
    if not resolved or resolved != batting_team:
        return _rej("G5_visible_team_mismatch")

    # G6
    if not (current_score <= score_i
            <= current_score + _FAST_PATH_SCORE_DELTA_MAX):
        return _rej("G6_score_window")

    # G7 — ball-units (correct for over-boundary e.g. 2.5→3.0).
    balls_cur = _fast_path_overs_str_to_balls(current_overs_str)
    delta_balls = balls_new - balls_cur
    if not (0 <= delta_balls <= _FAST_PATH_BALL_DELTA_MAX):
        return _rej("G7_balls_window")

    # G8
    if (score_i, overs_str) in cooldown:
        return _rej("G8_cooldown_dup")

    cooldown.append((score_i, overs_str))
    # Parsed wickets ignored — architectural safety thesis §3.3.
    _ = wkts_i
    return {"score": score_i, "match_overs": overs_str}, None


# ── Inline Commentary Generator ────────────────────────────────
from groq import AsyncGroq as _AsyncGroq
from eyes.config import GROQ_API_KEY as _GROQ_KEY


# Types the BED may emit (see eyes/commentary.py) that the commentary
# engine should narrate. Excludes MULTI_BALL (`certain=False` gap-fill
# artifacts from missed frames) and any future-added type we haven't
# explicitly opted in. Err on the side of belt-and-braces: a missing
# commentary is recoverable; a hallucinated commentary on an
# uncertain event is not.
_COMMENTARY_ELIGIBLE_BALL_TYPES: frozenset[str] = frozenset({
    "DOT",
    "FOUR", "SIX",
    "WICKET", "WICKET_LATE",
    "EXTRA",
    "DRS_WIDE", "DRS_NOT_OUT",
    "1_RUNS", "2_RUNS", "3_RUNS", "4_RUNS", "5_RUNS", "6_RUNS", "7_RUNS",
})
# score_manager.ABSORBED_LEGAL (Issue 3 Policy U) deliberately omitted —
# honest absorbed gaps must not drive storyteller without explicit opt-in.


class InlineCommentary:
    """Generates commentary inline within the pipeline loop for logging."""

    def __init__(self):
        self.groq = _AsyncGroq(api_key=_GROQ_KEY)
        self.context = ContextBuilder()
        self.detector = MomentDetector()
        self._prev_state: dict | None = None
        self.clients: set = set()
        self.history: list[dict] = []
        # Telemetry so a silent stall can never repeat. Increment on
        # every caught exception in generate() and log the running
        # total alongside the error message — 1 counter visible in the
        # log line, no external metrics backend needed.
        self._error_count: int = 0
        # Fix 3 telemetry — running tally of gather-level exceptions
        # swallowed by `return_exceptions=True`. Previously invisible.
        self._llm_exc_count: int = 0
        # Fix 1 telemetry — running tally of dicts returned by
        # _call_llm that were shaped as errors (text=="[error: ...]")
        # or empty, which previously survived isinstance(result,dict)
        # and got broadcast as-is or dropped silently at later stages.
        self._llm_invalid_count: int = 0

    @staticmethod
    def _is_commentary_eligible_event(event: dict | None) -> bool:
        """Fix 2 filter — decide whether a BED-authored ball_event
        should drive commentary. Keeps MULTI_BALL (`certain=False`)
        and anything outside the known set from accidentally firing
        wire/storyteller."""
        if not event:
            return False
        if event.get("type") not in _COMMENTARY_ELIGIBLE_BALL_TYPES:
            return False
        # Defensive: reject any listed type that arrived with
        # certain=False (shouldn't happen with current BED but cheap
        # to guard).
        if event.get("certain") is False:
            return False
        return True

    def _detect_ball(self, state: dict) -> dict | None:
        if not self._prev_state:
            return None
        prev_sc = self._prev_state.get("scorecard", {})
        curr_sc = state.get("scorecard", {})
        prev_ov = prev_sc.get("overs")
        curr_ov = curr_sc.get("overs")
        if not prev_ov or not curr_ov or prev_ov == curr_ov:
            return None
        prev_b = self._to_balls(prev_ov)
        curr_b = self._to_balls(curr_ov)
        if curr_b - prev_b != 1:
            return None
        s_d = (curr_sc.get("score") or 0) - (prev_sc.get("score") or 0)
        w_d = (curr_sc.get("wickets") or 0) - (prev_sc.get("wickets") or 0)
        if abs(s_d) > 7 and w_d == 0:
            return None
        if w_d > 0:
            return {"type": "WICKET", "runs": s_d, "over": curr_ov, "certain": True}
        if s_d == 0:
            return {"type": "DOT", "runs": 0, "over": curr_ov, "certain": True}
        if s_d == 4:
            return {"type": "FOUR", "runs": 4, "over": curr_ov, "certain": True}
        if s_d == 6:
            return {"type": "SIX", "runs": 6, "over": curr_ov, "certain": True}
        return {"type": f"{s_d}_RUNS", "runs": s_d, "over": curr_ov, "certain": True}

    def _detect_over_change(self, state: dict) -> dict | None:
        if not self._prev_state:
            return None
        curr = state.get("scorecard", {}).get("overs")
        prev = self._prev_state.get("scorecard", {}).get("overs")
        if not curr or not prev:
            return None
        if int(float(curr)) > int(float(prev)):
            return state.get("over_history", {}).get(str(int(float(prev))), {})
        return None

    @staticmethod
    def _to_balls(overs) -> int:
        o = float(overs or "0")
        return int(o) * 6 + round((o % 1) * 10)

    @staticmethod
    def _allowed_name_set(ws_payload: dict) -> set[str]:
        """S3 allowlist — names commentary may reference for the
        current ball: striker, non, bowler, and the team
        names (and any partial form of those)."""
        out: set[str] = set()
        sc = ws_payload.get("scorecard", {}) or {}
        match = ws_payload.get("match", {}) or {}
        for k in ("striker", "non", "current_bowler",
                  "batting_team", "bowling_team"):
            v = sc.get(k) or match.get(k)
            if isinstance(v, str) and v.strip():
                vl = v.lower().strip()
                out.add(vl)
                for tok in vl.split():
                    if len(tok) >= 3:
                        out.add(tok)
        for k in ("team_a", "team_b"):
            v = match.get(k)
            if isinstance(v, str) and v.strip():
                out.add(v.lower().strip())
                for tok in v.lower().split():
                    if len(tok) >= 3:
                        out.add(tok)
        return out

    @staticmethod
    def _known_player_set(ws_payload: dict) -> set[str]:
        """All player surnames/given-names in either squad. Used to
        spot when commentary references a real player who isn't on
        the field for THIS ball — the canonical S3 hallucination."""
        out: set[str] = set()
        for sq in ("full_batting_squad", "full_bowling_squad"):
            for p in ws_payload.get(sq, []) or []:
                n = (p.get("name") or "").lower().strip()
                if not n:
                    continue
                out.add(n)
                for tok in n.split():
                    if len(tok) >= 3:
                        out.add(tok)
        return out

    def _validate_commentary_names(
            self, text: str, ws_payload: dict) -> list[str]:
        """Return list of foreign player names found in `text`.
        Empty list = clean. Caller decides whether to drop, regen,
        or just log."""
        if not text:
            return []
        allowed = self._allowed_name_set(ws_payload)
        known = self._known_player_set(ws_payload)
        if not known:
            return []
        # Capitalised tokens (heuristic for proper nouns)
        toks = set(re.findall(r"\b[A-Z][a-zA-Z']{2,}\b", text))
        foreign: list[str] = []
        for tok in toks:
            tl = tok.lower()
            if tl in known and tl not in allowed:
                foreign.append(tok)
        return foreign

    async def generate(
            self, ws_payload: dict,
            ball_event_hint: dict | None = None) -> dict[str, dict]:
        """Generate commentary for all triggered personas. Returns {name: {text, latency_ms}}.

        `ball_event_hint` (Fix 2): when supplied by the caller, this
        authoritative BED-derived event is used instead of InlineCommentary's
        narrower `_detect_ball` (which required overs to advance by exactly
        1 legal ball and therefore silently skipped every wide / no-ball —
        Mode B of the 2026-04-24 investigation). When None, the previous
        self-detection path is preserved so any legacy caller keeps working
        without a signature update.
        """
        # Single try/finally wraps the entire body so _prev_state is
        # ALWAYS advanced, even on exception. Previously the success
        # path was the only place prev_state advanced; a NameError in
        # format_for_prompt caused the detector to re-fire the same
        # ball_event on every subsequent frame, crash again, and never
        # advance — permanent commentary blackout after one bug.
        try:
            return await self._generate_inner(ws_payload, ball_event_hint)
        except Exception as e:
            self._error_count += 1
            log.error(
                f"  [COMM] Error (#{self._error_count}): {e}",
                exc_info=True)
            return {}
        finally:
            self._prev_state = ws_payload

    async def _generate_inner(
            self, ws_payload: dict,
            ball_event_hint: dict | None = None) -> dict[str, dict]:
        # Fix 2: prefer the authoritative BED-produced event. Run the
        # eligibility filter on it so MULTI_BALL (certain=False) and
        # any unknown future type doesn't accidentally drive wire/
        # storyteller. Fall back to self-detection only when the
        # caller supplied no hint — preserves legacy behaviour.
        if ball_event_hint is not None:
            ball_event = (
                ball_event_hint
                if self._is_commentary_eligible_event(ball_event_hint)
                else None)
        else:
            ball_event = self._detect_ball(ws_payload)

        over_change = self._detect_over_change(ws_payload)

        if not ball_event and not over_change:
            return {}

        triggers = self.detector.classify(ws_payload, ball_event, over_change)
        if not triggers:
            return {}

        if ball_event:
            ctx = self.context.build_ball_context(ws_payload, ball_event)
        elif over_change:
            ctx = self.context.build_over_context(ws_payload, over_change)
        else:
            ctx = self.context.build_ball_context(ws_payload, {"type": "UPDATE"})

        di = ws_payload.get("delivery_info")
        if di:
            ctx["delivery_length"] = di.get("length")
            ctx["delivery_line"] = di.get("line")
            ctx["delivery_angle"] = di.get("bowling_angle")
            ctx["delivery_shot_type"] = di.get("shot_type")
            dir_info = di.get("shot_direction")
            if dir_info and isinstance(dir_info, dict):
                ctx["delivery_shot_direction"] = dir_info.get("side")
            ctx["delivery_shot_elevation"] = di.get("shot_elevation")

        if ws_payload.get("speed_kph"):
            ctx["speed_kph"] = ws_payload["speed_kph"]

        prompt_text = self.context.format_for_prompt(ctx)

        results: dict[str, dict] = {}
        tasks = {}
        for name in triggers:
            if (name == "wire"
                    and ws_payload.get("_wire_override")):
                _wo = {"text": ws_payload["_wire_override"],
                       "latency_ms": 0}
                results["wire"] = _wo
                self.context.recent_commentary.append(_wo["text"][:100])
                _wo_entry = {
                    "persona": "wire",
                    "text": _wo["text"],
                    "timestamp": time.time(),
                    "over": ws_payload.get("scorecard", {}).get("overs", "?"),
                    "score": (
                        f"{ws_payload.get('scorecard', {}).get('score', 0)}/"
                        f"{ws_payload.get('scorecard', {}).get('wickets', 0)}"
                    ),
                    "latency_ms": 0,
                }
                self.history.append(_wo_entry)
                await self._broadcast(_wo_entry)
                continue
            persona = PERSONALITIES[name]
            tasks[name] = self._call_llm(name, persona, prompt_text)

        gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for name, result in zip(tasks.keys(), gathered):
            # Fix 3 — surface gather-level exceptions instead of
            # silently dropping them via the isinstance() filter.
            # Mode A of the 2026-04-24 investigation was
            # indistinguishable in logs from "no ball event" because
            # both tasks raised on cold-start Groq calls and both
            # exceptions vanished here. Now each is logged with task
            # name and exception type for post-deploy triage.
            if isinstance(result, Exception):
                self._llm_exc_count += 1
                try:
                    log.warning(
                        f"  [COMM-LLM-EXC] {name} raised "
                        f"(#{self._llm_exc_count}): "
                        f"{type(result).__name__}: {result}")
                except Exception:
                    pass
                continue
            if not isinstance(result, dict):
                try:
                    log.warning(
                        f"  [COMM-LLM-BAD] {name} returned non-dict "
                        f"({type(result).__name__})")
                except Exception:
                    pass
                continue

            # Fix 1 — flag error-shaped / empty dicts returned by
            # _call_llm so Groq failures are attributable without
            # requiring source-level instrumentation. Together with
            # Fix 3 this covers every failure mode between "task
            # invoked" and "result accepted into payload".
            _text = (result.get("text") or "").strip()
            if _text.startswith("[error:") or not _text:
                self._llm_invalid_count += 1
                try:
                    log.warning(
                        f"  [COMM-LLM-INVALID] {name} produced "
                        f"error-shaped or empty text "
                        f"(#{self._llm_invalid_count}): "
                        f"text={_text[:120]!r}")
                except Exception:
                    pass
                continue

            if isinstance(result, dict):
                # S3 safety net: drop generations that name a player
                # who isn't actually on the field for this ball.
                # Real fix is correct context; this catches the rest.
                _foreign = self._validate_commentary_names(
                    result.get("text", ""), ws_payload)
                if _foreign:
                    try:
                        log.warning(
                            f"  [COMM-ALLOWLIST] {name} dropped: "
                            f"foreign names {_foreign} | "
                            f"text={result.get('text', '')[:120]!r}")
                    except Exception:
                        pass
                    # Don't broadcast a hallucinated line. Let the
                    # next ball's commentary be the user-visible
                    # output for this persona.
                    continue
                results[name] = result
                self.context.recent_commentary.append(result["text"][:100])
                entry = {
                    "persona": name,
                    "text": result["text"],
                    "timestamp": time.time(),
                    "over": ws_payload.get("scorecard", {}).get("overs", "?"),
                    "score": (
                        f"{ws_payload.get('scorecard', {}).get('score', 0)}/"
                        f"{ws_payload.get('scorecard', {}).get('wickets', 0)}"),
                    "latency_ms": result["latency_ms"],
                }
                self.history.append(entry)
                await self._broadcast(entry)

        return results

    async def _call_llm(self, name: str, persona: dict,
                        prompt_text: str) -> dict:
        config = persona["config"]
        t0 = time.time()
        try:
            response = await self.groq.chat.completions.create(
                model=config["model"],
                temperature=config["temperature"],
                max_tokens=config["max_tokens"],
                messages=[
                    {"role": "system", "content": persona["system"]},
                    {"role": "user", "content": prompt_text},
                ],
            )
            text = response.choices[0].message.content.strip()
            if name in _PERSONAS_TO_STRIP:
                text = _FIELDING_STRIP_RE.sub('', text)
                text = re.sub(r'\s{2,}', ' ', text).strip()
            ms = int((time.time() - t0) * 1000)
            return {"text": text, "latency_ms": ms}
        except Exception as e:
            ms = int((time.time() - t0) * 1000)
            return {"text": f"[error: {e}]", "latency_ms": ms}

    async def _broadcast(self, entry: dict):
        import json as _json
        payload = _json.dumps({"type": "commentary", "entry": entry})
        dead = []
        for client in self.clients:
            try:
                await client.send(payload)
            except Exception:
                dead.append(client)
        for c in dead:
            self.clients.discard(c)


# ── S1 monitoring: log every write to scoreboard._inn["striker"]
#    or ["non"] from outside scoreboard.py. With SM as the
#    sole UI authority, ANY external write here is suspicious — most
#    are legacy paths that should have been removed during cutover.
#    Their captured caller frames let us delete them one by one.
_STRIKER_KEYS = ("striker", "non")


class _StrikerLoggingDict(dict):
    """Drop-in dict that logs writes to striker/non keys."""

    def __setitem__(self, key, value):
        if key in _STRIKER_KEYS:
            old = self.get(key)
            if old != value:
                import inspect as _insp
                caller = "?"
                stk = _insp.stack()
                for fr in stk[1:8]:
                    fn = os.path.basename(fr.filename or "")
                    # Skip scoreboard.py internals — those writes are
                    # legitimate (Scoreboard owns its dict). We only
                    # want to surface external writers.
                    if fn == "scoreboard.py" or not fn:
                        continue
                    if fr.function == "__setitem__":
                        continue
                    caller = (f"{fn}:{fr.lineno} "
                              f"({fr.function})")
                    break
                try:
                    log.info(
                        f"  [STRIKER-WRITE] {caller}: "
                        f"{key} {old}->{value}")
                except Exception:
                    pass
        super().__setitem__(key, value)


def _wrap_innings_dicts(_sb):
    """Replace each non-wrapped innings dict with a logging variant.

    Idempotent — safe to call after every setup_innings/set_innings_2.
    """
    try:
        for _k, _d in list(_sb.innings.items()):
            if isinstance(_d, _StrikerLoggingDict):
                continue
            _sb.innings[_k] = _StrikerLoggingDict(_d)
    except Exception:
        pass


# ── WebSocket broadcast ────────────────────────────────────────
_ws_clients: set = set()

# Per-client send timeout. Without this, one slow client (network
# congestion, paused tab) hangs broadcast_state and starves the event
# loop's ability to accept new handshakes — which is exactly what the
# parity monitor was hitting ("timed out during opening handshake").
_WS_SEND_TIMEOUT_S = 0.75

# Fix 17 Path D (cold-start WS broadcast gate, 2026-04-26):
# don't push state to WS clients until first committed cold-start
# consensus completes (batting_team set AND non-zero score
# committed).  Closes the F6→F104 bad-UX window where the UI
# showed `LSG 0/0` for ~3 minutes despite the broadcast clearly
# showing `KKR 28/3`.  After the gate opens, all subsequent
# frames pass through unchanged.  Safety timeout: 90s wallclock
# (matches POISON-STREAK release threshold) so the UI never
# hangs indefinitely if cold-start consensus fails to converge
# (e.g. a never-actually-started match).
_ws_cold_start_gate_open: bool = False
_ws_cold_start_gate_first_attempt_ts: float | None = None
_WS_COLD_START_GATE_TIMEOUT_S: float = 90.0


def _ws_cold_start_gate_check(payload: dict) -> bool:
    """Return True if the WS broadcast should be allowed through.

    Gate-open conditions (any one suffices):
      (a) `batting_team` set on payload (cold-start has resolved
          *which* team is batting; suppressing further would
          block legitimate zero-state windows like innings-2
          first ball and between-over pauses).
      (b) Safety timeout (90s since first broadcast attempt) —
          ensures the UI never hangs even if team detection
          fails to converge.
      (c) Already-open: once opened, the gate stays open for the
          rest of the session.

    Hotfix 2026-04-26: original `_team and _score_i >= 1`
    requirement was too strict and held the gate closed for the
    full 90s timeout on every restart that came up during a
    legitimate zero-score window (innings-2 first ball, mid-
    match restart catching a between-overs graphic, etc.).
    """
    global _ws_cold_start_gate_open
    global _ws_cold_start_gate_first_attempt_ts
    if _ws_cold_start_gate_open:
        return True
    _now = time.time()
    if _ws_cold_start_gate_first_attempt_ts is None:
        _ws_cold_start_gate_first_attempt_ts = _now
    # Canonical payload places score/batting_team under
    # `payload["scorecard"]`, but a few legacy callsites broadcast a
    # flat shape during cold-start.  Accept both.
    _scorecard = payload.get("scorecard") or {}
    _team = (payload.get("batting_team")
             or _scorecard.get("batting_team"))
    _score = (payload.get("score")
              if payload.get("score") is not None
              else _scorecard.get("score"))
    try:
        _score_i = int(_score) if _score is not None else 0
    except (ValueError, TypeError):
        _score_i = 0
    # Hotfix 2026-04-26: the gate's primary job is to prevent
    # broadcasting state with wrong/unknown team during cold-start.
    # Once `batting_team` is committed (typically within 1-2
    # frames), we should no longer suppress — even if score hasn't
    # yet surfaced (mid-innings restart, between-overs, DRS pause,
    # etc.).  Earlier `_team and _score_i >= 1` requirement also
    # blocked broadcasts during legitimate score=0 windows
    # (innings-2 first ball, mid-match restart) and caused 90s of
    # dead UI on every restart.
    if _team:
        _ws_cold_start_gate_open = True
        log.info(
            f"[WS-COLD-START-GATE] OPEN — batting_team committed "
            f"(team={_team!r} score={_score_i}).  All subsequent "
            f"WS broadcasts pass through (Fix 17 Path D).")
        return True
    _elapsed = _now - _ws_cold_start_gate_first_attempt_ts
    if _elapsed > _WS_COLD_START_GATE_TIMEOUT_S:
        _ws_cold_start_gate_open = True
        log.warn(
            f"[WS-COLD-START-GATE] OPEN (timeout) — "
            f"{_elapsed:.0f}s elapsed since first broadcast "
            f"attempt without first committed non-zero state.  "
            f"Releasing gate to avoid UI hang (Fix 17 Path D).")
        return True
    return False


async def _ws_handler(websocket):
    _ws_clients.add(websocket)
    log.info(f"[WS] client connected ({len(_ws_clients)} total)")
    try:
        async for _ in websocket:
            pass
    except Exception:
        pass
    finally:
        _ws_clients.discard(websocket)
        log.info(f"[WS] client disconnected ({len(_ws_clients)} remain)")


def _json_default(obj):
    if isinstance(obj, set):
        return list(obj)
    return str(obj)


async def _send_with_timeout(client, data: str):
    try:
        await asyncio.wait_for(client.send(data),
                               timeout=_WS_SEND_TIMEOUT_S)
        return None
    except (asyncio.TimeoutError, Exception) as e:
        return (client, e)


async def broadcast_state(payload: dict):
    if not _ws_clients:
        return
    if not _ws_cold_start_gate_check(payload):
        return  # gate closed; suppress emission during cold-start
    # Trace mirror update — Trace-and-Detect v1: reflect post-deepMerge
    # state on the (hypothetical) client. Update sits *after* both
    # gate + client-presence guards so the mirror represents what a
    # connected UI actually sees.
    try:
        _TRACE_MIRROR.apply(payload)
    except Exception:
        pass
    data = json.dumps(payload, default=_json_default)
    clients = list(_ws_clients)
    results = await asyncio.gather(
        *[_send_with_timeout(c, data) for c in clients],
        return_exceptions=True,
    )
    for r in results:
        if isinstance(r, tuple):
            client, _err = r
            _ws_clients.discard(client)
            try:
                await client.close()
            except Exception:
                pass
# D9 fix (2026-05-10): squad URL is parametrized via CRICBUZZ_MATCH_ID
# env var or `--match-id <id>` CLI arg. Env wins over arg; both fall
# back to the last-known-good default with a WARN log so an out-of-date
# constant doesn't silently scrape the wrong squad list.
DEFAULT_MATCH_ID = "152075"
DEFAULT_MATCH_SLUG = "rr-vs-gt-52nd-match-indian-premier-league-2026"


def _resolve_match_id() -> tuple[str, str]:
    """Returns (match_id, source_label). Env > CLI > default."""
    env_id = os.environ.get("CRICBUZZ_MATCH_ID")
    if env_id:
        return env_id, "env:CRICBUZZ_MATCH_ID"
    argv_id = None
    argv = list(sys.argv) if hasattr(sys, "argv") else []
    for i, tok in enumerate(argv):
        if tok == "--match-id" and i + 1 < len(argv):
            argv_id = argv[i + 1]
            break
        if tok.startswith("--match-id="):
            argv_id = tok.split("=", 1)[1]
            break
    if argv_id:
        return argv_id, "arg:--match-id"
    return DEFAULT_MATCH_ID, "default"


def _build_squad_url() -> str:
    mid, source = _resolve_match_id()
    if source == "default":
        log.warn(
            f"[CONFIG] CRICBUZZ_MATCH_ID not set, falling back to "
            f"default {DEFAULT_MATCH_ID}")
    slug = os.environ.get("CRICBUZZ_MATCH_SLUG", DEFAULT_MATCH_SLUG)
    if slug == DEFAULT_MATCH_SLUG and source != "default":
        log.warn(
            f"[CONFIG] CRICBUZZ_MATCH_SLUG not set; using stale default "
            f"slug '{slug}'. Cricbuzz returns content keyed to the slug — "
            f"set CRICBUZZ_MATCH_SLUG to today's slug.")
    return (f"https://www.cricbuzz.com/cricket-match-squads/"
            f"{mid}/{slug}")


SQUAD_URL = _build_squad_url()
_env_sid = os.environ.get("BMF_SESSION_ID", "").strip()
SESSION_ID = _env_sid if _env_sid else uuid.uuid4().hex[:8]
os.environ["BMF_SESSION_ID"] = SESSION_ID

# Trace-and-Detect v1 wiring (see files/docs/operations/trace_and_detect_setup.md).
_TRACE_RECORDER = _trace.get_recorder()
_TRACE_HANDLER = _trace.install_log_handler()
_TRACE_WRITER = _trace.get_writer(SESSION_ID)
_TRACE_MIRROR = _trace.get_mirror()

# Shadow v3 delivery detector (env-gated). Non-blocking side-channel
# off OpenScout's result_sink. Logs decisions to
# files/logs/deliveries/<session>/live_decision_log.jsonl.
try:
    from eyes import shadow_delivery_detector as _shadow_dd
    from pathlib import Path as _Path_sdd
    _shadow_delivery_log_dir = _Path_sdd(__file__).resolve().parent / \
        "logs" / "deliveries" / f"shadow_{SESSION_ID}"
    _shadow_delivery_detector = _shadow_dd.maybe_create(
        SESSION_ID, _shadow_delivery_log_dir)
except Exception:  # noqa: BLE001
    log.exception("[SHADOW-DELIVERY] init failed; disabled")
    _shadow_delivery_detector = None

from monitoring_emitters import (
    SessionConfigInputs as _SessionConfigInputs,
    format_session_config as _format_session_config,
)
log.info(_format_session_config(_SessionConfigInputs(
    session_id=SESSION_ID,
    use_v3_chunker=USE_V3_CHUNKER,
    use_v3_chunker_spans=USE_V3_CHUNKER_SPANS,
    v3_fallback_enabled=V3_FALLBACK_ENABLED,
    v3_fallback_lookback_s=V3_FALLBACK_LOOKBACK_S,
    v3_fallback_forward_s=V3_FALLBACK_FORWARD_S,
    openscout_decoupled=OPENSCOUT_DECOUPLED,
    openscout_target_s=OPENSCOUT_DECOUPLED_TARGET_INTERVAL_S,
    openscout_tpm_budget=OPENSCOUT_TPM_BUDGET,
    use_open_scout=USE_OPEN_SCOUT,
    use_open_scout_spans=USE_OPEN_SCOUT_SPANS,
)))
if OPENSCOUT_DECOUPLED:
    log.warn(
        f"[CONFIG] OPENSCOUT_DECOUPLED=1 (new default 2026-05-11). "
        f"Decoupled loop runs at OPENSCOUT_DECOUPLED_TARGET_INTERVAL_S="
        f"{OPENSCOUT_DECOUPLED_TARGET_INTERVAL_S:.2f}s. Watch first "
        f"5 min for [OPEN-SCOUT-LOOP] cadence anomalies. Set "
        f"OPENSCOUT_DECOUPLED=0 to revert.")
_TRACE_LAST_HANDOFF_FRAME: int | None = None
_TRACE_LAST_INNINGS: int | None = None

# Live-monitoring v1 (2026-05-05).  Tracks tag emission cadence so
# the main loop can fire 5-minute snapshots without race conditions.
# See files/monitoring_emitters.py.
_MONITORING_LAST_5MIN_EMIT_TS: float = 0.0
_MONITORING_RETRO_EMITTED_INNINGS: set[int] = set()
_MONITORING_MATCH_START_TS: float = 0.0
# Snapshot of cumulative DWR RetroCounters captured at innings-1 end
# so the innings-2 summary can be derived as (current - snapshot).
_MONITORING_RETRO_INN1_SNAPSHOT: dict[str, int] = {
    "events_seen": 0, "spans_committed": 0, "spans_fallback": 0}


def frame_changed(current: np.ndarray, previous: np.ndarray | None,
                  threshold: float = 0.05) -> bool:
    if previous is None:
        return True
    if current.shape != previous.shape:
        return True
    diff = np.mean(np.abs(current.astype(float) - previous.astype(float)))
    return diff > (255 * threshold)


def _strip_has_scoreboard(strip: np.ndarray) -> bool:
    """Quick local check: does the bottom strip look like it has a
    scoreboard? Scoreboard strips have high-contrast text on a solid
    bar. Full-screen ads don't have this pattern at the very bottom."""
    if strip is None or strip.size == 0:
        return False
    gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY) if len(strip.shape) == 3 else strip
    std = float(np.std(gray))
    # Scoreboard bars: solid background + bright text → std 25-80
    # Full-screen ads: varied content all the way down → std > 40 OR < 10
    # We check: if the strip has moderate contrast typical of a
    # scoreboard bar, the frame likely still has cricket info.
    return 15.0 < std < 85.0


def _strip_has_text_band(strip: np.ndarray) -> bool:
    """Pre-Scout gate: does the bottom strip contain a broadcast
    scoreboard text bar?

    Scoreboard bars have high-contrast text (white/bright glyphs on
    a solid dark band) which produces strong **horizontal luminance
    gradients** from the vertical strokes of each character.
    Closeup shots of faces/uniforms, crowd, grass, or fade-outs lack
    this text-like signature.

    Calibrated on the 2026-04-21 SRH-vs-DC live session (n=210 scout
    frames, 28 FRAME_POISONED):
      - valid scoreboards  : grad_mean = 11.6 ± 3.4
      - poisoned closeups  : grad_mean =  3.7 ± 3.5
      - advertisements     : grad_mean =  3.8 ± 2.7

    A single-metric gate of ``grad_mean >= 6.0`` skips ~84% of
    poisoned frames and ~67% of full-screen ads while keeping ~91%
    of valid strips.  The main loop wraps this with a force-through
    safety valve so the ~9% false-skip rate cannot starve the
    pipeline if the heuristic is wrong on an unusual broadcast
    graphic.
    """
    if strip is None or strip.size == 0:
        return False
    gray = (cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
            if len(strip.shape) == 3 else strip)
    std = float(np.std(gray))
    # Near-uniform regions (blank fade, pure sky) can never be a strip.
    if std < 10.0:
        return False
    # Primary signal: horizontal gradient density from text glyphs.
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_mean = float(np.mean(np.abs(gx)))
    return grad_mean >= 6.0


class AdaptiveSleep:
    """Event-driven sleep with burst mode at X.5 overs.

    Normal: 1s between frames during play, 25s during over-break ads.
    Burst:  0s (back-to-back) for ~8s after the 5th ball of an over,
            maximising the chance of reading the score before ads cut in.

    Active-play burst (Phase 2, 2026-04-18): when Scout's last frame
    was tagged ``camera_view == "bowlers_end"`` (or ``side_on``), the
    broadcast is showing live cricket — drop the cadence to ~0.5s so
    we densely populate BallAnalyzer's tagged buffer with delivery
    frames.  When Scout tags a dead-time view (replay/graphic/ad/
    closeup) we relax the cadence up to ~2.5s.

    Phase-driven cadence (Phase 3, 2026-04-19): Scout's prompt now
    also returns ``frame_phase`` (release / flight / shot / post_shot
    / runup / between_play / ...).  Phases have very different
    information density: release/flight/shot are 1-2 s windows that
    contain ALL the classification data; runup is a 3-5 s walk that
    changes nothing frame-to-frame.  When ``frame_phase`` is set we
    use a per-phase interval map instead of the single 0.5 s active-
    play bucket.  Camera-view logic stays as the fallback for back-
    compat (frames recorded before the phase prompt rolled out have
    phase=None).
    """

    BURST_DURATION = 8.0

    # Active-play cadences (seconds between Scout calls).
    ACTIVE_PLAY_INTERVAL = 0.5    # bowlers_end / side_on
    DEAD_TIME_INTERVAL = 2.5      # replay / graphic / ad / other
    DEFAULT_INTERVAL = 1.0        # closeup / unknown — middle ground

    _ACTIVE_PLAY_VIEWS = ("bowlers_end", "side_on")
    _DEAD_TIME_VIEWS = ("replay", "graphic", "ad", "other")

    # Phase-driven cadence map.  Scout's reported `frame_phase`
    # selects the next-frame interval directly.
    #   * release/flight/shot @ 0.4 s — max burst, the 2-second
    #     window where length/line/shot data lives.  Scout's avg
    #     response is ~800 ms, so the effective rate is ~1 call/s
    #     (Path A from the 2026-04-19 design notes).  If frame
    #     density turns out to be insufficient we'll pipeline Scout
    #     calls during bursts (Path B).
    #   * post_shot @ 0.6 s — fielder reaction is useful for shot
    #     direction / boundary calls.
    #   * fielder_reaction @ 0.8 s — trajectory confirmation.
    #   * runup @ 1.5 s — bowler walking, nothing changes.
    #   * between_play @ 2.0 s — dead time.
    #   * replay/graphic @ 3.0 s — broadcast intermission.
    #   * advertisement @ 8.0 s — long quiet wait for end.
    PHASE_FREQUENCY: dict[str, float] = {
        "runup":            1.5,
        "release":          0.4,
        "flight":           0.4,
        "shot":             0.4,
        "post_shot":        0.6,
        "fielder_reaction": 0.8,
        "between_play":     2.0,
        "replay":           3.0,
        "graphic":          3.0,
        "advertisement":    8.0,
        "other":            2.0,
    }

    def __init__(self):
        self.over_complete = False
        self.ad_detected = False
        self._burst_until: float = 0.0
        # Last Scout camera_view tag — drives active-play cadence.
        self.last_camera_view: str | None = None
        # Last Scout frame_phase tag — drives per-phase cadence
        # (Phase 3, 2026-04-19) when present.
        self.last_frame_phase: str | None = None
        # Post-active-play "tail" window: the broadcast routinely
        # cuts away the moment the bowler releases (closeup of
        # the bowler, replay of the shot, crowd reaction) so the
        # next 1-3 frames after a `bowlers_end` are tagged dead-
        # time. Without this tail we relax the cadence to 2.5s
        # immediately, missing the short window when the strip
        # ticks to the new overs.  Holding 0.5s polling for ~5s
        # past every active-play frame catches the dot-ball strip
        # update without ballooning Groq spend (the tail expires
        # when the broadcast settles into a true ad / replay).
        self._active_tail_until: float = 0.0
        self.ACTIVE_TAIL_HOLD = 5.0  # seconds

    def on_over_change(self):
        self.over_complete = True

    def on_ball_5(self):
        """Start burst when the scoreboard shows ball 5 of the over."""
        self._burst_until = time.time() + self.BURST_DURATION
        log.info("[SLEEP] Burst mode ON — last ball of over")

    def check_burst(self, overs: float | None):
        """Called each scored frame. Triggers burst at X.5 if not already."""
        if overs is None:
            return
        ball = round((overs % 1) * 10)
        if ball == 5 and time.time() < self._burst_until:
            return
        if ball == 5:
            self.on_ball_5()

    @property
    def in_burst(self) -> bool:
        return time.time() < self._burst_until

    def on_ad_detected(self, frame: np.ndarray | None = None):
        """Trigger ad detection. If an over just completed AND the
        bottom strip doesn't look like a scoreboard, sleep long."""
        if self.in_burst:
            return
        if not self.over_complete or self.ad_detected:
            return
        if frame is not None:
            h = frame.shape[0]
            strip = frame[int(h * 0.88):, :]
            if _strip_has_scoreboard(strip):
                log.info("[SLEEP] Ad tagged but scoreboard strip "
                         "still visible — staying at 1s")
                return
        self.ad_detected = True
        log.info("[SLEEP] Over complete + full-screen ad → sleeping 25s")

    def on_scorecard_frame(self):
        self.over_complete = False
        self.ad_detected = False

    def on_camera_view(self, view: str | None) -> None:
        """Record Scout's latest camera_view; drives the next sleep."""
        self.last_camera_view = view
        # Extend the active-tail window every time we see a live
        # cricket frame.  This keeps cadence tight through the
        # 1-3 frame dead-time blip that follows almost every ball.
        if view in self._ACTIVE_PLAY_VIEWS:
            self._active_tail_until = (
                time.time() + self.ACTIVE_TAIL_HOLD)

    def on_frame_phase(self, phase: str | None) -> None:
        """Record Scout's latest frame_phase; drives per-phase cadence.

        Action phases (release/flight/shot/post_shot) also extend the
        active-tail window so a late-cycle cut-away (closeup, replay)
        doesn't immediately drop us back to dead-time cadence and miss
        the strip tick to the new score.
        """
        self.last_frame_phase = phase
        if phase in ("release", "flight", "shot", "post_shot"):
            self._active_tail_until = (
                time.time() + self.ACTIVE_TAIL_HOLD)

    def get_sleep_time(self) -> float:
        # Over-end burst always wins (last-ball-of-over coverage).
        if self.in_burst:
            return 0.0
        if self.ad_detected:
            self.ad_detected = False
            self.over_complete = False
            return 25.0
        # Phase-driven cadence (Phase 3, 2026-04-19): when Scout has
        # tagged the last frame with a frame_phase, that tag is the
        # most informative signal we have — use the phase map
        # directly.  Falls through to camera_view logic when phase
        # is missing (frames recorded before the phase prompt).
        if self.last_frame_phase is not None:
            interval = self.PHASE_FREQUENCY.get(
                self.last_frame_phase)
            if interval is not None:
                return interval
        # ── back-compat: camera_view-driven cadence ──────────────
        # Active-play burst: Scout tagged the last frame as live
        # cricket → densely sample so the tagged buffer has enough
        # bowlers_end frames at the moment of delivery detection.
        if self.last_camera_view in self._ACTIVE_PLAY_VIEWS:
            return self.ACTIVE_PLAY_INTERVAL
        # Active-play tail: we just saw live cricket within the
        # last ACTIVE_TAIL_HOLD seconds.  Stay fast — a dot ball's
        # broadcast cut-away (closeup of the bowler walking back,
        # replay of the shot) lasts ~3-5s before the strip
        # repaints with the new overs.  Polling at 0.5s through
        # this window means we catch the strip tick within ~1s
        # of it appearing instead of waiting 2.5s.
        if time.time() < self._active_tail_until:
            return self.ACTIVE_PLAY_INTERVAL
        if self.last_camera_view in self._DEAD_TIME_VIEWS:
            return self.DEAD_TIME_INTERVAL
        return self.DEFAULT_INTERVAL


_PLACEHOLDER_EXACT = {
    "UNNAMED", "UNKNOWN", "NULL", "NONE", "N/A",
    "NOT_VISIBLE", "NOT_SHOWN", "NAME", "PLAYER", "BATTER", "BOWLER",
}


def _safe_int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _sanitize_vision_hint_names(hint: str | None, scoreboard) -> str | None:
    if not hint:
        return hint
    surnames: set[str] = set()
    for card_attr in ("batting_card", "bowling_card"):
        card = getattr(scoreboard, card_attr, None) or {}
        for full in card:
            parts = (full or "").strip().split()
            if parts:
                surnames.add(parts[-1].upper())
    if not surnames:
        return hint

    def _split_alpha(s: str) -> tuple[str, str]:
        m = re.match(r"^([A-Za-z]+)(.*)$", s)
        return (m.group(1), m.group(2)) if m else ("", s)

    tokens = hint.split(" ")
    out: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        head, tail = _split_alpha(tok)
        upper_head = head.upper()
        if (head and head == head.upper() and not tail
                and upper_head not in surnames and i + 1 < n):
            head2, tail2 = _split_alpha(tokens[i + 1])
            if head2 and head2 == head2.upper():
                merged = upper_head + head2.upper()
                if merged in surnames:
                    out.append(merged + tail2)
                    i += 2
                    continue
        if (len(head) == 1 and head == head.upper() and not tail
                and i + 1 < n):
            head2, _ = _split_alpha(tokens[i + 1])
            if head2 and head2.upper() in surnames:
                i += 1
                continue
        out.append(tok)
        i += 1
    return " ".join(out)


def _align_extractor_batters_for_sm(
        ext_batters: list[dict[str, Any]],
        *,
        scoreboard,
        score_mgr,
        log,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Map extractor rows → (bat1_row, bat2_row) for FrameInput.

    Warm path aligns bat1=striker bat2=non when confident; preserves
    legacy strip ordering on cold striker or unresolved OCR rows.
    """

    def _strip_sentinel_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return row if row.get("name") else None

    def _row_matches_canonical(
            row: dict[str, Any],
            canonical: str | None,
    ) -> bool:
        if not canonical:
            return False
        raw = (row.get("name") or "").strip()
        if not raw:
            return False
        try:
            resolved = scoreboard.resolve_name(raw)
        except Exception:
            resolved = None
        if resolved == canonical:
            return True
        if resolved and score_mgr._same_name(resolved, canonical):
            return True
        return score_mgr._same_name(raw, canonical)

    xs = list(ext_batters or [])
    if len(xs) > 2:
        log.info(
            "  [BATTER-ALIGN] ext_batters "
            f"len={len(xs)} — scanning all rows for striker/non match")

    striker_ref = (score_mgr.striker or "").strip() or None
    non_ref = (score_mgr.non or "").strip() or None

    # CASE 3 — single-row extractor output
    if len(xs) == 1:
        only = xs[0]
        if striker_ref and _row_matches_canonical(only, striker_ref):
            return _strip_sentinel_row(only), None
        if non_ref and _row_matches_canonical(only, non_ref):
            return None, _strip_sentinel_row(only)
        return _strip_sentinel_row(only), None

    if len(xs) == 0:
        return None, None

    # CASE 2 — cold striker unknown → preserve legacy strip order
    if not striker_ref:
        return _strip_sentinel_row(xs[0]), (
            _strip_sentinel_row(xs[1]) if len(xs) >= 2 else None)

    striker_row = None
    striker_idx = None
    for _i, row in enumerate(xs):
        if _row_matches_canonical(row, striker_ref):
            striker_row = row
            striker_idx = _i
            break

    non_row = None
    if non_ref:
        for _j, row in enumerate(xs):
            if striker_idx is not None and _j == striker_idx:
                continue
            if _row_matches_canonical(row, non_ref):
                non_row = row
                break

    # CASE 5 — striker matched, partner unresolved → fill bat2 from remaining row
    if striker_row is not None and non_row is None and len(xs) >= 2:
        for _j, row in enumerate(xs):
            if striker_idx is not None and _j == striker_idx:
                continue
            non_row = row
            break

    # CASE 1 (+ CASE 5 completion) — striker row plus partner row identified
    if striker_row is not None and non_row is not None:
        return (
            _strip_sentinel_row(striker_row),
            _strip_sentinel_row(non_row))

    # CASE 4 — striker known but OCR could not match rows → fallback strip order
    _ext_names = [(r.get("name") or "").strip() for r in xs]
    log.warn(
        "  [STRIKER-ALIGN-FALLBACK] fallback strip order — striker/non could "
        f"not be matched (striker_ref={striker_ref!r}, "
        f"non_ref={non_ref!r}, ext_batter_names={_ext_names!r})")

    return (
        _strip_sentinel_row(xs[0]),
        _strip_sentinel_row(xs[1]) if len(xs) >= 2 else None)


# Maximum overs / score for a single T20 innings, used as sanity
# bounds for the innings-1 final-state latch.  T20 caps at 20 overs;
# a 350-run innings would shatter the IPL record by ~85 (max in IPL
# history is 287/3 by SRH on 2024-03-27).  Anything above these
# thresholds is an extractor hallucination (e.g. F921 on 2026-04-25
# read 639-4 (76.5) from a partly-tornoff broadcast graphic).
# Without these bounds the latch's max-wins logic locks out
# subsequent legitimate finals — see backlog "P0: Innings-1-final
# latch poisoned".
_INNINGS_TOTAL_MAX_OVERS = 20.0
_INNINGS_TOTAL_MAX_SCORE = 350


def _should_latch_innings_1_candidate(
        cand_score: int, cand_wkts: int, cand_overs_raw,
        existing_score: int, existing_wkts: int) -> tuple[bool, str | None]:
    """Decide whether a candidate innings-1 final should overwrite
    the latched value via max-wins logic, gated by T20 sanity bounds.

    Returns (should_latch, reject_reason).  When `should_latch` is
    False, `reject_reason` is "sanity_bound" if the candidate is
    impossibly high (extractor hallucination) or "max_wins_lost" if
    the candidate is legitimate but doesn't beat the existing latch.
    """
    try:
        cand_overs_f = float(cand_overs_raw)
    except (TypeError, ValueError):
        cand_overs_f = -1.0
    if (cand_overs_f > _INNINGS_TOTAL_MAX_OVERS
            or cand_score > _INNINGS_TOTAL_MAX_SCORE):
        return False, "sanity_bound"
    if (cand_score > existing_score
            or (cand_score == existing_score
                and cand_wkts > existing_wkts)):
        return True, None
    return False, "max_wins_lost"


def _validate_overs(ext_overs: float | None,
                    broadcast_this_over: list[str] | None,
                    confirmed_overs: float | None = None) -> float | None:
    """Cross-validate extractor overs against this-over token count.

    The this_over display (e.g. ['.', '4', '1']) provides an independent
    ball count.  When the extractor misreads decimals (0.1 → 1.0), the
    token count catches it.

    Three correction patterns we handle:

    1.  ``ball_from_overs == ball_from_tokens`` — extractor agrees with
        the strip; pass through.

    2.  ``ext_overs`` is at a whole boundary (X.0) but tokens > 0 —
        we just rolled into a new over but Scout briefly reads the
        previous over's circles. Correct to (X-1).N (the closing balls
        of the previous over).

    3.  Digit-swap. Extractor reads ``N.0`` (or any value whose
        integer part >> the previous confirmed integer part) but the
        token count says we're only N balls into an over. The truth
        is ``(prev_int).N`` — i.e. the digits got swapped (0.3 → 3.0).
        Detected when ``int(ext_overs)`` is significantly ahead of
        ``confirmed_overs``'s integer part. Without ``confirmed_overs``
        we cannot distinguish digit-swap from a legitimate over jump
        and fall back to the (X-1).N rule.
    """
    if ext_overs is None or broadcast_this_over is None:
        return ext_overs
    if len(broadcast_this_over) == 0:
        return ext_overs

    ball_from_overs = round((ext_overs % 1) * 10)
    ball_from_tokens = len(broadcast_this_over)

    if ball_from_tokens > 6:
        # Defence against multi-over recap strips leaking through. We
        # cannot trust this_over's count to validate overs if Scout
        # gave us the 18-token last-3-overs ribbon.
        return ext_overs

    if ball_from_overs == ball_from_tokens:
        return ext_overs

    ext_int = int(ext_overs)

    # Digit-swap detection. If we have a prior confirmed overs reading,
    # an extractor jump from (prev_int).x to (much bigger int).0 with a
    # token count matching the SMALL value is almost certainly a digit
    # swap. Example: prev=0.2, ext=3.0, tokens=3 → real value is 0.3.
    if (confirmed_overs is not None
            and ball_from_overs == 0
            and ball_from_tokens > 0):
        conf_int = int(confirmed_overs)
        if ext_int > conf_int + 1:
            corrected = float(f"{conf_int}.{ball_from_tokens}")
            log.info(
                f"  [OVERS FIX] digit-swap: extractor={ext_overs} "
                f"vs confirmed={confirmed_overs} + "
                f"this_over_tokens={ball_from_tokens} → {corrected}")
            return corrected

    if ball_from_overs == 0 and ball_from_tokens > 0:
        corrected = float(f"{max(0, ext_int - 1)}.{ball_from_tokens}")
    else:
        corrected = float(f"{ext_int}.{ball_from_tokens}")

    # Guard against regressing below confirmed overs.  A poisoned scout
    # frame can produce stale / misparsed this_over tokens (e.g. reading
    # "w w w 4 6" from a replay graphic) whose count contradicts the
    # confirmed extractor overs.  Applying the "X-1.N" correction in that
    # case pushes ext_overs BACKWARDS past the true live overs — which in
    # turn trips ScoreManager's overs-regression guard and sends it into
    # COLD_START, losing any real ball events that arrive during the
    # 3-frame re-warmup.  This was the root cause of the live LSG-vs-RR
    # F121→F122 failure where the SIX at 9.1 never reached the UI's
    # this_over (diverged from over_mgr's correctly-observed sequence).
    # If our "correction" would roll overs backward past a value we've
    # already confirmed, trust the confirmed value and skip the fix.
    if confirmed_overs is not None and corrected < confirmed_overs:
        log.info(
            f"  [OVERS FIX] SKIP regression: computed={corrected} "
            f"< confirmed={confirmed_overs} (tokens={ball_from_tokens} "
            f"likely stale/poisoned) — keeping ext_overs={ext_overs}")
        return ext_overs

    log.info(f"  [OVERS FIX] extractor={ext_overs} "
             f"this_over_tokens={ball_from_tokens} → {corrected}")
    return corrected


def _ext_name_matches_canonical(ext_name, canonical, sb) -> bool:
    if not ext_name or not canonical:
        return False
    if str(ext_name).upper() == str(canonical).upper():
        return True
    try:
        return sb.resolve_name(ext_name) == canonical
    except Exception:
        return False


def _is_placeholder(name: str) -> bool:
    if not name:
        return True
    up = name.upper().strip()
    if up in _PLACEHOLDER_EXACT:
        return True
    if re.match(r'^BATTER\d*', up):
        return True
    if re.match(r'^BOWLER\d*', up):
        return True
    if re.match(r'^PLAYER\d*', up):
        return True
    if "FROM_VISION" in up:
        return True
    if "EXACT_" in up:
        return True
    if "_NAME" in up:
        return True
    return False


_THIS_OVER_RE = re.compile(
    r'(?:this[_ ]?over|current[_ ]?over|ball[_ ]?by[_ ]?ball)\s*[:\-]?\s*'
    r'([0-9WwDdNnBb.\s/]+(?:\s+[0-9WwDdNnBb.]+)*)',
    re.IGNORECASE
)
_THIS_OVER_TOKEN_RE = re.compile(
    r'(?:\b(?:[0-7]lb|[0-7]b|lb|wd|wide|nb|noball|no[_ ]ball|[0-7]|W)\b|\.)',
    re.IGNORECASE)

_THIS_OVER_LINE_HARD_SEPARATORS = (
    "|", "EXTRA:", "EXTRAS:", "FULL", "SPEED:",
    "INFO_PANEL", "TARGET", "TO WIN", "RECENT", "FOURS",
    "SIXES", "FALL OF", "P'SHIP", "PARTNERSHIP")
_THIS_OVER_LINE_MAX_CHARS = 30


def _bound_this_over_slice(line: str, keyword_idx: int,
                           keyword_len: int) -> str:
    """Return the trimmed slice that follows ``THIS OVER`` (or
    ``CURRENT OVER``) on a single Scout line.

    Truncated at the first hard separator (``|``, ``EXTRA:``, ``FULL``,
    ``SPEED:`` …) or at :data:`_THIS_OVER_LINE_MAX_CHARS` characters,
    whichever comes first. Prevents the line-based fallback in
    :func:`_parse_this_over_from_scout` from scooping up unrelated
    digits (score, batter stats, partnership runs) when Scout reads
    multiple panels onto one line — see
    ``files/docs/investigations/p8_diagnosis.md`` §3.
    """
    tail = line[keyword_idx + keyword_len:]
    upper = tail.upper()
    cut = len(tail)
    for sep in _THIS_OVER_LINE_HARD_SEPARATORS:
        idx = upper.find(sep)
        if idx != -1 and idx < cut:
            cut = idx
    cut = min(cut, _THIS_OVER_LINE_MAX_CHARS)
    return tail[:cut]


def _parse_this_over_from_scout(scout_text: str) -> list[str] | None:
    """Try to extract this-over tokens from Scout's raw text."""
    m = _THIS_OVER_RE.search(scout_text)
    if not m:
        for line in scout_text.split("\n"):
            low = line.lower()
            for kw in ("this over", "current over"):
                kw_idx = low.find(kw)
                if kw_idx == -1:
                    continue
                slice_ = _bound_this_over_slice(line, kw_idx, len(kw))
                tokens = _THIS_OVER_TOKEN_RE.findall(slice_)
                if tokens:
                    return tokens
                break
        return None
    tokens = _THIS_OVER_TOKEN_RE.findall(m.group(1))
    return tokens if tokens else None


# ── Compiled regexes for broadcast data extraction ──────────────────
_RE_SPEED = re.compile(r'SPEED:\s*([\d.]+)\s*(?:kph|km/?h)?', re.IGNORECASE)
_RE_TARGET = re.compile(r'TARGET\s+(\d{2,3})', re.IGNORECASE)
_RE_TO_WIN = re.compile(
    r'(?:TO\s+WIN|NEED|REQUIRED)\s+(\d{2,3})\s+(?:OFF|FROM)\s+(\d{1,3})',
    re.IGNORECASE)
_RE_STRIKER = re.compile(r'[>*]\s*([A-Z][A-Za-z\s\'-]+?)\s+\d+\s*\(\d+\)')
_RE_FOURS = re.compile(r'FOURS?\s*[:\s]+(\d+)', re.IGNORECASE)
_RE_SIXES = re.compile(r'SIXES?\s*[:\s]+(\d+)', re.IGNORECASE)
_RE_EXTRAS_PANEL = re.compile(
    r'EXTRA(?:S)?:\s*(\d+)\s*\(([^)]*)\)', re.IGNORECASE)
_RE_EXTRA_TYPE = re.compile(
    r'EXTRA:\s*(WD|NB|Wd|Nb|Wide|No\s*Ball|WIDE|NO\s*BALL)',
    re.IGNORECASE)
_RE_DISMISSAL_MODE = re.compile(
    r'\b(BOWLED|CAUGHT|LBW|STUMPED|RUN\s*OUT|HIT\s*WICKET|'
    r'RETIRED\s*HURT|RETIRED\s*OUT)\b',
    re.IGNORECASE)
_RE_TEAM_ABBR = re.compile(
    r'\b(MI|CSK|RCB|KKR|SRH|RR|DC|PBKS|LSG|GT|NZ|WI|AUS|IND|ENG|SA|PAK|SL|BAN|AFG|IRE|ZIM|SCO|NAM)\s+\d')
_VENUE_PATTERNS = [
    re.compile(r'LIVE\s+FROM\s+(.+?)(?:\||\n|$)', re.IGNORECASE),
    re.compile(r'VENUE:\s*(.+?)(?:\||\n|$)', re.IGNORECASE),
    re.compile(r'(?:at|AT)\s+(?:the\s+)?(.+?'
               r'(?:Stadium|Ground|Cricket|Oval|Park|Gardens|'
               r'Chinnaswamy|Wankhede|Eden|Chepauk|Feroz Shah|'
               r'Narendra Modi|Arun Jaitley|Sawai Mansingh|'
               r'Rajiv Gandhi|Uppal|Brabourne|DY Patil))',
               re.IGNORECASE),
]
_MATCH_INFO_PATTERNS = [
    re.compile(r'(\d+(?:st|nd|rd|th)\s+Match)', re.IGNORECASE),
    re.compile(r'(MATCH\s+\d+)', re.IGNORECASE),
    re.compile(r'(#\w+v\w+)', re.IGNORECASE),
    re.compile(r'((?:FIRST|SECOND|THIRD|FOURTH|FIFTH)\s+T20I)',
               re.IGNORECASE),
    re.compile(r'(IPL\s+\d{4})', re.IGNORECASE),
]


def extract_broadcast_data(scout_text: str, cache: dict) -> dict:
    """Extract all deterministic data from Scout's raw text in one pass.

    Per-frame values are always returned. Session-level values (venue,
    match_info, team_abbr) are set in ``cache`` once and reused.
    Returns a dict of per-frame extracted values.
    """
    result: dict = {}
    if not scout_text:
        return result

    # ── Per-frame: speed ────────────────────────────────────────────
    m = _RE_SPEED.search(scout_text)
    if m:
        try:
            _spd = float(m.group(1))
            if 60.0 <= _spd <= 170.0:
                result["speed_kph"] = _spd
        except (ValueError, TypeError):
            pass

    # ── Per-frame: striker indicator (* or >) ───────────────────────
    m = _RE_STRIKER.search(scout_text)
    if m:
        result["striker_broadcast"] = m.group(1).strip()

    # ── Per-frame: fours/sixes counts ───────────────────────────────
    m = _RE_FOURS.search(scout_text)
    if m:
        result["fours"] = int(m.group(1))
    m = _RE_SIXES.search(scout_text)
    if m:
        result["sixes"] = int(m.group(1))

    # ── Per-frame: extras from info panel ───────────────────────────
    m = _RE_EXTRAS_PANEL.search(scout_text)
    if m:
        result["extras_total"] = int(m.group(1))
        result["extras_detail"] = m.group(2).strip()

    # ── Per-frame: current delivery extra type (e.g. "EXTRA: WD") ──
    m = _RE_EXTRA_TYPE.search(scout_text)
    if m:
        raw = m.group(1).strip().upper().replace(" ", "")
        if raw in ("WD", "WIDE"):
            result["broadcast_extra"] = "WD"
        elif raw in ("NB", "NOBALL"):
            result["broadcast_extra"] = "NB"

    # ── Per-frame: dismissal mode keyword (BOWLED/CAUGHT/LBW etc.) ─
    m = _RE_DISMISSAL_MODE.search(scout_text)
    if m:
        raw = m.group(1).strip().upper().replace(" ", "_")
        mode_map = {
            "BOWLED": "bowled", "CAUGHT": "caught",
            "LBW": "lbw", "STUMPED": "stumped",
            "RUNOUT": "run_out", "RUN_OUT": "run_out",
            "HIT_WICKET": "hit_wicket",
            "RETIRED_HURT": "retired_hurt",
            "RETIRED_OUT": "retired_out",
        }
        mode = mode_map.get(raw)
        if mode:
            result["dismissal_mode"] = mode

    # ── Per-frame: this-over from info panel ────────────────────────
    this_over = _parse_this_over_from_scout(scout_text)
    if this_over:
        result["this_over_broadcast"] = this_over

    # ── Cache-once: target ──────────────────────────────────────────
    if not cache.get("target"):
        m = _RE_TARGET.search(scout_text)
        if m:
            try:
                val = int(m.group(1))
                if val > 50:
                    cache["target"] = val
                    result["target"] = val
                    log.info(f"  [BROADCAST] Target extracted: {val}")
            except (ValueError, TypeError):
                pass
    if not cache.get("target"):
        m = _RE_TO_WIN.search(scout_text)
        if m:
            try:
                runs_needed = int(m.group(1))
                balls_rem = int(m.group(2))
                if runs_needed >= 10:
                    result["runs_needed"] = runs_needed
                    result["balls_remaining_chase"] = balls_rem
                    log.info(f"  [BROADCAST] Chase: {runs_needed} "
                             f"from {balls_rem} balls")
            except (ValueError, TypeError):
                pass

    # ── Cache-once: venue ───────────────────────────────────────────
    if not cache.get("venue"):
        for pat in _VENUE_PATTERNS:
            m = pat.search(scout_text)
            if m:
                cache["venue"] = m.group(1).strip().rstrip(".,;:")
                log.info(f"  [BROADCAST] Venue: {cache['venue']}")
                break

    # ── Cache-once: match info ──────────────────────────────────────
    if not cache.get("match_info"):
        for pat in _MATCH_INFO_PATTERNS:
            m = pat.search(scout_text)
            if m:
                cache["match_info"] = m.group(1).strip()
                log.info(f"  [BROADCAST] Match: {cache['match_info']}")
                break

    # ── Cache-once: team abbreviation ───────────────────────────────
    if not cache.get("team_abbr"):
        m = _RE_TEAM_ABBR.search(scout_text)
        if m:
            cache["team_abbr"] = m.group(1)

    return result


def clean_player_name(name: str) -> str:
    """Strip common broadcast suffixes: IMP, (C), (WK), * etc."""
    if not name:
        return name
    suffixes = [" IMP", " (IMP)", " IMPACT", " (C)", " (WK)",
                " (WK-C)", "(C)", "(WK)", "*"]
    upper = name.upper().strip()
    for suffix in suffixes:
        if upper.endswith(suffix):
            name = name[:len(name) - len(suffix)].strip()
            break
    return name


def clean_batter_entry(batter: dict) -> dict:
    """Strip stats embedded in name: 'TILAK 9(4)' → name='TILAK', runs=9, balls=4."""
    name = batter.get("name", "")
    if not name:
        return batter
    batter["_raw_name"] = name
    stat_match = re.search(r'(\d+)\s*\((\d+)\)', name)
    if stat_match:
        if batter.get("runs") is None or batter.get("runs") == 0:
            batter["runs"] = int(stat_match.group(1))
        if batter.get("balls") is None or batter.get("balls") == 0:
            batter["balls"] = int(stat_match.group(2))
    cleaned = re.sub(r'\s*\d+\s*\(?\d*\)?\s*$', '', name).strip()
    if cleaned:
        batter["name"] = cleaned
    return batter


def parse_bowling_figures(raw: str) -> dict | None:
    """Parse any bowling figure format into standard fields.

    Formats seen on broadcast:
      1-0-18-0    → overs=1, maidens=0, runs=18, wickets=0
      2-34 (3.2)  → wickets=2, runs=34, overs=3.2
      0-18 (1)    → wickets=0, runs=18, overs=1
      3/25        → wickets=3, runs=25
    """
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()

    full = re.match(r'(\d+\.?\d*)-(\d+)-(\d+)-(\d+)', raw)
    if full:
        return {
            "overs": full.group(1),
            "maidens": int(full.group(2)),
            "runs": int(full.group(3)),
            "wickets": int(full.group(4)),
        }

    wr_overs = re.match(r'(\d+)\s*[-/]\s*(\d+)\s*\((\d+\.?\d*)\)', raw)
    if wr_overs:
        w, r = int(wr_overs.group(1)), int(wr_overs.group(2))
        o = wr_overs.group(3)
        if w > r and w > 5:
            w, r = r, w
        if "." not in o:
            o = o + ".0"
        return {"wickets": w, "runs": r, "overs": o}

    wr = re.match(r'(\d+)\s*[-/]\s*(\d+)$', raw)
    if wr:
        w, r = int(wr.group(1)), int(wr.group(2))
        if w > r and w > 5:
            w, r = r, w
        return {"wickets": w, "runs": r}

    return None


def clean_bowler_entry(bowler: dict) -> dict:
    """Strip standard bowling figures from name: 'MUKESH 2-8 (1.5)' → name='MUKESH'.
    Handles O-M-R-W (4-field) format and W-R(O) / W/R(O) formats."""
    name = bowler.get("name", "")
    if not name:
        return bowler

    full_fig = re.search(r'(\d+\.?\d*)-(\d+)-(\d+)-(\d+)', name)
    if full_fig:
        parsed = parse_bowling_figures(full_fig.group(0))
        if parsed:
            for k, v in parsed.items():
                if bowler.get(k) is None or bowler.get(k) in (0, "0"):
                    bowler[k] = v
        cleaned = name[:full_fig.start()].strip()
        if cleaned:
            bowler["name"] = cleaned
        return bowler

    fig_match = re.search(r'(\d+)\s*[-/]\s*(\d+)\s*\((\d+\.?\d*)\)', name)
    if fig_match:
        parsed = parse_bowling_figures(fig_match.group(0))
        if parsed:
            for k, v in parsed.items():
                if bowler.get(k) is None or bowler.get(k) in (0, "0"):
                    bowler[k] = v
        cleaned = re.sub(r'\s*\d+\s*[-/]\s*\d+\s*\(\d+\.?\d*\)\s*$', '', name).strip()
    else:
        cleaned = re.sub(r'[\s\d()./,-]+$', '', name).strip()
    if cleaned:
        bowler["name"] = cleaned
    return bowler


def _resolve_to_squad(token: str, name_lookup: dict) -> str | None:
    """Check if a token resolves to a squad member via the lookup table."""
    up = token.upper().strip()
    if up in name_lookup:
        return name_lookup[up]
    return None


def _extract_stat_pairs(raw: str) -> list[tuple[int, int]]:
    """Extract runs(balls) pairs from a raw string.
    '9(7) 12(8)' → [(9,7), (12,8)]
    'SURYAKUMAR ROHIT 9 7 12 8' → [(9,7), (12,8)]"""
    pairs = re.findall(r'(\d+)\s*\((\d+)\)', raw)
    if pairs:
        return [(int(a), int(b)) for a, b in pairs]
    nums = re.findall(r'\d+', raw)
    if len(nums) >= 4:
        return [(int(nums[i]), int(nums[i + 1]))
                for i in range(0, len(nums) - 1, 2)]
    return []


def _resolve_for_split(token: str, name_lookup: dict, scoreboard) -> str | None:
    """Resolve a token to a squad member using lookup + fuzzy scoreboard match."""
    hit = _resolve_to_squad(token, name_lookup)
    if hit:
        return hit
    if scoreboard:
        return scoreboard.resolve_name(token)
    return None


def split_merged_batters(batters: list[dict], name_lookup: dict,
                         scoreboard) -> list[dict]:
    """Split merged batter names like 'SURYAKUMAR ROHIT' using squad lookup.
    Uses scoreboard history to assign stats to the right player.
    Also detects merged adjacent names like 'PRASHANT DUBE' where
    each part resolves to a different squad member."""
    result = []
    for batter in batters:
        raw_name = batter.get("name", "")
        name_only = re.sub(r'[\d()*>]+', ' ', raw_name).strip()
        name_only = re.sub(r'\s+', ' ', name_only)
        words = name_only.upper().strip().split()
        if len(words) < 2:
            result.append(batter)
            continue

        # Use resolve_name_split if scoreboard available — detects
        # merged names like "Prashant Dube" → Prashant Veer + Shivam Dube
        if scoreboard and scoreboard.batting_card:
            split_names = scoreboard.resolve_name_split(name_only)
            if len(split_names) == 2:
                raw = batter.get("_raw_name", raw_name)
                pairs = _extract_stat_pairs(raw)

                b1 = {"name": words[0], "runs": None, "balls": None,
                       "striker": batter.get("striker")}
                b2 = {"name": " ".join(words[1:]), "runs": None,
                       "balls": None, "striker": None}

                if len(pairs) >= 2:
                    _assign_stats_by_history(
                        b1, b2, split_names[0], split_names[1],
                        pairs[0], pairs[1], scoreboard)
                elif len(pairs) == 1:
                    b1["runs"], b1["balls"] = pairs[0]
                elif batter.get("runs") is not None:
                    b1["runs"] = batter.get("runs")
                    b1["balls"] = batter.get("balls")

                log.info(f"  [SPLIT] Merged names: '{raw_name}' → "
                         f"'{split_names[0]}' + '{split_names[1]}'")
                result.append(b1)
                result.append(b2)
                continue
            elif len(split_names) == 1:
                result.append(batter)
                continue

        # Fallback: don't split if the full name resolves to a squad member
        full_match = _resolve_for_split(name_only, name_lookup, scoreboard)
        if full_match:
            result.append(batter)
            continue

        split_found = False
        for i in range(1, len(words)):
            left = " ".join(words[:i])
            right = " ".join(words[i:])
            left_match = _resolve_for_split(left, name_lookup, scoreboard)
            right_match = _resolve_for_split(right, name_lookup, scoreboard)
            if left_match and right_match and left_match != right_match:
                raw = batter.get("_raw_name", raw_name)
                pairs = _extract_stat_pairs(raw)

                b1 = {"name": left, "runs": None, "balls": None,
                       "striker": batter.get("striker")}
                b2 = {"name": right, "runs": None, "balls": None,
                       "striker": None}

                if len(pairs) >= 2:
                    _assign_stats_by_history(
                        b1, b2, left_match, right_match,
                        pairs[0], pairs[1], scoreboard)
                elif len(pairs) == 1:
                    b1["runs"], b1["balls"] = pairs[0]
                elif batter.get("runs") is not None:
                    b1["runs"] = batter.get("runs")
                    b1["balls"] = batter.get("balls")

                log.info(f"  [SPLIT] '{raw_name}' → '{left}' + '{right}'")
                result.append(b1)
                result.append(b2)
                split_found = True
                break

        if not split_found:
            result.append(batter)
    return result


def _assign_stats_by_history(b1, b2, name1, name2,
                             pair_a, pair_b, scoreboard):
    """Assign two stat pairs to two players using scoreboard history."""
    prev1 = _get_previous_runs(name1, scoreboard)
    prev2 = _get_previous_runs(name2, scoreboard)

    if prev1 is not None and prev2 is not None:
        diff_a1 = abs(pair_a[0] - prev1)
        diff_b1 = abs(pair_b[0] - prev1)
        diff_a2 = abs(pair_a[0] - prev2)
        diff_b2 = abs(pair_b[0] - prev2)

        if (diff_a1 + diff_b2) <= (diff_b1 + diff_a2):
            b1["runs"], b1["balls"] = pair_a
            b2["runs"], b2["balls"] = pair_b
        else:
            b1["runs"], b1["balls"] = pair_b
            b2["runs"], b2["balls"] = pair_a
    else:
        b1["runs"], b1["balls"] = pair_a
        b2["runs"], b2["balls"] = pair_b


def _get_previous_runs(canonical: str, scoreboard) -> int | None:
    """Get last known runs for a player from the batting card."""
    if not scoreboard or not scoreboard.batting_card:
        return None
    entry = scoreboard.batting_card.get(canonical)
    if entry and entry.get("runs") is not None:
        return entry["runs"]
    return None


_IPL_BROADCAST_NAMES = {
    "Gujarat Titans": ["GT", "GUJ", "TITANS"],
    "Mumbai Indians": ["MI", "MUM", "MUMBAI"],
    "Rajasthan Royals": ["RR", "RAJ", "ROYALS"],
    "Delhi Capitals": ["DC", "DEL", "DELHI"],
    "Chennai Super Kings": ["CSK", "CHE", "CHENNAI"],
    "Royal Challengers Bengaluru": ["RCB", "BAN", "BENGALURU", "BANGALORE"],
    "Sunrisers Hyderabad": ["SRH", "HYD", "SUNRISERS"],
    "Kolkata Knight Riders": ["KKR", "KOL", "KOLKATA"],
    "Punjab Kings": ["PBKS", "PUN", "PUNJAB"],
    "Lucknow Super Giants": ["LSG", "LKN", "LUCKNOW"],
}


def build_team_variants(team: dict) -> set[str]:
    """Generate all valid ways a team might appear on broadcast."""
    variants: set[str] = set()
    name = team.get("name", "")
    full = team.get("full_name", name)

    variants.add(name.upper())
    variants.add(full.upper())

    variants.add(name[:2].upper())
    variants.add(name[:3].upper())

    words = full.split()
    if len(words) >= 2:
        variants.add("".join(w[0] for w in words).upper())

    for w in words:
        w_up = w.upper()
        variants.add(w_up)
        if len(w_up) >= 4:
            variants.add(w_up[:3])

    for key, abbrs in _IPL_BROADCAST_NAMES.items():
        if key.upper() in full.upper() or full.upper() in key.upper():
            variants.update(a.upper() for a in abbrs)

    variants.discard("")
    return variants


_IMPACT_SUB_INDICATORS = (
    "TOSS", "CHOSE TO", "WON THE TOSS",
    "IMPACT", "IMP SUB", "SUBSTITUTE", "REPLACES",
    "SUB IN", "SUB OUT", "COMING IN FOR",
    "IMPACT SUB OPTIONS", "SUB OPTIONS",
)


def detect_dismissal_in_vision(vision_desc: str) -> dict | None:
    """Backup: detect dismissal patterns in raw vision text.

    Requires fielder/bowler attribution (c/b/lbw/run out/st).
    Bare 'OUT' without attribution is ignored — could be impact sub.
    Frames with impact sub context are skipped entirely.
    """
    if not vision_desc:
        return None

    upper = vision_desc.upper()

    # Impact sub context → skip entirely, "OUT" means leaving XI
    if any(ind in upper for ind in _IMPACT_SUB_INDICATORS):
        return None

    _PATTERNS = [
        (r'(\w[\w\s]*?)\s+(\d+)\s*\((\d+)\)\s+c\s+([\w\s]+?)\s+b\s+(\w+)',
         "caught"),
        (r'(\w[\w\s]*?)\s+(\d+)\s*\((\d+)\)\s+st\s+([\w\s]+?)\s+b\s+(\w+)',
         "stumped"),
        (r'(\w[\w\s]*?)\s+(\d+)\s*\((\d+)\)\s+lbw\s+b\s+(\w+)',
         "lbw"),
        (r'(\w[\w\s]*?)\s+(\d+)\s*\((\d+)\)\s+b\s+(\w+)',
         "bowled"),
        (r'(\w[\w\s]*?)\s+(\d+)\s*\((\d+)\)\s+run\s+out',
         "run_out"),
        (r'(\w[\w\s]*?)\s+(\d+)\s*\((\d+)\)\s+retired',
         "retired"),
    ]
    for pattern, mode in _PATTERNS:
        m = re.search(pattern, vision_desc, re.IGNORECASE)
        if m:
            groups = m.groups()
            result = {
                "batter": groups[0].strip(),
                "type": mode,
                "runs": int(groups[1]),
                "balls": int(groups[2]),
            }
            if mode in ("caught", "stumped"):
                result["fielder"] = groups[3].strip()
                result["bowler"] = groups[4].strip()
            elif mode in ("lbw", "bowled"):
                result["bowler"] = groups[3].strip()
            return result
    return None


_COMMS_INDICATORS = ("ON THE MIC", "COMMS", "COMMENTARY", "COMM BOX",
                     "IN THE BOX", "ANALYST", "PRESENTER", "ON AIR")

_STAT_PANEL_INDICATORS = (
    "IN T20", "IN ODI", "IN TEST", "SINCE 20",
    "VS LEFT", "VS RIGHT", "V LEFT", "V RIGHT",
    "LEFT ARM", "RIGHT ARM", "SEAMERS", "SPINNERS",
    "PACERS", "LEG SPINNERS", "OFF SPINNERS",
)

_BOWLING_TYPE_KEYWORDS = (
    "SEAMERS", "SPINNERS", "PACERS", "LEFT ARM",
    "RIGHT ARM", "LEG SPIN", "OFF SPIN", "MEDIUM PACE",
)


def _has_commentary_context(vision_desc: str | None) -> bool:
    if not vision_desc:
        return False
    upper = vision_desc.upper()
    return any(ind in upper for ind in _COMMS_INDICATORS)


def _is_stat_panel(vision_desc: str | None) -> bool:
    """Check if the frame shows a stat panel (not live play)."""
    if not vision_desc:
        return False
    upper = vision_desc.upper()
    return any(ind in upper for ind in _STAT_PANEL_INDICATORS)


def _is_bowling_type_name(name: str) -> bool:
    """Check if a 'name' is actually a bowling type label, not a player."""
    if not name:
        return False
    upper = name.upper().strip()
    return any(kw in upper for kw in _BOWLING_TYPE_KEYWORDS)


_INFO_PANEL_KEYWORDS = [
    "IPL CAREER", "CAREER", "IN T20", "IN ODI",
    "SINCE 20", "ALL TIME", "TOURNAMENT", "SEASON STATS",
    "HEAD TO HEAD", "V SPINNERS", "V PACERS",
    "V LEFT ARM", "V RIGHT ARM", "PROJECTED SCORE",
    "PAR SCORE", "PREDICTED SCORE", "ECONOMY", "MATCHES",
    "TOP SCORES", "BOWLING STATS", "BATTING STATS",
    "PLAYER STATS", "BEST FIGURES", "PURPLE CAP", "ORANGE CAP",
]

_STANDINGS_ROW_KEYWORDS = [
    "STANDINGS", "TABLE", "RANK", "RANKINGS", "POSITION",
    "POINTS TABLE", "IPL POSITION",
]


def filter_standings_row_contamination(extracted: dict,
                                       vision_desc: str) -> dict:
    """Strip score-shaped fields from contextual standings graphics."""
    if not vision_desc:
        return extracted
    upper = vision_desc.upper()
    _matched_keyword = next(
        (kw for kw in _STANDINGS_ROW_KEYWORDS if kw in upper), None)
    if not _matched_keyword:
        return extracted
    if any(extracted.get(k) is not None
           for k in ("score", "wickets", "match_overs")):
        log.warn(
            f"  [STANDINGS-ROW-GATE] score fields stripped — "
            f"keyword={_matched_keyword!r}")
        extracted.pop("score", None)
        extracted.pop("wickets", None)
        extracted.pop("match_overs", None)
    return extracted


def _entry_has_score_stats(entry: dict) -> bool:
    return entry.get("runs") is not None or entry.get("balls") is not None


def normalize_extracted_batters(extracted: dict, scoreboard=None) -> dict:
    """Canonicalize batter rows and drop surname-only ghost fragments."""
    batters = extracted.get("batters")
    if not batters or not isinstance(batters, list) or scoreboard is None:
        return extracted
    batting_card = getattr(scoreboard, "batting_card", None) or {}
    if not batting_card:
        return extracted

    resolved_rows = []
    for row in batters:
        if not isinstance(row, dict):
            continue
        raw = (row.get("name") or "").strip()
        if not raw:
            continue
        resolved = scoreboard.resolve_name(raw)
        card_key = (scoreboard._find_card_key(resolved, batting_card)
                    if resolved else None)
        resolved_rows.append((row, raw, card_key))

    canonical_by_raw = {
        raw.upper(): card_key for _, raw, card_key in resolved_rows if card_key
    }
    cleaned: list[dict] = []
    by_key: dict[str, dict] = {}
    for row, raw, card_key in resolved_rows:
        raw_upper = raw.upper()
        parts = raw_upper.split()
        no_stats = not _entry_has_score_stats(row)
        if len(parts) == 1 and no_stats:
            token = parts[0]
            sibling_key = next(
                (key for other_raw, key in canonical_by_raw.items()
                 if other_raw != raw_upper
                 and token in key.upper().split()[1:]),
                None)
            if sibling_key:
                log.warn(
                    f"  [BATTER-NORMALIZE] dropping surname ghost "
                    f"{raw!r} paired with {sibling_key!r}")
                continue
        if card_key:
            row["name"] = card_key
            existing = by_key.get(card_key)
            if existing is None:
                by_key[card_key] = row
                cleaned.append(row)
            else:
                if (_entry_has_score_stats(row)
                        and not _entry_has_score_stats(existing)):
                    existing.update(row)
                if existing.get("striker") is None and row.get("striker") is not None:
                    existing["striker"] = row.get("striker")
                log.warn(
                    f"  [BATTER-NORMALIZE] merged duplicate row "
                    f"{raw!r} into {card_key!r}")
        else:
            cleaned.append(row)
    extracted["batters"] = cleaned
    return extracted


def filter_bowler_batter_row_contamination(extracted: dict,
                                           scoreboard=None) -> dict:
    """Strip bowler reads that are actually active batting rows."""
    if scoreboard is None:
        return extracted
    bowler = extracted.get("bowler")
    if not isinstance(bowler, dict):
        return extracted
    name = (bowler.get("name") or "").strip()
    if not name:
        return extracted
    batting_card = getattr(scoreboard, "batting_card", None) or {}
    if not batting_card:
        return extracted
    resolved = scoreboard.resolve_name(name)
    card_key = (scoreboard._find_card_key(resolved, batting_card)
                if resolved else None)
    batter_names = set()
    for row in extracted.get("batters") or []:
        raw = (row.get("name") or "").strip()
        if raw:
            batter_names.add(raw.upper())
            row_resolved = scoreboard.resolve_name(raw)
            if row_resolved:
                batter_names.add(row_resolved.upper())
    has_complete_figures = (
        bowler.get("wickets") is not None
        and bowler.get("runs") is not None
        and bowler.get("overs") is not None)
    # DC-vs-CSK Fix 2: bowler-row read is independent of batter-row
    # read; don't couple them. Strip ONLY when (a) the bowler row
    # itself is incomplete, OR (b) the name doesn't resolve to any
    # current batter AND isn't in the bowling-side squad roster
    # (squad-roster check protects against OCR artifacts).
    is_squad_bowler = False
    bowling_card = getattr(scoreboard, "bowling_card", None) or {}
    if bowling_card:
        name_upper = name.upper()
        resolved_lookup = (resolved or "").upper() if resolved else ""
        for b_key in bowling_card.keys():
            b_upper = (b_key or "").upper()
            if b_upper and (b_upper == name_upper
                            or (resolved_lookup
                                and b_upper == resolved_lookup)):
                is_squad_bowler = True
                break
    should_strip = (not has_complete_figures
                    or (card_key is None and not is_squad_bowler))
    if should_strip:
        log.warn(
            f"  [BOWLER-BATTER-GATE] bowler stripped — "
            f"name={name!r} resolved_batter={card_key!r} "
            f"complete_figures={has_complete_figures} "
            f"is_squad_bowler={is_squad_bowler}")
        extracted.pop("bowler", None)
        extracted.pop("bowler_name", None)
        extracted.pop("bowler_figures", None)
    return extracted


def apply_all_out_authority(scoreboard, text: str | None,
                            frame: int = 0) -> bool:
    """Promote W9 to all-out when final-wicket/innings-break evidence appears."""
    if scoreboard is None:
        return False
    try:
        cur_w = int((scoreboard._inn or {}).get("wickets") or 0)
    except (TypeError, ValueError):
        return False
    if cur_w != 9:
        return False
    upper = (text or "").upper()
    final_wicket_terms = (
        "ALL OUT", "ALL-OUT", "INNINGS BREAK", "END OF INNINGS",
        "INNINGS ENDS", "INNINGS ENDED", "BOWLED", "CAUGHT",
        "LBW", "RUN OUT", "STUMPED", "WICKET",
    )
    matched = next((term for term in final_wicket_terms if term in upper),
                   None)
    if not matched:
        return False
    return scoreboard.accept_all_out_authority(
        source=f"{matched.lower()} evidence", frame=frame)


def filter_info_panel_contamination(extracted: dict, vision_desc: str,
                                    scoreboard) -> dict:
    """When vision mentions a stats info panel, strip the bowler field
    from extracted (score/wickets stay — ConsistentReadTracker bounds
    those).

    Pre-Fix-8 (2026-04-26 inter-match bundle): this function detected
    info-panel content via `_INFO_PANEL_KEYWORDS` but only logged it,
    leaving the tracker to bound score/wicket reads.  That worked for
    score/wickets (the tracker rejects impossible jumps) but bowler
    updates flow through a different SM path that the tracker does NOT
    gate.

    F619 DC vs PBKS (2026-04-25 16:02:04, P1 in `docs/backlog.md`):
    a "YUZVENDRA CHAHAL IPL CAREER MATCHES 181 WICKETS 225 ECONOMY
    8.0" stats overlay with the broadcast strip still partially
    visible was extracted as `bowler="YUZVENDRA CHAHAL"` and committed
    to SM, even though Marco Jansen was bowling the over and Chahal
    hadn't been introduced yet.  The dead-time skip on
    `camera_view == "graphic"` should have caught this, but
    `vision.last_camera_view` lags scout response arrival by 1-2
    frames, so F619 ran with the previous frame's `bowlers_end` tag.

    Fix: content-based gate that doesn't depend on camera_view tag
    timing.  When the vision description contains an `_INFO_PANEL_
    KEYWORDS` marker (career / season / head-to-head / projected-
    score stats markers), strip `bowler`, `bowler_name`, and
    `bowler_figures` from `extracted`.  Why bowler-only:
    (a) bowler ingest bypasses the tracker (score does not — the
        tracker's consistency layer is sufficient)
    (b) bowler is sourced fresh from the broadcast strip on every
        active-play frame; dropping it from one stats-overlay frame
        loses no data, just delays bowler-change pickup by ~1-2 s
    (c) name-dropping a FUTURE bowler in a stats overlay is a
        documented bug pattern (F619, F643 in the
        `pipeline-2026-04-25-153247-dc-pbks-v5.log` trace) — the
        original BOWLER-STALE defense (shipped 2026-04-25) only
        guards against stale-bowler reads, not future-bowler ones

    Telemetry: emits `[INFO-PANEL-GATE]` log line when a strip fires,
    so post-deploy monitoring can count how often graphics with
    bowler-name overlays are caught.  Negative-firing in the steady
    state (most frames have no info-panel keywords) — a sustained
    high rate would suggest the keyword list needs broadening.
    """
    if not vision_desc or not scoreboard or not scoreboard._inn:
        return extracted
    upper = vision_desc.upper()
    _matched_keyword = next(
        (kw for kw in _INFO_PANEL_KEYWORDS if kw in upper), None)
    if not _matched_keyword:
        return extracted
    if extracted.get("bowler") or extracted.get("bowler_name"):
        _bw = extracted.get("bowler") or {}
        _bw_name = (_bw.get("name") if isinstance(_bw, dict)
                    else _bw) or extracted.get("bowler_name")
        log.warn(
            f"  [INFO-PANEL-GATE] bowler stripped — "
            f"name={_bw_name!r} panel_keyword={_matched_keyword!r}")
        extracted.pop("bowler", None)
        extracted.pop("bowler_name", None)
        extracted.pop("bowler_figures", None)
    else:
        log.info(
            f"  [INFO PANEL] Detected (keyword={_matched_keyword!r}) "
            f"— no bowler in extracted, tracker will bound values")
    # Cause-4: stats-overlay keywords often correlate with hallucinated
    # team score reads (graphic digits merged into extractor). When the
    # proposed score already disagrees with the tracker by more than the
    # FRAME POISON threshold, strip score-shaped fields so the poison
    # streak / POISON-RECAL watchdog cannot fire on overlay pollution.
    _ext_sc = extracted.get("score")
    _tr_sc = scoreboard._inn.get("score")
    if _ext_sc is not None and _tr_sc is not None:
        try:
            if abs(int(_ext_sc) - int(_tr_sc)) > 7:
                log.info(
                    f"  [GRAPHIC-FILTER] info_panel_keyword={_matched_keyword!r} "
                    f"divergence — stripping score path "
                    f"(raw_score={int(_ext_sc)!r} tracker={int(_tr_sc)!r}; "
                    f"classification_conf=n/a)")
                extracted.pop("score", None)
                extracted.pop("wickets", None)
                extracted.pop("match_overs", None)
        except (TypeError, ValueError):
            pass
    return extracted


def clean_extracted(extracted: dict, name_lookup: dict | None = None,
                    scoreboard=None, vision_desc: str | None = None) -> dict:
    """Preprocess extractor output: strip stats, filter placeholders, split merges."""
    if extracted.get("batters"):
        cleaned = []
        for b in extracted["batters"]:
            b["name"] = clean_player_name(b.get("name", ""))
            clean_batter_entry(b)
            if not _is_placeholder(b.get("name", "")):
                cleaned.append(b)
        extracted["batters"] = cleaned

    comms_frame = _has_commentary_context(vision_desc)
    stat_panel = _is_stat_panel(vision_desc)

    bw = extracted.get("bowler")
    if bw and isinstance(bw, dict):
        bw["name"] = clean_player_name(bw.get("name", ""))
        clean_bowler_entry(bw)
        # Sanity: if wickets > runs and wickets > 5, they're swapped
        bw_w = bw.get("wickets")
        bw_r = bw.get("runs")
        if (bw_w is not None and bw_r is not None
                and int(bw_w) > int(bw_r) and int(bw_w) > 5):
            bw["wickets"], bw["runs"] = bw_r, bw_w
        bw_name = bw.get("name", "")
        if _is_placeholder(bw_name):
            extracted["bowler"] = None
        elif _is_bowling_type_name(bw_name):
            log.info(f"[GUARD] '{bw_name}' is a bowling type, not a name")
            extracted["bowler"] = None
        elif stat_panel and scoreboard:
            resolved = scoreboard.resolve_name(bw_name)
            if not resolved:
                log.info(f"[GUARD] '{bw_name}' from stat panel — dropping")
                extracted["bowler"] = None
        elif comms_frame and scoreboard:
            resolved = scoreboard.resolve_name(bw_name)
            if not resolved:
                log.info(f"[GUARD] Bowler '{bw_name}' likely "
                         f"commentator — dropping")
                extracted["bowler"] = None

    if extracted.get("bowlers") and isinstance(extracted["bowlers"], list):
        cleaned_bowlers = []
        for b in extracted["bowlers"]:
            if isinstance(b, dict):
                b["name"] = clean_player_name(b.get("name", ""))
                clean_bowler_entry(b)
                b_name = b.get("name", "")
                if _is_placeholder(b_name):
                    continue
                if _is_bowling_type_name(b_name):
                    log.info(f"[GUARD] '{b_name}' is a bowling type, "
                             f"not a name — dropping")
                    continue
                if (stat_panel or comms_frame) and scoreboard:
                    resolved = scoreboard.resolve_name(b_name)
                    if not resolved:
                        log.info(f"[GUARD] Bowler '{b_name}' from "
                                 f"stat/comms panel — dropping")
                        continue
                cleaned_bowlers.append(b)
        extracted["bowlers"] = cleaned_bowlers

    if name_lookup and extracted.get("batters"):
        extracted["batters"] = split_merged_batters(
            extracted["batters"], name_lookup, scoreboard)
    normalize_extracted_batters(extracted, scoreboard)
    filter_bowler_batter_row_contamination(extracted, scoreboard)

    _clean_score_wickets(extracted)
    return extracted


def _clean_score_wickets(extracted: dict):
    """Always produce clean int score and int wickets from any format."""
    raw_score = extracted.get("score")
    raw_wickets = extracted.get("wickets")

    if raw_score is not None and "-" in str(raw_score):
        parts = str(raw_score).split("-")
        try:
            extracted["score"] = int(parts[0])
        except (ValueError, TypeError):
            extracted["score"] = None
        if raw_wickets is None and len(parts) > 1:
            try:
                extracted["wickets"] = int(parts[1])
            except (ValueError, TypeError):
                pass
    elif raw_score is not None:
        try:
            extracted["score"] = int(raw_score)
        except (ValueError, TypeError):
            extracted["score"] = None

    if extracted.get("wickets") is not None:
        try:
            extracted["wickets"] = int(extracted["wickets"])
        except (ValueError, TypeError):
            extracted["wickets"] = None


class ScoreJumpGuard:
    def __init__(self):
        self._pending_score: int | None = None
        self._pending_count = 0

    def check(self, old_score: int | None, new_score: int) -> bool:
        if old_score is None or old_score == 0:
            self._reset()
            return True
        jump = new_score - old_score
        if jump <= 7:
            self._reset()
            return True
        if jump < 0:
            self._reset()
            return False
        if self._pending_score == new_score:
            self._pending_count += 1
            if self._pending_count >= 2:
                log.info(f"Score jump {old_score}→{new_score} CONFIRMED")
                self._reset()
                return True
            log.info(f"Score jump {old_score}→{new_score} HOLD ({self._pending_count}/2)")
            return False
        log.info(f"Score jump {old_score}→{new_score} (+{jump}) HOLDING")
        self._pending_score = new_score
        self._pending_count = 1
        return False

    def _reset(self):
        self._pending_score = None
        self._pending_count = 0


def _project_active_batters(state: dict,
                            score_mgr,
                            scoreboard,
                            canon_fn) -> list:
    """Project striker / non into the WS payload `state`.

    SM is the sole authority for striker / non when in live mode
    (S1/S18 cutover, 2026-04-21).  This helper applies the canonical
    SM cutover write, then — if SM has cleared a slot to None during a
    mid-wicket-transition catch-up gap — falls back to `sb._inn`
    *provided* the value is currently in `active_batting` (i.e. not a
    stale dismissed-batter leftover from before the wicket cleared).

    Active-batting check is the safeguard against leaking dismissed
    names: when scout has detected a wicket and flipped a player's
    `batting_card[name].status` to "out", the player is excluded from
    `_active` and thus never surfaced via fallback even if `sb._inn`
    still holds them for a frame or two before its own update lands.

    Strengthened by Fix 5 (striker self-collision guard, same 2026-04-25
    inter-match bundle, `scoreboard.py:update_batter`): `sb._inn` is
    invariant-protected against `striker == non`, so this
    fallback can't surface a collided pair to the WS payload.  The
    `_other_slot` check below provides defence-in-depth for the
    payload-level analogue (one slot already SM-resolved, the other
    SM-null and falling back to a value matching the SM-resolved one).

    Args:
        state: payload state dict, mutated in place
        score_mgr: live ScoreManager instance (caller must gate on
            `not score_mgr.shadow`)
        scoreboard: live Scoreboard instance providing `_inn` and
            `batting_card`
        canon_fn: name canonicalizer (typically `_canon_player_name`),
            called for both SM and sb._inn values for consistency

    Returns:
        list of `(slot, sb_val)` tuples for each fallback that fired,
        for telemetry / logging.  Empty list when no fallback was
        needed (the common case once SM has caught up).
    """
    state["striker"] = canon_fn(score_mgr.striker)
    state["non"] = canon_fn(score_mgr.non)

    _bc = scoreboard.batting_card or {}
    # AUTHORITATIVE-BACKSTOP: WS projection fallback when SM slot null +
    # active batting (Fix 7). striker_path_b_read_audit.md R14 §2.2
    _sb = scoreboard._inn or {}
    _events = []
    for _slot in ("striker", "non"):
        if state.get(_slot) is not None:
            continue
        _sb_val = _sb.get(_slot)
        if not _sb_val:
            continue
        _card_key = (scoreboard.resolve_name(_sb_val)
                     if hasattr(scoreboard, "resolve_name") else _sb_val)
        _card = _bc.get(_card_key)
        if not _card or _card.get("status") != "batting":
            continue
        _other_slot = "non" if _slot == "striker" else "striker"
        if _card_key == state.get(_other_slot):
            continue
        state[_slot] = canon_fn(_card_key)
        _events.append((_slot, _card_key))
    return _events


def enforce_ws_slot_invariant(state: dict,
                              scoreboard,
                              canon_fn) -> bool:
    """Ensure WS striker/non never name the same active player."""
    striker = state.get("striker")
    non = state.get("non")
    if not striker or not non or striker != non:
        return False
    bc = getattr(scoreboard, "batting_card", None) or {}
    active = [name for name, card in bc.items()
              if card and card.get("status") == "batting"]
    duplicate = striker
    alternate = next((name for name in active if name != duplicate), None)
    if alternate:
        state["non"] = canon_fn(alternate)
        log.warn(
            f"  [WS-SLOT-INVARIANT] duplicate slots {duplicate!r}; "
            f"rebuilt non={alternate!r} from active card")
    else:
        state["non"] = None
        log.warn(
            f"  [WS-SLOT-INVARIANT] duplicate slots {duplicate!r}; "
            f"cleared non (no alternate active batter)")
    return True


# --- WS full-payload helpers (module-level; see
#     docs/investigations/build_full_payload_extraction_design.md)
_ws_scrub_counts: dict[str, int] = {}
_ws_scrub_consec: dict[str, int] = {}
_last_gap_sig: dict = {"sig": None}
_last_feeder_div_sig: dict = {"sig": None}


def _ws_canonicalize_player_name(raw, *, scoreboard, bowler: bool = False):
    """Resolve a raw scout name to its canonical squad key (WS boundary).

    Issue 1 defense-in-depth (2026-04-21).  SM canonicalizes at ingest;
    this is the second line at the WS boundary so raw surnames never leak.
    """
    if not raw:
        return raw
    try:
        resolved = scoreboard.resolve_name(raw)
        if not resolved:
            return raw
        card = (scoreboard.bowling_card if bowler
                else scoreboard.batting_card)
        if not card:
            return raw
        key = scoreboard._find_card_key(resolved, card)
        return key or raw
    except Exception:
        return raw


def _layer2_enqueue_blocked_absorbed(ball_event: dict | None) -> bool:
    """D2 — skip async delivery analysis for Policy U absorbed events."""
    if not ball_event:
        return False
    if ball_event.get("absorbed"):
        log.debug(
            f"  [LAYER2-SKIP-ABSORBED] type={ball_event.get('type')!r}")
        return True
    return False


def _assert_ws_payload_invariants(payload: dict, *, log) -> None:
    """Log-only invariant checks on the WS payload shape."""
    try:
        sc = payload.get("scorecard") or {}
        striker = sc.get("striker")
        if striker and "batting_card" in payload:
            card_names = {
                b.get("name") for b in (payload.get("batting_card") or [])
            }
            if card_names and striker not in card_names:
                log.warn(
                    f"  [INVARIANT] striker='{striker}' not in "
                    f"batting_card names="
                    f"{sorted(n for n in card_names if n)}"
                )
        if "batting_card" in payload:
            _out_set = {
                b.get("name") for b in (payload.get("batting_card") or [])
                if b.get("status") == "out"
            }
            for _slot in ("striker", "non"):
                _nm = sc.get(_slot)
                if _nm and _nm in _out_set:
                    log.warn(
                        f"  [INVARIANT] {_slot}='{_nm}' is "
                        f"dismissed in batting_card")
        for fow in (payload.get("fall_of_wickets") or []):
            batter = fow.get("batter")
            is_placeholder = (batter is None
                              or (isinstance(batter, str)
                                  and batter.lower() in {"unknown", "?"}))
            if is_placeholder and not fow.get("_unwitnessed"):
                log.warn(
                    f"  [INVARIANT] FOW placeholder missing "
                    f"_unwitnessed=True: {fow}"
                )
    except Exception:
        pass


def _record_state_recovery_ws_guard(
        family: str,
        proposed_reset: list[str] | None,
        *,
        state_recovery,
        score_mgr,
        scoreboard,
        frame_count: int,
        frame_candidate,
        current,
        suppressed: bool,
        log) -> None:
    event = state_recovery.observe(
        frame_count, family, frame_candidate,
        current=current,
        proposed_reset=proposed_reset,
        suppressed=suppressed)
    if event:
        log.warn(_format_state_recovery_event(event))
        _apply_state_recovery_phase2_mutation(
            event, score_mgr, scoreboard, state_recovery)


def project_fow_for_payload(fow_list: list[dict]) -> tuple[list[dict], int]:
    """Render every FOW row to UI; unwitnessed placeholders surface
    as "?/TBD" so the wicket count and the visible list never diverge,
    and we don't back-fill a previous wicket's batter name into a slot
    we never observed."""
    visible = []
    for w in fow_list or []:
        batter = w.get("batter")
        is_placeholder = (
            batter is None
            or (isinstance(batter, str)
                and batter.lower() in {"unknown", "?"}))
        unwitnessed = bool(w.get("_unwitnessed"))
        if unwitnessed and is_placeholder:
            visible.append({
                "wicket": w.get("wicket"),
                "batter": "?",
                "score": w.get("score"),
                "overs": w.get("overs"),
                "bowler": w.get("bowler") or "TBD",
                "how": w.get("how") or "TBD",
                "_unwitnessed": True,
            })
            continue
        visible.append({
            "wicket": w.get("wicket"),
            "batter": batter,
            "score": w.get("score"),
            "overs": w.get("overs"),
            "bowler": w.get("bowler"),
            "how": w.get("how"),
            "_unwitnessed": unwitnessed,
        })
    return visible, len(fow_list or [])


def _active_card_name(scoreboard, name: str | None) -> str | None:
    if not name or not scoreboard:
        return None
    card_key = (scoreboard.resolve_name(name)
                if hasattr(scoreboard, "resolve_name") else name)
    if not card_key:
        return None
    card = (getattr(scoreboard, "batting_card", {}) or {}).get(card_key)
    return card_key if card and card.get("status") == "batting" else None


def _canonical_active_slot(score_mgr, scoreboard, slot: str) -> str | None:
    """Read active slots from SM first; sb._inn is projection fallback."""
    # AUTHORITATIVE-BACKSTOP: SM-first; _inn only when SM empty/non-batting
    # (Cluster 1 helper by design). striker_path_b_read_audit.md R13 §2.2
    sm_val = getattr(score_mgr, slot, None) if score_mgr else None
    sm_key = _active_card_name(scoreboard, sm_val)
    if sm_key:
        return sm_key
    sb = getattr(scoreboard, "_inn", None) or {}
    return _active_card_name(scoreboard, sb.get(slot))


def _set_inn_slot_with_sm_mirror(score_mgr, scoreboard, slot: str,
                                 value: str | None, reason: str) -> bool:
    """Path B lockstep: mirror striker/non into ``sb._inn`` and SM.

    Both stores stay aligned for readers that still consult legacy
    projection.  Does not remove Fix 5 collision guards inside
    ``update_batter`` (defense in depth).
    """
    if not scoreboard or not getattr(scoreboard, "_inn", None):
        return False
    if slot not in ("striker", "non"):
        return False
    scoreboard._inn[slot] = value
    if score_mgr is not None:
        setattr(score_mgr, slot, value)
    log.info(
        f"  [STRIKER-SM-CUTOVER] mirrored {slot}={value!r} "
        f"reason={reason} — SM+_inn lockstep")
    return True


def _set_legacy_active_slot(score_mgr, scoreboard, slot: str,
                            value: str | None, reason: str) -> bool:
    """Delegate to Path B SM+_inn mirror (Cluster 1 completion)."""
    return _set_inn_slot_with_sm_mirror(
        score_mgr, scoreboard, slot, value, reason)


def _pr3_batter_arrival_slot_cutover(
        score_mgr, scoreboard, admitted_batter_key: str) -> None:
    """Lever 1 PR3 Part 2: lockstep SM+`_inn` when a new batter is admitted.

    Called from the `[REPLACE]` path after ``update_batter`` accepts a
    ``yet_to_bat → batting`` transition.  Repairs slots that still hold a
    dismissed name (edge cases where Part 1 guard did not run).
    """
    if not score_mgr or not scoreboard or not admitted_batter_key:
        return
    _bcard = scoreboard.batting_card or {}

    def _is_card_out(name: str | None) -> bool:
        if not name:
            return False
        ent = _bcard.get(name)
        return bool(ent and ent.get("status") == "out")

    if _is_card_out(score_mgr.non):
        _set_legacy_active_slot(
            score_mgr, scoreboard, "non",
            admitted_batter_key, "batter-arrival")
    elif _is_card_out(score_mgr.striker):
        _set_legacy_active_slot(
            score_mgr, scoreboard, "striker",
            admitted_batter_key, "batter-arrival")


def _apply_scorer_item2_cleanup(
        schema_shadow_events: list,
        step3_notes: list[tuple[str, str]],
        step4_ub_false: set[str],
        scoreboard,
        score_mgr,
        frame: int,
        changes: list) -> None:
    """Item 2 PR 1: shadow schema telemetry + ``[BATTERS-INVARIANT]`` backstop."""
    if schema_shadow_events and not SCORER_SCHEMA_ENFORCE:
        finalize_schema_shadow_logs(
            schema_shadow_events,
            frame=frame,
            log=log,
            step3_notes=step3_notes,
            changes=changes,
        )
    if scoreboard is not None:
        _batters_invariant_backstop(
            scoreboard, score_mgr, frame, changes,
            step3_notes, step4_ub_false,
        )


def _batters_invariant_backstop(
        scoreboard,
        score_mgr,
        frame: int,
        changes: list,
        step3_notes: list[tuple[str, str]],
        step4_ub_false: set[str],
) -> None:
    """§10.1 / §10.4 — WARN-only; autocorrect gated (default off)."""
    active = [
        n for n, s in scoreboard.batting_card.items()
        if s.get("status") == "batting"
    ]
    active_s = ",".join(active) if active else "-"
    w_out = [
        n for n in active
        if hasattr(scoreboard, "_is_witnessed_dismissal")
        and scoreboard._is_witnessed_dismissal(n)
    ]
    wo_s = ",".join(w_out) if w_out else "-"
    st = (_canonical_active_slot(score_mgr, scoreboard, "striker")
          if score_mgr or scoreboard else None)
    ns = (_canonical_active_slot(score_mgr, scoreboard, "non")
          if score_mgr or scoreboard else None)
    violations: list[tuple[str, str, str]] = []
    if len(active) > 2:
        violations.append(("A", "active_set_max_two", active_s))
    for n in w_out:
        violations.append(("B", "witnessed_in_active", n))
    if st:
        c = scoreboard.batting_card.get(st)
        if not c or c.get("status") != "batting":
            violations.append(("C", "striker_card_not_batting", st))
    if ns:
        c = scoreboard.batting_card.get(ns)
        if not c or c.get("status") != "batting":
            violations.append(("C", "non_card_not_batting", ns))
    if st and ns and st == ns:
        violations.append(("C", "striker_non_collision", st))

    if not violations:
        return

    tags = sorted({t for t, _ in step3_notes})
    tags_s = ",".join(tags) if tags else "-"
    step3_fired = "true" if step3_notes else "false"
    step4_false = "true" if step4_ub_false else "false"

    for rule, viol, target in violations:
        action = (
            "noop_phase1" if not BATTERS_INVARIANT_AUTOCORRECT
            else "auto_correct_deferred")
        log.warn(
            f"  [BATTERS-INVARIANT] rule={rule} violation={viol} "
            f"active={active_s} witnessed_out={wo_s} "
            f"striker={st or 'None'} non={ns or 'None'} "
            f"upstream_step3_fired={step3_fired} "
            f"upstream_step3_tags={tags_s} "
            f"upstream_step4_returned_false={step4_false} "
            f"action={action} target={target} frame=F{frame}"
        )

    if not BATTERS_INVARIANT_AUTOCORRECT:
        return
    # Phase 2 — reserved: demote / force_out / clear_slot per §10.1
    _ = changes


def _scorer_batter_update_allowed(scoreboard, name: str,
                                  frame: int,
                                  step3_notes: list | None = None) -> bool:
    """Pre-commit SCORER gate for witnessed dismissed batters."""
    card_key = (scoreboard.resolve_name(name)
                if hasattr(scoreboard, "resolve_name") else name)
    if card_key and hasattr(scoreboard, "_is_witnessed_dismissal"):
        if scoreboard._is_witnessed_dismissal(card_key):
            log.warn(
                f"  [SCORER-ACTIVE-GATE] rejecting batter update for "
                f"witnessed-out batter '{card_key}' at F{frame}")
            if step3_notes is not None:
                step3_notes.append(("SCORER-ACTIVE-GATE", card_key))
            return False
    return True


def _scorer_batter_row_is_dismissed_resurrection(
        scoreboard, name: str, frame: int,
        step3_notes: list | None = None) -> bool:
    """True if scorer proposes an update for a batter already marked out.

    Filters before ``update_batter`` so non-witnessed dismissals are not
    resurrected by LLM slates.  Witnessed outs log [SCORER-INVARIANT-
    FILTER]; stale ``out`` rows without FOW witness log
    [SCORER-DISMISSED-RESURRECT].
    """
    if not scoreboard or not getattr(scoreboard, "batting_card", None):
        return False
    resolved = (scoreboard.resolve_name(name)
                if hasattr(scoreboard, "resolve_name") else name)
    if not resolved:
        return False
    ck = scoreboard._find_card_key(resolved, scoreboard.batting_card)
    if not ck:
        return False
    card = scoreboard.batting_card.get(ck)
    if not card or card.get("status") != "out":
        return False
    if (hasattr(scoreboard, "_is_witnessed_dismissal")
            and scoreboard._is_witnessed_dismissal(ck)):
        log.info(
            f"  [SCORER-INVARIANT-FILTER] skipping batter_updates row "
            f"for witnessed-out '{ck}' at F{frame}")
        if step3_notes is not None:
            step3_notes.append(("SCORER-INVARIANT-FILTER", ck))
        return True
    log.warn(
        f"  [SCORER-DISMISSED-RESURRECT] skipping scorer proposal for "
        f"non-witnessed-out '{ck}' at F{frame}")
    if step3_notes is not None:
        step3_notes.append(("SCORER-DISMISSED-RESURRECT", ck))
    return True


def _sr_int(value) -> int | None:
    try:
        if value is None:
            return None
        return int(str(value).split("-")[0])
    except (TypeError, ValueError):
        return None


def _sr_float(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _sr_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _build_state_recovery_candidate(extracted: dict | None,
                                    scoreboard=None) -> dict:
    """Candidate state snapshot before guard stripping."""
    extracted = extracted or {}
    card = getattr(scoreboard, "batting_card", {}) if scoreboard else {}
    candidate: dict = {}

    score = _sr_int(extracted.get("score"))
    wickets = _sr_int(extracted.get("wickets"))
    overs = _sr_float(extracted.get("match_overs"))
    if score is not None:
        candidate["score"] = score
    if wickets is not None:
        candidate["wickets"] = wickets
    if overs is not None:
        candidate["overs"] = overs

    batters = []
    for row in extracted.get("batters") or []:
        raw_name = row.get("name")
        if not raw_name:
            continue
        resolved = None
        if scoreboard is not None:
            try:
                resolved = scoreboard.resolve_name(raw_name)
            except Exception:
                resolved = None
        name = resolved or raw_name
        card_row = card.get(name) or {}
        runs = _sr_int(row.get("runs"))
        balls = _sr_int(row.get("balls"))
        batters.append({
            "name": name,
            "runs": runs,
            "balls": balls,
            "status": card_row.get("status"),
            "status_update": (
                card_row.get("status") in (None, "yet_to_bat")),
        })
    if batters:
        candidate["batters"] = batters
        candidate["active_batters"] = [b["name"] for b in batters[:2]]
        if all(b.get("runs") is not None for b in batters):
            candidate["bat_sum"] = sum(int(b["runs"]) for b in batters)

    return candidate


def _build_state_recovery_current(scoreboard=None) -> dict:
    # AUTHORITATIVE-SBINN-READ: aggregator must see legacy projection drift
    # vs evidence, not SM. striker_path_b_read_audit.md R15 §2.1.4
    inn = getattr(scoreboard, "_inn", None) or {}
    return {
        "score": _sr_int(inn.get("score")),
        "wickets": _sr_int(inn.get("wickets")),
        "overs": _sr_float(inn.get("overs")),
        "striker": inn.get("striker"),
        "non": inn.get("non"),
    }


class StateRecoveryAggregator:
    """Telemetry-first multi-guard state-recovery consensus detector.

    Architectural contract:
    - Every guard that detects a stale-reference deadlock eventually
      needs release semantics, but a single guard family is too noisy
      to mutate state safely.
    - Require two independent guard families plus candidate-internal
      coherence so persistent OCR/stat-graphic noise does not become a
      recovery path.
    - Phase 1 is telemetry-only. Phase 2 must reset ScoreManager via
      ``ScoreManager.full_reset()`` (cold-start re-entry **plus** full
      Fix-16 per-innings scalar wipe).  ``force_cold_start_recalibration()``
      alone is insufficient and must not be the sole SM reset in Phase 2.
    """

    def __init__(self, threshold: int = 5,
                 min_guard_families: int = 2,
                 telemetry_only: bool = True):
        self.threshold = threshold
        self.min_guard_families = min_guard_families
        self.telemetry_only = telemetry_only
        self.reset()

    def reset(self, reason: str | None = None) -> None:
        self._sig: str | None = None
        self._count = 0
        self._start_frame: int | None = None
        self._last_frame: int | None = None
        self._families: set[str] = set()
        self._candidate: dict = {}
        self._coherence_checks: dict = {}
        self._current: dict = {}
        self._proposed_reset: set[str] = set()
        self._last_reset_reason = reason

    def observe(self, frame: int, family: str, candidate: dict | None,
                *, current: dict | None = None,
                proposed_reset: list[str] | None = None,
                suppressed: bool = False) -> dict | None:
        if suppressed:
            self.reset("suppressed_window")
            return None
        if not candidate or candidate.get("single_batter_field_only"):
            return None
        coherent, coherence = self._check_coherence(candidate)
        if not coherent:
            self.reset("incoherent_candidate")
            return None

        sig = self._signature(candidate)
        if sig != self._sig:
            self._sig = sig
            self._count = 1
            self._start_frame = frame
            self._last_frame = frame
            self._families = {family}
            self._candidate = dict(candidate)
            self._coherence_checks = coherence
            self._current = dict(current or {})
            self._proposed_reset = set(proposed_reset or [])
            return None

        if frame != self._last_frame:
            self._count += 1
            self._last_frame = frame
        self._families.add(family)
        self._current = dict(current or self._current or {})
        self._proposed_reset.update(proposed_reset or [])

        if (self._count >= self.threshold
                and len(self._families) >= self.min_guard_families):
            event = {
                "sig": self._sig[:12],
                "guards": sorted(self._families),
                "frames": self._count,
                "candidate": dict(self._candidate),
                "current": dict(self._current),
                "proposed_reset": sorted(self._proposed_reset),
                "coherence": dict(self._coherence_checks),
                "threshold_frames": self._threshold_frames(),
                "reason": "stale_reference_state",
                "telemetry_only": self.telemetry_only,
            }
            self.reset("candidate_emitted")
            return event
        return None

    def _signature(self, candidate: dict) -> str:
        return hashlib.sha1(_sr_json(candidate).encode("utf-8")).hexdigest()

    def _threshold_frames(self) -> dict:
        start = self._start_frame
        if start is None:
            return {"n3": None, "n5": None, "n8": None}
        return {
            "n3": start + 2 if self._count >= 3 else None,
            "n5": start + 4 if self._count >= 5 else None,
            "n8": start + 7 if self._count >= 8 else None,
        }

    def _check_coherence(self, candidate: dict) -> tuple[bool, dict]:
        score = candidate.get("score")
        wickets = candidate.get("wickets")
        overs = candidate.get("overs")
        checks = {
            "score_non_negative": True,
            "wickets_t20": True,
            "overs_t20": True,
            "active_batters_max_two": True,
            "batters_known_not_out": True,
            "bat_sum_within_score": True,
        }
        if score is not None and int(score) < 0:
            checks["score_non_negative"] = False
        if wickets is not None and not (0 <= int(wickets) <= 10):
            checks["wickets_t20"] = False
        if overs is not None and not (0 <= float(overs) <= 20):
            checks["overs_t20"] = False

        batters = candidate.get("batters") or []
        if len(candidate.get("active_batters") or []) > 2:
            checks["active_batters_max_two"] = False
        for batter in batters:
            if not batter.get("name"):
                checks["batters_known_not_out"] = False
            if (batter.get("status") == "out"
                    and not batter.get("status_update")):
                checks["batters_known_not_out"] = False

        bat_sum = candidate.get("bat_sum")
        if score is not None and bat_sum is not None:
            if int(bat_sum) > int(score) + 12:
                checks["bat_sum_within_score"] = False
        return all(checks.values()), checks


def _format_state_recovery_event(event: dict,
                                 *, actual: bool = False) -> str:
    tag = ("STATE-RECOVERY-OVERRIDE" if actual
           else "STATE-RECOVERY-OVERRIDE-CANDIDATE")
    return (
        f"  [{tag}] sig={event.get('sig')} "
        f"guards={','.join(event.get('guards') or [])} "
        f"frames={event.get('frames')} "
        f"candidate_json={_sr_json(event.get('candidate') or {})} "
        f"current_json={_sr_json(event.get('current') or {})} "
        f"coherence_json={_sr_json(event.get('coherence') or {})} "
        f"thresholds_json={_sr_json(event.get('threshold_frames') or {})} "
        f"proposed_reset={','.join(event.get('proposed_reset') or []) or '-'} "
        f"reason={event.get('reason', 'unknown')} "
        f"telemetry_only={str(event.get('telemetry_only', True)).lower()}"
    )


def _apply_state_recovery_phase2_mutation(
        event: dict,
        score_mgr,
        scoreboard,
        aggregator: StateRecoveryAggregator,
) -> None:
    """Apply Phase 2 mutation when ``STATE_RECOVERY_PHASE_2_ENABLED``.

    Phase 1 always logs the candidate first (caller).  Suppression for
    innings transitions / cold-start remains in ``observe(..., suppressed=)``.
    """
    if not STATE_RECOVERY_PHASE_2_ENABLED:
        return
    if score_mgr is None or scoreboard is None:
        log.warn(
            "  [STATE-RECOVERY-OVERRIDE] missing score_mgr/scoreboard "
            "— skipping Phase 2 mutation")
        return
    log.warn(_format_state_recovery_event(event, actual=True))
    try:
        score_mgr.full_reset(reason="state_recovery_consensus_override")
    except Exception as e:  # noqa: BLE001
        log.warn(f"  [STATE-RECOVERY-OVERRIDE] full_reset failed: {e}")
        return
    cand = event.get("candidate") or {}
    if cand.get("score") is not None:
        scoreboard._inn["score"] = int(cand["score"])
    if cand.get("wickets") is not None:
        scoreboard._inn["wickets"] = int(cand["wickets"])
    if cand.get("overs") is not None:
        ov = cand["overs"]
        scoreboard._inn["overs"] = (
            str(int(ov))
            if isinstance(ov, float) and ov == float(int(ov))
            else str(ov))
    aggregator.reset("phase2_mutation_applied")


def _score_inf_floor_components(scoreboard) -> tuple[int, int, bool]:
    """Return ``(bat_sum, extras_total, complete)`` for Layer 1.5 floor gate.

    ``bat_sum`` is the sum of ``runs`` across batting-card rows in
    ``batting`` or ``out`` status.  ``extras_total`` is
    ``scoreboard.extras['total']`` (0 if missing).  ``complete`` is
    False when any counted row lacks runs (transient card state) —
    callers must abstain from the floor check.
    """
    try:
        bc = scoreboard.batting_card
    except AttributeError:
        return (0, 0, False)
    bat_sum = 0
    for _c in bc.values():
        st = _c.get("status")
        if st not in ("batting", "out"):
            continue
        r = _c.get("runs")
        if r is None:
            return (0, 0, False)
        try:
            bat_sum += int(r)
        except (ValueError, TypeError):
            return (0, 0, False)
    try:
        ext = getattr(scoreboard, "extras", None) or {}
        if isinstance(ext, dict) and ext.get("total") is not None:
            extras_total = int(ext["total"])
        else:
            extras_total = 0
    except (ValueError, TypeError):
        return (0, 0, False)
    return (bat_sum, extras_total, True)


_DEFAULT_STRIP_OVERLAY_SENTINELS: tuple[str, ...] = (
    " > ",
    "RUN-RATE",
    "RUN RATE",
    "Run-Rate",
    "SPEED ",
    " kph",
    "CAREER",
    "BEST",
    "AVG",
    "STRIKE-RATE",
    "STRIKE RATE",
    "IN T20",
    "IN IPL",
    " vs ",
    "this season",
)


def _strip_overlay_sentinels() -> tuple[str, ...]:
    raw = os.environ.get("STRIP_OVERLAY_SENTINELS")
    if not raw:
        return _DEFAULT_STRIP_OVERLAY_SENTINELS
    parts = tuple(s for s in (p.strip() for p in raw.split(",")) if s)
    return parts or _DEFAULT_STRIP_OVERLAY_SENTINELS


_CROSS_MATCH_NUMBER_RE = re.compile(r"\bMATCH\s+(\d+)\b", re.IGNORECASE)


def _parse_current_match_number(match_info: str | None) -> int | None:
    """Extract the integer match number from broadcast-cache ``match_info``.

    Source: ``_broadcast_cache['match_info']`` populated by
    ``_MATCH_INFO_PATTERNS`` (~line 1504) from broadcast OCR. Returns
    ``None`` when the field is absent or holds a non-numeric variant
    (e.g., ``"FIRST T20I"``, ``"IPL 2026"``).
    """
    if not match_info:
        return None
    m = _CROSS_MATCH_NUMBER_RE.search(match_info)
    if not m:
        m = re.search(r"\b(\d+)(?:st|nd|rd|th)\b", match_info, re.IGNORECASE)
    if not m:
        return None
    try:
        return int(m.group(1))
    except (TypeError, ValueError):
        return None


def _detect_overlay_strip_sentinels(
        scout_strip_text: str | None,
        current_match_number: int | None = None) -> str | None:
    """Return matched sentinel keyword or ``None``.

    Comparison / career-stat overlays leak text patterns that do not
    appear on a normal live strip (head-to-head ``>``, ``RUN-RATE``,
    ``SPEED kph``, career qualifiers like ``IN T20``).  If any sentinel
    substring is present in scout text, treat the frame as an overlay.

    Cross-match check: when ``current_match_number`` is provided and the
    strip text mentions a different ``MATCH NN``, treat as overlay
    (broadcast feature card sourced from another match — e.g. Holder's
    GT-RCB stat card during GT-PBKS, 2026-05-03).
    """
    if not scout_strip_text:
        return None
    for s in _strip_overlay_sentinels():
        if s in scout_strip_text:
            return s
    if current_match_number is not None:
        m = _CROSS_MATCH_NUMBER_RE.search(scout_strip_text)
        if m:
            try:
                other = int(m.group(1))
            except (TypeError, ValueError):
                other = None
            if other is not None and other != current_match_number:
                return f"MATCH {other}"
    return None


_OVERLAY_SECONDARY_CUE_CAMS = frozenset({"graphic", "replay", "ad"})

# Batch G (2026-05-04): consecutive-identical-rejection lockout breakout.
# When the active-batting branch of the overlay detector rejects the
# same (strip_pair, active_pair) tuple K times in a row, the active set
# is treated as stale and the strip is allowed through.  Genuine
# overlays are ephemeral and do not repeat unchanged for K frames;
# sustained streaks therefore signal a state-desync lockout rather than
# a real overlay.  See
# files/docs/investigations/strip_overlay_detected_false_positive.md.
_OVERLAY_LOCKOUT_BREAKOUT_K = 3
_overlay_lockout_state: dict = {
    "last_pair": None,
    "last_active": None,
    "consecutive": 0,
}


def reset_overlay_lockout_state() -> None:
    _overlay_lockout_state["last_pair"] = None
    _overlay_lockout_state["last_active"] = None
    _overlay_lockout_state["consecutive"] = 0


def _detect_overlay_via_active_batting(
        extracted_batters: list | None,
        scoreboard,
        *,
        cam: str | None = None,
        frame_class: str | None = None) -> bool:
    """Return ``True`` when NEITHER strip batter resolves to an
    actively-batting card row AND a secondary overlay cue is present.

    Skips (returns ``False``) during cold-start when no card row is in
    ``batting`` status, since there is no ground truth to test against.

    Active-batting mismatch alone is too weak to classify a strip read
    as overlay: post-wicket transitions create stale-active-set lockouts
    where the only signal capable of correcting active is the strip read
    itself.  A secondary cue — non-``SCOREBOARD`` frame class or a
    cam value typical of overlay/cutaway frames — is required.
    """
    if not extracted_batters:
        return False
    try:
        bc = scoreboard.batting_card or {}
    except AttributeError:
        return False
    active = {n for n, c in bc.items() if c.get("status") == "batting"}
    if not active:
        return False
    secondary_cue = (
        (frame_class is not None and frame_class != "SCOREBOARD")
        or cam in _OVERLAY_SECONDARY_CUE_CAMS)
    if not secondary_cue:
        return False
    for be in extracted_batters:
        if not isinstance(be, dict):
            continue
        name = (be.get("name") or "").strip()
        if not name:
            continue
        resolved = scoreboard.resolve_name(name)
        if resolved and resolved in active:
            return False
    return True


def filter_off_roster_batter_rows(
        extracted: dict,
        scoreboard,
        batting_team: str | None,
        *,
        frame_count: int,
) -> bool:
    """Drop strip ``batters`` rows whose names don't resolve into the
    batting team's XI.  Per-row, non-poisoning: surviving rows commit
    normally; ``score``, ``match_overs``, and ``bowler`` are untouched.

    Scout occasionally hallucinates an opposing-team or off-roster
    name into a strip row (MI vs LSG F205 [Inglis, KL Rahul], F156
    [Samad, Shahbaz], F289 [Suryakumar, Rohit]).  Whole-frame
    rejection here would lose score/overs/bowler that the strip OCR'd
    correctly; the existing batting-squad guard (downstream) only
    fires when *all* names mismatch, leaving partial-hallucination
    cases (1/2 names off-roster) to poison the card via the row-delta
    guard.  This filter removes only the bad rows and lets the rest
    of the frame commit.

    Returns True when at least one row was dropped.
    """
    if not (extracted.get("batters") and scoreboard.batting_card
            and batting_team):
        return False
    filtered: list = []
    dropped: list[str] = []
    for row in extracted["batters"]:
        if not isinstance(row, dict):
            continue
        name = (row.get("name") or "").strip()
        resolved = scoreboard.resolve_name(name) if name else None
        if resolved and resolved in scoreboard.batting_card:
            filtered.append(row)
        else:
            dropped.append(name or "<empty>")
    if not dropped:
        return False
    extracted["batters"] = filtered
    log.warn(
        f"  [OFF-ROSTER-BATTER-REJECT] frame=F{frame_count} "
        f"dropped={dropped} kept={[r.get('name') for r in filtered]} "
        f"poison=none")
    return True


def filter_strip_stale_dismissed(
        extracted: dict,
        scoreboard,
        *,
        frame_count: int,
) -> bool:
    """DC-vs-CSK Fix 7: pop the entire ``batters`` list when any row
    names a batter the scoreboard already shows ``status=out``.

    The strip occasionally re-shows the just-dismissed batter for a
    handful of frames after the wicket falls; downstream
    ``WS-SCRUB`` repaired the slot but only after the dismissed name
    had already entered the striker assignment path. Rejecting at the
    strip-read boundary collapses the SCORER-DISMISSED-RESURRECT
    cascade and short-circuits the WS-SCRUB load.
    """
    batters = extracted.get("batters")
    if not batters or not getattr(scoreboard, "batting_card", None):
        return False
    dismissed_hits: list[tuple[str, dict | None]] = []
    for row in batters:
        if not isinstance(row, dict):
            continue
        name = (row.get("name") or "").strip()
        if not name:
            continue
        resolved = (scoreboard.resolve_name(name)
                    if hasattr(scoreboard, "resolve_name") else name)
        card = (scoreboard.batting_card or {}).get(resolved or name)
        if card and card.get("status") == "out":
            fow = None
            for w in (getattr(scoreboard, "fall_of_wickets", None) or []):
                if w.get("batter") == (resolved or name):
                    fow = w
                    break
            dismissed_hits.append((resolved or name, fow))
    if not dismissed_hits:
        return False
    for name, fow in dismissed_hits:
        log.warn(
            f"  [STRIP-STALE-DISMISSED] frame=F{frame_count} "
            f"batter={name!r} dismissed_at_fow="
            f"{(fow or {}).get('overs', '?')}")
    extracted.pop("batters", None)
    return True


_IPL_TEAM_ABBREV_MAP = {
    "csk": "chennai super kings",
    "dc": "delhi capitals",
    "mi": "mumbai indians",
    "pbks": "punjab kings",
    "rcb": "royal challengers bengaluru",
    "rr": "rajasthan royals",
    "kkr": "kolkata knight riders",
    "lsg": "lucknow super giants",
    "srh": "sunrisers hyderabad",
    "gt": "gujarat titans",
}


def _team_names_match(a: str, b: str) -> bool:
    a_lower = a.lower().strip()
    b_lower = b.lower().strip()
    if not a_lower or not b_lower:
        return False
    if a_lower == b_lower:
        return True
    if a_lower in b_lower or b_lower in a_lower:
        return True
    a_full = _IPL_TEAM_ABBREV_MAP.get(a_lower, a_lower)
    b_full = _IPL_TEAM_ABBREV_MAP.get(b_lower, b_lower)
    if a_full == b_full or a_full in b_full or b_full in a_full:
        return True
    return False


def filter_strip_wrong_team(
        visible_team: str | None,
        batting_team: str | None,
        our_teams: list[str] | None,
        innings: int,
        frame_count: int) -> bool:
    """Reject scoreboard reads that don't belong to our match.

    Vision is the source of truth for live state (team/score/overs/etc.).
    The only squad-side input we use is ``our_teams`` — the two team
    names from the squad-data scrape (cricbuzz, replaceable) which
    define the set of acceptable batting-team labels for this match.
    Batting team is NOT pre-set from toss data; pipeline derives it
    from consistent Vision reads instead.

    Cases:
      * innings not yet started → no guard (pre-match graphics expected).
      * visible_team is null → reject (live scoreboard banner ALWAYS
        carries a team token; null = recap / graphic / degraded read).
      * visible_team is not one of ``our_teams`` (e.g. "MI" during a
        PBKS vs DC match) → reject (foreign-match recap overlay).
      * batting_team already locked from prior reads AND visible_team
        doesn't match it → reject (cross-innings overlay).
    """
    if innings is None or innings < 1:
        return False
    if not visible_team:
        log.warn(
            f"  [STRIP-WRONG-TEAM] frame=F{frame_count} "
            f"visible=None — strip read rejected (no team confirmation)")
        return True
    if our_teams:
        in_match = any(_team_names_match(visible_team, t) for t in our_teams)
        if not in_match:
            log.warn(
                f"  [STRIP-WRONG-TEAM] frame=F{frame_count} "
                f"visible={visible_team!r} not in match teams {our_teams!r} "
                f"— foreign-match recap rejected")
            return True
    if not batting_team:
        return False
    if _team_names_match(visible_team, batting_team):
        return False
    log.warn(
        f"  [STRIP-WRONG-TEAM] frame=F{frame_count} "
        f"visible={visible_team!r} batting={batting_team!r} "
        f"— strip read rejected")
    return True


def apply_strip_overlay_prefilters(
        extracted: dict,
        scoreboard,
        scout_strip_text: str | None,
        *,
        frame_count: int,
        record_state_recovery_guard,
        current_match_number: int | None = None,
        cam: str | None = None,
        frame_class: str | None = None,
        batting_team: str | None = None,
        our_teams: list[str] | None = None,
) -> bool:
    """Stack of pre-filters that pop ``batters`` when the scout reading
    is an overlay graphic rather than the live strip.

    Runs BEFORE :func:`apply_comparison_strip_batter_row_delta_guard`,
    which becomes the residual backstop.  Returns ``True`` when batters
    were popped.
    """
    if not extracted.get("batters"):
        return False
    if filter_strip_stale_dismissed(
            extracted, scoreboard, frame_count=frame_count):
        record_state_recovery_guard(
            "batter_row_rejected",
            proposed_reset=["bat:strip_stale_dismissed"])
        return True
    if filter_strip_wrong_team(
            visible_team=extracted.get("batting_team_visible"),
            batting_team=batting_team,
            our_teams=our_teams,
            innings=getattr(scoreboard, "current_innings", 0) or 0,
            frame_count=frame_count):
        record_state_recovery_guard(
            "batter_row_rejected",
            proposed_reset=["bat:strip_wrong_team"])
        # Wrong team on strip → entire frame is from a recap/overlay,
        # not the live match. Pop ALL state-bearing fields so score,
        # overs, wickets, bowler stats etc. from the recap graphic
        # don't pollute consensus.  (Was only popping batters; phantom
        # MI 110-4 reads of past-match recap graphics were leaking
        # score/overs through during PBKS vs DC on 2026-05-11.)
        for _k in ("batters", "bowlers", "score", "wickets", "overs",
                   "extras", "this_over", "target", "fall_of_wickets",
                   "run_rate", "partnership"):
            extracted.pop(_k, None)
        return True
    sentinel = _detect_overlay_strip_sentinels(
        scout_strip_text, current_match_number=current_match_number)
    if sentinel:
        record_state_recovery_guard(
            "batter_row_rejected",
            proposed_reset=["bat:overlay_sentinel"])
        log.warn(
            f"  [STRIP-OVERLAY-DETECTED] frame=F{frame_count} "
            f"reason=sentinel sentinel={sentinel!r} "
            f"popped=batters")
        extracted.pop("batters", None)
        return True
    if _detect_overlay_via_active_batting(
            extracted.get("batters"), scoreboard,
            cam=cam, frame_class=frame_class):
        _names = [(b.get("name") or "")
                  for b in extracted["batters"] if isinstance(b, dict)]
        try:
            bc = scoreboard.batting_card or {}
        except AttributeError:
            bc = {}
        active_pair = tuple(sorted(
            n for n, c in bc.items() if c.get("status") == "batting"))
        strip_pair = tuple(sorted(_names))
        st = _overlay_lockout_state
        if (strip_pair == st["last_pair"]
                and active_pair == st["last_active"]):
            st["consecutive"] += 1
        else:
            st["last_pair"] = strip_pair
            st["last_active"] = active_pair
            st["consecutive"] = 1
        if st["consecutive"] >= _OVERLAY_LOCKOUT_BREAKOUT_K:
            log.warn(
                f"  [OVERLAY-LOCKOUT-BREAKOUT] frame=F{frame_count} "
                f"strip_batters={list(strip_pair)} "
                f"active={list(active_pair)} "
                f"consecutive={st['consecutive']} "
                f"force-updating active set (no pop)")
            reset_overlay_lockout_state()
            return False
        record_state_recovery_guard(
            "batter_row_rejected",
            proposed_reset=["bat:not_in_active_batting"])
        log.warn(
            f"  [STRIP-OVERLAY-DETECTED] frame=F{frame_count} "
            f"reason=active_batting strip_batters={_names} "
            f"popped=batters")
        extracted.pop("batters", None)
        return True
    reset_overlay_lockout_state()
    return False


def apply_comparison_strip_batter_row_delta_guard(
        extracted: dict,
        scoreboard,
        batting_team: str | None,
        *,
        frame_count: int,
        record_state_recovery_guard,
) -> bool:
    """Reject only strip ``batters`` when a confirmed row disagrees >20 runs.

    Score, ``match_overs``, and bowler strings come from separate OCR
    regions; a *batter row-pair* swap (misaligned label↔stats cells)
    must not strip those independent fields (Thread 7 / MI vs SRH
    F2134-class).  Returns True if ``batters`` were popped.
    """
    if not (extracted.get("batters") and scoreboard.batting_card
            and batting_team):
        return False
    for _gb in extracted["batters"]:
        _gb_name = _gb.get("name", "")
        _gb_resolved = (
            scoreboard.resolve_name(_gb_name) if _gb_name else None)
        if _gb_resolved and _gb_resolved in scoreboard.batting_card:
            _gb_card = scoreboard.batting_card[_gb_resolved]
            _gb_existing = _gb_card.get("runs")
            _gb_existing_balls = _gb_card.get("balls")
            _gb_new = _gb.get("runs")
            _gb_confirmed = (
                _gb_existing_balls is not None
                and int(_gb_existing_balls) > 0)
            if (_gb_confirmed
                    and _gb_existing is not None
                    and _gb_new is not None
                    and abs(int(_gb_existing) - int(_gb_new)) > 20):
                record_state_recovery_guard(
                    "batter_row_rejected",
                    proposed_reset=[
                        f"bat:{_gb_resolved}:runs",
                        f"bat:{_gb_resolved}:balls",
                    ])
                row_delta = abs(int(_gb_existing) - int(_gb_new))
                log.info(f"  [GUARD] {_gb_resolved} diff "
                         f"{_gb_existing}→{_gb_new} — "
                         f"comparison strip for batting team")
                log.warn(
                    f"  [STRIP-ROWS-MISALIGNED] frame=F{frame_count} "
                    f"row_delta={row_delta} popped=batters "
                    f"preserved=score,match_overs,bowler "
                    f"poison=batters_only "
                    f"row_pair={_gb_resolved} "
                    f"strip_runs={_gb_new} card_runs={_gb_existing}")
                extracted.pop("batters", None)
                return True
    return False


def _poison_scoreboard_after_graphic_transition(
        *,
        prev_vision_frame_type: str | None,
        frame_type: str,
        already_poisoned: bool,
) -> bool:
    """GRAPHIC→SCOREBOARD adjacency: overlay may still fade; strip OCR."""
    return (not already_poisoned
            and frame_type == "SCOREBOARD"
            and prev_vision_frame_type == "GRAPHIC")


def _apply_inn2_transition_gates(
        extracted: dict,
        scoreboard,
        score_mgr,
        frame_count: int,
) -> tuple[bool, str | None]:
    """P12 in-window content gates for innings-2 cold-start hardening.

    Six gates: numeric bounds (score/wickets/overs), bowler XI
    membership, batter XI membership, null-team advisory.  Returns
    ``(poisoned, reason)``.  No-op outside the post-reset transition
    window (self-skips via ``score_mgr.in_inn2_transition``).
    """
    if score_mgr is None or not score_mgr.in_inn2_transition(frame_count):
        return False, None

    score = extracted.get("score")
    wkts = extracted.get("wickets")
    overs = extracted.get("match_overs")
    if overs is None:
        overs = extracted.get("overs")

    if score is not None:
        try:
            if int(score) > 30:
                return True, f"score>30:{score}"
        except (ValueError, TypeError):
            pass
    if wkts is not None:
        try:
            if int(wkts) > 2:
                return True, f"wickets>2:{wkts}"
        except (ValueError, TypeError):
            pass
    if overs is not None:
        try:
            if float(str(overs).split("/")[0]) > 5.0:
                return True, f"overs>5.0:{overs}"
        except (ValueError, TypeError):
            pass

    resolve = (getattr(scoreboard, "resolve_name", None)
               or getattr(scoreboard, "_resolve_name", None))
    bowling_team = getattr(scoreboard, "bowling_team", None)
    batting_team = getattr(scoreboard, "batting_team", None)

    for be in (extracted.get("bowlers") or []):
        if not isinstance(be, dict):
            continue
        name = (be.get("name") or "").strip()
        if not name:
            continue
        resolved = resolve(name) if resolve else name
        if not resolved:
            return True, f"bowler_unresolved:{name}"
        kind, _ = scoreboard.is_eligible_to_bat_or_bowl(
            resolved, bowling_team)
        if kind == "reject":
            return True, f"bowler_not_in_xi:{resolved}"

    for be in (extracted.get("batters") or []):
        if not isinstance(be, dict):
            continue
        name = (be.get("name") or "").strip()
        if not name:
            continue
        resolved = resolve(name) if resolve else name
        if not resolved:
            return True, f"batter_unresolved:{name}"
        kind, _ = scoreboard.is_eligible_to_bat_or_bowl(
            resolved, batting_team)
        if kind == "reject":
            return True, f"batter_not_in_xi:{resolved}"

    team = extracted.get("batting_team_visible")
    if team in (None, "", "null") and score is not None:
        try:
            if int(score) > 0:
                log.info(
                    f"  [INN2-TRANSITION-NULL-TEAM] frame=F{frame_count} "
                    f"score={score} requires 2-frame corroboration "
                    f"(advisory only)")
        except (ValueError, TypeError):
            pass

    return False, None


def _detect_recap_inset_mode_c(
        *,
        extracted_score: int | None,
        extracted_team: str | None,
        scout_strip_text: str,
        tracker_score: int | None,
        tracker_state_committed: bool,
        score_delta_threshold: int = RECAP_INSET_SCORE_DELTA_THRESHOLD,
        fingerprint_re: "re.Pattern[str] | None" = _RECAP_FINGERPRINT_RE,
) -> tuple[bool, str | None]:
    """P3 Mode-C trigger: detect recap inset on a SCOREBOARD-tagged frame.

    Two independent triggers (OR):
      (1) ``team=null`` AND ``|extracted_score - tracker_score| >
          score_delta_threshold`` (only when tracker has committed state).
      (2) ``fingerprint_re`` matches anywhere in ``scout_strip_text``.

    Returns ``(triggered, reason)``. ``reason`` is ``None`` when not
    triggered. Cold-start frames (no committed tracker score) skip
    trigger 1; that hole is owned by P12.
    """
    if (tracker_state_committed
            and tracker_score is not None
            and extracted_team is None
            and extracted_score is not None):
        delta = abs(int(extracted_score) - int(tracker_score))
        if delta > score_delta_threshold:
            return True, f"team_null_delta_{delta}"

    if fingerprint_re is not None and scout_strip_text:
        if fingerprint_re.search(scout_strip_text):
            return True, "fingerprint"

    return False, None


def _should_poison_in_overlay_window(
        *,
        overlay_window_remaining: int,
        frame_type: str,
        extracted_team: str | None,
) -> bool:
    """P3 N-frame debounce: any post-P2 SCOREBOARD frame with team=null
    is treated as a residual inset read while the window is active.
    """
    return (overlay_window_remaining > 0
            and frame_type == "SCOREBOARD"
            and extracted_team is None)


def apply_scorer_decision(scoreboard, decision, frame, jump_guard,
                          batting_team=None, extracted=None,
                          frame_type: str | None = None,
                          score_mgr=None,
                          vision_desc: str | None = None,
                          innings_transition_suppressed: bool = False):
    changes = []
    schema_shadow_events: list = []
    step3_notes: list[tuple[str, str]] = []
    step4_ub_false: set[str] = set()

    # GRAPHIC frames (career/comparison overlays) regularly leak
    # career-stat numbers into the scorer's batter/bowler updates
    # ("Klaasen 44(18) v Noor in T20s" — those are vs-bowler career
    # numbers, not the live match). Hard-strip any
    # batter/bowler/score updates from a GRAPHIC frame; only innings-
    # change signals are allowed through.
    if frame_type == "GRAPHIC":
        for k in ("batter_updates", "bowler_update", "bowlers",
                  "score_update", "extras_update"):
            decision.pop(k, None)

    # [SCORER-SCHEMA-WOULD-DROP] / [SCORER-SCHEMA-WOULD-COERCE] emitted from
    # scorer_decision_schema.finalize_schema_shadow_logs
    schema_shadow_events = process_scorer_decision_schema(
        decision, frame=frame, enforce=SCORER_SCHEMA_ENFORCE, log=log)

    if decision.get("innings_change"):
        old_score = scoreboard._inn.get("score") or 0
        score_up = decision.get("score_update", {})
        new_score = score_up.get("to") if isinstance(score_up, dict) else None
        if new_score is not None and int(new_score) >= int(old_score):
            log.info(f"  [GUARD] Innings change rejected — score increased "
                     f"({old_score} → {new_score})")
            decision["innings_change"] = False
        else:
            log.info(f"  [SCORER] Innings change signalled — "
                     f"deferring to target detection logic")
            changes.append("INNINGS CHANGE (deferred)")
            _apply_scorer_item2_cleanup(
                schema_shadow_events, step3_notes, step4_ub_false,
                scoreboard, score_mgr, frame, changes)
            return changes

    if not batting_team:
        log.info("  No batting team set — skipping all updates")
        _apply_scorer_item2_cleanup(
            schema_shadow_events, step3_notes, step4_ub_false,
            scoreboard, score_mgr, frame, changes)
        return changes

    batter_ups = decision.get("batter_updates", {})
    batters_accepted = any(
        isinstance(u, dict) and u.get("accepted", True)
        for u in (batter_ups.values() if isinstance(batter_ups, dict) else [])
    )
    bowler_up = decision.get("bowler_update", {})
    if isinstance(bowler_up, dict) and "name" in bowler_up:
        bowler_accepted = bowler_up.get("accepted", True) and not _is_placeholder(bowler_up.get("name", ""))
    else:
        bowler_accepted = any(
            isinstance(d, dict) and d.get("accepted", True)
            for d in (bowler_up.values() if isinstance(bowler_up, dict) else [])
        )
    has_bowlers_array = bool(decision.get("bowlers"))
    has_ground_truth = bool(decision.get("ground_truth_applied"))
    if not batters_accepted and not bowler_accepted \
            and not has_bowlers_array and not has_ground_truth:
        log.info("  No players from our match recognized — skipping score")
        _apply_scorer_item2_cleanup(
            schema_shadow_events, step3_notes, step4_ub_false,
            scoreboard, score_mgr, frame, changes)
        return changes

    _ext_has_score = (extracted.get("score") is not None) if extracted else False
    _ext_has_overs = (extracted.get("match_overs") is not None) if extracted else False
    _ext_has_wickets = (extracted.get("wickets") is not None) if extracted else False
    _ext_has_batters = bool(extracted.get("batters")) if extracted else False
    _ext_has_any_data = _ext_has_score or _ext_has_overs or _ext_has_wickets or _ext_has_batters

    # Score correction guard: if the proposed score differs from
    # current by more than 7, this frame has stale/corrupted data.
    # Block ALL updates, not just ball events.
    score_up = decision.get("score_update", {})
    _proposed_score = None
    if isinstance(score_up, dict) and score_up.get("accepted") and score_up.get("to") is not None:
        try:
            _ps = score_up["to"]
            _proposed_score = int(str(_ps).split("-")[0]) if "-" in str(_ps) else int(_ps)
        except (ValueError, TypeError):
            pass
    if _proposed_score is not None:
        _cur_score = int(scoreboard._inn.get("score") or 0)
        _score_delta = _proposed_score - _cur_score
        if abs(_score_delta) > 7:
            log.info(f"  [GUARD] Score correction in Scorer output: "
                     f"{_cur_score}→{_proposed_score} (delta={_score_delta}) "
                     f"— blocking ALL updates for this frame")
            changes.append(f"CORRECTION_BLOCKED:{_proposed_score}")
            # P12 phantom-storm window extension: ≥5 CORRECTION_BLOCKED
            # within 60s of innings-2 reset extends the transition
            # window by 60s (capped at +300s total per S4).
            _p12_reset_wall = (
                getattr(score_mgr, "_inn2_reset_wall", None)
                if score_mgr is not None else None)
            if _p12_reset_wall is not None:
                _wall_now = time.time()
                if (_wall_now - _p12_reset_wall) <= 60.0:
                    if not hasattr(
                            score_mgr,
                            "_inn2_correction_blocked_timestamps"):
                        score_mgr._inn2_correction_blocked_timestamps = []
                    score_mgr._inn2_correction_blocked_timestamps.append(
                        _wall_now)
                    if len(
                            score_mgr._inn2_correction_blocked_timestamps
                    ) >= 5:
                        _ext_total = getattr(
                            score_mgr, "_inn2_extension_total", 0.0)
                        if _ext_total < 300.0:
                            score_mgr._inn2_reset_wall -= 60.0
                            score_mgr._inn2_extension_total = (
                                _ext_total + 60.0)
                            log.info(
                                f"  [INN2-TRANSITION-PHANTOM-STORM] "
                                f"{len(score_mgr._inn2_correction_blocked_timestamps)} "
                                f"blocks in "
                                f"{_wall_now - _p12_reset_wall:.0f}s — "
                                f"extending window by 60s "
                                f"(total={score_mgr._inn2_extension_total:.0f}s)")
                        else:
                            log.info(
                                f"  [INN2-TRANSITION-PHANTOM-STORM] cap "
                                f"reached ({_ext_total:.0f}s extended) — "
                                f"not extending further")
                        score_mgr._inn2_correction_blocked_timestamps.clear()
            _apply_scorer_item2_cleanup(
                schema_shadow_events, step3_notes, step4_ub_false,
                scoreboard, score_mgr, frame, changes)
            return changes

    if isinstance(score_up, dict) and score_up.get("accepted") and score_up.get("to") is not None:
        if not _ext_has_score and not _ext_has_any_data:
            log.info(f"  [GUARD] Scorer proposed score={score_up['to']} — "
                     f"extractor empty, blocking")
        else:
            if _proposed_score is not None:
                # Layer 1.5 floor (2026-04-28): inverse of Fix 11 —
                # batter-side figures are coherent but proposed *team
                # score* is below bat_sum + committed extras (stale
                # strip / OCR / graphic).  Suppressed on cold-start
                # (no committed score yet), AUTO-SWAP recovery window,
                # and explicit innings_transition_reset (score
                # legitimately returns to 0 while cards are mid-wipe).
                _suppress_score_inf_floor = (
                    scoreboard._inn.get("score") is None
                    or innings_transition_suppressed
                    or decision.get("innings_transition_reset"))
                _floor_blocked = False
                if not _suppress_score_inf_floor:
                    _sf_bat, _sf_ext, _sf_ok = _score_inf_floor_components(
                        scoreboard)
                    if _sf_ok:
                        _sf_min = _sf_bat + _sf_ext
                        if _proposed_score < _sf_min:
                            log.warn(
                                f"  [SCORE-INF-GATE] proposed="
                                f"{_proposed_score} < "
                                f"min_score_from_batters_and_extras "
                                f"(bat_sum={_sf_bat}, extras={_sf_ext}, "
                                f"min={_sf_min}) — rejecting score "
                                f"commit.  Score-side misread (Layer "
                                f"1.5 floor, Fix 11 sibling).")
                            changes.append(
                                f"SCORE-INF-GATE:proposed="
                                f"{_proposed_score}<bat_sum="
                                f"{_sf_bat}+extras={_sf_ext}")
                            _floor_blocked = True
                if not _floor_blocked:
                    # Fix 15 (Layer 1.5 score-side admission gate,
                    # 2026-04-26): sibling to Fix 11 EXTRAS-INF on the
                    # orthogonal score-side phantom dimension.  Catches
                    # the F52/F53-class score inflation where score
                    # jumps by +N with no corresponding bat-runs delta
                    # AND no wicket increment to absorb the runs.  In
                    # that case the maximum legitimate single-frame
                    # advance is 6 (one ball with all-extras combined:
                    # wide + leg-bye + boundary + penalty).  Any
                    # proposed advance above that without bat/wicket
                    # support is a stat-overlay or season-aggregate
                    # leak into the score field.  Hard-reject before
                    # the score commits.
                    _cur_score_for_gate = int(
                        scoreboard._inn.get("score") or 0)
                    _gate_advance = (_proposed_score
                                     - _cur_score_for_gate)
                    if _gate_advance > 0:
                        # bat_delta = sum of (proposed - current)
                        # across accepted batter_ups.  Use scorer-
                        # decision values directly (this gate runs
                        # BEFORE the _ext_batter_stats overlay map is
                        # built; the extras-vs-scorer trust hierarchy
                        # doesn't matter here because we only need a
                        # lower bound on the bat-side advance to
                        # validate the score-side).
                        _gate_bat_delta = 0
                        for _bgname, _bgupd in batter_ups.items():
                            if not isinstance(_bgupd, dict):
                                continue
                            if not _bgupd.get("accepted", True):
                                continue
                            _bgnew = _bgupd.get("runs")
                            if _bgnew is None:
                                continue
                            _bgresolved = (
                                scoreboard.resolve_name(_bgname)
                                or _bgname)
                            _bgcard = scoreboard.batting_card.get(
                                _bgresolved, {})
                            _bgcur = _bgcard.get("runs") or 0
                            try:
                                _bgdelta = int(_bgnew) - int(_bgcur)
                            except (ValueError, TypeError):
                                continue
                            if _bgdelta > 0:
                                _gate_bat_delta += _bgdelta
                        # wicket-fire signal: a new dismissal this
                        # frame can carry a positive runs delta into
                        # the accumulated score (the dismissed batter's
                        # last ball, if it scored).  Detect via
                        # wickets_update accepted-and-greater-than-
                        # current.
                        _gate_wkt_increment = 0
                        _wu_for_gate = decision.get(
                            "wickets_update", {})
                        if (isinstance(_wu_for_gate, dict)
                                and _wu_for_gate.get("accepted")
                                and _wu_for_gate.get("to")
                                is not None):
                            try:
                                _gate_wkt_increment = (
                                    int(_wu_for_gate["to"])
                                    - int(scoreboard._inn.get(
                                        "wickets") or 0))
                            except (ValueError, TypeError):
                                _gate_wkt_increment = 0
                        # Maximum legitimate single-frame extras on a
                        # single ball: 6 (wide + leg-bye/no-ball
                        # combinations capped at boundary-extra value).
                        # Allow 1 additional run if wickets fired this
                        # frame to absorb the dismissed batter's last-
                        # ball completion.
                        _gate_max_extras = 6
                        if _gate_wkt_increment > 0:
                            _gate_max_extras += 6  # last-ball headroom
                        _gate_score_explained = (_gate_bat_delta
                                                 + _gate_max_extras)
                        if (_gate_advance
                                > _gate_score_explained):
                            log.warn(
                                f"  [SCORE-INF-GATE] score "
                                f"{_cur_score_for_gate}→"
                                f"{_proposed_score} "
                                f"(advance=+{_gate_advance}) > "
                                f"explained "
                                f"(bat_delta={_gate_bat_delta} + "
                                f"extras_max={_gate_max_extras} = "
                                f"{_gate_score_explained}) — "
                                f"rejecting score commit.  Score-"
                                f"side phantom (Layer 1.5, "
                                f"F52/F53 class).")
                            changes.append(
                                f"SCORE-INF-GATE:advance="
                                f"{_gate_advance}>"
                                f"{_gate_score_explained}")
                        else:
                            if scoreboard.set(
                                    "score",
                                    _proposed_score, frame):
                                changes.append(
                                    f"score→{_proposed_score}")
                    else:
                        if scoreboard.set("score", _proposed_score,
                                          frame):
                            changes.append(
                                f"score→{_proposed_score}")

    overs_up = decision.get("overs_update", {})
    if isinstance(overs_up, dict) and overs_up.get("accepted") and overs_up.get("to") is not None:
        if not _ext_has_overs and not _ext_has_any_data:
            log.info(f"  [GUARD] Scorer proposed overs={overs_up['to']} — "
                     f"extractor empty, blocking")
        else:
            if scoreboard.set("overs", overs_up["to"], frame):
                changes.append(f"overs→{overs_up['to']}")

    wickets_up = decision.get("wickets_update", {})
    if isinstance(wickets_up, dict) and wickets_up.get("accepted") and wickets_up.get("to") is not None:
        if not _ext_has_wickets and not _ext_has_any_data:
            log.info(f"  [GUARD] Scorer proposed wickets={wickets_up['to']} — "
                     f"extractor empty, blocking")
        else:
            _prev_wkts = int(scoreboard._inn.get("wickets") or 0)
            if scoreboard.set("wickets", wickets_up["to"], frame):
                changes.append(f"wickets→{wickets_up['to']}")
                _new_wkts = int(scoreboard._inn.get("wickets") or 0)
                # Bug #9a: when wickets increment by exactly 1 and the
                # scorer didn't supply an explicit dismissed batter,
                # auto-dismiss the current striker. ~85% of T20
                # dismissals are the striker (caught/bowled/lbw/
                # stumped/hit-wicket); for the rare run-out of the
                # non-striker, the un-dismiss recovery path
                # (`update_batter` lines 723-737) will reactivate
                # them once the broadcast confirms they're still
                # batting. This stops FOW entries from being stuck
                # at "?/N (unknown, ?)" and stops dismissed batters
                # from lingering in AT THE CREASE.
                _diff = _new_wkts - _prev_wkts
                _explicit = decision.get("dismissal")
                if _diff == 1 and not _explicit:
                    _striker = _canonical_active_slot(
                        score_mgr, scoreboard, "striker")
                    _striker_card = (
                        scoreboard.batting_card.get(_striker)
                        if _striker else None)
                    if (_striker and _striker_card
                            and _striker_card.get("status") == "batting"):
                        if scoreboard.dismiss_batter(
                                _striker,
                                how="auto-inferred (striker on wicket)",
                                frame=frame):
                            changes.append(f"DISMISSED:{_striker}")
                            log.info(
                                f"  [WICKET-AUTO] Dismissed striker "
                                f"{_striker} on wicket increment "
                                f"({_prev_wkts}→{_new_wkts}); "
                                f"FOW recorded with full context")
                    elif _striker:
                        log.info(
                            f"  [WICKET-AUTO] Skipping auto-dismiss for "
                            f"{_striker} — not status=batting "
                            f"(card={_striker_card})")
                    else:
                        log.info(
                            f"  [WICKET-AUTO] Wickets {_prev_wkts}→"
                            f"{_new_wkts} but no striker known — "
                            f"FOW will hold placeholder")
                scoreboard.infer_dismissed_batters()

    dismissal = decision.get("dismissal")
    if dismissal:
        cur_wkts = scoreboard._inn.get("wickets")
        ext_wkts = extracted.get("wickets") if extracted else None
        wickets_increased = (ext_wkts is not None and cur_wkts is not None
                             and int(ext_wkts) > int(cur_wkts))
        if not wickets_increased:
            log.info(f"  [GUARD] Scorer proposed dismissal but "
                     f"wickets unchanged ({cur_wkts}) — blocking")
        else:
            items = dismissal if isinstance(dismissal, list) else [dismissal]
            for item in items:
                if isinstance(item, str):
                    name, how, bowler_d = item, None, None
                elif isinstance(item, dict):
                    name = item.get("batter", item.get("name", ""))
                    how = item.get("how")
                    bowler_d = item.get("bowler")
                else:
                    continue
                if name and scoreboard.dismiss_batter(
                        name, how, bowler_d, frame=frame):
                    changes.append(f"DISMISSED:{name}")

    batter_ups = decision.get("batter_updates", {})
    if isinstance(batter_ups, dict):
        extractor_batter_names: set[str] = set()
        _ext_batter_stats: dict[str, dict] = {}
        if extracted and extracted.get("batters"):
            for _b in extracted["batters"]:
                _bn = _b.get("name", "").upper().strip()
                if _bn:
                    extractor_batter_names.add(_bn)
                    _ext_batter_stats[_bn] = {
                        "runs": _b.get("runs"), "balls": _b.get("balls")}
                    _resolved = scoreboard.resolve_name(_bn)
                    if _resolved:
                        extractor_batter_names.add(_resolved.upper())
                        _ext_batter_stats[_resolved.upper()] = _ext_batter_stats[_bn]
        scoreboard.set_extractor_batters(extractor_batter_names)

        _scorer_batter_names = set(batter_ups.keys())
        _ext_only = {n for n in _ext_batter_stats if n not in
                     {k.upper() for k in _scorer_batter_names}}
        if _ext_only:
            log.info(f"  [FLOW] Extractor batters not in scorer: {_ext_only}")

        # === LAYER 1: EXTRAS-INF admission gate (Fix 11, 2026-04-26) ===
        #
        # Cricket physics: bat_sum + extras = score, with extras >= 0.
        # If proposed_bat_sum > current score, the batter proposal is
        # physically impossible (would require negative extras) and is
        # almost certainly a phantom commit.  Reject the entire batter-
        # figure proposal for this frame.
        #
        # Coverage scope (verified against today's CSK-vs-GT match data):
        #   * Catches batter-side sum-violation phantoms.  Today's
        #     fixtures: F732 (wkts=3 score=30 bat_sum=47, +17 excess —
        #     Brevis-era), F1276 (wkts=4 score=46 bat_sum=71, +25),
        #     F2400 (wkts=7 score=154 bat_sum=155, +1), and the Hosein
        #     +21 admission at F2408 (would-be bat_sum=176 > score=154,
        #     +22 — gate fires cleanly).
        #   * Does NOT catch score-side phantoms (e.g. F52 strip OCR
        #     misread of `1`->`5` inflating team score by +4 with
        #     bat_sum staying < score; downstream F53 EXTRAS-INF emitted
        #     `score=5 - bat_sum=1 = extras=4` but bat_sum < score so
        #     this gate doesn't fire).  A score-side admission gate is
        #     a separate layer (Layer 1.5, deferred).
        #   * Does NOT catch name-figure swap phantoms where total sum
        #     stays valid but two batters' rows are misattributed
        #     (signature 5 in the design-note framework — separate
        #     mechanism).
        #
        # Composition:
        #   * Acts pre-commit; phantom never enters scoreboard state.
        #     Hard-rejects the entire batter_ups + extractor-init slate
        #     for this frame.  v1 trade-off: any legitimate concurrent
        #     batter updates riding alongside the phantom in the same
        #     frame are also discarded; cost is one frame's worth of
        #     legitimate updates per gate fire, vs admitting the
        #     phantom.  Per-batter rejection deferred to v2 (would
        #     require stronger identification heuristics — same
        #     heuristics that failed to prevent the phantom).
        #   * known_extras = 0 in the formula (strict physics gate)
        #     to avoid feedback loops with the post-commit
        #     [EXTRAS-INF] reconciler at frame-loop ~line 4540, which
        #     itself derives extras from possibly-corrupted state.
        #     Tighter version (using current extras["total"] as a
        #     floor) deferred to v2 if production data shows phantoms
        #     slipping through.
        #   * The post-commit [EXTRAS-INF] log block stays as
        #     diagnostic for clean frames (different purpose:
        #     reconciles inferred extras for committed-clean state).
        #
        # Completeness gate: only fire when dismissed-batter count in
        # batting_card matches scoreboard wickets AND all dismissed-
        # and active-batter runs are known.  Partial sums under-count
        # and would produce false positives during transient state
        # (e.g. wicket fired but FOW row not yet upgraded with
        # dismissed-batter runs).  Abstaining when data is incomplete
        # is the right behaviour — false positives during state
        # transitions create a worse production experience than
        # missing some phantom commits.
        _gate_blocked = False
        try:
            _gate_score = scoreboard._inn.get("score")
            _gate_wkts = scoreboard._inn.get("wickets")
            if (_gate_score is not None
                    and _gate_wkts is not None
                    and batter_ups):
                _gate_wkts_i = int(_gate_wkts)
                _gate_score_i = int(_gate_score)
                _gate_dismissed_runs: list[int] = []
                _gate_dismissed_known = True
                _gate_dismissed_count = 0
                for _gc in scoreboard.batting_card.values():
                    if _gc.get("status") == "out":
                        _gate_dismissed_count += 1
                        _gr = _gc.get("runs")
                        if _gr is None:
                            _gate_dismissed_known = False
                            break
                        _gate_dismissed_runs.append(int(_gr))
                _gate_active_known = True
                _gate_current_active: dict[str, int] = {}
                for _gn, _gc in scoreboard.batting_card.items():
                    if _gc.get("status") == "batting":
                        _gr = _gc.get("runs")
                        if _gr is None:
                            _gate_active_known = False
                            break
                        _gate_current_active[_gn] = int(_gr)
                # Build the proposed-overlay map: for each accepted
                # batter_ups entry, prefer extractor runs over scorer
                # runs (matches the trust-hierarchy at the actual
                # update site, line ~2211).
                _gate_proposed: dict[str, int] = {}
                for _gname, _gupd in batter_ups.items():
                    if not isinstance(_gupd, dict) or not _gupd.get(
                            "accepted", True):
                        continue
                    _gname_up = _gname.upper().strip()
                    _gext_vals = _ext_batter_stats.get(_gname_up)
                    _gext_runs = (_gext_vals.get("runs")
                                  if _gext_vals else None)
                    _gscorer_runs = _gupd.get("runs")
                    _gfinal_runs = (_gext_runs if _gext_runs is not None
                                    else _gscorer_runs)
                    if _gfinal_runs is None:
                        continue
                    _gresolved = (scoreboard.resolve_name(_gname)
                                  or _gname)
                    _gate_proposed[_gresolved] = int(_gfinal_runs)
                if (_gate_dismissed_known
                        and _gate_active_known
                        and _gate_dismissed_count == _gate_wkts_i
                        and _gate_proposed):
                    # Compose proposed bat_sum = dismissed (locked)
                    # + (proposed value if updating, else current
                    # value) for each active batter + (proposed
                    # value as new active) for any batter_ups not
                    # yet active.
                    _gate_active_sum = 0
                    for _gn, _gr in _gate_current_active.items():
                        if _gn in _gate_proposed:
                            _gate_active_sum += _gate_proposed[_gn]
                        else:
                            _gate_active_sum += _gr
                    for _gn, _gr in _gate_proposed.items():
                        if _gn not in _gate_current_active:
                            _gate_active_sum += _gr
                    _gate_bat_sum = (sum(_gate_dismissed_runs)
                                     + _gate_active_sum)
                    if _gate_bat_sum > _gate_score_i:
                        _gate_excess = _gate_bat_sum - _gate_score_i
                        _gate_names = ", ".join(
                            f"{_n}={_r}"
                            for _n, _r in _gate_proposed.items())
                        log.warn(
                            f"  [EXTRAS-INF-GATE] wkts="
                            f"{_gate_wkts_i}: proposed bat_sum="
                            f"{_gate_bat_sum} > score="
                            f"{_gate_score_i} (excess="
                            f"{_gate_excess}) — rejecting batter "
                            f"proposals ({_gate_names}). Cricket "
                            f"physics violation; phantom commit "
                            f"prevented.")
                        changes.append(
                            f"EXTRAS-INF-GATE:bat_sum="
                            f"{_gate_bat_sum}>"
                            f"{_gate_score_i}")
                        _gate_blocked = True
        except (ValueError, TypeError):
            pass

        # Fix 14 (cricket-physics balls-ceiling, 2026-04-26):
        # sibling to Fix 11 on the orthogonal physics dimension.
        # Reject batter slates where a single batter's `balls`
        # field exceeds the total legal balls bowled in the
        # current innings (overs * 6 + ball-of-over).  Catches
        # the Powell `14(56)` class: at 6.1 overs there have
        # been 37 legal balls in the innings, so no batter can
        # have faced 56.  This is a definite stat-overlay leak
        # (season-aggregate / career figure) into the live
        # scoreboard strip.  Same hard-reject pattern as Fix 11
        # (whole-row reject; batter_ups and _ext_batter_stats
        # both cleared so the phantom values can't reach
        # `update_batter`).
        try:
            _bc_overs_str = scoreboard._inn.get("overs")
            _bc_total_legal: int | None = None
            if _bc_overs_str not in (None, "", "—", "?"):
                _bc_overs_str = str(_bc_overs_str)
                if "." in _bc_overs_str:
                    _bc_full, _bc_part = _bc_overs_str.split(".", 1)
                    _bc_total_legal = (int(_bc_full) * 6
                                       + int(_bc_part))
                else:
                    _bc_total_legal = int(_bc_overs_str) * 6
            if (_bc_total_legal is not None
                    and _bc_total_legal >= 0
                    and not _gate_blocked):
                _bc_violators: list[tuple[str, int, int]] = []
                # Tolerance: allow a small over-count to
                # absorb extras-ball edge cases (no-ball+leg-
                # bye charging the batter, weird scorer reads
                # near over boundaries).  Hard-reject only when
                # excess is unambiguous (>= 2 balls).
                _bc_tolerance = 2
                _bc_ceiling = _bc_total_legal + _bc_tolerance
                for _bcname, _bcupd in batter_ups.items():
                    if not isinstance(_bcupd, dict):
                        continue
                    if not _bcupd.get("accepted", True):
                        continue
                    _bcname_up = _bcname.upper().strip()
                    _bcext = _ext_batter_stats.get(_bcname_up)
                    _bcext_balls = (_bcext.get("balls")
                                    if _bcext else None)
                    _bcscorer_balls = _bcupd.get("balls")
                    _bcfinal_balls = (_bcext_balls
                                      if _bcext_balls is not None
                                      else _bcscorer_balls)
                    if _bcfinal_balls is None:
                        continue
                    try:
                        _bcfinal_balls_i = int(_bcfinal_balls)
                    except (ValueError, TypeError):
                        continue
                    if _bcfinal_balls_i > _bc_ceiling:
                        _bc_violators.append(
                            (_bcname, _bcfinal_balls_i,
                             _bc_ceiling))
                if _bc_violators:
                    _bc_names = ", ".join(
                        f"{_n}=balls={_b}"
                        for _n, _b, _ in _bc_violators)
                    log.warn(
                        f"  [BALLS-CEILING-GATE] overs="
                        f"{_bc_overs_str} (legal_balls="
                        f"{_bc_total_legal}, ceiling="
                        f"{_bc_ceiling}): {_bc_names} — "
                        f"rejecting batter proposals.  Cricket"
                        f" physics violation (per-batter balls"
                        f" cannot exceed innings total); "
                        f"phantom stat-overlay commit "
                        f"prevented (Powell 14(56) class).")
                    changes.append(
                        f"BALLS-CEILING-GATE:max_balls="
                        f"{max(b for _, b, _ in _bc_violators)}"
                        f">ceiling={_bc_ceiling}")
                    _gate_blocked = True
        except (ValueError, TypeError, AttributeError):
            pass

        if _gate_blocked:
            batter_ups = {}
            _ext_batter_stats = {}

        # Issue 1: When no active batters exist, populate directly
        # from extractor data — the Scorer often returns empty
        # batter_updates on initial frames.
        active_batters = [n for n, s in scoreboard.batting_card.items()
                          if s.get("status") == "batting"]
        if not active_batters and _ext_batter_stats and not batter_ups:
            log.info(f"  [INIT] No active batters — populating from "
                     f"extractor: {list(_ext_batter_stats.keys())}")
            for ebn, evals in _ext_batter_stats.items():
                _r = evals.get("runs")
                _b = evals.get("balls")
                # ABSTAIN on all-null rows.  The extractor prompt (post
                # 2026-04-21) emits null for unreadable numbers; we must
                # NOT activate a batter with fake 0(0) from those rows,
                # because the downstream STALE-0/consensus path can then
                # lock them at 0 when the real numbers (e.g. 115) arrive.
                # Wait for a frame where scout actually read digits.
                if _r is None and _b is None:
                    log.info(
                        f"  [INIT] Skipping activation of '{ebn}' — "
                        f"extractor returned null runs/balls; "
                        f"awaiting readable strip")
                    continue
                if _scorer_batter_row_is_dismissed_resurrection(
                        scoreboard, ebn, frame, step3_notes):
                    continue
                if not _scorer_batter_update_allowed(
                        scoreboard, ebn, frame, step3_notes):
                    continue
                if scoreboard.update_batter(ebn, runs=_r, balls=_b,
                                            frame=frame):
                    changes.append(
                        f"bat:{ebn}={_r if _r is not None else '?'}"
                        f"({_b if _b is not None else '?'})")
                else:
                    step4_ub_false.add(str(ebn))

        for name, update in batter_ups.items():
            if not isinstance(update, dict) or not update.get("accepted", True):
                continue
            # Expand short scorer keys (e.g. "M") using extractor names
            if len(name.strip()) <= 2 and extractor_batter_names:
                for ebn in extractor_batter_names:
                    if ebn.startswith(name.upper().strip()):
                        name = ebn
                        break
            if extractor_batter_names:
                _rn = scoreboard.resolve_name(name)
                _name_up = name.upper().strip()
                if (_name_up not in extractor_batter_names and
                        (not _rn or _rn.upper() not in extractor_batter_names)):
                    log.info(f"  [GUARD] Batter '{name}' not in extractor "
                             f"output — scorer inferred, rejecting")
                    step3_notes.append(("GUARD_BATTER_EXTRACTOR", name))
                    continue
            if _scorer_batter_row_is_dismissed_resurrection(
                    scoreboard, name, frame, step3_notes):
                continue
            if not _scorer_batter_update_allowed(
                    scoreboard, name, frame, step3_notes):
                continue
            _scorer_runs = update.get("runs")
            _scorer_balls = update.get("balls")
            _name_up2 = name.upper().strip()
            _ext_vals = _ext_batter_stats.get(_name_up2)
            # TRUST HIERARCHY (Bug #1 fix):
            #   Extractor wins on NUMBERS (runs/balls) — it's a direct
            #   regex parse of the broadcast strip, deterministic and
            #   accurate.
            #   Scorer wins on NAMES (resolution to canonical squad
            #   names) — handled by `name` resolution above.
            # Previously the Scorer's hallucinated runs/balls would
            # overwrite Extractor's correct values, then the
            # consistent_tracker regression guard would lock the bad
            # value in (rejecting the next frame's correct extractor
            # value as a "regression").
            _ext_runs = _ext_vals.get("runs") if _ext_vals else None
            _ext_balls = _ext_vals.get("balls") if _ext_vals else None
            _final_runs = _ext_runs if _ext_runs is not None \
                else _scorer_runs
            _final_balls = _ext_balls if _ext_balls is not None \
                else _scorer_balls
            if _ext_runs is not None and _scorer_runs is not None \
                    and str(_ext_runs) != str(_scorer_runs):
                log.info(f"  [FLOW] {name}: extractor runs={_ext_runs} "
                         f"vs scorer runs={_scorer_runs} "
                         f"— USING EXTRACTOR")
            if _ext_balls is not None and _scorer_balls is not None \
                    and str(_ext_balls) != str(_scorer_balls):
                log.info(f"  [FLOW] {name}: extractor balls={_ext_balls} "
                         f"vs scorer balls={_scorer_balls} "
                         f"— USING EXTRACTOR")
            if scoreboard.update_batter(name,
                                        runs=_final_runs,
                                        balls=_final_balls,
                                        striker=update.get("striker"),
                                        frame=frame):
                changes.append(
                    f"bat:{name}="
                    f"{_final_runs if _final_runs is not None else '?'}("
                    f"{_final_balls if _final_balls is not None else '?'})")
            else:
                step4_ub_false.add(str(name))

    bowler_up = decision.get("bowler_update", {})
    if isinstance(bowler_up, dict) and bowler_up:
        _ext_b_for_bowler = (extracted.get("bowler")
                             if isinstance(extracted, dict) else None)
        if "name" in bowler_up:
            bname = bowler_up["name"]
            if not _is_placeholder(bname) and bowler_up.get("accepted", True):
                _b_overs = bowler_up.get("overs")
                _b_runs = bowler_up.get("runs")
                _b_wickets = bowler_up.get("wickets")
                if (isinstance(_ext_b_for_bowler, dict)
                        and _ext_name_matches_canonical(
                            _ext_b_for_bowler.get("name"),
                            bname, scoreboard)):
                    _b_overs = _ext_b_for_bowler.get("overs", _b_overs)
                    _b_runs = _ext_b_for_bowler.get("runs", _b_runs)
                    _b_wickets = _ext_b_for_bowler.get("wickets", _b_wickets)
                if scoreboard.update_bowler(bname,
                                            overs=_b_overs,
                                            runs=_b_runs,
                                            wickets=_b_wickets,
                                            frame=frame,
                                            vision_desc=vision_desc):
                    changes.append(f"bowl:{bname}")
        else:
            for bname, bdata in bowler_up.items():
                if not isinstance(bdata, dict) or not bdata.get("accepted", True):
                    continue
                _b_overs = bdata.get("overs")
                _b_runs = bdata.get("runs")
                _b_wickets = bdata.get("wickets")
                if (isinstance(_ext_b_for_bowler, dict)
                        and _ext_name_matches_canonical(
                            _ext_b_for_bowler.get("name"),
                            bname, scoreboard)):
                    _b_overs = _ext_b_for_bowler.get("overs", _b_overs)
                    _b_runs = _ext_b_for_bowler.get("runs", _b_runs)
                    _b_wickets = _ext_b_for_bowler.get("wickets", _b_wickets)
                if scoreboard.update_bowler(bname,
                                            overs=_b_overs,
                                            runs=_b_runs,
                                            wickets=_b_wickets,
                                            frame=frame,
                                            vision_desc=vision_desc):
                    changes.append(f"bowl:{bname}")

    # Issue 4: When no bowler is set, populate from extractor
    if not scoreboard._inn.get("current_bowler") and extracted:
        _ext_b = extracted.get("bowler")
        if isinstance(_ext_b, dict) and _ext_b.get("name"):
            _ebn = _ext_b["name"]
            if not _is_placeholder(_ebn):
                log.info(f"  [INIT] No bowler set — populating from "
                         f"extractor: {_ebn}")
                if scoreboard.update_bowler(
                        _ebn,
                        overs=_ext_b.get("overs"),
                        runs=_ext_b.get("runs"),
                        wickets=_ext_b.get("wickets"),
                        frame=frame,
                        vision_desc=vision_desc):
                    changes.append(f"bowl:{_ebn}")

    for b in decision.get("bowlers", []):
        if isinstance(b, dict) and b.get("name"):
            bname = b["name"]
            if not _is_placeholder(bname):
                if scoreboard.update_bowler(bname,
                                            overs=b.get("overs"),
                                            runs=b.get("runs"),
                                            wickets=b.get("wickets"),
                                            frame=frame,
                                            vision_desc=vision_desc):
                    changes.append(f"bowl:{bname}")

    score_changed = any(c.startswith("score→") for c in changes)
    batter_changed = any(c.startswith("bat:") for c in changes)
    if score_changed and not batter_changed:
        log.info("  [WARN] Score changed but no batter update — "
                 "stats may be delayed")

    for field, reason in (decision.get("rejected") or {}).items():
        log.info(f"  REJECTED {field}: {reason}")
    for field, reason in (decision.get("deferred") or {}).items():
        log.info(f"  DEFERRED {field}: {reason}")

    # === S27: legacy striker default + DEDUP band-aid removed ===
    # Both the "extractor-order inference" + "default to active[0]/[1]"
    # block and the striker==non DEDUP rewrite were pre-SM
    # cutover code paths. ScoreManager is now the sole authority for
    # striker/non, and build_full_payload writes its values
    # (including None) through to the UI. The legacy writes here
    # caused per-frame `[STRIKER-WRITE]` flap (Hetmyer↔Parag at every
    # frame F250+) by racing SM. SM owns this. If SM has no striker,
    # the UI renders "—" / "incoming batter…" via its own fallback.
    _apply_scorer_item2_cleanup(
        schema_shadow_events, step3_notes, step4_ub_false,
        scoreboard, score_mgr, frame, changes)
    return changes


# ---------------------------------------------------------------------
# Debug-frame archival (P2 fix, 2026-04-25).
#
# Earlier behaviour deleted everything in `debug_frames/` on pipeline
# startup, which caused us to lose the 23 stratified prod-eval frames
# from the V5 evaluation when we restarted the pipeline mid-day to
# deploy the P0-A / P0-B / Pass-2 fixes.  The frames had only just been
# labeled and lived nowhere else; the eval json's image paths pointed
# straight at the live capture dir.  Going forward we move the
# existing frames into a dated subdir under `debug_frames_archive/`
# so the JSON's path field resolves transparently for any
# post-eval shadow run, and then bound disk usage with a retention cap.
# ---------------------------------------------------------------------

DEBUG_FRAMES_DIR = "debug_frames"
DEBUG_FRAMES_ARCHIVE_DIR = "debug_frames_archive"
DEBUG_FRAMES_ARCHIVE_KEEP = 10  # keep at most this many session subdirs


def _archive_old_debug_frames(
    src_dir: str = DEBUG_FRAMES_DIR,
    archive_root: str = DEBUG_FRAMES_ARCHIVE_DIR,
    *,
    keep_last_n: int = DEBUG_FRAMES_ARCHIVE_KEEP,
    session_id: str | None = None,
) -> int:
    """Move existing `*.jpg` frames from ``src_dir`` into a dated subdir
    under ``archive_root`` and enforce a retention cap on the archive.

    Returns the number of frames archived (0 if the source dir does not
    exist or is empty).  No-ops on a fresh start where the live
    capture dir is empty — there is nothing to preserve and we don't
    leave behind empty session dirs.

    The session subdir is named ``YYYY-MM-DD_HHMMSS`` so dirs sort
    chronologically; ``_enforce_retention_policy`` removes the oldest
    sessions beyond ``keep_last_n``.

    Used as a drop-in replacement for the prior
    ``glob('debug_frames/*.jpg') + os.remove`` cleanup at the top of
    ``run_test()``.  Tests inject ``src_dir`` / ``archive_root`` /
    ``session_id`` to make the behaviour deterministic.
    """
    import glob as _glob
    import shutil as _shutil
    from datetime import datetime as _dt

    if not os.path.isdir(src_dir):
        return 0
    existing = sorted(_glob.glob(os.path.join(src_dir, "*.jpg")))
    if not existing:
        return 0

    sid = session_id or _dt.now().strftime("%Y-%m-%d_%H%M%S")
    dest = os.path.join(archive_root, sid)
    os.makedirs(dest, exist_ok=True)

    moved = 0
    for path in existing:
        try:
            _shutil.move(path, dest)
            moved += 1
        except Exception as e:
            log.warning(
                f"[CLEANUP] Failed to archive {path} -> {dest}: {e}; "
                f"removing instead"
            )
            try:
                os.remove(path)
            except Exception:
                pass

    log.info(
        f"[CLEANUP] Archived {moved} frames to {dest} "
        f"(was {len(existing)} in {src_dir})"
    )
    _enforce_archive_retention(archive_root, keep_last_n=keep_last_n)
    return moved


def _enforce_archive_retention(
    archive_root: str = DEBUG_FRAMES_ARCHIVE_DIR,
    *,
    keep_last_n: int = DEBUG_FRAMES_ARCHIVE_KEEP,
) -> int:
    """Delete the oldest session subdirs in ``archive_root`` until at
    most ``keep_last_n`` remain.  Returns the number of session dirs
    removed.  Subdirs are sorted lexicographically (which matches
    chronological order given the ``YYYY-MM-DD_HHMMSS`` session-id
    format), so the oldest are always at the front of the list.

    Non-directory entries are ignored.  Errors during removal are
    logged but don't propagate — a transient FS hiccup shouldn't
    crash pipeline startup.
    """
    import shutil as _shutil

    if not os.path.isdir(archive_root):
        return 0
    entries = sorted(
        e for e in os.listdir(archive_root)
        if os.path.isdir(os.path.join(archive_root, e))
    )
    removed = 0
    while len(entries) > keep_last_n:
        oldest = entries.pop(0)
        target = os.path.join(archive_root, oldest)
        try:
            _shutil.rmtree(target)
            removed += 1
            log.info(f"[CLEANUP] Removed old archive: {target}")
        except Exception as e:
            log.warning(f"[CLEANUP] Failed to prune {target}: {e}")
    return removed


def _build_full_payload_from_state(
    *,
    scoreboard,
    score_mgr,
    over_mgr,
    partnership_tracker,
    cricket_field,
    team_names: list[str],
    batting_team: str | None,
    bowling_team: str | None,
    toss_winner_name: str | None,
    toss_decision_str: str | None,
    frame_count: int,
    last_delivery_info: dict | None,
    broadcast_cache: dict,
    speed_kph: float | None = None,
    canon_player_name=None,
    record_state_recovery_guard=None,
    assert_payload_invariants=None,
) -> dict:
    """Build the SINGLE canonical WS payload (extracted from run_test)."""
    _ = assert_payload_invariants  # API compatibility; not used in-body.
    state = scoreboard.get_live_state() if scoreboard._inn else {}
    # === S1 fix: complete the SM cutover ===
    # ScoreManager is the sole authority for striker / non /
    # current_bowler when running live (`shadow=False`). On idle
    # frames the old code path leaked `scoreboard._inn["striker"]`
    # (written by ~17 pre-SM sites) onto the UI, causing the
    # per-frame striker flicker (S1) and the stale-bowler hallucination
    # in Storyteller (S3). Override here so every WS payload — idle
    # or event — uses SM's tracked names.
    #
    # get_broadcast_state (legacy active-list scrub) removed 2026-04-29;
    # callers use get_live_state; ``_project_active_batters`` runs whenever
    # ``state`` is non-empty (shadow and live) so SM-first projection is
    # consistent. Bowler override + WS-SCRUB + slot invariant stay gated
    # on ``not score_mgr.shadow`` (audit get_broadcast_state_path_b §6.3).
    if state:
        _ws_fallback_events = _project_active_batters(
            state, score_mgr, scoreboard, canon_player_name)
        if not score_mgr.shadow and score_mgr.bowler_name:
            state["current_bowler"] = canon_player_name(
                score_mgr.bowler_name, bowler=True)
        for _fb_slot, _fb_val in _ws_fallback_events:
            log.info(
                f"  [WS-PROJECTION-FALLBACK] {_fb_slot}={_fb_val!r} "
                f"surfaced from sb._inn (SM-null, in active_batting)")
        if not score_mgr.shadow:
            # ── WS-boundary hygiene scrub (broadened 2026-04-22) ──
            # Reject ANY striker / non name that isn't currently
            # `batting_card[name].status == "batting"`, and fall back
            # to the active list so the UI never shows a None striker
            # when two batters are clearly at the crease.
            #
            # Merges two bugs caught in live monitoring of MI-vs-CSK:
            #   * P0-3 — striker=None after a wicket because SM cleared
            #     it and the old scrub only checked status=="out", never
            #     re-seeded from the active list.
            #   * P1-4 — "Danish Malewar" phantom non that wasn't
            #     in batting_card AT ALL (Scout OCR'd a squad-stats
            #     overlay); the old scrub skipped it because the
            #     card-not-found path fell through without action.
            #
            # Fallback rule:
            #   striker      → active[0] if available
            #   non  → first active name that isn't the striker
            #                  (avoids writing the same name to both
            #                  slots when striker just got re-seeded)
            #
            # Reason-tagged telemetry so post-deploy monitoring can
            # distinguish the P0-3 class ("status_out" etc.) from the
            # P1-4 class ("not_in_card"). Per-counter sub-tags land in
            # module-level `_ws_scrub_counts` for grep-ability.
            _scrub_counts = _ws_scrub_counts

            _bc = scoreboard.batting_card or {}
            _active = [_n for _n, _c in _bc.items()
                       if _c and _c.get("status") == "batting"]

            def _classify_reject_reason(_name: str) -> str:
                _c = _bc.get(_name)
                if _c is None:
                    return "not_in_card"
                _st = _c.get("status")
                if _st is None:
                    return "status_none"
                return f"status_{_st}"

            for _slot in ("striker", "non"):
                _nm = state.get(_slot)
                if not _nm:
                    continue
                _c = _bc.get(_nm)
                if _c and _c.get("status") == "batting":
                    _ws_scrub_consec.pop(f"{_slot}:{_nm}", None)
                    continue  # passes admission

                _reason = _classify_reject_reason(_nm)
                _key = f"{_slot}:{_reason}"
                _scrub_counts[_key] = _scrub_counts.get(_key, 0) + 1
                _consec_key = f"{_slot}:{_nm}"
                _ws_scrub_consec[_consec_key] = (
                    _ws_scrub_consec.get(_consec_key, 0) + 1)

                if (_c is not None
                        and _c.get("status") in ("yet_to_bat", None)
                        and _ws_scrub_consec[_consec_key] >= 2):
                    _old_status = _c.get("status")
                    _c["status"] = "batting"
                    _ws_scrub_consec.pop(_consec_key, None)
                    log.info(
                        f"  [WS-PROMOTE] {_slot}='{_nm}' auto-promoted "
                        f"via 2-frame consensus (was={_old_status})")
                    continue

                if _slot == "striker":
                    _fallback = _active[0] if _active else None
                else:  # non
                    _cur_str = state.get("striker")
                    _other = [_n for _n in _active if _n != _cur_str]
                    _fallback = _other[0] if _other else None

                log.warn(
                    f"  [WS-SCRUB] {_slot}='{_nm}' rejected "
                    f"reason={_reason} "
                    f"(#{_scrub_counts[_key]}) "
                    f"→ fallback={_fallback!r} "
                    f"active={_active}")
                record_state_recovery_guard(
                    "slot_scrub_rejected",
                    proposed_reset=[f"slot:{_slot}", f"status:{_nm}"])
                state[_slot] = _fallback
            if enforce_ws_slot_invariant(
                    state, scoreboard, canon_player_name):
                record_state_recovery_guard(
                    "slot_collision_rejected",
                    proposed_reset=["slot:striker", "slot:non"])

    visible_fow, internal_fow_count = project_fow_for_payload(
        scoreboard.fall_of_wickets)

    # ── Path B Item 3: SM vs SB bowler_name feeder divergence ─────
    try:
        _sm_bowler_raw = getattr(score_mgr, "bowler_name", None)
        _sb_bowler_raw = (scoreboard._inn or {}).get("current_bowler")
        _div_sig = (repr(_sm_bowler_raw), repr(_sb_bowler_raw))
        _prev_div_sig = _last_feeder_div_sig.get("sig")
        if (_div_sig != _prev_div_sig
                and _sm_bowler_raw != _sb_bowler_raw):
            _must_ch = bool(getattr(
                scoreboard, "_bowler_must_change", False))
            _consensus = "pending" if _must_ch else "active"
            _f_since = int(getattr(
                score_mgr, "frames_since_event", 0) or 0)
            log.info(
                "  [SM-FEEDER-DIVERGENCE] field=bowler_name "
                f"sm_value={_sm_bowler_raw!r} "
                f"sb_value={_sb_bowler_raw!r} "
                f"sb_consensus_state={_consensus} "
                f"frames_since_sm_update={_f_since}")
            _last_feeder_div_sig["sig"] = _div_sig
        elif _sm_bowler_raw == _sb_bowler_raw and _prev_div_sig is not None:
            _last_feeder_div_sig["sig"] = None
    except Exception as _bowler_div_exc:
        log.warn(
            f"  [SM-FEEDER-DIVERGENCE] diagnostic error: "
            f"{_bowler_div_exc}")

    # ── WS-PROJECTION-GAP diagnostics (2026-04-23) ──────────
    # Live investigation of the "UI sees None for striker/
    # non/current_bowler even though pipeline state has
    # them" cluster found by parity_monitor + element_checker.
    # Symptoms: 4 UI issues, all pointing to a projection gap
    # between (a) scoreboard._inn / scoreboard.batting_card,
    # (b) score_mgr state, and (c) the payload this function
    # returns. Log once per broadcast when a gap is detected,
    # so we can tell exactly which layer is dropping the value.
    #
    # Rate-limit: only log when a gap is freshly present
    # (suppress repeats while the gap persists) to avoid log
    # spam on the steady-state divergence we already know about.
    try:
        _sb = scoreboard._inn or {}
        _active_batting = [
            n for n, c in scoreboard.batting_card.items()
            if c.get("status") == "batting"
        ]
        _sm_striker = getattr(score_mgr, "striker", None)
        _sm_nonstr = getattr(score_mgr, "non", None)
        _sm_bowler = getattr(score_mgr, "bowler_name", None)
        _sb_striker = _sb.get("striker")
        _sb_nonstr = _sb.get("non")
        _sb_bowler = _sb.get("current_bowler")
        _final_striker = state.get("striker") if state else None
        _final_nonstr = state.get("non") if state else None
        _final_bowler = state.get("current_bowler") if state else None

        _signature = (
            _final_striker, _final_nonstr, _final_bowler,
            tuple(_active_batting), _sm_striker, _sm_nonstr,
            _sm_bowler, _sb_striker, _sb_nonstr, _sb_bowler,
        )
        _prev_sig = _last_gap_sig.get("sig")
        _gaps = []
        if (_final_striker is None and _active_batting
                and not score_mgr.shadow):
            _gaps.append(
                f"striker=None (payload) "
                f"sb._inn.striker={_sb_striker!r} "
                f"sm.striker={_sm_striker!r} "
                f"active_batting={_active_batting}")
        if (_final_nonstr is None and len(_active_batting) >= 2
                and not score_mgr.shadow):
            _gaps.append(
                f"non=None (payload) "
                f"sb._inn.non={_sb_nonstr!r} "
                f"sm.non={_sm_nonstr!r} "
                f"active_batting={_active_batting}")
        if (_final_bowler is None
                and (_sb_bowler or _sm_bowler)
                and not score_mgr.shadow):
            _gaps.append(
                f"current_bowler=None (payload) "
                f"sb._inn.current_bowler={_sb_bowler!r} "
                f"sm.bowler_name={_sm_bowler!r}")
        if _gaps and _signature != _prev_sig:
            for _g in _gaps:
                log.warn(f"  [WS-PROJECTION-GAP] {_g}")
            _last_gap_sig["sig"] = _signature
        elif not _gaps and _prev_sig is not None:
            log.info(
                "  [WS-PROJECTION-GAP] cleared — payload now "
                f"striker={_final_striker!r} "
                f"non={_final_nonstr!r} "
                f"current_bowler={_final_bowler!r}")
            _last_gap_sig["sig"] = None
    except Exception as _gap_exc:
        log.warn(
            f"  [WS-PROJECTION-GAP] diagnostic error: {_gap_exc}")

    _situation = get_match_situation(state) if state else {}
    _cur_partnership = None
    if partnership_tracker:
        _raw_score = scoreboard._inn.get("score")
        _raw_overs = scoreboard._inn.get("overs")
        # Don't anchor at zero on cold-start: skip the tracker
        # update entirely until score & overs have been confirmed,
        # otherwise we anchor at team_score=0 and partnership ends
        # up reporting the entire match score.
        if _raw_score is not None and _raw_overs is not None:
            _team_score_pp = int(_raw_score)
            _team_balls_pp = overs_to_balls(_raw_overs)
            _active_for_pp = (
                state.get("active_batters", {}) if state else {})
            # Best-guess seed for first anchor: when we cold-start
            # mid-innings we don't know historical FOW or how much
            # the previous partnership scored, but the per-batter
            # numbers ARE on the broadcast strip. So if the new
            # pair has runs r1+r2 and balls b1+b2 already on the
            # strip, treat that as the partnership's current
            # progress and back-date the anchor accordingly. This
            # is a lower-bound guess (ignores extras inside the
            # partnership) but it's vastly closer to truth than
            # "partnership = entire team score". It will be
            # corrected the next time the broadcast renders an
            # explicit "P'SHIP X(Y)" overlay (handled separately).
            _guess_runs = None
            _guess_balls = None
            _wkts_now = scoreboard._inn.get("wickets")
            if not partnership_tracker.current_pair:
                if _wkts_now == 0:
                    # Innings 1 start (or any 0-wicket state): the
                    # partnership IS the team score. Anchor at 0,
                    # not at current team_score, so the tracker
                    # always reports the running total.
                    _guess_runs = _team_score_pp
                    _guess_balls = _team_balls_pp
                else:
                    # Mid-innings cold-start with wickets fallen:
                    # use bat1+bat2 sum as a lower bound.
                    _bat_pair_runs = []
                    _bat_pair_balls = []
                    for _bn in _active_for_pp.keys():
                        _bc = scoreboard.batting_card.get(_bn) or {}
                        if _bc.get("runs") is not None:
                            _bat_pair_runs.append(
                                int(_bc.get("runs") or 0))
                        if _bc.get("balls") is not None:
                            _bat_pair_balls.append(
                                int(_bc.get("balls") or 0))
                    if len(_bat_pair_runs) == 2:
                        _guess_runs = sum(_bat_pair_runs)
                    if len(_bat_pair_balls) == 2:
                        _guess_balls = sum(_bat_pair_balls)
            partnership_tracker.update(
                _active_for_pp, _team_score_pp, _team_balls_pp,
                initial_guess_runs=_guess_runs,
                initial_guess_balls=_guess_balls)
            if partnership_tracker.current_pair:
                _cur_partnership = partnership_tracker.current(
                    _team_score_pp, _team_balls_pp)

    # Namespace session_id by innings so the UI's session-change
    # handler (useMatchSocket.ts) performs a full state reset when
    # the pipeline transitions from innings 1 → 2. Without this
    # reset, deepMerge preserves inn-1's score / batting_card /
    # bowling_card / this_over on top of inn-2's (initially null
    # or empty) values, yielding the "DC 242/2 (20 ov) — Sharma,
    # Klaasen" stale state the user observed at the inn-break.
    _ui_session = f"{SESSION_ID}_inn{scoreboard.current_innings}"
    return {
        "type": "state_update",
        "session_id": _ui_session,
        "timestamp": time.time(),
        "frame": frame_count,
        "match": {
            "team_a": team_names[0] if team_names else "",
            "team_b": team_names[1] if len(team_names) > 1 else "",
            "innings": scoreboard.current_innings,
            "target": state.get("target"),
            "toss": {
                "winner": toss_winner_name,
                "decision": toss_decision_str,
            },
            "phase": "pre_match" if not batting_team else "live",
            "match_phase": (
                scoreboard._inn.get("match_phase")
                if scoreboard._inn else None),
        },
        "innings_history": list(getattr(score_mgr, "innings_history", None)
                                or []),
        "scorecard": {
            "score": state.get("score"),
            "wickets": state.get("wickets"),
            "overs": state.get("overs"),
            "run_rate": state.get("run_rate"),
            "batting_team": batting_team or "",
            "bowling_team": bowling_team or "",
            "striker": state.get("striker"),
            "non": state.get("non"),
            "current_bowler": state.get("current_bowler"),
        },
        "batting_card": [
            {
                "name": n,
                "status": c.get("status"),
                "runs": c.get("runs"),
                "balls": c.get("balls"),
                "fours": c.get("fours") or 0,
                "sixes": c.get("sixes") or 0,
                "sr": (round((c["runs"] / c["balls"]) * 100, 1)
                       if c.get("balls") and c.get("runs") is not None
                       else 0),
                "dismissal": c.get("dismissal"),
                "is_striker": n == state.get("striker"),
                "position": c.get("position"),
                "batting_style": c.get("batting_style", "unknown"),
                "bowling_style": c.get("bowling_style", "unknown"),
            }
            for n, c in scoreboard.batting_card.items()
            if c.get("status") in ("batting", "out")
            or (c.get("runs") is not None
                and (c.get("runs") or 0) > 0)
        ],
        "bowling_card": _reconcile_bowler_overs(
            [
                {
                    "name": n,
                    "overs": c.get("overs"),
                    "maidens": c.get("maidens") or 0,
                    "runs": c.get("runs"),
                    "wickets": c.get("wickets"),
                    "economy": (
                        round(c["runs"] / max(float(c["overs"] or 0), 0.1), 1)
                        if c.get("overs") and c.get("runs") is not None
                        else None),
                    "is_current": n == state.get("current_bowler"),
                    "batting_style": c.get("batting_style", "unknown"),
                    "bowling_style": c.get("bowling_style", "unknown"),
                }
                for n, c in scoreboard.bowling_card.items()
                # Always surface the current bowler even when we
                # haven't yet recorded a ball against them (new
                # spell starting, or mid-over gap where the
                # broadcast bowler-slot was transiently repurposed
                # and stats didn't refresh). Without this the UI
                # hides the bowler until the first delivery of
                # their spell lands, which makes the "bowler
                # appearance on UI is slow" bug the user sees
                # during new-over transitions and intermittent
                # bowler-slot flicker.
                if (n == state.get("current_bowler")
                    or (c.get("overs") is not None
                        and float(c.get("overs") or 0) > 0))
            ],
            team_overs=state.get("overs"),
            current_bowler=state.get("current_bowler"),
        ),
        "extras": dict(scoreboard.extras),
        "partnerships": {"current": _cur_partnership},
        # ScoreManager is the single source of truth for `this_over`
        # on the UI.  The non-SM broadcast path used to pull from
        # over_mgr.get_display(), which diverges from SM's own
        # this_over by 1-2 frames whenever BED and SM disagree on
        # event timing (SM often fires a WIDE/NO_BALL on the frame
        # AFTER BED appends it to over_mgr).  The broadcast source
        # then alternates between over_mgr's view on idle frames
        # and SM's view on event frames, producing the visible
        # "last ball in this_over flickers on/off" bug. Sole owner =
        # SM, always — over_mgr stays internal for diagnostics.
        # Sole owner: SM. But SM clears `this_over` to [] the
        # same instant an over completes (append 6th ball →
        # archive → reset all happen inside one _apply_event).
        # Every downstream broadcast on that frame — and every
        # idle frame until the next over's first ball lands —
        # carries this_over=[], and the UI's deepMerge falls
        # back to the pre-rollover 5-ball snapshot (it never
        # sees the 6th ball in the `this_over` slot; the 6th
        # ball only appears for a sub-frame window).  To keep
        # the rolling-over "This Over" display sticky through
        # the over gap, fall back to SM's `completed_over` (the
        # full 6-ball just-completed over) whenever `this_over`
        # is empty.  First ball of the next over replaces it
        # cleanly because SM's this_over is then non-empty.
        # --- this_over: over_mgr (observed) is authoritative, SM fallback
        # score_mgr.this_over is DERIVED state (re-inferred from score/
        # wickets/overs deltas) and diverges from ground truth whenever
        # SM re-enters COLD_START.  Example: a single FRAME_POISONED scout
        # read triggers _validate_overs to regress overs, SM treats the
        # regression as a real reset, and the SIX / FOUR / DOT that lands
        # on the following frame never reaches score_mgr.this_over.
        # over_mgr.this_over is APPEND-ONLY observation (no re-inference),
        # so it captures every ball the pipeline emitted — matching the
        # broadcast.  Prefer it here, and only fall back to SM state when
        # over_mgr hasn't started populating the new over yet (which is
        # when SM's sticky completed_over bridges the rollover gap).
        "this_over": (
            list(over_mgr.get_display(
                scoreboard._inn.get("overs")
                if scoreboard._inn else None))
            if (over_mgr.get_display(
                scoreboard._inn.get("overs")
                if scoreboard._inn else None))
            else (list(score_mgr.completed_over)
                  if score_mgr and score_mgr.completed_over
                  else [])),
        # `completed_over` is the most-recently completed over,
        # held STICKILY in SM — set when an over rolls over,
        # never unset until the next over completes.  Without
        # this, the build_full_payload broadcast path only sent
        # `completed_over` on the single over-change frame
        # (test_pipeline.py:6336 `if _over_changed and ...`),
        # so the UI lost the completed-over display the very
        # next idle frame.  Verified 2026-04-19 KKR-vs-RR F547
        # wicket-on-7.0: the broadcast at F547 included the
        # over with W, but every subsequent frame stripped it,
        # leaving the UI's "This Over" pill empty / stuck on
        # the stale 5-entry pre-wicket snapshot.
        "completed_over": (
            list(score_mgr.completed_over)
            if score_mgr and score_mgr.completed_over
            else None),
        "completed_over_runs": (
            score_mgr.completed_over_runs
            if score_mgr and score_mgr.completed_over is not None
            else None),
        "match_situation": _situation,
        "over_history": {
            str(k): v for k, v in over_mgr.over_history.items()
        },
        "field": {
            "positions": cricket_field.get_display_positions(),
            "formation": cricket_field.template_name,
            "inside_count": cricket_field.inside_count,
            "outside_count": cricket_field.outside_count,
            "phase": cricket_field.phase,
            "confidence": cricket_field.confidence_label,
        },
        "speed_kph": speed_kph,
        "delivery_info": last_delivery_info,
        "venue": broadcast_cache.get("venue"),
        "match_info": broadcast_cache.get("match_info"),
        "fall_of_wickets": visible_fow,
        "fall_of_wickets_internal_count": internal_fow_count,
        "full_batting_squad": [
            {
                "name": n,
                "status": c.get("status"),
                "runs": c.get("runs"),
                "balls": c.get("balls"),
                "fours": c.get("fours") or 0,
                "sixes": c.get("sixes") or 0,
                "sr": (round((c["runs"] / c["balls"]) * 100, 1)
                       if c.get("balls") and c.get("runs") is not None
                       else 0),
                "dismissal": c.get("dismissal"),
                "is_striker": n == state.get("striker"),
                "position": c.get("position"),
                "batting_style": c.get("batting_style", "unknown"),
                "bowling_style": c.get("bowling_style", "unknown"),
            }
            for n, c in scoreboard.batting_card.items()
            if c.get("is_playing_xi", True)
        ],
        "full_bowling_squad": _reconcile_bowler_overs(
            [
                {
                    "name": n,
                    "overs": c.get("overs"),
                    "maidens": c.get("maidens") or 0,
                    "runs": c.get("runs"),
                    "wickets": c.get("wickets"),
                    "economy": (
                        round(c["runs"] / max(float(c["overs"] or 0), 0.1), 1)
                        if c.get("overs") and c.get("runs") is not None
                        else None),
                    "is_current": n == state.get("current_bowler"),
                    "batting_style": c.get("batting_style", "unknown"),
                    "bowling_style": c.get("bowling_style", "unknown"),
                }
                for n, c in scoreboard.bowling_card.items()
                if c.get("is_playing_xi", True)
            ],
            team_overs=state.get("overs"),
            current_bowler=state.get("current_bowler"),
        ),
    }


def _execute_innings_change_from_state(
    *,
    source: str,
    target: int | None,
    scoreboard,
    score_mgr,
    ball_analyzer,
    log,
    frame_count: int,
    team_locked: bool,
    bowling_team_strip_count: int,
    pending_innings_2: bool,
    pending_target: int | None,
    inn2_consecutive: int,
    batting_team: str | None,
    bowling_team: str | None,
    inn_break_pending: bool,
    inn_break_pending_frame: int,
    inn_break_pending_source: str | None,
    inn1_batting_team_latched: str | None,
    inn1_bowling_team_latched: str | None,
    inn1_completed_deterministic: bool,
    assign_teams_cb: Callable[..., None],
    reset_for_innings_cb: Callable[..., None],
) -> dict:
    """Centralised innings-change execution (Rule 2). Extracted from run_test.

    Keyword-only: snapshots mutable scalars; mutates scoreboard/score_mgr/
    ball_analyzer in place. Returns rebound scalar state for wrapper assignment.
    """
    if scoreboard.current_innings >= 2:
        return {
            "did_change": False,
            "team_locked": team_locked,
            "bowling_team_strip_count": bowling_team_strip_count,
            "pending_innings_2": pending_innings_2,
            "pending_target": pending_target,
            "inn2_consecutive": inn2_consecutive,
            "batting_team": batting_team,
            "bowling_team": bowling_team,
            "inn_break_pending": inn_break_pending,
            "inn_break_pending_frame": inn_break_pending_frame,
            "inn_break_pending_source": inn_break_pending_source,
            "inn1_batting_team_latched": inn1_batting_team_latched,
            "inn1_bowling_team_latched": inn1_bowling_team_latched,
            "inn1_completed_deterministic": inn1_completed_deterministic,
        }

    batting_team_out = batting_team
    bowling_team_out = bowling_team

    prev_score = int(scoreboard._inn.get("score") or 0) \
        if scoreboard._inn else 0
    prev_overs = scoreboard._inn.get("overs") if scoreboard._inn else None
    prev_wkts = int(scoreboard._inn.get("wickets") or 0) \
        if scoreboard._inn else 0
    derived_target = target
    if derived_target is None and prev_score > 0:
        derived_target = prev_score + 1

    cold_start_inn2_by_frame = (frame_count <= 20)
    try:
        _prev_overs_f = (
            float(prev_overs) if prev_overs is not None else 0.0)
    except (ValueError, TypeError):
        _prev_overs_f = 0.0
    cold_start_inn2_by_state = (
        _prev_overs_f < 18.0 and prev_wkts < 8)
    cold_start_inn2 = (
        (cold_start_inn2_by_frame or cold_start_inn2_by_state)
        and not inn1_completed_deterministic)
    log.info(
        f"  [INNINGS-CHANGE] source={source}  inn1 final="
        f"{prev_score}/{prev_wkts} ({prev_overs})  target="
        f"{derived_target}  cold_start_inn2={cold_start_inn2} "
        f"(by_frame={cold_start_inn2_by_frame} "
        f"by_state={cold_start_inn2_by_state} "
        f"overridden_by_inn1_completed={inn1_completed_deterministic})  "
        f"frame={frame_count}")

    if cold_start_inn2:
        try:
            score_mgr.set_innings_2(
                target=derived_target,
                batting_team=batting_team,
                reason=f"{source}:cold_start_relabel",
                warm_restart=True)
        except Exception as e:  # noqa: BLE001
            log.debug(f"[INNINGS-CHANGE] score_mgr.set_innings_2 "
                      f"swallowed: {e}")
        if (scoreboard.current_innings == 1
                and scoreboard._inn):
            _carry = dict(scoreboard._inn)
            if derived_target is not None:
                _carry["target"] = derived_target
            scoreboard.innings[2] = _carry
            scoreboard.innings[1] = scoreboard._blank()
            scoreboard.current_innings = 2
            scoreboard._innings2_reset_done = True
        else:
            scoreboard.set_innings_2(derived_target)
        log.info(
            f"  [INNINGS-CHANGE] cold-start path: relabelled "
            f"inn1→inn2 (preserved {prev_score}/{prev_wkts} "
            f"({prev_overs})), batting={batting_team} "
            f"bowling={bowling_team} (no swap — team roles "
            f"match the visible strip)")
    else:
        team_locked = False
        if (inn1_bowling_team_latched
                and inn1_batting_team_latched):
            new_bat = inn1_bowling_team_latched
            new_bowl = inn1_batting_team_latched
            log.info(
                "  [TEAM-ATTRIBUTION-CRICKET-RULES] "
                f"new_bat={new_bat} new_bowl={new_bowl} "
                f"latched_bat={inn1_batting_team_latched} "
                f"latched_bowl={inn1_bowling_team_latched} "
                f"source={source} frame={frame_count}")
        else:
            new_bat = bowling_team
            new_bowl = batting_team
            log.info(
                "  [TEAM-ATTRIBUTION-STRIP-FALLBACK] "
                f"new_bat={new_bat} new_bowl={new_bowl} "
                f"source={source} frame={frame_count}")
        if new_bat and new_bowl:
            try:
                score_mgr.set_innings_2(
                    target=derived_target,
                    batting_team=new_bat,
                    reason=source)
            except Exception as e:  # noqa: BLE001
                log.debug(f"[INNINGS-CHANGE] score_mgr.set_innings_2 "
                          f"swallowed: {e}")
        scoreboard.set_innings_2(derived_target)
        if new_bat and new_bowl:
            assign_teams_cb(new_bat, new_bowl, innings=2)
            team_locked = True
            batting_team_out = new_bat
            bowling_team_out = new_bowl
        else:
            log.warn(
                "  [INNINGS-CHANGE] Teams unknown at transition "
                "— leaving null; cold-start will re-derive from "
                "innings-2 broadcast.")
    if ball_analyzer:
        ball_analyzer.on_innings_change(2)
    reset_for_innings_cb(2, overs_reset_source=source)
    bowling_team_strip_count = 0
    pending_innings_2 = False
    pending_target = None
    inn2_consecutive = 0
    inn_break_pending = False
    inn_break_pending_frame = 0
    inn_break_pending_source = None

    return {
        "did_change": True,
        "team_locked": team_locked,
        "bowling_team_strip_count": bowling_team_strip_count,
        "pending_innings_2": pending_innings_2,
        "pending_target": pending_target,
        "inn2_consecutive": inn2_consecutive,
        "batting_team": batting_team_out,
        "bowling_team": bowling_team_out,
        "inn_break_pending": inn_break_pending,
        "inn_break_pending_frame": inn_break_pending_frame,
        "inn_break_pending_source": inn_break_pending_source,
        "inn1_batting_team_latched": inn1_batting_team_latched,
        "inn1_bowling_team_latched": inn1_bowling_team_latched,
        "inn1_completed_deterministic": inn1_completed_deterministic,
    }


async def run_test():
    global _MONITORING_LAST_5MIN_EMIT_TS, _MONITORING_MATCH_START_TS
    start = time.time()

    # === SQUADS ===
    log.info("=" * 60)
    log.info("SCRAPING SQUADS...")
    raw_data = await scrape_cricbuzz_squads(SQUAD_URL)
    if not raw_data:
        log.error("Squad scrape failed")
        return

    raw_data, squads = squads_to_pipeline_format(raw_data)
    team_names = list(squads.keys())
    log.info(f"Teams: {team_names}")

    # Enrich squads with batting handedness + bowling style (2-pass LLM).
    # Pass-1 (prior-knowledge guess) runs synchronously — fast (~3s) and
    # provides a complete-enough fallback. Pass-2 (web-search-grounded
    # verification) is launched as a background task once Scoreboard
    # exists so it doesn't block frame capture; on completion it
    # retro-patches both raw_data and Scoreboard cards. Cache hits skip
    # both passes; runs without GROQ_API_KEY fall through to "unknown"
    # styles. Failure is non-fatal — we keep running with whatever's
    # available.
    pass1_styles: dict = {}
    try:
        pass1_styles = await enrich_squad_styles(raw_data, pass2_background=True)
    except Exception as e:
        log.error(f"Style enrichment Pass-1 failed: {e} — continuing without")

    team_a_variants = build_team_variants(raw_data["team_a"])
    team_b_variants = build_team_variants(raw_data["team_b"])
    all_valid_teams = team_a_variants | team_b_variants
    log.info(f"Team variants: {sorted(all_valid_teams)}")

    # DON'T assume who bats — leave null
    batting_team = None
    bowling_team = None
    batting_squad = []
    bowling_squad = []
    batting_squad_roles = ""
    bowling_squad_roles = ""
    team_confirm_count = 0
    team_locked = False
    team_lock_frame = None

    scoreboard = Scoreboard()

    # Schedule Pass-2 (web-search-grounded style verification) as a
    # background task. The pipeline can now begin frame capture without
    # waiting for Pass-2 to finish — when it eventually completes it
    # retro-patches scoreboard.batting_card / bowling_card via the
    # update_player_styles callback. Pass-1 styles already merged above
    # remain in effect until then; on Pass-2 failure they stay (no
    # rollback needed). Skipped silently when Pass-1 produced no styles
    # (cache hit, GROQ_API_KEY missing, or upstream error).
    _pass2_task: asyncio.Task | None = None
    if pass1_styles:
        def _on_pass2_complete(pass2_styles: dict) -> None:
            try:
                scoreboard.update_player_styles(pass2_styles)
            except Exception as e:  # noqa: BLE001
                log.error(f"Pass-2 style retro-patch failed: {e}")

        _pass2_task = asyncio.create_task(
            enrich_squad_styles_pass2_async(
                raw_data, pass1_styles,
                on_complete=_on_pass2_complete))
        _pass2_task.add_done_callback(
            lambda t: t.exception() and log.error(
                f"Pass-2 background task raised: {t.exception()}"))

    # === S1 monitoring: monkey-patch innings-mutating Scoreboard
    # methods so the dict-wrapper survives every innings reset. ===
    _orig_setup_innings = scoreboard.setup_innings
    _orig_set_innings_2 = scoreboard.set_innings_2

    def _setup_innings_logged(*args, **kwargs):
        _r = _orig_setup_innings(*args, **kwargs)
        _wrap_innings_dicts(scoreboard)
        return _r

    def _set_innings_2_logged(*args, **kwargs):
        # Cold-start mid-innings-2 protection.
        #
        # Multiple call sites (`[CODE] Innings 2 confirmed`,
        # `[INNINGS] Scorer target`, auto-swap fresh-strip, etc.)
        # invoke `set_innings_2` to flip the innings flag and reset
        # state.  In a *real* innings transition this is correct —
        # innings 2 starts at 0/0 (0.0).  But during a cold-start
        # that began mid-innings-2 (pipeline started after the
        # interval), the data we accumulated under `current_innings
        # = 1` is *actually* innings 2 — wiping it to 0/0 destroys
        # legitimate observations (score, overs, batter / bowler
        # progress, this-over balls) and triggers the `delta>7`
        # poison guard against every recovery frame, freezing the
        # pipeline at 0/0 inn 2 forever.
        #
        # Heuristic: if at the time of the call we are in
        # `current_innings == 1` AND the state has any observed
        # progress (score > 0 OR overs > 0) AND it is *physically
        # impossible* for innings 1 to have ended (overs < 18.0 AND
        # wickets < 8), this must be a cold-start mid-innings-2
        # correction.  Snapshot the state, let the original method
        # blank everything, then restore the snapshot into
        # innings[2].
        _pre_inn = scoreboard.current_innings
        _pre_state: dict | None = None
        _is_cold_start_correction = False
        # Unified INNINGS-TRANSITION telemetry — one log line for every
        # set_innings_2 invocation regardless of trigger source. Lets
        # us audit transition frequency, time-to-detect, and catch
        # over-triggering (expected: exactly 1 per match, or 2 on
        # cold-start scenarios). Caller file:line reconstructed from
        # the stack so every trigger site is attributable.
        try:
            import inspect as _ins
            _frm = _ins.currentframe().f_back
            _caller = f"{os.path.basename(_frm.f_code.co_filename)}:{_frm.f_lineno}" if _frm else "?"
        except Exception:
            _caller = "?"
        _tel_target = args[0] if args else kwargs.get("target")
        _tel_inn = getattr(scoreboard, "_inn", None)
        _tel_score = (_tel_inn or {}).get("score") if _tel_inn else None
        _tel_wkts = (_tel_inn or {}).get("wickets") if _tel_inn else None
        _tel_overs = (_tel_inn or {}).get("overs") if _tel_inn else None
        _tel_team = (_tel_inn or {}).get("batting_team") if _tel_inn else None
        log.info(
            f"[INNINGS-TRANSITION-TELEMETRY] source=set_innings_2 "
            f"caller={_caller} "
            f"pre_inn={_pre_inn} "
            f"pre_state={_tel_score}/{_tel_wkts} ({_tel_overs}) "
            f"pre_team={_tel_team} "
            f"target={_tel_target}")
        if _pre_inn == 1 and scoreboard._inn:
            try:
                _pre_score = int(
                    scoreboard._inn.get("score") or 0)
            except (ValueError, TypeError):
                _pre_score = 0
            try:
                _pre_overs_raw = scoreboard._inn.get("overs")
                _pre_overs_f = (
                    float(_pre_overs_raw)
                    if _pre_overs_raw is not None else 0.0)
            except (ValueError, TypeError):
                _pre_overs_f = 0.0
            try:
                _pre_wkts = int(
                    scoreboard._inn.get("wickets") or 0)
            except (ValueError, TypeError):
                _pre_wkts = 0
            _has_progress = (_pre_score > 0 or _pre_overs_f > 0.0)
            _impossible_end = (
                _pre_overs_f < 18.0 and _pre_wkts < 8)
            _warm_advanced = bool(getattr(
                score_mgr, "_warm_advancing_observed", False))
            if _has_progress and _impossible_end and _warm_advanced:
                _is_cold_start_correction = True
                _pre_state = dict(scoreboard._inn)
                log.info(
                    f"[INNINGS] set_innings_2 with cold-start "
                    f"state {_pre_score}/{_pre_wkts} "
                    f"({_pre_overs_f}) — preserving (innings 1 "
                    f"physically incomplete; this is a cold-"
                    f"start mid-innings-2 correction).")
            elif _has_progress and _impossible_end:
                log.info(
                    f"[INNINGS] set_innings_2 with cold-start state "
                    f"{_pre_score}/{_pre_wkts} ({_pre_overs_f}) — NOT "
                    f"preserving (score never advanced after cold-start "
                    f"commit, likely frozen on stale-graphic).")
        # Live-monitoring v1: emit innings-1 RETRO-SUMMARY before
        # the scoreboard flips so the per-innings counter is sealed.
        try:
            if (1 not in _MONITORING_RETRO_EMITTED_INNINGS
                    and ball_analyzer is not None
                    and getattr(ball_analyzer, "_recorder", None)
                    is not None):
                from monitoring_emitters import emit_retro_summary
                _rc = ball_analyzer._recorder._retro_counters
                emit_retro_summary(1, _rc, logger=log)
                _MONITORING_RETRO_EMITTED_INNINGS.add(1)
                # Snapshot cumulative totals so the match-end emitter
                # can derive innings-2 = current - snapshot.
                _MONITORING_RETRO_INN1_SNAPSHOT["events_seen"] = (
                    _rc.events_seen)
                _MONITORING_RETRO_INN1_SNAPSHOT["spans_committed"] = (
                    _rc.spans_committed)
                _MONITORING_RETRO_INN1_SNAPSHOT["spans_fallback"] = (
                    _rc.spans_fallback)
        except Exception as _re:  # noqa: BLE001
            log.warning(f"[RETRO-SUMMARY] inn1 emit failed: {_re}")
        _r = _orig_set_innings_2(*args, **kwargs)
        if _is_cold_start_correction and _pre_state is not None:
            # Carry the requested target into the preserved
            # state so the caller's intent is honoured.
            _target = (
                args[0] if args
                else kwargs.get("target"))
            if _target is not None:
                _pre_state["target"] = _target
            else:
                _pre_state.setdefault(
                    "target",
                    scoreboard.innings[2].get("target")
                    if 2 in scoreboard.innings else None)
            scoreboard.innings[2] = _pre_state
            scoreboard.innings[1] = scoreboard._blank()
            scoreboard.current_innings = 2
            scoreboard._innings2_reset_done = True
        _wrap_innings_dicts(scoreboard)
        return _r

    scoreboard.setup_innings = _setup_innings_logged
    scoreboard.set_innings_2 = _set_innings_2_logged
    _wrap_innings_dicts(scoreboard)
    innings_1_total = None
    pending_innings_2 = False
    pending_target = None
    _inn2_consecutive = 0  # consecutive frames signalling innings 2
    _INN2_CONFIRM_FRAMES = 2  # 2-frame consensus for broadcast signals
    # === Innings-break deferral (2026-04-21) ===
    # When innings 1 reaches 20.0 overs (or all-out), the match enters
    # a 15-30 minute innings break. During the break the broadcast cycles
    # through stats panels, highlights, ads — none of which contain live
    # innings-2 data. Firing `execute_innings_change` immediately at
    # overs=20.0 flips the UI to "DC Inn 2 — Need X from Y balls" while
    # the match is still mid-break, with no innings-2 data to populate.
    # Via deepMerge the UI then keeps showing innings 1's batters/scores
    # stale on top of the "DC Inn 2" header, producing the nonsensical
    # "DC 242/2 (20 ov)" display the user sees.
    #
    # Fix: latch innings 1 final, set _inn_break_pending, and hold the
    # UI on innings 1's finalized state until we see real innings 2
    # evidence (low-overs score reading with the other team at bat).
    # Deterministic all_out_10 uses the same gate (all-out also triggers
    # a break). Hard timeout after _INN_BREAK_MAX_FRAMES prevents a
    # permanently-stuck break if broadcast evidence never surfaces.
    _inn_break_pending = False
    _inn_break_pending_frame = 0
    _inn_break_pending_source: str | None = None
    _INN_BREAK_MAX_FRAMES = 300  # ≈ 25 min @ 1 frame every 5s; safety net
    # P0-C: latch innings-1 team roles at deterministic innings-end edge.
    _inn1_batting_team_latched: str | None = None
    _inn1_bowling_team_latched: str | None = None
    _inn1_completed_deterministic: bool = False
    # P0-C telemetry: rolling FRAME_POISONED fraction during innings break.
    _POISON_RATE_WINDOW = 30
    # MI-SRH log DETAIL subsample F2347-F2694: 23/50 lines FRAME_POISONED ≈46%.
    # §P0-C ≥10pp headroom → 56%; telemetry-only (does not gate behaviour).
    _FRAME_POISONED_STRIP_TRUST_THRESHOLD = 0.56
    _poisoned_in_window: deque[bool] = deque(maxlen=_POISON_RATE_WINDOW)
    # === Match-end consensus (Fix A, 2026-04-22) ===
    # Require 2 consecutive scoreboard frames proposing the same
    # innings-2 end reason before finalizing the match. Protects
    # against single-frame OCR flickers (e.g. 8→10 wickets misread,
    # score briefly rewriting above target then self-correcting).
    # `target_reached` / `all_out` / `overs_exhausted` each track
    # consensus independently — a reason change resets the counter.
    _match_end_consecutive = 0
    _match_end_reason_pending: str | None = None
    _MATCH_END_CONFIRM = 2
    _correction_pending: dict | None = None  # tracks proposed score for consensus
    _correction_count = 0  # consecutive frames proposing the same new score
    _CORRECTION_CONFIRM = 2  # frames needed to accept a large delta
    # === Unsupported-score-spike consensus ===
    # An LLM can hallucinate a small (within-the-7-poison-threshold)
    # score increase — e.g. read 44 instead of 37 — when none of the
    # other strip cells move (overs unchanged, wickets unchanged,
    # bowler runs unchanged, no broadcast WD/NB badge, batter runs
    # unchanged).  Cricket physics says a real run-scoring event always
    # moves at least one of these; an "unsupported" delta is therefore
    # almost certainly a misread.  Pre-fix this poisoned `this_over`
    # with a phantom `Nb+6` because the EXTRA-IMMEDIATE path in
    # commentary.py emits the moment `balls_delta == 0 and s_delta > 0`
    # — and the spurious token never recovered even after the score
    # eventually stabilised.  Now: defer the score acceptance until a
    # second consecutive frame agrees with the same value.
    _unsupported_score_pending: int | None = None
    _unsupported_score_count = 0
    _UNSUPPORTED_SCORE_CONFIRM = 2
    _squad_roles: dict[str, str] = {}
    _last_wicket_frame = 0  # frame at which last wicket was detected
    _new_batter_candidate: str | None = None  # pending replacement name
    _new_batter_candidate_count = 0  # consecutive frames with same candidate
    _NEW_BATTER_CONFIRM = 2  # frames needed to accept replacement
    _first_frame_initialized = False  # set True after first valid scoreboard read
    _last_ball_event_frame = 0  # frame at which last ball_event was detected
    # Rollback tracking: when an EXTRA fires, snapshot the post-event
    # score so we can detect a subsequent confirmed regression and
    # peel the phantom Wd/Nb back off `over_mgr.this_over`.  See
    # over_mgr.pop_last_extra() for the API contract.  This is
    # defense-in-depth on top of the BED jitter-defer (which prevents
    # the no-signal +1 case) and the unsupported-score-spike guard
    # (which prevents +2..+7 phantoms): the residual case is a
    # broadcast WD/NB strip that lit up briefly, drove an EXTRA via
    # the broadcast_WD/broadcast_NB classifier, and then retracted on
    # subsequent frames as the team-score regressed.
    _last_extra_score: int | None = None
    _last_extra_over_int: int | None = None
    _ball_events_for_current_team = 0  # ball events fired since current
    # `assign_teams()` call. Resets to 0 every time teams are (re)assigned.
    # Used by Fix 3 (escape hatch) to detect cold-start team-lock: if we
    # have stripped 30+ frames as "bowling-team comparison strips" but
    # have never observed a single confirmed ball event for the team
    # we *think* is batting, our team assignment is the misread, not
    # the strip. Force-swap regardless of `_inn1_could_end`.
    _bowling_team_strip_count = 0  # consecutive frames showing bowling team strip
    # === S16/Day-1.5 hardening: cumulative (non-resetting) counter ===
    # The consecutive counter (`_bowling_team_strip_count`) resets the
    # moment one frame happens to read the assigned batting team — and
    # the SCOUT VLM hallucinates a team name on roughly 1 frame in 8
    # during cold-start, so the consecutive counter rarely reaches 30.
    # The cumulative counter only ever resets on a successful
    # `assign_teams()` call, so the escape hatch fires reliably even
    # when the consecutive streak keeps getting interrupted.
    _bowling_team_strip_total = 0
    _BOWLING_TEAM_SWAP_TOTAL_THRESHOLD = 20
    # Bug #16: was 5 — far too low. T20 broadcasts routinely show the
    # bowling team's player profiles, "BOWLING STATS" panels,
    # head-to-head graphics, and stat comparisons during between-overs
    # breaks. 5 frames at ~3s/frame = 15s of broadcast — virtually any
    # graphic exceeds it. We saw a real misfire at 8.0 overs of KKR's
    # innings: a brief GT graphic block triggered the swap, then 74s
    # later the live KKR strip returned and the system swapped back —
    # but `current_innings` had already been promoted to 2 and never
    # demoted, so KKR's own innings-1 data started landing in the
    # innings-2 slot.
    # 30 frames @ ~3s = ~90s of continuous broadcast — long enough that
    # only a real innings break sustains it.
    _BOWLING_TEAM_SWAP_THRESHOLD = 30

    # === STATE PERSISTENCE ===
    STATE_FILE = os.path.join(os.path.dirname(__file__), "match_state_cache.json")

    def save_match_state(frame_ct: int):
        """Persist scoreboard state every 10 frames."""
        if frame_ct % 10 != 0:
            return
        if (scoreboard._inn.get("score") is None
                and scoreboard._inn.get("wickets") is None
                and scoreboard._inn.get("overs") is None):
            return
        try:
            cache = scoreboard.get_cache_dict(frame_ct)
            cache["batting_team_var"] = batting_team
            cache["bowling_team_var"] = bowling_team
            cache["toss_winner"] = toss_winner_name
            cache["toss_decision"] = toss_decision_str
            # Live SESSION_ID overrides any BMF_SESSION_ID env fallback
            # so hot-resume can distinguish a real restart (different
            # uuid in cache vs current process) from a same-session
            # write-flush.
            if not cache.get("session_id"):
                cache["session_id"] = SESSION_ID
            with open(STATE_FILE, "w") as f:
                json.dump(cache, f)
        except Exception as e:
            log.error(f"[CACHE] Save failed: {e}")

    def load_match_state() -> dict | None:
        """Load cached state. Age-agnostic — callers gate on age per
        their tolerance (hot-resume identity block uses 3600s; toss-
        restore path uses its own threshold)."""
        if not os.path.exists(STATE_FILE):
            return None
        try:
            with open(STATE_FILE) as f:
                cached = json.load(f)
            return cached
        except Exception as e:
            log.error(f"[CACHE] Load failed: {e}")
            return None

    def assign_teams(bat_name, bowl_name, innings=1):
        nonlocal batting_team, bowling_team, batting_squad, bowling_squad
        nonlocal batting_squad_roles, bowling_squad_roles
        nonlocal team_confirm_count, team_locked, team_lock_frame
        nonlocal _squad_roles, _ball_events_for_current_team
        nonlocal _bowling_team_strip_total

        if team_locked and bat_name == batting_team:
            team_confirm_count += 1
            return

        if team_locked and bat_name != batting_team:
            log.info(f"  [GUARD] Team flip rejected — locked "
                     f"{batting_team} at F{team_lock_frame}")
            return

        if bat_name == batting_team:
            team_confirm_count += 1
            if team_confirm_count >= 3 and not team_locked:
                team_locked = True
                team_lock_frame = frame_count if frame_count else 0
                log.info(f"  [TEAM] Locked: {batting_team} batting, "
                         f"{bowling_team} bowling (F{team_lock_frame})")
            return

        team_confirm_count = 1
        batting_team = bat_name
        bowling_team = bowl_name
        batting_squad = squads.get(batting_team, [])
        bowling_squad = squads.get(bowling_team, [])
        roles_map: dict[str, str] = {}
        bat_xi: list[str] = []
        bowl_xi: list[str] = []
        bat_subs: list[str] = []
        bowl_subs: list[str] = []
        for key in ("team_a", "team_b"):
            team_data = raw_data[key]
            xi_names = [p["name"] for p in team_data.get("playing_xi", [])]
            bench_names = [p["name"] for p in team_data.get("bench", [])]
            if team_data["name"] == batting_team:
                batting_squad_roles = format_squad_roles(raw_data, key)
                bat_xi = xi_names
                bat_subs = bench_names
            elif team_data["name"] == bowling_team:
                bowling_squad_roles = format_squad_roles(raw_data, key)
                bowl_xi = xi_names
                bowl_subs = bench_names
            for p in (team_data.get("playing_xi", [])
                      + team_data.get("bench", [])):
                roles_map[p["name"]] = p.get("role", "")
        _squad_roles = roles_map
        player_styles = build_styles_lookup(raw_data) if raw_data else {}
        scoreboard.setup_innings(batting_team, bowling_team,
                                 batting_squad, bowling_squad,
                                 squad_roles=roles_map,
                                 batting_xi=bat_xi,
                                 bowling_xi=bowl_xi,
                                 batting_subs=bat_subs,
                                 bowling_subs=bowl_subs,
                                 player_styles=player_styles)
        scoreboard.current_innings = innings
        _cur_bowler = scoreboard._inn.get("current_bowler") if scoreboard._inn else None
        _bt = get_bowler_type(_cur_bowler, _squad_roles)
        _ov = float(scoreboard._inn.get("overs") or "0") if scoreboard._inn else 0
        cricket_field.initialize_from_match_context(_ov, _bt)
        cricket_checker.reset()
        # Fix 3 — fresh team assignment ⇒ fresh ball-event budget.
        _ball_events_for_current_team = 0
        # Day-1.5 escape-hatch hardening — cumulative strip counter
        # is per-team-assignment. Successful (re)assignment proves the
        # current strip data is now consistent with our team roles, so
        # the cumulative stripped-count is no longer evidence of a
        # team-lock misread.
        _bowling_team_strip_total = 0
        log.info(f"=== TEAMS SET: {batting_team} batting (inn {innings}) "
                 f"vs {bowling_team} bowling ===")

    toss_captured = False
    toss_winner_name = None
    toss_decision_str = None

    def _resolve_team_variant(name: str) -> str | None:
        """Resolve a team name/abbreviation to canonical team name."""
        if not name:
            return None
        up = name.upper().strip()
        for tn in team_names:
            if up == tn.upper():
                return tn
        if up in team_a_variants:
            return team_names[0]
        if up in team_b_variants:
            return team_names[1] if len(team_names) > 1 else None
        for tn in team_names:
            if up in tn.upper() or tn.upper() in up:
                return tn
        return None

    def check_toss_in_vision(vision_desc: str):
        """Detect toss result from vision text. Highest priority for
        team assignment — once captured, teams are locked forever."""
        nonlocal toss_captured, toss_winner_name, toss_decision_str
        nonlocal team_locked, team_lock_frame, team_confirm_count
        if toss_captured or not vision_desc:
            return
        upper = vision_desc.upper()

        m = re.search(
            r'(\w[\w\s]*?)\s+WON\s+(?:THE\s+)?TOSS\s+'
            r'(?:AND\s+)?(?:CHOSE|ELECTED|OPTED)\s+TO\s+'
            r'(BAT|BOWL|FIELD|BATTING|BOWLING|FIELDING)',
            upper)
        if not m:
            m = re.search(
                r'(\w[\w\s]*?)\s+WON\s+(?:THE\s+)?TOSS\s*'
                r'(?:&|AND)?\s*(BAT|BOWL|FIELD)\s*(?:FIRST)?',
                upper)
        if not m:
            m = re.search(
                r'TOSS\s*:\s*(\w[\w\s]*?)\s*,\s*'
                r'(?:ELECTED|CHOSE|OPTED)\s+TO\s+(BAT|BOWL|FIELD)',
                upper)
        if not m:
            m = re.search(
                r'(\w[\w\s]*?)\s+(?:CHOSE|ELECTED)\s+TO\s+'
                r'(BAT|BOWL|FIELD)',
                upper)
        if not m:
            return

        winner_raw = m.group(1).strip()
        decision = m.group(2).strip()
        winner = _resolve_team_variant(winner_raw)
        if not winner:
            log.info(f"[TOSS] Can't resolve '{winner_raw}' to a team")
            return
        other = [t for t in team_names if t != winner][0]
        if decision in ("BOWL", "FIELD", "BOWLING", "FIELDING"):
            bat, bowl = other, winner
        else:
            bat, bowl = winner, other
        toss_captured = True
        toss_winner_name = winner
        toss_decision_str = decision.lower()
        log.info(f"[TOSS] {winner} won, chose to {toss_decision_str}. "
                 f"{bat} bats, {bowl} bowls — LOCKED")
        assign_teams(bat, bowl, innings=1)
        team_locked = True
        team_lock_frame = frame_count if frame_count else 0
        team_confirm_count = 99

    def detect_team_from_players(extracted: dict):
        """Fallback: determine batting team from which squad the
        extracted batter names belong to."""
        if batting_team is not None:
            return
        batter_names = []
        for b in (extracted.get("batters") or []):
            n = b.get("name", "").upper().strip()
            if n and not _is_placeholder(n):
                batter_names.append(n)
        if len(batter_names) < 2:
            return

        def _squad_set(team_key):
            """Build a set of full names + individual parts for matching."""
            names = set()
            for p in squads.get(team_key, []):
                up = p.upper()
                names.add(up)
                for part in up.split():
                    if len(part) >= 4:
                        names.add(part)
            return names

        team_a_squad = _squad_set(team_names[0])
        team_b_squad = (_squad_set(team_names[1])
                        if len(team_names) > 1 else set())

        def _matches(n, squad):
            if any(n in s or s in n for s in squad):
                return True
            # Try last token of broadcast name (e.g. "M MARSH" → "MARSH")
            parts = n.split()
            if len(parts) > 1 and len(parts[-1]) >= 4:
                return parts[-1] in squad
            return False

        a_hits = sum(1 for n in batter_names if _matches(n, team_a_squad))
        b_hits = sum(1 for n in batter_names if _matches(n, team_b_squad))

        if a_hits >= 2 and a_hits > b_hits:
            bat = team_names[0]
            bowl = team_names[1] if len(team_names) > 1 else "?"
            log.info(f"[TEAM] Detected from players: {batter_names} "
                     f"→ {bat} batting ({a_hits} matches)")
            assign_teams(bat, bowl)
        elif b_hits >= 2 and b_hits > a_hits:
            bat = team_names[1]
            bowl = team_names[0]
            log.info(f"[TEAM] Detected from players: {batter_names} "
                     f"→ {bat} batting ({b_hits} matches)")
            assign_teams(bat, bowl)

    # === FIX 1: cross-team consistency check (cold start) ===
    # Reject internally inconsistent scorecards before they can poison
    # team assignment. A real T20 frame can never show "Player X batting
    # for KKR while Player Y bowls for KKR" — the bowler is on the
    # opposing team. The hallucinated F17 pre-match graphic in the
    # KKR-vs-RR bug had Jadeja (an RR player) listed as a KKR bowler,
    # which is squad-level impossible. Use the squad rosters (already
    # scraped) as the authority; toss is *not* used.
    #
    # Returns True when the card is consistent OR has too little info to
    # judge (incomplete data falls through to the existing consensus
    # path). Returns False only when squad data definitively proves the
    # card is fictional.
    _UPPER_TO_TEAM: dict[str, str] = {}
    for _tname, _plist in squads.items():
        for _p in _plist:
            up = _p.upper().strip()
            _UPPER_TO_TEAM[up] = _tname
            for _part in up.split():
                if len(_part) >= 4:
                    # First-match wins; ambiguous surnames (e.g. shared
                    # last names across teams) silently fall back to
                    # "unknown" via the conflict check below.
                    if _part in _UPPER_TO_TEAM and \
                            _UPPER_TO_TEAM[_part] != _tname:
                        _UPPER_TO_TEAM[_part] = "__AMBIGUOUS__"
                    else:
                        _UPPER_TO_TEAM.setdefault(_part, _tname)

    def _find_player_team(name: str) -> str | None:
        """Resolve a player name to its team using the scraped squads.

        Returns None for unknown / ambiguous / placeholder names so the
        caller can treat the card as 'too incomplete to judge'.
        """
        if not name:
            return None
        up = name.upper().strip()
        if _is_placeholder(up):
            return None
        hit = _UPPER_TO_TEAM.get(up)
        if hit and hit != "__AMBIGUOUS__":
            return hit
        # Last-token fallback (broadcast often shows "V SOORYAVANSHI")
        parts = up.split()
        if len(parts) > 1 and len(parts[-1]) >= 4:
            hit = _UPPER_TO_TEAM.get(parts[-1])
            if hit and hit != "__AMBIGUOUS__":
                return hit
        # Substring sweep — last resort
        for key, team in _UPPER_TO_TEAM.items():
            if team == "__AMBIGUOUS__" or len(key) < 4:
                continue
            if up == key or up in key or key in up:
                return team
        return None

    def _card_internally_consistent(extracted: dict) -> tuple[bool, str]:
        """Check that batters and bowler can plausibly co-exist on the
        same delivery, given the squad rosters.

        Returns (ok, reason). When ok is False, the caller should treat
        the frame as poisoned. When ok is True with reason='incomplete'
        the card just hasn't given us enough data to rule it out — let
        downstream consensus handle it.
        """
        batters = [b.get("name", "")
                   for b in (extracted.get("batters") or [])
                   if b.get("name")]
        bowler_obj = extracted.get("bowler")
        bowler = (bowler_obj.get("name", "")
                  if isinstance(bowler_obj, dict) else "")

        bat_teams = {t for t in (_find_player_team(b) for b in batters)
                     if t}
        bowl_team = _find_player_team(bowler) if bowler else None

        # Need at least one resolved batter AND a resolved bowler to make
        # any judgement. Otherwise: incomplete, defer to consensus.
        if not bat_teams or not bowl_team:
            return True, "incomplete"

        if len(bat_teams) > 1:
            return False, (
                f"batters span multiple teams {sorted(bat_teams)} — "
                f"impossible (batters must be on one team)")

        bat_team = next(iter(bat_teams))
        if bowl_team == bat_team:
            return False, (
                f"bowler ({bowler}) on same team as batters "
                f"({batters}) — both on {bat_team}, impossible")

        return True, "ok"

    # === AGENTS ===
    vision = Vision()
    # Parallel-Scout (design memo §3): a second Groq Scout instance
    # running fire-and-forget after each `vision.describe(...)` call.
    # Constructed only when USE_OPEN_SCOUT=1; otherwise stays None and
    # the per-frame loop becomes a single no-op branch.  See
    # files/docs/operations/parallel_scout_setup.md.
    open_scout: OpenScout | None = None
    open_scout_gate: OpenScoutRateGate | None = None
    open_scout_sidecar = None
    if USE_OPEN_SCOUT:
        try:
            # Layer A — per-frame JSONL sidecar.  Constructed before
            # OpenScout so every classify() and rate-gate skip can
            # write through it.  Layer B (per-span clip+metadata) is
            # wired later via ball_analyzer.attach_open_scout_sidecar
            # because it needs the rolling frame buffer.
            from eyes.openscout_persistence import OpenScoutSidecar
            open_scout_sidecar = OpenScoutSidecar(session_id=SESSION_ID)
            open_scout = OpenScout(sidecar=open_scout_sidecar)
            open_scout_gate = OpenScoutRateGate()
            log.info("[OPEN-SCOUT] enabled (USE_OPEN_SCOUT=1)")
        except Exception as _e:  # noqa: BLE001
            log.warn(f"[OPEN-SCOUT] init failed, disabling: {_e}")
            open_scout = None
            open_scout_gate = None
            open_scout_sidecar = None
    extractor = Extractor()
    scorer = MatchStateAgent()
    jump_guard = ScoreJumpGuard()
    cricket_checker = CricketChecker()
    over_mgr = ThisOverManager()

    # Wire the FOW-upgrade callback (Fix 3): when scoreboard.`_add_fow`
    # upgrades a placeholder W{n} entry to a real wicket with concrete
    # `overs="X.Y"`, ask the over manager to reorder its `this_over`
    # so the W token sits at the correct legal-ball position.  Fixes
    # the "W appended after the boundary" UX bug where wicket-graphics
    # animate before the score-strip catches up.
    scoreboard.on_fow_upgrade = over_mgr.reorder_wicket_to_ball

    # === COMMENTARY TRACKERS ===
    ball_detector = BallEventDetector()
    partnership_tracker = PartnershipTracker()

    # Bug #14: centralized innings-change reset.
    # Called from every code path that flips current_innings → 2.
    # Without this, three "global" trackers (BallEventDetector,
    # PartnershipTracker, ThisOverManager) carry innings-1 state into
    # innings 2 and produce nonsense like:
    #   - partnership "26 runs (-25 balls)" (PT anchor lagging)
    #   - Recent Overs panel showing innings-1 over_history entries
    #   - first ball of innings 2 mis-detected as a -200 score
    #     correction or a 19-ball MULTI_BALL jump
    # `scoreboard.set_innings_2` handles its own internal reset
    # (idempotent via `_innings2_reset_done`); this helper covers
    # the trackers that live OUTSIDE the scoreboard.
    _innings_reset_done_for: set[int] = set()

    # Persistent reference to the most recent Scout delivery
    # classification so the UI keeps showing length / line / shot
    # tags between deliveries (a fresh classification only fires
    # ~once per ball, but every WS broadcast in between should still
    # carry the last known result rather than blanking the panel).
    # Cleared on innings change.
    _last_delivery_info: dict | None = None

    # === Stuck-tracker POISON watchdog (2026-04-20) ===
    # The per-frame POISON delta check blocks extracted data from ever
    # reaching ScoreManager when delta > 7.  If the ScoreManager / tracker
    # locked onto a bad baseline during cold-start (e.g. a pre-match
    # Scout hallucination of "0-0 (0.0)" even though the broadcast is
    # actually at 57-3), every live read hits POISON and the normal
    # stale-recovery path in ScoreManager never sees the rejections.
    # Result: pipeline permanently stuck at 0-0 for the rest of the
    # innings.  Watchdog: count consecutive POISON'd frames whose
    # extracted score agrees with itself (i.e. the broadcast really IS
    # showing a new score).  After N in a row, nuke the tracker's
    # innings score/wickets/overs, force ScoreManager back into
    # COLD_START, and let the next good reads rebuild consensus.
    _poison_streak_new_score: int | None = None
    _poison_streak_count: int = 0
    _POISON_RECAL_THRESHOLD = 5
    _state_recovery = StateRecoveryAggregator(threshold=5)
    _state_recovery_frame_candidate: dict | None = None
    _state_recovery_current: dict | None = None
    _state_recovery_suppressed = True
    _state_recovery_suppress_until_frame = 0

    def _record_state_recovery_guard(
            family: str,
            proposed_reset: list[str] | None = None) -> None:
        _record_state_recovery_ws_guard(
            family, proposed_reset,
            state_recovery=_state_recovery,
            score_mgr=score_mgr,
            scoreboard=scoreboard,
            frame_count=frame_count,
            frame_candidate=_state_recovery_frame_candidate,
            current=_state_recovery_current,
            suppressed=_state_recovery_suppressed,
            log=log)

    # === MONITORING: latency tracking ===
    # _over_change_at_frame: frame number when over change was detected
    # _first_ball_after_over_at_frame: when first ball event arrived
    # _bowler_change_request_at_frame: when scoreboard requested new
    #   bowler; populated when card actually updates
    _over_change_at_frame: int | None = None
    _over_change_at_time: float | None = None
    _bowler_change_request_at_frame: int | None = None
    _bowler_change_request_at_time: float | None = None
    _bowler_change_request_overs: str | None = None

    # === FIELD-FROZEN MONITORING (Fix 5) ===
    # Track when cricket_field positions last changed. The field
    # formation should re-evaluate on every over change / wicket /
    # bowler change. If it stays identical for a long stretch DESPITE
    # those events, we have a separate freeze bug worth investigating.
    # This is *monitoring only* — no behavioural change. Logs a single
    # warning every 30 stale frames so we can correlate with broadcast.
    _field_last_signature: str | None = None
    _field_last_change_frame: int = 0
    _FIELD_FROZEN_WARN_THRESHOLD = 30  # frames (~90s @ 3s/frame)
    _field_frozen_warn_last_at: int = 0

    def reset_for_innings(
            new_innings: int,
            *,
            overs_reset_source: str | None = None) -> None:
        nonlocal _last_delivery_info
        if new_innings in _innings_reset_done_for:
            return
        _innings_reset_done_for.add(new_innings)
        ball_detector.reset()
        partnership_tracker.reset()
        over_mgr.reset()
        _last_delivery_info = None
        _tr = getattr(scoreboard, "_tracker", None)
        if _tr is not None:
            _tr.reset_overs_consensus()
            if overs_reset_source:
                log.info(
                    "  [OVERS-TRACKER-RESET] "
                    f"source={overs_reset_source} "
                    f"innings={new_innings}")
        log.info(f"  [INNINGS] Trackers reset for innings {new_innings}")

    # Centralised innings-change execution (Rule 2). Triggered by the
    # deterministic 20-over / 10-wicket triggers OR the broadcast-signal
    # consensus path. Idempotent: scoreboard.set_innings_2 + the
    # _innings_reset_done_for tracker each guard against double-firing.
    def execute_innings_change(source: str, target: int | None = None) -> bool:
        nonlocal team_locked, _bowling_team_strip_count
        nonlocal pending_innings_2, pending_target, _inn2_consecutive
        nonlocal batting_team, bowling_team
        nonlocal _inn_break_pending, _inn_break_pending_frame
        nonlocal _inn_break_pending_source
        nonlocal _inn1_batting_team_latched, _inn1_bowling_team_latched
        nonlocal _inn1_completed_deterministic
        _out = _execute_innings_change_from_state(
            source=source,
            target=target,
            scoreboard=scoreboard,
            score_mgr=score_mgr,
            ball_analyzer=ball_analyzer,
            log=log,
            frame_count=frame_count,
            team_locked=team_locked,
            bowling_team_strip_count=_bowling_team_strip_count,
            pending_innings_2=pending_innings_2,
            pending_target=pending_target,
            inn2_consecutive=_inn2_consecutive,
            batting_team=batting_team,
            bowling_team=bowling_team,
            inn_break_pending=_inn_break_pending,
            inn_break_pending_frame=_inn_break_pending_frame,
            inn_break_pending_source=_inn_break_pending_source,
            inn1_batting_team_latched=_inn1_batting_team_latched,
            inn1_bowling_team_latched=_inn1_bowling_team_latched,
            inn1_completed_deterministic=_inn1_completed_deterministic,
            assign_teams_cb=assign_teams,
            reset_for_innings_cb=reset_for_innings,
        )
        if not _out["did_change"]:
            return False
        team_locked = _out["team_locked"]
        _bowling_team_strip_count = _out["bowling_team_strip_count"]
        pending_innings_2 = _out["pending_innings_2"]
        pending_target = _out["pending_target"]
        _inn2_consecutive = _out["inn2_consecutive"]
        batting_team = _out["batting_team"]
        bowling_team = _out["bowling_team"]
        _inn_break_pending = _out["inn_break_pending"]
        _inn_break_pending_frame = _out["inn_break_pending_frame"]
        _inn_break_pending_source = _out["inn_break_pending_source"]
        _inn1_batting_team_latched = _out["inn1_batting_team_latched"]
        _inn1_bowling_team_latched = _out["inn1_bowling_team_latched"]
        _inn1_completed_deterministic = _out["inn1_completed_deterministic"]
        return True

    # === SCORE MANAGER (live mode — events drive Wire commentary) ===
    score_mgr = ScoreManager(shadow=False)
    # Attach the scoreboard so SM can canonicalize raw scout names
    # ("N RANA", "Rahul") to canonical squad keys ("Nitish Rana",
    # "KL Rahul") at the single entry point (_build_scorecard).  Without
    # this, `score_mgr.striker` / `bat1_name` stay raw, the UI's
    # `batting_card[i].is_striker = (name == striker)` comparison always
    # fails, and no batter is highlighted as striker.  Issue 1 fix.
    score_mgr.scoreboard = scoreboard
    current_action: str | None = None
    pending_action: str | None = None

    # === DRS STATE MACHINE ===
    _DRS_CONFIRM_FRAMES = 3
    _drs_state = "NONE"        # NONE → DETECTING → IN_PROGRESS → RESOLVED
    _drs_streak = 0
    _drs_grace = 0             # frames without DRS signal before resetting
    _DRS_GRACE_WINDOW = 3      # allow up to 3 non-DRS frames before reset
    _drs_pre_state: dict | None = None  # snapshot before DRS
    _drs_commentary_emitted = False
    _drs_resolve_wait = 0      # frames to wait after DRS exit before resolving
    _DRS_RESOLVE_DELAY = 3     # wait 3 frames for scoreboard to settle
    _drs_pending_resolve = False

    # === BROADCAST DATA CACHE (session-level, set once by extract_broadcast_data) ===
    _broadcast_cache: dict = {}
    _last_dismissal_mode: str | None = None
    # S4: track when dismissal_mode was set so we can age it out even
    # in the absence of a clearing ball event (broadcast graphics for
    # a single delivery shouldn't keep "BOWLED" sticky for minutes).
    _last_dismissal_mode_frame: int = 0
    _DISMISSAL_MODE_TTL_FRAMES = 8
    # === #13: event-driven invalidation across back-to-back wickets ===
    # When a death-over collapse fires W{N} and W{N+1} inside the same
    # 8-frame TTL window, the WICKET handler used to inherit the
    # previous wicket's dismissal_mode (set by W{N}'s broadcast
    # graphic, never refreshed before W{N+1}) and mis-attribute the
    # second dismissal as the same kind.  Track whether the mode has
    # already been consumed by a WICKET event; if so, the next WICKET
    # must NOT inherit it — it must rely on its own broadcast graphic
    # / ring-buffer hint or fall back to None ("inferred").  Honest
    # "inferred" beats wrong "bowled".
    _last_dismissal_mode_consumed: bool = False

    # === S17: dismissal-hint ring buffer ===
    # The wicket frame itself often carries no dismissal_mode in the
    # broadcast strip — the "BOWLED b. Narine" graphic can fire 1-3
    # frames BEFORE the score updates to W+1, and the action LLM has
    # already described the dismissal in plain English ("walking off
    # after getting stumped"). When the WICKET event finally fires we
    # scan this buffer for the most recent hint, so the FOW entry +
    # `dismissal_mode` payload field carry the right kind. Five-frame
    # window ≈ 2.5s at burst rate — wide enough to catch the broadcast
    # graphic, narrow enough to not pick up the previous wicket.
    # Was 5 — too short.  The extractor commonly takes 10-20 frames
    # to surface a new batter after a wicket (broadcast cuts to slow-
    # motion replays, dismissal graphics, crowd reactions before the
    # incoming batter reaches the crease and the strip refreshes), so
    # the hint aged out before `_auto_dismiss_for_new_batter` had a
    # chance to consume it.  Verified on KKR-vs-RR W6 (Jadeja bowled
    # Tyagi at F108, Archer first surfaced ~F125, FOW filed with
    # generic "inferred (replaced by new batter)" instead of
    # "bowled").  Each WICKET handler re-sets the hint with the
    # current frame, so the stale-graphic risk that 5 was protecting
    # against is bounded by "next confirmed wicket".
    _DISMISSAL_HINT_WINDOW = 30
    _recent_dismissal_hints: list[dict] = []  # [{frame, mode, source, fielder, bowler}]
    _DISMISSAL_KEYWORDS = {
        "stumped":  "stumped",
        "stumping": "stumped",
        "caught":   "caught",
        "catches":  "caught",
        "bowled":   "bowled",
        "lbw":      "lbw",
        "leg before": "lbw",
        "run out":  "run out",
        "run-out":  "run out",
        "runout":   "run out",
        "hit wicket": "hit wicket",
    }

    def _scan_dismissal_keyword(text: str) -> str | None:
        if not text:
            return None
        _t = text.lower()
        for kw, mode in _DISMISSAL_KEYWORDS.items():
            if kw in _t:
                return mode
        return None

    def _record_dismissal_hint(frame_num: int, mode: str, source: str):
        nonlocal _recent_dismissal_hints
        _recent_dismissal_hints.append({
            "frame": frame_num,
            "mode": mode,
            "source": source,
        })
        # Trim to window
        _cutoff = frame_num - _DISMISSAL_HINT_WINDOW
        _recent_dismissal_hints = [
            h for h in _recent_dismissal_hints if h["frame"] >= _cutoff
        ]

    def _consume_dismissal_hint(frame_num: int) -> str | None:
        """Pop the most recent in-window hint, if any."""
        nonlocal _recent_dismissal_hints
        _cutoff = frame_num - _DISMISSAL_HINT_WINDOW
        _in_window = [h for h in _recent_dismissal_hints if h["frame"] >= _cutoff]
        if not _in_window:
            return None
        # Most recent wins
        _hit = sorted(_in_window, key=lambda h: h["frame"])[-1]
        # Clear the window — this hint belongs to THIS wicket only.
        _recent_dismissal_hints = []
        return _hit["mode"]

    # === FIELD TRACKING (local, every frame) ===
    field_state = FieldState()
    field_detector = FieldDetector()
    field_changes = FieldChangeDetector()
    field_merger = FieldMerger()
    field_validator = FieldValidator()
    field_log = CricketLogger("FIELD")
    cricket_field = CricketField()
    _last_bowler_for_field: str | None = None

    # === FRAMES ===
    # FRAME_SOURCE=capture_card → UGREEN HDMI→USB (production default,
    # browser-independent, hardware-rate). Skip the Firefox window
    # discovery dance entirely in that mode.
    # FRAME_SOURCE=window      → legacy Quartz CGWindowList against
    # the Firefox tab (throttled when backgrounded; kept for fallback).
    firefox_wid = None
    firefox_onscreen = False
    if _FRAME_SOURCE_MODE == "capture_card":
        log.info("Frame source: capture_card "
                 "(skipping Firefox window discovery)")
        frames = make_frame_source(fps=CAPTURE_FPS, source="capture_card")
    elif _FRAME_SOURCE_MODE == "file":
        file_path = os.environ.get("FRAME_SOURCE_FILE")
        log.info("Frame source: file replay "
                 f"(path={file_path!r}, "
                 f"offset_s={os.environ.get('FRAME_SOURCE_FILE_OFFSET_S','0')}, "
                 f"loop={os.environ.get('FRAME_SOURCE_FILE_LOOP','0')})")
        frames = make_frame_source(fps=CAPTURE_FPS, source="file",
                                   video_path=file_path)
    elif _FRAME_SOURCE_MODE == "udp":
        log.info("Frame source: udp "
                 f"(url={os.environ.get('FRAME_SOURCE_UDP_URL', '<default>')}, "
                 f"watchdog_s={os.environ.get('FRAME_SOURCE_UDP_WATCHDOG_S','5.0')}, "
                 f"startup_grace_s={os.environ.get('FRAME_SOURCE_UDP_STARTUP_GRACE_S','15.0')})")
        frames = make_frame_source(fps=CAPTURE_FPS, source="udp")
    else:
        for w in FrameSource.list_windows():
            if "firefox" in w["owner"].lower():
                firefox_wid = w["id"]
                firefox_onscreen = True
                log.info(f"Found Firefox window (on-screen): id={w['id']} "
                         f"{w['width']}x{w['height']} \"{w['name'][:60]}\"")
                break
        if not firefox_wid:
            try:
                import Quartz
                all_wins = Quartz.CGWindowListCopyWindowInfo(
                    Quartz.kCGWindowListOptionAll
                    | Quartz.kCGWindowListExcludeDesktopElements,
                    Quartz.kCGNullWindowID,
                )
                for w in all_wins:
                    owner = w.get(Quartz.kCGWindowOwnerName, "")
                    bounds = w.get(Quartz.kCGWindowBounds, {})
                    width = bounds.get("Width", 0)
                    height = bounds.get("Height", 0)
                    if ("firefox" in owner.lower()
                            and width > 500 and height > 500):
                        firefox_wid = w.get(Quartz.kCGWindowNumber, 0)
                        name = w.get(Quartz.kCGWindowName, "")
                        log.warn(
                            f"Firefox is OFFSCREEN — capture may return stale "
                            f"frames! id={firefox_wid} {width}x{height} "
                            f"\"{name[:60]}\"")
                        log.warn(
                            ">>> Please move Firefox to the current desktop <<<")
                        break
            except Exception:
                pass

        if firefox_wid:
            frames = make_frame_source(window_id=firefox_wid,
                                       fps=CAPTURE_FPS, source="window")
        else:
            log.warn("Firefox not found — falling back to full screen capture")
            frames = FrameSource(fps=CAPTURE_FPS)
    frames.start()

    ball_analyzer: BallAnalyzer | None = None
    if firefox_wid or _FRAME_SOURCE_MODE in ("capture_card", "file", "udp"):
        # window_id is ignored when BallAnalyzer's own FRAME_SOURCE
        # resolves to capture_card; pass 0 as a harmless placeholder.
        # UDPFrameSource has the same get_latest_with_ts/get_frame_count
        # API as FileFrameSource — pass it through file_frame_source so
        # BallAnalyzer uses the externally-managed instance instead of
        # building its own internal source.
        ball_analyzer = BallAnalyzer(
            window_id=firefox_wid or 0,
            file_frame_source=(
                frames if _FRAME_SOURCE_MODE in ("file", "udp") else None),
        )
        ball_analyzer.start()
        log.info("[BALL ANALYZER] Background capture started "
                 f"(source={_FRAME_SOURCE_MODE})")
        # Layer B wiring — OpenScoutDeliveryWriter on SpanAggregator
        # committed callback (validation clips; no DWR coupling).
        if open_scout_sidecar is not None:
            try:
                ball_analyzer.attach_open_scout_sidecar(
                    open_scout_sidecar)
            except Exception as _e:  # noqa: BLE001
                log.warn(
                    f"[OPEN-SCOUT-DELIVERY] attach failed: {_e}")
        # Component 3 — OpenScout shadow-mode runner. No-op unless
        # SHADOW_MODE=1. See files/docs/investigations/
        # openscout_shadow_runner.md.
        try:
            from openscout_shadow.pipeline_hook import attach_shadow_runner
            shadow_runner = attach_shadow_runner(
                ball_analyzer, session_id=SESSION_ID)
            if shadow_runner is not None:
                try:
                    ball_analyzer.attach_stage2_span_lookup(
                        shadow_runner.find_stage2_span_for_event)
                except Exception as _e:  # noqa: BLE001
                    log.warning(
                        f"[SHADOW] stage2 lookup attach failed: {_e}")
        except Exception as _e:  # noqa: BLE001
            log.warning(f"[SHADOW] attach failed: {_e}")
            shadow_runner = None
    else:
        shadow_runner = None

    # ── Decoupled OpenScout loop ──
    # When OPENSCOUT_DECOUPLED=1, spawn the dedicated coroutine that
    # polls the capture frame source at OPENSCOUT_DECOUPLED_TARGET_
    # INTERVAL_S cadence, independent of main pipeline iteration timing.
    # See files/docs/operations/openscout_decoupled_setup.md.
    openscout_task: asyncio.Task | None = None
    openscout_slot: LatestFrameSlot | None = None
    openscout_tpm_budget: TPMBudget | None = None
    if (OPENSCOUT_DECOUPLED and open_scout is not None
            and open_scout_gate is not None):
        try:
            openscout_slot = LatestFrameSlot(source_fn=frames.get_latest)
            openscout_tpm_budget = TPMBudget(cap=OPENSCOUT_TPM_BUDGET)

            # ── Continuous chunker (score-event-decoupled detector) ──
            # Instantiate the streaming v3 state machine + auto clip
            # writer when USE_CONTINUOUS_CHUNKER=1.  Runs entirely
            # parallel to the score-event-driven DeliveryWindowRecorder.
            continuous_chunker = None
            auto_delivery_recorder = None
            if USE_CONTINUOUS_CHUNKER:
                try:
                    from eyes.continuous_chunker import ContinuousChunker
                    from eyes.auto_delivery_recorder import (
                        AutoDeliveryRecorder)
                    auto_delivery_recorder = AutoDeliveryRecorder(
                        session_id=SESSION_ID,
                        frame_slice_fn=ball_analyzer._frame_source,
                    )

                    def _cc_event_sink(event):
                        log.info(
                            f"[DELIVERY-DETECTED] "
                            f"start={event.start_ts:.3f} "
                            f"end={event.end_ts:.3f} "
                            f"dur={event.duration_s:.2f}s "
                            f"anchors={event.anchor_frames} "
                            f"conf={event.confidence_score:.2f}")
                        try:
                            auto_delivery_recorder(event)
                        except Exception:  # noqa: BLE001
                            log.exception(
                                "[AUTO-CLIP-WRITE-FAIL] recorder raised")

                    continuous_chunker = ContinuousChunker(
                        min_clip_duration_s=(
                            CONTINUOUS_CHUNKER_MIN_DURATION_S),
                        max_clip_duration_s=(
                            CONTINUOUS_CHUNKER_MAX_DURATION_S),
                        min_event_gap_s=(
                            CONTINUOUS_CHUNKER_MIN_EVENT_GAP_S),
                        min_confidence=(
                            CONTINUOUS_CHUNKER_MIN_CONFIDENCE),
                        event_sink=_cc_event_sink,
                    )
                    log.info(
                        f"[CONTINUOUS-CHUNKER-STATE] "
                        f"init "
                        f"min_dur_s={CONTINUOUS_CHUNKER_MIN_DURATION_S} "
                        f"max_dur_s={CONTINUOUS_CHUNKER_MAX_DURATION_S} "
                        f"min_gap_s={CONTINUOUS_CHUNKER_MIN_EVENT_GAP_S} "
                        f"min_conf={CONTINUOUS_CHUNKER_MIN_CONFIDENCE}")
                except Exception as _e:  # noqa: BLE001
                    log.warning(
                        f"[CONTINUOUS-CHUNKER-STATE] init_failed err={_e!r}")
                    continuous_chunker = None
                    auto_delivery_recorder = None

            def _open_scout_result_sink(res):
                try:
                    if ball_analyzer is not None:
                        ball_analyzer.record_open_classification(
                            res.timestamp,
                            res.frame_class,
                            res.raw_description,
                        )
                except Exception:  # noqa: BLE001
                    log.exception(
                        "[OPEN-SCOUT-LOOP] record_open_classification failed")
                # Chunker v3 shadow feed — closes over `vision` so the
                # cam/phase/broadcast_tag attached to this Scout call
                # come from the same frame.  No-op when
                # USE_V3_CHUNKER=0 (record_v3_frame guards on the
                # aggregator).
                try:
                    if ball_analyzer is not None:
                        ball_analyzer.record_v3_frame(
                            res.timestamp,
                            prod_cam=getattr(
                                vision, "last_camera_view", None),
                            prod_phase=getattr(
                                vision, "last_frame_phase", None),
                            v2_broadcast_tag=getattr(
                                res, "v2_broadcast_tag", "") or "",
                            v2_class=res.frame_class,
                            open_desc=res.raw_description,
                        )
                except Exception:  # noqa: BLE001
                    log.exception(
                        "[CHUNKER-V3] record_v3_frame failed")
                # Continuous chunker — score-event-decoupled detector.
                # Runs the v3 per-frame state machine and emits
                # auto/dNNN clips on cluster close.
                if continuous_chunker is not None:
                    try:
                        continuous_chunker.ingest(
                            res.timestamp,
                            prod_cam=getattr(
                                vision, "last_camera_view", None),
                            prod_phase=getattr(
                                vision, "last_frame_phase", None),
                            v2_broadcast_tag=getattr(
                                res, "v2_broadcast_tag", "") or "",
                            v2_class=res.frame_class,
                            open_desc=res.raw_description,
                        )
                    except Exception:  # noqa: BLE001
                        log.exception(
                            "[CONTINUOUS-CHUNKER-STATE] ingest failed")
                if shadow_runner is not None:
                    try:
                        shadow_runner.add_scout_result({
                            "ts": res.timestamp,
                            "frame_class": res.frame_class,
                            "raw_description": res.raw_description,
                        })
                    except Exception:  # noqa: BLE001
                        log.exception(
                            "[OPEN-SCOUT-LOOP] shadow add_scout_result failed")
                # Shadow v3 delivery detector (env-gated, non-blocking).
                if _shadow_delivery_detector is not None:
                    try:
                        _shadow_delivery_detector.add_scout_result(
                            res.timestamp, res.frame_class,
                            res.raw_description)
                    except Exception:  # noqa: BLE001
                        log.exception(
                            "[SHADOW-DELIVERY] add_scout_result failed")

            openscout_task = asyncio.create_task(openscout_loop(
                slot=openscout_slot,
                open_scout=open_scout,
                gate=open_scout_gate,
                tpm_budget=openscout_tpm_budget,
                target_interval_s=OPENSCOUT_DECOUPLED_TARGET_INTERVAL_S,
                result_sink=_open_scout_result_sink,
                capture_alive_fn=(
                    lambda: bool(getattr(ball_analyzer, "alive", True))),
                camera_view_fn=(
                    lambda: getattr(vision, "last_camera_view", None)),
                frame_phase_fn=(
                    lambda: getattr(vision, "last_frame_phase", None)),
            ))
            log.info(
                f"[OPEN-SCOUT-LOOP] decoupled loop spawned, "
                f"target={OPENSCOUT_DECOUPLED_TARGET_INTERVAL_S:.2f}s, "
                f"tpm_cap={OPENSCOUT_TPM_BUDGET}")
        except Exception as _e:  # noqa: BLE001
            log.warning(
                f"[OPEN-SCOUT-LOOP] decoupled spawn failed: {_e}; "
                f"falling back to inline path")
            openscout_task = None
            openscout_slot = None
            openscout_tpm_budget = None

    match_recorder_task: asyncio.Task | None = None
    if RECORD_FULL_MATCH:
        try:
            _mr_slot = LatestFrameSlot(source_fn=frames.get_latest)
            match_recorder_task = asyncio.create_task(match_recorder(
                slot=_mr_slot,
                session_id=SESSION_ID,
                fps=RECORD_FULL_MATCH_FPS,
            ))
        except Exception as _e:  # noqa: BLE001
            log.warning(f"[MATCH-RECORDER] spawn failed: {_e}")
            match_recorder_task = None

    await asyncio.sleep(1)

    # Auto-detect pitch center from first few frames using people clusters
    for _attempt in range(10):
        _raw = frames.get_latest()
        if _raw is not None:
            _f = downscale(_raw, FRAME_WIDTH)
            _dots = field_detector.detect_people(_f)
            if len(_dots) >= 8:
                if field_detector.auto_detect_pitch_from_people(_dots):
                    field_log.info(
                        f"Pitch detected from people at "
                        f"({field_detector.pitch_center['x']:.2f}, "
                        f"{field_detector.pitch_center['y']:.2f})")
                    break
            elif field_detector.auto_detect_pitch(_f):
                field_log.info(
                    f"Pitch detected from green mask at "
                    f"({field_detector.pitch_center['x']:.2f}, "
                    f"{field_detector.pitch_center['y']:.2f}) "
                    f"(fallback — will recalibrate from people)")
                break
        await asyncio.sleep(0.5)
    else:
        field_log.info("Pitch not detected — using default (0.50, 0.70)")

    frame_count = 0
    processed = 0
    skipped_pixel = 0
    skipped_no_strip = 0  # no-text-band in bottom region (pre-Scout)
    skipped_no_strip_total = 0  # lifetime counter for final summary
    skipped_ad = 0
    skipped_context = 0
    skipped_dead_view = 0  # camera_view in {replay,graphic,ad,other}
    _ad_streak_start: float | None = None
    _in_strategic_timeout: bool = False
    vision_hint = None
    prev_strip = None
    adaptive = AdaptiveSleep()
    # Dead-time skip transition flag (Phase 2.5 — 2026-04-18).  Set
    # True whenever we skip the LLM extract+scorer chain because
    # Scout's `camera_view` reported dead time.  Cleared on the first
    # active-play frame after the gap, with a one-line log entry so
    # we can audit dead → active transitions.
    _was_dead_time = False
    _cam_graphic_fp_cooldown = deque(maxlen=_FAST_PATH_COOLDOWN_MAXLEN)
    _prev_vision_frame_type: str | None = None
    # P3 — N-frame debounce window. Set to OVERLAY_WINDOW_FRAMES whenever
    # any GRAPHIC-FILTER mode (A/B/C) fires; decremented at the top of
    # each subsequent frame iteration.
    _overlay_window_remaining: int = 0

    last_broadcast_time = 0.0

    def _canon_player_name(raw, *, bowler: bool = False):
        return _ws_canonicalize_player_name(
            raw, scoreboard=scoreboard, bowler=bowler)

    def _assert_payload_invariants(payload):
        _assert_ws_payload_invariants(payload, log=log)

    def build_full_payload(speed_kph=None):
        """Build the SINGLE canonical payload — used everywhere."""
        return _build_full_payload_from_state(
            scoreboard=scoreboard,
            score_mgr=score_mgr,
            over_mgr=over_mgr,
            partnership_tracker=partnership_tracker,
            cricket_field=cricket_field,
            team_names=team_names,
            batting_team=batting_team,
            bowling_team=bowling_team,
            toss_winner_name=toss_winner_name,
            toss_decision_str=toss_decision_str,
            frame_count=frame_count,
            last_delivery_info=_last_delivery_info,
            broadcast_cache=_broadcast_cache,
            speed_kph=speed_kph,
            canon_player_name=_canon_player_name,
            record_state_recovery_guard=_record_state_recovery_guard,
            assert_payload_invariants=_assert_payload_invariants,
        )

    async def broadcast_base():
        """Broadcast full state at regular intervals."""
        nonlocal last_broadcast_time
        now = time.time()
        if now - last_broadcast_time < 1.0:
            return
        last_broadcast_time = now
        try:
            payload = build_full_payload()
            await broadcast_state(payload)
        except Exception as e:
            log.error(f"broadcast_base error: {e}")

    # === STARTUP CLEANUP ===
    # Move existing frames to a dated subdir under
    # `debug_frames_archive/` rather than deleting outright, so that
    # any in-flight evaluation work (e.g. a stratified V5/V6 prod-eval
    # JSON whose path field points at `debug_frames/...`) survives a
    # mid-session pipeline restart.  Retention cap bounds disk usage.
    _archive_old_debug_frames()

    # === CACHE POLICY (Rule 1 → validated hot-resume, 2026-05-11) ===
    # Identity-validated hot-resume replaces the legacy always-discard
    # policy. A cached snapshot is restored as authoritative when:
    #   - match_id matches the current CRICBUZZ_MATCH_ID
    #   - session_id differs from the live SESSION_ID (real restart,
    #     not a same-session write-flush)
    #   - cache age < 3600s (60 min)
    #   - score / wickets / overs all non-null in the cache
    # On identity failure we fall back to the legacy cold-start path
    # (toss data still preserved). Validation against the first non-null
    # broadcast read happens in the frame loop body and reverts to
    # COLD_START on divergence.
    cached_state = load_match_state()
    hot_resume_ok = False
    hot_resume_validate_pending = False
    if cached_state:
        cached_match_id = cached_state.get("match_id")
        current_match_id = os.environ.get("CRICBUZZ_MATCH_ID")
        cached_session_id = cached_state.get("session_id")
        current_session_id = SESSION_ID
        cache_age_s = time.time() - (cached_state.get("saved_at") or 0)
        identity_ok = (
            cached_match_id == current_match_id
            and cached_session_id != current_session_id
            and cache_age_s < 3600)
        if not identity_ok:
            log.info(
                f"[CACHE] hot-resume identity reject — "
                f"match_id_match={cached_match_id == current_match_id} "
                f"session_diff={cached_session_id != current_session_id} "
                f"age_s={cache_age_s:.0f} (limit=3600). "
                f"Falling back to cold-start.")
        else:
            cached_card_complete = all(
                cached_state.get(k) is not None
                for k in ("score", "wickets", "overs"))
            if cached_card_complete:
                scoreboard.restore_from_cache(cached_state)
                score_mgr.hot_resume_from_cache(cached_state, frame=0)
                hot_resume_ok = True
                hot_resume_validate_pending = True
                try:
                    _TRACE_RECORDER.record(
                        tag="HOT_RESUME",
                        score=cached_state.get("score"),
                        wickets=cached_state.get("wickets"),
                        overs=cached_state.get("overs"),
                        innings=cached_state.get("innings"),
                        match_id=cached_match_id,
                        cache_age_s=cache_age_s)
                except Exception:
                    pass
            else:
                log.info(
                    "[CACHE] hot-resume skipped — cached "
                    "score/wickets/overs has nulls")
        # Toss data is always preserved when fresh (3600s window).
        if (cached_state.get("toss_winner") and not toss_winner_name
                and cache_age_s < 3600):
            toss_winner_name = cached_state["toss_winner"]
            toss_decision_str = cached_state.get("toss_decision")
            toss_captured = True
            log.info(
                f"[CACHE] Toss restored: {toss_winner_name} - "
                f"{toss_decision_str}")
        if not hot_resume_ok:
            log.info("[CACHE] cold-start path active (no valid hot-resume)")
    else:
        log.info("[CACHE] No cached state found — starting fresh")

    # === HARD TEAM OVERRIDE (env var) ===
    # Set FORCE_BATTING_TEAM=KKR (or full name) to lock the batting team
    # before the pipeline starts. This bypasses Scout's team-from-strip
    # heuristic, which can be fooled when Scout hallucinates the strip.
    _force_bat = (os.environ.get("FORCE_BATTING_TEAM") or "").strip()
    if _force_bat:
        _force_resolved = _resolve_team_variant(_force_bat)
        if _force_resolved and _force_resolved in team_names:
            _force_bowl = next((t for t in team_names
                                if t != _force_resolved), None)
            if _force_bowl:
                if batting_team and batting_team != _force_resolved:
                    log.info(f"[FORCE] Override: was {batting_team} batting, "
                             f"forcing {_force_resolved} batting")
                else:
                    log.info(f"[FORCE] Locking {_force_resolved} batting "
                             f"vs {_force_bowl} bowling")
                assign_teams(_force_resolved, _force_bowl, innings=1)
                team_locked = True
                team_lock_frame = 0
        else:
            log.error(f"[FORCE] FORCE_BATTING_TEAM={_force_bat!r} did not "
                      f"resolve to a known team {team_names}")

    # === HARD INNINGS OVERRIDE (env var) ===
    # Set FORCE_INNINGS=2 when starting the pipeline mid-innings-2 from a
    # cleared cache. Without this override, the 20-over guard correctly
    # refuses to promote innings 1 → 2 on a target panel (because the
    # pipeline freshly thinks it is in innings 1 at low overs), so the
    # pipeline would stay in innings 1 forever.
    # Treats the restart as DETECTION, not TRANSITION — calls
    # `set_innings_2` once to reset trackers and then marks both reset
    # flags so subsequent target-panel detections are no-ops.
    _force_innings = (os.environ.get("FORCE_INNINGS") or "").strip()
    if _force_innings == "2":
        _force_target_str = (os.environ.get("FORCE_TARGET") or "").strip()
        _force_target = (int(_force_target_str)
                         if _force_target_str.isdigit() else None)
        scoreboard.set_innings_2(target=_force_target)
        if ball_analyzer:
            ball_analyzer.on_innings_change(2)
        reset_for_innings(2, overs_reset_source="FORCE_INNINGS_ENV")
        _innings_reset_done_for.add(2)
        scoreboard._innings2_reset_done = True
        log.info(
            f"[FORCE] Innings forced to 2 "
            f"(target={_force_target}). "
            f"Restart treated as detection, not transition.")

    log.info("=" * 60)
    log.info("[CONFIG] Vision:    Scout 17B (single call tag+read)")
    log.info("[CONFIG] Extractor: Groq (Scout 17B → 8B fallback)")
    log.info("[CONFIG] Scorer:    Groq (Scout 17B → 8B fallback)")
    log.info(f"PIPELINE STARTED — {TEST_DURATION}s — NO TEAM ASSUMPTION")
    log.info("=" * 60)

    try:
        while (time.time() - start) < TEST_DURATION:
            raw = frames.get_latest()
            if raw is None:
                await asyncio.sleep(0.2)
                continue

            frame_count += 1
            try:
                score_mgr.last_cold_start_verdict_implausible = False
            except Exception:
                pass
            set_global_frame(frame_count)
            try:
                _TRACE_RECORDER.begin_frame(frame_count)
            except Exception:
                pass
            # Component 3 — every ~60 s at 30 fps emit a structured
            # ``[SHADOW-STATS]`` heartbeat so live_match_monitor.py can
            # render a shadow panel and analyze_trace.py can confirm
            # liveness post-match.  See files/docs/investigations/
            # match_monitoring_plan_pre_live.md §4.6.
            if frame_count % 30 == 0 and shadow_runner is not None:
                try:
                    log.info(f"[SHADOW-STATS] {shadow_runner.stats()}")
                except Exception as _e:  # noqa: BLE001
                    log.warning(f"[SHADOW-STATS] failed: {_e}")

            # Live-monitoring v1: 5-min OPEN-SCOUT-STATS +
            # CHUNKER-V3-STATS rolling snapshots.  Emission is
            # gated on wall clock so the cadence holds even if
            # frames arrive irregularly.
            _now_wall = time.time()
            if _MONITORING_MATCH_START_TS == 0.0:
                _MONITORING_MATCH_START_TS = _now_wall
                _MONITORING_LAST_5MIN_EMIT_TS = _now_wall
            if (_now_wall - _MONITORING_LAST_5MIN_EMIT_TS) >= 300.0:
                try:
                    from monitoring_emitters import (
                        OpenScoutStatsCounters,
                        emit_chunker_v3_stats,
                        emit_open_scout_stats,
                    )
                    if open_scout is not None:
                        _scout_snap = OpenScoutStatsCounters(
                            class_counts=collections.Counter(
                                open_scout.window_class_counts),
                            latencies_ms=list(
                                open_scout.window_latencies_ms),
                            inter_call_gaps_s=list(
                                open_scout.window_inter_call_gaps_s),
                        )
                        emit_open_scout_stats(_scout_snap, window_min=5,
                                              logger=log)
                        open_scout.window_class_counts.clear()
                        open_scout.window_latencies_ms.clear()
                        open_scout.window_inter_call_gaps_s.clear()
                    if (ball_analyzer is not None
                            and getattr(ball_analyzer, "_recorder", None)
                            is not None):
                        from monitoring_emitters import (
                            check_v3_fallback_alarm)
                        _v3c = ball_analyzer._recorder._v3_stats_counters
                        _alarm_msg = check_v3_fallback_alarm(
                            _v3c, window_min=5)
                        emit_chunker_v3_stats(_v3c, window_min=5, logger=log)
                        if _alarm_msg is not None:
                            log.warn(_alarm_msg)
                except Exception as _e:  # noqa: BLE001
                    log.warning(f"[MONITORING-5MIN] failed: {_e}")
                _MONITORING_LAST_5MIN_EMIT_TS = _now_wall
            frame = downscale(raw, FRAME_WIDTH)

            # === S17: age out scoreboard.pending_dismissal_hint if it
            # outlives the dismissal window. Otherwise a hint observed
            # before any wicket would taint a future wicket whose own
            # capture path failed. ===
            _pdh_frame = getattr(
                scoreboard, "pending_dismissal_hint_frame", 0)
            if (getattr(scoreboard, "pending_dismissal_hint", None)
                    and _pdh_frame
                    and frame_count - _pdh_frame > _DISMISSAL_HINT_WINDOW):
                log.info(
                    f"  [DISMISSAL-HINT-CLEAR] "
                    f"{scoreboard.pending_dismissal_hint!r} aged out "
                    f"({frame_count - _pdh_frame} frames since seen)")
                scoreboard.pending_dismissal_hint = None
                scoreboard.pending_dismissal_bowler = None
                scoreboard.pending_dismissal_hint_frame = 0

            # === FIELD TRACKING (YOLO local, every frame, ~50ms) ===
            ft0 = time.time()
            dots = field_detector.detect_people(frame)

            # Re-calibrate pitch from people if not yet done
            if len(dots) >= 8 and not field_detector.pitch_calibrated:
                field_detector.auto_detect_pitch_from_people(dots)

            fielders = field_detector.filter_fielders(dots)
            yolo_positions = (field_detector.classify_zones(fielders)
                              if len(fielders) >= 2 else [])
            ft_ms = (time.time() - ft0) * 1000
            _vision_field: dict | None = None

            h = frame.shape[0]
            strip_region = frame[int(h * 0.85):, :]

            # Fix D (2026-04-22): force-process threshold 10 → 4.
            # With the old threshold of 10 and a ~2s-per-frame cadence,
            # a static broadcast period could suppress processing for
            # ~20s, which is longer than the gap between deliveries.
            # On return to live action the state would lag an entire
            # delivery behind.  Threshold 4 caps suppression to ~8s
            # while still filtering the truly redundant still frames.
            _PIXEL_SKIP_FORCE_THRESHOLD = 4
            if frame_count > 10 and not frame_changed(
                    strip_region, prev_strip, threshold=0.008):
                skipped_pixel += 1
                if skipped_pixel % _PIXEL_SKIP_FORCE_THRESHOLD == 0:
                    log.info(f"[F{frame_count}] Pixel skip #{skipped_pixel}")
                    cv2.imwrite(
                        f"debug_frames/f{frame_count}_pixskip.jpg", frame)
                if skipped_pixel >= _PIXEL_SKIP_FORCE_THRESHOLD:
                    log.info(f"[F{frame_count}] Force-processing after "
                             f"{skipped_pixel} pixel skips")
                    skipped_pixel = 0
                    prev_strip = None
                else:
                    await broadcast_base()
                    await asyncio.sleep(0.5)
                    continue
            prev_strip = strip_region.copy()

            # === STRIP PRESENCE GATE (Issue 4 — pre-Scout filter) ===
            # Skip Scout + Extractor + Scorer entirely on frames whose
            # bottom band doesn't contain a text-like scoreboard.  The
            # gate is grad-based (text → strong horizontal strokes)
            # and is calibrated to skip ~84% of closeup / crowd / ad
            # frames that would otherwise FRAME_POISON downstream.
            #
            # Safety valve: every ``_NO_STRIP_FORCE_EVERY`` consecutive
            # no-strip skips we still fire one full pipeline pass so
            # an unlucky calibration can't starve the scoreboard.
            _NO_STRIP_FORCE_EVERY = 12
            if (frame_count > 10
                    and not _strip_has_text_band(strip_region)):
                skipped_no_strip += 1
                skipped_no_strip_total += 1
                if skipped_no_strip >= _NO_STRIP_FORCE_EVERY:
                    log.info(
                        f"[F{frame_count}] Force-processing after "
                        f"{skipped_no_strip} no-strip skips "
                        f"(safety valve)")
                    try:
                        cv2.imwrite(
                            f"debug_frames/"
                            f"f{frame_count}_nostripforce.jpg",
                            frame)
                    except Exception:
                        pass
                    skipped_no_strip = 0
                else:
                    # Periodic telemetry + debug-frame dumps so we can
                    # monitor false-skip rate against the live feed.
                    if (skipped_no_strip == 1
                            or skipped_no_strip_total % 20 == 0):
                        log.info(
                            f"[F{frame_count}] No-strip skip "
                            f"#{skipped_no_strip} "
                            f"(lifetime={skipped_no_strip_total})")
                        try:
                            cv2.imwrite(
                                f"debug_frames/"
                                f"f{frame_count}_nostrip.jpg",
                                frame)
                        except Exception:
                            pass
                    await broadcast_base()
                    await asyncio.sleep(0.8)
                    continue
            else:
                skipped_no_strip = 0

            # === SNAPSHOT: UI state BEFORE processing ===
            _frame_wall_t0 = time.time()
            _before_state = scoreboard.get_live_state()
            _before_bat1 = _before_bat2 = "—"
            for _bn, _bc in scoreboard.batting_card.items():
                if _bc.get("status") == "batting":
                    _bs = f"{_bn} {_bc.get('runs','?')}({_bc.get('balls','?')})"
                    if _before_bat1 == "—":
                        _before_bat1 = _bs
                    else:
                        _before_bat2 = _bs
            _before_bowl_name = scoreboard._inn.get("current_bowler") or "—"
            _before_bowl_entry = scoreboard.bowling_card.get(_before_bowl_name, {})
            _before_bowl = (f"{_before_bowl_name} "
                            f"{_before_bowl_entry.get('wickets','?')}-"
                            f"{_before_bowl_entry.get('runs','?')} "
                            f"({_before_bowl_entry.get('overs','?')})")
            _before_this_over = over_mgr.get_display(
                scoreboard._inn.get("overs"))
            _before_score = (f"{_before_state.get('score')}-"
                             f"{_before_state.get('wickets')}"
                             f"({_before_state.get('overs')})")

            # === VISION (single Groq Scout call — strip + action) ===
            t0 = time.time()
            frame_type, description, action_desc = await vision.describe(
                frame, vision_hint)
            _prev_ft_poison = _prev_vision_frame_type
            _prev_vision_frame_type = frame_type
            v_ms = (time.time() - t0) * 1000
            current_action = action_desc

            # P3 — decrement overlay-window counter at frame start.
            # Captured value (after decrement) is what the per-frame
            # debounce check below sees.
            if _overlay_window_remaining > 0:
                _overlay_window_remaining -= 1
            _overlay_window_active_frame = (_overlay_window_remaining > 0)
            _inset_suspected_frame = False

            # === S17: scan action text for dismissal keywords ===
            # The action LLM frequently describes the dismissal a frame
            # or two before the score strip catches up ("walking off
            # after getting stumped"). Capture the hint into the
            # ring buffer so any auto-dismiss path (which runs earlier
            # in the same frame than the WICKET event handler) can
            # paint the right kind onto the FOW entry.
            if action_desc:
                _hint_mode = _scan_dismissal_keyword(action_desc)
                if _hint_mode:
                    _record_dismissal_hint(
                        frame_count, _hint_mode, "action")
                    # Push DIRECTLY into scoreboard too so
                    # `_auto_dismiss_for_new_batter` (called inside
                    # update_batter, which runs at line ~4449 — well
                    # before the WICKET handler at line ~5764) sees it.
                    scoreboard.pending_dismissal_hint = _hint_mode
                    scoreboard.pending_dismissal_bowler = (
                        scoreboard._inn.get("current_bowler"))
                    scoreboard.pending_dismissal_hint_frame = frame_count
                    log.info(
                        f"  [DISMISSAL-HINT] action says "
                        f"{_hint_mode!r} (window {_DISMISSAL_HINT_WINDOW}f)")

            # Push the Scout-classified frame into BallAnalyzer's
            # tagged buffer so analyze_last_delivery can pull semantic
            # delivery frames without needing Moondream as a gate.
            # (2026-04-18 architecture: free piggyback on the Scout
            # call we already made.)
            _last_cam = getattr(vision, "last_camera_view", None)
            _last_phase = getattr(vision, "last_frame_phase", None)
            try:
                if ball_analyzer and _last_cam:
                    ball_analyzer.record_tagged_frame(
                        frame, _last_cam, timestamp=t0,
                        frame_phase=_last_phase)
            except Exception as _e:
                log.debug(f"[TAGGED_FRAME] record swallowed: {_e}")
            # 2026-04-20: forward camera_view to the Gemini delivery
            # window recorder.  This is the SOLE input to the
            # Scout-triggered window state machine that defines the
            # delivery clip boundaries (bowlers_end -> open;
            # replay/graphic/ad -> close).  Cheap; does NOT touch
            # the scoreboard pipeline.
            try:
                if ball_analyzer:
                    ball_analyzer.on_scout_tag(t0, _last_cam)
                    ball_analyzer.recorder_tick(now=t0)
            except Exception as _e:
                log.debug(f"[DWR] on_scout_tag swallowed: {_e}")

            # Parallel-Scout (design memo §3.2): fire-and-forget
            # OpenScout call gated by per-state cadence.  Result lands
            # in BallAnalyzer.span_aggregator; the matcher is consulted
            # on every score event regardless of USE_OPEN_SCOUT_SPANS.
            # When OPENSCOUT_DECOUPLED=1, the dedicated coroutine owns
            # this work — skip the inline path entirely.
            if (not OPENSCOUT_DECOUPLED
                    and open_scout is not None
                    and open_scout_gate is not None
                    and ball_analyzer is not None):
                _capture_alive = bool(getattr(
                    ball_analyzer, "alive", True))
                if open_scout_gate.allow(
                        t0,
                        camera_view=_last_cam,
                        frame_phase=_last_phase,
                        capture_alive=_capture_alive):
                    _open_frame = frame
                    _open_ts = t0
                    _open_idx = frame_count

                    async def _open_scout_pipe(_f, _ts, _idx):
                        try:
                            res = await open_scout.classify(
                                _f, _ts, frame_idx=_idx)
                            if res is not None and ball_analyzer:
                                ball_analyzer.record_open_classification(
                                    res.timestamp,
                                    res.frame_class,
                                    res.raw_description,
                                )
                                try:
                                    ball_analyzer.record_v3_frame(
                                        res.timestamp,
                                        prod_cam=_last_cam,
                                        prod_phase=_last_phase,
                                        v2_broadcast_tag=getattr(
                                            res, "v2_broadcast_tag",
                                            "") or "",
                                        v2_class=res.frame_class,
                                        open_desc=res.raw_description,
                                    )
                                except Exception:  # noqa: BLE001
                                    log.debug(
                                        "[CHUNKER-V3] inline record swallowed")
                            if res is not None and shadow_runner is not None:
                                try:
                                    shadow_runner.add_scout_result({
                                        "ts": res.timestamp,
                                        "frame_class": res.frame_class,
                                        "raw_description":
                                            res.raw_description,
                                    })
                                except Exception:
                                    log.exception(
                                        "[SHADOW] add_scout_result failed")
                        except Exception as _e:  # noqa: BLE001
                            log.debug(
                                f"[OPEN-SCOUT] pipe swallowed: {_e}")

                    asyncio.create_task(
                        _open_scout_pipe(
                            _open_frame, _open_ts, _open_idx))
                elif open_scout_sidecar is not None:
                    # Layer A — record rate-gate skips so post-match
                    # review can see throttle / paused-view behavior
                    # alongside actual classifications.
                    try:
                        open_scout_sidecar.record_skip(
                            ts=t0,
                            frame_idx=frame_count,
                            rate_gate_reason=getattr(
                                open_scout_gate,
                                "last_decision_reason",
                                "skipped:unknown"),
                        )
                    except Exception as _e:  # noqa: BLE001
                        log.debug(
                            f"[OPEN-SCOUT] sidecar skip swallowed: {_e}")
            # 2026-05-03: shadow Stage 1 ingest must run independent
            # of the OpenScout rate gate. Per
            # files/docs/investigations/broadcast_mode_filter_tuning.md
            # §11, the ~0.17 fps gate cadence makes BMF peak_count
            # thresholds mathematically unreachable; Stage 1 needs the
            # full pipeline frame stream (~5 fps and below) to latch.
            if shadow_runner is not None and not getattr(
                    shadow_runner, "_has_own_ingest", False):
                try:
                    if (SHADOW_FRAME_DECIMATE <= 1
                            or (frame_count % SHADOW_FRAME_DECIMATE) == 0):
                        shadow_runner.add_frame(t0, frame)
                except Exception:
                    log.exception("[SHADOW] add_frame failed")
            # Phase 2: feed the camera_view tag into AdaptiveSleep so
            # the next-frame cadence bursts to ACTIVE_PLAY_INTERVAL
            # (~0.5s) when the broadcast is showing live cricket and
            # relaxes to DEAD_TIME_INTERVAL (~2.5s) for replays / ads
            # / graphics.  This populates the tagged buffer with 6-10
            # bowlers_end frames per delivery instead of 2-3.
            adaptive.on_camera_view(_last_cam)
            # P0-2 (2026-04-22): forward camera_view to the Scoreboard
            # so the XI-REJECT override gate can distinguish live-
            # action Scout reads (meaningful evidence the player is in
            # the XI) from stats-graphics reads (uninformative). See
            # eyes/scoreboard.py:on_camera_view.
            scoreboard.on_camera_view(_last_cam)
            # Phase 3 (2026-04-19): drive cadence from frame_phase
            # when present.  Action phases (release/flight/shot) get
            # 0.4 s polling, runup/between_play stretch out, ads
            # sleep 8 s.  See AdaptiveSleep.PHASE_FREQUENCY.
            adaptive.on_frame_phase(_last_phase)

            # === BROADCAST DATA EXTRACTION (all regex, before LLM) ===
            _bcast = extract_broadcast_data(description, _broadcast_cache)
            _frame_speed_kph = _bcast.get("speed_kph")

            # Striker from broadcast indicator (* or >).
            #
            # 2026-04-21 (Issue 5): stash the candidate instead of
            # applying it now.  If this frame's batter row read gets
            # whole-row-rejected below (balls/runs regression too
            # deep), the asterisk position parsed from the same
            # strip string is equally untrustworthy — Scout can't
            # put the mark on the right row if it got the rows
            # themselves wrong.  Apply the candidate only after
            # `update_batter` has had a chance to raise the row-
            # rejection flag on the scoreboard.
            _bcast_striker = _bcast.get("striker_broadcast")
            _pending_bcast_striker_key: str | None = None
            if _bcast_striker and scoreboard.batting_card:
                _bs_resolved = scoreboard.resolve_name(_bcast_striker)
                if _bs_resolved:
                    _bs_key = scoreboard._find_card_key(
                        _bs_resolved, scoreboard.batting_card)
                    if (_bs_key
                            and scoreboard.batting_card.get(_bs_key, {}).get(
                                "status") == "batting"):
                        _pending_bcast_striker_key = _bs_key

            # Target from broadcast (e.g. "TARGET 241")
            if _bcast.get("target"):
                _bt = _bcast["target"]
                if not scoreboard._inn.get("target"):
                    scoreboard.set("target", _bt, frame_count)
                    log.info(f"  [TARGET] Set from broadcast: {_bt}")
                if scoreboard.current_innings == 1:
                    # Bug #16 (revised): same 20-over / 10-wicket
                    # invariant. A "TARGET" graphic CAN appear during
                    # innings 1 — pre-match previews, "TARGET TO BEAT
                    # AT THIS GROUND", run-chase comparisons against
                    # historical totals. We only honour it as an
                    # innings-change signal if innings 1 has actually
                    # finished.
                    _inn1_o = float(
                        scoreboard._inn.get("overs") or "0") \
                        if scoreboard._inn else 0.0
                    _inn1_w = int(
                        scoreboard._inn.get("wickets") or 0) \
                        if scoreboard._inn else 0
                    if _inn1_o < 20.0 and _inn1_w < 10:
                        log.info(
                            f"  [GUARD] Target {_bt} seen but innings 1 "
                            f"at {_inn1_o}/{_inn1_w} — not a real "
                            f"innings change, ignoring promotion.")
                    else:
                        scoreboard.current_innings = 2
                        if ball_analyzer:
                            ball_analyzer.on_innings_change(2)
                        reset_for_innings(
                            2, overs_reset_source="broadcast_target_detect")
                        log.info(
                            f"  [INNINGS] Set to 2 "
                            f"(target detected: {_bt})")

            # Fours/Sixes from broadcast — apply to current striker.
            # Sanity-gate: career-stat overlays ("FOURS: 145") leak
            # absurd values; reject anything that violates
            # 4*fours + 6*sixes <= runs.
            _bcast_fours = _bcast.get("fours")
            _bcast_sixes = _bcast.get("sixes")
            if (_bcast_fours is not None or _bcast_sixes is not None):
                _fs_striker = _canonical_active_slot(
                    score_mgr, scoreboard, "striker")
                if _fs_striker and _fs_striker in scoreboard.batting_card:
                    _fs_entry = scoreboard.batting_card[_fs_striker]
                    _cur_r = _fs_entry.get("runs")
                    _f = (int(_bcast_fours) if _bcast_fours is not None
                          else int(_fs_entry.get("fours") or 0))
                    _s = (int(_bcast_sixes) if _bcast_sixes is not None
                          else int(_fs_entry.get("sixes") or 0))
                    if (_cur_r is not None
                            and 4 * _f + 6 * _s > int(_cur_r)):
                        log.warn(
                            f"  [FS-REJECT] broadcast fours={_f} "
                            f"sixes={_s} impossible vs "
                            f"{_fs_striker} runs={_cur_r} — ignoring")
                    else:
                        if _bcast_fours is not None:
                            _fs_entry["fours"] = int(_bcast_fours)
                        if _bcast_sixes is not None:
                            _fs_entry["sixes"] = int(_bcast_sixes)

            # This-over from info panel (broadcast override).
            # ONLY accept this_over from SCOREBOARD-tagged frames. GRAPHIC
            # frames (Orange Cap leaderboard etc.) leak digits like "2026"
            # into the broadcast parser which then poison this_over.
            if (_bcast.get("this_over_broadcast")
                    and frame_type == "SCOREBOARD"):
                _cur_score = scoreboard._inn.get("score")
                over_mgr.on_broadcast_override(
                    _bcast["this_over_broadcast"],
                    score=int(_cur_score) if _cur_score else None)
            elif (_bcast.get("this_over_broadcast")
                    and frame_type != "SCOREBOARD"):
                log.info(
                    f"  [THIS_OVER] Ignored broadcast tokens "
                    f"{_bcast['this_over_broadcast']} from "
                    f"{frame_type} frame (only SCOREBOARD honoured)")

            # Team abbreviation for early team detection
            if (_broadcast_cache.get("team_abbr")
                    and not batting_team):
                _abbr = _broadcast_cache["team_abbr"]
                _abbr_resolved = _resolve_team_variant(_abbr)
                # Fix 17 Path A (cold-start pre-match graphic gate,
                # 2026-04-26): pre-match team-reveal / toss
                # graphics universally show `<TEAM_ABBR> 0-0 (0.0)`.
                # No live-cricket frame would legitimately have all
                # three of score=0, wickets=0, overs=0.0 mid-match-
                # join.  When we haven't committed any non-zero
                # score yet AND the current frame's strip is
                # 0-0(0.0), treat it as a graphic — don't accept
                # the team_abbr.  This closes the F6 misread
                # (LSG-vs-KKR 2026-04-26) where a pre-match graphic
                # set `LSG batting` despite KKR actively batting.
                _path_a_strip_zzz = False
                _committed_score_a = (
                    int(scoreboard._inn.get("score") or 0)
                    if scoreboard._inn else 0)
                # Hotfix 2026-04-26: a fresh innings-2 (`LSG 0-0(0.0)`
                # at the literal start of the chase) is legitimate
                # production state, NOT a pre-match graphic.  Only
                # apply the pre-match gate when we're still in the
                # very first innings AND no batting_team has been
                # established yet.
                _path_a_eligible = (
                    _committed_score_a == 0
                    and getattr(scoreboard, "current_innings", 1) == 1
                    and not batting_team)
                # Parse the strip context near the team_abbr directly
                # from scout text since `extracted` isn't computed yet
                # at this stage.  Looks for `<ABBR> <runs>-<wkts>
                # (<overs>)` (canonical pre-match graphic shape).
                if _path_a_eligible:
                    try:
                        _strip_re = re.compile(
                            re.escape(_abbr)
                            + r"\s+(\d+)-(\d+)\s*\(\s*(\d+\.\d+|\d+)"
                            r"\s*\)")
                        _strip_m = _strip_re.search(description or "")
                        if _strip_m:
                            _sr, _sw, _so = _strip_m.group(1, 2, 3)
                            if (int(_sr) == 0
                                    and int(_sw) == 0
                                    and float(_so) == 0.0):
                                _path_a_strip_zzz = True
                    except (ValueError, TypeError, re.error):
                        pass
                if _path_a_strip_zzz:
                    log.info(
                        f"  [PRE-MATCH-GRAPHIC-GATE] team_abbr="
                        f"{_abbr} present on 0-0(0.0) strip "
                        f"with no committed score — treating as "
                        f"pre-match graphic, NOT assigning teams "
                        f"(Fix 17 Path A).")
                    # Hotfix 2026-04-26: also evict the cached
                    # team_abbr so a subsequent frame whose scout
                    # text contains a *different* match's strip
                    # (e.g. highlight-reel insert showing
                    # `RR 89-3 (10.4)`) doesn't fall through the
                    # gate's strip-pattern guard and trigger
                    # `assign_teams` from the stale pre-match
                    # value.  Real team commits will re-cache on
                    # the next legitimate live-cricket frame.
                    _broadcast_cache.pop("team_abbr", None)
                elif _abbr_resolved and _abbr_resolved in team_names:
                    _other = [t for t in team_names
                              if t != _abbr_resolved]
                    _bowl = _other[0] if _other else "?"
                    log.info(f"  [TEAM] From broadcast abbr: "
                             f"{_abbr} → {_abbr_resolved}")
                    assign_teams(_abbr_resolved, _bowl)

            # Broadcast extra type signal (e.g. "EXTRA: WD")
            _bcast_extra = _bcast.get("broadcast_extra")
            if _bcast_extra:
                ball_detector.set_broadcast_extra(_bcast_extra)
                log.info(f"  [BROADCAST] Extra signal: {_bcast_extra}")

            # Broadcast dismissal mode (BOWLED/CAUGHT/LBW etc.)
            _bcast_dismissal_mode = _bcast.get("dismissal_mode")
            if _bcast_dismissal_mode:
                _last_dismissal_mode = _bcast_dismissal_mode
                _last_dismissal_mode_frame = frame_count
                # #13: a fresh broadcast graphic resets the consumed
                # flag so the NEXT WICKET handler is allowed to use
                # this mode.  Without this reset, the second wicket
                # in a back-to-back sequence would skip even a
                # legitimately-fresh graphic.
                _last_dismissal_mode_consumed = False
                log.info(f"  [BROADCAST] Dismissal mode: "
                         f"{_bcast_dismissal_mode}")
                # S17: feed the ring buffer AND scoreboard.pending_*
                # so any auto-dismiss path (which runs before the
                # WICKET handler in the same frame) paints the FOW
                # with this kind, not the "inferred" stub.
                _bcast_dismissal_mode_norm = _scan_dismissal_keyword(
                    _bcast_dismissal_mode) or _bcast_dismissal_mode.lower()
                _record_dismissal_hint(
                    frame_count, _bcast_dismissal_mode_norm, "broadcast")
                scoreboard.pending_dismissal_hint = (
                    _bcast_dismissal_mode_norm)
                scoreboard.pending_dismissal_bowler = (
                    scoreboard._inn.get("current_bowler"))
                scoreboard.pending_dismissal_hint_frame = frame_count
            elif (_last_dismissal_mode
                  and frame_count - _last_dismissal_mode_frame
                  > _DISMISSAL_MODE_TTL_FRAMES):
                # S4 TTL — graphic was a single-ball overlay, age it
                # out so we don't keep emitting `dismissal_mode=bowled`
                # frame after frame on the WS payload.
                log.info(
                    f"  [DISMISSAL-CLEAR] TTL expired "
                    f"({frame_count - _last_dismissal_mode_frame} "
                    f"frames since set) — clearing "
                    f"{_last_dismissal_mode!r}")
                _last_dismissal_mode = None
                _last_dismissal_mode_frame = 0

            _all_out_text = " | ".join(
                x for x in (description, action_desc,
                            _bcast.get("dismissal_mode")) if x)
            if apply_all_out_authority(
                    scoreboard, _all_out_text, frame=frame_count):
                changes.append("wickets→10(all_out_authority)")

            # Broadcast extras total (info panel)
            if _bcast.get("extras_total") is not None:
                _be_total = _bcast["extras_total"]
                _cur_extras_total = sum(scoreboard.extras.values())
                if _be_total > _cur_extras_total:
                    scoreboard.extras["broadcast_total"] = _be_total
                    log.info(f"  [EXTRAS] Broadcast total: {_be_total}")

            # === EXTRAS INFERENCE ===
            # Cricket physics: team_score = sum(every batter's runs)
            # + extras. We can therefore infer extras whenever we
            # know the score AND every batter's contribution. When
            # wickets > 0 we need both active batters' runs and every
            # dismissed batter's runs (FOW carries the latter). If a
            # dismissed batter's runs are missing (placeholder), we
            # skip — partial sums under-count and would produce a
            # wildly inflated extras estimate.
            try:
                _ei_score = scoreboard._inn.get("score")
                _ei_wkts = scoreboard._inn.get("wickets")
                if _ei_score is not None and _ei_wkts is not None:
                    _ei_wkts_i = int(_ei_wkts)
                    _ei_active_runs = []
                    _ei_active_known = True
                    for c in scoreboard.batting_card.values():
                        if c.get("status") == "batting":
                            r = c.get("runs")
                            if r is None:
                                _ei_active_known = False
                                break
                            _ei_active_runs.append(int(r))
                    _ei_dismissed_runs = []
                    _ei_dismissed_known = True
                    for c in scoreboard.batting_card.values():
                        if c.get("status") == "out":
                            r = c.get("runs")
                            if r is None:
                                _ei_dismissed_known = False
                                break
                            _ei_dismissed_runs.append(int(r))
                    _ei_dismissed_count = sum(
                        1 for c in scoreboard.batting_card.values()
                        if c.get("status") == "out")
                    # Only infer when our dismissed-batter count
                    # matches the team wickets count (otherwise we're
                    # missing data for some FOW slots).
                    _ei_data_complete = (
                        _ei_active_known
                        and _ei_dismissed_known
                        and _ei_dismissed_count == _ei_wkts_i
                        and len(_ei_active_runs) >= 1)
                    if _ei_data_complete:
                        _ei_sum_runs = (sum(_ei_active_runs)
                                        + sum(_ei_dismissed_runs))
                        _ei_inferred = max(
                            0, int(_ei_score) - _ei_sum_runs)
                        # Diagnostic-only: write to `inferred_total`,
                        # not `total`.  See
                        # files/docs/investigations/extras_source_of_truth_diagnosis.md
                        _cur_inf = int(
                            scoreboard.extras.get("inferred_total") or 0)
                        if (_ei_inferred != _cur_inf
                                and _ei_inferred <= 40):
                            scoreboard.extras["inferred_total"] = (
                                _ei_inferred)
                            scoreboard.extras["inferred"] = True
                            log.info(
                                f"  [EXTRAS-INF] wkts={_ei_wkts_i}: "
                                f"score={_ei_score} - "
                                f"bat_sum={_ei_sum_runs} = "
                                f"extras={_ei_inferred}")
            except (ValueError, TypeError):
                pass

            # === DRS STATE MACHINE ===
            _drs_signal = vision.last_drs_flag
            _action_lower = (action_desc or "").lower()
            _desc_upper = (description or "").upper()
            if not _drs_signal and any(
                    kw in _action_lower for kw in
                    ("drs", "review", "reviewing", "decision pending",
                     "ball tracking", "umpire review")):
                _drs_signal = True
            if not _drs_signal and any(
                    kw in _desc_upper for kw in
                    ("REVIEW", "DRS", "DECISION PENDING",
                     "BALL TRACKING", "UMPIRE'S CALL",
                     "NOT GIVEN", "WIDE NOT GIVEN")):
                _drs_signal = True

            if _drs_signal:
                _drs_grace = 0
                if _drs_state == "NONE":
                    _drs_state = "DETECTING"
                    _drs_streak = 1
                    log.info(f"  [DRS] Detecting — frame 1")
                elif _drs_state == "DETECTING":
                    _drs_streak += 1
                    log.info(f"  [DRS] Detecting — frame {_drs_streak}")
                    if _drs_streak >= _DRS_CONFIRM_FRAMES:
                        _drs_state = "IN_PROGRESS"
                        _drs_pre_state = {
                            "score": scoreboard._inn.get("score"),
                            "wickets": scoreboard._inn.get("wickets"),
                            "overs": scoreboard._inn.get("overs"),
                        }
                        _drs_commentary_emitted = False
                        log.info(f"  [DRS] Confirmed IN_PROGRESS — "
                                 f"pre-state: {_drs_pre_state}")
                        # Freeze the ball-analyzer buffer NOW so the
                        # delivery under review is preserved through the
                        # 30-60s review window.
                        if ball_analyzer and ball_analyzer.alive:
                            ball_analyzer.freeze_buffer_for_drs()
                elif _drs_state == "IN_PROGRESS":
                    _drs_streak += 1
                    if (not _drs_commentary_emitted
                            and _commentary_engine is not None):
                        _drs_entry = {
                            "persona": "wire",
                            "text": ("The umpire's decision has been "
                                     "referred to the third umpire. "
                                     "DRS review in progress."),
                            "timestamp": time.time(),
                            "over": scoreboard._inn.get("overs", "?"),
                            "score": (f"{scoreboard._inn.get('score', 0)}/"
                                      f"{scoreboard._inn.get('wickets', 0)}"),
                            "latency_ms": 0,
                        }
                        _commentary_engine.history.append(_drs_entry)
                        asyncio.create_task(
                            _commentary_engine._broadcast(_drs_entry))
                        _drs_commentary_emitted = True
                        log.info(f"  [DRS] Commentary emitted: review in progress")
            else:
                if _drs_state == "DETECTING":
                    _drs_grace += 1
                    if _drs_grace > _DRS_GRACE_WINDOW:
                        _drs_state = "NONE"
                        _drs_streak = 0
                        _drs_grace = 0
                        log.info(f"  [DRS] Detecting reset — "
                                 f"grace window expired")
                    else:
                        log.info(f"  [DRS] Detecting — grace "
                                 f"{_drs_grace}/{_DRS_GRACE_WINDOW}")
                elif _drs_state == "IN_PROGRESS":
                    _drs_grace += 1
                    if _drs_grace > _DRS_GRACE_WINDOW:
                        _drs_state = "NONE"
                        _drs_streak = 0
                        _drs_grace = 0
                        _drs_pending_resolve = True
                        _drs_resolve_wait = 0
                        log.info(f"  [DRS] Exited IN_PROGRESS — "
                                 f"waiting {_DRS_RESOLVE_DELAY} frames "
                                 f"before resolving")
                    else:
                        log.info(f"  [DRS] IN_PROGRESS — grace "
                                 f"{_drs_grace}/{_DRS_GRACE_WINDOW}")

            if _drs_pending_resolve:
                _drs_resolve_wait += 1
                if _drs_resolve_wait >= _DRS_RESOLVE_DELAY:
                    _post = {
                        "score": scoreboard._inn.get("score"),
                        "wickets": scoreboard._inn.get("wickets"),
                        "overs": scoreboard._inn.get("overs"),
                    }
                    _pre = _drs_pre_state or {}
                    _drs_text = None
                    _pre_s = int(_pre.get("score") or 0)
                    _post_s = int(_post.get("score") or 0)
                    _pre_w = int(_pre.get("wickets") or 0)
                    _post_w = int(_post.get("wickets") or 0)

                    if _post_w > _pre_w:
                        _drs_text = ("DRS review complete. The on-field "
                                     "decision stands — the batter is out.")
                    elif _pre_w > _post_w:
                        _drs_text = ("DRS review complete. Decision "
                                     "overturned — the batter survives!")
                    elif _post_s > _pre_s and _post["overs"] == _pre["overs"]:
                        _extra_runs = _post_s - _pre_s
                        _drs_text = (f"DRS review complete. The call is "
                                     f"upheld — {_extra_runs} extra "
                                     f"run{'s' if _extra_runs != 1 else ''} "
                                     f"added.")
                    elif _post_s == _pre_s and _post_w == _pre_w:
                        _drs_text = ("DRS review complete. Decision "
                                     "overturned — no change to the score.")
                    else:
                        _drs_text = "DRS review complete."

                    log.info(f"  [DRS] Resolved (after {_DRS_RESOLVE_DELAY}"
                             f" frame delay): pre={_pre} post={_post} "
                             f"→ {_drs_text}")
                    # If DRS resolves with no change (overturned wicket,
                    # no extras), no ball event will fire — drop the
                    # frozen snapshot so it isn't re-used on the next
                    # unrelated delivery.  When a wicket / extra IS
                    # added, the resulting ball event will consume the
                    # snapshot via analyze_last_delivery.
                    _no_event_will_fire = (
                        _post_s == _pre_s and _post_w == _pre_w)
                    if (_no_event_will_fire and ball_analyzer
                            and ball_analyzer.alive):
                        ball_analyzer.unfreeze_buffer_for_drs()
                    if _commentary_engine is not None:
                        _drs_res_entry = {
                            "persona": "wire",
                            "text": _drs_text,
                            "timestamp": time.time(),
                            "over": _post.get("overs", "?"),
                            "score": (f"{_post.get('score', 0)}/"
                                      f"{_post.get('wickets', 0)}"),
                            "latency_ms": 0,
                        }
                        _commentary_engine.history.append(_drs_res_entry)
                        asyncio.create_task(
                            _commentary_engine._broadcast(_drs_res_entry))
                    _drs_pending_resolve = False
                    _drs_pre_state = None

            # Vision timed out entirely
            if frame_type == "UNKNOWN" and not description:
                if action_desc:
                    pending_action = action_desc
                log.info(f"[F{frame_count}] Vision timeout — skipping")
                continue

            if description:
                check_toss_in_vision(description)

            if frame_type == "ADVERTISEMENT":
                skipped_ad += 1
                cv2.imwrite(
                    f"debug_frames/f{frame_count}_ad.jpg", frame)
                log.info(f"[F{frame_count}] AD {v_ms:.0f}ms (#{skipped_ad})")
                merged_field = field_merger.merge(
                    yolo_positions, None, frame_count)
                if merged_field["source"] != "none":
                    m_overs = (scoreboard._inn.get("overs")
                               if scoreboard._inn else None)
                    field_state.update(
                        merged_field["positions"], frame_count, m_overs)
                adaptive.on_ad_detected(frame)
                await broadcast_base()
                await asyncio.sleep(adaptive.get_sleep_time())
                continue

            if frame_type in ("CLOSEUP", "PREMATCH"):
                skipped_context += 1
                if frame_type == "CLOSEUP":
                    cv2.imwrite(
                        f"debug_frames/f{frame_count}_closeup.jpg", frame)
                # Field merge — YOLO may see background fielders
                merged_field = field_merger.merge(
                    yolo_positions, None, frame_count)
                if merged_field["source"] != "none":
                    m_overs = (scoreboard._inn.get("overs")
                               if scoreboard._inn else None)
                    field_state.update(
                        merged_field["positions"], frame_count, m_overs)
                    if merged_field["source"] in (
                            "yolo", "yolo+vision", "vision_only"):
                        field_state.last_observed_frame = frame_count
                        field_state.balls_since_observation = 0

                # HYBRID: run extractor on CLOSEUP too — the broadcast
                # strip is almost always visible at the bottom
                if description and batting_team:
                    _cu_t0 = time.time()
                    _cu_ext = await extractor.extract(
                        description,
                        frame_type=frame_type,
                        team_a_name=team_names[0] if team_names else "",
                        team_b_name=team_names[1] if len(team_names) > 1 else "",
                    )
                    _cu_ems = (time.time() - _cu_t0) * 1000

                    if _cu_ext and _cu_ext.get("has_scorecard_data", True):
                        clean_extracted(
                            _cu_ext,
                            name_lookup=(scoreboard._name_lookup
                                         if scoreboard.batting_card else None),
                            scoreboard=scoreboard,
                            vision_desc=description)
                        if description:
                            filter_info_panel_contamination(
                                _cu_ext, description, scoreboard)
                            filter_standings_row_contamination(
                                _cu_ext, description)
                        _cu_vis = _cu_ext.get("batting_team_visible")
                        if (_cu_vis and bowling_team
                                and scoreboard.batting_card):
                            _cu_res = _resolve_team_variant(_cu_vis)
                            if _cu_res and _cu_res == bowling_team:
                                _cu_ext = {}

                        _cu_changes = []
                        _cu_s = _cu_ext.get("score")
                        if _cu_s is not None:
                            try:
                                _cu_si = int(_cu_s)
                                if scoreboard.set("score", _cu_si, frame_count):
                                    _cu_changes.append(f"score→{_cu_si}")
                            except (ValueError, TypeError):
                                pass
                        _cu_o = _cu_ext.get("match_overs")
                        if _cu_o is not None:
                            _cu_os = str(_cu_o).strip()
                            if "/" in _cu_os:
                                _cu_os = _cu_os.split("/")[0].strip()
                            try:
                                _cu_of = float(_cu_os)
                                if _cu_of < 20.0:
                                    if scoreboard.set("overs", _cu_os, frame_count):
                                        _cu_changes.append(f"overs→{_cu_os}")
                            except (ValueError, TypeError):
                                pass
                        _cu_w = _cu_ext.get("wickets")
                        if _cu_w is not None:
                            try:
                                _cu_wi = int(_cu_w)
                                if scoreboard.set("wickets", _cu_wi, frame_count):
                                    _cu_changes.append(f"wickets→{_cu_wi}")
                            except (ValueError, TypeError):
                                pass
                        if _cu_ext.get("batters"):
                            for _cb in _cu_ext["batters"]:
                                _cb_n = _cb.get("name", "")
                                if _cb_n and not _is_placeholder(_cb_n):
                                    if scoreboard.update_batter(
                                            _cb_n,
                                            runs=_cb.get("runs"),
                                            balls=_cb.get("balls"),
                                            striker=_cb.get("striker"),
                                            frame=frame_count):
                                        _cu_changes.append(
                                            f"bat:{_cb_n}={_cb.get('runs','?')}"
                                            f"({_cb.get('balls','?')})")
                        _cu_bw = _cu_ext.get("bowler")
                        if (_cu_bw and isinstance(_cu_bw, dict)
                                and scoreboard.bowling_card):
                            _cu_bn = _cu_bw.get("name", "")
                            if _cu_bn and not _is_placeholder(_cu_bn):
                                scoreboard.update_bowler(
                                    _cu_bn,
                                    overs=_cu_bw.get("overs"),
                                    runs=_cu_bw.get("runs"),
                                    wickets=_cu_bw.get("wickets"),
                                    frame=frame_count,
                                    vision_desc=description)
                                _cu_changes.append(f"bowl:{_cu_bn}")

                        # Flush entity suspicion after all updates
                        scoreboard._tracker._flush_entity_suspicion()

                        # Over change / ball event for hybrid frames
                        _cu_overs_str = scoreboard._inn.get("overs")
                        _cu_bowler_n = scoreboard._inn.get("current_bowler")
                        _cu_score_int = int(scoreboard._inn.get("score") or 0)
                        _pre_ball = ball_detector.detect(scoreboard._tracker)
                        if _pre_ball:
                            over_mgr.on_ball_event(_pre_ball,
                                                   score=_cu_score_int)
                        if over_mgr.check_over_change(
                                _cu_overs_str, _cu_bowler_n, _cu_score_int):
                            adaptive.on_over_change()

                        state = scoreboard.get_live_state()
                        ws_payload = build_full_payload()
                        await broadcast_state(ws_payload)

                        if _cu_changes:
                            log.info(f"[F{frame_count}] {frame_type} "
                                     f"{v_ms:.0f}ms+E{_cu_ems:.0f}ms "
                                     f"strip: {_cu_changes}")
                        else:
                            log.info(f"[F{frame_count}] {frame_type} "
                                     f"{v_ms:.0f}ms+E{_cu_ems:.0f}ms "
                                     f"(no strip data)")
                    else:
                        log.info(f"[F{frame_count}] {frame_type} "
                                 f"{v_ms:.0f}ms+E{_cu_ems:.0f}ms "
                                 f"(no scorecard)")
                else:
                    log.info(f"[F{frame_count}] {frame_type} "
                             f"{v_ms:.0f}ms (no team yet)")

                await broadcast_base()
                await asyncio.sleep(0.5)
                continue

            if not description:
                await asyncio.sleep(1.0)
                continue

            # ── Dead-time skip (Phase 2.5 — 2026-04-18) ─────────
            # When Scout tagged the frame as dead time (replay /
            # broadcaster graphic / ad / other) we skip the heavy
            # LLM chain (extract → scorer → score_mgr).  The
            # ADVERTISEMENT/CLOSEUP/PREMATCH cases above already
            # short-circuit on `frame_type`; this skip catches the
            # remaining case where the bottom strip is visible
            # (frame_type=SCOREBOARD or GRAPHIC) but the action
            # shot is a replay or full-screen graphic — not a
            # delivery view.  Saves ~1.5-2s of Groq calls per dead
            # frame and frees the loop so the next active-play
            # frame can fire faster.  ScoreManager state stays
            # frozen, which is correct: nothing changed during the
            # replay.
            _DEAD_VIEWS = ("replay", "graphic", "ad", "other")
            if _last_cam in _DEAD_VIEWS:
                skipped_dead_view += 1
                _was_dead_time = True
                # Thread 7 Fix 2 (2026-04-30): regex-only strip-head read when
                # Scout tags cam=graphic with strip visible and no stats overlay.
                # Commits ``score`` + ``overs`` only (design §3.2).
                if (_last_cam == "graphic"
                        and getattr(vision, "last_strip_flag", False)
                        and not getattr(vision, "last_overlay_flag", False)
                        and batting_team is not None
                        and scoreboard._inn):
                    _fp_commit, _fp_rej = _cam_graphic_fast_path(
                        description=description,
                        cam=_last_cam,
                        has_strip=getattr(vision, "last_strip_flag", False),
                        has_overlay_stats=getattr(
                            vision, "last_overlay_flag", False),
                        batting_team=batting_team,
                        current_score=int(
                            scoreboard._inn.get("score") or 0),
                        current_overs_str=scoreboard._inn.get("overs"),
                        cooldown=_cam_graphic_fp_cooldown,
                        resolve_team_variant=_resolve_team_variant,
                        frame_count=frame_count,
                    )
                    if _fp_commit is not None:
                        try:
                            _fp_cs = scoreboard.set(
                                "score", _fp_commit["score"], frame_count)
                        except Exception:
                            _fp_cs = False
                        try:
                            _fp_co = scoreboard.set(
                                "overs", _fp_commit["match_overs"],
                                frame_count)
                        except Exception:
                            _fp_co = False
                        if _fp_cs or _fp_co:
                            scoreboard._tracker._flush_entity_suspicion()
                            _fp_parts = []
                            if _fp_cs:
                                _fp_parts.append("score")
                            if _fp_co:
                                _fp_parts.append("overs")
                            log.info(
                                f"[F{frame_count}] [CAM-GRAPHIC-FAST-PATH-READ] "
                                f"score={_fp_commit['score']} "
                                f"overs={_fp_commit['match_overs']} "
                                f"changes={_fp_parts}")
                            await broadcast_state(build_full_payload())
                        else:
                            log.info(
                                f"[F{frame_count}] [CAM-GRAPHIC-FAST-PATH-NOOP] "
                                f"score={_fp_commit['score']} "
                                f"overs={_fp_commit['match_overs']} "
                                f"(state unchanged; no broadcast)")
                # Strategic timeout detection: T20 has two 2:30 min
                # timeouts per innings, typically after 6 / 14 overs.
                # A sustained ad/graphic block of >=75s while we're
                # parked at 6.x or 14.x overs is almost always a
                # strategic timeout. Flag it so the UI can render
                # "TIMEOUT" and we back off polling to save Scout
                # tokens (one Scout call every 4s instead of every
                # 1.5s during dead time).
                _now_ts = time.time()
                if _last_cam == "ad":
                    if _ad_streak_start is None:
                        _ad_streak_start = _now_ts
                    _ad_streak_dur = _now_ts - _ad_streak_start
                    _cur_overs_str = (
                        scoreboard._inn.get("overs")
                        if scoreboard._inn else None)
                    _cur_whole = -1
                    if _cur_overs_str:
                        try:
                            _cur_whole = int(
                                str(_cur_overs_str).split(".")[0])
                        except (ValueError, TypeError):
                            _cur_whole = -1
                    _at_timeout_over = _cur_whole in (6, 14)
                    if (_ad_streak_dur >= 75
                            and _at_timeout_over
                            and not _in_strategic_timeout):
                        _in_strategic_timeout = True
                        scoreboard._inn["match_phase"] = (
                            "strategic_timeout")
                        log.info(
                            f"[TIMEOUT] Strategic timeout detected: "
                            f"{_ad_streak_dur:.0f}s of ads at "
                            f"{_cur_overs_str} overs — backing off "
                            f"polling to 4s")
                else:
                    _ad_streak_start = None
                log.info(f"[F{frame_count}] {frame_type} "
                         f"cam={_last_cam} → dead-time skip "
                         f"(#{skipped_dead_view})"
                         + (" [TIMEOUT]" if _in_strategic_timeout
                            else ""))
                await broadcast_base()
                _sleep = (4.0 if _in_strategic_timeout
                          else adaptive.get_sleep_time())
                await asyncio.sleep(_sleep)
                continue
            if _in_strategic_timeout:
                _in_strategic_timeout = False
                _ad_streak_start = None
                if scoreboard._inn.get("match_phase") == \
                        "strategic_timeout":
                    scoreboard._inn["match_phase"] = "live"
                log.info(
                    f"[TIMEOUT] Strategic timeout ended — resuming "
                    f"normal polling (cam={_last_cam})")

            # Transition log: first active-play frame after a
            # dead-time gap.  Helps audit whether ScoreManager
            # might be looking at stale state when delivery events
            # fire on this frame.  The full pipeline runs as
            # normal — extract → scorer → score_mgr — so the
            # scorecard is refreshed BEFORE any delivery check.
            if _was_dead_time:
                log.info(f"[F{frame_count}] cam={_last_cam} → "
                         f"resuming active play after dead-time "
                         f"gap (#{skipped_dead_view} skipped)")
                _cam_graphic_fp_cooldown.clear()
                _was_dead_time = False

            processed += 1
            adaptive.on_scorecard_frame()
            adaptive.check_burst(
                _safe_float(scoreboard._inn.get("overs"))
                if scoreboard._inn else None)
            debug_path = f"debug_frames/f{frame_count}_{frame_type.lower()}.jpg"
            cv2.imwrite(debug_path, frame)
            log.info(f"\n{'='*55}")
            log.info(f"[F{frame_count}] {frame_type} — #{processed}")
            log.info(f"  [V {v_ms:.0f}ms] {description[:250]}")

            # === EXTRACTOR ===
            t0 = time.time()

            extracted = await extractor.extract(
                description,
                frame_type=frame_type,
                team_a_name=team_names[0] if team_names else "",
                team_b_name=team_names[1] if len(team_names) > 1 else "",
            )
            e_ms = (time.time() - t0) * 1000

            if not extracted or not extracted.get("has_scorecard_data", True):
                log.info(f"  [E {e_ms:.0f}ms] No data: {extracted.get('frame_type', '?')}")
                await asyncio.sleep(1.0)
                continue

            clean_extracted(extracted,
                           name_lookup=scoreboard._name_lookup if scoreboard.batting_card else None,
                           scoreboard=scoreboard,
                           vision_desc=description)

            if hot_resume_validate_pending and hot_resume_ok:
                _obs_score = extracted.get("score")
                _obs_wkts = extracted.get("wickets")
                _obs_overs_raw = extracted.get("overs")
                _obs_overs_f = None
                if _obs_overs_raw is not None:
                    try:
                        _obs_overs_f = float(_obs_overs_raw)
                    except (TypeError, ValueError):
                        _obs_overs_f = None
                if (_obs_score is not None and _obs_wkts is not None
                        and _obs_overs_f is not None):
                    _cs = cached_state.get("score")
                    _cw = cached_state.get("wickets")
                    try:
                        _co_f = float(cached_state.get("overs") or 0)
                    except (TypeError, ValueError):
                        _co_f = 0.0
                    _score_ok = (_cs - 6) <= _obs_score <= (_cs + 30)
                    _wkts_ok = _cw <= _obs_wkts <= (_cw + 2)
                    _overs_ok = _obs_overs_f >= (_co_f - 0.1)
                    if not (_score_ok and _wkts_ok and _overs_ok):
                        log.warn(
                            f"[HOT-RESUME-VALIDATE] REJECT — "
                            f"cached={_cs}/{_cw}({_co_f}) "
                            f"observed={_obs_score}/{_obs_wkts}"
                            f"({_obs_overs_f}). "
                            f"Reverting to COLD_START.")
                        score_mgr.mode = "COLD_START"
                        score_mgr.cold_candidate = None
                        score_mgr.cold_candidate_streak = 0
                        for _nm in list(scoreboard.batting_card.keys()):
                            scoreboard.batting_card[_nm]["runs"] = None
                            scoreboard.batting_card[_nm]["balls"] = None
                            scoreboard.batting_card[_nm]["status"] = (
                                "yet_to_bat")
                        hot_resume_ok = False
                    else:
                        log.info(
                            f"[HOT-RESUME-VALIDATE] OK — "
                            f"observed {_obs_score}/{_obs_wkts}"
                            f"({_obs_overs_f}) within tolerance")
                    hot_resume_validate_pending = False

            _state_recovery_frame_candidate = (
                _build_state_recovery_candidate(extracted, scoreboard))
            _state_recovery_current = (
                _build_state_recovery_current(scoreboard))
            _state_recovery_suppressed = (
                not batting_team
                or frame_type == "GRAPHIC"
                or frame_count <= _state_recovery_suppress_until_frame
                or not scoreboard._inn)

            # === EARLY FRAME POISON FLAG ===
            # Set before any DIRECT update path so all downstream
            # consumers (DIRECT batter, DIRECT bowler, Scorer) see it.
            _frame_poisoned = False
            # P7 fix (b): track whether this frame was poisoned by
            # GRAPHIC-only (absence of evidence) vs. any other reason
            # (contradicting evidence).  Only contradictions reset the
            # CORRECTION_BLOCKED consensus tracker; GRAPHIC frames
            # carry no contradicting score data and must not break a
            # legitimate recovery streak.
            _poison_non_graphic = False
            # Batch N (2026-05-04): batters-only poison.  When the
            # comparison-strip row-delta guard fires it pops only
            # `extracted["batters"]`; score / match_overs / bowler are
            # independent OCR regions and must still commit. Distinct
            # from `_frame_poisoned` (full-frame block).  See memo
            # files/docs/investigations/pooran_strip_rows_misaligned_state_lock.md
            _frame_poisoned_batters_only = False

            # Reject 0-0(0.0) frames mid-innings — these are
            # pre-match or stale graphics, not live data.
            #
            # 2026-04-18: BYPASS this guard when innings 1 has
            # demonstrably ended (>=20 overs OR >=10 wickets).  In
            # that case a fresh "0-0(0.0)" reading is the legitimate
            # innings-2 starting strip, not stale data.  Without
            # this bypass the guard kept stripping the new strip and
            # the pipeline never noticed the innings transition.
            _cur_match_score = int(scoreboard._inn.get("score") or 0)
            _cur_match_overs = float(
                scoreboard._inn.get("overs") or "0") \
                if scoreboard._inn else 0.0
            _cur_match_wkts = int(
                scoreboard._inn.get("wickets") or 0) \
                if scoreboard._inn else 0
            _innings_ended = (
                scoreboard.current_innings == 2
                or _cur_match_overs >= 20.0
                or _cur_match_wkts >= 10)
            _ext_s = extracted.get("score")
            _ext_w = extracted.get("wickets")
            _ext_o = extracted.get("match_overs")
            if (_cur_match_score > 5
                    and not _innings_ended
                    and _ext_s is not None and int(_ext_s) == 0
                    and _ext_w is not None and int(_ext_w) == 0
                    and _ext_o is not None and float(_ext_o) == 0.0):
                _frame_poisoned = True
                _poison_non_graphic = True
                log.info(f"  [GUARD] Extractor returned 0-0(0.0) "
                         f"mid-innings (current score={_cur_match_score}) "
                         f"— stripping all data")
                extracted.pop("score", None)
                extracted.pop("wickets", None)
                extracted.pop("match_overs", None)
                extracted.pop("batters", None)
                extracted.pop("bowler", None)
            elif (_innings_ended
                    and _ext_s is not None and int(_ext_s) == 0
                    and _ext_w is not None and int(_ext_w) == 0
                    and _ext_o is not None and float(_ext_o) == 0.0
                    and scoreboard.current_innings == 1):
                log.info(f"  [GUARD] 0-0(0.0) PASSED — innings 1 "
                         f"ended ({_cur_match_overs} ov / "
                         f"{_cur_match_wkts} wkts), this is innings "
                         f"2 starting fresh")

            # P3 — pre-frame debounce check. Runs FIRST so a SCOREBOARD
            # frame inside the overlay window (any team=null read) is
            # poisoned before any other strip-read processing fires.
            if _should_poison_in_overlay_window(
                    overlay_window_remaining=_overlay_window_remaining,
                    frame_type=frame_type,
                    extracted_team=extracted.get("batting_team_visible")):
                _frame_poisoned = True
                _inset_suspected_frame = True
                log.info(
                    "  [GRAPHIC-FILTER] overlay window active "
                    f"(remaining={_overlay_window_remaining}) — "
                    "poisoning strip read")
                extracted.pop("score", None)
                extracted.pop("wickets", None)
                extracted.pop("match_overs", None)

            # Toss banners are GRAPHIC frames — check before bailing on
            # the score path so the toss assignment fires even if the
            # downstream GRAPHIC handling poisons / drops extractor
            # fields. check_toss_in_vision is idempotent (gated by
            # toss_captured), so calling it here in addition to the
            # earlier call at the description-arrival site is safe.
            if not toss_captured and description:
                check_toss_in_vision(description)

            # GRAPHIC frames show aggregated/end-of-innings stats —
            # never use for live batter/bowler updates, but don't
            # poison the frame if score matches tracker (avoids
            # unnecessary consensus cycles).
            if frame_type == "GRAPHIC":
                extracted.pop("batters", None)
                extracted.pop("bowler", None)
                extracted.pop("speed_kph", None)
                _gfx_score = extracted.get("score")
                _gfx_wkts = extracted.get("wickets")
                _gfx_overs = extracted.get("match_overs")
                _trk_score = scoreboard._inn.get("score")
                _trk_wkts = scoreboard._inn.get("wickets")
                if (_gfx_score is not None and _trk_score is not None
                        and int(_gfx_score) == int(_trk_score)
                        and (_gfx_wkts is None or _trk_wkts is None
                             or int(_gfx_wkts) == int(_trk_wkts))):
                    log.info("  [GUARD] GRAPHIC frame — player stats "
                             "stripped, score matches tracker")
                else:
                    _frame_poisoned = True
                    log.info(
                        "  [GRAPHIC-FILTER] GRAPHIC frame — rejecting "
                        "extractor score path upstream of poison delta "
                        f"(frame_type=GRAPHIC raw_score={_gfx_score!r} "
                        f"raw_wkts={_gfx_wkts!r} raw_overs={_gfx_overs!r}; "
                        f"classification_conf=n/a)")
                    extracted.pop("score", None)
                    extracted.pop("wickets", None)
                    extracted.pop("match_overs", None)
                    # P3 — Mode A also arms the debounce window.
                    _overlay_window_remaining = OVERLAY_WINDOW_FRAMES
                    _overlay_window_active_frame = True
                    log.info(
                        "  [GUARD] GRAPHIC frame — player stats stripped, "
                        "score mismatch → poisoned (score fields cleared)")

            if _poison_scoreboard_after_graphic_transition(
                    prev_vision_frame_type=_prev_ft_poison,
                    frame_type=frame_type,
                    already_poisoned=_frame_poisoned):
                _frame_poisoned = True
                log.info(
                    "  [GRAPHIC-FILTER] GRAPHIC→SCOREBOARD transition — "
                    "poisoning strip read (lever-2 partial fade guard)")
                extracted.pop("score", None)
                extracted.pop("wickets", None)
                extracted.pop("match_overs", None)
                # P3 — Mode B also arms the debounce window.
                _overlay_window_remaining = OVERLAY_WINDOW_FRAMES
                _overlay_window_active_frame = True

            # P12 — innings-2 cold-start transition gates.  Reject
            # phantom recap/projection strips with bogus numeric
            # values or off-XI players during the post-reset window.
            # No-op outside the window (gate self-checks via score_mgr).
            if not _frame_poisoned and frame_type == "SCOREBOARD":
                _p12_triggered, _p12_reason = _apply_inn2_transition_gates(
                    extracted, scoreboard, score_mgr, frame_count)
                if _p12_triggered:
                    _frame_poisoned = True
                    log.info(
                        f"  [INN2-TRANSITION-REJECT] frame=F{frame_count} "
                        f"reason={_p12_reason} — poisoning strip read")
                    extracted.pop("score", None)
                    extracted.pop("wickets", None)
                    extracted.pop("match_overs", None)
                    extracted.pop("batters", None)
                    extracted.pop("bowlers", None)

            # P3 — Mode-C trigger: SCOREBOARD-tagged inset slipped past
            # Modes A and B (Scout did not classify GRAPHIC). Combines
            # `team=null + |score-tracker|>K` with an optional recap
            # fingerprint regex. See diagnosis §3 / §5 proposal 2+3.
            if not _frame_poisoned and frame_type == "SCOREBOARD":
                _trk_score_c = scoreboard._inn.get("score") \
                    if scoreboard._inn else None
                _tracker_committed_c = (
                    bool(scoreboard._inn)
                    and _trk_score_c is not None)
                _strip_text_c = description or ""
                _ext_score_c = extracted.get("score")
                _ext_team_c = extracted.get("batting_team_visible")
                _triggered_c, _reason_c = _detect_recap_inset_mode_c(
                    extracted_score=(int(_ext_score_c)
                                     if _ext_score_c is not None else None),
                    extracted_team=_ext_team_c,
                    scout_strip_text=_strip_text_c,
                    tracker_score=(int(_trk_score_c)
                                   if _trk_score_c is not None else None),
                    tracker_state_committed=_tracker_committed_c,
                )
                if _triggered_c:
                    _frame_poisoned = True
                    _inset_suspected_frame = True
                    _overlay_window_remaining = OVERLAY_WINDOW_FRAMES
                    _overlay_window_active_frame = True
                    log.info(
                        "  [GRAPHIC-FILTER] Mode-C inset detected — "
                        f"reason={_reason_c} — poisoning strip read")
                    extracted.pop("score", None)
                    extracted.pop("wickets", None)
                    extracted.pop("match_overs", None)

            # Filter info panel contamination before scorer
            if description:
                filter_info_panel_contamination(
                    extracted, description, scoreboard)
                filter_standings_row_contamination(
                    extracted, description)

            # Preserve raw score before guards can strip it,
            # so consensus tracking still works after FRAME_POISONED.
            _pre_guard_score = extracted.get("score")
            # Also preserve raw overs and wickets for the innings-2
            # fresh-strip detection: when the broadcast flips to
            # innings 2 the team-lock guard strips score/overs/wkts
            # below; we want to inspect them BEFORE that stripping to
            # tell apart a "fresh innings start" (overs ~0, score ~0)
            # from a comparison graphic showing some other state.
            _pre_guard_overs = extracted.get("match_overs")
            _pre_guard_wkts = extracted.get("wickets")

            # Comparison strip: if visible team is the bowling team,
            # this is innings-1 data or a comparison overlay — strip.
            # BUT: if we consistently ONLY see "bowling team" strips,
            # we likely missed an innings change and need to auto-swap.
            #
            # Rule 1 (cold-start): when batting_team is None we have no
            # ground truth for "who's batting" yet, so it's impossible
            # for any visible strip to be a "comparison" strip. Accept
            # everything; ScoreManager's cold-start consensus + Rule 2's
            # innings transition logic handles validation.
            _ext_vis_team = extracted.get("batting_team_visible")
            if (batting_team is not None
                    and _ext_vis_team and bowling_team
                    and scoreboard.batting_card):
                _vis_resolved = _resolve_team_variant(_ext_vis_team)
                if _vis_resolved and _vis_resolved == bowling_team:
                    _bowling_team_strip_count += 1
                    _bowling_team_strip_total += 1

                    # Bug #16 (revised): cricket-realism guard. The
                    # ONLY two ways a T20 innings can end are:
                    #   - 20 overs bowled (innings complete)
                    #   - 10 wickets down (all out)
                    # No exceptions. No "near the end" — only "at the
                    # end". If neither holds, the bowling-team strip is
                    # 100% a comparison/graphic and an innings change
                    # is physically impossible, no matter how many
                    # consecutive frames we've seen it for.
                    _inn1_overs = float(
                        scoreboard._inn.get("overs") or "0") \
                        if scoreboard._inn else 0.0
                    _inn1_wkts = int(
                        scoreboard._inn.get("wickets") or 0) \
                        if scoreboard._inn else 0
                    _inn1_could_end = (
                        scoreboard.current_innings == 2
                        or _inn1_overs >= 20.0
                        or _inn1_wkts >= 10)

                    # 2026-04-19 (KKR/RR fix): the strict 20.0/10
                    # threshold misses the common case where innings 1
                    # ends just shy of 20 overs / 10 wickets — e.g.
                    # RR 155/9 (19.5) finished the innings on the last
                    # ball without a 10th wicket falling.  After such
                    # an end the broadcast immediately flips to the
                    # second innings strip ("KKR 0-1 (0.X) | <new
                    # batters> | <new bowler>"), but our guard saw
                    # `_inn1_could_end = False` (overs 19.5 < 20.0,
                    # wkts 9 < 10) and stripped EVERY innings-2 frame
                    # forever.  The escape hatch couldn't fire because
                    # innings 1 had real ball events (so
                    # `_ball_events_for_current_team > 0`).  Pipeline
                    # froze at "RR 155/9 (19.5)" while the broadcast
                    # was deep into KKR's chase.
                    #
                    # Cricket physics: an innings cannot survive 30
                    # sustained "wrong batting team" frames at >= 18
                    # overs OR >= 8 wickets — both leave only 1-2
                    # legitimate balls to play and any sustained
                    # "wrong team" reading after that is the start of
                    # the next innings, not a comparison graphic.
                    # Fast-path swap is only safe at the strict
                    # threshold; the consensus path (30+ frames) is
                    # safe at the relaxed threshold.
                    _inn1_near_end = (
                        scoreboard.current_innings == 2
                        or _inn1_overs >= 18.0
                        or _inn1_wkts >= 8)

                    # 2026-04-18: when innings 1 has DEMONSTRABLY
                    # ended (>=20 ov OR >=10 wkts), a single bowling-
                    # team-strip frame is sufficient evidence of an
                    # innings transition.  Cricket physics: there is
                    # no cricketing reason innings 1 would still be
                    # in progress.  The 30-frame threshold (90 s of
                    # consecutive frames) was the old defensive
                    # bound for the case where _inn1_could_end was
                    # uncertain; once innings 1 is provably over,
                    # the old strip *cannot* be live data.
                    _swap_now = (
                        _inn1_could_end
                        and scoreboard.current_innings == 1)
                    # Use the relaxed `_inn1_near_end` for the
                    # consensus path: 30 sustained frames is itself
                    # strong evidence; combined with innings 1 being
                    # in the wind-down zone (>= 18 overs OR >= 8
                    # wickets) it is sufficient to trigger an innings
                    # change.  See the KKR/RR 19.5/9 freeze comment
                    # above for why the strict 20.0/10 threshold
                    # missed this case.
                    _swap_consensus = (
                        _bowling_team_strip_count
                        >= _BOWLING_TEAM_SWAP_THRESHOLD
                        and _inn1_near_end)
                    # Fix 3: escape hatch from cold-start team-lock.
                    # If we've stripped 30+ "bowling-team comparison"
                    # frames AND we have *never* fired a single ball
                    # event for the team we currently think is batting,
                    # then OUR team assignment is the misread, not the
                    # strip. Force a swap regardless of `_inn1_could_end`
                    # — there is no possible cricketing scenario where a
                    # team has been "batting" for 30 frames (~90 s of
                    # broadcast) without a single confirmed delivery.
                    # Day-1.5: the consecutive counter resets on a single
                    # frame that happens to read the assigned batting
                    # team — the SCOUT VLM hallucinates a team name on
                    # ~1 frame in 8 during cold-start, so the
                    # consecutive streak rarely reaches 30. Trip the
                    # escape on the CUMULATIVE strip count (which only
                    # resets on a successful `assign_teams`) so we
                    # actually recover from cold-start team-lock.
                    _swap_escape = (
                        (_bowling_team_strip_count
                            >= _BOWLING_TEAM_SWAP_THRESHOLD
                         or _bowling_team_strip_total
                            >= _BOWLING_TEAM_SWAP_TOTAL_THRESHOLD)
                        and _ball_events_for_current_team == 0
                        and scoreboard.current_innings == 1)

                    # 2026-04-19 (KKR/RR fix, fast-path): detect
                    # innings 2 from the strip itself.  If the
                    # extracted strip *shows* a fresh-innings score
                    # (overs <= 3.0 AND score < 30 AND wkts <= 2)
                    # while the visible team is the bowling team and
                    # innings 1 is near its end (>= 18 overs OR >= 8
                    # wickets), the strip cannot be a comparison
                    # graphic — it's the start of innings 2.  Three
                    # consecutive such frames (≈ 9 s) is plenty of
                    # consensus; we don't need the full 30-frame
                    # threshold because the strip *content* (low
                    # overs, low score) is itself strong evidence.
                    _fresh_overs = None
                    _fresh_score = None
                    _fresh_wkts = None
                    try:
                        if _pre_guard_overs is not None:
                            _fov_str = str(_pre_guard_overs)
                            if "/" in _fov_str:
                                _fov_str = _fov_str.split("/")[0]
                            _fresh_overs = float(_fov_str)
                        if _pre_guard_score is not None:
                            _fresh_score = int(_pre_guard_score)
                        if _pre_guard_wkts is not None:
                            _fresh_wkts = int(_pre_guard_wkts)
                    except (ValueError, TypeError):
                        pass
                    _strip_is_fresh = (
                        _fresh_overs is not None
                        and _fresh_overs <= 3.0
                        and _fresh_score is not None
                        and _fresh_score < 30
                        and (_fresh_wkts is None or _fresh_wkts <= 2))
                    _swap_fresh_strip = (
                        _strip_is_fresh
                        and _bowling_team_strip_count >= 3
                        and _inn1_near_end
                        and scoreboard.current_innings == 1)

                    if _swap_escape and not (_swap_now or _swap_consensus
                                             or _swap_fresh_strip):
                        log.info(
                            f"  [TEAM-LOCK ESCAPE] Stripped "
                            f"{_bowling_team_strip_count} consecutive "
                            f"({_bowling_team_strip_total} total) "
                            f"'{bowling_team}' frames AND zero ball "
                            f"events ever fired for current batting "
                            f"team '{batting_team}' — team assignment "
                            f"was the misread, not the strip. Forcing "
                            f"swap.")

                    if _swap_now:
                        log.info(
                            f"  [AUTO-SWAP] Innings 1 ended at "
                            f"{_inn1_overs} ov / {_inn1_wkts} wkts "
                            f"AND bowling team "
                            f"'{bowling_team}' visible on strip — "
                            f"swapping teams immediately (cricket "
                            f"physics — no consensus needed).")
                    elif _swap_fresh_strip:
                        log.info(
                            f"  [AUTO-SWAP] Innings-2 fresh-strip "
                            f"detected: bowling team "
                            f"'{bowling_team}' visible with strip "
                            f"score={_fresh_score}/{_fresh_wkts} "
                            f"overs={_fresh_overs} ({_bowling_team_strip_count} "
                            f"consecutive frames) AND innings 1 at "
                            f"{_inn1_overs}/{_inn1_wkts} (near end) — "
                            f"promoting to innings 2.")
                    elif _swap_consensus:
                        log.info(
                            f"  [AUTO-SWAP] Seen bowling team "
                            f"'{bowling_team}' strip "
                            f"{_bowling_team_strip_count} consecutive "
                            f"frames AND innings 1 at "
                            f"{_inn1_overs}/{_inn1_wkts} could plausibly "
                            f"have ended — swapping teams.")

                    if (_swap_now or _swap_consensus or _swap_escape
                            or _swap_fresh_strip):
                        _old_bat = batting_team
                        _old_bowl = bowling_team
                        team_locked = False
                        # Escape hatch is *not* an innings change —
                        # it's a correction of cold-start team roles
                        # within innings 1. Only the legitimate swap
                        # paths promote to innings 2.  Fresh-strip,
                        # auto-swap-now, and consensus paths all
                        # imply innings 2.  Only treat it as
                        # innings 1 when the *only* trigger is the
                        # escape hatch.
                        _is_inn2_trigger = (
                            _swap_now or _swap_consensus
                            or _swap_fresh_strip)
                        _new_innings = 2 if _is_inn2_trigger else 1
                        # Fix 9a (2026-04-26): inject innings-2 target
                        # BEFORE assign_teams.  assign_teams flips
                        # `scoreboard.current_innings = 2` as a side
                        # effect (see line 2799), and the
                        # `set_innings_2` call below is gated on
                        # `current_innings == 1` — so calling
                        # assign_teams first gates `set_innings_2`
                        # out entirely, leaving target=None.  This
                        # is the mechanism behind the target=66
                        # bug observed at F2503-F2504 in the
                        # CSK-vs-GT match: AUTO-SWAP fired,
                        # set_innings_2 was gated out, and a misread
                        # team_assignment.target=66 from the next
                        # frame's strip parser overwrote None.
                        # Source the target from the latched
                        # `innings_1_total` (set in the
                        # [INNINGS-END] block as innings 1 closed)
                        # rather than `scoreboard._inn.get("score")`
                        # which can be None at AUTO-SWAP time due
                        # to FRAME_POISONED guards stripping late
                        # innings-1 reads showing the team's final
                        # score.  Fall back to scoreboard score
                        # only if `innings_1_total` was never
                        # populated (rare — would mean innings 1
                        # ended without the [INNINGS-END] block
                        # ever latching).
                        if (_is_inn2_trigger
                                and scoreboard.current_innings == 1):
                            _inn1_score_latched = int(
                                (innings_1_total or {}).get("score")
                                or 0)
                            _inn1_score_live = int(
                                scoreboard._inn.get("score") or 0)
                            _inn1_score = max(
                                _inn1_score_latched,
                                _inn1_score_live)
                            _injected_target = (
                                _inn1_score + 1
                                if _inn1_score > 0 else None)
                            scoreboard.set_innings_2(_injected_target)
                            if _injected_target is not None:
                                log.info(
                                    f"  [AUTO-SWAP-TARGET] "
                                    f"Injecting target="
                                    f"{_injected_target} "
                                    f"(latched_final="
                                    f"{_inn1_score_latched}, "
                                    f"sb_score_live="
                                    f"{_inn1_score_live}) — "
                                    f"sourced from latched "
                                    f"innings_1_total")
                            else:
                                log.warn(
                                    f"  [AUTO-SWAP-TARGET] "
                                    f"Target injection skipped — "
                                    f"both latched_final and "
                                    f"sb_score=0 at AUTO-SWAP. "
                                    f"Target will remain None "
                                    f"until broadcast TARGET "
                                    f"overlay or downstream "
                                    f"recovery sets it.")
                            if ball_analyzer:
                                ball_analyzer.on_innings_change(2)
                            score_mgr.set_innings_2(
                                target=_injected_target,
                                batting_team=_old_bowl,
                                reason="AUTO-SWAP")
                            reset_for_innings(
                                2, overs_reset_source="AUTO-SWAP")
                            _state_recovery_suppress_until_frame = max(
                                _state_recovery_suppress_until_frame,
                                frame_count + 5)
                            _state_recovery.reset("innings_transition")
                        assign_teams(
                            _old_bowl, _old_bat,
                            innings=_new_innings)
                        team_locked = True
                        _bowling_team_strip_count = 0
                        _frame_poisoned = False
                    elif (_bowling_team_strip_count
                            >= _BOWLING_TEAM_SWAP_THRESHOLD
                            and not _inn1_could_end):
                        # Threshold met but innings 1 nowhere near
                        # done. This is a sustained graphic, not a
                        # missed innings change. Strip the frame and
                        # CAP the counter so it doesn't grow without
                        # bound and risk firing the moment innings 1
                        # legitimately reaches 18+ overs later.
                        log.info(
                            f"  [GUARD] Bowling-team strip "
                            f"{_bowling_team_strip_count} frames but "
                            f"innings 1 at "
                            f"{_inn1_overs}/{_inn1_wkts} — too early "
                            f"for innings change. Sustained graphic, "
                            f"not a swap.")
                        _bowling_team_strip_count = \
                            _BOWLING_TEAM_SWAP_THRESHOLD
                        _frame_poisoned = True
                        _poison_non_graphic = True
                        extracted.pop("score", None)
                        extracted.pop("wickets", None)
                        extracted.pop("match_overs", None)
                        extracted.pop("batters", None)
                        extracted.pop("bowler", None)
                        extracted.pop("bowler_name", None)
                        extracted.pop("bowler_figures", None)
                    else:
                        _frame_poisoned = True
                        _poison_non_graphic = True
                        log.info(
                            f"  [GUARD] Visible team '{_ext_vis_team}' "
                            f"is bowling team — comparison strip, "
                            f"ALL data stripped "
                            f"({_bowling_team_strip_count}/"
                            f"{_BOWLING_TEAM_SWAP_THRESHOLD})")
                        extracted.pop("score", None)
                        extracted.pop("wickets", None)
                        extracted.pop("match_overs", None)
                        extracted.pop("batters", None)
                        extracted.pop("bowler", None)
                        extracted.pop("bowler_name", None)
                        extracted.pop("bowler_figures", None)
                elif _vis_resolved and _vis_resolved == batting_team:
                    _bowling_team_strip_count = 0

            # Batting team old-data guard: if batter stats differ >20
            # from confirmed values, this is a replay/comparison strip.
            #
            # Per-batter scope: only enforce when the existing batter
            # row is a CONFIRMED reading, i.e. they've faced at least
            # one delivery (`balls > 0`). A row at 0(0) is the
            # placeholder seeded by `setup_innings()` (or by a fresh
            # post-wicket batter) and has never been confirmed by a
            # non-poisoned frame — comparing the first real read against
            # it would falsely poison every legitimate cold-start frame.
            # Batch U (2026-05-04) — per-row off-roster rejection.
            # Runs first so Scout hallucinations (MI vs LSG F205
            # [Inglis, KL Rahul]) don't poison the overlay/row-delta
            # guards downstream.  Per-row, non-poisoning: surviving
            # rows commit; score/overs/bowler untouched.
            filter_off_roster_batter_rows(
                extracted, scoreboard, batting_team,
                frame_count=frame_count)

            if apply_strip_overlay_prefilters(
                    extracted, scoreboard, description,
                    frame_count=frame_count,
                    record_state_recovery_guard=_record_state_recovery_guard,
                    current_match_number=_parse_current_match_number(
                        _broadcast_cache.get("match_info")),
                    cam=_last_cam,
                    batting_team=batting_team,
                    our_teams=team_names):
                _frame_poisoned_batters_only = True
            elif apply_comparison_strip_batter_row_delta_guard(
                    extracted, scoreboard, batting_team,
                    frame_count=frame_count,
                    record_state_recovery_guard=_record_state_recovery_guard):
                # Batch N (2026-05-04): honour the guard's stated
                # contract (`preserved=score,match_overs,bowler`).
                # Only `extracted["batters"]` was popped; the score,
                # overs, and bowler regions are independent and must
                # still commit.  Whole-frame poisoning here was the
                # root cause of the Pooran F493-F562 state-lock
                # cascade (5+ minutes frozen at 65-1 (4.4) while the
                # broadcast was at LSG 71-1+).  See memo
                # files/docs/investigations/pooran_strip_rows_misaligned_state_lock.md
                # §4.1.
                _frame_poisoned_batters_only = True

            # Guard: if extractor batter names don't match anyone in
            # the batting squad, this is a comparison strip — reject score
            if (extracted.get("batters") and batting_squad
                    and batting_team):
                _ext_names = [b.get("name", "").upper().strip()
                              for b in extracted["batters"] if b.get("name")]
                _squad_upper = {p.upper() for p in batting_squad}
                _squad_parts = set()
                for p in batting_squad:
                    for part in p.upper().split():
                        if len(part) >= 4:
                            _squad_parts.add(part)
                _all_squad = _squad_upper | _squad_parts

                def _name_in_squad(n):
                    if any(n in s or s in n for s in _all_squad):
                        return True
                    parts = n.split()
                    return len(parts) > 1 and parts[-1] in _all_squad

                _matches = sum(1 for n in _ext_names if _name_in_squad(n))
                if len(_ext_names) >= 2 and _matches == 0:
                    _frame_poisoned = True
                    _poison_non_graphic = True
                    log.info(f"  [GUARD] Batter names {_ext_names} don't "
                             f"match batting squad — comparison strip, "
                             f"stripping score/batters/bowler")
                    extracted.pop("score", None)
                    extracted.pop("wickets", None)
                    extracted.pop("match_overs", None)
                    extracted.pop("batters", None)
                    extracted.pop("bowler", None)

            # Fix extractor parsing "3.1/20" as "20", "3/20", etc.
            _ext_overs_raw = extracted.get("match_overs")
            if _ext_overs_raw is not None:
                _ov_str = str(_ext_overs_raw).strip()
                # Handle "3.1/20" or "3/20" format → extract part before slash
                if "/" in _ov_str:
                    _ov_str = _ov_str.split("/")[0].strip()
                    extracted["match_overs"] = _ov_str
                    log.info(f"  [FIX] Overs had slash format, using: {_ov_str}")

                # Fix LLM returning 0.X when Scout shows bare integer "(X)"
                # meaning X complete overs. E.g. Scout says "(1)" → LLM
                # extracts 0.1 instead of 1.0.
                #
                # CRITICAL: the regex MUST anchor to the team/bowler score
                # pattern "W-R (X)" to avoid matching batter balls-faced
                # "NAME R(B)" tokens. Earlier this used a bare
                # `\(\s*(\d{1,2})\s*\)` which matched "M MARSH 0(1)" and
                # wrongly rewrote legitimate 0.1 → 1.0 at every early-over
                # delivery. Two additional guards:
                #   (1) if the Scout description ALREADY contains a
                #       parenthesised decimal overs like "(0.1)", trust it
                #       and skip the correction entirely — the extractor
                #       is the one that mis-read a correctly-OCR'd strip.
                #   (2) only fire when the anchored "W-R (X)" token shows
                #       a bare integer (no decimal), which is the sole
                #       legitimate trigger case (OCR dropped the ".Y").
                try:
                    _ov_f = float(_ov_str)
                except (ValueError, TypeError):
                    _ov_f = 0.0
                _ov_int = int(_ov_f)
                _ov_ball = round((_ov_f % 1) * 10)
                if _ov_int == 0 and _ov_ball > 0 and description:
                    # Check if the W-R token (team or bowler) already
                    # carries a decimal overs — if so, the OCR is fine
                    # and the extractor, not the strip, is the one in
                    # error. Don't "correct" a correctly-OCR'd decimal.
                    _wr_with_decimal = re.search(
                        r'\d+-\d+\s+\(\s*\d+\.\d+\s*\)', description)
                    _bare_ov = re.search(
                        r'\d+-\d+\s+\(\s*(\d{1,2})\s*\)', description)
                    if _bare_ov and not _wr_with_decimal:
                        _scout_ov = int(_bare_ov.group(1))
                        if _scout_ov == _ov_ball and _scout_ov <= 20:
                            _ov_str = f"{_scout_ov}.0"
                            extracted["match_overs"] = _ov_str
                            log.info(f"  [FIX] Overs 0.{_ov_ball} "
                                     f"corrected to {_ov_str} — "
                                     f"Scout shows bare integer ({_scout_ov})")

                try:
                    _ext_overs_f = float(_ov_str)
                except (ValueError, TypeError):
                    _ext_overs_f = 0
                _cur_overs_f = float(scoreboard._inn.get("overs") or "0")
                if _ext_overs_f in (20.0, 50.0) and _cur_overs_f < 15.0:
                    log.info(f"  [FIX] Extractor returned overs={_ov_str}"
                             f" (match format) — dropping")
                    extracted.pop("match_overs", None)
                    _ext_overs_raw = None
                else:
                    _ext_overs_raw = _ov_str
                if _ext_overs_f >= 20.0 and _cur_overs_f >= 15.0:
                    # End-of-innings frame.  Two sub-cases:
                    #   (a) innings 1 — this is the FIRST observation of
                    #       the legitimate final.  Previously the entire
                    #       frame was skipped (`continue`), which meant
                    #       the scoreboard never registered the final
                    #       score / overs / wickets, the deterministic
                    #       `_det_overs_f >= 20.0` trigger downstream
                    #       never fired, no target was set, and the
                    #       innings transition was permanently lost
                    #       (innings froze at e.g. 154/8 (19.5) while the
                    #       broadcast moved on to RR 155/9 → KKR chase).
                    #       Now: latch the running final-score candidate
                    #       (max score wins, in case digits are torn
                    #       across multiple end-zone frames) and let the
                    #       frame flow through normal score updates so
                    #       the deterministic trigger can fire on the
                    #       same frame.
                    #   (b) innings 2 (or later) — these are post-
                    #       innings-1 summary graphics that don't apply
                    #       to the live state.  Skip as before.
                    if scoreboard.current_innings == 1:
                        _cand_score_raw = extracted.get("score")
                        _cand_wkts_raw = extracted.get("wickets")
                        try:
                            _cand_score_i = int(_cand_score_raw or 0)
                        except (ValueError, TypeError):
                            _cand_score_i = 0
                        try:
                            _cand_wkts_i = int(_cand_wkts_raw or 0)
                        except (ValueError, TypeError):
                            _cand_wkts_i = 0
                        try:
                            _existing_score_i = int(
                                (innings_1_total or {}).get("score") or 0)
                        except (ValueError, TypeError):
                            _existing_score_i = 0
                        try:
                            _existing_wkts_i = int(
                                (innings_1_total or {}).get("wickets") or 0)
                        except (ValueError, TypeError):
                            _existing_wkts_i = 0
                        # Higher score is always more authoritative; if
                        # tied, take the higher wicket count (more balls
                        # accounted for).  T20 sanity bounds gate the
                        # max-wins predicate so an upward extractor
                        # hallucination (e.g. 639-4 (76.5)) cannot lock
                        # out subsequent legitimate finals.
                        _should_latch, _latch_reject = (
                            _should_latch_innings_1_candidate(
                                _cand_score_i, _cand_wkts_i,
                                _ext_overs_raw,
                                _existing_score_i, _existing_wkts_i))
                        if _should_latch:
                            innings_1_total = {
                                "score": _cand_score_i,
                                "wickets": _cand_wkts_i,
                                "overs": _ext_overs_raw,
                            }
                            log.info(
                                f"  [INNINGS-END] Latched innings 1 "
                                f"final candidate: "
                                f"{_cand_score_i}-{_cand_wkts_i} "
                                f"({_ext_overs_raw}).")
                        elif _latch_reject == "sanity_bound":
                            log.info(
                                f"  [INNINGS-END] Rejecting bogus "
                                f"latch candidate "
                                f"{_cand_score_i}-{_cand_wkts_i} "
                                f"({_ext_overs_raw}) — exceeds T20 "
                                f"sanity bounds (>20 overs or >350 "
                                f"runs).")
                        # Archive and clear this-over for innings end
                        if over_mgr.this_over:
                            over_mgr.check_over_change(
                                _ext_overs_raw,
                                scoreboard._inn.get("current_bowler"),
                                int(scoreboard._inn.get("score") or 0))
                            over_mgr.this_over = []
                        log.info(
                            f"  [INNINGS-END] overs={_ext_overs_raw} "
                            f"reached in innings 1 (scoreboard "
                            f"{_cur_overs_f}) — letting frame through "
                            f"to register final + trigger transition.")
                        # Fall through (do NOT continue): score / over /
                        # wicket updates flow into the scoreboard via
                        # the normal path; the `_det_overs_f >= 20.0`
                        # block downstream will then fire
                        # `execute_innings_change` with the latched
                        # target.
                    else:
                        log.info(
                            f"  [GUARD] Overs {_ext_overs_raw} = "
                            f"innings complete graphic — already in "
                            f"inn {scoreboard.current_innings}, "
                            f"skipping")
                        await asyncio.sleep(1.0)
                        continue

            # === FIX 1: cold-start consistency gate ===
            # Before we let cold start commit to a team assignment,
            # verify the card isn't a hallucinated pre-match graphic.
            # If batters and the bowler resolve to the same team (or
            # batters span multiple teams), this frame is fictional
            # and must not seed `batting_team`. Mark it poisoned so
            # downstream guards strip it; the next valid frame will
            # cold-start cleanly.
            if not batting_team:
                _ok_cs, _reason_cs = _card_internally_consistent(extracted)
                if not _ok_cs:
                    _frame_poisoned = True
                    _poison_non_graphic = True
                    log.info(
                        f"  [GUARD] Cold-start card rejected — "
                        f"{_reason_cs}. Stripping all data and "
                        f"waiting for the next frame.")
                    extracted.pop("score", None)
                    extracted.pop("wickets", None)
                    extracted.pop("match_overs", None)
                    extracted.pop("batters", None)
                    extracted.pop("bowler", None)
                    extracted.pop("bowler_name", None)
                    extracted.pop("bowler_figures", None)
                    extracted.pop("batting_team_visible", None)

            # Detect batting team from player names if not yet set
            if not batting_team:
                detect_team_from_players(extracted)

            # Fallback: use visible_team directly from extractor
            if not batting_team and extracted:
                _vis = extracted.get("batting_team_visible")
                if _vis:
                    _vis_resolved = _resolve_team_variant(_vis)
                    if _vis_resolved and _vis_resolved in team_names:
                        # Fix 17 Path A extension (2026-04-26 hotfix):
                        # apply the pre-match-graphic gate to the
                        # extractor `visible_team` path too — pre-
                        # match team-reveal graphics universally
                        # show `<TEAM> 0-0 (0.0)` and the extractor
                        # happily sets `batting_team_visible=<team>`
                        # despite no live state.  Block the same
                        # way Path A blocks the broadcast-abbr path.
                        _vis_score = extracted.get("score")
                        _vis_wkts = extracted.get("wickets")
                        _vis_overs = extracted.get("match_overs")
                        _vis_committed = (
                            int(scoreboard._inn.get("score") or 0)
                            if scoreboard._inn else 0)
                        _vis_zzz = False
                        if (_vis_committed == 0
                                and getattr(
                                    scoreboard, "current_innings",
                                    1) == 1
                                and _vis_score is not None
                                and _vis_wkts is not None
                                and _vis_overs is not None):
                            try:
                                if (int(_vis_score) == 0
                                        and int(_vis_wkts) == 0
                                        and float(_vis_overs)
                                        == 0.0):
                                    _vis_zzz = True
                            except (ValueError, TypeError):
                                pass
                        if _vis_zzz:
                            log.info(
                                f"  [PRE-MATCH-GRAPHIC-GATE] "
                                f"visible_team={_vis} on 0-0(0.0) "
                                f"strip with no committed score "
                                f"— treating as pre-match graphic, "
                                f"NOT assigning teams (Fix 17 "
                                f"Path A, visible_team branch).")
                        else:
                            _other = [t for t in team_names
                                      if t != _vis_resolved]
                            _bowl_t = _other[0] if _other else "?"
                            log.info(
                                f"  [TEAM] Detected from "
                                f"visible_team: {_vis} → "
                                f"{_vis_resolved} batting")
                            assign_teams(_vis_resolved, _bowl_t)

            # Dismissal detection: extractor or backup from vision text.
            # Batch N: also gate on `_frame_poisoned_batters_only` —
            # the runs-delta guard discredits batter-related claims in
            # this strip, including any dismissal payload riding on it.
            _dismissal = (extracted.get("dismissal")
                          if not _frame_poisoned
                          and not _frame_poisoned_batters_only
                          else None)
            if (not _dismissal
                    and not _frame_poisoned
                    and not _frame_poisoned_batters_only):
                _dismissal = detect_dismissal_in_vision(description)
                if _dismissal:
                    extracted["dismissal"] = _dismissal
                    log.info(f"  [GUARD] Dismissal detected from vision: "
                             f"{_dismissal['batter']} {_dismissal['type']}")
            if _dismissal and isinstance(_dismissal, dict):
                # GUARD: regex-detected dismissals must be corroborated
                # by an actual wickets increment in the SAME frame's
                # extracted scoreboard. Without this, "Sharma 59(21)
                # retired" from a stat-panel overlay (or any partial
                # text match against an active batter) wrongly
                # flips the live batter to OUT. ~99% of false dismissals
                # we've seen lacked a wickets bump; drop them.
                _ext_wkts_now = (extracted.get("wickets")
                                 if extracted else None)
                _cur_wkts_now = scoreboard._inn.get("wickets")
                _wkt_bumped = (_ext_wkts_now is not None
                               and _cur_wkts_now is not None
                               and int(_ext_wkts_now) > int(_cur_wkts_now))
                if not _wkt_bumped:
                    log.info(
                        f"  [GUARD] Vision dismissal "
                        f"'{_dismissal.get('batter')} "
                        f"{_dismissal.get('type')}' rejected — "
                        f"wickets unchanged ({_cur_wkts_now})")
                    _dismissal = None
            if _dismissal and isinstance(_dismissal, dict):
                _d_name = _dismissal.get("batter", "")
                if _d_name and scoreboard.batting_card:
                    _d_resolved = scoreboard.resolve_name(_d_name)
                    if _d_resolved:
                        _d_key = scoreboard._find_card_key(
                            _d_resolved, scoreboard.batting_card)
                        if _d_key:
                            _entry = scoreboard.batting_card[_d_key]
                            if _entry["status"] == "batting":
                                scoreboard.dismiss_batter(
                                    _d_key,
                                    how=_dismissal.get("type"),
                                    bowler=_dismissal.get("bowler"),
                                    fielder=_dismissal.get("fielder"),
                                    frame=frame_count,
                                    extracted_batters=extracted.get(
                                        "batters"))
                            elif _entry["status"] == "yet_to_bat":
                                _entry["status"] = "out"
                                _entry["dismissal_source"] = (
                                    "wicket_ball_event")
                                _entry["runs"] = _dismissal.get("runs")
                                _entry["balls"] = _dismissal.get("balls")
                                _entry["dismissal"] = {
                                    "how": _dismissal.get("type"),
                                    "bowler": _dismissal.get("bowler"),
                                    "fielder": _dismissal.get("fielder"),
                                }
                                log.info(f"  [DISMISS] {_d_key} "
                                         f"{_dismissal.get('runs')}("
                                         f"{_dismissal.get('balls')}) "
                                         f"— {_dismissal.get('type')}")

            visible_team = extracted.get("batting_team_visible", "?")
            log.info(f"  [E {e_ms:.0f}ms] visible_team={visible_team} "
                     f"score={extracted.get('score')}-{extracted.get('wickets')} "
                     f"({extracted.get('match_overs')}) "
                     f"target={extracted.get('target')} rr={extracted.get('required_rate')}")
            if extracted.get("batters"):
                for b in extracted["batters"]:
                    log.info(f"    BAT: {b.get('name')} {b.get('runs')}({b.get('balls')}) "
                             f"{'*' if b.get('striker') else ''}")
            if extracted.get("bowler"):
                bw = extracted["bowler"]
                log.info(f"    BOWL: {bw.get('name')} {bw.get('wickets')}-{bw.get('runs')} "
                         f"({bw.get('overs')})")

            # Update bowler from extractor — strip is ground truth
            _ext_bowler = extracted.get("bowler")
            if (_ext_bowler and isinstance(_ext_bowler, dict)
                    and scoreboard.bowling_card
                    and not _frame_poisoned):
                _eb_name = _ext_bowler.get("name", "")
                if _eb_name and not _is_placeholder(_eb_name):
                    _eb_resolved = scoreboard.resolve_name(_eb_name)
                    _cur_bowler = scoreboard._inn.get("current_bowler")

                    # Auto-release bowler lock after 30 frames (~2+ minutes)
                    if scoreboard._bowler_locked:
                        frames_since = frame_count - scoreboard._bowler_lock_frame
                        if frames_since > 30:
                            scoreboard._bowler_locked = False
                            log.info(f"  [BOWLER] Lock auto-released after "
                                     f"{frames_since} frames")

                    if (scoreboard._bowler_locked
                            and _eb_resolved
                            and _eb_resolved != _cur_bowler):
                        log.info(f"  [GUARD] Bowler locked to "
                                 f"{_cur_bowler} this over — "
                                 f"rejecting {_eb_resolved}")
                    elif (scoreboard._bowler_must_change
                            and _eb_resolved
                            and _eb_resolved == scoreboard._prev_over_bowler):
                        # Auto-release the must-change guard after K
                        # frames stuck reading the previous bowler's
                        # name. The broadcast strip can keep showing
                        # the just-finished bowler's card for 60+
                        # seconds, blocking ALL bowler-name updates
                        # while the over progresses with someone else
                        # actually bowling. After K=5 frames we
                        # release the guard so the consensus path (3
                        # consistent reads) can fire on whatever
                        # Scout actually sees next. We keep
                        # `_prev_over_bowler` set so the new-bowler
                        # accept-on-1st-sighting path still works
                        # if a new name appears.
                        # 2026-04-21: threshold lowered 10→5 as part
                        # of Issue 3 (bowler cold-start lag).  In
                        # live IPL broadcasts the strip almost always
                        # catches up inside 3-4 frames; waiting 10
                        # was doubling the observed bowler-change
                        # visible lag without improving accuracy.
                        _frames_stuck = frame_count - (
                            _bowler_change_request_at_frame or frame_count)
                        if _frames_stuck >= 5:
                            log.info(
                                f"  [GUARD-RELEASE] _bowler_must_change "
                                f"stuck for {_frames_stuck} frames "
                                f"reading the previous bowler "
                                f"{_eb_resolved} — releasing guard so "
                                f"normal consensus path can update "
                                f"bowler stats. Identity flip still "
                                f"requires a NEW name reading.")
                            scoreboard._bowler_must_change = False
                        else:
                            log.info(
                                f"  [GUARD] Same bowler {_eb_resolved} "
                                f"after over change — waiting for "
                                f"new bowler name "
                                f"(stuck {_frames_stuck}f)")
                    else:
                        if (scoreboard._bowler_must_change
                                and _eb_resolved
                                and _eb_resolved != scoreboard._prev_over_bowler):
                            log.info(f"  [BOWLER] New bowler confirmed: "
                                     f"{_eb_resolved} (was "
                                     f"{scoreboard._prev_over_bowler})")
                            scoreboard._bowler_must_change = False
                            # DC-vs-CSK Fix 3: at over rollover the
                            # bowler always changes within 0-2 overs,
                            # so a clean (non-poisoned) read of a
                            # NEW name that resolves into the bowling-
                            # side squad is a strong-prior commit. Set
                            # ``current_bowler`` immediately and skip
                            # the N-consecutive-reads consensus path
                            # so the new spell starts on the very next
                            # frame instead of 5+s later.
                            try:
                                _bowling_squad = (
                                    scoreboard.bowling_card or {}).keys()
                                _is_squad = any(
                                    (k or "").upper() == _eb_resolved.upper()
                                    for k in _bowling_squad)
                                _prev_committed = (
                                    scoreboard._inn or {}).get(
                                        "current_bowler")
                                if (_is_squad
                                        and not _frame_poisoned
                                        and _prev_committed != _eb_resolved):
                                    if scoreboard._inn is not None:
                                        scoreboard._inn["current_bowler"] = (
                                            _eb_resolved)
                                    log.info(
                                        f"  [BOWLER] FAST-COMMIT swap "
                                        f"at over rollover — "
                                        f"current_bowler="
                                        f"{_eb_resolved} (squad-"
                                        f"validated, first clean read)")
                            except Exception as _fc_exc:
                                log.warn(
                                    f"  [BOWLER] fast-commit skipped: "
                                    f"{_fc_exc}")
                            # === S16 fix: do NOT set _bowler_locked
                            # here. Setting it before
                            # `scoreboard.update_bowler` had a chance
                            # to actually flip `current_bowler` (which
                            # has its own consensus path) used to lock
                            # in the OLD bowler for 30 frames, so a
                            # wicket falling in that window was
                            # credited to the previous-over bowler.
                            # The natural consensus inside
                            # scoreboard.update_bowler (3 reads OR
                            # bootstrap when current_bowler is None)
                            # is sufficient. The lock can re-engage
                            # later via the must_change satisfaction
                            # in update_bowler itself. ===
                        if (_eb_resolved
                                and _eb_resolved != _last_bowler_for_field):
                            _new_bt = get_bowler_type(
                                _eb_resolved, _squad_roles)
                            cricket_field.on_bowler_change(_new_bt)
                            _last_bowler_for_field = _eb_resolved
                        _bowl_runs_before = scoreboard._tracker.get(
                            f"bowl:{_eb_resolved or _eb_name}:runs")
                        scoreboard.update_bowler(
                            _eb_name,
                            frame=frame_count,
                            vision_desc=description)
                        _bowl_runs_after = scoreboard._tracker.get(
                            f"bowl:{_eb_resolved or _eb_name}:runs")
                        if (_bowl_runs_before is not None
                                and _bowl_runs_after is not None
                                and int(_bowl_runs_after) != int(_bowl_runs_before)):
                            _score_now = scoreboard._inn.get("score")
                            _score_before = scoreboard._tracker._prev_confirmed_score
                            _s_delta = (int(_score_now or 0)
                                        - int(_score_before or _score_now or 0))
                            _b_delta = int(_bowl_runs_after) - int(_bowl_runs_before)
                            if _s_delta == 0 and _b_delta != 0:
                                log.info(
                                    f"  [BOWLER-LEAD] {_eb_name} runs "
                                    f"{_bowl_runs_before}→{_bowl_runs_after} "
                                    f"(+{_b_delta}) but score unchanged "
                                    f"at {_score_now}")

            # === DRS FREEZE: skip all tracker updates during review ===
            if _drs_state == "IN_PROGRESS" or _drs_state == "DETECTING":
                log.info(f"  [DRS FREEZE] Skipping all tracker updates "
                         f"(state={_drs_state}, streak={_drs_streak})")
                # Jump directly to state broadcast, skip scorer + direct updates
                _rr_score = scoreboard._inn.get("score")
                _rr_overs = scoreboard._inn.get("overs")
                if _rr_score is not None and _rr_overs is not None:
                    try:
                        _rr_ov_f = float(_rr_overs)
                        _rr_whole = int(_rr_ov_f)
                        _rr_part = round((_rr_ov_f % 1) * 10)
                        _rr_balls = _rr_whole * 6 + _rr_part
                        if _rr_balls > 0:
                            _rr = round(float(_rr_score) / _rr_balls * 6, 2)
                            scoreboard.set("run_rate", _rr, frame_count)
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass
                state = scoreboard.get_live_state()
                speed_kph = _frame_speed_kph
                ball_event = None
                delivery_info = None
                ws_payload = build_full_payload(speed_kph=speed_kph)
                await broadcast_state(ws_payload)
                comm_t0 = time.time()
                comm_results: dict[str, dict] = {}
                comm_ms = 0
                _code_t0 = time.time()
                _code_ms = (time.time() - _code_t0) * 1000
                _frame_wall_ms = (time.time() - _frame_wall_t0) * 1000
                log.info(f"  Total: {_frame_wall_ms:.0f}ms "
                         f"(V:{v_ms:.0f} E:{e_ms:.0f})")
                log.info(f"  STATE: {state.get('batting_team') or '?'} "
                         f"{state.get('score')}-{state.get('wickets')} "
                         f"({state.get('overs')}) [DRS {_drs_state}]")
                # Still write DETAIL line for logging
                _before_state = scoreboard._inn.copy() if scoreboard._inn else {}
                _cw = comm_results.get("wire", {})
                _cs = comm_results.get("storyteller", {})
                _ca = comm_results.get("analyst", {})
                _cc = comm_results.get("colour", {})
                inv_corrections = []
                s_ms = 0
                ft_ms = 0
                _fielder_names = [p["name"] for p in
                                  cricket_field.get_display_positions()
                                  if p["type"] not in ("wk", "bowler", "bat")]
                _after_this_over = over_mgr.get_display(
                    scoreboard._inn.get("overs"))
                _after_this_over_src = " ".join(
                    f"{b}({s})" for b, s in
                    zip(over_mgr.this_over, over_mgr.this_over_sources)
                ) if over_mgr.this_over_sources else ""
                _after_state = scoreboard._inn.copy() if scoreboard._inn else {}
                _after_bat1 = "—"
                _after_bat2 = "—"
                _after_bowl = "—"
                # Path B read migration (2026-04-29): mirror the
                # canonical DETAIL site at ~L9663 — SM is authoritative
                # for striker/non; sb._inn is the legacy
                # projection fallback.  Emit divergence telemetry only
                # (every-frame log would flood; cutover writes already
                # fire `[STRIKER-SM-CUTOVER]` per write).
                _inn_str = scoreboard._inn.get("striker") if scoreboard._inn else None
                _inn_ns = scoreboard._inn.get("non") if scoreboard._inn else None
                _sm_str = getattr(score_mgr, "striker", None) if score_mgr else None
                _sm_ns = getattr(score_mgr, "non", None) if score_mgr else None
                _after_striker = _sm_str or _inn_str or "—"
                _after_non = _sm_ns or _inn_ns or "—"
                if (_sm_str and _inn_str and _sm_str != _inn_str) or \
                        (_sm_ns and _inn_ns and _sm_ns != _inn_ns):
                    log.info(
                        f"  [STRIKER-READ-SM-CANONICAL] DETAIL "
                        f"(DRS-freeze branch): SM-vs-_inn divergence — "
                        f"striker SM={_sm_str!r} _inn={_inn_str!r}; "
                        f"non SM={_sm_ns!r} _inn={_inn_ns!r}; "
                        f"using SM canonical")
                _after_run_rate = scoreboard._inn.get("run_rate", "—")
                for _abn, _abs in scoreboard.batting_card.items():
                    if _abs.get("status") == "batting":
                        _abstr = (f"{_abn} "
                                  f"{_abs.get('runs', '?')}"
                                  f"({_abs.get('balls', '?')})")
                        if not _after_bat1 or _after_bat1 == "—":
                            _after_bat1 = _abstr
                        else:
                            _after_bat2 = _abstr
                _cb_name = scoreboard._inn.get("current_bowler")
                if _cb_name and _cb_name in scoreboard.bowling_card:
                    _cbe = scoreboard.bowling_card[_cb_name]
                    _after_bowl = (f"{_cb_name} "
                                  f"{_cbe.get('wickets','?')}-"
                                  f"{_cbe.get('runs','?')} "
                                  f"({_cbe.get('overs','?')})")
                _detail_line = (
                    f"DETAIL|F{frame_count}|{frame_type}|"
                    f"tag={frame_type}|"
                    f"scout={description[:200].replace(chr(10), ' ')}|"
                    f"action={action_desc or '—'}|"
                    f"ext_score={extracted.get('score')}-{extracted.get('wickets')}"
                    f"({extracted.get('match_overs')})|"
                    f"ext_bat={extracted.get('raw_batters', '')}|"
                    f"ext_bowl={extracted.get('raw_bowler', '')}|"
                    f"scorer_changes=[]|"
                    f"yolo=0|"
                    f"BEFORE_score={_before_score}|"
                    f"BEFORE_bat1={_before_bat1}|"
                    f"BEFORE_bat2={_before_bat2}|"
                    f"BEFORE_bowl={_before_bowl}|"
                    f"BEFORE_this_over={_before_this_over}|"
                    f"AFTER_score={_after_state.get('score')}-"
                    f"{_after_state.get('wickets')}"
                    f"({_after_state.get('overs')})|"
                    f"AFTER_bat1={_after_bat1}|"
                    f"AFTER_bat2={_after_bat2}|"
                    f"AFTER_bowl={_after_bowl}|"
                    f"AFTER_this_over={_after_this_over}|"
                    f"AFTER_this_over_src={_after_this_over_src}|"
                    f"AFTER_striker={_after_striker}|"
                    f"AFTER_non={_after_non}|"
                    f"AFTER_run_rate={_after_run_rate}|"
                    f"AFTER_target=—|"
                    f"AFTER_innings={scoreboard.current_innings}|"
                    f"AFTER_partnership=—|"
                    f"AFTER_fow_count={len(scoreboard.fall_of_wickets)}|"
                    f"AFTER_field={cricket_field.phase} "
                    f"frozen={cricket_field._frozen} "
                    f"fielders={_fielder_names[:9]}|"
                    f"ball_event=—|"
                    f"ball_event_runs=—|ball_event_over=—|"
                    f"ball_event_extra=—|ball_event_free_hit=—|"
                    f"broadcast_extra={_bcast_extra or '—'}|"
                    f"dismissal_mode={_last_dismissal_mode or '—'}|"
                    f"striker_this_ball=—|"
                    f"delivery_length=—|delivery_line=—|"
                    f"delivery_angle=—|delivery_shot=—|"
                    f"delivery_direction=—|delivery_elevation=—|"
                    f"delivery_bounce=—|"
                    f"delivery_dets=0|delivery_det_rate=—|"
                    f"delivery_dir_zone=—|delivery_dir_conf=0|"
                    f"speed_kph=—|"
                    f"venue={_broadcast_cache.get('venue', '—')}|"
                    f"batting_team={batting_team or '—'}|"
                    f"match_info={_broadcast_cache.get('match_info', '—')}|"
                    f"completed_over=—|completed_over_runs=—|"
                    f"drs_state={_drs_state}|"
                    f"corrections=none|"
                    f"lat_vision={v_ms:.0f}|lat_extract={e_ms:.0f}|"
                    f"lat_scorer=0|lat_field=0|lat_comm=0|"
                    f"lat_code=0|lat_total={_frame_wall_ms:.0f}|"
                    f"comm_bowler=—|"
                    f"comm_wire=—|comm_storyteller=—|"
                    f"comm_analyst=—|comm_colour=—|"
                    f"comm_wire_ms=0|comm_story_ms=0|"
                    f"comm_analyst_ms=0|comm_colour_ms=0"
                )
                log.info(_detail_line)
                continue

            # === FRAME POISON CHECK (score divergence) ===
            # If extracted score diverges from tracker by >7, the entire
            # frame's data is from a wrong innings / stale graphic.
            # _frame_poisoned may already be True from guards above.
            # Use _pre_guard_score if guards already stripped score.
            _ext_score_raw = extracted.get("score")
            if _ext_score_raw is None:
                _ext_score_raw = _pre_guard_score
            if _ext_score_raw is not None:
                try:
                    _ext_score_int = int(_ext_score_raw)
                    # Cold-start safety: only run the poison delta check
                    # when we already have a CONFIRMED prior score.
                    # Without this, a fresh-start pipeline would compare
                    # ext=28 against `score or 0` = 0, declare delta=28 a
                    # poison spike, and block updates forever — never
                    # letting cold-start consensus make any progress.
                    _cur_score_raw = scoreboard._inn.get("score")
                    if _cur_score_raw is not None:
                        _cur_score_int_check = int(_cur_score_raw)
                        _delta_check = (
                            _ext_score_int - _cur_score_int_check)
                        if abs(_delta_check) > 7:
                            _frame_poisoned = True
                            _poison_non_graphic = True
                            _record_state_recovery_guard(
                                "poison_score",
                                proposed_reset=["score"])
                            log.info(
                                f"  [POISONED] Extracted score "
                                f"{_ext_score_int} vs tracker "
                                f"{_cur_score_int_check} (delta="
                                f"{_delta_check}) "
                                f"— blocking ALL updates this frame")
                            # Scout often tags cam=graphic + phase=graphic while
                            # the lexical frame_type stays SCOREBOARD (strip-up
                            # graphic interstitials). Those OCR reads must not
                            # advance POISON-RECAL — Cause-4 graphic pollution.
                            _gfx_phase_recal_skip = (
                                frame_type == "SCOREBOARD"
                                and _last_cam == "graphic"
                                and _last_phase == "graphic")
                            # Watchdog: count consecutive POISON frames
                            # to detect a stale tracker baseline (cold-
                            # start hallucination, missed innings change,
                            # etc.) — force a recal once the streak
                            # passes threshold.
                            #
                            # Cricket scores only climb within an
                            # innings, so during live play a stuck
                            # tracker manifests as a *rising* sequence of
                            # POISON'd values (e.g. 18 → 22 → 27 — every
                            # ball a new value), not a single repeating
                            # one.  Counting only exact repeats (the
                            # original behavior) reset the streak to 1/5
                            # every legitimate ball and the tracker
                            # could never escape.  Treat any monotonic
                            # non-decreasing run of POISON'd reads as
                            # the same diagnostic signal as a stale
                            # repeating overlay; both mean "many
                            # consecutive frames disagree with tracker
                            # in the same direction".  Track the highest
                            # value seen so a true regression (likely
                            # OCR noise rather than a stuck tracker)
                            # restarts the streak.
                            if _gfx_phase_recal_skip:
                                log.info(
                                    "  [POISON-RECAL-PRE-EMPTED] "
                                    "skipped streak advance — "
                                    f"graphic-phase OCR pollution "
                                    f"(would_be_delta={_delta_check}, "
                                    f"raw_score={_ext_score_int})")
                                log.info(
                                    "  [GRAPHIC-FILTER] SCOREBOARD+"
                                    "cam=graphic+phase=graphic — "
                                    "poison streak not fed "
                                    f"(classification_conf=n/a)")
                            elif (_poison_streak_new_score is None
                                    or _ext_score_int
                                    >= _poison_streak_new_score):
                                _poison_streak_count += 1
                                _poison_streak_new_score = max(
                                    _poison_streak_new_score
                                    if _poison_streak_new_score is not None
                                    else _ext_score_int,
                                    _ext_score_int)
                            else:
                                _poison_streak_new_score = _ext_score_int
                                _poison_streak_count = 1
                            if (not _gfx_phase_recal_skip):
                                log.info(
                                    f"  [POISON-STREAK] high="
                                    f"{_poison_streak_new_score} "
                                    f"latest={_ext_score_int} "
                                    f"streak={_poison_streak_count}/"
                                    f"{_POISON_RECAL_THRESHOLD}")
                                if (_poison_streak_count
                                        >= _POISON_RECAL_THRESHOLD):
                                    log.warn(
                                        f"  [POISON-RECAL] {_poison_streak_count} "
                                        f"consecutive POISON'd reads "
                                        f"(high={_poison_streak_new_score}, "
                                        f"latest={_ext_score_int}) — tracker "
                                        f"baseline {_cur_score_int_check} is "
                                        f"stale. Clearing tracker innings + "
                                        f"forcing ScoreManager cold-start.")
                                    scoreboard._inn["score"] = None
                                    scoreboard._inn["wickets"] = None
                                    scoreboard._inn["overs"] = None
                                    # P1 (2026-05-02): the phantom
                                    # commit that landed alongside
                                    # the stuck tracker baseline
                                    # (e.g. F55 47/3) seeded
                                    # _last_autodismiss_wickets to a
                                    # phantom value. POISON-RECAL is
                                    # the recovery — propagate the
                                    # reset to downstream one-way
                                    # gates so dismiss-replace doesn't
                                    # stay stranded.
                                    scoreboard.downstream_gates_resync(
                                        0, source="poison_recal")
                                    try:
                                        score_mgr.full_reset(
                                            reason=(
                                                "poison_recal_consensus "
                                                f"stuck_tracker="
                                                f"{_cur_score_int_check}"
                                                f"→live={_ext_score_int}"))
                                    except Exception as e:  # noqa: BLE001
                                        log.debug(
                                            f"[POISON-RECAL] SM recal "
                                            f"swallowed: {e}")
                                    _poison_streak_new_score = None
                                    _poison_streak_count = 0
                                    # Leave this frame poisoned; let the
                                    # next fresh read seed cold-start
                                    # consensus cleanly.
                        elif _delta_check >= 2:
                            # === Unsupported-score-spike guard ===
                            # +2..+7 is within the poison threshold but
                            # could still be a misread.  Require a
                            # corroborating signal (overs/wickets/bowler
                            # runs/batter runs/broadcast extra moved up
                            # too) before accepting on the first frame.
                            # Without ANY corroboration, defer one frame
                            # for confirmation — this is the same
                            # `balls_delta == 0 and s_delta > 0` shape
                            # that the EXTRA-IMMEDIATE path in
                            # `commentary.py` would otherwise flush as
                            # `Nb+{delta-1}` into `this_over`, where it
                            # then sticks even if the score stabilises
                            # back down (verified on KKR/RR F163 4.3o:
                            # 37 → 44, no other signals, → phantom
                            # `Nb+6` resident in `this_over` for the
                            # rest of the over).
                            _ext_overs_chk = extracted.get("match_overs")
                            _ext_wkts_chk = extracted.get("wickets")
                            _ext_batters_chk = (
                                extracted.get("batters") or [])
                            _ext_bowler_chk = (
                                extracted.get("bowler") or {})
                            _cur_overs_chk = (
                                scoreboard._inn.get("overs"))
                            _cur_wkts_chk = (
                                int(scoreboard._inn.get("wickets") or 0))
                            _cur_bowler_chk = (
                                scoreboard._inn.get("current_bowler"))
                            _overs_moved_chk = False
                            try:
                                if (_ext_overs_chk is not None
                                        and _cur_overs_chk is not None):
                                    _overs_moved_chk = (
                                        float(_ext_overs_chk)
                                        > float(_cur_overs_chk))
                            except (ValueError, TypeError):
                                pass
                            _wkts_moved_chk = False
                            try:
                                if _ext_wkts_chk is not None:
                                    _wkts_moved_chk = (
                                        int(_ext_wkts_chk)
                                        > _cur_wkts_chk)
                            except (ValueError, TypeError):
                                pass
                            _bcast_extra_chk = (
                                (_bcast or {}).get("broadcast_extra")
                                if isinstance(_bcast, dict) else None)
                            _bcast_extra_active = (
                                _bcast_extra_chk in ("WD", "NB"))
                            _bowler_runs_moved_chk = False
                            if (_cur_bowler_chk
                                    and isinstance(
                                        _ext_bowler_chk, dict)):
                                _ext_bowl_runs = (
                                    _ext_bowler_chk.get("runs"))
                                try:
                                    _cur_bowl_runs_now = (
                                        scoreboard._tracker.get(
                                            f"bowl:{_cur_bowler_chk}:runs")
                                        if hasattr(
                                            scoreboard, "_tracker")
                                        else None) or 0
                                    if _ext_bowl_runs is not None:
                                        _bowler_runs_moved_chk = (
                                            int(_ext_bowl_runs)
                                            > int(_cur_bowl_runs_now))
                                except (ValueError, TypeError,
                                        AttributeError):
                                    pass
                            _batter_runs_moved_chk = False
                            for _b_chk in _ext_batters_chk:
                                _bn_chk = (
                                    _b_chk.get("name", "")
                                    if isinstance(_b_chk, dict)
                                    else "")
                                _br_chk = (
                                    _b_chk.get("runs")
                                    if isinstance(_b_chk, dict)
                                    else None)
                                if not _bn_chk or _br_chk is None:
                                    continue
                                try:
                                    _br_i_chk = int(_br_chk)
                                    _cur_br_chk = 0
                                    if hasattr(scoreboard, "_tracker"):
                                        # Try full and short name keys
                                        _cur_br_chk = (
                                            scoreboard._tracker.get(
                                                f"bat:{_bn_chk}:runs")
                                            or 0)
                                    if _br_i_chk > int(_cur_br_chk):
                                        _batter_runs_moved_chk = True
                                        break
                                except (ValueError, TypeError,
                                        AttributeError):
                                    pass
                            _supported = (
                                _overs_moved_chk
                                or _wkts_moved_chk
                                or _bowler_runs_moved_chk
                                or _bcast_extra_active
                                or _batter_runs_moved_chk)
                            if not _supported:
                                if (_unsupported_score_pending
                                        == _ext_score_int):
                                    _unsupported_score_count += 1
                                else:
                                    _unsupported_score_pending = (
                                        _ext_score_int)
                                    _unsupported_score_count = 1
                                if (_unsupported_score_count
                                        >= _UNSUPPORTED_SCORE_CONFIRM):
                                    log.info(
                                        f"  [SUSPICION-CONFIRMED] "
                                        f"Score {_ext_score_int} held "
                                        f"for {_unsupported_score_count} "
                                        f"frames — accepting (was "
                                        f"unsupported but persistent).")
                                    _unsupported_score_pending = None
                                    _unsupported_score_count = 0
                                else:
                                    _frame_poisoned = True
                                    _poison_non_graphic = True
                                    log.info(
                                        f"  [SUSPICION] Score "
                                        f"+{_delta_check} (tracker="
                                        f"{_cur_score_int_check} → "
                                        f"ext={_ext_score_int}) with NO "
                                        f"corroborating signal "
                                        f"(overs_moved="
                                        f"{_overs_moved_chk} "
                                        f"wkts_moved={_wkts_moved_chk} "
                                        f"bowler_runs_moved="
                                        f"{_bowler_runs_moved_chk} "
                                        f"bcast_extra={_bcast_extra_chk} "
                                        f"batter_runs_moved="
                                        f"{_batter_runs_moved_chk}) — "
                                        f"deferring "
                                        f"({_unsupported_score_count}/"
                                        f"{_UNSUPPORTED_SCORE_CONFIRM} "
                                        f"frames). Likely LLM misread.")
                            else:
                                if _unsupported_score_pending is not None:
                                    _unsupported_score_pending = None
                                    _unsupported_score_count = 0
                        else:
                            # Score went down or by <2 — drop any
                            # in-flight unsupported-spike consensus
                            # since we no longer see that value.
                            if _unsupported_score_pending is not None:
                                _unsupported_score_pending = None
                                _unsupported_score_count = 0

                        # No poison spike on this frame → clear the
                        # stuck-tracker watchdog streak (only the
                        # abs(delta)>7 branch above accumulates it).
                        if abs(_delta_check) <= 7:
                            _poison_streak_new_score = None
                            _poison_streak_count = 0
                except (ValueError, TypeError):
                    pass

            # === BATTER-LEVEL SANITY CHECK ===
            # If any batter's runs exceed the team total IN THE SAME
            # FRAME's reading, the extractor produced internally
            # inconsistent data (wrong innings / stale graphic).
            #
            # CRITICAL: compare against the *extracted* score, not the
            # tracker's score.  Using `scoreboard._inn["score"]` here
            # was the source of the 2026-04-19 KKR/RR freeze: a stale
            # cold-start tracker total (1) made every legitimate score
            # advance (broadcast 5/1, with Raghuvanshi 4(5)) look like
            # "batter 4 > team total 1 → poison", blocking recovery
            # from cold-start forever.  The same-frame consistency
            # check is what we actually want: if THIS frame's data is
            # internally consistent (5 ≥ 4), accept it; downstream
            # delta guards still catch wild jumps.
            if (not _frame_poisoned
                    and extracted.get("batters")):
                _ext_team_total_chk = extracted.get("score")
                try:
                    _ext_team_total_chk = (
                        int(_ext_team_total_chk)
                        if _ext_team_total_chk is not None else None)
                except (ValueError, TypeError):
                    _ext_team_total_chk = None
                # Only run the check when we have an extracted total to
                # compare against — without it, there is no in-frame
                # consistency baseline and the check is meaningless.
                if (_ext_team_total_chk is not None
                        and _ext_team_total_chk > 0):
                    for _sb_chk in extracted["batters"]:
                        _sb_r_chk = _sb_chk.get("runs")
                        if _sb_r_chk is not None:
                            try:
                                if int(_sb_r_chk) > _ext_team_total_chk:
                                    _frame_poisoned = True
                                    _poison_non_graphic = True
                                    log.info(
                                        f"  [POISONED] Batter "
                                        f"{_sb_chk.get('name','?')} has "
                                        f"{_sb_r_chk} runs but extracted "
                                        f"team total is "
                                        f"{_ext_team_total_chk} — "
                                        f"in-frame inconsistency, "
                                        f"blocking ALL updates this frame")
                                    break
                            except (ValueError, TypeError):
                                pass

            # === SEED extractor batter names for auto-dismiss logic ===
            if (not _frame_poisoned
                    and extracted.get("batters") and scoreboard.batting_card):
                _ext_batter_set: set[str] = set()
                for _sb in extracted["batters"]:
                    _sb_n = _sb.get("name", "")
                    if _sb_n and not _is_placeholder(_sb_n):
                        _sb_r = scoreboard.resolve_name(_sb_n)
                        if _sb_r:
                            _ext_batter_set.add(_sb_r.upper())
                scoreboard.set_extractor_batters(_ext_batter_set)

            # === DIRECT EXTRACTOR → TRACKER for batter stats ===
            # Snapshot balls_faced BEFORE update for striker detection
            _balls_before: dict[str, int] = {}
            if (not _frame_poisoned
                    and extracted.get("batters") and scoreboard.batting_card):
                for _bn, _bc in scoreboard.batting_card.items():
                    if _bc.get("status") == "batting":
                        _balls_before[_bn] = int(_bc.get("balls") or 0)

                _direct_bat_changes = []
                for _db in extracted["batters"]:
                    _db_name = _db.get("name", "")
                    if _db_name and not _is_placeholder(_db_name):
                        _resolved = scoreboard.resolve_name(_db_name)
                        _card_key = scoreboard._find_card_key(
                            _resolved, scoreboard.batting_card) if _resolved else None
                        _old_entry = scoreboard.batting_card.get(
                            _card_key, {}) if _card_key else {}
                        _old_r = _old_entry.get("runs", "?")
                        _old_b = _old_entry.get("balls", "?")
                        # 2026-05-03: striker= dropped from this DIRECT
                        # path. The extractor's asterisk parse flaps
                        # frame-to-frame; SM is the sole striker
                        # authority post-S27 cutover. See
                        # files/docs/investigations/striker_write_thrashing.md
                        if scoreboard.update_batter(
                                _db_name,
                                runs=_db.get("runs"),
                                balls=_db.get("balls"),
                                frame=frame_count):
                            _new_entry = scoreboard.batting_card.get(
                                _card_key, {}) if _card_key else {}
                            _new_r = _new_entry.get("runs", "?")
                            _new_b = _new_entry.get("balls", "?")
                            _direct_bat_changes.append(
                                f"{_db_name}: ext={_db.get('runs','?')}"
                                f"({_db.get('balls','?')}) → "
                                f"tracker={_new_r}({_new_b}) "
                                f"[was {_old_r}({_old_b})]")
                if _direct_bat_changes:
                    log.info(f"  [DIRECT] Batter updates: "
                             f"{_direct_bat_changes}")

                # Apply the deferred broadcast-indicator striker flip
                # (Issue 5 gate, 2026-04-21).  Skip when this same
                # frame just whole-row-rejected a batter read — the
                # asterisk position parsed from the bad strip can't
                # be trusted either.
                if (_pending_bcast_striker_key
                        and getattr(
                            scoreboard,
                            "_last_row_rejected_frame",
                            -1) != frame_count):
                    _cur_striker = _canonical_active_slot(
                        score_mgr, scoreboard, "striker")
                    # Admission check (2026-04-22, matches WS-SCRUB
                    # invariant at build_full_payload). Only write
                    # through if the Scout-proposed name is currently
                    # in batting_card with status=="batting". Strict
                    # (Option A) for consistency with the WS-boundary
                    # scrub — a briefly-stale batting_card may produce
                    # the odd false rejection, which the corrective
                    # loop at L6878-6893 cleans up on the next ball.
                    _bc = scoreboard.batting_card or {}
                    _prop_card = _bc.get(_pending_bcast_striker_key)
                    _prop_ok = bool(
                        _prop_card
                        and _prop_card.get("status") == "batting")
                    if not _prop_ok:
                        _reason = (
                            "not_in_card" if _prop_card is None
                            else f"status_{_prop_card.get('status')}")
                        log.warn(
                            f"  [STRIKER-ADMIT] Rejecting broadcast "
                            f"indicator '{_pending_bcast_striker_key}'"
                            f" — {_reason}. current_striker stays "
                            f"'{_cur_striker}'")
                    elif _cur_striker != _pending_bcast_striker_key:
                        _old_ns = _canonical_active_slot(
                            score_mgr, scoreboard, "non")
                        _set_legacy_active_slot(
                            score_mgr, scoreboard, "striker",
                            _pending_bcast_striker_key,
                            "broadcast-indicator")
                        if _old_ns == _pending_bcast_striker_key:
                            _set_legacy_active_slot(
                                score_mgr, scoreboard, "non",
                                _cur_striker, "broadcast-indicator-swap")
                        log.info(
                            f"  [STRIKER] Broadcast indicator: "
                            f"{_pending_bcast_striker_key} "
                            f"(was {_cur_striker})")
                elif (_pending_bcast_striker_key
                        and getattr(
                            scoreboard,
                            "_last_row_rejected_frame",
                            -1) == frame_count):
                    log.info(
                        f"  [STRIKER] Broadcast indicator suppressed "
                        f"({_pending_bcast_striker_key}) — batter row "
                        f"was rejected this frame, asterisk read "
                        f"untrustworthy")

                # === S27: legacy non-SM striker writers removed ===
                # Both the "STRIKER FROM BALLS-FACED CHANGE" and
                # "BROADCAST STRIKER WINS" blocks wrote directly to
                # `scoreboard._inn["striker"]` / `["non"]`,
                # racing ScoreManager (which is the sole authority
                # for UI striker/non-striker after the SM cutover).
                # SM already consumes `broadcast_striker` via the
                # frame card (`score_manager.py:50, 301, 551, 954,
                # 1034`) and already infers striker from balls-faced
                # via its own ball-event ingest, so these legacy
                # writes added nothing but `[STRIKER-WRITE]` log
                # noise and a per-frame striker↔non flap
                # whenever the legacy inference disagreed with SM.

            # === BATTER REPLACEMENT after wicket (2-frame consensus) ===
            if (not _frame_poisoned
                    and extracted.get("batters")
                    and scoreboard.batting_card
                    and _last_wicket_frame > 0
                    and (frame_count - _last_wicket_frame) <= 40):
                _active_names = {
                    n for n, s in scoreboard.batting_card.items()
                    if s.get("status") == "batting"}
                for _rb in extracted["batters"]:
                    _rb_name = _rb.get("name", "")
                    if not _rb_name or _is_placeholder(_rb_name):
                        continue
                    _rb_resolved = scoreboard.resolve_name(_rb_name)
                    if not _rb_resolved:
                        continue
                    _rb_key = scoreboard._find_card_key(
                        _rb_resolved, scoreboard.batting_card)
                    if (_rb_key
                            and _rb_key not in _active_names
                            and scoreboard.batting_card[_rb_key].get(
                                "status") == "yet_to_bat"):
                        if _new_batter_candidate == _rb_key:
                            _new_batter_candidate_count += 1
                        else:
                            _new_batter_candidate = _rb_key
                            _new_batter_candidate_count = 1
                        if _new_batter_candidate_count >= _NEW_BATTER_CONFIRM:
                            # 2026-05-03: striker= dropped from this DIRECT
                            # path. The extractor's asterisk parse flaps
                            # frame-to-frame; SM is the sole striker
                            # authority post-S27 cutover. See
                            # files/docs/investigations/striker_write_thrashing.md
                            _accepted = scoreboard.update_batter(
                                _rb_key,
                                frame=frame_count)
                            if _accepted:
                                log.info(
                                    f"  [REPLACE] New batter '{_rb_key}' "
                                    f"seen {_new_batter_candidate_count}x "
                                    f"after wicket at F{_last_wicket_frame}"
                                    f" — activated")
                                _pr3_batter_arrival_slot_cutover(
                                    score_mgr, scoreboard, _rb_key)
                                _new_batter_candidate = None
                                _new_batter_candidate_count = 0
                            else:
                                log.info(
                                    f"  [REPLACE] '{_rb_key}' confirmed "
                                    f"but auto-dismiss deferred "
                                    f"(broadcast not settled)")
                        else:
                            log.info(
                                f"  [REPLACE] Candidate '{_rb_key}' "
                                f"frame {_new_batter_candidate_count}/"
                                f"{_NEW_BATTER_CONFIRM}, waiting")
                        break

            # Direct score/overs/wickets from extractor to tracker
            if not _frame_poisoned:
                # === P0 (2026-05-02): cricket-rules pre-check on DIRECT ===
                # Run SM's cricket_rules.validate_diff against the proposed
                # combined change BEFORE any scoreboard.set() mutates state.
                # Previously the SM evaluation log line at score_manager.py
                # 1641 fired AFTER the DIRECT commit landed (CSK vs MI run
                # F500 19:57:07: overs 5.2→7.5 was committed, then SM
                # logged d_balts_15_>_multi_max_12 — observability without
                # veto).  Now: if cricket_rules rejects, abort all three
                # DIRECT mutations.  Skip when current state is missing
                # (cold start) so the first valid commit can land.
                _direct_block_all = False
                _ext_score_pre = extracted.get("score")
                _ext_overs_pre = extracted.get("match_overs")
                _ext_wkts_pre = extracted.get("wickets")
                _cur_score_pre = (scoreboard._inn.get("score")
                                  if scoreboard._inn else None)
                _cur_overs_pre = (scoreboard._inn.get("overs")
                                  if scoreboard._inn else None)
                _cur_wkts_pre = (scoreboard._inn.get("wickets")
                                 if scoreboard._inn else None)
                _target_pre = (scoreboard._inn.get("target")
                               if scoreboard._inn else None)
                try:
                    _target_pre_i = (int(_target_pre)
                                     if _target_pre else None)
                except (ValueError, TypeError):
                    _target_pre_i = None
                try:
                    from cricket_rules import (
                        validate_direct_proposal as _cr_validate_direct,
                    )
                    _cr_pre = _cr_validate_direct(
                        cur_score=_cur_score_pre,
                        cur_overs=_cur_overs_pre,
                        cur_wickets=_cur_wkts_pre,
                        new_score=_ext_score_pre,
                        new_overs=_ext_overs_pre,
                        new_wickets=_ext_wkts_pre,
                        target=_target_pre_i,
                        innings=scoreboard.current_innings)
                    if not _cr_pre.ok:
                        _direct_block_all = True
                        log.warn(
                            f"  [DIRECT-SM-REJECT] "
                            f"cricket_rules: {_cr_pre.reject_reason} "
                            f"prev={_cur_score_pre}/{_cur_wkts_pre} "
                            f"({_cur_overs_pre}) → card="
                            f"{_ext_score_pre}/{_ext_wkts_pre} "
                            f"({_ext_overs_pre}) — aborting "
                            f"DIRECT score/overs/wickets commit")
                except Exception as _e_pre:  # noqa: BLE001
                    log.debug(
                        f"  [DIRECT-SM-REJECT] pre-check skipped: "
                        f"{_e_pre}")
                _ext_score = extracted.get("score")
                if not _direct_block_all and _ext_score is not None:
                    try:
                        _esi = int(_ext_score)
                        # P7 fix (c): SCORE-INF-GATE on the DIRECT
                        # path.  Without this, two consecutive frames
                        # of inflated extractor score (e.g. F177-F179
                        # ext_score=11 from the 2026-05-02 SA-WI
                        # corpus) feed Scoreboard's tracker consensus
                        # and flip score=11 with no admission gating —
                        # the gate inside apply_scorer_decision then
                        # sees current==proposed and lets it stand,
                        # producing the P7 lock-in.  Apply the same
                        # advance check here so DIRECT honors the cap.
                        # Suppressed on cold-start (score is None) so
                        # the first valid commit can land, and during
                        # the AUTO-SWAP recovery window (innings 2 may
                        # legitimately advance from 0 by more than 6).
                        _direct_block = False
                        _cur_dgate = scoreboard._inn.get("score") \
                            if scoreboard._inn else None
                        _direct_suppress = (
                            _cur_dgate is None
                            or int(_cur_dgate or 0) == 0
                            or frame_count
                            <= _state_recovery_suppress_until_frame)
                        if not _direct_suppress:
                            try:
                                _direct_advance = (
                                    _esi - int(_cur_dgate))
                            except (ValueError, TypeError):
                                _direct_advance = 0
                            if _direct_advance > 0:
                                _direct_bat_delta = 0
                                for _b_dg in (extracted.get(
                                        "batters") or []):
                                    _bn_dg = _b_dg.get("name", "")
                                    _br_dg = _b_dg.get("runs")
                                    if not _bn_dg or _br_dg is None:
                                        continue
                                    _bres_dg = (
                                        scoreboard.resolve_name(_bn_dg)
                                        or _bn_dg)
                                    _bcard_dg = (
                                        scoreboard.batting_card.get(
                                            _bres_dg, {}))
                                    _bcur_dg = _bcard_dg.get(
                                        "runs") or 0
                                    try:
                                        _d_dg = (int(_br_dg)
                                                 - int(_bcur_dg))
                                    except (ValueError, TypeError):
                                        continue
                                    if _d_dg > 0:
                                        _direct_bat_delta += _d_dg
                                _direct_wkt_inc = 0
                                _ext_w_dg = extracted.get("wickets")
                                if _ext_w_dg is not None:
                                    try:
                                        _direct_wkt_inc = (
                                            int(_ext_w_dg)
                                            - int(scoreboard._inn.get(
                                                "wickets") or 0))
                                    except (ValueError, TypeError):
                                        _direct_wkt_inc = 0
                                _direct_max_extras = 6
                                if _direct_wkt_inc > 0:
                                    _direct_max_extras += 6
                                _direct_explained = (
                                    _direct_bat_delta
                                    + _direct_max_extras)
                                if (_direct_advance
                                        > _direct_explained):
                                    _direct_block = True
                                    log.warn(
                                        f"  [SCORE-INF-GATE-DIRECT] "
                                        f"{_cur_dgate}→{_esi} "
                                        f"(advance="
                                        f"+{_direct_advance}) > "
                                        f"explained "
                                        f"(bat_delta="
                                        f"{_direct_bat_delta} + "
                                        f"extras_max="
                                        f"{_direct_max_extras} = "
                                        f"{_direct_explained}) — "
                                        f"rejecting direct commit. "
                                        f"P7 fix (c).")
                        else:
                            log.info(
                                f"  [SCORE-CAP-SUPPRESS-NARROW] "
                                f"DIRECT cap suppressed — "
                                f"cur={_cur_dgate} "
                                f"recovery_until="
                                f"{_state_recovery_suppress_until_frame}"
                                f" frame={frame_count}")
                        if (not _direct_block
                                and scoreboard.set(
                                    "score", _esi, frame_count)):
                            log.info(f"  [DIRECT] score→{_esi}")
                    except (ValueError, TypeError):
                        pass
                _ext_overs = extracted.get("match_overs")
                if not _direct_block_all and _ext_overs is not None:
                    _eos = str(_ext_overs).strip()
                    if "/" in _eos:
                        _eos = _eos.split("/")[0].strip()
                    try:
                        _eof = float(_eos)
                        if _eof < 20.0:
                            if scoreboard.set("overs", _eos, frame_count):
                                log.info(f"  [DIRECT] overs→{_eos}")
                    except (ValueError, TypeError):
                        pass
                _ext_wickets = extracted.get("wickets")
                if not _direct_block_all and _ext_wickets is not None:
                    try:
                        _ewi = int(_ext_wickets)
                        _prev_w = int(scoreboard._inn.get("wickets") or 0)
                        if scoreboard.set("wickets", _ewi, frame_count):
                            log.info(f"  [DIRECT] wickets→{_ewi}")
                            if _ewi > _prev_w:
                                _last_wicket_frame = frame_count
                                _new_batter_candidate = None
                                _new_batter_candidate_count = 0
                    except (ValueError, TypeError):
                        pass

            # === FIRST-FRAME INITIALIZATION ===
            # On the first valid scoreboard read, sync all derived fields
            # to the absolute values so we don't start with stale zeros.
            if not _first_frame_initialized and scoreboard._inn:
                _init_score = scoreboard._inn.get("score")
                _init_wkts = scoreboard._inn.get("wickets")
                _init_overs = scoreboard._inn.get("overs")
                if _init_score is not None and _init_wkts is not None:
                    _first_frame_initialized = True

                    # fow_count: pre-populate placeholder entries.
                    # Issue 4 fix (2026-04-21): use the single factory
                    # in Scoreboard so these cold-start placeholders
                    # carry `_unwitnessed: True` (previously they had
                    # `"unknown"/"?"` string values with no flag, so
                    # the UI rendered them as confirmed wickets).
                    _iwk = int(_init_wkts or 0)
                    if _iwk > 0 and not scoreboard.fall_of_wickets:
                        for _wi in range(1, _iwk + 1):
                            scoreboard.fall_of_wickets.append(
                                Scoreboard.make_fow_placeholder(_wi))
                        log.info(f"  [INIT] Pre-populated {_iwk} FOW "
                                 f"placeholder entries")

                    # innings: if broadcast shows chase data, set innings=2
                    # IMPORTANT: this is DETECTION, not a transition.
                    # The pipeline is starting up (cold start or mid-match
                    # restart) and we are simply observing what innings is
                    # currently in progress. We must NOT call
                    # reset_for_innings(2) — that helper is designed for
                    # LIVE transitions (innings 1 actually ended on this
                    # session). On a restart, calling it would wipe the
                    # FOW / bowling card / partnership data we just
                    # restored from cache (or the scoreboard.set_innings_2
                    # internal reset that would zero out absolute
                    # innings-2 state we are about to read from the
                    # broadcast). We also pre-mark innings 2 as
                    # already-reset so any future detection paths
                    # (broadcast-target, bowling-team-strip swap) don't
                    # spuriously fire the reset cascade for the same
                    # innings we started in.
                    _init_target = scoreboard._inn.get("target")
                    if (_init_target
                            and scoreboard.current_innings == 1):
                        scoreboard.current_innings = 2
                        _innings_reset_done_for.add(2)
                        if ball_analyzer:
                            ball_analyzer.on_innings_change(2)
                        if batting_team and bowling_team:
                            team_locked = False
                            assign_teams(
                                bowling_team, batting_team, innings=2)
                            team_locked = True
                            # P0-A / P0-B: first-frame innings-2 detect
                            # (restart / POISON-RECAL recovery) — align SM +
                            # overs consensus with Fix 16 semantics without
                            # full reset_for_innings (would wipe restored
                            # FOW / cards per comment above).
                            try:
                                score_mgr.set_innings_2(
                                    target=int(_init_target)
                                    if _init_target else None,
                                    batting_team=batting_team,
                                    reason="poison_recal_cold_start",
                                    warm_restart=True)
                            except Exception as e:  # noqa: BLE001
                                log.debug(
                                    f"[INIT] score_mgr.set_innings_2 "
                                    f"swallowed: {e}")
                            _tr_init = getattr(scoreboard, "_tracker", None)
                            if _tr_init is not None:
                                _tr_init.reset_overs_consensus()
                                log.info(
                                    "  [OVERS-TRACKER-RESET] "
                                    "source=poison_recal_cold_start "
                                    "innings=2")
                            log.info(
                                f"  [INIT] Detected innings=2 "
                                f"(target={_init_target}) — "
                                f"swapped teams: {batting_team} now "
                                f"batting (no transition reset, "
                                f"this is cold-start detection)")
                        else:
                            log.info(
                                f"  [INIT] Detected innings=2 "
                                f"(target={_init_target}) "
                                f"(no transition reset)")

                    log.info(f"  [INIT] First-frame initialization "
                             f"complete: {_init_score}-{_iwk}"
                             f"({_init_overs})")

            # === SCORER ===
            t0 = time.time()
            fow_str = json.dumps(scoreboard.fall_of_wickets[-5:]) \
                if scoreboard.fall_of_wickets else "None yet"
            history_str = json.dumps(scoreboard.get_update_history(10))

            decision = await scorer.validate(
                extracted=extracted,
                team_a=team_names[0] if team_names else "?",
                team_b=team_names[1] if len(team_names) > 1 else "?",
                batting_team=batting_team or "NOT SET",
                bowling_team=bowling_team or "NOT SET",
                innings=scoreboard.current_innings,
                target=str(scoreboard._inn.get("target") or "first innings"),
                batting_squad_roles=batting_squad_roles,
                bowling_squad_roles=bowling_squad_roles,
                batting_card=scoreboard.format_batting_card(),
                bowling_card=scoreboard.format_bowling_card(),
                live_state=scoreboard.get_live_state_str(),
                fow=fow_str,
                history=history_str,
                vision_desc=description,
            )
            s_ms = (time.time() - t0) * 1000

            # === INNINGS / TARGET — Rule 2 (Clean Design) ===
            # Deterministic triggers fire IMMEDIATELY (no consensus).
            # Cricket physics: in T20, innings 1 ends after 20 overs OR
            # 10 wickets — these are facts, not interpretations.
            # If broadcast already shows a target, prefer that over the
            # derived prev_score+1.
            _inn2_signal = False  # did this frame signal innings 2?
            if scoreboard.current_innings == 1:
                _det_overs = scoreboard._inn.get("overs") \
                    if scoreboard._inn else None
                _det_wkts = scoreboard._inn.get("wickets") \
                    if scoreboard._inn else None
                try:
                    _det_overs_f = float(_det_overs) \
                        if _det_overs is not None else 0.0
                except (ValueError, TypeError):
                    _det_overs_f = 0.0
                try:
                    _det_wkts_i = int(_det_wkts or 0)
                except (ValueError, TypeError):
                    _det_wkts_i = 0
                _bcast_target_now = _bcast.get("target") if _bcast else None
                # Prefer broadcast target when the broadcast graphic
                # explicitly states it.  Otherwise derive the target
                # from the latched innings-1 final (set in the
                # `[INNINGS-END]` block above as the broadcast
                # advanced through the closing balls), and only fall
                # back to scoreboard score+1 if neither is available.
                # This guarantees the chase target is anchored to the
                # ACTUAL final score, not a stale 19.x reading.
                _final_target = _bcast_target_now
                if _final_target is None and innings_1_total:
                    try:
                        _final_target = int(
                            innings_1_total.get("score") or 0) + 1
                        if _final_target <= 1:
                            _final_target = None
                    except (ValueError, TypeError):
                        _final_target = None
                # === Innings-break deferral (2026-04-21) ===
                # Instead of firing execute_innings_change the moment
                # we see overs=20.0, mark the innings as ended and wait
                # for real innings-2 evidence (the chasing team visible
                # on the strip with low overs, OR a broadcast target
                # counter). This keeps the UI on innings 1's latched
                # final during the 15-30 min innings break, matching
                # what a human viewer expects.
                _bat_names_this_frame = [
                    (b.get("name") or "").upper()
                    for b in (extracted.get("batters") or [])
                    if isinstance(b, dict) and b.get("name")
                ] if extracted else []
                _ext_overs_raw_now = (
                    extracted.get("match_overs") if extracted else None)
                try:
                    _ext_overs_now_f = (
                        float(_ext_overs_raw_now)
                        if _ext_overs_raw_now is not None else None)
                except (ValueError, TypeError):
                    _ext_overs_now_f = None
                _chasing_team = bowling_team  # innings 1's bowlers bat next
                _chasing_squad_names: set[str] = set()
                if _chasing_team and squads:
                    for _p in (squads.get(_chasing_team) or []):
                        _n = (str(_p) or "").upper().strip()
                        if _n:
                            _chasing_squad_names.add(_n)
                _inn2_evidence_chase_batter = any(
                    bn and any(bn in s or s in bn
                               for s in _chasing_squad_names)
                    for bn in _bat_names_this_frame
                ) if _chasing_squad_names else False
                _inn2_evidence_low_overs = (
                    _ext_overs_now_f is not None
                    and _ext_overs_now_f < 5.0
                    and (extracted or {}).get("score") is not None
                )
                _inn2_evidence_bcast_target = (
                    _bcast_target_now is not None
                    and int(_bcast_target_now or 0) > 0
                )
                # Gate accepts either:
                #   (a) A chasing-team batter visible on the strip
                #       (unambiguous — innings 2 has started), OR
                #   (b) low_overs (<5 ov) AND a broadcast target
                #       counter together (both hold only when the
                #       chase is live; neither triggers individually
                #       during replay/recap graphics).
                # low_overs or bcast_target alone are NOT sufficient —
                # the broadcast recycles summary graphics during the
                # innings break that can fake either signal in
                # isolation.
                _inn2_evidence_any = (
                    _inn2_evidence_chase_batter
                    or (_inn2_evidence_low_overs
                        and _inn2_evidence_bcast_target)
                )

                _det_all_out = _det_wkts_i >= 10
                _det_innings_end = _det_overs_f >= 20.0 or _det_all_out

                if _det_innings_end and not _inn_break_pending:
                    _src_tag = (
                        "all_out_10" if _det_all_out
                        else "overs_complete_20")
                    _inn_break_pending = True
                    _inn_break_pending_frame = frame_count
                    _inn_break_pending_source = _src_tag
                    if _src_tag in ("overs_complete_20", "all_out_10"):
                        _inn1_completed_deterministic = True
                        _inn1_batting_team_latched = batting_team
                        _inn1_bowling_team_latched = bowling_team
                        log.info(
                            "  [INN1-TEAM-LATCH] "
                            f"bat={_inn1_batting_team_latched} "
                            f"bowl={_inn1_bowling_team_latched} "
                            f"source={_src_tag} frame={frame_count}")
                    log.info(
                        f"  [INNINGS-BREAK] Innings 1 end detected "
                        f"({_src_tag}: overs={_det_overs_f} "
                        f"wickets={_det_wkts_i}) — latched_final="
                        f"{(innings_1_total or {}).get('score')} "
                        f"target={_final_target}. Holding UI on inn1 "
                        f"final until innings-2 broadcast evidence "
                        f"appears (chase-batter OR overs<5 OR target "
                        f"ticker).")

                if _inn_break_pending:
                    _frames_since = (
                        frame_count - _inn_break_pending_frame)
                    _timeout_fire = (
                        _frames_since >= _INN_BREAK_MAX_FRAMES)
                    if _inn2_evidence_any or _timeout_fire:
                        _trigger = (
                            "timeout" if _timeout_fire
                            else ("chase_batter"
                                  if _inn2_evidence_chase_batter
                                  else ("low_overs"
                                        if _inn2_evidence_low_overs
                                        else "bcast_target")))
                        log.info(
                            f"  [INNINGS-CHANGE] Firing — "
                            f"source={_inn_break_pending_source} "
                            f"trigger={_trigger} "
                            f"(frames_since_break="
                            f"{_frames_since}, "
                            f"chase_batter="
                            f"{_inn2_evidence_chase_batter}, "
                            f"low_overs="
                            f"{_inn2_evidence_low_overs} "
                            f"[ext_overs={_ext_overs_now_f}], "
                            f"bcast_target="
                            f"{_bcast_target_now}) "
                            f"target={_final_target}")
                        execute_innings_change(
                            _inn_break_pending_source or
                            "innings_break_resolved",
                            target=_final_target)

            # === INNINGS 2 END (MATCH COMPLETE) — Fix A, 2026-04-22 ===
            # Symmetric to the innings-1-end block above. T20 innings 2
            # terminates on exactly three deterministic conditions:
            #   1. target_reached: score >= target (chase successful)
            #   2. all_out:        wickets >= 10
            #   3. overs_exhausted: overs >= 20.0
            # Uses 2-frame consensus to guard against transient
            # single-frame misreads (e.g. Scout flickering 8→10 wickets
            # due to OCR noise). `scoreboard.finalize_match` is
            # idempotent, so even if consensus logic fires twice the
            # terminal state is computed exactly once.
            if (scoreboard.current_innings == 2
                    and not scoreboard.match_complete
                    and scoreboard._inn):
                try:
                    _i2_score = int(scoreboard._inn.get("score") or 0)
                except (ValueError, TypeError):
                    _i2_score = 0
                try:
                    _i2_wkts = int(scoreboard._inn.get("wickets") or 0)
                except (ValueError, TypeError):
                    _i2_wkts = 0
                try:
                    _i2_overs_f = float(
                        scoreboard._inn.get("overs") or 0.0)
                except (ValueError, TypeError):
                    _i2_overs_f = 0.0
                try:
                    _i2_target = int(scoreboard._inn.get("target") or 0)
                except (ValueError, TypeError):
                    _i2_target = 0

                _i2_target_reached = (
                    _i2_target > 0 and _i2_score >= _i2_target)
                _i2_all_out = (_i2_wkts >= 10)
                _i2_overs_exhausted = (_i2_overs_f >= 20.0)
                _i2_end_now = (
                    _i2_target_reached
                    or _i2_all_out
                    or _i2_overs_exhausted)

                if _i2_end_now:
                    _i2_end_reason = (
                        "target_reached" if _i2_target_reached
                        else "all_out" if _i2_all_out
                        else "overs_exhausted")
                    if _match_end_reason_pending == _i2_end_reason:
                        _match_end_consecutive += 1
                    else:
                        _match_end_reason_pending = _i2_end_reason
                        _match_end_consecutive = 1
                    log.info(
                        f"  [MATCH-END-PENDING] reason="
                        f"{_i2_end_reason} "
                        f"score={_i2_score}/{_i2_wkts} "
                        f"overs={_i2_overs_f} target={_i2_target} "
                        f"consecutive={_match_end_consecutive}/"
                        f"{_MATCH_END_CONFIRM}")
                    if (_match_end_consecutive
                            >= _MATCH_END_CONFIRM):
                        log.info(
                            f"  [MATCH-COMPLETE] firing — "
                            f"reason={_i2_end_reason} "
                            f"({_match_end_consecutive}-frame "
                            f"consensus)")
                        scoreboard.finalize_match(_i2_end_reason)
                else:
                    if _match_end_consecutive > 0:
                        log.info(
                            f"  [MATCH-END-PENDING] reset — "
                            f"physics no longer indicate end "
                            f"(score={_i2_score}/{_i2_wkts} "
                            f"overs={_i2_overs_f} "
                            f"target={_i2_target})")
                    _match_end_consecutive = 0
                    _match_end_reason_pending = None

            ta = decision.get("team_assignment", {})
            if isinstance(ta, dict):
                new_inn = ta.get("innings")
                target_val = ta.get("target")
                if target_val and batting_team:
                    try:
                        _tv = int(target_val)
                    except (ValueError, TypeError):
                        _tv = 0
                    if (scoreboard.current_innings == 1
                            and _tv > 50
                            and not pending_innings_2):
                        _inn2_signal = True
                        _inn2_consecutive += 1
                        if _inn2_consecutive >= _INN2_CONFIRM_FRAMES:
                            if toss_captured:
                                log.info(
                                    f"  [INNINGS] Scorer target "
                                    f"{_tv} — switching (toss, "
                                    f"{_inn2_consecutive} consecutive)")
                                scoreboard.set_innings_2(_tv)
                                team_locked = False
                                try:
                                    score_mgr.set_innings_2(
                                        target=_tv,
                                        batting_team=bowling_team,
                                        reason="scorer_innings_change")
                                except Exception as e:  # noqa: BLE001
                                    log.debug(
                                        f"[INNINGS] score_mgr.set_innings_2 "
                                        f"swallowed: {e}")
                                reset_for_innings(
                                    2,
                                    overs_reset_source="scorer_innings_change")
                                assign_teams(
                                    bowling_team, batting_team,
                                    innings=2)
                                team_locked = True
                            else:
                                pending_innings_2 = True
                                pending_target = _tv
                                log.info(
                                    f"  [INNINGS] Scorer target "
                                    f"{_tv} — pending confirmation")
                        else:
                            log.info(
                                f"  [INNINGS] Scorer target {_tv} — "
                                f"frame {_inn2_consecutive}/"
                                f"{_INN2_CONFIRM_FRAMES}, waiting")
                    elif scoreboard.current_innings == 2:
                        # Fix 9b (2026-04-26): target is monotonic-
                        # once-set in T20 chase.  The original
                        # rationale for unconditional overwrite was
                        # cold-start innings-2 detection where target
                        # was unknown until first TARGET overlay.
                        # With Fix 9a injecting target from
                        # latched innings_1_total at AUTO-SWAP
                        # boundary, team_assignment-derived target
                        # writes are typically misreads (e.g.
                        # parsing the chasing team's current score
                        # 66/4 as target=66 from a strip read).
                        # Apply two-layer guard:
                        #   (1) MONOTONIC: refuse to overwrite an
                        #       already-set target.  Idempotent
                        #       writes (same value) are silently
                        #       accepted.
                        #   (2) SANITY: when target is unset,
                        #       require proposed target > current
                        #       team score (otherwise the chase
                        #       would already be complete or
                        #       impossible).
                        try:
                            _curr_target = int(
                                scoreboard._inn.get("target") or 0)
                        except (ValueError, TypeError):
                            _curr_target = 0
                        try:
                            _curr_score = int(
                                scoreboard._inn.get("score") or 0)
                        except (ValueError, TypeError):
                            _curr_score = 0
                        if _curr_target > 0:
                            if _tv != _curr_target:
                                log.warn(
                                    f"  [TARGET-MONOTONIC] "
                                    f"Refusing inn2 target "
                                    f"overwrite {_curr_target} "
                                    f"→ {_tv} (proposal from "
                                    f"team_assignment, source: "
                                    f"strip parser)")
                        elif _tv > _curr_score:
                            scoreboard.set(
                                "target", _tv, frame_count)
                        else:
                            log.warn(
                                f"  [TARGET-SANITY] Rejecting "
                                f"target={_tv} ≤ "
                                f"current_team_score={_curr_score} "
                                f"— impossible in valid chase")
                if (new_inn == 2
                        and scoreboard.current_innings == 1
                        and batting_team
                        and not pending_innings_2):
                    _inn2_signal = True
                    _inn2_consecutive += 1
                    if _inn2_consecutive >= _INN2_CONFIRM_FRAMES:
                        if toss_captured:
                            log.info(
                                f"  [INNINGS] Scorer says innings 2"
                                f" — switching (toss, "
                                f"{_inn2_consecutive} consecutive)")
                            scoreboard.set_innings_2(
                                int(target_val) if target_val else None)
                            team_locked = False
                            try:
                                score_mgr.set_innings_2(
                                    target=int(target_val)
                                    if target_val else None,
                                    batting_team=bowling_team,
                                    reason="scorer_innings_change")
                            except Exception as e:  # noqa: BLE001
                                log.debug(
                                    f"[INNINGS] score_mgr.set_innings_2 "
                                    f"swallowed: {e}")
                            reset_for_innings(
                                2,
                                overs_reset_source="scorer_innings_change")
                            assign_teams(
                                bowling_team, batting_team, innings=2)
                            team_locked = True
                        else:
                            pending_innings_2 = True
                            pending_target = (
                                int(target_val) if target_val else None)
                            log.info(
                                f"  [INNINGS] Scorer says innings 2"
                                f" — pending batter confirmation")
                    else:
                        log.info(
                            f"  [INNINGS] Scorer says innings 2 — "
                            f"frame {_inn2_consecutive}/"
                            f"{_INN2_CONFIRM_FRAMES}, waiting")
            vision_hint = decision.get("vision_hint")
            vision_hint = _sanitize_vision_hint_names(
                vision_hint, scoreboard)
            # Append dismissed batters so scorer doesn't re-dismiss
            _cold_implausible = getattr(
                score_mgr, "last_cold_start_verdict_implausible", False)
            if scoreboard.batting_card and not _cold_implausible:
                dismissed = [n for n, c in scoreboard.batting_card.items()
                             if c.get("status") == "out"]
                if dismissed:
                    _dm = ", ".join(dismissed)
                    _suffix = f" ALREADY DISMISSED (do NOT dismiss again): {_dm}"
                    vision_hint = (vision_hint or "") + _suffix
            elif _cold_implausible:
                log.info(
                    "  [S] Hint: skipped ALREADY-DISMISSED suffix "
                    "(cold-start verdict implausible this frame)")
            if vision_hint:
                log.info(f"  [S] Hint: {vision_hint}")

            # S8: capture wicket count BEFORE the scorer runs so we
            # can decide downstream whether the change list represents
            # a real wicket (delta) versus a no-op (`wickets→0` as
            # change-list noise). Substring match on "wickets" used to
            # fire 96/140 frames and reset _new_batter_candidate.
            _pre_scorer_wkts = int(scoreboard._inn.get("wickets") or 0) \
                if scoreboard._inn else 0

            _poisoned_in_window.append(bool(_frame_poisoned))
            if (_inn_break_pending
                    and len(_poisoned_in_window) >= _POISON_RATE_WINDOW
                    and frame_count > 0
                    and frame_count % _POISON_RATE_WINDOW == 0):
                _pr = sum(_poisoned_in_window) / len(_poisoned_in_window)
                log.info(
                    "  [TEAM-ATTRIBUTION-POISON-RATE] "
                    f"rate={_pr:.2f} window={_POISON_RATE_WINDOW} "
                    f"threshold={_FRAME_POISONED_STRIP_TRUST_THRESHOLD} "
                    f"inn_break_pending={_inn_break_pending} "
                    f"frame={frame_count}")

            if _frame_poisoned:
                # Fix 4: gate consensus on `_frame_poisoned`. Poisoned
                # readings ARE NOT evidence — they're discarded data
                # from a frame our guards have judged untrustworthy.
                # Letting them feed `_correction_pending`/`count` is the
                # architectural bug that allowed score=6 to leak into
                # state at iter #17 of the KKR/RR run despite the team
                # being wrong. Recovery from a stuck team-lock is now
                # the responsibility of Fix 1 (cold-start consistency)
                # and Fix 3 (escape hatch) — *not* of consensus
                # accumulating across poisoned frames.
                changes = [f"FRAME_POISONED:{_ext_score_raw}"]
                # P7 fix (b): GRAPHIC frames are absence-of-evidence,
                # not contradicting evidence.  Resetting consensus on
                # GRAPHIC poison is what made the F184/F198 lock-in
                # unrecoverable — every GRAPHIC interleaved with the
                # SCOREBOARD stream broke the 2-frame
                # CORRECTION_BLOCKED override streak.  Preserve the
                # streak across GRAPHIC-only poison; reset on any
                # contradicting-evidence poison (mid-innings 0-0,
                # bowling-team strip, squad mismatch, score-delta>7,
                # etc.).
                if _correction_pending is not None:
                    if _poison_non_graphic:
                        _correction_pending = None
                        _correction_count = 0
                    else:
                        log.info(
                            f"  [CONSENSUS-PRESERVED-VIA-GRAPHIC] "
                            f"poison frame absence-only — "
                            f"_correction_pending={_correction_pending} "
                            f"count={_correction_count} preserved")
            else:
                changes = apply_scorer_decision(
                    scoreboard, decision,
                    frame_count, jump_guard,
                    batting_team=batting_team,
                    extracted=extracted,
                    frame_type=frame_type,
                    score_mgr=score_mgr,
                    vision_desc=description,
                    innings_transition_suppressed=(
                        frame_count
                        <= _state_recovery_suppress_until_frame))
                # 2-frame consensus for large score deltas: if the
                # same proposed score appears on consecutive frames,
                # accept it as the new truth (recovery, not corruption).
                _corr = [c for c in changes
                         if isinstance(c, str)
                         and c.startswith("CORRECTION_BLOCKED:")]
                if _corr:
                    _blocked_score = int(_corr[0].split(":")[1])
                    _record_state_recovery_guard(
                        "score_correction_blocked",
                        proposed_reset=["score"])
                    if (_correction_pending is not None
                            and _correction_pending == _blocked_score):
                        _correction_count += 1
                    else:
                        _correction_pending = _blocked_score
                        _correction_count = 1
                    if _correction_count >= _CORRECTION_CONFIRM:
                        log.info(
                            f"  [CONSENSUS] Score {_blocked_score} "
                            f"persisted {_correction_count} frames "
                            f"— accepting as new truth")
                        scoreboard.set(
                            "score", _blocked_score, frame_count)
                        changes = [
                            f"score→{_blocked_score}(consensus)"]
                        _correction_pending = None
                        _correction_count = 0
                    else:
                        log.info(
                            f"  [CONSENSUS] Score {_blocked_score} "
                            f"frame {_correction_count}/"
                            f"{_CORRECTION_CONFIRM}, waiting")
                else:
                    _score_inf = [c for c in changes
                                  if isinstance(c, str)
                                  and c.startswith("SCORE-INF-GATE:")]
                    if _score_inf:
                        _record_state_recovery_guard(
                            "score_inf_gate",
                            proposed_reset=["score"])
                    _correction_pending = None
                    _correction_count = 0
                    if not _frame_poisoned and not _score_inf:
                        _state_recovery.reset("clean_scorer_frame")

            # Track wicket frame for batter replacement consensus
            # S8: use the actual wicket-count delta instead of a
            # substring scan of `changes`. The old `"wickets" in c`
            # match also caught no-op `wickets→0` lines and reset the
            # new-batter consensus tracker every frame, which would
            # break detection when a real wicket eventually fell.
            _post_scorer_wkts = int(scoreboard._inn.get("wickets") or 0) \
                if scoreboard._inn else 0
            if _post_scorer_wkts > _pre_scorer_wkts:
                _last_wicket_frame = frame_count
                _new_batter_candidate = None
                _new_batter_candidate_count = 0
                log.info(
                    f"  [WICKET-TRACK] Wicket at F{frame_count} "
                    f"(wkts {_pre_scorer_wkts}→{_post_scorer_wkts})")

            total_ms = v_ms + e_ms + s_ms
            log.info(f"  [S {s_ms:.0f}ms] Changes: {changes or 'none'}")
            log.info(f"  Total: {total_ms:.0f}ms (V:{v_ms:.0f} E:{e_ms:.0f} S:{s_ms:.0f})")

            # === Broadcast P'SHIP / PARTNERSHIP override ===
            # Broadcasters periodically render the literal partnership
            # value, e.g. "P'SHIP 26 (18)" or "PARTNERSHIP: 26(18)".
            # When detected, hard-override our anchor — this is a
            # trusted reading that fixes any cold-start drift.
            if description and partnership_tracker:
                _pship_match = re.search(
                    r"(?:P'?SHIP|PARTNERSHIP)[\s:]*"
                    r"(\d{1,3})\s*[\(\/]\s*(\d{1,3})",
                    description.upper())
                if _pship_match:
                    _bp_runs = int(_pship_match.group(1))
                    _bp_balls = int(_pship_match.group(2))
                    _ts_now = scoreboard._inn.get("score")
                    _to_now = scoreboard._inn.get("overs")
                    if (_ts_now is not None and _to_now is not None
                            and 0 <= _bp_runs <= 400
                            and 0 <= _bp_balls <= 240):
                        _ts = int(_ts_now)
                        _tb = overs_to_balls(_to_now)
                        partnership_tracker.override(
                            _ts, _tb, _bp_runs, _bp_balls)

            # === Broadcast "THIS OVER" overlay back-fill ===
            # On cold-start mid-over, scan the strip for "THIS OVER:"
            # followed by ball symbols (digits, ., W, wd, nb). Hand
            # them to ThisOverManager.on_broadcast_override which
            # already knows how to safely fill placeholders without
            # overwriting observed balls.
            if description and over_mgr is not None:
                _to_match = re.search(
                    r"THIS\s+OVER[\s:]*([0-9wWnNbBdD\.\,\s]+?)"
                    r"(?:\s{2,}|$|FULL\s+SCORECARD|INFO_PANEL|"
                    r"SPEED|TO\s+WIN|RECENT)",
                    description.upper())
                if _to_match:
                    _raw = _to_match.group(1).strip()
                    _tokens = re.findall(
                        r"[0-7]|W|WD|NB|\.", _raw.replace(",", " "))
                    if 1 <= len(_tokens) <= 8:
                        try:
                            _bcs = scoreboard._inn.get("score")
                            over_mgr.on_broadcast_override(
                                _tokens,
                                score=int(_bcs) if _bcs is not None
                                else None)
                        except Exception as _e:
                            log.warn(
                                f"  [THIS-OVER-BCAST] override "
                                f"failed: {_e}")

            # Hard code check: detect innings 2 from vision / extractor
            _ext_target = extracted.get("target") if extracted else None
            if (description
                    and scoreboard.current_innings == 1
                    and not pending_innings_2):
                upper_desc = description.upper()

                _INN2_FALSE_POS = [
                    "PROJECTED", "PROJ SCORE", "CURRENT RUN RATE",
                    "RPO", "ECONOMY", "REQUIRED OVERS", "PAR SCORE",
                    "PREDICTED", "IF BATTING FIRST",
                ]
                if not any(fp in upper_desc for fp in _INN2_FALSE_POS):
                    detected_target = None
                    score_now = int(
                        scoreboard._inn.get("score") or 0)

                    # N7: prefer strip-local score when consensus lags.
                    _score_basis = _to_win_score_basis(
                        upper_desc, score_now)

                    # High-confidence patterns: "TO WIN" + 2-3 digit
                    # runs + delimiter + 1-3 digit balls. Accept the
                    # common IPL/TV variants (OFF, FROM, RUNS+BALLS,
                    # /, IN). The literal "TO WIN" + two integers is
                    # essentially impossible to hallucinate.
                    _high_conf_to_win = False
                    _tw_patterns = [
                        r'TO\s+WIN[\s:]+(\d{1,3})\s+OFF\s+(\d+)',
                        r'TO\s+WIN[\s:]+(\d{1,3})\s+FROM\s+(\d+)',
                        r'TO\s+WIN[\s:]+(\d{1,3})\s+RUNS?\s+(\d+)\s+BALLS?',
                        r'TO\s+WIN[\s:]+RUNS?\s+(\d{1,3})\s+BALLS?\s+(\d+)',
                        r'TO\s+WIN[\s:]+(\d{1,3})\s+IN\s+(\d+)',
                        r'TO\s+WIN[\s:]+(\d{1,3})\s*/\s*(\d+)',
                        r'NEED[\s:]+(\d{1,3})\s+OFF\s+(\d+)',
                        r'NEED[\s:]+(\d{1,3})\s+RUNS?\s+(\d+)\s+BALLS?',
                        r'REQUIRED?[\s:]+(\d{1,3})\s+OFF\s+(\d+)',
                        r'REQUIRED?[\s:]+(\d{1,3})\s+FROM\s+(\d+)',
                    ]
                    # Require score_now > 0: target = score + runs_needed
                    # is meaningless until cold-start has confirmed a
                    # score. Without this guard we'd fire target=34 on
                    # frame 1 instead of waiting for "DC 142/4 + need
                    # 34" → target=176.
                    for _pat in _tw_patterns:
                        _tw = re.search(_pat, upper_desc)
                        if _tw:
                            runs_needed = int(_tw.group(1))
                            balls_remaining = int(_tw.group(2))
                            if (runs_needed >= 1
                                    and 1 <= balls_remaining <= 120
                                    and score_now > 0):
                                detected_target = (
                                    _score_basis + runs_needed)
                                _high_conf_to_win = True
                                log.info(
                                    f"  [CODE] HIGH-CONF: score="
                                    f"{score_now} basis={_score_basis} "
                                    f"runs_needed={runs_needed} "
                                    f"balls_remaining="
                                    f"{balls_remaining} → target="
                                    f"{detected_target}  pattern="
                                    f"{_pat[:30]}")
                                break
                            elif (runs_needed >= 1
                                    and 1 <= balls_remaining <= 120):
                                log.info(
                                    f"  [CODE] HIGH-CONF deferred: "
                                    f"runs_needed={runs_needed} "
                                    f"balls={balls_remaining} but "
                                    f"score_now=0 (waiting for "
                                    f"cold-start)")

                    if not detected_target:
                        _inn2_patterns = [
                            r'TO\s+WIN\s+(\d{2,3})',
                            r'CHASING\s+(\d{2,3})',
                            r'(?<!PROJECTED\s)(?<!PROJ\s)'
                            r'TARGET\s*:?\s*(\d{2,3})',
                        ]
                        for pat in _inn2_patterns:
                            m = re.search(pat, upper_desc)
                            if m:
                                val = int(m.group(1))
                                if val > score_now and val > 50:
                                    detected_target = val
                                    break
                                elif 10 <= val <= score_now:
                                    detected_target = score_now + val
                                    log.info(
                                        f"  [CODE] {val} < score "
                                        f"→ runs needed, target="
                                        f"{detected_target}")
                                    break

                    if not detected_target and _ext_target:
                        try:
                            tv = int(_ext_target)
                            if tv > score_now and tv > 50:
                                detected_target = tv
                            elif 10 <= tv <= score_now:
                                detected_target = score_now + tv
                        except (ValueError, TypeError):
                            pass

                    if detected_target and batting_team:
                        _inn2_signal = True
                        _inn2_consecutive += 1
                        # High-confidence "TO WIN N OFF M" — 4 tokens
                        # (literal "TO WIN" + 2-3 digit runs + "OFF" +
                        # digit balls). The probability of all four
                        # tokens hallucinating coherently is effectively
                        # zero, so no consensus is needed.
                        if _high_conf_to_win:
                            log.info(
                                f"  [CODE] HIGH-CONF target "
                                f"{detected_target} — instant innings 2 "
                                f"swap (TO WIN N OFF M regex).")
                            execute_innings_change(
                                "to_win_N_off_M",
                                target=detected_target)
                        else:
                            _inn1_ov_now = float(
                                scoreboard._inn.get("overs") or "0") \
                                if scoreboard._inn else 0.0
                            _inn1_wk_now = int(
                                scoreboard._inn.get("wickets") or 0) \
                                if scoreboard._inn else 0
                            _inn1_done = (
                                _inn1_ov_now >= 20.0
                                or _inn1_wk_now >= 10)
                            if (_inn1_done
                                    and scoreboard.current_innings == 1):
                                log.info(
                                    f"  [CODE] Target "
                                    f"{detected_target} detected AND "
                                    f"innings 1 ended at "
                                    f"{_inn1_ov_now} ov / "
                                    f"{_inn1_wk_now} wkts — fast-path "
                                    f"innings 2 swap.")
                                execute_innings_change(
                                    "target_after_inn1_done",
                                    target=detected_target)
                            elif (_inn2_consecutive
                                    < _INN2_CONFIRM_FRAMES):
                                log.info(
                                    f"  [CODE] Target "
                                    f"{detected_target} — frame "
                                    f"{_inn2_consecutive}/"
                                    f"{_INN2_CONFIRM_FRAMES}, waiting")
                            elif toss_captured:
                                log.info(
                                    f"  [CODE] Innings 2 (toss): "
                                    f"target={detected_target}")
                                execute_innings_change(
                                    "scorer_target_toss",
                                    target=detected_target)
                            else:
                                pending_innings_2 = True
                                pending_target = detected_target
                                log.info(
                                    f"  [CODE] Target "
                                    f"{detected_target} detected — "
                                    f"pending batter confirmation "
                                    f"for innings 2")

            if not _inn2_signal:
                _inn2_consecutive = 0

            # Resolve pending innings 2 with batter confirmation
            if pending_innings_2 and batting_team:
                _pi2_batters = [
                    b.get("name", "").upper().strip()
                    for b in (extracted.get("batters") or [])
                    if b.get("name")
                    and len(b.get("name", "").strip()) >= 3]
                if len(_pi2_batters) >= 1:
                    _inn1_bat_squad = {
                        p.upper()
                        for p in squads.get(batting_team, [])}
                    _inn1_bowl_squad = {
                        p.upper()
                        for p in squads.get(bowling_team, [])}
                    bat_count = sum(
                        1 for bn in _pi2_batters
                        if any(bn in sq or sq in bn
                               for sq in _inn1_bat_squad)
                        and len(bn) >= 4)
                    bowl_count = sum(
                        1 for bn in _pi2_batters
                        if any(bn in sq or sq in bn
                               for sq in _inn1_bowl_squad)
                        and len(bn) >= 4)

                    if bowl_count > bat_count:
                        log.info(
                            f"  [CODE] Innings 2 confirmed: "
                            f"{bowling_team} now batting "
                            f"(inn 1 bowlers visible)")
                        scoreboard.set_innings_2(pending_target)
                        team_locked = False
                        new_bat = bowling_team
                        new_bowl = batting_team
                        assign_teams(
                            new_bat, new_bowl, innings=2)
                        team_locked = True
                        log.info(
                            f"  [CODE] Target set to "
                            f"{pending_target}")
                        pending_innings_2 = False
                        pending_target = None
                    elif bat_count > bowl_count:
                        log.info(
                            f"  [CODE] Innings 2 confirmed: "
                            f"{batting_team} is chasing "
                            f"(inn 1 batters still visible)")
                        scoreboard.set_innings_2(pending_target)
                        team_locked = False
                        assign_teams(
                            batting_team, bowling_team, innings=2)
                        team_locked = True
                        log.info(
                            f"  [CODE] Target set to "
                            f"{pending_target}")
                        pending_innings_2 = False
                        pending_target = None
                    else:
                        log.info(
                            f"  [CODE] Pending innings 2 — "
                            f"can't determine chasing team "
                            f"(bat={bat_count} bowl={bowl_count})")

            if decision.get("rejected"):
                log.info(f"  REJECTED: {decision['rejected']}")
            if decision.get("deferred"):
                log.info(f"  DEFERRED: {decision['deferred']}")

            # === Speed, Extras, This-over (broadcast-sourced only) ===
            speed_kph = _frame_speed_kph
            if not speed_kph:
                bw_ext = extracted.get("bowler") or {}
                if isinstance(bw_ext, dict):
                    speed_kph = bw_ext.get("speed_kph")
            if speed_kph:
                bowler_name = scoreboard._inn.get("current_bowler")
                if bowler_name:
                    _spd = float(speed_kph)
                    accepted = scoreboard.record_speed(bowler_name, _spd)
                    if not accepted:
                        speed_kph = None

            # === Extras: ball_event path is sole authority ===
            # The LLM extractor's `extras` dict was the historical source
            # for `record_extra`, but it (a) misses extras frequently
            # (only ~50% recall on observed wides), (b) hallucinates runs
            # (verified F68 on 2026-04-19 KKR-vs-RR: extractor returned
            # `{type: "wide", runs: 6}` for a 1-run wide, inflating
            # `extras["wides"]` and `extras["total"]` until the
            # `[EXTRAS-INF]` reconciliation clamped `total` back to the
            # CB-derived value — leaving `wides` permanently inflated and
            # the UI showing `wd8` against `total=3`).  The reliable
            # source is the ball_event=EXTRA handler below (line ~5408)
            # which fires off the score-delta signal that's already
            # gated by the scorer's confidence checks.  Routing extras
            # through ball_event also gives us a single increment site
            # for `extras["this_over"]`, which previously only fired on
            # the unreliable LLM path and so missed most over-resident
            # wides (verified same match 5.3o: 2 broadcast Wd tokens but
            # `extras.this_over=1` because only one fired record_extra).

            # this_over_broadcast from LLM extractor is ignored here —
            # the regex-based extraction in extract_broadcast_data()
            # already calls on_broadcast_override once per frame.
            # A second call risks re-injecting stale/hallucinated data.

            # Pre-fill this-over when joining mid-over
            if not over_mgr.this_over:
                _join_overs = scoreboard._inn.get("overs")
                if _join_overs:
                    over_mgr.initialize_mid_over(_join_overs)

            if over_mgr.this_over:
                over_runs = sum(int(x) for x in over_mgr.this_over
                                if isinstance(x, str) and x.isdigit())
                log.info(f"  [THIS OVER] {over_mgr.this_over} "
                         f"= {over_runs} runs")

            _cur_overs_str = scoreboard._inn.get("overs")
            _cur_bowler_name = scoreboard._inn.get("current_bowler")
            _cur_score_int = int(scoreboard._inn.get("score") or 0) if scoreboard._inn else 0

            # === ROLLBACK CHECK: was the last EXTRA retracted? ===
            # If we recorded an EXTRA's post-event score on a previous
            # frame and the tracker's current confirmed score has since
            # dropped below it WITHOUT the over rolling, the EXTRA was
            # phantom — pop the trailing Wd/Nb token from this_over.
            # Bounded to the SAME over so we don't roll back a token
            # that's already been archived to over_history.
            try:
                if (_last_extra_score is not None
                        and _last_extra_over_int is not None):
                    _cur_over_int_chk = int(float(_cur_overs_str or "0"))
                    if _cur_over_int_chk == _last_extra_over_int:
                        if _cur_score_int < _last_extra_score:
                            log.info(
                                f"  [ROLLBACK-TRIGGER] tracker score "
                                f"{_cur_score_int} < post-EXTRA score "
                                f"{_last_extra_score} (over "
                                f"{_last_extra_over_int}) — last EXTRA "
                                f"appears retracted, attempting pop")
                            _popped = over_mgr.pop_last_extra(
                                reason=(
                                    f"score regressed "
                                    f"{_last_extra_score}→{_cur_score_int} "
                                    f"in same over"))
                            if _popped:
                                _last_extra_score = None
                                _last_extra_over_int = None
                    else:
                        # Over rolled — the EXTRA is now in history,
                        # rollback no longer applies.
                        _last_extra_score = None
                        _last_extra_over_int = None
            except (ValueError, TypeError):
                pass

            # Ball detection: detect first, then decide where to append
            ball_event = ball_detector.detect(scoreboard._tracker)
            _over_changed = False
            _new_over_int = int(float(_cur_overs_str or "0"))

            # Snapshot striker BEFORE any rotation — this is who faced the ball
            _striker_this_ball = _canonical_active_slot(
                score_mgr, scoreboard, "striker")
            # `_completed_over` is captured right BEFORE check_over_change
            # archives + resets `over_mgr.this_over` (further down).  We
            # used to snapshot it HERE (before on_ball_event), but that
            # missed the closing ball — verified 2026-04-19 KKR-vs-RR
            # F547 where DETAIL logged `completed_over=['.','1','.','.','.']`
            # (5 entries, NO W) while `AFTER_this_over` correctly had
            # `['.','1','.','.','.','W']` (6 entries WITH W).  The UI
            # rendered the 5-entry version, producing the visible
            # "wicket missing from this-over pill at 7.0" bug.
            _completed_over: list = []
            _completed_over_runs = 0

            # ALWAYS append ball event BEFORE checking over change,
            # so the last ball of the over is captured in over_history
            delivery_info: dict | None = None
            if ball_event:
                if ball_event.get("type") in ("WICKET", "WICKET_LATE"):
                    if _striker_this_ball and not ball_event.get("dismissed"):
                        ball_event["dismissed"] = _striker_this_ball
                        ball_event["striker"] = _striker_this_ball
                        log.info(
                            f"  [WICKET-ATTRIB] Dismissed batter set "
                            f"from scoreboard striker: {_striker_this_ball}")
                    scoreboard.apply_known_wicket_increment(
                        ball_event.get("dismissed"))
                over_mgr.on_ball_event(
                    ball_event,
                    score=int(scoreboard._inn.get("score") or 0))
                log.info(f"  [THIS-OVER] Ball {ball_event.get('type')} "
                         f"appended to over {over_mgr._last_over_int}")
                _last_ball_event_frame = frame_count
                # Snapshot post-EXTRA score for the rollback guard
                # (see [ROLLBACK-TRIGGER] block above).  We track only
                # EXTRA events because legal-ball events (DOT/runs/W)
                # must NOT be rolled back: a score regression on those
                # is a real-data dispute that belongs in the consensus
                # tracker, not in this_over surgery.
                if ball_event.get("type") == "EXTRA":
                    try:
                        _last_extra_score = int(
                            scoreboard._inn.get("score") or 0)
                        _last_extra_over_int = (
                            over_mgr._last_over_int)
                    except (ValueError, TypeError):
                        _last_extra_score = None
                        _last_extra_over_int = None
                # Fix 3: confirms the current `assign_teams()` call was
                # the right one. Resets in `assign_teams()` itself.
                _ball_events_for_current_team += 1
                scoreboard._tracker.on_ball_event()
                # === MONITORING: first-ball-after-over latency ===
                if (_over_change_at_frame is not None
                        and _over_change_at_time is not None):
                    _frames_lag = frame_count - _over_change_at_frame
                    _ms_lag = (time.time() - _over_change_at_time) * 1000
                    log.info(
                        f"  [LATENCY] FIRST BALL after over change: "
                        f"+{_frames_lag} frames / {_ms_lag:.0f}ms")
                    if _frames_lag > 3:
                        log.warn(
                            f"  [LATENCY-HIGH] first ball took "
                            f"{_frames_lag} frames (>3 — likely "
                            f"appearing during 2nd ball broadcast)")
                    _over_change_at_frame = None
                    _over_change_at_time = None

                # Ensure striker/non-striker are active batters
                _active = [n for n, s in scoreboard.batting_card.items()
                           if s.get("status") == "batting"]
                _s = _canonical_active_slot(score_mgr, scoreboard, "striker")
                _ns = _canonical_active_slot(
                    score_mgr, scoreboard, "non")
                if _s and _s not in _active and _active:
                    _new = [a for a in _active if a != _ns]
                    _next = _new[0] if _new else _active[0]
                    _set_legacy_active_slot(
                        score_mgr, scoreboard, "striker", _next,
                        "active-slot-repair")
                    log.info(f"  [STRIKER] {_s} dismissed → {_next}")
                _ns = _canonical_active_slot(
                    score_mgr, scoreboard, "non")
                if _ns and _ns not in _active and _active:
                    _new = [a for a in _active
                            if a != _canonical_active_slot(
                                score_mgr, scoreboard, "striker")]
                    _next = _new[0] if _new else _active[0]
                    _set_legacy_active_slot(
                        score_mgr, scoreboard, "non", _next,
                        "active-slot-repair")
                    log.info(f"  [NON-STRIKER] {_ns} dismissed → "
                             f"{_next}")

                # Guard: striker and non must be different
                _s = _canonical_active_slot(score_mgr, scoreboard, "striker")
                _ns = _canonical_active_slot(
                    score_mgr, scoreboard, "non")
                if _s and _ns and _s == _ns and len(_active) >= 2:
                    _other = [a for a in _active if a != _s]
                    if _other:
                        _set_legacy_active_slot(
                            score_mgr, scoreboard, "non",
                            _other[0], "active-slot-dedup")
                        log.info(f"  [STRIKER-DEDUP] {_s} == non → "
                                 f"non={_other[0]}")

                # === Update extras tally when EXTRA event fires ===
                # Route through scoreboard.record_extra so that ALL four
                # counters (wides/no_balls/total/this_over) and the
                # extras_log audit trail stay consistent.  Previously
                # this branch hand-incremented only wides/no_balls/total
                # and silently dropped `this_over`, which broke the UI
                # "+N this over" pill (verified 2026-04-19 KKR-vs-RR
                # 5.3o: 2 broadcast Wd tokens in the over but UI showed
                # "+1 this over" because record_extra only fired from
                # the unreliable LLM-extractor path).
                _evt_runs = ball_event.get("runs", 0)
                _evt_type = ball_event.get("type", "")
                if _evt_type == "EXTRA":
                    _extra_sub = ball_event.get("extra_type", "")
                    if "wide" in _extra_sub:
                        scoreboard.record_extra("wide", _evt_runs)
                    elif "no_ball" in _extra_sub:
                        scoreboard.record_extra("no_ball", 1)
                    elif "leg_bye" in _extra_sub:
                        scoreboard.record_extra("leg_bye", _evt_runs)
                    elif "bye" in _extra_sub:
                        scoreboard.record_extra("bye", _evt_runs)

                # === S27: legacy odd-runs striker rotation removed ===
                # ScoreManager already rotates striker on odd runs as
                # part of its ball-event ingest (`score_manager.py`
                # `_apply_event` rotation logic). The legacy write
                # here raced SM and produced the per-frame Hetmyer↔
                # Jadeja flap visible in `[STRIKER-WRITE]` logs.

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
                # D2: absorbed gate before _evt_is_real — defense-in-depth
                # even if ABSORBED_LEGAL were ever classified as "real".
                if (ball_analyzer and ball_analyzer.alive
                        and not _layer2_enqueue_blocked_absorbed(ball_event)
                        and _evt_is_real):
                    _da_t0 = time.time()
                    score_delta = ball_event.get("runs", 0)
                    _over_str = ball_event.get("over")
                    try:
                        _over_num = float(_over_str) if _over_str else None
                    except (ValueError, TypeError):
                        _over_num = None
                    # Async delivery classification (2026-04-20):
                    # Hand the score event to the BallAnalyzer's
                    # background worker and return IMMEDIATELY with a
                    # pending stub.  Blocking here for 10-25s (Gemini
                    # upload + classify) was making score-event
                    # detection drift ~20s behind reality, which made
                    # retrospective lookback grab post-ball replays
                    # instead of the live delivery.  The real result
                    # is published asynchronously via
                    # ball_analyzer.last_completed_delivery_info() and
                    # we refresh _last_delivery_info below (once per
                    # frame) so every WS broadcast sees the latest.
                    # Squad-resolved handedness / bowling arm (see
                    # eyes/player_enrichment.py).  These are authoritative
                    # frame-of-reference inputs for line/shot_side/
                    # bowling_angle derivation — the per-delivery VLM
                    # no longer tries to read them off the frame.
                    try:
                        _known_handed = (
                            scoreboard.get_current_batsman_handed())
                    except Exception:
                        _known_handed = "unknown"
                    try:
                        _known_arm = scoreboard.get_current_bowling_arm()
                    except Exception:
                        _known_arm = "unknown"
                    delivery_info = ball_analyzer.enqueue_delivery_analysis(
                        runs=score_delta,
                        speed_kph=_frame_speed_kph,
                        over_number=_over_num,
                        innings=scoreboard.current_innings,
                        event_age_hint=ball_event.get("_event_age_hint"),
                        event_type=_evt_type_raw,
                        known_batsman_handed=_known_handed,
                        known_bowling_arm=_known_arm)
                    if shadow_runner is not None:
                        try:
                            shadow_runner.mark_score_event(time.time())
                        except Exception:
                            log.exception(
                                "[SHADOW] mark_score_event failed")
                    _da_ms = (time.time() - _da_t0) * 1000
                    # Only promote to _last_delivery_info when the call
                    # returned a FINAL result synchronously (legacy
                    # fallback paths).  Pending stubs are logged but
                    # don't overwrite the last real classification.
                    if (delivery_info
                            and not delivery_info.get("_untrackable")
                            and not delivery_info.get("_pending")):
                        _last_delivery_info = delivery_info
                    if delivery_info:
                        _d_method = delivery_info.get("_method", "?")
                        _d_comp = delivery_info.get("_comparison", {})
                        if delivery_info.get("_pending"):
                            log.info(
                                f"  [DELIVERY ENQUEUED] dnum="
                                f"{delivery_info.get('_delivery_num')} "
                                f"evt={delivery_info.get('_event_type')} "
                                f"runs={delivery_info.get('runs')} "
                                f"(submit_ms={_da_ms:.0f}, "
                                f"method={_d_method}) — awaiting async "
                                f"classification")
                        elif delivery_info.get("_untrackable"):
                            _skip = delivery_info.get("_skip_reason", "unknown")
                            log.info(f"  [DELIVERY SKIPPED] reason={_skip} "
                                     f"({_da_ms:.0f}ms, method={_d_method})")
                        else:
                            log.info(f"  [DELIVERY] "
                                     f"{delivery_info['commentary_line']} "
                                     f"({_da_ms:.0f}ms, "
                                     f"{delivery_info['detections']} dets, "
                                     f"method={_d_method})")
                            # === MONITORING: classification quality ===
                            _qual_fields = [
                                "length", "line", "bowling_angle",
                                "bounce", "shot_type",
                                "shot_action", "shot_intent",
                                "shot_elevation",
                                "swing_or_seam"]
                            _unknown = sum(
                                1 for _f in _qual_fields
                                if not delivery_info.get(_f)
                                or str(delivery_info.get(_f)).lower()
                                in ("unknown", "none", ""))
                            _conf = delivery_info.get(
                                "_vlm_confidence", "?")
                            _det = delivery_info.get("detections", 0)
                            _dr = delivery_info.get("detection_rate", 0)
                            _method = delivery_info.get(
                                "_method", "vlm")
                            log.info(
                                f"  [QUALITY] dets={_det} "
                                f"rate={_dr:.0%} conf={_conf} "
                                f"unknown={_unknown}/"
                                f"{len(_qual_fields)} fields "
                                f"method={_method}")
                            # `dets` is ONLY meaningful in trajectory
                            # mode (USE_TRAJECTORY_ANALYSIS=1). VLM
                            # mode does not compute optical detections,
                            # so dets=0 is the normal case there and
                            # is not by itself a quality signal.
                            if (_unknown >= 6
                                    or (_det == 0 and _method
                                        == "trajectory")
                                    or _conf == "low"):
                                log.warn(
                                    f"  [QUALITY-LOW] delivery has "
                                    f"poor classification — most "
                                    f"fields unknown / low conf "
                                    f"(method={_method})")
                        if _d_comp:
                            _sa = _d_comp.get("snapshot", {})
                            _la = _d_comp.get("three_layer", {})
                            log.info(
                                f"  [DELIVERY-AB] "
                                f"A(snap): {_sa.get('status','?')} "
                                f"{_sa.get('ms',0):.0f}ms "
                                f"{_sa.get('detections',0)} dets | "
                                f"B(3layer): {_la.get('status','?')} "
                                f"{_la.get('ms',0):.0f}ms "
                                f"{_la.get('detections',0)} dets")
                    else:
                        log.info(f"  [DELIVERY] No classification ({_da_ms:.0f}ms)")

            # Snapshot the over JUST BEFORE check_over_change archives
            # and resets it.  This is the canonical "completed over"
            # state — it includes the closing ball (incl. a W from a
            # wicket-on-the-6th-ball) because on_ball_event has
            # already appended it above.  We snapshot here rather
            # than after check_over_change because the archive call
            # mutates over_mgr.this_over to [].
            _completed_over = list(over_mgr.this_over)
            _completed_over_runs = sum(
                int(x) for x in _completed_over
                if isinstance(x, str) and x.isdigit())

            if over_mgr.check_over_change(_cur_overs_str, _cur_bowler_name, _cur_score_int):
                # Use synthesized last-ball event if the boundary was
                # missed by the normal detector (absorbed into over change)
                if over_mgr._last_ball_event and not ball_event:
                    ball_event = over_mgr._last_ball_event
                    over_mgr._last_ball_event = None
                    log.info(f"  [OVER] Recovered last-ball event: "
                             f"{ball_event['type']}")
                adaptive.on_over_change()
                # Striker rotates at end of over
                _s = _canonical_active_slot(score_mgr, scoreboard, "striker")
                _ns = _canonical_active_slot(
                    score_mgr, scoreboard, "non")
                if _s and _ns:
                    _set_legacy_active_slot(
                        score_mgr, scoreboard, "striker", _ns,
                        "over-end")
                    _set_legacy_active_slot(
                        score_mgr, scoreboard, "non", _s,
                        "over-end")
                    log.info(f"  [STRIKER] Over change rotation: "
                             f"{_ns} ← {_s}")
                _ov_f = float(_cur_overs_str or "0")
                _bt_ov = get_bowler_type(
                    _cur_bowler_name, _squad_roles) if _cur_bowler_name else None
                cricket_field.on_over_change(_ov_f, _bt_ov)
                scoreboard._bowler_must_change = True
                scoreboard._bowler_locked = False
                scoreboard._prev_over_bowler = _cur_bowler_name
                # === S16 fix: clear current_bowler + bowler-consensus
                # state on over change. Otherwise the wrapper-GUARD in
                # the bowler-update path (test_pipeline.py:4142) keeps
                # "rejecting Sunil Narine" because `_cur_bowler` is
                # still Varun. Clearing forces scoreboard.update_bowler
                # to take its first-bowler bootstrap path (line ~1369)
                # and accept the next read on first sighting. Any
                # wicket falling between over-change and the new
                # bowler being read would otherwise get credited to
                # the previous-over bowler. ===
                scoreboard._inn["last_bowler"] = (
                    scoreboard._inn.get("current_bowler"))
                scoreboard._inn["current_bowler"] = None
                scoreboard._inn["bowler_between_overs"] = True
                scoreboard._pending_bowler_name = None
                scoreboard._pending_bowler_count = 0
                # === #10: event-driven comm_bowler invalidation ===
                # SM doesn't auto-clear `bowler_name` on over change
                # (it only updates from `card.bowler_name` when set),
                # so for the 2-3 frames between over rollover and
                # the new bowler being read off the strip, both the
                # WS payload and storyteller context still carry the
                # PREVIOUS over's bowler — verified on 2026-04-19
                # KKR-vs-RR end-of-over commentary referencing the
                # outgoing bowler when the new one was already
                # bowling.  Clear all SM bowler fields synchronously
                # with the over rollover; SM's next ingest will
                # repopulate from the new strip read.
                score_mgr.bowler_name = None
                # Also invalidate the in-flight `_cur_bowler_name`
                # captured at the top of this frame so any DETAIL
                # log / commentary downstream sees the cleared
                # state instead of the snapshot from before the
                # over-change handler ran.
                _cur_bowler_name = None
                _over_changed = True
                # === MONITORING: arm first-ball + bowler-change timers ===
                _over_change_at_frame = frame_count
                _over_change_at_time = time.time()
                _bowler_change_request_at_frame = frame_count
                _bowler_change_request_at_time = time.time()
                _bowler_change_request_overs = _cur_overs_str
                log.info(f"  [OVER CHANGE] → {_cur_overs_str}")
                log.info(f"  [LATENCY] over-change at F{frame_count}; "
                         f"awaiting first ball + new bowler")

            # Compute run rate from score and overs
            _rr_score = scoreboard._inn.get("score")
            _rr_overs = scoreboard._inn.get("overs")
            if _rr_score is not None and _rr_overs is not None:
                try:
                    _rr_ov_f = float(_rr_overs)
                    _rr_whole = int(_rr_ov_f)
                    _rr_part = round((_rr_ov_f % 1) * 10)
                    _rr_balls = _rr_whole * 6 + _rr_part
                    if _rr_balls > 0:
                        _rr = round(float(_rr_score) / _rr_balls * 6, 2)
                        scoreboard.set("run_rate", _rr, frame_count)
                except (ValueError, TypeError, ZeroDivisionError):
                    pass

            state = scoreboard.get_live_state()
            log.info(f"  STATE: {state.get('batting_team') or '?'} "
                     f"{state.get('score')}-{state.get('wickets')} "
                     f"({state.get('overs')}) inn={state.get('innings')} "
                     f"RR={state.get('run_rate') or '—'} | "
                     f"Bat: {scoreboard.get_current_batters()} | "
                     f"Bowl: {scoreboard.get_current_bowler()}")
            try:
                _bs = int(_before_state["score"]) if (
                    _before_state.get("score") is not None) else None
            except (TypeError, ValueError):
                _bs = None
            try:
                _as = int(state["score"]) if state.get("score") is not None else None
            except (TypeError, ValueError):
                _as = None
            try:
                over_mgr.fill_strip_coverage_gap(
                    _before_state.get("overs"),
                    scoreboard._inn.get("overs") if scoreboard._inn else None,
                    _bs, _as, frame_count)
            except (TypeError, ValueError, AttributeError):
                pass

            # === MONITORING: bowler-change lag ===
            if (_bowler_change_request_at_frame is not None
                    and _bowler_change_request_at_time is not None):
                # current_bowler is the canonical name; _prev_over_bowler
                # is also a name. Compare names only (get_current_bowler()
                # returns "Name W-R" which would never equal a bare name).
                _now_bowler = scoreboard._inn.get("current_bowler")
                _prev_bowler = scoreboard._prev_over_bowler
                if _now_bowler and _now_bowler != _prev_bowler:
                    _bc_frames = (
                        frame_count - _bowler_change_request_at_frame)
                    _bc_ms = (
                        (time.time() - _bowler_change_request_at_time)
                        * 1000)
                    log.info(
                        f"  [LATENCY] BOWLER CHANGE picked up: "
                        f"{_prev_bowler} → {_now_bowler} after "
                        f"+{_bc_frames} frames / {_bc_ms:.0f}ms "
                        f"(over rolled at "
                        f"{_bowler_change_request_overs})")
                    if _bc_frames > 4:
                        log.warn(
                            f"  [LATENCY-HIGH] bowler card took "
                            f"{_bc_frames} frames to update")
                    _bowler_change_request_at_frame = None
                    _bowler_change_request_at_time = None
                    _bowler_change_request_overs = None
                else:
                    _lag_bc_frames = (
                        frame_count - _bowler_change_request_at_frame)
                    _lag_bc_secs = (
                        time.time() - _bowler_change_request_at_time)
                    if _lag_bc_frames > 6 or _lag_bc_secs > 30:
                        log.warn(
                            f"  [BOWLER-LATENCY-HARDCAP] bowler unresolved "
                            f"{_lag_bc_frames} frames / "
                            f"{_lag_bc_secs:.1f}s since over change "
                            f"(now={_now_bowler!r} was={_prev_bowler!r}) "
                            f"— clearing current_bowler")
                        scoreboard._inn["last_bowler"] = (
                            scoreboard._inn.get("current_bowler"))
                        scoreboard._inn["current_bowler"] = None
                        scoreboard._inn["bowler_between_overs"] = True
                        scoreboard._pending_bowler_name = None
                        scoreboard._pending_bowler_count = 0
                        _bowler_change_request_at_frame = None
                        _bowler_change_request_at_time = None
                        _bowler_change_request_overs = None
                    elif _lag_bc_frames > 3 or _lag_bc_secs > 15:
                        log.warn(
                            f"  [LATENCY-STUCK] bowler card still "
                            f"showing {_now_bowler} (was "
                            f"{_prev_bowler}) after "
                            f"{_lag_bc_frames} frames / "
                            f"{_lag_bc_secs:.1f}s since over change")

            # === CRICKET CHECKS (after all updates) ===
            inv_corrections = cricket_checker.check(
                scoreboard._inn,
                scoreboard.batting_card,
                scoreboard.bowling_card,
                over_mgr.this_over,
                scoreboard._tracker,
            )
            if inv_corrections:
                log.info(f"  [CRICKET] {len(inv_corrections)} corrections")
                state = scoreboard.get_live_state()

            # === SCORE MANAGER (shadow mode) ===
            # Hybrid data source:
            #   score/wickets/overs → pipeline state (post-scorer, in sync with BED)
            #   batter/bowler stats → raw extractor (current on-screen values)
            _ext_batters = extracted.get("batters") or []
            _ext_bowler_sm = extracted.get("bowler")
            _eb1, _eb2 = _align_extractor_batters_for_sm(
                _ext_batters,
                scoreboard=scoreboard,
                score_mgr=score_mgr,
                log=log,
            )
            _sm_frame = FrameInput(
                frame_id=str(frame_count),
                timestamp=time.time(),
                ext_score=_safe_int(state.get("score")),
                ext_wickets=_safe_int(state.get("wickets")),
                ext_overs=_validate_overs(
                    _safe_float(state.get("overs")),
                    _bcast.get("this_over_broadcast"),
                    confirmed_overs=_safe_float(score_mgr.overs)),
                ext_bat1_name=(
                    _eb1.get("name") if _eb1 else None),
                ext_bat1_runs=(
                    _safe_int(_eb1.get("runs")) if _eb1 else None),
                ext_bat1_balls=(
                    _safe_int(_eb1.get("balls")) if _eb1 else None),
                ext_bat2_name=(
                    _eb2.get("name") if _eb2 else None),
                ext_bat2_runs=(
                    _safe_int(_eb2.get("runs")) if _eb2 else None),
                ext_bat2_balls=(
                    _safe_int(_eb2.get("balls")) if _eb2 else None),
                ext_bowler_name=(_ext_bowler_sm.get("name")
                                 if _ext_bowler_sm else None),
                ext_bowler_wickets=(_safe_int(_ext_bowler_sm.get("wickets"))
                                    if _ext_bowler_sm else None),
                ext_bowler_runs=(_safe_int(_ext_bowler_sm.get("runs"))
                                 if _ext_bowler_sm else None),
                ext_bowler_overs=(_safe_float(_ext_bowler_sm.get("overs"))
                                  if _ext_bowler_sm else None),
                scorer_changes=(changes if isinstance(changes, list)
                                else []),
                speed_kph=_frame_speed_kph,
                broadcast_extra=_bcast.get("broadcast_extra"),
                broadcast_this_over=_bcast.get("this_over_broadcast"),
                broadcast_target=_bcast.get("target"),
                broadcast_striker=_bcast.get("striker_broadcast"),
                broadcast_venue=_broadcast_cache.get("venue"),
                broadcast_team=(_broadcast_cache.get("team_abbr")
                                or extracted.get("batting_team_visible")),
                broadcast_match_info=_broadcast_cache.get("match_info"),
                scout_text=description or "",
                action_text=current_action,
                delivery_info=delivery_info,
                drs_state=_drs_state,
            )
            _sm_was_cold = score_mgr.mode == "COLD_START"
            _sm_result = score_mgr.on_frame(_sm_frame)
            if (_sm_was_cold and score_mgr.mode == "WARM"
                    and _sm_result
                    and ((score_mgr.wickets or 0) > 0
                         or float(score_mgr.overs or 0.0) >= 1.0)):
                over_mgr.resync_to_over(
                    score_mgr.overs,
                    reason="score_manager_mid_innings_recovery")

            _sm_belist_fan = (_sm_result or {}).get("ball_events") or []
            if any(e.get("type") == ABSORBED_LEGAL for e in _sm_belist_fan):
                _sc_abs = int(scoreboard._inn.get("score") or 0)
                for _abe in _sm_belist_fan:
                    if _abe.get("type") == ABSORBED_LEGAL:
                        over_mgr.on_ball_event(_abe, score=_sc_abs)
                        log.info(
                            f"  [THIS-OVER] Ball {_abe.get('type')} "
                            f"ix={_abe.get('ball_index')} "
                            f"over={_abe.get('over')}")
                        _ball_events_for_current_team += 1

            if _sm_result and _sm_result.get("ball_event"):
                _sm_evt = _sm_result["ball_event"]
                _sm_belist = (_sm_result or {}).get("ball_events") or []
                _sm_decomposed_abs = (
                    len(_sm_belist) > 1
                    and any(e.get("type") == ABSORBED_LEGAL
                            for e in _sm_belist))
                if _sm_decomposed_abs:
                    log.info(
                        "  [SHADOW-DECOMPOSED] SM absorbed decomposition "
                        f"n={len(_sm_belist)} last_type={_sm_evt.get('type')!r} "
                        f"BED={(ball_event or {}).get('type')!r}")
                elif ball_event:
                    _sm_type = _sm_evt.get("type", "")
                    _bed_type = ball_event.get("type", "")
                    # Normalize event types for comparison
                    _norm = {"1_RUNS": "RUNS", "2_RUNS": "RUNS",
                             "3_RUNS": "RUNS", "EXTRA": "WIDE"}
                    _sm_n = _norm.get(_sm_type, _sm_type)
                    _bed_n = _norm.get(_bed_type, _bed_type)
                    _sm_match = (_sm_n == _bed_n
                                 or (_sm_n in ("WIDE", "NO_BALL")
                                     and _bed_n in ("WIDE", "NO_BALL",
                                                    "EXTRA")))
                    log.info(f"  [SHADOW] SM={_sm_type} "
                             f"BED={_bed_type} "
                             f"{'MATCH' if _sm_match else 'MISMATCH'}")
                else:
                    log.info(f"  [SHADOW] SM={_sm_evt['type']} "
                             f"BED=None EXTRA_FIRE")
            elif ball_event:
                log.info(f"  [SHADOW] SM=None "
                         f"BED={ball_event.get('type')} MISSED")

            # === Pull async delivery classification result ===
            # enqueue_delivery_analysis hands the DWR + Gemini call to
            # a background worker and returns a pending stub; we poll
            # the BallAnalyzer's shared slot every frame so WS payloads
            # carry the freshest completed classification, not the one
            # frozen at event time.
            if ball_analyzer and ball_analyzer.alive:
                _async_latest = (
                    ball_analyzer.last_completed_delivery_info())
                if (_async_latest is not None
                        and _async_latest is not _last_delivery_info):
                    _last_delivery_info = _async_latest

            # === WebSocket broadcast ===
            # Dual-broadcaster unification (Path A): every WS frame
            # goes through build_full_payload(), which owns the
            # canonical projection for UI fields. ScoreManager still
            # computes events and wire text, but its raw payload no
            # longer bypasses the scoreboard/ThisOverManager-backed
            # field sources on event frames.
            ws_payload = build_full_payload(speed_kph=speed_kph)
            if _striker_this_ball:
                ws_payload["striker_this_ball"] = _striker_this_ball
            if _last_dismissal_mode:
                ws_payload["dismissal_mode"] = _last_dismissal_mode
            if _over_changed and _completed_over:
                ws_payload["completed_over"] = _completed_over
                ws_payload["completed_over_runs"] = _completed_over_runs
            if not score_mgr.shadow and _sm_result is not None:
                # Pre-format Wire so InlineCommentary skips the LLM call,
                # while keeping the WS payload shape canonical.
                _sm_evt = _sm_result.get("ball_event")
                _sm_all = (_sm_result.get("ball_events")
                           if isinstance(_sm_result, dict) else None)
                if _sm_all:
                    ws_payload["ball_events"] = _sm_all
                if _sm_evt:
                    ws_payload["ball_event"] = _sm_evt
                    _gap_wire = None
                    for _ev in (_sm_all or []):
                        _gp = _ev.get("gap_parent")
                        if _gp:
                            _gap_wire = format_absorbed_gap_wire(
                                _gp, ws_payload.get("scorecard", {}),
                                score_mgr)
                            break
                    if _gap_wire:
                        ws_payload["_wire_override"] = _gap_wire
                    else:
                        # Batch O (2026-05-04): prefer BED's authoritative
                        # ball_event over SM's warm-mode inference.  SM's
                        # `self.score` is a live property over scoreboard._inn,
                        # which the broadcast tracker has already mutated by
                        # the time on_frame runs — so d_score==0 in warm mode
                        # and _infer_legal returns DOT for every legal ball.
                        # See files/docs/investigations/
                        # wire_commentary_no_run_hallucination.md §B-§C1.
                        _wire_event = ball_event if ball_event else _sm_evt
                        _plain = format_wire(
                            _wire_event, ws_payload.get("scorecard", {}),
                            score_mgr)
                        if _plain:
                            ws_payload["_wire_override"] = _plain
            _assert_payload_invariants(ws_payload)
            await broadcast_state(ws_payload)

            scoreboard._tracker._flush_entity_suspicion()
            scoreboard.validate_state_consistency()
            save_match_state(frame_count)

            # === COMMENTARY GENERATION (inline) ===
            comm_t0 = time.time()
            comm_results: dict[str, dict] = {}
            if _commentary_engine is not None:
                try:
                    # Fix 2 (2026-04-24) — pass the BED-authored
                    # ball_event so wires / no-balls / DRS events
                    # (balls_delta == 0 on the strip) actually
                    # generate commentary. Previously
                    # InlineCommentary re-ran its own narrower
                    # detector and silently skipped ~5% of BED
                    # events that didn't coincide with an overs
                    # tick.
                    comm_results = await _commentary_engine.generate(
                        ws_payload, ball_event_hint=ball_event)
                except Exception as _ce:
                    log.error(f"  [COMM] Error: {_ce}")
            comm_ms = (time.time() - comm_t0) * 1000
            if comm_results:
                _comm_names = ", ".join(f"{k}({v['latency_ms']}ms)"
                                        for k, v in comm_results.items())
                log.info(f"  [COMM {comm_ms:.0f}ms] {_comm_names}")

            # === COMMENTARY DATA (derived from deltas) ===
            if ball_event:
                evt_type = ball_event.get("type", "")

                if evt_type in ("WICKET", "WICKET_LATE"):
                    cricket_field.on_wicket()
                    # === Day-1.5 follow-up: explicit `dismissed` ===
                    # SM's `_apply_event` WICKET branch falls back to
                    # `self.striker` when `event["dismissed"]` is unset
                    # (`score_manager.py:1291-1298`).  SM's internal
                    # `self.striker` lags by one rotation in some
                    # over-change + odd-runs sequences (verified on
                    # KKR-vs-RR W6: SM had Hetmyer as striker but
                    # broadcast '*' marker + balls-faced delta both
                    # agreed Jadeja was on strike — the scoreboard
                    # `_inn["striker"]` correctly tracked Jadeja via
                    # the broadcast indicator).  Pass scoreboard's
                    # striker explicitly so SM doesn't have to guess.
                    # === S17: resolve dismissal_mode for THIS wicket ===
                    # Priority: explicit `_last_dismissal_mode` (broadcast
                    # graphic) → ring-buffer hint (action text or
                    # graphic that was already cleared by TTL) → None.
                    #
                    # #13: only use `_last_dismissal_mode` if it has
                    # NOT already been consumed by a previous WICKET.
                    # In a death-over collapse W{N} and W{N+1} can
                    # both fire inside the 8-frame TTL window; without
                    # the consumed gate, W{N+1} would inherit W{N}'s
                    # mode and silently mis-attribute the dismissal.
                    _eligible_mode = (
                        _last_dismissal_mode
                        if not _last_dismissal_mode_consumed
                        else None)
                    _resolved_dm = (
                        _eligible_mode
                        or _consume_dismissal_hint(frame_count))
                    if _resolved_dm:
                        ball_event["dismissal_mode"] = _resolved_dm
                        # Pipe into scoreboard so the next
                        # `_auto_dismiss_for_new_batter` call paints
                        # the FOW entry with this kind instead of the
                        # "inferred (replaced by new batter)" stub.
                        scoreboard.pending_dismissal_hint = _resolved_dm
                        scoreboard.pending_dismissal_bowler = (
                            scoreboard._inn.get("current_bowler"))
                        scoreboard.pending_dismissal_hint_frame = frame_count
                        # Promote it onto _last_dismissal_mode for the
                        # next 1-2 frames so the WS payload sticks the
                        # mode to the wicket the user is looking at,
                        # then S4 TTL ages it out.
                        _last_dismissal_mode = _resolved_dm
                        _last_dismissal_mode_frame = frame_count
                        log.info(
                            f"  [DISMISSAL] Wicket attributed kind="
                            f"{_resolved_dm!r} bowler="
                            f"{scoreboard.pending_dismissal_bowler!r}")
                    else:
                        # Truly no hint — clear so the next ball doesn't
                        # inherit a stale value.
                        _last_dismissal_mode = None
                        _last_dismissal_mode_frame = 0
                        if _last_dismissal_mode_consumed:
                            log.info(
                                f"  [DISMISSAL] No fresh hint for "
                                f"this wicket; previous mode was "
                                f"already consumed by W{(scoreboard._inn or {}).get('wickets', '?')-1 if scoreboard._inn else '?'}"
                                f" — recording as 'inferred' rather "
                                f"than inheriting stale value.")
                    # #13: mark consumed AFTER attribution so the next
                    # WICKET in this collapse window cannot reuse the
                    # same mode.
                    _last_dismissal_mode_consumed = True
                else:
                    # S4: any non-wicket ball event proves the prior
                    # dismissal graphic was either pre-match noise or
                    # already accounted for. Clear so we never emit
                    # `dismissal_mode=bowled` on a delivery where no
                    # wicket actually fell.
                    if _last_dismissal_mode:
                        log.info(
                            f"  [DISMISSAL-CLEAR] Non-wicket event "
                            f"{evt_type} — clearing stale "
                            f"{_last_dismissal_mode!r}")
                        _last_dismissal_mode = None
                        _last_dismissal_mode_frame = 0

                action_for_event = current_action or pending_action
                if action_for_event:
                    ball_event["action"] = action_for_event
                    if "free hit" in action_for_event.lower():
                        ball_event["free_hit"] = True
                        log.info(f"  [FREE HIT] detected from action text")
                pending_action = None

                team_score = scoreboard._inn.get("score") or 0
                team_balls = overs_to_balls(
                    scoreboard._inn.get("overs") or "0")
                ended_partnership = partnership_tracker.update(
                    state.get("active_batters", {}), team_score, team_balls)

                situation = get_match_situation(state)
                spell = get_spell_analysis(
                    scoreboard.bowling_card,
                    scoreboard._inn.get("current_bowler"))
                batter_phases = {
                    n: get_batter_phase(s)
                    for n, s in state.get("active_batters", {}).items()}
                partnership = partnership_tracker.current(
                    team_score, team_balls)

                packet = {
                    "event": ball_event,
                    "action": current_action,
                    "scorecard": {
                        "score": state.get("score"),
                        "wickets": state.get("wickets"),
                        "overs": state.get("overs"),
                        "target": state.get("target"),
                        "innings": state.get("innings"),
                    },
                    "batter_phases": batter_phases,
                    "bowler_spell": spell,
                    "partnership": ended_partnership or partnership,
                    "match_situation": situation,
                    "this_over": over_mgr.get_display(
                        scoreboard._inn.get("overs")),
                    "field": {
                        "positions": cricket_field.get_display_positions(),
                        "formation": cricket_field.template_name,
                    },
                }

                _cert = "✓" if ball_event.get("certain") else "?"
                _bd = ball_event.get("balls_delta", 0)
                log.info(f"  [BALL EVENT {_cert}] {ball_event['type']} "
                         f"| {ball_event.get('over')} "
                         f"| +{ball_event.get('runs',0)} runs "
                         f"(Δballs={_bd})"
                         f"{' | ' + current_action[:60] if current_action else ''}")

                # P1-5 (2026-04-22): boundary accumulator.  Gates on
                # ball_event["type"], NOT runs, so wide-fours (type=
                # EXTRA), overthrow-sixes (type=SIX), all-run fours
                # (type=4_RUNS), and bye-fours (type=EXTRA) are each
                # handled correctly out of the box. Striker source of
                # truth is the ScoreManager (sole authority for
                # striker/non post-S18); fall back to
                # scoreboard._inn only if SM hasn't seeded yet.
                try:
                    _be_type = (ball_event.get("type") or "").upper()
                    if _be_type in ("FOUR", "SIX"):
                        _striker_for_bdy = _canonical_active_slot(
                            score_mgr, scoreboard, "striker")
                        scoreboard.accumulate_boundary(
                            _striker_for_bdy,
                            "four" if _be_type == "FOUR" else "six")
                except Exception as _bdy_exc:  # noqa: BLE001
                    log.warn(f"  [BDY-ACC] swallowed: {_bdy_exc}")
                if situation.get("phase"):
                    log.info(f"  [SITUATION] {situation['phase']} — "
                             f"need {situation.get('runs_needed','?')} "
                             f"from {situation.get('balls_remaining','?')} "
                             f"@ {situation.get('required_rate','?')} rpo")
            elif current_action:
                log.info(f"  [ACTION] {current_action[:80]}")

            # === FIELD MERGE (YOLO + vision from extractor) ===
            _vision_field = extracted.get("field_observed") if extracted else None
            merged_field = field_merger.merge(
                yolo_positions, _vision_field, frame_count)
            match_overs = (scoreboard._inn.get("overs")
                           if scoreboard._inn else None)

            if merged_field["source"] != "none":
                field_state.update(
                    merged_field["positions"], frame_count, match_overs)
                _ov_for_field = float(match_overs or 0)
                cricket_field.update_from_observation(
                    yolo_positions,
                    frame_type=frame_type.lower(),
                    overs=_ov_for_field)
                # Keeper: trust vision first, YOLO fallback
                if _vision_field and _vision_field.get("keeper_visible"):
                    field_state.keeper_position = _vision_field.get(
                        "keeper_position", "back")
                elif merged_field.get("keeper"):
                    field_state.keeper_position = merged_field["keeper"]
                if merged_field["source"] in (
                        "yolo", "yolo+vision", "vision_only"):
                    field_state.last_observed_frame = frame_count
                    field_state.balls_since_observation = 0

                recent = field_state.get_changes_since(frame_count)
                for ch in recent:
                    if ch.get("frame") == frame_count:
                        field_log.info(
                            f"[F{frame_count}] {ch.get('meaning', '')}")

            # Broadcaster field graphic validation
            fg = extracted.get("field_graphic") if extracted else None
            if fg and fg.get("detected") and fg.get("positions"):
                broadcast_field = fg["positions"]
                validation = field_validator.validate(
                    field_state.positions, broadcast_field)
                field_state.calibrate(broadcast_field)
                if validation and validation["accuracy"] < 0.6:
                    field_log.info(
                        f"[F{frame_count}] Low accuracy "
                        f"({validation['accuracy']:.0%}) — "
                        f"recalibrating from broadcast")

            # Periodic field stats
            if frame_count % 30 == 0 and field_state.positions:
                total = len(field_state.positions)
                yolo_sourced = sum(1 for p in field_state.positions
                                   if p.get("source") != "vision")
                vision_sourced = total - yolo_sourced
                field_log.info(
                    f"[F{frame_count}] {field_state.formation} | "
                    f"total:{total} (yolo:{yolo_sourced} vis:{vision_sourced}) | "
                    f"slips:{field_state.slips} "
                    f"in:{field_state.inside_circle} "
                    f"out:{field_state.outside_circle} | "
                    f"keeper:{field_state.keeper_position or '?'} | "
                    f"fresh:{field_state.balls_since_observation} balls ago | "
                    f"conf:{field_state.confidence:.1f} | "
                    f"{ft_ms:.0f}ms")
                if field_validator.accuracy_log:
                    field_log.info(
                        f"[FIELD VALID] Avg accuracy: "
                        f"{field_validator.get_average_accuracy():.0%} "
                        f"across {len(field_validator.accuracy_log)} "
                        f"validations")

            # === DETAILED FRAME LOG (for analysis) ===
            _yolo_count = len(yolo_positions) if yolo_positions else 0
            _bat1 = _bat2 = "—"
            for _bn, _bc in scoreboard.batting_card.items():
                if _bc.get("status") == "batting":
                    _bs = f"{_bn} {_bc.get('runs','?')}({_bc.get('balls','?')})"
                    if _bc.get("position", 99) <= 2 or _bat1 == "—":
                        if _bat1 == "—":
                            _bat1 = _bs
                        else:
                            _bat2 = _bs
                    else:
                        _bat2 = _bs
            _bowl_name = scoreboard._inn.get("current_bowler") or "—"
            _bowl_entry = scoreboard.bowling_card.get(_bowl_name, {})
            _bowl_str = (f"{_bowl_name} "
                         f"{_bowl_entry.get('wickets','?')}-"
                         f"{_bowl_entry.get('runs','?')} "
                         f"({_bowl_entry.get('overs','?')})")
            _this_over_display = over_mgr.get_display(
                scoreboard._inn.get("overs"))
            _this_over_src = ",".join(
                f"{t}({s})" for t, s in
                zip(over_mgr.this_over, over_mgr.this_over_sources)
            ) if over_mgr.this_over_sources else ""
            _field_pos = cricket_field.get_display_positions()
            _fielder_names = [p["name"] for p in _field_pos
                              if p["type"] not in ("wk", "bowler", "bat")]
            # Fix 5 — frozen-field monitor.  We don't *do* anything; we
            # just emit a one-line warning every 30 frames if the field
            # signature hasn't changed.  Pair with the broadcast log to
            # decide whether the field really should have moved.
            try:
                _field_sig = "|".join(
                    f"{p.get('type','?')}:{p.get('name','?')}:"
                    f"{p.get('x',0):.0f},{p.get('y',0):.0f}"
                    for p in _field_pos)
            except Exception:
                _field_sig = ""
            if _field_sig != _field_last_signature:
                _field_last_signature = _field_sig
                _field_last_change_frame = frame_count
            else:
                _stale_frames = frame_count - _field_last_change_frame
                if (_stale_frames >= _FIELD_FROZEN_WARN_THRESHOLD
                        and (frame_count - _field_frozen_warn_last_at)
                        >= _FIELD_FROZEN_WARN_THRESHOLD):
                    _field_frozen_warn_last_at = frame_count
                    log.info(
                        f"  [FIELD-MONITOR] Field unchanged for "
                        f"{_stale_frames} frames "
                        f"(template={cricket_field.template_name}, "
                        f"frozen={cricket_field._frozen}, "
                        f"phase={cricket_field.phase}). "
                        f"If a wicket / over / bowler change has "
                        f"happened in this window, the field-state "
                        f"updater is the bug.")
            _ext_bat_str = ""
            if extracted and extracted.get("batters"):
                _ext_bat_str = " | ".join(
                    f"{b.get('name','?')} {b.get('runs','?')}({b.get('balls','?')})"
                    for b in extracted["batters"])
            _ext_bowl_str = ""
            if extracted and extracted.get("bowler") and isinstance(extracted["bowler"], dict):
                _eb = extracted["bowler"]
                _ext_bowl_str = (f"{_eb.get('name','?')} "
                                 f"{_eb.get('wickets','?')}-"
                                 f"{_eb.get('runs','?')} "
                                 f"({_eb.get('overs','?')})")

            # === DETAIL log reads SM directly (issue #8 tail) ===
            # `state.get("striker")` reads `scoreboard._inn["striker"]`,
            # which after the S27 cutover is no longer kept in sync by
            # the legacy striker writers and lags SM by 1-2 frames on
            # wicket / over-change frames.  SM is the UI authority for
            # striker / non-striker, so the DETAIL log should match.
            _striker = score_mgr.striker or state.get("striker") or "—"
            _non = (score_mgr.non
                            or state.get("non") or "—")
            _run_rate = state.get("run_rate")
            _run_rate_str = f"{_run_rate:.2f}" if _run_rate else "—"
            _target = state.get("target") or "—"
            _innings = state.get("innings", "?")
            _pship = ""
            if partnership_tracker and partnership_tracker.current_pair:
                _ts = scoreboard._inn.get("score") or 0
                _tb = overs_to_balls(scoreboard._inn.get("overs") or "0")
                _p = partnership_tracker.current(_ts, _tb)
                if _p:
                    _pship = f"{_p.get('runs',0)}({_p.get('balls',0)})"
            scoreboard.sync_fow_to_wickets()
            # `infer_fow_from_batting_order()` was the source of the
            # 2026-04-19 W6 Jofra-Archer→Vaibhav-Sooryavanshi flip — it
            # walked the batting order and "guessed" a dismissed batter
            # for every unknown FOW slot.  Removed under no-fabrication
            # policy; placeholders now stay `_unwitnessed=True` until a
            # real wicket event or CB scrape fills them.
            _fow_count = len(scoreboard.fall_of_wickets)

            _cw = comm_results.get("wire", {})
            _cs = comm_results.get("storyteller", {})
            _ca = comm_results.get("analyst", {})
            _cc = comm_results.get("colour", {})

            _frame_wall_ms = (time.time() - _frame_wall_t0) * 1000
            _api_ms = v_ms + e_ms + s_ms + ft_ms + comm_ms
            _code_ms = max(0, _frame_wall_ms - _api_ms)

            _detail_line = (
                f"DETAIL|F{frame_count}|{frame_type}|"
                f"tag={frame_type}|"
                f"scout={description[:120].replace(chr(10), ' ') if description else '—'}|"
                f"action={current_action[:100] if current_action else '—'}|"
                f"ext_score={extracted.get('score')}-{extracted.get('wickets')}"
                f"({extracted.get('match_overs')})|"
                f"ext_bat={_ext_bat_str}|"
                f"ext_bowl={_ext_bowl_str}|"
                f"scorer_changes={changes if 'changes' in dir() else '—'}|"
                f"yolo={_yolo_count}|"
                f"BEFORE_score={_before_score}|"
                f"BEFORE_bat1={_before_bat1}|BEFORE_bat2={_before_bat2}|"
                f"BEFORE_bowl={_before_bowl}|"
                f"BEFORE_this_over={_before_this_over}|"
                f"AFTER_score={state.get('score')}-{state.get('wickets')}"
                f"({state.get('overs')})|"
                f"AFTER_bat1={_bat1}|AFTER_bat2={_bat2}|"
                f"AFTER_bowl={_bowl_str}|"
                f"AFTER_this_over={_this_over_display}|"
                f"AFTER_this_over_src={_this_over_src}|"
                f"AFTER_striker={_striker}|"
                f"AFTER_non={_non}|"
                f"AFTER_run_rate={_run_rate_str}|"
                f"AFTER_target={_target}|"
                f"AFTER_innings={_innings}|"
                f"AFTER_partnership={_pship or '—'}|"
                f"AFTER_fow_count={_fow_count}|"
                f"AFTER_field={cricket_field.template_name} "
                f"frozen={cricket_field._frozen} "
                f"fielders={_fielder_names[:9]}|"
                f"ball_event={ball_event.get('type') if ball_event else '—'}|"
                f"ball_event_runs={ball_event.get('runs', '—') if ball_event else '—'}|"
                f"ball_event_over={ball_event.get('over', '—') if ball_event else '—'}|"
                f"ball_event_extra={ball_event.get('extra_type', '—') if ball_event else '—'}|"
                f"ball_event_free_hit={'yes' if ball_event and ball_event.get('free_hit') else '—'}|"
                f"broadcast_extra={_bcast_extra or '—'}|"
                f"dismissal_mode={_last_dismissal_mode or '—'}|"
                f"striker_this_ball={_striker_this_ball or '—'}|"
                f"delivery_length={delivery_info.get('length', '—') if delivery_info else '—'}|"
                f"delivery_line={delivery_info.get('line', '—') if delivery_info else '—'}|"
                f"delivery_angle={delivery_info.get('bowling_angle', '—') if delivery_info else '—'}|"
                f"delivery_shot={delivery_info.get('shot_type', '—') if delivery_info else '—'}|"
                f"delivery_direction={delivery_info.get('shot_direction', {}).get('side', '—') if delivery_info else '—'}|"
                f"delivery_elevation={delivery_info.get('shot_elevation', '—') if delivery_info else '—'}|"
                f"delivery_bounce={delivery_info.get('bounce', '—') if delivery_info else '—'}|"
                f"delivery_dets={delivery_info.get('detections', 0) if delivery_info else 0}|"
                f"delivery_method={delivery_info.get('_method', '—') if delivery_info else '—'}|"
                f"delivery_snap_dets={delivery_info.get('_comparison', {}).get('snapshot', {}).get('detections', '—') if delivery_info else '—'}|"
                f"delivery_3layer_dets={delivery_info.get('_comparison', {}).get('three_layer', {}).get('detections', '—') if delivery_info else '—'}|"
                f"delivery_det_rate={'%.2f' % delivery_info['detection_rate'] if delivery_info and 'detection_rate' in delivery_info else '—'}|"
                f"delivery_dir_zone={delivery_info.get('shot_direction', {}).get('zone', '—') if delivery_info else '—'}|"
                f"delivery_dir_conf={delivery_info.get('shot_direction', {}).get('confidence', 0) if delivery_info else 0}|"
                f"delivery_shot_action={delivery_info.get('shot_action', '—') if delivery_info else '—'}|"
                f"delivery_shot_intent={delivery_info.get('shot_intent', '—') if delivery_info else '—'}|"
                f"delivery_swing={delivery_info.get('swing_or_seam', '—') if delivery_info else '—'}|"
                f"delivery_speed_vlm={delivery_info.get('ball_speed_kph_vlm', '—') if delivery_info else '—'}|"
                f"delivery_vlm_conf={delivery_info.get('_vlm_confidence', '—') if delivery_info else '—'}|"
                f"delivery_vlm_ms={delivery_info.get('_vlm_ms', '—') if delivery_info else '—'}|"
                f"speed_kph={speed_kph or '—'}|"
                f"venue={_broadcast_cache.get('venue', '—')}|"
                f"batting_team={batting_team or '—'}|"
                f"match_info={_broadcast_cache.get('match_info', '—')}|"
                f"completed_over={_completed_over if _over_changed else '—'}|"
                f"completed_over_runs={_completed_over_runs if _over_changed else '—'}|"
                f"drs_state={_drs_state}|"
                f"corrections={'; '.join(inv_corrections) if inv_corrections else 'none'}|"
                f"lat_vision={v_ms:.0f}|lat_extract={e_ms:.0f}|"
                f"lat_scorer={s_ms:.0f}|lat_field={ft_ms:.0f}|"
                f"lat_comm={comm_ms:.0f}|"
                f"lat_code={_code_ms:.0f}|"
                f"lat_total={_frame_wall_ms:.0f}|"
                f"comm_bowler={_cur_bowler_name or '—'}|"
                f"comm_wire={_cw.get('text', '—')[:150].replace(chr(10), ' ')}|"
                f"comm_storyteller={_cs.get('text', '—')[:200].replace(chr(10), ' ')}|"
                f"comm_analyst={_ca.get('text', '—')[:200].replace(chr(10), ' ')}|"
                f"comm_colour={_cc.get('text', '—')[:200].replace(chr(10), ' ')}|"
                f"comm_wire_ms={_cw.get('latency_ms', 0)}|"
                f"comm_story_ms={_cs.get('latency_ms', 0)}|"
                f"comm_analyst_ms={_ca.get('latency_ms', 0)}|"
                f"comm_colour_ms={_cc.get('latency_ms', 0)}"
            )
            log.info(_detail_line)

            # ── Trace-and-Detect v1 — write structured trace record ──
            # Additive to DETAIL line; never raises into the pipeline.
            # See files/docs/operations/trace_and_detect_setup.md.
            try:
                _ui_after_snap = _TRACE_MIRROR.snapshot_compact()
                _ui_before_snap = {
                    "scorecard": {
                        "score": _before_score,
                        "striker": _striker,
                        "non_striker": _non,
                        "current_bowler": _before_bowl,
                    },
                    "batting_card_at_crease": [
                        {"name": _before_bat1, "is_striker": True},
                        {"name": _before_bat2, "is_striker": False},
                    ],
                    "this_over": list(_before_this_over)
                                 if isinstance(_before_this_over, (list, tuple))
                                 else [],
                }
                _ui_diff = _trace.compute_ui_diff(
                    _ui_before_snap, _ui_after_snap)
                global _TRACE_LAST_HANDOFF_FRAME, _TRACE_LAST_INNINGS
                _cur_inn = state.get("innings")
                if (_TRACE_LAST_INNINGS is not None
                        and _cur_inn != _TRACE_LAST_INNINGS):
                    _TRACE_LAST_HANDOFF_FRAME = frame_count
                _TRACE_LAST_INNINGS = _cur_inn
                _mode = _trace.derive_pipeline_mode(
                    _trace.ModeContext(
                        cold_start_gate_open=_ws_cold_start_gate_open,
                        current_innings=_cur_inn,
                        last_innings_handoff_frame=_TRACE_LAST_HANDOFF_FRAME,
                    ),
                    frame_count,
                )
                _decisions = _TRACE_RECORDER.drain()
                _ext_full = (extracted or {})
                _scorer_proposed = {
                    "score": _ext_full.get("score"),
                    "wickets": _ext_full.get("wickets"),
                    "overs": _ext_full.get("match_overs"),
                    "batter_updates": _ext_full.get("batters") or [],
                    "bowler": _ext_full.get("bowler") or {},
                }
                _trace_record = {
                    "frame": frame_count,
                    "ts_wall": time.time(),
                    "ts_match": (
                        f"{batting_team or '?'} "
                        f"{state.get('score')}-{state.get('wickets')} "
                        f"({state.get('overs')}) "
                        f"inn={state.get('innings')}"),
                    "session": SESSION_ID,
                    "frame_type": frame_type,
                    "cadence_ms": int(_frame_wall_ms),
                    "capture": {
                        "cap_idx": frame_count,
                        "cap_source": _FRAME_SOURCE_MODE,
                        "force_processed": False,
                    },
                    "pipeline": {
                        "mode": _mode,
                        "innings": _cur_inn,
                        "cold_start_gate":
                            "OPEN" if _ws_cold_start_gate_open else "CLOSED",
                        "ws_clients": len(_ws_clients),
                        "batting_team": batting_team,
                        "striker": _striker,
                        "non_striker": _non,
                        "current_bowler": _bowl_name,
                        "fow_count": _fow_count,
                        "inset_suspected": bool(
                            locals().get("_inset_suspected_frame", False)),
                        "overlay_window_active": bool(
                            locals().get(
                                "_overlay_window_active_frame", False)),
                    },
                    "scout": {
                        "ms": int(v_ms),
                        "tag": frame_type,
                        "raw_text_120": (description[:120].replace(
                            chr(10), " ") if description else None),
                        "action_100": (current_action[:100]
                                       if current_action else None),
                    },
                    "extractor": {
                        "ms": int(e_ms),
                        "score": _ext_full.get("score"),
                        "wickets": _ext_full.get("wickets"),
                        "match_overs": _ext_full.get("match_overs"),
                        "visible_team": _ext_full.get("visible_team"),
                        "target": _ext_full.get("target"),
                        "rr": _ext_full.get("rr"),
                        "batters": _ext_full.get("batters") or [],
                        "bowler": _ext_full.get("bowler") or {},
                    },
                    "scorer": {
                        "ms": int(s_ms),
                        "proposed": _scorer_proposed,
                        "decisions": _decisions,
                        "committed_changes": (changes
                                              if "changes" in dir()
                                              else []),
                    },
                    "ball_event": {
                        "type": (ball_event.get("type")
                                 if ball_event else None),
                        "runs": (ball_event.get("runs")
                                 if ball_event else None),
                        "over": (ball_event.get("over")
                                 if ball_event else None),
                        "extra_type": (ball_event.get("extra_type")
                                       if ball_event else None),
                        "free_hit": bool(
                            ball_event and ball_event.get("free_hit")),
                        "broadcast_extra": _bcast_extra,
                        "dismissal_mode": _last_dismissal_mode,
                        "striker_this_ball": _striker_this_ball,
                    },
                    "ui_before": _ui_before_snap,
                    "ui_after": _ui_after_snap,
                    "ui_diff": _ui_diff,
                    "lat_ms": {
                        "vision": int(v_ms),
                        "extract": int(e_ms),
                        "scorer": int(s_ms),
                        "field": int(ft_ms),
                        "comm": int(comm_ms),
                        "code": int(_code_ms),
                        "total": int(_frame_wall_ms),
                    },
                    "anomalies": [],
                }
                _TRACE_WRITER.write_record(_trace_record)
            except Exception as _trace_exc:  # noqa: BLE001
                # Never let trace emission break the pipeline.
                log.warn(f"[TRACE] write failed F{frame_count}: "
                         f"{_trace_exc}")

            await asyncio.sleep(adaptive.get_sleep_time())

    except KeyboardInterrupt:
        log.info("Interrupted")
    except Exception as e:
        log.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if openscout_task is not None and not openscout_task.done():
            openscout_task.cancel()
            try:
                await openscout_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        if (match_recorder_task is not None
                and not match_recorder_task.done()):
            match_recorder_task.cancel()
            try:
                await match_recorder_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        if ball_analyzer:
            ball_analyzer.stop()
        frames.stop()
        await vision.close()
        await extractor.close()
        await scorer.close()

    elapsed = time.time() - start
    log.info("\n" + "=" * 60)
    log.info(f"TEST COMPLETE — {elapsed:.0f}s")
    log.info(f"  Frames: {frame_count} | Pipeline: {processed} | "
             f"PixDiff: {skipped_pixel} | NoStrip: "
             f"{skipped_no_strip_total} | Ads: {skipped_ad} | "
             f"Context: {skipped_context}")
    log.info(f"  Final: {scoreboard.get_live_state()}")
    log.info("=" * 60)

    # Live-monitoring v1: match-end roll-up emissions.  Innings-2
    # RETRO-SUMMARY (derived as current - innings-1 snapshot), then
    # the single MATCH-SUMMARY.  Wrapped per-block so a partial
    # failure on one tag never blocks the others.
    try:
        from monitoring_emitters import (
            MatchSummaryInputs, RetroCounters,
            emit_match_summary, emit_retro_summary,
            format_open_scout_stats, format_chunker_v3_stats,
            OpenScoutStatsCounters,
        )
        _ba_rec = (ball_analyzer._recorder
                   if (ball_analyzer is not None
                       and getattr(ball_analyzer, "_recorder", None)
                       is not None)
                   else None)
        if _ba_rec is not None:
            _rc_full = _ba_rec._retro_counters
            _snap = _MONITORING_RETRO_INN1_SNAPSHOT
            _rc2 = RetroCounters(
                events_seen=max(
                    0, _rc_full.events_seen - _snap["events_seen"]),
                spans_committed=max(
                    0, _rc_full.spans_committed - _snap["spans_committed"]),
                spans_fallback=max(
                    0, _rc_full.spans_fallback - _snap["spans_fallback"]),
            )
            if 1 in _MONITORING_RETRO_EMITTED_INNINGS:
                emit_retro_summary(2, _rc2, logger=log)
            else:
                emit_retro_summary(1, _rc_full, logger=log)
            # Final partial-window OPEN-SCOUT-STATS / CHUNKER-V3-STATS.
            if open_scout is not None:
                _final_scout = OpenScoutStatsCounters(
                    class_counts=collections.Counter(
                        open_scout.window_class_counts),
                    latencies_ms=list(open_scout.window_latencies_ms),
                    inter_call_gaps_s=list(
                        open_scout.window_inter_call_gaps_s),
                )
                log.info(format_open_scout_stats(_final_scout, window_min=5))
            log.info(format_chunker_v3_stats(
                _ba_rec._v3_stats_counters, window_min=5))
            # MATCH-SUMMARY roll-up.
            _loop_tracker = getattr(open_scout, "_loop_tracker", None) \
                if open_scout is not None else None
            _summary = MatchSummaryInputs(
                duration_min=elapsed / 60.0,
                retro=_rc_full,
                scout_class_totals=collections.Counter(
                    getattr(open_scout, "match_class_totals", {})
                    if open_scout is not None else {}),
                scout_lat_ms_all=list(
                    getattr(open_scout, "match_latencies_ms", [])
                    if open_scout is not None else []),
                loop_gaps_s_all=(
                    list(_loop_tracker.all_gaps_s)
                    if _loop_tracker is not None else []),
                loop_e429_total=(
                    int(getattr(_loop_tracker, "_calls_429", 0))
                    if _loop_tracker is not None else 0),
                v3_resolved=_ba_rec._v3_stats_match.resolved_count,
                v3_none=_ba_rec._v3_stats_match.none_count,
                v3_fallback=_ba_rec._v3_stats_match.fallback_count,
                v3_drove_cut=_ba_rec._v3_stats_match.drove_cut_count,
            )
            emit_match_summary(_summary, logger=log)
    except Exception as _me:  # noqa: BLE001
        log.warning(f"[MATCH-SUMMARY] emit failed: {_me}")

    log.info("\nBATTING CARD:")
    log.info(scoreboard.format_batting_card())
    log.info("\nBOWLING CARD:")
    log.info(scoreboard.format_bowling_card())

    # Commentary-ready stats
    log.info(f"\nEXTRAS: wides={scoreboard.extras['wides']} "
             f"no_balls={scoreboard.extras['no_balls']} "
             f"byes={scoreboard.extras['byes']} "
             f"leg_byes={scoreboard.extras['leg_byes']} "
             f"total={scoreboard.extras['total']}")
    log.info(f"OVERS TRACKED: {len(over_mgr.over_history)} complete")
    for ov, data in sorted(over_mgr.over_history.items()):
        balls = data.get("balls", [])
        bowler = data.get("bowler", "?")
        if balls:
            ov_runs = sum(int(x) for x in balls
                         if isinstance(x, str) and x.isdigit())
            log.info(f"  Over {ov}: {balls} = {ov_runs} runs "
                     f"(by {bowler})")
        else:
            log.info(f"  Over {ov}: by {bowler} — no ball data")
    if over_mgr.this_over:
        cur_runs = sum(int(x) for x in over_mgr.this_over
                      if isinstance(x, str) and x.isdigit())
        log.info(f"  Current over: {over_mgr.this_over} = {cur_runs} runs")
    if scoreboard.bowler_speeds:
        log.info("BOWLING SPEEDS:")
        for bname, speeds in scoreboard.bowler_speeds.items():
            stats = scoreboard.get_bowler_speed_stats(bname)
            if stats:
                log.info(f"  {bname}: avg={stats['avg_speed']}kph "
                         f"max={stats['max_speed']} min={stats['min_speed']} "
                         f"({stats['count']} readings)")

    # Commentary data summary
    log.info(f"\nBALL EVENTS: {len(ball_detector.events)} detected")
    for ev in ball_detector.events:
        action_str = (f" — {ev['action'][:60]}"
                      if ev.get("action") else "")
        log.info(f"  {ev.get('over','?')} {ev['type']}: "
                 f"+{ev.get('runs',0)} (bat={ev.get('striker','?')} "
                 f"bowl={ev.get('bowler','?')}){action_str}")
    log.info(f"PARTNERSHIPS: {len(partnership_tracker.partnerships)} completed")
    for p in partnership_tracker.partnerships:
        log.info(f"  {p['batters']} — {p['runs']} runs "
                 f"off {p['balls']} balls")
    if partnership_tracker.current_pair:
        state_final = scoreboard.get_live_state()
        team_score = scoreboard._inn.get("score") or 0
        team_balls = overs_to_balls(scoreboard._inn.get("overs") or "0")
        curr_p = partnership_tracker.current(team_score, team_balls)
        log.info(f"  Current: {curr_p['batters']} — {curr_p['runs']} runs "
                 f"off {curr_p['balls']} balls (unbroken)")
    situation_final = get_match_situation(scoreboard.get_live_state())
    log.info(f"MATCH SITUATION: {json.dumps(situation_final)}")

    # Field tracking summary
    fs = field_state.get_state()
    keeper_str = "-"
    if fs.get("keeper"):
        keeper_str = fs["keeper"].get("position") or "-"
    log.info(f"\nFIELD STATE: {fs.get('formation') or 'unknown'} | "
             f"slips:{fs.get('slips',0)} close:{fs.get('close_catchers',0)} "
             f"in:{fs.get('inside_circle',0)} out:{fs.get('outside_circle',0)} "
             f"| {fs.get('fielders_detected',0)} fielders "
             f"| conf:{fs.get('confidence',0):.1f} "
             f"| keeper:{keeper_str} "
             f"| validated:{fs.get('validated',False)} "
             f"| freshness:{field_state.get_freshness()}")
    if field_state.changes_log:
        log.info(f"  Field changes detected: {len(field_state.changes_log)}")
    if field_state.over_snapshots:
        log.info(f"  Over snapshots: {len(field_state.over_snapshots)}")
    if field_validator.accuracy_log:
        log.info(f"  Validation avg accuracy: "
                 f"{field_validator.get_average_accuracy():.0%} "
                 f"across {len(field_validator.accuracy_log)} validations")
    if field_merger.last_merged:
        lm = field_merger.last_merged
        log.info(f"  Last merge source: {lm.get('source')} "
                 f"(yolo:{lm.get('yolo_count',0)} "
                 f"vision:{lm.get('vision_count',0)})")


_commentary_engine: InlineCommentary | None = None


async def _commentary_ws_handler(websocket):
    if _commentary_engine:
        _commentary_engine.clients.add(websocket)
        for entry in _commentary_engine.history[-20:]:
            await websocket.send(json.dumps({"type": "commentary", "entry": entry}))
        try:
            async for _ in websocket:
                pass
        finally:
            _commentary_engine.clients.discard(websocket)


async def main():
    global _commentary_engine
    _commentary_engine = InlineCommentary()

    ws_server = await websockets.serve(
        _ws_handler, "0.0.0.0", WS_PORT,
        ping_interval=20, ping_timeout=10,
        open_timeout=15, max_queue=64,
    )
    log.info(f"[WS] Server started on ws://0.0.0.0:{WS_PORT}")

    comm_server = await websockets.serve(
        _commentary_ws_handler, "0.0.0.0", COMMENTARY_PORT,
        ping_interval=20, ping_timeout=10,
        open_timeout=15, max_queue=64,
    )
    log.info(f"[WS] Commentary server on ws://0.0.0.0:{COMMENTARY_PORT}")

    try:
        await run_test()
    finally:
        ws_server.close()
        await ws_server.wait_closed()
        comm_server.close()
        await comm_server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
