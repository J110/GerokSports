# SportsComm — Agent Prompts & Example Outputs

Generated from WI vs ENG 5th T20I test run (Apr 3 2026).

---

## 1. VISION — Dumb Describer

**Model:** `Qwen/Qwen3-VL-8B-Instruct` (Together AI)
**Temperature:** 0 | **Max tokens:** 300

### Prompt

```
You are watching a live cricket broadcast stream.

FIRST WORD of your response MUST be exactly one of:
  SCOREBOARD — bottom scoreboard strip is visible with score/overs/batter info
  GRAPHIC — full-screen overlay (batting scorecard, bowling scorecard, lineup)
  CLOSEUP — player faces, jerseys, dugout, celebrations, no scoreboard visible
  ADVERTISEMENT — ad content, sponsor logos, non-cricket commercial
  PREMATCH — countdown, toss, anthem, walkout, coin flip, ceremony

If ADVERTISEMENT: respond with ONLY the word ADVERTISEMENT.
Do not describe the ad. Stop immediately.

If CLOSEUP or PREMATCH: briefly note what you see (1-2 sentences max).
Do NOT report jersey numbers as scores. Player names on jerseys
are NOT batters at the crease.

If SCOREBOARD or GRAPHIC: describe everything precisely:

LIVE SCOREBOARD (persistent strip at bottom of screen):
  Top line: team abbreviation, score-wickets, overs in parentheses
  Bottom line: two batter names with runs(balls) SEPARATELY,
bowler name with figures W-R(overs), rotating info section
  ALWAYS two separate batters. Never one combined name.
  * or > prefix = striker.

FULL SCORECARD GRAPHIC (overlay filling the screen):
  Every batter/bowler row. Note which TEAM the graphic belongs to.
  Extract every row: name, dismissal, runs, balls, 4s, 6s, SR.

Report every number exactly. Describe what you SEE — don't interpret.

HINT FROM SCORER:
{vision_hint}
```

### Example Outputs

**Frame 1 — Live scoreboard (first frame, no hint)**
```
SCOREBOARD — bottom scoreboard strip is visible with score/overs/batter info

Top line: England 156-7 (19.4)
Bottom line: REHAN MOEEN 0 (1) 22 (13) | 21 RUNS FROM 2 BALLS | RUSSELL 0-56 (3.4) | TO WIN
```
*Latency: 2.1s | 467 chars*

**Frame 2 — Same scoreboard, with scorer hint**
```
SCOREBOARD — bottom scoreboard strip is visible with score/overs/batter info

LIVE SCOREBOARD (persistent strip at bottom of screen):
  Top line: England 156-7 (19.4)
  Bottom line: REHAN MOEEN 22(13), unnamed batter 0(1), RUSSELL 0-56(3.4), rotating info section
```
*Latency: 1.9s | 319 chars*

**Frame 3 — Post-match banner visible**
```
SCOREBOARD — bottom scoreboard strip is visible with score/overs/batter info

Top line: WEST INDIES WON BY 10 RUNS
Bottom line: REHAN MOEEN 10(3) 22(13) 166-7, SPEED 111.6 km/h, THIS OVER 6 0 1 6 4
```
*Latency: 1.3s | 197 chars*

**Frame 4 — Vision over-describes (hallucination example)**
```
SCOREBOARD — bottom scoreboard strip is visible with score/overs/batter info

Top line: WEST INDIES WON BY 10 RUNS
Bottom line: REHAN MOEEN 10(3) 22(13) 166-7 — REHAN MOEEN is not a batter
at the crease; this is a bowling scorecard row. The 166-7 is the team to...
```
*Latency: 5.9s | 932 chars — long response = hallucination / over-interpretation*

**Ad frame (from earlier tests)**
```
ADVERTISEMENT
```
*Latency: ~0.5s | 13 chars — minimal token cost*

---

## 2. EXTRACTOR — Dumb Data Extractor

**Model:** `Qwen/Qwen2.5-7B-Instruct-Turbo` (Together AI)
**Temperature:** 0 | **Max tokens:** 500

### Prompt

