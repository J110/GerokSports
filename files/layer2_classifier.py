"""Layer 2 — Qwen-only spatial classifier.

History:
  - Original L2 fired Qwen + Gemini-3-flash in parallel, routed per
    field by the offline audit's accuracy ownership, and merged.
  - Fix B (2026-04-22) capped Gemini at 15 s with Qwen-only fallback.
  - **Fix C (2026-04-22): Gemini retired entirely.**  Live monitoring
    of Fix B showed 100 % Gemini timeout (15/15 deliveries) — Gemini
    was consuming its 15 s budget and contributing zero field values
    to committed output while still occupying the thread pool worker
    past the timeout boundary (uncancellable HTTPS client), which
    queued subsequent deliveries behind a stuck worker.  Removing
    Gemini recovers the thread pool, removes the 15 s-per-delivery
    waste, and loses exactly what Gemini was contributing live: nothing.

Qwen bakeoff accuracy (used to decide which fields to publish vs
suppress post-Gemini):

  Publishable (≥ 70 %):
    batsman_handed     71 %
    bowling_arm        94 %
    shot_played       100 %
    shot_angle        100 %
    bounce            100 %

  Suppressed (< 70 %, null-ified rather than degraded) — these were
  Gemini-owned in the routing JSON and would have come back "unknown"
  anyway after retirement; explicit None + reason makes it legible
  to the commentary layer:
    bowling_angle      59 %
    bowling_type       33 %
    elevation          33 %   (→ shot_elevation downstream)
    contact_quality     0 %

  Defer to higher layers (Layer 3 slowed clips / Layer 4 replays):
    length, line, shot_type   (low everywhere in current L2)

For each delivery mp4 produced by the DWR we:

  1.  burst the mp4 into 16 evenly-spaced JPEG frames
  2.  call Qwen-30B-instruct (Fireworks) with the spatial
      decomposition prompt (PROMPT_SPATIAL from
      model_bakeoff_spatial.py)
  3.  parse the JSON and run spatial_to_cricket(...) to translate
      the 13 grounded spatial answers into the 14-field cricket
      schema (length, line, bounce, shot_type, contact_quality, ...)
  4.  commit fields whose self-rated confidence ≥ conf_floor (0.70
      by default); abstain → "unknown" otherwise
  5.  null-ify the 4 suppressed fields at the legacy-output
      boundary and attach `_suppression_reasons` for observability
  6.  emit a legacy `delivery_info` dict (unchanged schema) plus a
      `layer2.json` sidecar

Interface contract (matches GeminiDeliveryClassifier):
  - `available()` -> bool
  - `classify_video(mp4_path, runs, save_dir) -> dict`
  - `classify_frames(frames, runs, save_dir, fps=None) -> dict`
  - `.last_ms` / stats attrs for logging
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import numpy as np

from model_bakeoff_spatial import (
    PROMPT_SPATIAL,
    burst as _burst_mp4,
    call_openai_compat as _call_openai_compat,
    parse_json as _parse_spatial_json,
    spatial_to_cricket,
)
from gemini_delivery_classifier import (
    _LINE_GEMINI_TO_LEGACY,
    _LEGACY_BOWLING_ANGLE,
    _LEGACY_ELEVATION,
    _build_commentary_line,
    _shot_type_from_runs,
    compile_frames_to_mp4,
)

log = logging.getLogger("layer2_classifier")
try:
    from eyes.cricket_logger import _ensure_file_handler
    log.addHandler(_ensure_file_handler())
    log.setLevel(logging.INFO)
except Exception:
    pass


QWEN_NAME = "qwen30b-instruct"
# Legacy display name — kept for diagnostic sidecars and any log
# consumers that parse the previous "_gemini_model" field.
GEM_NAME = "gemini-3-flash (retired 2026-04-22)"

QWEN_MODEL = "accounts/fireworks/models/qwen3-vl-30b-a3b-instruct"
# Deprecated constant — no longer called but preserved so the legacy
# schema's `_gemini_model` key keeps a stable (if historical) value.
GEM_MODEL = "gemini-3-flash-preview (retired)"

FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"

# 2026-04-23: densification experiment Step 1 — uniform N=30.
#
# Rationale: the 2026-04 spatial bakeoff (logs/audit_v1/bakeoff_spatial/
# consistency.md) pinned `length` accuracy at 0/9 across Qwen, Gemini
# Flash, and Gemini Pro at N=16.  At ~2.7 s delivery duration, N=16
# yields ~6 fps effective sampling — the 30-50 ms ball bounce is aliased
# away entirely, so the signal `length` depends on isn't in the input.
#
# This is Step 1 of a falsifiable sequence (see session notes):
#   Step 1 (this change): uniform N=16 → N=30 single-pass densification.
#       Tests whether sampling density is the bottleneck at all.  If
#       length accuracy lifts 0% → 35-45%, we keep it and stop.
#   Step 2 (gated on Step 1 outcome): bounce-window two-pass with
#       physics-based `release_ts + 0.45s` estimation.
#   Step 3 (deferred): optical-flow / release-shot bracketing.
#
# HARD CAP: Fireworks' Qwen endpoint enforces 30 images/conversation
# (discovered 2026-04-23 live — initial N=32 attempt returned
# HTTP 400 "Too many images were provided, we currently limit the
# number of images per conversation to 30").  So the max we can push
# single-pass is N=30.  Step 2's bounce-window pass would be a SECOND
# call, not a denser first call, which is orthogonal to this cap.
#
# Cost: ~2× Qwen wall time on every L2 call (p50 ~5-7s → ~10-12s
# expected), and payload size ~1.5-3 MB (30 × 50-100 KB) well under
# Fireworks' 10 MB cap.  Accept the latency hit for the duration of
# the experiment; revisit if it pushes L2 timeouts.
N_BURST = 30
# Qwen via Fireworks: live p50 ~5-7 s at N=16; N=32 expected to roughly
# double that.  The 30 s ceiling is the hard fail cutoff; anything
# approaching that window indicates an upstream Fireworks problem
# (investigate, don't tune here).
QWEN_TIMEOUT_S = 30.0


def _load_routing() -> tuple[dict, float]:
    """Load `conf_floor` from layer2_routing.json.

    The per-field owner map is no longer consulted (Qwen is the only
    classifier), but we keep the loader so a custom `conf_floor` can
    still be injected without code changes.
    """
    p = Path(__file__).parent / "layer2_routing.json"
    if not p.exists():
        log.warning(
            "[L2] layer2_routing.json missing — defaulting "
            "conf_floor=0.70")
        return ({}, 0.70)
    try:
        d = json.loads(p.read_text())
        return (d.get("routing", {}), float(d.get("conf_floor", 0.70)))
    except Exception as e:  # noqa: BLE001
        log.warning(f"[L2] failed to load routing ({e}) — defaulting")
        return ({}, 0.70)


# Cricket fields we route/commit (is_valid_delivery is synthesised).
_ROUTABLE_FIELDS = [
    "is_valid_delivery", "batsman_handed", "bowling_arm",
    "bowling_angle", "bowling_type", "length", "line", "bounce",
    "shot_played", "shot_type", "shot_side", "shot_angle",
    "elevation", "contact_quality",
]

# Fields whose Qwen-alone accuracy is below the usable threshold in
# the bakeoff.  Null-ified at the legacy-output boundary so commentary
# downstream omits them rather than publishes low-accuracy content.
#
# Keys here are LEGACY (delivery_info) field names — not the internal
# cricket-schema names — because this suppression is applied AFTER
# _routed_to_legacy() runs.  Mapping:
#   bowling_type       → bowling_type (direct)
#   contact_quality    → contact_quality (direct)
#   elevation          → shot_elevation (legacy name)
#   bowling_angle      → bowling_angle (legacy, _LEGACY_BOWLING_ANGLE)
SUPPRESSED_LEGACY_FIELDS = (
    "bowling_type",
    "contact_quality",
    "shot_elevation",
    "bowling_angle",
)

_SUPPRESSION_REASON = "low_accuracy_without_gemini"


def _route_qwen_only(
    q_vals: dict, q_confs: dict, conf_floor: float,
) -> tuple[dict, dict, dict]:
    """Commit Qwen field values above conf_floor; abstain otherwise.

    Replaces the prior Q + G routing after Gemini was retired.  The
    shape of the return tuple is preserved so downstream layer2.json
    sidecars and logging continue to parse.

    Returns (committed_vals, committed_conf, per_field_diag).
    """
    committed: dict[str, Any] = {}
    committed_conf: dict[str, float] = {}
    diag: dict[str, dict] = {}

    for fld in _ROUTABLE_FIELDS:
        own_val = q_vals.get(fld)
        own_conf = float(q_confs.get(fld, 0.0) or 0.0)

        is_unk = own_val in (None, "unknown", "none", "")
        if isinstance(own_val, bool):
            is_unk = False
        committed_flag = (not is_unk) and own_conf >= conf_floor

        if committed_flag:
            committed[fld] = own_val
            committed_conf[fld] = own_conf
        else:
            if isinstance(own_val, bool):
                committed[fld] = None
            else:
                committed[fld] = "unknown"
            committed_conf[fld] = 0.0

        diag[fld] = {
            "owner": QWEN_NAME,
            "committed": committed_flag,
            "owner_value": own_val,
            "owner_conf": round(own_conf, 3),
        }

    return committed, committed_conf, diag


def _apply_suppression(legacy: dict) -> dict:
    """Null-ify the Gemini-dependent fields Qwen is too inaccurate on.

    Called at the legacy-output boundary.  Setting the field to `None`
    plays cleanly with the existing commentary line builder, whose
    enum membership checks (`if btype in ("fast","medium","spin"):`)
    naturally skip None values.  Records `_suppression_reasons` for
    observability downstream.
    """
    reasons = legacy.get("_suppression_reasons") or {}
    for fld in SUPPRESSED_LEGACY_FIELDS:
        # Preserve "normal" default on bounce-like defaults if the key
        # happens to match (it doesn't today, but be explicit).
        legacy[fld] = None
        reasons[fld] = _SUPPRESSION_REASON

    # shot_direction.confidence label stays meaningful (derived from
    # the MEAN of committed confs on PUBLISHABLE fields only), but we
    # don't touch shot_direction.{side,zone} — those come from shot
    # geometry which Qwen handles well.

    legacy["_suppression_reasons"] = reasons
    return legacy


def _bool_val(x: Any, default: bool = True) -> bool:
    """Cast spatial_to_cricket's bool-ish outputs safely."""
    if isinstance(x, bool):
        return x
    if isinstance(x, str):
        s = x.strip().lower()
        if s in ("true", "yes", "1"):
            return True
        if s in ("false", "no", "0"):
            return False
    return default


