#!/usr/bin/env python3
"""Chunk-based delivery window detection v2 — applied to v1 cached frames.

Reuses the per-frame Scout outputs in ``chunk_v1_combined_data.csv``.
NO new Scout calls are made.

Differences from v1 (see task spec):
  * Adds an ACTION_VERB substring feature on open_desc.
  * Drops the camera-view constraint on rule 4 (any
    ``frame_phase ∈ {release, flight, shot, post_shot}`` is a delivery).
  * Adds a provisional ``delivery_candidate`` class (rule 5) which is
    promoted to delivery only if 3+ consecutive candidates appear, else
    demoted to pre_post.
  * Forward extension from delivery anchors with a termination counter
    and a 12s hard cap.
  * Backward backfill (≤2s) for shot/post_shot anchors with no prior
    release in the same chunk.
  * Bridge rule restricted: only bridges through pre_post gaps ≤1s,
    never through graphic / replay / ad / drs.

Outputs:
  * chunk_v2_results.txt — per-clip narrative + summary tables.
  * chunk_v2_per_frame.csv — clip_id, ts, tentative_type, final_type,
    anchor_reason, extension_reason.

Usage::
    cd files/scripts/broadcast_mode_tuning
    PYTHONPATH=../.. python3 chunk_detection_v2.py
"""
from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent.parent
DELIVERIES_DIR = REPO_ROOT / "files" / "logs" / "deliveries"
LABEL_CSV = REPO_ROOT / "files" / "scripts" / "path_a_baseline" / "clip_aggregates_v2.csv"
SRC_CSV = SCRIPT_DIR / "chunk_v1_combined_data.csv"
OUT_TXT = SCRIPT_DIR / "chunk_v2_results.txt"
OUT_CSV = SCRIPT_DIR / "chunk_v2_per_frame.csv"


# Allow `import chunk_detection_v1` for v1-vs-v2 chunk comparison.
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


# ----------------------------- features (shared with v1) ------------------

CAREER_STATS_RX = re.compile(
    r"\b[A-Z][A-Z\.\-' ]{3,30}\s+\d{1,3}\*?\s*\(?\d{1,3}\)?"
    r"[\s\"\.,;\-]*?MATCH\s*\d+\s+v\s+[A-Z]{2,5}\b"
)
DISMISSAL_RX = re.compile(
    r"\b\w+\s+c\s+\w+\s+b\s+\w+\s+\d+\(\d+\)",
    re.IGNORECASE,
)
REPLAY_TAGS = {"REPLAY", "SLO-MO", "TELESTRATOR", "SPLIT-SCREEN"}
CELEB_SUBS = (
    "celebrating a wicket", "celebrating", "high-fiv",
    "celebration huddle", "huddle around the stumps",
    "fielders running toward", "raised in celebration", "last wicket",
)
DRS_SUBS = (
    "drs", "ball-tracking", "ultra-edge", "snicko",
    "hawkeye trajectory", "umpire's call", "decision review",
)
UMPIRE_GESTURES = (
    "raised", "outstretched", "signaling", "signalling",
    "arm extended", "indicating", "gesture",
)
ACTION_VERBS = (
    "running in", "running toward", "running with",
    "sprinting", "mid-swing", "mid-air", "mid-stride",
    "mid-motion", "just released", "just threw", "just hit",
    "diving", "fielding", "playing shot",
    "preparing shot", "preparing to play", "preparing to hit",
    "catching", "ball in flight", "ball traveling",
    "ball mid-air", "throwing",
    "chasing ball", "chasing the ball",
    "leaping", "lunging",
)
DELIVERY_PHASES = {"release", "flight", "shot", "post_shot"}
RELEASE_PHASES = {"release", "flight"}


@dataclass
class FrameRow:
    session: str
    clip_id: str
    ts: float
    prod_cam: str
    prod_phase: str
    v2_broadcast_tag: str
    v2_class: str
    open_desc: str


