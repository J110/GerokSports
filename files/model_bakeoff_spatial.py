"""Spatial-decomposition bake-off — Qwen vs Gemini, 3 runs for consistency.

Test design (per user 2026-04-20):
  • Same 5 clips as the prior bake-off.
  • Same 16-frame burst per clip.
  • NEW prompt (PROMPT_SPATIAL): asks 13 grounded spatial questions
    ("where does the ball first hit the pitch?") instead of cricket
    categories ("is this short_of_a_length?").
  • Code (spatial_to_cricket) maps the spatial answers back to the
    standard 14-field cricket schema so scoring against the existing
    truth is apples-to-apples with the prior cricket-category bake-off.
  • Models: qwen30b-instruct + gemini-3-flash-preview only (Scout dropped).
  • N_REPS=3 per cell, RUNS=3 separate matrix passes, so 9 samples per
    (model, clip, field) total.  This lets us read BOTH per-run accuracy
    AND run-to-run consistency.

Outputs:
  logs/audit_v1/bakeoff_spatial/run_<idx>/results.json
  logs/audit_v1/bakeoff_spatial/run_<idx>/report.md
  logs/audit_v1/bakeoff_spatial/consistency.md   (after all runs)
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import cv2

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from eyes.config import GEMINI_API_KEY  # noqa: E402

os.environ.setdefault("GEMINI_API_KEY", GEMINI_API_KEY)

FIREWORKS_API_KEY = os.environ.get(
    "FIREWORKS_API_KEY", "fw_8Kyu9Ug7kXVp6kPRDvhL3n")

N_REPS = 3
N_BURST = 16
JPEG_Q = 88
RUNS_DEFAULT = 3

MODELS = [
    ("qwen30b-instruct", "fireworks",
     "accounts/fireworks/models/qwen3-vl-30b-a3b-instruct"),
    ("gemini-3-flash", "gemini",
     "gemini-3-flash-preview"),
]

# Cricket-side scoring schema (same as cricket-category bake-off).
FIELDS = [
    "is_valid_delivery",
    "batsman_handed",
    "bowling_arm",
    "bowling_angle",
    "bowling_type",
    "length",
    "line",
    "bounce",
    "shot_played",
    "shot_type",
    "shot_side",
    "shot_angle",
    "elevation",
    "contact_quality",
]

# Same clips + truth as the prior bake-off.
CLIPS = [
    {"id": "ctrl_old2", "path": "ball_test_clip_60fps_long.mp4",
     "label": "CONTROL: Apr10 hi-fid SHORT/steep/pull",
     "truth": {
         "is_valid_delivery": True,
         "batsman_handed": "right",
         "bowling_arm": "right",
         "length": "short",
         "shot_played": True,
         "shot_type": "pull",
     }},
    {"id": "old1", "path": "ball_test_clip_30fps.mp4",
     "label": "Apr10 hi-fid: LEFT-handed defence square of wicket",
     "truth": {
         "is_valid_delivery": True,
         "batsman_handed": "left",
         "shot_played": True,
         "shot_type": "defend",
     }},
    {"id": "w19", "path":
     "logs/deliveries/20260420_140137/windows/window_0019/delivery_window.mp4",
     "label": "YT 3.0: round-arm, on stumps, defend (Mendis)",
     "truth": {
         "is_valid_delivery": True,
         "batsman_handed": "right",
         "bowling_arm": "right",
         "bowling_angle": "round_the_wicket",
         "bowling_type": "fast",
         "line": ["off_stump", "middle_stump", "leg_stump"],
         "bounce": "normal",
         "shot_played": True,
         "shot_type": "defend",
         "shot_side": "leg",
         "elevation": "along_ground",
     }},
    {"id": "w21", "path":
     "logs/deliveries/20260420_140137/windows/window_0021/delivery_window.mp4",
     "label": "YT 3.1: SHORT, off stump, pull (inside-edged)",
     "truth": {
         "is_valid_delivery": True,
         "batsman_handed": "right",
         "bowling_arm": "right",
         "bowling_angle": "over_the_wicket",
         "bowling_type": "fast",
         "length": "short",
         "line": "off_stump",
         "bounce": "normal",
         "shot_played": True,
         "shot_type": "pull",
         "shot_side": "leg",
         "shot_angle": "square",
         "elevation": "along_ground",
         "contact_quality": "inside_edge",
     }},
    {"id": "w23", "path":
     "logs/deliveries/20260420_140137/windows/window_0023/delivery_window.mp4",
     "label": "YT 3.2: SHORT, outside off, cut for FOUR",
     "truth": {
         "is_valid_delivery": True,
         "batsman_handed": "right",
         "bowling_arm": "right",
         "bowling_angle": "over_the_wicket",
         "bowling_type": "fast",
         "length": "short",
         "line": "outside_off",
         "bounce": "normal",
         "shot_played": True,
         "shot_type": "cut",
         "shot_side": "off",
         "shot_angle": "square",
         "elevation": "in_air",
         "contact_quality": "well_timed",
     }},
]


# ─────────────────── SPATIAL PROMPT ───────────────────

PROMPT_SPATIAL = """\
You are analyzing a video of a cricket delivery. The camera is behind \
the bowler, looking down the pitch toward the batsman. The batsman is \
facing the camera.

