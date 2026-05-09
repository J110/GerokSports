#!/usr/bin/env python3
"""Post-match: compare live shadow detector decisions against the
offline v3 pipeline run on the same Scout sidecars. Surfaces
live_only / offline_only / agreed and the per-miss reason."""

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


@dataclass
class LiveCluster:
    cluster_id: int
    anchor_t: float
    start_t: float
    end_t: float
    reason: str


def parse_live(log_path: Path) -> list[LiveCluster]:
    out: list[LiveCluster] = []
    for ln in log_path.read_text().splitlines():
        try:
            rec = json.loads(ln)
        except Exception:
            continue
        if rec.get("type") != "cluster_kept":
            continue
        out.append(LiveCluster(
            cluster_id=rec.get("cluster_id", 0),
            anchor_t=float(rec.get("anchor_t", 0.0)),
            start_t=float(rec.get("start_t", 0.0)),
            end_t=float(rec.get("end_t", 0.0)),
            reason=rec.get("reason", "?"),
        ))
    return out


def parse_offline_report(report_path: Path) -> list[float]:
    anchors: list[float] = []
    for m in re.finditer(r"\|\s*\d+\s*\|\s*t=([\d.]+)s\s*\|",
                         report_path.read_text()):
        anchors.append(float(m.group(1)))
    return anchors


def run_offline_pipeline(sidecars_dir: str, video: str,
                          window_end: float,
                          out_dir: Path) -> Path:
    """Invoke delivery_clip_pipeline.py with --no-extract to produce
    the offline pipeline_report.md that we'll diff against."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["python3", str(SCOUT_BASE / "delivery_clip_pipeline.py"),
           "--sidecars-dir", sidecars_dir,
           "--video", video,
           "--output-dir", str(out_dir),
           "--time-window", f"0-{int(window_end)}",
           "--no-extract", "--skip-verify"]
    subprocess.run(cmd, check=True, cwd=str(SCOUT_BASE))
    return out_dir / "pipeline_report.md"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--decision-log", required=True)
    ap.add_argument("--sidecars-dir", required=True,
                    help="comma-separated dirs of Scout sidecars")
    ap.add_argument("--video", required=True)
    ap.add_argument("--window-end", type=float, default=3600.0)
    ap.add_argument("--offline-output-dir", required=True)
    ap.add_argument("--report", required=True,
                    help="output path for miss_tracking_report.md")
    args = ap.parse_args()

    live = parse_live(Path(args.decision_log))
    print(f"Live kept clusters: {len(live)}")
    offline_report = run_offline_pipeline(
        args.sidecars_dir, args.video, args.window_end,
        Path(args.offline_output_dir))
    offline = parse_offline_report(offline_report)
    print(f"Offline kept clusters: {len(offline)}")

    # Match by anchor proximity ≤2s.
    matched_offline: set[float] = set()
    matched_live: set[int] = set()
    agreed = []
    for lc in live:
        for oa in offline:
            if oa in matched_offline:
                continue
            if abs(oa - lc.anchor_t) <= 2.0:
                agreed.append((lc, oa))
                matched_offline.add(oa)
                matched_live.add(lc.cluster_id)
                break
    live_only = [lc for lc in live if lc.cluster_id not in matched_live]
    offline_only = sorted(oa for oa in offline if oa not in matched_offline)

    md: list[str] = []
    md.append("# Live vs offline shadow-detector miss tracking\n\n")
    md.append(f"Decision log: `{args.decision_log}`\n")
    md.append(f"Offline report: `{offline_report}`\n\n")
    md.append("## Summary\n")
    md.append(f"- agreed: **{len(agreed)}**\n")
    md.append(f"- live_only (live found, offline missed): "
              f"**{len(live_only)}**\n")
    md.append(f"- offline_only (offline found, live missed): "
              f"**{len(offline_only)}**\n\n")

    md.append("## Live-only clusters (live had it, offline didn't)\n")
    if live_only:
        md.append("| cluster | anchor | start | end | reason |\n")
        md.append("|---|---|---|---|---|\n")
        for lc in live_only:
            md.append(f"| c{lc.cluster_id} | {lc.anchor_t:.1f}s | "
                      f"{lc.start_t:.1f} | {lc.end_t:.1f} | "
                      f"{lc.reason} |\n")
    else:
        md.append("(none)\n")

    md.append("\n## Offline-only clusters (live missed)\n")
    if offline_only:
        md.append("| anchor |\n|---|\n")
        for oa in offline_only:
            md.append(f"| t={oa:.1f}s |\n")
    else:
        md.append("(none)\n")

    md.append("\n## Per-miss why-live-missed\n")
    md.append("Inspect `live_decision_log.jsonl` near the missed anchor "
              "for `cluster_dropped`/`hard_reject`/`gap_exceeded` events.\n")
    md.append("Likely live-miss reasons:\n")
    md.append("- Fix 5 (replay-followup) drop happens offline only — "
              "live shadow does not implement it; live may emit cluster_kept "
              "for replay-followups offline drops.\n")
    md.append("- rescue_singletons / merge_rescued runs offline only — "
              "isolated A/B singletons offline kept, live drops via min_run.\n")
    md.append("- Anchor selection differs slightly when prose-rank ties "
              "across multiple delivery frames.\n")

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text("".join(md))
    print(f"Wrote {args.report}")
    print(f"agreed={len(agreed)} live_only={len(live_only)} "
          f"offline_only={len(offline_only)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
