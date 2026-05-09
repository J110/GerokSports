"""Squad scraper — parse Cricbuzz squad pages with BeautifulSoup.

Extracts both teams, playing XI, bench/impact subs, roles, captain, keeper.
Builds name lookup table and empty scorecards.

Cricbuzz structure:
  Team A (left):  <a> tags with 'border-r-2' in class
  Team B (right): <a> tags with 'justify-end' in class
  Playing XI first, then bench (separated by section headers)
  Player text: "Name(C)Role" e.g. "Rovman Powell(C)Batter"
"""
from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

from eyes.cricket_logger import CricketLogger

log = CricketLogger("SQUAD")

ROLES = [
    "Batting Allrounder",
    "Bowling Allrounder",
    "WK-Batter",
    "Batter",
    "Bowler",
]

ROLE_PATTERN = re.compile(
    r"(Batting Allrounder|Bowling Allrounder|WK-Batter|Batter|Bowler)$"
)

STAFF_PATTERN = re.compile(
    r"(Head [Cc]oach|Head of|Assistant [Cc]oach|Team Manager|Manager|"
    r"Physiotherapist|Physio|Analyst|Batting [Cc]oach|Bowling [Cc]oach|"
    r"Fielding [Cc]oach|Wicket-?keeping [Cc]oach|Spin [Cc]oaching?|"
    r"Fast Bowling [Cc]oach|Lead Assistant|Selector|Trainer|Director|"
    r"Mentor|Support Staff|Spin Bowling [Cc]oach|Strategic Advisor|"
    r"Consultant|Performance [Cc]oach|Video Analyst|"
    r"Scouting|Scout|Strength|Doctor|Medical)",
    re.IGNORECASE,
)


def _parse_player_text(text: str) -> dict:
    """Parse 'Rovman Powell(C)Batter' into structured player data."""
    text = text.strip()

    captain = "(C)" in text or "(C &" in text or "(C/" in text
    keeper = "(WK)" in text or "& WK)" in text or "C/WK)" in text
    text = re.sub(r"\(C\s*[&/]\s*WK\)", "", text)
    text = text.replace("(C)", "").replace("(WK)", "").replace("(C/WK)", "")
    text = text.strip()

    role = "unknown"
    name = text
    m = ROLE_PATTERN.search(text)
    if m:
        role = m.group(1)
        name = text[:m.start()].strip()

    role_map = {
        "Batter": "batter",
        "Bowler": "bowler",
        "Batting Allrounder": "bat_allrounder",
        "Bowling Allrounder": "bowl_allrounder",
        "WK-Batter": "wk_batter",
    }
    role = role_map.get(role, role)

    return {
        "name": name,
        "role": role,
        "captain": captain,
        "keeper": keeper or role == "wk_batter",
    }


def _is_team_a(classes: list[str]) -> bool:
    return "border-r-2" in classes


def _is_team_b(classes: list[str]) -> bool:
    return "justify-end" in classes


def _is_section_start(classes: list[str]) -> bool:
    return "border-t" in classes


