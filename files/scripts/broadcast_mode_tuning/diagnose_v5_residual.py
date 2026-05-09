#!/usr/bin/env python3
"""Diagnose three residual issues from the 1200-1500 window:

1. Medium-shot ball at t=1325-1340 — why no SS?
2. c29 (1277) replay-of-just-bowled-ball — what markers identify it?
3. c32 (1418) wicket catch — what's in the 1419-1430 forward extension?
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from signal_extraction import extract_signals  # noqa: E402
from delivery_classifier import FrameInfo, annotate  # noqa: E402

SC = REPO_ROOT / "files/scripts/broadcast_mode_tuning/fifth_5min_scout_run"
OUT = REPO_ROOT / "files/scripts/broadcast_mode_tuning/diagnose_v5_residual.txt"


WINDOWS = [
    (1325, 1340, "medium-shot ball — why SS=N?"),
    (1275, 1295, "c29 replay-of-just-bowled — markers?"),
    (1418, 1430, "c32 wicket catch — forward extension content"),
]


def yn(b: bool) -> str:
    return "Y" if b else "n"


def main() -> int:
    lines: list[str] = []

    def emit(s: str = "") -> None:
        print(s)
        lines.append(s)

    by_t: dict[int, FrameInfo] = {}
    for t in range(1200, 1500):
        fno = int(t * 25)
        path = SC / f"f_{fno:05d}_t={float(t):06.2f}.txt"
        if not path.exists():
            continue
        raw = path.read_text()
        text = raw.split("---\n", 1)[1].strip() if "---\n" in raw else raw
        f = FrameInfo(t=float(t), text=text)
        f.signals = extract_signals(text)
        annotate(f)
        by_t[t] = f

    for lo, hi, title in WINDOWS:
        emit(f"=== t={lo}-{hi} — {title} ===")
        emit()
        emit("Per-frame signals:")
        for t in range(lo, hi + 1):
            f = by_t.get(t)
            if f is None:
                continue
            s = f.signals
            emit(f"  t={t} D={int(f.is_delivery)} path={f.path:>4s} "
                 f"V={yn(s.V)} S={yn(s.S)} M={yn(s.M)} M2={yn(s.M2)} "
                 f"W={yn(s.W)} K={yn(s.K)} SS={yn(s.SS)}({yn(s.SS_via_loose)}) "
                 f"CG={yn(s.CG)} HARD={yn(s.HARD)} rc={s.role_count}")
        emit()
        emit("Prose excerpts (first 280 chars per frame):")
        for t in range(lo, hi + 1):
            f = by_t.get(t)
            if f is None:
                continue
            txt = f.text.replace("\n", " ").strip()
            emit(f"  -- t={t} --")
            emit(f"     {txt[:280]}")
            if len(txt) > 280:
                emit(f"     ... ({len(txt)} total chars)")
        emit()

    OUT.write_text("\n".join(lines) + "\n")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
