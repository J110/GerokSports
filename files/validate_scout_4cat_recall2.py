"""Recall test on truly-classified deliveries.

Source: delivery folders where Scout's existing classifier (the
detailed prompt) returned a non-unknown length+line.  These are
ground-truth bowler's-end delivery views.

For each, run the v2 4-category prompt on every saved scout_pick frame
(typically 5 per delivery).  Report:
  - per-frame category
  - per-delivery: did ANY of its frames get tagged "delivery"?
  - per-delivery: what fraction of frames got "delivery"?
"""
from __future__ import annotations

import asyncio
import base64
import json
import time
from pathlib import Path

import cv2
from groq import AsyncGroq

from eyes.config import GROQ_API_KEY, GROQ_PRIMARY_MODEL
from validate_scout_4cat_iter import PROMPT_V2, parse


def find_classified_deliveries() -> list[Path]:
    out: list[Path] = []
    for sess in sorted(Path("logs/deliveries").iterdir()):
        if not sess.is_dir():
            continue
        for d in sorted(sess.iterdir()):
            if not d.is_dir():
                continue
            pj = d / "predictions.json"
            if not pj.exists():
                continue
            try:
                o = json.load(open(pj))
            except Exception:
                continue
            if (o.get("vlm_confidence") in ("high", "medium")
                    and o.get("components", {}).get("2_length") not in (
                        None, "", "unknown")):
                out.append(d)
    return out


async def call(client: AsyncGroq, frame) -> dict:
    h, w = frame.shape[:2]
    if w > 1280:
        scale = 1280/w
        frame = cv2.resize(frame, (1280, int(h*scale)))
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    t0 = time.time()
    try:
        resp = await client.chat.completions.create(
            model=GROQ_PRIMARY_MODEL, temperature=0, max_tokens=140,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": PROMPT_V2},
            ]}],
        )
        ms = (time.time()-t0)*1000
        raw = resp.choices[0].message.content.strip()
    except Exception as e:
        return {"category": "unknown", "raw": "", "error": str(e),
                "ms": (time.time()-t0)*1000}
    r = parse(raw)
    r["ms"] = round(ms)
    return r


async def main() -> None:
    if not GROQ_API_KEY:
        raise SystemExit("GROQ_API_KEY missing")
    delivs = find_classified_deliveries()
    print(f"Found {len(delivs)} truly classified deliveries")

    client = AsyncGroq(api_key=GROQ_API_KEY, timeout=10)
    per_delivery = []
    for di, d in enumerate(delivs):
        picks = sorted(d.glob("scout_pick_*.jpg"))
        if not picks:
            continue
        cats: list[str] = []
        for p in picks:
            bgr = cv2.imread(str(p))
            if bgr is None:
                continue
            r = await call(client, bgr)
            cats.append(r.get("category", "unknown"))
        n_del = sum(1 for c in cats if c == "delivery")
        n_rep = sum(1 for c in cats if c == "replay_scorecard")
        n_live = sum(1 for c in cats if c == "live")
        per_delivery.append({
            "d": str(d), "n_frames": len(cats),
            "n_delivery": n_del, "n_replay": n_rep, "n_live": n_live,
            "cats": cats,
        })
        print(f"  [{di:02d}] {d.parent.name}/{d.name} "
              f"frames={len(cats)} "
              f"delivery={n_del} live={n_live} replay={n_rep}  "
              f"cats={cats}")

    n = len(per_delivery)
    any_delivery = sum(1 for r in per_delivery if r["n_delivery"] > 0)
    majority_delivery = sum(1 for r in per_delivery
                            if r["n_delivery"] > r["n_frames"]/2)
    print("\n=== RECALL ON TRULY-CLASSIFIED DELIVERIES ===")
    print(f"  Total deliveries:                   {n}")
    print(f"  Any-frame got 'delivery' tag:       {any_delivery}/{n} "
          f"({any_delivery*100/max(n,1):.0f}%)")
    print(f"  Majority of frames got 'delivery':  {majority_delivery}/{n} "
          f"({majority_delivery*100/max(n,1):.0f}%)")
    total_frames = sum(r["n_frames"] for r in per_delivery)
    total_del = sum(r["n_delivery"] for r in per_delivery)
    total_rep = sum(r["n_replay"] for r in per_delivery)
    total_live = sum(r["n_live"] for r in per_delivery)
    print(f"  Total frames: {total_frames}")
    print(f"    delivery:  {total_del}  ({total_del*100/max(total_frames,1):.0f}%)")
    print(f"    live:      {total_live}  ({total_live*100/max(total_frames,1):.0f}%)")
    print(f"    replay:    {total_rep}  ({total_rep*100/max(total_frames,1):.0f}%)")

    out_dir = Path("logs/scout_4cat_validation/recall_test_v2")
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "results.jsonl").open("w") as f:
        for r in per_delivery:
            f.write(json.dumps(r) + "\n")
    print(f"\nSaved → {out_dir}/results.jsonl")


if __name__ == "__main__":
    asyncio.run(main())