async def scrape_cricbuzz_squads(url: str) -> dict | None:
    """Scrape a Cricbuzz squad page and return structured data.

    Returns:
    {
        "team_a": {"name": "WI", "full_name": "West Indies",
                   "playing_xi": [...], "bench": [...]},
        "team_b": {"name": "ENG", "full_name": "England",
                   "playing_xi": [...], "bench": [...]},
        "venue": "...", "format": "T20"
    }
    """
    log.info(f"Fetching: {url}")

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml",
            })
            resp.raise_for_status()
    except Exception as e:
        log.error(f"Failed to fetch URL: {e}")
        return None

    soup = BeautifulSoup(resp.text, "lxml")

    # Extract team names from h1 tags or page title
    team_names = _extract_team_names(soup, url)

    # Find all player links (both teams, both sections)
    player_links = soup.find_all(
        "a", href=lambda h: h and "/profiles/" in h,
        class_=lambda c: c and ("border-r-2" in c or "justify-end" in c)
    )

    if not player_links:
        log.error("No player links found — page structure may have changed")
        return None

    # Split into teams and sections
    team_a_xi, team_a_bench = [], []
    team_b_xi, team_b_bench = [], []

    a_section = "xi"
    b_section = "xi"

    for link in player_links:
        classes = link.get("class", [])
        text = link.get_text(strip=True)
        player = _parse_player_text(text)

        is_a = _is_team_a(classes)
        is_b = _is_team_b(classes)
        starts_section = _is_section_start(classes)

        # Filter out coaching staff (their text has no player role)
        # Also catches concatenated name+role like "NameHead of Scouting"
        if STAFF_PATTERN.search(text):
            continue
        if player.get("role") == "unknown" and STAFF_PATTERN.search(player.get("name", "")):
            continue

        # Tag impact subs
        if "bg-cbAntiFlash" in classes:
            player["impact_sub"] = True  # subbed INTO XI
        elif "bg-pink-50" in classes:
            player["impact_sub"] = True  # subbed OUT of XI
            player["subbed_out"] = True

        if is_a:
            if starts_section and team_a_xi:
                a_section = "bench"
            if a_section == "xi":
                team_a_xi.append(player)
            else:
                team_a_bench.append(player)

        elif is_b:
            if starts_section and team_b_xi:
                b_section = "bench"
            if b_section == "xi":
                team_b_xi.append(player)
            else:
                team_b_bench.append(player)

    # Extract venue from page
    venue = _extract_venue(soup)
    fmt = _extract_format(url)

    result = {
        "team_a": {
            "name": team_names[0] if team_names else "Team A",
            "full_name": team_names[0] if team_names else "Team A",
            "playing_xi": team_a_xi,
            "bench": team_a_bench,
        },
        "team_b": {
            "name": team_names[1] if len(team_names) > 1 else "Team B",
            "full_name": team_names[1] if len(team_names) > 1 else "Team B",
            "playing_xi": team_b_xi,
            "bench": team_b_bench,
        },
        "venue": venue,
        "format": fmt,
    }

    _log_squads(result)
    return result


def _extract_team_names(soup: BeautifulSoup, url: str) -> list[str]:
    """Extract team abbreviations from the page."""
    # Try page title first: "West Indies vs England, 5th T20I..."
    title = soup.find("title")
    if title:
        title_text = title.get_text(strip=True)
        # "Cricket match squads | West Indies vs England, 5th T20I..."
        if " vs " in title_text:
            parts = title_text.split("|")[-1].strip() if "|" in title_text else title_text
            vs_part = parts.split(",")[0].strip()
            if " vs " in vs_part:
                teams = vs_part.split(" vs ")
                return [t.strip() for t in teams[:2]]

    # Fallback: parse from URL slug "wi-vs-eng-5th-t20i..."
    slug = url.rstrip("/").split("/")[-1]
    if "-vs-" in slug:
        parts = slug.split("-vs-")
        a = parts[0].split("/")[-1].upper()
        b = parts[1].split("-")[0].upper()
        return [a, b]

    return []


def _extract_venue(soup: BeautifulSoup) -> str | None:
    """Try to find venue info on the page."""
    for text_elem in soup.find_all(string=re.compile(r"Stadium|Ground|Oval|Park|Arena")):
        parent = text_elem.parent
        if parent:
            full = parent.get_text(strip=True)
            if len(full) < 120:
                return full
    return None


def _extract_format(url: str) -> str:
    slug = url.lower()
    if "t20" in slug:
        return "T20"
    if "odi" in slug or "one-day" in slug:
        return "ODI"
    if "test" in slug:
        return "Test"
    if "ipl" in slug or "premier-league" in slug:
        return "T20"
    return "T20"


def _log_squads(data: dict):
    for key in ("team_a", "team_b"):
        team = data[key]
        xi = team["playing_xi"]
        bench = team["bench"]
        log.info(f"  {team['name']}: {len(xi)} XI + {len(bench)} bench")
        for p in xi:
            tags = []
            if p["captain"]:
                tags.append("C")
            if p["keeper"]:
                tags.append("WK")
            tag_str = f" ({','.join(tags)})" if tags else ""
            log.info(f"    {p['name']}{tag_str} — {p['role']}")
        for p in bench:
            log.info(f"    [bench] {p['name']} — {p['role']}")