def _routed_to_legacy(routed: dict, conf: dict, runs: int,
                      wall_ms: float) -> dict:
    """Translate routed 14-field cricket dict into the legacy
    delivery_info schema consumed by test_pipeline / wire / UI.

    Mirrors gemini_delivery_classifier._to_legacy_schema but sourced
    from Qwen-routed fields and with "unknown" propagated honestly on
    abstentions.  After this runs, `_apply_suppression()` null-ifies
    the 4 Gemini-dependent fields."""
    handed = routed.get("batsman_handed") or "unknown"
    bowling_arm = routed.get("bowling_arm") or "unknown"
    bowling_type = routed.get("bowling_type") or "unknown"
    bowling_angle_g = routed.get("bowling_angle") or "unknown"
    bowling_angle_legacy = _LEGACY_BOWLING_ANGLE.get(
        bowling_angle_g, "unknown")

    length = routed.get("length") or "unknown"
    line_g = routed.get("line") or "unknown"
    line_legacy = _LINE_GEMINI_TO_LEGACY.get(line_g, "unknown")

    bounce = routed.get("bounce") or "unknown"

    shot_played = _bool_val(routed.get("shot_played"), True)
    shot_type_g = routed.get("shot_type") or "unknown"
    if not shot_played and shot_type_g not in (
            "leave", "no_shot", "unknown"):
        shot_type_g = "no_shot"

    shot_side = routed.get("shot_side") or "unknown"
    shot_angle = routed.get("shot_angle") or "no_shot"
    elevation_g = routed.get("elevation") or "no_shot"
    elevation_legacy = _LEGACY_ELEVATION.get(elevation_g, "unknown")

    contact_quality = routed.get("contact_quality") or "unknown"

    # shot_intent fallback: derive from runs / contact / shot_played.
    # Note: contact_quality is a SUPPRESSED field post-Fix-C; the
    # branches below using it fire only when Qwen happened to commit
    # a value (rare — bakeoff 0 %).  Keep the derivation for
    # structural compatibility; the dominant path is runs-based.
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

    shot_action = shot_type_g

    if elevation_legacy in ("along_ground", "in_the_air"):
        shot_type_field = elevation_legacy
    elif shot_type_g == "no_shot":
        shot_type_field = "defended"
    else:
        shot_type_field = _shot_type_from_runs(runs)

    zone_from_angle = {
        "behind_wicket": "behind",
        "square":        "square",
        "mid":           "mid",
        "down_ground":   "down_the_ground",
        "no_shot":       "unknown",
        "unknown":       "unknown",
    }

    # Overall confidence label from the mean of committed confidences.
    committed_confs = [
        v for v in conf.values() if v is not None and v > 0]
    if committed_confs:
        mean_c = sum(committed_confs) / len(committed_confs)
        conf_label = (
            "high" if mean_c >= 0.85
            else "medium" if mean_c >= 0.70
            else "low")
    else:
        conf_label = "low"

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
            "zone":       zone_from_angle.get(shot_angle, "unknown"),
            "confidence": conf_label,
        },
        "swing_or_seam":  "not_visible",
        "ball_speed_visible": False,
        "ball_speed_kph_vlm": None,
        "runs":           runs,
        "detections":     0,
        "detection_rate": 0.0,
        "commentary_line": "",

        # Tier 1+2 additive keys
        "batsman_handed":  handed,
        "bowling_arm":     bowling_arm,
        "bowling_type":    bowling_type,
        "contact_quality": contact_quality,
        "narrative":       "",

        # Meta
        "_method":            "layer2",
        # `_gemini_*` keys retained for downstream schema stability
        # (see bakeoff_delivery_models / ball_analyzer / smoke tests).
        # `_gemini_ms` now reports the Qwen wall time since that's the
        # only classifier call and thus the L2 latency that matters
        # for monitoring.
        "_gemini_model":      GEM_MODEL,
        "_qwen_model":        QWEN_MODEL,
        "_gemini_ms":         round(wall_ms),
        "_gemini_confidence": conf_label,
        "_is_valid_delivery": _bool_val(
            routed.get("is_valid_delivery"), True),
    }
    out["commentary_line"] = _build_commentary_line(out)
    return out


