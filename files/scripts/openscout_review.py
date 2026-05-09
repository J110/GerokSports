#!/usr/bin/env python3
"""Summarise OpenScout validation clips under files/logs/openscout_deliveries/."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

FILES_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DELIVERIES_ROOT = FILES_ROOT / "logs" / "openscout_deliveries"


def load_meta(path: Path) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def action_pct(meta: dict) -> float:
    na = int(meta.get("n_classifications_action") or 0)
    no = int(meta.get("n_classifications_other") or 0)
    t = na + no
    if t <= 0:
        return 0.0
    return 100.0 * na / t


def main() -> int:
    ap = argparse.ArgumentParser(
        description="OpenScout delivery validation directory review")
    ap.add_argument(
        "--session",
        required=True,
        help="Session id (folder name under openscout_deliveries)",
    )
    ap.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_DELIVERIES_ROOT,
        help="Parent of session directories",
    )
    ap.add_argument(
        "--list",
        action="store_true",
        help="List each action clip with duration, action %%, manual_review",
    )
    ap.add_argument(
        "--summary",
        action="store_true",
        help="Print manual_review tallies and optional recall",
    )
    ap.add_argument(
        "--actual",
        type=int,
        default=None,
        metavar="N",
        help="Known real delivery count on the field (recall denominator)",
    )
    args = ap.parse_args()

    sess = args.root / args.session
    if not sess.is_dir():
        print(f"Session directory not found: {sess}", file=sys.stderr)
        return 1

    action_meta_paths = sorted(sess.glob("delivery_*_metadata.json"))
    action_rows: list[tuple[Path, dict]] = []
    for p in action_meta_paths:
        m = load_meta(p)
        if m and m.get("frame_class") == "action":
            action_rows.append((p, m))

    bands = Counter()
    for _p, m in action_rows:
        bands[str(m.get("duration_band") or "unknown")] += 1

    na_dir = sess / "non_action"
    non_action_meta: list[tuple[Path, dict]] = []
    if na_dir.is_dir():
        for p in sorted(na_dir.glob("*_metadata.json")):
            m = load_meta(p)
            if m:
                non_action_meta.append((p, m))

    by_cls = Counter()
    for _p, m in non_action_meta:
        by_cls[str(m.get("frame_class") or "unknown")] += 1

    print(f"Session: {args.session}")
    print(
        f"Total deliveries (action): {len(action_rows)}"
    )
    print(
        f"  short (<3s): {bands.get('short', 0)}"
    )
    print(
        f"  normal (3-15s): {bands.get('normal', 0)}"
    )
    print(
        f"  long (>15s): {bands.get('long', 0)}"
    )
    if non_action_meta:
        parts = [
            f"{k}={v}"
            for k, v in sorted(by_cls.items())
        ]
        print(
            f"Non-action spans: {len(non_action_meta)} ({', '.join(parts)})"
        )
    else:
        print("Non-action spans: 0")

    if args.list:
        print("")
        for p, m in sorted(
                action_rows,
                key=lambda x: int(x[1].get("delivery_seq") or 0)):
            ds = m.get("delivery_seq")
            dur = m.get("duration_s")
            rev = m.get("manual_review")
            stem = p.name.replace("_metadata.json", "")
            print(
                f"  {stem}.mp4  delivery_seq={ds}  duration_s={dur}  "
                f"action%={action_pct(m):.0f}  manual_review={rev!r}"
            )

    if args.summary:
        real = 0
        fp = 0
        noise_labels = ("false_positive", "noise", "fp")
        for _p, m in action_rows:
            v = m.get("manual_review")
            if not v:
                continue
            vs = str(v).strip().lower()
            if vs in ("real", "wicket", "yes", "true", "delivery"):
                real += 1
            elif vs in noise_labels:
                fp += 1

        n_ann = real + fp
        n_det = len(action_rows)
        fp_rate = (100.0 * fp / n_det) if n_det else 0.0
        print("")
        print(
            f"Annotated action clips (manual_review set): "
            f"{n_ann} / {n_det}"
        )
        print(f"  counted as real deliveries: {real}")
        print(f"  counted as false positives / noise: {fp}")
        print(
            f"False positives: {fp} / {n_det} detected = "
            f"{fp_rate:.0f}% noise rate"
        )
        if args.actual is not None and args.actual > 0:
            recall = 100.0 * real / args.actual
            print(
                f"Real deliveries: {real} / {args.actual} actual = "
                f"{recall:.0f}% recall"
            )
        else:
            print(
                "(Pass --actual N with ground-truth ball count to "
                "print recall.)"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