Return ONLY a single JSON object on one line.  For each field, return \
an object with two keys:
  - "value": one of the listed options for that field
  - "confidence": a number from 0.0 (no visual evidence) to 1.0 \
(absolutely certain)

Calibrate confidence honestly.  If the bounce is occluded, say so by \
returning {"value": "unknown", "confidence": 0.1}.  If you can clearly \
see the ball pitch on zone 3 of the pitch, return {"value": "3", \
"confidence": 0.95}.  Confidence should track how strong the visual \
evidence is, NOT how confident a typical answer would sound.

Example shape:
  {"ball_bounce_zone": {"value": "3", "confidence": 0.9}, \
"bat_swing": {"value": "horizontal", "confidence": 0.7}, ...}

Note: the bowler's bowling arm and the batsman's handedness are \
provided separately from a squad lookup — do NOT try to classify \
them here.  Focus on what is actually happening on this delivery.

Fields:

1. ball_bounce_zone
   Divide the pitch into four zones from bowler to batsman. Where \
does the ball first bounce?
   - "1_nearest_bowler"
   - "2"
   - "3"
   - "4_nearest_batsman"
   - "no_bounce"
   - "unknown"

2. ball_position_at_batsman
   When the ball reaches the batsman, where is it relative to the \
batsman's body (from camera view)?
   - "far_left_of_body"
   - "near_left_of_body"
   - "at_body_center"
   - "near_right_of_body"
   - "far_right_of_body"
   - "unknown"

3. ball_height_at_batsman
   When the ball reaches the batsman, what height is it at?
   - "at_feet"
   - "shin"
   - "knee_to_waist"
   - "waist_to_chest"
   - "chest_to_head"
   - "above_head"
   - "unknown"

4. bat_swing
   How does the bat move through the shot?
   - "vertical"
   - "horizontal"
   - "diagonal"
   - "minimal"
   - "no_swing"
   - "unknown"

5. shot_intent
   What was the batsman trying to do?
   - "aggressive"
   - "defensive"
   - "left"
   - "missed"
   - "unknown"

6. ball_direction_after_contact
   After the ball leaves the bat, which direction does it travel \
(from camera view)?
   - "back_toward_camera"
   - "forward_left"
   - "square_left"
   - "behind_left"
   - "forward_right"
   - "square_right"
   - "behind_right"
   - "straight_up"
   - "no_contact"
   - "unknown"

7. ball_elevation_after_contact
   After the ball leaves the bat:
   - "ground"
   - "low_air"
   - "high_air"
   - "no_contact"
   - "unknown"

8. fielder_reaction
   What does a fielder do after the shot?
   - "running"
   - "diving"
   - "catching"
   - "ball_past_fielder"
   - "none_visible"
   - "unknown"

9. ball_final_position
   After the shot (or after the ball passes the batsman if no shot \
was played), where does the ball end up?
   - "on_pitch"
   - "hit_stumps"
   - "inside_circle"
   - "outside_circle"
   - "crossed_boundary"
   - "unknown"

10. bowling_style
    What type of bowling is the bowler delivering?
    - "fast" : long run-up, fast arm action, ball travels quickly
    - "medium" : shorter run-up, moderate pace
    - "spin" : very short run-up, slower arm action, ball is slow
    - "unknown"

