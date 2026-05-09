"""Single source of truth: Vision/Scout structured fields → naive 5-corpus scout label.

Human rubric GT uses ``{action,replay,ad,other,umpire,unknown}``; Scout-derived
labels omit ``umpire`` (never emitted by Vision) — use ``scout_to_label_naive``.
"""
from __future__ import annotations

LIVE_PHASES = frozenset({"runup", "release", "flight", "shot", "post_shot"})


def scout_to_label_naive(rec: dict) -> str:
    """Recommended Phase-B mapping from production ``Vision.describe`` sidecars.

    Returns one of ``action``, ``replay``, ``ad``, ``other``.
    """

    ft = (rec.get("frame_type") or "").upper()

    cam = rec.get("last_camera_view")
    if isinstance(cam, str):
        cam = cam.strip().lower() or None
    phase = rec.get("last_frame_phase")
    if isinstance(phase, str):
        phase = phase.strip().lower() or None

    if ft == "ADVERTISEMENT" or cam == "ad":
        return "ad"

    if ft == "GRAPHIC":
        return "other"

    if ft == "CLOSEUP":
        return "other"

    if cam == "closeup":
        return "other"

    if cam == "replay" or phase == "replay":
        return "replay"

    if cam == "bowlers_end" and phase in LIVE_PHASES:
        return "action"

    if cam == "side_on":
        return "action"

    # Everything else → other (including UNKNOWN, graphic cam without GRAPHIC ft,
    # bowlers_end + between_play / fielder_reaction, ``other`` camera_view, gaps).
    return "other"