class Layer2Classifier:
    """Qwen-only spatial classifier — drop-in replacement for
    GeminiDeliveryClassifier in the DWR pipeline.

    Post Fix C (2026-04-22): Gemini path retired.  Sequential single
    API call per delivery; no thread pool, no timeout-fallback
    bookkeeping, no merge step.
    """

    def __init__(self):
        self._fw_client = None
        self._routing: dict = {}
        self._conf_floor: float = 0.70
        self._init_error: str | None = None
        self._calls = 0
        self._failures = 0
        self._last_ms = 0
        self._last_q_ms = 0
        # Retained and always 0 so any diagnostic readers that poll
        # `_last_g_ms` during the deploy/rollback window don't blow up.
        self._last_g_ms = 0
        self._init_clients()

    def _init_clients(self):
        self._routing, self._conf_floor = _load_routing()
        try:
            from openai import OpenAI
            api_key = os.environ.get(
                "FIREWORKS_API_KEY", "fw_8Kyu9Ug7kXVp6kPRDvhL3n")
            self._fw_client = OpenAI(
                base_url=FIREWORKS_BASE_URL, api_key=api_key)
        except Exception as e:  # noqa: BLE001
            self._init_error = f"fireworks:{e}"
            log.warning(f"[L2] Fireworks client init failed: {e}")

        log.info(
            f"[L2] ready (Qwen-only, post Fix-C) "
            f"fw={self._fw_client is not None} "
            f"conf_floor={self._conf_floor:.2f} "
            f"suppressed_fields={list(SUPPRESSED_LEGACY_FIELDS)}")

    def available(self) -> bool:
        return self._fw_client is not None

    @property
    def last_ms(self) -> int:
        return self._last_ms

    def gemini_timeout_fallback_rate(self) -> tuple[int, int, float]:
        """Back-compat shim for the Fix-B monitor.

        Gemini is retired in Fix C; this always returns (0, calls, 0.0)
        so the monitor script reports a clean zero and eventually gets
        removed in a follow-up cleanup.  Kept until external callers
        are migrated off it.
        """
        return (0, self._calls, 0.0)

    def classify_video(self, mp4_path: str, runs: int = 0,
                       save_dir: str | None = None,
                       known_batsman_handed: str = "unknown",
                       known_bowling_arm: str = "unknown") -> dict:
        if not self.available():
            return _unknown_legacy(runs, "layer2_unavailable", {
                "_l2_init_error": self._init_error,
            })

        try:
            frames = _burst_mp4(mp4_path, N_BURST)
        except Exception as e:  # noqa: BLE001
            return _unknown_legacy(runs, f"burst_failed:{e}", {})

        if not frames:
            return _unknown_legacy(runs, "empty_burst", {})

        self._calls += 1
        t0 = time.time()

        # Single synchronous Qwen call.  Previously this was the Q
        # branch of a parallel Q+G future pair; post Fix-C there is no
        # G branch to race against, and the synchronous call removes
        # the ThreadPoolExecutor entirely (that was the source of the
        # thread-pool occupation queueing pathology under timeout).
        try:
            q_raw, q_ms, _qi, _qo, q_err = _call_openai_compat(
                self._fw_client, QWEN_MODEL, frames, PROMPT_SPATIAL)
        except Exception as e:  # noqa: BLE001
            q_raw, q_ms, q_err = "", int(
                (time.time() - t0) * 1000), f"qwen:{e}"

        wall = (time.time() - t0) * 1000
        self._last_ms = round(wall)
        self._last_q_ms = q_ms
        self._last_g_ms = 0

        q_parsed = _parse_spatial_json(q_raw) if q_raw else None
        q_vals, q_conf = (spatial_to_cricket(
            q_parsed,
            known_batsman_handed=known_batsman_handed,
            known_bowling_arm=known_bowling_arm)
            if q_parsed else ({}, {}))

        if not q_parsed:
            self._failures += 1
            log.warning(
                f"[L2] Qwen unparseable after {wall:.0f}ms "
                f"(err={q_err})")
            return _unknown_legacy(runs, "qwen_unparseable", {
                "_qwen_raw": (q_raw or "")[:300],
                "_qwen_err": q_err,
                "_l2_ms": round(wall),
            })

        routed, routed_conf, diag = _route_qwen_only(
            q_vals, q_conf, self._conf_floor)

        # Scoreboard already confirmed a delivery — override abstention
        # on is_valid_delivery so downstream doesn't flag untrackable.
        if not _bool_val(routed.get("is_valid_delivery"), True):
            routed["is_valid_delivery"] = True

        result = _routed_to_legacy(routed, routed_conf, runs, wall)
        result = _apply_suppression(result)

        # Commit metrics (diag-level; "agree" no longer meaningful
        # without a second model but kept absent for schema clarity).
        commits = sum(1 for d in diag.values() if d["committed"])
        result["_layer2_routed"] = routed
        result["_layer2_conf"] = routed_conf
        result["_layer2_diag"] = diag
        result["_layer2_committed"] = commits
        result["_qwen_ms"] = q_ms
        # Back-compat alias: legacy consumers read `_gemini_ms` as the
        # classifier wall time.  Post Fix-C that IS the Qwen ms.
        result["_gemini_ms"] = q_ms
        result["_l2_ms"] = round(wall)

        log.info(
            f"[L2] {wall:.0f}ms (qwen={q_ms}ms) "
            f"committed={commits}/{len(_ROUTABLE_FIELDS)} "
            f"hand={routed.get('batsman_handed')} "
            f"arm={routed.get('bowling_arm')} "
            f"len={routed.get('length')} "
            f"line={routed.get('line')} "
            f"bounce={routed.get('bounce')} "
            f"shot={routed.get('shot_type')}/{routed.get('shot_side')} "
            f"[suppressed: {','.join(SUPPRESSED_LEGACY_FIELDS)}]")

        # Densification-experiment telemetry.  One structured line per
        # L2 call that exposes per-field value + raw confidence + commit
        # bit for the "hard" fields where densification is expected to
        # matter (length, line, bounce, bowling_type).  Aggregating these
        # across a run gives us commit-rate and confidence-distribution
        # deltas vs the N=16 bakeoff baseline without needing ground
        # truth at runtime.
        #
        # Grep pattern: `[L2-DENSIFY]`
        def _fld(name: str) -> str:
            val = q_vals.get(name)
            conf = q_conf.get(name)
            committed = bool(diag.get(name, {}).get("committed"))
            val_s = val if val is not None else "null"
            conf_s = f"{conf:.2f}" if isinstance(conf, (int, float)) else "na"
            return f"{name}={val_s}|c={conf_s}|ok={int(committed)}"

        log.info(
            "[L2-DENSIFY] "
            f"n_burst={N_BURST} wall={wall:.0f}ms "
            + " ".join(_fld(f) for f in
                       ("length", "line", "bounce", "bowling_type")))

        if save_dir:
            try:
                d = Path(save_dir)
                d.mkdir(parents=True, exist_ok=True)
                (d / "layer2.json").write_text(json.dumps({
                    "qwen": {
                        "model": QWEN_MODEL,
                        "ms": q_ms,
                        "err": q_err,
                        "raw": (q_raw or "")[:4000],
                        "parsed": q_parsed,
                        "cricket_values": q_vals,
                        "cricket_confidence": q_conf,
                    },
                    "conf_floor":   self._conf_floor,
                    "routed":       routed,
                    "routed_conf":  routed_conf,
                    "per_field":    diag,
                    "committed":    commits,
                    "suppressed":   list(SUPPRESSED_LEGACY_FIELDS),
                    "wall_ms":      round(wall),
                    "_note": (
                        "Gemini retired in Fix C (2026-04-22); see "
                        "layer2_classifier.py docstring."),
                }, indent=2))
            except Exception as e:  # noqa: BLE001
                log.warning(f"[L2] could not write layer2.json: {e}")

        return result

    def classify_frames(
        self,
        frames: list[tuple[float, np.ndarray]],
        runs: int = 0,
        save_dir: str | None = None,
        fps: float | None = None,
        known_batsman_handed: str = "unknown",
        known_bowling_arm: str = "unknown",
    ) -> dict:
        if not frames:
            return _unknown_legacy(runs, "no_frames", {})
        mp4_path = None
        try:
            target_path = None
            if save_dir:
                d = Path(save_dir)
                d.mkdir(parents=True, exist_ok=True)
                target_path = str(d / "delivery_window.mp4")
            mp4_path = compile_frames_to_mp4(
                frames, out_path=target_path, fps=fps)
            return self.classify_video(
                mp4_path, runs=runs, save_dir=save_dir,
                known_batsman_handed=known_batsman_handed,
                known_bowling_arm=known_bowling_arm)
        finally:
            # Only delete temp compile outputs; never the persisted
            # delivery_window.mp4 under save_dir.
            if (mp4_path and not save_dir
                    and os.path.exists(mp4_path)):
                try:
                    os.remove(mp4_path)
                except Exception:
                    pass

    def shutdown(self):
        # No-op post Fix-C (no ThreadPoolExecutor to drain).  Retained
        # so downstream teardown code that calls .shutdown() keeps
        # working without edits.
        return


