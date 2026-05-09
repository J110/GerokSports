"""ChunkerV3 — rule-based, time-based per-frame label + delivery-window.

Spec: ``files/docs/algorithms/chunker_v3.md``.

Ports keyword constants verbatim from
``/Users/anmolmohan/Projects/SportsComm/v3_1_simulation.py``.  The
algorithm itself is the rule-based v3 variant (NOT the v3.1 confidence-
scored variant) plus three fixes:

  * Fix #1 — bidirectional REPLAY propagation, time-bounded (4 s) and
    consecutive-frame-bounded (3 live anchors).
  * Fix #2 — celebration → REPLAY only if crowd is the subject; a
    player-only raised arm stays in the delivery window.
  * Fix #3 — same-label chunks within 10 s merge unless the gap
    contains AD / REPLAY / DRS / graphic-block.

All thresholds are seconds, NOT frame counts.  Decoupled OpenScout
cadence (1.0–1.3 s median) makes frame-count thresholds unstable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

# ── Keyword constants ────────────────────────────────────────────────
# Verbatim from /Users/anmolmohan/Projects/SportsComm/v3_1_simulation.py
# (constants only; algorithm logic is rule-based per chunker_v3.md).

ACTION_VERBS = (
    "running in", "running toward", "running with", "sprinting",
    "mid-swing", "mid-air", "mid-stride", "mid-motion", "just released",
    "just threw", "just hit", "diving", "fielding", "playing shot",
    "preparing shot", "preparing to play", "preparing to hit",
    "catching", "ball in flight", "ball traveling", "ball mid-air",
    "throwing", "chasing ball", "chasing the ball", "leaping", "lunging",
)

DRS_KEYWORDS = (
    "ball-tracking", "ball tracking", "trajectory", "hawkeye", "hawk-eye",
    "ultra-edge", "snicko", "decision review", "drs", "umpire's call",
)

BRAND_KEYWORDS = (
    "jiohotstar", "hotstar", "self-serve", "star sports", "tata ipl",
    "vivo", "dream11", "jio", "sponsor", "official partner",
)

LIVE_CONTEXT_TERMS = (
    "batter", "batsman", "batsmen", "stumps", "wicket", "crease",
    "at the crease", "stumps visible",
)

CELEBRATION_TERMS_PLAYER = (
    "raising bat", "arm raised", "arms outstretched", "high-fiv",
    "celebration", "celebrating", "raised in celebration",
)

CELEBRATION_TERMS_CROWD = (
    "crowd cheering", "fans celebrating", "crowd celebrating",
    "fans cheering", "crowd erupting", "spectators cheering",
)

CROWD_AS_SUBJECT_TERMS = (
    "crowd visible", "spectators visible", "fans visible",
    "crowd in the foreground", "spectators in the foreground",
    "crowd cheering", "fans cheering",
)

SLOWMO_TERMS = (
    "slow motion", "slow-mo", "slo-mo", "slowed", "in slow",
    "slowed down", "moments earlier", "moments ago", "previous",
)

NO_PLAYERS_TERMS = (
    "no people visible", "no people are", "no players visible",
    "no players are", "no individuals", "no action visible",
    "title card", "static graphic", "static image",
)

EXPLICIT_UMPIRE = (
    "the umpire", "umpire is", "umpire raised", "umpire's arm",
    "umpire signal", "umpire raises", "umpire signals",
)
HYPOTHETICAL_UMPIRE = (
    "or the umpire", "possibly the umpire", "to the umpire", "or umpire",
    "possibly umpire", "to teammates or the umpire",
    "to a teammate or the umpire",
)
SIGNALING_VERBS = (
    "raised", "outstretched", "arm extended", "signaling", "signalling",
    "indicating", "gesture",
)

CAREER_STATS_REGEX = re.compile(
    r"\b[A-Z][A-Z\.\-' ]{3,30}\s+\d{1,3}\*?\s*\(?\d{1,3}\)?"
    r"[\s\"\.,;\-]*?MATCH\s*\d+\s+v\s+[A-Z]{2,5}\b"
)
MATCH_OVERLAY_REGEX = re.compile(
    r"MATCH\s*\d+\s+v\s+[A-Z]{2,5}\b", re.IGNORECASE)
DISMISSAL_REGEX = re.compile(
    r"\b[A-Z][a-z]+\s+c\s+[A-Z][a-z]+\s+b\s+[A-Z][a-z]+\s+\d+\(\d+\)"
)

DELIVERY_PHASES = frozenset({
    "release", "flight", "shot", "post_shot", "runup",
})
LIVE_CAMS = frozenset({"bowlers_end", "side_on"})
REPLAY_TAG_VALUES = frozenset({"REPLAY", "SLO-MO", "TELESTRATOR",
                               "SPLIT-SCREEN"})

# ── v3.1 replay-filter constants ─────────────────────────────────────
# Ported from files/scripts/broadcast_mode_tuning/validate_replay_rules.py.
# v3.1 layers cluster-aware text-only filters on top of v3 production-tag
# rules to suppress pre-delivery / replay / close-up false positives that
# v3's prod_cam-driven rules can't see.
STRONG_DELIVERY_VERBS = (
    "mid-swing", "mid-air", "mid-action",
    "just released", "just bowled", "just delivered",
    "just hit", "just played",
    "about to release", "about to bowl",
    "follow-through", "follow through",
    "arm raised",
    "playing a shot", "played a shot",
    "ball in flight", "ball traveling", "ball in the air",
    "diving to catch", "diving to field",
    "diving to take", "leaping to catch",
)

# Weaker action signals — pick up isolated frames whose action verb
# isn't in STRONG_DELIVERY_VERBS but still suggests live play.
WEAK_ACTION_VERBS = (
    "running", "throwing", "fielding", "diving",
    "raising arm",
    "swinging", "swung", "hit the ball", "hits the ball",
    "preparing to play", "preparing to hit",
    "in motion", "mid-stride",
)

# Explicit non-delivery hints — stillness / between-ball language used
# by the confidence scorer to bump NON_DELIVERY votes for filler frames.
NON_DELIVERY_HINTS = (
    "between deliveries", "preparing", "standing still", "walking",
)

# Cricket-pitch context — when present alongside a STRONG verb, lets a
# closer framing still count as delivery (recovers d004-class
# truncated deliveries where Scout describes "stumps" / "crease"
# without the literal "wide field" phrase).
PITCH_CONTEXT_TERMS = (
    "wicket", "wickets", "crease", "stumps", "pitch",
)

# Crowd-as-primary-subject (replay indicator).  Real wide-field
# broadcast deliveries virtually never describe the crowd as part of
# the scene; replays (boundary / wicket replays from low or
# behind-batter angles) frequently do.  Used by the cluster-level
# ``crowd_sandwich`` reject rule in
# :class:`eyes.continuous_chunker.ContinuousChunker`; a separate
# evidence key from ``has_crowd_subj`` so that broader v3 REPLAY
# behaviour is unchanged.
CROWD_PROMINENT_TERMS = (
    "crowd of spectators",
    "large crowd in the background",
    "crowd in the background",
    "crowd in the foreground",
    "stadium full of spectators",
    "spectators watch",
    "spectators are seated",
    "crowd of fans",
)

WIDE_FIELD_TERMS = (
    "wide field view", "wide view", "wide shot",
    "cricket pitch with players positioned",
    "cricket pitch with several players",
    "cricket pitch with players",
    "wide field of a cricket",
)

ACTOR_ROLES = (
    "bowler", "batter", "batsmen", "fielder", "fielders",
    "wicketkeeper", "wicket-keeper", "wicket keeper",
    "umpire",
)

REPLAY_OVERLAY_BARE_TERMS = (
    "wicket ball speed", "wicket ball ",
    "instant replay", "slow motion", "slo-mo",
    "stats breakdown",
)

POST_ACTION_PHRASES = (
    "post-action moment", "post action moment",
    "action has concluded", "action concluded",
    "moment after the action",
    "appears to be a break",
    "darkened stadium", "darkened", "black screen",
    "blurry view", "minimal graphical overlays",
)

CLOSE_UP_TERMS = (
    "close-up", "close up", "close shot",
    "medium shot", "medium close-up", "medium close up",
    "single cricket player", "single player",
    "close-up of a", "close-up shot",
    "waist up", "from the waist", "lower body",
    "legs and feet", "from behind",
)

SINGLE_PLAYER_TERMS = (
    "close-up of a single", "single cricket player",
    "close-up shot of a single", "medium shot of a single",
    "medium shot of a cricket player",
)

# Labels in priority order (highest first).
LABEL_AD = "AD"
LABEL_DRS = "DRS"
LABEL_REPLAY = "REPLAY"
LABEL_UMPIRE = "UMPIRE_SIGNAL"
LABEL_DELIVERY = "DELIVERY_ACTION"
LABEL_REPLAY_LEAN = "REPLAY_LEAN"
LABEL_NON_DELIVERY = "NON_DELIVERY_ACTION"
LABELS = (
    LABEL_AD, LABEL_DRS, LABEL_REPLAY, LABEL_UMPIRE,
    LABEL_DELIVERY, LABEL_REPLAY_LEAN, LABEL_NON_DELIVERY,
)
HOSTILE_LABELS = frozenset({LABEL_AD, LABEL_REPLAY, LABEL_DRS})

# Thresholds (seconds — see chunker_v3.md §B).
ANCHOR_CONFIRM_WINDOW_S = 4.0
ANCHOR_CONFIRM_MIN_FRAMES = 2
ANCHOR_BRIDGE_WINDOW_S = 2.0
SOLO_PHASE_NEIGHBOR_S = 1.5
SOLO_PHASE_SUPPORT_S = 2.0
REPLAY_PROP_LIVE_ANCHOR_S = 4.0
REPLAY_PROP_LIVE_ANCHOR_RUN = 3
CLUSTER_MERGE_GAP_S = 10.0
LOOKBACK_S = 4.0
FORWARD_S = 4.0
UMPIRE_APPEND_S = 3.0
DRS_APPEND_S = 5.0
GRAPHIC_BLOCK_MIN_S = 2.0
EARLY_GRAPHIC_AD_HORIZON_S = 3.0


# ── Frame schema ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class FrameInput:
    """Per-frame Scout payload consumed by the chunker."""

    ts: float
    prod_cam: str
    prod_phase: str
    v2_broadcast_tag: str
    v2_class: str
    open_desc: str

    @classmethod
    def from_dict(cls, d: dict) -> "FrameInput":
        return cls(
            ts=float(d.get("ts", 0.0)),
            prod_cam=str(d.get("prod_cam", "") or ""),
            prod_phase=str(d.get("prod_phase", "") or ""),
            v2_broadcast_tag=str(d.get("v2_broadcast_tag", "") or ""),
            v2_class=str(d.get("v2_class", "") or ""),
            open_desc=str(d.get("open_desc", "") or ""),
        )


@dataclass
class LabeledFrame:
    """Per-frame label plus the predicate evidence that produced it."""

    ts: float
    label: str
    inputs: FrameInput
    evidence: dict = field(default_factory=dict)


@dataclass
class Chunk:
    """Contiguous run of same-label frames."""

    label: str
    start_ts: float
    end_ts: float
    frame_indices: list[int]
    confirmed: bool = False

    @property
    def duration_s(self) -> float:
        return max(0.0, self.end_ts - self.start_ts)


# ── Predicate computation ────────────────────────────────────────────


def _has_any(terms: Iterable[str], text: str) -> bool:
    return any(t in text for t in terms)


def score_frame(f: FrameInput) -> dict:
    """Return per-rule predicate booleans for one frame.

    Pure: same input → same output.  No state.
    """
    desc = f.open_desc.lower()
    raw = f.open_desc

    has_career = bool(CAREER_STATS_REGEX.search(raw)) or bool(
        MATCH_OVERLAY_REGEX.search(raw))
    has_dismissal = bool(DISMISSAL_REGEX.search(raw))
    has_action_verb = _has_any(ACTION_VERBS, desc)
    has_drs = _has_any(DRS_KEYWORDS, desc)
    has_brand = _has_any(BRAND_KEYWORDS, desc)
    has_live_ctx = _has_any(LIVE_CONTEXT_TERMS, desc)
    has_celeb_player = _has_any(CELEBRATION_TERMS_PLAYER, desc)
    has_celeb_crowd = _has_any(CELEBRATION_TERMS_CROWD, desc)
    has_crowd_subj = _has_any(CROWD_AS_SUBJECT_TERMS, desc)
    has_slowmo = _has_any(SLOWMO_TERMS, desc)
    has_no_players = _has_any(NO_PLAYERS_TERMS, desc)
    has_explicit_umpire = _has_any(EXPLICIT_UMPIRE, desc)
    has_hypothetical_umpire = _has_any(HYPOTHETICAL_UMPIRE, desc)
    has_signaling_verb = _has_any(SIGNALING_VERBS, desc)

    is_replay_tag = f.v2_broadcast_tag.upper() in REPLAY_TAG_VALUES
    is_delivery_phase = f.prod_phase in DELIVERY_PHASES

    # v3.1 text-only predicates (pre-delivery / replay / close-up filter)
    has_strong_delivery_verb = _has_any(STRONG_DELIVERY_VERBS, desc)
    roles_seen: set[str] = set()
    for r in ACTOR_ROLES:
        if r in desc:
            roles_seen.add(r.split()[0])
    has_multi_actor = len(roles_seen) >= 2
    # Wide-field framing: literal phrase OR multi-actor mention.
    has_wide_field = _has_any(WIDE_FIELD_TERMS, desc) or has_multi_actor
    has_pitch_context = _has_any(PITCH_CONTEXT_TERMS, desc)
    has_crowd_prominent = _has_any(CROWD_PROMINENT_TERMS, desc)
    has_replay_overlay_bare = _has_any(REPLAY_OVERLAY_BARE_TERMS, desc)
    has_analysis_graphic = (
        "analysis" in desc
        and ("graphic" in desc or "overlay" in desc or "letters" in desc))
    has_replay_overlay = has_replay_overlay_bare or has_analysis_graphic
    has_post_action = _has_any(POST_ACTION_PHRASES, desc)
    has_close_up = _has_any(CLOSE_UP_TERMS, desc)
    has_single_player_term = _has_any(SINGLE_PLAYER_TERMS, desc)
    if has_multi_actor:
        is_single_player_focus = False
    elif has_single_player_term:
        is_single_player_focus = True
    else:
        is_single_player_focus = has_close_up and len(roles_seen) <= 1

    return {
        "has_action_verb": has_action_verb,
        "has_drs": has_drs,
        "has_brand": has_brand,
        "has_live_ctx": has_live_ctx,
        "has_celeb_player": has_celeb_player,
        "has_celeb_crowd": has_celeb_crowd,
        "has_crowd_subj": has_crowd_subj,
        "has_slowmo": has_slowmo,
        "has_no_players": has_no_players,
        "has_career_stats": has_career,
        "has_dismissal": has_dismissal,
        "has_explicit_umpire": has_explicit_umpire,
        "has_hypothetical_umpire": has_hypothetical_umpire,
        "has_signaling_verb": has_signaling_verb,
        "is_replay_tag": is_replay_tag,
        "is_delivery_phase": is_delivery_phase,
        # v3.1 — text-only signals layered on top of v3.
        "has_strong_delivery_verb": has_strong_delivery_verb,
        "has_wide_field": has_wide_field,
        "has_pitch_context": has_pitch_context,
        "has_crowd_prominent": has_crowd_prominent,
        "has_multi_actor": has_multi_actor,
        "has_replay_overlay": has_replay_overlay,
        "has_post_action": has_post_action,
        "has_close_up": has_close_up,
        "is_single_player_focus": is_single_player_focus,
    }


def label_frame(f: FrameInput, ev: dict) -> str:
    """Apply the priority-order label decision (AD > DRS > REPLAY >
    UMPIRE_SIGNAL > DELIVERY_ACTION > REPLAY_LEAN > NON_DELIVERY_ACTION).

    v3.1 layers on top of v3:
      * ``has_replay_overlay`` (overlay text like "INSTANT REPLAY",
        "WICKET BALL SPEED", or ANALYSIS-as-graphic) → REPLAY hard.
      * ``has_post_action`` ("post-action moment", "darkened stadium")
        → REPLAY (these reliably mark replay sequences).
      * Frames that v3 would label DELIVERY but ``is_single_player_focus``
        AND not ``has_wide_field`` → demoted to REPLAY_LEAN, a soft
        replay signal that the cluster-aware filter in
        :class:`eyes.continuous_chunker.ContinuousChunker` weights against
        the cluster's accept/reject verdict.
    """
    cam = f.prod_cam
    phase = f.prod_phase

    # AD
    if cam == "ad" or phase == "advertisement":
        return LABEL_AD
    if cam == "graphic" and ev["has_brand"] and ev["has_no_players"]:
        return LABEL_AD
    if (f.ts <= EARLY_GRAPHIC_AD_HORIZON_S
            and cam == "graphic" and ev["has_no_players"]):
        return LABEL_AD

    # DRS
    if ev["has_drs"]:
        return LABEL_DRS

    # REPLAY (Fix #2: celeb_player ALONE doesn't trigger)
    # v3.1 hard-replay override: overlay strings like "INSTANT REPLAY"
    # / "WICKET BALL SPEED" / "SLOW MOTION" / ANALYSIS-as-graphic only
    # render during replay sequences — bulletproof short-circuit.
    # ``has_post_action`` and ``is_single_player_focus`` are kept as
    # evidence (not label overrides) so cluster-level filters in
    # ContinuousChunker can fold them in without breaking v3 window
    # expansion through bowler-walks-back / between_play intervals.
    if ev.get("has_replay_overlay"):
        return LABEL_REPLAY
    if ev["is_replay_tag"]:
        return LABEL_REPLAY
    if ev["has_career_stats"] or ev["has_dismissal"]:
        return LABEL_REPLAY
    if ev["has_slowmo"]:
        return LABEL_REPLAY
    if ev["has_crowd_subj"] and ev["has_action_verb"]:
        return LABEL_REPLAY
    if ev["has_celeb_crowd"]:
        return LABEL_REPLAY

    # UMPIRE_SIGNAL
    if (ev["has_explicit_umpire"]
            and not ev["has_hypothetical_umpire"]
            and ev["has_signaling_verb"]
            and cam != "bowlers_end"):
        return LABEL_UMPIRE

    # DELIVERY_ACTION (any of the three predicates)
    delivery_a = (
        ev["is_delivery_phase"]
        and ev["has_live_ctx"]
        and not ev["has_crowd_subj"]
        and not ev["is_replay_tag"]
    )
    delivery_b = (
        ev["has_action_verb"]
        and cam in LIVE_CAMS
        and ev["has_live_ctx"]
    )
    delivery_c = (
        f.v2_class == "action"
        and cam in LIVE_CAMS
        and ev["is_delivery_phase"]
        and ev["has_live_ctx"]
    )
    # v3.1 crowd-prominent demotion: an off-live-cam frame that has a
    # strong delivery verb but is described primarily in terms of the
    # crowd ("large crowd in the background", "crowd of spectators")
    # is almost certainly a replay angle.  Demote to REPLAY_LEAN; the
    # cluster filter folds in surrounding context.  Live-cam frames
    # are exempt — production tagging vets them as the live feed.
    if (cam not in LIVE_CAMS
            and ev.get("has_crowd_prominent")
            and ev.get("has_strong_delivery_verb")):
        return LABEL_REPLAY_LEAN

    if delivery_a or delivery_b or delivery_c:
        # v3.1 close-up demotion: a frame that would otherwise be
        # DELIVERY but reads as a single-player close-up WITHOUT
        # wide-field framing OR cricket-pitch context AND is not on a
        # live production cam is more likely an isolated replay cut
        # than the live broadcast.  Pitch context (stumps / crease /
        # wicket) protects truncated deliveries where Scout describes
        # the action close-up but still mentions cricket-specific
        # objects.  The cluster filter in ContinuousChunker decides
        # accept / reject from neighbours.
        if (ev.get("is_single_player_focus")
                and not ev.get("has_wide_field")
                and not ev.get("has_pitch_context")
                and cam not in LIVE_CAMS):
            return LABEL_REPLAY_LEAN
        return LABEL_DELIVERY

    # v3.1 off-live-cam delivery upgrade: when production tags don't
    # claim a live cam (auto-detector pipeline runs without v2 prod_cam
    # signals at all), accept frames that have a strong delivery verb
    # AND wide-field / pitch-context framing AND aren't a single-player
    # close-up.  Mirrors validate_replay_rules.label_frame_v31's
    # primary delivery rule.  Live-cam frames keep the v3 path above.
    if (cam not in LIVE_CAMS
            and ev.get("has_strong_delivery_verb")
            and (ev.get("has_wide_field") or ev.get("has_pitch_context"))
            and not ev.get("is_single_player_focus")):
        return LABEL_DELIVERY

    # Off-live-cam close-up framing with no wide-field / pitch-context
    # corroboration reads as soft replay rather than non-delivery.
    if (ev.get("is_single_player_focus")
            and not ev.get("has_wide_field")
            and not ev.get("has_pitch_context")
            and cam not in LIVE_CAMS):
        return LABEL_REPLAY_LEAN

    return LABEL_NON_DELIVERY


def _solo_phase_only(f: FrameInput, ev: dict) -> bool:
    """True if a frame's DELIVERY_ACTION was driven SOLELY by rule (a)
    (is_delivery_phase + has_live_ctx) with no action-verb / v2_class
    corroboration.  Such frames are demoted unless they have neighbors.
    """
    return (
        ev["is_delivery_phase"]
        and ev["has_live_ctx"]
        and not ev["has_action_verb"]
        and f.v2_class != "action"
    )


def classify_frames(frames: list[FrameInput]) -> list[LabeledFrame]:
    """Compute per-frame labels with priority-order rules and apply the
    solo-prod_phase demotion (post-label rewrite).

    Frames are sorted by ts on input; a defensive sort happens here too.
    """
    if not frames:
        return []
    ordered = sorted(frames, key=lambda x: x.ts)

    labeled: list[LabeledFrame] = []
    for f in ordered:
        ev = score_frame(f)
        labeled.append(LabeledFrame(
            ts=f.ts, label=label_frame(f, ev), inputs=f, evidence=ev))

    # Solo prod_phase demotion (Section A).
    n = len(labeled)
    delivery_idx = [i for i, lf in enumerate(labeled)
                    if lf.label == LABEL_DELIVERY]
    delivery_set = set(delivery_idx)
    for i in delivery_idx:
        lf = labeled[i]
        if not _solo_phase_only(lf.inputs, lf.evidence):
            continue
        ts = lf.ts
        # Neighbor: another DELIVERY_ACTION within ±1.5 s
        has_neighbor = any(
            j != i
            and j in delivery_set
            and abs(labeled[j].ts - ts) <= SOLO_PHASE_NEIGHBOR_S
            for j in range(max(0, i - 6), min(n, i + 7))
        )
        # Support: action-verb OR v2_class=="action" within ±2.0 s
        has_support = False
        for j in range(max(0, i - 6), min(n, i + 7)):
            if j == i:
                continue
            if abs(labeled[j].ts - ts) > SOLO_PHASE_SUPPORT_S:
                continue
            if (labeled[j].evidence.get("has_action_verb")
                    or labeled[j].inputs.v2_class == "action"):
                has_support = True
                break
        if not has_neighbor and not has_support:
            lf.label = LABEL_NON_DELIVERY
            lf.evidence["_demoted_solo_phase"] = True

    return labeled


# ── Chunk construction ───────────────────────────────────────────────


def _contiguous_chunks(labeled: list[LabeledFrame]) -> list[Chunk]:
    """Group consecutive same-label frames into Chunk objects."""
    chunks: list[Chunk] = []
    if not labeled:
        return chunks
    cur_label = labeled[0].label
    cur_start = labeled[0].ts
    cur_end = labeled[0].ts
    cur_idx = [0]
    for i in range(1, len(labeled)):
        lf = labeled[i]
        if lf.label == cur_label:
            cur_end = lf.ts
            cur_idx.append(i)
        else:
            chunks.append(Chunk(
                label=cur_label, start_ts=cur_start, end_ts=cur_end,
                frame_indices=cur_idx))
            cur_label = lf.label
            cur_start = lf.ts
            cur_end = lf.ts
            cur_idx = [i]
    chunks.append(Chunk(
        label=cur_label, start_ts=cur_start, end_ts=cur_end,
        frame_indices=cur_idx))
    return chunks


def _is_live_anchor(lf: LabeledFrame) -> bool:
    """Live-anchor frame for the Fix #1 propagation halt rule."""
    cam = lf.inputs.prod_cam
    ev = lf.evidence
    return (
        cam in LIVE_CAMS
        and ev.get("has_live_ctx", False)
        and not ev.get("has_crowd_subj", False)
        and not ev.get("has_career_stats", False)
    )


