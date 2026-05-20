"""Vision — Single-provider Scout 17B cricket stream watcher.

Scout 17B (Groq): ONE call does tag + read.
  max_tokens=600, ~1.0s, $0.09/match.
  Outputs a 3-boolean classification line, then reads the strip.

Returns (frame_type, description, action_description).
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import time

import cv2
import numpy as np
from groq import AsyncGroq

from eyes.config import GROQ_API_KEY, GROQ_PRIMARY_MODEL
from eyes.cricket_logger import CricketLogger, get_global_frame

log = CricketLogger("VISION")

VALID_FRAME_TYPES = {
    "SCOREBOARD", "GRAPHIC", "CLOSEUP", "ADVERTISEMENT", "PREMATCH",
}

_SCOUT_TIMEOUT = 5.0

# Shadow-mode perceptual-hash dedup instrumentation (env-gated via
# SCOUT_DEDUP_SHADOW=1). Log-only; never alters scout call path.
# ROI fractions calibrated against the IPL-2026 4621b9f8 broadcast
# graphics package — a broadcaster lookup table is future work.
_SCOUT_DEDUP_CACHE_MAX_SIZE = 30
_SCOUT_DEDUP_TTL_SECONDS = 10.0
_SCOUT_DEDUP_THRESHOLD = 6
_SCOUT_DEDUP_ROI_RATIO = (80 / 1661, 895 / 940, 360 / 1661, 938 / 940)
_scout_dedup_cache: list[tuple] = []


def _scout_dedup_score_block_phash(frame):
    import imagehash
    from PIL import Image
    h, w = frame.shape[:2]
    rx1, ry1, rx2, ry2 = _SCOUT_DEDUP_ROI_RATIO
    x1, y1 = int(w * rx1), int(h * ry1)
    x2, y2 = int(w * rx2), int(h * ry2)
    crop = frame[y1:y2, x1:x2]
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    return imagehash.phash(Image.fromarray(rgb))


# Fix #4 (2026-04-23): template-placeholder guard.
# Scout's vision endpoint occasionally regurgitates the prompt
# template verbatim — returning literal bracketed tokens like
# "STRIP: [TEAM] [SCORE]-[WICKETS] ([OVERS]) | [BATTER1] ..."
# instead of extracting real values from the broadcast.  When that
# happens downstream parsers see "0-0" and template names, which
# poisons the scorecard with null fields and corrupted state.
#
# Defense: after Scout returns, scan the description + action for
# any of these bracketed markers.  If found, treat the frame as
# UNKNOWN (skip downstream processing) and bump the rejection
# counter for monitoring.  Grep pattern: `[SCOUT-REJECT]`.
_TEMPLATE_MARKERS = re.compile(
    r"\[(?:RUNS|BALLS|W|R|OVERS|SCORE|WICKETS|SR|WKT|"
    r"NAME|TEAM|BATTER\d*|BOWLER)\]",
    re.IGNORECASE,
)

# ── Combined tag + read prompt ──────────────────────────────────────
# 2026-04-19: extended the JSON tag with `frame_phase` and
# `ball_position` fields.  Validation on 115 frames from 31 prior
# confirmed deliveries:
#   * 100% of deliveries get >= 1 release/flight/shot frame
#   * 90% strip-parse rate (vs ~97% prior — within bounds)
#   * Avg latency 808 ms (no regression vs 1.0 s baseline)
# `frame_phase` lets `analyze_last_delivery` sample the moment of
# action (release / flight / shot) instead of the post-delivery
# camera dwell that biased the prior selection.
#
# 2026-04-24 (Part B, V5): STEP 1 rewritten from a single-example
# anchor to three balanced examples (bowlers_end / closeup / graphic)
# with an explicit "DO NOT copy the values" instruction.  Shadow run
# (41 frames × 7 variants × 3 reps = 861 calls) showed:
#   * Rulebook-only variants (V1–V3) did NOT shift bowlers_end
#     precision (15.2% baseline → ±1pp across variants).  Scout was
#     copying the STEP 1 example line byte-identically and ignoring
#     the rulebook below.
#   * V4 diagnostic (swap example camera_view "bowlers_end" → "other",
#     single-character change, rulebook unchanged) caused Scout to
#     emit "other" on 36/41 frames — proving the example block is the
#     dominant control surface for camera_view output.
#   * V5 (this prompt — three balanced examples + hardened rulebook
#     for bowlers_end / release / flight / shot / closeup) doubled
#     bowlers_end strict precision from 15.2% to 31.2% with 7 truth-
#     improving shifts, 0 regressions, and 100% recall preserved on
#     all 5 human-labeled bowlers_end frames.
# Updated 2026-05-02 per files/docs/investigations/
# strip_ocr_failure_mode_analysis.md §5 item 1:
#   - team=null when strip shows flag/logo only (stops IPL/CPL prior
#     hallucinations: KKR, RCB, MI, LSG, LIONS, etc.)
#   - overs=null when no X.Y over counter on strip (stops stealing a
#     digit from score, SR, or partnership)
#   - replaced KKR numeric example with a null-using example (examples
#     are priors — concrete team abbreviations get regurgitated).
# The ≥90% precision target is NOT met — remaining FPs are geometric
# ambiguity cases the model cannot resolve without either a stronger
# vision model, a post-hoc verification call, or temperature>0
# ensembling.  See docs/scout_shadow_run_v1_analysis.md,
# docs/scout_corpus_v1.json, docs/scout_labeling_rubric_v1.md.
SCOUT_PROMPT_VERBOSE = """\
You are reading a live IPL cricket broadcast frame.

