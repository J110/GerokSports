"""VLM-based delivery classifier (Groq Scout 17B).

Replaces the broken classical CV trajectory pipeline (detect_white_ball +
phase_separator + ball_classifier).  Sends 3 saved delivery frames
(release / pitch / shot) to Scout with a structured JSON prompt.  Scout
returns a semantic classification — length, line, shot type, direction —
in ~700-1000ms.  No coordinate math, no broadcaster calibration.

Design contract: returned dict matches the schema downstream consumers in
`test_pipeline.py` expect (length, line, bowling_angle, shot_type,
shot_elevation, shot_direction{side,zone,confidence}, bounce, runs,
detections, detection_rate, commentary_line, _method).

Sync API on purpose — `BallAnalyzer.analyze_last_delivery` is sync.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import time

import cv2
import numpy as np
from groq import Groq

from eyes.config import GROQ_API_KEY, GROQ_PRIMARY_MODEL

log = logging.getLogger("vlm_delivery_classifier")

_TIMEOUT_S = 8.0
_JPEG_QUALITY = 78  # 78 keeps Scout-readable detail at ~80KB / 960×618 frame


def _select_action_frames(
    frames: list[np.ndarray],
    n: int,
) -> tuple[list[np.ndarray], list[int], str]:
    """Pick frames biased toward the action (delivery + contact).

    Strategy: compute frame-difference energy across all frames. Bowler's
    runup, ball release, pitch, and shot contact produce the highest
    motion. Static post-contact frames (batsman standing) rank low and
    get filtered out. We always keep one frame from the result phase
    (last 30%) so Scout sees the ball outcome.

    Returns: (picks, picked_indices, mode_tag).
    """
    if not frames:
        return [], [], "empty"
    if len(frames) <= n:
        return list(frames), list(range(len(frames))), "all"

    diffs = [0.0]
    h, w = frames[0].shape[:2]
    sample_w = min(w, 320)
    sample_h = max(1, int(h * sample_w / max(w, 1)))
    prev_small = cv2.resize(frames[0], (sample_w, sample_h))
    prev_gray = cv2.cvtColor(prev_small, cv2.COLOR_BGR2GRAY)
    for i in range(1, len(frames)):
        small = cv2.resize(frames[i], (sample_w, sample_h))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        d = float(cv2.absdiff(gray, prev_gray).mean())
        diffs.append(d)
        prev_gray = gray

    total = len(frames)
    result_start = int(total * 0.7)
    result_pick: int | None = None
    if result_start < total:
        rs_diffs = [(diffs[i], i) for i in range(result_start, total)]
        if rs_diffs:
            result_pick = max(rs_diffs, key=lambda x: x[0])[1]

    n_action = n - (1 if result_pick is not None else 0)
    action_pool = [(diffs[i], i) for i in range(total)
                   if i != result_pick]
    action_pool.sort(reverse=True)
    chosen_action = sorted(idx for _, idx in action_pool[:n_action])

    if result_pick is not None:
        chosen = sorted(chosen_action + [result_pick])
    else:
        chosen = chosen_action

    seen: set[int] = set()
    chosen = [i for i in chosen if not (i in seen or seen.add(i))]
    picks = [frames[i] for i in chosen]
    return picks, chosen, "motion"


VLM_PROMPT = """\
You are watching a live IPL cricket broadcast.  The {n_frames} images \
below were captured around the moment a ball event was detected on the \
scoreboard.  A delivery DEFINITELY happened — the score advanced.  \
Your job is to classify it.

The frames are in temporal order across roughly 3-5 seconds of the \
broadcast feed.  A typical delivery sequence on TV is a MIX of camera \
angles: bowler's-end wide shot → release → ball in flight → \
pitch/bounce → contact → close-up of the batter → fielder reaction → \
sometimes a slow-mo replay or boundary chase.  ALL of these belong to \
the same delivery and carry useful information.  Some frames may be \
graphics, replays, or cuts the broadcast interleaved — work around \
them.  Use whatever frame(s) carry play to extract the classification.

