"""Sub-clip delivery isolation v2 — replay/ad hard-close + padding.

Iteration on the v1 extract_spans.py.  The SpanAggregator core stays
production-default.  This wrapper adds:

* **Replay/ad hard-close pre-pass** — each ``replay`` or ``ad`` frame
  triggers ``SpanAggregator.force_close(now=ts)`` and is then dropped
  from the feed.  This prevents single replay flickers from being
  absorbed by ``SAME_CLASS_GAP_TOL=1`` and concatenated with a later
  action burst.  The aggregator therefore only ever observes
  ``action`` / ``other`` classes (with rare ``unknown``).
* **Symmetric padding** — after picking the longest qualifying span,
  expand by ``SUB_CLIP_PADDING_S`` (default 2.0 s, env-var
  configurable), clamped to ``[0, clip_duration]``.  Padding is
  reported separately from the raw span bounds.

Selection rule (unchanged from v1): pick the longest action span
with ``frame_count >= MIN_RUN_FRAMES (5)`` and ``duration_s >=
MIN_ACTION_SPAN_S (2.0)``.  No qualifying span → record (0, 0) and
tag ``no_qualifying_span``; this matches production behaviour where
no span = no Qwen call.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FILES = REPO / "files"
sys.path.insert(0, str(FILES))
sys.path.insert(0, str(FILES / "eyes"))

from eyes.span_aggregator import SpanAggregator, MIN_ACTION_SPAN_S  # noqa: E402

SCOUT_JSONL = FILES / "scripts" / "path_a_baseline" / "scout_results_v2.jsonl"
AGG_CSV = FILES / "scripts" / "path_a_baseline" / "clip_aggregates_v2.csv"
DELIV_ROOT = FILES / "logs" / "deliveries"
OUT_DIR = FILES / "scripts" / "sub_clip_isolation_v2"
COMP_DIR = OUT_DIR / "comparisons"
SEL_CSV = OUT_DIR / "span_selection.csv"
GALLERY = OUT_DIR / "gallery.mp4"

MIN_RUN_FRAMES = 5
PADDING_S = float(os.environ.get("SUB_CLIP_PADDING_S", "2.0"))
HARD_CLOSE_CLASSES = {"replay", "ad"}

# Fresh validation set — zero overlap with v1 picks.
# v1 set was: 20260420_202239 {d002,d004,d010,d020,d025},
#             20260421_195050 {d016,d022,d024,d031,d048}.
SELECTED = [
    ("20260420_202239", "d012"),  # HIGH 1.000 1_RUNS
    ("20260420_202239", "d032"),  # HIGH 0.885 1_RUNS, max_run=11
    ("20260421_195050", "d013"),  # HIGH 0.941 1_RUNS
    ("20260420_202239", "d033"),  # MED  0.591 SIX, 3 replay frames
    ("20260420_202239", "d005"),  # MED  0.688 DOT
    ("20260421_195050", "d066"),  # MED  0.625 FOUR
    ("20260421_195050", "d008"),  # MED  0.565 1_RUNS, 9 replay (hard-close test)
    ("20260420_202239", "d017"),  # LOW  0.480 1_RUNS
    ("20260421_195050", "d021"),  # LOW  0.238 1_RUNS, 13 replay
    ("20260421_195050", "d027"),  # LOW  0.389 SIX
]


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


def run_aggregator_with_hard_close(frames: list[dict]) -> tuple[list, int]:
    """Feed Scout frames into SpanAggregator with replay/ad hard-close.

    Returns (committed_spans, hard_close_count).  hard_close_count is
    the number of replay/ad frames that triggered a force_close
    (whether or not an open span actually existed).
    """
    agg = SpanAggregator()
    hard_closes = 0
    for fr in frames:
        cls = fr.get("scout_class")
        if not cls:
            continue
        ts = float(fr["frame_index"])
        if cls in HARD_CLOSE_CLASSES:
            agg.force_close(now=ts)
            hard_closes += 1
            continue
        agg.add_classification(ts, cls, text=fr.get("raw_description"))
    agg.force_close()
    return list(agg.snapshot()), hard_closes


def select_span(spans: list) -> tuple[dict, str]:
    action = [s for s in spans
              if s.frame_class == "action"
              and s.frame_count >= MIN_RUN_FRAMES
              and s.duration_s >= MIN_ACTION_SPAN_S]
    if not action:
        any_action = [s for s in spans
                      if s.frame_class == "action"
                      and s.duration_s >= MIN_ACTION_SPAN_S]
        if not any_action:
            return ({"start": 0.0, "end": 0.0, "frames": 0,
                     "n_spans": 0}, "no_qualifying_span")
        s = max(any_action, key=lambda s: s.frame_count)
        return ({"start": s.start_ts, "end": s.end_ts,
                 "frames": s.frame_count, "n_spans": len(any_action)},
                f"below_min_run_{MIN_RUN_FRAMES}")
    note = ("multi_qualifying_n="
            f"{len(action)}_picked_longest" if len(action) > 1
            else "single_qualifying_span")
    s = max(action, key=lambda s: s.frame_count)
    return ({"start": s.start_ts, "end": s.end_ts,
             "frames": s.frame_count, "n_spans": len(action)}, note)


def apply_padding(start: float, end: float, clip_dur: float,
                  pad: float = PADDING_S) -> tuple[float, float, str]:
    if end <= start:
        return (0.0, 0.0, "")
    raw = (start, end)
    s = max(0.0, start - pad)
    e = min(clip_dur, end + pad)
    flags = []
    if start - pad < 0:
        flags.append("clamped_start")
    if end + pad > clip_dur:
        flags.append("clamped_end")
    return (s, e, ",".join(flags))


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
    _make_text_png(overlay_lines, (1280, 60), overlay_png)
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
        replay_frames = int(meta["replay_count"])
        ad_frames = int(meta["ad_count"])

        spans, hard_closes = run_aggregator_with_hard_close(frames)
        sel, note = select_span(spans)

        orig = clip_path(session, clip_id)
        if not orig.exists():
            print(f"[skip] missing video {orig}")
            continue
        try:
            clip_dur = ffprobe_duration(orig)
        except subprocess.CalledProcessError as e:
            print(f"[skip] ffprobe failed for {session}/{clip_id}: {e}")
            continue

        raw_start, raw_end = sel["start"], sel["end"]
        if sel["frames"] > 0:
            pad_start, pad_end, clamp_flags = apply_padding(
                raw_start, raw_end, clip_dur)
        else:
            pad_start, pad_end, clamp_flags = 0.0, 0.0, ""

        rows.append({
            "session": session,
            "clip_id": clip_id,
            "manual_label": meta["manual_label"],
            "event_type": ev,
            "action_ratio_v2": ar,
            "max_run_v2": max_run,
            "replay_frames": replay_frames,
            "ad_frames": ad_frames,
            "clip_duration_s": round(clip_dur, 3),
            "hard_close_count": hard_closes,
            "n_spans_after_hardclose": sel["n_spans"],
            "raw_start_s": round(raw_start, 3),
            "raw_end_s": round(raw_end, 3),
            "padded_start_s": round(pad_start, 3),
            "padded_end_s": round(pad_end, 3),
            "padding_clamp_flags": clamp_flags,
            "selected_frames": sel["frames"],
            "selection_note": note,
        })

        out_video = COMP_DIR / f"{session}_{clip_id}_comparison.mp4"
        if sel["frames"] == 0:
            overlay = [
                f"{session}/{clip_id}  {meta['manual_label']}  {ev}",
                (f"ar={ar:.2f}  max_run={max_run}  hard_close={hard_closes}  "
                 f"NO_SPAN"),
            ]
            try:
                render_side_by_side(orig, 0.0, clip_dur, overlay, out_video)
            except subprocess.CalledProcessError as e:
                print(f"[ffmpeg-fail] {session}/{clip_id}: {e}")
                continue
        else:
            overlay = [
                f"{session}/{clip_id}  {meta['manual_label']}  {ev}",
                (f"ar={ar:.2f}  raw=[{raw_start:.1f}-{raw_end:.1f}]  "
                 f"pad=[{pad_start:.1f}-{pad_end:.1f}]  hc={hard_closes}"),
            ]
            try:
                render_side_by_side(orig, pad_start, pad_end,
                                    overlay, out_video)
            except subprocess.CalledProcessError as e:
                print(f"[ffmpeg-fail] {session}/{clip_id}: {e}")
                continue

        title_path = title_dir / f"{session}_{clip_id}_title.mp4"
        title_lines = [
            f"{session}/{clip_id}",
            f"{meta['manual_label']}  |  {ev}",
            (f"ar={ar:.2f}  max_run={max_run}  "
             f"replay={replay_frames}  ad={ad_frames}"),
        ]
        render_title_card(title_lines, title_path)
        parts.append(title_path)
        parts.append(out_video)

        print(f"[ok] {session}/{clip_id} note={note} hc={hard_closes} "
              f"raw=[{raw_start:.1f}-{raw_end:.1f}] "
              f"pad=[{pad_start:.1f}-{pad_end:.1f}] "
              f"clamp={clamp_flags or '-'}")

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
