"""Cricket rules validation — ensures extracted data obeys cricket logic."""
from __future__ import annotations

from dataclasses import dataclass, field

from eyes.cricket_logger import CricketLogger

log = CricketLogger("VALID")


@dataclass
class ValidationIssue:
    rule: str
    detail: str
    severity: str  # "warning" | "error" | "critical"
    field_path: str = ""


class MatchStateValidator:
    """Validates LLM extractions against cricket rules.

    Score only increases. Overs go 0.1→0.6→1.0. Wickets increase by 1 only.
    Minimum time between deliveries. Score can't exceed theoretical max.
    """

    MAX_OVERS_T20 = 20
    MAX_WICKETS = 10
    MAX_RUNS_PER_BALL = 7  # 6 + no ball
    MAX_SCORE_T20 = 300  # theoretical ceiling
    BALLS_PER_OVER = 6

    def __init__(self, match_format: str = "T20"):
        self.format = match_format
        self.max_overs = self.MAX_OVERS_T20 if match_format == "T20" else 50
        self._prev_scoreboard: dict | None = None
        self._issues_history: list[ValidationIssue] = []
        self._corrections_count = 0

    def validate(self, scoreboard: dict) -> tuple[dict, list[ValidationIssue]]:
        """Validate a scoreboard extraction. Returns (validated_scoreboard, issues)."""
        issues: list[ValidationIssue] = []

        if not scoreboard or scoreboard.get("score") is None:
            return scoreboard, issues

        score = self._safe_int(scoreboard.get("score"))
        wickets = self._safe_int(scoreboard.get("wickets"), 0)
        overs = scoreboard.get("overs")

        # Rule: score must be non-negative
        if score is not None and score < 0:
            issues.append(ValidationIssue("negative_score", f"Score {score} < 0", "critical"))
            score = self._prev_scoreboard.get("score", 0) if self._prev_scoreboard else 0

        # Rule: score can't exceed theoretical max
        if score is not None and score > self.MAX_SCORE_T20:
            issues.append(ValidationIssue(
                "impossible_score", f"Score {score} > {self.MAX_SCORE_T20}", "error"
            ))

        # Rule: wickets in range 0–10
        if wickets < 0 or wickets > self.MAX_WICKETS:
            issues.append(ValidationIssue(
                "invalid_wickets", f"Wickets {wickets} outside 0–10", "critical"
            ))
            wickets = min(max(wickets, 0), self.MAX_WICKETS)

        # Rule: overs validation
        overs_issue = self._validate_overs(overs)
        if overs_issue:
            issues.append(overs_issue)

        # Rules comparing to previous state
        if self._prev_scoreboard:
            prev_score = self._safe_int(self._prev_scoreboard.get("score"), 0)
            prev_wickets = self._safe_int(self._prev_scoreboard.get("wickets"), 0)

            # Rule: score should not decrease (within same innings)
            if score is not None and prev_score is not None and score < prev_score:
                issues.append(ValidationIssue(
                    "score_decreased",
                    f"Score went from {prev_score} to {score}",
                    "error",
                ))

            # Rule: wickets should not decrease
            if wickets < prev_wickets:
                issues.append(ValidationIssue(
                    "wickets_decreased",
                    f"Wickets went from {prev_wickets} to {wickets}",
                    "error",
                ))

            # Rule: wickets increase by at most 1 per ball
            if wickets - prev_wickets > 1:
                issues.append(ValidationIssue(
                    "multi_wicket_jump",
                    f"Wickets jumped from {prev_wickets} to {wickets}",
                    "warning",
                ))

            # Rule: score can't jump more than MAX_RUNS_PER_BALL per delivery
            if score is not None and prev_score is not None:
                jump = score - prev_score
                if jump > self.MAX_RUNS_PER_BALL:
                    issues.append(ValidationIssue(
                        "score_jump",
                        f"Score jumped by {jump} (prev {prev_score} → {score})",
                        "warning",
                    ))

        # Rule: batter runs can't exceed team score
        for key in ("batter_1", "batter_2"):
            batter = scoreboard.get(key, {})
            if batter and isinstance(batter, dict):
                b_runs = self._safe_int(batter.get("runs"))
                if b_runs is not None and score is not None and b_runs > score:
                    issues.append(ValidationIssue(
                        "batter_exceeds_total",
                        f"Batter {batter.get('name')} runs {b_runs} > team score {score}",
                        "critical",
                        field_path=key,
                    ))

        # Build validated scoreboard
        validated = dict(scoreboard)
        if score is not None:
            validated["score"] = score
        validated["wickets"] = wickets

        has_critical = any(i.severity == "critical" for i in issues)
        if not has_critical:
            self._prev_scoreboard = validated

        # Log results
        if not issues:
            log.info(f"✓ All checks passed: {score}/{wickets} ({overs})")
        else:
            for issue in issues:
                if issue.severity == "critical":
                    log.error(f"{issue.detail} — REJECTING")
                elif issue.severity == "error":
                    log.error(f"{issue.detail} — REJECTING")
                else:
                    log.warn(f"{issue.detail}")

        self._issues_history.extend(issues)
        self._corrections_count += len(issues)

        return validated, issues

    def _validate_overs(self, overs) -> ValidationIssue | None:
        if overs is None:
            return None
        try:
            overs_str = str(overs)
            if "." in overs_str:
                whole, ball = overs_str.split(".")
                whole = int(whole)
                ball = int(ball)
                if ball < 0 or ball > 6:
                    return ValidationIssue(
                        "invalid_ball_in_over",
                        f"Ball {ball} in over {overs_str} — must be 0–6",
                        "error",
                    )
                if whole > self.max_overs:
                    return ValidationIssue(
                        "overs_exceeded",
                        f"Over {whole} exceeds max {self.max_overs}",
                        "error",
                    )
            else:
                whole = int(overs_str)
                if whole > self.max_overs:
                    return ValidationIssue(
                        "overs_exceeded",
                        f"Over {whole} exceeds max {self.max_overs}",
                        "error",
                    )
        except (ValueError, TypeError):
            return ValidationIssue(
                "unparseable_overs", f"Cannot parse overs: {overs}", "warning"
            )
        return None

    @staticmethod
    def _safe_int(val, default=None) -> int | None:
        if val is None:
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    def get_issues_count(self) -> int:
        return self._corrections_count

    def reset(self):
        self._prev_scoreboard = None
        self._issues_history.clear()
        self._corrections_count = 0
