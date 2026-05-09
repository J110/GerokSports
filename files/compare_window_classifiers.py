"""Per-window classifier comparison: Moondream vs Gemini.

Sample 12 tier-1 deliveries from the 60-delivery snapshot.  For each
delivery, treat the (moment_start, moment_key, moment_end) frames as
the 3-frame window sample (25%/50%/75% of an idealised window).

Run two classifiers on the same window:

  A. Moondream (local MLX) — `query` per frame, aggregate descriptions.
     This is the "free, slow, local" path.
  B. Gemini 2.5-flash — single API call with all 3 frames and a
     structured JSON prompt.  This is the "cheap, fast, hosted" path.

Compare both to the existing pipeline's tier-1 prediction
(length / line / shot / direction).
"""
from __future__ import annotations
import json
import os
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).parent
SNAP = ROOT / "logs/deliveries/snapshot_20260417_postkill_222206"
OUT = ROOT / "results_window_compare.json"

os.environ.setdefault(
    "GEMINI_API_KEY", os.environ["GEMINI_API_KEY"])

DELIVERY_QUESTION_GEMINI = """\
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

MOONDREAM_QUERY_PER_FRAME = """\
This is ONE frame from a single cricket delivery (3 frames are
captured per delivery; this is one of them).  Look at it carefully and
return ONLY a single JSON object on one line with these fields:

  {"is_delivery_view": true,    // true if this is a bowler's-end view of an active delivery
   "phase": "release",          // runup | release | flight | shot | post_shot | none
   "length": "good_length",     // yorker | full | good_length | short_of_a_length | short | bouncer | unknown
   "line": "outside_off",       // wide_outside_off | outside_off | on_stumps | on_pads | down_leg | leg_stump | unknown
   "shot": "along_ground",      // defended | along_ground | in_the_air | left | unknown
   "direction": "offside",      // straight | offside | legside | behind_wicket | no_shot | unknown
   "confidence": 0.6}           // 0.0 - 1.0

If the frame is NOT a bowler's-end delivery view (closeup, replay,
between-overs etc.), set is_delivery_view=false and "unknown" for all
classification fields.
"""


# ── Sampling ───────────────────────────────────────────────────────

def sample_deliveries(all_rows, n=12):
    """Take a stratified spread across the tier-1 list."""
    if n >= len(all_rows):
        return all_rows
    step = len(all_rows) / n
    picks = [all_rows[int(i * step)] for i in range(n)]
    return picks


# ── Moondream ──────────────────────────────────────────────────────

def run_moondream(deliveries):
    from pitch_grounder import _get_model, _bgr_to_pil, warmup
    print("Loading Moondream...")
    model = _get_model()
    if model is None:
        raise SystemExit("Moondream unavailable")
    print("Warming up...")
    warmup()

    out = []
    for d in deliveries:
        d_id = d["id"]
        folder = SNAP / d_id
        results = {"id": d_id, "per_frame": {}}
        t_total = time.time()
        for label, fname in [("start", "moment_start.jpg"),
                              ("key",   "moment_key.jpg"),
                              ("end",   "moment_end.jpg")]:
            fp = folder / fname
            if not fp.exists():
                results["per_frame"][label] = {"error": "missing"}
                continue
            bgr = cv2.imread(str(fp))
            pil = _bgr_to_pil(bgr)
            t0 = time.time()
            try:
                ans = model.query(pil, MOONDREAM_QUERY_PER_FRAME)
                raw = (ans.get("answer") or "").strip()
            except Exception as e:
                raw = f"ERROR: {e}"
            results["per_frame"][label] = {
                "raw": raw,
                "ms": int((time.time() - t0) * 1000),
            }
        results["wall_ms"] = int((time.time() - t_total) * 1000)
        out.append(results)
        print(f"  {d_id}  total {results['wall_ms']} ms")
    return out


# ── Gemini ─────────────────────────────────────────────────────────

def run_gemini(deliveries):
    from google import genai
    from google.genai import types
    client = genai.Client()
    model_id = "gemini-2.5-flash"
    print(f"Using Gemini model: {model_id}")

    out = []
    for d in deliveries:
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
        parts.append(types.Part.from_text(text=DELIVERY_QUESTION_GEMINI))

        t0 = time.time()
        try:
            resp = client.models.generate_content(
                model=model_id,
                contents=parts,
            )
            raw = resp.text or ""
        except Exception as e:
            raw = f"ERROR: {e}"
        wall_ms = int((time.time() - t0) * 1000)
        out.append({"id": d_id, "raw": raw, "wall_ms": wall_ms})
        print(f"  {d_id}  {wall_ms} ms  {raw[:80].replace(chr(10),' ')}")
    return out


# ── Main ───────────────────────────────────────────────────────────

def main():
    rows = json.loads((ROOT / "tier1_deliveries.json").read_text())
    picked = sample_deliveries(rows, n=12)
    print(f"Sampled {len(picked)} deliveries from {len(rows)} tier-1:")
    for d in picked:
        print(f"  {d['id']}  pipeline-pred: {d['pred_raw']}")

    print("\n=== Phase A: Gemini 2.5-flash on 3-frame windows ===")
    gemini_results = run_gemini(picked)

    print("\n=== Phase B: Moondream per-frame query + aggregate ===")
    moondream_results = run_moondream(picked)

    out = {
        "picked": picked,
        "gemini": gemini_results,
        "moondream": moondream_results,
    }
    OUT.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
