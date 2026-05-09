"""Qwen full-matrix attribution test — direct counterpart to
gemini_full_matrix_test.py.

  models   — qwen3-vl-30b-a3b-instruct, qwen3-vl-30b-a3b-thinking
             (the only Qwen3-VL variants on Fireworks serverless;
             8B / 32B / 235B require dedicated GPU deployments)
  prompts  — OLD, NEW, CLEAN  (identical to the Gemini matrix so the
             two reports are directly comparable cell-by-cell)
  clips    — same 5 clips as the Gemini matrix
  reps     — n=3 per cell

INPUT SHAPE — important caveat
==============================
Fireworks serverless does NOT accept video_url for Qwen3-VL: docs say
"Video models are not available on serverless; dedicated deployment
required" (the only video-capable serverless option is Qwen3-Omni and
even that needs a custom deployment).

Per the user's "3 frames is useless" feedback we send a DENSE FRAME
BURST instead:  N_BURST frames extracted at evenly-spaced positions
across the clip (so the burst spans the full delivery — runup, bounce,
contact, follow-through).  This is materially more temporal signal
than the old 3-frame approach but is NOT native video sampling.  Read
the report headers accordingly.

Output:
  logs/audit_v1/qwen_matrix/full_matrix.json
  logs/audit_v1/qwen_matrix/full_matrix_report.md

Cost: ~90 calls × ~3000 input tokens ≈ ~$0.50 incl. thinking tokens.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import cv2

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# Reuse the EXACT same prompts as the Gemini matrix so the two reports
# are line-for-line comparable.
from gemini_ab_schema_test import PROMPT_FULL  # = NEW
from gemini_full_matrix_test import PROMPT_CLEAN  # = CLEAN
from test_gemini_video_v2 import PROMPT_STRUCT  # = OLD

PROMPTS = [
    ("OLD",   PROMPT_STRUCT),
    ("NEW",   PROMPT_FULL),
    ("CLEAN", PROMPT_CLEAN),
]

# ─── Fireworks ───
FIREWORKS_API_KEY = os.environ.get(
    "FIREWORKS_API_KEY",
    "fw_8Kyu9Ug7kXVp6kPRDvhL3n",
)

MODELS = [
    ("qwen30b-instruct",
     "accounts/fireworks/models/qwen3-vl-30b-a3b-instruct",
     800),    # max_tokens for non-thinking variant
    ("qwen30b-thinking",
     "accounts/fireworks/models/qwen3-vl-30b-a3b-thinking",
     3072),   # thinking variant needs lots of headroom
]
N_REPS = 3

# Number of frames to send per clip (the "dense frame burst").  16 at
# 720p ~ 16 × ~50 KB ≈ 800 KB, well under Fireworks' 10 MB payload cap.
N_BURST = 16
JPEG_Q = 88


# ─── clips: same five as the Gemini matrix ───
CONTROL_CLIPS = [
    {"id": "ctrl_old2", "fidelity": "HIGH", "control": True,
     "path": "ball_test_clip_60fps_long.mp4",
     "truth_length": "short",
     "truth_shot": "pull",
     "truth_handed": "right",
     "label": "CONTROL: Apr10 hi-fid SHORT/steep/pull (verified)"},
]

WORKING_CLIPS = [
    {"id": "old1", "fidelity": "HIGH",
     "path": "ball_test_clip_30fps.mp4",
     "truth_length": None,
     "truth_shot": "defend",
     "truth_handed": "left",
     "label": "Apr10 hi-fid: LEFT-handed defence square of wicket"},
    {"id": "w19", "fidelity": "LOW",
     "path": "logs/deliveries/20260420_140137/windows/window_0019/delivery_window.mp4",
     "truth_length": None,
     "truth_shot": "defend",
     "truth_handed": "right",
     "label": "YT 3.0: round-arm, on stumps, defend (Mendis)"},
    {"id": "w21", "fidelity": "LOW",
     "path": "logs/deliveries/20260420_140137/windows/window_0021/delivery_window.mp4",
     "truth_length": "short",
     "truth_shot": "pull",
     "truth_handed": "right",
     "label": "YT 3.1: SHORT, off stump, pull (inside-edged)"},
    {"id": "w23", "fidelity": "LOW",
     "path": "logs/deliveries/20260420_140137/windows/window_0023/delivery_window.mp4",
     "truth_length": "short",
     "truth_shot": "cut",
     "truth_handed": "right",
     "label": "YT 3.2: SHORT, outside off, cut for FOUR"},
]

CLIPS = CONTROL_CLIPS + WORKING_CLIPS


# ─── helpers ───

def normalise_length(v):
    if v is None:
        return None
    v = str(v).lower()
    if v in {"short_of_a_length", "short_of_length"}:
        return "short_of_length"
    return v


def parse_json(text: str):
    """Strip ```json fences, find the LAST {...} block (thinking models
    often emit reasoning prose first, JSON last)."""
    if not text:
        return None
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    matches = list(re.finditer(r"\{[\s\S]*?\}", text))
    if not matches:
        # Try greedy single match
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    # Try matches from largest to smallest (largest is most likely the
    # full JSON object).
    matches.sort(key=lambda m: -(m.end() - m.start()))
    for m in matches:
        try:
            return json.loads(m.group(0))
        except Exception:
            continue
    # Final fallback: greedy span
    g = re.search(r"\{[\s\S]*\}", text)
    if g:
        try:
            return json.loads(g.group(0))
        except Exception:
            return None
    return None


def extract_burst(mp4_path: str, n: int) -> list[bytes]:
    """Extract n JPEG frames evenly spaced across the clip."""
    cap = cv2.VideoCapture(mp4_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        cap.release()
        return []
    indices = [int(total * (i + 0.5) / n) for i in range(n)]
    out = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            continue
        ok, jpg = cv2.imencode(".jpg", frame,
                               [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_Q])
        if ok:
            out.append(jpg.tobytes())
    cap.release()
    return out


def make_messages(frames: list[bytes], prompt_text: str):
    content = []
    for i, f in enumerate(frames):
        b = base64.b64encode(f).decode()
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b}"},
        })
    # Frame-burst preamble so the model knows it's a temporal sequence,
    # not unrelated images.
    preamble = (
        f"Below are {len(frames)} keyframes extracted at "
        f"evenly-spaced timestamps from a single short video clip "
        f"(8-15 seconds) of one cricket delivery.  Treat them as a "
        f"chronological sequence — first frame is the start of the "
        f"clip, last frame is the end.  Use the temporal progression "
        f"between frames to infer ball flight, bounce, and contact.\n\n"
    )
    content.append({"type": "text", "text": preamble + prompt_text})
    return [{"role": "user", "content": content}]


def call(client, model_id: str, frames: list[bytes], prompt_text: str,
         max_tokens: int):
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=model_id,
            messages=make_messages(frames, prompt_text),
            max_tokens=max_tokens,
            temperature=0.2,
        )
        ms = int((time.time() - t0) * 1000)
        usage = resp.usage
        text = resp.choices[0].message.content or ""
        return text, ms, getattr(usage, "prompt_tokens", 0), \
            getattr(usage, "completion_tokens", 0), None
    except Exception as e:  # noqa: BLE001
        ms = int((time.time() - t0) * 1000)
        return "", ms, 0, 0, str(e)[:300]


def main():
    from openai import OpenAI
    client = OpenAI(
        base_url="https://api.fireworks.ai/inference/v1",
        api_key=FIREWORKS_API_KEY,
    )

    out_dir = ROOT / "logs" / "audit_v1" / "qwen_matrix"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Pre-extract frame bursts once per clip (frames are deterministic).
    bursts: dict[str, list[bytes]] = {}
    for clip in CLIPS:
        path = ROOT / clip["path"]
        if not path.exists():
            print(f"  missing: {path}")
            continue
        frames = extract_burst(str(path), N_BURST)
        bursts[clip["id"]] = frames
        total_kb = sum(len(f) for f in frames) / 1024
        print(f"clip {clip['id']:10s} {clip['fidelity']:4s}  "
              f"{len(frames)} frames, {total_kb:6.0f} KB total — "
              f"{clip['label']}")
    print()

    rows = []
    n_calls = sum(1 for c in CLIPS if c["id"] in bursts) \
        * len(MODELS) * len(PROMPTS) * N_REPS
    i = 0
    for clip in CLIPS:
        frames = bursts.get(clip["id"])
        if not frames:
            continue
        print(f"\n{'='*78}")
        print(f"clip {clip['id']:10s} {clip['fidelity']:4s} — "
              f"{clip['label']}")
        print(f"{'='*78}")

        for model_tag, model_id, max_tok in MODELS:
            for prompt_tag, prompt in PROMPTS:
                for rep in range(N_REPS):
                    i += 1
                    text, ms, in_tok, out_tok, err = call(
                        client, model_id, frames, prompt, max_tok)
                    parsed = parse_json(text) or {}
                    length = normalise_length(parsed.get("length"))
                    shot = parsed.get("shot_type")
                    line = parsed.get("line")
                    bounce = parsed.get("bounce")
                    ang = parsed.get("bowling_angle")
                    handed = parsed.get("batsman_handed")

                    tl = clip["truth_length"]
                    ts = clip["truth_shot"]
                    th = clip["truth_handed"]

                    def mk(truth, pred):
                        if truth is None:
                            return "·"
                        if pred is None:
                            return "?"
                        return "✓" if pred == truth else "✗"

                    err_str = f" ERR={err[:60]}" if err else ""
                    print(f"  [{i:3d}/{n_calls}] {model_tag:18s} "
                          f"{prompt_tag:5s} rep{rep+1} ({ms/1000:5.1f}s "
                          f"in={in_tok} out={out_tok})  "
                          f"len={length} {mk(tl, length)}  "
                          f"shot={shot} {mk(ts, shot)}  "
                          f"hand={handed} {mk(th, handed)}{err_str}")

                    rows.append({
                        "clip": clip["id"],
                        "fidelity": clip["fidelity"],
                        "model": model_tag,
                        "served_model": model_id,
                        "prompt": prompt_tag,
                        "rep": rep + 1,
                        "ms": ms,
                        "in_tok": in_tok,
                        "out_tok": out_tok,
                        "error": err,
                        "truth_length": tl,
                        "truth_shot": ts,
                        "truth_handed": th,
                        "pred_length": length,
                        "pred_shot": shot,
                        "pred_line": line,
                        "pred_bounce": bounce,
                        "pred_angle": ang,
                        "pred_handed": handed,
                        "raw": text,
                    })

                    # Persist incrementally so a mid-run failure isn't fatal
                    if i % 6 == 0:
                        (out_dir / "full_matrix.json").write_text(
                            json.dumps(rows, indent=2, default=str))

    out_json = out_dir / "full_matrix.json"
    out_json.write_text(json.dumps(rows, indent=2, default=str))
    print(f"\nWrote {out_json}  ({len(rows)} rows)")

    md = render_report(rows)
    out_md = out_dir / "full_matrix_report.md"
    out_md.write_text(md)
    print(f"Wrote {out_md}\n")


# ─── report (mirrors the Gemini one for cell-by-cell comparison) ───

def pct(num, den):
    if den == 0:
        return "n/a"
    return f"{100*num/den:.0f}%"


def render_report(rows: list[dict]) -> str:
    out = [
        f"# Qwen full-matrix attribution — report\n",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Models: {', '.join(m[0] for m in MODELS)}",
        f"Prompts: {', '.join(t for t, _ in PROMPTS)}",
        f"Reps per cell: {N_REPS}",
        f"Input shape: dense frame burst, **N={N_BURST} frames** "
        f"per clip (Fireworks serverless does NOT accept video_url "
        f"for Qwen3-VL).  These results are NOT directly comparable "
        f"to a native-video model on the temporal axis — but they "
        f"ARE directly comparable to each other across (model, prompt, "
        f"clip) cells.\n",
    ]

    # ─── CONTROL CLIPS ───
    control_ids = {c["id"] for c in CONTROL_CLIPS}
    control_rows = [r for r in rows if r["clip"] in control_ids]
    if control_rows:
        out.append("## CONTROL CLIPS — drift detection across runs\n")
        out.append("| clip | model | prompt | length acc | shot acc | "
                   "mode_length | reps |")
        out.append("|---|---|---|---|---|---|---|")
        for ctl in CONTROL_CLIPS:
            for model_tag, _, _ in MODELS:
                for prompt_tag, _ in PROMPTS:
                    cell = [r for r in control_rows
                            if r["clip"] == ctl["id"]
                            and r["model"] == model_tag
                            and r["prompt"] == prompt_tag]
                    if not cell:
                        continue
                    lens = [r["pred_length"] for r in cell]
                    shots = [r["pred_shot"] for r in cell]
                    tl = ctl["truth_length"]
                    ts = ctl["truth_shot"]
                    n_l_ok = sum(1 for v in lens if tl and v == tl)
                    n_s_ok = sum(1 for v in shots if ts and v == ts)
                    mode_l = Counter(v for v in lens if v).most_common(1)
                    ml = (f"{mode_l[0][0]}({mode_l[0][1]})"
                          if mode_l else "—")
                    out.append(
                        f"| {ctl['id']} | {model_tag} "
                        f"| {prompt_tag} | "
                        f"{n_l_ok}/{len(cell)} | "
                        f"{n_s_ok}/{len(cell)} | {ml} | {len(cell)} |")
        out.append("")

    # ─── per-cell ───
    out.append("## Per-cell summary (averaged over n=3 reps)\n")
    out.append("| clip | fid | model | prompt | n_ok_len/n_truth | "
               "n_ok_shot/n_truth | distinct_len | mode_len | "
               "mode_shot | avg ms |")
    out.append("|---|---|---|---|---|---|---|---|---|---|")

    by_cell = {}
    for r in rows:
        key = (r["clip"], r["model"], r["prompt"])
        by_cell.setdefault(key, []).append(r)

    for clip in CLIPS:
        for model_tag, _, _ in MODELS:
            for prompt_tag, _ in PROMPTS:
                key = (clip["id"], model_tag, prompt_tag)
                cell = by_cell.get(key, [])
                if not cell:
                    continue
                tl = clip["truth_length"]
                ts = clip["truth_shot"]
                lens = [r["pred_length"] for r in cell]
                shots = [r["pred_shot"] for r in cell]
                n_l_ok = sum(1 for v in lens
                             if tl is not None and v == tl)
                n_l_truth = (len(cell) if tl is not None else 0)
                n_s_ok = sum(1 for v in shots
                             if ts is not None and v == ts)
                n_s_truth = (len(cell) if ts is not None else 0)
                distinct = len({v for v in lens if v is not None})
                mode_l = Counter(v for v in lens if v).most_common(1)
                mode_s = Counter(v for v in shots if v).most_common(1)
                ml = (f"{mode_l[0][0]}({mode_l[0][1]})"
                      if mode_l else "—")
                ms_v = (f"{mode_s[0][0]}({mode_s[0][1]})"
                        if mode_s else "—")
                avg_ms = int(sum(r["ms"] for r in cell) / len(cell))
                out.append(
                    f"| {clip['id']} | {clip['fidelity']} | "
                    f"{model_tag} | {prompt_tag} | "
                    f"{n_l_ok}/{n_l_truth} | {n_s_ok}/{n_s_truth} | "
                    f"{distinct} | {ml} | {ms_v} | {avg_ms} |")

    # ─── aggregate ───
    out.append("\n## Aggregate accuracy by (model, prompt) — "
               "across all clips × reps that have truth\n")
    out.append("| model | prompt | length acc | shot acc | "
               "handed acc | avg ms |")
    out.append("|---|---|---|---|---|---|")
    for model_tag, _, _ in MODELS:
        for prompt_tag, _ in PROMPTS:
            cell = [r for r in rows
                    if r["model"] == model_tag and r["prompt"] == prompt_tag]
            n_l = sum(1 for r in cell if r["truth_length"])
            n_l_ok = sum(1 for r in cell
                         if r["truth_length"]
                         and r["pred_length"] == r["truth_length"])
            n_s = sum(1 for r in cell if r["truth_shot"])
            n_s_ok = sum(1 for r in cell
                         if r["truth_shot"]
                         and r["pred_shot"] == r["truth_shot"])
            n_h = sum(1 for r in cell if r["truth_handed"])
            n_h_ok = sum(1 for r in cell
                         if r["truth_handed"]
                         and r["pred_handed"] == r["truth_handed"])
            avg_ms = (int(sum(r["ms"] for r in cell) / len(cell))
                      if cell else 0)
            out.append(
                f"| {model_tag} | {prompt_tag} | "
                f"{n_l_ok}/{n_l} ({pct(n_l_ok, n_l)}) | "
                f"{n_s_ok}/{n_s} ({pct(n_s_ok, n_s)}) | "
                f"{n_h_ok}/{n_h} ({pct(n_h_ok, n_h)}) | "
                f"{avg_ms} |")

    # ─── modal collapse ───
    out.append("\n## Modal-collapse view — "
               "length distribution per (model, prompt, fidelity)\n")
    out.append("| model | prompt | fidelity | length distribution |")
    out.append("|---|---|---|---|")
    for model_tag, _, _ in MODELS:
        for prompt_tag, _ in PROMPTS:
            for fid in ("HIGH", "LOW"):
                cell = [r for r in rows
                        if r["model"] == model_tag
                        and r["prompt"] == prompt_tag
                        and r["fidelity"] == fid]
                ctr = Counter(r["pred_length"] for r in cell
                              if r["pred_length"])
                dist = ", ".join(f"`{k}`×{n}"
                                 for k, n in ctr.most_common())
                out.append(
                    f"| {model_tag} | {prompt_tag} | "
                    f"{fid} | {dist} |")

    # ─── per-clip rep variance ───
    out.append("\n## Per-clip rep variance (length only)\n")
    out.append("| clip | truth | model+prompt | rep1 | rep2 | rep3 |")
    out.append("|---|---|---|---|---|---|")
    for clip in CLIPS:
        for model_tag, _, _ in MODELS:
            for prompt_tag, _ in PROMPTS:
                cell = sorted(
                    by_cell.get((clip["id"], model_tag, prompt_tag), []),
                    key=lambda r: r["rep"])
                if not cell:
                    continue
                vals = [r["pred_length"] or "—" for r in cell]
                tl = clip["truth_length"] or "—"
                marks = []
                for v in vals:
                    if clip["truth_length"] and v == clip["truth_length"]:
                        marks.append(f"**{v} ✓**")
                    else:
                        marks.append(v)
                while len(marks) < 3:
                    marks.append("—")
                out.append(
                    f"| {clip['id']} | {tl} | "
                    f"{model_tag}/{prompt_tag} | "
                    f"{marks[0]} | {marks[1]} | {marks[2]} |")

    # ─── error rows / parse failures ───
    err_rows = [r for r in rows if r["error"] or r["pred_length"] is None]
    if err_rows:
        out.append(f"\n## Parse failures / API errors ({len(err_rows)})\n")
        out.append("| clip | model | prompt | rep | ms | error | "
                   "raw[:120] |")
        out.append("|---|---|---|---|---|---|---|")
        for r in err_rows:
            err = (r["error"] or "")[:60]
            raw = (r["raw"] or "")[:120].replace("\n", " ")
            out.append(
                f"| {r['clip']} | {r['model']} | {r['prompt']} | "
                f"{r['rep']} | {r['ms']} | {err} | `{raw}` |")

    # ─── tokens / cost ───
    out.append("\n## Token & cost summary\n")
    out.append("| model | n calls | avg in_tok | avg out_tok | "
               "total in_tok | total out_tok |")
    out.append("|---|---|---|---|---|---|")
    for model_tag, _, _ in MODELS:
        cell = [r for r in rows if r["model"] == model_tag]
        if not cell:
            continue
        avg_in = int(sum(r["in_tok"] for r in cell) / len(cell))
        avg_out = int(sum(r["out_tok"] for r in cell) / len(cell))
        tot_in = sum(r["in_tok"] for r in cell)
        tot_out = sum(r["out_tok"] for r in cell)
        out.append(
            f"| {model_tag} | {len(cell)} | {avg_in} | {avg_out} | "
            f"{tot_in} | {tot_out} |")

    return "\n".join(out)


if __name__ == "__main__":
    main()
