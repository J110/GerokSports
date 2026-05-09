"""Simulate confidence-based propagation chunker on cached frames.

Replaces v3's hard-threshold rules (4s anchor window, ≥2 frame
count, fixed cluster-merge gaps) with evidence accumulation.
Frames vote with per-label confidence scores; chunks grow via
walk-with-inertia until evidence drops below threshold.

Validates against:
1. The 19-clip emitted-fixture (precision check vs v3.1).
2. The user's over-mapped delivery timestamps (true recall on
   the 60-ball innings).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SESSION = "96b39448"
SIDECAR = ROOT.parent / "logs" / f"openscout-{SESSION}.jsonl"
META_DIR = ROOT.parent / "files" / "logs" / "deliveries" / SESSION / "auto"

# === Truth from user ==========================================

TRUTH_19_CLIPS = {
    "d001": "real",   "d002": "real",   "d003": "real",
    "d004": "trunc",  "d005": "pre",    "d006": "post",
    "d007": "trunc",  "d008": "replay", "d009": "replay",
    "d010": "replay", "d011": "replay", "d012": "replay",
    "d013": "real",   "d014": "real",   "d015": "replay",
    "d016": "replay", "d017": "replay", "d018": "real",
    "d019": "real",
}

# User's clip-to-over mapping
CLIP_OVERS = {
    "d001": (0,3), "d002": (0,6), "d003": (1,1), "d004": (1,2),
    "d005": (2,2), "d007": (2,5), "d009": (4,1), "d010": (4,5),
    "d013": (5,5), "d014": (6,4), "d018": (8,4), "d019": (10,1),
}


# === Keyword sets =============================================

STRONG_VERBS = [
    "mid-swing", "mid-air", "mid-action",
    "just released", "just bowled", "just delivered",
    "just hit", "just played", "played a shot",
    "about to release", "about to bowl",
    "follow-through", "follow through",
    "playing a shot",
    "ball in flight", "ball traveling", "ball in the air",
    "diving to catch", "diving to field",
    "leaping to catch", "leaping",
]

# Weaker action signals — include these to pick up isolated frames
WEAK_ACTION_VERBS = [
    "running", "throwing", "fielding", "diving",
    "raising arm", "arm raised",
    "swinging", "swung", "hit the ball", "hits the ball",
    "preparing to play", "preparing to hit",
    "in motion", "mid-stride",
]

WIDE_FIELD_TERMS = [
    "wide field view", "wide view", "wide shot",
    "cricket pitch with players",
    "cricket pitch with several players",
    "cricket field with players",
]

ACTOR_ROLES = ["bowler", "batter", "batsmen", "fielder",
               "fielders", "wicketkeeper", "wicket-keeper",
               "wicket keeper", "umpire"]

PITCH_TERMS = ["wicket", "wickets", "crease", "stumps", "pitch"]

REPLAY_OVERLAY_TERMS = [
    "wicket ball speed", "wicket ball ", "instant replay",
    "slow motion", "slo-mo", "stats breakdown",
]

POST_ACTION_PHRASES = [
    "post-action moment", "post action moment",
    "action has concluded", "action concluded",
    "darkened stadium", "black screen", "blurry view",
]

CROWD_PROMINENT = [
    "crowd of spectators", "large crowd in the background",
    "crowd in the background", "crowd in the foreground",
    "stadium full of spectators",
    "spectators watch", "spectators are seated",
]

CLOSE_UP_TERMS = [
    "close-up", "close up", "close shot",
    "medium shot", "medium close-up",
    "single cricket player", "close-up of a single",
    "medium shot of a single", "from behind",
]

NO_PLAYERS = ["no people visible", "no players visible",
              "title card", "static graphic"]

BRAND_KEYWORDS = ["jiohotstar", "self-serve", "tata ipl logo",
                   "sponsor", "brand"]


# === Per-frame scoring ========================================

LABELS = ["DELIVERY", "REPLAY", "AD", "DRS",
          "UMPIRE", "NON_DELIVERY"]


def _has_any(terms: list, desc: str) -> bool:
    d = desc.lower()
    return any(t in d for t in terms)


def _count_actors(desc: str) -> int:
    d = desc.lower()
    seen = set()
    for r in ACTOR_ROLES:
        if r in d:
            seen.add(r.split()[0])
    return len(seen)


def score_frame(desc: str, v2_tag: str = "") -> dict:
    """Returns confidence per label, all in [0, 1]."""
    d = (desc or "").lower()

    has_strong = _has_any(STRONG_VERBS, d)
    has_weak = _has_any(WEAK_ACTION_VERBS, d)
    has_action_any = has_strong or has_weak
    has_wide = _has_any(WIDE_FIELD_TERMS, d) or _count_actors(d) >= 2
    has_pitch = _has_any(PITCH_TERMS, d)
    has_close = _has_any(CLOSE_UP_TERMS, d)
    has_replay_ovl = _has_any(REPLAY_OVERLAY_TERMS, d)
    has_post_action = _has_any(POST_ACTION_PHRASES, d)
    has_crowd = _has_any(CROWD_PROMINENT, d)
    has_no_players = _has_any(NO_PLAYERS, d)
    has_brand = _has_any(BRAND_KEYWORDS, d)
    has_drs = any(k in d for k in
                   ("ball-tracking", "trajectory", "hawkeye",
                    "ultra-edge", "snicko", "decision review"))
    has_umpire_subj = ("the umpire" in d or "umpire is" in d
                        or "umpire raised" in d
                        or "umpire's arm" in d)
    has_signal = any(s in d for s in
                      ("raised", "outstretched", "signaling",
                       "indicating"))

    s = {l: 0.0 for l in LABELS}

    # DELIVERY — cricket invariants applied as HARD rules
    # before scoring (no point scoring delivery if invariant
    # disqualifies the frame).
    delivery_disqualified = (
        # Crowd-prominent + action = replay angle, never live
        (has_crowd and has_action_any)
        # Replay overlay text on screen — definitively replay
        or has_replay_ovl
        # v2 broadcast tag is replay/slo-mo
        or v2_tag in ("REPLAY", "SLO-MO", "TELESTRATOR",
                       "SPLIT-SCREEN")
        # Post-action phrase explicit in description
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

    # REPLAY
    if has_replay_ovl:
        s["REPLAY"] += 0.70
    if v2_tag in ("REPLAY", "SLO-MO", "TELESTRATOR",
                   "SPLIT-SCREEN"):
        s["REPLAY"] += 0.50
    if has_post_action:
        s["REPLAY"] += 0.30
    if has_crowd and has_action_any:
        s["REPLAY"] += 0.30

    # AD
    if has_brand and has_no_players:
        s["AD"] += 0.50
    if has_no_players:
        s["AD"] += 0.20

    # DRS
    if has_drs:
        s["DRS"] += 0.80

    # UMPIRE_SIGNAL
    if has_umpire_subj and has_signal:
        s["UMPIRE"] += 0.50

    # NON_DELIVERY — only when EXPLICITLY signaled. No
    # arbitrary fallback default — frames that lack signal
    # will inherit their label from the nearest confirmed
    # anchor (label propagation step in find_anchors).
    if "between deliveries" in d or "preparing" in d:
        s["NON_DELIVERY"] += 0.40
    if "standing still" in d or "walking" in d:
        s["NON_DELIVERY"] += 0.25
    if ("single cricket player" in d or "close-up" in d):
        if not has_action_any:
            s["NON_DELIVERY"] += 0.30

    # Clamp
    return {k: max(0.0, min(1.0, v)) for k, v in s.items()}


# === Walk with inertia ========================================

def find_confirmed_anchors(frames: list) -> list:
    """Return frames where the top label has clear evidence.
    Only these are 'confirmed' — uncertain frames inherit
    their label from the nearest confirmed anchor in
    propagate_labels().
    """
    anchors = []
    for i, f in enumerate(frames):
        ranked = sorted(f["score"].items(), key=lambda x: -x[1])
        top, top_v = ranked[0]
        second_v = ranked[1][1]
        if top_v >= 0.40 and (top_v - second_v) >= 0.15:
            anchors.append((i, top, top_v))
    return anchors


def propagate_labels(frames: list,
                      confirmed: list) -> list:
    """Every frame gets a label by inheriting from its
    nearest confirmed anchor (in frame index distance).
    Returns list of (idx, label, score) for every frame.
    """
    if not confirmed:
        return [(i, "NON_DELIVERY", 0.0)
                for i in range(len(frames))]

    # Pre-compute confirmed indices for fast nearest lookup
    confirmed_indices = [c[0] for c in confirmed]
    confirmed_lookup = {c[0]: c for c in confirmed}

    result = []
    j = 0  # pointer into confirmed_indices
    for i in range(len(frames)):
        if i in confirmed_lookup:
            result.append(confirmed_lookup[i])
            continue
        # Advance j so confirmed_indices[j-1] <= i <
        # confirmed_indices[j]
        while (j < len(confirmed_indices)
               and confirmed_indices[j] < i):
            j += 1
        # Find nearest: compare j-1 and j positions
        candidates = []
        if j > 0:
            candidates.append(confirmed[j - 1])
        if j < len(confirmed_indices):
            candidates.append(confirmed[j])
        # Pick by smallest index distance
        best = min(candidates, key=lambda c: abs(c[0] - i))
        # Keep label, but reduce confidence to mark
        # inheritance
        inherited_score = best[2] * 0.7
        result.append((i, best[1], inherited_score))
    return result


def find_all_anchors(frames: list) -> list:
    """Returns label per frame after propagation. Backwards
    compatible — every frame has an anchor.
    """
    confirmed = find_confirmed_anchors(frames)
    return propagate_labels(frames, confirmed)


def demote_sandwiched_anchors(anchors: list,
                                frames: list) -> list:
    """If an anchor A is between two anchors of a DIFFERENT
    label and BOTH neighbors have higher scores than A,
    demote A to the neighbor label.

    Returns updated anchors list. Iterates until stable.
    """
    while True:
        changed = False
        new_anchors = []
        for j, (idx, label, score) in enumerate(anchors):
            if j == 0 or j == len(anchors) - 1:
                new_anchors.append((idx, label, score))
                continue
            prev_idx, prev_label, prev_score = anchors[j - 1]
            next_idx, next_label, next_score = anchors[j + 1]
            # Sandwich condition: surrounded by SAME different label
            # AND both neighbors more confident
            if (prev_label == next_label
                    and prev_label != label
                    and prev_score > score
                    and next_score > score):
                # Demote: re-label this frame's score to the
                # surrounding label, with reduced confidence
                # (it's the sandwich's score, dampened)
                demoted_score = (prev_score + next_score) / 2 - 0.10
                new_anchors.append((idx, prev_label, demoted_score))
                # Also update the underlying frame's score so
                # downstream cluster-walks see the new label
                frames[idx]["score"][prev_label] = max(
                    frames[idx]["score"].get(prev_label, 0),
                    demoted_score)
                # Drop the original DELIVERY score so it can't
                # re-anchor a delivery cluster
                if label != prev_label:
                    frames[idx]["score"][label] = (
                        score - 0.30)
                changed = True
            else:
                new_anchors.append((idx, label, score))
        anchors = new_anchors
        if not changed:
            break
    return anchors


def find_anchors(frames: list) -> list:
    """Return indices of CONFIRMED DELIVERY anchors after
    sandwich-based misclassification correction.
    """
    all_anchors = find_all_anchors(frames)
    corrected = demote_sandwiched_anchors(all_anchors, frames)
    # Return only DELIVERY anchors (with reasonable score)
    return [idx for (idx, lbl, sc) in corrected
            if lbl == "DELIVERY" and sc >= 0.50]


def walk_chunk(frames: list, anchor_idx: int) -> tuple:
    """From anchor, walk both directions accumulating evidence.
    Returns (start_idx, end_idx, total_strength).
    """
    n = len(frames)
    chunk_label = "DELIVERY"
    S = frames[anchor_idx]["score"]["DELIVERY"]
    start = end = anchor_idx

    def extend(direction: int) -> int:
        nonlocal S
        i = anchor_idx
        while True:
            j = i + direction
            if j < 0 or j >= n:
                return i
            f = frames[j]
            support = f["score"]["DELIVERY"]
            dissent_top = max(v for k, v in f["score"].items()
                               if k != "DELIVERY")
            # Case A — supports
            if support >= 0.40 and dissent_top < 0.40:
                S += 0.20
                i = j
                continue
            # Case B — ambiguous, lookahead
            if support >= 0.20 and dissent_top < 0.50:
                if S >= 1.0:  # inertia
                    i = j
                    continue
                # lookahead: 2 frames in extension direction
                ks = [j + direction * k for k in (1, 2)]
                ks = [k for k in ks if 0 <= k < n]
                next_supports = [frames[k]["score"]["DELIVERY"]
                                  for k in ks]
                if sum(1 for v in next_supports if v >= 0.30) >= 1:
                    i = j
                    continue
                # boundary
                return i
            # Case C — strong dissent, lookahead 3
            if dissent_top >= 0.50 and support < 0.30:
                ks = [j + direction * k for k in (1, 2, 3)]
                ks = [k for k in ks if 0 <= k < n]
                next_dissent = sum(
                    1 for k in ks
                    if max(v for kk, v in frames[k]["score"].items()
                            if kk != "DELIVERY") >= 0.40)
                if next_dissent >= 2:
                    return i  # real boundary
                # absorb as misclassification, with penalty
                if S >= 1.5:
                    S -= 0.40
                    if S < 0.30:
                        return i
                    i = j
                    continue
                return i
            # Else: weak in both directions, stop
            return i

    end = extend(+1)
    start = extend(-1)
    return start, end, S


# === Cluster formation =========================================

def find_clusters(frames: list) -> list:
    """Returns list of (start_idx, end_idx, strength)."""
    anchors = find_anchors(frames)
    used = set()
    clusters = []
    for a in anchors:
        if a in used:
            continue
        s, e, S = walk_chunk(frames, a)
        for j in range(s, e + 1):
            used.add(j)
        clusters.append((s, e, S))
    # Sort by start, merge overlaps
    clusters.sort()
    merged = []
    for c in clusters:
        if merged and c[0] <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], c[1]),
                           merged[-1][2] + c[2])
        else:
            merged.append(list(c))
    return [(s, e, S) for s, e, S in merged]


def cluster_level_sandwich_reject(
    cluster_start: int,
    cluster_end: int,
    all_anchors: list,
    frames: list,
) -> str | None:
    """Cluster-level sandwich rule (purely structural).

    A confirmed DELIVERY cluster is REJECTED if the anchor
    immediately preceding the cluster (in the global ts-sorted
    anchor list) and the anchor immediately following the
    cluster are BOTH the same non-DELIVERY label.

    This catches multi-frame replay misclassification runs
    where individual DELIVERY anchors don't satisfy the
    per-frame sandwich (they're surrounded by other DELIVERY
    anchors) but the cluster as a whole is bracketed by REPLAY.
    """
    # Find anchors that fall WITHIN the cluster bounds
    cluster_anchor_positions = [
        i for i, (idx, _, _) in enumerate(all_anchors)
        if cluster_start <= idx <= cluster_end
    ]
    if not cluster_anchor_positions:
        return None
    first_pos = cluster_anchor_positions[0]
    last_pos = cluster_anchor_positions[-1]

    # Anchor immediately before the cluster
    prev_label = None
    if first_pos > 0:
        prev_label = all_anchors[first_pos - 1][1]
    # Anchor immediately after the cluster
    next_label = None
    if last_pos < len(all_anchors) - 1:
        next_label = all_anchors[last_pos + 1][1]

    # If both adjacent anchors are the same non-DELIVERY label,
    # the cluster is bracket-sandwiched → demote.
    if (prev_label is not None and next_label is not None
            and prev_label == next_label
            and prev_label != "DELIVERY"
            and prev_label != "NON_DELIVERY"):
        return f"cluster_sandwich_{prev_label}"

    return None


def cluster_rejection_v31(frames: list, s: int, e: int) -> str | None:
    """v3.1 cluster-level rejection rules. Returns reason if
    rejected, None if accepted.

    1. Strong replay overlay anywhere in cluster → reject
    2. Crowd-prominent frame + ≤1 strong DELIVERY frame → reject
    3. >50% close-ups + ≤1 strong DELIVERY frame → reject
    """
    cluster_frames = frames[s:e + 1]
    if not cluster_frames:
        return "empty"

    # Re-derive flags per frame from descriptions
    n_strong_delivery = 0  # DELIVERY score >= 0.5
    n_replay_strong = 0
    n_crowd = 0
    n_close = 0

    for f in cluster_frames:
        desc = f.get("desc", "").lower()
        has_crowd = _has_any(CROWD_PROMINENT, desc)
        # Strong delivery: confidence ≥ 0.5 AND not crowd-prominent
        # (crowd dominates real-action signal in scored frames)
        if f["score"]["DELIVERY"] >= 0.5 and not has_crowd:
            n_strong_delivery += 1
        # Replay overlay: explicit terms OR ANALYSIS-as-graphic
        # OR REPLAY score ≥ 0.7
        analysis_graphic = ("analysis" in desc
                             and ("graphic" in desc
                                  or "overlay" in desc
                                  or "letters" in desc))
        if (_has_any(REPLAY_OVERLAY_TERMS, desc)
                or analysis_graphic
                or f["score"]["REPLAY"] >= 0.7):
            n_replay_strong += 1
        # Crowd prominent
        if has_crowd:
            n_crowd += 1
        # Close-up
        if _has_any(CLOSE_UP_TERMS, desc) and not _has_any(
                PITCH_TERMS, desc):
            n_close += 1

    # Rule 1: any strong replay → reject
    if n_replay_strong >= 1:
        return f"v31_replay_overlay_{n_replay_strong}"

    # Rule 2: crowd-sandwich (≥1 crowd + ≤1 strong delivery)
    if n_crowd >= 1 and n_strong_delivery <= 1:
        return (f"v31_crowd_sandwich_{n_crowd}c/"
                f"{n_strong_delivery}d")

    # Rule 3: close-up dominated
    if (len(cluster_frames) > 0
            and n_close > len(cluster_frames) / 2
            and n_strong_delivery <= 1):
        return (f"v31_close_up_dominated_{n_close}/"
                f"{len(cluster_frames)}")

    return None  # Accept


# === Run on session 96b39448 ===================================

def main() -> int:
    if not SIDECAR.exists():
        print(f"ERROR: sidecar not found at {SIDECAR}")
        return 1

    raw_entries = []
    with open(SIDECAR) as f:
        for line in f:
            try:
                r = json.loads(line)
                if r.get("ts"):
                    raw_entries.append(r)
            except Exception:
                pass
    raw_entries.sort(key=lambda r: r["ts"])

    # Score every frame
    frames = []
    for r in raw_entries:
        desc = r.get("raw_text") or ""
        frames.append({
            "ts": r["ts"],
            "desc": desc[:200],
            "score": score_frame(desc, r.get("v2_broadcast_tag", "")),
            "frame_class": r.get("frame_class", "?"),
        })

    print(f"Loaded {len(frames)} Scout frames")

    # Find anchors
    anchors = find_anchors(frames)
    print(f"DELIVERY anchors found: {len(anchors)}")

    # Build clusters
    raw_clusters = find_clusters(frames)
    print(f"Raw DELIVERY clusters formed: {len(raw_clusters)}")

    # Coalesce nearby clusters (within 5s of each other) so v31
    # rejection sees full surrounding context — a replay overlay
    # frame 2s outside a sub-cluster should still invalidate that
    # cluster.
    coalesced_groups = []  # list of (start_idx, end_idx, members)
    for c in raw_clusters:
        s, e, S = c
        if not coalesced_groups:
            coalesced_groups.append([s, e, [c]])
            continue
        prev = coalesced_groups[-1]
        prev_end_ts = frames[prev[1]]["ts"]
        curr_start_ts = frames[s]["ts"]
        if curr_start_ts - prev_end_ts <= 5.0:
            prev[1] = max(prev[1], e)
            prev[2].append(c)
        else:
            coalesced_groups.append([s, e, [c]])

    # Apply v3.1 cluster-level rejection on coalesced ranges
    # AND cluster-level structural sandwich (purely positional,
    # no time windows).
    all_anchors_global = find_all_anchors(frames)
    clusters = []
    rejection_reasons = {}
    for grp_s, grp_e, members in coalesced_groups:
        # First: cluster-level structural sandwich check
        sandwich_reason = cluster_level_sandwich_reject(
            grp_s, grp_e, all_anchors_global, frames)
        if sandwich_reason is not None:
            rejection_reasons[sandwich_reason] = (
                rejection_reasons.get(sandwich_reason, 0)
                + len(members))
            continue
        # Second: v3.1 frame-content checks
        reason = cluster_rejection_v31(frames, grp_s, grp_e)
        if reason is None:
            for c in members:
                clusters.append(c)
        else:
            rejection_reasons[reason] = rejection_reasons.get(
                reason, 0) + len(members)

    print(f"After v3.1 rejection (coalesced): {len(clusters)} "
          f"clusters from {len(raw_clusters)} raw "
          f"(rejected {len(raw_clusters) - len(clusters)})")
    if rejection_reasons:
        print(f"  Rejection reasons:")
        for r, c in sorted(rejection_reasons.items(),
                            key=lambda x: -x[1]):
            print(f"    {r}: {c}")

    # Print each cluster with timing
    print()
    print(f"{'Cluster':<8} {'Start ts':<14} {'End ts':<14} "
          f"{'Dur':<6} {'Strength':<10} {'Anchors'}")
    print("-" * 80)
    for i, (s, e, S) in enumerate(clusters):
        ts_s = frames[s]["ts"]
        ts_e = frames[e]["ts"]
        n_in = e - s + 1
        print(f"c{i+1:<7} {ts_s:.0f}    {ts_e:.0f}    "
              f"{ts_e - ts_s:<6.1f} {S:<10.2f} {n_in}")

    # ============== PRECISION ON 19-CLIP FIXTURE ==============
    print()
    print("=" * 80)
    print("PRECISION CHECK against user-labeled 19-clip fixture")
    print("=" * 80)

    # For each user-labeled clip, check if it overlaps with any
    # confidence cluster. ACCEPT if overlap; REJECT if not.
    correct = 0
    fp_real_rejected = []
    fp_replay_accepted = []
    pre_post_accepted = []

    for clip_id, truth in TRUTH_19_CLIPS.items():
        meta_path = META_DIR / clip_id / "metadata.json"
        if not meta_path.exists():
            continue
        m = json.loads(meta_path.read_text())
        clip_s, clip_e = m["start_ts"], m["end_ts"]

        # Does any cluster overlap this clip's window?
        accepted = False
        for s, e, S in clusters:
            ts_s = frames[s]["ts"]
            ts_e = frames[e]["ts"]
            if ts_s <= clip_e and ts_e >= clip_s:
                accepted = True
                break

        verdict = "ACCEPT" if accepted else "REJECT"
        expected = "ACCEPT" if truth in ("real", "trunc") else "REJECT"

        if verdict == expected:
            correct += 1
        elif truth in ("real", "trunc"):
            fp_real_rejected.append(clip_id)
        elif truth == "replay":
            fp_replay_accepted.append(clip_id)
        elif truth in ("pre", "post"):
            pre_post_accepted.append(clip_id)

        match = "✓" if verdict == expected else "✗"
        print(f"  {clip_id} {truth:<7} {verdict:<8} {match}")

    n_real = sum(1 for t in TRUTH_19_CLIPS.values()
                  if t in ("real", "trunc"))
    n_tp = n_real - len(fp_real_rejected)
    n_fp = len(fp_replay_accepted) + len(pre_post_accepted)
    if n_tp + n_fp > 0:
        precision_19 = 100.0 * n_tp / (n_tp + n_fp)
    else:
        precision_19 = 0.0
    recall_19 = 100.0 * n_tp / n_real if n_real > 0 else 0.0
    print(f"\nFixture accuracy: {correct}/{len(TRUTH_19_CLIPS)} "
          f"({100*correct/len(TRUTH_19_CLIPS):.1f}%)")
    print(f"Fixture precision: {n_tp}/{n_tp+n_fp} = {precision_19:.1f}%")
    print(f"Fixture recall:    {n_tp}/{n_real} = {recall_19:.1f}%")

    # ============== TRUE RECALL ON 60-BALL INNINGS ==============
    print()
    print("=" * 80)
    print("TRUE RECALL on innings (~60 balls)")
    print("=" * 80)

    # First and last labeled deliveries give us the time range
    labeled_clip_ts = []
    for clip_id, (over, ball) in CLIP_OVERS.items():
        meta_path = META_DIR / clip_id / "metadata.json"
        if meta_path.exists():
            m = json.loads(meta_path.read_text())
            labeled_clip_ts.append((over * 6 + ball, m["start_ts"]))

    labeled_clip_ts.sort()
    first_ball = labeled_clip_ts[0][0]   # ball # of d001
    last_ball = labeled_clip_ts[-1][0]   # ball # of d019
    first_ts = labeled_clip_ts[0][1]
    last_ts = labeled_clip_ts[-1][1]

    # Each ball ~ (last_ts - first_ts) / (last_ball - first_ball)
    ball_count = last_ball - first_ball + 1
    avg_ball_dur = (last_ts - first_ts) / max(last_ball - first_ball, 1)
    print(f"First labeled ball: #{first_ball} at ts={first_ts:.0f}")
    print(f"Last  labeled ball: #{last_ball} at ts={last_ts:.0f}")
    print(f"Ball range: {ball_count} balls over "
          f"{last_ts - first_ts:.0f}s "
          f"(avg {avg_ball_dur:.0f}s/ball)")

    # Count clusters within the labeled time range
    clusters_in_range = sum(
        1 for s, e, _ in clusters
        if first_ts <= frames[s]["ts"] <= last_ts
    )
    print(f"\nConfidence chunker clusters in this range: "
          f"{clusters_in_range}")
    print(f"Estimated balls in range: {ball_count}")
    print(f"Estimated true recall: "
          f"{100*clusters_in_range/ball_count:.1f}%")
    print(f"  (capped at 100 — multiple clusters per ball "
          f"would inflate)")

    # Compare to baseline
    print()
    print(f"Baseline (rule-based v3.1): emitted 19 clips, "
          f"true recall ~20%")
    print(f"Confidence chunker:         {clusters_in_range} clusters, "
          f"true recall ~{100*min(clusters_in_range, ball_count)/ball_count:.0f}%")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
