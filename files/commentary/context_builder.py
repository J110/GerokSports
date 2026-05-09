"""Builds match context strings for LLM commentary calls."""
from __future__ import annotations


class ContextBuilder:
    def __init__(self):
        self.recent_commentary: list[str] = []
        self.dot_ball_streak: int = 0
        self.boundary_streak: int = 0

    def build_ball_context(self, state: dict, ball_event: dict) -> dict:
        sc = state.get("scorecard", {})
        match = state.get("match", {})

        ctx: dict = {
            "ball": ball_event,
            "score": f"{sc.get('score', 0)}/{sc.get('wickets', 0)} ({sc.get('overs', '0')})",
            "batting_team": sc.get("batting_team", "?"),
            "bowling_team": sc.get("bowling_team", "?"),
            "innings": match.get("innings", 1),
            # Top-level fields from the WS payload that format_for_prompt
            # needs but which live on `state`, not inside scorecard/match.
            # Without these, format_for_prompt's WICKET branch crashed
            # with NameError: name 'state' is not defined whenever a
            # wicket fired.
            "dismissal_mode": state.get("dismissal_mode", ""),
        }
        if state.get("venue"):
            ctx["venue"] = state["venue"]
        if state.get("match_info"):
            ctx["match_info"] = state["match_info"]

        _striker_override = state.get("striker_this_ball")
        _is_wicket = ball_event.get("type") == "WICKET"
        batting_card = state.get("batting_card", [])
        if isinstance(batting_card, list):
            for b in batting_card:
                _status = b.get("status", "")
                if _status == "batting":
                    pass
                elif (_status == "out" and _is_wicket
                      and _striker_override
                      and b.get("name", "") == _striker_override):
                    pass
                else:
                    continue
                _is_striker = b.get("is_striker")
                if _striker_override:
                    _is_striker = (b.get("name", "") == _striker_override)
                if _is_striker:
                    ctx["striker"] = b.get("name", "?")
                    ctx["striker_stats"] = (
                        f"{b.get('runs', 0)}({b.get('balls', 0)}) "
                        f"SR {b.get('sr', '-')}")
                else:
                    ctx["non"] = b.get("name", "?")
                    ctx["non_stats"] = (
                        f"{b.get('runs', 0)}({b.get('balls', 0)}) "
                        f"SR {b.get('sr', '-')}")

        bowler = sc.get("current_bowler")
        if bowler:
            ctx["bowler"] = bowler
        bowling_card = state.get("bowling_card", [])
        if isinstance(bowling_card, list):
            for b in bowling_card:
                if b.get("is_current"):
                    ctx["bowler_stats"] = (
                        f"{b.get('wickets', 0)}-{b.get('runs', 0)} "
                        f"({b.get('overs', '0')})")
                    ctx["bowler_economy"] = b.get("economy")
                    break

        if match.get("innings") == 2 and match.get("target"):
            target = int(match["target"])
            score_val = sc.get("score") or 0
            runs_needed = target - score_val
            overs_f = float(sc.get("overs") or "0")
            balls_rem = 120 - (int(overs_f) * 6 + round((overs_f % 1) * 10))
            rrr = (runs_needed / balls_rem * 6) if balls_rem > 0 else 0
            ctx["chase"] = {
                "target": target,
                "runs_needed": runs_needed,
                "balls_remaining": balls_rem,
                "required_rate": round(rrr, 2),
            }

        ctx["this_over"] = state.get("this_over", [])
        ctx["this_over_runs"] = sum(
            int(x) for x in ctx["this_over"] if isinstance(x, str) and x.isdigit())
        if state.get("completed_over"):
            ctx["completed_over"] = state["completed_over"]
            ctx["completed_over_runs"] = state.get("completed_over_runs", 0)

        partnership = state.get("partnerships", {})
        if isinstance(partnership, dict) and partnership.get("current"):
            p = partnership["current"]
            ctx["partnership"] = f"{p.get('runs', 0)} runs ({p.get('balls', 0)} balls)"

        ctx["recent_lines"] = self.recent_commentary[-5:]
        if len(self.recent_commentary) > 10:
            self.recent_commentary = self.recent_commentary[-10:]

        if ball_event.get("type") == "DOT":
            self.dot_ball_streak += 1
            self.boundary_streak = 0
        elif ball_event.get("type") in ("FOUR", "SIX"):
            self.boundary_streak += 1
            self.dot_ball_streak = 0
        else:
            self.dot_ball_streak = 0
            self.boundary_streak = 0

        ctx["dot_streak"] = self.dot_ball_streak
        ctx["boundary_streak"] = self.boundary_streak
        return ctx

    def build_over_context(self, state: dict, over_summary: dict) -> dict:
        ctx = self.build_ball_context(state, {"type": "OVER_END"})
        ctx["over_summary"] = over_summary
        return ctx

    def format_for_prompt(self, ctx: dict) -> str:
        lines: list[str] = []

        # Event type FIRST so the LLM reads it before anything else
        b = ctx.get("ball", {})
        if b.get("type") and b["type"] != "OVER_END":
            over_str = b.get("over", "0")
            try:
                over_f = float(over_str)
                over_int = int(over_f)
                ball_num = round((over_f % 1) * 10)
                delivery = f"{over_int}.{ball_num}"
            except (ValueError, TypeError):
                delivery = over_str
            ball_type = b.get("type", "?")
            extra = ""
            if ball_type == "EXTRA":
                extra = f" ({b.get('extra_type', 'wide/no-ball')})"
            free_hit = " [FREE HIT]" if b.get("free_hit") else ""
            runs = b.get("runs", 0)
            extras_type = b.get("extras_type", "")
            if extras_type == "leg_bye_or_bye":
                lines.append(f"OUTCOME: LEG BYE/BYE ({runs} runs). The ball did NOT come off the bat — the runs are extras (leg byes or byes). Do NOT credit the batter with these runs.")
            elif ball_type == "WICKET":
                dismissal_mode = ctx.get("dismissal_mode", "")
                if dismissal_mode:
                    lines.append(f"OUTCOME: WICKET ({dismissal_mode}). The batter is OUT — {dismissal_mode}. Describe this dismissal accurately using ONLY this mode.")
                else:
                    lines.append(f"OUTCOME: WICKET. The batter is OUT. Do NOT specify how the batter was dismissed (caught/bowled/lbw/stumped) — the dismissal mode is unknown.")
            else:
                lines.append(f"OUTCOME: {ball_type} ({runs} runs). Describe this result.")
            lines.append(f"THIS BALL: {delivery}: {ball_type}{extra}{free_hit} | +{runs} runs")

        _match_line = f"MATCH: {ctx.get('batting_team', '?')} vs {ctx.get('bowling_team', '?')}, Innings {ctx.get('innings', 1)}"
        if ctx.get("match_info"):
            _match_line += f" — {ctx['match_info']}"
        lines.append(_match_line)
        if ctx.get("venue"):
            lines.append(f"VENUE: {ctx['venue']}")
        lines.append(f"SCORE: {ctx.get('score', '?')}")

        if ctx.get("chase"):
            c = ctx["chase"]
            lines.append(f"CHASE: Need {c['runs_needed']} from {c['balls_remaining']} balls (RRR: {c['required_rate']})")

        lines.append(f"STRIKER: {ctx.get('striker', '?')} — {ctx.get('striker_stats', '?')}")
        lines.append(f"NON-STRIKER: {ctx.get('non', '?')} — {ctx.get('non_stats', '?')}")
        econ = ctx.get("bowler_economy")
        econ_str = f" (Econ: {econ})" if econ else ""
        lines.append(f"BOWLER: {ctx.get('bowler', '?')} — {ctx.get('bowler_stats', '?')}{econ_str}")

        if ctx.get("speed_kph"):
            lines.append(f"SPEED: {ctx['speed_kph']} kph")

        if ctx.get("partnership"):
            lines.append(f"PARTNERSHIP: {ctx['partnership']}")

        lines.append(f"THIS OVER: {ctx.get('this_over', [])} = {ctx.get('this_over_runs', 0)} runs")

        if ctx.get("completed_over"):
            lines.append(f"JUST-COMPLETED OVER: {ctx['completed_over']} "
                         f"= {ctx.get('completed_over_runs', 0)} runs")

        if ctx.get("over_summary"):
            os_ = ctx["over_summary"]
            lines.append(f"COMPLETED OVER: {os_.get('balls', [])} = {os_.get('runs', 0)} runs by {os_.get('bowler', '?')}")

        overs_str = ctx.get("score", "0/0 (0)").split("(")[-1].rstrip(")")
        try:
            _ov_f = float(overs_str)
            _total_balls = int(_ov_f) * 6 + round((_ov_f % 1) * 10)
            _balls_rem = 120 - _total_balls
            _overs_rem_w = _balls_rem // 6
            _overs_rem_b = _balls_rem % 6
            if 0 < _balls_rem <= 120:
                lines.append(f"REMAINING: {_balls_rem} balls "
                             f"({_overs_rem_w}.{_overs_rem_b} overs)")
        except (ValueError, TypeError):
            pass

        if ctx.get("dot_streak", 0) >= 3:
            lines.append(f"PRESSURE: {ctx['dot_streak']} dot balls in a row")
        if ctx.get("boundary_streak", 0) >= 2:
            lines.append(f"MOMENTUM: {ctx['boundary_streak']} boundaries in a row")

        dl = ctx.get("delivery_length")
        dli = ctx.get("delivery_line")
        da = ctx.get("delivery_angle")
        dst = ctx.get("delivery_shot_type")
        ddir = ctx.get("delivery_shot_direction")
        delev = ctx.get("delivery_shot_elevation")
        if dl or dli or da or dst or ddir or delev:
            parts: list[str] = []
            if da and da != "unknown":
                parts.append(f"Angle: {da.replace('_', ' ')}")
            if dl and dl != "unknown":
                parts.append(f"Length: {dl.replace('_', ' ')}")
            if dli and dli != "unknown":
                parts.append(f"Line: {dli.replace('_', ' ')}")
            if dst and dst != "unknown":
                parts.append(f"Shot: {dst.replace('_', ' ')}")
            if ddir and ddir != "unknown":
                parts.append(f"Direction: {ddir.replace('_', ' ')}")
            if delev and delev != "unknown":
                parts.append(f"Elevation: {delev.replace('_', ' ')}")
            if parts:
                lines.append(f"DELIVERY DATA: {' | '.join(parts)}")

        recent = ctx.get("recent_lines") or []
        if recent:
            openers = []
            for rl in recent[-5:]:
                words = rl.split()[:12]
                openers.append(" ".join(words))
            lines.append(
                "RECENT OPENERS (do NOT start with similar phrasing): "
                + " | ".join(openers))

        return "\n".join(lines)
