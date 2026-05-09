"""Quick verification: run is_delivery_frame on saved scout_pick frames.

Prints per-delivery pass rate and a global summary so we can decide
whether burst-based capture (relying on is_delivery_frame at high FPS)
is feasible for this broadcast.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).parent))
from pitch_detector import (  # noqa: E402
    is_delivery_frame,
    _find_pitch_center,
    _has_figures_at_both_ends,
)


def main(session_dir: str) -> None:
    base = Path(session_dir)
    if not base.exists():
        print(f"Missing dir: {base}")
        return

    delivery_dirs = sorted(d for d in base.iterdir()
                           if d.is_dir() and d.name.startswith("d"))
    if not delivery_dirs:
        print("No delivery dirs found.")
        return

    tot = pas = pitch_only = 0
    rows: list[tuple[str, int, int, int, int, str]] = []
    for ddir in delivery_dirs:
        picks = sorted(ddir.glob("scout_pick_*.jpg"))
        if not picks:
            continue
        d_pass = d_pitch = 0
        for p in picks:
            frame = cv2.imread(str(p))
            if frame is None:
                continue
            tot += 1
            pcx = _find_pitch_center(frame)
            full = is_delivery_frame(frame)
            if full:
                pas += 1
                d_pass += 1
            elif pcx is not None:
                pitch_only += 1
                d_pitch += 1
        runs = "?"
        pj = ddir / "predictions.json"
        if pj.exists():
            try:
                runs = str(json.loads(pj.read_text()).get("runs", "?"))
            except Exception:
                pass
        rows.append((ddir.name, len(picks), d_pass, d_pitch,
                     len(picks) - d_pass - d_pitch, runs))

    print(f"{'delivery':<8} {'picks':<6} {'pass':<5} {'pitch_only':<11} "
          f"{'fail_all':<9} runs")
    print("-" * 56)
    n_at_least_one = 0
    for name, n, p, pi, f, r in rows:
        if p >= 1:
            n_at_least_one += 1
        marker = " ✓" if p >= 1 else ""
        print(f"{name:<8} {n:<6} {p:<5} {pi:<11} {f:<9} {r}{marker}")

    print()
    print(f"TOTAL frames: {tot}  pass={pas} ({pas/max(tot,1)*100:.0f}%)  "
          f"pitch_only={pitch_only} ({pitch_only/max(tot,1)*100:.0f}%)  "
          f"fail={tot-pas-pitch_only}")
    print(f"Deliveries with ≥1 passing pick: {n_at_least_one}/{len(rows)} "
          f"({n_at_least_one/max(len(rows),1)*100:.0f}%)")


if __name__ == "__main__":
    sd = (sys.argv[1] if len(sys.argv) > 1
          else "logs/deliveries/20260419_195420")
    main(sd)
