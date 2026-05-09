"""Part B shadow-eval prompt variants (V1 / V2a / V2b / V3, cumulative).

Each variant produces a `prompt` string and a `normaliser` function that
takes Scout's raw JSON tag dict and returns a canonicalised
`(camera_view, frame_phase)` pair.  V1 is the current SCOUT_PROMPT plus
the alias re-point; V2a/V2b/V3 layer cumulative prompt-text edits.

The prompts are copy-pasted from the agreed Part B drafts (see
conversation on 2026-04-24).  Any wording divergence from those drafts
is a bug.
"""
from __future__ import annotations

# ---------------------------------------------------------------------
# Alias tables
# ---------------------------------------------------------------------
# V0: the alias table deployed in vision.py today.
ALIAS_BASELINE = {
    "bowler_end": "bowlers_end", "bowlers": "bowlers_end",
    "wide_shot": "bowlers_end", "wide": "bowlers_end",
    "side": "side_on", "sideon": "side_on",
    "close_up": "closeup", "close-up": "closeup",
    "replay_slow_mo": "replay", "slow_mo": "replay",
    "advertisement": "ad", "commercial": "ad",
    "fullscreen_graphic": "graphic", "scorecard_graphic": "graphic",
}

# V1+: re-point wide_shot / wide to side_on (not bowlers_end).
ALIAS_REPOINTED = {
    "bowler_end": "bowlers_end", "bowlers": "bowlers_end",
    "wide_shot": "side_on", "wide": "side_on",
    "side": "side_on", "sideon": "side_on",
    "close_up": "closeup", "close-up": "closeup",
    "replay_slow_mo": "replay", "slow_mo": "replay",
    "advertisement": "ad", "commercial": "ad",
    "fullscreen_graphic": "graphic", "scorecard_graphic": "graphic",
}

CAMERA_VIEW_ALLOWED = {
    "bowlers_end", "side_on", "closeup", "replay",
    "graphic", "ad", "other",
}
FRAME_PHASE_ALLOWED = {
    "runup", "release", "flight", "shot", "post_shot",
    "fielder_reaction", "replay", "between_play", "graphic",
    "advertisement", "other",
}


def canon(raw_cam: str | None, raw_phase: str | None,
          alias: dict[str, str]) -> tuple[str | None, str | None]:
    """Apply alias + allowed-set filter; return (None, None) on miss."""
    cam = (raw_cam or "").strip().lower() or None
    phase = (raw_phase or "").strip().lower() or None
    if cam in alias:
        cam = alias[cam]
    if cam not in CAMERA_VIEW_ALLOWED:
        cam = None
    if phase not in FRAME_PHASE_ALLOWED:
        phase = None
    return cam, phase


