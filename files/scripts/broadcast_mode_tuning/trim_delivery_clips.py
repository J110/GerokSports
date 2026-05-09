#!/usr/bin/env python3
"""Trim 77 predicted clips down to delivery + live-action frames only.

Reads pipeline_report.md from predicted_clips_3600_v2/, walks each
cluster's clip window over Scout sidecars, classifies frames as
LIVE_ACTION / REPLAY_AD / IDLE, computes a single contiguous trim
window, and re-encodes from the source match recording."""

from __future__ import annotations

import argparse
import re
import statistics
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCOUT_BASE = REPO_ROOT / "files/scripts/broadcast_mode_tuning"
sys.path.insert(0, str(SCOUT_BASE))

from signal_extraction import (  # noqa: E402
    v_match, v_post_match, hard_match,
)
from delivery_classifier import strong_post_action_match  # noqa: E402

REPORT = SCOUT_BASE / "predicted_clips_3600_v2/pipeline_report.md"
SOURCE_VIDEO = REPO_ROOT / "files/logs/deliveries/dfb1c947/match_dfb1c947.mp4"
OUT_DIR = SCOUT_BASE / "predicted_clips_3600_trimmed"
TRIM_REPORT = OUT_DIR / "trim_report.md"

SIDECAR_DIRS = [SCOUT_BASE / d for d in [
    "first_5min_scout_run", "second_5min_scout_run",
    "third_5min_scout_run", "fourth_5min_scout_run",
    "fifth_5min_scout_run", "sixth_5min_scout_run",
    "seventh_5min_scout_run", "eighth_5min_scout_run",
    "ninth_5min_scout_run", "tenth_5min_scout_run",
    "eleventh_5min_scout_run", "twelfth_5min_scout_run",
]]

MIN_DUR = 5.0
MAX_DUR = 12.0
DEFAULT_TAIL_CAP_S = 8.0
WICKET_TAIL_CAP_S = 12.0
FLOOR_BEFORE_S = 1.5
FLOOR_AFTER_S = 4.0
HEAD_BACKWARD_CAP_S = 6.0
HEAD_GAP_TOLERANCE_S = 3.0
TAIL_GAP_TOLERANCE_S = 6.0
TAIL_DROP_AFTER_S = 8.0
HEAD_PAD = 0.5
TAIL_PAD = 0.5

IDLE_PATTERNS = [
    re.compile(r"\bbetween\s+deliveries\b", re.IGNORECASE),
    re.compile(r"\bno\s+active\s+play\b", re.IGNORECASE),
    re.compile(r"\bmoment\s+of\s+inaction\b", re.IGNORECASE),
    re.compile(r"\bpreparing\s+for\s+(?:the\s+)?next\s+play\b", re.IGNORECASE),
    re.compile(r"\bwaiting\s+for\s+(?:the\s+)?next\s+(?:play|delivery)\b",
               re.IGNORECASE),
    re.compile(r"\bstanding\s+still\b", re.IGNORECASE),
]

BALL_TRACKING_PATTERNS = [
    re.compile(
        r"\bball\s+(?:is\s+)?(?:rolling|rolls|travelling|traveling|flying|"
        r"bouncing|in\s+the\s+air|in\s+mid-air|heading\s+(?:toward|towards)|"
        r"mid-air|in\s+motion)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:fielder|player)s?\s+(?:running|chasing|sprinting|diving|"
        r"picking\s+up|retrieving|fielding|throwing\s+(?:the\s+)?ball)\b",
        re.IGNORECASE),
    re.compile(
        r"\b(?:batters?|batsm[ae]n)\s+(?:running|sprinting|"
        r"completing\s+a\s+run|taking\s+(?:a\s+)?run)\b", re.IGNORECASE),
    re.compile(r"\bball\s+(?:has\s+been|was)\s+hit\b", re.IGNORECASE),
    re.compile(
        r"\b(?:after|following)\s+(?:a\s+|the\s+)?"
        r"(?:hit|stroke|shot|delivery)\b", re.IGNORECASE),
]

