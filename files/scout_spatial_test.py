"""Scout (Llama-4-Scout @ Groq) on the spatial-decomposition prompt,
3-run consistency to match the Qwen + Gemini bake-off.

Constraints:
  • Groq caps multi-image input at 5 per call for Scout.
  • To match Qwen/Gemini's 16-frame burst we send 3 chunks × 5 frames =
    15 frames per "rep", aggregate per-field by MAX-CONFIDENCE
    (since the new prompt asks for {value, confidence} per field).

Output:
  logs/audit_v1/scout_spatial/run_{1,2,3}/results.json
  logs/audit_v1/scout_spatial/run_{1,2,3}/report.md
  logs/audit_v1/scout_spatial/consistency.md
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from eyes.config import GROQ_API_KEY, GROQ_PRIMARY_MODEL  # noqa: E402
from model_bakeoff_spatial import (  # noqa: E402
    CLIPS, FIELDS, PROMPT_SPATIAL, burst,
    matches, normalise, parse_json, pct, spatial_to_cricket,
)

N_REPS = 3
RUNS_DEFAULT = 3
N_BURST = 15            # 3 × 5 — matches Qwen/Gemini coverage
SCOUT_PER = 5           # Groq hard cap per call
SCOUT_CHUNKS = 3
SLEEP_BETWEEN = 0.6     # be polite to Groq RPM


def call_scout(client, frames, prompt, max_tokens=1500):
    """One Groq call with up to SCOUT_PER frames."""
    content = []
    for f in frames:
        b64 = base64.b64encode(f).decode()
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })
    content.append({
        "type": "text",
        "text": (f"Below are {len(frames)} keyframes (chronological "
                 f"order) from one cricket delivery clip.\n\n" + prompt),
    })
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=GROQ_PRIMARY_MODEL,
            messages=[{"role": "user", "content": content}],
            max_tokens=max_tokens,
            temperature=0.2,
        )
        ms = int((time.time() - t0) * 1000)
        u = resp.usage
        return (resp.choices[0].message.content or "", ms,
                getattr(u, "prompt_tokens", 0),
                getattr(u, "completion_tokens", 0), None)
    except Exception as e:
        return "", int((time.time() - t0) * 1000), 0, 0, str(e)[:300]


def aggregate_by_max_conf(chunk_parsed: list[dict]) -> dict:
    """For each spatial field, pick the value from the chunk where the
    model self-rated highest confidence.  Returns dict in the same
    {value, confidence} shape spatial_to_cricket expects."""
    agg = {}
    SPATIAL_FIELDS = [
        "bowling_arm", "bowler_position_at_release", "bat_side_of_body",
        "ball_bounce_zone", "ball_position_at_batsman",
        "ball_height_at_batsman", "bat_swing", "shot_intent",
        "ball_direction_after_contact", "ball_elevation_after_contact",
        "fielder_reaction", "ball_final_position",
        "bowling_style", "ball_bat_contact_point",
    ]
    for f in SPATIAL_FIELDS:
        best = None
        for cp in chunk_parsed:
            v = cp.get(f)
            if v is None:
                continue
            if isinstance(v, dict):
                conf = float(v.get("confidence", 0.0))
                val = v.get("value")
            else:
                conf = 0.5
                val = v
            if val is None:
                continue
            if str(val).lower() == "unknown":
                # Treat unknown as low-priority unless every chunk
                # said unknown.
                conf = min(conf, 0.05)
            if best is None or conf > best["confidence"]:
                best = {"value": val, "confidence": conf}
        if best is not None:
            agg[f] = best
    return agg


def run_one(run_idx: int, run_dir: Path, gclient_groq):
    run_dir.mkdir(parents=True, exist_ok=True)

    bursts = {}
    for c in CLIPS:
        p = ROOT / c["path"]
        if not p.exists():
            print(f"  missing: {p}")
            continue
        bursts[c["id"]] = burst(str(p), N_BURST)
        kb = sum(len(f) for f in bursts[c["id"]]) / 1024
        print(f"clip {c['id']:10s} {len(bursts[c['id']])} frames, "
              f"{kb:5.0f} KB — {c['label']}")
    print()

    rows = []
    n_total = sum(1 for c in CLIPS if c["id"] in bursts) * N_REPS
    i = 0
    for clip in CLIPS:
        frames = bursts.get(clip["id"])
        if not frames:
            continue
        print(f"\n{'='*78}")
        print(f"RUN {run_idx}  clip {clip['id']:10s} — {clip['label']}")
        truth_str = ", ".join(f"{k}={v}" for k, v in clip["truth"].items())
        print(f"  truth: {truth_str}")
        print(f"{'='*78}")

        chunks = [frames[k*SCOUT_PER:(k+1)*SCOUT_PER]
                  for k in range(SCOUT_CHUNKS)]

        for rep in range(N_REPS):
            i += 1
            chunk_meta = []
            chunk_parsed = []
            t_start = time.time()
            total_in = total_out = 0
            err_collect = []
            for ci, chunk in enumerate(chunks):
                if not chunk:
                    continue
                text, ms, in_t, out_t, err = call_scout(
                    gclient_groq, chunk, PROMPT_SPATIAL)
                time.sleep(SLEEP_BETWEEN)
                parsed = parse_json(text) or {}
                if err:
                    err_collect.append(f"chunk{ci}:{err[:60]}")
                chunk_meta.append({
                    "chunk": ci, "ms": ms,
                    "in_tok": in_t, "out_tok": out_t,
                    "error": err, "raw": text,
                    "parsed_keys": list(parsed.keys()),
                })
                chunk_parsed.append(parsed)
                total_in += in_t
                total_out += out_t
            ms_total = int((time.time() - t_start) * 1000)

            agg_spatial = aggregate_by_max_conf(chunk_parsed)
            cricket_v, cricket_c = spatial_to_cricket(agg_spatial)
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

            err_str = (" ERR=" + "; ".join(err_collect)[:80]
                       if err_collect else "")
            print(f"  [{i:3d}/{n_total}] scout rep{rep+1} "
                  f"({ms_total/1000:5.1f}s in={total_in} out={total_out}) "
                  f"per-field {n_ok}/{n_truth}{err_str}")
            pf = " ".join(
                f"{f}={p}@{c:.2f}{'✓' if ok else '✗'}"
                for f, _, p, c, ok in hits)
            print(f"        {pf}")

            rows.append({
                "run": run_idx,
                "clip": clip["id"],
                "model": "scout",
                "provider": "groq",
                "rep": rep + 1,
                "ms": ms_total,
                "in_tok": total_in,
                "out_tok": total_out,
                "error": "; ".join(err_collect) if err_collect else None,
                "truth": truth,
                "spatial": agg_spatial,
                "chunk_meta": chunk_meta,
                "pred": pred,
                "pred_conf": pred_conf,
                "n_ok": n_ok,
                "n_truth": n_truth,
            })

    out_json = run_dir / "results.json"
    out_json.write_text(json.dumps(rows, indent=2))
    print(f"\nWrote {out_json}  ({len(rows)} rows)")

    # Per-run report
    md = [f"# Scout spatial — Run {run_idx}\n"]
    md.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    md.append(f"Reps per clip: {N_REPS}.  Per rep: 3 calls × 5 frames "
              f"(Groq cap), aggregated per spatial-field by MAX confidence.")
    md.append(f"Then `spatial_to_cricket` produces 14 cricket-schema "
              f"fields scored against truth.\n")

    md.append("## Per-field accuracy (all clips × reps)\n")
    md.append("| field | scout |")
    md.append("|---|---|")
    for fld in FIELDS:
        ok = n = 0
        for r in rows:
            if fld not in r["truth"]:
                continue
            n += 1
            if matches(r["pred"].get(fld), r["truth"][fld]):
                ok += 1
        if n == 0:
            continue
        md.append(f"| **{fld}** | {ok}/{n} ({pct(ok, n)}) |")
    total_ok = sum(r["n_ok"] for r in rows)
    total_n = sum(r["n_truth"] for r in rows)
    md.append(f"| **TOTAL** | **{total_ok}/{total_n} "
              f"({pct(total_ok, total_n)})** |")
    md.append("")
    out_md = run_dir / "report.md"
    out_md.write_text("\n".join(md))
    print(f"Wrote {out_md}")

    return rows


def consistency_report(all_runs_rows, out_path: Path):
    md = ["# Scout spatial — consistency across 3 runs\n"]
    md.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    md.append("## Per-field accuracy by run\n")
    md.append("| field | run 1 | run 2 | run 3 | mean | spread |")
    md.append("|---|---|---|---|---|---|")
    pooled_ok, pooled_n = {}, {}
    for fld in FIELDS:
        per_run = []
        for ridx, rows in enumerate(all_runs_rows, 1):
            ok = n = 0
            for r in rows:
                if fld not in r["truth"]:
                    continue
                n += 1
                if matches(r["pred"].get(fld), r["truth"][fld]):
                    ok += 1
            per_run.append((ok, n))
            pooled_ok[fld] = pooled_ok.get(fld, 0) + ok
            pooled_n[fld] = pooled_n.get(fld, 0) + n
        if all(n == 0 for _, n in per_run):
            continue
        rates = [(o / n) if n else 0.0 for o, n in per_run]
        mean = sum(rates) / len(rates)
        spread = (max(rates) - min(rates)) * 100
        cells = " | ".join(f"{o}/{n} ({pct(o, n)})" for o, n in per_run)
        md.append(f"| **{fld}** | {cells} | {mean*100:.0f}% "
                  f"| ±{spread:.0f} pp |")
    pooled_total_ok = sum(pooled_ok.values())
    pooled_total_n = sum(pooled_n.values())
    md.append(f"| **TOTAL** | (per-run cells above) |  |  |  | "
              f"pooled **{pooled_total_ok}/{pooled_total_n} "
              f"({pct(pooled_total_ok, pooled_total_n)})** |")
    md.append("")
    md.append("## Pooled per-field (the headline)\n")
    md.append("| field | scout (45 calls) |")
    md.append("|---|---|")
    for fld in FIELDS:
        n = pooled_n.get(fld, 0)
        if n == 0:
            continue
        ok = pooled_ok[fld]
        md.append(f"| **{fld}** | {ok}/{n} ({pct(ok, n)}) |")
    out_path.write_text("\n".join(md))
    print(f"Wrote {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=RUNS_DEFAULT)
    args = ap.parse_args()

    from openai import OpenAI
    gclient_groq = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=GROQ_API_KEY,
    )

    base = ROOT / "logs/audit_v1/scout_spatial"
    base.mkdir(parents=True, exist_ok=True)

    all_runs_rows = []
    for ridx in range(1, args.runs + 1):
        print(f"\n{'#'*78}")
        print(f"# RUN {ridx} of {args.runs} → {base/f'run_{ridx}'}")
        print(f"{'#'*78}")
        rows = run_one(ridx, base / f"run_{ridx}", gclient_groq)
        all_runs_rows.append(rows)

    consistency_report(all_runs_rows, base / "consistency.md")


if __name__ == "__main__":
    main()