@dataclass
class FrameFeatures:
    has_action_verb: bool
    has_celebration_cue: bool
    has_drs_signal: bool
    has_umpire_signal_cue: bool
    is_replay_tag: bool
    is_career_stats_overlay: bool
    is_graphic: bool
    is_ad: bool
    is_prod_delivery_phase: bool


def extract_features(r: FrameRow) -> FrameFeatures:
    desc = r.open_desc or ""
    desc_low = desc.lower()
    has_celeb = (any(s in desc_low for s in CELEB_SUBS)
                 or bool(DISMISSAL_RX.search(desc)))
    return FrameFeatures(
        has_action_verb=any(v in desc_low for v in ACTION_VERBS),
        has_celebration_cue=has_celeb,
        has_drs_signal=any(s in desc_low for s in DRS_SUBS),
        has_umpire_signal_cue=("umpire" in desc_low
                               and any(g in desc_low for g in UMPIRE_GESTURES)),
        is_replay_tag=r.v2_broadcast_tag in REPLAY_TAGS,
        is_career_stats_overlay=bool(CAREER_STATS_RX.search(desc)),
        is_graphic=(r.prod_cam == "graphic" or r.prod_phase == "graphic"),
        is_ad=(r.prod_cam == "ad" or r.prod_phase == "advertisement"),
        is_prod_delivery_phase=r.prod_phase in DELIVERY_PHASES,
    )


# ----------------------------- tentative classification --------------------


def tentative_type(r: FrameRow, f: FrameFeatures) -> str:
    if f.is_ad:
        return "ad"
    if f.has_drs_signal:
        return "drs"
    if f.is_replay_tag or f.is_career_stats_overlay:
        return "replay"
    if f.is_prod_delivery_phase:
        return "delivery"
    if f.has_action_verb and r.v2_class == "action":
        return "delivery_candidate"
    if f.has_umpire_signal_cue:
        return "umpire_signal"
    if f.is_graphic:
        return "graphic"
    return "pre_post"


def anchor_reason_for(r: FrameRow, f: FrameFeatures, t: str) -> str:
    if t == "delivery" and f.is_prod_delivery_phase:
        return f"prod_{r.prod_phase}"
    return ""


# ----------------------------- anchor confirmation -------------------------


def confirm_anchors(types: list[str], reasons: list[str]) -> int:
    """Promote runs of ≥3 'delivery_candidate' to 'delivery'; demote rest.

    Mutates types/reasons in place.  Returns number of anchor promotions
    (one per promoted run).
    """
    promotions = 0
    n = len(types)
    i = 0
    while i < n:
        if types[i] != "delivery_candidate":
            i += 1
            continue
        j = i
        while j < n and types[j] == "delivery_candidate":
            j += 1
        run = j - i
        if run >= 3:
            for k in range(i, j):
                types[k] = "delivery"
                reasons[k] = "action_anchor"
            promotions += 1
        else:
            for k in range(i, j):
                types[k] = "pre_post"
        i = j
    return promotions


# ----------------------------- forward extension --------------------------


def forward_extend(rows: list[FrameRow],
                   feats: list[FrameFeatures],
                   types: list[str],
                   anchor_reasons: list[str],
                   ext_reasons: list[str]) -> int:
    """Extend each delivery block forward.  Mutates types/ext_reasons.

    Returns count of frames newly assigned to delivery via extension.
    """
    n = len(rows)
    extended = 0
    i = 0
    while i < n:
        if types[i] != "delivery":
            i += 1
            continue
        # find end of contiguous delivery block
        j = i
        while j + 1 < n and types[j + 1] == "delivery":
            j += 1
        anchor_start_ts = rows[i].ts
        counter = 0.0
        k = j + 1
        while k < n:
            r = rows[k]
            f = feats[k]
            if types[k] == "delivery":
                break
            if types[k] in ("ad", "replay", "drs", "graphic"):
                break
            if f.has_celebration_cue:
                break
            if (r.ts - anchor_start_ts) > 12.0:
                break
            if f.has_action_verb or f.is_prod_delivery_phase:
                counter = 0.0
            else:
                if r.v2_class == "other":
                    counter += 1.0
                elif r.v2_class == "action":
                    counter += 0.5
                else:
                    counter += 0.5
            if counter >= 2.0:
                break
            types[k] = "delivery"
            ext_reasons[k] = "forward_extension"
            if not anchor_reasons[k]:
                anchor_reasons[k] = "forward_extension"
            extended += 1
            k += 1
        i = max(k, j + 1)
    return extended


