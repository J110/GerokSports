"""Regex-primary Extractor — fast path for the structured SCOUT prose.

Parses the deterministic format that today's SCOUT_PROMPT
(VISIBLE_TEXT + STRIP) produces:

    {"has_strip": true, ..., "camera_view": "bowlers_end", "frame_phase": "release", ...}
    VISIBLE_TEXT: MI 76-3 9.1 | NAMAN TILAK 26 20 | KRUNAL 0-9 1.1
    STRIP: MI 76-3 (9.1) | extras=null | this_over=null | NAMAN 26(20) | TILAK 21(20) | KRUNAL 0-9 (1.1)
    INFO_PANEL: null
    SPEED: null
    EXTRA: null
    THIS OVER: null
    FULL SCORECARD: null
    The frame shows ...

Returns a dict compatible with the LLM Extractor's JSON schema for the
state-derivation-critical fields (score/wickets/overs/batters/bowler/
target/run_rate/dismissal-pattern). Returns ``None`` if the STRIP
line is absent or malformed — caller falls back to the LLM Extractor.

Track-2 narrative fields (batting_action, bowling_action,
field_observed, field_graphic) are NOT extracted here; if downstream
needs them, the LLM fallback can be forced via the ``always_fallback``
parameter on ``parse_strip``.

Trade-off: regex misses edge cases (unusual STRIP layouts, partial-
read frames, dismissal narrative). Caller's job to wrap with LLM
fallback when this returns None or when narrative fields matter.
"""
from __future__ import annotations

import json
import re
from typing import Any


# JSON tag line at the start of every SCOUT response (defined by
# SCOUT_PROMPT STEP 1). Captures camera_view + frame_phase tags.
_JSON_TAG_LINE = re.compile(r"^\s*(\{[^}]+\})", re.MULTILINE)

# STRIP line. Fields are pipe-delimited; values are either tokens
# (team abbr, names, numbers) or the literal word 'null'.
_STRIP_LINE = re.compile(
    r"^STRIP:\s*(?P<body>.+?)$", re.MULTILINE | re.IGNORECASE)

# Score header inside STRIP body: TEAM RUNS-WKTS (OVERS)
# Team token: 2-4 uppercase letters or 'null'. Score: digits or 'null'.
_STRIP_HEAD = re.compile(
    r"""
    ^\s*
    (?P<team>[A-Z]{2,5}|null)\s+
    (?P<runs>\d+|null)-(?P<wkts>\d+|null)\s+
    \(\s*(?P<overs>\d+(?:\.\d+)?|null)\s*\)
    """,
    re.VERBOSE,
)

# Batter row: optional * or > striker indicator, then NAME with
# possibly multiple words, then runs(balls). Allow 'null' tokens.
# Names are lazy-matched up to the runs(balls) anchor.
_BATTER_ROW = re.compile(
    r"""
    \|\s*
    (?P<striker>\*|>)?
    \s*
    (?P<name>(?:null|[A-Za-z][A-Za-z' .\-]*?))
    \s+
    (?P<runs>\d+|null)\s*\(\s*(?P<balls>\d+|null)\s*\)
    """,
    re.VERBOSE,
)

# Bowler row: NAME W-R (O) at the end of the STRIP body.
_BOWLER_ROW = re.compile(
    r"""
    \|\s*
    (?P<name>(?:null|[A-Za-z][A-Za-z' .\-]*?))
    \s+
    (?P<wkts>\d+|null)-(?P<runs>\d+|null)\s*\(\s*(?P<overs>\d+(?:\.\d+)?|null)\s*\)
    \s*$
    """,
    re.VERBOSE,
)