# ---------------------------------------------------------------------
# The baseline SCOUT_PROMPT (as-is today in files/eyes/vision.py:60-158)
# ---------------------------------------------------------------------
# V1 reuses this text unmodified; V2a/V2b/V3 mutate sections of it.
# Keep this in sync with vision.py by re-extracting if the prompt is
# edited.  For shadow runs the {vision_hint} is always substituted with
# "None — first frame or no issues."  so the prompts are directly
# comparable.
PROMPT_V1 = """\
You are reading a live IPL cricket broadcast frame.

STEP 1 — CLASSIFY. Output this JSON on the FIRST line, nothing before it:
{{"has_strip": true, "has_overlay_stats": false, "drs_review": false, \
"camera_view": "bowlers_end", "frame_phase": "release", \
"ball_position": null}}

has_strip: Is the team score strip visible at the bottom?
has_overlay_stats: Are career/tournament/head-to-head stats shown as an \
OVERLAY on top of the live feed? (NOT the regular scoreboard strip)
drs_review: Is a DRS review decision being shown?

camera_view: ONE of these exact strings, describing the camera angle:
  - "bowlers_end": the standard wide shot down the pitch from the \
    bowler's end (bowler running in / mid-delivery / batter at crease \
    visible from behind the stumps).  This is the delivery-action \
    camera.
  - "side_on": square / side-on field camera (e.g. third-man or fine-\
    leg angle on a boundary chase).
  - "closeup": closeup of a player (batter, bowler, fielder, captain, \
    crowd individual) — face / upper body fills the frame.
  - "replay": clearly a replay or slow-motion of an earlier moment \
    (replay logo, slow-mo motion blur, "REPLAY" badge).
  - "graphic": full-screen broadcaster graphic (full scorecard, \
    partnership graphic, statistical overlay, sponsor card).
  - "ad": commercial / advertisement break.
  - "other": pre-match presenter, post-match presentation, drinks \
    break, anything else.

frame_phase: ONE of these exact strings, describing the MOMENT of the \
delivery this frame shows.  Use the visual signature, not your guess:
  - "runup": Camera behind the bowler looking down the pitch.  The \
    bowler is walking or running toward the crease.  The ball is in \
    the bowler's hand.  The batter is at the far crease, often \
    taking guard.
  - "release": Camera still behind the bowler.  The bowler is in \
    their delivery stride — front foot landing, arm coming through, \
    or arm at the top of the action.  The ball may still be in the \
    hand or just released.
  - "flight": Camera behind the bowler.  The ball has left the \
    bowler's hand and is visible in the air between the bowler's end \
    and the batter.  The batter is preparing to play a shot.  Bowler \
    in follow-through.
  - "shot": Camera behind the bowler (or a tight angle).  The ball \
    has been struck / defended / left.  The bat is in motion through \
    the shot or just after contact.
  - "post_shot": The shot has been played.  Camera may still be on \
    bowler's end briefly, or has just cut to follow the ball.  The \
    batter has completed the shot motion.
  - "fielder_reaction": Camera has cut to a fielder running after \
    the ball, diving, catching, throwing, OR a celebration huddle \
    around the stumps after a wicket.  The pitch is no longer the \
    focus.
  - "replay": Slow-motion replay, spider-cam, close-up of ball/bat \
    contact, wagon wheel, hawkeye, stats overlay over live feed.
  - "between_play": Cricket visible but no delivery happening.  \
    Bowler walking back to mark, field change, drinks, batter \
    signalling for new bat, umpire discussion.
  - "graphic": Full-screen / near-full-screen broadcaster graphic.  \
    Score summary, partnership stats, player profile, sponsor.
  - "advertisement": Commercial break, no cricket content visible.
  - "other": none of the above.

ball_position: If you can clearly see the ball in flight as a small \
white object between the bowler's end and the batter, give its \
position as {{"x": 0.0..1.0, "y": 0.0..1.0}} where (0,0) is top-left.  \
Only set this for "release", "flight", or "shot" phases.  Otherwise \
return null.  Do NOT guess — if the ball is not clearly visible as a \
small object in flight, return null.

STEP 2 — READ THE STRIP (skip if has_strip is false).
Output the strip data in this exact format:
STRIP: [TEAM] [SCORE]-[WICKETS] ([OVERS]) | [BATTER1] [RUNS]([BALLS]) | \
[BATTER2] [RUNS]([BALLS]) | [BOWLER] [W]-[R] ([OVERS])

Example: STRIP: KKR 105-2 (11.3) | Green 45(32) | Raghuvanshi 4(5) | \
Siddharth 0-21 (2.3)

STEP 3 — REPORT OVERLAYS (skip if nothing visible):
INFO_PANEL: [career/tournament/head-to-head text]
SPEED: [number] (bowling speed in kph)
EXTRA: wide/no_ball/leg_bye/bye
THIS OVER: [ball-by-ball results]
FULL SCORECARD: [every batter/bowler row]

STEP 4 — ACTION (1 sentence):
What is happening? (delivery bowled, shot played, celebration, etc.)

RULES:
- JSON tag line MUST be first. Then strip. Then overlays. Then action.
- Report exact numbers from the strip. Don't guess or infer.
- * or > prefix on batter name = striker.
- If this is a pure ADVERTISEMENT with no strip: output the JSON with \
all false, then say "ADVERTISEMENT" and stop.

HINT FROM SCORER:
None — first frame or no issues.\
"""


# ---------------------------------------------------------------------
# V2a: harden bowlers_end + release/flight/shot.  Closeup unchanged.
# ---------------------------------------------------------------------
_V2A_BOWLERS_END = """\
  - "bowlers_end": the standard wide shot down the pitch from BEHIND \
    the bowler.  REQUIRED: the pitch extends away from the camera \
    toward the far stumps.  The bowler or the batter (or both) is \
    typically visible — the bowler at or near the foreground, the \
    batter at the far crease (often small, in the upper half of the \
    frame).  If the camera is square to the pitch from the sideline \
    (third-man, fine-leg, square-leg), this is "side_on", not \
    "bowlers_end".  This is the only camera where a legal ball can \
    be delivered on-screen."""

