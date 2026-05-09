#!/usr/bin/env python3
"""Dump V / V_post / V_loose status with matched-pattern phrases for
the c49 (t=2256) and c50 (t=2347) regions in eighth_5min_scout_run."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from signal_extraction import (  # noqa: E402
    extract_signals, V_PATTERNS, V_POST_PATTERNS, V_LOOSE_PATTERNS,
    NEGATION_BEFORE_PAT, v_match, v_post_match,
)
from delivery_classifier import FrameInfo, annotate  # noqa: E402

SC = REPO_ROOT / "files/scripts/broadcast_mode_tuning/eighth_5min_scout_run"
OUT = REPO_ROOT / "files/scripts/broadcast_mode_tuning/diagnose_v_post_2256_2347.txt"

WINDOWS = [
    (2245, 2260, "c49 region — anchor t=2256 path=A"),
    (2340, 2360, "c50 region — anchor t=2347 path=A"),
]


def yn(b: bool) -> str:
    return "Y" if b else "n"


def matches_with_negation(text: str, patterns) -> list[tuple[str, str, bool]]:
    """For each pattern, find all matches and report (pattern_repr,
    matched_phrase, negated)."""
    hits: list[tuple[str, str, bool]] = []
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
    for t in range(2100, 2400):
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
        emit(f"=== {title} (t={lo}-{hi}) ===")
        emit()
        for t in range(lo, hi + 1):
            f = by_t.get(t)
            if f is None:
                continue
            s = f.signals
            v_hits = matches_with_negation(f.text, V_PATTERNS)
            vpost_hits = matches_with_negation(f.text, V_POST_PATTERNS)
            vloose_hits = matches_with_negation(f.text, V_LOOSE_PATTERNS)

            emit(f"-- t={t} | path={f.path} | D={int(f.is_delivery)} | "
                 f"V={yn(s.V)} V_post={yn(s.V_post)} | M2={yn(s.M2)} "
                 f"W={yn(s.W)} K={yn(s.K)} SS={yn(s.SS)} --")
            if v_hits:
                emit(f"   V matches:")
                for pat, phrase, neg in v_hits:
                    flag = " [NEGATED]" if neg else ""
                    emit(f"     '{phrase}'{flag}  via  {pat}")
            else:
                emit("   V matches: (none)")
            if vpost_hits:
                emit(f"   V_post matches:")
                for pat, phrase, neg in vpost_hits:
                    flag = " [NEGATED]" if neg else ""
                    emit(f"     '{phrase}'{flag}  via  {pat}")
            else:
                emit("   V_post matches: (none)")
            # Show V_loose-only hits (not in V) to surface pre-action language
            v_only = {p for p, _, _ in v_hits}
            vl_only = [(p, ph, n) for p, ph, n in vloose_hits if p not in v_only]
            if vl_only:
                emit(f"   V_loose-only (pre-action) matches:")
                for pat, phrase, neg in vl_only:
                    flag = " [NEGATED]" if neg else ""
                    emit(f"     '{phrase}'{flag}  via  {pat}")
            # Prose excerpt (first 250 chars)
            prose_one_line = f.text.replace("\n", " ").strip()
            emit(f"   prose: {prose_one_line[:250]}")
            if len(prose_one_line) > 250:
                emit(f"          ... ({len(prose_one_line)} total chars)")
            emit()

    OUT.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
