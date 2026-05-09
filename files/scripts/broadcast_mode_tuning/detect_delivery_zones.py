#!/usr/bin/env python3
"""Detect cricket delivery zones from Scout sidecar data via binary classification + smoothing + boundary detection."""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LOGS_DIR = REPO_ROOT / "logs"

WINDOW_SECONDS = 300.0

ACTION_VERBS = [
    "mid-swing", "mid-air", "mid-action", "mid-stride",
    "running", "running in", "running between", "sprinting",
    "bowling", "delivering", "releasing",
    "just released", "just bowled", "just delivered",
    "follow-through",
    "playing a shot", "preparing to play", "preparing to hit",
    "preparing to bowl", "preparing to bat",
    "diving", "leaping", "catching",
    "throwing", "fielding", "swinging",
    "ball in flight", "ball traveling",
]

CRICKET_ROLES = [
    "bowler", "batter", "batsman", "batsmen",
    "fielder", "fielders",
    "wicketkeeper", "wicket-keeper", "wicket keeper",
    "umpire",
]

PLURAL_ROLE_TERMS = [
    "fielders", "batters", "batsmen", "bowlers", "wicketkeepers",
]

X_PLAYERS_RE = re.compile(
    r"\b(two|three|four|five|six|seven|eight|nine|several|multiple|many|some)\s+players\b",
    re.IGNORECASE,
)

THE_PLAYER_TERMS = ["the player", "another player", "second player", "third player"]

WIDE_FIELD_TERMS = [
    "wide field view", "wide view",
    "cricket pitch with players", "cricket pitch with several players",
    "cricket field with players", "cricket pitch and surrounding",
]

TEAM_ABBREVS = ["DC", "CSK", "MI", "RCB", "KKR", "RR", "PBKS", "LSG", "GT", "SRH"]
TEAM_FULL = [
    "delhi capitals", "chennai super kings", "mumbai indians",
    "royal challengers bangalore", "royal challengers bengaluru",
    "royal challengers",
    "kolkata knight riders", "knight riders",
    "rajasthan royals", "punjab kings",
    "lucknow super giants", "super giants",
    "gujarat titans", "sunrisers hyderabad",
    "capitals", "super kings", "indians", "challengers",
    "royals", "kings", "titans", "sunrisers",
]
WEAK_INFO_PATTERNS = [
    re.compile(r"tata\s+ipl", re.IGNORECASE),
    re.compile(r"\bmatch\s+\d+\b", re.IGNORECASE),
    re.compile(r"arun\s+jaitley\s+stadium", re.IGNORECASE),
    re.compile(r"ipl\s+\d{4}", re.IGNORECASE),
    re.compile(r"jiohotstar", re.IGNORECASE),
]

REPLAY_OVERLAY_TERMS = [
    "wicket ball speed", "instant replay", "ball speeds after",
    "slow motion", "slo-mo",
    "darkened stadium", "blurry view",
]
POST_ACTION_SOFT = [
    "post-action moment", "action has concluded",
]
CROWD_TERMS = [
    "crowd of spectators", "large crowd in the background",
    "stadium full of spectators", "spectators watch", "crowd in the foreground",
]
UNUSUAL_ANGLE_TERMS = [
    "foot-level", "ground-level", "from below",
    "low-angle replay", "ground level replay",
]

SCORE_RE = re.compile(r"\b\d{1,3}\s*[-/]\s*\d{1,2}\b")
OVER_RE = re.compile(r"\(\d{1,2}\.\d\)")
BATTER_STAT_RE = re.compile(r"\b\d{1,3}\s*\(\s*\d{1,3}\s*\)")
BOWLER_FIG_RE = re.compile(r"\b\d{1,2}\s*-\s*\d{1,3}\s*\(\s*\d{1,2}(?:\.\d)?\s*\)")
ANALYSIS_RE = re.compile(r"analysis", re.IGNORECASE)
ANALYSIS_GFX_RE = re.compile(r"graphic|letters|overlay", re.IGNORECASE)