_V2A_RELEASE = """\
  - "release": Camera BEHIND the bowler looking down the pitch.  \
    REQUIRED: the pitch extends away from the camera AND the bowler \
    is in delivery stride (front foot landing, arm coming through, \
    or arm at the top of the action).  The batter should be visible \
    at the far crease, though may be partially occluded by umpire or \
    non-striker.  If the bowler is not visible at all (full closeup \
    of the batter, umpire, fielder, or a replay), this is NOT \
    release."""

_V2A_FLIGHT = """\
  - "flight": Camera BEHIND the bowler looking down the pitch.  \
    REQUIRED: the pitch extends away from the camera AND the ball \
    has left the bowler's hand (the bowler is typically in follow-\
    through or has just exited the frame).  The batter should be \
    visible at the far crease preparing to play, though may be \
    partially occluded.  If the camera is not looking down the pitch \
    from behind the bowler's end, this is NOT flight."""

_V2A_SHOT = """\
  - "shot": Camera BEHIND the bowler (or a tight over-the-shoulder \
    angle from behind the stumps).  REQUIRED: the pitch extends away \
    from the camera AND the bat is in motion through the shot or \
    just after contact.  A batter close-up without the pitch \
    extending away is NOT "shot" — it is "closeup" or "post_shot"."""


# ---------------------------------------------------------------------
# V2b: V2a + broadened closeup (face/body dominant even with pitch in bg).
# ---------------------------------------------------------------------
_V2B_CLOSEUP = """\
  - "closeup": a player's face or upper body fills a substantial \
    portion of the frame (batter at the non-striker's end, bowler \
    walking back, fielder reaction, captain directing, coach, crowd \
    individual).  Use this tag whenever face/body is the visual \
    subject, EVEN IF the pitch, stumps, or fielders are partly \
    visible in the background.  A frame where the pitch does NOT \
    extend away from the camera toward the far stumps is almost \
    always closeup, not bowlers_end."""


# ---------------------------------------------------------------------
# V3: V2b + disambiguation block appended before `ball_position:` line.
# ---------------------------------------------------------------------
_V3_DISAMBIG = """\
DISAMBIGUATION — common mistakes to avoid:

These frames are NEVER "bowlers_end" and NEVER an action phase \
(release/flight/shot), even if cricket is visible:
  * Batter close-up at the striker's end (face-dominant, stumps and \
    pitch behind the batter visible in the background) → closeup + \
    post_shot or between_play.
  * Bowler close-up at the start or end of their mark (face/\
    shoulders dominant, pitch visible behind) → closeup + runup or \
    between_play.
  * Post-wicket celebration huddle near the stumps → side_on or \
    closeup + fielder_reaction.
  * Umpire / third-umpire consultation frame → closeup or graphic + \
    between_play.
  * Hawkeye / ball-tracker / wagon-wheel / pitch-map overlay on the \
    live feed → graphic + graphic (phase).
  * Crowd shot, dugout shot, coach reaction → closeup + between_play.

These ARE "bowlers_end" and an action phase:
  * The pitch extends away from the camera toward the far stumps, \
    the bowler is in view running in or delivering (or has just \
    released and is in follow-through), and the batter is at the far \
    crease (may be partly occluded).
  * Immediately after contact, while the camera is still behind the \
    bowler and the pitch is still extending away.

"""


# ---------------------------------------------------------------------
# Original text spans in PROMPT_V1 (literal replacement anchors).
# ---------------------------------------------------------------------
_V1_BOWLERS_END = """\
  - "bowlers_end": the standard wide shot down the pitch from the \
    bowler's end (bowler running in / mid-delivery / batter at crease \
    visible from behind the stumps).  This is the delivery-action \
    camera."""

_V1_CLOSEUP = """\
  - "closeup": closeup of a player (batter, bowler, fielder, captain, \
    crowd individual) — face / upper body fills the frame."""

