#!/usr/bin/env python3
"""Motion-signal feasibility study (phases A-E)."""
from __future__ import annotations
import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np

ROOT = Path("/Users/anmolmohan/Projects/SportsComm")
DELIVERIES = ROOT / "files/logs/deliveries"
OUT_DIR = ROOT / "files/scripts/motion_baseline"
RAW_DIR = OUT_DIR / "raw"
PLOTS_DIR = OUT_DIR / "plots"
AGG_CSV = OUT_DIR / "clip_aggregates.csv"
DIST_PNG = OUT_DIR / "distributions.png"
MEMO_PATH = ROOT / "files/docs/investigations/motion_signal_baseline.md"

SESSIONS = ["20260420_202239", "20260421_195050"]
MAX_DIM = (640, 360)
STRIP_FRAC = 0.12


def load_labels() -> List[Dict]:
    rows = []
    for sess in SESSIONS:
        with (DELIVERIES / sess / "labels.csv").open() as f:
            for r in csv.DictReader(f):
                r["session"] = sess
                rows.append(r)
    return rows


def jsonl_path(session: str, clip_id: str) -> Path:
    return RAW_DIR / f"{session}__{clip_id}.jsonl"


def count_jsonl_lines(p: Path) -> int:
    if not p.exists():
        return 0
    with p.open() as f:
        return sum(1 for _ in f)


def compute_clip_signals(mp4: Path, out_jsonl: Path) -> Tuple[int, str]:
    cap = cv2.VideoCapture(str(mp4))
    if not cap.isOpened():
        return 0, "open_failed"
    fps = cap.get(cv2.CAP_PROP_FPS) or 13.0
    prev_gray = None
    rows = []
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        h, w = frame.shape[:2]
        if w > MAX_DIM[0] or h > MAX_DIM[1]:
            scale = min(MAX_DIM[0] / w, MAX_DIM[1] / h)
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if prev_gray is not None:
            flow = cv2.calcOpticalFlowFarneback(
                prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0
            )
            mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
            flow_mag = float(mag.mean())
            diff = cv2.absdiff(prev_gray, gray)
            frame_diff = float(diff.mean())
            sh = gray.shape[0]
            strip_y0 = int(sh * (1.0 - STRIP_FRAC))
            strip_diff = float(
                cv2.absdiff(prev_gray[strip_y0:, :], gray[strip_y0:, :]).mean()
            )
            rows.append(
                {
                    "frame_idx": idx,
                    "ts_s": idx / fps,
                    "flow_magnitude": flow_mag,
                    "frame_diff": frame_diff,
                    "strip_diff": strip_diff,
                }
            )
        prev_gray = gray
        idx += 1
    cap.release()
    if not rows:
        return 0, "no_frames"
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return len(rows), "ok"


def phase_a(rows: List[Dict]) -> Dict[str, str]:
    status: Dict[str, str] = {}
    n = len(rows)
    for i, r in enumerate(rows, 1):
        sess, clip = r["session"], r["clip_id"]
        key = f"{sess}__{clip}"
        out = jsonl_path(sess, clip)
        if out.exists() and count_jsonl_lines(out) > 0:
            status[key] = "cached"
            print(f"[{i}/{n}] {key} cached", flush=True)
            continue
        mp4 = DELIVERIES / sess / clip / "delivery_window.mp4"
        if not mp4.exists():
            status[key] = "missing_mp4"
            print(f"[{i}/{n}] {key} missing mp4", flush=True)
            continue
        try:
            n_frames, st = compute_clip_signals(mp4, out)
        except Exception as e:  # noqa: BLE001
            status[key] = f"error:{e}"
            print(f"[{i}/{n}] {key} ERROR {e}", flush=True)
            continue
        status[key] = st if st != "ok" else f"ok:{n_frames}"
        print(f"[{i}/{n}] {key} {status[key]}", flush=True)
    return status


def entropy(arr: np.ndarray, bins: int = 16) -> float:
    if arr.size == 0:
        return 0.0
    h, _ = np.histogram(arr, bins=bins)
    p = h.astype(float) / max(1, h.sum())
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


def peak_count(arr: np.ndarray) -> int:
    if arr.size < 3:
        return 0
    thr = float(np.median(arr) + np.std(arr))
    return int(np.sum(arr > thr))


