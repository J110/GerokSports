"""
A/B Accuracy Test: Old models vs New models
Same 5 vision descriptions → compare extractor + scorer output.

OLD: Extractor=Llama-3.3-70B, Scorer=Qwen2.5-7B (Together)
NEW: Extractor=Scout-17B,      Scorer=Scout-17B (Groq)

Ground truth from the last known-good pipeline run.
"""

import asyncio
import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

import httpx
from groq import AsyncGroq
from eyes.config import (
    GROQ_API_KEY, TOGETHER_API_KEY, TOGETHER_BASE_URL,
)
from eyes.agent import EXTRACTOR_PROMPT
from eyes.match_state import SCORER_PROMPT

TEAM_A = "Gujarat Titans"
TEAM_B = "Rajasthan Royals"

# Vision descriptions captured from the last pipeline run (F2, F10, F16, F20, F21)
CASES = [
    {
        "label": "F2 — info panel, one batter",
        "frame_type": "SCOREBOARD",
        "vision": (
            "bottom scoreboard strip is visible with score/overs/batter info\n\n"
            "LIVE SCOREBOARD (persistent strip at bottom of screen):\n"
            "  Top line: GT 141-5 (13.5)\n"
            "  Bottom line: SHAHRUKH KHAN v LEFT ARM SEAMERS - IN T20s SINCE 2025 "
            "| INNINGS 8 OUTS 1 AVERAGE 34"
        ),
        "truth": {
            "score": 141, "wickets": 5, "overs": "13.5",
            "team": "GT", "batters": ["SHAHRUKH KHAN"],
        },
    },
    {
        "label": "F10 — two batters + bowler + chase",
        "frame_type": "SCOREBOARD",
        "vision": (
            "bottom scoreboard strip is visible with score/overs/batter info\n\n"
            "LIVE SCOREBOARD (persistent strip at bottom of screen):\n"
            "  Top line: GT 145-5 (14) | > TEWATIA 2(3) | SHAHRUKH 11(4) "
            "| TO WIN 66 OFF 36\n"
            "  Bottom line: BISHNOI IMP 3-15 (2) | RR logo"
        ),
        "truth": {
            "score": 145, "wickets": 5, "overs": "14",
            "team": "GT", "batters": ["TEWATIA", "SHAHRUKH"],
            "bowler": "BISHNOI", "bowler_fig": "3-15",
            "runs_needed": 66, "balls_remaining": 36,
        },
    },
    {
        "label": "F16 — score progression, this-over",
        "frame_type": "SCOREBOARD",
        "vision": (
            "bottom scoreboard strip is visible with score/overs/batter info\n\n"
            "LIVE SCOREBOARD (persistent strip at bottom of screen):\n"
            "  Top line: GT 149-5 (14.1) | > TEWATIA 6(4) | SHAHRAUKH 11(4) "
            "| TO WIN 62 OFF 35\n"
            "  Bottom line: BISHNOI IMP 3-19 (2.1) | 4 □ □"
        ),
        "truth": {
            "score": 149, "wickets": 5, "overs": "14.1",
            "team": "GT", "batters": ["TEWATIA", "SHAHRAUKH"],
            "bowler": "BISHNOI", "bowler_fig": "3-19",
        },
    },
    {
        "label": "F20 — boundary progression",
        "frame_type": "SCOREBOARD",
        "vision": (
            "bottom scoreboard strip is visible with score/overs/batter info\n\n"
            "LIVE SCOREBOARD (persistent strip at bottom of screen):\n"
            "  Top line: GT 155-5 (14.2) | > TEWATIA 12(5) | SHAHRUKH IMP 11(4) "
            "| TO WIN 56 OFF 34\n"
            "  Bottom line: BISHNOI IMP 3-25 (2.2) | 4 6"
        ),
        "truth": {
            "score": 155, "wickets": 5, "overs": "14.2",
            "team": "GT", "batters": ["TEWATIA", "SHAHRUKH"],
            "bowler": "BISHNOI", "bowler_fig": "3-25",
        },
    },
    {
        "label": "F6 — dismissal frame (c JADEJA b BISHNOI)",
        "frame_type": "SCOREBOARD",
        "vision": (
            "bottom scoreboard strip is visible with score/overs/batter info\n\n"
            "LIVE SCOREBOARD (persistent strip at bottom of screen):\n"
            "  Top line: GT 131-4 12.3\n"
            "  Bottom line: WASHINGTON SUNDAR 4(2) c JADEJA b BISHNOI SR 200"
        ),
        "truth": {
            "score": 131, "wickets": 4, "overs": "12.3",
            "team": "GT", "batters": ["WASHINGTON SUNDAR"],
            "dismissal_batter": "WASHINGTON SUNDAR",
            "dismissal_type": "caught",
        },
    },
]


