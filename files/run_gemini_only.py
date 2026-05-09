"""Run Gemini 2.5-flash on all 12 sampled tier-1 deliveries with retry.

Use exponential backoff to retry 503/UNAVAILABLE errors so we get a
complete dataset for evaluation.
"""
from __future__ import annotations
import json
import os
import re
import time
from pathlib import Path

ROOT = Path(__file__).parent
SNAP = ROOT / "logs/deliveries/snapshot_20260417_postkill_222206"
OUT = ROOT / "results_gemini_only.json"

os.environ.setdefault(
    "GEMINI_API_KEY", os.environ["GEMINI_API_KEY"])

PROMPT = """\
You are watching a single delivery from a live IPL cricket broadcast.
Three frames are provided in temporal order: start (run-up), key (the
moment of release / shot), and end (immediate aftermath).

Look at the three frames as a SEQUENCE and infer what happened in
this delivery.  Do NOT use any prior knowledge about the match.

Return ONLY a single JSON object on one line, with these fields:

  {
    "is_delivery": true,            // true if a real bowled delivery
    "phase_visible": "release",     // best phase visible: runup, release,
                                    //   flight, shot, post_shot, none
    "length": "good_length",        // yorker | full | good_length | short_of_a_length |
                                    //   short | bouncer | unknown
    "line": "outside_off",          // wide_outside_off | outside_off | on_stumps |
                                    //   on_pads | down_leg | leg_stump | unknown
    "shot": "along_ground",         // defended | along_ground | in_the_air | left | unknown
    "direction": "offside",         // straight | offside | legside | behind_wicket |
                                    //   no_shot | unknown
    "confidence": 0.7,              // 0.0 - 1.0  (how confident overall)
    "narrative": "20-30 word description of what happened"
  }

If the three frames do NOT look like a real bowled delivery (e.g. they
are closeups, replays, between-overs footage), set is_delivery=false
and put "unknown" for all classification fields.
"""


def call_gemini(client, types, parts, max_retries=4):
    delay = 4.0
    for attempt in range(max_retries):
        t0 = time.time()
        try:
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=parts,
            )
            return resp.text or "", int((time.time() - t0) * 1000)
        except Exception as e:
            err = str(e)
            wall = int((time.time() - t0) * 1000)
            if "503" in err or "UNAVAILABLE" in err or "overload" in err.lower():
                if attempt < max_retries - 1:
                    print(f"    overload after {wall}ms, "
                          f"sleeping {delay:.0f}s and retrying ({attempt+1})")
                    time.sleep(delay)
                    delay *= 2
                    continue
            return f"ERROR: {err}", wall
    return "ERROR: max_retries", 0


def parse_json_from_text(text: str) -> dict | None:
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def main():
    from google import genai
    from google.genai import types
    client = genai.Client()

    rows = json.loads((ROOT / "tier1_deliveries.json").read_text())
    step = len(rows) / 12
    picked = [rows[int(i * step)] for i in range(12)]

    out = []
    for d in picked:
        d_id = d["id"]
        folder = SNAP / d_id
        parts = []
        for fname, label in [("moment_start.jpg", "frame 1 of 3 (start, run-up)"),
                              ("moment_key.jpg",   "frame 2 of 3 (key, release/shot)"),
                              ("moment_end.jpg",   "frame 3 of 3 (end, aftermath)")]:
            fp = folder / fname
            if not fp.exists():
                continue
            with open(fp, "rb") as f:
                data = f.read()
            parts.append(types.Part.from_bytes(data=data, mime_type="image/jpeg"))
            parts.append(types.Part.from_text(text=label))
        parts.append(types.Part.from_text(text=PROMPT))

        raw, wall_ms = call_gemini(client, types, parts)
        parsed = parse_json_from_text(raw)
        out.append({
            "id": d_id,
            "raw": raw,
            "parsed": parsed,
            "wall_ms": wall_ms,
            "pipeline_pred": d["pred_raw"],
            "pipeline_runs": d["runs"],
        })
        ok = "OK" if parsed else "FAIL_PARSE"
        if parsed:
            summary = (f"{parsed.get('length','?')} / "
                       f"{parsed.get('line','?')} / "
                       f"{parsed.get('shot','?')} / "
                       f"{parsed.get('direction','?')}")
        else:
            summary = raw[:80].replace("\n", " ")
        print(f"  {d_id}  {wall_ms}ms  {ok}  {summary}")
        OUT.write_text(json.dumps(out, indent=2))

    print(f"\nWrote {OUT}  ({len(out)} entries)")


if __name__ == "__main__":
    main()