```
You are a cricket data extractor. You extract EXACTLY what
vision described. Nothing more. Nothing less.

MOST IMPORTANT — extract chase data if visible:
"28 RUNS FROM 6 BALLS TO WIN" → runs_needed: 28, balls_remaining: 6
"28 FROM 6 BALLS" → runs_needed: 28, balls_remaining: 6
"NEED 93 FROM 51" → runs_needed: 93, balls_remaining: 51
"TO WIN 112 RUNS FROM 63 BALLS" → runs_needed: 112, balls_remaining: 63
"TARGET 177" → target: 177
These appear during innings 2. NEVER miss them.
balls_remaining is NOT overs. It is a countdown of deliveries.

THIS MATCH: {team_a_name} vs {team_b_name}
VISION FRAME TYPE: {frame_type}

RAW OBSERVATION:
"{description}"

CRITICAL — REPORT NAMES EXACTLY AS VISION DESCRIBED:
Do NOT resolve, replace, or match names to any squad.
Vision says "S CURRAN 15(14)" → you report: name="S CURRAN", runs=15, balls=14
Vision says "LIVINGSTONE 10(5)" → you report: name="LIVINGSTONE", runs=10, balls=5
Vision says "HOSEIN 2-9(1.3)" → you report bowler: name="HOSEIN"
You are a data extractor. You extract what vision saw.
Name resolution is the scorer's job. NEVER change a name.

FRAME TYPE RULES:
- CLOSEUP or PREMATCH: set has_scorecard_data: false.
- SCOREBOARD: set has_scorecard_data: true. Extract ALL visible data
(score, wickets, overs, batters, bowler, chase info).
NEVER return has_scorecard_data: false for a SCOREBOARD frame.
- GRAPHIC: set has_scorecard_data: true, ground_truth: true.
Also set graphic_type to one of:
  "bowling_scorecard" — shows bowling figures (overs, runs, wickets, economy)
  "batting_scorecard" — shows batting data (runs, balls, 4s, 6s)
  "fall_of_wickets" — shows FOW data
  "partnership" — shows partnership data
  "other" — any other graphic
And set graphic_team to the team name shown on the graphic
(e.g. "West Indies" if the graphic says "WEST INDIES" at top).

OTHER MATCH TICKERS:
If vision describes scores for teams other than
{team_a_name} or {team_b_name} (e.g. IND 187-5),
put those in "other_match_ticker". Do NOT use them as
score/overs/batters/bowler for our match.

Also extract "REQUIRED RUN-RATE 9.37" → required_rate: 9.37

batting_team_visible: the team name shown NEXT TO the main
score (e.g. "ENG 84-3" → "England"). Must be {team_a_name}
or {team_b_name}. If neither, set to null.

RETURN JSON:
{
  "frame_type": "scoreboard|graphic|closeup|prematch|ad",
  "has_scorecard_data": true,
  "batting_team_visible": null,
  "score": 84,
  "wickets": 3,
  "match_overs": "11.3",
  "run_rate": null,
  "target": null,
  "required_rate": null,
  "runs_needed": 93,
  "balls_remaining": 51,
  "batters": [
    {"name": "S CURRAN", "runs": 15, "balls": 14, "striker": false},
    {"name": "LIVINGSTONE", "runs": 10, "balls": 5, "striker": true}
  ],
  "bowler": {"name": "HOSEIN", "overs": "1.3", "runs": 9, "wickets": 2},
  "ground_truth": false,
  "graphic_type": null,
  "graphic_team": null,
  "other_match_ticker": null
}

Omit fields not visible. JSON only. No explanation.
```

### Example Outputs

**Frame 1 — First scoreboard (merged name, chase data missed)**
```json
{
  "frame_type": "scoreboard",
  "has_scorecard_data": true,
  "batting_team_visible": null,
  "score": 156,
  "wickets": 7,
  "match_overs": "19.4",
  "batters": [
    {"name": "REHAN MOEEN", "runs": 0, "balls": 1, "striker": false},
    {"name": "unnamed batter", "runs": 0, "balls": 1, "striker": true}
  ],
  "bowler": {"name": "RUSSELL", "overs": "3.4", "runs": 56, "wickets": 0}
}
```
*Latency: 2.5s*
*Note: "21 RUNS FROM 2 BALLS" was in vision output but extractor didn't capture runs_needed/balls_remaining.*

**Frame 3 — Clean extraction with separate batter names**
```json
{
  "frame_type": "scoreboard",
  "has_scorecard_data": true,
  "score": 84,
  "wickets": 3,
  "match_overs": "11.3",
  "batters": [
    {"name": "S CURRAN", "runs": 15, "balls": 14, "striker": false},
    {"name": "LIVINGSTONE", "runs": 10, "balls": 5, "striker": true}
  ],
  "bowler": {"name": "HOSEIN", "overs": "1.3", "runs": 9, "wickets": 2}
}
```
*Latency: 2.3s*
*Note: Names reported exactly as vision described — no resolution attempted. Correct behavior.*