_V1_RELEASE = """\
  - "release": Camera still behind the bowler.  The bowler is in \
    their delivery stride — front foot landing, arm coming through, \
    or arm at the top of the action.  The ball may still be in the \
    hand or just released."""

_V1_FLIGHT = """\
  - "flight": Camera behind the bowler.  The ball has left the \
    bowler's hand and is visible in the air between the bowler's end \
    and the batter.  The batter is preparing to play a shot.  Bowler \
    in follow-through."""

_V1_SHOT = """\
  - "shot": Camera behind the bowler (or a tight angle).  The ball \
    has been struck / defended / left.  The bat is in motion through \
    the shot or just after contact."""


def _build(v1_text: str, *,
           bowlers_end: str | None = None,
           release: str | None = None,
           flight: str | None = None,
           shot: str | None = None,
           closeup: str | None = None,
           disambig: str | None = None) -> str:
    out = v1_text
    if bowlers_end is not None:
        assert _V1_BOWLERS_END in out, "V1 bowlers_end anchor missing"
        out = out.replace(_V1_BOWLERS_END, bowlers_end)
    if release is not None:
        assert _V1_RELEASE in out, "V1 release anchor missing"
        out = out.replace(_V1_RELEASE, release)
    if flight is not None:
        assert _V1_FLIGHT in out, "V1 flight anchor missing"
        out = out.replace(_V1_FLIGHT, flight)
    if shot is not None:
        assert _V1_SHOT in out, "V1 shot anchor missing"
        out = out.replace(_V1_SHOT, shot)
    if closeup is not None:
        assert _V1_CLOSEUP in out, "V1 closeup anchor missing"
        out = out.replace(_V1_CLOSEUP, closeup)
    if disambig is not None:
        anchor = "ball_position: If you can clearly see"
        assert anchor in out, "disambig anchor missing"
        out = out.replace(anchor, disambig + anchor)
    return out


PROMPT_V2A = _build(
    PROMPT_V1,
    bowlers_end=_V2A_BOWLERS_END,
    release=_V2A_RELEASE,
    flight=_V2A_FLIGHT,
    shot=_V2A_SHOT,
)

PROMPT_V2B = _build(
    PROMPT_V1,
    bowlers_end=_V2A_BOWLERS_END,
    release=_V2A_RELEASE,
    flight=_V2A_FLIGHT,
    shot=_V2A_SHOT,
    closeup=_V2B_CLOSEUP,
)

PROMPT_V3 = _build(
    PROMPT_V1,
    bowlers_end=_V2A_BOWLERS_END,
    release=_V2A_RELEASE,
    flight=_V2A_FLIGHT,
    shot=_V2A_SHOT,
    closeup=_V2B_CLOSEUP,
    disambig=_V3_DISAMBIG,
)


# V4 — example-swap hypothesis test.
# The STEP 1 example JSON in PROMPT_V1 hard-codes
#   "camera_view": "bowlers_end", "frame_phase": "release"
# Inspection of shadow-run raws shows Scout copies this literal pair
# on most frames regardless of prompt instructions below — i.e. the
# model treats the example as the default answer rather than a
# template.  V4 tests the hypothesis that swapping the example to a
# neutral "other"/"other" pair (which is a valid but *unlikely* answer
# for live cricket) forces Scout to actually classify instead of
# defaulting.  If V4 shifts precision materially while all of
# V1/V2a/V2b/V3 did not, the lever is the example, not the rulebook.
_V1_STEP1_EXAMPLE = (
    '{{"has_strip": true, "has_overlay_stats": false, "drs_review": false, '
    '"camera_view": "bowlers_end", "frame_phase": "release", '
    '"ball_position": null}}'
)
_V4_STEP1_EXAMPLE = (
    '{{"has_strip": true, "has_overlay_stats": false, "drs_review": false, '
    '"camera_view": "other", "frame_phase": "other", '
    '"ball_position": null}}'
)
assert _V1_STEP1_EXAMPLE in PROMPT_V1, "V1 step-1 example anchor missing"
PROMPT_V4 = PROMPT_V1.replace(_V1_STEP1_EXAMPLE, _V4_STEP1_EXAMPLE)

# V4b — V2a rulebook tightening + neutral example (the combined lever).
PROMPT_V4B = PROMPT_V2A.replace(_V1_STEP1_EXAMPLE, _V4_STEP1_EXAMPLE)


