#!/usr/bin/env python3
"""Summarize annotation CSV vs model predictions. Stdlib only."""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent.parent
DEFAULT_CSV = SCRIPT_DIR / "annotations.csv"
DEFAULT_MD = SCRIPT_DIR / "annotations_analysis.md"

FIELD_PAIRS = [
    ("length", "gt_length", "model_length", "model_length_conf"),
    ("line", "gt_line", "model_line", "model_line_conf"),
    ("shot_type", "gt_shot_type", "model_shot_type", "model_shot_type_conf"),
    ("shot_side", "gt_shot_side", "model_shot_side", "model_shot_side_conf"),
    ("shot_angle", "gt_shot_angle", "model_shot_angle", "model_shot_angle_conf"),
    ("handedness", "gt_handedness", "model_handedness", "model_handedness_conf"),
]

CONF_THRESH = 0.7


def norm_ws(ws: str) -> str:
    if ws == "fallback_pre_event_window":
        return "fallback"
    if ws == "retrospective_span":
        return "retrospective"
    return ws or ""


def exclude_gt(val: str) -> bool:
    v = (val or "").strip().lower()
    return v in ("", "unknown", "skip", "u")


def float_conf(raw) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def load_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def accuracy_block(rows: list[dict]) -> list[str]:
    lines = ["## Per-field accuracy", "", "| Field | Match | Total | Accuracy |", "|-------|------:|------:|---------:|"]
    for label, gt_k, m_k, _ in FIELD_PAIRS:
        total = 0
        match = 0
        for r in rows:
            gt = (r.get(gt_k) or "").strip()
            m = (r.get(m_k) or "").strip()
            if exclude_gt(gt):
                continue
            total += 1
            if gt == m:
                match += 1
        pct = 100.0 * match / total if total else 0.0
        lines.append(f"| {label} | {match} | {total} | {pct:.1f}% |")
    lines.append("")
    return lines


def length_by_bounce(rows: list[dict]) -> list[str]:
    lines = ["## Length accuracy by bounce visibility", "", "| bounce_visible | Match | Total | Accuracy |", "|----------------|------:|------:|---------:|"]
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        buckets[(r.get("bounce_visible") or "unknown").strip()].append(r)
    for bkey in sorted(buckets.keys()):
        sub = buckets[bkey]
        total = 0
        match = 0
        for r in sub:
            gt = (r.get("gt_length") or "").strip()
            m = (r.get("model_length") or "").strip()
            if exclude_gt(gt):
                continue
            total += 1
            if gt == m:
                match += 1
        pct = 100.0 * match / total if total else 0.0
        lines.append(f"| {bkey} | {match} | {total} | {pct:.1f}% |")
    lines.append("")
    return lines


def length_by_source(rows: list[dict]) -> list[str]:
    lines = [
        "## Length accuracy by window source",
        "",
        "| window_source | Match | Total | Accuracy |",
        "|----------------|------:|------:|---------:|",
    ]
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        buckets[norm_ws(r.get("window_source") or "")].append(r)
    for skey in sorted(buckets.keys()):
        sub = buckets[skey]
        total = 0
        match = 0
        for r in sub:
            gt = (r.get("gt_length") or "").strip()
            m = (r.get("model_length") or "").strip()
            if exclude_gt(gt):
                continue
            total += 1
            if gt == m:
                match += 1
        pct = 100.0 * match / total if total else 0.0
        lines.append(f"| {skey} | {match} | {total} | {pct:.1f}% |")
    lines.append("")
    return lines


def fabrication(rows: list[dict]) -> list[str]:
    lines = [
        "## High-confidence wrong predictions (model conf ≥ {:.1f}, GT not unknown/skip)".format(CONF_THRESH),
        "",
        "Per field: top 5 wrong predictions ranked by model confidence (desc).",
        "",
    ]
    for label, gt_k, m_k, c_k in FIELD_PAIRS:
        wrong: list[tuple[float, str, str]] = []
        for r in rows:
            gt = (r.get(gt_k) or "").strip()
            m = (r.get(m_k) or "").strip()
            if exclude_gt(gt):
                continue
            if gt == m:
                continue
            c = float_conf(r.get(c_k))
            if c is None or c < CONF_THRESH:
                continue
            wrong.append((c, m, gt))
        wrong.sort(key=lambda t: -t[0])
        top = wrong[:5]
        lines.append(f"### {label}")
        lines.append("")
        lines.append("| Field | Model | GT | Conf |")
        lines.append("|-------|-------|-------|------|")
        for c, m, gt in top:
            lines.append(f"| {label} | {m} | {gt} | {c:.2f} |")
        if not top:
            lines.append("| — | — | — | — |")
        lines.append("")
    return lines


def correlate_flight(rows: list[dict]) -> list[str]:
    """Optional: length match rate for bounce yes vs no (Path 2/3 probe)."""
    lines = ["## Length × bounce visible (quick correlation)", "", "| bounce | Match | Total | Accuracy |", "|--------|------:|------:|---------:|"]
    for bv in ("yes", "no", "partial"):
        sub = [r for r in rows if (r.get("bounce_visible") or "").strip() == bv]
        total = match = 0
        for r in sub:
            gt = (r.get("gt_length") or "").strip()
            m = (r.get("model_length") or "").strip()
            if exclude_gt(gt):
                continue
            total += 1
            if gt == m:
                match += 1
        pct = 100.0 * match / total if total else 0.0
        lines.append(f"| {bv} | {match} | {total} | {pct:.1f}% |")
    lines.append("")
    return lines


def resolve_path(p: Path, *, script_dir: Path, repo_root: Path) -> Path:
    if p.is_absolute():
        return p
    r = repo_root / p
    if r.is_file() or r.is_dir():
        return r
    return script_dir / p


def main() -> int:
    ap = argparse.ArgumentParser(description="Analyze annotations.csv vs model predictions.")
    ap.add_argument("--input", type=Path, default=DEFAULT_CSV, help="annotations CSV path")
    ap.add_argument("--output", type=Path, default=DEFAULT_MD, help="markdown report path")
    args = ap.parse_args()

    in_path = resolve_path(args.input, script_dir=SCRIPT_DIR, repo_root=REPO_ROOT)
    out_path = resolve_path(args.output, script_dir=SCRIPT_DIR, repo_root=REPO_ROOT)

    if not in_path.is_file():
        print(f"No CSV at {in_path}", file=sys.stderr)
        return 1

    rows = load_rows(in_path)
    if not rows:
        print("CSV is empty (no rows).", file=sys.stderr)
        return 1

    parts = (
        ["# Annotation analysis", "", f"Rows: **{len(rows)}**", f"Input: `{in_path}`", ""]
        + accuracy_block(rows)
        + length_by_bounce(rows)
        + length_by_source(rows)
        + correlate_flight(rows)
        + fabrication(rows)
    )
    text = "\n".join(parts) + "\n"
    print(text)
    out_path.write_text(text, encoding="utf-8")
    print(f"[wrote] {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
