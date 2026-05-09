import os
"""
DEFINITIVE VISION MODEL BENCHMARK
5 hard broadcast frames × 6 models across 3 providers.

Together AI:  Qwen3-VL-8B (current baseline)
Groq:         Llama-4 Scout 17B
fal.ai:       Gemini 2.5 Flash, Gemini 2.5 Pro, GPT-4.1, Llama-4 Maverick
"""

import base64
import time
import json
import httpx
from groq import Groq

TOGETHER_KEY = "tgp_v1_gKtaajInL6RLKCJ5k4Z_YtNU7jcksWOo6885LZWXTrQ"
GROQ_KEY = os.environ["GROQ_API_KEY"]
FAL_KEY = "1046419b-959d-47ae-905f-90db6faddf8f:87df92e3f719d7f06e97df4dc851dc77"

MODELS = [
    ("Qwen3-VL-8B",     "together", "Qwen/Qwen3-VL-8B-Instruct"),
    ("Scout-17B",        "groq",    "meta-llama/llama-4-scout-17b-16e-instruct"),
    ("Gemini-2.5-Flash", "fal",     "google/gemini-2.5-flash"),
    ("Gemini-2.5-Pro",   "fal",     "google/gemini-2.5-pro"),
    ("GPT-4.1",          "fal",     "openai/gpt-4.1"),
    ("Maverick-128E",    "fal",     "meta-llama/llama-4-maverick"),
]

VISION_PROMPT = """\
You are watching a live cricket broadcast stream.

FIRST WORD of your response MUST be exactly one of:
  SCOREBOARD — bottom scoreboard strip is visible with score/overs/batter info
  GRAPHIC — full-screen overlay (batting scorecard, bowling scorecard, lineup)
  CLOSEUP — player faces, jerseys, dugout, celebrations, no scoreboard visible
  ADVERTISEMENT — ad content, sponsor logos, non-cricket commercial
  PREMATCH — countdown, toss, anthem, walkout, coin flip, ceremony

If ADVERTISEMENT: respond with ONLY the word ADVERTISEMENT.
If CLOSEUP or PREMATCH: briefly note what you see (1-2 sentences max).

If SCOREBOARD or GRAPHIC: describe everything precisely:

LIVE SCOREBOARD (persistent strip at bottom of screen):
  Top line: team abbreviation, score-wickets, overs in parentheses
  Bottom line: batter names with runs(balls), bowler name with figures W-R(overs)
  * or > prefix = striker.

BOWLING SPEED: If a speed number is visible (80-160 range), report: SPEED: 141.6
EXTRAS: If umpire signal or wd/nb in over indicator, report: EXTRA: wide/no_ball
THIS OVER: If ball-by-ball results shown, report exactly.
FULL SCORECARD GRAPHIC: Every batter/bowler row with name, runs, balls, etc.

Report every number exactly. Describe what you SEE — don't interpret.\
"""