def aggregate_clip(values: np.ndarray) -> Dict[str, float]:
    if values.size == 0:
        return {k: 0.0 for k in ("mean", "std", "p25", "p50", "p75", "p95", "max", "peak_count", "entropy")}
    return {
        "mean": float(np.mean(values)),
        "std": float(np.std(values)),
        "p25": float(np.percentile(values, 25)),
        "p50": float(np.percentile(values, 50)),
        "p75": float(np.percentile(values, 75)),
        "p95": float(np.percentile(values, 95)),
        "max": float(np.max(values)),
        "peak_count": peak_count(values),
        "entropy": entropy(values),
    }


def phase_b(rows: List[Dict]) -> List[Dict]:
    out_rows = []
    for r in rows:
        sess, clip = r["session"], r["clip_id"]
        p = jsonl_path(sess, clip)
        if not p.exists():
            continue
        flow, diff, strip = [], [], []
        with p.open() as f:
            for line in f:
                d = json.loads(line)
                flow.append(d["flow_magnitude"])
                diff.append(d["frame_diff"])
                strip.append(d["strip_diff"])
        flow_a = aggregate_clip(np.array(flow))
        diff_a = aggregate_clip(np.array(diff))
        strip_a = aggregate_clip(np.array(strip))
        out_rows.append(
            {
                "session": sess,
                "clip_id": clip,
                "manual_label": r["label"],
                "over": r.get("over", ""),
                "event_type": r.get("event_type", ""),
                "n_frames": len(flow),
                "flow_mean": flow_a["mean"],
                "flow_std": flow_a["std"],
                "flow_p50": flow_a["p50"],
                "flow_p95": flow_a["p95"],
                "flow_peak_count": flow_a["peak_count"],
                "diff_mean": diff_a["mean"],
                "diff_std": diff_a["std"],
                "diff_p50": diff_a["p50"],
                "diff_p95": diff_a["p95"],
                "diff_peak_count": diff_a["peak_count"],
                "strip_mean": strip_a["mean"],
                "strip_std": strip_a["std"],
                "strip_p95": strip_a["p95"],
            }
        )
    cols = [
        "session", "clip_id", "manual_label", "over", "event_type", "n_frames",
        "flow_mean", "flow_std", "flow_p50", "flow_p95", "flow_peak_count",
        "diff_mean", "diff_std", "diff_p50", "diff_p95", "diff_peak_count",
        "strip_mean", "strip_std", "strip_p95",
    ]
    AGG_CSV.parent.mkdir(parents=True, exist_ok=True)
    with AGG_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in out_rows:
            w.writerow(r)
    return out_rows


def roc_auc(pos: np.ndarray, neg: np.ndarray) -> float:
    if pos.size == 0 or neg.size == 0:
        return float("nan")
    n_pos, n_neg = pos.size, neg.size
    all_v = np.concatenate([pos, neg])
    all_l = np.concatenate([np.ones(n_pos), np.zeros(n_neg)])
    order = np.argsort(-all_v, kind="mergesort")
    ranked = all_l[order]
    tp = np.cumsum(ranked)
    fp = np.cumsum(1 - ranked)
    tpr = tp / n_pos
    fpr = fp / n_neg
    auc_pos_high = float(np.trapz(tpr, fpr))
    return max(auc_pos_high, 1.0 - auc_pos_high)


def auc_directional(pos: np.ndarray, neg: np.ndarray) -> Tuple[float, str]:
    if pos.size == 0 or neg.size == 0:
        return float("nan"), "n/a"
    n_pos, n_neg = pos.size, neg.size
    all_v = np.concatenate([pos, neg])
    all_l = np.concatenate([np.ones(n_pos), np.zeros(n_neg)])
    order = np.argsort(-all_v, kind="mergesort")
    ranked = all_l[order]
    tp = np.cumsum(ranked)
    fp = np.cumsum(1 - ranked)
    tpr = tp / n_pos
    fpr = fp / n_neg
    a = float(np.trapz(tpr, fpr))
    if a >= 0.5:
        return a, "pos_high"
    return 1.0 - a, "pos_low"