def _is_propagation_eligible(lf: LabeledFrame) -> bool:
    """Ambiguous frame eligible to be absorbed by REPLAY propagation
    (Section B.2)."""
    ev = lf.evidence
    if ev.get("has_crowd_subj") or ev.get("has_celeb_crowd"):
        return True
    if ev.get("has_career_stats") or ev.get("has_dismissal"):
        return True
    if ev.get("has_slowmo"):
        return True
    if (lf.inputs.v2_class == "action"
            and ev.get("is_delivery_phase")):
        return True
    return False


def _propagate_replays(labeled: list[LabeledFrame]) -> None:
    """Mutate ``labeled`` in place: from each REPLAY frame walk forward
    and backward through propagation-eligible frames.  Halt on each
    side at 3 consecutive live anchors OR 4 s of accumulated live
    anchor (Fix #1)."""
    n = len(labeled)
    replay_seeds = [i for i, lf in enumerate(labeled)
                    if lf.label == LABEL_REPLAY]

    def _walk(start_idx: int, step: int) -> None:
        i = start_idx + step
        live_run = 0
        live_acc_start: Optional[float] = None
        live_acc_total = 0.0
        last_ts = labeled[start_idx].ts
        while 0 <= i < n:
            lf = labeled[i]
            if _is_live_anchor(lf):
                live_run += 1
                if live_acc_start is None:
                    live_acc_start = lf.ts
                live_acc_total = abs(lf.ts - live_acc_start)
                if (live_run >= REPLAY_PROP_LIVE_ANCHOR_RUN
                        or live_acc_total >= REPLAY_PROP_LIVE_ANCHOR_S):
                    return
                # Live anchor encountered but not yet over threshold —
                # do NOT absorb.  Keep walking.
                last_ts = lf.ts
                i += step
                continue
            live_run = 0
            live_acc_start = None
            live_acc_total = 0.0
            if lf.label in HOSTILE_LABELS and lf.label != LABEL_REPLAY:
                # AD or DRS — hard stop.
                return
            if lf.label == LABEL_REPLAY:
                last_ts = lf.ts
                i += step
                continue
            if not _is_propagation_eligible(lf):
                # Not eligible and not a live-anchor that resets — stop.
                return
            lf.label = LABEL_REPLAY
            lf.evidence["_replay_propagated"] = True
            last_ts = lf.ts
            i += step

    for seed in replay_seeds:
        _walk(seed, +1)
        _walk(seed, -1)


