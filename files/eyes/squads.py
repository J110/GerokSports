"""Squad loading — fetch any URL, use LLM to extract squads.

User pastes a URL (Cricbuzz, ESPNcricinfo, IPL official, anything).
System fetches the page, feeds text to an LLM agent, gets structured
squad data back. Works with any cricket site.
"""
from __future__ import annotations

import json

import httpx
from bs4 import BeautifulSoup

from eyes.config import GROQ_API_KEY, GROQ_PRIMARY_MODEL
from eyes.cricket_logger import CricketLogger

log = CricketLogger("SQUAD")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

SQUAD_PROMPT = """\
You are extracting cricket match squad information from a webpage.

PAGE CONTENT:
{page_text}

Extract the following into JSON:
{{
  "team_a": {{
    "name": "<full team name>",
    "short": "<abbreviation like CSK, MI, ENG, WI>",
    "playing_xi": ["Full Player Name", ...],
    "impact_subs": ["Full Player Name", ...]
  }},
  "team_b": {{
    "name": "<full team name>",
    "short": "<abbreviation>",
    "playing_xi": ["Full Player Name", ...],
    "impact_subs": ["Full Player Name", ...]
  }},
  "toss": {{
    "winner": "<team name>",
    "decision": "bat|bowl"
  }},
  "venue": "<stadium name, city>",
  "format": "T20|ODI|Test"
}}

Rules:
- Extract FULL player names (first + last), not just surnames.
- playing_xi should have exactly 11 players per team.
- impact_subs are extras beyond the XI (0-5 per team). Omit if none.
- If toss info not available, set toss to null.
- If any field isn't on the page, set it to null.
- JSON only. No explanation.\
"""


async def scrape_squads_from_url(url: str) -> dict | None:
    """Fetch any URL, extract text, use LLM to get squad data."""
    log.info(f"Fetching: {url}")

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml",
            })
            resp.raise_for_status()
            html = resp.text

    except Exception as e:
        log.error(f"Failed to fetch URL: {e}")
        return None

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "iframe"]):
        tag.decompose()
    page_text = soup.get_text("\n", strip=True)

    # Truncate to fit in LLM context — keep first ~6000 chars
    # which should cover squads, toss, venue on any cricket site
    if len(page_text) > 6000:
        page_text = page_text[:6000]

    log.info(f"Page text: {len(page_text)} chars. Sending to LLM...")

    prompt = SQUAD_PROMPT.format(page_text=page_text)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{GROQ_BASE_URL}/chat/completions",
                json={
                    "model": GROQ_PRIMARY_MODEL,
                    "max_tokens": 800,
                    "temperature": 0,
                    "messages": [{"role": "user", "content": prompt}],
                },
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
            return _parse_json(raw)

    except Exception as e:
        log.error(f"LLM squad extraction failed: {e}")
        return None


def _parse_json(raw: str) -> dict | None:
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
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        log.error(f"JSON parse failed: {text[:300]}")
        return None


def build_name_lookup(players: list[str]) -> dict[str, str]:
    """Map every plausible broadcast variant to the canonical full name."""
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
            lookup[f"{first} {last}"] = full

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


async def load_squads_from_url(url: str) -> tuple[dict | None, dict[str, list[str]]]:
    """Fetch URL, extract squads via LLM, return (raw_data, squads_dict).

    squads_dict: {"Team A": ["Player 1", ...], "Team B": [...]}
    """
    data = await scrape_squads_from_url(url)
    if not data:
        return None, {}

    squads: dict[str, list[str]] = {}
    for key in ("team_a", "team_b"):
        team = data.get(key, {})
        if not team:
            continue
        name = team.get("short") or team.get("name", "Unknown")
        xi = team.get("playing_xi", [])
        subs = team.get("impact_subs", [])
        all_players = xi + (subs or [])
        if all_players:
            squads[name] = all_players
            log.info(f"  {name}: {len(xi)} XI + {len(subs or [])} subs")
            for p in all_players:
                log.info(f"    - {p}")

    return data, squads
