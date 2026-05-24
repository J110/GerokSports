"""Cricbuzz ground-truth → UIBallSnapshot ingester.

Two input modes:

1. ``--ledger PATH`` (default) — reads the curated per-ball JSON ledger
   (`files/tests/fixtures/dc_vs_kkr_2026_152064_ledger.json`). Covers
   overs 1-6 of DC innings, no extras, one wicket. Format documented
   in that file's ``_metadata`` block.

2. ``--commentary PATH`` — reads the reverse-chronological Cricbuzz
   commentary markdown
   (`files/tests/fixtures/dckkr_innings_1_cricbuzz_commentary.md`).
   Full innings 1 coverage (~120 legal balls + wides + compound events).
   Format spec: design memo §7 Step 5b.1.

Both modes emit the same `UIBallSnapshot` JSONL schema so the diff
harness consumes them identically. Multi-event frames (e.g. 10.2's
wicket-on-wide + wide + 1-run trio) are disambiguated via
``event_index``, an integer that starts at 0 for each fresh
``over_ball`` coordinate and increments on collision.

Name canonicalisation: last-name-only with overrides for the cases
where the pipeline diverges from a naive last-token rule.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


NAME_OVERRIDES: dict[str, str] = {
    "Varun Chakravarthy": "Chakaravarthy",
    "Varun Chakaravarthy": "Chakaravarthy",
}


def canonical_name(full_name: str | None) -> str | None:
    if not full_name:
        return None
    stripped = full_name.strip()
    if stripped in NAME_OVERRIDES:
        return NAME_OVERRIDES[stripped]
    return stripped.split()[-1]


@dataclass
class UIBallSnapshot:
    over_ball: str
    score: int
    wickets: int
    balls_total: int
    striker_name: str | None
    striker_runs: int
    striker_balls: int
    striker_fours: int
    striker_sixes: int
    non_striker_name: str | None
    non_striker_runs: int
    non_striker_balls: int
    non_striker_fours: int
    non_striker_sixes: int
    bowler_name: str | None
    bowler_overs: str | None
    bowler_runs: int
    bowler_wickets: int
    event_index: int = 0
    this_over_tokens: list[str] = field(default_factory=list)
    recent_over_n_minus_1: list[str] = field(default_factory=list)
    partnership_runs: int = 0
    partnership_balls: int = 0
    extras_total: int = 0
    extras_wd: int = 0
    extras_nb: int = 0
    extras_b: int = 0
    extras_lb: int = 0
    fow_entries: list[list[Any]] = field(default_factory=list)


def _legal_balls_from_overs(overs_str: str | None) -> int:
    if not overs_str:
        return 0
    try:
        completed, balls = overs_str.split(".")
        return int(completed) * 6 + int(balls)
    except (ValueError, AttributeError):
        return 0


def _completed_over_index(overs_str: str | None) -> int | None:
    if not overs_str:
        return None
    try:
        completed, balls = overs_str.split(".")
        if int(balls) == 0:
            return int(completed) - 1
        return None
    except (ValueError, AttributeError):
        return None


def _extract_card(card: dict | None, name: str | None) -> dict:
    if not card or not name:
        return {}
    return card.get(name) or {}


# ─────────────────────────────────────────────────────────────────────
# Mode 1: ledger JSON → snapshots (existing path, unchanged behavior)
# ─────────────────────────────────────────────────────────────────────

def _ball_to_snapshot_from_ledger(
    ball: dict,
    fow_accumulator: list[list[Any]],
) -> UIBallSnapshot:
    state = ball.get("expected_state_after", {}) or {}
    over_ball = ball.get("ball_id", "")
    overs_str = state.get("overs") or over_ball

    striker_full = state.get("striker_after_rotation") or ball.get("striker_name")
    non_full = state.get("non_striker_after_rotation") or ball.get("non_striker_name")
    bowler_full = ball.get("bowler_name")

    striker = canonical_name(striker_full)
    non = canonical_name(non_full)
    bowler = canonical_name(bowler_full)

    bcard = state.get("batting_card") or {}
    bowl_card = state.get("bowling_card") or {}

    striker_slot = _extract_card(bcard, striker_full)
    non_slot = _extract_card(bcard, non_full)
    bowler_slot = _extract_card(bowl_card, bowler_full)

    extras_total = int(ball.get("extras") or 0)
    extras_type = (ball.get("extras_type") or "").lower()
    extras_wd = extras_total if extras_type in ("wd", "wide") else 0
    extras_nb = extras_total if extras_type in ("nb", "no_ball", "noball") else 0
    extras_b = extras_total if extras_type in ("b", "bye") else 0
    extras_lb = extras_total if extras_type in ("lb", "leg_bye", "legbye") else 0

    wicket = ball.get("wicket")
    if wicket:
        fow_accumulator.append([
            int(state.get("score") or 0),
            int(state.get("wickets") or len(fow_accumulator) + 1),
            canonical_name(wicket.get("batter") or ball.get("striker_name")),
            overs_str,
        ])

    completed = _completed_over_index(overs_str)
    over_history = state.get("over_history") or {}
    recent = []
    if completed is not None and completed >= 0:
        recent = over_history.get(str(completed)) or over_history.get(completed) or []

    return UIBallSnapshot(
        over_ball=over_ball,
        score=int(state.get("score") or 0),
        wickets=int(state.get("wickets") or 0),
        balls_total=_legal_balls_from_overs(overs_str),
        striker_name=striker,
        striker_runs=int(striker_slot.get("runs") or 0),
        striker_balls=int(striker_slot.get("balls_faced") or striker_slot.get("balls") or 0),
        striker_fours=int(striker_slot.get("fours") or 0),
        striker_sixes=int(striker_slot.get("sixes") or 0),
        non_striker_name=non,
        non_striker_runs=int(non_slot.get("runs") or 0),
        non_striker_balls=int(non_slot.get("balls_faced") or non_slot.get("balls") or 0),
        non_striker_fours=int(non_slot.get("fours") or 0),
        non_striker_sixes=int(non_slot.get("sixes") or 0),
        bowler_name=bowler,
        bowler_overs=bowler_slot.get("overs"),
        bowler_runs=int(bowler_slot.get("runs") or 0),
        bowler_wickets=int(bowler_slot.get("wickets") or 0),
        event_index=0,
        this_over_tokens=list(state.get("this_over") or []),
        recent_over_n_minus_1=list(recent),
        partnership_runs=0,
        partnership_balls=0,
        extras_total=extras_total,
        extras_wd=extras_wd,
        extras_nb=extras_nb,
        extras_b=extras_b,
        extras_lb=extras_lb,
        fow_entries=[list(e) for e in fow_accumulator],
    )


def ingest_ledger(ledger_path: Path, out_path: Path) -> int:
    with ledger_path.open() as fh:
        ledger = json.load(fh)
    balls = ledger.get("balls") or []
    fow_acc: list[list[Any]] = []
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with out_path.open("w") as out:
        for ball in balls:
            snap = _ball_to_snapshot_from_ledger(ball, fow_acc)
            out.write(json.dumps(asdict(snap)) + "\n")
            written += 1
    print(f"Ingested {written} ball snapshots from {ledger_path} → {out_path}")
    return 0


# ─────────────────────────────────────────────────────────────────────
# Mode 2: Cricbuzz commentary markdown → snapshots (new path)
# ─────────────────────────────────────────────────────────────────────


@dataclass
class _Event:
    over_ball: str               # "10.2"
    bowler_full: str             # "Anukul Roy"
    batter_full: str             # "Pathum Nissanka"
    outcome_raw: str             # "wide, out Stumped!!"
    commentary: str              # everything after the outcome
    new_batter_full: str | None = None  # "comes to the crease" name (if any)


_BALL_COORD_RE = re.compile(r"^(\d{1,2})\.(\d)$")
_BALL_LINE_RE = re.compile(
    r"^(?P<bowler>[^,]+?)\s+to\s+(?P<batter>[^,]+?),\s*(?P<rest>.+)$"
)
_NEW_BATTER_RE = re.compile(
    r"^(?P<name>[A-Z][A-Za-z' .-]+?),\s+(?:right|left)[\s-]+handed bat,\s+comes to the crease",
    re.IGNORECASE,
)
_THATS_OUT_RE = re.compile(r",\s*THATS OUT!!", re.IGNORECASE)


def _parse_commentary_events(commentary_path: Path) -> list[_Event]:
    """Walk the reverse-chronological commentary file and yield
    `_Event` records in CHRONOLOGICAL order.

    Each event records the over_ball, the bowler/batter, the raw
    outcome string ("no run", "1 run", "FOUR", "wide", "out Caught
    by ...", "wide, out Stumped!!" etc.), and an optional new-batter
    arrival (the post-wicket replacement, scraped from the
    "comes to the crease" line immediately preceding the wicket
    event in file order).
    """
    raw_lines = commentary_path.read_text().splitlines()
    lines = [ln.strip() for ln in raw_lines if ln.strip()]

    # First pass: locate ball-coord anchors and group following lines
    # until the next anchor / "Over N" line.
    events_rev: list[_Event] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        m = _BALL_COORD_RE.match(line)
        if not m:
            i += 1
            continue
        over_ball = f"{int(m.group(1))}.{int(m.group(2))}"
        # Collect lines belonging to this ball entry until the next
        # ball-coord, "Over N" header, or "Over Summary" / "View all
        # overs" markers.
        i += 1
        body: list[str] = []
        while i < n:
            nxt = lines[i]
            if _BALL_COORD_RE.match(nxt):
                break
            if nxt.startswith("Over ") and nxt.split()[1].isdigit():
                break
            if nxt in ("Over Summary", "View all overs"):
                break
            body.append(nxt)
            i += 1
        # Find canonical ball line in body (the first "X to Y, ..." line
        # that is NOT the "THATS OUT!!" duplicate).
        canonical = None
        new_batter = None
        for b in body:
            if _THATS_OUT_RE.search(b):
                continue
            mm = _BALL_LINE_RE.match(b)
            if mm and canonical is None:
                canonical = mm
            else:
                nb = _NEW_BATTER_RE.match(b)
                if nb:
                    new_batter = nb.group("name").strip()
        if canonical is None:
            continue
        rest = canonical.group("rest")
        # Split outcome from commentary on the first comma — BUT preserve
        # a "wide, out X!!" compound prefix as the full outcome so the
        # classifier can see the wicket indicator that follows the wide.
        if rest.lower().startswith(("wide,", "no ball,", "no-ball,")):
            head, _, tail = rest.partition(",")
            tail = tail.lstrip()
            if tail.lower().startswith("out "):
                # Take through the next sentence-ending !! as outcome.
                m2 = re.match(r"(out\s+[^!]*!!)\s*(.*)", tail, re.IGNORECASE)
                if m2:
                    outcome = f"{head.strip()}, {m2.group(1).strip()}"
                    commentary = m2.group(2).strip()
                else:
                    outcome, commentary = rest.split(",", 1)
                    outcome = outcome.strip()
                    commentary = commentary.strip()
            else:
                outcome, commentary = rest.split(",", 1)
                outcome = outcome.strip()
                commentary = commentary.strip()
        elif "," in rest:
            outcome, commentary = rest.split(",", 1)
            outcome = outcome.strip()
            commentary = commentary.strip()
        else:
            outcome, commentary = rest.strip(), ""
        events_rev.append(_Event(
            over_ball=over_ball,
            bowler_full=canonical.group("bowler").strip(),
            batter_full=canonical.group("batter").strip(),
            outcome_raw=outcome,
            commentary=commentary,
            new_batter_full=new_batter,
        ))
    # File is reverse-chronological → reverse to get chronological.
    events_rev.reverse()
    return events_rev


@dataclass
class _State:
    score: int = 0
    wickets: int = 0
    legal_balls_total: int = 0
    extras_total: int = 0
    extras_wd: int = 0
    extras_nb: int = 0
    extras_b: int = 0
    extras_lb: int = 0
    this_over_tokens: list[str] = field(default_factory=list)
    over_history: dict[int, list[str]] = field(default_factory=dict)
    fow: list[list[Any]] = field(default_factory=list)
    batting: dict[str, dict] = field(default_factory=dict)
    bowling: dict[str, dict] = field(default_factory=dict)
    striker_full: str | None = None
    non_striker_full: str | None = None
    current_over: int = 0
    legal_balls_this_over: int = 0
    # Map for next-bowler bootstrap (first ball of an over names them)
    last_bowler_full: str | None = None


def _ensure_batter(state: _State, full: str) -> dict:
    slot = state.batting.get(full)
    if slot is None:
        slot = {
            "runs": 0,
            "balls_faced": 0,
            "fours": 0,
            "sixes": 0,
            "status": "batting",
        }
        state.batting[full] = slot
    return slot


def _ensure_bowler(state: _State, full: str) -> dict:
    slot = state.bowling.get(full)
    if slot is None:
        slot = {
            "overs": "0.0",
            "balls": 0,
            "runs": 0,
            "wickets": 0,
            "maidens": 0,
        }
        state.bowling[full] = slot
    return slot


def _classify_outcome(text: str) -> dict:
    """Parse the comma-separated outcome prefix of a ball line.

    Returns a dict with keys:
      runs_off_bat: int   (runs credited to striker)
      total_runs:   int   (total runs added to team score this ball)
      legal_ball:   bool  (False for wide / no-ball without bat)
      wicket:       bool  (dismissal taken)
      wide:         bool
      no_ball:      bool
      bye:          int
      leg_bye:      int
      boundary_token: str | None  ("4" / "6" or None)
    """
    t = text.strip().lower()
    out = {
        "runs_off_bat": 0, "total_runs": 0,
        "legal_ball": True, "wicket": False,
        "wide": False, "no_ball": False,
        "bye": 0, "leg_bye": 0,
        "boundary_token": None,
    }
    # Wide (possibly compound with wicket)
    if t.startswith("wide"):
        out["wide"] = True
        out["legal_ball"] = False
        out["total_runs"] = 1  # base wide = 1 extra
        if re.search(r"\bout\b", t):
            out["wicket"] = True
        return out
    # No ball
    if t.startswith("no ball") or t.startswith("no-ball"):
        out["no_ball"] = True
        out["legal_ball"] = False
        out["total_runs"] = 1
        if re.search(r"\bout\b", t):
            out["wicket"] = True
        return out
    # Boundary keyword
    if t.startswith("four"):
        out["runs_off_bat"] = 4
        out["total_runs"] = 4
        out["boundary_token"] = "4"
        return out
    if t.startswith("six"):
        out["runs_off_bat"] = 6
        out["total_runs"] = 6
        out["boundary_token"] = "6"
        return out
    # Numeric runs ("N run" / "N runs")
    m = re.match(r"^(\d+)\s+runs?$", t)
    if m:
        n = int(m.group(1))
        out["runs_off_bat"] = n
        out["total_runs"] = n
        if n == 4:
            out["boundary_token"] = "4"
        elif n == 6:
            out["boundary_token"] = "6"
        return out
    # Dot
    if t == "no run":
        return out
    # Out (legal ball wicket — caught, bowled, lbw, run out, stumped)
    if t.startswith("out "):
        out["wicket"] = True
        return out
    # Leg-bye / bye
    m = re.match(r"^(\d+)\s+leg\s*byes?$", t)
    if m:
        out["leg_bye"] = int(m.group(1))
        out["total_runs"] = int(m.group(1))
        return out
    m = re.match(r"^(\d+)\s+byes?$", t)
    if m:
        out["bye"] = int(m.group(1))
        out["total_runs"] = int(m.group(1))
        return out
    # Fallback: treat as dot (no runs, no wicket)
    return out


def _format_overs_after_ball(over: int, balls_this_over: int) -> str:
    if balls_this_over == 0:
        return f"{over}.0"
    return f"{over}.{balls_this_over}"


def _format_bowler_overs(slot: dict) -> str:
    b = int(slot.get("balls") or 0)
    return f"{b // 6}.{b % 6}"


def _snapshot(
    state: _State, over_ball: str, event_index: int,
    bowler_full: str,
) -> UIBallSnapshot:
    striker = canonical_name(state.striker_full)
    non = canonical_name(state.non_striker_full)
    bowler = canonical_name(bowler_full)

    s_slot = state.batting.get(state.striker_full) or {}
    n_slot = state.batting.get(state.non_striker_full) or {}
    bw_slot = state.bowling.get(bowler_full) or {}

    # recent_over_n_minus_1: populate on the first legal ball of any
    # over > 0 (covers both ".0" rollover and ".1" ball_id conventions).
    completed = _completed_over_index(over_ball)
    recent = []
    if completed is not None and completed >= 0:
        recent = state.over_history.get(completed) or []
    else:
        try:
            c_str, b_str = over_ball.split(".")
            c, b = int(c_str), int(b_str)
            if b == 1 and c > 0:
                recent = state.over_history.get(c - 1) or []
        except (ValueError, AttributeError):
            pass

    return UIBallSnapshot(
        over_ball=over_ball,
        score=state.score,
        wickets=state.wickets,
        balls_total=state.legal_balls_total,
        striker_name=striker,
        striker_runs=int(s_slot.get("runs") or 0),
        striker_balls=int(s_slot.get("balls_faced") or 0),
        striker_fours=int(s_slot.get("fours") or 0),
        striker_sixes=int(s_slot.get("sixes") or 0),
        non_striker_name=non,
        non_striker_runs=int(n_slot.get("runs") or 0),
        non_striker_balls=int(n_slot.get("balls_faced") or 0),
        non_striker_fours=int(n_slot.get("fours") or 0),
        non_striker_sixes=int(n_slot.get("sixes") or 0),
        bowler_name=bowler,
        bowler_overs=_format_bowler_overs(bw_slot) if bw_slot else None,
        bowler_runs=int(bw_slot.get("runs") or 0),
        bowler_wickets=int(bw_slot.get("wickets") or 0),
        event_index=event_index,
        this_over_tokens=list(state.this_over_tokens),
        recent_over_n_minus_1=list(recent),
        partnership_runs=0,
        partnership_balls=0,
        extras_total=state.extras_total,
        extras_wd=state.extras_wd,
        extras_nb=state.extras_nb,
        extras_b=state.extras_b,
        extras_lb=state.extras_lb,
        fow_entries=[list(e) for e in state.fow],
    )


def _apply_event(
    state: _State, ev: _Event, event_index: int,
) -> UIBallSnapshot:
    parsed = _classify_outcome(ev.outcome_raw)
    over_n = int(ev.over_ball.split(".")[0])
    bowler_full = ev.bowler_full
    batter_full = ev.batter_full

    # New over rollover: when we cross from one over to a different one,
    # commit previous over to over_history and reset this_over.
    # End-of-over striker rotation is applied EAGERLY at end of the
    # 6th legal ball below (before snapshot), to match the pipeline's
    # eager-rotation convention. So no rotation here on the rollover.
    if over_n != state.current_over and state.legal_balls_this_over > 0:
        state.over_history[state.current_over] = list(state.this_over_tokens)
        state.this_over_tokens = []
        state.legal_balls_this_over = 0
        state.current_over = over_n
    elif over_n != state.current_over:
        state.current_over = over_n

    # Striker / bowler bootstrap from the ball line itself.
    if state.striker_full is None:
        state.striker_full = batter_full
        _ensure_batter(state, batter_full)
    elif state.striker_full != batter_full and state.non_striker_full != batter_full:
        # Batter on strike doesn't match either crease slot — likely
        # a stale post-rotation rollover. Set striker to this batter
        # without losing non-striker tracking.
        state.striker_full = batter_full
        _ensure_batter(state, batter_full)
    elif state.non_striker_full == batter_full and state.striker_full != batter_full:
        # Striker rotated by previous ball but state lagged.
        state.striker_full, state.non_striker_full = (
            batter_full, state.striker_full)
        _ensure_batter(state, batter_full)
    else:
        _ensure_batter(state, batter_full)
    _ensure_bowler(state, bowler_full)
    state.last_bowler_full = bowler_full

    striker_slot = state.batting[batter_full]
    bowler_slot = state.bowling[bowler_full]

    # Update extras counters
    if parsed["wide"]:
        state.extras_wd += parsed["total_runs"]
        state.extras_total += parsed["total_runs"]
    if parsed["no_ball"]:
        state.extras_nb += parsed["total_runs"]
        state.extras_total += parsed["total_runs"]
    if parsed["bye"]:
        state.extras_b += parsed["bye"]
        state.extras_total += parsed["bye"]
    if parsed["leg_bye"]:
        state.extras_lb += parsed["leg_bye"]
        state.extras_total += parsed["leg_bye"]

    # Team score: add total_runs (which already includes the +1 base
    # for wide/no-ball, runs_off_bat for bat, and bye/leg-bye runs).
    state.score += parsed["total_runs"]

    # Striker stats: only legal balls advance balls_faced; runs_off_bat
    # credits to striker on any delivery (rare on extras).
    if parsed["legal_ball"]:
        striker_slot["balls_faced"] = int(striker_slot.get("balls_faced") or 0) + 1
    striker_slot["runs"] = int(striker_slot.get("runs") or 0) + parsed["runs_off_bat"]
    if parsed["boundary_token"] == "4":
        striker_slot["fours"] = int(striker_slot.get("fours") or 0) + 1
    elif parsed["boundary_token"] == "6":
        striker_slot["sixes"] = int(striker_slot.get("sixes") or 0) + 1

    # Bowler stats: balls only on legal; runs include extras except byes/leg-byes.
    if parsed["legal_ball"]:
        bowler_slot["balls"] = int(bowler_slot.get("balls") or 0) + 1
    bowler_runs_credit = parsed["runs_off_bat"]
    if parsed["wide"]:
        bowler_runs_credit += parsed["total_runs"]
    if parsed["no_ball"]:
        bowler_runs_credit += parsed["total_runs"]
    bowler_slot["runs"] = int(bowler_slot.get("runs") or 0) + bowler_runs_credit

    # this_over token
    token = None
    if parsed["wicket"]:
        if parsed["wide"]:
            token = "Wd+W"
        elif parsed["no_ball"]:
            token = "Nb+W"
        elif parsed["boundary_token"] == "4":
            token = "4+W"
        elif parsed["boundary_token"] == "6":
            token = "6+W"
        elif parsed["runs_off_bat"] > 0:
            token = f"{parsed['runs_off_bat']}+W"
        else:
            token = "W"
    elif parsed["wide"]:
        token = "Wd"
    elif parsed["no_ball"]:
        token = "Nb"
    elif parsed["bye"]:
        token = f"{parsed['bye']}b"
    elif parsed["leg_bye"]:
        token = f"{parsed['leg_bye']}lb"
    elif parsed["boundary_token"]:
        token = parsed["boundary_token"]
    elif parsed["runs_off_bat"] == 0:
        token = "."
    else:
        token = str(parsed["runs_off_bat"])
    state.this_over_tokens.append(token)

    # Wicket bookkeeping
    if parsed["wicket"]:
        state.wickets += 1
        bowler_slot["wickets"] = int(bowler_slot.get("wickets") or 0) + 1
        # FoW: record post-state score + wkt#
        # overs_str = post-state legal-balls — for wide-with-wicket
        # the legal-ball counter doesn't advance, so the overs string
        # still reflects the prior legal ball.
        dismissed_canon = canonical_name(batter_full)
        # Striker is dismissed by convention (run-outs may dismiss
        # either, but ledger of cricket-truth in §7 maps to striker
        # in all 8 wickets for this fixture).
        striker_slot["status"] = "out"
        fow_overs = _format_overs_after_ball(
            state.current_over,
            state.legal_balls_this_over + (1 if parsed["legal_ball"] else 0),
        )
        state.fow.append([
            state.score, state.wickets, dismissed_canon, fow_overs,
        ])
        # Slot the new batter in: if the commentary attached a
        # "comes to the crease" name, use it; else leave striker None
        # so subsequent ball will hydrate.
        if ev.new_batter_full:
            new_full = ev.new_batter_full
            _ensure_batter(state, new_full)
            # New batter takes the dismissed batter's slot (striker)
            state.striker_full = new_full
        else:
            state.striker_full = None

    # Legal-ball / over counters
    if parsed["legal_ball"]:
        state.legal_balls_total += 1
        state.legal_balls_this_over += 1

    # Mid-over striker rotation for odd runs (not on wickets / extras-only)
    if (parsed["legal_ball"]
            and not parsed["wicket"]
            and parsed["runs_off_bat"] in (1, 3, 5)):
        state.striker_full, state.non_striker_full = (
            state.non_striker_full, state.striker_full)

    # End-of-over striker rotation, applied EAGERLY before snapshot at X.6
    # (when the 6th legal ball of this over has just been processed).
    # Pipeline convention: striker reflects post-end-of-over-swap at X.6.
    if parsed["legal_ball"] and state.legal_balls_this_over == 6:
        state.striker_full, state.non_striker_full = (
            state.non_striker_full, state.striker_full)

    # Build snapshot
    over_ball_str = _format_overs_after_ball(
        state.current_over, state.legal_balls_this_over)
    # For mid-over events the over_ball string already matches
    # ev.over_ball when parsed["legal_ball"] is True. For wides/no-balls
    # we still want to anchor on ev.over_ball coordinate (which encodes
    # "the pending legal ball this resolves into") so the diff lines up.
    if not parsed["legal_ball"]:
        over_ball_str = ev.over_ball
    return _snapshot(state, over_ball_str, event_index, bowler_full)


def ingest_commentary(commentary_path: Path, out_path: Path) -> int:
    events = _parse_commentary_events(commentary_path)
    state = _State()
    seen_at_coord: dict[str, int] = {}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with out_path.open("w") as out:
        for ev in events:
            # event_index: increment per (ev.over_ball) collision
            event_index = seen_at_coord.get(ev.over_ball, 0)
            seen_at_coord[ev.over_ball] = event_index + 1
            snap = _apply_event(state, ev, event_index)
            out.write(json.dumps(asdict(snap)) + "\n")
            written += 1
    print(
        f"Ingested {written} ball/extras events from {commentary_path} "
        f"→ {out_path}")
    print(
        f"Final state: score={state.score}/{state.wickets} "
        f"legal_balls={state.legal_balls_total} "
        f"extras=total:{state.extras_total} wd:{state.extras_wd} "
        f"nb:{state.extras_nb} b:{state.extras_b} lb:{state.extras_lb} "
        f"fow_count={len(state.fow)}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--ledger",
        type=Path,
        default=None,
        help="Curated per-ball JSON ledger (overs 1-6 only).",
    )
    p.add_argument(
        "--commentary",
        type=Path,
        default=None,
        help="Cricbuzz commentary markdown (full innings).",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "tests/fixtures/dckkr_ground_truth_ui_snapshots.jsonl",
    )
    args = p.parse_args()
    if args.commentary is not None:
        return ingest_commentary(args.commentary, args.output)
    if args.ledger is None:
        args.ledger = (
            Path(__file__).resolve().parents[1]
            / "tests/fixtures/dc_vs_kkr_2026_152064_ledger.json")
    return ingest_ledger(args.ledger, args.output)


if __name__ == "__main__":
    sys.exit(main())
