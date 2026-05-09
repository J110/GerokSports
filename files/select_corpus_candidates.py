"""Select 40 stratified candidate frames for corpus labeling.

Subsets:
  - 18 batter-closeup-with-background: frames within ±5 of a
    boundary/wicket/extra event where Scout tagged cam=bowlers_end
    (high probability of mis-tag)
  - 12 disambiguation patterns: reach into post-wicket windows for
    huddles, pick closeup+between_play frames for walk-backs,
    closeup+fielder_reaction frames, etc.
  - 10 active-play recall control: frames 0-2 before a ball_event
    where Scout tagged cam=bowlers_end + phase=release
"""
from __future__ import annotations
import json
import random
from collections import defaultdict

random.seed(42)  # reproducibility

INV = "corpus_frame_inventory.json"
OUT = "corpus_candidates.json"

with open(INV) as f:
    inv = json.load(f)

frames = {r["frame_count"]: r for r in inv["frames"]}
events = inv["events"]

# Only consider frames that actually exist on disk as SCOREBOARD
# (imwrite paths — others are pixskip and can't be viewed).
scoreboard_frames = {
    fc: r for fc, r in frames.items()
    if r["scout_frame_type"] == "SCOREBOARD"
}
print(f"scoreboard frames available: {len(scoreboard_frames)}")


def frames_near_event(event_fc: int, window: int = 8,
                      direction: str = "both") -> list[dict]:
    """Return SCOREBOARD frames within `window` of event_fc."""
    out = []
    for fc, r in sorted(scoreboard_frames.items()):
        d = fc - event_fc
        if direction == "after" and d < 0:
            continue
        if direction == "before" and d > 0:
            continue
        if abs(d) <= window:
            out.append((d, r))
    return out


key_events = [(e["frame_count"], e["event"]) for e in events
              if e["event"] in ("WICKET", "FOUR", "SIX", "EXTRA")]
print(f"key events (wicket/boundary/extra): {len(key_events)}")

# ============================================================
# Subset 1 — batter_closeup_with_background  (target: 18)
# ============================================================
# Heuristic: frames in the 0-to-+6 window after a WICKET/FOUR/SIX/EXTRA
# event, where Scout tagged cam=bowlers_end.  The +0 to +6 window
# captures the reaction / celebration / between-deliveries camera
# cuts that are the dominant failure mode.
s1_candidates = []
seen = set()
for fc, ev in key_events:
    for delta, r in frames_near_event(fc, window=10, direction="after"):
        if delta < 2:  # skip event frame + delivery-adjacent (those belong to subset 3)
            continue
        if r["scout_cam"] != "bowlers_end":
            continue
        if r["frame_count"] in seen:
            continue
        seen.add(r["frame_count"])
        s1_candidates.append({
            "frame_count": r["frame_count"],
            "rationale": (f"+{delta} frames after {ev} @ F{fc}; "
                          f"scout={r['scout_cam']}/{r['scout_phase']}"),
            "near_event": ev,
            "near_event_fc": fc,
            "delta_frames": delta,
            "subset": "batter_closeup_with_background",
            "scout_cam": r["scout_cam"],
            "scout_phase": r["scout_phase"],
            "frame_path": r["frame_path"],
        })

print(f"\n=== subset 1 (closeup-heavy): "
      f"{len(s1_candidates)} candidates ===")
# Prefer diversity across different events.
by_event = defaultdict(list)
for c in s1_candidates:
    by_event[c["near_event_fc"]].append(c)
# Round-robin sample up to 18, preferring 1-2 per event for spread.
s1_selected = []
max_per_event = 3
for c_list in by_event.values():
    c_list.sort(key=lambda x: x["delta_frames"])  # nearest first
for _ in range(max_per_event):
    for fc in list(by_event.keys()):
        if by_event[fc]:
            s1_selected.append(by_event[fc].pop(0))
            if len(s1_selected) >= 18:
                break
    if len(s1_selected) >= 18:
        break
# Pad if under 18 by taking remaining candidates.
remaining = [c for c_list in by_event.values() for c in c_list]
random.shuffle(remaining)
for c in remaining:
    if len(s1_selected) >= 18:
        break
    s1_selected.append(c)
s1_selected = s1_selected[:18]
print(f"  selected: {len(s1_selected)}")
for c in s1_selected:
    print(f"    F{c['frame_count']:4d}  {c['rationale']}")

# ============================================================
# Subset 2 — disambiguation  (target: 12, 2 each of 6 patterns)
# ============================================================
# Scout's already-closeup tag captures some patterns (walk-back,
# reaction).  Post-wicket huddle should be in +0 to +10 after WICKET.
# Graphic frames are Scout-tagged `graphic`.  Other patterns (umpire
# consult, crowd, dugout, batter-striker-closeup) need to be picked
# by inspection; we'll pre-select closeup-tagged and between_play-
# tagged frames as candidates and classify during labelling.

