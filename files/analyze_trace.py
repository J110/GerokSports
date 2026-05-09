"""Trace post-match analyzer — CLI.

Reads `logs/trace/<SESSION>.jsonl(.gz)` produced by `trace_emitter`,
runs every rule in `anomaly_rules.py`, writes a Markdown report and
optionally re-writes the JSONL with each record's `anomalies[]` field
populated.

Usage:
    python files/analyze_trace.py logs/trace/<SESSION>.jsonl \
        --report files/docs/match_reports/<DATE>_<slug>.md \
        [--annotate logs/trace/<SESSION>.annotated.jsonl] \
        [--match-name "RR vs DC, 43rd, IPL 2026"]

Per `files/docs/investigations/trace_and_detect_system_design.md` §5.2.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import statistics
import sys
from typing import Any

from trace_emitter import read_trace, TRACE_SCHEMA_VERSION
from anomaly_rules import Anomaly, evaluate


SEVERITY_ORDER = {"error": 0, "warn": 1, "info": 2, "advisory": 3}


def _fmt_ts(epoch: float | None) -> str:
    if not epoch:
        return "?"
    return dt.datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")


def _bucketize(anoms: list[Anomaly]) -> dict[str, list[Anomaly]]:
    out: dict[str, list[Anomaly]] = {
        "error": [], "warn": [], "info": [], "advisory": []}
    for a in anoms:
        out.setdefault(a.severity, []).append(a)
    return out


def _decision_histogram(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: collections.Counter[str] = collections.Counter()
    for r in records:
        for d in (((r.get("scorer") or {}).get("decisions")) or []):
            tag = d.get("tag")
            if tag:
                counts[tag] += 1
    return dict(counts.most_common())


def _mode_timeline(records: list[dict[str, Any]]) -> list[
        tuple[int, int, str]]:
    """Returns list of (start_frame, end_frame, mode) compressed runs."""
    out: list[tuple[int, int, str]] = []
    cur_mode: str | None = None
    cur_start: int | None = None
    cur_end: int | None = None
    for r in records:
        m = ((r.get("pipeline") or {}).get("mode")) or "WARM"
        f = int(r.get("frame") or 0)
        if cur_mode is None:
            cur_mode = m
            cur_start = f
            cur_end = f
        elif m == cur_mode:
            cur_end = f
        else:
            out.append((cur_start or 0, cur_end or 0, cur_mode))
            cur_mode = m
            cur_start = f
            cur_end = f
    if cur_mode is not None:
        out.append((cur_start or 0, cur_end or 0, cur_mode))
    return out


_KV_RE = __import__("re").compile(
    r"([a-zA-Z_][a-zA-Z0-9_]*)=([^\s]+)")


def _parse_kv_payload(raw: str | None) -> dict[str, str]:
    """Extract ``key=value`` tokens from a ``[TAG] ...`` log message.

    Values stay strings; callers cast to ``int`` / ``float`` as needed.
    """
    if not raw:
        return {}
    out: dict[str, str] = {}
    for m in _KV_RE.finditer(raw):
        out[m.group(1)] = m.group(2).rstrip("%,")
    return out


def _decisions_by_tag(records: list[dict[str, Any]],
                      tag: str) -> list[dict[str, Any]]:
    """All decision entries with ``tag``, in record order."""
    out: list[dict[str, Any]] = []
    for r in records:
        for d in (((r.get("scorer") or {}).get("decisions")) or []):
            if d.get("tag") == tag:
                out.append(d)
    return out


def _f(d: dict[str, str], k: str, default: float = 0.0) -> float:
    try:
        return float(d.get(k, default))
    except (ValueError, TypeError):
        return default


def _i(d: dict[str, str], k: str, default: int = 0) -> int:
    try:
        return int(float(d.get(k, default)))
    except (ValueError, TypeError):
        return default


def _retro_summary_section(records: list[dict[str, Any]]) -> str:
    """[RETRO-SUMMARY] per-innings hit-rate table."""
    rows = _decisions_by_tag(records, "RETRO-SUMMARY")
    if not rows:
        return ""
    lines = ["## Retro-span hit rate (per innings)\n\n",
             "| Innings | Events | Committed | Fallback | Hit rate |\n"
             "|---------|--------|-----------|----------|----------|\n"]
    for d in rows:
        kv = _parse_kv_payload(d.get("raw_message"))
        lines.append(
            f"| {kv.get('innings', '?')} | "
            f"{kv.get('events_seen', '?')} | "
            f"{kv.get('spans_committed', '?')} | "
            f"{kv.get('spans_fallback', '?')} | "
            f"{kv.get('hit_rate', '?')}% |\n")
    lines.append("\n")
    return "".join(lines)


def _open_scout_stats_section(records: list[dict[str, Any]]) -> str:
    """[OPEN-SCOUT-STATS] class-distribution drift timeline."""
    rows = _decisions_by_tag(records, "OPEN-SCOUT-STATS")
    if not rows:
        return ""
    lines = ["## OpenScout class distribution (5-min windows)\n\n",
             "| # | total | action | replay | umpire | ad | other "
             "| lat p50 ms | lat p90 ms | cadence med s |\n"
             "|---|-------|--------|--------|--------|----|"
             "-------|------------|------------|---------------|\n"]
    for i, d in enumerate(rows, 1):
        kv = _parse_kv_payload(d.get("raw_message"))
        lines.append(
            f"| {i} | {kv.get('total', 0)} | "
            f"{kv.get('action', 0)} | {kv.get('replay', 0)} | "
            f"{kv.get('umpire', 0)} | {kv.get('ad', 0)} | "
            f"{kv.get('other', 0)} | {kv.get('lat_p50_ms', 0)} | "
            f"{kv.get('lat_p90_ms', 0)} | "
            f"{kv.get('cadence_median_s', 0)} |\n")
    lines.append("\n")
    return "".join(lines)


def _open_scout_loop_stats_section(
        records: list[dict[str, Any]]) -> str:
    """[OPEN-SCOUT-LOOP-STATS] cadence/util timeline + flagging."""
    rows = _decisions_by_tag(records, "OPEN-SCOUT-LOOP-STATS")
    if not rows:
        return ""
    lines = ["## OpenScout-loop cadence (30-s windows)\n\n",
             "| # | calls | median gap s | p90 gap s | target s "
             "| util % | mean tok | 429 | derate | slot miss "
             "| flag |\n"
             "|---|-------|--------------|-----------|----------|"
             "--------|----------|-----|--------|-----------|"
             "------|\n"]
    for i, d in enumerate(rows, 1):
        kv = _parse_kv_payload(d.get("raw_message"))
        util = _f(kv, "util_tpm_pct")
        median_gap = _f(kv, "median_gap_s")
        flag = ""
        if util > 80.0:
            flag += "HIGH-UTIL "
        if median_gap > 2.0:
            flag += "SLOW-CADENCE "
        lines.append(
            f"| {i} | {kv.get('calls', 0)} | "
            f"{kv.get('median_gap_s', 0)} | "
            f"{kv.get('p90_gap_s', 0)} | {kv.get('target_s', 0)} | "
            f"{kv.get('util_tpm_pct', 0)} | "
            f"{kv.get('mean_tokens', 0)} | "
            f"{kv.get('e429_count', 0)} | "
            f"{kv.get('derate_active', 0)} | "
            f"{kv.get('frame_slot_miss', 0)} | {flag.strip() or '—'} |\n")
    lines.append("\n")
    return "".join(lines)


def _chunker_v3_stats_section(records: list[dict[str, Any]]) -> str:
    """[CHUNKER-V3-STATS] hit-rate timeline + fallback flagging."""
    rows = _decisions_by_tag(records, "CHUNKER-V3-STATS")
    if not rows:
        return ""
    lines = ["## V3 chunker hit rate (5-min windows)\n\n",
             "| # | resolved | none | fallback | mean dur s "
             "| mean diff s | drove cut % | flag |\n"
             "|---|----------|------|----------|-----------|"
             "-------------|-------------|------|\n"]
    for i, d in enumerate(rows, 1):
        kv = _parse_kv_payload(d.get("raw_message"))
        resolved = _i(kv, "resolved")
        none_ct = _i(kv, "none")
        fallback = _i(kv, "fallback")
        total = resolved + none_ct
        fallback_pct = (100.0 * fallback / total) if total > 0 else 0.0
        flag = "HIGH-FALLBACK" if fallback_pct > 30.0 else "—"
        lines.append(
            f"| {i} | {resolved} | {none_ct} | {fallback} | "
            f"{kv.get('mean_dur_s', 0)} | "
            f"{kv.get('mean_diff_s', 0)} | "
            f"{kv.get('drove_cut_pct', 0)} | {flag} |\n")
    lines.append("\n")
    return "".join(lines)


def _alarms_section(records: list[dict[str, Any]]) -> str:
    """ALARM-* tripwire fires, surfaced as a high-severity advisory.

    Walks every record/decision; emits one row per alarm fire with
    frame number, wall-clock timestamp, alarm tag, and the raw
    payload (all key=value tokens after the tag).
    """
    alarm_tags = {
        "ALARM-V3-FALLBACK-HIGH",
        "ALARM-OPEN-SCOUT-TPM-HIGH",
        "ALARM-V3-CONSECUTIVE-NONE",
    }
    fires: list[tuple[int, float | None, str, str]] = []
    for r in records:
        frame = int(r.get("frame") or 0)
        ts_wall = r.get("ts_wall")
        for d in (((r.get("scorer") or {}).get("decisions")) or []):
            tag = d.get("tag")
            if tag in alarm_tags:
                raw = d.get("raw_message") or ""
                _, _, payload = raw.partition("]")
                fires.append((frame, ts_wall, tag, payload.strip()))
    if not fires:
        return ""
    lines = [
        "## ALARMS DURING MATCH (high-severity advisory)\n\n",
        "| Frame | Wall ts | Alarm | Context |\n"
        "|-------|---------|-------|---------|\n",
    ]
    for frame, ts_wall, tag, payload in fires:
        ts_str = _fmt_ts(ts_wall) if ts_wall else "?"
        ctx = payload.replace("|", "\\|")
        if len(ctx) > 240:
            ctx = ctx[:237] + "..."
        lines.append(
            f"| F{frame} | {ts_str} | `{tag}` | {ctx} |\n")
    lines.append("\n")
    return "".join(lines)


def _clip_write_health_section(records: list[dict[str, Any]]) -> str:
    """[CLIP-WRITE-OK] / [CLIP-WRITE-FAIL] health roll-up.

    Always emits a one-line health summary when any CLIP-WRITE-* tag
    fired; appends a per-failure detail table when at least one
    failure occurred.  Threshold for ``high`` severity flag in the
    headline is fail_pct > 5%.
    """
    ok_rows = _decisions_by_tag(records, "CLIP-WRITE-OK")
    fail_rows = _decisions_by_tag(records, "CLIP-WRITE-FAIL")
    total = len(ok_rows) + len(fail_rows)
    if total == 0:
        return ""
    fail_pct = (100.0 * len(fail_rows) / total) if total > 0 else 0.0
    sev = "**HIGH**" if fail_pct > 5.0 else "ok"
    out = ["## Clip-write health\n\n",
           f"- Total cuts: **{total}** "
           f"({len(ok_rows)} OK, {len(fail_rows)} failed) — "
           f"fail rate {fail_pct:.1f}% [{sev}]\n\n"]
    if fail_rows:
        out.append(
            "| delivery_id | reason | source | span |\n"
            "|-------------|--------|--------|------|\n")
        for d in fail_rows:
            kv = _parse_kv_payload(d.get("raw_message"))
            out.append(
                f"| {kv.get('delivery_id', '?')} "
                f"| {kv.get('reason', '?')} "
                f"| {kv.get('source', '?')} "
                f"| {kv.get('span', '?')} |\n")
        out.append("\n")
    return "".join(out)


def _match_summary_section(records: list[dict[str, Any]]) -> str:
    """[MATCH-SUMMARY] one-line headline block."""
    rows = _decisions_by_tag(records, "MATCH-SUMMARY")
    if not rows:
        return ""
    kv = _parse_kv_payload(rows[-1].get("raw_message"))
    lines = ["## Match-end headline\n\n",
             f"- Duration: **{kv.get('duration_min', '?')} min**\n",
             f"- Events seen: **{kv.get('events_seen', '?')}** "
             f"(committed {kv.get('spans_committed', '?')}, "
             f"hit rate {kv.get('hit_rate', '?')}%)\n",
             f"- Scout calls: **{kv.get('scout_calls', '?')}** "
             f"(action {kv.get('scout_action_pct', '?')}%, "
             f"replay {kv.get('scout_replay_pct', '?')}%, "
             f"other {kv.get('scout_other_pct', '?')}%, "
             f"p50 {kv.get('scout_lat_p50_ms', '?')} ms)\n",
             f"- Loop: median gap **"
             f"{kv.get('loop_median_gap_s', '?')} s**, "
             f"429 total **{kv.get('loop_e429_total', '?')}**\n",
             f"- V3: resolved {kv.get('v3_resolved', '?')}, "
             f"none {kv.get('v3_none', '?')}, "
             f"fallback {kv.get('v3_fallback', '?')}, "
             f"drove cut {kv.get('v3_drove_cut_pct', '?')}%\n\n"]
    return "".join(lines)


def _latency_quantiles(records: list[dict[str, Any]]) -> dict[
        str, dict[str, int]]:
    by_stage: dict[str, list[int]] = collections.defaultdict(list)
    for r in records:
        lats = (r.get("lat_ms") or {})
        for k, v in lats.items():
            if isinstance(v, (int, float)):
                by_stage[k].append(int(v))
    out: dict[str, dict[str, int]] = {}
    for stage, vs in by_stage.items():
        if not vs:
            continue
        vs.sort()
        out[stage] = {
            "p50": int(statistics.median(vs)),
            "p95": int(vs[int(len(vs) * 0.95) - 1] if vs else 0),
            "p99": int(vs[int(len(vs) * 0.99) - 1] if vs else 0),
            "max": vs[-1],
            "n": len(vs),
        }
    return out


def _format_anomaly_block(a: Anomaly) -> str:
    return (
        f"### {a.id} — `{a.severity}` at frame {a.fired_at_frame}\n"
        f"- First evidence frame: {a.first_evidence_frame}\n"
        f"- Duration: {a.duration_frames} frames\n"
        f"- Verdict: {a.verdict}\n"
        f"- Evidence:\n```json\n"
        f"{json.dumps(a.evidence, indent=2, default=str)}\n```\n"
        f"- Trace pointer: `jq -c 'select(.frame >= "
        f"{max(a.first_evidence_frame - 2, 0)} and .frame <= "
        f"{a.fired_at_frame + 2})' <session>.jsonl`\n"
    )


def render_report(
    *,
    header: dict[str, Any],
    records: list[dict[str, Any]],
    fired: list[Anomaly],
    match_name: str | None,
    trace_path: str,
) -> str:
    bucketed = _bucketize(fired)
    histogram = _decision_histogram(records)
    timeline = _mode_timeline(records)
    lat = _latency_quantiles(records)

    started = header.get("started_ts_wall")
    ended = (records[-1].get("ts_wall")
             if records and records[-1].get("ts_wall") else None)
    duration_s = (int(ended - started)
                  if (started and ended) else None)
    err_n = len(bucketed.get("error", []))
    warn_n = len(bucketed.get("warn", []))
    info_n = len(bucketed.get("info", []))
    adv_n = len(bucketed.get("advisory", []))

    cadence = (
        f"{len(records) / duration_s:.2f} fps mean"
        if (duration_s and duration_s > 0)
        else "?"
    )
    out: list[str] = []
    out.append(f"# Match trace report — `{header.get('session', '?')}`\n")
    if match_name:
        out.append(f"**Match:** {match_name}\n")
    out.append(
        f"**Trace:** `{trace_path}` — {len(records)} records, "
        f"{_fmt_ts(started)} → {_fmt_ts(ended)} "
        f"(duration {duration_s}s, {cadence})\n")
    out.append(f"**Schema version:** {header.get('_schema_version')} "
               f"(reader: {TRACE_SCHEMA_VERSION})\n\n")

    # Live-monitoring v1 headline (always at the top when present).
    _match_block = _match_summary_section(records)
    if _match_block:
        out.append(_match_block)
    _clip_block = _clip_write_health_section(records)
    if _clip_block:
        out.append(_clip_block)

    _alarms_block = _alarms_section(records)
    if _alarms_block:
        out.append(_alarms_block)

    out.append("## Summary\n")
    decisions_total = sum(histogram.values())
    out.append(f"- Records: **{len(records)}**\n")
    out.append(f"- Decisions captured: **{decisions_total}** "
               f"({len(histogram)} distinct tags)\n")
    out.append(
        f"- Anomalies: **{err_n} error**, {warn_n} warn, "
        f"{info_n} info, {adv_n} advisory\n")
    if timeline:
        mode_counts = collections.Counter(m for _, _, m in timeline)
        out.append(f"- Mode windows: " +
                   ", ".join(f"{m}×{c}" for m, c in mode_counts.most_common()) +
                   "\n")
    out.append("\n")

    if bucketed.get("error"):
        out.append("## Errors (operator action required)\n\n")
        for a in sorted(bucketed["error"], key=lambda x: x.fired_at_frame):
            out.append(_format_anomaly_block(a))
            out.append("\n")
    if bucketed.get("warn"):
        out.append("## Warnings\n\n")
        for a in sorted(bucketed["warn"], key=lambda x: x.fired_at_frame):
            out.append(_format_anomaly_block(a))
            out.append("\n")
    if bucketed.get("info"):
        out.append("## Info\n\n")
        for a in sorted(bucketed["info"], key=lambda x: x.fired_at_frame):
            out.append(_format_anomaly_block(a))
            out.append("\n")
    if bucketed.get("advisory"):
        out.append("## Advisory (not counted toward errors/warnings — Q4)\n\n")
        for a in sorted(bucketed["advisory"],
                        key=lambda x: x.fired_at_frame):
            out.append(_format_anomaly_block(a))
            out.append("\n")

    # Live-monitoring v1 aggregate sections.
    for _section in (
            _retro_summary_section(records),
            _open_scout_stats_section(records),
            _open_scout_loop_stats_section(records),
            _chunker_v3_stats_section(records),
    ):
        if _section:
            out.append(_section)

    out.append("## Decision-tag histogram\n\n")
    out.append("| Tag | Count |\n|-----|-------|\n")
    for tag, count in list(histogram.items())[:60]:
        out.append(f"| `{tag}` | {count} |\n")
    if len(histogram) > 60:
        out.append(f"| _… {len(histogram) - 60} more …_ | |\n")
    out.append("\n")

    out.append("## Mode timeline (compressed)\n\n")
    for s, e, m in timeline[:120]:
        out.append(f"- F{s}–F{e}: **{m}**\n")
    if len(timeline) > 120:
        out.append(f"- _… {len(timeline) - 120} more transitions …_\n")
    out.append("\n")

    out.append("## Latency p50/p95/p99 (ms)\n\n")
    out.append("| Stage | p50 | p95 | p99 | max | n |\n"
               "|-------|-----|-----|-----|-----|---|\n")
    for stage, q in lat.items():
        out.append(f"| {stage} | {q['p50']} | {q['p95']} | {q['p99']} "
                   f"| {q['max']} | {q['n']} |\n")
    out.append("\n")

    out.append("## Trace pointer index\n\n")
    out.append("Each anomaly cites a frame range. To inspect:\n\n"
               "```\njq -c 'select(.frame >= START and .frame <= END)' "
               f"{trace_path}\n```\n")
    return "".join(out)


def annotate_trace(
    *,
    header: dict[str, Any],
    records: list[dict[str, Any]],
    by_frame: dict[int, list[Anomaly]],
    out_path: str,
) -> None:
    with open(out_path, "w", encoding="utf-8") as fp:
        fp.write(json.dumps(header, default=str) + "\n")
        for r in records:
            f = int(r.get("frame") or 0)
            anoms = by_frame.get(f) or []
            if anoms:
                r = dict(r)
                r["anomalies"] = [a.to_dict() for a in anoms]
            fp.write(json.dumps(r, default=str) + "\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("trace", help="path to <session>.jsonl(.gz)")
    p.add_argument("--report", required=True,
                   help="path to write Markdown report")
    p.add_argument("--annotate", default=None,
                   help="optional path to write JSONL with anomalies[] "
                        "field populated")
    p.add_argument("--match-name", default=None)
    args = p.parse_args(argv)

    try:
        header, records = read_trace(args.trace)
    except ValueError as e:
        print(f"[analyze_trace] schema/file error: {e}", file=sys.stderr)
        return 2
    fired, by_frame = evaluate(records)
    md = render_report(
        header=header, records=records, fired=fired,
        match_name=args.match_name, trace_path=args.trace,
    )
    os.makedirs(os.path.dirname(os.path.abspath(args.report)) or ".",
                exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as fp:
        fp.write(md)
    print(f"[analyze_trace] wrote {args.report} "
          f"({len(records)} records, {len(fired)} anomalies)")
    if args.annotate:
        annotate_trace(header=header, records=records,
                       by_frame=by_frame, out_path=args.annotate)
        print(f"[analyze_trace] wrote {args.annotate}")
    return 0 if not any(a.severity == "error" for a in fired) else 1


if __name__ == "__main__":
    raise SystemExit(main())
