"""20b LLM rescue: scan V_post-rich gaps for missed deliveries.

After P2 high-signal rescue + phantom_rescue, large gaps with multiple
V_post hits often hide deliveries the rule pipeline couldn't recover.
For each qualifying gap, send Scout prose to gpt-oss-20b on Groq; on a
high/medium-confidence delivery_found=true response, promote the V_post
frame nearest the model's approx_t to a single-frame rescued cluster.

Env-gated by the call site (delivery_clip_pipeline.py):
  LLM_RESCUE_ENABLED=1     opt-in
  SCOUT_REPLAY_LOG=<path>  if set, replay mode — call site skips
  GROQ_API_KEY=<key>       required when enabled

Cost: ~$0.001 per gap; capped at 10 LLM calls per innings.
Gap criteria: duration > 25s and >=3 V_post frames inside.
"""

from __future__ import annotations

import json
import os
import re
from typing import Callable

from delivery_classifier import FrameInfo


RESCUE_PROMPT = """\
Below are per-frame descriptions of a cricket broadcast over a window.
Identify whether a cricket DELIVERY (bowler releases ball + batter
plays) occurred in this window. If yes, output the approximate
timestamp range (in seconds from window start). If no delivery, say
'NO_DELIVERY_FOUND'.

A 'delivery' is the actual ball release moment, NOT the runup or
post-action. Look for cues like 'mid-action', 'just bowled', 'mid-swing',
'follow-through', 'ball in flight', 'fielder running for the ball'.

Output JSON: {"delivery_found": true|false, "approx_t": <seconds>,
"confidence": "high|medium|low", "reason": "<≤30 words>"}

Window prose:
"""

MIN_GAP_S = 25.0
MIN_V_POST = 3
MAX_CALLS_PER_INNINGS = 10
MODEL = "openai/gpt-oss-20b"


def _extract_json(raw: str) -> dict | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def _parse_rescue(raw: str) -> dict:
    obj = _extract_json(raw)
    if obj is None:
        return {"delivery_found": False, "approx_t": None,
                "confidence": "low", "reason": (raw or "")[:120]}
    return {
        "delivery_found": bool(obj.get("delivery_found", False)),
        "approx_t": obj.get("approx_t"),
        "confidence": str(obj.get("confidence", "")).lower(),
        "reason": str(obj.get("reason", ""))[:200],
    }


def _build_prose(frames: list[FrameInfo]) -> str:
    return "\n".join(f"[t={f.t:.1f}] {f.text.replace(chr(10), ' ').strip()}"
                     for f in frames)


def _approx_t_to_abs(approx_t, gap_lo: float, gap_hi: float) -> float | None:
    """Model is asked for 'seconds from window start' but in practice
    often echoes the absolute [t=...] timestamps from the prose. Accept
    both: if approx_t falls inside the gap window absolute-wise, treat
    it as absolute; otherwise treat as offset from gap_lo."""
    if approx_t is None:
        return None
    try:
        v = float(approx_t)
    except (TypeError, ValueError):
        return None
    if gap_lo <= v <= gap_hi:
        return v
    abs_t = gap_lo + v
    if gap_lo <= abs_t <= gap_hi:
        return abs_t
    return None


def _default_llm_caller(prose_body: str) -> dict:
    """Sync Groq call. Imported lazily so tests don't need the SDK
    installed and so module import is cheap when the gate is off."""
    from groq import Groq

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0.0,
        max_tokens=4096,
        reasoning_effort="low",
        messages=[{"role": "user",
                   "content": RESCUE_PROMPT + prose_body
                   + "\n\nReply with ONLY the JSON object, no extra "
                     "text."}],
        timeout=90.0,
    )
    return _parse_rescue(resp.choices[0].message.content)


def llm_rescue_v_post_gaps(
        clusters: list[dict],
        all_frames: list[FrameInfo],
        *,
        min_gap_s: float = MIN_GAP_S,
        min_v_post: int = MIN_V_POST,
        max_calls: int = MAX_CALLS_PER_INNINGS,
        llm_caller: Callable[[str], dict] | None = None,
) -> list[dict]:
    """Scan adjacent kept clusters for V_post-rich gaps and ask the LLM
    whether a delivery happened in each. Promote the nearest V_post
    frame to a single-frame rescued cluster on high/medium confidence.

    Returns the cluster list with newly rescued clusters merged in,
    sorted by start_t. The input `clusters` list is not mutated.
    """
    if not clusters or len(clusters) < 2 or not all_frames:
        return list(clusters)

    caller = llm_caller or _default_llm_caller
    sorted_clusters = sorted(clusters, key=lambda c: c["start_t"])

    # Pre-collect frame timestamps already inside any kept cluster so
    # rescued frames don't duplicate cluster members.
    in_cluster_t: set[float] = set()
    for c in sorted_clusters:
        for f in c["frames"]:
            in_cluster_t.add(f.t)

    rescued: list[dict] = []
    calls_made = 0

    for i in range(len(sorted_clusters) - 1):
        if calls_made >= max_calls:
            break
        gap_lo = sorted_clusters[i]["end_t"]
        gap_hi = sorted_clusters[i + 1]["start_t"]
        if gap_hi - gap_lo <= min_gap_s:
            continue

        gap_frames = [f for f in all_frames
                      if gap_lo < f.t < gap_hi
                      and f.t not in in_cluster_t]
        if not gap_frames:
            continue

        v_post_frames = [f for f in gap_frames
                         if getattr(f.signals, "V_post", False)]
        if len(v_post_frames) < min_v_post:
            continue

        # Skip gap if V_post frames sit too close to an already-rescued
        # cluster anchor we just appended (dedup against this pass).
        if any(abs(v.t - r["start_t"]) < 8.0
               for v in v_post_frames for r in rescued):
            continue

        prose = _build_prose(gap_frames)
        try:
            result = caller(prose)
        except Exception as exc:  # noqa: BLE001
            result = {"delivery_found": False, "approx_t": None,
                      "confidence": "low", "reason": f"caller error: {exc}"}
        calls_made += 1

        if not result.get("delivery_found"):
            continue
        if result.get("confidence") not in ("high", "medium"):
            continue

        abs_t = _approx_t_to_abs(result.get("approx_t"), gap_lo, gap_hi)
        if abs_t is None:
            continue

        nearest = min(v_post_frames, key=lambda f: abs(f.t - abs_t))
        rescued.append({
            "start_idx": -1,
            "end_idx": -1,
            "start_t": nearest.t,
            "end_t": nearest.t,
            "frames": [nearest],
            "rescued_by": "llm_v_post_gap",
            "llm_confidence": result.get("confidence"),
            "llm_approx_t": result.get("approx_t"),
            "llm_reason": result.get("reason", ""),
        })

    if not rescued:
        return list(sorted_clusters)
    out = list(sorted_clusters) + rescued
    out.sort(key=lambda c: c["start_t"])
    return out
