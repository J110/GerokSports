#!/usr/bin/env python3
"""Live pipeline log observer for match-day telemetry rollups.

Tails (or replays) pipeline tee log(s) plus ``files/logs/machine-1-*.log``
(stdlib-handled `[DWR]` lines), merges replay streams by timestamp where
parsable, aggregates telemetry, and rewrites markdown every N seconds.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import glob
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Iterable

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

# Timestamp shapes seen in pipeline logs (fixtures + prod-shaped tests).
_TS_BRACKET = re.compile(
    r"\[(\d{2}:\d{2}:\d{2})\s+F\d+(?:\s+\w+)?\]"
)

_THIS_OVER_OVER = re.compile(
    r"\[THIS-OVER\]\s+Ball\s+\S+\s+appended\s+to\s+over\s+(\d+)",
    re.I,
)
_DIRECT_SCORE = re.compile(r"\[DIRECT\]\s+score→(\d+)")
_OVERS_EQ = re.compile(r"overs=(\d+\.\d+|\d+)\b")
_SM_INNINGS = re.compile(r"\[SM-INNINGS-2-RESET\]\s+reason=([^:\s]+)")
_STRIKER_CUTOVER_REASON = re.compile(
    r"\[STRIKER-SM-CUTOVER\][^\n]*?reason=([\w\-]+)",
)
_BAT_RULE_A = re.compile(
    r"\[BATTERS-INVARIANT\]\s+rule=([^\s]+)",
)
_SCOUT_CAM = re.compile(
    r"\[SCOUT\]\s+\w+\s+\d+ms\s+.*?\bcam=(\w+)\b",
)
_SCOUT_FRAME_LINE = re.compile(r"\[SCOUT\]\s+(\w+)\s+(\d+)ms\b")

_FRAMES_PROCESSED_HASH = re.compile(
    r"\[[Ff](\d+)\][^\n]*[\u2014]\s*#(\d+)\s*$")

# 2026-05-03 ``[SHADOW-STATS] {...}`` heartbeat produced by
# files/test_pipeline.py every ~60 s when the OpenScout shadow runner
# is attached.  Payload is a Python dict repr (str-ified
# ``OpenScoutShadowRunner.stats()`` output).
_SHADOW_STATS_LINE = re.compile(r"\[SHADOW-STATS\]\s*(\{.*\})\s*$")

# 2026-05-03 simple substring tags surfaced from today's shipments
# (P10/P12/P14/P15/P16/P19/P20 + SHADOW umbrella).  Each is bumped via
# the generic ``in clean`` check below; trace_emitter.KNOWN_TAGS is the
# source-of-truth for the full enum.
_TAGS_2026_05_03 = (
    "[TIMEOUT-GAP-INFER]",
    "[BATTER-CONSENSUS-RESET]",
    "[BOWLER-STATS-SANITY-REJECT]",
    "[SCORE-OVERS-RR-REJECT]",
    "[BOWLER-LATENCY-HARDCAP]",
    "[LATENCY-STUCK]",
    "[STRIP-OVERLAY-DETECTED]",
    "[INN2-TRANSITION-REJECT]",
    "[INN2-TRANSITION-NULL-TEAM]",
    "[INN2-COLD-START-LOCKOUT]",
    "[INN2-COLD-START-CONSENSUS]",
    "[INN2-TRANSITION-PHANTOM-STORM]",
)

# 2026-05-04 round 2/3 fix tags (Batches F/G/H/J).  ``[INVARIANT]``
# is generic; we only count the Batch-F-specific
# ``Refusing to un-dismiss`` substring.
_TAGS_ROUND_2_3 = (
    "[OVERLAY-LOCKOUT-BREAKOUT]",
    "[BOWLER-STATS-REGRESSION]",
    "[INCOMING-BATTER-PROMOTED]",
)
_INVARIANT_UNDISMISS_SUBSTR = (
    "[INVARIANT]", "Refusing to un-dismiss",
)
_BMF_DEBUG_DIR_REL = "files/logs/bmf_debug"
_WICKET_HINT = "[WICKET]"

# `[DWR] window #N source=<slug> frames=M …`
_DWR_WINDOW_LINE = re.compile(
    r"\[DWR\]\s+window\s+#(\d+)\s+source=(\S+)\s+.*?frames=(\d+)",
    re.IGNORECASE,
)

_MATCH_TITLE_DEFAULT = "RCB vs GT"

_TAIL_EOF = "__TAIL_EOF__"

_DEFAULT_LOG_GLOB = (
    "logs/pipeline-*-rcb-gt-live.log,"
    "logs/pipeline-*-gt-rcb-live.log,"
    "files/logs/machine-1-*.log"
)

_MAX_FRAME_SAMPLES = 8000


def _strip_ansi(s: str) -> str:
    return ANSI_ESCAPE.sub("", s)


def parse_dwr_window_line(clean: str) -> tuple[int, str, int] | None:
    """Parse ``[DWR] window #… source=… frames=…`` or return None."""
    m = _DWR_WINDOW_LINE.search(clean)
    if not m:
        return None
    try:
        return int(m.group(1)), m.group(2), int(m.group(3))
    except ValueError:
        return None


def _parse_ts(line_clean: str) -> str | None:
    m = _TS_BRACKET.search(line_clean)
    return m.group(1) if m else None


def _hhmmss_sort_seconds(ts: str | None) -> float | None:
    if not ts or len(ts) < 8:
        return None
    try:
        h, m, s = (int(x) for x in ts.split(":"))
        return ((h * 60) + m) * 60 + s
    except ValueError:
        return None


def _severity(line_clean: str) -> str | None:
    if re.search(r"\bERROR\b", line_clean):
        return "ERROR"
    if re.search(r"\bWARN(?:ING)?\b", line_clean):
        return "WARN"
    if re.search(r"\bINFO\b", line_clean):
        return "INFO"
    return None


def _median_sorted(sorted_vals: list[int]) -> float | None:
    if not sorted_vals:
        return None
    n = len(sorted_vals)
    mid = n // 2
    if n % 2:
        return float(sorted_vals[mid])
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0


def _pick_newest_for_pattern(repo_root: Path, pattern: str) -> Path | None:
    full = str(repo_root / pattern.replace("\\", "/"))
    paths = [Path(p) for p in glob.glob(full)]
    if not paths:
        return None
    paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return paths[0]


