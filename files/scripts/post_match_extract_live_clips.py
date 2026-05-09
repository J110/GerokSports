#!/usr/bin/env python3
"""Post-match: read live_decision_log.jsonl, ffmpeg-cut trimmed clips
from the completed match.mp4 using the live-decided cluster anchors
+ trim logic (anchor-centered head/tail walk on the buffered prose
that was emitted to the decision log)."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCOUT_BASE = REPO_ROOT / "files/scripts/broadcast_mode_tuning"
sys.path.insert(0, str(SCOUT_BASE))

from signal_extraction import (  # noqa: E402
    v_match, v_post_match, hard_match,
)
from delivery_classifier import strong_post_action_match  # noqa: E402

# Re-use trim logic by importing the script's helpers.
sys.path.insert(0, str(REPO_ROOT / "files/scripts/broadcast_mode_tuning"))
import trim_delivery_clips as _trim  # noqa: E402


@dataclass
class LiveCluster:
    cluster_id: int
    start_t: float
    end_t: float
    anchor_t: float
    reason: str


def parse_decision_log(path: Path) -> tuple[
        list[LiveCluster], dict[float, str]]:
    clusters: list[LiveCluster] = []
    prose_by_rel_t: dict[float, str] = {}
    # Walk events; for kept clusters we don't have prose in the log
    # directly (frame_signal records signals, not text). So this script
    # additionally accepts a sidecar prose dump if available.
    for ln in path.read_text().splitlines():
        try:
            rec = json.loads(ln)
        except Exception:
            continue
        if rec.get("type") == "cluster_kept":
            clusters.append(LiveCluster(
                cluster_id=rec.get("cluster_id", 0),
                start_t=float(rec["start_t"]),
                end_t=float(rec["end_t"]),
                anchor_t=float(rec.get("anchor_t", rec["end_t"])),
                reason=rec.get("reason", "?"),
            ))
    return clusters, prose_by_rel_t


def load_prose_dir(prose_dir: Path) -> dict[float, str]:
    out: dict[float, str] = {}
    if not prose_dir.exists():
        return out
    for p in sorted(prose_dir.glob("f_*.txt")):
        m = re.search(r"_t=(\d+(?:\.\d+)?)\.txt$", p.name)
        if not m:
            continue
        t = float(m.group(1))
        raw = p.read_text()
        text = raw.split("---\n", 1)[1].strip() if "---\n" in raw else raw
        out[t] = text
    return out


def trim_window(cluster: LiveCluster,
                 prose_by_t: dict[float, str]) -> tuple[float, float]:
    """Apply anchor-centered trim using buffered prose. Reuses
    classify() and trim parameters from trim_delivery_clips."""
    # Build a mock Cluster object compatible with trim_delivery_clips.
    class _C:
        idx = cluster.cluster_id
        anchor_t = cluster.anchor_t
        path = "?"
        clip_start = cluster.start_t - 5
        clip_end = cluster.end_t + 8
        orig_duration = (cluster.end_t + 8) - (cluster.start_t - 5)

    # Replace load_prose with our buffered prose
    orig_load = _trim.load_prose

    def _load(start_t: float, end_t: float):
        return sorted(
            (t, prose_by_t[t]) for t in prose_by_t
            if start_t - 0.5 <= t <= end_t + 0.5)
    _trim.load_prose = _load
    try:
        r = _trim.trim_cluster(_C())
    finally:
        _trim.load_prose = orig_load
    return r.trim_start, r.trim_end


def ffmpeg_cut(source: Path, out: Path,
                start: float, end: float) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
           "-i", str(source),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
           "-c:a", "aac", "-b:a", "128k", str(out)]
    subprocess.run(cmd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--decision-log", required=True,
                    help="path to live_decision_log.jsonl")
    ap.add_argument("--source-video", required=True,
                    help="path to completed match.mp4")
    ap.add_argument("--prose-dir",
                    help="optional: directory of Scout sidecars "
                         "matching the live session, used to drive trim")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--no-extract", action="store_true")
    args = ap.parse_args()

    log_path = Path(args.decision_log)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    clusters, _ = parse_decision_log(log_path)
    prose = load_prose_dir(Path(args.prose_dir)) if args.prose_dir else {}

    summary: list[str] = []
    summary.append("# Post-match live-clip extraction\n\n")
    summary.append(f"Decision log: `{log_path}`\n")
    summary.append(f"Source video: `{args.source_video}`\n")
    summary.append(f"Live clusters kept: **{len(clusters)}**\n\n")
    summary.append("| # | anchor | start | end | trim_start | trim_end "
                   "| dur | reason |\n")
    summary.append("|---|---|---|---|---|---|---|---|\n")
    for c in clusters:
        if prose:
            ts, te = trim_window(c, prose)
        else:
            ts = max(0.0, c.anchor_t - 1.5)
            te = c.anchor_t + 6.0
        dur = te - ts
        if not args.no_extract:
            out_path = out_dir / f"c{c.cluster_id}_anchor{int(c.anchor_t)}.mp4"
            ffmpeg_cut(Path(args.source_video), out_path, ts, te)
        summary.append(
            f"| c{c.cluster_id} | {c.anchor_t:.1f}s | {c.start_t:.1f} "
            f"| {c.end_t:.1f} | {ts:.2f} | {te:.2f} | {dur:.2f}s "
            f"| {c.reason} |\n")
    (out_dir / "post_match_summary.md").write_text("".join(summary))
    print(f"Wrote {len(clusters)} clips + post_match_summary.md to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
