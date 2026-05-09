"""Learns broadcaster visual vocabulary by observing correlations."""
from __future__ import annotations

import time
from collections import defaultdict, Counter

from eyes.cricket_logger import CricketLogger

log = CricketLogger("CORR")


class CorrelationLearner:
    """Maps visual symbols and patterns to cricket events.

    Observes correlations between what appears on screen (colors, symbols,
    text patterns, positions) and what actually happened (ball events,
    score changes). Over time, builds a vocabulary specific to the
    current broadcaster.

    For example:
    - A yellow flash + score change = boundary
    - A red text overlay = wicket
    - Specific icon positions = DRS review
    """

    def __init__(self):
        self._ball_correlations: list[dict] = []
        self._frame_type_counts = Counter()
        self._symbol_event_pairs: dict[str, Counter] = defaultdict(Counter)
        self._broadcast_patterns: dict[str, list] = defaultdict(list)
        self._learned_vocabulary: dict[str, str] = {}

    def on_ball(self, ball: dict, extraction: dict):
        """Record what was visible when a ball event occurred."""
        record = {
            "result": ball.get("result"),
            "runs": ball.get("runs"),
            "wicket": ball.get("wicket"),
            "frame_type": extraction.get("frame_type"),
            "broadcast_text": extraction.get("broadcast_text", []),
            "timestamp": time.time(),
        }

        # Track frame_type → result correlations
        ft = extraction.get("frame_type", "unknown")
        self._frame_type_counts[ft] += 1

        # Track text patterns near events
        texts = extraction.get("broadcast_text", [])
        if isinstance(texts, list):
            for text in texts:
                if isinstance(text, str):
                    self._symbol_event_pairs[text.lower()][ball.get("result", "unknown")] += 1

        # Track umpire signal correlations
        players = extraction.get("players", {})
        if isinstance(players, dict):
            signal = players.get("umpire_signal")
            if signal and signal not in ("null", None):
                record["umpire_signal"] = signal
                self._symbol_event_pairs[f"signal:{signal}"][ball.get("result", "unknown")] += 1

        self._ball_correlations.append(record)
        self._update_vocabulary()

    def on_frame(self, extraction: dict):
        """Track general frame patterns (not tied to ball events)."""
        ft = extraction.get("frame_type", "unknown")
        self._frame_type_counts[ft] += 1

    def _update_vocabulary(self):
        """Periodically derive learned mappings from accumulated data."""
        if len(self._ball_correlations) < 10:
            return

        prev_size = len(self._learned_vocabulary)
        for symbol, event_counts in self._symbol_event_pairs.items():
            total = sum(event_counts.values())
            if total < 3:
                continue
            most_common, count = event_counts.most_common(1)[0]
            confidence = count / total
            if confidence > 0.7:
                if symbol not in self._learned_vocabulary:
                    log.info(f"Learned: {symbol} → {most_common} ({count}/{total} correlations)")
                self._learned_vocabulary[symbol] = most_common
            elif total >= 3 and confidence <= 0.5:
                top_two = event_counts.most_common(2)
                if len(top_two) == 2:
                    log.warn(f"Conflicting correlation: {symbol} mapped to both {top_two[0][0]} and {top_two[1][0]}")

        new_size = len(self._learned_vocabulary)
        if new_size > prev_size:
            log.info(f"Vocabulary: {new_size} symbols mapped after {len(self._ball_correlations)} balls")

    def get_vocabulary(self) -> dict[str, str]:
        return dict(self._learned_vocabulary)

    def predict_from_text(self, texts: list[str]) -> str | None:
        """Given broadcast text, predict what event might be happening."""
        if not texts:
            return None
        for text in texts:
            if isinstance(text, str):
                key = text.lower()
                if key in self._learned_vocabulary:
                    return self._learned_vocabulary[key]
        return None

    def get_stats(self) -> dict:
        return {
            "total_ball_observations": len(self._ball_correlations),
            "frame_type_distribution": dict(self._frame_type_counts),
            "learned_vocabulary_size": len(self._learned_vocabulary),
            "vocabulary": self._learned_vocabulary,
        }

    def reset(self):
        self.__init__()
