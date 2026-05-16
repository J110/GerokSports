"""ThisOverManager — single source of truth for ball-by-ball this-over data.

Local ball events are PRIMARY. Broadcast override only fills gaps.

Over transitions are a TWO-STAGE process:
  1. The closing ball of an over (or an overs integer increment) marks
     the over as "completed" — but the display KEEPS showing it.
  2. The next over's display only resets when one of the following
     happens: a new ball event arrives (real first ball of the next
     over), the broadcast publishes a new over with the first ball
     filled, or a time-based fallback elapses (~12s — enough for the
     next bowler to walk to their mark).

This avoids two bugs:
  (a) the "leaked closing ball" issue — clearing immediately at the
      integer boundary then having a stale broadcast override
      repopulate `this_over` with the previous over's tokens
      ("4 . _ _ _ _" appearing as ball 1 of the new over).
  (b) UX whiplash where the just-completed over disappears before
      the user has a chance to read it.
"""
from __future__ import annotations

import time

from eyes.cricket_logger import CricketLogger

log = CricketLogger("OVER")

# Hold completed over visible for this long if no new ball/over is
# observed. Tunes the gap between overs (between-over breaks in T20
# are ~40-60s, but new bowler's first delivery usually lands within
# 30s; 12s is enough to read the closing ball cleanly while still
# guaranteeing the display catches up before ball 2 of the next over).
COMPLETED_OVER_HOLD_S = 3.0

# Cricket invariant: a single over cannot exceed 6 legal deliveries
# plus extras (wides + no-balls). Realistically extras-per-over caps at
# ~3 even on bad days; anything beyond 9 tokens is the broadcast's
# multi-over recap ribbon (which IPL/PL graphics frequently flash —
# showing the LAST 3 OVERS as one wide strip during between-overs
# breaks). If Scout reads that strip and feeds it to us as
# "this_over_broadcast", we must reject it: we cannot tell which 6
# of the 18 tokens belong to the current over.
#
# Tokens that originated from real, observed ball events
# (`on_ball_event`) are NEVER subject to this cap — they are ground
# truth. The cap only governs broadcast-sourced (vision-derived)
# wholesale acceptance.
MAX_THIS_OVER_LEN = 9

# Hard upper bound on observed (`on_ball_event`-sourced) tokens in a
# single over. If we ever exceed this with real events, it means
# `check_over_change` failed to fire at the over boundary (e.g. Scout
# briefly misread overs to a wrong value, or the broadcast strip
# refresh lagged). Past this point we refuse to extend the list — the
# UI is better served by a stable too-short over than an ever-growing
# multi-over blob.
MAX_OBSERVED_THIS_OVER_LEN = 12

# Bug (2026-04-20): the last ball of the over was often missing from
# `this_over`. Root cause: `_inn.overs` can advance to "X+1.0" via a
# direct/SM write path in the same frame where `_tracker.overs` is
# still at "X.5", so the BallEventDetector (which reads from the
# tracker) doesn't fire the closing-ball event. Then
# `check_over_change("X+1.0")` archives `this_over` with only 5
# observed legal balls, the 6-token state never materialises, and
# the hold-window expires with the 5-ball ribbon being the last
# state the UI ever sees.
#
# Fix: when `check_over_change` is asked to roll over while
# `this_over` has fewer than 6 legal balls, defer the rollover for
# up to ROLLOVER_MAX_DEFER_FRAMES frames. In the deferred frames
# the tracker usually catches up, BallEventDetector fires the
# closing ball, and on_ball_event appends it (growing the ribbon
# to 6 legal). The next check_over_change call then archives
# cleanly. If the detector still hasn't fired after the grace
# window, archive with whatever we have (current behaviour) — the
# UI is better served by eventual progress than an infinite hold.
ROLLOVER_MAX_DEFER_FRAMES = 2


