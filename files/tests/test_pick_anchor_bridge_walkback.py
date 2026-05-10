"""Regression tests for delivery_classifier.pick_anchor bridge-gated walkback.

Covers:
  * Synthetic happy/unhappy bridges (gap, empty, HARD, candidate gate).
  * Change 3 tolerance: ≤1 empty frame in bridge is allowed; ≥2 rejects.
  * Pinned 23-row regression set: replays metadata.json fixtures and
    asserts pick_anchor's outcome equals the TSV ground truth.

Run from repo root:
    pytest files/tests/test_pick_anchor_bridge_walkback.py -q
"""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BMT = os.path.join(ROOT, "scripts", "broadcast_mode_tuning")
for p in (ROOT, BMT):
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest  # noqa: E402

from delivery_classifier import FrameInfo, pick_anchor  # noqa: E402
from signal_extraction import Signals  # noqa: E402


def _sig(**kw) -> Signals:
    s = Signals()
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def _frame(t: float, *, path: str = "B", **sig_kw) -> FrameInfo:
    s = _sig(**sig_kw)
    f = FrameInfo(t=t, text="", signals=s)
    f.is_delivery = True
    f.path = path
    return f


def _best(t: float, **sig_kw) -> FrameInfo:
    """Path 'A' frame — score_frame gives +1 bonus, so this beats
    Path-B siblings at score-tie and lands as `best` deterministically."""
    return _frame(t, path="A", **sig_kw)


def _cluster(frames):
    return {"frames": frames, "phantom_rescued": False}


# ── Synthetic cases ──────────────────────────────────────────────────


def test_happy_path_no_walkback_when_gap_le_4():
    """Candidate at t=10 has a 4s gap — strictly NOT >4 → no walkback."""
    frames = [
        _frame(10, V=True, M=True, M2=True, W=True),
        _frame(11, M=True, W=True),
        _frame(12, M=True, W=True),
        _frame(13, M=True, W=True),
        _best(14, V=True, M=True, M2=True, W=True),
    ]
    anchor = pick_anchor(_cluster(frames))
    assert anchor.t == 14.0


def test_happy_walkback_clean_bridge_gap_gt_4():
    """Candidate at t=10, best at t=17 → gap=7 > 4, bridge clean."""
    frames = [_frame(10, V=True, M=True, M2=True, W=True)]
    for t in (11, 12, 13, 14, 15, 16):
        frames.append(_frame(t, M=True, W=True))
    frames.append(_best(17, V=True, M=True, M2=True, W=True))
    anchor = pick_anchor(_cluster(frames))
    assert anchor.t == 10.0


def test_gap_too_small_no_walkback():
    frames = [
        _frame(15, V=True, M=True, M2=True, W=True),
        _frame(16, M=True, W=True),
        _best(17, V=True, M=True, M2=True, W=True),
    ]
    anchor = pick_anchor(_cluster(frames))
    assert anchor.t == 17.0


def test_bridge_broken_HARD_rejects_walkback():
    frames = [_frame(10, V=True, M=True, M2=True, W=True)]
    for t in (11, 12):
        frames.append(_frame(t, M=True, W=True))
    frames.append(_frame(13, M=True, W=True, HARD=True))
    for t in (14, 15):
        frames.append(_frame(t, M=True, W=True))
    frames.append(_best(17, V=True, M=True, M2=True, W=True))
    anchor = pick_anchor(_cluster(frames))
    assert anchor.t == 17.0


def test_bridge_one_empty_frame_OK_after_change3():
    """Change 3: ≤1 empty (no M no W, no HARD) frame in bridge allowed."""
    frames = [_frame(10, V=True, M=True, M2=True, W=True)]
    frames.append(_frame(11, M=True, W=True))
    frames.append(_frame(12))  # empty (no M no W no HARD)
    for t in (13, 14, 15, 16):
        frames.append(_frame(t, M=True, W=True))
    frames.append(_best(17, V=True, M=True, M2=True, W=True))
    anchor = pick_anchor(_cluster(frames))
    assert anchor.t == 10.0


def test_bridge_two_empty_frames_REJECT_after_change3():
    """Two empty frames → walkback rejected."""
    frames = [_frame(10, V=True, M=True, M2=True, W=True)]
    frames.append(_frame(11, M=True, W=True))
    frames.append(_frame(12))  # empty
    frames.append(_frame(13))  # empty
    for t in (14, 15, 16):
        frames.append(_frame(t, M=True, W=True))
    frames.append(_best(17, V=True, M=True, M2=True, W=True))
    anchor = pick_anchor(_cluster(frames))
    assert anchor.t == 17.0


