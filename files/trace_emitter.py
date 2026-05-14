"""Trace-and-Detect v1 — JSONL trace emission, UI mirror, decision capture.

Per `files/docs/investigations/trace_and_detect_system_design.md` §3 and §6.

Public surface:
- `TraceWriter` — opens `logs/trace/<session>.jsonl`, writes the schema
  header, appends per-frame records.
- `DecisionRecorder` — process-wide accumulator. `begin_frame(n)` opens
  a new bucket; every `record(tag=..., **payload)` appends to the bucket;
  `drain()` returns and resets it.
- `DecisionLogHandler` — `logging.Handler` that auto-promotes any
  ``[TAG] ...`` log line to a structured decision entry on the active
  recorder. Closes Phase C surface area without touching ~30 sites.
- `UIMirror` — server-side replica of `scorecard-ui/app/hooks/
  useMatchSocket.ts:L5-L36` ``deepMerge``. Snapshot before/after every
  WS publish; feed both into the trace.
- `compute_ui_diff(before, after) -> list[dict]` — scalar-path diff
  used for the trace's `ui_diff[]` field.
- `derive_pipeline_mode(...) -> str` — one of
  ``COLD_START | WARM | INNINGS_HANDOFF`` (TEAM_LATCH deferred).
- `TRACE_SCHEMA_VERSION` — bump on any breaking change.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

TRACE_SCHEMA_VERSION = 1

# P3 — replay/recap-inset detector telemetry. Two booleans surface in
# the per-frame trace record under ``pipeline.{inset_suspected,
# overlay_window_active}``. ``inset_suspected`` is True on any frame
# poisoned by Mode-C or by the post-P2 N-frame debounce window;
# ``overlay_window_active`` is True for every frame whose decremented
# window counter is > 0 (i.e. a P2/P3 firing happened within the last
# ``OVERLAY_WINDOW_FRAMES`` frames). Schema unchanged — these are
# additive optional fields under the existing ``pipeline`` object.
P3_TRACE_FIELDS: tuple[str, ...] = ("inset_suspected", "overlay_window_active")

DEFAULT_TRACE_DIR = os.environ.get(
    "TRACE_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs",
                 "trace"),
)

# Tag enum — kept in sync with §3.1 of the design memo. Tags not in this
# set are auto-captured but flagged ``known=False`` so the analyzer can
# surface unexpected emissions for catalog updates.
KNOWN_TAGS: set[str] = {
    "POISON-RECAL", "POISON-RECAL-PRE-EMPTED",
    "GRAPHIC-FILTER",
    "STRIKER-ALIGN-FALLBACK", "BATTER-ALIGN",
    "BOWLER-BATTER-GATE", "BOWLER-LEAD",
    "BOWLER-OVERRIDE", "BOWLER-BOOTSTRAP-REJECT",
    "BOWLING-CARD-CREATED", "BOWLING-CARD-RESUMED",
    "MULTI-BALL-DERIVATION-EXPANDED",
    "WICKET-PENDING-BOWLER-ATTRIBUTION",
    "WICKET-BACKFILLED-TO-BOWLER",
    "WICKET-ATTRIBUTION-ORPHANED",
    "BOWLER-MAIDEN-CREDITED",
    "DERIVATION-STRIP-DIVERGENCE-BOWLER",
    "CONSECUTIVE-OVER-BOWLER-REJECTED",
    "BOWLER-CONSENSUS-INCONSISTENT",
    "BOWLER-CONSENSUS-INCONSISTENT-OVERRIDE",
    "BOWLER-LOCK-RELEASED", "BOWLER-LOCK-ACQUIRED",
    "GUARD-RELEASE",
    "WS-SLOT-INVARIANT", "WS-SCRUB",
    "BATTERS-INVARIANT",
    "STRIP-ROWS-MISALIGNED",
    "STRIP-OVERLAY-DETECTED",
    "OVERLAY-LOCKOUT-BREAKOUT",
    "NEW-BATTER-BALLS-GATE",
    "WICKET-AUTO", "WICKET-TRACK", "WICKET-ATTRIB",
    "EXTRAS", "EXTRAS-INF", "EXTRAS-INF-GATE",
    "EXTRA-INFER-DEFERRED",
    "FIELD-MONITOR",
    "WS-COLD-START-GATE",
    "SM-FEEDER-SYNC",
    "CAM-GRAPHIC-FAST-PATH-REJECT", "CAM-GRAPHIC-FAST-PATH-READ",
    "CAM-GRAPHIC-FAST-PATH-NOOP",
    # GUARD: deprecated 2026-05-03 — bowler stats sanity rejections now
    # surface as ``BOWLER-STATS-SANITY-REJECT`` (P15). Kept registered so
    # legacy logs still classify as ``known=True``.
    "GUARD", "BOARD-INVARIANT", "INVARIANT",
    "SM",
    "SCORER-INVARIANT-FILTER",
    "BOWLER",
    "WICKET",
    "DISMISS",
    "DIRECT", "FLOW", "WARN", "ACTION", "S", "E", "V",
    "INIT", "INNINGS", "INNINGS-CHANGE", "INNINGS-TRANSITION-TELEMETRY",
    "STRIKER-READ-SM-CANONICAL",
    # P12 — innings-2 cold-start hardening (2026-05-03).  Five tags
    # surface in the per-frame trace under ``scorer.decisions[].tag``;
    # the analyzer rolls them up via the existing decision histogram.
    "INN2-TRANSITION-REJECT",
    "INN2-TRANSITION-NULL-TEAM",
    "INN2-COLD-START-LOCKOUT",
    "INN2-COLD-START-CONSENSUS",
    "INN2-TRANSITION-PHANTOM-STORM",
    # P10 (2026-05-03) — strip-OCR gap padding after timeout.
    "TIMEOUT-GAP-INFER",
    # P14 (2026-05-03) — batter slot identity consensus reset on
    # legitimate slot change.
    "BATTER-CONSENSUS-RESET",
    # P15 (2026-05-03) — bowler spell vs team-overs sanity rejection.
    # Replaces the legacy ``[GUARD]`` tag for this specific guard;
    # GUARD itself remains in the set for backward compatibility but
    # is marked deprecated above.
    "BOWLER-STATS-SANITY-REJECT",
    # P16 (2026-05-03) — DIRECT score/overs proposal rejected on RR
    # plausibility.
    "SCORE-OVERS-RR-REJECT",
    # P20 (2026-05-03) — bowler stale latency telemetry. HARDCAP fires
    # when the 20-frame timeout clears the bowler; STUCK is the
    # advisory shoulder (>8 frames stuck, not yet hardcap).
    "BOWLER-LATENCY-HARDCAP",
    "LATENCY-STUCK",
    # H.2 (2026-05-04) — bowler wickets-regression guard. Fires when a
    # proposed wickets value is lower than the card's current value
    # (cross-match overlay backstop).
    "BOWLER-STATS-REGRESSION",
    # Batch M (2026-05-04) — per-field variant of the regression guard.
    # When proposed wickets < current, keep wickets pinned but accept
    # the other fields (overs, runs_conceded) instead of rejecting the
    # whole frame. Distinct tag so monitoring can separate the new
    # behavior from the legacy whole-frame rejection.
    "BOWLER-STATS-REGRESSION-FIELD",
    # Batch V (2026-05-05) — per-field BOWLER-STALE rejection in
    # ScoreManager._accept_update. Sub-condition A (all four figures
    # match historical, not in must-change grace) drops all four
    # fields. Sub-condition B (overs regress vs historical) drops only
    # bowler_overs and keeps runs/wickets. The outer name-mismatch
    # always rejects bowler_name with reason ``name-mismatch-sm``.
    "BOWLER-STALE",
    # Batch J (2026-05-04) — incoming-batter promoted to status=batting
    # immediately on wicket-event rollover, eliminating the upstream
    # poison cascade caused by stale active-batting set vs. strip showing
    # the new pair (see score_manager_overs_commit_stall.md).
    "INCOMING-BATTER-PROMOTED",
    # Batch U (2026-05-04) — per-row off-roster batter rejection.
    # Fires when a strip ``batters[]`` row name doesn't resolve into
    # the batting team's XI (Scout hallucination — MI vs LSG F205
    # [Inglis, KL Rahul]).  Non-poisoning: only the bad rows are
    # dropped; score/overs/bowler commit normally.
    "OFF-ROSTER-BATTER-REJECT",
    # Batch L (2026-05-04) — squad-order fallback removed from incoming-
    # batter promotion. When strip read has no candidate at the wicket
    # frame, the slot is deferred (active set briefly size-1) until the
    # next strip read names the real incoming batter. Prevents phantom-
    # dismissal cascades when squad list order differs from batting
    # order (F285 KKR vs PBKS — Markram guessed via squad order, real
    # incoming was Pooran).
    "INCOMING-BATTER-PENDING",
    # OpenScout shadow runner (2026-05-03). ``SHADOW`` is the umbrella
    # tag for any ``[SHADOW] ...`` log line emitted by
    # ``files/openscout_shadow/``. ``SHADOW-STATS`` is the periodic
    # JSON-payload heartbeat written from ``test_pipeline.py`` every
    # 1800 frames (~60 s at 30 fps).
    "SHADOW",
    "SHADOW-STATS",
    # OpenScout Stage 2 span routing (sub_clip_delivery_isolation_v4
    # §8, 2026-05-03).  Sub-tags under the existing OPEN-SCOUT umbrella;
    # registered here so they classify as ``known=True`` in the
    # auto-decision stream.  Two log shapes:
    #   ``[OPEN-SCOUT-SPAN] used: event_ts=X span=[A,B]``
    #   ``[OPEN-SCOUT-SPAN] no_match: event_ts=X — falling back to
    #     legacy window``
    "OPEN-SCOUT",
    "OPEN-SCOUT-SPAN",
    # Chunker v3 (2026-05-05) — emitted once per delivery-window
    # resolution by ``DeliveryWindowRecorder._emit_chunker_v3_trace``.
    # Payload format: ``legacy_start=A legacy_end=B v3_start=C
    # v3_end=D drove_cut={legacy|v3}``.  Auto-promoted to
    # ``decisions[]`` by the existing log-handler bridge.
    "CHUNKER-V3-WINDOW",
    "CHUNKER-V3",
    # CHUNKER-V3-FALLBACK (2026-05-05) — fires once per score event
    # where v3 returned None AND legacy `_find_span` also returned
    # None.  Payload: ``event_ts=X window=(A, B) lookback_s=L
    # forward_s=F``.  Auto-promoted to P22 in the analyzer.
    "CHUNKER-V3-FALLBACK",
    # Batch BB (2026-05-05) — DWR `_find_span` admits a between_play
    # bowlers_end tag as an anchor when an action-phase tag lies within
    # MAX_CONTIGUOUS_GAP_S either side. Restores retrospective_span
    # firing rate without reverting RC-7's isolated-tag rejection.
    "PHASE-BRIDGE-ACCEPT",
    # Live-monitoring v1 (2026-05-05) — periodic + match-end aggregate
    # tags emitted by ``files/monitoring_emitters.py``.  See
    # ``files/docs/operations/live_monitoring.md``.
    "RETRO-SUMMARY",
    "OPEN-SCOUT-STATS",
    "OPEN-SCOUT-LOOP-STATS",
    "CHUNKER-V3-STATS",
    "MATCH-SUMMARY",
    # Startup config dump (2026-05-05) — single emission at SESSION_ID
    # init capturing all live-monitoring-relevant feature flags.
    "SESSION-CONFIG",
    # Tripwire alarms (2026-05-05) — derived from CHUNKER-V3-STATS,
    # OPEN-SCOUT-LOOP-STATS, and per-event v3 outcomes in DWR.  Surface
    # in analyze_trace.py post-match report.
    "ALARM-V3-FALLBACK-HIGH",
    "ALARM-OPEN-SCOUT-TPM-HIGH",
    "ALARM-V3-CONSECUTIVE-NONE",
    # Clip-write verification (2026-05-05).  Fires once per delivery
    # cut from ``DeliveryWindowRecorder._classify_frames_for_event``
    # to confirm the ``delivery_window.mp4`` landed on disk.
    # CLIP-WRITE-FAIL covers missing file, sub-1 KB output, and any
    # OSError raised while stat()'ing the path.
    "CLIP-WRITE-OK",
    "CLIP-WRITE-FAIL",
    # Continuous chunker (2026-05-06) — score-event-decoupled detector.
    # State-machine transitions emit ``CONTINUOUS-CHUNKER-STATE``.
    # ``DELIVERY-DETECTED`` fires once per closed cluster.
    # ``AUTO-CLIP-WRITE-OK`` / ``AUTO-CLIP-WRITE-FAIL`` are auto-clip
    # write outcomes from ``files/eyes/auto_delivery_recorder.py``.
    "CONTINUOUS-CHUNKER-STATE",
    "CONTINUOUS-CHUNKER-REJECTED",
    "DELIVERY-DETECTED",
    "AUTO-CLIP-WRITE-OK",
    "AUTO-CLIP-WRITE-FAIL",
    # DC-vs-CSK reliability batch (2026-05-05). See
    # ``files/tests/test_pipeline_reliability_batch.py``.
    # STRIP-ROW-NAME-MISMATCH and STRIP-ROW-DUPLICATE fire from
    # ScoreManager._update_batters when the strip-row → SM-slot bind
    # cannot be made or both rows name the same batter. STRIP-STALE-
    # DISMISSED fires from filter_strip_stale_dismissed when any row
    # names a status=out batter (rejects the entire strip read).
    "STRIP-ROW-NAME-MISMATCH",
    "STRIP-ROW-DUPLICATE",
    "STRIP-STALE-DISMISSED",
    "STRIP-WRONG-TEAM",
    "INNINGS-2-BOOTSTRAP",
    # Hot-resume on pipeline restart (2026-05-11). HOT_RESUME records
    # the cache identity + restored state; HOT-RESUME-VALIDATE fires
    # on the first non-null broadcast read post-restore (OK / REJECT
    # outcomes); CACHE classifies legacy identity-reject / cold-start-
    # path log lines from the startup block.
    "HOT_RESUME",
    "HOT-RESUME-VALIDATE",
    "CACHE",
    "SCOUT-RETRY-QUEUED",
    "SCOUT-RETRY-SUCCESS",
    "SCOUT-RETRY-EXHAUSTED",
    "SCOUT-RETRY-BUFFER-OVERFLOW",
    "SCOUT-RETRY-IN-CALL-QUEUED",
    "SCOUT-RETRY-IN-CALL-SUCCESS",
    "SCOUT-RETRY-IN-CALL-EXHAUSTED",
}

# Regex matches the leading ``[TAG]`` token in any log message. Captures
# the tag name and the trailing payload (may be empty).
_TAG_RE = re.compile(r"\[([A-Z][A-Z0-9_-]*)\]\s*(.*)", re.DOTALL)


# ── Decision recorder ──────────────────────────────────────────────


class DecisionRecorder:
    """Frame-scoped accumulator for guard/decision tags.

    Single instance per pipeline process. ``begin_frame(n)`` resets the
    bucket; every emission site (or the auto log-handler) calls
    ``record(tag=..., **payload)``; ``drain()`` returns and clears the
    bucket for inclusion in the trace record.

    Thread-safe via lock — vision/extract/scorer all run inside the
    same async loop today, so the lock is mostly defensive.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: int | None = None
        self._bucket: list[dict[str, Any]] = []

    def begin_frame(self, frame: int) -> None:
        with self._lock:
            self._frame = frame
            self._bucket = []

    def record(self, *, tag: str, **payload: Any) -> None:
        if not tag:
            return
        entry = {"tag": tag, **payload}
        with self._lock:
            self._bucket.append(entry)

    def drain(self) -> list[dict[str, Any]]:
        with self._lock:
            out = self._bucket
            self._bucket = []
            return out

    @property
    def current_frame(self) -> int | None:
        return self._frame


