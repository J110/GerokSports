#!/usr/bin/env python3
"""V6c vs V6d discriminating-frame report for combined-corpus ensembles.

Loads K shadow envelopes per variant (--v6c-runs, --v6d-runs), takes
majority vote of ``canon_camera_view`` over all rows (K× replicate votes)
per ``frame_id``, compares variants, merges corpus metadata
(``phase_bucket``, ``match_id``, ``path``).
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_FILES = _HERE.parent


def _load(paths: list[Path]) -> list[list[dict]]:
    rows: list[list[dict]] = []
    for p in sorted(paths):
        rows.append(json.loads(p.read_text(encoding="utf-8"))["results"])
    return rows


def _votes_by_frame(
        all_rows_var: list[list[dict]],
        variant_name: str,
) -> dict[str, list[str]]:
    """frame_id → list of canon_camera_view votes (excluding errors)."""
    out: dict[str, list[str]] = {}
    for run in all_rows_var:
        for r in run:
            if r.get("variant") != variant_name:
                continue
            if r.get("error"):
                continue
            cam = r.get("canon_camera_view")
            if cam is None:
                continue
            fid = str(r["frame_id"])
            out.setdefault(fid, []).append(str(cam))
    return out


def _majority(
        per_frame_votes: dict[str, list[str]],
) -> tuple[dict[str, str], dict[str, str]]:
    mv: dict[str, str] = {}
    ties: dict[str, str] = {}
    for fid in sorted(per_frame_votes.keys()):
        votes = per_frame_votes[fid]
        if not votes:
            continue
        c = Counter(votes).most_common(2)
        if len(c) == 1:
            mv[fid] = c[0][0]
            continue
        (la, na), (lb, nb) = c[0], c[1]
        if na == nb:
            ties[fid] = f"TIE('{la}', '{lb}' @ {na})"
        elif na > nb:
            mv[fid] = la
        else:
            mv[fid] = lb
    return mv, ties


def _migration_hash(fid_to_label: dict[str, str]) -> str:
    blob = json.dumps(sorted(fid_to_label.items()),
                      separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def _error_frac(rows: list[dict], variant_name: str) -> tuple[int, int, float]:
    vr = [r for r in rows if r["variant"] == variant_name]
    if not vr:
        return 0, 0, 0.0
    errs = sum(1 for r in vr if r.get("error"))
    return errs, len(vr), round(100.0 * errs / len(vr), 2)


def _expand(pat_list: list[str]) -> list[Path]:
    out: list[Path] = []
    for raw in pat_list:
        hits = sorted(glob.glob(raw, recursive=False))
        if hits:
            for h in hits:
                out.append(Path(h))
            continue
        p = Path(raw)
        if not p.is_absolute():
            p = _FILES / p
        out.append(p)
    return sorted(set(out), key=lambda x: x.name)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--v6c-runs", nargs="+")
    ap.add_argument("--v6d-runs", nargs="+")
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--output", "-o", required=True)
    args = ap.parse_args(argv)

    v6_paths = _expand(args.v6c_runs)
    v6d_paths = _expand(args.v6d_runs)
    corp_path = Path(args.corpus)
    if not corp_path.is_absolute():
        corp_path = _FILES / corp_path
    corp = json.loads(corp_path.read_text(encoding="utf-8"))

    corpus_frames = corp.get("frames", [])
    v6_chunks = _load(v6_paths)
    v6d_chunks = _load(v6d_paths)

    votes6 = _votes_by_frame(v6_chunks, "V6c")
    votes_d = _votes_by_frame(v6d_chunks, "V6d")
    maj6, ties6 = _majority(votes6)
    maj_d, ties_d = _majority(votes_d)

    by_fid: dict[str, dict] = {str(fr["frame_id"]): fr for fr in corpus_frames}
    corpus_ids = sorted(by_fid.keys())

    disc: list[tuple[str, str, str, dict]] = []
    missing_either = 0
    agree_n = 0
    for fid in corpus_ids:
        a = maj6.get(fid)
        b = maj_d.get(fid)
        meta = by_fid[fid]
        if a is None or b is None:
            missing_either += 1
            continue
        if a != b:
            disc.append((fid, a, b, meta))
        else:
            agree_n += 1

    rate = round(100.0 * len(disc) / max(len(corpus_ids), 1), 1)
    bc: Counter[str] = Counter(str(m.get("phase_bucket", "?"))
                               for _, _, _, m in disc)

    f941_axis = [(a, b) for (_, a, b, _) in disc
                 if a == "bowlers_end" and b == "other"]
    f748_axis = [(a, b) for (_, a, b, _) in disc if a == "closeup"
                 and b == "bowlers_end"]

    mh6 = _migration_hash(maj6)
    mh7 = _migration_hash(maj_d)

    lines = [
        "# V6c vs V6d — discriminating frames (combined corpus)",
        "",
        "## §1 Summary",
        "",
        f"- **Combined corpus frames:** {len(corpus_ids)}",
        f"- **Agree (maj V6c = maj V6d):** {agree_n}",
        f"- **Discriminating:** {len(disc)} ({rate}% of corpus)",
        f"- **Missing majority on ≥1 variant:** {missing_either}",
        "",
        "## §2 Discriminating frames",
        "",
        "| frame_id | phase_bucket | match_id | V6c maj | "
        "V6d maj | path |",
        "|----------|--------------|----------|---------|---------|------|",
    ]
    for fid, va, vb, m in sorted(
            disc,
            key=lambda t: (
                str(t[3].get("phase_bucket")),
                str(t[3].get("match_id")),
                int(t[3].get("frame_count") or -1),
            ),
    ):
        pb = m.get("phase_bucket", "?")
        mid = m.get("match_id", "?")
        pth = m.get("path", "?")
        lines.append(f"| `{fid}` | `{pb}` | `{mid}` | `{va}` | `{vb}` | `{pth}` |")

    lines.extend([
        "",
        "## §3 Per-bucket disagreement",
        "",
    ])
    for k, v in bc.most_common():
        lines.append(f"- **{k}:** {v}")

    lines.extend([
        "",
        "## §4 Pattern notes",
        "",
        f"- **V6c bowlers_end → V6d other (f941-class):** {len(f941_axis)}",
        f"- **V6c closeup → V6d bowlers_end (f748-class):** {len(f748_axis)}",
        "",
        "> Labels are ensemble majorities — not adjudicated accuracy.",
        "",
        "## §5 Labeling recommendations",
        "",
        f"- **Prioritize:** {len(disc)} discriminating frames only.",
        f"- **Rough wall time (~45 s/frame):** ~{max(1, len(disc) * 45 // 60)} min.",
        "",
        "## §6 Run inventory",
        "",
        "### V6c",
    ])
    for p in sorted(v6_paths):
        env = json.loads(p.read_text(encoding="utf-8"))
        rs = env.get("results", [])
        e, tot, pct = _error_frac(rs, "V6c")
        rel = p.name
        lines.append(f"- `{rel}` — rows {tot}, errs {e} (**{pct}%**)")
    lines.append("")
    lines.append("### V6d")
    for p in sorted(v6d_paths):
        env = json.loads(p.read_text(encoding="utf-8"))
        rs = env.get("results", [])
        e, tot, pct = _error_frac(rs, "V6d")
        lines.append(f"- `{p.name}` — rows {tot}, errs {e} (**{pct}%**)")

    lines.extend([
        "",
        "### Majority hashes",
        "",
        f"- **V6c pooled majority hash:** `{mh6}`",
        f"- **V6d pooled majority hash:** `{mh7}`",
        f"- **V6c ties:** {len(ties6)}",
        f"- **V6d ties:** {len(ties_d)}",
    ])

    outp = Path(args.output)
    if not outp.is_absolute():
        outp = _FILES / outp
    outp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {outp}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
