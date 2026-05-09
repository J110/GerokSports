"""Micro intelligence accumulator — subtle observations from LLM over many frames."""
from __future__ import annotations

import time
from collections import defaultdict

from eyes.cricket_logger import CricketLogger

log = CricketLogger("MICRO")


class MicroAnalysis:
    """Accumulates micro-observations the LLM extracts between deliveries.

    Tracks per-bowler (run-up, patterns), per-batter (guard, practice shots,
    scoring zones), field evolution, pitch state, conditions, keeper.
    """

    def __init__(self):
        self.bowler_data: dict[str, dict] = defaultdict(lambda: defaultdict(list))
        self.batter_data: dict[str, dict] = defaultdict(lambda: defaultdict(list))
        self.captain_events: list[dict] = []
        self.dugout_observations: list[dict] = []
        self.keeper_data: dict[str, list] = defaultdict(list)
        self.pitch_timeline: list[dict] = []
        self.dew_onset: int | None = None
        self.umpire_signals: list[dict] = []
        self.conditions_timeline: list[dict] = []

    def on_extraction(self, extraction: dict, frame_number: int):
        """Process all micro-observations from a single LLM extraction."""
        micro = extraction.get("micro_observations", {})
        action = extraction.get("action", {})
        players = extraction.get("players", {})
        conditions = extraction.get("conditions", {})
        field = extraction.get("field", {})
        scoreboard = extraction.get("scoreboard", {})

        if not isinstance(micro, dict):
            micro = {}

        bowler_name = None
        if isinstance(scoreboard, dict):
            bowler_info = scoreboard.get("bowler", {})
            if isinstance(bowler_info, dict):
                bowler_name = bowler_info.get("name")

        # Bowler run-up tracking
        run_up = micro.get("bowler_run_up")
        if run_up and run_up not in ("null", None) and bowler_name:
            obs = self.bowler_data[bowler_name]["run_up_observations"]
            obs.append({
                "frame": frame_number,
                "observation": run_up,
                "over": scoreboard.get("overs") if isinstance(scoreboard, dict) else None,
            })
            log.info(f"Bowler {bowler_name}: run-up={run_up} ({len(obs)} observation this over)")
            if len(obs) >= 4 and sum(1 for o in obs[-4:] if o["observation"] == "shorter") >= 3:
                log.warn(f"Bowler {bowler_name} run-up shorter in 3 of last 4 overs — possible fatigue")

        # Batter guard tracking
        guard = micro.get("batter_guard")
        if guard and guard not in ("null", None):
            batter = self._get_current_striker(extraction)
            if batter:
                guards = self.batter_data[batter]["guard_observations"]
                prev_guard = guards[-1]["guard"] if guards else None
                guards.append({
                    "frame": frame_number,
                    "guard": guard,
                })
                overs = scoreboard.get("overs") if isinstance(scoreboard, dict) else "?"
                if prev_guard and prev_guard != guard:
                    log.info(f"Batter {batter}: guard={guard} (changed from {prev_guard} at over {overs})")
                else:
                    log.info(f"Batter {batter}: guard={guard}")

        # Practice shot tracking
        practice = micro.get("batter_practice_shot")
        if practice and practice not in ("null", None):
            batter = self._get_current_striker(extraction)
            if batter:
                self.batter_data[batter]["practice_shots"].append({
                    "frame": frame_number,
                    "shot": practice,
                })
                log.info(f"Batter {batter}: practicing {practice} between deliveries")

        # Batter looking at field
        looking = micro.get("batter_looking_at_field")
        if looking and looking not in ("null", None):
            batter = self._get_current_striker(extraction)
            if batter:
                self.batter_data[batter]["looking_at"].append({
                    "frame": frame_number,
                    "direction": looking,
                })

        # Captain conversations
        captain_talk = players.get("captain_talking_to") if isinstance(players, dict) else None
        if captain_talk and captain_talk not in ("null", None):
            overs = scoreboard.get("overs") if isinstance(scoreboard, dict) else "?"
            self.captain_events.append({
                "frame": frame_number,
                "talking_to": captain_talk,
                "overs": overs,
            })
            log.info(f"Captain talking to {captain_talk} before over {overs}")

        # Padded up in dugout
        if isinstance(players, dict) and players.get("padded_up_in_dugout"):
            self.dugout_observations.append({
                "frame": frame_number,
                "padded_up": True,
                "timestamp": time.time(),
            })
            log.info("Padded up player spotted in dugout")

        # Keeper position per bowler
        keeper_pos = field.get("keeper_position") if isinstance(field, dict) else None
        if keeper_pos and keeper_pos not in ("null", None) and bowler_name:
            self.keeper_data[bowler_name].append(keeper_pos)
            log.info(f"Keeper moved to {keeper_pos} position for {bowler_name}")

        # Pitch appearance
        pitch = conditions.get("pitch_appearance") if isinstance(conditions, dict) else None
        if pitch and pitch not in ("null", None):
            self.pitch_timeline.append({
                "frame": frame_number,
                "appearance": pitch,
            })
            count = len(self.pitch_timeline)
            log.info(f"Pitch: showing {pitch} ({count} observation{'s' if count > 1 else ''})")

        # Dew onset detection
        dew = conditions.get("dew_visible") if isinstance(conditions, dict) else None
        if dew and self.dew_onset is None:
            self.dew_onset = frame_number

        # Umpire signals
        signal = players.get("umpire_signal") if isinstance(players, dict) else None
        if signal and signal not in ("null", None):
            self.umpire_signals.append({
                "frame": frame_number,
                "signal": signal,
            })

        # Conditions snapshot
        if isinstance(conditions, dict) and any(
            conditions.get(k) not in (None, "null") for k in conditions
        ):
            self.conditions_timeline.append({
                "frame": frame_number,
                "conditions": {k: v for k, v in conditions.items() if v not in (None, "null")},
            })

    def get_insights(self) -> list[dict]:
        """Generate insights from accumulated micro-observations."""
        insights = []
        _log_insights = True

        # Bowler fatigue detection
        for bowler, data in self.bowler_data.items():
            run_ups = data.get("run_up_observations", [])
            if len(run_ups) >= 6:
                recent = [r["observation"] for r in run_ups[-6:]]
                if recent.count("shorter") >= 3:
                    insights.append({
                        "type": "bowler_fatigue",
                        "player": bowler,
                        "detail": "Run-up noticeably shorter in recent overs",
                    })

        # Batter guard changes
        for batter, data in self.batter_data.items():
            guards = data.get("guard_observations", [])
            if len(guards) >= 4:
                mid = len(guards) // 2
                early_guards = [g["guard"] for g in guards[:mid]]
                late_guards = [g["guard"] for g in guards[mid:]]
                if early_guards and late_guards and early_guards[-1] != late_guards[-1]:
                    insights.append({
                        "type": "guard_change",
                        "player": batter,
                        "detail": f"Changed from {early_guards[-1]} to {late_guards[-1]}",
                    })

            # Practice shot intent signals
            practice = data.get("practice_shots", [])
            if len(practice) >= 2:
                recent = practice[-2:]
                insights.append({
                    "type": "intent_signal",
                    "player": batter,
                    "detail": f"Practicing {recent[-1]['shot']} between deliveries",
                })

            # Looking at field direction
            looking = data.get("looking_at", [])
            if len(looking) >= 3:
                recent = [l["direction"] for l in looking[-3:]]
                if len(set(recent)) == 1:
                    insights.append({
                        "type": "targeting",
                        "player": batter,
                        "detail": f"Consistently looking at {recent[0]}",
                    })

        # Captain activity
        if len(self.captain_events) >= 3:
            recent = self.captain_events[-3:]
            if all(e["talking_to"] == "bowler" for e in recent):
                insights.append({
                    "type": "captain_concern",
                    "detail": "Captain in frequent conversation with bowler",
                })

        # Pitch deterioration
        if len(self.pitch_timeline) >= 4:
            early = self.pitch_timeline[:len(self.pitch_timeline) // 2]
            late = self.pitch_timeline[len(self.pitch_timeline) // 2:]
            early_set = set(p["appearance"] for p in early)
            late_set = set(p["appearance"] for p in late)
            if early_set != late_set:
                insights.append({
                    "type": "pitch_change",
                    "detail": f"Pitch changed from {early_set} to {late_set}",
                })

        # Keeper positioning patterns
        for bowler, positions in self.keeper_data.items():
            if len(positions) >= 3:
                unique = set(positions[-3:])
                if len(unique) == 1:
                    insights.append({
                        "type": "keeper_pattern",
                        "player": bowler,
                        "detail": f"Keeper consistently {positions[-1]} for {bowler}",
                    })

        for i in insights:
            player = i.get("player", "")
            prefix = f"{player} — " if player else ""
            log.insight(f"{prefix}{i['detail']}")

        return insights

    def get_summary(self) -> dict:
        return {
            "bowlers_tracked": list(self.bowler_data.keys()),
            "batters_tracked": list(self.batter_data.keys()),
            "captain_events": len(self.captain_events),
            "dugout_observations": len(self.dugout_observations),
            "pitch_observations": len(self.pitch_timeline),
            "dew_onset_frame": self.dew_onset,
            "umpire_signals": len(self.umpire_signals),
            "insights": self.get_insights(),
        }

    @staticmethod
    def _get_current_striker(extraction: dict) -> str | None:
        sb = extraction.get("scoreboard", {})
        if not isinstance(sb, dict):
            return None
        for key in ("batter_1", "batter_2"):
            batter = sb.get(key, {})
            if isinstance(batter, dict) and batter.get("is_striker") and batter.get("name"):
                return batter["name"]
        b1 = sb.get("batter_1", {})
        if isinstance(b1, dict) and b1.get("name"):
            return b1["name"]
        return None

    def reset(self):
        self.__init__()
