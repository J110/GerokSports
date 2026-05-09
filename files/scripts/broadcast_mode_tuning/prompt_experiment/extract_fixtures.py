#!/usr/bin/env python3
"""Extract 25 fixture frames from session 96b39448 delivery clips.

Categories (5 frames each):
    real          — release moments from real-delivery clips
    replay_overlay — frames showing ANALYSIS / SPEED / WICKET overlays
    replay_action  — replay-angle frames of the action itself
    pre           — bowler-walking-back / pre-delivery moments
    post          — fielder-retrieving / post-delivery moments

Usage:
    cd files/scripts/broadcast_mode_tuning/prompt_experiment
    python3 extract_fixtures.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[3]
SESSION_DIR = REPO_ROOT / "files" / "logs" / "deliveries" / "96b39448" / "auto"
SIDECAR = REPO_ROOT / "logs" / "openscout-96b39448.jsonl"
FIXTURE_DIR = SCRIPT_DIR / "fixtures"

RELEASE_MARKERS = (
    "mid-air", "just released", "just bowled", "just delivered",
    "mid-action", "follow-through", "arm raised", "mid-swing",
    "playing a shot", "ball in flight",
)


def _load_sidecar() -> list[dict]:
    if not SIDECAR.exists():
        return []
    out: list[dict] = []
    for line in SIDECAR.open():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    out.sort(key=lambda r: r.get("ts", 0.0))
    return out


def find_release_offset(clip_id: str, sidecar: list[dict]) -> float | None:
    """Return seconds-into-clip of the first Scout description in this
    clip's window that mentions a release-moment marker, or None if no
    match.
    """
    meta_path = SESSION_DIR / clip_id / "metadata.json"
    if not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text())
    s, e = meta["start_ts"], meta["end_ts"]
    for r in sidecar:
        ts = r.get("ts", 0.0)
        if ts < s or ts > e:
            continue
        txt = (r.get("raw_text") or "").lower()
        if any(m in txt for m in RELEASE_MARKERS):
            return max(0.0, ts - s)
    return None

# (category, clip_id, t_seconds_into_clip, fixture_index)
SAMPLES = [
    # 5 real deliveries — release/play moment (mid clip)
    ("real", "d001", 6.0, 1),
    ("real", "d002", 6.0, 2),
    ("real", "d003", 6.0, 3),
    ("real", "d013", 6.0, 4),
    ("real", "d014", 6.0, 5),
    # 5 replay-with-overlay frames (early seconds of replay clips,
    # where the broadcast splash / ANALYSIS / WICKET / SPEED graphic
    # dominates)
    ("replay_overlay", "d010", 1.0, 1),
    ("replay_overlay", "d010", 2.0, 2),
    ("replay_overlay", "d012", 1.0, 3),
    ("replay_overlay", "d012", 2.0, 4),
    ("replay_overlay", "d015", 1.5, 5),
    # 5 replay-of-action frames (mid-clip, where the slow-mo action
    # itself is being shown)
    ("replay_action", "d008", 5.0, 1),
    ("replay_action", "d009", 5.0, 2),
    ("replay_action", "d011", 5.0, 3),
    ("replay_action", "d016", 5.0, 4),
    ("replay_action", "d017", 5.0, 5),
    # 5 pre-delivery frames — d005 + early seconds of real clips,
    # where the bowler is walking back / setting up
    ("pre", "d005", 4.0, 1),
    ("pre", "d001", 0.8, 2),
    ("pre", "d002", 0.8, 3),
    ("pre", "d013", 0.8, 4),
    ("pre", "d018", 0.8, 5),
    # 5 post-delivery frames — d006 + late seconds of real clips,
    # where the fielder is retrieving / batters are running
    ("post", "d006", 5.0, 1),
    ("post", "d001", 12.0, 2),
    ("post", "d002", 12.0, 3),
    ("post", "d013", 12.0, 4),
    ("post", "d019", 12.0, 5),
]


def grab(mp4: Path, t_sec: float) -> bytes | None:
    cap = cv2.VideoCapture(str(mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if fps <= 0 or total <= 0:
        cap.release()
        return None
    duration = total / fps
    t = min(t_sec, max(0.0, duration - 0.05))
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return None
    ok2, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return buf.tobytes() if ok2 else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only-real-release",
        action="store_true",
        help="Only re-extract real_001..real_005, choosing each clip's "
             "first frame whose Scout description mentions a "
             "release-moment marker.  Falls back to clip middle on miss.",
    )
    args = parser.parse_args()

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    sidecar: list[dict] = []
    if args.only_real_release:
        sidecar = _load_sidecar()
        print(f"Loaded {len(sidecar)} sidecar records from {SIDECAR.name}")

    samples = SAMPLES
    if args.only_real_release:
        samples = [s for s in SAMPLES if s[0] == "real"]

    written = 0
    for category, clip_id, t_sec, idx in samples:
        mp4 = SESSION_DIR / clip_id / "delivery.mp4"
        if not mp4.exists():
            print(f"[skip] missing {mp4}")
            continue

        chosen_t = t_sec
        note = f"middle @ {t_sec:.1f}s"
        if args.only_real_release and category == "real":
            off = find_release_offset(clip_id, sidecar)
            if off is None:
                print(f"[warn] {clip_id}: no release marker in Scout "
                      f"sidecar; falling back to middle")
            else:
                chosen_t = off
                note = f"release @ {off:.2f}s"

        jpg = grab(mp4, chosen_t)
        if jpg is None:
            print(f"[fail] {clip_id} @ {chosen_t:.2f}s")
            continue
        out = FIXTURE_DIR / f"{category}_{idx:03d}.jpg"
        out.write_bytes(jpg)
        written += 1
        print(f"[ok] {out.name}  <- {clip_id}  {note}")
    print(f"\nWrote {written}/{len(samples)} fixtures to {FIXTURE_DIR}")
    return 0 if written == len(samples) else 1


if __name__ == "__main__":
    raise SystemExit(main())
