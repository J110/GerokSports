#!/usr/bin/env python3
"""Diagnose why c7 (anchor 1764) opened at 1762 instead of 1757."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from signal_extraction import extract_signals  # noqa: E402
from delivery_classifier import FrameInfo, annotate, build_clusters  # noqa: E402

SC = REPO_ROOT / "files/scripts/broadcast_mode_tuning/sixth_5min_scout_run"
OUT = REPO_ROOT / "files/scripts/broadcast_mode_tuning/diagnose_c7.txt"

T_LO = 1755
T_HI = 1768
GAP_MAX = 3
MIN_RUN = 2


def yn(b: bool) -> str:
    return "Y" if b else "n"


def path_check(s) -> tuple[bool, bool, bool, bool]:
    if s.HARD:
        return (False, False, False, False)
    k2 = s.K or (s.SS and s.CG)
    a = s.V and s.S and (s.W or s.M2)
    b = s.V and s.M and s.W and k2 and s.SS
    c = s.M2 and s.W and k2 and s.SS
    d = s.V and s.M2 and s.K and s.SS
    return (a, b, c, d)


def main() -> int:
    lines: list[str] = []

    def emit(s: str = "") -> None:
        print(s)
        lines.append(s)

    by_t: dict[int, FrameInfo] = {}
    for t in range(1500, 1800):
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

    emit(f"=== Per-frame signals for t={T_LO}-{T_HI} ===")
    emit()
    header = (f"{'t':>4} | {'V':>1} {'S':>1} {'M':>1} {'M2':>2} {'W':>1} "
             f"{'K':>1} {'SS':>2} {'SSlo':>4} {'CG':>2} {'HARD':>4} | "
             f"{'A':>1} {'B':>1} {'C':>1} {'D':>1} | path | rc")
    emit(header)
    emit("-" * len(header))
    for t in range(T_LO, T_HI + 1):
        f = by_t.get(t)
        if f is None:
            emit(f"{t:>4}  (no frame)")
            continue
        s = f.signals
        a, b, c, d = path_check(s)
        emit(
            f"{t:>4} | {yn(s.V)} {yn(s.S)} {yn(s.M)} "
            f"{yn(s.M2):>2} {yn(s.W)} {yn(s.K)} "
            f"{yn(s.SS):>2} {yn(s.SS_via_loose):>4} {yn(s.CG):>2} "
            f"{yn(s.HARD):>4} | {yn(a)} {yn(b)} {yn(c)} {yn(d)} | "
            f"{f.path:>4} | {s.role_count}"
        )

    emit()
    emit("=== Spotlight: t=1757 ===")
    f = by_t.get(1757)
    if f is None:
        emit("  (no frame at t=1757)")
    else:
        s = f.signals
        a, b, c, d = path_check(s)
        k2 = s.K or (s.SS and s.CG)
        emit(f"  V={yn(s.V)} S={yn(s.S)} M={yn(s.M)} M2={yn(s.M2)} "
             f"W={yn(s.W)} K={yn(s.K)} SS={yn(s.SS)}({yn(s.SS_via_loose)}) "
             f"CG={yn(s.CG)} HARD={yn(s.HARD)} rc={s.role_count}")
        emit(f"  K2 (K OR (SS AND CG)) = {yn(k2)}")
        emit(f"  Path A fires: {yn(a)} (need V+S+(W|M2))")
        emit(f"  Path B fires: {yn(b)} (need V+M+W+K2+SS)")
        emit(f"  Path C fires: {yn(c)} (need M2+W+K2+SS)")
        emit(f"  Path D fires: {yn(d)} (need V+M2+K+SS)")
        emit(f"  Final classification: path={f.path} is_delivery={f.is_delivery}")
        emit()
        emit("  Prose:")
        for ln in f.text.splitlines():
            emit(f"    {ln}")

    emit()
    emit(f"=== Cluster builder trace, t={T_LO}-{T_HI} ===")
    in_cluster = False
    cluster_start: int | None = None
    last_d: int | None = None
    gap = 0
    closed: list[tuple[int, int, str]] = []
    for t in range(T_LO, T_HI + 1):
        f = by_t.get(t)
        if f is None:
            continue
        s = f.signals
        if not in_cluster:
            if s.HARD or not f.is_delivery:
                emit(f"  t={t}: idle (HARD={yn(s.HARD)} D={yn(f.is_delivery)} path={f.path})")
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

    emit()
    emit(f"=== Closed clusters: {len(closed)} ===")
    for s_, e_, why in closed:
        n_d = sum(1 for t in range(s_, e_ + 1)
                  if by_t.get(t) and by_t[t].is_delivery)
        any_v = any(by_t[t].signals.V for t in range(s_, e_ + 1)
                    if by_t.get(t))
        emit(f"  start={s_} end={e_} reason={why} delivery_count={n_d} "
             f"any_v={yn(any_v)} pass_min_run({MIN_RUN})={yn(n_d >= MIN_RUN)} "
             f"pass_v_filter={yn(any_v)}")

    emit()
    emit("=== build_clusters() output (cross-check) ===")
    sub = [f for f in [by_t.get(t) for t in range(T_LO - 5, T_HI + 5)]
           if f is not None]
    clusters = build_clusters(sub, gap_max=GAP_MAX, min_run=MIN_RUN)
    emit(f"  Found {len(clusters)} cluster(s)")
    for c in clusters:
        emit(f"  cluster {c['start_t']:.0f}-{c['end_t']:.0f}s "
             f"({len(c['frames'])} frames)")

    OUT.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
