"""Simulate RC-7 phase gate over historical window_debug.json corpus.

Purpose: give the Part A validation rollup a second broadcast context
beyond post-restart MI-vs-CSK innings 2. Reads every saved
window_debug.json under logs/deliveries/, examines the bowlers_end tags
that were present near each delivery, and reports what RC-7's filter
would have done.

Output:
  - Per-session aggregates (match_dir → counts)
  - Global phase distribution of bowlers_end tags
  - Per-session "would-have-been-rejected" rate
  - Distribution of non-action phases (post_shot / between_play / ...)
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ACTION_PHASES = {"release", "flight", "shot", "runup"}
DELIVERIES_ROOT = Path(
    "/Users/anmolmohan/Projects/SportsComm/files/logs/deliveries")


def load_windows() -> list[dict]:
    rows = []
    for wd in DELIVERIES_ROOT.rglob("window_debug.json"):
        try:
            with open(wd) as f:
                d = json.load(f)
            d["_session"] = wd.parent.parent.name  # 20260421_195050
            d["_dir"] = wd.parent.name  # d024
            rows.append(d)
        except Exception:
            pass
    return rows


def analyze(rows: list[dict]) -> None:
    print(f"Total windows loaded: {len(rows)}\n")

    # ── Global source distribution ──────────────────────────
    src = Counter(r.get("window_source") for r in rows)
    print("=== Historical window source distribution ===")
    for k, v in src.most_common():
        print(f"  {k:40s} {v:4d} ({100*v/len(rows):5.1f}%)")
    print()

    # ── bowlers_end tag phase distribution ───────────────────
    # Inspect every bowlers_end tag found within any window's clip
    # bounds. These are the tags that pre-RC-7 DWR considered as
    # potential anchors.
    phase_counter = Counter()
    per_session_tags: dict[str, Counter] = defaultdict(Counter)
    # For each window, identify which phase tag would have been the
    # anchor: the latest bowlers_end tag within the clip (since
    # span_end = last bowlers_end_ts, which seeds the anchor in the
    # reversed walk).
    anchor_phases: list[str] = []
    anchor_phases_by_session: dict[str, list[str]] = defaultdict(list)
    # Only score "retrospective_span" windows — fallback windows didn't
    # have an anchor tag to begin with, so they're not informative for
    # RC-7 simulation (they'd still fall back).
    retro_rows = [r for r in rows
                  if r.get("window_source") == "retrospective_span"]
    print(f"retrospective_span windows (had a bowlers_end anchor): "
          f"{len(retro_rows)}")
    print(f"fallback_* windows (no anchor): "
          f"{len(rows) - len(retro_rows)}\n")

    for r in retro_rows:
        tags = r.get("tags") or []
        be_tags = [t for t in tags
                   if (t.get("camera_view") or "").lower() == "bowlers_end"]
        if not be_tags:
            # Retrospective span without bowlers_end tags in the clip
            # range is odd — ignore for now.
            continue
        # Anchor = latest bowlers_end tag (span_end seed).
        anchor = max(be_tags, key=lambda t: t["ts"])
        ph = (anchor.get("frame_phase") or "none").lower()
        anchor_phases.append(ph)
        anchor_phases_by_session[r["_session"]].append(ph)
        for t in be_tags:
            phase_counter[(t.get("frame_phase") or "none").lower()] += 1
            per_session_tags[r["_session"]][
                (t.get("frame_phase") or "none").lower()] += 1

    # ── Global anchor-phase distribution (the one that matters) ─────
    print("=== ANCHOR phase distribution (latest bowlers_end tag per "
          "retrospective window) ===")
    total = len(anchor_phases)
    anchor_counter = Counter(anchor_phases)
    for k, v in anchor_counter.most_common():
        action = " (action)" if k in ACTION_PHASES else " (REJECT by RC-7)"
        print(f"  {k:25s} {v:4d} ({100*v/total:5.1f}%){action}")
    rejected = sum(v for k, v in anchor_counter.items()
                   if k not in ACTION_PHASES)
    print(f"\nTotal retrospective windows simulated: {total}")
    print(f"Would be PHASE-REJECTed: {rejected} ({100*rejected/total:.2f}%)")
    print()

    # ── Per-session anchor-phase rejection rate ────────────────────
    print("=== Per-session rejection rate (anchor non-action) ===")
    print(f"{'session':25s} {'n':>6s} {'reject':>8s} {'%':>7s}  "
          f"non-action phases")
    for sess in sorted(anchor_phases_by_session.keys()):
        phases = anchor_phases_by_session[sess]
        n = len(phases)
        rej = [p for p in phases if p not in ACTION_PHASES]
        n_rej = len(rej)
        pct = 100 * n_rej / n if n else 0
        non_action_dist = Counter(rej).most_common()
        breakdown = ", ".join(f"{p}={c}" for p, c in non_action_dist) or "-"
        print(f"  {sess:25s} {n:6d} {n_rej:8d} {pct:6.1f}%  {breakdown}")
    print()

    # ── Full tag phase distribution (all bowlers_end tags) ─────────
    print("=== ALL bowlers_end tags phase distribution ===")
    total_be = sum(phase_counter.values())
    for k, v in phase_counter.most_common():
        action = " (action)" if k in ACTION_PHASES else ""
        print(f"  {k:25s} {v:5d} ({100*v/total_be:5.1f}%){action}")
    print()

    # ── Fall-through simulation ────────────────────────────────
    # For each window that would be rejected on anchor, check if an
    # earlier bowlers_end tag with an action phase exists within the
    # clip — that would be RC-7's fall-through outcome. (This is a
    # conservative estimate because the real `_find_span` looks back
    # further than the clip bounds.)
    fall_through_ok = 0
    fall_through_miss = 0
    for r in retro_rows:
        tags = r.get("tags") or []
        be_tags = [t for t in tags
                   if (t.get("camera_view") or "").lower() == "bowlers_end"]
        if not be_tags:
            continue
        anchor = max(be_tags, key=lambda t: t["ts"])
        ph = (anchor.get("frame_phase") or "none").lower()
        if ph in ACTION_PHASES:
            continue
        # Anchor would be rejected — is there an earlier action-phase tag?
        earlier_action = [
            t for t in be_tags
            if t["ts"] < anchor["ts"]
            and (t.get("frame_phase") or "").lower() in ACTION_PHASES
        ]
        if earlier_action:
            fall_through_ok += 1
        else:
            fall_through_miss += 1
    total_rej = fall_through_ok + fall_through_miss
    if total_rej:
        print(f"=== Fall-through outcome for {total_rej} "
              f"hypothetically-rejected anchors ===")
        print(f"  fall-through to earlier action-phase tag: "
              f"{fall_through_ok} "
              f"({100*fall_through_ok/total_rej:.1f}%)")
        print(f"  no earlier action tag → would fall back to raw-buffer: "
              f"{fall_through_miss} "
              f"({100*fall_through_miss/total_rej:.1f}%)")
    print()


if __name__ == "__main__":
    rows = load_windows()
    analyze(rows)
