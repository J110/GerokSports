#!/usr/bin/env python3
"""Cluster-level QA: signal-driven clusters classified by Groq llama-3.3-70b-versatile.

Builds clusters from contiguous has_signal frames (NOT Path A/B/C, NOT
iter7 merge), classifies each cluster with a revised rubric that drops
the score-strip requirement, gates by label/confidence/evidence-in-range,
merges adjacent kept clusters within 8s, drops blocks under 2s.
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
RESULTS_JSON = OUT_DIR / "cluster_level_qa_results.json"
RESULTS_MD = OUT_DIR / "cluster_level_qa_report.md"
PROSE_TXT = OUT_DIR / "cluster_level_qa_prose.txt"

FPS = 25.0
N_FRAMES = 7500

CLUSTER_GAP_MAX = 2
CLUSTER_MIN_RUN = 1

GATE_CONF = 0.6
MERGE_GAP_S = 8.0
MIN_BLOCK_S = 2.0

API_CAP = 30

TRUTH_WINDOWS = [
    ("1st delivery", 100.0, 115.0),
    ("2nd delivery", 122.0, 128.0),
]

MODEL = "llama-3.3-70b-versatile"
GROQ_KEY = os.environ.get(
    "GROQ_API_KEY",
    os.environ["GROQ_API_KEY"],
)

SYSTEM = (
    "You analyze 1fps frame descriptions from a cricket broadcast to "
    "classify a single short broadcast moment (typically 3-7 seconds).\n\n"
    "The defining signal of a LIVE DELIVERY is the bowler's-end camera "
    "shot: pitch extends away from camera toward far stumps, bowler in "
    "the foreground (running in, in delivery stride, or following "
    "through), batter at the far crease. This is the ONLY camera angle "
    "from which a legal ball is bowled. If the frame descriptions "
    "include this framing, it is a DELIVERY regardless of what "
    "scoreboard or score strip text appears.\n\n"
    "A REPLAY shows the same framing but with REPLAY/SLOW-MOTION "
    "badges, slow-motion blur, recap context, or repeat of a wicket/"
    "boundary moment.\n\n"
    "PRE_MATCH shows presenters, anthem, toss, sponsor montages, or "
    "full-screen graphics with no bowler's-end camera at all.\n\n"
    "NON_LIVE covers between-deliveries closeups, fielder reactions, "
    "crowd shots, idle stadium framing.\n\n"
    "Score strip text content (numbers, team names, over counts) is "
    "NOT part of the DELIVERY definition. Ignore it for classification. "
    "The visual framing of the camera shot is the only test.\n\n"
    "EXAMPLE: a 4s, 4-frame cluster with description sample 'wide shot "
    "of the cricket pitch, bowler running in toward the wicket, batter "
    "standing at the far crease taking guard, umpire visible at the "
    "stumps' classifies as DELIVERY with evidence_frame_t at the frame "
    "showing the bowler in motion. Reason: bowler's-end framing with "
    "bowler in delivery stride, batter at far crease.\n\n"
    "A cluster contains a delivery if ANY single frame shows bowler's-"
    "end framing with bowler motion. The other frames in the cluster "
    "being between-deliveries shots, closeups, or breaks does NOT "
    "negate the delivery — list each live moment separately. Do not "
    "majority-vote across the cluster; enumerate evidence."
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


def has_signal(f: Frame) -> bool:
    return f.path in ("A", "B", "C")


def hard_reject(f: Frame) -> bool:
    return f.is_replay_hard or f.is_crowd_dominant or f.is_unusual_angle


def build_clusters(frames: list[Frame]) -> list[tuple[int, int]]:
    """Contiguous Path-A|B|C runs. gap_max=2 plain NOT_DELIVERY frames
    permitted inside a cluster; a hard-reject frame closes immediately
    and does not count toward the gap budget."""
    clusters: list[tuple[int, int]] = []
    n = len(frames)
    i = 0
    while i < n:
        f = frames[i]
        if hard_reject(f) or not has_signal(f):
            i += 1
            continue
        start = i
        last_sig = i
        j = i + 1
        gap = 0
        while j < n:
            fj = frames[j]
            if hard_reject(fj):
                break
            if has_signal(fj):
                last_sig = j
                gap = 0
            else:
                gap += 1
                if gap > CLUSTER_GAP_MAX:
                    break
            j += 1
        if (last_sig - start + 1) >= CLUSTER_MIN_RUN:
            clusters.append((start, last_sig))
        i = last_sig + 1
    return clusters


def _signal_count(f: Frame) -> int:
    return (int(f.has_action_verb) + int(f.has_strong_score)
            + int(f.has_multi_actor) + int(f.has_wide_field)
            + int(f.has_weak_info))


def signal_richest_sample(items: list[Frame], top_k: int = 2) -> list[Frame]:
    if not items:
        return []
    chosen: dict[float, Frame] = {items[0].rel_t: items[0],
                                  items[-1].rel_t: items[-1]}
    middle = items[1:-1] if len(items) >= 2 else []
    middle_sorted = sorted(middle, key=_signal_count, reverse=True)
    for f in middle_sorted[:top_k]:
        chosen.setdefault(f.rel_t, f)
    return [chosen[t] for t in sorted(chosen)]


def build_payload(cid: int, a: int, b: int, frames: list[Frame]) -> dict:
    in_block = frames[a:b + 1]
    sampled = signal_richest_sample(in_block)
    start_t = in_block[0].rel_t
    end_t = in_block[-1].rel_t
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
        "cluster_id": cid,
        "start_t": start_t,
        "end_t": end_t,
        "duration_s": end_t - start_t,
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
        f"Cluster {p['cluster_id']}: {p['start_t']:.1f}s -> "
        f"{p['end_t']:.1f}s ({p['duration_s']:.1f}s, "
        f"{p['frame_count']} frames).",
        f"Aggregate signals: {json.dumps(p['signal_summary'])}, "
        f"paths: {json.dumps(p['path_summary'])}.",
        "Sampled frame descriptions:",
    ]
    for f in p["sampled_frames"]:
        lines.append(f"[t={f['t']:.1f}s] {f['open_description']}")
    lines.extend([
        "",
        "Answer in two parts.",
        "",
        "PART 1 (prose): Write 3-5 plain English sentences describing "
        "what is happening in this cluster. Enumerate every frame "
        "timestamp where a live delivery is visible (bowler's-end "
        "framing with bowler motion, follow-through, ball release). "
        "Do not collapse the cluster to a single label.",
        "",
        "PART 2 (JSON): On a new line write exactly 'JSON:' and then a "
        "JSON object matching this schema. live_delivery_moments lists "
        "one entry per distinct live-delivery frame; an empty list "
        "means no live delivery in the cluster.",
        "{",
        '  "live_delivery_moments": [',
        '    {"t": float, "evidence": "one sentence quoting the frame '
        'description that shows bowler\'s-end framing or motion"}',
        "  ],",
        '  "replay_moments": [',
        '    {"t": float, "evidence": "..."}',
        "  ],",
        '  "non_live_summary": "one sentence describing what the '
        'non-delivery frames show (closeup, crowd, between-play, etc.)",',
        '  "confidence": 0.0-1.0',
        "}",
    ])
    return "\n".join(lines)


def parse_response(text: str) -> tuple[str, dict | None, str | None]:
    if "JSON:" in text:
        prose, after = text.split("JSON:", 1)
    else:
        prose, after = text, text
    lo = after.find("{")
    hi = after.rfind("}")
    if lo < 0 or hi < 0:
        return prose.strip(), None, "no-json-block"
    try:
        return prose.strip(), json.loads(after[lo:hi + 1]), None
    except json.JSONDecodeError as e:
        return prose.strip(), None, f"json-parse:{e}"


def call_groq(client, payload: dict) -> tuple[str, dict | None, str | None]:
    """Returns (prose, verdict_dict_or_None, error_or_None)."""
    user = build_user_prompt(payload)
    last_err = None
    for attempt in range(2):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                temperature=0,
                max_tokens=600,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user},
                ],
            )
            text = resp.choices[0].message.content or ""
            prose, verdict, parse_err = parse_response(text)
            if verdict is None:
                last_err = parse_err
                time.sleep(1.0)
                continue
            return prose, verdict, None
        except Exception as e:  # noqa: BLE001
            last_err = repr(e)
            time.sleep(1.0)
    return "", None, last_err


def select_clusters_for_api(clusters: list[tuple[int, int]],
                            frames: list[Frame],
                            cap: int) -> list[int]:
    """Indices to call. If <= cap, all. Else uniform sample with
    guaranteed inclusion of any cluster overlapping a truth window."""
    if len(clusters) <= cap:
        return list(range(len(clusters)))
    must = set()
    for k, (a, b) in enumerate(clusters):
        s, e = frames[a].rel_t, frames[b].rel_t
        for _, lo, hi in TRUTH_WINDOWS:
            if s <= hi and e >= lo:
                must.add(k)
    remaining = cap - len(must)
    pool = [k for k in range(len(clusters)) if k not in must]
    if remaining <= 0 or not pool:
        chosen = sorted(must)[:cap]
    else:
        step = len(pool) / remaining
        sampled = {pool[min(len(pool) - 1, int(round(i * step)))]
                   for i in range(remaining)}
        chosen = sorted(must | sampled)
    return chosen


def group_anchors(anchors: list[dict], merge_gap_s: float) -> list[dict]:
    """Each anchor is {t, evidence, cluster_id}. Adjacent anchors
    within merge_gap_s merge into one group. No duration filter —
    singletons are 1-anchor groups."""
    if not anchors:
        return []
    anchors = sorted(anchors, key=lambda m: m["t"])
    groups: list[dict] = []
    cur = {
        "earliest": anchors[0]["t"],
        "latest": anchors[0]["t"],
        "anchors": [anchors[0]],
    }
    for a in anchors[1:]:
        if a["t"] - cur["latest"] <= merge_gap_s:
            cur["latest"] = a["t"]
            cur["anchors"].append(a)
        else:
            groups.append(cur)
            cur = {"earliest": a["t"], "latest": a["t"], "anchors": [a]}
    groups.append(cur)
    return groups


def main() -> int:
    from groq import Groq
    frames = load_frames()
    print(f"Loaded {len(frames)} frames")

    clusters = build_clusters(frames)
    print(f"Built {len(clusters)} clusters "
          f"(gap_max={CLUSTER_GAP_MAX}, min_run={CLUSTER_MIN_RUN}, "
          f"predicate=path∈{{A,B,C}})")
    print("All clusters:")
    for k, (a, b) in enumerate(clusters):
        s, e = frames[a].rel_t, frames[b].rel_t
        print(f"  #{k + 1}: {s:.1f}-{e:.1f}s ({e - s:.1f}s, {b - a + 1} frames)")

    if len(clusters) < 5:
        sys.exit(f"ERROR: {len(clusters)} clusters < 5 — predicate too "
                 "loose. Aborting before API.")
    if len(clusters) > 25:
        sys.exit(f"ERROR: {len(clusters)} clusters > 25 — predicate too "
                 "tight. Aborting before API.")
    longest_idx = max(range(len(clusters)),
                      key=lambda k: frames[clusters[k][1]].rel_t
                      - frames[clusters[k][0]].rel_t)
    longest_dur = (frames[clusters[longest_idx][1]].rel_t
                   - frames[clusters[longest_idx][0]].rel_t)
    if longest_dur > 10.0:
        a, b = clusters[longest_idx]
        sys.exit(f"ERROR: longest cluster {longest_dur:.1f}s "
                 f"({frames[a].rel_t:.1f}-{frames[b].rel_t:.1f}s) > 10s "
                 "— still bridging. Aborting before API.")

    # Verify-gate truth-window expectations
    def cluster_at(target_lo: float, target_hi: float) -> list[tuple[int, float, float]]:
        return [(k + 1, frames[a].rel_t, frames[b].rel_t)
                for k, (a, b) in enumerate(clusters)
                if frames[a].rel_t <= target_hi and frames[b].rel_t >= target_lo]

    print("Verify-gate checks:")
    for name, lo, hi in TRUTH_WINDOWS:
        hits = cluster_at(lo, hi)
        spans = ", ".join(f"#{cid} ({s:.1f}-{e:.1f}s)" for cid, s, e in hits)
        print(f"  {name} ({lo:.0f}-{hi:.0f}s): {spans or '(none)'}")
    t134 = cluster_at(134.0, 134.0)
    print(f"  t=134 isolation check: {t134 or '(none)'}")

    client = Groq(api_key=GROQ_KEY, timeout=20.0)

    def call_one(k: int, idx: int, total: int) -> dict:
        a, b = clusters[k]
        payload = build_payload(k + 1, a, b, frames)
        prose, verdict, err = call_groq(client, payload)
        moments = (verdict or {}).get("live_delivery_moments") or []
        replays = (verdict or {}).get("replay_moments") or []
        print(f"  [{idx}/{total}] cluster {k + 1} "
              f"({payload['start_t']:.1f}-{payload['end_t']:.1f}s) "
              f"-> {len(moments)} live, {len(replays)} replay "
              f"(conf {verdict.get('confidence') if verdict else '-'})")
        return {
            "cluster_id": k + 1,
            "payload": payload,
            "prose": prose,
            "verdict": verdict,
            "error": err,
        }

    # Verify gate first: clusters #2 and #3 (1st delivery)
    print("=== Verify gate (clusters 2 and 3) ===")
    verify_ks = [k for k in (1, 2) if k < len(clusters)]
    verify_results = [call_one(k, i + 1, len(verify_ks))
                      for i, k in enumerate(verify_ks)]
    c3 = next((r for r in verify_results if r["cluster_id"] == 3), None)
    if c3 is None or c3["verdict"] is None:
        sys.exit("Verify gate: cluster 3 missing verdict")
    c3_moments = c3["verdict"].get("live_delivery_moments") or []
    if not c3_moments:
        sys.exit("Verify gate FAIL: cluster 3 returned empty "
                 "live_delivery_moments — rubric needs further work. "
                 f"Cluster 3 verdict: {c3['verdict']}")
    print(f"Verify gate PASS: cluster 3 returned {len(c3_moments)} "
          f"live moment(s) -> {[m.get('t') for m in c3_moments]}")

    selected = select_clusters_for_api(clusters, frames, API_CAP)
    remaining = [k for k in selected if k not in verify_ks]
    print(f"Selected {len(selected)}/{len(clusters)} total; "
          f"{len(remaining)} remaining after verify")

    results = list(verify_results)
    t0 = time.time()
    for idx, k in enumerate(remaining, 1):
        results.append(call_one(k, idx, len(remaining)))
    dt = time.time() - t0
    print(f"Wall (post-verify): {dt:.1f}s")

    prose_lines: list[str] = []
    for r in results:
        p = r["payload"]
        prose_lines.append(
            f"=== Cluster {r['cluster_id']}: "
            f"{p['start_t']:.1f}-{p['end_t']:.1f}s "
            f"({p['duration_s']:.1f}s, {p['frame_count']} frames) ==="
        )
        prose_lines.append(r.get("prose") or "(no prose captured)")
        prose_lines.append("")
    PROSE_TXT.write_text("\n".join(prose_lines))

    # Moment-based gate: a cluster passes iff len(moments) >= 1, every
    # moment t lies inside [start_t, end_t], and confidence >= GATE_CONF.
    def passes_gate(r: dict) -> tuple[bool, str]:
        v = r.get("verdict")
        if v is None:
            return False, "no-verdict"
        moments = v.get("live_delivery_moments") or []
        if not moments:
            return False, "no-live-moments"
        c = v.get("confidence")
        if c is None or c < GATE_CONF:
            return False, f"conf={c}"
        p = r["payload"]
        for m in moments:
            t = m.get("t")
            if t is None or not (p["start_t"] <= t <= p["end_t"]):
                return False, f"moment-out-of-range({t})"
        return True, "kept"

    for r in results:
        ok, why = passes_gate(r)
        r["gate_kept"] = ok
        r["gate_reason"] = why

    kept = [r for r in results if r["gate_kept"]]
    anchors_all: list[dict] = []
    for r in kept:
        for m in r["verdict"]["live_delivery_moments"]:
            anchors_all.append({
                "t": m["t"],
                "evidence": m.get("evidence", ""),
                "cluster_id": r["cluster_id"],
                "confidence": r["verdict"].get("confidence"),
            })
    anchor_groups = group_anchors(anchors_all, MERGE_GAP_S)

    RESULTS_JSON.write_text(json.dumps({
        "model": MODEL,
        "wall_time_s": dt,
        "cluster_count": len(clusters),
        "selected_count": len(selected),
        "results": results,
        "anchor_groups": anchor_groups,
    }, indent=2))

    # Markdown report
    md = [
        "# Cluster-level QA report",
        "",
        f"Model: `{MODEL}` · {len(clusters)} clusters built · "
        f"{len(selected)} called · wall {dt:.1f}s.",
        f"Cluster builder: gap_max={CLUSTER_GAP_MAX}, "
        f"min_run={CLUSTER_MIN_RUN}, signal=V|S|M|W|K.",
        "",
        "## Cluster table",
        "",
        "| ID | Window | Frames | Signals | Paths | #Live | #Replay | "
        "Live moments | Conf | Gate |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        p = r["payload"]
        v = r.get("verdict") or {}
        moments = v.get("live_delivery_moments") or []
        replays = v.get("replay_moments") or []
        gate = "KEEP" if r.get("gate_kept") else f"DROP ({r.get('gate_reason')})"
        sig = "/".join(f"{p['signal_summary'][k]}" for k in "VSMWK")
        path = "/".join(f"{p['path_summary'][k]}" for k in ("A", "B", "C", "none"))
        moments_s = "; ".join(
            f"t={m.get('t')}: {(m.get('evidence') or '')[:80]}"
            for m in moments
        ).replace("|", "/").replace("\n", " ") or "—"
        md.append(
            f"| {r['cluster_id']} | "
            f"{p['start_t']:.1f}-{p['end_t']:.1f}s ({p['duration_s']:.1f}s) | "
            f"{p['frame_count']} | "
            f"{sig} | {path} | "
            f"{len(moments)} | {len(replays)} | "
            f"{moments_s} | "
            f"{v.get('confidence', '-')} | {gate} |"
        )

    # Block table
    md.extend([
        "",
        f"## Anchor groups (merge gap <= {MERGE_GAP_S:.0f}s, no min-"
        "duration filter — singletons retained)",
        "",
        "| ID | #Anchors | Earliest | Latest | Source clusters | "
        "Anchors (t @ cluster) | Evidence |",
        "|---|---|---|---|---|---|---|",
    ])
    if not anchor_groups:
        md.append("| — | 0 | — | — | — | — | — |")
    for i, g in enumerate(anchor_groups, 1):
        ids = sorted({a["cluster_id"] for a in g["anchors"]})
        anchors_s = ", ".join(
            f"{a['t']:.1f}@c{a['cluster_id']}" for a in g["anchors"]
        )
        ev_s = " // ".join(
            (a.get("evidence") or "").replace("|", "/").replace("\n", " ")
            for a in g["anchors"]
        )
        md.append(
            f"| {i} | {len(g['anchors'])} | "
            f"{g['earliest']:.1f}s | {g['latest']:.1f}s | "
            f"{','.join(map(str, ids))} | {anchors_s} | {ev_s} |"
        )

    # Truth check
    md.extend([
        "",
        "## Truth check",
        "",
    ])
    for name, lo, hi in TRUTH_WINDOWS:
        overlapping = [r for r in results
                       if r["payload"]["start_t"] <= hi
                       and r["payload"]["end_t"] >= lo]
        if not overlapping:
            md.append(f"- **{name}** ({lo:.0f}-{hi:.0f}s): "
                      "NO clusters overlap.")
            continue
        with_moments = []
        moments_in_truth = []
        for r in overlapping:
            ms = (r.get("verdict") or {}).get("live_delivery_moments") or []
            if ms:
                with_moments.append(r["cluster_id"])
            for m in ms:
                t = m.get("t")
                if t is not None and lo <= t <= hi:
                    moments_in_truth.append((r["cluster_id"], t))
        ids = [r["cluster_id"] for r in overlapping]
        md.append(
            f"- **{name}** ({lo:.0f}-{hi:.0f}s): "
            f"{len(overlapping)} cluster(s) overlap "
            f"[{','.join(map(str, ids))}], "
            f"{len(with_moments)} with live moments "
            f"[{','.join(map(str, with_moments)) or '—'}], "
            f"{len(moments_in_truth)} moments inside truth window "
            f"[{','.join(f'{cid}@{t:.1f}s' for cid, t in moments_in_truth) or '—'}]."
        )

    # Gate metrics
    total_moments = sum(
        len((r.get("verdict") or {}).get("live_delivery_moments") or [])
        for r in results
    )
    in_range = sum(
        1
        for r in results
        for m in ((r.get("verdict") or {}).get("live_delivery_moments") or [])
        if m.get("t") is not None
        and r["payload"]["start_t"] <= m["t"] <= r["payload"]["end_t"]
    )
    in_range_pct = (100.0 * in_range / total_moments) if total_moments else 0.0
    md.extend([
        "",
        "## Gate metrics",
        "",
        f"- Clusters tested: {len(results)}",
        f"- Clusters with ≥1 live moment: "
        f"{sum(1 for r in results if ((r.get('verdict') or {}).get('live_delivery_moments') or []))}",
        f"- Total live moments: {total_moments}",
        f"- Clusters kept (≥1 moment ∧ all moments in-range ∧ conf ≥ "
        f"{GATE_CONF}): {len(kept)}",
        f"- Total anchors across kept clusters: {len(anchors_all)}",
        f"- Final anchor groups emitted: {len(anchor_groups)}",
        f"- Moment-in-window sanity: {in_range}/{total_moments} "
        f"({in_range_pct:.0f}%; should be 100%)",
    ])
    RESULTS_MD.write_text("\n".join(md) + "\n")
    print(f"Wrote {RESULTS_JSON} and {RESULTS_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
