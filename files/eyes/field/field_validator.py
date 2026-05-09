from __future__ import annotations


class FieldValidator:
    """Validates YOLO+vision tracking against broadcaster graphics."""

    def __init__(self):
        self.validations: list[dict] = []
        self.accuracy_log: list[float] = []

    def validate(self, our_positions: list[dict],
                 broadcast_positions: list[dict]) -> dict | None:
        """Compare our tracked field against broadcaster's graphic.

        our_positions: from FieldMerger (YOLO+vision)
        broadcast_positions: from extractor field_graphic

        Returns accuracy score + corrections needed.
        """
        if not broadcast_positions or not our_positions:
            return None

        our_zones: set[str] = set()
        for p in our_positions:
            zone = p.get("zone", "")
            base = zone.split("-", 1)[-1] if "-" in zone else zone
            our_zones.add(base)

        broadcast_zones: set[str] = set()
        for p in broadcast_positions:
            zone = p.get("zone", "")
            broadcast_zones.add(zone.lower().replace(" ", "_"))

        correct = our_zones & broadcast_zones
        missed = broadcast_zones - our_zones
        extra = our_zones - broadcast_zones

        total = len(broadcast_zones)
        accuracy = len(correct) / total if total > 0 else 0.0

        result = {
            "accuracy": round(accuracy, 2),
            "correct": sorted(correct),
            "missed": sorted(missed),
            "extra": sorted(extra),
            "broadcast_count": total,
            "our_count": len(our_zones),
            "corrections_needed": len(missed) + len(extra),
        }

        self.validations.append(result)
        self.accuracy_log.append(accuracy)

        print(f"[FIELD VALID] Accuracy: {accuracy:.0%} "
              f"({len(correct)}/{total} correct, "
              f"{len(missed)} missed, {len(extra)} extra)")
        if missed:
            print(f"[FIELD VALID] We missed: {sorted(missed)}")
        if extra:
            print(f"[FIELD VALID] We had extra: {sorted(extra)}")

        return result

    def get_average_accuracy(self) -> float | None:
        if not self.accuracy_log:
            return None
        return sum(self.accuracy_log) / len(self.accuracy_log)
