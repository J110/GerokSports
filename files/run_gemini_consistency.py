import os
"""Confidence-calibration test via self-consistency.

Re-call Gemini 3 times on the same 20 tier-1 deliveries.  For each
delivery, measure agreement across the three calls on each field.

If high-confidence answers (conf >= 0.9) are stable across calls
while low-confidence answers wobble, then confidence carries signal.
If high and low confidence answers wobble equally, confidence is
useless for downstream filtering.
"""
from __future__ import annotations
import json, os, re, time, random
from pathlib import Path

ROOT = Path(__file__).parent
SNAP = ROOT / "logs/deliveries/snapshot_20260417_postkill_222206"
OUT = ROOT / "results_gemini_consistency.json"
os.environ.setdefault("GEMINI_API_KEY",
                      os.environ["GEMINI_API_KEY"])

PROMPT = """\
You are watching a single delivery from a live IPL cricket broadcast.
Three frames are provided in temporal order: start, key, end.

Return ONLY a single JSON object on one line:
  {"is_delivery": true,
   "phase_visible": "release",
   "length": "good_length",
   "line": "outside_off",
   "shot": "along_ground",
   "direction": "offside",
   "confidence": 0.7,
   "narrative": "20-30 word description"}

If the three frames do NOT look like a real bowled delivery, set
is_delivery=false and "unknown" for all classification fields.
"""

_RETRY = re.compile(r"retry in ([0-9]+(?:\.[0-9]+)?)s")


def call(client, parts, max_retries=5):
    for a in range(max_retries):
        t0 = time.time()
        try:
            r = client.models.generate_content(
                model="gemini-2.5-flash", contents=parts)
            return r.text or "", int((time.time()-t0)*1000)
        except Exception as e:
            err = str(e)
            if a == max_retries-1 or not any(
                k in err for k in ("503","UNAVAILABLE","429")):
                return f"ERROR: {err[:120]}", int((time.time()-t0)*1000)
            m = _RETRY.search(err)
            time.sleep(float(m.group(1))+1 if m else 4*(2**a))
    return "ERROR: max", 0


def parse(text):
    if not text: return None
    text = re.sub(r"^```(?:json)?\s*|\s*```$","",text.strip())
    m = re.search(r"\{[\s\S]*\}", text)
    if not m: return None
    try: return json.loads(m.group(0))
    except: return None


def main():
    from google import genai
    from google.genai import types
    client = genai.Client()

    rows = json.loads((ROOT / "tier1_deliveries.json").read_text())
    rng = random.Random(7)
    rng.shuffle(rows)
    rows = rows[:20]
    print(f"Self-consistency: 20 deliveries x 3 calls = 60 calls\n")

    out = []
    if OUT.exists():
        try:
            out = json.loads(OUT.read_text())
            done = {(r["id"], r["call"]) for r in out if r.get("parsed")}
            print(f"  resuming, {len(done)} successful calls already")
        except Exception:
            pass
    else:
        done = set()

    for i, d in enumerate(rows):
        did = d["id"]
        folder = SNAP / did
        for call_idx in (1, 2, 3):
            if (did, call_idx) in done: continue
            parts = []
            for fname in ("moment_start.jpg","moment_key.jpg","moment_end.jpg"):
                with open(folder/fname,"rb") as f: data=f.read()
                parts.append(types.Part.from_bytes(data=data, mime_type="image/jpeg"))
            parts.append(types.Part.from_text(text=PROMPT))

            raw, ms = call(client, parts)
            p = parse(raw)
            out.append({"id": did, "call": call_idx, "raw": raw,
                        "parsed": p, "wall_ms": ms})
            tag = (f"is_del={p.get('is_delivery')} conf={p.get('confidence')} "
                   f"L={p.get('length')} {p.get('line')}/"
                   f"{p.get('shot')}/{p.get('direction')}") if p else "FAIL"
            print(f"  {did} call{call_idx}  {ms/1000:>4.1f}s  {tag}")
            OUT.write_text(json.dumps(out, indent=2))
            time.sleep(0.3)

    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
