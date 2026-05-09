"""Player style enrichment — batting handedness + bowling arm/style.

After the squad is scraped from Cricbuzz we know the players but not
how they bat (RHB/LHB) or how they bowl (Right-arm fast / Slow
left-arm orthodox / etc.).  Doing this once per match and caching it
is much cheaper than having the live delivery classifier guess from
the camera frame every ball — and much more accurate, because we
ground it in the actual player identity rather than pixels.

Two LLM passes (Groq, OpenAI-compatible chat completions):

1. Pass 1 — infer
   Plain Groq chat call (no tools) against a capable text model
   (default `llama-3.3-70b-versatile`).  Takes the squad JSON and
   infers batting_style + bowling_style for every player from the
   model's prior knowledge.  Fast, cheap, often right but
   occasionally wrong or "unknown".

2. Pass 2 — verify
   Groq `groq/compound` agentic system, which has built-in web
   search (Tavily-powered).  Double-checks the inferred styles
   against live web data (ESPNcricinfo, Cricbuzz profiles, official
   team sites, Wikipedia).  Corrects whatever was wrong and fills in
   the "unknown"s.

Both calls produce the same schema:

    {
      "Rovman Powell":  {"batting_style": "RHB",
                         "bowling_style": "Right-arm medium"},
      "Gudakesh Motie": {"batting_style": "LHB",
                         "bowling_style": "Slow left-arm orthodox"},
      ...
    }

Results are merged back into `raw_data["team_a|team_b"]["playing_xi"
| "bench"]` as two new keys on each player dict and also persisted
to `data/commentary/player_styles_<slug>.json` so a restart of the
pipeline during the same match doesn't re-spend the LLM budget.

`batting_style` is always one of: "RHB", "LHB", "unknown".
`bowling_style` is a free-text English phrase (lowercased, hyphens
allowed) or "None" for pure batters / "unknown" when we have no
evidence.  The UI just renders the string verbatim beside the
batter / bowler row.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

from eyes.config import GROQ_API_KEY
from eyes.cricket_logger import CricketLogger

log = CricketLogger("ENRICH")


# Pass 1 (infer): a plain Groq text model.  llama-3.3-70b-versatile
# has stronger prior knowledge of named cricketers than scout-17b, and
# enrichment only fires once per match (then caches), so the 70B cost
# is negligible.
# Pass 2 (verify): groq/compound, Groq's agentic system with built-in
# web search — this is the equivalent of "Gemini + Google Search"
# grounding for correctness.
ENRICH_MODEL = os.environ.get(
    "PLAYER_ENRICHMENT_MODEL", "llama-3.3-70b-versatile")
VERIFY_MODEL = os.environ.get(
    "PLAYER_VERIFICATION_MODEL", "groq/compound")

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "commentary"


BATTING_VOCAB = {"RHB", "LHB", "unknown"}


# ── cache helpers ────────────────────────────────────────────────────

def _cache_key(raw_data: dict) -> str:
    """Stable hash of (team names + playing XI + bench) so minor
    rescrapes hit the same cache entry but an actual squad change
    invalidates it."""
    payload = []
    for key in ("team_a", "team_b"):
        team = raw_data.get(key) or {}
        payload.append(team.get("name", ""))
        for section in ("playing_xi", "bench"):
            for p in team.get(section, []) or []:
                payload.append(p.get("name", ""))
    digest = hashlib.sha1("|".join(payload).encode()).hexdigest()[:12]
    return digest


def _cache_path(raw_data: dict) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"player_styles_{_cache_key(raw_data)}.json"


def _load_cache(raw_data: dict) -> dict | None:
    p = _cache_path(raw_data)
    if not p.exists():
        return None
    try:
        cached = json.loads(p.read_text())
        if not isinstance(cached, dict):
            return None
        log.info(f"Loaded cached styles from {p.name} "
                 f"({len(cached)} players)")
        return cached
    except Exception as e:  # noqa: BLE001
        log.warn(f"Cache read failed ({p.name}): {e}")
        return None


def _save_cache(raw_data: dict, styles: dict):
    p = _cache_path(raw_data)
    try:
        p.write_text(json.dumps(styles, indent=2))
        log.info(f"Saved styles to {p.name}")
    except Exception as e:  # noqa: BLE001
        log.warn(f"Cache write failed ({p.name}): {e}")


# ── squad helpers ────────────────────────────────────────────────────

def _all_players(raw_data: dict) -> list[dict]:
    """Flat list of player dicts across both teams, both sections,
    annotated with the team/section they came from so we can format
    a clean prompt."""
    out: list[dict] = []
    for key in ("team_a", "team_b"):
        team = raw_data.get(key) or {}
        team_name = team.get("name", key)
        for section in ("playing_xi", "bench"):
            for p in team.get(section, []) or []:
                if not p.get("name"):
                    continue
                out.append({
                    "team": team_name,
                    "section": section,
                    "name": p["name"],
                    "role": p.get("role", "unknown"),
                })
    return out


def _format_squad_prompt(players: list[dict]) -> str:
    lines: list[str] = []
    current_team: str | None = None
    current_section: str | None = None
    for p in players:
        if p["team"] != current_team:
            current_team = p["team"]
            current_section = None
            lines.append(f"\nTeam: {current_team}")
        if p["section"] != current_section:
            current_section = p["section"]
            lines.append(f"  [{current_section}]")
        lines.append(f"    - {p['name']} (role: {p['role']})")
    return "\n".join(lines)


def _merge_styles_into_raw(raw_data: dict, styles: dict):
    """Write batting_style / bowling_style onto each player dict."""
    for key in ("team_a", "team_b"):
        team = raw_data.get(key) or {}
        for section in ("playing_xi", "bench"):
            for p in team.get(section, []) or []:
                name = p.get("name")
                if not name:
                    continue
                s = styles.get(name) or {}
                p["batting_style"] = _clean_batting(
                    s.get("batting_style"))
                p["bowling_style"] = _clean_bowling(
                    s.get("bowling_style"))


def _clean_batting(v) -> str:
    if not isinstance(v, str):
        return "unknown"
    up = v.strip().upper().replace("-", "").replace(" ", "")
    if up in ("RHB", "RIGHTHAND", "RIGHTHANDED",
              "RIGHTHANDBAT", "RIGHTHANDBATTER"):
        return "RHB"
    if up in ("LHB", "LEFTHAND", "LEFTHANDED",
              "LEFTHANDBAT", "LEFTHANDBATTER"):
        return "LHB"
    return "unknown"


def _clean_bowling(v) -> str:
    if not isinstance(v, str):
        return "unknown"
    s = v.strip()
    if not s:
        return "unknown"
    if s.lower() in ("none", "n/a", "na", "does not bowl",
                     "doesn't bowl", "non-bowler", "pure batter"):
        return "None"
    if s.lower() in ("unknown", "?"):
        return "unknown"
    # Keep as-is, trim whitespace.
    return re.sub(r"\s+", " ", s)


# ── Groq client (async) ──────────────────────────────────────────────

def _make_client():
    try:
        from groq import AsyncGroq
        # Pass-2 calls groq/compound with web-search fan-out.  Production
        # data (3/3 sessions on 2026-04-25) showed every call exceeding
        # 90 s, and SDK default max_retries=2 turned that into a
        # deterministic 271 s budget burn (3 attempts × 90 s) with zero
        # successes.  Single-shot 240 s is shorter wall-clock than the
        # old 3-attempt budget AND actually fits compound's prod latency.
        # max_retries=0 disables SDK auto-retry: Pass-2 runs background-
        # async with graceful Pass-1 fallback, so a second SDK attempt
        # only triples wall-clock cost without changing failure semantics.
        # See backlog "P1: Pass-2 enrichment retry/timeout policy".
        return AsyncGroq(api_key=GROQ_API_KEY, timeout=240.0, max_retries=0)
    except Exception as e:  # noqa: BLE001
        log.error(f"Groq SDK init failed: {e}")
        return None


def _extract_json_blob(raw: str) -> dict | None:
    if not raw:
        return None
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not m:
        return None
    blob = m.group(0)
    try:
        parsed = json.loads(blob)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        for i in range(len(blob), 0, -1):
            if blob[i - 1] == "}":
                try:
                    parsed = json.loads(blob[:i])
                    return parsed if isinstance(parsed, dict) else None
                except json.JSONDecodeError:
                    continue
    return None


INFER_PROMPT = """\
You are a cricket reference librarian.  Given the squads below,
return your best guess of each player's batting handedness and
bowling style based on your prior knowledge of the player.

