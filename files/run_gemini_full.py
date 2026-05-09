"""Run Gemini 2.5-flash on all 60 tier-1 deliveries.

Per delivery: 3 frames + structured-JSON prompt → JSON answer with
length / line / shot / direction / phase / confidence / narrative.

Rate-limited (1 call/sec base, exponential backoff on overload).
Saves results incrementally so a crash mid-run doesn't lose progress.
"""
from __future__ import annotations
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
SNAP = ROOT / "logs/deliveries/snapshot_20260417_postkill_222206"
OUT = ROOT / "results_gemini_full.json"

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
are closeups, replays, between-overs footage, fielding drills), set
is_delivery=false and put "unknown" for all classification fields.
"""


def parse_json_from_text(text):
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


_RETRY_HINT = re.compile(r"retry in ([0-9]+(?:\.[0-9]+)?)s")


def call_gemini(client, types, parts, max_retries=8):
    last = ""
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
            last = err
            if not any(k in err for k in ("503", "UNAVAILABLE", "overload",
                                          "RESOURCE_EXHAUSTED", "429")):
                return f"ERROR: {err}", wall
            if attempt >= max_retries - 1:
                return f"ERROR: max_retries: {err[:120]}", wall
            m = _RETRY_HINT.search(err)
            if m:
                delay = float(m.group(1)) + 2.0
            else:
                delay = min(60.0, 4.0 * (2 ** attempt))
            print(f"      retry {attempt+1}: "
                  f"{err[:70]}  sleeping {delay:.0f}s")
            time.sleep(delay)
    return f"ERROR: max_retries: {last}", 0


def main():
    from google import genai
    from google.genai import types
    client = genai.Client()

    rows = json.loads((ROOT / "tier1_deliveries.json").read_text())
    print(f"Running on {len(rows)} tier-1 deliveries...")

    # Resume from existing results if present
    out = []
    if OUT.exists():
        try:
            out = json.loads(OUT.read_text())
            done_ids = {r["id"] for r in out}
            rows = [r for r in rows if r["id"] not in done_ids]
            print(f"Resuming: {len(out)} already done, {len(rows)} remaining")
        except Exception:
            out = []

    base_delay = 0.3  # billing enabled, push the API
    for i, d in enumerate(rows):
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

        if parsed:
            summary = (f"{parsed.get('is_delivery','?')!s:>5}  "
                       f"{parsed.get('length','?')} / "
                       f"{parsed.get('line','?')} / "
                       f"{parsed.get('shot','?')} / "
                       f"{parsed.get('direction','?')}  "
                       f"conf={parsed.get('confidence','?')}")
        else:
            summary = "FAIL_PARSE: " + raw[:80].replace("\n", " ")
        progress = f"[{len(out)}/{len(out) + len(rows) - i - 1}]"
        print(f"  {progress:>9} {d_id}  {wall_ms/1000:>5.1f}s  {summary}")

        # Save every iteration so we don't lose progress
        OUT.write_text(json.dumps(out, indent=2))

        time.sleep(base_delay)

    print(f"\nWrote {OUT}  ({len(out)} entries)")


if __name__ == "__main__":
    main()