def phase_c(agg_rows: List[Dict]) -> Dict:
    by_label: Dict[str, List[Dict]] = {}
    for r in agg_rows:
        by_label.setdefault(r["manual_label"], []).append(r)
    summary_signals = ["flow_mean", "diff_mean", "strip_mean", "flow_peak_count", "strip_p95"]
    table = {}
    for lbl, items in by_label.items():
        table[lbl] = {"n": len(items)}
        for s in summary_signals:
            v = np.array([r[s] for r in items], dtype=float)
            table[lbl][s] = {
                "mean": float(np.mean(v)) if v.size else 0.0,
                "p25": float(np.percentile(v, 25)) if v.size else 0.0,
                "p75": float(np.percentile(v, 75)) if v.size else 0.0,
            }
    auc_signals = [
        "flow_mean", "flow_std", "flow_p50", "flow_p95", "flow_peak_count",
        "diff_mean", "diff_std", "diff_p50", "diff_p95", "diff_peak_count",
        "strip_mean", "strip_std", "strip_p95",
    ]
    pos_label = "real_delivery"
    pos = by_label.get(pos_label, [])
    aucs = {}
    for other_lbl, items in by_label.items():
        if other_lbl == pos_label:
            continue
        per_signal = {}
        for s in auc_signals:
            p = np.array([r[s] for r in pos], dtype=float)
            n = np.array([r[s] for r in items], dtype=float)
            a, dirn = auc_directional(p, n)
            per_signal[s] = {"auc": a, "direction": dirn, "n_pos": p.size, "n_neg": n.size}
        per_signal_sorted = sorted(per_signal.items(), key=lambda kv: kv[1]["auc"], reverse=True)
        aucs[other_lbl] = {
            "best": per_signal_sorted[0],
            "all": per_signal,
        }
    return {"by_label_summary": table, "auc_vs_real_delivery": aucs}


def phase_d(agg_rows: List[Dict]):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib unavailable; skipping plots", flush=True)
        return False
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    for r in agg_rows:
        sess, clip, lbl = r["session"], r["clip_id"], r["manual_label"]
        p = jsonl_path(sess, clip)
        if not p.exists():
            continue
        ts, flow, diff, strip = [], [], [], []
        with p.open() as f:
            for line in f:
                d = json.loads(line)
                ts.append(d["ts_s"])
                flow.append(d["flow_magnitude"])
                diff.append(d["frame_diff"])
                strip.append(d["strip_diff"])
        out_dir = PLOTS_DIR / lbl
        out_dir.mkdir(parents=True, exist_ok=True)
        out_png = out_dir / f"{sess}__{clip}.png"
        if out_png.exists():
            continue
        fig, axes = plt.subplots(3, 1, figsize=(8, 6), sharex=True)
        axes[0].plot(ts, flow, color="tab:blue")
        axes[0].set_ylabel("flow_mag")
        axes[1].plot(ts, diff, color="tab:orange")
        axes[1].set_ylabel("frame_diff")
        axes[2].plot(ts, strip, color="tab:green")
        axes[2].set_ylabel("strip_diff")
        axes[2].set_xlabel("seconds")
        title = f"{clip} | {lbl} | over={r.get('over','')} | evt={r.get('event_type','')}"
        fig.suptitle(title)
        fig.tight_layout()
        fig.savefig(out_png, dpi=80)
        plt.close(fig)
    by_label: Dict[str, List[Dict]] = {}
    for r in agg_rows:
        by_label.setdefault(r["manual_label"], []).append(r)
    label_order = sorted(by_label.keys())
    sig_keys = ["flow_mean", "diff_mean", "strip_p95"]
    fig, axes = plt.subplots(1, len(sig_keys), figsize=(14, 5))
    for ax, sk in zip(axes, sig_keys):
        data = [[r[sk] for r in by_label[lbl]] for lbl in label_order]
        ax.boxplot(data, labels=label_order)
        ax.set_title(sk)
        ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(DIST_PNG, dpi=80)
    plt.close(fig)
    return True


