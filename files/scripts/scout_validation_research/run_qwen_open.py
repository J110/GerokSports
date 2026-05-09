#!/usr/bin/env python3
"""Open-ended Qwen-VL descriptions — same frames + prompt as ``run_scout_open.py``.

Invokes **production Layer2 Qwen surface**: Fireworks OpenAI-compatible API with
``accounts/fireworks/models/qwen3-vl-30b-a3b-instruct`` (see
``files/layer2_classifier.py``).

Writes ``output/qwen_responses_open.jsonl`` (same record shape as Scout open run).

Example::

    cd files/scripts/scout_validation_research
    PYTHONPATH=../.. python3 run_qwen_open.py --throttle-s 1.0
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import cv2

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_LABELS_CSV = SCRIPT_DIR / "output" / "labels_to_fill.csv"
OUTPUT_JSONL = SCRIPT_DIR / "output" / "qwen_responses_open.jsonl"

# Must match run_scout_open.OPEN_PROMPT for fair A/B comparison.
OPEN_PROMPT = """This is a single frame from a professional cricket match broadcast on television.

Describe what you see in this frame in detail. Specifically address:
- What is the camera showing? (e.g., wide field view, closeup of a player, crowd shot, score graphic)
- What are the people in the frame doing? (e.g., bowler running, batter standing, players talking, fielders walking)
- Are there any graphical overlays? (e.g., score graphics, REPLAY tags, sponsor logos, player stats)
- What does the action level look like? (e.g., active play happening, between deliveries, post-action moment, replay or slow-motion)

