"""Scoreboard — pre-built scorecards with null stats.

Squads are known before the first ball. Batting and bowling cards
are pre-built with all 11 players. Stats start at null (hasn't
batted/bowled yet). The match is about filling in the blanks.

Hard limits only: negative scores, overs > 20, wickets > 10.
"""
from __future__ import annotations

import os
import time
from copy import deepcopy
from difflib import SequenceMatcher

from eyes.consistent_tracker import ConsistentReadTracker
from eyes.cricket_logger import CricketLogger

try:
    import trace_emitter as _trace
except ImportError:
    _trace = None

log = CricketLogger("BOARD")

T20_MAX_OVERS = 20


class LiveMatchTracker:
    """Physics-based bounding for live cricket match data.

    Between consecutive frames in a live broadcast:
    - Max 1 ball per ~15s, pipeline captures every ~4s
    - Max 7 runs per ball (6 + no-ball)
    - Max 1 wicket per ball
    - Overs advance by at most 0.1 per ball

    After ad breaks (missed frames), allow slightly larger jumps.
    """

    WARMUP_FRAMES = 5  # first N scoreboard frames: allow large corrections

    def __init__(self):
        self.score: int | None = None
        self.wickets: int | None = None
        self.overs_balls: int | None = None  # stored as total balls
        self.frames_since_scoreboard: int = 0
        self._active_mmb: int = 1
        self._scoreboard_count: int = 0
        self.batters: dict[str, dict] = {}   # name -> {runs, balls}
        self.bowlers: dict[str, dict] = {}   # name -> {runs, wickets, overs_balls}

    def _max_missed_balls(self) -> int:
        """Return cached mmb for the current scoreboard frame's update window."""
        return self._active_mmb

    def on_non_scoreboard_frame(self):
        self.frames_since_scoreboard += 1

    def on_scoreboard_frame(self):
        self._scoreboard_count += 1
        if self._scoreboard_count <= self.WARMUP_FRAMES:
            self._active_mmb = 120  # accept anything during warmup
        else:
            self._active_mmb = max(1, self.frames_since_scoreboard // 3)
        self.frames_since_scoreboard = 0
        return self._active_mmb

    def update_score(self, new_score: int | None) -> int | None:
        if new_score is None:
            return self.score
        if self.score is None:
            self.score = new_score
            return new_score
        mmb = self._max_missed_balls()
        delta = new_score - self.score
        max_jump = 7 * mmb
        if delta < 0:
            return self.score  # reject decrease
        if delta > max_jump:
            return self.score  # reject contamination
        self.score = new_score
        return new_score

    def update_wickets(self, new_w: int | None) -> int | None:
        if new_w is None:
            return self.wickets
        if self.wickets is None:
            self.wickets = new_w
            return new_w
        mmb = self._max_missed_balls()
        delta = new_w - self.wickets
        if delta < 0:
            return self.wickets
        if delta > mmb:
            return self.wickets
        self.wickets = new_w
        return new_w

    def update_overs(self, new_overs_balls: int | None) -> int | None:
        if new_overs_balls is None:
            return self.overs_balls
        if self.overs_balls is None:
            self.overs_balls = new_overs_balls
            return new_overs_balls
        mmb = self._max_missed_balls()
        delta = new_overs_balls - self.overs_balls
        if delta < 0:
            return self.overs_balls
        if delta > mmb:
            return self.overs_balls
        self.overs_balls = new_overs_balls
        return new_overs_balls

    def update_batter(self, name: str, new_runs: int | None,
                      new_balls: int | None) -> tuple[int | None, int | None]:
        existing = self.batters.get(name)
        if not existing:
            self.batters[name] = {"runs": new_runs, "balls": new_balls}
            return new_runs, new_balls
        old_r = existing.get("runs") or 0
        old_b = existing.get("balls") or 0
        if new_runs is None:
            new_runs = old_r
        if new_balls is None:
            new_balls = old_b
        mmb = self._max_missed_balls()
        max_balls_inc = max(1, mmb)
        max_runs_inc = 6 * max_balls_inc
        r_delta = new_runs - old_r
        b_delta = new_balls - old_b
        if r_delta < 0 or r_delta > max_runs_inc:
            new_runs = old_r
        if b_delta < 0 or b_delta > max_balls_inc:
            new_balls = old_b
        # Also: batter runs can't exceed team score
        if self.score is not None and new_runs > self.score:
            new_runs = old_r
        existing["runs"] = new_runs
        existing["balls"] = new_balls
        return new_runs, new_balls

    def update_bowler(self, name: str, new_runs: int | None,
                      new_wickets: int | None,
                      new_overs_balls: int | None) -> tuple:
        existing = self.bowlers.get(name)
        if not existing:
            self.bowlers[name] = {
                "runs": new_runs, "wickets": new_wickets,
                "overs_balls": new_overs_balls,
            }
            return new_runs, new_wickets, new_overs_balls
        old_r = existing.get("runs") or 0

        # First non-zero reading — accept unconditionally
        # (bowler may have been bowling before we joined)
        if old_r == 0 and new_runs is not None and new_runs > 0:
            existing["runs"] = new_runs
            existing["wickets"] = new_wickets
            existing["overs_balls"] = new_overs_balls
            return new_runs, new_wickets, new_overs_balls

        mmb = self._max_missed_balls()
        max_r_inc = 7 * mmb
        if new_runs is not None:
            r_delta = new_runs - old_r
            if r_delta < 0 or r_delta > max_r_inc:
                new_runs = old_r
            if self.score is not None and new_runs > self.score:
                new_runs = old_r
        else:
            new_runs = old_r
        existing["runs"] = new_runs
        existing["wickets"] = new_wickets
        existing["overs_balls"] = new_overs_balls
        return new_runs, new_wickets, new_overs_balls

    def reset(self):
        self.score = None
        self.wickets = None
        self.overs_balls = None
        self.frames_since_scoreboard = 0
        self._active_mmb = 1
        self._scoreboard_count = 0
        self.batters = {}
        self.bowlers = {}


class Scoreboard:
    """Pre-built scorecards. Squads loaded before first ball."""

    def __init__(self):
        self.match_format = "T20"
        self.batting_team: str | None = None
        self.bowling_team: str | None = None
        self.current_innings = 1
        # Match terminal state (set once innings-2 physics resolve).
        # `match_end_reason` ∈ {"target_reached", "all_out",
        # "overs_exhausted"}. `match_result` is a computed dict with
        # winner / margin / remaining-balls for UI rendering.
        self.match_complete: bool = False
        self.match_end_reason: str | None = None
        self.match_result: dict | None = None

        self.batting_card: dict[str, dict] = {}
        self.bowling_card: dict[str, dict] = {}
        self._name_lookup: dict[str, str] = {}
        self._squad_roles: dict[str, str] = {}
        # name -> {"batting_style": "RHB"|"LHB"|"unknown",
        #          "bowling_style": "Right-arm fast"|"None"|"unknown"}
        # Populated pre-first-ball by player_enrichment.py and merged
        # into every batting_card / bowling_card entry.
        self._player_styles: dict[str, dict] = {}
        self._dismissed_inferred = False

        self.innings: dict[int, dict] = {1: self._blank(), 2: self._blank()}
        self.fall_of_wickets: list[dict] = []
        self.partnerships: list[dict] = []
        self.current_partnership: dict | None = None

        self._update_history: list[dict] = []

        self._tracker = ConsistentReadTracker()
        self._dismissed_recovery: dict[str, int] = {}
        self._dismiss_attempt_count: dict[str, int] = {}
        self._extractor_batter_names: set[str] = set()

        # Optional callback wired by the test_pipeline main loop after
        # both Scoreboard and ThisOverManager are constructed.  Fired
        # whenever `_add_fow` upgrades a placeholder W{n} entry to a
        # real wicket with concrete `overs="X.Y"` — gives the over
        # manager the chance to reorder its `this_over` token list
        # so the W token sits at the correct legal-ball position.
        # See `OverManager.reorder_wicket_to_ball` and the RR-vs-SRH
        # 2026-04-25 inn-2 over-0 trace in `docs/backlog.md`.
        # `None` keeps existing tests / call sites unaffected (no-op
        # when no consumer is wired).
        self.on_fow_upgrade: callable | None = None

        self.extras: dict[str, int] = self._blank_extras()
        self.this_over: list[str] = []
        self.over_history: dict[int, list[str]] = {}
        self.bowler_speeds: dict[str, list[float]] = {}
        self.bowler_type: dict[str, str] = {}
        self._last_over_num: int | None = None
        self._bowler_must_change: bool = False
        self._prev_over_bowler: str | None = None
        self._bowler_locked: bool = False
        self._bowler_lock_frame: int = 0
        # Bowler 3-frame consensus (broadcast-authoritative override).
        # When the same bowler name is read on N consecutive
        # SCOREBOARD frames we flip current_bowler unconditionally,
        # bypassing inference and stale state.
        self._pending_bowler_name: str | None = None
        # Fix #2 (2026-04-22): recoverable same-bowler regression.
        # When the same bowler is read with identical lower figures
        # N times in a row, we treat the previously recorded higher
        # figures as a corrupted lock and allow the override. Keyed
        # by canonical bowler name; value = (proposed_figures_tuple,
        # count). Gets reset on any non-regression / different bowler.
        self._bowler_regress_pending: dict[str, tuple[tuple, int]] = {}
        self._BOWLER_REGRESS_OVERRIDE_N = 5
        # Fix #3 (2026-04-23): rotation-guard override threshold.
        # N consecutive rejections of the same bowler name means our
        # _prev_over_bowler record is wrong — accept and clear.
        self._ROTATION_OVERRIDE_N = 3
        self._pending_bowler_count: int = 0
        # Fix 17B extension (2026-04-28): plain N-frame consensus must not
        # flip current_bowler when the candidate's spell ball-in-over disagrees
        # with the team strip (stale cumulative / wrong-bowler graphic).
        self._bowler_consensus_inconsistent_streak: dict[str, int] = {}
        self._BOWLER_CONSENSUS_OVERS_OVERRIDE_N = 3
        # BOWLER-OVERRIDE consensus floor (investigation 5, 2026-05-14).
        # Even with must_change=True (over-rollover), require ≥2 reads of
        # the candidate name before flipping current_bowler — a single VLM
        # read of a prior-over bowler's name (e.g. mid-cycle stats panel
        # showing his over-1 figures) was enough to falsely flip and
        # cascade into BOWLER-AUTO mis-attribution.  When the leader is
        # well-established (≥0.3 overs of accumulated stats), require 3
        # reads.  must_change=True provides a 1-frame credit, but the
        # floor of 2 always holds — single-read flips never fire.
        self._BOWLER_OVERRIDE_CONSENSUS_FRAMES = 2
        self._BOWLER_OVERRIDE_CONSENSUS_FRAMES_HIGH_WEIGHT = 3
        self._BOWLER_OVERRIDE_HIGH_WEIGHT_BALL_THRESHOLD = 3  # 3 legal balls
        # BOWLER-AUTO attribution freeze (investigation 5 companion).
        # When an override is pending (a candidate is accumulating reads
        # but consensus hasn't fired), buffer team-score deltas instead
        # of crediting the now-uncertain current bowler.  On resolution
        # (consensus fires or dissipates) the buffer is flushed to the
        # resolved bowler.  Prevents the boundary at F201 (+4 runs)
        # from being credited to Anukul Roy while the override to
        # Anukul was still 1-of-2-frames pending.
        self._bowler_attribution_freeze_runs: int = 0
        # Batter-balls per-frame tracking (investigation 8, 2026-05-14).
        # The striker tracker can oscillate within a single frame,
        # incrementing both batters' balls counts and inflating one
        # batter's total far above their broadcast count.  Track which
        # batters had their balls field bumped this frame and suppress
        # any subsequent bump beyond the first (cricket physics: one
        # delivery, one ball, one striker).
        self._batter_balls_frame: int = -1
        self._batter_balls_incremented_this_frame: set[str] = set()
        # Frame of the most recent whole-row rejection (CLONE-REJECT or
        # balls-regression-too-deep).  The main loop reads this to
        # suppress broadcast-indicator striker updates on the same
        # frame, since the asterisk/row-order read from the strip
        # string is untrustworthy when we've just rejected its stats.
        # (Issue 5 fix, 2026-04-21.)
        self._last_row_rejected_frame: int = -1
        # Wickets regression consensus. When the broadcast consistently
        # reads FEWER wickets than our current state for N frames in
        # a row, accept the regression — our pipeline almost certainly
        # over-counted (false-positive wicket detection from a misread).
        # Cricket invariant: wickets only DECREASE on innings change,
        # but our state can be CORRUPTED upward by hallucinated +1
        # ticks. The only authoritative source is the strip itself;
        # if it disagrees with us for several frames it's right.
        self._pending_wickets_low: int | None = None
        self._pending_wickets_low_count: int = 0
        self._all_out_lock: bool = False
        self._all_out_lock_frame: int = 0
        self._all_out_lock_source: str | None = None
        # Wickets upward-jump consensus. Symmetric to the regression
        # path: when the broadcast consistently shows a value MORE THAN
        # +1 above our current counter for N frames in a row, trust it.
        # This is the only recovery path from cold-start over-lock — if
        # the pipeline attached during a pre-match ad where the strip
        # reads "0-0" and the consistent-tracker committed wickets=0,
        # the real match score (e.g. 10-2) would otherwise be rejected
        # indefinitely by the per-frame +1 cap. 3-frame consensus means
        # ~8-10 s of steady broadcast agreement before we jump.
        self._pending_wickets_high: int | None = None
        self._pending_wickets_high_count: int = 0
        # Layer 4 / Fix 12 (2026-04-26): rejection-consensus release
        # for the runs-monotonic guard.  Mirrors the POISON-STREAK
        # template (5-frame consensus → force-set baseline) at the
        # per-batter runs level.  When a Scout-proposed runs value
        # is rejected by either of the regression clauses below
        # (`runs == 0 with cur > 5`, or `cur − new > 5`) and the
        # SAME proposed value re-appears N times consecutively for
        # the same batter, the current value is almost certainly a
        # stale phantom and the rejected proposal is truth.  Force-
        # set the runs baseline to release the lock-in.
        #
        # Production grounding (2026-04-26 CSK-vs-GT, Dube case):
        # 357 rejections of runs=22 across F1767-F1812 (41:50 wall-
        # clock window) with zero release events under the
        # detection-only guard.  POISON-STREAK released a comparable
        # over-stuck window in 90s with the same 5-frame threshold.
        # Same architectural template, applied to a different guard.
        # Field-specific by design: only the runs counter is force-
        # set; the rejected balls value (captured pre-null) is also
        # force-set if present, so the truth row commits whole.  We
        # do NOT extend release semantics to the CLONE-REJECT or
        # balls-regression-too-deep clauses (different rejection
        # semantics — those are not "rejecting the same truth value
        # repeatedly" patterns).  See backlog "Layer 4" entry.
        self._RUNS_REJECT_RELEASE_N: int = 5
        self._runs_reject_streak: dict[str, dict] = {}
        # Fix 18 (Layer 2 + Layer 3, 2026-04-26):
        # Layer 2 (bat-runs reconciler detection): post-commit
        # diagnostic firing whenever `bat_sum > score + 5` (less
        # aggressive than the existing +10 cap-reset threshold).
        # Layer 3 (capping-batters reset Path C hybrid): when the
        # +10 cap warning fires, reset the batter whose `runs`
        # most recently advanced — that's the most likely phantom
        # culprit (the broken `if runs > score` per-batter check
        # only worked when a single batter held the entire phantom
        # inflation; with split-phantom cases like Brevis 1+ Dube
        # 22, neither individually exceeds score, so no reset
        # fired).  Iterative: after the first reset, the cap is
        # re-evaluated; if still over, reset the next-most-recent
        # advance.  Both layers share the `_last_runs_advance`
        # tracking dict.
        self._last_runs_advance: dict[str, dict] = {}
        self._fresh_batter_admission: dict[str, dict] = {}
        # Per-frame tally of bat-sum-reconciler fires for the
        # analyzer / parity monitor to count.
        self._L2_RECONCILER_THRESHOLD: int = 5
        self._L3_CAP_RESET_THRESHOLD: int = 10
        # Fix #1 (2026-04-23): wicket-seed gate state.
        # The cold-start auto-dismiss seed originally fired on any
        # old==0 → value>0 transition, which silently pre-armed the
        # gate the first time a REAL wicket was taken during a live
        # restart — blocking the actual dismissal from ever firing
        # (observed on Sarfaraz, MI vs CSK 2026-04-23).
        # Fix: only seed when wickets were never confirmed (old is
        # None).  Once we've seen wickets=0 confirmed on >=2 frames,
        # a 0→1 transition is a real event and must NOT seed.
        # Counter resets on innings transitions (see set_innings_2
        # / start_new_innings).
        self._wickets_confirmed_frames_at_zero: int = 0
        # Fix #3 (2026-04-23): rotation-guard override state.
        # Tracks consecutive rotation-rejection count per bowler.
        # After _ROTATION_OVERRIDE_N consistent rejections for the
        # same bowler name, our _prev_over_bowler record is almost
        # certainly wrong (we mis-labelled the previous over); accept
        # the read and clear the lockout.  Mirrors the same recoverable
        # pattern as _BOWLER_REGRESS_OVERRIDE_N.
        self._rotation_rejection_count: dict[str, int] = {}
        # Fix #2 (2026-04-23): BOWLER-AUTO / Scout race state.
        # Frame of the most recent update_bowler() call — proxy for
        # "Scout is actively reading the bowler strip in this window".
        # When BOWLER-AUTO about to fire within 2 frames of a Scout
        # bowler read, defer — Scout's read will supply the
        # authoritative figures, and auto-increment would otherwise
        # race ahead and trigger spurious [BOWLER-STALE] rejections.
        self._last_bowler_scout_frame: int = -1000
        # BOWLER-STALE freshness disambiguator (2026-04-25 RR-vs-SRH
        # fix).  The same-figures stale-graphic defense in
        # update_bowler() (see ~L2060) rejects a proposed identity
        # change when the proposed figures exactly match what's
        # already recorded for that name.  Pre-fix the gate had no
        # way to distinguish a fresh between-ball repeat read of a
        # new bowler (recorded values were just written 1-N frames
        # ago by THIS spell) from a genuine end-of-spell stale
        # graphic (recorded values were written long ago and the
        # graphic is now resurfacing).  The trap: a new bowler's
        # first read populates the card; every subsequent identical
        # read is rejected; 3-frame consensus never accumulates;
        # current_bowler never flips.  Production damage 2026-04-25:
        # 54+ rejects across 4 bowlers in match-2 innings 1, with
        # those bowlers' deliveries inflating the still-current
        # bowler's stats via BOWLER-AUTO (team-score → bowler-stats
        # mirror, which targets `current_bowler`).
        #
        # Disambiguator: stamp every active card-write with (a) the
        # frame at which it happened, and (b) which bowler was
        # `current_bowler` at that instant.  The same-figures
        # rejection is suppressed when BOTH last-write was within
        # `_BOWLER_STALE_FRESH_FRAMES` AND `current_bowler` hasn't
        # changed since that write — that's the "between deliveries
        # of a bowler trying to take over" case.  When the bowler
        # context HAS changed since the recorded write, the original
        # stale-graphic defense fires unchanged: matching figures on
        # a name we recorded under a different `current_bowler`
        # context IS the stale-graphic signature.
        #
        # Threshold rationale: 180 frames (~9 s @ 20 fps).
        # Empirical match-2 inter-ball BOARD-write median was 14
        # frames, p95 207 frames; the bowler-context disambiguator
        # carries the actual semantic separation, so the freshness
        # window can be permissive without weakening genuine-stale
        # rejection.
        self._bowling_card_active_write_frame: dict[str, int] = {}
        self._bowling_card_active_write_bowler: dict[str, str | None] = {}
        self._BOWLER_STALE_FRESH_FRAMES = 180
        # P0-2 (2026-04-22): XI-REJECT override state.
        # When Scout consistently reads the same bench/reserve name as
        # the current bowler across N reads, our squad scrape was almost
        # certainly pre-XI-finalization and the player was actually
        # named to the XI. Accept the read and flip is_playing_xi=True
        # on the card.
        #
        # Gate-1 (total consistency): >= _XI_OVERRIDE_N total rejections
        # Gate-2 (action-phase): >= _XI_OVERRIDE_ACTION_N of those
        #   rejections must have occurred while Scout's latest camera_view
        #   tag was "bowlers_end" — rejecting rejections seen only during
        #   stats-graphics slices reduces the chance of promoting a
        #   genuinely-benched player whose headshot appears on a
        #   career-averages overlay.
        #
        # Stored value: list of camera_view strings captured at each
        # rejection moment, so we can re-evaluate the gate each time a
        # new rejection lands without re-deriving history.
        self._XI_OVERRIDE_N = 3
        self._XI_OVERRIDE_ACTION_N = 2
        self._xi_rejection_views: dict[str, list[str | None]] = {}
        # Latest camera_view tag from Scout — set by on_camera_view()
        # from the main pipeline after every Scout tag emission.
        # Feeds the P0-2 override gate; None when unknown.
        self._last_scout_camera_view: str | None = None
        # P11 (2026-05-03): XI + subs + impact substitution (per team key).
        # TODO: enforce max 4 overseas on field (needs passport metadata).
        self._team_match_membership: dict[str, dict] = {}
        self._impact_promote_streak: dict[tuple[str, str], int] = {}
        self._impact_promote_last_frame: dict[tuple[str, str], int] = {}
        self._batter_slot_last_identity: dict[str, str] = {}

    # Bowler career / phase stats overlays (2026-04-28): Scout sometimes
    # OCRs aggregate figures as if they were the live spell.  Strong
    # multi-word phrases are rejected without requiring implausible
    # numbers; bare "CAREER" in vision is ignored unless spell figures
    # are already physically impossible (so commentary noise doesn't
    # block legitimate reads).  Complements Fix 8 INFO-PANEL stripping
    # in test_pipeline (strip-level) — this guard runs at commit time
    # inside Scoreboard with vision_desc from the same frame.
    _BOWLER_STATS_GRAPHIC_STRONG_PHRASES: tuple[str, ...] = (
        "IN T20", "IN T20IS", "IN IPL", "IN ODI", "ALL FORMATS",
        "IPL CAREER", "T20 CAREER",
        "OVERS 1-6", "OVERS 7-15", "OVERS 16-20",
        "POWERPLAY", "DEATH OVERS",
    )

    @staticmethod
    def _bowler_stats_graphic_implausible_spell(
            runs: int | None, wickets: int | None,
            overs: str | None) -> bool:
        """True if figures cannot describe a single T20 IPL spell."""
        if wickets is not None:
            try:
                if int(wickets) > 10:
                    return True
            except (TypeError, ValueError):
                pass
        if runs is not None:
            try:
                if int(runs) > 80:
                    return True
            except (TypeError, ValueError):
                pass
        if overs is not None:
            try:
                if float(overs) > 4.0:
                    return True
            except (TypeError, ValueError):
                pass
        return False

    def _bowler_stats_graphic_strong_keyword(self, vision_desc: str) -> bool:
        upper = vision_desc.upper()
        return any(kw in upper for kw in self._BOWLER_STATS_GRAPHIC_STRONG_PHRASES)

    def on_camera_view(self, view: str | None) -> None:
        """Record Scout's latest camera_view tag.

        Called from the main pipeline right after a Scout tag fires.
        Used by the P0-2 XI-REJECT override gate to distinguish
        stats-graphics rejections (bench player name on a career-
        averages overlay) from live-action rejections (bench player
        genuinely appearing on-screen as an active bowler, which
        indicates the squad scrape was pre-XI-finalization).
        """
        self._last_scout_camera_view = view

    @staticmethod
    def _blank() -> dict:
        return {
            "score": None,
            "wickets": None,
            "overs": None,
            "run_rate": None,
            "target": None,
            "extras": 0,
        }

    @staticmethod
    def _blank_extras() -> dict:
        return {
            "wides": 0, "no_balls": 0, "byes": 0,
            "leg_byes": 0, "penalties": 0, "total": 0,
            # Per-over counter (zero on over rollover) — surfaces in
            # the UI / parity monitor for live drift detection.
            "this_over": 0,
            # Bounded chronological log of recent extras for diagnostics
            # (matches Cricbuzz's "Wd / Nb" detail row).
            "log": [],
        }

    @property
    def _inn(self) -> dict:
        return self.innings[self.current_innings]

    def set_innings_2(self, target: int | None = None):
        """Switch to innings 2 with full state reset.

        Resets all CV trackers, batter/bowler trackers, extras,
        this-over, etc. Does NOT touch teams or cards — the caller
        must call setup_innings() / assign_teams() to set the
        correct batting/bowling sides and rebuild cards.

        Bug #14: idempotent. Previously this method early-returned if
        `current_innings` was already 2, which meant any caller who
        had set `current_innings = 2` directly (e.g. via assign_teams
        or a broadcast target detection) bypassed every reset below.
        Result: innings 1's fall_of_wickets, extras, this_over etc.
        leaked into innings 2.
        New behaviour: a one-shot guard `_innings2_reset_done` ensures
        the resets run exactly once per actual innings transition,
        regardless of which call path got there first. Subsequent
        invocations are no-ops (except for refreshing `target`).
        """
        # Match-complete guard (Fix B, 2026-04-22): once innings 2 has
        # terminated on physics conditions (target/all_out/overs),
        # refuse any further innings transitions. This prevents a
        # spurious target-re-detection frame from re-entering the
        # innings-2 reset path and clearing terminal result data.
        if self.match_complete:
            log.info(
                f"[MATCH-COMPLETE] set_innings_2 refused — match "
                f"already resolved ({self.match_end_reason}).")
            return

        if target:
            self._inn["target"] = target

        if getattr(self, "_innings2_reset_done", False):
            return

        self._innings2_reset_done = True

        self.innings[2] = self._blank()
        self.current_innings = 2
        if target:
            self._inn["target"] = target

        self._tracker = ConsistentReadTracker()
        self._dismissed_recovery = {}
        self._dismiss_attempt_count = {}
        self._extractor_batter_names = set()
        # Gate for _auto_dismiss_for_new_batter (Issue D, 2026-04-21):
        # wickets-counter value at which we last fired an auto-dismiss.
        # Auto-dismiss is blocked until the counter advances beyond
        # this, which guarantees at least one real wicket event has
        # occurred since the last phantom-batter proposal.
        self._last_autodismiss_wickets = 0
        # Fix #1 (2026-04-23): new innings starts at wickets=0 with
        # no prior confirmations — reset the zero-streak counter so
        # the seed rearms correctly for the innings-2 cold start.
        self._wickets_confirmed_frames_at_zero = 0
        # Fix #3 (2026-04-23): fresh innings ⇒ rotation state is
        # irrelevant; clear any pending rejection counters.
        self._rotation_rejection_count = {}
        # Per-batter streak of "missing from extractor" frames; used
        # to require at least 2 consecutive misses before believing a
        # dismissal signal.
        self._missing_batter_streak: dict[str, int] = {}
        # Fix C (#28): incoming-batter consensus streak — clear on innings
        # transition so a deferred-incoming candidate doesn't leak across.
        self._incoming_streak: dict[str, int] = {}
        # Layer 4 (Fix 12): clear runs-rejection-streak state so an
        # innings-1 stuck-window doesn't leak into innings-2 (different
        # batter pool, different name keys, but defensive hygiene).
        self._runs_reject_streak = {}
        self._impact_promote_streak = {}
        self._impact_promote_last_frame = {}
        self._batter_slot_last_identity = {}
        # Fix 18 (2026-04-26): innings hygiene for Layer 3 cap-
        # reset tracking.  Different batters in innings 2 must
        # not inherit innings-1 advance frames.
        self._last_runs_advance = {}
        self.extras = self._blank_extras()
        self.this_over = []
        self.over_history = {}
        self.bowler_speeds = {}
        self._last_over_num = None
        self._bowler_must_change = False
        self._prev_over_bowler = None
        self._bowler_locked = False
        self._bowler_lock_frame = 0
        self.fall_of_wickets = []
        self.partnerships = []
        self.current_partnership = None
        self._dismissed_inferred = False

        log.info(f"[INNINGS] Set to 2. Target: {target}. "
                 f"All trackers reset.")

    # ------------------------------------------------------------------
    # Match-complete (Fix B, 2026-04-22)
    # ------------------------------------------------------------------

    def finalize_match(self, reason: str) -> dict | None:
        """Mark match as terminated on a physics condition.

        Called exactly once when innings-2 physics resolve:
          - "target_reached": chase completed, batting team won
          - "all_out": chasing team bowled out
          - "overs_exhausted": 20 overs used without reaching target

        Idempotent — subsequent calls are no-ops and return the
        previously-computed result.
        """
        if self.match_complete:
            return self.match_result
        self.match_complete = True
        self.match_end_reason = reason
        self.match_result = self._compute_result(reason)
        log.info(
            f"[MATCH-COMPLETE] reason={reason} "
            f"result={self.match_result}")
        return self.match_result

    def _compute_result(self, reason: str) -> dict:
        """Build a human-readable match result dict.

        Structure:
          winner: str — team name
          margin: str — e.g. "by 4 wickets" or "by 23 runs"
          balls_remaining: int | None — only set on target_reached
          reason: str — the physics condition that terminated the match
        """
        inn2 = self._inn if self.current_innings == 2 else None
        if inn2 is None:
            return {"winner": None, "margin": None,
                    "balls_remaining": None, "reason": reason}
        try:
            score = int(inn2.get("score") or 0)
        except (ValueError, TypeError):
            score = 0
        try:
            wkts = int(inn2.get("wickets") or 0)
        except (ValueError, TypeError):
            wkts = 0
        try:
            overs_f = float(inn2.get("overs") or 0.0)
        except (ValueError, TypeError):
            overs_f = 0.0
        try:
            target = int(inn2.get("target") or 0)
        except (ValueError, TypeError):
            target = 0

        batting = self.batting_team
        bowling = self.bowling_team

        if reason == "target_reached":
            whole = int(overs_f)
            partial = round((overs_f - whole) * 10)
            balls_bowled = whole * 6 + max(0, partial)
            balls_remaining = max(0, 120 - balls_bowled)
            wickets_left = max(0, 10 - wkts)
            return {
                "winner": batting,
                "margin": (
                    f"by {wickets_left} wicket"
                    f"{'s' if wickets_left != 1 else ''}"),
                "balls_remaining": balls_remaining,
                "reason": reason,
            }
        elif reason in ("all_out", "overs_exhausted"):
            if target > 0:
                runs = target - 1 - score
                runs = max(0, runs)
            else:
                runs = None
            # Tie handling: if the chasing side ends on exactly
            # target-1 (== team 1 total), scores are level. In T20 a
            # super-over resolves it; absent that signal, the correct
            # terminal label is "tied", not a 0-run win.
            if runs == 0:
                return {
                    "winner": None,
                    "margin": "tied",
                    "balls_remaining": None,
                    "reason": reason,
                }
            return {
                "winner": bowling,
                "margin": (
                    f"by {runs} run{'s' if (runs or 0) != 1 else ''}"
                    if runs is not None else None),
                "balls_remaining": None,
                "reason": reason,
            }
        return {"winner": None, "margin": None,
                "balls_remaining": None, "reason": reason}

    # ------------------------------------------------------------------
    # Pre-match setup
    # ------------------------------------------------------------------

    def setup_innings(self, batting_team: str, bowling_team: str,
                      batting_squad: list[str], bowling_squad: list[str],
                      squad_roles: dict[str, str] | None = None,
                      batting_xi: list[str] | None = None,
                      bowling_xi: list[str] | None = None,
                      batting_subs: list[str] | None = None,
                      bowling_subs: list[str] | None = None,
                      player_styles: dict[str, dict] | None = None):
        """Pre-build scorecards with all players. Stats start at null.

        squad_roles maps canonical name → role string
        (e.g. "bowler", "bat_allrounder", "bowl_allrounder").
        batting_xi / bowling_xi: the playing XI names (subset of squad).
        ``batting_subs`` / ``bowling_subs``: bench pool (impact-eligible).
        player_styles maps canonical name → {batting_style, bowling_style}
        (from player_enrichment.enrich_squad_styles).
        """
        self.batting_team = batting_team
        self.bowling_team = bowling_team
        if squad_roles:
            self._squad_roles.update(squad_roles)
        if player_styles:
            self._player_styles.update(player_styles)

        _bat_xi_set = set(batting_xi) if batting_xi else set()
        _bowl_xi_set = set(bowling_xi) if bowling_xi else set()
        _bat_sub_set = (
            set(batting_subs) if batting_subs is not None else set())
        _bowl_sub_set = (
            set(bowling_subs) if bowling_subs is not None else set())
        if batting_subs is None and batting_xi:
            _bat_sub_set = {n for n in batting_squad if n not in _bat_xi_set}
        if bowling_subs is None and bowling_xi:
            _bowl_sub_set = {n for n in bowling_squad if n not in _bowl_xi_set}

        self.batting_card = {}
        for name in batting_squad:
            st = self._player_styles.get(name) or {}
            self.batting_card[name] = {
                "runs": None, "balls": None,
                "fours": None, "sixes": None, "sr": None,
                "status": "yet_to_bat", "dismissal": None,
                "dismissal_source": None,
                "position": len(self.batting_card) + 1,
                "is_playing_xi": name in _bat_xi_set if _bat_xi_set else True,
                "batting_style": st.get("batting_style", "unknown"),
                "bowling_style": st.get("bowling_style", "unknown"),
            }

        _bc_prev_size = len(getattr(self, "bowling_card", {}) or {})
        self.bowling_card = {}
        try:
            from trace_emitter import get_recorder as _bcget
            _bcget().record(
                tag="BOWLING-CARD-CLEARED",
                reason="innings1_init",
                prev_size=int(_bc_prev_size),
                squad_size=len(bowling_squad))
        except Exception:
            pass
        for name in bowling_squad:
            st = self._player_styles.get(name) or {}
            self.bowling_card[name] = {
                "overs": None, "maidens": 0,
                "runs": None, "wickets": None, "econ": None,
                "balls": 0,
                "balls_this_over": 0,
                "runs_this_over": 0,
                "byes_lb_this_over": 0,
                "position": len(self.bowling_card) + 1,
                "is_playing_xi": name in _bowl_xi_set if _bowl_xi_set else True,
                "batting_style": st.get("batting_style", "unknown"),
                "bowling_style": st.get("bowling_style", "unknown"),
            }

        self._dismissed_inferred = False
        self._build_name_lookup(batting_squad + bowling_squad)

        self._inn["batting_team"] = batting_team
        self._inn["bowling_team"] = bowling_team
        self._impact_promote_streak = {}
        self._impact_promote_last_frame = {}
        self._batter_slot_last_identity = {}
        if batting_xi and bowling_xi:
            self._init_match_membership(
                batting_team, set(batting_xi), set(_bat_sub_set),
                bowling_team, set(bowling_xi), set(_bowl_sub_set))
        else:
            self._team_match_membership = {}

        log.info(f"Scorecards built: {batting_team} ({len(batting_squad)} bat) "
                 f"vs {bowling_team} ({len(bowling_squad)} bowl)")

    def _init_match_membership(
            self,
            batting_team: str,
            bat_xi: set[str],
            bat_subs: set[str],
            bowling_team: str,
            bowl_xi: set[str],
            bowl_subs: set[str]) -> None:
        self._team_match_membership = {
            batting_team: {
                "active_xi": set(bat_xi),
                "available_subs": set(bat_subs) - set(bat_xi),
                "replaced": set(),
                "impact_used": False,
            },
            bowling_team: {
                "active_xi": set(bowl_xi),
                "available_subs": set(bowl_subs) - set(bowl_xi),
                "replaced": set(),
                "impact_used": False,
            },
        }

    def is_eligible_to_bat_or_bowl(
            self, canonical_name: str, team: str | None) -> tuple:
        """Return (kind, reason) where kind ∈ ok | reject | candidate."""
        if not team or not self._team_match_membership.get(team):
            return ("ok", "no_membership_state")
        m = self._team_match_membership[team]
        if canonical_name in m["active_xi"]:
            return ("ok", "active_xi")
        if canonical_name in m["replaced"]:
            return ("reject", "replaced_player")
        if canonical_name in m["available_subs"]:
            return ("candidate", "potential_impact_player")
        return ("reject", "not_in_squad")

    def _clear_impact_streak_team(self, team: str) -> None:
        for k in list(self._impact_promote_streak.keys()):
            if k[0] == team:
                self._impact_promote_streak.pop(k, None)
                self._impact_promote_last_frame.pop(k, None)

    def _bump_impact_streak(
            self, team: str, name: str, frame: int) -> int:
        for k in list(self._impact_promote_streak.keys()):
            if k[0] == team and k[1] != name:
                self._impact_promote_streak.pop(k, None)
                self._impact_promote_last_frame.pop(k, None)
        key = (team, name)
        prev_f = self._impact_promote_last_frame.get(key, -10**9)
        if frame != prev_f + 1 and prev_f > -10**8:
            self._impact_promote_streak[key] = 1
        else:
            self._impact_promote_streak[key] = (
                self._impact_promote_streak.get(key, 0) + 1)
        self._impact_promote_last_frame[key] = frame
        return self._impact_promote_streak[key]

    def _promote_impact_player(self, team: str, name: str) -> None:
        m = self._team_match_membership[team]
        m["available_subs"].discard(name)
        m["active_xi"].add(name)
        m["impact_used"] = True
        if name in self.batting_card:
            self.batting_card[name]["is_playing_xi"] = True
        if name in self.bowling_card:
            self.bowling_card[name]["is_playing_xi"] = True
        log.info(
            f"[IMPACT-PLAYER-ACTIVATED] team {team} player {name} "
            f"promoted from sub pool, impact_used=true")

    def _reset_batter_consensus_for(self, name: str) -> None:
        log.info(
            f"[BATTER-CONSENSUS-RESET] {name} — clearing bat tracker streak")
        self._tracker.force_set(f"bat:{name}:runs", None)
        self._tracker.force_set(f"bat:{name}:balls", None)
        self._runs_reject_streak.pop(name, None)

    def mark_player_replaced_for_testing(self, team: str, player: str) -> None:
        m = self._team_match_membership.get(team)
        if not m:
            return
        m["active_xi"].discard(player)
        m["available_subs"].discard(player)
        m["replaced"].add(player)

    # ------------------------------------------------------------------
    # Style retro-patch (used by background Pass-2 enrichment).
    # ------------------------------------------------------------------
    def update_player_styles(self, styles: dict[str, dict]) -> int:
        """Merge ``styles`` into ``_player_styles`` and patch any existing
        ``batting_card`` / ``bowling_card`` entries in place.

        Used by the background Pass-2 enrichment: when Pass-2 completes
        after ``setup_innings`` has already populated cards from Pass-1
        styles, this method applies the corrections without rebuilding
        the cards (which would wipe live stats). Future ``setup_innings``
        calls (e.g. for innings 2) will pick up the merged
        ``_player_styles`` automatically.

        Returns the number of card slots updated (sum of batting+bowling
        cards touched), useful for telemetry and tests.
        """
        if not styles:
            return 0
        self._player_styles.update(styles)
        n_updated = 0
        for name, st in styles.items():
            if not isinstance(st, dict):
                continue
            bat = st.get("batting_style", "unknown")
            bowl = st.get("bowling_style", "unknown")
            if name in self.batting_card:
                self.batting_card[name]["batting_style"] = bat
                self.batting_card[name]["bowling_style"] = bowl
                n_updated += 1
            if name in self.bowling_card:
                self.bowling_card[name]["batting_style"] = bat
                self.bowling_card[name]["bowling_style"] = bowl
                n_updated += 1
        log.info(f"[STYLES-PATCH] Updated {n_updated} card slots from "
                 f"background Pass-2 enrichment ({len(styles)} players)")
        return n_updated

    def infer_dismissed_batters(self):
        """DISABLED (Bug #2 fix).

        Previously this method tried to infer dismissals from the squad
        XI order (e.g. "openers always bat", "players between this
        position and the active position must have been dismissed").
        That heuristic is fundamentally broken for T20 cricket because
        teams routinely send non-openers up the order (e.g. KKR sent
        Rahane to open instead of Narine in this match) and promote
        nightwatchmen / Impact-Subs out of squad order.

        A player is now dismissed ONLY when there is direct evidence:
          1. They were on the strip and then disappeared (replaced by
             a new batter at the crease).
          2. The wickets count increased at the same time.
          3. Scout's action text describes a dismissal.

        Squad position is metadata for commentary context only — never
        a state-change trigger. Wicket count is tracked separately in
        `self._inn['wickets']` so disabling this does not affect the
        score; it only stops phantom dismissals from corrupting the
        batting card and seeding bad scorer hints.
        """
        # No-op preserved so existing call sites remain valid.
        self._dismissed_inferred = True
        return

    # ------------------------------------------------------------------
    # Name resolution — broadcast names → canonical squad names
    # ------------------------------------------------------------------

    _VOWEL_VARIANTS = {
        "OO": "U", "U": "OO",
        "EE": "I", "I": "EE",
        "TH": "T", "T": "TH",
        "V": "W", "W": "V",
    }

    def _build_name_lookup(self, all_players: list[str]):
        """Build lookup table mapping broadcast variants to canonical names."""
        self._name_lookup = {}
        for full in all_players:
            parts = full.strip().split()
            if not parts:
                continue
            up = full.upper().strip()
            self._name_lookup[up] = full

            if len(parts) >= 2:
                last = parts[-1].upper()
                first = parts[0].upper()
                self._name_lookup[last] = full
                self._name_lookup[f"{first[0]} {last}"] = full
                self._name_lookup[f"{first[0]}. {last}"] = full
                self._name_lookup[f"{first[0]}{last}"] = full

                if len(parts) == 3:
                    middle = parts[1].upper()
                    self._name_lookup[f"{first[0]} {middle[0]} {last}"] = full

                for old, new in self._VOWEL_VARIANTS.items():
                    variant = last.replace(old, new)
                    if variant != last:
                        self._name_lookup[variant] = full
                        if len(parts) >= 2:
                            self._name_lookup[
                                f"{first[0]} {variant}"] = full

        self._add_unique_prefixes(all_players)
        self._add_unique_first_names(all_players)

    def _add_unique_first_names(self, all_players: list[str]):
        """Add first-name-only lookup if the first name is unique."""
        first_name_map: dict[str, list[str]] = {}
        for full in all_players:
            parts = full.strip().split()
            if len(parts) >= 2:
                first = parts[0].upper()
                first_name_map.setdefault(first, []).append(full)
        for first, names in first_name_map.items():
            if len(set(names)) == 1 and first not in self._name_lookup:
                self._name_lookup[first] = names[0]

    def _add_unique_prefixes(self, all_players: list[str]):
        """Add 3/4-letter surname prefixes only if unique across squads."""
        prefix_candidates: dict[str, list[str]] = {}
        for full in all_players:
            parts = full.strip().split()
            if not parts:
                continue
            last = parts[-1].upper()
            surnames = {last}
            for old, new in self._VOWEL_VARIANTS.items():
                variant = last.replace(old, new)
                if variant != last:
                    surnames.add(variant)
            for sn in surnames:
                if len(sn) >= 5:
                    prefix_candidates.setdefault(sn[:3], []).append(full)
                    prefix_candidates.setdefault(sn[:4], []).append(full)

        for prefix, names in prefix_candidates.items():
            if len(set(names)) == 1 and prefix not in self._name_lookup:
                self._name_lookup[prefix] = names[0]

    @staticmethod
    def _name_similarity(a: str, b: str) -> float:
        """Similarity ratio handling insertions/deletions properly."""
        if not a or not b:
            return 0.0
        return SequenceMatcher(None, a, b).ratio()

    def resolve_name(self, name: str) -> str | None:
        """Resolve a broadcast name to a canonical squad name."""
        if not name:
            return None
        clean = name.upper().strip()

        if clean in self._name_lookup:
            return self._name_lookup[clean]

        # Exact match in cards
        if name in self.batting_card or name in self.bowling_card:
            return name

        # Fuzzy: surname match, initial+surname
        for canonical in list(self.batting_card) + list(self.bowling_card):
            canonical_parts = canonical.upper().split()
            if clean in canonical_parts:
                return canonical
            name_parts = clean.split()
            if len(name_parts) == 2 and len(name_parts[0]) <= 2:
                initial, surname = name_parts
                if surname in canonical_parts and \
                        canonical.upper().startswith(initial):
                    return canonical

        # Single initial (e.g. "M" from scorer) — try "M <surname>" combos
        if len(clean) <= 2:
            for key, canonical in self._name_lookup.items():
                if key.startswith(clean + " ") and len(key.split()) == 2:
                    self._name_lookup[clean] = canonical
                    log.info(f"[NAME] Single initial '{clean}' → "
                             f"'{canonical}' (via '{key}')")
                    return canonical

        log.info(f"[NAME] Exact miss for '{clean}', trying fuzzy "
                 f"({len(self._name_lookup)} keys)...")

        best_match = None
        best_score = 0.0
        for key, canonical in self._name_lookup.items():
            if len(key) < 4 and len(clean) > 4:
                continue
            score = self._name_similarity(clean, key)
            if score > best_score and score >= 0.75:
                best_score = score
                best_match = canonical
        if best_match:
            self._name_lookup[clean] = best_match
            log.info(f"Fuzzy matched '{name}' → '{best_match}' "
                     f"({best_score:.0%})")
            return best_match

        near = sorted(
            [(k, self._name_similarity(clean, k))
             for k in self._name_lookup if len(k) >= 4],
            key=lambda x: -x[1])[:3]
        log.warn(f"No match for '{clean}'. Closest: "
                 f"{[(k, f'{s:.2f}') for k, s in near]}")

        return None

    def resolve_name_split(self, raw_name: str) -> list[str]:
        """Resolve a name, splitting merged names if needed.

        "Prashant Dube" where full→Prashant Veer (fuzzy) but
        surname "Dube"→Shivam Dube → split into two players.
        Returns list of 1 or 2 canonical names.
        """
        if not raw_name:
            return []
        parts = raw_name.strip().split()

        if len(parts) == 2:
            full_match = self.resolve_name(raw_name)
            surname_match = self.resolve_name(parts[1])
            firstname_match = self.resolve_name(parts[0])

            if (full_match and surname_match
                    and full_match != surname_match
                    and firstname_match
                    and firstname_match != surname_match):
                log.info(f"[NAME] Merged names: '{raw_name}' → "
                         f"'{firstname_match}' + '{surname_match}'")
                return [firstname_match, surname_match]

            if full_match:
                return [full_match]

        resolved = self.resolve_name(raw_name)
        return [resolved] if resolved else []

    # ------------------------------------------------------------------
    # Scalar updates — hard limits only
    # ------------------------------------------------------------------

    def set(self, field: str, value, frame: int) -> bool:
        if value is None:
            return False

        old = self._inn.get(field)

        if field == "score":
            try:
                v = int(value)
            except (ValueError, TypeError):
                return False
            # Absolute T20 ceiling — no team has ever passed 287 in
            # men's T20Is.  720 was way too loose for a T20 pipeline
            # and let OCR garbage (e.g. "446" misread of an overlay
            # number) through to the headline.
            if v < 0 or v > 320:
                log.warn(f"Score rejected: absolute {v} > 320")
                return False
            # Chase-aware ceiling: in 2nd innings, the score can equal
            # target on the winning ball but never exceed target by more
            # than a small OCR-jitter buffer.  Rejects e.g. 446/2 when
            # the chase target is 181.
            if self.current_innings >= 2:
                tgt = self._inn.get("target")
                if tgt is not None and v > int(tgt) + 4:
                    log.warn(f"Score rejected: chase {v} > "
                             f"target {tgt} + 4")
                    return False
            # Per-update jump guard: even after a long ad break,
            # consecutive scoreboard reads should not differ by 100+
            # runs.  Hard-reject before the consensus tracker so
            # repeated bad reads can't form consensus.
            cur_score = self._inn.get("score")
            if cur_score is not None:
                try:
                    cur_int = int(cur_score)
                    if v < cur_int:
                        log.warn(
                            f"Score regression rejected: {cur_int}→{v} "
                            f"(normal-play score physics; reset authority "
                            f"required)")
                        return False
                    if v - cur_int > 100:
                        log.warn(f"Score rejected: jump "
                                 f"{cur_int} → {v} (+{v - cur_int}) "
                                 f"too large for a single update")
                        return False
                except (ValueError, TypeError):
                    pass
            confirmed = self._tracker.update("score", v, frame)
            if confirmed != v:
                return False
            value = v

        elif field == "wickets":
            try:
                v = int(value)
            except (ValueError, TypeError):
                return False
            if v < 0 or v > 10:
                return False
            # Fix #1 (2026-04-23): count per-frame Scout observations
            # of wickets=0 — the gate below uses this to distinguish
            # a cold-start attach from a live 0→1 transition.  We
            # increment on the RAW observation (before tracker gate)
            # because we care about how many frames Scout has shown
            # zero, not how many consensus commits fired.  Threshold
            # in the seed logic is >=2 observed zeros.
            if v == 0:
                self._wickets_confirmed_frames_at_zero += 1
            cur_w = self._inn.get("wickets")
            if cur_w is not None:
                cur_wi = int(cur_w)
                if v < cur_wi:
                    if self._all_out_lock and cur_wi >= 10:
                        log.warn(
                            f"Wickets regression rejected under all-out "
                            f"lock: {cur_w}→{v} "
                            f"(source={self._all_out_lock_source})")
                        return False
                    # Broadcast-authoritative regression path. Reject
                    # the lower reading by default (single-frame OCR
                    # noise), but if the SAME lower value persists for
                    # 3 SCOREBOARD frames in a row it's the broadcast
                    # correcting our over-counted wickets — accept it
                    # AND drop any tentative FOW entries we added on
                    # top of the now-invalid wicket.
                    if self._pending_wickets_low == v:
                        self._pending_wickets_low_count += 1
                    else:
                        self._pending_wickets_low = v
                        self._pending_wickets_low_count = 1
                    if self._pending_wickets_low_count < 3:
                        log.warn(
                            f"Wickets regression rejected: "
                            f"{cur_w}→{v} "
                            f"(consensus {self._pending_wickets_low_count}/3)")
                        return False
                    log.warn(
                        f"[WICKETS-REGRESS] Accepting {cur_w}→{v} "
                        f"after 3 consecutive frames of broadcast "
                        f"reading {v}. Pipeline over-counted; "
                        f"trimming tentative FOW entries above "
                        f"wicket #{v}.")
                    self._pending_wickets_low = None
                    self._pending_wickets_low_count = 0
                    # Drop any FOW entry whose wicket number is now
                    # phantom (above the new lower count). Confirmed
                    # entries (tentative=False) are kept as-is and
                    # the operator can investigate the disagreement.
                    _kept = []
                    for _f in self.fall_of_wickets:
                        try:
                            _wn = int(_f.get("wicket") or 0)
                        except (ValueError, TypeError):
                            _wn = 0
                        if _wn > v and _f.get("tentative"):
                            log.info(
                                f"[FOW] Dropping tentative W{_wn} "
                                f"({_f.get('batter')}) — wickets "
                                f"regressed to {v}, this entry was "
                                f"a phantom dismissal.")
                            # Reactivate the batter we tentatively
                            # marked out (mirror of dismiss-tentative).
                            _bn = _f.get("batter")
                            if _bn:
                                _key = self._find_card_key(
                                    _bn, self.batting_card)
                                if _key and self.batting_card.get(
                                        _key, {}).get("status") == "out":
                                    _e = self.batting_card[_key]
                                    if isinstance(_e.get("dismissal"),
                                                  dict) and "tentative" in str(
                                            _e["dismissal"].get("how", "")):
                                        _e["status"] = "batting"
                                        _e["dismissal"] = None
                                        log.info(
                                            f"[FOW] Reactivated "
                                            f"{_key} (tentative "
                                            f"dismissal cleared "
                                            f"alongside W{_wn}).")
                            continue
                        _kept.append(_f)
                    self.fall_of_wickets = _kept
                    # P1 fix (2026-05-02): wickets regressed downward
                    # — propagate the corrected count to gates that
                    # encode last-known wickets as a one-way counter.
                    self.downstream_gates_resync(
                        v, source="wickets_regression_accept")
                else:
                    self._pending_wickets_low = None
                    self._pending_wickets_low_count = 0
                if v > cur_wi + 1:
                    if self._pending_wickets_high == v:
                        self._pending_wickets_high_count += 1
                    else:
                        self._pending_wickets_high = v
                        self._pending_wickets_high_count = 1
                    if self._pending_wickets_high_count < 3:
                        log.warn(
                            f"Wickets jump +{v - cur_wi} deferred "
                            f"(max +1/frame): {cur_w}→{v} "
                            f"(consensus "
                            f"{self._pending_wickets_high_count}/3)")
                        return False
                    log.warn(
                        f"[WICKETS-JUMP] Accepting {cur_w}→{v} "
                        f"after 3 consecutive frames of broadcast "
                        f"reading {v}. Cold-start over-lock "
                        f"recovered — catching up to broadcast.")
                    # Stamp the consistent-tracker's confirmed state
                    # directly so we skip its 2-frame pending delay on
                    # top of the 3-frame scoreboard consensus we just
                    # cleared. Without this the tracker treats {0→2}
                    # as a fresh pending proposal and returns 0, which
                    # makes `set()` fail below and keeps us stuck.
                    self._tracker.confirmed["wickets"] = v
                    self._tracker.pending.pop("wickets", None)
                    self._tracker.pending_counts.pop("wickets", None)
                    self._pending_wickets_high = None
                    self._pending_wickets_high_count = 0
                    value = v
                else:
                    self._pending_wickets_high = None
                    self._pending_wickets_high_count = 0
                    confirmed = self._tracker.update("wickets", v, frame)
                    if confirmed != v:
                        return False
                    value = confirmed
            else:
                confirmed = self._tracker.update("wickets", v, frame)
                if confirmed != v:
                    return False
                value = confirmed

        elif field == "overs":
            try:
                s = str(value).strip()
                if "." in s:
                    whole_s, ball_s = s.split(".")
                    whole = int(whole_s)
                    ball = int(ball_s)
                    if ball > 5:
                        whole += 1
                        ball = 0
                        log.info(f"Overs '{value}' had ball>5 — "
                                 f"normalized to {whole}.{ball}")
                else:
                    whole, ball = int(float(s)), 0
            except (ValueError, TypeError):
                return False
            if whole > T20_MAX_OVERS or whole < 0:
                return False
            overs_str = f"{whole}.{ball}"
            # Hard multi-over jump guard.  Cricket cannot advance more than
            # one over between consecutive scoreboard reads in normal play.
            # We allow +2 (not just +1) because the pipeline can legitimately
            # miss the last ball of an over during an ad-break, in which
            # case the next read shows over N+2 ball 1.  A +3 or larger
            # jump is always a Scout misread of the team-overs digit
            # (e.g. (0.5) hallucinated as 5.0; the cricket-rules validator
            # also catches this downstream, but rejecting here keeps
            # _inn["overs"] from holding the wrong value for downstream
            # consumers and the UI between reject and recovery).
            cur_overs = self._inn.get("overs")
            if cur_overs is not None:
                try:
                    cur_w_s, _ = str(cur_overs).split(".")
                    cur_w_int = int(cur_w_s)
                    if whole > cur_w_int + 2:
                        log.warn(f"Overs rejected: jump {cur_overs} → "
                                 f"{overs_str} (+{whole - cur_w_int} overs) "
                                 f"too large for a single update")
                        try:
                            _cur_b = int(str(cur_overs).split(".")[1])
                            _delta_balls = (
                                whole * 6 + ball
                                - (cur_w_int * 6 + _cur_b))
                            log.info(
                                f"[GAP-AT-REJECTION] Δballs={_delta_balls} "
                                f"proposed_overs={overs_str} "
                                f"current_overs={cur_overs} "
                                f"source=scoreboard_jump_limit")
                            try:
                                from eyes.frame_ledger import (
                                    get_ledger, SmOutcome)
                                get_ledger().record_sm_outcome(
                                    int(frame) if frame is not None else 0,
                                    SmOutcome.REJECTED_SB_JUMP_LIMIT,
                                    payload={
                                        "delta_balls": _delta_balls,
                                        "proposed_overs": overs_str,
                                        "current_overs": str(cur_overs),
                                        "source": "scoreboard_jump_limit",
                                    })
                            except Exception:
                                pass
                        except (ValueError, IndexError):
                            pass
                        return False
                except (ValueError, AttributeError):
                    pass
            confirmed = self._tracker.update("overs", overs_str, frame)
            if confirmed != overs_str:
                return False
            value = overs_str

        elif field == "target":
            if self.current_innings == 1:
                log.warn(f"Target rejected: innings 1 has no target (value={value})")
                return False
            try:
                v = int(value)
            except (ValueError, TypeError):
                return False
            if v < 1 or v > 720:
                return False
            value = v

        elif field == "run_rate":
            try:
                v = round(float(value), 2)
            except (ValueError, TypeError):
                return False
            if v < 0 or v > 36:
                return False
            value = v

        else:
            return False

        self._inn[field] = value
        if old != value:
            self._log("set", field, old, value, frame)
            # B-κ instrumentation (2026-05-21) — fire DIRECT-SCORE-COMMIT
            # at every score-field write that advances the tracker. The
            # payload's overs_at_commit / wickets_at_commit fields let
            # the analyzer detect "split score/overs commit" sequences —
            # the active defect mechanism surfaced in stream-gap
            # reconciliation memo §10. Wrapped defensively; trace
            # emission must never break the write path. Layer 1.5 +
            # Layer 2 gates pre-validate the additive nature.
            if field == "score" and _trace is not None:
                try:
                    _trace.get_recorder().record(
                        tag="DIRECT-SCORE-COMMIT",
                        score_before=old,
                        score_after=value,
                        overs_at_commit=self._inn.get("overs"),
                        wickets_at_commit=self._inn.get("wickets"),
                        frame_id=frame)
                except Exception:
                    pass
            # Cold-start seeding of the auto-dismiss gate (Issue D,
            # 2026-04-21; refined by Fix #1, 2026-04-23).
            #
            # Original behaviour: any old==0 → value>0 transition would
            # seed the gate to `value`, blocking auto-dismissal until
            # the counter advanced past it.  That protected against
            # mid-match attaches (where historical wickets can't be
            # attributed) but misfired on the FIRST real wicket during
            # a live session — the gate pre-armed itself to 1, then
            # the genuine dismissal event found `_cur_wk <=
            # _last_dismiss_wk` and was silently dropped.  Observed
            # on Sarfaraz, MI vs CSK 2026-04-23: cold-start wicket
            # seed fired at F11 on the first real wicket, locking the
            # dismissal gate for the rest of the innings.
            #
            # New gate: seed ONLY when wickets were never confirmed
            # (`old is None`, pure cold-start) OR when we've seen
            # fewer than 2 frames confirming wickets=0.  Once 2+
            # frames have confirmed zero, any subsequent 0→1 is a
            # real event and must NOT pre-arm the gate.
            _wk_zero_streak = self._wickets_confirmed_frames_at_zero
            _should_seed = (
                field == "wickets"
                and isinstance(value, int)
                and value > 0
                and getattr(self, "_last_autodismiss_wickets", 0) == 0
                and (
                    old is None
                    or (old == 0 and _wk_zero_streak < 2)
                )
            )
            if _should_seed:
                self._last_autodismiss_wickets = value
                log.info(
                    f"[DISMISS] Cold-start seed — gate set to "
                    f"wickets={value} (zero_streak={_wk_zero_streak}, "
                    f"historical wickets will not trigger "
                    f"auto-dismissal).")
            elif (field == "wickets" and isinstance(value, int)
                    and value > 0 and old == 0
                    and _wk_zero_streak >= 2):
                log.info(
                    f"[DISMISS] Live wicket — gate NOT seeded "
                    f"(wickets=0 confirmed on {_wk_zero_streak} prior "
                    f"frames; 0→{value} is a real event).")
            # Bowler auto-increment: when team score / overs advance,
            # the runs/balls are conceded by the *current* bowler. The
            # broadcast bowler card lags behind the team score by 1-2
            # frames; mirroring the delta onto the current bowler lets
            # the UI show "0.4 → 0.5" the moment the team strip flips
            # to "7.5". For runs we add the full delta — extras
            # (wides/no-balls/byes/leg-byes/penalties) are credited to
            # the bowler in cricket scoring; we subtract leg-byes /
            # byes if and when the broadcast confirms them later.
            #
            # OPERATIONAL NOTE (2026-04-26): the live observation that
            # "bowler stats lag team stats" is *not* a bug.  Two
            # independent ingest paths feed bowler.runs/overs:
            #   (a) BOWLER-AUTO mirror, attempted here on every team
            #       score/overs delta.
            #   (b) Scout-driven SCOREBOARD reads, which extract
            #       authoritative bowler figures directly from the
            #       broadcast bowler card.
            # When Scout is reading the bowler card at high cadence
            # (typical mid-innings), BOWLER-AUTO's deferral logic at
            # `_mirror_team_delta_to_bowler` (search "Scout active")
            # suppresses most mirrors so the authoritative Scout value
            # commits cleanly without race.  Net effect: Scout is the
            # dominant ingest path, and bowler stats trail team stats
            # by 1-2 Scout cadence intervals (a few seconds).  This is
            # bounded but visible — future engineers seeing
            # "Holder runs=22 but team total advanced past that" should
            # not chase it as a bug.  Two paths, different cadences,
            # one wins per frame.  See backlog "P2: SM ingest-latency
            # reduction" for an architectural fix that closes the gap.
            try:
                if field in ("score", "overs"):
                    self._mirror_team_delta_to_bowler(
                        field, old, value, frame)
            except Exception as _e:
                log.warn(f"[BOWLER-AUTO] mirror failed: {_e}")
        return True

    def accept_all_out_authority(self, source: str,
                                 frame: int = 0) -> bool:
        """Promote 9 wickets to all-out from independent final-wicket evidence."""
        try:
            cur_w = int(self._inn.get("wickets") or 0)
        except (TypeError, ValueError):
            cur_w = 0
        if cur_w >= 10:
            self._all_out_lock = True
            self._all_out_lock_source = source
            self._all_out_lock_frame = frame
            return True
        if cur_w != 9:
            return False
        self._tracker.force_set("wickets", 10)
        old = self._inn.get("wickets")
        self._inn["wickets"] = 10
        self._all_out_lock = True
        self._all_out_lock_source = source
        self._all_out_lock_frame = frame
        self.sync_fow_to_wickets()
        self._log("set", "wickets", old, 10, frame)
        log.warn(
            f"[ALL-OUT-AUTHORITY] Promoted wickets 9→10 from "
            f"{source}; contextual wicket regressions locked until "
            f"innings transition")
        return True

    # ------------------------------------------------------------------
    # Bowler auto-increment
    # ------------------------------------------------------------------

    def _team_balls_seen(self) -> int:
        try:
            whole_s, ball_s = (
                str(self._inn.get("overs") or "0.0").split(".") + ["0"])[:2]
            return int(whole_s) * 6 + int((ball_s or "0")[:1])
        except (TypeError, ValueError):
            return 0

    def _bowler_has_fow_credit(self, name: str) -> bool:
        """True if any fall_of_wickets entry attributes a wicket to this
        bowler.  Used by `update_bowler` to gate strip-delta wicket
        increments behind a real dismissal-event commit (investigation
        7B, 2026-05-14).
        """
        if not name:
            return False
        for fow in self.fall_of_wickets:
            if fow.get("bowler") == name:
                return True
        return False

    def _flush_bowler_attribution_freeze(self, frame: int,
                                         *, reason: str) -> None:
        """Apply any buffered team-score delta to the current bowler.

        Called at the two transition sites where a pending BOWLER-OVERRIDE
        resolves: ``fired`` (consensus reached, new bowler installed) or
        ``dissipated`` (incoming read matched current bowler, pending
        cleared).  In both cases the bowler now sitting on
        ``self._inn["current_bowler"]`` is the resolved attribution
        target.
        """
        runs = self._bowler_attribution_freeze_runs
        if runs <= 0:
            self._bowler_attribution_freeze_runs = 0
            return
        cb_name = self._inn.get("current_bowler") if self._inn else None
        if cb_name and cb_name in self.bowling_card:
            entry = self.bowling_card[cb_name]
            cur_r = int(entry.get("runs") or 0)
            entry["runs"] = cur_r + runs
            self._tracker.force_set(
                f"bowl:{cb_name}:runs", entry["runs"])
            log.info(
                f"[BOWLER-ATTRIBUTION-FLUSH] {cb_name}: +{runs} runs "
                f"({cur_r} → {entry['runs']}) reason={reason}")
        else:
            log.info(
                f"[BOWLER-ATTRIBUTION-FLUSH-NO-TARGET] dropping {runs} "
                f"buffered runs reason={reason} (no current_bowler)")
        self._bowler_attribution_freeze_runs = 0

    def _mirror_team_delta_to_bowler(self, field, old_v, new_v,
                                     frame: int) -> None:
        """Apply a team score/overs delta to the current bowler.

        Cricket scoring attributes every team run (except byes / leg-
        byes) and every legal delivery to the bowler on the day. The
        broadcast bowling-card overlay refreshes 1-2 frames after the
        team strip, leaving the UI showing stale figures until then.
        Mirroring the delta here keeps bowler stats live without
        waiting for the broadcast LLM read.

        OVER-BOUNDARY GUARD: the same bowler cannot bowl two
        consecutive overs (cricket rule). When team overs cross from
        ``X.0 → X.1`` (the first ball of the next over), the run /
        ball belongs to a DIFFERENT bowler whose name we don't know
        yet (broadcast bowler-card refresh lags by 1-2 frames).
        Skipping the mirror in that case prevents poisoning the
        outgoing bowler's figures with the new bowler's deliveries.
        """
        # A1 part 1 (2026-05-14): derivation-only — this team-delta
        # mirror path is superseded by event-driven _apply_bowler_delta
        # invoked from score_manager._accumulate_stats_from_event.
        # Disabled to remove the competing write path.  See
        # files/docs/investigations/derivation_only_stats_design.md.
        return
        cb_name = self._inn.get("current_bowler") if self._inn else None
        if not cb_name or cb_name not in self.bowling_card:
            return
        entry = self.bowling_card[cb_name]
        # Cold-start guard: if the team's prior state is None, this
        # is the FIRST broadcast read (pipeline just started, joined
        # mid-match). We're not actually observing ball-by-ball
        # increments here — the bowler stats from the broadcast strip
        # are what they are, don't blindly add the team total to them.
        if old_v is None or self._inn.get("overs") is None:
            return
        # Fix #2 (2026-04-23): defer when Scout is actively reading.
        # If update_bowler() fired within the last 2 frames Scout is
        # supplying authoritative figures — let those commit instead
        # of auto-incrementing, which otherwise races ahead (bumping
        # recorded overs 0.4 → 0.5) and then causes Scout's 0.4 read
        # to be rejected as stale on the same frame.
        # BOWLER-AUTO attribution freeze (investigation 5, 2026-05-14).
        # If a BOWLER-OVERRIDE is currently building consensus toward a
        # different bowler, buffer the team-score delta instead of
        # crediting the now-uncertain current bowler.  The buffer is
        # flushed in `_flush_bowler_attribution_freeze` at the two
        # resolution sites (override fires OR pending dissipates).
        # Placed BEFORE the scout-gap deferral so a pending override
        # captures every team-score delta during the consensus window
        # rather than letting some land as scout-gap drops.
        if (self._pending_bowler_name is not None
                and field == "score"):
            try:
                _delta = int(new_v) - int(old_v or 0)
            except (ValueError, TypeError):
                _delta = 0
            if 0 < _delta <= 6:
                self._bowler_attribution_freeze_runs += _delta
                log.info(
                    f"[BOWLER-ATTRIBUTION-FROZEN] +{_delta} runs "
                    f"buffered (pending={self._pending_bowler_name!r} "
                    f"streak={self._pending_bowler_count}, "
                    f"leader={cb_name!r}, "
                    f"buffered_total="
                    f"{self._bowler_attribution_freeze_runs})")
                if _trace is not None:
                    try:
                        _trace.get_recorder().record(
                            tag="BOWLER-ATTRIBUTION-FROZEN",
                            pending_candidate=self._pending_bowler_name,
                            pending_streak=self._pending_bowler_count,
                            leader=cb_name,
                            delta_runs=_delta,
                            buffered_total=(
                                self._bowler_attribution_freeze_runs))
                    except Exception:
                        pass
            return
        _scout_gap = frame - self._last_bowler_scout_frame
        if 0 <= _scout_gap < 2:
            log.info(
                f"[BOWLER-AUTO] {field} delta deferred — Scout "
                f"active (last bowler read {_scout_gap} frame(s) "
                f"ago); letting broadcast supply authoritative value")
            return
        # Determine current team-overs context (for over-boundary check).
        # _inn["overs"] holds the value AT THE MOMENT this set() was
        # invoked — for a "score" delta, overs has not yet been bumped
        # for the same broadcast read, so reading it gives the OLD
        # team overs. For an "overs" delta, old_v is the same OLD
        # value. Both paths can use _team_balls_part_of(_inn overs).
        try:
            _team_overs_now = (str(self._inn.get("overs") or "0.0")
                               .split(".") + ["0"])[:2]
            _team_balls_in_over = int(_team_overs_now[1])
        except (ValueError, TypeError):
            _team_balls_in_over = -1
        if field == "score":
            # If team overs ends in .0, the run we're about to add
            # corresponds to ball-1 of a brand-new over → new bowler.
            # Skip the auto-mirror; the broadcast bowler card will
            # catch up within 1-2 frames and we'll get the correct
            # name to credit.
            if _team_balls_in_over == 0:
                log.info(
                    f"[BOWLER-AUTO] runs delta deferred — team at "
                    f"over boundary ({self._inn.get('overs')}); "
                    f"new bowler will be confirmed by broadcast")
                return
            try:
                delta = int(new_v) - int(old_v or 0)
            except (ValueError, TypeError):
                return
            # Sanity guard: more than 6 runs in a single set() call
            # is almost always a cold-start big jump, not a single
            # delivery. Skip — broadcast bowler card will sync.
            if delta <= 0 or delta > 6:
                return
            cur_r = int(entry.get("runs") or 0)
            entry["runs"] = cur_r + delta
            self._tracker.force_set(
                f"bowl:{cb_name}:runs", entry["runs"])
            log.info(
                f"[BOWLER-AUTO] {cb_name} runs {cur_r} → "
                f"{entry['runs']} (+{delta} from team score)")
        elif field == "overs":
            try:
                old_w_s, old_b_s = (str(old_v or "0.0").split(".")
                                    + ["0"])[:2]
                new_w_s, new_b_s = (str(new_v).split(".")
                                    + ["0"])[:2]
                old_balls_total = int(old_w_s) * 6 + int(old_b_s)
                new_balls_total = int(new_w_s) * 6 + int(new_b_s)
            except (ValueError, TypeError):
                return
            balls_delta = new_balls_total - old_balls_total
            # Sanity guard: more than 1 ball in a single delta is
            # either dead-time skip or cold-start jump → don't auto-
            # mirror, let the broadcast bowler card take over.
            if balls_delta <= 0 or balls_delta > 1:
                return
            # Over-boundary skip: if old overs ends in ".0" then the
            # NEW ball(s) belong to the next over → different bowler.
            # Skip auto-attribution (broadcast confirms within 1-2
            # frames). Special case: if old=X.5 → new=X+1.0 we DO want
            # to attribute (that's the 6th and final ball of over X+1
            # by the current bowler).
            if int(old_b_s) == 0 and int(old_w_s) > 0:
                log.info(
                    f"[BOWLER-AUTO] overs delta deferred — old="
                    f"{old_v} is end-of-over, new ball belongs to "
                    f"a different bowler")
                return
            try:
                cur_w_s, cur_b_s = (str(entry.get("overs") or "0.0")
                                    .split(".") + ["0"])[:2]
                cur_total = int(cur_w_s) * 6 + int(cur_b_s)
            except (ValueError, TypeError):
                cur_total = 0
            new_total = cur_total + balls_delta
            new_w = new_total // 6
            new_b = new_total % 6
            new_overs_str = f"{new_w}.{new_b}"
            entry["overs"] = new_overs_str
            self._tracker.force_set(
                f"bowl:{cb_name}:overs", new_overs_str)
            log.info(
                f"[BOWLER-AUTO] {cb_name} overs "
                f"{cur_w_s}.{cur_b_s} → {new_overs_str} "
                f"(+{balls_delta} balls from team overs)")

    # ------------------------------------------------------------------
    # Batter updates — write to pre-built batting card
    # ------------------------------------------------------------------

    def _find_card_key(self, resolved: str, card: dict) -> str | None:
        """Find the exact key in a card that matches the resolved name."""
        if resolved in card:
            return resolved
        for key in card:
            if self.resolve_name(key) == resolved:
                return key
        return None

    def set_extractor_batters(self, names: set[str]):
        """Store current extractor batter names for auto-dismiss logic."""
        self._extractor_batter_names = names

    def _auto_dismiss_for_new_batter(self, active: list[str],
                                     new_batter: str) -> str | None:
        """When wickets > 0 and a new batter appears but 2 are active,
        auto-dismiss the active batter NOT in the extractor output.

        Only fires when exactly ONE active batter is missing from the
        extractor output (set difference = dismissed batter). If both
        active batters appear in the extractor (broadcast still showing
        the outgoing batter momentarily), returns None so the caller
        retries on the next frame.

        Gate (2026-04-21, Issue D): the wicket counter MUST have
        advanced since the last auto-dismiss we fired.  Without this
        gate, any extractor hallucination of a third batter (e.g. a
        replay graphic overlay, a career-stats panel, or a Scout
        misread of a career summary) would fire a dismissal against
        whichever active batter happened to be missing from the
        current frame's extractor output.  The wicket counter is the
        only deterministic signal that a real dismissal occurred;
        without a tick, no auto-dismiss may fire.
        """
        ext = self._extractor_batter_names
        if not ext:
            return None

        def _in_ext(name: str) -> bool:
            n_up = name.upper()
            return any(n_up in e or e in n_up for e in ext)

        missing = [a for a in active if not _in_ext(a)]

        # --- wicket-tick gate -------------------------------------
        try:
            _cur_wk = int(self._inn.get("wickets") or 0)
        except (TypeError, ValueError):
            _cur_wk = 0
        _last_dismiss_wk = getattr(self, "_last_autodismiss_wickets", 0)
        if _cur_wk <= _last_dismiss_wk:
            # Path 2 (P0-B, 2026-04-25): witnessed-FOW re-assertion
            # bypass.  The gate's intent is to block phantom NEW
            # wickets from extractor hallucinations.  When upstream
            # state corruption resurrects a witnessed-FOW dismissed
            # batter into the active set (live evidence: DC vs PBKS
            # F339 → F832 deadlock, 1330 consecutive WS-SCRUB
            # rejections of Nitish Rana), this gate compounds the
            # corruption by refusing to re-apply the canonical
            # dismissal — we appear to "already have dismissed someone
            # at this wicket count" because the resurrected batter
            # was originally dismissed at exactly this count.
            #
            # FOW is canonical: re-asserting a witnessed dismissal
            # creates no new wicket, just enforces one that already
            # happened.  Bypass the gate when exactly one active is
            # both (a) missing from extractor and (b) carries a
            # witnessed FOW entry.  Do NOT bump
            # `_last_autodismiss_wickets` (no new wicket occurred)
            # and do NOT call `_add_fow` (entry already exists; the
            # immutable witnessed-rule would refuse the rewrite
            # anyway).
            #
            # Composes with P0-A as defense-in-depth at a fourth
            # choke point.  P0-A (Fix 1+2+3) prevents resurrection at
            # update_batter and validate_state_consistency; this fix
            # ensures the auto-dismiss replacement path also recovers
            # cleanly if any future code path re-introduces resurrection.
            _bypass_candidates = [a for a in missing
                                  if self._is_witnessed_dismissal(a)]
            if len(_bypass_candidates) == 1:
                _name = _bypass_candidates[0]
                log.warn(
                    f"[INVARIANT] Re-asserting witnessed dismissal of "
                    f"'{_name}' (wicket-tick gate bypassed — FOW "
                    f"canonical, _cur_wk={_cur_wk} == "
                    f"_last_dismiss_wk={_last_dismiss_wk}). "
                    f"New batter '{new_batter}' will replace.")
                self.batting_card[_name]["status"] = "out"
                self.batting_card[_name]["dismissal_source"] = (
                    "wicket_ball_event")
                self._missing_batter_streak = {}
                return _name
            log.info(
                f"[DISMISS] Blocked — wickets counter has not advanced "
                f"since last auto-dismiss (cur={_cur_wk}, "
                f"last_dismiss_at={_last_dismiss_wk}). New batter "
                f"'{new_batter}' is almost certainly an extractor "
                f"hallucination (replay/comparison overlay) rather than "
                f"a real arrival at the crease.")
            return None

        if len(missing) != 1:
            if missing:
                log.info(f"[DISMISS] Multiple batters missing from "
                         f"extractor ({missing}) — ambiguous, skipping")
            else:
                log.info(f"[DISMISS] Both active batters in extractor "
                         f"output — broadcast hasn't settled, deferring")
            return None

        # --- missing-streak gate ----------------------------------
        # The "missing from extractor" signal is noisy: a single
        # closeup / replay / graphic frame routinely drops one batter.
        # Require the candidate to be missing for ≥ 2 consecutive
        # frames before acting on the signal.
        _streak = getattr(self, "_missing_batter_streak", {})
        candidate = missing[0]
        _streak = {k: v for k, v in _streak.items() if k in active}
        _streak[candidate] = _streak.get(candidate, 0) + 1
        self._missing_batter_streak = _streak
        if _streak[candidate] < 2:
            log.info(
                f"[DISMISS] '{candidate}' missing from extractor "
                f"(streak={_streak[candidate]}/2) — deferring one frame "
                f"to rule out a single-frame closeup/overlay drop.")
            return None

        dismissed = missing[0]
        _streak_in = getattr(self, "_incoming_streak", {})
        if _streak_in and new_batter not in _streak_in:
            _streak_in = {}
        _streak_in[new_batter] = _streak_in.get(new_batter, 0) + 1
        self._incoming_streak = _streak_in
        if _streak_in[new_batter] < 2:
            log.info(
                f"[DISMISS] incoming '{new_batter}' "
                f"streak={_streak_in[new_batter]}/2 — deferring")
            return None
        self._incoming_streak = {}
        self._last_autodismiss_wickets = _cur_wk
        self._missing_batter_streak = {}
        # === S17: prefer the structured dismissal hint piped in from
        # the pipeline (action-text scan or broadcast graphic) over
        # the generic "inferred" placeholder. The hint is a single
        # one-shot — clear after consuming so the next wicket gets a
        # fresh signal and we don't paint a stale "stumped" onto an
        # actually-bowled wicket. ===
        _hint = getattr(self, "pending_dismissal_hint", None)
        _hint_bowler = getattr(self, "pending_dismissal_bowler", None)
        if _hint:
            self.batting_card[dismissed]["dismissal"] = _hint
            self.pending_dismissal_hint = None
        else:
            self.batting_card[dismissed]["dismissal"] = (
                "inferred (replaced by new batter)")
        if _hint_bowler:
            self.batting_card[dismissed]["dismissal_bowler"] = _hint_bowler
            self.pending_dismissal_bowler = None
        self.batting_card[dismissed]["status"] = "out"
        self.batting_card[dismissed]["dismissal_source"] = "auto_inference"
        wk = self._inn.get("wickets")
        self._add_fow(wk, dismissed,
                       self._inn.get("score"),
                       self._inn.get("overs"),
                       how=_hint,
                       bowler=_hint_bowler or self._inn.get("current_bowler"))
        log.info(f"[WICKET] Auto-dismissed {dismissed} — "
                 f"not in extractor output, {new_batter} replacing"
                 + (f" (kind={_hint!r})" if _hint else ""))
        return dismissed

    def downstream_gates_resync(self, new_wickets: int | None,
                                source: str = "phantom_recovery") -> None:
        """Reset gate fingerprints when state recovers from a phantom.

        P1 fix (2026-05-02 CSK vs MI post-mortem §Issue 3): gates
        whose state encodes "the last time wickets advanced" are
        one-way counters that don't observe downward corrections.
        ``_last_autodismiss_wickets`` is the load-bearing case — when
        the F55 phantom 47/3 commit was reverted by POISON-RECAL the
        counter stayed at 3, blocking new-batter activation for 195
        frames until real wickets caught up (Naman Dhir / Suryakumar
        Yadav both rejected as "extractor hallucination").

        Call this from every phantom-recovery trigger (POISON-RECAL,
        consensus correction, wickets regression accept). Idempotent
        and safe when no actual regression occurred.
        """
        try:
            new_wkts_i = (int(new_wickets)
                          if new_wickets is not None else 0)
        except (ValueError, TypeError):
            new_wkts_i = 0
        old_dismiss = int(
            getattr(self, "_last_autodismiss_wickets", 0) or 0)
        if old_dismiss > new_wkts_i:
            self._last_autodismiss_wickets = new_wkts_i
            log.info(
                f"[GATE-RESYNC] _last_autodismiss_wickets "
                f"{old_dismiss}→{new_wkts_i} (source={source})")
        # Active-batter rebuild (B2): drop tentative/unwitnessed FOW
        # entries above the new wickets count and reactivate any
        # batter whose only dismissal record was that tentative FOW.
        # Confirmed/witnessed entries are preserved (see _add_fow
        # immutability rules).
        _kept_fow = []
        _reactivated: list[str] = []
        for _f in self.fall_of_wickets:
            try:
                _wn = int(_f.get("wicket") or 0)
            except (ValueError, TypeError):
                _wn = 0
            _is_tentative = bool(
                _f.get("tentative") or _f.get("_unwitnessed"))
            if _wn > new_wkts_i and _is_tentative:
                _bn = _f.get("batter")
                if _bn:
                    _key = self._find_card_key(_bn, self.batting_card)
                    if (_key and self.batting_card.get(_key, {}).get(
                            "status") == "out"):
                        self.batting_card[_key]["status"] = "batting"
                        self.batting_card[_key]["dismissal"] = None
                        _reactivated.append(_key)
                log.info(
                    f"[GATE-RESYNC] Dropping tentative FOW W{_wn} "
                    f"({_bn or 'unknown'}) — wickets reset to "
                    f"{new_wkts_i} (source={source})")
                continue
            _kept_fow.append(_f)
        if len(_kept_fow) != len(self.fall_of_wickets):
            self.fall_of_wickets = _kept_fow
        if _reactivated:
            log.info(
                f"[GATE-RESYNC] Reactivated batters: {_reactivated}")
        self._missing_batter_streak = {}
        if new_wkts_i == 0:
            self._wickets_confirmed_frames_at_zero = 0

    def force_reset_score(self, new_score: int, *, reason: str,
                          frame: int = 0) -> bool:
        """High-confidence escape hatch around the regression-rejection
        predicate at :1224 (`if v < cur_int: return False`). Caller
        surface limited to recovery paths that have already gathered
        out-of-band evidence the committed score is wrong (cold-start
        over-read recovery, state-recovery aggregator, poison-streak
        watchdog). Emits SCORE-FORCE-RESET trace tag for audit.
        """
        try:
            v = int(new_score)
        except (ValueError, TypeError):
            return False
        if v < 0 or v > 320:
            return False
        cur = self._inn.get("score")
        self._inn["score"] = v
        try:
            self._tracker.confirmed["score"] = v
        except (AttributeError, KeyError, TypeError):
            pass
        log.info(
            f"[SCORE-FORCE-RESET] {cur}→{v} (reason={reason})")
        if _trace is not None:
            try:
                _trace.get_recorder().record(
                    tag="SCORE-FORCE-RESET",
                    old_score=cur,
                    new_score=v,
                    reason=reason,
                    frame_id=str(frame))
            except Exception:
                pass
        return True

    def update_batter(self, name: str, runs: int | None = None,
                      balls: int | None = None, fours: int | None = None,
                      sixes: int | None = None, striker: bool | None = None,
                      frame: int = 0,
                      runs_delta: int | None = None,
                      balls_delta: int | None = None,
                      fours_delta: int | None = None,
                      sixes_delta: int | None = None) -> bool:
        if any(d is not None for d in
               (runs_delta, balls_delta, fours_delta, sixes_delta)):
            return self._apply_batter_delta(
                name,
                int(runs_delta or 0), int(balls_delta or 0),
                int(fours_delta or 0), int(sixes_delta or 0),
                frame=frame)
        # A2 part 2 (2026-05-14): DERIVATION-STRIP-DIVERGENCE-BATTER.
        # Audit-only comparison of the incoming strip read against the
        # derived batting_card[X] before the strip kwargs are coerced
        # to None below.  Strip never overrides; this fires when the
        # event-derivation path and the strip view drift apart, which
        # signals an under-firing event detector or a strip OCR
        # mis-attribution (F438-class row scramble).
        if _trace is not None and name in self.batting_card:
            try:
                _d = self.batting_card[name]
                _d_runs = int(_d.get("runs") or 0)
                _d_balls = int(_d.get("balls") or 0)
                _d_fours = int(_d.get("fours") or 0)
                _d_sixes = int(_d.get("sixes") or 0)
                _s_runs = int(runs) if runs is not None else None
                _s_balls = int(balls) if balls is not None else None
                _s_fours = int(fours) if fours is not None else None
                _s_sixes = int(sixes) if sixes is not None else None
                _div = False
                if (_s_runs is not None
                        and abs(_s_runs - _d_runs)
                        / max(1, _d_runs) > 0.10):
                    _div = True
                if _s_balls is not None and abs(_s_balls - _d_balls) > 1:
                    _div = True
                if _s_fours is not None and _s_fours != _d_fours:
                    _div = True
                if _s_sixes is not None and _s_sixes != _d_sixes:
                    _div = True
                if _div:
                    _trace.get_recorder().record(
                        tag="DERIVATION-STRIP-DIVERGENCE-BATTER",
                        batter=name,
                        derived={
                            "runs": _d_runs, "balls": _d_balls,
                            "fours": _d_fours, "sixes": _d_sixes,
                        },
                        strip_observed={
                            "runs": _s_runs, "balls": _s_balls,
                            "fours": _s_fours, "sixes": _s_sixes,
                        },
                        frame_id=str(frame))
            except Exception:
                pass
        # A2 part 1 (2026-05-14): derivation-only batter stats.
        # Strip-driven stat fields (runs/balls/fours/sixes) no longer
        # write to batting_card[X].  The identity-resolution + status-
        # gate + XI + opposition-reject path below still runs on every
        # call so striker_tracker / non_striker_tracker keep getting
        # name observations.  The event-driven _apply_batter_delta path
        # remains the sole writer to entry.runs/.balls/.fours/.sixes.
        # See files/docs/investigations/derivation_only_stats_design.md.
        # This also makes the f043c5d "strip wins if monotonic >=
        # derived" runs-monotonic guard at L2296+ dead code — the
        # `new_r is not None` precondition fails for every entry.  Code
        # left in place for the same blast-radius reason as A1 part 1's
        # corresponding bowler-stale gates: removing the dead branches
        # requires bisection-friendly follow-up commits, and they don't
        # cost runtime once the kwargs are None.
        runs = None
        balls = None
        fours = None
        sixes = None
        resolved = self.resolve_name(name)
        if resolved is None:
            log.warn(f"Batter '{name}' not in any squad")
            return False

        # Guard: reject if player is in the bowling squad (opposition)
        bowl_key = self._find_card_key(resolved, self.bowling_card)
        if bowl_key is not None:
            log.warn(f"Batter '{name}' is in bowling squad "
                     f"(opposition) — rejecting")
            return False

        card_key = self._find_card_key(resolved, self.batting_card)
        if card_key is None:
            log.warn(f"Batter '{name}' not in batting card"
                     f" (resolved: {resolved})")
            return False
        name = card_key

        entry = self.batting_card[name]
        team_el = self.batting_team
        kind_top, rsn_top = ("ok", "")
        if team_el and self._team_match_membership.get(team_el):
            kind_top, rsn_top = self.is_eligible_to_bat_or_bowl(name, team_el)
            if kind_top == "reject":
                log.info(
                    f"[XI-GATE] reject — Batter '{name}' is {rsn_top} — "
                    f"rejecting")
                return False
        if kind_top == "candidate" and entry["status"] == "batting":
            log.info(
                f"[XI-GATE] reject — Batter '{name}' sub-pool with "
                f"active card state — rejecting")
            return False

        if striker is not None:
            slot_k = "s" if striker else "n"
            prev_slot = self._batter_slot_last_identity.get(slot_k)
            if prev_slot is not None and prev_slot != name:
                self._reset_batter_consensus_for(name)
            self._batter_slot_last_identity[slot_k] = name

        if entry["status"] == "out":
            # Batch F (2026-05-04, wicket-on-wicket bat1 regression).
            # Refuse early when the dismissal was sourced from a wicket
            # ball event — the strip routinely shows the just-dismissed
            # batter for 1-2 frames after the wicket commits (cache lag),
            # which previously tripped the 2-frame UN-DISMISS counter
            # and resurrected the dismissed batter (PBKS innings F107
            # → F128, Stoinis re-emerging on Jansen's wicket). Orthogonal
            # to the witnessed-FOW gate below: wicket-ball-event is
            # canonical regardless of FOW enrichment timing.
            if entry.get("dismissal_source") == "wicket_ball_event":
                log.warn(f"[INVARIANT] Refusing to un-dismiss '{name}' "
                         f"— dismissal sourced from wicket ball event "
                         f"(strip read suppressed)")
                return False
            # Fix 1 (2026-04-25, P0-A active-batter invariants).
            # Refuse to un-dismiss a batter that FOW has witnessed as
            # actually out.  The un-dismiss path was originally added
            # for *auto-dismiss-of-wrong-batter* recovery (placeholder
            # FOW, no `_witnessed`), but during DC vs PBKS F339 it
            # also resurrected Pathum Nissanka — a witnessed dismissal
            # — when Scout misread a phase-economy graphic as a live
            # batter strip.  Witnessed FOW is the canonical "this
            # batter is out" record and overrides repeated strip reads.
            if self._is_witnessed_dismissal(name):
                log.warn(f"[INVARIANT] Refusing to un-dismiss '{name}' "
                         f"— witnessed FOW entry exists "
                         f"(strip read suppressed)")
                return False
            self._dismissed_recovery.setdefault(name, 0)
            self._dismissed_recovery[name] += 1
            count = self._dismissed_recovery[name]
            # Bug fix: lowered consensus from 3 → 2 frames so a
            # wrongly-dismissed batter (auto-dismiss picked the wrong
            # member of the pair on a wicket) gets back on the UI in
            # ~10s instead of 30+s. The un-dismiss carries the same
            # safety as before — un-dismissing also auto-deactivates
            # the OTHER batter who is no longer showing on the strip
            # (the actual dismissee), keeping pair size at 2.
            if count < 2:
                log.warn(f"Batter {name} dismissed but seen again "
                         f"({count}/2) — waiting for consensus")
                return False
            log.info(f"[UN-DISMISS] {name} appeared on strip for "
                     f"{count} consecutive frames — reactivating "
                     f"(likely auto-dismiss of wrong batter)")
            entry["status"] = "batting"
            entry["dismissal"] = None
            self._dismissed_recovery.pop(name, None)
            # If 2 batters already active, auto-dismiss one
            active = [k for k, v in self.batting_card.items()
                      if v["status"] == "batting"]
            if len(active) > 2:
                # Deactivate the one NOT in extractor output
                for a in active:
                    if a != name and (self.batting_card[a].get("runs") is None
                                     or self.batting_card[a].get("runs") == 0):
                        self.batting_card[a]["status"] = "yet_to_bat"
                        self.batting_card[a]["runs"] = None
                        self.batting_card[a]["balls"] = None
                        log.info(f"[UN-DISMISS] Deactivated {a} to make "
                                 f"room for {name}")
                        break

        active = [k for k, v in self.batting_card.items()
                  if v["status"] == "batting"]

        was_yet_to_bat = entry["status"] == "yet_to_bat"
        admitted_from_live_pair = False
        if entry["status"] == "yet_to_bat":
            if team_el and self._team_match_membership.get(team_el):
                kind_y, _rsn_y = self.is_eligible_to_bat_or_bowl(
                    name, team_el)
                if kind_y == "candidate":
                    if self._team_match_membership[team_el]["impact_used"]:
                        log.info(
                            f"[XI-GATE] reject — team "
                            f"already used impact player, '{name}' "
                            f"rejected as second activation")
                        return False
                    _streak = self._bump_impact_streak(
                        team_el, name, frame)
                    if _streak < 3:
                        return False
                    self._promote_impact_player(team_el, name)
                elif kind_y == "ok":
                    self._clear_impact_streak_team(team_el)
            if len(active) >= 2 and name not in active:
                wk = int(self._inn.get("wickets") or 0)
                try:
                    ov_f = float(self._inn.get("overs") or "0")
                except (ValueError, TypeError):
                    ov_f = 0.0
                if wk == 0 and ov_f < 2.0:
                    replaced = False
                    for a in active:
                        ae = self.batting_card[a]
                        if (ae.get("runs") or 0) == 0 and \
                                (ae.get("balls") or 0) <= 1:
                            ae["status"] = "yet_to_bat"
                            ae["runs"] = None
                            ae["balls"] = None
                            self._tracker.force_set(f"bat:{a}:runs", None)
                            self._tracker.force_set(f"bat:{a}:balls", None)
                            log.warn(f"Deactivated {a} (0(0) at 0 wkt "
                                     f"— likely wrong initial activation)")
                            replaced = True
                            break
                    if not replaced:
                        log.warn(f"Batter '{name}' rejected — 2 active "
                                 f"with stats: {active}")
                        return False
                elif wk > 0 and self._extractor_batter_names:
                    dismissed = self._auto_dismiss_for_new_batter(
                        active, name)
                    if not dismissed:
                        log.warn(f"Batter '{name}' rejected — 2 batters "
                                 f"already active: {active}")
                        return False
                    admitted_from_live_pair = True
                else:
                    log.warn(f"Batter '{name}' rejected — 2 batters "
                             f"already active: {active}")
                    return False
            elif len(active) >= 1 and int(self._inn.get("wickets") or 0) > 0:
                admitted_from_live_pair = True
            entry["status"] = "batting"
            entry["runs"] = 0
            entry["balls"] = 0
            if admitted_from_live_pair:
                self._fresh_batter_admission[name] = {
                    "frame": frame,
                    "team_balls": self._team_balls_seen(),
                }
            log.info(f"Batter activated: {name}")

        old_str = f"{entry['runs']}({entry['balls']})"

        if runs is not None or balls is not None:
            try:
                new_r = int(runs) if runs is not None else None
                new_b = int(balls) if balls is not None else None
            except (ValueError, TypeError):
                new_r, new_b = None, None
            cur_r = entry.get("runs")
            cur_b = entry.get("balls")
            fresh_meta = self._fresh_batter_admission.get(name)
            if (fresh_meta and new_b is not None
                    and (cur_b is None or int(cur_b) <= 2)):
                admitted_at = fresh_meta.get("team_balls")
                now_balls = self._team_balls_seen()
                try:
                    balls_since_admit = max(
                        0, int(now_balls) - int(admitted_at))
                except (TypeError, ValueError):
                    balls_since_admit = 0
                max_fresh_balls = max(3, balls_since_admit + 3)
                if int(new_b) > max_fresh_balls:
                    log.warn(
                        f"[NEW-BATTER-BALLS-GATE] {name}: proposed "
                        f"{new_r}({new_b}) exceeds fresh-admission "
                        f"ceiling {max_fresh_balls} balls "
                        f"(since_admit={balls_since_admit}); "
                        f"dropping row")
                    new_r = None
                    new_b = None
                    self._last_row_rejected_frame = frame
            elif fresh_meta and new_b is not None and int(new_b) > 2:
                self._fresh_batter_admission.pop(name, None)
            # CLONE GUARD: if the proposed (runs, balls) tuple exactly
            # matches the OTHER active batter's current stats, reject
            # the update. This is almost always the LLM reading the
            # wrong row of the strip and copying batter A's line into
            # batter B's slot. Allowing it produces the symptom where
            # both batters show identical stats (e.g. both 12(8)) which
            # is impossible unless they really did face the same number
            # of balls AND scored the same — extraordinarily rare and
            # the broadcast will re-confirm on subsequent frames.
            #
            # We DO allow the clone if either:
            #   - the new tuple is (0, 0) — fresh activation, common.
            #   - the new tuple matches what THIS entry already has —
            #     idempotent re-write, no harm.
            # Otherwise defer until the broadcast strip confirms.
            if (new_r is not None and new_b is not None
                    and not (new_r == 0 and new_b == 0)
                    and not (cur_r == new_r and cur_b == new_b)):
                _other_match = None
                for _other_name, _other_entry in self.batting_card.items():
                    if _other_name == name:
                        continue
                    if _other_entry.get("status") != "batting":
                        continue
                    _o_r = _other_entry.get("runs")
                    _o_b = _other_entry.get("balls")
                    if (_o_r is not None and _o_b is not None
                            and int(_o_r) == new_r
                            and int(_o_b) == new_b
                            and not (int(_o_r) == 0 and int(_o_b) == 0)):
                        _other_match = _other_name
                        break
                if _other_match is not None:
                    log.warn(
                        f"[CLONE-REJECT] {name}: proposed "
                        f"{new_r}({new_b}) is identical to "
                        f"{_other_match}'s current line — likely a "
                        f"misread row of the batting strip. Keeping "
                        f"existing {cur_r}({cur_b}); awaiting "
                        f"broadcast re-confirmation.")
                    new_r = None
                    new_b = None
                    self._last_row_rejected_frame = frame
            # === Runs-monotonic guard (detection layer) ===
            # Two clauses below detect runs regressions that almost
            # always indicate row-misread phantoms.  Both null both
            # fields (whole-row invalidation).  The Layer 4 release
            # block right after captures consecutive rejections of
            # the same value so a real truth-lock-in window can be
            # broken via consensus.  See `__init__` doc on
            # `_runs_reject_streak`.
            _runs_regression_rejected = False
            _runs_regression_value: int | None = None
            _runs_regression_balls: int | None = None
            if (new_r is not None and new_r == 0
                    and cur_r is not None and int(cur_r) > 5):
                _runs_regression_rejected = True
                _runs_regression_value = 0
                _runs_regression_balls = (
                    int(new_b) if new_b is not None else None)
                log.warn(f"Batter '{name}' runs regression "
                         f"{cur_r}→0 rejected — dropping balls "
                         f"{new_b} too (whole-row invalidation)")
                new_r = None
                new_b = None
                self._last_row_rejected_frame = frame
            elif (new_r is not None and cur_r is not None
                    and int(cur_r) - int(new_r) > 5):
                _runs_regression_rejected = True
                _runs_regression_value = int(new_r)
                _runs_regression_balls = (
                    int(new_b) if new_b is not None else None)
                log.warn(f"Batter '{name}' runs regression "
                         f"{cur_r}→{new_r} (-{int(cur_r) - int(new_r)}) "
                         f"rejected — dropping balls {new_b} too "
                         f"(whole-row invalidation)")
                new_r = None
                new_b = None
                self._last_row_rejected_frame = frame

            # === Layer 4 (Fix 12, 2026-04-26): rejection-consensus
            # release on the runs-monotonic guard. ===
            #
            # Mirrors POISON-STREAK at `test_pipeline.py:6246`.  When
            # the same proposed runs value is rejected
            # `_RUNS_REJECT_RELEASE_N` times consecutively for this
            # batter, the held `cur_r` is almost certainly a stale
            # phantom (the truth-stream has been knocking on the door
            # without being let in).  Release: force-set the tracker
            # baseline to the rejected value so the legitimate stream
            # can commit; balls counterpart force-set too if it was
            # present in the rejected row.  Streak is per-batter and
            # field-specific to runs (balls has its own guard).
            #
            # Reset semantics:
            #   * different rejected value → restart counter at 1
            #     (the held lock-in target is no longer constant)
            #   * legitimate acceptance (no rejection this frame for
            #     this batter) → drop the entry entirely (the
            #     phantom window has closed naturally)
            #
            # Idempotent: post-release the streak is reset, so the
            # next rejection (if any) starts a fresh count.  No
            # double-release.
            if _runs_regression_rejected:
                _streak = self._runs_reject_streak.setdefault(
                    name, {"value": None, "count": 0})
                if _streak["value"] == _runs_regression_value:
                    _streak["count"] += 1
                else:
                    _streak["value"] = _runs_regression_value
                    _streak["count"] = 1
                log.info(
                    f"  [RUNS-REJECT-STREAK] {name}="
                    f"{_runs_regression_value} streak="
                    f"{_streak['count']}/"
                    f"{self._RUNS_REJECT_RELEASE_N} "
                    f"(cur={cur_r} held)")
                if _streak["count"] >= self._RUNS_REJECT_RELEASE_N:
                    log.warn(
                        f"  [RUNS-REJECT-RELEASE] {name}: "
                        f"{_streak['count']} consecutive "
                        f"rejections of runs="
                        f"{_runs_regression_value} "
                        f"(cur={cur_r}) — accepting as new "
                        f"truth (current value is stale "
                        f"phantom). force_set bat:{name}:runs"
                        f"{', balls' if _runs_regression_balls is not None else ''}.")
                    try:
                        self._tracker.force_set(
                            f"bat:{name}:runs",
                            _runs_regression_value)
                        entry["runs"] = _runs_regression_value
                        if _runs_regression_balls is not None:
                            self._tracker.force_set(
                                f"bat:{name}:balls",
                                _runs_regression_balls)
                            entry["balls"] = _runs_regression_balls
                    except Exception as _e:  # noqa: BLE001
                        log.debug(
                            f"  [RUNS-REJECT-RELEASE] "
                            f"force_set swallowed: {_e}")
                    _streak["value"] = None
                    _streak["count"] = 0
                    # Truth row was right after all — clear the
                    # row-rejected flag so downstream broadcast-
                    # indicator striker updates aren't suppressed
                    # on this frame for the wrong reason.
                    self._last_row_rejected_frame = -1
            elif new_r is not None:
                # Legitimate runs observation for this batter on
                # this frame — phantom window closed, drop the
                # streak entry so a future unrelated rejection
                # starts a clean counter.
                self._runs_reject_streak.pop(name, None)
            # Reject balls decreasing — but tolerate a small (-2)
            # broadcast correction. The pipeline routinely over-counts
            # balls by 1-2 because an inferred event lands a frame
            # before the broadcast strip updates, OR the LLM occasionally
            # double-counts when the number is partially obscured. The
            # broadcast absolute value is authoritative; we trust it
            # within a 2-ball window. Anything beyond -2 is treated as
            # a stale/misread frame.
            #
            # 2026-04-21 (Issue 5):  When we detect a >2 balls regression
            # the Scout read is almost certainly a row-bleed or OCR
            # confusion of the batter strip — see Travis Head F51 live
            # log where "Head 21(15)" appeared in parallel with
            # "Abhishek 34(15)" while Head's confirmed was 23 balls.
            # The balls half of the row is clearly bad, and that
            # contaminates the runs half too (Head's runs actually
            # came from a different row's column).  Reject the WHOLE
            # batter row — both runs and balls — so the invalid
            # read can't leak through as a runs-only update and
            # then dislodge striker state downstream.
            if (new_b is not None and cur_b is not None
                    and int(new_b) < int(cur_b) - 2):
                log.warn(f"Batter '{name}' balls regression "
                         f"{cur_b}→{new_b} rejected (>2 balls backward)"
                         f" — dropping runs={new_r} too (whole-row "
                         f"invalidation)")
                new_b = None
                new_r = None
                # Flag the scoreboard so the main loop can skip its
                # broadcast-indicator striker update on this frame —
                # if the row is a misread the striker asterisk read
                # from the same string is untrustworthy too.
                self._last_row_rejected_frame = frame
            elif (new_b is not None and cur_b is not None
                    and int(new_b) < int(cur_b)):
                _delta = int(cur_b) - int(new_b)
                log.info(f"[BALLS CORRECTED] {name}: "
                         f"{cur_b}→{new_b} (-{_delta}, "
                         f"broadcast over-count recovery)")
                # Force-set so the consensus tracker doesn't keep
                # rejecting the lower value indefinitely. Broadcast
                # is authoritative for absolute values.
                self._tracker.force_set(f"bat:{name}:balls", int(new_b))
                entry["balls"] = int(new_b)

            # Couple runs+balls: submit both, then check if runs
            # was deferred by tracker while balls was accepted.
            # If so, revert balls to keep them in sync.
            old_r = entry.get("runs")
            old_b = entry.get("balls")
            eff_r = None
            eff_b = None
            if new_r is not None:
                eff_r = self._tracker.update(
                    f"bat:{name}:runs", new_r, frame)
                if eff_r is not None:
                    entry["runs"] = eff_r
            # Investigation 8 (2026-05-14): batter-balls invariant gates.
            # Two physical impossibilities guarded here:
            #   (I)  Same frame increments two different batters' balls
            #        — cricket has one striker per delivery.
            #   (H)  Sum of all batters' balls exceeds team legal balls
            #        — striker-tracker oscillation can inflate one
            #        batter's count well above broadcast ground truth.
            # When either fires, suppress the balls update for this
            # call (commit runs as usual; balls will converge on the
            # next consensus-clean read).
            if new_b is not None:
                # Reset per-frame state on frame boundary
                if frame != self._batter_balls_frame:
                    self._batter_balls_frame = frame
                    self._batter_balls_incremented_this_frame = set()
                _ob = int(old_b) if old_b is not None else 0
                _nb = int(new_b)
                _bumping = (_nb > _ob)
                # (I) Double-increment guard
                if (_bumping
                        and self._batter_balls_incremented_this_frame
                        and name not in (
                            self._batter_balls_incremented_this_frame)):
                    log.warn(
                        f"  [BATTER-BALLS-DOUBLE-INCREMENT-FRAME] "
                        f"frame={frame} '{name}' balls {_ob}→{_nb} "
                        f"suppressed — already incremented "
                        f"{sorted(self._batter_balls_incremented_this_frame)} "
                        f"this frame (one striker per delivery)")
                    if _trace is not None:
                        try:
                            _trace.get_recorder().record(
                                tag="BATTER-BALLS-DOUBLE-INCREMENT-FRAME",
                                frame_id=str(frame),
                                batters=sorted(
                                    self._batter_balls_incremented_this_frame
                                    | {name}),
                                suppressed=name)
                        except Exception:
                            pass
                    new_b = None  # skip balls update; runs already committed
                # (H) Sum-invariant guard
                elif _bumping:
                    _team_legal = self._team_balls_seen()
                    _sum_balls = sum(
                        int(c.get("balls") or 0)
                        for c in self.batting_card.values())
                    _delta = _nb - _ob
                    if (_team_legal > 0
                            and _sum_balls + _delta > _team_legal + 1):
                        log.warn(
                            f"  [BATTER-BALLS-INVARIANT-FREEZE] "
                            f"sum_balls={_sum_balls} + "
                            f"Δ({name}={_delta}) > team_legal_balls="
                            f"{_team_legal}+1 — striker-tracker "
                            f"oscillation suspected; freezing balls "
                            f"update")
                        if _trace is not None:
                            try:
                                _trace.get_recorder().record(
                                    tag="BATTER-BALLS-INVARIANT-FREEZE",
                                    frame_id=str(frame),
                                    sum_current=_sum_balls,
                                    team_balls=_team_legal,
                                    attempted_update=name,
                                    attempted_delta=_delta)
                            except Exception:
                                pass
                        new_b = None
            if new_b is not None:
                eff_b = self._tracker.update(
                    f"bat:{name}:balls", new_b, frame)
                if eff_b is not None:
                    entry["balls"] = eff_b
                    # Mark this batter as having incremented this frame
                    # so subsequent calls in the same frame trip (I).
                    if int(eff_b) > (int(old_b) if old_b is not None
                                     else 0):
                        self._batter_balls_incremented_this_frame.add(
                            name)
            # Fix 18 (Layer 3, 2026-04-26): track most-recent runs
            # advance for the cap-reset Path C hybrid.  The frame
            # when each batter's runs last increased is the
            # primary signal for "which batter is most likely the
            # phantom inflation source" when the sum-cap fires.
            try:
                _old_r_i = (int(old_r) if old_r is not None
                            else None)
                _eff_r_i = (int(eff_r) if eff_r is not None
                            else None)
                if (_eff_r_i is not None
                        and (_old_r_i is None
                             or _eff_r_i > _old_r_i)):
                    self._last_runs_advance[name] = {
                        "frame": frame,
                        "from": _old_r_i,
                        "to": _eff_r_i,
                    }
            except (ValueError, TypeError):
                pass
            # If runs was deferred (didn't change) but balls jumped,
            # revert balls to prevent impossible stat lines like 0(14)
            if (new_r is not None and new_b is not None
                    and eff_r == old_r and eff_b != old_b
                    and old_r is not None and int(old_r) == 0
                    and new_r > 0):
                entry["balls"] = old_b
                self._tracker.force_set(f"bat:{name}:balls", old_b)
                log.info(f"Batter '{name}' balls deferred with runs "
                         f"({old_r},{old_b}) — waiting for runs consensus")

        # Sanity-check fours/sixes against runs. Cricket physics:
        # 4*fours + 6*sixes <= runs. Broadcast career-stat overlays
        # ("FOURS: 145") leak into our regex; reject anything that
        # cannot fit the batter's current scoring ceiling.
        _cur_runs_for_chk = entry.get("runs")
        _new_fours = int(fours) if fours is not None else entry.get("fours")
        _new_sixes = int(sixes) if sixes is not None else entry.get("sixes")
        _ok_fs = True
        if _cur_runs_for_chk is not None:
            _f = int(_new_fours or 0)
            _s = int(_new_sixes or 0)
            if 4 * _f + 6 * _s > int(_cur_runs_for_chk):
                _ok_fs = False
                log.warn(
                    f"[FS-REJECT] {name}: fours={_f} sixes={_s} "
                    f"impossible vs runs={_cur_runs_for_chk}; "
                    f"keeping previous "
                    f"({entry.get('fours')}/{entry.get('sixes')})")
        if _ok_fs:
            if fours is not None:
                entry["fours"] = int(fours)
            if sixes is not None:
                entry["sixes"] = int(sixes)

        new_str = f"{entry['runs']}({entry['balls']})"
        if old_str != new_str:
            self._log("batter", name, old_str, new_str, frame)

        # Striker self-collision guard (Fix 5, 2026-04-25 inter-match
        # commit; see backlog "Striker self-collision in update_batter").
        # Without this guard a transitional review-graphic that lists
        # the two batter rows in swapped order can drive
        # update_batter(name, striker=False) onto a name that the
        # previous frame's swap already wrote into _inn["striker"],
        # ending in striker == non.  Observed at ~8% of frames
        # in 2026-04-25 RR-vs-SRH match-2 (sample F174-F176, F290+).
        # WS payload is unaffected (uses ScoreManager) but commentary
        # subsystems (storyteller / analyst / colour) and persisted
        # DETAIL telemetry both read sb._inn directly and produce
        # "X faces X" prose / zero-length partnership against the
        # collided slot.  Refuse the write rather than fight a swap
        # the next frame should re-establish anyway.
        if striker is not None and entry.get("status") != "batting":
            log.warn(
                f"  [STRIKER-STATUS-GATE] Refusing role flip for "
                f"{name} — status={entry.get('status')!r}")
        elif striker is True:
            # AUTHORITATIVE-SBINN-READ: Fix 5 collision guard — write-site
            # precondition on legacy _inn slot; SM read would deselect branch.
            # striker_path_b_read_audit.md R1 §2.1.1
            if self._inn.get("non") == name:
                log.warn(
                    f"  [STRIKER-COLLISION] Refusing striker={name} "
                    f"— already non; would self-collide")
            else:
                self._inn["striker"] = name
        elif striker is False:
            # AUTHORITATIVE-SBINN-READ: Fix 5 collision guard (mirror branch).
            # striker_path_b_read_audit.md R2 §2.1.1
            if self._inn.get("striker") == name:
                log.warn(
                    f"  [STRIKER-COLLISION] Refusing non="
                    f"{name} — already striker; would self-collide")
            else:
                self._inn["non"] = name

        # Path B note (2026-04-28): pipeline prefers ScoreManager for live
        # striker reads; ``apply_scorer_decision`` mirrors SM+_inn via
        # ``_set_inn_slot_with_sm_mirror``.  These ``_inn`` writes stay as
        # Fix 5 backstop for LLM ``striker=`` flags, gated by
        # ``[STRIKER-STATUS-GATE]`` and ``[STRIKER-COLLISION]`` above.

        return True

    # ------------------------------------------------------------------
    # Boundary accumulator — derive fours/sixes from ball events (P1-5)
    # ------------------------------------------------------------------
    def accumulate_boundary(self, striker_name: str | None,
                            kind: str) -> bool:
        """Increment striker's fours/sixes counter from a ball event.

        Called from the main pipeline when a ball event with
        ``type == "FOUR"`` or ``"SIX"`` fires. The ball-event type
        already encodes "the ball reached the boundary" (as distinct
        from "4/6 runs were scored"), which gives us the right edge-
        case behaviour for free:

          * Normal FOUR (type=FOUR, runs=4)       → increments
          * Wide-four (type=EXTRA, runs=5)        → NOT called
          * Overthrow-six (type=SIX, runs=6)      → increments
          * All-run four (type=4_RUNS, runs=4)    → NOT called
          * Bye four (type=EXTRA, runs=4)         → NOT called

        Rejects quietly (returns False + logs) when:
          * striker_name is None / empty
          * batting_card has no entry for striker (squad mismatch)
          * card entry's status != "batting" (dismissed/not-yet-in)
          * resulting 4*fours+6*sixes would exceed the striker's
            currently-tracked runs (cricket invariant). Strip reads
            usually converge within the next frame or two, so a
            spurious reject here is self-healing.
        """
        if not striker_name or kind not in ("four", "six"):
            self._bdy_skip("bad_input")
            return False
        card = self.batting_card.get(striker_name) if self.batting_card else None
        if not card:
            log.info(
                f"  [BDY-ACC] Skip {kind} for striker='{striker_name}'"
                f" — not in batting_card")
            self._bdy_skip("not_in_card")
            return False
        if card.get("status") != "batting":
            log.info(
                f"  [BDY-ACC] Skip {kind} for striker='{striker_name}'"
                f" — card.status={card.get('status')!r}")
            self._bdy_skip(f"status_{card.get('status')}")
            return False

        cur_f = int(card.get("fours") or 0)
        cur_s = int(card.get("sixes") or 0)
        new_f = cur_f + (1 if kind == "four" else 0)
        new_s = cur_s + (1 if kind == "six" else 0)

        cur_r = card.get("runs")
        if cur_r is not None and (4 * new_f + 6 * new_s) > int(cur_r):
            # Invariant violation — runs hasn't caught up yet (or the
            # striker is wrong). Skip; the next frame will re-fire
            # only if a genuine FOUR/SIX event lands again, which
            # only happens on the next boundary.
            #
            # Expected to fire occasionally (race between ball-event
            # and strip run-total consensus). Monitor the
            # invariant-skip rate post-deploy via _bdy_skip_counts;
            # if it's <5% of boundary events, Option A (accept the
            # occasional miss) is fine. If it's >5%, revisit with
            # Option B (queue-and-retry).
            log.info(
                f"  [BDY-ACC] Skip {kind} for '{striker_name}' — "
                f"would violate 4f+6s<=runs "
                f"(new {new_f}/{new_s} vs runs={cur_r})")
            self._bdy_skip("invariant")
            return False

        card["fours"] = new_f
        card["sixes"] = new_s
        log.info(
            f"  [BDY-ACC] {striker_name} {kind.upper()} → "
            f"fours={new_f} sixes={new_s} "
            f"(runs={cur_r})")
        return True

    def _bdy_skip(self, reason: str) -> None:
        """Reason-tagged counter for boundary-accumulator skips.

        Buckets: `not_in_card`, `status_<x>`, `invariant`, `bad_input`.
        Lets post-deploy monitoring distinguish the invariant race
        (expected, self-healing) from the other classes (genuine
        striker/card issues that the upstream WS-SCRUB should be
        catching too).
        """
        counts = getattr(self, "_bdy_skip_counts", None)
        if counts is None:
            counts = {}
            self._bdy_skip_counts = counts
        counts[reason] = counts.get(reason, 0) + 1

    # ------------------------------------------------------------------
    # Event-driven stat accumulation (single-writer derivation path).
    # Bypasses extractor-trust guards (consensus, XI-gate consensus,
    # graphic-gate, wickets-regression). Caller is the SM event log,
    # not the broadcast strip — guards that exist to defend against
    # bad detection are by definition irrelevant here. Preserved
    # invariants: row must exist, must be in playing XI, batter must
    # not be dismissed.
    # ------------------------------------------------------------------
    def _apply_batter_delta(self, name: str, runs_delta: int,
                            balls_delta: int, fours_delta: int,
                            sixes_delta: int, frame: int = 0) -> bool:
        resolved = self.resolve_name(name)
        if resolved is None:
            log.warn(f"  [BAT-DELTA] '{name}' not in any squad — drop")
            return False
        card_key = self._find_card_key(resolved, self.batting_card)
        if card_key is None:
            log.warn(f"  [BAT-DELTA] '{name}' not in batting card "
                     f"(resolved: {resolved})")
            return False
        name = card_key
        entry = self.batting_card[name]
        if not entry.get("is_playing_xi", True):
            log.warn(f"  [BAT-DELTA] '{name}' not in playing XI — drop")
            return False
        if entry["status"] == "out":
            log.warn(
                f"  [BAT-DELTA] refusing event-driven increment for "
                f"'{name}' — status=out")
            return False
        if entry["status"] == "yet_to_bat":
            entry["status"] = "batting"
        # A2 part 1: BATTING-CARD-CREATED / -RESUMED on first event-
        # delta for this batter.  Distinguished by whether the entry
        # already carries non-zero stats (RESUMED) — e.g. cache-resume
        # or innings re-init populated the slot — vs a fresh first
        # delivery (CREATED).  Mirrors A1 part 1's bowler hook
        # semantics; lazy-init via getattr so SB __init__ doesn't need
        # to be touched.
        if name not in getattr(
                self, "_batting_card_first_event_seen", set()):
            if not hasattr(self, "_batting_card_first_event_seen"):
                self._batting_card_first_event_seen = set()
            self._batting_card_first_event_seen.add(name)
            try:
                _ent_runs = int(entry.get("runs") or 0)
                _ent_balls = int(entry.get("balls") or 0)
                _ent_fours = int(entry.get("fours") or 0)
                _ent_sixes = int(entry.get("sixes") or 0)
                _resumed = (
                    _ent_runs > 0 or _ent_balls > 0
                    or _ent_fours > 0 or _ent_sixes > 0)
                if _trace is not None:
                    _trace.get_recorder().record(
                        tag=("BATTING-CARD-RESUMED" if _resumed
                             else "BATTING-CARD-CREATED"),
                        batter=name,
                        frame_id=str(frame),
                        existing_runs=_ent_runs,
                        existing_balls=_ent_balls,
                        existing_fours=_ent_fours,
                        existing_sixes=_ent_sixes)
            except Exception:
                pass
        cur_runs = int(entry.get("runs") or 0)
        cur_balls = int(entry.get("balls") or 0)
        cur_fours = int(entry.get("fours") or 0)
        cur_sixes = int(entry.get("sixes") or 0)
        entry["runs"] = cur_runs + runs_delta
        entry["balls"] = cur_balls + balls_delta
        entry["fours"] = cur_fours + fours_delta
        entry["sixes"] = cur_sixes + sixes_delta
        if entry["balls"] > 0:
            entry["sr"] = round(entry["runs"] / entry["balls"] * 100, 2)
        log.info(
            f"  [BAT-DELTA] {name} +runs={runs_delta} +balls={balls_delta} "
            f"+4s={fours_delta} +6s={sixes_delta} → "
            f"runs={entry['runs']} balls={entry['balls']} "
            f"4s={entry['fours']} 6s={entry['sixes']} frame={frame}")
        return True

    def _apply_bowler_delta(self, name: str, runs_delta: int,
                            balls_delta: int, wickets_delta: int,
                            frame: int = 0) -> bool:
        if frame > self._last_bowler_scout_frame:
            self._last_bowler_scout_frame = frame
        resolved = self.resolve_name(name)
        if resolved is None:
            log.warn(f"  [BOWL-DELTA] '{name}' not in any squad — drop")
            return False
        card_key = self._find_card_key(resolved, self.bowling_card)
        if card_key is None:
            log.warn(f"  [BOWL-DELTA] '{name}' not in bowling card "
                     f"(resolved: {resolved})")
            return False
        name = card_key
        entry = self.bowling_card[name]
        if not entry.get("is_playing_xi", True):
            log.warn(f"  [BOWL-DELTA] '{name}' not in playing XI — drop")
            return False
        cur_runs = int(entry.get("runs") or 0)
        cur_wkts = int(entry.get("wickets") or 0)
        cur_balls = int(entry.get("balls") or 0)
        new_balls = cur_balls + balls_delta
        entry["balls"] = new_balls
        entry["runs"] = cur_runs + runs_delta
        entry["wickets"] = cur_wkts + wickets_delta
        # A1 part 2 (2026-05-14): overs now DERIVED from accumulated
        # legal balls.  Strip-driven overs writes were neutralized in
        # part 1; ball-event accumulation is the sole source.
        entry["overs"] = f"{new_balls // 6}.{new_balls % 6}"
        # Transient per-over counters (reset by
        # score_manager._complete_over at over-end after maiden
        # detection).  Drive the BOWLER-MAIDEN-CREDITED trace.
        if balls_delta > 0:
            entry["balls_this_over"] = (
                int(entry.get("balls_this_over") or 0) + balls_delta)
        if runs_delta > 0:
            entry["runs_this_over"] = (
                int(entry.get("runs_this_over") or 0) + runs_delta)
        if new_balls > 0:
            entry["econ"] = round(entry["runs"] / new_balls * 6, 2)
        log.info(
            f"  [BOWL-DELTA] {name} +runs={runs_delta} +balls={balls_delta} "
            f"+wkts={wickets_delta} → runs={entry['runs']} "
            f"overs={entry['overs']} wkts={entry['wickets']} frame={frame}")
        return True

    # ------------------------------------------------------------------
    # Bowler updates — write to pre-built bowling card
    # ------------------------------------------------------------------

    @staticmethod
    def _overs_to_balls(ov) -> int:
        try:
            s = str(ov)
            if "." in s:
                w, b = s.split(".")
                return int(w) * 6 + int(b)
            return int(s) * 6
        except (ValueError, TypeError):
            return 0

    def _bowler_team_over_consensus(
            self, current_bowler: str | None, candidate: str,
            candidate_overs: str | None, read_count: int) -> bool:
        """Use team-over physics to accelerate stale-bowler recovery."""
        if not current_bowler or candidate == current_bowler:
            return False
        if candidate_overs is None or read_count < 2:
            return False
        team_balls = self._team_balls_seen()
        team_ball_in_over = team_balls % 6
        if team_ball_in_over == 0:
            return False
        candidate_ball = self._overs_to_balls(candidate_overs) % 6
        current_overs = (
            self.bowling_card.get(current_bowler, {}).get("overs"))
        current_ball = self._overs_to_balls(current_overs) % 6
        if candidate_ball != team_ball_in_over:
            return False
        if current_overs is None:
            return True
        return current_ball != team_ball_in_over

    def _bowler_plain_consensus_overs_plausible(
            self, overs_str: str | None) -> bool:
        """True if candidate spell overs align with team strip ball index.

        Used only for the vanilla ``_CONSENSUS_N`` flip path (not must_change,
        not `_bowler_team_over_consensus`).  When the strip shows ball *k*
        of the current over, the bowler overlay should show the same *k*
        legal balls into their spell; a stale 4.0 cumulative read shows
        ball index 0 and mismatches mid-over.
        """
        if overs_str is None:
            return True
        try:
            team_b = self._team_balls_seen()
            cand_b = self._overs_to_balls(overs_str)
        except (TypeError, ValueError):
            return True
        return (cand_b % 6) == (team_b % 6)

    def update_bowler(self, name: str, overs: str | None = None,
                      runs: int | None = None, wickets: int | None = None,
                      maidens: int | None = None, frame: int = 0,
                      vision_desc: str | None = None,
                      runs_delta: int | None = None,
                      balls_delta: int | None = None,
                      wickets_delta: int | None = None) -> bool:
        if isinstance(runs, str):
            try: runs = int(runs)
            except (TypeError, ValueError): runs = None
        if isinstance(wickets, str):
            try: wickets = int(wickets)
            except (TypeError, ValueError): wickets = None
        if isinstance(maidens, str):
            try: maidens = int(maidens)
            except (TypeError, ValueError): maidens = None
        if any(d is not None for d in
               (runs_delta, balls_delta, wickets_delta)):
            return self._apply_bowler_delta(
                name,
                int(runs_delta or 0), int(balls_delta or 0),
                int(wickets_delta or 0), frame=frame)
        # A1 part 2 (2026-05-14): DERIVATION-STRIP-DIVERGENCE-BOWLER.
        # Audit-only comparison of the incoming strip read against the
        # derived bowling_card[X] before the strip kwargs are coerced
        # to None below.  Strip never overrides; this fires when the
        # event-derivation path and the strip view drift apart, which
        # signals an under-firing event detector or a strip read of a
        # different bowler (e.g. info-pane cycling).
        if _trace is not None and name in self.bowling_card:
            try:
                _d = self.bowling_card[name]
                _d_runs = int(_d.get("runs") or 0)
                _d_balls = int(_d.get("balls") or 0)
                _d_wkts = int(_d.get("wickets") or 0)
                _s_runs = int(runs) if runs is not None else None
                _s_balls = (
                    self._overs_to_balls(overs)
                    if overs is not None else None)
                _s_wkts = int(wickets) if wickets is not None else None
                _div = False
                if (_s_runs is not None
                        and abs(_s_runs - _d_runs)
                        / max(1, _d_runs) > 0.10):
                    _div = True
                if _s_balls is not None and abs(_s_balls - _d_balls) > 1:
                    _div = True
                if _s_wkts is not None and _s_wkts != _d_wkts:
                    _div = True
                if _div:
                    _trace.get_recorder().record(
                        tag="DERIVATION-STRIP-DIVERGENCE-BOWLER",
                        bowler=name,
                        derived={
                            "runs": _d_runs,
                            "balls": _d_balls,
                            "wickets": _d_wkts,
                        },
                        strip_observed={
                            "runs": _s_runs,
                            "balls": _s_balls,
                            "wickets": _s_wkts,
                        },
                        frame_id=str(frame))
            except Exception:
                pass
        # A1 part 1 (2026-05-14): derivation-only bowler stats.
        # Strip-driven stat fields (overs/runs/wickets/maidens) no
        # longer write to bowling_card[X].  The identity-resolution +
        # consensus + override + bootstrap path below still runs on
        # every call (name observation feeds bowler_tracker).  The
        # event-driven _apply_bowler_delta path remains the sole writer
        # to entry.runs/.wickets/.overs/.balls.  See
        # files/docs/investigations/derivation_only_stats_design.md.
        overs = None
        runs = None
        wickets = None
        maidens = None
        # Fix #2 (2026-04-23): record frame of this Scout bowler read
        # before any early-exit.  BOWLER-AUTO uses this to detect
        # "Scout is actively reading the bowler strip right now" and
        # defer auto-increment rather than racing ahead.  Stamp
        # unconditionally — even rejected reads signal that Scout saw
        # something bowler-shaped in the frame.
        if frame > self._last_bowler_scout_frame:
            self._last_bowler_scout_frame = frame
        resolved = self.resolve_name(name)
        if resolved is None:
            log.warn(f"Bowler '{name}' not in any squad")
            return False
        card_key = self._find_card_key(resolved, self.bowling_card)
        if card_key is None:
            log.warn(f"Bowler '{name}' not in bowling card"
                     f" (resolved: {resolved})")
            return False
        name = card_key

        # === Bowler stats wickets-regression guard (H.2, 2026-05-04) ===
        # Wickets are strictly monotonic within a spell. A proposed
        # wickets value lower than what's already on the card is a
        # cross-match overlay (broadcast feature graphic showing this
        # bowler's stats from a different match) — reject before any
        # downstream coercion. Backstop to the cross-match sentinel in
        # `test_pipeline._detect_overlay_strip_sentinels`. See
        # `files/docs/investigations/cross_match_graphic_overlay_contamination.md`.
        _card_wickets = self.bowling_card.get(name, {}).get("wickets")
        if (wickets is not None
                and _card_wickets is not None
                and wickets < _card_wickets):
            log.warn(
                f"  [BOWLER-STATS-REGRESSION-FIELD] '{name}' "
                f"wickets={wickets}<{_card_wickets} — keeping "
                f"{_card_wickets}, accepting other fields "
                f"(likely cross-match overlay; per-field guard)")
            wickets = _card_wickets

        # Investigation 7A (2026-05-14): bowler-row physics sanity.
        # A column-scrambled VLM read like `VAIBHAV 4-1 (1.2)` (where
        # 4/1 are actually FOURS/SIXES from the adjacent stats panel,
        # not wickets/runs) yields a +N>1 wickets delta that no
        # cricket physics can produce — a bowler takes at most ONE
        # wicket on a single delivery.  Suppress the wicket update
        # field-by-field and continue accepting runs/overs.
        _prev_wkts_for_junk = int(_card_wickets or 0)
        if (wickets is not None
                and int(wickets) - _prev_wkts_for_junk > 1):
            log.warn(
                f"  [BOWLER-ROW-JUNK-REJECT] '{name}' wickets "
                f"{_prev_wkts_for_junk}→{wickets} jumps >1 in one "
                f"observation; column-scrambled OCR. Suppressing "
                f"wickets update; runs={runs} overs={overs} still "
                f"considered.")
            if _trace is not None:
                try:
                    _trace.get_recorder().record(
                        tag="BOWLER-ROW-JUNK-REJECT",
                        bowler=name,
                        parsed_wickets=int(wickets),
                        prev_wickets=_prev_wkts_for_junk,
                        parsed_overs=str(overs) if overs is not None else None,
                        parsed_runs=int(runs) if runs is not None else None,
                        frame_id=str(frame))
                except Exception:
                    pass
            wickets = _prev_wkts_for_junk

        # Investigation 7B (2026-05-14): wicket credit derivation
        # invariant.  A bowler's wicket count must be DERIVED from
        # dismissal events (fall_of_wickets entries with bowler=name),
        # not invented from a strip delta.  If the strip claims this
        # bowler has wickets > 0 but no FOW entry credits them yet,
        # the claim is either a misread or a backfill from an earlier
        # unattributed wicket (between-overs gap when current_bowler
        # was None).  Suppress the increment; the dismissal-event
        # path will credit correctly when a real wicket fires.
        if (wickets is not None
                and int(wickets) > _prev_wkts_for_junk
                and not self._bowler_has_fow_credit(name)):
            log.warn(
                f"  [BOWLER-WICKET-DELTA-SUPPRESSED-NO-EVENT] '{name}' "
                f"wickets {_prev_wkts_for_junk}→{wickets} suppressed — "
                f"no FOW entry credits this bowler yet; strip is "
                f"either misread or unattributed-wicket backfill")
            if _trace is not None:
                try:
                    _trace.get_recorder().record(
                        tag="BOWLER-WICKET-DELTA-SUPPRESSED-NO-EVENT",
                        bowler=name,
                        prev=_prev_wkts_for_junk,
                        attempted=int(wickets),
                        frame_id=str(frame))
                except Exception:
                    pass
            wickets = _prev_wkts_for_junk

        # === Bowler stats graphic gate (2026-04-28) ===
        # OR semantics: reject on career/phase overlay keywords in
        # vision **or** on spell-impossible figures.  Bare "CAREER"
        # alone does not fire (handled only via implausible_figures
        # together with other signals — see strong-phrase list).
        _implausible = self._bowler_stats_graphic_implausible_spell(
            runs, wickets, overs)
        _strong_kw = (
            bool(vision_desc)
            and self._bowler_stats_graphic_strong_keyword(vision_desc))
        if _strong_kw or _implausible:
            _reason = "career_keyword" if _strong_kw else "implausible_figures"
            log.warn(
                f"  [BOWLER-STATS-GRAPHIC-GATE] rejecting {name!r} - "
                f"reason={_reason} "
                f"(overs={overs!r} runs={runs!r} wickets={wickets!r})")
            return False

        bowl_team = self.bowling_team
        if bowl_team and self._team_match_membership.get(bowl_team):
            bkind, brsn = self.is_eligible_to_bat_or_bowl(name, bowl_team)
            if bkind == "reject":
                log.info(
                    f"[XI-GATE] reject — Bowler '{name}' is {brsn} — "
                    f"rejecting")
                return False
            if bkind == "candidate":
                if self._team_match_membership[bowl_team]["impact_used"]:
                    log.info(
                        f"[XI-GATE] reject — team already used impact "
                        f"player, '{name}' rejected as second activation")
                    return False
                _bst = self._bump_impact_streak(bowl_team, name, frame)
                if _bst < 3:
                    return False
                self._promote_impact_player(bowl_team, name)
            elif bkind == "ok":
                self._clear_impact_streak_team(bowl_team)

        # === Fix F (2026-04-22): playing-XI membership check ===
        # The bowling_card carries the full squad (XI + bench) so that
        # the Scorer can record stats for unexpected inclusions. But a
        # live bowler MUST be in the playing XI.  Scout frequently
        # misreads bench-player names from bowler-stats widgets (IPL
        # broadcasts pre-fire graphics showing squad averages during
        # breaks) and those reads must not be allowed to become
        # `current_bowler` or pollute a bench player's figures.
        _is_xi = self.bowling_card[name].get("is_playing_xi", True)
        if not _is_xi:
            # P0-2 (2026-04-22): XI-REJECT override with action-phase
            # gate. After _XI_OVERRIDE_N total consistent rejections of
            # the same name AND >= _XI_OVERRIDE_ACTION_N of them during
            # active play (camera_view=bowlers_end), promote the player
            # to the playing XI — our squad scrape was almost certainly
            # pre-XI-finalization.
            #
            # Observed failure (MI vs CSK 2026-04-23): Akeal Hosein
            # bowled every over of innings-2's middle phase but every
            # Scout read was XI-REJECTed because our initial scrape
            # listed him as bench. Bowling card never populated for
            # the entire innings.
            #
            # Camera-view gate guards against false promotion: a bench
            # player's name appearing on a career-stats graphic is
            # *not* a signal that they're in the XI. Only reads during
            # live action count toward the promotion.
            _view = self._last_scout_camera_view
            _views = self._xi_rejection_views.setdefault(name, [])
            _views.append(_view)
            _total = len(_views)
            _action = sum(1 for _v in _views if _v == "bowlers_end")
            if (_total >= self._XI_OVERRIDE_N
                    and _action >= self._XI_OVERRIDE_ACTION_N):
                log.warn(
                    f"  [XI-REJECT-OVERRIDE] Promoting '{name}' to XI "
                    f"after {_total} consistent rejections "
                    f"({_action} during camera_view=bowlers_end). "
                    f"Squad scrape was likely pre-XI-finalization; "
                    f"flipping is_playing_xi=True and accepting the "
                    f"read as current_bowler."
                )
                self.bowling_card[name]["is_playing_xi"] = True
                self._xi_rejection_views.pop(name, None)
                # Fall through to normal update path below.
            else:
                log.info(
                    f"  [XI-REJECT] Rejecting '{name}' read — not in "
                    f"bowling-team playing XI (bench/reserve). Scout "
                    f"is likely OCR'ing a squad-averages / career-"
                    f"stats graphic. current_bowler stays "
                    f"'{self._inn.get('current_bowler')}' "
                    f"(rejection {_total}/{self._XI_OVERRIDE_N}, "
                    f"action-phase "
                    f"{_action}/{self._XI_OVERRIDE_ACTION_N}, "
                    f"view={_view!r})")
                return False

        # === Issue 2: bowler rotation rule (2026-04-21) ===
        # A bowler cannot bowl two consecutive overs in T20/ODI.  If
        # `_prev_over_bowler` is set and the incoming read names that
        # same bowler as current, the read has to be wrong by the laws
        # of cricket — typically an end-of-spell / cumulative-stats
        # graphic showing the just-finished bowler's figures, or a
        # stale strip lingering for a couple of seconds after over
        # rollover.  Reject the identity flip (we still drop through
        # below only if the current_bowler already matches — updating
        # the SAME bowler's stats mid-spell is fine).
        #
        # `_prev_over_bowler` stays pinned until the NEXT over change
        # replaces it, so this rule keeps protecting the current over
        # for its entire duration — not just the first N frames.
        #
        # Reject ALL updates (both identity and figures) when the
        # incoming name matches the previous-over bowler.  If the read
        # is wrong about the name, the figures attached to that read
        # are also wrong (Scout is looking at the wrong graphic) and
        # would otherwise poison the previous bowler's career totals.
        _cur_now = self._inn.get("current_bowler") if self._inn else None
        if (self._prev_over_bowler
                and name == self._prev_over_bowler):
            # Fix #3 (2026-04-23): recoverable override.
            # Our _prev_over_bowler record is a best-effort snapshot
            # taken at over-rollover.  If Scout consistently disagrees
            # — reading the same "forbidden" name across multiple
            # frames — the odds are our record is wrong (mis-labelled
            # over boundary, cold-start rotation, mid-match restart
            # without full context).  After N consistent rejections,
            # flip: accept the read and clear the lockout.  Observed
            # failure this guard recovers from: MI vs CSK 2026-04-23,
            # F12-F27 stuck with current_bowler=None because rotation
            # rejected every Ghazanfar read after a mis-recorded
            # previous over.
            count = self._rotation_rejection_count.get(name, 0) + 1
            self._rotation_rejection_count[name] = count
            if count >= self._ROTATION_OVERRIDE_N:
                log.warn(
                    f"  [ROTATION-OVERRIDE] Accepting '{name}' after "
                    f"{count} consistent rejections — "
                    f"_prev_over_bowler='{self._prev_over_bowler}' "
                    f"record is likely wrong; clearing the lockout."
                )
                self._rotation_rejection_count.pop(name, None)
                self._prev_over_bowler = None
                # Fall through to the normal update path below.
            else:
                log.info(
                    f"  [ROTATION] Rejecting bowler read '{name}' — "
                    f"can't bowl two consecutive overs (just bowled "
                    f"prev over; rejection "
                    f"{count}/{self._ROTATION_OVERRIDE_N}). "
                    f"current_bowler stays '{_cur_now}'"
                )
                if _trace is not None:
                    try:
                        _trace.get_recorder().record(
                            tag="CONSECUTIVE-OVER-BOWLER-REJECTED",
                            bowler=name,
                            prev_over_bowler=self._prev_over_bowler,
                            rejection_count=count,
                            frame_id=str(frame))
                    except Exception:
                        pass
                return False
        elif name != self._prev_over_bowler:
            # Different bowler accepted — clear any stale counter for
            # this name so the override threshold doesn't carry over.
            self._rotation_rejection_count.pop(name, None)

        # === Stale-graphic detection (refined 2026-04-22) ===
        # Layer-3 defense against end-of-spell graphics resurrecting a
        # previous bowler.  The rotation rule (above) catches
        # "Madushanka → Madushanka" at over change, but not
        # "Madushanka → Shivang → Reddy" where Shivang bowled TWO
        # overs ago and his end-of-spell graphic is now on-screen
        # between Madushanka's last ball and Reddy's first ball.
        #
        # Two defense branches, split by identity-vs-current:
        #
        # IDENTITY CHANGE (name != current):
        #   (a) Same-figures stale graphic — incoming name brings
        #       the exact figures already recorded for them, no new
        #       info, just the same graphic re-read. Rejected
        #       OUTSIDE must_change grace (inside grace a returning
        #       bowler legitimately shows last-spell figures).
        #   Regression check DOES NOT apply on identity change:
        #   different bowlers have independent spells, so comparing
        #   an incoming bowler's proposed overs to their own
        #   previously-recorded figures would wrongly block a
        #   legitimate handover read whenever the incoming bowler's
        #   last recorded value happens to be corrupt-high.  That
        #   class of bug is handled by the SAME-identity branch
        #   below with recoverable override.
        #
        # SAME IDENTITY (name == current):
        #   (b) Overs-regression with recoverable override — a real
        #       spell only goes forward, so lower overs means stale
        #       cache OR corrupted lock. We reject the first few
        #       regression reads; if the same lower proposal
        #       persists for `_BOWLER_REGRESS_OVERRIDE_N` frames,
        #       the recorded value is the corrupt one and we allow
        #       the override (log loudly — this is the unstick path
        #       for phantom high-water records).
        if name != _cur_now:
            hist = self.bowling_card.get(name, {})
            hist_r = hist.get("runs")
            hist_w = hist.get("wickets")
            hist_o = hist.get("overs")

            # (a) Same-figures stale graphic.
            #
            # Freshness disambiguator (2026-04-25 RR-vs-SRH fix; see
            # __init__ comment on `_bowling_card_active_write_*`):
            # bypass this rejection when (i) the recorded figures
            # were written recently AND (ii) `current_bowler` hasn't
            # changed since that write.  That's the
            # "between-deliveries repeat read of a bowler trying to
            # take over" pattern — figures haven't ticked yet
            # because no ball has been bowled in the gap, the
            # consensus mechanism downstream needs these repeats to
            # accumulate and flip identity.  When the bowler
            # context HAS changed in the interim, the original
            # stale-graphic defense applies unchanged.
            _last_w_frame = (
                self._bowling_card_active_write_frame.get(
                    name, -10**9))
            _last_w_bowler = (
                self._bowling_card_active_write_bowler.get(
                    name, None))
            _recently_written = (
                (frame - _last_w_frame)
                <= self._BOWLER_STALE_FRESH_FRAMES)
            _same_bowler_context = (_last_w_bowler == _cur_now)
            _fresh_between_ball = (
                _recently_written and _same_bowler_context)

            if (not self._bowler_must_change
                    and not _fresh_between_ball
                    and hist_r is not None
                    and hist_w is not None
                    and hist_o is not None
                    and runs is not None
                    and wickets is not None
                    and overs is not None):
                try:
                    same_figures = (
                        int(runs) == int(hist_r)
                        and int(wickets) == int(hist_w)
                        and str(overs) == str(hist_o))
                except (TypeError, ValueError):
                    same_figures = False
                if same_figures:
                    log.info(
                        f"  [BOWLER-STALE] Rejecting '{name}' read — "
                        f"proposed {wickets}-{runs}({overs}) exactly "
                        f"matches recorded {hist_w}-{hist_r}({hist_o})"
                        f"; no handoff grace "
                        f"(must_change={self._bowler_must_change}). "
                        f"Likely stale end-of-spell graphic; "
                        f"current_bowler stays '{_cur_now}'"
                    )
                    return False

            # Identity change: clear any pending regression counter
            # for the incoming bowler — the stale figures (if any)
            # will be re-evaluated from the new reads.
            self._bowler_regress_pending.pop(name, None)

        else:
            # Same identity (name == _cur_now): check for a genuine
            # regression and apply recoverable-override logic.
            hist = self.bowling_card.get(name, {})
            hist_o = hist.get("overs")
            hist_r = hist.get("runs")
            hist_w = hist.get("wickets")
            if hist_o is not None and overs is not None:
                try:
                    regressing = float(overs) < float(hist_o)
                except (TypeError, ValueError):
                    regressing = False
                if regressing:
                    prop = (str(overs),
                            int(runs) if runs is not None else None,
                            int(wickets) if wickets is not None else None)
                    prev = self._bowler_regress_pending.get(name)
                    if prev and prev[0] == prop:
                        new_count = prev[1] + 1
                    else:
                        new_count = 1
                    self._bowler_regress_pending[name] = (prop, new_count)

                    if new_count >= self._BOWLER_REGRESS_OVERRIDE_N:
                        log.warn(
                            f"  [BOWLER-RECOVER] Overriding stuck "
                            f"'{name}' figures "
                            f"{hist_w}-{hist_r}({hist_o}) → "
                            f"{prop[2]}-{prop[1]}({prop[0]}) "
                            f"after {new_count} consistent "
                            f"regression reads. Recorded value was "
                            f"likely corrupt; clearing tracker lock "
                            f"and accepting live reads.")
                        # Clear tracker locks so the write below
                        # isn't itself rejected as a regression.
                        try:
                            self._tracker.force_set(
                                f"bowl:{name}:runs",
                                prop[1] if prop[1] is not None else 0)
                            self._tracker.force_set(
                                f"bowl:{name}:wickets",
                                prop[2] if prop[2] is not None else 0)
                            self._tracker.force_set(
                                f"bowl:{name}:overs", prop[0])
                        except Exception as e:  # noqa: BLE001
                            log.warn(
                                f"  [BOWLER-RECOVER] force_set "
                                f"failed: {e}")
                        # Also overwrite the card directly — the
                        # tracker.update() below would honour this.
                        entry = self.bowling_card[name]
                        entry["overs"] = prop[0]
                        if prop[1] is not None:
                            entry["runs"] = prop[1]
                        if prop[2] is not None:
                            entry["wickets"] = prop[2]
                        self._bowler_regress_pending.pop(name, None)
                        # Fall through so the normal update path
                        # below records the read cleanly.
                    else:
                        log.info(
                            f"  [BOWLER-STALE] Rejecting '{name}' "
                            f"read — overs {overs} < recorded "
                            f"{hist_o}; spell can't regress "
                            f"({new_count}/"
                            f"{self._BOWLER_REGRESS_OVERRIDE_N} "
                            f"consistent; will override if "
                            f"persistent)."
                        )
                        return False
                else:
                    # Non-regressing read — clear any pending
                    # override candidate.
                    self._bowler_regress_pending.pop(name, None)

        entry = self.bowling_card[name]
        old_str = f"{entry['wickets']}/{entry['runs']} ({entry['overs']})"

        # T20 bowler max overs guard
        if overs is not None:
            try:
                overs_float = float(overs)
            except (ValueError, TypeError):
                overs_float = 0
            if overs_float > 4.0:
                log.info(f"[GUARD] Bowler {name} overs {overs} > 4.0 "
                         f"— career stat, dropping ALL figures")
                overs = None
                runs = None
                wickets = None
            else:
                match_overs = float(self._inn.get("overs") or "0")
                if match_overs > 0 and overs_float > match_overs + 1.0:
                    log.info(
                        f"[BOWLER-STATS-SANITY-REJECT] Bowler {name} "
                        f"overs {overs} > team overs {match_overs}+1.0 — "
                        f"rejecting figures (recap/phantom spell)")
                    overs = None
                    runs = None
                    wickets = None

        try:
            new_r = int(runs) if runs is not None else None
        except (ValueError, TypeError):
            new_r = None
        try:
            new_w = int(wickets) if wickets is not None else None
        except (ValueError, TypeError):
            new_w = None

        if new_r is not None:
            # 2026-05-13 (bowler-spell seed): same as overs — a fresh
            # bowler entry sitting at runs=0 (initial) gets the first
            # strip-read directly, then normal consensus from there.
            _card_runs = int(entry.get("runs") or 0)
            if _card_runs == 0 and new_r > 0:
                entry["runs"] = new_r
                self._tracker.force_set(f"bowl:{name}:runs", new_r)
                log.info(
                    f"  [BOWLER-SPELL-SEED] '{name}' runs "
                    f"0 → {new_r} (first non-zero strip read; "
                    f"bypassing consensus)")
            else:
                eff_r = self._tracker.update(
                    f"bowl:{name}:runs", new_r, frame)
                if eff_r is not None:
                    entry["runs"] = int(eff_r)
        if new_w is not None:
            _card_wkts = int(entry.get("wickets") or 0)
            if _card_wkts == 0 and new_w > 0:
                entry["wickets"] = new_w
                self._tracker.force_set(f"bowl:{name}:wickets", new_w)
                log.info(
                    f"  [BOWLER-SPELL-SEED] '{name}' wickets "
                    f"0 → {new_w} (first non-zero strip read; "
                    f"bypassing consensus)")
            else:
                eff_w = self._tracker.update(
                    f"bowl:{name}:wickets", new_w, frame)
                if eff_w is not None:
                    entry["wickets"] = int(eff_w)
        if overs is not None:
            # 2026-05-13 (bowler-spell seed): when a bowler's card is
            # at the fresh-entry baseline (overs=0.0 / 0 / None), accept
            # the first non-zero strip-read directly.  The consensus
            # tracker rejects jumps from 0.0 → 2.x as implausible spike,
            # leaving Hazlewood-class fresh-spell bowlers stuck at 0-0
            # for their entire spell.  After the seed, normal consensus
            # resumes (the next read of e.g. 2.3 advances cleanly from
            # the 2.2 seed).
            _card_balls = self._overs_to_balls(entry.get("overs"))
            _ovs_str = str(overs).strip()
            _seeded = False
            if (_card_balls == 0
                    and _ovs_str not in ("0.0", "0", "None", "")):
                entry["overs"] = _ovs_str
                self._tracker.force_set(
                    f"bowl:{name}:overs", _ovs_str)
                log.info(
                    f"  [BOWLER-SPELL-SEED] '{name}' overs "
                    f"0.0 → {_ovs_str} (first non-zero strip read; "
                    f"bypassing consensus)")
                _seeded = True
            if not _seeded:
                eff_ov = self._tracker.update(
                    f"bowl:{name}:overs", str(overs), frame)
                if eff_ov is not None:
                    entry["overs"] = str(eff_ov)

        if maidens is not None:
            try:
                entry["maidens"] = int(maidens)
            except (ValueError, TypeError):
                pass

        new_str = f"{entry['wickets']}/{entry['runs']} ({entry['overs']})"
        if old_str != new_str:
            self._log("bowler", name, old_str, new_str, frame)

        # Stamp the active-write frame and current-bowler context for
        # the BOWLER-STALE freshness disambiguator (see __init__
        # comment).  Only stamp on a meaningful committed write —
        # i.e. when the rendered figure string actually changed —
        # so a no-op call doesn't refresh the freshness baseline.
        if old_str != new_str:
            self._bowling_card_active_write_frame[name] = frame
            self._bowling_card_active_write_bowler[name] = (
                self._inn.get("current_bowler") if self._inn else None)

        # === Bowler 3-frame consensus before flipping current_bowler ===
        # Broadcast is authoritative; inference is provisional. But a
        # single LLM hallucination ("Short" reads as "Choudhary" once
        # because the previous bowler card is still on screen) must
        # not flip our state. Only when the same name is read on
        # CONSENSUS_N consecutive frames do we override the current
        # bowler. The previous bowler (just-finished over) is exempt
        # from consensus — when over rolls over and the new bowler is
        # read, we flip immediately if we know the previous bowler is
        # gone. The score/wickets/overs above always update the named
        # entry's stats — that's harmless even for misreads (their
        # tracker rejects regressions).
        _CONSENSUS_N = 3
        _cur_bowler = self._inn.get("current_bowler")
        _prev_over_bowler = self._prev_over_bowler
        _bowler_changed = False
        # Track whether the override was already pending at entry — used
        # to flush the BOWLER-AUTO attribution-freeze buffer on the
        # transition where pending dissipates (read matches current
        # bowler) or fires (override accepted).
        _pending_at_entry = self._pending_bowler_name is not None
        if name == _cur_bowler:
            self._pending_bowler_name = None
            self._pending_bowler_count = 0
            if _pending_at_entry:
                self._flush_bowler_attribution_freeze(frame, reason="dissipated")
        else:
            if name == self._pending_bowler_name:
                self._pending_bowler_count += 1
            else:
                if self._pending_bowler_name:
                    self._bowler_consensus_inconsistent_streak.pop(
                        self._pending_bowler_name, None)
                self._pending_bowler_name = name
                self._pending_bowler_count = 1
            # Two paths to flip:
            #   (a) over just rolled and we expect a new bowler
            #       (_bowler_must_change) — accept after consensus
            #       (≥2 reads, ≥3 if leader is well-established)
            #       provided the new name != previous over's bowler.
            #   (b) normal play — require N consecutive reads.
            _accept = False
            _ov_for_flip = overs if overs is not None else entry.get("overs")
            # Investigation 5 (2026-05-14): must_change=True formerly
            # accepted on 1st sighting; a single VLM read of a prior-
            # over bowler's name was enough to flip current_bowler and
            # poison subsequent BOWLER-AUTO attribution.  Require
            # consensus regardless of must_change.
            _override_required = self._BOWLER_OVERRIDE_CONSENSUS_FRAMES
            if (_cur_bowler is not None
                    and self.bowling_card.get(_cur_bowler)
                    and self._overs_to_balls(
                        str(self.bowling_card[_cur_bowler].get("overs")
                            or "0.0"))
                    >= self._BOWLER_OVERRIDE_HIGH_WEIGHT_BALL_THRESHOLD):
                _override_required = (
                    self._BOWLER_OVERRIDE_CONSENSUS_FRAMES_HIGH_WEIGHT)
            if self._bowler_must_change:
                _override_required = max(
                    self._BOWLER_OVERRIDE_CONSENSUS_FRAMES,
                    _override_required - 1)

            _must_change_path = (
                self._bowler_must_change
                and (not _prev_over_bowler
                     or name != _prev_over_bowler)
                and self._pending_bowler_count >= _override_required)
            if _must_change_path:
                _accept = True
            elif (self._bowler_must_change
                    and (not _prev_over_bowler
                         or name != _prev_over_bowler)):
                log.info(
                    f"  [BOWLER-OVERRIDE-PENDING] candidate={name!r} "
                    f"streak={self._pending_bowler_count}/"
                    f"{_override_required} leader={_cur_bowler!r} "
                    f"must_change=True")
                if _trace is not None:
                    try:
                        _trace.get_recorder().record(
                            tag="BOWLER-OVERRIDE-PENDING",
                            candidate=name,
                            streak=self._pending_bowler_count,
                            required=_override_required,
                            leader=_cur_bowler,
                            must_change=True)
                    except Exception:
                        pass
            if not _accept and self._bowler_team_over_consensus(
                    _cur_bowler, name, overs, self._pending_bowler_count):
                log.warn(
                    f"  [BOWLER-TEAM-OVER-CONSENSUS] accepting {name!r} "
                    f"after {self._pending_bowler_count} reads — "
                    f"candidate overs {overs} matches team over "
                    f"{self._inn.get('overs')} while current_bowler "
                    f"{_cur_bowler!r} is inconsistent")
                _accept = True
            elif self._pending_bowler_count >= _CONSENSUS_N:
                if self._bowler_plain_consensus_overs_plausible(_ov_for_flip):
                    self._bowler_consensus_inconsistent_streak.pop(name, None)
                    _accept = True
                else:
                    st = self._bowler_consensus_inconsistent_streak.get(
                        name, 0) + 1
                    self._bowler_consensus_inconsistent_streak[name] = st
                    cand_mod = self._overs_to_balls(str(_ov_for_flip or 0)) % 6
                    team_mod = self._team_balls_seen() % 6
                    log.warn(
                        f"  [BOWLER-CONSENSUS-INCONSISTENT] refusing flip to "
                        f"{name!r} — overs={_ov_for_flip!r} ball_mod6={cand_mod} "
                        f"vs team strip ball_mod6={team_mod} "
                        f"(team_overs={self._inn.get('overs')!r}); "
                        f"streak={st}/"
                        f"{self._BOWLER_CONSENSUS_OVERS_OVERRIDE_N}")
                    if st >= self._BOWLER_CONSENSUS_OVERS_OVERRIDE_N:
                        log.warn(
                            f"  [BOWLER-CONSENSUS-INCONSISTENT-OVERRIDE] "
                            f"accepting {name!r} after {st} mismatched frames — "
                            f"forcing flip (strip/broadcast may disagree on "
                            f"figure shape)")
                        self._bowler_consensus_inconsistent_streak.pop(name, None)
                        _accept = True
            if _accept:
                _fire_reads = self._pending_bowler_count
                _fire_must_change = self._bowler_must_change
                log.info(
                    f"[BOWLER-OVERRIDE] {_cur_bowler} → {name} "
                    f"(reads={_fire_reads}, "
                    f"must_change={_fire_must_change})")
                if _trace is not None:
                    try:
                        _trace.get_recorder().record(
                            tag="BOWLER-OVERRIDE-FIRED",
                            old=_cur_bowler,
                            new=name,
                            consensus_frames=_fire_reads,
                            required=_override_required,
                            must_change=_fire_must_change)
                    except Exception:
                        pass
                self._inn["current_bowler"] = name
                self._inn["bowler_between_overs"] = False
                self._tracker.force_set("current_bowler", name)
                self._pending_bowler_name = None
                self._pending_bowler_count = 0
                self._bowler_must_change = False
                _bowler_changed = True
                # Flush any buffered team-score deltas to the newly-
                # confirmed bowler.  These were accumulated while the
                # override was pending — see _mirror_team_delta_to_bowler.
                self._flush_bowler_attribution_freeze(frame, reason="fired")
        # First-bowler bootstrap: if no current_bowler is set at all,
        # accept this read immediately so cold-start populates the
        # bowling card on frame 1.
        _bootstrapped = False
        if not _cur_bowler and not _bowler_changed:
            # P3 fix (2026-05-02): the over-rollover handler in
            # test_pipeline.py clears current_bowler=None and sets
            # _bowler_must_change=True; without this gate the strip's
            # next read of the just-finished bowler bootstraps him
            # straight back in, defeating the must-change protection.
            # Bootstrap is for cold-start (no bowler ever set, no
            # must-change pending) — reject when must_change is active
            # AND the candidate matches the previous-over bowler.
            if (self._bowler_must_change
                    and self._prev_over_bowler
                    and name == self._prev_over_bowler):
                log.info(
                    f"  [BOWLER-BOOTSTRAP-REJECT] refusing to install "
                    f"{name!r} via bootstrap — must_change=True and "
                    f"name matches previous-over bowler "
                    f"{self._prev_over_bowler!r}; waiting for a "
                    f"different name")
            else:
                self._inn["current_bowler"] = name
                self._inn["bowler_between_overs"] = False
                self._tracker.force_set("current_bowler", name)
                _bootstrapped = True

        # === Issue 3 fix (2026-04-21): seed a freshly-promoted bowler's
        # figures to 0-0(0.0) immediately, bypassing the tracker's
        # 3-frame cold-start consensus.
        #
        # A bowler entering `current_bowler` via the must-change path
        # has just started a new over, which in limited-overs cricket
        # ALWAYS means 0-0(0.0) at ball 0 of their spell.  Without
        # seeding, the tracker waits 3 identical reads of "0" before
        # promoting to `confirmed`, which means entry["runs"] stays
        # None for 3 frames and the UI shows a blank/"—" bowler line
        # for ~3-5 seconds.
        #
        # Safe because we only seed when the card's figures are still
        # unset (a returning 2nd-spell bowler keeps their accumulated
        # figures — those entries are non-None).
        if _bowler_changed or _bootstrapped:
            try:
                _bc_runs = int(entry.get("runs") or 0)
                _bc_wkts = int(entry.get("wickets") or 0)
                _bc_balls = int(entry.get("balls") or 0)
                _resumed = (_bc_runs > 0 or _bc_wkts > 0 or _bc_balls > 0)
                if _trace is not None:
                    _trace.get_recorder().record(
                        tag=("BOWLING-CARD-RESUMED" if _resumed
                             else "BOWLING-CARD-CREATED"),
                        bowler=name,
                        frame_id=str(frame),
                        existing_runs=_bc_runs,
                        existing_wickets=_bc_wkts,
                        existing_balls=_bc_balls)
            except Exception:
                pass
        if (_bowler_changed or _bootstrapped) and entry.get("runs") is None:
            # Issue B fix (2026-04-21): prefer scout-text figures over
            # hard-coded zeros when the bowler is entering with an
            # already-accumulated spell (impact sub, mid-match join).
            # Example: Madushanka enters over 12 and Scout reads
            # "Madushanka 1-24 (3)" — seeding at 0-0(0.0) would lose
            # his 24 runs, and subsequent monotonic-increase consensus
            # would block recovery.  Seed with the scout values when
            # they pass sanity (non-negative, ≤ 250 runs, ≤ 10
            # wickets, overs in [0.0, 4.0]).
            seed_r, seed_w, seed_o = 0, 0, "0.0"
            from_scout = False
            try:
                _r = int(new_r) if new_r is not None else None
                _w = int(new_w) if new_w is not None else None
            except (TypeError, ValueError):
                _r, _w = None, None
            try:
                _o = float(overs) if overs is not None else None
            except (TypeError, ValueError):
                _o = None
            if (_r is not None and 0 <= _r <= 250
                    and _w is not None and 0 <= _w <= 10
                    and _o is not None and 0.0 <= _o <= 4.0
                    and (_r > 0 or _w > 0 or _o > 0)):
                seed_r, seed_w = _r, _w
                seed_o = str(overs)
                from_scout = True
            _carryover_balls = self._overs_to_balls(entry.get("overs"))
            _has_carryover_overs = (
                not from_scout
                and entry.get("overs") is not None
                and _carryover_balls > 0)
            entry["runs"] = seed_r
            entry["wickets"] = seed_w
            if entry.get("overs") is None or from_scout:
                entry["overs"] = seed_o
            self._tracker.force_set(f"bowl:{name}:runs", seed_r)
            self._tracker.force_set(f"bowl:{name}:wickets", seed_w)
            if _has_carryover_overs:
                log.info(
                    f"  [BOWLER-RESET-SKIPPED-CARRYOVER] '{name}' "
                    f"preserved_overs={entry.get('overs')!r} "
                    f"(prior-spell figures, not zeroing tracker)")
            else:
                self._tracker.force_set(f"bowl:{name}:overs", seed_o)
            if from_scout:
                log.info(
                    f"[BOWLER SEED] {name} figures seeded from scout "
                    f"text to {seed_w}-{seed_r} ({seed_o}) — "
                    f"mid-spell entry (impact sub / mid-match join)")
            else:
                log.info(
                    f"[BOWLER SEED] {name} figures seeded to 0-0(0.0) "
                    f"on spell start (skipping cold-start consensus)")
        return True

    # ------------------------------------------------------------------
    # Fall of Wickets
    # ------------------------------------------------------------------

    def _add_fow(self, wicket_num: int | None, batter: str,
                 score: int | str | None, overs: str | None,
                 how: str | None = None, bowler: str | None = None):
        """Add or upgrade a FOW entry. Confirmed entries are immutable.

        Three cases for an existing slot at the same wicket number:
          1. Placeholder (batter ∈ {None, "", "unknown"}): UPGRADE
             with the new details (this is exactly what placeholders
             exist for).
          2. Real entry, same batter: idempotent re-write — silently
             skip (we may have rolled through this dismissal twice).
          3. Real entry, different batter:
             a. SCOREBOARD-PROVABLY-WRONG existing entry — replace
                in place. The "existing" batter is provably wrong
                when they're currently still batting (`status ==
                "batting"`) or never came in at all (`yet_to_bat`).
                Cricket law: a batter cannot be dismissed AND still
                be at the crease. The new dismissal is the truth
                and we MUST rewrite W{wk} so we don't bump to W{wk+1}
                and outrun the team's wicket counter.
             b. Otherwise REFUSE the rewrite (immutable history).
        """
        wk = int(wicket_num or 0)
        if wk <= 0:
            wk = len(self.fall_of_wickets) + 1

        # Cold-start back-fill placeholders carry score="?" / overs="?"
        # because the wicket fell BEFORE the pipeline started observing.
        # A fresh dismissal that arrives later (with a real score/overs)
        # is for a DIFFERENT wicket — typically the next one — not
        # the historic one. Promote `wk` to the next free slot in
        # that case so we don't smash Cricbuzz-known history.
        #
        # IMPORTANT: only promote when the new dismissal is genuinely
        # for a *future* wicket — i.e. the team's wickets counter
        # has already advanced past `wk`. If wk == total wickets,
        # the new dismissal IS the wk-th wicket and should upgrade
        # the back-fill in place (the back-fill was a guess that's
        # now being proven correct).
        _team_wkts = int(self._inn.get("wickets") or 0)
        for existing in self.fall_of_wickets:
            if existing.get("wicket") == wk:
                _ex_score = existing.get("score")
                _ex_overs = existing.get("overs")
                _is_backfill = (
                    existing.get("tentative", False)
                    and (_ex_score in (None, "?", "")
                         or _ex_overs in (None, "?", "")))
                if (_is_backfill
                        and score is not None and score != "?"
                        and overs is not None and overs != "?"
                        and _team_wkts > wk):
                    new_wk = len(self.fall_of_wickets) + 1
                    log.info(
                        f"[FOW] W{wk} is cold-start back-fill "
                        f"(unknown score/overs); fresh dismissal "
                        f"{batter} at {score}/{overs} routed to "
                        f"W{new_wk} instead (team_wkts="
                        f"{_team_wkts}).")
                    wk = new_wk
                    break

        for existing in self.fall_of_wickets:
            if existing.get("wicket") == wk:
                _existing_batter = existing.get("batter")
                _is_tentative = existing.get("tentative", False)
                _is_unwitnessed = existing.get("_unwitnessed", False)
                if (_existing_batter in (None, "", "unknown")
                        or _is_tentative
                        or _is_unwitnessed):
                    existing["batter"] = batter
                    existing["score"] = score
                    existing["overs"] = overs
                    if how:
                        existing["how"] = how
                    if bowler:
                        existing["bowler"] = bowler
                    existing.pop("tentative", None)
                    existing.pop("_unwitnessed", None)
                    existing["_witnessed"] = True
                    _flag_str = []
                    if _is_unwitnessed:
                        _flag_str.append("was _unwitnessed")
                    if _is_tentative:
                        _flag_str.append("was tentative")
                    _flag_suf = (f" ({', '.join(_flag_str)})"
                                 if _flag_str else "")
                    log.info(f"[FOW] Upgraded placeholder W{wk}: "
                             f"{batter} at {score}/{wk} ({overs})"
                             f"{_flag_suf}")
                    # Fix 10 (2026-04-26, Path A): post-witnessed
                    # dismissal slot-rotation hook.  Fires on the
                    # placeholder→witnessed upgrade.  Closes the
                    # rotation gap observed in CSK-vs-GT (Sarfaraz,
                    # Dube, Overton) where `_auto_dismiss_for_new_
                    # batter` flips status="out" without clearing
                    # `_inn["striker"]` / `["non"]`.  See
                    # helper docstring for full rationale.
                    self._post_witnessed_dismissal_slot_rotation(
                        batter)
                    # Fire FOW-upgrade callback (Fix 3): pass the
                    # legal-ball index parsed from `overs="X.Y"`.
                    # Wrapped in try/except so a misbehaving consumer
                    # cannot poison the FOW write path itself.
                    if self.on_fow_upgrade is not None and overs:
                        try:
                            _ball_y = int(str(overs).split(".")[-1])
                            if _ball_y > 0:
                                self.on_fow_upgrade(_ball_y)
                        except (ValueError, IndexError, Exception) as _e:
                            log.warn(
                                f"[FOW-REORDER] callback raised "
                                f"{type(_e).__name__}: {_e}; "
                                f"continuing without reorder")
                elif _existing_batter == batter:
                    log.info(f"[FOW] Idempotent re-add of W{wk} "
                             f"({batter}) — no change")
                else:
                    # Witnessed FOW entries are IMMUTABLE.  The
                    # legacy "provably wrong" rewrite path that used
                    # to overwrite based on `batting_card` status
                    # was the source of the Jofra-Archer→Vaibhav-
                    # Sooryavanshi flip on 2026-04-19: a real
                    # wicket event correctly populated W6 with
                    # Archer, but a later wicket event for a batter
                    # whose card status was momentarily "yet_to_bat"
                    # tripped the rewrite and silently replaced the
                    # confirmed Archer entry.
                    #
                    # New rule: once an entry is witnessed
                    # (populated by `_add_fow` from a real ball
                    # event), it can never be rewritten.  If the
                    # new dismissal genuinely belongs to W{wk}
                    # (rare — would imply W{wk-1}…W{wk} all
                    # mis-fired), we surface the conflict in the
                    # log so the underlying mis-attribution is
                    # visible, rather than papering over it.
                    log.warn(
                        f"[FOW] Rewrite REFUSED for W{wk}: "
                        f"witnessed entry {_existing_batter} is "
                        f"immutable; new dismissal {batter} at "
                        f"{score}/{overs} not applied. If this is "
                        f"a real wk-conflict, investigate the "
                        f"upstream wicket-counter / striker state "
                        f"that produced the duplicate W{wk}.")
                return

        fow = {"wicket": wk, "score": score, "overs": overs,
               "batter": batter, "_witnessed": True}
        if how:
            fow["how"] = how
        if bowler:
            fow["bowler"] = bowler
        self.fall_of_wickets.append(fow)
        self.fall_of_wickets.sort(key=lambda x: x.get("wicket", 0))
        # Fix 10 (2026-04-26, Path A): post-witnessed dismissal
        # slot-rotation hook.  Fires on the new-FOW-entry path
        # (no prior placeholder existed at this wicket number).
        # See `_post_witnessed_dismissal_slot_rotation` docstring.
        self._post_witnessed_dismissal_slot_rotation(batter)

    def _post_witnessed_dismissal_slot_rotation(
            self, dismissed: str | None) -> None:
        """Post-witnessed-FOW slot-clear / rotation invariant
        (Fix 10, Path A — 2026-04-26).

        Cricket physics: a witnessed-out batter cannot retain
        occupancy of either active crease slot
        (``self._inn["striker"]`` / ``["non"]``).  This
        hook fires from `_add_fow` after stamping
        ``_witnessed=True`` on a FOW entry (both the
        placeholder-upgrade and new-entry creation paths).

        Three behaviours by case:

          1. Dismissed batter occupied **striker** slot only.
             Rotate the surviving non into the striker
             slot; clear non pending new-batter
             admission.  Mirrors typical post-wicket broadcast
             state at end-of-over (when ends swap) and
             converges to the correct mid-over state within
             1–2 strip reads when the new batter actually
             faces.

          2. Dismissed batter occupied **non** slot
             only.  Clear non; striker unchanged.
             Run-out at the non-striker end is the most common
             path here.

          3. Dismissed name in **neither** slot.  Two sub-
             cases observed in production:
             (a) Cold-start back-fill of historic wickets
                 where current crease state legitimately
                 reflects a much later innings stage than the
                 upgraded wicket: no-op (correct).
             (b) **Real-time delayed witness — placeholder
                 window outlived crease rotation** (Fix 13,
                 Path D extension, 2026-04-26).  Powell W4
                 placeholder added at F179 (`_unwitnessed`),
                 upgraded at F258 (~2 min / 79 frames later);
                 in the gap, broadcast had already rotated the
                 crease past Powell's tenure, so the slot
                 check no-ops.  But the dismissal still needs
                 to commit to `batting_card.status="out"` and
                 `active_batters` removal — `_add_fow` doesn't
                 propagate either of those.  Path D adds Case
                 5 below to handle this sub-case.

          4. Anomaly: dismissed name occupied **both** slots
             (e.g. striker self-collision Fix 5 didn't catch).
             Defensive clear of both with WARN log.

          5. (Fix 13, Path D, 2026-04-26) Dismissed name not
             in either slot, but present in `batting_card`
             with status="batting".  Card-side propagation:
             flip `batting_card[name].status = "out"`.
             Distinct telemetry tag
             `[POST-WICKET-CARD-PROPAGATE]` separates this
             from regular slot-rotation fires.  Same root
             cricket-physics invariant (a witnessed-out
             batter cannot be active anywhere), just a
             different state surface than the crease slots.
             Derived views (`_extractor_batter_names`,
             transient active-batter lists in scorer-decision
             paths) are recomputed from `batting_card.status`
             downstream, so flipping the card propagates to
             those views without direct mutation.

        Why hook here and not at the four ``status="out"``
        callsites:  ``dismiss_batter()`` (line 2763) already
        clears slots explicitly, but
        ``_auto_dismiss_for_new_batter`` (line 1528) and the
        ``validate_state_consistency`` demote paths (3091,
        3124) flip status without touching ``_inn`` slots —
        leaving the dismissed name to trigger downstream
        ``[STRIKER-COLLISION]`` (Fix 5) and ``[WS-SCRUB]``
        cascades for the rest of the over.  Centralising the
        invariant at ``_add_fow``'s witnessed stamp covers the
        auto-dismiss path (which calls ``_add_fow``) and any
        future witnessed-FOW write site without requiring
        per-callsite touch-ups.

        Coverage caveat: the validate-resurrection demote paths
        (lines 3091, 3124) do *not* call ``_add_fow`` (the FOW
        entry already exists from the original witnessing).
        For those paths, the slot would have been cleared at
        the *original* witnessing, when this hook first ran.
        If a resurrection re-populated the slot before
        validate demotes it back, the slot will not be re-
        cleared by this hook.  Filed as a follow-up under the
        "Complete the SM-cutover" architectural item.

        Validation evidence (CSK-vs-GT 2026-04-26): three
        rotation-gap instances (Sarfaraz F1670, Dube F1813,
        Overton F2410+) with 88 / 443+ / 240+ defensive
        cascade fires per stuck-non window before
        new-batter admission resolved the slot.  This hook
        closes the upstream gap; Fix 5 and ``[WS-SCRUB]``
        stay as backstops, expected post-fix fire counts
        approach 0.

        Idempotent: re-asserting a witnessed dismissal whose
        name has already been cleared from slots is a no-op.
        Composes with ``dismiss_batter()``'s explicit clear
        (lines 2800-2803), which becomes a no-op because this
        hook already cleared the slots earlier in the call
        chain via ``_add_fow``.
        """
        if not dismissed or not self._inn:
            return
        # AUTHORITATIVE-SBINN-READ: rotation writer reads legacy striker slot.
        # striker_path_b_read_audit.md R3 §2.1.1
        striker_dismissed = (self._inn.get("striker") == dismissed)
        # AUTHORITATIVE-SBINN-READ: legacy non slot (audit R4 §2.1.1)
        non_dismissed = (
            self._inn.get("non") == dismissed)
        if not (striker_dismissed or non_dismissed):
            # Case 3 / 5 split (Fix 13, Path D, 2026-04-26):
            # not in either slot.  Check whether the dismissed
            # batter is still showing as active in
            # `batting_card` (status="batting") — if so this is
            # the real-time-delayed-witness sub-case (3b /
            # Case 5) and the card-side dismissal still needs
            # to commit.  If status is already "out" or
            # "yet_to_bat", this is the legitimate cold-start
            # back-fill (Case 3a) — no-op.
            #
            # Note: `_extractor_batter_names` and any transient
            # active-batter sets passed to scorer-decision
            # paths are recomputed downstream from
            # `batting_card.status`, so flipping the card
            # status propagates naturally to those derived
            # views without needing direct mutation here.
            _card_entry = self.batting_card.get(dismissed)
            _card_active = (_card_entry is not None
                            and _card_entry.get("status")
                            == "batting")
            if _card_active:
                self.batting_card[dismissed]["status"] = "out"
                self.batting_card[dismissed]["dismissal_source"] = (
                    "wicket_ball_event")
                log.info(
                    f"[POST-WICKET-CARD-PROPAGATE] "
                    f"'{dismissed}' dismissed but not in crease "
                    f"slots — batting_card.status flipped "
                    f"'batting'→'out' (real-time-delayed-"
                    f"witness path, Fix 13 Case 5).")
            return
        if striker_dismissed and not non_dismissed:
            # AUTHORITATIVE-SBINN-READ: surviving non for rotation into striker.
            # striker_path_b_read_audit.md R5 §2.1.1
            _surviving = self._inn.get("non")
            self._inn["striker"] = _surviving
            self._inn["non"] = None
            log.info(
                f"[POST-WICKET-ROTATION] striker '{dismissed}' "
                f"dismissed → rotated non "
                f"'{_surviving}' into striker slot; "
                f"non cleared pending new-batter "
                f"admission.")
        elif non_dismissed and not striker_dismissed:
            self._inn["non"] = None
            log.info(
                f"[POST-WICKET-ROTATION] non "
                f"'{dismissed}' dismissed → slot cleared "
                f"pending new-batter admission.")
        else:
            self._inn["striker"] = None
            self._inn["non"] = None
            log.warn(
                f"[POST-WICKET-ROTATION] anomaly: "
                f"'{dismissed}' occupied BOTH striker and "
                f"non slots — both cleared "
                f"defensively (likely prior collision state "
                f"that Fix 5 did not catch).")

    def apply_known_wicket_increment(
            self, dismissed: str | None,
            extracted_batters: list[dict] | None = None) -> None:
        """Apply post-wicket cleanup before a witnessed FOW arrives.

        ``extracted_batters`` (optional): the same-frame strip read so
        the incoming-batter promotion (Batch J) can prefer a strip-
        sourced candidate over squad-order fallback.
        """
        if not dismissed:
            return
        # Idempotency: if FOW entry for this wicket index already
        # exists, a prior writer this frame (typically the auto-
        # striker-dismiss path at test_pipeline.py:4683 calling
        # dismiss_batter, which writes FOW immutably) has already
        # recorded the wicket.  Calling _add_fow again would be
        # refused as a rewrite, but the side effects above (status
        # flip to "out", _post_witnessed_dismissal_slot_rotation,
        # incoming-batter promote) would still fire — silently
        # marking the wrong batter dismissed because WICKET-ATTRIB
        # at test_pipeline.py:12181 read the post-rotation
        # SM.striker (already the non-dismissed partner).  F407
        # case: W1=KL Rahul written by the first path; this fn
        # called with dismissed=Pathum Nissanka set Pathum.status
        # =out before FOW immutability gate rejected the duplicate
        # entry.  Pre-check the FOW list and no-op when the wicket
        # is already recorded.
        try:
            _cur_wkts_for_idem = int(self._inn.get("wickets") or 0)
        except (TypeError, ValueError):
            _cur_wkts_for_idem = 0
        if _cur_wkts_for_idem > 0 and len(self.fall_of_wickets) >= _cur_wkts_for_idem:
            _existing = self.fall_of_wickets[_cur_wkts_for_idem - 1]
            _existing_batter = (
                _existing.get("batter") if isinstance(_existing, dict)
                else None)
            log.info(
                f"[APPLY-KNOWN-WICKET-IDEMPOTENT-NO-OP] "
                f"FOW W{_cur_wkts_for_idem} already recorded as "
                f"{_existing_batter!r} — skipping duplicate write "
                f"for {dismissed!r} (no status flip, no rotation, "
                f"no incoming-batter promote)")
            return
        resolved = self.resolve_name(dismissed) or dismissed
        card_key = self._find_card_key(resolved, self.batting_card)
        if card_key is None:
            log.info(
                f"[POST-WICKET-PENDING] dismissed={dismissed!r} "
                f"not in batting_card — skipping pending-wicket cleanup")
            return
        self.batting_card[card_key]["status"] = "out"
        self.batting_card[card_key]["dismissal_source"] = "wicket_ball_event"
        try:
            wk = int(self._inn.get("wickets") or 0)
        except (TypeError, ValueError):
            wk = 0
        if wk > 0:
            self._add_fow(
                wk, card_key,
                self._inn.get("score"),
                self._inn.get("overs"),
                how=getattr(self, "pending_dismissal_hint", None),
                bowler=(getattr(self, "pending_dismissal_bowler", None)
                        or self._inn.get("current_bowler")))
        self._post_witnessed_dismissal_slot_rotation(card_key)
        self._promote_incoming_batter_after_wicket(
            card_key, extracted_batters=extracted_batters,
            source="apply_known_wicket_increment")

    def _promote_incoming_batter_after_wicket(
            self, dismissed_name: str,
            extracted_batters: list[dict] | None = None,
            source: str = "unknown") -> str | None:
        """Promote the incoming batter to ``status=batting`` immediately
        on a wicket-event rollover.

        Eliminates the upstream poison cascade documented in
        ``files/docs/investigations/score_manager_overs_commit_stall.md``:
        without this hook, ``apply_overlay_strip_batter_pop_guard``
        treats clean strip reads of the new pair as overlay graphics
        because the active-batting set still names only the surviving
        partner.

        Promotion source (single path, Batch L 2026-05-04):
          1. Strip read (``extracted_batters`` arg). Picks the first
             non-dismissed name that resolves to a ``yet_to_bat`` card
             entry. Highest confidence — the broadcast strip already
             names the incoming batter.

        Squad next-in-order fallback was REMOVED in Batch L. F285 KKR
        vs PBKS demonstrated that the squad list order is the
        team-sheet position, not the actual batting order; promoting
        the lowest-position ``yet_to_bat`` entry (Markram) when the
        real incoming batter was Pooran caused a phantom-dismissal
        cascade 17 frames later when Pooran's strip read was treated
        as a new arrival, demoting the wrongly-promoted Markram.

        New policy when strip has no candidate: defer. Emit
        ``[INCOMING-BATTER-PENDING]`` and return ``None``. The
        active-batting set may briefly be size-1; the next strip-read
        path (``apply_overlay_strip_batter_pop_guard`` /
        ``update_batter``) promotes whoever the broadcast actually
        shows.

        Idempotent: no-op when ``len(active) >= 2`` (some other path
        already promoted) or when no ``yet_to_bat`` entries remain
        (innings is all-out).
        """
        active = [n for n, c in self.batting_card.items()
                  if c.get("status") == "batting"]
        if len(active) >= 2:
            return None

        candidate: str | None = None
        promoted_via: str | None = None

        for ext_b in (extracted_batters or []):
            if not isinstance(ext_b, dict):
                continue
            ext_name = ext_b.get("name", "")
            if not ext_name:
                continue
            ext_resolved = self.resolve_name(ext_name)
            if ext_resolved is None or ext_resolved == dismissed_name:
                continue
            card_entry = self.batting_card.get(ext_resolved)
            if (card_entry is not None
                    and card_entry.get("status") == "yet_to_bat"):
                candidate = ext_resolved
                promoted_via = "strip"
                break

        if candidate is None:
            yet_to_bat_count = sum(
                1 for c in self.batting_card.values()
                if c.get("status") == "yet_to_bat")
            if yet_to_bat_count > 0:
                log.info(
                    f"  [INCOMING-BATTER-PENDING] dismissed="
                    f"'{dismissed_name}' source={source} — strip had "
                    f"no candidate; deferring (yet_to_bat slots="
                    f"{yet_to_bat_count}, awaiting strip read). "
                    f"Squad-order fallback removed: F285 KKR vs PBKS "
                    f"showed squad list ≠ batting order, producing "
                    f"phantom dismissal cascade when guessed batter's "
                    f"actual arrival was misread as the wrong player.")
            return None

        self.batting_card[candidate]["status"] = "batting"
        self.batting_card[candidate]["promoted_source"] = (
            f"{source}:{promoted_via}")
        log.info(
            f"  [INCOMING-BATTER-PROMOTED] '{candidate}' → batting "
            f"after wicket of '{dismissed_name}' "
            f"(source={source}:{promoted_via})")
        return candidate

    def infer_fow_from_batting_order(self):
        """Deprecated: deliberate no-op (no-fabrication policy).

        This method used to guess the dismissed batter for unknown
        FOW placeholders by walking the batting order and picking
        the lowest-position `yet_to_bat` player.  That guess was
        wrong often enough (any time the actual dismissal order
        differed from the batting order, or the broadcast hadn't
        yet surfaced an incoming batter) that it polluted FOW with
        confidently-wrong names — verified on 2026-04-19 KKR-vs-RR
        where W6 was attributed to Vaibhav Sooryavanshi by this
        path even though Jofra Archer was the actual dismissal.

        New policy: an empty / `_unwitnessed=True` FOW entry is
        better than a wrong one.  The UI renders these as
        "W{n} — details unavailable" until either:
          * a real wicket event surfaces with full details, or
          * the cold-start CB-scrape enrichment path populates them.
        """
        return

    def sync_fow_to_wickets(self):
        """Ensure FOW list length matches actual wickets count.

        Immutability principle: confirmed FOW entries are PERMANENT.
        We will only ever ADD placeholders for wickets we know
        happened but missed the details of (e.g. mid-innings join).
        We will NEVER trim, even if the wickets counter regresses —
        because a wickets-counter regression is itself a bug
        (the only way wickets go down is an innings change, which
        runs `start_new_innings` and clears FOW explicitly), and
        deleting a confirmed FOW entry to "make the math work" with
        a corrupt wickets counter is the wrong direction. Log loudly
        instead so the underlying mis-read is visible.
        """
        wk = int(self._inn.get("wickets") or 0)
        if len(self.fall_of_wickets) > wk:
            log.info(
                f"[FOW] Length {len(self.fall_of_wickets)} > "
                f"wickets counter {wk} — keeping all FOW entries "
                f"(immutable). Wickets counter likely regressed.")
        # Seeding policy:
        #  * gap == 1 AND we already have ≥1 confirmed FOW: a fresh
        #    wicket likely just fell — current striker / score / overs
        #    are reasonable best-effort guesses that the dismissal
        #    graphic will upgrade in seconds.
        #  * gap > 1, or this is cold-start (no prior FOW): we are
        #    back-filling wickets that fell in the unobserved past.
        #    Current striker/score/overs are NOT correct for those
        #    historical events — seeding them produces nonsense like
        #    "46/1, 46/2, 46/3 (Stubbs, 5.2)" three times for wickets
        #    that actually fell at different scores in different overs.
        #    Use "unknown" placeholders instead; broadcast graphics
        #    (or the scorecard summary on innings break) will upgrade
        #    them as data arrives.
        # === No-fabrication rule ===
        # Every placeholder we add here is for a wicket we did NOT
        # witness end-to-end through the ball-event path.  Mark them
        # `_unwitnessed: True` so the UI can render an honest
        # "W{n} — details unavailable" instead of guessing, and so
        # `_add_fow` can distinguish placeholders that are safe to
        # upgrade (unwitnessed) from confirmed entries that must
        # never be rewritten by the regular wicket-detection path.
        #
        # Previously the "fresh wicket" branch (gap == 1, mid-game)
        # seeded a placeholder with `current_striker` as the
        # dismissed batter and force-marked them OUT in the batting
        # card.  That was the source of the Jofra-Archer→Vaibhav-
        # Sooryavanshi flip on 2026-04-19: striker state lagged the
        # broadcast by one rotation, so the wrong batter was named
        # in the placeholder, marked OUT in the card, and later when
        # the real dismissal graphic surfaced the rewrite path
        # tripped because the existing entry's batter was now flagged
        # `status="out"` but the new entry's batter was on a
        # different team / never batted.  Removing the seed (and
        # hence the side-effect on the batting card) eliminates the
        # whole class of bugs at the cost of ~2-5 frames where the
        # UI shows "details unavailable" before the real wicket
        # event populates the slot via `_add_fow`.
        while len(self.fall_of_wickets) < wk:
            missing_wk = len(self.fall_of_wickets) + 1
            self.fall_of_wickets.append(
                Scoreboard.make_fow_placeholder(missing_wk))
            log.info(f"[FOW] Placeholder W{missing_wk}: _unwitnessed "
                     f"(no fabrication — awaiting real wicket event "
                     f"or CB scrape enrichment)")

    @staticmethod
    def make_fow_placeholder(wicket_number: int) -> dict:
        """Single source of truth for FOW placeholder entry shape.

        Issue 4 fix (2026-04-21): consolidates the two divergent paths
        (`_ensure_fow_placeholders` here and the cold-start pre-populate
        in `test_pipeline.py`) into one factory.  Previously the
        cold-start path seeded `batter="unknown", score="?", overs="?"`
        WITHOUT `_unwitnessed: True`, so the UI rendered those as
        confirmed wickets with garbage values.  Anyone needing a
        placeholder MUST go through this function.
        """
        return {
            "wicket": int(wicket_number),
            "batter": None,
            "score": None,
            "overs": None,
            "bowler": None,
            "_unwitnessed": True,
        }

    # ------------------------------------------------------------------
    # Dismissals
    # ------------------------------------------------------------------

    def _is_witnessed_dismissal(self, name: str) -> bool:
        """True if `name` has a witnessed (non-placeholder) FOW entry.

        Canonical "is this batter a confirmed dismissal" check used by
        invariant guards.  A name is a confirmed dismissal iff there is
        a `fall_of_wickets` entry whose `batter == name`, with
        `_witnessed=True` and not `_unwitnessed=True` (back-fill
        placeholders carry `_unwitnessed=True`; real wicket events
        stamp `_witnessed=True` via `_add_fow`, line ~2375).

        Used by:
          * `update_batter()` un-dismiss prevention (refuses to un-
            dismiss a batter the FOW says was actually out);
          * `validate_state_consistency()` post-hoc resurrection demote
            and FOW-preferred max-2 deactivation.

        Filed 2026-04-25 (DC vs PBKS F339 active-batter resurrection
        regression — see backlog P0 "SCORER doesn't enforce active-
        batter invariants").
        """
        for f in self.fall_of_wickets:
            if (f.get("batter") == name
                    and f.get("_witnessed")
                    and not f.get("_unwitnessed")):
                return True
        return False

    def dismiss_batter(self, name: str, how: str | None = None,
                       bowler: str | None = None, fielder: str | None = None,
                       frame: int = 0,
                       extracted_batters: list[dict] | None = None) -> bool:
        # Idempotency: same race as apply_known_wicket_increment.
        # The existing `entry["status"] != "batting"` check below
        # protects against the SAME batter being dismissed twice, but
        # NOT against a DIFFERENT batter being dismissed for the SAME
        # wicket-counter (e.g. auto-striker-dismiss writes FOW W1
        # =Rahul; then the scorer-decision path at test_pipeline.py:
        # 4725 calls dismiss_batter("Pathum") for the same wicket.
        # Pathum.status is still "batting", check passes, function
        # corrupts Pathum.status to "out" before _add_fow's
        # immutability gate rejects the duplicate entry).  Pre-check
        # FOW length against current wickets counter.
        try:
            _cur_wkts_for_idem = int(self._inn.get("wickets") or 0)
        except (TypeError, ValueError):
            _cur_wkts_for_idem = 0
        if _cur_wkts_for_idem > 0 and len(self.fall_of_wickets) >= _cur_wkts_for_idem:
            _existing = self.fall_of_wickets[_cur_wkts_for_idem - 1]
            _existing_batter = (
                _existing.get("batter") if isinstance(_existing, dict)
                else None)
            if _existing_batter != name:
                log.info(
                    f"[DISMISS-BATTER-IDEMPOTENT-NO-OP] "
                    f"FOW W{_cur_wkts_for_idem} already recorded as "
                    f"{_existing_batter!r} — skipping duplicate write "
                    f"for {name!r} (no status flip, no rotation)")
                return False
        resolved = self.resolve_name(name)
        if resolved is None:
            log.warn(f"Dismiss: '{name}' not in any squad")
            return False
        card_key = self._find_card_key(resolved, self.batting_card)
        if card_key is None:
            log.warn(f"Dismiss: '{name}' not in batting card"
                     f" (resolved: {resolved})")
            return False
        name = card_key

        entry = self.batting_card[name]
        if entry["status"] != "batting":
            self._dismiss_attempt_count[name] = \
                self._dismiss_attempt_count.get(name, 0) + 1
            ct = self._dismiss_attempt_count[name]
            if ct <= 3:
                log.warn(f"Dismiss: {name} status is "
                         f"'{entry['status']}', not batting")
            # After 3 failed attempts, silently suppress to reduce log noise
            return False

        entry["status"] = "out"
        entry["dismissal"] = {"how": how, "bowler": bowler, "fielder": fielder}
        entry["dismissal_source"] = "wicket_ball_event"

        score = self._inn.get("score", 0) or 0
        overs = self._inn.get("overs", "0")
        wk = self._inn.get("wickets") or 0

        self._add_fow(wk, name, score, overs, how=how, bowler=bowler)

        log.info(f"DISMISSED: {name} {entry['runs']}({entry['balls']}) "
                 f"— {how or '?'} | FOW {wk}/{score} ({overs})")

        # AUTHORITATIVE-SBINN-READ: legacy striker clear (audit R6 §2.1.1)
        if self._inn.get("striker") == name:
            self._inn["striker"] = None
        # AUTHORITATIVE-SBINN-READ: legacy non clear (audit R7 §2.1.1)
        if self._inn.get("non") == name:
            self._inn["non"] = None

        self._promote_incoming_batter_after_wicket(
            name, extracted_batters=extracted_batters,
            source="dismiss_batter")

        return True

    # ------------------------------------------------------------------
    # Innings management
    # ------------------------------------------------------------------

    def start_new_innings(self, batting_squad: list[str],
                          bowling_squad: list[str], frame: int = 0):
        if self.match_complete:
            log.info(
                f"[MATCH-COMPLETE] start_new_innings refused — match "
                f"already resolved ({self.match_end_reason}).")
            return
        if self.current_innings >= 2:
            log.error("Cannot start innings 3")
            return

        inn1_score = self._inn.get("score") or 0
        old_bat = self.batting_team
        old_bowl = self.bowling_team

        log.info(f"[INNINGS] {old_bowl} now batting. Target: {int(inn1_score) + 1}")

        self.current_innings = 2
        self._tracker = ConsistentReadTracker()
        self._dismissed_recovery = {}
        self._dismiss_attempt_count = {}
        self._last_autodismiss_wickets = 0
        # Fix #1 / #3 (2026-04-23): innings 2 starts at wickets=0 with
        # no rotation history; reset both counters so new-innings cold
        # start behaves cleanly.
        self._wickets_confirmed_frames_at_zero = 0
        self._rotation_rejection_count = {}
        # P0-2 (2026-04-22): XI rejection tracker is per-innings state.
        # Each innings has its own bowling team whose squad/XI status
        # was scraped independently; stale rejection history from
        # innings-1 must not influence innings-2 promotion decisions.
        self._xi_rejection_views = {}
        self._missing_batter_streak = {}
        self.extras = self._blank_extras()
        self.this_over = []
        self.over_history = {}
        self.bowler_speeds = {}
        self.bowler_type = {}
        self._last_over_num = None
        self._bowler_must_change = False
        self._prev_over_bowler = None
        self._bowler_locked = False
        self._bowler_lock_frame = 0

        self.batting_team = old_bowl
        self.bowling_team = old_bat

        self.batting_card = {}
        for name in batting_squad:
            st = self._player_styles.get(name) or {}
            self.batting_card[name] = {
                "runs": None, "balls": None,
                "fours": None, "sixes": None, "sr": None,
                "status": "yet_to_bat", "dismissal": None,
                "dismissal_source": None,
                "position": len(self.batting_card) + 1,
                "batting_style": st.get("batting_style", "unknown"),
                "bowling_style": st.get("bowling_style", "unknown"),
            }

        _bc_prev_size = len(getattr(self, "bowling_card", {}) or {})
        self.bowling_card = {}
        try:
            from trace_emitter import get_recorder as _bcget
            _bcget().record(
                tag="BOWLING-CARD-CLEARED",
                reason="innings2_init",
                prev_size=int(_bc_prev_size),
                squad_size=len(bowling_squad))
        except Exception:
            pass
        for name in bowling_squad:
            st = self._player_styles.get(name) or {}
            self.bowling_card[name] = {
                "overs": None, "maidens": 0,
                "runs": None, "wickets": None, "econ": None,
                "balls": 0,
                "balls_this_over": 0,
                "runs_this_over": 0,
                "byes_lb_this_over": 0,
                "position": len(self.bowling_card) + 1,
                "batting_style": st.get("batting_style", "unknown"),
                "bowling_style": st.get("bowling_style", "unknown"),
            }
        # Reset BOWLER-STALE freshness tracking — innings-2 is a
        # different bowling team with no carried-over write history.
        self._bowling_card_active_write_frame = {}
        self._bowling_card_active_write_bowler = {}

        inn2 = self._inn
        inn2["batting_team"] = self.batting_team
        inn2["bowling_team"] = self.bowling_team
        inn2["target"] = int(inn1_score) + 1
        inn2["score"] = 0
        inn2["wickets"] = 0
        inn2["overs"] = "0.0"
        # Clear innings-1 player identities — innings-2 has a fresh
        # striker/non pair and a fresh opening bowler.
        # Without this the UI keeps showing the previous team's
        # batters on the scorestrip until the new batters get
        # activated (which can take many frames during the break).
        inn2["striker"] = None
        inn2["non"] = None
        inn2["current_bowler"] = None
        inn2["run_rate"] = None

        self.fall_of_wickets = []
        self.partnerships = []
        self.current_partnership = None

    # ------------------------------------------------------------------
    # Format cards as tables for agent prompts
    # ------------------------------------------------------------------

    def format_batting_card(self) -> str:
        lines = [f"{'#':>2} {'Player':<22} {'Status':<12} {'R':>4} {'B':>4} "
                 f"{'4s':>3} {'6s':>3} {'SR':>7}"]
        lines.append("-" * 65)
        for name, s in self.batting_card.items():
            pos = s["position"]
            status = s["status"]
            r = s["runs"] if s["runs"] is not None else "-"
            b = s["balls"] if s["balls"] is not None else "-"
            f4 = s["fours"] if s["fours"] is not None else "-"
            f6 = s["sixes"] if s["sixes"] is not None else "-"
            sr = f"{s['sr']:.1f}" if s.get("sr") is not None else "-"
            lines.append(f"{pos:>2} {name:<22} {status:<12} {r:>4} {b:>4} "
                         f"{f4:>3} {f6:>3} {sr:>7}")
        return "\n".join(lines)

    def format_bowling_card(self) -> str:
        lines = [f"{'Player':<22} {'O':>5} {'M':>2} {'R':>4} {'W':>2} {'Econ':>6}"]
        lines.append("-" * 45)
        for name, s in self.bowling_card.items():
            o = s["overs"] if s["overs"] is not None else "-"
            m = s["maidens"] if s["maidens"] is not None else "-"
            r = s["runs"] if s["runs"] is not None else "-"
            w = s["wickets"] if s["wickets"] is not None else "-"
            e = f"{s['econ']:.1f}" if s.get("econ") is not None else "-"
            lines.append(f"{name:<22} {o:>5} {m:>2} {r:>4} {w:>2} {e:>6}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Live state for prompts
    # ------------------------------------------------------------------

    def get_live_state(self) -> dict:
        inn = self._inn
        active_batters = [(n, s) for n, s in self.batting_card.items()
                          if s["status"] == "batting"]
        # AUTHORITATIVE-SBINN-READ: legacy projection snapshot (prompts / WS
        # via _project_active_batters). striker_path_b_read_audit.md R8 §2.1.2
        striker = inn.get("striker")
        non = inn.get("non")

        return {
            "score": inn.get("score"),
            "wickets": inn.get("wickets"),
            "overs": inn.get("overs"),
            "batting_team": self.batting_team,
            "bowling_team": self.bowling_team,
            "striker": striker,
            "non": non,
            "current_bowler": inn.get("current_bowler"),
            "last_bowler": inn.get("last_bowler"),
            "bowler_between_overs": bool(inn.get("bowler_between_overs")),
            "run_rate": inn.get("run_rate"),
            "target": inn.get("target"),
            "active_batters": {n: {"runs": s["runs"], "balls": s["balls"]}
                               for n, s in active_batters},
            "innings": self.current_innings,
            "match_complete": self.match_complete,
            "match_end_reason": self.match_end_reason,
            "match_result": self.match_result,
        }

    def get_broadcast_state(self) -> dict:
        """Back-compat alias for :meth:`get_live_state`.

        ``get_broadcast_state`` previously rewrote striker / non-striker
        against the active batting list. That path was redundant on live
        frames (``test_pipeline._project_active_batters`` overwrites slots
        at the WS boundary) and differed from shadow behaviour. Prefer
        :meth:`get_live_state` in new code; WS broadcast uses
        ``get_live_state`` + ``_project_active_batters`` (Cluster 1 / Fix 7).

        See ``files/docs/investigations/get_broadcast_state_path_b_audit.md``
        (Option A, 2026-04-29).
        """
        return self.get_live_state()

    def get_live_state_str(self) -> str:
        ls = self.get_live_state()
        score = ls.get("score", "?")
        wk = ls.get("wickets", "?")
        ov = ls.get("overs", "?")

        striker = ls.get("striker", "?")
        non = ls.get("non", "?")

        s_stats = ""
        ns_stats = ""
        if striker and striker in self.batting_card:
            e = self.batting_card[striker]
            s_stats = f" {e['runs']}({e['balls']})"
        if non and non in self.batting_card:
            e = self.batting_card[non]
            ns_stats = f" {e['runs']}({e['balls']})"

        bowler = ls.get("current_bowler", "?")
        b_stats = ""
        if bowler and bowler in self.bowling_card:
            e = self.bowling_card[bowler]
            b_stats = f" {e['wickets']}-{e['runs']} ({e['overs']})"

        return (f"Score: {score}-{wk} ({ov})\n"
                f"Striker: {striker}{s_stats}\n"
                f"Non-striker: {non}{ns_stats}\n"
                f"Bowler: {bowler}{b_stats}")

    # ------------------------------------------------------------------
    # Full state for API/debug
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return {
            "current_innings": self.current_innings,
            "batting_team": self.batting_team,
            "bowling_team": self.bowling_team,
            "innings": deepcopy(self.innings),
            "batting_card": deepcopy(self.batting_card),
            "bowling_card": deepcopy(self.bowling_card),
            "fall_of_wickets": deepcopy(self.fall_of_wickets),
            "extras": deepcopy(self.extras),
            "this_over": self.this_over[:],
            "over_history": deepcopy(self.over_history),
        }

    def get_summary(self) -> dict:
        """Short summary for quick display."""
        inn = self._inn
        # AUTHORITATIVE-SBINN-READ: legacy projection snapshot (e.g. main
        # log). striker_path_b_read_audit.md R9 §2.1.2
        return {
            "innings": self.current_innings,
            "batting_team": self.batting_team,
            "bowling_team": self.bowling_team,
            "score": inn.get("score"),
            "wickets": inn.get("wickets"),
            "overs": inn.get("overs"),
            "run_rate": inn.get("run_rate"),
            "target": inn.get("target"),
            "striker": inn.get("striker"),
            "non": inn.get("non"),
            "current_bowler": inn.get("current_bowler"),
        }

    # ------------------------------------------------------------------
    # State invariants — run after every update cycle
    # ------------------------------------------------------------------

    def validate_state_consistency(self):
        """Enforce hard invariants after every update cycle."""
        score = self._inn.get("score") or 0
        wickets = self._inn.get("wickets") or 0

        # --- Invariant 1: batter runs can never exceed team score ---
        if score:
            total_batter_runs = sum(
                card.get("runs", 0) or 0
                for card in self.batting_card.values()
                if card.get("status") in ("batting", "out")
            )

            # Fix 18 Layer 2 (bat-runs reconciler detection,
            # 2026-04-26): observability diagnostic firing on
            # smaller divergences (>+5) than the cap-reset
            # threshold (>+10).  Detection-only — surfaces the
            # divergence for postmortem before it grows to the
            # cap threshold.  Counts per match into
            # `_L2_RECONCILER_FIRES` for the analyzer.
            if total_batter_runs > score + self._L2_RECONCILER_THRESHOLD:
                log.warn(
                    f"[BAT-SUM-RECONCILER] divergence detected: "
                    f"bat_sum={total_batter_runs} > score+{self._L2_RECONCILER_THRESHOLD}"
                    f"={score + self._L2_RECONCILER_THRESHOLD} "
                    f"(excess={total_batter_runs - score}).  "
                    f"Layer 2 detection-only — Layer 3 cap-reset "
                    f"engages at +{self._L3_CAP_RESET_THRESHOLD}.")
                if not hasattr(self, "_L2_RECONCILER_FIRES"):
                    self._L2_RECONCILER_FIRES = 0
                self._L2_RECONCILER_FIRES += 1

            if total_batter_runs > score + self._L3_CAP_RESET_THRESHOLD:
                log.warn(f"[INVARIANT] Batter total {total_batter_runs} > "
                         f"score {score}+10. Capping batters.")
                # Fix 18 Layer 3 (cap-reset Path C hybrid,
                # 2026-04-26): the legacy reset only fired when an
                # *individual* batter's runs > score.  In split-
                # phantom cases (Brevis +1, Dube +22 on top of
                # score 30) neither individual batter exceeds
                # score, so no reset fired (199 cap warnings, 0
                # resets in the CSK-vs-GT 31-min window).  Path C
                # hybrid: identify the most-recently-advanced
                # batter (by frame in `_last_runs_advance`) and
                # reset that one.  The most recent advance is the
                # most likely phantom because legitimate scoring
                # advances are bounded by ball cadence; phantom
                # OCR jitter advances are unbounded.  Iterative:
                # after each reset, recompute and continue while
                # over-cap (max 2 iterations, matching the active
                # batter count).
                _l3_iter = 0
                while (_l3_iter < 2
                       and total_batter_runs > score
                       + self._L3_CAP_RESET_THRESHOLD):
                    _l3_iter += 1
                    # Pick most-recent advance among active batters
                    _active_advance = [
                        (n, self._last_runs_advance.get(n, {}))
                        for n, c in self.batting_card.items()
                        if c.get("status") == "batting"
                    ]
                    _active_advance = [
                        (n, a) for n, a in _active_advance
                        if a.get("frame") is not None]
                    _active_advance.sort(
                        key=lambda x: x[1].get("frame", -1),
                        reverse=True)
                    if not _active_advance:
                        # Fall back to legacy per-batter check.
                        for name, card in self.batting_card.items():
                            if card.get("status") == "batting":
                                runs = card.get("runs", 0) or 0
                                if runs > score:
                                    card["runs"] = None
                                    card["balls"] = None
                                    self._tracker.force_set(
                                        f"bat:{name}:runs", None)
                                    self._tracker.force_set(
                                        f"bat:{name}:balls", None)
                                    log.warn(
                                        f"[INVARIANT] {name} "
                                        f"runs {runs} > score "
                                        f"{score} — reset "
                                        f"(legacy per-batter)")
                        break
                    _victim, _advance = _active_advance[0]
                    _runs_before = (
                        self.batting_card[_victim].get("runs"))
                    self.batting_card[_victim]["runs"] = None
                    self.batting_card[_victim]["balls"] = None
                    self._tracker.force_set(
                        f"bat:{_victim}:runs", None)
                    self._tracker.force_set(
                        f"bat:{_victim}:balls", None)
                    self._last_runs_advance.pop(_victim, None)
                    log.warn(
                        f"[CAP-RESET-LAST-ADVANCE] iter={_l3_iter} "
                        f"reset '{_victim}' (runs was "
                        f"{_runs_before}, last advance at frame "
                        f"{_advance.get('frame')} "
                        f"{_advance.get('from')}→"
                        f"{_advance.get('to')}).  "
                        f"bat_sum was {total_batter_runs} > "
                        f"score+{self._L3_CAP_RESET_THRESHOLD}; "
                        f"Path C hybrid (Fix 18 Layer 3).")
                    if not hasattr(self, "_L3_CAP_RESET_FIRES"):
                        self._L3_CAP_RESET_FIRES = 0
                    self._L3_CAP_RESET_FIRES += 1
                    # Recompute total for next iteration.
                    total_batter_runs = sum(
                        c.get("runs", 0) or 0
                        for c in self.batting_card.values()
                        if c.get("status") in ("batting", "out"))

        # --- Invariant 2: no FOW-witnessed dismissals in active set ---
        # Fix 2 (2026-04-25, P0-A): defense-in-depth against the F339
        # resurrection class.  Even if some other code path bypasses
        # `update_batter`'s un-dismiss guard (Fix 1), this post-hoc
        # check demotes any batter back to "out" if FOW carries a
        # witnessed entry for them.  Option A: just demote, no
        # replacement inference — leaving a "vacancy" (one active
        # batter) is a separate problem the existing code already
        # handles, and inferring a replacement from squad position
        # could itself be wrong.
        active = [n for n, c in self.batting_card.items()
                  if c["status"] == "batting"]
        for name in active:
            if self._is_witnessed_dismissal(name):
                log.warn(f"[INVARIANT] Demoting resurrected batter "
                         f"'{name}' (witnessed FOW entry) — restoring "
                         f"out status")
                self.batting_card[name]["status"] = "out"
                self.batting_card[name]["dismissal_source"] = (
                    "wicket_ball_event")
                # Preserve dismissal record by recovering it from FOW
                # if the entry was wiped by the un-dismiss path.
                if not self.batting_card[name].get("dismissal"):
                    fow = next(
                        (f for f in self.fall_of_wickets
                         if f.get("batter") == name and f.get("_witnessed")),
                        None,
                    )
                    if fow:
                        self.batting_card[name]["dismissal"] = {
                            "how": fow.get("how"),
                            "bowler": fow.get("bowler"),
                            "fielder": fow.get("fielder"),
                        }

        # --- Invariant 3: max 2 active batters ---
        # Fix 3 (2026-04-25, P0-A): prefer FOW-witnessed dismissals
        # over squad position when deactivating excess actives.  The
        # legacy position-based sort would deactivate the lower-order
        # batter (e.g. Rana, pos 5) when the *resurrected* one
        # (Pathum, pos 2) was the actual culprit.  Most violations
        # should be caught by Invariant 2 above; if a violation
        # survives, FOW-resurrected first / position fallback is the
        # right ordering.
        active = [n for n, c in self.batting_card.items()
                  if c["status"] == "batting"]
        if len(active) > 2:
            log.warn(f"[INVARIANT] {len(active)} active batters: {active}")
            fow_resurrected = [n for n in active
                               if self._is_witnessed_dismissal(n)]
            if fow_resurrected:
                for name in fow_resurrected[:len(active) - 2]:
                    self.batting_card[name]["status"] = "out"
                    self.batting_card[name]["dismissal_source"] = (
                        "wicket_ball_event")
                    log.warn(f"[INVARIANT] Demoting resurrected batter "
                             f"'{name}' from active set "
                             f"(FOW-witnessed dismissal)")
                active = [n for n, c in self.batting_card.items()
                          if c["status"] == "batting"]

            if len(active) > 2:
                # No (more) FOW resurrections — fall back to position.
                # This branch should not normally fire: if max-2 is
                # violated, at least one active should be FOW-witnessed.
                log.warn(f"[INVARIANT] Falling back to position-based "
                         f"deactivation; no FOW match in active set "
                         f"{active} (anomaly)")
                sorted_by_pos = sorted(
                    active,
                    key=lambda n: self.batting_card[n].get("position", 99))
                for name in sorted_by_pos[2:]:
                    self.batting_card[name]["status"] = "yet_to_bat"
                    log.warn(f"[INVARIANT] Deactivated {name} "
                             f"(pos {self.batting_card[name].get('position')})")

        # --- Invariant 4: bowler wickets can never exceed team wickets ---
        if wickets:
            for name, card in self.bowling_card.items():
                bw = card.get("wickets")
                if bw is not None and int(bw) > int(wickets):
                    log.warn(f"[INVARIANT] {name} has {bw} wickets but "
                             f"team only lost {wickets} — capping")
                    card["wickets"] = int(wickets)
                    self._tracker.force_set(
                        f"bowl:{name}:wickets", int(wickets))

    # ------------------------------------------------------------------
    # State persistence — save/restore across restarts
    # ------------------------------------------------------------------

    def get_cache_dict(self, frame: int) -> dict:
        """Serialise essential state for on-disk caching."""
        return {
            "score": self._inn.get("score"),
            "wickets": self._inn.get("wickets"),
            "overs": self._inn.get("overs"),
            "run_rate": self._inn.get("run_rate"),
            "target": self._inn.get("target"),
            "batting_team": self.batting_team,
            "bowling_team": self.bowling_team,
            "innings": self.current_innings,
            # AUTHORITATIVE-SBINN-READ: disk cache must round-trip _inn restore.
            # striker_path_b_read_audit.md R10 §2.1.3
            "striker": self._inn.get("striker"),
            "non": self._inn.get("non"),
            "current_bowler": self._inn.get("current_bowler"),
            "batting_card": {
                k: {kk: vv for kk, vv in v.items()}
                for k, v in self.batting_card.items()
                if v.get("status") in ("batting", "out")
            },
            "bowling_card": {
                k: {kk: vv for kk, vv in v.items()}
                for k, v in self.bowling_card.items()
                if v.get("overs") and float(v.get("overs", "0") or "0") > 0
            },
            "fall_of_wickets": self.fall_of_wickets[:],
            "over_history": {str(k): v for k, v in self.over_history.items()},
            "match_id": os.environ.get("CRICBUZZ_MATCH_ID"),
            "session_id": os.environ.get("BMF_SESSION_ID"),
            "frame": frame,
            "saved_at": time.time(),
        }

    def restore_from_cache(self, cached: dict):
        """Restore state from a previously saved cache dict."""
        inn = self._inn
        for field in ("score", "wickets", "overs", "run_rate",
                      "target", "striker", "non", "current_bowler"):
            if cached.get(field) is not None:
                inn[field] = cached[field]

        if cached.get("score") is not None:
            self._tracker.force_set("score", int(cached["score"]))
        if cached.get("overs") is not None:
            self._tracker.force_set("overs", str(cached["overs"]))
        if cached.get("wickets") is not None:
            self._tracker.force_set("wickets", int(cached["wickets"]))

        for name, card_data in (cached.get("batting_card") or {}).items():
            if name in self.batting_card:
                # Restore batting stats but mark dismissed players as
                # yet_to_bat so the strip can re-confirm who's actually in.
                # This prevents stale dismissed lists from blocking
                # players who are visibly batting after a restart.
                if card_data.get("status") == "out":
                    card_data = dict(card_data)
                    card_data["status"] = "yet_to_bat"
                    card_data["dismissal"] = None
                    card_data["runs"] = None
                    card_data["balls"] = None
                self.batting_card[name].update(card_data)
                if card_data.get("status") == "batting":
                    r = int(card_data["runs"]) if card_data.get("runs") is not None else None
                    b = int(card_data["balls"]) if card_data.get("balls") is not None else None
                    if r is not None:
                        self._tracker.force_set(f"bat:{name}:runs", r)
                    if b is not None:
                        self._tracker.force_set(f"bat:{name}:balls", b)

        # Reset dismissed recovery counters and FOW on restore
        self._dismissed_recovery = {}
        self._dismissed_inferred = False
        # After a restore, any wickets already on the scoreboard were
        # witnessed BEFORE we joined — we can't fire auto-dismiss for
        # them.  Seed the gate at the current wicket count so only
        # NEW wickets (post-restore) can trigger auto-dismissal.
        try:
            self._last_autodismiss_wickets = int(
                self._inn.get("wickets") or 0)
        except (TypeError, ValueError):
            self._last_autodismiss_wickets = 0
        # Fix #1 (2026-04-23): the cache confirms prior wicket state;
        # prime the zero-streak past the seed threshold so a
        # subsequent 0→1 transition on this session is recognised as
        # a real live event, not a cold-start historical seed.
        self._wickets_confirmed_frames_at_zero = max(
            self._wickets_confirmed_frames_at_zero, 2)
        self._missing_batter_streak = {}

        for name, card_data in (cached.get("bowling_card") or {}).items():
            if name in self.bowling_card:
                self.bowling_card[name].update(card_data)

        self.fall_of_wickets = cached.get("fall_of_wickets", [])

        log.info(f"[CACHE] Restored: {cached.get('score')}-"
                 f"{cached.get('wickets')} ({cached.get('overs')}) "
                 f"from frame {cached.get('frame')}")

    # ------------------------------------------------------------------
    # This-over tracking (broadcast-sourced only, no delta reconstruction)
    # ------------------------------------------------------------------

    def record_extra(self, extra_type: str, runs: int = 1):
        """Record an extra (wide, no_ball, bye, leg_bye)."""
        key_map = {
            "wide": "wides", "no_ball": "no_balls",
            "bye": "byes", "leg_bye": "leg_byes",
            "penalty": "penalties",
        }
        key = key_map.get(extra_type)
        if key:
            self.extras[key] += runs
            self.extras["total"] += runs
            self.extras["this_over"] = (self.extras.get("this_over", 0)
                                        or 0) + 1
            entry = {
                "over": self._inn.get("overs"),
                "type": extra_type,
                "runs": runs,
                "this_over_after": list(self.this_over),
            }
            log_list = self.extras.setdefault("log", [])
            log_list.append(entry)
            if len(log_list) > 50:
                self.extras["log"] = log_list[-50:]
            log.info(f"[EXTRA] {extra_type} +{runs} at "
                     f"{self._inn.get('overs')}o  "
                     f"this_over_extras={self.extras['this_over']}  "
                     f"innings_total={self.extras['total']}  "
                     f"this_over_now={self.this_over}")

    def update_this_over(self, broadcast: list):
        """Update this-over from the broadcast indicator — sole source of
        ball-by-ball data. The broadcast shows cumulative results like
        ['.', '4', '1'] after 3 balls. Always trust broadcast over any
        local state."""
        if not broadcast:
            return

        # Normalise all entries to strings (extractor may send ints)
        broadcast = [str(x) for x in broadcast]

        if broadcast == self.this_over:
            return

        if len(broadcast) < len(self.this_over) and len(self.this_over) > 6:
            log.info(f"[THIS-OVER] Broadcast shorter "
                     f"({len(self.this_over)}→{len(broadcast)}) "
                     f"— new over, resetting")
            self.this_over = broadcast
        elif len(broadcast) >= len(self.this_over):
            self.this_over = broadcast

        if len(self.this_over) > 12:
            log.info(f"[THIS-OVER] {len(self.this_over)} entries — "
                     f"missed reset, trimming to last 6")
            self.this_over = self.this_over[-6:]

    def over_just_changed(self) -> bool:
        """Check if the over number changed since last check."""
        overs_str = self._inn.get("overs") or "0.0"
        try:
            over_num = int(str(overs_str).split(".")[0])
        except (ValueError, TypeError):
            return False
        if self._last_over_num is None:
            self._last_over_num = over_num
            return False
        if over_num != self._last_over_num:
            self._last_over_num = over_num
            return True
        return False

    def on_new_over(self, completed_over: int):
        """Archive the completed over and reset this_over.

        Sets _bowler_must_change flag — same bowler can't bowl
        consecutive overs in limited-overs cricket.
        """
        bowler = self._inn.get("current_bowler")
        archived: dict = {
            "broadcast_balls": self.this_over.copy() if self.this_over else [],
            "bowler": bowler,
        }

        if bowler and bowler in self.bowling_card:
            bc = self.bowling_card[bowler]
            archived["bowler_figures"] = {
                "overs": bc.get("overs"),
                "runs": bc.get("runs"),
                "wickets": bc.get("wickets"),
            }

        # Immutable: first archive of a given over slot wins. A second
        # call for the same `completed_over` is treated as a duplicate
        # archive attempt (e.g. the over rollover misfired and then
        # re-fired on the next sane reading) — keep the original.
        if completed_over in self.over_history:
            log.info(
                f"[ARCHIVE] Over {completed_over} already archived "
                f"({self.over_history[completed_over]}). Refusing "
                f"second archive payload {archived}.")
        else:
            self.over_history[completed_over] = archived

        self._bowler_must_change = True
        self._bowler_locked = False
        self._prev_over_bowler = bowler

        if self.this_over:
            over_runs = sum(int(x) for x in self.this_over
                           if isinstance(x, str) and x.isdigit())
            wkts = sum(1 for x in self.this_over if x == "W")
            log.info(f"Over {completed_over} complete: "
                     f"{self.this_over} = {over_runs} runs, "
                     f"{wkts} wickets (by {bowler or '?'})")
        else:
            log.info(f"Over {completed_over} complete: "
                     f"no ball data (by {bowler or '?'})")
        # Reset per-over extras counter at over boundary; innings total
        # and extras log are preserved for parity diagnostics.
        if self.extras.get("this_over"):
            log.info(f"[EXTRA] over {completed_over} closed with "
                     f"{self.extras['this_over']} extra(s) — "
                     f"resetting per-over counter")
        self.extras["this_over"] = 0
        self.this_over = []

    def record_speed(self, bowler_name: str, speed_kph: float) -> bool:
        """Track bowling speed for a bowler with role-based validation."""
        if not bowler_name or not speed_kph:
            return False
        if speed_kph < 60 or speed_kph > 170:
            return False

        role = self._get_bowler_role(bowler_name)

        # Squad role overrides everything
        if role == "spin" and speed_kph > 105:
            log.info(f"[SPEED] {speed_kph}kph rejected — "
                     f"{bowler_name} is a spinner (squad)")
            return False
        if role == "pace" and speed_kph < 100:
            log.info(f"[SPEED] {speed_kph}kph rejected — "
                     f"{bowler_name} is a pacer (squad)")
            return False

        # First-reading classifier only when squad has no role
        if bowler_name not in self.bowler_speeds:
            self.bowler_speeds[bowler_name] = []
            if role == "":
                if speed_kph < 100:
                    self.bowler_type[bowler_name] = "spin"
                else:
                    self.bowler_type[bowler_name] = "pace"
            else:
                self.bowler_type[bowler_name] = role
        else:
            btype = self.bowler_type.get(bowler_name)
            if btype == "spin" and speed_kph > 105:
                log.info(f"[SPEED] {speed_kph}kph rejected — {bowler_name} "
                         f"classified as spinner")
                return False
            if btype == "pace" and speed_kph < 85:
                log.info(f"[SPEED] {speed_kph}kph rejected — {bowler_name} "
                         f"classified as pacer")
                return False

        self.bowler_speeds[bowler_name].append(speed_kph)
        return True

    _KNOWN_SPINNERS = {
        "RASHID KHAN", "YUZVENDRA CHAHAL", "RAVI BISHNOI",
        "KULDEEP YADAV", "RAVINDRA JADEJA", "AXAR PATEL",
        "MANIMARAN SIDDHARTH", "VARUN CHAKRAVARTHY",
        "RAVICHANDRAN ASHWIN", "WASHINGTON SUNDAR",
        "SUNIL NARINE", "ADAM ZAMPA", "NOOR AHMAD",
        "RAHUL CHAHAR", "PIYUSH CHAWLA", "AMIT MISHRA",
    }

    def _get_bowler_role(self, bowler_name: str) -> str:
        """Determine if a bowler is spin or pace from squad data."""
        role_str = self._squad_roles.get(bowler_name, "").lower()
        if role_str:
            if any(x in role_str for x in (
                    "spin", "slow", "orthodox", "leg-break",
                    "off-break", "sla", "chinaman")):
                return "spin"
            if any(x in role_str for x in (
                    "fast", "pace", "seam", "medium")):
                return "pace"

        if bowler_name.upper() in self._KNOWN_SPINNERS:
            return "spin"

        return ""

    def get_bowler_speed_stats(self, bowler_name: str) -> dict | None:
        """Get speed statistics for a bowler."""
        speeds = self.bowler_speeds.get(bowler_name)
        if not speeds:
            return None
        return {
            "avg_speed": round(sum(speeds) / len(speeds), 1),
            "max_speed": round(max(speeds), 1),
            "min_speed": round(min(speeds), 1),
            "count": len(speeds),
        }

    def initialize_this_over(self, overs) -> None:
        """Pre-fill this-over when joining mid-over."""
        overs_f = float(overs or "0")
        balls_this_over = round((overs_f % 1) * 10)
        if balls_this_over > 0 and len(self.this_over) == 0:
            self.this_over = ["?"] * balls_this_over
            log.info(f"[THIS-OVER] Joined at {overs}, "
                     f"pre-filled {balls_this_over} balls as '?'")

    def get_this_over_runs(self) -> int:
        """Total runs in the current over."""
        return sum(int(x) for x in self.this_over
                   if isinstance(x, str) and x.isdigit())

    def get_this_over_for_display(self) -> list[str]:
        """Return this-over trimmed to match the overs sub-ball count.

        If overs shows X.3, there should be at most 3 legal balls in
        this-over (plus any extras like wd/nb). Excess legal balls from
        a previous over or false detections are trimmed from the front,
        keeping the most recent balls.
        """
        overs_raw = self._inn.get("overs") or "0"
        try:
            overs = float(overs_raw)
        except (ValueError, TypeError):
            return list(self.this_over)

        balls_this_over = round((overs % 1) * 10)
        if balls_this_over == 0:
            return list(self.this_over)

        display = list(self.this_over)

        legal = [x for x in display if str(x).lower() not in ("wd", "nb")]
        extras = [x for x in display if str(x).lower() in ("wd", "nb")]

        if len(legal) > balls_this_over:
            legal = legal[-balls_this_over:]
            display = extras + legal
            log.info(f"[THIS-OVER] Trimmed to {balls_this_over} "
                     f"legal balls: {display}")

        return display

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    def get_current_batters(self) -> str:
        active = [(n, s) for n, s in self.batting_card.items()
                  if s["status"] == "batting"]
        if not active:
            return "None"
        # AUTHORITATIVE-SBINN-READ / DEFER: display marker only; no SM on SB.
        # striker_path_b_read_audit.md R11 §2.1.a
        striker = self._inn.get("striker")
        parts = []
        for name, stats in active:
            marker = "*" if name == striker else ""
            r = stats["runs"] if stats["runs"] is not None else "?"
            parts.append(f"{name}{marker}({r})")
        return " ".join(parts)

    def get_current_bowler(self) -> str:
        cb = self._inn.get("current_bowler")
        if not cb or cb not in self.bowling_card:
            return "None"
        e = self.bowling_card[cb]
        return f"{cb} {e.get('wickets', '?')}-{e.get('runs', '?')}"

    # ------------------------------------------------------------------
    # Player-style lookups (consumed by delivery classifier to derive
    # frame-of-reference for `line`, `shot_side`, `bowling_angle`).
    # Styles come from eyes/player_enrichment.py (2-pass LLM) and are
    # stamped onto each card entry when the innings is initialised.
    # ------------------------------------------------------------------

    def _batting_handed_from_style(self, style: str | None) -> str:
        s = (style or "").strip().upper()
        if s == "RHB":
            return "right"
        if s == "LHB":
            return "left"
        return "unknown"

    def _bowling_arm_from_style(self, style: str | None) -> str:
        s = (style or "").strip().lower()
        if not s or s in ("unknown", "none"):
            return "unknown"
        if s.startswith("right-arm") or "right arm" in s:
            return "right"
        if (s.startswith("left-arm")
                or "left arm" in s
                or "slow left-arm" in s
                or "left-arm wrist" in s):
            return "left"
        return "unknown"

    def get_current_batsman_handed(self) -> str:
        """Return the striker's batting handedness ('left'/'right'/
        'unknown') resolved pre-match from the squad enrichment pass."""
        if not self._inn:
            return "unknown"
        # AUTHORITATIVE-SBINN-READ / DEFER: handedness path; same constraint as R11.
        # striker_path_b_read_audit.md R12 §2.1.a
        striker = self._inn.get("striker")
        if not striker:
            return "unknown"
        card = self.batting_card.get(striker) or {}
        style = card.get("batting_style")
        if style in (None, "unknown"):
            style = (self._player_styles.get(striker) or {}).get(
                "batting_style")
        return self._batting_handed_from_style(style)

    def get_current_bowling_arm(self) -> str:
        """Return the current bowler's arm ('left'/'right'/'unknown')
        resolved pre-match from the squad enrichment pass."""
        if not self._inn:
            return "unknown"
        bowler = self._inn.get("current_bowler")
        if not bowler:
            return "unknown"
        card = self.bowling_card.get(bowler) or {}
        style = card.get("bowling_style")
        if style in (None, "unknown", "None"):
            style = (self._player_styles.get(bowler) or {}).get(
                "bowling_style")
        return self._bowling_arm_from_style(style)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _log(self, category: str, field: str, old, new, frame: int):
        entry = {"cat": category, "field": field, "old": old,
                 "new": new, "frame": frame, "time": time.time()}
        self._update_history.append(entry)
        if len(self._update_history) > 200:
            self._update_history = self._update_history[-100:]
        log.info(f"{field}: {old} -> {new} [F{frame}]")

    def get_update_history(self, n: int = 10) -> list[dict]:
        return self._update_history[-n:]