def resolve_watch_pairs(repo_root: Path, patterns_csv: str) -> list[tuple[str, Path]]:
    """One newest path per comma-separated glob; duplicate paths deduped."""
    out: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for raw in patterns_csv.split(","):
        pat = raw.strip()
        if not pat:
            continue
        p = _pick_newest_for_pattern(repo_root, pat)
        if p is None:
            continue
        key = str(p.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append((pat, p))
    return out


def merged_replay_lines(paths: list[Path]) -> Iterable[str]:
    """Replay merge: sort by parsed ``HH:MM:SS`` then file index / line no."""
    rows: list[tuple[tuple[float, int, int], str]] = []
    for pi, path in enumerate(paths):
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for li, line in enumerate(fh):
                clean = _strip_ansi(line.rstrip("\n"))
                ts = _parse_ts(clean)
                sec = _hhmmss_sort_seconds(ts)
                sk = (
                    sec if sec is not None else float("inf"),
                    pi,
                    li,
                )
                rows.append((sk, line))
    rows.sort(key=lambda x: x[0])
    for _, line in rows:
        yield line


class ObservationState:
    """Mutable rollup consumed by the markdown writer."""

    def __init__(self, match_title: str, watched_logs: list[Path]) -> None:
        self.match_title = match_title
        self.watched_logs = watched_logs
        self.started_wall = dt.datetime.now(dt.timezone.utc).isoformat()
        self.first_log_ts: str | None = None
        self.last_log_ts: str | None = None
        self.last_refresh_wall = ""

        self.frames_seen_max = 0
        self.processed_max = 0

        self.last_over_ball: str | None = None
        self.last_pipeline_score: str | None = None
        self.last_active_batters_note: str | None = None

        self.current_delivery_over: int | None = None

        self.tag_totals: dict[str, int] = collections.Counter()
        self.ws_slot_samples: collections.deque[str] = collections.deque(
            maxlen=8)
        self.striker_cutover_reasons: dict[str, int] = collections.Counter()
        self.innings_reset_times: list[str] = []

        self.per_over: dict[int, dict[str, Any]] = collections.defaultdict(
            lambda: {
                "this_over": 0,
                "delivery_enqueued": 0,
                "dwr_window": 0,
                "dwr_skip_phantom": 0,
                "dwr_skip_overlap": 0,
                "dwr_skip_stale": 0,
                "balls_logged": [],
            })

        # DWR span assembly (machine-1 log)
        self.dwr_window_frames_all: list[int] = []
        self.dwr_frames_by_source: dict[str, list[int]] = (
            collections.defaultdict(list))

        self.scout_cam: dict[str, int] = collections.Counter()
        self.scout_errors: dict[str, int] = collections.Counter()

        self.errors_table: collections.deque[tuple[str, str, str, str]] = (
            collections.deque(maxlen=80))

        self.notable: collections.deque[str] = collections.deque(maxlen=40)

        self.ball_detector_notes: dict[str, int] = collections.Counter()

        self.per_minute: dict[str, collections.Counter[str]] = (
            collections.defaultdict(collections.Counter))

        self.lines_ok = 0
        self.lines_malformed = 0

        self.shadow_lines = 0
        self.shadow_stats_lines = 0
        self.last_shadow_stats: dict[str, Any] | None = None
        self.last_shadow_stats_ts: str | None = None

        # Round 2/3 tag notable timestamps (Batches F/G/H/J).
        self.round_2_3_notable: dict[str, list[str]] = {
            "[INVARIANT] Refusing to un-dismiss": [],
            "[OVERLAY-LOCKOUT-BREAKOUT]": [],
            "[BOWLER-STATS-REGRESSION]": [],
            "[INCOMING-BATTER-PROMOTED]": [],
        }
        self.wicket_count = 0
        # BMF debug telemetry growth tracker (set lazily on first
        # render).  Keyed by file path → (size_bytes, refresh_wall).
        self.bmf_size_history: list[tuple[str, int]] = []

    def _record_dwr_window_frames(self, bucket: str, n: int) -> None:
        lst = self.dwr_frames_by_source[bucket]
        lst.append(n)
        if len(lst) > _MAX_FRAME_SAMPLES:
            del lst[: len(lst) - _MAX_FRAME_SAMPLES]
        self.dwr_window_frames_all.append(n)
        if len(self.dwr_window_frames_all) > _MAX_FRAME_SAMPLES:
            del self.dwr_window_frames_all[
                : len(self.dwr_window_frames_all) - _MAX_FRAME_SAMPLES]

    def _minute_key(self, hhmmss: str | None) -> str | None:
        if not hhmmss or len(hhmmss) < 5:
            return None
        return hhmmss[:5]

    def ingest_line(self, raw: str, *, stderr_major: Any) -> None:
        clean = _strip_ansi(raw.rstrip("\n"))
        if not clean.strip():
            return

        ts = _parse_ts(clean)
        if ts:
            self.last_log_ts = ts
            if self.first_log_ts is None:
                self.first_log_ts = ts

        minute_k = self._minute_key(ts)

        fm = re.search(r"\[[Ff](\d+)\]", clean)
        if fm:
            try:
                self.frames_seen_max = max(
                    self.frames_seen_max, int(fm.group(1)))
            except ValueError:
                self.lines_malformed += 1
                return

        pm = _FRAMES_PROCESSED_HASH.search(clean)
        if pm:
            try:
                self.processed_max = max(
                    self.processed_max, int(pm.group(2)))
            except ValueError:
                pass

        over_ball_m = list(_OVERS_EQ.finditer(clean))
        if over_ball_m:
            self.last_over_ball = over_ball_m[-1].group(1)

        dm = _DIRECT_SCORE.search(clean)
        if dm:
            self.last_pipeline_score = dm.group(1)

        def bump(tag_key: str, n: int = 1) -> None:
            self.tag_totals[tag_key] += n
            if minute_k:
                self.per_minute[minute_k][tag_key] += n

        # --- Today's shipments validation ---
        if "[WS-SLOT-INVARIANT]" in clean:
            bump("[WS-SLOT-INVARIANT]")
            self.ws_slot_samples.append(clean[-220:])
            self.notable.append(f"WS-SLOT-INVARIANT @ {ts or '?'}")
        if "[SM-W8-DISMISSED-GUARD]" in clean:
            bump("[SM-W8-DISMISSED-GUARD]")
        if "[STRIP-ROWS-MISALIGNED]" in clean or (
                "[STRIPS-ROW-MISALIGNED]" in clean):
            bump("[STRIPS-ROW-MISALIGNED]")
        if "[CAM-GRAPHIC-FAST-PATH-READ]" in clean:
            bump("[CAM-GRAPHIC-FAST-PATH-READ]")
        if "[CAM-GRAPHIC-FAST-PATH-REJECT]" in clean:
            bump("[CAM-GRAPHIC-FAST-PATH-REJECT]")
        if "[CAM-GRAPHIC-FAST-PATH-NOOP]" in clean:
            bump("[CAM-GRAPHIC-FAST-PATH-NOOP]")
        if "[SM-INNINGS-2-RESET]" in clean:
            bump("[SM-INNINGS-2-RESET]")
            self.innings_reset_times.append(ts or "?")
            m = _SM_INNINGS.search(clean)
            reason = m.group(1) if m else "?"
            print(
                f"[live_match_monitor] MAJOR: SM-INNINGS-2-RESET "
                f"reason={reason} @ {ts}",
                file=sys.stderr,
            )
            stderr_major.put(("innings_reset", clean))

        if "[BATTERS-INVARIANT]" in clean:
            bump("[BATTERS-INVARIANT]")
            rm = _BAT_RULE_A.search(clean)
            if rm and rm.group(1) == "A":
                bump("[BATTERS-INVARIANT] rule=A NON-ADMISSION")
            ac = re.search(r"\bactive=([^ ]+)", clean)
            if ac:
                raw_act = ac.group(1).strip().strip(",")
                parts = [p for p in raw_act.split(",") if p]
                self.last_active_batters_note = (
                    f"{len(parts)} named ({raw_act[:120]})")

        if "[STRIKER-SM-CUTOVER]" in clean:
            bump("[STRIKER-SM-CUTOVER]")
            cr = _STRIKER_CUTOVER_REASON.search(clean)
            rk = cr.group(1) if cr else "(no reason= field)"
            self.striker_cutover_reasons[rk] += 1

        if "_FRAME_POISONED_STRIP_TRUST_THRESHOLD" in clean:
            bump("[_FRAME_POISONED_STRIP_TRUST_THRESHOLD]")
            self.notable.append(
                f"P0-C poison-rate / threshold mention @ {ts or '?'}")
        if "[TEAM-ATTRIBUTION-POISON-RATE]" in clean:
            bump("[TEAM-ATTRIBUTION-POISON-RATE]")

        # --- Delivery detection ---
        tom = _THIS_OVER_OVER.search(clean)
        if tom:
            ov = int(tom.group(1))
            self.current_delivery_over = ov
            rec = self.per_over[ov]
            rec["this_over"] += 1
            rec["balls_logged"].append(ts or "?")
            bump("[THIS-OVER]")
            if minute_k:
                self.per_minute[minute_k]["[THIS-OVER]"] += 1

        if "[DELIVERY ENQUEUED]" in clean:
            bump("[DELIVERY ENQUEUED]")
            ov = self.current_delivery_over
            if ov is not None:
                self.per_over[ov]["delivery_enqueued"] += 1
            if minute_k:
                self.per_minute[minute_k]["[DELIVERY ENQUEUED]"] += 1

        if "[DWR]" in clean:
            parsed = parse_dwr_window_line(clean)
            if parsed:
                _wid, src_raw, frames_n = parsed
                bump("[DWR] window")
                if minute_k:
                    self.per_minute[minute_k]["[DWR] window"] += 1

                if src_raw == "retrospective_span":
                    bump("[DWR] window source=retrospective_span")
                    bucket = "retrospective_span"
                elif src_raw == "fallback_pre_event_window":
                    bump("[DWR] window source=fallback_pre_event_window")
                    bucket = "fallback_pre_event_window"
                else:
                    bump("[DWR] window source=other")
                    bump(f"[DWR] window source_other={src_raw}")
                    bucket = f"other:{src_raw}"

                self._record_dwr_window_frames(bucket, frames_n)

                ov = self.current_delivery_over
                if ov is not None:
                    self.per_over[ov]["dwr_window"] += 1

            elif "SKIP phantom" in clean:
                bump("[DWR] SKIP phantom")
                ov = self.current_delivery_over
                om = re.search(r"\bover=([\d.]+)", clean)
                if om:
                    try:
                        ov = int(float(om.group(1)))
                    except ValueError:
                        pass
                if ov is not None:
                    self.per_over[ov]["dwr_skip_phantom"] += 1
                if minute_k:
                    self.per_minute[minute_k]["[DWR] SKIP phantom"] += 1
            elif "overlaps" in clean and "refusing to" in clean:
                bump("[DWR] SKIP overlap")
                ov = self.current_delivery_over
                if ov is not None:
                    self.per_over[ov]["dwr_skip_overlap"] += 1
                if minute_k:
                    self.per_minute[minute_k]["[DWR] SKIP overlap"] += 1
            elif "rejecting stale span" in clean:
                bump("[DWR] rejecting stale span")
                ov = self.current_delivery_over
                if ov is not None:
                    self.per_over[ov]["dwr_skip_stale"] += 1
                if minute_k:
                    self.per_minute[minute_k]["[DWR] rejecting stale span"] += 1

        # --- Scout ---
        scm = _SCOUT_CAM.search(clean)
        if scm:
            cam = scm.group(1)
            self.scout_cam[cam] += 1
            bump(f"[SCOUT] cam={cam}")

        elif "[SCOUT]" in clean:
            if _SCOUT_FRAME_LINE.search(clean) and "cam=" not in clean:
                self.scout_cam["(unknown_cam_field)"] += 1
                bump("[SCOUT] cam_parse_miss")
            err_bucket = None
            low = clean.lower()
            if "[scout] error:" in low:
                tail = clean.split(":", 2)[-1].strip()[:160]
                if "timeout" in low:
                    err_bucket = "TimeoutError-ish"
                elif "rate" in low and "limit" in low:
                    err_bucket = "RateLimitError-ish"
                elif "502" in clean or "500" in clean:
                    err_bucket = "HTTP 500/502"
                else:
                    err_bucket = "other"
                self.scout_errors[err_bucket] += 1
                bump("[SCOUT] API error line")
                print(
                    f"[live_match_monitor] MAJOR: Scout error ({err_bucket}) "
                    f"@ {ts}: {tail}",
                    file=sys.stderr,
                )
                stderr_major.put(("scout_err", clean))

        # --- Operational ---
        sev = _severity(clean)
        if sev == "ERROR" or (
                sev == "WARN" and (
                    "Traceback" in clean or "crashed" in clean.lower())):
            tag_src = "ERROR_LINE"
            if "[" in clean:
                inner = re.search(r"\[([^\]]+)\]", clean)
                if inner:
                    tag_src = inner.group(1)[:48]
            msg = clean[-400:]
            self.errors_table.append((ts or "?", sev, tag_src, msg))
            bump("ERROR_LINES")
            print(
                f"[live_match_monitor] MAJOR: {sev} @ {ts}: {msg[:200]}",
                file=sys.stderr,
            )
            stderr_major.put(("error", clean))

        # --- 2026-05-03 shipments (P10/P12/P14/P15/P16/P19/P20) ---
        for _tag in _TAGS_2026_05_03:
            if _tag in clean:
                bump(_tag)

        # --- 2026-05-04 round 2/3 fixes (Batches F/G/H/J) ---
        if (_INVARIANT_UNDISMISS_SUBSTR[0] in clean
                and _INVARIANT_UNDISMISS_SUBSTR[1] in clean):
            key = "[INVARIANT] Refusing to un-dismiss"
            bump(key)
            lst = self.round_2_3_notable[key]
            if len(lst) < 16:
                lst.append(ts or "?")
        for _tag in _TAGS_ROUND_2_3:
            if _tag in clean:
                bump(_tag)
                lst = self.round_2_3_notable[_tag]
                if len(lst) < 16:
                    lst.append(ts or "?")
        if _WICKET_HINT in clean:
            self.wicket_count += 1

        # --- OpenScout shadow runner heartbeat + umbrella ---
        if "[SHADOW-STATS]" in clean:
            self.shadow_stats_lines += 1
            bump("[SHADOW-STATS]")
            sm = _SHADOW_STATS_LINE.search(clean)
            if sm:
                payload = sm.group(1)
                parsed: dict[str, Any] | None = None
                try:
                    import ast
                    parsed = ast.literal_eval(payload)
                except (ValueError, SyntaxError):
                    parsed = None
                if isinstance(parsed, dict):
                    self.last_shadow_stats = parsed
                    self.last_shadow_stats_ts = ts
        elif "[SHADOW]" in clean:
            self.shadow_lines += 1
            bump("[SHADOW]")
            low = clean.lower()
            if ("exception" in low or "fail" in low
                    or "error" in low):
                bump("[SHADOW] exception")

        if "[BED]" in clean:
            self.ball_detector_notes["[BED]"] += 1
        low = clean.lower()
        if "ball_detector" in low or "balldetector" in low:
            self.ball_detector_notes["mention_ball_detector"] += 1
        if "ballextractor" in low and "error" in low:
            bump("ball_detector_error_mention")

        self.lines_ok += 1

    def frames_per_second_approx(self) -> str | None:
        if self.processed_max <= 1:
            return None
        if not self.first_log_ts or not self.last_log_ts:
            return None

        def _to_sec(hms: str) -> float:
            h, m, s = (int(x) for x in hms.split(":"))
            return ((h * 60) + m) * 60 + s

        try:
            t0 = _to_sec(self.first_log_ts)
            t1 = _to_sec(self.last_log_ts)
        except ValueError:
            return None
        span = t1 - t0
        if span <= 0:
            return None
        return f"{self.processed_max / span:.3f}"

    def retrospective_headline_pct(self) -> tuple[str, float | None]:
        """Human headline + numeric pct (None if N/A)."""
        retro = self.tag_totals.get("[DWR] window source=retrospective_span", 0)
        fb = self.tag_totals.get(
            "[DWR] window source=fallback_pre_event_window", 0)
        denom = retro + fb
        if denom == 0:
            return "N/A (no windows yet)", None
        pct = 100.0 * retro / denom
        return f"{pct:.1f}%", pct


def _render_md(state: ObservationState) -> str:
    today = dt.date.today().isoformat()
    fps = state.frames_per_second_approx()

    rows_ship = [
        "[WS-SLOT-INVARIANT]",
        "[SM-W8-DISMISSED-GUARD]",
        "[STRIPS-ROW-MISALIGNED]",
        "[CAM-GRAPHIC-FAST-PATH-READ]",
        "[CAM-GRAPHIC-FAST-PATH-REJECT]",
        "[CAM-GRAPHIC-FAST-PATH-NOOP]",
        "[SM-INNINGS-2-RESET]",
        "[BATTERS-INVARIANT]",
        "[BATTERS-INVARIANT] rule=A NON-ADMISSION",
        "[STRIKER-SM-CUTOVER]",
        "[_FRAME_POISONED_STRIP_TRUST_THRESHOLD]",
        "[TEAM-ATTRIBUTION-POISON-RATE]",
        "[DELIVERY ENQUEUED]",
        "[DWR] window",
        "[DWR] window source=retrospective_span",
        "[DWR] window source=fallback_pre_event_window",
        "[DWR] window source=other",
        "[DWR] SKIP phantom",
        "[DWR] SKIP overlap",
        "[DWR] rejecting stale span",
        "[THIS-OVER]",
        # 2026-05-03 shipments (see runbook §4.6).
        "[TIMEOUT-GAP-INFER]",
        "[BATTER-CONSENSUS-RESET]",
        "[BOWLER-STATS-SANITY-REJECT]",
        "[SCORE-OVERS-RR-REJECT]",
        "[BOWLER-LATENCY-HARDCAP]",
        "[LATENCY-STUCK]",
        "[STRIP-OVERLAY-DETECTED]",
        "[INN2-TRANSITION-REJECT]",
        "[INN2-TRANSITION-NULL-TEAM]",
        "[INN2-COLD-START-LOCKOUT]",
        "[INN2-COLD-START-CONSENSUS]",
        "[INN2-TRANSITION-PHANTOM-STORM]",
        "[SHADOW]",
        "[SHADOW] exception",
        "[SHADOW-STATS]",
        # 2026-05-04 round 2/3 fixes (Batches F/G/H/J).
        "[INVARIANT] Refusing to un-dismiss",
        "[OVERLAY-LOCKOUT-BREAKOUT]",
        "[BOWLER-STATS-REGRESSION]",
        "[INCOMING-BATTER-PROMOTED]",
    ]

    ship_notes = {
        "[SM-INNINGS-2-RESET]":
            "Expect exactly once per innings transition (P0-A).",
        "[SM-W8-DISMISSED-GUARD]":
            "PR3 dedup; expect ≤6/match.",
        "[WS-SLOT-INVARIANT]":
            "Lever 1 PR1–PR4; compare vs priors (~73–87% reduction thesis).",
        "[STRIPS-ROW-MISALIGNED]":
            "Thread 7 Fix 1 (also emitted as STRIP-ROWS-MISALIGNED).",
        "[_FRAME_POISONED_STRIP_TRUST_THRESHOLD]":
            "Logged inside TEAM-ATTRIBUTION-POISON-RATE block (P0-C).",
        "[DWR] window":
            "Includes machine-1 stdlib log; see **DWR window source distribution**.",
        "[TIMEOUT-GAP-INFER]":
            "P10 (2026-05-03): info; bursts only on strip OCR drops.",
        "[BATTER-CONSENSUS-RESET]":
            "P14 (2026-05-03): info; ~1–2 per over on legitimate striker swap.",
        "[BOWLER-STATS-SANITY-REJECT]":
            "P15 (2026-05-03): replaces legacy [GUARD]; expect rare.",
        "[SCORE-OVERS-RR-REJECT]":
            "P16 (2026-05-03): occasional OCR RR-implausibility veto.",
        "[BOWLER-LATENCY-HARDCAP]":
            "P20 (2026-05-03): expected ~once per 10+ overs.",
        "[LATENCY-STUCK]":
            "P20 (2026-05-03): >8 frames stuck advisory; should not persist.",
        "[STRIP-OVERLAY-DETECTED]":
            "P19 (2026-05-02/03): pre-filter before row-delta fallback.",
        "[INN2-TRANSITION-PHANTOM-STORM]":
            "P12 (2026-05-03): critical; ≥5 rejects within 60 s.",
        "[SHADOW]":
            "OpenScout shadow runner umbrella (start/stop/exception).",
        "[SHADOW-STATS]":
            "Periodic heartbeat (~60 s) when SHADOW_MODE=1; see **OpenScout shadow runner**.",
        "[INVARIANT] Refusing to un-dismiss":
            "Batch F (2026-05-04): expected ≤5/match; bursts hint at strip flap.",
        "[OVERLAY-LOCKOUT-BREAKOUT]":
            "Batch G (2026-05-04): fallback path; expected ≤5/match if Batch J holds.",
        "[BOWLER-STATS-REGRESSION]":
            "Batch H (2026-05-04): cross-match contamination guard; expected ≤3/match.",
        "[INCOMING-BATTER-PROMOTED]":
            "Batch J (2026-05-04): expected ≈ wickets-1 per innings.",
    }

    delivery_tags = (
        "[DELIVERY ENQUEUED]",
        "[DWR] window",
        "[DWR] window source=retrospective_span",
        "[DWR] window source=fallback_pre_event_window",
        "[DWR] window source=other",
        "[DWR] SKIP phantom",
        "[DWR] SKIP overlap",
        "[DWR] rejecting stale span",
        "[THIS-OVER]",
    )

    headline_str, headline_pct = state.retrospective_headline_pct()

    md: list[str] = []
    logs_join = ", ".join(f"`{p}`" for p in state.watched_logs) or "`(none)`"
    md.append(f"# Live observation: {state.match_title}, {today}")
    md.append("")
    md.append("## Match status")
    md.append("")
    md.append(f"- **Started (monitor clock):** {state.started_wall}")
    md.append(f"- **Watched logs:** {logs_join}")
    md.append(
        f"- **Last refresh:** "
        f"{state.last_refresh_wall or dt.datetime.now(dt.timezone.utc).isoformat()}")
    md.append(
        f"- **Frames processed (max `#` seen):** {state.processed_max}")
    md.append(f"- **Max frame id `[Fn]`:** {state.frames_seen_max}")
    md.append(
        f"- **Current over (last `overs=` capture):** "
        f"{state.last_over_ball or '—'}")
    md.append(
        f"- **Pipeline score (last `[DIRECT]`):** "
        f"{state.last_pipeline_score or '—'}")
    md.append(
        f"- **Approx. processing rate:** "
        f"{fps + ' frames/sec (from log timestamps)' if fps else 'n/a'}")
    md.append(
        f"- **Active batters note (last BATTERS-INVARIANT):** "
        f"{state.last_active_batters_note or '—'}")
    md.append("")
    md.append("### DWR headline (retrospective vs fallback spans)")
    md.append("")
    md.append(
        f"- **retrospective_span_pct** "
        f"(retro / (retro + fallback)): **{headline_str}**")
    md.append("")
    md.append("### SM-INNINGS-2-RESET watch")
    md.append("")
    md.append(f"- **Fire count:** {state.tag_totals.get('[SM-INNINGS-2-RESET]', 0)}")
    md.append(f"- **Timestamps:** {', '.join(state.innings_reset_times) or '—'}")
    md.append("")

    md.append("## DWR window source distribution")
    md.append("")
    md.append("### DWR span assembly distribution")
    md.append("")
    md.append("| Kind | Count | % of typed windows | Avg frames | Median frames | Max frames |")
    md.append("| --- | --- | --- | --- | --- | --- |")

    retro_c = state.tag_totals.get("[DWR] window source=retrospective_span", 0)
    fb_c = state.tag_totals.get(
        "[DWR] window source=fallback_pre_event_window", 0)
    other_c = state.tag_totals.get("[DWR] window source=other", 0)
    typed_total = retro_c + fb_c + other_c
    denom_pct = typed_total if typed_total else 1

    def _row(label: str, cnt: int, bucket_key: str) -> None:
        samples = sorted(state.dwr_frames_by_source.get(bucket_key, []))
        avg_f = (
            sum(samples) / len(samples)) if samples else None
        med_f = _median_sorted(samples)
        mx_f = max(samples) if samples else None
        avg_disp = f"{avg_f:.2f}" if avg_f is not None else "—"
        med_disp = (
            f"{med_f:.1f}" if med_f is not None and med_f != int(med_f)
            else (str(int(med_f)) if med_f is not None else "—"))
        md.append(
            f"| {label} | {cnt} | {100.0 * cnt / denom_pct:.1f}% | "
            f"{avg_disp} | {med_disp} | "
            f"{mx_f if mx_f is not None else '—'} |")

    _row("`retrospective_span`", retro_c, "retrospective_span")
    _row("`fallback_pre_event_window`", fb_c, "fallback_pre_event_window")
    other_samples: list[int] = []
    for sk, lst in state.dwr_frames_by_source.items():
        if sk.startswith("other:"):
            other_samples.extend(lst)
    other_samples.sort()
    if other_c > 0 and other_samples:
        omx = max(other_samples)
        oavg = sum(other_samples) / len(other_samples)
        omed = _median_sorted(other_samples)
        md.append(
            f"| `other` (aggregated) | {other_c} | "
            f"{100.0 * other_c / denom_pct:.1f}% | "
            f"{oavg:.2f} | "
            f"{omed if omed is not None else '—'} | "
            f"{omx} |")
    else:
        md.append(
            f"| `other` (aggregated) | {other_c} | "
            f"{100.0 * other_c / denom_pct:.1f}% | "
            f"— | — | — |")

    stale_r = state.tag_totals.get("[DWR] rejecting stale span", 0)
    sk_ph = state.tag_totals.get("[DWR] SKIP phantom", 0)
    sk_ov = state.tag_totals.get("[DWR] SKIP overlap", 0)
    md.append(f"| stale-span rejections | {stale_r} | — | — | — | — |")
    md.append(f"| SKIP phantom | {sk_ph} | — | — | — | — |")
    md.append(f"| SKIP overlap | {sk_ov} | — | — | — | — |")

    all_f = sorted(state.dwr_window_frames_all)
    if all_f:
        md.append("")
        md.append(
            f"- **All DWR windows (frames):** count={len(all_f)}, "
            f"median={_median_sorted(all_f)}, max={max(all_f)}")
    md.append("")
    md.append(
        "*Per-over breakdown for retrospective vs fallback is **not** attributed "
        "(machine-1 `[DWR]` lines omit pipeline wall-clock timestamps); "
        "`DWR windows` per over stays pipeline-context-only.*")
    md.append("")

    md.append("## Per-over delivery detection")
    md.append("")
    md.append(
        "| Over | THIS-OVER count | DELIVERY ENQUEUED count | "
        "DWR windows | Notes |")
    md.append("| --- | --- | --- | --- | --- |")
    overs_sorted = sorted(state.per_over.keys())
    if not overs_sorted:
        md.append("| — | 0 | 0 | 0 | No per-over events yet |")
    for ov in overs_sorted:
        rec = state.per_over[ov]
        notes = []
        if rec["dwr_skip_phantom"]:
            notes.append(f"phantom×{rec['dwr_skip_phantom']}")
        if rec["dwr_skip_overlap"]:
            notes.append(f"overlap×{rec['dwr_skip_overlap']}")
        if rec["dwr_skip_stale"]:
            notes.append(f"stale×{rec['dwr_skip_stale']}")
        md.append(
            f"| {ov} | {rec['this_over']} | {rec['delivery_enqueued']} | "
            f"{rec['dwr_window']} | {', '.join(notes) or '—'} |")
    md.append("")

    md.append("### STRIKER-SM-CUTOVER reasons (Lever 1 PR3)")
    md.append("")
    if state.striker_cutover_reasons:
        for reason, cnt in sorted(
                state.striker_cutover_reasons.items(),
                key=lambda kv: (-kv[1], kv[0])):
            md.append(f"- `{reason}`: {cnt}")
    else:
        md.append("- _(none yet)_")
    md.append("")

    md.append("### WS-SLOT-INVARIANT recent contexts (truncated)")
    md.append("")
    if state.ws_slot_samples:
        for s in state.ws_slot_samples:
            md.append(f"- `{s}`")
    else:
        md.append("- _(none)_")
    md.append("")

    md.append("## Today's shipments validation")
    md.append("")
    md.append("| Tag | Count | Per-over rate | Notes |")
    md.append("| --- | --- | --- | --- |")
    n_overs = max(len(overs_sorted), 1)
    for tag in rows_ship:
        if tag in delivery_tags:
            continue
        c = state.tag_totals.get(tag, 0)
        note = ship_notes.get(tag, "")
        md.append(f"| `{tag}` | {c} | {c / n_overs:.3f} | {note} |")
    md.append("")

    md.append("## OpenScout shadow runner")
    md.append("")
    if state.shadow_lines == 0 and state.shadow_stats_lines == 0:
        md.append("- _(no `[SHADOW]` lines seen — SHADOW_MODE likely off)_")
    else:
        md.append(
            f"- **`[SHADOW]` lines:** {state.shadow_lines} "
            f"(of which exceptions: "
            f"{state.tag_totals.get('[SHADOW] exception', 0)})")
        md.append(
            f"- **`[SHADOW-STATS]` heartbeats:** "
            f"{state.shadow_stats_lines} "
            f"(last @ {state.last_shadow_stats_ts or '—'})")
        s = state.last_shadow_stats or {}
        if s:
            md.append("- **Last heartbeat snapshot:**")
            md.append("")
            md.append("| Field | Value |")
            md.append("| --- | --- |")
            for k in (
                "thread_alive",
                "frames_received",
                "scout_results_received",
                "stage1_windows_opened",
                "stage1_windows_closed",
                "stage2_spans_emitted",
                "stage3_qwen_dispatched",
                "stage3_qwen_failed",
                "exceptions_total",
                "queue_depth_frame",
                "queue_depth_scout",
                "queue_depth_span",
                "last_record_ts",
            ):
                md.append(f"| `{k}` | {s.get(k, '—')} |")
        else:
            md.append("- _(stats payload not yet parsed)_")
    md.append("")

    md.append("## Scout classification distribution")
    md.append("")
    total_scout = sum(state.scout_cam.values()) or 1
    md.append("| Camera view | Count | % of frames |")
    md.append("| --- | --- | --- |")
    for cam, cnt in sorted(
            state.scout_cam.items(), key=lambda kv: (-kv[1], kv[0])):
        md.append(f"| `{cam}` | {cnt} | {100.0 * cnt / total_scout:.2f}% |")
    md.append("")
    md.append("### Scout / API errors (bucketed)")
    md.append("")
    if state.scout_errors:
        for k, v in sorted(state.scout_errors.items()):
            md.append(f"- `{k}`: {v}")
    else:
        md.append("- _(none classified)_")
    md.append("")

    md.append("## Errors and warnings (recent capped)")
    md.append("")
    md.append("| Timestamp | Severity | Tag/Source | Message |")
    md.append("| --- | --- | --- | --- |")
    for ts, sev, tag, msg in list(state.errors_table)[-40:]:
        esc = msg.replace("|", "\\|").replace("\n", " ")
        md.append(f"| {ts} | {sev} | `{tag}` | {esc} |")
    md.append("")

    md.append("## Operational extras")
    md.append("")
    md.append("### Ball detector / commentary hints")
    md.append("")
    for k, v in sorted(state.ball_detector_notes.items()):
        md.append(f"- `{k}`: {v}")
    md.append("")
    md.append("- Malformed/skipped parse attempts (counter drift): "
                f"{state.lines_malformed}")
    md.append("")

    md.append("### Round 2/3 fixes — tag activity")
    md.append("")
    md.append("| Tag | Count | Notable | Expected behavior |")
    md.append("| --- | --- | --- | --- |")
    _round_2_3_expected = {
        "[INVARIANT] Refusing to un-dismiss":
            "Batch F: ≤5/match; per-wicket post-flap suppression.",
        "[OVERLAY-LOCKOUT-BREAKOUT]":
            "Batch G: ≤5/match if Batch J pre-empts the lockouts.",
        "[BOWLER-STATS-REGRESSION]":
            "Batch H: ≤3/match; >3 indicates contamination or guard FP.",
        "[INCOMING-BATTER-PROMOTED]":
            "Batch J: ≈ (wickets - per-innings tail) over the match.",
    }
    for _tag in (
            "[INVARIANT] Refusing to un-dismiss",
            "[OVERLAY-LOCKOUT-BREAKOUT]",
            "[BOWLER-STATS-REGRESSION]",
            "[INCOMING-BATTER-PROMOTED]",
    ):
        c = state.tag_totals.get(_tag, 0)
        notes = state.round_2_3_notable.get(_tag, [])
        notable_disp = ", ".join(notes[:6]) if notes else "—"
        md.append(
            f"| `{_tag}` | {c} | {notable_disp} | "
            f"{_round_2_3_expected[_tag]} |")
    md.append("")
    md.append(f"- Wicket-event hint count (`[WICKET]`): {state.wicket_count}")
    md.append("")

    md.append("### BMF debug telemetry")
    md.append("")
    bmf_dir = Path(_BMF_DEBUG_DIR_REL)
    if not bmf_dir.is_absolute():
        bmf_dir = Path.cwd() / bmf_dir
    if not bmf_dir.exists():
        md.append(
            f"- _(`{_BMF_DEBUG_DIR_REL}` not present — Batch I lazy-create may not have fired yet.)_")
    else:
        rows = []
        try:
            for p in sorted(bmf_dir.glob("*.jsonl")):
                try:
                    sz = p.stat().st_size
                except OSError:
                    continue
                rows.append((p.name, sz))
        except OSError:
            rows = []
        if not rows:
            md.append(
                f"- _(no `*.jsonl` files yet under `{_BMF_DEBUG_DIR_REL}` — Batch I may not have fired.)_")
        else:
            md.append("| File | Size (bytes) |")
            md.append("| --- | --- |")
            for name, sz in rows:
                md.append(f"| `{name}` | {sz} |")
            md.append("")
            md.append(
                "- Expected ~150 rows / 30s heartbeat at 5 fps effective ingest. "
                "If bytes do not grow between refreshes, Batch I telemetry is broken.")
    md.append("")

    md.append("## Per-minute rollup (wall-clock mm:ss from log prefix)")
    md.append("")
    minutes_sorted = sorted(state.per_minute.keys())
    keep = minutes_sorted[-25:] if len(minutes_sorted) > 25 else minutes_sorted
    md.append("| Minute | WS-SLOT | DELIVERY-Q | DWR-win | retro | fb | stale | THIS-OVER |")
    md.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for mk in keep:
        pc = state.per_minute[mk]
        md.append(
            f"| {mk} | {pc.get('[WS-SLOT-INVARIANT]', 0)} | "
            f"{pc.get('[DELIVERY ENQUEUED]', 0)} | "
            f"{pc.get('[DWR] window', 0)} | "
            f"{pc.get('[DWR] window source=retrospective_span', 0)} | "
            f"{pc.get('[DWR] window source=fallback_pre_event_window', 0)} | "
            f"{pc.get('[DWR] rejecting stale span', 0)} | "
            f"{pc.get('[THIS-OVER]', 0)} |")
    md.append("")

    md.append("## Notable events")
    md.append("")
    if state.notable:
        for line in state.notable:
            md.append(f"- {line}")
    else:
        md.append("- _(none auto-flagged)_")

    md.append("")
    md.append("## Anomalies (automatic heuristics)")
    md.append("")
    anomalies = []
    ic = state.tag_totals.get("[SM-INNINGS-2-RESET]", 0)
    if ic > 1:
        anomalies.append(
            f"- SM-INNINGS-2-RESET fired {ic} times (expect 1 per transition "
            "— verify innings boundary logic).")
    if ic == 0:
        anomalies.append(
            "- SM-INNINGS-2-RESET not seen yet "
            "(normal until innings change).")
    if state.tag_totals.get("[SM-W8-DISMISSED-GUARD]", 0) > 6:
        anomalies.append(
            "- SM-W8-DISMISSED-GUARD exceeds PR3 expectation (>6).")
    scout_total = sum(state.scout_cam.values())
    if scout_total:
        be = state.scout_cam.get("bowlers_end", 0) / scout_total
        if be > 0.30:
            anomalies.append(
                f"- bowlers_end Share {be:.1%} — unusually high vs typical "
                "production mix (watch over-emission).")
    if sum(state.scout_errors.values()):
        anomalies.append("- Scout/API bucket errors present — see table.")
    if state.tag_totals.get("ERROR_LINES", 0) > 20:
        anomalies.append("- Elevated ERROR/WARN capture volume.")
    if state.last_shadow_stats is not None:
        s = state.last_shadow_stats
        if not s.get("thread_alive", True):
            anomalies.append(
                "- SHADOW thread_alive=False on most recent heartbeat — "
                "shadow runner died (main pipeline unaffected).")
        if int(s.get("exceptions_total", 0) or 0) > 5:
            anomalies.append(
                f"- SHADOW exceptions_total="
                f"{s.get('exceptions_total')} (>5) — investigate "
                "files/logs/openscout_shadow/.")
    if (state.shadow_stats_lines == 0
            and state.tag_totals.get("[SHADOW]", 0) > 0):
        anomalies.append(
            "- `[SHADOW]` lines present but no `[SHADOW-STATS]` "
            "heartbeats yet — confirm test_pipeline 1800-frame logger.")
    if headline_pct is not None and headline_pct < 30.0:
        anomalies.append(
            "- **RETROSPECTIVE PATH UNDERFIRED**: "
            f"retrospective_span_pct={headline_pct:.1f}% "
            "(bowlers_end span rarely satisfies DWR lookback — "
            "investigate Scout tagging vs window geometry).")
    if not anomalies:
        anomalies.append("- No heuristic anomalies yet (or insufficient data).")
    md.extend(anomalies)
    md.append("")
    return "\n".join(md)


def _reader_thread(
        proc: subprocess.Popen[str],
        q: queue.Queue[str | tuple[str, str]],
        glob_pat: str,
) -> None:
    assert proc.stdout
    try:
        for line in proc.stdout:
            q.put(line)
    finally:
        q.put((_TAIL_EOF, glob_pat))


def _run_tail_follow(
        log_path: Path,
        *,
        from_beginning: bool,
) -> subprocess.Popen[str]:
    args = ["tail"]
    if from_beginning:
        args.extend(["-n", "+1"])
    else:
        args.extend(["-n", "0"])
    args.extend(["-F", str(log_path)])
    return subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )


