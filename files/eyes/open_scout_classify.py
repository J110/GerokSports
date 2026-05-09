"""Production copy of the open-prose Scout classifier (rule v2).

Source of truth: ``files/scripts/scout_validation_research/classify_descriptions.py``
(``classify_v2_final``, ``classify_full``, ``is_ad_pattern``,
``is_replay_pattern``, ``is_umpire_pattern`` and supporting primitives,
frozen at the v2 ruleset that scored P=0.772 / R=0.987 / F1=0.867 on
the 247-frame validation corpus — see
``files/docs/investigations/scout_per_frame_classification_validation.md``
§§ 11.4-11.7).

Why a copy lives in ``files/eyes/``:
  Production code must not import from ``files/scripts/`` (that
  directory is for one-off research scripts; nothing under it is on
  the install path of the live pipeline).  When the validation
  ruleset advances to a v3, the canonical script and this module
  should be updated together — see §11.6 of the design memo.

API:
  classify_full(desc) -> str
      Returns one of {"action", "replay", "ad", "umpire", "other"}.
"""
from __future__ import annotations

import re
from typing import Callable

CLOSEUP_TERMS_V2 = (
    "close-up", "closeup", "medium shot", "medium close", "close up",
    "medium-close", "full-body shot", "full body shot", "full shot of",
)

CEREMONY_NEG = (
    "cheerleader",
    "cheerleaders",
    "pom-pom",
    "pom poms",
    "pompoms",
    "air asia",
    "dancers on the field",
    "dancers standing",
)


def neg_ad_semantic(d: str) -> bool:
    return (
        "does not depict a professional cricket" in d
        or ("does not depict" in d and "cricket match" in d)
        or ("pinky" in d and "home loan" in d)
    )


def neg_empty_wide_stadium(d: str) -> bool:
    crowd = (
        "stands filled" in d
        or "crowd in the stands" in d
        or "large crowd in the stands" in d
        or "crowded stadium" in d
    )
    idle = (
        "no active play" in d
        or "no intense action" in d
        or "not actively engaged" in d
        or "mostly stationary" in d
        or ("standing still" in d and "few individuals" in d)
        or ("appear to be standing still" in d and "few" in d)
    )
    if not crowd or not idle:
        return False
    energetic = (
        "mid-stride" in d
        or "mid stride" in d
        or "mid-swing" in d
        or "mid swing" in d
        or "mid-throw" in d
        or "just bowled" in d
        or "having just bowled" in d
        or "airborne" in d
    )
    return not energetic


def neg_solitary_wide_batter_prep(d: str) -> bool:
    if "wide field view of a cricket player standing" not in d:
        if not (
            "wide field view of a cricket player" in d
            and "standing still" in d
        ):
            return False
    elif "standing still" not in d and "stands still" not in d:
        return False

    if (
        ("holding a bat" in d or "holding a cricket bat" in d)
        and any(
            x in d for x in (
                "wickets", "wicket", "stumps",
                "near the wicket", "near the wickets",
            ))):
        return False

    multitext = (
        "bowler" in d or "umpire" in d
        or "wicketkeeper" in d or "fielder" in d
    )
    if multitext and (
            "several players" in d or "another player" in d
            or "two players" in d):
        return False
    if multitext:
        return False

    energetic = (
        "mid-" in d
        or re.search(r"\b(bowls?|bowling|bowled)\b", d) is not None
        or re.search(r"\bswings?\b", d) is not None
    )
    return not energetic


def pos_wide_only(d: str) -> bool:
    return ("wide field view" in d
            or "frame shows a wide field view" in d)


def pos_full_body_pitch(d: str) -> bool:
    if not any(
            k in d for k in (
                "full shot of", "full-body shot", "full body shot")):
        return False
    markers = (
        "bowler", "stumps", "wickets", "wicket", "crease", "pitch",
        "near the wickets", "preparing to bowl",
    )
    if any(m in d for m in markers):
        return True
    if "glove" in d and "ball" in d:
        return True
    return False


def pos_alt_delivery_language(d: str) -> bool:
    kinetic = (
        "mid-swing", "mid swing", "mid-throw", "mid throw",
        "mid-stride", "mid stride", "mid-action", "mid action",
        "ball airborne", "the ball airborne",
        "having just bowled", "just bowled", "just thrown the ball",
        "appears to have just thrown",
        "captured in mid-throw", "in mid-throw", "in mid-action",
        "attempting to catch", "fallen while attempting to catch",
        "fielding stance", "crouching on a green field",
        "wicket-keeper", "wicketkeeper", "kneeling on one knee",
        "two cricket players on a green field",
        "throwing or catching a ball",
    )
    if any(a in d for a in kinetic):
        return True
    if "preparing to hit the ball" in d:
        return True
    if "preparing to hit a ball" in d:
        return True
    if "preparing for the next delivery" in d and "pitch" in d:
        return True
    if "has just received a delivery" in d:
        return True
    if "in the act of bowling" in d or "in the act of hitting" in d:
        return True
    return False


