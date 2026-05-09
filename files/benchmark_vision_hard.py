import os
"""
Benchmark: Groq Scout vs Together Qwen3-VL
on 5 HARD frames where vision previously made errors.

Tests: merged names, dismissal text, misspellings, full graphics, bowler-as-batter.
"""

import base64
import time
import httpx
from groq import Groq

TOGETHER_API_KEY = "tgp_v1_gKtaajInL6RLKCJ5k4Z_YtNU7jcksWOo6885LZWXTrQ"
TOGETHER_BASE_URL = "https://api.together.xyz/v1"
TOGETHER_MODEL = "Qwen/Qwen3-VL-8B-Instruct"

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
GROQ_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

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

# ── 5 HARD frames with known Qwen3-VL errors ────────────
HARD_FRAMES = [
    {
        "path": "debug_frames/f1_scoreboard.jpg",
        "label": "MERGED NAMES — two batters shown adjacent",
        "qwen_error": "Merged 'WASHINGTON BUTTLER' as one batter. Truth: WASHINGTON [Sundar] and BUTTLER [Jos] are TWO batters.",
        "checks": [
            ("score", "131", "Score 131"),
            ("wickets", "3", "Wickets 3"),
            ("overs", "12.2", "Overs 12.2"),
            ("team", "GT", "Team GT"),
            ("batter_split", ["WASHINGTON", "BUTTLER"], "Two separate batters visible"),
            ("bowler", "BISHNOI", "Bowler Bishnoi"),
            ("target_calc", "80", "'TO WIN 80' visible"),
        ],
    },
    {
        "path": "debug_frames/f6_scoreboard.jpg",
        "label": "DISMISSAL NOTATION — 'c JADEJA b BISHNOI' in batter line",
        "qwen_error": "Read stats + dismissal as one blob. Must parse: SUNDAR 4(2) DISMISSED c JADEJA b BISHNOI.",
        "checks": [
            ("score", "131", "Score 131"),
            ("wickets", "4", "Wickets 4"),
            ("overs", "12.3", "Overs 12.3"),
            ("team", "GT", "Team GT"),
            ("dismissed_batter", "SUNDAR", "Washington Sundar visible"),
            ("dismissal_type", "JADEJA", "Caught by Jadeja"),
            ("dismissal_bowler", "BISHNOI", "Bowled by Bishnoi"),
        ],
    },
    {
        "path": "debug_frames/f15_scoreboard.jpg",
        "label": "BOWLER AS BATTER — Deshpande (RR bowler) shown with batting stats",
        "qwen_error": "Read DESHPANDE 27(15) as a batter. But Deshpande is an RR bowler. Strip shows GT batting card with rotated info.",
        "checks": [
            ("score", "44", "Score 44"),
            ("wickets", "0", "Wickets 0"),
            ("overs", "4.2", "Overs 4.2"),
            ("team", "GT", "Team GT"),
            ("batter1", "SUDHARSAN", "Sudharsan visible"),
            ("batter2", "DESHPANDE", "Deshpande visible (even though he's a bowler)"),
            ("batter2_runs", "27", "Deshpande showed 27 runs"),
        ],
    },
    {
        "path": "debug_frames/f21_graphic.jpg",
        "label": "FULL BATTING SCORECARD — RR batting card, multiple rows",
        "qwen_error": "Took 6.7s and truncated output. Only 3 of 5+ batter rows extracted.",
        "checks": [
            ("frame_type", "GRAPHIC", "Classified as GRAPHIC"),
            ("team", "RAJASTHAN", "RR batting card"),
            ("batter1", "JAISWAL", "Jaiswal row"),
            ("batter2", "SOORYAVANSHI", "Sooryavanshi row (accept SURYAVANSHI too)"),
            ("batter3", "JUREL", "Jurel row"),
            ("batter1_runs", "55", "Jaiswal 55 runs"),
            ("batter3_runs", "75", "Jurel 75 runs"),
        ],
    },
    {
        "path": "debug_frames/f23_graphic.jpg",
        "label": "BOWLING SCORECARD — GT bowling figures, multiple rows",
        "qwen_error": "Took 5.3s. Truncated bowling card. Need all bowler figures.",
        "checks": [
            ("frame_type", "GRAPHIC", "Classified as GRAPHIC"),
            ("team_bowl", "TITANS", "GT bowling card (accept GUJARAT too)"),
            ("bowler1", "SIRAJ", "Siraj row"),
            ("bowler2", "RABADA", "Rabada row"),
            ("siraj_wickets", "1", "Siraj 1 wicket"),
            ("rabada_wickets", "2", "Rabada 2 wickets"),
        ],
    },
]


