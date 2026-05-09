"""Benchmark: Together Qwen3-VL-8B vs Groq Scout 17B for strip vision."""
import asyncio
import base64
import json
import os
import re
import time
from pathlib import Path

import httpx
from groq import AsyncGroq

TOGETHER_API_KEY = "tgp_v1_gKtaajInL6RLKCJ5k4Z_YtNU7jcksWOo6885LZWXTrQ"
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

TOGETHER_MODEL = "Qwen/Qwen3-VL-8B-Instruct"
GROQ_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

# RCB + CSK player names for scoring
PLAYER_NAMES = [
    "SALT", "KOHLI", "PADIKKAL", "PATIDAR", "JITESH", "DAVID",
    "SHEPHERD", "KRUNAL", "BHUVNESHWAR", "ABHINANDAN", "DUFFY",
    "BETHELL", "HAZLEWOOD", "VENKATESH", "SUYASH",
    "SAMSON", "RUTURAJ", "GAIKWAD", "MHATRE", "SARFARAZ",
    "DUBE", "PRASHANT", "OVERTON", "NOOR", "KAMBOJ",
    "HENRY", "KHALEEL",
    "RCB", "CSK", "BENGALURU", "CHENNAI",
]

STRIP_PROMPT = """\
You are watching a live cricket broadcast stream.

FIRST WORD of your response MUST be exactly one of:
  SCOREBOARD — bottom scoreboard strip is visible with score/overs/batter info
  GRAPHIC — full-screen overlay (batting scorecard, bowling scorecard, lineup)
  CLOSEUP — player faces, jerseys, dugout, celebrations, no scoreboard visible
  ADVERTISEMENT — ad content, sponsor logos, non-cricket commercial
  PREMATCH — countdown, toss, anthem, walkout, coin flip, ceremony

If ADVERTISEMENT: respond with ONLY the word ADVERTISEMENT. \
Do not describe the ad. Stop immediately.

If CLOSEUP or PREMATCH: briefly note what you see (1-2 sentences max). \
Do NOT report jersey numbers as scores. Player names on jerseys \
are NOT batters at the crease. \
IMPORTANT: even on closeups, look for fielders visible in the \
background. Mention any you can see (e.g. "fielder at deep cover \
in background").

If SCOREBOARD or GRAPHIC: describe everything precisely:

CRITICAL — TWO SOURCES OF DATA ON SCREEN:

1. LIVE SCOREBOARD STRIP (bottom bar, always present during play):
  Small text. Shows: team score-wickets (overs), two batters \
with MATCH runs(balls), current bowler with MATCH figures W-R(overs).
  Top line: team abbreviation, score-wickets, overs in parentheses
  Bottom line: batter names with runs(balls), \
bowler name with figures W-R(overs), rotating info section
  * or > prefix = striker.
  These are MATCH stats. Report them.

2. INFO/CAREER PANEL (rotating overlay, appears above or beside strip):
  Larger text. Appears temporarily. Contains words like: \
IPL, CAREER, T20, SINCE, TOURNAMENT, ALL TIME, RECORD, \
HEAD TO HEAD, v SPINNERS, v PACERS, IN T20, SEASON, FOURS, SIXES.
  These are NOT match stats.
  Label them: INFO_PANEL: [whatever it says]
  Do NOT mix info panel numbers with strip data.
  If panel shows KLAASEN 60(52) but strip shows KLAASEN 9(14), \
report ONLY the strip value: KLAASEN 9(14).
  If bowler shows 11-0-43-0 but match is at 10 overs, that is \
a career/tournament stat — label it as INFO_PANEL.

BOWLING SPEED: After each delivery, a speed reading appears \
briefly on screen (e.g. '141.6 KPH' or 'SPEED 132.7 km/h'). \
If you see a speed number, report it: SPEED: 141.6
The speed is a 3-digit number (80-160 range) followed by \
kph, km/h, or sometimes just the number alone. \
It appears for only 2-3 seconds — capture it if visible.

EXTRAS: The umpire signals extras after a delivery:
  - Arms stretched sideways = WIDE
  - One arm extended forward = NO BALL
  - Leg tapped = LEG BYE
  - Hand waved across = BYE
If you see an umpire signal or the scoreboard shows \
'wd' or 'nb' or 'W' or 'NB' in the this-over indicator, \
report it: EXTRA: wide (or no_ball, leg_bye, bye)

THIS OVER: If a row of ball-by-ball results is shown for the \
current over (e.g. '4 . 1 6 wd 4'), report it exactly.

FULL SCORECARD GRAPHIC (overlay filling the screen):
  Every batter/bowler row. Note which TEAM the graphic belongs to.
  Extract every row: name, dismissal, runs, balls, 4s, 6s, SR.

Report every number exactly. Describe what you SEE — don't interpret.

AFTER reading the scoreboard strip, ALSO describe what is \
happening in the REST of the frame (the other 85%):
- Is a delivery being bowled? Describe the shot played.
- Is the ball traveling to a fielder or boundary?
- Is a batter running between wickets?
- Is this a replay of a recent delivery?
- Is a bowler walking back to their mark?
- Is a fielder celebrating or diving?
The scoreboard is 15% of the frame. Describe BOTH.

HINT FROM SCORER:
None — benchmark test, no hints.\
"""