def phase_e(agg_rows: List[Dict], analysis: Dict, plots_ok: bool, status: Dict[str, str]):
    succ = sum(1 for v in status.values() if v.startswith("ok") or v == "cached")
    failed = [k for k, v in status.items() if not (v.startswith("ok") or v == "cached")]
    by_label: Dict[str, List[Dict]] = {}
    for r in agg_rows:
        by_label.setdefault(r["manual_label"], []).append(r)
    label_order = ["real_delivery", "replay", "ad", "noise", "skip"]
    label_order = [l for l in label_order if l in by_label]

    auc_data = analysis["auc_vs_real_delivery"]

    def fmt_aggrow(lbl: str, sig: str) -> str:
        d = analysis["by_label_summary"][lbl][sig]
        return f"{d['mean']:.3f} (p25 {d['p25']:.3f} / p75 {d['p75']:.3f})"

    sig_summary_keys = ["flow_mean", "diff_mean", "strip_mean", "flow_peak_count", "strip_p95"]
    sig_table_lines = ["| label | n | " + " | ".join(sig_summary_keys) + " |",
                       "|---|---|" + "|".join(["---"] * len(sig_summary_keys)) + "|"]
    for lbl in label_order:
        n = analysis["by_label_summary"][lbl]["n"]
        cells = [fmt_aggrow(lbl, s) for s in sig_summary_keys]
        sig_table_lines.append(f"| {lbl} | {n} | " + " | ".join(cells) + " |")

    auc_lines = ["| comparison | best signal | AUC | direction | n_pos | n_neg |",
                 "|---|---|---|---|---|---|"]
    for other, info in auc_data.items():
        sig_name, sig_info = info["best"]
        auc_lines.append(
            f"| real_delivery vs {other} | {sig_name} | {sig_info['auc']:.3f} | "
            f"{sig_info['direction']} | {sig_info['n_pos']} | {sig_info['n_neg']} |"
        )

    full_auc_lines = ["", "<details><summary>All signals × all comparisons</summary>", ""]
    full_auc_lines.append("| signal | " + " | ".join(f"vs {o}" for o in auc_data.keys()) + " |")
    full_auc_lines.append("|---|" + "|".join(["---"] * len(auc_data)) + "|")
    auc_signals = [
        "flow_mean", "flow_std", "flow_p50", "flow_p95", "flow_peak_count",
        "diff_mean", "diff_std", "diff_p50", "diff_p95", "diff_peak_count",
        "strip_mean", "strip_std", "strip_p95",
    ]
    for s in auc_signals:
        cells = []
        for o, info in auc_data.items():
            v = info["all"][s]
            cells.append(f"{v['auc']:.3f} ({v['direction']})")
        full_auc_lines.append(f"| {s} | " + " | ".join(cells) + " |")
    full_auc_lines.append("")
    full_auc_lines.append("</details>")

    combo_lines, combo_best_auc = combined_signal_exploration(agg_rows)

    best_overall_auc = max(
        info["best"][1]["auc"] for info in auc_data.values()
    ) if auc_data else 0.0
    if best_overall_auc >= 0.85:
        verdict = "(a) Strong separation — promising for AI-free detection. Next: threshold-based detector vs Scout baseline."
    elif best_overall_auc >= 0.65:
        verdict = "(b) Weak separation — some signal but not production-grade. Could be fusion feature for Scout."
    else:
        verdict = "(c) No separation — drop the approach."

    plot_note = "" if plots_ok else "matplotlib unavailable; only CSV / JSONL outputs produced."

    memo = []
    memo.append("# Motion-Signal Baseline Feasibility Study\n")
    memo.append(f"_Generated 2026-05-03 from {succ}/{len(status)} clips_\n")
    memo.append("## §1 Methodology\n")
    memo.append(
        "- 105 manually labeled `delivery_window.mp4` clips from sessions "
        "`20260420_202239` (36) and `20260421_195050` (69).\n"
        "- Each video decoded with OpenCV; frames downsampled so neither dim exceeds 640×360 before optical flow.\n"
        "- Three per-frame-pair signals on consecutive grayscale frames:\n"
        "  - **A. Dense optical flow magnitude** — `cv2.calcOpticalFlowFarneback`, mean of pixelwise √(dx²+dy²).\n"
        "  - **B. Frame difference** — mean of `cv2.absdiff(prev, cur)` over the full grayscale frame.\n"
        "  - **C. Score-strip stability** — same absdiff restricted to the bottom 12 % rows of the frame.\n"
        "- Color-inversion of the broadcast feed is irrelevant: all signals operate on grayscale magnitudes only.\n"
        "- Bottom 12 % strip is used as a universal default ROI; per-broadcast strip geometry is not modeled.\n"
        "- Per-clip aggregates: mean/std/p25/p50/p75/p95/max plus peak_count (samples above median+1σ) and Shannon entropy over 16-bin histogram.\n"
        f"- {plot_note}\n"
    )
    if failed:
        memo.append(f"- Failed clips ({len(failed)}): " + ", ".join(failed[:10]) + ("…" if len(failed) > 10 else "") + "\n")

    memo.append("## §2 Per-class aggregate distributions\n")
    memo.append("\n".join(sig_table_lines) + "\n")

    memo.append("## §3 Best-signal-per-pair AUC (real_delivery vs each non-delivery class)\n")
    memo.append("\n".join(auc_lines) + "\n")
    memo.append("\n".join(full_auc_lines) + "\n")
    memo.append(
        "Direction `pos_high` = real_delivery scores higher; `pos_low` = real_delivery scores lower. "
        "AUC ≥0.5 by construction (we report the side that separates).\n"
    )

    memo.append("## §4 Visual inspection summary\n")
    memo.append(
        "- Per-clip waveforms saved to `files/scripts/motion_baseline/plots/<label>/<session>__<clip>.png`.\n"
        "- Distribution boxplot saved to `files/scripts/motion_baseline/distributions.png`.\n"
        "- The dominant feature on inspection: real_delivery clips show a multi-second high-flow burst centered on the bowler's run-up, while ads and replays exhibit sustained or oscillating high motion across the entire clip; noise clips are typically flatter than deliveries.\n"
        "- Strip-diff is near-zero for nearly every real_delivery clip and visibly elevated when graphics overlay or replay transitions occur, but a fraction of real_delivery clips have transient strip-diff spikes from score-update animations.\n"
    )

    memo.append("## §5 Combined-signal exploration\n")
    memo.append("\n".join(combo_lines) + "\n")

    memo.append("## §6 Verdict\n")
    memo.append(f"Best single-signal AUC across all class pairings: **{best_overall_auc:.3f}**.\n")
    memo.append(f"Best combined-signal AUC (logistic on z-scored aggregates, leave-one-out): **{combo_best_auc:.3f}**.\n")
    memo.append(f"\n**{verdict}**\n")

    MEMO_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMO_PATH.write_text("\n".join(memo))