class DecisionLogHandler(logging.Handler):
    """Promote ``log.info("[TAG] ...")`` lines to decision entries.

    Hooked into the root cricket logger (and any child loggers that
    propagate). Each emit:
      1. Extracts the leading ``[TAG]`` token.
      2. Records ``{tag, raw_message[:200], log_level, logger,
         known: bool}`` on the active recorder.

    Cheap (one regex per log line; no allocation when no match).
    Per-site instrumentation can still call ``recorder.record(...)``
    directly for richer typed payloads — those entries layer on top of
    the auto-captured ones.
    """

    def __init__(self, recorder: DecisionRecorder, *,
                 known_tags: Iterable[str] | None = None) -> None:
        super().__init__(level=logging.DEBUG)
        self._recorder = recorder
        self._known = set(known_tags) if known_tags is not None else KNOWN_TAGS

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            msg = record.getMessage()
        except Exception:
            return
        m = _TAG_RE.search(msg)
        if not m:
            return
        tag = m.group(1)
        try:
            self._recorder.record(
                tag=tag,
                raw_message=msg[:200],
                log_level=record.levelname,
                logger=record.name,
                known=tag in self._known,
                _auto=True,
            )
        except Exception:
            pass


# ── Server-side UI mirror ──────────────────────────────────────────
#
# Replicates `scorecard-ui/app/hooks/useMatchSocket.ts` deepMerge:
#   - `innings_history` arrays are replaced wholesale.
#   - Other arrays: replaced if non-empty, else keep previous if it is
#     non-empty, else take incoming.
#   - Nested dicts: deep-merge.
#   - Scalars: take incoming if not in (None, "", undefined); else keep
#     previous.
# Reading the TS hook is the source of truth — keep parity tested.


