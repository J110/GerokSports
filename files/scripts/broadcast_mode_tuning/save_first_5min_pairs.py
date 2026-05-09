#!/usr/bin/env python3
"""Save paired frame jpg + Scout open_desc txt for the first 5 min of dfb1c947 replay."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from detect_delivery_zones import (  # noqa: E402
    WINDOW_SECONDS, classify, has_action, has_scoreboard, is_not_delivery, pick_sidecar,
)

VIDEO_PATH = REPO_ROOT / "files/logs/deliveries/dfb1c947/match_dfb1c947.mp4"
OUT_DIR = REPO_ROOT / "files/scripts/broadcast_mode_tuning/first_5min_inspection"
FPS = 25.0


def yn(b: bool) -> str:
    return "Y" if b else "N"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sidecar")
    ap.add_argument("--video", default=str(VIDEO_PATH))
    args = ap.parse_args()

    sidecar = pick_sidecar(args.sidecar)
    print(f"Sidecar: {sidecar}")
    print(f"Video:   {args.video}")

    samples: list[dict] = []
    t0 = None
    with open(sidecar) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("ts") is None or not d.get("raw_text"):
                continue
            if t0 is None:
                t0 = d["ts"]
            rel = d["ts"] - t0
            if rel > WINDOW_SECONDS:
                break
            d["_rel"] = rel
            samples.append(d)

    print(f"Samples in first {WINDOW_SECONDS:.0f}s: {len(samples)}")
    if not samples:
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        sys.exit(f"cannot open video {args.video}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    saved = 0
    skipped = 0
    for i, s in enumerate(samples):
        rel = s["_rel"]
        text = s["raw_text"]
        frame_no = int(round(rel * FPS))
        if frame_no >= total:
            skipped += 1
            continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        ok, frame = cap.read()
        if not ok or frame is None:
            skipped += 1
            continue

        stem = f"f_{i:04d}_t={rel:05.1f}"
        jpg = OUT_DIR / f"{stem}.jpg"
        txt = OUT_DIR / f"{stem}.txt"

        cv2.imwrite(str(jpg), frame, [cv2.IMWRITE_JPEG_QUALITY, 80])

        is_d, reason = classify(text)
        a = has_action(text)
        sc = has_scoreboard(text)
        nd, nd_reason = is_not_delivery(text)

        is_replay_hard = nd and nd_reason.startswith(("replay-overlay", "analysis-as-graphic"))
        is_crowd_dominant = nd and nd_reason.startswith("crowd")

        with open(txt, "w") as f:
            f.write(f"ts: {s['ts']:.6f}\n")
            f.write(f"rel_t: {rel:.3f}\n")
            f.write(f"frame_no: {frame_no}\n")
            f.write(f"scout_class: {s.get('frame_class', 'n/a')}\n")
            f.write(f"v2_broadcast_tag: n/a\n")
            f.write(f"binary_label: {'DELIVERY' if is_d else 'NOT_DELIVERY'}\n")
            f.write(f"classify_reason: {reason}\n")
            f.write(f"signals:\n")
            f.write(f"  has_action: {yn(a)}\n")
            f.write(f"  has_score: {yn(sc)}\n")
            f.write(f"  is_replay_hard: {yn(is_replay_hard)}\n")
            f.write(f"  is_crowd_dominant: {yn(is_crowd_dominant)}\n")
            f.write("---\n")
            f.write(text)
            f.write("\n")

        saved += 1

    cap.release()
    print(f"Saved {saved} pairs to {OUT_DIR} (skipped {skipped})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
