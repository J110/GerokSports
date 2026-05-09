"""Gemini 3 Flash Preview delivery-action classifier.

Owns delivery details only (length / line / shot type / bounce / ...).
Scoreboard pipeline (Scout) keeps owning names, scores, overs, current
bowler/batsman, speed, etc.  Player handedness and bowling arm are
resolved pre-match by eyes/player_enrichment.py and rendered on the
batter/bowler rows — NOT per delivery.

Inputs:
    frames: list[(epoch_ts, np.ndarray BGR)] — a contiguous window
            of broadcast frames captured by DeliveryWindowRecorder
            (Scout-triggered camera_view==bowlers_end transition,
            ~8-15 s typical).

Output:
    dict matching the existing `delivery_info` shape consumed by
    test_pipeline.py / wire.py / commentary, EXTENDED additively
    with the new Tier 1+2 fields the user committed to (bounce,
    contact_quality, narrative).

The classifier:
  1. Compiles frames -> mp4 in a tempfile (h264 / mp4v fallback).
  2. Sends mp4 + a non-anchoring schema prompt to gemini-3-flash-preview.
  3. Parses JSON, normalises enums, fills in unknowns honestly,
     maps to the legacy `delivery_info` shape so downstream consumers
     don't have to change.

Sync API (BallAnalyzer.analyze_last_delivery is sync).  Wall time on
a 12-s 720p clip with the v3 paid Gemini key is ~12-16 s.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from eyes.config import GEMINI_API_KEY, GEMINI_DELIVERY_MODEL

log = logging.getLogger("gemini_delivery_classifier")

try:
    from eyes.cricket_logger import _ensure_file_handler
    log.addHandler(_ensure_file_handler())
    log.setLevel(logging.INFO)
except Exception:
    pass


# ── Tier 1 + Tier 2 schema (12 fields + narrative + meta) ───────────
#
# Hand-tuned against gemini-3-flash-preview's actual perceptual
# capability (see results_video_g3flash.json):
#   - length, bounce, line: model can read these
#   - shot_side / shot_angle: coarse only (the model contradicts itself
#     between structured + commentator on the same video, so we keep
#     the enum loose)
#   - contact_quality / shot_intent: kept but flagged as low-trust
#
# 2026-04-21: batsman_handed + bowling_arm REMOVED from the prompt.
# Those are now resolved pre-match once per player in
# eyes/player_enrichment.py (2-pass LLM with Google Search) and
# attached to the batter/bowler rows directly in the UI.  The per-
# delivery camera frame is a poor place to re-guess player identity
# every ball.
#
# NEGATIVE ANCHORS: the prompt MUST forbid filling in a default value
# when the model can't see the cue.  "unknown" is always a valid choice.
# This is the 60% prior-pull problem we saw on 2.5-flash.

GEMINI_PROMPT = """\
You are watching a short video clip (typically 8-15 s) of a single \
cricket delivery captured live from the bowler's-end TV camera.  The \
score advanced after this clip, so a delivery DEFINITELY occurred.

Your job is to classify what HAPPENED — what the bowler bowled, what \
the batter did, and what was visible.  You are NOT asked for player \
names, score, overs, bowler speed, or fielder positions — those come \
from a separate scoreboard pipeline.  Do not attempt to fill them in.

Return ONLY a single JSON object on one line, no prose, no markdown \
fences, no commentary outside the JSON.

Schema (every field required, every enum exact, "unknown" always \
allowed and PREFERRED over guessing):

