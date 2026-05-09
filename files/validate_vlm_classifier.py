"""Offline validation: run VLM classifier on today's surviving deliveries.

Loads the latest run's intact delivery folders (frames + raw_features
record), classifies each with `VLMDeliveryClassifier`, and writes a
side-by-side HTML review sheet plus a JSONL of results.

Usage:
    python validate_vlm_classifier.py
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, ".")
from vlm_delivery_classifier import VLMDeliveryClassifier


BASE = Path("logs/deliveries")
OUT_DIR = BASE / "vlm_validation"
OUT_DIR.mkdir(exist_ok=True)


def load_fresh_deliveries(include_rejected: bool = True) -> list[dict]:
    """Return records whose delivery folder mtime matches the record
    timestamp within 90s.  These are the surviving (un-overwritten)
    delivery folders.

    If include_rejected is True, also include records with a
    vlm_reject_* status (so we can re-test them against the relaxed
    prompt).
    """
    recs = [json.loads(l) for l in (BASE / "raw_features.jsonl").open()]
    fresh: list[dict] = []
    for r in recs:
        st = r.get("status")
        if st is not None and not (
                include_rejected and isinstance(st, str)
                and st.startswith("vlm_reject")):
            continue
        n = r["delivery_num"]
        fdir = BASE / f"delivery_{n:03d}"
        ws = fdir / "wide_shot.jpg"
        if not ws.exists():
            continue
        if not all((fdir / f"moment_{x}.jpg").exists()
                   for x in ("start", "key", "end")):
            continue
        try:
            rec_t = dt.datetime.fromisoformat(r["timestamp"])
        except Exception:
            continue
        delta = abs(ws.stat().st_mtime - rec_t.timestamp())
        if delta > 90:
            continue
        r["_folder"] = fdir
        r["_rec_t"] = rec_t
        r["_prev_status"] = st
        fresh.append(r)
    return fresh


def run_vlm_on_deliveries(records: list[dict]) -> list[dict]:
    clf = VLMDeliveryClassifier()
    results: list[dict] = []
    for i, rec in enumerate(records, 1):
        fdir: Path = rec["_folder"]
        frames = [
            cv2.imread(str(fdir / "moment_start.jpg")),
            cv2.imread(str(fdir / "moment_key.jpg")),
            cv2.imread(str(fdir / "moment_end.jpg")),
        ]
        if any(f is None for f in frames):
            print(f"[{i}/{len(records)}] d{rec['delivery_num']:03d} SKIP — frame read fail")
            continue
        t0 = time.time()
        out = clf.classify(frames, runs=rec.get("runs", 0),
                           speed_kph=rec.get("speed_kph"),
                           n_frames=3)  # only 3 saved; sweep comes later
        ms = (time.time() - t0) * 1000
        out["delivery_num"] = rec["delivery_num"]
        out["timestamp"] = rec["timestamp"]
        out["folder"] = str(fdir.relative_to(BASE.parent))
        out["old_pred"] = rec.get("predicted", {})
        out["wall_ms"] = round(ms)
        results.append(out)
        print(f"[{i}/{len(records)}] d{rec['delivery_num']:03d} "
              f"runs={rec.get('runs')} speed={rec.get('speed_kph')} "
              f"→ {out.get('length','?')}/{out.get('line','?')}/"
              f"{out.get('shot_action','?')} dir={out.get('shot_direction',{}).get('side','?')} "
              f"({ms:.0f}ms, conf={out.get('_vlm_confidence','?')})")
    print(f"\n[VLM] stats: {clf.stats}")
    return results


def write_html(results: list[dict], out_path: Path) -> None:
    rows = []
    for r in results:
        n = r["delivery_num"]
        # OUT_DIR sits inside BASE, so frames live one level up
        # at ../delivery_NNN/<frame>.jpg
        def rel(name: str, _n=n) -> str:
            return f"../delivery_{_n:03d}/{name}"

        old = r.get("old_pred", {})
        sd = r.get("shot_direction", {})
        rows.append(f"""
