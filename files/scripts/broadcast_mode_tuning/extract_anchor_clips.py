#!/usr/bin/env python3
"""Extract clips around each anchor group from cluster_level_qa_results.json.

Per anchor group, derives a clip window using:
  - backward extension across adjacent clusters (regardless of moments)
    while gap ≤ 8s, plus 2s lead-in.
  - forward extension only across adjacent clusters with ≥1 live
    moment, plus 5s trailing buffer.
  - sanity bounds: min 4s, max 20s (with false-bridge guard).

Truth-checks Group 1 covers 100-115s and Group 2 ≤ 135s before
invoking ffmpeg. Re-encodes for clean cuts.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TUNING_DIR = REPO_ROOT / "files/scripts/broadcast_mode_tuning"
RESULTS_JSON = TUNING_DIR / "cluster_level_qa_results.json"
VIDEO = REPO_ROOT / "files/logs/deliveries/dfb1c947/match_dfb1c947.mp4"
OUT_ROOT = TUNING_DIR / "anchor_clips"

GAP_S = 8.0
LEAD_IN_S = 2.0
TRAIL_S = 5.0
MIN_CLIP_S = 4.0
MAX_CLIP_S = 20.0
FALSE_BRIDGE_FALLBACK_S = 10.0


def load_data() -> dict:
    if not RESULTS_JSON.exists():
        sys.exit(f"missing {RESULTS_JSON}; run cluster_level_qa.py first")
    return json.loads(RESULTS_JSON.read_text())


def build_clusters_info(results: list[dict]) -> list[dict]:
    info = []
    for r in results:
        p = r["payload"]
        v = r.get("verdict") or {}
        moments = v.get("live_delivery_moments") or []
        info.append({
            "cluster_id": p["cluster_id"],
            "start_t": p["start_t"],
            "end_t": p["end_t"],
            "moments": moments,
            "moments_count": len(moments),
        })
    info.sort(key=lambda c: c["start_t"])
    return info


def find_cluster(info: list[dict], cid: int) -> dict:
    for c in info:
        if c["cluster_id"] == cid:
            return c
    raise KeyError(f"cluster {cid} not found in info")


def compute_windows(anchor_groups: list[dict], info: list[dict]) -> list[dict]:
    """Boundary-aware backward/forward extension. Groups are processed
    in temporal order; each group's claim accumulates and bounds later
    groups' backward chains."""
    group_primaries: list[tuple[dict, dict]] = []
    for g in anchor_groups:
        anchors = sorted(g["anchors"], key=lambda a: a["t"])
        primary = find_cluster(info, anchors[0]["cluster_id"])
        primary_end = find_cluster(info, anchors[-1]["cluster_id"])
        group_primaries.append((primary, primary_end))

    windows: list[dict] = []
    prior_associations: set[int] = set()

    for i, g in enumerate(anchor_groups):
        primary, primary_end = group_primaries[i]
        anchors = sorted(g["anchors"], key=lambda a: a["t"])
        earliest, latest = anchors[0], anchors[-1]

        # Backward boundary = max end_t over clusters claimed by
        # earlier groups (primary + their implicit forward gap claims).
        prev_boundary = 0.0
        for cid in prior_associations:
            c = find_cluster(info, cid)
            prev_boundary = max(prev_boundary, c["end_t"])

        # Backward chain: stop on >GAP_S gap OR boundary cross.
        idx = info.index(primary)
        back_extent = primary["start_t"]
        associated: set[int] = {primary["cluster_id"], primary_end["cluster_id"]}
        j = idx - 1
        while j >= 0:
            prev_c = info[j]
            if back_extent - prev_c["end_t"] > GAP_S:
                break
            if prev_c["start_t"] <= prev_boundary:
                break
            back_extent = prev_c["start_t"]
            associated.add(prev_c["cluster_id"])
            j -= 1

        # Forward brake = min primary.start_t over later groups
        # (or +inf if last). Forward chain stops on
        #   * a 0-moment cluster, OR
        #   * gap > GAP_S, OR
        #   * cluster.end_t >= next_group_start.
        later_starts = [group_primaries[k][0]["start_t"]
                        for k in range(i + 1, len(anchor_groups))]
        next_group_start = min(later_starts) if later_starts else float("inf")

        idx_end = info.index(primary_end)
        fwd_extent = primary_end["end_t"]
        j = idx_end + 1
        while j < len(info):
            next_c = info[j]
            if next_c["moments_count"] < 1:
                break
            if next_c["start_t"] - fwd_extent > GAP_S:
                break
            if next_c["end_t"] >= next_group_start:
                break
            fwd_extent = next_c["end_t"]
            associated.add(next_c["cluster_id"])
            j += 1

        # Implicit forward claim: gap clusters between this group's
        # primary_end and the next group's primary start belong to
        # this (the earlier) group, so later groups' backward chains
        # see them as a boundary.
        for c in info:
            if (c["cluster_id"] not in associated
                    and c["start_t"] > primary_end["end_t"]
                    and c["start_t"] < next_group_start):
                associated.add(c["cluster_id"])

        clip_start = max(0.0, back_extent - LEAD_IN_S)
        clip_end = fwd_extent + TRAIL_S

        note = ""
        if (clip_end - clip_start) < MIN_CLIP_S:
            clip_end = clip_start + MIN_CLIP_S
            note = f"min-clip-extended-to-{MIN_CLIP_S:.0f}s"
        if (clip_end - clip_start) > MAX_CLIP_S:
            clip_end = earliest["t"] + FALSE_BRIDGE_FALLBACK_S
            note = "false-bridge-guard"

        windows.append({
            "earliest_anchor": earliest["t"],
            "latest_anchor": latest["t"],
            "primary_cluster": primary["cluster_id"],
            "primary_end_cluster": primary_end["cluster_id"],
            "associated_clusters": sorted(associated),
            "prev_group_boundary": prev_boundary,
            "next_group_start": next_group_start,
            "back_extent": back_extent,
            "fwd_extent": fwd_extent,
            "clip_start": clip_start,
            "clip_end": clip_end,
            "clip_duration": clip_end - clip_start,
            "note": note,
            "anchors": anchors,
        })
        prior_associations |= associated

    return windows


