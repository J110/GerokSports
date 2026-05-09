"""Live-monitoring v1 (2026-05-05) — aggregate trace tag emitters.

Five log tags surface here, all auto-promoted to ``decisions[]`` by
the existing ``DecisionLogHandler`` bridge in ``trace_emitter``:

  * ``[RETRO-SUMMARY]`` — per-innings + match-end retrospective span
    hit-rate counter.
  * ``[OPEN-SCOUT-STATS]`` — 5-min rolling OpenScout class
    distribution + latency snapshot.
  * ``[OPEN-SCOUT-LOOP-STATS]`` — 30-s decoupled-loop cadence /
    util / 429 / derate / slot-miss snapshot. Skipped entirely
    when ``OPENSCOUT_DECOUPLED=0``.
  * ``[CHUNKER-V3-STATS]`` — 5-min rolling v3 hit/miss/fallback
    snapshot + mean window duration + mean v3↔legacy diff.
  * ``[MATCH-SUMMARY]`` — single match-end roll-up across all of
    the above.

Counters are deliberately log-only: no metrics endpoint, no
behavior change. ``analyze_trace.py`` consumes the emitted tags
post-match.
"""
from __future__ import annotations

import logging
import os
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Optional

log = logging.getLogger("monitoring_emitters")


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    if pct <= 0:
        return s[0]
    if pct >= 100:
        return s[-1]
    k = (len(s) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] + (s[hi] - s[lo]) * frac


def _median(values: list[float]) -> float:
    return _percentile(values, 50)


def _mean(values: list[float]) -> float:
    return (sum(values) / len(values)) if values else 0.0


# ── 1. Retro-span hit-rate ─────────────────────────────────────────


@dataclass
class RetroCounters:
    """Per-innings retrospective-span counters.

    ``note_event`` and ``note_commit`` / ``note_fallback`` are called
    from ``DeliveryWindowRecorder.classify_for_score_event``.
    Snapshots are emitted on innings end and on match end.
    """

    events_seen: int = 0
    spans_committed: int = 0
    spans_fallback: int = 0

    def note_event(self) -> None:
        self.events_seen += 1

    def note_commit(self) -> None:
        self.spans_committed += 1

    def note_fallback(self) -> None:
        self.spans_fallback += 1

    def hit_rate_pct(self) -> float:
        if self.events_seen <= 0:
            return 0.0
        return 100.0 * (self.spans_committed / self.events_seen)


def format_retro_summary(innings: int, c: RetroCounters) -> str:
    return (
        f"[RETRO-SUMMARY] innings={innings} "
        f"events_seen={c.events_seen} "
        f"spans_committed={c.spans_committed} "
        f"spans_fallback={c.spans_fallback} "
        f"hit_rate={c.hit_rate_pct():.1f}%"
    )


def emit_retro_summary(innings: int, c: RetroCounters,
                       logger: logging.Logger | None = None) -> str:
    msg = format_retro_summary(innings, c)
    (logger or log).info(msg)
    return msg


# ── 2. OpenScout class distribution snapshot ───────────────────────


_OPEN_SCOUT_BUCKETS: tuple[str, ...] = (
    "action", "replay", "umpire", "ad", "other")


@dataclass
class OpenScoutStatsCounters:
    class_counts: Counter = field(default_factory=Counter)
    latencies_ms: list[float] = field(default_factory=list)
    inter_call_gaps_s: list[float] = field(default_factory=list)

    def note_call(self, *, frame_class: str, latency_ms: float,
                  gap_s: float | None = None) -> None:
        bucket = frame_class if frame_class in _OPEN_SCOUT_BUCKETS \
            else "other"
        self.class_counts[bucket] += 1
        self.latencies_ms.append(float(latency_ms))
        if gap_s is not None:
            self.inter_call_gaps_s.append(float(gap_s))

    def reset(self) -> None:
        self.class_counts = Counter()
        self.latencies_ms = []
        self.inter_call_gaps_s = []


def format_open_scout_stats(c: OpenScoutStatsCounters,
                            window_min: int = 5) -> str:
    cc = c.class_counts
    total = sum(cc.values())
    return (
        f"[OPEN-SCOUT-STATS] window_min={window_min} "
        f"action={cc.get('action', 0)} "
        f"replay={cc.get('replay', 0)} "
        f"umpire={cc.get('umpire', 0)} "
        f"ad={cc.get('ad', 0)} "
        f"other={cc.get('other', 0)} "
        f"total={total} "
        f"lat_p50_ms={_percentile(c.latencies_ms, 50):.0f} "
        f"lat_p90_ms={_percentile(c.latencies_ms, 90):.0f} "
        f"cadence_median_s={_median(c.inter_call_gaps_s):.2f}"
    )