def _confirm_delivery_chunks(labeled: list[LabeledFrame],
                             chunks: list[Chunk]) -> None:
    """Set ``confirmed=True`` on DELIVERY_ACTION chunks per §B.1."""
    for c in chunks:
        if c.label != LABEL_DELIVERY:
            continue
        # (i) ≥2 DELIVERY_ACTION frames within a 4 s window
        idxs = c.frame_indices
        if len(idxs) >= ANCHOR_CONFIRM_MIN_FRAMES:
            tss = [labeled[i].ts for i in idxs]
            tss.sort()
            for a in range(len(tss)):
                for b in range(a + 1, len(tss)):
                    if (tss[b] - tss[a]) <= ANCHOR_CONFIRM_WINDOW_S:
                        c.confirmed = True
                        break
                if c.confirmed:
                    break
        if c.confirmed:
            continue
        # (ii) 1 is_delivery_phase frame + ≥1 has_action_verb frame
        # within ±2 s
        for i in idxs:
            ev_i = labeled[i].evidence
            if not ev_i.get("is_delivery_phase"):
                continue
            ts_i = labeled[i].ts
            for j, lf_j in enumerate(labeled):
                if j == i:
                    continue
                if abs(lf_j.ts - ts_i) > ANCHOR_BRIDGE_WINDOW_S:
                    continue
                if lf_j.evidence.get("has_action_verb"):
                    c.confirmed = True
                    break
            if c.confirmed:
                break