# V5 — V2b rulebook + balanced multi-example showing camera_view values
# spanning the taxonomy.  The hypothesis: a single example with
# "bowlers_end" creates a default attractor; showing three examples for
# three broadcast contexts (delivery / closeup / graphic) forces Scout
# to actually classify instead of copying the first example.  Explicit
# "DO NOT copy example values" instruction added defensively.
_V5_STEP1_BLOCK = """\
STEP 1 — CLASSIFY. Output one JSON object on the FIRST line, nothing \
before it.  Pick `camera_view` and `frame_phase` from the enums below \
by looking at the ACTUAL frame.  Example JSON shapes for three common \
broadcast contexts (these are format guides — DO NOT copy the values, \
pick the value that matches the frame):

- During a delivery (camera behind bowler, pitch extends away): \
{{"has_strip": true, "has_overlay_stats": false, "drs_review": false, \
"camera_view": "bowlers_end", "frame_phase": "release", \
"ball_position": null}}
- During a player closeup (face/body fills frame): \
{{"has_strip": true, "has_overlay_stats": false, "drs_review": false, \
"camera_view": "closeup", "frame_phase": "between_play", \
"ball_position": null}}
- During a full-screen broadcaster graphic (scorecard, partnership): \
{{"has_strip": false, "has_overlay_stats": true, "drs_review": false, \
"camera_view": "graphic", "frame_phase": "graphic", \
"ball_position": null}}
"""

# The V1 STEP 1 block (to replace).
_V1_STEP1_BLOCK = (
    "STEP 1 — CLASSIFY. Output this JSON on the FIRST line, nothing "
    "before it:\n"
    + _V1_STEP1_EXAMPLE
    + "\n"
)
assert _V1_STEP1_BLOCK in PROMPT_V1, "V1 step-1 block anchor missing"
PROMPT_V5 = PROMPT_V2B.replace(_V1_STEP1_BLOCK, _V5_STEP1_BLOCK)


# ---------------------------------------------------------------------
# V6c — V5 STEP-1 closeup example rewritten on the discrimination
# boundary.
#
# V5 production evaluation (DC vs PBKS, 23 stratified bowlers_end
# frames, 2026-04-25) found 34.8% strict precision — a real 1.85x lift
# over V0 (~15%) but in the marginal band (25-40%) of the
# pre-committed thresholds.  Failure-mode breakdown showed 40% of FPs
# were closeup frames where the camera angle is from the bowler's-end
# direction but the pitch does NOT recede away (face dominant, stumps
# sometimes visible behind).  V5's closeup example anchored on the
# obvious case ("face/body fills frame") and offered no anchor for
# this boundary.
#
# V6c keeps V5's three-example structure intact (the V4 diagnostic
# showed the example block is the dominant control surface) and
# rewrites only the closeup scenario sentence to lift the
# discrimination test ("no full pitch receding away") into the
# example.  Same length, same example count, same JSON shape.  V0 is
# the production deploy, V5 is the current-shipping production prompt;
# corpus_v1 shadow run validates that V6c does not regress on the
# 41-frame benchmark before it sees a production-distribution test.
# ---------------------------------------------------------------------
_V5_CLOSEUP_EXAMPLE = (
    "- During a player closeup (face/body fills frame): "
    "{{\"has_strip\": true, \"has_overlay_stats\": false, "
    "\"drs_review\": false, \"camera_view\": \"closeup\", "
    "\"frame_phase\": \"between_play\", \"ball_position\": null}}"
)
_V6C_CLOSEUP_EXAMPLE = (
    "- During a closeup of a player (face/upper body fills frame, "
    "no full pitch receding away even if camera angle is from "
    "bowler's end direction): "
    "{{\"has_strip\": true, \"has_overlay_stats\": false, "
    "\"drs_review\": false, \"camera_view\": \"closeup\", "
    "\"frame_phase\": \"between_play\", \"ball_position\": null}}"
)
assert _V5_CLOSEUP_EXAMPLE in PROMPT_V5, "V5 closeup example anchor missing"
PROMPT_V6C = PROMPT_V5.replace(_V5_CLOSEUP_EXAMPLE, _V6C_CLOSEUP_EXAMPLE)
assert PROMPT_V6C != PROMPT_V5, "V6c closeup swap was a no-op"