11. ball_bat_contact_point
    Where did the ball contact the bat?
    - "middle_of_bat" : ball hit the flat face of the bat
    - "top_of_bat" : ball hit near the top edge
    - "bottom_of_bat" : ball hit near the bottom edge
    - "inside_edge" : ball hit the inner edge of the bat (batsman's \
body side)
    - "outside_edge" : ball hit the outer edge of the bat (away from \
body)
    - "pad_or_body" : ball hit the batsman's pad or body, not the bat
    - "no_contact" : ball did not hit bat or body
    - "unknown"

Return only JSON.  Every field must be an object with both "value" \
and "confidence".
"""


# ─────────────────── SPATIAL → CRICKET MAPPER ───────────────────

def _gv(d, k):
    """Get the .value of d[k], handling both wrapped {value,confidence}
    shape and flat raw-value shape.  Lower-cased string, or original
    bool, or None."""
    v = d.get(k)
    if v is None:
        return None
    if isinstance(v, dict):
        v = v.get("value")
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    return str(v).strip().lower()


def _gc(d, k):
    """Get the .confidence of d[k] (0.0 if not provided)."""
    v = d.get(k)
    if isinstance(v, dict):
        try:
            return float(v.get("confidence", 0.0))
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _min_conf(*confs):
    """Min over provided confidences; 0.0 if all are 0 or empty."""
    cs = [c for c in confs if c is not None]
    if not cs:
        return 0.0
    return float(min(cs))


# Backward-compat alias used elsewhere in the file (sanity-check script).
def _g(d, k):  # noqa: D401
    return _gv(d, k)


def spatial_to_cricket(s: dict,
                       known_batsman_handed: str = "unknown",
                       known_bowling_arm: str = "unknown",
                       ) -> tuple[dict, dict]:
    """Translate the spatial JSON into the cricket schema.

    `known_batsman_handed` / `known_bowling_arm` let the caller inject
    the values resolved pre-match from the squad (see
    eyes/player_enrichment.py).  These flow into:
      - line mapping (ball_position_at_batsman → line)
      - shot_side mapping (camera direction → off/leg)
      - bowling_angle (requires arm to tell over-the-wicket from
        round-the-wicket given bowler position)
    They are NOT re-emitted as outputs — they belong on the batter /
    bowler rows, not the per-delivery diag.

    Returns (cricket_values, cricket_confidence).

    Each spatial field may be either:
      - {"value": "...", "confidence": 0.x}  (new wrapped shape)
      - "..."                                (legacy flat shape)

    Per-field confidence on the cricket side = MIN of the spatial
    confidences that fed into it (since every input must be right
    for the derivation to be).

    Frame of reference:
      Camera is BEHIND the bowler, looking down the pitch toward the
      batsman, who is FACING the camera.
      => Batsman's right-hand side appears on the LEFT of the camera frame.
         Batsman's left-hand side  appears on the RIGHT of the camera frame.

    Cricket convention:
      A right-handed batsman's OFF side is his right => CAMERA-LEFT.
      A right-handed batsman's LEG side is his left  => CAMERA-RIGHT.
      A left-handed batsman's  OFF side is his left  => CAMERA-RIGHT.
      A left-handed batsman's  LEG side is his right => CAMERA-LEFT.

      A right-arm-OVER bowler: umpire on bowler's left
        => bowler body on CAMERA-LEFT.
      A right-arm-ROUND bowler: umpire on bowler's right
        => bowler body on CAMERA-RIGHT.
      Left-arm: mirror.
    """
    out, conf = {}, {}

    # ── synthetic: is_valid_delivery (no direct question) ──
    if any(_gv(s, k) not in (None, "unknown")
           for k in ("ball_bounce_zone",
                     "ball_position_at_batsman")):
        out["is_valid_delivery"] = True
        conf["is_valid_delivery"] = max(_gc(s, "ball_bounce_zone"),
                                        _gc(s, "ball_position_at_batsman"))
    else:
        out["is_valid_delivery"] = "unknown"
        conf["is_valid_delivery"] = 0.0

    # 2026-04-21: bowling_arm + batsman_handed are no longer derived
    # from per-delivery frames. Handedness + bowling arm come from the
    # pre-match squad enrichment pass (eyes/player_enrichment.py) and
    # live on the batter/bowler rows. They are NOT re-emitted as
    # per-delivery outputs — but the caller can pass them in so we
    # can still derive `line`, `shot_side`, and `bowling_angle`
    # correctly (all three need the frame-of-reference).
    out["bowling_arm"] = "unknown"
    conf["bowling_arm"] = 0.0
    out["batsman_handed"] = "unknown"
    conf["batsman_handed"] = 0.0

    _arm = known_bowling_arm if known_bowling_arm in (
        "left", "right") else None
    _handed_inj = known_batsman_handed if known_batsman_handed in (
        "left", "right") else None

    # ── bowling_angle: known arm + spatial bowler pos ──
    # The prompt no longer asks for bowler_position_at_release (it
    # was only useful paired with a known arm).  If a future prompt
    # brings it back, we still honour it here.
    out["bowling_angle"] = "unknown"
    conf["bowling_angle"] = 0.0

    # ── 4. ball_bounce_zone → length ──
    bz = _gv(s, "ball_bounce_zone")
    out["length"] = {
        "1_nearest_bowler": "short",
        "2": "short_of_length",
        "3": "good_length",
        "4_nearest_batsman": "full",
        "no_bounce": "full_toss",
    }.get(bz, "unknown")
    conf["length"] = _gc(s, "ball_bounce_zone")

    # ── 5. ball_position_at_batsman + (injected) handedness → line ──
    bp = _gv(s, "ball_position_at_batsman")
    handed = _handed_inj  # frame-of-reference injected by caller
    LINE_MAP = {
        ("right", "far_left_of_body"):   "wide_outside_off",
        ("right", "near_left_of_body"):  "outside_off",
        ("right", "at_body_center"):     "middle_stump",
        ("right", "near_right_of_body"): "leg_stump",
        ("right", "far_right_of_body"):  "down_leg",
        ("left",  "far_right_of_body"):  "wide_outside_off",
        ("left",  "near_right_of_body"): "outside_off",
        ("left",  "at_body_center"):     "middle_stump",
        ("left",  "near_left_of_body"):  "leg_stump",
        ("left",  "far_left_of_body"):   "down_leg",
    }
    out["line"] = LINE_MAP.get((handed, bp), "unknown")
    # line confidence is capped by the ball-position measurement since
    # handedness is ground truth from the squad.
    conf["line"] = _gc(s, "ball_position_at_batsman") if handed else 0.0

    # ── 6. ball_height_at_batsman → bounce ──
    bh = _gv(s, "ball_height_at_batsman")
    out["bounce"] = {
        "at_feet": "low",
        "shin": "low",
        "knee_to_waist": "normal",
        "waist_to_chest": "normal",
        "chest_to_head": "steep",
        "above_head": "extra",
    }.get(bh, "unknown")
    conf["bounce"] = _gc(s, "ball_height_at_batsman")

    # ── 9 (first; shot_type uses it) → shot_side + shot_angle ──
    dir_ = _gv(s, "ball_direction_after_contact")
    # handedness here is the injected value from the squad lookup.
    if handed == "right":
        cam_to_side = {"left": "off", "right": "leg"}
    elif handed == "left":
        cam_to_side = {"left": "leg", "right": "off"}
    else:
        cam_to_side = {"left": "unknown", "right": "unknown"}
    DIR_TO_SIDE_ANGLE = {
        "back_toward_camera":   ("straight", "down_ground"),
        "forward_left":         (cam_to_side["left"],  "mid"),
        "square_left":          (cam_to_side["left"],  "square"),
        "behind_left":          (cam_to_side["left"],  "behind_wicket"),
        "forward_right":        (cam_to_side["right"], "mid"),
        "square_right":         (cam_to_side["right"], "square"),
        "behind_right":         (cam_to_side["right"], "behind_wicket"),
        "straight_up":          ("straight", "square"),
        "no_contact":           ("no_shot",  "no_shot"),
    }
    side, angle = DIR_TO_SIDE_ANGLE.get(dir_, ("unknown", "unknown"))
    out["shot_side"] = side
    out["shot_angle"] = angle
    # shot_side needs handedness (from squad) and direction (from
    # frame). Handedness is ground-truth here so confidence rides on
    # the direction read.
    conf["shot_side"] = (_gc(s, "ball_direction_after_contact")
                         if handed else 0.0)
    # shot_angle only depends on direction
    conf["shot_angle"] = _gc(s, "ball_direction_after_contact")

    # ── 7+8 → shot_played + shot_type ──
    swing = _gv(s, "bat_swing")
    intent = _gv(s, "shot_intent")
    line = out["line"]
    leg_side_lines = ("on_middle_stump", "leg_stump", "down_leg",
                      "middle_stump")
    off_side_lines = ("wide_outside_off", "outside_off", "off_stump")

    if intent == "left" or swing == "no_swing":
        out["shot_played"] = False
    elif intent in ("aggressive", "defensive", "missed") or swing in (
            "vertical", "horizontal", "diagonal", "minimal"):
        out["shot_played"] = True
    else:
        out["shot_played"] = "unknown"
    conf["shot_played"] = _min_conf(_gc(s, "bat_swing"),
                                    _gc(s, "shot_intent"))

    if intent == "left" or swing == "no_swing":
        out["shot_type"] = "leave"
        conf["shot_type"] = _min_conf(_gc(s, "bat_swing"),
                                      _gc(s, "shot_intent"))
    elif swing == "minimal" or intent == "defensive":
        out["shot_type"] = "defend"
        conf["shot_type"] = _min_conf(_gc(s, "bat_swing"),
                                      _gc(s, "shot_intent"))
    elif swing == "vertical":
        out["shot_type"] = "drive"
        conf["shot_type"] = _gc(s, "bat_swing")
    elif swing == "horizontal":
        # pull/cut needs swing + (direction OR line)
        if side == "leg":
            out["shot_type"] = "pull"
        elif side == "off":
            out["shot_type"] = "cut"
        elif line in leg_side_lines:
            out["shot_type"] = "pull"
        elif line in off_side_lines:
            out["shot_type"] = "cut"
        else:
            out["shot_type"] = "pull"
        conf["shot_type"] = _min_conf(
            _gc(s, "bat_swing"),
            max(_gc(s, "ball_direction_after_contact"),
                _gc(s, "ball_position_at_batsman")))
    elif swing == "diagonal":
        if bh in ("at_feet", "shin"):
            out["shot_type"] = "sweep"
        else:
            out["shot_type"] = "flick"
        conf["shot_type"] = _min_conf(_gc(s, "bat_swing"),
                                      _gc(s, "ball_height_at_batsman"))
    else:
        out["shot_type"] = "unknown"
        conf["shot_type"] = 0.0

    # ── 10. ball_elevation_after_contact → elevation ──
    out["elevation"] = {
        "ground": "along_ground",
        "low_air": "in_air",
        "high_air": "in_air",
        "no_contact": "no_shot",
    }.get(_gv(s, "ball_elevation_after_contact"), "unknown")
    conf["elevation"] = _gc(s, "ball_elevation_after_contact")

    # ── 13. bowling_style → bowling_type ──
    bs = _gv(s, "bowling_style")
    out["bowling_type"] = bs if bs in ("fast", "medium", "spin") \
        else "unknown"
    conf["bowling_type"] = _gc(s, "bowling_style")

    # ── 14. ball_bat_contact_point → contact_quality ──
    cp = _gv(s, "ball_bat_contact_point")
    out["contact_quality"] = {
        "middle_of_bat":   "well_timed",
        "top_of_bat":      "edged",
        "bottom_of_bat":   "edged",
        "inside_edge":     "inside_edge",
        "outside_edge":    "outside_edge",
        "pad_or_body":     "off_pad",
        "no_contact":      "missed",
    }.get(cp, "unknown")
    conf["contact_quality"] = _gc(s, "ball_bat_contact_point")

    return out, conf


# ─────────────────── helpers (shared with cricket bake-off) ───────────────────

def b64(b): return base64.b64encode(b).decode()


def normalise(field, v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (list, tuple)):
        return [normalise(field, x) for x in v]
    s = str(v).lower().strip()
    if s == "true": return True
    if s == "false": return False
    if s in {"unknown", "n/a", "na", "null", ""}:
        return "unknown"
    if field == "length" and s in {"short_of_a_length", "short_of_length"}:
        return "short_of_length"
    if field == "bowling_angle":
        if s in {"over", "over_the_wicket"}: return "over_the_wicket"
        if s in {"round", "round_the_wicket"}: return "round_the_wicket"
    if field == "line" and s == "middle":
        return "middle_stump"
    return s


def matches(pred, truth):
    if truth is None:
        return False
    if isinstance(truth, list):
        return pred in truth
    return pred == truth


def parse_json(text: str):
    """Pick the OUTER JSON object.  We use a brace-depth scan that
    starts at the first '{' and walks until depth returns to zero,
    respecting strings.  This avoids the old bug where the regex
    grabbed an inner ``{"value": ..., "confidence": ...}`` block.
    """
    if not text:
        return None
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    starts = [i for i, ch in enumerate(text) if ch == "{"]
    for start in starts:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    chunk = text[start:i + 1]
                    try:
                        return json.loads(chunk)
                    except Exception:
                        break
    # last-resort: greedy outer match
    g = re.search(r"\{[\s\S]*\}", text)
    if g:
        try:
            return json.loads(g.group(0))
        except Exception:
            return None
    return None


def burst(mp4: str, n: int) -> list[bytes]:
    cap = cv2.VideoCapture(mp4)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    out = []
    if total <= 0:
        cap.release()
        return out
    for i in range(n):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * (i + 0.5) / n))
        ok, fr = cap.read()
        if not ok:
            continue
        ok, j = cv2.imencode(".jpg", fr,
                             [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_Q])
        if ok:
            out.append(j.tobytes())
    cap.release()
    return out


def _img_parts_openai(frames):
    return [{"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{b64(f)}"}}
            for f in frames]


def call_openai_compat(client, model, frames, prompt, max_tokens=1200):
    content = _img_parts_openai(frames)
    content.append({"type": "text",
                    "text": f"Below are {len(frames)} keyframes "
                            f"(chronological order) from one cricket "
                            f"delivery clip.\n\n" + prompt})
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
            max_tokens=max_tokens,
            temperature=0.2,
        )
        ms = int((time.time() - t0) * 1000)
        u = resp.usage
        return (resp.choices[0].message.content or "", ms,
                getattr(u, "prompt_tokens", 0),
                getattr(u, "completion_tokens", 0), None)
    except Exception as e:
        return "", int((time.time() - t0) * 1000), 0, 0, str(e)[:300]


def call_gemini(client_g, types_g, frames, prompt):
    parts = []
    for f in frames:
        parts.append(types_g.Part.from_bytes(
            data=f, mime_type="image/jpeg"))
    parts.append(types_g.Part.from_text(
        text=f"Below are {len(frames)} keyframes (chronological "
             f"order) from one cricket delivery clip.\n\n" + prompt))
    t0 = time.time()
    try:
        resp = client_g.models.generate_content(
            model="gemini-3-flash-preview", contents=parts)
        ms = int((time.time() - t0) * 1000)
        u = getattr(resp, "usage_metadata", None)
        return (resp.text or "", ms,
                getattr(u, "prompt_token_count", 0) if u else 0,
                getattr(u, "candidates_token_count", 0) if u else 0,
                None)
    except Exception as e:
        return "", int((time.time() - t0) * 1000), 0, 0, str(e)[:300]


# ─────────────────── runner ───────────────────

def run_one(run_idx: int, run_dir: Path):
    from openai import OpenAI
    from google import genai
    from google.genai import types as gtypes

    run_dir.mkdir(parents=True, exist_ok=True)

    clients = {
        "fireworks": OpenAI(
            base_url="https://api.fireworks.ai/inference/v1",
            api_key=FIREWORKS_API_KEY),
    }
    gclient = genai.Client()

    bursts: dict[str, list[bytes]] = {}
    for c in CLIPS:
        p = ROOT / c["path"]
        if not p.exists():
            print(f"  missing: {p}")
            continue
        bursts[c["id"]] = burst(str(p), N_BURST)
        kb = sum(len(f) for f in bursts[c["id"]]) / 1024
        print(f"clip {c['id']:10s} {len(bursts[c['id']])} frames, "
              f"{kb:5.0f} KB — {c['label']}")
    print()

    rows = []
    n_total = sum(1 for c in CLIPS if c["id"] in bursts) \
        * len(MODELS) * N_REPS
    i = 0

    for clip in CLIPS:
        frames = bursts.get(clip["id"])
        if not frames:
            continue
        print(f"\n{'='*78}")
        print(f"RUN {run_idx}  clip {clip['id']:10s} — {clip['label']}")
        truth_str = ", ".join(f"{k}={v}" for k, v in clip["truth"].items())
        print(f"  truth: {truth_str}")
        print(f"{'='*78}")

        for model_tag, provider, model_id in MODELS:
            for rep in range(N_REPS):
                i += 1
                if provider == "gemini":
                    text, ms, in_tok, out_tok, err = call_gemini(
                        gclient, gtypes, frames, PROMPT_SPATIAL)
                else:
                    client = clients[provider]
                    text, ms, in_tok, out_tok, err = call_openai_compat(
                        client, model_id, frames, PROMPT_SPATIAL,
                        max_tokens=1200)

                spatial = parse_json(text) or {}
                cricket_v, cricket_c = spatial_to_cricket(spatial)
                pred = {f: normalise(f, cricket_v.get(f)) for f in FIELDS}
                pred_conf = {f: float(cricket_c.get(f, 0.0))
                             for f in FIELDS}

                truth = {f: normalise(f, v)
                         for f, v in clip["truth"].items()}
                hits = []
                for f in FIELDS:
                    if f not in truth:
                        continue
                    p = pred.get(f)
                    hits.append((f, truth[f], p, pred_conf[f],
                                 matches(p, truth[f])))
                n_truth = len(hits)
                n_ok = sum(1 for *_, ok in hits if ok)

                err_str = f" ERR={err[:60]}" if err else ""
                print(f"  [{i:3d}/{n_total}] {model_tag:18s} rep{rep+1} "
                      f"({ms/1000:5.1f}s in={in_tok} out={out_tok}) "
                      f"per-field {n_ok}/{n_truth}{err_str}")
                pf = " ".join(
                    f"{f}={p}@{c:.2f}{'✓' if ok else '✗'}"
                    for f, _, p, c, ok in hits)
                print(f"        {pf}")

                rows.append({
                    "run": run_idx,
                    "clip": clip["id"],
                    "model": model_tag,
                    "provider": provider,
                    "rep": rep + 1,
                    "ms": ms,
                    "in_tok": in_tok,
                    "out_tok": out_tok,
                    "error": err,
                    "truth": truth,
                    "spatial": spatial,
                    "pred": pred,
                    "pred_conf": pred_conf,
                    "n_ok": n_ok,
                    "n_truth": n_truth,
                    "raw": text,
                })

                if i % 3 == 0:
                    (run_dir / "results.json").write_text(
                        json.dumps(rows, indent=2, default=str))

    out_json = run_dir / "results.json"
    out_json.write_text(json.dumps(rows, indent=2, default=str))
    print(f"\nWrote {out_json}  ({len(rows)} rows)")

    md = render_run_report(rows, run_idx)
    out_md = run_dir / "report.md"
    out_md.write_text(md)
    print(f"Wrote {out_md}")
    return rows


# ─────────────────── reports ───────────────────

def pct(num, den):
    if den == 0:
        return "—"
    return f"{100*num/den:.0f}%"


def render_run_report(rows, run_idx):
    out = [
        f"# Spatial-decomposition bake-off — Run {run_idx}\n",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Models: {', '.join(m[0] for m in MODELS)}",
        f"Reps per (model, clip): {N_REPS}",
        f"Prompt: PROMPT_SPATIAL (13 grounded spatial questions). "
        f"Cricket-category schema produced by code-side mapping.",
        f"Scoring: a field is correct ONLY if the mapped cricket value "
        f"equals truth (after normalise).  Unknown counts as wrong.\n",
        f"## Per-field accuracy across all clips × reps\n",
    ]
    header = "| field | " + " | ".join(m[0] for m in MODELS) + " |"
    sep = "|---|" + "|".join("---" for _ in MODELS) + "|"
    out.append(header)
    out.append(sep)
    for fld in FIELDS:
        cells = []
        for model_tag, _, _ in MODELS:
            ok = den = 0
            for r in rows:
                if r["model"] != model_tag:
                    continue
                if fld not in r["truth"]:
                    continue
                den += 1
                if matches(r["pred"].get(fld), r["truth"][fld]):
                    ok += 1
            cells.append(f"{ok}/{den} ({pct(ok, den)})")
        out.append(f"| **{fld}** | " + " | ".join(cells) + " |")
    cells = []
    for model_tag, _, _ in MODELS:
        ok = sum(r["n_ok"] for r in rows if r["model"] == model_tag)
        den = sum(r["n_truth"] for r in rows if r["model"] == model_tag)
        cells.append(f"**{ok}/{den} ({pct(ok, den)})**")
    out.append(f"| **TOTAL** | " + " | ".join(cells) + " |")
    out.append("")

    out.append("## Per-clip per-field hits per model\n")
    for clip in CLIPS:
        if not any(r["clip"] == clip["id"] for r in rows):
            continue
        out.append(f"### {clip['id']} — {clip['label']}\n")
        truth_str = ", ".join(f"`{k}={v}`"
                              for k, v in clip["truth"].items())
        out.append(f"Truth: {truth_str}\n")
        out.append("| field | truth | " + " | ".join(
            f"{m[0]} (r1/r2/r3)" for m in MODELS) + " |")
        out.append("|---|---|" + "|".join("---" for _ in MODELS) + "|")
        for fld in FIELDS:
            if fld not in clip["truth"]:
                continue
            t = clip["truth"][fld]
            cells = []
            for model_tag, _, _ in MODELS:
                vals = []
                for rep in (1, 2, 3):
                    matching = [r for r in rows
                                if r["clip"] == clip["id"]
                                and r["model"] == model_tag
                                and r["rep"] == rep]
                    if matching:
                        v = matching[0]["pred"].get(fld)
                        c = (matching[0].get("pred_conf") or {}
                             ).get(fld, 0.0)
                        v_disp = v if v is not None else "—"
                        mark = "✓" if matches(v, t) else ""
                        vals.append(f"{v_disp}@{c:.2f}{mark}")
                    else:
                        vals.append("—")
                cells.append(" / ".join(str(x) for x in vals))
            out.append(f"| {fld} | `{t}` | " + " | ".join(cells) + " |")
        out.append("")

    # ── Confidence calibration ──
    out.append("## Confidence vs accuracy (per model)\n")
    out.append("Mean reported confidence and accuracy at three "
               "confidence-floor cuts.  A well-calibrated model should "
               "have higher accuracy at higher confidence cuts.\n")
    out.append("| model | mean conf | acc all | acc conf≥0.5 | "
               "acc conf≥0.7 | acc conf≥0.9 |")
    out.append("|---|---|---|---|---|---|")
    for model_tag, _, _ in MODELS:
        all_calls = [r for r in rows if r["model"] == model_tag]
        if not all_calls:
            continue
        cells = []
        # Per-field samples
        confs, hits = [], []
        for r in all_calls:
            for fld, t in r["truth"].items():
                p = r["pred"].get(fld)
                c = (r.get("pred_conf") or {}).get(fld, 0.0)
                confs.append(c)
                hits.append(1 if matches(p, t) else 0)
        mean_c = sum(confs)/len(confs) if confs else 0
        cells.append(f"{mean_c:.2f}")
        cells.append(f"{sum(hits)}/{len(hits)} "
                     f"({100*sum(hits)/max(1,len(hits)):.0f}%)")
        for floor in (0.5, 0.7, 0.9):
            mask = [(h, c) for h, c in zip(hits, confs) if c >= floor]
            ok = sum(h for h, _ in mask)
            den = len(mask)
            cells.append(f"{ok}/{den} ({pct(ok, den)})"
                         if den else "—")
        out.append(f"| {model_tag} | " + " | ".join(cells) + " |")
    out.append("")

    out.append("## Per-field mean confidence (when answered, all reps)\n")
    out.append("| field | " + " | ".join(m[0] for m in MODELS) + " |")
    out.append("|---|" + "|".join("---" for _ in MODELS) + "|")
    for fld in FIELDS:
        cells = []
        for model_tag, _, _ in MODELS:
            cs = [(r.get("pred_conf") or {}).get(fld)
                  for r in rows if r["model"] == model_tag
                  and fld in r["truth"]]
            cs = [c for c in cs if c is not None]
            if not cs:
                cells.append("—")
            else:
                cells.append(f"{sum(cs)/len(cs):.2f}")
        out.append(f"| **{fld}** | " + " | ".join(cells) + " |")
    out.append("")

    out.append("## Latency & token usage\n")
    out.append("| model | n calls | avg ms | avg in_tok | avg out_tok |")
    out.append("|---|---|---|---|---|")
    for model_tag, _, _ in MODELS:
        cell = [r for r in rows if r["model"] == model_tag]
        if not cell:
            continue
        avg_ms = int(sum(r["ms"] for r in cell) / len(cell))
        avg_in = int(sum(r["in_tok"] for r in cell) / len(cell))
        avg_out = int(sum(r["out_tok"] for r in cell) / len(cell))
        out.append(f"| {model_tag} | {len(cell)} | {avg_ms} | "
                   f"{avg_in} | {avg_out} |")

    err_rows = [r for r in rows if r["error"]]
    if err_rows:
        out.append(f"\n## API errors ({len(err_rows)})\n")
        out.append("| clip | model | rep | error |")
        out.append("|---|---|---|---|")
        for r in err_rows:
            out.append(f"| {r['clip']} | {r['model']} | {r['rep']} | "
                       f"`{r['error'][:120]}` |")
    return "\n".join(out)


def render_consistency_report(all_rows_by_run, base_dir: Path):
    """Compare per-field accuracy across the 3 runs."""
    out = [
        f"# Spatial-decomposition consistency report\n",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Runs: {len(all_rows_by_run)}",
        f"Per-run sample size: {N_REPS} reps × {len(CLIPS)} clips × "
        f"{len(MODELS)} models = {N_REPS*len(CLIPS)*len(MODELS)} calls",
        f"\n## Per-field accuracy by run\n",
    ]
    for model_tag, _, _ in MODELS:
        out.append(f"\n### {model_tag}\n")
        run_ids = sorted(all_rows_by_run.keys())
        header = "| field | " + " | ".join(f"run {ri}" for ri in run_ids)
        header += " | mean | spread |"
        out.append(header)
        out.append("|---|" + "|".join("---" for _ in run_ids) + "|---|---|")
        for fld in FIELDS:
            vals = []
            for ri in run_ids:
                rows = all_rows_by_run[ri]
                ok = den = 0
                for r in rows:
                    if r["model"] != model_tag:
                        continue
                    if fld not in r["truth"]:
                        continue
                    den += 1
                    if matches(r["pred"].get(fld), r["truth"][fld]):
                        ok += 1
                vals.append((ok, den))
            cells = [f"{o}/{d} ({pct(o, d)})" for o, d in vals]
            den = vals[0][1] if vals else 0
            if den:
                pcts = [100*o/d for o, d in vals if d > 0]
                mean = sum(pcts)/len(pcts) if pcts else 0
                spread = (max(pcts) - min(pcts)) if pcts else 0
                cells.append(f"{mean:.0f}%")
                cells.append(f"±{spread/2:.0f} pp")
            else:
                cells.append("—")
                cells.append("—")
            out.append(f"| **{fld}** | " + " | ".join(cells) + " |")
        # Total
        cells = []
        totals = []
        for ri in run_ids:
            rows = all_rows_by_run[ri]
            ok = sum(r["n_ok"] for r in rows if r["model"] == model_tag)
            den = sum(r["n_truth"] for r in rows if r["model"] == model_tag)
            totals.append((ok, den))
            cells.append(f"**{ok}/{den} ({pct(ok, den)})**")
        if totals and totals[0][1]:
            pcts = [100*o/d for o, d in totals if d > 0]
            mean = sum(pcts)/len(pcts) if pcts else 0
            spread = (max(pcts) - min(pcts)) if pcts else 0
            cells.append(f"**{mean:.0f}%**")
            cells.append(f"**±{spread/2:.0f} pp**")
        else:
            cells.append("—")
            cells.append("—")
        out.append(f"| **TOTAL** | " + " | ".join(cells) + " |")

    # Pooled (all 3 runs combined) - the headline number
    out.append("\n## Pooled across all 3 runs (the headline)\n")
    pooled = []
    for ri in sorted(all_rows_by_run.keys()):
        pooled.extend(all_rows_by_run[ri])
    header = "| field | " + " | ".join(m[0] for m in MODELS) + " |"
    out.append(header)
    out.append("|---|" + "|".join("---" for _ in MODELS) + "|")
    for fld in FIELDS:
        cells = []
        for model_tag, _, _ in MODELS:
            ok = den = 0
            for r in pooled:
                if r["model"] != model_tag:
                    continue
                if fld not in r["truth"]:
                    continue
                den += 1
                if matches(r["pred"].get(fld), r["truth"][fld]):
                    ok += 1
            cells.append(f"{ok}/{den} ({pct(ok, den)})")
        out.append(f"| **{fld}** | " + " | ".join(cells) + " |")
    cells = []
    for model_tag, _, _ in MODELS:
        ok = sum(r["n_ok"] for r in pooled if r["model"] == model_tag)
        den = sum(r["n_truth"] for r in pooled if r["model"] == model_tag)
        cells.append(f"**{ok}/{den} ({pct(ok, den)})**")
    out.append(f"| **TOTAL** | " + " | ".join(cells) + " |")

    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=RUNS_DEFAULT,
                        help="number of independent matrix passes")
    parser.add_argument("--start-from", type=int, default=1,
                        help="resume / skip earlier runs")
    args = parser.parse_args()

    base_dir = ROOT / "logs" / "audit_v1" / "bakeoff_spatial"
    base_dir.mkdir(parents=True, exist_ok=True)

    all_rows_by_run = {}
    for ri in range(args.start_from, args.runs + 1):
        run_dir = base_dir / f"run_{ri}"
        print(f"\n{'#'*78}")
        print(f"# RUN {ri} of {args.runs} → {run_dir}")
        print(f"{'#'*78}")
        rows = run_one(ri, run_dir)
        all_rows_by_run[ri] = rows

    # Pull in any earlier-run results that already exist on disk
    for ri in range(1, args.runs + 1):
        if ri in all_rows_by_run:
            continue
        rj = base_dir / f"run_{ri}" / "results.json"
        if rj.exists():
            all_rows_by_run[ri] = json.loads(rj.read_text())

    md = render_consistency_report(all_rows_by_run, base_dir)
    out_md = base_dir / "consistency.md"
    out_md.write_text(md)
    print(f"\nWrote {out_md}")


if __name__ == "__main__":
    main()
