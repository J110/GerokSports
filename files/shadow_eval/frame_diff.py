"""Per-frame diff across variants — what actually changed?

Prints, per frame, the V0/V1/V2a/V2b/V3 majority-vote cam tags
alongside the human label, focusing on frames where any variant
differs from V0.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_FILES = _HERE.parent
sys.path.insert(0, str(_FILES))

corpus = json.load((_FILES / "docs/scout_corpus_v1.json").open())["frames"]
shadow = json.load((_FILES / "docs/shadow_run_v1.json").open())["results"]

# Build (frame_id, variant) -> majority vote cam
votes: dict[tuple[str, str], str | None] = {}
for r in shadow:
    votes.setdefault((r["frame_id"], r["variant"]), []).append(r["canon_camera_view"])

vote_cam: dict[tuple[str, str], str | None] = {}
for k, v in votes.items():
    non_null = [x for x in v if x is not None]
    vote_cam[k] = Counter(non_null).most_common(1)[0][0] if non_null else None

variants = ["V1", "V2a", "V2b", "V3", "V4", "V4b", "V5"]

# Find frames where at least one variant differs from V0.
hdr = (f"{'FID':6} {'subset':28} {'human':11} {'V0':11} "
       + " ".join(f"{v:11}" for v in variants) + "  changed")
print(hdr)
print("-" * len(hdr))

changed = 0
good_shifts = 0
bad_shifts = 0
for f in corpus:
    fid = f["frame_id"]
    v0 = f["scout_cam_original"]
    vs = {v: vote_cam.get((fid, v)) for v in variants}
    if all(vs[v] == v0 for v in variants):
        continue
    changed += 1
    row = (f"{fid:6} {f['subset'][:28]:28} "
           f"{f['human_camera_view']:11} {v0 or '-':11} "
           + " ".join(f"{(vs[v] or '-'):11}" for v in variants))
    # evaluate whether any shift was good (v -> human label)
    shifted_toward_truth = []
    for v in variants:
        if vs[v] != v0:
            if vs[v] == f["human_camera_view"]:
                shifted_toward_truth.append(v)
            elif v0 == f["human_camera_view"]:
                # v0 was right; shift is a regression
                shifted_toward_truth.append(f"-{v}")
    if shifted_toward_truth:
        flag = " | " + ",".join(shifted_toward_truth)
        if any(not s.startswith("-") for s in shifted_toward_truth):
            good_shifts += 1
        if any(s.startswith("-") for s in shifted_toward_truth):
            bad_shifts += 1
    else:
        flag = " | (shift, no truth-change)"
    print(row + flag)

print("-" * 130)
print(f"Frames where at least one variant differs from V0: {changed}")
print(f"Frames with at least one truth-improving shift:     {good_shifts}")
print(f"Frames with at least one regression from V0:        {bad_shifts}")
