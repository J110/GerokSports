#!/usr/bin/env python3
"""Chunk-based delivery window detection v1.

Six-chunk segmentation algorithm (delivery / pre_post / replay / ad /
umpire_signal / drs).  Tested on the 8 May 3 (20260503_205835) clips
plus 10 random clips drawn from the 105-clip labeled corpus with
``random.seed(42)``.

Pipeline per frame:
  * 3 fps sampling (catches brief release moments — 1 fps was unreliable).
  * 3 Scout calls in parallel:
      - production prompt (eyes.vision.SCOUT_PROMPT) → prod_cam, prod_phase
      - OPEN_PROMPT_V2 → v2_broadcast_tag + v2_class via classify_full
      - OPEN_PROMPT v1 → open_desc
  * Boolean feature extraction (regex / substring matches).
  * Tentative per-frame chunk type via 6 first-match rules.
  * Temporal smoothing of single-frame outliers.
  * Merge consecutive same-type frames into chunks (with bridge-gap rule).

Outputs:
  * chunk_v1_combined_data.csv — per-frame raw data.
  * chunk_v1_results.txt — per-clip narrative + summary tables.

Usage::
    cd files/scripts/broadcast_mode_tuning
    PYTHONPATH=../.. python3 chunk_detection_v1.py
"""
from __future__ import annotations

import asyncio
import base64
import csv
import json
import random
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import cv2

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent.parent
DELIVERIES_DIR = REPO_ROOT / "files" / "logs" / "deliveries"
MAY3_SESSION = "20260503_205835"
LABEL_CSV = REPO_ROOT / "files" / "scripts" / "path_a_baseline" / "clip_aggregates_v2.csv"
OUT_CSV = SCRIPT_DIR / "chunk_v1_combined_data.csv"
OUT_TXT = SCRIPT_DIR / "chunk_v1_results.txt"

VISION_HINT = "None — first frame or no issues."
FPS_SAMPLE = 3.0
FRAME_DT = 1.0 / FPS_SAMPLE

# Inter-frame pacing: per-frame batch fans out 3 Groq calls in parallel
# and then sleeps PACING_S before the next sample. Keeps total token
# pressure under per-key Groq throughput limits.
PACING_S = 0.20


def _ensure_path() -> None:
    root_s = str((REPO_ROOT / "files").resolve())
    if root_s not in sys.path:
        sys.path.insert(0, root_s)


# ----------------------------- sample selection -----------------------------


def pick_random_clips(seed: int = 42, n: int = 10) -> list[tuple[str, str, str]]:
    """Return [(session, clip_id, manual_label), ...] using seed."""
    random.seed(seed)
    with LABEL_CSV.open() as f:
        rows = list(csv.DictReader(f))
    pick = random.sample(rows, n)
    return [(r["session"], r["clip_id"], r["manual_label"]) for r in pick]


def list_may3_clips() -> list[tuple[str, str, str]]:
    """Return [(session, clip_id, manual_label='N/A'), ...] for May 3 set."""
    sess = MAY3_SESSION
    sess_dir = DELIVERIES_DIR / sess
    out: list[tuple[str, str, str]] = []
    for p in sorted(sess_dir.glob("d*")):
        if p.is_dir() and (p / "delivery_window.mp4").exists():
            out.append((sess, p.name, "N/A"))
    return out


# ----------------------------- frame sampling ------------------------------


def sample_frames(mp4: Path, fps: float = FPS_SAMPLE) -> list[tuple[float, bytes]]:
    cap = cv2.VideoCapture(str(mp4))
    fps_in = cap.get(cv2.CAP_PROP_FPS) or 0.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if fps_in <= 0 or total <= 0:
        cap.release()
        return []
    duration = total / fps_in
    out: list[tuple[float, bytes]] = []
    dt = 1.0 / fps
    t = 0.0
    while t <= duration + 1e-3:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            t += dt
            continue
        ok2, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok2:
            out.append((t, buf.tobytes()))
        t += dt
    cap.release()
    return out