def truth_check(windows: list[dict]) -> None:
    if not windows:
        sys.exit("no anchor groups to check")
    fail = []
    g1 = windows[0]
    if not (g1["clip_start"] <= 100.0 and g1["clip_end"] >= 115.0):
        fail.append(
            f"group 1 clip {g1['clip_start']:.1f}-{g1['clip_end']:.1f}s "
            "does NOT cover truth window 100-115s"
        )
    g2 = windows[1] if len(windows) > 1 else None
    if g2 is not None and g2["clip_end"] > 135.0:
        fail.append(
            f"group 2 clip ends at {g2['clip_end']:.1f}s > 135s "
            "(false-bridge into cluster 5/6 territory)"
        )
    g3 = windows[2] if len(windows) > 2 else None
    if g3 is not None and g2 is not None and g3["clip_start"] < g2["clip_end"]:
        fail.append(
            f"g02 ends at {g2['clip_end']:.1f}s but g03 starts at "
            f"{g3['clip_start']:.1f}s (overlap)"
        )
    g4 = windows[3] if len(windows) > 3 else None
    g5 = windows[4] if len(windows) > 4 else None
    if g4 is not None and g5 is not None and g5["clip_start"] < g4["clip_end"]:
        fail.append(
            f"g04 ends at {g4['clip_end']:.1f}s but g05 starts at "
            f"{g5['clip_start']:.1f}s (overlap)"
        )
    if fail:
        sys.exit("truth-check FAIL:\n  - " + "\n  - ".join(fail))


def slug_for_group(idx: int, w: dict) -> str:
    if abs(w["latest_anchor"] - w["earliest_anchor"]) < 0.01:
        return f"g{idx:02d}_t{int(round(w['earliest_anchor']))}"
    return (f"g{idx:02d}_t{int(round(w['earliest_anchor']))}-"
            f"{int(round(w['latest_anchor']))}")


