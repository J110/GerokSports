#!/usr/bin/env python3
"""Combined-match stratified Scout corpus sampler with M-2 bucket coverage.

M-2 (``files/docs/scout_labeling_rubric_v1.md``): emit a bucket-coverage
report with each stratified sample.  For any bucket with pool>0 and
sampled=0, log ``[BUCKET-COVERAGE]`` on stderr unless the gap is explicitly
documented via ``--document-empty``.

Phase × innings buckets (T20 IPL default):
  powerplay = completed-over index 1–6, middle 7–15, death 16–20, using
  cricket over strings (e.g. ``14.5`` → 15th over segment).

Innings: derived from ``events`` in each inventory when ``ball_event_over``
resets after a high-over segment (same heuristic as manual review: large
backward jump in parsed over).

Existing ``corpus_frame_inventory.json`` does not store innings; this module
recomputes nearest ball event per frame and assigns phase_bucket without
changing the inventory schema.

Output: corpus JSON aligned with ``docs/scout_corpus_v1.json`` field names
for downstream tools; ``phase_bucket`` and ``metadata`` are additive.
``run_shadow.py`` only requires ``frame_id`` and ``path`` on each frame.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from datetime import date
from pathlib import Path

# Fixed bucket order for stable reports.
PHASE_BUCKETS: tuple[str, ...] = (
    "powerplay_inn1",
    "middle_inn1",
    "death_inn1",
    "powerplay_inn2",
    "middle_inn2",
    "death_inn2",
)


def parse_ball_over(over: str | None) -> float | None:
    """Parse ``ball_event_over`` string to a monotonic float for ordering.

    Returns None for em-dashes, ``?``, or empty.
    """
    if over is None:
        return None
    s = str(over).strip()
    if not s or s in ("\u2014", "—", "?"):
        return None
    m = re.match(r"^(\d+)\.(\d+)$", s)
    if not m:
        try:
            return float(s)
        except ValueError:
            return None
    whole = int(m.group(1))
    ball = int(m.group(2))
    return float(whole) + min(ball, 6) / 10.0


def t20_match_phase(over_f: float | None) -> str | None:
    """Map ball position to powerplay | middle | death (1-based over index)."""
    if over_f is None:
        return None
    whole = int(over_f)
    over_index = whole + 1  # 0.4 → 1st over, 14.5 → 15th over
    if over_index <= 6:
        return "powerplay"
    if over_index <= 15:
        return "middle"
    return "death"


def assign_event_innings(events: list[dict]) -> dict[int, int]:
    """Map each event's frame_count to innings (1, 2, …) from over resets."""
    sorted_e = sorted(events, key=lambda e: e["frame_count"])
    innings = 1
    prev_of: float | None = None
    frame_to_innings: dict[int, int] = {}
    for ev in sorted_e:
        of = parse_ball_over(ev.get("over"))
        if of is not None and prev_of is not None and of < prev_of - 4.0:
            innings += 1
        frame_to_innings[ev["frame_count"]] = innings
        if of is not None:
            prev_of = of
    return frame_to_innings


def nearest_event_for_frame(
        frame_fc: int,
        events: list[dict],
) -> dict | None:
    """Pick nearest ball-event row with a parsable ``over``."""
    usable = [
        e for e in events
        if parse_ball_over(e.get("over")) is not None
    ]
    if not usable:
        return None
    return min(usable, key=lambda e: abs(e["frame_count"] - frame_fc))


def phase_bucket_for_frame(
        frame_fc: int,
        events: list[dict],
        frame_to_innings: dict[int, int],
) -> str | None:
    ev = nearest_event_for_frame(frame_fc, events)
    if ev is None:
        return None
    inn = frame_to_innings.get(ev["frame_count"])
    if inn is None:
        return None
    if inn not in (1, 2):
        return None
    ph = t20_match_phase(parse_ball_over(ev.get("over")))
    if ph is None:
        return None
    return f"{ph}_inn{inn}"


