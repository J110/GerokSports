import os
"""Benchmark extractor across Groq models vs Together baseline.

Uses 10 real vision descriptions from pipeline runs.
Compares accuracy + speed for each model.
"""

import json
import time
import sys

import httpx
from groq import Groq

# ---------------------------------------------------------------------------
# API clients
# ---------------------------------------------------------------------------

GROQ_KEY = os.environ["GROQ_API_KEY"]
TOGETHER_KEY = "tgp_v1_gKtaajInL6RLKCJ5k4Z_YtNU7jcksWOo6885LZWXTrQ"

groq_client = Groq(api_key=GROQ_KEY)
together_client = httpx.Client(
    base_url="https://api.together.xyz/v1",
    headers={"Authorization": f"Bearer {TOGETHER_KEY}",
             "Content-Type": "application/json"},
    timeout=30.0,
)

MODELS = {
    "groq_llama4_scout":  "meta-llama/llama-4-scout-17b-16e-instruct",
    "groq_qwen3_32b":     "qwen/qwen3-32b",
    "groq_llama70b":      "llama-3.3-70b-versatile",
    "groq_llama8b":       "llama-3.1-8b-instant",
    "together_qwen7b":    "Qwen/Qwen2.5-7B-Instruct-Turbo",
}

RATE_LIMIT_SLEEP = {
    "groq_llama4_scout": 3,
    "groq_qwen3_32b": 3,
    "groq_llama70b": 2,
    "groq_llama8b": 10,
    "together_qwen7b": 0.3,
}

# ---------------------------------------------------------------------------
# Extractor prompt (same as production, with team names filled in)
# ---------------------------------------------------------------------------

EXTRACTOR_PROMPT = """\
THIS MATCH IS: {team_a} vs {team_b}
THERE ARE NO OTHER TEAMS.

batting_team_visible MUST be one of:
  '{team_a}' or '{team_b}' or null.
NEVER return any other team name.

Batter and bowler names: report EXACTLY what vision described.
Do NOT invent names. Do NOT guess names.
If you cannot read a name from vision, set to null.

You are a cricket data extractor. You extract EXACTLY what \
vision described. Nothing more. Nothing less.

MOST IMPORTANT - extract chase data if visible:
"28 RUNS FROM 6 BALLS TO WIN" -> runs_needed: 28, balls_remaining: 6
"TARGET 177" -> target: 177

VISION FRAME TYPE: {frame_type}

RAW OBSERVATION:
"{description}"

CRITICAL - REPORT NAMES EXACTLY AS VISION DESCRIBED:
Do NOT resolve, replace, or match names to any squad.
NEVER invent data. If vision didn't mention it, omit it.

FRAME TYPE RULES:
- CLOSEUP or PREMATCH: set has_scorecard_data: false.
- SCOREBOARD: set has_scorecard_data: true. Extract ALL visible data.
- GRAPHIC: set has_scorecard_data: true, ground_truth: true.

batting_team_visible: the team name shown NEXT TO the main score.
Must be '{team_a}' or '{team_b}'. If neither, set to null.

score and wickets are ALWAYS separate fields.
score is ONLY the run total (integer): 58
wickets is ONLY the wicket count (integer): 2
NEVER combine them as "58-2" in the score field.

BOWLING SPEED:
If vision mentions a speed reading (SPEED: 141.6): set bowler speed_kph.
If no speed visible: set speed_kph to null.

EXTRAS:
If vision mentions WIDE/wd: extras.type = "wide", extras.runs = 1.
If vision mentions NO BALL/NB: extras.type = "no_ball", extras.runs = 1.

THIS OVER INDICATOR:
If visible, extract: this_over_broadcast as array.

RETURN JSON:
{{
  "frame_type": "scoreboard|graphic|closeup|prematch|ad",
  "has_scorecard_data": true,
  "batting_team_visible": null,
  "score": null,
  "wickets": null,
  "match_overs": null,
  "run_rate": null,
  "target": null,
  "runs_needed": null,
  "balls_remaining": null,
  "batters": [
    {{"name": "EXACT_NAME", "runs": 0, "balls": 0, "striker": false}}
  ],
  "bowler": {{"name": "EXACT_NAME", "overs": "0", "runs": 0, "wickets": 0, "speed_kph": null}},
  "extras": {{"type": null, "runs": 0}},
  "this_over_broadcast": null,
  "ground_truth": false,
  "graphic_type": null,
  "graphic_team": null,
  "other_match_ticker": null
}}

Omit fields not visible. JSON only. No explanation.\
"""

