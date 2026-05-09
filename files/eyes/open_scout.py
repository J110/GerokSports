"""OpenScout — per-frame open-prose Scout classifier (parallel to Vision).

Implements §3 of ``files/docs/investigations/parallel_scout_delivery_window_design.md``:
a second Groq Llama-Scout-17B instance running fire-and-forget at a
decoupled cadence in the per-frame loop.  Output is the natural-prose
description from ``OPEN_PROMPT`` (frozen from
``files/scripts/scout_validation_research/run_scout_open.py``) routed
through the rule-v2 classifier in ``open_scout_classify.classify_full``
to one of {action, replay, ad, umpire, other}.

Why a separate ``AsyncGroq`` client (rather than reusing ``Vision``):
  * Decouples primary-Scout latency budget (~800 ms median) from the
    open-prose call so neither blocks the other.
  * Per-key Groq rate-limits are by token throughput, not connection
    count — running two parallel HTTP/2 streams is well within budget
    at the proposed 0.5–1 fps cadence.
  * Failure isolation: a 429 / 5xx on OpenScout drops the observation
    silently; the primary scoreboard pipeline is untouched.

This module is dormant unless ``USE_OPEN_SCOUT=1`` (default 1) and
``OpenScout`` is actually constructed by ``BallAnalyzer``; the
downstream window-placement only consults its output when
``USE_OPEN_SCOUT_SPANS=1`` (default 0) — see config.py.
"""
from __future__ import annotations

import asyncio
import base64
import os
import time
from typing import NamedTuple

import cv2
import numpy as np
from groq import AsyncGroq

from eyes.config import (
    GROQ_API_KEY,
    GROQ_PRIMARY_MODEL,
    OPEN_SCOUT_ACTIVE_INTERVAL_S,
    OPEN_SCOUT_AMBIGUOUS_INTERVAL_S,
    OPEN_SCOUT_MAX_TOKENS,
    OPEN_SCOUT_TEMPERATURE,
    OPEN_SCOUT_TIMEOUT_S,
)
from eyes.cricket_logger import CricketLogger
from eyes.open_scout_classify import classify_full

log = CricketLogger("OPEN-SCOUT")

# Frozen prompt — IDENTICAL to run_scout_open.py:32-41 so the rule-v2
# classifier behaves the same in production as it did in validation.
# Any prompt drift invalidates the §11.4 P=0.77 / R=0.99 baseline.
OPEN_PROMPT = (
    "This is a single frame from a professional cricket match "
    "broadcast on television.\n\n"
    "Describe what you see in this frame in detail. Specifically "
    "address:\n"
    "- What is the camera showing? (e.g., wide field view, closeup "
    "of a player, crowd shot, score graphic)\n"
    "- What are the people in the frame doing? (e.g., bowler "
    "running, batter standing, players talking, fielders walking)\n"
    "- Are there any graphical overlays? (e.g., score graphics, "
    "REPLAY tags, sponsor logos, player stats)\n"
    "- What does the action level look like? (e.g., active play "
    "happening, between deliveries, post-action moment, replay or "
    "slow-motion)\n\n"
    "Provide a 2-4 sentence description in plain language. Don't "
    "classify the frame; just describe it.\n"
)

# V2 prompt — Path A iteration (regression set: 105 manually labeled
# delivery clips, see ``files/docs/investigations/scout_path_a_iteration
# .md``).  Front-loads broadcast-mode probing so replay / slo-mo /
# telestrator frames produce keyword-matchable prose.  v1 is preserved
# verbatim above for byte-identical rollback (memo §11.4 baseline).
#
# Activate by setting OPEN_SCOUT_PROMPT_VERSION=v2 in the environment.
OPEN_PROMPT_V2 = (
    "This is a single frame from a professional cricket match "
    "broadcast on television.\n\n"
    "Begin your response with EXACTLY ONE of these tags on its "
    "own first line, with no extra words on that line:\n"
    "  [BROADCAST: REPLAY]  — a \"REPLAY\" text label, replay "
    "watermark, or \"INSTANT REPLAY\" graphic is visible.\n"
    "  [BROADCAST: SLO-MO]  — a \"SLOW MOTION\", \"SLO-MO\", or "
    "\"SUPER SLO-MO\" tag is visible, OR motion is clearly slowed, "
    "frozen, or stretched (slo-mo capture without a tag).\n"
    "  [BROADCAST: TELESTRATOR]  — telestrator drawings, freeze-"
    "frame analysis arrows or circles, or analyst diagrams are "
    "drawn over players.\n"
    "  [BROADCAST: SPLIT-SCREEN]  — the frame shows a split-screen "
    "replay layout (two angles side by side).\n"
    "  [BROADCAST: LIVE]  — none of the above markers are present.\n\n"
    "After the tag line, write 2-3 sentences describing:\n"
    "  - camera framing and what people are doing (wide field "
    "view, closeup, mid-stride, mid-swing, walking between balls, "
    "crowd shot, studio shot, etc.).\n"
    "  - persistent on-screen graphics — score bar, sponsor logos, "
    "view counts. These are NOT replay indicators.\n\n"
    "Do not classify the frame beyond the tag; just describe.\n"
)