# ---------------------------------------------------------------------
# V6d — V6c base + targeted f941 escalation fix.
#
# V6c (closeup STEP-1 example tightened with "no full pitch receding
# away" discrimination) preserved f205/f748 closeup remediation but
# inadvertently turned the closeup example into a discrimination GATE
# rather than an inclusive attractor: frames that fail both the
# closeup test (no face dominance + no pitch receding) and the
# delivery signature now fall back to the FIRST STEP-1 example's
# default literal pair (bowlers_end/release).  f941 (atmospheric
# stadium / drone show, no pitch) lands stably on bowlers_end across
# all 3 V6c replicates — operational severity escalation per
# files/docs/investigations/scout_v6c_replicate_runs_decision.md §4.
#
# V6d edits ONLY:
#   (A) the bowlers_end STEP-1 example parenthetical — adds a
#       symmetric negative discrimination test ("NOT atmospheric/
#       crowd/stadium shots without a visible cricket pitch — those
#       are 'other'") to mirror the V6c closeup tightening pattern,
#       which V4 (variants.py:350-372) established as the dominant
#       prompt control surface.
#   (B) the "other" rulebook entry — appends explicit visual-
#       signature enumeration matching f941/f942/f020/f749 corpus
#       notes, giving "other" a stronger positive landing zone for
#       no-pitch ambiguous frames.
#
# V6d preserves _V6C_CLOSEUP_EXAMPLE byte-identically (f205/f748
# remediation by construction) and does NOT change the bowlers_end
# rulebook, the closeup rulebook, the side_on rulebook, the STEP 1
# example count or ordering, or any STEP 2-4 content.  Schema /
# alias / canon machinery untouched.
# ---------------------------------------------------------------------
_V5_BOWLERS_END_EXAMPLE = (
    "- During a delivery (camera behind bowler, pitch extends away): "
    "{{\"has_strip\": true, \"has_overlay_stats\": false, "
    "\"drs_review\": false, \"camera_view\": \"bowlers_end\", "
    "\"frame_phase\": \"release\", \"ball_position\": null}}"
)
_V6D_BOWLERS_END_EXAMPLE = (
    "- During a delivery (camera behind bowler AND pitch extends "
    "away toward the far stumps; NOT atmospheric/crowd/stadium "
    "shots without a visible cricket pitch — those are \"other\"): "
    "{{\"has_strip\": true, \"has_overlay_stats\": false, "
    "\"drs_review\": false, \"camera_view\": \"bowlers_end\", "
    "\"frame_phase\": \"release\", \"ball_position\": null}}"
)

# Anchor must match PROMPT_V1 whitespace (design §7.b backslash form
# does not match the literal concatenation in this repo).
_V1_OTHER_RULEBOOK = (
    '  - "other": pre-match presenter, post-match presentation, '
    'drinks     break, anything else.'
)
_V6D_OTHER_RULEBOOK = (
    '  - "other": pre-match presenter, post-match presentation, '
    'drinks     break, atmospheric/stadium/crowd shots without '
    'a visible cricket pitch (drone shows, boundary-board close-ups, '
    'wide stand crowds, dark camera-side angles), '
    'anything else.'
)

assert _V5_BOWLERS_END_EXAMPLE in PROMPT_V6C, (
    "V5 bowlers_end example anchor missing in V6c")
assert _V1_OTHER_RULEBOOK in PROMPT_V6C, (
    "V1 'other' rulebook anchor missing in V6c")
PROMPT_V6D = (
    PROMPT_V6C
    .replace(_V5_BOWLERS_END_EXAMPLE, _V6D_BOWLERS_END_EXAMPLE)
    .replace(_V1_OTHER_RULEBOOK, _V6D_OTHER_RULEBOOK)
)
assert PROMPT_V6D != PROMPT_V6C, "V6d edits were a no-op"
assert (PROMPT_V6D.count("\"camera_view\": \"bowlers_end\"") ==
        PROMPT_V6C.count("\"camera_view\": \"bowlers_end\"")), (
    "V6d unintentionally changed bowlers_end example count")
assert _V6C_CLOSEUP_EXAMPLE in PROMPT_V6D, (
    "V6d must preserve V6c closeup example byte-identically")

