#!/usr/bin/env python3
"""Stage 1 70b post-pass — region-by-region validation of pipeline
clusters using llama-3.3-70b-versatile.

Now also surfaces dropped-but-considered candidates (FIX5_DROPPED,
HARD_REJECT_RUN, MIN_RUN_DROPPED, V_FILTER_DROPPED, PHANTOM_NOT_RESCUED)
so 70b can endorse drop-reversals when warranted."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from groq import AsyncGroq

REPO_ROOT = Path(__file__).resolve().parents[3]
SCOUT_BASE = REPO_ROOT / "files/scripts/broadcast_mode_tuning"
sys.path.insert(0, str(SCOUT_BASE))

from signal_extraction import extract_signals  # noqa: E402
from delivery_classifier import (  # noqa: E402
    FrameInfo, annotate_all, pick_anchor, rescue_singletons,
    merge_rescued_with_neighbors, phantom_rescue,
    strong_post_action_match,
)
from delivery_clip_pipeline import (  # noqa: E402
    is_replay_followup, is_wicket_cluster,
)

DEFAULT_REPORT = SCOUT_BASE / "predicted_clips_3600/pipeline_report.md"
OUT_MD = SCOUT_BASE / "stage1_70b_report.md"
OUT_JSON = SCOUT_BASE / "stage1_70b_results.json"

MODEL = "llama-3.3-70b-versatile"
TEMPERATURE = 0.0
MAX_TOKENS = 2200
TIMEOUT_S = 60.0
CONCURRENCY = 4

GROQ_KEY = os.environ.get(
    "GROQ_API_KEY",
    os.environ["GROQ_API_KEY"],
)

SYSTEM_PROMPT = (
    "You analyze 1fps frame descriptions from a cricket broadcast. "
    "A LIVE DELIVERY is a single legal ball bowled by the bowler in "
    "ongoing match play. Each delivery has: a setup phase (run-up), "
    "a release moment (ball bowled), and a post-action phase "
    "(batter's shot or no-shot, fielder reaction, score update). "
    "A REPLAY shows the same delivery from a different camera angle "
    "or in slow-motion, often with stat overlays. An AD/PROMO is "
    "non-cricket content (commercials, sponsor cards, studio shots, "
    "dugout interviews). BETWEEN_BALLS_SETUP is wide-field cricket "
    "content between deliveries (bowler walking back, batter "
    "adjusting). BOWLER_INTRO is a stats card shown when a new "
    "bowler starts an over.\n\n"
    "The user's pipeline already detected candidate clusters at "
    "specific timestamps (provided in the prompt). Some other "
    "candidates were considered and dropped with a stated drop "
    "reason; for those, decide whether the drop was correct or "
    "whether a real delivery was wrongly dropped. Re-validate "
    "kept clusters and find any deliveries the pipeline missed in "
    "the gaps."
)


@dataclass
class Cluster:
    idx: int
    anchor_t: float
    path: str
    clip_start: float
    clip_end: float


@dataclass
class DroppedCandidate:
    drop_reason: str
    start_t: float
    end_t: float
    anchor_t: float
    paths: list[str]


def parse_report(path: Path) -> list[Cluster]:
    txt = path.read_text()
    out: list[Cluster] = []
    for m in re.finditer(
        r"\|\s*(\d+)\s*\|\s*t=([\d.]+)s\s*\|\s*(\w+)\s*\|\s*"
        r"([\d.]+)-([\d.]+)s\s*\|\s*([\d.]+)s\s*\|", txt):
        out.append(Cluster(
            idx=int(m.group(1)),
            anchor_t=float(m.group(2)),
            path=m.group(3),
            clip_start=float(m.group(4)),
            clip_end=float(m.group(5)),
        ))
    return out


def shadow_pipeline_with_drops(frames: list[FrameInfo],
                                gap_max: int = 3,
                                min_run: int = 2) -> tuple[
                                    list[dict], list[DroppedCandidate]]:
    """Replay the cluster builder + Fix 5 + phantom rescue, capturing
    every dropped candidate and its drop_reason. Returns (final
    clusters, dropped candidates)."""
    n = len(frames)
    drops: list[DroppedCandidate] = []
    raw_runs: list[dict] = []  # all path-firing runs (regardless of filter)
    hard_runs: list[tuple[int, int]] = []

    # 1. Walk frames, capture every is_delivery run + adjacent HARD runs.
    i = 0
    while i < n:
        f = frames[i]
        if f.signals.HARD:
            j = i
            while j < n and frames[j].signals.HARD:
                j += 1
            hard_runs.append((i, j - 1))
            i = j
            continue
        if not f.is_delivery:
            i += 1
            continue
        start = i
        last_d = i
        j = i + 1
        gap = 0
        while j < n:
            fj = frames[j]
            if fj.signals.HARD:
                break
            if fj.is_delivery:
                last_d = j
                gap = 0
            else:
                gap += 1
                if gap > gap_max:
                    break
            j += 1
        run_frames = frames[start:last_d + 1]
        delivery_count = sum(1 for x in run_frames if x.is_delivery)
        any_v = any(x.signals.V for x in run_frames)
        raw_runs.append({
            "start_idx": start,
            "end_idx": last_d,
            "start_t": frames[start].t,
            "end_t": frames[last_d].t,
            "frames": run_frames,
            "delivery_count": delivery_count,
            "any_v": any_v,
        })
        i = last_d + 1

    # 2. Apply build_clusters gates (min_run + V-filter), capturing
    # MIN_RUN_DROPPED and V_FILTER_DROPPED. V-filter-dropped runs that
    # are Path-C-only become PHANTOM_NOT_RESCUED candidates if phantom
    # rescue evidence is missing.
    kept_runs: list[dict] = []
    for r in raw_runs:
        if r["delivery_count"] < min_run:
            paths = [x.path for x in r["frames"] if x.is_delivery]
            anchor = r["frames"][0].t
            drops.append(DroppedCandidate(
                drop_reason="MIN_RUN", start_t=r["start_t"],
                end_t=r["end_t"], anchor_t=anchor, paths=paths))
            continue
        if not r["any_v"]:
            delivery_paths = [x.path for x in r["frames"] if x.is_delivery]
            all_c = bool(delivery_paths) and \
                all(p == "C" for p in delivery_paths)
            tag = "V_FILTER" if not all_c else "PHANTOM_NOT_RESCUED"
            anchor = r["frames"][0].t
            drops.append(DroppedCandidate(
                drop_reason=tag, start_t=r["start_t"],
                end_t=r["end_t"], anchor_t=anchor, paths=delivery_paths))
            continue
        kept_runs.append({
            "start_idx": r["start_idx"],
            "end_idx": r["end_idx"],
            "start_t": r["start_t"],
            "end_t": r["end_t"],
            "frames": r["frames"],
        })

    # 3. Mark wicket clusters (used by Fix 5 extended-window logic).
    for c in kept_runs:
        c["is_wicket"] = is_wicket_cluster(c)

    # 4. Apply Fix 5 (replay-followup drop). Capture FIX5_DROPPED.
    plans = []
    for c in kept_runs:
        anchor = pick_anchor(c)
        plans.append({"cluster": c, "anchor": anchor})
    filtered_plans: list[dict] = []
    dropped_frame_ts: set[float] = set()
    for p in plans:
        prev = filtered_plans[-1] if filtered_plans else None
        is_repl, why = is_replay_followup(p, prev)
        if is_repl:
            c = p["cluster"]
            paths = [x.path for x in c["frames"] if x.is_delivery]
            drops.append(DroppedCandidate(
                drop_reason="FIX5_DROPPED",
                start_t=c["start_t"], end_t=c["end_t"],
                anchor_t=p["anchor"].t, paths=paths))
            for f in c["frames"]:
                dropped_frame_ts.add(f.t)
            continue
        filtered_plans.append(p)

    # 5. Capture HARD_REJECT runs (frames where HARD fired).
    for hs, he in hard_runs:
        run_frames = frames[hs:he + 1]
        drops.append(DroppedCandidate(
            drop_reason="HARD_REJECT",
            start_t=run_frames[0].t, end_t=run_frames[-1].t,
            anchor_t=run_frames[0].t,
            paths=["HARD"] * len(run_frames)))

    # 6. Run rescue + merge + phantom rescue (mirroring the live
    # pipeline) so the resulting cluster set matches the report.
    kept_clusters = [p["cluster"] for p in filtered_plans]
    rescue_candidates = [f for f in frames if f.t not in dropped_frame_ts]
    augmented = rescue_singletons(kept_clusters, rescue_candidates,
                                   max_distance_s=60.0)
    merged = merge_rescued_with_neighbors(augmented, max_distance_s=10.0)
    phantom_candidates = [f for f in frames if f.t not in dropped_frame_ts]
    final_clusters = phantom_rescue(merged, phantom_candidates,
                                     post_action_window_s=3.0)
    return final_clusters, drops


def build_regions(clusters: list[Cluster],
                   drops: list[DroppedCandidate],
                   window_end: float,
                   pad: float = 5.0, gap_min: float = 25.0,
                   max_size: float = 90.0,
                   split_target: float = 60.0,
                   overlap: float = 10.0) -> list[tuple[float, float]]:
    raw: list[tuple[float, float]] = []
    for c in clusters:
        raw.append((max(0.0, c.clip_start - pad),
                    min(window_end, c.clip_end + pad)))
    for d in drops:
        raw.append((max(0.0, d.start_t - pad),
                    min(window_end, d.end_t + pad)))
    raw.sort()
    # Merge overlaps to produce "covered" intervals.
    covered: list[tuple[float, float]] = []
    for s, e in raw:
        if covered and s <= covered[-1][1]:
            covered[-1] = (covered[-1][0], max(covered[-1][1], e))
        else:
            covered.append((s, e))
    # Fill gaps >gap_min between covered intervals.
    regions: list[tuple[float, float]] = list(covered)
    for a, b in zip(covered, covered[1:]):
        gs, ge = a[1], b[0]
        if ge - gs > gap_min:
            regions.append((gs, ge))
    # Pre-first and post-last tails.
    if covered:
        first = covered[0][0]
        if first > 0:
            regions.append((0.0, first))
        last = covered[-1][1]
        if window_end - last > 0:
            regions.append((last, window_end))
    else:
        regions.append((0.0, window_end))
    regions.sort()
    # Merge overlaps again after additions.
    merged: list[tuple[float, float]] = []
    for r in regions:
        if merged and r[0] <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], r[1]))
        else:
            merged.append(r)
    # Split oversized.
    final: list[tuple[float, float]] = []
    for s, e in merged:
        if e - s <= max_size:
            final.append((s, e))
            continue
        cur = s
        while cur < e:
            seg_end = min(e, cur + split_target)
            final.append((cur, seg_end))
            if seg_end >= e:
                break
            cur = seg_end - overlap
    return final


def gather_prose(start_t: float, end_t: float,
                  sidecar_dirs: list[Path]) -> list[tuple[float, str]]:
    frames: list[tuple[float, str]] = []
    seen: set[float] = set()
    for d in sidecar_dirs:
        if not d.exists():
            continue
        for p in sorted(d.glob("*.txt")):
            try:
                t = float(p.stem.split("_t=")[1])
            except (IndexError, ValueError):
                continue
            if t < start_t or t > end_t:
                continue
            if t in seen:
                continue
            seen.add(t)
            raw = p.read_text()
            text = raw.split("---\n", 1)[1].strip() if "---\n" in raw else raw
            text = text.replace("\n", " ").strip()
            frames.append((t, text))
    frames.sort()
    return frames


def assign_drop_ids(drops: list[DroppedCandidate]) -> list[dict]:
    return [{
        "id": i + 1, "drop_reason": d.drop_reason,
        "start_t": d.start_t, "end_t": d.end_t,
        "anchor_t": d.anchor_t, "paths": d.paths,
    } for i, d in enumerate(drops)]


def kept_in_region(clusters: list[Cluster],
                    start_t: float, end_t: float) -> list[Cluster]:
    return [c for c in clusters
            if start_t <= c.anchor_t <= end_t]


def drops_in_region(drops_w_id: list[dict],
                     start_t: float, end_t: float) -> list[dict]:
    return [d for d in drops_w_id
            if d["anchor_t"] >= start_t and d["anchor_t"] <= end_t]


def build_user_prompt(start_t: float, end_t: float,
                       prose_frames: list[tuple[float, str]],
                       region_clusters: list[Cluster],
                       region_drops: list[dict]) -> str:
    cl_lines = []
    if region_clusters:
        for c in region_clusters:
            cl_lines.append(
                f"  - cluster {c.idx}: anchor t={c.anchor_t:.1f}s "
                f"(path={c.path}, clip {c.clip_start:.1f}-{c.clip_end:.1f}s)"
            )
    else:
        cl_lines.append("  (none)")
    drop_lines = []
    if region_drops:
        for d in region_drops:
            drop_lines.append(
                f"  - drop {d['id']}: anchor t={d['anchor_t']:.1f}s "
                f"({d['start_t']:.1f}-{d['end_t']:.1f}s, "
                f"reason={d['drop_reason']}, paths={d['paths']})"
            )
    else:
        drop_lines.append("  (none)")
    frame_lines = [f"[t={t:.1f}] {prose}" for t, prose in prose_frames]
    return (
        f"Region: {start_t:.1f}s -> {end_t:.1f}s "
        f"({end_t - start_t:.1f}s, {len(prose_frames)} frames).\n"
        f"Pipeline-detected (kept) clusters in this region:\n"
        + "\n".join(cl_lines)
        + "\nPipeline-considered (dropped) clusters in this region "
        "with drop reason:\n"
        + "\n".join(drop_lines)
        + "\n\nFor each kept cluster, decide if a real delivery is "
        "present. For each dropped cluster, decide whether the drop "
        "was correct (REPLAY/AD/BETWEEN_BALLS/etc) or whether a real "
        "delivery was wrongly dropped (drop-reversal). Also surface "
        "any deliveries the pipeline missed entirely.\n"
        "\nFrame descriptions:\n"
        + "\n".join(frame_lines)
        + "\n\nOutput JSON only:\n"
        '{\n'
        '  "deliveries": [\n'
        '    {\n'
        '      "start_t": float,\n'
        '      "end_t": float,\n'
        '      "outcome": "DOT|RUNS|FOUR|SIX|WICKET|UNKNOWN",\n'
        '      "confidence": 0.0-1.0,\n'
        '      "evidence": "one sentence citing frame timestamps",\n'
        '      "matches_pipeline_cluster": <cluster_id or null>,\n'
        '      "matches_dropped_cluster": <drop_id or null>\n'
        '    }\n'
        '  ],\n'
        '  "non_deliveries": [\n'
        '    {\n'
        '      "type": "REPLAY|AD|BOWLER_INTRO|BETWEEN_BALLS|OTHER",\n'
        '      "start_t": float,\n'
        '      "end_t": float,\n'
        '      "matches_pipeline_cluster": <cluster_id or null>,\n'
        '      "matches_dropped_cluster": <drop_id or null>\n'
        '    }\n'
        '  ]\n'
        '}'
    )


async def call_70b(client: AsyncGroq, sem: asyncio.Semaphore,
                    region: tuple[float, float],
                    prose_frames: list[tuple[float, str]],
                    region_clusters: list[Cluster],
                    region_drops: list[dict]) -> dict:
    user_prompt = build_user_prompt(region[0], region[1],
                                    prose_frames, region_clusters,
                                    region_drops)
    async with sem:
        for attempt in range(5):
            try:
                resp = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=MODEL,
                        temperature=TEMPERATURE,
                        max_tokens=MAX_TOKENS,
                        response_format={"type": "json_object"},
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                    ),
                    timeout=TIMEOUT_S,
                )
                content = resp.choices[0].message.content
                parsed = json.loads(content)
                return {"region": region, "ok": True, "result": parsed}
            except json.JSONDecodeError as e:
                if attempt == 4:
                    return {"region": region, "ok": False,
                            "error": f"json: {e}", "raw": content}
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                is_429 = "429" in msg or "rate_limit" in msg.lower()
                if attempt == 4:
                    return {"region": region, "ok": False, "error": msg}
                await asyncio.sleep(15.0 if is_429 else 2.0)
    return {"region": region, "ok": False, "error": "unknown"}


async def main_async(sidecar_dirs: list[Path],
                      clusters: list[Cluster],
                      window_end: float) -> int:
    # Load + annotate frames once.
    frames: list[FrameInfo] = []
    seen: set[float] = set()
    for d in sidecar_dirs:
        if not d.exists():
            continue
        for p in sorted(d.glob("f_*.txt")):
            m = re.search(r"_t=(\d+(?:\.\d+)?)\.txt$", p.name)
            if not m:
                continue
            t = float(m.group(1))
            if t > window_end or t in seen:
                continue
            seen.add(t)
            raw = p.read_text()
            text = raw.split("---\n", 1)[1].strip() if "---\n" in raw else raw
            f = FrameInfo(t=t, text=text)
            f.signals = extract_signals(text)
            frames.append(f)
    frames.sort(key=lambda f: f.t)
    annotate_all(frames)

    final_clusters, drops = shadow_pipeline_with_drops(frames)
    print(f"Shadow pipeline: {len(final_clusters)} final clusters, "
          f"{len(drops)} dropped candidates")
    by_reason: dict[str, int] = {}
    for d in drops:
        by_reason[d.drop_reason] = by_reason.get(d.drop_reason, 0) + 1
    for k, v in sorted(by_reason.items()):
        print(f"  {k}: {v}")
    drops_w_id = assign_drop_ids(drops)

    regions = build_regions(clusters, drops, window_end)
    print(f"Built {len(regions)} regions for 0-{window_end:.0f}s.")

    client = AsyncGroq(api_key=GROQ_KEY)
    sem = asyncio.Semaphore(CONCURRENCY)

    tasks = []
    for region in regions:
        prose_frames = gather_prose(region[0], region[1], sidecar_dirs)
        region_cls = kept_in_region(clusters, region[0], region[1])
        region_drops = drops_in_region(drops_w_id, region[0], region[1])
        tasks.append(call_70b(client, sem, region, prose_frames,
                               region_cls, region_drops))
    results = await asyncio.gather(*tasks)

    n_ok = sum(1 for r in results if r["ok"])
    n_err = sum(1 for r in results if not r["ok"])
    print(f"\n70b calls: {n_ok} ok, {n_err} errors")

    # Aggregate.
    all_deliveries: list[dict] = []
    all_non_deliveries: list[dict] = []
    for r in results:
        if not r["ok"]:
            continue
        res = r["result"]
        for d in res.get("deliveries", []) or []:
            d["region"] = list(r["region"])
            all_deliveries.append(d)
        for nd in res.get("non_deliveries", []) or []:
            nd["region"] = list(r["region"])
            all_non_deliveries.append(nd)

    # Dedupe deliveries by start_t (keep highest confidence).
    by_start: dict[float, dict] = {}
    for d in all_deliveries:
        try:
            st = round(float(d.get("start_t", -1)), 1)
        except (TypeError, ValueError):
            continue
        if st < 0:
            continue
        prev = by_start.get(st)
        if prev is None or float(d.get("confidence", 0) or 0) > \
                float(prev.get("confidence", 0) or 0):
            by_start[st] = d
    deliveries = sorted(by_start.values(), key=lambda d: d["start_t"])

    # Diff: agreed / rejected / reclassified / found / drop-reversal.
    agreed: list[tuple[Cluster, dict]] = []
    rejected: list[Cluster] = []
    reclassified: list[tuple[Cluster, dict]] = []
    rescued: list[tuple[dict, dict]] = []  # (drop, delivery)
    found: list[dict] = []

    def find_match_for_cluster(c: Cluster) -> dict | None:
        explicit = [d for d in deliveries
                    if d.get("matches_pipeline_cluster") == c.idx]
        if explicit:
            return explicit[0]
        nearby = [d for d in deliveries
                  if abs(float(d.get("start_t", 0) or 0) - c.anchor_t) <= 10.0
                  or (float(d.get("start_t", 0) or 0) <= c.anchor_t
                      <= float(d.get("end_t", 0) or 0))]
        if nearby:
            nearby.sort(key=lambda d: abs(
                float(d.get("start_t", 0) or 0) - c.anchor_t))
            return nearby[0]
        return None

    for c in clusters:
        m = find_match_for_cluster(c)
        if m is not None:
            agreed.append((c, m))
        else:
            nd_match = None
            for nd in all_non_deliveries:
                if nd.get("matches_pipeline_cluster") == c.idx:
                    nd_match = nd
                    break
                try:
                    s = float(nd.get("start_t", 0) or 0)
                    e = float(nd.get("end_t", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if s <= c.anchor_t <= e:
                    nd_match = nd
                    break
            if nd_match is not None:
                reclassified.append((c, nd_match))
            else:
                rejected.append(c)

    # Drop-reversals: deliveries with matches_dropped_cluster id.
    matched_delivery_ids: set[int] = set()
    for _, d in agreed:
        matched_delivery_ids.add(id(d))
    drops_by_id = {d["id"]: d for d in drops_w_id}
    for d in deliveries:
        if id(d) in matched_delivery_ids:
            continue
        did = d.get("matches_dropped_cluster")
        if did and did in drops_by_id:
            rescued.append((drops_by_id[did], d))
            matched_delivery_ids.add(id(d))

    # Anything else not matched = found.
    for d in deliveries:
        if id(d) in matched_delivery_ids:
            continue
        found.append(d)

    # Write JSON.
    OUT_JSON.write_text(json.dumps({
        "regions": [{"start": r[0], "end": r[1]} for r in regions],
        "drops": drops_w_id,
        "deliveries": deliveries,
        "non_deliveries": all_non_deliveries,
        "diff": {
            "agreed": [{"cluster_id": c.idx, "anchor_t": c.anchor_t,
                         "delivery": d} for c, d in agreed],
            "rejected": [{"cluster_id": c.idx, "anchor_t": c.anchor_t,
                           "path": c.path,
                           "clip_window": [c.clip_start, c.clip_end]}
                          for c in rejected],
            "reclassified": [{"cluster_id": c.idx, "anchor_t": c.anchor_t,
                                "non_delivery": nd}
                             for c, nd in reclassified],
            "rescued": [{"drop": dr, "delivery": dl}
                         for dr, dl in rescued],
            "found": found,
        },
        "errors": [r for r in results if not r["ok"]],
    }, indent=2, default=str))

    # Write Markdown.
    md: list[str] = []
    md.append("# Stage 1 70b validation report\n\n")
    md.append(f"Window: 0-{window_end:.0f}s · "
              f"Pipeline clusters: {len(clusters)} · "
              f"Dropped candidates: {len(drops)} · "
              f"70b deliveries: {len(deliveries)} · "
              f"Regions: {len(regions)} ({n_ok} ok, {n_err} errors)\n\n")
    md.append("## Drop categories\n")
    for k, v in sorted(by_reason.items()):
        md.append(f"- {k}: {v}\n")
    md.append("\n## Summary\n")
    md.append(f"- agreed: **{len(agreed)}**\n")
    md.append(f"- 70b-rejected: **{len(rejected)}**\n")
    md.append(f"- 70b-reclassified: **{len(reclassified)}**\n")
    md.append(f"- 70b-rescued (drop-reversal): **{len(rescued)}**\n")
    md.append(f"- 70b-found (no pipeline candidate): **{len(found)}**\n")

    md.append("\n## 70b-rescued (drop-reversals, ranked by drop reason)\n")
    if rescued:
        priority = {"V_FILTER": 1, "MIN_RUN": 2, "PHANTOM_NOT_RESCUED": 3,
                    "FIX5_DROPPED": 4, "HARD_REJECT": 5}
        rescued.sort(key=lambda x: (
            priority.get(x[0]["drop_reason"], 9),
            -float(x[1].get("confidence", 0) or 0)))
        md.append("| drop_id | reason | start | end | conf | "
                  "outcome | evidence |\n")
        md.append("|---|---|---|---|---|---|---|\n")
        for dr, dl in rescued:
            ev = (dl.get("evidence", "") or "").replace("|", "/")
            md.append(f"| d{dr['id']} | {dr['drop_reason']} | "
                      f"{dr['start_t']:.1f} | {dr['end_t']:.1f} | "
                      f"{dl.get('confidence', '?')} | "
                      f"{dl.get('outcome', '?')} | {ev} |\n")
    else:
        md.append("(none)\n")

    md.append("\n## 70b-rejected\n")
    if rejected:
        md.append("| cluster | anchor | path | clip |\n")
        md.append("|---|---|---|---|\n")
        for c in rejected:
            md.append(f"| c{c.idx} | t={c.anchor_t:.1f}s | {c.path} | "
                      f"{c.clip_start:.1f}-{c.clip_end:.1f}s |\n")
    else:
        md.append("(none)\n")

    md.append("\n## 70b-reclassified\n")
    if reclassified:
        md.append("| cluster | anchor | 70b type | window |\n")
        md.append("|---|---|---|---|\n")
        for c, nd in reclassified:
            md.append(f"| c{c.idx} | t={c.anchor_t:.1f}s | "
                      f"{nd.get('type', '?')} | "
                      f"{nd.get('start_t', '?')}-"
                      f"{nd.get('end_t', '?')} |\n")
    else:
        md.append("(none)\n")

    md.append("\n## 70b-found (pipeline never considered)\n")
    if found:
        md.append("| start | end | outcome | conf | evidence |\n")
        md.append("|---|---|---|---|---|\n")
        for d in found:
            ev = (d.get("evidence", "") or "").replace("|", "/")
            md.append(f"| {d.get('start_t', '?')} | "
                      f"{d.get('end_t', '?')} | "
                      f"{d.get('outcome', '?')} | "
                      f"{d.get('confidence', '?')} | {ev} |\n")
    else:
        md.append("(none)\n")

    md.append("\n## Per-cluster verdict\n")
    md.append("| cluster | anchor | path | verdict | 70b note |\n")
    md.append("|---|---|---|---|---|\n")
    by_idx: dict[int, str] = {}
    by_note: dict[int, str] = {}
    for c, d in agreed:
        by_idx[c.idx] = "agreed"
        by_note[c.idx] = (d.get("evidence", "") or "")[:120]
    for c in rejected:
        by_idx[c.idx] = "rejected"
        by_note[c.idx] = ""
    for c, nd in reclassified:
        by_idx[c.idx] = f"reclassified:{nd.get('type', '?')}"
        by_note[c.idx] = ""
    for c in clusters:
        md.append(f"| c{c.idx} | t={c.anchor_t:.1f}s | {c.path} | "
                  f"{by_idx.get(c.idx, '?')} | "
                  f"{by_note.get(c.idx, '').replace('|', '/')} |\n")

    if n_err > 0:
        md.append("\n## Errors\n")
        for r in results:
            if r["ok"]:
                continue
            md.append(f"- region {r['region']}: "
                      f"{r.get('error', '?')[:200]}\n")

    OUT_MD.write_text("".join(md))

    print()
    print(f"agreed={len(agreed)} rejected={len(rejected)} "
          f"reclassified={len(reclassified)} rescued={len(rescued)} "
          f"found={len(found)}")
    print(f"Wrote {OUT_MD}")
    print(f"Wrote {OUT_JSON}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sidecars-dir",
                    default=",".join(str(SCOUT_BASE / d) for d in [
                        "first_5min_scout_run", "second_5min_scout_run",
                        "third_5min_scout_run", "fourth_5min_scout_run",
                        "fifth_5min_scout_run", "sixth_5min_scout_run",
                        "seventh_5min_scout_run", "eighth_5min_scout_run",
                        "ninth_5min_scout_run", "tenth_5min_scout_run",
                        "eleventh_5min_scout_run", "twelfth_5min_scout_run",
                    ]))
    ap.add_argument("--report", default=str(DEFAULT_REPORT))
    ap.add_argument("--window-end", type=float, default=3600.0)
    args = ap.parse_args()

    sidecar_dirs = [Path(p) for p in args.sidecars_dir.split(",")]
    clusters = parse_report(Path(args.report))
    print(f"Parsed {len(clusters)} clusters from {args.report}")

    return asyncio.run(main_async(sidecar_dirs, clusters, args.window_end))


if __name__ == "__main__":
    raise SystemExit(main())
