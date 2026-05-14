"""Extractor — dumb data extractor. Pass-through only.

Extracts exactly what vision described. No name resolution.
No squad matching. No validation. That's the scorer's job.

Uses Groq (Llama 4 Scout 17B) for speed + accuracy.
Falls back to Llama 3.1 8B on rate limits.
"""

import json
import time

from groq import AsyncGroq

from eyes.config import (
    GROQ_API_KEY, GROQ_PRIMARY_MODEL, GROQ_FALLBACK_MODEL, GROQ_TEXT_MODEL,
)
from eyes.cricket_logger import CricketLogger
from eyes.extract_regex import parse_strip
from eyes.extract_regex import (
    _parse_tag_line,
    _STRIP_LINE as _STRIP_LINE_RE,
)
import re as _re_agent

_DIGITS_2_3_RE = _re_agent.compile(r"\d{2,3}")

try:
    import trace_emitter as _trace_agent
except ImportError:
    _trace_agent = None


log = CricketLogger("EXTRACT")

# Text-only task — use the faster small model by default.  Set
# GROQ_TEXT_MODEL=meta-llama/llama-4-scout-17b-16e-instruct to revert
# to the multimodal scout-17b model (slower but matches pre-2026-05-12
# behaviour).  Fallback retained at 8b-instant in case the configured
# primary itself rate-limits.
PRIMARY_MODEL = GROQ_TEXT_MODEL
FALLBACK_MODEL = GROQ_FALLBACK_MODEL

