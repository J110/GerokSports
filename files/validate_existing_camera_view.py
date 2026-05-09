"""Test whether Scout's EXISTING production prompt reliably tags these
115 confirmed-delivery frames as camera_view=bowlers_end.

Three v1/v2/v3 prompt rewrites all failed at <5% recall.  Hypothesis:
the existing description-style prompt that's been running in
production *already* tags these frames correctly — we just never
isolated and measured it.  If it does, we don't need a new prompt;
we just consume `vision.last_camera_view` as the burst signal.
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
from eyes.vision import SCOUT_PROMPT, Vision


async def call(client: AsyncGroq, frame) -> dict:
    h, w = frame.shape[:2]
    if w > 1280:
        scale = 1280/w
        frame = cv2.resize(frame, (1280, int(h*scale)))
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    prompt = SCOUT_PROMPT.format(vision_hint="None.")
    t0 = time.time()
    try:
        resp = await client.chat.completions.create(
            model=GROQ_PRIMARY_MODEL,
            temperature=0,
            max_tokens=600,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": prompt},
            ]}],
        )
        ms = (time.time()-t0)*1000
        raw = resp.choices[0].message.content.strip()
    except Exception as e:
        return {"error": str(e), "raw": "", "ms": (time.time()-t0)*1000,
                "frame_type": "?", "camera_view": None,
                "has_strip": False}
    tag, ftype = Vision._parse_tag(raw)
    has_strip = tag.get("has_strip", False) if tag else False
    has_overlay = tag.get("has_overlay_stats", False) if tag else False
    cv = Vision._normalise_camera_view(
        tag.get("camera_view") if tag else None,
        frame_type=ftype, has_strip=has_strip, has_overlay=has_overlay,
    )
    return {"frame_type": ftype, "camera_view": cv, "raw_tag": tag,
            "has_strip": has_strip, "has_overlay": has_overlay,
            "ms": round(ms)}


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


async def main() -> None:
    if not GROQ_API_KEY:
        raise SystemExit("GROQ_API_KEY missing")
    delivs = find_classified_deliveries()
    print(f"Found {len(delivs)} truly-classified deliveries")
    client = AsyncGroq(api_key=GROQ_API_KEY, timeout=15)

    per: list[dict] = []
    for di, d in enumerate(delivs):
        picks = sorted(d.glob("scout_pick_*.jpg"))
        if not picks:
            continue
        cvs: list[str | None] = []
        fts: list[str] = []
        for p in picks:
            bgr = cv2.imread(str(p))
            if bgr is None:
                continue
            r = await call(client, bgr)
            cvs.append(r.get("camera_view"))
            fts.append(r.get("frame_type", "?"))
        n_be = sum(1 for c in cvs if c == "bowlers_end")
        per.append({"d": str(d), "n_frames": len(cvs),
                    "n_bowlers_end": n_be, "camera_views": cvs,
                    "frame_types": fts})
        print(f"  [{di:02d}] {d.parent.name}/{d.name} "
              f"bowlers_end={n_be}/{len(cvs)}  cv={cvs}  ft={fts}")

    n = len(per)
    any_be = sum(1 for r in per if r["n_bowlers_end"] > 0)
    maj_be = sum(1 for r in per if r["n_bowlers_end"] > r["n_frames"]/2)
    total = sum(r["n_frames"] for r in per)
    t_be = sum(r["n_bowlers_end"] for r in per)
    print("\n=== EXISTING PROMPT — camera_view recall ===")
    print(f"  Deliveries with ANY bowlers_end frame:      {any_be}/{n}  "
          f"({any_be*100/max(n,1):.0f}%)")
    print(f"  Deliveries with MAJORITY bowlers_end:       {maj_be}/{n}  "
          f"({maj_be*100/max(n,1):.0f}%)")
    print(f"  Total frames: {total}, bowlers_end: {t_be}  "
          f"({t_be*100/max(total,1):.0f}%)")

    out_dir = Path("logs/scout_4cat_validation/existing_prompt_recall")
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "results.jsonl").open("w") as f:
        for r in per:
            f.write(json.dumps(r) + "\n")
    print(f"\nSaved → {out_dir}/results.jsonl")


if __name__ == "__main__":
    asyncio.run(main())