# ---------------------------------------------------------------------------
# 10 test inputs — real vision descriptions from pipeline
# ---------------------------------------------------------------------------

TEST_CASES = [
    # F1: Standard scoreboard, innings 2 chasing
    {
        "team_a": "Gujarat Titans", "team_b": "Rajasthan Royals",
        "frame_type": "SCOREBOARD",
        "description": (
            "LIVE SCOREBOARD: Top line: GT 56-0 (5.5) "
            "Bottom line: > SUDHARSHAN 33(24) | KUSHAGRA 17(11) | "
            "TARGET 211 | SANDEEP 0-19 (1.5)"
        ),
        "expected": {
            "batting_team_visible": "Gujarat Titans",
            "score": 56, "wickets": 0, "match_overs": "5.5",
            "target": 211,
            "batters": [
                {"name": "SUDHARSHAN", "runs": 33, "balls": 24, "striker": True},
                {"name": "KUSHAGRA", "runs": 17, "balls": 11},
            ],
            "bowler_name": "SANDEEP", "bowler_wickets": 0,
            "bowler_runs": 19, "bowler_overs": "1.5",
            "has_scorecard_data": True,
        },
    },
    # F2: Score unchanged, over ticked
    {
        "team_a": "Gujarat Titans", "team_b": "Rajasthan Royals",
        "frame_type": "SCOREBOARD",
        "description": (
            "LIVE SCOREBOARD: Top line: GT 56-0 (6) "
            "| > SUDHARSHAN 33(24) | KUSHAGRA 17(12) "
            "| AHMEDABAD | REVIEWS REMAINING | TITANS 2 | ROYALS 2"
        ),
        "expected": {
            "batting_team_visible": "Gujarat Titans",
            "score": 56, "wickets": 0, "match_overs": "6",
            "batters": [
                {"name": "SUDHARSHAN", "runs": 33, "balls": 24, "striker": True},
                {"name": "KUSHAGRA", "runs": 17, "balls": 12},
            ],
            "has_scorecard_data": True,
        },
    },
    # F3: New bowler, speed gun visible
    {
        "team_a": "Gujarat Titans", "team_b": "Rajasthan Royals",
        "frame_type": "SCOREBOARD",
        "description": (
            "LIVE SCOREBOARD: Top line: GT 62-0 (6.2) "
            "Bottom line: > SUDHARSHAN 39(26) | KUSHAGRA 17(12) | TARGET 211 "
            "SPEED: 98.8 "
            "The frame shows a bowler running in to deliver."
        ),
        "expected": {
            "score": 62, "wickets": 0, "match_overs": "6.2",
            "target": 211,
            "batters": [
                {"name": "SUDHARSHAN", "runs": 39, "balls": 26, "striker": True},
                {"name": "KUSHAGRA", "runs": 17, "balls": 12},
            ],
            "speed_kph": 98.8,
            "has_scorecard_data": True,
        },
    },
    # F4: Head-to-head panel (trap — extractor should NOT confuse)
    {
        "team_a": "Gujarat Titans", "team_b": "Rajasthan Royals",
        "frame_type": "SCOREBOARD",
        "description": (
            "LIVE SCOREBOARD: Top line: GT 62-0 (6.2) "
            "Bottom line: SUDHARSHAN v JADEJA IN T20s | INNINGS 5 | "
            "RUNS 65 | OUTS 1 | STRIKE RATE 171"
        ),
        "expected": {
            "score": 62, "wickets": 0, "match_overs": "6.2",
            "has_scorecard_data": True,
        },
    },
    # F5: Wide delivery, this-over indicator
    {
        "team_a": "West Indies", "team_b": "England",
        "frame_type": "SCOREBOARD",
        "description": (
            "LIVE SCOREBOARD: WI 89-3 (12.1) "
            "KING 42(30) > POORAN 18(15) | WOAKES 2-22 (3.1) "
            "EXTRA: wide | THIS OVER: 4 . 1 wd"
        ),
        "expected": {
            "batting_team_visible": "West Indies",
            "score": 89, "wickets": 3, "match_overs": "12.1",
            "batters": [
                {"name": "KING", "runs": 42, "balls": 30},
                {"name": "POORAN", "runs": 18, "balls": 15, "striker": True},
            ],
            "bowler_name": "WOAKES", "bowler_overs": "3.1",
            "bowler_runs": 22, "bowler_wickets": 2,
            "extras_type": "wide",
            "this_over": ["4", ".", "1", "wd"],
            "has_scorecard_data": True,
        },
    },
    # F6: Bowling scorecard graphic
    {
        "team_a": "Gujarat Titans", "team_b": "Rajasthan Royals",
        "frame_type": "GRAPHIC",
        "description": (
            "RAJASTHAN ROYALS BOWLING FIGURES: "
            "SANDEEP 2-0-19-0 | DESHPANDE 2-0-22-1 | "
            "ARCHER 2-0-15-0 | JADEJA 1-0-8-0"
        ),
        "expected": {
            "has_scorecard_data": True,
            "ground_truth": True,
            "graphic_type": "bowling_scorecard",
            "graphic_team_contains": "Rajasthan",
            "bowlers_count": 4,
        },
    },
    # F7: Chase info in description
    {
        "team_a": "India", "team_b": "New Zealand",
        "frame_type": "SCOREBOARD",
        "description": (
            "LIVE SCOREBOARD: IND 124-3 (15.2) "
            "KOHLI 58(39) > PANT 22(14) | SOUTHEE 1-28 (3.2) "
            "NEED 53 FROM 28 BALLS | REQUIRED RUN-RATE 11.35"
        ),
        "expected": {
            "batting_team_visible": "India",
            "score": 124, "wickets": 3, "match_overs": "15.2",
            "runs_needed": 53, "balls_remaining": 28,
            "required_rate": 11.35,
            "batters": [
                {"name": "KOHLI", "runs": 58, "balls": 39},
                {"name": "PANT", "runs": 22, "balls": 14, "striker": True},
            ],
            "bowler_name": "SOUTHEE",
            "has_scorecard_data": True,
        },
    },
    # F8: Advertisement
    {
        "team_a": "Gujarat Titans", "team_b": "Rajasthan Royals",
        "frame_type": "ADVERTISEMENT",
        "description": "ADVERTISEMENT",
        "expected": {
            "has_scorecard_data": False,
        },
    },
    # F9: Other match ticker mixed in
    {
        "team_a": "Gujarat Titans", "team_b": "Rajasthan Royals",
        "frame_type": "SCOREBOARD",
        "description": (
            "LIVE SCOREBOARD: GT 98-2 (11.3) "
            "> BUTTLER 45(28) | PHILLIPS 12(8) | BURGER 1-18 (2.3) "
            "OTHER MATCH: CSK 156-4 (18.2)"
        ),
        "expected": {
            "batting_team_visible": "Gujarat Titans",
            "score": 98, "wickets": 2, "match_overs": "11.3",
            "batters": [
                {"name": "BUTTLER", "runs": 45, "balls": 28, "striker": True},
                {"name": "PHILLIPS", "runs": 12, "balls": 8},
            ],
            "bowler_name": "BURGER",
            "has_scorecard_data": True,
            "other_ticker_present": True,
        },
    },
    # F10: Closeup with no scoreboard
    {
        "team_a": "Gujarat Titans", "team_b": "Rajasthan Royals",
        "frame_type": "CLOSEUP",
        "description": (
            "Close-up of Rashid Khan celebrating with teammates "
            "after taking a wicket. One fielder visible at deep "
            "midwicket in the background."
        ),
        "expected": {
            "has_scorecard_data": False,
        },
    },
]