def load_merged_inventories(paths: list[Path]) -> list[dict]:
    """Load inventories; each frame gains ``_match_id`` for dedupe."""
    rows: list[dict] = []
    for p in paths:
        inv = json.loads(p.read_text(encoding="utf-8"))
        match_id = inv.get("match_id") or p.stem
        for fr in inv.get("frames", []):
            rec = dict(fr)
            rec["_match_id"] = str(match_id)
            rec["_source_inventory"] = str(p)
            rows.append(rec)
    return rows


def build_bucket_coverage(
        targets: dict[str, int],
        pool_counts: dict[str, int],
        sampled_counts: dict[str, int],
        documented_empty: dict[str, str],
) -> list[dict]:
    out: list[dict] = []
    for bucket in PHASE_BUCKETS:
        target = targets[bucket]
        pool = pool_counts.get(bucket, 0)
        sampled = sampled_counts.get(bucket, 0)
        reason = ""
        status = "OK"
        if pool > 0 and sampled == 0:
            if bucket in documented_empty:
                status = "OK"
                reason = f"documented_empty={documented_empty[bucket]}"
            else:
                status = "UNDOCUMENTED_ZERO"
                reason = f"pool={pool}, sampled=0"
        elif pool > 0 and sampled < min(pool, target):
            status = "WARN"
            reason = f"pool={pool}, sampled={sampled}, target={target}"
        entry = {
            "bucket": bucket,
            "pool": pool,
            "sampled": sampled,
            "target": target,
            "status": status,
            "reason": reason,
        }
        out.append(entry)
    return out


def _emit_stderr_warnings(coverage: list[dict]) -> None:
    for row in coverage:
        if row["status"] == "OK":
            continue
        b = row["bucket"]
        tag = "[BUCKET-COVERAGE]"
        if row["status"] == "UNDOCUMENTED_ZERO":
            print(
                f"{tag} UNDOCUMENTED_ZERO {b}: {row['reason']}",
                file=sys.stderr,
            )
        else:
            print(
                f"{tag} WARN {b}: {row['reason']}",
                file=sys.stderr,
            )


def select_combined_corpus(
        *,
        frames: list[dict],
        events_by_match: dict[str, list[dict]],
        target_per_bucket: int,
        seed: int,
        documented_empty: dict[str, str],
) -> tuple[list[dict], list[dict], dict[str, int], dict[str, int]]:
    """Return (output_frames, bucket_coverage, pool_counts, sampled_counts)."""
    rng = random.Random(seed)
    targets = {b: target_per_bucket for b in PHASE_BUCKETS}

    # Eligible: SCOREBOARD only (same signal as select_corpus_candidates).
    eligible: list[dict] = []
    pool_counts: dict[str, int] = {b: 0 for b in PHASE_BUCKETS}
    for fr in frames:
        if fr.get("scout_frame_type") != "SCOREBOARD":
            continue
        mid = fr["_match_id"]
        evs = events_by_match.get(mid, [])
        if not evs:
            continue
        fti = assign_event_innings(evs)
        pb = phase_bucket_for_frame(fr["frame_count"], evs, fti)
        if pb is None or pb not in PHASE_BUCKETS:
            continue
        pool_counts[pb] += 1
        eligible.append({**fr, "_phase_bucket": pb})

    by_bucket: dict[str, list[dict]] = {b: [] for b in PHASE_BUCKETS}
    for fr in eligible:
        by_bucket[fr["_phase_bucket"]].append(fr)

    picked: list[dict] = []
    sampled_counts: dict[str, int] = {b: 0 for b in PHASE_BUCKETS}
    for b in PHASE_BUCKETS:
        pool = list(by_bucket[b])
        rng.shuffle(pool)
        n = min(target_per_bucket, len(pool))
        for fr in pool[:n]:
            picked.append(fr)
            sampled_counts[b] += 1

    coverage = build_bucket_coverage(
        targets, pool_counts, sampled_counts, documented_empty)

    out_frames: list[dict] = []
    for fr in sorted(
            picked,
            key=lambda x: (x["_match_id"], x["frame_count"]),
    ):
        fc = fr["frame_count"]
        pb = fr["_phase_bucket"]
        rationale = (
            f"combined stratified M-2; phase_bucket={pb}; match={fr['_match_id']}; "
            f"scout={fr.get('scout_cam')}/{fr.get('scout_phase')}"
        )
        # path: relative to files/ (run_shadow resolves under files/)
        rel_path = fr["frame_path"].replace("\\", "/")
        out_frames.append({
            "frame_id": f"f{fc:03d}",
            "frame_count": fc,
            "path": rel_path,
            "subset": "combined_stratified",
            "phase_bucket": pb,
            "match_id": fr["_match_id"],
            "selection_rationale": rationale,
            "scout_cam_original": fr.get("scout_cam"),
            "scout_phase_original": fr.get("scout_phase"),
            "human_camera_view": "pending",
            "human_frame_phase": "pending",
            "confidence": "pending",
            "notes": "",
        })

    return out_frames, coverage, pool_counts, sampled_counts


