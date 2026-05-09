"""Smoke test for OpenScoutShadowRunner.

Self-contained: drives Stage 1 directly via ``ingest_signals`` and
feeds synthetic Scout results to Stage 2, no external assets needed.
Verifies that the shadow thread produces at least one delivery JSONL
record and that the file ends with a footer.

Run from files/:
    python -m scripts.openscout_shadow_smoke.run_smoke
or:
    PYTHONPATH=files python files/scripts/openscout_shadow_smoke/run_smoke.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_FILES_ROOT = Path(__file__).resolve().parents[2]
if str(_FILES_ROOT) not in sys.path:
    sys.path.insert(0, str(_FILES_ROOT))

from openscout_shadow.shadow_runner import OpenScoutShadowRunner


def _stub_qwen(*, span_start_ts, span_end_ts, span):
    return {
        "length": "GOOD",
        "line": "OFF",
        "shot": "DEFENCE",
        "angle": "FORWARD",
        "bounce": None,
        "type": "SEAM",
        "contact": True,
        "runs": 0,
        "commentary_feed": "shadow stub",
        "_smoke_span_window_s": round(span_end_ts - span_start_ts, 3),
    }


def _drive_stage1_active(runner: OpenScoutShadowRunner, t0: float) -> float:
    """Push synthetic signals so Stage 1 latches ACTIVE.

    Open band requires strip_mean ≤ 0.35 and flow_peak_count ≥ 10
    held for min_active_s (1.5 s). Signals bypass cv2 via
    BroadcastModeFilter.ingest_signals.
    """
    ts = t0
    # Bimodal: 1 spike per 4 samples so median≈0.05, peaks are
    # well above ``median + std``. 80 samples × 0.1s = 8 s, comfortably
    # > min_active_s (1.5 s).
    for i in range(80):
        ts += 0.1
        flow = 20.0 if i % 4 == 0 else 0.05
        runner._stage1.ingest_signals(
            ts, flow_magnitude=flow, strip_diff=0.04)
    return ts


def main() -> int:
    out_dir = Path("/tmp/openscout_shadow_smoke")
    out_dir.mkdir(parents=True, exist_ok=True)
    session_id = f"smoke{int(time.time())}"
    runner = OpenScoutShadowRunner(
        session_id=session_id,
        output_dir=out_dir,
        qwen_classifier=_stub_qwen,
    )
    runner.start()

    # Stage 1: latch ACTIVE on the shadow thread's filter directly.
    # (add_frame would also work but requires opencv on PATH.)
    last_ts = _drive_stage1_active(runner, t0=1000.0)
    if runner._stage1.current_state() != "active":
        print(
            f"FAIL: stage1 did not latch ACTIVE: "
            f"{runner._stage1.stats()}", file=sys.stderr)
        runner.stop()
        return 1

    # Stage 2: action obs forming a > 2 s span, then a hard-close.
    base = last_ts + 0.5
    for i in range(8):
        runner.add_scout_result({
            "ts": base + i * 0.5,
            "frame_class": "action",
            "raw_description": f"action {i}",
        })
    runner.add_scout_result({
        "ts": base + 6.0,
        "frame_class": "replay",
        "raw_description": "replay-trigger",
    })
    # Tail of frames so closure-hold (3 s) elapses.
    for i in range(6):
        runner.add_scout_result({
            "ts": base + 10.0 + i * 1.0,
            "frame_class": "other",
            "raw_description": f"tail {i}",
        })

    time.sleep(1.0)
    runner.stop()

    out_path = out_dir / f"{session_id}.jsonl"
    if not out_path.exists():
        print(f"FAIL: no JSONL at {out_path}", file=sys.stderr)
        return 1
    lines = [ln for ln in out_path.read_text().splitlines() if ln]
    records = [json.loads(ln) for ln in lines]
    deliveries = [r for r in records if "delivery_id" in r]
    has_header = any(r.get("_header") for r in records)
    has_footer = any(r.get("_footer") for r in records)
    if not deliveries:
        print(f"FAIL: no delivery records in {out_path}", file=sys.stderr)
        for r in records:
            print(f"  {json.dumps(r)}", file=sys.stderr)
        return 1
    if not (has_header and has_footer):
        print(
            f"FAIL: missing header/footer (header={has_header}, "
            f"footer={has_footer})", file=sys.stderr)
        return 1
    required = {
        "session_id", "delivery_id",
        "stage1_window_open_ts", "stage1_window_close_ts",
        "stage2_span_start_ts", "stage2_span_end_ts",
        "stage2_span_padded_start", "stage2_span_padded_end",
        "stage2_max_consecutive_action", "stage2_action_ratio",
        "stage2_hard_close_count",
        "stage3_qwen_details",
        "stage3_qwen_latency_ms", "stage3_qwen_error",
    }
    for d in deliveries:
        missing = required - set(d.keys())
        if missing:
            print(
                f"FAIL: delivery missing fields {missing}: {d}",
                file=sys.stderr)
            return 1
    print(f"OK: {len(deliveries)} delivery record(s) in {out_path}")
    for d in deliveries:
        print(json.dumps(d, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