def emit_open_scout_stats(c: OpenScoutStatsCounters,
                          window_min: int = 5,
                          logger: logging.Logger | None = None) -> str:
    msg = format_open_scout_stats(c, window_min=window_min)
    (logger or log).info(msg)
    c.reset()
    return msg


# ── 3. OpenScout-loop cadence / util / 429 / slot-miss ─────────────


@dataclass
class OpenScoutLoopStatsCounters:
    """Decoupled-loop telemetry, reset every emission window.

    Distinct from the in-loop ``_CadenceTracker`` because that one is
    a sliding window for the in-loop log line; this one resets each
    snapshot so analyzers see crisp non-overlapping windows.
    """

    gaps_s: list[float] = field(default_factory=list)
    tokens: list[int] = field(default_factory=list)
    e429_count: int = 0
    frame_slot_miss: int = 0

    def note_call(self, *, gap_s: float | None, tokens: int) -> None:
        if gap_s is not None:
            self.gaps_s.append(float(gap_s))
        self.tokens.append(int(tokens))

    def note_429(self) -> None:
        self.e429_count += 1

    def note_slot_miss(self) -> None:
        self.frame_slot_miss += 1

    def reset(self) -> None:
        self.gaps_s = []
        self.tokens = []
        self.e429_count = 0
        self.frame_slot_miss = 0


def is_decoupled_enabled() -> bool:
    """OPENSCOUT_DECOUPLED defaults to 1 — only ``0`` disables."""
    return os.environ.get("OPENSCOUT_DECOUPLED", "1") != "0"


def format_open_scout_loop_stats(
        c: OpenScoutLoopStatsCounters,
        *,
        window_s: int = 30,
        target_s: float,
        util_tpm_pct: float,
        derate_active: bool) -> str:
    return (
        f"[OPEN-SCOUT-LOOP-STATS] window_s={window_s} "
        f"calls={len(c.tokens)} "
        f"median_gap_s={_median(c.gaps_s):.2f} "
        f"p90_gap_s={_percentile(c.gaps_s, 90):.2f} "
        f"target_s={target_s:.2f} "
        f"util_tpm_pct={util_tpm_pct:.1f} "
        f"mean_tokens={int(_mean([float(t) for t in c.tokens]))} "
        f"e429_count={c.e429_count} "
        f"derate_active={1 if derate_active else 0} "
        f"frame_slot_miss={c.frame_slot_miss}"
    )


def emit_open_scout_loop_stats(
        c: OpenScoutLoopStatsCounters,
        *,
        window_s: int = 30,
        target_s: float,
        util_tpm_pct: float,
        derate_active: bool,
        logger: logging.Logger | None = None) -> Optional[str]:
    if not is_decoupled_enabled():
        return None
    msg = format_open_scout_loop_stats(
        c,
        window_s=window_s,
        target_s=target_s,
        util_tpm_pct=util_tpm_pct,
        derate_active=derate_active,
    )
    (logger or log).info(msg)
    c.reset()
    return msg


# ── 4. V3 chunker stats ────────────────────────────────────────────


@dataclass
class ChunkerV3StatsCounters:
    resolved_count: int = 0
    none_count: int = 0
    fallback_count: int = 0
    drove_cut_count: int = 0
    durations_s: list[float] = field(default_factory=list)
    legacy_diff_s: list[float] = field(default_factory=list)

    def note_outcome(
            self,
            *,
            v3_bounds: tuple[float, float] | None,
            legacy_bounds: tuple[float, float] | None,
            fallback_used: bool,
            drove_cut: bool) -> None:
        if v3_bounds is None:
            self.none_count += 1
        else:
            self.resolved_count += 1
            self.durations_s.append(
                float(v3_bounds[1] - v3_bounds[0]))
            if legacy_bounds is not None:
                diff = (abs(v3_bounds[1] - legacy_bounds[1])
                        + abs(v3_bounds[0] - legacy_bounds[0]))
                self.legacy_diff_s.append(float(diff))
        if fallback_used:
            self.fallback_count += 1
        if drove_cut:
            self.drove_cut_count += 1

    def reset(self) -> None:
        self.resolved_count = 0
        self.none_count = 0
        self.fallback_count = 0
        self.drove_cut_count = 0
        self.durations_s = []
        self.legacy_diff_s = []


def _drove_cut_pct(c: ChunkerV3StatsCounters) -> float:
    total = c.resolved_count + c.none_count
    if total <= 0:
        return 0.0
    return 100.0 * (c.drove_cut_count / total)


def format_chunker_v3_stats(c: ChunkerV3StatsCounters,
                            window_min: int = 5) -> str:
    return (
        f"[CHUNKER-V3-STATS] window_min={window_min} "
        f"resolved={c.resolved_count} "
        f"none={c.none_count} "
        f"fallback={c.fallback_count} "
        f"mean_dur_s={_mean(c.durations_s):.2f} "
        f"mean_diff_s={_mean(c.legacy_diff_s):.2f} "
        f"drove_cut_pct={_drove_cut_pct(c):.1f}"
    )