{
  "is_valid_delivery":  true | false,
  "bowling_angle":      "over_the_wicket" | "round_the_wicket" | "unknown",
  "bowling_type":       "fast" | "medium" | "spin" | "unknown",
  "length":             "yorker" | "full" | "good_length" |
                        "short_of_length" | "short" | "bouncer" |
                        "full_toss" | "unknown",
  "line":               "wide_outside_off" | "outside_off" | "off_stump" |
                        "middle_stump" | "leg_stump" | "down_leg" |
                        "wide_down_leg" | "unknown",
  "bounce":             "low" | "normal" | "steep" | "extra" | "unknown",
  "shot_played":        true | false,
  "shot_type":          "leave" | "defend" | "drive" | "cut" | "pull" |
                        "hook" | "flick" | "glance" | "sweep" |
                        "reverse_sweep" | "slog" | "dab" | "ramp" |
                        "no_shot" | "unknown",
  "shot_side":          "off" | "leg" | "straight" | "behind" | "no_shot",
  "shot_angle":         "behind_wicket" | "square" | "mid" |
                        "down_ground" | "no_shot",
  "elevation":          "along_ground" | "in_air" | "no_shot",
  "contact_quality":    "middled" | "well_timed" | "mistimed" |
                        "edged" | "inside_edge" | "outside_edge" |
                        "off_pad" | "beaten" | "left_alone" | "missed" |
                        "unknown",
  "narrative":          "<2-3 sentence description of the delivery and \
shot, focused on what is actually visible.  No player names, no \
fielder positions, no scoreboard restating, no speculation.>",
  "confidence":         "high" | "medium" | "low"
}

