"""A/B test: does Gemini's per-field accuracy depend on schema size?

Test design (per the user's framing):
  Hypothesis A — "schema overload": the 14-field full schema overwhelms
    the model's joint-field reasoning.  When asked for fewer fields,
    the model gives more accurate answers and shows real variance.
  Hypothesis B — "input perception ceiling": the bowler's-end clip
    fundamentally underdetermines length / shot_type, regardless of
    how the question is asked.  Smaller schemas would still collapse
    to the modal answer ("good_length", "drive", "outside_off").

Three prompt variants run per clip:
  FULL    — the existing 14-field schema (control / baseline)
  MIN     — 3 fields only: is_valid_delivery, length, shot_type
  SPLIT   — two calls per clip:
              BOWLING — length, line, bowling_angle, bounce
              BATTING — shot_type, shot_side, elevation, contact_quality

Clips:
  3 truth-labelled clips (windows 19/21/23 from the NZ-vs-SL session)
    — used for per-field accuracy.
  2 additional real-delivery clips (windows 9 and 14) without ground
    truth — used only for modal-tuple analysis (does length collapse
    to the same modal value across different deliveries?).

Outputs:
  logs/audit_v1/ab_schema_test/results.json
  logs/audit_v1/ab_schema_test/report.md

Cost: 5 clips * 4 calls * ~$0.0022 ≈ $0.05 total.
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent
SESSION = "20260420_140137"
WIN_ROOT = ROOT / "logs" / "deliveries" / SESSION / "windows"
FIXTURE = ROOT / "logs" / "audit_v1" / "fixtures" / f"over_test_{SESSION}.json"
OUT = ROOT / "logs" / "audit_v1" / "ab_schema_test"

# Match the production classifier's model
MODEL = "gemini-3-flash-preview"


# ───────────────── prompts ─────────────────

PROMPT_FULL = """\
You are watching a short video clip (8-15 s) of a single cricket \
delivery captured live from the bowler's-end TV camera.  The score \
advanced after this clip, so a delivery DEFINITELY occurred.

Return ONLY a single JSON object on one line, no prose, no markdown.

Schema (every field required, "unknown" always allowed and PREFERRED \
over guessing):
{
  "is_valid_delivery":  true | false,
  "batsman_handed":     "right" | "left" | "unknown",
  "bowling_arm":        "right" | "left" | "unknown",
  "bowling_angle":      "over_the_wicket" | "round_the_wicket" | "unknown",
  "bowling_type":       "fast" | "medium" | "spin" | "unknown",
  "length":             "yorker" | "full" | "good_length" |
                        "short_of_length" | "short" | "bouncer" |
                        "full_toss" | "unknown",
  "line":               "wide_outside_off" | "outside_off" | "off_stump" |
                        "middle_stump" | "leg_stump" | "down_leg" |
                        "wide_down_leg" | "unknown",
  "bounce":             "low" | "normal" | "steep" | "extra" | "unknown",
  "shot_played":        true | false,
  "shot_type":          "leave" | "defend" | "drive" | "cut" | "pull" |
                        "hook" | "flick" | "glance" | "sweep" |
                        "reverse_sweep" | "slog" | "dab" | "ramp" |
                        "no_shot" | "unknown",
  "shot_side":          "off" | "leg" | "straight" | "behind" | "no_shot",
  "shot_angle":         "behind_wicket" | "square" | "mid" |
                        "down_ground" | "no_shot",
  "elevation":          "along_ground" | "in_air" | "no_shot",
  "contact_quality":    "middled" | "well_timed" | "mistimed" |
                        "edged" | "inside_edge" | "outside_edge" |
                        "off_pad" | "beaten" | "left_alone" | "missed" |
                        "unknown",
  "confidence":         "high" | "medium" | "low"
}

CRITICAL: do not pull from cricket priors.  Length must be derived \
from where the ball pitches relative to the batter — not from \
"what's most common in the IPL".  "unknown" is a valid answer.
"""


PROMPT_MIN = """\
You are watching a short video clip (8-15 s) of a single cricket \
delivery from the bowler's-end TV camera.  Classify only THREE fields.

Return ONLY a single JSON object on one line.  "unknown" is always \
allowed and PREFERRED over guessing.

{
  "is_valid_delivery": true | false,
  "length":            "yorker" | "full" | "good_length" |
                       "short_of_length" | "short" | "bouncer" |
                       "full_toss" | "unknown",
  "shot_type":         "leave" | "defend" | "drive" | "cut" | "pull" |
                       "hook" | "flick" | "glance" | "sweep" |
                       "reverse_sweep" | "slog" | "dab" | "ramp" |
                       "no_shot" | "unknown"
}