STEP 1 — CLASSIFY. Output one JSON object on the FIRST line, nothing \
before it.  Pick `camera_view` and `frame_phase` from the enums below \
by looking at the ACTUAL frame.  Example JSON shapes for three \
common broadcast contexts (these are format guides — DO NOT copy the \
values, pick the value that matches the frame):

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

has_strip: Is the team score strip visible at the bottom?
has_overlay_stats: Are career/tournament/head-to-head stats shown as an \
OVERLAY on top of the live feed? (NOT the regular scoreboard strip)
drs_review: Is a DRS review decision being shown?

camera_view: ONE of these exact strings, describing the camera angle:
  - "bowlers_end": the standard wide shot down the pitch from BEHIND \
    the bowler.  REQUIRED: the pitch extends away from the camera \
    toward the far stumps.  The bowler or the batter (or both) is \
    typically visible — the bowler at or near the foreground, the \
    batter at the far crease (often small, in the upper half of the \
    frame).  If the camera is square to the pitch from the sideline \
    (third-man, fine-leg, square-leg), this is "side_on", not \
    "bowlers_end".  This is the only camera where a legal ball can \
    be delivered on-screen.
  - "side_on": square / side-on field camera (e.g. third-man or fine-\
    leg angle on a boundary chase).
  - "closeup": a player's face or upper body fills a substantial \
    portion of the frame (batter at the non-striker's end, bowler \
    walking back, fielder reaction, captain directing, coach, crowd \
    individual).  Use this tag whenever face/body is the visual \
    subject, EVEN IF the pitch, stumps, or fielders are partly \
    visible in the background.  A frame where the pitch does NOT \
    extend away from the camera toward the far stumps is almost \
    always closeup, not bowlers_end.
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
  - "release": Camera BEHIND the bowler looking down the pitch.  \
    REQUIRED: the pitch extends away from the camera AND the bowler \
    is in delivery stride (front foot landing, arm coming through, \
    or arm at the top of the action).  The batter should be visible \
    at the far crease, though may be partially occluded by umpire or \
    non-striker.  If the bowler is not visible at all (full closeup \
    of the batter, umpire, fielder, or a replay), this is NOT \
    release.
  - "flight": Camera BEHIND the bowler looking down the pitch.  \
    REQUIRED: the pitch extends away from the camera AND the ball \
    has left the bowler's hand (the bowler is typically in follow-\
    through or has just exited the frame).  The batter should be \
    visible at the far crease preparing to play, though may be \
    partially occluded.  If the camera is not looking down the pitch \
    from behind the bowler's end, this is NOT flight.
  - "shot": Camera BEHIND the bowler (or a tight over-the-shoulder \
    angle from behind the stumps).  REQUIRED: the pitch extends away \
    from the camera AND the bat is in motion through the shot or \
    just after contact.  A batter close-up without the pitch \
    extending away is NOT "shot" — it is "closeup" or "post_shot".
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

STEP 2 — TRANSCRIBE THE SCOREBOARD STRIP VERBATIM.
On the next line, output:
VISIBLE_TEXT: <the exact text rendered on the bottom-strip scoreboard, \
character-by-character, left-to-right, top-to-bottom>

Transcribe ONLY pixels you can actually read on THIS frame's strip. \
Don't paraphrase, don't expand abbreviations, don't substitute names \
from memory or from training data. Read what's there.

If the scoreboard strip is absent (replay, ad, full-screen graphic, \
mid-cut, no strip rendered), emit exactly: \
VISIBLE_TEXT: (none)

If the strip is partially visible or text is corrupted by decode \
artifacts / motion blur / overlay occlusion: transcribe only the \
parts you can clearly read, use ? for individual characters or words \
you cannot resolve. Do NOT guess from team context.

STEP 3 — PARSE THE STRIP FROM VISIBLE_TEXT.
Every value in the STRIP line below MUST appear verbatim in your own \
VISIBLE_TEXT output for this frame. If a field is not present in \
VISIBLE_TEXT, use null. Don't fill from priors, hint, or training data.

Output format (angle-bracket tokens are placeholders — NEVER emit \
them literally; substitute the value you transcribed in VISIBLE_TEXT \
or the literal word null):
STRIP: <team_or_null> <runs>-<wkts> (<overs>) | extras=<n_or_null> | \
this_over=<symbols_or_null> | <striker> <r>(<b>) | <nonstriker> <r>(<b>) | \
<bowler> <w>-<r> (<o>)

If VISIBLE_TEXT was (none), emit exactly:
STRIP: null null-null (null) | extras=null | this_over=null | null null(null) | \
null null(null) | null null-null (null)

Team token: If VISIBLE_TEXT doesn't include a team abbreviation, emit \
team=null. Do NOT guess from which teams might be playing. Common \
spurious outputs to avoid: inferring KKR, RCB, MI, LSG, LIONS, Paarl, \
Blue Waters, or any franchise abbreviation when not in VISIBLE_TEXT.