def score_extractor(extracted: dict, truth: dict) -> tuple[int, int, list[str]]:
    """Score extractor output against ground truth. Returns (hits, total, details)."""
    hits = 0
    total = 0
    details = []

    def check(field, expected, label):
        nonlocal hits, total
        total += 1
        actual = extracted.get(field)
        if actual == expected or str(actual) == str(expected):
            hits += 1
            details.append(f"  ✓ {label}: {actual}")
        else:
            details.append(f"  ✗ {label}: got {actual}, expected {expected}")

    check("score", truth["score"], "score")
    check("wickets", truth["wickets"], "wickets")

    total += 1
    ext_overs = extracted.get("match_overs")
    if str(ext_overs) == str(truth["overs"]) or str(ext_overs) == str(float(truth["overs"])):
        hits += 1
        details.append(f"  ✓ overs: {ext_overs}")
    else:
        details.append(f"  ✗ overs: got {ext_overs}, expected {truth['overs']}")

    # Batters
    ext_batters = [b.get("name", "").upper() for b in extracted.get("batters", [])]
    for expected_bat in truth.get("batters", []):
        total += 1
        found = any(expected_bat.upper() in eb for eb in ext_batters)
        if found:
            hits += 1
            details.append(f"  ✓ batter: {expected_bat}")
        else:
            details.append(f"  ✗ batter: {expected_bat} not in {ext_batters}")

    # Bowler
    if "bowler" in truth:
        total += 1
        ext_bowl = (extracted.get("bowler") or {}).get("name", "").upper()
        if truth["bowler"].upper() in ext_bowl:
            hits += 1
            details.append(f"  ✓ bowler: {ext_bowl}")
        else:
            details.append(f"  ✗ bowler: got '{ext_bowl}', expected {truth['bowler']}")

    # Chase data
    if "runs_needed" in truth:
        total += 1
        ext_rn = extracted.get("runs_needed")
        if ext_rn == truth["runs_needed"]:
            hits += 1
            details.append(f"  ✓ runs_needed: {ext_rn}")
        else:
            details.append(f"  ✗ runs_needed: got {ext_rn}, expected {truth['runs_needed']}")

    if "balls_remaining" in truth:
        total += 1
        ext_br = extracted.get("balls_remaining")
        if ext_br == truth["balls_remaining"]:
            hits += 1
            details.append(f"  ✓ balls_remaining: {ext_br}")
        else:
            details.append(f"  ✗ balls_remaining: got {ext_br}, expected {truth['balls_remaining']}")

    # Dismissal
    if "dismissal_batter" in truth:
        total += 1
        ext_dis = extracted.get("dismissal")
        if ext_dis and truth["dismissal_batter"].upper() in (ext_dis.get("batter", "")).upper():
            hits += 1
            details.append(f"  ✓ dismissal: {ext_dis.get('batter')}")
        else:
            details.append(f"  ✗ dismissal: got {ext_dis}, expected {truth['dismissal_batter']}")

    return hits, total, details


