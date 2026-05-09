"""Offline test: run saved frames through the dual-vision pipeline.

Uses debug_frames/ scoreboard+ad frames to test:
1. Qwen3-VL primary with Scout fallback (short-scoreboard augmentation)
2. Join phase (2 consistent readings)
3. Bowler lock after over change
4. Dismissal guard (no dismissal without wicket increase)
"""
import asyncio
import glob
import json
import os
import re
import sys
import time

import cv2

sys.path.insert(0, os.path.dirname(__file__))

from eyes.vision import Vision
from eyes.agent import Extractor
from eyes.match_state import MatchStateAgent as Scorer
from eyes.scoreboard import Scoreboard
from eyes.squad_scraper import (
    scrape_cricbuzz_squads, squads_to_pipeline_format,
    format_squad_roles,
)
from eyes.cricket_logger import CricketLogger

log = CricketLogger("TEST")

SQUAD_URL = "https://www.cricbuzz.com/cricket-match-squads/149721/rcb-vs-csk-11th-match-indian-premier-league-2026"
FRAMES_DIR = os.path.join(os.path.dirname(__file__), "debug_frames")
MAX_FRAMES = 25


def natural_sort_key(path):
    nums = re.findall(r'\d+', os.path.basename(path))
    return int(nums[0]) if nums else 0