def _active_prompt() -> str:
    """Return the prompt to use this call.

    Resolved per-call (not at import) so a test harness can flip
    ``OPEN_SCOUT_PROMPT_VERSION`` between sessions without
    re-importing.  Default is v1 — production behavior unchanged.
    """
    return (OPEN_PROMPT_V2
            if os.environ.get("OPEN_SCOUT_PROMPT_VERSION", "v1") == "v2"
            else OPEN_PROMPT)


VALID_CLASSES = ("action", "replay", "ad", "umpire", "other")

# v2 prompt structured tag (OPEN_PROMPT_V2 emits one of these on the
# first line of the response).  Parsed out to a simple uppercase token
# so downstream consumers (ChunkerV3) don't have to know about the
# bracketed wire format.
_V2_BROADCAST_TAGS = (
    ("[BROADCAST: REPLAY]", "REPLAY"),
    ("[BROADCAST: SLO-MO]", "SLO-MO"),
    ("[BROADCAST: TELESTRATOR]", "TELESTRATOR"),
    ("[BROADCAST: SPLIT-SCREEN]", "SPLIT-SCREEN"),
    ("[BROADCAST: LIVE]", "LIVE"),
)


def extract_v2_broadcast_tag(desc: str | None) -> str:
    """Return the v2 broadcast tag token (REPLAY/SLO-MO/TELESTRATOR/
    SPLIT-SCREEN/LIVE) if the prompt's first-line tag is present in
    ``desc``; otherwise return "".

    Empty string means "tag not detected" — typically a v1-prompt
    response, a malformed first line, or an LLM that didn't follow
    the format.  Callers treat "" as "no signal" rather than "LIVE".
    """
    if not desc:
        return ""
    # The tag is required to be on the first line per the prompt, but
    # we tolerate leading whitespace / quoting from the LLM.
    head = desc.lstrip()[:64].upper()
    for needle, token in _V2_BROADCAST_TAGS:
        if needle in head:
            return token
    return ""

# Camera-view + adaptive-state buckets used by the rate gate.  These
# names mirror the values that ``Vision._normalise_camera_view`` /
# ``AdaptiveSleep`` already emit so the gate can stay declarative.
_ACTIVE_VIEWS = frozenset({"bowlers_end", "side_on"})
_AMBIGUOUS_VIEWS = frozenset({None, "closeup", "graphic", "other"})
_PAUSED_VIEWS = frozenset({"ad"})
_PAUSED_PHASES = frozenset({"advertisement"})


class OpenScoutResult(NamedTuple):
    """Per-call output handed back to ``BallAnalyzer``."""

    timestamp: float
    frame_class: str          # one of VALID_CLASSES
    raw_description: str      # verbatim Scout text (may be empty on err)
    tokens_total: int = 0     # resp.usage.total_tokens (0 if unavailable)
    v2_broadcast_tag: str = ""  # REPLAY/SLO-MO/TELESTRATOR/SPLIT-SCREEN/LIVE or ""