# ------------------------------------------------------------------
# Name lookup table
# ------------------------------------------------------------------

def build_name_lookup(players: list[str]) -> dict[str, str]:
    """Map every broadcast variant to the canonical full name."""
    lookup: dict[str, str] = {}
    for full in players:
        parts = full.strip().split()
        if not parts:
            continue
        up = full.upper().strip()
        lookup[up] = full

        if len(parts) >= 2:
            last = parts[-1].upper()
            first = parts[0].upper()
            lookup[last] = full
            lookup[f"{first[0]} {last}"] = full
            lookup[f"{first[0]}. {last}"] = full
            lookup[f"{last} {first[0]}"] = full

            if len(parts) == 3:
                middle = parts[1].upper()
                lookup[f"{first[0]} {middle[0]} {last}"] = full
                lookup[f"{middle} {last}"] = full

    return lookup


def resolve_name(broadcast_name: str, lookup: dict[str, str]) -> str | None:
    """Resolve a broadcast name against the lookup table."""
    up = broadcast_name.upper().strip()
    for suffix in ("(C)", "(WK)", "(C/WK)", "(IMP)", "(WK/C)"):
        up = up.replace(suffix, "").strip()
    if up in lookup:
        return lookup[up]
    for key, canonical in lookup.items():
        if len(up) >= 4 and len(key) >= 4:
            if key.startswith(up) or up.startswith(key):
                return canonical
    return None


def try_split_merged(broadcast_name: str, lookup: dict[str, str]) -> list[str] | None:
    """Try to split 'KING POWELL' into two known players."""
    up = broadcast_name.upper().strip()
    words = up.split()
    if len(words) < 2:
        return None
    for i in range(1, len(words)):
        left = " ".join(words[:i])
        right = " ".join(words[i:])
        left_match = resolve_name(left, lookup)
        right_match = resolve_name(right, lookup)
        if left_match and right_match and left_match != right_match:
            return [left_match, right_match]
    return None


# ------------------------------------------------------------------
# Convert scraped data to pipeline format
# ------------------------------------------------------------------

def squads_to_pipeline_format(data: dict) -> tuple[dict, dict[str, list[str]]]:
    """Convert scraped data to the format main.py expects.

    Returns: (raw_data, {"TeamA": [names], "TeamB": [names]})
    """
    squads: dict[str, list[str]] = {}

    for key in ("team_a", "team_b"):
        team = data[key]
        name = team["name"]
        xi_names = [p["name"] for p in team["playing_xi"]]
        bench_names = [p["name"] for p in team["bench"]]
        squads[name] = xi_names + bench_names

    return data, squads


def squad_membership_by_team_name(data: dict) -> dict[str, dict[str, list[str]]]:
    """Expose playing XI and bench per Cricbuzz team name (P11 tests)."""
    out: dict[str, dict[str, list[str]]] = {}
    for key in ("team_a", "team_b"):
        team = data[key]
        out[team["name"]] = {
            "xi": [p["name"] for p in team.get("playing_xi", [])],
            "subs": [p["name"] for p in team.get("bench", [])],
        }
    return out


def format_squad_roles(data: dict, team_key: str) -> str:
    """Format squad with positions and roles for the scorer prompt.

    e.g. '1. Brandon King — batter'
         '2. Johnson Charles — wk_batter (WK)'
         '6. Rovman Powell — batter (C)'
    """
    team = data.get(team_key, {})
    lines: list[str] = []
    for i, p in enumerate(team.get("playing_xi", []), 1):
        tags = []
        if p.get("captain"):
            tags.append("C")
        if p.get("keeper"):
            tags.append("WK")
        tag_str = f" ({','.join(tags)})" if tags else ""
        lines.append(f"  {i:2}. {p['name']} — {p['role']}{tag_str}")
    for p in team.get("bench", []):
        lines.append(f"  sub. {p['name']} — {p['role']}")
    return "\n".join(lines) if lines else "  (unknown)"