def _has_graphic_block(labeled: list[LabeledFrame],
                       lo: int, hi: int) -> bool:
    """True if there's a contiguous run of ≥2 graphic frames spanning
    > GRAPHIC_BLOCK_MIN_S between indices lo..hi (inclusive)."""
    if hi < lo:
        return False
    run_start = None
    run_count = 0
    for k in range(lo, hi + 1):
        if labeled[k].inputs.prod_cam == "graphic":
            if run_start is None:
                run_start = labeled[k].ts
                run_count = 1
            else:
                run_count += 1
                if run_count >= 2 and (
                        labeled[k].ts - run_start) >= GRAPHIC_BLOCK_MIN_S:
                    return True
        else:
            run_start = None
            run_count = 0
    return False


def _merge_same_label(labeled: list[LabeledFrame],
                      chunks: list[Chunk]) -> list[Chunk]:
    """Apply Fix #3 cluster-merge: same-label confirmed DELIVERY
    chunks within 10 s merge if the gap is benign.  Single-frame
    REPLAY / AD / DRS in the gap are treated as Scout flicker and do
    NOT block; sustained hostile (≥2 contiguous frames) does block.

    Bug-fix vs prior version: the prev-chunk lookup tracks the last
    DELIVERY chunk in ``out`` rather than ``out[-1]`` — otherwise
    interleaved NDA chunks always caused the label-equality test to
    fail and the merge never fired.
    """
    if not chunks:
        return chunks
    out: list[Chunk] = []
    last_delivery_out_idx: int | None = None
    for ch in chunks:
        if (ch.label == LABEL_DELIVERY and ch.confirmed
                and last_delivery_out_idx is not None
                and out[last_delivery_out_idx].confirmed):
            prev = out[last_delivery_out_idx]
            gap = ch.start_ts - prev.end_ts
            if 0 <= gap <= CLUSTER_MERGE_GAP_S:
                gap_lo = prev.frame_indices[-1] + 1
                gap_hi = ch.frame_indices[0] - 1
                if _gap_is_mergeable(labeled, gap_lo, gap_hi):
                    prev.end_ts = ch.end_ts
                    prev.frame_indices.extend(ch.frame_indices)
                    continue
        out.append(ch)
        if ch.label == LABEL_DELIVERY:
            last_delivery_out_idx = len(out) - 1
    return out


