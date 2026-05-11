"""Per-frame Scout-prose signal extraction (V/S/M/W/K/SS + HARD_REJECT)."""

from __future__ import annotations

import re
from dataclasses import dataclass

V_PATTERNS = [
    re.compile(r"\b(?:just\s+)?(?:released|bowled|delivered|thrown)\b", re.IGNORECASE),
    re.compile(r"\bjust\s+swung\b", re.IGNORECASE),
    re.compile(r"\bin\s+(?:mid-action|delivery\s+stride|process\s+of\s+(?:bowling|delivering))\b", re.IGNORECASE),
    re.compile(r"\bfollow[-\s]through\b", re.IGNORECASE),
    re.compile(r"\babout\s+to\s+(?:bowl|deliver|release|throw)\b", re.IGNORECASE),
    re.compile(r"\brunning\s+in\b", re.IGNORECASE),
    re.compile(r"\brunning\s+on\s+the\s+field\b", re.IGNORECASE),
    re.compile(r"\b(?:throwing|throws|swinging|delivering|bowling|hitting)\s+(?:the\s+|a\s+)?(?:white\s+)?(?:ball|object)\b", re.IGNORECASE),
    re.compile(r"\bin\s+the\s+process\s+of\s+(?:throwing|swinging|hitting|playing)\b", re.IGNORECASE),
    re.compile(r"\b(?:in\s+mid-stride|mid-stride)\b", re.IGNORECASE),
    re.compile(r"\b(?:just|having\s+just)\s+(?:hit|played|struck|made\s+contact)\b", re.IGNORECASE),
    re.compile(r"\bhit\s+the\s+ball\b", re.IGNORECASE),
]

V_LOOSE_PATTERNS = V_PATTERNS + [
    re.compile(r"\bpreparing\s+to\s+(?:bowl|deliver)\b", re.IGNORECASE),
    re.compile(r"\brunning\b", re.IGNORECASE),
    re.compile(r"\bin\s+motion\b", re.IGNORECASE),
]

# V_POST: subset of V markers that ONLY fire on post-delivery action
# (the ball was actually released / hit / swung — not "about to bowl"
# or "running in" pre-action setup). Used by the cluster_builder
# V-filter to drop clusters that contain only setup frames without
# an actual release event.
V_POST_PATTERNS = [
    re.compile(r"\b(?:just|having\s+just)\s+(?:released|bowled|delivered|thrown|hit|swung|played|struck|made\s+contact)\b",
               re.IGNORECASE),
    re.compile(r"\bjust\s+swung\b", re.IGNORECASE),
    re.compile(r"\bfollow[-\s]through\b", re.IGNORECASE),
    re.compile(r"\bin\s+(?:mid-action|delivery\s+stride)\b", re.IGNORECASE),
    re.compile(r"\bin\s+(?:the\s+)?process\s+of\s+(?:bowling|delivering)\b",
               re.IGNORECASE),
    re.compile(r"\b(?:in\s+mid-stride|mid-stride)\b", re.IGNORECASE),
    re.compile(r"\bhit\s+the\s+ball\b", re.IGNORECASE),
]

ROLES_STRICT = [
    "bowler", "batter", "batters", "batsman", "batsmen",
    "wicketkeeper", "wicket-keeper", "keeper",
    "umpire", "fielder", "fielders",
]
ROLES_LOOSE = ROLES_STRICT + [
    "player", "players", "cricketer", "cricketers",
]

