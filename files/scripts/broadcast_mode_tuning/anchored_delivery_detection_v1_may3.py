#!/usr/bin/env python3
"""Anchored delivery-window detection v1 on May 3 corpus.

Algorithm summary (see task brief):
  1. ANCHOR FIND: prod_cam=bowlers_end AND prod_phase=release.
  2. ANCHOR VALIDATE (require ALL):
     a) >=1 neighbor within +/-2s with prod_cam=bowlers_end (any phase)
        OR (prod_cam=closeup AND prod_phase=between_play)
     b) v2_broadcast_tag == LIVE
     c) open_desc does NOT match a REPLAY PATTERN
     d) no frame within +/-1s has prod_phase==fielder_reaction
  3. BOUNDARY: from validated anchor, scan +/-5s while phase in
     {between_play, shot, post_shot, flight, runup} or
     (closeup+between_play). Stop on replay pattern, ad/graphic cam,
     fielder_reaction, or +/-5s boundary.
  4. MERGE: validated anchors within 3s merge to one window.

Inputs (cached from prior diagnostic runs in this directory):
  - may3_production_prompt_results.txt  -> prod_cam, prod_phase
  - may3_v2_prompt_results.txt          -> v2_broadcast_tag, v2_class
  - may3_open_prompt_results.txt        -> open_desc

Outputs:
  - may3_combined_prompts.csv
  - may3_anchored_detection_results.txt
  - stdout: per-clip log + summary truth table
"""
from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROD_FILE = SCRIPT_DIR / "may3_production_prompt_results.txt"
V2_FILE = SCRIPT_DIR / "may3_v2_prompt_results.txt"
OPEN_FILE = SCRIPT_DIR / "may3_open_prompt_results.txt"
CSV_OUT = SCRIPT_DIR / "may3_combined_prompts.csv"
TXT_OUT = SCRIPT_DIR / "may3_anchored_detection_results.txt"

GROUND_TRUTH = {
    "d001": False, "d002": False, "d003": False,
    "d004": True,  "d005": True,  "d006": False,
    "d007": True,  "d008": False,
}

CLIP_HEADER = re.compile(r"\[CLIP\s+(d\d+)\]")
TS_LINE = re.compile(r"^\s*(\d+(?:\.\d+)?)s\s*[-—]")  # both prod & open
V2_TS_LINE = re.compile(r"^\s*(\d+(?:\.\d+)?)s\s+class=(\S+)")
JSON_LINE = re.compile(r"JSON:\s*(\{.*\})")
DESC_LINE = re.compile(r'Description:\s*"(.*)"\s*$')
RAW_LINE = re.compile(r'raw:\s*"(.*)"\s*$')
OPEN_INLINE = re.compile(r'^\s*\d+(?:\.\d+)?s\s*[-—]\s*"(.*)"\s*$')
BCAST_TAG = re.compile(r"\[BROADCAST:\s*([A-Z\-]+)\]")

REPLAY_KEYWORDS = (
    "replay", "relive", "instant replay", "slow motion", "slo-mo",
    "super slo-mo", "telestrator", "freeze frame", "spider-cam",
    "translucent white circle", "ball-tracking overlay", "trajectory",
)
CAREER_STATS_RE = re.compile(
    r"\b[A-Z][A-Z\.\-' ]{3,30}\s+\d{1,3}\*?\s*"
    r"(?:\(\d{1,3}\)|\d{1,3})\s+MATCH\s*\d+\s+v\s+[A-Z]{2,5}\b"
)

BOUNDARY_PHASES = {"between_play", "shot", "post_shot", "flight", "runup"}


@dataclass
class Frame:
    clip: str
    ts: float
    prod_cam: str | None = None
    prod_phase: str | None = None
    v2_tag: str | None = None
    v2_class: str | None = None
    open_desc: str = ""


# ---------- parsers ------------------------------------------------------

def _parse_prod(path: Path) -> dict[str, dict[float, tuple[str | None, str | None]]]:
    out: dict[str, dict[float, tuple]] = {}
    cur_clip: str | None = None
    cur_ts: float | None = None
    pending_json: dict | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m_clip = CLIP_HEADER.search(line)
        if m_clip:
            cur_clip = m_clip.group(1)
            out.setdefault(cur_clip, {})
            continue
        m_ts = TS_LINE.match(line)
        if m_ts and cur_clip:
            cur_ts = float(m_ts.group(1))
            pending_json = None
            continue
        m_j = JSON_LINE.search(line)
        if m_j and cur_clip and cur_ts is not None:
            try:
                pending_json = json.loads(m_j.group(1))
            except Exception:
                pending_json = None
            cam = pending_json.get("camera_view") if pending_json else None
            phase = pending_json.get("frame_phase") if pending_json else None
            out[cur_clip][cur_ts] = (cam, phase)
            continue
    return out