class OpenScout:
    """Per-frame open-prose Scout — async, fire-and-forget."""

    def __init__(self,
                 *,
                 api_key: str | None = None,
                 model: str | None = None,
                 max_tokens: int = OPEN_SCOUT_MAX_TOKENS,
                 temperature: float = OPEN_SCOUT_TEMPERATURE,
                 timeout_s: float = OPEN_SCOUT_TIMEOUT_S,
                 sidecar: "OpenScoutSidecar | None" = None):
        self._client = AsyncGroq(
            api_key=api_key or GROQ_API_KEY,
            timeout=timeout_s + 2.0,
        )
        self._model = model or GROQ_PRIMARY_MODEL
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._timeout_s = timeout_s
        self._sidecar = sidecar

        self.calls_attempted = 0
        self.calls_succeeded = 0
        self.calls_failed = 0
        self.last_error: str | None = None
        self.class_counts: dict[str, int] = {c: 0 for c in VALID_CLASSES}
        # Live-monitoring v1 (2026-05-05).  Window-local counters that
        # ``test_pipeline.py`` snapshots+resets every 5 minutes for the
        # ``[OPEN-SCOUT-STATS]`` tag.  Cumulative counters above are
        # untouched.
        from collections import Counter, deque
        self.window_class_counts: Counter = Counter()
        self.window_latencies_ms: deque = deque(maxlen=2000)
        self._last_call_wall: float | None = None
        self.window_inter_call_gaps_s: deque = deque(maxlen=2000)
        self.match_class_totals: Counter = Counter()
        self.match_latencies_ms: list[float] = []

    def attach_sidecar(self,
                       sidecar: "OpenScoutSidecar | None") -> None:
        """Wire (or detach) a per-frame JSONL sidecar.  Idempotent."""
        self._sidecar = sidecar

    @staticmethod
    def _encode(frame: np.ndarray) -> str | None:
        try:
            ok, buf = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ok:
                return None
            return base64.b64encode(buf).decode()
        except Exception as e:  # noqa: BLE001
            log.warn(f"[OPEN-SCOUT] encode failed: {e}")
            return None

    async def classify(self,
                       frame: np.ndarray,
                       timestamp: float | None = None,
                       *,
                       frame_idx: int | None = None,
                       ) -> OpenScoutResult | None:
        """Run one open-prose Scout call.  Returns None on failure.

        Failures are intentionally swallowed (logged + counted) so the
        per-frame loop's ``asyncio.create_task`` never raises.  The
        SpanAggregator tolerates dropped observations via
        ``SOFT_GAP_TOLERANCE_S``.

        ``frame_idx`` is best-effort metadata for the sidecar JSONL —
        omitted if the caller doesn't have one.  Sidecar failures are
        swallowed inside the sidecar so they cannot affect this path.
        """
        call_t0 = time.time()
        ts = timestamp if timestamp is not None else call_t0
        b64 = self._encode(frame)
        if b64 is None:
            self._record_sidecar(
                ts=ts, frame_idx=frame_idx, frame_class=None,
                raw_text="", latency_ms=int(
                    (time.time() - call_t0) * 1000),
                error="encode_failed")
            return None

        self.calls_attempted += 1
        text = ""
        tokens_total = 0
        try:
            resp = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self._model,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image_url",
                             "image_url": {
                                 "url": (
                                     "data:image/jpeg;base64,"
                                     f"{b64}")}},
                            {"type": "text",
                             "text": _active_prompt()},
                        ],
                    }],
                ),
                timeout=self._timeout_s,
            )
            if resp.choices and resp.choices[0].message:
                text = (resp.choices[0].message.content or "").strip()
            usage = getattr(resp, "usage", None)
            if usage is not None:
                tokens_total = int(getattr(usage, "total_tokens", 0) or 0)
        except asyncio.TimeoutError:
            self.calls_failed += 1
            self.last_error = "timeout"
            log.warn(f"[OPEN-SCOUT] timeout after {self._timeout_s:.1f}s")
            self._record_sidecar(
                ts=ts, frame_idx=frame_idx, frame_class=None,
                raw_text="", latency_ms=int(
                    (time.time() - call_t0) * 1000),
                error="timeout")
            return None
        except Exception as e:  # noqa: BLE001
            self.calls_failed += 1
            self.last_error = str(e)[:200]
            log.warn(f"[OPEN-SCOUT] error: {e}")
            self._record_sidecar(
                ts=ts, frame_idx=frame_idx, frame_class=None,
                raw_text="", latency_ms=int(
                    (time.time() - call_t0) * 1000),
                error=str(e)[:200])
            return None

        cls = classify_full(text)
        if cls not in VALID_CLASSES:
            cls = "other"
        v2_tag = extract_v2_broadcast_tag(text)
        self.calls_succeeded += 1
        self.class_counts[cls] = self.class_counts.get(cls, 0) + 1
        latency_ms = int((time.time() - call_t0) * 1000)
        self.window_class_counts[cls] += 1
        self.match_class_totals[cls] += 1
        self.window_latencies_ms.append(latency_ms)
        self.match_latencies_ms.append(latency_ms)
        if self._last_call_wall is not None:
            self.window_inter_call_gaps_s.append(
                call_t0 - self._last_call_wall)
        self._last_call_wall = call_t0
        self._record_sidecar(
            ts=ts, frame_idx=frame_idx, frame_class=cls,
            raw_text=text,
            latency_ms=latency_ms,
            error=None,
            tokens_total=tokens_total)
        return OpenScoutResult(
            timestamp=ts, frame_class=cls, raw_description=text,
            tokens_total=tokens_total,
            v2_broadcast_tag=v2_tag)

    def _record_sidecar(self,
                        *,
                        ts: float,
                        frame_idx: int | None,
                        frame_class: str | None,
                        raw_text: str,
                        latency_ms: int,
                        error: str | None,
                        tokens_total: int = 0) -> None:
        sc = self._sidecar
        if sc is None:
            return
        try:
            sc.record_classification(
                ts=ts,
                frame_idx=frame_idx,
                frame_class=frame_class,
                raw_text=raw_text,
                latency_ms=latency_ms,
                error=error,
                rate_gate_reason="passed",
                tokens_total=tokens_total,
            )
        except Exception as e:  # noqa: BLE001
            log.warn(f"[OPEN-SCOUT] sidecar record failed: {e}")

    def stats(self) -> dict:
        return {
            "attempted": self.calls_attempted,
            "succeeded": self.calls_succeeded,
            "failed": self.calls_failed,
            "last_error": self.last_error,
            "class_counts": dict(self.class_counts),
        }

    async def aclose(self) -> None:
        try:
            await self._client.close()
        except Exception:  # noqa: BLE001
            pass