def deep_merge_ui(prev: dict[str, Any] | None,
                  incoming: dict[str, Any] | None) -> dict[str, Any]:
    """Server-side replica of the client deepMerge."""
    if prev is None:
        return dict(incoming or {})
    if incoming is None:
        return dict(prev)
    out: dict[str, Any] = dict(prev)
    for k, nv in incoming.items():
        pv = prev.get(k)
        if k == "innings_history" and isinstance(nv, list):
            out[k] = nv
            continue
        if isinstance(nv, list):
            if len(nv) > 0:
                out[k] = nv
            elif isinstance(pv, list) and len(pv) > 0:
                out[k] = pv
            else:
                out[k] = nv
            continue
        if (isinstance(nv, dict) and isinstance(pv, dict)):
            out[k] = deep_merge_ui(pv, nv)
            continue
        # Scalars: keep previous on null/empty incoming.
        if nv is None or nv == "":
            # Already in `out` from the spread; don't overwrite.
            continue
        out[k] = nv
    return out


class UIMirror:
    """Single-client mirror — what the UI shows after deep-merging
    every payload that has passed the cold-start gate.

    Use as:
        mirror = UIMirror()
        before = mirror.snapshot_compact()
        if gate_open:
            mirror.apply(payload)
        after = mirror.snapshot_compact()
    """

    def __init__(self) -> None:
        self._state: dict[str, Any] = {}

    def apply(self, payload: dict[str, Any]) -> None:
        self._state = deep_merge_ui(self._state, payload)

    def reset(self) -> None:
        self._state = {}

    def snapshot_full(self) -> dict[str, Any]:
        return json.loads(json.dumps(self._state, default=str))

    def snapshot_compact(self) -> dict[str, Any]:
        """The trace-record-friendly subset.

        Mirrors the §3.1 schema: scorecard, batting at-crease (with
        is_striker), bowling current, this_over, extras_total,
        partnership current, fow_count, innings.
        """
        s = self._state
        scorecard = s.get("scorecard") or {}
        batting = s.get("batting_card") or []
        bowling = s.get("bowling_card") or []
        extras = s.get("extras") or {}
        partnerships = (s.get("partnerships") or {}).get("current")
        fow = s.get("fall_of_wickets") or []
        match = s.get("match") or {}

        at_crease = [
            {
                "name": b.get("name"),
                "runs": b.get("runs"),
                "balls": b.get("balls"),
                "is_striker": bool(b.get("is_striker")),
                "status": b.get("status"),
            }
            for b in batting
            if isinstance(b, dict) and b.get("status") in ("batting", "not_out")
        ]
        current_bowler = next(
            (
                {
                    "name": b.get("name"),
                    "wickets": b.get("wickets"),
                    "runs": b.get("runs"),
                    "overs": b.get("overs"),
                }
                for b in bowling
                if isinstance(b, dict) and b.get("is_current")
            ),
            None,
        )
        return {
            "scorecard": {
                "score": scorecard.get("score"),
                "wickets": scorecard.get("wickets"),
                "overs": scorecard.get("overs"),
                "run_rate": scorecard.get("run_rate"),
                "striker": scorecard.get("striker"),
                "non_striker": scorecard.get("non_striker"),
                "current_bowler": scorecard.get("current_bowler"),
            },
            "batting_card_at_crease": at_crease,
            "bowling_current": current_bowler,
            "this_over": list(s.get("this_over") or []),
            "extras_total": extras.get("total"),
            "partnership_current": partnerships,
            "fow_count": len(fow),
            "innings": match.get("innings"),
        }


