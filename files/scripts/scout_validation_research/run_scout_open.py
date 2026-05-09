#!/usr/bin/env python3
"""Open-ended Scout descriptions — diagnostic corpus (natural language).

Same frames + Groq multimodal wiring as ``run_scout_focused.py`` but with a
description-only prompt. Does **not** touch ``run_scout.py``, ``Vision``, or
``run_scout_focused.py``.

Writes ``output/scout_responses_open.jsonl``.

Example::

    cd files/scripts/scout_validation_research
    PYTHONPATH=../.. python3 run_scout_open.py --throttle-s 0.35
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import csv
import json
import sys
from pathlib import Path
from typing import Any

import cv2

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_LABELS_CSV = SCRIPT_DIR / "output" / "labels_to_fill.csv"
OUTPUT_JSONL = SCRIPT_DIR / "output" / "scout_responses_open.jsonl"

OPEN_PROMPT = """This is a single frame from a professional cricket match broadcast on television.

Describe what you see in this frame in detail. Specifically address:
- What is the camera showing? (e.g., wide field view, closeup of a player, crowd shot, score graphic)
- What are the people in the frame doing? (e.g., bowler running, batter standing, players talking, fielders walking)
- Are there any graphical overlays? (e.g., score graphics, REPLAY tags, sponsor logos, player stats)
- What does the action level look like? (e.g., active play happening, between deliveries, post-action moment, replay or slow-motion)

Provide a 2-4 sentence description in plain language. Don't classify the frame; just describe it.
"""


def _ensure_path() -> None:
    root_s = str(SCRIPT_DIR.parent.parent.resolve())
    if root_s not in sys.path:
        sys.path.insert(0, root_s)


def groq_completion_to_jsonable(resp: Any) -> dict[str, Any]:
    """Flatten Groq SDK completion for JSON serialization."""
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


async def open_scout_call(
        client,
        *,
        model: str,
        image_b64: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
        timeout_s: float,
) -> tuple[str | None, dict[str, Any] | None]:
    try:
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
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
            ),
            timeout=timeout_s,
        )
        raw_d = groq_completion_to_jsonable(resp)
        text = ""
        if resp.choices and resp.choices[0].message:
            text = (resp.choices[0].message.content or "").strip()
        return text, raw_d
    except asyncio.TimeoutError:
        print("[err] Groq: timeout", file=sys.stderr)
        return None, None
    except Exception as e:
        print(f"[err] Groq: {e}", file=sys.stderr)
        return None, None


async def main_async(args: argparse.Namespace) -> int:
    _ensure_path()
    from groq import AsyncGroq
    from eyes.config import GROQ_API_KEY, GROQ_PRIMARY_MODEL

    labels_csv = args.labels_csv.resolve()
    client = AsyncGroq(api_key=GROQ_API_KEY, timeout=args.timeout_s)
    OUTPUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    if not args.append:
        OUTPUT_JSONL.unlink(missing_ok=True)

    processed = 0
    short_generic = 0
    short_len = 40

    with labels_csv.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

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
            continue
        mat = cv2.imread(str(img_path))
        if mat is None:
            print(f"[err] imread {img_path}", file=sys.stderr)
            continue

        _, buf = cv2.imencode(".jpg", mat, [cv2.IMWRITE_JPEG_QUALITY, 80])
        b64 = base64.b64encode(buf).decode()

        txt, raw_d = await open_scout_call(
            client,
            model=GROQ_PRIMARY_MODEL,
            image_b64=b64,
            prompt=OPEN_PROMPT,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            timeout_s=args.timeout_s + 30.0,
        )
        if txt is None:
            txt = ""
        if txt and len(txt) < short_len:
            short_generic += 1

        rec = {
            "frame_path": rel,
            "source_clip": row.get("source_clip", ""),
            "time_in_clip_s": row.get("time_in_clip_s", ""),
            "ground_truth": gt,
            "open_description": txt,
            "raw_response": raw_d,
        }
        with OUTPUT_JSONL.open("a", encoding="utf-8") as out:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        processed += 1
        if args.throttle_s > 0:
            await asyncio.sleep(args.throttle_s)
        if args.limit is not None and processed >= args.limit:
            break

    await client.close()
    rate_short = short_generic / processed if processed else 0.0
    print(f"Wrote {OUTPUT_JSONL} ({processed} rows, "
          f"very_short_desc(<{short_len}ch)={short_generic} {rate_short:.1%})")
    if processed and rate_short > 0.25:
        print(
            f"[S1] Many very short replies — bump --max-tokens or "
            f"--temperature; retry subset.",
            file=sys.stderr,
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--labels-csv", type=Path, default=DEFAULT_LABELS_CSV)
    p.add_argument("--throttle-s", type=float, default=0.35)
    p.add_argument("--max-tokens", type=int, default=220)
    p.add_argument("--temperature", type=float, default=0.2)
    p.add_argument("--timeout-s", type=float, default=90.0)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--append", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p


def main() -> None:
    raise SystemExit(asyncio.run(main_async(build_parser().parse_args())))


if __name__ == "__main__":
    main()