class OpenScoutRateGate:
    """Throttle decisions for OpenScout (§3.2 of design memo).

    Cadence map:
      - active play (bowlers_end / side_on) → ``active_interval_s`` (default 1 fps)
      - ambiguous (closeup, graphic, other, unknown) → ``ambiguous_interval_s``
        (default 0.5 fps)
      - ads / paused capture → no calls

    The gate is intentionally stateless about which call actually
    happened — ``allow(ts, ...)`` returns True/False and updates
    ``_last_allow_ts`` so a drop downstream still counts as "we tried".
    Caller (``BallAnalyzer.maybe_run_open_scout``) is responsible for
    spawning the task.
    """

    def __init__(self,
                 *,
                 active_interval_s: float = OPEN_SCOUT_ACTIVE_INTERVAL_S,
                 ambiguous_interval_s: float = OPEN_SCOUT_AMBIGUOUS_INTERVAL_S):
        self._active_s = max(0.05, active_interval_s)
        self._ambiguous_s = max(0.05, ambiguous_interval_s)
        self._last_allow_ts: float = 0.0
        self.allowed = 0
        self.skipped_throttled = 0
        self.skipped_paused = 0
        # Reason set by the most recent ``allow()`` call.  When
        # ``allow`` returns True this is "passed"; when False it is
        # one of the skip reasons below.  Lets the OpenScout sidecar
        # log skip records without the gate having to know about it.
        self.last_decision_reason: str = "passed"

    def _interval_for(self, camera_view: str | None,
                      frame_phase: str | None) -> float | None:
        if frame_phase in _PAUSED_PHASES:
            return None
        if camera_view in _PAUSED_VIEWS:
            return None
        if camera_view in _ACTIVE_VIEWS:
            return self._active_s
        return self._ambiguous_s

    def allow(self,
              ts: float,
              *,
              camera_view: str | None = None,
              frame_phase: str | None = None,
              capture_alive: bool = True) -> bool:
        if not capture_alive:
            self.skipped_paused += 1
            self.last_decision_reason = "skipped:capture_paused"
            return False
        interval = self._interval_for(camera_view, frame_phase)
        if interval is None:
            self.skipped_paused += 1
            self.last_decision_reason = (
                f"skipped:paused_view"
                f"(cam={camera_view},phase={frame_phase})")
            return False
        if (ts - self._last_allow_ts) < interval:
            self.skipped_throttled += 1
            self.last_decision_reason = (
                f"skipped:throttled(interval_s={interval:.2f})")
            return False
        self._last_allow_ts = ts
        self.allowed += 1
        self.last_decision_reason = "passed"
        return True

    def stats(self) -> dict:
        return {
            "allowed": self.allowed,
            "skipped_throttled": self.skipped_throttled,
            "skipped_paused": self.skipped_paused,
        }