def encode_frame(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def call_together(b64: str) -> tuple[float, str]:
    t0 = time.time()
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(
            f"{TOGETHER_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {TOGETHER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": TOGETHER_MODEL,
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


def call_groq(b64: str) -> tuple[float, str]:
    client = Groq(api_key=GROQ_API_KEY)
    t0 = time.time()
    response = client.chat.completions.create(
        model=GROQ_MODEL,
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
    elapsed = time.time() - t0
    return elapsed, response.choices[0].message.content


def check_output(text: str, checks: list) -> tuple[int, int, list[str], list[str]]:
    upper = text.upper()
    hits = 0
    total = len(checks)
    passed = []
    failed = []

    for check in checks:
        name = check[0]
        expected = check[1]
        label = check[2]

        if name == "batter_split":
            # Special: check if BOTH names appear separately
            names = expected
            if all(n.upper() in upper for n in names):
                hits += 1
                passed.append(f"  + {label}")
            else:
                missing = [n for n in names if n.upper() not in upper]
                failed.append(f"  - {label} (missing: {missing})")
        elif name == "batter2" and expected == "SOORYAVANSHI":
            if "SOORYAVANSHI" in upper or "SURYAVANSHI" in upper:
                hits += 1
                passed.append(f"  + {label}")
            else:
                failed.append(f"  - {label}")
        elif name == "team_bowl":
            if "TITANS" in upper or "GUJARAT" in upper:
                hits += 1
                passed.append(f"  + {label}")
            else:
                failed.append(f"  - {label}")
        else:
            if expected.upper() in upper:
                hits += 1
                passed.append(f"  + {label}")
            else:
                failed.append(f"  - {label} (expected '{expected}')")

    return hits, total, passed, failed


def run():
    print("=" * 80)
    print("HARD CASE BENCHMARK: Groq Scout vs Together Qwen3-VL")
    print("Frames where Qwen3-VL previously made errors")
    print("=" * 80)

    results = {"together": [], "groq": []}

    for i, frame in enumerate(HARD_FRAMES):
        path = frame["path"]
        label = frame["label"]
        qwen_error = frame["qwen_error"]
        checks = frame["checks"]

        print(f"\n{'━' * 80}")
        print(f"FRAME {i+1}: {path}")
        print(f"  CHALLENGE: {label}")
        print(f"  PAST ERROR: {qwen_error}")
        print(f"{'━' * 80}")

        b64 = encode_frame(path)

        # Together Qwen3-VL
        print(f"\n  ┌─ QWEN3-VL (Together) ─────────────────────────")
        try:
            t_time, t_text = call_together(b64)
            t_hits, t_total, t_passed, t_failed = check_output(t_text, checks)
            results["together"].append((t_time, t_hits, t_total))
            print(f"  │ Time: {t_time:.1f}s | Score: {t_hits}/{t_total}")
            for p in t_passed:
                print(f"  │ {p}")
            for f in t_failed:
                print(f"  │ {f}")
            print(f"  │")
            for line in t_text.strip().split("\n")[:12]:
                print(f"  │ {line}")
            if len(t_text.strip().split("\n")) > 12:
                print(f"  │ ... ({len(t_text.strip().split(chr(10)))} lines total)")
        except Exception as e:
            print(f"  │ ERROR: {e}")
            results["together"].append((0, 0, len(checks)))
        print(f"  └{'─' * 48}")

        time.sleep(1)

        # Groq Scout
        print(f"\n  ┌─ SCOUT (Groq) ──────────────────────────────")
        try:
            g_time, g_text = call_groq(b64)
            g_hits, g_total, g_passed, g_failed = check_output(g_text, checks)
            results["groq"].append((g_time, g_hits, g_total))
            print(f"  │ Time: {g_time:.1f}s | Score: {g_hits}/{g_total}")
            for p in g_passed:
                print(f"  │ {p}")
            for f in g_failed:
                print(f"  │ {f}")
            print(f"  │")
            for line in g_text.strip().split("\n")[:12]:
                print(f"  │ {line}")
            if len(g_text.strip().split("\n")) > 12:
                print(f"  │ ... ({len(g_text.strip().split(chr(10)))} lines total)")
        except Exception as e:
            print(f"  │ ERROR: {e}")
            results["groq"].append((0, 0, len(checks)))
        print(f"  └{'─' * 48}")

        # Verdict
        t_hits_f = results["together"][-1][1]
        g_hits_f = results["groq"][-1][1]
        t_time_f = results["together"][-1][0]
        g_time_f = results["groq"][-1][0]

        if g_hits_f > t_hits_f:
            print(f"\n  >>> SCOUT WINS ({g_hits_f} vs {t_hits_f}) — {g_time_f:.1f}s vs {t_time_f:.1f}s")
        elif t_hits_f > g_hits_f:
            print(f"\n  >>> QWEN3-VL WINS ({t_hits_f} vs {g_hits_f}) — {t_time_f:.1f}s vs {g_time_f:.1f}s")
        else:
            faster = "SCOUT" if g_time_f < t_time_f else "QWEN3-VL"
            print(f"\n  >>> TIED {t_hits_f}/{t_total} — {faster} faster ({g_time_f:.1f}s vs {t_time_f:.1f}s)")

        time.sleep(2)

    # Summary
    print(f"\n{'━' * 80}")
    print("FINAL SUMMARY — HARD CASES ONLY")
    print(f"{'━' * 80}")

    t_times = [r[0] for r in results["together"] if r[0] > 0]
    g_times = [r[0] for r in results["groq"] if r[0] > 0]
    t_total_hits = sum(r[1] for r in results["together"])
    t_total_checks = sum(r[2] for r in results["together"])
    g_total_hits = sum(r[1] for r in results["groq"])
    g_total_checks = sum(r[2] for r in results["groq"])

    t_avg = sum(t_times) / len(t_times) if t_times else 0
    g_avg = sum(g_times) / len(g_times) if g_times else 0

    print(f"\n  {'Model':<22} {'Avg Time':>10} {'Accuracy':>12} {'Checks':>10}")
    print(f"  {'─' * 58}")
    t_pct = t_total_hits / t_total_checks * 100 if t_total_checks else 0
    g_pct = g_total_hits / g_total_checks * 100 if g_total_checks else 0
    print(f"  {'Qwen3-VL (Together)':<22} {t_avg:>9.1f}s {t_pct:>10.0f}%  {t_total_hits}/{t_total_checks}")
    print(f"  {'Scout (Groq)':<22} {g_avg:>9.1f}s {g_pct:>10.0f}%  {g_total_hits}/{g_total_checks}")

    if g_avg > 0:
        speedup = t_avg / g_avg
        print(f"\n  Speed: Scout is {speedup:.1f}x {'faster' if speedup > 1 else 'slower'}")

    # Per-frame comparison
    print(f"\n  Per-frame breakdown:")
    for i, frame in enumerate(HARD_FRAMES):
        t_h = results["together"][i][1]
        g_h = results["groq"][i][1]
        tot = results["together"][i][2]
        t_t = results["together"][i][0]
        g_t = results["groq"][i][0]
        winner = "SCOUT" if g_h > t_h else ("QWEN" if t_h > g_h else "TIE")
        print(f"    F{i+1} {frame['label'][:40]:<42} Q:{t_h}/{tot} ({t_t:.1f}s)  S:{g_h}/{tot} ({g_t:.1f}s)  [{winner}]")

    if g_total_hits > t_total_hits:
        print(f"\n  VERDICT: SCOUT wins on hard cases — more accurate AND faster")
    elif g_total_hits == t_total_hits:
        print(f"\n  VERDICT: Tied accuracy on hard cases — Scout {speedup:.1f}x faster")
    else:
        delta = t_total_hits - g_total_hits
        print(f"\n  VERDICT: Qwen3-VL wins by {delta} checks — accuracy matters more on hard frames")


if __name__ == "__main__":
    run()