GRAPHIC_OVERLAY_PAT = re.compile(
    r"\b(?:graphic\s+overlay\s+with\s+the\s+word\s+\"?(?:FOUR|SIX|WICKET|"
    r"OUT|HOWZAT)|"
    r"large\s+(?:gold|orange|red|blue)\s+circle\s+with\s+the\s+word|"
    r"close[-\s]?up\s+of\s+(?:a\s+)?(?:large\s+)?(?:orange\s+)?cricket\s+"
    r"ball\s+with\s+the\s+word\s+\"?(?:WICKET|FOUR|SIX|OUT)|"
    r"(?:FOUR|SIX|WICKET|OUT)\s+(?:in\s+)?(?:large|stylized|bold|"
    r"superimposed)|"
    r"the\s+word\s+\"?(?:FOUR|SIX|WICKET|OUT)\"?\s+(?:in\s+the\s+center|"
    r"superimposed|in\s+large))",
    re.IGNORECASE,
)


def is_graphic_overlay(text: str) -> bool:
    return bool(GRAPHIC_OVERLAY_PAT.search(text))


WICKET_TAIL_PATTERNS = [
    re.compile(r"\bcelebrating\b", re.IGNORECASE),
    re.compile(r"\bwicket\s+(?:has\s+)?fallen\b", re.IGNORECASE),
    re.compile(r"\bbatsm(?:a|e)n\s+dismissed\b", re.IGNORECASE),
    re.compile(r"\bwalking\s+off\b", re.IGNORECASE),
    re.compile(r"\bWICKET\b"),
]

BOWLER_CTX = re.compile(
    r"\b(?:bowler|bowling|delivering|run[-\s]?up)\b", re.IGNORECASE)
BATTER_CTX = re.compile(
    r"\b(?:batter|batsm(?:a|e)n|batting|at\s+the\s+crease|holding\s+a\s+bat)\b",
    re.IGNORECASE)


def is_ball_tracking(text: str) -> bool:
    return any(p.search(text) for p in BALL_TRACKING_PATTERNS)


def is_wicket_phrase(text: str) -> bool:
    return any(p.search(text) for p in WICKET_TAIL_PATTERNS)


@dataclass
class Cluster:
    idx: int
    anchor_t: float
    path: str
    clip_start: float
    clip_end: float
    orig_duration: float


def parse_report(path: Path) -> list[Cluster]:
    out: list[Cluster] = []
    for m in re.finditer(
        r"\|\s*(\d+)\s*\|\s*t=([\d.]+)s\s*\|\s*(\w+)\s*\|\s*"
        r"([\d.]+)-([\d.]+)s\s*\|\s*([\d.]+)s\s*\|", path.read_text()):
        out.append(Cluster(
            idx=int(m.group(1)),
            anchor_t=float(m.group(2)),
            path=m.group(3),
            clip_start=float(m.group(4)),
            clip_end=float(m.group(5)),
            orig_duration=float(m.group(6)),
        ))
    return out


def load_prose(start_t: float, end_t: float) -> list[tuple[float, str]]:
    out: list[tuple[float, str]] = []
    seen: set[float] = set()
    for d in SIDECAR_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.glob("f_*.txt")):
            try:
                t = float(p.stem.split("_t=")[1])
            except (IndexError, ValueError):
                continue
            if t < start_t - 0.5 or t > end_t + 0.5 or t in seen:
                continue
            seen.add(t)
            raw = p.read_text()
            text = raw.split("---\n", 1)[1].strip() if "---\n" in raw else raw
            out.append((t, text))
    out.sort()
    return out


def classify(text: str) -> str:
    if hard_match(text):
        return "REPLAY_AD"
    if is_graphic_overlay(text):
        return "GRAPHIC"
    if v_match(text) or v_post_match(text) or \
            strong_post_action_match(text) is not None:
        return "LIVE_ACTION"
    if BOWLER_CTX.search(text) and BATTER_CTX.search(text):
        return "LIVE_ACTION"
    if is_ball_tracking(text):
        return "BALL_TRACKING"
    for pat in IDLE_PATTERNS:
        if pat.search(text):
            return "IDLE"
    return "OTHER"


def is_track(label: str) -> bool:
    return label in ("LIVE_ACTION", "BALL_TRACKING")


def is_terminator(label: str) -> bool:
    return label in ("REPLAY_AD", "GRAPHIC")


@dataclass
class TrimResult:
    cluster: Cluster
    trim_start: float
    trim_end: float
    anchor_used_t: float
    head_drop: float
    tail_drop: float
    drop_reasons: list[str]
    head_idle_dropped: bool
    tail_idle_dropped: bool
    internal_replay_truncated_at: float | None
    ball_tracking_extended: bool
    wicket_bonus: bool
    tail_cap_used_s: float
    label_log: list[tuple[float, str]]