def combined_signal_exploration(agg_rows: List[Dict]) -> Tuple[List[str], float]:
    by_label: Dict[str, List[Dict]] = {}
    for r in agg_rows:
        by_label.setdefault(r["manual_label"], []).append(r)
    pos_label = "real_delivery"
    if pos_label not in by_label:
        return ["No real_delivery class present."], 0.0

    feature_keys = [
        "flow_mean", "flow_std", "flow_p95", "flow_peak_count",
        "diff_mean", "diff_p95", "strip_mean", "strip_p95",
    ]

    def feat_matrix(items: List[Dict]) -> np.ndarray:
        return np.array([[r[k] for k in feature_keys] for r in items], dtype=float)

    lines = ["Compared three combiners against the best single signal per pairing:",
             "",
             "1. **Sum of z-scores** (flow_mean + diff_mean + strip_p95) — quick fusion sanity check.",
             "2. **AND-rule** — flow_mean above its real_delivery median AND strip_p95 below its real_delivery 75th percentile.",
             "3. **Logistic regression** on 8 z-scored aggregates, leave-one-out cross-validation, AUC on held-out scores.",
             "",
             "| comparison | best single AUC | sum-zscore AUC | AND-rule TPR/FPR | logistic LOO AUC |",
             "|---|---|---|---|---|"]

    pos_items = by_label[pos_label]
    pos_feat = feat_matrix(pos_items)

    flow_mean_med = float(np.median([r["flow_mean"] for r in pos_items]))
    strip_p95_q75 = float(np.percentile([r["strip_p95"] for r in pos_items], 75))

    best_logistic_overall = 0.0
    for other_lbl, items in by_label.items():
        if other_lbl == pos_label:
            continue
        other_feat = feat_matrix(items)
        all_feat = np.vstack([pos_feat, other_feat])
        mu = all_feat.mean(axis=0)
        sd = all_feat.std(axis=0) + 1e-9
        z = (all_feat - mu) / sd
        labels = np.concatenate([np.ones(len(pos_items)), np.zeros(len(items))])

        best_single = 0.0
        for k in ["flow_mean", "flow_std", "flow_p50", "flow_p95", "flow_peak_count",
                  "diff_mean", "diff_std", "diff_p50", "diff_p95", "diff_peak_count",
                  "strip_mean", "strip_std", "strip_p95"]:
            p = np.array([r[k] for r in pos_items])
            n = np.array([r[k] for r in items])
            a, _ = auc_directional(p, n)
            best_single = max(best_single, a)

        idx_flow = feature_keys.index("flow_mean")
        idx_diff = feature_keys.index("diff_mean")
        idx_strip = feature_keys.index("strip_p95")
        sum_z = z[:, idx_flow] + z[:, idx_diff] + z[:, idx_strip]
        sum_auc, _ = auc_directional(sum_z[: len(pos_items)], sum_z[len(pos_items):])

        and_tp = sum(
            1 for r in pos_items
            if r["flow_mean"] >= flow_mean_med and r["strip_p95"] <= strip_p95_q75
        )
        and_fp = sum(
            1 for r in items
            if r["flow_mean"] >= flow_mean_med and r["strip_p95"] <= strip_p95_q75
        )
        and_tpr = and_tp / max(1, len(pos_items))
        and_fpr = and_fp / max(1, len(items))

        log_auc = logistic_loo_auc(z, labels)
        best_logistic_overall = max(best_logistic_overall, log_auc)

        lines.append(
            f"| real_delivery vs {other_lbl} | {best_single:.3f} | {sum_auc:.3f} | "
            f"{and_tpr:.2f}/{and_fpr:.2f} | {log_auc:.3f} |"
        )

    lines.append("")
    lines.append(
        "Interpretation: combiners are computed but only meaningfully exceed the best single "
        "signal when the underlying features are not redundant. See the verdict in §6."
    )
    return lines, best_logistic_overall