def _gap_is_mergeable(labeled: list[LabeledFrame],
                      gap_lo: int, gap_hi: int) -> bool:
    """Check whether the inter-cluster gap [gap_lo..gap_hi] permits
    merging two DELIVERY clusters per Fix #3.

    Sustained hostile (≥2 contiguous frames of REPLAY/AD/DRS) blocks
    merge.  Isolated single-frame hostile is flicker — does NOT block.
    A graphic-block lasting > 2 s also blocks.
    """
    if gap_hi < gap_lo:
        return True
    # Walk the gap counting consecutive hostile frames.  Reset on
    # non-hostile; if any run reaches 2, the gap is not mergeable.
    hostile_run = 0
    for k in range(gap_lo, gap_hi + 1):
        if labeled[k].label in HOSTILE_LABELS:
            hostile_run += 1
            if hostile_run >= 2:
                return False
        else:
            hostile_run = 0
    if _has_graphic_block(labeled, gap_lo, gap_hi):
        return False
    return True


def build_chunks(labeled_in: list[LabeledFrame]) -> list[Chunk]:
    """End-to-end chunking: propagate replays, build contiguous chunks,
    confirm delivery anchors, merge same-label clusters."""
    if not labeled_in:
        return []
    # Work on a copy so callers' label list is unaffected by propagation.
    labeled = [LabeledFrame(
        ts=lf.ts, label=lf.label, inputs=lf.inputs,
        evidence=dict(lf.evidence)) for lf in labeled_in]
    _propagate_replays(labeled)
    chunks = _contiguous_chunks(labeled)
    _confirm_delivery_chunks(labeled, chunks)
    chunks = _merge_same_label(labeled, chunks)
    # Re-confirm post-merge (merged chunks now span multiple original
    # delivery frames; the confirmed flag was carried from the first).
    _confirm_delivery_chunks(labeled, chunks)
    return chunks


# ── Window construction ──────────────────────────────────────────────


def _label_at_time(labeled: list[LabeledFrame], ts: float) -> str | None:
    """Return label of the frame at exactly ``ts`` (None if absent)."""
    for lf in labeled:
        if abs(lf.ts - ts) < 1e-6:
            return lf.label
    return None


def _hostile_run_at(labeled: list[LabeledFrame],
                    start_idx: int, step: int) -> int:
    """Count consecutive hostile frames starting at ``start_idx`` and
    walking by ``step`` (±1).  Used to distinguish single-frame
    flicker (run == 1) from sustained hostile blocks (run ≥ 2)."""
    n = len(labeled)
    run = 0
    i = start_idx
    while 0 <= i < n and labeled[i].label in HOSTILE_LABELS:
        run += 1
        i += step
    return run


def _expand_lookback(labeled: list[LabeledFrame],
                    cluster_start_idx: int,
                    max_s: float) -> float:
    """Walk backward through NON_DELIVERY_ACTION (and same-label
    DELIVERY frames) absorbing single-frame hostile flicker.  Halt on
    sustained hostile (≥2 contiguous) or graphic-block (≥2 contiguous
    graphic frames)."""
    if cluster_start_idx <= 0:
        return labeled[cluster_start_idx].ts
    new_start_ts = labeled[cluster_start_idx].ts
    target = new_start_ts - max_s
    i = cluster_start_idx - 1
    while i >= 0 and labeled[i].ts >= target:
        lf = labeled[i]
        if lf.label in HOSTILE_LABELS:
            run = _hostile_run_at(labeled, i, -1)
            if run >= 2:
                break
            # 1-frame flicker: skip past it without claiming the bound.
            i -= 1
            continue
        if (lf.inputs.prod_cam == "graphic"
                and i - 1 >= 0
                and labeled[i - 1].inputs.prod_cam == "graphic"):
            break
        if lf.label not in (LABEL_NON_DELIVERY, LABEL_DELIVERY):
            break
        new_start_ts = lf.ts
        i -= 1
    return new_start_ts


