"""Smoke-test gemini_delivery_classifier on the existing tier-1 clips.

Sends the two known-truth clips through the Tier 1+2 schema classifier
end-to-end (mp4 path overload — the clips are already mp4, no need to
recompile from frames for this test).  Verifies:
  - SDK / key reachable
  - JSON parse + enum normalisation
  - delivery_info legacy shape preserved
  - Tier 1+2 fields present
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from gemini_delivery_classifier import (
    GeminiDeliveryClassifier, _unknown_result,
)


CLIPS = [
    ("ball_test_clip_30fps.mp4", 0,
     "Clip 1 (15s) — LEFT-handed Pant, played square of wicket"),
    ("ball_test_clip_60fps_long.mp4", 0,
     "Clip 3 (45s) — SHORT delivery, steep bounce, dab (right-handed)"),
]

LEGACY_KEYS = [
    "length", "line", "bowling_angle", "bounce",
    "shot_type", "shot_elevation", "shot_action", "shot_intent",
    "shot_direction", "swing_or_seam", "commentary_line",
]
NEW_KEYS = [
    "batsman_handed", "bowling_arm", "bowling_type",
    "contact_quality", "narrative",
]


def main():
    clf = GeminiDeliveryClassifier()
    if not clf.available():
        print(f"FATAL: classifier unavailable: {clf._init_error}")
        sys.exit(1)
    print(f"Classifier ready: model={clf._model}")

    out = []
    for fname, runs, truth in CLIPS:
        path = ROOT / fname
        if not path.exists():
            print(f"  SKIP {fname} — not found")
            continue
        size_mb = path.stat().st_size / 1024 / 1024
        print(f"\n{'=' * 72}")
        print(f"{fname}  ({size_mb:.1f} MB)  truth: {truth}")
        print(f"{'=' * 72}")

        t0 = time.time()
        r = clf.classify_video(str(path), runs=runs)
        wall = time.time() - t0

        # Schema completeness check
        missing_legacy = [k for k in LEGACY_KEYS if k not in r]
        missing_new = [k for k in NEW_KEYS if k not in r]
        if missing_legacy or missing_new:
            print(f"  SCHEMA INCOMPLETE: missing_legacy={missing_legacy} "
                  f"missing_new={missing_new}")

        print(f"  wall: {wall:.1f}s  conf: {r.get('_gemini_confidence')}")
        print(f"  ─ Tier 1 + 2 (Gemini) ─")
        print(f"    handedness:       {r.get('batsman_handed')}")
        print(f"    bowling_arm:      {r.get('bowling_arm')}")
        print(f"    bowling_type:     {r.get('bowling_type')}")
        print(f"    bowling_angle:    {r.get('bowling_angle')}")
        print(f"    length:           {r.get('length')}")
        print(f"    line:             {r.get('line')}")
        print(f"    bounce:           {r.get('bounce')}")
        print(f"    shot_action:      {r.get('shot_action')}")
        print(f"    shot_side/zone:   "
              f"{r['shot_direction'].get('side')} / "
              f"{r['shot_direction'].get('zone')}")
        print(f"    elevation:        {r.get('shot_elevation')}")
        print(f"    contact_quality:  {r.get('contact_quality')}")
        print(f"  ─ Narrative ─")
        print(f"    {r.get('narrative')}")
        print(f"  ─ Commentary line ─")
        print(f"    {r.get('commentary_line')}")
        if r.get("_untrackable"):
            print(f"  ! UNTRACKABLE: {r.get('_skip_reason')}")

        out.append({
            "clip": fname,
            "truth": truth,
            "wall_s": round(wall, 2),
            "result": r,
        })

    out_path = ROOT / "results_smoke_gemini.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {out_path.name}")


if __name__ == "__main__":
    main()
