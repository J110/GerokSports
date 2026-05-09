"""Commentary-quality data derived from scorecard deltas.

All classes here compute data Machine 2 needs WITHOUT any extra
vision calls — purely from frame-to-frame state changes.
"""
from __future__ import annotations

from copy import deepcopy

from eyes.cricket_logger import CricketLogger

log = CricketLogger("COMMENTARY")


class BallEventDetector:
    """Detect ball events from confirmed tracker values only.

    Emits certain events when overs advance by exactly 1 ball.
    Also detects wides/no-balls via broadcast_extra signal or
    score+1 with overs unchanged.
    """

    def __init__(self):
        # When a wicket is detected without an overs tick we
        # already credited the delivery to that wicket. The
        # broadcast's eventual overs tick must then be silently
        # consumed (otherwise we'd emit a phantom DOT for the
        # same delivery). `_balls_owed_to_silence` tracks how
        # many upcoming legal-ball ticks should be ignored.
        self._balls_owed_to_silence: int = 0
        self.prev_score: int | None = None
        self.prev_wickets: int | None = None
        self.prev_overs: str | None = None
        self.prev_bowler_runs: int | None = None
        # Track previous frame's bowler so we can tell when an over
        # rollover invalidates `prev_bowler_runs` for delta math
        # (the new bowler's small total minus the old bowler's large
        # total gives a meaningless negative delta).
        self.prev_bowler: str | None = None
        # Track striker name + balls to infer extras when score
        # advances but neither legal-balls nor batter-balls do.
        self.prev_striker: str | None = None
        self.prev_striker_balls: int | None = None
        # Track striker runs as an independent witness for leg-bye
        # classification (Bug #11). Bowler runs in the broadcast strip
        # often lag the team score by 1-2 frames; if we relied only on
        # bowler_runs_delta == 0, every legal off-the-bat single during
        # that lag window would be mislabelled as a leg bye.
        self.prev_striker_runs: int | None = None
        self.events: list[dict] = []
        self._possible_extra: dict | None = None
        self._broadcast_extra: str | None = None
        self._free_hit_next = False
        self._event_queue: list[dict] = []
        self._prev_broadcast_extra: str | None = None
        self._broadcast_extra_changed_at: int = 0
        self._detect_count: int = 0
        # Recent (over, type, runs, score_at_event) tuples so we can
        # suppress a duplicate emission of the SAME event within a short
        # window.  Entries are aged out after _DEDUP_WINDOW detect calls
        # (≈30s @ 1Hz processing) — long enough to swallow OCR jitter
        # that re-presents the same delta one or two frames later, short
        # enough that a real second wide on the same scoreboard read is
        # not falsely suppressed (which can't happen anyway: a real
        # second wide changes the score, which changes the dedup key).
        self._recent_emissions: list[tuple[int, tuple]] = []
        self._DEDUP_WINDOW = 30
        # Pending-jitter deferral for the EXTRA-IMMEDIATE catch-all path.
        # When score increases by +1 with NO corroborating signal (no
        # broadcast WD/NB, no bowler-runs delta, no striker-balls
        # quiet — i.e. the only evidence is the team-score digit
        # itself), defer one frame to confirm.  Real wides almost
        # always come with at least one supporting signal within the
        # 1-3s broadcast lag; isolated +1 score deltas with zero
        # corroboration are overwhelmingly OCR jitter on the score
        # digit.  Discovered 2026-04-19 KKR-vs-RR: 5 phantom Wd
        # tokens fired this run via this catch-all.
        self._extra_jitter_pending: dict | None = None

    def reset(self) -> None:
        """Wipe all state for a fresh innings (Bug #14).

        Without this, prev_score / prev_overs / prev_striker_runs from
        innings 1 produce huge spurious deltas at the first frame of
        innings 2 (e.g. score 230 → 0 looks like a -230 score
        correction; overs 20.0 → 0.5 looks like a multi-ball jump).
        """
        self._balls_owed_to_silence = 0
        self.prev_score = None
        self.prev_wickets = None
        self.prev_overs = None
        self.prev_bowler_runs = None
        self.prev_bowler = None
        self.prev_striker = None
        self.prev_striker_balls = None
        self.prev_striker_runs = None
        self.events = []
        self._possible_extra = None
        self._broadcast_extra = None
        self._free_hit_next = False
        self._event_queue = []
        self._prev_broadcast_extra = None
        self._broadcast_extra_changed_at = 0
        self._detect_count = 0
        self._extra_jitter_pending = None
        log.info("[BED] Detector reset for new innings")

    def set_broadcast_extra(self, extra_type: str | None):
        """Feed broadcast EXTRA: WD/NB signal from info panel."""
        if extra_type != self._prev_broadcast_extra:
            self._broadcast_extra_changed_at = self._detect_count
        self._prev_broadcast_extra = self._broadcast_extra
        self._broadcast_extra = extra_type

    def _broadcast_extra_is_fresh(self, within_calls: int = 5) -> bool:
        """True if _broadcast_extra changed value recently.

        Avoids treating stale broadcast display (e.g. "EXTRA: WD" left
        visible for multiple deliveries within an over) as a fresh signal.
        """
        return (self._broadcast_extra is not None
                and self._detect_count - self._broadcast_extra_changed_at
                <= within_calls)

    def _dedup_key(self, event: dict, score_at_event) -> tuple:
        """Compose the dedup tuple per Bug #6 spec.

        Includes score_at_event so a legitimate second extra of the
        same type at the same over (which always changes the score)
        produces a distinct key and fires correctly.
        """
        return (
            str(event.get("over") or ""),
            event.get("type"),
            event.get("extra_type"),
            int(event.get("runs") or 0),
            int(score_at_event or 0),
        )

    def _is_duplicate(self, key: tuple) -> bool:
        cutoff = self._detect_count - self._DEDUP_WINDOW
        self._recent_emissions = [
            (c, k) for c, k in self._recent_emissions if c >= cutoff]
        for _, k in self._recent_emissions:
            if k == key:
                return True
        return False

    def _record_emission(self, key: tuple) -> None:
        self._recent_emissions.append((self._detect_count, key))

    @staticmethod
    def _to_balls(overs) -> int:
        o = float(overs or "0")
        return int(o) * 6 + round((o % 1) * 10)

    def detect(self, tracker) -> dict | None:
        """Read from ConsistentReadTracker directly."""
        self._detect_count += 1

        # Drain queued events before processing new state.
        # This delivers the legal delivery that was queued behind an extra.
        if self._event_queue:
            event = self._event_queue.pop(0)
            score_now = tracker.get("score")
            dedup_key = self._dedup_key(event, score_now)
            if self._is_duplicate(dedup_key):
                log.info(f"[DEDUP] suppressed duplicate (queued) "
                         f"{event.get('type')} | "
                         f"{event.get('over')} key={dedup_key}")
                return None
            self._record_emission(dedup_key)
            self.events.append(event)
            tag = "✓" if event.get("certain") else "?"
            log.info(f"[BALL {tag}] {event['type']} | "
                     f"{event.get('over', '?')} "
                     f"+{event.get('runs', 0)} runs (queued)")
            return event

        score = tracker.get("score")
        wickets = tracker.get("wickets")
        overs = tracker.get("overs")

        cur_bowler_early = tracker.get("current_bowler")

        # Establish baseline: first time we see any overs witness.
        if self.prev_overs is None:
            self._save(score, wickets, overs, bowler=cur_bowler_early)
            return None
        # Team overs often missing from ConsistentReadTracker on non-strip
        # frames (close-up, ad, DRS) while score/wickets still commit.
        # Old behaviour: `_save(..., overs=None)` cleared `prev_overs`,
        # wiping the balls baseline — BallEventDetector never reached
        # `balls_delta` math for the rest of an innings (observed: zero
        # delivery detection in innings 2 when overs stayed None in UI).
        if overs is None:
            self._save(score, wickets, self.prev_overs,
                       bowler=cur_bowler_early)
            return None

        new_b = self._to_balls(overs)
        old_b = self._to_balls(self.prev_overs)
        balls_delta = new_b - old_b
        s_delta = (score or 0) - (self.prev_score or 0)
        w_delta = (wickets or 0) - (self.prev_wickets or 0)

        # Pending-jitter housekeeping: a deferred extra is only valid
        # if THIS frame is the exact "same +1, same score, no other
        # change" we expected.  Anything else — over advanced, wicket
        # fell, score moved by something other than +1 — overtakes
        # the deferral; drop the pending marker so it can't fire on
        # a future frame.  (The pure-regression case is handled by
        # the steady-state branch below.)
        if (self._extra_jitter_pending is not None
            and not (s_delta == 1 and balls_delta == 0 and w_delta == 0
                     and (self._extra_jitter_pending.get("score_at")
                          == score))
            and not (s_delta == 0 and balls_delta == 0 and w_delta == 0)):
            log.info(
                f"[EXTRA] method=jitter_overtaken s_delta={s_delta} "
                f"balls_delta={balls_delta} w_delta={w_delta} — "
                f"discarding deferred extra "
                f"(pending_score={self._extra_jitter_pending.get('score_at')})")
            self._extra_jitter_pending = None

        if balls_delta == 0 and s_delta == 0 and w_delta == 0:
            # Score steady-state — if a jittered +1 was deferred last
            # frame and the score regressed back here, the deferral
            # was correct: the +1 was OCR noise.  Clear the pending
            # marker so we don't fire a stale EXTRA on the next +1.
            if self._extra_jitter_pending is not None:
                log.info(
                    f"[EXTRA] method=jitter_cleared "
                    f"pending_score={self._extra_jitter_pending['score_at']} "
                    f"now_steady_at={score} — discarding deferred extra")
                self._extra_jitter_pending = None
            self._save(score, wickets, overs, bowler=cur_bowler_early)
            return None

        # A legal delivery can produce at most 7 runs (6 + 1 no-ball).
        # Larger deltas are score corrections, not real deliveries.
        if abs(s_delta) > 7 and w_delta == 0:
            log.info(f"[GUARD] Score correction detected: delta={s_delta}, "
                     f"not a ball event")
            self._save(score, wickets, overs, bowler=cur_bowler_early)
            return None

        # Compute bowler runs delta early — needed for leg bye detection
        bowler_runs = None
        cur_bowler = tracker.get("current_bowler")
        if cur_bowler:
            bowler_runs = tracker.get(f"bowl:{cur_bowler}:runs")
            if bowler_runs is not None:
                bowler_runs = int(bowler_runs)
        bowler_runs_delta = 0
        if bowler_runs is not None and self.prev_bowler_runs is not None:
            bowler_runs_delta = bowler_runs - self.prev_bowler_runs

        # Striker faced-balls delta — independent witness for whether
        # any legal delivery was bowled to this batter.
        cur_striker = tracker.get("striker")
        striker_balls = None
        if cur_striker:
            _sb = tracker.get(f"bat:{cur_striker}:balls")
            if _sb is not None:
                try:
                    striker_balls = int(_sb)
                except (ValueError, TypeError):
                    striker_balls = None
        striker_balls_delta = 0
        # Only meaningful if the striker hasn't changed since last
        # detect call (rotation would naturally show prev=None for
        # the new batter, falsely registering 0 delta).
        if (cur_striker
                and cur_striker == self.prev_striker
                and striker_balls is not None
                and self.prev_striker_balls is not None):
            striker_balls_delta = striker_balls - self.prev_striker_balls

        # Striker runs delta — independent witness for whether the runs
        # came off the bat. If this is positive, the runs are NOT a leg
        # bye/bye, regardless of where the bowler runs strip currently
        # sits.
        striker_runs = None
        if cur_striker:
            _sr = tracker.get(f"bat:{cur_striker}:runs")
            if _sr is not None:
                try:
                    striker_runs = int(_sr)
                except (ValueError, TypeError):
                    striker_runs = None
        striker_runs_delta = 0
        striker_runs_witnessed = False
        if (cur_striker
                and cur_striker == self.prev_striker
                and striker_runs is not None
                and self.prev_striker_runs is not None):
            striker_runs_delta = striker_runs - self.prev_striker_runs
            striker_runs_witnessed = True

        event: dict | None = None

        # Consume any owed silenced ball-ticks first. These exist
        # when we previously emitted a WICKET for a delivery whose
        # overs hadn't yet ticked on the broadcast strip; we owe
        # one silent tick per such wicket so the broadcast catch-up
        # doesn't re-emit a phantom DOT for the same delivery.
        if (self._balls_owed_to_silence > 0
                and balls_delta >= 1
                and s_delta == 0
                and w_delta == 0):
            self._balls_owed_to_silence -= 1
            log.info(
                f"[BED] Silencing 1 owed ball-tick "
                f"(balls_delta={balls_delta}); "
                f"remaining owed={self._balls_owed_to_silence}")
            self._save(score, wickets, overs, bowler_runs,
                       cur_striker, striker_balls, striker_runs)
            return None

        # LATE-BOUNDARY PROMOTION: when the previous frame held a
        # `_possible_extra` (score increased without overs ticking),
        # and THIS frame the overs tick with no further score change,
        # the held score-delta was actually a legal boundary whose
        # over-tick lagged by one frame. Promote to FOUR/SIX/N_RUNS
        # instead of emitting a phantom DOT for the catch-up frame.
        # Without this, score 121→125 (overs lagged) → next frame
        # overs tick (s_delta=0) emits DOT and we lose the boundary
        # token in this_over.
        if (balls_delta == 1
                and s_delta == 0
                and w_delta == 0
                and self._possible_extra is not None
                and self._possible_extra.get("score_at") == score
                and self._possible_extra.get("runs", 0) > 0):
            late_runs = int(self._possible_extra.get("runs", 0))
            if late_runs == 4:
                event = {"type": "FOUR", "runs": 4, "certain": True}
            elif late_runs == 6:
                event = {"type": "SIX", "runs": 6, "certain": True}
            else:
                event = {"type": f"{late_runs}_RUNS",
                         "runs": late_runs, "certain": True}
            event["over"] = overs
            event["bowler"] = tracker.get("current_bowler")
            event["batter"] = tracker.get("striker")
            log.info(
                f"[BED] Late-boundary promotion: held score+"
                f"{late_runs} (overs lagged) is now confirmed by "
                f"overs tick — emitting "
                f"{event['type']} instead of DOT")
            self._possible_extra = None

        if event is None and balls_delta == 1:
            # Check if a fresh broadcast_extra implies an extra + legal
            # delivery were both missed in the same Scout gap.  The wide/NB
            # always precedes the legal re-bowl chronologically.
            if self._broadcast_extra_is_fresh(within_calls=5):
                _bcast = self._broadcast_extra
                extra_type = "wide" if _bcast == "WD" else "no_ball"

                # The extra consumed 1 run; remaining runs are from the
                # legal delivery that followed.
                extra_runs = 1
                legal_runs = max(0, s_delta - extra_runs)

                extra_event = {
                    "type": "EXTRA", "extra_type": extra_type,
                    "runs": extra_runs, "certain": True,
                    "over": self.prev_overs,
                    "bowler": cur_bowler,
                    "_event_age_hint": "older",
                }

                # Build the legal delivery event for the queue
                if w_delta > 0:
                    legal_event = {"type": "WICKET", "runs": legal_runs,
                                  "certain": True}
                elif legal_runs == 0:
                    legal_event = {"type": "DOT", "runs": 0, "certain": True}
                elif legal_runs == 4:
                    legal_event = {"type": "FOUR", "runs": 4, "certain": True}
                elif legal_runs == 6:
                    legal_event = {"type": "SIX", "runs": 6, "certain": True}
                else:
                    legal_event = {"type": f"{legal_runs}_RUNS",
                                  "runs": legal_runs, "certain": True}
                legal_event["over"] = overs
                legal_event["bowler"] = tracker.get("current_bowler")
                legal_event["batter"] = tracker.get("striker")

                log.info(f"[DECOMPOSE] balls_delta=1 + fresh {_bcast}: "
                         f"emitting EXTRA({extra_runs}) first, "
                         f"queueing {legal_event['type']}({legal_runs})")

                self._event_queue.append(legal_event)
                self._broadcast_extra = None
                if extra_type == "no_ball":
                    self._free_hit_next = True

                event = extra_event
            else:
                if w_delta > 0:
                    event = {"type": "WICKET", "runs": s_delta,
                             "certain": True}
                elif s_delta == 0:
                    event = {"type": "DOT", "runs": 0, "certain": True}
                elif s_delta == 4:
                    event = {"type": "FOUR", "runs": 4, "certain": True}
                elif s_delta == 6:
                    event = {"type": "SIX", "runs": 6, "certain": True}
                else:
                    event = {"type": f"{s_delta}_RUNS", "runs": s_delta,
                             "certain": True}
                event["over"] = overs
                event["bowler"] = tracker.get("current_bowler")
                event["batter"] = tracker.get("striker")

                # Leg bye / bye detection (Bug #11 hardened):
                # The OLD heuristic — bowler_runs_delta == 0 alone — fired
                # false positives whenever the bowler stats strip lagged
                # the team score by 1-2 frames (a normal Star Sports broadcast
                # behaviour). A real off-the-bat single would be tagged "1lb"
                # until the bowler strip caught up — by then the over ribbon
                # had already shipped the wrong token to the UI.
                #
                # New rule: ONLY classify as leg-bye/bye when we have BOTH
                # witnesses agreeing the runs went past the bat:
                #   1. Bowler runs unchanged (existing — runs not credited
                #      to bowler)
                #   2. Striker runs unchanged AND we successfully read the
                #      same striker in both frames (new — runs not credited
                #      to batter either)
                # If the striker witness is absent (rotation, missed read),
                # fall back to "regular run" rather than risk the false
                # positive. A missed leg-bye tag is far less harmful than
                # silently downgrading a batter's actual run.
                striker_quiet = (striker_runs_witnessed
                                 and striker_runs_delta == 0)
                if (event["type"] not in ("DOT", "WICKET", "FOUR", "SIX")
                        and s_delta > 0 and bowler_runs_delta == 0
                        and bowler_runs is not None
                        and self.prev_bowler_runs is not None
                        and striker_quiet):
                    event["extras_type"] = "leg_bye_or_bye"
                    event["extras_runs"] = s_delta
                    log.info(f"[DETECT] Likely leg bye/bye: score +{s_delta}, "
                             f"bowler runs unchanged AND striker "
                             f"{cur_striker} runs unchanged "
                             f"(prev={self.prev_striker_runs}, "
                             f"now={striker_runs})")
                elif (event["type"] not in ("DOT", "WICKET", "FOUR", "SIX")
                        and s_delta > 0 and bowler_runs_delta == 0
                        and bowler_runs is not None
                        and self.prev_bowler_runs is not None
                        and striker_runs_witnessed
                        and striker_runs_delta > 0):
                    log.info(f"[DETECT] Bowler runs lag detected: score "
                             f"+{s_delta}, bowler runs flat but striker "
                             f"{cur_striker} runs +{striker_runs_delta} "
                             f"— treating as legal run off the bat, NOT "
                             f"leg-bye")

        elif balls_delta > 1:
            event = {"type": "MULTI_BALL", "balls_missed": balls_delta,
                     "total_runs": s_delta, "certain": False}

        # WICKET-WITHOUT-OVERS-TICK: wicket fell but the broadcast
        # team-overs strip hasn't ticked yet (very common — the
        # wicket animation/celebration freezes the overs counter for
        # 1-3 frames). Without this path we'd later see the overs
        # tick with w_delta=0 and emit a DOT for what was actually
        # a wicket ball.
        #
        # Two sub-cases:
        #   (a) overs has NOT yet ticked: emit WICKET now AND
        #       advance prev_overs internally so the upcoming
        #       broadcast overs tick is silently consumed.
        #   (b) overs ALREADY ticked in a prior frame and we
        #       emitted the previous ball as DOT/RUNS — now wickets
        #       caught up. Emit WICKET_LATE which replaces the most
        #       recent token in this_over with 'W' (cricket: the
        #       "previous" ball was actually a wicket ball).
        if (event is None
                and balls_delta == 0
                and w_delta > 0):
            # Detect "late" sub-case: was the immediately-preceding
            # event a normal delivery (DOT / N_RUNS / WICKET / FOUR
            # / SIX, NOT an extra) at the SAME overs string the
            # tracker now reports? If yes, the wicket maps to that
            # delivery, not a new one.
            _is_late = False
            if self.events:
                _last = self.events[-1]
                _last_over = str(_last.get("over") or "")
                _last_type = _last.get("type", "")
                if (_last_over == str(overs)
                        and _last_type in ("DOT", "FOUR", "SIX",
                                            "WICKET")
                        and not _last_type.startswith("WICKET_LATE")
                        and not _last.get("extra_type")):
                    _is_late = True
                elif (_last_over == str(overs)
                      and _last_type.endswith("_RUNS")):
                    _is_late = True
            if _is_late:
                event = {"type": "WICKET_LATE", "runs": s_delta,
                         "certain": True}
                event["over"] = overs
                event["bowler"] = tracker.get("current_bowler")
                event["batter"] = tracker.get("striker")
                log.info(
                    f"[BED] Late wicket reading (w_delta=+{w_delta} "
                    f"after overs already ticked) — emitting "
                    f"WICKET_LATE to upgrade last token to 'W'")
            else:
                event = {"type": "WICKET", "runs": s_delta,
                         "certain": True}
                event["over"] = overs
                event["bowler"] = tracker.get("current_bowler")
                event["batter"] = tracker.get("striker")
                # Owe a silenced legal-ball tick: when the
                # broadcast's overs strip eventually catches up
                # (often 1-3 frames later), we must NOT emit a
                # phantom DOT for the same delivery we just
                # credited to the wicket.
                self._balls_owed_to_silence += 1
                log.info(
                    f"[BED] Wicket detected without overs tick "
                    f"(w_delta={w_delta}, s_delta={s_delta}) — "
                    f"emitting WICKET, owing 1 silenced ball-tick")

        # DRS outcomes: overs go back, wickets decrease
        if balls_delta == -1 and s_delta >= 1 and s_delta <= 2:
            event = {"type": "DRS_WIDE", "runs": s_delta,
                     "certain": True, "over": overs,
                     "bowler": tracker.get("current_bowler")}
        if balls_delta == 0 and w_delta == -1:
            event = {"type": "DRS_NOT_OUT", "runs": 0,
                     "certain": True, "over": overs,
                     "bowler": tracker.get("current_bowler")}

        # Extras: score changed but overs unchanged (wide / no-ball).
        #
        # CRICKET INVARIANT (the user's hard rule): if `balls_delta ==
        # 0` and `s_delta > 0`, the only cricket-legal explanation is
        # an extra. There is NO scenario where the team can score runs
        # without the legal-balls counter ticking, except wides and
        # no-balls. Therefore we emit an EXTRA event IMMEDIATELY on
        # the first frame we see this delta — no consensus, no fall-
        # through to a slow path. The 4 supplementary signals
        # (`_bcast`, striker_balls_quiet, bowler_runs_delta, etc.)
        # only refine the wide-vs-no_ball CLASSIFICATION; they no
        # longer gate the event itself.
        if bowler_runs is not None and self.prev_bowler_runs is not None:
            bowler_runs_delta = bowler_runs - self.prev_bowler_runs

        if balls_delta == 0 and s_delta > 0 and event is None:
            _bcast = self._broadcast_extra
            striker_witnessed = (
                cur_striker is not None
                and cur_striker == self.prev_striker
                and striker_balls is not None
                and self.prev_striker_balls is not None)
            striker_balls_quiet = (
                striker_witnessed and striker_balls_delta == 0)

            # Sanity-cap on bowler_runs_delta: max runs charged on a
            # single delivery is 7 (no-ball + 6 off the bat). Anything
            # larger means the LLM read a different bowler's row; do
            # not trust it as a wide-vs-no_ball signal.
            bowler_runs_signal_ok = (
                bowler_runs_delta is not None
                and bowler_runs_delta > 0
                and bowler_runs_delta <= 7
                and self.prev_bowler is not None
                and cur_bowler == self.prev_bowler)

            # Evidence-source-aware classification.  The branches below
            # set both `extra_type` AND a `_method` tag for the new
            # [EXTRA] log line so we can audit which evidence drove
            # each decision.  The trailing catch-all is gated by a
            # one-frame deferral when there is NO corroboration —
            # see the `_extra_jitter_pending` block below for why.
            _method: str | None = None
            extra_type = None
            _why = ""
            if _bcast == "NB":
                extra_type = "no_ball"
                _method = "broadcast_NB"
                _why = "broadcast NB signal"
            elif _bcast == "WD":
                extra_type = "wide"
                _method = "broadcast_WD"
                _why = "broadcast WD signal"
            elif striker_balls_quiet:
                extra_type = "wide"
                _method = "striker_balls_quiet"
                _why = (f"striker {cur_striker} balls unchanged "
                        f"(prev={self.prev_striker_balls}, "
                        f"now={striker_balls}); a no-ball would have "
                        f"ticked striker balls")
            elif bowler_runs_signal_ok:
                extra_type = "wide" if s_delta <= 2 else "no_ball"
                _method = "bowler_runs_delta"
                _why = (f"bowler {cur_bowler} runs "
                        f"+{bowler_runs_delta} (stable bowler)")
            else:
                # NO corroborating signal at all.  This branch is the
                # phantom-extra factory — one stray frame where the
                # team-score digit jitters from 125 → 126 and back is
                # all it takes to ship a Wd token to the UI that
                # never gets cleaned up.  Defer one frame: if the
                # delta persists, fire; if the score regresses, the
                # steady-state path above will clear the pending
                # marker and we never fire.
                if (s_delta == 1
                        and self._extra_jitter_pending is None):
                    self._extra_jitter_pending = {
                        "score_at": score,
                        "overs": overs,
                        "bowler": cur_bowler,
                    }
                    log.info(
                        f"[EXTRA] method=deferred reason=no_corroboration "
                        f"score+{s_delta} at overs={overs} — "
                        f"will confirm next frame "
                        f"(no broadcast WD/NB, no bowler-runs delta, "
                        f"no striker-balls signal)")
                    # Critical: do NOT call self._save() — we need the
                    # next frame's delta to recompute against the same
                    # prev_score so a steady +1 looks like +1 again
                    # (then we fire) and a regression looks like 0
                    # (then steady-state path clears pending).
                    self._possible_extra = None
                    return None

                # If we ARE pending and the delta is still +1 vs the
                # previous (un-saved) prev_score AND score matches the
                # pending score_at, that's the confirmation we waited
                # for.  Fire as wide (no signal still, but two
                # consecutive frames of agreement is enough).
                if (s_delta == 1
                        and self._extra_jitter_pending is not None
                        and (self._extra_jitter_pending.get("score_at")
                             == score)):
                    extra_type = "wide"
                    _method = "deferred_confirmed"
                    _why = (f"score +{s_delta} sustained 2 frames "
                            f"(jitter ruled out)")
                    self._extra_jitter_pending = None
                else:
                    # Multi-run no-signal extra (s_delta == 2..7) or
                    # something else unexpected — keep prior behaviour.
                    extra_type = "wide"
                    _method = "no_signal_default"
                    _why = (f"score +{s_delta} with overs unchanged → "
                            f"cricket-invariant extra, defaulting wide "
                            f"(no broadcast signal, multi-run)")

            event = {
                "type": "EXTRA", "extra_type": extra_type,
                "runs": s_delta, "certain": True, "over": overs,
                "bowler": cur_bowler}
            log.info(
                f"[EXTRA-IMMEDIATE] {extra_type}: score +{s_delta}, "
                f"overs unchanged ({overs}) — {_why}")
            log.info(f"[EXTRA] method={_method} extra_type={extra_type} "
                     f"runs={s_delta} fired")
            self._possible_extra = None
            self._broadcast_extra = None
            # A real-signal fire supersedes any pending jitter (e.g.
            # we deferred on frame N for no signal, then on frame N+1
            # the broadcast WD strip caught up — fire on the WD signal
            # and clear pending so we don't double-fire next frame).
            self._extra_jitter_pending = None
            if extra_type == "no_ball":
                self._free_hit_next = True
        else:
            self._possible_extra = None

        # Tag free hit on the next legal delivery after a no-ball
        if event and balls_delta == 1 and self._free_hit_next:
            event["free_hit"] = True
            self._free_hit_next = False

        self._save(score, wickets, overs, bowler_runs,
                   cur_striker, striker_balls, striker_runs,
                   bowler=cur_bowler)

        if event:
            dedup_key = self._dedup_key(event, score)
            if self._is_duplicate(dedup_key):
                log.info(f"[DEDUP] suppressed duplicate "
                         f"{event.get('type')} | {event.get('over')} "
                         f"+{event.get('runs')} runs (key={dedup_key})")
                return None
            self._record_emission(dedup_key)
            self.events.append(event)
            tag = "✓" if event.get("certain") else "?"
            log.info(f"[BALL {tag}] {event['type']} | {overs} "
                     f"+{s_delta} runs (Δballs={balls_delta})")
        return event

    def _save(self, s, w, o, br=None,
              striker=None, striker_balls=None, striker_runs=None,
              bowler=None):
        self.prev_score = s
        self.prev_wickets = w
        self.prev_overs = o
        if br is not None:
            self.prev_bowler_runs = br
        # Track bowler identity even when bowler_runs is None — we
        # need it to detect over-rollover bowler swaps for the
        # extras classifier.
        if bowler is not None:
            self.prev_bowler = bowler
        # Always overwrite striker so rotations are reflected; only
        # remember striker_balls/runs when the striker is stable AND we
        # actually have a value (avoid wiping a known prev value
        # when this frame's tracker read came back None).
        if striker is not None:
            self.prev_striker = striker
        if striker_balls is not None:
            self.prev_striker_balls = striker_balls
        if striker_runs is not None:
            self.prev_striker_runs = striker_runs


