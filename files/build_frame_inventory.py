"""Part B corpus scaffolding — parse RC9 Scout log into a frame
inventory so stratified selection is data-driven.

Output: `corpus_frame_inventory.json` with one entry per debug_frame
jpeg on disk, augmented with Scout's original tags, the frame's
timestamp, and proximity to nearest ball_event (WICKET/FOUR/SIX/
EXTRA).
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict

DEFAULT_LOG = "logs/runs/rcb_gt_rc9_commentary_203904.log"
DEFAULT_FRAMES_DIR = "debug_frames"
DEFAULT_OUT = "corpus_frame_inventory.json"

# ANSI colour prefix that wraps every log line in RC9.
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _strip(line: str) -> str:
    return ANSI.sub("", line)


SCOUT_LINE = re.compile(
    r"\[(\d{2}:\d{2}:\d{2})\s+F(\d+)\s+VISION\].*"
    r"\[SCOUT\]\s+(\w+)\s+(\d+)ms\s+"
    r"strip=(\w+)\s+overlay=(\w+)\s+drs=(\w+)\s+"
    r"cam=(\w+)\s+phase=(\w+)"
)

DETAIL_LINE = re.compile(
    r"\[(\d{2}:\d{2}:\d{2})\s+F(\d+)\s+TEST\].*DETAIL\|"
)

BALL_EVENT = re.compile(r"\|ball_event=([A-Z_]+)\|")
BALL_OVER = re.compile(r"\|ball_event_over=([^|]+)\|")


def parse_log(log_path: str):
    """Return (scout_records, ball_event_records).

    scout_records: dict[frame_count] = {
        'ts': '20:39:09', 'frame_type': 'SCOREBOARD', 'ms': 973,
        'strip': True, 'overlay': False, 'drs': False,
        'cam': 'bowlers_end', 'phase': 'release'
    }
    ball_event_records: list[{'frame_count', 'ts', 'event', 'over'}]
    """
    scout: dict[int, dict] = {}
    events: list[dict] = []

    with open(log_path, encoding="utf-8") as f:
        for raw in f:
            line = _strip(raw.rstrip("\n"))
            m = SCOUT_LINE.search(line)
            if m:
                (ts, fc, ftype, ms, strip, overlay, drs,
                 cam, phase) = m.groups()
                scout[int(fc)] = {
                    "ts": ts,
                    "frame_type": ftype,
                    "ms": int(ms),
                    "strip": strip == "True",
                    "overlay": overlay == "True",
                    "drs": drs == "True",
                    "cam": cam,
                    "phase": phase,
                }
                continue
            d = DETAIL_LINE.search(line)
            if d:
                ts, fc = d.groups()
                be = BALL_EVENT.search(line)
                bo = BALL_OVER.search(line)
                if be and be.group(1) != "NONE":
                    events.append({
                        "frame_count": int(fc),
                        "ts": ts,
                        "event": be.group(1),
                        "over": bo.group(1) if bo else "?",
                    })
    return scout, events


def _ts_to_sec(ts: str) -> int:
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def nearest_event(frame_ts: str, events: list[dict],
                  frame_fc: int) -> dict:
    """Return nearest ball_event by frame_count distance.  Frame
    distance is more meaningful than wall-time delta because the
    pipeline polls at variable rates.
    """
    if not events:
        return {"event": None, "delta_frames": None,
                "delta_sec": None, "direction": None}
    best = None
    for ev in events:
        d = ev["frame_count"] - frame_fc
        if best is None or abs(d) < abs(best["delta_frames"]):
            best = {
                "event": ev["event"],
                "event_over": ev["over"],
                "delta_frames": d,
                "delta_sec": (_ts_to_sec(ev["ts"])
                              - _ts_to_sec(frame_ts)),
                "direction": "after" if d > 0
                             else ("before" if d < 0 else "at"),
            }
    return best


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(
        description=(
            "Build corpus_frame_inventory.json from Scout log lines + jpeg "
            "names under frames-dir."),
    )
    ap.add_argument(
        "--log",
        default=DEFAULT_LOG,
        help=f"Pipeline or commentary log with [SCOUT] lines (default: {DEFAULT_LOG})",
    )
    ap.add_argument(
        "--output",
        "-o",
        default=DEFAULT_OUT,
        help=f"Output inventory JSON path (default: {DEFAULT_OUT})",
    )
    ap.add_argument(
        "--frames-dir",
        default=DEFAULT_FRAMES_DIR,
        help=(
            "Directory of f*_*.jpg snapshots for this session "
            f"(default: {DEFAULT_FRAMES_DIR})"),
    )
    ap.add_argument(
        "--match-id",
        default="",
        help="Optional stable id stored in inventory JSON for combined-corpus merges",
    )
    args = ap.parse_args(argv)
    log_path = args.log
    out_path = args.output
    frames_dir = args.frames_dir
    match_id = args.match_id.strip() or None

    print(f"Parsing {log_path}...")
    scout, events = parse_log(log_path)
    print(f"  scout records: {len(scout)}")
    print(f"  ball events:   {len(events)}")
    for ev in events:
        print(f"    F{ev['frame_count']} {ev['event']} @ {ev['over']}")

    print(f"\nScanning {frames_dir}/...")
    frame_files = defaultdict(list)  # frame_count -> [filename...]
    for fn in os.listdir(frames_dir):
        if not fn.endswith(".jpg"):
            continue
        m = re.match(r"f(\d+)_(.*)\.jpg$", fn)
        if not m:
            continue
        frame_files[int(m.group(1))].append(fn)
    print(f"  frames on disk: {len(frame_files)}")

    records = []
    missing_scout = 0
    for fc in sorted(frame_files.keys()):
        sc = scout.get(fc)
        if not sc:
            missing_scout += 1
            continue
        files = sorted(frame_files[fc])
        scoreboard_file = next(
            (f for f in files if "_scoreboard.jpg" in f), None)
        primary = scoreboard_file or files[0]
        ev = nearest_event(sc["ts"], events, fc)
        rec = {
            "frame_count": fc,
            "frame_path": f"{frames_dir}/{primary}",
            "all_files": files,
            "ts": sc["ts"],
            "scout_frame_type": sc["frame_type"],
            "scout_cam": sc["cam"],
            "scout_phase": sc["phase"],
            "scout_has_strip": sc["strip"],
            "scout_has_overlay": sc["overlay"],
            "scout_drs": sc["drs"],
            "scout_ms": sc["ms"],
            "nearest_event": ev,
        }
        records.append(rec)
    print(f"  scout-matched: {len(records)}, "
          f"missing-scout: {missing_scout}")

    envelope = {
        "source_log": log_path,
        "total_events": len(events),
        "events": events,
        "frames": records,
    }
    if match_id:
        envelope["match_id"] = match_id
    with open(out_path, "w") as f:
        json.dump(envelope, f, indent=2)
    print(f"\nWrote {out_path}")

    print("\n=== Cam distribution (across saved SCOREBOARD frames) ===")
    cam_dist = defaultdict(int)
    for r in records:
        if r["scout_frame_type"] == "SCOREBOARD":
            cam_dist[r["scout_cam"]] += 1
    for k, v in sorted(cam_dist.items(), key=lambda x: -x[1]):
        print(f"  {k:20s} {v}")

    print("\n=== Phase distribution ===")
    phase_dist = defaultdict(int)
    for r in records:
        if r["scout_frame_type"] == "SCOREBOARD":
            phase_dist[r["scout_phase"]] += 1
    for k, v in sorted(phase_dist.items(), key=lambda x: -x[1]):
        print(f"  {k:20s} {v}")

    print("\n=== Frames near ball events (within ±5 frames) ===")
    near_events = [r for r in records
                   if (r["nearest_event"]["delta_frames"] is not None
                       and abs(r["nearest_event"]["delta_frames"]) <= 5)]
    print(f"  count: {len(near_events)}")
    evs = defaultdict(int)
    for r in near_events:
        evs[r["nearest_event"]["event"]] += 1
    for k, v in sorted(evs.items(), key=lambda x: -x[1]):
        print(f"    {k}: {v}")


if __name__ == "__main__":
    main()
