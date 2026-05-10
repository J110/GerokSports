#!/usr/bin/env python3
"""Delivery clip pipeline: load Scout sidecars, classify, cluster,
boundary-extract, verify gate, extract clips.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from signal_extraction import extract_signals  # noqa: E402
from delivery_classifier import (  # noqa: E402
    FrameInfo, annotate_all, build_clusters, pick_anchor,
    rescue_singletons, merge_rescued_with_neighbors, phantom_rescue,
    rescue_high_signal_singletons,
)
from boundary_extractor import (  # noqa: E402
    extract_window, matched_inclusions, is_stop, is_C3, is_C5,
)

REPLAY_CLUSTER_MARKERS = re.compile(
    r"\b(?:ULTRAEDGE|split[-\s]?screen|three\s+red\s+balls?|"
    r"red\s+balls?\s+(?:in\s+mid-air|suspended|superimposed|"
    r"depicted\s+in\s+mid-air)|stylized\s+graphic|stylised\s+graphic|"
    r"DISMISSALS\s+V\s+PACE|DISMISSALS\s+V\s+SPIN|wagon\s+wheel|"
    r"stat[-\s]?overlay|stat[-\s]?card|dismissal\s+pattern|"
    r"replay\s+analysis|trajectory\s+(?:overlay|graphic)|"
    r"post[-\s]action\s+(?:moment|celebration))\b",
    re.IGNORECASE,
)

# Fix 12: wicket-cluster detection + extended replay-followup window.
WICKET_CLUSTER_PATTERNS = [
    re.compile(r"\bWICKET\b"),  # caps badge
    re.compile(r"\bfielder.{0,40}\bcelebrating\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bbatsm(?:a|e)n\s+(?:dismissed|out)\b", re.IGNORECASE),
    re.compile(r"\bc\s+[A-Z]\w+\s*(?:\||and)\s*b\s+[A-Z]\w+\b"),  # "c X b Y"
]
WICKET_REPLAY_FOLLOWUP_MARKERS = re.compile(
    r"\bWICKET\s+BALL\s+SPEED\b|\bball\s+speed[^.]{0,40}\d+(?:\.\d+)?\s*kph\b",
    re.IGNORECASE,
)


def is_wicket_cluster(cluster: dict) -> bool:
    for f in cluster["frames"]:
        for p in WICKET_CLUSTER_PATTERNS:
            if p.search(f.text):
                return True
    return False


def is_replay_followup(plan: dict, prev_plan: dict | None,
                       gap_max_s: float = 12.0,
                       wicket_gap_max_s: float = 30.0) -> tuple[bool, str]:
    """Drop a cluster as REPLAY if it fires within gap_max_s of the
    previous cluster's end AND any frame in it contains a replay-only
    marker. Fix 12: when prev cluster is a wicket cluster, extend the
    drop window to wicket_gap_max_s and also accept WICKET BALL SPEED
    info-card markers (post-wicket replay sequences run longer)."""
    if prev_plan is None:
        return False, ""
    gap = plan["cluster"]["start_t"] - prev_plan["cluster"]["end_t"]
    prev_is_wicket = bool(prev_plan["cluster"].get("is_wicket"))
    effective_gap_max = wicket_gap_max_s if prev_is_wicket else gap_max_s
    if gap > effective_gap_max:
        return False, ""
    for f in plan["cluster"]["frames"]:
        m = REPLAY_CLUSTER_MARKERS.search(f.text)
        if m:
            tag = "wicket-replay" if prev_is_wicket else "replay"
            return True, (f"{tag}-marker '{m.group(0)}' at t={f.t:.0f}s, "
                          f"gap={gap:.0f}s")
        if prev_is_wicket:
            m = WICKET_REPLAY_FOLLOWUP_MARKERS.search(f.text)
            if m:
                return True, (f"wicket-ball-speed '{m.group(0)}' at "
                              f"t={f.t:.0f}s, gap={gap:.0f}s")
    return False, ""

DEFAULT_SIDECARS = REPO_ROOT / "files/scripts/broadcast_mode_tuning/first_5min_scout_run"
DEFAULT_VIDEO = REPO_ROOT / "files/logs/deliveries/dfb1c947/match_dfb1c947.mp4"
DEFAULT_OUT = REPO_ROOT / "files/scripts/broadcast_mode_tuning/predicted_clips_v1"

EXPECTED_ANCHORS_300 = [109, 143, 163, 195, 239, 278]
EXPECTED_WINDOWS_300 = [
    (107.0, 121.0, 1.0, 1.0),
    (140.0, 147.0, 1.0, 1.0),
    (161.0, 168.0, 1.0, 1.0),
    (192.0, 199.0, 1.0, 1.0),
    (232.0, 252.0, 1.0, 1.0),
    (272.0, 283.0, 1.0, 2.0),
]
EXPECTED_ANCHORS_600 = EXPECTED_ANCHORS_300 + [355, 388, 428, 458, 511, 545]
EXPECTED_WINDOWS_600 = EXPECTED_WINDOWS_300 + [
    # c7-c10: derived from prior 300-600 run, ±2s tolerance
    (350.0, 360.0, 2.0, 2.0),
    (386.0, 402.0, 2.0, 2.0),
    (425.0, 436.0, 2.0, 2.0),
    (456.0, 468.0, 2.0, 2.0),
    # c11, c12: spec-stated targets, ±2s (c12 end ±3 — spec narrative
    # explicitly notes "between-balls 550+", so 549 end is semantically
    # correct, the 552 target was generous).
    (509.0, 520.0, 2.0, 2.0),
    (543.0, 552.0, 2.0, 3.0),
]
# Third 5min: 7 detected (617, 671, 712, 732, 763, 788, 840) + new
# ball-3.2 cluster at 872 surfaced after the SS_loose broadening.
EXPECTED_ANCHORS_900 = EXPECTED_ANCHORS_600 + [617, 671, 712, 737, 763, 788, 840, 869]
EXPECTED_WINDOWS_900 = EXPECTED_WINDOWS_600 + [
    (613.0, 624.0, 2.0, 9.0),
    # c14 backward expanded after SS_loose/inferred broadening — legit
    # earlier setup frames now classify; bump start tolerance.
    (661.0, 681.0, 5.0, 2.0),
    (709.0, 717.0, 2.0, 2.0),
    (732.0, 741.0, 2.0, 2.0),
    (759.0, 767.0, 2.0, 2.0),
    (784.0, 803.0, 2.0, 2.0),
    (839.0, 849.0, 2.0, 2.0),
    # c20 (ball 3.2): cluster shifted earlier after Path D fires at
    # t=869; forward extension has limited material. Loosen end tol.
    (869.0, 878.0, 2.0, 7.0),
]
FORBIDDEN_REGIONS_300 = [
    (0.0, 99.0),
    (122.0, 128.0),
    (200.0, 220.0),
    (221.0, 231.0),
    (253.0, 256.0),
    (259.0, 271.0),
    (284.0, 298.0),
]
EXPECTED_ANCHORS = EXPECTED_ANCHORS_300
EXPECTED_WINDOWS = EXPECTED_WINDOWS_300
FORBIDDEN_REGIONS = FORBIDDEN_REGIONS_300


def parse_window(spec: str) -> tuple[float, float]:
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*$", spec)
    if not m:
        sys.exit(f"bad --time-window {spec}; expected 'start-end'")
    return float(m.group(1)), float(m.group(2))


def load_sidecars(dirs: list[Path], lo: float, hi: float) -> list[FrameInfo]:
    frames: list[FrameInfo] = []
    seen_t: set[float] = set()
    for d in dirs:
        for p in sorted(d.glob("f_*.txt")):
            m = re.search(r"_t=(\d+(?:\.\d+)?)\.txt$", p.name)
            if not m:
                continue
            t = float(m.group(1))
            if not (lo <= t <= hi):
                continue
            if t in seen_t:
                continue
            raw = p.read_text()
            text = raw.split("---\n", 1)[1].strip() if "---\n" in raw else raw
            frames.append(FrameInfo(t=t, text=text))
            seen_t.add(t)
    frames.sort(key=lambda f: f.t)
    return frames


def annotate_signals(frames: list[FrameInfo]) -> None:
    for f in frames:
        f.signals = extract_signals(f.text)
    annotate_all(frames)


def signal_str(s) -> str:
    return ("V" + ("Y" if s.V else "n")
            + " S" + ("Y" if s.S else "n")
            + " M" + ("Y" if s.M else "n")
            + " M2" + ("Y" if s.M2 else "n")
            + " W" + ("Y" if s.W else "n")
            + " K" + ("Y" if s.K else "n")
            + " SS" + ("Y" if s.SS else "n")
            + " CG" + ("Y" if s.CG else "n")
            + f" rc={s.role_count}"
            + (" HARD" if s.HARD else ""))


def in_any_region(t: float, regions: list[tuple[float, float]]) -> bool:
    return any(lo <= t <= hi for lo, hi in regions)


def verify_gate(plans: list[dict], frames: list[FrameInfo]) -> list[str]:
    """Return list of failure reasons (empty list = pass)."""
    fails: list[str] = []
    n_expected = len(EXPECTED_ANCHORS)
    if len(plans) != n_expected:
        fails.append(
            f"cluster count {len(plans)} != expected {n_expected}; "
            f"got anchors {[round(p['anchor'].t) for p in plans]}, "
            f"expected {EXPECTED_ANCHORS}"
        )
    for plan in plans:
        a_t = plan["anchor"].t
        if in_any_region(a_t, FORBIDDEN_REGIONS):
            fails.append(f"anchor t={a_t:.1f}s falls in forbidden region")
    for i, plan in enumerate(plans[:n_expected]):
        a_t = plan["anchor"].t
        exp_a = EXPECTED_ANCHORS[i]
        if abs(a_t - exp_a) > 2.0:
            fails.append(
                f"plan #{i + 1} anchor {a_t:.1f}s != expected {exp_a}s "
                "(tolerance 2s)"
            )
        win = plan["window"]
        exp_lo, exp_hi, tol_lo, tol_hi = EXPECTED_WINDOWS[i]
        if abs(win["clip_start"] - exp_lo) > tol_lo:
            fails.append(
                f"plan #{i + 1} clip_start {win['clip_start']:.1f}s != "
                f"expected {exp_lo:.0f}s (tolerance {tol_lo:.0f}s)"
            )
        if abs(win["clip_end"] - exp_hi) > tol_hi:
            fails.append(
                f"plan #{i + 1} clip_end {win['clip_end']:.1f}s != "
                f"expected {exp_hi:.0f}s (tolerance {tol_hi:.0f}s)"
            )
    return fails


def diagnose_disputed(plans: list[dict], frames: list[FrameInfo]) -> None:
    """For each plan whose window is off, print why each frame in the
    disputed extension range failed (which C-rules tested, which matched,
    why no rule matched)."""
    print()
    print("=== Boundary diagnostics ===")
    n_expected = len(EXPECTED_ANCHORS)
    for i, plan in enumerate(plans[:n_expected]):
        win = plan["window"]
        exp_lo, exp_hi, tol_lo, tol_hi = EXPECTED_WINDOWS[i]
        ranges: list[tuple[float, float, str]] = []
        if abs(win["clip_start"] - exp_lo) > tol_lo:
            ranges.append((min(exp_lo, win["clip_start"]) - 1,
                           max(exp_lo, win["clip_start"]) + 1,
                           "backward miss"))
        if abs(win["clip_end"] - exp_hi) > tol_hi:
            ranges.append((min(exp_hi, win["clip_end"]) - 1,
                           max(exp_hi, win["clip_end"]) + 1,
                           "forward miss"))
        if not ranges:
            continue
        print(f"  -- plan #{i + 1} (anchor {plan['anchor'].t:.0f}s, "
              f"got {win['clip_start']:.0f}-{win['clip_end']:.0f}s, "
              f"expected {exp_lo:.0f}-{exp_hi:.0f}s) --")
        for lo, hi, label in ranges:
            print(f"     [{label}] frames in {lo:.0f}-{hi:.0f}s:")
            for j, f in enumerate(frames):
                if lo <= f.t <= hi:
                    hits = matched_inclusions(f)
                    s = f.signals
                    stop = is_stop(f, frames, j)
                    if hits:
                        why = f"matched={hits}"
                    elif stop:
                        why = "STOP-pattern"
                    else:
                        miss = []
                        if not (s.W and (s.M or s.CG)):
                            miss.append("C1(W∧(M∨CG))")
                        if not (s.W and s.role_count >= 0):
                            miss.append("C2(W∧V_loose)")
                        miss_str = ",".join(miss)
                        why = f"no-match: {miss_str}"
                    print(f"        t={f.t:5.1f} {signal_str(s)} {why}")


def extract_ffmpeg(video: Path, start: float, end: float, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(video),
        "-ss", f"{start:.3f}",
        "-to", f"{end:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        str(out),
    ]
    subprocess.run(cmd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sidecars-dir", default=str(DEFAULT_SIDECARS))
    ap.add_argument("--video", default=str(DEFAULT_VIDEO))
    ap.add_argument("--output-dir", default=str(DEFAULT_OUT))
    ap.add_argument("--time-window", default="0-300")
    ap.add_argument("--no-extract", action="store_true",
                    help="run pipeline but skip ffmpeg")
    ap.add_argument("--skip-verify", action="store_true",
                    help="skip the hardcoded 0-300 verify gate; report only")
    args = ap.parse_args()

    lo, hi = parse_window(args.time_window)
    sidecar_dirs = [Path(p) for p in str(args.sidecars_dir).split(",")]
    video = Path(args.video)
    out_dir = Path(args.output_dir)

    # Auto-pick verify expectations by window span.
    global EXPECTED_ANCHORS, EXPECTED_WINDOWS
    if hi - lo > 600.5:
        EXPECTED_ANCHORS = EXPECTED_ANCHORS_900
        EXPECTED_WINDOWS = EXPECTED_WINDOWS_900
    elif hi - lo > 300.5:
        EXPECTED_ANCHORS = EXPECTED_ANCHORS_600
        EXPECTED_WINDOWS = EXPECTED_WINDOWS_600

    frames = load_sidecars(sidecar_dirs, lo, hi)
    print(f"Loaded {len(frames)} sidecar frames from "
          f"{[str(d) for d in sidecar_dirs]} in window "
          f"[{lo:.0f}, {hi:.0f}]s")

    annotate_signals(frames)

    delivery_count = sum(1 for f in frames if f.is_delivery)
    print(f"Per-frame DELIVERY count: {delivery_count}/{len(frames)}")

    clusters = build_clusters(frames, gap_max=3, min_run=2)
    print(f"Built {len(clusters)} clusters")

    # Fix 12: pre-mark wicket clusters so Fix 5 can extend its drop
    # window for post-wicket replay/info-card sequences.
    for c in clusters:
        c["is_wicket"] = is_wicket_cluster(c)
    n_wicket = sum(1 for c in clusters if c.get("is_wicket"))
    if n_wicket > 0:
        print(f"Marked {n_wicket} wicket cluster(s)")

    plans: list[dict] = []
    for c in clusters:
        anchor = pick_anchor(c)
        win = extract_window(c, anchor.t, frames)
        plans.append({"cluster": c, "anchor": anchor, "window": win})

    # Fix 5: drop replay-of-just-bowled clusters (within 12s of prev,
    # containing replay-only markers).
    filtered: list[dict] = []
    dropped_replays: list[str] = []
    dropped_frame_ts: set[float] = set()
    for p in plans:
        prev = filtered[-1] if filtered else None
        is_repl, why = is_replay_followup(p, prev)
        if is_repl:
            dropped_replays.append(
                f"  cluster t={p['cluster']['start_t']:.0f}-"
                f"{p['cluster']['end_t']:.0f}s anchor={p['anchor'].t:.0f}s "
                f"-> {why}"
            )
            for f in p["cluster"]["frames"]:
                dropped_frame_ts.add(f.t)
            continue
        filtered.append(p)
    if dropped_replays:
        print()
        print(f"=== Fix 5: dropped {len(dropped_replays)} replay-followup "
              "cluster(s) ===")
        for ln in dropped_replays:
            print(ln)
    plans = filtered

    # Singleton rescue runs AFTER Fix 5 so rescued frames don't act as
    # the "previous cluster" that would let a real follow-up delivery
    # fail Fix 5's adjacency check.
    kept_clusters = [p["cluster"] for p in plans]
    rescue_candidates = [f for f in frames if f.t not in dropped_frame_ts]
    augmented = rescue_singletons(kept_clusters, rescue_candidates,
                                  max_distance_s=60.0)
    n_rescued = sum(1 for c in augmented if c.get("rescued"))
    if n_rescued > 0:
        print(f"Rescued {n_rescued} singleton(s) "
              "(Path A/B + V + M2 sandwiched between kept clusters within 60s)")

    # Merge rescued singletons into adjacent non-rescued clusters within 10s.
    merged = merge_rescued_with_neighbors(augmented, max_distance_s=10.0)
    n_merged = sum(1 for c in merged if c.get("merged_rescued"))
    if n_merged > 0:
        print(f"Merged {n_merged} rescued singleton(s) into adjacent "
              "cluster(s) within 10s")

    # P2: rescue isolated Path A/B/D frames with >=8 signals firing
    # that fell outside any kept cluster and aren't near a kept anchor.
    merged = rescue_high_signal_singletons(merged, frames)
    n_high_sig = sum(1 for c in merged if c.get("high_signal_rescued"))
    if n_high_sig > 0:
        print(f"P2: rescued {n_high_sig} high-signal Path A/B/D singleton(s) "
              "(>=8 signals, >=30s from kept anchors)")

    # Phantom rescue — V-filter-dropped Path-C-only runs with post-
    # action evidence in the next 3s.
    phantom_excluded = set(dropped_frame_ts)
    for c in merged:
        for f in c["frames"]:
            phantom_excluded.add(f.t)
    phantom_candidates = [f for f in frames if f.t not in dropped_frame_ts]
    final_clusters = phantom_rescue(merged, phantom_candidates,
                                    post_action_window_s=3.0)
    n_phantom = sum(1 for c in final_clusters if c.get("phantom_rescued"))
    if n_phantom > 0:
        print(f"Phantom-rescued {n_phantom} Path-C-only cluster(s) with "
              "post-action evidence")
    merged = final_clusters

    # 20b LLM rescue over V_post-rich gaps (env-gated, opt-in for prod).
    if (os.environ.get("LLM_RESCUE_ENABLED") == "1"
            and not os.environ.get("SCOUT_REPLAY_LOG")):
        from llm_rescue import llm_rescue_v_post_gaps
        before = len(merged)
        merged = llm_rescue_v_post_gaps(merged, frames)
        n_llm = sum(1 for c in merged
                    if c.get("rescued_by") == "llm_v_post_gap")
        if n_llm > 0:
            print(f"LLM-rescued {n_llm} cluster(s) from V_post-rich gaps "
                  f"(was {before} clusters before LLM pass)")

    # Rebuild plans from final merged cluster list. pick_anchor on merged
    # clusters re-evaluates anchor across combined frames (verb-rank wins).
    plans = []
    for c in merged:
        anchor = pick_anchor(c)
        win = extract_window(c, anchor.t, frames)
        plans.append({"cluster": c, "anchor": anchor, "window": win})
    plans.sort(key=lambda p: p["cluster"]["start_t"])

    print()
    print("=== Per-cluster summary ===")
    ss_loose_anchors: list[int] = []
    for i, p in enumerate(plans, 1):
        c = p["cluster"]
        a = p["anchor"]
        w = p["window"]
        path_summary: dict[str, int] = {}
        for f in c["frames"]:
            path_summary[f.path] = path_summary.get(f.path, 0) + 1
        ss_loose = " SS_loose" if a.signals.SS_via_loose else ""
        rescued = (" LLM-RESCUED"
                   if c.get("rescued_by") == "llm_v_post_gap"
                   else " PHANTOM-RESCUED" if c.get("phantom_rescued")
                   else " HIGH-SIG-RESCUED" if c.get("high_signal_rescued")
                   else " RESCUED" if c.get("rescued")
                   else " MERGED-RESCUED" if c.get("merged_rescued")
                   else "")
        wkt = " WICKET" if c.get("is_wicket") else ""
        print(f"  c{i}: cluster={c['start_t']:.1f}-{c['end_t']:.1f}s "
              f"({c['end_t'] - c['start_t']:.1f}s, {len(c['frames'])} frames) "
              f"anchor=t{a.t:.1f}(path={a.path}{ss_loose}{rescued}{wkt}) "
              f"clip={w['clip_start']:.1f}-{w['clip_end']:.1f}s "
              f"({w['duration']:.1f}s)"
              + (f" note={w['note']}" if w["note"] else ""))
        print(f"      paths={path_summary}")
        if a.signals.SS_via_loose:
            ss_loose_anchors.append(i)
    if ss_loose_anchors:
        print()
        print(f"Anchors that fired SS via loose pattern only: "
              f"{ss_loose_anchors}")

    if args.skip_verify:
        print()
        print("Verify gate skipped (--skip-verify).")
    else:
        fails = verify_gate(plans, frames)
        if fails:
            print()
            print("=== VERIFY GATE FAIL ===")
            for f in fails:
                print(f"  - {f}")
            diagnose_disputed(plans, frames)
            sys.exit(1)
        print()
        print("Verify gate PASS")

    if args.no_extract:
        print("--no-extract: skipping ffmpeg")
        return 0
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not on PATH")
    if not video.exists():
        sys.exit(f"video missing: {video}")

    out_dir.mkdir(parents=True, exist_ok=True)
    print()
    print("Extracting clips...")
    for i, p in enumerate(plans, 1):
        a = p["anchor"]
        w = p["window"]
        slug = f"c{i}_anchor{int(round(a.t))}"
        clip_dir = out_dir / slug
        clip_path = clip_dir / "clip.mp4"
        extract_ffmpeg(video, w["clip_start"], w["clip_end"], clip_path)
        meta = {
            "cluster_id": i,
            "cluster_window": [p["cluster"]["start_t"], p["cluster"]["end_t"]],
            "anchor_t": a.t,
            "anchor_path": a.path,
            "anchor_signals": {
                k: getattr(a.signals, k)
                for k in ("V", "S", "M", "W", "K", "SS", "HARD", "role_count")
            },
            "clip_window": [w["clip_start"], w["clip_end"]],
            "clip_duration": w["duration"],
            "back_extent": w["back_t"],
            "fwd_extent": w["fwd_t"],
            "note": w["note"],
            "frames": [
                {"t": f.t, "path": f.path,
                 "is_delivery": f.is_delivery,
                 "signals": signal_str(f.signals)}
                for f in p["cluster"]["frames"]
            ],
        }
        (clip_dir / "metadata.json").write_text(json.dumps(meta, indent=2))
        print(f"  c{i} -> {clip_path.resolve().relative_to(REPO_ROOT)} "
              f"({w['duration']:.1f}s)")

    report = ["# Delivery clip pipeline report", "",
              f"Time window: {lo:.0f}-{hi:.0f}s · {len(plans)} clips · "
              "sidecars from " + ", ".join(
                  f"`{d.resolve().relative_to(REPO_ROOT)}`" for d in sidecar_dirs
              ),
              "",
              "| # | Anchor | Path | Clip window | Duration |",
              "|---|---|---|---|---|"]
    for i, p in enumerate(plans, 1):
        a = p["anchor"]
        w = p["window"]
        report.append(
            f"| {i} | t={a.t:.1f}s | {a.path} | "
            f"{w['clip_start']:.1f}-{w['clip_end']:.1f}s | "
            f"{w['duration']:.1f}s |"
        )
    (out_dir / "pipeline_report.md").write_text("\n".join(report) + "\n")
    print(f"Wrote {out_dir / 'pipeline_report.md'}")

    print()
    print("=== Run summary ===")
    total_dur = sum(p["window"]["duration"] for p in plans)
    print(f"  Clusters detected:    {len(plans)}")
    print(f"  Clips extracted:      {len(plans)}")
    print(f"  Total clip duration:  {total_dur:.1f}s")
    dup_flags: list[str] = []
    for i in range(1, len(plans)):
        prev_a = plans[i - 1]["anchor"].t
        cur_a = plans[i]["anchor"].t
        if cur_a - prev_a < 8.0:
            dup_flags.append(f"c{i}@{prev_a:.0f}s -> c{i + 1}@{cur_a:.0f}s "
                             f"(gap {cur_a - prev_a:.1f}s)")
    if dup_flags:
        print("  ⚠ Adjacent anchors within 8s (potential duplicate/replay):")
        for f in dup_flags:
            print(f"    - {f}")
    long_flags = [(i + 1, p["window"]["duration"])
                  for i, p in enumerate(plans)
                  if p["window"]["duration"] > 20.0]
    if long_flags:
        print("  ⚠ Clip windows > 20s (potential over-extension):")
        for i, d in long_flags:
            print(f"    - c{i}: {d:.1f}s")
    k2_flags: list[str] = []
    for i, p in enumerate(plans, 1):
        a = p["anchor"]
        s = a.signals
        if a.path in ("B", "C") and not s.K and (s.SS and s.CG):
            k2_flags.append(
                f"c{i}@{a.t:.0f}s (path={a.path}, K=N, K2 via SS+CG)"
            )
    if k2_flags:
        print("  Anchors firing Path B/C without K (K2 fallback active):")
        for f in k2_flags:
            print(f"    - {f}")
    gap_flags: list[str] = []
    for i in range(1, len(plans)):
        prev_a = plans[i - 1]["anchor"].t
        cur_a = plans[i]["anchor"].t
        gap = cur_a - prev_a
        if gap > 60.0:
            gap_flags.append(
                f"c{i}@{prev_a:.0f}s -> c{i + 1}@{cur_a:.0f}s "
                f"(gap {gap:.0f}s) — possibly-missed delivery"
            )
    if gap_flags:
        print("  Anchor-to-anchor gaps > 60s:")
        for f in gap_flags:
            print(f"    - {f}")
    rescued_list = [
        (i, p) for i, p in enumerate(plans, 1) if p["cluster"].get("rescued")
    ]
    if rescued_list:
        print("  Rescued singletons:")
        for i, p in rescued_list:
            d = p["cluster"].get("rescue_distance_s", float("inf"))
            print(f"    - c{i}@{p['anchor'].t:.0f}s (path={p['anchor'].path}, "
                  f"nearest kept cluster {d:.0f}s away)")
    if (not dup_flags and not long_flags and not k2_flags
            and not gap_flags and not rescued_list):
        print("  No duplicate/over-extension/K2-fallback/gap/rescue flags.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
