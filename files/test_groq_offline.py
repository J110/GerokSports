"""
Offline test: feed 5 saved frames through Vision → Extractor → Scorer
all on the updated providers (Vision=Together, Extractor+Scorer=Groq Scout).

Verifies:
  - Scout extractor parses JSON correctly
  - Scout scorer returns valid decisions
  - Latency per stage
  - No import/config errors
"""

import asyncio
import base64
import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from eyes.vision import Vision
from eyes.agent import Extractor
from eyes.match_state import MatchStateAgent
from eyes.config import GROQ_PRIMARY_MODEL, GROQ_FALLBACK_MODEL, TOGETHER_MODEL

import cv2
import numpy as np


FRAMES = [
    "debug_frames/f2_scoreboard.jpg",
    "debug_frames/f10_scoreboard.jpg",
    "debug_frames/f16_scoreboard.jpg",
    "debug_frames/f20_scoreboard.jpg",
    "debug_frames/f21_scoreboard.jpg",
]

TEAM_A = "Gujarat Titans"
TEAM_B = "Rajasthan Royals"


async def run():
    print("=" * 70)
    print("OFFLINE PIPELINE TEST — saved frames")
    print(f"  Vision:    Together AI ({TOGETHER_MODEL})")
    print(f"  Extractor: Groq ({GROQ_PRIMARY_MODEL} → {GROQ_FALLBACK_MODEL})")
    print(f"  Scorer:    Groq ({GROQ_PRIMARY_MODEL} → {GROQ_FALLBACK_MODEL})")
    print("=" * 70)

    vision = Vision()
    extractor = Extractor()
    scorer = MatchStateAgent()

    total_vision = 0
    total_extract = 0
    total_score = 0
    json_fails = 0

    batting_team = None
    bowling_team = None
    innings = 1
    target = None

    for i, path in enumerate(FRAMES):
        frame = cv2.imread(path)
        if frame is None:
            print(f"\n  F{i+1}: SKIP — can't read {path}")
            continue

        print(f"\n{'━' * 70}")
        print(f"  FRAME {i+1}: {path}")

        # ── VISION ────────────────────────────
        t0 = time.time()
        frame_type, desc = await vision.describe(frame)
        v_time = time.time() - t0
        total_vision += v_time
        print(f"  [VISION]    {v_time:.1f}s  type={frame_type}  ({len(desc)} chars)")
        print(f"    {desc[:120]}...")

        if frame_type in ("ADVERTISEMENT", "CLOSEUP", "PREMATCH"):
            print(f"  → Skipping (non-scoreboard)")
            continue

        # ── EXTRACTOR ─────────────────────────
        t0 = time.time()
        extracted = await extractor.extract(
            desc, frame_type,
            team_a_name=TEAM_A, team_b_name=TEAM_B,
        )
        e_time = time.time() - t0
        total_extract += e_time

        if not extracted:
            json_fails += 1
            print(f"  [EXTRACT]   {e_time:.1f}s  FAILED (empty/parse error)")
            continue

        score = extracted.get("score")
        wickets = extracted.get("wickets")
        overs = extracted.get("match_overs")
        batters = extracted.get("batters", [])
        bowler = extracted.get("bowler", {})
        vis_team = extracted.get("batting_team_visible")

        bat_str = " | ".join(
            f"{b.get('name','')} {b.get('runs','?')}({b.get('balls','?')})"
            for b in batters
        )
        bowl_str = f"{bowler.get('name','')} {bowler.get('wickets','?')}-{bowler.get('runs','?')}({bowler.get('overs','')})" if bowler else "none"

        print(f"  [EXTRACT]   {e_time:.1f}s  team={vis_team} score={score}-{wickets} ({overs})")
        print(f"    BAT: {bat_str or 'none'}")
        print(f"    BOWL: {bowl_str}")

        # ── SCORER ────────────────────────────
        t0 = time.time()
        decision = await scorer.validate(
            extracted=extracted,
            team_a=TEAM_A, team_b=TEAM_B,
            batting_team=batting_team or "",
            bowling_team=bowling_team or "",
            innings=innings,
            target=str(target) if target else "",
            batting_squad_roles="(not loaded for offline test)",
            bowling_squad_roles="(not loaded for offline test)",
            batting_card="(offline test)",
            bowling_card="(offline test)",
            live_state=f"score={score} wickets={wickets} overs={overs}",
            fow="",
            history="",
            vision_desc=desc[:200],
        )
        s_time = time.time() - t0
        total_score += s_time

        if not decision:
            json_fails += 1
            print(f"  [SCORER]    {s_time:.1f}s  FAILED (empty/parse error)")
            continue

        ta = decision.get("team_assignment", {})
        score_upd = decision.get("score_update", {})
        overs_upd = decision.get("overs_update", {})
        hint = decision.get("vision_hint", "")

        if ta and ta.get("batting_team"):
            batting_team = ta["batting_team"]
            bowling_team = ta.get("bowling_team")
            if ta.get("innings"):
                innings = ta["innings"]
            if ta.get("target"):
                target = ta["target"]

        print(f"  [SCORER]    {s_time:.1f}s")
        if ta and ta.get("batting_team"):
            print(f"    TEAMS: {batting_team} bat vs {bowling_team} bowl (inn {innings}, target={target})")
        if score_upd and score_upd.get("accepted"):
            print(f"    SCORE: {score_upd.get('from')} → {score_upd.get('to')}")
        if overs_upd and overs_upd.get("accepted"):
            print(f"    OVERS: {overs_upd.get('from')} → {overs_upd.get('to')}")
        if hint:
            print(f"    HINT: {hint[:100]}")

        cycle = v_time + e_time + s_time
        print(f"  [CYCLE]     {cycle:.1f}s total (V:{v_time:.1f} E:{e_time:.1f} S:{s_time:.1f})")

        await asyncio.sleep(1)

    # ── Summary ───────────────────────────
    n = len(FRAMES)
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Frames tested:    {n}")
    print(f"  JSON failures:    {json_fails}")
    print(f"  Avg vision:       {total_vision/n:.1f}s")
    print(f"  Avg extractor:    {total_extract/n:.1f}s")
    print(f"  Avg scorer:       {total_score/n:.1f}s")
    print(f"  Avg total cycle:  {(total_vision+total_extract+total_score)/n:.1f}s")
    print(f"\n  Vision:    Together ({TOGETHER_MODEL})")
    print(f"  Extractor: Groq ({GROQ_PRIMARY_MODEL})")
    print(f"  Scorer:    Groq ({GROQ_PRIMARY_MODEL})")

    await vision.close()
    await extractor.close()
    await scorer.close()


if __name__ == "__main__":
    asyncio.run(run())
