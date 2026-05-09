#!/usr/bin/env python3
"""Block-level open-prose diagnostic for the 7 iter7 blocks."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cluster_level_qa import (  # noqa: E402
    SYSTEM, GROQ_KEY, MODEL, load_frames, signal_richest_sample,
)
from detect_delivery_zones import Frame  # noqa: E402

OUT_PATH = REPO_ROOT / "files/scripts/broadcast_mode_tuning/block_level_open_diag.txt"

ITER7_BLOCKS = [
    (101.0, 110.0),
    (122.0, 147.0),
    (161.0, 164.0),
    (176.0, 179.0),
    (182.0, 197.0),
    (234.0, 244.0),
    (272.0, 278.0),
]


def build_payload(block_id: int, start: float, end: float,
                  all_frames: list[Frame]) -> dict:
    in_block = [f for f in all_frames if start <= f.rel_t <= end]
    sampled = signal_richest_sample(in_block)
    signal_summary = {
        "V": sum(1 for f in in_block if f.has_action_verb),
        "S": sum(1 for f in in_block if f.has_strong_score),
        "M": sum(1 for f in in_block if f.has_multi_actor),
        "W": sum(1 for f in in_block if f.has_wide_field),
        "K": sum(1 for f in in_block if f.has_weak_info),
    }
    path_summary = {"A": 0, "B": 0, "C": 0, "none": 0}
    for f in in_block:
        path_summary[f.path] = path_summary.get(f.path, 0) + 1
    return {
        "block_id": block_id,
        "start_t": start,
        "end_t": end,
        "duration_s": end - start,
        "frame_count": len(in_block),
        "signal_summary": signal_summary,
        "path_summary": path_summary,
        "sampled_frames": sampled,
    }


def build_prompt(p: dict) -> str:
    s = p["signal_summary"]
    a = p["path_summary"]
    lines = [
        f"Cluster: {p['start_t']:.1f}s -> {p['end_t']:.1f}s, "
        f"{p['duration_s']:.1f}s, {p['frame_count']} frames.",
        f"Signals: V={s['V']} S={s['S']} M={s['M']} W={s['W']} K={s['K']}.",
        f"Paths: A={a['A']} B={a['B']} C={a['C']} none={a['none']}.",
        "Sampled descriptions:",
    ]
    for f in p["sampled_frames"]:
        lines.append(f"[t={f.rel_t:.1f}] {f.text}")
    lines.extend([
        "",
        "Tell me what's happening in this segment. Specifically:",
        "- Is this a live delivery, replay, pre-match, or break in play?",
        "- If multiple distinct events occur, identify each one with "
        "approximate timestamps from the cluster window.",
        "- Cite specific frame timestamps as evidence.",
        "- What makes you confident or uncertain?",
        "",
        "3-6 sentences. No JSON.",
    ])
    return "\n".join(lines)


def call(client, prompt: str) -> tuple[str, str | None]:
    last_err = None
    for attempt in range(2):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                temperature=0.2,
                max_tokens=500,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            )
            return (resp.choices[0].message.content or "").strip(), None
        except Exception as e:  # noqa: BLE001
            last_err = repr(e)
            time.sleep(1.0)
    return "", last_err


def main() -> int:
    from groq import Groq
    client = Groq(api_key=GROQ_KEY, timeout=20.0)
    frames = load_frames()
    print(f"Loaded {len(frames)} frames")

    out_lines: list[str] = []
    t0 = time.time()
    for i, (start, end) in enumerate(ITER7_BLOCKS, 1):
        payload = build_payload(i, start, end, frames)
        prose, err = call(client, build_prompt(payload))
        s = payload["signal_summary"]
        a = payload["path_summary"]
        header = (f"=== Block {i}: {start:.0f}-{end:.0f}s "
                  f"({end - start:.0f}s, {payload['frame_count']} frames) ===")
        meta = (f"[paths A={a['A']} B={a['B']} C={a['C']} none={a['none']}; "
                f"signals V={s['V']} S={s['S']} M={s['M']} W={s['W']} K={s['K']}]")
        body = prose if prose else f"(ERROR: {err})"
        print(header)
        print(meta)
        print(body)
        print()
        out_lines += [header, meta, body, ""]
    dt = time.time() - t0
    print(f"Wall: {dt:.1f}s")
    OUT_PATH.write_text("\n".join(out_lines))
    print(f"Wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