Provide a 2-4 sentence description in plain language. Don't classify the frame; just describe it.
"""

# Layer2 production path (files/layer2_classifier.py).
QWEN_MODEL = "accounts/fireworks/models/qwen3-vl-30b-a3b-instruct"
FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"

# Fireworks list pricing (2026, serverless): Qwen3 VL 30B A3B Instruct —
# $0.15 / 1M input tokens, $0.60 / 1M output tokens
# (https://fireworks.ai/pricing). Image tokens dominate input; expect
# ~1–3k tokens/image + text — order of **$0.0003–0.001 per frame** ⇒
# **247 frames ≪ $10** (confirm via ``usage`` on each response).


def _ensure_path() -> None:
    root_s = str(SCRIPT_DIR.parent.parent.resolve())
    if root_s not in sys.path:
        sys.path.insert(0, root_s)


def fireworks_completion_to_jsonable(resp: Any) -> dict[str, Any]:
    """Flatten OpenAI SDK completion for JSON serialization."""
    if hasattr(resp, "model_dump"):
        try:
            d = resp.model_dump()
            if isinstance(d, dict):
                return d
        except Exception:
            pass
    out: dict[str, Any] = {
        "id": getattr(resp, "id", None),
        "model": getattr(resp, "model", None),
        "object": getattr(resp, "object", None),
        "choices": [],
    }
    ch = getattr(resp, "choices", None) or []
    for i, c in enumerate(ch):
        msg = getattr(c, "message", None)
        out["choices"].append({
            "index": getattr(c, "index", i),
            "finish_reason": getattr(c, "finish_reason", None),
            "message": {
                "role": getattr(msg, "role", None),
                "content": (getattr(msg, "content", None) or "").strip(),
            },
        })
    usage = getattr(resp, "usage", None)
    if usage is not None:
        if hasattr(usage, "model_dump"):
            try:
                out["usage"] = usage.model_dump()
            except Exception:
                out["usage"] = {}
        else:
            out["usage"] = {
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            }
    else:
        out["usage"] = None
    return out


def estimate_usd_from_usage(u: dict[str, Any] | None) -> float | None:
    if not u:
        return None
    pi = u.get("prompt_tokens")
    co = u.get("completion_tokens")
    if pi is None and co is None:
        return None
    pi = int(pi or 0)
    co = int(co or 0)
    return (pi * 0.15 + co * 0.60) / 1_000_000.0


def qwen_open_call_sync(
        client: Any,
        *,
        model: str,
        image_b64: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
        timeout: float,
) -> tuple[str | None, dict[str, Any] | None, int | None]:
    """Blocking Fireworks call. Returns (text, raw_dict, latency_ms)."""
    t0 = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_b64}",
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        ms = int((time.perf_counter() - t0) * 1000)
        raw_d = fireworks_completion_to_jsonable(resp)
        text = ""
        if resp.choices and resp.choices[0].message:
            text = (resp.choices[0].message.content or "").strip()
        return text, raw_d, ms
    except Exception as e:
        ms = int((time.perf_counter() - t0) * 1000)
        print(f"[err] Fireworks Qwen: {e}", file=sys.stderr)
        return None, {"error": str(e)[:500]}, ms


async def main_async(args: argparse.Namespace) -> int:
    _ensure_path()
    from openai import OpenAI

    api_key = os.environ.get(
        "FIREWORKS_API_KEY", "fw_8Kyu9Ug7kXVp6kPRDvhL3n")
    client = OpenAI(base_url=FIREWORKS_BASE_URL, api_key=api_key)
    model = args.model

    labels_csv = args.labels_csv.resolve()
    OUTPUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    if not args.append:
        OUTPUT_JSONL.unlink(missing_ok=True)

    processed = ok = errors = 0
    short_generic = 0
    short_len = 40
    total_usd_est = 0.0
    latencies: list[int] = []

    with labels_csv.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    # Pre-flight cost note (theoretical cap at public list rates).
    print(
        "Cost note: Fireworks Qwen3-VL-30B ≈ $0.15/1M in + $0.60/1M out tokens; "
        f"247 frames typically ≪ $10 (see per-response usage).",
        file=sys.stderr,
    )

    for row in rows:
        gt = (row.get("label") or "").strip()
        rel = (row.get("frame_path") or "").strip()
        if not rel:
            continue
        img_path = (SCRIPT_DIR / rel).resolve()
        if args.dry_run:
            print(f"[dry-run] {img_path}")
            processed += 1
            continue
        if not img_path.is_file():
            print(f"[err] missing {img_path}", file=sys.stderr)
            errors += 1
            continue
        mat = cv2.imread(str(img_path))
        if mat is None:
            print(f"[err] imread {img_path}", file=sys.stderr)
            errors += 1
            continue

        _, buf = cv2.imencode(".jpg", mat, [cv2.IMWRITE_JPEG_QUALITY, 80])
        b64 = base64.b64encode(buf).decode()

        txt, raw_d, wall_ms = await asyncio.to_thread(
            qwen_open_call_sync,
            client,
            model=model,
            image_b64=b64,
            prompt=OPEN_PROMPT,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            timeout=args.timeout_s,
        )
        if wall_ms is not None:
            latencies.append(wall_ms)
        if txt is None:
            txt = ""
            errors += 1
        else:
            ok += 1
        if raw_d and isinstance(raw_d, dict):
            u = raw_d.get("usage")
            est = estimate_usd_from_usage(u)
            if est is not None:
                total_usd_est += est

        if txt and len(txt) < short_len:
            short_generic += 1

        rec = {
            "frame_path": rel,
            "source_clip": row.get("source_clip", ""),
            "time_in_clip_s": row.get("time_in_clip_s", ""),
            "ground_truth": gt,
            "open_description": txt,
            "latency_ms": wall_ms,
            "raw_response": raw_d,
        }
        with OUTPUT_JSONL.open("a", encoding="utf-8") as out:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        processed += 1
        if args.throttle_s > 0:
            await asyncio.sleep(args.throttle_s)
        if args.limit is not None and processed >= args.limit:
            break

    err_rate = errors / processed if processed else 0.0
    rate_short = short_generic / processed if processed else 0.0
    lat_note = ""
    if latencies:
        lat_note = (
            f" latency_ms p50={sorted(latencies)[len(latencies)//2]} "
            f"p90={sorted(latencies)[int(len(latencies)*0.9)-1]}"
        )
    print(
        f"Wrote {OUTPUT_JSONL} ({processed} rows, errors={errors} "
        f"{err_rate:.1%}, very_short(<{short_len}ch)={short_generic} {rate_short:.1%},"
        f" est_cost_usd_sum≈{total_usd_est:.4f}{lat_note})",
    )
    if processed and err_rate > 0.10:
        print(
            "[S4] Qwen error rate >10% on this batch — review logs; "
            "comparison script should subset to successes.",
            file=sys.stderr,
        )
    if processed and rate_short > 0.25:
        print(
            f"[S3] Many very short replies — bump --max-tokens or check model output.",
            file=sys.stderr,
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--labels-csv", type=Path, default=DEFAULT_LABELS_CSV)
    p.add_argument("--model", type=str, default=QWEN_MODEL)
    p.add_argument("--throttle-s", type=float, default=1.0)
    p.add_argument("--max-tokens", type=int, default=220)
    p.add_argument("--temperature", type=float, default=0.2)
    p.add_argument("--timeout-s", type=float, default=120.0)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--append", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p


def main() -> None:
    raise SystemExit(asyncio.run(main_async(build_parser().parse_args())))


if __name__ == "__main__":
    main()
