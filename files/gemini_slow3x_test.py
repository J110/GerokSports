"""Gemini 3 Flash test on 3x-slowed video clips.

Why slowed video:
  Gemini's native video API samples roughly 1fps from the uploaded
  clip.  If we re-encode the clip at 1/3 playback speed (same frames,
  3x duration) without re-sampling pixels, Gemini's sampler ends up
  looking at ~3x more frames per real-time second of action.  This is
  the cleanest way to give Gemini more temporal resolution without
  changing anything else.

Test:
  • 5 clips (same as bake-off).
  • For each clip, re-encode at 3x duration with `setpts=3.0*PTS`
    (no pixel resample, no compression change beyond a single re-mux).
  • Send the slowed mp4 as actual `video/mp4` to gemini-3-flash-preview.
  • PROMPT_SPATIAL (14 questions, with confidence).
  • spatial_to_cricket mapper produces the 14-field cricket schema.
  • 3 reps per clip = 15 calls total.
  • Score against the same truth as the bake-off.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from eyes.config import GEMINI_API_KEY  # noqa: E402
from model_bakeoff_spatial import (  # noqa: E402
    CLIPS,
    FIELDS,
    PROMPT_SPATIAL,
    matches,
    normalise,
    parse_json,
    pct,
    spatial_to_cricket,
)

os.environ.setdefault("GEMINI_API_KEY", GEMINI_API_KEY)

N_REPS = 3
SLOW_FACTOR = 3.0          # 3x slower playback
OUT_DIR = ROOT / "logs/audit_v1/gemini_slow3x"
SLOW_DIR = OUT_DIR / "slowed_clips"


def slow_clip(src: Path, dst: Path, factor: float = SLOW_FACTOR) -> dict:
    """Slow `src` to `dst` by `factor` (3.0 == 1/3 speed).

    Re-times via setpts only — no pixel resampling.  Re-encodes with
    libx264 to keep the output a clean mp4 Gemini can read.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(src),
        # setpts re-times (slows playback); scale rounds to even dims
        # which libx264 requires.  No content change.
        "-vf", f"setpts={factor:.3f}*PTS,"
               f"scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-an",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        str(dst),
    ]
    subprocess.run(cmd, check=True)
    info = probe(dst)
    return info