# ── ui_diff — scalar path delta ────────────────────────────────────


def _flatten_scalars(obj: Any, prefix: str = "",
                     out: dict[str, Any] | None = None) -> dict[str, Any]:
    if out is None:
        out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            _flatten_scalars(v, f"{prefix}.{k}" if prefix else k, out)
    elif isinstance(obj, list):
        # Lists compared by full equality at one path; cricket UI lists
        # tend to be small ordered structs (this_over, batting card)
        # where item-by-item flattening produces noise.
        out[prefix] = list(obj)
    else:
        out[prefix] = obj
    return out


def compute_ui_diff(before: dict[str, Any],
                    after: dict[str, Any]) -> list[dict[str, Any]]:
    fb = _flatten_scalars(before)
    fa = _flatten_scalars(after)
    diffs: list[dict[str, Any]] = []
    keys = set(fb) | set(fa)
    for k in sorted(keys):
        bv = fb.get(k, "<absent>")
        av = fa.get(k, "<absent>")
        if bv == av:
            continue
        diffs.append({"path": k, "from": bv, "to": av})
    return diffs


# ── Pipeline mode ──────────────────────────────────────────────────


@dataclass
class ModeContext:
    """Inputs needed to derive ``pipeline.mode`` per record."""

    cold_start_gate_open: bool
    current_innings: int | None
    last_innings_handoff_frame: int | None
    handoff_window_frames: int = 60