def _unknown_legacy(runs: int, reason: str, extras: dict) -> dict:
    """Shaped like _to_legacy_schema's unknown path so downstream
    never has to branch on _method.  Applies the same suppression so
    the null-ification of Gemini-dependent fields is consistent
    between happy-path and abstention-path output."""
    base = {
        "length":         "unknown",
        "line":           "unknown",
        "bowling_angle":  "unknown",
        "bounce":         "normal",
        "shot_type":      _shot_type_from_runs(runs),
        "shot_elevation": "unknown",
        "shot_action":    "unknown",
        "shot_intent":    "unknown",
        "shot_direction": {
            "side": "unknown", "zone": "unknown",
            "confidence": "low"},
        "swing_or_seam":  "not_visible",
        "ball_speed_visible": False,
        "ball_speed_kph_vlm": None,
        "runs":           runs,
        "detections":     0,
        "detection_rate": 0.0,
        "commentary_line": "no classification available",

        "batsman_handed":  "unknown",
        "bowling_arm":     "unknown",
        "bowling_type":    "unknown",
        "contact_quality": "unknown",
        "narrative":       "",

        "_method":            "layer2",
        "_gemini_model":      GEM_MODEL,
        "_qwen_model":        QWEN_MODEL,
        "_gemini_ms":         0,
        "_gemini_confidence": "low",
        "_is_valid_delivery": True,
        "_skip_reason":       reason,
        "_untrackable":       True,
    }
    base.update(extras)
    return _apply_suppression(base)