def read_window_meta(clip_dir: Path) -> tuple[float, float]:
    """Return (duration_s, event_in_clip_s); NaN-NaN if unavailable."""
    try:
        meta = json.loads((clip_dir / "window_debug.json").read_text())
        return (meta["clip_end_ts"] - meta["clip_start_ts"],
                meta["event_ts"] - meta["clip_start_ts"])
    except Exception:
        return float("nan"), float("nan")


# ----------------------------- Scout calls --------------------------------


async def _groq_call(client, model: str, prompt: str, jpg_b64: str,
                     max_tokens: int, timeout_s: float = 90.0) -> str:
    try:
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                temperature=0.2,
                max_tokens=max_tokens,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url",
                         "image_url": {
                             "url": f"data:image/jpeg;base64,{jpg_b64}"}},
                        {"type": "text", "text": prompt},
                    ],
                }],
            ),
            timeout=timeout_s,
        )
        if resp.choices and resp.choices[0].message:
            return (resp.choices[0].message.content or "").strip()
        return ""
    except asyncio.TimeoutError:
        return "[timeout]"
    except Exception as e:  # noqa: BLE001
        return f"[err: {e}]"


def _parse_prod_first_json(text: str) -> dict | None:
    if not text:
        return None
    lines = text.splitlines()
    for line in lines:
        s = line.strip()
        if s.startswith("{"):
            depth = 0
            end = -1
            for i, ch in enumerate(s):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end >= 0:
                try:
                    return json.loads(s[:end + 1])
                except Exception:
                    return None
        if s:
            return None
    return None


def _parse_v2_tag(text: str) -> str:
    if not text:
        return "LIVE"
    first = text.splitlines()[0].strip().upper()
    m = re.search(r"\[BROADCAST:\s*([A-Z\-]+)\s*\]", first)
    if m:
        return m.group(1)
    if "REPLAY" in first:
        return "REPLAY"
    if "SLO-MO" in first or "SLOW MOTION" in first:
        return "SLO-MO"
    if "TELESTRATOR" in first:
        return "TELESTRATOR"
    if "SPLIT-SCREEN" in first or "SPLIT SCREEN" in first:
        return "SPLIT-SCREEN"
    return "LIVE"


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


async def gather_frame(client, prod_prompt: str, v2_prompt: str,
                       v1_prompt: str, jpg: bytes, classify_full,
                       session: str, clip_id: str, ts: float) -> FrameRow:
    b64 = base64.b64encode(jpg).decode()
    raw_prod, raw_v2, raw_v1 = await asyncio.gather(
        _groq_call(client, MODEL, prod_prompt, b64, max_tokens=600),
        _groq_call(client, MODEL, v2_prompt, b64, max_tokens=220),
        _groq_call(client, MODEL, v1_prompt, b64, max_tokens=220),
    )
    obj = _parse_prod_first_json(raw_prod)
    prod_cam = (obj or {}).get("camera_view") or ""
    prod_phase = (obj or {}).get("frame_phase") or ""
    v2_tag = _parse_v2_tag(raw_v2)
    v2_class = classify_full(raw_v2) or "other"
    return FrameRow(
        session=session, clip_id=clip_id, ts=round(ts, 3),
        prod_cam=str(prod_cam), prod_phase=str(prod_phase),
        v2_broadcast_tag=v2_tag, v2_class=v2_class,
        open_desc=raw_v1,
    )


# ----------------------------- feature extraction ---------------------------

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
    "celebrating a wicket",
    "celebrating",
    "high-fiv",
    "celebration huddle",
    "huddle around the stumps",
    "fielders running toward",
    "raised in celebration",
    "last wicket",
)
DRS_SUBS = (
    "drs",
    "ball-tracking",
    "ultra-edge",
    "snicko",
    "hawkeye trajectory",
    "umpire's call",
    "decision review",
)
UMPIRE_GESTURES = (
    "raised", "outstretched", "signaling", "signalling",
    "arm extended", "indicating", "gesture",
)


def _has_sub(text_low: str, subs) -> bool:
    return any(s in text_low for s in subs)


