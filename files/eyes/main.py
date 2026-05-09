"""Machine 1 — The Eyes: Scorecard-First Architecture.

Pre-match:  User pastes URL → LLM scrapes squads → build scorecards.
Live:       Frame diff → Vision → Extractor → Match State → Scoreboard.

Usage:
    python -m eyes.main
    python -m eyes.main --window-id 12345
"""
from __future__ import annotations

import asyncio
import argparse
import json
import signal
import time

import numpy as np

from eyes.config import (
    CAPTURE_FPS,
    PREVIEW_INTERVAL,
    SERVER_URL,
    STATE_BROADCAST_INTERVAL,
)
from eyes.capture.frame_source import FrameSource, make_frame_source
from eyes.capture.downscale import downscale
from eyes.scoreboard import Scoreboard
from eyes.vision import Vision
from eyes.agent import Extractor
from eyes.match_state import MatchStateAgent
from eyes.squad_scraper import (
    scrape_cricbuzz_squads, squads_to_pipeline_format,
    build_name_lookup, format_squad_roles,
)
from eyes.player_enrichment import (
    enrich_squad_styles, enrich_squad_styles_pass2_async,
    build_styles_lookup,
)
from eyes.gpu_monitor import GPUMonitor
from eyes.network.broadcaster import Broadcaster
from eyes.network.debug_server import DebugUI
from eyes.cricket_logger import CricketLogger, set_global_frame, set_sse_callback

log = CricketLogger("MAIN")

FRAME_WIDTH = 1280


# ------------------------------------------------------------------
# Pixel-hash frame diff — skip unchanged frames, zero API cost
# ------------------------------------------------------------------

def frame_changed(current: np.ndarray, previous: np.ndarray | None,
                  threshold: float = 0.05) -> bool:
    """Compare bottom 20% of frame (scoreboard strip). <1ms, local."""
    if previous is None:
        return True
    diff = np.mean(np.abs(current.astype(float) - previous.astype(float)))
    return diff > (255 * threshold)


# ------------------------------------------------------------------
# Apply scorer decision to scoreboard
# ------------------------------------------------------------------

class ScoreJumpGuard:
    """Hold score jumps >7 for 2-frame confirmation. Code, not prompt."""

    def __init__(self):
        self._pending_score: int | None = None
        self._pending_count = 0

    def check(self, old_score: int | None, new_score: int) -> bool:
        """Return True if the score update should be applied."""
        if old_score is None or old_score == 0:
            self._reset()
            return True

        jump = new_score - old_score
        if jump <= 7:
            self._reset()
            return True

        if jump < 0:
            self._reset()
            return False

        # Jump > 7 — need 2-frame confirmation
        if self._pending_score == new_score:
            self._pending_count += 1
            if self._pending_count >= 2:
                log.info(f"Score jump {old_score}→{new_score} CONFIRMED "
                         f"after {self._pending_count} frames")
                self._reset()
                return True
            log.info(f"Score jump {old_score}→{new_score} — "
                     f"waiting ({self._pending_count}/2)")
            return False

        log.info(f"Score jump {old_score}→{new_score} (+{jump}) — "
                 f"HOLDING for confirmation")
        self._pending_score = new_score
        self._pending_count = 1
        return False

    def _reset(self):
        self._pending_score = None
        self._pending_count = 0