# Pattern A — post-wicket huddle: 6 frames after each WICKET, any tag
s2_huddle = []
for fc, ev in key_events:
    if ev != "WICKET":
        continue
    for delta, r in frames_near_event(fc, window=10, direction="after"):
        s2_huddle.append({
            "frame_count": r["frame_count"],
            "rationale": f"+{delta} frames after WICKET @ F{fc}",
            "near_event": "WICKET",
            "near_event_fc": fc,
            "delta_frames": delta,
            "subset": "disambiguation",
            "candidate_pattern": "post_wicket_huddle",
            "scout_cam": r["scout_cam"],
            "scout_phase": r["scout_phase"],
            "frame_path": r["frame_path"],
        })

# Pattern B — bowler walk-back / closeup during between_play
s2_bowler_walkback = []
for fc, r in sorted(scoreboard_frames.items()):
    if (r["scout_cam"] == "closeup"
            and r["scout_phase"] == "between_play"):
        s2_bowler_walkback.append({
            "frame_count": fc,
            "rationale": "scout=closeup/between_play (likely walk-back or reaction)",
            "near_event": None,
            "near_event_fc": None,
            "delta_frames": None,
            "subset": "disambiguation",
            "candidate_pattern": "closeup_between_play",
            "scout_cam": r["scout_cam"],
            "scout_phase": r["scout_phase"],
            "frame_path": r["frame_path"],
        })

# Pattern C — graphic overlay frames (Scout-tagged graphic)
s2_graphic = []
for fc, r in sorted(scoreboard_frames.items()):
    if r["scout_cam"] == "graphic":
        s2_graphic.append({
            "frame_count": fc,
            "rationale": "scout=graphic (overlay / stats graphic)",
            "near_event": None,
            "near_event_fc": None,
            "delta_frames": None,
            "subset": "disambiguation",
            "candidate_pattern": "graphic_overlay",
            "scout_cam": r["scout_cam"],
            "scout_phase": r["scout_phase"],
            "frame_path": r["frame_path"],
        })

# Pattern D — closeup+fielder_reaction
s2_fielder = []
for fc, r in sorted(scoreboard_frames.items()):
    if (r["scout_cam"] == "closeup"
            and r["scout_phase"] == "fielder_reaction"):
        s2_fielder.append({
            "frame_count": fc,
            "rationale": "scout=closeup/fielder_reaction",
            "near_event": None,
            "near_event_fc": None,
            "delta_frames": None,
            "subset": "disambiguation",
            "candidate_pattern": "closeup_fielder_reaction",
            "scout_cam": r["scout_cam"],
            "scout_phase": r["scout_phase"],
            "frame_path": r["frame_path"],
        })

# Pattern E — bowlers_end + between_play (suspicious combo — likely
# a non-action frame misclassified as bowlers_end camera).  Also
# bowlers_end + post_shot / fielder_reaction are suspicious.
s2_suspicious_combo = []
for fc, r in sorted(scoreboard_frames.items()):
    if (r["scout_cam"] == "bowlers_end"
            and r["scout_phase"] in ("between_play", "post_shot",
                                     "fielder_reaction")):
        s2_suspicious_combo.append({
            "frame_count": fc,
            "rationale": (f"scout=bowlers_end/{r['scout_phase']} "
                          f"(suspicious combo)"),
            "near_event": None,
            "near_event_fc": None,
            "delta_frames": None,
            "subset": "disambiguation",
            "candidate_pattern": "suspicious_combo",
            "scout_cam": r["scout_cam"],
            "scout_phase": r["scout_phase"],
            "frame_path": r["frame_path"],
        })

print(f"\n=== subset 2 (disambiguation) candidate pools ===")
print(f"  post_wicket_huddle:      {len(s2_huddle)}")
print(f"  closeup_between_play:    {len(s2_bowler_walkback)}")
print(f"  graphic_overlay:         {len(s2_graphic)}")
print(f"  closeup_fielder_react:   {len(s2_fielder)}")
print(f"  suspicious_combo:        {len(s2_suspicious_combo)}")

# Pick 2-3 from each pool, dedup against subset 1.
s1_fcs = {c["frame_count"] for c in s1_selected}
s2_selected = []
for pool, n in [(s2_huddle, 3),
                (s2_bowler_walkback, 5),  # pad: fielder_react pool is empty
                (s2_graphic, 2),
                (s2_fielder, 2),
                (s2_suspicious_combo, 2)]:
    picked = 0
    random.shuffle(pool)
    for c in pool:
        if c["frame_count"] in s1_fcs:
            continue
        if any(x["frame_count"] == c["frame_count"] for x in s2_selected):
            continue
        s2_selected.append(c)
        picked += 1
        if picked >= n:
            break