CRITICAL: do not pull from cricket priors.  Length must be derived \
from where the ball pitches relative to the batter — not from \
"what's most common in the IPL".  "unknown" is a valid answer.
"""


PROMPT_BOWLING = """\
You are watching a short video clip (8-15 s) of a single cricket \
delivery from the bowler's-end TV camera.  Classify ONLY the BOWLING \
fields — what the bowler bowled.  Ignore what the batter did.

Return ONLY a single JSON object on one line.  "unknown" is always \
allowed and PREFERRED over guessing.

{
  "length":         "yorker" | "full" | "good_length" |
                    "short_of_length" | "short" | "bouncer" |
                    "full_toss" | "unknown",
  "line":           "wide_outside_off" | "outside_off" | "off_stump" |
                    "middle_stump" | "leg_stump" | "down_leg" |
                    "wide_down_leg" | "unknown",
  "bowling_angle":  "over_the_wicket" | "round_the_wicket" | "unknown",
  "bounce":         "low" | "normal" | "steep" | "extra" | "unknown"
}

CRITICAL: derive length from where the ball pitches relative to the \
batter — not from any cricket prior about modal lengths.
"""


PROMPT_BATTING = """\
You are watching a short video clip (8-15 s) of a single cricket \
delivery from the bowler's-end TV camera.  Classify ONLY the BATTING \
fields — what the batter did.  Ignore what the bowler bowled.

Return ONLY a single JSON object on one line.  "unknown" is always \
allowed and PREFERRED over guessing.  If the batter played no shot \
(left it / missed entirely), use "no_shot" / "leave" / "missed".

{
  "shot_type":       "leave" | "defend" | "drive" | "cut" | "pull" |
                     "hook" | "flick" | "glance" | "sweep" |
                     "reverse_sweep" | "slog" | "dab" | "ramp" |
                     "no_shot" | "unknown",
  "shot_side":       "off" | "leg" | "straight" | "behind" | "no_shot",
  "elevation":       "along_ground" | "in_air" | "no_shot",
  "contact_quality": "middled" | "well_timed" | "mistimed" |
                     "edged" | "inside_edge" | "outside_edge" |
                     "off_pad" | "beaten" | "left_alone" | "missed" |
                     "unknown"
}