def derive_pipeline_mode(ctx: ModeContext, current_frame: int) -> str:
    if not ctx.cold_start_gate_open:
        return "COLD_START"
    if (
        ctx.last_innings_handoff_frame is not None
        and current_frame - ctx.last_innings_handoff_frame
        <= ctx.handoff_window_frames
    ):
        return "INNINGS_HANDOFF"
    return "WARM"


# ── Trace writer ───────────────────────────────────────────────────


@dataclass
class TraceWriter:
    """Append-only JSONL writer for one pipeline session.

    Header line is emitted on first ``write_record`` call. File is
    fsync'd opportunistically — append cost on local disk for ~5 KB
    JSON lines is dominated by the JSON serialize, not the IO.

    Caller owns rotation: a sibling cron / analyzer step gzips the file
    after the session ends. No in-process rotation.
    """

    session_id: str
    trace_dir: str = DEFAULT_TRACE_DIR
    schema_version: int = TRACE_SCHEMA_VERSION

    _fp: Any = field(default=None, init=False, repr=False)
    _path: str = field(default="", init=False, repr=False)
    _header_written: bool = field(default=False, init=False, repr=False)
    _records: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        os.makedirs(self.trace_dir, exist_ok=True)
        self._path = os.path.join(self.trace_dir,
                                  f"{self.session_id}.jsonl")

    @property
    def path(self) -> str:
        return self._path

    @property
    def records_written(self) -> int:
        return self._records

    def _open(self) -> None:
        if self._fp is None:
            self._fp = open(self._path, "a", buffering=1, encoding="utf-8")

    def _ensure_header(self) -> None:
        if self._header_written:
            return
        self._open()
        header = {
            "_schema_version": self.schema_version,
            "session": self.session_id,
            "started_ts_wall": time.time(),
        }
        self._fp.write(json.dumps(header, default=str) + "\n")
        self._header_written = True

    def write_record(self, record: dict[str, Any]) -> None:
        self._ensure_header()
        try:
            line = json.dumps(record, default=str)
        except (TypeError, ValueError) as e:
            line = json.dumps({
                "frame": record.get("frame"),
                "_serialize_error": str(e),
            })
        assert self._fp is not None
        self._fp.write(line + "\n")
        self._records += 1

    def close(self) -> None:
        if self._fp is not None:
            try:
                self._fp.flush()
            finally:
                self._fp.close()
                self._fp = None


