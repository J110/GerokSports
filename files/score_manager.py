"""ScoreManager — sole UI authority for the cricket pipeline.

Sits between the existing pipeline (Vision → Extractor → Scorer) and the
WebSocket UI.  Pure Python, no LLM calls.  Validates scorecard changes,
infers ball events, manages match state, and produces canonical UI payloads.
"""
from __future__ import annotations

import copy
import os
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

from card_helpers import _reconcile_bowler_overs
from cricket_rules import (
    Diff,
    validate_absolute,
    validate_diff,
)
from eyes.cricket_logger import CricketLogger
from eyes.this_over import ThisOverManager as _TOM

try:
    from cricket_rules import _cold_start_infer_gap_tokens as _infer_gap_tokens
except ImportError:
    _infer_gap_tokens = None
try:
    import trace_emitter as _trace
except ImportError:
    _trace = None
try:
    from eyes.frame_ledger import (
        get_ledger as _get_ledger,
        SmOutcome as _SmOutcome,
        _coerce_frame_id,
    )
except ImportError:
    _get_ledger = None
    _SmOutcome = None
    _coerce_frame_id = None


def _ledger_record(frame, outcome, payload=None):
    if _get_ledger is None:
        return
    fid = _coerce_frame_id(frame) if _coerce_frame_id else None
    if fid is None:
        return
    try:
        _get_ledger().record_sm_outcome(fid, outcome, payload=payload)
    except Exception:
        pass

log = CricketLogger("SCORE_MGR")

_is_legal_run_token = _TOM._is_legal_run_token
# _merge_broadcast removed 2026-05-20 (option G — broadcast wholesale-
# accept path deleted; ThisOverManager.on_broadcast_override gone).

# Policy U — absorbed legal-ball gap fill (Issue 3 Direction B).
ABSORBED_LEGAL = "ABSORBED_LEGAL"

# A1 part 2 (2026-05-14): bowler-credited dismissal taxonomy.  Only
# these wicket types credit the bowler's wickets column.  Run-outs,
# retired-hurt, obstructing-the-field, hit-the-ball-twice, timed-out,
# and unknowns do not.  ``bowler_wicket`` is the generic placeholder
# emitted by _infer_wicket before broadcast specifics arrive.
_BOWLER_CREDITED_DISMISSALS = frozenset({
    "bowled", "caught", "lbw", "stumped",
    "hit-wicket", "hit_wicket",
    "caught-and-bowled", "caught_and_bowled",
    "bowler_wicket",
})
# F381 wicket-attribution lag — raised 2026-05-19 from 10 to 40 in
# symmetry with `_PENDING_BOWLER_BALL_CREDIT_MAX_LAG` below. Same
# broadcast-cadence justification: at ~1Hz scout cadence the
# between-overs window where bowler attribution lags (camera on
# walking-back bowler, sponsor banners, standings ribbons) commonly
# exceeds 10 frames. The Tyagi handoff at the over-3-to-4 boundary
# in watch_20260519_121701 showed 31 frames of "bowler invisible";
# wicket attribution shares the same broadcast-coverage window, so
# the 10-frame threshold here was structurally guaranteed to orphan
# F381-class wickets too. 40 frames at 1Hz covers ≈6-7 balls of
# broadcast outage with margin.
_PENDING_WICKET_MAX_FRAME_LAG = 40
# Empirically tuned from L2-Slim captured-Scout replay (2026-05-19):
# Tyagi handoff at the over-3-to-4 boundary saw 31 frames of "bowler
# invisible to Scout" before SM resolved the new bowler — frames
# 288/290/303 queued, frame 319 first BOWL-DELTA Kartik Tyagi.
# 40 frames at ~1Hz scout cadence covers ≈6-7 balls of broadcast
# outage with margin, beyond which the attribution is genuinely
# indeterminate (orphan-class behavior is correct). Same structural
# argument as the original B1.3 force-flush deadline — observable
# lag drives the constant. F381's _PENDING_WICKET_MAX_FRAME_LAG
# above is a parallel target for tuning; deferred until L2 hits
# all green.
_PENDING_BOWLER_BALL_CREDIT_MAX_LAG = 20

SM_INLINE_MULTI_BALL = os.environ.get("SM_INLINE_MULTI_BALL", "0") == "1"
SM_POST_WICKET_SLOT_DIFF = (
    os.environ.get("SM_POST_WICKET_SLOT_DIFF", "0") == "1")


def _is_bowler_credited_dismissal(dtype) -> bool:
    if not dtype:
        return False
    norm = str(dtype).lower()
    if norm in _BOWLER_CREDITED_DISMISSALS:
        return True
    return norm.replace("_", "-") in _BOWLER_CREDITED_DISMISSALS

# P12 — innings-2 cold-start hardening thresholds (2026-05-03).
# Hybrid window: primary = (frames<F AND wall<S); safety net = wall<C.
# Defaults from diagnosis §4.  Set any to 0 to disable that clause.
INN2_TRANSITION_FRAMES = int(os.environ.get(
    "INN2_TRANSITION_FRAMES", "250"))
INN2_TRANSITION_SECONDS = int(os.environ.get(
    "INN2_TRANSITION_SECONDS", "900"))
INN2_TRANSITION_CEILING_SECONDS = int(os.environ.get(
    "INN2_TRANSITION_CEILING_SECONDS", "1200"))


# Strict umpire-signal patterns for inferring WIDE / NO_BALL from scout
# text.  A bare "wide" substring is too loose ("wide stance", "wider
# angle", "wide-angle camera") and a bare "no ball" was producing
# false-positive NB classifications on commentary text.  Only the
# patterns below — which describe an explicit umpire call or canonical
# arms-extended signal — are accepted; everything else falls back to
# generic EXTRA pending resolution.
_WIDE_PATTERNS: tuple[str, ...] = (
    "umpire signals wide",
    "umpire signaling wide",
    "umpire's arms extended",
    "umpires arms extended",
    "umpire raises both arms horizontally",
    "called wide by the umpire",
    "wide ball signal",
    "signalled wide",
    "signaled wide",
)

_NO_BALL_PATTERNS: tuple[str, ...] = (
    "umpire signals no ball",
    "umpire signals no-ball",
    "no-ball called",
    "no ball called",
    "umpire's arm extended at shoulder",
    "umpires arm extended at shoulder",
    "free hit awarded",
    "signalled no ball",
    "signaled no ball",
)


def _matches_wide_signal(text: str) -> bool:
    if not text:
        return False
    if any(p in text for p in _NO_BALL_PATTERNS):
        return False
    return any(p in text for p in _WIDE_PATTERNS)


def _matches_no_ball_signal(text: str) -> bool:
    if not text:
        return False
    return any(p in text for p in _NO_BALL_PATTERNS)


def _blank_extras_dict() -> dict[str, Any]:
    return {
        "wides": 0, "no_balls": 0, "byes": 0,
        "leg_byes": 0, "penalties": 0, "total": 0,
        "this_over": 0,
        "log": [],
    }


# Batch S — abbreviation re-detection guard. Maps known broadcast
# abbreviations to canonical full team names so the batting_team
# setter can reject strip-OCR misreads (e.g. "RCB" arriving while
# locked team is "Lucknow Super Giants"). Mirrors the IPL subset of
# `_IPL_BROADCAST_NAMES` in test_pipeline.py; expand if other leagues
# need the same protection.
_BATTING_TEAM_ABBR_TO_FULL: dict[str, str] = {
    abbr.upper(): full
    for full, abbrs in {
        "Gujarat Titans": ["GT", "GUJ", "TITANS"],
        "Mumbai Indians": ["MI", "MUM", "MUMBAI"],
        "Rajasthan Royals": ["RR", "RAJ", "ROYALS"],
        "Delhi Capitals": ["DC", "DEL", "DELHI"],
        "Chennai Super Kings": ["CSK", "CHE", "CHENNAI"],
        "Royal Challengers Bengaluru": ["RCB", "BAN", "BENGALURU", "BANGALORE"],
        "Sunrisers Hyderabad": ["SRH", "HYD", "SUNRISERS"],
        "Kolkata Knight Riders": ["KKR", "KOL", "KOLKATA"],
        "Punjab Kings": ["PBKS", "PUN", "PUNJAB"],
        "Lucknow Super Giants": ["LSG", "LKN", "LUCKNOW"],
    }.items()
    for abbr in abbrs
}


def _conflicts_with_locked_team(proposed: str, current: str) -> bool:
    proposed_full = _BATTING_TEAM_ABBR_TO_FULL.get(proposed.upper())
    if not proposed_full:
        return False
    return proposed_full.upper() != current.upper()


# ---------------------------------------------------------------------------
# FrameInput — everything ScoreManager needs each frame
# ---------------------------------------------------------------------------

@dataclass
class FrameInput:
    frame_id: str
    timestamp: float

    # From Extractor (structured scorecard parse)
    ext_score: int | None = None
    ext_wickets: int | None = None
    ext_overs: float | None = None
    ext_bat1_name: str | None = None
    ext_bat1_runs: int | None = None
    ext_bat1_balls: int | None = None
    ext_bat2_name: str | None = None
    ext_bat2_runs: int | None = None
    ext_bat2_balls: int | None = None
    ext_bowler_name: str | None = None
    ext_bowler_wickets: int | None = None
    ext_bowler_runs: int | None = None
    ext_bowler_overs: float | None = None

    # From Scorer (field update decisions)
    scorer_changes: list[str] = field(default_factory=list)

    # From broadcast info panel
    speed_kph: float | None = None
    ext_extras_total: int | None = None
    broadcast_extra: str | None = None
    broadcast_this_over: list[str] | None = None
    broadcast_target: int | None = None
    broadcast_striker: str | None = None
    broadcast_venue: str | None = None
    broadcast_team: str | None = None
    broadcast_match_info: str | None = None

    # From Scout raw text
    scout_text: str = ""
    action_text: str | None = None

    # From delivery analysis (may arrive same frame or later)
    delivery_info: dict | None = None

    # From DRS state machine
    drs_state: str = "NONE"


# ---------------------------------------------------------------------------
# PendingBall — queue entry for deferred attribution during overlay windows
# ---------------------------------------------------------------------------

@dataclass
class PendingBall:
    """Single deferred-ball record awaiting bowler/striker attribution.

    Enqueued when SM observes a runs/balls delta but tracker state is
    unresolved (overlay window, PENDING_OVERRIDE). Drained FIFO when
    both attribution fields fill via tracker on_lock callbacks or at
    the force-flush deadline. See no_multiball_design.md §2.1.
    """

    frame_id: int
    runs_delta: int
    balls_delta: int = 1
    wickets_delta: int = 0
    observed_strip_tokens: list[str] = field(default_factory=list)
    bowler: Optional[str] = None
    striker: Optional[str] = None
    placeholder_token: str = "?"
    committed: bool = False
    slot_idx: Optional[int] = None


@dataclass
class ExpectedBall:
    over: int = 0
    ball: int = 1
    legal_ball_count: int = 0


def _legal_balls_from_overs(overs):
    if overs is None:
        return None
    try:
        f = float(overs)
    except (TypeError, ValueError):
        return None
    if f < 0:
        return None
    whole = int(f)
    frac = round((f - whole) * 10)
    if frac < 0 or frac > 9:
        return None
    return whole * 6 + frac


# ---------------------------------------------------------------------------
# ScoreManager
# ---------------------------------------------------------------------------

COLD_CONSENSUS = int(os.environ.get("COLD_CONSENSUS_FRAMES", "2"))
COLD_MAX_FRAMES = 10
COLD_MAX_FRAMES_WITH_REF = 25  # extended limit when validating against ref
# Option E (2026-05-14): in COLD_START, accept a non-identical candidate
# → card transition as a legal MULTI_BALL gap if the diff passes
# cricket-rules and the ball-count delta is small.  Tighter than WARM's
# MULTI_BALL_MAX_BALLS=12 because cold-start has no anchored state to
# corroborate larger gaps; >3 balls without anchored history is almost
# always corrupted OCR.
COLD_START_MULTI_BALL_MAX_BALLS = 3

# Pre-match VLM-hallucination gate (cold-start only).  Investigation in
# `scout_raw.jsonl` from the 2026-05-14 watch session: the Scout VLM
# fabricates plausible "TEAM N-W (O.B)" strips over walk-out / toss
# coverage where no scoreboard graphic exists.  Two cheap signals catch
# nearly all such frames before they feed cold-start consensus:
#   1. skeleton strip — score/overs present, all named-player slots null;
#   2. pre-match narrative cue inside the raw VLM transcript.
_COLD_START_PREMATCH_CUE = re.compile(
    r"\b("
    r"won the toss"
    r"|chos(en|e) to (bat|bowl)"
    r"|walking (onto|out|back|off)"
    r"|after the toss"
    r"|warm-?up"
    r"|pre-?match"
    r"|lineup"
    r"|preview"
    r")\b",
    re.IGNORECASE,
)


def _is_skeleton_strip(frame: "FrameInput") -> bool:
    score_present = frame.ext_score is not None
    overs_present = frame.ext_overs is not None
    bat1_null = frame.ext_bat1_name in (None, "", "null")
    bat2_null = frame.ext_bat2_name in (None, "", "null")
    bowler_null = frame.ext_bowler_name in (None, "", "null")
    return (
        (score_present or overs_present)
        and bat1_null and bat2_null and bowler_null
    )


def _record_cold_start_reject(tag: str, frame: "FrameInput", card: dict) -> None:
    log.info(
        f"[{tag}] frame={frame.frame_id} "
        f"score={card.get('score')} wickets={card.get('wickets')} "
        f"overs={card.get('overs')}")
    if _trace is None:
        return
    try:
        _trace.get_recorder().record(
            tag=tag,
            frame_id=frame.frame_id,
            score=card.get("score"),
            wickets=card.get("wickets"),
            overs=card.get("overs"),
        )
    except Exception:
        pass

# POISON-/carousel-heavy cold exits: anchored in `cold_start_recovery_analysis.md`.
# ─ Pair A: enough SM cold iterations *and* enough pipeline frames → adopt the
#   last fully-structured viable card (passed false-zero rejection) without
#   waiting for triple identical reads.
# ─ Pair B: very long starvation where scorer occasionally emits a viable triple
#   but carousel never stabilises triple-agreement (`cold_frames` stays low).
COLD_START_PIPELINE_FALLBACK_AFTER = 25
COLD_START_PIPELINE_FALLBACK_STARVATION = 45


