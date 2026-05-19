"""Secondary text-LLM resolver for SM-orchestrator multi-ball gaps.

See files/docs/investigations/sm_as_orchestrator_design.md §4.

Two feature flags gate behavior:

  SM_ORCHESTRATOR_RESOLVER=1
      Activates the resolver interface (mock + telemetry only).
      Default off.

  SM_ORCHESTRATOR_RESOLVER_LLM=1
      Activates real Groq llama-3.1-8b-instant calls on cache miss.
      Default off. Requires GROQ_API_KEY in env. Model is configurable
      via GAP_RESOLVER_MODEL (default llama-3.1-8b-instant; swap to
      llama-3.3-70b-versatile if 8B eval accuracy is insufficient).

Resolution hierarchy inside resolve():
  1. Δballs<2 precondition → UNRESOLVED source=precondition
  2. Replay-cache hit (TEST_SECONDARY_LLM_REPLAY) → source=replay
  3. SM_ORCHESTRATOR_RESOLVER_LLM=1 → Groq call, source=llm
  4. Otherwise → UNRESOLVED source=mock

Validation gates on LLM responses (all must pass):
  - len(events) == delta_observed.balls
  - sum(events.runs_off_bat) == delta_score
  - every event.confidence >= 0.7

Failures emit GAP-RESOLVER-LLM-INCONSISTENT or
GAP-RESOLVER-LLM-LOW-CONFIDENCE trace tags and fall back to
UNRESOLVED. API errors emit GAP-RESOLVER-LLM-ERROR.
"""
from __future__ import annotations

import json
import os
import pathlib
import time
from dataclasses import dataclass, field
from typing import Optional

try:
    import trace_emitter as _trace
except ImportError:
    _trace = None

try:
    from eyes.cricket_logger import CricketLogger
    log = CricketLogger("SECONDARY_RESOLVER")
except ImportError:
    import logging
    log = logging.getLogger("SECONDARY_RESOLVER")


@dataclass
class ExpectedBallContext:
    over: int
    ball: int
    legal_ball_count: int


@dataclass
class ScoutContext:
    visible_text: Optional[str] = None
    info_panel: Optional[str] = None
    strip: Optional[str] = None
    frame_type: Optional[str] = None
    camera_view: Optional[str] = None
    frame_phase: Optional[str] = None


@dataclass
class MatchState:
    innings: Optional[int] = None
    score_before: Optional[int] = None
    wickets_before: Optional[int] = None
    overs_before: Optional[float] = None
    score_after: Optional[int] = None
    wickets_after: Optional[int] = None
    overs_after: Optional[float] = None
    striker: Optional[str] = None
    non_striker: Optional[str] = None
    bowler: Optional[str] = None


@dataclass
class DeltaObserved:
    runs: int = 0
    wickets: int = 0
    balls: int = 0


@dataclass
class SecondaryResolveRequest:
    frame_id: int
    expected_ball: ExpectedBallContext
    scout_context: ScoutContext
    match_state: MatchState
    delta_observed: DeltaObserved
    delta_score: int = 0
    prior_scout_texts: list[str] = field(default_factory=list)


@dataclass
class WicketInfo:
    dismissed: Optional[str] = None
    type: Optional[str] = None
    fielder: Optional[str] = None


@dataclass
class ExtrasInfo:
    type: Optional[str] = None
    runs: int = 0


@dataclass
class ResolvedEvent:
    event_type: str
    runs_off_bat: int = 0
    extras: ExtrasInfo = field(default_factory=ExtrasInfo)
    wicket: Optional[WicketInfo] = None
    confidence: float = 0.0


@dataclass
class SecondaryResolveResponse:
    events: list[ResolvedEvent] = field(default_factory=list)
    unresolved: bool = True
    reasoning: str = ""
    source: str = "mock"

    @property
    def event_type(self) -> str:
        if not self.events:
            return "UNRESOLVED"
        if len(self.events) == 1:
            return self.events[0].event_type
        return "MULTI"

    @property
    def confidence(self) -> float:
        if not self.events:
            return 0.0
        return min(e.confidence for e in self.events)


def _unresolved(reason: str, source: str) -> SecondaryResolveResponse:
    return SecondaryResolveResponse(
        events=[], unresolved=True, reasoning=reason, source=source)


def _emit_trace(tag: str, **payload) -> None:
    if _trace is not None:
        try:
            _trace.get_recorder().record(tag=tag, **payload)
        except Exception:
            pass


DEFAULT_MODEL = "llama-3.1-8b-instant"
LLM_TIMEOUT_S = 10.0
LLM_MAX_TOKENS = 600
LLM_CONFIDENCE_FLOOR = 0.7


