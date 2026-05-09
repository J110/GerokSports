"""Validate proposed replay-filter rules against cached open_desc data.

Runs proposed v3.1 chunker rules on every frame in 19 cached
`auto/dNNN` clips from session 96b39448, aggregates per-clip
verdicts, and compares to user-provided truth labels.

Goal: confirm the new rules push precision from 47% to ≥75% on
the existing replay sample before shipping to live pipeline.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SESSION = "96b39448"
SIDECAR = ROOT.parent / "logs" / f"openscout-{SESSION}.jsonl"
META_DIR = ROOT.parent / "files" / "logs" / "deliveries" / SESSION / "auto"

TRUTH = {
    "d001": "real",   "d002": "real",   "d003": "real",
    "d004": "trunc",  "d005": "pre",    "d006": "post",
    "d007": "trunc",  "d008": "replay", "d009": "replay",
    "d010": "replay", "d011": "replay", "d012": "replay",
    "d013": "real",   "d014": "real",   "d015": "replay",
    "d016": "replay", "d017": "replay", "d018": "real",
    "d019": "real",
}

# === Rule constants ============================================

STRONG_DELIVERY_VERBS = [
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
]
ACTION_VERBS = STRONG_DELIVERY_VERBS

# Cricket-pitch context — when present alongside an actor and
# a STRONG verb, lets a closer framing still count as delivery.
PITCH_CONTEXT_TERMS = [
    "wicket", "wickets", "crease", "stumps", "pitch",
]

# Crowd-as-primary-subject — a strong replay indicator. Real
# wide-field broadcast deliveries virtually never describe the
# crowd as part of the scene; replays (especially boundary /
# wicket replays from low or behind-batter angles) frequently
# do. See validation memo (this file's docstring).
CROWD_PROMINENT_TERMS = [
    "crowd of spectators",
    "large crowd in the background",
    "crowd in the background",
    "crowd in the foreground",
    "stadium full of spectators",
    "spectators watch",
    "spectators are seated",
    "crowd of fans",
]

WIDE_FIELD_TERMS = [
    "wide field view", "wide view", "wide shot",
    "cricket pitch with players positioned",
    "cricket pitch with several players",
    "cricket pitch with players",
    "wide field of a cricket",
]

# Multi-actor: requires mentions of 2+ distinct role tokens
ACTOR_ROLES = [
    "bowler", "batter", "batsmen", "fielder", "fielders",
    "wicketkeeper", "wicket-keeper", "wicket keeper",
    "umpire",
]

# Replay-specific overlay text — Scout transcribes these literally
REPLAY_OVERLAY_TERMS = [
    "WICKET BALL SPEED", "WICKET BALL",
    "ANALYSIS",  # specifically the graphic, distinguishable in
                 # context — see _has_replay_overlay
    "INSTANT REPLAY", "REPLAY ", "SLOW MOTION", "SLO-MO",
    "STATS BREAKDOWN",
]

POST_ACTION_PHRASES = [
    "post-action moment", "post action moment",
    "action has concluded", "action concluded",
    "moment after the action",
    "appears to be a break",
    "darkened stadium", "darkened", "black screen",
    "blurry view", "minimal graphical overlays",
]

# Close-up / medium-shot framing markers
CLOSE_UP_TERMS = [
    "close-up", "close up", "close shot",
    "medium shot", "medium close-up", "medium close up",
    "single cricket player", "single player",
    "close-up of a", "close-up shot",
    "waist up", "from the waist", "lower body",
    "legs and feet", "from behind",
]


# === Per-frame scoring =========================================

def _lower(s: str | None) -> str:
    return (s or "").lower()


def _has_action_verb(desc: str) -> bool:
    d = _lower(desc)
    return any(v in d for v in ACTION_VERBS)


def _has_wide_field(desc: str) -> bool:
    d = _lower(desc)
    if any(t in d for t in WIDE_FIELD_TERMS):
        return True
    # Multi-actor: 2+ distinct role tokens
    roles_seen = set()
    for r in ACTOR_ROLES:
        if r in d:
            roles_seen.add(r.split()[0])
    return len(roles_seen) >= 2


def _has_pitch_context(desc: str) -> bool:
    """Cricket-specific objects in scene — wicket, crease, stumps."""
    d = _lower(desc)
    return any(t in d for t in PITCH_CONTEXT_TERMS)


def _has_crowd_prominent(desc: str) -> bool:
    """Crowd-as-subject. Strong replay indicator."""
    d = _lower(desc)
    return any(t in d for t in CROWD_PROMINENT_TERMS)


# Module-level alias so decide_clip can reach it
_has_crowd_prominent_module = _has_crowd_prominent


def _has_replay_overlay(desc: str) -> bool:
    """Replay-specific text overlays. ANALYSIS only counts when
    described as a 'graphic' or 'overlay' — avoid false-positives
    on commentary using the word 'analysis'.
    """
    d = _lower(desc)
    for term in ("wicket ball speed", "wicket ball ",
                 "instant replay", "slow motion", "slo-mo",
                 "stats breakdown"):
        if term in d:
            return True
    # ANALYSIS as graphic
    if "analysis" in d and ("graphic" in d or "overlay" in d
                            or "letters" in d):
        return True
    return False


def _has_post_action_phrase(desc: str) -> bool:
    d = _lower(desc)
    return any(p in d for p in POST_ACTION_PHRASES)


def _has_close_up(desc: str) -> bool:
    d = _lower(desc)
    return any(t in d for t in CLOSE_UP_TERMS)


def _is_single_player_focus(desc: str) -> bool:
    """Frame is dominated by a single player, no multi-actor setup."""
    d = _lower(desc)
    if any(t in d for t in
           ("close-up of a single", "single cricket player",
            "close-up shot of a single", "medium shot of a single",
            "medium shot of a cricket player")):
        return True
    # Multi-actor present overrides single-player
    roles_seen = set()
    for r in ACTOR_ROLES:
        if r in d:
            roles_seen.add(r.split()[0])
    if len(roles_seen) >= 2:
        return False
    # Single role mentioned + close-up framing
    if _has_close_up(desc) and len(roles_seen) <= 1:
        return True
    return False


# === Per-frame label ===========================================

def label_frame_v31(desc: str, v2_tag: str = "") -> str:
    """Returns one of: DELIVERY_ACTION, REPLAY, NON_DELIVERY,
    or PRE_POST.

    DELIVERY_ACTION requires ALL of:
      (a) wide-field framing OR multi-actor mention
      (b) action verb
      (c) no replay-overlay text
      (d) no post-action phrase
      (e) not single-player close-up framing

    REPLAY fires when any replay indicator is present.
    """
    if _has_replay_overlay(desc):
        return "REPLAY"
    if v2_tag in ("REPLAY", "SLO-MO", "TELESTRATOR", "SPLIT-SCREEN"):
        return "REPLAY"

    if _has_post_action_phrase(desc):
        return "REPLAY"  # post-action descriptions are usually
                          # part of replay sequences

    has_action = _has_action_verb(desc)
    has_wide = _has_wide_field(desc)
    has_pitch_ctx = _has_pitch_context(desc)
    is_close = _is_single_player_focus(desc)
    has_crowd = _has_crowd_prominent(desc)

    # Crowd-prominent + action verb = replay (cricket invariant)
    if has_crowd and has_action:
        return "REPLAY_LEAN"

    # DELIVERY: strong verb + (wide field OR cricket-pitch context)
    # AND not close-up framing
    if has_action and (has_wide or has_pitch_ctx) and not is_close:
        return "DELIVERY_ACTION"

    if is_close:
        return "REPLAY_LEAN"

    if has_action and not has_wide and not has_pitch_ctx:
        return "PRE_POST"

    return "NON_DELIVERY"


# === Cluster-level decision ====================================

def decide_clip(frames: list[dict]) -> tuple[str, str]:
    """Aggregate per-frame labels into ACCEPT / REJECT verdict.

    Returns (verdict, reason).
    """
    labels = [label_frame_v31(f.get("raw_text") or "",
                              f.get("v2_broadcast_tag", ""))
              for f in frames]

    # Hard reject: any REPLAY-strong frame
    if "REPLAY" in labels:
        idx = labels.index("REPLAY")
        return "REJECT", f"replay_signal@{idx}"

    # Reject if no DELIVERY_ACTION at all (means cluster has only
    # close-ups, pre/post action, or non-delivery moments)
    n_delivery = sum(1 for l in labels if l == "DELIVERY_ACTION")
    if n_delivery == 0:
        return "REJECT", "no_delivery_frame"

    # Reject if cluster is dominated by close-ups (>50%) AND has
    # only weak DELIVERY_ACTION evidence — replays that happen
    # to include one wide field shot still get rejected
    n_close = sum(1 for l in labels if l == "REPLAY_LEAN")
    if n_close > len(labels) // 2 and n_delivery == 1:
        return "REJECT", f"close_up_dominated_{n_close}/{len(labels)}"

    # Reject if cluster has ≥1 crowd-prominent frame and only
    # 1 DELIVERY frame — single delivery sandwiched between
    # crowd shots = replay of a prior moment
    n_crowd = sum(1 for f in frames
                  if _has_crowd_prominent(f.get("raw_text") or ""))
    if n_crowd >= 1 and n_delivery <= 1:
        return "REJECT", f"crowd_sandwich_{n_crowd}c/{n_delivery}d"

    return "ACCEPT", f"delivery_frames={n_delivery}"


# === Run on all 19 clips =======================================

def main() -> int:
    if not SIDECAR.exists():
        print(f"ERROR: sidecar not found at {SIDECAR}")
        return 1

    all_entries = []
    with open(SIDECAR) as f:
        for line in f:
            try:
                r = json.loads(line)
                if r.get("ts"):
                    all_entries.append(r)
            except Exception:
                pass
    all_entries.sort(key=lambda r: r["ts"])

    # Per-clip processing
    print("=" * 78)
    print(f"{'Clip':<8} {'Truth':<8} {'Verdict':<10} {'Reason':<28} "
          f"{'Match'}")
    print("=" * 78)

    correct = 0
    fp_real_rejected = []  # rejected real deliveries (precision penalty)
    fp_replay_accepted = []  # accepted replays
    truth_class_counts = {}
    verdict_class_counts = {}

    for clip_id in sorted(TRUTH.keys()):
        truth = TRUTH[clip_id]
        meta_path = META_DIR / clip_id / "metadata.json"
        if not meta_path.exists():
            print(f"{clip_id:<8} MISSING metadata")
            continue
        m = json.loads(meta_path.read_text())
        s, e = m["start_ts"], m["end_ts"]
        frames = [r for r in all_entries
                  if s - 0.5 <= r["ts"] <= e + 0.5]

        verdict, reason = decide_clip(frames)

        # Match: ACCEPT for real/trunc, REJECT for everything else
        if truth in ("real", "trunc"):
            expected = "ACCEPT"
        else:  # pre / post / replay
            expected = "REJECT"

        match = "✓" if verdict == expected else "✗"
        if verdict == expected:
            correct += 1
        elif truth in ("real", "trunc") and verdict == "REJECT":
            fp_real_rejected.append(clip_id)
        elif truth == "replay" and verdict == "ACCEPT":
            fp_replay_accepted.append(clip_id)

        truth_class_counts[truth] = truth_class_counts.get(truth, 0) + 1

        print(f"{clip_id:<8} {truth:<8} {verdict:<10} "
              f"{reason:<28} {match}")

    print("=" * 78)
    print(f"\nAccuracy: {correct}/{len(TRUTH)} = "
          f"{100.0 * correct / len(TRUTH):.1f}%")

    # Precision/recall on "real-or-trunc" class
    n_real = sum(1 for t in TRUTH.values() if t in ("real", "trunc"))
    n_replay = sum(1 for t in TRUTH.values() if t == "replay")
    n_pre_post = sum(1 for t in TRUTH.values() if t in ("pre", "post"))

    n_tp = n_real - len(fp_real_rejected)
    n_fp = len(fp_replay_accepted)  # plus pre/post if accepted
    pre_post_accepted = []
    for cid, t in TRUTH.items():
        if t in ("pre", "post"):
            meta_path = META_DIR / cid / "metadata.json"
            if not meta_path.exists():
                continue
            m = json.loads(meta_path.read_text())
            s, e = m["start_ts"], m["end_ts"]
            frames = [r for r in all_entries
                      if s - 0.5 <= r["ts"] <= e + 0.5]
            v, _ = decide_clip(frames)
            if v == "ACCEPT":
                pre_post_accepted.append(cid)
    n_fp += len(pre_post_accepted)

    print(f"\nReal/trunc deliveries: {n_real}")
    print(f"  Accepted: {n_tp}  Rejected (FN): "
          f"{len(fp_real_rejected)} {fp_real_rejected}")
    print(f"Replays:               {n_replay}")
    print(f"  Rejected: {n_replay - len(fp_replay_accepted)}  "
          f"Accepted (FP): {len(fp_replay_accepted)} "
          f"{fp_replay_accepted}")
    print(f"Pre/post:              {n_pre_post}")
    print(f"  Rejected: {n_pre_post - len(pre_post_accepted)}  "
          f"Accepted (FP): {len(pre_post_accepted)} "
          f"{pre_post_accepted}")

    n_accepted = n_tp + n_fp
    if n_accepted > 0:
        precision = 100.0 * n_tp / n_accepted
    else:
        precision = 0.0
    if n_real > 0:
        recall = 100.0 * n_tp / n_real
    else:
        recall = 0.0

    print(f"\nPrecision: {n_tp}/{n_accepted} = {precision:.1f}%")
    print(f"Recall:    {n_tp}/{n_real} = {recall:.1f}%")

    print("\nBaseline (current chunker on this sample): 47% precision")
    print(f"v3.1 rules:                                {precision:.1f}% "
          f"precision  ({'IMPROVED' if precision > 47 else 'NO CHANGE'})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
