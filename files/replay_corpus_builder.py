"""Replay-detector corpus builder.

Generates a labelled clip corpus for validating the RC-1 (replay overlay
detection) and RC-2 (slow-motion detection) components, per the
validation plan:

  - 12 clips spanning CLEAN, CLEAN_POST_BOUNDARY, MIXED_FRONT,
    MIXED_BACK, REPLAY_POLLUTED
  - Each clip labelled with frame-level live vs replay regions at
    ~1 s resolution
  - Companion review HTML embedding the clip video and proposed
    regions on a simple timeline SVG
  - JSONL written to files/logs/replay_detector_corpus.jsonl so it's
    trivial to version-control alongside the DWR code

The labelling pass is driven by contact sheets (5x5 thumbnails per
clip with per-frame timestamps) which the labeller consumes to
propose boundaries.  Initial AI-labelled regions are written to the
JSONL with explicit per-clip uncertainty notes; the review HTML is
the tool the human uses to spot-check and correct.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Literal

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
DELIVERIES = ROOT / "logs" / "deliveries"
CORPUS_DIR = ROOT / "logs" / "replay_detector_corpus"
CORPUS_DIR.mkdir(parents=True, exist_ok=True)
SHEETS_DIR = CORPUS_DIR / "contact_sheets"
SHEETS_DIR.mkdir(parents=True, exist_ok=True)
VIDEOS_DIR = CORPUS_DIR / "videos"
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

JSONL_PATH = ROOT / "logs" / "replay_detector_corpus.jsonl"
REVIEW_HTML = CORPUS_DIR / "review.html"

LABEL_TYPES = (
    "CLEAN", "CLEAN_POST_BOUNDARY",
    "MIXED_FRONT", "MIXED_BACK", "REPLAY_POLLUTED",
)


@dataclass
class ClipSpec:
    clip_key: str
    session: str
    delivery_id: str
    label: str
    prior_event: str | None = None
    inter_event_s: float | None = None
    notes: str = ""


# 12-clip corpus per the agreed plan
CORPUS: list[ClipSpec] = [
    # --- CLEAN padding (variety of outcomes, none post-boundary) ---
    ClipSpec("c01_d002_extra", "20260421_195050", "d002", "CLEAN",
             prior_event="DOT",
             notes="EXTRA (wide/no-ball variety), tests detector on unusual deliveries"),
    ClipSpec("c02_d008_single", "20260421_195050", "d008", "CLEAN",
             prior_event="DOT",
             notes="1-run post-DOT, visible action variety"),
    ClipSpec("c03_d019_defensive", "20260421_195050", "d019", "CLEAN",
             prior_event="1_RUNS",
             notes="DOT defensive post-1R, low-motion live test"),
    # --- CLEAN user anchors ---
    ClipSpec("c04_d023_anchor", "20260421_195050", "d023", "CLEAN",
             prior_event="DOT",
             notes="User-labelled 'almost perfect' anchor"),
    ClipSpec("c05_d024_anchor", "20260421_195050", "d024", "CLEAN",
             prior_event="2_RUNS",
             notes="User-labelled 'almost perfect' anchor"),
    # --- CLEAN_POST_BOUNDARY (tight timing, hardest case for detectors) ---
    ClipSpec("c06_d039_post_four", "20260421_195050", "d039",
             "CLEAN_POST_BOUNDARY",
             prior_event="FOUR", inter_event_s=22.5,
             notes="Tight 22.5s post-FOUR — detector should NOT false-positive"),
    ClipSpec("c07_d069_post_six", "20260421_195050", "d069",
             "CLEAN_POST_BOUNDARY",
             prior_event="SIX", inter_event_s=23.0,
             notes="Tight 23.0s post-SIX — detector should NOT false-positive"),
    # --- MIXED_FRONT ---
    ClipSpec("c08_d027_mixed_front", "20260421_195050", "d027",
             "MIXED_FRONT",
             prior_event="1_RUNS",
             notes="User-labelled: 'first 30-40% is live delivery, rest replay/reaction'"),
    # --- MIXED_BACK ---
    ClipSpec("c09_d025_mixed_back", "20260421_195050", "d025",
             "MIXED_BACK",
             prior_event="2_RUNS",
             notes="User-labelled: 'only last 30-40% is the delivery'"),
    ClipSpec("c10_d026_mixed_back", "20260421_195050", "d026",
             "MIXED_BACK",
             prior_event="SIX", inter_event_s=4.5,
             notes="User-labelled 'identical to d025'; inter_event=4.5s "
                   "suggests phantom event — may be REPLAY_POLLUTED; "
                   "verify during labelling"),
    # --- REPLAY_POLLUTED ---
    ClipSpec("c11_d028_wicket_post_six", "20260421_195050", "d028",
             "REPLAY_POLLUTED",
             prior_event="SIX", inter_event_s=54.3,
             notes="Candidate REPLAY_POLLUTED — WICKET event after SIX; "
                   "verify during labelling"),
    ClipSpec("c12_d021_post_six_bakeoff", "20260420_202239", "d021",
             "REPLAY_POLLUTED",
             prior_event="SIX", inter_event_s=64.5,
             notes="Cross-session anchor — diagnosed today as post-SIX "
                   "replay cycle. Gemini classified content as 'slog' "
                   "matching d020's SIX, not d021's actual FOUR delivery."),
]


# ── Contact-sheet generation ────────────────────────────────────────


def _extract_frames_evenly(mp4_path: Path, n: int = 25
                           ) -> list[tuple[float, np.ndarray]]:
    """Return n evenly-spaced frames with their relative timestamps.

    Timestamps are clip-relative seconds (0.0 at first extracted
    frame, not necessarily the first frame of the mp4).
    """
    cap = cv2.VideoCapture(str(mp4_path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if total <= 0:
        cap.release()
        return []
    step = (total - 1) / float(n - 1) if n > 1 else 0.0
    idxs = [int(round(i * step)) for i in range(n)]
    out: list[tuple[float, np.ndarray]] = []
    for idx in sorted(set(idxs)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, fr = cap.read()
        if not ok:
            continue
        out.append((idx / fps, fr))
    cap.release()
    return out


def _label_thumb(img: np.ndarray, ts: float, idx: int,
                 banner: str = "") -> np.ndarray:
    """Annotate a thumbnail with its timestamp + index for easy reference."""
    h, w = img.shape[:2]
    label = f"#{idx:02d}  t={ts:5.2f}s"
    pad = 28
    canvas = np.zeros((h + pad, w, 3), dtype=img.dtype)
    canvas[:h] = img
    cv2.putText(canvas, label, (8, h + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (240, 240, 240), 1,
                cv2.LINE_AA)
    if banner:
        cv2.rectangle(canvas, (0, 0), (w, 22), (40, 40, 40), -1)
        cv2.putText(canvas, banner, (8, 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1,
                    cv2.LINE_AA)
    return canvas


def make_contact_sheet(mp4_path: Path,
                       out_path: Path,
                       cols: int = 5,
                       rows: int = 5,
                       thumb_w: int = 320,
                       banner: str = "") -> tuple[int, float]:
    """Generate a cols x rows contact sheet of evenly-spaced thumbnails.

    Returns (n_frames_drawn, clip_duration_s).
    """
    n = cols * rows
    frames = _extract_frames_evenly(mp4_path, n=n)
    if not frames:
        return 0, 0.0
    dur = frames[-1][0] - frames[0][0]
    # Resize every frame to uniform dimensions
    thumbs = []
    for idx, (ts, fr) in enumerate(frames):
        h, w = fr.shape[:2]
        scale = thumb_w / float(w)
        tw, th = thumb_w, int(round(h * scale))
        resized = cv2.resize(fr, (tw, th), interpolation=cv2.INTER_AREA)
        thumbs.append(_label_thumb(resized, ts, idx, banner=banner))
    th = thumbs[0].shape[0]
    tw = thumbs[0].shape[1]
    sheet = np.zeros((rows * th, cols * tw, 3), dtype=thumbs[0].dtype)
    for i, t in enumerate(thumbs[:n]):
        r, c = divmod(i, cols)
        sheet[r * th:(r + 1) * th, c * tw:(c + 1) * tw] = t
    cv2.imwrite(str(out_path), sheet,
                [cv2.IMWRITE_JPEG_QUALITY, 82])
    return len(thumbs), dur


# ── Per-clip metadata helpers ───────────────────────────────────────


def _clip_paths(spec: ClipSpec) -> tuple[Path, Path]:
    src_mp4 = DELIVERIES / spec.session / spec.delivery_id / "delivery_window.mp4"
    sheet = SHEETS_DIR / f"{spec.clip_key}.jpg"
    return src_mp4, sheet


def _copy_video(spec: ClipSpec) -> Path:
    src, _ = _clip_paths(spec)
    dst = VIDEOS_DIR / f"{spec.clip_key}.mp4"
    if not dst.exists():
        import shutil
        shutil.copy2(src, dst)
    return dst


def build_all_contact_sheets() -> list[dict]:
    rows: list[dict] = []
    for spec in CORPUS:
        src, sheet = _clip_paths(spec)
        if not src.exists():
            print(f"[skip] {spec.clip_key}: missing {src}")
            continue
        _copy_video(spec)
        banner = f"{spec.clip_key}   label={spec.label}   prior={spec.prior_event}"
        n, dur = make_contact_sheet(src, sheet, banner=banner)
        rows.append({
            "clip_key": spec.clip_key,
            "session": spec.session,
            "delivery_id": spec.delivery_id,
            "mp4_rel": f"videos/{spec.clip_key}.mp4",
            "sheet_rel": f"contact_sheets/{spec.clip_key}.jpg",
            "duration_s": round(dur, 2),
            "n_thumbs": n,
            "label": spec.label,
            "prior_event": spec.prior_event,
            "inter_event_s": spec.inter_event_s,
            "notes": spec.notes,
        })
        print(f"  {spec.clip_key}  dur={dur:.1f}s  n={n}  -> {sheet.name}")
    return rows


if __name__ == "__main__":
    rows = build_all_contact_sheets()
    (CORPUS_DIR / "clips_index.json").write_text(
        json.dumps(rows, indent=2))
    print(f"\nWrote {len(rows)} contact sheets to {SHEETS_DIR}")
    print(f"Index: {CORPUS_DIR / 'clips_index.json'}")
