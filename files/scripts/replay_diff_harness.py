"""Differential-testing harness: pipeline UIBallSnapshot stream vs
Cricbuzz ground-truth UIBallSnapshot stream.

Inputs:
  --pipeline       JSONL emitted by replay_captured_scout_trace.py
                   --snapshot-output
  --ground-truth   JSONL emitted by ingest_cricbuzz_ground_truth.py

Output:
  --report         Markdown file with four sections:
                   1. Per-surface incident count summary
                   2. Per-ball divergences
                   3. Conservation invariants
                   4. Unclassified divergences

Spec: files/docs/investigations/differential_testing_methodology_design.md §2.4.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SCALAR_FIELDS = (
    "score", "wickets", "balls_total",
    "striker_name", "striker_runs", "striker_balls",
    "striker_fours", "striker_sixes",
    "non_striker_name", "non_striker_runs", "non_striker_balls",
    "non_striker_fours", "non_striker_sixes",
    "bowler_name", "bowler_overs", "bowler_runs", "bowler_wickets",
    "partnership_runs", "partnership_balls",
    "extras_total", "extras_wd", "extras_nb", "extras_b", "extras_lb",
)
LIST_FIELDS = ("this_over_tokens", "recent_over_n_minus_1", "fow_entries")

WICKET_TOKENS = {"W", "w", "Wd+W", "WD+W", "nb+W", "NB+W"}


@dataclass
class Divergence:
    over_ball: str
    field: str
    pipeline_value: Any
    ground_truth_value: Any
    surface: str | None = None


@dataclass
class DiffReport:
    matched_balls: int = 0
    missing_in_pipeline: list[str] = field(default_factory=list)
    phantom_in_pipeline: list[str] = field(default_factory=list)
    divergences: list[Divergence] = field(default_factory=list)
    surface_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    surface_examples: dict[str, str] = field(default_factory=dict)
    conservation_failures: list[str] = field(default_factory=list)


def _load_jsonl(path: Path) -> "OrderedDict[tuple, dict]":
    out: OrderedDict[tuple, dict] = OrderedDict()
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            ob = r.get("over_ball")
            if ob is None:
                continue
            key = (ob, int(r.get("event_index") or 0))
            out[key] = r
    return out


def _key_str(k: tuple) -> str:
    ob, idx = k
    return ob if idx == 0 else f"{ob}#{idx}"


def _is_wicket_token(tok: str) -> bool:
    if not tok:
        return False
    if tok in WICKET_TOKENS:
        return True
    return "W" in tok and tok != "Wd"


def _classify(div: Divergence, *, pipeline_ball: dict | None,
              gt_ball: dict | None) -> str | None:
    f = div.field
    pv, gv = div.pipeline_value, div.ground_truth_value

    if f == "this_over_tokens":
        gv_list = gv or []
        pv_list = pv or []
        gv_has_w = any(_is_wicket_token(t) for t in gv_list)
        pv_has_w = any(_is_wicket_token(t) for t in pv_list)
        if gv_has_w and not pv_has_w:
            # Plain-W missing-in-pipeline → C21b (the symbol-revert
            # surface): pipeline either dropped the W or replaced it
            # with a run/dot token. Compound-with-wicket-token only
            # when the ONLY W-bearing token is a compound form.
            has_plain_w = any(t in ("W", "w") for t in gv_list)
            has_compound_w = any(
                t in ("Wd+W", "nb+W", "WD+W", "NB+W") for t in gv_list)
            if has_plain_w:
                return "C21b-symbol-revert"
            if has_compound_w:
                return "Compound-with-wicket-token"
        if len(pv_list) < len(gv_list):
            return "Multi-ball-compression"

    if f == "bowler_name" and pv != gv:
        return "F-B-ad-occlusion"
    if f == "bowler_overs":
        return "F-A-commit-lag"

    if f in ("striker_fours", "striker_sixes"):
        if isinstance(pv, int) and isinstance(gv, int) and pv > gv:
            if pipeline_ball and gt_ball:
                if pipeline_ball.get("score") == gt_ball.get("score"):
                    return "Boundary-counter-double-increment"

    if f == "striker_name":
        if gt_ball and gt_ball.get("wickets", 0) > 0:
            return "D-post-FoW-striker"

    if f == "score":
        if isinstance(pv, int) and isinstance(gv, int) and pv > gv:
            tokens = (gt_ball.get("this_over_tokens") or []) if gt_ball else []
            last = tokens[-1] if tokens else ""
            if last not in ("4", "6", "4+W", "6+W"):
                return "E2-phantom-runs"

    if f == "fow_entries":
        return "E3-wicket-frame-misalign"

    if f == "recent_over_n_minus_1":
        if (not pv) and gv:
            return "Recent-overs-drop"

    if f.startswith("extras_") and isinstance(pv, int) and isinstance(gv, int) and pv < gv:
        return "Extras-counter-drop"

    if f == "bowler_wickets" and isinstance(pv, int) and isinstance(gv, int) and pv < gv:
        return "Bowler-W-credit-failure"

    return None


def _check_conservation(pipeline_ball: dict, gt_ball: dict | None) -> list[str]:
    """Per-batter-ledger conservation. Two checks:
      - striker+non+extras > team_score (impossible — partial sum can't
        exceed total)
      - team_score divergence vs GT exceeds extras_wd + extras_nb (a
        phantom-runs heuristic at the snapshot level)
    """
    fails = []
    score = pipeline_ball.get("score") or 0
    extras = pipeline_ball.get("extras_total") or 0
    ob = pipeline_ball.get("over_ball")
    if extras > score:
        fails.append(
            f"{ob}: extras_total({extras}) > score({score})")
    sr = pipeline_ball.get("striker_runs") or 0
    nr = pipeline_ball.get("non_striker_runs") or 0
    if sr + nr + extras > score:
        fails.append(
            f"{ob}: striker({sr})+non_striker({nr})+extras({extras}) "
            f"= {sr+nr+extras} > score({score})")
    if gt_ball is not None:
        gt_score = gt_ball.get("score") or 0
        if score - gt_score > 3:
            fails.append(
                f"{ob}: pipeline score({score}) exceeds GT({gt_score}) "
                f"by {score - gt_score}")
    return fails


def diff(pipeline_path: Path, ground_truth_path: Path) -> DiffReport:
    pipe = _load_jsonl(pipeline_path)
    gt = _load_jsonl(ground_truth_path)
    rep = DiffReport()

    all_keys = list(OrderedDict.fromkeys(list(gt.keys()) + list(pipe.keys())))
    for key in all_keys:
        p = pipe.get(key)
        g = gt.get(key)
        if p is None and g is not None:
            rep.missing_in_pipeline.append(_key_str(key))
            continue
        if g is None and p is not None:
            rep.phantom_in_pipeline.append(_key_str(key))
            continue
        rep.matched_balls += 1

        for f in SCALAR_FIELDS:
            pv, gv = p.get(f), g.get(f)
            if pv != gv:
                div = Divergence(
                    over_ball=_key_str(key), field=f,
                    pipeline_value=pv, ground_truth_value=gv)
                div.surface = _classify(div, pipeline_ball=p, gt_ball=g)
                rep.divergences.append(div)
        for f in LIST_FIELDS:
            pv, gv = p.get(f) or [], g.get(f) or []
            if pv != gv:
                div = Divergence(
                    over_ball=_key_str(key), field=f,
                    pipeline_value=pv, ground_truth_value=gv)
                div.surface = _classify(div, pipeline_ball=p, gt_ball=g)
                rep.divergences.append(div)
        rep.conservation_failures.extend(_check_conservation(p, g))

    # Workstream I (Surface I — Silent-wicket-absorption) detector.
    # Predicate: GT FoW entry exists at over.ball X (within pipeline's
    # observation window) but pipeline FoW lacks a corresponding entry
    # within ±1 legal ball of X. Out-of-window GT FoWs are excluded
    # because no snapshot path could have observed them.
    def _overs_to_legal(o):
        if o is None:
            return None
        try:
            s = f"{float(o):.1f}"
            c, b = s.split(".")
            return int(c) * 6 + int(b)
        except (TypeError, ValueError):
            return None

    pipe_max_legal = 0
    pipe_all_fow_entries: list[tuple] = []
    for snap in pipe.values():
        try:
            m = int(snap.get("balls_total") or 0)
        except (TypeError, ValueError):
            m = 0
        pipe_max_legal = max(pipe_max_legal, m)
        for entry in (snap.get("fow_entries") or []):
            if not entry:
                continue
            score, wkt, batter, overs = (
                (entry + [None] * 4)[:4])
            if batter is None and not score:
                continue
            pipe_all_fow_entries.append(
                (score, batter, _overs_to_legal(overs)))
    gt_final_fow: list[list] = []
    for snap in gt.values():
        fl = snap.get("fow_entries") or []
        if len(fl) > len(gt_final_fow):
            gt_final_fow = fl

    silent_absorption_examples: list[str] = []
    for gt_entry in gt_final_fow:
        if not gt_entry:
            continue
        gscore, gwkt, gbatter, govers = (gt_entry + [None] * 4)[:4]
        g_legal = _overs_to_legal(govers)
        if g_legal is None or g_legal > pipe_max_legal:
            continue  # out-of-window
        matched = False
        for pscore, pbatter, p_legal in pipe_all_fow_entries:
            if gbatter and pbatter and gbatter == pbatter:
                matched = True
                break
            if (gscore is not None and pscore == gscore
                    and p_legal is not None
                    and abs(p_legal - g_legal) <= 1):
                matched = True
                break
        if not matched:
            silent_absorption_examples.append(str(govers or gwkt))
    if silent_absorption_examples:
        rep.surface_counts["Silent-wicket-absorption"] = (
            len(silent_absorption_examples))
        rep.surface_examples.setdefault(
            "Silent-wicket-absorption", silent_absorption_examples[0])

    # C21b temporal-pattern detector: scan pipeline snapshots in emit
    # order for the same over.ball coordinate; if any earlier snapshot
    # contains a W (or compound-W) token at position i and a later
    # snapshot at the same coord has a non-W token at position i, that
    # is a symbol-revert.
    by_coord: dict[str, list[dict]] = defaultdict(list)
    for k, snap in pipe.items():
        ob = k[0]
        by_coord[ob].append(snap)
    c21b_examples: list[str] = []
    for ob, snaps in by_coord.items():
        if len(snaps) < 2:
            continue
        for i, earlier in enumerate(snaps):
            etoks = earlier.get("this_over_tokens") or []
            for later in snaps[i + 1:]:
                ltoks = later.get("this_over_tokens") or []
                for pos, etok in enumerate(etoks):
                    if not _is_wicket_token(etok):
                        continue
                    if pos < len(ltoks) and not _is_wicket_token(ltoks[pos]):
                        c21b_examples.append(ob)
                        break
                if c21b_examples and c21b_examples[-1] == ob:
                    break
    if c21b_examples:
        rep.surface_counts["C21b-symbol-revert"] = len(c21b_examples)
        rep.surface_examples.setdefault(
            "C21b-symbol-revert", c21b_examples[0])

    for k in rep.missing_in_pipeline:
        rep.surface_counts["G-pipeline-lag"] += 1
        rep.surface_examples.setdefault("G-pipeline-lag", k)
    for d in rep.divergences:
        if d.surface:
            rep.surface_counts[d.surface] += 1
            rep.surface_examples.setdefault(d.surface, d.over_ball)
    if rep.conservation_failures:
        rep.surface_counts["Per-batter-ledger-drift"] = len(rep.conservation_failures)
        rep.surface_examples.setdefault(
            "Per-batter-ledger-drift",
            rep.conservation_failures[0].split(":", 1)[0])
    return rep


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    s = json.dumps(v) if isinstance(v, (list, dict)) else str(v)
    if len(s) > 60:
        s = s[:57] + "…"
    return s


def render_markdown(rep: DiffReport, pipeline_path: Path,
                    gt_path: Path) -> str:
    lines: list[str] = []
    lines.append(f"# Differential diff report")
    lines.append("")
    lines.append(f"- Pipeline: `{pipeline_path}`")
    lines.append(f"- Ground truth: `{gt_path}`")
    lines.append(
        f"- Matched balls: {rep.matched_balls} | "
        f"missing-in-pipeline: {len(rep.missing_in_pipeline)} | "
        f"phantom-in-pipeline: {len(rep.phantom_in_pipeline)} | "
        f"total divergences: {len(rep.divergences)}")
    lines.append("")

    lines.append("## 1. Per-surface incident counts")
    lines.append("")
    lines.append("| Surface | Count | First example (over.ball) |")
    lines.append("|---|---|---|")
    if not rep.surface_counts:
        lines.append("| _none_ | 0 | — |")
    for surface in sorted(rep.surface_counts, key=lambda s: -rep.surface_counts[s]):
        lines.append(
            f"| {surface} | {rep.surface_counts[surface]} | "
            f"{rep.surface_examples.get(surface, '—')} |")
    lines.append("")

    lines.append("## 2. Per-ball divergences")
    lines.append("")
    lines.append(
        "| over.ball | field | pipeline | ground-truth | surface |")
    lines.append("|---|---|---|---|---|")
    for d in rep.divergences:
        lines.append(
            f"| {d.over_ball} | {d.field} | {_fmt(d.pipeline_value)} | "
            f"{_fmt(d.ground_truth_value)} | "
            f"{d.surface or '_unclassified_'} |")
    if not rep.divergences:
        lines.append("| _none_ | | | | |")
    lines.append("")

    lines.append("## 3. Conservation invariants")
    lines.append("")
    if not rep.conservation_failures:
        lines.append("All conservation checks passed.")
    else:
        for i, msg in enumerate(rep.conservation_failures, 1):
            lines.append(f"{i}. {msg}")
    lines.append("")

    lines.append("## 4. Unclassified divergences")
    lines.append("")
    unclassified = [d for d in rep.divergences if not d.surface]
    if not unclassified:
        lines.append("No unclassified divergences.")
    else:
        lines.append("| over.ball | field | pipeline | ground-truth |")
        lines.append("|---|---|---|---|")
        for d in unclassified:
            lines.append(
                f"| {d.over_ball} | {d.field} | {_fmt(d.pipeline_value)} "
                f"| {_fmt(d.ground_truth_value)} |")
    lines.append("")

    lines.append("## 5. Missing / phantom balls")
    lines.append("")
    lines.append(
        f"- Missing-in-pipeline ({len(rep.missing_in_pipeline)}): "
        f"{', '.join(rep.missing_in_pipeline) or '—'}")
    lines.append(
        f"- Phantom-in-pipeline ({len(rep.phantom_in_pipeline)}): "
        f"{', '.join(rep.phantom_in_pipeline) or '—'}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--pipeline", required=True, type=Path)
    p.add_argument("--ground-truth", required=True, type=Path)
    p.add_argument("--report", required=True, type=Path)
    args = p.parse_args()
    rep = diff(args.pipeline, args.ground_truth)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        render_markdown(rep, args.pipeline, args.ground_truth))
    print(
        f"Diff: matched={rep.matched_balls} "
        f"missing={len(rep.missing_in_pipeline)} "
        f"phantom={len(rep.phantom_in_pipeline)} "
        f"divergences={len(rep.divergences)} "
        f"surfaces={dict(rep.surface_counts)}")
    print(f"Report: {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
