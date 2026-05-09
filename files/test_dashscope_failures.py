"""
Targeted DashScope vs Current Pipeline comparison.
Tests the EXACT frames where Qwen tagger or Scout reader failed.

For each frame we test:
  1. TAGGER: DashScope qwen-vl-max classification vs Qwen3-VL (Together)
  2. READER: DashScope qwen-vl-max strip reading vs Scout 17B (Groq)
"""
import asyncio
import base64
import json
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

TAGGER_PROMPT = """\
Classify this cricket broadcast frame. Respond with EXACTLY ONE WORD:

  SCOREBOARD — bottom scoreboard strip visible with score/overs/batter info
  GRAPHIC — full-screen overlay (batting card, bowling card, lineup, stats table)
  CLOSEUP — player faces, celebrations, dugout, crowd, no scoreboard visible
  ADVERTISEMENT — ad content, sponsor logos, commercial break
  PREMATCH — countdown, toss, anthem, walkout, coin flip, ceremony

One word only. Nothing else.\
"""

READER_PROMPT = """\
You are reading a live IPL cricket broadcast frame.

FIRST — READ THE SCOREBOARD STRIP at the very BOTTOM of the screen.
The strip is a thin bar (~15% of screen height) always present during play.
It is there during live action, closeups, replays, and graphics.

OUTPUT THE STRIP DATA IMMEDIATELY in this exact format:
STRIP: [TEAM] [SCORE]-[WICKETS] ([OVERS]) | [BATTER1] [RUNS]([BALLS]) | \
[BATTER2] [RUNS]([BALLS]) | [BOWLER] [W]-[R] ([OVERS])

Example: STRIP: KKR 105-2 (11.3) | Green 45(32) | Raghuvanshi 4(5) | \
Siddharth 0-21 (2.3)

If the strip is not visible (full-screen ad, blank screen): say "NO_STRIP".

THEN — report any overlays:

INFO/CAREER PANEL (rotating overlay, larger text, above strip):
Contains words like IPL, CAREER, T20, RECORD, HEAD TO HEAD, etc.
These are NOT match stats. Label: INFO_PANEL: [text]

BOWLING SPEED: SPEED: [number] (80-160 range, kph/km/h)
EXTRAS: EXTRA: wide/no_ball/leg_bye/bye (umpire signal or wd/nb in over)
THIS OVER: ball-by-ball results (e.g. '4 . 1 6 wd 4')
FULL SCORECARD GRAPHIC: every batter/bowler row with all stats.

FINALLY — describe the cricket ACTION in 1 sentence:
What is happening? (delivery bowled, shot played, fielder diving, etc.)

CRITICAL RULES:
- Strip data FIRST, always. Even during closeups/replays.
- Report exact numbers from the strip. Don't guess or infer.
- * or > prefix on a batter name = striker.
- If this is an ADVERTISEMENT: say only "ADVERTISEMENT".

HINT FROM SCORER:
Last confirmed: LSG ~10-0 (1.3 ov), Marsh ~5(3), Markram ~2(4)\
"""

# Frames where the pipeline CONFIRMED failed, with the failure reason
FAILURE_FRAMES = [
    {
        "file": "f20_unknown.jpg",
        "qwen_tag": "unknown",      # ← FAILED: Qwen couldn't classify
        "scout_read": "digits=False, confused overs",
        "ground_truth_tag": "SCOREBOARD",
        "ground_truth_strip": True,
        "desc": "F20: Qwen tagged UNKNOWN. Scout read MITCHELL MARSH=0(1) (wrong stats). Strip visible."
    },
    {
        "file": "f60_unknown.jpg",
        "qwen_tag": "unknown",      # ← FAILED: Qwen couldn't classify
        "scout_read": "digits=False",
        "ground_truth_tag": "SCOREBOARD",
        "ground_truth_strip": True,
        "desc": "F60: Qwen tagged UNKNOWN. Strip clearly visible with live action."
    },
    {
        "file": "f150_scoreboard.jpg",
        "qwen_tag": "SCOREBOARD",   # ← Qwen OK
        "scout_read": "digits=False, said 'I see an advertisement'",
        "ground_truth_tag": "SCOREBOARD",
        "ground_truth_strip": True,
        "desc": "F150: Scout said 'advertisement' on a SCOREBOARD frame. Strip data lost."
    },
    {
        "file": "f160_graphic.jpg",
        "qwen_tag": "GRAPHIC",      # ← Qwen OK
        "scout_read": "digits=True but extractor got None for score/overs",
        "ground_truth_tag": "GRAPHIC",
        "ground_truth_strip": True,
        "desc": "F160: Graphic overlay. Scout found digits but extractor couldn't parse score/overs."
    },
    {
        "file": "f170_ad.jpg",
        "qwen_tag": "AD",
        "scout_read": "STRIP: LSG 0-0 (0.0) — hallucinated zeros",
        "ground_truth_tag": "ADVERTISEMENT",
        "ground_truth_strip": False,
        "desc": "F170: AD frame but Scout hallucinated STRIP: LSG 0-0 (0.0) with zeroed stats."
    },
    {
        "file": "f180_graphic.jpg",
        "qwen_tag": "GRAPHIC",      # ← Qwen OK
        "scout_read": "digits=True",
        "ground_truth_tag": "GRAPHIC",
        "ground_truth_strip": True,
        "desc": "F180: Graphic frame. Scout found digits. Testing DashScope quality."
    },
    {
        "file": "f210_ad.jpg",
        "qwen_tag": "AD",
        "scout_read": "digits=False, said 'no strip, various overlays and logos'",
        "ground_truth_tag": "ADVERTISEMENT",
        "ground_truth_strip": False,
        "desc": "F210: AD frame. Scout correctly identified no strip. Baseline test."
    },
    {
        "file": "f7_scoreboard.jpg",
        "qwen_tag": "SCOREBOARD",
        "scout_read": "digits=True, STRIP: LSG 6-0 (1)",
        "ground_truth_tag": "SCOREBOARD",
        "ground_truth_strip": True,
        "desc": "F7: WORKING frame — Scout got STRIP: LSG 6-0 (1) correctly. Baseline."
    },
    {
        "file": "f100_scoreboard.jpg",
        "qwen_tag": "SCOREBOARD",
        "scout_read": "digits=True",
        "ground_truth_tag": "SCOREBOARD",
        "ground_truth_strip": True,
        "desc": "F100: WORKING frame — Scout read strip correctly. Baseline."
    },
]


def encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


async def call_dashscope(b64: str, prompt: str, max_tokens: int = 300) -> tuple[str, int]:
    """Call DashScope qwen-vl-max. Returns (content, latency_ms)."""
    import httpx
    t0 = time.time()
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{DASHSCOPE_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": DASHSCOPE_VISION_MODEL,
                "temperature": 0,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": prompt},
                ]}],
            },
        )
    ms = int((time.time() - t0) * 1000)
    if r.status_code != 200:
        return f"HTTP {r.status_code}: {r.text[:200]}", ms
    data = r.json()
    return data["choices"][0]["message"]["content"].strip(), ms


async def call_groq_scout(b64: str, prompt: str) -> tuple[str, int]:
    """Call Groq Scout 17B (current reader). Returns (content, latency_ms)."""
    from groq import AsyncGroq
    t0 = time.time()
    client = AsyncGroq(api_key=GROQ_API_KEY, timeout=10)
    try:
        resp = await client.chat.completions.create(
            model=GROQ_PRIMARY_MODEL,
            temperature=0,
            max_tokens=600,
            messages=[{"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": prompt},
            ]}],
        )
        ms = int((time.time() - t0) * 1000)
        return resp.choices[0].message.content.strip(), ms
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        return f"ERROR: {e}", ms
    finally:
        await client.close()


async def call_together_qwen(b64: str, prompt: str) -> tuple[str, int]:
    """Call Together AI Qwen3-VL (current tagger). Returns (content, latency_ms)."""
    import httpx
    t0 = time.time()
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(
            "https://api.together.xyz/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {TOGETHER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": TOGETHER_VISION_MODEL,
                "temperature": 0,
                "max_tokens": 30,
                "messages": [{"role": "user", "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": prompt},
                ]}],
            },
        )
    ms = int((time.time() - t0) * 1000)
    if r.status_code != 200:
        return f"HTTP {r.status_code}: {r.text[:200]}", ms
    data = r.json()
    return data["choices"][0]["message"]["content"].strip(), ms


def has_real_strip(text: str) -> bool:
    """Check if response contains real strip data with non-zero numbers."""
    import re
    if "NO_STRIP" in text.upper() or "ADVERTISEMENT" in text.upper():
        return False
    if "no scoreboard" in text.lower() or "don't see" in text.lower():
        return False
    m = re.search(r"STRIP:.*?(\d+)-(\d+)\s*\((\d+\.?\d*)\)", text)
    if m:
        score, wkts, overs = int(m.group(1)), int(m.group(2)), float(m.group(3))
        if score == 0 and wkts == 0 and overs == 0:
            return False
        return True
    return bool(re.search(r"\d{2,3}", text))


