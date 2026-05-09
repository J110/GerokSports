#!/usr/bin/env python3
"""Invoke production Vision.describe on each JPEG from labels CSV.

Writes **one JSON object per line**::

    {
      "frame_path": "...",
      "source_clip": "...",
      "time_in_clip_s": "...",
      "ground_truth": "<from CSV>",
      "scout_response": { ... Vision sidecars + scout_raw ... },
      "scout_label_naive": "action"|"replay"|"ad"|"other"
    }

``scout_label_naive`` comes from :func:`scout_mapping.scout_to_label_naive`
applied to the flat ``scout_response`` payload.

Requirements:
  - ``PYTHONPATH`` must include repository ``files/``.
  - ``GROQ_API_KEY`` for ``eyes.config``.

Example::

    cd files/scripts/scout_validation_research
    PYTHONPATH=../.. python3 run_scout.py --labels-csv output/labels_to_fill.csv
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path

import cv2

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_LABELS_CSV = SCRIPT_DIR / "output" / "labels_to_fill.csv"
OUTPUT_JSONL = SCRIPT_DIR / "output" / "scout_responses.jsonl"

ALLOWED_LABELS = frozenset({
    "action", "replay", "ad", "other", "umpire", "unknown",
})

NAIVE_LABELS = frozenset({"action", "replay", "ad", "other"})


def _ensure_path() -> None:
    root_s = str(SCRIPT_DIR.parent.parent.resolve())
    if root_s not in sys.path:
        sys.path.insert(0, root_s)


def _patch_scout_for_raw_logging() -> None:
    from eyes.vision import Vision  # noqa: WPS433

    if getattr(Vision._scout_call, "_validation_patch", False):
        return

    _orig = Vision._scout_call

    async def _wrapped(self, image_b64: str, prompt: str):
        txt = await _orig(self, image_b64, prompt)
        self._validation_raw_scout_response = txt  # noqa: SLF001
        return txt

    _wrapped._validation_patch = True  # type: ignore[attr-defined]
    Vision._scout_call = _wrapped  # noqa: SLF001


async def classify_one(
        vision,
        bgr,
        *,
        vision_hint: str,
) -> dict[str, object | None]:
    """Return flat dict suitable for nesting under ``scout_response``."""
    frame_type, description, action = await vision.describe(
        bgr, vision_hint=vision_hint,
    )
    raw = getattr(vision, "_validation_raw_scout_response", None)
    return {
        "frame_type": frame_type,
        "description_preview": (description or "")[:2000],
        "action_description": action,
        "last_camera_view": vision.last_camera_view,
        "last_frame_phase": vision.last_frame_phase,
        "last_ball_position": vision.last_ball_position,
        "last_strip_flag": vision.last_strip_flag,
        "last_overlay_flag": vision.last_overlay_flag,
        "last_drs_flag": vision.last_drs_flag,
        "scout_raw": raw,
    }


def validate_labels_csv(path: Path) -> dict[str, int]:
    """B1: non-empty labels only in ALLOWED_LABELS. Returns distribution."""
    bad: dict[str, int] = {}
    dist: dict[str, int] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            lab = (row.get("label") or "").strip()
            dist[lab] = dist.get(lab, 0) + 1
            if not lab:
                raise ValueError(f"Empty label row: {row.get('frame_path')}")
            if lab not in ALLOWED_LABELS:
                bad[lab] = bad.get(lab, 0) + 1
    if bad:
        keys = sorted(bad)
        raise ValueError(f"Illegal labels {{k: counts}} = {repr({k: bad[k] for k in keys})}")
    return dist


async def main_async(args: argparse.Namespace) -> int:
    labels_csv = args.labels_csv.resolve()
    throttle_s = args.throttle_s

    if not args.dry_run and not args.skip_validation:
        dist = validate_labels_csv(labels_csv)
        print(f"[B1] label distribution: {dist}")
        for k in sorted(dist):
            if k not in ALLOWED_LABELS:
                raise SystemExit(1)

    _ensure_path()
    _patch_scout_for_raw_logging()
    from eyes.vision import Vision  # noqa: WPS433
    from scout_mapping import scout_to_label_naive  # noqa: WPS433

    vision = Vision()
    OUTPUT_JSONL.parent.mkdir(parents=True, exist_ok=True)

    if not args.dry_run and not args.append:

        OUTPUT_JSONL.unlink(missing_ok=True)

    processed = 0

    try:
        with labels_csv.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))

        for row in rows:
            label = (row.get("label") or "").strip()
            if args.require_label and not label:
                continue
            if label and label not in ALLOWED_LABELS:
                raise ValueError(f"Unexpected label {label!r} for {row.get('frame_path')}")

            rel = (row.get("frame_path") or "").strip()
            if not rel:
                continue

            img_path = (SCRIPT_DIR / rel).resolve()
            if args.dry_run:
                print(f"[dry-run] {img_path}")
                processed += 1
            else:
                if not img_path.is_file():
                    print(f"[err] missing {img_path}", file=sys.stderr)
                    continue

                mat = cv2.imread(str(img_path))
                if mat is None:
                    print(f"[err] cv2.imread failed {img_path}", file=sys.stderr)
                    continue

                scout_flat = await classify_one(
                    vision, mat, vision_hint=args.vision_hint,
                )
                naive_lbl = scout_to_label_naive(scout_flat)

                assert naive_lbl in NAIVE_LABELS, naive_lbl

                record = {
                    "frame_path": rel,
                    "source_clip": row.get("source_clip", ""),
                    "time_in_clip_s": row.get("time_in_clip_s", ""),
                    "ground_truth": label,
                    "scout_response": scout_flat,
                    "scout_label_naive": naive_lbl,
                }

                with OUTPUT_JSONL.open("a", encoding="utf-8") as out:
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")

                processed += 1

                if throttle_s > 0:
                    await asyncio.sleep(throttle_s)

            if args.limit is not None and processed >= args.limit:
                break

    finally:
        await vision.close()

    tgt = OUTPUT_JSONL if not args.dry_run else OUTPUT_JSONL.name
    print(f"{'Would write' if args.dry_run else 'Wrote'} {tgt} ({processed} rows)")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--labels-csv", type=Path, default=DEFAULT_LABELS_CSV)
    p.add_argument(
        "--vision-hint",
        default="Research batch — classify this single frame.",
    )
    p.add_argument("--throttle-s", type=float, default=0.35)
    p.add_argument("--require-label", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--append", action="store_true")
    p.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip B1 CSV validation (not recommended)",
    )
    return p


def main() -> None:
    args = build_arg_parser().parse_args()
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
