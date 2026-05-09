#!/usr/bin/env python3
"""v3.1 cricket-broadcast chunking algorithm simulation.

Reads a Scout frame dump (text), computes per-frame label confidences,
identifies anchors, walks/grows chunks with inertia, merges, builds
consequential delivery windows, and scores against ground truth.

Deterministic. No external deps.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ----------------------------------------------------------------------
# Keyword tables
# ----------------------------------------------------------------------
ACTION_VERBS = [
    "running in", "running toward", "running with", "sprinting", "mid-swing",
    "mid-air", "mid-stride", "mid-motion", "just released", "just threw",
    "just hit", "diving", "fielding", "playing shot", "preparing shot",
    "preparing to play", "preparing to hit", "catching", "ball in flight",
    "ball traveling", "ball mid-air", "throwing", "chasing ball",
    "chasing the ball", "leaping", "lunging",
]

DRS_KEYWORDS = [
    "ball-tracking", "ball tracking", "trajectory", "hawkeye", "hawk-eye",
    "ultra-edge", "snicko", "decision review", "drs", "umpire's call",
]

BRAND_KEYWORDS = [
    "jiohotstar", "hotstar", "self-serve", "star sports", "tata ipl", "vivo",
    "dream11", "jio", "sponsor", "official partner",
]

LIVE_CONTEXT_TERMS = [
    "batter", "batsman", "batsmen", "stumps", "wicket", "crease",
    "at the crease", "stumps visible",
]

CELEBRATION_TERMS_PLAYER = [
    "raising bat", "arm raised", "arms outstretched", "high-fiv",
    "celebration", "celebrating", "raised in celebration",
]

CELEBRATION_TERMS_CROWD = [
    "crowd cheering", "fans celebrating", "crowd celebrating",
    "fans cheering", "crowd erupting", "spectators cheering",
]

CROWD_AS_SUBJECT_TERMS = [
    "crowd visible", "spectators visible", "fans visible",
    "crowd in the foreground", "spectators in the foreground",
    "crowd cheering", "fans cheering",
]

CAREER_STATS_REGEX = re.compile(
    r"\b[A-Z][A-Z\.\-' ]{3,30}\s+\d{1,3}\*?\s*\(?\d{1,3}\)?[\s\"\.,;\-]*?MATCH\s*\d+\s+v\s+[A-Z]{2,5}\b"
)
MATCH_OVERLAY_REGEX = re.compile(r"MATCH\s*\d+\s+v\s+[A-Z]{2,5}\b", re.IGNORECASE)
DISMISSAL_REGEX = re.compile(
    r"\b[A-Z][a-z]+\s+c\s+[A-Z][a-z]+\s+b\s+[A-Z][a-z]+\s+\d+\(\d+\)"
)

SLOWMO_TERMS = [
    "slow motion", "slow-mo", "slo-mo", "slowed", "in slow", "slowed down",
    "moments earlier", "moments ago", "previous",
]

NO_PLAYERS_TERMS = [
    "no people visible", "no people are", "no players visible",
    "no players are", "no individuals", "no action visible", "title card",
    "static graphic", "static image",
]

EXPLICIT_UMPIRE = [
    "the umpire", "umpire is", "umpire raised", "umpire's arm",
    "umpire signal", "umpire raises", "umpire signals",
]
HYPOTHETICAL_UMPIRE = [
    "or the umpire", "possibly the umpire", "to the umpire", "or umpire",
    "possibly umpire", "to teammates or the umpire",
    "to a teammate or the umpire",
]
SIGNALING_VERBS = [
    "raised", "outstretched", "arm extended", "signaling", "signalling",
    "indicating", "gesture",
]

DELIVERY_PHASES = {"release", "flight", "shot", "post_shot"}
HOSTILE_LABELS = {"REPLAY", "AD", "DRS"}
LABELS = ["DELIVERY_ACTION", "REPLAY", "AD", "DRS", "UMPIRE_SIGNAL", "NON_DELIVERY_ACTION"]


# ----------------------------------------------------------------------
# Frame dataclass
# ----------------------------------------------------------------------
@dataclass
class Frame:
    ts: float
    prod_cam: str
    prod_phase: str
    v2_broadcast: str
    v2_class: str
    open_desc: str
    scores: Dict[str, float] = field(default_factory=dict)
    top_label: str = ""
    top_score: float = 0.0
    second_score: float = 0.0
    margin: float = 0.0
    anchor: str = "NONE"  # STRONG | WEAK | NONE


@dataclass
class Clip:
    session: str
    clip_id: str
    frames: List[Frame] = field(default_factory=list)


@dataclass
class Chunk:
    label: str
    start_idx: int
    end_idx: int
    strength: float
    notes: str = ""

    def start_ts(self, frames: List[Frame]) -> float:
        return frames[self.start_idx].ts

    def end_ts(self, frames: List[Frame]) -> float:
        return frames[self.end_idx].ts


# ----------------------------------------------------------------------
# Parser
# ----------------------------------------------------------------------
CLIP_HDR = re.compile(r"^\[CLIP\s+([^/]+)/([^\]]+)\]")
TS_HDR = re.compile(r"^\s*ts=\s*([\d.]+)s")
KEY_VAL = re.compile(r"^\s*(prod_cam|prod_phase|v2_broadcast|v2_class)=(.+)$")
OPEN_DESC_START = re.compile(r'^\s*open_desc:\s*"(.*)$')


def parse_dump(path: Path) -> List[Clip]:
    clips: List[Clip] = []
    cur_clip: Optional[Clip] = None
    cur_frame: Optional[Frame] = None
    in_open_desc = False
    desc_buf: List[str] = []

    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")

            # finishing an open_desc on a closing quote line
            if in_open_desc:
                # look for terminating quote
                idx = line.rfind('"')
                if idx >= 0 and (line[idx:].strip() == '"' or line.strip().endswith('"')):
                    desc_buf.append(line[: idx])
                    if cur_frame is not None:
                        cur_frame.open_desc = "\n".join(desc_buf).strip()
                    in_open_desc = False
                    desc_buf = []
                    continue
                else:
                    desc_buf.append(line)
                    continue

            m = CLIP_HDR.match(line)
            if m:
                if cur_clip is not None and cur_frame is not None:
                    cur_clip.frames.append(cur_frame)
                    cur_frame = None
                cur_clip = Clip(session=m.group(1), clip_id=m.group(2))
                clips.append(cur_clip)
                continue

            m = TS_HDR.match(line)
            if m:
                if cur_clip is not None and cur_frame is not None:
                    cur_clip.frames.append(cur_frame)
                cur_frame = Frame(
                    ts=float(m.group(1)),
                    prod_cam="", prod_phase="", v2_broadcast="", v2_class="",
                    open_desc="",
                )
                continue

            m = KEY_VAL.match(line)
            if m and cur_frame is not None:
                key, val = m.group(1), m.group(2).strip()
                setattr(cur_frame, key, val)
                continue

            m = OPEN_DESC_START.match(line)
            if m and cur_frame is not None:
                rest = m.group(1)
                # single-line open_desc?
                if rest.endswith('"'):
                    cur_frame.open_desc = rest[:-1].strip()
                else:
                    in_open_desc = True
                    desc_buf = [rest]
                continue

    # flush
    if cur_clip is not None and cur_frame is not None:
        cur_clip.frames.append(cur_frame)

    # sort each clip frames by ts (defensive)
    for c in clips:
        c.frames.sort(key=lambda f: f.ts)
    return clips


# ----------------------------------------------------------------------
# Scoring
# ----------------------------------------------------------------------
def _has_any(terms: List[str], text: str) -> bool:
    return any(t in text for t in terms)


def score_frame(f: Frame) -> None:
    desc = f.open_desc.lower()
    raw_desc = f.open_desc  # raw for case-sensitive regex

    has_career = bool(CAREER_STATS_REGEX.search(raw_desc)) or bool(MATCH_OVERLAY_REGEX.search(raw_desc))
    has_dismissal = bool(DISMISSAL_REGEX.search(raw_desc))
    has_action_verb = _has_any(ACTION_VERBS, desc)
    has_drs = _has_any(DRS_KEYWORDS, desc)
    has_brand = _has_any(BRAND_KEYWORDS, desc)
    has_live_ctx = _has_any(LIVE_CONTEXT_TERMS, desc)
    has_celeb_player = _has_any(CELEBRATION_TERMS_PLAYER, desc)
    has_celeb_crowd = _has_any(CELEBRATION_TERMS_CROWD, desc)
    has_crowd_subj = _has_any(CROWD_AS_SUBJECT_TERMS, desc)
    has_slowmo = _has_any(SLOWMO_TERMS, desc)
    has_no_players = _has_any(NO_PLAYERS_TERMS, desc)

    bcast = f.v2_broadcast.upper()
    is_replay_tag = bcast in {"REPLAY", "SLO-MO", "TELESTRATOR", "SPLIT-SCREEN"}

    # DELIVERY
    d = 0.0
    if f.prod_phase in DELIVERY_PHASES:
        d += 0.40
    if has_action_verb:
        d += 0.30
    if has_live_ctx:
        d += 0.20
    if f.v2_class == "action":
        d += 0.20
    if has_career:
        d -= 0.40
    if has_crowd_subj and has_action_verb:
        d -= 0.30
    if has_slowmo:
        d -= 0.30
    if has_dismissal:
        d -= 0.30
    if is_replay_tag:
        d -= 0.30
    delivery = max(0.0, min(1.0, d))

    # REPLAY
    r = 0.0
    if is_replay_tag:
        r += 0.40
    if has_career:
        r += 0.30
    if has_dismissal:
        r += 0.30
    if has_slowmo:
        r += 0.20
    if has_crowd_subj and has_action_verb:
        r += 0.30
    if has_celeb_crowd:
        r += 0.20
    replay = max(0.0, min(1.0, r))

    # AD
    a = 0.0
    if f.prod_cam == "ad" or f.prod_phase == "advertisement":
        a += 0.70
    if f.prod_cam == "graphic" and has_brand and has_no_players:
        a += 0.50
    if f.ts <= 3.0 and f.prod_cam == "graphic" and has_no_players:
        a += 0.30
    ad = max(0.0, min(1.0, a))

    # DRS
    drs = 0.0
    if has_drs:
        drs += 0.80
    drs = max(0.0, min(1.0, drs))

    # UMPIRE
    has_explicit = _has_any(EXPLICIT_UMPIRE, desc)
    has_hypothetical = _has_any(HYPOTHETICAL_UMPIRE, desc)
    has_signal_verb = _has_any(SIGNALING_VERBS, desc)
    u = 0.0
    if has_explicit:
        u += 0.50
    if has_signal_verb:
        u += 0.30
    if f.prod_cam == "bowlers_end":
        u -= 0.40
    if has_hypothetical and not has_explicit:
        u -= 0.50
    umpire = max(0.0, min(1.0, u))

    # NON_DELIVERY (residual)
    nd = 0.10  # baseline
    if (f.v2_class == "action" and f.prod_phase not in DELIVERY_PHASES
            and replay < 0.3 and drs < 0.3 and ad < 0.3 and umpire < 0.3):
        nd += 0.30
    if f.prod_phase == "between_play":
        nd += 0.20
    non_delivery = max(0.0, min(1.0, nd))

    f.scores = {
        "DELIVERY_ACTION": delivery,
        "REPLAY": replay,
        "AD": ad,
        "DRS": drs,
        "UMPIRE_SIGNAL": umpire,
        "NON_DELIVERY_ACTION": non_delivery,
    }
    ranked = sorted(f.scores.items(), key=lambda kv: kv[1], reverse=True)
    f.top_label = ranked[0][0]
    f.top_score = ranked[0][1]
    f.second_score = ranked[1][1]
    f.margin = f.top_score - f.second_score

    if f.top_score >= 0.6 and f.margin >= 0.2:
        f.anchor = "STRONG"
    elif f.top_score >= 0.4:
        f.anchor = "WEAK"
    else:
        f.anchor = "NONE"


# ----------------------------------------------------------------------
# Walk mechanics
# ----------------------------------------------------------------------
ANCHOR_PRIORITY = ["AD", "DRS", "REPLAY", "UMPIRE_SIGNAL", "DELIVERY_ACTION", "NON_DELIVERY_ACTION"]


def build_chunks(frames: List[Frame]) -> List[Chunk]:
    n = len(frames)
    in_chunk: List[Optional[int]] = [None] * n  # idx -> chunk index
    chunks: List[Chunk] = []

    # collect strong anchors with priority
    strong = [(i, f) for i, f in enumerate(frames) if f.anchor == "STRONG"]
    strong.sort(key=lambda t: (ANCHOR_PRIORITY.index(t[1].top_label), t[0]))

    for anchor_idx, anchor_f in strong:
        if in_chunk[anchor_idx] is not None:
            ch = chunks[in_chunk[anchor_idx]]
            if ch.strength > 1.0 and ch.label != anchor_f.top_label:
                continue
            if ch.label == anchor_f.top_label:
                continue

        chunk_label = anchor_f.top_label
        S = anchor_f.scores[chunk_label]
        chunk = Chunk(label=chunk_label, start_idx=anchor_idx, end_idx=anchor_idx, strength=S)
        chunk_index = len(chunks)
        chunks.append(chunk)
        in_chunk[anchor_idx] = chunk_index

        # FORWARD walk
        i = anchor_idx + 1
        while i < n:
            nxt = frames[i]
            other_chunk = in_chunk[i]
            if other_chunk is not None and chunks[other_chunk].strength > 1.0 and chunks[other_chunk].label != chunk_label:
                break

            support = nxt.scores[chunk_label]
            dissent_label, dissent = max(
                ((lbl, sc) for lbl, sc in nxt.scores.items() if lbl != chunk_label),
                key=lambda kv: kv[1],
            )

            if support >= 0.4 and dissent < 0.4:
                chunk.end_idx = i
                in_chunk[i] = chunk_index
                S += 0.3
                chunk.strength = S
                i += 1
                continue
            elif support >= 0.2 and dissent < 0.5:
                if S >= 1.0:
                    chunk.end_idx = i
                    in_chunk[i] = chunk_index
                    i += 1
                    continue
                else:
                    next2 = frames[i:i + 3]
                    cnt = sum(1 for ff in next2 if ff.scores[chunk_label] >= 0.3)
                    if cnt >= 2:
                        chunk.end_idx = i
                        in_chunk[i] = chunk_index
                        i += 1
                        continue
                    else:
                        break
            elif dissent >= 0.5 and support < 0.3:
                next_is_other_anchor = (
                    nxt.anchor == "STRONG" and nxt.top_label != chunk_label
                )
                next3 = frames[i:i + 4]
                dcount = sum(
                    1 for ff in next3
                    if max(((lbl, sc) for lbl, sc in ff.scores.items() if lbl != chunk_label), key=lambda kv: kv[1])[0] == dissent_label
                    and max(((lbl, sc) for lbl, sc in ff.scores.items() if lbl != chunk_label), key=lambda kv: kv[1])[1] >= 0.4
                )
                if dcount >= 2 or next_is_other_anchor:
                    break
                else:
                    if S >= 1.5:
                        chunk.end_idx = i
                        in_chunk[i] = chunk_index
                        S -= 0.5
                        chunk.strength = S
                        if S < 0.3:
                            break
                        i += 1
                        continue
                    else:
                        break
            else:
                if S >= 0.8:
                    chunk.end_idx = i
                    in_chunk[i] = chunk_index
                    i += 1
                    continue
                else:
                    break

        # BACKWARD walk
        S = chunk.strength
        i = anchor_idx - 1
        while i >= 0:
            prv = frames[i]
            other_chunk = in_chunk[i]
            if other_chunk is not None and chunks[other_chunk].strength > 1.0 and chunks[other_chunk].label != chunk_label:
                break

            support = prv.scores[chunk_label]
            dissent_label, dissent = max(
                ((lbl, sc) for lbl, sc in prv.scores.items() if lbl != chunk_label),
                key=lambda kv: kv[1],
            )

            if support >= 0.4 and dissent < 0.4:
                chunk.start_idx = i
                in_chunk[i] = chunk_index
                S += 0.3
                chunk.strength = S
                i -= 1
                continue
            elif support >= 0.2 and dissent < 0.5:
                if S >= 1.0:
                    chunk.start_idx = i
                    in_chunk[i] = chunk_index
                    i -= 1
                    continue
                else:
                    prev2 = frames[max(0, i - 2):i + 1]
                    cnt = sum(1 for ff in prev2 if ff.scores[chunk_label] >= 0.3)
                    if cnt >= 2:
                        chunk.start_idx = i
                        in_chunk[i] = chunk_index
                        i -= 1
                        continue
                    else:
                        break
            elif dissent >= 0.5 and support < 0.3:
                prev_is_other_anchor = (
                    prv.anchor == "STRONG" and prv.top_label != chunk_label
                )
                prev3 = frames[max(0, i - 3):i + 1]
                dcount = sum(
                    1 for ff in prev3
                    if max(((lbl, sc) for lbl, sc in ff.scores.items() if lbl != chunk_label), key=lambda kv: kv[1])[0] == dissent_label
                    and max(((lbl, sc) for lbl, sc in ff.scores.items() if lbl != chunk_label), key=lambda kv: kv[1])[1] >= 0.4
                )
                if dcount >= 2 or prev_is_other_anchor:
                    break
                else:
                    if S >= 1.5:
                        chunk.start_idx = i
                        in_chunk[i] = chunk_index
                        S -= 0.5
                        chunk.strength = S
                        if S < 0.3:
                            break
                        i -= 1
                        continue
                    else:
                        break
            else:
                if S >= 0.8:
                    chunk.start_idx = i
                    in_chunk[i] = chunk_index
                    i -= 1
                    continue
                else:
                    break

    # ------------------------------------------------------------------
    # Merge same-label adjacent chunks
    # ------------------------------------------------------------------
    chunks.sort(key=lambda c: c.start_idx)
    merged: List[Chunk] = []
    for ch in chunks:
        if not merged:
            merged.append(ch)
            continue
        prev = merged[-1]
        if prev.label != ch.label:
            merged.append(ch)
            continue
        # check gap
        gap_lo = prev.end_idx + 1
        gap_hi = ch.start_idx - 1
        ok = True
        if gap_lo <= gap_hi:
            # any STRONG anchor of hostile label in gap?
            for k in range(gap_lo, gap_hi + 1):
                ff = frames[k]
                if ff.anchor == "STRONG" and ff.top_label in HOSTILE_LABELS and ff.top_label != ch.label:
                    ok = False
                    break
            if ok:
                # check 3+ consecutive frames where same dissent_label and dissent >= 0.4
                run_label = None
                run_count = 0
                for k in range(gap_lo, gap_hi + 1):
                    ff = frames[k]
                    dlabel, dscore = max(
                        ((lbl, sc) for lbl, sc in ff.scores.items() if lbl != ch.label),
                        key=lambda kv: kv[1],
                    )
                    if dscore >= 0.4:
                        if dlabel == run_label:
                            run_count += 1
                        else:
                            run_label = dlabel
                            run_count = 1
                        if run_count >= 3:
                            ok = False
                            break
                    else:
                        run_label = None
                        run_count = 0
        if ok:
            prev.end_idx = max(prev.end_idx, ch.end_idx)
            prev.strength = max(prev.strength, ch.strength)
        else:
            merged.append(ch)

    return merged


# ----------------------------------------------------------------------
# Consequential window
# ----------------------------------------------------------------------
def consequential_windows(frames: List[Frame], chunks: List[Chunk]) -> List[Tuple[float, float]]:
    delivery_chunks = [c for c in chunks if c.label == "DELIVERY_ACTION"]
    umpire_chunks = [c for c in chunks if c.label == "UMPIRE_SIGNAL"]
    drs_chunks = [c for c in chunks if c.label == "DRS"]

    windows: List[Tuple[float, float]] = []
    for d in delivery_chunks:
        s_ts = d.start_ts(frames)
        e_ts = d.end_ts(frames)

        # append umpire chunks within 3s after end_ts
        for u in umpire_chunks:
            if 0 <= u.start_ts(frames) - e_ts <= 3.0:
                e_ts = max(e_ts, u.end_ts(frames))
        # append DRS chunks within 5s after end_ts
        for r in drs_chunks:
            if 0 <= r.start_ts(frames) - e_ts <= 5.0:
                e_ts = max(e_ts, r.end_ts(frames))

        # lookback up to 2s
        s_idx = d.start_idx
        target = s_ts - 2.0
        i = s_idx - 1
        while i >= 0 and frames[i].ts >= target:
            ff = frames[i]
            if ff.anchor == "STRONG" and ff.top_label in HOSTILE_LABELS:
                break
            if ff.anchor == "STRONG" and ff.top_label not in {"DELIVERY_ACTION", "NON_DELIVERY_ACTION"}:
                break
            if ff.top_label == "NON_DELIVERY_ACTION" and ff.top_score >= 0.5:
                # weak NDA OK
                pass
            elif ff.anchor == "NONE":
                pass
            elif ff.top_label == "DELIVERY_ACTION":
                pass
            elif ff.top_label == "NON_DELIVERY_ACTION":
                pass
            else:
                break
            s_ts = ff.ts
            i -= 1

        # forward up to 2s
        e_idx = d.end_idx
        target = e_ts + 2.0
        j = e_idx + 1
        while j < len(frames) and frames[j].ts <= target:
            ff = frames[j]
            if ff.anchor == "STRONG" and ff.top_label in HOSTILE_LABELS:
                break
            if ff.anchor == "STRONG" and ff.top_label not in {"DELIVERY_ACTION", "NON_DELIVERY_ACTION", "UMPIRE_SIGNAL"}:
                break
            if ff.anchor == "NONE" or ff.top_label in {"NON_DELIVERY_ACTION", "DELIVERY_ACTION", "UMPIRE_SIGNAL"}:
                pass
            else:
                break
            e_ts = ff.ts
            j += 1

        windows.append((s_ts, e_ts))

    # merge overlapping windows
    if not windows:
        return []
    windows.sort()
    merged: List[Tuple[float, float]] = [windows[0]]
    for s, e in windows[1:]:
        ps, pe = merged[-1]
        if s <= pe + 0.34:  # roughly one frame
            merged[-1] = (ps, max(pe, e))
        else:
            merged.append((s, e))
    return merged


# ----------------------------------------------------------------------
# Ground truth + scoring
# ----------------------------------------------------------------------
GROUND_TRUTH = {
    ("20260503_205835", "d001"): None,
    ("20260503_205835", "d002"): None,
    ("20260503_205835", "d003"): None,
    ("20260503_205835", "d004"): (1.0, 8.0),
    ("20260503_205835", "d005"): (5.0, 9.0),
    ("20260503_205835", "d006"): None,
    ("20260503_205835", "d007"): (0.0, 5.0),
    ("20260503_205835", "d008"): None,
    ("20260421_195050", "d046"): (2.0, 12.0),
    ("20260421_195050", "d059"): (0.0, 11.0),
    ("20260421_195050", "d051"): (0.0, 8.0),
    ("20260420_202239", "d015"): (8.0, 18.0),
    ("20260420_202239", "d004"): (7.0, 18.0),
    ("20260420_202239", "d036"): (12.0, 20.0),
    ("20260420_202239", "d032"): (12.0, 22.0),
    ("20260420_202239", "d029"): (8.0, 13.0),
    ("20260420_202239", "d018"): (8.0, 22.0),
    ("20260420_202239", "d014"): (0.0, 7.0),
}


def iou(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    inter = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    if union <= 0:
        return 0.0
    return inter / union


def verdict(truth: Optional[Tuple[float, float]],
            preds: List[Tuple[float, float]]) -> Tuple[str, float, List[Tuple[float, float]]]:
    if truth is None and not preds:
        return "MATCH", 1.0, []
    if truth is None and preds:
        return "FP", 0.0, preds
    if truth is not None and not preds:
        return "WRONG", 0.0, []
    # both present; pick largest predicted
    largest = max(preds, key=lambda w: w[1] - w[0])
    iou_val = iou(truth, largest)
    extras = [w for w in preds if w != largest]
    if iou_val >= 0.6:
        return "MATCH", iou_val, extras
    if iou_val >= 0.3:
        return "PARTIAL", iou_val, extras
    return "WRONG", iou_val, extras


# ----------------------------------------------------------------------
# Render
# ----------------------------------------------------------------------
def render_clip(clip: Clip, chunks: List[Chunk], windows: List[Tuple[float, float]],
                truth: Optional[Tuple[float, float]], v: str, iou_val: float,
                extras: List[Tuple[float, float]]) -> str:
    out: List[str] = []
    out.append(f"[CLIP {clip.session}/{clip.clip_id}]")
    if truth is None:
        out.append("  Truth window: NONE")
    else:
        out.append(f"  Truth window: {truth[0]:.1f}-{truth[1]:.1f}s")
    out.append("")
    out.append("  Anchors found:")
    found_any_anchor = False
    for f in clip.frames:
        if f.anchor != "NONE":
            found_any_anchor = True
            out.append(
                f"    ts={f.ts:.2f} label={f.top_label} score={f.top_score:.2f} margin={f.margin:.2f} ({f.anchor})"
            )
    if not found_any_anchor:
        out.append("    (none)")
    out.append("")
    out.append("  Chunks (after walks + merging):")
    if not chunks:
        out.append("    (none)")
    for c in chunks:
        out.append(
            f"    [{c.start_ts(clip.frames):.2f}-{c.end_ts(clip.frames):.2f}] "
            f"{c.label} strength={c.strength:.2f}"
        )
    out.append("")
    if windows:
        primary = max(windows, key=lambda w: w[1] - w[0])
        out.append(f"  Consequential delivery window: {primary[0]:.2f}-{primary[1]:.2f}s")
    else:
        out.append("  Consequential delivery window: NONE")
    if extras:
        out.append(f"  Extra windows: {extras}")
    out.append(f"  IoU vs truth: {iou_val:.2f}")
    out.append(f"  Verdict: {v}")
    out.append("")
    return "\n".join(out)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main(dump_path: Path, results_path: Path) -> None:
    clips = parse_dump(dump_path)
    counts = {"MATCH": 0, "PARTIAL": 0, "WRONG": 0, "FP": 0}
    per_clip_iou: List[Tuple[str, float, str]] = []

    text_blocks: List[str] = []
    text_blocks.append("v3.1 cricket-broadcast chunking simulation")
    text_blocks.append("=" * 70)
    text_blocks.append("")

    for clip in clips:
        for f in clip.frames:
            score_frame(f)
        chunks = build_chunks(clip.frames)
        windows = consequential_windows(clip.frames, chunks)
        truth = GROUND_TRUTH.get((clip.session, clip.clip_id))
        v, iou_val, extras = verdict(truth, windows)
        counts[v] += 1
        per_clip_iou.append((f"{clip.session}/{clip.clip_id}", iou_val, v))
        text_blocks.append(render_clip(clip, chunks, windows, truth, v, iou_val, extras))

    # scorecard
    text_blocks.append("=" * 70)
    text_blocks.append("OVERALL SCORECARD (v3.1)")
    text_blocks.append("=" * 70)
    text_blocks.append(
        f"  MATCH={counts['MATCH']}  PARTIAL={counts['PARTIAL']}  "
        f"WRONG={counts['WRONG']}  FP={counts['FP']}  / 18"
    )
    text_blocks.append("")
    text_blocks.append("Per-clip:")
    for name, ival, v in per_clip_iou:
        text_blocks.append(f"  {name:<35} IoU={ival:.2f}  {v}")
    text_blocks.append("")
    text_blocks.append("v3 baseline (for comparison):")
    text_blocks.append("  MATCH=10  PARTIAL=7  WRONG=1  FP=0  / 18")

    results_path.write_text("\n".join(text_blocks), encoding="utf-8")
    print(f"  MATCH={counts['MATCH']}  PARTIAL={counts['PARTIAL']}  "
          f"WRONG={counts['WRONG']}  FP={counts['FP']}  / 18")
    for name, ival, v in per_clip_iou:
        print(f"  {name:<35} IoU={ival:.2f}  {v}")


if __name__ == "__main__":
    dump = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "/Users/anmolmohan/Library/Application Support/Claude/local-agent-mode-sessions/"
        "e5cb7aad-1b91-4dc0-8d12-cddc0c4fd0bf/75506dad-0db5-4dd6-82d6-69272ee757d2/"
        "local_844010c6-82db-4eb3-94cf-9f87bc3bf63d/uploads/chunk_v1_frame_dump.txt"
    )
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(
        "/Users/anmolmohan/Projects/SportsComm/v3_1_simulation_results.txt"
    )
    main(dump, out)
