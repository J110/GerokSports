#!/usr/bin/env python3
"""Subscribe to the live pipeline WS and emit one row per legal-ball boundary.

Output:
  - JSONL at $OUT_DIR/ball_log_<SESSION>.jsonl (full payload snapshot)
  - TSV   at $OUT_DIR/ball_log_<SESSION>.tsv   (human compare vs Cricbuzz)

Row emitted whenever the (innings, overs, score, wickets, striker, non,
bowler, this_over_str) signature changes. Captures every UI-visible state
shift so post-match diff against Cricbuzz commentary is row-aligned.

Usage:
  python files/scripts/ball_by_ball_logger.py \
      --ws ws://localhost:8765 \
      --session "$BMF_SESSION_ID" \
      --out-dir files/logs/ball_log
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import websockets
except ImportError:
    print("ERROR: pip install websockets", file=sys.stderr)
    sys.exit(2)


def _safe(d: dict, *keys, default=""):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def _signature(payload: dict) -> tuple:
    inn = _safe(payload, "current_innings", default=_safe(payload, "innings"))
    return (
        inn,
        _safe(payload, "overs"),
        _safe(payload, "score"),
        _safe(payload, "wickets"),
        _safe(payload, "striker"),
        _safe(payload, "non"),
        _safe(payload, "current_bowler"),
        " ".join(map(str, payload.get("this_over") or [])),
    )


def _flatten_row(payload: dict, ts_iso: str) -> dict:
    return {
        "ts": ts_iso,
        "innings": _safe(payload, "current_innings",
                         default=_safe(payload, "innings")),
        "batting_team": _safe(payload, "batting_team"),
        "bowling_team": _safe(payload, "bowling_team"),
        "overs": _safe(payload, "overs"),
        "score": _safe(payload, "score"),
        "wickets": _safe(payload, "wickets"),
        "striker": _safe(payload, "striker"),
        "non": _safe(payload, "non"),
        "current_bowler": _safe(payload, "current_bowler"),
        "this_over": " ".join(map(str, payload.get("this_over") or [])),
        "target": _safe(payload, "target"),
        "run_rate": _safe(payload, "run_rate"),
        "req_rr": _safe(payload, "required_run_rate"),
        "last_event": _safe(payload, "last_delivery_info",
                            "delta_summary",
                            default=_safe(payload,
                                          "last_delivery_info",
                                          "event")),
    }


async def run(ws_url: str, jsonl_path: Path, tsv_path: Path,
              full_path: Path | None):
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    header = ("ts\tinn\tovers\tscore\twkts\tstriker\tnon\tbowler"
              "\tthis_over\tlast_event\n")
    if not tsv_path.exists():
        tsv_path.write_text(header)
    last_sig: tuple | None = None
    print(f"[ball-log] connecting → {ws_url}", flush=True)
    while True:
        try:
            async with websockets.connect(ws_url, ping_interval=20,
                                          ping_timeout=20) as ws:
                print(f"[ball-log] connected; jsonl={jsonl_path} "
                      f"tsv={tsv_path}", flush=True)
                async for raw in ws:
                    try:
                        payload = json.loads(raw)
                    except Exception:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    sig = _signature(payload)
                    if sig == last_sig:
                        continue
                    last_sig = sig
                    ts_iso = datetime.now(timezone.utc).isoformat()
                    row = _flatten_row(payload, ts_iso)
                    with jsonl_path.open("a") as fh:
                        fh.write(json.dumps(row,
                                            ensure_ascii=False) + "\n")
                    if full_path is not None:
                        rec = {"ts": ts_iso, "payload": payload}
                        with full_path.open("a") as fh:
                            fh.write(json.dumps(rec,
                                                ensure_ascii=False,
                                                default=str) + "\n")
                    line = (f"{ts_iso}\t{row['innings']}\t{row['overs']}\t"
                            f"{row['score']}\t{row['wickets']}\t"
                            f"{row['striker']}\t{row['non']}\t"
                            f"{row['current_bowler']}\t"
                            f"{row['this_over']}\t{row['last_event']}\n")
                    with tsv_path.open("a") as fh:
                        fh.write(line)
                    print(line.rstrip("\n"), flush=True)
        except (ConnectionRefusedError, OSError) as e:
            print(f"[ball-log] WS not up yet ({e}); retry in 3s",
                  flush=True)
            await asyncio.sleep(3)
        except websockets.ConnectionClosed:
            print("[ball-log] WS closed; reconnecting in 2s", flush=True)
            await asyncio.sleep(2)
        except Exception as e:
            print(f"[ball-log] unexpected error: {e!r}; retry 3s",
                  flush=True)
            await asyncio.sleep(3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ws", default=os.environ.get(
        "BALL_LOG_WS", "ws://localhost:8765"))
    ap.add_argument("--session", default=os.environ.get(
        "BMF_SESSION_ID", "live_" + time.strftime("%Y%m%d_%H%M%S")))
    ap.add_argument("--out-dir", default=os.environ.get(
        "BALL_LOG_DIR", "files/logs/ball_log"))
    ap.add_argument("--keep-full", action="store_true",
                    help="also save raw WS payloads (large)")
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    jsonl = out_dir / f"ball_log_{args.session}.jsonl"
    tsv = out_dir / f"ball_log_{args.session}.tsv"
    full = (out_dir / f"ball_log_{args.session}_full.jsonl"
            if args.keep_full else None)
    try:
        asyncio.run(run(args.ws, jsonl, tsv, full))
    except KeyboardInterrupt:
        print("[ball-log] stopped", flush=True)


if __name__ == "__main__":
    main()