CONTEXT (from scoreboard — TRUST this):
  runs scored on this ball: {runs}
  speed (kph, if known): {speed}

Return ONLY valid JSON on a single line, no prose, no markdown fences.
Always set is_delivery=true.  If a particular field cannot be read \
from any frame, set it to "unknown" — never refuse the whole call.

Schema:

{{"is_delivery":true,\
"bowling_angle":"over"|"round"|"unknown",\
"length":"yorker"|"full"|"good_length"|"short"|"bouncer"|"full_toss",\
"line":"wide_outside_off"|"outside_off"|"off_stump"|"middle"|\
"leg_stump"|"down_leg"|"wide_down_leg",\
"shot_intent":"defended"|"attacked"|"left"|"edged"|"missed"|"unknown",\
"shot_action":"drive"|"cut"|"pull"|"hook"|"sweep"|"reverse_sweep"|\
"flick"|"glance"|"dab"|"late_cut"|"slog"|"slash"|"none"|"unknown",\
"shot_side":"off"|"leg"|"straight"|"behind"|"unknown",\
"shot_zone":"behind"|"square"|"mid"|"down_the_ground"|"unknown",\
"elevation":"along_ground"|"in_the_air"|"top_edge"|"unknown",\
"swing_or_seam":"inswing"|"outswing"|"seam_away"|"seam_in"|\
"straight"|"not_visible",\
"ball_speed_visible":true|false,\
"ball_speed_kph":<number or null>,\
"confidence":"high"|"medium"|"low"}}

GUIDANCE:
- The frames may include a closeup of the batter's shot, a fielder \
  diving, a replay of the SAME delivery, or a celebration after a \
  boundary/wicket.  Use these to read shot type and direction.  They \
  are part of the delivery sequence, NOT reasons to reject.
- LENGTH: where the ball pitches RELATIVE TO THE BATTER.  yorker = at \
  the toes; full = drivable on the half-volley; good_length = forces \
  uncertainty; short = chest-high; bouncer = above shoulder.  Almost \
  every delivery bounces; full_toss is RARE — only use when there is \
  clearly no bounce visible across the sequence.