print(f"  selected: {len(s2_selected)}")
for c in s2_selected:
    print(f"    F{c['frame_count']:4d}  [{c['candidate_pattern']}]  "
          f"{c['rationale']}")

# ============================================================
# Subset 3 — active-play recall control  (target: 10)
# ============================================================
# Frames 0 to -2 before a ball_event where scout=bowlers_end/release.
# These are the "moment of delivery" frames; any recall loss here is
# meaningful (it'd be a real delivery Scout fails to verify).
s3_candidates = []
for fc, ev in key_events:
    if ev not in ("FOUR", "SIX", "WICKET", "DOT", "EXTRA"):
        continue
    for delta, r in frames_near_event(fc, window=2, direction="before"):
        if (r["scout_cam"] == "bowlers_end"
                and r["scout_phase"] == "release"):
            s3_candidates.append({
                "frame_count": r["frame_count"],
                "rationale": (f"{delta} frames before {ev} @ F{fc}; "
                              f"scout=bowlers_end/release (active-play)"),
                "near_event": ev,
                "near_event_fc": fc,
                "delta_frames": delta,
                "subset": "active_play_recall",
                "scout_cam": r["scout_cam"],
                "scout_phase": r["scout_phase"],
                "frame_path": r["frame_path"],
            })

# Also include the ball_event frame itself if it's a SCOREBOARD frame
for fc, ev in key_events:
    r = scoreboard_frames.get(fc)
    if r and r["scout_cam"] == "bowlers_end":
        s3_candidates.append({
            "frame_count": fc,
            "rationale": (f"on {ev} event frame; "
                          f"scout={r['scout_cam']}/{r['scout_phase']}"),
            "near_event": ev,
            "near_event_fc": fc,
            "delta_frames": 0,
            "subset": "active_play_recall",
            "scout_cam": r["scout_cam"],
            "scout_phase": r["scout_phase"],
            "frame_path": r["frame_path"],
        })

# Dedup against s1/s2 and pick 10 spread across events
taken_fcs = {c["frame_count"] for c in s1_selected + s2_selected}
s3_candidates = [c for c in s3_candidates
                 if c["frame_count"] not in taken_fcs]
# Dedup within s3
seen = set()
s3_unique = []
for c in s3_candidates:
    if c["frame_count"] in seen:
        continue
    seen.add(c["frame_count"])
    s3_unique.append(c)

# Spread across different events
by_evfc = defaultdict(list)
for c in s3_unique:
    by_evfc[c["near_event_fc"]].append(c)
s3_selected = []
while len(s3_selected) < 10:
    progress = False
    for fc in list(by_evfc.keys()):
        if by_evfc[fc]:
            s3_selected.append(by_evfc[fc].pop(0))
            progress = True
            if len(s3_selected) >= 10:
                break
    if not progress:
        break

print(f"\n=== subset 3 (recall control) ===")
print(f"  candidates: {len(s3_unique)}, selected: {len(s3_selected)}")
for c in s3_selected:
    print(f"    F{c['frame_count']:4d}  {c['rationale']}")

# ============================================================
# Total
# ============================================================
all_selected = s1_selected + s2_selected + s3_selected
print(f"\n=== TOTAL: {len(all_selected)} frames ===")
subset_counts = defaultdict(int)
for c in all_selected:
    subset_counts[c["subset"]] += 1
for k, v in subset_counts.items():
    print(f"  {k}: {v}")

targets = {
    "batter_closeup_with_background": 18,
    "disambiguation": 12,
    "active_play_recall": 10,
}
pool_counts = {
    "batter_closeup_with_background": len(s1_candidates),
    "disambiguation": (
        len(s2_huddle) + len(s2_bowler_walkback) + len(s2_graphic)
        + len(s2_fielder) + len(s2_suspicious_combo)),
    "active_play_recall": len(s3_unique),
}
bucket_coverage = []
print("\n=== BUCKET COVERAGE ===")
for bucket, target in targets.items():
    pool = pool_counts.get(bucket, 0)
    sampled = subset_counts.get(bucket, 0)
    status = "OK"
    reason = ""
    if pool > 0 and sampled == 0:
        status = "WARN"
        reason = f"pool={pool}, sampled=0"
    elif sampled < min(pool, target):
        status = "WARN"
        reason = f"pool={pool}, sampled={sampled}, target={target}"
    bucket_coverage.append({
        "bucket": bucket,
        "pool": pool,
        "sampled": sampled,
        "target": target,
        "status": status,
        "reason": reason,
    })
    marker = "[BUCKET-COVERAGE]" if status == "WARN" else "bucket"
    print(f"  {marker} {bucket}: pool={pool} sampled={sampled} "
          f"target={target}" + (f" reason={reason}" if reason else ""))

with open(OUT, "w") as f:
    json.dump({
        "candidates": all_selected,
        "targets": targets,
        "bucket_coverage": bucket_coverage,
    }, f, indent=2)
print(f"\nWrote {OUT}")
