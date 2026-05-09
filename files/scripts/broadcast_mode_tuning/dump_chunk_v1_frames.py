#!/usr/bin/env python3
"""Frame-by-frame dump of chunk_v1_combined_data.csv.

Writes chunk_v1_frame_dump.txt with one section per clip, listing every
sampled frame's prod_cam, prod_phase, v2_broadcast_tag, v2_class, and
the verbatim open_desc.  Reads window_debug.json per clip for duration
and event_ts.

Usage::
    cd files/scripts/broadcast_mode_tuning
    python3 dump_chunk_v1_frames.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent.parent
DELIVERIES_DIR = REPO_ROOT / "files" / "logs" / "deliveries"
LABEL_CSV = REPO_ROOT / "files" / "scripts" / "path_a_baseline" / "clip_aggregates_v2.csv"
SRC_CSV = SCRIPT_DIR / "chunk_v1_combined_data.csv"
OUT_TXT = SCRIPT_DIR / "chunk_v1_frame_dump.txt"


def read_window_meta(session: str, clip_id: str) -> tuple[float, float]:
    p = DELIVERIES_DIR / session / clip_id / "window_debug.json"
    try:
        meta = json.loads(p.read_text())
        return (meta["clip_end_ts"] - meta["clip_start_ts"],
                meta["event_ts"] - meta["clip_start_ts"])
    except Exception:
        return float("nan"), float("nan")


def label_lookup() -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    with LABEL_CSV.open() as f:
        for r in csv.DictReader(f):
            out[(r["session"], r["clip_id"])] = r["manual_label"]
    return out


def main() -> None:
    with SRC_CSV.open() as f:
        rows = list(csv.DictReader(f))

    # Group by (session, clip_id) preserving order of first appearance.
    groups: dict[tuple[str, str], list[dict]] = {}
    order: list[tuple[str, str]] = []
    for r in rows:
        key = (r["session"], r["clip_id"])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)

    labels = label_lookup()
    out_lines: list[str] = []

    def emit(line: str = "") -> None:
        out_lines.append(line)

    for session, clip_id in order:
        duration, event = read_window_meta(session, clip_id)
        label = labels.get((session, clip_id), "N/A")
        emit("=" * 70)
        emit(f"[CLIP {session}/{clip_id}]")
        emit(f"  duration={duration:.2f}s event_ts={event:.2f}s")
        emit(f"  manual_label={label}")
        emit("")
        for r in groups[(session, clip_id)]:
            ts = float(r["ts"])
            prod_cam = r["prod_cam"] or "(unset)"
            prod_phase = r["prod_phase"] or "(unset)"
            v2_tag = r["v2_broadcast_tag"]
            v2_class = r["v2_class"]
            open_desc = (r["open_desc"] or "").strip()
            emit(f"  ts={ts:6.2f}s")
            emit(f"    prod_cam={prod_cam}")
            emit(f"    prod_phase={prod_phase}")
            emit(f"    v2_broadcast={v2_tag}")
            emit(f"    v2_class={v2_class}")
            emit(f"    open_desc: \"{open_desc}\"")
            emit("")
        emit("")

    OUT_TXT.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_TXT} ({len(rows)} frames across {len(order)} clips)")


if __name__ == "__main__":
    main()
