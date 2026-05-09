"""Re-run only the cells that failed in qwen_full_matrix_test.py
with proper exponential backoff for rate-limit (429) errors,
then re-render the report.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from qwen_full_matrix_test import (  # noqa: E402
    CLIPS, MODELS, N_BURST, PROMPTS, call, extract_burst,
    normalise_length, parse_json, render_report,
)

OUT_JSON = ROOT / "logs" / "audit_v1" / "qwen_matrix" / "full_matrix.json"
OUT_MD = ROOT / "logs" / "audit_v1" / "qwen_matrix" / "full_matrix_report.md"


def needs_retry(row: dict) -> bool:
    if row.get("error"):
        return True
    # Output got truncated past max_tokens or just couldn't parse
    if row.get("pred_length") is None and row.get("pred_shot") is None:
        return True
    return False


def call_with_retry(client, model_id, frames, prompt_text, max_tokens,
                    max_attempts=5):
    delay = 8.0
    for attempt in range(max_attempts):
        text, ms, in_tok, out_tok, err = call(
            client, model_id, frames, prompt_text, max_tokens)
        if err and ("429" in err or "rate" in err.lower()):
            print(f"    429 attempt {attempt+1}/{max_attempts}, "
                  f"sleeping {delay:.0f}s")
            time.sleep(delay)
            delay = min(delay * 1.8, 60.0)
            continue
        return text, ms, in_tok, out_tok, err
    return text, ms, in_tok, out_tok, err


def main():
    from openai import OpenAI

    rows = json.loads(OUT_JSON.read_text())
    failed = [r for r in rows if needs_retry(r)]
    print(f"loaded {len(rows)} rows, {len(failed)} need retry\n")

    if not failed:
        print("nothing to retry, just re-rendering report")
        OUT_MD.write_text(render_report(rows))
        return

    client = OpenAI(
        base_url="https://api.fireworks.ai/inference/v1",
        api_key=__import__("os").environ.get(
            "FIREWORKS_API_KEY", "fw_8Kyu9Ug7kXVp6kPRDvhL3n"),
    )

    bursts: dict[str, list[bytes]] = {}
    for clip in CLIPS:
        path = ROOT / clip["path"]
        if path.exists():
            bursts[clip["id"]] = extract_burst(str(path), N_BURST)

    model_meta = {tag: (mid, mt) for tag, mid, mt in MODELS}
    prompt_meta = {tag: p for tag, p in PROMPTS}
    clip_meta = {c["id"]: c for c in CLIPS}

    fixed = 0
    for i, row in enumerate(failed, 1):
        clip = clip_meta[row["clip"]]
        frames = bursts.get(clip["id"])
        if not frames:
            print(f"  [{i}/{len(failed)}] no frames for "
                  f"{clip['id']}, skipping")
            continue
        model_id, max_tok = model_meta[row["model"]]
        prompt = prompt_meta[row["prompt"]]
        print(f"  [{i}/{len(failed)}] {row['clip']:10s} "
              f"{row['model']:18s} {row['prompt']:5s} rep{row['rep']}")
        # Be polite to avoid re-hitting the limit
        time.sleep(1.5)
        text, ms, in_tok, out_tok, err = call_with_retry(
            client, model_id, frames, prompt, max_tok)
        parsed = parse_json(text) or {}
        row["raw"] = text
        row["ms"] = ms
        row["in_tok"] = in_tok
        row["out_tok"] = out_tok
        row["error"] = err
        row["pred_length"] = normalise_length(parsed.get("length"))
        row["pred_shot"] = parsed.get("shot_type")
        row["pred_line"] = parsed.get("line")
        row["pred_bounce"] = parsed.get("bounce")
        row["pred_angle"] = parsed.get("bowling_angle")
        row["pred_handed"] = parsed.get("batsman_handed")
        ok = row["pred_length"] is not None or row["pred_shot"] is not None
        print(f"      → {ms/1000:.1f}s  in={in_tok} out={out_tok}  "
              f"len={row['pred_length']} shot={row['pred_shot']}  "
              f"err={err[:40] if err else '-'}  "
              f"{'FIXED' if ok else 'STILL FAILED'}")
        if ok:
            fixed += 1
        # Persist every loop iteration
        OUT_JSON.write_text(json.dumps(rows, indent=2, default=str))

    OUT_MD.write_text(render_report(rows))
    print(f"\nFixed {fixed}/{len(failed)} cells.")
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_MD}")


if __name__ == "__main__":
    main()