**Frame 2 — Extractor misassigns bowler as batter**
```json
{
  "frame_type": "scoreboard",
  "has_scorecard_data": true,
  "score": 156,
  "wickets": 7,
  "match_overs": "19.4",
  "batters": [
    {"name": "REHAN MOEEN", "runs": 22, "balls": 13, "striker": false},
    {"name": "unnamed batter", "runs": 0, "balls": 1, "striker": false},
    {"name": "RUSSELL", "runs": 0, "balls": 56, "striker": true}
  ],
  "bowler": {"name": "HOSEIN", "overs": "1.3", "runs": 9, "wickets": 2}
}
```
*Latency: 2.8s*
*Note: RUSSELL 0-56(3.4) bowling figures misread as batter with 0 runs, 56 balls. Scorer rejects because Andre Russell isn't in England batting card.*

---

## 3. SCORER — Match State Agent (Cricket Brain)

**Model:** `Qwen/Qwen2.5-7B-Instruct-Turbo` (Together AI)
**Temperature:** 0 | **Max tokens:** 600

### Prompt

```
You are the official scorer for this cricket match.

TEAMS IN THIS MATCH: {team_a} and {team_b}
Current config: batting={batting_team}, bowling={bowling_team},
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
  If you see a team name that is NOT one of our two teams
(e.g. IND, AUS when our match is {team_a} vs {team_b}) → IGNORE IT.

SCORECARD GRAPHIC RULE (critical):
  A BOWLING scorecard for team X means team X is BOWLING:
    "bowling scorecard for West Indies" → WI is bowling →
the OTHER team ({team_a} or {team_b}) is batting.
  A BATTING scorecard for team X means team X WAS batting:
    "batting scorecard for West Indies" → WI batted (could be
previous innings if teams have changed).
  Check graphic_type and graphic_team from the extractor:
    If graphic_type == "bowling_scorecard" and graphic_team == X:
      X is the BOWLING team. The other team is batting.
    If graphic_type == "batting_scorecard" and graphic_team == X:
      X was the batting team.
  Do NOT set batting_team = X from a bowling scorecard of X.
That is backwards.

  The extractor may also provide "batting_team_visible" — the
team shown next to the live scoreboard score.
  If batting_team is "NOT SET" and batting_team_visible is one of
our teams:
    The visible team IS the batting team. Set it.
    The other team is bowling.
  If batting_team IS set but visible team DIFFERS and is one of
our teams:
    This might be an innings change. Check: is the score near 0?
Are the batter names from the other team? If yes → innings change.

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
  If "LAST WICKET" info mentions a player from one team, and
that team is the one visible on the scoreboard → confirms they
are batting.

MATCH OVERS FROM BALLS REMAINING (always calculate when available):
  When runs_needed and balls_remaining arrive from extractor:
    For T20: match_balls_bowled = 120 - balls_remaining
    match_overs = (match_balls_bowled // 6) . (match_balls_bowled % 6)
    Example: 51 balls remaining → 120-51=69 → 69//6=11 r 3 → 11.3 overs
  This OVERRIDES any extracted match_overs. It is more reliable.
  Use it in overs_update with accepted=true.

NAME RESOLUTION (scorer's exclusive job):
  The extractor sends raw names exactly as vision described
(e.g. "S CURRAN", "LIVINGSTONE", "HOSEIN").
You must resolve them against the squads:
  "S CURRAN" → matches Sam Curran in {batting_team} squad → batter.
  "LIVINGSTONE" → matches Liam Livingstone in {batting_team} → batter.
  "HOSEIN" → matches Akeal Hosein in {bowling_team} squad → bowler.
  If a name matches a player in the batting squad → it's a batter.
  If a name matches a player in the bowling squad → it's a bowler.
  If a name matches NO squad member → reject it (noise/venue label).

TEAM DETECTION FROM SQUAD (when team name is not visible):
  If batting_team is not yet set but you can identify the batters:
check which squad they belong to.
  Example: Buttler and Curran are both England players →
England is batting. Set it.
  Player-name-based detection is MORE reliable than reading
team abbreviations from the scoreboard.

PROCESS EACH FIELD — in this order of preference:

1. RECONCILE (accept data that fits):
   Score increased? Check if consistent with runs/boundary.
   Overs advanced by one ball? Accept.
   Batter runs increased proportionally? Accept.

2. CORRECT (fix using your records):
   Batter runs decreased? Impossible — keep higher value.
   Overs could be match or bowler? Check your records.
   Name doesn't match squad? Check resolved_name from extractor.

3. DEFER (need more evidence):
   New name appeared but wickets unchanged? Hold as provisional.
   Large score jump without ball events? Wait one frame.

4. REJECT (fundamentally impossible):
   Score decreased in same innings. Wickets decreased. Overs > 20.
   Only reject what CANNOT be explained by any cricket logic.

BATTING ORDER CHECK:
  The batting squad is listed in batting order. Positions 1-3 are
openers/top order. Positions 8-11 are bowlers who bat last.
  If the innings just started (0 wickets, overs < 1): batters MUST
be from positions 1-3. A position 9 batter (bowler) cannot open.
  After 5+ wickets: lower-order batters (7-11) are expected.
  Reject batters who are clearly out of order for the match situation.

PLAYER ROLE CHECK:
  Cross-check the squad roles for every name:
  - A player with role "bowler" should NOT appear as batter unless
7+ wickets have fallen (tail-enders batting).
  - A player with role "batter" or "wk_batter" should NOT appear
as the bowler — they don't bowl.
  - Wicket-keepers (WK) do not bowl.
  - If a bowler appears as batter at position 1, REJECT.
  Reject any assignment that contradicts the player's role.

DISMISSALS:
  When wickets increases: identify who got out from extractor data.
  Mark them out. Record FOW. Add new batter.

BOWLER CHANGES:
  Only at over boundaries. Mid-over name change → reject name.

GROUND TRUTH (scorecard graphics):
  Verify team assignment first. Then override entire card.

OBSERVED vs ESTIMATED:
  Only record what was directly read from broadcast.
  Never calculate overs from run rate. Keep last observed value.

VISION HINT (specific and actionable):
  Tell vision exactly what to look for. Player names, expected
stats, which numbers matter. Be specific, not generic.

RETURN JSON:
{
  "team_assignment": {
    "batting_team": null,
    "bowling_team": null,
    "innings": null,
    "target": null
  },
  "score_update": {"from": null, "to": null, "accepted": false},
  "overs_update": {"from": null, "to": null, "accepted": false},
  "wickets_update": {"from": null, "to": null, "accepted": false},
  "batter_updates": {},
  "bowler_update": {},
  "dismissal": null,
  "ball_event": null,
  "ground_truth_applied": null,
  "rejected": {},
  "deferred": {},
  "innings_change": false,
  "vision_hint": "specific instruction for next frame"
}

team_assignment: set batting_team and bowling_team if not yet
configured or if innings changed. Set innings (1 or 2).
Set target if visible. If teams are already correct, set all
to null (no change needed).

JSON only. No explanation.
```

