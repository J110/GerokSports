import os
"""
Benchmark ALL available vision models on Together AI + Groq Scout.
Same 5 hard frames, same prompt, same checks.

Together AI vision models available:
  - Qwen/Qwen3-VL-8B-Instruct         (current — baseline)
  - Qwen/Qwen2-VL-72B-Instruct        (older, much larger)
  - nim/meta/llama-3.2-11b-vision-instruct
  - nim/meta/llama-3.2-90b-vision-instruct

Groq:
  - meta-llama/llama-4-scout-17b-16e-instruct

5 hard frames that previously caused errors.
"""

import base64
import time
import httpx
from groq import Groq

TOGETHER_API_KEY = "tgp_v1_gKtaajInL6RLKCJ5k4Z_YtNU7jcksWOo6885LZWXTrQ"
TOGETHER_BASE_URL = "https://api.together.xyz/v1"
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

MODELS = {
    "Qwen3-VL-8B":   {"provider": "together", "id": "Qwen/Qwen3-VL-8B-Instruct"},
    "Qwen2-VL-72B":  {"provider": "together", "id": "Qwen/Qwen2-VL-72B-Instruct"},
    "Llama3.2-11B":  {"provider": "together", "id": "nim/meta/llama-3.2-11b-vision-instruct"},
    "Llama3.2-90B":  {"provider": "together", "id": "nim/meta/llama-3.2-90b-vision-instruct"},
    "Scout-17B":     {"provider": "groq",     "id": "meta-llama/llama-4-scout-17b-16e-instruct"},
}

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
THIS OVER: If ball-by-ball results shown (e.g. '4 . 1 6 wd 4'), report exactly.

FULL SCORECARD GRAPHIC: Every batter/bowler row with name, runs, balls, etc.

Report every number exactly. Describe what you SEE — don't interpret.