def _expand_forward(labeled: list[LabeledFrame],
                   cluster_end_idx: int,
                   max_s: float) -> float:
    n = len(labeled)
    if cluster_end_idx >= n - 1:
        return labeled[cluster_end_idx].ts
    new_end_ts = labeled[cluster_end_idx].ts
    target = new_end_ts + max_s
    j = cluster_end_idx + 1
    while j < n and labeled[j].ts <= target:
        lf = labeled[j]
        if lf.label in HOSTILE_LABELS:
            run = _hostile_run_at(labeled, j, +1)
            if run >= 2:
                break
            # 1-frame flicker: skip past it without claiming the bound.
            j += 1
            continue
        if (lf.inputs.prod_cam == "graphic"
                and j + 1 < n
                and labeled[j + 1].inputs.prod_cam == "graphic"):
            break
        if lf.label not in (LABEL_NON_DELIVERY, LABEL_DELIVERY):
            break
        new_end_ts = lf.ts
        j += 1
    return new_end_ts


def _build_window_for_cluster(
        cluster: Chunk,
        labeled_for_window: list[LabeledFrame],
        chunks: list[Chunk],
        ) -> tuple[float, float]:
    """Compute the consequential delivery window (start, end) for one
    confirmed DELIVERY cluster.  Helper shared by the primary-cluster
    scorer and the final window builder."""
    start_ts = _expand_lookback(
        labeled_for_window, cluster.frame_indices[0], LOOKBACK_S)
    end_ts = _expand_forward(
        labeled_for_window, cluster.frame_indices[-1], FORWARD_S)
    for c in chunks:
        if c.label == LABEL_UMPIRE:
            if 0 <= c.start_ts - end_ts <= UMPIRE_APPEND_S:
                end_ts = max(end_ts, c.end_ts)
        elif c.label == LABEL_DRS:
            if 0 <= c.start_ts - end_ts <= DRS_APPEND_S:
                end_ts = max(end_ts, c.end_ts)
    return (start_ts, end_ts)


def _select_primary_cluster(
        confirmed: list[Chunk],
        labeled_for_window: list[LabeledFrame],
        chunks: list[Chunk],
        event_ts: Optional[float]) -> Optional[Chunk]:
    """Pick the cluster whose POST-EXPANSION window is largest.

    Raw cluster duration is misleading when one false-positive cluster
    is short but its expansion is also short (blocked by neighboring
    REPLAY/AD/DRS) and the real cluster is short but expands cleanly
    through NDA.  The post-expansion size correlates with how
    "supported" the cluster is by surrounding context.
    """
    if not confirmed:
        return None
    if event_ts is not None:
        before = [c for c in confirmed if c.end_ts <= event_ts]
        if before:
            return max(before, key=lambda c: c.end_ts)
        return min(confirmed, key=lambda c: abs(c.end_ts - event_ts))
    # No event_ts → score by post-expansion window width.
    best: Optional[Chunk] = None
    best_width = -1.0
    for c in confirmed:
        s, e = _build_window_for_cluster(c, labeled_for_window, chunks)
        w = max(0.0, e - s)
        if w > best_width:
            best_width = w
            best = c
    return best


def find_consequential_window(
        frames: list[FrameInput],
        event_ts: Optional[float] = None,
        ) -> Optional[tuple[float, float]]:
    """End-to-end: classify, chunk, return (start_ts, end_ts) | None.

    ``event_ts`` is optional; when supplied, selects the cluster whose
    end is closest to (and not after) it.  Otherwise the cluster with
    the largest post-expansion window wins (NOT raw cluster duration —
    short clusters surrounded by NDA can carry a real delivery while
    short clusters butted against REPLAY do not).
    """
    if not frames:
        return None
    labeled = classify_frames(frames)
    if not labeled:
        return None
    chunks = build_chunks(labeled)

    # Re-derive a labeled list for window expansion that includes the
    # propagation mutations (build_chunks operates on a copy).
    labeled_for_window = [LabeledFrame(
        ts=lf.ts, label=lf.label, inputs=lf.inputs,
        evidence=dict(lf.evidence)) for lf in labeled]
    _propagate_replays(labeled_for_window)

    confirmed_delivery = [c for c in chunks
                          if c.label == LABEL_DELIVERY and c.confirmed]
    primary = _select_primary_cluster(
        confirmed_delivery, labeled_for_window, chunks, event_ts)
    if primary is None:
        return None

    start_ts, end_ts = _build_window_for_cluster(
        primary, labeled_for_window, chunks)
    return (round(start_ts, 3), round(end_ts, 3))


# ── Confidence-scoring pipeline (v3.2) ──────────────────────────────
# Per-frame 6-label confidence + walk-with-inertia clustering, ported
# from ``files/scripts/broadcast_mode_tuning/simulate_confidence_chunker.py``.
# Drives :class:`eyes.continuous_chunker.ContinuousChunker`.  The legacy
# :func:`label_frame` priority-rules path (used by the score-event v3
# code path) is unchanged.

CONF_LABELS = ("DELIVERY", "REPLAY", "AD", "DRS", "UMPIRE", "NON_DELIVERY")

# v2_broadcast_tag values (uppercase) that hard-disqualify delivery.
_REPLAY_V2_TAGS = frozenset({"REPLAY", "SLO-MO", "TELESTRATOR",
                             "SPLIT-SCREEN"})

# ── Speed-overlay isolation classifier ─────────────────────────────
# Scout transcribes the on-screen speed overlay (e.g. "142.3 kph")
# verbatim.  Real deliveries render the speed overlay alongside the
# score / overs / striker stats / team abbreviation; replay clips
# strip everything except the speed.  This pair of rules exploits the
# distinction.
SPEED_PAT = re.compile(r"\d{2,3}(\.\d)?\s*kph", re.IGNORECASE)
SCORE_NUM_PAT = re.compile(r"\b\d{1,3}\s*[-/]\s*\d{1,2}\b")
OVER_PAT = re.compile(r"\(\d{1,2}\.\d\)")
BATTER_STAT_PAT = re.compile(r"\b\d{1,3}\s*\(\s*\d{1,3}\s*\)")
TEAM_ABBREV_PAT = re.compile(
    r"\b(DC|CSK|MI|RCB|KKR|RR|PBKS|LSG|GT|SRH)\b")

_SPEED_CONTEXT_PATTERNS = (
    SCORE_NUM_PAT, OVER_PAT, BATTER_STAT_PAT, TEAM_ABBREV_PAT)


def has_speed_with_score(desc: str | None) -> bool:
    """Speed overlay co-rendered with score / overs / batter stats /
    team abbreviation — broadcast-side signal that the frame is a live
    delivery, not a replay isolated cut."""
    if not desc:
        return False
    if not SPEED_PAT.search(desc):
        return False
    return any(p.search(desc) for p in _SPEED_CONTEXT_PATTERNS)


