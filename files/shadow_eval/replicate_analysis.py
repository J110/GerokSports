"""Cross-run comparison for Scout shadow JSONs (e.g. three V6c replicates).

Loads multiple run envelopes (--runs PATH PATH PATH), optionally compares
against a baseline shadow (--baseline) for headline metrics on a shared
corpus (--corpus defaults to docs/scout_corpus_v1.json).

Emits Markdown via --out-md summarising:

  * Migration hash per run (sorted (frame_id, majority vote_cam))
  * Internal cam flip rate (within-run, 3 replicates per frame)
  * Cross-run agreement (all runs agree / 2-of-3 split / all differ)
  * Cross-run flip rate (fraction of frames where majority votes differ)

Usage (from repo ``files/``)::

    python3 shadow_eval/replicate_analysis.py \\
      --runs docs/a.json docs/b.json docs/c.json \\
      --baseline docs/shadow_run_v1.json \\
      --out-md docs/scout_v6c_replicate_analysis_autogen.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from statistics import mean

_HERE = Path(__file__).resolve().parent
_FILES = _HERE.parent
sys.path.insert(0, str(_FILES))

from shadow_eval.analyze import (  # noqa: E402
    _build_emissions,
    _build_per_frame,
    _precision_recall,
    meta_corpus_frames,
    repo_path_under_files,
)

CAM_LABELS = frozenset(
    {"bowlers_end", "closeup", "side_on", "graphic", "ad", "other", "replay"}
)


def _percentile(sorted_vals: list[float], pct: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    ix = (len(sorted_vals) - 1) * (pct / 100.0)
    lo = int(ix)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = ix - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


def aggregate_groq_metadata(rows: list[dict], variant: str) -> dict:
    """Summarise additive ``groq_*`` harness fields. Legacy envelopes
    lacking those keys yield ``has_metadata`` False."""

    rr = [r for r in rows if r.get("variant") == variant]
    if not rr:
        return {"n_rows": 0, "has_metadata": False}

    has_any = any(
        ("groq_response_id" in r or "groq_model" in r or "groq_latency_ms" in r)
        for r in rr
    )

    ids_raw = [r.get("groq_response_id") for r in rr]
    ids_nn = [x for x in ids_raw if x]

    finish = Counter(r.get("groq_finish_reason") for r in rr)
    attempts = Counter(r.get("groq_attempt_count") for r in rr)
    lat_all: list[float] = []
    lat_ok: list[float] = []
    for r in rr:
        x = r.get("groq_latency_ms")
        if isinstance(x, (int, float)):
            lat_all.append(float(x))
            if not r.get("error"):
                lat_ok.append(float(x))
    sorted_lat = sorted(lat_all)
    models = {r.get("groq_model") for r in rr}

    dup_ids = bool(len(ids_nn) != len(set(ids_nn)))

    return {
        "n_rows": len(rr),
        "has_metadata": bool(has_any),
        "groq_response_ids_non_null": len(ids_nn),
        "groq_response_id_duplicates_within_run": dup_ids,
        "groq_finish_reason": dict(finish),
        "groq_attempt_count": {str(k): v for k, v in attempts.items()},
        "groq_model_values": sorted(m for m in models if m),
        "groq_latency_ms_p50": _percentile(sorted_lat, 50.0),
        "groq_latency_ms_p95": _percentile(sorted_lat, 95.0),
        "groq_latency_ms_p99": _percentile(sorted_lat, 99.0),
        "groq_latency_ms_mean_ok_rows": float(mean(lat_ok)) if lat_ok else None,
    }


def migration_hash(votes_sorted: list[tuple[str, str | None]]) -> str:
    """Stable hash of migration pattern: sorted ``(frame_id, vote_cam)``."""
    blob = json.dumps(votes_sorted, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def load_results(path: Path) -> list[dict]:
    return json.load(path.open(encoding="utf-8"))["results"]


def per_run_per_frame(rows: list[dict], variant: str) -> dict:
    vf = [r for r in rows if r["variant"] == variant]
    return _build_per_frame(vf)


def vote_pairs(
    corpus_sorted: list[dict], per_frame: dict, variant: str,
) -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    for f in corpus_sorted:
        fid = f["frame_id"]
        key = (fid, variant)
        vc = per_frame[key]["vote_cam"] if key in per_frame else None
        out.append((fid, vc))
    return out


def internal_flip_mean(corpus: list[dict], per_frame: dict, variant: str) -> float:
    flips = [
        per_frame[(f["frame_id"], variant)]["flip_cam"]
        for f in corpus
        if (f["frame_id"], variant) in per_frame
    ]
    return float(mean(flips)) if flips else 0.0


def net_accuracy(corpus: list[dict], per_frame: dict, variant: str) -> tuple[int, int]:
    ok = 0
    for f in corpus:
        key = (f["frame_id"], variant)
        if key not in per_frame:
            continue
        if per_frame[key]["vote_cam"] == f["human_camera_view"]:
            ok += 1
    return ok, len(corpus)


def strict_bowlers_end_precision(
    per_frame: dict, corpus: list[dict], variant: str,
) -> tuple[float | None, int]:
    emissions = _build_emissions(
        corpus, per_frame, variant, subset_filter=None, use_vote=True,
    )
    pr = _precision_recall(emissions, CAM_LABELS)
    bow = pr.get("bowlers_end", {})
    p = bow.get("precision")
    n_em = bow.get("emitted", 0)
    return p, int(n_em)


def analyze_cross_runs(
    corpus_sorted: list[dict],
    run_label_and_pf: list[tuple[str, dict]],
    variant: str,
) -> dict:
    hashes: list[str] = []
    votes_by_run: list[list[tuple[str, str | None]]] = []

    for _label, pf in run_label_and_pf:
        vp = vote_pairs(corpus_sorted, pf, variant)
        votes_by_run.append(vp)
        hashes.append(migration_hash(vp))

    nf = len(corpus_sorted)
    nruns = len(votes_by_run)
    majority_histogram: dict[int, int] = {}
    cross_flip_frames = 0
    unstable_frames: list[str] = []

    for i in range(nf):
        triple = [votes_by_run[r][i][1] for r in range(nruns)]
        cross_flip_frames += int(len(set(triple)) > 1)
        ctr = Counter(triple)
        mc = max(ctr.values()) if ctr else 0
        majority_histogram[mc] = majority_histogram.get(mc, 0) + 1
        if len(set(triple)) == nruns:
            unstable_frames.append(corpus_sorted[i]["frame_id"])

    cross_flip_rate = cross_flip_frames / nf if nf else 0.0

    legacy_buckets = {}
    if nruns == 3:
        legacy_buckets = {
            "stable_all_agree": majority_histogram.get(3, 0),
            "two_of_three_agree_pattern": majority_histogram.get(2, 0),
            "all_three_differ": majority_histogram.get(1, 0),
        }

    frame_vote_matrix: dict[str, list[str | None]] = {}
    for i in range(nf):
        fid = corpus_sorted[i]["frame_id"]
        frame_vote_matrix[fid] = [votes_by_run[r][i][1] for r in range(nruns)]

    differing_detail: list[str] = []
    if len(set(hashes)) > 1:
        fid_order = [f["frame_id"] for f in corpus_sorted]
        baseline_vp = votes_by_run[0]
        for ri in range(1, len(votes_by_run)):
            for j, fid in enumerate(fid_order):
                a = baseline_vp[j][1]
                b = votes_by_run[ri][j][1]
                if a != b:
                    differing_detail.append(
                        f"`{fid}` run1→run{ri + 1}: {a!r} → {b!r}")

    return {
        "hashes": hashes,
        "nruns": nruns,
        "majority_histogram": majority_histogram,
        "legacy_three_run_buckets": legacy_buckets,
        "cross_flip_frames": cross_flip_frames,
        "cross_flip_rate": cross_flip_rate,
        "unstable_frames": unstable_frames,
        "frame_vote_matrix": frame_vote_matrix,
        "differing_detail": differing_detail[:120],
        "migration_hashes_unique": sorted(set(hashes)),
    }


def format_md(
    *,
    corpus_path: Path,
    run_paths: list[Path],
    run_labels: list[str],
    corpus_sorted: list[dict],
    variant: str,
    baselines_pf: dict | None,
    baseline_variant: str,
    per_run_stats: list[dict],
    cross: dict,
    watch_frames: tuple[str, ...],
    groq_sections: list[dict] | None = None,
) -> str:
    corpus_n = len(corpus_sorted)
    lines: list[str] = []
    o = lines.append

    o("# Replicate-run cross-analysis (autogen)")
    o("")
    try:
        crel = corpus_path.relative_to(_FILES)
    except ValueError:
        crel = corpus_path
    o(f"* **Corpus:** `{crel}` ({corpus_n} frames, sorted by frame_id)")
    o(f"* **Variant (replicates):** `{variant}`")
    if baselines_pf is not None:
        o(f"* **Baseline comparison:** `{baseline_variant}` from merged shadow baseline")
    o("")
    o("## Run inputs")
    hashes_list = cross["hashes"]
    if len(run_labels) != len(run_paths) or len(run_paths) != len(hashes_list):
        raise ValueError("run_labels / run_paths / hashes length mismatch")
    for lab, rp, hh in zip(run_labels, run_paths, hashes_list):
        try:
            rel = rp.relative_to(_FILES)
        except ValueError:
            rel = rp
        o(f"* **{lab}:** `{rel}` → `migration_hash={hh}`")
    o("")
    uniq = cross["migration_hashes_unique"]
    o("## Migration hash stability")
    o(f"* **Distinct hashes:** {len(uniq)} — {uniq}")
    o(f"* **Deterministic voting pattern across runs:** `{len(uniq) == 1}`")
    o("")
    ims = [st["internal_flip"] for st in per_run_stats]
    o("## Internal vs cross-run flip")
    o("| Run | Internal flip rate | Strict BE prec | BE emitted | Net acc |")
    o("|-----|---------------------|----------------|------------|---------|")
    for st in per_run_stats:
        spp = st["be_prec"]
        sp = f"{spp*100:.1f}%" if spp is not None else "n/a"
        o(f"| {st['label']} | {st['internal_flip']*100:.1f}% | "
          f"{sp} | {st['be_n']} | "
          f"{st['acc_ok']}/{st['acc_n']} |")
    o(f"| **Avg internal flip** | {mean(ims)*100:.2f}% | | | |")
    o("")
    cr = cross["cross_flip_rate"]
    o(f"* **Cross-run flip rate:** {cr*100:.1f}% "
      f"({cross['cross_flip_frames']} / {corpus_n} frames)")
    nr = cross.get("nruns") or len(cross["hashes"])
    mh = cross.get("majority_histogram") or {}
    o(f"* **Modal vote agreement (across {nr} runs):**")
    for k in sorted(mh.keys(), reverse=True):
        o(f"  * Plurality on **{k}/{nr}** runs: **{mh[k]}** frames")
    leg = cross.get("legacy_three_run_buckets") or {}
    if leg:
        o("* **Legacy 3-run labels (when N=3 only):**")
        o(f"  * All agree: **{leg.get('stable_all_agree', 0)}**")
        o(f"  * Two-vs-one: **{leg.get('two_of_three_agree_pattern', 0)}**")
        o(f"  * Three distinct: **{leg.get('all_three_differ', 0)}**")
    o("")
    if groq_sections:
        o("## Groq API metadata (additive row fields)")
        o("| Run | Meta? | non-null response ids | dup ids in-run? | "
          "p50 ms | p95 | p99 | mean ms (ok rows) | models | "
          "finish_reason (counts) | attempt_count (counts) |")
        o("|-----|-------|------------------------|-----------------|"
          "--------|-----|-----|------------------|--------|"
          "-------------------------|------------------------|")
        for block in groq_sections:
            lab = block["label"]
            st = block["stats"]
            if not st.get("has_metadata"):
                o(f"| {lab} | no | — | — | — | — | — | — | — | — | — |")
                continue
            fin = st.get("groq_finish_reason") or {}
            fin_s = ", ".join(f"{k}={fin[k]}" for k in sorted(fin.keys()))
            att = st.get("groq_attempt_count") or {}
            att_s = ", ".join(f"{k}={att[k]}" for k in sorted(att.keys()))
            mods = ", ".join(st.get("groq_model_values") or [])
            o(
                f"| {lab} | yes | {st.get('groq_response_ids_non_null')} | "
                f"{st.get('groq_response_id_duplicates_within_run')} | "
                f"{st.get('groq_latency_ms_p50')!s} | "
                f"{st.get('groq_latency_ms_p95')!s} | "
                f"{st.get('groq_latency_ms_p99')!s} | "
                f"{st.get('groq_latency_ms_mean_ok_rows')!s} | "
                f"`{mods}` | "
                f"{fin_s} | {att_s} |"
            )
        o("")
    if baselines_pf is not None:
        bp, bn = strict_bowlers_end_precision(baselines_pf, corpus_sorted,
                                                baseline_variant)
        bo, tn = net_accuracy(corpus_sorted, baselines_pf, baseline_variant)
        bf = internal_flip_mean(corpus_sorted, baselines_pf, baseline_variant)
        bps = f"{bp*100:.1f}%" if bp is not None else "n/a"
        o("## Baseline row (merged analysis anchors)")
        o(f"* `{baseline_variant}` strict BE precision: **{bps}** ({bn} emitted)")
        o(f"* `{baseline_variant}` net accuracy: **{bo}/{tn}**")
        o(f"* `{baseline_variant}` internal flip rate: **{bf*100:.1f}%**")
        o("")

    o("## Watch frames (votes per run)")
    m = cross["frame_vote_matrix"]
    for wf in watch_frames:
        votes = m.get(wf)
        if votes is None:
            continue
        o(f"* **`{wf}`:** " + ", ".join(f"run{r+1}={v!r}"
                                         for r, v in enumerate(votes)))
    o("")
    dist = cross.get("differing_detail") or []
    if dist:
        o("## Sample differing frames (run1 vs later runs)")
        for row in dist[:40]:
            o(f"* {row}")
        o("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--runs", nargs="+", required=True,
        help="Two or more shadow JSON envelopes "
        "(same variant rows, disjoint replicate batches).")
    ap.add_argument(
        "--corpus",
        default="docs/scout_corpus_v1.json",
        help="Corpus JSON (default: %(default)s).")
    ap.add_argument(
        "--baseline", default=None,
        help="Optional shadow_run_v1.json for V5 headline metrics.")
    ap.add_argument(
        "--variant", default="V6c",
        help="Variant key to analyse (default: %(default)s).")
    ap.add_argument(
        "--baseline-variant", default="V5",
        help="Baseline variant tag if --baseline (default: %(default)s).")
    ap.add_argument(
        "--out-md", required=True,
        help="Write Markdown summary here.")
    ap.add_argument(
        "--labels", nargs="*", default=None,
        help="Optional labels for each --runs entry (same length as --runs).")
    ns = ap.parse_args(argv)

    corp_path = repo_path_under_files(ns.corpus)
    _, corpus = meta_corpus_frames(corp_path)
    corpus_sorted = sorted(corpus, key=lambda fc: fc["frame_id"])

    run_paths = [repo_path_under_files(p) for p in ns.runs]
    variant = ns.variant

    lbls = ns.labels if ns.labels else [f"run{i}" for i in range(1, len(run_paths) + 1)]
    if len(lbls) != len(run_paths):
        raise SystemExit("--labels count must match --runs count.")

    merged_for_analysis: list[tuple[str, dict]] = []
    groq_sections: list[dict] = []
    for lab, rp in zip(lbls, run_paths):
        rows = load_results(rp)
        bad = sum(1 for r in rows if r.get("error"))
        if bad > len(rows) * 0.1:
            raise SystemExit(f"S1.3: Run {rp} error rows {bad} exceed 10%.")
        merged_for_analysis.append((lab, per_run_per_frame(rows, variant)))
        groq_sections.append({
            "label": lab,
            "stats": aggregate_groq_metadata(rows, variant),
        })

    baselines_pf: dict | None = None
    if ns.baseline:
        brow = load_results(repo_path_under_files(ns.baseline))
        baselines_pf = per_run_per_frame(brow, ns.baseline_variant)

    cross_in = analyze_cross_runs(corpus_sorted, merged_for_analysis, variant)

    per_run_stats: list[dict] = []
    for lab, pf in merged_for_analysis:
        p_be, n_be = strict_bowlers_end_precision(pf, corpus_sorted, variant)
        acc_ok, acc_n = net_accuracy(corpus_sorted, pf, variant)
        per_run_stats.append({
            "label": lab,
            "internal_flip": internal_flip_mean(corpus_sorted, pf, variant),
            "be_prec": p_be,
            "be_n": n_be,
            "acc_ok": acc_ok,
            "acc_n": acc_n,
        })

    watch = ("f941", "f748", "f205", "f942")
    text = format_md(
        corpus_path=corp_path,
        run_paths=run_paths,
        run_labels=lbls,
        corpus_sorted=corpus_sorted,
        variant=variant,
        baselines_pf=baselines_pf,
        baseline_variant=ns.baseline_variant,
        per_run_stats=per_run_stats,
        cross=cross_in,
        watch_frames=watch,
        groq_sections=groq_sections,
    )

    out = repo_path_under_files(ns.out_md)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