def apply_scorer_decision(scoreboard: Scoreboard, decision: dict,
                          frame: int, jump_guard: ScoreJumpGuard,
                          batting_team: str | None = None) -> list[str]:
    changes: list[str] = []

    if decision.get("innings_change"):
        changes.append("INNINGS CHANGE")
        return changes

    if not batting_team:
        log.info("No batting team set — skipping all updates")
        return changes

    batter_ups = decision.get("batter_updates", {})
    batters_accepted = any(
        isinstance(u, dict) and u.get("accepted", True)
        for u in (batter_ups.values() if isinstance(batter_ups, dict) else [])
    )
    bowler_up = decision.get("bowler_update", {})
    bowler_accepted = any(
        isinstance(d, dict) and d.get("accepted", True)
        for d in (bowler_up.values() if isinstance(bowler_up, dict) else [])
    )
    if not batters_accepted and not bowler_accepted:
        log.info("No players from our match recognized — skipping score")
        return changes

    score_up = decision.get("score_update", {})
    if isinstance(score_up, dict) and score_up.get("accepted") and score_up.get("to") is not None:
        old = scoreboard._inn.get("score")
        new = score_up["to"]
        if jump_guard.check(old, int(new)):
            if scoreboard.set("score", new, frame):
                changes.append(f"score: {old} -> {new}")

    overs_up = decision.get("overs_update", {})
    if isinstance(overs_up, dict) and overs_up.get("accepted") and overs_up.get("to") is not None:
        if scoreboard.set("overs", overs_up["to"], frame):
            changes.append(f"overs: {overs_up.get('from')} -> {overs_up['to']}")

    wickets_up = decision.get("wickets_update", {})
    if isinstance(wickets_up, dict) and wickets_up.get("accepted") and wickets_up.get("to") is not None:
        if scoreboard.set("wickets", wickets_up["to"], frame):
            changes.append(f"wickets: {wickets_up.get('from')} -> {wickets_up['to']}")

    dismissal = decision.get("dismissal")
    if dismissal:
        name = dismissal if isinstance(dismissal, str) else dismissal.get("batter", "")
        how = dismissal.get("how") if isinstance(dismissal, dict) else None
        bowler = dismissal.get("bowler") if isinstance(dismissal, dict) else None
        if name and scoreboard.dismiss_batter(name, how, bowler, frame=frame):
            changes.append(f"DISMISSED: {name}")

    batter_ups = decision.get("batter_updates", {})
    if isinstance(batter_ups, dict):
        for name, update in batter_ups.items():
            if not isinstance(update, dict) or not update.get("accepted", True):
                continue
            if scoreboard.update_batter(name,
                                        striker=update.get("striker"),
                                        frame=frame):
                changes.append(f"bat:{name}")

    bowler_up = decision.get("bowler_update", {})
    if isinstance(bowler_up, dict):
        for bname, bdata in bowler_up.items():
            if not isinstance(bdata, dict) or not bdata.get("accepted", True):
                continue
            if scoreboard.update_bowler(bname, frame=frame):
                changes.append(f"bowl:{bname}")

    rejected = decision.get("rejected", {})
    if isinstance(rejected, dict):
        for field, reason in rejected.items():
            log.info(f"REJECTED {field}: {reason}")

    deferred = decision.get("deferred", {})
    if isinstance(deferred, dict):
        for field, reason in deferred.items():
            log.info(f"DEFERRED {field}: {reason}")

    return changes


# ------------------------------------------------------------------
# Pre-match setup
# ------------------------------------------------------------------

async def setup_match() -> tuple[dict | None, dict[str, list[str]]]:
    """Prompt user for Cricbuzz squad URL, scrape with BeautifulSoup."""
    print("\n" + "=" * 50)
    print("  MACHINE 1 — PRE-MATCH SETUP")
    print("=" * 50)
    print("\nPaste the Cricbuzz squad URL for this match.")
    print("Example: cricbuzz.com/cricket-match-squads/69788/wi-vs-eng...\n")

    url = input("Squad URL: ").strip()
    if not url:
        log.warn("No URL provided. Running without squads.")
        return None, {}

    print("\nScraping squads...")
    raw_data = await scrape_cricbuzz_squads(url)

    if not raw_data:
        log.error("Failed to scrape squads from URL.")
        return None, {}

    raw_data, squads = squads_to_pipeline_format(raw_data)

    # Enrich squad with batting handedness + bowling style (2-pass LLM).
    # Pass-1 (prior-knowledge guess) runs synchronously here so the user
    # sees populated styles before confirming. Pass-2
    # (web-search-grounded verification) is scheduled later in
    # ``main_loop`` once the Scoreboard exists, so it can retro-patch
    # cards without blocking startup.
    print("\nLooking up batting/bowling styles...")
    try:
        await enrich_squad_styles(raw_data, pass2_background=True)
    except Exception as e:
        log.warn(f"Style enrichment Pass-1 failed: {e} — continuing without")

    print("\n" + "-" * 50)
    for key in ("team_a", "team_b"):
        team = raw_data[key]
        xi = team["playing_xi"]
        bench = team["bench"]
        print(f"\n  {team['name']} — Playing XI:")
        for i, p in enumerate(xi, 1):
            tags = []
            if p["captain"]:
                tags.append("C")
            if p["keeper"]:
                tags.append("WK")
            tag_str = f" ({','.join(tags)})" if tags else ""
            bat = p.get("batting_style", "unknown")
            bowl = p.get("bowling_style", "unknown")
            style = f"  [{bat} | {bowl}]" if bat != "unknown" or bowl != "unknown" else ""
            print(f"    {i:2}. {p['name']}{tag_str} — {p['role']}{style}")
        if bench:
            print(f"  Bench:")
            for p in bench:
                print(f"       {p['name']} — {p['role']}")

    venue = raw_data.get("venue")
    fmt = raw_data.get("format")
    if venue:
        print(f"\n  Venue: {venue}")
    if fmt:
        print(f"  Format: {fmt}")

    print("\n" + "-" * 50)
    confirm = input("\nLook correct? (y/n): ").strip().lower()
    if confirm not in ("y", "yes", ""):
        log.warn("User rejected squads. Running without.")
        return None, {}

    return raw_data, squads