CRITICAL: derive shot from what the bat does — not from any cricket \
prior about modal shots.
"""


# ───────────────── clip selection ─────────────────

# 3 clips with hand-graded ground truth — used for per-field accuracy.
GRADED_CLIPS = [
    {"window_id": 19, "label": "broadcast 3.0 (Milne / K Mendis, dot)"},
    {"window_id": 21, "label": "broadcast 3.1 (Milne / K Mendis, dot)"},
    {"window_id": 23, "label": "broadcast 3.2 (Milne / K Mendis, FOUR)"},
]

# 2 more confirmed real deliveries — no truth, used for modal-tuple
# distribution only (do answers vary across different real deliveries?).
EXTRA_CLIPS = [
    {"window_id": 9, "label": "broadcast 1.5 (Milne / Mendis, no run, full)"},
    {"window_id": 14, "label": "broadcast 2.4 (Lister / Mendis, FOUR)"},
]

ALL_CLIPS = GRADED_CLIPS + EXTRA_CLIPS


# ───────────────── Gemini client ─────────────────

def make_client():
    """Reuse the same SDK init path as the production classifier."""
    sys.path.insert(0, str(ROOT))
    from eyes.config import GEMINI_API_KEY
    os.environ.setdefault("GEMINI_API_KEY", GEMINI_API_KEY)
    from google import genai
    from google.genai import types
    client = genai.Client()
    return client, types


def call_gemini(client, types, mp4_bytes: bytes, prompt: str) -> dict:
    """One Gemini call.  Returns {raw, parsed, ms, error}."""
    parts = [
        types.Part.from_bytes(data=mp4_bytes, mime_type="video/mp4"),
        types.Part.from_text(text=prompt),
    ]
    t0 = time.time()
    try:
        resp = client.models.generate_content(
            model=MODEL, contents=parts)
        raw = resp.text or ""
        ms = int((time.time() - t0) * 1000)
    except Exception as e:  # noqa: BLE001
        return {"raw": "", "parsed": None,
                "ms": int((time.time() - t0) * 1000),
                "error": str(e)[:300]}

    parsed = parse_json(raw)
    return {"raw": raw, "parsed": parsed, "ms": ms, "error": None}


_FENCE_RE = None


def parse_json(s: str):
    """Strip ``` fences, parse JSON, tolerate trailing prose."""
    import re as _re
    s = s.strip()
    s = _re.sub(r"^```(?:json)?\s*", "", s)
    s = _re.sub(r"\s*```$", "", s)
    s = s.strip()
    # Try to grab the first {...} block
    m = _re.search(r"\{.*\}", s, flags=_re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


# ───────────────── grading ─────────────────

def grade_field(truth, pred) -> str:
    if truth is None or truth == "" or truth == "unknown":
        return "na"
    if pred is None or pred == "" or pred == "—":
        return "miss"
    if pred == "unknown":
        return "unk"
    if str(truth).lower() == str(pred).lower():
        return "match"
    return "miss"


# ───────────────── runner ─────────────────

def main():
    if not FIXTURE.exists():
        sys.exit(f"missing fixture {FIXTURE}")
    fixture = json.loads(FIXTURE.read_text())
    truth_by_wid = {lbl["window_id"]: (lbl.get("truth") or {})
                    for lbl in fixture["labels"]}

    OUT.mkdir(parents=True, exist_ok=True)
    print(f"loading client...")
    client, types = make_client()
    print(f"running on {len(ALL_CLIPS)} clips, 4 calls each "
          f"(FULL, MIN, BOWLING, BATTING)")

    results = []
    for clip in ALL_CLIPS:
        wid = clip["window_id"]
        mp4 = WIN_ROOT / f"window_{wid:04d}" / "delivery_window.mp4"
        if not mp4.exists():
            print(f"  [w{wid:04d}] missing mp4, skipping")
            continue
        data = mp4.read_bytes()
        truth = truth_by_wid.get(wid, {})
        print(f"\n[w{wid:04d}] {clip['label']}")
        print(f"  mp4: {len(data)/1024:.0f} KB, truth fields: "
              f"{sum(1 for v in truth.values() if v)}")

        per_clip = {
            "window_id": wid,
            "label": clip["label"],
            "mp4_bytes": len(data),
            "truth": truth,
            "calls": {},
        }

        for variant, prompt in [("FULL", PROMPT_FULL),
                                ("MIN", PROMPT_MIN),
                                ("BOWLING", PROMPT_BOWLING),
                                ("BATTING", PROMPT_BATTING)]:
            print(f"  → {variant} ...", end="", flush=True)
            r = call_gemini(client, types, data, prompt)
            err = (f" ERROR: {r['error'][:80]}"
                   if r["error"] else "")
            preview = (json.dumps(r["parsed"])[:120]
                       if r["parsed"] else "(unparseable)")
            print(f" {r['ms']} ms{err}\n      {preview}")
            per_clip["calls"][variant] = r

        results.append(per_clip)

    out_json = OUT / "results.json"
    out_json.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nWrote {out_json}")

    md = render_report(results)
    out_md = OUT / "report.md"
    out_md.write_text(md)
    print(f"Wrote {out_md}\n")
    print(md)


# ───────────────── report ─────────────────

# Field → which variant(s) ask for it
FIELD_VARIANTS = {
    "length":          ["FULL", "MIN", "BOWLING"],
    "line":            ["FULL", "BOWLING"],
    "bowling_angle":   ["FULL", "BOWLING"],
    "bounce":          ["FULL", "BOWLING"],
    "shot_type":       ["FULL", "MIN", "BATTING"],
    "shot_side":       ["FULL", "BATTING"],
    "elevation":       ["FULL", "BATTING"],
    "contact_quality": ["FULL", "BATTING"],
}


def render_report(results: list[dict]) -> str:
    """Build a markdown report comparing the 4 prompt variants."""
    out = ["# Gemini A/B schema test — report\n",
           f"Model: `{MODEL}`",
           f"Clips: {len(results)} total "
           f"({sum(1 for r in results if r['truth'])} graded)\n",
           ""]

    # Per-field accuracy (graded clips only)
    graded = [r for r in results if r["truth"]]
    out.append("## Per-field accuracy on graded clips "
               f"(n={len(graded)})\n")
    out.append("| field | FULL | MIN | BOWLING | BATTING | "
               "(n=graded clips with that variant)|")
    out.append("|---|---|---|---|---|---|")
    for field, variants in FIELD_VARIANTS.items():
        cells = []
        for v in ["FULL", "MIN", "BOWLING", "BATTING"]:
            if v not in variants:
                cells.append("—")
                continue
            n_match = n_total = 0
            for r in graded:
                truth_v = (r["truth"] or {}).get(field)
                pred_v = ((r["calls"].get(v) or {})
                          .get("parsed") or {}).get(field)
                g = grade_field(truth_v, pred_v)
                if g in ("match", "miss"):
                    n_total += 1
                    if g == "match":
                        n_match += 1
            cells.append(f"{n_match}/{n_total}" if n_total
                         else "—")
        out.append(f"| {field} | " + " | ".join(cells) + " | |")

    # Aggregate accuracy across the fields each variant covers
    out.append("\n## Aggregate accuracy per variant (graded clips)\n")
    out.append("| variant | matched / graded | accuracy |")
    out.append("|---|---|---|")
    for v in ["FULL", "MIN", "BOWLING", "BATTING"]:
        n_match = n_total = 0
        for r in graded:
            for field, variants in FIELD_VARIANTS.items():
                if v not in variants:
                    continue
                truth_v = (r["truth"] or {}).get(field)
                pred_v = ((r["calls"].get(v) or {})
                          .get("parsed") or {}).get(field)
                g = grade_field(truth_v, pred_v)
                if g in ("match", "miss"):
                    n_total += 1
                    if g == "match":
                        n_match += 1
        pct = (f"{100*n_match/n_total:.0f}%" if n_total else "—")
        out.append(f"| {v} | {n_match}/{n_total} | {pct} |")

    # Modal-tuple analysis on length / shot_type across ALL clips
    out.append(
        "\n## Modal collapse — distribution of length / shot_type "
        "across all clips\n")
    out.append("If a variant returns the SAME value for most clips, "
               "that's the prior-pull pattern.  Real cricket has variance.")
    out.append("")
    out.append("| variant | field | distribution (count of each value) |")
    out.append("|---|---|---|")
    for v in ["FULL", "MIN", "BOWLING", "BATTING"]:
        for field in ["length", "shot_type"]:
            if v not in FIELD_VARIANTS.get(field, []):
                continue
            vals = []
            for r in results:
                pred_v = ((r["calls"].get(v) or {})
                          .get("parsed") or {}).get(field)
                if pred_v is not None:
                    vals.append(pred_v)
            ctr = Counter(vals)
            dist = ", ".join(f"`{k}`×{n}"
                             for k, n in ctr.most_common())
            out.append(f"| {v} | {field} | {dist} |")

    # Per-clip per-variant table for the GRADED clips
    out.append("\n## Per-clip detail (graded clips)\n")
    for r in graded:
        out.append(
            f"### Window #{r['window_id']} — {r['label']}\n")
        out.append("| field | truth | FULL | MIN | BOWLING | BATTING |")
        out.append("|---|---|---|---|---|---|")
        for field in ["length", "line", "bowling_angle", "bounce",
                      "shot_type", "shot_side", "elevation",
                      "contact_quality"]:
            row = [field, str(r["truth"].get(field) or "—")]
            for v in ["FULL", "MIN", "BOWLING", "BATTING"]:
                if v not in FIELD_VARIANTS.get(field, []):
                    row.append("—")
                else:
                    pv = ((r["calls"].get(v) or {})
                          .get("parsed") or {}).get(field)
                    truth_v = r["truth"].get(field)
                    g = grade_field(truth_v, pv)
                    marker = ({"match": "✓", "miss": "✗",
                               "unk": "?", "na": ""}).get(g, "")
                    row.append(f"{pv or '—'} {marker}".strip())
            out.append("| " + " | ".join(row) + " |")
        out.append("")

    # Latency
    out.append("## Latency per call (ms)\n")
    out.append("| window | FULL | MIN | BOWLING | BATTING | total split |")
    out.append("|---|---|---|---|---|---|")
    for r in results:
        cells = [f"#{r['window_id']}"]
        for v in ["FULL", "MIN", "BOWLING", "BATTING"]:
            ms = (r["calls"].get(v) or {}).get("ms", "—")
            cells.append(str(ms))
        b = (r["calls"].get("BOWLING") or {}).get("ms", 0) or 0
        ba = (r["calls"].get("BATTING") or {}).get("ms", 0) or 0
        cells.append(str(b + ba))
        out.append("| " + " | ".join(cells) + " |")

    return "\n".join(out)


if __name__ == "__main__":
    main()
