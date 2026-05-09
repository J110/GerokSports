"""Part B shadow-run analysis.

Computes, per variant (V0/V1/V2a/V2b/V3):
  * Strict precision by cam tag (of emitted, what fraction match human label)
  * Coverage-weighted precision (weighted by Scout's pipeline-wide emission
    volume from the 5-session A3 audit)
  * Recall by human label (of human-labeled X, fraction Scout emits X)
  * Per-subset precision/recall breakdown
  * Replicate flip rate (proxy for Scout variance)
  * Emission distribution shift vs V0 baseline

V0 = Scout's current baseline (scout_cam_original in corpus).  V1-V3 come
from the shadow run JSON.

Corpus/shadow/output paths configurable via CLI (defaults preserve
prior behaviour).

Comparison mode: ``--baseline-shadow OLD.json --shadow NEW.json``
replaces variants present in NEW (e.g. a V6c-only rerun) onto rows
from OLD so V5 is preserved alongside fresh V6c.

Usage:
    python3 shadow_eval/analyze.py
    python3 shadow_eval/analyze.py --shadow docs/shadow_run_v6c_TS.json \\
        --baseline-shadow docs/shadow_run_v1.json --variants V5,V6c \\
        --out-md docs/scout_shadow_compare_v6c.md
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from statistics import mean

_HERE = Path(__file__).resolve().parent
_FILES = _HERE.parent
sys.path.insert(0, str(_FILES))

DEFAULT_CORPUS = _FILES / "docs" / "scout_corpus_v1.json"
DEFAULT_SHADOW = _FILES / "docs" / "shadow_run_v1.json"
DEFAULT_OUT_MD = _FILES / "docs" / "scout_shadow_run_v1_analysis.md"

DEFAULT_VARIANTS = ["V1", "V2a", "V2b", "V3", "V4", "V4b", "V5", "V6c", "V6d", "V6e"]

# Scout's pipeline-wide emission distribution from the A3 audit
# (5 sessions, 408 camera_view emissions total).  Used as weights for
# coverage-weighted precision so single-bucket gains are not
# over-credited.
COVERAGE_WEIGHTS = {
    "bowlers_end": 342 / 408,  # 83.8%
    "closeup":      55 / 408,  # 13.5%
    "graphic":       7 / 408,  # 1.7%
    "other":         3 / 408,  # 0.7%
    "ad":            1 / 408,  # 0.2%
    "side_on":       0 / 408,  # 0.0%
    "replay":        0 / 408,  # 0.0%
}


def repo_path_under_files(p: str | Path, files_root: Path = _FILES) -> Path:
    path = Path(p)
    return path if path.is_absolute() else (files_root / path)


def merge_shadow_overlay(baseline_rows: list[dict],
                         overlay_rows: list[dict],
                         ) -> list[dict]:
    """Variants present in overlay replace all rows with that variant name
    from baseline — used to overlay a fresh ``V6c`` run atop
    ``shadow_run_v1.json`` without rewriting the baseline file."""
    overlay_vars = {r["variant"] for r in overlay_rows}
    stripped = [r for r in baseline_rows if r["variant"] not in overlay_vars]
    return stripped + list(overlay_rows)


def meta_corpus_frames(corpus_path: Path) -> tuple[str, list[dict]]:
    raw = json.load(corpus_path.open(encoding="utf-8"))
    return raw.get("version", "?"), raw["frames"]


def load_corpus_and_shadow(corpus_path: Path,
                           shadow_primary_path: Path,
                           baseline_shadow_path: Path | None,
                           ) -> tuple[list[dict], list[dict]]:
    _, corpus = meta_corpus_frames(corpus_path)
    overlay = json.load(shadow_primary_path.open(encoding="utf-8"))["results"]
    if baseline_shadow_path is not None:
        base = json.load(baseline_shadow_path.open(encoding="utf-8"))["results"]
        shadow = merge_shadow_overlay(base, overlay)
    else:
        shadow = overlay
    return corpus, shadow



def _majority_vote(cams: list[str | None]) -> str | None:
    """Pick the most common non-None tag across replicates; tie-breaks
    by arbitrary Counter ordering but results are stable since input is
    deterministic (temperature=0)."""
    non_null = [c for c in cams if c is not None]
    if not non_null:
        return None
    return Counter(non_null).most_common(1)[0][0]


def _variants_supported(per_frame: dict[tuple[str, str], dict],
                        corpus: list[dict],
                        candidates: list[str],
                        ) -> list[str]:
    """Keep only variants with a row for every corpus frame."""
    out: list[str] = []
    for v in candidates:
        if all((fc["frame_id"], v) in per_frame for fc in corpus):
            out.append(v)
        else:
            print(f"[analyze.py] SKIP variant missing rows: {v}", file=sys.stderr)
    return out


def _build_per_frame(shadow: list[dict]) -> dict:
    """Return {(frame_id, variant): {"reps": [..cam..], "vote": cam}}."""
    out: dict[tuple[str, str], dict] = {}
    for r in shadow:
        key = (r["frame_id"], r["variant"])
        out.setdefault(key, {"reps_cam": [], "reps_phase": []})
        out[key]["reps_cam"].append(r["canon_camera_view"])
        out[key]["reps_phase"].append(r["canon_frame_phase"])
    for v in out.values():
        v["vote_cam"] = _majority_vote(v["reps_cam"])
        v["vote_phase"] = _majority_vote(v["reps_phase"])
        v["flip_cam"] = 1 if len(set(v["reps_cam"])) > 1 else 0
        v["flip_phase"] = 1 if len(set(v["reps_phase"])) > 1 else 0
    return out


def _precision_recall(emissions: list[tuple[str, str]],
                      labels: set[str]) -> dict:
    """emissions: list of (predicted, truth).  Returns per-label
    precision, recall, and counts."""
    out: dict[str, dict] = {}
    for lbl in labels:
        emitted = [(p, t) for p, t in emissions if p == lbl]
        truthed = [(p, t) for p, t in emissions if t == lbl]
        tp = [e for e in emitted if e[1] == lbl]
        out[lbl] = {
            "emitted": len(emitted),
            "truth": len(truthed),
            "tp": len(tp),
            "precision": (len(tp) / len(emitted)) if emitted else None,
            "recall": (len(tp) / len(truthed)) if truthed else None,
        }
    return out


def _coverage_weighted_precision(per_label: dict[str, dict]) -> float:
    """Weight each label's precision by Scout's pipeline-wide share of
    emissions for that label.  Missing / None precision (label not
    emitted by variant) is treated as 1.0 (no harm from absence) to
    match "coverage precision = fraction of pipeline emissions that
    would be correct"."""
    num = 0.0
    denom = 0.0
    for lbl, w in COVERAGE_WEIGHTS.items():
        if w == 0:
            continue
        p = per_label.get(lbl, {}).get("precision")
        if p is None:
            continue
        num += w * p
        denom += w
    return num / denom if denom else 0.0