class PartnershipTracker:
    """Track partnerships from active batter pairs."""

    def __init__(self):
        self.current_pair: set[str] = set()
        self.partnership_start_score = 0
        self.partnership_start_balls = 0
        self.partnerships: list[dict] = []

    def reset(self) -> None:
        """Wipe all state for a fresh innings (Bug #14).

        Without this, partnership_start_balls carries the innings-1
        anchor (e.g. 73) into innings 2 and produces nonsense like
        '26 runs (-25 balls)' until the first ball event of the new
        innings re-anchors the tracker.
        """
        self.current_pair = set()
        self.partnership_start_score = 0
        self.partnership_start_balls = 0
        self.partnerships = []
        log.info("[PARTNERSHIP] Tracker reset for new innings")

    def update(self, active_batters: dict, team_score: int,
               team_balls: int,
               initial_guess_runs: int | None = None,
               initial_guess_balls: int | None = None) -> dict | None:
        """Update active pair; returns the just-ended partnership if any.

        New (2026-04-18): when anchoring a fresh pair, callers may
        supply `initial_guess_runs` and `initial_guess_balls` — the
        best-effort estimate of how much the new pair has already
        accumulated. We then back-date the anchor so that
        `current(team_score, team_balls)` returns the guess straight
        away, instead of zero. This matters during cold-start mid-
        innings: without it the tracker pretends the pair is fresh
        and `current = team_score - 0 = 169` which is wildly wrong.
        """
        pair = set(active_batters.keys())
        ended = None

        if pair != self.current_pair and len(pair) == 2:
            if self.current_pair:
                ended = {
                    "batters": list(self.current_pair),
                    "runs": team_score - self.partnership_start_score,
                    "balls": team_balls - self.partnership_start_balls,
                    "ended": True,
                }
                self.partnerships.append(ended)
                log.info(f"[PARTNERSHIP] {ended['batters']} — "
                         f"{ended['runs']} runs off {ended['balls']} balls")

            self.current_pair = pair
            if initial_guess_runs is not None:
                self.partnership_start_score = (
                    team_score - max(0, int(initial_guess_runs)))
            else:
                self.partnership_start_score = team_score
            if initial_guess_balls is not None:
                self.partnership_start_balls = (
                    team_balls - max(0, int(initial_guess_balls)))
            else:
                self.partnership_start_balls = team_balls
            log.info(
                f"[PARTNERSHIP] new pair {pair} anchored at score="
                f"{self.partnership_start_score} balls="
                f"{self.partnership_start_balls}  (team={team_score}/"
                f"{team_balls}, guess_runs={initial_guess_runs} "
                f"guess_balls={initial_guess_balls})")

        return ended

    def override(self, team_score: int, team_balls: int,
                 broadcast_runs: int, broadcast_balls: int) -> None:
        """Hard-override anchor from a trusted broadcast read.

        Cricbuzz / Hotstar overlays periodically render the literal
        "P'SHIP 26 (18)" — when we see that, prefer it over our
        derived numbers. We rebase the anchor so that subsequent
        `current()` calls return broadcast_runs / broadcast_balls
        relative to the now-current team_score / team_balls.
        """
        new_start_score = team_score - max(0, int(broadcast_runs))
        new_start_balls = team_balls - max(0, int(broadcast_balls))
        if (new_start_score != self.partnership_start_score
                or new_start_balls != self.partnership_start_balls):
            log.info(
                f"[PARTNERSHIP] broadcast override: {broadcast_runs}"
                f"({broadcast_balls}) — anchor {self.partnership_start_score}"
                f"/{self.partnership_start_balls} → {new_start_score}/"
                f"{new_start_balls}")
            self.partnership_start_score = new_start_score
            self.partnership_start_balls = new_start_balls

    def current(self, team_score: int, team_balls: int) -> dict:
        return {
            "runs": max(0, team_score - self.partnership_start_score),
            "balls": max(0, team_balls - self.partnership_start_balls),
            "batters": list(self.current_pair),
            "ended": False,
        }


