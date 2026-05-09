#!/usr/bin/env python3
"""Extract 1 fps JPEGs from labeled delivery-window MP4s.

Video filenames vary by session ({delivery_window_p,n}.mp4, etc.); we pick
the first delivery_window*.mp4 in each clip folder.

See README.md for corpus definition and labeling protocol.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
FILES_ROOT = SCRIPT_DIR.parent.parent
DELIVERIES = FILES_ROOT / "logs" / "deliveries"
FRAMES_DIR = SCRIPT_DIR / "output" / "frames"
LABELS_CSV = SCRIPT_DIR / "output" / "labels_to_fill.csv"

# Positive clips (delivery present); exclude d009 per ball-by-ball thread.
POSITIVE_SESSION = "20260420_214218"
POSITIVE_DELIVERIES = [
    "d001", "d002", "d003", "d004", "d005",
    "d006", "d007", "d008", "d010",
]

# Negative clips (no delivery in window).
NEGATIVE_SESSION = "20260430_195352"
NEGATIVE_DELIVERIES = ["d001", "d002", "d010", "d102", "d104", "d105"]


def _find_mp4(clip_dir: Path) -> Path | None:
    hits = sorted(clip_dir.glob("delivery_window*.mp4"))
    if hits:
        return hits[0]
    others = sorted(clip_dir.glob("*.mp4"))
    return others[0] if others else None


def _ffprobe_duration_s(path: Path) -> float | None:
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            text=True,
        ).strip()
        return float(out)
    except (subprocess.CalledProcessError, ValueError, OSError):
        return None


def _ffmpeg_fps_jpegs(video: Path, out_pattern: Path, fps: float) -> None:
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(video),
            "-vf", f"fps={fps}",
            "-q:v", "2",
            str(out_pattern),
        ],
        check=True,
    )


def extract_one_clip(
        session: str,
        delivery: str,
        *,
        deliveries_root: Path,
        fps: float,
        max_frames: int | None,
        dry_run: bool,
        step_s: float,
) -> list[tuple[int, Path]]:
    clip_dir = deliveries_root / session / delivery
    mp4 = _find_mp4(clip_dir)
    if mp4 is None:
        print(f"[skip] No MP4 under {clip_dir}", file=sys.stderr)
        return []

    dur = _ffprobe_duration_s(mp4)
    work = SCRIPT_DIR / "output" / "_ffmpeg_tmp"
    if not dry_run:
        FRAMES_DIR.mkdir(parents=True, exist_ok=True)
        work.mkdir(parents=True, exist_ok=True)
        for leftover in work.glob("frame_*.jpg"):
            leftover.unlink()
    pattern_work = work / "frame_%06d.jpg"
    stem = f"{session}_{delivery}"

    if dry_run:
        n_est = int((dur or 0) / step_s) + 1 if dur else -1
        print(f"[dry-run] {mp4.name} dur={dur}s est_frames~={n_est}")
        return []

    _ffmpeg_fps_jpegs(mp4, pattern_work, fps)
    numbered = sorted(work.glob("frame_*.jpg"))
    rows: list[tuple[int, Path]] = []

    # ffmpeg fps filter emits frames at 0, step_s, 2*step_s, ... timeline
    for i, jp in enumerate(numbered):
        t = int(round(i * step_s))
        if max_frames is not None and i >= max_frames:
            break
        dest = FRAMES_DIR / f"{stem}_{t}.jpg"
        shutil.move(str(jp), dest)
        rows.append((t, dest))

    # cleanup stray tmp frames if ffmpeg wrote more than capped
    for leftover in work.glob("frame_*.jpg"):
        leftover.unlink()

    meta = ""
    if dur is not None:
        meta = f" duration_s={dur:.2f}"
    print(f"[ok] {session}/{delivery}: {len(rows)} frames from {mp4.name}{meta}")
    return rows


def write_labels_csv(all_rows: list[tuple[str, str, float]]) -> None:
    LABELS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with LABELS_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["frame_path", "source_clip", "time_in_clip_s", "label"],
        )
        w.writeheader()
        for rel_path, source_clip, t in all_rows:
            w.writerow({
                "frame_path": rel_path,
                "source_clip": source_clip,
                "time_in_clip_s": t,
                "label": "",
            })
    print(f"Wrote {LABELS_CSV} ({len(all_rows)} rows, label column empty)")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--deliveries-root",
        type=Path,
        default=DELIVERIES,
        help="Root folder containing session subdirs",
    )
    p.add_argument("--fps", type=float, default=1.0, help="Extraction fps (default 1)")
    p.add_argument(
        "--max-per-clip",
        type=int,
        default=None,
        metavar="N",
        help="Cap frames per clip (e.g. 10 for budget); default = no cap",
    )
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    deliveries_root = args.deliveries_root.resolve()

    fps = args.fps
    step_s = 1.0 / fps if fps > 0 else 1.0

    specs: list[tuple[str, str]] = [(POSITIVE_SESSION, d) for d in POSITIVE_DELIVERIES]
    specs.extend((NEGATIVE_SESSION, d) for d in NEGATIVE_DELIVERIES)

    csv_rows: list[tuple[str, str, float]] = []

    for session, delivery in specs:
        frames = extract_one_clip(
            session,
            delivery,
            deliveries_root=deliveries_root,
            fps=fps,
            max_frames=args.max_per_clip,
            dry_run=args.dry_run,
            step_s=step_s,
        )
        source_clip = f"{session}/{delivery}"
        for t, path in frames:
            rel_path = f"output/frames/{path.name}"
            csv_rows.append((rel_path, source_clip, float(t)))

    csv_rows.sort(key=lambda r: (r[1], r[2]))
    if not args.dry_run:
        write_labels_csv(csv_rows)

    if not args.dry_run:
        print("Done. Fill labels_to_fill.csv (see README) before run_scout.py / analyze.py.")


if __name__ == "__main__":
    main()