# ---------------------------------------------------------------------------
# Scoring function
# ---------------------------------------------------------------------------

def score_result(parsed: dict, expected: dict) -> tuple[int, int, list[str]]:
    """Score extracted JSON against expected. Returns (points, total, issues)."""
    points = 0
    total = 0
    issues = []

    def check(field, exp_val, label=None):
        nonlocal points, total
        label = label or field
        total += 1
        got = parsed.get(field)
        if isinstance(exp_val, bool):
            if bool(got) == exp_val:
                points += 1
            else:
                issues.append(f"{label}: got={got} exp={exp_val}")
        elif isinstance(exp_val, (int, float)):
            try:
                if abs(float(got or 0) - exp_val) < 0.5:
                    points += 1
                else:
                    issues.append(f"{label}: got={got} exp={exp_val}")
            except (TypeError, ValueError):
                issues.append(f"{label}: got={got} exp={exp_val}")
        elif isinstance(exp_val, str):
            if got and str(got).upper().strip() == exp_val.upper().strip():
                points += 1
            elif got and exp_val.upper() in str(got).upper():
                points += 0.5
                issues.append(f"{label}: partial '{got}'")
            else:
                issues.append(f"{label}: got={got} exp={exp_val}")
        else:
            if got == exp_val:
                points += 1
            else:
                issues.append(f"{label}: got={got} exp={exp_val}")

    # Core fields
    if "score" in expected:
        check("score", expected["score"])
    if "wickets" in expected:
        check("wickets", expected["wickets"])
    if "match_overs" in expected:
        check("match_overs", expected["match_overs"])
    if "has_scorecard_data" in expected:
        check("has_scorecard_data", expected["has_scorecard_data"])
    if "target" in expected:
        check("target", expected["target"])
    if "runs_needed" in expected:
        check("runs_needed", expected["runs_needed"])
    if "balls_remaining" in expected:
        check("balls_remaining", expected["balls_remaining"])
    if "required_rate" in expected:
        check("required_rate", expected["required_rate"])
    if "speed_kph" in expected:
        total += 1
        bowler = parsed.get("bowler") or {}
        got_speed = bowler.get("speed_kph") if isinstance(bowler, dict) else None
        if got_speed and abs(float(got_speed) - expected["speed_kph"]) < 1:
            points += 1
        else:
            issues.append(f"speed: got={got_speed} exp={expected['speed_kph']}")
    if "ground_truth" in expected:
        check("ground_truth", expected["ground_truth"])

    # Team visible
    if "batting_team_visible" in expected:
        total += 1
        got_team = parsed.get("batting_team_visible") or ""
        exp_team = expected["batting_team_visible"]
        if got_team and exp_team:
            if (got_team.upper() == exp_team.upper()
                    or exp_team.upper() in got_team.upper()
                    or got_team.upper() in exp_team.upper()):
                points += 1
            else:
                issues.append(f"team: got='{got_team}' exp='{exp_team}'")
        elif not got_team and not exp_team:
            points += 1
        else:
            issues.append(f"team: got='{got_team}' exp='{exp_team}'")

    # Batters
    if "batters" in expected:
        exp_batters = expected["batters"]
        got_batters = parsed.get("batters") or []
        for i, eb in enumerate(exp_batters):
            total += 1  # name match
            matched = None
            for gb in got_batters:
                gname = (gb.get("name") or "").upper()
                ename = eb["name"].upper()
                if ename in gname or gname in ename:
                    matched = gb
                    break
            if matched:
                points += 1
                if "runs" in eb:
                    total += 1
                    try:
                        if int(matched.get("runs", -1)) == eb["runs"]:
                            points += 1
                        else:
                            issues.append(f"bat[{i}].runs: "
                                          f"got={matched.get('runs')} exp={eb['runs']}")
                    except (TypeError, ValueError):
                        issues.append(f"bat[{i}].runs: "
                                      f"got={matched.get('runs')} exp={eb['runs']}")
                if "balls" in eb:
                    total += 1
                    try:
                        if int(matched.get("balls", -1)) == eb["balls"]:
                            points += 1
                        else:
                            issues.append(f"bat[{i}].balls: "
                                          f"got={matched.get('balls')} exp={eb['balls']}")
                    except (TypeError, ValueError):
                        issues.append(f"bat[{i}].balls: "
                                      f"got={matched.get('balls')} exp={eb['balls']}")
                if "striker" in eb and eb["striker"]:
                    total += 1
                    if matched.get("striker"):
                        points += 1
                    else:
                        issues.append(f"bat[{i}].striker: "
                                      f"got={matched.get('striker')} exp=True")
            else:
                issues.append(f"bat[{i}]: {eb['name']} NOT FOUND")
                if "runs" in eb:
                    total += 1
                if "balls" in eb:
                    total += 1
                if "striker" in eb and eb["striker"]:
                    total += 1

    # Bowler
    if "bowler_name" in expected:
        total += 1
        bowler = parsed.get("bowler") or {}
        got_name = (bowler.get("name") or "").upper() if isinstance(bowler, dict) else ""
        exp_name = expected["bowler_name"].upper()
        if exp_name in got_name or got_name in exp_name:
            points += 1
        else:
            issues.append(f"bowler: got='{got_name}' exp='{exp_name}'")
        if "bowler_overs" in expected:
            total += 1
            got_ov = str(bowler.get("overs", "")) if isinstance(bowler, dict) else ""
            if got_ov == expected["bowler_overs"]:
                points += 1
            else:
                issues.append(f"bowl.overs: got={got_ov} exp={expected['bowler_overs']}")
        if "bowler_runs" in expected:
            total += 1
            try:
                if int(bowler.get("runs", -1)) == expected["bowler_runs"]:
                    points += 1
                else:
                    issues.append(f"bowl.runs: got={bowler.get('runs')} "
                                  f"exp={expected['bowler_runs']}")
            except (TypeError, ValueError):
                issues.append(f"bowl.runs: got={bowler.get('runs')} "
                              f"exp={expected['bowler_runs']}")
        if "bowler_wickets" in expected:
            total += 1
            try:
                if int(bowler.get("wickets", -1)) == expected["bowler_wickets"]:
                    points += 1
                else:
                    issues.append(f"bowl.wkts: got={bowler.get('wickets')} "
                                  f"exp={expected['bowler_wickets']}")
            except (TypeError, ValueError):
                issues.append(f"bowl.wkts: got={bowler.get('wickets')} "
                              f"exp={expected['bowler_wickets']}")

    # Extras
    if "extras_type" in expected:
        total += 1
        extras = parsed.get("extras") or {}
        if isinstance(extras, dict) and extras.get("type") == expected["extras_type"]:
            points += 1
        else:
            issues.append(f"extras: got={extras} exp={expected['extras_type']}")

    # This over
    if "this_over" in expected:
        total += 1
        got_over = parsed.get("this_over_broadcast") or []
        if got_over == expected["this_over"]:
            points += 1
        elif len(got_over) == len(expected["this_over"]):
            points += 0.5
            issues.append(f"this_over: partial match")
        else:
            issues.append(f"this_over: got={got_over} exp={expected['this_over']}")

    # Graphic checks
    if "graphic_type" in expected:
        check("graphic_type", expected["graphic_type"])
    if "graphic_team_contains" in expected:
        total += 1
        gt = parsed.get("graphic_team") or ""
        if expected["graphic_team_contains"].upper() in gt.upper():
            points += 1
        else:
            issues.append(f"graphic_team: got='{gt}' "
                          f"exp contains '{expected['graphic_team_contains']}'")
    if "bowlers_count" in expected:
        total += 1
        got_bowlers = parsed.get("bowlers") or []
        if len(got_bowlers) == expected["bowlers_count"]:
            points += 1
        else:
            issues.append(f"bowlers_count: got={len(got_bowlers)} "
                          f"exp={expected['bowlers_count']}")

    # Other ticker
    if "other_ticker_present" in expected:
        total += 1
        if parsed.get("other_match_ticker"):
            points += 1
        else:
            issues.append("other_ticker: missing")

    return points, total, issues