def consec_run(labels: list[tuple[float, str]], idx: int,
                target: str, direction: int, max_s: float) -> int:
    """Count consecutive frames matching `target` starting at idx,
    moving by direction (+1 or -1), stopping when the time spread
    reaches max_s. Returns count."""
    if idx < 0 or idx >= len(labels):
        return 0
    cnt = 0
    base_t = labels[idx][0]
    j = idx
    while 0 <= j < len(labels):
        t, lab = labels[j]
        if abs(t - base_t) > max_s:
            break
        if lab != target:
            break
        cnt += 1
        j += direction
    return cnt


def trim_cluster(c: Cluster) -> TrimResult:
    # Pull a slightly wider prose window so the head walk can reach
    # frames slightly outside the original clip if needed.
    prose = load_prose(c.clip_start - 2, c.clip_end + 2)
    labels = [(t, classify(text)) for t, text in prose]
    drop_reasons: list[str] = []
    internal_replay_truncated_at: float | None = None

    # Anchor centered on the cluster's pick_anchor.t (from report).
    anchor_t = c.anchor_t
    anchor_idx = min(range(len(labels)),
                     key=lambda i: abs(labels[i][0] - anchor_t),
                     default=0) if labels else 0
    drop_reasons.append("anchor_centered_floor")

    # Floor zone: [anchor - 1.5, anchor + 4.0]. REPLAY_AD/GRAPHIC inside
    # truncates the floor.
    floor_lo = anchor_t - FLOOR_BEFORE_S
    floor_hi = anchor_t + FLOOR_AFTER_S
    floor_truncate_back: float | None = None
    floor_truncate_fwd: float | None = None
    for t, lab in labels:
        if not is_terminator(lab):
            continue
        if floor_lo <= t < anchor_t:
            floor_truncate_back = max(floor_truncate_back or floor_lo, t + 0.0)
            internal_replay_truncated_at = (internal_replay_truncated_at
                                            if internal_replay_truncated_at
                                            is not None else t)
            drop_reasons.append(f"floor_term_back_at_t{t:.1f}_{lab.lower()}")
        elif anchor_t < t <= floor_hi:
            if floor_truncate_fwd is None or t < floor_truncate_fwd:
                floor_truncate_fwd = t
                internal_replay_truncated_at = (
                    internal_replay_truncated_at
                    if internal_replay_truncated_at is not None else t)
                drop_reasons.append(
                    f"floor_term_fwd_at_t{t:.1f}_{lab.lower()}")

    # Walk BACKWARD from anchor through cluster frames.
    backward_cap_t = max(c.clip_start, anchor_t - HEAD_BACKWARD_CAP_S)
    if floor_truncate_back is not None:
        backward_cap_t = max(backward_cap_t, floor_truncate_back + 0.001)
    head_kept_idx = anchor_idx
    head_idle = False
    last_track_back_t = anchor_t
    j = anchor_idx - 1
    while j >= 0:
        t, lab = labels[j]
        if t < backward_cap_t:
            drop_reasons.append("head_backward_cap")
            break
        if is_terminator(lab):
            head_kept_idx = j + 1
            internal_replay_truncated_at = (
                internal_replay_truncated_at
                if internal_replay_truncated_at is not None else t)
            drop_reasons.append(f"head_term_at_t{t:.1f}_{lab.lower()}")
            break
        if is_track(lab):
            head_kept_idx = j
            last_track_back_t = t
            j -= 1
            continue
        gap = last_track_back_t - t
        if gap > HEAD_GAP_TOLERANCE_S:
            head_idle = True
            drop_reasons.append("head_idle_dropped")
            break
        # Tolerable gap: peek further back for another track within 3s.
        future_back_track = any(
            is_track(labels[k][1])
            for k in range(j - 1, -1, -1)
            if last_track_back_t - labels[k][0] <= HEAD_GAP_TOLERANCE_S)
        if future_back_track:
            head_kept_idx = j
            j -= 1
            continue
        head_idle = True
        drop_reasons.append("head_idle_no_prior_track")
        break

    # Wicket bonus tail cap.
    wicket_bonus = False
    for t, text_full in prose:
        if t < anchor_t or t > anchor_t + 8.0:
            continue
        if is_wicket_phrase(text_full):
            wicket_bonus = True
            break
    tail_cap_s = WICKET_TAIL_CAP_S if wicket_bonus else DEFAULT_TAIL_CAP_S
    cap_t = anchor_t + tail_cap_s
    if floor_truncate_fwd is not None:
        cap_t = min(cap_t, floor_truncate_fwd - 0.001)

    # Walk FORWARD from anchor.
    tail_kept_idx = anchor_idx
    tail_idle = False
    last_track_t = anchor_t
    ball_tracking_used = False
    j = anchor_idx + 1
    while j < len(labels):
        t, lab = labels[j]
        if t > cap_t:
            drop_reasons.append(
                f"tail_cap_{'wicket' if wicket_bonus else 'default'}"
                f"_{tail_cap_s:.0f}s")
            break
        if is_terminator(lab):
            internal_replay_truncated_at = (
                internal_replay_truncated_at
                if internal_replay_truncated_at is not None else t)
            drop_reasons.append(
                f"graphic_terminated_tail" if lab == "GRAPHIC"
                else f"tail_replay_at_t{t:.1f}")
            break
        if is_track(lab):
            tail_kept_idx = j
            last_track_t = t
            if lab == "BALL_TRACKING":
                ball_tracking_used = True
            j += 1
            continue
        gap = t - last_track_t
        if gap > TAIL_DROP_AFTER_S:
            tail_idle = True
            drop_reasons.append("tail_idle_dropped")
            break
        if gap > TAIL_GAP_TOLERANCE_S:
            tail_idle = True
            drop_reasons.append("tail_gap_exceeded")
            break
        future_track = any(
            is_track(labels[k][1])
            for k in range(j + 1, len(labels))
            if labels[k][0] - t <= TAIL_GAP_TOLERANCE_S)
        if future_track:
            tail_kept_idx = j
            j += 1
            continue
        tail_idle = True
        drop_reasons.append("tail_idle_no_future_track")
        break

    # Compute trim_start / trim_end with floor enforcement.
    head_t = labels[head_kept_idx][0] if labels else anchor_t
    tail_t = labels[tail_kept_idx][0] if labels else anchor_t
    trim_start = head_t - HEAD_PAD
    trim_end = tail_t + TAIL_PAD
    # Floor ensures [anchor - FLOOR_BEFORE, anchor + FLOOR_AFTER] kept
    # unless terminator carved it back.
    floor_start = anchor_t - FLOOR_BEFORE_S
    if floor_truncate_back is not None:
        floor_start = max(floor_start, floor_truncate_back + 0.001)
    floor_end = anchor_t + FLOOR_AFTER_S
    if floor_truncate_fwd is not None:
        floor_end = min(floor_end, floor_truncate_fwd - 0.001)
    trim_start = min(trim_start, floor_start)
    trim_end = max(trim_end, floor_end)
    trim_start = max(trim_start, c.clip_start - 2)
    trim_end = min(trim_end, c.clip_end + 2)

    # Hard cap.
    dur = trim_end - trim_start
    if dur < MIN_DUR:
        deficit = MIN_DUR - dur
        trim_start = max(0.0, trim_start - deficit / 2)
        trim_end = trim_end + deficit / 2
        drop_reasons.append(f"padded_to_min({MIN_DUR}s)")
    elif dur > MAX_DUR:
        trim_end = trim_start + MAX_DUR
        drop_reasons.append(f"truncated_to_max({MAX_DUR}s)")

    head_drop = trim_start - c.clip_start
    tail_drop = c.clip_end - trim_end

    return TrimResult(
        cluster=c,
        trim_start=round(trim_start, 2),
        trim_end=round(trim_end, 2),
        anchor_used_t=anchor_t,
        head_drop=round(head_drop, 2),
        tail_drop=round(tail_drop, 2),
        drop_reasons=drop_reasons,
        head_idle_dropped=head_idle,
        tail_idle_dropped=tail_idle,
        internal_replay_truncated_at=internal_replay_truncated_at,
        ball_tracking_extended=ball_tracking_used,
        wicket_bonus=wicket_bonus,
        tail_cap_used_s=tail_cap_s,
        label_log=labels,
    )


