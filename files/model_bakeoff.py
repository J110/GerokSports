"""Per-field accuracy bake-off — Qwen vs Gemini vs Scout.

Test design (per user's brief 2026-04-20):
  • Same 5 clips as the Gemini/Qwen matrices.
  • Send a 16-frame burst (evenly spaced across the clip) to each
    model.  Scout (Llama-4-Scout @ Groq) is hard-capped by Groq at 5
    images per call, so for Scout we split the burst into 3 chunks of
    5 frames (early / middle / late) and make 3 separate API calls
    per (clip, rep), then aggregate per-field.
  • Single committal prompt (PROMPT_FULL) — we don't reward "unknown",
    we just score each field "did the model match truth, yes or no".
  • n=3 reps per (model, clip).

Aggregation rule for Scout's 3-chunk answer:
  For each field, take the most common non-"unknown" value across the
  3 chunks.  Ties broken by the latest chunk (post-contact frames are
  the most informative).  If all 3 chunks said "unknown", final = "unknown".

Output:
  logs/audit_v1/bakeoff/results.json
  logs/audit_v1/bakeoff/report.md
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

from eyes.config import (  # noqa: E402
    GEMINI_API_KEY, GROQ_API_KEY, GROQ_PRIMARY_MODEL,
)
os.environ.setdefault("GEMINI_API_KEY", GEMINI_API_KEY)

from gemini_ab_schema_test import PROMPT_FULL  # noqa: E402

PROMPT = PROMPT_FULL  # committal: encourages a value per field
N_REPS = 3
N_BURST = 16          # frames sent to qwen + gemini
SCOUT_CHUNKS = 3      # number of Scout API calls per (clip, rep)
SCOUT_PER = 5         # frames per Scout call (Groq hard limit)
JPEG_Q = 88

FIREWORKS_API_KEY = os.environ.get(
    "FIREWORKS_API_KEY", "fw_8Kyu9Ug7kXVp6kPRDvhL3n")

# Models — display tag, provider, model_id
MODELS = [
    ("qwen30b-instruct", "fireworks",
     "accounts/fireworks/models/qwen3-vl-30b-a3b-instruct"),
    ("gemini-3-flash",   "gemini",
     "gemini-3-flash-preview"),
    ("scout",            "groq",
     GROQ_PRIMARY_MODEL),
]

# All 14 classification fields from PROMPT_FULL.  A truth value can be:
#   - a single string (must match exactly after normalise)
#   - a list/tuple of strings (any value in the list counts as a hit)
#   - missing / not in clip["truth"] → not scored for that clip
FIELDS = [
    "is_valid_delivery",
    "batsman_handed",
    "bowling_arm",
    "bowling_angle",
    "bowling_type",
    "length",
    "line",
    "bounce",
    "shot_played",
    "shot_type",
    "shot_side",
    "shot_angle",
    "elevation",
    "contact_quality",
]

# ─── clips with full per-field truth ───
# Sourced from logs/audit_v1/fixtures/over_test_20260420_140137.json
# plus prior-known batsman_handed.  Field values must match exactly
# what the prompt's schema expects (don't alias; fix in NORMALISE).
CLIPS = [
    {"id": "ctrl_old2", "path": "ball_test_clip_60fps_long.mp4",
     "label": "CONTROL: Apr10 hi-fid SHORT/steep/pull",
     "truth": {
         "is_valid_delivery": True,
         "batsman_handed": "right",
         "bowling_arm": "right",
         "length": "short",
         "shot_played": True,
         "shot_type": "pull",
     }},
    {"id": "old1", "path": "ball_test_clip_30fps.mp4",
     "label": "Apr10 hi-fid: LEFT-handed defence square of wicket",
     "truth": {
         "is_valid_delivery": True,
         "batsman_handed": "left",
         "shot_played": True,
         "shot_type": "defend",
     }},
    {"id": "w19", "path":
     "logs/deliveries/20260420_140137/windows/window_0019/delivery_window.mp4",
     "label": "YT 3.0: round-arm, on stumps, defend (Mendis)",
     "truth": {
         "is_valid_delivery": True,
         "batsman_handed": "right",
         "bowling_arm": "right",
         "bowling_angle": "round_the_wicket",
         "bowling_type": "fast",
         # fixture says "on_stumps" — accept any of off/middle/leg
         "line": ["off_stump", "middle_stump", "leg_stump"],
         "bounce": "normal",
         "shot_played": True,
         "shot_type": "defend",
         "shot_side": "leg",
         "elevation": "along_ground",
     }},
    {"id": "w21", "path":
     "logs/deliveries/20260420_140137/windows/window_0021/delivery_window.mp4",
     "label": "YT 3.1: SHORT, off stump, pull (inside-edged)",
     "truth": {
         "is_valid_delivery": True,
         "batsman_handed": "right",
         "bowling_arm": "right",
         "bowling_angle": "over_the_wicket",
         "bowling_type": "fast",
         "length": "short",
         "line": "off_stump",
         "bounce": "normal",
         "shot_played": True,
         "shot_type": "pull",
         "shot_side": "leg",
         "shot_angle": "square",
         "elevation": "along_ground",
         "contact_quality": "inside_edge",
     }},
    {"id": "w23", "path":
     "logs/deliveries/20260420_140137/windows/window_0023/delivery_window.mp4",
     "label": "YT 3.2: SHORT, outside off, cut for FOUR",
     "truth": {
         "is_valid_delivery": True,
         "batsman_handed": "right",
         "bowling_arm": "right",
         "bowling_angle": "over_the_wicket",
         "bowling_type": "fast",
         "length": "short",
         "line": "outside_off",
         "bounce": "normal",
         "shot_played": True,
         "shot_type": "cut",
         "shot_side": "off",
         "shot_angle": "square",
         "elevation": "in_air",
         "contact_quality": "well_timed",
     }},
]


# ─── helpers ───

def b64(b): return base64.b64encode(b).decode()


def normalise(field: str, v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v  # is_valid_delivery / shot_played stay boolean
    if isinstance(v, (list, tuple)):
        return [normalise(field, x) for x in v]
    s = str(v).lower().strip()
    if s in {"true"}: return True
    if s in {"false"}: return False
    if s in {"unknown", "n/a", "na", "null", ""}:
        return "unknown"
    if field == "length" and s in {"short_of_a_length", "short_of_length"}:
        return "short_of_length"
    if field == "bowling_angle":
        if s in {"over", "over_the_wicket"}: return "over_the_wicket"
        if s in {"round", "round_the_wicket"}: return "round_the_wicket"
    if field == "line":
        if s in {"middle"}: return "middle_stump"
    return s


def matches(pred, truth):
    """Truth may be a single value or list-of-acceptable-values."""
    if truth is None:
        return False
    if isinstance(truth, list):
        return pred in truth
    return pred == truth


def parse_json(text: str):
    if not text:
        return None
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    matches = list(re.finditer(r"\{[\s\S]*?\}", text))
    if matches:
        matches.sort(key=lambda m: -(m.end() - m.start()))
        for m in matches:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    g = re.search(r"\{[\s\S]*\}", text)
    if g:
        try: return json.loads(g.group(0))
        except Exception: return None
    return None


def burst(mp4: str, n: int) -> list[bytes]:
    cap = cv2.VideoCapture(mp4)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    out = []
    if total <= 0:
        cap.release(); return out
    for i in range(n):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * (i + 0.5) / n))
        ok, fr = cap.read()
        if not ok: continue
        ok, j = cv2.imencode(".jpg", fr,
                             [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_Q])
        if ok: out.append(j.tobytes())
    cap.release()
    return out


# ─── per-provider call ───

def _img_parts_openai(frames):
    return [{"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{b64(f)}"}}
            for f in frames]


def call_openai_compat(client, model, frames, prompt, max_tokens=800):
    content = _img_parts_openai(frames)
    content.append({"type": "text",
                    "text": f"Below are {len(frames)} keyframes "
                            f"(chronological order) from one cricket "
                            f"delivery clip.\n\n" + prompt})
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
            max_tokens=max_tokens,
            temperature=0.2,
        )
        ms = int((time.time() - t0) * 1000)
        u = resp.usage
        return (resp.choices[0].message.content or "", ms,
                getattr(u, "prompt_tokens", 0),
                getattr(u, "completion_tokens", 0), None)
    except Exception as e:  # noqa: BLE001
        return "", int((time.time() - t0) * 1000), 0, 0, str(e)[:300]


def call_qwen(client, frames, prompt):
    return call_openai_compat(
        client["fireworks"],
        "accounts/fireworks/models/qwen3-vl-30b-a3b-instruct",
        frames, prompt, max_tokens=800)


def call_gemini(client_g, types_g, frames, prompt):
    parts = []
    for f in frames:
        parts.append(types_g.Part.from_bytes(
            data=f, mime_type="image/jpeg"))
    parts.append(types_g.Part.from_text(
        text=f"Below are {len(frames)} keyframes (chronological "
             f"order) from one cricket delivery clip.\n\n" + prompt))
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
    except Exception as e:  # noqa: BLE001
        return "", int((time.time() - t0) * 1000), 0, 0, str(e)[:300]


def call_scout(client, frames, prompt):
    """Scout = Groq.  5-image cap → caller already chunked."""
    return call_openai_compat(
        client["groq"], GROQ_PRIMARY_MODEL,
        frames, prompt, max_tokens=800)


# ─── Scout chunked + aggregation ───

def scout_chunks_then_aggregate(client, frames, prompt):
    """3 calls × 5 frames; aggregate per-field.

    Returns (aggregated_dict, list_of_call_meta).
    """
    chunk_size = SCOUT_PER
    chunks = [frames[i*chunk_size:(i+1)*chunk_size]
              for i in range(SCOUT_CHUNKS)]
    chunk_results = []
    for ci, chunk in enumerate(chunks):
        if len(chunk) < 1:
            continue
        text, ms, in_t, out_t, err = call_scout(client, chunk, prompt)
        # Polite spacing — Groq has aggressive RPM limits
        time.sleep(1.0)
        parsed = parse_json(text) or {}
        chunk_results.append({
            "chunk": ci, "ms": ms, "in_tok": in_t, "out_tok": out_t,
            "error": err, "raw": text, "parsed": parsed,
        })

    # Aggregate: per field, mode of non-unknown values across chunks;
    # tie-break preferring later chunk; fall back to "unknown".
    agg = {}
    for fld in FIELDS:
        vals = []
        for ci, cr in enumerate(chunk_results):
            v = normalise(fld, cr["parsed"].get(fld))
            if v is None:
                continue
            vals.append((ci, v))
        if not vals:
            agg[fld] = None
            continue
        non_unknown = [(ci, v) for ci, v in vals if v != "unknown"]
        pool = non_unknown if non_unknown else vals
        ctr = Counter(v for _, v in pool)
        top_count = ctr.most_common(1)[0][1]
        # values tied at top
        top_vals = [v for v, c in ctr.items() if c == top_count]
        if len(top_vals) == 1:
            agg[fld] = top_vals[0]
        else:
            # Pick the one from the latest chunk
            for ci, v in reversed(pool):
                if v in top_vals:
                    agg[fld] = v
                    break
    return agg, chunk_results


# ─── runner ───

def main():
    from openai import OpenAI
    from google import genai
    from google.genai import types as gtypes

    out_dir = ROOT / "logs" / "audit_v1" / "bakeoff"
    out_dir.mkdir(parents=True, exist_ok=True)

    clients = {
        "fireworks": OpenAI(
            base_url="https://api.fireworks.ai/inference/v1",
            api_key=FIREWORKS_API_KEY),
        "groq": OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=GROQ_API_KEY),
    }
    gclient = genai.Client()

    # Pre-extract burst once per clip
    bursts: dict[str, list[bytes]] = {}
    for c in CLIPS:
        p = ROOT / c["path"]
        if not p.exists():
            print(f"  missing: {p}"); continue
        bursts[c["id"]] = burst(str(p), N_BURST)
        kb = sum(len(f) for f in bursts[c["id"]]) / 1024
        print(f"clip {c['id']:10s} {len(bursts[c['id']])} frames, "
              f"{kb:5.0f} KB — {c['label']}")
    print()

    rows = []
    n_total = sum(1 for c in CLIPS if c["id"] in bursts) \
        * len(MODELS) * N_REPS
    i = 0

    for clip in CLIPS:
        frames = bursts.get(clip["id"])
        if not frames:
            continue
        print(f"\n{'='*78}")
        print(f"clip {clip['id']:10s} — {clip['label']}")
        truth_str = ", ".join(f"{k}={v}" for k, v in clip["truth"].items())
        print(f"  truth: {truth_str}")
        print(f"{'='*78}")

        for model_tag, provider, model_id in MODELS:
            for rep in range(N_REPS):
                i += 1
                t_total = time.time()
                if model_tag == "scout":
                    agg, chunks_meta = scout_chunks_then_aggregate(
                        clients, frames, PROMPT)
                    ms = int((time.time() - t_total) * 1000)
                    in_tok = sum(c["in_tok"] for c in chunks_meta)
                    out_tok = sum(c["out_tok"] for c in chunks_meta)
                    errs = [c["error"] for c in chunks_meta if c["error"]]
                    err = "; ".join(errs)[:300] if errs else None
                    raw = json.dumps([c["raw"] for c in chunks_meta])
                    pred = agg
                elif provider == "gemini":
                    text, ms, in_tok, out_tok, err = call_gemini(
                        gclient, gtypes, frames, PROMPT)
                    parsed = parse_json(text) or {}
                    pred = {f: normalise(f, parsed.get(f)) for f in FIELDS}
                    raw = text
                else:
                    client = clients[provider]
                    text, ms, in_tok, out_tok, err = call_openai_compat(
                        client, model_id, frames, PROMPT, max_tokens=800)
                    parsed = parse_json(text) or {}
                    pred = {f: normalise(f, parsed.get(f)) for f in FIELDS}
                    raw = text

                # Score per field
                truth = {f: normalise(f, v) for f, v in clip["truth"].items()}
                hits = []
                for f in FIELDS:
                    if f not in truth:
                        continue
                    p = pred.get(f)
                    hits.append((f, truth[f], p, matches(p, truth[f])))
                n_truth = len(hits)
                n_ok = sum(1 for _, _, _, ok in hits if ok)

                err_str = f" ERR={err[:60]}" if err else ""
                print(f"  [{i:3d}/{n_total}] {model_tag:18s} rep{rep+1} "
                      f"({ms/1000:5.1f}s in={in_tok} out={out_tok}) "
                      f"per-field {n_ok}/{n_truth}{err_str}")
                # Brief per-field hit/miss line
                pf = " ".join(f"{f}={p}{'✓' if ok else '✗'}"
                              for f, _, p, ok in hits)
                print(f"        {pf}")

                rows.append({
                    "clip": clip["id"],
                    "model": model_tag,
                    "provider": provider,
                    "rep": rep + 1,
                    "ms": ms,
                    "in_tok": in_tok,
                    "out_tok": out_tok,
                    "error": err,
                    "truth": truth,
                    "pred": pred,
                    "n_ok": n_ok,
                    "n_truth": n_truth,
                    "raw": raw,
                })

                # Persist incrementally
                if i % 3 == 0:
                    (out_dir / "results.json").write_text(
                        json.dumps(rows, indent=2, default=str))

    out_json = out_dir / "results.json"
    out_json.write_text(json.dumps(rows, indent=2, default=str))
    print(f"\nWrote {out_json}  ({len(rows)} rows)")

    md = render_report(rows)
    out_md = out_dir / "report.md"
    out_md.write_text(md)
    print(f"Wrote {out_md}\n")


# ─── report ───

def pct(num, den):
    if den == 0: return "—"
    return f"{100*num/den:.0f}%"


def render_report(rows: list[dict]) -> str:
    out = [
        f"# Per-field bake-off — Qwen vs Gemini vs Scout\n",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Models: {', '.join(m[0] for m in MODELS)}",
        f"Reps per (model, clip): {N_REPS}",
        f"Input shape: 16-frame burst.  Scout = 3 calls × 5 frames "
        f"(Groq hard cap), aggregated per-field by mode-of-non-unknown.",
        f"Scoring: a field is correct ONLY if the model's value "
        f"equals the truth value exactly (after schema normalisation). "
        f"Unknown counts as wrong.\n",
    ]

    # ─── HEADLINE: per-field accuracy across all clips × reps ───
    out.append("## Per-field accuracy across all clips × reps\n")
    header = "| field | " + " | ".join(m[0] for m in MODELS) + " |"
    sep = "|---|" + "|".join("---" for _ in MODELS) + "|"
    out.append(header); out.append(sep)
    for fld in FIELDS:
        cells = []
        for model_tag, _, _ in MODELS:
            ok = den = 0
            for r in rows:
                if r["model"] != model_tag: continue
                if fld not in r["truth"]: continue
                den += 1
                if matches(r["pred"].get(fld), r["truth"][fld]):
                    ok += 1
            cells.append(f"{ok}/{den} ({pct(ok, den)})")
        out.append(f"| **{fld}** | " + " | ".join(cells) + " |")
    # Totals row
    cells = []
    for model_tag, _, _ in MODELS:
        ok = sum(r["n_ok"] for r in rows if r["model"] == model_tag)
        den = sum(r["n_truth"] for r in rows if r["model"] == model_tag)
        cells.append(f"**{ok}/{den} ({pct(ok, den)})**")
    out.append(f"| **TOTAL** | " + " | ".join(cells) + " |")
    out.append("")

    # ─── per-clip per-field detail ───
    out.append("## Per-clip per-field hits (rep1/rep2/rep3) per model\n")
    out.append("Each cell shows the predicted value across reps and "
               "✓ if it matched truth.\n")
    for clip in CLIPS:
        if not any(r["clip"] == clip["id"] for r in rows):
            continue
        out.append(f"### {clip['id']} — {clip['label']}\n")
        truth_str = ", ".join(f"`{k}={v}`"
                              for k, v in clip["truth"].items())
        out.append(f"Truth: {truth_str}\n")
        out.append("| field | truth | " + " | ".join(
            f"{m[0]} (r1/r2/r3)" for m in MODELS) + " |")
        out.append("|---|---|" + "|".join("---" for _ in MODELS) + "|")
        for fld in FIELDS:
            if fld not in clip["truth"]:
                continue
            t = clip["truth"][fld]
            cells = []
            for model_tag, _, _ in MODELS:
                vals = []
                for rep in (1, 2, 3):
                    matching = [r for r in rows
                                if r["clip"] == clip["id"]
                                and r["model"] == model_tag
                                and r["rep"] == rep]
                    if matching:
                        v = matching[0]["pred"].get(fld) or "—"
                        mark = "✓" if matches(v, t) else ""
                        vals.append(f"{v}{mark}")
                    else:
                        vals.append("—")
                cells.append(" / ".join(vals))
            out.append(f"| {fld} | `{t}` | " + " | ".join(cells) + " |")
        out.append("")

    # ─── latency / cost ───
    out.append("## Latency & token usage\n")
    out.append("| model | n calls | avg ms | avg in_tok | avg out_tok |")
    out.append("|---|---|---|---|---|")
    for model_tag, _, _ in MODELS:
        cell = [r for r in rows if r["model"] == model_tag]
        if not cell: continue
        avg_ms = int(sum(r["ms"] for r in cell) / len(cell))
        avg_in = int(sum(r["in_tok"] for r in cell) / len(cell))
        avg_out = int(sum(r["out_tok"] for r in cell) / len(cell))
        out.append(f"| {model_tag} | {len(cell)} | {avg_ms} | "
                   f"{avg_in} | {avg_out} |")

    # ─── errors ───
    err_rows = [r for r in rows if r["error"]]
    if err_rows:
        out.append(f"\n## API errors ({len(err_rows)})\n")
        out.append("| clip | model | rep | error |")
        out.append("|---|---|---|---|")
        for r in err_rows:
            out.append(f"| {r['clip']} | {r['model']} | {r['rep']} | "
                       f"`{r['error'][:120]}` |")

    return "\n".join(out)


if __name__ == "__main__":
    main()