@dataclass
class FrameFeatures:
    is_career_stats_overlay: bool
    is_replay_tag: bool
    has_celebration_cue: bool
    has_drs_signal: bool
    has_umpire_signal_cue: bool


def extract_features(row: FrameRow) -> FrameFeatures:
    desc = row.open_desc or ""
    desc_low = desc.lower()
    is_career = bool(CAREER_STATS_RX.search(desc))
    is_replay = row.v2_broadcast_tag in REPLAY_TAGS
    has_celeb = _has_sub(desc_low, CELEB_SUBS) or bool(DISMISSAL_RX.search(desc))
    has_drs = _has_sub(desc_low, DRS_SUBS)
    has_ump = ("umpire" in desc_low) and any(g in desc_low for g in UMPIRE_GESTURES)
    return FrameFeatures(
        is_career_stats_overlay=is_career,
        is_replay_tag=is_replay,
        has_celebration_cue=has_celeb,
        has_drs_signal=has_drs,
        has_umpire_signal_cue=has_ump,
    )


# ----------------------------- chunk classification ------------------------

DELIVERY_PHASES = {"release", "flight", "shot", "post_shot"}


def tentative_type(row: FrameRow, feat: FrameFeatures) -> str:
    if row.prod_cam == "ad" or row.prod_phase == "advertisement":
        return "ad"
    if feat.has_drs_signal:
        return "drs"
    if feat.is_replay_tag or feat.is_career_stats_overlay:
        return "replay"
    if row.prod_cam == "bowlers_end" and row.prod_phase in DELIVERY_PHASES:
        return "delivery"
    if feat.has_umpire_signal_cue:
        return "umpire_signal"
    return "pre_post"


def smooth_types(rows: list[FrameRow], feats: list[FrameFeatures],
                 types: list[str]) -> tuple[list[str], list[str]]:
    """Return (smoothed_types, notes-per-frame).  Notes are '' or reason."""
    n = len(types)
    out = list(types)
    notes = [""] * n
    for i, t in enumerate(types):
        if t != "delivery":
            continue
        ts_i = rows[i].ts
        nbrs = [j for j in range(n) if j != i and abs(rows[j].ts - ts_i) <= 1.5]
        nbr_celeb = any(feats[j].has_celebration_cue for j in nbrs)
        prior_3s = [j for j in range(n)
                    if rows[j].ts < ts_i and (ts_i - rows[j].ts) <= 3.0]
        prior_has_delivery = any(types[j] == "delivery" for j in prior_3s)
        if nbr_celeb and not prior_has_delivery:
            out[i] = "pre_post"
            notes[i] = "smoothed:celeb_neighbor"
            continue
        if nbrs:
            replay_share = sum(1 for j in nbrs if types[j] == "replay") / len(nbrs)
            if replay_share > 0.5:
                out[i] = "replay"
                notes[i] = "smoothed:replay_majority"
    return out, notes


# ----------------------------- chunk merging --------------------------------


@dataclass
class Chunk:
    type_: str
    start_ts: float
    end_ts: float
    frame_count: int


CONSEQUENTIAL_TYPES = {"delivery", "replay", "ad", "drs", "umpire_signal"}
NON_BRIDGEABLE = {"ad", "replay", "drs"}