HARD_FRAMES = [
    {
        "path": "debug_frames/f1_scoreboard.jpg",
        "label": "MERGED NAMES",
        "detail": "Two batters shown adjacent — must not merge into one",
        "checks": {
            "score_131": "131", "wickets_3": "3", "overs_12.2": "12.2",
            "team_GT": "GT", "batter_WASHINGTON": "WASHINGTON",
            "batter_BUTTLER": "BUTTLER", "bowler_BISHNOI": "BISHNOI",
        },
    },
    {
        "path": "debug_frames/f6_scoreboard.jpg",
        "label": "DISMISSAL TEXT",
        "detail": "'c JADEJA b BISHNOI' mixed with batter stats",
        "checks": {
            "score_131": "131", "wickets_4": "4", "overs_12.3": "12.3",
            "team_GT": "GT", "batter_SUNDAR": "SUNDAR",
            "dismissal_JADEJA": "JADEJA", "bowler_BISHNOI": "BISHNOI",
        },
    },
    {
        "path": "debug_frames/f15_scoreboard.jpg",
        "label": "BOTTOM LINE",
        "detail": "Batter names + stats in small bottom strip",
        "checks": {
            "score_44": "44", "wickets_0": "0", "overs_4.2": "4.2",
            "team_GT": "GT", "batter_SUDHARSAN": "SUDHARSAN",
            "batter_DESHPANDE": "DESHPANDE", "runs_27": "27",
        },
    },
    {
        "path": "debug_frames/f21_graphic.jpg",
        "label": "BAT SCORECARD",
        "detail": "Full RR batting card — multiple rows, dismissal details",
        "checks": {
            "type_GRAPHIC": "GRAPHIC", "team_RR": "RAJASTHAN",
            "JAISWAL": "JAISWAL", "SOORYAVANSHI": "SOORYAVANSHI|SURYAVANSHI",
            "JUREL": "JUREL", "jaiswal_55": "55", "jurel_75": "75",
        },
    },
    {
        "path": "debug_frames/f23_graphic.jpg",
        "label": "BOWL SCORECARD",
        "detail": "GT bowling figures — 5 bowlers with overs/runs/wickets",
        "checks": {
            "type_GRAPHIC": "GRAPHIC", "team_GT": "TITANS|GUJARAT",
            "SIRAJ": "SIRAJ", "RABADA": "RABADA",
            "siraj_w1": "1", "rabada_w2": "2",
        },
    },
]


def encode_frame(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def call_together(model_id: str, b64: str) -> tuple[float, str]:
    t0 = time.time()
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"https://api.together.xyz/v1/chat/completions",
            headers={"Authorization": f"Bearer {TOGETHER_KEY}", "Content-Type": "application/json"},
            json={
                "model": model_id, "temperature": 0, "max_tokens": 500,
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": VISION_PROMPT},
                ]}],
            },
        )
        resp.raise_for_status()
        return time.time() - t0, resp.json()["choices"][0]["message"]["content"]


def call_groq(model_id: str, b64: str) -> tuple[float, str]:
    client = Groq(api_key=GROQ_KEY)
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model_id, temperature=0, max_tokens=500,
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": VISION_PROMPT},
        ]}],
    )
    return time.time() - t0, resp.choices[0].message.content


def call_fal(model_id: str, b64: str) -> tuple[float, str]:
    t0 = time.time()
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            "https://fal.run/fal-ai/any-llm/vision",
            headers={"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"},
            json={
                "model": model_id,
                "prompt": VISION_PROMPT,
                "image_urls": [f"data:image/jpeg;base64,{b64}"],
                "max_tokens": 500,
                "temperature": 0,
            },
        )
        resp.raise_for_status()
        return time.time() - t0, resp.json().get("output", "")


def call_model(provider: str, model_id: str, b64: str) -> tuple[float, str]:
    if provider == "together":
        return call_together(model_id, b64)
    elif provider == "groq":
        return call_groq(model_id, b64)
    elif provider == "fal":
        return call_fal(model_id, b64)
    raise ValueError(f"Unknown provider: {provider}")


def check_output(text: str, checks: dict) -> tuple[int, int, list[str]]:
    upper = text.upper()
    hits, total, misses = 0, len(checks), []
    for name, expected in checks.items():
        alts = expected.upper().split("|")
        if any(a in upper for a in alts):
            hits += 1
        else:
            misses.append(name)
    return hits, total, misses


