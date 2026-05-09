"""Retry scraping matches that got 502 errors, with retry on failed pages."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(__file__))

from scrape_commentary import (
    API_BASE, HEADERS, SLEEP_BETWEEN_PAGES,
    fetch_match_summary, extract_match_info,
    build_ball_entries, save_markdown, save_json,
)

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                       "data", "commentary")

RETRY_MATCHES = [
    ("1415755", "IND vs SA — T20 WC 2024 Final"),
    ("1512731", "SA vs AFG — T20 WC 2026 Super Over"),
]

MAX_PAGE_RETRIES = 3
RETRY_SLEEP = 5.0


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_all_commentary_with_retry(match_id: str) -> list[dict]:
    """Fetch all pages with retry on 502 errors."""
    page = 1
    all_items: list[dict] = []
    total_pages = None

    while True:
        url = f"{API_BASE}/playbyplay?event={match_id}&page={page}"
        label = f"page {page}" + (f"/{total_pages}" if total_pages else "")

        success = False
        for attempt in range(1, MAX_PAGE_RETRIES + 1):
            try:
                print(f"  Fetching {label} (attempt {attempt})...")
                data = _fetch_json(url)
                success = True
                break
            except urllib.error.HTTPError as e:
                print(f"  HTTP {e.code} on {label} (attempt {attempt})")
                if e.code in (502, 503, 504) and attempt < MAX_PAGE_RETRIES:
                    print(f"  Retrying in {RETRY_SLEEP}s...")
                    time.sleep(RETRY_SLEEP)
                else:
                    print(f"  Giving up on {label}")
                    break

        if not success:
            print(f"  Failed after {MAX_PAGE_RETRIES} attempts — stopping.")
            break

        comm = data.get("commentary", {})
        items = comm.get("items", [])
        total_pages = comm.get("pageCount", total_pages)

        if not items:
            break

        all_items.extend(items)
        print(f"    Got {len(items)} items (total: {len(all_items)})")

        if total_pages and page >= total_pages:
            break

        page += 1
        time.sleep(SLEEP_BETWEEN_PAGES)

    return all_items


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("RETRY SCRAPER — matches with 502 errors\n")

    for mid, label in RETRY_MATCHES:
        md_path = os.path.join(OUT_DIR, f"commentary_{mid}.md")
        json_path = os.path.join(OUT_DIR, f"commentary_{mid}.json")

        print(f"{'=' * 60}")
        print(f"{label} (ID: {mid})")
        print(f"{'=' * 60}")

        try:
            summary = fetch_match_summary(mid)
            match_info = extract_match_info(summary)
            print(f"  Match: {match_info.get('name')}")
        except Exception as e:
            print(f"  Summary failed: {e}")
            match_info = {"name": label}

        raw_items = fetch_all_commentary_with_retry(mid)
        if not raw_items:
            print("  No items — skipping\n")
            continue

        entries = build_ball_entries(raw_items)
        ball_entries = [e for e in entries if e["batter"]]
        innings_set = sorted(set(e["innings"] for e in ball_entries))
        print(f"  Total: {len(ball_entries)} deliveries, "
              f"{len(innings_set)} innings")
        for inn in innings_set:
            n = sum(1 for e in ball_entries if e["innings"] == inn)
            print(f"    Innings {inn}: {n} balls")

        save_markdown(match_info, entries, md_path)
        save_json(entries, json_path)
        print()
        time.sleep(3)


if __name__ == "__main__":
    main()
