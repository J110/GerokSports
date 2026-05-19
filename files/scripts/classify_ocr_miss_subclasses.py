#!/usr/bin/env python3
"""Stage 3a: raw-VLM sub-classification of the 12 ocr_miss events
from the stage-3 classifier output.

For each ocr_miss event, walk the session trace around the gap-end
frame, extract VLM-side signals (frame_type classification, raw_text
first 120 chars), and sub-classify into:

  (a) genuine_non_scoreboard — VLM correctly tagged non-SCOREBOARD;
      strip not visible in those frames
  (b) classifier_misclassify — VLM tagged SCOREBOARD but raw_text
      contains graphic/replay markers (no STRIP: prefix or strip
      degenerate)
  (c) vlm_extraction_failure — VLM tagged SCOREBOARD, STRIP: line
      present, but content unparseable (null-team / null-overs /
      degenerate digits)
  (d) other_mixed — doesn't cleanly fit the above

Reports distribution + per-event annotations + per-class fix shape.

No code edits — pure investigation.
"""
from __future__ import annotations

import collections
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
TRACE_DIR = ROOT / "logs" / "trace"
DELIVERIES_DIR = ROOT / "files" / "logs" / "deliveries"
CLASSIFICATION_PATH = pathlib.Path(
    "/tmp/steady_state_gap_classification.jsonl")
OUT_PATH = pathlib.Path("/tmp/ocr_miss_subclass.jsonl")


# Markers that indicate the raw_text shows non-scoreboard content
# even when VLM tagged SCOREBOARD.
GRAPHIC_MARKERS = (
    "graphic", "replay", "overlay", "advertisement",
    "intro", "outro", "team logo", "transition",
    "presenter", "studio", "highlight",
)
SCOREBOARD_MISC_MARKERS = (
    "drs", "third umpire", "review",
    "powerplay", "innings break", "strategic",
)


def has_strip_prefix(s: str) -> bool:
    if not s:
        return False
    return bool(re.search(r"\bSTRIP\s*:", s, re.IGNORECASE))