def run_ffmpeg(source: Path, out_path: Path,
                start: float, end: float) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
        "-i", str(source),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "aac", "-b:a", "128k",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default=str(REPORT))
    ap.add_argument("--source", default=str(SOURCE_VIDEO))
    ap.add_argument("--output-dir", default=str(OUT_DIR))
    ap.add_argument("--no-extract", action="store_true",
                    help="run trim algorithm without ffmpeg")
    args = ap.parse_args()

    clusters = parse_report(Path(args.report))
    print(f"Parsed {len(clusters)} clusters from {args.report}")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[TrimResult] = []
    for c in clusters:
        r = trim_cluster(c)
        results.append(r)

    # ffmpeg cuts.
    if not args.no_extract:
        source = Path(args.source)
        for r in results:
            anchor_int = int(r.cluster.anchor_t)
            name = f"c{r.cluster.idx}_anchor{anchor_int}.mp4"
            out_path = out_dir / name
            run_ffmpeg(source, out_path, r.trim_start, r.trim_end)
            print(f"  c{r.cluster.idx} -> {out_path.name} "
                  f"({r.trim_end - r.trim_start:.2f}s)")

    # Stats.
    durs = [r.trim_end - r.trim_start for r in results]
    median = statistics.median(durs)
    n_internal = sum(1 for r in results
                     if r.internal_replay_truncated_at is not None)
    n_head_idle = sum(1 for r in results if r.head_idle_dropped)
    n_tail_idle = sum(1 for r in results if r.tail_idle_dropped)
    n_padded = sum(1 for r in results
                   if any("padded_to_min" in x for x in r.drop_reasons))
    n_capped = sum(1 for r in results
                   if any("truncated_to_max" in x for x in r.drop_reasons))
    n_ball_track = sum(1 for r in results if r.ball_tracking_extended)
    n_wicket_bonus = sum(1 for r in results if r.wicket_bonus)
    n_tail_cap_hit = sum(1 for r in results
                          if any(x.startswith("tail_cap_")
                                 for x in r.drop_reasons))
    n_graphic_term = sum(1 for r in results
                         if any(x == "graphic_terminated_tail"
                                or "floor_term" in x and "graphic" in x
                                for x in r.drop_reasons))
    n_tail_idle_no_future = sum(1 for r in results
                                 if any(x == "tail_idle_no_future_track"
                                        for x in r.drop_reasons))

    # Report.
    md: list[str] = []
    md.append("# Trim report\n\n")
    md.append(f"Source: `{args.source}`\n")
    md.append(f"Output: `{out_dir}`\n")
    md.append(f"Clips: {len(results)}\n\n")
    md.append("## Aggregate stats\n")
    md.append(f"- median trimmed duration: **{median:.2f}s**\n")
    md.append(f"- min trimmed duration: {min(durs):.2f}s\n")
    md.append(f"- max trimmed duration: {max(durs):.2f}s\n")
    md.append(f"- internal-replay truncations: **{n_internal}**\n")
    md.append(f"- head_idle drops: **{n_head_idle}**\n")
    md.append(f"- tail_idle drops: **{n_tail_idle}**\n")
    md.append(f"- BALL_TRACKING-extended tails: **{n_ball_track}**\n")
    md.append(f"- wicket-bonus tails: **{n_wicket_bonus}**\n")
    md.append(f"- tail_cap hits ({DEFAULT_TAIL_CAP_S:.0f}s default / "
              f"{WICKET_TAIL_CAP_S:.0f}s wicket): {n_tail_cap_hit}\n")
    md.append(f"- graphic_terminated_tail: **{n_graphic_term}**\n")
    md.append(f"- tail_idle_no_future_track: {n_tail_idle_no_future}\n")
    md.append(f"- padded to {MIN_DUR}s floor: {n_padded}\n")
    md.append(f"- capped at {MAX_DUR}s ceiling: {n_capped}\n\n")
    md.append("## Per-clip table\n")
    md.append("| # | anchor | path | original | trimmed | "
              "delta | trim_window | drop_reasons |\n")
    md.append("|---|---|---|---|---|---|---|---|\n")
    for r in results:
        c = r.cluster
        td = r.trim_end - r.trim_start
        delta = c.orig_duration - td
        reasons = "; ".join(r.drop_reasons) or "-"
        md.append(
            f"| c{c.idx} | t={c.anchor_t:.1f}s | {c.path} | "
            f"{c.orig_duration:.1f}s | {td:.2f}s | {delta:+.2f}s | "
            f"{r.trim_start:.2f}-{r.trim_end:.2f}s | {reasons} |\n"
        )

    TRIM_REPORT.write_text("".join(md))
    print()
    print(f"median={median:.2f}s n_internal_replay={n_internal} "
          f"n_head_idle={n_head_idle} n_tail_idle={n_tail_idle} "
          f"padded={n_padded} capped={n_capped}")
    print(f"Wrote {TRIM_REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