@dataclass
class Frame:
    ts: float
    rel_t: float
    text: str
    is_delivery: bool = False
    smoothed: bool = False
    reason: str = ""
    is_replay_hard: bool = False
    is_crowd_dominant: bool = False
    is_unusual_angle: bool = False
    has_action_verb: bool = False
    has_multi_actor: bool = False
    has_wide_field: bool = False
    has_strong_score: bool = False
    has_weak_info: bool = False
    roles_seen: tuple[str, ...] = ()
    multi_actor_source: str = "none"
    plural_matches: tuple[str, ...] = ()
    x_players_match: str = ""
    the_player_count: int = 0
    path: str = "none"


def has_action_verb(text: str) -> bool:
    low = text.lower()
    return any(term in low for term in ACTION_VERBS)


def roles_in(text: str) -> tuple[str, ...]:
    low = text.lower()
    seen = set()
    for role in CRICKET_ROLES:
        if re.search(rf"\b{re.escape(role)}\b", low):
            seen.add(role)
    return tuple(sorted(seen))


def multi_actor_evidence(text: str) -> dict:
    """Return diagnostics + source for has_multi_actor."""
    low = text.lower()
    roles = roles_in(text)
    plural = tuple(t for t in PLURAL_ROLE_TERMS if t in low)
    m = X_PLAYERS_RE.search(text)
    x_players = m.group(0) if m else ""
    the_player_count = sum(low.count(t) for t in THE_PLAYER_TERMS)
    if len(roles) >= 2:
        source = "named_roles"
    elif plural:
        source = "plural"
    elif x_players:
        source = "x_players"
    elif the_player_count >= 2:
        source = "the_player_count"
    else:
        source = "none"
    return {
        "is_multi": source != "none",
        "source": source,
        "roles": roles,
        "plural": plural,
        "x_players": x_players,
        "the_player_count": the_player_count,
    }


def has_multi_actor(text: str) -> bool:
    return multi_actor_evidence(text)["is_multi"]


def has_wide_field(text: str) -> bool:
    low = text.lower()
    return any(term in low for term in WIDE_FIELD_TERMS)


# Backwards-compat: pre-iteration-4 callers used has_action for the
# combined verbs+roles signal. Map to the new verbs-only signal.
has_action = has_action_verb


def has_strong_score(text: str) -> bool:
    """Live-play scoreboard signals: numeric score / over / batter stat / bowler figures / team abbreviation."""
    if SCORE_RE.search(text) or OVER_RE.search(text) or BATTER_STAT_RE.search(text):
        return True
    if BOWLER_FIG_RE.search(text):
        return True
    if any(re.search(rf"\b{abbr}\b", text) for abbr in TEAM_ABBREVS):
        return True
    return False


def has_weak_info(text: str) -> bool:
    """Informational broadcast watermarks (team full names, match info, channel branding)."""
    low = text.lower()
    if any(name in low for name in TEAM_FULL):
        return True
    if any(p.search(text) for p in WEAK_INFO_PATTERNS):
        return True
    return False


# Backwards-compat alias for callers still using the pre-iteration-3 name.
has_scoreboard = has_strong_score


def is_not_delivery(text: str) -> tuple[bool, str]:
    low = text.lower()
    for term in REPLAY_OVERLAY_TERMS:
        if term in low:
            return True, f"replay-overlay:{term}"
    if ANALYSIS_RE.search(text) and ANALYSIS_GFX_RE.search(text):
        return True, "analysis-as-graphic"
    for term in CROWD_TERMS:
        if term in low:
            return True, f"crowd:{term}"
    for term in UNUSUAL_ANGLE_TERMS:
        if term in low:
            return True, f"unusual-angle:{term}"
    return False, ""


