"""2x2 attribution test:

  axis 1 — clip fidelity:  HIGH (1920x1241, 30/60fps, ~3.5 Mbps)
                           LOW  (720x486,  10fps,    ~0.4 Mbps  — pipeline output)
  axis 2 — prompt:         OLD  (PROMPT_STRUCT, two-step, no "score advanced" prior)
                           NEW  (PROMPT_FULL, one-step, asserts "delivery DEFINITELY occurred")

We run all 4 cells on a balanced set of clips:
  - 2 high-fid OLD clips with truth (square shot / short-steep-pull)
  - 3 low-fid YouTube clips with truth (w19=defend / w21=short-pull / w23=short-cut)

Per-cell, we run BOTH prompts on EACH clip to disentangle effects.
Per-clip diversity also reveals modal-collapse: are the answers
identical across different deliveries within a cell?
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from eyes.config import GEMINI_API_KEY
os.environ.setdefault("GEMINI_API_KEY", GEMINI_API_KEY)

from gemini_ab_schema_test import PROMPT_FULL, parse_json
from test_gemini_video_v2 import PROMPT_STRUCT

MODEL = "gemini-3-flash-preview"

CLIPS = [
    {"id": "old1", "fidelity": "HIGH",
     "path": "ball_test_clip_30fps.mp4",
     "truth_length": None,
     "truth_shot": None,
     "label": "Apr10: LEFT-handed, square defence"},
    {"id": "old2", "fidelity": "HIGH",
     "path": "ball_test_clip_60fps_long.mp4",
     "truth_length": "short",
     "truth_shot": "pull",
     "label": "Apr10: SHORT/steep, pull"},
    {"id": "w19", "fidelity": "LOW",
     "path": "logs/deliveries/20260420_140137/windows/window_0019/delivery_window.mp4",
     "truth_length": None,
     "truth_shot": "defend",
     "label": "YT 3.0: round-arm, on stumps, defend"},
    {"id": "w21", "fidelity": "LOW",
     "path": "logs/deliveries/20260420_140137/windows/window_0021/delivery_window.mp4",
     "truth_length": "short",
     "truth_shot": "pull",
     "label": "YT 3.1: SHORT, off stump, pull (inside-edged)"},
    {"id": "w23", "fidelity": "LOW",
     "path": "logs/deliveries/20260420_140137/windows/window_0023/delivery_window.mp4",
     "truth_length": "short",
     "truth_shot": "cut",
     "label": "YT 3.2: SHORT, outside off, cut for FOUR"},
]

PROMPTS = [("OLD", PROMPT_STRUCT), ("NEW", PROMPT_FULL)]


def call(client, types, data, prompt):
    parts = [
        types.Part.from_bytes(data=data, mime_type="video/mp4"),
        types.Part.from_text(text=prompt),
    ]
    t0 = time.time()
    resp = client.models.generate_content(model=MODEL, contents=parts)
    ms = int((time.time() - t0) * 1000)
    served = getattr(resp, "model_version", None) or "?"
    return resp.text or "", ms, served


def normalise_length(v):
    """The two prompts use slightly different enums; normalise."""
    if v is None:
        return None
    v = str(v).lower()
    if v in {"short_of_a_length", "short_of_length"}:
        return "short_of_length"
    return v


def main():
    from google import genai
    from google.genai import types
    client = genai.Client()

    print(f"requested model: {MODEL}\n")
    rows = []
    for clip in CLIPS:
        path = ROOT / clip["path"]
        if not path.exists():
            print(f"missing clip: {path}")
            continue
        data = path.read_bytes()
        size_kb = len(data) / 1024
        print(f"=== {clip['id']:5s} {clip['fidelity']:4s} "
              f"{size_kb:7.0f} KB — {clip['label']} ===")

        for tag, prompt in PROMPTS:
            raw, ms, served = call(client, types, data, prompt)
            parsed = parse_json(raw) or {}
            length = normalise_length(parsed.get("length"))
            shot = parsed.get("shot_type")
            line = parsed.get("line")
            bounce = parsed.get("bounce")
            ang = parsed.get("bowling_angle")
            tl = clip["truth_length"]
            ts = clip["truth_shot"]
            mark_l = ("✓" if (tl and length == tl)
                      else ("✗" if tl else "·"))
            mark_s = ("✓" if (ts and shot == ts)
                      else ("✗" if ts else "·"))
            print(f"   {tag} ({ms/1000:4.1f}s, served={served}): "
                  f"len={length} {mark_l}  "
                  f"shot={shot} {mark_s}  "
                  f"line={line}  bounce={bounce}  ang={ang}")
            rows.append({
                "clip": clip["id"],
                "fidelity": clip["fidelity"],
                "prompt": tag,
                "served_model": served,
                "ms": ms,
                "truth_length": tl,
                "truth_shot": ts,
                "pred_length": length,
                "pred_shot": shot,
                "pred_line": line,
                "pred_bounce": bounce,
                "pred_angle": ang,
                "raw": raw,
            })
        print()

    out = ROOT / "logs" / "audit_v1" / "ab_schema_test" / "two_by_two.json"
    out.write_text(json.dumps(rows, indent=2, default=str))
    print(f"wrote {out}")

    # Summary
    print("\n=== summary ===")
    for fid in ("HIGH", "LOW"):
        for prompt in ("OLD", "NEW"):
            cell = [r for r in rows
                    if r["fidelity"] == fid and r["prompt"] == prompt]
            if not cell:
                continue
            n_l = sum(1 for r in cell
                      if r["truth_length"] is not None)
            n_l_ok = sum(1 for r in cell
                         if r["truth_length"] is not None
                         and r["pred_length"] == r["truth_length"])
            n_s = sum(1 for r in cell
                      if r["truth_shot"] is not None)
            n_s_ok = sum(1 for r in cell
                         if r["truth_shot"] is not None
                         and r["pred_shot"] == r["truth_shot"])
            distinct_lengths = len({r["pred_length"]
                                    for r in cell})
            distinct_tuples = len({(r["pred_length"], r["pred_shot"],
                                    r["pred_line"], r["pred_bounce"],
                                    r["pred_angle"]) for r in cell})
            print(f"  fid={fid:4s} prompt={prompt}: "
                  f"length={n_l_ok}/{n_l}  "
                  f"shot={n_s_ok}/{n_s}  "
                  f"distinct length values={distinct_lengths}/"
                  f"{len(cell)}  "
                  f"distinct full-tuples={distinct_tuples}/"
                  f"{len(cell)}")


if __name__ == "__main__":
    main()