class SecondaryResolver:
    def __init__(self, replay_path: Optional[str] = None):
        self._cache: dict[tuple[int, int], dict] = {}
        if replay_path is None:
            replay_path = os.environ.get("TEST_SECONDARY_LLM_REPLAY")
        if replay_path:
            self._load_replay(pathlib.Path(replay_path))
        self._groq_client = None

    def _load_replay(self, path: pathlib.Path) -> None:
        if not path.exists():
            return
        with path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    fid = int(rec["frame_id"])
                    lbc = int(rec["legal_ball_count"])
                    self._cache[(fid, lbc)] = rec.get("response", {})
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue

    def resolve(
        self, req: SecondaryResolveRequest
    ) -> SecondaryResolveResponse:
        if req.delta_observed.balls < 2:
            return _unresolved(
                "precondition: Δballs<2 is not a gap event",
                source="precondition")
        key = (req.frame_id, req.expected_ball.legal_ball_count)
        canned = self._cache.get(key)
        if canned is not None:
            return self._from_canned(canned)
        if os.environ.get("SM_ORCHESTRATOR_RESOLVER_LLM", "0") == "1":
            return self._call_llm(req)
        return _unresolved(
            "no replay entry; LLM flag off — stage 2b mock",
            source="mock")

    @staticmethod
    def _from_canned(canned: dict) -> SecondaryResolveResponse:
        raw_events = canned.get("events")
        if raw_events is None and canned.get("event_type"):
            raw_events = [{
                "event_type": canned["event_type"],
                "runs_off_bat": canned.get("runs_off_bat", 0),
                "extras": canned.get("extras"),
                "wicket": canned.get("wicket"),
                "confidence": canned.get("confidence", 0.0),
            }]
        events = [_event_from_dict(e) for e in (raw_events or [])]
        return SecondaryResolveResponse(
            events=events,
            unresolved=bool(canned.get("unresolved", not events)),
            reasoning=canned.get("reasoning", ""),
            source="replay")

    def _call_llm(
        self, req: SecondaryResolveRequest
    ) -> SecondaryResolveResponse:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            _emit_trace(
                "GAP-RESOLVER-LLM-ERROR",
                reason="no_groq_api_key")
            log.info("[GAP-RESOLVER-LLM-ERROR] no GROQ_API_KEY")
            return _unresolved(
                "no GROQ_API_KEY in env", source="llm-error")
        model = os.environ.get("GAP_RESOLVER_MODEL", DEFAULT_MODEL)
        try:
            from groq import Groq
        except ImportError:
            _emit_trace(
                "GAP-RESOLVER-LLM-ERROR",
                reason="groq_sdk_missing")
            log.info(
                "[GAP-RESOLVER-LLM-ERROR] groq SDK not installed")
            return _unresolved(
                "groq SDK not available", source="llm-error")

        if self._groq_client is None:
            self._groq_client = Groq(api_key=api_key)
        prompt = _build_prompt(req)

        t0 = time.monotonic()
        try:
            chat = self._groq_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=LLM_MAX_TOKENS,
                timeout=LLM_TIMEOUT_S,
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - t0) * 1000)
            _emit_trace(
                "GAP-RESOLVER-LLM-ERROR",
                model=model, latency_ms=latency_ms,
                error_type=type(e).__name__, error=str(e)[:200])
            log.info(
                f"[GAP-RESOLVER-LLM-ERROR] model={model} "
                f"{type(e).__name__}: {str(e)[:200]}")
            return _unresolved(
                f"llm api error: {type(e).__name__}",
                source="llm-error")
        latency_ms = int((time.monotonic() - t0) * 1000)

        usage = getattr(chat, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        completion_tokens = (
            getattr(usage, "completion_tokens", 0) if usage else 0)
        _emit_trace(
            "GAP-RESOLVER-LLM-CALL",
            model=model, frame_id=req.frame_id,
            delta_balls=req.delta_observed.balls,
            delta_score=req.delta_score,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            latency_ms=latency_ms)
        log.info(
            f"[GAP-RESOLVER-LLM-CALL] model={model} "
            f"frame={req.frame_id} Δballs={req.delta_observed.balls} "
            f"Δscore={req.delta_score} "
            f"in_tokens={prompt_tokens} out_tokens={completion_tokens} "
            f"latency_ms={latency_ms}")

        content = chat.choices[0].message.content
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError) as e:
            _emit_trace(
                "GAP-RESOLVER-LLM-INCONSISTENT",
                model=model, reason="json_parse_failed",
                error=str(e)[:200], content_preview=str(content)[:300])
            log.info(
                f"[GAP-RESOLVER-LLM-INCONSISTENT] model={model} "
                f"json_parse_failed: {e}")
            return _unresolved(
                "llm json parse failed", source="llm-inconsistent")

        events_raw = parsed.get("events") or []
        expected_n = req.delta_observed.balls
        if len(events_raw) != expected_n:
            _emit_trace(
                "GAP-RESOLVER-LLM-INCONSISTENT",
                model=model, reason="event_count_mismatch",
                expected=expected_n, got=len(events_raw))
            log.info(
                f"[GAP-RESOLVER-LLM-INCONSISTENT] model={model} "
                f"event_count {len(events_raw)} != Δballs {expected_n}")
            return _unresolved(
                "len(events) != Δballs", source="llm-inconsistent")

        try:
            total_runs = sum(
                int(e.get("runs_off_bat", 0)) for e in events_raw)
        except (TypeError, ValueError):
            total_runs = -1
        if total_runs != req.delta_score:
            _emit_trace(
                "GAP-RESOLVER-LLM-INCONSISTENT",
                model=model, reason="runs_sum_mismatch",
                expected=req.delta_score, got=total_runs)
            log.info(
                f"[GAP-RESOLVER-LLM-INCONSISTENT] model={model} "
                f"runs_sum {total_runs} != Δscore {req.delta_score}")
            return _unresolved(
                "sum(runs_off_bat) != Δscore",
                source="llm-inconsistent")

        try:
            min_conf = min(
                float(e.get("confidence", 0.0)) for e in events_raw)
        except (TypeError, ValueError):
            min_conf = 0.0
        if min_conf < LLM_CONFIDENCE_FLOOR:
            _emit_trace(
                "GAP-RESOLVER-LLM-LOW-CONFIDENCE",
                model=model, min_confidence=min_conf,
                floor=LLM_CONFIDENCE_FLOOR)
            log.info(
                f"[GAP-RESOLVER-LLM-LOW-CONFIDENCE] model={model} "
                f"min_conf={min_conf:.2f} floor={LLM_CONFIDENCE_FLOOR}")
            return _unresolved(
                "confidence floor not met",
                source="llm-low-confidence")

        events = [_event_from_dict(e) for e in events_raw]
        return SecondaryResolveResponse(
            events=events,
            unresolved=bool(parsed.get("unresolved", False)),
            reasoning=str(parsed.get("reasoning", "")),
            source="llm")