EXTRACTOR_PROMPT = """\
THIS MATCH IS: {team_a_name} vs {team_b_name}
THERE ARE NO OTHER TEAMS.

batting_team_visible MUST be one of:
  '{team_a_name}' or '{team_b_name}' or null.
NEVER return any other team name.

Batter and bowler names: report EXACTLY what vision described.
If vision says 'SUDHARSAN' → report 'SUDHARSAN'.
Do NOT invent names. Do NOT guess names.
If you cannot read a name from vision → set to null.

You are a cricket data extractor. You extract EXACTLY what \
vision described. Nothing more. Nothing less.

MOST IMPORTANT — extract chase data if visible:
"28 RUNS FROM 6 BALLS TO WIN" → runs_needed: 28, balls_remaining: 6
"28 FROM 6 BALLS" → runs_needed: 28, balls_remaining: 6
"NEED 93 FROM 51" → runs_needed: 93, balls_remaining: 51
"TO WIN 112 RUNS FROM 63 BALLS" → runs_needed: 112, balls_remaining: 63
"TARGET 177" → target: 177
These appear during innings 2. NEVER miss them. \
balls_remaining is NOT overs. It is a countdown of deliveries.

PROJECTED SCORE is NOT a target:
"PROJECTED SCORE 163" → projected_score: 163 (innings 1 stat)
"PAR SCORE 163" → projected_score: 163 (innings 1 DLS stat)
"PREDICTED SCORE 163" → projected_score: 163
"114 | 7 RPO 124 | 9 RPO 139" → projected_score only, NOT target.
These appear in innings 1 as info panels. NEVER set target from them.
Only set target from "TO WIN", "CHASING", or standalone "TARGET" \
(without "PROJECTED" or "PAR" before it).

VISION FRAME TYPE: {frame_type}

RAW OBSERVATION:
"{description}"

CRITICAL — REPORT NAMES EXACTLY AS VISION DESCRIBED:
Do NOT resolve, replace, or match names to any squad.
Report every name character-for-character as vision wrote it.
You are a data extractor. You extract what vision saw.
Name resolution is the scorer's job. NEVER change a name.
NEVER invent data. If vision didn't mention it, omit it.

INFO PANEL FILTERING:
If vision reports INFO_PANEL data (career/tournament/IPL stats), \
put it in a separate field:
  "info_panel": {{"type": "career_stats", "text": "whatever it says"}}
Do NOT use info panel numbers for score, batters, or bowler fields.
If vision reports TWO stats for the same player (strip vs panel), \
use the SMALLER number — match stats are always smaller than \
career stats mid-match.
If a bowler shows overs > 4.0 (T20 max per bowler), it is a \
career/tournament stat — do NOT use it for bowler overs. \
If bowler overs > current match overs, same rule — reject it.

BOWLING FIGURES FORMAT:
The broadcast strip shows bowling figures as W-R (overs), where \
W = wickets taken and R = runs conceded. For example: \
"GREEN 1-4 0.4" means wickets=1, runs=4, overs=0.4. \
The FIRST number is ALWAYS wickets, the SECOND is ALWAYS runs. \
A bowler's runs will almost always be >= their wickets in T20s. \
If the first number is larger, you have it backwards — swap them.

FRAME TYPE RULES:
- CLOSEUP or PREMATCH: set has_scorecard_data: false.
- SCOREBOARD: set has_scorecard_data: true. Extract ALL visible data \
(score, wickets, overs, batters, bowler, chase info). \
NEVER return has_scorecard_data: false for a SCOREBOARD frame.
- GRAPHIC: set has_scorecard_data: true, ground_truth: true. \
Also set graphic_type to one of:
  "bowling_scorecard" — shows bowling figures (overs, runs, wickets, economy)
  "batting_scorecard" — shows batting data (runs, balls, 4s, 6s)
  "fall_of_wickets" — shows FOW data
  "partnership" — shows partnership data
  "other" — any other graphic
And set graphic_team to the team name shown on the graphic \
(e.g. "West Indies" if the graphic says "WEST INDIES" at top).
For GRAPHIC bowling_scorecard: return ALL bowlers in "bowlers" array:
  "bowlers": [{{"name": "MUKESH", "overs": "2", "runs": 12, "wickets": 2}}, ...]
For SCOREBOARD (live strip): use single "bowler" object as usual.

OTHER MATCH TICKERS:
If vision describes scores for teams other than \
{team_a_name} or {team_b_name} (e.g. IND 187-5), \
put those in "other_match_ticker". Do NOT use them as \
score/overs/batters/bowler for our match.

Also extract "REQUIRED RUN-RATE 9.37" → required_rate: 9.37

batting_team_visible: the team name shown NEXT TO the main \
score (e.g. "ENG 84-3" → "England"). Must be {team_a_name} \
or {team_b_name}. If neither, set to null.

score and wickets are ALWAYS separate fields.
score is ONLY the run total (integer): 58
wickets is ONLY the wicket count (integer): 2
NEVER combine them as "58-2" in the score field.

match_overs: the CURRENT overs bowled (e.g. 0.5, 3.2, 15.4).
CRITICAL: "P 0.5/20" means 0.5 overs bowled out of 20 total. \
match_overs = "0.5", NOT "20". The number BEFORE the slash \
is the overs bowled. The number AFTER (20, 50) is the match \
format and must be IGNORED for match_overs.

FIELD POSITIONS (report on EVERY frame, not just wide angles):
Look at the ENTIRE frame, including background and edges. \
Even on closeups, fielders are often visible in the \
background as blurred figures in team colors.
Report what you can see:
  field_observed: {{
    "visible_fielders": 7,
    "positions": ["deep cover", "point", "mid-off", "mid-on",
                  "midwicket", "deep square leg", "fine leg"],
    "slips": 0,
    "keeper_visible": true,
    "keeper_position": "back",
    "formation_impression": "defensive",
    "changes_noticed": "point moved wider since last frame",
    "partial_view": true,
    "confidence": "low"
  }}
confidence levels:
  high — wide angle, all/most fielders clearly visible
  medium — medium shot, 4-6 fielders visible
  low — closeup, 1-3 fielders in background
  none — no fielders visible at all (tight closeup, ad)
If NO fielders visible at all:
  field_observed: {{"visible_fielders": 0, "confidence": "none"}}
Even 1-2 fielders visible in a closeup is useful.

BROADCASTER FIELD GRAPHIC:
Sometimes the broadcast shows an oval/circular diagram with \
dots marking fielder positions. It has "OFF" and "LEG" labels \
on each side, with a pitch strip in the center.
If you see this graphic:
  field_graphic: {{
    "detected": true,
    "positions": [
      {{"zone": "slip", "depth": "close"}},
      {{"zone": "point", "depth": "ring"}},
      {{"zone": "cover", "depth": "ring"}},
      {{"zone": "mid-off", "depth": "ring"}},
      {{"zone": "mid-on", "depth": "ring"}},
      {{"zone": "midwicket", "depth": "ring"}},
      {{"zone": "deep square leg", "depth": "boundary"}},
      {{"zone": "fine leg", "depth": "boundary"}},
      {{"zone": "long-on", "depth": "boundary"}}
    ]
  }}
Count every dot. There should be exactly 9 fielders \
(excluding keeper and bowler). Read each position carefully.

DISMISSAL DETECTION:
If vision mentions any of these patterns near a batter name:
  'NAME runs(balls) c FIELDER b BOWLER' → caught
  'NAME runs(balls) b BOWLER' → bowled
  'NAME runs(balls) lbw b BOWLER' → lbw
  'NAME runs(balls) run out' → run_out
  'NAME runs(balls) st KEEPER b BOWLER' → stumped
  'NAME runs(balls) retired' → retired
Then this batter is OUT. Do NOT put them in the batters array.
Instead set:
  "dismissal": {{
    "batter": "EXACT_NAME",
    "type": "caught|bowled|lbw|run_out|stumped|retired",
    "fielder": "FIELDER_NAME or null",
    "bowler": "BOWLER_NAME or null",
    "runs": 4,
    "balls": 2
  }}

WARNING — "OUT" has TWO meanings on broadcast:
  1. DISMISSAL: 'HEAD c Jadeja b Bishnoi 23(18)' — batter is out
  2. IMPACT SUB: 'OUT SALIL PAYNE' — player leaving the XI
If 'OUT' appears near TOSS, IMPACT, SUB, REPLACES, or without
c/b/lbw/run out context → it is an IMPACT SUBSTITUTION, NOT a
dismissal. Do NOT set the dismissal field.

BOWLING SPEED:
If vision mentions a speed reading (SPEED: 141.6 or \
similar number in 80-160 range with kph/km/h):
set bowling.speed_kph to that number. \
If no speed visible: set bowling.speed_kph to null. \
Do NOT guess the speed. Only report what vision saw.

EXTRAS:
If vision mentions WIDE, wd, or arms outstretched: \
set extras.type = "wide", extras.runs = 1. \
If vision mentions NO BALL, NB, or FREE HIT: \
set extras.type = "no_ball", extras.runs = 1. \
If vision mentions LEG BYE: set extras.type = "leg_bye". \
If vision mentions BYE: set extras.type = "bye". \
Wides and no-balls add runs to TEAM score but NOT batter runs.

THIS OVER INDICATOR:
The broadcast sometimes shows a small row of ball-by-ball \
results for the current over. Examples: \
'4 . 1 6 wd 4' or icons showing dots and boundaries.
If visible, extract: this_over_broadcast: ["4", ".", "1", "6", "wd", "4"]

BATTING ACTION — what the batter did with the ball:
SHOT TYPES: drive, cover_drive, straight_drive, on_drive, \
pull, hook, cut, sweep, reverse_sweep, flick, glance, \
loft, slog, defense, leave, scoop, uppercut
DIRECTION: straight, cover, point, third_man, midwicket, \
square_leg, fine_leg, long_on, long_off
ELEVATION: along_ground, bounced, aerial
CONTACT: middle, edge, top_edge, leading_edge, toe, miss
Examples:
'Swung over mid-on' → shot:loft, direction:long_on, elevation:aerial
'Drives through cover' → shot:cover_drive, direction:cover, elevation:along_ground
'Thick edge flies over keeper' → shot:cut, direction:third_man, contact:edge, elevation:aerial
'Pulls to deep square leg' → shot:pull, direction:square_leg, elevation:along_ground

BOWLING ACTION — what the bowler delivered:
TYPE: fast (135+), medium_fast (120-135), medium (110-120), spin (<100)
VARIATION: outswing, inswing, seam, cutter, bouncer, yorker, \
full_toss, slower_ball, knuckle_ball, off_break, leg_break, \
googly, arm_ball, carrom_ball, flipper
LINE: outside_off, off_stump, middle, leg_stump, outside_leg
LENGTH: yorker, full, good_length, back_of_length, short, half_volley
Examples:
'Full outside off, shape away' → line:outside_off, length:full, variation:outswing
'Slower ball, overpitched' → variation:slower_ball, length:full
'Tossed up on off stump' → type:spin, line:off_stump, length:full
'Short and wide' → length:short, line:outside_off

NULL vs ZERO — CRITICAL:
Numeric fields (runs, balls, overs, wickets) MUST be null when not \
visible in the scout text. NEVER default to 0. \
"0" means "I can see this player and their score is genuinely 0." \
"null" means "I cannot read this number from the frame." \
These are different facts. A batter whose number you cannot read \
is NOT a batter on 0 — they may be on 115. Writing 0 is a lie. \
If scout text is "Abhishek [RUNS]([BALLS])" or "Abhishek * |" or \
any pattern without actual digits next to the name, set runs=null \
AND balls=null. Same for the bowler's overs/runs/wickets. \
Same for the batter's 4s/6s if you can't see those columns. \
If you are tempted to write 0 because the template shows 0, stop: \
write null instead. The template below uses null to make this \
explicit — follow it.

RETURN JSON:
{{
  "frame_type": "scoreboard|graphic|closeup|prematch|ad",
  "has_scorecard_data": true,
  "batting_team_visible": null,
  "score": null,
  "wickets": null,
  "match_overs": null,
  "run_rate": null,
  "target": null,
  "projected_score": null,
  "required_rate": null,
  "runs_needed": null,
  "balls_remaining": null,
  "batters": [
    {{"name": "EXACT_NAME_FROM_VISION", "runs": null, "balls": null, "striker": false}}
  ],
  "bowler": {{"name": "EXACT_NAME_FROM_VISION", "overs": null, "runs": null, "wickets": null, "speed_kph": null}},
  "bowlers": [],
  "extras": {{"type": null, "runs": null}},
  "this_over_broadcast": null,
  "batting_action": {{
    "shot_type": null, "direction": null, "elevation": null, "contact": null
  }},
  "bowling_action": {{
    "type": null, "variation": null, "line": null, "length": null
  }},
  "dismissal": null,
  "ground_truth": false,
  "graphic_type": null,
  "graphic_team": null,
  "other_match_ticker": null,
  "field_observed": null,
  "field_graphic": null,
  "info_panel": null
}}

Omit fields not visible. JSON only. No explanation. \
REMEMBER: unreadable numbers are null, NOT zero.\
"""