Overs token: If VISIBLE_TEXT has no X.Y over counter (only ball-by-\
ball dots such as THIS OVER ⊙⊙⊙ with no numeric over visible), emit \
([overs]) as (null). Do NOT take a digit from the team score (e.g. \
the 9 in 9-0), from strike rate, required rate, partnership totals, \
speed kph, or any adjacent panel.

CRITICAL — anti-priming rules (this is the regression that broke the \
2026-05-11 and 2026-05-12 matches; read carefully):
- Do NOT output player names that are not literally in VISIBLE_TEXT \
for THIS frame. Even if you know who plays for this team, even if a \
HINT below names someone, ONLY output names you transcribed in \
VISIBLE_TEXT above.
- The names "Rohit Sharma", "Suryakumar Yadav", "Harshal Patel", \
"Ishan Kishan", "Yashasvi Jaiswal", "Jasprit Bumrah", "Jadeja", and \
ALL other player names you might know from training data are \
FORBIDDEN unless they appear in VISIBLE_TEXT for THIS specific frame. \
If a batter/bowler row is unreadable, emit null for that slot.
- The score, wickets, and overs MUST match digits actually present \
in VISIBLE_TEXT. Do not echo the previous frame's score or any \
score-shaped number from the hint. If you can't read the digits this \
frame, emit null.

STEP 4 — REPORT OVERLAYS (skip if nothing visible):
INFO_PANEL: [career/tournament/head-to-head text]
SPEED: [number] (bowling speed in kph)
EXTRA: wide/no_ball/leg_bye/bye
THIS OVER: [ball-by-ball results]
FULL SCORECARD: [every batter/bowler row]

STEP 5 — ACTION (1 sentence):
What is happening? (delivery bowled, shot played, celebration, etc.)

RULES:
- JSON tag line MUST be first. Then VISIBLE_TEXT line. Then STRIP. \
Then overlays. Then action.
- Every field in STRIP must come from your own VISIBLE_TEXT \
transcription. If it's not in VISIBLE_TEXT, it MUST be null.
- * or > prefix on batter name = striker.
- If this is a pure ADVERTISEMENT with no strip: output the JSON with \
all false, then VISIBLE_TEXT: (none), then "ADVERTISEMENT" and stop.

HINT FROM SCORER (TIE-BREAKING ONLY — VISIBLE_TEXT always wins; if \
the hint contradicts what you read in pixels, IGNORE the hint and \
output what you actually see):
{vision_hint}\
"""


# 2026-05-12: Short prompt — targets ~1.5K input tokens (vs ~3.5K
# for SCOUT_PROMPT_VERBOSE) so the 60 fpm Vision loop stays under
# Groq's 300K TPM cap on scout-17b.  Drops STEP 4 overlays + STEP 5
# action narrative (neither is consumed by the regex Extractor or
# the Scorer's first-200-char tie-break context).  Keeps STEP 1 JSON
# tag, STEP 2 VISIBLE_TEXT grounding (load-bearing for hallucination
# defense), STEP 3 STRIP, plus an optional CHASE line for innings-2.
# Anti-priming rules preserved verbatim — they were the post-mortem
# fix for the 2026-05-11/12 hallucination regression.
SCOUT_PROMPT_SHORT = """\
You are reading a live IPL cricket broadcast frame.

Output exactly the following lines, in this order. Do not output \
anything else.

LINE 1 — JSON classification tag (must be the very first line).
{{"has_strip": <bool>, "has_overlay_stats": <bool>, "drs_review": \
<bool>, "camera_view": "<enum>", "frame_phase": "<enum>", \
"ball_position": null}}

camera_view enum (pick one):
  bowlers_end  — wide shot from behind bowler, pitch extends away
  side_on      — square camera (third-man / fine-leg), pitch off-axis
  closeup      — face/body fills frame
  replay       — slow-motion / replay badge / spider-cam / hawkeye
  graphic      — full-screen scorecard / partnership / sponsor card
  ad           — commercial break
  other        — presenter, drinks, anything else

frame_phase enum (pick one): \
runup | release | flight | shot | post_shot | fielder_reaction | \
replay | between_play | graphic | advertisement | other

LINE 2 — VISIBLE_TEXT. Transcribe ONLY the bottom-strip scoreboard \
text, character-by-character, exactly as the pixels render. Use ? \
for individual chars/words you cannot resolve. Do NOT paraphrase, \
expand abbreviations, or fill from memory.
VISIBLE_TEXT: <verbatim text, or (none) if no strip is rendered>

LINE 3 — STRIP. Parse VISIBLE_TEXT into the structured format below. \
Every value MUST appear verbatim in your own VISIBLE_TEXT for this \
frame. If a field is not in VISIBLE_TEXT, emit the literal word null.
STRIP: <team_or_null> <runs>-<wkts> (<overs>) | extras=<n_or_null> | \
this_over=<symbols_or_null> | <striker> <r>(<b>) | <nonstriker> \
<r>(<b>) | <bowler> <w>-<r> (<o>)

If VISIBLE_TEXT was (none), emit exactly:
STRIP: null null-null (null) | extras=null | this_over=null | null \
null(null) | null null(null) | null null-null (null)