# ------------------------------------------------------------------
# Main loop
# ------------------------------------------------------------------

async def main_loop(window_id: int | None = None):
    # === PRE-MATCH: prompt for URL, scrape squads ===
    log.info("=== PRE-MATCH SETUP ===")
    raw_data, squads = await setup_match()

    team_names = list(squads.keys())
    log.info(f"Squads loaded: {team_names}")

    # DON'T assume who bats — leave null.
    # The first SCOREBOARD frame tells us who's batting.
    batting_team: str | None = None
    bowling_team: str | None = None
    batting_squad: list[str] = []
    bowling_squad: list[str] = []
    batting_squad_roles = ""
    bowling_squad_roles = ""

    scoreboard = Scoreboard()

    # Schedule Pass-2 (web-search-grounded style verification) as a
    # background task. setup_match() already ran Pass-1 to populate
    # raw_data; Pass-2 retro-patches scoreboard cards via
    # update_player_styles when it eventually completes.
    if raw_data:
        _pass1_styles = build_styles_lookup(raw_data)
        if _pass1_styles:
            def _on_pass2_complete(pass2_styles: dict) -> None:
                try:
                    scoreboard.update_player_styles(pass2_styles)
                except Exception as e:  # noqa: BLE001
                    log.warn(f"Pass-2 style retro-patch failed: {e}")

            _pass2_task = asyncio.create_task(
                enrich_squad_styles_pass2_async(
                    raw_data, _pass1_styles,
                    on_complete=_on_pass2_complete))
            _pass2_task.add_done_callback(
                lambda t: t.exception() and log.warn(
                    f"Pass-2 background task raised: {t.exception()}"))

    # --- helpers to (re)assign teams once we know who's batting ---
    def assign_teams(bat_name: str, bowl_name: str, innings: int = 1):
        nonlocal batting_team, bowling_team, batting_squad, bowling_squad
        nonlocal batting_squad_roles, bowling_squad_roles
        batting_team = bat_name
        bowling_team = bowl_name
        batting_squad = squads.get(batting_team, [])
        bowling_squad = squads.get(bowling_team, [])
        if raw_data:
            for key in ("team_a", "team_b"):
                if raw_data[key]["name"] == batting_team:
                    batting_squad_roles = format_squad_roles(raw_data, key)
                elif raw_data[key]["name"] == bowling_team:
                    bowling_squad_roles = format_squad_roles(raw_data, key)
        player_styles = build_styles_lookup(raw_data) if raw_data else {}
        scoreboard.setup_innings(batting_team, bowling_team,
                                 batting_squad, bowling_squad,
                                 player_styles=player_styles)
        scoreboard.current_innings = innings
        log.info(f"TEAMS SET: {batting_team} batting (inn {innings}) "
                 f"vs {bowling_team} bowling")

    # === INIT AGENTS ===
    vision = Vision()
    extractor = Extractor()
    scorer = MatchStateAgent()
    gpu = GPUMonitor()
    broadcaster = Broadcaster(SERVER_URL)
    debug = DebugUI()
    frames = make_frame_source(window_id=window_id, fps=CAPTURE_FPS)

    set_sse_callback(debug.emit)

    debug.set_state_getters(
        scorecard=lambda: scoreboard.get_state(),
        field=lambda: {},
        micro=lambda: {},
        validation=lambda: {},
        full_state=lambda: {
            "scoreboard": scoreboard.get_state(),
            "gpu": gpu.get_stats(),
        },
        select_window=lambda wid: setattr(frames, 'window_id', wid),
    )

    await debug.start()
    frames.start()
    log.info(f"Pipeline starting — window: {window_id or 'none (select in debug UI)'}")
    log.info("Debug UI: http://localhost:8001")

    frame_count = 0
    vision_hint: str | None = None
    prev_strip: np.ndarray | None = None
    jump_guard = ScoreJumpGuard()

    try:
        while True:
            raw = frames.get_latest()
            if raw is None:
                await asyncio.sleep(0.1)
                continue

            frame_count += 1
            set_global_frame(frame_count)

            frame = downscale(raw, FRAME_WIDTH)
            h = frame.shape[0]
            strip_region = frame[int(h * 0.8):, :]

            # === PIXEL DIFF: skip if nothing changed on screen ===
            if not frame_changed(strip_region, prev_strip):
                if frame_count % 20 == 0:
                    log.info(f"[F{frame_count}] No pixel change — skipping")
                await asyncio.sleep(5)
                continue
            prev_strip = strip_region.copy()

            # === VISION: describe the frame ===
            gpu.on_qwen_start("vision", frame_count)
            t_vision = time.time()
            frame_type, description, _action_desc = await vision.describe(frame, vision_hint)
            vision_ms = (time.time() - t_vision) * 1000
            gpu.on_qwen_end("vision", frame_count, vision_ms / 1000)

            if not description and frame_type == "UNKNOWN":
                log.warn("Vision returned empty — skipping")
                await asyncio.sleep(5)
                continue

            # --- Route by frame type ---
            if frame_type == "ADVERTISEMENT":
                log.info(f"[F{frame_count}] AD — {vision_ms:.0f}ms — skip")
                await asyncio.sleep(5)
                continue

            if frame_type in ("CLOSEUP", "PREMATCH"):
                log.info(f"[F{frame_count}] {frame_type} {vision_ms:.0f}ms — "
                         f"{description[:120]}")
                await debug.emit("vision", {"frame_type": frame_type,
                                             "description": description[:200],
                                             "ms": round(vision_ms)})
                await asyncio.sleep(5)
                continue

            # SCOREBOARD or GRAPHIC or UNKNOWN — full pipeline
            log.info(f"[F{frame_count}] {frame_type} {vision_ms:.0f}ms — "
                     f"{description[:180]}")
            await debug.emit("vision", {"frame_type": frame_type,
                                         "description": description,
                                         "ms": round(vision_ms)})

            # === EXTRACTOR: map to scorecard fields ===
            gpu.on_qwen_start("extractor", frame_count)
            t_ext = time.time()


            extracted = await extractor.extract(
                description,
                frame_type=frame_type,
                team_a_name=team_names[0] if team_names else "",
                team_b_name=team_names[1] if len(team_names) > 1 else "",
            )
            ext_ms = (time.time() - t_ext) * 1000
            gpu.on_qwen_end("extractor", frame_count, ext_ms / 1000)

            if not extracted or extracted.get("frame_type") == "ad":
                log.info(f"[EXTRACT {ext_ms:.0f}ms] No scorecard data")
                await asyncio.sleep(5)
                continue

            if not extracted.get("has_scorecard_data", True):
                log.info(f"[EXTRACT {ext_ms:.0f}ms] Context only: "
                         f"{extracted.get('frame_type', '?')}")
                await asyncio.sleep(5)
                continue

            corrections = extracted.get("corrections", [])
            if corrections:
                log.info(f"[EXTRACT] Corrections: {corrections}")

            log.info(f"[EXTRACT {ext_ms:.0f}ms] {extracted.get('frame_type', '?')} | "
                     f"score={extracted.get('score', '?')}-"
                     f"{extracted.get('wickets', '?')} "
                     f"({extracted.get('match_overs', '?')})")

            # === MATCH STATE: official scorer validates ===
            gpu.on_qwen_start("scorer", frame_count)
            t_scorer = time.time()

            fow_str = json.dumps(scoreboard.fall_of_wickets[-5:]) \
                if scoreboard.fall_of_wickets else "None yet"
            history_str = json.dumps(scoreboard.get_update_history(10))

            decision = await scorer.validate(
                extracted=extracted,
                team_a=team_names[0] if team_names else "?",
                team_b=team_names[1] if len(team_names) > 1 else "?",
                batting_team=batting_team or "NOT SET",
                bowling_team=bowling_team or "NOT SET",
                innings=scoreboard.current_innings,
                target=str(scoreboard._inn.get("target") or "first innings"),
                batting_squad_roles=batting_squad_roles,
                bowling_squad_roles=bowling_squad_roles,
                batting_card=scoreboard.format_batting_card(),
                bowling_card=scoreboard.format_bowling_card(),
                live_state=scoreboard.get_live_state_str(),
                fow=fow_str,
                history=history_str,
                vision_desc=description,
            )
            scorer_ms = (time.time() - t_scorer) * 1000
            gpu.on_qwen_end("scorer", frame_count, scorer_ms / 1000)

            # === HANDLE TEAM ASSIGNMENT from scorer ===
            ta = decision.get("team_assignment", {})
            if isinstance(ta, dict) and ta.get("batting_team"):
                new_bat = ta["batting_team"]
                new_inn = ta.get("innings", 1)

                # Code guard: if extractor says bowling_scorecard for team X,
                # then X is bowling, not batting. Flip if scorer got it wrong.
                g_type = extracted.get("graphic_type")
                g_team = extracted.get("graphic_team", "")
                if g_type == "bowling_scorecard" and g_team:
                    for tn in team_names:
                        if (g_team.upper() in tn.upper()
                                or tn.upper() in g_team.upper()):
                            if (new_bat.upper() in tn.upper()
                                    or tn.upper() in new_bat.upper()):
                                other = [t for t in team_names if t != tn][0]
                                log.info(f"Bowling scorecard for {tn} — "
                                         f"flipping: {tn} bowls, {other} bats")
                                new_bat = other
                            break

                # ONLY accept names matching our two teams
                resolved_bat = None
                for tn in team_names:
                    if (new_bat.upper() in tn.upper()
                            or tn.upper() in new_bat.upper()):
                        resolved_bat = tn
                        break

                if not resolved_bat:
                    log.info(f"Team assignment IGNORED: '{new_bat}' "
                             f"not in {team_names}")
                elif resolved_bat != batting_team:
                    resolved_bowl = [t for t in team_names
                                     if t != resolved_bat][0]
                    assign_teams(resolved_bat, resolved_bowl,
                                 new_inn or 1)
                    target_val = ta.get("target")
                    if target_val:
                        scoreboard.set("target", target_val, frame_count)

            vision_hint = decision.get("vision_hint")
            if vision_hint:
                log.info(f"[SCORER] Hint: {vision_hint}")

            if decision:
                changes = apply_scorer_decision(scoreboard, decision,
                                                frame_count, jump_guard,
                                                batting_team=batting_team,
                                                vision_desc=description)
                if changes:
                    log.info(f"[SCORER {scorer_ms:.0f}ms] {changes}")
                    await debug.emit("update", {"changes": changes})
                else:
                    log.info(f"[SCORER {scorer_ms:.0f}ms] No changes")
            else:
                log.info(f"[SCORER {scorer_ms:.0f}ms] Empty decision")

            # === PERIODIC ===
            gpu.on_frame_end(frame_count)

            if frame_count % 10 == 0:
                log.info(f"Score: {scoreboard.get_summary()} | "
                         f"Bat: {scoreboard.get_current_batters()} | "
                         f"Bowl: {scoreboard.get_current_bowler()}")

            if frame_count % 30 == 0:
                gpu.print_stats()

            if frame_count % STATE_BROADCAST_INTERVAL == 0:
                await broadcaster.send_state(scoreboard.get_state())

            if frame_count % PREVIEW_INTERVAL == 0:
                await debug.update_preview(frame)

            await debug.emit("status", {
                "frame": frame_count,
                "vision_ms": round(vision_ms),
                "extract_ms": round(ext_ms),
                "scorer_ms": round(scorer_ms),
                "gpu": gpu.get_stats(),
            })

            await asyncio.sleep(5)

    except asyncio.CancelledError:
        log.info("Shutting down...")
    except Exception as e:
        log.error(f"Main loop exception: {e}")
        import traceback
        traceback.print_exc()
    finally:
        frames.stop()
        await vision.close()
        await extractor.close()
        await scorer.close()
        await broadcaster.close()
        await debug.stop()
        log.info("Eyes stopped.")


def main():
    parser = argparse.ArgumentParser(description="Machine 1 — The Eyes")
    parser.add_argument("--window-id", type=int, default=None,
                        help="macOS window ID to capture")
    args = parser.parse_args()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    task = loop.create_task(main_loop(args.window_id))

    def shutdown(sig, _frame):
        log.info(f"Received signal {sig}, shutting down...")
        task.cancel()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        loop.run_until_complete(task)
    except asyncio.CancelledError:
        pass
    finally:
        loop.close()


if __name__ == "__main__":
    main()
