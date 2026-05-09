"""Build a stable audit set sampled from production _tagged_buffer
admissions across recent sessions.

`frame_*.jpg` files are the picks selected from `_tagged_buffer` and
sent to the VLM classifier — the precision-critical surface.  We
sample these uniformly at random across 3 sessions, copy to
`audit_v1/frames/NNN.jpg`, and emit:

  audit_v1/
    frames/000.jpg .. 059.jpg
    sources.json          (origin path of each NNN.jpg)
    montage_NN.jpg        (4x3 grids, 12 frames each, for human label)

Run once.  audit_v1/ is the immutable benchmark for measuring prompt
changes.
"""
from __future__ import annotations
import json
import random
import shutil
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).parent
SESSIONS = [
    ROOT / "logs/deliveries/20260419_230742",
    ROOT / "logs/deliveries/20260419_223221",
    ROOT / "logs/deliveries/20260419_210351",
]
OUT = ROOT / "audit_v1"
N_SAMPLE = 60
GRID_COLS, GRID_ROWS = 4, 3
TILE_W = 480


def main():
    if OUT.exists():
        print(f"refusing to overwrite {OUT}")
        return

    candidates: list[Path] = []
    for sess in SESSIONS:
        for d in sorted(sess.iterdir()):
            if d.is_dir():
                candidates.extend(sorted(d.glob("frame_*.jpg")))
    print(f"candidates: {len(candidates)} across {len(SESSIONS)} sessions")
    if len(candidates) < N_SAMPLE:
        print(f"WARN: only {len(candidates)} available")

    random.seed(0)
    sample = random.sample(candidates, min(N_SAMPLE, len(candidates)))

    (OUT / "frames").mkdir(parents=True)
    sources = {}
    for i, src in enumerate(sample):
        name = f"{i:03d}.jpg"
        shutil.copy(src, OUT / "frames" / name)
        sources[name] = str(src.relative_to(ROOT))
    (OUT / "sources.json").write_text(json.dumps(sources, indent=2))

    per_grid = GRID_COLS * GRID_ROWS
    n_grids = (len(sample) + per_grid - 1) // per_grid
    for g in range(n_grids):
        tiles = sample[g * per_grid:(g + 1) * per_grid]
        rows = []
        for r in range(GRID_ROWS):
            row_imgs = []
            for c in range(GRID_COLS):
                idx = r * GRID_COLS + c
                if idx < len(tiles):
                    img = cv2.imread(str(tiles[idx]))
                    h, w = img.shape[:2]
                    th = int(h * TILE_W / w)
                    img = cv2.resize(img, (TILE_W, th),
                                     interpolation=cv2.INTER_AREA)
                else:
                    img = np.zeros((1, TILE_W, 3), dtype=np.uint8)
                gid = g * per_grid + idx
                cv2.putText(img, f"{gid:03d}", (10, 36),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.2,
                            (0, 255, 255), 3, cv2.LINE_AA)
                cv2.putText(img, f"{gid:03d}", (10, 36),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.2,
                            (0, 0, 0), 1, cv2.LINE_AA)
                row_imgs.append(img)
            max_h = max(im.shape[0] for im in row_imgs)
            row_imgs = [
                cv2.copyMakeBorder(im, 0, max_h - im.shape[0], 0, 0,
                                   cv2.BORDER_CONSTANT, value=(0, 0, 0))
                for im in row_imgs
            ]
            rows.append(np.hstack(row_imgs))
        max_w = max(r.shape[1] for r in rows)
        rows = [
            cv2.copyMakeBorder(r, 0, 0, 0, max_w - r.shape[1],
                               cv2.BORDER_CONSTANT, value=(0, 0, 0))
            for r in rows
        ]
        montage = np.vstack(rows)
        cv2.imwrite(str(OUT / f"montage_{g:02d}.jpg"), montage,
                    [cv2.IMWRITE_JPEG_QUALITY, 80])

    print(f"wrote {len(sample)} frames + {n_grids} montages to {OUT}")


if __name__ == "__main__":
    main()
