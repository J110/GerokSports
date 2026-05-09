#!/usr/bin/env python3
"""Open-prompt pilot: ask the reasoner to free-form describe two contrasting clusters."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cluster_qa_experiment import (  # noqa: E402
    build_payload, load_frames, GROQ_KEY,
)

OUT_PATH = REPO_ROOT / "files/scripts/broadcast_mode_tuning/cluster_qa_open_pilot.txt"

PILOT_BLOCKS = [
    (2, 122.0, 147.0),
    (3, 161.0, 164.0),
]

MODEL = "llama-3.3-70b-versatile"


def build_prompt(p: dict) -> str:
    lines = [
        f"Below are 1fps frame descriptions from a cricket broadcast, "
        f"spanning {p['duration_s']:.0f}s. Each frame is captioned by a "
        "vision model.",
        "",
    ]
    for f in p["sampled_frames"]:
        lines.append(f"[t={f['t']:.1f}s] {f['open_description']}")
    lines.extend([
        "",
        f"Aggregate signals across the cluster: {p['signal_summary']}.",
        "",
        "Tell me what's happening in this segment. Specifically:",
        "- Is this a live delivery, replay, or something else?",
        "- If multiple distinct events occur, identify each one with "
        "approximate timestamps.",
        "- What visual evidence makes you confident or uncertain?",
        "",
        "Answer in plain prose, 3-6 sentences. No JSON.",
    ])
    return "\n".join(lines)


def main() -> int:
    from groq import Groq
    client = Groq(api_key=GROQ_KEY, timeout=20.0)
    frames = load_frames()

    out_lines: list[str] = []
    for block_id, start, end in PILOT_BLOCKS:
        payload = build_payload(block_id, start, end, frames)
        prompt = build_prompt(payload)
        resp = client.chat.completions.create(
            model=MODEL,
            temperature=0.2,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.choices[0].message.content or ""
        header = (f"=== Block {block_id}: {start:.0f}-{end:.0f}s "
                  f"({end - start:.0f}s, {payload['frame_count']} frames) ===")
        print(header)
        print(text)
        print()
        out_lines += [header, text, ""]

    OUT_PATH.write_text("\n".join(out_lines))
    print(f"Wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