def overs_to_balls(overs_str: str) -> int:
    s = str(overs_str or "0")
    if "." in s:
        w, b = s.split(".")
        return int(w) * 6 + int(b)
    return int(s) * 6


def get_match_situation(state: dict) -> dict:
    score = state.get("score") or 0
    wickets = state.get("wickets") or 0
    overs = float(state.get("overs") or "0")
    target = state.get("target")
    innings = state.get("innings", 1)

    balls_bowled = overs_to_balls(str(overs))
    # Bug #15: compute run-rate from balls_bowled (the canonical
    # measure) and require BOTH score AND balls > 0. Previous formula
    # `score / (overs or 0.1)` produced CRR=590 whenever score lagged
    # the overs reset by one frame at innings transition (59 / 0.1 =
    # 590 displayed in the situation panel while the ScoreStrip
    # showed the correct 7.38 from a different code path). Falling
    # back to 0 here also ensures the UI's `sit.run_rate > 0` guard
    # correctly hides the field instead of rendering bogus numbers.
    if balls_bowled > 0 and score > 0:
        run_rate = round(score / balls_bowled * 6, 2)
    else:
        run_rate = 0.0

    situation: dict = {
        "run_rate": run_rate,
        "balls_bowled": balls_bowled,
        "balls_remaining": 120 - balls_bowled,
        "wickets_in_hand": 10 - wickets,
    }

    if target and innings == 2:
        runs_needed = int(target) - score
        balls_left = 120 - balls_bowled
        req_rate = round(runs_needed / (balls_left / 6), 2) if balls_left > 0 else 999
        situation["runs_needed"] = runs_needed
        situation["balls_remaining"] = balls_left
        situation["required_rate"] = req_rate

        if runs_needed <= 0:
            situation["phase"] = "WON"
        elif wickets >= 8:
            situation["phase"] = "DESPERATE"
        elif req_rate > 12:
            situation["phase"] = "VERY_DIFFICULT"
        elif req_rate > 9:
            situation["phase"] = "CHALLENGING"
        elif req_rate < 6:
            situation["phase"] = "COMFORTABLE"
        else:
            situation["phase"] = "IN_THE_BALANCE"

    return situation


