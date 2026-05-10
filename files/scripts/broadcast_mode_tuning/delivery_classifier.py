"""Path A/B/C classifier + cluster builder + anchor selection."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from signal_extraction import Signals, extract_signals


@dataclass
class FrameInfo:
    t: float
    text: str
    signals: Signals = field(default_factory=Signals)
    is_delivery: bool = False
    path: str = "none"


def annotate(frame: FrameInfo) -> None:
    s = frame.signals
    if s.HARD:
        frame.is_delivery, frame.path = False, "none"
        return
    # K2: broadcast-context indicator. Falls back to "score-strip in
    # cricket-geometry prose" when no specific brand was quoted.
    k2 = s.K or (s.SS and s.CG)
    if s.V and s.S and (s.W or s.M2):
        frame.is_delivery, frame.path = True, "A"
        return
    if s.V and s.M and s.W and k2 and s.SS:
        frame.is_delivery, frame.path = True, "B"
        return
    if s.M2 and s.W and k2 and s.SS:
        frame.is_delivery, frame.path = True, "C"
        return
    # Path D: medium-shot batter follow-through. V + strict multi-actor +
    # explicit brand + score graphic. W not required since broadcast cuts
    # to medium shot after the ball is hit.
    if s.V and s.M2 and s.K and s.SS:
        frame.is_delivery, frame.path = True, "D"
        return
    frame.is_delivery, frame.path = False, "none"


def annotate_all(frames: list[FrameInfo]) -> None:
    for f in frames:
        if not isinstance(f.signals, Signals) or f.signals == Signals():
            f.signals = extract_signals(f.text)
        annotate(f)


def build_clusters(frames: list[FrameInfo],
                   gap_max: int = 3, min_run: int = 1) -> list[dict]:
    """Walk frames in time order. Open cluster on a DELIVERY frame.
    NOT_DELIVERY non-hard frames count toward gap; >gap_max closes.
    HARD frame closes immediately and does not count as gap."""
    clusters: list[dict] = []
    n = len(frames)
    i = 0
    while i < n:
        f = frames[i]
        if f.signals.HARD or not f.is_delivery:
            i += 1
            continue
        start = i
        last_d = i
        j = i + 1
        gap = 0
        while j < n:
            fj = frames[j]
            if fj.signals.HARD:
                break
            if fj.is_delivery:
                last_d = j
                gap = 0
            else:
                gap += 1
                if gap > gap_max:
                    break
            j += 1
        run = frames[start:last_d + 1]
        delivery_count = sum(1 for x in run if x.is_delivery)
        # Cluster V-filter uses V (negation-guarded). V_post is computed
        # in signal_extraction but not used here — kept for potential
        # future use (e.g., pre-vs-post anchoring).
        any_v = any(x.signals.V for x in run)
        if delivery_count >= min_run and any_v:
            clusters.append({
                "start_idx": start,
                "end_idx": last_d,
                "start_t": frames[start].t,
                "end_t": frames[last_d].t,
                "frames": run,
            })
        i = last_d + 1
    return clusters


_ANCHOR_RANK: list[tuple[re.Pattern, int]] = [
    (re.compile(r"\bjust\s+released\b", re.IGNORECASE), 6),
    (re.compile(r"\bjust\s+bowled\b", re.IGNORECASE), 5),
    (re.compile(r"\bfollow[-\s]through\b", re.IGNORECASE), 5),
    (re.compile(r"\bdelivery\s+stride\b", re.IGNORECASE), 4),
    (re.compile(r"\bin\s+mid-action\b", re.IGNORECASE), 4),
    (re.compile(r"\bin\s+process\s+of\s+(?:bowling|delivering)\b", re.IGNORECASE), 3),
    (re.compile(r"\babout\s+to\s+(?:release|bowl|deliver)\b", re.IGNORECASE), 2),
]
_PATH_PREF = {"A": 3, "D": 3, "B": 2, "C": 1, "none": 0}


def score_frame(f: FrameInfo) -> tuple[int, int]:
    """(prose_rank_with_pathA_bonus, m2_tiebreaker). Tuple compare:
    higher prose-rank wins; ties broken in favor of strict multi-actor."""
    base = 1
    for pat, val in _ANCHOR_RANK:
        if pat.search(f.text):
            base = max(base, val)
    if f.path == "A":
        base += 1
    return (base, 1 if f.signals.M2 else 0)


def rescue_singletons(clusters: list[dict], all_frames: list[FrameInfo],
                      max_distance_s: float = 60.0) -> list[dict]:
    """Rescue high-confidence single-frame deliveries that fall outside
    kept clusters but sit within max_distance_s of a kept cluster.

    Criteria for a frame to be a rescue candidate:
      - is_delivery=True
      - path in {A, B} (Path C/D excluded — too risky for singletons)
      - V=Y AND M2=Y (high signal density)
      - Not already inside any kept cluster

    A candidate is rescued if min(dist_before, dist_after) <= max_distance_s
    where distance is measured from the candidate's t to the nearest kept
    cluster boundary (start_t for after, end_t for before).

    Rescued singletons become 1-frame clusters with rescued=True.
    """
    if not all_frames or not clusters:
        return list(clusters)
    in_cluster_t: set[float] = set()
    for c in clusters:
        for f in c["frames"]:
            in_cluster_t.add(f.t)
    cluster_starts = sorted(c["start_t"] for c in clusters)
    cluster_ends = sorted(c["end_t"] for c in clusters)

    rescued: list[dict] = []
    for f in all_frames:
        if f.t in in_cluster_t:
            continue
        if not f.is_delivery:
            continue
        if f.path not in ("A", "B"):
            continue
        s = f.signals
        if not (s.V and s.M2):
            continue
        dist_before = min((f.t - e for e in cluster_ends if e < f.t),
                          default=float("inf"))
        dist_after = min((s_ - f.t for s_ in cluster_starts if s_ > f.t),
                         default=float("inf"))
        # Require BOTH sides within max_distance_s — singleton must be
        # sandwiched between two real clusters. This rejects pre-match
        # singletons (no prior cluster) and trailing singletons (no
        # follow-up).
        if dist_before > max_distance_s or dist_after > max_distance_s:
            continue
        rescued.append({
            "start_idx": -1,
            "end_idx": -1,
            "start_t": f.t,
            "end_t": f.t,
            "frames": [f],
            "rescued": True,
            "rescue_distance_s": min(dist_before, dist_after),
            "rescue_dist_before": dist_before,
            "rescue_dist_after": dist_after,
        })

    out = list(clusters) + rescued
    out.sort(key=lambda c: c["start_t"])
    return out


POST_ACTION_PHRASES = [
    re.compile(r"\bhelmet\s+(?:lying\s+|on\s+)?(?:on\s+)?the\s+ground\b",
               re.IGNORECASE),
    re.compile(r"\bbatter\s+walking\s+off\b", re.IGNORECASE),
    re.compile(r"\bfielder\s+(?:celebrating|reacting|jumping|raising\s+arms)\b",
               re.IGNORECASE),
    re.compile(r"\bplayers?\s+(?:reacting|celebrating)\b", re.IGNORECASE),
    re.compile(r"\b(?:player|fielder)(?:'s)?\s+hands?\s+raised\b",
               re.IGNORECASE),
    re.compile(r"\bwicket\s+has\s+fallen\b", re.IGNORECASE),
    re.compile(r"\bbatter\s+dismissed\b", re.IGNORECASE),
    re.compile(r"\bcelebrating\s+after\s+a\s+(?:wicket|catch|shot|four|six)\b",
               re.IGNORECASE),
    re.compile(r"\bjust\s+hit\s+(?:the\s+|a\s+)?(?:four|six|boundary)\b",
               re.IGNORECASE),
]

# Fix 13: stricter post-action marker for phantom_rescue. Generic
# "player walking off" / "walking on the field" no longer qualifies —
# we require explicit wicket / four / six / catch / "helmet on ground"
# / WICKET graphic-style evidence.
HEDGE_BEFORE_PAT = re.compile(
    r"\b(?:possibly|perhaps|maybe|may\s+have|might\s+have|"
    r"could\s+(?:be|have)|appears\s+to\s+be|seems\s+to\s+be|"
    r"or\s+(?:after|before|during|perhaps|possibly|maybe)|"
    r"likely|unlikely)\s*"
    r"(?:[\w,'-]+\s+){0,5}$",
    re.IGNORECASE,
)


def strong_post_action_match(text: str):
    """Return (start, end, phrase) of a strong-post-action match that
    is NOT preceded within ~60 chars by a hedge phrase ('possibly',
    'or after', 'may have', etc.). Returns None if no qualifying match."""
    for m in STRONG_POST_ACTION_PHRASES.finditer(text):
        prefix = text[max(0, m.start() - 60): m.start()]
        if HEDGE_BEFORE_PAT.search(prefix):
            continue
        return (m.start(), m.end(), m.group(0))
    return None


STRONG_POST_ACTION_PHRASES = re.compile(
    r"\b(?:helmet\s+(?:lying\s+|on\s+)?(?:on\s+)?the\s+ground|"
    r"batsm(?:a|e)n\s+walking\s+off|"
    r"(?:fielder|player)\s+(?:celebrating|jumping|fist[-\s]?pumping|"
    r"raising\s+arms|hands\s+raised\s+above)|"
    r"wicket\s+has\s+fallen|wicket\s+fell|batsm(?:a|e)n\s+dismissed|"
    r"celebrating\s+after\s+(?:a\s+|the\s+)?(?:wicket|catch|shot|four|six)|"
    r"just\s+hit\s+(?:a\s+|the\s+)?(?:four|six|boundary)|"
    r"catching\s+the\s+ball|caught\s+(?:behind\s+|out\s*)?\b|"
    r"(?:lunges?|lunging|diving|dives)\s+(?:forward\s+)?to\s+catch|"
    r"(?:lunges?|lunging|diving|dives)\s+for\s+the\s+ball|"
    r"(?:lunges?|lunging|diving|dives)\s+on\s+the\s+ground|"
    r"(?:attempting|trying)\s+to\s+(?:catch|take\s+the\s+catch)|"
    r"(?:going\s+for|going\s+to|attempts\s+to\s+take)\s+(?:the\s+|a\s+)?catch|"
    r"(?:reach(?:ing|es)|stretches?|stretching)\s+for\s+the\s+ball|"
    r"fielder\s+(?:lunging|diving)\b|"
    r"\bWICKET\b\s+(?:graphic|overlay|text|sign)|"
    r"\b(?:FOUR|SIX)\b\s+(?:graphic|overlay|text|sign|celebration))",
    re.IGNORECASE,
)


def phantom_rescue(clusters: list[dict], all_frames: list[FrameInfo],
                   post_action_window_s: float = 3.0,
                   gap_max: int = 2) -> list[dict]:
    """Find runs of Path-C-only DELIVERY frames that fell outside any
    kept cluster (i.e., V-filter dropped them), and rescue as DELIVERY
    when post-action markers appear within post_action_window_s after
    the run end. The phantom delivery happened in the camera cut; the
    surrounding frames carry the evidence.
    """
    if not all_frames:
        return clusters
    in_cluster_t: set[float] = set()
    for c in clusters:
        for f in c["frames"]:
            in_cluster_t.add(f.t)
    n = len(all_frames)
    candidates: list[dict] = []
    i = 0
    while i < n:
        f = all_frames[i]
        if (not f.is_delivery) or (f.t in in_cluster_t):
            i += 1
            continue
        start = i
        last = i
        j = i + 1
        gap = 0
        while j < n:
            fj = all_frames[j]
            if fj.t in in_cluster_t:
                break
            if fj.is_delivery:
                last = j
                gap = 0
            else:
                gap += 1
                if gap > gap_max:
                    break
            j += 1
        run = all_frames[start:last + 1]
        delivery_paths = [x.path for x in run if x.is_delivery]
        if len(delivery_paths) >= 2 and all(p == "C" for p in delivery_paths):
            end_t = run[-1].t
            window_hit_t = None
            window_hit_phrase = None
            # Fix 14b: search both in-run and after-run frames within
            # window. A path-C delivery's own prose may describe both
            # setup and post-action (e.g. "lunges to catch the ball").
            for k in range(start, n):
                fk = all_frames[k]
                if fk.t > end_t + post_action_window_s:
                    break
                # Fix 13b: strong post-action evidence with hedge guard.
                # Skip matches preceded by "possibly" / "or after" /
                # "may have" / "appears to be" within 60 chars.
                hit = strong_post_action_match(fk.text)
                if hit is not None:
                    window_hit_t = fk.t
                    window_hit_phrase = hit[2]
                    break
            if window_hit_t is not None:
                candidates.append({
                    "start_t": run[0].t,
                    "end_t": run[-1].t,
                    "frames": run,
                    "phantom_rescued": True,
                    "post_action_at_t": window_hit_t,
                    "post_action_phrase": window_hit_phrase,
                })
        i = last + 1
    out = list(clusters) + candidates
    out.sort(key=lambda c: c["start_t"])
    return out


def merge_rescued_with_neighbors(clusters: list[dict],
                                  max_distance_s: float = 10.0) -> list[dict]:
    """Merge rescued singleton clusters with adjacent non-rescued
    clusters within max_distance_s. The closer neighbor wins; ties go
    to the previous cluster."""
    if not clusters:
        return clusters
    clusters = sorted(clusters, key=lambda c: c["start_t"])
    out: list[dict] = []
    i = 0
    while i < len(clusters):
        c = clusters[i]
        if not c.get("rescued"):
            out.append(c)
            i += 1
            continue
        prev = out[-1] if out else None
        nxt = clusters[i + 1] if i + 1 < len(clusters) else None
        prev_dist = (c["start_t"] - prev["end_t"]) if prev else float("inf")
        nxt_dist = (nxt["start_t"] - c["end_t"]) if nxt else float("inf")
        target = None
        if prev_dist <= max_distance_s and prev_dist <= nxt_dist:
            target = "prev"
        elif nxt_dist <= max_distance_s:
            target = "nxt"
        if target == "prev":
            prev["start_t"] = min(prev["start_t"], c["start_t"])
            prev["end_t"] = max(prev["end_t"], c["end_t"])
            prev["frames"] = sorted(prev["frames"] + c["frames"],
                                    key=lambda f: f.t)
            prev["merged_rescued"] = True
            i += 1
            continue
        if target == "nxt":
            merged = dict(nxt)
            merged["start_t"] = min(c["start_t"], nxt["start_t"])
            merged["end_t"] = max(c["end_t"], nxt["end_t"])
            merged["frames"] = sorted(c["frames"] + nxt["frames"],
                                      key=lambda f: f.t)
            merged["merged_rescued"] = True
            merged.pop("rescued", None)
            out.append(merged)
            i += 2
            continue
        out.append(c)
        i += 1
    return out


def rescue_high_signal_singletons(
        clusters: list[dict],
        all_frames: list[FrameInfo],
        min_signals: int = 8,
        kept_cluster_min_dist_s: float = 30.0,
        hard_window_s: float = 2.0,
) -> list[dict]:
    """Promote orphan Path A/B/D frames with very high signal density to
    single-frame clusters. Recovers deliveries that the cluster builder
    rejects because min_run=2 / gap_max=3 leaves a single high-signal
    frame stranded between non-delivery neighbors.

    Criteria for a frame to be rescued:
      1. is_delivery=True with path in {A, B, D} (Path C excluded — its
         predicate is too lax for singleton promotion).
      2. >=min_signals of {V, V_post, S, M, M2, W, K, SS, CG} fire.
      3. Frame sits >=kept_cluster_min_dist_s away from every kept
         cluster's anchor (avoids duplicating splits of the same
         delivery captured by a real cluster nearby).
      4. No HARD_REJECT frame within +/- hard_window_s seconds.
    """
    if not all_frames:
        return list(clusters)

    in_cluster_t: set[float] = set()
    kept_anchor_ts: list[float] = []
    for c in clusters:
        for f in c["frames"]:
            in_cluster_t.add(f.t)
        anchor_t = c.get("anchor_t")
        if anchor_t is None:
            anchor_obj = c.get("anchor")
            anchor_t = anchor_obj.t if anchor_obj is not None else c["start_t"]
        kept_anchor_ts.append(anchor_t)

    hard_ts = [f.t for f in all_frames if f.signals.HARD]

    rescued: list[dict] = []
    for f in all_frames:
        if f.t in in_cluster_t:
            continue
        if not f.is_delivery:
            continue
        if f.path not in ("A", "B", "D"):
            continue
        s = f.signals
        sig_count = sum([
            s.V, s.V_post, s.S, s.M, s.M2, s.W, s.K, s.SS, s.CG,
        ])
        if sig_count < min_signals:
            continue
        if any(abs(f.t - a) < kept_cluster_min_dist_s for a in kept_anchor_ts):
            continue
        if any(abs(f.t - h) <= hard_window_s for h in hard_ts):
            continue
        rescued.append({
            "start_idx": -1,
            "end_idx": -1,
            "start_t": f.t,
            "end_t": f.t,
            "frames": [f],
            "high_signal_rescued": True,
            "rescue_signal_count": sig_count,
        })

    out = list(clusters) + rescued
    out.sort(key=lambda c: c["start_t"])
    return out


def pick_anchor(cluster: dict) -> FrameInfo:
    if cluster.get("phantom_rescued"):
        delivery = [f for f in cluster["frames"] if f.is_delivery]
        return (delivery[-1] if delivery else cluster["frames"][-1])
    candidates = [f for f in cluster["frames"] if f.is_delivery]
    if not candidates:
        candidates = cluster["frames"]
    best = candidates[0]
    best_score = score_frame(best)
    best_pref = _PATH_PREF.get(best.path, 0)
    for f in candidates[1:]:
        sc = score_frame(f)
        pr = _PATH_PREF.get(f.path, 0)
        if (sc > best_score) or (sc == best_score and pr > best_pref):
            best, best_score, best_pref = f, sc, pr
    frames_sorted = sorted(cluster["frames"], key=lambda x: x.t)
    for f in frames_sorted:
        if f.t >= best.t:
            break
        if not f.signals.V:
            continue
        if not (f.signals.M2 or f.signals.W):
            continue
        if (best.t - f.t) <= 4.0:
            continue
        bridge = [g for g in frames_sorted if f.t < g.t < best.t]
        if not bridge:
            continue
        hard_in_bridge = any(g.signals.HARD for g in bridge)
        empty_in_bridge = sum(
            1 for g in bridge
            if not (g.signals.M or g.signals.W) and not g.signals.HARD
        )
        if not hard_in_bridge and empty_in_bridge <= 1:
            return f
    return best
