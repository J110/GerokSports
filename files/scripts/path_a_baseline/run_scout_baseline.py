#!/usr/bin/env python3
"""Path A baseline — re-classify labeled delivery clips with current Scout.

Reads labels.csv from one or more sessions under
``files/logs/deliveries/<session>/``, extracts frames at 1.0s cadence
from each clip's ``delivery_window.mp4``, dispatches every frame
through the existing ``OpenScout.classify`` path (Llama 4 Scout 17B
on Groq, frozen ``OPEN_PROMPT``), and aggregates per-clip statistics.

Outputs (next to this script):
  - frames/<session>/<clip>/fNNN.jpg   extracted frame cache
  - scout_results.jsonl                per-frame Scout result (resumable)
  - clip_aggregates.csv                per-clip aggregates

Resumable: re-runs skip frames whose (session, clip, frame_index) is
already present in scout_results.jsonl.

Usage::

    cd /Users/anmolmohan/Projects/SportsComm
    PYTHONPATH=files python files/scripts/path_a_baseline/run_scout_baseline.py
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import statistics
import sys
import time
from pathlib import Path

import cv2

SCRIPT_DIR = Path(__file__).resolve().parent
FILES_ROOT = SCRIPT_DIR.parent.parent
REPO_ROOT = FILES_ROOT.parent
DELIVERIES_ROOT = FILES_ROOT / "logs" / "deliveries"

DEFAULT_SESSIONS = [
    "20260420_202239",
    "20260421_195050",
]
DEFAULT_INTERVAL_S = 1.0
DEFAULT_CONCURRENCY = 4
SCOUT_CLASSES = ("action", "replay", "ad", "umpire", "other")

FRAMES_DIR = SCRIPT_DIR / "frames"


def results_path(version: str) -> Path:
    suffix = "" if version == "v1" else f"_{version}"
    return SCRIPT_DIR / f"scout_results{suffix}.jsonl"


def aggregates_path(version: str) -> Path:
    suffix = "" if version == "v1" else f"_{version}"
    return SCRIPT_DIR / f"clip_aggregates{suffix}.csv"


def _ensure_path() -> None:
    p = str(FILES_ROOT)
    if p not in sys.path:
        sys.path.insert(0, p)


def load_labels(session: str) -> list[dict]:
    csv_path = DELIVERIES_ROOT / session / "labels.csv"
    if not csv_path.exists():
        return []
    rows: list[dict] = []
    with csv_path.open("r", newline="") as f:
        for row in csv.DictReader(f):
            row["session"] = session
            rows.append(row)
    return rows


def extract_frames(mp4_path: Path, out_dir: Path,
                   interval_s: float) -> list[Path]:
    """Extract frames at ``interval_s`` cadence; return list in order.

    Cached: if out_dir already has fNNN.jpg files, return those.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(out_dir.glob("f*.jpg"))
    if existing:
        return existing

    cap = cv2.VideoCapture(str(mp4_path))
    if not cap.isOpened():
        return []
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    if fps <= 1.0 or fps != fps:
        fps = 25.0
    step = max(1, int(round(fps * interval_s)))

    saved: list[Path] = []
    idx = 0
    out_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        if idx % step == 0:
            p = out_dir / f"f{out_idx:03d}.jpg"
            cv2.imwrite(str(p), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            saved.append(p)
            out_idx += 1
        idx += 1
    cap.release()
    return saved


def load_done_frames(jsonl_path: Path) -> set[tuple[str, str, int]]:
    if not jsonl_path.exists():
        return set()
    done: set[tuple[str, str, int]] = set()
    with jsonl_path.open("r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = (
                rec.get("session", ""),
                rec.get("clip_id", ""),
                int(rec.get("frame_index", -1)),
            )
            if key[2] >= 0:
                done.add(key)
    return done


async def classify_one(open_scout, sem, frame_path: Path,
                       *, session: str, clip_id: str, manual_label: str,
                       frame_index: int) -> dict:
    img = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
    if img is None:
        return {
            "session": session,
            "clip_id": clip_id,
            "manual_label": manual_label,
            "frame_index": frame_index,
            "scout_class": None,
            "raw_description": "",
            "latency_ms": 0,
            "error": "imread_failed",
        }
    async with sem:
        t0 = time.monotonic()
        res = await open_scout.classify(img, time.time(),
                                        frame_idx=frame_index)
        latency_ms = int((time.monotonic() - t0) * 1000)
    if res is None:
        return {
            "session": session,
            "clip_id": clip_id,
            "manual_label": manual_label,
            "frame_index": frame_index,
            "scout_class": None,
            "raw_description": "",
            "latency_ms": latency_ms,
            "error": open_scout.last_error or "classify_returned_none",
        }
    return {
        "session": session,
        "clip_id": clip_id,
        "manual_label": manual_label,
        "frame_index": frame_index,
        "scout_class": res.frame_class,
        "raw_description": res.raw_description,
        "latency_ms": latency_ms,
        "error": None,
    }


async def run_scout(rows: list[dict], jsonl_path: Path,
                    *, concurrency: int) -> None:
    _ensure_path()
    from eyes.open_scout import OpenScout

    done = load_done_frames(jsonl_path)
    pending: list[tuple[Path, dict]] = []
    for row in rows:
        for fi, fp in enumerate(row["frame_paths"]):
            key = (row["session"], row["clip_id"], fi)
            if key in done:
                continue
            pending.append((
                fp,
                {
                    "session": row["session"],
                    "clip_id": row["clip_id"],
                    "manual_label": row["label"],
                    "frame_index": fi,
                },
            ))
    if not pending:
        print("[scout] all frames already classified")
        return

    print(f"[scout] dispatching {len(pending)} frames "
          f"with concurrency={concurrency}")
    open_scout = OpenScout()
    sem = asyncio.Semaphore(concurrency)

    out_f = jsonl_path.open("a")
    write_lock = asyncio.Lock()
    try:
        async def runner(fp, ctx):
            rec = await classify_one(open_scout, sem, fp, **ctx)
            async with write_lock:
                out_f.write(json.dumps(rec) + "\n")
                out_f.flush()
            return rec

        tasks = [asyncio.create_task(runner(fp, ctx))
                 for fp, ctx in pending]
        completed = 0
        for fut in asyncio.as_completed(tasks):
            rec = await fut
            completed += 1
            if completed % 25 == 0 or completed == len(tasks):
                print(f"[scout] {completed}/{len(tasks)} "
                      f"(last: {rec['session']}/{rec['clip_id']}"
                      f"/f{rec['frame_index']:03d} "
                      f"-> {rec['scout_class']})")
    finally:
        out_f.close()
        await open_scout.aclose()


def aggregate(jsonl_path: Path, agg_path: Path) -> list[dict]:
    by_clip: dict[tuple[str, str], dict] = {}
    if not jsonl_path.exists():
        return []
    with jsonl_path.open("r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            key = (rec["session"], rec["clip_id"])
            slot = by_clip.setdefault(key, {
                "session": rec["session"],
                "clip_id": rec["clip_id"],
                "manual_label": rec["manual_label"],
                "frames": [],
            })
            slot["frames"].append(rec)

    results: list[dict] = []
    for (session, clip_id), slot in sorted(by_clip.items()):
        frames = sorted(slot["frames"], key=lambda r: r["frame_index"])
        classes = [r["scout_class"] for r in frames]
        latencies = [r["latency_ms"] for r in frames if r.get("latency_ms")]
        total = len(classes)
        action_count = sum(1 for c in classes if c == "action")
        replay_count = sum(1 for c in classes if c == "replay")
        ad_count = sum(1 for c in classes if c == "ad")
        other_count = sum(1 for c in classes if c in ("other", "umpire", None))
        max_run = 0
        cur = 0
        for c in classes:
            if c == "action":
                cur += 1
                if cur > max_run:
                    max_run = cur
            else:
                cur = 0
        agg = {
            "session": session,
            "clip_id": clip_id,
            "manual_label": slot["manual_label"],
            "total_frames": total,
            "action_count": action_count,
            "action_ratio": (action_count / total) if total else 0.0,
            "max_consecutive_action": max_run,
            "replay_count": replay_count,
            "ad_count": ad_count,
            "other_count": other_count,
            "latency_median_ms": (int(statistics.median(latencies))
                                  if latencies else 0),
        }
        results.append(agg)

    with agg_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "session", "clip_id", "manual_label", "total_frames",
            "action_count", "action_ratio", "max_consecutive_action",
            "replay_count", "ad_count", "other_count",
            "latency_median_ms",
        ])
        writer.writeheader()
        for r in results:
            row = dict(r)
            row["action_ratio"] = f"{r['action_ratio']:.3f}"
            writer.writerow(row)
    return results