def _parse_v2(path: Path) -> dict[str, dict[float, tuple[str | None, str | None]]]:
    out: dict[str, dict[float, tuple]] = {}
    cur_clip: str | None = None
    cur_ts: float | None = None
    cur_class: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m_clip = CLIP_HEADER.search(line)
        if m_clip:
            cur_clip = m_clip.group(1)
            out.setdefault(cur_clip, {})
            continue
        m_ts = V2_TS_LINE.match(line)
        if m_ts and cur_clip:
            cur_ts = float(m_ts.group(1))
            cur_class = m_ts.group(2)
            continue
        m_raw = RAW_LINE.search(line)
        if m_raw and cur_clip and cur_ts is not None:
            tag_match = BCAST_TAG.search(m_raw.group(1))
            tag = tag_match.group(1) if tag_match else None
            out[cur_clip][cur_ts] = (tag, cur_class)
            cur_ts = None
    return out


def _parse_open(path: Path) -> dict[str, dict[float, str]]:
    out: dict[str, dict[float, str]] = {}
    cur_clip: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m_clip = CLIP_HEADER.search(line)
        if m_clip:
            cur_clip = m_clip.group(1)
            out.setdefault(cur_clip, {})
            continue
        m_inline = OPEN_INLINE.match(line)
        if m_inline and cur_clip:
            ts = float(re.match(r"\s*(\d+(?:\.\d+)?)s", line).group(1))
            out[cur_clip][ts] = m_inline.group(1)
    return out


def load_corpus() -> dict[str, list[Frame]]:
    prod = _parse_prod(PROD_FILE)
    v2 = _parse_v2(V2_FILE)
    op = _parse_open(OPEN_FILE)
    clips = sorted(set(prod) | set(v2) | set(op))
    out: dict[str, list[Frame]] = {}
    for clip in clips:
        ts_set = set(prod.get(clip, {})) | set(v2.get(clip, {})) | set(op.get(clip, {}))
        frames: list[Frame] = []
        for ts in sorted(ts_set):
            cam, phase = prod.get(clip, {}).get(ts, (None, None))
            tag, cls = v2.get(clip, {}).get(ts, (None, None))
            desc = op.get(clip, {}).get(ts, "")
            frames.append(Frame(clip=clip, ts=ts,
                                prod_cam=cam, prod_phase=phase,
                                v2_tag=tag, v2_class=cls,
                                open_desc=desc))
        out[clip] = frames
    return out


# ---------- algorithm ----------------------------------------------------

def _matches_replay_pattern(desc: str) -> tuple[bool, str | None]:
    if not desc:
        return False, None
    low = desc.lower()
    for kw in REPLAY_KEYWORDS:
        if kw in low:
            return True, f"keyword:{kw!r}"
    m = CAREER_STATS_RE.search(desc)
    if m:
        return True, f"career_stats_overlay({m.group(0)!r})"
    return False, None


def _neighbor_ok(frames: list[Frame], anchor_ts: float, window: float = 2.0) -> Frame | None:
    for f in frames:
        if f.ts == anchor_ts:
            continue
        if abs(f.ts - anchor_ts) > window:
            continue
        if f.prod_cam == "bowlers_end":
            return f
        if f.prod_cam == "closeup" and f.prod_phase == "between_play":
            return f
    return None


def _has_fielder_reaction_within(frames: list[Frame], ts: float, window: float = 1.0) -> bool:
    for f in frames:
        if abs(f.ts - ts) <= window and f.prod_phase == "fielder_reaction":
            return True
    return False


@dataclass
class AnchorResult:
    ts: float
    validated: bool
    reasons: list[str] = field(default_factory=list)
    neighbor_desc: str | None = None


