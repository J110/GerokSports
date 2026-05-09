"""Sub-clip delivery isolation v2: extract Scout-derived spans + render side-by-side comparisons.

Reads cached v2 Scout per-frame results and runs them through the existing
SpanAggregator (default config and the proposed P22 tuning, soft_gap=5.0).
Picks the longest qualifying ``action`` span (frame_count >= 5,
duration_s >= MIN_ACTION_SPAN_S) per clip, writes a selection CSV, then
renders ffmpeg side-by-side comparison videos and a gallery concat.
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FILES = REPO / "files"
sys.path.insert(0, str(FILES))
sys.path.insert(0, str(FILES / "eyes"))

from eyes.span_aggregator import SpanAggregator, MIN_ACTION_SPAN_S  # noqa: E402

SCOUT_JSONL = FILES / "scripts" / "path_a_baseline" / "scout_results_v2.jsonl"
AGG_CSV = FILES / "scripts" / "path_a_baseline" / "clip_aggregates_v2.csv"
DELIV_ROOT = FILES / "logs" / "deliveries"
OUT_DIR = FILES / "scripts" / "sub_clip_isolation"
COMP_DIR = OUT_DIR / "comparisons"
SEL_CSV = OUT_DIR / "span_selection.csv"
GALLERY = OUT_DIR / "gallery.mp4"

MIN_RUN_FRAMES = 5  # max_consecutive_action heuristic from Path A iteration

SELECTED = [
    # (session, clip_id) — chosen across action_ratio bands and event types.
    ("20260420_202239", "d004"),  # HIGH 0.955 / 2_RUNS
    ("20260421_195050", "d048"),  # HIGH 1.000 / 1_RUNS
    ("20260421_195050", "d016"),  # HIGH 0.857 / lower max_run within HIGH
    ("20260420_202239", "d010"),  # MED  0.625 / WICKET
    ("20260420_202239", "d020"),  # MED  0.688 / SIX
    ("20260421_195050", "d024"),  # MED  0.692 / typical
    ("20260420_202239", "d002"),  # MED  0.636 / 1_RUNS, has replay frames
    ("20260420_202239", "d025"),  # LOW  0.375 / has 6 replay frames
    ("20260421_195050", "d022"),  # LOW  0.200 / dominated by replay
    ("20260421_195050", "d031"),  # LOW  0.133 / extreme replay-dominant
]


@dataclass
class ClipMeta:
    session: str
    clip_id: str
    label: str
    event_type: str
    action_ratio: float
    max_run: int
    total_frames: int


def load_aggregates() -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    with AGG_CSV.open() as f:
        for row in csv.DictReader(f):
            out[(row["session"], row["clip_id"])] = row
    return out


def load_event_types() -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for sess_dir in DELIV_ROOT.iterdir():
        labels = sess_dir / "labels.csv"
        if not labels.exists():
            continue
        with labels.open() as f:
            for row in csv.DictReader(f):
                out[(sess_dir.name, row["clip_id"])] = row.get("event_type", "")
    return out


def load_scout_frames() -> dict[tuple[str, str], list[dict]]:
    by_clip: dict[tuple[str, str], list[dict]] = defaultdict(list)
    with SCOUT_JSONL.open() as f:
        for line in f:
            r = json.loads(line)
            by_clip[(r["session"], r["clip_id"])].append(r)
    for k in by_clip:
        by_clip[k].sort(key=lambda r: r["frame_index"])
    return by_clip


def run_aggregator(frames: list[dict], soft_gap: float) -> list:
    agg = SpanAggregator(soft_gap_tolerance_s=soft_gap)
    for fr in frames:
        cls = fr.get("scout_class")
        if not cls:
            continue
        ts = float(fr["frame_index"])  # 1 fps cadence
        agg.add_classification(ts, cls, text=fr.get("raw_description"))
    agg.force_close()
    return [s for s in agg.snapshot()]


def select_span(spans: list, clip_duration: float) -> tuple[dict, str]:
    action = [s for s in spans
              if s.frame_class == "action"
              and s.frame_count >= MIN_RUN_FRAMES
              and s.duration_s >= MIN_ACTION_SPAN_S]
    if not action:
        # Relax min_run to capture the "qualifying duration only" case so we
        # can record whether ANY action span existed at all.
        any_action = [s for s in spans
                      if s.frame_class == "action"
                      and s.duration_s >= MIN_ACTION_SPAN_S]
        if not any_action:
            return ({"start": 0.0, "end": 0.0, "frames": 0,
                     "ratio": 0.0, "n_spans": 0}, "no_qualifying_span")
        # Pick longest by frame_count for diagnostic display.
        s = max(any_action, key=lambda s: s.frame_count)
        return ({"start": s.start_ts, "end": s.end_ts,
                 "frames": s.frame_count, "ratio": 1.0,
                 "n_spans": len(any_action)},
                f"below_min_run_{MIN_RUN_FRAMES}")
    note = "single_qualifying_span"
    if len(action) > 1:
        note = f"multi_qualifying_n={len(action)}_picked_longest"
    s = max(action, key=lambda s: s.frame_count)
    ratio = s.frame_count / max(1, int(round(s.end_ts - s.start_ts + 1)))
    return ({"start": s.start_ts, "end": s.end_ts,
             "frames": s.frame_count, "ratio": ratio,
             "n_spans": len(action)}, note)


def clip_path(session: str, clip_id: str) -> Path:
    return DELIV_ROOT / session / clip_id / "delivery_window.mp4"


def ffprobe_duration(p: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(p)
    ], text=True).strip()
    return float(out)


def _make_text_png(text_lines: list[str], size: tuple[int, int],
                   out_png: Path, bg=(0, 0, 0), fg=(255, 255, 255)) -> None:
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(img)
    font = None
    for fp in ("/System/Library/Fonts/Helvetica.ttc",
               "/System/Library/Fonts/Supplemental/Arial.ttf",
               "/Library/Fonts/Arial.ttf"):
        if Path(fp).exists():
            try:
                font = ImageFont.truetype(fp, 22)
                break
            except OSError:
                continue
    if font is None:
        font = ImageFont.load_default()
    line_h = 28
    total_h = line_h * len(text_lines)
    y0 = (size[1] - total_h) // 2
    for i, line in enumerate(text_lines):
        bbox = d.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = max(10, (size[0] - w) // 2)
        d.text((x, y0 + i * line_h), line, fill=fg, font=font)
    img.save(out_png)


def render_side_by_side(orig: Path, sel_start: float, sel_end: float,
                        overlay_lines: list[str], out_path: Path) -> None:
    duration = ffprobe_duration(orig)
    sub_dur = max(0.001, sel_end - sel_start)
    pad_after = max(0.0, duration - sub_dur)
    overlay_png = out_path.with_suffix(".overlay.png")
    _make_text_png(overlay_lines, (1280, 60), overlay_png,
                   bg=(0, 0, 0), fg=(255, 255, 255))
    filter_complex = (
        f"[0:v]scale=640:360,setsar=1[L];"
        f"[1:v]trim=start={sel_start:.3f}:end={sel_end:.3f},"
        f"setpts=PTS-STARTPTS,scale=640:360,setsar=1,"
        f"tpad=stop_mode=add:stop_duration={pad_after:.3f}:color=black[R];"
        f"[L][R]hstack=inputs=2[SBS];"
        f"[SBS][2:v]overlay=0:main_h-overlay_h[VO]"
    )
    cmd = [
        "ffmpeg", "-y", "-i", str(orig), "-i", str(orig),
        "-loop", "1", "-t", f"{duration:.3f}", "-i", str(overlay_png),
        "-filter_complex", filter_complex,
        "-map", "[VO]", "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-t", f"{duration:.3f}",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    overlay_png.unlink(missing_ok=True)


def render_title_card(text_lines: list[str], out_path: Path,
                      dur: float = 1.5) -> None:
    png = out_path.with_suffix(".png")
    _make_text_png(text_lines, (1280, 360), png)
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(png),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-t", str(dur), "-r", "16",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    png.unlink(missing_ok=True)


def concat_gallery(parts: list[Path], out_path: Path) -> None:
    list_file = out_path.parent / "_concat_list.txt"
    with list_file.open("w") as f:
        for p in parts:
            f.write(f"file '{p.as_posix()}'\n")
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file), "-c:v", "libx264",
        "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    list_file.unlink(missing_ok=True)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    COMP_DIR.mkdir(parents=True, exist_ok=True)

    aggregates = load_aggregates()
    event_types = load_event_types()
    scout_frames = load_scout_frames()

    rows: list[dict] = []
    parts: list[Path] = []
    title_dir = OUT_DIR / "_titles"
    title_dir.mkdir(exist_ok=True)

    for session, clip_id in SELECTED:
        meta = aggregates.get((session, clip_id))
        if meta is None:
            print(f"[skip] no aggregate for {session}/{clip_id}")
            continue
        frames = scout_frames.get((session, clip_id), [])
        ev = event_types.get((session, clip_id), "")
        ar = float(meta["action_ratio"])
        max_run = int(meta["max_consecutive_action"])

        spans_default = run_aggregator(frames, soft_gap=2.5)
        spans_p22 = run_aggregator(frames, soft_gap=5.0)
        sel_def, note_def = select_span(spans_default, 0)
        sel_p22, note_p22 = select_span(spans_p22, 0)

        rows.append({
            "session": session,
            "clip_id": clip_id,
            "manual_label": meta["manual_label"],
            "event_type": ev,
            "action_ratio_v2": ar,
            "max_run_v2": max_run,
            "n_spans_default": sel_def["n_spans"],
            "selected_start_s_default": round(sel_def["start"], 3),
            "selected_end_s_default": round(sel_def["end"], 3),
            "selected_frames_default": sel_def["frames"],
            "selection_note_default": note_def,
            "n_spans_p22": sel_p22["n_spans"],
            "selected_start_s_p22": round(sel_p22["start"], 3),
            "selected_end_s_p22": round(sel_p22["end"], 3),
            "selected_frames_p22": sel_p22["frames"],
            "selection_note_p22": note_p22,
        })

        # Render against P22 selection (preferred per task brief).  Fall back
        # to default if P22 produced no span.
        sel = sel_p22 if sel_p22["frames"] > 0 else sel_def
        cfg_used = "p22" if sel_p22["frames"] > 0 else "default"
        orig = clip_path(session, clip_id)
        if not orig.exists():
            print(f"[skip] missing video {orig}")
            continue
        out_video = COMP_DIR / f"{session}_{clip_id}_comparison.mp4"
        if sel["frames"] == 0:
            try:
                duration = ffprobe_duration(orig)
                overlay = [
                    f"{session}/{clip_id}  {meta['manual_label']}  {ev}",
                    f"ar={ar:.2f}  max_run={max_run}  NO_SPAN  cfg={cfg_used}",
                ]
                render_side_by_side(orig, 0.0, duration, overlay, out_video)
            except subprocess.CalledProcessError as e:
                print(f"[ffmpeg-fail] {session}/{clip_id}: {e}")
                continue
        else:
            overlay = [
                f"{session}/{clip_id}  {meta['manual_label']}  {ev}",
                (f"ar={ar:.2f}  max_run={max_run}  "
                 f"sub=[{sel['start']:.1f}s-{sel['end']:.1f}s]  cfg={cfg_used}"),
            ]
            try:
                render_side_by_side(orig, sel["start"], sel["end"],
                                    overlay, out_video)
            except subprocess.CalledProcessError as e:
                print(f"[ffmpeg-fail] {session}/{clip_id}: {e}")
                continue

        title_path = title_dir / f"{session}_{clip_id}_title.mp4"
        title_lines = [
            f"{session}/{clip_id}",
            f"{meta['manual_label']}  |  {ev}",
            f"action_ratio={ar:.2f}  max_run={max_run}",
        ]
        render_title_card(title_lines, title_path)
        parts.append(title_path)
        parts.append(out_video)

        print(f"[ok] {session}/{clip_id} default={note_def} p22={note_p22} "
              f"sel={sel['start']:.1f}-{sel['end']:.1f}")

    if rows:
        with SEL_CSV.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"[csv] wrote {SEL_CSV}")

    if parts:
        try:
            concat_gallery(parts, GALLERY)
            print(f"[gallery] wrote {GALLERY}")
        except subprocess.CalledProcessError as e:
            print(f"[gallery-fail] {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
