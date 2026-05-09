"""Frame-count sweep: run Scout on the same delivery with 3, 5, and 8
images and see where classification quality plateaus.

Expects fresh deliveries written by BallAnalyzer in VLM mode, i.e.
``logs/deliveries/<session>/d<NN>/frame_<KK>.jpg`` with 8 saved frames.

Usage:
    .venv/bin/python frame_count_sweep.py [<session_id>] [<delivery_num>]

If no args, sweeps the most recent session and the first 5 deliveries
that have 8 frames saved.

Output:
    logs/deliveries/vlm_validation/sweep_<session>.html
        Visual side-by-side of 3/5/8-frame results per delivery.
    logs/deliveries/vlm_validation/sweep_<session>.jsonl
        Raw classifications.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import cv2

# Allow imports from this directory
sys.path.insert(0, os.path.dirname(__file__))
from vlm_delivery_classifier import VLMDeliveryClassifier  # noqa: E402

ROOT = Path(__file__).parent / "logs" / "deliveries"
OUT = ROOT / "vlm_validation"
OUT.mkdir(parents=True, exist_ok=True)


def _latest_session() -> str | None:
    sessions = sorted(p.name for p in ROOT.iterdir()
                      if p.is_dir() and p.name.startswith("2"))
    return sessions[-1] if sessions else None


def _delivery_folders(session: str) -> list[Path]:
    base = ROOT / session
    if not base.exists():
        return []
    return sorted(p for p in base.iterdir()
                  if p.is_dir() and p.name.startswith("d"))


def _load_frames(folder: Path) -> tuple[list, dict]:
    frames = []
    for k in range(16):
        f = folder / f"frame_{k:02d}.jpg"
        if not f.exists():
            break
        img = cv2.imread(str(f))
        if img is not None:
            frames.append(img)
    meta = {}
    meta_path = folder / "meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            pass
    return frames, meta


def main() -> None:
    args = sys.argv[1:]
    session = args[0] if args else _latest_session()
    if not session:
        print("No sessions found in logs/deliveries/")
        return
    print(f"Session: {session}")

    folders = _delivery_folders(session)
    if not folders:
        print(f"No delivery folders in session {session}")
        return

    target_d = args[1] if len(args) > 1 else None
    if target_d:
        folders = [f for f in folders if target_d in f.name]

    sweep_n = (3, 5)  # 5 is Scout's per-call max
    clf = VLMDeliveryClassifier()

    out_jsonl = OUT / f"sweep_{session}.jsonl"
    out_html = OUT / f"sweep_{session}.html"
    rows = []

    with out_jsonl.open("w") as jf:
        for folder in folders[:8]:  # limit for sanity
            frames, meta = _load_frames(folder)
            if len(frames) < 3:
                print(f"  {folder.name}: skip (only {len(frames)} frames)")
                continue
            print(f"\n{folder.name} — {len(frames)} frames available, "
                  f"runs={meta.get('runs','?')} "
                  f"speed={meta.get('speed_kph','?')}")

            results = {}
            for n in sweep_n:
                if len(frames) < n:
                    continue
                t0 = time.time()
                res = clf.classify(
                    frames, runs=meta.get("runs", 0),
                    speed_kph=meta.get("speed_kph"), n_frames=n)
                results[n] = res
                ms = (time.time() - t0) * 1000
                if res.get("_untrackable"):
                    print(f"  n={n}: REJECT {res.get('_skip_reason','?')} "
                          f"({ms:.0f}ms)")
                else:
                    sd = res.get("shot_direction", {})
                    print(f"  n={n}: "
                          f"{res.get('length','?')}/{res.get('line','?')} "
                          f"{res.get('shot_action','?')} "
                          f"({sd.get('zone','?')}, "
                          f"{res.get('shot_elevation','?')}) "
                          f"swing={res.get('swing_or_seam','?')} "
                          f"conf={res.get('_vlm_confidence','?')} "
                          f"({ms:.0f}ms)")
                jf.write(json.dumps({
                    "delivery": folder.name,
                    "n_frames": n,
                    "ms": round(ms),
                    "result": {
                        k: v for k, v in res.items()
                        if not k.startswith("_") or k in (
                            "_skip_reason", "_vlm_confidence")
                    },
                }) + "\n")

            rows.append((folder, meta, results))

    _write_html(out_html, session, rows, sweep_n)
    print(f"\nWrote {out_jsonl.name} and {out_html.name}")
    os.system(f"open -a 'Google Chrome' {out_html} 2>/dev/null || "
              f"open {out_html}")


def _write_html(path: Path, session: str, rows: list, sweep_n: tuple) -> None:
    cb = int(time.time())
    parts = [
        "<!doctype html><meta charset=utf-8>",
        f"<title>Frame-count sweep — {session}</title>",
        "<style>",
        "body{font-family:-apple-system,Helvetica,Arial,sans-serif;"
        "margin:20px;background:#fafafa;color:#222}",
        "h1{font-size:18px}",
        "table{border-collapse:collapse;margin-bottom:32px;width:100%}",
        "th,td{border:1px solid #ccc;padding:6px;vertical-align:top;"
        "font-size:13px;text-align:left}",
        "th{background:#eee}",
        "img{height:120px;display:block;margin:2px 0}",
        ".reject{background:#fee}",
        ".n{font-weight:bold;font-size:16px;color:#08a}",
        "code{background:#f4f4f4;padding:1px 4px;border-radius:2px}",
        "</style>",
        f"<h1>Frame-count sweep — session {session}</h1>",
        f"<p>Comparing Scout VLM with N={sweep_n} frames per delivery.</p>",
    ]
    for folder, meta, results in rows:
        runs = meta.get("runs", "?")
        n_total = meta.get("n_frames_total", "?")
        parts.append(f"<h2>{folder.name} — runs={runs}, "
                     f"narrowed_total={n_total}</h2>")
        # Show all saved frames as a strip
        parts.append("<div style='display:flex;gap:4px;flex-wrap:wrap'>")
        for k in range(16):
            f = folder / f"frame_{k:02d}.jpg"
            if not f.exists():
                break
            parts.append(
                f"<img src='file://{f.resolve()}?v={cb}' "
                f"title='frame_{k:02d}'>")
        parts.append("</div>")

        parts.append("<table>")
        parts.append("<tr><th>N</th><th>length</th><th>line</th>"
                     "<th>pitch_pos</th><th>shot</th><th>direction</th>"
                     "<th>elev</th><th>swing</th><th>speed</th>"
                     "<th>conf</th><th>commentary</th><th>ms</th></tr>")
        for n in sweep_n:
            if n not in results:
                parts.append(f"<tr><td>{n}</td>"
                             "<td colspan='11'>(not enough frames)</td></tr>")
                continue
            r = results[n]
            sd = r.get("shot_direction", {})
            cls = "reject" if r.get("_untrackable") else ""
            if r.get("_untrackable"):
                parts.append(
                    f"<tr class='{cls}'><td class='n'>{n}</td>"
                    f"<td colspan='9'>REJECT — "
                    f"{r.get('_skip_reason','?')}</td>"
                    f"<td>{r.get('_vlm_confidence','?')}</td>"
                    f"<td>{r.get('_vlm_ms','?')}</td></tr>")
            else:
                parts.append(
                    f"<tr><td class='n'>{n}</td>"
                    f"<td>{r.get('length','?')}</td>"
                    f"<td>{r.get('line','?')}</td>"
                    f"<td>{r.get('pitch_position','?')}</td>"
                    f"<td>{r.get('shot_action','?')}</td>"
                    f"<td>{sd.get('zone','?')}</td>"
                    f"<td>{r.get('shot_elevation','?')}</td>"
                    f"<td>{r.get('swing_or_seam','?')}</td>"
                    f"<td>{r.get('ball_speed_kph_vlm') or '—'}</td>"
                    f"<td>{r.get('_vlm_confidence','?')}</td>"
                    f"<td>{r.get('commentary_line','')}</td>"
                    f"<td>{r.get('_vlm_ms','?')}</td></tr>")
        parts.append("</table>")
    path.write_text("\n".join(parts))


if __name__ == "__main__":
    main()