# 2026-05-13 (#66): VISIBLE_TEXT alternate-format batter rows.  Some
# Scout outputs in the same session emit pipe-delimited STRIP rows
# ('| NAMAN 26(20) | TILAK 21(20) |') while others truncate STRIP to
# just the score header and put the batter data into VISIBLE_TEXT
# with a '>' striker marker and space-separated stats:
#   VISIBLE_TEXT: MI 101-3 11.5 > NAMAN TILAK 38 28 34 28 RUN-RATE ...
# or with the marker between the two names:
#   VISIBLE_TEXT: ... NAMAN > TILAK 38 28 33 27 RUN-RATE ...
# Both layouts are scanned only when the STRIP-body batter scan
# returned zero rows, so the standard pipe-delimited path stays
# primary.  Stats may be present (two number pairs after the names)
# but are optional — names alone are enough for the per-entity
# ConfidenceTracker observe() calls; ScoreManager keeps the strip's
# runs/balls authority when STRIP itself parses cleanly.
_VT_LINE = re.compile(r"VISIBLE_TEXT\s*:\s*(?P<body>.+?)$",
                      re.MULTILINE | re.IGNORECASE)
_VT_BATTERS_PREFIX_GT = re.compile(
    r">\s+(?P<striker>[A-Z][A-Za-z']{2,})\s+(?P<non>[A-Z][A-Za-z']{2,})"
    r"(?:\s+(?P<sr>\d+)\s+(?P<sb>\d+)\s+(?P<nr>\d+)\s+(?P<nb>\d+))?",
)
_VT_BATTERS_INFIX_GT = re.compile(
    r"(?P<non>[A-Z][A-Za-z']{2,})\s+>\s+(?P<striker>[A-Z][A-Za-z']{2,})"
    r"(?:\s+(?P<sr>\d+)\s+(?P<sb>\d+)\s+(?P<nr>\d+)\s+(?P<nb>\d+))?",
)

# extras= and this_over= mid-strip tokens.
_EXTRAS = re.compile(r"extras\s*=\s*(?P<v>\d+|null)", re.IGNORECASE)
_THIS_OVER = re.compile(r"this_over\s*=\s*(?P<v>\S+)", re.IGNORECASE)

# Innings-2 / chase phrases anywhere in the SCOUT response.
_CHASE_RUNS_BALLS = re.compile(
    r"(?:NEED\s+|TO\s+WIN\s+)?(\d+)\s+(?:RUNS?\s+)?(?:FROM|OFF)\s+(\d+)\s+BALLS?",
    re.IGNORECASE,
)
_TARGET = re.compile(r"\bTARGET[\s:]+(\d+)\b", re.IGNORECASE)
_REQUIRED_RATE = re.compile(
    r"REQUIRED\s+(?:RUN[-\s]?RATE|RR)\s*[:=]?\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_RUN_RATE = re.compile(
    r"RUN[-\s]?RATE\s*[:=]?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_PROJECTED_SCORE = re.compile(
    r"(?:PROJECTED|PAR|PREDICTED)\s+SCORE\s*[:=]?\s*(\d+)", re.IGNORECASE)


def _parse_num_or_null(token: str | None) -> int | None:
    if token is None or token.lower() == "null":
        return None
    try:
        return int(token)
    except ValueError:
        return None


def _parse_overs_or_null(token: str | None) -> float | None:
    if token is None or token.lower() == "null":
        return None
    try:
        return float(token)
    except ValueError:
        return None


def _parse_tag_line(text: str) -> dict[str, Any]:
    """Parse the JSON tag line on row 1 of the SCOUT response.
    Returns whatever fields it carries; missing → empty dict."""
    m = _JSON_TAG_LINE.search(text)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


def _camera_view_to_frame_type(cam: str | None,
                               has_strip: bool,
                               has_overlay: bool) -> str:
    if cam == "ad":
        return "ad"
    if has_overlay or cam == "graphic":
        return "graphic"
    if cam == "replay":
        return "graphic"
    if cam == "closeup" or cam == "other":
        return "closeup"
    if cam in ("bowlers_end", "side_on"):
        return "scoreboard" if has_strip else "closeup"
    return "closeup"