async def main():
    log.info("=" * 60)
    log.info("OFFLINE TEST — saved frames")
    log.info("=" * 60)

    log.info("Scraping squads...")
    raw_data = await scrape_cricbuzz_squads(SQUAD_URL)
    if not raw_data:
        log.error("Squad scrape failed")
        return
    raw_data, squads = squads_to_pipeline_format(raw_data)
    team_names = list(squads.keys())
    log.info(f"Teams: {team_names}")

    all_frames = sorted(
        glob.glob(os.path.join(FRAMES_DIR, "f*_scoreboard.jpg"))
        + glob.glob(os.path.join(FRAMES_DIR, "f*_ad.jpg")),
        key=natural_sort_key,
    )
    if not all_frames:
        log.error("No frames found in debug_frames/")
        return

    all_frames = all_frames[:MAX_FRAMES]
    log.info(f"Testing {len(all_frames)} frames")

    vision = Vision()
    extractor = Extractor()
    scorer = Scorer()
    scoreboard = Scoreboard()

    batting_team = "Chennai Super Kings"
    bowling_team = "Royal Challengers Bengaluru"
    batting_squad = squads.get(batting_team, [])
    bowling_squad = squads.get(bowling_team, [])

    roles_map: dict[str, str] = {}
    for key in ("team_a", "team_b"):
        for p in (raw_data[key].get("playing_xi", [])
                  + raw_data[key].get("bench", [])):
            roles_map[p["name"]] = p.get("role", "")

    scoreboard.setup_innings(batting_team, bowling_team,
                             batting_squad, bowling_squad,
                             squad_roles=roles_map)

    vision_hint = None

    qwen_count = 0
    scout_fb_count = 0
    merged_count = 0
    scoreboard_count = 0

    for i, fpath in enumerate(all_frames):
        fname = os.path.basename(fpath)
        frame = cv2.imread(fpath)
        if frame is None:
            continue

        t0 = time.time()
        frame_type, description, action_desc = await vision.describe(
            frame, vision_hint)
        v_ms = (time.time() - t0) * 1000

        if frame_type in ("ADVERTISEMENT", "CLOSEUP", "PREMATCH"):
            log.info(f"[{fname}] {frame_type} {v_ms:.0f}ms — skipping")
            continue

        if frame_type == "UNKNOWN" and not description:
            log.info(f"[{fname}] UNKNOWN {v_ms:.0f}ms — skipping")
            continue

        t0 = time.time()
        extracted = await extractor.extract(
            description=description,
            frame_type=frame_type,
            team_a_name=batting_team,
            team_b_name=bowling_team,
        )
        e_ms = (time.time() - t0) * 1000

        if not extracted or extracted.get("frame_type") == "ad":
            log.info(f"[{fname}] {frame_type} V:{v_ms:.0f} E:{e_ms:.0f} — "
                     f"no data")
            continue

        scoreboard.on_scoreboard_frame()
        scoreboard_count += 1

        if extracted.get("batters"):
            for b in extracted["batters"]:
                bname = b.get("name", "")
                if bname:
                    scoreboard.update_batter(
                        bname,
                        runs=b.get("runs"),
                        balls=b.get("balls"),
                        fours=b.get("fours"),
                        sixes=b.get("sixes"),
                        striker=b.get("striker"),
                        frame=i)

        if extracted.get("score") is not None:
            try:
                scoreboard.set("score", int(extracted["score"]), i)
            except (ValueError, TypeError):
                pass

        if extracted.get("match_overs") is not None:
            scoreboard.set("overs", extracted["match_overs"], i)

        if extracted.get("wickets") is not None:
            try:
                scoreboard.set("wickets", int(extracted["wickets"]), i)
            except (ValueError, TypeError):
                pass

        _ext_bowler = extracted.get("bowler")
        if _ext_bowler and isinstance(_ext_bowler, dict):
            _eb_name = _ext_bowler.get("name", "")
            if _eb_name:
                _eb_resolved = scoreboard.resolve_name(_eb_name)
                _cur_bowler = scoreboard._inn.get("current_bowler")

                if (scoreboard._bowler_locked
                        and _eb_resolved
                        and _eb_resolved != _cur_bowler):
                    log.info(f"  [GUARD] Bowler locked to "
                             f"{_cur_bowler} this over — "
                             f"rejecting {_eb_resolved}")
                elif (scoreboard._bowler_must_change
                        and _eb_resolved
                        and _eb_resolved == scoreboard._prev_over_bowler):
                    log.info(f"  [GUARD] Same bowler {_eb_resolved} "
                             f"after over change — waiting")
                else:
                    if (scoreboard._bowler_must_change
                            and _eb_resolved
                            and _eb_resolved != scoreboard._prev_over_bowler):
                        log.info(f"  [BOWLER] New bowler: "
                                 f"{_eb_resolved} (was "
                                 f"{scoreboard._prev_over_bowler})")
                        scoreboard._bowler_must_change = False
                        scoreboard._bowler_locked = True
                    scoreboard.update_bowler(
                        _eb_name,
                        overs=_ext_bowler.get("overs"),
                        runs=_ext_bowler.get("runs"),
                        wickets=_ext_bowler.get("wickets"),
                        frame=i)

        if scoreboard.over_just_changed():
            prev_over = (scoreboard._last_over_num or 1) - 1
            if prev_over >= 0:
                scoreboard.on_new_over(prev_over)

        score_str = (f"{extracted.get('score')}-"
                     f"{extracted.get('wickets')} "
                     f"({extracted.get('match_overs')})")
        bat_str = " | ".join(
            f"{b.get('name')} {b.get('runs')}({b.get('balls')})"
            for b in (extracted.get("batters") or []))
        bw = extracted.get("bowler") or {}
        bw_str = (f"{bw.get('name')} {bw.get('wickets')}-{bw.get('runs')} "
                  f"({bw.get('overs')})" if bw.get("name") else "none")

        log.info(f"[{fname}] {frame_type} V:{v_ms:.0f} E:{e_ms:.0f}")
        log.info(f"  Extracted: {score_str}  Bat: {bat_str}  Bowl: {bw_str}")
        log.info(f"  STATE: {scoreboard._inn.get('score')}-"
                 f"{scoreboard._inn.get('wickets')} "
                 f"({scoreboard._inn.get('overs')}) | "
                 f"Bat: {scoreboard.get_current_batters()} | "
                 f"Bowl: {scoreboard.get_current_bowler()}")

    log.info("=" * 60)
    log.info(f"OFFLINE TEST COMPLETE — {scoreboard_count} scoreboard frames")
    log.info(f"Final state: {scoreboard._inn.get('score')}-"
             f"{scoreboard._inn.get('wickets')} "
             f"({scoreboard._inn.get('overs')}) inn="
             f"{scoreboard.current_innings}")
    log.info(f"Batters: {scoreboard.get_current_batters()}")
    log.info(f"Bowler: {scoreboard.get_current_bowler()}")
    log.info("=" * 60)

    await vision.close()
    await extractor.close()
    await scorer.close()


if __name__ == "__main__":
    asyncio.run(main())
