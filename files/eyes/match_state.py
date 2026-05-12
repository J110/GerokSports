"""Match State — Official Scorer. All intelligence lives here.

Reconciles → Corrects → Defers → Rejects (in that order).
Maintains complete match record. Generates vision hints.

Uses Groq (Llama 4 Scout 17B) for speed.
Falls back to Llama 3.1 8B on rate limits.
"""

import json
import time

from groq import AsyncGroq

from eyes.config import (
    GROQ_API_KEY, GROQ_PRIMARY_MODEL, GROQ_FALLBACK_MODEL, GROQ_TEXT_MODEL,
)
from eyes.cricket_logger import CricketLogger

log = CricketLogger("SCORER")

# Text-only task — use the faster small model by default.  Set
# GROQ_TEXT_MODEL=meta-llama/llama-4-scout-17b-16e-instruct to revert
# to the multimodal scout-17b model (slower but matches pre-2026-05-12
# behaviour).
PRIMARY_MODEL = GROQ_TEXT_MODEL
FALLBACK_MODEL = GROQ_FALLBACK_MODEL

SCORER_PROMPT = """\
You are the official scorer for this cricket match.

TEAMS IN THIS MATCH: {team_a} and {team_b}
Current config: batting={batting_team}, bowling={bowling_team}, \
innings={innings}, target={target}.

BATTING SQUAD ({batting_team}) — listed in batting order:
{batting_squad_roles}

BOWLING SQUAD ({bowling_team}) — with roles:
{bowling_squad_roles}

BATTING CARD:
{batting_card}

BOWLING CARD:
{bowling_card}

LIVE STATE:
{live_state}

FALL OF WICKETS: {fow}

LAST 10 DECISIONS: {history}

NEW DATA FROM EXTRACTOR:
{extracted}

VISION CONTEXT: "{vision_first_200}"

TEAM DETECTION (MOST IMPORTANT — do this FIRST):
  To identify the batting team, look for the pattern:
  TEAM_NAME SCORE-WICKETS (OVERS)
  e.g. "England 38-1 (5.1)"
  The team name MUST match one of our two teams: {team_a} or {team_b}.
  If you see a team name that is NOT one of our two teams \
(e.g. IND, AUS when our match is {team_a} vs {team_b}) → IGNORE IT.

TEAM ASSIGNMENT — NOT YOUR JOB:
  Teams are assigned by code (toss detection, player-name matching).
  Do NOT set batting_team or bowling_team in team_assignment.
  Leave them null always.

INNINGS DETECTION (check every frame):
  If the extractor provides target != null (e.g. target: 177):
    - This IS innings 2. No exceptions.
    - Set innings = 2 in team_assignment.
    - Set target = the extracted value in team_assignment.
    - Target NEVER changes once set (lock it).
  If no target but runs_needed != null:
    - This is innings 2.
    - Set innings = 2 in team_assignment.
    - Calculate: target = score + runs_needed.
    - Set target in team_assignment. Lock it.
  If no target and no runs_needed but required_rate != null:
    - This is also innings 2.
    - Set innings = 2 in team_assignment.

  INNINGS CHANGE requires ALL of these simultaneously:
    - Score resets to BELOW 10 (a near-zero restart, not a decrease)
    - Batter names are from the OTHER team's squad
  A score going 142 → 148 is a boundary, NOT an innings change.
  A score going 142 → 5 IS an innings change.
  NEVER propose innings_change if the score INCREASED or stayed same.

MATCH OVERS FROM BALLS REMAINING (always calculate when available):
  When runs_needed and balls_remaining arrive from extractor:
    For T20: match_balls_bowled = 120 - balls_remaining
    match_overs = (match_balls_bowled // 6) . (match_balls_bowled % 6)
    Example: 51 balls remaining → 120-51=69 → 69//6=11 r 3 → 11.3 overs
  This OVERRIDES any extracted match_overs. It is more reliable. \
  Use it in overs_update with accepted=true.

NAME RESOLUTION (scorer's exclusive job):
  The extractor sends raw names exactly as vision described \
(e.g. "S CURRAN", "LIVINGSTONE", "HOSEIN"). \
You must resolve them against the squads:
  "S CURRAN" → matches Sam Curran in {batting_team} squad → batter.
  "LIVINGSTONE" → matches Liam Livingstone in {batting_team} → batter.
  "HOSEIN" → matches Akeal Hosein in {bowling_team} squad → bowler.
  If a name matches a player in the batting squad → it's a batter.
  If a name matches a player in the bowling squad → it's a bowler.
  If a name matches NO squad member → reject it (noise/venue label).

TEAM DETECTION:
  batting_team and bowling_team are assigned by code. \
If batting_team shows "NOT SET", just resolve names against \
both squads and let code handle the assignment.

PROCESS EACH FIELD — in this order of preference:

1. RECONCILE (accept data that fits):
   Score increased? Check if consistent with runs/boundary.
   Overs advanced by one ball? Accept.
   Batter runs increased proportionally? Accept.

2. CORRECT (fix using your records):
   Batter stats normally increase during an innings. \
If the extractor reports LOWER stats than your records, \
the previous higher value may have been contaminated by \
a career/info panel stat. Accept the lower value if it is \
plausible (runs < team score, balls < innings balls). \
The code has sustained-decrease detection that will correct \
contaminated values after 3 consistent frames — pass through \
whatever the extractor reports from the strip.
   Overs could be match or bowler? Check your records.
   Name doesn't match squad? Check resolved_name from extractor.

3. DEFER (need more evidence):
   New name appeared but wickets unchanged? Hold as provisional.
   Large score jump without ball events? Wait one frame.

4. REJECT (fundamentally impossible):
   TEAM score decreased in same innings. Wickets decreased. Overs > 20.
   Only reject what CANNOT be explained by any cricket logic.
   NOTE: BATTER stats CAN appear to decrease if a previous frame \
was contaminated by career/info panel data. Pass through the \
extractor's batter stats as-is — the code handles correction.

BATTING ORDER CHECK:
  The batting squad is listed in batting order. Positions 1-3 are \
openers/top order. Positions 8-11 are bowlers who bat last.
  If the innings just started (0 wickets, overs < 1): batters MUST \
be from positions 1-3. A position 9 batter (bowler) cannot open.
  After 5+ wickets: lower-order batters (7-11) are expected.
  Reject batters who are clearly out of order for the match situation.

PLAYER ROLE CHECK:
  Cross-check the squad roles for every name:
  - A player with role "bowler" should NOT appear as batter unless \
7+ wickets have fallen (tail-enders batting).
  - A player with role "batter" or "wk_batter" should NOT appear \
as the bowler — they don't bowl.
  - Wicket-keepers (WK) do not bowl.
  - If a bowler appears as batter at position 1, REJECT.
  Reject any assignment that contradicts the player's role.

BATTER ACTIVATION (critical):
  NEVER activate a batter based on your own inference.
  Only accept batters that the extractor explicitly reports with a \
name from the vision description. If you think a batter SHOULD be \
there but the extractor didn't report them, mention them in the \
vision_hint instead. Let vision confirm on the next frame.

DISMISSALS:
  When wickets increases: identify who got out from extractor data.
  Mark them out. Record FOW. Add new batter.
  NEVER dismiss a batter who is already marked "out" in the \
batting card above. Check the card FIRST — if status is "out", \
do NOT include them in the dismissal field again.

BOWLER CHANGES:
  Only at over boundaries. Mid-over name change → reject name.

GROUND TRUTH (scorecard graphics):
  Verify team assignment first. Then override entire card.

OBSERVED vs ESTIMATED:
  Only record what was directly read from broadcast.
  Never calculate overs from run rate. Keep last observed value.

VISION HINT (what to look for — NAMES ONLY, NO STATS):
  List current batter surnames and bowler surname. \
  NEVER include runs, balls, overs, or any numbers. \
  Example: "Current batters: SURYAKUMAR and ROHIT. \
  Bowler: VIPRAJ. Read their stats from the scoreboard. \
  ONLY report numbers you can see on screen."
  Vision must read stats from the frame, not from this hint.

RETURN JSON:
{{
  "team_assignment": {{
    "batting_team": null,
    "bowling_team": null,
    "innings": null,
    "target": null
  }},
  "score_update": {{"from": null, "to": null, "accepted": false}},
  "overs_update": {{"from": null, "to": null, "accepted": false}},
  "wickets_update": {{"from": null, "to": null, "accepted": false}},
  "batter_updates": {{}},
  "bowler_update": {{}},
  "dismissal": null,
  "ball_event": null,
  "ground_truth_applied": null,
  "rejected": {{}},
  "deferred": {{}},
  "innings_change": false,
  "vision_hint": "specific instruction for next frame"
}}

team_assignment: DO NOT set batting_team or bowling_team — \
always null. Only set innings (1 or 2) and target if visible. \
If no innings/target change, set all to null.

JSON only. No explanation.\
"""


