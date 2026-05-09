#!/usr/bin/env python3
"""Manual labeling tool for delivery clips.

Usage:
    python files/scripts/label_clips.py <session_dir>
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

LABEL_MAP = {
    "d": "real_delivery",
    "r": "replay",
    "a": "ad",
    "x": "noise",
    "s": "skip",
}
CSV_FIELDS = ["clip_id", "label", "over", "event_type", "runs", "window_source"]
CSV_NAME = "labels.csv"


def load_done(csv_path: Path) -> set[str]:
    if not csv_path.exists():
        return set()
    done: set[str] = set()
    with csv_path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = row.get("clip_id")
            if cid:
                done.add(cid)
    return done


def load_meta(clip_dir: Path) -> dict | None:
    p = clip_dir / "window_debug.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def open_clip(clip: Path) -> None:
    subprocess.Popen(
        [
            "osascript",
            "-e",
            'tell application "QuickTime Player" to close (every window) without saving',
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.Popen(["open", str(clip)])


def append_row(csv_path: Path, row: dict) -> None:
    new_file = not csv_path.exists()
    with csv_path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: label_clips.py <session_dir>", file=sys.stderr)
        return 2
    session = Path(argv[1]).resolve()
    if not session.is_dir():
        print(f"not a directory: {session}", file=sys.stderr)
        return 2

    clip_dirs = sorted(p for p in session.iterdir() if p.is_dir() and p.name.startswith("d"))
    csv_path = session / CSV_NAME
    done = load_done(csv_path)
    total = len(clip_dirs)
    print(f"Total: {total}  Done: {len(done)}  Remaining: {total - len(done)}")

    for clip_dir in clip_dirs:
        clip_id = clip_dir.name
        if clip_id in done:
            continue
        mp4 = clip_dir / "delivery_window.mp4"
        if not mp4.exists():
            continue

        meta = load_meta(clip_dir)
        if meta is None:
            print(f"\n[{clip_id}] (no metadata)")
            over = event_type = runs = window_source = ""
        else:
            over = meta.get("over_number", "")
            event_type = meta.get("event_type", "")
            runs = meta.get("runs", "")
            window_source = meta.get("window_source", "")
            print(f"\n[{clip_id}] over={over} event={event_type} runs={runs}")

        open_clip(mp4)

        while True:
            print("label [d=delivery r=replay a=ad x=noise s=skip q=quit]: ", end="", flush=True)
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                print("\nsaved, exiting")
                return 0
            key = line.strip().lower()[:1]
            if key == "q":
                print("saved, exiting")
                return 0
            if key in LABEL_MAP:
                append_row(
                    csv_path,
                    {
                        "clip_id": clip_id,
                        "label": LABEL_MAP[key],
                        "over": over,
                        "event_type": event_type,
                        "runs": runs,
                        "window_source": window_source,
                    },
                )
                done.add(clip_id)
                break
            print("invalid: d/r/a/x/s/q")

    print("\nall clips labeled")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
