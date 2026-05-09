#!/usr/bin/env python3
"""Delivery-detection focused Scout prompt (A/B vs production `run_scout.py`).

Calls Groq directly with the same multimodal pattern as `Vision._scout_call`
but **does not** use `Vision.describe` or `SCOUT_PROMPT`.

Writes ``output/scout_responses_focused.jsonl``.

Example::

    cd files/scripts/scout_validation_research
    PYTHONPATH=../.. python3 run_scout_focused.py --throttle-s 0.35
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import csv
import json
import re
import sys
from pathlib import Path

import cv2

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_LABELS_CSV = SCRIPT_DIR / "output" / "labels_to_fill.csv"
OUTPUT_JSONL = SCRIPT_DIR / "output" / "scout_responses_focused.jsonl"

FOCUSED_PROMPT = """Look at this single frame from a cricket broadcast.

Classify this frame as ONE of:
- "action": shows the actual delivery moment — bowler running in, releasing the ball, ball in flight, or batter playing the shot
- "replay": shows a delivery being replayed, often in slow motion, often with a REPLAY graphic overlay, often from a different camera angle than the live broadcast camera
- "ad": television commercial
- "umpire": shows umpire signaling (out, six, four, no-ball, wide, dead ball)
- "other": anything else — closeup of a single player, score graphic, crowd shot, between-deliveries footage, post-action reaction, players talking

Important guidance:
- If the frame shows a wide pitch view with the bowler in his run-up or delivery stride, classify as "action"
- If the frame shows a wide pitch view with players setting up between deliveries (no one bowling or batting), classify as "other"
- If you cannot tell from this single frame whether something is action or replay, default to "action" (replay typically has visual cues like graphics overlays, slow-motion artifacts, or different camera angles)

Respond with only the single word: action, replay, ad, umpire, or other.
"""

VALID_LABELS = frozenset({"action", "replay", "ad", "umpire", "other"})
_TOKEN_RE = re.compile(r"[a-z]+", re.IGNORECASE)


def _ensure_path() -> None:
    root_s = str(SCRIPT_DIR.parent.parent.resolve())
    if root_s not in sys.path:
        sys.path.insert(0, root_s)


def parse_focused_label(raw: str | None) -> str:
    if not raw or not str(raw).strip():
        return "invalid"
    for m in _TOKEN_RE.finditer(raw.lower()):
        tok = m.group(0).lower()
        if tok in VALID_LABELS:
            return tok
    return "invalid"


def _encode_jpeg_b64(bgr) -> str:
    _, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(buf).decode()


async def focused_scout_call(
        client,
        *,
        model: str,
        image_b64: str,
        prompt: str,
        max_tokens: int,
) -> str | None:
    try:
        resp = await client.chat.completions.create(
            model=model,
            temperature=0,
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
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[err] Groq: {e}", file=sys.stderr)
        return None


async def main_async(args: argparse.Namespace) -> int:
    _ensure_path()
    from groq import AsyncGroq
    from eyes.config import GROQ_API_KEY, GROQ_PRIMARY_MODEL

    labels_csv = args.labels_csv.resolve()
    client = AsyncGroq(api_key=GROQ_API_KEY, timeout=7.0)
    OUTPUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    if not args.append:
        OUTPUT_JSONL.unlink(missing_ok=True)

    processed = 0
    invalid_n = 0

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

        b64 = _encode_jpeg_b64(mat)
        raw = await focused_scout_call(
            client,
            model=GROQ_PRIMARY_MODEL,
            image_b64=b64,
            prompt=FOCUSED_PROMPT,
            max_tokens=args.max_tokens,
        )
        fl = parse_focused_label(raw)
        if fl == "invalid":
            invalid_n += 1
            print(f"[warn] invalid parse {rel!r}: {raw!r}", file=sys.stderr)

        rec = {
            "frame_path": rel,
            "source_clip": row.get("source_clip", ""),
            "time_in_clip_s": row.get("time_in_clip_s", ""),
            "ground_truth": gt,
            "focused_response_raw": raw,
            "focused_label": fl,
        }
        with OUTPUT_JSONL.open("a", encoding="utf-8") as out:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        processed += 1
        if args.throttle_s > 0:
            await asyncio.sleep(args.throttle_s)
        if args.limit is not None and processed >= args.limit:
            break

    await client.close()
    inv_rate = invalid_n / processed if processed else 0.0
    print(
        f"Wrote {OUTPUT_JSONL} ({processed} rows, "
        f"invalid={invalid_n} rate={inv_rate:.1%})",
    )
    if inv_rate > 0.10 and processed >= 20:
        print(
            "[S2] Invalid parse rate >10% — tighten prompt or inspect stderr samples.",
            file=sys.stderr,
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--labels-csv", type=Path, default=DEFAULT_LABELS_CSV)
    p.add_argument("--throttle-s", type=float, default=0.35)
    p.add_argument("--max-tokens", type=int, default=32)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--append", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p


def main() -> None:
    raise SystemExit(asyncio.run(main_async(build_parser().parse_args())))


if __name__ == "__main__":
    main()
