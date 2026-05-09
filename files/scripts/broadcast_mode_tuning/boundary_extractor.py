"""Boundary extraction: C1-C5 inclusion + S1-S8 stop patterns."""

from __future__ import annotations

import re

from signal_extraction import Signals, matches_v_loose

CELEBRATION_PAT = re.compile(
    r"\b(FOUR|SIX|wicket\s+fell|raised?\s+his\s+arm|raising\s+arms|"
    r"arms\s+(?:above\s+his\s+head|raised|outstretched)|fist[-\s]?pump|"
    r"fists?\s+clenched|jumping\s+up|high[-\s]?fiving|"
    r"cheering\s+crowd|fans\s+cheering|shouting\s+in\s+(?:joy|celebration))\b",
    re.IGNORECASE,
)

CELEBRATING_LOOSE_PAT = re.compile(r"\b(celebrating|celebration)\b", re.IGNORECASE)

POST_ACTION_PAT = re.compile(
    r"\b(post[-\s]action|moment\s+of\s+interaction|engaged\s+in\s+conversation|"
    r"walking\s+together|bumping|elbow\s+bumping)\b",
    re.IGNORECASE,
)

CLOSEUP_PAT = re.compile(
    r"\b(close[-\s]?up|medium\s+shot|head[-\s]and[-\s]shoulders|"
    r"close-up\s+shot)\b",
    re.IGNORECASE,
)

CROWD_CTX_PAT = re.compile(r"\b(crowd|fans|spectators)\b", re.IGNORECASE)


CROWD_OR_STADIUM_PAT = re.compile(
    r"\b(crowd|fans|spectators|stadium)\b", re.IGNORECASE,
)

C6_PHRASE_PAT = re.compile(
    r"\b(post[-\s]action|between\s+deliveries|fielders|walking|running)\b",
    re.IGNORECASE,
)

C7_PHRASE_PAT = re.compile(
    r"\b(post[-\s]action|between\s+deliveries)\b", re.IGNORECASE,
)


def is_C1(s: Signals) -> bool:
    return s.W and (s.M or s.CG)


def is_C2(s: Signals, text: str) -> bool:
    return s.W and matches_v_loose(text)


def is_C3(text: str) -> bool:
    return bool(CELEBRATION_PAT.search(text))


def is_C4(s: Signals, text: str) -> bool:
    if not s.M2 or not CLOSEUP_PAT.search(text):
        return False
    return bool(POST_ACTION_PAT.search(text))


def is_C5(text: str) -> bool:
    if not CROWD_OR_STADIUM_PAT.search(text):
        return False
    if CELEBRATION_PAT.search(text):
        return True
    # Loose "celebrating" only modifies C5 when crowd context present.
    return bool(CELEBRATING_LOOSE_PAT.search(text))


def is_C6(s: Signals, text: str) -> bool:
    return s.W and bool(C6_PHRASE_PAT.search(text)) and s.CG


def is_C7(s: Signals, text: str) -> bool:
    if not CLOSEUP_PAT.search(text):
        return False
    return (bool(C7_PHRASE_PAT.search(text))
            or bool(CELEBRATION_PAT.search(text)))


def matched_inclusions(f) -> list[str]:
    s = f.signals
    hits: list[str] = []
    if is_C1(s):
        hits.append("C1")
    if is_C2(s, f.text):
        hits.append("C2")
    if is_C3(f.text):
        hits.append("C3")
    if is_C4(s, f.text):
        hits.append("C4")
    if is_C5(f.text):
        hits.append("C5")
    if is_C6(s, f.text):
        hits.append("C6")
    if is_C7(s, f.text):
        hits.append("C7")
    return hits


def is_inclusion(f) -> bool:
    return bool(matched_inclusions(f))


