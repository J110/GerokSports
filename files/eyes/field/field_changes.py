from __future__ import annotations


class FieldChangeDetector:
    """Detects meaningful field changes between deliveries."""

    def __init__(self):
        self.prev_ball_field: list[dict] | None = None
        self.between_ball_moves: list[dict] = []

    def on_new_positions(self, positions: list[dict],
                         is_ball_event: bool) -> dict | None:
        if is_ball_event and self.prev_ball_field:
            changes = self._compare(self.prev_ball_field, positions)
            if changes:
                self.prev_ball_field = [p.copy() for p in positions]
                return changes

        if is_ball_event:
            self.prev_ball_field = [p.copy() for p in positions]

        return None

    def _compare(self, old: list[dict],
                 new: list[dict]) -> dict | None:
        if len(old) < 5 or len(new) < 5:
            return None

        old_zones = set(p["zone"] for p in old)
        new_zones = set(p["zone"] for p in new)

        added = new_zones - old_zones
        removed = old_zones - new_zones

        if not added and not removed:
            return None

        changes = []
        for zone in added:
            changes.append({"type": "added", "zone": zone})
        for zone in removed:
            changes.append({"type": "removed", "zone": zone})

        return {
            "added_zones": list(added),
            "removed_zones": list(removed),
            "changes": changes,
            "summary": self._summarize(added, removed),
        }

    @staticmethod
    def _summarize(added: set[str], removed: set[str]) -> str:
        parts = []
        if removed:
            parts.append(f"removed from {', '.join(removed)}")
        if added:
            parts.append(f"added to {', '.join(added)}")
        return "; ".join(parts)