def extract_strip_text(s: str) -> str:
    if not s:
        return ""
    m = re.search(r"STRIP\s*:\s*([^\n|]+)", s, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def strip_is_degenerate(s: str) -> bool:
    if not s:
        return True
    t = s.strip().lower()
    if t in ("null", "none", ""):
        return True
    if t.count("null") >= 2:
        return True
    if not re.search(r"\d", t):
        return True
    return False


def has_graphic_marker(s: str) -> bool:
    if not s:
        return False
    low = s.lower()
    return any(m in low for m in GRAPHIC_MARKERS)


def load_trace(session: str) -> list[dict]:
    p = TRACE_DIR / f"{session}.jsonl"
    if not p.exists():
        return []
    out = []
    with p.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("frame") is None:
                continue
            out.append(rec)
    return out


def load_raw_responses(session: str) -> dict[int, str]:
    p = DELIVERIES_DIR / session / "scout_raw.jsonl"
    if not p.exists():
        return {}
    out = {}
    with p.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                fid = int(rec.get("frame_id", -1))
                out[fid] = rec.get("raw_response", "") or ""
            except (json.JSONDecodeError, ValueError):
                continue
    return out


def collect_window_frames(
    trace: list[dict], gap_end_frame: int,
    prev_legal: int, curr_legal: int,
) -> list[dict]:
    end_idx = None
    for i, rec in enumerate(trace):
        if int(rec.get("frame", -1)) == gap_end_frame:
            end_idx = i
            break
    if end_idx is None:
        return []
    # Walk backwards to find prev commit
    start_idx = 0
    for j in range(end_idx - 1, -1, -1):
        ext = (trace[j].get("extractor") or {})
        v = ext.get("match_overs")
        if v is not None:
            try:
                f = float(v)
                legal = int(f) * 6 + round((f - int(f)) * 10)
            except (TypeError, ValueError):
                legal = None
            if legal == prev_legal:
                start_idx = j
                break
    return trace[start_idx + 1: end_idx]


def subclassify(window: list[dict],
                raw_by_frame: dict[int, str]) -> dict:
    n = len(window)
    if n == 0:
        return {"subclass": "no_window_frames", "n": 0}

    # Per-frame mini-analysis
    per_frame = []
    counts = collections.Counter()
    for rec in window:
        fid = int(rec.get("frame", -1))
        ft = rec.get("frame_type") or "UNKNOWN"
        scout = rec.get("scout") or {}
        raw120 = scout.get("raw_text_120") or ""
        full_raw = raw_by_frame.get(fid, "")
        text_for_analysis = full_raw if full_raw else raw120
        has_strip = has_strip_prefix(text_for_analysis)
        strip = extract_strip_text(text_for_analysis)
        degen = strip_is_degenerate(strip)
        graphic = has_graphic_marker(text_for_analysis)
        if ft != "SCOREBOARD":
            counts["non_scoreboard_tag"] += 1
            tag = "non_scoreboard"
        elif graphic and (not has_strip or degen):
            counts["sb_tag_graphic_content"] += 1
            tag = "sb_tag_but_graphic"
        elif has_strip and degen:
            counts["sb_strip_degenerate"] += 1
            tag = "sb_strip_degenerate"
        elif has_strip and not degen:
            counts["sb_strip_readable_but_overs_null"] += 1
            tag = "sb_strip_readable_no_overs"
        else:
            counts["sb_no_strip"] += 1
            tag = "sb_no_strip"
        per_frame.append({
            "frame": fid, "frame_type": ft, "tag": tag,
            "has_strip_prefix": has_strip,
            "strip_text_preview": strip[:80],
            "raw120": raw120[:120],
        })

    # Aggregate sub-class
    if counts.get("non_scoreboard_tag", 0) >= n // 2:
        subclass = "(a) genuine_non_scoreboard"
    elif counts.get("sb_tag_graphic_content", 0) >= 1:
        subclass = "(b) classifier_misclassify"
    elif counts.get("sb_strip_degenerate", 0) >= n // 2:
        subclass = "(c) vlm_extraction_failure_degenerate"
    elif counts.get("sb_strip_readable_but_overs_null", 0) >= n // 2:
        subclass = "(c) vlm_extraction_failure_strip_readable"
    elif counts.get("sb_no_strip", 0) >= n // 2:
        subclass = "(c) vlm_extraction_failure_no_strip"
    else:
        subclass = "(d) mixed"

    return {
        "subclass": subclass,
        "n": n,
        "per_frame_counts": dict(counts),
        "sample_frames": per_frame[:5],
    }


def main():
    with CLASSIFICATION_PATH.open() as fh:
        all_results = [json.loads(l) for l in fh if l.strip()]
    ocr_miss = [
        r for r in all_results
        if r["classification"]["class"] == "ocr_miss"
    ]
    print(f"ocr_miss events to sub-classify: {len(ocr_miss)}")
    print()

    output = []
    for r in ocr_miss:
        session = r["session"]
        trace = load_trace(session)
        raw_by_frame = load_raw_responses(session)
        window = collect_window_frames(
            trace, r["gap_end_frame"],
            prev_legal=int(r["prev_overs"].split(".")[0]) * 6
                       + int(r["prev_overs"].split(".")[1]),
            curr_legal=int(r["new_overs"].split(".")[0]) * 6
                        + int(r["new_overs"].split(".")[1]),
        )
        sc = subclassify(window, raw_by_frame)
        result = {
            "session": session,
            "gap_end_frame": r["gap_end_frame"],
            "delta": r["delta"],
            "prev_overs": r["prev_overs"],
            "new_overs": r["new_overs"],
            "raw_available": bool(raw_by_frame),
            "subclassification": sc,
        }
        output.append(result)

    # Aggregate
    by_subclass = collections.Counter(
        r["subclassification"]["subclass"] for r in output)
    print("=" * 70)
    print(f"OCR_MISS SUB-CLASSIFICATION (n={len(output)})")
    print("=" * 70)
    print(f"raw scout_raw.jsonl available for "
          f"{sum(1 for r in output if r['raw_available'])} "
          f"of {len(output)} sessions")
    print()
    print(f"{'Subclass':<55} {'Count':>5} {'%':>6}")
    print("-" * 70)
    total = len(output) or 1
    for sub, c in by_subclass.most_common():
        print(f"{sub:<55} {c:>5} {100*c/total:>5.1f}%")
    print()

    # Per-class samples
    print("=" * 70)
    print("PER-SUBCLASS REPRESENTATIVE SAMPLES")
    print("=" * 70)
    by_sub_samples = collections.defaultdict(list)
    for r in output:
        by_sub_samples[r["subclassification"]["subclass"]].append(r)
    for sub, samples in sorted(by_sub_samples.items()):
        print(f"\n--- {sub} ({len(samples)} cases) ---")
        for s in samples[:3]:
            sc = s["subclassification"]
            print(f"  session={s['session']:<32} "
                  f"frame={s['gap_end_frame']} "
                  f"Δ={s['delta']} "
                  f"{s['prev_overs']}→{s['new_overs']} "
                  f"window_n={sc['n']} "
                  f"raw={'yes' if s['raw_available'] else 'no'}")
            print(f"    counts: {sc['per_frame_counts']}")
            for sf in sc["sample_frames"][:3]:
                print(f"    frame={sf['frame']:>4} "
                      f"type={sf['frame_type']:<11} "
                      f"tag={sf['tag']:<28} "
                      f"strip={sf['strip_text_preview']!r}")

    # Diagnosis + fix shape per dominant sub-class
    print()
    print("=" * 70)
    print("FIX-SHAPE PROPOSALS PER SUB-CLASS")
    print("=" * 70)
    for sub, c in by_subclass.most_common():
        pct = 100 * c / total
        print(f"\n{sub}  ({c}/{total}, {pct:.0f}%)")
        if sub.startswith("(a)"):
            print(
                "  Fix shape: structurally unfixable at current Scout\n"
                "  cadence/quality — strip genuinely not visible in those\n"
                "  windows. Frame Fate Ledger documents the rate; we\n"
                "  accept a small irreducible class and revisit only if\n"
                "  the rate climbs.")
        elif sub.startswith("(b)"):
            print(
                "  Fix shape: Scout VLM prompt or post-classification\n"
                "  filter. The VLM is calling a graphic/replay frame a\n"
                "  SCOREBOARD. Either tighten the VLM prompt's\n"
                "  SCOREBOARD criteria, OR add a post-VLM check: if\n"
                "  raw_text contains graphic markers AND no STRIP:\n"
                "  prefix, downgrade to non-SCOREBOARD. Touches\n"
                "  files/eyes/vision.py (VLM prompt) or\n"
                "  files/eyes/extract_regex.py (post-classify filter).")
        elif "vlm_extraction_failure" in sub:
            print(
                "  Fix shape: Scout VLM is seeing the scoreboard but\n"
                "  the STRIP extraction is degenerate (null tokens) or\n"
                "  missing entirely. Tighten the VLM prompt to demand a\n"
                "  literal STRIP line with score/overs always populated\n"
                "  when scoreboard is in frame. Touches\n"
                "  files/eyes/vision.py prompt template.")
        else:
            print(
                "  Fix shape: mixed signals — pull individual cases\n"
                "  and triage; may indicate a new failure mode.")

    OUT_PATH.write_text(
        "\n".join(json.dumps(r, default=str) for r in output))
    print()
    print(f"per-event detail at {OUT_PATH}")


if __name__ == "__main__":
    main()
