import os
"""Negative-control rejection test.

Send the pipeline's `failed_*.jpg` triplets (frames the existing
detector tried and rejected) to Gemini.  These should mostly NOT be
real bowler's-end deliveries.  Measures Gemini's ability to say
is_delivery=false when the input is not a delivery.
"""
from __future__ import annotations
import json, os, re, sys, time, random
from pathlib import Path

ROOT = Path(__file__).parent
SNAP = ROOT / "logs/deliveries/snapshot_20260417_postkill_222206"
OUT = ROOT / "results_gemini_negatives.json"
os.environ.setdefault("GEMINI_API_KEY",
                      os.environ["GEMINI_API_KEY"])

PROMPT = """\
You are watching what may or may not be a single delivery from a live
IPL cricket broadcast.  Three frames are provided in temporal order.

Look at the three frames as a SEQUENCE and decide whether they show a
real bowled delivery from the bowler's-end camera.  Closeups, replays,
between-overs footage, fielding drills, crowd shots, presenter shots,
graphics → NOT a delivery.

Return ONLY a single JSON object on one line:
  {"is_delivery": true,
   "phase_visible": "release",
   "length": "good_length",
   "line": "outside_off",
   "shot": "along_ground",
   "direction": "offside",
   "confidence": 0.7,
   "narrative": "what is actually happening in these 3 frames (20-30 words)"}

If NOT a delivery, set is_delivery=false and "unknown" for the
classification fields, but DESCRIBE WHAT YOU SEE in narrative.
"""

_RETRY = re.compile(r"retry in ([0-9]+(?:\.[0-9]+)?)s")


def call(client, parts, max_retries=5):
    for a in range(max_retries):
        t0 = time.time()
        try:
            r = client.models.generate_content(
                model="gemini-2.5-flash", contents=parts)
            return r.text or "", int((time.time() - t0) * 1000)
        except Exception as e:
            err = str(e)
            if a == max_retries - 1 or not any(
                k in err for k in ("503", "UNAVAILABLE", "429")):
                return f"ERROR: {err[:120]}", int((time.time() - t0) * 1000)
            m = _RETRY.search(err)
            time.sleep(float(m.group(1)) + 1 if m else 4 * (2 ** a))
    return "ERROR: max", 0


def parse(text):
    if not text: return None
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    m = re.search(r"\{[\s\S]*\}", text)
    if not m: return None
    try: return json.loads(m.group(0))
    except: return None


def main():
    from google import genai
    from google.genai import types
    client = genai.Client()

    # find all deliveries with failed_* triplets
    cands = []
    for d in sorted(SNAP.iterdir()):
        if not d.is_dir() or not d.name.startswith("delivery_"): continue
        fs = [d/"failed_start.jpg", d/"failed_mid.jpg", d/"failed_end.jpg"]
        if all(f.exists() and f.stat().st_size > 0 for f in fs):
            cands.append(d.name)
    random.Random(42).shuffle(cands)
    cands = cands[:15]
    print(f"Testing rejection on {len(cands)} failed_* triplets:")
    print(" ", cands)

    out = []
    for i, did in enumerate(cands):
        d = SNAP / did
        parts = []
        for fname, label in [
            ("failed_start.jpg", "frame 1 of 3 (start)"),
            ("failed_mid.jpg",   "frame 2 of 3 (middle)"),
            ("failed_end.jpg",   "frame 3 of 3 (end)"),
        ]:
            with open(d/fname, "rb") as f: data = f.read()
            parts.append(types.Part.from_bytes(data=data, mime_type="image/jpeg"))
            parts.append(types.Part.from_text(text=label))
        parts.append(types.Part.from_text(text=PROMPT))

        raw, ms = call(client, parts)
        p = parse(raw)
        out.append({"id": did, "kind": "failed_triplet",
                    "raw": raw, "parsed": p, "wall_ms": ms})
        if p:
            isd = p.get("is_delivery")
            tag = "REJECT" if isd is False else "ACCEPT"
            print(f"  [{i+1:>2}/{len(cands)}] {did}  {ms/1000:>4.1f}s  "
                  f"{tag:>6}  conf={p.get('confidence')}  "
                  f"{(p.get('narrative') or '')[:90]}")
        else:
            print(f"  [{i+1:>2}/{len(cands)}] {did}  FAIL_PARSE  {raw[:80]}")
        OUT.write_text(json.dumps(out, indent=2))
        time.sleep(0.3)

    rej = sum(1 for r in out if r["parsed"] and
              r["parsed"].get("is_delivery") is False)
    print(f"\nRejected {rej}/{len(out)} of failed_* triplets "
          f"({100*rej/max(1,len(out)):.0f}%)")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