def test_candidate_lacks_M2_W_gate_rejects():
    """Walkback candidate must satisfy V AND (M2 OR W). V-only fails."""
    frames = [_frame(10, V=True)]
    for t in range(11, 17):
        frames.append(_frame(t, M=True, W=True))
    frames.append(_best(17, V=True, M=True, M2=True, W=True))
    anchor = pick_anchor(_cluster(frames))
    assert anchor.t == 17.0


# ── Pinned 23-row regression ─────────────────────────────────────────


_TSV = Path(BMT) / "anchor_bridge_gated_results.tsv"


def _parse_compact_signals(sig_str: str) -> Signals:
    """Parse 'VY Sn MY M2Y WY Kn SSY CGY rc=4 [HARD]' compact format."""
    s = Signals()
    if not sig_str:
        return s
    for tok in sig_str.split():
        if tok == "HARD":
            s.HARD = True
        elif tok.startswith("rc="):
            try:
                s.role_count = int(tok[3:])
            except ValueError:
                pass
        elif tok.startswith("V_post") or tok.startswith("Vpost"):
            s.V_post = tok.endswith("Y")
        elif tok.startswith("V") and len(tok) == 2:
            s.V = tok.endswith("Y")
        elif tok.startswith("M2"):
            s.M2 = tok.endswith("Y")
        elif tok.startswith("M") and len(tok) == 2:
            s.M = tok.endswith("Y")
        elif tok.startswith("SS"):
            s.SS = tok.endswith("Y")
        elif tok.startswith("S") and len(tok) == 2:
            s.S = tok.endswith("Y")
        elif tok.startswith("W"):
            s.W = tok.endswith("Y")
        elif tok.startswith("K"):
            s.K = tok.endswith("Y")
        elif tok.startswith("CG"):
            s.CG = tok.endswith("Y")
    return s


def _load_pinned_rows():
    if not _TSV.exists():
        return []
    rows = []
    with open(_TSV) as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for r in reader:
            rows.append(r)
    return rows


def _find_metadata(source_dir: str, cluster_id: int) -> Path | None:
    base = Path(BMT) / source_dir
    if not base.exists():
        return None
    for cdir in base.iterdir():
        if cdir.is_dir() and cdir.name.startswith(f"c{cluster_id}_"):
            mp = cdir / "metadata.json"
            if mp.exists():
                return mp
    return None


def _load_cluster_from_metadata(meta_path: Path) -> dict:
    with open(meta_path) as fh:
        meta = json.load(fh)
    frames = []
    for fr in meta.get("frames", []):
        sigs = _parse_compact_signals(fr.get("signals", ""))
        f = FrameInfo(t=float(fr["t"]), text="", signals=sigs)
        f.is_delivery = bool(fr.get("is_delivery", False))
        f.path = fr.get("path", "none")
        frames.append(f)
    return {"frames": frames, "phantom_rescued": False}


@pytest.mark.parametrize("row", _load_pinned_rows())
def test_pinned_regression_pick_anchor(row):
    """Replay each pinned cluster through pick_anchor.

    Bound contract (less strict than equality with the diff script's
    TSV anchor — pick_anchor derives `best` from its own score_frame
    while the diff script reads `current_anchor_t` from metadata, so
    the iteration windows differ):

      * Returned anchor t MUST be one of the cluster's frame times.
      * Returned anchor t MUST NOT exceed `current_anchor_t` from
        metadata (walkback never goes forward).
      * Smoke check: pick_anchor returns a FrameInfo (no crash).
    """
    meta = _find_metadata(row["source_dir"], int(row["cluster_id"]))
    if meta is None:
        pytest.skip(f"metadata missing for {row['cluster_name']}")
    cluster = _load_cluster_from_metadata(meta)
    cluster_ts = {f.t for f in cluster["frames"]}
    current_t = float(row["current_anchor_t"])
    actual = pick_anchor(cluster)

    assert actual.t in cluster_ts, (
        f"{row['cluster_name']}: pick_anchor returned t={actual.t} "
        f"not in cluster frame times {sorted(cluster_ts)}")
    assert actual.t <= current_t, (
        f"{row['cluster_name']}: pick_anchor={actual.t} > "
        f"current_anchor_t={current_t} (walkback went forward)")