class ThisOverManager:

    def __init__(self):
        self.this_over: list[str] = []
        self.this_over_sources: list[str] = []  # "obs" or "bcast" per ball
        # Pending-slot tracking (no-MULTI_BALL B1.2b). Maps slot index
        # → metadata for "?" placeholders awaiting attribution drain
        # by SM's pending-ball queue (B1.3). See no_multiball_design.md.
        self._pending_slots: dict[int, dict] = {}
        # Back-reference to ScoreManager for the slot-binding callback
        # (B1.2c). Set via attach_score_manager() once both managers
        # are constructed (test_pipeline.py wires this).
        self._score_manager = None
        self.over_history: dict[int, dict] = {}
        self._last_over_int: int | None = None
        self._over_start_score: int | None = None
        self._last_ball_event: dict | None = None
        # Pending-clear bookkeeping (see module docstring).
        # When set, `this_over` is the JUST-COMPLETED over and we are
        # waiting for the new over to actually start before resetting.
        self._pending_clear: bool = False
        self._pending_clear_at: float | None = None
        self._pending_clear_over_int: int | None = None
        # Bowler that bowled the held over. Used to flush the held
        # over the moment the broadcast confirms a different bowler
        # is now bowling — cricket forbids consecutive overs by the
        # same bowler, so a confirmed-different bowler is a definitive
        # "the new over has started" signal.
        self._held_over_bowler: str | None = None
        # SCORE-GATED MUTATION GUARD. `this_over` is the on-screen
        # ball ribbon and the user's hard rule is "linked to score
        # alone". A new circle (legal ball, wide, no-ball, wicket)
        # can ONLY appear after the team score advances OR the team
        # overs advance — both are score-state changes the BallEvent
        # detector picks up. The broadcast strip ("Wd Wd 1 .") flips
        # every frame as the LLM re-reads it and historically was
        # allowed to mutate this_over on its own; that produced the
        # "flicker to 1 then back to Wd" the user keeps seeing. Track
        # the score at which the last mutation happened and refuse
        # broadcast-driven writes until score moves again.
        self._last_mutation_score: int | None = None
        self._last_mutation_overs: str | None = None
        # Bug #12: cache the last bowler we observed bowling THIS over.
        # `current_bowler` from the broadcast strip is frequently None
        # for 1-3 frames around an over boundary (the strip clears
        # while the new bowler walks up). Without a cache, the over
        # archive locks in `bowler=None` permanently.
        self._current_over_bowler: str | None = None
        # Defer counter for the short-over rollover guard (see
        # ROLLOVER_MAX_DEFER_FRAMES docstring). Reset to 0 whenever we
        # actually archive an over so each rollover gets a fresh budget.
        self._rollover_defer_count: int = 0

    def reset(self) -> None:
        """Wipe all state for a fresh innings (Bug #14).

        Without this, over_history from innings 1 leaks into the
        Recent Overs panel of innings 2, and `_last_over_int`
        retained from innings 1 (e.g. 19) blocks check_over_change
        from firing for innings 2's overs (0..N) since they appear
        to go backwards.
        """
        self.this_over = []
        self.this_over_sources = []
        self.over_history = {}
        self._last_over_int = None
        self._over_start_score = None
        self._last_ball_event = None
        self._pending_clear = False
        self._pending_clear_at = None
        self._pending_clear_over_int = None
        self._current_over_bowler = None
        self._held_over_bowler = None
        self._rollover_defer_count = 0
        log.info("[OVER] Manager reset for new innings")

    def resync_to_over(self, overs: str | float | None,
                       reason: str = "recovery") -> None:
        """Clear stale current-over state and align cursor to team overs."""
        if overs is None:
            return
        try:
            over_int = int(float(overs))
        except (TypeError, ValueError):
            return
        self.this_over = []
        self.this_over_sources = []
        self._last_over_int = over_int
        self._over_start_score = None
        self._last_ball_event = None
        self._pending_clear = False
        self._pending_clear_at = None
        self._pending_clear_over_int = None
        self._current_over_bowler = None
        self._held_over_bowler = None
        self._rollover_defer_count = 0
        log.info(
            f"[OVER-RESYNC] Cursor aligned to over {over_int} "
            f"from team_overs={overs!r} ({reason}); cleared current tokens")

    def fill_strip_coverage_gap(
            self, prev_overs: str | float | None,
            new_overs: str | float | None,
            old_score: int | None,
            new_score: int | None,
            frame_count: int = 0,
            *,
            frame_classified_as_graphic: bool = False) -> None:
        """P10: infer missing this_over tokens after broadcast resumption.

        2026-05-13 (bug #5 root): early-return when the caller flags
        this frame as graphic (strategic timeout, H2H card, preview).
        Otherwise the team-overs jump heuristic appends '?' tokens
        for a non-existent ball-event gap.
        """
        if frame_classified_as_graphic:
            return
        if new_overs is None:
            return
        try:
            no = float(str(new_overs).split("/")[0])
        except (TypeError, ValueError):
            return
        frac = round((no - int(no)) * 10)
        if frac <= 0 or frac > 6:
            return
        cur_len = len(self.this_over)
        pad = frac - cur_len
        if pad <= 0:
            return
        delta = (new_score or 0) - (old_score or 0)
        for i in range(pad):
            last = (i == pad - 1)
            if last and 0 < delta <= 6:
                self.this_over.append(str(delta))
                self.this_over_sources.append("gap_infer_score")
            else:
                self.this_over.append("?")
                self.this_over_sources.append("gap_infer")
        log.info(
            f"[TIMEOUT-GAP-INFER] frame={frame_count} "
            f"prev_overs={prev_overs!r} new_overs={new_overs!r} "
            f"score {old_score}→{new_score} +{pad} inferred tokens "
            f"→ {self.this_over}")

    def _force_rollover(self, expected: int, observed: int,
                        reason: str = "forced") -> None:
        """Synchronous archive + reset, bypassing the _pending_clear
        deferral.  Used by on_ball_event when team_overs has crossed
        past the over we're currently filling but check_over_change
        deferred (waiting for missing balls).  Mirrors the archival
        path in check_over_change at line 1118.

        2026-05-13 (anomaly 1 — late-rollover token bleed): without
        this gate, ball events from the new over get appended to the
        OLD over's this_over and end up archived under the wrong
        over_history key.
        """
        if self._last_over_int is None:
            return
        archive_payload = {
            "balls": self.this_over.copy(),
            "bowler": self._current_over_bowler,
            "runs": sum(int(x) for x in self.this_over
                        if isinstance(x, str) and x.isdigit()),
            "wickets": sum(1 for x in self.this_over if x == "W"),
        }
        try:
            from trace_emitter import get_recorder as _ovget
            _ovrec = _ovget()
        except Exception:
            _ovrec = None
        if self._last_over_int not in self.over_history:
            self.over_history[self._last_over_int] = archive_payload
            log.info(
                f"[OVER-ROLLOVER-FORCED] Over "
                f"{self._last_over_int}: {self.this_over} -> "
                f"archived (reason={reason}, expected={expected}, "
                f"observed={observed}, "
                f"this_over_len={len(self.this_over)})")
            if _ovrec is not None:
                try:
                    _ovrec.record(
                        tag="OVER-ARCHIVE-WRITE",
                        over_n=int(self._last_over_int),
                        tokens=list(self.this_over),
                        token_count=len(self.this_over),
                        source="force_rollover")
                    if len(self.this_over) != 6:
                        _ovrec.record(
                            tag="OVER-ARCHIVE-INVALID-TOKEN-COUNT",
                            over_n=int(self._last_over_int),
                            token_count=len(self.this_over),
                            tokens=list(self.this_over))
                except Exception:
                    pass
        else:
            log.info(
                f"[OVER-ROLLOVER-FORCED] Over "
                f"{self._last_over_int} already archived; "
                f"resetting this_over (reason={reason}, "
                f"expected={expected}, observed={observed})")
            if _ovrec is not None:
                try:
                    _ovrec.record(
                        tag="OVER-ARCHIVE-DOUBLE-WRITE",
                        over_n=int(self._last_over_int),
                        existing_tokens=list(
                            (self.over_history[self._last_over_int] or {})
                            .get("balls", [])),
                        attempted_tokens=list(self.this_over),
                        source="force_rollover")
                except Exception:
                    pass
        self.this_over = []
        self.this_over_sources = []
        self._pending_clear = False
        self._pending_clear_at = None
        self._pending_clear_over_int = None
        self._held_over_bowler = None
        self._current_over_bowler = None
        self._over_start_score = None
        self._last_over_int = self._last_over_int + 1
        self._last_ball_event = None
        self._rollover_defer_count = 0

    def _consume_pending_clear(self, reason: str) -> None:
        """Reset display to start of the new over.

        Called when there's evidence the next over has actually
        started: a new ball event, a broadcast showing fresh tokens,
        a fractional overs advance, or the hold-window timeout.
        """
        if not self._pending_clear:
            return
        log.info(
            f"Completed over flushed ({reason}): "
            f"{self.this_over} → []")
        self.this_over = []
        self.this_over_sources = []
        self._pending_clear = False
        self._pending_clear_at = None
        self._pending_clear_over_int = None
        self._held_over_bowler = None

    def on_ball_event(self, event: dict | None,
                      score: int | None = None) -> None:
        if event is None:
            return
        # B1.2e diagnostic: capture pre-state for THIS-OVER-APPEND trace.
        _b1_pre_len = len(self.this_over)
        # Score-gated mutation marker: every ball event was triggered
        # by a score (or overs) state change upstream, so any append
        # below MUST advance `_last_mutation_score` to the new score.
        # That unlocks the next broadcast-driven gap-fill while the
        # CURRENT score still locks out broadcast flicker.
        if score is not None:
            try:
                self._last_mutation_score = int(score)
            except (ValueError, TypeError):
                pass
        # Process event (body unchanged below); emit per-append trace at end.
        try:
            self._on_ball_event_inner(event, score)
        finally:
            if len(self.this_over) > _b1_pre_len:
                try:
                    from trace_emitter import get_recorder as _toget
                    _torec = _toget()
                    for _i in range(_b1_pre_len, len(self.this_over)):
                        _src = (self.this_over_sources[_i]
                                if _i < len(self.this_over_sources)
                                else "unknown")
                        _torec.record(
                            tag="THIS-OVER-APPEND",
                            slot_idx=_i,
                            token=str(self.this_over[_i]),
                            source=str(_src),
                            event_type=str(event.get("type")))
                except Exception:
                    pass

    def _on_ball_event_inner(self, event: dict | None,
                             score: int | None = None) -> None:
        if event is None:
            return

        # 2026-05-13 (anomaly 1 — late-rollover token bleed):
        # check_over_change can defer the rollover (SHORT-OVER guard
        # waits for the closing-ball event to land).  During that
        # defer, the broadcast strip can advance team_overs into the
        # NEW over.  Without this gate, ball events from the new over
        # get appended to the OLD over's self.this_over and the
        # eventual archive misattributes them.
        #
        # Trigger: event's `over` field has Y > 0 in "X.Y" AND
        # int(event.over) + 1 > self._last_over_int + 1 (i.e., we're
        # inside a later over than expected).  Suppress the gate at
        # X.0 boundary because the held-over routing below covers
        # late balls of the just-archived over.
        _state_var_for_commit_msg = "self._last_over_int"  # noqa: F841
        ev_over_for_gate = (
            event.get("over") if isinstance(event, dict) else None)
        if (ev_over_for_gate is not None
                and self._last_over_int is not None):
            try:
                _ev_v_gate = float(ev_over_for_gate)
                _ev_int_gate = int(_ev_v_gate)
                _ev_frac_gate = round((_ev_v_gate % 1) * 10)
                if _ev_frac_gate > 0:
                    _observed = _ev_int_gate + 1
                    _expected = self._last_over_int + 1
                    if _observed > _expected:
                        self._force_rollover(
                            expected=_expected,
                            observed=_observed,
                            reason="ball_event_past_boundary")
            except (ValueError, TypeError):
                pass

        # Determine which over this event LOGICALLY belongs to.
        #
        # Per cricket convention the team-overs counter ticks to "X.0"
        # only AFTER the 6th legal ball of over X-1. So an event whose
        # `over` field reads "6.0" was actually bowled DURING over 5
        # (it IS the 6th ball of over 5). An event reading "6.1" is
        # the 1st ball of over 6.
        #
        # This matters for the held-over flush. BallEventDetector
        # operates on per-frame deltas; it can produce a queued legal
        # event one frame late (the wide/legal-decomposition path
        # appends `legal_event` to `_event_queue` and emits the EXTRA
        # first). When that queued event finally fires, the team-overs
        # reading at queue-emit time is whatever the latest frame
        # carried — which is "6.0" or even "6.1" if the broadcast was
        # ahead. Without the fractional-aware mapping below the held
        # completed over (5) gets flushed and the late ball is shown
        # as ball 1 of over 6 — exactly the visible "last ball bleeds
        # into next over" bug.
        ev_over_logical: int | None = None
        ev_over_str = event.get("over") if isinstance(event, dict) else None
        if ev_over_str is not None:
            try:
                _v = float(ev_over_str)
                _v_int = int(_v)
                _v_frac = round((_v % 1) * 10)
                if _v_frac == 0 and _v_int > 0:
                    # "X.0" → 6th ball of over X-1
                    ev_over_logical = _v_int - 1
                else:
                    ev_over_logical = _v_int
            except (ValueError, TypeError):
                ev_over_logical = None

        # Late ball event for the just-completed (held) over.
        # Append to the held this_over and update the held over's
        # archive. Do NOT flush.
        #
        # Two ways an event can be identified as "late":
        #
        #   (a) Its `over` field decodes to the held over (e.g. "6.0"
        #       → over 5).  Reliable when the broadcast strip stayed
        #       at "X.0" while the score updated.
        #
        #   (b) Cricket-rules fallback: if the held over does not yet
        #       contain 6 legal balls, the next ball MUST belong to it
        #       — the new over cannot start until the old bowler has
        #       bowled 6 legal deliveries.  This catches the case
        #       where the team-overs string already advanced to "X.1"
        #       by the time the late delta materialised, so the
        #       event's own `over` field reads "X.1" and (a) misses.
        #       Without this fallback the late ball gets attributed
        #       to ball-1 of the new over and bleeds into it.
        if self._pending_clear:
            held_int = self._pending_clear_over_int
            held_legal = 0
            archived = (self.over_history.get(held_int) if held_int is not None
                        else None)
            if archived and isinstance(archived.get("balls"), list):
                held_legal = sum(
                    1 for x in archived["balls"]
                    if str(x).lower() not in ("wd", "nb")
                    and not str(x).lower().startswith("wd")
                    and not str(x).lower().startswith("nb"))
            late_by_overs = (held_int is not None
                             and ev_over_logical is not None
                             and ev_over_logical == held_int)
            late_by_count = (held_int is not None and held_legal < 6)
            if late_by_overs or late_by_count:
                if late_by_count and not late_by_overs:
                    log.info(
                        f"Late ball routed to held over {held_int} by "
                        f"cricket-rules fallback: held has {held_legal} "
                        f"legal balls (< 6), event over="
                        f"{event.get('over') if isinstance(event, dict) else '?'}")
                self._append_to_held_and_rearchive(event)
                return

        # First real ball of the new over → flush the held completed
        # over now (don't wait for the timeout). Synthesised boundary
        # balls injected by check_over_change set
        # _last_ball_event but they're attributed to the OLD over
        # (over=f"{old_int}.6"); they don't belong to the new over,
        # so don't flush on those.
        if self._pending_clear:
            self._consume_pending_clear("ball event in new over")

        # Defence-in-depth cap on observed extensions. If we ever try
        # to append a 13th token to this_over via real ball events,
        # something upstream is broken — `check_over_change` should
        # have fired and reset us at the over boundary. Refuse the
        # append rather than letting the list grow without bound;
        # that's the visible bug ("12-circle this over").
        # DRS_WIDE replaces the last token (no length growth) — allow
        # it through so an in-flight DRS can still correct the last
        # ball. Everything else is blocked.
        _drs_replace = (isinstance(event, dict)
                        and event.get("type") == "DRS_WIDE")
        if (not _drs_replace
                and len(self.this_over) >= MAX_OBSERVED_THIS_OVER_LEN):
            log.info(
                f"on_ball_event refused: this_over already has "
                f"{len(self.this_over)} tokens "
                f"(>= MAX_OBSERVED_THIS_OVER_LEN). "
                f"Likely missed over rollover — event dropped: "
                f"{event}")
            return

        # Bug #12: capture the bowler attached to this ball event. The
        # bowler who bowled this delivery is, by definition, the bowler
        # of the current over — which is exactly what over_history
        # needs at archive time. Trust this over the live-strip
        # `current_bowler` (which can flip to the next bowler as soon
        # as the broadcast graphic refreshes).
        #
        # FIRST-WRITE-WINS for the over bowler: once we've recorded a
        # non-None bowler for this over, never overwrite it from a
        # later event.  Critical at the over boundary — the broadcast
        # frequently flips its bowler-strip to the NEXT over's bowler
        # in the very same frame that the last ball of the current
        # over lands.  Without first-write-wins the late ball event
        # carries the wrong bowler (next-over-bowler) and that's what
        # gets archived for the just-completed over.  Cricket never
        # permits the same bowler to bowl consecutive overs, so once
        # we've seen a bowler for an over, that's the one.  The
        # next-over rollover (`check_over_change`) clears the cache.
        _ev_bowler = event.get("bowler") if isinstance(event, dict) else None
        if _ev_bowler and not self._current_over_bowler:
            self._current_over_bowler = _ev_bowler

        self._append_event_token(event)

    def _append_to_held_and_rearchive(self, event: dict) -> None:
        """Append a late ball event to the just-completed (held) over.

        Triggered when `on_ball_event` receives an event whose logical
        over matches `_pending_clear_over_int`. The event was bowled
        DURING the held over but reached us after the over rollover
        (typical cause: BallEventDetector's wide-decomposition queues
        the legal delivery for the next frame). We must not flush the
        hold — the token belongs at the END of the held this_over,
        not at the start of the new over.
        """
        held_int = self._pending_clear_over_int
        # Defence-in-depth: at most 12 tokens for a single over even
        # when extras pile up.
        if len(self.this_over) >= MAX_OBSERVED_THIS_OVER_LEN:
            log.info(
                f"Late ball for held over {held_int} REFUSED: "
                f"this_over already has {len(self.this_over)} tokens "
                f"(>= MAX_OBSERVED_THIS_OVER_LEN). Dropped: {event}")
            return

        before = list(self.this_over)
        self._append_event_token(event)

        # The held over was already archived to over_history at the
        # boundary. The late append changes its contents — we must
        # rewrite that one entry. This is the ONLY sanctioned
        # in-place mutation of over_history (first-write-wins still
        # applies to every other path); the over has not been
        # finalised on the user-facing display yet (the hold window
        # is still open).
        if held_int is not None:
            existing = self.over_history.get(held_int)
            archive_payload = {
                "balls": self.this_over.copy(),
                "bowler": (existing.get("bowler") if existing
                           else self._current_over_bowler),
                "runs": sum(int(x) for x in self.this_over
                            if isinstance(x, str) and x.isdigit()),
                "wickets": sum(1 for x in self.this_over if x == "W"),
            }
            _existing_balls = list((existing or {}).get("balls", []))
            self.over_history[held_int] = archive_payload
            log.info(
                f"Late ball appended to held over {held_int}: "
                f"{before} → {self.this_over} (event over="
                f"{event.get('over') if isinstance(event, dict) else '?'})")
            try:
                from trace_emitter import get_recorder as _hovget
                _hovrec = _hovget()
                _hovrec.record(
                    tag="OVER-ARCHIVE-WRITE",
                    over_n=int(held_int),
                    tokens=list(self.this_over),
                    token_count=len(self.this_over),
                    source="held_over_late_append",
                    sanctioned_rewrite=bool(existing))
                if existing and _existing_balls != list(self.this_over):
                    _hovrec.record(
                        tag="OVER-ARCHIVE-DOUBLE-WRITE",
                        over_n=int(held_int),
                        existing_tokens=_existing_balls,
                        attempted_tokens=list(self.this_over),
                        source="held_over_late_append_sanctioned")
                if len(self.this_over) != 6:
                    _hovrec.record(
                        tag="OVER-ARCHIVE-INVALID-TOKEN-COUNT",
                        over_n=int(held_int),
                        token_count=len(self.this_over),
                        tokens=list(self.this_over))
            except Exception:
                pass
        else:
            log.info(
                f"Late ball appended to held over (no over_int): "
                f"{before} → {self.this_over}")

    def _append_event_token(self, event: dict) -> None:
        """Append the token for `event` to `self.this_over`.

        Extracted from `on_ball_event` so the late-event-for-held-over
        path can reuse the exact same per-event token logic without
        re-running the flush/cap guards (those are decided by the
        caller).
        """
        # NOTE: type-specific dispatches MUST come before the generic
        # `event.get("certain")` branch — an EXTRA event also carries
        # `certain: True` and would otherwise be appended as a digit
        # (the run count) instead of the "Wd"/"Nb" token. Same risk
        # applies to MULTI_BALL and DRS_* events; keep them above.
        _ev_type = event.get("type")
        if _ev_type == "WICKET_LATE":
            # Broadcast wickets reading lagged the overs reading by
            # 1 frame: we already appended a DOT/run for the wicket
            # ball — replace it with 'W' instead of inserting a
            # phantom new ball. Handled BEFORE the generic certain
            # branch so the existing DOT/N token is upgraded
            # in place rather than a second 'W' appended.
            if self.this_over:
                removed = self.this_over.pop()
                if self.this_over_sources:
                    self.this_over_sources.pop()
                log.info(f"Late wicket: replaced last token "
                         f"'{removed}' → 'W'")
            self.this_over.append("W")
            self.this_over_sources.append("obs")
        elif _ev_type == "EXTRA":
            extra_type = event.get("extra_type", "wide_or_noball")
            if "no_ball" in extra_type:
                token = "Nb"
            else:
                token = "Wd"
            runs = event.get("runs", 1)
            if runs > 1:
                token = f"{token}+{runs - 1}"
            self.this_over.append(token)
            self.this_over_sources.append("obs")
            log.info(f"Extra detected — added '{token}' ({extra_type})")
        elif _ev_type == "DRS_WIDE":
            if self.this_over:
                removed = self.this_over.pop()
                if self.this_over_sources:
                    self.this_over_sources.pop()
                log.info(f"DRS wide: replaced '{removed}' → 'wd'")
            self.this_over.append("wd")
            self.this_over_sources.append("obs")
        elif _ev_type == "DRS_NOT_OUT":
            log.info("DRS not-out — no this-over change")
        elif _ev_type == "ABSORBED_LEGAL":
            slot_idx = len(self.this_over)
            if event.get("gap_finalize_wicket"):
                self.this_over.append("W")
                self.this_over_sources.append("obs")
            else:
                self.this_over.append("?")
                self.this_over_sources.append("obs_pending")
                self._pending_slots[slot_idx] = {
                    "source": "absorbed_legal",
                    "ball_index": event.get("ball_index"),
                }
                # B1.2c slot-binding callback: link this "?" slot back
                # to the corresponding SM PendingBall. The producer
                # (SM._decompose_multi_ball OR test_pipeline.py for BED
                # events) enqueued a PendingBall with slot_idx=None;
                # we bind it to this slot_idx in FIFO order.
                if self._score_manager is not None:
                    self._score_manager.bind_pending_slot(slot_idx)
        elif event.get("certain"):
            t = _ev_type
            if t == "WICKET":
                self.this_over.append("W")
            elif t == "DOT":
                self.this_over.append(".")
            elif t == "FOUR":
                self.this_over.append("4")
            elif t == "SIX":
                self.this_over.append("6")
            else:
                r = event.get("runs", 0)
                if event.get("extras_type") == "leg_bye_or_bye":
                    self.this_over.append(f"{r}lb")
                else:
                    self.this_over.append(str(r) if r > 0 else ".")
            self.this_over_sources.append("obs")
        elif event.get("type") == "MULTI_BALL":
            # No-MULTI_BALL architecture (B1.2b): append N "?"
            # placeholders instead of synthesizing tokens via
            # infer_gap_tokens. Pending-queue drain (B1.3) rewrites
            # each "?" with the observed runs/wickets token once
            # bowler+striker attribution resolves. See
            # files/docs/investigations/no_multiball_design.md.
            missed = event.get("balls_missed") or event.get("balls_skipped") or 0
            total_r = event.get("total_runs")
            # Cap at 6 — we can only have 6 legal deliveries in the
            # current over.
            capped = min(missed, 6 - len(self.this_over))
            capped = max(capped, 0)
            for _ in range(capped):
                slot_idx = len(self.this_over)
                self.this_over.append("?")
                self.this_over_sources.append("multi_ball_pending")
                self._pending_slots[slot_idx] = {
                    "source": "multi_ball",
                }
            if capped > 0:
                log.info(
                    f"Missed {missed} balls (+{total_r} runs) — "
                    f"appended {capped} '?' placeholders (pending "
                    f"attribution drain, was: synthesized tokens)")
            else:
                log.info(
                    f"Missed {missed} balls (+{total_r} runs) — "
                    f"no room in current over for placeholders")

    def attach_score_manager(self, score_manager) -> None:
        """Wire the back-reference for the slot-binding callback (B1.2c).

        Once both managers are constructed, the pipeline calls this so
        the ABSORBED_LEGAL handler can call sm.bind_pending_slot(slot_idx)
        immediately after appending a "?" placeholder.
        """
        self._score_manager = score_manager

    def rewrite_token(self, slot_idx: int, token: str) -> None:
        """Rewrite a pending '?' slot to a real token (B1.2b).

        Called by ScoreManager's pending-ball-queue drain (B1.3) after
        bowler+striker attribution resolves for a previously-deferred
        ball. Pops the entry from `_pending_slots` so a second drain
        attempt is a no-op.
        """
        if not (0 <= slot_idx < len(self.this_over)):
            log.warn(
                f"[rewrite_token] slot_idx={slot_idx} out of range "
                f"(this_over len={len(self.this_over)})")
            return
        old = self.this_over[slot_idx]
        self.this_over[slot_idx] = token
        if slot_idx < len(self.this_over_sources):
            self.this_over_sources[slot_idx] = "obs"
        self._pending_slots.pop(slot_idx, None)
        log.info(
            f"[rewrite_token] slot {slot_idx}: '{old}' → '{token}'")

    def pop_last_extra(self, reason: str = "") -> bool:
        """Remove the trailing token if it's an EXTRA (Wd/Nb/+N).

        Defense-in-depth for retracted phantom extras: the EXTRA-IMMEDIATE
        path can fire on a single misread frame (broadcast WD strip
        flickers, or score-digit OCR jitters +1).  When a downstream
        consumer (the unsupported-score-spike guard, or a confirmed
        score regression in the next frame) determines the EXTRA was
        not real, this method peels it off `this_over` so the UI's
        pill doesn't carry a phantom Wd/Nb token until the over rolls.

        Only pops EXTRA tokens (Wd, Nb, Wd+N, Nb+N).  Refuses to pop
        legal-ball tokens ('.', '1'-'6', 'W') because those are not
        the bug class we're guarding against and a wrongful pop here
        would silently delete a real delivery.

        Returns True if a pop happened.
        """
        if not self.this_over:
            return False
        last = self.this_over[-1]
        is_extra = (
            isinstance(last, str)
            and (last.startswith("Wd") or last.startswith("Nb")
                 or last.startswith("wd") or last.startswith("nb")))
        if not is_extra:
            log.info(
                f"[ROLLBACK] refused — last token '{last}' is not an "
                f"EXTRA (only Wd/Nb may be rolled back). reason={reason}")
            return False
        removed = self.this_over.pop()
        if self.this_over_sources:
            self.this_over_sources.pop()
        log.info(
            f"[ROLLBACK] popped extra token '{removed}' from this_over "
            f"(now={self.this_over}). reason={reason}")
        return True

    def on_broadcast_override(self, data: list | None,
                              score: int | None = None) -> None:
        """Use broadcast data to fill gaps — never overwrite observed.

        Immutability principle: confirmed history is permanent. The
        broadcast is permitted to FILL `?` placeholders and (only via
        an explicit DRS event from `on_ball_event`) to overwrite the
        LAST token. It cannot:
          * Overwrite any non-`?` token that isn't the last
          * Extend `this_over` beyond its current length
          * Re-seed a non-empty `this_over`

        SCORE-GATED MUTATION (the user's hard rule): the broadcast
        strip flips every frame as the LLM re-reads it; that's the
        flicker root cause. `this_over` mutates ONLY when score
        advances. Until score moves past `_last_mutation_score`, all
        broadcast writes are refused — even gap-fills — so the strip
        cannot mutate the displayed circles between balls.

        Cold-start (no prior mutation recorded) is exempt so the
        initial join still gets a sensible mid-over fill.
        """
        if not data:
            return

        if (self._last_mutation_score is not None
                and score is not None
                and int(score) <= int(self._last_mutation_score)):
            log.info(
                f"Broadcast {data} ignored — score "
                f"{score} has not advanced past last mutation "
                f"({self._last_mutation_score}); this_over is "
                f"score-gated.")
            return

        broadcast = self._merge_broadcast(
            [str(x).lower().strip() for x in data])

        # Token-alphabet validation.  The broadcast `THIS OVER:`
        # field is occasionally polluted by adjacent strip
        # overlays (most often the per-ball-speed track that
        # sits directly above the run-track on production
        # graphics).  Scout reads both as text and OCR doesn't
        # reliably distinguish `THIS OVER:` from `SPEED:`.
        # Without this gate the pipeline ingests speed numbers
        # as run-tokens, archiving nonsense overs like
        # `[139, 148, 143, 147, 145, 140] = 862 runs`
        # (RR-vs-SRH 2026-04-25 F2461; class active
        # intermittently since 2026-04-16).  A single illegal
        # token is a strong signal that the whole strip was
        # misread, so reject the entire list rather than try
        # to filter — partial acceptance leaves us with a
        # silently truncated over and the same UX bug surface.
        _illegal = [t for t in broadcast
                    if not self._is_legal_run_token(t)]
        if _illegal:
            log.warn(
                f"[TOKEN-VALIDATE] Rejecting broadcast tokens "
                f"{broadcast} — illegal token(s) {_illegal} "
                f"outside cricket-scorecard alphabet (likely "
                f"speed-track misread or adjacent-strip OCR "
                f"pollution)")
            return

        # Multi-over recap rejection. The broadcast frequently shows
        # the LAST 3 OVERS as one wide ribbon during between-overs
        # breaks ("18-token strip"). Scout reads that as "this_over"
        # and we cannot tell which 6 belong to the current over —
        # reject wholesale. on_broadcast_override is only allowed to
        # touch the current over.
        if len(broadcast) > MAX_THIS_OVER_LEN:
            log.info(
                f"Broadcast {broadcast} ({len(broadcast)} tokens) "
                f"exceeds MAX_THIS_OVER_LEN={MAX_THIS_OVER_LEN} — "
                f"rejected as multi-over recap strip")
            return

        # While holding a just-completed over, ignore broadcast updates
        # that match the held over (Scout is still reading the
        # previous-over strip during the between-overs gap). Only
        # accept a broadcast that's clearly the NEW over (much
        # shorter — 0 or 1 token) which signals the next over has
        # started on the broadcast.
        if self._pending_clear:
            held = [x for x in self.this_over
                    if str(x).lower() not in ("wd", "nb")]
            if len(broadcast) >= len(held) - 1:
                # Same-length-or-larger broadcast while holding =>
                # almost certainly the stale previous-over strip.
                log.info(
                    f"Broadcast {broadcast} ignored "
                    f"(holding completed over {self.this_over})")
                return
            # Broadcast is shorter than the held over — new over has
            # started on the strip. Flush and accept.
            self._consume_pending_clear("broadcast shows new over")

        # Empty local → accept broadcast wholesale, BUT only on cold
        # start (we're joining mid-innings and have no observations
        # of our own). Once we're warm (_last_over_int set), local
        # being empty means we just transitioned overs and are
        # waiting for the next ball event — accepting a broadcast
        # full of '?' tokens (Scout misread) would freeze phantom
        # placeholders into the new over. Filter '?' tokens out of
        # the wholesale accept to keep observations clean.
        if not self.this_over:
            cold = self._last_over_int is None
            if cold:
                _bcast_before = list(self.this_over)
                self.this_over = broadcast
                self.this_over_sources = ["bcast"] * len(broadcast)
                log.info(
                    f"Broadcast fill (cold-start, empty local): "
                    f"{self.this_over}")
                try:
                    from trace_emitter import get_recorder as _brget
                    _brget().record(
                        tag="THIS-OVER-BROADCAST-REPLACE",
                        before=_bcast_before, after=list(self.this_over),
                        source="cold_start_empty_local")
                except Exception:
                    pass
                return
            # Warm-mode wholesale accept: only if the broadcast has
            # zero '?' tokens (otherwise wait for real ball events).
            if any(t == "?" for t in broadcast):
                log.info(
                    f"Broadcast {broadcast} has '?' tokens "
                    f"(warm-mode, empty local) — ignoring, will "
                    f"wait for ball events")
                return
            _bcast_before = list(self.this_over)
            self.this_over = broadcast
            self.this_over_sources = ["bcast"] * len(broadcast)
            log.info(
                f"Broadcast fill (warm, empty local, "
                f"clean tokens): {self.this_over}")
            try:
                from trace_emitter import get_recorder as _brget
                _brget().record(
                    tag="THIS-OVER-BROADCAST-REPLACE",
                    before=_bcast_before, after=list(self.this_over),
                    source="warm_empty_local_clean")
            except Exception:
                pass
            return

        # If broadcast is shorter but local has ? slots, still fill them
        has_gaps = any(b == "?" for b in self.this_over)
        if len(broadcast) < len(self.this_over) and not has_gaps:
            log.info(f"Broadcast {broadcast} shorter than "
                     f"local {self.this_over} (no gaps) — ignored")
            return

        # Count observed (non-?) balls in local
        obs_count = sum(1 for i, b in enumerate(self.this_over)
                        if b != "?"
                        and i < len(self.this_over_sources)
                        and self.this_over_sources[i] == "obs")

        if obs_count == 0:
            # All local is placeholder/bcast → safe to replace
            _bcast_before = list(self.this_over)
            self.this_over = broadcast
            self.this_over_sources = ["bcast"] * len(broadcast)
            log.info(f"Broadcast replaces all-placeholder local: "
                     f"{self.this_over}")
            try:
                from trace_emitter import get_recorder as _brget
                _brget().record(
                    tag="THIS-OVER-BROADCAST-REPLACE",
                    before=_bcast_before, after=list(self.this_over),
                    source="warm_all_placeholder")
            except Exception:
                pass
            return

        # Only fill ? positions within the existing range —
        # never extend local from broadcast (new balls come only
        # from on_ball_event or MULTI_BALL placeholders).
        old = self.this_over[:]
        merged = list(self.this_over)
        merged_src = list(self.this_over_sources)

        filled = 0
        for i in range(len(merged)):
            if merged[i] == "?" and i < len(broadcast):
                merged[i] = broadcast[i]
                if i < len(merged_src):
                    merged_src[i] = "bcast"
                filled += 1

        if filled > 0:
            log.info(f"Broadcast filled {filled} gaps: {old} → {merged}")
            _bcast_before = list(self.this_over)
            self.this_over = merged
            self.this_over_sources = merged_src
            try:
                from trace_emitter import get_recorder as _brget
                _brget().record(
                    tag="THIS-OVER-BROADCAST-REPLACE",
                    before=_bcast_before, after=list(self.this_over),
                    source="gap_merge",
                    gaps_filled=int(filled))
            except Exception:
                pass
        else:
            log.info(f"Broadcast {broadcast} — no gaps to fill in "
                     f"local {self.this_over}")

    def reorder_wicket_to_ball(self, ball_index_in_over: int) -> bool:
        """Move the W token in `this_over` so it occupies the
        N-th legal-ball position, where N = `ball_index_in_over`.

        Triggered from the FOW-upgrade callback: when a placeholder
        FOW entry is upgraded with a real `overs="X.Y"`, we know
        the wicket actually fell on the Y-th legal ball of over X.
        Without reordering, `this_over` token order reflects
        broadcast-detection time, which is misleading whenever the
        wickets ticker animates faster than the score ticker (the
        RR-vs-SRH 2026-04-25 inn-2 over-0 case: real chronological
        order `[., ., ., Wd, 6, W]`, observed `[., ., ., Wd, W, 6]`
        because the W graphic surfaced ~45 s before the boundary
        score caught up).

        Legal-ball position counts only deliveries that consume a
        ball: digit tokens (`.`, `0..7`), bye / leg-bye tokens
        (`Nb`, `Nlb`), and `W`.  Extras-only tokens (`Wd`, `Nb`,
        and compound forms `Wd+N` / `Nb+N`) do not advance the
        legal-ball counter.

        Returns True if a reorder happened, False otherwise (no W
        present, or W already at the correct legal-ball position).
        """
        try:
            target = int(ball_index_in_over)
        except (TypeError, ValueError):
            return False
        if target <= 0 or "W" not in self.this_over:
            return False

        def _is_pure_extra(t: str) -> bool:
            # Wides / no-balls (raw or compound) — do not consume a ball.
            return (t == "Wd" or t == "Nb"
                    or t.startswith("Wd+") or t.startswith("Nb+"))

        cur_w_idx = self.this_over.index("W")
        # Current legal-ball position of W (1-indexed: a W with
        # zero non-extra tokens before it is the 1st legal ball).
        cur_legal_pos = sum(
            1 for t in self.this_over[:cur_w_idx + 1]
            if not _is_pure_extra(t))

        if cur_legal_pos == target:
            return False  # already in the right place

        # Pop W (and matching source slot) from current position.
        self.this_over.pop(cur_w_idx)
        if cur_w_idx < len(self.this_over_sources):
            popped_src = self.this_over_sources.pop(cur_w_idx)
        else:
            popped_src = "fow_upgrade"

        # Find the smallest insertion index where exactly
        # `target - 1` legal balls precede W, so W itself becomes
        # the target-th legal ball after insertion.  Iterating
        # all candidate slots (0..len) is O(N²) on a 6-9 element
        # list — fine for this hot path.
        insert_at = len(self.this_over)
        for cand in range(len(self.this_over) + 1):
            legal_before = sum(
                1 for t in self.this_over[:cand]
                if not _is_pure_extra(t))
            if legal_before == target - 1:
                insert_at = cand
                break

        self.this_over.insert(insert_at, "W")
        if insert_at <= len(self.this_over_sources):
            self.this_over_sources.insert(insert_at, popped_src)
        else:
            self.this_over_sources.append(popped_src)

        log.info(
            f"[FOW-REORDER] W repositioned from legal-ball "
            f"{cur_legal_pos} → {target} (FOW upgrade): "
            f"this_over={self.this_over}")
        return True

    @staticmethod
    def _is_legal_run_token(t: str) -> bool:
        """Return True iff `t` belongs to the cricket-scorecard
        alphabet that `_merge_broadcast` is permitted to emit.

        This is the inverse of an OCR-misread escape: the broadcast
        `THIS OVER:` field is occasionally polluted by adjacent
        graphic strips (most often the per-ball-speed track that
        sits directly above the run-track on production overlays).
        Without alphabet validation the pipeline ingests speed
        numbers as run-tokens — see RR vs SRH 2026-04-25 F2461
        which archived `[139, 148, 143, 147, 145, 140] = 862 runs`
        for over 2.

        Legal alphabet (matches `_merge_broadcast` output):
          - "." dot ball
          - "?" placeholder (intra-pipeline; cold-start fills,
            MULTI_BALL gaps, etc.)
          - single-digit runs in 0..7 (7 covers the rare
            overthrow / wide+6 case)
          - "W" wicket, "Wd" wide, "Nb" no-ball (compound
            forms like "Wd+4" never come from `_merge_broadcast`
            — they originate in observed `on_ball_event` and
            bypass this gate, so we don't need to allow them
            here)
          - "{N}b" bye and "{N}lb" leg-bye where N is a
            single digit

        Anything else (3-digit speed values, gibberish OCR)
        triggers wholesale rejection of the broadcast list at
        the caller.
        """
        if t in (".", "?", "W", "Wd", "Nb"):
            return True
        if t.isdigit() and len(t) == 1 and 0 <= int(t) <= 7:
            return True
        # leg-byes: "{N}lb" with N a single digit
        if (t.endswith("lb") and len(t) == 3
                and t[0].isdigit() and 0 <= int(t[0]) <= 7):
            return True
        # byes: "{N}b" with N a single digit; must not be "nb"
        if (t.endswith("b") and not t.endswith("nb")
                and len(t) == 2
                and t[0].isdigit() and 0 <= int(t[0]) <= 7):
            return True
        return False

    @staticmethod
    def _merge_broadcast(tokens: list[str]) -> list[str]:
        """Normalize broadcast tokens to our display format.
        'w' alone = WICKET (W), 'wd'/'wide' = WIDE (Wd),
        'lb'/'2lb' = leg bye, 'b'/'1b' = bye."""
        result = []
        for t in tokens:
            low = t.lower()
            if low in ("wd", "wide"):
                result.append("Wd")
            elif low in ("nb", "noball"):
                result.append("Nb")
            elif low == "w":
                result.append("W")
            elif low == "lb":
                result.append("1lb")
            elif low.endswith("lb") and low[:-2].isdigit():
                result.append(low)
            elif low == "b" and len(t) == 1:
                result.append("1b")
            elif low.endswith("b") and low[:-1].isdigit() and not low.endswith("nb"):
                result.append(low)
            elif t == ".":
                result.append(".")
            elif t.isdigit():
                result.append(t)
            else:
                result.append(t)
        return result

    def check_over_change(self, overs: str | None,
                          bowler: str | None,
                          score: int | None = None) -> bool:
        if not overs:
            return False
        new_int = int(float(overs))

        # Bug #12: while still in the live over, cache any non-None
        # bowler we see. We use this cache as the archive fallback if
        # `bowler` is None at the exact frame the over rolls (very
        # common — the broadcast clears the bowling strip in the
        # inter-over gap).
        if (bowler
                and self._last_over_int is not None
                and new_int == self._last_over_int):
            self._current_over_bowler = bowler

        # BOWLER-CHANGE FLUSH. While we're holding a completed over on
        # the display, the moment a CONFIRMED-DIFFERENT bowler appears
        # the new over has unambiguously started — cricket forbids the
        # same bowler bowling consecutive overs, so a different bowler
        # name from a clean broadcast read is a fact, not a signal we
        # need to wait on. Flush the held display immediately rather
        # than waiting for the team-overs digit to advance or the
        # 3-second hold timeout to expire.
        if (self._pending_clear and bowler
                and self._held_over_bowler):
            _a = (bowler or "").strip().lower()
            _b = (self._held_over_bowler or "").strip().lower()
            # Compare last name (single token) to absorb LLM
            # firstname-vs-shortname variation (Praful Hinge ↔ Hinge).
            _a_last = _a.split()[-1] if _a else ""
            _b_last = _b.split()[-1] if _b else ""
            if _a_last and _b_last and _a_last != _b_last:
                self._consume_pending_clear(
                    f"new bowler '{bowler}' replaces "
                    f"'{self._held_over_bowler}'")

        # OVERS MISREAD ROLLBACK (issue #1). Symptom: Scout briefly
        # reads "0.1" as "1.0" (one bad frame) → check_over_change
        # archives over 0 with the partial this_over → next frame
        # team_overs corrects back to 0.1 but the archive is locked.
        # Detect: we recently archived over N (now _last_over_int
        # > new_int) and the new reading sits at the over we JUST
        # archived. Rewind: pull the archived balls back into
        # this_over, drop the bad over_history entry, restore the
        # pending-clear state.
        if (self._last_over_int is not None
                and new_int < self._last_over_int
                and (self._last_over_int - 1) in self.over_history):
            archived_int = self._last_over_int - 1
            archived = self.over_history.get(archived_int)
            if archived and new_int == archived_int:
                _archived_balls = list(archived.get("balls") or [])
                log.info(
                    f"[ROLLBACK] Overs misread recovery: previously "
                    f"archived over {archived_int} = {_archived_balls} "
                    f"but team_overs now reads {overs} (still in "
                    f"over {archived_int}). Rewinding archive — "
                    f"restoring this_over and clearing slot.")
                self.this_over = _archived_balls
                self.this_over_sources = (["obs"] * len(_archived_balls))
                self.over_history.pop(archived_int, None)
                self._last_over_int = archived_int
                self._pending_clear = False
                self._pending_clear_at = None
                self._pending_clear_over_int = None
                self._held_over_bowler = None
                # restore over_start_score conservatively (best effort)
                self._over_start_score = (
                    score - sum(int(x) for x in _archived_balls
                                if isinstance(x, str) and x.isdigit())
                    if score is not None else self._over_start_score)
                return True

        # Multi-over jump guard. Cricket can never advance more than
        # one over at a time within the pipeline's per-frame
        # processing cadence. If new_int > _last_over_int + 1, this
        # is one of:
        #   - A Scout misread of the team-overs digit (e.g. 9.5 → 11.0
        #     for one frame, then back to 10.0)
        #   - A pipeline stall that genuinely missed an over of frames
        # In both cases, blindly advancing _last_over_int would
        # archive nothing, leak the missed over's balls into the
        # next over's `this_over`, and produce the visible "two overs
        # of circles in one ribbon" bug. Refuse the jump and wait for
        # a sane reading; the next correct frame will roll us forward
        # one over at a time.
        if (self._last_over_int is not None
                and new_int > self._last_over_int + 1):
            log.info(
                f"Over-jump rejected: {self._last_over_int} → "
                f"{new_int} is implausible for one frame (likely "
                f"Scout misread). Waiting for a sane overs reading.")
            return False

        if self._last_over_int is not None and new_int > self._last_over_int:
            # SHORT-OVER ROLLOVER DEFER. If `this_over` has fewer than
            # 6 legal balls at this point, the BallEventDetector has
            # not yet emitted the closing delivery for the over that
            # is being archived. Typical cause: `_inn.overs` has
            # advanced to (X+1).0 via a direct write / ScoreManager
            # commit in the same frame where `_tracker.overs` is
            # still at X.5, so the detector (which reads from the
            # tracker) sees no balls_delta. Without this defer we
            # would archive the over with 5 tokens and the 6-token
            # state would never be seen by the UI — the visible
            # "last ball missing" bug (2026-04-20).
            #
            # Defer up to ROLLOVER_MAX_DEFER_FRAMES frames to let the
            # tracker catch up. In the deferred frames the detector
            # fires the late DOT/run/W, on_ball_event appends it
            # normally (legal_count becomes 6), and the next
            # check_over_change call here archives cleanly with
            # `legal_count >= 6` so this guard is a no-op.
            _legal_count = sum(
                1 for x in self.this_over
                if str(x).lower() not in ("wd", "nb", "w")
                and not str(x).lower().startswith("wd")
                and not str(x).lower().startswith("nb"))
            # 'W' counts as a legal ball for this check — a wicket
            # delivery still consumes one of the six legal slots.
            _wicket_count = sum(1 for x in self.this_over if x == "W")
            _legal_count += _wicket_count
            if _legal_count < 6:
                if (self._rollover_defer_count
                        < ROLLOVER_MAX_DEFER_FRAMES):
                    self._rollover_defer_count += 1
                    log.info(
                        f"[OVER-DEFER] Rollover {self._last_over_int} "
                        f"→ {new_int} deferred "
                        f"({self._rollover_defer_count}/"
                        f"{ROLLOVER_MAX_DEFER_FRAMES}): "
                        f"this_over has {_legal_count}/6 legal balls "
                        f"— waiting for the closing-ball event to "
                        f"arrive before archiving.")
                    return False
                log.info(
                    f"[OVER-DEFER] Rollover {self._last_over_int} → "
                    f"{new_int} forced after "
                    f"{self._rollover_defer_count} deferrals: "
                    f"still only {_legal_count}/6 legal — archiving "
                    f"short; the closing ball was never detected.")
            # Fresh defer budget for the NEXT rollover.
            self._rollover_defer_count = 0
            # Pick the best bowler attribution we have. Priority order:
            #   1. The bowler we cached during this over from the
            #      observed ball events (most reliable — these were
            #      attached to actual deliveries we saw)
            #   2. The `bowler` argument passed in this frame
            #   3. The bowler attached to _last_ball_event
            # We deliberately rank the per-over cache ABOVE the live
            # strip parameter, because the strip can flip to the
            # incoming bowler as soon as the broadcast graphic refreshes
            # (often before check_over_change actually fires). Cricket
            # never permits the same bowler to bowl consecutive overs,
            # so taking the strip value at over rollover risks
            # crediting the next bowler with the over they didn't bowl.
            archive_bowler = (self._current_over_bowler
                              or bowler)
            if not archive_bowler and self._last_ball_event:
                archive_bowler = self._last_ball_event.get("bowler")
            bowler = archive_bowler
            # End-of-over reconciliation (LOG ONLY — never synth a
            # token here). Two reasons:
            #
            #   1. The over only advances when a LEGAL delivery is
            #      bowled. So the LAST circle in this_over MUST be a
            #      legal ball, never an extra. Appending a 'Wd' or
            #      'Nb' at over rollover puts an extra in a position
            #      where one is logically impossible.
            #
            #   2. Even when the discrepancy is real (we missed a
            #      delivery mid-over), we do not know which position
            #      the missing ball belongs to. Inserting it at the
            #      end is misleading; users read this as "the last
            #      ball was X" when in reality we just had +N runs
            #      unaccounted for somewhere in the over.
            #
            # The score itself is tracked authoritatively from the
            # broadcast scorecard — leaving the ribbon one circle
            # short is harmless. Surface the gap as a warning so the
            # next session can investigate; the broadcast strip's
            # `this_over_broadcast` (when read cleanly) can still
            # fill `?` placeholders via on_broadcast_override later.
            self._last_ball_event = None
            if score is not None and self._over_start_score is not None:
                _tracked_runs = sum(
                    int(x) for x in self.this_over
                    if isinstance(x, str) and x.isdigit())
                for _t in self.this_over:
                    if not isinstance(_t, str):
                        continue
                    _low = _t.lower()
                    if _low.startswith("wd") or _low.startswith("nb"):
                        _tracked_runs += 1
                        if "+" in _t:
                            try:
                                _tracked_runs += int(_t.split("+")[-1])
                            except (ValueError, IndexError):
                                pass
                _total_over_runs = score - self._over_start_score
                _missing = _total_over_runs - _tracked_runs
                if _missing != 0:
                    log.info(
                        f"Over {self._last_over_int} reconcile: "
                        f"score delta=+{_total_over_runs} but "
                        f"this_over tracks {_tracked_runs} runs "
                        f"({_missing:+d} missing). Tokens preserved "
                        f"as observed; no synth at over boundary "
                        f"(extras can never sit on the over-closing "
                        f"ball).")

            # over_history is APPEND-ONLY / FIRST-WRITE-WINS. Once an
            # over has been archived, that slot is immutable — no
            # subsequent code path (re-archive, mid-innings restart,
            # spurious over rollover) is allowed to overwrite it.
            # If we're being asked to write a slot that already
            # exists, log it loudly and keep the original entry.
            _archive_payload = {
                "balls": self.this_over.copy(),
                "bowler": bowler,
                "runs": sum(int(x) for x in self.this_over
                            if isinstance(x, str) and x.isdigit()),
                "wickets": sum(1 for x in self.this_over if x == "W"),
            }
            _existing_archive = self.over_history.get(self._last_over_int)
            if _existing_archive:
                log.info(
                    f"Over {self._last_over_int} re-archive REFUSED: "
                    f"slot already holds "
                    f"{_existing_archive.get('balls')} (by "
                    f"{_existing_archive.get('bowler')}). "
                    f"Ignoring new payload {_archive_payload}.")
            else:
                self.over_history[self._last_over_int] = _archive_payload
                log.info(
                    f"Over {self._last_over_int} complete: "
                    f"{self.this_over} = "
                    f"{_archive_payload['runs']} runs, "
                    f"{_archive_payload['wickets']} wkts "
                    f"(by {bowler})")
            # HOLD the completed over on display until either the next
            # ball event arrives, the broadcast shows the new over, or
            # the hold-window times out. Do NOT clear `this_over` yet.
            self._pending_clear = True
            self._pending_clear_at = time.monotonic()
            self._pending_clear_over_int = self._last_over_int
            # Remember which bowler bowled the held over. The next
            # over MUST be a different bowler (cricket forbids the
            # same bowler bowling consecutive overs), so a confirmed
            # different bowler is a definitive "new over started"
            # signal — flush the held display the moment we see one.
            self._held_over_bowler = bowler
            self._last_over_int = new_int
            self._over_start_score = score
            # Reset the per-over bowler cache for the new over.
            self._current_over_bowler = None
            return True

        # Fractional overs advance after a held completed over
        # (e.g. team moved from 1.0 → 1.1 — definitely a new over).
        if self._pending_clear and float(overs) > float(new_int):
            self._consume_pending_clear(
                f"team overs advanced to {overs}")

        # Time-based fallback: if we've held the completed over longer
        # than COMPLETED_OVER_HOLD_S without any new ball/over signal,
        # clear it so the UI doesn't get stuck on the previous over.
        if (self._pending_clear and self._pending_clear_at is not None
                and time.monotonic() - self._pending_clear_at
                > COMPLETED_OVER_HOLD_S):
            self._consume_pending_clear(
                f"hold-window {COMPLETED_OVER_HOLD_S:.0f}s elapsed")

        # Stale data guard: at X.0 with 6+ legal balls → clear
        # (skip while holding — that's the EXPECTED state during the
        # between-overs gap and the new check_over_change boundary
        # path already archived/held it correctly).
        if (not self._pending_clear
                and float(overs) == float(new_int)
                and self.this_over):
            legal = [x for x in self.this_over
                     if str(x).lower() not in ("wd", "nb", "w")
                     and not str(x).lower().startswith("wd")
                     and not str(x).lower().startswith("nb")]
            if len(legal) >= 6:
                log.info(f"Stale this-over at {overs} with "
                         f"{len(legal)} legal balls — clearing")
                self.this_over = []
                self.this_over_sources = []

        self._last_over_int = new_int
        if self._over_start_score is None and score is not None:
            self._over_start_score = score
        return False

    def initialize_mid_over(self, overs: str | None,
                            score_so_far: int | None = None,
                            wickets_so_far: int | None = None) -> None:
        """Pre-fill placeholders for cold-start mid-over joins.

        When ``score_so_far`` is provided, the helper applies a
        cricket-domain heuristic to infer per-ball tokens from the
        score delta (see ``cricket_rules.infer_gap_tokens``).  Without
        a score context, falls back to ``"?"`` placeholders for
        backward compatibility.

        ONLY runs when we're truly cold (no `_last_over_int` recorded
        yet). After the first over transition, this is a no-op —
        otherwise it would re-inject phantom placeholders into a
        freshly-cleared `this_over` (post over-transition), and then
        the next `on_ball_event.append(...)` would slot the real ball
        AFTER the phantoms, downgrading observed positions.
        """
        if self._last_over_int is not None:
            return
        balls = round((float(overs or "0") % 1) * 10)
        if balls > 0 and not self.this_over:
            if score_so_far is not None:
                from cricket_rules import _cold_start_infer_gap_tokens
                self.this_over = list(
                    _cold_start_infer_gap_tokens(
                        balls, int(score_so_far or 0),
                        int(wickets_so_far or 0)))
                self.this_over_sources = ["bcast_synth"] * balls
                log.info(
                    f"Joined at {overs}, pre-filled {balls} balls "
                    f"via infer_gap_tokens(score={score_so_far}, "
                    f"wkts={wickets_so_far}): {self.this_over}")
            else:
                self.this_over = ["?"] * balls
                self.this_over_sources = ["bcast"] * balls
                log.info(
                    f"Joined at {overs}, pre-filled {balls} "
                    f"balls as '?'")

    def get_display(self, overs: str | None) -> list[str]:
        # Time-based fallback for the held completed over — clear if
        # the hold window has elapsed even when no other signal came.
        if (self._pending_clear and self._pending_clear_at is not None
                and time.monotonic() - self._pending_clear_at
                > COMPLETED_OVER_HOLD_S):
            self._consume_pending_clear(
                f"hold-window {COMPLETED_OVER_HOLD_S:.0f}s elapsed (display)")

        # Always return the full observed sequence (incl. extras like
        # Wd / Nb). Once a ball has been observed and appended, it is
        # PERMANENT for the duration of this over — never trimmed,
        # never re-ordered. The broadcast frequently shows 7-9 circles
        # for an over (6 legal + N wides + N no-balls), and our UI
        # must mirror that.
        #
        # LENGTH FLOOR (issue #7): if team_overs reports more legal
        # balls than this_over contains, pad with `?` placeholders so
        # the UI never shows fewer balls than the broadcast says have
        # been bowled. Wides/no-balls (Wd, Nb tokens) don't count
        # against the legal floor — they're "extra" circles.
        if not overs:
            if self.this_over:
                self._log_count_mismatch(overs, len(self.this_over))
            return self.this_over[:]
        sub = round((float(overs) % 1) * 10)
        if self._pending_clear:
            return self.this_over[:]
        if sub == 0:
            return self.this_over[:]
        legal_n = sum(
            1 for x in self.this_over
            if str(x).lower() not in ("wd", "nb")
            and not str(x).lower().startswith("wd")
            and not str(x).lower().startswith("nb"))
        if legal_n < sub:
            # Pad with '?' placeholders so the UI ribbon length always
            # matches what the broadcast says has been bowled. The
            # placeholders are subsequently fillable by
            # `on_broadcast_override` (which only writes into '?'
            # slots) or get upgraded by future ball events.
            #
            # Defence-in-depth cap (P8 fix, 2026-05-02): the floor
            # pad must respect MAX_OBSERVED_THIS_OVER_LEN. Without
            # this clamp, a multi-over jump that `check_over_change`
            # rejects (`_last_over_int` stuck while team_overs
            # climbs) lets `sub` keep growing and the pad runs away
            # to 12+ '?' tokens for a single over — see
            # trace 866ce150 F181-F198. Once we hit the cap, we
            # surface the gap via `_log_count_mismatch` rather than
            # extending; the next observed ball or successful
            # `check_over_change` will reset the ribbon cleanly.
            requested = sub - legal_n
            allowed = MAX_OBSERVED_THIS_OVER_LEN - len(self.this_over)
            missing = max(min(requested, allowed), 0)
            if missing < requested:
                log.info(
                    f"[FLOOR-CAP] Pad clamped {requested}→{missing} "
                    f"to keep this_over within "
                    f"MAX_OBSERVED_THIS_OVER_LEN="
                    f"{MAX_OBSERVED_THIS_OVER_LEN} "
                    f"(team_overs={overs}, current={self.this_over})")
            for _ in range(missing):
                self.this_over.append("?")
                self.this_over_sources.append("bcast")
            if missing > 0:
                log.info(
                    f"[FLOOR] Padded {missing} '?' placeholders to "
                    f"this_over (team_overs={overs} expects {sub} "
                    f"legal, observed only {legal_n}) — "
                    f"new={self.this_over}")
            self._log_count_mismatch(overs, sub)
        elif legal_n > sub:
            self._log_count_mismatch(overs, legal_n)
        return self.this_over[:]

    def _log_count_mismatch(self, overs: str | None, legal_n: int) -> None:
        """One-shot log per over when display count diverges from
        team_overs. Helps diagnose wide-detection misses without
        spamming the log."""
        try:
            sub = round((float(overs or "0") % 1) * 10)
        except (ValueError, TypeError):
            return
        if sub == legal_n:
            return
        key = (self._last_over_int, sub, legal_n)
        if getattr(self, "_last_mismatch_key", None) == key:
            return
        self._last_mismatch_key = key
        log.info(
            f"this_over count mismatch: team@{overs} expects "
            f"{sub} legal balls, observed {legal_n} legal "
            f"(tokens={self.this_over}) — keeping observations")
