"""Full matrix attribution test:

  models   — gemini-3-flash-preview, gemini-2.5-pro
  prompts  — OLD, NEW, CLEAN (NEW minus the prior-pulling language)
  clips    — 5 total (2 OLD high-fid with truth, 3 YouTube low-fid with truth)
  reps     — n=3 per cell

Goals:
  1. Decouple model effect from prompt effect from clip-fidelity effect.
  2. Measure single-call variance — is "good_length" collapse stable
     across replicates, or noisy?
  3. Pro vs Flash on the same input — does the bigger model break the
     modal-prior pull?

Output:
  logs/audit_v1/ab_schema_test/full_matrix.json
  logs/audit_v1/ab_schema_test/full_matrix_report.md

Cost: ~90 calls × $0.005 = ~$0.45.
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from eyes.config import GEMINI_API_KEY
os.environ.setdefault("GEMINI_API_KEY", GEMINI_API_KEY)

from gemini_ab_schema_test import PROMPT_FULL, parse_json
from test_gemini_video_v2 import PROMPT_STRUCT


# ───────────────── prompts ─────────────────

# CLEAN = PROMPT_FULL with the "delivery DEFINITELY occurred" framing
# removed and "unknown is BETTER than wrong" promoted to the top.
PROMPT_CLEAN = """\
You are watching a short video clip (8-15 s) of a single cricket \
delivery from the bowler's-end TV camera.

Your job: classify what you can ACTUALLY SEE.  "unknown" is always a \
valid answer and is STRONGLY PREFERRED over guessing.  Do NOT pull \
from cricket priors — for example, do NOT default length to \
"good_length" just because it is the modal IPL length.  If the \
bounce point is not clearly visible relative to the batter, length \
is "unknown".  This is non-negotiable.

If the clip does not actually contain a bowled delivery (replay only, \
fielding drill, walk-back, scoreboard graphic), set is_valid_delivery=\
false and "unknown" for the rest.

Return ONLY a single JSON object on one line.