LINE 4 (optional) — CHASE info, only if the frame literally shows a \
target / required-rate / runs-needed phrase. Otherwise omit entirely. \
Use these exact tokens so the downstream parser matches them:
CHASE: TARGET <n> | REQUIRED RUN-RATE <f> | NEED <n> FROM <n> BALLS

Omit any sub-token whose value isn't in pixels — e.g. if only target \
is visible: "CHASE: TARGET 177".

ANTI-PRIMING RULES (these closed the 2026-05-11/12 hallucination \
regression — read carefully):
- Output ONLY names you literally transcribed in VISIBLE_TEXT this \
frame. NEVER from training data, NEVER from the hint, NEVER from a \
previous frame.
- Forbidden defaults (unless literally in VISIBLE_TEXT this frame): \
Rohit Sharma, Suryakumar Yadav, Harshal Patel, Ishan Kishan, \
Yashasvi Jaiswal, Jasprit Bumrah, Jadeja, and every other player \
name from training data.
- Score, wickets, overs MUST match digits actually rendered in \
VISIBLE_TEXT. Do not echo the hint or the previous frame's score. \
If unreadable, emit null.
- Team token: emit null when only a flag/logo is shown — do NOT \
infer MI, RCB, KKR, LSG, CSK, DC, PBKS, GT, RR, SRH from logo \
geometry. Only emit a team abbreviation that is written in pixels.
- Overs token: emit null if no X.Y over counter is visible — do NOT \
steal a digit from score, run-rate, partnership, or speed.
- * or > prefix on a batter name marks the striker.