- LINE: the ball's line at the batter, not at release.
- BOWLING_ANGLE — pick "over" (over-the-wicket: bowler's bowling arm \
  passes the SAME side of the stumps as their landing foot) or \
  "round" (round-the-wicket: bowler delivers from the OPPOSITE side, \
  crossing behind the stumps before release).  Default is "over"; \
  "round" is the exception (~10-15% of T20 deliveries) used mainly by \
  pacers cramping a left-hander and by spinners.  REQUIREMENTS for \
  "round": you must see the bowler's run-up cross to the off side of \
  the stumps from a right-armer (or leg side from a left-armer) AT \
  THE RELEASE STRIDE.  If only post-release frames are available or \
  the runup is partially occluded, prefer "over" or "unknown" — DO \
  NOT default to "round".
- SHOT_INTENT — what the BATTER tried to do with the ball.  Pick \
  exactly one:
    * "defended": soft block, no follow-through, intends 0 runs.
    * "attacked": full swing, intends boundary/run.  Almost every \
      4 / 6 is attacked.  Most singles are attacked.
    * "left": batter let the ball pass without offering a shot \
      (bat raised / pulled away).  Score does not advance unless \
      it's an extra.
    * "edged": bat made unintended contact (ball deflected off \
      the edge — usually backward of square or to slip / keeper).
    * "missed": the batter swung but the ball beat the bat \
      (no contact).  Often a wicket / dot ball.
    * "unknown" only if every frame is wide-angle or replay-blurred.
- SHOT_ACTION — the BAT-STROKE played.  Pick exactly one:
    * "drive": classic full-face stroke, foot to the pitch (off-drive, \
      cover-drive, on-drive — all "drive" for our purposes).
    * "cut": horizontal bat to a short / wide ball, going off side \
      square or backward.
    * "pull": horizontal bat to a short ball, going leg side square.
    * "hook": pull to a bouncer (above shoulder).
    * "sweep": down-on-knee, bat horizontal, swept to leg.
    * "reverse_sweep": sweep with reversed grip / behind point.
    * "flick": wristy on-side stroke off the pads.
    * "glance": light deflection fine on the leg side.
    * "dab": guided / tapped run behind point.
    * "late_cut": cut played LATE, going to third man.
    * "slog": cross-batted heave for a six.
    * "slash": forced upper-cut over slips / point.
    * "none": batter left or missed (no shot).
    * "unknown": shot played but type unclear from frames.
  SHOT_INTENT and SHOT_ACTION are INDEPENDENT axes.  A boundary \
  4 driven through cover = intent "attacked", action "drive".  A \
  defensive prod that dribbled to silly point = intent "defended", \
  action "drive" (the stroke shape was a defensive drive).
- SHOT_SIDE — which SIDE OF THE PITCH the ball went after the shot.
  Pick exactly one of {{"off","leg","straight","behind","unknown"}}.
  Right-handed batter: cover/point/third = OFF, midwicket/square-leg/\
  fine-leg = LEG, mid-off/mid-on = STRAIGHT, slip/keeper/short third \
  = BEHIND.
- SHOT_ZONE — where on the field the ball travelled.  Pick exactly one:
    * "behind": square of the wicket and BACK (third man / fine leg /\
      slip / keeper region)
    * "square": square of the wicket (point / cover-point / square-leg)
    * "mid": between square and the bowler (cover / midwicket region)
    * "down_the_ground": straight (mid-off / straight / mid-on)
    * "unknown" only when no fielder reaction or trajectory cue exists.
  Avoid defaulting to "down_the_ground" or "unknown" — choose based on \
  the fielder reaction in the last 1-2 frames.
- ELEVATION — describes the BALL'S TRAJECTORY off the bat, NOT the \
  outcome.  Pick exactly one:
    * "along_ground": the ball rolled / skidded / stayed below knee \
      height after contact.
    * "in_the_air": ANY aerial contact — the ball lifted above knee \
      height after the bat.  This INCLUDES catches (held or dropped), \
      lofted drives, attempted boundaries cleared/intercepted, edges \
      that carried, and all sixes.  If the score advanced by 6, this \
      is ALWAYS "in_the_air".  If a fielder is shown jumping / \
      diving forward / putting hands up, the ball was in the air.
    * "top_edge": clearly mis-hit / skied off the upper edge — almost \
      always loops vertically.
  Do NOT label "along_ground" just because the score didn't advance \
  — a dropped catch is in_the_air with 0 runs scored.
- SWING_OR_SEAM: visible across the flight frames.  Use \
  "not_visible" if you cannot tell.
- BALL_SPEED: read the broadcast speed overlay if it appears in any \
  frame.  Set ball_speed_visible=false and ball_speed_kph=null if not.
- "confidence":"low" if camera angle, occlusion, or motion blur \
  prevents a clean read.
"""


# ── Mapping VLM vocabulary → existing schema vocabulary ──────────────
# `line` taxonomy from `ball_classifier.py` uses "on_stumps" / "on_pads".
# VLM returns "middle" / "leg_stump" / "down_leg". Translate so the
# existing commentary builders / log fields stay consistent.
_LINE_VLM_TO_SCHEMA = {
    "wide_outside_off": "wide_outside_off",
    "outside_off": "outside_off",
    "off_stump": "off_stump",
    "middle": "on_stumps",
    "leg_stump": "leg_stump",
    "down_leg": "on_pads",
    "wide_down_leg": "down_leg",
}

# `shot_type` field downstream is overloaded: it conflates "what the bat
# did" (drive/cut/pull) with "what happened to the ball" (along_ground/
# in_the_air/defended). Existing `_LENGTH_TEXT`/`_SHOT_TEXT` keys are the
# latter.  We populate BOTH:
#   `shot_type`     = elevation-style label (along_ground|in_the_air|...)
#   `shot_action`   = bat-action label (drive|cut|pull|...) — new field
_ELEVATION_TO_SHOT_TYPE = {
    "along_ground": "along_ground",
    "in_the_air":   "in_the_air",
    "unknown":      "unknown",
}

# Map granular field positions → coarse side for downstream consumers
# that still expect side ∈ {off,leg,straight,behind,unknown}.
# Kept for backward compatibility with old VLM responses (pre-v30).
_DIRECTION_TO_SIDE = {
    "cover":          "off",
    "point":          "off",
    "backward_point": "off",
    "third_man":      "behind",
    "mid_off":        "straight",
    "straight":       "straight",
    "mid_on":         "straight",
    "midwicket":      "leg",
    "square_leg":     "leg",
    "fine_leg":       "behind",
    "unknown":        "unknown",
}

# New (v30+) shot vocabularies.
_SHOT_INTENT_VOCAB = {"defended", "attacked", "left", "edged",
                      "missed", "unknown"}
_SHOT_ACTION_VOCAB = {"drive", "cut", "pull", "hook", "sweep",
                      "reverse_sweep", "flick", "glance", "dab",
                      "late_cut", "slog", "slash", "none", "unknown"}
_SHOT_SIDE_VOCAB = {"off", "leg", "straight", "behind", "unknown"}
_SHOT_ZONE_VOCAB = {"behind", "square", "mid", "down_the_ground",
                    "unknown"}


def _encode_jpeg(frame: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return base64.b64encode(buf).decode()


def _shot_type_from_runs(runs: int) -> str:
    if runs == 0:
        return "defended"
    if runs == 6:
        return "in_the_air"
    if runs == 4:
        return "unknown"
    return "along_ground"


_LENGTH_TEXT = {
    "yorker": "yorker",
    "full": "full",
    "good_length": "good length",
    "short": "short",
    "bouncer": "bouncer",
    "full_toss": "full toss",
}

_LINE_TEXT = {
    "wide_outside_off": "wide outside off",
    "outside_off": "outside off",
    "off_stump": "on off stump",
    "on_stumps": "on the stumps",
    "leg_stump": "on leg stump",
    "on_pads": "down the leg side",
    "down_leg": "wide down leg",
}

_DIRECTION_PHRASE = {
    "cover":          "through cover",
    "point":          "through point",
    "backward_point": "through backward point",
    "third_man":      "down to third man",
    "mid_off":        "back past mid-off",
    "straight":       "straight down the ground",
    "mid_on":         "back past mid-on",
    "midwicket":      "through midwicket",
    "square_leg":     "through square leg",
    "fine_leg":       "down to fine leg",
}

_SHOT_VERB = {
    "drive":         "driven",
    "cut":           "cut",
    "pull":          "pulled",
    "sweep":         "swept",
    "reverse_sweep": "reverse-swept",
    "defend":        "defended",
    "leave":         "left alone",
    "flick":         "flicked",
    "hook":          "hooked",
    "slog":          "slogged",
    "glance":        "glanced",
    "dab":           "dabbed",
    "late_cut":      "late-cut",
    "no_shot":       "no shot played",
}


def _build_commentary_line(c: dict) -> str:
    """Mini commentary builder for VLM output.

    Example: "good length, on off stump, driven through cover, in the air"
    """
    parts: list[str] = []

    if c.get("bowling_angle") == "round":
        parts.append("round the wicket")

    length_text = _LENGTH_TEXT.get(c.get("length", ""))
    if length_text:
        parts.append(length_text)

    line_text = _LINE_TEXT.get(c.get("line", ""))
    if line_text:
        parts.append(line_text)

    action = c.get("shot_action", "")
    direction = c.get("shot_direction", {}).get("zone", "")
    elev = c.get("shot_elevation", "unknown")
    verb = _SHOT_VERB.get(action, "")

    if action and action != "no_shot" and verb:
        clause = verb
        dir_phrase = _DIRECTION_PHRASE.get(direction, "")
        if dir_phrase:
            clause = f"{verb} {dir_phrase}"
        parts.append(clause)
    elif action == "no_shot":
        parts.append("no shot played")

    if elev == "in_the_air":
        parts.append("in the air")
    elif elev == "along_ground":
        parts.append("along the ground")
    elif elev == "top_edge":
        parts.append("off the top edge")

    swing = c.get("swing_or_seam", "")
    if swing and swing not in ("not_visible", "straight"):
        parts.append({
            "inswing": "inswing",
            "outswing": "outswing",
            "seam_away": "seamed away",
            "seam_in":   "seamed in",
        }.get(swing, swing))

    return ", ".join(parts) or "no classification available"


class VLMDeliveryClassifier:
    """Classify a delivery from 3 key frames using Groq Scout."""

    def __init__(self, model: str | None = None):
        self._client = Groq(api_key=GROQ_API_KEY, timeout=_TIMEOUT_S + 2)
        self._model = model or GROQ_PRIMARY_MODEL
        self._calls = 0
        self._failures = 0

    def classify(
        self,
        frames: list[np.ndarray],
        runs: int = 0,
        speed_kph: float | None = None,
        n_frames: int = 8,
        save_dir: str | None = None,
    ) -> dict:
        """Classify a delivery.

        Args:
            frames: list of BGR frames in temporal order across the
                full bowler's-end delivery sequence.  We sample
                ``n_frames`` evenly-spaced frames to send to Scout.
            runs: score delta on this delivery (helps Scout disambiguate
                shot_type fallback for fours/sixes/dots).
            speed_kph: optional bowling speed from the broadcast.
            n_frames: how many evenly-spaced frames to send to Scout.
                Capped at 5 (Scout's per-request image limit).  Default
                8 is clamped to 5 — the parameter exists so the caller
                can request fewer (3) for the frame-count sweep test.

        Returns:
            classification dict — see module docstring for schema.
        """
        if not frames:
            return self._unknown(runs, "no_frames")

        # Scout caps requests at 5 images per message
        n_pick = max(1, min(n_frames, 5))
        if len(frames) >= n_pick:
            # Motion-biased selection: prefer high frame-diff energy
            # (bowler's stride, ball pitching, bat contact) over static
            # post-contact frames.  Always keep one result-phase frame.
            picks, idxs, _mode = _select_action_frames(frames, n_pick)
            log.info(
                f"[VLM] frame-pick mode={_mode} "
                f"picked {len(picks)}/{len(frames)} idxs={idxs}")
        else:
            # not enough frames — pad by repeating
            picks = list(frames)
            while len(picks) < n_pick:
                picks.append(frames[-1])

        try:
            encoded = [_encode_jpeg(f) for f in picks]
        except Exception as e:
            log.warning(f"[VLM] encode failed: {e}")
            return self._unknown(runs, "encode_failed")

        speed_str = f"{speed_kph:.0f}" if speed_kph else "unknown"
        prompt = VLM_PROMPT.format(
            n_frames=len(picks), runs=runs, speed=speed_str)

        if save_dir:
            try:
                import os as _os
                _os.makedirs(save_dir, exist_ok=True)
                for _i, _pf in enumerate(picks):
                    cv2.imwrite(_os.path.join(
                        save_dir, f"scout_pick_{_i:02d}.jpg"), _pf)
            except Exception as _se:
                log.warning(f"[VLM] could not save scout picks: {_se}")

        content = [{"type": "text", "text": prompt}]
        for b64 in encoded:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            })

        t0 = time.time()
        try:
            self._calls += 1
            resp = self._client.chat.completions.create(
                model=self._model,
                temperature=0,
                max_tokens=300,
                messages=[{"role": "user", "content": content}],
            )
            raw = resp.choices[0].message.content.strip()
        except Exception as e:
            self._failures += 1
            ms = (time.time() - t0) * 1000
            log.warning(f"[VLM] API error after {ms:.0f}ms: {e}")
            return self._unknown(runs, "vlm_api_error")

        ms = (time.time() - t0) * 1000

        parsed = self._parse_json(raw)
        if not parsed:
            self._failures += 1
            log.warning(f"[VLM] {ms:.0f}ms unparseable: {raw[:200]}")
            return self._unknown(runs, "vlm_unparseable", raw=raw, ms=ms)

        # Architectural rule: ScoreManager already confirmed a delivery
        # happened (the score advanced).  We never reject — at worst we
        # return a result with mostly "unknown" fields.  If Scout still
        # returns is_delivery=false despite the rewritten prompt, we log
        # it as a soft signal but pass the schema through anyway.
        if parsed.get("is_delivery") is False:
            log.info(f"[VLM] {ms:.0f}ms low-info (is_delivery=false from "
                     f"model, but score-confirmed — accepting as unknown)")
            parsed["is_delivery"] = True

        result = self._to_schema(parsed, runs)
        result["_method"] = "vlm"
        result["_vlm_ms"] = round(ms)
        result["_vlm_raw"] = raw
        result["_vlm_confidence"] = parsed.get("confidence", "unknown")
        result["commentary_line"] = _build_commentary_line(result)

        log.info(
            f"[VLM] {ms:.0f}ms "
            f"len={result['length']} line={result['line']} "
            f"angle={result['bowling_angle']} "
            f"shot={result.get('shot_action','?')}/{result['shot_elevation']} "
            f"dir={result['shot_direction'].get('side','?')} "
            f"conf={result['_vlm_confidence']}"
        )

        if save_dir:
            try:
                import os as _os
                _os.makedirs(save_dir, exist_ok=True)
                _req = {
                    "model": self._model,
                    "n_frames_total": len(frames),
                    "n_frames_sent": len(picks),
                    "frames_sent": [f"scout_pick_{i:02d}.jpg"
                                    for i in range(len(picks))],
                    "runs": runs,
                    "speed_kph": speed_kph,
                    "prompt": prompt,
                    "raw_response": raw,
                    "vlm_ms": round(ms),
                }
                with open(_os.path.join(save_dir,
                                        "scout_request.json"), "w") as _f:
                    json.dump(_req, _f, indent=2)
            except Exception as _se:
                log.warning(f"[VLM] could not save scout request: {_se}")

        return result

    # ── Internals ────────────────────────────────────────────────────
    # NOTE: any-frame rescue and reclassify-with-subset removed.  The
    # architectural rule is that ScoreManager confirms delivery; the
    # VLM's only job is classification.  Rescue is no longer needed
    # because we never reject.

    @staticmethod
    def _parse_json(raw: str) -> dict | None:
        """Extract the first JSON object from Scout's response."""
        # Strip markdown fences if Scout added them despite instructions
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        # Find first {...} object
        m = re.search(r"\{.*?\}", cleaned, re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            # Try trimming to last } found
            snippet = m.group(0)
            for i in range(len(snippet), 0, -1):
                if snippet[i - 1] == "}":
                    try:
                        return json.loads(snippet[:i])
                    except json.JSONDecodeError:
                        continue
            return None

    @staticmethod
    def _to_schema(p: dict, runs: int) -> dict:
        bowling_angle = p.get("bowling_angle", "unknown")
        if bowling_angle not in ("over", "round"):
            bowling_angle = "unknown"

        length = p.get("length", "unknown")
        if length not in {"yorker", "full", "good_length", "short",
                          "bouncer", "full_toss"}:
            length = "unknown"

        line_raw = p.get("line", "unknown")
        line = _LINE_VLM_TO_SCHEMA.get(line_raw, "unknown")

        # New (v30+) shot fields. Fall back to legacy "shot_type" /
        # "shot_direction" if the VLM emitted the old schema.
        shot_action = p.get("shot_action") or p.get("shot_type", "unknown")
        if shot_action == "defend":
            shot_action = "drive"  # legacy "defend" is a defensive drive
        if shot_action == "leave" or shot_action == "no_shot":
            shot_action = "none"
        if shot_action not in _SHOT_ACTION_VOCAB:
            shot_action = "unknown"

        shot_intent = p.get("shot_intent", "unknown")
        if shot_intent not in _SHOT_INTENT_VOCAB:
            # Heuristic fallback from runs / shot_action.
            if shot_action == "none":
                shot_intent = "left"
            elif runs >= 4:
                shot_intent = "attacked"
            elif runs == 0:
                shot_intent = "defended"
            else:
                shot_intent = "attacked"

        elevation = p.get("elevation", "unknown")
        if elevation not in {"along_ground", "in_the_air", "top_edge"}:
            elevation = "unknown"

        # Direction: new schema uses shot_side + shot_zone. Fall
        # back to legacy shot_direction → field-position mapping.
        side = p.get("shot_side", "unknown")
        if side not in _SHOT_SIDE_VOCAB:
            _legacy_dir = p.get("shot_direction", "unknown")
            side = _DIRECTION_TO_SIDE.get(_legacy_dir, "unknown")
        zone = p.get("shot_zone", "unknown")
        if zone not in _SHOT_ZONE_VOCAB:
            # Map legacy field positions → coarse zone.
            _legacy_dir = p.get("shot_direction", "unknown")
            _legacy_to_zone = {
                "cover": "mid", "mid_off": "down_the_ground",
                "mid_on": "down_the_ground",
                "straight": "down_the_ground",
                "midwicket": "mid",
                "point": "square", "square_leg": "square",
                "backward_point": "behind", "third_man": "behind",
                "fine_leg": "behind",
            }
            zone = _legacy_to_zone.get(_legacy_dir, "unknown")

        swing = p.get("swing_or_seam", "not_visible")
        if swing not in {"inswing", "outswing", "seam_away", "seam_in",
                         "straight", "not_visible"}:
            swing = "not_visible"

        speed_visible = bool(p.get("ball_speed_visible", False))
        speed_kph_vlm = p.get("ball_speed_kph")
        try:
            speed_kph_vlm = float(speed_kph_vlm) if speed_kph_vlm else None
        except (TypeError, ValueError):
            speed_kph_vlm = None

        # Bounce is no longer in the VLM prompt; derive from length
        if length == "full_toss":
            bounce = "no_bounce"
        else:
            bounce = "normal"

        # Use runs-based shot_type as a sanity floor for elevation.
        if elevation == "unknown":
            shot_type = _shot_type_from_runs(runs)
        else:
            shot_type = elevation

        confidence = p.get("confidence", "medium")
        return {
            "bowling_angle": bowling_angle,
            "length": length,
            "line": line,
            "bounce": bounce,
            "shot_type": shot_type,
            "shot_elevation": elevation,
            "shot_action": shot_action,
            "shot_intent": shot_intent,
            "shot_direction": {
                "side": side,
                "zone": zone,
                "confidence": confidence,
            },
            "swing_or_seam": swing,
            "ball_speed_visible": speed_visible,
            "ball_speed_kph_vlm": speed_kph_vlm,
            "runs": runs,
            "detections": 0,         # N/A for VLM mode
            "detection_rate": 0.0,   # N/A for VLM mode
        }

    @staticmethod
    def _unknown(runs: int, reason: str,
                 raw: str | None = None, ms: float = 0.0) -> dict:
        result = {
            "length": "unknown", "line": "unknown",
            "bowling_angle": "unknown", "bounce": "unknown",
            "shot_type": _shot_type_from_runs(runs),
            "shot_elevation": _shot_type_from_runs(runs),
            "shot_action": "unknown",
            "shot_intent": "unknown",
            "shot_direction": {"side": "unknown", "zone": "unknown",
                               "confidence": "none"},
            "runs": runs, "detections": 0, "detection_rate": 0.0,
            "commentary_line": "",
            "_method": "vlm",
            "_untrackable": True,
            "_skip_reason": reason,
            "_vlm_ms": round(ms),
        }
        if raw:
            result["_vlm_raw"] = raw[:300]
        return result

    @property
    def stats(self) -> dict:
        return {"calls": self._calls, "failures": self._failures}
