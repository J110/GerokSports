"""
Simplified Tagger Prompt Test
Tests the 3-boolean approach (has_strip, has_overlay_stats, drs_review)
across DashScope, Qwen3-VL (Together), and Scout 17B (Groq).
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
import time
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from eyes.config import (
    DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, DASHSCOPE_VISION_MODEL,
    GROQ_API_KEY, GROQ_PRIMARY_MODEL,
    TOGETHER_API_KEY, TOGETHER_VISION_MODEL,
)

DEBUG_DIR = Path(__file__).parent / "debug_frames"

# ── The new simplified prompt ──
SIMPLIFIED_TAGGER = """\
Classify this cricket broadcast frame. Reply JSON only.

{
  "has_strip": true | false,
  "has_overlay_stats": true | false,
  "drs_review": true | false
}

has_strip: Is the team score strip visible at the bottom?
has_overlay_stats: Are career/tournament/head-to-head stats shown as an OVERLAY on top of the live feed? (NOT the regular scoreboard strip)
drs_review: Is a DRS review decision being shown?\
"""

# ── All test frames with ground truth ──
FRAMES = [
    # CONFIRMED FAILURES
    {"file": "f1_ad.jpg",
     "gt": {"has_strip": False, "has_overlay_stats": False, "drs_review": False},
     "note": "Pure ad/pre-match. No strip."},
    {"file": "f4_ad.jpg",
     "gt": {"has_strip": False, "has_overlay_stats": False, "drs_review": False},
     "note": "Ad frame."},
    {"file": "f5_ad.jpg",
     "gt": {"has_strip": False, "has_overlay_stats": False, "drs_review": False},
     "note": "Ad frame."},
    {"file": "f20_unknown.jpg",
     "gt": {"has_strip": True, "has_overlay_stats": True, "drs_review": False},
     "note": "FAILURE: Qwen tagged UNKNOWN. Strip visible + info panel overlay."},
    {"file": "f60_unknown.jpg",
     "gt": {"has_strip": True, "has_overlay_stats": False, "drs_review": False},
     "note": "FAILURE: Qwen tagged UNKNOWN. Strip visible, field graphic overlay."},
    {"file": "f150_scoreboard.jpg",
     "gt": {"has_strip": True, "has_overlay_stats": False, "drs_review": False},
     "note": "FAILURE: Both said 'advertisement'. Strip IS visible."},
    {"file": "f160_graphic.jpg",
     "gt": {"has_strip": True, "has_overlay_stats": True, "drs_review": False},
     "note": "FAILURE: Extractor got None. Graphic overlay + strip."},
    {"file": "f170_ad.jpg",
     "gt": {"has_strip": False, "has_overlay_stats": False, "drs_review": False},
     "note": "FAILURE: Scout hallucinated zeros. Actually an ad."},
    {"file": "f210_ad.jpg",
     "gt": {"has_strip": False, "has_overlay_stats": False, "drs_review": False},
     "note": "Ad frame. Both got it right."},
    # WORKING BASELINES
    {"file": "f6_graphic.jpg",
     "gt": {"has_strip": True, "has_overlay_stats": True, "drs_review": False},
     "note": "Graphic with strip."},
    {"file": "f7_scoreboard.jpg",
     "gt": {"has_strip": True, "has_overlay_stats": False, "drs_review": False},
     "note": "Clean scoreboard. WORKING baseline."},
    {"file": "f9_scoreboard.jpg",
     "gt": {"has_strip": True, "has_overlay_stats": False, "drs_review": False},
     "note": "Clean scoreboard. WORKING baseline."},
    {"file": "f10_scoreboard.jpg",
     "gt": {"has_strip": True, "has_overlay_stats": False, "drs_review": False},
     "note": "Clean scoreboard. WORKING baseline."},
    {"file": "f30_scoreboard.jpg",
     "gt": {"has_strip": True, "has_overlay_stats": False, "drs_review": False},
     "note": "Clean scoreboard."},
    {"file": "f40_scoreboard.jpg",
     "gt": {"has_strip": True, "has_overlay_stats": False, "drs_review": False},
     "note": "Clean scoreboard."},
    {"file": "f50_scoreboard.jpg",
     "gt": {"has_strip": True, "has_overlay_stats": False, "drs_review": False},
     "note": "Clean scoreboard."},
    {"file": "f70_scoreboard.jpg",
     "gt": {"has_strip": True, "has_overlay_stats": False, "drs_review": False},
     "note": "Clean scoreboard."},
    {"file": "f80_scoreboard.jpg",
     "gt": {"has_strip": True, "has_overlay_stats": False, "drs_review": False},
     "note": "Clean scoreboard."},
    {"file": "f100_scoreboard.jpg",
     "gt": {"has_strip": True, "has_overlay_stats": False, "drs_review": False},
     "note": "Clean scoreboard. WORKING baseline."},
    {"file": "f110_scoreboard.jpg",
     "gt": {"has_strip": True, "has_overlay_stats": False, "drs_review": False},
     "note": "Clean scoreboard."},
    {"file": "f120_scoreboard.jpg",
     "gt": {"has_strip": True, "has_overlay_stats": False, "drs_review": False},
     "note": "Clean scoreboard."},
    {"file": "f130_scoreboard.jpg",
     "gt": {"has_strip": True, "has_overlay_stats": False, "drs_review": False},
     "note": "Clean scoreboard."},
    {"file": "f140_scoreboard.jpg",
     "gt": {"has_strip": True, "has_overlay_stats": False, "drs_review": False},
     "note": "Clean scoreboard."},
    {"file": "f180_graphic.jpg",
     "gt": {"has_strip": True, "has_overlay_stats": True, "drs_review": False},
     "note": "Career stats overlay + strip visible."},
    {"file": "f190_scoreboard.jpg",
     "gt": {"has_strip": True, "has_overlay_stats": False, "drs_review": False},
     "note": "Clean scoreboard."},
    {"file": "f200_scoreboard.jpg",
     "gt": {"has_strip": True, "has_overlay_stats": False, "drs_review": False},
     "note": "Clean scoreboard."},
]


def encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def parse_json(raw: str) -> dict | None:
    text = raw.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    return None


async def call_dashscope(b64: str, prompt: str) -> tuple[str, int]:
    import httpx
    t0 = time.time()
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(
            f"{DASHSCOPE_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": DASHSCOPE_VISION_MODEL, "temperature": 0,
                  "max_tokens": 80,
                  "messages": [{"role": "user", "content": [
                      {"type": "image_url",
                       "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                      {"type": "text", "text": prompt}]}]},
        )
    ms = int((time.time() - t0) * 1000)
    if r.status_code != 200:
        return f"ERR {r.status_code}", ms
    return r.json()["choices"][0]["message"]["content"].strip(), ms


async def call_together(b64: str, prompt: str) -> tuple[str, int]:
    import httpx
    t0 = time.time()
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(
            "https://api.together.xyz/v1/chat/completions",
            headers={"Authorization": f"Bearer {TOGETHER_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": TOGETHER_VISION_MODEL, "temperature": 0,
                  "max_tokens": 80,
                  "messages": [{"role": "user", "content": [
                      {"type": "image_url",
                       "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                      {"type": "text", "text": prompt}]}]},
        )
    ms = int((time.time() - t0) * 1000)
    if r.status_code != 200:
        return f"ERR {r.status_code}", ms
    return r.json()["choices"][0]["message"]["content"].strip(), ms


async def call_groq(b64: str, prompt: str) -> tuple[str, int]:
    from groq import AsyncGroq
    t0 = time.time()
    client = AsyncGroq(api_key=GROQ_API_KEY, timeout=10)
    try:
        resp = await client.chat.completions.create(
            model=GROQ_PRIMARY_MODEL, temperature=0, max_tokens=80,
            messages=[{"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": prompt}]}])
        ms = int((time.time() - t0) * 1000)
        return resp.choices[0].message.content.strip(), ms
    except Exception as e:
        return f"ERR: {e}"[:100], int((time.time() - t0) * 1000)
    finally:
        await client.close()


def score_result(parsed: dict | None, gt: dict) -> dict:
    if not parsed:
        return {"strip": False, "overlay": False, "drs": False, "total": 0, "max": 3}
    s = parsed.get("has_strip") == gt["has_strip"]
    o = parsed.get("has_overlay_stats") == gt["has_overlay_stats"]
    d = parsed.get("drs_review") == gt["drs_review"]
    return {"strip": s, "overlay": o, "drs": d,
            "total": int(s) + int(o) + int(d), "max": 3}


async def test_frame(frame: dict) -> dict | None:
    path = DEBUG_DIR / frame["file"]
    if not path.exists():
        return None
    b64 = encode_image(str(path))

    ds, tg, gr = await asyncio.gather(
        call_dashscope(b64, SIMPLIFIED_TAGGER),
        call_together(b64, SIMPLIFIED_TAGGER),
        call_groq(b64, SIMPLIFIED_TAGGER),
        return_exceptions=True,
    )

    def safe(r):
        return r if not isinstance(r, Exception) else (str(r)[:80], 0)

    ds_raw, ds_ms = safe(ds)
    tg_raw, tg_ms = safe(tg)
    gr_raw, gr_ms = safe(gr)

    ds_parsed = parse_json(ds_raw)
    tg_parsed = parse_json(tg_raw)
    gr_parsed = parse_json(gr_raw)

    gt = frame["gt"]

    return {
        "file": frame["file"], "note": frame["note"], "gt": gt,
        "dashscope": {"raw": ds_raw, "parsed": ds_parsed, "ms": ds_ms,
                      "score": score_result(ds_parsed, gt)},
        "qwen":     {"raw": tg_raw, "parsed": tg_parsed, "ms": tg_ms,
                     "score": score_result(tg_parsed, gt)},
        "scout":    {"raw": gr_raw, "parsed": gr_parsed, "ms": gr_ms,
                     "score": score_result(gr_parsed, gt)},
    }


def flag(ok: bool) -> str:
    return "✓" if ok else "✗"


async def main():
    print("=" * 90)
    print("Simplified 3-Boolean Tagger — DashScope vs Qwen3-VL vs Scout 17B")
    print("=" * 90)
    print(f"Prompt: has_strip / has_overlay_stats / drs_review")
    print(f"Models: {DASHSCOPE_VISION_MODEL} | {TOGETHER_VISION_MODEL} | {GROQ_PRIMARY_MODEL}")
    print(f"Frames: {len(FRAMES)}")
    print()

    # Batch: run up to 3 frames concurrently to stay under rate limits
    results = []
    BATCH = 3
    for i in range(0, len(FRAMES), BATCH):
        batch = FRAMES[i:i + BATCH]
        batch_results = await asyncio.gather(
            *[test_frame(f) for f in batch])
        for r in batch_results:
            if r:
                results.append(r)

    # Per-model totals
    totals = {
        "dashscope": {"strip": 0, "overlay": 0, "drs": 0, "total": 0, "ms": 0},
        "qwen":      {"strip": 0, "overlay": 0, "drs": 0, "total": 0, "ms": 0},
        "scout":     {"strip": 0, "overlay": 0, "drs": 0, "total": 0, "ms": 0},
    }
    n = len(results)

    for r in results:
        for model in ("dashscope", "qwen", "scout"):
            s = r[model]["score"]
            totals[model]["strip"] += int(s["strip"])
            totals[model]["overlay"] += int(s["overlay"])
            totals[model]["drs"] += int(s["drs"])
            totals[model]["total"] += s["total"]
            totals[model]["ms"] += r[model]["ms"]

    # Detailed per-frame output
    for r in results:
        is_failure = "FAILURE" in r["note"]
        marker = " *** FAILURE FRAME ***" if is_failure else ""
        print(f"{'─' * 90}")
        print(f"  {r['file']}{marker}")
        print(f"  {r['note']}")
        gt = r["gt"]
        print(f"  GT: strip={gt['has_strip']}  overlay={gt['has_overlay_stats']}  drs={gt['drs_review']}")

        for label, model in [("DashScope", "dashscope"),
                             ("Qwen3-VL", "qwen"),
                             ("Scout17B", "scout")]:
            p = r[model]["parsed"]
            s = r[model]["score"]
            ms = r[model]["ms"]
            if p:
                strip_v = p.get("has_strip")
                overlay_v = p.get("has_overlay_stats")
                drs_v = p.get("drs_review")
                print(f"  {label:10s}: "
                      f"strip={flag(s['strip'])}{str(strip_v):<6s} "
                      f"overlay={flag(s['overlay'])}{str(overlay_v):<6s} "
                      f"drs={flag(s['drs'])}{str(drs_v):<6s} "
                      f"({s['total']}/3) {ms}ms")
            else:
                raw_preview = r[model]["raw"][:60]
                print(f"  {label:10s}: PARSE FAIL — '{raw_preview}' {ms}ms")
        print()

    # Summary table
    print(f"\n{'=' * 90}")
    print("SUMMARY")
    print(f"{'=' * 90}")
    print(f"\n{'Model':<20s} {'strip':>8s} {'overlay':>8s} {'drs':>8s} "
          f"{'TOTAL':>8s} {'avg ms':>8s}")
    print(f"{'─' * 20} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 8}")
    for label, model in [("DashScope (max)", "dashscope"),
                         ("Qwen3-VL 8B", "qwen"),
                         ("Scout 17B", "scout")]:
        t = totals[model]
        avg_ms = t["ms"] // n if n else 0
        print(f"{label:<20s} "
              f"{t['strip']:>3d}/{n:<3d}  "
              f"{t['overlay']:>3d}/{n:<3d}  "
              f"{t['drs']:>3d}/{n:<3d}  "
              f"{t['total']:>3d}/{n*3:<3d}  "
              f"{avg_ms:>5d}ms")

    # Failure-only summary
    failures = [r for r in results if "FAILURE" in r["note"]]
    if failures:
        fn = len(failures)
        print(f"\nFAILURE FRAMES ONLY ({fn} frames):")
        print(f"{'Model':<20s} {'strip':>8s} {'overlay':>8s} {'drs':>8s} {'TOTAL':>8s}")
        print(f"{'─' * 20} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 8}")
        for label, model in [("DashScope (max)", "dashscope"),
                             ("Qwen3-VL 8B", "qwen"),
                             ("Scout 17B", "scout")]:
            fs = ft = fo = fd = 0
            for r in failures:
                s = r[model]["score"]
                fs += int(s["strip"])
                fo += int(s["overlay"])
                fd += int(s["drs"])
                ft += s["total"]
            print(f"{label:<20s} "
                  f"{fs:>3d}/{fn:<3d}  "
                  f"{fo:>3d}/{fn:<3d}  "
                  f"{fd:>3d}/{fn:<3d}  "
                  f"{ft:>3d}/{fn*3:<3d}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
