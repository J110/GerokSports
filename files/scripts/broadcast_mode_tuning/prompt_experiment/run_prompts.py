#!/usr/bin/env python3
"""Run 5 candidate prompts against 25 fixture frames via Groq Llama-4-Scout.

Outputs results.csv with columns:
    frame, truth_label, prompt_id, raw_response, parsed_answer

Usage:
    cd files/scripts/broadcast_mode_tuning/prompt_experiment
    PYTHONPATH=../../.. python3 run_prompts.py
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import csv
import re
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[3]
FIXTURE_DIR = SCRIPT_DIR / "fixtures"
RESULTS_CSV = SCRIPT_DIR / "results.csv"

PROMPTS = {
    "P1_binary": (
        "Is this frame from LIVE cricket play, or is it a REPLAY / "
        "slow-motion / analysis graphic? Answer with exactly one word: "
        "LIVE or REPLAY."
    ),
    "P2_scene": (
        "Classify this cricket frame into ONE of:\n"
        "  DELIVERY — bowler is releasing the ball, ball is in flight, "
        "or batter is playing a shot in live action\n"
        "  REPLAY — slow-motion, replay tag, analysis graphic, or "
        "unusual replay-only angle\n"
        "  BETWEEN_DELIVERIES — players walking, fielders adjusting, "
        "no ball action\n"
        "  REACTION — close-up of player(s) post-event (celebrating, "
        "walking off)\n"
        "  GRAPHIC — score card, ad, or non-action graphic dominates "
        "the frame\n"
        "Reply with just the label."
    ),
    "P3_checklist": (
        "Mark any visible in this cricket frame (Y/N for each):\n"
        "  REPLAY_TAG: REPLAY/INSTANT REPLAY text\n"
        "  SLO_MO: SLOW MOTION/SLO-MO text or blurred-motion capture\n"
        "  ANALYSIS: ANALYSIS/BREAKDOWN/STATS graphic dominating frame\n"
        "  BALL_SPEED: speed/trajectory overlay\n"
        "  CROWD_FOREGROUND: crowd/spectators take >30% of the frame\n"
        "  BOWLER_RELEASING: bowler is captured mid-action releasing "
        "the ball\n"
        "  BATTER_PLAYING: batter is mid-swing or just-played\n"
        "  FIELDER_DIVING: fielder is diving / leaping to catch\n"
        "Format: REPLAY_TAG: N, SLO_MO: N, ..."
    ),
    "P4_camera": (
        "What is the camera framing in this cricket frame? Answer ONE:\n"
        "  BOWLERS_END_WIDE — view from behind the bowler showing the "
        "pitch\n"
        "  SIDE_ON_PITCH — square-of-the-wicket view of the pitch\n"
        "  CLOSEUP — close-up of one player\n"
        "  AERIAL — overhead or stand-level wide\n"
        "  REPLAY_CUT — angle that's NOT typical live broadcast "
        "(foot-level, behind-batter, slow-motion)\n"
        "  GRAPHIC — graphic overlay dominates"
    ),
    "P5_anchor": (
        "In this single frame of a cricket broadcast, is the camera "
        "positioned at the standard live pitch view (showing bowler "
        "running in OR the batter at the crease about to face), with "
        "no replay indicators? Answer YES or NO."
    ),
}


def truth_label(frame_path: Path) -> str:
    return frame_path.stem.rsplit("_", 1)[0]


def parse_answer(prompt_id: str, raw: str) -> str:
    s = (raw or "").strip()
    if not s or s.startswith("[err") or s.startswith("[timeout"):
        return "ERROR"
    upper = s.upper()
    if prompt_id == "P1_binary":
        if "REPLAY" in upper.split():
            return "REPLAY"
        if "LIVE" in upper.split():
            return "LIVE"
        if "REPLAY" in upper:
            return "REPLAY"
        if "LIVE" in upper:
            return "LIVE"
        return "OTHER"
    if prompt_id == "P2_scene":
        for label in (
            "BETWEEN_DELIVERIES", "DELIVERY", "REPLAY",
            "REACTION", "GRAPHIC",
        ):
            if re.search(rf"\b{label}\b", upper):
                return label
        return "OTHER"
    if prompt_id == "P3_checklist":
        keys = [
            "REPLAY_TAG", "SLO_MO", "ANALYSIS", "BALL_SPEED",
            "CROWD_FOREGROUND", "BOWLER_RELEASING",
            "BATTER_PLAYING", "FIELDER_DIVING",
        ]
        flags = []
        for k in keys:
            m = re.search(rf"{k}\s*:?\s*(Y(?:ES)?|N(?:O)?)", upper)
            if m:
                flags.append(f"{k}={'Y' if m.group(1).startswith('Y') else 'N'}")
            else:
                flags.append(f"{k}=?")
        return ";".join(flags)
    if prompt_id == "P4_camera":
        for label in (
            "BOWLERS_END_WIDE", "SIDE_ON_PITCH", "CLOSEUP",
            "AERIAL", "REPLAY_CUT", "GRAPHIC",
        ):
            if re.search(rf"\b{label}\b", upper):
                return label
        return "OTHER"
    if prompt_id == "P5_anchor":
        if re.search(r"\bYES\b", upper):
            return "YES"
        if re.search(r"\bNO\b", upper):
            return "NO"
        return "OTHER"
    return "OTHER"


async def call_groq(client, model: str, prompt: str, jpg: bytes,
                    timeout_s: float = 90.0) -> str:
    b64 = base64.b64encode(jpg).decode()
    try:
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                temperature=0.2,
                max_tokens=260,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        {"type": "text", "text": prompt},
                    ],
                }],
            ),
            timeout=timeout_s,
        )
        if resp.choices and resp.choices[0].message:
            return (resp.choices[0].message.content or "").strip()
        return ""
    except asyncio.TimeoutError:
        return "[timeout]"
    except Exception as e:  # noqa: BLE001
        return f"[err: {type(e).__name__}: {e}]"


async def call_with_retry(client, model, prompt, jpg, attempts: int = 3) -> str:
    delay = 4.0
    last = ""
    for _ in range(attempts):
        last = await call_groq(client, model, prompt, jpg)
        if not last.startswith("[err") and not last.startswith("[timeout"):
            return last
        await asyncio.sleep(delay)
        delay *= 2
    return last


FIELDNAMES = ["frame", "truth_label", "prompt_id",
              "raw_response", "parsed_answer"]


def _load_existing() -> list[dict[str, str]]:
    if not RESULTS_CSV.exists():
        return []
    with RESULTS_CSV.open() as f:
        return list(csv.DictReader(f))


async def main_async() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prompts",
        default="",
        help="Comma-separated prompt IDs to (re-)run, e.g. P2_scene,P3_checklist. "
             "Default: all prompts.",
    )
    parser.add_argument(
        "--fixtures",
        default="",
        help="Comma-separated fixture stems (without .jpg) to (re-)run, "
             "e.g. real_001,real_002. Default: all fixtures.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Merge new rows into existing results.csv: drop matching "
             "(fixture,prompt) pairs and append re-run rows.",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(REPO_ROOT / "files"))
    from groq import AsyncGroq
    from eyes.config import GROQ_API_KEY, GROQ_PRIMARY_MODEL

    prompt_filter = {p.strip() for p in args.prompts.split(",") if p.strip()}
    fixture_filter = {f.strip() for f in args.fixtures.split(",") if f.strip()}

    all_fixtures = sorted(FIXTURE_DIR.glob("*.jpg"))
    if not all_fixtures:
        print(f"No fixtures in {FIXTURE_DIR}; run extract_fixtures.py first.")
        return 1
    fixtures = [f for f in all_fixtures
                if not fixture_filter or f.stem in fixture_filter]
    prompts = {pid: p for pid, p in PROMPTS.items()
               if not prompt_filter or pid in prompt_filter}
    if not fixtures or not prompts:
        print("Filter excluded all fixtures or prompts.")
        return 1

    n_total = len(fixtures) * len(prompts)
    print(f"Running {len(fixtures)} fixtures x {len(prompts)} prompts "
          f"= {n_total} calls")

    client = AsyncGroq(api_key=GROQ_API_KEY, timeout=90.0)
    new_rows: list[dict[str, str]] = []
    t0 = time.time()
    n_done = 0

    for fx in fixtures:
        jpg = fx.read_bytes()
        truth = truth_label(fx)
        for pid, prompt in prompts.items():
            raw = await call_with_retry(client, GROQ_PRIMARY_MODEL, prompt, jpg)
            parsed = parse_answer(pid, raw)
            new_rows.append({
                "frame": fx.name,
                "truth_label": truth,
                "prompt_id": pid,
                "raw_response": raw,
                "parsed_answer": parsed,
            })
            n_done += 1
            elapsed = time.time() - t0
            print(f"[{n_done:3d}/{n_total}] {fx.name} | {pid:12s} | "
                  f"{parsed:30s} | {elapsed:5.1f}s")
            await asyncio.sleep(0.4)

    if args.append:
        existing = _load_existing()
        replace_keys = {(r["frame"], r["prompt_id"]) for r in new_rows}
        merged = [r for r in existing
                  if (r["frame"], r["prompt_id"]) not in replace_keys]
        merged.extend(new_rows)
        merged.sort(key=lambda r: (r["frame"], r["prompt_id"]))
        rows_out = merged
    else:
        rows_out = new_rows

    with RESULTS_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows_out)
    print(f"\nWrote {len(rows_out)} rows ({len(new_rows)} new) -> {RESULTS_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