def has_speed_alone(desc: str | None) -> bool:
    """Speed overlay rendered without any of the live-broadcast
    accompaniments (score / overs / batter stats / team abbreviation).
    Strong replay indicator."""
    if not desc or not SPEED_PAT.search(desc):
        return False
    return not has_speed_with_score(desc)


def _count_actor_tokens(desc_lower: str) -> int:
    seen: set[str] = set()
    for r in ACTOR_ROLES:
        if r in desc_lower:
            seen.add(r.split()[0])
    return len(seen)


def score_frame_confidence(open_desc: str | None,
                           v2_broadcast_tag: str | None = None) -> dict:
    """Per-frame 6-label confidence ∈ [0, 1].  No state.

    Cricket invariants are HARD rules: ``has_crowd_prominent + action``,
    explicit replay-overlay text, v2_broadcast_tag in
    {REPLAY, SLO-MO, TELESTRATOR, SPLIT-SCREEN}, and explicit
    post-action phrases all veto the DELIVERY contribution.

    Returns the score dict; every label key is present, all values are
    clamped to [0, 1].  An always-on NON_DELIVERY fallback ensures
    every frame has a clear top label so downstream walks have an
    anchor to inspect.
    """
    d = (open_desc or "").lower()
    v2 = (v2_broadcast_tag or "").upper()

    has_strong = _has_any(STRONG_DELIVERY_VERBS, d)
    has_weak = _has_any(WEAK_ACTION_VERBS, d)
    has_action_any = has_strong or has_weak
    has_speed_score = has_speed_with_score(d)
    has_speed_only = has_speed_alone(d)
    has_wide = (_has_any(WIDE_FIELD_TERMS, d)
                or _count_actor_tokens(d) >= 2)
    has_pitch = _has_any(PITCH_CONTEXT_TERMS, d)
    has_close = _has_any(CLOSE_UP_TERMS, d)
    has_replay_ovl_bare = _has_any(REPLAY_OVERLAY_BARE_TERMS, d)
    has_analysis_graphic = (
        "analysis" in d
        and ("graphic" in d or "overlay" in d or "letters" in d))
    has_replay_overlay = has_replay_ovl_bare or has_analysis_graphic
    has_post_action = _has_any(POST_ACTION_PHRASES, d)
    has_crowd = _has_any(CROWD_PROMINENT_TERMS, d)
    has_no_players = _has_any(NO_PLAYERS_TERMS, d)
    has_brand = _has_any(BRAND_KEYWORDS, d)
    has_drs = _has_any(DRS_KEYWORDS, d)
    has_umpire_subj = _has_any(EXPLICIT_UMPIRE, d)
    has_signal = _has_any(SIGNALING_VERBS, d)

    s = {lbl: 0.0 for lbl in CONF_LABELS}

    delivery_disqualified = (
        (has_crowd and has_action_any)
        or has_replay_overlay
        or v2 in _REPLAY_V2_TAGS
        or has_post_action
    )
    if not delivery_disqualified:
        if has_strong:
            s["DELIVERY"] += 0.50
        elif has_weak:
            s["DELIVERY"] += 0.20
        if has_wide:
            s["DELIVERY"] += 0.20
        if has_pitch:
            s["DELIVERY"] += 0.15
        if has_close and not has_pitch:
            s["DELIVERY"] -= 0.20
        # Speed-overlay isolation: speed + live broadcast stats is a
        # high-confidence delivery signal; speed by itself is a
        # high-confidence replay signal handled below.
        if has_speed_score:
            s["DELIVERY"] += 0.50

    if has_replay_overlay:
        s["REPLAY"] += 0.70
    if v2 in _REPLAY_V2_TAGS:
        s["REPLAY"] += 0.50
    if has_post_action:
        s["REPLAY"] += 0.30
    if has_crowd and has_action_any:
        s["REPLAY"] += 0.30
    if has_speed_only:
        s["REPLAY"] += 0.50

    if has_brand and has_no_players:
        s["AD"] += 0.50
    if has_no_players:
        s["AD"] += 0.20

    if has_drs:
        s["DRS"] += 0.80

    if has_umpire_subj and has_signal:
        s["UMPIRE"] += 0.50

    if _has_any(NON_DELIVERY_HINTS[:2], d):
        s["NON_DELIVERY"] += 0.30
    if _has_any(NON_DELIVERY_HINTS[2:], d):
        s["NON_DELIVERY"] += 0.20
    if (("single cricket player" in d or "close-up" in d)
            and not has_action_any):
        s["NON_DELIVERY"] += 0.25

    others_max = max(s["DELIVERY"], s["REPLAY"], s["AD"],
                     s["DRS"], s["UMPIRE"])
    if others_max < 0.30:
        s["NON_DELIVERY"] = max(s["NON_DELIVERY"], 0.55 - others_max)

    return {k: max(0.0, min(1.0, v)) for k, v in s.items()}


def find_all_anchors(scored_frames: list[dict]) -> list[tuple[int, str, float]]:
    """Every frame gets an anchor — its top-scoring label + that score.

    The NON_DELIVERY fallback in :func:`score_frame_confidence` ensures
    every frame has at least one non-zero label, so a top exists.
    """
    out: list[tuple[int, str, float]] = []
    for i, f in enumerate(scored_frames):
        ranked = sorted(f["score"].items(), key=lambda x: -x[1])
        top, top_v = ranked[0]
        out.append((i, top, float(top_v)))
    return out


def demote_sandwiched_anchors(
        anchors: list[tuple[int, str, float]],
        scored_frames: list[dict],
        ) -> list[tuple[int, str, float]]:
    """Single-frame structural sandwich correction.

    If anchor A at j is between anchors j-1 / j+1 of the SAME different
    label AND both neighbours have higher scores, demote A to that
    surrounding label with dampened score.  Mutates
    ``scored_frames[j]['score']`` in place so subsequent walk_chunk
    calls see the correction.  Iterates until stable.
    """
    while True:
        changed = False
        new_anchors: list[tuple[int, str, float]] = []
        for j, (idx, label, score) in enumerate(anchors):
            if j == 0 or j == len(anchors) - 1:
                new_anchors.append((idx, label, score))
                continue
            _pi, prev_label, prev_score = anchors[j - 1]
            _ni, next_label, next_score = anchors[j + 1]
            if (prev_label == next_label
                    and prev_label != label
                    and prev_score > score
                    and next_score > score):
                demoted_score = (prev_score + next_score) / 2 - 0.10
                new_anchors.append((idx, prev_label, demoted_score))
                scored_frames[idx]["score"][prev_label] = max(
                    scored_frames[idx]["score"].get(prev_label, 0.0),
                    demoted_score)
                if label != prev_label:
                    scored_frames[idx]["score"][label] = score - 0.30
                changed = True
            else:
                new_anchors.append((idx, label, score))
        anchors = new_anchors
        if not changed:
            break
    return anchors