def get_spell_analysis(bowling_card: dict, current_bowler: str | None) -> dict:
    if not current_bowler:
        return {}
    entry = None
    for name, s in bowling_card.items():
        if name == current_bowler:
            entry = s
            break
    if not entry:
        return {}

    overs = float(entry.get("overs") or 0)
    runs = entry.get("runs") or 0
    wickets = entry.get("wickets") or 0
    if overs == 0:
        return {}

    economy = round(runs / overs, 2)
    if economy < 5 and wickets > 0:
        quality = "excellent"
    elif economy < 6:
        quality = "tight"
    elif economy < 8:
        quality = "decent"
    elif economy > 12:
        quality = "getting hammered"
    elif economy > 10:
        quality = "expensive"
    else:
        quality = "average"

    return {
        "economy": economy,
        "quality": quality,
        "wickets": wickets,
        "overs": overs,
        "runs": runs,
    }


def get_batter_phase(batter_stats: dict) -> dict:
    runs = batter_stats.get("runs") or 0
    balls = batter_stats.get("balls") or 0

    if balls == 0:
        return {"phase": "new_batter", "sr": 0, "runs": runs, "balls": balls}

    sr = round((runs / balls) * 100, 1)

    if balls <= 5:
        phase = "just_in"
    elif sr > 180:
        phase = "on_fire"
    elif sr > 140:
        phase = "aggressive"
    elif sr > 100:
        phase = "steady"
    elif sr > 70:
        phase = "anchoring"
    else:
        phase = "struggling"

    return {"phase": phase, "sr": sr, "runs": runs, "balls": balls}