def run_cli(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Stratified combined Scout corpus over phase×innings buckets (M-2). "
            "T20 defaults: powerplay overs 1–6, middle 7–15, death 16–20; "
            f"buckets: {', '.join(PHASE_BUCKETS)}."
        ),
    )
    ap.add_argument(
        "--inventory",
        action="append",
        dest="inventories",
        metavar="PATH",
        required=True,
        help="Inventory JSON (repeat for multiple matches).",
    )
    ap.add_argument(
        "--output",
        required=True,
        help="Output corpus JSON path.",
    )
    ap.add_argument(
        "--target-per-bucket",
        type=int,
        default=8,
        help="Target sample size per phase×innings bucket (default: 8).",
    )
    ap.add_argument(
        "--seed",
        type=int,
        default=42,
        help="RNG seed for reproducible sampling (default: 42).",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 2 if any bucket is WARN or UNDOCUMENTED_ZERO.",
    )
    ap.add_argument(
        "--document-empty",
        action="append",
        default=None,
        metavar="BUCKET:REASON",
        help="Mark a bucket as intentionally empty (repeatable).",
    )
    args = ap.parse_args(argv)
    doc_items = args.document_empty or []

    documented: dict[str, str] = {}
    for item in doc_items:
        if ":" not in item:
            print("ERROR: --document-empty must be BUCKET:REASON", file=sys.stderr)
            return 2
        k, v = item.split(":", 1)
        documented[k.strip()] = v.strip()

    paths = [Path(p) for p in args.inventories]
    merged = load_merged_inventories(paths)
    events_by_match: dict[str, list[dict]] = {}
    for p in paths:
        inv = json.loads(Path(p).read_text(encoding="utf-8"))
        mid = str(inv.get("match_id") or Path(p).stem)
        events_by_match[mid] = list(inv.get("events", []))

    out_fr, coverage, pool_counts, _ = select_combined_corpus(
        frames=merged,
        events_by_match=events_by_match,
        target_per_bucket=args.target_per_bucket,
        seed=args.seed,
        documented_empty=documented,
    )

    _emit_stderr_warnings(coverage)

    bad = [r for r in coverage if r["status"] != "OK"]

    source_log = "; ".join(str(x) for x in sorted(paths))
    envelope = {
        "version": "v1_combined_sampler",
        "created": str(date.today()),
        "revision_log": [{
            "date": str(date.today()),
            "change": "Combined stratified corpus (phase×innings M-2).",
        }],
        "source_log": source_log,
        "labeling_rubric": "files/docs/scout_labeling_rubric_v1.md",
        "labeler": "pending",
        "selection_method": "combined stratified phase×innings (M-2, T20)",
        "labeling_method": "pending human pass",
        "total_frames": len(out_fr),
        "subset_targets": {
            "combined_stratified": args.target_per_bucket * len(PHASE_BUCKETS),
        },
        "metadata": {
            "sampler": "scripts/select_combined_scout_corpus.py",
            "seed": args.seed,
            "target_per_bucket": args.target_per_bucket,
            "t20_phase_rules": (
                "powerplay: overs 1–6; middle: 7–15; death: 16–20 (segment from "
                "ball_event_over)"
            ),
            "inventories": [str(p) for p in paths],
            "bucket_coverage": coverage,
            "pool_counts_by_bucket": pool_counts,
        },
        "frames": out_fr,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(envelope, f, indent=2, sort_keys=True)
    print(f"Wrote {out_path} ({len(out_fr)} frames)", file=sys.stderr)
    if args.strict and bad:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