# ---------------------------------------------------------------------
# V6e — V6d base + explicit side_on / boundary fielding preservation.
#
# V6d bowlers_end STEP-1 tightened for f941 no-pitch frames but routed
# pbks_rr_f600 (boundary chase) to bowlers_end. V6e adds a semicolon-
# delimited third NOT clause (side-on/lateral chase) mirroring V6d's
# atmospheric pattern. Design: scout_v6e_design.md
# ---------------------------------------------------------------------
_V6E_BOWLERS_END_EXAMPLE = (
    "- During a delivery (camera behind bowler AND pitch extends "
    "away toward the far stumps; NOT atmospheric/crowd/stadium "
    "shots without a visible cricket pitch — those are \"other\"; "
    "NOT side-on/lateral camera angles showing fielder running "
    "parallel to boundary rope or chasing ball laterally across "
    "frame — those are \"side_on\"): "
    "{{\"has_strip\": true, \"has_overlay_stats\": false, "
    "\"drs_review\": false, \"camera_view\": \"bowlers_end\", "
    "\"frame_phase\": \"release\", \"ball_position\": null}}"
)

assert _V6D_BOWLERS_END_EXAMPLE in PROMPT_V6D, (
    "V6d bowlers_end example anchor missing in PROMPT_V6D — "
    "re-derive from literal slice at variants.py:495-502")
PROMPT_V6E = PROMPT_V6D.replace(
    _V6D_BOWLERS_END_EXAMPLE,
    _V6E_BOWLERS_END_EXAMPLE,
)
assert PROMPT_V6E != PROMPT_V6D, "V6e edit is a no-op"
assert _V6C_CLOSEUP_EXAMPLE in PROMPT_V6E, (
    "V6e must preserve V6c closeup example byte-identically")
assert _V6D_OTHER_RULEBOOK in PROMPT_V6E, (
    "V6e must preserve V6d other rulebook entry")
assert (PROMPT_V6E.count("\"camera_view\": \"bowlers_end\"") ==
        PROMPT_V6D.count("\"camera_view\": \"bowlers_end\"")), (
    "V6e unintentionally changed bowlers_end example count")


def _unescape(p: str) -> str:
    """vision.py's SCOUT_PROMPT uses `{{`/`}}` as str.format escape
    pairs for literal braces (so the production template's
    `.format(vision_hint=...)` call substitutes the hint without
    eating the example-JSON curly braces).  The shadow harness does
    not call .format(), so we strip the escape here — otherwise Scout
    echoes the literal `{{...}}` pattern and our JSON parser rejects
    it."""
    return p.replace("{{", "{").replace("}}", "}")


VARIANTS = {
    "V1":  {"prompt": _unescape(PROMPT_V1),  "alias": ALIAS_REPOINTED},
    "V2a": {"prompt": _unescape(PROMPT_V2A), "alias": ALIAS_REPOINTED},
    "V2b": {"prompt": _unescape(PROMPT_V2B), "alias": ALIAS_REPOINTED},
    "V3":  {"prompt": _unescape(PROMPT_V3),  "alias": ALIAS_REPOINTED},
    "V4":  {"prompt": _unescape(PROMPT_V4),  "alias": ALIAS_REPOINTED},
    "V4b": {"prompt": _unescape(PROMPT_V4B), "alias": ALIAS_REPOINTED},
    "V5":  {"prompt": _unescape(PROMPT_V5),  "alias": ALIAS_REPOINTED},
    "V6c": {"prompt": _unescape(PROMPT_V6C), "alias": ALIAS_REPOINTED},
    "V6d": {"prompt": _unescape(PROMPT_V6D), "alias": ALIAS_REPOINTED},
    "V6e": {"prompt": _unescape(PROMPT_V6E), "alias": ALIAS_REPOINTED},
}


if __name__ == "__main__":
    # Smoke test: verify all VARIANTS entries assembled without anchor
    # misses, and print a diff summary.
    for name, v in VARIANTS.items():
        p = v["prompt"]
        print(f"{name}: {len(p)} chars")
    print()
    print("V2a-V1 delta:", len(PROMPT_V2A) - len(PROMPT_V1))
    print("V2b-V2a delta:", len(PROMPT_V2B) - len(PROMPT_V2A))
    print("V3-V2b delta:", len(PROMPT_V3) - len(PROMPT_V2B))