def find_delivery_anchors(scored_frames: list[dict]) -> list[int]:
    """Indices of CONFIRMED DELIVERY anchors (post sandwich-correction)."""
    all_anchors = find_all_anchors(scored_frames)
    corrected = demote_sandwiched_anchors(all_anchors, scored_frames)
    return [idx for (idx, lbl, sc) in corrected
            if lbl == "DELIVERY" and sc >= 0.50]


def walk_chunk(scored_frames: list[dict],
               anchor_idx: int) -> tuple[int, int, float]:
    """Walk both directions from a DELIVERY anchor accumulating
    evidence per inertia rules (Case A/B/C in the design memo).
    Returns ``(start_idx, end_idx, total_strength)``.
    """
    n = len(scored_frames)
    S = scored_frames[anchor_idx]["score"]["DELIVERY"]

    def _extend(direction: int) -> int:
        nonlocal S
        i = anchor_idx
        while True:
            j = i + direction
            if j < 0 or j >= n:
                return i
            f = scored_frames[j]
            support = f["score"]["DELIVERY"]
            dissent_top = max(v for k, v in f["score"].items()
                              if k != "DELIVERY")
            # Case A — supports
            if support >= 0.40 and dissent_top < 0.40:
                S += 0.20
                i = j
                continue
            # Case B — ambiguous, lookahead 2
            if support >= 0.20 and dissent_top < 0.50:
                if S >= 1.0:
                    i = j
                    continue
                ks = [j + direction * k for k in (1, 2)]
                ks = [k for k in ks if 0 <= k < n]
                next_supports = [
                    scored_frames[k]["score"]["DELIVERY"] for k in ks]
                if sum(1 for v in next_supports if v >= 0.30) >= 1:
                    i = j
                    continue
                return i
            # Case C — strong dissent, lookahead 3
            if dissent_top >= 0.50 and support < 0.30:
                ks = [j + direction * k for k in (1, 2, 3)]
                ks = [k for k in ks if 0 <= k < n]
                next_dissent = sum(
                    1 for k in ks
                    if max(v for kk, v in scored_frames[k]["score"].items()
                           if kk != "DELIVERY") >= 0.40)
                if next_dissent >= 2:
                    return i
                if S >= 1.5:
                    S -= 0.40
                    if S < 0.30:
                        return i
                    i = j
                    continue
                return i
            return i

    end = _extend(+1)
    start = _extend(-1)
    return start, end, S


def find_clusters(scored_frames: list[dict]) -> list[tuple[int, int, float]]:
    """Cluster-form delivery anchors into ``(start_idx, end_idx, strength)``.

    Mutates ``scored_frames[i]['score']`` via demote_sandwiched_anchors.
    Overlapping walks merge.
    """
    anchors = find_delivery_anchors(scored_frames)
    used: set[int] = set()
    clusters: list[tuple[int, int, float]] = []
    for a in anchors:
        if a in used:
            continue
        s, e, S = walk_chunk(scored_frames, a)
        for j in range(s, e + 1):
            used.add(j)
        clusters.append((s, e, S))
    clusters.sort()
    merged: list[list] = []
    for c in clusters:
        if merged and c[0] <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], c[1])
            merged[-1][2] = merged[-1][2] + c[2]
        else:
            merged.append([c[0], c[1], c[2]])
    return [(s, e, S) for s, e, S in merged]


def cluster_level_sandwich_reject(
        cluster_start: int,
        cluster_end: int,
        all_anchors: list[tuple[int, str, float]],
        ) -> str | None:
    """Reject a cluster bracket-sandwiched by the SAME non-DELIVERY,
    non-NON_DELIVERY label on both sides.  Purely structural — no time
    windows; uses the global anchor sequence.
    """
    cluster_anchor_positions = [
        i for i, (idx, _, _) in enumerate(all_anchors)
        if cluster_start <= idx <= cluster_end
    ]
    if not cluster_anchor_positions:
        return None
    first_pos = cluster_anchor_positions[0]
    last_pos = cluster_anchor_positions[-1]
    prev_label = (all_anchors[first_pos - 1][1]
                  if first_pos > 0 else None)
    next_label = (all_anchors[last_pos + 1][1]
                  if last_pos < len(all_anchors) - 1 else None)
    if (prev_label is not None and next_label is not None
            and prev_label == next_label
            and prev_label != "DELIVERY"
            and prev_label != "NON_DELIVERY"):
        return f"cluster_sandwich_{prev_label}"
    return None


def cluster_rejection_v31(
        scored_frames: list[dict],
        s: int, e: int) -> str | None:
    """v3.1 in-cluster rejection: replay overlay, crowd-sandwich,
    close-up dominated.  Operates on the confidence scores + raw
    description text, not chunker_v3 LabeledFrame labels.
    """
    cluster_frames = scored_frames[s:e + 1]
    if not cluster_frames:
        return "empty"

    n_strong_delivery = 0
    n_replay_strong = 0
    n_crowd = 0
    n_close = 0

    for f in cluster_frames:
        desc = (f.get("desc") or "").lower()
        has_crowd = _has_any(CROWD_PROMINENT_TERMS, desc)
        if f["score"]["DELIVERY"] >= 0.5 and not has_crowd:
            n_strong_delivery += 1
        analysis_graphic = (
            "analysis" in desc
            and ("graphic" in desc or "overlay" in desc
                 or "letters" in desc))
        if (_has_any(REPLAY_OVERLAY_BARE_TERMS, desc)
                or analysis_graphic
                or f["score"]["REPLAY"] >= 0.7):
            n_replay_strong += 1
        if has_crowd:
            n_crowd += 1
        if (_has_any(CLOSE_UP_TERMS, desc)
                and not _has_any(PITCH_CONTEXT_TERMS, desc)):
            n_close += 1

    if n_replay_strong >= 1:
        return f"v31_replay_overlay_{n_replay_strong}"
    if n_crowd >= 1 and n_strong_delivery <= 1:
        return f"v31_crowd_sandwich_{n_crowd}c/{n_strong_delivery}d"
    if (len(cluster_frames) > 0
            and n_close > len(cluster_frames) / 2
            and n_strong_delivery <= 1):
        return f"v31_close_up_dominated_{n_close}/{len(cluster_frames)}"
    return None


__all__ = [
    "FrameInput",
    "LabeledFrame",
    "Chunk",
    "score_frame",
    "label_frame",
    "classify_frames",
    "build_chunks",
    "find_consequential_window",
    "LABELS",
    "LABEL_AD",
    "LABEL_DRS",
    "LABEL_REPLAY",
    "LABEL_UMPIRE",
    "LABEL_DELIVERY",
    "LABEL_NON_DELIVERY",
    "DELIVERY_PHASES",
    "LIVE_CAMS",
    "REPLAY_TAG_VALUES",
    # v3.2 confidence pipeline
    "CONF_LABELS",
    "score_frame_confidence",
    "find_all_anchors",
    "find_delivery_anchors",
    "demote_sandwiched_anchors",
    "walk_chunk",
    "find_clusters",
    "cluster_level_sandwich_reject",
    "cluster_rejection_v31",
    # Speed-overlay isolation classifier
    "has_speed_with_score",
    "has_speed_alone",
    "SPEED_PAT",
]
