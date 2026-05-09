#!/usr/bin/env python3
"""Diagnose why no cluster forms in 940-960s of fourth_5min_scout_run."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from signal_extraction import extract_signals  # noqa: E402
from delivery_classifier import (  # noqa: E402
    FrameInfo, annotate, build_clusters,
)

SIDECARS = REPO_ROOT / "files/scripts/broadcast_mode_tuning/fourth_5min_scout_run"
OUT_TXT = REPO_ROOT / "files/scripts/broadcast_mode_tuning/diagnose_3_4.txt"

T_LO = 940
T_HI = 960
GAP_MAX = 2
MIN_RUN = 2


def yn(b: bool) -> str:
    return "Y" if b else "n"


def path_check(s) -> tuple[bool, bool, bool]:
    """Return (path_A_fires, path_B_fires, path_C_fires)."""
    if s.HARD:
        return (False, False, False)
    k2 = s.K or (s.SS and s.CG)
    a = s.V and s.S and (s.W or s.M2)
    b = s.V and s.M2 and s.W and k2 and s.SS
    c = s.M2 and s.W and k2 and s.SS
    return (a, b, c)


def main() -> int:
    lines: list[str] = []

    def emit(s: str) -> None:
        print(s)
        lines.append(s)

    # Load and annotate frames
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
    emit("")
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

    # Spotlight on t=945, 946, 947
    emit("")
    emit("=== Spotlight: t=945, 946, 947 ===")
    emit("")
    for t in (945, 946, 947):
        f = by_t.get(t)
        if f is None:
            emit(f"  t={t}: (no frame)")
            continue
        s = f.signals
        a, b, c = path_check(s)
        emit(f"  t={t}: V={yn(s.V)} S={yn(s.S)} M={yn(s.M)} M2={yn(s.M2)} "
             f"W={yn(s.W)} K={yn(s.K)} SS={yn(s.SS)}({'loose' if s.SS_via_loose else 'strict'}) "
             f"CG={yn(s.CG)} HARD={yn(s.HARD)} rc={s.role_count}")
        emit(f"        Path A fires: {yn(a)} (need V+S+(W|M2))")
        emit(f"        Path B fires: {yn(b)} (need V+M2+W+(K|SS&CG)+SS)")
        emit(f"        Path C fires: {yn(c)} (need M2+W+(K|SS&CG)+SS)")
        emit(f"        Final classification: path={f.path} is_delivery={f.is_delivery}")
        miss = []
        if not s.HARD:
            if not (s.V and s.S and (s.W or s.M2)):
                a_miss = []
                if not s.V: a_miss.append("V")
                if not s.S: a_miss.append("S")
                if not (s.W or s.M2): a_miss.append("(W|M2)")
                miss.append(f"A:{','.join(a_miss)}")
            if not (s.V and s.M2 and s.W and (s.K or (s.SS and s.CG)) and s.SS):
                b_miss = []
                if not s.V: b_miss.append("V")
                if not s.M2: b_miss.append("M2")
                if not s.W: b_miss.append("W")
                if not (s.K or (s.SS and s.CG)): b_miss.append("K2")
                if not s.SS: b_miss.append("SS")
                miss.append(f"B:{','.join(b_miss)}")
            if not (s.M2 and s.W and (s.K or (s.SS and s.CG)) and s.SS):
                c_miss = []
                if not s.M2: c_miss.append("M2")
                if not s.W: c_miss.append("W")
                if not (s.K or (s.SS and s.CG)): c_miss.append("K2")
                if not s.SS: c_miss.append("SS")
                miss.append(f"C:{','.join(c_miss)}")
        if miss:
            emit(f"        Missing for each path: {miss}")
        emit("")

    # Cluster builder trace for t=940-960
    emit("=== Cluster builder trace, t=940-960 ===")
    emit("")
    in_cluster = False
    cluster_start: int | None = None
    last_d: int | None = None
    gap = 0
    open_clusters: list[tuple[int, int]] = []
    closed_clusters: list[tuple[int, int, str]] = []
    for t in range(T_LO, T_HI + 1):
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
        # in_cluster
        if s.HARD:
            emit(f"  t={t}: HARD-REJECT -> close at last_d={last_d}")
            closed_clusters.append((cluster_start, last_d, "hard-reject"))
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
            closed_clusters.append((cluster_start, last_d, f"gap>{GAP_MAX}"))
            in_cluster = False
            cluster_start = None
            continue
        emit(f"  t={t}: gap={gap} (D=N path=none)")

    if in_cluster:
        closed_clusters.append((cluster_start, last_d, "window-end"))
        emit(f"  t={T_HI}: window end -> close at last_d={last_d}")

    emit("")
    emit(f"=== Closed clusters in 940-960: {len(closed_clusters)} ===")
    for s_, e_, why in closed_clusters:
        n_frames = sum(1 for t in range(s_, e_ + 1)
                       if by_t.get(t) and by_t[t].is_delivery)
        passes_min = n_frames >= MIN_RUN
        any_v = any(by_t[t].signals.V for t in range(s_, e_ + 1) if by_t.get(t))
        emit(f"  start={s_} end={e_} reason={why} delivery_count={n_frames} "
             f"any_v={yn(any_v)} pass_min_run({MIN_RUN})={yn(passes_min)} "
             f"pass_v_filter={yn(any_v)}")

    # Sanity: also show what build_clusters() actually produces
    emit("")
    emit("=== build_clusters() output (for cross-check) ===")
    sub = [f for f in all_frames if T_LO - 5 <= f.t <= T_HI + 5]
    clusters = build_clusters(sub, gap_max=GAP_MAX, min_run=MIN_RUN)
    emit(f"  Found {len(clusters)} cluster(s) in window [{T_LO - 5}, {T_HI + 5}]")
    for c in clusters:
        emit(f"  cluster {c['start_t']:.0f}-{c['end_t']:.0f}s "
             f"({len(c['frames'])} frames)")

    OUT_TXT.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {OUT_TXT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