async def test_together(frame_path: str) -> tuple[float, str, str]:
    """Returns (latency_seconds, raw_text, error_or_empty)."""
    with open(frame_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    payload = {
        "model": TOGETHER_MODEL,
        "temperature": 0,
        "max_tokens": 400,
        "messages": [{"role": "user", "content": [
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": STRIP_PROMPT},
        ]}],
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        start = time.time()
        try:
            resp = await client.post(
                "https://api.together.xyz/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {TOGETHER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            elapsed = time.time() - start
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            return elapsed, text, ""
        except Exception as e:
            return time.time() - start, "", str(e)


async def test_groq(frame_path: str) -> tuple[float, str, str]:
    """Returns (latency_seconds, raw_text, error_or_empty)."""
    with open(frame_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    client = AsyncGroq(api_key=GROQ_API_KEY, timeout=15.0)
    start = time.time()
    try:
        resp = await client.chat.completions.create(
            model=GROQ_MODEL,
            temperature=0,
            max_tokens=400,
            messages=[{"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": STRIP_PROMPT},
            ]}],
        )
        elapsed = time.time() - start
        text = resp.choices[0].message.content
        return elapsed, text, ""
    except Exception as e:
        return time.time() - start, "", str(e)
    finally:
        await client.close()


def score_vision(text: str) -> tuple[int, list[str]]:
    """Score out of 7: frame_type, score, wickets, overs, batter1, batter2, bowler.
    Returns (score, list_of_what_was_found)."""
    points = 0
    found = []
    upper = text.upper()

    # 1. Frame type identified correctly
    first_word = upper.split()[0] if upper.strip() else ""
    if first_word in ("SCOREBOARD", "GRAPHIC", "CLOSEUP",
                      "ADVERTISEMENT", "PREMATCH"):
        points += 1
        found.append(f"type:{first_word}")
    elif any(x in upper for x in ["SCOREBOARD", "STRIP", "LIVE"]):
        points += 1
        found.append("type:~SCOREBOARD")

    # 2. Score (2-3 digit number with separator and wickets)
    score_match = re.search(r'(\d{2,3})\s*[-/]\s*(\d{1,2})', text)
    if score_match:
        points += 1
        found.append(f"score:{score_match.group(0)}")

    # 3. Overs (X.Y pattern)
    overs_match = re.search(r'(\d{1,2}\.\d)', text)
    if overs_match:
        points += 1
        found.append(f"overs:{overs_match.group(1)}")

    # 4-5. Batter names (up to 2 points)
    names_found = []
    for name in PLAYER_NAMES:
        if name in upper and name not in ("RCB", "CSK", "BENGALURU", "CHENNAI"):
            names_found.append(name)
    batter_points = min(len(set(names_found)), 2)
    points += batter_points
    if names_found:
        found.append(f"players:{','.join(list(set(names_found))[:4])}")

    # 6. Bowler (3rd distinct player name = likely bowler)
    if len(set(names_found)) >= 3:
        points += 1
        found.append("bowler:yes")

    # 7. Team name
    if any(t in upper for t in ["RCB", "CSK", "BENGALURU", "CHENNAI",
                                 "CHALLENGERS", "SUPER KINGS"]):
        points += 1
        found.append("team:yes")

    return points, found


async def benchmark():
    frame_dir = Path("benchmark_frames")
    frames = sorted(frame_dir.glob("f*.jpg"),
                    key=lambda p: int(re.search(r'f(\d+)', p.stem).group(1)))

    if not frames:
        print("No frames found in benchmark_frames/. Run capture first.")
        return

    print(f"Found {len(frames)} frames\n")
    print(f"{'Frame':<10} {'Together':>10} {'Groq':>10}  "
          f"{'T_Pts':>5} {'G_Pts':>5}  Winner")
    print("-" * 75)

    t_total_time = 0.0
    g_total_time = 0.0
    t_total_score = 0
    g_total_score = 0
    results = []

    for fp in frames:
        t_time, t_text, t_err = await test_together(str(fp))
        g_time, g_text, g_err = await test_groq(str(fp))

        t_score, t_found = score_vision(t_text) if not t_err else (0, ["ERROR"])
        g_score, g_found = score_vision(g_text) if not g_err else (0, ["ERROR"])

        t_total_time += t_time
        g_total_time += g_time
        t_total_score += t_score
        g_total_score += g_score

        if t_err:
            winner = "Groq (Together err)"
        elif g_err:
            winner = "Together (Groq err)"
        elif t_score > g_score:
            winner = "Together"
        elif g_score > t_score:
            winner = "Groq"
        else:
            winner = f"Tie → {'Together' if t_time < g_time else 'Groq'} faster"

        name = fp.name
        print(f"{name:<10} {t_time:>9.1f}s {g_time:>9.1f}s  "
              f"{t_score:>5}/7 {g_score:>5}/7  {winner}")

        results.append({
            "frame": name,
            "together": {
                "latency": round(t_time, 2),
                "score": t_score,
                "found": t_found,
                "text": t_text[:300] if not t_err else f"ERROR: {t_err}",
                "full_text": t_text if not t_err else f"ERROR: {t_err}",
            },
            "groq": {
                "latency": round(g_time, 2),
                "score": g_score,
                "found": g_found,
                "text": g_text[:300] if not g_err else f"ERROR: {g_err}",
                "full_text": g_text if not g_err else f"ERROR: {g_err}",
            },
            "winner": winner,
        })

    n = len(frames)
    max_score = n * 7
    print("-" * 75)
    print(f"{'TOTAL':<10} {t_total_time:>9.1f}s {g_total_time:>9.1f}s  "
          f"{t_total_score:>5}/{max_score} {g_total_score:>5}/{max_score}")
    print(f"\nAvg latency:  Together {t_total_time/n:.2f}s  |  "
          f"Groq {g_total_time/n:.2f}s  |  "
          f"Groq is {t_total_time/max(g_total_time,0.01):.1f}x faster")
    print(f"Accuracy:     Together {t_total_score}/{max_score} "
          f"({t_total_score/max_score*100:.0f}%)  |  "
          f"Groq {g_total_score}/{max_score} "
          f"({g_total_score/max_score*100:.0f}%)")

    print(f"\nCost per match (~1700 frames):")
    print(f"  Together: ~$0.41  (paid)")
    print(f"  Groq:     ~$0.09  (paid tier) / FREE (within free tier RPD)")

    # Save detailed results
    out_path = f"benchmark_results_{int(time.time())}.json"
    with open(out_path, "w") as f:
        json.dump({
            "summary": {
                "frames": n,
                "together_avg_latency": round(t_total_time / n, 2),
                "groq_avg_latency": round(g_total_time / n, 2),
                "together_accuracy": f"{t_total_score}/{max_score}",
                "groq_accuracy": f"{g_total_score}/{max_score}",
                "speed_ratio": round(t_total_time / max(g_total_time, 0.01), 1),
            },
            "frames": results,
        }, f, indent=2)
    print(f"\nDetailed results saved to {out_path}")

    # Print side-by-side comparison for each frame
    print("\n" + "=" * 80)
    print("DETAILED COMPARISON")
    print("=" * 80)
    for r in results:
        print(f"\n--- {r['frame']} ---")
        print(f"  Together ({r['together']['latency']}s, "
              f"{r['together']['score']}/7): "
              f"{r['together']['found']}")
        print(f"  Groq     ({r['groq']['latency']}s, "
              f"{r['groq']['score']}/7): "
              f"{r['groq']['found']}")
        # Show first 200 chars of each response
        print(f"  T: {r['together']['text'][:200]}")
        print(f"  G: {r['groq']['text'][:200]}")


if __name__ == "__main__":
    asyncio.run(benchmark())
