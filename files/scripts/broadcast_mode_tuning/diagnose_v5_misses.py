#!/usr/bin/env python3
"""Dump signal flags for four windows of interest in fifth_5min_scout_run.

Targets:
  - t=1265-1271 (c3+c4 duplicate split)
  - t=1325-1336 (missed ball with explicit motion-verb prose)
  - t=1445-1455 (missed wicket ball)
  - t=1275-1280 (c5: real ball 4.5 or replay false positive?)
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from signal_extraction import extract_signals  # noqa: E402
from delivery_classifier import FrameInfo, annotate  # noqa: E402

SIDECARS = REPO_ROOT / "files/scripts/broadcast_mode_tuning/fifth_5min_scout_run"
OUT_TXT = REPO_ROOT / "files/scripts/broadcast_mode_tuning/diagnose_v5_misses.txt"

WINDOWS = [
    (1265, 1271, "c3 + c4 duplicate split"),
    (1275, 1280, "c5 — real 4.5 or replay false positive?"),
    (1325, 1336, "missed ball with explicit motion-verb prose"),
    (1445, 1455, "missed wicket ball"),
]


def yn(b: bool) -> str:
    return "Y" if b else "n"


def path_check(s) -> tuple[bool, bool, bool]:
    if s.HARD:
        return (False, False, False)
    k2 = s.K or (s.SS and s.CG)
    a = s.V and s.S and (s.W or s.M2)
    b = s.V and s.M and s.W and k2 and s.SS
    c = s.M2 and s.W and k2 and s.SS
    return (a, b, c)


def main() -> int:
    lines: list[str] = []

    def emit(s: str = "") -> None:
        print(s)
        lines.append(s)

    # Load and annotate the entire fifth-5min window
    by_t: dict[int, FrameInfo] = {}
    for t in range(1200, 1500):
        fno = int(t * 25)
        path = SIDECARS / f"f_{fno:05d}_t={float(t):06.2f}.txt"
        if not path.exists():
            continue
        raw = path.read_text()
        text = raw.split("---\n", 1)[1].strip() if "---\n" in raw else raw
        f = FrameInfo(t=float(t), text=text)
        f.signals = extract_signals(text)
        annotate(f)
        by_t[t] = f

    header = (f"{'t':>4} | {'V':>1} {'S':>1} {'M':>1} {'M2':>2} {'W':>1} "
             f"{'K':>1} {'SS':>2} {'SSlo':>4} {'CG':>2} {'HARD':>4} | "
             f"{'A':>1} {'B':>1} {'C':>1} | path | rc")

    for lo, hi, title in WINDOWS:
        emit(f"=== t={lo}-{hi} — {title} ===")
        emit()
        emit(header)
        emit("-" * len(header))
        for t in range(lo, hi + 1):
            f = by_t.get(t)
            if f is None:
                emit(f"{t:>4}  (no frame)")
                continue
            s = f.signals
            a, b, c = path_check(s)
            emit(
                f"{t:>4} | {yn(s.V)} {yn(s.S)} {yn(s.M)} "
                f"{yn(s.M2):>2} {yn(s.W)} {yn(s.K)} "
                f"{yn(s.SS):>2} {yn(s.SS_via_loose):>4} {yn(s.CG):>2} "
                f"{yn(s.HARD):>4} | {yn(a)} {yn(b)} {yn(c)} | {f.path:>4} | "
                f"{s.role_count}"
            )
        emit()

    # Quote prose for any frame in 1325-1336 / 1445-1455 with delivery-verb
    # language. Helps confirm "what Scout actually said".
    import re
    verb_pat = re.compile(
        r"\b(?:released|bowled|delivered|thrown|swung|swinging|"
        r"follow[-\s]through|just\s+(?:hit|played|bowled|delivered|released)|"
        r"about\s+to\s+(?:bowl|deliver|release|throw)|"
        r"in\s+mid[-\s]?(?:action|stride|swing|air)|delivery\s+stride|"
        r"in\s+process\s+of\s+(?:bowling|delivering)|"
        r"running\s+(?:in|on\s+the\s+field)|throwing\s+the\s+ball)\b",
        re.IGNORECASE,
    )
    for lo, hi, title in WINDOWS:
        emit(f"=== Prose with delivery-verb language: t={lo}-{hi} ({title}) ===")
        emit()
        for t in range(lo, hi + 1):
            f = by_t.get(t)
            if f is None:
                continue
            m = verb_pat.search(f.text)
            if not m:
                continue
            emit(f"  -- t={t} path={f.path} V={yn(f.signals.V)} "
                 f"matched='{m.group(0)}' --")
            for ln in f.text.splitlines():
                emit(f"     {ln}")
            emit()

    OUT_TXT.write_text("\n".join(lines) + "\n")
    print(f"Wrote {OUT_TXT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