HINT FROM SCORER:
None — benchmark run.\
"""

HARD_FRAMES = [
    {
        "path": "debug_frames/f1_scoreboard.jpg",
        "label": "MERGED NAMES",
        "checks": {
            "score_131": "131", "wickets_3": "3", "overs_12.2": "12.2",
            "team_GT": "GT", "batter_WASHINGTON": "WASHINGTON",
            "batter_BUTTLER": "BUTTLER", "bowler_BISHNOI": "BISHNOI",
        },
    },
    {
        "path": "debug_frames/f6_scoreboard.jpg",
        "label": "DISMISSAL TEXT",
        "checks": {
            "score_131": "131", "wickets_4": "4", "overs_12.3": "12.3",
            "team_GT": "GT", "batter_SUNDAR": "SUNDAR",
            "dismissal_JADEJA": "JADEJA", "bowler_BISHNOI": "BISHNOI",
        },
    },
    {
        "path": "debug_frames/f15_scoreboard.jpg",
        "label": "BOTTOM LINE",
        "checks": {
            "score_44": "44", "wickets_0": "0", "overs_4.2": "4.2",
            "team_GT": "GT", "batter_SUDHARSAN": "SUDHARSAN",
            "batter_DESHPANDE": "DESHPANDE", "runs_27": "27",
        },
    },
    {
        "path": "debug_frames/f21_graphic.jpg",
        "label": "BAT SCORECARD",
        "checks": {
            "type_GRAPHIC": "GRAPHIC", "team_RR": "RAJASTHAN",
            "JAISWAL": "JAISWAL", "SOORYAVANSHI": "SOORYAVANSHI|SURYAVANSHI",
            "JUREL": "JUREL", "jaiswal_55": "55", "jurel_75": "75",
        },
    },
    {
        "path": "debug_frames/f23_graphic.jpg",
        "label": "BOWL SCORECARD",
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
            f"{TOGETHER_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {TOGETHER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_id,
                "temperature": 0,
                "max_tokens": 500,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        {"type": "text", "text": VISION_PROMPT},
                    ],
                }],
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    return time.time() - t0, content


def call_groq(model_id: str, b64: str) -> tuple[float, str]:
    client = Groq(api_key=GROQ_API_KEY)
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model_id,
        temperature=0,
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": VISION_PROMPT},
            ],
        }],
    )
    return time.time() - t0, resp.choices[0].message.content


def check_output(text: str, checks: dict) -> tuple[int, int, list[str]]:
    upper = text.upper()
    hits = 0
    total = len(checks)
    misses = []
    for name, expected in checks.items():
        alternatives = expected.upper().split("|")
        if any(alt in upper for alt in alternatives):
            hits += 1
        else:
            misses.append(name)
    return hits, total, misses


def run():
    print("=" * 90)
    print("VISION MODEL BENCHMARK — 5 hard frames × 5 models")
    print("=" * 90)

    # Pre-encode all frames
    encoded = {}
    for frame in HARD_FRAMES:
        encoded[frame["path"]] = encode_frame(frame["path"])
    print(f"Encoded {len(encoded)} frames\n")

    # Results: model_name -> [(time, hits, total, misses, first_line)]
    all_results: dict[str, list] = {}

    for model_name, model_cfg in MODELS.items():
        provider = model_cfg["provider"]
        model_id = model_cfg["id"]
        all_results[model_name] = []

        print(f"\n{'━' * 90}")
        print(f"  MODEL: {model_name} ({model_id}) via {provider}")
        print(f"{'━' * 90}")

        for fi, frame in enumerate(HARD_FRAMES):
            b64 = encoded[frame["path"]]
            label = frame["label"]

            try:
                if provider == "together":
                    elapsed, text = call_together(model_id, b64)
                else:
                    elapsed, text = call_groq(model_id, b64)

                hits, total, misses = check_output(text, frame["checks"])
                first_line = text.strip().split("\n")[0][:90]
                all_results[model_name].append((elapsed, hits, total, misses, first_line))

                status = "✓" if hits == total else f"✗ miss:{','.join(misses)}"
                print(f"    F{fi+1} {label:<16} {elapsed:>5.1f}s  {hits}/{total}  {status}")
                print(f"       {first_line}")

            except Exception as e:
                err_msg = str(e)[:120]
                all_results[model_name].append((0, 0, len(frame["checks"]), list(frame["checks"].keys()), f"ERROR: {err_msg}"))
                print(f"    F{fi+1} {label:<16}  ERROR  {err_msg}")

            time.sleep(1.5)

    # ── Summary table ─────────────────────────────
    print(f"\n\n{'=' * 90}")
    print("SUMMARY TABLE")
    print(f"{'=' * 90}")

    header = f"  {'Model':<18} {'Avg Time':>9} {'Accuracy':>10} {'F1':>5} {'F2':>5} {'F3':>5} {'F4':>5} {'F5':>5}"
    print(header)
    print(f"  {'─' * 78}")

    model_summaries = []
    for model_name, results in all_results.items():
        times = [r[0] for r in results if r[0] > 0]
        avg_time = sum(times) / len(times) if times else 0
        total_hits = sum(r[1] for r in results)
        total_checks = sum(r[2] for r in results)
        pct = total_hits / total_checks * 100 if total_checks else 0

        per_frame = "".join(f" {r[1]:>2}/{r[2]}" for r in results)
        print(f"  {model_name:<18} {avg_time:>8.1f}s {pct:>8.0f}%  {per_frame}")
        model_summaries.append((model_name, avg_time, total_hits, total_checks, pct))

    # ── Per-frame winners ─────────────────────────
    print(f"\n  PER-FRAME WINNERS:")
    for fi, frame in enumerate(HARD_FRAMES):
        best_score = -1
        best_time = 999
        best_model = ""
        for model_name, results in all_results.items():
            r = results[fi]
            if r[1] > best_score or (r[1] == best_score and r[0] < best_time and r[0] > 0):
                best_score = r[1]
                best_time = r[0]
                best_model = model_name
        print(f"    F{fi+1} {frame['label']:<16} → {best_model} ({best_score}/{results[fi][2]}, {best_time:.1f}s)")

    # ── Overall verdict ───────────────────────────
    print(f"\n  OVERALL RANKING (by accuracy, speed as tiebreaker):")
    ranked = sorted(model_summaries, key=lambda x: (-x[4], x[1]))
    for i, (name, avg_t, hits, total, pct) in enumerate(ranked):
        marker = " ◀ BEST" if i == 0 else ""
        print(f"    {i+1}. {name:<18} {pct:.0f}% ({hits}/{total})  avg {avg_t:.1f}s{marker}")


if __name__ == "__main__":
    run()