# ── Reader (used by the analyzer) ──────────────────────────────────


def read_trace(path: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read a trace JSONL (or .jsonl.gz). Returns ``(header, records)``.

    Header is the first line (``_schema_version`` etc.); records are
    everything after. Raises ``ValueError`` on schema-version mismatch.
    """
    opener = gzip.open if path.endswith(".gz") else open
    header: dict[str, Any] | None = None
    records: list[dict[str, Any]] = []
    with opener(path, "rt", encoding="utf-8") as fp:
        for i, line in enumerate(fp):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if i == 0 and "_schema_version" in obj:
                header = obj
                continue
            records.append(obj)
    if header is None:
        raise ValueError(
            f"trace file {path!r} missing schema header on first line")
    if header.get("_schema_version") != TRACE_SCHEMA_VERSION:
        raise ValueError(
            f"trace schema mismatch: file={header.get('_schema_version')} "
            f"reader={TRACE_SCHEMA_VERSION}")
    return header, records


# ── Singleton accessors (convenience for test_pipeline.py wiring) ──

_RECORDER: DecisionRecorder | None = None
_WRITER: TraceWriter | None = None
_MIRROR: UIMirror | None = None


def get_recorder() -> DecisionRecorder:
    global _RECORDER
    if _RECORDER is None:
        _RECORDER = DecisionRecorder()
    return _RECORDER


def install_log_handler(logger: logging.Logger | None = None) -> DecisionLogHandler:
    """Attach the auto-decision handler to a logger (root by default)."""
    handler = DecisionLogHandler(get_recorder())
    target = logger if logger is not None else logging.getLogger()
    target.addHandler(handler)
    return handler


def get_writer(session_id: str,
               trace_dir: str = DEFAULT_TRACE_DIR) -> TraceWriter:
    global _WRITER
    if _WRITER is None:
        _WRITER = TraceWriter(session_id=session_id, trace_dir=trace_dir)
    return _WRITER


def get_mirror() -> UIMirror:
    global _MIRROR
    if _MIRROR is None:
        _MIRROR = UIMirror()
    return _MIRROR


def reset_singletons() -> None:
    """Test helper — clear module-level state between runs."""
    global _RECORDER, _WRITER, _MIRROR
    if _WRITER is not None:
        _WRITER.close()
    _RECORDER = None
    _WRITER = None
    _MIRROR = None