def _build_emissions(corpus, per_frame, variant: str,
                     subset_filter: str | None = None,
                     use_vote: bool = True) -> list[tuple[str, str]]:
    """Return list of (predicted, truth) for the given variant.

    `use_vote=True` uses majority-vote cam across replicates; False
    expands each replicate as its own row (for variance analysis).
    """
    frames_by_id = {f["frame_id"]: f for f in corpus}
    emissions: list[tuple[str, str]] = []
    for f in corpus:
        if subset_filter and f["subset"] != subset_filter:
            continue
        key = (f["frame_id"], variant)
        if key not in per_frame:
            continue
        rec = per_frame[key]
        truth = f["human_camera_view"]
        if use_vote:
            pred = rec["vote_cam"]
            if pred is not None:
                emissions.append((pred, truth))
        else:
            for pred in rec["reps_cam"]:
                if pred is not None:
                    emissions.append((pred, truth))
    return emissions


def _baseline_emissions(corpus, subset_filter: str | None = None,
                        ) -> list[tuple[str, str]]:
    """V0 = Scout's original tag on the captured frames."""
    out = []
    for f in corpus:
        if subset_filter and f["subset"] != subset_filter:
            continue
        out.append((f["scout_cam_original"], f["human_camera_view"]))
    return out


def _fmt_pct(x: float | None, n: int | None = None) -> str:
    if x is None:
        return "n/a"
    s = f"{x*100:.1f}%"
    if n is not None:
        return f"{s} ({n})"
    return s