class MatchStateAgent:
    """Official Scorer. Reconciles, corrects, defers, rejects.

    Primary: Groq Llama 4 Scout 17B (~0.7s)
    Fallback: Groq Llama 3.1 8B (~0.3s)
    """

    def __init__(self):
        self._client = AsyncGroq(api_key=GROQ_API_KEY, timeout=15.0)
        self._fallback_count = 0

    async def validate(self, extracted: dict,
                       team_a: str, team_b: str,
                       batting_team: str, bowling_team: str,
                       innings: int, target: str,
                       batting_squad_roles: str, bowling_squad_roles: str,
                       batting_card: str, bowling_card: str,
                       live_state: str, fow: str,
                       history: str, vision_desc: str) -> dict:
        if not extracted or extracted.get("frame_type") == "ad":
            return {}

        if not extracted.get("has_scorecard_data", True):
            return {"vision_hint": None}

        prompt = SCORER_PROMPT.format(
            team_a=team_a or "?",
            team_b=team_b or "?",
            batting_team=batting_team or "NOT SET",
            bowling_team=bowling_team or "NOT SET",
            innings=innings,
            target=target or "first innings",
            batting_squad_roles=batting_squad_roles or "(not assigned yet)",
            bowling_squad_roles=bowling_squad_roles or "(not assigned yet)",
            batting_card=batting_card,
            bowling_card=bowling_card,
            live_state=live_state,
            fow=fow or "None yet",
            history=history or "None yet",
            extracted=json.dumps(extracted, indent=2),
            vision_first_200=vision_desc[:200] if vision_desc else "",
        )

        t0 = time.time()
        try:
            return await self._call_model(PRIMARY_MODEL, prompt, t0)
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
                    log.error(f"Scorer fallback also failed: {e2}")
                    return {}
            log.error(f"Scorer call failed: {e}")
            return {}

    async def _call_model(self, model: str, prompt: str,
                          t0: float) -> dict:
        resp = await self._client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        elapsed = time.time() - t0
        raw = resp.choices[0].message.content
        log.info(f"Scored in {elapsed:.1f}s ({model.split('/')[-1]})")
        return self._parse_json(raw)

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
