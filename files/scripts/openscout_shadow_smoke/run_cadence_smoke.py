"""Cadence smoke test for OpenScoutShadowRunner (Batch D).

Validates the post-Batch-D contract: the shadow Stage 1 ingest path is
decoupled from the OpenScout rate gate and runs at the pipeline's
native ~5 fps cadence. With v1 production BroadcastModeFilter
thresholds (window_s=10.0, open_flow_peak_min=10) this cadence MUST
produce at least one Stage 1 window-open event on a real-delivery
fixture; under the pre-Batch-D ~0.17 fps gate cadence the
``peak_count`` thresholds were mathematically unreachable. See
files/docs/investigations/broadcast_mode_filter_tuning.md §11.

The fixture jsonl already carries pre-computed signals (flow,
strip_diff) per frame, so we drive the runner's Stage 1 directly via
``ingest_signals`` at 5 fps cadence (1 sample per 200ms) instead of
re-running the cv2 optical-flow stack. The runner is otherwise
identical to the production wiring: started, observed via the public
``stats()`` snapshot, then stopped.

Run from files/:
    python -m scripts.openscout_shadow_smoke.run_cadence_smoke
or:
    PYTHONPATH=files python files/scripts/openscout_shadow_smoke/run_cadence_smoke.py
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

_FIXTURE_CANDIDATES = [
    _FILES_ROOT / "scripts" / "motion_baseline" / "raw"
    / "20260420_202239__d002.jsonl",
]


def _load_signals(p: Path) -> list[tuple[float, float, float]]:
    rows: list[tuple[float, float, float]] = []
    with p.open() as f:
        for line in f:
            d = json.loads(line)
            rows.append(
                (float(d["ts_s"]),
                 float(d["flow_magnitude"]),
                 float(d["strip_diff"])))
    return rows


def _pump_at_5fps(runner: OpenScoutShadowRunner,
                  signals: list[tuple[float, float, float]]) -> float:
    """Re-pump fixture signals at 5 fps cadence (1 sample / 200 ms).

    Drives the runner's Stage 1 filter directly to bypass cv2 (the
    fixture jsonl has no frames; signals are pre-computed). The
    timestamps are rewritten so the inter-sample gap is exactly the
    Batch-D production cadence regardless of the fixture's recording
    cadence.
    """
    ts = 1000.0
    for _orig_ts, flow, strip in signals:
        ts += 0.2
        runner._stage1.ingest_signals(ts, flow, strip)
    return ts


def main() -> int:
    fixture: Path | None = next(
        (p for p in _FIXTURE_CANDIDATES if p.exists()), None)
    if fixture is None:
        print(
            "SKIP: no labeled-clip fixture under "
            "files/scripts/motion_baseline/raw/ — run phase A of "
            "compute_motion_signals.py first",
            file=sys.stderr)
        return 0

    out_dir = Path("/tmp/openscout_shadow_cadence_smoke")
    out_dir.mkdir(parents=True, exist_ok=True)
    session_id = f"cadence-smoke-{int(time.time())}"
    runner = OpenScoutShadowRunner(
        session_id=session_id,
        output_dir=out_dir,
    )
    runner.start()
    try:
        signals = _load_signals(fixture)
        if not signals:
            print(f"FAIL: empty fixture {fixture}", file=sys.stderr)
            return 1
        _pump_at_5fps(runner, signals)
        time.sleep(0.5)
        snapshot = runner.stats()
    finally:
        runner.stop()

    opened = int(snapshot.get("stage1_windows_opened", 0))
    if opened < 1:
        print(
            f"FAIL: expected stage1_windows_opened ≥ 1, got "
            f"{opened}; stats={json.dumps(snapshot, default=str)}",
            file=sys.stderr)
        return 1
    print(
        f"OK: stage1_windows_opened={opened} from {fixture.name} "
        f"({len(signals)} signals at 5 fps)")
    print(json.dumps(snapshot, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