def emit_chunker_v3_stats(c: ChunkerV3StatsCounters,
                          window_min: int = 5,
                          logger: logging.Logger | None = None) -> str:
    msg = format_chunker_v3_stats(c, window_min=window_min)
    (logger or log).info(msg)
    c.reset()
    return msg


# ── 5. Match-end roll-up ───────────────────────────────────────────


@dataclass
class MatchSummaryInputs:
    duration_min: float
    retro: RetroCounters
    scout_class_totals: Counter
    scout_lat_ms_all: list[float]
    loop_gaps_s_all: list[float]
    loop_e429_total: int
    v3_resolved: int
    v3_none: int
    v3_fallback: int
    v3_drove_cut: int


def _pct(num: int, denom: int) -> float:
    if denom <= 0:
        return 0.0
    return 100.0 * (num / denom)


def format_match_summary(s: MatchSummaryInputs) -> str:
    cc = s.scout_class_totals
    total = sum(cc.values())
    v3_total = s.v3_resolved + s.v3_none
    return (
        f"[MATCH-SUMMARY] duration_min={s.duration_min:.1f} "
        f"events_seen={s.retro.events_seen} "
        f"spans_committed={s.retro.spans_committed} "
        f"hit_rate={s.retro.hit_rate_pct():.1f}% "
        f"scout_calls={total} "
        f"scout_action_pct={_pct(cc.get('action', 0), total):.1f} "
        f"scout_replay_pct={_pct(cc.get('replay', 0), total):.1f} "
        f"scout_other_pct={_pct(cc.get('other', 0), total):.1f} "
        f"scout_lat_p50_ms={_percentile(s.scout_lat_ms_all, 50):.0f} "
        f"loop_median_gap_s={_median(s.loop_gaps_s_all):.2f} "
        f"loop_e429_total={s.loop_e429_total} "
        f"v3_resolved={s.v3_resolved} "
        f"v3_none={s.v3_none} "
        f"v3_fallback={s.v3_fallback} "
        f"v3_drove_cut_pct={_pct(s.v3_drove_cut, v3_total):.1f}"
    )


def emit_match_summary(s: MatchSummaryInputs,
                       logger: logging.Logger | None = None) -> str:
    msg = format_match_summary(s)
    (logger or log).info(msg)
    return msg


@dataclass
class SessionConfigInputs:
    session_id: str
    use_v3_chunker: bool
    use_v3_chunker_spans: bool
    v3_fallback_enabled: bool
    v3_fallback_lookback_s: float
    v3_fallback_forward_s: float
    openscout_decoupled: bool
    openscout_target_s: float
    openscout_tpm_budget: int
    use_open_scout: bool
    use_open_scout_spans: bool


def format_session_config(s: SessionConfigInputs) -> str:
    return (
        f"[SESSION-CONFIG] session_id={s.session_id} "
        f"use_v3_chunker={int(s.use_v3_chunker)} "
        f"use_v3_chunker_spans={int(s.use_v3_chunker_spans)} "
        f"v3_fallback_enabled={int(s.v3_fallback_enabled)} "
        f"v3_fallback_lookback_s={s.v3_fallback_lookback_s:.1f} "
        f"v3_fallback_forward_s={s.v3_fallback_forward_s:.1f} "
        f"openscout_decoupled={int(s.openscout_decoupled)} "
        f"openscout_target_s={s.openscout_target_s:.2f} "
        f"openscout_tpm_budget={s.openscout_tpm_budget} "
        f"use_open_scout={int(s.use_open_scout)} "
        f"use_open_scout_spans={int(s.use_open_scout_spans)}"
    )


# ── Tripwire alarms ────────────────────────────────────────────────


def check_v3_fallback_alarm(c: ChunkerV3StatsCounters,
                            *, window_min: int = 5,
                            threshold: float = 0.30) -> Optional[str]:
    """Returns the ALARM-V3-FALLBACK-HIGH log line if the v3 fallback
    rate exceeded ``threshold`` over the snapshot window, else None."""
    total = c.resolved_count + c.none_count
    if total <= 0:
        return None
    pct = c.fallback_count / max(total, 1)
    if pct <= threshold:
        return None
    return (
        f"[ALARM-V3-FALLBACK-HIGH] window_min={window_min} "
        f"fallback_count={c.fallback_count} "
        f"total_events={total} "
        f"pct={100.0 * c.fallback_count / total:.1f}% "
        f"— v3 misfiring at scale, consider rollback via "
        f"USE_V3_CHUNKER_SPANS=0"
    )