def pos_pitch_standing_batter(d: str) -> bool:
    if ("cricket player standing on the pitch" not in d
            and "standing on the pitch" not in d):
        return False
    return any(
        k in d for k in ("preparing", "delivery", "bowler", "wicket"))


def is_tight_framing(d: str) -> bool:
    return any(t in d for t in CLOSEUP_TERMS_V2) or "medium shot" in d


def pos_batter_wideish_prep(d: str) -> bool:
    if is_tight_framing(d):
        return False
    if "batter" not in d and "batsman" not in d:
        return False
    if "preparing to hit" not in d:
        return False
    return "green field" in d or "pitch" in d


def has_strong_action_signal(d: str) -> bool:
    if is_tight_framing(d):
        return pos_full_body_pitch(d) or pos_alt_delivery_language(d)
    return (
        pos_full_body_pitch(d)
        or pos_alt_delivery_language(d)
        or pos_pitch_standing_batter(d)
        or pos_batter_wideish_prep(d)
    )


def classify_v2_final(desc: str) -> str:
    """Binary action-vs-other gate (validation memo §11.4)."""
    d = (desc or "").lower()

    if neg_ad_semantic(d):
        return "other"
    if any(c in d for c in CEREMONY_NEG):
        return "other"
    if neg_empty_wide_stadium(d):
        return "other"
    if neg_solitary_wide_batter_prep(d):
        return "other"

    strong = has_strong_action_signal(d)
    tight = is_tight_framing(d)
    if tight and not strong:
        return "other"

    wide = pos_wide_only(d)
    if wide and not neg_empty_wide_stadium(d) and not neg_solitary_wide_batter_prep(d):
        return "action"

    if strong:
        return "action"

    return "other"


REPLAY_CONSERVATIVE = (
    "replay", "slow motion", "slow-motion", "slo-mo", "slo mo",
    "freeze-frame", "freeze frame",
    "telestrator overlay", "telestrator",
    "split-screen replay",
    "slow-motion overlay", "slow-motion footage",
    "slow-motion replay",
    "replay graphic",
)
REPLAY_UPPER = ("REPLAY", "SLOW-MO", "SUPER SLO-MO")

# v2 prompt structured tag — emitted on the first line of Scout's
# response by ``OPEN_PROMPT_V2``.  Matched before the legacy substring
# pass so we can be both precise (no false positives from negated
# prose) and able to detect untagged replay tokens that slip through
# v1 prose.  See ``files/docs/investigations/scout_path_a_iteration.md``.
REPLAY_TAGS_V2 = (
    "[BROADCAST: REPLAY]",
    "[BROADCAST: SLO-MO]",
    "[BROADCAST: TELESTRATOR]",
    "[BROADCAST: SPLIT-SCREEN]",
)
LIVE_TAG_V2 = "[BROADCAST: LIVE]"

# Substrings that indicate the prose is *negating* replay rather than
# asserting it (e.g. "there are no visible indicators of replay,
# slow motion, or other non-live features").  Used to gate the
# legacy substring matcher only — the v2 tag pass above ignores them
# because the tag itself is a positive assertion.
REPLAY_NEG_SUBSTRINGS = (
    "no indication of replay",
    "no replay",
    "without replay",
    "no slow-motion",
    "no slow motion",
    "not a replay",
    "no replay or slow-motion",
    "no visible indicators of replay",
    "no visible indicators of slow",
    "no indicators of replay",
    "no signs of replay",
    "absent of replay",
)


def is_replay_pattern(desc: str) -> bool:
    u = desc or ""
    if any(t in u for t in REPLAY_TAGS_V2):
        return True
    if LIVE_TAG_V2 in u:
        return False

    d = u.lower()
    has_negation = any(n in d for n in REPLAY_NEG_SUBSTRINGS)

    if any(s in u for s in REPLAY_UPPER) and not has_negation:
        return True
    if any(s in d for s in REPLAY_CONSERVATIVE) and not has_negation:
        return True
    return False


def is_ad_pattern(desc: str) -> bool:
    d = (desc or "").lower()
    if neg_ad_semantic(d):
        return True
    if "pinky" in d and "home loan" in d:
        return True
    return False


def is_umpire_pattern(desc: str) -> bool:
    d = (desc or "").lower()
    if "umpire" not in d:
        return False
    return any(
        k in d for k in (
            "signal", "signaling", "signalling",
            "raised", "outstretched", "arms outstretched",
            "gesture",
        ))


def classify_full(desc: str,
                  *,
                  binary_fn: Callable[[str], str] = classify_v2_final,
                  ) -> str:
    """Multiclass routing per validation memo §11.6.

    Returns one of {"action", "replay", "ad", "umpire", "other"}.
    Order matters — ad / replay / umpire patterns short-circuit
    before the binary gate so kinetic phrasing inside a replay
    caption ("the bowler bowls in slow-motion") does not leak into
    the ``action`` channel.
    """
    d = desc or ""
    if is_ad_pattern(d):
        return "ad"
    if is_replay_pattern(d):
        return "replay"
    if is_umpire_pattern(d):
        return "umpire"
    if binary_fn(d) == "action":
        return "action"
    return "other"