# ----------------------------- backward backfill --------------------------


def backward_backfill(rows: list[FrameRow],
                      feats: list[FrameFeatures],
                      types: list[str],
                      anchor_reasons: list[str],
                      ext_reasons: list[str]) -> int:
    """For shot/post_shot-only delivery blocks, walk back ≤2s.

    Extends the chunk's starting index backward to the earliest
    has_action_verb frame that isn't blocked by a barrier.
    """
    n = len(rows)
    backfilled = 0
    i = 0
    while i < n:
        if types[i] != "delivery":
            i += 1
            continue
        j = i
        while j + 1 < n and types[j + 1] == "delivery":
            j += 1
        # phases present in this block
        block_phases = {rows[k].prod_phase for k in range(i, j + 1)
                        if feats[k].is_prod_delivery_phase}
        anchored_on_shot = bool(block_phases & {"shot", "post_shot"})
        has_release = bool(block_phases & RELEASE_PHASES)
        if anchored_on_shot and not has_release:
            anchor_start_ts = rows[i].ts
            new_start = i
            k = i - 1
            while k >= 0:
                r = rows[k]
                f = feats[k]
                if (anchor_start_ts - r.ts) > 2.0:
                    break
                if (f.is_graphic or f.is_replay_tag or f.is_ad
                        or f.has_celebration_cue):
                    break
                if f.has_action_verb:
                    new_start = k
                k -= 1
            for kk in range(new_start, i):
                if types[kk] != "delivery":
                    types[kk] = "delivery"
                    ext_reasons[kk] = "backward_backfill"
                    if not anchor_reasons[kk]:
                        anchor_reasons[kk] = "backward_backfill"
                    backfilled += 1
        i = j + 1
    return backfilled


# ----------------------------- smoothing -----------------------------------


def smooth(rows: list[FrameRow],
           feats: list[FrameFeatures],
           types: list[str]) -> list[tuple[int, str, str]]:
    """Reassign isolated single-frame deliveries flanked by celebration.

    Returns list of (frame_idx, before, reason) for every reassignment.
    """
    n = len(types)
    notes: list[tuple[int, str, str]] = []
    for i, t in enumerate(types):
        if t != "delivery":
            continue
        is_isolated = ((i == 0 or types[i - 1] != "delivery")
                       and (i == n - 1 or types[i + 1] != "delivery"))
        if not is_isolated:
            continue
        ts_i = rows[i].ts
        nbrs = [j for j in range(n) if j != i and abs(rows[j].ts - ts_i) <= 1.5]
        nbr_celeb = any(feats[j].has_celebration_cue for j in nbrs)
        prior_3s = [j for j in range(n)
                    if rows[j].ts < ts_i and (ts_i - rows[j].ts) <= 3.0]
        prior_has_delivery = any(types[j] == "delivery" for j in prior_3s)
        if nbr_celeb and not prior_has_delivery:
            notes.append((i, "delivery", "celeb_neighbor_isolated"))
            types[i] = "pre_post"
    return notes


# ----------------------------- chunk build + bridge ------------------------


@dataclass
class Chunk:
    type_: str
    start_ts: float
    end_ts: float
    frame_count: int


