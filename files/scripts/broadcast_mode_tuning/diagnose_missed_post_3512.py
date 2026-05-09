#!/usr/bin/env python3
"""Dump signal flags + cluster builder trace for t=3520-3600 to
investigate why post-c78 (t=3512 anchor) deliveries weren't picked up."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from signal_extraction import extract_signals  # noqa: E402
from delivery_classifier import (  # noqa: E402
    FrameInfo, annotate, strong_post_action_match,
)

SC = REPO_ROOT / "files/scripts/broadcast_mode_tuning/twelfth_5min_scout_run"
OUT = REPO_ROOT / "files/scripts/broadcast_mode_tuning/diagnose_missed_post_3512.txt"

T_LO = 3520
T_HI = 3600
GAP_MAX = 3


def yn(b: bool) -> str:
    return "Y" if b else "n"


def main() -> int:
    lines: list[str] = []

    def emit(s: str = "") -> None:
        print(s)
        lines.append(s)

    by_t: dict[int, FrameInfo] = {}
    for t in range(T_LO - 5, T_HI + 5):
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

    emit(f"=== Per-frame signals + prose for t={T_LO}-{T_HI} ===")
    emit()
    for t in range(T_LO, T_HI + 1):
        f = by_t.get(t)
        if f is None:
            emit(f"-- t={t}: SIDECAR MISSING --")
            emit()
            continue
        s = f.signals
        sa = strong_post_action_match(f.text)
        sa_str = f"STRONG={sa[2]!r}" if sa else "STRONG=-"
        emit(f"-- t={t} | path={f.path} | D={int(f.is_delivery)} | "
             f"V={yn(s.V)} V_post={yn(s.V_post)} S={yn(s.S)} "
             f"M={yn(s.M)} M2={yn(s.M2)} W={yn(s.W)} K={yn(s.K)} "
             f"SS={yn(s.SS)} SS_loose={yn(getattr(s, 'SS_via_loose', False))} "
             f"CG={yn(s.CG)} HARD={yn(s.HARD)} | {sa_str} --")
        prose = f.text.replace("\n", " ").strip()
        emit(f"   prose: {prose[:300]}")
        if len(prose) > 300:
            emit(f"          ... ({len(prose)} total chars)")
        emit()

    # Cluster builder trace replicating build_clusters logic.
    emit(f"=== Cluster builder trace t={T_LO}-{T_HI} (gap_max={GAP_MAX}) ===")
    in_cluster = False
    cluster_start = None
    last_d = None
    gap = 0
    closed: list[tuple[int, int, str]] = []
    for t in range(T_LO, T_HI + 1):
        f = by_t.get(t)
        if f is None:
            emit(f"  t={t}: missing")
            continue
        s = f.signals
        if not in_cluster:
            if s.HARD or not f.is_delivery:
                emit(f"  t={t}: idle (HARD={yn(s.HARD)} D={int(f.is_delivery)} "
                     f"path={f.path})")
                continue
            in_cluster = True
            cluster_start = t
            last_d = t
            gap = 0
            emit(f"  t={t}: OPEN (path={f.path})")
            continue
        if s.HARD:
            emit(f"  t={t}: HARD-REJECT -> close at last_d={last_d}")
            closed.append((cluster_start, last_d, "hard"))
            in_cluster = False
            cluster_start = None
            continue
        if f.is_delivery:
            last_d = t
            gap = 0
            emit(f"  t={t}: extend (path={f.path}), last_d={t}")
            continue
        gap += 1
        if gap > GAP_MAX:
            emit(f"  t={t}: gap>{GAP_MAX} -> close at last_d={last_d}")
            closed.append((cluster_start, last_d, f"gap>{GAP_MAX}"))
            in_cluster = False
            cluster_start = None
            continue
        emit(f"  t={t}: gap={gap} (path={f.path})")
    if in_cluster:
        closed.append((cluster_start, last_d, "window-end"))

    emit()
    emit(f"=== Closed clusters in window: {len(closed)} ===")
    for s_, e_, why in closed:
        run = [by_t[t] for t in range(s_, e_ + 1) if t in by_t]
        deliv = [r for r in run if r.is_delivery]
        any_v = any(r.signals.V for r in run)
        paths = [r.path for r in deliv]
        path_only_c = all(p == "C" for p in paths) if paths else False
        emit(f"  start={s_} end={e_} reason={why} delivery_count={len(deliv)} "
             f"any_V={yn(any_v)} all_C={yn(path_only_c)} paths={paths}")

    emit()
    emit("=== Focus: t=3528 ===")
    f = by_t.get(3528)
    if f is None:
        emit("  3528 sidecar MISSING")
    else:
        s = f.signals
        emit(f"  flags: V={yn(s.V)} V_post={yn(s.V_post)} S={yn(s.S)} "
             f"M={yn(s.M)} M2={yn(s.M2)} W={yn(s.W)} K={yn(s.K)} "
             f"SS={yn(s.SS)} SS_loose={yn(getattr(s, 'SS_via_loose', False))} "
             f"CG={yn(s.CG)} HARD={yn(s.HARD)}")
        k2 = s.K or (s.SS and s.CG)
        emit(f"  k2 fallback = K or (SS and CG) = {yn(k2)}")
        emit("  Path eligibility:")
        emit(f"    A = V & S & (W|M2)        -> {yn(s.V and s.S and (s.W or s.M2))}")
        emit(f"    B = V & M & W & k2 & SS    -> {yn(s.V and s.M and s.W and k2 and s.SS)}")
        emit(f"    C = M2 & W & k2 & SS       -> {yn(s.M2 and s.W and k2 and s.SS)}")
        emit(f"    D = V & M2 & K & SS        -> {yn(s.V and s.M2 and s.K and s.SS)}")
        emit(f"  result: path={f.path} is_delivery={int(f.is_delivery)}")

    emit()
    emit("=== Strong post-action hits anywhere in window ===")
    any_strong = False
    for t in range(T_LO, T_HI + 1):
        f = by_t.get(t)
        if f is None:
            continue
        sa = strong_post_action_match(f.text)
        if sa:
            emit(f"  t={t}: {sa[2]!r}")
            any_strong = True
    if not any_strong:
        emit("  (none)")

    OUT.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