def build_chunks(rows: list[FrameRow], types: list[str]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for r, t in zip(rows, types):
        if chunks and chunks[-1].type_ == t:
            chunks[-1].end_ts = r.ts
            chunks[-1].frame_count += 1
        else:
            chunks.append(Chunk(type_=t, start_ts=r.ts, end_ts=r.ts,
                                frame_count=1))
    # Bridge gap merge
    merged: list[Chunk] = []
    i = 0
    while i < len(chunks):
        cur = chunks[i]
        if (merged and merged[-1].type_ == cur.type_
                and (cur.start_ts - merged[-1].end_ts) <= 1.0):
            # Confirm intervening chunk types are bridgeable.
            # Intervening chunks are all chunks strictly between merged[-1]
            # and cur in the sequence (none if i was right after merged[-1]).
            inter_ok = True
            for k in range(len(merged), i):
                if chunks[k].type_ in NON_BRIDGEABLE:
                    inter_ok = False
                    break
            if inter_ok:
                merged[-1].end_ts = cur.end_ts
                merged[-1].frame_count += cur.frame_count
                i += 1
                continue
        merged.append(cur)
        i += 1
    return merged


# ----------------------------- runner --------------------------------------

MODEL: str = ""  # set in main_async


async def process_clip(client, prod_prompt: str, v2_prompt: str,
                       v1_prompt: str, classify_full,
                       session: str, clip_id: str) -> list[FrameRow]:
    mp4 = DELIVERIES_DIR / session / clip_id / "delivery_window.mp4"
    if not mp4.exists():
        return []
    rows: list[FrameRow] = []
    for ts, jpg in sample_frames(mp4, FPS_SAMPLE):
        row = await gather_frame(client, prod_prompt, v2_prompt, v1_prompt,
                                 jpg, classify_full, session, clip_id, ts)
        rows.append(row)
        await asyncio.sleep(PACING_S)
    return rows


def _label_lookup() -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    with LABEL_CSV.open() as f:
        for r in csv.DictReader(f):
            out[(r["session"], r["clip_id"])] = r["manual_label"]
    return out


def _format_clip_section(emit, session: str, clip_id: str, label: str,
                         rows: list[FrameRow], types: list[str],
                         smoothed: list[str], notes: list[str],
                         chunks: list[Chunk]) -> None:
    clip_dir = DELIVERIES_DIR / session / clip_id
    duration, event = read_window_meta(clip_dir)
    emit("=" * 60)
    emit(f"[CLIP {session}/{clip_id}]")
    emit(f"  duration={duration:.2f}s event_ts={event:.2f}s")
    emit(f"  manual_label={label}")
    emit("")
    emit("  Per-frame tentative types:")
    for r, t in zip(rows, types):
        emit(f"    {r.ts:5.2f}s {t}")
    reassigned = [(r.ts, types[i], smoothed[i], notes[i])
                  for i, r in enumerate(rows) if types[i] != smoothed[i]]
    emit("")
    emit("  After smoothing:")
    if reassigned:
        for ts, before, after, note in reassigned:
            emit(f"    {ts:5.2f}s {before} -> {after}  ({note})")
    else:
        emit("    (no reassignments)")
    emit("")
    emit("  Final chunks:")
    for c in chunks:
        emit(f"    [{c.start_ts:5.2f}s - {c.end_ts:5.2f}s] {c.type_}"
             f"  ({c.frame_count} frames)")
    consequential = [c for c in chunks if c.type_ in CONSEQUENTIAL_TYPES]
    emit("")
    emit("  Consequential chunks (would be saved as videos):")
    if consequential:
        for c in consequential:
            emit(f"    {c.type_}: [{c.start_ts:5.2f}s - {c.end_ts:5.2f}s]")
    else:
        emit("    none")
    emit("")


def _summary_table(emit, header: str, rows: list[tuple[str, str, list[Chunk]]]) -> None:
    emit("=" * 60)
    emit(header)
    emit("")
    if rows and rows[0][1] != "":
        emit("| clip | label | chunks detected | consequential chunks |")
        emit("| ---- | ---- | ---- | ---- |")
        for clip, label, chunks in rows:
            chunk_summary = ", ".join(c.type_ for c in chunks) or "(none)"
            cons = ", ".join(f"{c.type_} [{c.start_ts:.2f}-{c.end_ts:.2f}]"
                             for c in chunks if c.type_ in CONSEQUENTIAL_TYPES) or "none"
            emit(f"| {clip} | {label} | {chunk_summary} | {cons} |")
    else:
        emit("| clip | chunks detected | consequential chunks |")
        emit("| ---- | ---- | ---- |")
        for clip, _, chunks in rows:
            chunk_summary = ", ".join(c.type_ for c in chunks) or "(none)"
            cons = ", ".join(f"{c.type_} [{c.start_ts:.2f}-{c.end_ts:.2f}]"
                             for c in chunks if c.type_ in CONSEQUENTIAL_TYPES) or "none"
            emit(f"| {clip} | {chunk_summary} | {cons} |")
    emit("")


async def main_async() -> int:
    global MODEL
    _ensure_path()
    from groq import AsyncGroq
    from eyes.config import GROQ_API_KEY, GROQ_PRIMARY_MODEL
    from eyes.vision import SCOUT_PROMPT
    from eyes.open_scout import OPEN_PROMPT
    from eyes.open_scout_classify import classify_full

    MODEL = GROQ_PRIMARY_MODEL
    prod_prompt = SCOUT_PROMPT.format(vision_hint=VISION_HINT)
    v2_prompt = OPEN_PROMPT
    v1_prompt = OPEN_PROMPT

    label_map = _label_lookup()
    may3_clips = list_may3_clips()
    rand_clips = pick_random_clips(seed=42, n=10)

    out_lines: list[str] = []

    def emit(line: str) -> None:
        print(line, flush=True)
        out_lines.append(line)

    emit("Test set 1 — 8 May 3 clips (20260503_205835):")
    for s, c, _ in may3_clips:
        emit(f"  {s}/{c}")
    emit("")
    emit("Test set 2 — 10 random clips (seed=42):")
    for s, c, lbl in rand_clips:
        emit(f"  {s}/{c}  manual_label={lbl}")
    emit("")
    emit(f"Sampling at {FPS_SAMPLE} fps; 3 prompts per frame in parallel.")
    emit(f"Model: {MODEL}")
    emit("")

    client = AsyncGroq(api_key=GROQ_API_KEY, timeout=90.0)
    csv_rows: list[FrameRow] = []
    set1_summary: list[tuple[str, str, list[Chunk]]] = []
    set2_summary: list[tuple[str, str, list[Chunk]]] = []

    for label_set, clips, summary, want_label in (
            ("Test set 1 — 8 May 3 clips", may3_clips, set1_summary, False),
            ("Test set 2 — 10 random clips", rand_clips, set2_summary, True),
    ):
        emit("#" * 60)
        emit(f"# {label_set}")
        emit("#" * 60)
        for session, clip_id, lbl_in in clips:
            label = lbl_in if want_label else label_map.get((session, clip_id), "N/A")
            rows = await process_clip(client, prod_prompt, v2_prompt,
                                      v1_prompt, classify_full,
                                      session, clip_id)
            if not rows:
                emit(f"[CLIP {session}/{clip_id}] (no frames sampled)")
                continue
            csv_rows.extend(rows)
            feats = [extract_features(r) for r in rows]
            tentatives = [tentative_type(r, f) for r, f in zip(rows, feats)]
            smoothed, notes = smooth_types(rows, feats, tentatives)
            chunks = build_chunks(rows, smoothed)
            _format_clip_section(emit, session, clip_id, label,
                                 rows, tentatives, smoothed, notes, chunks)
            display_clip = f"{session}/{clip_id}"
            summary.append((display_clip, label if want_label else "", chunks))

    await client.close()

    _summary_table(emit, "Summary — Test set 1 (8 May 3 clips)", set1_summary)
    _summary_table(emit, "Summary — Test set 2 (10 random clips with manual_label)",
                   set2_summary)

    # CSV write
    with OUT_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["clip_id", "session", "ts", "prod_cam", "prod_phase",
                    "v2_broadcast_tag", "v2_class", "open_desc"])
        for r in csv_rows:
            w.writerow([r.clip_id, r.session, f"{r.ts:.3f}", r.prod_cam,
                        r.prod_phase, r.v2_broadcast_tag, r.v2_class,
                        r.open_desc])
    emit(f"Wrote {OUT_CSV} ({len(csv_rows)} frame rows)")

    OUT_TXT.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_TXT}")

    # Class totals across both sets
    cls_totals: Counter[str] = Counter()
    for r in csv_rows:
        cls_totals[r.v2_class] += 1
    print("v2_class totals:",
          ", ".join(f"{k}={cls_totals.get(k, 0)}"
                    for k in ("action", "replay", "ad", "umpire", "other")))
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