def build_chunks(rows: list[FrameRow], types: list[str]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for r, t in zip(rows, types):
        if chunks and chunks[-1].type_ == t:
            chunks[-1].end_ts = r.ts
            chunks[-1].frame_count += 1
        else:
            chunks.append(Chunk(type_=t, start_ts=r.ts, end_ts=r.ts,
                                frame_count=1))
    return chunks


def bridge_chunks(chunks: list[Chunk]) -> list[Chunk]:
    """Merge same-type chunks separated by a single ≤1s pre_post chunk."""
    while True:
        out: list[Chunk] = []
        i = 0
        merged_any = False
        while i < len(chunks):
            c = chunks[i]
            if (out and i + 1 < len(chunks)
                    and out[-1].type_ == chunks[i + 1].type_
                    and c.type_ == "pre_post"
                    and (chunks[i + 1].start_ts - out[-1].end_ts) <= 1.0):
                nxt = chunks[i + 1]
                out[-1] = Chunk(out[-1].type_, out[-1].start_ts, nxt.end_ts,
                                out[-1].frame_count + c.frame_count + nxt.frame_count)
                i += 2
                merged_any = True
                continue
            out.append(c)
            i += 1
        chunks = out
        if not merged_any:
            break
    return chunks


# ----------------------------- I/O helpers --------------------------------


def load_csv() -> tuple[list[tuple[str, str]], dict[tuple[str, str], list[FrameRow]]]:
    grouped: dict[tuple[str, str], list[FrameRow]] = {}
    order: list[tuple[str, str]] = []
    with SRC_CSV.open() as f:
        for r in csv.DictReader(f):
            key = (r["session"], r["clip_id"])
            if key not in grouped:
                grouped[key] = []
                order.append(key)
            grouped[key].append(FrameRow(
                session=r["session"], clip_id=r["clip_id"],
                ts=float(r["ts"]),
                prod_cam=r["prod_cam"], prod_phase=r["prod_phase"],
                v2_broadcast_tag=r["v2_broadcast_tag"],
                v2_class=r["v2_class"], open_desc=r["open_desc"],
            ))
    for key in grouped:
        grouped[key].sort(key=lambda x: x.ts)
    return order, grouped


def label_lookup() -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    with LABEL_CSV.open() as f:
        for r in csv.DictReader(f):
            out[(r["session"], r["clip_id"])] = r["manual_label"]
    return out


def read_window_meta(session: str, clip_id: str) -> tuple[float, float]:
    p = DELIVERIES_DIR / session / clip_id / "window_debug.json"
    try:
        meta = json.loads(p.read_text())
        return (meta["clip_end_ts"] - meta["clip_start_ts"],
                meta["event_ts"] - meta["clip_start_ts"])
    except Exception:
        return float("nan"), float("nan")


# ----------------------------- v1 chunk reproduction ----------------------


def v1_chunks_for(rows: list[FrameRow]) -> list[Chunk]:
    """Reproduce v1 chunks for comparison (uses chunk_detection_v1)."""
    import chunk_detection_v1 as v1
    v1_rows = [v1.FrameRow(session=r.session, clip_id=r.clip_id, ts=r.ts,
                           prod_cam=r.prod_cam, prod_phase=r.prod_phase,
                           v2_broadcast_tag=r.v2_broadcast_tag,
                           v2_class=r.v2_class, open_desc=r.open_desc)
               for r in rows]
    v1_feats = [v1.extract_features(r) for r in v1_rows]
    v1_types = [v1.tentative_type(r, f) for r, f in zip(v1_rows, v1_feats)]
    v1_smoothed, _ = v1.smooth_types(v1_rows, v1_feats, v1_types)
    v1_chunks = v1.build_chunks(v1_rows, v1_smoothed)
    out: list[Chunk] = []
    for c in v1_chunks:
        out.append(Chunk(c.type_, c.start_ts, c.end_ts, c.frame_count))
    return out


# ----------------------------- runner -------------------------------------

CONSEQUENTIAL_TYPES = {"delivery", "replay", "ad", "drs", "umpire_signal"}
MAY3_SESSION = "20260503_205835"


def chunks_summary(chunks: list[Chunk]) -> str:
    return ", ".join(c.type_ for c in chunks) or "(none)"


def cons_summary(chunks: list[Chunk]) -> str:
    parts = [f"{c.type_} [{c.start_ts:.2f}-{c.end_ts:.2f}]"
             for c in chunks if c.type_ in CONSEQUENTIAL_TYPES]
    return ", ".join(parts) or "none"


def delta_string(v1: list[Chunk], v2: list[Chunk]) -> str:
    v1_d = sum(1 for c in v1 if c.type_ == "delivery")
    v2_d = sum(1 for c in v2 if c.type_ == "delivery")
    v1_r = sum(1 for c in v1 if c.type_ == "replay")
    v2_r = sum(1 for c in v2 if c.type_ == "replay")
    v1_u = sum(1 for c in v1 if c.type_ == "umpire_signal")
    v2_u = sum(1 for c in v2 if c.type_ == "umpire_signal")
    parts = []
    if v1_d != v2_d:
        parts.append(f"delivery {v1_d}->{v2_d}")
    if v1_r != v2_r:
        parts.append(f"replay {v1_r}->{v2_r}")
    if v1_u != v2_u:
        parts.append(f"umpire {v1_u}->{v2_u}")
    return "; ".join(parts) or "no chunk-count change"


def match_classification(label: str, chunks: list[Chunk]) -> str:
    """yes / partial / no — heuristic without truth windows."""
    n_delivery = sum(1 for c in chunks if c.type_ == "delivery")
    if label == "real_delivery":
        if n_delivery == 1:
            return "yes"
        if n_delivery == 0:
            return "no"
        return f"partial (n={n_delivery})"
    if label == "ad":
        n_ad = sum(1 for c in chunks if c.type_ == "ad")
        return "yes" if n_ad >= 1 and n_delivery == 0 else "partial/no"
    return "n/a"


def run() -> int:
    order, grouped = load_csv()
    labels = label_lookup()

    out_lines: list[str] = []

    def emit(line: str = "") -> None:
        out_lines.append(line)

    set1: list[tuple[str, list[Chunk], list[Chunk]]] = []  # (clip_disp, v1, v2)
    set2: list[tuple[str, str, list[Chunk], list[Chunk]]] = []  # (clip_disp, label, v1, v2)

    per_frame_csv_rows: list[list[str]] = []

    for session, clip_id in order:
        rows = grouped[(session, clip_id)]
        feats = [extract_features(r) for r in rows]
        tentatives = [tentative_type(r, f) for r, f in zip(rows, feats)]
        anchor_reasons = [anchor_reason_for(r, f, t)
                          for r, f, t in zip(rows, feats, tentatives)]
        ext_reasons = [""] * len(rows)

        types = list(tentatives)
        n_anchor_promo = confirm_anchors(types, anchor_reasons)
        n_forward = forward_extend(rows, feats, types, anchor_reasons, ext_reasons)
        n_backfill = backward_backfill(rows, feats, types, anchor_reasons, ext_reasons)
        smooth_notes = smooth(rows, feats, types)
        chunks_pre_bridge = build_chunks(rows, types)
        chunks = bridge_chunks(chunks_pre_bridge)

        v1_chunks = v1_chunks_for(rows)

        duration, event = read_window_meta(session, clip_id)
        label = labels.get((session, clip_id), "N/A")
        clip_disp = f"{session}/{clip_id}"

        emit("=" * 70)
        emit(f"[CLIP {clip_disp}]")
        emit(f"  duration={duration:.2f}s event_ts={event:.2f}s")
        emit(f"  manual_label={label}")
        emit(f"  truth_window=N/A")
        emit("")
        emit("  Per-frame classification (v2):")
        for r, f, tnt, fin, areason, ereason in zip(
                rows, feats, tentatives, types,
                anchor_reasons, ext_reasons):
            note_parts = []
            if tnt != fin:
                note_parts.append(f"tentative={tnt}")
            if fin == "delivery" and f.is_prod_delivery_phase:
                note_parts.append(f"prod={r.prod_phase}")
            if areason and areason not in (f"prod_{r.prod_phase}",):
                note_parts.append(areason)
            if ereason and ereason != areason:
                note_parts.append(ereason)
            note = (" [" + ", ".join(note_parts) + "]") if note_parts else ""
            emit(f"    ts={r.ts:5.2f}s {fin}{note}")
        if smooth_notes:
            emit("")
            emit("  Smoothing reassignments:")
            for idx, before, reason in smooth_notes:
                emit(f"    ts={rows[idx].ts:5.2f}s {before} -> pre_post"
                     f"  ({reason})")
        emit("")
        emit("  Chunks:")
        for c in chunks:
            emit(f"    [{c.start_ts:5.2f}s - {c.end_ts:5.2f}s] {c.type_}"
                 f"  ({c.frame_count} frames)")
        emit("")
        emit("  Consequential chunks (saved as videos):")
        consequential = [c for c in chunks if c.type_ in CONSEQUENTIAL_TYPES]
        if consequential:
            for c in consequential:
                emit(f"    {c.type_}: [{c.start_ts:5.2f}s - {c.end_ts:5.2f}s]")
        else:
            emit("    none")
        emit("")
        emit("  Diagnostic counts:")
        emit(f"    n_action_verb_frames: "
             f"{sum(1 for f in feats if f.has_action_verb)}")
        emit(f"    n_prod_delivery_phase_frames: "
             f"{sum(1 for f in feats if f.is_prod_delivery_phase)}")
        emit(f"    n_anchor_promotions: {n_anchor_promo}")
        emit(f"    n_backfill_extensions: {n_backfill}")
        emit(f"    n_forward_extensions: {n_forward}")
        emit("")

        for r, tnt, fin, areason, ereason in zip(
                rows, tentatives, types, anchor_reasons, ext_reasons):
            per_frame_csv_rows.append([
                f"{r.session}/{r.clip_id}", f"{r.ts:.3f}",
                tnt, fin, areason, ereason,
            ])

        if session == MAY3_SESSION:
            set1.append((clip_disp, v1_chunks, chunks))
        else:
            set2.append((clip_disp, label, v1_chunks, chunks))

    # Summary tables
    emit("=" * 70)
    emit("Summary — Test set 1 (8 May 3 clips)")
    emit("")
    emit("| clip | v1 chunks | v2 chunks | v1 -> v2 delta |")
    emit("| ---- | ---- | ---- | ---- |")
    for clip, v1c, v2c in set1:
        emit(f"| {clip} | {chunks_summary(v1c)} | {chunks_summary(v2c)} "
             f"| {delta_string(v1c, v2c)} |")
    emit("")

    emit("=" * 70)
    emit("Summary — Test set 2 (10 random clips)")
    emit("")
    emit("| clip | label | truth window | v1 chunks | v2 chunks | match |")
    emit("| ---- | ---- | ---- | ---- | ---- | ---- |")
    for clip, label, v1c, v2c in set2:
        emit(f"| {clip} | {label} | N/A | {chunks_summary(v1c)} "
             f"| {chunks_summary(v2c)} | {match_classification(label, v2c)} |")
    emit("")

    # Flag-for-review list
    emit("=" * 70)
    emit("Flag-for-review (v2 detected MORE delivery chunks than ground truth"
         " for real_delivery clips, which truth says is 1):")
    flagged: list[tuple[str, int]] = []
    for clip, label, _v1c, v2c in set2:
        n_d = sum(1 for c in v2c if c.type_ == "delivery")
        if label == "real_delivery" and n_d >= 2:
            flagged.append((clip, n_d))
    for clip, n_d in flagged:
        emit(f"  {clip}: {n_d} delivery chunks (truth implies 1)")
    if not flagged:
        emit("  (none)")
    emit("")

    OUT_TXT.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_TXT}")

    with OUT_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["clip_id", "ts", "tentative_type", "final_type",
                    "anchor_reason", "extension_reason"])
        for row in per_frame_csv_rows:
            w.writerow(row)
    print(f"Wrote {OUT_CSV} ({len(per_frame_csv_rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