{
  "is_valid_delivery":  true | false,
  "batsman_handed":     "right" | "left" | "unknown",
  "bowling_arm":        "right" | "left" | "unknown",
  "bowling_angle":      "over_the_wicket" | "round_the_wicket" | "unknown",
  "bowling_type":       "fast" | "medium" | "spin" | "unknown",
  "length":             "yorker" | "full" | "good_length" |
                        "short_of_length" | "short" | "bouncer" |
                        "full_toss" | "unknown",
  "line":               "wide_outside_off" | "outside_off" | "off_stump" |
                        "middle_stump" | "leg_stump" | "down_leg" |
                        "wide_down_leg" | "unknown",
  "bounce":             "low" | "normal" | "steep" | "extra" | "unknown",
  "shot_played":        true | false,
  "shot_type":          "leave" | "defend" | "drive" | "cut" | "pull" |
                        "hook" | "flick" | "glance" | "sweep" |
                        "reverse_sweep" | "slog" | "dab" | "ramp" |
                        "no_shot" | "unknown",
  "shot_side":          "off" | "leg" | "straight" | "behind" | "no_shot",
  "shot_angle":         "behind_wicket" | "square" | "mid" |
                        "down_ground" | "no_shot",
  "elevation":          "along_ground" | "in_air" | "no_shot",
  "contact_quality":    "middled" | "well_timed" | "mistimed" |
                        "edged" | "inside_edge" | "outside_edge" |
                        "off_pad" | "beaten" | "left_alone" | "missed" |
                        "unknown",
  "confidence":         "high" | "medium" | "low"
}
"""

PROMPTS = [
    ("OLD",   PROMPT_STRUCT),
    ("NEW",   PROMPT_FULL),
    ("CLEAN", PROMPT_CLEAN),
]

MODELS = ["gemini-3-flash-preview", "gemini-2.5-pro"]
N_REPS = 3


# ───────────────── clips ─────────────────

# CONTROL CLIPS — run on every matrix invocation forever.  These are
# the absolute-accuracy reference points: if a future matrix run shows
# noticeably different numbers on these specific clips, something
# outside our control has changed (model update, API change, encoder
# regression).  Without these, we can't distinguish "we improved" from
# "Google updated the model".
#
# Add a clip to this list ONLY if:
#   1. Ground truth is verified by hand against the broadcast.
#   2. The mp4 is at native fidelity from the capture pipeline (not
#      re-encoded later) so the answer reflects what live capture
#      actually produces.
#   3. The clip will exist on disk in this same path indefinitely.
#
# Initial seed: ball_test_clip_60fps_long.mp4 (Apr10 hi-fid, true =
# SHORT/steep/pull) — the clearest pre-fix length-determinable clip
# we have.  Add a fresh post-fix YouTube delivery as soon as one is
# captured + hand-graded.
CONTROL_CLIPS = [
    {"id": "ctrl_old2", "fidelity": "HIGH", "control": True,
     "path": "ball_test_clip_60fps_long.mp4",
     "truth_length": "short",
     "truth_shot": "pull",
     "truth_handed": "right",
     "label": "CONTROL: Apr10 hi-fid SHORT/steep/pull (verified)"},
    # TODO: add fresh YouTube control clip after first post-fix capture.
    # Format:
    # {"id": "ctrl_yt_<sessionid>_w<NN>", "fidelity": "HIGH",
    #  "control": True,
    #  "path": "logs/deliveries/<session>/windows/window_<NNNN>/delivery_window.mp4",
    #  "truth_length": "...", "truth_shot": "...", "truth_handed": "...",
    #  "label": "CONTROL: YT <over.ball> <one-line description>"},
]

# WORKING CLIPS — the current investigation set.  Rotate these freely
# as we capture new data; do NOT remove control clips.
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


# ───────────────── runner ─────────────────

def normalise_length(v):
    if v is None:
        return None
    v = str(v).lower()
    if v in {"short_of_a_length", "short_of_length"}:
        return "short_of_length"
    return v


def call(client, types, model, data, prompt):
    parts = [
        types.Part.from_bytes(data=data, mime_type="video/mp4"),
        types.Part.from_text(text=prompt),
    ]
    t0 = time.time()
    try:
        resp = client.models.generate_content(model=model, contents=parts)
        ms = int((time.time() - t0) * 1000)
        served = getattr(resp, "model_version", None) or "?"
        return resp.text or "", ms, served, None
    except Exception as e:  # noqa: BLE001
        ms = int((time.time() - t0) * 1000)
        return "", ms, "?", str(e)[:200]


def main():
    from google import genai
    from google.genai import types
    client = genai.Client()

    out_dir = ROOT / "logs" / "audit_v1" / "ab_schema_test"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    n_calls = len(CLIPS) * len(MODELS) * len(PROMPTS) * N_REPS
    i = 0
    for clip in CLIPS:
        path = ROOT / clip["path"]
        if not path.exists():
            print(f"  missing: {path}")
            continue
        data = path.read_bytes()
        size_kb = len(data) / 1024
        print(f"\n{'='*72}")
        print(f"clip {clip['id']:5s} {clip['fidelity']:4s}  "
              f"{size_kb:7.0f} KB — {clip['label']}")
        print(f"{'='*72}")

        for model in MODELS:
            for tag, prompt in PROMPTS:
                for rep in range(N_REPS):
                    i += 1
                    raw, ms, served, err = call(
                        client, types, model, data, prompt)
                    parsed = parse_json(raw) or {}
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

                    err_str = f" ERR={err[:50]}" if err else ""
                    print(f"  [{i:3d}/{n_calls}] {model[:8]:8s} "
                          f"{tag:5s} rep{rep+1} ({ms/1000:4.1f}s) "
                          f"len={length} {mk(tl, length)}  "
                          f"shot={shot} {mk(ts, shot)}  "
                          f"hand={handed} {mk(th, handed)}{err_str}")

                    rows.append({
                        "clip": clip["id"],
                        "fidelity": clip["fidelity"],
                        "model": model,
                        "served_model": served,
                        "prompt": tag,
                        "rep": rep + 1,
                        "ms": ms,
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
                        "raw": raw,
                    })

    out_json = out_dir / "full_matrix.json"
    out_json.write_text(json.dumps(rows, indent=2, default=str))
    print(f"\nWrote {out_json}  ({len(rows)} rows)")

    md = render_report(rows)
    out_md = out_dir / "full_matrix_report.md"
    out_md.write_text(md)
    print(f"Wrote {out_md}\n")


# ───────────────── report ─────────────────

def render_report(rows: list[dict]) -> str:
    from datetime import datetime
    out = [f"# Full-matrix attribution test — report\n",
           f"Generated: {datetime.now().isoformat(timespec='seconds')}",
           f"Models: {', '.join(MODELS)}",
           f"Prompts: {', '.join(t for t, _ in PROMPTS)}",
           f"Reps per cell: {N_REPS}\n"]

    # ── CONTROL CLIPS (drift detection) ────────────────────────────
    control_ids = {c["id"] for c in CONTROL_CLIPS}
    control_rows = [r for r in rows if r["clip"] in control_ids]
    if control_rows:
        out.append("## CONTROL CLIPS — track these across runs to "
                   "detect upstream drift\n")
        out.append("If these numbers shift meaningfully between runs "
                   "(without code changes on our side), the model or "
                   "API has changed under us.")
        out.append("")
        out.append("| clip | model | prompt | length acc | shot acc | "
                   "mode_length | reps |")
        out.append("|---|---|---|---|---|---|---|")
        for ctl in CONTROL_CLIPS:
            for model in MODELS:
                for prompt_tag, _ in PROMPTS:
                    cell = [r for r in control_rows
                            if r["clip"] == ctl["id"]
                            and r["model"] == model
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
                        f"| {ctl['id']} | {model.replace('gemini-', '')} "
                        f"| {prompt_tag} | "
                        f"{n_l_ok}/{len(cell)} | "
                        f"{n_s_ok}/{len(cell)} | {ml} | {len(cell)} |")
        out.append("")

    # Per-cell summary: each cell = (clip, model, prompt) over n reps
    out.append("## Per-cell summary (averaged over n=3 reps)\n")
    out.append("Format: `length(✓/✗/?) shot(✓/✗/?)` — "
               "✓=match truth, ✗=wrong, ?=unknown/no-truth.")
    out.append("Distinct values across reps shown for length only.\n")
    out.append("| clip | fid | model | prompt | n_ok_len/n_truth | "
               "n_ok_shot/n_truth | distinct_len | mode_len | "
               "mode_shot | avg ms |")
    out.append("|---|---|---|---|---|---|---|---|---|---|")

    by_cell = {}
    for r in rows:
        key = (r["clip"], r["model"], r["prompt"])
        by_cell.setdefault(key, []).append(r)

    for clip in CLIPS:
        for model in MODELS:
            for prompt_tag, _ in PROMPTS:
                key = (clip["id"], model, prompt_tag)
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
                ms = (f"{mode_s[0][0]}({mode_s[0][1]})"
                      if mode_s else "—")
                avg_ms = int(sum(r["ms"] for r in cell) / len(cell))
                out.append(
                    f"| {clip['id']} | {clip['fidelity']} | "
                    f"{model.replace('gemini-', '')} | {prompt_tag} | "
                    f"{n_l_ok}/{n_l_truth} | {n_s_ok}/{n_s_truth} | "
                    f"{distinct} | {ml} | {ms} | {avg_ms} |")

    # Aggregate per (model, prompt) over all clips × reps with truth
    out.append("\n## Aggregate accuracy by (model, prompt) — "
               "across all clips × reps that have truth\n")
    out.append("| model | prompt | length acc | shot acc | "
               "handed acc | avg ms |")
    out.append("|---|---|---|---|---|---|")
    for model in MODELS:
        for prompt_tag, _ in PROMPTS:
            cell = [r for r in rows
                    if r["model"] == model and r["prompt"] == prompt_tag]
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
                f"| {model.replace('gemini-', '')} | {prompt_tag} | "
                f"{n_l_ok}/{n_l} ({pct(n_l_ok, n_l)}) | "
                f"{n_s_ok}/{n_s} ({pct(n_s_ok, n_s)}) | "
                f"{n_h_ok}/{n_h} ({pct(n_h_ok, n_h)}) | "
                f"{avg_ms} |")

    # Modal-collapse panel
    out.append("\n## Modal-collapse view — "
               "length distribution per (model, prompt, fidelity)\n")
    out.append("Across all reps × clips of that fidelity.  "
               "If one value dominates, that's prior-pull.\n")
    out.append("| model | prompt | fidelity | length distribution |")
    out.append("|---|---|---|---|")
    for model in MODELS:
        for prompt_tag, _ in PROMPTS:
            for fid in ("HIGH", "LOW"):
                cell = [r for r in rows
                        if r["model"] == model
                        and r["prompt"] == prompt_tag
                        and r["fidelity"] == fid]
                ctr = Counter(r["pred_length"] for r in cell
                              if r["pred_length"])
                dist = ", ".join(f"`{k}`×{n}"
                                 for k, n in ctr.most_common())
                out.append(
                    f"| {model.replace('gemini-', '')} | {prompt_tag} | "
                    f"{fid} | {dist} |")

    # Per-clip per-cell: which length values were produced across reps
    out.append("\n## Per-clip rep variance (length only)\n")
    out.append("| clip | truth | model+prompt | rep1 | rep2 | rep3 |")
    out.append("|---|---|---|---|---|---|")
    for clip in CLIPS:
        for model in MODELS:
            for prompt_tag, _ in PROMPTS:
                cell = sorted(
                    by_cell.get((clip["id"], model, prompt_tag), []),
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
                    f"{model.replace('gemini-', '')}/{prompt_tag} | "
                    f"{marks[0]} | {marks[1]} | {marks[2]} |")

    return "\n".join(out)


def pct(num, den):
    if den == 0:
        return "n/a"
    return f"{100*num/den:.0f}%"


if __name__ == "__main__":
    main()
