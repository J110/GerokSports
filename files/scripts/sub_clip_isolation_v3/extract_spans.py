"""Sub-clip delivery isolation v3 — 1s padding + event_ts anchoring.

Iteration on v2.  Two changes in this wrapper (SpanAggregator core
unchanged):

* **Padding** reduced from 2.0 s to 1.0 s (env-overridable).  Targets
  v2's "padded to nearly full clip" failure on long single spans.
* **event_ts anchoring** — load `event_ts` and `clip_start_ts` from
  each clip's `window_debug.json`, compute
  `event_offset_s = event_ts - clip_start_ts`.  Filter candidate
  spans to those whose midpoint is ≤ `event_offset_s` (a span whose
  majority is *after* the score event is almost certainly a replay).
  Then pick the span ending CLOSEST TO BUT NOT AFTER
  `event_offset_s`, tie-breaking by longer `frame_count`.  If the
  filter eliminates everything, fall back to v2's "longest by
  frame_count" rule and flag.  If `event_offset_s` is missing /
  invalid (≤ 0), fall back unconditionally.

Design note: in this dataset `event_offset_s > clip_duration` for
every clip (the score event is detected ~1–10 s *after* the clip
window closes, by design of the retrospective_span window source).
That means the "midpoint > event_offset_s" filter is rarely active
on its own — but the "end_ts closest to event_offset_s" preference
materially differs from v2's "longest" preference whenever there
are multiple qualifying spans (e.g. d032).
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
V2_CSV = FILES / "scripts" / "sub_clip_isolation_v2" / "span_selection.csv"
OUT_DIR = FILES / "scripts" / "sub_clip_isolation_v3"
COMP_DIR = OUT_DIR / "comparisons"
SEL_CSV = OUT_DIR / "span_selection.csv"
GALLERY = OUT_DIR / "gallery.mp4"

MIN_RUN_FRAMES = 5
PADDING_S = float(os.environ.get("SUB_CLIP_PADDING_S", "1.0"))
HARD_CLOSE_CLASSES = {"replay", "ad"}

# v2's 10 clips, in v2 order — kept first in the gallery so the operator
# can compare directly.  Then the 5 new clips for v3.  Zero overlap with
# v1+v2 sets.
V2_CLIPS = [
    ("20260420_202239", "d012"),
    ("20260420_202239", "d032"),
    ("20260421_195050", "d013"),
    ("20260420_202239", "d033"),
    ("20260420_202239", "d005"),
    ("20260421_195050", "d066"),
    ("20260421_195050", "d008"),
    ("20260420_202239", "d017"),
    ("20260421_195050", "d021"),
    ("20260421_195050", "d027"),
]
NEW_CLIPS = [
    ("20260420_202239", "d015"),  # HIGH 1.000 1_RUNS, max_run=23 (long-span test)
    ("20260421_195050", "d029"),  # HIGH 1.000 1_RUNS, max_run=10
    ("20260420_202239", "d029"),  # MED  0.700 DOT, max_run=13, 0 replay
    ("20260421_195050", "d055"),  # MED  0.583 1_RUNS, 0 replay
    ("20260421_195050", "d060"),  # LOW  0.455 1_RUNS, 0 replay
]
SELECTED = V2_CLIPS + NEW_CLIPS


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


def load_v2_selections() -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    if not V2_CSV.exists():
        return out
    with V2_CSV.open() as f:
        for row in csv.DictReader(f):
            out[(row["session"], row["clip_id"])] = row
    return out


def load_event_offset(session: str, clip_id: str) -> float | None:
    p = DELIV_ROOT / session / clip_id / "window_debug.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
        ev = float(d.get("event_ts"))
        cs = float(d.get("clip_start_ts"))
        off = ev - cs
        if off <= 0:
            return None
        return off
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def run_aggregator_with_hard_close(frames: list[dict]) -> tuple[list, int]:
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


def select_span(spans: list,
                event_offset_s: float | None) -> tuple[dict, str, int, int]:
    """Return (sel_dict, note, n_pre, n_post) where sel_dict has start,
    end, frames, n_spans; note records the selection_basis + outcome.
    """
    qualifying = [s for s in spans
                  if s.frame_class == "action"
                  and s.frame_count >= MIN_RUN_FRAMES
                  and s.duration_s >= MIN_ACTION_SPAN_S]
    n_pre = len(qualifying)
    if not qualifying:
        # Diagnostic fallback: longest below-min-run span if any.
        any_action = [s for s in spans
                      if s.frame_class == "action"
                      and s.duration_s >= MIN_ACTION_SPAN_S]
        if not any_action:
            return ({"start": 0.0, "end": 0.0, "frames": 0, "n_spans": 0},
                    "no_qualifying_span", 0, 0)
        s = max(any_action, key=lambda s: s.frame_count)
        return ({"start": s.start_ts, "end": s.end_ts,
                 "frames": s.frame_count, "n_spans": len(any_action)},
                f"below_min_run_{MIN_RUN_FRAMES}", 0, 0)

    if event_offset_s is None or event_offset_s <= 0:
        s = max(qualifying, key=lambda s: s.frame_count)
        return ({"start": s.start_ts, "end": s.end_ts,
                 "frames": s.frame_count, "n_spans": len(qualifying)},
                "fallback_no_event_ts", n_pre, n_pre)

    # Anchor filter: drop spans whose MIDPOINT is past the event.
    filtered = [s for s in qualifying
                if (s.start_ts + s.end_ts) / 2.0 <= event_offset_s]
    n_post = len(filtered)

    if not filtered:
        # All candidates are mostly post-event.  Defensive fallback to
        # v2 longest-span behaviour but flag the basis.
        s = max(qualifying, key=lambda s: s.frame_count)
        return ({"start": s.start_ts, "end": s.end_ts,
                 "frames": s.frame_count, "n_spans": len(qualifying)},
                "anchor_filtered_all", n_pre, 0)

    # Pick: end_ts closest to but not after event_offset_s.  All filtered
    # spans satisfy midpoint <= event_offset_s, but their end_ts may
    # exceed event_offset_s when the span straddles the event.  Prefer
    # ends <= event_offset_s; if none, take the smallest end.  Within
    # the chosen partition, pick max end_ts then max frame_count.
    not_after = [s for s in filtered if s.end_ts <= event_offset_s]
    pool = not_after if not_after else filtered

    def key(s):
        # Larger end_ts first (closer to event); larger frame_count
        # breaks ties.
        return (s.end_ts, s.frame_count)

    s = max(pool, key=key)
    basis = ("anchor_end_before_event" if not_after
             else "anchor_straddle_event")
    note = (basis + (f"_n={len(filtered)}" if len(filtered) > 1 else ""))
    return ({"start": s.start_ts, "end": s.end_ts,
             "frames": s.frame_count, "n_spans": len(qualifying)},
            note, n_pre, n_post)


def apply_padding(start: float, end: float, clip_dur: float,
                  pad: float = PADDING_S) -> tuple[float, float, str]:
    if end <= start:
        return (0.0, 0.0, "")
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
    v2_sel = load_v2_selections()

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

        spans, hard_closes = run_aggregator_with_hard_close(frames)
        event_offset = load_event_offset(session, clip_id)
        sel, note, n_pre, n_post = select_span(spans, event_offset)

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

        v2 = v2_sel.get((session, clip_id))
        if v2:
            v2_start = float(v2.get("padded_start_s") or 0)
            v2_end = float(v2.get("padded_end_s") or 0)
            sel_changed = (round(v2_start, 1) != round(pad_start, 1)
                           or round(v2_end, 1) != round(pad_end, 1))
        else:
            v2_start = v2_end = 0.0
            sel_changed = False

        rows.append({
            "session": session,
            "clip_id": clip_id,
            "manual_label": meta["manual_label"],
            "event_type": ev,
            "action_ratio_v2": ar,
            "max_run_v2": max_run,
            "replay_frames": replay_frames,
            "clip_duration_s": round(clip_dur, 3),
            "event_offset_s": round(event_offset, 3) if event_offset else "",
            "hard_close_count": hard_closes,
            "n_candidates_pre_filter": n_pre,
            "n_candidates_post_filter": n_post,
            "selection_basis": note,
            "raw_start_s": round(raw_start, 3),
            "raw_end_s": round(raw_end, 3),
            "padded_start_s": round(pad_start, 3),
            "padded_end_s": round(pad_end, 3),
            "padding_clamp_flags": clamp_flags,
            "selected_frames": sel["frames"],
            "v2_padded_start_s": round(v2_start, 3) if v2 else "",
            "v2_padded_end_s": round(v2_end, 3) if v2 else "",
            "selection_changed": sel_changed if v2 else "",
        })

        out_video = COMP_DIR / f"{session}_{clip_id}_comparison.mp4"
        if sel["frames"] == 0:
            overlay = [
                f"{session}/{clip_id}  {meta['manual_label']}  {ev}",
                (f"ar={ar:.2f}  max_run={max_run}  hc={hard_closes}  "
                 f"NO_SPAN  basis={note}"),
            ]
            try:
                render_side_by_side(orig, 0.0, clip_dur, overlay, out_video)
            except subprocess.CalledProcessError as e:
                print(f"[ffmpeg-fail] {session}/{clip_id}: {e}")
                continue
        else:
            ev_str = (f"ev_off={event_offset:.1f}" if event_offset
                      else "ev_off=NA")
            chg = "CHANGED" if sel_changed else "same"
            overlay = [
                (f"{session}/{clip_id}  {meta['manual_label']}  {ev}  "
                 f"{ev_str}  {chg}"),
                (f"raw=[{raw_start:.1f}-{raw_end:.1f}]  "
                 f"pad=[{pad_start:.1f}-{pad_end:.1f}]  "
                 f"basis={note}"),
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
             f"replay={replay_frames}"),
            (f"event_offset={event_offset:.1f}s  "
             f"clip_dur={clip_dur:.1f}s") if event_offset
                else f"event_offset=NA  clip_dur={clip_dur:.1f}s",
        ]
        render_title_card(title_lines, title_path)
        parts.append(title_path)
        parts.append(out_video)

        chg = "CHG" if sel_changed else "SAM"
        eo = f"{event_offset:.1f}" if event_offset else "NA"
        print(f"[ok] {session}/{clip_id} basis={note} "
              f"hc={hard_closes} eoff={eo} "
              f"raw=[{raw_start:.1f}-{raw_end:.1f}] "
              f"pad=[{pad_start:.1f}-{pad_end:.1f}] "
              f"vs_v2=[{v2_start:.1f}-{v2_end:.1f}] {chg}")

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
