"""Cricket checker — enforces impossible-state rules AFTER tracker confirms.

Simplified from old CricketInvariantChecker. Removed harmful batter scaling
(old invariants 4 & 5) that caused stat oscillation.
"""
from __future__ import annotations

from eyes.cricket_logger import CricketLogger

log = CricketLogger("CRICKET")


class CricketChecker:

    def __init__(self) -> None:
        self._prev_active: list[str] = []
        self._prev_wickets: int = 0
        self._wickets_initialized: bool = False
        self._wickets_confirmed: bool = False
        self._batter_changed_recently: bool = False

    def reset(self) -> None:
        self._prev_active = []
        self._prev_wickets = 0
        self._wickets_initialized = False
        self._wickets_confirmed = False
        self._batter_changed_recently = False

    def check(self, state: dict, batting_card: dict, bowling_card: dict,
              this_over: list, tracker) -> list[str]:
        """Run all checks. Correct violations in-place. Return corrections."""
        corrections: list[str] = []

        score = int(state.get("score") or 0)
        wickets = int(state.get("wickets") or 0)
        overs = float(state.get("overs") or "0")

        active = [k for k, v in batting_card.items()
                  if v.get("status") == "batting"]
        dismissed = [k for k, v in batting_card.items()
                     if v.get("status") == "out"]

        batter_set_changed = (set(active) != set(self._prev_active)
                              and len(self._prev_active) > 0)
        if batter_set_changed:
            self._batter_changed_recently = True
            log.info(f"Batter swap detected: "
                     f"{self._prev_active} → {active}")

        # CHECK 1: Wickets can't increase if same 2 batters active
        # Phase 1 (not confirmed): accept extractor wickets freely until
        # we've seen a real batter-change-confirmed wicket transition.
        # Phase 2 (confirmed): require batter swap for wicket increases.
        if self._wickets_initialized:
            if wickets > self._prev_wickets:
                if batter_set_changed or self._batter_changed_recently:
                    self._wickets_confirmed = True
                    log.info(f"Wicket {self._prev_wickets}→{wickets} "
                             f"accepted (batter swap — guard now active)")
                    self._batter_changed_recently = False
                elif not self._wickets_confirmed:
                    log.info(f"Wicket {self._prev_wickets}→{wickets} "
                             f"accepted (mid-innings join, guard inactive)")
                elif len(active) == 2 and set(active) == set(self._prev_active):
                    corrections.append(
                        f"Wicket {self._prev_wickets}→{wickets} but same "
                        f"batters {active} — reverting")
                    state["wickets"] = self._prev_wickets
                    tracker.force_set("wickets", self._prev_wickets)
                    wickets = self._prev_wickets
        else:
            if wickets > 0:
                self._wickets_initialized = True

        self._prev_active = active.copy()
        self._prev_wickets = wickets

        # CHECK 3: Bowler overs can't exceed 4.0 in T20
        for name, card in bowling_card.items():
            bowl_ov = float(card.get("overs") or "0")
            if bowl_ov > 4.0:
                corrections.append(
                    f"Bowler {name} overs {bowl_ov} > 4.0 — clearing")
                card["overs"] = None
                tracker.force_set(f"bowl:{name}:overs", None)

        # CHECK 4: Bowler runs can't exceed team score
        for name, card in bowling_card.items():
            bowl_runs = card.get("runs") or 0
            if bowl_runs > score and score > 0:
                corrections.append(
                    f"Bowler {name} runs {bowl_runs} > score {score} — "
                    f"capping")
                card["runs"] = score
                tracker.force_set(f"bowl:{name}:runs", score)

        # CHECK 5: This-over legal balls ≤ overs sub-ball count
        # Only trim '?' placeholder tokens — those are speculative
        # FLOOR-pads inserted by ThisOverManager.get_display() to match
        # team_overs. Real observations (W, numbers, dots) are never
        # trimmed here; they are managed exclusively by check_over_change
        # archival and on_ball_event append (the rollback path can
        # restore them and we must not destroy them again).
        # Trim '?' placeholders from the END (most recently added),
        # not the front (which would destroy the earliest real ball
        # like a first-ball wicket).
        if this_over:
            sub = round((overs % 1) * 10)
            if sub > 0:
                legal = [x for x in this_over
                         if str(x).lower() not in ("wd", "nb")]
                trimmed = 0
                while len(legal) > sub and this_over:
                    # Find rightmost '?' placeholder to remove.
                    idx = next(
                        (i for i in range(len(this_over) - 1, -1, -1)
                         if this_over[i] == "?"),
                        None)
                    if idx is None:
                        # No placeholders left to safely remove.
                        # Real observations exceed the over count —
                        # leave them and surface a warning instead.
                        break
                    this_over.pop(idx)
                    trimmed += 1
                    legal = [x for x in this_over
                             if str(x).lower() not in ("wd", "nb")]
                if trimmed > 0:
                    corrections.append(
                        f"This-over trimmed {trimmed} '?' placeholder"
                        f"{'s' if trimmed != 1 else ''} to match "
                        f"{sub} legal balls")

        if corrections:
            for c in corrections:
                log.info(c)

        return corrections