def summarize(aggs: list[dict]) -> None:
    by_label: dict[str, list[dict]] = {}
    for r in aggs:
        by_label.setdefault(r["manual_label"], []).append(r)
    print("\n=== Per-label summary ===")
    print(f"{'label':<16} {'n':>4} {'action_ratio mean':>18} "
          f"{'p25':>6} {'p50':>6} {'p75':>6} "
          f"{'max_run mean':>14} {'max_run max':>12}")
    for label in sorted(by_label):
        rs = by_label[label]
        ratios = [r["action_ratio"] for r in rs]
        runs = [r["max_consecutive_action"] for r in rs]
        ratios_s = sorted(ratios)
        n = len(ratios)
        if n == 0:
            continue
        mean = sum(ratios) / n
        p25 = ratios_s[max(0, n // 4)]
        p50 = ratios_s[n // 2]
        p75 = ratios_s[min(n - 1, (3 * n) // 4)]
        run_mean = sum(runs) / n
        run_max = max(runs)
        print(f"{label:<16} {n:>4} {mean:>18.3f} "
              f"{p25:>6.2f} {p50:>6.2f} {p75:>6.2f} "
              f"{run_mean:>14.2f} {run_max:>12d}")

    print("\n=== Threshold sweep (action_ratio >= T → predict delivery) ===")
    delivery = [r for r in aggs if r["manual_label"] == "real_delivery"]
    nondel = [r for r in aggs if r["manual_label"] in
              ("replay", "ad", "noise")]
    print(f"delivery={len(delivery)} non_delivery={len(nondel)}")
    print(f"{'T':>5} {'TP':>4} {'FN':>4} {'FP':>4} {'TN':>4} "
          f"{'P':>6} {'R':>6} {'F1':>6}")
    for t10 in range(0, 11):
        T = t10 / 10.0
        tp = sum(1 for r in delivery if r["action_ratio"] >= T)
        fn = len(delivery) - tp
        fp = sum(1 for r in nondel if r["action_ratio"] >= T)
        tn = len(nondel) - fp
        p = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * p * rec / (p + rec)) if (p + rec) else 0.0
        print(f"{T:>5.1f} {tp:>4d} {fn:>4d} {fp:>4d} {tn:>4d} "
              f"{p:>6.2f} {rec:>6.2f} {f1:>6.2f}")


async def amain(args: argparse.Namespace) -> int:
    sessions = args.sessions or DEFAULT_SESSIONS
    rows: list[dict] = []
    for s in sessions:
        rows.extend(load_labels(s))

    rows = [r for r in rows if r.get("label") and r["label"] != "skip"]
    if args.max_clips:
        rows = rows[: args.max_clips]
    if not rows:
        print("[scout] no labeled clips found", file=sys.stderr)
        return 1
    print(f"[scout] {len(rows)} labeled clips across "
          f"{len(set(r['session'] for r in rows))} sessions")

    extracted = 0
    skipped_missing = 0
    for row in rows:
        clip_dir = DELIVERIES_ROOT / row["session"] / row["clip_id"]
        mp4 = clip_dir / "delivery_window.mp4"
        if not mp4.exists():
            row["frame_paths"] = []
            skipped_missing += 1
            continue
        frame_dir = FRAMES_DIR / row["session"] / row["clip_id"]
        try:
            row["frame_paths"] = extract_frames(
                mp4, frame_dir, args.interval)
        except Exception as e:  # noqa: BLE001
            print(f"[extract] {row['session']}/{row['clip_id']} "
                  f"failed: {e}")
            row["frame_paths"] = []
        if row["frame_paths"]:
            extracted += 1
    print(f"[extract] clips_with_frames={extracted} "
          f"missing_mp4={skipped_missing} "
          f"total_frames={sum(len(r['frame_paths']) for r in rows)}")

    rows = [r for r in rows if r["frame_paths"]]
    if args.extract_only:
        return 0

    os.environ["OPEN_SCOUT_PROMPT_VERSION"] = args.prompt_version
    rp = results_path(args.prompt_version)
    ap = aggregates_path(args.prompt_version)
    print(f"[scout] prompt_version={args.prompt_version} "
          f"results={rp.name} aggregates={ap.name}")
    await run_scout(rows, rp, concurrency=args.concurrency)

    aggs = aggregate(rp, ap)
    print(f"\n[aggregate] wrote {len(aggs)} clip rows -> {ap}")
    summarize(aggs)
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sessions", nargs="*", default=None,
                   help="session ids (default: 20260420_202239 "
                        "20260421_195050)")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_S)
    p.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    p.add_argument("--max-clips", type=int, default=0)
    p.add_argument("--extract-only", action="store_true")
    p.add_argument("--aggregate-only", action="store_true")
    p.add_argument("--prompt-version", choices=["v1", "v2"],
                   default="v1")
    args = p.parse_args()

    if args.aggregate_only:
        rp = results_path(args.prompt_version)
        ap = aggregates_path(args.prompt_version)
        aggs = aggregate(rp, ap)
        print(f"[aggregate] wrote {len(aggs)} clip rows -> {ap}")
        summarize(aggs)
        return 0
    return asyncio.run(amain(args))


if __name__ == "__main__":
    sys.exit(main())