### Example Outputs

**Frame 1 — First frame, no teams set. Scorer identifies England batting.**
```json
{
  "team_assignment": {
    "batting_team": "England",
    "bowling_team": "West Indies",
    "innings": 1,
    "target": null
  },
  "score_update": {"from": null, "to": 156, "accepted": true},
  "overs_update": {"from": null, "to": "19.4", "accepted": true},
  "wickets_update": {"from": null, "to": 7, "accepted": true},
  "batter_updates": {},
  "bowler_update": {},
  "dismissal": null,
  "ball_event": null,
  "ground_truth_applied": null,
  "rejected": {
    "REHAN MOEEN": "merged name — not in squad",
    "unnamed batter": "not a real player name"
  },
  "deferred": {},
  "innings_change": false,
  "vision_hint": "Look for batter names: REHAN MOEEN, unnamed batter. Bowler: RUSSELL. Wickets: 7. Overs: 19.4."
}
```
*Latency: 3.3s*
*Note: Correctly set England batting from "England 156-7" pattern. Rejected merged name "REHAN MOEEN" (Rehan Ahmed + Moeen Ali). Score/overs/wickets accepted as first load.*

**Frame 2 — Hosein resolved, Russell rejected as batter**
```json
{
  "team_assignment": null,
  "score_update": {"from": 156, "to": 156, "accepted": true},
  "overs_update": {"from": "19.4", "to": "19.4", "accepted": true},
  "wickets_update": {"from": 7, "to": 7, "accepted": true},
  "batter_updates": {},
  "bowler_update": {
    "name": "Akeal Hosein",
    "overs": "1.3",
    "runs": 9,
    "wickets": 2,
    "accepted": true
  },
  "dismissed": null,
  "rejected": {
    "REHAN MOEEN": "merged name — not in either squad",
    "unnamed batter": "not a real name",
    "RUSSELL": "Andre Russell is in West Indies squad — not an England batter"
  },
  "deferred": {},
  "innings_change": false,
  "vision_hint": "Focus on batter names, runs, and balls faced for REHAN MOEEN and RUSSELL, and bowler name, overs, and runs for HOSEIN."
}
```
*Latency: 3.0s*
*Note: HOSEIN resolved → Akeal Hosein (WI bowler). RUSSELL correctly rejected as batter (he's WI, not England). Merged name rejected again — self-corrects next frame.*

**Frame 4 — Batters accepted, score jump held by code guard**
```json
{
  "team_assignment": null,
  "score_update": {"from": 156, "to": 166, "accepted": true},
  "overs_update": {"from": "19.4", "to": "19.4", "accepted": true},
  "wickets_update": {"from": 7, "to": 7, "accepted": true},
  "batter_updates": {
    "S CURRAN": {"runs": 15, "balls": 14, "accepted": true},
    "LIVINGSTONE": {"runs": 10, "balls": 5, "accepted": true}
  },
  "bowler_update": {
    "name": "Akeal Hosein",
    "overs": "1.3",
    "runs": 9,
    "wickets": 2,
    "accepted": true
  },
  "rejected": {},
  "deferred": {},
  "innings_change": false,
  "vision_hint": "Focus on batter names and their stats for the next frame. Check for any new wickets or ball events."
}
```
*Latency: 2.7s*
*Note: Scorer accepted 166, but the code-level ScoreJumpGuard held the 156→166 (+10) jump. Batters S CURRAN and LIVINGSTONE accepted — names now separate (self-corrected from "REHAN MOEEN" merged name in earlier frames). Scoreboard resolved S CURRAN → Sam Curran, LIVINGSTONE → Liam Livingstone.*

**Frame 3 — Innings change detected (post-match content)**
```json
{
  "team_assignment": null,
  "score_update": {"from": 156, "to": 84, "accepted": false},
  "overs_update": {"from": "19.4", "to": "11.3", "accepted": false},
  "wickets_update": {"from": 7, "to": 3, "accepted": false},
  "batter_updates": {},
  "bowler_update": {},
  "rejected": {
    "score": "decreased from 156 to 84 — impossible in same innings",
    "overs": "decreased from 19.4 to 11.3 — overs can't go backward"
  },
  "innings_change": true,
  "vision_hint": "Focus on batter and bowler names, runs, balls, and wickets for the next frame."
}
```
*Latency: 2.3s*
*Note: Score dropped 156→84 and overs 19.4→11.3. Scorer correctly rejected both (can't decrease). Flagged innings_change=true because it detected different match context. Code-level guard prevented the innings flip since it was post-match replay data, not live play.*

---

## Pipeline Flow Summary

```
Frame captured
    │
    ├─ Pixel-hash diff → skip if <5% change (0ms, free)
    │
    ▼
VISION (Qwen3-VL-8B, ~1.5-2s)
    │ Returns: (frame_type, description)
    │
    ├─ ADVERTISEMENT → skip (0 tokens wasted)
    ├─ CLOSEUP/PREMATCH → skip extractor & scorer
    │
    ▼
EXTRACTOR (Qwen2.5-7B, ~2-3s)
    │ Returns: structured JSON (score, batters, bowler, chase data)
    │ NO validation, NO name resolution
    │
    ▼
SCORER (Qwen2.5-7B, ~2-3s)
    │ Returns: validated updates, rejections, vision_hint
    │ ALL intelligence lives here
    │
    ▼
CODE GUARDS
    ├─ ScoreJumpGuard: holds >7 run jumps for 2-frame confirmation
    ├─ OversJumpGuard: rejects >1 over jumps per frame
    ├─ BowlingScorecard flip: if scorer misreads bowling card
    ├─ Team gating: no updates if batting_team unset
    │
    ▼
SCOREBOARD (name resolution → card updates)
```

**Cost per match (~1700 frames):**
| Agent | Per call | Per match |
|-------|----------|-----------|
| Vision | $0.00024 | $0.41 |
| Extractor | $0.00006 | $0.10 |
| Scorer | $0.00010 | $0.17 |
| **Total** | | **$0.68** |

---

## Known Issues

1. **Extractor can't reliably parse "X RUNS FROM Y BALLS"** — moved to top of prompt, still inconsistent. Scorer fallback (score + runs_needed = target) works.
2. **Vision merges adjacent batter names** — "REHAN MOEEN" instead of "Rehan Ahmed" + "Moeen Ali". Self-corrects on next frame when names separate.
3. **Vision sometimes over-interprets** — adds cricket reasoning to descriptions (F4: 5.9s, 932 chars). Should be dumb. Longer response = wasted tokens.