def extract_clip(in_path: Path, start: float, end: float, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(in_path),
        "-ss", f"{start:.3f}",
        "-to", f"{end:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def main() -> int:
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not on PATH")
    if not VIDEO.exists():
        sys.exit(f"video not found: {VIDEO}")

    data = load_data()
    results = data.get("results") or []
    anchor_groups = data.get("anchor_groups") or []
    if not anchor_groups:
        sys.exit("no anchor_groups in results JSON")

    info = build_clusters_info(results)
    windows = compute_windows(anchor_groups, info)

    print("Planned clip windows:")
    for i, w in enumerate(windows, 1):
        anchors_s = ", ".join(f"{a['t']:.1f}" for a in w["anchors"])
        print(f"  g{i:02d} anchors=[{anchors_s}] "
              f"primary=c{w['primary_cluster']} "
              f"associated={w['associated_clusters']} "
              f"window={w['clip_start']:.1f}-{w['clip_end']:.1f}s "
              f"({w['clip_duration']:.1f}s)"
              + (f" note={w['note']}" if w["note"] else ""))

    truth_check(windows)
    print("Truth check PASS")

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    print()
    print("Extracting clips...")
    for i, (g, w) in enumerate(zip(anchor_groups, windows), 1):
        slug = slug_for_group(i, w)
        clip_dir = OUT_ROOT / slug
        clip_path = clip_dir / "clip.mp4"
        meta_path = clip_dir / "metadata.json"

        extract_clip(VIDEO, w["clip_start"], w["clip_end"], clip_path)

        truth_match = []
        if 100.0 <= w["earliest_anchor"] <= 115.0:
            truth_match.append("1st-delivery")
        if 122.0 <= w["earliest_anchor"] <= 128.0:
            truth_match.append("2nd-delivery")

        associated_detail = []
        for cid in w["associated_clusters"]:
            c = find_cluster(info, cid)
            associated_detail.append({
                "cluster_id": cid,
                "window": [c["start_t"], c["end_t"]],
                "moments_count": c["moments_count"],
            })

        meta = {
            "anchor_group_id": i,
            "anchors": [
                {"t": a["t"], "evidence": a.get("evidence", ""),
                 "cluster_id": a["cluster_id"]}
                for a in w["anchors"]
            ],
            "primary_cluster": w["primary_cluster"],
            "primary_end_cluster": w["primary_end_cluster"],
            "associated_clusters": associated_detail,
            "back_extent": w["back_extent"],
            "fwd_extent": w["fwd_extent"],
            "clip_window": [w["clip_start"], w["clip_end"]],
            "clip_duration": w["clip_duration"],
            "note": w["note"],
            "evidence_excerpts": [a.get("evidence", "") for a in w["anchors"]],
            "truth_match": truth_match,
        }
        meta_path.write_text(json.dumps(meta, indent=2))
        print(f"  g{i:02d} -> {clip_path.relative_to(REPO_ROOT)} "
              f"({w['clip_duration']:.1f}s) "
              + (f"truth={truth_match}" if truth_match else ""))

    print()
    print("Final clip table:")
    print(f"  {'group':>5}  {'clip window':>14}  {'dur':>5}  "
          f"{'anchors':>20}  {'associated':>12}  truth")
    for i, w in enumerate(windows, 1):
        anchors_s = ",".join(f"{a['t']:.0f}" for a in w["anchors"])
        assoc_s = ",".join(f"c{c}" for c in w["associated_clusters"])
        truth = ""
        if 100.0 <= w["earliest_anchor"] <= 115.0:
            truth = "1st"
        elif 122.0 <= w["earliest_anchor"] <= 128.0:
            truth = "2nd"
        print(f"  g{i:02d}    {w['clip_start']:5.1f}-{w['clip_end']:5.1f}s  "
              f"{w['clip_duration']:5.1f}  "
              f"{anchors_s:>20}  {assoc_s:>12}  {truth}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