# Inferred-role patterns: when prose pairs a generic "player" with a
# specific cricket action context, treat it as an implicit specific role
# for M2 (strict-multi-actor) purposes. Useful when Scout describes
# "one player about to bowl and another player holding a bat" rather
# than "the bowler and the batter".
INFERRED_BOWLER_PATS = [
    re.compile(
        r"\b(?:player|cricketer)\b[^.]*?\b(?:about\s+to\s+(?:bowl|deliver|release)|"
        r"bowling|delivering|in\s+process\s+of\s+bowling|"
        r"in\s+the\s+process\s+of\s+(?:bowling|delivering)|"
        r"preparing\s+to\s+bowl|just\s+(?:bowled|delivered|released))\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:about\s+to\s+(?:bowl|deliver|release)|bowling|delivering|"
        r"in\s+process\s+of\s+bowling|preparing\s+to\s+bowl|"
        r"just\s+(?:bowled|delivered|released))\b[^.]*?\b(?:player|cricketer)\b",
        re.IGNORECASE | re.DOTALL,
    ),
]
INFERRED_BATTER_PATS = [
    re.compile(
        r"\b(?:player|cricketer)\b[^.]*?\b(?:holding\s+(?:a\s+|the\s+)?bat|"
        r"at\s+bat|at\s+the\s+(?:wicket|crease)|"
        r"with\s+(?:a\s+|the\s+)?bat\s+raised|"
        r"preparing\s+to\s+(?:bat|hit|play\s+a\s+shot))\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:holding\s+(?:a\s+|the\s+)?bat|at\s+the\s+(?:wicket|crease)|"
        r"with\s+(?:a\s+|the\s+)?bat\s+raised)\b[^.]*?\b(?:player|cricketer)\b",
        re.IGNORECASE | re.DOTALL,
    ),
]
INFERRED_FIELDER_PATS = [
    re.compile(
        r"\b(?:player|cricketer)\b[^.]*?\b(?:walking|standing|positioned|"
        r"scattered)\b[^.]*?\b(?:field|pitch|wicket|crease|stumps)\b",
        re.IGNORECASE | re.DOTALL,
    ),
]

CRICKET_GEOMETRY_PATTERNS = [
    re.compile(r"\b(pitch|wicket|wickets|stumps|crease|"
               r"the\s+field|cricket\s+field|cricket\s+pitch)\b",
               re.IGNORECASE),
]

W_PATTERNS = [
    re.compile(r"\bwide\s+(?:field|pitch)\s+view\b", re.IGNORECASE),
    re.compile(r"\bwide-angle\s+view\b", re.IGNORECASE),
    re.compile(r"\bwide-angle\s+view\s+of\s+(?:the\s+)?(?:playing\s+area|cricket\s+(?:field|pitch))\b", re.IGNORECASE),
    re.compile(r"\b(?:cricket\s+)?(?:field|pitch)\s+with\s+(?:several\s+|multiple\s+|many\s+)?(?:players|fielders|cricket\s+players|batsmen|batters)\s+(?:positioned|scattered|on\s+the\s+(?:field|pitch))\b", re.IGNORECASE),
    re.compile(r"\bframe\s+shows\s+(?:a\s+)?cricket\s+(?:field|pitch)\b", re.IGNORECASE),
    re.compile(r"\bview\s+of\s+(?:a\s+)?cricket\s+(?:field|pitch)\s+with\s+(?:players|fielders|several\s+players)\b", re.IGNORECASE),
]

K_PATTERN = re.compile(
    r"\b(TATA\s+IPL|JioHotstar|Delhi\s+Capitals|Chennai\s+Super\s+Kings|"
    r"Super\s+Kings|Capitals|Yono\s+SBI|TATA\s+AIG|RuPay|KINGFISHER|"
    r"FedEx|Etihad|Hero\s+FinCorp|Britannia)\b",
    re.IGNORECASE,
)

S_PATTERNS = [
    re.compile(r"\b(DC|CSK|MI|RCB|KKR|GT|SRH|RR|PBKS|LSG)\s+\d+[-/]\d+\b"),
    re.compile(r"\b\d+\.\d+\s+(?:over|ball)\b", re.IGNORECASE),
    re.compile(r"\b[A-Z]{3,}\s+\d+-\d+\s+\d+\b"),
    re.compile(r"(?:DC\s+vs\s+CSK|Capitals\s+vs\s+Super\s+Kings).*?\d+", re.IGNORECASE),
    re.compile(r"\b\d+\.\d+\s*(?:B|over)\b", re.IGNORECASE),
]