class ScoreManager:
    """Single source of truth for all UI state."""

    def __init__(self, *, shadow: bool = True):
        self.shadow = shadow

        # Optional Scoreboard reference for name canonicalization.
        # When attached (via test_pipeline on startup), every name that
        # enters SM state — bat1/bat2/bowler/striker/non — is
        # normalized to the canonical squad key so downstream identity
        # comparisons (`striker == bat1_name`, `batting_card[i].is_striker`)
        # don't break on raw scout surnames like "N RANA" vs canonical
        # "Nitish Rana". Issue 1 fix (2026-04-21).
        self.scoreboard = None

        # Path B LOW-risk batch: scalars mirrored from `Scoreboard` when
        # attached; shadow / no-SB tests store here (set_innings_2 calls
        # __init__ and clears scoreboard before batting_team assign).
        self._sm_scalar_fallback: dict[str, Any] = {}
        self._current_frame: int = 0

        # Mode
        self.mode: str = "COLD_START"
        self.cold_candidate: dict | None = None
        self.cold_frames: int = 0
        # Number of consecutive frames the same `cold_candidate` has
        # been observed. Bumped from implicit 2-frame agreement to
        # explicit 3-frame consensus to defend against single-frame
        # Scout hallucinations of cold-start scorecards.
        # ("GT 112-3 (12.5)" appearing on a frame where the actual
        # match is 0-0 — a coherent, physics-valid scorecard the
        # warm-mode diff guards cannot catch because there is no
        # prior state to compare against.)
        self.cold_candidate_streak: int = 0
        # Cold-start consensus: dropped from 3 → 2 in 2026-05-14 paired
        # with `consistent_tracker.INITIAL_CONSENSUS_FRAMES` 3 → 2.  The
        # 3-frame floor existed to defend against single-frame Scout
        # hallucinations of cold-start scorecards (e.g. "GT 112-3 (12.5)"
        # on a frame where the real match is 0-0); commit d935966 moved
        # that defence to the skeleton-strip + pre-match-cue gates which
        # filter bad reads before they reach the consensus accumulator,
        # so the 3rd matching frame is no longer load-bearing.  Halves
        # the wall-clock to first WARM anchor (~6 Scout cadences instead
        # of ~10).  Env-overridable for paranoid revert.
        self.COLD_START_CONSENSUS_FRAMES: int = int(
            os.environ.get("COLD_START_CONSENSUS_FRAMES", "2"))
        self._cold_pipeline_frames: int = 0
        self._cold_last_viable: dict | None = None
        self._cold_pipeline_fallback_after: int = COLD_START_PIPELINE_FALLBACK_AFTER
        self._cold_pipeline_fallback_starvation: int = (
            COLD_START_PIPELINE_FALLBACK_STARVATION)
        # State snapshot at COLD_START entry — used at WARM transition
        # to synthesize ball events for the deliveries that flew past
        # during consensus convergence. Defaults to a fresh-boot anchor
        # (0/0/0.0); mid-match re-entries update this in the COLD_START
        # entry paths.
        self._cold_start_entry: dict = {
            "score": 0, "wickets": 0, "overs": 0.0}
        # Most recent synthesis output, surfaced for downstream
        # consumers (over_mgr, trace replay).
        self._cold_start_synthesized_events: list[dict] = []

        # Pending-ball queue (no-MULTI_BALL architecture, Issue 1 fix).
        # FIFO of deferred ball deltas observed during overlay windows
        # or bowler PENDING_OVERRIDE. Drained when tracker on_lock
        # callbacks fire (wired in B1.3). Designed depth <=3 per
        # overlay window per Investigation #2 Q2; maxlen=6 gives
        # headroom + overflow signal. See no_multiball_design.md.
        self._pending_ball_queue: deque[PendingBall] = deque(maxlen=6)
        # B1.3 §2.6: over_history archive deferral. When an over rolls
        # over with the pending queue non-empty, archive is skipped
        # this frame and the over_n is parked here. Subsequent frames
        # attempt drain; archive proceeds when queue empties or at the
        # §2.7 force-flush deadline.
        self._over_archive_pending: int | None = None

        # Accepted UI state (score / wickets / run_rate / target /
        # batting_team → Path B properties; see class body below.)
        self.overs: float | None = None
        # Stage 1 (additive, see sm_as_orchestrator_design.md §3): tracked,
        # not gated. None until first overs commit establishes baseline.
        self._expected_next_ball: ExpectedBall | None = None

        self.bat1_name: str | None = None
        self.bat2_name: str | None = None

        self.bowler_name: str | None = None

        self.striker: str | None = None
        self.non: str | None = None
        # Fix #20: set True for the lifetime of the frame whose
        # _cold_start_plausible returned False. Reset per-frame in
        # the run_test loop. Consumed by the prompt assembly to skip
        # the "ALREADY DISMISSED" Scorer hint when the cold-start
        # verdict is implausible — phantom dismissals from a poisoned
        # cold-start frame must not propagate into Scorer prompts.
        self.last_cold_start_verdict_implausible: bool = False
        # Lever 1 PR3: dedupe [SM-W8-DISMISSED-GUARD] telemetry (§14.8).
        self._w8_guard_fired: set[str] = set()
        # S5b-3a (2026-05-20): post-wicket striker slot-diff derivation
        # state. Set in _apply_wicket_fall_only at wicket commit if the
        # dismissed batter was on strike; cleared in _identify_and_set
        # once self.striker becomes non-None again. See
        # cold_start_initial_striker_design.md.
        self._post_wicket_slot_to_diff: str | None = None

        # Match context (innings / batting_team / target → Path B properties)
        self.venue: str | None = None
        self.match_info: str | None = None

        # Computed (run_rate → Path B property reads SB._inn)
        self.required_run_rate: float | None = None
        self.balls_remaining: int | None = None
        self.match_phase: str | None = None
        self.bat1_sr: float | None = None
        self.bat2_sr: float | None = None
        self.bowler_economy: float | None = None

        # DC-vs-CSK Fix 4: 2-frame consensus cache for score commits.
        # ``_pending_score`` holds the last unconfirmed proposal; the
        # next frame must echo the same score before the value commits.
        # Monotonic single-ball-event jumps (+1/+2/+3/+4/+6) are
        # trusted on first read since they are predictable from the
        # ball event; jumps > +6 in a single read ALWAYS require
        # 2-frame confirmation.
        self._pending_score: int | None = None
        self._pending_score_frame: int | None = None
        # Over tracking
        self.this_over: list[str] = []
        self.this_over_src: list[str] = []
        self.over_history: dict[int, list[str]] = {}
        self.completed_over: list[str] | None = None
        self.completed_over_runs: int | None = None

        # Partnership
        self.partnership_runs: int = 0
        self.partnership_balls: int = 0
        self.partnership_known: bool = True

        # Fall of wickets / extras (Path B: use _fow_writable / _extras_writable)
        self._fow_sm_internal: list[dict] = []
        self._extras_sm_internal: dict[str, Any] = _blank_extras_dict()

        # Free hit
        self.free_hit_next: bool = False

        # Extras tracking — observability and parity-monitor surface.
        # innings_extras: total wides/no-balls/byes seen in current innings
        # this_over_extras: count of extra-tokens (Wd/Nb/B/LB) currently
        #   in self.this_over.  Cleared at over rollover.
        # extras: innings_extras / this_over_extras / extras_log → properties

        # Speed
        self.last_speed: float | None = None
        self.last_speed_at_over: float | None = None

        # Pending resolutions
        self.pending_extra: dict | None = None
        self.pending_extra_frames: int = 0
        self.pending_wicket: dict | None = None
        self.pending_wicket_frames: int = 0

        # History
        self.recent_frames: list[FrameInput] = []

        # Last event
        self.last_event: dict | None = None
        self.frames_since_event: int = 0
        self._stale_reject_count: int = 0

        # Reference state from last WARM period — used to validate cold-start
        # consensus when re-entering COLD_START from stale recovery.
        self._last_warm_state: dict | None = None

        # Deferred score change: when score advances but overs don't (and no
        # broadcast_extra), defer firing until overs catch up on the next frame.
        self._deferred_score: int = 0
        self._deferred_frames: int = 0
        # Set True when the deferral chain expired with overs still stuck —
        # signals to `_infer_event` that the overs-lag has persisted long
        # enough to be considered a hard signal for EXTRA inference.
        self._extras_persistent_lag: bool = False

        # Overs-regression consensus: a single-frame overs regression is
        # almost always a poisoned scout read (or _validate_overs backing
        # up after mis-parsing a replay graphic's THIS OVER ribbon).
        # Require N consecutive regression frames before re-entering
        # COLD_START so real ball events on the NEXT frame don't get lost
        # to a phantom cold-start window.  Tracks (best_seen, streak).
        self._overs_regress_streak: int = 0
        self._overs_regress_from: float | None = None
        self._OVERS_REGRESS_THRESHOLD: int = 2
        # D5 stuck-tracker recovery: count any rejected-regression frame
        # (large or small). When the streak reaches the threshold, force
        # a full reset — tracker is almost certainly anchored to a stale
        # commit that the live broadcast keeps disagreeing with.
        self._regression_streak: int = 0
        self._REGRESSION_STREAK_THRESHOLD: int = 10
        self._LARGE_OVERS_REGRESSION_GAP: float = 3.0
        # D4 inn2-preserve gating: True only after a real forward score
        # advance happens while in WARM mode. A cold-start commit that
        # immediately freezes (no live progress) leaves this False, so
        # the inn1→inn2 preserve heuristic in the pipeline can refuse
        # to carry the stale state across the innings flip.
        self._warm_advancing_observed: bool = False
        # D7 team-change consensus: defer the inn-2 trigger until the
        # same new team is seen on N consecutive frames. Single-frame
        # pre-match-graphic flips otherwise commit a spurious flip.
        self._team_change_candidate: str | None = None
        self._team_change_streak: int = 0
        self.TEAM_CHANGE_CONSENSUS_FRAMES: int = 3

        # Innings history (for archiving at innings change)
        self.innings_history: list[dict] = []

        self._innings_fallback: int = 1
        self._sm_feeder_sb_missing_logged: bool = False

        self._inn2_bootstrap_attempted: bool = False

    # -----------------------------------------------------------------
    # Pending-ball queue methods (no-MULTI_BALL architecture, B1.1).
    # See files/docs/investigations/no_multiball_design.md.
    # -----------------------------------------------------------------

    def _enqueue_pending_ball(
        self,
        *,
        runs_delta: int,
        wickets_delta: int = 0,
        frame_id: int,
        strip_tokens: Optional[list[str]] = None,
        slot_idx: Optional[int] = None,
    ) -> Optional[PendingBall]:
        # B1.3 prereq (exclusive-producer invariant): the canonical
        # producer is SM._decompose_multi_ball. The two test_pipeline.py
        # producers are disabled in B1.3 but defense-in-depth: reject
        # duplicates with same (frame_id, slot_idx) so future drift
        # surfaces immediately rather than silently double-crediting.
        for _existing in self._pending_ball_queue:
            if (_existing.frame_id == frame_id
                    and _existing.slot_idx == slot_idx
                    and not _existing.committed):
                self._emit_pending_trace(
                    "PENDING-BALL-ENQUEUE-DUPLICATE-REJECTED",
                    frame_id=frame_id,
                    slot_idx=slot_idx,
                    runs_delta=runs_delta,
                    queue_depth=len(self._pending_ball_queue),
                )
                return None
        if (self._pending_ball_queue.maxlen is not None
                and len(self._pending_ball_queue) >= self._pending_ball_queue.maxlen):
            self._emit_pending_trace(
                "PENDING-BALL-QUEUE-OVERFLOW",
                queue_depth=len(self._pending_ball_queue),
                dropping_oldest_frame_id=self._pending_ball_queue[0].frame_id,
                incoming_frame_id=frame_id,
            )

        entry = PendingBall(
            frame_id=frame_id,
            runs_delta=runs_delta,
            wickets_delta=wickets_delta,
            observed_strip_tokens=list(strip_tokens or []),
            slot_idx=slot_idx,
        )
        self._pending_ball_queue.append(entry)
        self._emit_pending_trace(
            "PENDING-BALL-ENQUEUED",
            frame_id=frame_id,
            runs_delta=runs_delta,
            wickets_delta=wickets_delta,
            queue_depth=len(self._pending_ball_queue),
            slot_idx=slot_idx,
        )
        return entry

    def _resweep_pending_attribution(self, name: str, role: str) -> int:
        """Fill `role` on uncommitted queue entries where it is None.

        `role` in {"bowler", "striker"}. Returns count of entries
        updated. Does NOT drain; caller must drain afterward.
        """
        if role not in ("bowler", "striker"):
            raise ValueError(f"unknown role {role!r}")
        tag = ("PENDING-BALL-BOWLER-ATTRIBUTED"
               if role == "bowler" else "PENDING-BALL-STRIKER-ATTRIBUTED")
        updated = 0
        for entry in self._pending_ball_queue:
            if entry.committed:
                continue
            current = entry.bowler if role == "bowler" else entry.striker
            if current is not None:
                continue
            if role == "bowler":
                entry.bowler = name
            else:
                entry.striker = name
            updated += 1
            self._emit_pending_trace(
                tag,
                frame_id=entry.frame_id,
                name=name,
                slot_idx=entry.slot_idx,
            )
        return updated

    def _rewrite_eyes_this_over_from_event(
            self, card: dict, token: str) -> None:
        """Fix A: SM-authoritative rewrite of eyes-side ``over_mgr.this_over``.

        Broadcast wholesale-accept and other non-queue-routed paths emit
        ``?`` placeholders into ``over_mgr.this_over`` that bypass the SM
        pending queue, so the queue-drain rewrite at ``_drain_pending_queue``
        never fires for them. SM is the authoritative source on every
        ball commit — propagate the resolved token to eyes immediately,
        closing the orphan-``?`` class observed in
        ``logs/trace/watch_20260519_082523.jsonl`` frames 4-45 (over 0).

        Slot derives from ``card["overs"]``: ``N.M`` → slot ``M-1``,
        with ``M=0`` (over-end frame) mapping to slot 5 (the
        just-completed 6th ball of the previous over).
        Out-of-range slots are silently no-ops in
        ``ThisOverManager.rewrite_token``.
        """
        over_mgr = getattr(self, "over_mgr", None)
        rewrite = getattr(over_mgr, "rewrite_token", None)
        if rewrite is None:
            return
        try:
            _ov_f = float(card.get("overs") or self.overs or 0)
        except (TypeError, ValueError):
            return
        _legal = round((_ov_f % 1) * 10)
        slot_idx = 5 if _legal == 0 else _legal - 1
        try:
            rewrite(slot_idx, token)
        except Exception:
            pass

    def _drain_pending_queue(self, reason: str) -> int:
        """FIFO-drain entries with both bowler+striker known.

        Halts at the first uncommitted entry (FIFO order preserved).
        Rewrites placeholder token in over_mgr.this_over via
        rewrite_token() when available (wired fully in B1.2).
        """
        drained = 0
        for entry in list(self._pending_ball_queue):
            if entry.committed:
                continue
            if entry.bowler is None or entry.striker is None:
                break
            entry.committed = True
            derived = self._derive_pending_token(entry)
            over_mgr = getattr(self, "over_mgr", None)
            rewrite = getattr(over_mgr, "rewrite_token", None)
            if rewrite is not None and entry.slot_idx is not None:
                try:
                    rewrite(entry.slot_idx, derived)
                except Exception:
                    pass
            self._emit_pending_trace(
                "PENDING-BALL-DRAINED",
                frame_id=entry.frame_id,
                reason=reason,
                bowler=entry.bowler,
                striker=entry.striker,
                runs_delta=entry.runs_delta,
                wickets_delta=entry.wickets_delta,
                token=derived,
                slot_idx=entry.slot_idx,
            )
            drained += 1
        while self._pending_ball_queue and self._pending_ball_queue[0].committed:
            self._pending_ball_queue.popleft()
        return drained

    def _bowler_pending_override_active(self) -> tuple[bool, str | None, int]:
        """B1.3 §2.7: detect bowler PENDING_OVERRIDE proxy.

        ConfidenceTracker doesn't define a PENDING_OVERRIDE state per se;
        the equivalent live signal is scoreboard's
        `_pending_bowler_name is not None` with streak count > 0 —
        an override candidate accumulating but not yet won the lock.
        Returns (active, candidate_name, streak).
        """
        if self.scoreboard is None:
            return (False, None, 0)
        try:
            cand = getattr(self.scoreboard, "_pending_bowler_name", None)
            streak = int(getattr(
                self.scoreboard, "_pending_bowler_count", 0) or 0)
        except Exception:
            return (False, None, 0)
        return (cand is not None and streak > 0, cand, streak)

    def _attempt_pending_archive_drain(
            self, current_overs: float | None) -> None:
        """B1.3 §2.6/§2.7: pre-archive retry + force-flush deadlines.

        Called from `_handle_warm` at the top of every frame when
        `_over_archive_pending` is set. Tries drain first; if queue
        empties, the archive happens naturally on the next over-end
        path (caller clears the deferral flag). If still non-empty,
        evaluates the two-stage deadline.
        """
        if self._over_archive_pending is None:
            return
        if current_overs is None:
            return
        deferred_n = int(self._over_archive_pending)
        # Attempt drain (no-op if attribution still missing).
        self._drain_pending_queue("pre_archive_retry")
        if not self._pending_ball_queue:
            # Queue empty — archive completed_over now.
            self._commit_deferred_archive(
                deferred_n, source="pre_archive_drain_success")
            return
        try:
            _ov_f = float(current_overs)
        except (TypeError, ValueError):
            return
        soft_deadline = float(deferred_n + 1) + 0.3
        hard_cap = float(deferred_n + 1) + 1.0
        if _ov_f < soft_deadline:
            return
        if _ov_f < hard_cap:
            # Soft deadline reached: check PENDING_OVERRIDE extension.
            active, cand, streak = self._bowler_pending_override_active()
            if active:
                self._emit_pending_trace(
                    "PENDING-BALL-FLUSH-EXTENDED-OVERRIDE-ACTIVE",
                    deferred_over=deferred_n,
                    current_overs=_ov_f,
                    soft_deadline=soft_deadline,
                    pending_candidate=cand,
                    pending_streak=streak,
                )
                return
        # Force-flush: commit each remaining entry to current leader
        # / first non-None / fallback to self.striker / self.bowler_name.
        fallback_bowler = (
            self.bowler_name
            or (self.scoreboard._inn or {}).get("current_bowler")
            if self.scoreboard is not None else self.bowler_name)
        fallback_striker = self.striker
        for entry in list(self._pending_ball_queue):
            if entry.committed:
                continue
            if entry.bowler is None:
                entry.bowler = fallback_bowler
            if entry.striker is None:
                entry.striker = fallback_striker
            self._emit_pending_trace(
                "PENDING-BALL-FORCED-FLUSH-UNRESOLVED",
                frame_id=entry.frame_id,
                slot_idx=entry.slot_idx,
                bowler_used=entry.bowler,
                striker_used=entry.striker,
                runs_delta=entry.runs_delta,
                wickets_delta=entry.wickets_delta,
                deferred_over=deferred_n,
                current_overs=_ov_f,
                hard_cap_reached=(_ov_f >= hard_cap),
            )
        # Now run a normal drain — entries with non-None attribution
        # commit through the standard path (delta apply + token rewrite
        # to "?"). Token in over_history will remain "?" for forced
        # entries since rewrite_token is called with derived token; we
        # do NOT fabricate displayed tokens per §2.7.
        self._drain_pending_queue("force_flush")
        # Archive over_history[N] with mixed real/"?" tokens per §2.7.
        self._commit_deferred_archive(
            deferred_n,
            source=("force_flush_hard_cap" if _ov_f >= hard_cap
                    else "force_flush_soft"))

    def _commit_deferred_archive(self, over_n: int, *, source: str) -> None:
        """B1.3 §2.6/§2.7: write deferred over_history entry + clear flag.

        Source = `self.completed_over` (captured at the deferral moment
        before this_over was reset). Emits OVER-ARCHIVE-WRITE +
        OVER-ARCHIVE-INVALID-TOKEN-COUNT mirroring the inline-rollover
        archive instrumentation in `_apply_event`.
        """
        tokens = list(self.completed_over or [])
        existing = self.over_history.get(over_n)
        self.over_history[over_n] = list(tokens)
        if _trace is not None:
            try:
                _trace.get_recorder().record(
                    tag="OVER-ARCHIVE-WRITE",
                    over_n=int(over_n),
                    tokens=list(tokens),
                    token_count=len(tokens),
                    source=f"deferred_{source}")
                if (existing is not None
                        and list(existing) != list(tokens)):
                    _trace.get_recorder().record(
                        tag="OVER-ARCHIVE-DOUBLE-WRITE",
                        over_n=int(over_n),
                        existing_tokens=list(existing),
                        attempted_tokens=list(tokens),
                        source=f"deferred_{source}")
                if len(tokens) != 6:
                    _trace.get_recorder().record(
                        tag="OVER-ARCHIVE-INVALID-TOKEN-COUNT",
                        over_n=int(over_n),
                        token_count=len(tokens),
                        tokens=list(tokens))
            except Exception:
                pass
        self._over_archive_pending = None

    def bind_pending_slot(self, slot_idx: int) -> bool:
        """Bind a this_over slot_idx to the head unbound PendingBall (B1.2c).

        Called by ThisOverManager after it appends a "?" placeholder. Walks
        the pending queue head→tail; the first uncommitted entry with
        slot_idx=None gets bound to this slot. FIFO order matches event
        emission order — producer (SM._decompose_multi_ball or BED via
        test_pipeline.py) enqueues N PendingBalls, then over_mgr fields
        N ABSORBED_LEGAL events and binds each in order.

        Returns True on successful bind, False if no unbound entry exists
        (orphan — likely a "?" emitted without prior SM enqueue).
        """
        for entry in self._pending_ball_queue:
            if not entry.committed and entry.slot_idx is None:
                entry.slot_idx = slot_idx
                self._emit_pending_trace(
                    "PENDING-BALL-SLOT-BOUND",
                    slot_idx=slot_idx,
                    frame_id=entry.frame_id,
                )
                return True
        self._emit_pending_trace(
            "PENDING-BALL-SLOT-BOUND-ORPHAN",
            slot_idx=slot_idx,
        )
        return False

    @staticmethod
    def _derive_pending_token(entry: PendingBall) -> str:
        if entry.wickets_delta > 0:
            return "W"
        if entry.runs_delta == 0:
            return "."
        return str(entry.runs_delta)

    def _emit_pending_trace(self, tag: str, **payload: Any) -> None:
        if _trace is None:
            return
        try:
            _trace.get_recorder().record(tag=tag, **payload)
        except Exception:
            pass

    def _fow_writable(self) -> list[dict]:
        if self.scoreboard is not None:
            return self.scoreboard.fall_of_wickets
        return self._fow_sm_internal

    def _extras_writable(self) -> dict[str, Any]:
        if self.scoreboard is not None:
            return self.scoreboard.extras
        return self._extras_sm_internal

    def _sb_inn_get(self, key: str) -> Any:
        if self.scoreboard is None:
            return None
        try:
            return self.scoreboard._inn.get(key)
        except Exception:
            return None

    def _frame_int(self, frame: FrameInput) -> int:
        try:
            n = int(frame.frame_id)
        except (TypeError, ValueError):
            n = self._current_frame
        self._current_frame = n
        return n

    # --- Path B LOW-risk batch: read-through / feeders (contract §12) ---

    @property
    def fow_list(self) -> list[dict]:
        return list(self._fow_writable())

    @fow_list.setter
    def fow_list(self, value: list[dict] | None) -> None:
        w = self._fow_writable()
        w.clear()
        if value:
            w.extend(value)

    @property
    def innings_extras(self) -> int:
        return int(self._extras_writable().get("total", 0) or 0)

    @innings_extras.setter
    def innings_extras(self, value: int) -> None:
        self._extras_writable()["total"] = int(value)

    @property
    def this_over_extras(self) -> int:
        return int(self._extras_writable().get("this_over", 0) or 0)

    @this_over_extras.setter
    def this_over_extras(self, value: int) -> None:
        self._extras_writable()["this_over"] = int(value)

    @property
    def extras_log(self) -> list[dict]:
        raw = self._extras_writable().get("log")
        return list(raw) if raw else []

    @extras_log.setter
    def extras_log(self, value: list[dict] | None) -> None:
        self._extras_writable()["log"] = list(value or [])

    def _fmt_sb_val(self, v: Any) -> str:
        return "None" if v is None else repr(v)

    @property
    def bat1_runs(self) -> int | None:
        if self.scoreboard is not None and self.bat1_name:
            c = (self.scoreboard.batting_card or {}).get(self.bat1_name) or {}
            r = c.get("runs")
            if r is not None:
                try:
                    return int(r)
                except (TypeError, ValueError):
                    return None
        return None

    @property
    def bat1_balls(self) -> int | None:
        if self.scoreboard is not None and self.bat1_name:
            c = (self.scoreboard.batting_card or {}).get(self.bat1_name) or {}
            b = c.get("balls")
            if b is not None:
                try:
                    return int(b)
                except (TypeError, ValueError):
                    return None
        return None

    @property
    def bat2_runs(self) -> int | None:
        if self.scoreboard is not None and self.bat2_name:
            c = (self.scoreboard.batting_card or {}).get(self.bat2_name) or {}
            r = c.get("runs")
            if r is not None:
                try:
                    return int(r)
                except (TypeError, ValueError):
                    return None
        return None

    @property
    def bat2_balls(self) -> int | None:
        if self.scoreboard is not None and self.bat2_name:
            c = (self.scoreboard.batting_card or {}).get(self.bat2_name) or {}
            b = c.get("balls")
            if b is not None:
                try:
                    return int(b)
                except (TypeError, ValueError):
                    return None
        return None

    @property
    def bowler_wickets(self) -> int | None:
        if self.scoreboard is not None and self.bowler_name:
            c = (self.scoreboard.bowling_card or {}).get(self.bowler_name) or {}
            w = c.get("wickets")
            if w is not None:
                try:
                    return int(w)
                except (TypeError, ValueError):
                    return None
        return None

    @property
    def bowler_runs(self) -> int | None:
        if self.scoreboard is not None and self.bowler_name:
            c = (self.scoreboard.bowling_card or {}).get(self.bowler_name) or {}
            r = c.get("runs")
            if r is not None:
                try:
                    return int(r)
                except (TypeError, ValueError):
                    return None
        return None

    @property
    def bowler_overs(self) -> float | None:
        if self.scoreboard is not None and self.bowler_name:
            c = (self.scoreboard.bowling_card or {}).get(self.bowler_name) or {}
            o = c.get("overs")
            if o is not None:
                try:
                    return float(o)
                except (TypeError, ValueError):
                    return None
        return None

    @property
    def innings(self) -> int:
        if self.scoreboard is not None:
            try:
                return int(self.scoreboard.current_innings)
            except (TypeError, ValueError):
                return self._innings_fallback
        return self._innings_fallback

    @innings.setter
    def innings(self, v: int) -> None:
        sbv = None
        if self.scoreboard is not None:
            try:
                sbv = int(self.scoreboard.current_innings)
            except (TypeError, ValueError):
                sbv = None
        log.info(
            "  [SM-FEEDER-SYNC] field=innings note=read_only_now "
            f"sb_value={self._fmt_sb_val(sbv)} sm_would_set={v!r}")
        if self.scoreboard is None:
            try:
                self._innings_fallback = int(v)
            except (TypeError, ValueError):
                pass

    @property
    def score(self) -> int | None:
        if self.scoreboard is not None:
            raw = self._sb_inn_get("score")
            if raw is not None:
                try:
                    return int(raw)
                except (TypeError, ValueError):
                    return None
            return None
        return self._sm_scalar_fallback.get("score")

    @score.setter
    def score(self, value: int | None) -> None:
        if value is None:
            self._sm_scalar_fallback.pop("score", None)
            return
        try:
            iv = int(value)
        except (TypeError, ValueError):
            log.info(
                "  [SM-FEEDER-SYNC] field=score sb_accepted=false "
                "reason=coerce_error")
            return
        if self.shadow:
            sbv = self._sb_inn_get("score")
            if self.scoreboard is None:
                sbv = self._sm_scalar_fallback.get("score")
            try:
                div = sbv is None or int(sbv) != iv
            except (TypeError, ValueError):
                div = True
            log.info(
                f"  [SM-SHADOW-PARITY] field=score sm_would_accept={iv} "
                f"sb_value={self._fmt_sb_val(sbv)} "
                f"divergence={str(div).lower()}")
            self._sm_scalar_fallback["score"] = iv
            return
        if self.scoreboard is None:
            if not self._sm_feeder_sb_missing_logged:
                log.info("  [SM-FEEDER-SYNC] field=score sb_attached=false")
                self._sm_feeder_sb_missing_logged = True
            self._sm_scalar_fallback["score"] = iv
            return
        frame = self._current_frame
        try:
            ok = self.scoreboard.set("score", iv, frame)
        except Exception as e:
            log.info(
                "  [SM-FEEDER-SYNC] field=score "
                f"value={iv} sb_error={e}")
            return
        log.info(
            f"  [SM-FEEDER-SYNC] field=score value={iv} "
            f"sb_accepted={str(ok).lower()}")

    @property
    def wickets(self) -> int | None:
        if self.scoreboard is not None:
            raw = self._sb_inn_get("wickets")
            if raw is not None:
                try:
                    return int(raw)
                except (TypeError, ValueError):
                    return None
            return None
        return self._sm_scalar_fallback.get("wickets")

    @wickets.setter
    def wickets(self, value: int | None) -> None:
        if value is None:
            self._sm_scalar_fallback.pop("wickets", None)
            return
        try:
            iv = int(value)
        except (TypeError, ValueError):
            return
        if self.shadow:
            sbv = self._sb_inn_get("wickets")
            if self.scoreboard is None:
                sbv = self._sm_scalar_fallback.get("wickets")
            try:
                div = sbv is None or int(sbv) != iv
            except (TypeError, ValueError):
                div = True
            log.info(
                f"  [SM-SHADOW-PARITY] field=wickets sm_would_accept={iv} "
                f"sb_value={self._fmt_sb_val(sbv)} "
                f"divergence={str(div).lower()}")
            self._sm_scalar_fallback["wickets"] = iv
            return
        if self.scoreboard is None:
            if not self._sm_feeder_sb_missing_logged:
                log.info("  [SM-FEEDER-SYNC] field=wickets sb_attached=false")
                self._sm_feeder_sb_missing_logged = True
            self._sm_scalar_fallback["wickets"] = iv
            return
        try:
            ok = self.scoreboard.set("wickets", iv, self._current_frame)
        except Exception as e:
            log.info(
                "  [SM-FEEDER-SYNC] field=wickets "
                f"value={iv} sb_error={e}")
            return
        log.info(
            f"  [SM-FEEDER-SYNC] field=wickets value={iv} "
            f"sb_accepted={str(ok).lower()}")

    @property
    def run_rate(self) -> float | None:
        if self.scoreboard is not None:
            raw = self._sb_inn_get("run_rate")
            if raw is not None:
                try:
                    return float(raw)
                except (TypeError, ValueError):
                    return None
            return None
        v = self._sm_scalar_fallback.get("run_rate")
        return float(v) if v is not None else None

    @run_rate.setter
    def run_rate(self, value: float | None) -> None:
        if value is None:
            self._sm_scalar_fallback.pop("run_rate", None)
            return
        try:
            fv = float(value)
        except (TypeError, ValueError):
            return
        if self.shadow:
            sbv = self._sb_inn_get("run_rate")
            if self.scoreboard is None:
                sbv = self._sm_scalar_fallback.get("run_rate")
            try:
                div = (sbv is None or float(sbv) != fv)
            except (TypeError, ValueError):
                div = True
            log.info(
                f"  [SM-SHADOW-PARITY] field=run_rate sm_would_accept={fv} "
                f"sb_value={self._fmt_sb_val(sbv)} "
                f"divergence={str(div).lower()}")
            self._sm_scalar_fallback["run_rate"] = fv
            return
        if self.scoreboard is None:
            self._sm_scalar_fallback["run_rate"] = fv
            return
        try:
            ok = self.scoreboard.set("run_rate", fv, self._current_frame)
        except Exception as e:
            log.info(
                f"  [SM-FEEDER-SYNC] field=run_rate value={fv} "
                f"sb_error={e}")
            return
        log.info(
            f"  [SM-FEEDER-SYNC] field=run_rate value={fv} "
            f"sb_accepted={str(ok).lower()}")

    @property
    def target(self) -> int | None:
        if self.scoreboard is not None:
            raw = self._sb_inn_get("target")
            if raw is not None:
                try:
                    return int(raw)
                except (TypeError, ValueError):
                    return None
            return None
        return self._sm_scalar_fallback.get("target")

    @target.setter
    def target(self, value: int | None) -> None:
        if value is None:
            self._sm_scalar_fallback.pop("target", None)
            return
        try:
            iv = int(value)
        except (TypeError, ValueError):
            return
        if self.shadow:
            sbv = self._sb_inn_get("target")
            if self.scoreboard is None:
                sbv = self._sm_scalar_fallback.get("target")
            try:
                div = sbv is None or int(sbv) != iv
            except (TypeError, ValueError):
                div = True
            log.info(
                f"  [SM-SHADOW-PARITY] field=target sm_would_accept={iv} "
                f"sb_value={self._fmt_sb_val(sbv)} "
                f"divergence={str(div).lower()}")
            self._sm_scalar_fallback["target"] = iv
            return
        if self.scoreboard is None:
            self._sm_scalar_fallback["target"] = iv
            return
        try:
            ok = self.scoreboard.set("target", iv, self._current_frame)
        except Exception as e:
            log.info(
                f"  [SM-FEEDER-SYNC] field=target value={iv} "
                f"sb_error={e}")
            return
        log.info(
            f"  [SM-FEEDER-SYNC] field=target value={iv} "
            f"sb_accepted={str(ok).lower()}")

    @property
    def batting_team(self) -> str | None:
        if self.scoreboard is not None:
            bt = getattr(self.scoreboard, "batting_team", None)
            return bt if isinstance(bt, str) or bt is None else str(bt)
        return self._sm_scalar_fallback.get("batting_team")

    @batting_team.setter
    def batting_team(self, value: str | None) -> None:
        if value is None:
            self._sm_scalar_fallback.pop("batting_team", None)
            if self.scoreboard is not None:
                try:
                    self.scoreboard.batting_team = None
                except Exception:
                    pass
            return
        if self.shadow:
            sbv = (getattr(self.scoreboard, "batting_team", None)
                   if self.scoreboard else None)
            if self.scoreboard is None:
                sbv = self._sm_scalar_fallback.get("batting_team")
            div = sbv != value
            log.info(
                f"  [SM-SHADOW-PARITY] field=batting_team "
                f"sm_would_accept={value!r} sb_value={self._fmt_sb_val(sbv)} "
                f"divergence={str(div).lower()}")
            self._sm_scalar_fallback["batting_team"] = value
            return
        if self.scoreboard is None:
            if not self._sm_feeder_sb_missing_logged:
                log.info(
                    "  [SM-FEEDER-SYNC] field=batting_team sb_attached=false")
                self._sm_feeder_sb_missing_logged = True
            self._sm_scalar_fallback["batting_team"] = value
            return
        cur = getattr(self.scoreboard, "batting_team", None)
        if (cur and value != cur
                and _conflicts_with_locked_team(value, cur)):
            log.warn(
                f"  [SM-FEEDER-SYNC] field=batting_team value={value!r} "
                f"sb_accepted=false reason=abbreviation_conflict "
                f"locked={cur!r}")
            return
        try:
            self.scoreboard.batting_team = value
            ok = True
        except Exception as e:
            ok = False
            log.info(
                f"  [SM-FEEDER-SYNC] field=batting_team "
                f"value={value!r} sb_error={e}")
            return
        log.info(
            f"  [SM-FEEDER-SYNC] field=batting_team value={value!r} "
            f"sb_accepted={str(ok).lower()}")

    def _clear_per_innings_sm_surface(self) -> None:
        """Wipe accepted strip state and Fix-16 cached fields for the current innings.

        Does **not** touch match context (`innings`, `target`, `batting_team`,
        `venue`, `match_info`, `innings_history`, `shadow`, `scoreboard`).
        Mirrors the per-innings surface a fresh `__init__` would have after
        those fields are restored — used by `full_reset()` so cold-start
        re-entry does not leave `bat1_*` / `bowler_*` / `this_over` stale.
        """
        self.score = None
        self.wickets = None
        self.overs = None
        self.run_rate = None

        self.bat1_name = None
        self.bat2_name = None

        self.bowler_name = None

        self.striker = None
        self.non = None

        self.required_run_rate = None
        self.balls_remaining = None
        self.match_phase = None
        self.bat1_sr = None
        self.bat2_sr = None
        self.bowler_economy = None

        self.this_over = []
        self.this_over_src = []
        self.over_history = {}
        self.completed_over = None
        self.completed_over_runs = None

        self.partnership_runs = 0
        self.partnership_balls = 0
        self.partnership_known = True

        self._extras_sm_internal = _blank_extras_dict()
        self._fow_sm_internal.clear()
        if self.scoreboard is not None:
            self.scoreboard.fall_of_wickets.clear()
            self.scoreboard.extras.clear()
            self.scoreboard.extras.update(_blank_extras_dict())
        self.free_hit_next = False

        self.last_speed = None
        self.last_speed_at_over = None

        self.pending_extra = None
        self.pending_extra_frames = 0
        self.pending_wicket = None
        self.pending_wicket_frames = 0

        self.recent_frames = []

        self.last_event = None
        self.frames_since_event = 0

        self._overs_regress_streak = 0
        self._overs_regress_from = None
        self._regression_streak = 0

    def full_reset(self, reason: str = "") -> None:
        """Cold-start re-entry **plus** full Fix-16 per-innings scalar wipe.

        `force_cold_start_recalibration()` alone only clears cold-start
        bookkeeping; cached batter/bowler/extras/FOW/partnership fields
        remain (Fix 16 surface).  Phase 2 state-recovery mutation will call
        this method instead of `force_cold_start_recalibration()` alone.

        Preserves: `innings`, `target`, `batting_team`, `venue`,
        `match_info`, `innings_history`, `shadow`, `scoreboard`.
        """
        log.warn(f"[SM-FULL-RESET] reason={reason or 'external'}")
        self.force_cold_start_recalibration(
            reason=f"full_reset:{reason or 'external'}")
        self._clear_per_innings_sm_surface()
        # Do not validate the next cold-start seed against the pre-reset
        # WARM snapshot — that surface included the stale scalars we just
        # cleared.
        self._last_warm_state = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_frame(self, frame: FrameInput) -> dict | None:
        """Called every frame. Returns UI payload dict or None."""
        # Stage 2d: backfill prior frame's ACCEPTED_NOOP if nothing
        # fired during its processing. Lagged by one frame; the very
        # last frame of a session stays NOT_YET_SEEN (acceptable
        # given session-boundary semantics).
        if _get_ledger is not None:
            try:
                prev_fid = getattr(self, "_last_frame_id_for_ledger", None)
                if prev_fid is not None:
                    from eyes.frame_ledger import (
                        ExtractorOutcome as _EO)
                    _ledger = _get_ledger()
                    _entry = _ledger.get(prev_fid)
                    if _entry is not None and _entry.sm_outcome == \
                            _SmOutcome.NOT_YET_SEEN:
                        _noop = (
                            _SmOutcome.ACCEPTED_NOOP_NULL_OVERS
                            if _entry.extractor_outcome == _EO.NULL_OVERS
                            else _SmOutcome.ACCEPTED_NOOP)
                        _ledger.record_sm_outcome_if_unset(
                            prev_fid, _noop)
                try:
                    self._last_frame_id_for_ledger = int(frame.frame_id)
                except (TypeError, ValueError, AttributeError):
                    self._last_frame_id_for_ledger = None
            except Exception:
                pass
        self._frame_int(frame)
        self.recent_frames.append(frame)
        if len(self.recent_frames) > 5:
            self.recent_frames.pop(0)

        if frame.drs_state == "IN_PROGRESS":
            return None

        if not self._inn2_bootstrap_attempted:
            self._attempt_inn2_bootstrap(frame)

        # Count ScoreManager-visible frames while cold even when scorer strips
        # the inbound card ( `_build_scorecard` → None).  Older logic only
        # advanced counters inside `_handle_cold_start`, letting POISON-RECAL /
        # FRAME_POISONED windows stall without tripping consensus *or*
        # `cold_frames`-based give-ups.
        if self.mode == "COLD_START":
            self._cold_pipeline_frames += 1

        card = self._build_scorecard(frame)
        if card is None:
            self.frames_since_event += 1
            resolved = self._try_resolve_pending(frame)
            if resolved:
                return self._build_payload(resolved)
            return None

        if not self._is_valid(card):
            return None

        if self.mode == "COLD_START":
            return self._handle_cold_start(card, frame)
        else:
            return self._handle_warm(card, frame)

    def stop(self):
        self.__init__(shadow=self.shadow)

    def start(self):
        self.__init__(shadow=self.shadow)

    # ------------------------------------------------------------------
    # Build scorecard from frame data
    # ------------------------------------------------------------------

    def _build_scorecard(self, frame: FrameInput) -> dict | None:
        card: dict[str, Any] = {}

        if frame.ext_score is not None:
            card["score"] = frame.ext_score
        if frame.ext_wickets is not None:
            card["wickets"] = frame.ext_wickets
        if frame.ext_overs is not None:
            card["overs"] = frame.ext_overs

        # Fallback: parse scorer changes
        if "score" not in card:
            for c in frame.scorer_changes:
                if c.startswith("score→"):
                    try:
                        card["score"] = int(c.split("→")[1].split("(")[0])
                    except (ValueError, IndexError):
                        pass
        if "wickets" not in card:
            for c in frame.scorer_changes:
                if c.startswith("wickets→"):
                    try:
                        card["wickets"] = int(c.split("→")[1])
                    except (ValueError, IndexError):
                        pass
        if "overs" not in card:
            for c in frame.scorer_changes:
                if c.startswith("overs→"):
                    try:
                        card["overs"] = float(c.split("→")[1])
                    except (ValueError, IndexError):
                        pass

        if "score" not in card:
            return None

        # Batters
        card["bat1_name"] = frame.ext_bat1_name
        card["bat1_runs"] = frame.ext_bat1_runs
        card["bat1_balls"] = frame.ext_bat1_balls
        card["bat2_name"] = frame.ext_bat2_name
        card["bat2_runs"] = frame.ext_bat2_runs
        card["bat2_balls"] = frame.ext_bat2_balls

        # Scorer may have resolved full names
        for c in frame.scorer_changes:
            if c.startswith("bat:"):
                name_stats = c[4:]
                eq = name_stats.find("=")
                if eq > 0:
                    full_name = name_stats[:eq]
                    if (card["bat1_name"]
                            and card["bat1_name"].lower() in full_name.lower()):
                        card["bat1_name"] = full_name
                    elif (card["bat2_name"]
                            and card["bat2_name"].lower() in full_name.lower()):
                        card["bat2_name"] = full_name

        # Bowler
        card["bowler_name"] = frame.ext_bowler_name
        card["bowler_wickets"] = frame.ext_bowler_wickets
        card["bowler_runs"] = frame.ext_bowler_runs
        card["bowler_overs"] = frame.ext_bowler_overs

        for c in frame.scorer_changes:
            if c.startswith("bowl:"):
                full_name = c[5:]
                if (card["bowler_name"]
                        and card["bowler_name"].lower() in full_name.lower()):
                    card["bowler_name"] = full_name

        # Broadcast supplements
        card["speed_kph"] = frame.speed_kph
        card["extras_total"] = frame.ext_extras_total
        card["broadcast_extra"] = frame.broadcast_extra
        card["broadcast_striker"] = frame.broadcast_striker
        card["broadcast_this_over"] = frame.broadcast_this_over
        card["action_text"] = frame.action_text

        # === Canonicalize all names at the single entry point ===
        # Issue 1 fix (2026-04-21): SM previously stored whatever raw
        # scout surname the extractor emitted ("N RANA", "Rahul"), then
        # downstream code compared these against canonical batting_card
        # keys ("Nitish Rana", "KL Rahul") and always missed — producing
        # a UI where no batter is ever marked as the striker.  Normalize
        # here so self.bat1_name, self.striker etc. carry canonical
        # squad keys throughout.  If the scoreboard can't resolve a
        # name we keep the raw value (SM's consensus/validation layers
        # need something to key on) but the downstream output boundary
        # layer in build_full_payload does a second canonicalize pass
        # as defense in depth.
        for _k in ("bat1_name", "bat2_name", "bowler_name",
                   "broadcast_striker"):
            _raw = card.get(_k)
            if _raw:
                # Class-9 fix (2026-05-20): enforce squad-canonical or
                # reject. Previous behavior kept raw on resolver-None,
                # letting OCR junk like "PATHUM RAHUL" reach striker
                # assignment. Now resolver-None → card[_k]=None →
                # downstream consumers treat as "no name signal this
                # frame; preserve prior identity." Cold-start (no
                # scoreboard) still passes raw through.
                card[_k] = self._squad_canonical_or_reject(_raw, _k)

        return card

    def _make_fow_placeholder(self, wicket_number: int) -> dict:
        """Create an FOW placeholder entry in the canonical shape.

        Issue 4 fix (2026-04-21): SM's three placeholder sites used a
        minimal `{"score": "?", "overs": "?"}` shape that diverged from
        Scoreboard's `{batter: None, _unwitnessed: True, ...}`.  The UI
        rendered SM placeholders as confirmed wickets with garbage
        values.  Delegate to the Scoreboard factory when available so
        both pipelines produce identical placeholder rows.
        """
        if self.scoreboard is not None:
            try:
                return self.scoreboard.make_fow_placeholder(wicket_number)
            except Exception:
                pass
        return {
            "wicket": int(wicket_number),
            "batter": None,
            "score": None,
            "overs": None,
            "bowler": None,
            "_unwitnessed": True,
        }

    def _canonicalize_name(self, raw: str | None,
                           slot: str = "") -> str | None:
        """Resolve a raw scout name to its canonical squad key.

        Returns canonical name when resolvable, None when not (so the
        caller can decide whether to fall back to raw or drop the
        update).  Deliberately conservative: only returns a canonical
        name when both resolve_name() and _find_card_key() succeed,
        matched against the appropriate card (batting for bat/striker
        slots, bowling for bowler slot).
        """
        if not raw or not self.scoreboard:
            return None
        try:
            resolved = self.scoreboard.resolve_name(raw)
            if not resolved:
                return None
            card_dict = (
                self.scoreboard.bowling_card
                if slot.startswith("bowler")
                else self.scoreboard.batting_card
            )
            if not card_dict:
                return None
            key = self.scoreboard._find_card_key(resolved, card_dict)
            return key
        except Exception:
            return None

    def _same_player_canon(self, a: str | None,
                            b: str | None) -> bool:
        """Class 9b helper (2026-05-20): canonical-aware identity
        comparison for the wicket slot-clearing path.

        Returns True when a and b refer to the same squad player.
        First tries strict equality (fast path, common case). On
        miss, canonicalizes both via Scoreboard.resolve_name (the
        same resolver enforced at SM commit gates) and compares
        canonicals. Different identity-source canonicalization paths
        (event/broadcast vs slot-state) can produce non-equal strings
        that resolve to the same canonical squad name.
        """
        if not a or not b:
            return False
        if a == b:
            return True
        if not self.scoreboard:
            return False
        try:
            canon_a = self.scoreboard.resolve_name(a) or a
            canon_b = self.scoreboard.resolve_name(b) or b
            return canon_a == canon_b
        except Exception:
            return False

    def _squad_canonical_or_reject(self, raw: str | None,
                                   slot: str = "") -> str | None:
        """Class-9 gate (2026-05-20): canonicalize a raw Scout name
        against the loaded squad, or reject it.

        Behavior:
        - Empty raw → return raw unchanged.
        - No scoreboard loaded (cold-start pre-roster) → return raw
          unchanged (passthrough; SM consensus layers handle).
        - Scoreboard loaded but resolver returns None → emit
          ``NAME-REJECTED-NOT-IN-SQUAD`` trace with best near-match
          diagnostic, return None. Caller treats None as "no name
          signal this frame; preserve prior identity."
        - Resolver returns canonical → return canonical.
        """
        if not raw:
            return raw
        if not self.scoreboard:
            return raw
        canon = self._canonicalize_name(raw, slot)
        if canon is not None:
            return canon
        # Rejected — compute best near-match for diagnostic payload.
        best_match = None
        best_score = 0.0
        try:
            lookup = getattr(
                self.scoreboard, "_name_lookup", None) or {}
            sim_fn = getattr(
                self.scoreboard, "_name_similarity", None)
            if sim_fn is not None:
                clean = str(raw).upper().strip()
                for key, val in lookup.items():
                    if len(key) < 4 and len(clean) > 4:
                        continue
                    s = sim_fn(clean, key)
                    if s > best_score:
                        best_score = float(s)
                        best_match = val
        except Exception:
            pass
        log.warn(
            f"[NAME-REJECTED-NOT-IN-SQUAD] raw={raw!r} slot={slot!r} "
            f"best_match={best_match!r} score={best_score:.2f} "
            f"— preserving prior identity")
        if _trace is not None:
            try:
                _trace.get_recorder().record(
                    tag="NAME-REJECTED-NOT-IN-SQUAD",
                    raw=raw, slot=slot,
                    best_fuzzy_match=best_match,
                    best_fuzzy_score=round(best_score, 2),
                    frame_id=getattr(self, "_current_frame", None))
            except Exception:
                pass
        return None

    def _set_slot_pair(self, striker: str | None, non: str | None,
                       *, source: str) -> None:
        """Write ``striker`` / ``non`` together (single tuple unpack).

        Canonicalizes both values via :meth:`_canonicalize_name` (batting
        slots), then falls back to the raw input when no scoreboard or no
        resolution — mirroring :meth:`_build_payload` defense-in-depth.

        If both canonical values are non-``None`` and equal, logs
        ``[SM-SLOT-INVARIANT]`` with ``source=`` and clears ``non``
        so the SM surface matches the single-slot repair used downstream
        by ``enforce_ws_slot_invariant``.

        Contract: ``source`` is **required** for telemetry (Lever 1 —
        ``sm_rotation_atomicity_design.md`` §6). Call-sites will migrate in
        PR2+; PR1 ships the helper only.
        """
        _s = self._canonicalize_name(striker) or striker
        _ns = self._canonicalize_name(non) or non
        if _s is not None and _ns is not None and _s == _ns:
            log.warn(
                f"[SM-SLOT-INVARIANT] duplicate slots {_s!r} "
                f"(source={source}); clearing non")
            _ns = None
        self.striker, self.non = _s, _ns

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _is_valid(self, card: dict) -> bool:
        s = card.get("score")
        w = card.get("wickets")
        o = card.get("overs")

        if s is not None and s < 0:
            return False
        if w is not None and (w < 0 or w > 10):
            return False

        if o is not None:
            ball = round((o % 1) * 10)
            if ball > 5:
                return False
            if o > 20.0:
                return False

        # Reject stale 0-0(0.0) when match is already running
        if (s == 0 and w == 0 and o is not None and o == 0.0
                and self.overs is not None and self.overs > 1.0):
            return False

        # Batter runs can't exceed team score
        for key in ("bat1_runs", "bat2_runs"):
            r = card.get(key)
            if r is not None and s is not None and r > s:
                return False

        return True

    # ------------------------------------------------------------------
    # Cold start
    # ------------------------------------------------------------------

    def _synthesize_cold_start_ball_events(
        self,
        implied_balls: int,
        implied_runs: int,
        implied_wickets: int,
    ) -> list[dict]:
        """Generate synthetic ball events for the cold-start convergence gap.

        Distribution heuristic (see commit message):
          - If ``implied_runs in (4, 6)``: boundary signature — all runs to
            the last ball, dots for the rest.
          - Else if ``implied_runs <= implied_balls``: dots first, then ones
            until reaching the total.
          - Else: ones across all-but-last; remainder attributed to last.

        Wickets are not distributed (no observation basis for which ball
        carried the wicket); their count is recorded in the trace tag so
        post-match audit can flag the gap.

        Events are written to ``self._cold_start_synthesized_events`` and
        the inferred tokens overwrite the "?" placeholders in
        ``self.this_over`` so the UI reflects the synthesised over.

        Bowler / striker credit (Issue 1 fix, 2026-05-14): when BOTH
        ``self.bowler_name`` and ``self.striker`` are populated (the
        LOCKED proxy from within score_manager), the synth walks the
        tokens and credits bowling_card / batting_card via the existing
        delta APIs with the same per-token distribution + odd-run
        striker rotation pattern used by the MULTI_BALL decomposition
        (A2 part 2 / 32a2207).  When either slot is None, falls back
        to the legacy no-credit behavior — the gap by definition lacks
        the name observation needed to attribute credit safely.
        """
        if implied_balls <= 0:
            return []

        if implied_runs in (4, 6):
            tokens = ["."] * (implied_balls - 1) + [str(implied_runs)]
        elif implied_runs <= implied_balls:
            n_singles = implied_runs
            n_dots = implied_balls - n_singles
            tokens = ["."] * n_dots + ["1"] * n_singles
        else:
            excess = implied_runs - (implied_balls - 1)
            tokens = ["1"] * (implied_balls - 1) + [str(excess)]

        events: list[dict] = []
        for i, tok in enumerate(tokens):
            try:
                runs = 0 if tok == "." else int(tok)
            except ValueError:
                runs = 0
            ev = {
                "type": "SYNTHESIZED",
                "ball_index": i,
                "runs": runs,
                "token": tok,
                "synthesized": True,
                "striker": None,
                "bowler": None,
            }
            events.append(ev)
            if _trace is not None:
                try:
                    _trace.get_recorder().record(
                        tag="COLD-START-SYNTHESIZED-EVENT",
                        ball_index=i,
                        runs=runs,
                        token=tok,
                        implied_balls=implied_balls,
                        implied_runs=implied_runs,
                        implied_wickets=implied_wickets,
                    )
                except Exception:
                    pass

        log.info(
            f"[COLD-START-SYNTHESIZE] balls={implied_balls} "
            f"runs={implied_runs} wickets={implied_wickets} "
            f"tokens={tokens}")

        self._cold_start_synthesized_events = list(events)
        self.this_over = list(tokens)
        try:
            self.this_over_src = ["synth"] * len(tokens)
        except AttributeError:
            pass

        # Class 8 sub-pattern B fix (2026-05-20): partnership is an
        # aggregate identity-blind metric; previously it was credited
        # only inside the gated walk below (which requires bowler +
        # striker to be resolved). When the gap exits cold-start
        # before either name has propagated through trackers, the
        # walk skipped — partnership stayed at 0 through the synth
        # window, lagging by exactly implied_runs forever after.
        # Decoupled here: unconditional aggregate, runs even when
        # the per-batter / per-bowler walk skips.
        # Equivalence: synth's token distribution generates W-free
        # token lists where sum(int-tokens) == implied_runs, so
        # aggregate (implied_runs/implied_balls) == in-loop sum.
        try:
            if not self.partnership_known:
                self.partnership_runs = 0
                self.partnership_balls = 0
                self.partnership_known = True
            _pship_runs_before = int(self.partnership_runs or 0)
            _pship_balls_before = int(self.partnership_balls or 0)
            self.partnership_runs = (
                int(self.partnership_runs or 0) + int(implied_runs))
            self.partnership_balls = (
                int(self.partnership_balls or 0) + int(implied_balls))
            if _trace is not None:
                try:
                    _trace.get_recorder().record(
                        tag="PARTNERSHIP-WRITE",
                        runs_before=_pship_runs_before,
                        balls_before=_pship_balls_before,
                        runs_after=int(self.partnership_runs or 0),
                        balls_after=int(self.partnership_balls or 0),
                        source="synth_cold_start_aggregate",
                        implied_runs=int(implied_runs),
                        implied_balls=int(implied_balls),
                        frame_id=str(self._current_frame))
                except Exception:
                    pass
        except Exception:
            pass

        # Issue 1 (2026-05-14): credit synthesized balls to bowler /
        # striker when BOTH name slots are populated.  `self.bowler_name`
        # and `self.striker` are non-None only after their respective
        # ConfidenceTrackers have committed (LOCKED) and the SM-side
        # setter has propagated the name — so non-None acts as the
        # LOCKED proxy from within score_manager.  When either slot is
        # None, fall back to legacy no-credit behavior (the original
        # "no observation basis" caveat).  Strike rotation is local
        # (mirrors self.striker / self.non); committed via
        # _set_slot_pair at the end if odd-run count flipped the
        # striker.
        # Issue 1 follow-up (2026-05-14): fallback through scoreboard
        # accessors when SM-side slots haven't propagated yet.  The
        # cold-start window has a known propagation gap — at the moment
        # _synthesize_cold_start_ball_events runs, _accept_initial may
        # not have committed self.striker / self.bowler_name yet (the
        # card's bat1_name / bowler_name fields can arrive None when
        # upstream strip reads were dropped by the digits-false veto).
        # Fall back to the scoreboard's current_bowler + SM's bat1_name
        # so synth credits don't silently skip.
        bowler_name = self.bowler_name
        if not bowler_name and self.scoreboard is not None:
            try:
                bowler_name = (
                    self.scoreboard._inn or {}).get("current_bowler")
            except Exception:
                bowler_name = None
        striker_name = self.striker
        if not striker_name:
            striker_name = self.bat1_name or getattr(
                self, "_pending_striker", None)
        non_name = self.non or self.bat2_name
        _fallback_used = (
            bowler_name != self.bowler_name
            or striker_name != self.striker)
        if (bowler_name and striker_name and self.scoreboard is not None
                and implied_balls > 0):
            _cur_str = striker_name
            _cur_non = non_name
            for i, _tok in enumerate(tokens):
                if _tok in (".", "W", "?"):
                    single_runs = 0
                else:
                    try:
                        single_runs = int(_tok)
                    except (TypeError, ValueError):
                        single_runs = 0
                _wkt_delta = 1 if _tok == "W" else 0
                try:
                    self.scoreboard.update_bowler(
                        bowler_name,
                        runs_delta=single_runs,
                        balls_delta=1,
                        wickets_delta=_wkt_delta,
                        frame=self._current_frame)
                except Exception:
                    pass
                if _cur_str and _tok != "W":
                    try:
                        self.scoreboard.update_batter(
                            _cur_str,
                            runs_delta=single_runs,
                            balls_delta=1,
                            fours_delta=1 if _tok == "4" else 0,
                            sixes_delta=1 if _tok == "6" else 0,
                            frame=self._current_frame)
                    except Exception:
                        pass
                # Partnership accumulation moved to identity-blind
                # aggregate block above (class-8 sub-pattern B fix,
                # 2026-05-20). The per-token in-loop write was lossy
                # because the entire walk skipped when bowler/striker
                # weren't resolved yet. Per-batter / per-bowler credit
                # stays in this loop; partnership doesn't need it.
                if _trace is not None:
                    try:
                        _trace.get_recorder().record(
                            tag="COLD-START-SYNTH-CREDITED",
                            token=_tok,
                            ball_index=i,
                            total_balls=implied_balls,
                            single_ball_runs=single_runs,
                            bowler=bowler_name,
                            striker=_cur_str,
                            wicket_credited=bool(_wkt_delta),
                            fallback_used=bool(_fallback_used),
                            partnership_balls_after=int(
                                self.partnership_balls or 0),
                            partnership_runs_after=int(
                                self.partnership_runs or 0),
                            frame_id=str(self._current_frame))
                    except Exception:
                        pass
                if single_runs % 2 == 1 and _cur_non:
                    _cur_str, _cur_non = _cur_non, _cur_str
            if (_cur_str and _cur_str != striker_name and _cur_non):
                try:
                    self._set_slot_pair(
                        _cur_str, _cur_non,
                        source="cold_start_synth")
                except Exception:
                    pass
        return events

    def _maybe_synthesize_cold_start_gap(self) -> None:
        """Compute deltas from cold-start entry → WARM anchor and dispatch
        to ``_synthesize_cold_start_ball_events`` if any balls passed.
        Called from every COLD_START → WARM transition site.
        """
        entry = self._cold_start_entry or {
            "score": 0, "wickets": 0, "overs": 0.0}
        try:
            anchor_balls = self._overs_to_balls(self.overs or 0.0)
            entry_balls = self._overs_to_balls(entry.get("overs") or 0.0)
        except (TypeError, ValueError):
            return
        implied_balls = max(0, anchor_balls - entry_balls)
        implied_runs = max(0, (self.score or 0) - (entry.get("score") or 0))
        implied_wickets = max(
            0, (self.wickets or 0) - (entry.get("wickets") or 0))
        if implied_balls > 0:
            self._synthesize_cold_start_ball_events(
                implied_balls, implied_runs, implied_wickets)

    def _handle_cold_start(self, card: dict, frame: FrameInput) -> dict | None:
        self.cold_frames += 1

        # Cold-start requires the minimum viable scorecard (score, wickets,
        # overs all present). Without this guard, a frame that only reads
        # the score field would seed `cold_candidate` with overs=None, and
        # 3 such matching frames would trigger COLD_START → WARM with
        # overs=None — which then crashes `_apply_event` at the first
        # `int(card["overs"])` call. We do NOT reset the existing
        # candidate streak on an incomplete read; we just skip this frame
        # so the next more-complete frame can extend (or flip) the
        # candidate normally.
        if (card.get("score") is None
                or card.get("wickets") is None
                or card.get("overs") is None):
            return None

        # Pre-match VLM-hallucination gate.  Rejected frames roll back the
        # `cold_frames` increment so the give-up budget is not consumed
        # by frames that never reach the accumulator.  See the
        # `_COLD_START_PREMATCH_CUE` / `_is_skeleton_strip` block at the
        # top of this module for the investigation reference.
        if _is_skeleton_strip(frame):
            self.cold_frames -= 1
            _record_cold_start_reject(
                "COLD-START-SKELETON-STRIP-REJECT", frame, card)
            return None
        if _COLD_START_PREMATCH_CUE.search(frame.scout_text or ""):
            self.cold_frames -= 1
            _record_cold_start_reject(
                "COLD-START-PREMATCH-CUE-REJECT", frame, card)
            return None

        if self._false_zero_cold_start(card, frame):
            self.cold_candidate = None
            self.cold_candidate_streak = 0
            log.info(
                f"[SM] cold-start zero candidate rejected as contextual "
                f"graphic: scout={frame.scout_text[:80]!r}")
            return None

        # Last coarse strip snapshot that survives the false-zero heuristic.
        self._cold_last_viable = copy.deepcopy(card)

        _fb_payload = self._cold_start_maybe_pipeline_fallback(frame)
        if _fb_payload is not None:
            return _fb_payload

        if self.cold_candidate is None:
            # P12 cold-start commit lockout: during innings-2
            # transition window, require 3 consecutive frames passing
            # numeric bounds before allowing the seed.  Card here has
            # no batter/bowler rows (filtered upstream by Phase B), so
            # gate set is bounds-only.
            if self.in_inn2_transition(self._current_frame):
                _s = card.get("score") or 0
                _w = card.get("wickets") or 0
                _o = card.get("overs") or 0.0
                _gate_reason = None
                if _s > 30:
                    _gate_reason = f"score>30:{_s}"
                elif _w > 2:
                    _gate_reason = f"wickets>2:{_w}"
                elif _o > 5.0:
                    _gate_reason = f"overs>5.0:{_o}"
                if _gate_reason is not None:
                    log.info(
                        f"[INN2-COLD-START-LOCKOUT] proposed seed "
                        f"{_s}/{_w} ({_o}) rejected — "
                        f"reason={_gate_reason}")
                    self._inn2_consensus_count = 0
                    return None
                self._inn2_consensus_count = (
                    getattr(self, "_inn2_consensus_count", 0) + 1)
                if self._inn2_consensus_count < 3:
                    log.info(
                        f"[INN2-COLD-START-CONSENSUS] frame "
                        f"{self._inn2_consensus_count}/3 — "
                        f"deferring seed")
                    return None
            self.cold_candidate = card
            self.cold_candidate_streak = 1
            log.info(
                f"[SM] cold-start candidate seeded "
                f"{card.get('score')}/{card.get('wickets')} "
                f"({card.get('overs')}) — streak 1/"
                f"{self.COLD_START_CONSENSUS_FRAMES}")
            self.mark_inn2_first_commit()
            return None

        consensus = (
            self.cold_candidate.get("score") == card.get("score")
            and self.cold_candidate.get("wickets") == card.get("wickets")
            and abs((self.cold_candidate.get("overs") or 0)
                    - (card.get("overs") or 0)) < 0.05
        )

        if not consensus:
            # Option E (2026-05-14): physics-linked promotion.  Before
            # flipping the candidate and resetting the streak, check
            # whether the candidate → card transition is a legal
            # forward step (cricket_rules validate_diff passes AND
            # the ball-count delta is within the cold-start cap).  If
            # so, treat as a MULTI_BALL gap: seed WARM at the
            # candidate, then commit the card as a synthetic
            # MULTI_BALL event so bowler / batter / this_over all
            # accumulate via the existing event derivation path.
            try:
                _cand_overs = float(
                    self.cold_candidate.get("overs") or 0.0)
                _card_overs = float(card.get("overs") or 0.0)
                _cand_score = int(self.cold_candidate.get("score") or 0)
                _card_score = int(card.get("score") or 0)
                _cand_wkts = int(self.cold_candidate.get("wickets") or 0)
                _card_wkts = int(card.get("wickets") or 0)
                _d_balls = (self._overs_to_balls(_card_overs)
                            - self._overs_to_balls(_cand_overs))
                _d_score = _card_score - _cand_score
                _d_wkt = _card_wkts - _cand_wkts
            except (TypeError, ValueError):
                _d_balls = -1
                _d_score = 0
                _d_wkt = 0
            _promote = False
            if 0 < _d_balls <= COLD_START_MULTI_BALL_MAX_BALLS:
                _diff = Diff(
                    d_score=_d_score, d_balts=_d_balls, d_wkt=_d_wkt)
                _diff_check = validate_diff(
                    _diff,
                    new_score=_card_score,
                    new_wickets=_card_wkts,
                    new_overs=_card_overs,
                    target=self.target,
                    innings=self.innings)
                _promote = bool(_diff_check.ok)
            if _promote:
                log.info(
                    f"[SM] COLD-START-PHYSICS-PROMOTE: candidate "
                    f"{_cand_score}/{_cand_wkts} ({_cand_overs}) → "
                    f"card {_card_score}/{_card_wkts} ({_card_overs}) "
                    f"accepted as legal forward step "
                    f"(d_balls={_d_balls}, d_score={_d_score}, "
                    f"d_wkt={_d_wkt}); seeding WARM at candidate and "
                    f"committing card as MULTI_BALL gap")
                # S4a step (i) instrumentation (2026-05-20): this Path B
                # branch (COLD_START_PHYSICS_PROMOTE) was empirically dead
                # across the 9-fixture L2 corpus (0 fires). Adding a
                # high-visibility WARN log to surface any production
                # firing before S4a step (ii) deletes the branch. Run
                # for at least one production session; if PATH-B-FIRED
                # never appears, S4a step (ii) deletes Path B.
                log.warn(
                    f"[PATH-B-FIRED] COLD_START_PHYSICS_PROMOTE "
                    f"frame={self._current_frame} "
                    f"candidate_score={_cand_score} "
                    f"candidate_overs={_cand_overs} "
                    f"card_score={_card_score} card_overs={_card_overs} "
                    f"d_balls={_d_balls} d_score={_d_score} "
                    f"— Path B fired in production; see scoping doc "
                    f"before S4a step (ii) deletion ships")
                if _trace is not None:
                    try:
                        _trace.get_recorder().record(
                            tag="COLD-START-PHYSICS-PROMOTE",
                            candidate_score=_cand_score,
                            candidate_overs=_cand_overs,
                            candidate_wickets=_cand_wkts,
                            card_score=_card_score,
                            card_overs=_card_overs,
                            card_wickets=_card_wkts,
                            d_balls=_d_balls,
                            d_score=_d_score,
                            d_wkt=_d_wkt,
                            frame_id=str(self._current_frame))
                    except Exception:
                        pass
                # 1. Seed WARM at the candidate.  _accept_initial
                #    handles the COLD→WARM bookkeeping and seeds
                #    _event_baseline_score (per 44f2510).
                _candidate_for_seed = dict(self.cold_candidate)
                self._last_warm_state = None
                self._accept_initial(_candidate_for_seed, frame)
                self.mode = "WARM"
                # 2. Snapshot the just-seeded state as `prev` for the
                #    gap event.
                _prev_snap = self._snapshot()
                # 3. Advance SM state to the card (so bowler/striker
                #    name resolution + downstream consumers see the
                #    new score/overs/wickets).
                self._accept_update(card, self._current_frame)
                # 4. Construct + apply the synthetic MULTI_BALL event.
                #    A1 part 2's MULTI_BALL decomp in
                #    _accumulate_stats_from_event credits bowler.runs
                #    + balls; the unified gap-token helper (86e9aa4)
                #    populates this_over from the same distribution.
                _mb_event = {
                    "type": "COLD_START_SYNTH",
                    "balls_missed": _d_balls,
                    "total_runs": _d_score,
                    "wickets_in_gap": _d_wkt,
                    "certain": False,
                    "striker": self.striker,
                    "this_over_token": "?",
                }
                self._apply_event(_mb_event, _prev_snap, card, frame)
                self.last_event = _mb_event
                self.frames_since_event = 0
                self._recompute()
                return self._build_payload(
                    _mb_event, ball_events=[_mb_event])
            log.info(
                f"[SM] cold-start candidate flipped "
                f"{self.cold_candidate.get('score')}/"
                f"{self.cold_candidate.get('wickets')} "
                f"({self.cold_candidate.get('overs')}) → "
                f"{card.get('score')}/{card.get('wickets')} "
                f"({card.get('overs')}) — streak reset to 1/"
                f"{self.COLD_START_CONSENSUS_FRAMES} "
                f"(physics-promote not eligible: "
                f"d_balls={_d_balls}, cap="
                f"{COLD_START_MULTI_BALL_MAX_BALLS})")
            self.cold_candidate = card
            self.cold_candidate_streak = 1
            max_f = (COLD_MAX_FRAMES_WITH_REF if self._last_warm_state
                     else COLD_MAX_FRAMES)
            if self.cold_frames >= max_f:
                # Even on the give-up path, never adopt a card that
                # violates absolute / chase / overs ceilings.
                abs_check = validate_absolute(
                    score=card.get("score"),
                    wickets=card.get("wickets"),
                    overs=card.get("overs"),
                    target=self.target, innings=self.innings)
                if not abs_check.ok:
                    log.info(f"[SM] cold-start give-up REJECT "
                             f"({abs_check.reject_reason})")
                    return None
                if not self._cold_start_plausible(card):
                    log.info(
                        f"[SM] cold-start max-frames-timeout deferred: "
                        f"implausible_candidate "
                        f"{card.get('score')}/{card.get('wickets')} "
                        f"({card.get('overs')})")
                    self.cold_frames = 0
                    return None
                self._last_warm_state = None
                self._accept_initial(card, frame)
                self.mode = "WARM"
                log.info(f"[SM] COLD_START → WARM (max frames, ref cleared)  "
                         f"{self.score}/{self.wickets} ({self.overs})")
                self._maybe_synthesize_cold_start_gap()
                return self._build_payload()
            return None

        # Bump streak — this frame agrees with the candidate.
        self.cold_candidate_streak += 1
        if self.cold_candidate_streak < self.COLD_START_CONSENSUS_FRAMES:
            log.info(
                f"[SM] cold-start consensus building "
                f"{card.get('score')}/{card.get('wickets')} "
                f"({card.get('overs')}) — streak "
                f"{self.cold_candidate_streak}/"
                f"{self.COLD_START_CONSENSUS_FRAMES}")
            return None

        if not self._cold_start_plausible(card):
            self.cold_candidate = card
            self.cold_candidate_streak = 1
            if self.cold_frames >= COLD_MAX_FRAMES_WITH_REF:
                # Same escape-hatch absolute guard as above — refuse to
                # adopt a chase-impossible / >320 / >20-over card even
                # when the consensus mechanism has timed out.
                abs_check = validate_absolute(
                    score=card.get("score"),
                    wickets=card.get("wickets"),
                    overs=card.get("overs"),
                    target=self.target, innings=self.innings)
                if not abs_check.ok:
                    log.info(f"[SM] cold-start give-up REJECT "
                             f"({abs_check.reject_reason})")
                    return None
                self._last_warm_state = None
                self._accept_initial(card, frame)
                self.mode = "WARM"
                log.info(f"[SM] COLD_START → WARM (max frames, ref cleared)  "
                         f"{self.score}/{self.wickets} ({self.overs})")
                self._maybe_synthesize_cold_start_gap()
                return self._build_payload()
            return None

        self._last_warm_state = None
        self._accept_initial(card, frame)
        self.mode = "WARM"
        log.info(
            f"[SM] COLD_START → WARM (consensus "
            f"{self.cold_candidate_streak}/"
            f"{self.COLD_START_CONSENSUS_FRAMES})  "
            f"{self.score}/{self.wickets} ({self.overs})")
        self._maybe_synthesize_cold_start_gap()
        return self._build_payload()

    def _cold_start_maybe_pipeline_fallback(
            self,
            frame: FrameInput,
    ) -> dict | None:
        """If cold-start starvation thresholds tripped, anchor last viable triple."""
        lv = self._cold_last_viable
        if lv is None:
            return None

        starvation = (
            self._cold_pipeline_frames >= self._cold_pipeline_fallback_starvation)
        heavy_flip = (
            self._cold_pipeline_frames >= self._cold_pipeline_fallback_after
            and self.cold_frames >= COLD_MAX_FRAMES)

        if not (starvation or heavy_flip):
            return None

        snap = copy.deepcopy(lv)
        if not self._cold_start_plausible(snap):
            return None

        log.warn(
            "[COLD-START-FORCED-RECOVER] "
            f"cold_watchdog_frames={self._cold_pipeline_frames} "
            f"cold_iterations={self.cold_frames} "
            f"path={'starvation' if starvation else 'heavy_flip'} "
            f"snap={snap.get('score')}/{snap.get('wickets')}"
            f"({snap.get('overs')}) frame={frame.frame_id}")

        self._last_warm_state = None
        self._accept_initial(snap, frame)
        self.cold_candidate = None
        self.cold_candidate_streak = 0
        self.mode = "WARM"
        log.info(
            f"[SM] COLD_START → WARM (pipeline watchdog)  "
            f"{self.score}/{self.wickets} ({self.overs})")
        self._maybe_synthesize_cold_start_gap()
        return self._build_payload()

    def _cold_start_plausible(self, card: dict) -> bool:
        """Check if a cold-start candidate is plausible.

        Two regimes:
          - Pure cold start (no `_last_warm_state`, e.g. fresh pipeline
            boot mid-innings): only absolute / chase / overs ceilings
            apply.  Whatever scorecard the broadcast shows is adopted
            once consensus is reached.
          - Stale recovery (we had a WARM state and re-entered
            COLD_START): the candidate must be a legal cricket diff
            from the last warm state.
        """
        self.last_cold_start_verdict_implausible = False
        cs = card.get("score")
        co = card.get("overs")
        cw = card.get("wickets")

        # Always enforce absolute / chase / overs ceilings — even a
        # fresh cold-start scorecard like 446/2 is impossible.
        abs_check = validate_absolute(
            score=cs, wickets=cw, overs=co,
            target=self.target, innings=self.innings)
        if not abs_check.ok:
            log.info(f"[SM] cold-start reject ({abs_check.reject_reason})")
            if self.striker is not None:
                log.info(
                    f"[SM] cold-start reject also cleared self.striker "
                    f"(was={self.striker!r})")
                self.striker = None
            self.last_cold_start_verdict_implausible = True
            return False

        ref = self._last_warm_state
        if ref is None and (self.innings is None or self.innings == 1):
            cs_v = cs or 0
            co_v = co or 0
            cw_v = cw or 0
            if cw_v >= 2 and co_v < 1.0:
                log.info(
                    f"[SM] cold-start reject (inn1_impossible_wickets_overs: "
                    f"{cs_v}/{cw_v} ({co_v}))")
                if self.striker is not None:
                    log.info(
                        f"[SM] cold-start reject also cleared self.striker "
                        f"(was={self.striker!r})")
                    self.striker = None
                self.last_cold_start_verdict_implausible = True
                return False
            if cw_v >= 5 and co_v < 5.0:
                log.info(
                    f"[SM] cold-start reject (inn1_severe_collapse_implausible: "
                    f"{cs_v}/{cw_v} ({co_v}))")
                if self.striker is not None:
                    log.info(
                        f"[SM] cold-start reject also cleared self.striker "
                        f"(was={self.striker!r})")
                    self.striker = None
                self.last_cold_start_verdict_implausible = True
                return False
            if cw_v >= 3 and cs_v < cw_v * 2:
                log.info(
                    f"[SM] cold-start reject (inn1_score_too_low_for_wickets: "
                    f"{cs_v}/{cw_v} ({co_v}))")
                if self.striker is not None:
                    log.info(
                        f"[SM] cold-start reject also cleared self.striker "
                        f"(was={self.striker!r})")
                    self.striker = None
                self.last_cold_start_verdict_implausible = True
                return False

        if ref is None:
            return True

        rs = ref.get("score", 0) or 0
        ro = ref.get("overs", 0) or 0
        rw = ref.get("wickets", 0) or 0
        cs_v = cs or 0
        co_v = co or 0
        cw_v = cw or 0

        d_score = cs_v - rs
        d_balls = self._overs_to_balls(co_v) - self._overs_to_balls(ro)
        d_wickets = cw_v - rw

        # Cold-start exit-from-stale-recovery ceiling (2026-05-19).
        # The existing validate_diff below enforces cricket-physics
        # consistency but doesn't cap absolute jump magnitude — a
        # 34-ball jump with +15 runs passes its rules even though
        # at 1Hz scout cadence that's only possible from a graphic
        # overlay misread (frame 276 of watch_20260519_121701:
        # STRIP "(8.4)" glued from VISIBLE_TEXT "8 4.1"). Reject
        # exits where the balls jump exceeds 15 (≈2.3 overs)
        # combined with any meaningful score delta. Pure cold-start
        # entry (ref is None) is exempt via the early return at the
        # start of this method; we only reach here when there IS a
        # prior warm state to compare against.
        _COLD_EXIT_BALLS_CEILING = 15
        _COLD_EXIT_SCORE_FLOOR = 6
        if (d_balls > _COLD_EXIT_BALLS_CEILING
                and d_score > _COLD_EXIT_SCORE_FLOOR):
            if _trace is not None:
                try:
                    _trace.get_recorder().record(
                        tag="OVERS-JUMP-IMPLAUSIBLE-REJECTED",
                        proposed_overs=float(co_v),
                        current_overs=float(ro),
                        delta_balls=int(d_balls),
                        proposed_score=int(cs_v),
                        current_score=int(rs),
                        delta_score=int(d_score),
                        source="cold_start_exit_vs_last_warm")
                except Exception:
                    pass
            log.info(
                f"  [OVERS-JUMP-IMPLAUSIBLE-REJECTED] cold_start_exit "
                f"proposed={cs_v}/{cw_v} ({co_v}) "
                f"last_warm={rs}/{rw} ({ro}) "
                f"d_balls={d_balls} d_score={d_score} — "
                f"rejecting cold-exit (graphic-overlay misread class)")
            log.info(
                f"[GAP-AT-REJECTION] Δballs={d_balls} "
                f"proposed_overs={co_v} current_overs={ro} "
                f"proposed_score={cs_v} current_score={rs} "
                f"d_score={d_score} source=cold_start_exit_vs_last_warm")
            if _SmOutcome is not None:
                _ledger_record(
                    getattr(frame, "frame_id", None)
                    if not isinstance(frame, int) else frame,
                    _SmOutcome.REJECTED_COLD_EXIT,
                    payload={
                        "delta_balls": int(d_balls),
                        "proposed_overs": float(co_v),
                        "current_overs": float(ro),
                        "source": "cold_start_exit_vs_last_warm",
                    })
            self.last_cold_start_verdict_implausible = True
            return False

        # Stale-recovery diff must be a legal cricket transition.
        # Striker / bowler deltas unavailable across a re-entry — pass
        # None and rely on team-level invariants.
        diff = Diff(
            d_score=d_score, d_balts=d_balls, d_wkt=d_wickets,
            d_str_runs=None, d_str_balls=None,
            d_bwl_runs=None, d_bwl_wkt=None, d_bwl_balls=None)
        result = validate_diff(
            diff,
            new_score=cs_v, new_wickets=cw_v, new_overs=co_v,
            target=self.target, innings=self.innings)
        if not result.ok:
            log.info(
                f"[SM] cold-start reject ({result.reject_reason})  "
                f"ref={rs}/{rw}({ro}) → cand={cs_v}/{cw_v}({co_v})")
            if self.striker is not None:
                log.info(
                    f"[SM] cold-start reject also cleared self.striker "
                    f"(was={self.striker!r})")
                self.striker = None
            self.last_cold_start_verdict_implausible = True
            return False
        return True

    def _false_zero_cold_start(self, card: dict,
                               frame: FrameInput) -> bool:
        """Reject 0-0 cold-start cards that came from mid-match graphics."""
        if not (card.get("score") == 0
                and card.get("wickets") == 0
                and float(card.get("overs") or 0.0) == 0.0):
            return False
        text = (frame.scout_text or frame.action_text or "").upper()
        graphic_keywords = (
            "DRS", "REVIEW", "ULTRAEDGE", "ULTRA EDGE", "SNICKO",
            "BALL TRACKING", "HAWK", "FULL SCORECARD", "SCORECARD",
            "INTERVIEW", "IMPACT PLAYER", "PLAYER PROFILE",
        )
        has_mid_match_graphic = any(k in text for k in graphic_keywords)
        has_player_shape = bool(card.get("bat1_name") and card.get("bat2_name"))
        has_bowler_shape = bool(card.get("bowler_name"))
        return has_mid_match_graphic and not (
            has_player_shape and has_bowler_shape)

    def hot_resume_from_cache(self, cached: dict, frame: int) -> None:
        """Restore SM state from a validated cache dict.

        Does NOT call ``_accept_initial`` — that path expects a
        ``FrameInput`` and clobbers ``broadcast_team`` / ``target`` /
        ``venue`` / ``match_info`` with ``frame.broadcast_*`` defaults
        (None at hot-resume time), undoing what
        ``scoreboard.restore_from_cache`` just did on the scoreboard side.

        Caller must invoke ``scoreboard.restore_from_cache(cached)``
        separately (this method does NOT touch the scoreboard).
        Caller must also have already validated identity (match_id +
        session_id + age) — this method commits the cache as
        authoritative and exits ``COLD_START`` immediately.
        """
        self.score = cached.get("score")
        self.wickets = cached.get("wickets")
        _prior_overs_for_gap = self.overs
        self.overs = cached.get("overs")
        self._track_overs_advance(
            _prior_overs_for_gap, self.overs, frame)
        # A1 prerequisite (2026-05-14): seed _event_baseline_score so the
        # first post-resume event has a non-stale anchor (parity with
        # _accept_initial seed and the caedd4c innings-2 reset).  Without
        # this, the first innings event after a cache resume computes
        # d_score against scoreboard.score = cached_score (DIRECT path
        # may have pre-advanced before _handle_warm runs) and emits the
        # wrong type.
        try:
            self._event_baseline_score = (
                int(self.score) if self.score is not None else 0)
        except (TypeError, ValueError):
            self._event_baseline_score = 0
        if _trace is not None:
            try:
                _trace.get_recorder().record(
                    tag="EVENT-BASELINE-SEEDED-HOT-RESUME",
                    score=self._event_baseline_score,
                    frame_id=str(frame))
            except Exception:
                pass
        if cached.get("target") is not None:
            self.target = cached.get("target")
            self._innings_fallback = 2
        if cached.get("batting_team"):
            self.batting_team = cached.get("batting_team")
        # Mirror active batters / current bowler from the cache. Fields
        # not present in the cache stay None and get filled by the first
        # WARM frame's normal update path.
        _bc = (cached.get("batting_card") or {})
        _active = [n for n, c in _bc.items() if c.get("status") == "batting"]
        if len(_active) >= 1:
            self.bat1_name = _active[0]
        if len(_active) >= 2:
            self.bat2_name = _active[1]
        _striker = cached.get("striker")
        _non = cached.get("non")
        if _striker and _non:
            self._set_slot_pair(_striker, _non, source="hot_resume")
        elif _active:
            # Fall back to the active-pair ordering if striker/non
            # weren't cached (older cache shapes).
            self._set_slot_pair(
                _active[0], _active[1] if len(_active) > 1 else None,
                source="hot_resume")
        if cached.get("current_bowler"):
            self.bowler_name = cached.get("current_bowler")
        self.mode = "WARM"
        self.cold_candidate = None
        self.cold_candidate_streak = 0
        self.cold_frames = 0
        log.info(
            f"[SM] HOT-RESUME from cache  "
            f"{self.score}/{self.wickets} ({self.overs}) frame=F{frame}")

    def _accept_initial(self, card: dict, frame: FrameInput) -> None:
        """Adopt a cold-start scorecard into WARM state.

        Called for both:
          (a) FRESH initialisation (pipeline boot — `self.score is None`)
          (b) RE-ENTRY into WARM after stale recovery
              (`self.score is not None` — we had a prior warm state).

        On RE-ENTRY this method MUST preserve historical fields the
        broadcast doesn't re-derive: confirmed FOW entries, observed
        balls in `this_over`, the running partnership.  Wiping them
        causes the symptoms we saw on 2026-04-17:
          - this-over `[., ?, ?, ?, 1]` (observed dot lost on re-init)
          - partnership=1/1 mid-over (running counter zeroed)
          - duplicate Buttler@95/9.1 entries in FOW (placeholder list
            re-built, then a later wicket event appended again)
        """
        if self.mode == "COLD_START":
            self._cold_pipeline_frames = 0
            self._cold_last_viable = None

        is_reentry = self.score is not None

        _prior_overs_for_gap = self.overs
        self.score = card.get("score")
        self.wickets = card.get("wickets")
        self.overs = card.get("overs")
        self._track_overs_advance(
            _prior_overs_for_gap, self.overs,
            getattr(frame, "frame_id", 0))
        # A1 prerequisite (2026-05-14): seed _event_baseline_score at
        # COLD_START → WARM exit.  Trace evidence (F27 in DC-vs-KKR
        # 2026-05-14 16:48 watch) showed the very first WARM event after
        # cold-start computing d_score=0 for a real FOUR — root cause
        # was _event_baseline_score being None at that point, so the
        # 4dbd0e3 fix fell back to _self_score which had already been
        # advanced to 4 by the DIRECT path before _handle_warm ran.
        # Seeding here anchors the first delta to the cold-start
        # accepted score (0 for fresh innings, accumulated for
        # mid-innings recovery).  Symmetric with caedd4c (innings-2)
        # and the hot_resume_from_cache seed above.
        try:
            self._event_baseline_score = (
                int(self.score) if self.score is not None else 0)
        except (TypeError, ValueError):
            self._event_baseline_score = 0
        if _trace is not None:
            try:
                _trace.get_recorder().record(
                    tag="EVENT-BASELINE-SEEDED-WARM-INITIAL",
                    score=self._event_baseline_score,
                    is_reentry=bool(is_reentry),
                    frame_id=str(self._current_frame))
            except Exception:
                pass

        # Dismissed-batter resurrection guard (2026-04-23, WS-PROJECTION
        # investigation).  The same scrub already runs in
        # `_update_batters` (warm path) but was missing here in the
        # re-init path.  Live probe of MI-vs-CSK inn1 (F59 Sharma
        # wicket → F162+ WS-PROJECTION-GAP) showed SM.non stuck
        # on 'Kartik Sharma' for 170+ frames after her dismissal: a
        # stale broadcast strip still listed "Kartik 18(19)" post-
        # wicket, SM re-entered COLD_START, _init_from_card accepted
        # bat2_name=Sharma from that read, and lines 655-656 propagated
        # her into self.non.  Payload override wrote Sharma,
        # WS-HYGIENE stripped her as out → UI lost non.  Drop
        # any card batter the scoreboard already marks dismissed before
        # we assign to bat1/bat2.
        if self.scoreboard is not None:
            for _key in ("bat1_name", "bat2_name"):
                _nm = card.get(_key)
                if not _nm:
                    continue
                _sc_card = (self.scoreboard.batting_card or {}).get(_nm)
                if _sc_card and _sc_card.get("status") == "out":
                    log.warn(
                        f"[SM] init: dropping {_key}='{_nm}' — "
                        f"scoreboard shows status=out (stale strip "
                        f"read of dismissed batter resurrected in "
                        f"re-init)")
                    card[_key] = None
                    card.pop(_key.replace("_name", "_runs"), None)
                    card.pop(_key.replace("_name", "_balls"), None)

        self.bat1_name = card.get("bat1_name")
        _prev_b2_accept = self.bat2_name
        self.bat2_name = card.get("bat2_name")

        self.bowler_name = card.get("bowler_name")

        # Striker identification (W3–W6 → Lever 1 `_set_slot_pair`).
        # F1 fix (2026-05-20, B-ε): consume the canonical
        # `broadcast_striker` field (populated from Scout's *-marker
        # detection via test_pipeline.py:1783 + :13823 + score_manager.py:1616)
        # instead of the legacy `broadcast` field that no producer
        # writes. Apply Priority 3's first-name match (skip when
        # batters share first name) for symmetric-ambiguity defense.
        # Gate on self.striker is None so re-entry preserves an
        # already-locked striker. See §11 of
        # cold_start_initial_striker_design.md.
        if self.striker is None:
            _strip_bc = card.get("broadcast_striker")
            if _strip_bc:
                ind = _strip_bc.lower().strip()
                _b1_first = ((self.bat1_name or "").split() or [""])[0].lower()
                _b2_first = ((self.bat2_name or "").split() or [""])[0].lower()
                if _b1_first and _b2_first and _b1_first != _b2_first:
                    if _b1_first in ind and _b2_first not in ind:
                        self._set_slot_pair(
                            self.bat1_name, self.bat2_name,
                            source="init_from_card.striker")
                    elif _b2_first in ind and _b1_first not in ind:
                        self._set_slot_pair(
                            self.bat2_name, self.bat1_name,
                            source="init_from_card.non")
                    else:
                        self._set_slot_pair(
                            self.bat1_name, self.bat2_name,
                            source="init_from_card.combined_ambiguous")
                else:
                    self._set_slot_pair(
                        self.bat1_name, self.bat2_name,
                        source="init_from_card.combined_same_first")
            else:
                self._set_slot_pair(
                    self.bat1_name, self.bat2_name,
                    source="cold_start_no_indicator")

        if self.bat2_name != _prev_b2_accept:
            self._w8_guard_fired.clear()

        # Match context
        self.batting_team = frame.broadcast_team
        self.target = frame.broadcast_target
        self.venue = frame.broadcast_venue
        self.match_info = frame.broadcast_match_info
        if self.target:
            self._innings_fallback = 2

        # ── History-preserving init ───────────────────────────────────
        target_wkts = self.wickets or 0
        _fl = self._fow_writable()
        if not is_reentry:
            # Fresh pipeline boot — start with placeholder rows for
            # any wickets that fell before we joined.  Issue 4 fix:
            # use the Scoreboard factory so placeholders carry
            # `_unwitnessed: True` (UI can then render them honestly).
            _fl.clear()
            _fl.extend(
                self._make_fow_placeholder(_i + 1)
                for _i in range(target_wkts)
            )
        else:
            # Re-entry: never shrink, never overwrite.  Pad with
            # placeholders only if the broadcast says more wickets
            # have fallen since we last had warm state.
            while len(_fl) < target_wkts:
                _fl.append(
                    self._make_fow_placeholder(len(_fl) + 1))
            if len(_fl) > target_wkts:
                # Confirmed history outranks a wickets read that
                # shrank.  Preserve all entries; the diff layer will
                # reject the regression on the next frame.
                log.warn(
                    f"[SM] re-WARM: card wickets {target_wkts} < "
                    f"confirmed FOW history {len(_fl)} — "
                    f"keeping history intact")

        mid_innings_boot = (
            not is_reentry
            and ((self.wickets or 0) > 0
                 or float(self.overs or 0.0) >= 1.0))

        if not is_reentry:
            # Fresh init — seed this_over only for true early joins. A
            # mid-innings recovery waits for observed post-recovery balls.
            if self.overs and not mid_innings_boot:
                balls = round((self.overs % 1) * 10)
                if balls > 0:
                    if _infer_gap_tokens is not None:
                        self.this_over = list(
                            _infer_gap_tokens(
                                balls,
                                int(self.score or 0),
                                int(self.wickets or 0)))
                    else:
                        self.this_over = ["?"] * balls
                    self.this_over_src = ["bcast_synth"] * balls
        else:
            # Re-entry: keep observed balls (`obs` source) intact.
            # Pad with placeholders only if the new ball count exceeds
            # what we had; never truncate (truncation would lose the
            # observation that was already recorded).
            if self.overs:
                balls = round((self.overs % 1) * 10)
                while len(self.this_over) < balls:
                    self.this_over.append("?")
                    self.this_over_src.append("bcast")

        if not is_reentry:
            self.partnership_runs = 0
            self.partnership_balls = 0
            self.partnership_known = not mid_innings_boot
        # On re-entry, leave partnership counters as they were.  We
        # don't know the true value but the running total we had is a
        # far better estimate than zero, and subsequent ball events
        # will accumulate forward correctly.

        if card.get("speed_kph"):
            self.last_speed = card["speed_kph"]
            self.last_speed_at_over = self.overs

        self._recompute()

    # ------------------------------------------------------------------
    # Warm running
    # ------------------------------------------------------------------

    def _handle_warm(self, card: dict, frame: FrameInput) -> dict | None:
        # B1.3 §2.6/§2.7: pre-archive retry + deadline evaluation.
        # Runs every frame when an over-archive is deferred. Drains if
        # attribution arrived; force-flushes at the §2.7 soft/hard
        # deadlines (with PENDING_OVERRIDE extension between them).
        if self._over_archive_pending is not None:
            self._attempt_pending_archive_drain(
                card.get("overs") if isinstance(card, dict) else None)
        self._try_resolve_pending(frame)

        if card.get("score") is not None:
            try: card["score"] = int(card["score"])
            except (TypeError, ValueError): card["score"] = 0
        if card.get("wickets") is not None:
            try: card["wickets"] = int(card["wickets"])
            except (TypeError, ValueError): card["wickets"] = 0
        if card.get("overs") is not None:
            try: card["overs"] = float(card["overs"])
            except (TypeError, ValueError): card["overs"] = 0.0
        if isinstance(self.score, str):
            try: self.score = int(self.score)
            except ValueError: self.score = 0
        if isinstance(self.wickets, str):
            try: self.wickets = int(self.wickets)
            except ValueError: self.wickets = 0
        if isinstance(self.overs, str):
            try: self.overs = float(self.overs)
            except ValueError: self.overs = 0.0

        if self._detect_innings_change(card, frame):
            return self._build_payload()

        def _val(card_v, self_v):
            """Resolve value: prefer card, fall back to state, then 0."""
            if card_v is not None:
                return card_v
            if self_v is not None:
                return self_v
            return 0

        c_score = _val(card.get("score"), self.score)
        c_wickets = _val(card.get("wickets"), self.wickets)
        new_overs = _val(card.get("overs"), self.overs)
        old_overs = self.overs if self.overs is not None else 0

        try: c_score = int(c_score)
        except (TypeError, ValueError): c_score = 0
        try: c_wickets = int(c_wickets)
        except (TypeError, ValueError): c_wickets = 0
        try: new_overs = float(new_overs)
        except (TypeError, ValueError): new_overs = 0.0
        try: old_overs = float(old_overs)
        except (TypeError, ValueError): old_overs = 0.0

        _self_score = self.score if self.score is not None else 0
        _self_wickets = self.wickets if self.wickets is not None else 0
        try: _self_score = int(_self_score)
        except (TypeError, ValueError): _self_score = 0
        try: _self_wickets = int(_self_wickets)
        except (TypeError, ValueError): _self_wickets = 0
        # A1 prerequisite (2026-05-14): persistent baseline across
        # _handle_warm calls.  Trace evidence (F19 in DC-vs-KKR
        # 2026-05-14 16:12 watch) showed d_score computing as 0 even
        # though scoreboard.score advanced 0→4 in the same frame —
        # SM=DOT BED=FOUR MISMATCH.  Audit (see commit message) ruled
        # out direct scoreboard writes outside SM, so the failure mode
        # is subtler than "scoreboard pre-advanced", but the symptom
        # is consistent: c_score - _self_score returns 0.  Defending
        # by anchoring d_score to the score recorded at the *last
        # successful event commit* (``_event_baseline_score``) makes
        # the delta correct regardless of when scoreboard.score gets
        # written within the frame.  Lazy-init via getattr so old SM
        # init sites and replay harnesses don't need to be touched.
        _ev_baseline = getattr(self, "_event_baseline_score", None)
        if _ev_baseline is None:
            _baseline_score = _self_score
            _baseline_source = "self_score"
        else:
            _baseline_score = int(_ev_baseline)
            _baseline_source = "prev_event"
        d_score = c_score - _baseline_score
        d_wickets = c_wickets - _self_wickets
        d_overs = round(new_overs - old_overs, 2)

        # Overs-jump implausibility guard (2026-05-19).
        # Live broadcasts intermittently overlay graphics (sponsor
        # banners, standings ribbons, post-over stats, tournament
        # totals) that corrupt single STRIP fields. parse_strip then
        # emits a structurally-valid-but-wrong overs value: e.g.
        # frame 276 of watch_20260519_121701 had VISIBLE_TEXT
        # "DC 43-0 8 4.1 ..." (where the "8" is a separate stat)
        # but the STRIP regex glued "8" + "4.1" → "(8.4)". SM with
        # no upstream guard accepted overs=8.4 as a legitimate
        # progression from 3.2 (Δ=5.2 overs = 32 legal balls in one
        # frame) and fabricated a multi-ball gap to fill it,
        # corrupting downstream bowling/batting credit and the
        # over_history archive. Bisect against the L2-Slim
        # captured-Scout-replay harness against 16 commits back to
        # the effective branch root all showed the ORPHAN at
        # (43, 0, 8.4) — this is structural, not a regression.
        #
        # Guard: reject the frame when both dimensions of progress
        # are simultaneously implausible AND we don't have 3-frame
        # consensus on the new value. Cold-start exempt — legitimate
        # cold-start exits jump from 0.0 → wherever the broadcast
        # is showing.
        # Threshold in LEGAL BALLS (semantic), not raw float overs:
        # X.5 → X+1.0 looks like a 0.5 float jump but is only 1
        # legal ball. Converting overs (O.B notation) to integer
        # ball counts before differencing gives a meaningful delta.
        _BALLS_JUMP_TOLERANCE = 3   # ~3 legal balls between scout frames
        _OVERS_JUMP_CONSENSUS_FRAMES = 3
        _SCORE_JUMP_THRESHOLD = 20

        def _overs_to_balls(o: float) -> int:
            try:
                fo = float(o)
            except (TypeError, ValueError):
                return 0
            whole = int(fo)
            frac = int(round((fo - whole) * 10))
            return whole * 6 + frac

        _new_balls_total = _overs_to_balls(new_overs)
        _old_balls_total = _overs_to_balls(old_overs)
        _d_balls = _new_balls_total - _old_balls_total

        # Two-dimension OR check: either an implausible ball jump
        # OR an implausible score jump triggers the guard. The
        # consensus accumulator handles transient false positives —
        # legitimate progressions confirmed by 3 frames at the same
        # value pass through. Trace evidence: frame 276 of the
        # captured-Scout replay shows _d_balls=32 with d_score=10,
        # so a strict AND would have missed it (d_score below 20).
        # OR with consensus is robust to both signatures of the
        # graphic-overlay misread class.
        if (self.mode == "WARM"
                and self.overs is not None
                and (_d_balls > _BALLS_JUMP_TOLERANCE
                     or d_score > _SCORE_JUMP_THRESHOLD)):
            proposed = (new_overs, c_score)
            cur_candidate = getattr(
                self, "_overs_jump_candidate", None)
            cur_streak = getattr(self, "_overs_jump_streak", 0)
            if cur_candidate == proposed:
                cur_streak += 1
            else:
                cur_streak = 1
            self._overs_jump_candidate = proposed
            self._overs_jump_streak = cur_streak
            if cur_streak < _OVERS_JUMP_CONSENSUS_FRAMES:
                _delta_balls = _d_balls
                if _trace is not None:
                    try:
                        _trace.get_recorder().record(
                            tag="OVERS-JUMP-IMPLAUSIBLE-REJECTED",
                            proposed_overs=float(new_overs),
                            current_overs=float(old_overs),
                            delta_overs=float(d_overs),
                            delta_balls=_delta_balls,
                            proposed_score=int(c_score),
                            current_score=int(_self_score),
                            delta_score=int(d_score),
                            streak=cur_streak,
                            consensus_required=(
                                _OVERS_JUMP_CONSENSUS_FRAMES),
                            source_frame_id=getattr(
                                frame, "frame_id", None))
                    except Exception:
                        pass
                log.info(
                    f"  [OVERS-JUMP-IMPLAUSIBLE-REJECTED] "
                    f"proposed_overs={new_overs} "
                    f"current_overs={old_overs} "
                    f"d_overs={d_overs} "
                    f"delta_balls={_delta_balls} "
                    f"proposed_score={c_score} "
                    f"current_score={_self_score} "
                    f"d_score={d_score} "
                    f"streak={cur_streak}/"
                    f"{_OVERS_JUMP_CONSENSUS_FRAMES} — "
                    f"keeping prior state")
                log.info(
                    f"[GAP-AT-REJECTION] Δballs={_delta_balls} "
                    f"proposed_overs={new_overs} "
                    f"current_overs={old_overs} "
                    f"proposed_score={c_score} "
                    f"current_score={_self_score} "
                    f"d_score={d_score} streak={cur_streak}/"
                    f"{_OVERS_JUMP_CONSENSUS_FRAMES} "
                    f"source=warm_consensus")
                if _SmOutcome is not None:
                    _ledger_record(
                        getattr(frame, "frame_id", None),
                        _SmOutcome.REJECTED_WARM_CONSENSUS,
                        payload={
                            "delta_balls": int(_delta_balls),
                            "proposed_overs": float(new_overs),
                            "current_overs": float(old_overs),
                            "source": "warm_consensus",
                            "streak": cur_streak,
                        })
                self._update_supplements(card, frame)
                self.frames_since_event += 1
                return None
            self._overs_jump_candidate = None
            self._overs_jump_streak = 0
        elif getattr(self, "_overs_jump_candidate", None) is not None:
            self._overs_jump_candidate = None
            self._overs_jump_streak = 0


        if (_trace is not None
                and _baseline_source == "prev_event"
                and d_score != c_score - _self_score):
            try:
                _trace.get_recorder().record(
                    tag="SM-EVENT-DELTA-FROM-PREV",
                    prev_event_score=int(_baseline_score),
                    self_score=int(_self_score),
                    card_score=int(c_score),
                    d_score=int(d_score),
                    d_score_naive=int(c_score - _self_score),
                    frame_id=str(self._current_frame))
            except Exception:
                pass

        # DC-vs-CSK Fix 4: 2-frame consensus gate for ambiguous score
        # commits. Predictable monotonic ball-event increments
        # (+1/+2/+3/+4/+6) commit on first read; jumps > +6 OR any
        # change without overs/wickets advance require a second frame
        # echoing the same score. A different second-frame proposal
        # discards the cache and starts fresh.
        _trusted_first_read_deltas = {0, 1, 2, 3, 4, 6}
        _is_predictable = (
            d_score in _trusted_first_read_deltas
            and (d_overs > 0 or d_wickets > 0
                 or d_score == 0))
        _huge_jump = d_score > 6
        if d_score != 0 and (not _is_predictable or _huge_jump):
            if (self._pending_score is not None
                    and self._pending_score == c_score):
                self._pending_score = None
                self._pending_score_frame = None
            else:
                if (self._pending_score is not None
                        and self._pending_score != c_score):
                    log.info(
                        f"  [SCORE-CONSENSUS] discarding pending "
                        f"{self._pending_score} after disagreeing "
                        f"second read {c_score} — restarting consensus")
                self._pending_score = c_score
                self._pending_score_frame = self._current_frame
                log.info(
                    f"  [SCORE-CONSENSUS] caching score proposal "
                    f"{c_score} (delta={d_score:+d}, "
                    f"jump>6={_huge_jump}); awaiting second frame")
                self._update_supplements(card, frame)
                self.frames_since_event += 1
                return None

        # Clear deferred flag when overs/wickets advance — the full score gap
        # is already captured in d_score since SM never updated during deferral.
        if self._deferred_score > 0 and (d_overs > 0 or d_wickets > 0):
            self._deferred_score = 0
            self._deferred_frames = 0

        # Diff validation (cricket physics)
        if d_score < 0:
            self._deferred_score = 0
            return None
        if d_wickets < 0:
            return None
        if d_overs < 0:
            # D5 large-gap fast-track: a regression of >3 overs is almost
            # never a transient glitch — it's a stuck tracker disagreeing
            # with the live broadcast. Force re-COLD_START on the FIRST
            # such frame instead of waiting for the 2-frame deferral.
            if (old_overs is not None and new_overs is not None
                    and (old_overs - new_overs)
                    > self._LARGE_OVERS_REGRESSION_GAP):
                log.info(
                    f"[SM] Overs LARGE regression ({old_overs}→"
                    f"{new_overs}, gap {old_overs - new_overs:.1f}) — "
                    f"force re-COLD_START (stuck-tracker recovery)")
                self.full_reset(reason="stuck_tracker_large_overs_regression")
                self._regression_streak = 0
                return None
            # D5 streak detector: many small rejected regressions also
            # indicate a stuck tracker, even when no individual frame
            # crosses the large-gap threshold.
            self._regression_streak += 1
            if self._regression_streak >= self._REGRESSION_STREAK_THRESHOLD:
                log.info(
                    f"[SM] Regression streak {self._regression_streak} "
                    f"— force re-COLD_START (persistent stuck-tracker)")
                self.full_reset(reason="stuck_tracker_regression_streak")
                self._regression_streak = 0
                return None
            # Require N consecutive regression frames before re-entering
            # COLD_START.  A single FRAME_POISONED scout read (or a
            # _validate_overs correction triggered by a stale this_over
            # ribbon) can flip ext_overs backwards for one frame, and the
            # pre-consensus behaviour dropped the VERY NEXT real ball
            # event into cold-start (lost forever once the streak re-
            # warmed).  With consensus, a genuine regression (innings
            # reset, DRS overs revert) still propagates after N frames;
            # a one-off glitch is transparently ignored.
            if (self._overs_regress_from is None
                    or old_overs > self._overs_regress_from):
                self._overs_regress_from = old_overs
            self._overs_regress_streak += 1
            if self._overs_regress_streak < self._OVERS_REGRESS_THRESHOLD:
                log.info(
                    f"[SM] Overs regression ({old_overs}→{new_overs}) "
                    f"— deferred "
                    f"({self._overs_regress_streak}/"
                    f"{self._OVERS_REGRESS_THRESHOLD}), ignoring frame")
                self._update_supplements(card, frame)
                self.frames_since_event += 1
                return None
            log.info(
                f"[SM] Overs regression ({self._overs_regress_from}→"
                f"{new_overs}) confirmed after "
                f"{self._overs_regress_streak} frames — "
                f"re-entering COLD_START")
            self._last_warm_state = self._snapshot()
            self.mode = "COLD_START"
            self.cold_candidate = None
            self.cold_candidate_streak = 0
            self.cold_frames = 0
            self._cold_pipeline_frames = 0
            self._cold_last_viable = None
            self._stale_reject_count = 0
            self._deferred_score = 0
            self._overs_regress_streak = 0
            self._overs_regress_from = None
            self._regression_streak = 0
            return None

        # Forward progress (or equality) — clear any pending regression
        # streak so a transient glitch doesn't carry across frames.
        if self._overs_regress_streak > 0:
            log.info(
                f"[SM] Overs-regression streak cleared "
                f"({self._overs_regress_streak} frame(s) of "
                f"{self._overs_regress_from}→? were transient) — "
                f"back in sync at {new_overs}")
            self._overs_regress_streak = 0
            self._overs_regress_from = None
        self._regression_streak = 0
        if d_wickets > 2:
            return None

        # Use ball-count delta (base-6 aware) for multi-ball detection
        d_balls = (self._overs_to_balls(new_overs)
                   - self._overs_to_balls(old_overs))

        # ── Cricket-rules diff validation ──────────────────────────────
        # Replaces the older heuristic stack (per-ball ceiling, chase
        # ceiling, absolute T20 ceiling, single-ball d_score>7).  Every
        # diff we accept must satisfy:
        #   - new state passes absolute + chase ceilings, AND
        #   - the diff itself satisfies cricket physics
        #     (multi-ball ceilings, no negative deltas, etc.)
        # Striker / bowler deltas are passed as None for now: the
        # validator falls back to invariants-only and lets _infer_event
        # classify the event from team-level deltas.  This is the
        # "Option 1" partial-data path from the spec.
        cr_diff = Diff(
            d_score=d_score, d_balts=d_balls, d_wkt=d_wickets,
            d_str_runs=None, d_str_balls=None,
            d_bwl_runs=None, d_bwl_wkt=None, d_bwl_balls=None)
        cr_result = validate_diff(
            cr_diff,
            new_score=c_score, new_wickets=c_wickets, new_overs=new_overs,
            target=self.target, innings=self.innings)
        if not cr_result.ok:
            log.warn(
                f"[SM] REJECT (cricket_rules: {cr_result.reject_reason})  "
                f"prev={self.score}/{self.wickets} ({old_overs}) → "
                f"card={c_score}/{c_wickets} ({new_overs})")
            self._stale_reject_count += 1
            if self._stale_reject_count > 10:
                log.info("[SM] Too many consecutive rejections — "
                         "re-entering COLD_START to re-calibrate")
                self._last_warm_state = self._snapshot()
                self.mode = "COLD_START"
                self.cold_candidate = None
                self.cold_candidate_streak = 0
                self.cold_frames = 0
                self._cold_pipeline_frames = 0
                self._cold_last_viable = None
                self._stale_reject_count = 0
            return None

        self._stale_reject_count = 0

        # Score-only change with no overs/wicket movement and no broadcast
        # confirmation: defer rather than firing a potentially wrong EXTRA.
        # The score may have been updated from a graphic overlay before overs
        # caught up.  If broadcast_extra is present on this frame, emit
        # immediately — no deferral needed.
        if (d_score > 0 and d_overs == 0 and d_wickets == 0
                and not card.get("broadcast_extra")
                and self._deferred_frames < 2):
            self._deferred_score += d_score
            self._deferred_frames += 1
            self._update_supplements(card, frame)
            self.frames_since_event += 1
            log.info(f"[SM] Deferring score +{d_score} (overs stuck at "
                     f"{old_overs}, total deferred={self._deferred_score})")
            return None

        # Resolve deferred via broadcast_extra confirmation or timeout
        if (self._deferred_score > 0 and d_overs == 0 and d_wickets == 0
                and (card.get("broadcast_extra")
                     or self._deferred_frames >= 2)):
            self._extras_persistent_lag = self._deferred_frames >= 2
            self._deferred_score = 0
            self._deferred_frames = 0
        else:
            self._extras_persistent_lag = False

        # No change = steady state — still adopt new data (batter names, etc.)
        if d_score == 0 and d_wickets == 0 and d_overs == 0:
            # Snapshot batter prev values BEFORE _update_batters mutates
            # them, so _identify_and_set can compute deltas
            # against the previous frame.
            _pb1r, _pb1b = self.bat1_runs, self.bat1_balls
            _pb2r, _pb2b = self.bat2_runs, self.bat2_balls
            self._update_batters(card)
            self._identify_and_set(
                card, frame, _pb1r, _pb1b, _pb2r, _pb2b)
            self._update_supplements(card, frame)
            self.frames_since_event += 1
            return None

        prev = self._snapshot()
        # Capture batter prevs separately — `prev` here is the SM-state
        # snapshot used by event inference, which keys by bat1/bat2 slot.
        # Striker resolution needs prev-by-name to survive a batter swap
        # in _accept_update; pull the same numbers via the snapshot.
        _pb1r = prev.get("bat1_runs")
        _pb1b = prev.get("bat1_balls")
        _pb2r = prev.get("bat2_runs")
        _pb2b = prev.get("bat2_balls")
        fi = self._current_frame
        self._accept_update(card, fi)
        # Resolve striker AFTER _accept_update so any batter rotation
        # is reflected in self.bat1_name/bat2_name; use saved prevs.
        self._identify_and_set(
            card, frame, _pb1r, _pb1b, _pb2r, _pb2b)

        # Dispatch-loop redesign scoping (2026-05-20): shadow-compare the
        # inline _apply_multi_ball_gap prediction against the actual
        # _decompose_multi_ball + dispatch loop output. Pure observation
        # — no state mutation from the inline path. Emits one
        # DISPATCH-LOOP-SHADOW-COMPARISON trace per multi-ball gap event.
        _mb_shadow: dict | None = None
        try:
            _shadow_d_balls = (
                self._overs_to_balls(card.get("overs") or self.overs or 0)
                - self._overs_to_balls(prev.get("overs") or 0))
        except Exception:
            _shadow_d_balls = 0
        if _shadow_d_balls > 1 and _trace is not None:
            try:
                _mb_shadow = {
                    "d_balls": int(_shadow_d_balls),
                    "before": self._capture_multi_ball_shadow_state(),
                    "predicted": self._apply_multi_ball_gap(
                        d_score=int(d_score),
                        d_wickets=int(d_wickets),
                        d_balls=int(_shadow_d_balls),
                        striker=self.striker,
                        non=self.non,
                        bowler_name=self.bowler_name),
                }
            except Exception:
                _mb_shadow = None

        inferred = self._infer_event(d_score, d_wickets, d_overs, prev, card,
                                     frame)

        events: list[dict] = []
        if inferred is None:
            events = []
        elif isinstance(inferred, list):
            events = inferred
        else:
            events = [inferred]

        base_balls = self._overs_to_balls(prev.get("overs") or 0)
        for i, evt in enumerate(events):
            if evt.get("type") == ABSORBED_LEGAL:
                tb_after = base_balls + i + 1
                evt["over"] = str(self._balls_to_overs(tb_after))
                sp_o = self._balls_to_overs(base_balls + i)
                sc_o = self._balls_to_overs(base_balls + i + 1)
                self._apply_absorbed_event(
                    evt, {"overs": sp_o}, {"overs": sc_o}, frame)
            else:
                self._apply_event(evt, prev, card, frame)

        if _mb_shadow is not None:
            try:
                _after = self._capture_multi_ball_shadow_state()
                _actual = self._compute_multi_ball_shadow_actual_delta(
                    _mb_shadow["before"], _after)
                _divergent = self._compare_multi_ball_shadow(
                    _mb_shadow["predicted"], _actual)
                _trace.get_recorder().record(
                    tag="DISPATCH-LOOP-SHADOW-COMPARISON",
                    d_balls=_mb_shadow["d_balls"],
                    d_score=int(d_score),
                    d_wickets=int(d_wickets),
                    bowler_name=_mb_shadow["predicted"].get("bowler_name"),
                    striker_in=_mb_shadow["predicted"].get("striker_in"),
                    non_in=_mb_shadow["predicted"].get("non_in"),
                    tokens=_mb_shadow["predicted"].get("tokens"),
                    predicted=_mb_shadow["predicted"],
                    actual=_actual,
                    divergence_fields=_divergent,
                    flag_on=SM_INLINE_MULTI_BALL,
                    frame_id=str(self._current_frame))
            except Exception:
                pass

        if events:
            self.last_event = events[-1]
            self.frames_since_event = 0
            # A1 prerequisite: capture the score at successful event
            # commit as the baseline for the next frame's d_score.
            try:
                self._event_baseline_score = int(c_score)
            except (TypeError, ValueError):
                self._event_baseline_score = None
            for evt in events:
                log.info(f"[SM] {evt['type']}  "
                         f"{self.score}/{self.wickets} ({self.overs})  "
                         f"striker={evt.get('striker')}")

        self._recompute()
        return self._build_payload(events[-1] if events else None,
                                   ball_events=events)

    # ------------------------------------------------------------------
    # Innings transition
    # ------------------------------------------------------------------

    def force_cold_start_recalibration(self, reason: str = "") -> None:
        """Drop the current WARM lock and re-enter COLD_START.

        Called externally when the pipeline detects that the WARM
        baseline is stuck (e.g. many consecutive tracker-POISON blocks
        with a consistent alternative reading).  The normal stale-
        rejection recovery at line ~710 only fires for cricket-rules
        rejections inside `on_frame`, which never trigger when the
        pipeline's own POISON guard has already stripped the frame
        before it reached us.  This method is the escape hatch for
        that scenario.

        Preserves innings, target, and innings_history so the match
        context isn't lost.  All per-innings counters, the warm
        snapshot, and the cold-start candidate are cleared so the
        next good read can seed a fresh candidate.
        """
        prev_state = (f"{self.score}/{self.wickets} ({self.overs}) "
                      f"mode={self.mode}")
        self._last_warm_state = self._snapshot() if self.score is not None else None
        self.mode = "COLD_START"
        self.cold_candidate = None
        self.cold_candidate_streak = 0
        self.cold_frames = 0
        self._cold_pipeline_frames = 0
        self._cold_last_viable = None
        self._stale_reject_count = 0
        self._deferred_score = 0
        self._deferred_frames = 0
        log.info(f"[SM] FORCE_COLD_START_RECALIBRATION: was {prev_state} "
                 f"→ COLD_START (reason={reason or 'external'})")

    def _innings_history_archive_entry(self) -> dict:
        """Build one innings archive row (WS-shaped cards; deep-copied leaves).

        Used at both innings-transition append sites so structure stays
        identical. Mutable nested values are ``copy.deepcopy``'d so innings 2
        mutations cannot corrupt the archived innings 1 snapshot.
        """
        sb = self.scoreboard
        state: dict = {}
        if sb is not None and sb._inn:
            state = sb.get_live_state() or {}

        striker = state.get("striker") or self.striker
        cur_bowler = state.get("current_bowler") or self.bowler_name
        overs_for_reconcile = state.get("overs")

        batting_team = self.batting_team
        bowling_team = None
        if sb is not None:
            bowling_team = getattr(sb, "bowling_team", None)

        batting_card: list[dict] = []
        bowling_card_raw: list[dict] = []
        if sb is not None:
            _bc = sb.batting_card or {}
            batting_card = [
                {
                    "name": n,
                    "status": c.get("status"),
                    "runs": c.get("runs"),
                    "balls": c.get("balls"),
                    "fours": c.get("fours") or 0,
                    "sixes": c.get("sixes") or 0,
                    "sr": (round((c["runs"] / c["balls"]) * 100, 1)
                           if c.get("balls") and c.get("runs") is not None
                           else 0),
                    "dismissal": c.get("dismissal"),
                    "is_striker": n == striker,
                    "position": c.get("position"),
                    "batting_style": c.get("batting_style", "unknown"),
                    "bowling_style": c.get("bowling_style", "unknown"),
                }
                for n, c in _bc.items()
                if c.get("status") in ("batting", "out")
                or (c.get("runs") is not None
                    and (c.get("runs") or 0) > 0)
            ]
            bowling_card_raw = [
                {
                    "name": n,
                    "overs": c.get("overs"),
                    "maidens": c.get("maidens") or 0,
                    "runs": c.get("runs"),
                    "wickets": c.get("wickets"),
                    "economy": (
                        round(c["runs"] / max(float(c["overs"] or 0), 0.1), 1)
                        if c.get("overs") and c.get("runs") is not None
                        else None),
                    "is_current": n == cur_bowler,
                    "batting_style": c.get("batting_style", "unknown"),
                    "bowling_style": c.get("bowling_style", "unknown"),
                }
                for n, c in (sb.bowling_card or {}).items()
                if (n == cur_bowler
                    or (c.get("overs") is not None
                        and float(c.get("overs") or 0) > 0))
            ]

        bowling_card = bowling_card_raw
        if sb is not None:
            bowling_card = _reconcile_bowler_overs(
                bowling_card_raw,
                team_overs=overs_for_reconcile,
                current_bowler=cur_bowler,
            )

        _cur_pp = None
        if self.partnership_known:
            _batters = [x for x in (self.striker, self.non) if x]
            _cur_pp = {
                "runs": self.partnership_runs,
                "balls": self.partnership_balls,
                "batters": sorted(_batters),
                "ended": False,
            }
        partnerships = {"current": _cur_pp}

        fow_src = list(self._fow_writable())
        fall_of_wickets_vis: list[dict] = []
        for w in fow_src:
            batter = w.get("batter")
            is_placeholder = (
                batter is None
                or (isinstance(batter, str)
                    and batter.lower() in {"unknown", "?"}))
            unwitnessed = bool(w.get("_unwitnessed"))
            if unwitnessed and is_placeholder:
                fall_of_wickets_vis.append({
                    "wicket": w.get("wicket"),
                    "batter": "?",
                    "score": w.get("score"),
                    "overs": w.get("overs"),
                    "bowler": w.get("bowler") or "TBD",
                    "how": w.get("how") or "TBD",
                    "_unwitnessed": True,
                })
                continue
            fall_of_wickets_vis.append({
                "wicket": w.get("wicket"),
                "batter": batter,
                "score": w.get("score"),
                "overs": w.get("overs"),
                "bowler": w.get("bowler"),
                "how": w.get("how"),
                "_unwitnessed": unwitnessed,
            })

        return {
            "innings": self.innings,
            "score": self.score,
            "wickets": self.wickets,
            "overs": self.overs,
            "fow_list": copy.deepcopy(fow_src),
            "over_history": copy.deepcopy(self.over_history),
            "batting_team": batting_team,
            "bowling_team": bowling_team,
            "batting_card": copy.deepcopy(batting_card),
            "bowling_card": copy.deepcopy(bowling_card),
            "partnerships": copy.deepcopy(partnerships),
            "extras": copy.deepcopy(dict(self._extras_writable())),
            "fall_of_wickets": copy.deepcopy(fall_of_wickets_vis),
        }

    def _detect_innings_change(self, card: dict, frame: FrameInput) -> bool:
        """Detect innings change and re-enter COLD_START if confirmed."""
        if self.innings >= 2:
            return False

        changed = False
        reason = None

        # Target appearing for the first time
        if frame.broadcast_target and not self.target:
            changed = True
            reason = "target_appeared"

        # Batting team changed — require N-frame consensus to prevent
        # single-frame pre-match-graphic flips from triggering spurious
        # inn-2 transitions (D7 fix).
        #
        # Playing-teams sanity check (2026-05-19): only accept a
        # team-change signal if the proposed new team is one of the
        # two teams actually playing this match. Scout VLM can
        # hallucinate any 3-letter token as a team code (e.g. "LSG"
        # picked up from on-screen standings/sponsor in a DC vs KKR
        # broadcast), and the scoreboard's own team-lock already
        # rejects such writes — but this path read broadcast_team
        # directly, bypassing that rejection. Without the guard, three
        # consecutive misreads of any wrong team committed a spurious
        # team-change that triggered _reset_for_innings_2, which in
        # turn caused the NO-SCOREBOARD credit-skip cascade fixed at
        # 6881476 AND the SM-mode-revert latency that motivated the
        # reverted 48798b2 WS-gate workaround. Root cause closed here.
        _playing_teams: set[str] = set()
        if self.scoreboard is not None:
            _bt = getattr(self.scoreboard, "batting_team", None)
            _bowl = getattr(self.scoreboard, "bowling_team", None)
            if _bt:
                _playing_teams.add(_bt.upper())
            if _bowl:
                _playing_teams.add(_bowl.upper())
        if (frame.broadcast_team and self.batting_team
                and frame.broadcast_team.upper() != self.batting_team.upper()
                and (len(_playing_teams) < 2
                     or frame.broadcast_team.upper() in _playing_teams)):
            if frame.broadcast_team.upper() == (
                    self._team_change_candidate or "").upper():
                self._team_change_streak += 1
            else:
                self._team_change_candidate = frame.broadcast_team
                self._team_change_streak = 1
            if self._team_change_streak >= self.TEAM_CHANGE_CONSENSUS_FRAMES:
                changed = True
                reason = reason or "batting_team_changed"
                log.info(
                    f"[SM] team-change consensus committed: "
                    f"{self.batting_team} → {frame.broadcast_team} "
                    f"(streak {self._team_change_streak})")
                self._team_change_candidate = None
                self._team_change_streak = 0
            else:
                log.info(
                    f"[SM] team-change candidate {frame.broadcast_team} "
                    f"streak {self._team_change_streak}/"
                    f"{self.TEAM_CHANGE_CONSENSUS_FRAMES} — deferring "
                    f"inn-2 trigger")
                if _SmOutcome is not None:
                    _ledger_record(
                        getattr(frame, "frame_id", None),
                        _SmOutcome.REJECTED_TEAM_CHANGE_PENDING,
                        payload={
                            "proposed_team": frame.broadcast_team,
                            "current_team": self.batting_team,
                            "streak": self._team_change_streak,
                            "consensus_required": (
                                self.TEAM_CHANGE_CONSENSUS_FRAMES),
                        })
        elif (frame.broadcast_team and self.batting_team
                and frame.broadcast_team.upper()
                == self.batting_team.upper()):
            self._team_change_candidate = None
            self._team_change_streak = 0

        # Score dropping to 0 with wickets 0 while we had significant progress
        s = card.get("score", 0)
        w = card.get("wickets", 0)
        # Team-change corroboration required (2026-05-19). A 0/0
        # score read without a corresponding batting-team flip is
        # structurally indistinguishable from a sponsor-graphic /
        # skeleton-strip misread, not a real innings transition.
        # Surfaced by L2-Slim captured-Scout replay frame 215 of
        # watch_20260519_121701: STRIP "null 0-0 (3.2) | *NISSANKA
        # 0(2) | RAHUL 0(1) | NARINE 0-0 (1.2)" — a stats-overlay
        # whose null team prefix and fake per-batter stats hint
        # the row isn't a live scorecard read at all. Pre-fix, the
        # score_reset_from_progress branch accepted s=0, w=0 with
        # prior self.score > 20 regardless of team — triggering
        # _reset_for_innings_2 → full state wipe → cold-start
        # exit accepted next graphic misread as fresh anchor
        # (frame 276 ORPHAN at (43, 0, 8.4)).
        #
        # Architectural parity with 98a53cc, which gated the
        # batting_team_changed branch on playing-teams membership.
        # Real T20 innings-2 always flips batting team, so a
        # genuine score-reset transition is corroborated by the
        # already-gated team-change branch above; this branch
        # firing without that corroboration is the misread signal.
        _bcast_team = (
            (frame.broadcast_team or "").upper()
            if frame.broadcast_team else None)
        _cur_team = (
            (self.batting_team or "").upper()
            if self.batting_team else None)
        _team_changed = bool(
            _bcast_team and _cur_team
            and _bcast_team != _cur_team)
        if (s == 0 and w == 0
                and self.score is not None and self.score > 20
                and self.wickets is not None):
            if _team_changed:
                changed = True
                reason = reason or "score_reset_from_progress"
            else:
                if _trace is not None:
                    try:
                        _trace.get_recorder().record(
                            tag=("INN2-SCORE-RESET-TEAM-CHANGE-"
                                 "REQUIRED-REJECTED"),
                            prev_score=int(self.score),
                            cand_score=int(s),
                            prev_team=self.batting_team,
                            cand_team=frame.broadcast_team,
                            frame_id=getattr(
                                frame, "frame_id", None))
                    except Exception:
                        pass
                log.info(
                    f"  [INN2-SCORE-RESET-TEAM-CHANGE-"
                    f"REQUIRED-REJECTED] prev={self.score}/"
                    f"{self.wickets} prev_team={self.batting_team} "
                    f"cand=0/0 cand_team="
                    f"{frame.broadcast_team!r} — score reset "
                    f"without team change is skeleton/graphic "
                    f"misread, not innings transition")

        # Wickets regression: wickets only go up within an innings, so
        # any strict regression by >1 is structurally impossible without
        # either (a) an innings transition, or (b) OCR corruption. The
        # >1 tolerance filters single-frame misreads (e.g. 6→5) while
        # catching real resets (e.g. 6→0 or 6→1 on new innings).
        if (w is not None and self.wickets is not None
                and self.wickets >= 2 and w < self.wickets - 1):
            changed = True
            reason = reason or "wickets_regressed"

        if not changed:
            return False

        log.info(f"[INNINGS-TRANSITION-TELEMETRY] source=score_manager "
                 f"reason={reason} "
                 f"prev={self.score}/{self.wickets} ({self.overs}) "
                 f"prev_team={self.batting_team} "
                 f"cand={s}/{w} cand_team={frame.broadcast_team} "
                 f"cand_target={frame.broadcast_target}")
        log.info(f"[SM] INNINGS CHANGE detected  "
                 f"inn1: {self.score}/{self.wickets} ({self.overs})  "
                 f"team was={self.batting_team}, now={frame.broadcast_team}")

        # Archive innings 1 (full scorecard snapshot — §innings_history)
        self.innings_history.append(
            copy.deepcopy(self._innings_history_archive_entry()))

        # Reset state for innings 2 via canonical setter (Fix 16).
        self.set_innings_2(target=frame.broadcast_target,
                           batting_team=frame.broadcast_team,
                           reason=reason,
                           archive=False)

        return True

    def set_innings_2(self, target: int | None = None,
                      batting_team: str | None = None,
                      reason: str = "set_innings_2",
                      archive: bool = True,
                      warm_restart: bool = False) -> None:
        """Canonical innings-2 transition (Fix 16, 2026-04-26).

        Replaces the historical four-callsite divergence where
        only `_handle_innings_change` archived + reset cached
        scalars (`bat1_runs`, `bat2_runs`, `bowler_*`,
        `this_over`, `over_history`, `partnership_*`,
        `extras_*`, `fow_list`, `pending_extra`,
        `pending_wicket`, etc.).  The other three callsites
        (`_accept_update` line 707, `_update_misc` line 1171,
        `_update_supplements` line 1273) left those scalars
        intact, leaking innings-1 state into innings-2 displays.
        Now all four route through this method.

        `archive=True` archives the current innings into
        `innings_history` before the reset (use when the caller
        has not already done so).  `archive=False` skips the
        archive step (for `_handle_innings_change` which
        already archived).
        """
        if self.innings == 2:
            # Idempotent — innings-2 already active.
            return
        if archive:
            log.info(
                f"[SM-INNINGS-2-RESET] reason={reason}: "
                f"archiving innings 1 ({self.score}/"
                f"{self.wickets} ({self.overs}) "
                f"team={self.batting_team}) and resetting "
                f"all per-innings cached scalars.  target="
                f"{target} new_batting_team={batting_team}.")
            self.innings_history.append(
                copy.deepcopy(self._innings_history_archive_entry()))
        else:
            log.info(
                f"[SM-INNINGS-2-RESET] reason={reason}: "
                f"resetting all per-innings cached scalars "
                f"(archive already performed by caller).  "
                f"target={target} new_batting_team="
                f"{batting_team}.")
        # A2 prerequisite (2026-05-14): capture innings-1's final
        # _event_baseline_score before __init__ wipes other state, so
        # the EVENT-BASELINE-RESET-INNINGS-2 trace records the value
        # that would have leaked into innings-2's first d_score.
        _prev_event_baseline = getattr(
            self, "_event_baseline_score", None)
        shadow = self.shadow
        history = self.innings_history
        reset_frame = self._current_frame
        scoreboard_ref = self.scoreboard
        self.__init__(shadow=shadow)
        self.innings_history = history
        self.scoreboard = scoreboard_ref
        self.innings = 2
        if target is not None:
            self.target = target
        if batting_team is not None:
            self.batting_team = batting_team
        self.mode = "COLD_START"
        self._inn2_reset_frame = reset_frame
        self._inn2_reset_wall = time.time()
        self._inn2_first_commit_seen = bool(warm_restart)
        # A2 prerequisite: explicit reset of the event-baseline anchor.
        # self.__init__() runs the __init__ body but doesn't delete
        # instance attributes set after init, so _event_baseline_score
        # would otherwise survive carrying innings-1's final score —
        # producing a negative d_score on innings-2's first card and
        # dropping the event at the L2058 regression check.
        self._event_baseline_score = 0
        if _trace is not None:
            try:
                _trace.get_recorder().record(
                    tag="EVENT-BASELINE-RESET-INNINGS-2",
                    prev_baseline=(
                        int(_prev_event_baseline)
                        if _prev_event_baseline is not None else None),
                    frame_id=str(reset_frame))
            except Exception:
                pass

    def in_inn2_transition(
            self,
            current_frame_idx: int,
            current_wall: float | None = None) -> bool:
        reset_frame = getattr(self, "_inn2_reset_frame", None)
        if reset_frame is None:
            return False
        if getattr(self, "_inn2_first_commit_seen", False):
            return False
        reset_wall = getattr(self, "_inn2_reset_wall", None)
        if reset_wall is None:
            return False
        if current_wall is None:
            current_wall = time.time()
        frames_since = current_frame_idx - reset_frame
        wall_since = current_wall - reset_wall
        primary = (
            frames_since < INN2_TRANSITION_FRAMES
            and wall_since < INN2_TRANSITION_SECONDS)
        safety_net = wall_since < INN2_TRANSITION_CEILING_SECONDS
        return primary or safety_net

    def mark_inn2_first_commit(self) -> None:
        self._inn2_first_commit_seen = True

    def _attempt_inn2_bootstrap(self, frame: FrameInput) -> bool:
        """Detect mid-match restart and seed innings 2 directly.

        Fires at most once per pipeline session. Returns True if
        bootstrap fired. Guard is set only on success so a late
        target observation can still trigger bootstrap on a later
        frame.
        """
        if self._inn2_bootstrap_attempted:
            return False
        if self.innings != 1:
            return False
        if self.score is not None and self.score != 0:
            return False
        if frame.broadcast_target is None or frame.broadcast_target <= 0:
            return False
        seed_score = frame.ext_score
        if seed_score is None or seed_score <= 0:
            return False
        log.info(
            f"[INNINGS-2-BOOTSTRAP] target={frame.broadcast_target} "
            f"seed_score={seed_score} — restart detected "
            f"mid-innings-2, bypassing 3-frame consensus")
        self.set_innings_2(target=frame.broadcast_target,
                           reason="restart_bootstrap")
        self._inn2_bootstrap_attempted = True
        return True

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _snapshot(self) -> dict:
        return {
            "score": self.score, "wickets": self.wickets, "overs": self.overs,
            "bat1_name": self.bat1_name, "bat1_runs": self.bat1_runs,
            "bat1_balls": self.bat1_balls,
            "bat2_name": self.bat2_name, "bat2_runs": self.bat2_runs,
            "bat2_balls": self.bat2_balls,
            "bowler_name": self.bowler_name,
            "bowler_wickets": self.bowler_wickets,
            "bowler_runs": self.bowler_runs,
            "extras_total": self._extras_writable().get("total"),
        }

    def _accept_update(self, card: dict, frame: int = 0) -> None:
        if frame and frame != self._current_frame:
            self._current_frame = int(frame)
        if card.get("score") is not None:
            _prior_score = self.score
            if (self.mode == "WARM"
                    and _prior_score is not None
                    and card["score"] > _prior_score):
                self._warm_advancing_observed = True
            self.score = card["score"]
        if card.get("wickets") is not None:
            self.wickets = card["wickets"]
        if card.get("overs") is not None:
            _prior_overs_for_gap = self.overs
            self.overs = card["overs"]
            self._track_overs_advance(
                _prior_overs_for_gap, self.overs, frame)
            if _SmOutcome is not None:
                _ledger_record(frame, _SmOutcome.ACCEPTED_COMMIT)

        self._update_batters(card)

        if card.get("bowler_name"):
            # Issue 2 (2026-04-21): bowler rotation rule.  A bowler
            # can't bowl two consecutive overs — if the incoming name
            # matches the previous-over bowler, reject the identity flip.
            _prev = (getattr(self.scoreboard, "_prev_over_bowler", None)
                     if self.scoreboard else None)
            if not (_prev and card["bowler_name"] == _prev):
                self.bowler_name = card["bowler_name"]

        if card.get("speed_kph"):
            self.last_speed = card["speed_kph"]
            self.last_speed_at_over = self.overs
        if card.get("broadcast_target") and not self.target:
            # Fix 16: route through canonical setter so cached
            # innings-1 scalars are reset, not just the field flip.
            self.set_innings_2(target=card["broadcast_target"],
                               batting_team=self.batting_team,
                               reason="_update_misc.target_arrival")

    def _track_overs_advance(self, prev_overs, new_overs, frame) -> None:
        new_legal = _legal_balls_from_overs(new_overs)
        if new_legal is None:
            return
        prev_legal = _legal_balls_from_overs(prev_overs)
        if self._expected_next_ball is None or prev_legal is None:
            self._expected_next_ball = ExpectedBall(
                over=new_legal // 6,
                ball=(new_legal % 6) + 1,
                legal_ball_count=new_legal,
            )
            return
        delta = new_legal - prev_legal
        if delta >= 2:
            log.info(
                f"[GAP-DETECTED] Δballs={delta} "
                f"prev_legal={prev_legal} new_legal={new_legal} "
                f"prev_overs={prev_overs} new_overs={new_overs} "
                f"frame={frame} innings={self.innings}")
        if delta != 0:
            self._expected_next_ball.legal_ball_count = new_legal
            self._expected_next_ball.over = new_legal // 6
            self._expected_next_ball.ball = (new_legal % 6) + 1

    def _update_batters(self, card: dict) -> None:
        card_b1 = card.get("bat1_name")
        card_b2 = card.get("bat2_name")
        if not card_b1 and not card_b2:
            return

        # Dismissed-batter resurrection guard (2026-04-21).  Live probe
        # of SRH-vs-DC inn2 caught SM broadcasting `striker=Axar Patel`
        # AFTER Patel's wicket (W7).  Root cause: a stale broadcast
        # strip briefly re-showed Patel's name, _update_batters accepted
        # it, and SM re-slotted him into bat1/bat2.  Scrub any card
        # entry that names a batter the scoreboard already marks as
        # dismissed — those reads are OCR noise from post-wicket
        # graphics and must not re-enter SM's crease state.
        if self.scoreboard is not None:
            for _key in ("bat1_name", "bat2_name"):
                _nm = card.get(_key)
                if not _nm:
                    continue
                _card = (self.scoreboard.batting_card or {}).get(_nm)
                if _card and _card.get("status") == "out":
                    log.warn(
                        f"[SM] dropping {_key}='{_nm}' from card — "
                        f"scoreboard shows status=out (stale strip "
                        f"read of dismissed batter)")
                    card[_key] = None
                    card.pop(_key.replace("_name", "_runs"), None)
                    card.pop(_key.replace("_name", "_balls"), None)
        card_b1 = card.get("bat1_name")
        card_b2 = card.get("bat2_name")
        if not card_b1 and not card_b2:
            return

        # DC-vs-CSK Fix 5: strip-row → slot binding by NAME match.
        # Reject the entire frame's batter update when both strip rows
        # name the same batter (Scout duplicated one row into both
        # slots). When SM already has a current pair and neither
        # strip name matches either of them, log STRIP-ROW-NAME-
        # MISMATCH and reject — keeps WS-SLOT-INVARIANT as backstop
        # only.
        if card_b1 and card_b2 and self._same_name(card_b1, card_b2):
            log.warn(
                f"  [STRIP-ROW-DUPLICATE] both strip rows name same "
                f"batter — bat1={card_b1!r} bat2={card_b2!r}; "
                f"rejecting batter update")
            for _k in ("bat1_name", "bat1_runs", "bat1_balls",
                       "bat2_name", "bat2_runs", "bat2_balls"):
                card.pop(_k, None)
            return
        if (self.bat1_name or self.bat2_name):
            cur_pair = [n for n in (self.bat1_name, self.bat2_name) if n]

            def _row_matches_current(_row_name: str | None) -> bool:
                if not _row_name:
                    return True
                return any(self._same_name(_row_name, _cur)
                           for _cur in cur_pair)
            mismatched: list[str] = []
            if card_b1 and not _row_matches_current(card_b1):
                mismatched.append(card_b1)
            if card_b2 and not _row_matches_current(card_b2):
                mismatched.append(card_b2)
            if mismatched and len(mismatched) == len(
                    [n for n in (card_b1, card_b2) if n]):
                # Every named row mismatches — the strip is reading a
                # different pair than SM. Keep WS-SLOT-INVARIANT as the
                # backstop; reject this frame's batter update.
                log.warn(
                    f"  [STRIP-ROW-NAME-MISMATCH] strip rows "
                    f"{mismatched!r} match neither current "
                    f"bat1={self.bat1_name!r} nor "
                    f"bat2={self.bat2_name!r}; rejecting batter update")
                for _k in ("bat1_name", "bat1_runs", "bat1_balls",
                           "bat2_name", "bat2_runs", "bat2_balls"):
                    card.pop(_k, None)
                return

        # Bootstrap: adopt batter names when internal state has none
        if not self.bat1_name and not self.bat2_name:
            self.bat1_name = card_b1
            self.bat2_name = card_b2
            if not self.striker:
                self._set_slot_pair(
                    self.bat1_name, self.bat2_name,
                    source="update_batters_bootstrap")
            self._w8_guard_fired.clear()
            return

        # Use fuzzy-match aware set difference for arrivals/departures
        card_batters = [n for n in (card_b1, card_b2) if n]
        my_batters = [n for n in (self.bat1_name, self.bat2_name) if n]

        def _fuzzy_in(name, names_list):
            for n in names_list:
                if self._same_name(name, n):
                    return True
            return False

        arrived = [n for n in card_batters if not _fuzzy_in(n, my_batters)]
        departed = [n for n in my_batters if not _fuzzy_in(n, card_batters)]

        if (len(arrived) == 1 and len(departed) == 1):
            gone = departed[0]
            new = arrived[0]
            if self.bat1_name == gone:
                self.bat1_name = new
            elif self.bat2_name == gone:
                self.bat2_name = new
                self._w8_guard_fired.clear()

    def _update_supplements(self, card: dict, frame: FrameInput) -> None:
        if card.get("speed_kph"):
            self.last_speed = card["speed_kph"]
            self.last_speed_at_over = self.overs
        if card.get("broadcast_target") and not self.target:
            # Fix 16: route through canonical setter so cached
            # innings-1 scalars are reset, not just the field flip.
            self.set_innings_2(
                target=card["broadcast_target"],
                batting_team=self.batting_team,
                reason="_update_supplements.target_arrival")
        if frame.broadcast_venue and not self.venue:
            self.venue = frame.broadcast_venue

        # Broadcast this-over backfill removed 2026-05-20 (option G —
        # wholesale-accept path deleted; broadcast_this_over field stays
        # in FrameInput/card for now but no longer drives state mutation
        # here. ThisOverManager.on_broadcast_override is also deleted.
        # The deleted block used _merge_broadcast to canonicalize then
        # gated on _is_legal_run_token / this_over_src=="bcast" to
        # backfill '?' slots. With on_broadcast_override gone there's
        # no broadcast source to backfill from; tokens come only from
        # observed ball events.

        # Striker resolution moved to _identify_and_set so that
        # balls-faced and runs-delta evidence can take precedence over
        # the broadcast indicator (which suffers from surname-cluster
        # ambiguity, e.g. KKR's Singh/Roy where the broadcast strip
        # showing "Singh" matches both Rinku Singh and his partner).
        # _identify_and_set is invoked from on_frame BEFORE
        # _update_batters mutates internal batter state, so the
        # resulting deltas are well-defined.

    def _sm_w8_partner_if_active(
            self, partner: str | None) -> str | None:
        """Return ``partner`` unless scoreboard marks them dismissed (PR3).

        Suppresses re-introducing ``bat1_name`` / ``bat2_name`` /
        ``self.non`` partners who are already ``status=out`` on the
        batting card.  Deduped `[SM-W8-DISMISSED-GUARD]` telemetry
        per §14.8.
        """
        if not partner:
            return None
        if not self.scoreboard:
            return partner
        entry = (self.scoreboard.batting_card or {}).get(partner)
        if entry and entry.get("status") == "out":
            if partner not in self._w8_guard_fired:
                log.info(
                    f"[SM-W8-DISMISSED-GUARD] suppressed partner="
                    f"{partner!r} — batting_card.status=out")
                self._w8_guard_fired.add(partner)
            return None
        return partner

    def _w8_non_for_identified(self, new: str) -> str | None:
        """Non-striker paired with identified striker ``new`` (W8 / Lever 1).

        Fuzzy-matches ``new`` to ``bat1_name`` / ``bat2_name``.  If neither
        matches, applies §3.3: retain prior ``non`` only when its
        canonical form differs from ``new``'s; otherwise ``None`` so
        ``_set_slot_pair`` does not propagate a stale duplicate.

        Lever 1 PR3: partners with ``batting_card.status=out`` return
        ``None`` so dismissed names are not written back into ``non``.
        """
        if self.bat1_name and self._same_name(new, self.bat1_name):
            return self._sm_w8_partner_if_active(self.bat2_name)
        if self.bat2_name and self._same_name(new, self.bat2_name):
            return self._sm_w8_partner_if_active(self.bat1_name)
        _nc = self._canonicalize_name(new) or new
        _prior_non = (self._canonicalize_name(self.non)
                      or self.non)
        if (_prior_non is not None and _nc is not None
                and _prior_non != _nc):
            return self._sm_w8_partner_if_active(self.non)
        return None

    def _identify_and_set(self, card: dict,
                                  frame: FrameInput,
                                  prev_b1_runs: int | None,
                                  prev_b1_balls: int | None,
                                  prev_b2_runs: int | None,
                                  prev_b2_balls: int | None) -> None:
        """Resolve striker by evidence priority.

        The broadcast `striker` indicator was previously the sole source
        and matched by full-name substring. That broke on the KKR pair
        Rinku Singh / Anukul Roy, where the strip-shown "Singh" is a
        substring of both internal batter names ("Rinku Singh" and the
        late-overs partner sharing the surname). Result: broadcast
        flipped striker on every frame, overriding the correct evidence
        from balls-faced and runs deltas.

        Priority (evidence wins, inference last):
          1. Balls-faced delta — only the striker's ball count ticks
             on a legal delivery. Works for dots, runs, wickets;
             unambiguous on every frame where a legal ball was bowled.
          2. Runs delta — only the striker's runs increase. Works on
             frames where a run-scoring delivery happened.
          3. Broadcast indicator — match against FIRST names so
             surname-clusters (Singh/Roy) don't produce false matches.
          4. Keep current striker (no evidence to flip).
        """
        # Map card-side bat1/bat2 to internal batters by name (positions
        # may differ; the broadcast strip can swap the two rows).
        b1_internal = self.bat1_name
        b2_internal = self.bat2_name
        if not b1_internal and not b2_internal:
            return

        candidates: dict[str, dict] = {}
        for cn_key, cr_key, cb_key in [
            ("bat1_name", "bat1_runs", "bat1_balls"),
            ("bat2_name", "bat2_runs", "bat2_balls"),
        ]:
            cname = card.get(cn_key)
            if not cname:
                continue
            if b1_internal and self._same_name(cname, b1_internal):
                prev_r, prev_b, internal = (prev_b1_runs, prev_b1_balls,
                                            b1_internal)
            elif b2_internal and self._same_name(cname, b2_internal):
                prev_r, prev_b, internal = (prev_b2_runs, prev_b2_balls,
                                            b2_internal)
            else:
                continue
            cur_r = card.get(cr_key)
            cur_b = card.get(cb_key)
            d_r = ((cur_r - prev_r) if (cur_r is not None
                                         and prev_r is not None)
                   else None)
            d_b = ((cur_b - prev_b) if (cur_b is not None
                                         and prev_b is not None)
                   else None)
            candidates[internal] = {"d_runs": d_r, "d_balls": d_b}

        new: str | None = None
        method: str | None = None

        # Priority 1: balls-faced delta == 1 (one batter's ball count
        # ticked, the other's didn't). Most reliable signal.
        bumped_b = [n for n, c in candidates.items() if c["d_balls"] == 1]
        flat_b = [n for n, c in candidates.items() if c["d_balls"] == 0]
        if len(bumped_b) == 1 and len(flat_b) >= 1:
            new = bumped_b[0]
            method = "balls_delta"

        # Priority 2: runs delta > 0 (only the striker scored)
        if not new:
            bumped_r = [n for n, c in candidates.items()
                        if c["d_runs"] is not None and c["d_runs"] > 0]
            flat_r = [n for n, c in candidates.items() if c["d_runs"] == 0]
            if len(bumped_r) == 1 and len(flat_r) >= 1:
                new = bumped_r[0]
                method = "runs_delta"

        # Priority 3: broadcast indicator with FIRST-NAME match.  Skip
        # when both batters share the same first name (rare but defends
        # against the symmetric ambiguity we built this for).
        if not new and card.get("broadcast_striker"):
            ind = card["broadcast_striker"].lower().strip()
            b1_first = ((b1_internal or "").split() or [""])[0].lower()
            b2_first = ((b2_internal or "").split() or [""])[0].lower()
            if b1_first and b2_first and b1_first != b2_first:
                if b1_first in ind and b2_first not in ind:
                    new = b1_internal
                    method = "broadcast_first_name"
                elif b2_first in ind and b1_first not in ind:
                    new = b2_internal
                    method = "broadcast_first_name"

        # Priority 3' (S5b-3a, 2026-05-20, feature-gated): post-wicket
        # new-batter detection via slot-diff. Computes the slot-diff
        # answer in shadow regardless of flag state so trace data
        # accumulates; only overrides `new` when SM_POST_WICKET_SLOT_DIFF
        # is on AND the broadcast paths above didn't already resolve.
        # See cold_start_initial_striker_design.md §3.1.
        _slot_diff_result: str | None = None
        _slot_diff_method: str | None = None
        if self.striker is None and self._post_wicket_slot_to_diff:
            _slot_key = self._post_wicket_slot_to_diff
            _new_in_slot = card.get(_slot_key)
            if _new_in_slot and _new_in_slot != self.non:
                _slot_diff_result = _new_in_slot
                _slot_diff_method = "post_wicket_slot_diff"
        if (_trace is not None and self._post_wicket_slot_to_diff
                and (_slot_diff_result or new)):
            try:
                _trace.get_recorder().record(
                    tag="STRIKER-POST-WICKET-DERIVATION",
                    broadcast_path_result=new,
                    broadcast_method=method,
                    slot_diff_result=_slot_diff_result,
                    slot_diff_method=_slot_diff_method,
                    cleared_slot=self._post_wicket_slot_to_diff,
                    self_striker=self.striker,
                    self_non=self.non,
                    bat1_name=self.bat1_name,
                    bat2_name=self.bat2_name,
                    divergence_fields=(
                        ["striker"]
                        if (_slot_diff_result and _slot_diff_result != new)
                        else []),
                    flag_on=SM_POST_WICKET_SLOT_DIFF,
                    frame_id=str(getattr(frame, "frame_id", None)))
            except Exception:
                pass
        if (SM_POST_WICKET_SLOT_DIFF and _slot_diff_result and not new):
            new = _slot_diff_result
            method = _slot_diff_method

        if new and new != self.striker:
            if self.striker is not None:
                # Deterministic striker rotation (2026-05-19) — SM-internal
                # parity with 2105463. Once an initial striker is locked
                # (innings-start init or post-wicket new-batter), the
                # broadcast/strip-derived striker indicator no longer
                # overrides self.striker mid-over. SM's per-ball rotation
                # in `_apply_event` is the sole authority through to the
                # next wicket.
                #
                # Surfaced by files/tests/test_sm_derivation_ledger.py
                # at ball 4.6 of the DC vs KKR fixture: the broadcast
                # indicator advanced to the post-wicket-and-EOO-swap
                # striker (Nissanka) mid-frame, flipping `self.striker`
                # before the wicket-attribution logic could identify
                # Rahul as dismissed.
                log.info(
                    f"  [STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC]"
                    f" method={method} broadcast={new!r} "
                    f"deterministic={self.striker!r} — "
                    f"keeping deterministic")
                if _trace is not None:
                    try:
                        _trace.get_recorder().record(
                            tag=("STRIKER-SM-BROADCAST-DISAGREES-"
                                 "DETERMINISTIC"),
                            method=method,
                            broadcast_striker=new,
                            deterministic_striker=self.striker)
                    except Exception:
                        pass
            else:
                log.info(f"[STRIKER] method={method} striker={new} "
                         f"(was={self.striker})")
                _ns = self._w8_non_for_identified(new)
                self._set_slot_pair(
                    new, _ns, source=f"identify_and_set.{method}")

        # S5b-3a: once striker is non-None again, the post-wicket gap
        # is closed; clear the slot-diff anchor.
        if self.striker is not None and self._post_wicket_slot_to_diff:
            self._post_wicket_slot_to_diff = None


    # ------------------------------------------------------------------
    # Event inference
    # ------------------------------------------------------------------

    @staticmethod
    def _overs_to_balls(overs: float) -> int:
        """Convert overs (base-6) to total balls. 8.5 → 53, 9.0 → 54."""
        full = int(overs)
        part = round((overs - full) * 10)
        return full * 6 + part

    @staticmethod
    def _balls_to_overs(total_balls: int) -> float:
        """Inverse of _overs_to_balls — legal-ball index → team overs float."""
        if total_balls <= 0:
            return 0.0
        full = total_balls // 6
        rem = total_balls % 6
        if rem == 0:
            return float(full)
        return float(full) + rem / 10.0

    def _apply_multi_ball_gap(
            self,
            d_score: int, d_wickets: int, d_balls: int,
            striker: str | None, non: str | None,
            bowler_name: str | None) -> dict:
        """Inline computation of multi-ball gap effects (scoping scaffold).

        Pure function. Returns a result dict describing the state writes a
        multi-ball gap of (d_balls runs=d_score wickets=d_wickets) would
        produce — partnership delta, per-bowler total, per-ball batter
        credits, and the final striker pair after rotation. Uses the same
        ``_infer_gap_tokens`` heuristic as ``_decompose_multi_ball`` +
        ``_apply_absorbed_event`` so the predicted delta matches the
        actual decomposition path token-for-token.

        Does NOT mutate self. The ``SM_INLINE_MULTI_BALL`` flag does not
        gate any behavior in this method — it controls the dispatch-loop
        shadow comparison wiring in ``_handle_warm``. This scaffold's
        purpose is to produce predicted deltas for shadow comparison;
        the flag-on path swap is a future commit gated on the shadow
        data confirming equivalence. See
        ``files/docs/investigations/dispatch_loop_redesign_scoping.md``.
        """
        result: dict[str, Any] = {
            "d_score": int(d_score),
            "d_wickets": int(d_wickets),
            "d_balls": int(d_balls),
            "bowler_name": bowler_name,
            "striker_in": striker,
            "non_in": non,
            "partnership_balls_delta": 0,
            "partnership_runs_delta": 0,
            "bowler_balls_delta": 0,
            "bowler_runs_delta": 0,
            "bowler_wickets_delta": 0,
            "batter_credits": [],
            "final_striker": striker,
            "final_non": non,
            "wicket_event": None,
            "tokens": [],
        }
        if d_balls <= 0:
            return result
        if _infer_gap_tokens is not None:
            tokens = list(_infer_gap_tokens(
                int(d_balls), int(d_score), int(d_wickets)))
        else:
            tokens = ["?"] * int(d_balls)
        result["tokens"] = list(tokens)
        cur_str = striker
        cur_non = non
        for idx, tok in enumerate(tokens):
            is_last = idx == int(d_balls) - 1
            if tok in (".", "W", "?"):
                single_runs = 0
            else:
                try:
                    single_runs = int(tok)
                except (TypeError, ValueError):
                    single_runs = 0
            wkt_delta = 1 if (is_last and int(d_wickets) > 0) else 0
            result["partnership_balls_delta"] += 1
            if is_last:
                result["partnership_runs_delta"] += int(d_score)
            result["bowler_balls_delta"] += 1
            result["bowler_runs_delta"] += single_runs
            result["bowler_wickets_delta"] += wkt_delta
            if cur_str and tok != "W":
                result["batter_credits"].append({
                    "name": cur_str,
                    "runs_delta": single_runs,
                    "balls_delta": 1,
                    "fours": 1 if tok == "4" else 0,
                    "sixes": 1 if tok == "6" else 0,
                })
            if single_runs % 2 == 1 and cur_non:
                cur_str, cur_non = cur_non, cur_str
        result["final_striker"] = cur_str
        result["final_non"] = cur_non
        if int(d_wickets) > 0:
            result["wicket_event"] = {
                "type": "WICKET",
                "runs": int(d_score),
                "legal": True,
                "this_over_token": "W",
                "striker": cur_str,
            }
        return result

    def _capture_multi_ball_shadow_state(self) -> dict:
        sb = self.scoreboard
        if sb is not None:
            inn = sb._inn or {}
            bowling_card = inn.get("bowling_card") or {}
            batting_card = sb.batting_card or {}
        else:
            bowling_card = {}
            batting_card = {}
        return {
            "partnership_runs": int(self.partnership_runs or 0),
            "partnership_balls": int(self.partnership_balls or 0),
            "striker": self.striker,
            "non": self.non,
            "score": self.score,
            "wickets": self.wickets,
            "overs": self.overs,
            "bowling_card": {
                name: {
                    "runs": (c or {}).get("runs"),
                    "balls": (c or {}).get("balls"),
                    "wickets": (c or {}).get("wickets"),
                }
                for name, c in bowling_card.items()
            },
            "batting_card": {
                name: {
                    "runs": (c or {}).get("runs"),
                    "balls": (c or {}).get("balls"),
                    "fours": (c or {}).get("fours"),
                    "sixes": (c or {}).get("sixes"),
                }
                for name, c in batting_card.items()
            },
        }

    @staticmethod
    def _compute_multi_ball_shadow_actual_delta(
            before: dict, after: dict) -> dict:
        def _pb_delta(field: str) -> int:
            return int((after.get(field) or 0)) - int((before.get(field) or 0))
        delta: dict[str, Any] = {
            "partnership_runs_delta": _pb_delta("partnership_runs"),
            "partnership_balls_delta": _pb_delta("partnership_balls"),
            "score_delta": _pb_delta("score"),
            "wickets_delta": _pb_delta("wickets"),
            "bowler": {},
            "batter": {},
            "striker_change": None,
            "non_change": None,
        }
        if before.get("striker") != after.get("striker"):
            delta["striker_change"] = (before.get("striker"), after.get("striker"))
        if before.get("non") != after.get("non"):
            delta["non_change"] = (before.get("non"), after.get("non"))
        for name, after_card in (after.get("bowling_card") or {}).items():
            before_card = (before.get("bowling_card") or {}).get(name) or {}
            d = {}
            for k in ("runs", "balls", "wickets"):
                db = int(before_card.get(k) or 0)
                da = int(after_card.get(k) or 0)
                if da != db:
                    d[f"{k}_delta"] = da - db
            if d:
                delta["bowler"][name] = d
        for name, after_card in (after.get("batting_card") or {}).items():
            before_card = (before.get("batting_card") or {}).get(name) or {}
            d = {}
            for k in ("runs", "balls", "fours", "sixes"):
                db = int(before_card.get(k) or 0)
                da = int(after_card.get(k) or 0)
                if da != db:
                    d[f"{k}_delta"] = da - db
            if d:
                delta["batter"][name] = d
        return delta

    @staticmethod
    def _compare_multi_ball_shadow(predicted: dict, actual: dict) -> list[str]:
        divergent: list[str] = []
        for field in ("partnership_runs_delta", "partnership_balls_delta"):
            if int(predicted.get(field) or 0) != int(actual.get(field) or 0):
                divergent.append(field)
        bowler_name = predicted.get("bowler_name")
        actual_bowler = (actual.get("bowler") or {}).get(bowler_name) or {}
        for k in ("balls_delta", "runs_delta", "wickets_delta"):
            pred_key = "bowler_" + k.replace("_delta", "") + "_delta"
            if (int(predicted.get(pred_key) or 0)
                    != int(actual_bowler.get(k) or 0)):
                divergent.append(pred_key)
        predicted_batter_runs = sum(
            int(c.get("runs_delta") or 0)
            for c in predicted.get("batter_credits") or [])
        actual_batter_runs = sum(
            int((c or {}).get("runs_delta") or 0)
            for c in (actual.get("batter") or {}).values())
        if predicted_batter_runs != actual_batter_runs:
            divergent.append("batter_runs_total")
        predicted_batter_balls = sum(
            int(c.get("balls_delta") or 0)
            for c in predicted.get("batter_credits") or [])
        actual_batter_balls = sum(
            int((c or {}).get("balls_delta") or 0)
            for c in (actual.get("batter") or {}).values())
        if predicted_batter_balls != actual_batter_balls:
            divergent.append("batter_balls_total")
        if predicted.get("final_striker") != predicted.get("striker_in"):
            actual_final = (actual.get("striker_change") or (None, None))[1]
            if actual_final and actual_final != predicted.get("final_striker"):
                divergent.append("final_striker")
        return divergent

    def _decompose_multi_ball(
            self,
            d_score: int, d_wickets: int, d_overs: float, d_balls: int,
            striker: str | None) -> list[dict]:
        """Expand a skipped-delivery gap into N Policy U absorbed events.

        Preconditions: ``validate_diff`` has already accepted ``d_balls``
        (≤ :data:`cricket_rules.MULTI_BALL_MAX_BALLS`). Larger gaps are
        rejected in :meth:`_handle_warm` before this runs — see
        :func:`_warn_multi_ball_cap_if_cricket_reject`.
        """
        gap_meta = {
            "balls_skipped": d_balls,
            "runs": d_score,
            "wickets_in_gap": d_wickets,
            "overs_skipped": d_overs,
        }
        log.info(
            f"[MULTI_BALL_DECOMPOSED] balls_skipped={d_balls} runs={d_score} "
            f"wickets_in_gap={d_wickets} overs_skipped={d_overs}")
        out: list[dict] = []
        last_i = d_balls - 1
        for i in range(d_balls):
            ev: dict[str, Any] = {
                "type": ABSORBED_LEGAL,
                "absorbed": True,
                "certain": False,
                "runs": None,
                "legal": True,
                "striker": striker,
                "ball_index": i,
                "gap_parent": gap_meta if i == 0 else None,
                "_gap_meta": gap_meta,
            }
            if i == last_i and d_wickets > 0:
                ev["gap_finalize_wicket"] = True
            log.debug(
                f"[ABSORBED_LEGAL] ball_index={i}/{last_i} "
                f"finalize_wkt={ev.get('gap_finalize_wicket', False)}")
            # B1.2c: enqueue a PendingBall per emitted event. over_mgr's
            # ABSORBED_LEGAL handler will bind each slot back via
            # bind_pending_slot() in FIFO order. Per-ball runs_delta is
            # 0 here; B1.3's drain distributes from gap_meta.runs.
            self._enqueue_pending_ball(
                runs_delta=0,
                wickets_delta=1 if ev.get("gap_finalize_wicket") else 0,
                frame_id=self._current_frame,
                slot_idx=None,
            )
            out.append(ev)
        return out

    def _infer_event(self, d_score: int, d_wickets: int, d_overs: float,
                     prev: dict, card: dict,
                     frame: FrameInput) -> dict | list[dict] | None:

        striker, non, striker_runs = self._identify_striker(
            prev, card, frame)

        # MULTI_BALL: skipped deliveries (use ball count, not decimal overs)
        new_overs = card.get("overs") or self.overs or 0
        old_overs = prev.get("overs") or 0
        d_balls = self._overs_to_balls(new_overs) - self._overs_to_balls(old_overs)
        if d_balls > 1:
            return self._decompose_multi_ball(
                d_score, d_wickets, d_overs, d_balls, striker)

        # EXTRAS: score changed, overs didn't — but require a HARD signal
        # before committing.  An overs lag alone is not enough: the
        # scoreboard often updates score before overs by 1 frame on a
        # legal delivery.  Without a hard signal we defer one more frame;
        # if next frame brings d_overs > 0 with the same delta, the
        # legal-delivery branch will fire instead.
        if d_score > 0 and d_overs == 0 and d_wickets == 0:
            extras_now = card.get("extras_total")
            extras_prev = prev.get("extras_total")
            extras_bumped = (
                extras_now is not None and extras_prev is not None
                and extras_now > extras_prev)
            has_hard_signal = (
                card.get("broadcast_extra") in {"WD", "NB"}
                or extras_bumped
                or d_score == 1
                or self._extras_persistent_lag)
            if not has_hard_signal:
                log.info(
                    f"[EXTRA-INFER-DEFERRED] frame={frame.frame_id} "
                    f"d_score={d_score} d_overs=0 reason=no_hard_signal "
                    f"— waiting 1 frame")
                return None
            return self._infer_extra(d_score, striker, card, frame)

        # WICKET
        if d_wickets > 0:
            return self._infer_wicket(d_score, d_wickets, d_overs, prev, card,
                                      frame, striker)

        # LEGAL DELIVERY
        if d_overs > 0:
            return self._infer_legal(d_score, striker, striker_runs, card,
                                     frame)

        return None

    def _identify_striker(self, prev: dict, card: dict,
                          frame: FrameInput) -> tuple:
        """Who faced this ball?  Priority: balls delta → broadcast → state.

        Cross-matches card batters to previous batters by fuzzy name
        regardless of slot position (extractor may swap bat1/bat2 order).
        """
        # Build cross-match: for each card batter, find matching prev batter
        matches = self._cross_match_batters(prev, card)

        # Check balls delta via cross-matched pairs
        d_bat: dict[str, tuple] = {}
        for my_name, (c_runs, c_balls, p_runs, p_balls) in matches.items():
            if c_balls is not None and p_balls is not None:
                d_balls = c_balls - p_balls
                d_runs = max((c_runs or 0) - (p_runs or 0), 0)
                d_bat[my_name] = (d_balls, d_runs)

        strikers = [n for n, (db, _) in d_bat.items() if db == 1]
        nons = [n for n, (db, _) in d_bat.items() if db != 1]

        if len(strikers) == 1:
            s = strikers[0]
            ns = nons[0] if nons else (
                self.bat2_name if s == self.bat1_name else self.bat1_name)
            return s, ns, d_bat[s][1]

        # S5b-2 audit (2026-05-20): the broadcast-indicator fallback
        # at this site is deleted. Corpus check showed 7 fallback
        # invocations across L2 + L1.5; in zero of them was
        # `self.striker is None`, and in the 2 cases where the
        # broadcast value disagreed with self.striker (frame 232/245
        # of watch_20260519_121701), the disagreement was the same
        # pattern the 2026-05-19 deterministic rotation override
        # (commit 2105463) was added to block — but at a different
        # call site. Routing those cases through state_fallback
        # produces the deterministic answer in every observed case.
        # See §7.6 of sm_as_orchestrator_design.md for the full
        # audit; the instrumentation tag is kept to surface any
        # future cases where state_fallback isn't authoritative.
        if _trace is not None:
            try:
                _trace.get_recorder().record(
                    tag="STRIKER-IDENTIFY-FALLBACK-INVOKED",
                    branch="state_fallback",
                    d_bat_size=len(d_bat),
                    strikers_count=len(strikers),
                    nons_count=len(nons),
                    self_striker_set=(self.striker is not None),
                    self_striker=self.striker,
                    self_non=self.non,
                    broadcast_striker=card.get("broadcast_striker"),
                    bat1_name=self.bat1_name,
                    bat2_name=self.bat2_name,
                    frame_id=str(getattr(frame, "frame_id", None)))
            except Exception:
                pass

        # State fallback
        cs = card.get("score") if card.get("score") is not None else 0
        ss = self.score if self.score is not None else 0
        return self.striker, self.non, max(cs - ss, 0)

    def _cross_match_batters(self, prev: dict, card: dict) -> dict:
        """Match card batters to internal state batters by fuzzy name.

        Returns {my_name: (card_runs, card_balls, prev_runs, prev_balls)}
        for each matched batter.  Handles extractor swapping bat1/bat2 slots.
        """
        result: dict[str, tuple] = {}
        card_batters = []
        for prefix in ("bat1", "bat2"):
            cn = card.get(f"{prefix}_name")
            if cn:
                card_batters.append((
                    cn, card.get(f"{prefix}_runs"),
                    card.get(f"{prefix}_balls")))

        used_card: set[int] = set()
        for my_name in (self.bat1_name, self.bat2_name):
            if not my_name:
                continue
            for i, (cn, cr, cb) in enumerate(card_batters):
                if i in used_card:
                    continue
                if self._same_name(cn, my_name):
                    # Find prev stats for this batter
                    p_runs, p_balls = None, None
                    for pp in ("bat1", "bat2"):
                        pn = prev.get(f"{pp}_name")
                        if pn and self._same_name(pn, my_name):
                            p_runs = prev.get(f"{pp}_runs")
                            p_balls = prev.get(f"{pp}_balls")
                            break
                    result[my_name] = (cr, cb, p_runs, p_balls)
                    used_card.add(i)
                    break

        return result

    def _infer_extra(self, d_score: int, striker: str | None,
                     card: dict, frame: FrameInput) -> dict:
        if card.get("broadcast_extra") == "WD":
            return {"type": "WIDE", "runs": d_score, "legal": False,
                    "this_over_token": "Wd", "striker": striker}
        if card.get("broadcast_extra") == "NB":
            return {"type": "NO_BALL", "runs": d_score, "legal": False,
                    "batter_runs": d_score - 1, "free_hit_next": True,
                    "this_over_token": "Nb", "striker": striker}

        event: dict = {
            "type": "EXTRA", "runs": d_score, "legal": False,
            "this_over_token": str(d_score), "striker": striker,
            "needs_resolution": True,
        }
        self.pending_extra = event
        self.pending_extra_frames = 0

        for rf in self.recent_frames[-3:]:
            text = (rf.scout_text or "").lower()
            if _matches_no_ball_signal(text):
                event["type"] = "NO_BALL"
                event["this_over_token"] = "Nb"
                event["free_hit_next"] = True
                event["needs_resolution"] = False
                self.pending_extra = None
                break
            if _matches_wide_signal(text):
                event["type"] = "WIDE"
                event["this_over_token"] = "Wd"
                event["needs_resolution"] = False
                self.pending_extra = None
                break

        return event

    def _infer_wicket(self, d_score: int, d_wickets: int, d_overs: float,
                      prev: dict, card: dict, frame: FrameInput,
                      striker: str | None) -> dict:
        prev_batters = {n for n in [prev.get("bat1_name"),
                                    prev.get("bat2_name")] if n}
        curr_batters = {n for n in [card.get("bat1_name"),
                                    card.get("bat2_name")] if n}
        departed = prev_batters - curr_batters
        arrived = curr_batters - prev_batters

        # Slot-diff reliability gate (2026-05-19). A real post-wicket
        # strip frame shows BOTH batters: the survivor + the new
        # incomer. When curr_batters has fewer than 2 names, the
        # strip is either a graphic overlay (camera_view='graphic')
        # OR a transient camera angle focused on one player. The
        # "departed" set in those cases is misleading — names
        # absent from a partial view aren't dismissed, just
        # off-screen for this frame. Trace evidence: frame 245 of
        # watch_20260519_121701 had curr_b=('Pathum Nissanka', None)
        # from a stats-overlay graphic — naive slot-diff resolved
        # dismissed=KL Rahul even though Rahul was still at the
        # crease. Defer to pending_wicket and let `_try_resolve_
        # pending` retry on subsequent frames when both batter
        # slots are observable.
        if len(curr_batters) < 2:
            dismissed = None
            new_batter = None
        else:
            dismissed = departed.pop() if len(departed) == 1 else None
            new_batter = arrived.pop() if len(arrived) == 1 else None

        d_bowler_w = 0
        if (card.get("bowler_wickets") is not None
                and prev.get("bowler_wickets") is not None):
            d_bowler_w = card["bowler_wickets"] - prev["bowler_wickets"]

        if d_score > 0 and d_bowler_w == 0:
            wicket_type = "run_out"
        elif d_bowler_w > 0:
            wicket_type = "bowler_wicket"
        else:
            wicket_type = "unknown"

        action = (frame.action_text or "").lower()
        for wt in ["caught", "bowled", "lbw", "stumped", "run out",
                    "hit wicket"]:
            if wt in action:
                wicket_type = wt.replace(" ", "_")
                break

        event: dict = {
            "type": "WICKET", "runs": d_score, "dismissed": dismissed,
            "new_batter": new_batter, "wicket_type": wicket_type,
            "legal": d_overs > 0, "this_over_token": "W",
            "striker": striker,
        }

        if dismissed is None:
            # Fallback path for legitimate single-wicket case:
            # d_wickets==1 with reliable deterministic striker.
            # Use self.striker (the deterministic-rotation-tracked
            # on-strike batter) as the dismissed batter. This
            # commits the wicket at the same frame as the wickets-
            # counter advance, so downstream consumers (FOW record,
            # partnership reset, harness checkpoint) see consistent
            # state immediately. The d_wickets==1 + striker-known
            # combination is the structurally reliable signature
            # for a real wicket: scoreboard's "max +1/frame" gate
            # only allows single-wicket increments, and the
            # deterministic-striker rotation has authoritative
            # batter identity.
            if d_wickets == 1 and self.striker:
                dismissed = self.striker
                event["dismissed"] = dismissed
                if _trace is not None:
                    try:
                        _trace.get_recorder().record(
                            tag=("WICKET-RESOLVED-FROM-"
                                 "DETERMINISTIC-STRIKER"),
                            dismissed=dismissed,
                            d_wickets=int(d_wickets),
                            frame_id=str(
                                getattr(frame, "frame_id", None)))
                    except Exception:
                        pass
                return event
            # Genuinely indeterminate (d_wickets > 1 or no striker
            # locked). Per derive-not-detect: a wicket can't commit
            # without a deterministically-resolved dismissed name.
            # Store as pending_wicket for `_try_resolve_pending` to
            # retry on subsequent frames; do NOT return the event
            # for immediate processing. The downstream
            # `_apply_wicket_fall_only` has a P1 fallback via
            # frame.broadcast_striker against bat1/bat2 — that
            # path is semantically backwards: an indicator pointing
            # at a batter means they're STILL at the crease, not
            # that they were dismissed.
            #
            # Trace evidence: phantom wicket at frame 245 of
            # watch_20260519_121701 — Scout misread wickets 0→2,
            # scoreboard correctly deferred the +2 delta (consensus
            # 2/3), but card.wickets=2 still drove _infer_wicket here.
            # Slot-diff returned dismissed=None (batter slots
            # unchanged), event was returned anyway, P1 fallback
            # matched broadcast_striker='PATHUM' against bat1='Pathum
            # Nissanka' → falsely recorded Pathum as dismissed at
            # score=38/overs=3.5. FOW immutability guard then blocked
            # the REAL wicket at frame 361 (KL Rahul caught Green
            # bowled Tyagi at 49/5.0) from rewriting that slot.
            #
            # Structural parallel to F381's wicket-attribution-
            # requires-bowler pattern (this commit's wicket-commit-
            # requires-dismissed-identity). 10-frame pending window
            # calibrated against the same broadcast cadence that
            # justified the 5b25e59 bowler-credit threshold tune.
            event["needs_resolution"] = True
            self.pending_wicket = event
            self.pending_wicket_frames = 0
            if _trace is not None:
                try:
                    _trace.get_recorder().record(
                        tag="WICKET-DEFERRED-NO-DISMISSED-IDENTITY",
                        d_score=int(d_score),
                        d_wickets=int(d_wickets),
                        d_overs=float(d_overs),
                        prev_batters=sorted(prev_batters),
                        curr_batters=sorted(curr_batters),
                        frame_id=str(
                            getattr(frame, "frame_id", None)))
                except Exception:
                    pass
            return None

        return event

    def _infer_legal(self, d_score: int, striker: str | None,
                     striker_runs: int, card: dict,
                     frame: FrameInput) -> dict:
        """Classify legal delivery based on team score delta.

        Batter stat deltas are unreliable (extractor lags scorer by 1-2 frames),
        so event type is determined from d_score alone, matching BED's logic.
        LEG_BYE is only inferred from explicit broadcast signals, not stat gaps.
        """
        if d_score == 0:
            return {"type": "DOT", "runs": 0,
                    "this_over_token": ".", "striker": striker}
        if d_score == 4:
            return {"type": "FOUR", "runs": 4,
                    "this_over_token": "4", "striker": striker}
        if d_score == 6:
            return {"type": "SIX", "runs": 6,
                    "this_over_token": "6", "striker": striker}
        return {"type": "RUNS", "runs": d_score, "batter_runs": d_score,
                "this_over_token": str(d_score), "striker": striker}

    # ------------------------------------------------------------------
    # Apply event effects
    # ------------------------------------------------------------------

    def _apply_wicket_fall_only(self, event: dict,
                                frame: FrameInput) -> None:
        """Record FOW / batter slots for a WICKET-shaped event.

        Extracted so ABSORBED_LEGAL gap_finalize_wicket can reuse the
        same semantics without duplicating striker rotation / this_over
        mechanics from :meth:`_apply_event`.
        """
        # Class 9b diagnostic (2026-05-20): trace function entry to
        # confirm dispatch reaches this site at over-end wicket
        # (sub-pattern i-a check). Pure observability; no behavior.
        log.info(
            f"[WICKET-FALL-ONLY-CALLED] frame={getattr(frame, 'frame_id', None)} "
            f"score={self.score} wickets={self.wickets} "
            f"overs={self.overs} event_keys={list(event.keys())}")
        # --- Fall of Wicket ---
        # Resolution priority (2026-05-19 — derive-not-detect):
        #   P2: event.dismissed (authoritative, set by `_infer_wicket`
        #       via card slot-diff OR the deterministic-striker
        #       fallback for d_wickets==1 cases).
        #   P3: SM.self.striker (deterministic-rotation last resort).
        #
        # P1 (frame.broadcast_striker matched against bat1/bat2) was
        # REMOVED 2026-05-19. The semantic was backwards: a
        # broadcast indicator points at a batter who is CURRENTLY at
        # the crease — meaning they're STILL batting, not that they
        # were dismissed. P1's bat1/bat2 match-against-current-pair
        # logic confused presence with departure.
        #
        # Trace evidence (frame 245 of watch_20260519_121701, after
        # _infer_wicket's slot-diff gate blocked the phantom): P1
        # still fired here on a phantom wicket attempt and matched
        # broadcast_striker='PATHUM' against bat1='Pathum Nissanka',
        # overriding the (correct) None / deferred outcome.
        # Trace evidence (frame 361 real wicket, with this commit's
        # _infer_wicket deterministic-striker fallback): event came
        # in with dismissed='KL Rahul' (the actual on-strike dismissed
        # batter), but P1 then matched broadcast_striker='PATHUM'
        # against bat1='Pathum Nissanka' and overrode to dismissed=
        # 'Pathum Nissanka' — wrong batter zeroed, wrong partnership
        # reset shape.
        best_dismissed = event.get("dismissed")
        _resolution_src = (
            "P2:event.dismissed (slot_diff or deterministic_striker)"
            if best_dismissed else None)
        if not best_dismissed:
            best_dismissed = (event.get("striker")
                              or self.striker
                              or "unknown")
            _resolution_src = (
                "P3:SM.self.striker (deterministic-rotation fallback)")
        event["dismissed"] = best_dismissed
        log.info(
            f"[SM] WICKET dismissed={best_dismissed} "
            f"via {_resolution_src} "
            f"(SM.self.striker was {self.striker!r}, "
            f"frame.broadcast_striker={frame.broadcast_striker!r})")
        # Class 9b diagnostic (2026-05-20): trace identity comparison
        # inputs to attribute sub-pattern (i-b: best_dismissed='unknown'
        # / None) vs (i-c: best_dismissed correct but slots already
        # cleared) vs (ii: identity-source canonicalization mismatch
        # — already addressed by 0ddeb58's _same_player_canon).
        log.info(
            f"[WICKET-SLOT-CLEAR-ENTRY] frame={getattr(frame, 'frame_id', None)} "
            f"event_dismissed={event.get('dismissed')!r} "
            f"event_striker={event.get('striker')!r} "
            f"best_dismissed_resolved={best_dismissed!r} "
            f"resolution_src={_resolution_src!r} "
            f"self.striker={self.striker!r} "
            f"self.non={self.non!r} "
            f"self.bat1_name={self.bat1_name!r} "
            f"self.bat2_name={self.bat2_name!r}")
        new_entry = {
            "score": self.score, "overs": self.overs,
            "dismissed": best_dismissed,
            "bowler": self.bowler_name,
            "wicket_type": event.get("wicket_type"),
        }

        # Class 9b fix (2026-05-20): strict == compared slot identity
        # (canonicalized via _build_scorecard gate) against
        # best_dismissed (sourced from event/broadcast and not always
        # canonicalized). Mismatch silently skipped slot-clearing,
        # leaving the dismissed batter on crease — propagated through
        # subsequent balls in over_5+ (watch_20260515_161437 ball 4.6).
        # Use canonical comparison so different identity sources match.
        survivor = None
        for nm in (self.bat1_name, self.bat2_name):
            if nm and not self._same_player_canon(nm, best_dismissed):
                survivor = nm
                break
        # S5b-3a (2026-05-20): capture the slot key of the dismissed
        # striker BEFORE the slot is wiped, so _identify_and_set's
        # Priority 3' slot-diff path can detect the new batter once
        # Scout reads the updated strip. See
        # cold_start_initial_striker_design.md §3.1.
        if self._same_player_canon(best_dismissed, self.striker):
            if self._same_player_canon(self.bat1_name, best_dismissed):
                self._post_wicket_slot_to_diff = "bat1_name"
            elif self._same_player_canon(self.bat2_name, best_dismissed):
                self._post_wicket_slot_to_diff = "bat2_name"
        if self._same_player_canon(self.bat1_name, best_dismissed):
            self.bat1_name = None
        if self._same_player_canon(self.bat2_name, best_dismissed):
            self.bat2_name = None
        if self._same_player_canon(best_dismissed, self.striker):
            self._set_slot_pair(
                None, survivor,
                source="apply_event.wicket_striker_out")
        elif self._same_player_canon(best_dismissed, self.non):
            self._set_slot_pair(
                survivor, None,
                source="apply_event.wicket_non_striker_out")
        target_idx = (self.wickets or 0) - 1
        _fl = self._fow_writable()
        if target_idx < 0:
            _fl.append(new_entry)
        elif target_idx < len(_fl):
            existing = _fl[target_idx]
            is_placeholder = (existing.get("score") == "?"
                              or not existing.get("dismissed"))
            if is_placeholder:
                _fl[target_idx] = new_entry
            else:
                log.warn(
                    f"[SM] FOW W{target_idx + 1} immutable "
                    f"(confirmed {existing.get('dismissed')}@"
                    f"{existing.get('score')}/{existing.get('overs')})"
                    f" — refusing rewrite to "
                    f"{new_entry.get('dismissed')}@"
                    f"{new_entry.get('score')}/"
                    f"{new_entry.get('overs')}")
        else:
            while len(_fl) < target_idx:
                _fl.append(
                    self._make_fow_placeholder(
                        len(_fl) + 1))
            _fl.append(new_entry)
        self.partnership_runs = 0
        self.partnership_balls = 0
        self.partnership_known = True

    def _apply_absorbed_event(
            self, evt: dict, sim_prev: dict, sim_card: dict,
            frame: FrameInput) -> None:
        """Apply one ABSORBED_LEGAL synthetic ball (Policy U / Issue 3).

        Does not rotate striker (D3). Does not append SM ``this_over``
        tokens — :class:`eyes.this_over.ThisOverManager` consumes the
        emitted ``ball_events`` stream with ``?`` / ``W`` placeholders.
        """
        gap_meta = evt.get("_gap_meta") or {}
        nballs = int(gap_meta.get("balls_skipped") or 0)
        runs_in_gap = int(gap_meta.get("runs") or 0)
        wkts_in_gap = int(gap_meta.get("wickets_in_gap") or 0)
        idx = int(evt.get("ball_index") or 0)
        is_last = nballs > 0 and idx >= nballs - 1

        if not self.partnership_known:
            self.partnership_runs = 0
            self.partnership_balls = 0
            self.partnership_known = True
        _pship_runs_before = int(self.partnership_runs or 0)
        _pship_balls_before = int(self.partnership_balls or 0)
        self.partnership_balls += 1
        if is_last:
            self.partnership_runs += runs_in_gap
        if _trace is not None:
            try:
                _trace.get_recorder().record(
                    tag="PARTNERSHIP-WRITE",
                    runs_before=_pship_runs_before,
                    balls_before=_pship_balls_before,
                    runs_after=int(self.partnership_runs or 0),
                    balls_after=int(self.partnership_balls or 0),
                    source="apply_absorbed_event",
                    frame_id=str(self._current_frame))
            except Exception:
                pass

        # Change B (2026-05-14): ABSORBED_LEGAL bowler per-ball credit.
        # The MULTI_BALL gap decomposition produces N ABSORBED_LEGAL
        # events (one per ball).  Per A1 part 2's MULTI_BALL hook,
        # bowler.runs/balls should accumulate via the unified
        # infer_gap_tokens distribution.  Cache the token list on
        # gap_meta on the first call (idx==0), then per-call apply
        # one token's worth of runs to bowler.  Wicket credit lands
        # on the last ball only (when gap_finalize_wicket is set).
        bowler_name = self.bowler_name
        if (bowler_name and self.scoreboard is not None
                and _infer_gap_tokens is not None and nballs > 0):
            _tokens = gap_meta.get("_tokens")
            if _tokens is None:
                _tokens = list(_infer_gap_tokens(
                    nballs, runs_in_gap, wkts_in_gap))
                gap_meta["_tokens"] = _tokens
            if 0 <= idx < len(_tokens):
                _tok = _tokens[idx]
                if _tok in (".", "W", "?"):
                    single_runs = 0
                else:
                    try:
                        single_runs = int(_tok)
                    except (TypeError, ValueError):
                        single_runs = 0
                _wkt_delta = 1 if (is_last and evt.get(
                    "gap_finalize_wicket")) else 0
                self.scoreboard.update_bowler(
                    bowler_name,
                    runs_delta=single_runs,
                    balls_delta=1,
                    wickets_delta=_wkt_delta,
                    frame=self._current_frame)
                if _trace is not None:
                    try:
                        _trace.get_recorder().record(
                            tag="ABSORBED-LEGAL-BOWLER-CREDITED",
                            bowler=bowler_name,
                            ball_index=idx,
                            total_balls=nballs,
                            token=_tok,
                            single_ball_runs=single_runs,
                            wicket_credited=bool(_wkt_delta),
                            frame_id=str(self._current_frame))
                    except Exception:
                        pass
                # A2 part 2: batter credit per absorbed ball.  Tracks
                # current striker across the gap via gap_meta so
                # rotation persists between calls.  Wicket token does
                # not credit the batter (separate WICKET path handles
                # dismissed-batter accounting).
                if "_current_striker" not in gap_meta:
                    gap_meta["_current_striker"] = (
                        evt.get("striker") or self.striker)
                    gap_meta["_current_non"] = self.non
                    gap_meta["_orig_striker"] = (
                        evt.get("striker") or self.striker)
                _cur_str = gap_meta["_current_striker"]
                _cur_non = gap_meta["_current_non"]
                if _cur_str and _tok != "W" and self.scoreboard is not None:
                    self.scoreboard.update_batter(
                        _cur_str,
                        runs_delta=single_runs,
                        balls_delta=1,
                        fours_delta=1 if _tok == "4" else 0,
                        sixes_delta=1 if _tok == "6" else 0,
                        frame=self._current_frame)
                    if _trace is not None:
                        try:
                            _trace.get_recorder().record(
                                tag=("MULTI-BALL-BATTER-"
                                     "DERIVATION-EXPANDED"),
                                batter=_cur_str,
                                ball_index=idx,
                                total_balls=nballs,
                                single_ball_runs=single_runs,
                                token=_tok,
                                source="absorbed_legal",
                                frame_id=str(self._current_frame))
                        except Exception:
                            pass
                if single_runs % 2 == 1 and _cur_non:
                    gap_meta["_current_striker"] = _cur_non
                    gap_meta["_current_non"] = _cur_str
                if is_last:
                    _final_str = gap_meta.get("_current_striker")
                    _orig_str = gap_meta.get("_orig_striker")
                    _final_non = gap_meta.get("_current_non")
                    if (_final_str and _final_non
                            and _final_str != _orig_str):
                        try:
                            self._set_slot_pair(
                                _final_str, _final_non,
                                source="absorbed_legal_decomp")
                        except Exception:
                            pass

        if evt.get("gap_finalize_wicket"):
            w_ev = {
                "type": "WICKET",
                "runs": runs_in_gap,
                "dismissed": evt.get("dismissed"),
                "new_batter": evt.get("new_batter"),
                "wicket_type": evt.get("wicket_type") or "unknown",
                "legal": True,
                "this_over_token": "W",
                "striker": evt.get("striker"),
            }
            self._apply_wicket_fall_only(w_ev, frame)

        if frame.delivery_info:
            evt["delivery"] = frame.delivery_info

    def _emit_credit_skipped(self, reason: str, event: dict,
                              striker_name=None, bowler_name=None) -> None:
        """B1.2e diagnostic: emit CREDIT-SKIPPED-WITH-REASON trace."""
        if _trace is None:
            return
        try:
            _trace.get_recorder().record(
                tag="CREDIT-SKIPPED-WITH-REASON",
                event_type=str(event.get("type")),
                reason=reason,
                striker_name=str(striker_name) if striker_name else None,
                bowler_name=str(bowler_name) if bowler_name else None,
                score=int(self.score or 0),
                overs=str(self.overs) if self.overs is not None else None,
                frame_id=str(self._current_frame),
            )
        except Exception:
            pass

    def _accumulate_stats_from_event(self, event: dict) -> None:
        """Single-writer derivation: post one ball event's contribution
        to scoreboard.batting_card / bowling_card via the *_delta API.

        Runs before strike rotation so `event["striker"]` / `self.striker`
        names the batter who actually faced the ball. Bowler is
        `self.bowler_name`. Skips if scoreboard isn't attached (shadow
        / no-SB tests), if name slots are unset, or for MULTI_BALL
        (ambiguous distribution).
        """
        if self.scoreboard is None:
            self._emit_credit_skipped("NO-SCOREBOARD", event)
            return
        etype = event.get("type")
        if etype in (None, ABSORBED_LEGAL):
            self._emit_credit_skipped(
                "NO-EVENT-TYPE" if etype is None
                else "ABSORBED-FORWARDED-ELSEWHERE",
                event)
            return

        striker_name = event.get("striker") or self.striker
        if not striker_name and self.scoreboard is not None:
            try:
                striker_name = (
                    self.scoreboard._inn or {}).get("striker")
            except Exception:
                striker_name = None
        bowler_name = self.bowler_name
        if not bowler_name and self.scoreboard is not None:
            try:
                bowler_name = (
                    self.scoreboard._inn or {}).get("current_bowler")
            except Exception:
                bowler_name = None

        # A1 part 2: drain pending F381 wickets whenever a known bowler
        # is in context.  In-window pending wickets credit ``bowler_name``;
        # past-window entries are orphaned.
        if bowler_name and getattr(self, "_pending_bowler_wickets", None):
            self._drain_pending_bowler_wickets(bowler_name)
        # Symmetric: drain pending runs/balls backfill entries when a
        # bowler resolves. Mirrors the F381 wicket-drain semantics.
        if (bowler_name
                and getattr(self, "_pending_bowler_ball_credits", None)):
            self._drain_pending_bowler_ball_credits(bowler_name)

        # A1 part 2: MULTI_BALL decomposition.  The synth event from
        # cold-start / broadcast-cutaway carries N balls + M runs in a
        # single record (commentary.py:500); expand into N
        # _apply_bowler_delta calls with even distribution (remainder
        # front-loaded).  Batter not credited — per-ball striker is
        # unknown across the gap.  Skips silently if no bowler locked.
        if etype == "COLD_START_SYNTH":
            n_balls = int(event.get("balls_missed") or 0)
            total_runs = int(event.get("total_runs") or 0)
            wkts_in_gap = int(event.get("wickets_in_gap") or 0)
            if bowler_name and n_balls > 0:
                # Cricket-realistic per-ball distribution via the
                # unified helper.  Replaces the prior even-split
                # heuristic which would credit 1/1/1/1 for a 4-run
                # gap that's almost always a single boundary.
                if _infer_gap_tokens is not None:
                    _tokens = _infer_gap_tokens(
                        n_balls, total_runs, wkts_in_gap)
                else:
                    _tokens = ["?"] * n_balls
                # A2 part 2: per-token striker rotation for batter
                # credit during the gap.  Local mirror of self.striker
                # / self.non; committed back via _set_slot_pair if the
                # rotation count is odd at end of the gap.
                _cur_str = striker_name
                _cur_non = self.non
                for i, _tok in enumerate(_tokens):
                    if _tok in (".", "W", "?"):
                        single_runs = 0
                    else:
                        try:
                            single_runs = int(_tok)
                        except (TypeError, ValueError):
                            single_runs = 0
                    self.scoreboard.update_bowler(
                        bowler_name,
                        runs_delta=single_runs,
                        balls_delta=1,
                        wickets_delta=0,
                        frame=self._current_frame)
                    if _trace is not None:
                        try:
                            _trace.get_recorder().record(
                                tag="MULTI-BALL-DERIVATION-EXPANDED",
                                bowler=bowler_name,
                                ball_index=i,
                                total_balls=n_balls,
                                single_ball_runs=single_runs,
                                token=_tok,
                                total_runs=total_runs,
                                frame_id=str(self._current_frame))
                        except Exception:
                            pass
                    # A2 part 2: batter credit for this gap ball.
                    # Wicket token (W) does NOT credit the batter (the
                    # WICKET event flow handles dismissed batter
                    # separately); other tokens credit the current
                    # striker with runs + 1 ball faced.
                    if _cur_str and _tok != "W":
                        self.scoreboard.update_batter(
                            _cur_str,
                            runs_delta=single_runs,
                            balls_delta=1,
                            fours_delta=1 if _tok == "4" else 0,
                            sixes_delta=1 if _tok == "6" else 0,
                            frame=self._current_frame)
                        if _trace is not None:
                            try:
                                _trace.get_recorder().record(
                                    tag=("MULTI-BALL-BATTER-"
                                         "DERIVATION-EXPANDED"),
                                    batter=_cur_str,
                                    ball_index=i,
                                    total_balls=n_balls,
                                    single_ball_runs=single_runs,
                                    token=_tok,
                                    frame_id=str(self._current_frame))
                            except Exception:
                                pass
                    if single_runs % 2 == 1 and _cur_non:
                        _cur_str, _cur_non = _cur_non, _cur_str
                # Commit final rotation if it shifted.
                if _cur_str and _cur_str != striker_name and _cur_non:
                    try:
                        self._set_slot_pair(
                            _cur_str, _cur_non,
                            source="multi_ball_decomp")
                    except Exception:
                        pass
            return

        if etype == "WICKET":
            legal = bool(event.get("legal", True))
            wkt_kind = event.get("wicket_type") or "unknown"
            # A1 part 2: bowler-credited dismissal filter (exclude
            # run_out / retired-hurt / obstructing-field / unknown).
            bowler_attributable = _is_bowler_credited_dismissal(wkt_kind)
            runs_this_ball = int(event.get("runs", 0) or 0)
            if striker_name:
                self.scoreboard.update_batter(
                    striker_name,
                    runs_delta=runs_this_ball,
                    balls_delta=1 if legal else 0,
                    fours_delta=0, sixes_delta=0,
                    frame=self._current_frame)
            else:
                self._emit_credit_skipped(
                    "WICKET-NO-STRIKER", event,
                    striker_name=striker_name, bowler_name=bowler_name)
            if bowler_name:
                self.scoreboard.update_bowler(
                    bowler_name,
                    runs_delta=runs_this_ball,
                    balls_delta=1 if legal else 0,
                    wickets_delta=1 if bowler_attributable else 0,
                    frame=self._current_frame)
            elif bowler_attributable:
                # F381 backfill: queue for credit when next bowler locks.
                self._queue_pending_bowler_wicket(
                    wkt_kind, event.get("dismissed"))
            return

        if etype == "DOT":
            runs_off_bat, runs_total, legal = 0, 0, True
        elif etype == "FOUR":
            runs_off_bat, runs_total, legal = 4, 4, True
        elif etype == "SIX":
            runs_off_bat, runs_total, legal = 6, 6, True
        elif etype == "RUNS":
            # A2 part 2: extras-attribution refinement.  Bye / leg-bye
            # runs DO NOT credit the bowler and DO NOT credit the
            # batter's runs column (they're team extras), but the ball
            # IS legal and counts in the striker's balls_faced and the
            # bowler's balls.  Bowler's economy is preserved by NOT
            # incrementing runs_this_over for byes/lb; track the
            # subtotal separately on bowling_card[X].byes_lb_this_over
            # so audit can reconstruct the over composition.
            _extras_subtype = event.get("extras_type")
            if _extras_subtype in (
                    "leg_bye_or_bye", "bye", "leg_bye"):
                runs_off_bat = 0
                runs_total = 0
                legal = True
                # Track byes/lb on bowler's transient over-state for
                # observability (maiden check uses runs_this_over
                # which already excludes byes via this branch).
                _byes_lb_runs = int(
                    event.get("extras_runs",
                              event.get("runs", 0)) or 0)
                if (bowler_name and _byes_lb_runs > 0
                        and self.scoreboard is not None):
                    _bc = (self.scoreboard.bowling_card or {}).get(
                        bowler_name)
                    if _bc is not None:
                        _bc["byes_lb_this_over"] = (
                            int(_bc.get("byes_lb_this_over") or 0)
                            + _byes_lb_runs)
            else:
                runs_off_bat = int(
                    event.get("batter_runs",
                              event.get("runs", 0)) or 0)
                runs_total = int(event.get("runs", 0) or 0)
                legal = True
        elif etype == "WIDE":
            runs_off_bat = 0
            runs_total = int(event.get("runs", 0) or 0)
            legal = False
        elif etype == "NO_BALL":
            runs_off_bat = int(event.get("batter_runs", 0) or 0)
            runs_total = int(event.get("runs", 0) or 0)
            legal = False
        elif etype == "EXTRA":
            # Pending unresolved extra — credit bowler with the runs;
            # no batter credit until resolution upgrades the type.
            runs_off_bat = 0
            runs_total = int(event.get("runs", 0) or 0)
            legal = False
        else:
            self._emit_credit_skipped(
                "FALLTHROUGH-NO-BRANCH", event,
                striker_name=striker_name, bowler_name=bowler_name)
            return

        if striker_name and (runs_off_bat != 0 or legal):
            self.scoreboard.update_batter(
                striker_name,
                runs_delta=runs_off_bat,
                balls_delta=1 if legal else 0,
                fours_delta=1 if etype == "FOUR" else 0,
                sixes_delta=1 if etype == "SIX" else 0,
                frame=self._current_frame)
        else:
            self._emit_credit_skipped(
                "NO-STRIKER" if not striker_name else "BATTER-GATE-REJECTED",
                event, striker_name=striker_name, bowler_name=bowler_name)
        if bowler_name and (runs_total != 0 or legal):
            self.scoreboard.update_bowler(
                bowler_name,
                runs_delta=runs_total,
                balls_delta=1 if legal else 0,
                wickets_delta=0,
                frame=self._current_frame)
        else:
            self._emit_credit_skipped(
                "NO-BOWLER" if not bowler_name else "BOWLER-GATE-REJECTED",
                event, striker_name=striker_name, bowler_name=bowler_name)
            # Symmetric runs/balls backfill — analog to F381 wicket
            # backfill above. When bowler_name is None at commit
            # time (typical at over-handoff before Scout sees the
            # new bowler in a clean strip read), enqueue the
            # runs/balls credit for retroactive backfill. Drained
            # by `_drain_pending_bowler_ball_credits` either inline
            # on the next ball commit with a known bowler, or via
            # the on_lock tracker callback at test_pipeline.py:
            # 7198-7206. Without this, the bowler-card credit for
            # every first-ball-after-handoff is silently lost.
            if (not bowler_name and legal):
                self._queue_pending_bowler_ball_credit(
                    runs_delta=runs_total,
                    wickets_delta=0,
                    event_overs=(
                        str(self.overs)
                        if self.overs is not None else None),
                    frame_id=self._current_frame)
            if (legal and self.last_speed is not None
                    and self.last_speed_at_over != self.overs):
                self.last_speed = None
                self.last_speed_at_over = None

    def _apply_event(self, event: dict, prev: dict, card: dict,
                     frame: FrameInput) -> None:
        if event.get("type") == ABSORBED_LEGAL:
            log.warn(
                "[SM] ABSORBED_LEGAL reached _apply_event — "
                "should use _apply_absorbed_event; skipping")
            return
        # --- Stat accumulation (single-writer derivation path) ---
        # Must run BEFORE strike rotation so `event["striker"]` /
        # `self.striker` still names the batter who actually faced the
        # ball. NO_BALL/EXTRA pending resolution is a known gap: an
        # initially-EXTRA-typed event credits the bowler with the
        # extras runs but not the no-ball batter portion if it later
        # resolves to NO_BALL. Out of scope this round.
        self._accumulate_stats_from_event(event)

        # --- This Over ---
        is_over_change = (int(card.get("overs", 0)) != int(prev.get("overs", 0))
                          and (card.get("overs", 0) or 0)
                          > (prev.get("overs", 0) or 0))

        if event["type"] == "COLD_START_SYNTH":
            if is_over_change:
                self._complete_over(prev)
                self.this_over = []
                self.this_over_src = []
            _mb_balls = int(event.get("balls_missed") or 0)
            _mb_runs = int(event.get("total_runs") or 0)
            _mb_wkts = int(event.get("wickets_in_gap") or 0)
            if _mb_balls > 0 and _infer_gap_tokens is not None:
                _mb_tokens = list(
                    _infer_gap_tokens(_mb_balls, _mb_runs, _mb_wkts))
                self.this_over.extend(_mb_tokens)
                self.this_over_src.extend(
                    ["multi_ball_synth"] * len(_mb_tokens))
        elif is_over_change:
            # The ball that triggered the over rollover IS the 6th
            # legal ball of the previous over (the team-overs counter
            # ticks to "X.0" only AFTER that 6th ball lands). It must
            # be appended to the just-completed over BEFORE archiving,
            # NOT started as ball 1 of the new over — that was the
            # visible "last ball bleeds into next over's first ball"
            # bug. After the closing append we archive and start the
            # new over empty; the genuine first ball of the new over
            # arrives on the next frame's event.
            self.this_over.append(event.get("this_over_token", "?"))
            self.this_over_src.append("obs")
            self._rewrite_eyes_this_over_from_event(
                card, event.get("this_over_token", "?"))
            self.completed_over = list(self.this_over)
            self.completed_over_runs = sum(
                int(t) for t in self.this_over if t.isdigit())
            _archive_over_n = int(prev.get("overs", 0) or 0)
            # B1.3 §2.6: defer archive if pending queue has unresolved
            # entries. The §2.7 force-flush deadline (evaluated each
            # frame in _handle_warm) backstops this so the archive
            # eventually proceeds even if attribution never resolves.
            if self._pending_ball_queue:
                self._emit_pending_trace(
                    "OVER-ARCHIVE-DEFERRED-QUEUE-NONEMPTY",
                    over_n=_archive_over_n,
                    queue_depth=len(self._pending_ball_queue),
                    source="sm_apply_event_inline_rollover",
                )
                self._over_archive_pending = _archive_over_n
                # Skip the rest of the archive block on this frame.
                self.this_over_extras = 0
                self.this_over = []
                self.this_over_src = []
                return
            _existing_archive = self.over_history.get(_archive_over_n)
            self.over_history[_archive_over_n] = list(
                self.this_over)
            if _trace is not None:
                try:
                    _trace.get_recorder().record(
                        tag="OVER-ARCHIVE-WRITE",
                        over_n=_archive_over_n,
                        tokens=list(self.this_over),
                        token_count=len(self.this_over),
                        source="sm_apply_event_inline_rollover")
                    if (_existing_archive is not None
                            and list(_existing_archive) != list(self.this_over)):
                        _trace.get_recorder().record(
                            tag="OVER-ARCHIVE-DOUBLE-WRITE",
                            over_n=_archive_over_n,
                            existing_tokens=list(_existing_archive),
                            attempted_tokens=list(self.this_over),
                            source="sm_apply_event_inline_rollover")
                    if len(self.this_over) != 6:
                        _trace.get_recorder().record(
                            tag="OVER-ARCHIVE-INVALID-TOKEN-COUNT",
                            over_n=_archive_over_n,
                            token_count=len(self.this_over),
                            tokens=list(self.this_over))
                except Exception:
                    pass
            if self.this_over_extras:
                log.info(f"[SM/EXTRAS] over {prev.get('overs','?')} "
                         f"closed (inline rollover) with "
                         f"{self.this_over_extras} extra(s) — "
                         f"resetting per-over counter")
            self.this_over_extras = 0
            self.this_over = []
            self.this_over_src = []
            # Clear bowler attribution for the next over. d0df7b4
            # preserves `bowler_name` through the 6th-ball credit
            # (just completed via `_accumulate_stats_from_event`
            # above), but after that credit lands the attribution
            # must expire so the next over's first ball doesn't
            # silently inherit the previous spell's bowler from
            # stale state. Surfaced by L2-Slim frame 205 of the
            # watch_20260519_121701 captured-Scout replay: Narine's
            # 1st ball (3.1) was miscredited to Anukul Roy because
            # `self.bowler_name='Anukul Roy'` persisted from over 3
            # while Scout's frame 205 read had `bowler=None` (only
            # batter rows visible). With the clear, the next frame's
            # `_accumulate_stats_from_event` finds no current bowler
            # and emits `CREDIT-SKIPPED-WITH-REASON: NO-BOWLER`;
            # the ball routes through the B1.x pending queue and
            # drains when the tracker LOCKs the new bowler (Narine
            # at frame 213 in this fixture).
            _prev_bowler_at_clear = self.bowler_name
            self.bowler_name = None
            if (self.scoreboard is not None
                    and self.scoreboard._inn is not None):
                self.scoreboard._inn["current_bowler"] = None
            if _trace is not None:
                try:
                    _trace.get_recorder().record(
                        tag="BOWLER-LOCK-RELEASED",
                        reason="over_end_credit_complete",
                        prev_bowler=_prev_bowler_at_clear,
                        over_n=_archive_over_n,
                        frame_id=str(self._current_frame))
                except Exception:
                    pass
        else:
            # DC-vs-CSK Fix 6: pad with "?" for any missed deliveries
            # so a first-ball read failure followed by a clean second-
            # ball read renders as ["?", "4"] rather than ["4", "?"].
            # The expected position comes from the new card's overs
            # decimal (e.g. 1.2 → 2 legal balls completed); only legal
            # events advance position, so we pad legal-only.
            if event.get("legal", True):
                try:
                    new_overs = float(card.get("overs") or self.overs or 0)
                    expected_legal = round((new_overs % 1) * 10)
                    legal_so_far = sum(
                        1 for t in self.this_over
                        if t not in ("Wd", "Nb"))
                    if legal_so_far >= expected_legal and self.this_over:
                        _incoming = str(event.get("this_over_token", "?"))
                        _last_legal = next(
                            (t for t in reversed(self.this_over)
                             if t not in ("Wd", "Nb")), None)
                        if _last_legal == _incoming:
                            log.info(
                                f"[SM/THIS_OVER] dedup skip "
                                f"token={_incoming!r} "
                                f"legal_so_far={legal_so_far} "
                                f"expected={expected_legal} "
                                f"overs={new_overs}")
                            return
                    while legal_so_far + 1 < expected_legal:
                        self.this_over.append("?")
                        self.this_over_src.append("infer")
                        legal_so_far += 1
                except (TypeError, ValueError):
                    pass
            self.this_over.append(event.get("this_over_token", "?"))
            self.this_over_src.append("obs")
            self._rewrite_eyes_this_over_from_event(
                card, event.get("this_over_token", "?"))

        # --- Free Hit ---
        if self.free_hit_next and event.get("legal", True):
            event["is_free_hit"] = True
            self.free_hit_next = False
        else:
            event["is_free_hit"] = False
        if event.get("free_hit_next"):
            self.free_hit_next = True

        # --- Extras observability ---
        # Count any extra-style event (wide / no-ball / byes / leg-byes).
        # We use the over rollover side-effect (is_over_change) below to
        # zero this_over_extras, matching how this_over is reset.  This
        # gives the UI/parity-monitor a single source of truth for the
        # extras counter so we can see extras drift in real time.
        _etype = event.get("type")
        _etoken = event.get("this_over_token", "")
        if _etype in ("WIDE", "NO_BALL") or _etoken in ("Wd", "Nb",
                                                         "B", "LB"):
            _runs_on_extra = int(event.get("runs", 0) or 0)
            _ex = self._extras_writable()
            _ex["total"] = int(_ex.get("total", 0) or 0) + _runs_on_extra
            _ex["this_over"] = int(_ex.get("this_over", 0) or 0) + 1
            entry = {
                "over": self.overs,
                "type": _etype or "EXTRA",
                "token": _etoken,
                "runs": _runs_on_extra,
                "this_over_len_after": len(self.this_over),
            }
            _lg = _ex.setdefault("log", [])
            _lg.append(entry)
            if len(_lg) > 50:
                _ex["log"] = _lg[-50:]
            log.info(f"[SM/EXTRAS] +{_runs_on_extra} ({_etype}/"
                     f"{_etoken}) at {self.overs}o "
                     f"this_over_extras={self.this_over_extras} "
                     f"innings_extras={self.innings_extras} "
                     f"this_over_now={self.this_over}")

        # --- Strike Rotation ---
        # ABSORBED_LEGAL never reaches here (warm path uses
        # `_apply_absorbed_event`; D3 keeps striker fixed across the gap).
        if event.get("legal", True) and event.get("runs", 0) % 2 == 1:
            self.striker, self.non = self.non, self.striker
        if is_over_change:
            self.striker, self.non = self.non, self.striker

        # --- Fall of Wicket ---
        # Slot indexing: after _accept_update bumped self.wickets to N,
        # this dismissal is the N-th wicket and belongs at fow_list[N-1].
        # If a placeholder already sits in that slot (from cold-start
        # re-init padding), upgrade it.  If a CONFIRMED entry sits
        # there, refuse the rewrite — confirmed history is immutable.
        # Always-append (the previous behaviour) caused the duplicate
        # Buttler@95/9.1 entries observed on 2026-04-17.
        if event["type"] == "WICKET":
            self._apply_wicket_fall_only(event, frame)
        else:
            if not self.partnership_known:
                self.partnership_runs = 0
                self.partnership_balls = 0
                self.partnership_known = True
            _pship_runs_before = int(self.partnership_runs or 0)
            _pship_balls_before = int(self.partnership_balls or 0)
            self.partnership_runs += event.get("runs", 0)
            self.partnership_balls += 1 if event.get("legal", True) else 0
            if _trace is not None:
                try:
                    _trace.get_recorder().record(
                        tag="PARTNERSHIP-WRITE",
                        runs_before=_pship_runs_before,
                        balls_before=_pship_balls_before,
                        runs_after=int(self.partnership_runs or 0),
                        balls_after=int(self.partnership_balls or 0),
                        source="apply_event_normal",
                        frame_id=str(self._current_frame))
                except Exception:
                    pass

        # --- Delivery enrichment ---
        if frame.delivery_info:
            event["delivery"] = frame.delivery_info

    def _complete_over(self, prev: dict) -> None:
        """Archive current over when an over change is detected."""
        # A1 part 2: maiden detection + transient over-state reset.
        # Fires BEFORE archiving so the bowling_card transient counters
        # still reflect this over's deliveries.  A maiden is credited
        # only if the over completed (>= 6 legal balls) with zero
        # bowler-attributable runs (byes/leg-byes don't disqualify, but
        # they also aren't tracked here yet — out of scope this round).
        if self.scoreboard is not None and self.bowler_name:
            _bc = (self.scoreboard.bowling_card or {}).get(
                self.bowler_name)
            if _bc is not None:
                _bto = int(_bc.get("balls_this_over") or 0)
                _rto = int(_bc.get("runs_this_over") or 0)
                _byes_lb = int(_bc.get("byes_lb_this_over") or 0)
                # A2 part 2: bowler-runs-only maiden check.
                # runs_this_over is already excluded byes/lb (those
                # don't increment bowler.runs via _apply_bowler_delta),
                # so the subtraction here is documentation-only when
                # the byes/lb path is the canonical RUNS-extras
                # branch.  If the value isn't already exclusive
                # (e.g. a future change includes byes in
                # runs_this_over), the subtraction stays correct.
                _bowler_runs_this_over = max(0, _rto - _byes_lb)
                if _bto >= 6 and _bowler_runs_this_over == 0:
                    _bc["maidens"] = int(_bc.get("maidens") or 0) + 1
                    if _trace is not None:
                        try:
                            _trace.get_recorder().record(
                                tag="BOWLER-MAIDEN-CREDITED",
                                bowler=self.bowler_name,
                                over_index=int(prev.get("overs", 0) or 0),
                                bowler_runs_this_over=(
                                    _bowler_runs_this_over),
                                byes_lb_this_over=_byes_lb,
                                frame_id=str(self._current_frame))
                        except Exception:
                            pass
                _bc["balls_this_over"] = 0
                _bc["runs_this_over"] = 0
                _bc["byes_lb_this_over"] = 0
        self.completed_over = list(self.this_over)
        self.completed_over_runs = sum(
            int(t) for t in self.this_over if t.isdigit())
        _archive_over_n = int(prev.get("overs", 0) or 0)
        # B1.3 §2.6: defer archive if pending queue non-empty.
        if self._pending_ball_queue:
            self._emit_pending_trace(
                "OVER-ARCHIVE-DEFERRED-QUEUE-NONEMPTY",
                over_n=_archive_over_n,
                queue_depth=len(self._pending_ball_queue),
                source="sm_complete_over",
            )
            self._over_archive_pending = _archive_over_n
            self.this_over_extras = 0
            return
        _existing_archive = self.over_history.get(_archive_over_n)
        self.over_history[_archive_over_n] = list(
            self.this_over)
        if _trace is not None:
            try:
                _trace.get_recorder().record(
                    tag="OVER-ARCHIVE-WRITE",
                    over_n=_archive_over_n,
                    tokens=list(self.this_over),
                    token_count=len(self.this_over),
                    source="sm_complete_over")
                if (_existing_archive is not None
                        and list(_existing_archive) != list(self.this_over)):
                    _trace.get_recorder().record(
                        tag="OVER-ARCHIVE-DOUBLE-WRITE",
                        over_n=_archive_over_n,
                        existing_tokens=list(_existing_archive),
                        attempted_tokens=list(self.this_over),
                        source="sm_complete_over")
                if len(self.this_over) != 6:
                    _trace.get_recorder().record(
                        tag="OVER-ARCHIVE-INVALID-TOKEN-COUNT",
                        over_n=_archive_over_n,
                        token_count=len(self.this_over),
                        tokens=list(self.this_over))
            except Exception:
                pass
        # Reset per-over extras counter at over boundary (innings total
        # is preserved).  Logged so we can see the over close cleanly.
        if self.this_over_extras:
            log.info(f"[SM/EXTRAS] over {prev.get('overs','?')} closed "
                     f"with {self.this_over_extras} extra(s) — "
                     f"resetting per-over counter")
        self.this_over_extras = 0

    # A1 part 2: F381 backfill queue.  Wickets that fire with
    # ``bowler_name`` unset (between-overs gap) are buffered here and
    # credited to the next bowler that locks within
    # ``_PENDING_WICKET_MAX_FRAME_LAG`` frames.  Out-of-window entries
    # are dropped with a WICKET-ATTRIBUTION-ORPHANED trace.
    def _queue_pending_bowler_wicket(
            self, wkt_kind, dismissed) -> None:
        if not hasattr(self, "_pending_bowler_wickets"):
            self._pending_bowler_wickets = []
        entry = {
            "frame_id": int(self._current_frame or 0),
            "dismissal_type": wkt_kind,
            "dismissed_batter": dismissed,
        }
        self._pending_bowler_wickets.append(entry)
        if _trace is not None:
            try:
                _trace.get_recorder().record(
                    tag="WICKET-PENDING-BOWLER-ATTRIBUTION",
                    frame_id=str(self._current_frame),
                    dismissal_type=wkt_kind,
                    dismissed_batter=dismissed)
            except Exception:
                pass

    def _drain_pending_bowler_wickets(self, bowler_name: str) -> None:
        cur_frame = int(self._current_frame or 0)
        for e in list(self._pending_bowler_wickets):
            lag = cur_frame - int(e.get("frame_id") or 0)
            if lag <= _PENDING_WICKET_MAX_FRAME_LAG:
                if self.scoreboard is not None:
                    self.scoreboard.update_bowler(
                        bowler_name,
                        runs_delta=0,
                        balls_delta=0,
                        wickets_delta=1,
                        frame=cur_frame)
                if _trace is not None:
                    try:
                        _trace.get_recorder().record(
                            tag="WICKET-BACKFILLED-TO-BOWLER",
                            bowler=bowler_name,
                            dismissal_type=e.get("dismissal_type"),
                            dismissed_batter=e.get("dismissed_batter"),
                            frame_lag=lag,
                            frame_id=str(cur_frame))
                    except Exception:
                        pass
            else:
                if _trace is not None:
                    try:
                        _trace.get_recorder().record(
                            tag="WICKET-ATTRIBUTION-ORPHANED",
                            frame_id=str(e.get("frame_id")),
                            original_lag=lag,
                            dismissal_type=e.get("dismissal_type"))
                    except Exception:
                        pass
            self._pending_bowler_wickets.remove(e)

    # Symmetric runs/balls backfill queue (2026-05-19).
    # Structural analog to the F381 wicket-backfill pair above. When
    # `_accumulate_stats_from_event` skips a non-wicket bowler credit
    # because `bowler_name` is None (typical at over-handoff before
    # the new bowler appears in Scout reads), enqueue the runs/balls
    # delta here. When the bowler tracker LOCKs (`on_lock` callback
    # at test_pipeline.py:7198-7206 fires
    # `_drain_pending_bowler_ball_credits`) OR when the next ball
    # commit observes a fresh bowler (inline drain inside
    # `_accumulate_stats_from_event`), retroactively credit. Out-of-
    # window entries (>_PENDING_BOWLER_BALL_CREDIT_MAX_LAG frames)
    # are dropped with a PENDING-BOWLER-BALL-CREDIT-ORPHANED trace.
    #
    # Surfaced by L2-Slim captured-Scout replay frame 205 of
    # watch_20260519_121701: Sunil Narine's first ball of over 4
    # (the 3.1 ball event) committed with bowler_name=None
    # (parse_strip's bowler=None at that frame, Scout's strip had
    # only batter rows). The existing path silently emitted
    # CREDIT-SKIPPED-WITH-REASON: NO-BOWLER and walked away —
    # Narine's first-ball credit was permanently lost, leaving him
    # with 5 balls at over-end instead of 6.
    def _queue_pending_bowler_ball_credit(
            self, *,
            runs_delta: int, wickets_delta: int,
            event_overs: str | None, frame_id: int) -> None:
        if not hasattr(self, "_pending_bowler_ball_credits"):
            self._pending_bowler_ball_credits = []
        entry = {
            "frame_id": int(frame_id or 0),
            "runs_delta": int(runs_delta),
            "balls_delta": 1,
            "wickets_delta": int(wickets_delta),
            "event_overs": event_overs,
        }
        self._pending_bowler_ball_credits.append(entry)
        if _trace is not None:
            try:
                _trace.get_recorder().record(
                    tag="PENDING-BOWLER-BALL-CREDIT-QUEUED",
                    **entry)
            except Exception:
                pass

    def _drain_pending_bowler_ball_credits(
            self, bowler_name: str) -> None:
        if not getattr(self, "_pending_bowler_ball_credits", None):
            return
        cur_frame = int(self._current_frame or 0)
        for e in list(self._pending_bowler_ball_credits):
            lag = cur_frame - int(e.get("frame_id") or 0)
            if lag <= _PENDING_BOWLER_BALL_CREDIT_MAX_LAG:
                if self.scoreboard is not None:
                    self.scoreboard.update_bowler(
                        bowler_name,
                        runs_delta=e["runs_delta"],
                        balls_delta=e["balls_delta"],
                        wickets_delta=e["wickets_delta"],
                        frame=cur_frame)
                if _trace is not None:
                    try:
                        _trace.get_recorder().record(
                            tag="PENDING-BOWLER-BALL-CREDIT-BACKFILLED",
                            bowler=bowler_name,
                            runs_delta=e["runs_delta"],
                            balls_delta=e["balls_delta"],
                            wickets_delta=e["wickets_delta"],
                            event_overs=e.get("event_overs"),
                            frame_lag=lag,
                            frame_id=str(cur_frame))
                    except Exception:
                        pass
            else:
                if _trace is not None:
                    try:
                        _trace.get_recorder().record(
                            tag="PENDING-BOWLER-BALL-CREDIT-ORPHANED",
                            original_frame_id=str(e.get("frame_id")),
                            runs_delta=e["runs_delta"],
                            balls_delta=e["balls_delta"],
                            event_overs=e.get("event_overs"),
                            original_lag=lag)
                    except Exception:
                        pass
            self._pending_bowler_ball_credits.remove(e)

    # ------------------------------------------------------------------
    # Resolve pending ambiguities
    # ------------------------------------------------------------------

    def _try_resolve_pending(self, frame: FrameInput) -> dict | None:
        """Called every frame. Returns resolved event if any."""
        resolved_event = None

        # --- Extra: WIDE vs NO_BALL ---
        if self.pending_extra:
            resolved = False

            if frame.broadcast_extra == "WD":
                self.pending_extra["type"] = "WIDE"
                self.pending_extra["this_over_token"] = "Wd"
                self._fix_last_this_over_token("Wd")
                resolved = True
            elif frame.broadcast_extra == "NB":
                self.pending_extra["type"] = "NO_BALL"
                self.pending_extra["this_over_token"] = "Nb"
                self.free_hit_next = True
                self._fix_last_this_over_token("Nb")
                resolved = True

            if not resolved:
                text = (frame.scout_text or "").lower()
                if _matches_no_ball_signal(text):
                    self.pending_extra["type"] = "NO_BALL"
                    self.free_hit_next = True
                    self._fix_last_this_over_token("Nb")
                    resolved = True
                elif _matches_wide_signal(text):
                    self.pending_extra["type"] = "WIDE"
                    self._fix_last_this_over_token("Wd")
                    resolved = True

            if not resolved:
                self.pending_extra_frames += 1
                if self.pending_extra_frames >= 2:
                    self.pending_extra["type"] = "WIDE"
                    self._fix_last_this_over_token("Wd")
                    resolved = True

            if resolved:
                resolved_event = self.pending_extra
                self.pending_extra = None

        # --- Wicket: who was dismissed ---
        if self.pending_wicket:
            card = self._build_scorecard(frame)
            if card:
                curr = {n for n in [card.get("bat1_name"),
                                    card.get("bat2_name")] if n}
                prev_names = {n for n in [self.bat1_name, self.bat2_name] if n}
                departed = prev_names - curr
                # Same slot-diff reliability gate as `_infer_wicket`
                # (2026-05-19): require BOTH curr batter slots
                # filled before trusting departure inference. A
                # one-batter-visible frame is typically a graphic
                # overlay or transient camera angle, not a real
                # post-wicket strip.
                if len(curr) < 2:
                    departed = set()
                if departed:
                    _resolved_dismissed = departed.pop()
                    self.pending_wicket["dismissed"] = _resolved_dismissed
                    self.pending_wicket["needs_resolution"] = False
                    resolved_event = self.pending_wicket
                    if _trace is not None:
                        try:
                            _trace.get_recorder().record(
                                tag="WICKET-RESOLVED-FROM-PENDING",
                                dismissed=_resolved_dismissed,
                                pending_frames=int(
                                    self.pending_wicket_frames),
                                frame_id=str(
                                    getattr(frame, "frame_id", None)))
                        except Exception:
                            pass
                    # Commit the resolved wicket. Two commits needed:
                    # (1) _accumulate_stats_from_event handles the
                    #     stat-side updates — striker +1 ball faced,
                    #     bowler +1 ball + bowler-credited wicket
                    #     (line 4719+ WICKET branch).
                    # (2) _apply_wicket_fall_only handles the FOW
                    #     record + slot zeroing.
                    # The wickets COUNTER (self.wickets) was already
                    # mirrored from card.wickets via _accept_update
                    # at the original frame, so we don't double-
                    # increment. Without these commits, the
                    # resolved_event is returned to the caller but
                    # the on_frame path (line ~1430) only invokes
                    # `_build_payload` — never `_apply_event` — so
                    # the stat deltas + FOW + dismissed batter
                    # status all stay uncommitted.
                    try:
                        self._accumulate_stats_from_event(
                            resolved_event)
                    except Exception:
                        pass
                    try:
                        self._apply_wicket_fall_only(
                            resolved_event, frame)
                    except Exception:
                        pass
                    self.pending_wicket = None
                else:
                    self.pending_wicket_frames += 1
                    # 10-frame window — symmetric with the F381
                    # wicket-attribution lag (`_PENDING_WICKET_MAX_
                    # FRAME_LAG=10`) and calibrated against the same
                    # broadcast cadence that justified 5b25e59's
                    # bowler-credit threshold tune. Observed real
                    # wicket at 4.6 needed ~6 frames (frame 361 →
                    # 367) for dismissal text to appear cleanly in
                    # Scout; 10 frames covers that with margin.
                    if self.pending_wicket_frames >= 10:
                        if _trace is not None:
                            try:
                                _trace.get_recorder().record(
                                    tag="WICKET-PENDING-ABANDONED",
                                    pending_frames=int(
                                        self.pending_wicket_frames),
                                    pending_event=dict(
                                        self.pending_wicket),
                                    frame_id=str(
                                        getattr(
                                            frame, "frame_id", None)))
                            except Exception:
                                pass
                        self.pending_wicket = None

        return resolved_event

    def _fix_last_this_over_token(self, token: str) -> None:
        if self.this_over:
            self.this_over[-1] = token

    # ------------------------------------------------------------------
    # Computed fields
    # ------------------------------------------------------------------

    def _recompute(self) -> None:
        if self.score is not None and self.overs and self.overs > 0:
            total_balls = (int(self.overs) * 6
                           + round((self.overs % 1) * 10))
            self.run_rate = (round(self.score / total_balls * 6, 2)
                             if total_balls > 0 else 0)

        if self.target and self.score is not None and self.overs:
            balls_left = 120 - (int(self.overs) * 6
                                + round((self.overs % 1) * 10))
            self.balls_remaining = max(balls_left, 0)
            runs_left = self.target - self.score
            self.required_run_rate = (
                round(runs_left / balls_left * 6, 2) if balls_left > 0
                else 999)

        if self.overs is not None:
            o = int(self.overs)
            if o < 6:
                self.match_phase = "powerplay"
            elif o < 15:
                self.match_phase = "middle"
            else:
                self.match_phase = "death"

        if (self.bat1_runs is not None and self.bat1_balls
                and self.bat1_balls > 0):
            self.bat1_sr = round(self.bat1_runs / self.bat1_balls * 100, 2)
        if (self.bat2_runs is not None and self.bat2_balls
                and self.bat2_balls > 0):
            self.bat2_sr = round(self.bat2_runs / self.bat2_balls * 100, 2)
        # Cross-field invariant (Bug-fix): when team overs are at a
        # whole boundary (X.0), the current bowler's overs must also
        # end on .0 — they bowled the closing ball of the over (no
        # mid-over bowler changes in T20). Snap forward if Extractor /
        # Scorer briefly lagged on the closing ball.
        if (self.overs is not None and self.bowler_overs is not None):
            try:
                t_balls = (int(self.overs) * 6
                           + round((self.overs % 1) * 10))
                b_balls = (int(self.bowler_overs) * 6
                           + round((self.bowler_overs % 1) * 10))
            except (ValueError, TypeError):
                t_balls = b_balls = 0
            if t_balls > 0 and t_balls % 6 == 0 and b_balls % 6 != 0:
                snapped = ((b_balls // 6) + 1) * 6
                if snapped <= t_balls:
                    snapped_overs = float(f"{snapped // 6}.{snapped % 6}")
                    if snapped_overs != self.bowler_overs:
                        bn = self.bowler_name
                        if (self.scoreboard is not None and bn
                                and not self.shadow):
                            try:
                                self.scoreboard.update_bowler(
                                    bn, overs=str(snapped_overs),
                                    frame=self._current_frame)
                            except Exception:
                                pass
                            log.info(
                                "  [SM-FEEDER-SYNC] field=bowler_overs "
                                f"value={snapped_overs} "
                                "sb_accepted=true note=spell_snap")

        if (self.bowler_runs is not None and self.bowler_overs
                and self.bowler_overs > 0):
            bb = (int(self.bowler_overs) * 6
                  + round((self.bowler_overs % 1) * 10))
            self.bowler_economy = (round(self.bowler_runs / bb * 6, 2)
                                   if bb > 0 else 0)

    # ------------------------------------------------------------------
    # Build payload (single source for UI + logging)
    # ------------------------------------------------------------------

    def _build_payload(self, event: dict | None = None,
                       *,
                       ball_events: list[dict] | None = None) -> dict:
        # Issue 1 defense-in-depth (2026-04-21): even though
        # _build_scorecard canonicalizes at ingest, a stale raw name
        # could linger in self.striker across a state transition where
        # the ingest path wasn't hit (e.g. payload built from a pending
        # retry without a fresh frame).  Canonicalize at the output so
        # the WS payload is always consistent with batting_card keys.
        if ball_events is not None:
            be = ball_events
        elif event is not None:
            be = [event]
        else:
            be = []
        last_ev = be[-1] if be else None
        _striker_out = (self._canonicalize_name(self.striker)
                        or self.striker)
        _non_out = (self._canonicalize_name(self.non)
                            or self.non)
        _bat1_out = (self._canonicalize_name(self.bat1_name)
                     or self.bat1_name)
        _bat2_out = (self._canonicalize_name(self.bat2_name)
                     or self.bat2_name)
        _bowler_out = (self._canonicalize_name(self.bowler_name, "bowler")
                       or self.bowler_name)
        return {
            "type": "state_update",
            "source": "score_manager",
            "scorecard": {
                "score": self.score,
                "wickets": self.wickets,
                "overs": self.overs,
                "batting_team": self.batting_team,
                "run_rate": self.run_rate,
                "striker": _striker_out,
                "non": _non_out,
                "bat1": {
                    "name": _bat1_out, "runs": self.bat1_runs,
                    "balls": self.bat1_balls, "sr": self.bat1_sr,
                },
                "bat2": {
                    "name": _bat2_out, "runs": self.bat2_runs,
                    "balls": self.bat2_balls, "sr": self.bat2_sr,
                },
                "bowler": {
                    "name": _bowler_out,
                    "wickets": self.bowler_wickets,
                    "runs": self.bowler_runs,
                    "overs": self.bowler_overs,
                    "economy": self.bowler_economy,
                },
                "partnership": {
                    "runs": (self.partnership_runs
                             if self.partnership_known else None),
                    "balls": (self.partnership_balls
                              if self.partnership_known else None),
                },
            },
            "match": {
                "target": self.target,
                "runs_required": ((self.target - self.score)
                                  if self.target and self.score is not None
                                  else None),
                "balls_remaining": self.balls_remaining,
                "required_rate": self.required_run_rate,
                "innings": self.innings,
                "phase": self.match_phase,
                "venue": self.venue,
                "match_info": self.match_info,
            },
            "this_over": self.this_over,
            "over_history": self.over_history,
            "completed_over": self.completed_over,
            "completed_over_runs": self.completed_over_runs,
            "fow_count": len(self.fow_list),
            "fow_list": self.fow_list,
            "extras": {
                "innings_total": self.innings_extras,
                "this_over": self.this_over_extras,
                "log_tail": self.extras_log[-5:],
            },
            "free_hit": self.free_hit_next,
            "speed_kph": (self.last_speed
                          if self.last_speed_at_over == self.overs
                          else None),
            "speed_kph_at_over": self.last_speed_at_over,
            "ball_event": last_ev,
            "ball_events": be,
            "pending": {
                "extra_type": self.pending_extra is not None,
                "dismissed": self.pending_wicket is not None,
            },
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _same_name(a: str | None, b: str | None) -> bool:
        if not a or not b:
            return False
        return a.lower() in b.lower() or b.lower() in a.lower()