def run():
    print("=" * 90)
    print("DEFINITIVE VISION BENCHMARK — 5 hard frames × 6 models × 3 providers")
    print("=" * 90)

    encoded = {f["path"]: encode_frame(f["path"]) for f in HARD_FRAMES}
    print(f"Encoded {len(encoded)} frames\n")

    # results[model_name] = [(time, hits, total, misses, first_line), ...]
    results: dict[str, list] = {}

    for model_name, provider, model_id in MODELS:
        results[model_name] = []
        print(f"\n{'━' * 90}")
        print(f"  {model_name} ({model_id}) via {provider}")
        print(f"{'━' * 90}")

        for fi, frame in enumerate(HARD_FRAMES):
            b64 = encoded[frame["path"]]
            try:
                elapsed, text = call_model(provider, model_id, b64)
                hits, total, misses = check_output(text, frame["checks"])
                first_line = text.strip().split("\n")[0][:85]
                results[model_name].append((elapsed, hits, total, misses, first_line))

                status = "✓" if hits == total else f"✗ miss:{','.join(misses)}"
                print(f"    F{fi+1} {frame['label']:<16} {elapsed:>5.1f}s  {hits}/{total}  {status}")

            except Exception as e:
                err = str(e)[:100]
                results[model_name].append((0, 0, len(frame["checks"]), list(frame["checks"].keys()), f"ERR:{err}"))
                print(f"    F{fi+1} {frame['label']:<16}  ERR   {err}")

            time.sleep(1)

    # ── Summary ───────────────────────────────────
    print(f"\n\n{'=' * 90}")
    print("RESULTS TABLE")
    print(f"{'=' * 90}")

    header = f"  {'Model':<20} {'Provider':<10} {'Avg(s)':>7} {'Acc%':>6} {'F1':>4} {'F2':>4} {'F3':>4} {'F4':>4} {'F5':>4} {'Total':>7}"
    print(header)
    print(f"  {'─' * 80}")

    summaries = []
    for model_name, provider, model_id in MODELS:
        res = results[model_name]
        times = [r[0] for r in res if r[0] > 0]
        avg_t = sum(times) / len(times) if times else 0
        total_hits = sum(r[1] for r in res)
        total_checks = sum(r[2] for r in res)
        pct = total_hits / total_checks * 100 if total_checks else 0

        per_frame = " ".join(f"{r[1]:>2}/{r[2]}" for r in res)
        print(f"  {model_name:<20} {provider:<10} {avg_t:>6.1f}s {pct:>5.0f}%  {per_frame}  {total_hits}/{total_checks}")
        summaries.append((model_name, provider, avg_t, total_hits, total_checks, pct))

    # ── Ranking ───────────────────────────────────
    print(f"\n  RANKING (accuracy first, speed as tiebreaker):")
    ranked = sorted(summaries, key=lambda x: (-x[5], x[2]))
    for i, (name, prov, avg_t, hits, total, pct) in enumerate(ranked):
        tag = " ◀ BEST" if i == 0 else ""
        print(f"    {i+1}. {name:<20} {pct:>5.0f}% ({hits}/{total})  {avg_t:.1f}s  [{prov}]{tag}")

    # ── Cost estimate per match ───────────────────
    print(f"\n  COST ESTIMATE (1700 frames/match):")
    cost_map = {
        "Qwen3-VL-8B": 0.00024,
        "Scout-17B": 0.00010,
        "Gemini-2.5-Flash": 0.00015,
        "Gemini-2.5-Pro": 0.00120,
        "GPT-4.1": 0.00100,
        "Maverick-128E": 0.00020,
    }
    for name, cost in cost_map.items():
        match_cost = cost * 1700
        print(f"    {name:<20} ~${cost:.5f}/frame  = ${match_cost:.2f}/match")

    # ── Per-frame detail ──────────────────────────
    print(f"\n  PER-FRAME DETAIL:")
    for fi, frame in enumerate(HARD_FRAMES):
        print(f"\n    F{fi+1}: {frame['label']} — {frame['detail']}")
        for model_name, _, _ in MODELS:
            r = results[model_name][fi]
            status = "✓" if not r[3] else f"miss: {', '.join(r[3])}"
            fl = r[4][:70] if r[4] else ""
            print(f"      {model_name:<20} {r[0]:>5.1f}s {r[1]}/{r[2]}  {status}")
            print(f"        → {fl}")


if __name__ == "__main__":
    run()