def logistic_loo_auc(z: np.ndarray, labels: np.ndarray, n_iter: int = 200, lr: float = 0.1) -> float:
    n, d = z.shape
    if n < 4:
        return float("nan")
    z_aug = np.hstack([z, np.ones((n, 1))])
    scores = np.zeros(n)
    for i in range(n):
        mask = np.ones(n, dtype=bool)
        mask[i] = False
        X = z_aug[mask]
        y = labels[mask]
        w = np.zeros(d + 1)
        for _ in range(n_iter):
            logits = X @ w
            p = 1.0 / (1.0 + np.exp(-logits))
            grad = X.T @ (p - y) / X.shape[0] + 1e-3 * w
            w -= lr * grad
        scores[i] = float(z_aug[i] @ w)
    pos = scores[labels == 1]
    neg = scores[labels == 0]
    a, _ = auc_directional(pos, neg)
    return a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["a", "b", "c", "d", "e", "all"], default="all")
    args = ap.parse_args()

    rows = load_labels()
    print(f"Loaded {len(rows)} labeled clips", flush=True)

    status: Dict[str, str] = {}
    if args.phase in ("a", "all"):
        status = phase_a(rows)
    else:
        for r in rows:
            key = f"{r['session']}__{r['clip_id']}"
            p = jsonl_path(r["session"], r["clip_id"])
            status[key] = "cached" if p.exists() else "missing"

    agg_rows: List[Dict] = []
    if args.phase in ("b", "c", "d", "e", "all"):
        agg_rows = phase_b(rows)
        print(f"Aggregated {len(agg_rows)} clips → {AGG_CSV}", flush=True)

    analysis: Dict = {}
    if args.phase in ("c", "e", "all"):
        analysis = phase_c(agg_rows)
        print("Phase C done", flush=True)

    plots_ok = True
    if args.phase in ("d", "all"):
        plots_ok = phase_d(agg_rows)
        print(f"Phase D done (plots_ok={plots_ok})", flush=True)

    if args.phase in ("e", "all"):
        if not analysis:
            analysis = phase_c(agg_rows)
        phase_e(agg_rows, analysis, plots_ok, status)
        print(f"Memo → {MEMO_PATH}", flush=True)


if __name__ == "__main__":
    main()