def run_analysis(*,
                 corpus_path: Path,
                 shadow_paths_md: str,
                 corpus_meta_version: str,
                 corpus: list[dict],
                 shadow: list[dict],
                 variant_order: list[str],
                 out_md: Path,
                 ) -> str:
    per_frame = _build_per_frame(shadow)
    variants = _variants_supported(per_frame, corpus, variant_order)
    if not variants:
        raise SystemExit(
            "[analyze.py] ERROR: no variant has complete rows for "
            "every corpus frame; check shadow JSON merges.")
    cam_labels = {"bowlers_end", "closeup", "side_on", "graphic",
                  "ad", "other", "replay"}
    subsets = sorted({f["subset"] for f in corpus})

    lines: list[str] = []
    p = lines.append

    p("# Part B shadow-run v1 — analysis")
    p("")
    try:
        corpus_rel = corpus_path.relative_to(_FILES)
    except ValueError:
        corpus_rel = corpus_path
    p(f"Corpus: `{corpus_rel}` "
      f"(v{corpus_meta_version}, {len(corpus)} frames)")
    p(f"Shadow inputs: {shadow_paths_md} — **`{len(shadow)}`** API result rows.")
    p("")
    p("Baseline (V0) = `scout_cam_original` stored in the corpus (what "
      "Scout emitted on the live RC9 run).  V1–V3 = majority-vote cam "
      "across 3 replicates at temperature=0.")
    p("")

    # Build all emissions once (majority-vote).
    per_variant_em = {v: _build_emissions(corpus, per_frame, v)
                      for v in variants}
    per_variant_em["V0"] = _baseline_emissions(corpus)

    # ------------------------------------------------------------
    # Table 1: Precision per cam tag (strict + coverage-weighted)
    # ------------------------------------------------------------
    p("## 1. Precision by camera_view tag")
    p("")
    p("Strict precision: of frames the variant tagged X, fraction where "
      "the human label is X.  N = frames emitted by the variant.")
    p("")
    p("| Variant | bowlers_end | closeup | side_on | graphic | other | ad | replay | Coverage-weighted |")
    p("|---|---|---|---|---|---|---|---|---|")
    rows_for_summary = {}
    for v in ["V0"] + variants:
        pr = _precision_recall(per_variant_em[v], cam_labels)
        cwp = _coverage_weighted_precision(pr)
        rows_for_summary[v] = {"pr": pr, "cwp": cwp}
        row = [v]
        for lbl in ("bowlers_end", "closeup", "side_on", "graphic",
                    "other", "ad", "replay"):
            n = pr[lbl]["emitted"]
            row.append(_fmt_pct(pr[lbl]["precision"], n))
        row.append(_fmt_pct(cwp))
        p("| " + " | ".join(row) + " |")
    p("")
    p("Coverage-weighted precision is the sum of per-label precision "
      "weighted by Scout's pipeline-wide emission share for that label "
      "(from the 5-session A3 audit: bowlers_end 83.8%, closeup 13.5%, "
      "graphic 1.7%, other/ad 0.9%).  It estimates how much of Scout's "
      "real-world emission volume the variant would get right.")
    p("")

    # ------------------------------------------------------------
    # Table 2: Recall per human label
    # ------------------------------------------------------------
    p("## 2. Recall by human label")
    p("")
    p("Of frames HUMAN-labeled X, fraction the variant tagged X.  "
      "N = number of human-labeled frames with that label.")
    p("")
    human_counts = Counter(f["human_camera_view"] for f in corpus)
    header_labels = [l for l, _ in human_counts.most_common()]
    p("| Variant | " + " | ".join(
        f"{l} (N={human_counts[l]})" for l in header_labels) + " |")
    p("|---|" + "|".join("---" for _ in header_labels) + "|")
    for v in ["V0"] + variants:
        pr = rows_for_summary[v]["pr"]
        row = [v]
        for l in header_labels:
            row.append(_fmt_pct(pr[l]["recall"]))
        p("| " + " | ".join(row) + " |")
    p("")

    # ------------------------------------------------------------
    # Table 3: Emission distribution (where does each variant put things?)
    # ------------------------------------------------------------
    p("## 3. Emission distribution (cam counts per variant)")
    p("")
    p(f"Where does each variant place the {len(corpus)} frames?")
    p("")
    dists: dict[str, Counter] = {}
    for v in ["V0"] + variants:
        d = Counter()
        if v == "V0":
            for f in corpus:
                d[f["scout_cam_original"]] += 1
        else:
            for f in corpus:
                rec = per_frame.get((f["frame_id"], v))
                if rec:
                    d[rec["vote_cam"] or "__null__"] += 1
        dists[v] = d
    all_labels = sorted({l for d in dists.values() for l in d})
    p("| Variant | " + " | ".join(all_labels) + " |")
    p("|---|" + "|".join("---" for _ in all_labels) + "|")
    for v in ["V0"] + variants:
        row = [v] + [str(dists[v].get(l, 0)) for l in all_labels]
        p("| " + " | ".join(row) + " |")
    p("")

    # ------------------------------------------------------------
    # Table 4: Per-subset precision (bowlers_end only, most actionable)
    # ------------------------------------------------------------
    p("## 4. Per-subset `bowlers_end` precision")
    p("")
    p("Strict precision on bowlers_end tag, broken out by corpus "
      "subset.  N in each cell = frames the variant tagged bowlers_end "
      "within that subset.")
    p("")
    p("| Variant | " + " | ".join(subsets) + " | overall |")
    p("|---|" + "|".join("---" for _ in subsets) + "|---|")
    for v in ["V0"] + variants:
        row = [v]
        for s in subsets:
            em = (_baseline_emissions(corpus, s) if v == "V0"
                  else _build_emissions(corpus, per_frame, v, s))
            pr = _precision_recall(em, {"bowlers_end"})
            be = pr["bowlers_end"]
            row.append(_fmt_pct(be["precision"], be["emitted"]))
        em = per_variant_em[v]
        pr = _precision_recall(em, {"bowlers_end"})
        be = pr["bowlers_end"]
        row.append(_fmt_pct(be["precision"], be["emitted"]))
        p("| " + " | ".join(row) + " |")
    p("")

    # ------------------------------------------------------------
    # Table 5: Per-subset `bowlers_end` recall
    # ------------------------------------------------------------
    p("## 5. Per-subset `bowlers_end` recall (human-labeled denominator)")
    p("")
    p("Of HUMAN-labeled bowlers_end frames in each subset, fraction the "
      "variant tagged bowlers_end.  Recall denominator is small for "
      "non-active-play subsets because human-labeled bowlers_end frames "
      "concentrate in `active_play_recall`.")
    p("")
    p("| Variant | " + " | ".join(subsets) + " | overall |")
    p("|---|" + "|".join("---" for _ in subsets) + "|---|")
    for v in ["V0"] + variants:
        row = [v]
        for s in subsets:
            em = (_baseline_emissions(corpus, s) if v == "V0"
                  else _build_emissions(corpus, per_frame, v, s))
            pr = _precision_recall(em, {"bowlers_end"})
            be = pr["bowlers_end"]
            row.append(_fmt_pct(be["recall"], be["truth"]))
        em = per_variant_em[v]
        pr = _precision_recall(em, {"bowlers_end"})
        be = pr["bowlers_end"]
        row.append(_fmt_pct(be["recall"], be["truth"]))
        p("| " + " | ".join(row) + " |")
    p("")

    # ------------------------------------------------------------
    # Table 6: Replicate variance
    # ------------------------------------------------------------
    p("## 6. Replicate variance (Scout stability)")
    p("")
    p("Fraction of frames where the variant produced >1 distinct "
      "camera_view across its 3 replicates.  High values indicate Scout "
      "is uncertain — flagging potential boundary cases the prompt "
      "doesn't fully resolve.")
    p("")
    p("| Variant | cam flip rate | phase flip rate |")
    p("|---|---|---|")
    for v in variants:
        cam_flip = mean([per_frame[(fc["frame_id"], v)]["flip_cam"]
                         for fc in corpus])
        ph_flip = mean([per_frame[(fc["frame_id"], v)]["flip_phase"]
                        for fc in corpus])
        p(f"| {v} | {cam_flip*100:.1f}% | {ph_flip*100:.1f}% |")
    p("")

    # ------------------------------------------------------------
    # Table 7: Human-labeled bowlers_end recall floor (strict)
    # ------------------------------------------------------------
    p("## 7. Recall floor on HUMAN-labeled bowlers_end (strict)")
    p("")
    hbe_frames = [f for f in corpus
                  if f["human_camera_view"] == "bowlers_end"]
    hbe_n = len(hbe_frames)
    p(f"N = {len(hbe_frames)} human-labeled bowlers_end frames: "
      f"{', '.join(f['frame_id'] for f in hbe_frames)}")
    p("")
    p("| Variant | caught | missed | recall |")
    p("|---|---|---|---|")
    for v in ["V0"] + variants:
        caught = []
        missed = []
        for f in hbe_frames:
            if v == "V0":
                pred = f["scout_cam_original"]
            else:
                rec = per_frame.get((f["frame_id"], v))
                pred = rec["vote_cam"] if rec else None
            if pred == "bowlers_end":
                caught.append(f["frame_id"])
            else:
                missed.append((f["frame_id"], pred))
        p(f"| {v} | {len(caught)} "
          f"({', '.join(caught) or '-'}) | {len(missed)} "
          f"({', '.join(f'{fid}→{p}' for fid, p in missed) or '-'}) | "
          f"{_fmt_pct(len(caught)/len(hbe_frames))} |")
    p("")

    # ------------------------------------------------------------
    # Table 8: Frame_phase precision on bowlers_end-tagged frames
    # ------------------------------------------------------------
    p("## 8. `frame_phase` precision when variant tagged bowlers_end")
    p("")
    p("Of frames the variant tagged `bowlers_end` where the human label "
      "is also `bowlers_end`, fraction whose `frame_phase` matches the "
      "human phase.  Phase comparison is case-insensitive equality on "
      "the vote_phase; `None` phase counts as mismatch.")
    p("")
    p("| Variant | phase matches / TP frames |")
    p("|---|---|")
    for v in variants:
        tp = [f for f in corpus
              if f["human_camera_view"] == "bowlers_end"
              and per_frame.get((f["frame_id"], v), {}).get(
                  "vote_cam") == "bowlers_end"]
        ok = [f for f in tp
              if per_frame[(f["frame_id"], v)]["vote_phase"]
                  == f["human_frame_phase"]]
        frac = len(ok)/len(tp) if tp else None
        p(f"| {v} | {len(ok)}/{len(tp)} = {_fmt_pct(frac)} |")
    p("")

    # ------------------------------------------------------------
    # Decision summary
    # ------------------------------------------------------------
    p("## 9. Decision summary")
    p("")
    p("Precision targets: ≥90% strict bowlers_end precision + "
      "coverage-weighted ≥90%.  Recall floor: ≥90% strict recall on "
      f"human-labeled bowlers_end frames (N={hbe_n}).")
    p("")
    p("| Variant | BE strict prec | BE recall (strict, "
      f"N={hbe_n}) | "
      "Coverage-wtd | Cam flip rate | Meets targets? |")
    p("|---|---|---|---|---|---|")
    for v in ["V0"] + variants:
        em = per_variant_em[v]
        pr = _precision_recall(em, {"bowlers_end"})
        be = pr["bowlers_end"]
        prec = be["precision"]
        caught = 0
        for fr in hbe_frames:
            if v == "V0":
                if fr["scout_cam_original"] == "bowlers_end":
                    caught += 1
            else:
                rc = per_frame.get((fr["frame_id"], v))
                if rc and rc["vote_cam"] == "bowlers_end":
                    caught += 1
        rec_val = caught / len(hbe_frames) if hbe_frames else None
        cwp = rows_for_summary[v]["cwp"]
        if v == "V0":
            flip = "n/a"
        else:
            fr = mean([per_frame[(fc["frame_id"], v)]["flip_cam"]
                       for fc in corpus])
            flip = f"{fr*100:.1f}%"
        meets = ((prec or 0) >= 0.90 and (rec_val or 0) >= 0.90
                 and cwp >= 0.90)
        p(f"| {v} | {_fmt_pct(prec, be['emitted'])} | "
          f"{_fmt_pct(rec_val)} ({caught}/{len(hbe_frames)}) | "
          f"{_fmt_pct(cwp)} | {flip} | "
          f"{'yes' if meets else 'no'} |")
    p("")

    text = "\n".join(lines)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(text + "\n", encoding="utf-8")
    try:
        out_rel = out_md.relative_to(_FILES)
    except ValueError:
        out_rel = out_md
    print(f"Wrote {out_rel}")
    print("\n=== Quick preview ===")
    print("\n".join(lines[:60]))
    return text


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--corpus",
        type=str,
        default=str(DEFAULT_CORPUS.relative_to(_FILES)),
        help="Corpus JSON (default docs/scout_corpus_v1.json)",
    )
    ap.add_argument(
        "--shadow",
        type=str,
        default=str(DEFAULT_SHADOW.relative_to(_FILES)),
        help="Primary shadow JSON rows (fresh V6c-only run overlays "
             "baseline when combined with --baseline-shadow)",
    )
    ap.add_argument(
        "--baseline-shadow",
        type=str,
        default=None,
        help="Optional baseline JSON: variants overlapping --shadow "
             "are replaced row-for-row",
    )
    ap.add_argument(
        "--out-md",
        type=str,
        default=str(DEFAULT_OUT_MD.relative_to(_FILES)),
        help="Analysis markdown destination",
    )
    ap.add_argument(
        "--variants",
        type=str,
        default=None,
        help="Comma-separated variants to score (default: full ladder)",
    )
    ns = ap.parse_args(argv)

    corp_path = repo_path_under_files(ns.corpus)
    shadow_primary = repo_path_under_files(ns.shadow)
    baseline = (repo_path_under_files(ns.baseline_shadow)
                if ns.baseline_shadow else None)
    corpus_meta_version, corpus = meta_corpus_frames(corp_path)
    _, shadow = load_corpus_and_shadow(corp_path, shadow_primary,
                                       baseline)
    variant_order = (
        [v.strip() for v in ns.variants.split(",") if v.strip()]
        if ns.variants else list(DEFAULT_VARIANTS))
    md_parts = []
    if baseline is None:
        md_parts.append(f"`{shadow_primary.relative_to(_FILES)}`")
    else:
        md_parts.append(
            f"overlay `{shadow_primary.relative_to(_FILES)}` on "
            f"`{baseline.relative_to(_FILES)}`")
    run_analysis(
        corpus_path=corp_path,
        shadow_paths_md="; ".join(md_parts),
        corpus_meta_version=corpus_meta_version,
        corpus=corpus,
        shadow=shadow,
        variant_order=variant_order,
        out_md=repo_path_under_files(ns.out_md),
    )


if __name__ == "__main__":
    main()