def evaluate_anchors(frames: list[Frame]) -> list[AnchorResult]:
    candidates = [f for f in frames
                  if f.prod_cam == "bowlers_end" and f.prod_phase == "release"]
    results: list[AnchorResult] = []
    for c in candidates:
        reasons: list[str] = []
        neigh = _neighbor_ok(frames, c.ts)
        if not neigh:
            reasons.append("no_qualifying_neighbor_within_2s")
        else:
            neigh_desc = (f"neighbor=cam={neigh.prod_cam}+"
                          f"phase={neigh.prod_phase}@{neigh.ts:.2f}s")
        if c.v2_tag != "LIVE":
            reasons.append(f"v2_tag={c.v2_tag} (not LIVE)")
        replay_hit, why = _matches_replay_pattern(c.open_desc)
        if replay_hit:
            reasons.append(f"replay_pattern[{why}] in open_desc")
        if _has_fielder_reaction_within(frames, c.ts):
            reasons.append("fielder_reaction_within_1s")
        validated = not reasons
        ar = AnchorResult(ts=c.ts, validated=validated, reasons=reasons)
        if neigh:
            ar.neighbor_desc = neigh_desc  # type: ignore[name-defined]
        results.append(ar)
    return results


def _expand_window(frames: list[Frame], anchor_ts: float,
                   max_extent: float = 5.0) -> tuple[float, float, str, str]:
    by_ts = {f.ts: f for f in frames}
    sorted_ts = sorted(by_ts)

    def step(direction: int) -> tuple[float, str]:
        cur = anchor_ts
        stop_reason = "extent_reached"
        for ts in sorted_ts:
            if direction > 0 and ts <= anchor_ts:
                continue
            if direction < 0 and ts >= anchor_ts:
                continue
            if abs(ts - anchor_ts) > max_extent:
                if direction > 0:
                    break
                else:
                    continue
            f = by_ts[ts]
            replay_hit, _ = _matches_replay_pattern(f.open_desc)
            if replay_hit:
                stop_reason = f"replay_pattern@{ts:.2f}s"
                break
            if f.prod_cam in ("ad", "graphic"):
                stop_reason = f"cam={f.prod_cam}@{ts:.2f}s"
                break
            if f.prod_phase == "fielder_reaction":
                stop_reason = f"fielder_reaction@{ts:.2f}s"
                break
            cont = (f.prod_phase in BOUNDARY_PHASES
                    or (f.prod_cam == "closeup"
                        and f.prod_phase == "between_play"))
            if not cont:
                stop_reason = (f"phase={f.prod_phase}/cam={f.prod_cam}"
                               f"@{ts:.2f}s")
                break
            cur = ts
        return cur, stop_reason

    fwd_ts_list = [ts for ts in sorted_ts if ts > anchor_ts]
    bwd_ts_list = [ts for ts in sorted_ts if ts < anchor_ts]
    fwd_end, fwd_reason = anchor_ts, "no_forward_frames"
    bwd_end, bwd_reason = anchor_ts, "no_backward_frames"
    if fwd_ts_list:
        fwd_end, fwd_reason = step(+1)
    if bwd_ts_list:
        bwd_end, bwd_reason = _step_backward(frames, anchor_ts, max_extent)
    return bwd_end, fwd_end, bwd_reason, fwd_reason


def _step_backward(frames: list[Frame], anchor_ts: float,
                   max_extent: float) -> tuple[float, str]:
    by_ts = {f.ts: f for f in frames}
    bwd = sorted([ts for ts in by_ts if ts < anchor_ts], reverse=True)
    cur = anchor_ts
    reason = "extent_reached"
    for ts in bwd:
        if abs(ts - anchor_ts) > max_extent:
            break
        f = by_ts[ts]
        replay_hit, _ = _matches_replay_pattern(f.open_desc)
        if replay_hit:
            reason = f"replay_pattern@{ts:.2f}s"
            break
        if f.prod_cam in ("ad", "graphic"):
            reason = f"cam={f.prod_cam}@{ts:.2f}s"
            break
        if f.prod_phase == "fielder_reaction":
            reason = f"fielder_reaction@{ts:.2f}s"
            break
        cont = (f.prod_phase in BOUNDARY_PHASES
                or (f.prod_cam == "closeup"
                    and f.prod_phase == "between_play"))
        if not cont:
            reason = f"phase={f.prod_phase}/cam={f.prod_cam}@{ts:.2f}s"
            break
        cur = ts
    return cur, reason