def parse_strip(text: str,
                team_a: str | None = None,
                team_b: str | None = None) -> dict[str, Any] | None:
    """Try to parse SCOUT response with regex.  Returns a dict shaped
    like the LLM Extractor's JSON output for state-derivation fields,
    or ``None`` to signal "couldn't extract — caller should fall back
    to LLM".

    The caller doesn't need ``team_a`` / ``team_b`` for parsing but
    they're accepted so this function can be a drop-in replacement
    for ``Extractor.extract`` signature later.
    """
    if not text:
        return None

    tag = _parse_tag_line(text)
    has_strip = bool(tag.get("has_strip"))
    has_overlay = bool(tag.get("has_overlay_stats"))
    cam = tag.get("camera_view")
    frame_phase = tag.get("frame_phase")
    frame_type = _camera_view_to_frame_type(cam, has_strip, has_overlay)

    # Locate the STRIP line.
    strip_match = _STRIP_LINE.search(text)
    if not strip_match:
        # No STRIP line at all — let LLM handle (probably ad / replay
        # / corrupted frame). Return None to fall back.
        return None
    strip_body = strip_match.group("body").strip()

    # All-null sentinel STRIP from the new SCOUT_PROMPT means "I
    # couldn't read pixels". Return a no-data response — no need for
    # LLM round-trip on this.
    if strip_body.lower().startswith("null null-null"):
        return {
            "frame_type": frame_type,
            "has_scorecard_data": False,
            "camera_view": cam,
            "frame_phase": frame_phase,
            "_extract_path": "regex_null",
        }

    head_match = _STRIP_HEAD.match(strip_body)
    if not head_match:
        return None  # malformed STRIP — let LLM try

    team = head_match.group("team")
    if team and team.lower() == "null":
        team = None
    score = _parse_num_or_null(head_match.group("runs"))
    wickets = _parse_num_or_null(head_match.group("wkts"))
    overs = _parse_overs_or_null(head_match.group("overs"))

    # batters and bowler — walk the pipe-separated tail.
    batters: list[dict[str, Any]] = []
    bowler: dict[str, Any] = {}
    # Bowler row matches at end of strip body; remove it before
    # batter-row scan so the bowler row isn't mistaken for a batter.
    bowl_m = _BOWLER_ROW.search(strip_body)
    if bowl_m:
        bname = bowl_m.group("name").strip()
        if bname.lower() != "null" and bname:
            bowler = {
                "name": bname,
                "wickets": _parse_num_or_null(bowl_m.group("wkts")),
                "runs": _parse_num_or_null(bowl_m.group("runs")),
                "overs": bowl_m.group("overs") if bowl_m.group("overs") != "null" else None,
            }
        strip_for_batters = strip_body[:bowl_m.start()]
    else:
        strip_for_batters = strip_body

    for bm in _BATTER_ROW.finditer(strip_for_batters):
        nm = bm.group("name").strip()
        if not nm or nm.lower() == "null":
            continue
        # Avoid picking up the head's "TEAM RUNS-WKTS" again — head
        # match precedes the first pipe so batter regex should never
        # match it, but guard anyway.
        if any(nm == b["name"] for b in batters):
            continue
        batters.append({
            "name": nm,
            "runs": _parse_num_or_null(bm.group("runs")),
            "balls": _parse_num_or_null(bm.group("balls")),
            "striker": bm.group("striker") in ("*", ">"),
        })

    # 2026-05-13 (#66): VISIBLE_TEXT fallback for the alternate Scout
    # layout where STRIP is truncated to the score header and batter
    # data is space-separated on the VISIBLE_TEXT line.  Only runs
    # when the STRIP-body scan above found nothing.  Stats are
    # ambiguous in this layout (PREFIX vs INFIX disagree on which
    # number pair belongs to which batter) so we surface names only
    # and let ScoreManager keep its STRIP-driven runs/balls authority.
    if not batters:
        vt_m = _VT_LINE.search(text)
        if vt_m:
            vt_body = vt_m.group("body")
            alt_m = _VT_BATTERS_PREFIX_GT.search(vt_body)
            if not alt_m:
                alt_m = _VT_BATTERS_INFIX_GT.search(vt_body)
            if alt_m:
                _str_name = alt_m.group("striker").strip()
                _non_name = alt_m.group("non").strip()
                batters.append({
                    "name": _str_name,
                    "runs": None,
                    "balls": None,
                    "striker": True,
                })
                batters.append({
                    "name": _non_name,
                    "runs": None,
                    "balls": None,
                    "striker": False,
                })

    extras_m = _EXTRAS.search(strip_body)
    extras_runs = (
        _parse_num_or_null(extras_m.group("v")) if extras_m else None)
    this_over_m = _THIS_OVER.search(strip_body)
    this_over_val = this_over_m.group("v") if this_over_m else None
    if this_over_val and this_over_val.lower() == "null":
        this_over_val = None

    # ── prose fields (target / run_rate / chase data) ──
    chase_m = _CHASE_RUNS_BALLS.search(text)
    runs_needed = (
        int(chase_m.group(1)) if chase_m else None)
    balls_remaining = (
        int(chase_m.group(2)) if chase_m else None)

    target_m = _TARGET.search(text)
    target = int(target_m.group(1)) if target_m else None

    required_rate_m = _REQUIRED_RATE.search(text)
    required_rate = (
        float(required_rate_m.group(1)) if required_rate_m else None)

    run_rate_m = _RUN_RATE.search(text)
    run_rate = (
        float(run_rate_m.group(1)) if run_rate_m
        and not required_rate_m else None)  # avoid double-match
    if required_rate_m and run_rate_m and run_rate_m.start() != required_rate_m.start():
        # Both present and at different positions — keep both
        run_rate = float(run_rate_m.group(1))

    projected_m = _PROJECTED_SCORE.search(text)
    projected_score = (
        int(projected_m.group(1)) if projected_m else None)

    batting_team_visible = team if (
        team and (team_a is None or team in (team_a, team_b)
                  or _team_matches(team, team_a) or _team_matches(team, team_b))
    ) else (team if team and team_a is None else None)

    return {
        "frame_type": frame_type,
        "has_scorecard_data": True,
        "batting_team_visible": batting_team_visible,
        "score": score,
        "wickets": wickets,
        "match_overs": overs,
        "run_rate": run_rate,
        "target": target,
        "projected_score": projected_score,
        "required_rate": required_rate,
        "runs_needed": runs_needed,
        "balls_remaining": balls_remaining,
        "batters": batters,
        "bowler": bowler or None,
        "bowlers": [],
        "extras": ({"type": None, "runs": extras_runs}
                   if extras_runs is not None else None),
        "this_over_broadcast": this_over_val,
        "dismissal": None,        # regex doesn't parse dismissal prose
        "ground_truth": False,
        "graphic_type": None,
        "graphic_team": None,
        "other_match_ticker": None,
        "field_observed": None,
        "field_graphic": None,
        "info_panel": None,
        "camera_view": cam,
        "frame_phase": frame_phase,
        "_extract_path": "regex",
    }


def _team_matches(broadcast_token: str | None,
                  full_name: str | None) -> bool:
    """Loose match: 'MI' matches 'Mumbai Indians', 'RCB' matches
    'Royal Challengers Bengaluru', etc.  Used to validate the team
    abbreviation pulled out of STRIP against the configured match
    teams."""
    if not broadcast_token or not full_name:
        return False
    tok = broadcast_token.upper().strip()
    full = full_name.upper().strip()
    if tok == full:
        return True
    # Acronym match: first letters of each word in full == tok
    acronym = "".join(w[0] for w in full.split() if w)
    if tok == acronym:
        return True
    # Prefix
    if full.startswith(tok) or tok in full:
        return True
    return False