def classify(text: str) -> tuple[bool, str]:
    """Three-path DELIVERY classifier.

    Path A: action_verb + strong_score (live-play digits / abbrevs)
    Path B: action_verb + multi_actor + wide_field + weak_info
    Path C: strong_score + wide_field + multi_actor (no verb required;
            posture-tolerant fallback for live wide-field setups)
    Hard rejects (replay overlay, crowd dominant, unusual angle) override
    all paths.
    """
    nd, why = is_not_delivery(text)
    if nd:
        return False, why
    av = has_action_verb(text)
    strong = has_strong_score(text)
    multi = has_multi_actor(text)
    wide = has_wide_field(text)
    weak = has_weak_info(text)
    if av and strong:
        return True, "path-a:action+strong-score"
    if av and multi and wide and weak:
        return True, "path-b:action+multi-actor+wide+weak"
    if strong and wide and multi and weak:
        return True, "path-c:strong-score+wide+multi-actor+weak"
    missing = []
    if not av or not strong:
        a_missing = []
        if not av:
            a_missing.append("action-verb")
        if not strong:
            a_missing.append("strong-score")
        missing.append("path-a[" + ",".join(a_missing) + "]")
    if not (av and multi and wide and weak):
        b_missing = []
        if not av:
            b_missing.append("action-verb")
        if not multi:
            b_missing.append("multi-actor")
        if not wide:
            b_missing.append("wide-field")
        if not weak:
            b_missing.append("weak-info")
        missing.append("path-b[" + ",".join(b_missing) + "]")
    if not (strong and wide and multi and weak):
        c_missing = []
        if not strong:
            c_missing.append("strong-score")
        if not wide:
            c_missing.append("wide-field")
        if not multi:
            c_missing.append("multi-actor")
        if not weak:
            c_missing.append("weak-info")
        missing.append("path-c[" + ",".join(c_missing) + "]")
    return False, "missing:" + "+".join(missing)


def categorize_signals(text: str) -> tuple[bool, bool, bool]:
    """Return (is_replay_hard, is_crowd_dominant, is_unusual_angle)."""
    nd, why = is_not_delivery(text)
    if not nd:
        return False, False, False
    is_replay_hard = why.startswith(("replay-overlay", "analysis-as-graphic"))
    is_crowd_dominant = why.startswith("crowd")
    is_unusual_angle = why.startswith("unusual-angle")
    return is_replay_hard, is_crowd_dominant, is_unusual_angle


def annotate(frame: Frame) -> None:
    frame.is_delivery, frame.reason = classify(frame.text)
    (frame.is_replay_hard, frame.is_crowd_dominant,
     frame.is_unusual_angle) = categorize_signals(frame.text)
    frame.has_action_verb = has_action_verb(frame.text)
    frame.has_wide_field = has_wide_field(frame.text)
    frame.has_strong_score = has_strong_score(frame.text)
    frame.has_weak_info = has_weak_info(frame.text)

    ev = multi_actor_evidence(frame.text)
    frame.has_multi_actor = ev["is_multi"]
    frame.multi_actor_source = ev["source"]
    frame.roles_seen = ev["roles"]
    frame.plural_matches = ev["plural"]
    frame.x_players_match = ev["x_players"]
    frame.the_player_count = ev["the_player_count"]

    if frame.reason.startswith("path-a"):
        frame.path = "A"
    elif frame.reason.startswith("path-b"):
        frame.path = "B"
    elif frame.reason.startswith("path-c"):
        frame.path = "C"
    else:
        frame.path = "none"
    frame.smoothed = frame.is_delivery


def pick_sidecar(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    candidates = []
    for p in glob.glob(str(LOGS_DIR / "openscout-*.jsonl")):
        path = Path(p)
        try:
            with open(path) as f:
                first = f.readline()
                if not first:
                    continue
                t0 = json.loads(first)["ts"]
            with open(path, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - 4096))
                tail = f.read().splitlines()
            t_last = None
            for line in reversed(tail):
                try:
                    t_last = json.loads(line)["ts"]
                    break
                except Exception:
                    continue
            if t_last is None:
                continue
            if (t_last - t0) >= WINDOW_SECONDS:
                candidates.append((path.stat().st_mtime, path))
        except Exception:
            continue
    if not candidates:
        sys.exit("No sidecar covers >= 300s")
    candidates.sort(reverse=True)
    return candidates[0][1]


def load_frames(path: Path) -> list[Frame]:
    frames: list[Frame] = []
    t0 = None
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            ts = d.get("ts")
            text = d.get("raw_text") or d.get("open_desc") or ""
            if ts is None or not text:
                continue
            if t0 is None:
                t0 = ts
            rel = ts - t0
            if rel > WINDOW_SECONDS:
                break
            frames.append(Frame(ts=ts, rel_t=rel, text=text))
    return frames


