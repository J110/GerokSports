"""ConsistentReadTracker — replaces LiveMatchTracker.

Two consecutive frames showing the same value = confirmed truth.
Suspicious changes (big drops, halved stats) need 3 readings.
Bowler stats cross-checked against score delta to block info panel leaks.
"""
from __future__ import annotations

from eyes.cricket_logger import CricketLogger

log = CricketLogger("TRACK")


class ConsistentReadTracker:

    CONSENSUS_THRESHOLD = 4  # frames of consistent disagreement → reset
    # Cold-start consensus. The very first reading we get for a field
    # (`field not in self.confirmed`) must be SEEN ON N CONSECUTIVE
    # FRAMES with the SAME value before we accept it. This is the
    # primary defence against single-frame Scout hallucinations
    # ("GT 112-3 (12.5)" appearing on a frame where the actual match
    # is 0-0 — a coherent, physics-valid scorecard that no warm-mode
    # diff guard can catch because there's no prior state to compare
    # against). 3 frames is the sweet spot: catches one-frame
    # hallucinations cheaply (~1.5s of pipeline latency at 2fps), but
    # not so high that we lag the real first ball of an innings.
    INITIAL_CONSENSUS_FRAMES = 3

    # Fields exempt from cold-start consensus — these are inherently
    # initial-only or self-validating elsewhere. Adding everything to
    # the consensus path would block legitimate first reads of static
    # metadata and damage the cold-start UX without security gain.
    INITIAL_CONSENSUS_EXEMPT: set[str] = {
        # Add here any field that is metadata-only or already
        # protected by an upstream consensus mechanism (e.g. team
        # assignment uses team_confirm_count >= 3 in test_pipeline).
    }

    # --- Batter physics bounds (2026-04-24, Fix #1 for F24 row-swap) ---
    # Max legal single-delivery credit to a batter is a SIX (6 runs).
    # With a no-ball on the same delivery, the batter can still only
    # score the 6 off the bat — the +1 for the no-ball is an EXTRA,
    # credited to the team not the batter. However, Scout strip reads
    # occasionally lag by one frame relative to the ball-event stream,
    # so a legitimate "NB + six off the bat" can arrive as a +7 strip
    # delta during the reconciliation window. We give the cap one run
    # of slack to avoid false-rejecting that edge case.
    #
    # The old threshold here was +30, which is ~4× looser than cricket
    # physics allows. RCB-vs-GT 2026-04-24 F24 demonstrated the impact:
    # a Scout row-swap misread of Gill 2→16 (+14) sailed past the +30
    # gate, returned `suspicious=False`, and promoted via the
    # pending-match fast-confirm path once a same-frame second caller
    # re-proposed the same value. The downward half of the swap
    # (Sudharsan 37→21) was correctly rejected by the monotonic
    # guard, leaving state asymmetrically poisoned for ~80 seconds
    # until the fast-confirm path happened to accept a correcting
    # read. Parity monitor showed UI=23 vs Cricbuzz=9.
    #
    # Tightening to +7 forces any above-single-ball delta through
    # either the 4-frame reject-streak consensus (L198-263) or the
    # 3-frame pending-consensus (L274-333); neither can fire from a
    # single-frame scramble, which is the exact F24 class of bug.
    # Also symmetrises with the bowler-runs rule at L475 (also +7).
    BATTER_SINGLE_BALL_RUN_MAX = 6
    BATTER_NO_BALL_ADDITIONAL = 1

    def __init__(self):
        self.confirmed: dict = {}
        self.pending: dict = {}
        self.pending_counts: dict = {}
        self._prev_confirmed_score: int | None = None
        self._suspicious_this_frame: dict[str, set[str]] = {}
        self._last_frame: int = -1
        self._no_data_streak: int = 0
        self._post_gap_grace: int = 0
        self._reject_streak: dict[str, list] = {}  # field → [value, count]
        self._post_event_grace: int = 0  # frames of 1-read acceptance after ball event
        # Cold-start consensus bookkeeping: maps field → [proposed_value, count].
        # Reset to 1 if a different value arrives before INITIAL_CONSENSUS_FRAMES.
        self._initial_consensus: dict[str, list] = {}

    def update(self, field: str, value, frame_count: int = 0):
        """Submit a reading. Returns the confirmed value."""
        if value is None:
            self._no_data_streak += 1
            return self.confirmed.get(field)

        if self._no_data_streak >= 5:
            self._post_gap_grace = 3
            log.info(f"[GAP] {self._no_data_streak} frames without data "
                     f"— entering grace period for {field}")
        self._no_data_streak = 0

        if self._post_gap_grace > 0 and self._is_drs_pattern(field, value):
            old = self.confirmed.get(field)
            self.confirmed[field] = value
            self.pending.pop(field, None)
            self.pending_counts.pop(field, None)
            self._post_gap_grace -= 1
            if old != value:
                log.info(f"[DRS-GRACE] {field}: {old} → {value} "
                         f"(grace={self._post_gap_grace})")
            return value

        if frame_count != self._last_frame:
            self._flush_entity_suspicion()
            self._last_frame = frame_count

        current = self.confirmed.get(field)

        # Cold-start fast-path. If this field has never been confirmed,
        # bypass the entire warm-mode logic (suspicious / pending /
        # consensus-override paths) — those paths assume there is a
        # prior confirmed value to compare against. Route through
        # `_initial_consensus` instead, which requires
        # INITIAL_CONSENSUS_FRAMES of identical readings before
        # promoting to `self.confirmed`. Without this fast-path the
        # second-frame `pending`-confirm at the bottom commits the
        # value too early, which is the very hallucination
        # vulnerability we are trying to close.
        if field not in self.confirmed:
            if field in self.INITIAL_CONSENSUS_EXEMPT:
                self.confirmed[field] = value
                if field == "score":
                    self._prev_confirmed_score = None
                log.info(f"{field}: initial → {value} (exempt)")
                return value

            streak = self._initial_consensus.get(field)
            if streak and streak[0] == value:
                streak[1] += 1
                if streak[1] >= self.INITIAL_CONSENSUS_FRAMES:
                    self.confirmed[field] = value
                    self._initial_consensus.pop(field, None)
                    self.pending.pop(field, None)
                    self.pending_counts.pop(field, None)
                    if field == "score":
                        self._prev_confirmed_score = None
                    log.info(
                        f"{field}: initial → {value} "
                        f"(cold-start consensus "
                        f"{self.INITIAL_CONSENSUS_FRAMES}/"
                        f"{self.INITIAL_CONSENSUS_FRAMES})")
                    return value
                log.info(
                    f"{field}: initial proposed {value} "
                    f"({streak[1]}/{self.INITIAL_CONSENSUS_FRAMES}"
                    f" — waiting)")
                return None

            if streak and streak[0] != value:
                log.info(
                    f"{field}: initial proposal flipped "
                    f"{streak[0]} → {value} — resetting consensus "
                    f"to 1/{self.INITIAL_CONSENSUS_FRAMES}")
            self._initial_consensus[field] = [value, 1]
            return None

        if current == value:
            self.pending.pop(field, None)
            self.pending_counts.pop(field, None)
            return value

        # Fast-path: small natural cricket increments on batter stats
        # from the strip are almost always correct — confirm immediately
        if current is not None and self._is_natural_batter_increment(
                field, current, value):
            old = current
            self.confirmed[field] = value
            self.pending.pop(field, None)
            self.pending_counts.pop(field, None)
            self._reject_streak.pop(field, None)
            log.info(f"{field}: {old} → {value} (fast-confirm, "
                     f"natural increment F{frame_count})")
            return value

        # Fast-path: tight-delta bowler increments (Issue 3 fix,
        # 2026-04-21).  Wickets stepping +1 and overs stepping
        # exactly +0.1 are the unambiguous ball-by-ball shape of
        # bowler figures; neither value-space has room for an OCR
        # misread to masquerade as a legal increment (wickets 0..10
        # only ever tick once; overs are always N.0-N.5 within a
        # single over).  Confirm immediately so a just-seeded
        # "0-0(0.0)" card promotes on the next strip read after
        # the first delivery.  Runs are deliberately NOT in this
        # fast-path — a 0→3 runs jump matches both a triple and a
        # comparison-strip misread, so it still flows through the
        # pending path with score-delta cross-check (the same
        # reasoning we apply to the suspicious guards above).
        if current is not None and self._is_natural_bowler_increment(
                field, current, value):
            old = current
            self.confirmed[field] = value
            self.pending.pop(field, None)
            self.pending_counts.pop(field, None)
            self._reject_streak.pop(field, None)
            log.info(f"{field}: {old} → {value} (fast-confirm, "
                     f"natural bowler increment F{frame_count})")
            return value

        # Post-ball-event grace: accept non-suspicious changes on first read.
        # Batter/bowler/wickets change legitimately after a delivery;
        # frame_poisoned already blocks corruption upstream.
        if self._post_event_grace > 0 and current is not None:
            suspicious_check = self._is_suspicious(field, current, value)
            if not suspicious_check:
                old = current
                self.confirmed[field] = value
                self.pending.pop(field, None)
                self.pending_counts.pop(field, None)
                self._reject_streak.pop(field, None)
                self._post_event_grace -= 1
                if old != value:
                    log.info(f"{field}: {old} → {value} (post-event "
                             f"immediate, grace={self._post_event_grace})")
                return value

        suspicious = current is not None and self._is_suspicious(field, current, value)
        if suspicious:
            entity = ":".join(field.split(":")[:2])
            self._suspicious_this_frame.setdefault(entity, set()).add(field)

            # Consensus override: if extractor keeps proposing the same
            # "suspicious" value for N frames, the tracker is stale — reset
            streak = self._reject_streak.get(field)
            if streak and self._values_close(streak[0], value, field):
                streak[1] += 1
                streak[0] = value  # track latest proposed value
                if streak[1] >= self.CONSENSUS_THRESHOLD:
                    # Couple batter runs+balls: if runs wants to regress
                    # but balls hasn't changed, the extractor is stale.
                    try:
                        _old_f, _new_f = float(current), float(value)
                    except (ValueError, TypeError):
                        _old_f, _new_f = 0.0, 0.0
                    if (field.startswith("bat:") and field.endswith(":runs")
                            and _new_f < _old_f):
                        balls_field = field.replace(":runs", ":balls")
                        cur_balls = self.confirmed.get(balls_field)
                        if cur_balls is not None and float(cur_balls) > 2:
                            log.info(
                                f"[CONSENSUS-BLOCKED] {field}: "
                                f"{current}→{value} — balls still at "
                                f"{cur_balls}, runs regression impossible")
                            self._reject_streak.pop(field, None)
                            return current

                    # Same logic for bowler stats: a bowler's runs,
                    # wickets, and overs CANNOT regress mid-spell.
                    # Without this guard, repeated mis-reads during
                    # ad-breaks / replays / dead-time frames (where
                    # scout reads `0-0 (0.0)`) silently overwrite
                    # the real bowler stats after 4 frames, e.g.
                    # KKR-vs-RR 2026-04-19 F373 18:58:55:
                    #   `[CONSENSUS] bowl:Jofra Archer:runs:
                    #     16 → 0 (extractor agreed 4 frames)`
                    #   `[CONSENSUS] bowl:Jofra Archer:wickets:
                    #     1 → 0 (extractor agreed 4 frames)`
                    #   `[CONSENSUS] bowl:Jofra Archer:overs:
                    #     2.1 → 0.0 (extractor agreed 4 frames)`
                    # which then leaks into the UI as a stale
                    # `Bowler 0-0 (0.0)` line / a different-bowler
                    # broadcast for the next ~30s until a real ball
                    # event re-syncs the card.  A bowler's stats
                    # only legitimately reset when the bowler's
                    # NAME changes (handled separately by the
                    # bowling card swap in scoreboard.update_bowler);
                    # never within a single spell.
                    if (field.startswith("bowl:")
                            and (field.endswith(":runs")
                                 or field.endswith(":wickets")
                                 or field.endswith(":overs"))
                            and _new_f < _old_f):
                        log.info(
                            f"[CONSENSUS-BLOCKED] {field}: "
                            f"{current}→{value} — bowler stats "
                            f"cannot regress mid-spell (likely "
                            f"dead-time misread)")
                        self._reject_streak.pop(field, None)
                        return current

                    # Match-level overs cannot regress within an
                    # innings — the only legitimate reset is via
                    # `set_innings_2()`, which clears `confirmed`
                    # wholesale rather than going through this
                    # consensus path.  Without this guard, four
                    # consecutive `(POWERPLAY)`-misparse frames
                    # silently overwrite a real over-7 reading
                    # with 0.5 and poison every dependent field
                    # (RR vs SRH 2026-04-25 F3120: `(POWERPLAY)`
                    # text → `[CONSENSUS] overs: 6.0 → 0.5
                    # (extractor agreed 4 frames)` → cascading
                    # batter/bowler/this_over corruption until
                    # process restart).  Mirrors the bowler /
                    # batter regression guards above.
                    if field == "overs" and _new_f < _old_f:
                        log.info(
                            f"[CONSENSUS-BLOCKED] {field}: "
                            f"{current}→{value} — match overs "
                            f"cannot regress within an innings "
                            f"(likely dead-time / placeholder-"
                            f"graphic misread)")
                        self._reject_streak.pop(field, None)
                        return current

                    old = current
                    self.confirmed[field] = value
                    self.pending.pop(field, None)
                    self.pending_counts.pop(field, None)
                    self._reject_streak.pop(field, None)
                    if field == "score":
                        self._prev_confirmed_score = old
                    log.info(f"[CONSENSUS] {field}: {old} → {value} "
                             f"(extractor agreed {streak[1]} frames)")
                    return value
            else:
                self._reject_streak[field] = [value, 1]
        else:
            self._reject_streak.pop(field, None)

        pending = self.pending.get(field)

        if pending is not None:
            pending_value, _ = pending

            if pending_value == value:
                if suspicious:
                    count = self.pending_counts.get(field, 1) + 1
                    self.pending_counts[field] = count
                    log.info(f"[SUSPICIOUS] {field}: {current}→{value} "
                             f"count={count}/3")
                    if count < 3:
                        return current

                    # Regression guards must apply on the pending-consensus
                    # promotion path too, not just reject-streak (2026-04-21).
                    # Without this, a repeat "suspicious" read that survived
                    # Path 1's CONSENSUS-BLOCKED ends up promoted here,
                    # silently regressing bowler/batter figures.  Observed
                    # live (SRH-vs-DC F113):
                    #   F111 [CONSENSUS-BLOCKED] bowl:Eshan Malinga:runs:
                    #         26→22 (Path 1 pops streak, correctly blocks)
                    #   F113 [SUSPICIOUS] …:runs: 26→22 count=3/3
                    #   F113 bowl:Eshan Malinga:runs: 26 → 22 (confirmed)
                    # Parity monitor confirmed CB had Malinga at 3-23 while
                    # UI ended up at 3-28/3-22 due to this drift.
                    try:
                        _old_f, _new_f = float(current), float(value)
                    except (ValueError, TypeError):
                        _old_f, _new_f = 0.0, 0.0
                    if (field.startswith("bat:") and field.endswith(":runs")
                            and _new_f < _old_f):
                        balls_field = field.replace(":runs", ":balls")
                        cur_balls = self.confirmed.get(balls_field)
                        if cur_balls is not None and float(cur_balls) > 2:
                            log.info(
                                f"[CONSENSUS-BLOCKED] {field}: "
                                f"{current}→{value} — balls still at "
                                f"{cur_balls}, runs regression impossible "
                                f"(pending-path)")
                            self.pending.pop(field, None)
                            self.pending_counts.pop(field, None)
                            return current
                    if (field.startswith("bowl:")
                            and (field.endswith(":runs")
                                 or field.endswith(":wickets")
                                 or field.endswith(":overs"))
                            and _new_f < _old_f):
                        log.info(
                            f"[CONSENSUS-BLOCKED] {field}: "
                            f"{current}→{value} — bowler stats cannot "
                            f"regress mid-spell (pending-path)")
                        self.pending.pop(field, None)
                        self.pending_counts.pop(field, None)
                        return current

                    # Match-level overs regression guard, pending
                    # path — analogue of the consensus-override
                    # guard above.  Without this, the same
                    # `(POWERPLAY)`-misparse pattern can promote
                    # via the SUSPICIOUS-count=3/3 path instead of
                    # the reject-streak path and still poison
                    # confirmed state.
                    if field == "overs" and _new_f < _old_f:
                        log.info(
                            f"[CONSENSUS-BLOCKED] {field}: "
                            f"{current}→{value} — match overs cannot "
                            f"regress within an innings "
                            f"(pending-path)")
                        self.pending.pop(field, None)
                        self.pending_counts.pop(field, None)
                        return current

                old = current
                self.confirmed[field] = value
                self.pending.pop(field, None)
                self.pending_counts.pop(field, None)
                if field == "score" and old != value:
                    self._prev_confirmed_score = old
                if old != value:
                    log.info(f"{field}: {old} → {value} (confirmed F{frame_count})")
                return value
            else:
                self.pending[field] = (value, frame_count)
                self.pending_counts[field] = 0
                return current
        else:
            self.pending[field] = (value, frame_count)
            self.pending_counts[field] = 0
            return current

    def _flush_entity_suspicion(self):
        """If 2+ fields from the same entity were suspicious this frame,
        escalate ALL pending fields from that entity to need 3 readings."""
        for entity, flagged in self._suspicious_this_frame.items():
            if len(flagged) >= 2:
                escalated = []
                for f in list(self.pending.keys()):
                    if f.startswith(entity) and f not in flagged:
                        old_count = self.pending_counts.get(f, 0)
                        self.pending_counts[f] = max(old_count, 2)
                        escalated.append(f)
                if escalated:
                    log.info(f"[ENTITY-SUSPICIOUS] {entity}: {len(flagged)} "
                             f"fields suspicious → escalating {escalated}")
        self._suspicious_this_frame = {}

    def _is_suspicious(self, field: str, old, new) -> bool:
        try:
            old_f, new_f = float(old), float(new)
        except (ValueError, TypeError):
            return False

        # --- Score ---
        # ANY downward drop is suspicious. Score in T20 cricket never
        # decreases outside two narrowly-scoped paths (both handled
        # elsewhere): a DRS overturn (caught by `_is_drs_pattern` in
        # post-gap grace) and an innings change (handled by the
        # innings-transition path which fully resets state). A -1/-2
        # OCR misread of the team-score digit during normal play used
        # to slip past this guard's old `>5` threshold and then
        # fabricate a phantom EXTRA on the next frame when the score
        # snapped back up. Treat every regression as suspicious so it
        # has to clear 4-frame consensus before being accepted.
        if field == "score" and new_f < old_f:
            log.info(f"[SUSPICIOUS] score: {old}→{new} "
                     f"(any decrease is suspicious in normal play)")
            return True
        # Large upward jumps are suspicious too.  Even after a long ad
        # break the pipeline catches up via repeated scoreboard reads;
        # a single +30 jump in one update means OCR noise (a sponsor
        # overlay number, a different innings's score graphic, two
        # numbers blending during a transition).  Require 3-frame
        # consensus before we accept it.
        if field == "score" and new_f - old_f > 30:
            log.info(f"[SUSPICIOUS] score: {old}→{new} "
                     f"(jump +{new_f - old_f:.0f} too large)")
            return True

        # --- Match overs: never go backwards ---
        if field == "overs":
            if new_f < old_f:
                log.info(f"[SUSPICIOUS] overs: {old}→{new} (backwards)")
                return True

        # --- Wickets (team) ---
        if field == "wickets" and new_f < old_f:
            return True

        # --- Batter runs ---
        if field.startswith("bat:") and field.endswith(":runs"):
            balls_field = field.replace(":runs", ":balls")
            balls = self.confirmed.get(balls_field)
            # STALE-0 override (hardened 2026-04-21, Fix A.3):
            #   Previously we accepted ANY non-zero runs value on a
            #   batter whose confirmed state was 0(0) after 3+ overs,
            #   reasoning "the batter clearly isn't at 0(0), this is
            #   a stale zero and we should unblock".  That reasoning
            #   is right in the common case but it also accepts
            #   comparison-overlay and career-summary graphics
            #   verbatim — e.g. the "Klaasen last 5 innings: 51, 43,
            #   62…" overlay gets ingested as "Klaasen is on 51
            #   RIGHT NOW" because we bypass the suspicion check on
            #   the first read.  The result: a locked-in wrong score
            #   that regression rejection then protects against
            #   correction.
            #
            #   New rule: fast-accept 0→X ONLY when X fits a single
            #   delivery (≤ 6 runs).  Any bigger jump MUST pass the
            #   normal 3-frame consensus path — which filters out
            #   one-off overlay reads while still converging on
            #   genuine catch-up values within a few seconds.
            if balls is not None and float(balls) == 0 and new_f > 0:
                if old_f == 0 and new_f <= 6:
                    log.info(
                        f"[STALE-0-SMALL] {field}: 0→{new_f} — "
                        f"fast-accepting (fits a single delivery)")
                    return False
                log.info(
                    f"[SUSPICIOUS] {field}: {old}→{new} while "
                    f"balls=0 — deferring to consensus "
                    f"(comparison-overlay protection)")
                return True
            # Runs should never decrease within an innings — batter stats
            # are strictly monotonic. Any drop (even by 1) is an OCR
            # misread (tightened 2026-04-21; the old `> 1` threshold
            # let small regressions promote via post-event grace).
            if new_f < old_f:
                log.info(f"[SUSPICIOUS] {field}: {old}→{new} "
                         f"(runs dropped by {old_f - new_f})")
                return True
            if old_f > 10 and new_f < old_f * 0.5:
                return True
            # Upward physics cap — a batter cannot score more than a
            # SIX off a single legal delivery, with one run of slack
            # for the NB+six strip-lag edge case. See the
            # BATTER_SINGLE_BALL_RUN_MAX comment at the top of the
            # class for the full derivation. Any jump above this cap
            # is routed into the normal 3/4-frame consensus paths; a
            # single-frame scramble cannot survive.
            _bat_cap = (self.BATTER_SINGLE_BALL_RUN_MAX
                        + self.BATTER_NO_BALL_ADDITIONAL)
            if new_f - old_f > _bat_cap:
                log.info(
                    f"[BAT-PHYSICS] {field}: {old}→{new} "
                    f"(+{new_f - old_f:.0f} exceeds single-ball "
                    f"cap {_bat_cap}) — routing to consensus")
                return True

        # --- Batter balls ---
        if field.startswith("bat:") and field.endswith(":balls"):
            # Batter balls are strictly monotonic within an innings
            # (tightened 2026-04-21 to reject any downward drift).
            if new_f < old_f:
                log.info(f"[SUSPICIOUS] {field}: {old}→{new} "
                         f"(balls dropped by {old_f - new_f})")
                return True
            if new_f > old_f + 20:
                return True

        # --- Bowler runs: cross-check vs score delta ---
        if field.startswith("bowl:") and field.endswith(":runs"):
            bowler_name = field.split(":")[1]
            bowl_wkts = self.confirmed.get(f"bowl:{bowler_name}:wickets")
            if bowl_wkts is not None and new_f < float(bowl_wkts):
                log.info(f"[SUSPICIOUS] {field}: runs={new_f} < "
                         f"wickets={bowl_wkts} — likely swapped")
                return True
            runs_delta = new_f - old_f
            score = self.confirmed.get("score")
            if score is not None and new_f > float(score):
                return True
            if self._prev_confirmed_score is not None and score is not None:
                score_delta = float(score) - float(self._prev_confirmed_score)
                if runs_delta > score_delta + 2:
                    return True
            if runs_delta > 7:
                return True
            # Any drop in bowler runs is suspicious — a spell's runs are
            # strictly monotonically non-decreasing (2026-04-21). The old
            # `new_f < old_f - 3` threshold let small regressions (e.g.
            # Harsh Dubey 5→4, Malinga 20→18) slip through the post-event
            # grace path and corrupt the confirmed figures. Within a
            # spell runs can only go up; between spells `force_set` resets
            # the tracker key, so there's no legitimate downward case here.
            if new_f < old_f:
                return True

        # --- Bowler wickets: max +1 per frame, never decrease ---
        if field.startswith("bowl:") and field.endswith(":wickets"):
            bowler_name = field.split(":")[1]
            bowl_runs = self.confirmed.get(f"bowl:{bowler_name}:runs")
            if bowl_runs is not None and new_f > float(bowl_runs):
                log.info(f"[SUSPICIOUS] {field}: wickets={new_f} > "
                         f"runs={bowl_runs} — likely swapped")
                return True
            if new_f > old_f + 1:
                return True
            if new_f < old_f:
                return True

        # --- Bowler overs: cap 4.0, never decrease ---
        # Allow up to +1.0 jump (full over) for ad-break gaps,
        # but block career-stat leaks (e.g. 0.4→3.0)
        if field.startswith("bowl:") and field.endswith(":overs"):
            if new_f > 4.0:
                return True
            if new_f > old_f + 1.0:
                return True
            if new_f < old_f:
                return True

        return False

    @staticmethod
    def _is_natural_batter_increment(field: str, old, new) -> bool:
        """Small positive batter increments from the broadcast strip
        are ground truth — no need to wait for a second read."""
        try:
            old_f, new_f = float(old), float(new)
        except (ValueError, TypeError):
            return False
        delta = new_f - old_f
        if field.startswith("bat:") and field.endswith(":runs"):
            return 1 <= delta <= 6
        if field.startswith("bat:") and field.endswith(":balls"):
            return delta == 1
        return False

    @staticmethod
    def _is_natural_bowler_increment(field: str, old, new) -> bool:
        """Tight-delta bowler increments whose value-space rules out
        OCR collisions — wickets can only step +1 (a single wicket
        on the ball), overs can only step +0.1 within a spell.
        Runs are intentionally excluded (see caller comment)."""
        try:
            old_f, new_f = float(old), float(new)
        except (ValueError, TypeError):
            return False
        if field.startswith("bowl:") and field.endswith(":wickets"):
            return new_f - old_f == 1
        if field.startswith("bowl:") and field.endswith(":overs"):
            delta = new_f - old_f
            return 0.09 <= delta <= 0.11
        return False

    @staticmethod
    def _values_close(a, b, field: str) -> bool:
        """Check if two rejected values are 'close enough' to count as
        the same consensus signal (e.g. score 82 and 83 both disagree
        with the tracker's 239)."""
        try:
            fa, fb = float(a), float(b)
        except (ValueError, TypeError):
            return a == b
        if field == "score":
            return abs(fa - fb) <= 5
        if field == "overs":
            return abs(fa - fb) <= 0.3
        if field == "wickets":
            return abs(fa - fb) <= 1
        return abs(fa - fb) <= 2

    def _is_drs_pattern(self, field: str, value) -> bool:
        """Check if this looks like a DRS outcome change."""
        old = self.confirmed.get(field)
        if old is None or value is None:
            return False
        try:
            old_f, new_f = float(old), float(value)
        except (ValueError, TypeError):
            return False
        if field == "overs" and 0 < old_f - new_f <= 0.1:
            return True
        if field == "wickets" and old_f - new_f == 1:
            return True
        if field == "score" and abs(new_f - old_f) <= 2:
            return True
        return False

    def on_ball_event(self):
        """After a ball event, accept changes on first read for 2 frames.
        The frame_poisoned flag already blocks corrupted data upstream,
        so consensus can be safely relaxed here."""
        self._post_event_grace = 2

    def force_set(self, field: str, value):
        """Override without consistency check. Used by cricket checks."""
        self.confirmed[field] = value
        self.pending.pop(field, None)
        self._initial_consensus.pop(field, None)

    def reset_overs_consensus(self) -> None:
        """P0-B: drop innings-1 overs floor from consensus so innings-2
        reads (0.x) are not rejected as regressions vs e.g. 20.0."""
        for _k in ("overs",):
            self.confirmed.pop(_k, None)
            self.pending.pop(_k, None)
            self.pending_counts.pop(_k, None)
            self._initial_consensus.pop(_k, None)
            self._reject_streak.pop(_k, None)

    def get(self, field: str, default=None):
        return self.confirmed.get(field, default)

    def get_all_batters(self) -> dict:
        batters: dict = {}
        for field, value in self.confirmed.items():
            if field.startswith("bat:"):
                parts = field.split(":")
                if len(parts) == 3:
                    _, name, stat = parts
                    batters.setdefault(name, {})[stat] = value
        return batters

    def get_all_bowlers(self) -> dict:
        bowlers: dict = {}
        for field, value in self.confirmed.items():
            if field.startswith("bowl:"):
                parts = field.split(":")
                if len(parts) == 3:
                    _, name, stat = parts
                    bowlers.setdefault(name, {})[stat] = value
        return bowlers