# S1-S8 stop patterns
DRS_PAT = re.compile(r"\b(DRS|reviews\s+remaining|DRS\s+TIMER)\b", re.IGNORECASE)
PROFILE_PAT = re.compile(
    r"\b(career\s+statistics|matches\s+played|wickets\s+taken|"
    r"economy\s+rate|strike\s+rate|innings|outs|average)\b",
    re.IGNORECASE,
)
BETWEEN_PAT = re.compile(
    r"\b(between\s+deliveries|no\s+active\s+play|preparing\s+for\s+next|"
    r"waiting\s+for\s+the\s+next)\b",
    re.IGNORECASE,
)
FULLSCREEN_AD_PAT = re.compile(
    r"\b(promotional\s+graphic|TATA\s+IPL\s+graphic|sponsor\s+card|"
    r"silhouette\s+of\s+a\s+cricket\s+player|silhouettes\s+of\s+cricket\s+players)\b",
    re.IGNORECASE,
)
INDOOR_PAT = re.compile(
    r"\b(office|study|indoor|laptop|desk|shelf|bookshelf|jar|tin\s+can)\b",
    re.IGNORECASE,
)
TOURNAMENT_OVERLAY_PAT = re.compile(
    r"\b(Won\s+the\s+Toss|Impact\s+Sub\s+Options|Tournament\s+Standings|"
    r"Match\s+Number)\b",
    re.IGNORECASE,
)


def is_S1(f) -> bool:
    s = f.signals
    if not (s.K and not s.SS):
        return False
    return not s.V


def is_S2(text: str) -> bool:
    return bool(DRS_PAT.search(text))


def is_S3(s: Signals, text: str) -> bool:
    return bool(PROFILE_PAT.search(text)) and bool(CLOSEUP_PAT.search(text))


def is_S4_run(frames, idx: int, run_len: int = 3) -> bool:
    """3+ consecutive frames matching the S4 conditions ending at idx."""
    if idx + 1 < run_len:
        return False
    for k in range(idx - run_len + 1, idx + 1):
        f = frames[k]
        if not BETWEEN_PAT.search(f.text):
            return False
        if CELEBRATION_PAT.search(f.text):
            return False
        if f.signals.V:
            return False
    return True


def is_S5(text: str) -> bool:
    return bool(FULLSCREEN_AD_PAT.search(text))


def is_S6(text: str) -> bool:
    return bool(INDOOR_PAT.search(text))


def is_S7(s: Signals, text: str) -> bool:
    return bool(TOURNAMENT_OVERLAY_PAT.search(text))


SPEED_PAT = re.compile(
    r"\b(?:SPEED\s+\d+|\d+(?:\.\d+)?\s*kph|speedometer)\b",
    re.IGNORECASE,
)

# Fix 6: wicket-context anchor markers + catch markers for forward
# peek-ahead extension.
WICKET_ANCHOR_PAT = re.compile(
    r"\b(?:wicket\s+(?:falls?|fell)|caught|dismissed|out\b|"
    r"walking\s+off\s+the\s+pitch|walking\s+off\s+the\s+field|"
    r"batsm(?:a|e)n\s+walking\s+off|"
    r"ball\s+is\s+visible\s+in\s+mid-air|"
    r"fielder\s+(?:lunges|dives|catching\s+the\s+ball))\b",
    re.IGNORECASE,
)
CATCH_MARKER_PAT = re.compile(
    r"\b(?:fielder\s+(?:catches|dives|lunges|catching\s+the\s+ball)|"
    r"caught|wicket\s+falls?|wicket\s+fell|out\b|"
    r"holding\s+(?:a|the)\s+ball\s+up|"
    r"raising\s+(?:a|the)\s+ball|"
    r"player\s+(?:running|celebrating)|fans?\s+cheering|"
    r"walking\s+off\s+the\s+pitch|walking\s+off\s+the\s+field|"
    r"batsm(?:a|e)n\s+walking\s+off)\b",
    re.IGNORECASE,
)


def is_S9(text: str) -> bool:
    return bool(SPEED_PAT.search(text))


def is_S8_run(frames, idx: int, run_len: int = 3) -> bool:
    if idx + 1 < run_len:
        return False
    for k in range(idx - run_len + 1, idx + 1):
        f = frames[k]
        if not CLOSEUP_PAT.search(f.text):
            return False
        if CELEBRATION_PAT.search(f.text):
            return False
        if f.signals.V:
            return False
        if f.signals.role_count > 1:
            return False
    return True


def is_stop(f, frames, idx: int) -> bool:
    s = f.signals
    if s.HARD:
        return True
    if is_S1(f):
        return True
    if is_S2(f.text):
        return True
    if is_S3(s, f.text):
        return True
    if is_S4_run(frames, idx):
        return True
    if is_S5(f.text):
        return True
    if is_S6(f.text):
        return True
    if is_S7(s, f.text):
        return True
    if is_S8_run(frames, idx):
        return True
    if is_S9(f.text):
        return True
    return False


