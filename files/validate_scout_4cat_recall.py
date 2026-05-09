"""Recall-only test: how well does the v2 prompt detect 'delivery' on
frames that we KNOW are bowler's-end views?

Pulls scout_pick_*.jpg from existing delivery folders.  These frames
already passed `is_delivery_frame()`, so by construction they should
be bowler's-end views.  The question is whether Scout-with-the-v2-
prompt agrees.

Scoring:
  pred=delivery → TRUE positive
  pred=replay_scorecard with badge → could be a replay of a delivery,
        score separately
  pred=live → FALSE negative (this is the failure mode)

Usage:
    .venv/bin/python validate_scout_4cat_recall.py [--n 30]
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import random
import time
from pathlib import Path

import cv2
import numpy as np
from groq import AsyncGroq

from eyes.config import GROQ_API_KEY, GROQ_PRIMARY_MODEL
from validate_scout_4cat_iter import PROMPT_V2, parse


async def call(client: AsyncGroq, frame: np.ndarray) -> dict:
    h, w = frame.shape[:2]
    if w > 1280:
        scale = 1280 / w
        frame = cv2.resize(frame, (1280, int(h*scale)))
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    t0 = time.time()
    try:
        resp = await client.chat.completions.create(
            model=GROQ_PRIMARY_MODEL,
            temperature=0,
            max_tokens=140,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {
                         "url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": PROMPT_V2},
                ],
            }],
        )
        ms = (time.time() - t0) * 1000
        raw = resp.choices[0].message.content.strip()
    except Exception as e:
        return {"error": str(e), "ms": (time.time() - t0)*1000,
                "category": "unknown", "raw": ""}
    r = parse(raw)
    r["ms"] = round(ms)
    r["raw"] = raw
    return r


async def main(n: int) -> None:
    if not GROQ_API_KEY:
        raise SystemExit("GROQ_API_KEY missing")

    deliv_root = Path("logs/deliveries")
    candidates: list[Path] = []
    for sess in sorted(deliv_root.iterdir()):
        if not sess.is_dir():
            continue
        for d in sorted(sess.iterdir()):
            if not d.is_dir():
                continue
            for p in sorted(d.glob("scout_pick_*.jpg")):
                candidates.append(p)

    print(f"Found {len(candidates)} candidate scout_pick frames")
    random.seed(0)
    sample = random.sample(candidates, min(n, len(candidates)))
    print(f"Sampling {len(sample)} for recall test")

    client = AsyncGroq(api_key=GROQ_API_KEY, timeout=10)
    out: list[dict] = []
    for i, p in enumerate(sample):
        bgr = cv2.imread(str(p))
        if bgr is None:
            continue
        r = await call(client, bgr)
        r["i"] = i
        r["src"] = str(p)
        out.append(r)
        print(f"  [{i:02d}] {r.get('category','?'):>17s} "
              f"conf={r.get('confidence','?'):>6s} "
              f"badge={r.get('replay_badge','')[:20]:<20s} "
              f"{r.get('reason','')[:50]}  "
              f"<- {p.parent.parent.name}/{p.parent.name}")

    counts: dict[str, int] = {}
    for r in out:
        c = r.get("category", "unknown")
        counts[c] = counts.get(c, 0) + 1
    n_total = max(len(out), 1)
    print("\n=== RECALL on confirmed bowler's-end frames ===")
    for c, ct in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {c:>17s}: {ct:>3d}  ({ct*100/n_total:.0f}%)")
    delivery_count = counts.get("delivery", 0)
    print(f"\nDelivery recall: {delivery_count}/{n_total} = "
          f"{delivery_count*100/n_total:.0f}%")

    out_dir = Path("logs/scout_4cat_validation/recall_test")
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "results.jsonl").open("w") as f:
        for r in out:
            f.write(json.dumps(r) + "\n")
    print(f"\nSaved → {out_dir}/results.jsonl")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=30)
    args = p.parse_args()
    asyncio.run(main(args.n))
