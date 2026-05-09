#!/usr/bin/env python3
"""Cluster-QA: validate detect_delivery_zones blocks via Groq llama-3.3-70b-versatile.

Read-only experiment. Re-annotates the 300 frames using current rules,
builds a per-block payload (sampled descriptions + aggregate signals/paths),
asks the reasoning model to classify each cluster, writes a comparison
report. Does not modify any rule code.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from detect_delivery_zones import annotate, Frame  # noqa: E402

OUT_DIR = REPO_ROOT / "files/scripts/broadcast_mode_tuning"
SCOUT_DIR = OUT_DIR / "first_5min_scout_run"
RESULTS_JSON = OUT_DIR / "cluster_qa_results.json"
RESULTS_MD = OUT_DIR / "cluster_qa_report.md"

FPS = 25.0
N_FRAMES = 7500

BLOCKS = [
    (101.0, 110.0),
    (122.0, 147.0),
    (161.0, 164.0),
    (176.0, 179.0),
    (182.0, 197.0),
    (234.0, 244.0),
    (272.0, 278.0),
]

MODEL = "llama-3.3-70b-versatile"
GROQ_KEY = os.environ.get(
    "GROQ_API_KEY",
    os.environ["GROQ_API_KEY"],
)

SYSTEM = (
    "You are analyzing 1fps frame descriptions from a live cricket "
    "broadcast. A LIVE DELIVERY shows the bowler's-end camera: the pitch "
    "extends away from the camera toward the far stumps, with the bowler "
    "in foreground and batter at the far crease. This is the ONLY camera "
    "angle from which a legal ball is bowled. A live broadcast also shows "
    "a numerical score strip with over count and batter runs (e.g. "
    "'47-3 (5.2)'), NOT just team branding like 'TATA IPL' or 'Capitals "
    "vs Super Kings'. A REPLAY shows similar bowler's-end framing but "
    "with REPLAY/SLOW-MOTION badges, slow-mo motion blur, or recap "
    "context. A single delivery typically lasts 4-8 seconds of broadcast "
    "time before cutting to closeups or replays.\n\n"
    "EXAMPLE: a 4-second cluster where descriptions read 'bowler running "
    "in toward the wicket, batter taking guard at the far crease, score "
    "strip shows DC 0-0 (0.0)' is a DELIVERY. Cite the frame timestamp "
    "showing the clearest bowler's-end framing as your evidence."
)


def read_text(path: Path) -> str:
    raw = path.read_text()
    if "---\n" in raw:
        return raw.split("---\n", 1)[1].strip()
    return raw.strip()


def load_frames() -> list[Frame]:
    frames: list[Frame] = []
    for i in range(0, N_FRAMES, 25):
        rel_t = i / FPS
        stem = f"f_{i:05d}_t={rel_t:06.2f}"
        path = SCOUT_DIR / f"{stem}.txt"
        if not path.exists():
            continue
        f = Frame(ts=rel_t, rel_t=rel_t, text=read_text(path))
        annotate(f)
        frames.append(f)
    return frames


def _signal_count(f: Frame) -> int:
    return (int(f.has_action_verb) + int(f.has_strong_score)
            + int(f.has_multi_actor) + int(f.has_wide_field)
            + int(f.has_weak_info))


def signal_richest_sample(items: list[Frame], top_k: int = 2) -> list[Frame]:
    """First + last + top-k signal-richest frames, deduped, time-sorted."""
    if not items:
        return []
    chosen: dict[float, Frame] = {items[0].rel_t: items[0],
                                  items[-1].rel_t: items[-1]}
    middle = items[1:-1] if len(items) >= 2 else []
    middle_sorted = sorted(middle, key=_signal_count, reverse=True)
    for f in middle_sorted[:top_k]:
        chosen.setdefault(f.rel_t, f)
    return [chosen[t] for t in sorted(chosen)]


def build_payload(block_id: int, start: float, end: float,
                  all_frames: list[Frame]) -> dict:
    in_block = [f for f in all_frames if start <= f.rel_t <= end]
    sampled = signal_richest_sample(in_block)
    signal_summary = {
        "V": sum(1 for f in in_block if f.has_action_verb),
        "S": sum(1 for f in in_block if f.has_strong_score),
        "M": sum(1 for f in in_block if f.has_multi_actor),
        "W": sum(1 for f in in_block if f.has_wide_field),
        "K": sum(1 for f in in_block if f.has_weak_info),
    }
    path_summary = {"A": 0, "B": 0, "C": 0, "none": 0}
    for f in in_block:
        path_summary[f.path] = path_summary.get(f.path, 0) + 1
    return {
        "block_id": block_id,
        "start_t": start,
        "end_t": end,
        "duration_s": end - start,
        "frame_count": len(in_block),
        "signal_summary": signal_summary,
        "path_summary": path_summary,
        "sampled_frames": [
            {
                "t": f.rel_t,
                "open_description": f.text,
                "signals": {
                    "V": int(f.has_action_verb),
                    "S": int(f.has_strong_score),
                    "M": int(f.has_multi_actor),
                    "W": int(f.has_wide_field),
                    "K": int(f.has_weak_info),
                },
            }
            for f in sampled
        ],
    }


def build_user_prompt(p: dict) -> str:
    lines = [
        f"Cluster {p['block_id']}: {p['start_t']}s -> {p['end_t']}s "
        f"({p['duration_s']}s, {p['frame_count']} frames).",
        f"Aggregate signals: {json.dumps(p['signal_summary'])}, "
        f"paths: {json.dumps(p['path_summary'])}.",
        "Sampled frame descriptions:",
    ]
    for f in p["sampled_frames"]:
        lines.append(f"[t={f['t']}] {f['open_description']}")
    lines.extend([
        "",
        "Identify the single frame timestamp in this cluster with the "
        "strongest live-delivery evidence (bowler's-end framing, "
        "follow-through, ball release). If no frame shows live delivery "
        "framing, set evidence_frame_t to null.",
        "",
        "Classify this cluster. If multiple distinct deliveries appear "
        "bridged (typical when duration > 12s), return MULTI_DELIVERY "
        "with split timestamps.",
        "",
        "Output JSON only:",
        "{",
        '  "label": "DELIVERY" | "MULTI_DELIVERY" | "REPLAY" | '
        '"PRE_MATCH" | "NON_LIVE" | "UNCERTAIN",',
        '  "split_at_seconds": [t1, t2, ...] or [],',
        '  "confidence": 0.0-1.0,',
        '  "evidence_frame_t": float | null,',
        '  "reason": "1-2 sentences citing visual evidence"',
        "}",
    ])
    return "\n".join(lines)


def call_groq(client, payload: dict) -> tuple[dict | None, str | None]:
    user = build_user_prompt(payload)
    last_err = None
    for attempt in range(2):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                temperature=0,
                max_tokens=400,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user},
                ],
            )
            text = resp.choices[0].message.content or "{}"
            return json.loads(text), None
        except Exception as e:  # noqa: BLE001
            last_err = repr(e)
            time.sleep(1.5)
    return None, last_err


def truth_overlap(start: float, end: float, lo: float, hi: float) -> bool:
    return start <= hi and end >= lo


def main() -> int:
    from groq import Groq
    client = Groq(api_key=GROQ_KEY, timeout=20.0)
    frames = load_frames()
    print(f"Loaded {len(frames)} frames")

    results = []
    t0 = time.time()
    for i, (start, end) in enumerate(BLOCKS, 1):
        payload = build_payload(i, start, end, frames)
        verdict, err = call_groq(client, payload)
        results.append({
            "block_id": i,
            "payload": payload,
            "verdict": verdict,
            "error": err,
        })
        label = verdict.get("label") if verdict else f"ERROR({err})"
        print(f"Block {i} ({start}-{end}s): {label}")
    dt = time.time() - t0
    print(f"Wall: {dt:.1f}s")

    RESULTS_JSON.write_text(json.dumps(results, indent=2))

    # Aggregation gate: keep DELIVERY clusters with sufficient confidence
    # AND an evidence_frame_t inside the cluster window.
    def passes_gate(r: dict) -> tuple[bool, str]:
        v = r.get("verdict")
        if v is None:
            return False, "no-verdict"
        if v.get("label") != "DELIVERY":
            return False, f"label={v.get('label')}"
        conf = v.get("confidence")
        if conf is None or conf < 0.6:
            return False, f"conf={conf}"
        ev = v.get("evidence_frame_t")
        if ev is None:
            return False, "evidence-null"
        p = r["payload"]
        if not (p["start_t"] <= ev <= p["end_t"]):
            return False, f"evidence-out-of-range({ev})"
        return True, "kept"

    for r in results:
        ok, why = passes_gate(r)
        r["gate_kept"] = ok
        r["gate_reason"] = why

    delivery_results = [r for r in results
                        if r.get("verdict") and r["verdict"].get("label") == "DELIVERY"]
    in_range = [r for r in delivery_results
                if r["verdict"].get("evidence_frame_t") is not None
                and r["payload"]["start_t"]
                <= r["verdict"]["evidence_frame_t"]
                <= r["payload"]["end_t"]]
    in_range_pct = (100.0 * len(in_range) / len(delivery_results)
                    if delivery_results else 0.0)

    lines = [
        "# Cluster QA report",
        "",
        f"Model: `{MODEL}` · {len(BLOCKS)} blocks · wall time {dt:.1f}s.",
        "",
        "Detection verdict for every block is DELIVERY (these are the "
        "blocks emitted by `detect_delivery_zones.detect_blocks`).",
        "",
        "## Summary table",
        "",
        "| Block | Range | Reasoner | Conf | Evidence t | Splits | Gate |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        p = r["payload"]
        v = r["verdict"] or {}
        ev = v.get("evidence_frame_t")
        ev_str = f"{ev:.1f}" if isinstance(ev, (int, float)) else "null"
        gate = "KEEP" if r.get("gate_kept") else f"DROP ({r.get('gate_reason')})"
        splits = v.get("split_at_seconds") or []
        splits_str = ",".join(f"{s:.1f}" for s in splits) if splits else "-"
        lines.append(
            f"| {r['block_id']} | "
            f"{p['start_t']:.0f}-{p['end_t']:.0f}s ({p['duration_s']:.0f}s) | "
            f"`{v.get('label', 'ERROR')}` | "
            f"{v.get('confidence', '-')} | "
            f"{ev_str} | {splits_str} | {gate} |"
        )
    lines.extend([
        "",
        f"**Evidence-in-range sanity**: "
        f"{len(in_range)}/{len(delivery_results)} DELIVERY-labeled "
        f"clusters have `evidence_frame_t` inside their window "
        f"({in_range_pct:.0f}%). Should be 100%; deviations indicate "
        f"hallucinated timestamps.",
        "",
    ])

    for r in results:
        p = r["payload"]
        v = r["verdict"]
        lines.append(
            f"## Block {r['block_id']}: t={p['start_t']:.0f}-"
            f"{p['end_t']:.0f}s ({p['duration_s']:.0f}s, "
            f"{p['frame_count']} frames)"
        )
        lines.append("")
        if v is None:
            lines.append(f"- **Reasoner**: ERROR — `{r['error']}`")
            lines.append("")
            continue
        lines.append(
            f"- **Reasoner**: `{v.get('label')}` "
            f"(confidence {v.get('confidence')})"
        )
        ev = v.get("evidence_frame_t")
        if ev is not None:
            in_win = p["start_t"] <= ev <= p["end_t"]
            tag = "" if in_win else " ⚠ OUT OF RANGE"
            lines.append(f"- Evidence frame: t={ev:.1f}s{tag}")
        else:
            lines.append("- Evidence frame: null")
        splits = v.get("split_at_seconds") or []
        if splits:
            lines.append(f"- **Splits**: {splits}")
        lines.append(f"- Aggregate signals: `{p['signal_summary']}`")
        lines.append(f"- Path attribution: `{p['path_summary']}`")
        lines.append(f"- Gate: **{('KEEP' if r.get('gate_kept') else 'DROP')}** "
                     f"({r.get('gate_reason')})")
        lines.append(f"- Reason: {v.get('reason')}")
        lines.append("")

    lines.append("## Disagreement highlights")
    lines.append("")
    b2 = next(r for r in results if r["block_id"] == 2)
    if b2["verdict"]:
        lab = b2["verdict"].get("label")
        sp = b2["verdict"].get("split_at_seconds") or []
        if lab == "MULTI_DELIVERY":
            keeps_2nd = any(122.0 <= s <= 134.0 for s in sp)
            lines.append(
                f"- **Block 2 (25 s)** flagged `MULTI_DELIVERY` with splits "
                f"{sp}. Splits in 122–134 region (preserves 2nd delivery): "
                f"{'YES' if keeps_2nd else 'NO'}."
            )
        else:
            lines.append(
                f"- **Block 2 (25 s)** classified `{lab}` — model did NOT "
                f"detect the bridged-deliveries case despite duration > 12 s."
            )
    lines.append("")

    for bid in (3, 4):
        rb = next(r for r in results if r["block_id"] == bid)
        if rb["verdict"]:
            lab = rb["verdict"].get("label")
            lines.append(
                f"- **Block {bid} (3 s)** classified `{lab}`."
            )
    lines.append("")

    lines.append("## Truth check")
    lines.append("")
    truth_windows = [("1st delivery", 100.0, 115.0),
                     ("2nd delivery", 122.0, 128.0)]
    for name, lo, hi in truth_windows:
        for r in results:
            p = r["payload"]
            if truth_overlap(p["start_t"], p["end_t"], lo, hi):
                v = r["verdict"]
                lab = v.get("label") if v else "?"
                splits = (v.get("split_at_seconds") if v else []) or []
                lines.append(
                    f"- **{name}** ({lo:.0f}-{hi:.0f}s) covered by Block "
                    f"{r['block_id']} ({p['start_t']:.0f}-"
                    f"{p['end_t']:.0f}s) → reasoner `{lab}` splits={splits}"
                )
                break

    RESULTS_MD.write_text("\n".join(lines) + "\n")
    print(f"Wrote {RESULTS_JSON} and {RESULTS_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