SS_PATTERNS = [
    re.compile(r"\bscore\s+(?:graphic|strip|display|board|ticker|line)\b", re.IGNORECASE),
    re.compile(r"\bscoreboard\s+(?:at|along|on)?\s*(?:the\s+)?(?:bottom|top)\b", re.IGNORECASE),
    re.compile(r"\bscoreboard\s+(?:with|displaying|showing)\b", re.IGNORECASE),
    re.compile(r"\bscore\s+display\b", re.IGNORECASE),
]
SS_LOOSE_PATTERNS = [
    re.compile(
        r"\b(?:displaying|showing|including|features?|displays?|with)\b.{0,80}"
        r"\bscore(?:s)?\b.{0,80}\b(?:player|team|run\s+rate|over|wicket|standings)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\bscore(?:s)?\s*,\s*(?:player|team|run\s+rate|over|wicket|standings)",
        re.IGNORECASE,
    ),
    re.compile(r"\bcurrent\s+score\b", re.IGNORECASE),
    re.compile(
        r"\b(?:displaying|showing)\s+(?:the\s+)?(?:current\s+)?score(?:\s+(?:and|,))",
        re.IGNORECASE,
    ),
    # Wicket-ball-speed and ball-speed graphics are post-delivery info
    # cards — semantically equivalent to a score-strip overlay for
    # gating purposes. Boundary extractor S9 still uses these as a
    # delivery-end stop marker.
    re.compile(r"\bWICKET\s+BALL\s+SPEED\b", re.IGNORECASE),
    re.compile(r"\bball\s+speed\s+(?:graphic|banner|reading|of\s+\d)", re.IGNORECASE),
    re.compile(r"\b\d+(?:\.\d+)?\s*kph\b", re.IGNORECASE),
]

HARD_REJECT_PATTERNS = [
    # Case-insensitive: true replay/recap/montage markers + ULTRAEDGE.
    re.compile(r"\b(?:slow[-\s]motion|slo[-\s]?mo|recap|highlight\s+reel|montage|ULTRAEDGE)\b", re.IGNORECASE),
    # Case-sensitive: only the caps "REPLAY" badge (Scout's lowercase
    # interpretation "during a replay" should NOT hard-reject the
    # post-wicket info-card frame).
    re.compile(r"\bREPLAY\b"),
    re.compile(r"\binstant\s+replay\b", re.IGNORECASE),
    re.compile(r"\bUGREEN\b"),
    re.compile(r"\bChutney\s+Couple\b", re.IGNORECASE),
    re.compile(r"\b(?:indoor|office|study|desk|laptop|shelf|bookshelf)\b", re.IGNORECASE),
    # Fix 8: between-balls bowler-intro / stats-card overlays.
    re.compile(r"\bplayer\s+profile\s+(?:and\s+)?statistics\b", re.IGNORECASE),
    re.compile(r"\bplayer\s+profile\s+(?:with|showing|displaying|featuring)\b",
               re.IGNORECASE),
    re.compile(r"\brecent\s+form\s+statistics\b", re.IGNORECASE),
    re.compile(r"\bbowler\s+profile\b", re.IGNORECASE),
    re.compile(r"\bbowling\s+stats?\s+(?:card|graphic|panel|display)\b",
               re.IGNORECASE),
]

# Fix 12b: post-wicket info-card detector. Frame is HARD_REJECT if
# POST_WICKET_INFO_PAT matches AND no LIVE_SCORE_MARKER is present.
POST_WICKET_INFO_PAT = re.compile(
    r"\bWICKET\s+BALL\s+SPEED\b\s*\d+(?:\.\d+)?\s*kph\b|"
    r"\bball\s+speed\s+(?:after\s+)?(?:wicket|six|four)\b",
    re.IGNORECASE,
)
LIVE_SCORE_MARKER_PAT = re.compile(
    # Team abbrev + score-with-overs (e.g. "DC 61-4 9.2", "CSK 47/3")
    r"\b(DC|CSK|MI|RCB|KKR|GT|SRH|RR|PBKS|LSG)\s+\d+[-/]\d+(?:\s+\d+(?:\.\d+)?)?\b|"
    # Decimal overs ("9.2 overs", "5.1 over")
    r"\b\d+\.\d+\s+(?:over|overs|ball)\b|"
    # "over 9.2"
    r"\bover\s+\d+\.\d+\b|"
    # Run rate
    r"\brun[-\s]rate\b",
    re.IGNORECASE,
)

