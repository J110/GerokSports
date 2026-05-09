#!/usr/bin/env python3
"""Copy combined-corpus jpeg paths into a flat dir with unique basenames.

``select_combined_scout_corpus`` may merge matches that reuse overlapping
``frame_count`` integers. ``run_shadow`` keys rows by ``frame_id`` and
looks up snapshots under ``--frames-dir / path.name``, so collisions
would corrupt Groq rows.

Reads the corpus JSON, copies each referenced file into
``--dest-dir``, rewrites ``path``, and derives a unique ``frame_id``
from ``match_id`` + original ``frame_id`` / ``frame_count``.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_FILES = _HERE.parent


def _slug(mid: str) -> str:
    s = mid.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_") or "match"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, help="Input corpus JSON.")
    ap.add_argument(
        "--output",
        "-o",
        required=True,
        help="Output corpus JSON (with updated path + frame_id).",
    )
    ap.add_argument(
        "--dest-dir",
        default="docs/corpus_frames_combined_v1",
        help="Flat directory under files/ for copied JPEGs.",
    )
    args = ap.parse_args(argv)

    corp_path = Path(args.corpus)
    if corp_path.is_absolute():
        inp = corp_path
    else:
        inp = _FILES / corp_path
    payload = json.loads(inp.read_text(encoding="utf-8"))
    frames: list[dict] = payload.get("frames", [])
    dest = _FILES / args.dest_dir.replace("\\", "/")
    dest.mkdir(parents=True, exist_ok=True)

    for row in frames:
        mid = str(row.get("match_id", "unknown"))
        slug_mid = _slug(mid)
        rel = Path(row["path"])
        src = (_FILES / rel).resolve()
        if not src.is_file():
            print(f"ERROR: missing jpeg {src}", file=sys.stderr)
            return 2
        out_name = f"{slug_mid}_{src.name}"
        dst = dest / out_name
        shutil.copy2(src, dst)

        fid = row.get("frame_id", "")
        fc = row.get("frame_count", "")
        new_fid = f"{slug_mid}_{fid}" if fid else f"{slug_mid}_fc{fc}"
        row["frame_id"] = new_fid
        row["path"] = str(Path(args.dest_dir) / out_name)
        meta = payload.setdefault("metadata", {})
        meta.setdefault("materialize", {})
        md = meta["materialize"]
        md["dest_dir"] = args.dest_dir
        md["source_corpus"] = str(corp_path)

    outp = Path(args.output)
    if not outp.is_absolute():
        outp = _FILES / outp
    outp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {outp} with {len(frames)} JPEGs → {dest}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
