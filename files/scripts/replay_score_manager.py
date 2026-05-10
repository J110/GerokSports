"""Replay last night's pipeline DETAIL log through the post-D1..D7
ScoreManager and tally marker firings.

Reads the cluster pipeline log line-by-line, extracts per-frame
broadcast/extractor signal from the DETAIL|F<N>|SCOREBOARD records,
reconstructs a `FrameInput`, and feeds them sequentially through a
fresh `ScoreManager` running in shadow mode (no Scoreboard attached).
A logging handler captures every SM log line into
`files/logs/replay-rr-vs-gt-derived.log` and counts the D1..D7
marker substrings on the fly.

Caveats (intentional, see replay_validation_rr_gt.md):
  * Shadow-mode SM uses `_sm_scalar_fallback` for score/wickets so
    properties read back what we wrote — Scoreboard side channels
    (delivery analyzer, ball-event emission, name canonicalization)
    are NOT reproduced.
  * BALL EVENT counts not validated.
  * Final-state cricbuzz diff not produced (manual follow-up).

Usage:
    python files/scripts/replay_score_manager.py \\
        --in files/logs/pipeline-20260509-rr-vs-gt-52nd-match.log \\
        --out files/logs/replay-rr-vs-gt-derived.log
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from score_manager import FrameInput, ScoreManager  # noqa: E402


# DETAIL header: "DETAIL|F<N>|<TAG>|tag=...|scout=STRIP: <strip>|action=..."
_DETAIL_RE = re.compile(r"DETAIL\|F(\d+)\|([A-Z_]+)\|tag=")
# scout=STRIP: <segment1> | extras=...
_STRIP_RE = re.compile(r"scout=STRIP:\s*([^|]*)\|\s*extras=")
# Strip first segment: "<TEAM> <SCORE>-<WICKETS> (<OVERS>)" with optional "null"
_TEAM_SCORE_RE = re.compile(
    r"^\s*([A-Za-z]{2,5}|null)\s+([0-9]+|null)-([0-9]+|null)\s*\(([0-9.]+|null)\)")
# ext_score=<S>-<W>(<O>)
_EXT_RE = re.compile(r"ext_score=([^|]+?)\|")
_EXT_TRIPLE_RE = re.compile(
    r"^(None|[0-9]+)-(None|[0-9]+)\(\s*(None|[0-9.]+)\s*\)\s*$")
# AFTER_target=<n> (broadcast target arrived previously); we use this
# only as a back-fill heuristic — when SM commits target on prior frame
# the cluster keeps echoing it.
_AFTER_TARGET_RE = re.compile(r"\|AFTER_target=([^|]+)\|")


@dataclass
class ParsedFrame:
    frame_id: int
    tag: str
    broadcast_team: str | None
    ext_score: int | None
    ext_wickets: int | None
    ext_overs: float | None
    target: int | None
    scout_text: str


def _opt_int(s: str | None) -> int | None:
    if not s or s.strip() in ("null", "None", "—"):
        return None
    try:
        return int(s.strip())
    except ValueError:
        return None


def _opt_float(s: str | None) -> float | None:
    if not s or s.strip() in ("null", "None", "—"):
        return None
    try:
        return float(s.strip())
    except ValueError:
        return None


def parse_detail_line(line: str) -> ParsedFrame | None:
    m = _DETAIL_RE.search(line)
    if not m:
        return None
    fid = int(m.group(1))
    tag = m.group(2)

    # ext_score primary source
    ext_s = ext_w = None
    ext_o = None
    em = _EXT_RE.search(line)
    if em:
        triple = _EXT_TRIPLE_RE.match(em.group(1).strip())
        if triple:
            ext_s = _opt_int(triple.group(1))
            ext_w = _opt_int(triple.group(2))
            ext_o = _opt_float(triple.group(3))

    # Scout strip → broadcast_team (and ext_* fallback when ext is null)
    bteam = None
    sm = _STRIP_RE.search(line)
    strip_seg = sm.group(1) if sm else ""
    if strip_seg:
        tm = _TEAM_SCORE_RE.match(strip_seg)
        if tm:
            t = tm.group(1)
            if t and t != "null":
                bteam = t
            if ext_s is None:
                ext_s = _opt_int(tm.group(2))
            if ext_w is None:
                ext_w = _opt_int(tm.group(3))
            if ext_o is None:
                ext_o = _opt_float(tm.group(4))

    # Target
    target = None
    tgt_m = _AFTER_TARGET_RE.search(line)
    if tgt_m:
        target = _opt_int(tgt_m.group(1))

    return ParsedFrame(
        frame_id=fid, tag=tag, broadcast_team=bteam,
        ext_score=ext_s, ext_wickets=ext_w, ext_overs=ext_o,
        target=target, scout_text=strip_seg.strip())


# Markers to count in the replay-emitted SM log lines.
MARKER_PATTERNS = {
    "D1+D2+D3 inn1_impossible_wickets_overs":
        "inn1_impossible_wickets_overs",
    "D1+D2+D3 inn1_severe_collapse_implausible":
        "inn1_severe_collapse_implausible",
    "D1+D2+D3 inn1_score_too_low_for_wickets":
        "inn1_score_too_low_for_wickets",
    "D5 large overs regression force re-COLD_START":
        "Overs LARGE regression",
    "D5 regression streak force re-COLD_START":
        "Regression streak",
    "D7 team-change deferred":
        "team-change candidate",
    "D7 team-change consensus committed":
        "team-change consensus committed",
    "(legacy) Overs regression deferred":
        "Overs regression",
    "(legacy) cold-start reject":
        "cold-start reject",
}


def _install_capture(out_path: str) -> tuple[Counter, callable]:
    """Patch CricketLogger._log to mirror every SM log line into
    out_path and tally marker substrings. Returns (counter, restore_fn).
    """
    from eyes import cricket_logger as cl  # noqa: WPS433

    counts: Counter = Counter()
    fp = open(out_path, "w")
    orig_log = cl.CricketLogger._log

    def patched(self, level, msg):
        try:
            line = f"[F{self.frame} {self.component}] {level}: {msg}"
            fp.write(line + "\n")
            for label, needle in MARKER_PATTERNS.items():
                if needle in msg:
                    counts[label] += 1
        except Exception:
            pass
        # Skip console — replay is silent for noise control.

    cl.CricketLogger._log = patched

    def restore():
        cl.CricketLogger._log = orig_log
        fp.close()

    return counts, restore


def replay(in_path: str, out_path: str) -> Counter:
    counts, restore = _install_capture(out_path)
    try:
        sm = ScoreManager(shadow=True)
        sm._innings_fallback = 1

        parsed_count = 0
        fed_count = 0
        last_frame_id = 0
        with open(in_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                pf = parse_detail_line(line)
                if pf is None:
                    continue
                parsed_count += 1
                last_frame_id = pf.frame_id
                # Update CricketLogger's global frame counter so
                # captured log lines carry the correct frame_id.
                from eyes import cricket_logger as cl
                cl.set_global_frame(pf.frame_id)
                frame = FrameInput(
                    frame_id=f"F{pf.frame_id}",
                    timestamp=float(pf.frame_id),
                    ext_score=pf.ext_score,
                    ext_wickets=pf.ext_wickets,
                    ext_overs=pf.ext_overs,
                    broadcast_team=pf.broadcast_team,
                    broadcast_target=pf.target,
                    scout_text=pf.scout_text,
                )
                try:
                    sm.on_frame(frame)
                    fed_count += 1
                except Exception as e:  # noqa: BLE001
                    pass
    finally:
        restore()

    print(f"parsed_detail_lines={parsed_count} fed={fed_count} "
          f"last_frame=F{last_frame_id}")
    print("MARKER COUNTS:")
    for label, _ in MARKER_PATTERNS.items():
        print(f"  {label:55s} {counts.get(label, 0):>6d}")
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--out", dest="out_path", required=True)
    args = ap.parse_args()
    replay(args.in_path, args.out_path)


if __name__ == "__main__":
    main()
