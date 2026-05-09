#!/usr/bin/env python3
"""Filter 70b 'found' deliveries vs kept-cluster anchors. Tag each as
DUPLICATE_DRIFT (≤10s from a kept anchor) or GENUINE_NOVEL (>10s).
Print high-confidence novels to stage1_70b_novel.md."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCOUT_BASE = REPO_ROOT / "files/scripts/broadcast_mode_tuning"
RESULTS = SCOUT_BASE / "stage1_70b_results.json"
REPORT = SCOUT_BASE / "predicted_clips_3600/pipeline_report.md"
OUT = SCOUT_BASE / "stage1_70b_novel.md"

SIDECAR_DIRS = [SCOUT_BASE / d for d in [
    "first_5min_scout_run", "second_5min_scout_run",
    "third_5min_scout_run", "fourth_5min_scout_run",
    "fifth_5min_scout_run", "sixth_5min_scout_run",
    "seventh_5min_scout_run", "eighth_5min_scout_run",
    "ninth_5min_scout_run", "tenth_5min_scout_run",
    "eleventh_5min_scout_run", "twelfth_5min_scout_run",
]]


def parse_anchors(report_path: Path) -> list[tuple[int, float]]:
    import re
    out = []
    for m in re.finditer(
        r"\|\s*(\d+)\s*\|\s*t=([\d.]+)s\s*\|\s*\w+\s*\|", report_path.read_text()):
        out.append((int(m.group(1)), float(m.group(2))))
    return out


def gather_prose(start_t: float, end_t: float) -> list[tuple[float, str]]:
    out: list[tuple[float, str]] = []
    seen: set[float] = set()
    for d in SIDECAR_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.glob("*.txt")):
            try:
                t = float(p.stem.split("_t=")[1])
            except (IndexError, ValueError):
                continue
            if t < start_t or t > end_t or t in seen:
                continue
            seen.add(t)
            raw = p.read_text()
            text = raw.split("---\n", 1)[1].strip() if "---\n" in raw else raw
            out.append((t, text.replace("\n", " ").strip()))
    out.sort()
    return out


def main() -> int:
    data = json.loads(RESULTS.read_text())
    found = data["diff"]["found"]
    anchors = parse_anchors(REPORT)

    classified: list[dict] = []
    for d in found:
        try:
            st = float(d.get("start_t", 0) or 0)
            ed = float(d.get("end_t", st) or st)
        except (TypeError, ValueError):
            continue
        mid = (st + ed) / 2
        nearest_dist = float("inf")
        nearest_idx = None
        nearest_anchor = None
        for idx, at in anchors:
            dist = min(abs(mid - at), abs(st - at), abs(ed - at))
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_idx = idx
                nearest_anchor = at
        tag = "DUPLICATE_DRIFT" if nearest_dist <= 10.0 else "GENUINE_NOVEL"
        classified.append({
            "tag": tag,
            "start_t": st,
            "end_t": ed,
            "confidence": float(d.get("confidence", 0) or 0),
            "outcome": d.get("outcome", "?"),
            "evidence": d.get("evidence", ""),
            "nearest_idx": nearest_idx,
            "nearest_anchor": nearest_anchor,
            "nearest_dist": nearest_dist,
        })

    n_dup = sum(1 for c in classified if c["tag"] == "DUPLICATE_DRIFT")
    n_nov = sum(1 for c in classified if c["tag"] == "GENUINE_NOVEL")
    high_novels = sorted(
        [c for c in classified
         if c["tag"] == "GENUINE_NOVEL" and c["confidence"] >= 0.7],
        key=lambda c: c["start_t"])

    md: list[str] = []
    md.append("# Stage 1 70b — genuine-novel filter\n\n")
    md.append(f"Found total: **{len(classified)}** "
              f"(DUPLICATE_DRIFT: {n_dup}, GENUINE_NOVEL: {n_nov})\n")
    md.append(f"Surfaced (GENUINE_NOVEL with conf >= 0.7): "
              f"**{len(high_novels)}**\n\n")

    md.append("## High-confidence genuine novels\n")
    if not high_novels:
        md.append("(none)\n")
    for c in high_novels:
        md.append(f"\n### t={c['start_t']:.1f}-{c['end_t']:.1f}s  "
                  f"conf={c['confidence']} outcome={c['outcome']}\n")
        md.append(f"- 70b evidence: {c['evidence']}\n")
        md.append(f"- nearest kept cluster: c{c['nearest_idx']} "
                  f"(anchor t={c['nearest_anchor']:.1f}s, "
                  f"dist={c['nearest_dist']:.1f}s)\n")
        md.append(f"- frame prose excerpt:\n")
        prose = gather_prose(c["start_t"] - 1, c["end_t"] + 1)
        for t, p in prose:
            md.append(f"    - [t={t:.1f}] {p[:240]}"
                      + ("..." if len(p) > 240 else "") + "\n")

    md.append("\n## All classifications (summary)\n")
    md.append("| start | end | conf | outcome | tag | nearest_c | dist |\n")
    md.append("|---|---|---|---|---|---|---|\n")
    for c in sorted(classified, key=lambda c: c["start_t"]):
        md.append(f"| {c['start_t']} | {c['end_t']} | {c['confidence']} | "
                  f"{c['outcome']} | {c['tag']} | c{c['nearest_idx']} | "
                  f"{c['nearest_dist']:.1f} |\n")

    OUT.write_text("".join(md))
    print(f"Total found: {len(classified)} "
          f"(dup={n_dup}, novel={n_nov}, surfaced={len(high_novels)})")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
