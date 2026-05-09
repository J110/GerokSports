"""
Batch-scrape ball-by-ball commentary for 10 benchmark matches.

Uses the existing scrape_commentary.py functions via the ESPN playbyplay API.
Saves to /data/commentary/commentary_{match_id}.md + .json

Usage:
    python files/scrape_batch_commentary.py
"""
from __future__ import annotations

import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(__file__))

from scrape_commentary import (
    fetch_match_summary,
    extract_match_info,
    fetch_all_commentary,
    build_ball_entries,
    save_markdown,
    save_json,
)

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                       "data", "commentary")

MATCHES = [
    # (match_id, short_label)
    ("1512773", "IND vs NZ — T20 WC 2026 Final"),
    ("1512772", "IND vs ENG — T20 WC 2026 Semi-Final"),
    ("1415719", "IND vs PAK — T20 WC 2024 New York"),
    ("1415755", "IND vs SA — T20 WC 2024 Final"),
    ("951373",  "WI vs ENG — T20 WC 2016 Final"),
    ("1298150", "IND vs PAK — T20 WC 2022 Melbourne"),
    ("1512731", "SA vs AFG — T20 WC 2026 Super Over"),
    ("1512737", "ZIM vs AUS — T20 WC 2026"),
    ("1426306", "RCB vs CSK — IPL 2024"),
    ("1370353", "CSK vs GT — IPL 2023 Final"),
]

SLEEP_BETWEEN_MATCHES = 2.0


def scrape_one(match_id: str, label: str) -> dict:
    """Scrape a single match. Returns stats dict."""
    md_path = os.path.join(OUT_DIR, f"commentary_{match_id}.md")
    json_path = os.path.join(OUT_DIR, f"commentary_{match_id}.json")

    if os.path.exists(md_path):
        size_kb = os.path.getsize(md_path) / 1024
        if size_kb > 5:
            print(f"  SKIP — already exists ({size_kb:.0f} KB)")
            return {"status": "skipped", "file": md_path}

    print(f"  [1/3] Fetching summary...")
    try:
        summary = fetch_match_summary(match_id)
        match_info = extract_match_info(summary)
        print(f"  Match: {match_info.get('name', '?')}")
        print(f"  Result: {match_info.get('result', '?')}")
    except Exception as e:
        print(f"  Warning: summary failed ({e})")
        match_info = {"name": label}

    print(f"  [2/3] Fetching ball-by-ball commentary...")
    raw_items = fetch_all_commentary(match_id)
    if not raw_items:
        print(f"  ERROR — no commentary returned")
        return {"status": "error", "reason": "no commentary"}

    entries = build_ball_entries(raw_items)
    ball_entries = [e for e in entries if e["batter"]]
    innings_set = sorted(set(e["innings"] for e in ball_entries))

    print(f"  Total: {len(ball_entries)} deliveries across "
          f"{len(innings_set)} innings")
    for inn in innings_set:
        inn_balls = [e for e in ball_entries if e["innings"] == inn]
        print(f"    Innings {inn}: {len(inn_balls)} balls")

    print(f"  [3/3] Saving...")
    save_markdown(match_info, entries, md_path)
    save_json(entries, json_path)

    return {
        "status": "ok",
        "deliveries": len(ball_entries),
        "innings": len(innings_set),
        "file": md_path,
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print("=" * 70)
    print("BATCH COMMENTARY SCRAPER — 10 benchmark matches")
    print(f"Output: {OUT_DIR}")
    print("=" * 70)

    results = []
    total_deliveries = 0

    for i, (mid, label) in enumerate(MATCHES, 1):
        print(f"\n[{i}/{len(MATCHES)}] {label} (ID: {mid})")
        print("-" * 50)

        try:
            stats = scrape_one(mid, label)
            results.append((mid, label, stats))
            if stats.get("deliveries"):
                total_deliveries += stats["deliveries"]
        except Exception:
            traceback.print_exc()
            results.append((mid, label, {"status": "error",
                                         "reason": traceback.format_exc()[-200:]}))

        if i < len(MATCHES):
            time.sleep(SLEEP_BETWEEN_MATCHES)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for mid, label, stats in results:
        status = stats["status"]
        if status == "ok":
            print(f"  OK   {label}: {stats['deliveries']} deliveries")
        elif status == "skipped":
            print(f"  SKIP {label}: already exists")
        else:
            print(f"  FAIL {label}: {stats.get('reason', '?')}")

    print(f"\nTotal new deliveries scraped: {total_deliveries}")
    print(f"Files in: {OUT_DIR}")


if __name__ == "__main__":
    main()