def check_tpm_alarm(*, util_tpm_pct: float, median_gap_s: float,
                    derate_active: bool, window_s: int = 30,
                    threshold_pct: float = 80.0) -> Optional[str]:
    """Returns the ALARM-OPEN-SCOUT-TPM-HIGH log line when util_tpm_pct
    exceeds ``threshold_pct``, else None."""
    if util_tpm_pct <= threshold_pct:
        return None
    return (
        f"[ALARM-OPEN-SCOUT-TPM-HIGH] window_s={window_s} "
        f"util_tpm_pct={util_tpm_pct:.1f} "
        f"median_gap_s={median_gap_s:.2f} "
        f"derate_active={1 if derate_active else 0} "
        f"— token budget pressure; auto-derate engaged or imminent"
    )


def check_consecutive_none_alarm(consecutive_none: int,
                                 last_event_ts: float,
                                 *, step: int = 5) -> Optional[str]:
    """Returns the ALARM-V3-CONSECUTIVE-NONE log line when the streak
    reaches a multiple of ``step`` (>=step), else None."""
    if consecutive_none < step or consecutive_none % step != 0:
        return None
    return (
        f"[ALARM-V3-CONSECUTIVE-NONE] consecutive_none="
        f"{consecutive_none} "
        f"last_event_ts={last_event_ts:.2f} "
        f"— v3 returning None on extended streak; possible "
        f"upstream Scout failure"
    )


# ── Clip-write verification ────────────────────────────────────────


CLIP_WRITE_MIN_BYTES = 1024  # ffmpeg can emit empty containers; <1KB
                             # almost always means no frames landed.


def format_clip_write_ok(*, delivery_id: object, size_bytes: int,
                         duration_s: float, source: str,
                         window_start: float,
                         window_end: float) -> str:
    return (
        f"[CLIP-WRITE-OK] delivery_id={delivery_id} "
        f"bytes={size_bytes} duration_s={duration_s:.2f} "
        f"source={source} "
        f"span=({window_start:.2f},{window_end:.2f})"
    )


def format_clip_write_fail(*, delivery_id: object, reason: str,
                           path: str, source: str,
                           window_start: float,
                           window_end: float) -> str:
    return (
        f"[CLIP-WRITE-FAIL] delivery_id={delivery_id} "
        f"reason={reason} path={path} source={source} "
        f"span=({window_start:.2f},{window_end:.2f})"
    )


def verify_clip_write(*, mp4_path: "os.PathLike | str",
                      delivery_id: object,
                      window_start: float,
                      window_end: float,
                      source: str,
                      logger: logging.Logger | None = None,
                      min_bytes: int = CLIP_WRITE_MIN_BYTES) -> str:
    """Stat ``mp4_path``; emit ``[CLIP-WRITE-OK]`` if present and at
    least ``min_bytes``, else ``[CLIP-WRITE-FAIL]``.  ``OSError`` from
    stat is caught and reported as ``reason=os_error``.  Returns the
    log line emitted."""
    from pathlib import Path
    p = Path(mp4_path)
    lg = logger or log
    try:
        if p.exists():
            size_bytes = p.stat().st_size
            if size_bytes >= min_bytes:
                msg = format_clip_write_ok(
                    delivery_id=delivery_id,
                    size_bytes=size_bytes,
                    duration_s=max(0.0, window_end - window_start),
                    source=source,
                    window_start=window_start,
                    window_end=window_end,
                )
                lg.info(msg)
                return msg
            reason = f"too_small_{size_bytes}_bytes"
        else:
            reason = "missing"
        msg = format_clip_write_fail(
            delivery_id=delivery_id,
            reason=reason,
            path=str(p),
            source=source,
            window_start=window_start,
            window_end=window_end,
        )
        lg.warning(msg)
        return msg
    except OSError as e:
        msg = (
            f"[CLIP-WRITE-FAIL] delivery_id={delivery_id} "
            f"reason=os_error err={e!r} path={p!s}"
        )
        lg.warning(msg)
        return msg


__all__ = [
    "RetroCounters",
    "OpenScoutStatsCounters",
    "OpenScoutLoopStatsCounters",
    "ChunkerV3StatsCounters",
    "MatchSummaryInputs",
    "SessionConfigInputs",
    "format_retro_summary",
    "format_open_scout_stats",
    "format_open_scout_loop_stats",
    "format_chunker_v3_stats",
    "format_match_summary",
    "format_session_config",
    "format_clip_write_ok",
    "format_clip_write_fail",
    "verify_clip_write",
    "emit_retro_summary",
    "emit_open_scout_stats",
    "emit_open_scout_loop_stats",
    "emit_chunker_v3_stats",
    "emit_match_summary",
    "is_decoupled_enabled",
    "check_v3_fallback_alarm",
    "check_tpm_alarm",
    "check_consecutive_none_alarm",
    "CLIP_WRITE_MIN_BYTES",
]