# Fix 11: replay-mode score overlay. Full team name + score + plain
# over number (no decimal) is the format Scout sees on replay/recap
# graphics. If matched without any live-scorebar marker, frame is
# HARD_REJECT.
REPLAY_SCORE_PAT = re.compile(
    r"\b(?:CAPITALS|SUPER\s+KINGS|MUMBAI\s+INDIANS|ROYAL\s+CHALLENGERS|"
    r"KOLKATA\s+KNIGHT\s+RIDERS|GUJARAT\s+TITANS|RAJASTHAN\s+ROYALS|"
    r"PUNJAB\s+KINGS|LUCKNOW\s+SUPER\s+GIANTS|SUNRISERS\s+HYDERABAD|"
    r"CHENNAI\s+SUPER\s+KINGS|DELHI\s+CAPITALS)\s+\d+[-/]\d+\s+\(?\d+\)?\b",
    re.IGNORECASE,
)

CROWD_SHOT_PAT = re.compile(r"\bcrowd\s+shot\b", re.IGNORECASE)
CHEERING_PAT = re.compile(r"\bcheering\b", re.IGNORECASE)
FIELD_PAT = re.compile(r"\b(field|pitch|stumps|wicket|crease)\b", re.IGNORECASE)

# Negation context check for HARD_REJECT matches: phrases like "no
# indication of replay", "not in slow-motion" should not hard-reject.
NEGATION_BEFORE_PAT = re.compile(
    r"\b(?:no|not|without|absent|absence\s+of|no\s+indication\s+of|"
    r"there\s+is\s+no|there\s+are\s+no|"
    r"hasn'?t|isn'?t|wasn'?t|aren'?t|haven'?t|"
    r"has\s+not(?:\s+yet)?|have\s+not(?:\s+yet)?|"
    r"is\s+not|are\s+not|was\s+not|were\s+not|"
    r"never|cannot|can'?t)"
    r"\b\s+(?:\w+\s+){0,4}$",
    re.IGNORECASE,
)

HEDGE_AFTER_V_PAT = re.compile(
    r"^[,\s]*(?:\w+\s+){0,2}\bor\s+(?:about\s+to|preparing\s+to|"
    r"may(?:be)?|might|perhaps|possibly|could)\b",
    re.IGNORECASE,
)

# Bowler-returning-to-mark hedge: V verb "just bowled/delivered/released/
# thrown the ball" followed by "and is walking back" (no "away" / "to the
# crease" disambiguator) indicates the frame is between-balls (bowler
# returning to bowling mark), not a fresh delivery moment.
BOWLER_WALKBACK_AFTER_V_PAT = re.compile(
    r"^[\s,]*(?:the\s+)?(?:ball\s+)?and\s+is\s+walking\s+back"
    r"(?!\s+(?:away|to\s+the\s+(?:crease|pavilion|dressing)))",
    re.IGNORECASE,
)

# Disjunction-before V: prose like "in the process of bowling or about
# to bowl" — pattern 'about to bowl' would match the second alternative.
# Treat as hedged when the preceding clause ends with another V-verb
# followed by ' or '.
HEDGE_BEFORE_V_PAT = re.compile(
    r"\b(?:bowling|delivering|throwing|swinging|hitting|bowled|"
    r"delivered|thrown|swung|hit|played|released|struck|"
    r"action|stride|follow[-\s]through)\b[,\s]*or\s*$"
    r"|"
    r"\b(?:possibly|perhaps|maybe|appears\s+to\s+be|seems\s+to\s+be|"
    r"likely|may\s+have|might\s+have)\s+"
    r"(?:[\w,'-]+\s+){0,4}$",
    re.IGNORECASE,
)


def _hedge_after(text: str, end: int) -> bool:
    suffix = text[end: end + 50]
    if HEDGE_AFTER_V_PAT.match(suffix):
        return True
    if BOWLER_WALKBACK_AFTER_V_PAT.match(suffix):
        return True
    return False


def _hedge_before(text: str, start: int) -> bool:
    return bool(HEDGE_BEFORE_V_PAT.search(text[max(0, start - 60): start]))


def v_match(text: str) -> bool:
    """V signal with negation-context + hedge-after guards. Returns True
    if any V_PATTERN matches and is NOT preceded within ~30 chars by a
    negation phrase ('no', 'not', 'without', 'has not yet', etc.) AND
    is NOT immediately followed by a hedge-disjunction ('or about to
    bowl', 'or maybe ...')."""
    for pattern in V_PATTERNS:
        for m in pattern.finditer(text):
            prefix = text[max(0, m.start() - 30): m.start()]
            if NEGATION_BEFORE_PAT.search(prefix):
                continue
            if _hedge_after(text, m.end()):
                continue
            if _hedge_before(text, m.start()):
                continue
            return True
    return False


