"""
Scrape ball-by-ball commentary from ESPNcricinfo via ESPN playbyplay API.

Usage:
    python scrape_commentary.py <espncricinfo_match_id> [output_file]

Example:
    python scrape_commentary.py 1512773
    python scrape_commentary.py 1512773 commentary_ind_vs_nz_final.md
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
import urllib.error

API_BASE = (
    "https://site.web.api.espn.com/apis/site/v2/sports/cricket/8676"
)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}
SLEEP_BETWEEN_PAGES = 0.5


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_match_summary(match_id: str) -> dict:
    url = f"{API_BASE}/summary?event={match_id}"
    return _fetch_json(url)


def fetch_all_commentary(match_id: str) -> list[dict]:
    """Fetch every page of playbyplay commentary."""
    page = 1
    all_items: list[dict] = []
    total_pages = None

    while True:
        url = f"{API_BASE}/playbyplay?event={match_id}&page={page}"
        print(f"  Fetching page {page}" + (f"/{total_pages}" if total_pages else "") + "...")

        try:
            data = _fetch_json(url)
        except urllib.error.HTTPError as e:
            print(f"  HTTP {e.code} on page {page} — stopping.")
            break

        comm = data.get("commentary", {})
        items = comm.get("items", [])
        total_pages = comm.get("pageCount", total_pages)

        if not items:
            break

        all_items.extend(items)
        print(f"    Got {len(items)} items (total so far: {len(all_items)})")

        if total_pages and page >= total_pages:
            break

        page += 1
        time.sleep(SLEEP_BETWEEN_PAGES)

    return all_items


def extract_match_info(summary: dict) -> dict:
    """Pull match header info from the summary API."""
    info: dict = {}

    header = summary.get("header", {})
    comps = header.get("competitions", [{}])
    comp = comps[0] if comps else {}
    info["name"] = header.get("name", "")
    info["description"] = header.get("description", "")
    info["short_name"] = header.get("shortName", "")

    venue = summary.get("gameInfo", {}).get("venue", {})
    info["venue"] = venue.get("fullName", "")
    info["city"] = venue.get("address", {}).get("city", "")

    notes = summary.get("notes", [])
    for note in notes:
        ntype = note.get("type", "")
        if ntype == "toss":
            info["toss"] = note.get("text", "")
        elif ntype == "matchdays":
            info["date"] = note.get("text", "")
        elif ntype == "season":
            info["season"] = note.get("text", "")
        elif ntype == "matchnumber":
            info["match_number"] = note.get("text", "")

    teams = []
    for comp_team in comp.get("competitors", []):
        t = comp_team.get("team", {})
        score = comp_team.get("score", "")
        teams.append({
            "name": t.get("displayName", ""),
            "abbr": t.get("abbreviation", ""),
            "score": score,
            "winner": comp_team.get("winner", False),
        })
    info["teams"] = teams

    status = comp.get("status", {})
    status_type = status.get("type", {})
    info["result"] = (
        status.get("summary", "")
        or status_type.get("shortDetail", "")
        or status_type.get("detail", "")
    )
    info["state"] = status_type.get("state", "")

    return info


def classify_play_type(item: dict) -> str:
    """Determine event type from the item."""
    pt = item.get("playType", {}).get("description", "").lower()
    short = (item.get("shortText") or "").upper()
    dismissal = item.get("dismissal", {})

    if dismissal.get("dismissal"):
        return "WICKET"
    if "OUT" in short:
        return "WICKET"
    if pt == "six" or "SIX" in short:
        return "SIX"
    if pt == "four" or "FOUR" in short:
        return "FOUR"
    if "wide" in pt or "WIDE" in short:
        return "WIDE"
    if "no ball" in pt or "NO BALL" in short:
        return "NO_BALL"
    if "leg bye" in pt or "LEG BYE" in short:
        return "LEG_BYE"
    if "bye" in pt:
        return "BYE"
    if pt == "no run" or "no run" in short.lower():
        return "DOT"

    run_m = re.search(r"(\d+)\s*run", pt)
    if not run_m:
        run_m = re.search(r"(\d+)\s*RUN", short)
    if run_m:
        n = int(run_m.group(1))
        return {1: "SINGLE", 2: "TWO", 3: "THREE"}.get(n, f"{n}_RUNS")

    score_val = item.get("scoreValue", 0)
    if score_val == 0:
        return "DOT"
    if score_val == 1:
        return "SINGLE"
    if score_val == 2:
        return "TWO"
    if score_val == 3:
        return "THREE"
    return "OTHER"


def _strip_html(text: str) -> str:
    """Remove HTML tags from commentary text."""
    return re.sub(r"<[^>]+>", "", text)


def build_ball_entries(items: list[dict]) -> list[dict]:
    """Convert raw API items into structured ball entries."""
    entries: list[dict] = []

    for item in items:
        short = item.get("shortText") or ""
        text = _strip_html(item.get("text") or "")
        pre = _strip_html(item.get("preText") or "")

        over_info = item.get("over", {})
        overs = over_info.get("overs", 0)
        over_num = over_info.get("number", 0)
        ball_num = over_info.get("ball", 0)

        innings_info = item.get("innings", {})
        innings_num = innings_info.get("number", item.get("period", 0))
        total_score = innings_info.get("totalRuns", 0)
        total_wickets = innings_info.get("wickets", 0)

        batsman = item.get("batsman", {})
        bat_athlete = batsman.get("athlete", {})
        bowler = item.get("bowler", {})
        bowl_athlete = bowler.get("athlete", {})

        event = classify_play_type(item)
        score_val = item.get("scoreValue", 0)

        dismissal = item.get("dismissal", {})
        dismissal_text = ""
        if dismissal.get("dismissal"):
            d_bat = dismissal.get("batsman", {}).get("athlete", {})
            dismissal_text = dismissal.get("text", "")
            if not dismissal_text:
                dismissal_text = f"{d_bat.get('displayName', '?')} {dismissal.get('type', '')}"

        entry = {
            "innings": innings_num,
            "over": over_num,
            "ball": ball_num,
            "overs": overs,
            "over_ball": f"{over_num}.{ball_num}" if over_num else str(overs),
            "bowler": bowl_athlete.get("displayName", ""),
            "batter": bat_athlete.get("displayName", ""),
            "event": event,
            "runs": score_val,
            "short_text": short,
            "commentary": text,
            "pre_text": pre,
            "score": f"{total_score}/{total_wickets}",
            "innings_runs": total_score,
            "innings_wickets": total_wickets,
            "innings_balls": innings_info.get("balls", 0),
            "bat_runs": batsman.get("totalRuns", 0),
            "bat_balls": batsman.get("faced", 0),
            "bat_fours": batsman.get("fours", 0),
            "bat_sixes": batsman.get("sixes", 0),
            "bowl_overs": bowler.get("overs", 0),
            "bowl_runs": bowler.get("conceded", 0),
            "bowl_wickets": bowler.get("wickets", 0),
            "bowl_maidens": bowler.get("maidens", 0),
            "dismissal": dismissal_text,
            "dismissal_type": dismissal.get("type", ""),
        }
        entries.append(entry)

    return entries


def save_markdown(match_info: dict, entries: list[dict], filename: str):
    """Save full commentary to a structured markdown file."""
    entries.sort(key=lambda x: (x["innings"], x.get("innings_balls", 0)))

    teams = match_info.get("teams", [])
    team_names = [t["name"] for t in teams]
    team_scores = [f"{t['name']} {t['score']}" for t in teams]

    total_balls = len([e for e in entries if e["batter"]])
    fours = sum(1 for e in entries if e["event"] == "FOUR")
    sixes = sum(1 for e in entries if e["event"] == "SIX")
    wickets = sum(1 for e in entries if e["event"] == "WICKET")
    dots = sum(1 for e in entries if e["event"] == "DOT")

    event_icon = {
        "FOUR": "4",
        "SIX": "6",
        "WICKET": "W",
        "DOT": ".",
        "WIDE": "wd",
        "NO_BALL": "nb",
        "LEG_BYE": "lb",
        "BYE": "b",
        "SINGLE": "1",
        "TWO": "2",
        "THREE": "3",
        "OTHER": "?",
    }

    with open(filename, "w") as f:
        f.write(f"# {match_info.get('name') or match_info.get('description', 'Match Commentary')}\n\n")
        f.write(f"**{match_info.get('date', '')}**\n\n")
        f.write(f"**Venue:** {match_info.get('venue', '?')}, {match_info.get('city', '')}\n\n")
        if match_info.get("toss"):
            f.write(f"**Toss:** {match_info['toss']}\n\n")
        f.write(f"**Result:** {match_info.get('result', '?')}\n\n")
        for ts in team_scores:
            f.write(f"- {ts}\n")
        f.write("\n---\n\n")

        f.write(f"**Total deliveries:** {total_balls} | ")
        f.write(f"**4s:** {fours} | **6s:** {sixes} | ")
        f.write(f"**Wickets:** {wickets} | **Dots:** {dots}\n\n")
        f.write("---\n\n")

        current_innings = None
        current_over = None

        for entry in entries:
            inn = entry["innings"]
            over_num = entry["over"]

            if inn != current_innings:
                current_innings = inn
                current_over = None
                inn_team = team_names[inn - 1] if inn <= len(team_names) else f"Team {inn}"
                f.write(f"\n## Innings {inn} — {inn_team}\n\n")

            if over_num != current_over and over_num > 0:
                current_over = over_num
                f.write(f"\n### Over {over_num}\n\n")

            if not entry["batter"] and entry.get("pre_text"):
                f.write(f"> {entry['pre_text'][:300]}\n\n")
                continue

            if not entry["batter"]:
                continue

            ev = event_icon.get(entry["event"], "?")
            ob = entry["over_ball"]
            bowler = entry["bowler"]
            batter = entry["batter"]
            short = entry["short_text"]
            comm = entry["commentary"]
            score = entry["score"]

            line = f"**{ob}** `[{ev}]` {bowler} to {batter}"
            if entry["event"] == "WICKET":
                line += f" — **{short}**"
                if entry["dismissal"]:
                    line += f"\\\n> *{entry['dismissal']}*"
            else:
                line += f", **{short.split(', ')[-1] if ', ' in short else short}**"

            if comm:
                line += f"\\\n{comm}"

            line += f"  \n*{score} ({entry['innings_balls']}b) | "
            line += f"{batter} {entry['bat_runs']}({entry['bat_balls']}) | "
            line += f"{bowler} {entry['bowl_wickets']}-{entry['bowl_runs']}({entry['bowl_overs']})*\n\n"

            f.write(line)

        f.write("\n---\n\n")
        f.write(f"*Scraped from ESPNcricinfo via ESPN API. {total_balls} deliveries across {len(set(e['innings'] for e in entries))} innings.*\n")

    print(f"\nSaved {total_balls} deliveries to {filename}")


def save_json(entries: list[dict], filename: str):
    """Save raw JSON for programmatic use."""
    with open(filename, "w") as f:
        json.dump(entries, f, indent=2)
    print(f"Saved {len(entries)} entries to {filename}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scrape_commentary.py <match_id> [output.md]")
        print("Example: python scrape_commentary.py 1512773")
        sys.exit(1)

    match_id = sys.argv[1]
    output_md = sys.argv[2] if len(sys.argv) > 2 else f"commentary_{match_id}.md"
    output_json = output_md.replace(".md", ".json")

    print(f"Scraping match {match_id}...")
    print()

    print("[1/3] Fetching match summary...")
    try:
        summary = fetch_match_summary(match_id)
        match_info = extract_match_info(summary)
        print(f"  Match: {match_info.get('name', '?')}")
        print(f"  Result: {match_info.get('result', '?')}")
        for t in match_info.get("teams", []):
            print(f"  {t['name']}: {t['score']}")
    except Exception as e:
        print(f"  Warning: couldn't fetch summary ({e}). Continuing...")
        match_info = {"name": f"Match {match_id}"}

    print()
    print("[2/3] Fetching ball-by-ball commentary...")
    raw_items = fetch_all_commentary(match_id)
    print(f"  Total raw items: {len(raw_items)}")

    if not raw_items:
        print("\nNo commentary found. The match may not have started yet,")
        print("or the match ID may be incorrect.")
        sys.exit(1)

    entries = build_ball_entries(raw_items)
    ball_entries = [e for e in entries if e["batter"]]
    print(f"  Ball entries: {len(ball_entries)}")

    innings_set = set(e["innings"] for e in ball_entries)
    for inn in sorted(innings_set):
        inn_balls = [e for e in ball_entries if e["innings"] == inn]
        print(f"  Innings {inn}: {len(inn_balls)} balls")

    print()
    print("[3/3] Saving output...")
    save_markdown(match_info, entries, output_md)
    save_json(entries, output_json)

    print()
    print("Sample (first 5 balls):")
    for entry in ball_entries[:5]:
        print(f"  {entry['over_ball']} {entry['bowler']} to {entry['batter']}: {entry['short_text']}")

    print()
    print("Sample (last 5 balls):")
    for entry in ball_entries[-5:]:
        print(f"  {entry['over_ball']} {entry['bowler']} to {entry['batter']}: {entry['short_text']}")


if __name__ == "__main__":
    main()