# ---------------------------------------------------------------------------
# Parse JSON robustly
# ---------------------------------------------------------------------------

def parse_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if "```" in text:
            text = text[:text.index("```")]
        text = text.strip()
    # Strip leading think tags (some models wrap in <think>)
    if "<think>" in text:
        think_end = text.find("</think>")
        if think_end >= 0:
            text = text[think_end + len("</think>"):].strip()
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
    return {}


# ---------------------------------------------------------------------------
# Call Groq
# ---------------------------------------------------------------------------

def call_groq(model_id: str, prompt: str,
              retries: int = 3) -> tuple[float, str]:
    for attempt in range(retries):
        start = time.time()
        try:
            resp = groq_client.chat.completions.create(
                model=model_id,
                temperature=0,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            elapsed = time.time() - start
            return elapsed, resp.choices[0].message.content
        except Exception as e:
            elapsed = time.time() - start
            err = str(e)
            if "429" in err and attempt < retries - 1:
                wait = 10 * (attempt + 1)
                print(f"    Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            return elapsed, f"ERROR: {e}"
    return 0.0, "ERROR: exhausted retries"


# ---------------------------------------------------------------------------
# Call Together (baseline)
# ---------------------------------------------------------------------------

def call_together(model_id: str, prompt: str) -> tuple[float, str]:
    start = time.time()
    try:
        resp = together_client.post(
            "/chat/completions",
            json={
                "model": model_id,
                "temperature": 0,
                "max_tokens": 500,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        elapsed = time.time() - start
        resp.raise_for_status()
        return elapsed, resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return time.time() - start, f"ERROR: {e}"


# ---------------------------------------------------------------------------
# Run benchmark
# ---------------------------------------------------------------------------

def run_benchmark():
    results = {}

    for model_name, model_id in MODELS.items():
        print(f"\n{'=' * 60}")
        print(f"MODEL: {model_name} ({model_id})")
        print(f"{'=' * 60}")

        is_together = model_name.startswith("together_")
        total_points = 0
        total_possible = 0
        total_time = 0
        json_fails = 0
        case_results = []

        for i, case in enumerate(TEST_CASES):
            prompt = EXTRACTOR_PROMPT.format(
                team_a=case["team_a"],
                team_b=case["team_b"],
                frame_type=case["frame_type"],
                description=case["description"],
            )

            if is_together:
                elapsed, raw = call_together(model_id, prompt)
            else:
                elapsed, raw = call_groq(model_id, prompt)

            total_time += elapsed

            if raw.startswith("ERROR:"):
                print(f"  F{i + 1}: API ERROR ({elapsed:.2f}s) -> {raw[:100]}")
                case_results.append({"case": i + 1, "error": raw[:100],
                                     "time": elapsed})
                time.sleep(RATE_LIMIT_SLEEP.get(model_name, 1))
                continue

            parsed = parse_json(raw)
            if not parsed:
                json_fails += 1
                print(f"  F{i + 1}: JSON FAIL ({elapsed:.2f}s) -> "
                      f"{raw[:120]}...")
                case_results.append({"case": i + 1, "json_fail": True,
                                     "time": elapsed})
                time.sleep(RATE_LIMIT_SLEEP.get(model_name, 1))
                continue

            pts, tot, issues = score_result(parsed, case["expected"])
            total_points += pts
            total_possible += tot

            if pts == tot:
                status = "PASS"
            elif pts >= tot * 0.7:
                status = "OKAY"
            else:
                status = "FAIL"

            issue_str = ""
            if issues:
                issue_str = f" | {'; '.join(issues[:3])}"

            print(f"  F{i + 1}: {status} {pts}/{tot} ({elapsed:.2f}s)"
                  f"{issue_str}")

            case_results.append({
                "case": i + 1, "points": pts, "total": tot,
                "time": elapsed, "issues": issues,
            })

            time.sleep(RATE_LIMIT_SLEEP.get(model_name, 1))

        accuracy = (total_points / total_possible * 100
                    if total_possible > 0 else 0)
        avg_time = total_time / len(TEST_CASES)

        print(f"\n  SUMMARY: {total_points}/{total_possible} "
              f"({accuracy:.1f}%) | Avg: {avg_time:.2f}s | "
              f"Total: {total_time:.1f}s | JSON fails: {json_fails}")

        results[model_name] = {
            "model_id": model_id,
            "accuracy": accuracy,
            "total_points": total_points,
            "total_possible": total_possible,
            "avg_time_s": round(avg_time, 3),
            "total_time_s": round(total_time, 1),
            "json_fails": json_fails,
            "cases": case_results,
        }

    # Final comparison table
    print(f"\n\n{'=' * 70}")
    print("FINAL COMPARISON")
    print(f"{'=' * 70}")
    print(f"{'Model':<22} {'Accuracy':>10} {'Avg Time':>10} "
          f"{'Total':>8} {'JSON Fail':>10}")
    print("-" * 70)
    for name, r in sorted(results.items(),
                           key=lambda x: -x[1]["accuracy"]):
        print(f"{name:<22} {r['accuracy']:>9.1f}% {r['avg_time_s']:>9.3f}s "
              f"{r['total_time_s']:>7.1f}s {r['json_fails']:>9}")
    print("-" * 70)

    best = max(results.items(), key=lambda x: x[1]["accuracy"])
    fastest = min(results.items(), key=lambda x: x[1]["avg_time_s"])
    print(f"\nBest accuracy: {best[0]} ({best[1]['accuracy']:.1f}%)")
    print(f"Fastest:       {fastest[0]} ({fastest[1]['avg_time_s']:.3f}s avg)")

    # Value pick: best accuracy/speed ratio
    for name, r in results.items():
        r["value"] = r["accuracy"] / max(r["avg_time_s"], 0.01)
    value_pick = max(results.items(), key=lambda x: x[1]["value"])
    print(f"Best value:    {value_pick[0]} "
          f"({value_pick[1]['accuracy']:.1f}% @ "
          f"{value_pick[1]['avg_time_s']:.3f}s)")

    # Save results
    out_path = "benchmark_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    run_benchmark()