def _emit_retrospective_stderr_warning(state: ObservationState) -> None:
    _hs, pct = state.retrospective_headline_pct()
    if pct is None:
        return
    if pct < 30.0:
        retro = state.tag_totals.get("[DWR] window source=retrospective_span", 0)
        fb = state.tag_totals.get(
            "[DWR] window source=fallback_pre_event_window", 0)
        print(
            "[live_match_monitor] RETROSPECTIVE PATH UNDERFIRED: "
            f"retrospective_span_pct={pct:.1f}% "
            f"(retrospective={retro}, fallback={fb})",
            file=sys.stderr,
        )


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Tail pipeline + machine-1 logs → markdown rollup.",
    )
    parser.add_argument(
        "--log-glob",
        default=_DEFAULT_LOG_GLOB,
        help=(
            "Comma-separated globs relative to --repo-root; "
            "newest match per glob, deduped."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=repo_root,
        help="Resolve relative globs against this directory.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Markdown output path (default: files/logs/live_observation_<utc>.md).",
    )
    parser.add_argument(
        "--refresh-seconds",
        type=float,
        default=60.0,
        help="Rewrite rollup interval.",
    )
    parser.add_argument(
        "--match-title",
        default=_MATCH_TITLE_DEFAULT,
        help="Title substring for markdown heading.",
    )
    parser.add_argument(
        "--wait-log-poll",
        type=float,
        default=2.0,
        help="Seconds between glob retries when no watch paths resolve.",
    )
    parser.add_argument(
        "--tail-from-start",
        action="store_true",
        help="Pass `tail -n +1` to ingest existing log contents then follow.",
    )
    parser.add_argument(
        "--replay-file",
        action="append",
        dest="replay_files",
        default=None,
        help=(
            "Process log file(s) once and exit (may repeat flag). "
            "Merged by timestamp when parsable."
        ),
    )
    args = parser.parse_args()

    glob_union_desc = ",".join(
        p.strip() for p in args.log_glob.split(",") if p.strip())

    q_major: queue.Queue[Any] = queue.Queue()

    def refresh_watch_pairs() -> list[tuple[str, Path]]:
        return resolve_watch_pairs(args.repo_root, args.log_glob)

    if args.replay_files:
        paths = [Path(p).expanduser().resolve() for p in args.replay_files]
        for p in paths:
            if not p.is_file():
                print(f"Replay file not found: {p}", file=sys.stderr)
                return 2
        out_path = Path(args.output) if args.output else (
            args.repo_root / "files" / "logs"
            / f"live_observation_replay_{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}.md")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        state = ObservationState(args.match_title, paths)
        for line in merged_replay_lines(paths):
            try:
                state.ingest_line(line, stderr_major=q_major)
            except Exception as exc:
                state.lines_malformed += 1
                print(f"[live_match_monitor] skip line: {exc}", file=sys.stderr)
        state.last_refresh_wall = dt.datetime.now(dt.timezone.utc).isoformat()
        _emit_retrospective_stderr_warning(state)
        out_path.write_text(_render_md(state), encoding="utf-8")
        print(f"Wrote {out_path}", file=sys.stderr)
        return 0

    def open_or_wait_watch() -> list[tuple[str, Path]]:
        pairs = refresh_watch_pairs()
        while not pairs:
            print(
                f"[live_match_monitor] Waiting for any log matching "
                f"`{glob_union_desc}` under `{args.repo_root}` "
                f"(poll every {args.wait_log_poll}s).",
                file=sys.stderr,
            )
            time.sleep(args.wait_log_poll)
            pairs = refresh_watch_pairs()
        return pairs

    watch_pairs = open_or_wait_watch()
    watched_paths = [p for _, p in watch_pairs]

    out_path = Path(args.output) if args.output else (
        args.repo_root / "files" / "logs"
        / f"live_observation_{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    state = ObservationState(args.match_title, watched_paths)

    line_queue: queue.Queue[str | tuple[str, str]] = queue.Queue(maxsize=100000)
    procs: list[subprocess.Popen[str]] = []

    for gpat, lp in watch_pairs:
        proc = _run_tail_follow(lp, from_beginning=args.tail_from_start)
        procs.append(proc)
        th = threading.Thread(
            target=_reader_thread,
            args=(proc, line_queue, gpat),
            daemon=True,
        )
        th.start()

    next_write = time.monotonic() + args.refresh_seconds
    display = ", ".join(str(p) for p in watched_paths)
    print(
        f"[live_match_monitor] Following ({len(watched_paths)} file(s)): "
        f"{display} → `{out_path}` (refresh {args.refresh_seconds}s)",
        file=sys.stderr,
    )

    def restart_tail(glob_pat: str) -> None:
        nonlocal watch_pairs, watched_paths, state
        lp = _pick_newest_for_pattern(args.repo_root, glob_pat)
        if lp is None:
            print(
                f"[live_match_monitor] No file for pattern `{glob_pat}` — "
                "skipping restart.",
                file=sys.stderr,
            )
            return
        print(
            f"[live_match_monitor] Restart tail `{glob_pat}` → `{lp}`",
            file=sys.stderr,
        )
        proc = _run_tail_follow(lp, from_beginning=args.tail_from_start)
        procs.append(proc)
        th = threading.Thread(
            target=_reader_thread,
            args=(proc, line_queue, glob_pat),
            daemon=True,
        )
        th.start()
        # keep state path list in sync if new inode
        cur = list(dict.fromkeys(list(state.watched_logs) + [lp]))
        state.watched_logs = cur

    try:
        while True:
            timeout = max(0.05, next_write - time.monotonic())
            try:
                item = line_queue.get(timeout=timeout)
            except queue.Empty:
                item = None

            if item is not None:
                if isinstance(item, tuple) and item[0] == _TAIL_EOF:
                    gpat_e = item[1]
                    restart_tail(gpat_e)
                else:
                    assert isinstance(item, str)
                    try:
                        state.ingest_line(item, stderr_major=q_major)
                    except Exception as exc:
                        state.lines_malformed += 1
                        print(
                            f"[live_match_monitor] ingest skip: {exc}",
                            file=sys.stderr,
                        )

            while True:
                try:
                    extra = line_queue.get_nowait()
                except queue.Empty:
                    break
                if isinstance(extra, tuple) and extra[0] == _TAIL_EOF:
                    restart_tail(extra[1])
                    continue
                try:
                    state.ingest_line(extra, stderr_major=q_major)
                except Exception as exc:
                    state.lines_malformed += 1
                    print(
                        f"[live_match_monitor] ingest skip: {exc}",
                        file=sys.stderr,
                    )

            if time.monotonic() >= next_write:
                state.last_refresh_wall = dt.datetime.now(
                    dt.timezone.utc).isoformat()
                _emit_retrospective_stderr_warning(state)
                try:
                    out_path.write_text(_render_md(state), encoding="utf-8")
                except OSError as exc:
                    print(f"[live_match_monitor] write failed: {exc}",
                          file=sys.stderr)
                next_write = time.monotonic() + args.refresh_seconds

            try:
                while True:
                    q_major.get_nowait()
            except queue.Empty:
                pass

    except KeyboardInterrupt:
        print("\n[live_match_monitor] stopping...", file=sys.stderr)
        state.last_refresh_wall = dt.datetime.now(dt.timezone.utc).isoformat()
        _emit_retrospective_stderr_warning(state)
        out_path.write_text(_render_md(state), encoding="utf-8")
        for pr in procs:
            try:
                pr.terminate()
            except ProcessLookupError:
                pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
