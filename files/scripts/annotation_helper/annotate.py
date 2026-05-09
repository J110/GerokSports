#!/usr/bin/env python3
"""
Interactive CLI to annotate delivery clips against layer2.json predictions.
Stdlib only. Run from repo root or any cwd (paths default relative to repo).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_SESSION = "20260430_195352"
DEFAULT_DELIVERIES = REPO_ROOT / "files" / "logs" / "deliveries" / DEFAULT_SESSION


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SAMPLE = SCRIPT_DIR / "sample.txt"
DEFAULT_OUTPUT = SCRIPT_DIR / "annotations.csv"

CSV_FIELDS = [
    "delivery_id",
    "window_source",
    "bounce_visible",
    "gt_length",
    "gt_line",
    "gt_shot_type",
    "gt_shot_side",
    "gt_shot_angle",
    "gt_handedness",
    "notes",
    "model_length",
    "model_length_conf",
    "model_line",
    "model_line_conf",
    "model_shot_type",
    "model_shot_type_conf",
    "model_shot_side",
    "model_shot_side_conf",
    "model_shot_angle",
    "model_shot_angle_conf",
    "model_handedness",
    "model_handedness_conf",
    "annotated_at",
]

MENU_BOUNCE = ["yes", "no", "partial"]
MENU_LENGTH = [
    "yorker",
    "full",
    "good_length",
    "short_of_length",
    "short",
    "bouncer",
]
MENU_LINE = ["outside_off", "off_stump", "middle", "leg_stump", "outside_leg"]
MENU_SHOT_TYPE = ["pull", "cut", "flick", "defend"]
MENU_SHOT_SIDE = ["off", "leg", "straight"]
MENU_SHOT_ANGLE = [
    "cover",
    "mid_off",
    "straight",
    "mid_on",
    "square",
    "down_ground",
    "mid",
    "square_leg",
    "fine_leg",
    "point",
    "third_man",
]
MENU_HAND = ["right", "left"]


def parse_sample(path: Path, deliveries_base: Path) -> list[tuple[str, str]]:
    """Return [(delivery_id, window_source), ...]. Falls back to window_debug if tag missing."""
    rows: list[tuple[str, str]] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = re.split(r"\s+", line, maxsplit=1)
        did = parts[0].strip()
        tag = parts[1].strip() if len(parts) > 1 else ""
        if not did.startswith("d") or not did[1:].isdigit():
            continue
        if not tag:
            wd = deliveries_base / did / "window_debug.json"
            if wd.is_file():
                j = json.loads(wd.read_text())
                tag = j.get("window_source") or ""
        rows.append((did, tag))
    return rows


def load_done_ids(csv_path: Path) -> set[str]:
    if not csv_path.is_file():
        return set()
    with csv_path.open(newline="", encoding="utf-8") as f:
        return {r["delivery_id"] for r in csv.DictReader(f) if r.get("delivery_id")}


def load_predictions(layer2_path: Path) -> tuple[dict, dict]:
    data = json.loads(layer2_path.read_text())
    q = data.get("qwen") or {}
    cv = q.get("cricket_values") or {}
    cc = q.get("cricket_confidence") or {}
    return cv, cc


def print_model_table(cv: dict, cc: dict) -> None:
    rows = [
        ("length", cv.get("length"), cc.get("length")),
        ("line", cv.get("line"), cc.get("line")),
        ("bounce", cv.get("bounce"), cc.get("bounce")),
        ("shot_type", cv.get("shot_type"), cc.get("shot_type")),
        ("shot_side", cv.get("shot_side"), cc.get("shot_side")),
        ("shot_angle", cv.get("shot_angle"), cc.get("shot_angle")),
        ("elevation", cv.get("elevation"), cc.get("elevation")),
        ("bowling_type", cv.get("bowling_type"), cc.get("bowling_type")),
        ("contact_quality", cv.get("contact_quality"), cc.get("contact_quality")),
        ("batsman_handed", cv.get("batsman_handed"), cc.get("batsman_handed")),
        ("bowling_arm", cv.get("bowling_arm"), cc.get("bowling_arm")),
        ("bowling_angle", cv.get("bowling_angle"), cc.get("bowling_angle")),
    ]
    label_w = max(len(r[0]) for r in rows)
    val_w = max(len(str(r[1] or "")) for r in rows)
    val_w = max(val_w, 12)
    print(f"{'Field':<{label_w}}  | {'Model says':<{val_w}} | Confidence")
    print("-" * (label_w + val_w + 20))
    for name, val, conf in rows:
        cstr = "" if conf is None else f"{float(conf):.2f}"
        print(f"{name:<{label_w}}  | {str(val):<{val_w}} | {cstr}")


def open_video(mp4: Path) -> None:
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(mp4)], check=False)
        else:
            subprocess.run(["xdg-open", str(mp4)], check=False)
    except OSError:
        print(f"[WARN] Could not launch a media player. Open manually:\n  {mp4.resolve()}")


def menu_choice(
    title: str,
    options: list[str],
    *,
    stdin,
    allow_skip: bool = True,
    skip_delivery: list[bool],
) -> str:
    while True:
        print(f"\n{title}")
        for i, opt in enumerate(options, 1):
            print(f"  {i}) {opt}")
        print("  u) unknown")
        if allow_skip:
            print("  s) skip delivery (remaining ground-truth fields → skip)")
        print(" > ", end="", flush=True)
        line = stdin.readline()
        if not line:
            raise EOFError("EOF on input — use Ctrl+D only if you intend to exit.")
        choice = line.strip().lower()
        if allow_skip and choice == "s":
            skip_delivery[0] = True
            return "skip"
        if choice == "u":
            return "unknown"
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(options):
                return options[idx - 1]
        print("  Invalid — enter a number, u, or s.")


def annotate_fields(stdin, skip_delivery: list[bool]) -> dict[str, str]:
    out: dict[str, str] = {}
    if skip_delivery[0]:
        out["bounce_visible"] = "skip"
    else:
        out["bounce_visible"] = menu_choice(
            "Bounce visible in clip?", MENU_BOUNCE, stdin=stdin, allow_skip=True, skip_delivery=skip_delivery
        )
    fields = [
        ("gt_length", "Length:", MENU_LENGTH),
        ("gt_line", "Line:", MENU_LINE),
        ("gt_shot_type", "Shot type:", MENU_SHOT_TYPE),
        ("gt_shot_side", "Shot side (off/leg/straight):", MENU_SHOT_SIDE),
        ("gt_shot_angle", "Shot angle / direction:", MENU_SHOT_ANGLE),
        ("gt_handedness", "Batsman handedness:", MENU_HAND),
    ]
    for key, title, opts in fields:
        if skip_delivery[0]:
            out[key.replace("gt_", "", 1) if key.startswith("gt_") else key] = "skip"
            continue
        # keys in out use gt_* prefix in final row assembly
        val = menu_choice(title, opts, stdin=stdin, allow_skip=True, skip_delivery=skip_delivery)
        short = key[3:] if key.startswith("gt_") else key
        out[short] = val
    # normalize keys to gt_* for assembly
    return {
        "bounce_visible": out.get("bounce_visible", "skip"),
        "gt_length": out.get("length", "skip"),
        "gt_line": out.get("line", "skip"),
        "gt_shot_type": out.get("shot_type", "skip"),
        "gt_shot_side": out.get("shot_side", "skip"),
        "gt_shot_angle": out.get("shot_angle", "skip"),
        "gt_handedness": out.get("handedness", "skip"),
    }


def notes_prompt(stdin) -> str:
    print("\nNotes (free-form, ENTER to skip):\n > ", end="", flush=True)
    line = stdin.readline()
    return (line or "").rstrip("\n")


def resolve_path(p: Path, *, script_dir: Path, repo_root: Path) -> Path:
    if p.is_absolute():
        return p
    r = repo_root / p
    if r.is_file() or r.is_dir():
        return r
    s = script_dir / p
    return s


def main() -> int:
    ap = argparse.ArgumentParser(description="Manual delivery annotation vs layer2 predictions.")
    ap.add_argument("--sample-file", type=Path, default=DEFAULT_SAMPLE)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--deliveries", type=Path, default=DEFAULT_DELIVERIES, help="delivery session folder")
    ap.add_argument("--resume", action="store_true", help="Skip delivery_id already present in output CSV")
    args = ap.parse_args()

    sample_path = resolve_path(args.sample_file, script_dir=SCRIPT_DIR, repo_root=REPO_ROOT)
    out_path = resolve_path(args.output, script_dir=SCRIPT_DIR, repo_root=REPO_ROOT)
    deliveries = resolve_path(args.deliveries, script_dir=SCRIPT_DIR, repo_root=REPO_ROOT)

    if not sample_path.is_file():
        print(f"Sample file not found: {sample_path}", file=sys.stderr)
        return 1
    if not deliveries.is_dir():
        print(f"Deliveries folder not found: {deliveries}", file=sys.stderr)
        return 1

    queue = parse_sample(sample_path, deliveries)
    done: set[str] = set()
    if args.resume:
        done = load_done_ids(out_path)

    write_header = not out_path.is_file() or out_path.stat().st_size == 0
    out_path.parent.mkdir(parents=True, exist_ok=True)

    stdin = sys.stdin
    for i, (did, wsrc) in enumerate(queue, 1):
        if did in done:
            print(f"[resume] skipping {did} (already in {out_path.name})")
            continue

        wd = deliveries / did / "window_debug.json"
        l2 = deliveries / did / "layer2.json"
        mp4 = deliveries / did / "delivery_window.mp4"

        print("\n" + "═" * 28)
        print(f" Delivery: {did} ({i}/{len(queue)})")
        print(f" Source: {wsrc}")
        print(f" Folder: {deliveries / did}")
        print("═" * 28)

        if not l2.is_file():
            print(f"[WARN] Missing layer2.json — cannot show predictions for {did}")
            continue

        cv, cc = load_predictions(l2)
        print_model_table(cv, cc)

        if mp4.is_file():
            print(f"\nOpening clip: {mp4}")
            open_video(mp4)
        else:
            print(f"\n[WARN] No mp4 — skipped/phantom? Path:\n  {mp4}")

        skip_delivery = [False]
        try:
            gt_block = annotate_fields(stdin, skip_delivery)
        except EOFError as e:
            print(e, file=sys.stderr)
            return 0

        notes = notes_prompt(stdin)

        row = {
            "delivery_id": did,
            "window_source": wsrc,
            "bounce_visible": gt_block["bounce_visible"],
            "gt_length": gt_block["gt_length"],
            "gt_line": gt_block["gt_line"],
            "gt_shot_type": gt_block["gt_shot_type"],
            "gt_shot_side": gt_block["gt_shot_side"],
            "gt_shot_angle": gt_block["gt_shot_angle"],
            "gt_handedness": gt_block["gt_handedness"],
            "notes": notes,
            "model_length": cv.get("length", ""),
            "model_length_conf": cc.get("length", ""),
            "model_line": cv.get("line", ""),
            "model_line_conf": cc.get("line", ""),
            "model_shot_type": cv.get("shot_type", ""),
            "model_shot_type_conf": cc.get("shot_type", ""),
            "model_shot_side": cv.get("shot_side", ""),
            "model_shot_side_conf": cc.get("shot_side", ""),
            "model_shot_angle": cv.get("shot_angle", ""),
            "model_shot_angle_conf": cc.get("shot_angle", ""),
            "model_handedness": cv.get("batsman_handed", ""),
            "model_handedness_conf": cc.get("batsman_handed", ""),
            "annotated_at": datetime.now(timezone.utc).isoformat(),
        }

        with out_path.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            if write_header:
                w.writeheader()
                write_header = False
            w.writerow(row)

        print(f"\n[saved] → {out_path}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