class Extractor:
    """Dumb data extractor. Passes through what vision saw.

    Primary: Groq Llama 4 Scout 17B (~0.7s)
    Fallback: Groq Llama 3.1 8B (~0.3s)
    """

    def __init__(self):
        self._client = AsyncGroq(api_key=GROQ_API_KEY, timeout=15.0)
        self._fallback_count = 0

    async def extract(self, description: str, frame_type: str,
                      team_a_name: str = "", team_b_name: str = "",
                      **kwargs) -> dict:
        if not description:
            return {}

        t_regex0 = time.time()
        regex_result = parse_strip(
            description, team_a_name or None, team_b_name or None)
        t_regex_ms = int((time.time() - t_regex0) * 1000)
        if regex_result is not None:
            log.info(
                f"[EXTRACT-PATH] path={regex_result.get('_extract_path')} "
                f"t_ms={t_regex_ms}")
            self._apply_digits_false_veto(regex_result, description)
            return regex_result

        prompt = EXTRACTOR_PROMPT.format(
            frame_type=frame_type,
            team_a_name=team_a_name or "Unknown",
            team_b_name=team_b_name or "Unknown",
            description=description,
        )

        t0 = time.time()
        try:
            result = await self._call_model(PRIMARY_MODEL, prompt, t0)
            t_llm_ms = int((time.time() - t0) * 1000)
            log.info(f"[EXTRACT-PATH] path=llm t_ms={t_llm_ms}")
            if isinstance(result, dict):
                result.setdefault("_extract_path", "llm")
                self._apply_digits_false_veto(result, description)
            return result
        except Exception as e:
            err = str(e).lower()
            if "rate_limit" in err or "429" in err:
                self._fallback_count += 1
                log.info(f"Scout rate limited, falling back to 8B "
                         f"(#{self._fallback_count})")
                try:
                    return await self._call_model(
                        FALLBACK_MODEL, prompt, t0)
                except Exception as e2:
                    log.error(f"Fallback also failed: {e2}")
                    return {}
            log.error(f"Extractor call failed: {e}")
            return {}

    async def _call_model(self, model: str, prompt: str,
                          t0: float) -> dict:
        resp = await self._client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        elapsed = time.time() - t0
        raw = resp.choices[0].message.content
        log.info(f"Extracted in {elapsed:.1f}s ({model.split('/')[-1]})")
        return self._parse_json(raw)

    def _apply_digits_false_veto(self, result: dict,
                                 description: str) -> None:
        """Anti-hallucination veto: when the Scout response's digits
        classifier reports no digits but the STRIP block contains
        digits, drop the digit-bearing fields from ``result``.

        Canonical VLM hallucination signature for cross-match graphic
        flashes that the team-token gate (8cb9465) doesn't catch when
        the team token is missing or itself hallucinated.

        Classifier source order:
          1. Explicit ``digits`` field in the JSON tag header
             (future-proof when Scout exposes a pixel-level digit
             classifier).
          2. Fallback: ``\d{2,3}`` regex over the full response,
             matching Vision's existing ``has_digits`` heuristic at
             vision.py:644.  Single-digit STRIPs like
             "DC 0-0 (0.0)" produce classifier=False even though the
             STRIP contains digits — that's the hallucination this
             veto targets.
        """
        if not isinstance(result, dict) or not description:
            return
        # Classifier verdict.
        tag = _parse_tag_line(description) if _parse_tag_line else {}
        classifier_digits = tag.get("digits") if tag else None
        if classifier_digits is None:
            classifier_digits = bool(
                _DIGITS_2_3_RE.search(description))
        if classifier_digits:
            return
        # STRIP block content.
        strip_m = _STRIP_LINE_RE.search(description) if _STRIP_LINE_RE else None
        if not strip_m:
            return
        strip_body = (strip_m.group("body") or "").strip()
        if not any(ch.isdigit() for ch in strip_body):
            return
        # Veto: digits in STRIP that classifier didn't see.
        if _trace_agent is not None:
            try:
                _trace_agent.get_recorder().record(
                    tag="SCOUT-DIGITS-FALSE-STRIP-VETOED",
                    strip_preview=strip_body[:120],
                    has_strip_flag=(tag.get("has_strip")
                                    if tag else None),
                    extract_path=result.get("_extract_path"))
            except Exception:
                pass
        log.warn(
            f"[SCOUT-DIGITS-FALSE-STRIP-VETOED] classifier reports "
            f"no digits but STRIP contains digits: "
            f"{strip_body[:120]!r} — vetoing digit-bearing fields.")
        # Drop digit-bearing fields.  Keep team identification
        # (batting_team_visible) since team-token hallucination has a
        # separate defense (the 8cb9465 prefix gate).
        for _k in ("score", "wickets", "match_overs",
                   "this_over_broadcast", "extras",
                   "run_rate", "target", "projected_score",
                   "required_rate", "runs_needed", "balls_remaining"):
            if _k in result:
                result[_k] = None
        result["bowler"] = {}
        result["batters"] = []

    @staticmethod
    def _parse_json(raw: str) -> dict:
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
            log.error(f"JSON parse failed: {text[:200]}")
            return {}

    async def close(self):
        await self._client.close()
