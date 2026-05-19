#!/usr/bin/env python3
"""
Δballs distribution analysis across captured trace files.

Walks logs/trace/*.jsonl, computes per-session frame-to-frame Δballs
between consecutive SCOREBOARD frames where overs is parseable, and
groups by Δballs value + frame context (cold-start, overlay,
steady-state). Tracks whether each gap was eventually resolved by
subsequent reads.

Output: TSV summary to stdout + per-event detail JSONL to optional
--detail-out path.
"""

import argparse
import collections
import json
import math
import pathlib
import re
import sys


OVERS_RE = re.compile(r"^(\d+)\.([0-9])$")


def parse_overs(v):
    """Return total legal balls (over*6 + ball) or None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        if not math.isfinite(f) or f < 0:
            return None
        whole = int(f)
        frac = round((f - whole) * 10)
        if frac < 0 or frac > 9:
            return None
        return whole * 6 + frac
    if isinstance(v, str):
        m = OVERS_RE.match(v.strip())
        if not m:
            try:
                return parse_overs(float(v))
            except ValueError:
                return None
        return int(m.group(1)) * 6 + int(m.group(2))
    return None


def frame_context(rec, frame_idx_in_session):
    pipe = rec.get("pipeline") or {}
    if pipe.get("cold_start_gate") == "CLOSED" or frame_idx_in_session < 5:
        return "cold_start"
    if pipe.get("overlay_window_active"):
        return "overlay"
    if pipe.get("inset_suspected"):
        return "inset_suspected"
    return "steady_state"


def extract_overs(rec):
    ext = rec.get("extractor") or {}
    v = ext.get("match_overs")
    parsed = parse_overs(v)
    if parsed is not None:
        return parsed
    sc = rec.get("scorer") or {}
    prop = sc.get("proposed") or {}
    return parse_overs(prop.get("overs"))


def innings_of(rec):
    pipe = rec.get("pipeline") or {}
    return pipe.get("innings")


def analyze_file(path: pathlib.Path):
    events = []
    prev_legal = None
    prev_innings = None
    frame_idx = 0
    total_transitions = 0
    scoreboard_frames = 0

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("_schema_version") is not None and rec.get("frame") is None:
                continue
            frame_idx = rec.get("frame", frame_idx + 1)
            if rec.get("frame_type") != "SCOREBOARD":
                continue
            scoreboard_frames += 1
            legal = extract_overs(rec)
            inn = innings_of(rec)
            if legal is None:
                continue
            if prev_legal is None or prev_innings != inn:
                prev_legal = legal
                prev_innings = inn
                continue
            d = legal - prev_legal
            total_transitions += 1
            ctx = frame_context(rec, frame_idx)
            events.append({
                "session": path.stem,
                "frame": frame_idx,
                "prev_legal": prev_legal,
                "curr_legal": legal,
                "delta": d,
                "context": ctx,
                "innings": inn,
            })
            prev_legal = legal
            prev_innings = inn
    return events, total_transitions, scoreboard_frames


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace-dir", default="logs/trace")
    ap.add_argument("--detail-out", default=None)
    ap.add_argument("--min-frames", type=int, default=20,
                    help="Skip sessions with fewer than this many SCOREBOARD frames (likely incomplete)")
    args = ap.parse_args()

    trace_dir = pathlib.Path(args.trace_dir)
    files = sorted(trace_dir.glob("*.jsonl"))
    if not files:
        print(f"no jsonl files in {trace_dir}", file=sys.stderr)
        sys.exit(1)

    all_events = []
    total_transitions = 0
    total_scoreboard = 0
    skipped_sessions = 0
    per_session_stats = []

    for fp in files:
        events, ntrans, nsb = analyze_file(fp)
        if nsb < args.min_frames:
            skipped_sessions += 1
            continue
        all_events.extend(events)
        total_transitions += ntrans
        total_scoreboard += nsb
        per_session_stats.append((fp.stem, nsb, ntrans, len([e for e in events if e["delta"] >= 2])))

    by_delta = collections.Counter(e["delta"] for e in all_events)
    by_delta_ctx = collections.Counter((e["delta"], e["context"]) for e in all_events)

    gaps = [e for e in all_events if e["delta"] >= 2]
    by_gap_bucket = collections.Counter()
    by_gap_bucket_ctx = collections.defaultdict(collections.Counter)
    for e in gaps:
        bucket = "2" if e["delta"] == 2 else "3" if e["delta"] == 3 else "4+"
        by_gap_bucket[bucket] += 1
        by_gap_bucket_ctx[bucket][e["context"]] += 1

    print("=" * 72)
    print("Δballs DISTRIBUTION (frame-to-frame, consecutive SCOREBOARD reads)")
    print("=" * 72)
    print(f"sessions analyzed: {len(files) - skipped_sessions} (skipped {skipped_sessions} with <{args.min_frames} frames)")
    print(f"total SCOREBOARD frames: {total_scoreboard}")
    print(f"total transitions (consecutive same-innings pairs w/ parseable overs): {total_transitions}")
    print()
    print(f"{'Δballs':<10} {'count':>8} {'pct':>8}")
    print("-" * 28)
    pct_total = sum(by_delta.values())
    for d in sorted(by_delta.keys()):
        c = by_delta[d]
        pct = 100.0 * c / pct_total if pct_total else 0.0
        marker = "  ← negative (regression)" if d < 0 else ""
        print(f"{d:<10} {c:>8} {pct:>7.2f}%{marker}")
    print()
    print("GAP EVENTS (Δballs ≥ 2) by bucket × context")
    print("-" * 60)
    print(f"{'bucket':<6} {'context':<18} {'count':>8} {'pct_of_total':>14}")
    for bucket in ("2", "3", "4+"):
        for ctx in ("cold_start", "overlay", "inset_suspected", "steady_state"):
            c = by_gap_bucket_ctx[bucket][ctx]
            if c == 0:
                continue
            pct = 100.0 * c / pct_total if pct_total else 0.0
            print(f"{bucket:<6} {ctx:<18} {c:>8} {pct:>13.4f}%")
    print()
    total_gaps = sum(by_gap_bucket.values())
    gap_pct = 100.0 * total_gaps / pct_total if pct_total else 0.0
    print(f"TOTAL Δballs ≥ 2: {total_gaps}  ({gap_pct:.3f}% of all transitions)")
    print()

    print("Resolution check: did the over-count eventually catch up within next N frames?")
    print("-" * 60)
    sessions = collections.defaultdict(list)
    for e in all_events:
        sessions[e["session"]].append(e)
    resolved_within = collections.Counter()
    unresolved_at_session_end = 0
    for sid, evs in sessions.items():
        for i, e in enumerate(evs):
            if e["delta"] < 2:
                continue
            future = evs[i + 1: i + 1 + 30]
            if not future:
                unresolved_at_session_end += 1
                continue
            ok = any(fe["delta"] in (0, 1) for fe in future[:5])
            if ok:
                resolved_within["≤5 frames"] += 1
            elif any(fe["delta"] in (0, 1) for fe in future[:15]):
                resolved_within["6-15 frames"] += 1
            elif any(fe["delta"] in (0, 1) for fe in future):
                resolved_within["16-30 frames"] += 1
            else:
                resolved_within["unresolved >30"] += 1
    for k in ("≤5 frames", "6-15 frames", "16-30 frames", "unresolved >30"):
        c = resolved_within.get(k, 0)
        pct = 100.0 * c / total_gaps if total_gaps else 0.0
        print(f"  {k:<20} {c:>8} {pct:>7.2f}% of gaps")
    if unresolved_at_session_end:
        print(f"  (gaps at session end without follow-up: {unresolved_at_session_end})")

    if args.detail_out:
        with open(args.detail_out, "w") as out:
            for e in gaps:
                out.write(json.dumps(e) + "\n")
        print(f"\nper-gap detail written to {args.detail_out}")


if __name__ == "__main__":
    main()