def _event_from_dict(d: dict) -> ResolvedEvent:
    extras = d.get("extras") or {}
    wkt = d.get("wicket")
    return ResolvedEvent(
        event_type=str(d.get("event_type", "UNRESOLVED")),
        runs_off_bat=int(d.get("runs_off_bat", 0)),
        extras=ExtrasInfo(
            type=extras.get("type"),
            runs=int(extras.get("runs", 0)),
        ),
        wicket=(WicketInfo(
            dismissed=wkt.get("dismissed") or wkt.get("dismissed_name"),
            type=wkt.get("type"),
            fielder=wkt.get("fielder"),
        ) if wkt else None),
        confidence=float(d.get("confidence", 0.0)),
    )


def _build_prompt(req: SecondaryResolveRequest) -> str:
    ms = req.match_state
    prior = "\n---\n".join(
        t for t in (req.prior_scout_texts or []) if t)
    prior_block = prior if prior else "(no prior frames available)"
    gap_block = _scout_block(req.scout_context)
    expected_n = req.delta_observed.balls
    return f"""You are resolving a multi-ball gap in a cricket scoreboard pipeline. Between two consecutive Scout reads, the scoreboard advanced by {expected_n} legal balls and {req.delta_score} runs. Identify the ball-by-ball events.

PRIOR SCOUT READS (most recent last):
{prior_block}

SCOUT TEXT AT GAP FRAME:
{gap_block}

CURRENT MATCH STATE:
- Innings: {ms.innings}
- Striker: {ms.striker}
- Non-striker: {ms.non_striker}
- Bowler: {ms.bowler}
- Overs before gap: {ms.overs_before}  Overs after: {ms.overs_after}
- Score before gap: {ms.score_before}  Score after: {ms.score_after}
- Wickets after: {ms.wickets_after}

OUTPUT — strict JSON, no other text:
{{
  "events": [
    {{
      "event_type": "FOUR"|"SIX"|"ZERO"|"ONE"|"TWO"|"THREE"|"FIVE"|"WIDE"|"NO_BALL"|"BYE"|"LEG_BYE"|"WICKET",
      "runs_off_bat": <int 0..6>,
      "wicket": {{"dismissed_name": <str>, "type": "bowled"|"caught"|"lbw"|"runout"|"stumped"}} | null,
      "confidence": <float 0..1>
    }}
  ],
  "unresolved": <bool>,
  "reasoning": <short str>
}}

HARD CONSTRAINTS:
- events list length MUST equal {expected_n}
- sum of runs_off_bat across events MUST equal {req.delta_score}
- set unresolved=true if you cannot meet both constraints with per-event confidence >= 0.7
- Output ONLY the JSON object."""


def _scout_block(ctx: ScoutContext) -> str:
    parts = []
    if ctx.strip:
        parts.append(f"STRIP: {ctx.strip}")
    if ctx.visible_text:
        parts.append(f"VISIBLE_TEXT: {ctx.visible_text}")
    if ctx.info_panel:
        parts.append(f"INFO_PANEL: {ctx.info_panel}")
    if ctx.frame_type:
        parts.append(f"frame_type={ctx.frame_type}")
    if not parts:
        return "(no scout text captured for gap frame)"
    return "\n".join(parts)


_singleton: Optional[SecondaryResolver] = None


def get_resolver() -> SecondaryResolver:
    global _singleton
    if _singleton is None:
        _singleton = SecondaryResolver()
    return _singleton


def reset_resolver() -> None:
    global _singleton
    _singleton = None