def smooth(frames: list[Frame]) -> None:
    """Identity pre-pass: per-frame classification stands; merge is done in detect_blocks."""
    for f in frames:
        f.smoothed = f.is_delivery


def detect_blocks(frames: list[Frame], gap_max: int = 6,
                  min_block_s: float = 3.0) -> list[tuple[int, int]]:
    """Pass-2 distance-aware merge + Pass-3 min-duration filter.

    Two adjacent DELIVERY runs separated by <=gap_max NOT_DELIVERY frames
    merge into one block, *unless* any gap frame carries is_replay_hard or
    is_crowd_dominant. Blocks shorter than min_block_s seconds are dropped.
    All frames inside a kept block (including absorbed gap frames) are
    marked smoothed=True.
    """
    n = len(frames)
    raw: list[tuple[int, int]] = []

    # Pass 2: walk frames, accumulate (start, last_d) blocks honoring gap rule.
    i = 0
    while i < n:
        if not frames[i].is_delivery:
            i += 1
            continue
        block_start = i
        last_d = i
        j = i + 1
        gap_run_start = -1
        while j < n:
            f = frames[j]
            if f.is_delivery:
                last_d = j
                gap_run_start = -1
                j += 1
                continue
            # NOT_DELIVERY frame.
            if f.is_replay_hard or f.is_crowd_dominant or f.is_unusual_angle:
                break
            if gap_run_start == -1:
                gap_run_start = j
            if (j - gap_run_start + 1) > gap_max:
                break
            j += 1
        raw.append((block_start, last_d))
        i = last_d + 1

    # Pass 3: filter by min duration; promote absorbed gap frames to smoothed.
    out: list[tuple[int, int]] = []
    for a, b in raw:
        if frames[b].rel_t - frames[a].rel_t >= min_block_s:
            for k in range(a, b + 1):
                frames[k].smoothed = True
            out.append((a, b))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sidecar", help="explicit sidecar path; auto-picks if omitted")
    ap.add_argument("--debug-non-deliveries", action="store_true",
                    help="print classification reason for blocks that may not be deliveries")
    args = ap.parse_args()

    sidecar = pick_sidecar(args.sidecar)
    print(f"Sidecar: {sidecar}")

    frames = load_frames(sidecar)
    if not frames:
        sys.exit("No frames loaded")
    print(f"Loaded {len(frames)} frames covering {frames[-1].rel_t:.1f}s")

    for f in frames:
        f.is_delivery, f.reason = classify(f.text)

    smooth(frames)

    blocks = detect_blocks(frames)

    print()
    print("=== DELIVERY zones detected in first 5 min ===")
    print()
    if not blocks:
        print("(no blocks detected)")
    for n, (a, b) in enumerate(blocks, 1):
        ta = frames[a].rel_t
        tb = frames[b].rel_t
        m = sum(1 for f in frames[a:b + 1] if f.smoothed)
        print(f"Block {n}: t={ta:.1f}s -> t={tb:.1f}s ({tb - ta:.1f}s, {m} Scout frames)")
    print()
    print(f"Total blocks: {len(blocks)}")

    print()
    print("=== Reference (user-provided truth) ===")
    print("First delivery: 1:40 to 1:55 (t=100s -> t=115s)")

    overlap = [(n, frames[a].rel_t, frames[b].rel_t)
               for n, (a, b) in enumerate(blocks, 1)
               if frames[a].rel_t <= 115 and frames[b].rel_t >= 100]
    print()
    if overlap:
        print(f"Truth overlap: {len(overlap)} block(s) intersect 100-115s -> "
              + ", ".join(f"#{n}({a:.1f}-{b:.1f})" for n, a, b in overlap))
    else:
        print("Truth overlap: NONE (no block intersects 100-115s)")

    if args.debug_non_deliveries:
        print()
        print("=== Per-block raw frames ===")
        for n, (a, b) in enumerate(blocks, 1):
            print(f"-- Block {n} (t={frames[a].rel_t:.1f}-{frames[b].rel_t:.1f}s) --")
            for f in frames[a:b + 1]:
                mark = "D" if f.smoothed else "."
                raw = "d" if f.is_delivery else "."
                print(f"  [{mark}{raw}] t={f.rel_t:6.1f}s  {f.reason:30s}  {f.text[:120]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