async def test_frame(frame: dict) -> dict:
    path = DEBUG_DIR / frame["file"]
    if not path.exists():
        return {"file": frame["file"], "error": "FILE NOT FOUND"}

    b64 = encode_image(str(path))

    # Run all 4 calls in parallel:
    # DashScope tagger, DashScope reader, Qwen tagger, Scout reader
    ds_tag_task = call_dashscope(b64, TAGGER_PROMPT, max_tokens=30)
    ds_read_task = call_dashscope(b64, READER_PROMPT, max_tokens=600)
    qwen_tag_task = call_together_qwen(b64, TAGGER_PROMPT)
    scout_read_task = call_groq_scout(b64, READER_PROMPT)

    results = await asyncio.gather(
        ds_tag_task, ds_read_task, qwen_tag_task, scout_read_task,
        return_exceptions=True,
    )

    def safe(r):
        if isinstance(r, Exception):
            return (f"ERROR: {r}", 0)
        return r

    ds_tag, ds_tag_ms = safe(results[0])
    ds_read, ds_read_ms = safe(results[1])
    qwen_tag, qwen_tag_ms = safe(results[2])
    scout_read, scout_read_ms = safe(results[3])

    gt_tag = frame["ground_truth_tag"]
    gt_strip = frame["ground_truth_strip"]

    ds_tag_word = ds_tag.split()[0].upper().rstrip(".,") if ds_tag else "?"
    qwen_tag_word = qwen_tag.split()[0].upper().rstrip(".,") if qwen_tag else "?"

    return {
        "file": frame["file"],
        "desc": frame["desc"],
        "ground_truth": {"tag": gt_tag, "strip": gt_strip},
        "dashscope_tag": {"text": ds_tag_word, "ms": ds_tag_ms,
                          "correct": ds_tag_word == gt_tag},
        "qwen_tag":      {"text": qwen_tag_word, "ms": qwen_tag_ms,
                          "correct": qwen_tag_word == gt_tag},
        "dashscope_read": {"text": ds_read[:300], "ms": ds_read_ms,
                           "has_strip": has_real_strip(ds_read),
                           "correct": has_real_strip(ds_read) == gt_strip},
        "scout_read":     {"text": scout_read[:300], "ms": scout_read_ms,
                           "has_strip": has_real_strip(scout_read),
                           "correct": has_real_strip(scout_read) == gt_strip},
    }


async def main():
    print("=" * 78)
    print("DashScope vs Current Pipeline — Failure Frame Comparison")
    print("=" * 78)
    print(f"DashScope model: {DASHSCOPE_VISION_MODEL}")
    print(f"Current tagger:  {TOGETHER_VISION_MODEL}")
    print(f"Current reader:  {GROQ_PRIMARY_MODEL}")
    print(f"Frames to test:  {len(FAILURE_FRAMES)}")
    print()

    ds_tag_wins = 0
    qwen_tag_wins = 0
    ds_read_wins = 0
    scout_read_wins = 0
    total = 0

    for frame in FAILURE_FRAMES:
        print(f"{'─' * 78}")
        print(f"  {frame['desc']}")
        print(f"  Ground truth: {frame['ground_truth_tag']} | strip={frame['ground_truth_strip']}")
        print(f"{'─' * 78}")

        result = await test_frame(frame)
        if "error" in result:
            print(f"  ✗ {result['error']}")
            continue

        total += 1

        # Tagger comparison
        dt = result["dashscope_tag"]
        qt = result["qwen_tag"]
        dt_ok = "✓" if dt["correct"] else "✗"
        qt_ok = "✓" if qt["correct"] else "✗"
        if dt["correct"]: ds_tag_wins += 1
        if qt["correct"]: qwen_tag_wins += 1

        print(f"  TAGGER:  DashScope={dt_ok} {dt['text']:<14s} ({dt['ms']}ms)"
              f"  |  Qwen3-VL={qt_ok} {qt['text']:<14s} ({qt['ms']}ms)")

        # Reader comparison
        dr = result["dashscope_read"]
        sr = result["scout_read"]
        dr_ok = "✓" if dr["correct"] else "✗"
        sr_ok = "✓" if sr["correct"] else "✗"
        if dr["correct"]: ds_read_wins += 1
        if sr["correct"]: scout_read_wins += 1

        print(f"  READER:  DashScope={dr_ok} strip={str(dr['has_strip']):<5s} ({dr['ms']}ms)"
              f"  |  Scout17B={sr_ok} strip={str(sr['has_strip']):<5s} ({sr['ms']}ms)")

        # Show what each reader actually said
        print(f"    DS read:    {dr['text'][:120]}")
        print(f"    Scout read: {sr['text'][:120]}")
        print()

    # Summary
    print(f"\n{'=' * 78}")
    print("SUMMARY")
    print(f"{'=' * 78}")
    print(f"\n{'':20s} {'DashScope':>12s}  {'Current':>12s}  {'Winner':>10s}")
    print(f"{'─' * 20} {'─' * 12} {'─' * 12} {'─' * 10}")
    tag_winner = "DashScope" if ds_tag_wins > qwen_tag_wins else "Qwen3-VL" if qwen_tag_wins > ds_tag_wins else "TIE"
    read_winner = "DashScope" if ds_read_wins > scout_read_wins else "Scout17B" if scout_read_wins > ds_read_wins else "TIE"
    print(f"{'Tagger accuracy':20s} {ds_tag_wins:>5d}/{total:<5d}  {qwen_tag_wins:>5d}/{total:<5d}  {tag_winner:>10s}")
    print(f"{'Reader accuracy':20s} {ds_read_wins:>5d}/{total:<5d}  {scout_read_wins:>5d}/{total:<5d}  {read_winner:>10s}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
