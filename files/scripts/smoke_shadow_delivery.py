#!/usr/bin/env python3
"""Smoke-test the shadow delivery detector against dfb1c947 sidecars.

Replays Scout prose at simulated wall-clock time, drains the detector,
and compares cluster_kept events against predicted_clips_3600_v3
anchors. Sets SHADOW_DELIVERY_DETECTOR=1 in this process before
importing the module."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

os.environ["SHADOW_DELIVERY_DETECTOR"] = "1"

REPO_ROOT = Path(__file__).resolve().parents[2]
SCOUT_BASE = REPO_ROOT / "files/scripts/broadcast_mode_tuning"
EYES = REPO_ROOT / "files/eyes"
import sys
sys.path.insert(0, str(EYES))

from shadow_delivery_detector import ShadowDeliveryDetector  # noqa: E402

SIDECAR_DIRS = [SCOUT_BASE / d for d in [
    "first_5min_scout_run", "second_5min_scout_run",
    "third_5min_scout_run", "fourth_5min_scout_run",
    "fifth_5min_scout_run", "sixth_5min_scout_run",
    "seventh_5min_scout_run", "eighth_5min_scout_run",
    "ninth_5min_scout_run", "tenth_5min_scout_run",
    "eleventh_5min_scout_run", "twelfth_5min_scout_run",
]]
V3_REPORT = SCOUT_BASE / "predicted_clips_3600_v3/pipeline_report.md"
LOG_DIR = REPO_ROOT / "files/logs/deliveries/shadow_smoke_dfb1c947"


def load_frames() -> list[tuple[float, str]]:
    out: list[tuple[float, str]] = []
    seen: set[float] = set()
    for d in SIDECAR_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.glob("f_*.txt")):
            m = re.search(r"_t=(\d+(?:\.\d+)?)\.txt$", p.name)
            if not m:
                continue
            t = float(m.group(1))
            if t in seen:
                continue
            seen.add(t)
            raw = p.read_text()
            text = raw.split("---\n", 1)[1].strip() if "---\n" in raw else raw
            out.append((t, text))
    out.sort()
    return out


def parse_v3_anchors() -> set[float]:
    out: set[float] = set()
    for m in re.finditer(r"\|\s*\d+\s*\|\s*t=([\d.]+)s\s*\|",
                         V3_REPORT.read_text()):
        out.add(float(m.group(1)))
    return out


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "live_decision_log.jsonl"
    if log_path.exists():
        log_path.unlink()
    det = ShadowDeliveryDetector(session_id="smoke_dfb1c947",
                                  log_path=log_path,
                                  match_start_ts=0.0)
    det.start()

    frames = load_frames()
    print(f"Loaded {len(frames)} sidecar frames")
    for t, text in frames:
        det.add_scout_result(timestamp=t, frame_class="action",
                              raw_description=text)
    # Wait for queue drain + final pending closes.
    while not det._q.empty():
        time.sleep(0.05)
    time.sleep(0.5)
    det.stop()

    # Read decision log.
    events = []
    with log_path.open() as fp:
        for ln in fp:
            try:
                events.append(json.loads(ln))
            except Exception:
                continue
    # Latest cluster_kept per cluster_id (merge re-emits supersede).
    _latest_kept: dict = {}
    for e in events:
        if e["type"] != "cluster_kept":
            continue
        _latest_kept[e["cluster_id"]] = e
    kept = list(_latest_kept.values())
    dropped = [e for e in events if e["type"] == "cluster_dropped"]
    phantom = [e for e in events if e["type"] == "phantom_rescue"]
    opened = [e for e in events if e["type"] == "cluster_open"]
    closed = [e for e in events if e["type"] == "cluster_close"]
    print(f"Events: {len(events)}")
    print(f"  cluster_open={len(opened)} cluster_close={len(closed)} "
          f"cluster_kept={len(kept)} cluster_dropped={len(dropped)} "
          f"phantom_rescue={len(phantom)}")

    v3_anchors = parse_v3_anchors()
    shadow_anchors = {round(e["anchor_t"], 1) for e in kept}
    in_both = v3_anchors & shadow_anchors
    v3_only = sorted(v3_anchors - shadow_anchors)
    shadow_only = sorted(shadow_anchors - v3_anchors)
    print()
    print(f"v3 baseline anchors: {len(v3_anchors)}")
    print(f"shadow kept anchors: {len(shadow_anchors)}")
    print(f"agreed: {len(in_both)}  v3_only: {len(v3_only)}  "
          f"shadow_only: {len(shadow_only)}")
    if v3_only:
        print(f"  v3_only sample: {v3_only[:10]}")
    if shadow_only:
        print(f"  shadow_only sample: {shadow_only[:10]}")
    print(f"\nDecision log: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