def probe(p: Path) -> dict:
    out = subprocess.check_output([
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries",
        "stream=duration,nb_frames,r_frame_rate,width,height",
        "-of", "json", str(p),
    ])
    j = json.loads(out)
    s = j["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    fps = float(num) / float(den) if float(den) else 0.0
    return {
        "duration_s": float(s.get("duration", 0)),
        "n_frames": int(s.get("nb_frames", 0) or 0),
        "fps": round(fps, 2),
        "w": s.get("width"),
        "h": s.get("height"),
        "size_kb": round(p.stat().st_size / 1024),
    }


def call_gemini_video(client_g, types_g, mp4_bytes: bytes,
                      prompt: str) -> tuple[str, int, int, int, str | None]:
    parts = [
        types_g.Part.from_bytes(data=mp4_bytes, mime_type="video/mp4"),
        types_g.Part.from_text(
            text="Above is a single cricket delivery clip, played back "
                 "at 1/3 normal speed for clarity.  Analyse it and "
                 "return the JSON.\n\n" + prompt),
    ]
    t0 = time.time()
    try:
        resp = client_g.models.generate_content(
            model="gemini-3-flash-preview", contents=parts)
        ms = int((time.time() - t0) * 1000)
        u = getattr(resp, "usage_metadata", None)
        return (resp.text or "", ms,
                getattr(u, "prompt_token_count", 0) if u else 0,
                getattr(u, "candidates_token_count", 0) if u else 0,
                None)
    except Exception as e:
        return "", int((time.time() - t0) * 1000), 0, 0, str(e)[:300]


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if SLOW_DIR.exists():
        shutil.rmtree(SLOW_DIR)
    SLOW_DIR.mkdir(parents=True)

    print("== Slowing clips 3x ==")
    clip_meta = {}
    for c in CLIPS:
        src = ROOT / c["path"]
        if not src.exists():
            print(f"  missing: {src}")
            continue
        orig = probe(src)
        dst = SLOW_DIR / f"{c['id']}_slow3x.mp4"
        slow = slow_clip(src, dst)
        clip_meta[c["id"]] = {
            "src": str(src), "slowed": str(dst),
            "orig": orig, "slow": slow,
        }
        print(f"  {c['id']:10s}  orig {orig['duration_s']:5.1f}s "
              f"@{orig['fps']:.0f}fps  →  slow {slow['duration_s']:5.1f}s "
              f"@{slow['fps']:.0f}fps  ({slow['size_kb']} KB)")
    print()

    from google import genai
    from google.genai import types as gtypes
    gclient = genai.Client()

    rows = []
    n_total = sum(1 for c in CLIPS if c["id"] in clip_meta) * N_REPS
    i = 0
    for clip in CLIPS:
        meta = clip_meta.get(clip["id"])
        if not meta:
            continue
        print(f"\n{'='*78}")
        print(f"clip {clip['id']:10s} — {clip['label']}")
        truth_str = ", ".join(f"{k}={v}" for k, v in clip["truth"].items())
        print(f"  truth: {truth_str}")
        print(f"{'='*78}")
        with open(meta["slowed"], "rb") as fh:
            mp4_bytes = fh.read()

        for rep in range(N_REPS):
            i += 1
            text, ms, in_tok, out_tok, err = call_gemini_video(
                gclient, gtypes, mp4_bytes, PROMPT_SPATIAL)
            spatial = parse_json(text) or {}
            cricket_v, cricket_c = spatial_to_cricket(spatial)
            pred = {f: normalise(f, cricket_v.get(f)) for f in FIELDS}
            pred_conf = {f: float(cricket_c.get(f, 0.0))
                         for f in FIELDS}

            truth = {f: normalise(f, v)
                     for f, v in clip["truth"].items()}
            hits = []
            for f in FIELDS:
                if f not in truth:
                    continue
                p = pred.get(f)
                hits.append((f, truth[f], p, pred_conf[f],
                             matches(p, truth[f])))
            n_truth = len(hits)
            n_ok = sum(1 for *_, ok in hits if ok)

            err_str = f" ERR={err[:60]}" if err else ""
            print(f"  [{i:3d}/{n_total}] rep{rep+1} "
                  f"({ms/1000:5.1f}s in={in_tok} out={out_tok}) "
                  f"per-field {n_ok}/{n_truth}{err_str}")
            pf = " ".join(
                f"{f}={p}@{c:.2f}{'✓' if ok else '✗'}"
                for f, _, p, c, ok in hits)
            print(f"       {pf}")

            rows.append({
                "clip": clip["id"],
                "rep": rep + 1,
                "ms": ms,
                "in_tok": in_tok,
                "out_tok": out_tok,
                "error": err,
                "truth": truth,
                "spatial": spatial,
                "pred": pred,
                "pred_conf": pred_conf,
                "n_ok": n_ok,
                "n_truth": n_truth,
                "raw": text,
            })

    # ── Persist ──
    out_json = OUT_DIR / "results.json"
    out_json.write_text(json.dumps({
        "model": "gemini-3-flash-preview",
        "slow_factor": SLOW_FACTOR,
        "n_reps": N_REPS,
        "input_mode": "video/mp4 (3x slower playback)",
        "clip_meta": clip_meta,
        "rows": rows,
        "generated": datetime.now().isoformat(timespec="seconds"),
    }, indent=2))
    print(f"\nWrote {out_json}")

    # ── Per-field accuracy table ──
    md = ["# Gemini 3 Flash — 3x slower video test\n"]
    md.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    md.append(f"Model: `gemini-3-flash-preview`")
    md.append(f"Input: actual `video/mp4`, slowed {SLOW_FACTOR:g}x via "
              f"ffmpeg `setpts={SLOW_FACTOR:g}*PTS` "
              f"(no pixel resample)")
    md.append(f"Reps per clip: {N_REPS}\n")

    md.append("## Slowed-clip metadata\n")
    md.append("| clip | original | slowed | size |")
    md.append("|---|---|---|---|")
    for cid, m in clip_meta.items():
        o, s = m["orig"], m["slow"]
        md.append(f"| {cid} | {o['duration_s']:.1f}s @ {o['fps']:.0f}fps "
                  f"| {s['duration_s']:.1f}s @ {s['fps']:.0f}fps "
                  f"| {s['size_kb']} KB |")
    md.append("")

    md.append("## Per-field accuracy (all clips × reps)\n")
    md.append("| field | accuracy | mean conf |")
    md.append("|---|---|---|")
    for fld in FIELDS:
        confs, hits = [], []
        for r in rows:
            if fld not in r["truth"]:
                continue
            confs.append((r["pred_conf"] or {}).get(fld, 0.0))
            hits.append(1 if matches(r["pred"].get(fld), r["truth"][fld])
                        else 0)
        if not hits:
            continue
        md.append(f"| **{fld}** | {sum(hits)}/{len(hits)} "
                  f"({pct(sum(hits), len(hits))}) | "
                  f"{sum(confs)/len(confs):.2f} |")
    total_h = sum(r["n_ok"] for r in rows)
    total_n = sum(r["n_truth"] for r in rows)
    md.append(f"| **TOTAL** | **{total_h}/{total_n} "
              f"({pct(total_h, total_n)})** |  |")
    md.append("")

    # ── Per-clip per-field detail (3 reps side by side) ──
    md.append("## Per-clip detail (rep1 / rep2 / rep3)\n")
    for clip in CLIPS:
        if clip["id"] not in clip_meta:
            continue
        md.append(f"### {clip['id']} — {clip['label']}\n")
        truth = {f: normalise(f, v) for f, v in clip["truth"].items()}
        clip_rows = sorted([r for r in rows if r["clip"] == clip["id"]],
                           key=lambda r: r["rep"])
        md.append("| field | truth | rep1 | rep2 | rep3 |")
        md.append("|---|---|---|---|---|")
        for fld in FIELDS:
            if fld not in truth:
                continue
            cells = [f"`{truth[fld]}`"]
            for r in clip_rows:
                v = r["pred"].get(fld)
                c = (r["pred_conf"] or {}).get(fld, 0.0)
                ok = matches(v, truth[fld])
                cells.append(f"{v}@{c:.2f}{'✓' if ok else ''}")
            md.append(f"| {fld} | " + " | ".join(cells) + " |")
        md.append("")

    # ── Calibration ──
    md.append("## Confidence calibration\n")
    confs, hits = [], []
    for r in rows:
        for fld, t in r["truth"].items():
            confs.append((r["pred_conf"] or {}).get(fld, 0.0))
            hits.append(1 if matches(r["pred"].get(fld), t) else 0)
    md.append("| confidence floor | accuracy |")
    md.append("|---|---|")
    md.append(f"| all | {sum(hits)}/{len(hits)} "
              f"({pct(sum(hits), len(hits))}) |")
    for floor in (0.5, 0.7, 0.9):
        mask = [(h, c) for h, c in zip(hits, confs) if c >= floor]
        ok = sum(h for h, _ in mask)
        den = len(mask)
        md.append(f"| ≥ {floor} | "
                  + (f"{ok}/{den} ({pct(ok, den)})" if den else "—")
                  + " |")
    md.append("")

    md.append("## Latency / token usage\n")
    if rows:
        avg_ms = sum(r["ms"] for r in rows) / len(rows)
        avg_in = sum(r["in_tok"] for r in rows) / len(rows)
        avg_out = sum(r["out_tok"] for r in rows) / len(rows)
        md.append(f"- calls: {len(rows)}")
        md.append(f"- avg latency: {avg_ms/1000:.1f}s")
        md.append(f"- avg input tokens: {avg_in:.0f}")
        md.append(f"- avg output tokens: {avg_out:.0f}")

    out_md = OUT_DIR / "report.md"
    out_md.write_text("\n".join(md))
    print(f"Wrote {out_md}")


if __name__ == "__main__":
    main()