def v_post_match(text: str) -> bool:
    """V_post signal — fires only on post-delivery action markers (the
    ball was actually released / hit / swung / followed-through), with
    the same negation-context + hedge-after guards as v_match. Used to
    filter clusters that contain only pre-action setup (about to bowl,
    running in) without a real release frame."""
    for pattern in V_POST_PATTERNS:
        for m in pattern.finditer(text):
            prefix = text[max(0, m.start() - 30): m.start()]
            if NEGATION_BEFORE_PAT.search(prefix):
                continue
            if _hedge_after(text, m.end()):
                continue
            if _hedge_before(text, m.start()):
                continue
            return True
    return False


def hard_match(text: str) -> bool:
    """HARD_REJECT match with negation-context guard. A match preceded
    within 30 chars by 'no'/'not'/'without'/'no indication of' is
    treated as negated and ignored."""
    for p in HARD_REJECT_PATTERNS:
        m = p.search(text)
        if not m:
            continue
        prefix = text[max(0, m.start() - 60): m.start()]
        if NEGATION_BEFORE_PAT.search(prefix):
            continue
        return True
    # Fix 12b: post-wicket info-card overlay with no live scorebar.
    if POST_WICKET_INFO_PAT.search(text) and not LIVE_SCORE_MARKER_PAT.search(text):
        return True
    # Fix 11: replay-mode score format (full team name + plain over)
    # without live scorebar.
    if REPLAY_SCORE_PAT.search(text) and not LIVE_SCORE_MARKER_PAT.search(text):
        return True
    return False


@dataclass
class Signals:
    V: bool = False
    V_post: bool = False
    S: bool = False
    M: bool = False
    M2: bool = False
    W: bool = False
    K: bool = False
    SS: bool = False
    SS_via_loose: bool = False
    CG: bool = False
    HARD: bool = False
    role_count: int = 0


def matches_any(patterns, text: str) -> bool:
    return any(p.search(text) for p in patterns)


def extract_signals(text: str) -> Signals:
    s = Signals()
    s.V = v_match(text)
    s.V_post = v_post_match(text)
    low = text.lower()
    seen_loose: set[str] = set()
    for r in ROLES_LOOSE:
        if re.search(rf"\b{re.escape(r)}\b", low):
            seen_loose.add(r)
    seen_strict = {r for r in seen_loose if r in ROLES_STRICT}
    inferred = 0
    if matches_any(INFERRED_BOWLER_PATS, text) and "bowler" not in seen_strict:
        inferred += 1
    if matches_any(INFERRED_BATTER_PATS, text) and not (
        "batter" in seen_strict or "batters" in seen_strict
        or "batsman" in seen_strict or "batsmen" in seen_strict
    ):
        inferred += 1
    if matches_any(INFERRED_FIELDER_PATS, text) and not (
        "fielder" in seen_strict or "fielders" in seen_strict
    ):
        inferred += 1
    s.role_count = len(seen_loose)
    s.M = len(seen_loose) >= 1
    s.M2 = (len(seen_strict) + inferred) >= 2
    s.CG = matches_any(CRICKET_GEOMETRY_PATTERNS, text)
    s.W = matches_any(W_PATTERNS, text)
    s.K = bool(K_PATTERN.search(text))
    s.S = matches_any(S_PATTERNS, text)
    ss_strict = s.S or matches_any(SS_PATTERNS, text)
    ss_loose = matches_any(SS_LOOSE_PATTERNS, text)
    s.SS = ss_strict or ss_loose
    s.SS_via_loose = ss_loose and not ss_strict
    s.HARD = hard_match(text)
    if not s.HARD:
        if CROWD_SHOT_PAT.search(text) and CHEERING_PAT.search(text):
            if not FIELD_PAT.search(text):
                s.HARD = True
    return s


def matches_v_loose(text: str) -> bool:
    return matches_any(V_LOOSE_PATTERNS, text)