def merge_windows(windows: list[tuple[float, float, float]],
                  gap: float = 3.0) -> list[tuple[float, float, list[float]]]:
    """Merge anchors within `gap` seconds.  Each input is (anchor, lo, hi).
    Returns merged (lo, hi, [anchor_ts ...])."""
    if not windows:
        return []
    by_anchor = sorted(windows, key=lambda w: w[0])
    merged: list[tuple[float, float, list[float]]] = []
    for anchor, lo, hi in by_anchor:
        if merged and (anchor - merged[-1][2][-1]) <= gap:
            plo, phi, anchors = merged[-1]
            merged[-1] = (min(plo, lo), max(phi, hi), anchors + [anchor])
        else:
            merged.append((lo, hi, [anchor]))
    return merged


# ---------- output -------------------------------------------------------

def write_csv(corpus: dict[str, list[Frame]]) -> None:
    with CSV_OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["clip_id", "ts", "prod_cam", "prod_phase",
                    "v2_broadcast_tag", "v2_class", "open_desc"])
        for clip in sorted(corpus):
            for f in corpus[clip]:
                w.writerow([clip, f"{f.ts:.2f}", f.prod_cam or "",
                            f.prod_phase or "", f.v2_tag or "",
                            f.v2_class or "", f.open_desc])


def main() -> int:
    if not all(p.exists() for p in (PROD_FILE, V2_FILE, OPEN_FILE)):
        missing = [str(p) for p in (PROD_FILE, V2_FILE, OPEN_FILE) if not p.exists()]
        print(f"missing inputs: {missing}", file=sys.stderr)
        return 1

    corpus = load_corpus()
    write_csv(corpus)

    out_lines: list[str] = []

    def emit(s: str = "") -> None:
        print(s, flush=True)
        out_lines.append(s)

    detection_status: dict[str, bool] = {}
    for clip in sorted(corpus):
        frames = corpus[clip]
        anchors = evaluate_anchors(frames)
        valid = [a for a in anchors if a.validated]

        emit("=" * 60)
        emit(f"[CLIP {clip}] frames={len(frames)} "
             f"truth_has_delivery={GROUND_TRUTH.get(clip)}")
        emit("")
        emit("  Anchor candidates:")
        if not anchors:
            emit("    (none — no bowlers_end+release frame)")
        else:
            for a in anchors:
                f = next(fr for fr in frames if fr.ts == a.ts)
                emit(f"    {a.ts:.2f}s (bowlers_end + release) "
                     f"v2={f.v2_tag} class={f.v2_class}")

        emit("")
        emit("  Validation:")
        if not anchors:
            emit("    (no anchors)")
        else:
            for a in anchors:
                if a.validated:
                    parts = []
                    if a.neighbor_desc:
                        parts.append(a.neighbor_desc)
                    parts.append("broadcast=LIVE")
                    parts.append("no_replay_pattern")
                    parts.append("no_fielder_reaction")
                    emit(f"    {a.ts:.2f}s OK  " + ", ".join(parts))
                else:
                    emit(f"    {a.ts:.2f}s REJECT  reasons="
                         + "; ".join(a.reasons))

        windows_in = []
        for a in valid:
            lo, hi, lo_r, hi_r = _expand_window(frames, a.ts)
            windows_in.append((a.ts, lo, hi))
        merged = merge_windows(windows_in)

        emit("")
        emit("  Delivery windows:")
        if not merged:
            emit("    (none)")
        else:
            for lo, hi, anchors_in in merged:
                anchors_str = ",".join(f"{x:.2f}s" for x in anchors_in)
                emit(f"    [{lo:.2f}s, {hi:.2f}s] anchor={anchors_str}")
        detection_status[clip] = bool(merged)
        emit("")

    emit("=" * 60)
    emit("SUMMARY (truth vs detection)")
    emit("")
    emit(f"  {'Clip':<6} {'Truth':<7} {'Detected':<9} {'Match'}")
    correct = 0
    for clip in sorted(corpus):
        truth = GROUND_TRUTH.get(clip)
        det = detection_status.get(clip, False)
        match = (truth == det)
        if match:
            correct += 1
        truth_str = "yes" if truth else "no"
        det_str = "yes" if det else "no"
        emit(f"  {clip:<6} {truth_str:<7} {det_str:<9} "
             f"{'OK' if match else 'MISS'}")
    emit("")
    emit(f"  accuracy: {correct}/{len(corpus)}")

    TXT_OUT.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"\nWrote {CSV_OUT}")
    print(f"Wrote {TXT_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