HINT FROM SCORER (TIE-BREAK ONLY — VISIBLE_TEXT always wins; if the \
hint contradicts what you read in pixels, IGNORE the hint):
{vision_hint}\
"""


# Module-level selector — defaults to short.  Set SCOUT_PROMPT_MODE=
# verbose to revert to the pre-2026-05-12 prompt (slower, higher TPM,
# carries STEP 4 overlays + STEP 5 action narrative).
SCOUT_PROMPT = (
    SCOUT_PROMPT_VERBOSE
    if os.environ.get("SCOUT_PROMPT_MODE", "short").lower() == "verbose"
    else SCOUT_PROMPT_SHORT
)


class Vision:
    """Scout does everything: tag + read in one call."""

    # Allowed camera_view values — Scout occasionally returns close
    # variants ("bowler_end", "wide_shot"); we normalise.
    _CAMERA_VIEW_ALLOWED = {
        "bowlers_end", "side_on", "closeup", "replay",
        "graphic", "ad", "other",
    }
    # 2026-04-24 (Part B, V1): re-point wide_shot / wide to side_on.
    # An elevated square/side shot with the pitch visible off-axis is
    # a side_on frame in the consumer-aligned rubric (see rubric EC-6
    # in docs/scout_labeling_rubric_v1.md) — DWR opening a delivery
    # window on such a frame would expect pitch-receding geometry in
    # subsequent frames and would cut a broken clip.  A3 audit of 5
    # production sessions found zero emissions of "wide_shot" or
    # "wide" from Scout, so this change is defensive hygiene with no
    # observable traffic impact; it fires only if a future prompt
    # revision or model upgrade causes Scout to emit these aliases.
    _CAMERA_VIEW_ALIASES = {
        "bowler_end": "bowlers_end", "bowlers": "bowlers_end",
        "wide_shot": "side_on", "wide": "side_on",
        "side": "side_on", "sideon": "side_on",
        "close_up": "closeup", "close-up": "closeup",
        "replay_slow_mo": "replay", "slow_mo": "replay",
        "advertisement": "ad", "commercial": "ad",
        "fullscreen_graphic": "graphic", "scorecard_graphic": "graphic",
    }

    # 2026-04-19: phase tag describes the MOMENT of the delivery.
    # Used by BallAnalyzer to sample release / flight / shot frames
    # for VLM classification — solves the post-action-dwell bias of
    # the prior "last N bowlers_end frames" selection.
    _FRAME_PHASE_ALLOWED = {
        "runup", "release", "flight", "shot", "post_shot",
        "fielder_reaction", "replay", "between_play", "graphic",
        "advertisement", "other",
    }
    _FRAME_PHASE_ALIASES = {
        "delivery_release": "release", "ball_release": "release",
        "delivery_flight": "flight", "ball_flight": "flight",
        "shot_played": "shot", "batting_shot": "shot",
        "after_shot": "post_shot", "post-shot": "post_shot",
        "fielding": "fielder_reaction", "fielder": "fielder_reaction",
        "celebration": "fielder_reaction",
        "ad": "advertisement", "commercial": "advertisement",
        "between": "between_play", "no_play": "between_play",
    }

    def __init__(self):
        self._groq = AsyncGroq(
            api_key=GROQ_API_KEY, timeout=_SCOUT_TIMEOUT + 2)
        # Raw-Scout dump (opt-in via SCOUT_RAW_DUMP=1). Each call's
        # full multi-line response is appended to
        # files/logs/deliveries/<SESSION_ID>/scout_raw.jsonl so future
        # runs can replay the match deterministically with $0 Groq cost.
        self._raw_dump_fp = None
        if os.environ.get("SCOUT_RAW_DUMP") == "1":
            sid = os.environ.get("BMF_SESSION_ID", "no_session")
            ddir = os.path.join("files", "logs", "deliveries", sid)
            os.makedirs(ddir, exist_ok=True)
            self._raw_dump_fp = open(
                os.path.join(ddir, "scout_raw.jsonl"),
                "a", buffering=1, encoding="utf-8")
        # Replay cache (opt-in via SCOUT_REPLAY_LOG=<path>). When a
        # frame_id is present in the cache, _scout_call returns the
        # cached raw_response instead of calling Groq. Takes precedence
        # over real API calls; misses fall through to Groq (so partial
        # caches still work — paired with SCOUT_RAW_DUMP=1 they'll be
        # filled on the fly).
        self._replay_cache: dict[int, str] = {}
        replay_path = os.environ.get("SCOUT_REPLAY_LOG")
        if replay_path and os.path.exists(replay_path):
            with open(replay_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        fid = rec.get("frame_id")
                        raw = rec.get("raw_response")
                        if isinstance(fid, int) and isinstance(raw, str):
                            self._replay_cache[fid] = raw
                    except json.JSONDecodeError:
                        continue
            log.info(f"[SCOUT-REPLAY] loaded {len(self._replay_cache)} "
                     f"cached responses from {replay_path}")
        self.last_drs_flag: bool = False
        # Fix #4: cumulative count of frames where Scout returned a
        # prompt-template placeholder response.  Surfaced for monitoring;
        # rare (1-5/match) means the guard is doing its job silently,
        # frequent (10+/match) signals a Scout reliability issue.
        self.scout_template_rejection_count: int = 0
        # Last camera_view tag (set after every describe() call).  Read
        # by the main loop so the tag can be pushed into BallAnalyzer's
        # tagged-frame buffer for delivery analysis.
        self.last_camera_view: str | None = None
        # Last frame_phase tag — drives `analyze_last_delivery`'s
        # frame-selection so VLM classification sees release/flight/
        # shot frames instead of post-action dwell.
        self.last_frame_phase: str | None = None
        # Last ball_position {"x": float, "y": float} or None.  Not
        # used by capture pipeline yet; stored for future trajectory
        # inference.
        self.last_ball_position: dict | None = None
        # Scout strip / overlay classifier outputs — surfaced for Thread 7
        # Fix 2 (`cam=graphic` fast-path in test_pipeline). Reset defensively
        # alongside ``last_camera_view`` when Scout fails or is rejected.
        self.last_strip_flag: bool = False
        self.last_overlay_flag: bool = False

    async def describe(self, frame: np.ndarray,
                       vision_hint: str | None = None,
                       frame_id: int | None = None,
                       ) -> tuple[str, str, str | None]:
        """Returns (frame_type, description, action_description).

        Side-effect: sets ``self.last_camera_view`` to one of the
        allowed camera_view tags (bowlers_end / side_on / closeup /
        replay / graphic / ad / other) so the caller can stash the
        frame in BallAnalyzer's tagged buffer for delivery analysis.

        Stage 2d: if frame_id is provided, records dispatch +
        response/timeout/error into the Frame Fate Ledger.
        """
        if frame_id is not None:
            try:
                from eyes.frame_ledger import get_ledger
                get_ledger().record_dispatch(int(frame_id))
            except Exception:
                pass
        image_b64 = self._encode(frame)
        hint = vision_hint or "None — first frame or no issues."
        prompt = SCOUT_PROMPT.format(vision_hint=hint)

        # Shadow-mode dedup precomputation (env-gated, log-only).
        _dedup_shadow_ctx = None
        if os.environ.get("SCOUT_DEDUP_SHADOW") == "1":
            try:
                _now = time.time()
                _live_phash = _scout_dedup_score_block_phash(frame)
                _scout_dedup_cache[:] = [
                    e for e in _scout_dedup_cache
                    if _now - e[2] <= _SCOUT_DEDUP_TTL_SECONDS
                ]
                _best_dist = None
                _best_entry = None
                for _entry in _scout_dedup_cache:
                    _d = _live_phash - _entry[0]
                    if _best_dist is None or _d < _best_dist:
                        _best_dist = _d
                        _best_entry = _entry
                _dedup_shadow_ctx = (_live_phash, _best_dist, _best_entry, _now)
            except Exception as _exc:
                log.warn(f"[SCOUT-DEDUP-SHADOW] precompute failed: {_exc!r}")
                _dedup_shadow_ctx = None

        t0 = time.time()
        raw = await self._scout_call(image_b64, prompt)
        ms = (time.time() - t0) * 1000

        if _dedup_shadow_ctx is not None:
            try:
                _live_phash, _best_dist, _best_entry, _now = _dedup_shadow_ctx
                _would_skip = (
                    _best_dist is not None
                    and _best_dist <= _SCOUT_DEDUP_THRESHOLD
                )

                def _extract_fields(text):
                    if not text:
                        return (None, None, None)
                    _score = _wkts = _overs = None
                    _m = re.search(r"(\d{1,3})[/-](\d{1,2})", text)
                    if _m:
                        _score = int(_m.group(1))
                        _wkts = int(_m.group(2))
                    _m2 = re.search(r"\(?(\d{1,2}\.\d)\)?", text)
                    if _m2:
                        try:
                            _overs = float(_m2.group(1))
                        except ValueError:
                            _overs = None
                    return (_score, _wkts, _overs)

                _live_s, _live_w, _live_o = _extract_fields(raw)
                if _would_skip and _best_entry is not None:
                    _cached_s, _cached_w, _cached_o = _extract_fields(
                        _best_entry[1])
                else:
                    _cached_s = _cached_w = _cached_o = None

                try:
                    from trace_emitter import get_recorder as _get_rec
                    _get_rec().record(
                        tag="SCOUT-DEDUP-SHADOW",
                        would_skip=_would_skip,
                        best_dist=(int(_best_dist)
                                   if _best_dist is not None else None),
                        cached_score=_cached_s,
                        live_score=_live_s,
                        cached_wkts=_cached_w,
                        live_wkts=_live_w,
                        cached_overs=_cached_o,
                        live_overs=_live_o,
                        score_match=((_cached_s == _live_s)
                                     if _would_skip else None),
                    )
                except Exception as _exc:
                    log.warn(
                        f"[SCOUT-DEDUP-SHADOW] trace emit failed: {_exc!r}")

                _scout_dedup_cache.append((_live_phash, raw or "", _now))
                while len(_scout_dedup_cache) > _SCOUT_DEDUP_CACHE_MAX_SIZE:
                    _scout_dedup_cache.pop(0)
            except Exception as _exc:
                log.warn(f"[SCOUT-DEDUP-SHADOW] postprocess failed: {_exc!r}")

        if not raw:
            log.info(f"[SCOUT] Empty response {ms:.0f}ms")
            self.last_camera_view = None
            self.last_strip_flag = False
            self.last_overlay_flag = False
            if frame_id is not None:
                try:
                    from eyes.frame_ledger import (
                        get_ledger, ScoutStatus, ScoutResponseClass)
                    get_ledger().record_scout_response(
                        int(frame_id),
                        ScoutResponseClass.OTHER,
                        status=ScoutStatus.ERROR)
                except Exception:
                    pass
            return ("UNKNOWN", "", None)

        tag, frame_type = self._parse_tag(raw)
        description, action_desc = self._split_output(raw, frame_type)

        # Fix #4 (2026-04-23): template-placeholder guard.  If Scout
        # echoed the prompt template instead of parsing the broadcast,
        # reject the whole read — downstream parsers can't recover
        # from literal "[RUNS]" / "[BATTER1]" tokens and would write
        # corrupted state.  Check both description and action payload.
        _tmpl_hit = (
            (description and _TEMPLATE_MARKERS.search(description))
            or (action_desc and _TEMPLATE_MARKERS.search(action_desc))
        )
        if _tmpl_hit:
            self.scout_template_rejection_count += 1
            preview = (description or action_desc or "")[:200]
            log.warn(
                f"[SCOUT-REJECT] Template placeholder detected "
                f"(#{self.scout_template_rejection_count}): "
                f"{preview!r}"
            )
            self.last_camera_view = None
            self.last_frame_phase = None
            self.last_ball_position = None
            self.last_strip_flag = False
            self.last_overlay_flag = False
            self.last_drs_flag = False
            return ("UNKNOWN", "", None)

        has_digits = bool(re.search(r"\d{2,3}", raw))
        strip_flag = tag.get("has_strip", False) if tag else False
        overlay_flag = tag.get("has_overlay_stats", False) if tag else False
        drs_flag = tag.get("drs_review", False) if tag else False

        self.last_strip_flag = strip_flag
        self.last_overlay_flag = overlay_flag
        self.last_drs_flag = drs_flag
        self.last_camera_view = self._normalise_camera_view(
            tag.get("camera_view") if tag else None,
            frame_type=frame_type,
            has_strip=strip_flag,
            has_overlay=overlay_flag,
        )
        self.last_frame_phase = self._normalise_frame_phase(
            tag.get("frame_phase") if tag else None,
            camera_view=self.last_camera_view,
            frame_type=frame_type,
        )
        self.last_ball_position = self._normalise_ball_position(
            tag.get("ball_position") if tag else None,
            frame_phase=self.last_frame_phase,
        )

        log.info(f"[SCOUT] {frame_type} {ms:.0f}ms "
                 f"strip={strip_flag} overlay={overlay_flag} "
                 f"drs={drs_flag} cam={self.last_camera_view} "
                 f"phase={self.last_frame_phase} "
                 f"digits={has_digits} "
                 f"{len(raw)} chars")
        if not has_digits and frame_type != "ADVERTISEMENT":
            log.info(f"[SCOUT] Preview: {raw[:200]}")

        if frame_id is not None:
            try:
                from eyes.frame_ledger import (
                    get_ledger, ScoutResponseClass, ScoutStatus)
                rc = {
                    "SCOREBOARD": ScoutResponseClass.SCOREBOARD,
                    "GRAPHIC":    ScoutResponseClass.GRAPHIC,
                    "CLOSEUP":    ScoutResponseClass.OTHER,
                    "ADVERTISEMENT": ScoutResponseClass.OTHER,
                    "PREMATCH":   ScoutResponseClass.OTHER,
                }.get(frame_type, ScoutResponseClass.OTHER)
                get_ledger().record_scout_response(
                    int(frame_id), rc, status=ScoutStatus.RESPONDED)
            except Exception:
                pass

        return (frame_type, description, action_desc)

    @classmethod
    def _normalise_camera_view(cls, raw: str | None, *,
                                frame_type: str,
                                has_strip: bool,
                                has_overlay: bool) -> str | None:
        """Map Scout's camera_view to one of the allowed tags.

        IMPORTANT: frame_type overrides Scout's `camera_view` when the
        two conflict.  Empirical bug (2026-04-18): Scout sometimes
        returns ``camera_view="bowlers_end"`` on AD frames where the
        scoreboard strip is absent — without this guard we'd record
        an ad frame into BallAnalyzer's bowlers_end tagged buffer
        and poison delivery analysis.  Rule:

          - frame_type == ADVERTISEMENT  →  always "ad"
          - has_overlay and not has_strip →  always "graphic"
          - otherwise trust Scout's tag if it's in the allowed set
          - fall back to None
        """
        if frame_type == "ADVERTISEMENT":
            return "ad"
        if has_overlay and not has_strip:
            return "graphic"
        if isinstance(raw, str):
            v = raw.strip().lower().replace(" ", "_")
            v = cls._CAMERA_VIEW_ALIASES.get(v, v)
            if v in cls._CAMERA_VIEW_ALLOWED:
                # When the strip ISN'T visible at all, an active-play
                # tag (bowlers_end / side_on) doesn't make sense —
                # Scout is hallucinating from the visual content
                # only.  Demote to "other" so the tagged buffer
                # doesn't pick it up as a delivery candidate.
                if (not has_strip
                        and v in ("bowlers_end", "side_on")):
                    return "other"
                return v
        return None

    @classmethod
    def _normalise_frame_phase(cls, raw: str | None, *,
                                camera_view: str | None,
                                frame_type: str) -> str | None:
        """Map Scout's frame_phase to one of the allowed tags.

        Cross-checks against camera_view: if Scout claims `release`
        on an `ad`-tagged frame, the phase tag is hallucinated —
        force it to `advertisement`.  Same for graphic / replay.
        """
        if frame_type == "ADVERTISEMENT" or camera_view == "ad":
            return "advertisement"
        if camera_view == "graphic":
            return "graphic"
        if camera_view == "replay":
            return "replay"
        if isinstance(raw, str):
            v = raw.strip().lower().replace(" ", "_")
            v = cls._FRAME_PHASE_ALIASES.get(v, v)
            if v in cls._FRAME_PHASE_ALLOWED:
                return v
        return None

    @staticmethod
    def _normalise_ball_position(raw, *,
                                  frame_phase: str | None) -> dict | None:
        """Validate and clip ball_position to [0,1]x[0,1].

        Only meaningful for `release`, `flight`, `shot` phases.  Drop
        otherwise — Scout was instructed to return null but may still
        echo a stale value.
        """
        if frame_phase not in ("release", "flight", "shot"):
            return None
        if not isinstance(raw, dict):
            return None
        try:
            x = float(raw.get("x"))
            y = float(raw.get("y"))
        except (TypeError, ValueError):
            return None
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            return None
        return {"x": x, "y": y}

    # ------------------------------------------------------------------
    # Scout call — single Groq call, tag + read, 600 tokens
    # ------------------------------------------------------------------
    async def _scout_call(self, image_b64: str,
                          prompt: str) -> str | None:
        fid = get_global_frame()
        if self._replay_cache:
            cached = self._replay_cache.get(fid)
            if cached is not None:
                return cached
        # F130-class fix: 429 retry once with parsed backoff. Without
        # this, a single 429 returns None → ("UNKNOWN","",None) at the
        # describe() boundary → frame discarded by test_pipeline.py with
        # no replay path on the producer side.
        from eyes.openscout_loop import (
            _DEFAULT_429_BACKOFF_S, _is_rate_limit, _parse_reset_seconds,
        )
        retry_t0: float | None = None
        for attempt in range(2):
            try:
                resp = await self._groq.chat.completions.create(
                    model=GROQ_PRIMARY_MODEL,
                    temperature=0,
                    max_tokens=600,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image_url",
                             "image_url": {
                                 "url": f"data:image/jpeg;base64,{image_b64}"}},
                            {"type": "text", "text": prompt},
                        ],
                    }],
                )
                content = resp.choices[0].message.content.strip()
                finish = resp.choices[0].finish_reason
                usage = resp.usage
                tokens = usage.completion_tokens if usage else "?"
                if finish != "stop":
                    log.info(f"[SCOUT] finish={finish} tokens={tokens}")
                if self._raw_dump_fp is not None:
                    try:
                        self._raw_dump_fp.write(json.dumps({
                            "ts": time.time(),
                            "frame_id": fid,
                            "raw_response": content,
                            "finish_reason": finish,
                            "tokens": tokens if isinstance(tokens, int) else None,
                        }) + "\n")
                    except Exception:
                        pass
                # Optional: save the jpeg sent to Groq (exact bytes
                # the model received) so input/output pairs can be
                # audited together.  Two env gates:
                #   SCOUT_FRAME_DUMP_IDS=17,42  → dump only those IDs
                #   SCOUT_FRAME_DUMP=1          → dump every frame
                # (SCOUT_FRAME_DUMP_IDS takes precedence when set.)
                _dump_ids = os.environ.get("SCOUT_FRAME_DUMP_IDS", "")
                _dump_all = os.environ.get("SCOUT_FRAME_DUMP") == "1"
                _do_dump = False
                if _dump_ids:
                    try:
                        _wanted = {int(x) for x in _dump_ids.split(",")
                                   if x.strip()}
                        _do_dump = fid in _wanted
                    except ValueError:
                        _do_dump = False
                elif _dump_all:
                    _do_dump = True
                if _do_dump:
                    try:
                        sid = os.environ.get(
                            "BMF_SESSION_ID", "no_session")
                        ddir = os.path.join(
                            "files", "logs", "deliveries", sid,
                            "scout_frames")
                        os.makedirs(ddir, exist_ok=True)
                        fpath = os.path.join(
                            ddir, f"f{fid:06d}.jpg")
                        with open(fpath, "wb") as _fp:
                            _fp.write(base64.b64decode(image_b64))
                    except Exception:
                        pass
                if attempt > 0 and retry_t0 is not None:
                    try:
                        from trace_emitter import get_recorder as _get_rec
                        _get_rec().record(
                            tag="SCOUT-RETRY-IN-CALL-SUCCESS",
                            frame_id=fid,
                            retry_latency_ms=int(
                                (time.time() - retry_t0) * 1000))
                    except Exception:
                        pass
                return content
            except Exception as e:
                if attempt == 0 and _is_rate_limit(e):
                    sleep_for = (_parse_reset_seconds(str(e))
                                 or _DEFAULT_429_BACKOFF_S)
                    try:
                        from trace_emitter import get_recorder as _get_rec
                        _get_rec().record(
                            tag="SCOUT-RETRY-IN-CALL-QUEUED",
                            frame_id=fid,
                            error=str(e)[:200])
                    except Exception:
                        pass
                    log.warn(
                        f"[SCOUT] 429 rate-limit, retrying after "
                        f"{sleep_for:.2f}s ({e!r})")
                    retry_t0 = time.time()
                    await asyncio.sleep(sleep_for)
                    continue
                if attempt > 0:
                    try:
                        from trace_emitter import get_recorder as _get_rec
                        _get_rec().record(
                            tag="SCOUT-RETRY-IN-CALL-EXHAUSTED",
                            frame_id=fid,
                            retries=1,
                            error=str(e)[:200])
                    except Exception:
                        pass
                log.error(f"[SCOUT] Error: {e}")
                return None
        return None

    # ------------------------------------------------------------------
    # Parse the JSON tag line from Scout output
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_tag(raw: str) -> tuple[dict | None, str]:
        """Extract the classification JSON and derive frame_type."""
        tag = None
        for line in raw.split("\n")[:5]:
            line = line.strip()
            if line.startswith("{") and "has_strip" in line:
                try:
                    tag = json.loads(line)
                    break
                except json.JSONDecodeError:
                    brace_end = line.rfind("}") + 1
                    if brace_end > 0:
                        try:
                            tag = json.loads(line[:brace_end])
                            break
                        except json.JSONDecodeError:
                            pass

        if not tag:
            upper = raw.upper()[:100]
            if "ADVERTISEMENT" in upper and "STRIP" not in upper:
                return ({"has_strip": False, "has_overlay_stats": False,
                         "drs_review": False}, "ADVERTISEMENT")
            has_strip = bool(re.search(
                r"STRIP:\s*(?:[A-Z]{2,}|null)\s+\d+", raw, re.IGNORECASE))
            return ({"has_strip": has_strip, "has_overlay_stats": False,
                     "drs_review": False},
                    "SCOREBOARD" if has_strip else "UNKNOWN")

        has_strip = tag.get("has_strip", False)
        has_overlay = tag.get("has_overlay_stats", False)
        drs = tag.get("drs_review", False)

        if drs:
            return (tag, "SCOREBOARD")
        if has_strip and has_overlay:
            return (tag, "GRAPHIC")
        if has_strip:
            return (tag, "SCOREBOARD")
        if has_overlay:
            return (tag, "GRAPHIC")
        return (tag, "ADVERTISEMENT")

    # ------------------------------------------------------------------
    # Split scout output into description + action
    # ------------------------------------------------------------------
    @staticmethod
    def _split_output(raw: str, frame_type: str,
                      ) -> tuple[str, str | None]:
        if frame_type == "ADVERTISEMENT":
            return ("", None)

        lines = raw.split("\n")
        text_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("{") and "has_strip" in stripped:
                continue
            text_lines.append(line)
        text = "\n".join(text_lines).strip()

        action = None
        for marker in ("ACTION:", "CRICKET ACTION:", "STEP 4"):
            idx = text.upper().find(marker)
            if idx != -1:
                after = text[idx:]
                colon = after.find(":")
                if colon != -1:
                    action_part = after[colon + 1:].strip()
                    nl = action_part.find("\n")
                    if nl != -1:
                        action_part = action_part[:nl].strip()
                    text = text[:idx].strip()
                    if len(action_part) > 10:
                        action = action_part
                break

        return (text, action)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _encode(frame: np.ndarray) -> str:
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return base64.b64encode(buf).decode()

    async def close(self):
        await self._groq.close()