For EVERY player (both playing XI and bench, both teams) return:
  "batting_style":  "RHB"  (right-hand batsman)
                  | "LHB"  (left-hand batsman)
                  | "unknown"  (you genuinely don't know)
  "bowling_style":  a short English phrase like
                    "Right-arm fast"
                    "Right-arm medium-fast"
                    "Right-arm medium"
                    "Right-arm off-spin"
                    "Right-arm legbreak"
                    "Right-arm legbreak googly"
                    "Left-arm fast"
                    "Left-arm medium"
                    "Slow left-arm orthodox"
                    "Left-arm wrist-spin (chinaman)"
                  | "None"  (the player does not bowl at all)
                  | "unknown" (you don't know)

"unknown" is ALWAYS acceptable and preferred over a confident wrong
guess.  Do not make up styles you are not sure of — the next stage
of the pipeline will look up uncertain answers on the web.

Return ONLY a single JSON object keyed by the player's full name
EXACTLY as given below (spelling, spacing, punctuation, accents all
preserved).  Every player must appear as a key.  No extra keys, no
markdown fences, no explanation.

Example shape:
{
  "Rovman Powell":  {"batting_style": "RHB", "bowling_style": "Right-arm medium"},
  "Gudakesh Motie": {"batting_style": "LHB", "bowling_style": "Slow left-arm orthodox"},
  "Phil Salt":      {"batting_style": "RHB", "bowling_style": "None"}
}

Squads:
{squads}
"""


VERIFY_PROMPT = """\
You are a cricket reference fact-checker.  Below is a set of
initial guesses of each player's batting handedness and bowling
style.  Some are correct, some are wrong, some are "unknown".

Your job: use web search to look up each player (ESPNcricinfo,
Cricbuzz, official team site, Wikipedia as a last resort) and
return a CORRECTED JSON object.  Fix any style that disagrees with
a reliable source.  Fill in as many "unknown"s as you can confirm.
When a pure batter genuinely does not bowl, use "None" for
bowling_style.  If the web cannot confirm a player's style with
reasonable confidence, leave it as "unknown".

Prefer the TEAM NAMES given below as a disambiguator when multiple
players share a name (e.g. several Mohammad Shami's).

Return ONLY the final corrected JSON object, keyed by the player's
full name EXACTLY as given.  Every player from the initial guesses
must appear as a key.  Use the same value vocabulary:
  batting_style ∈ {"RHB", "LHB", "unknown"}
  bowling_style: short English phrase, "None", or "unknown"
No markdown fences, no prose, no citations inline — just the JSON.

Teams (for disambiguation): {teams}

Initial guesses (JSON):
{guesses}
"""


# ── API-layer helpers ────────────────────────────────────────────────

async def _call_groq_plain(client, prompt: str, model: str) -> str:
    """One-shot chat completion on a plain Groq text model.
    No tools, low temperature for deterministic JSON."""
    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=4000,
    )
    if not resp.choices:
        return ""
    return resp.choices[0].message.content or ""


async def _call_groq_with_search(client, prompt: str, model: str) -> str:
    """Chat completion against Groq's Compound agentic system, which
    transparently runs web searches (Tavily) server-side when it
    decides it needs fresher / more authoritative info.  Caller just
    sees the final synthesised text."""
    # groq/compound doesn't accept temperature overrides on some
    # versions — keep the call minimal.
    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4000,
    )
    if not resp.choices:
        return ""
    return resp.choices[0].message.content or ""


def _fallback_styles(players: list[dict]) -> dict:
    """All-unknown fallback when the LLM is unavailable."""
    out: dict[str, dict] = {}
    for p in players:
        out[p["name"]] = {
            "batting_style": "unknown",
            "bowling_style": ("None"
                              if p.get("role") in ("batter", "wk_batter")
                              else "unknown"),
        }
    return out


def _normalise_styles(raw: dict, players: list[dict]) -> dict:
    """Ensure every player has an entry; clean vocab; drop strays."""
    valid_names = {p["name"] for p in players}
    out: dict[str, dict] = {}
    for name in valid_names:
        s = raw.get(name) if isinstance(raw, dict) else None
        s = s if isinstance(s, dict) else {}
        out[name] = {
            "batting_style": _clean_batting(s.get("batting_style")),
            "bowling_style": _clean_bowling(s.get("bowling_style")),
        }
    return out


# ── public coroutines ────────────────────────────────────────────────

async def _run_pass1(client, raw_data: dict, players: list[str]) -> dict:
    """Pass-1: prior-knowledge guess. Always fast (~1-3s)."""
    t0 = time.time()
    prompt1 = INFER_PROMPT.replace("{squads}", _format_squad_prompt(players))
    try:
        raw1 = await _call_groq_plain(client, prompt1, ENRICH_MODEL)
    except Exception as e:  # noqa: BLE001
        log.error(f"Pass-1 (infer) LLM call failed: {e}")
        raw1 = ""
    parsed1 = _extract_json_blob(raw1) or {}
    pass1 = _normalise_styles(parsed1, players)
    dt1 = (time.time() - t0) * 1000
    log.info(f"Pass-1 (infer) complete in {dt1:.0f}ms "
             f"({sum(1 for s in pass1.values() if s['batting_style'] != 'unknown')}"
             f"/{len(pass1)} known)")
    return pass1


async def _run_pass2(client, raw_data: dict, pass1: dict,
                     players: list[str]) -> dict | None:
    """Pass-2: websearch-grounded verification. Slow (~30s-5min) and may
    time out. Returns the corrected styles dict on success, or None when
    the call failed or the response was unparseable (caller falls back to
    Pass-1)."""
    t1 = time.time()
    teams_str = (
        f"{(raw_data.get('team_a') or {}).get('name', '?')} vs "
        f"{(raw_data.get('team_b') or {}).get('name', '?')}"
    )
    prompt2 = (VERIFY_PROMPT
               .replace("{teams}", teams_str)
               .replace("{guesses}", json.dumps(pass1, indent=2)))
    try:
        raw2 = await _call_groq_with_search(
            client, prompt2, VERIFY_MODEL)
    except Exception as e:  # noqa: BLE001
        log.error(f"Pass-2 (verify) LLM call failed: {e}")
        return None
    parsed2 = _extract_json_blob(raw2)
    if not parsed2:
        # First action item from backlog P2 entry: log the actual
        # response body so the malformed shape is observable.  The
        # four fix candidates (preamble-strip, prompt-tightening,
        # wider extractor, parse-retry) can't be ranked without
        # knowing what `groq/compound` is actually returning.
        # Truncate to keep log size sane on long preambles.
        body_preview = (raw2 or "").replace("\n", "\\n")[:2048]
        body_len = len(raw2 or "")
        log.warn(
            f"Pass-2 returned unparseable JSON — keeping pass-1 styles "
            f"(raw_len={body_len} preview={body_preview!r})"
        )
        return None
    pass2 = _normalise_styles(parsed2, players)
    dt2 = (time.time() - t1) * 1000
    log.info(f"Pass-2 (verify) complete in {dt2:.0f}ms "
             f"({sum(1 for s in pass2.values() if s['batting_style'] != 'unknown')}"
             f"/{len(pass2)} known)")
    corrections = sum(
        1 for n in pass1
        if pass1[n]["batting_style"] != pass2.get(n, {}).get(
            "batting_style")
        or pass1[n]["bowling_style"] != pass2.get(n, {}).get(
            "bowling_style"))
    log.info(f"Pass-2 corrected {corrections} players vs pass-1")
    return pass2


async def enrich_squad_styles(raw_data: dict,
                              use_cache: bool = True,
                              pass2_background: bool = False) -> dict:
    """Infer + verify styles for every player and merge into raw_data.

    Mutates `raw_data` in place and returns the styles dict for
    convenience.  Safe to call when GROQ_API_KEY is missing — in
    that case every player ends up with `unknown` styles and the rest
    of the pipeline continues.

    Modes:
    - ``pass2_background=False`` (default, legacy behaviour): runs Pass-1
      then Pass-2 inline and returns the final (Pass-2 if available, else
      Pass-1) styles. Caller blocks for the full ~3-300s budget. Cache is
      written with the final styles.
    - ``pass2_background=True``: runs Pass-1 inline and returns its styles
      immediately. Pass-2 is *not* started; the caller is expected to
      schedule :func:`enrich_squad_styles_pass2_async` as a background
      task once any downstream sinks (e.g. ``Scoreboard``) exist that
      should be retro-patched when Pass-2 finishes. No cache is written
      in this mode — Pass-2's completion handler owns cache writes so
      that a future restart still benefits from web-grounded styles.
    """
    players = _all_players(raw_data)
    if not players:
        log.warn("No players to enrich")
        return {}

    if use_cache:
        cached = _load_cache(raw_data)
        if cached:
            _merge_styles_into_raw(raw_data, cached)
            _log_styles(raw_data, tag="cache")
            return cached

    client = _make_client()
    if client is None:
        log.warn("Groq SDK unavailable — using unknown-style fallback")
        styles = _fallback_styles(players)
        _merge_styles_into_raw(raw_data, styles)
        return styles

    pass1 = await _run_pass1(client, raw_data, players)

    if pass2_background:
        # Caller will schedule Pass-2 separately. Merge Pass-1 now so the
        # pipeline can use it; Pass-2 will overwrite later via the
        # completion handler.
        _merge_styles_into_raw(raw_data, pass1)
        _log_styles(raw_data, tag="pass1")
        return pass1

    # Legacy synchronous path: run Pass-2 inline.
    pass2 = await _run_pass2(client, raw_data, pass1, players)
    final = pass2 if pass2 is not None else pass1

    _save_cache(raw_data, final)
    _merge_styles_into_raw(raw_data, final)
    _log_styles(raw_data, tag="final")
    return final


async def enrich_squad_styles_pass2_async(
        raw_data: dict,
        pass1_styles: dict,
        on_complete=None) -> dict | None:
    """Run Pass-2 enrichment in the background after Pass-1 already ran.

    Designed to be wrapped in :func:`asyncio.create_task` so the caller
    does not block on it. Mutates ``raw_data`` in place if Pass-2
    succeeds, writes the canonical cache, and (if ``on_complete`` is
    provided) invokes it with the final styles dict so downstream sinks
    (typically a ``Scoreboard`` whose ``batting_card``/``bowling_card``
    were populated using Pass-1) can be retroactively patched.

    On Pass-2 failure (LLM error, timeout, unparseable JSON) the function
    falls back to caching the Pass-1 styles so a restart-during-the-same
    match doesn't re-spend the LLM budget. The completion callback is
    NOT invoked in the failure case — there is nothing new to apply.
    """
    players = _all_players(raw_data)
    if not players:
        return None
    client = _make_client()
    if client is None:
        log.warn("Groq SDK unavailable — Pass-2 background skipped")
        return None
    try:
        pass2 = await _run_pass2(client, raw_data, pass1_styles, players)
    except Exception as e:  # noqa: BLE001
        log.error(f"Pass-2 background task crashed: {e}")
        pass2 = None

    if pass2 is None:
        # Cache Pass-1 so a restart during the same match still benefits
        # from at least the prior-knowledge guess.
        _save_cache(raw_data, pass1_styles)
        log.warn("Pass-2 background failed — cached Pass-1 as fallback")
        return None

    _save_cache(raw_data, pass2)
    _merge_styles_into_raw(raw_data, pass2)
    _log_styles(raw_data, tag="pass2-bg")
    if on_complete is not None:
        try:
            on_complete(pass2)
        except Exception as e:  # noqa: BLE001
            log.error(f"Pass-2 on_complete callback failed: {e}")
    return pass2


def _log_styles(raw_data: dict, tag: str = ""):
    prefix = f"[{tag}] " if tag else ""
    for key in ("team_a", "team_b"):
        team = raw_data.get(key) or {}
        name = team.get("name", key)
        xi = team.get("playing_xi") or []
        log.info(f"{prefix}{name} — styles:")
        for p in xi:
            bat = p.get("batting_style", "unknown")
            bowl = p.get("bowling_style", "unknown")
            log.info(f"{prefix}  {p['name']:<24} {bat:<4} | {bowl}")


# ── convenience view ────────────────────────────────────────────────

def build_styles_lookup(raw_data: dict) -> dict[str, dict]:
    """Return {player_name: {batting_style, bowling_style}} across
    both teams, both sections.  Useful for propagating into scorecard
    entries at innings setup time."""
    out: dict[str, dict] = {}
    for key in ("team_a", "team_b"):
        team = raw_data.get(key) or {}
        for section in ("playing_xi", "bench"):
            for p in team.get(section, []) or []:
                name = p.get("name")
                if not name:
                    continue
                out[name] = {
                    "batting_style": p.get("batting_style", "unknown"),
                    "bowling_style": p.get("bowling_style", "unknown"),
                }
    return out