def extract_window(cluster: dict, anchor_t: float,
                   all_frames: list, *,
                   back_cap_s: float = 6.0,
                   fwd_cap_s: float = 12.0,
                   peek_ahead: int = 4,
                   peek_extend_after: int = 2) -> dict:
    cluster_start = cluster["start_t"]
    cluster_end = cluster["end_t"]
    n = len(all_frames)

    # Locate cluster bounds in all_frames index space
    start_idx = next(i for i, f in enumerate(all_frames) if f.t == cluster_start)
    end_idx = next(i for i, f in enumerate(all_frames) if f.t == cluster_end)

    # Backward: skip-tolerance ≤2; C7-only matches capped at 2 in a row.
    back_t = cluster_start
    skip = 0
    c7_run = 0
    j = start_idx - 1
    while j >= 0:
        f = all_frames[j]
        if (anchor_t - f.t) > back_cap_s:
            break
        # S9 (speed reading) is a definitive boundary marker: include frame
        # and stop.
        if is_S9(f.text):
            back_t = f.t
            break
        if is_stop(f, all_frames, j):
            break
        hits = matched_inclusions(f)
        if hits:
            if hits == ["C7"]:
                c7_run += 1
                if c7_run > 2:
                    break
            else:
                c7_run = 0
            back_t = f.t
            skip = 0
        else:
            skip += 1
            if skip > 2:
                break
        j -= 1

    # Forward: skip-tolerance ≤2; C7-only matches capped at 2 in a row;
    # S9 (speed reading) includes its frame and stops.
    fwd_t = cluster_end
    skip = 0
    c7_run = 0
    j = end_idx + 1
    while j < n:
        f = all_frames[j]
        if (f.t - anchor_t) > fwd_cap_s:
            break
        if is_S9(f.text):
            fwd_t = f.t
            peek_hit = -1
            for kk in range(j + 1, min(n, j + 1 + peek_ahead + 1)):
                fk = all_frames[kk]
                if is_C3(fk.text) or is_C5(fk.text):
                    peek_hit = kk
                    break
            if peek_hit >= 0:
                last_kk = min(n - 1, peek_hit + peek_extend_after)
                fwd_t = all_frames[last_kk].t
                j = last_kk + 1
                skip = 0
                c7_run = 0
                continue
            break
        hits = matched_inclusions(f)
        if hits:
            if hits == ["C7"]:
                c7_run += 1
                if c7_run > 2:
                    break
            else:
                c7_run = 0
            fwd_t = f.t
            skip = 0
            j += 1
            continue
        if is_stop(f, all_frames, j):
            peek_hit = -1
            for kk in range(j, min(n, j + peek_ahead + 1)):
                fk = all_frames[kk]
                if is_C3(fk.text) or is_C5(fk.text):
                    peek_hit = kk
                    break
            if peek_hit >= 0:
                last_kk = min(n - 1, peek_hit + peek_extend_after)
                fwd_t = all_frames[last_kk].t
                j = last_kk + 1
                skip = 0
                c7_run = 0
                continue
            break
        skip += 1
        if skip > 2:
            break
        j += 1

    # Fix 6: when any frame in the cluster has wicket-context markers,
    # do an additional peek-ahead up to 8s past current fwd_t to
    # capture the catch / celebration cluster that follows.
    cluster_frames = [f for f in all_frames
                      if cluster_start <= f.t <= cluster_end]
    has_wicket_ctx = any(WICKET_ANCHOR_PAT.search(f.text)
                         for f in cluster_frames)
    if has_wicket_ctx:
        peek_end_t = fwd_t + 8.0
        for f in all_frames:
            if f.t <= fwd_t:
                continue
            if f.t > peek_end_t:
                break
            if CATCH_MARKER_PAT.search(f.text):
                fwd_t = f.t

    clip_start = min(back_t, cluster_start)
    clip_end = max(fwd_t, cluster_end)
    duration = clip_end - clip_start + 1.0

    note = ""
    if duration < 4.0:
        clip_end = clip_start + 4.0
        note = "min-extended"
    if (clip_end - clip_start + 1.0) > 22.0:
        clip_end = anchor_t + 12.0
        note = "max-cap"

    return {
        "anchor_t": anchor_t,
        "back_t": back_t,
        "fwd_t": fwd_t,
        "clip_start": clip_start,
        "clip_end": clip_end,
        "duration": clip_end - clip_start,
        "note": note,
    }