async def call_groq(client, model, prompt):
    t0 = time.time()
    resp = await client.chat.completions.create(
        model=model, temperature=0, max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return time.time() - t0, resp.choices[0].message.content


async def call_together(client, model, prompt):
    t0 = time.time()
    resp = await client.post(
        f"{TOGETHER_BASE_URL}/chat/completions",
        json={"model": model, "temperature": 0, "max_tokens": 600,
              "messages": [{"role": "user", "content": prompt}]},
        headers={"Authorization": f"Bearer {TOGETHER_API_KEY}",
                 "Content-Type": "application/json"},
    )
    resp.raise_for_status()
    return time.time() - t0, resp.json()["choices"][0]["message"]["content"]


def parse_json(raw):
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if "```" in text:
            text = text[:text.index("```")]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s = text.find("{")
        e = text.rfind("}") + 1
        if s >= 0 and e > s:
            try:
                return json.loads(text[s:e])
            except json.JSONDecodeError:
                pass
        return None


async def run():
    groq = AsyncGroq(api_key=GROQ_API_KEY, timeout=15.0)
    together = httpx.AsyncClient(timeout=15.0)

    models = {
        "OLD_EXT": ("groq", "llama-3.3-70b-versatile"),
        "NEW_EXT": ("groq", "meta-llama/llama-4-scout-17b-16e-instruct"),
        "OLD_SCR": ("together", "Qwen/Qwen2.5-7B-Instruct-Turbo"),
        "NEW_SCR": ("groq", "meta-llama/llama-4-scout-17b-16e-instruct"),
    }

    print("=" * 75)
    print("A/B ACCURACY TEST — Old vs New models")
    print(f"  OLD Extractor: Llama-3.3-70B (Groq)")
    print(f"  NEW Extractor: Scout 17B (Groq)")
    print(f"  OLD Scorer:    Qwen2.5-7B (Together)")
    print(f"  NEW Scorer:    Scout 17B (Groq)")
    print("=" * 75)

    # ── EXTRACTOR A/B ─────────────────────
    ext_results = {"old": [], "new": []}

    print(f"\n{'━' * 75}")
    print("EXTRACTOR COMPARISON")
    print(f"{'━' * 75}")

    for case in CASES:
        prompt = EXTRACTOR_PROMPT.format(
            frame_type=case["frame_type"],
            team_a_name=TEAM_A, team_b_name=TEAM_B,
            description=case["vision"],
        )

        print(f"\n  {case['label']}")

        for tag, model_key in [("OLD(70B)", "OLD_EXT"), ("NEW(Scout)", "NEW_EXT")]:
            provider, model = models[model_key]
            try:
                if provider == "groq":
                    elapsed, raw = await call_groq(groq, model, prompt)
                else:
                    elapsed, raw = await call_together(together, model, prompt)

                parsed = parse_json(raw)
                if not parsed:
                    print(f"    {tag}: {elapsed:.1f}s — JSON FAIL")
                    ext_results["old" if "OLD" in tag else "new"].append((0, 1, elapsed))
                    continue

                hits, total, details = score_extractor(parsed, case["truth"])
                ext_results["old" if "OLD" in tag else "new"].append((hits, total, elapsed))
                print(f"    {tag}: {elapsed:.1f}s — {hits}/{total}")
                for d in details:
                    print(f"      {d}")

            except Exception as e:
                print(f"    {tag}: ERROR — {str(e)[:80]}")
                ext_results["old" if "OLD" in tag else "new"].append((0, 1, 0))

            await asyncio.sleep(0.5)

    # ── SCORER A/B ────────────────────────
    print(f"\n{'━' * 75}")
    print("SCORER COMPARISON")
    print(f"{'━' * 75}")

    scorer_results = {"old": [], "new": []}

    # Use case F10 (richest data) for scorer test
    scorer_case = CASES[1]  # F10
    ext_prompt = EXTRACTOR_PROMPT.format(
        frame_type=scorer_case["frame_type"],
        team_a_name=TEAM_A, team_b_name=TEAM_B,
        description=scorer_case["vision"],
    )
    # Get extraction first (use Scout for consistency)
    _, ext_raw = await call_groq(groq, "meta-llama/llama-4-scout-17b-16e-instruct", ext_prompt)
    extracted = parse_json(ext_raw) or {}

    scorer_prompt = SCORER_PROMPT.format(
        team_a=TEAM_A, team_b=TEAM_B,
        batting_team="Gujarat Titans", bowling_team="Rajasthan Royals",
        innings=2, target=211,
        batting_squad_roles="Kushagra(wk), Sudharsan(bat), Buttler(wk), Phillips(wk), Sundar(all), Tewatia(all), Rashid(all), Rabada(bowl), Ashok(bowl), Siraj(bowl), Prasidh(bowl), Shahrukh(bat)",
        bowling_squad_roles="Jaiswal(bat), Sooryavanshi(bat), Jurel(wk), Parag(all), Hetmyer(bat), Ferreira(wk), Jadeja(all), Archer(bowl), Burger(bowl), Deshpande(bowl), Sandeep(bowl), Bishnoi(bowl)",
        batting_card="Tewatia: 2(3) batting | Shahrukh Khan: 11(4) batting | Others: yet_to_bat",
        bowling_card="Bishnoi: 3-15 (2.0)",
        live_state="score=145 wickets=5 overs=14.0 batting=Gujarat Titans",
        fow="5 wickets fallen",
        history="F2: score=141, F10: score=145",
        extracted=json.dumps(extracted, indent=2),
        vision_first_200=scorer_case["vision"][:200],
    )

    print(f"\n  Test case: {scorer_case['label']}")
    print(f"  Extracted: score={extracted.get('score')}-{extracted.get('wickets')} "
          f"({extracted.get('match_overs')})")

    for tag, model_key in [("OLD(Qwen7B)", "OLD_SCR"), ("NEW(Scout)", "NEW_SCR")]:
        provider, model = models[model_key]
        try:
            if provider == "groq":
                elapsed, raw = await call_groq(groq, model, scorer_prompt)
            else:
                elapsed, raw = await call_together(together, model, scorer_prompt)

            parsed = parse_json(raw)
            if not parsed:
                print(f"\n    {tag}: {elapsed:.1f}s — JSON FAIL")
                print(f"      Raw: {raw[:200]}")
                scorer_results["old" if "OLD" in tag else "new"].append((elapsed, False))
                continue

            scorer_results["old" if "OLD" in tag else "new"].append((elapsed, True))

            ta = parsed.get("team_assignment", {})
            su = parsed.get("score_update", {})
            ou = parsed.get("overs_update", {})
            wu = parsed.get("wickets_update", {})
            bu = parsed.get("batter_updates", {})
            bo = parsed.get("bowler_update", {})
            hint = parsed.get("vision_hint", "")

            print(f"\n    {tag}: {elapsed:.1f}s")
            if ta:
                print(f"      teams: bat={ta.get('batting_team')} bowl={ta.get('bowling_team')} "
                      f"inn={ta.get('innings')} target={ta.get('target')}")
            if su:
                print(f"      score: {su.get('from')}→{su.get('to')} accepted={su.get('accepted')}")
            if ou:
                print(f"      overs: {ou.get('from')}→{ou.get('to')} accepted={ou.get('accepted')}")
            if wu:
                print(f"      wickets: {wu.get('from')}→{wu.get('to')} accepted={wu.get('accepted')}")
            if bu:
                for name, upd in bu.items():
                    print(f"      batter {name}: {upd}")
            if bo:
                print(f"      bowler: {bo}")
            if hint:
                print(f"      hint: {hint[:100]}")

            rej = parsed.get("rejected", {})
            if rej:
                print(f"      rejected: {rej}")

        except Exception as e:
            print(f"\n    {tag}: ERROR — {str(e)[:100]}")
            scorer_results["old" if "OLD" in tag else "new"].append((0, False))

        await asyncio.sleep(1)

    # ── FINAL SUMMARY ─────────────────────
    print(f"\n{'━' * 75}")
    print("EXTRACTOR SUMMARY")
    print(f"{'━' * 75}")

    for label, key in [("OLD (70B)", "old"), ("NEW (Scout)", "new")]:
        res = ext_results[key]
        total_h = sum(r[0] for r in res)
        total_t = sum(r[1] for r in res)
        avg_time = sum(r[2] for r in res) / len(res) if res else 0
        pct = total_h / total_t * 100 if total_t else 0
        print(f"  {label:<16} {pct:>5.0f}% ({total_h}/{total_t})  avg {avg_time:.1f}s")

    print(f"\n{'━' * 75}")
    print("SCORER SUMMARY")
    print(f"{'━' * 75}")
    for label, key in [("OLD (Qwen7B)", "old"), ("NEW (Scout)", "new")]:
        res = scorer_results[key]
        if res:
            elapsed = res[0][0]
            ok = res[0][1]
            print(f"  {label:<16} {'JSON OK' if ok else 'JSON FAIL'}  {elapsed:.1f}s")

    await groq.close()
    await together.aclose()


if __name__ == "__main__":
    asyncio.run(run())
