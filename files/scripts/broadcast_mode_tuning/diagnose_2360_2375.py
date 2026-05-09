#!/usr/bin/env python3
"""Dump V/V_post + cluster builder state for t=2360-2375 to diagnose
the c52 (anchor 2365) cluster that V_post filter dropped."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from signal_extraction import (  # noqa: E402
    extract_signals, V_PATTERNS, V_POST_PATTERNS, V_LOOSE_PATTERNS,
    NEGATION_BEFORE_PAT,
)
from delivery_classifier import FrameInfo, annotate  # noqa: E402

SC = REPO_ROOT / "files/scripts/broadcast_mode_tuning/eighth_5min_scout_run"
OUT = REPO_ROOT / "files/scripts/broadcast_mode_tuning/diagnose_2360_2375.txt"

T_LO = 2360
T_HI = 2375
GAP_MAX = 3


def yn(b: bool) -> str:
    return "Y" if b else "n"


def matches(text: str, patterns):
    hits = []
    for p in patterns:
        for m in p.finditer(text):
            prefix = text[max(0, m.start() - 30): m.start()]
            negated = bool(NEGATION_BEFORE_PAT.search(prefix))
            hits.append((p.pattern, m.group(0), negated))
    return hits


def main() -> int:
    lines: list[str] = []

    def emit(s: str = "") -> None:
        print(s)
        lines.append(s)

    by_t: dict[int, FrameInfo] = {}
    for t in range(2300, 2400):
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

    emit(f"=== Per-frame V / V_post + prose for t={T_LO}-{T_HI} ===")
    emit()
    for t in range(T_LO, T_HI + 1):
        f = by_t.get(t)
        if f is None:
            continue
        s = f.signals
        v_hits = matches(f.text, V_PATTERNS)
        vpost_hits = matches(f.text, V_POST_PATTERNS)
        v_only_pats = {p for p, _, _ in v_hits}
        vl_extra = [(p, ph, n) for p, ph, n in matches(f.text, V_LOOSE_PATTERNS)
                    if p not in v_only_pats]
        emit(f"-- t={t} | path={f.path} | D={int(f.is_delivery)} | "
             f"V={yn(s.V)} V_post={yn(s.V_post)} | M2={yn(s.M2)} "
             f"W={yn(s.W)} K={yn(s.K)} SS={yn(s.SS)} HARD={yn(s.HARD)} --")
        if v_hits:
            emit("   V matches:")
            for pat, phrase, neg in v_hits:
                flag = " [NEGATED]" if neg else ""
                emit(f"     '{phrase}'{flag}  via  {pat}")
        else:
            emit("   V matches: (none)")
        if vpost_hits:
            emit("   V_post matches:")
            for pat, phrase, neg in vpost_hits:
                flag = " [NEGATED]" if neg else ""
                emit(f"     '{phrase}'{flag}  via  {pat}")
        else:
            emit("   V_post matches: (none)")
        if vl_extra:
            emit("   V_loose-only (pre-action) matches:")
            for pat, phrase, neg in vl_extra:
                flag = " [NEGATED]" if neg else ""
                emit(f"     '{phrase}'{flag}  via  {pat}")
        emit("   prose:")
        for ln in f.text.splitlines():
            emit(f"     {ln}")
        emit()

    # Cluster builder trace
    emit(f"=== Cluster builder trace t={T_LO}-{T_HI} ===")
    in_cluster = False
    cluster_start = None
    last_d = None
    gap = 0
    closed = []
    for t in range(T_LO, T_HI + 1):
        f = by_t.get(t)
        if f is None:
            continue
        s = f.signals
        if not in_cluster:
            if s.HARD or not f.is_delivery:
                emit(f"  t={t}: idle (HARD={yn(s.HARD)} D={int(f.is_delivery)} "
                     f"path={f.path} V_post={yn(s.V_post)})")
                continue
            in_cluster = True
            cluster_start = t
            last_d = t
            gap = 0
            emit(f"  t={t}: OPEN (path={f.path} V_post={yn(s.V_post)})")
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
            emit(f"  t={t}: extend (path={f.path} V_post={yn(s.V_post)}), last_d={t}")
            continue
        gap += 1
        if gap > GAP_MAX:
            emit(f"  t={t}: gap>{GAP_MAX} -> close at last_d={last_d}")
            closed.append((cluster_start, last_d, f"gap>{GAP_MAX}"))
            in_cluster = False
            cluster_start = None
            continue
        emit(f"  t={t}: gap={gap} (path={f.path} V_post={yn(s.V_post)})")
    if in_cluster:
        closed.append((cluster_start, last_d, "window-end"))

    emit()
    emit(f"=== Closed clusters: {len(closed)} ===")
    for s_, e_, why in closed:
        n_d = sum(1 for t in range(s_, e_ + 1)
                  if by_t.get(t) and by_t[t].is_delivery)
        any_vp = any(by_t[t].signals.V_post for t in range(s_, e_ + 1)
                     if by_t.get(t))
        any_v = any(by_t[t].signals.V for t in range(s_, e_ + 1)
                    if by_t.get(t))
        emit(f"  start={s_} end={e_} reason={why} delivery_count={n_d} "
             f"any_V={yn(any_v)} any_V_post={yn(any_vp)}")

    OUT.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