<tr>
  <td><b>d{n:03d}</b><br>{html.escape(r['timestamp'])}<br>
      runs={r.get('runs','?')} speed={r.get('_vlm_ms','?')}ms<br>
      conf=<b>{html.escape(str(r.get('_vlm_confidence','?')))}</b></td>
  <td><img src="{rel('moment_start.jpg')}" width="320"></td>
  <td><img src="{rel('moment_key.jpg')}" width="320"></td>
  <td><img src="{rel('moment_end.jpg')}" width="320"></td>
  <td>
    <div><b>VLM (new)</b></div>
    <div>angle: <b>{html.escape(str(r.get('bowling_angle','?')))}</b></div>
    <div>length: <b>{html.escape(str(r.get('length','?')))}</b></div>
    <div>line: <b>{html.escape(str(r.get('line','?')))}</b></div>
    <div>shot: <b>{html.escape(str(r.get('shot_action','?')))}</b></div>
    <div>direction: <b>{html.escape(str(sd.get('side','?')))}</b></div>
    <div>elev: <b>{html.escape(str(r.get('shot_elevation','?')))}</b></div>
    <div>bounce: <b>{html.escape(str(r.get('bounce','?')))}</b></div>
    <hr>
    <div><b>Old (trajectory)</b></div>
    <div style="color:#888">length: {html.escape(str(old.get('length','?')))}</div>
    <div style="color:#888">line: {html.escape(str(old.get('line','?')))}</div>
    <div style="color:#888">angle: {html.escape(str(old.get('bowling_angle','?')))}</div>
    <hr>
    <div style="font-size:11px;color:#444">
      <i>{html.escape(r.get('commentary_line',''))}</i>
    </div>
  </td>
</tr>""")

    body = "\n".join(rows)
    html_doc = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>VLM Validation</title>
<style>
body {{ font-family: -apple-system, sans-serif; margin: 16px; }}
table {{ border-collapse: collapse; }}
td {{ border: 1px solid #ccc; padding: 8px; vertical-align: top;
      font-size: 12px; }}
th {{ background: #eee; padding: 6px; }}
img {{ display: block; }}
</style>
</head><body>
<h2>VLM Delivery Classifier — Validation ({len(results)} deliveries)</h2>
<p>Compare frame-by-frame: are VLM labels (bold) plausible given the
imagery? The old trajectory predictions are shown grey for reference;
they are known to be unreliable.</p>
<table>
<tr><th>Meta</th><th>Frame 1 (release)</th><th>Frame 2 (pitch)</th>
<th>Frame 3 (shot)</th><th>Classification</th></tr>
{body}
</table>
</body></html>"""
    out_path.write_text(html_doc)
    print(f"[HTML] wrote {out_path}")


def main():
    fresh = load_fresh_deliveries()
    print(f"Loaded {len(fresh)} fresh deliveries")
    results = run_vlm_on_deliveries(fresh)

    out_jsonl = OUT_DIR / "results.jsonl"
    with out_jsonl.open("w") as f:
        for r in results:
            r2 = {k: v for k, v in r.items() if k != "_vlm_raw"}
            f.write(json.dumps(r2, default=str) + "\n")
    print(f"[JSONL] wrote {out_jsonl}")

    write_html(results, OUT_DIR / "review.html")

    # Summary
    print("\n=== SUMMARY ===")
    n_total = len(results)
    n_reject = sum(1 for r in results if r.get("_untrackable"))
    n_accept = n_total - n_reject
    print(f"Total: {n_total}  Accept: {n_accept}  Reject: {n_reject} "
          f"({100*n_reject/max(n_total,1):.0f}%)")
    print(f"{'D#':>4}  {'prev':<28}  new")
    for r in results:
        prev = str(r.get("_prev_status") or "accept")
        if r.get("_untrackable"):
            new = f"REJECT:{r.get('_skip_reason','?')}"
        else:
            new = (f"ACCEPT len={r.get('length','?')} "
                   f"shot={r.get('shot_action','?')}")
        print(f"{r['delivery_num']:>4}  {prev:<28}  {new}")


if __name__ == "__main__":
    main()
