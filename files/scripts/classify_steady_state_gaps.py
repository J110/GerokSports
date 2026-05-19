#!/usr/bin/env python3
"""Root-cause classification of steady-state Δ≥2 gap events.

Per memo §9 stage 3: sample 20-30 of the audit's 114 steady-state
Δ=2-12 events, walk each session's trace, classify the intermediate
frames between gap-start and gap-end into one of:

  (a) scout_cadence_drop     — no intermediate frame at all
  (b) frame_filter_reject    — intermediate frames classified non-SCOREBOARD
  (c) extractor_reject       — SCOREBOARD frames with rejection decisions
  (d) ocr_miss               — SCOREBOARD frames with null match_overs
  (e) measurement_artifact   — overs regressed/snapped between commits

Report breakdown + sample annotations for the top-5 dominant classes.
"""
from __future__ import annotations

import collections
import json
import pathlib
import random
import re


ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
TRACE_DIR = ROOT / "logs" / "trace"
GAPS_PATH = pathlib.Path("/tmp/delta_balls_gaps.jsonl")
OUT_PATH = pathlib.Path("/tmp/steady_state_gap_classification.jsonl")

OVERS_RE = re.compile(r"^(\d+)\.([0-9])$")


def parse_overs_to_legal(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        whole = int(f)
        frac = round((f - whole) * 10)
        return whole * 6 + frac if 0 <= frac <= 9 else None
    if isinstance(v, str):
        m = OVERS_RE.match(v.strip())
        if not m:
            try:
                return parse_overs_to_legal(float(v))
            except ValueError:
                return None
        return int(m.group(1)) * 6 + int(m.group(2))
    return None


def load_trace_records(session: str) -> list[dict]:
    p = TRACE_DIR / f"{session}.jsonl"
    if not p.exists():
        return []
    out = []
    with p.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("frame") is None:
                continue
            out.append(rec)
    return out


REJECT_TAGS = {
    "OVERS-JUMP-IMPLAUSIBLE-REJECTED",
    "STRIP-ROW-NAME-MISMATCH",
    "GAP-AT-REJECTION",
    "SM-DRIFT-GUARD",
    "Overs rejected",  # SB-side, sometimes in raw_message
    "Score rejected",
    "SCORE-CAP-SUPPRESS-NARROW",
    "CORRECTION_BLOCKED",
}


def has_rejection_decision(rec: dict) -> tuple[bool, list[str]]:
    decisions = (rec.get("scorer") or {}).get("decisions") or []
    hits = []
    for d in decisions:
        tag = d.get("tag", "")
        msg = d.get("raw_message", "")
        for rt in REJECT_TAGS:
            if rt in tag or rt in msg:
                hits.append(rt)
                break
    return (len(hits) > 0, hits)


def classify_gap(
    trace: list[dict], gap_end_frame: int, prev_legal: int,
    curr_legal: int,
) -> dict:
    end_idx = None
    for i, rec in enumerate(trace):
        if int(rec.get("frame", -1)) == gap_end_frame:
            end_idx = i
            break
    if end_idx is None:
        return {"class": "trace_lookup_failed",
                "reason": "gap_end frame not in trace"}

    start_idx = None
    for j in range(end_idx - 1, -1, -1):
        ext = (trace[j].get("extractor") or {})
        legal = parse_overs_to_legal(ext.get("match_overs"))
        ft = trace[j].get("frame_type")
        if ft == "SCOREBOARD" and legal == prev_legal:
            start_idx = j
            break
        if ft == "SCOREBOARD" and legal is not None and legal < prev_legal:
            break
    if start_idx is None:
        return {"class": "trace_lookup_failed",
                "reason": "gap_start prev_legal not found before end_idx"}

    intermediate = trace[start_idx + 1: end_idx]
    n_intermediate = len(intermediate)

    if n_intermediate == 0:
        return {
            "class": "scout_cadence_drop",
            "reason": "no intermediate trace frame between commits",
            "n_intermediate": 0,
        }

    by_frame_type = collections.Counter()
    sb_with_overs = 0
    sb_no_overs = 0
    sb_overs_in_between = 0
    rejection_count = 0
    rejection_tags: list[str] = []
    sample_details = []

    for rec in intermediate:
        ft = rec.get("frame_type") or "UNKNOWN"
        by_frame_type[ft] += 1
        ext = rec.get("extractor") or {}
        legal = parse_overs_to_legal(ext.get("match_overs"))
        rejected, hits = has_rejection_decision(rec)
        if rejected:
            rejection_count += 1
            rejection_tags.extend(hits)
        if ft == "SCOREBOARD":
            if legal is None:
                sb_no_overs += 1
            else:
                sb_with_overs += 1
                if prev_legal < legal < curr_legal:
                    sb_overs_in_between += 1
        sample_details.append({
            "frame": rec.get("frame"),
            "frame_type": ft,
            "match_overs": ext.get("match_overs"),
            "rejected": rejected,
            "reject_hits": list(set(hits))[:3],
        })

    # Classify
    if sb_overs_in_between >= 1:
        klass = "measurement_artifact"
        reason = (f"intermediate SCOREBOARD frame had overs between "
                  f"prev={prev_legal} and curr={curr_legal}")
    elif rejection_count >= max(1, n_intermediate // 2):
        klass = "extractor_reject"
        reason = (f"{rejection_count}/{n_intermediate} intermediate "
                  f"frames had rejection decisions")
    elif sb_with_overs >= 1 and sb_no_overs == 0 and rejection_count == 0:
        klass = "scout_cadence_drop_intermediate_clean"
        reason = (f"SCOREBOARD intermediate frames were clean but "
                  f"didn't capture the missing ball cleanly")
    elif sb_no_overs >= 1:
        klass = "ocr_miss"
        reason = (f"{sb_no_overs}/{n_intermediate} SCOREBOARD frames "
                  f"had null match_overs")
    elif by_frame_type.get("SCOREBOARD", 0) == 0:
        klass = "frame_filter_reject"
        reason = (f"0 SCOREBOARD frames in {n_intermediate} "
                  f"intermediate; "
                  f"types: {dict(by_frame_type)}")
    else:
        klass = "mixed_unclassified"
        reason = (f"mixed signals: "
                  f"sb_with_overs={sb_with_overs}, "
                  f"sb_no_overs={sb_no_overs}, "
                  f"rejection={rejection_count}, "
                  f"types={dict(by_frame_type)}")

    return {
        "class": klass,
        "reason": reason,
        "n_intermediate": n_intermediate,
        "by_frame_type": dict(by_frame_type),
        "sb_with_overs": sb_with_overs,
        "sb_no_overs": sb_no_overs,
        "sb_overs_in_between": sb_overs_in_between,
        "rejection_count": rejection_count,
        "rejection_tags": list(set(rejection_tags)),
        "sample_intermediate": sample_details[:5],
    }


def main():
    with GAPS_PATH.open() as fh:
        all_gaps = [json.loads(l) for l in fh if l.strip()]
    candidates = [
        g for g in all_gaps
        if g["context"] == "steady_state" and 2 <= g["delta"] <= 12
    ]
    print(f"Total steady-state Δ=2-12 events: {len(candidates)}")

    random.seed(42)
    # Stratify by Δ value to make sample representative
    by_delta = collections.defaultdict(list)
    for g in candidates:
        by_delta[g["delta"]].append(g)
    sample = []
    target = 25
    per_bucket = max(1, target // len(by_delta))
    for d, evs in sorted(by_delta.items()):
        k = min(len(evs), per_bucket + (1 if d <= 4 else 0))
        sample.extend(random.sample(evs, k))
    print(f"Sampled {len(sample)} events (stratified by Δ)")

    results = []
    failed_lookups = 0
    for ev in sample:
        session = ev["session"]
        trace = load_trace_records(session)
        if not trace:
            failed_lookups += 1
            continue
        cls = classify_gap(
            trace,
            gap_end_frame=ev["frame"],
            prev_legal=ev["prev_legal"],
            curr_legal=ev["curr_legal"],
        )
        results.append({
            "session": session,
            "gap_end_frame": ev["frame"],
            "delta": ev["delta"],
            "prev_overs": (
                f"{ev['prev_legal']//6}.{ev['prev_legal']%6}"),
            "new_overs": (
                f"{ev['curr_legal']//6}.{ev['curr_legal']%6}"),
            "classification": cls,
        })

    # Aggregate
    by_class = collections.Counter(r["classification"]["class"] for r in results)
    by_delta_class = collections.Counter(
        (r["delta"], r["classification"]["class"]) for r in results)

    print()
    print("=" * 70)
    print("ROOT-CAUSE CLASSIFICATION")
    print("=" * 70)
    print(f"Sample size: {len(results)} (skipped {failed_lookups} no-trace)")
    print()
    print(f"{'Class':<40} {'Count':>6} {'%':>6}")
    print("-" * 56)
    total = len(results) if results else 1
    for klass, c in by_class.most_common():
        print(f"{klass:<40} {c:>6} {100*c/total:>5.1f}%")
    print()

    print("Δ × class breakdown:")
    print(f"{'Δ':<4} {'class':<40} {'count':>5}")
    for (d, k), c in sorted(by_delta_class.items()):
        print(f"{d:<4} {k:<40} {c:>5}")
    print()

    # Sample annotations per class (up to 3 per class)
    print("=" * 70)
    print("REPRESENTATIVE SAMPLES PER CLASS")
    print("=" * 70)
    by_class_samples = collections.defaultdict(list)
    for r in results:
        by_class_samples[r["classification"]["class"]].append(r)
    for klass, samples in sorted(by_class_samples.items()):
        print(f"\n--- class: {klass} ({len(samples)} total) ---")
        for s in samples[:3]:
            c = s["classification"]
            print(
                f"  session={s['session']:<32} "
                f"frame={s['gap_end_frame']:>4} "
                f"Δ={s['delta']} "
                f"{s['prev_overs']}→{s['new_overs']}")
            print(f"    reason: {c.get('reason')}")
            if c.get("sample_intermediate"):
                for si in c["sample_intermediate"][:3]:
                    print(
                        f"    intermediate frame={si.get('frame')} "
                        f"type={si.get('frame_type')} "
                        f"overs={si.get('match_overs')!r} "
                        f"rejected={si.get('rejected')} "
                        f"{si.get('reject_hits') or ''}")

    OUT_PATH.write_text("\n".join(
        json.dumps(r, default=str) for r in results))
    print()
    print(f"per-case detail at {OUT_PATH}")


if __name__ == "__main__":
    main()