CRITICAL rules:
- DO NOT guess.  If a field is not visible in the video, set it to \
"unknown" (or "no_shot" / "no_shot" for shot_side/shot_angle if no \
shot was played).  An "unknown" answer is BETTER than a wrong answer.
- DO NOT pull from cricket priors.  E.g. don't default length to \
"good_length" just because it's the modal IPL length.  Only commit \
to a length if you can see the bounce point relative to the batter.
- DO NOT fabricate fielder positions or player names in the narrative.
- shot_played=false implies shot_side="no_shot", shot_angle="no_shot", \
elevation="no_shot", shot_type in {"leave","no_shot","unknown"}, \
contact_quality in {"left_alone","missed","beaten","unknown"}.
- bowling_angle "round_the_wicket" is the EXCEPTION (~10-15% of T20 \
deliveries) — only choose it if you can see the bowler's run-up cross \
to the OPPOSITE side of the stumps before release.  Otherwise "over_\
the_wicket" or "unknown".
- bounce "steep" requires visible chest/shoulder bounce off the pitch; \
"low" requires the ball staying below knee.  Default to "normal" only \
if a normal bounce is actually visible.
- is_valid_delivery=false if the clip is clearly NOT a delivery \
(replay-only / wicket celebration / drinks break / blank cut).  We \
will trust the scoreboard otherwise — set to true even if the camera \
work is unusual.
- confidence="high" only if the camera showed a clean release + \
flight + bounce + shot sequence.  Otherwise "medium" or "low".
"""


# ── Mapping Gemini schema -> existing delivery_info shape ───────────
# test_pipeline.py + wire.py + commentary consume these legacy keys.
# We map Gemini's enums onto them so nothing downstream changes.

_LINE_GEMINI_TO_LEGACY = {
    "wide_outside_off": "wide_outside_off",
    "outside_off":      "outside_off",
    "off_stump":        "off_stump",
    "middle_stump":     "on_stumps",
    "leg_stump":        "leg_stump",
    "down_leg":         "on_pads",
    "wide_down_leg":    "down_leg",
    "unknown":          "unknown",
}

_LENGTH_VOCAB = {"yorker", "full", "good_length", "short_of_length",
                 "short", "bouncer", "full_toss", "unknown"}

_LENGTH_TEXT = {
    "yorker": "yorker",
    "full": "full",
    "good_length": "good length",
    "short_of_length": "short of a length",
    "short": "short",
    "bouncer": "bouncer",
    "full_toss": "full toss",
}

_LINE_TEXT_LEGACY = {
    "wide_outside_off": "wide outside off",
    "outside_off": "outside off",
    "off_stump": "on off stump",
    "on_stumps": "on the stumps",
    "leg_stump": "on leg stump",
    "on_pads": "down the leg side",
    "down_leg": "wide down leg",
}

_SHOT_TYPE_VOCAB = {"leave", "defend", "drive", "cut", "pull", "hook",
                    "flick", "glance", "sweep", "reverse_sweep", "slog",
                    "dab", "ramp", "no_shot", "unknown"}

_SHOT_VERB = {
    "drive":         "driven",
    "cut":           "cut",
    "pull":          "pulled",
    "hook":          "hooked",
    "flick":         "flicked",
    "glance":        "glanced",
    "sweep":         "swept",
    "reverse_sweep": "reverse-swept",
    "slog":          "slogged",
    "dab":           "dabbed",
    "ramp":          "ramped",
    "defend":        "defended",
    "leave":         "left alone",
    "no_shot":       "no shot played",
}

_SHOT_SIDE_VOCAB = {"off", "leg", "straight", "behind", "no_shot"}
_SHOT_ANGLE_VOCAB = {"behind_wicket", "square", "mid", "down_ground",
                     "no_shot"}
_ELEVATION_VOCAB = {"along_ground", "in_air", "no_shot"}
_BOUNCE_VOCAB = {"low", "normal", "steep", "extra", "unknown"}
_BOWLING_ANGLE_VOCAB = {"over_the_wicket", "round_the_wicket", "unknown"}
_BOWLING_TYPE_VOCAB = {"fast", "medium", "spin", "unknown"}
_HANDED_VOCAB = {"right", "left", "unknown"}
_CONTACT_VOCAB = {"middled", "well_timed", "mistimed", "edged",
                  "inside_edge", "outside_edge", "off_pad", "beaten",
                  "left_alone", "missed", "unknown"}

_ZONE_FROM_ANGLE = {
    "behind_wicket": "behind",
    "square":        "square",
    "mid":           "mid",
    "down_ground":   "down_the_ground",
    "no_shot":       "unknown",
}

_LEGACY_ELEVATION = {
    "along_ground": "along_ground",
    "in_air":       "in_the_air",
    "no_shot":      "unknown",
}

_LEGACY_BOWLING_ANGLE = {
    "over_the_wicket":  "over",
    "round_the_wicket": "round",
    "unknown":          "unknown",
}


def _enum(value: Any, vocab: set[str], fallback: str = "unknown") -> str:
    if not isinstance(value, str):
        return fallback
    v = value.strip().lower().replace(" ", "_").replace("-", "_")
    return v if v in vocab else fallback


def _build_commentary_line(d: dict) -> str:
    """Compact human commentary from the normalized fields."""
    parts: list[str] = []
    btype = d.get("bowling_type")
    if btype in ("fast", "medium", "spin"):
        parts.append(btype)
    bangle = d.get("bowling_angle")
    if bangle == "round":
        parts.append("round the wicket")
    length_text = _LENGTH_TEXT.get(d.get("length", ""))
    if length_text:
        parts.append(length_text)
    line_text = _LINE_TEXT_LEGACY.get(d.get("line", ""))
    if line_text:
        parts.append(line_text)
    bounce = d.get("bounce")
    if bounce in ("steep", "low", "extra"):
        parts.append(f"{bounce} bounce")

    action = d.get("shot_action") or d.get("shot_type", "")
    sd = d.get("shot_direction") or {}
    zone = sd.get("zone")
    elev = d.get("shot_elevation")
    verb = _SHOT_VERB.get(action, "")
    if verb and action != "no_shot":
        clause = verb
        zone_phrase = {
            "behind":          "behind the wicket",
            "square":          "square of the wicket",
            "mid":             "into the mid",
            "down_the_ground": "down the ground",
        }.get(zone, "")
        if zone_phrase:
            clause = f"{verb} {zone_phrase}"
        parts.append(clause)
    elif action in ("no_shot", "leave"):
        parts.append("left alone")

    if elev == "in_the_air":
        parts.append("in the air")
    elif elev == "along_ground":
        parts.append("along the ground")

    cq = d.get("contact_quality")
    if cq in ("edged", "inside_edge", "outside_edge", "beaten",
              "missed", "off_pad"):
        parts.append({
            "edged":         "edged",
            "inside_edge":   "off the inside edge",
            "outside_edge":  "off the outside edge",
            "beaten":        "beaten",
            "missed":        "swung and missed",
            "off_pad":       "off the pad",
        }[cq])

    return ", ".join(parts) or "no classification available"


# ── mp4 compilation ─────────────────────────────────────────────────

def compile_frames_to_mp4(
    frames: list[tuple[float, np.ndarray]],
    out_path: str | None = None,
    fps: float | None = None,
    max_width: int | None = None,
) -> str:
    """Compile (ts, BGR) frames into an mp4 at `out_path`.

    Encoder defaults updated 2026-04-20 to stop throwing away the
    information Gemini needs for length classification:
      - `fps=None` (default) derives the actual frame rate from the
        frame timestamps, so playback speed matches reality and the
        bounce moment isn't temporally smeared.  Pass an explicit
        float to override (e.g. for slow-mo experiments).
      - `max_width=None` (default) preserves whatever resolution the
        caller already picked.  The previous hard-coded 720 px cap
        was a 4× pixel reduction below the buffer's 960 px frames
        and measurably hurt length perception.  Pass a value if the
        caller wants an additional safety cap.

    Returns the path to the written mp4.
    """
    if not frames:
        raise ValueError("compile_frames_to_mp4: empty frames")
    if out_path is None:
        fd, out_path = tempfile.mkstemp(prefix="delivery_", suffix=".mp4")
        os.close(fd)

    if fps is None:
        if len(frames) >= 2:
            duration = frames[-1][0] - frames[0][0]
            if duration > 0:
                fps = (len(frames) - 1) / duration
            else:
                fps = 30.0
        else:
            fps = 30.0
        # Clamp to a sane range so a single bad timestamp can't
        # produce a 1000 fps file or a 0.1 fps slideshow.
        fps = max(5.0, min(120.0, fps))

    h0, w0 = frames[0][1].shape[:2]
    if max_width is not None and w0 > max_width:
        scale = max_width / w0
        out_w = max_width
        out_h = int(h0 * scale)
    else:
        out_w = w0
        out_h = h0
    if out_w % 2:
        out_w -= 1
    if out_h % 2:
        out_h -= 1

    # Try avc1 (h264) first — best compression.  Fall back to mp4v
    # (mpeg4) which is universally available in opencv builds.
    for fourcc_str in ("avc1", "mp4v"):
        fourcc = cv2.VideoWriter_fourcc(*fourcc_str)
        writer = cv2.VideoWriter(out_path, fourcc, fps, (out_w, out_h))
        if writer.isOpened():
            break
        writer.release()
    else:
        raise RuntimeError("compile_frames_to_mp4: no working fourcc")

    for _ts, fr in frames:
        if fr.shape[1] != out_w or fr.shape[0] != out_h:
            fr_out = cv2.resize(fr, (out_w, out_h),
                                interpolation=cv2.INTER_AREA)
        else:
            fr_out = fr
        writer.write(fr_out)
    writer.release()
    return out_path


# ── JSON parsing ────────────────────────────────────────────────────

def _parse_json(raw: str) -> dict | None:
    if not raw:
        return None
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not m:
        return None
    blob = m.group(0)
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        for i in range(len(blob), 0, -1):
            if blob[i - 1] == "}":
                try:
                    return json.loads(blob[:i])
                except json.JSONDecodeError:
                    continue
    return None


# ── Public classifier ───────────────────────────────────────────────

def _shot_type_from_runs(runs: int) -> str:
    if runs == 0:
        return "defended"
    if runs == 6:
        return "in_the_air"
    if runs == 4:
        return "unknown"
    return "along_ground"


def _unknown_result(runs: int, reason: str,
                    raw: str | None = None,
                    ms: float = 0.0,
                    extras: dict | None = None) -> dict:
    out: dict = {
        # Legacy delivery_info shape (what test_pipeline / wire / UI
        # already consume)
        "length": "unknown", "line": "unknown",
        "bowling_angle": "unknown", "bounce": "unknown",
        "shot_type": _shot_type_from_runs(runs),
        "shot_elevation": _shot_type_from_runs(runs),
        "shot_action": "unknown",
        "shot_intent": "unknown",
        "shot_direction": {"side": "unknown", "zone": "unknown",
                           "confidence": "none"},
        "swing_or_seam": "not_visible",
        "ball_speed_visible": False,
        "ball_speed_kph_vlm": None,
        "runs": runs,
        "detections": 0,
        "detection_rate": 0.0,
        "commentary_line": "",
        # New Tier 1+2 fields (additive).  Downstream consumers can
        # opt in.
        "batsman_handed": "unknown",
        "bowling_arm":    "unknown",
        "bowling_type":   "unknown",
        "contact_quality": "unknown",
        "narrative":      "",
        # Meta
        "_method":        "gemini",
        "_gemini_model":  GEMINI_DELIVERY_MODEL,
        "_gemini_ms":     round(ms),
        "_gemini_confidence": "low",
        "_untrackable":   True,
        "_skip_reason":   reason,
    }
    if raw:
        out["_gemini_raw"] = raw[:600]
    if extras:
        out.update(extras)
    return out


def _to_legacy_schema(p: dict, runs: int, raw: str, ms: float) -> dict:
    """Map Gemini schema -> existing delivery_info shape (additive)."""
    handed = _enum(p.get("batsman_handed"), _HANDED_VOCAB)
    bowling_arm = _enum(p.get("bowling_arm"), _HANDED_VOCAB)
    bowling_type = _enum(p.get("bowling_type"), _BOWLING_TYPE_VOCAB)
    bowling_angle_g = _enum(p.get("bowling_angle"), _BOWLING_ANGLE_VOCAB)
    bowling_angle_legacy = _LEGACY_BOWLING_ANGLE[bowling_angle_g]

    length = _enum(p.get("length"), _LENGTH_VOCAB)
    line_g = (p.get("line") or "unknown").strip().lower()
    line_legacy = _LINE_GEMINI_TO_LEGACY.get(line_g, "unknown")

    bounce = _enum(p.get("bounce"), _BOUNCE_VOCAB)

    shot_played = bool(p.get("shot_played", True))
    shot_type_g = _enum(p.get("shot_type"), _SHOT_TYPE_VOCAB)
    if not shot_played and shot_type_g not in ("leave", "no_shot",
                                               "unknown"):
        shot_type_g = "no_shot"

    shot_side = _enum(p.get("shot_side"), _SHOT_SIDE_VOCAB,
                      fallback="unknown")
    shot_angle = _enum(p.get("shot_angle"), _SHOT_ANGLE_VOCAB,
                       fallback="no_shot")
    elevation_g = _enum(p.get("elevation"), _ELEVATION_VOCAB,
                        fallback="no_shot")
    elevation_legacy = _LEGACY_ELEVATION[elevation_g]

    contact_quality = _enum(p.get("contact_quality"), _CONTACT_VOCAB)

    confidence = (p.get("confidence") or "medium").strip().lower()
    if confidence not in ("high", "medium", "low"):
        confidence = "medium"

    narrative = (p.get("narrative") or "").strip()

    # shot_intent fallback: derive from runs / contact / shot_played
    if not shot_played:
        shot_intent = "left"
    elif contact_quality in ("edged", "inside_edge", "outside_edge"):
        shot_intent = "edged"
    elif contact_quality in ("missed", "beaten"):
        shot_intent = "missed"
    elif runs >= 4:
        shot_intent = "attacked"
    elif runs == 0 and shot_type_g in ("defend", "leave"):
        shot_intent = "defended"
    elif runs == 0:
        shot_intent = "defended"
    else:
        shot_intent = "attacked"

    # shot_action: same as shot_type_g for the v1 mapping (the legacy
    # taxonomy was already a subset of Gemini's).  "defend" stays
    # "defend" so downstream verbs render correctly.
    shot_action = shot_type_g

    # Legacy `shot_type` field is overloaded as elevation in the
    # existing pipeline.  Honour that — set it to elevation_legacy if
    # known, otherwise the runs-based fallback.
    if elevation_legacy in ("along_ground", "in_the_air"):
        shot_type_field = elevation_legacy
    elif shot_type_g == "no_shot":
        shot_type_field = "defended"
    else:
        shot_type_field = _shot_type_from_runs(runs)

    out: dict = {
        # Legacy keys (delivery_info contract)
        "length":         length,
        "line":           line_legacy,
        "bowling_angle":  bowling_angle_legacy,
        "bounce":         bounce if bounce != "unknown" else "normal",
        "shot_type":      shot_type_field,
        "shot_elevation": elevation_legacy,
        "shot_action":    shot_action,
        "shot_intent":    shot_intent,
        "shot_direction": {
            "side":       shot_side,
            "zone":       _ZONE_FROM_ANGLE.get(shot_angle, "unknown"),
            "confidence": confidence,
        },
        "swing_or_seam":  "not_visible",  # Gemini doesn't classify this
        "ball_speed_visible": False,      # speed comes from scoreboard
        "ball_speed_kph_vlm": None,
        "runs":           runs,
        "detections":     0,
        "detection_rate": 0.0,
        "commentary_line": "",  # filled below

        # New Tier 1+2 keys (additive — opt-in for downstream)
        "batsman_handed":  handed,
        "bowling_arm":     bowling_arm,
        "bowling_type":    bowling_type,
        "contact_quality": contact_quality,
        "narrative":       narrative,

        # Meta
        "_method":            "gemini",
        "_gemini_model":      GEMINI_DELIVERY_MODEL,
        "_gemini_ms":         round(ms),
        "_gemini_confidence": confidence,
        "_gemini_raw":        raw[:600] if raw else "",
        "_is_valid_delivery": bool(p.get("is_valid_delivery", True)),
    }
    out["commentary_line"] = _build_commentary_line(out)
    return out


class GeminiDeliveryClassifier:
    """Classify a delivery from a video clip using gemini-3-flash-preview.

    Lazy-imports the google-genai SDK so the rest of the pipeline can
    boot even if the SDK or key is missing.  Use `available()` to
    check before relying on it in production.
    """

    def __init__(self, model: str | None = None,
                 api_key: str | None = None):
        self._model = model or GEMINI_DELIVERY_MODEL
        self._api_key = api_key or GEMINI_API_KEY
        self._client = None
        self._types = None
        self._calls = 0
        self._failures = 0
        self._last_ms = 0
        self._init_error: str | None = None
        self._init_client()

    def _init_client(self):
        try:
            os.environ.setdefault("GEMINI_API_KEY", self._api_key)
            from google import genai
            from google.genai import types
            self._client = genai.Client()
            self._types = types
        except Exception as e:  # noqa: BLE001
            self._init_error = str(e)
            log.warning(f"[GEMINI] SDK init failed: {e}")

    def available(self) -> bool:
        return self._client is not None

    def classify_video(self,
                       mp4_path: str,
                       runs: int = 0,
                       save_dir: str | None = None,
                       ) -> dict:
        if not self.available():
            return _unknown_result(runs, "gemini_unavailable",
                                   extras={"_gemini_init_error":
                                           self._init_error})

        try:
            data = Path(mp4_path).read_bytes()
        except Exception as e:  # noqa: BLE001
            return _unknown_result(runs, f"mp4_read_failed:{e}")

        if len(data) > 19 * 1024 * 1024:
            log.warning(f"[GEMINI] mp4 {len(data)/1024/1024:.1f}MB > 19MB "
                        f"— inline upload may fail; consider lowering fps")

        parts = [
            self._types.Part.from_bytes(data=data, mime_type="video/mp4"),
            self._types.Part.from_text(text=GEMINI_PROMPT),
        ]

        t0 = time.time()
        self._calls += 1
        try:
            resp = self._client.models.generate_content(
                model=self._model,
                contents=parts,
            )
            raw = resp.text or ""
        except Exception as e:  # noqa: BLE001
            self._failures += 1
            ms = (time.time() - t0) * 1000
            log.warning(f"[GEMINI] API error after {ms:.0f}ms: "
                        f"{str(e)[:200]}")
            return _unknown_result(runs, f"gemini_api_error",
                                   ms=ms,
                                   extras={"_gemini_error":
                                           str(e)[:300]})

        ms = (time.time() - t0) * 1000
        self._last_ms = round(ms)

        parsed = _parse_json(raw)
        if not parsed:
            self._failures += 1
            log.warning(f"[GEMINI] {ms:.0f}ms unparseable: {raw[:300]}")
            return _unknown_result(runs, "gemini_unparseable",
                                   raw=raw, ms=ms)

        result = _to_legacy_schema(parsed, runs, raw, ms)

        # If Gemini explicitly says it's not a valid delivery, flag
        # but do NOT reject — the scoreboard already confirmed.  We
        # downgrade to untrackable so the UI keeps the previous
        # delivery_info instead of overwriting with bad fields.
        if not result.get("_is_valid_delivery", True):
            log.info(f"[GEMINI] {ms:.0f}ms is_valid_delivery=false "
                     f"from model — keeping result but marking "
                     f"untrackable")
            result["_untrackable"] = True
            result["_skip_reason"] = "gemini_rejected_window"

        log.info(
            f"[GEMINI] {ms:.0f}ms model={self._model} "
            f"hand={result['batsman_handed']} "
            f"arm={result['bowling_arm']} "
            f"type={result['bowling_type']}/{result['bowling_angle']} "
            f"len={result['length']} line={result['line']} "
            f"bounce={result['bounce']} "
            f"shot={result['shot_action']}/"
            f"{result['shot_direction']['side']}-"
            f"{result['shot_direction']['zone']} "
            f"contact={result['contact_quality']} "
            f"conf={result['_gemini_confidence']}"
        )
        if result.get("narrative"):
            log.info(f"  >> {result['narrative']}")

        if save_dir:
            try:
                d = Path(save_dir)
                d.mkdir(parents=True, exist_ok=True)
                (d / "gemini_request.json").write_text(json.dumps({
                    "model":      self._model,
                    "mp4":        os.path.basename(mp4_path),
                    "mp4_bytes":  len(data),
                    "runs":       runs,
                    "prompt":     GEMINI_PROMPT,
                    "raw":        raw,
                    "wall_ms":    self._last_ms,
                    "parsed":     parsed,
                    "normalised": result,
                }, indent=2))
            except Exception as e:  # noqa: BLE001
                log.warning(f"[GEMINI] could not save request: {e}")

        return result

    def classify_frames(self,
                        frames: list[tuple[float, np.ndarray]],
                        runs: int = 0,
                        save_dir: str | None = None,
                        fps: float | None = None,
                        known_batsman_handed: str = "unknown",
                        known_bowling_arm: str = "unknown",
                        ) -> dict:
        """Compile frames -> mp4 -> classify.  Cleans up the temp file.

        `fps=None` (default) lets compile_frames_to_mp4 derive the
        true playback rate from frame timestamps.  Pass an explicit
        value only if you intentionally want a different rate.
        """
        if not frames:
            return _unknown_result(runs, "no_frames")
        mp4_path = None
        try:
            target_path = None
            if save_dir:
                d = Path(save_dir)
                d.mkdir(parents=True, exist_ok=True)
                target_path = str(d / "delivery_window.mp4")
            mp4_path = compile_frames_to_mp4(
                frames, out_path=target_path, fps=fps)
            return self.classify_video(mp4_path, runs=runs,
                                       save_dir=save_dir)
        finally:
            if mp4_path and not save_dir:
                try:
                    os.unlink(mp4_path)
                except OSError:
                    pass

    @property
    def stats(self) -> dict:
        return {"calls": self._calls,
                "failures": self._failures,
                "last_ms": self._last_ms,
                "model": self._model}
