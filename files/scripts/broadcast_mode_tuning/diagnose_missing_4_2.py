#!/usr/bin/env python3
"""Diagnose why ball 4.2 (~1170-1200) didn't form a cluster in fourth_5min_scout_run."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from signal_extraction import extract_signals  # noqa: E402
from delivery_classifier import (  # noqa: E402
    FrameInfo, annotate, build_clusters,
)

SIDECARS = REPO_ROOT / "files/scripts/broadcast_mode_tuning/fourth_5min_scout_run"
OUT_TXT = REPO_ROOT / "files/scripts/broadcast_mode_tuning/diagnose_4_2.txt"

T_LO = 1170
T_HI = 1200
TRACE_LO = 1148
GAP_MAX = 2
MIN_RUN = 2

DELIVERY_VERB_PAT = re.compile(
    r"\b(?:released|bowled|delivered|thrown|swung|swinging|"
    r"follow[-\s]through|just\s+(?:hit|played|bowled|delivered|released)|"
    r"about\s+to\s+(?:bowl|deliver|release|throw)|"
    r"in\s+mid[-\s]?(?:action|stride)|delivery\s+stride|"
    r"in\s+process\s+of\s+(?:bowling|delivering)|"
    r"running\s+(?:in|on\s+the\s+field))\b",
    re.IGNORECASE,
)


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

    all_frames: list[FrameInfo] = []
    for t in range(900, 1200):
        fno = int(t * 25)
        path = SIDECARS / f"f_{fno:05d}_t={float(t):06.2f}.txt"
        if not path.exists():
            continue
        raw = path.read_text()
        text = raw.split("---\n", 1)[1].strip() if "---\n" in raw else raw
        f = FrameInfo(t=float(t), text=text)
        f.signals = extract_signals(text)
        annotate(f)
        all_frames.append(f)
    by_t = {round(f.t): f for f in all_frames}

    emit(f"=== Per-frame signals for t={T_LO}-{T_HI} ===")
    emit()
    header = (f"{'t':>4} | {'V':>1} {'S':>1} {'M':>1} {'M2':>2} {'W':>1} "
             f"{'K':>1} {'SS':>2} {'SSlo':>4} {'CG':>2} {'HARD':>4} | "
             f"{'A':>1} {'B':>1} {'C':>1} | path | rc")
    emit(header)
    emit("-" * len(header))
    for t in range(T_LO, T_HI + 1):
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
    emit(f"=== Cluster builder trace, t={TRACE_LO}-{T_HI} ===")
    emit()
    in_cluster = False
    cluster_start: int | None = None
    last_d: int | None = None
    gap = 0
    closed: list[tuple[int, int, str]] = []
    for t in range(TRACE_LO, T_HI + 1):
        f = by_t.get(t)
        if f is None:
            continue
        s = f.signals
        if not in_cluster:
            if s.HARD or not f.is_delivery:
                emit(f"  t={t}: idle (HARD={yn(s.HARD)} D={yn(f.is_delivery)})")
                continue
            in_cluster = True
            cluster_start = t
            last_d = t
            gap = 0
            emit(f"  t={t}: OPEN cluster (path={f.path})")
            continue
        if s.HARD:
            emit(f"  t={t}: HARD-REJECT -> close at last_d={last_d}")
            closed.append((cluster_start, last_d, "hard-reject"))
            in_cluster = False
            cluster_start = None
            continue
        if f.is_delivery:
            last_d = t
            gap = 0
            emit(f"  t={t}: extend cluster (path={f.path}), last_d={t}")
            continue
        gap += 1
        if gap > GAP_MAX:
            emit(f"  t={t}: gap>{GAP_MAX} -> close at last_d={last_d}")
            closed.append((cluster_start, last_d, f"gap>{GAP_MAX}"))
            in_cluster = False
            cluster_start = None
            continue
        emit(f"  t={t}: gap={gap} (D=N path=none)")
    if in_cluster:
        closed.append((cluster_start, last_d, "window-end"))
        emit(f"  t={T_HI}: window end -> close at last_d={last_d}")

    emit()
    emit(f"=== Closed clusters in {TRACE_LO}-{T_HI}: {len(closed)} ===")
    for s_, e_, why in closed:
        n_d = sum(1 for t in range(s_, e_ + 1) if by_t.get(t) and by_t[t].is_delivery)
        any_v = any(by_t[t].signals.V for t in range(s_, e_ + 1) if by_t.get(t))
        emit(f"  start={s_} end={e_} reason={why} delivery_count={n_d} "
             f"any_v={yn(any_v)} pass_min_run({MIN_RUN})={yn(n_d >= MIN_RUN)} "
             f"pass_v_filter={yn(any_v)}")

    emit()
    emit("=== build_clusters() output (cross-check) ===")
    sub = [f for f in all_frames if TRACE_LO - 5 <= f.t <= T_HI + 5]
    clusters = build_clusters(sub, gap_max=GAP_MAX, min_run=MIN_RUN)
    emit(f"  Found {len(clusters)} cluster(s) in window "
         f"[{TRACE_LO - 5}, {T_HI + 5}]")
    for c in clusters:
        emit(f"  cluster {c['start_t']:.0f}-{c['end_t']:.0f}s "
             f"({len(c['frames'])} frames)")

    # Quote prose for any frame in 1180-1200 with delivery-verb language
    # that didn't reach DELIVERY classification.
    emit()
    emit("=== Prose excerpts: 1180-1200 frames with delivery-verb language ===")
    emit("    (only frames where is_delivery=False but prose contains "
         "released/bowled/swung/follow-through/just-hit/etc.)")
    emit()
    for t in range(1180, T_HI + 1):
        f = by_t.get(t)
        if f is None:
            continue
        m = DELIVERY_VERB_PAT.search(f.text)
        if not m:
            continue
        if f.is_delivery:
            continue  # already classified, not interesting here
        emit(f"  -- t={t} (path={f.path}, V={yn(f.signals.V)}, "
             f"matched verb='{m.group(0)}') --")
        for ln in f.text.splitlines():
            emit(f"     {ln}")
        emit()

    OUT_TXT.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {OUT_TXT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
