"""Verify (a) the served model identity and (b) re-run FULL prompt on
the OLD high-fidelity clips so we can compare directly to the YouTube
720p/10fps results."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from eyes.config import GEMINI_API_KEY
os.environ.setdefault("GEMINI_API_KEY", GEMINI_API_KEY)

from gemini_ab_schema_test import PROMPT_FULL, parse_json

MODEL = "gemini-3-flash-preview"


def main():
    from google import genai
    from google.genai import types
    client = genai.Client()

    clips = [
        ("ball_test_clip_30fps.mp4",
         "OLD: 1920x1241 30fps — LEFT-handed batsman"),
        ("ball_test_clip_60fps_long.mp4",
         "OLD: 1920x1241 60fps — SHORT/steep, pull"),
    ]

    print(f"requested model: {MODEL}\n")
    out = []
    for fname, label in clips:
        path = ROOT / fname
        data = path.read_bytes()
        size_mb = len(data) / (1024 * 1024)
        print(f"=== {fname}  ({size_mb:.1f} MB) ===")
        print(f"  {label}")

        parts = [
            types.Part.from_bytes(data=data, mime_type="video/mp4"),
            types.Part.from_text(text=PROMPT_FULL),
        ]
        t0 = time.time()
        resp = client.models.generate_content(model=MODEL, contents=parts)
        ms = int((time.time() - t0) * 1000)

        # Try every plausible field the SDK exposes for served-model id
        served = {}
        for attr in ("model_version", "model"):
            v = getattr(resp, attr, None)
            if v:
                served[attr] = v
        if hasattr(resp, "usage_metadata"):
            for attr in ("model_version",):
                v = getattr(resp.usage_metadata, attr, None)
                if v:
                    served[f"usage.{attr}"] = v
        # Dump the whole resp model_dump for any other clue
        try:
            dumped = resp.model_dump()
            for k in ("model", "model_version"):
                if k in dumped and dumped[k] not in served.values():
                    served[f"dump.{k}"] = dumped[k]
        except Exception:
            pass

        print(f"  served-model fields: {served}")
        print(f"  wall: {ms} ms")
        parsed = parse_json(resp.text or "")
        if parsed:
            keep = {k: parsed.get(k) for k in (
                "length", "line", "bowling_angle", "bounce",
                "shot_type", "shot_side", "elevation",
                "contact_quality", "confidence")}
            print(f"  parsed: {json.dumps(keep)}")
        else:
            print(f"  RAW (unparseable): {(resp.text or '')[:300]}")
        print()

        out.append({
            "clip": fname,
            "label": label,
            "size_mb": size_mb,
            "requested_model": MODEL,
            "served": served,
            "ms": ms,
            "raw": resp.text,
            "parsed": parsed,
        })

    out_path = ROOT / "logs" / "audit_v1" / "ab_schema_test" / \
               "model_check_old_clips.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
