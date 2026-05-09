"""Unit tests for BroadcastModeFilter (Component 2, Stage 1).

Run:
    cd /Users/anmolmohan/Projects/SportsComm/files
    python3 tests/test_broadcast_mode_filter.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

THIS = Path(__file__).resolve().parent
ROOT = THIS.parent
sys.path.insert(0, str(ROOT))

from eyes.broadcast_mode_filter import (
    STATE_ACTIVE,
    STATE_INACTIVE,
    BroadcastModeFilter,
)

RAW_DIR = ROOT / "scripts" / "motion_baseline" / "raw"


class _Recorder:
    def __init__(self) -> None:
        self.opens: list[float] = []
        self.closes: list[float] = []

    def on_open(self, ts: float) -> None:
        self.opens.append(ts)

    def on_close(self, ts: float) -> None:
        self.closes.append(ts)


def _make_filter(rec: _Recorder, **overrides) -> BroadcastModeFilter:
    params = dict(
        window_s=4.0,
        open_strip_mean_max=0.18,
        open_flow_peak_min=10,
        close_strip_mean_max=0.30,
        close_flow_peak_min=6,
        min_active_s=1.0,
        min_inactive_s=1.0,
    )
    params.update(overrides)
    return BroadcastModeFilter(rec.on_open, rec.on_close, **params)


def _pump_signals(
    bmf: BroadcastModeFilter,
    duration_s: float,
    *,
    fps: float,
    flow_mag: float,
    strip_diff: float,
    start_ts: float = 0.0,
    flow_spike_every: int = 0,
    flow_spike_value: float = 0.0,
    strip_noise: float = 0.0,
    seed: int = 0,
) -> float:
    """Feed synthetic signals into the filter; return last ts used.

    ``flow_spike_every > 0`` emits a ``flow_spike_value`` sample every
    N samples (interleaved with a low baseline of ``flow_mag``). This
    produces the spiky distribution real deliveries exhibit, which
    ``peak_count = |{x > median + 1σ}|`` rewards.
    """
    rng = np.random.default_rng(seed)
    n = max(1, int(duration_s * fps))
    ts = start_ts
    for i in range(n):
        ts = start_ts + (i + 1) / fps
        if flow_spike_every > 0 and (i % flow_spike_every) == 0:
            fm = flow_spike_value
        else:
            fm = flow_mag
        sd = strip_diff + (rng.standard_normal() * strip_noise
                           if strip_noise > 0 else 0.0)
        bmf.ingest_signals(ts, max(0.0, fm), max(0.0, sd))
    return ts


# ── 1. Stationary frames → INACTIVE ───────────────────────────────

def test_stationary_stays_inactive() -> None:
    rec = _Recorder()
    bmf = _make_filter(rec)
    last = _pump_signals(bmf, duration_s=15.0, fps=15.0,
                         flow_mag=0.0, strip_diff=0.0)
    assert bmf.current_state() == STATE_INACTIVE
    assert rec.opens == []
    assert rec.closes == []
    assert last > 0


# ── 2. High-motion, stable strip → ACTIVE after debounce ─────────

def test_high_motion_stable_strip_goes_active() -> None:
    rec = _Recorder()
    bmf = _make_filter(rec, min_active_s=1.0, window_s=4.0)
    _pump_signals(bmf, duration_s=8.0, fps=15.0,
                  flow_mag=0.5, strip_diff=0.05,
                  flow_spike_every=3, flow_spike_value=8.0,
                  seed=42)
    assert bmf.current_state() == STATE_ACTIVE, bmf.stats()
    assert len(rec.opens) == 1
    assert rec.closes == []


# ── 3. High-motion, unstable strip → stays INACTIVE ──────────────

def test_high_motion_unstable_strip_stays_inactive() -> None:
    rec = _Recorder()
    bmf = _make_filter(rec)
    _pump_signals(bmf, duration_s=15.0, fps=15.0,
                  flow_mag=0.5, strip_diff=0.7,
                  flow_spike_every=3, flow_spike_value=8.0,
                  seed=7)
    assert bmf.current_state() == STATE_INACTIVE
    assert rec.opens == []


# ── 4. Transition test: stable → unstable strip ──────────────────

def test_transition_stable_then_unstable() -> None:
    rec = _Recorder()
    bmf = _make_filter(rec, min_active_s=1.0, min_inactive_s=1.0,
                       window_s=4.0)
    end_a = _pump_signals(bmf, duration_s=6.0, fps=15.0,
                          flow_mag=0.5, strip_diff=0.05,
                          flow_spike_every=3, flow_spike_value=8.0,
                          seed=1)
    assert bmf.current_state() == STATE_ACTIVE, bmf.stats()
    assert len(rec.opens) == 1

    _pump_signals(bmf, duration_s=10.0, fps=15.0,
                  flow_mag=0.5, strip_diff=0.8,
                  flow_spike_every=3, flow_spike_value=8.0,
                  seed=2, start_ts=end_a)
    assert bmf.current_state() == STATE_INACTIVE, bmf.stats()
    assert len(rec.closes) == 1


# ── 5. Min-duration debounce suppresses flicker ──────────────────

def test_flicker_does_not_transition() -> None:
    rec = _Recorder()
    # Long debounce so that short bursts of "active-like" signal
    # never complete the transition.
    bmf = _make_filter(rec, min_active_s=5.0, window_s=4.0)
    fps = 15.0
    ts = 0.0
    rng = np.random.default_rng(123)
    # Alternate 0.5 s ACTIVE-like and 0.5 s INACTIVE-like bursts
    # for 20 s.
    for cycle in range(20):
        active_like = cycle % 2 == 0
        for i in range(int(0.5 * fps)):
            ts += 1.0 / fps
            if active_like:
                fm = 8.0 if (i % 3 == 0) else 0.5
                sd = 0.05
            else:
                fm = 0.2
                sd = 0.6
            bmf.ingest_signals(ts, max(0.0, fm), max(0.0, sd))
    assert bmf.current_state() == STATE_INACTIVE, bmf.stats()
    assert rec.opens == []


def test_debounce_timer_resets_on_dissent() -> None:
    rec = _Recorder()
    bmf = _make_filter(rec, min_active_s=2.0, window_s=4.0)
    fps = 15.0
    ts = 0.0
    # 1.5 s active-like (below min_active_s=2.0)
    for i in range(int(1.5 * fps)):
        ts += 1.0 / fps
        bmf.ingest_signals(ts, 8.0 if (i % 3 == 0) else 0.5, 0.05)
    assert bmf.current_state() == STATE_INACTIVE
    # Brief dip into inactive-like territory
    for _ in range(int(0.5 * fps)):
        ts += 1.0 / fps
        bmf.ingest_signals(ts, 0.1, 0.6)
    # Then 1.8 s active-like again — still not enough to trip
    # a full 2 s debounce after the dip restarted the pending timer.
    for i in range(int(1.8 * fps)):
        ts += 1.0 / fps
        bmf.ingest_signals(ts, 8.0 if (i % 3 == 0) else 0.5, 0.05)
    assert bmf.current_state() == STATE_INACTIVE, bmf.stats()
    assert rec.opens == []


# ── 6. Validation errors on bad construction ─────────────────────

def test_rejects_inverted_hysteresis_band() -> None:
    rec = _Recorder()
    try:
        BroadcastModeFilter(
            rec.on_open, rec.on_close,
            open_strip_mean_max=0.30,
            close_strip_mean_max=0.10,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError on inverted strip band")
    try:
        BroadcastModeFilter(
            rec.on_open, rec.on_close,
            open_flow_peak_min=20,
            close_flow_peak_min=30,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError on inverted flow band")


# ── 7. Real fixture replay (jsonl pre-computed signals) ──────────

def _load_jsonl_signals(p: Path) -> list[tuple[float, float, float]]:
    rows: list[tuple[float, float, float]] = []
    with p.open() as f:
        for line in f:
            d = json.loads(line)
            rows.append((d["ts_s"], d["flow_magnitude"], d["strip_diff"]))
    return rows


def _replay_clip(
    jsonl: Path,
    **bmf_kwargs,
) -> tuple[float, float, _Recorder, BroadcastModeFilter]:
    rec = _Recorder()
    bmf = BroadcastModeFilter(rec.on_open, rec.on_close, **bmf_kwargs)
    rows = _load_jsonl_signals(jsonl)
    active_time = 0.0
    total_time = 0.0
    prev_ts = rows[0][0] if rows else 0.0
    for ts, flow, strip in rows:
        dt = max(0.0, ts - prev_ts)
        bmf.ingest_signals(ts, flow, strip)
        if bmf.current_state() == STATE_ACTIVE:
            active_time += dt
        total_time += dt
        prev_ts = ts
    return active_time, total_time, rec, bmf


def test_fixture_replay_real_delivery_ad_replay() -> None:
    fixtures = [
        ("real_delivery", RAW_DIR / "20260420_202239__d002.jsonl", "high"),
        ("ad",            RAW_DIR / "20260420_202239__d001.jsonl", "low"),
        ("replay",        RAW_DIR / "20260421_195050__d043.jsonl", "low"),
    ]
    available = [(lbl, p, expect) for lbl, p, expect in fixtures
                 if p.exists()]
    if not available:
        print("[skip] no fixture jsonl available — run phase A "
              "of compute_motion_signals.py first")
        return

    # Thresholds loosened relative to the module defaults to match
    # the sliding-window peak_count scale (baseline peak_count=35
    # was measured over full-clip aggregates of ~350 frames; a 10 s
    # window at 13 fps covers ~130 frames, so absolute counts are
    # lower). Phase B tuning picks the production defaults.
    params = dict(
        window_s=10.0,
        open_strip_mean_max=0.20,
        open_flow_peak_min=12,
        close_strip_mean_max=0.35,
        close_flow_peak_min=8,
        min_active_s=2.0,
        min_inactive_s=3.0,
    )
    results: list[tuple[str, str, float]] = []
    for label, p, expect in available:
        active_t, total_t, rec, bmf = _replay_clip(p, **params)
        frac = active_t / total_t if total_t > 0 else 0.0
        print(f"[fixture] {label:>14} {p.name} "
              f"active={active_t:.1f}s/{total_t:.1f}s ({frac:.0%}) "
              f"opens={len(rec.opens)} closes={len(rec.closes)}")
        results.append((label, expect, frac))
    # Directional check (stop condition S3): real_delivery fraction
    # must exceed ad/replay fraction. With n=1 of each, compare
    # pairwise without absolute thresholds.
    by_expect: dict[str, float] = {}
    for label, expect, frac in results:
        by_expect[expect] = max(by_expect.get(expect, 0.0), frac)
    if "high" in by_expect and "low" in by_expect:
        assert by_expect["high"] > by_expect["low"], (
            f"real_delivery fraction {by_expect['high']:.0%} should "
            f"exceed ad/replay fraction {by_expect['low']:.0%}")


# ── 7b. Cadence regression: BMF latches at 5 fps prod cadence ────

def test_filter_opens_window_at_production_cadence() -> None:
    """Stage 1 must open a window with v1 production thresholds when
    fed at the ~5 fps shadow ingest cadence Batch D unblocked.

    Regression for files/docs/investigations/
    broadcast_mode_filter_tuning.md §11: the Phase-B sweep silently
    assumed an ingest cadence the OpenScout rate gate (~0.17 fps)
    could never deliver. After Batch D the shadow add_frame path is
    decoupled and runs at the pipeline's native ~5 fps, which is the
    cadence baked into the v1 production thresholds (window_s=10.0,
    open_flow_peak_min=10).
    """
    rec = _Recorder()
    bmf = BroadcastModeFilter(rec.on_open, rec.on_close)
    _pump_signals(
        bmf,
        duration_s=30.0,
        fps=5.0,
        flow_mag=0.5,
        strip_diff=0.04,
        flow_spike_every=4,
        flow_spike_value=20.0,
        seed=2026,
    )
    assert bmf.current_state() == STATE_ACTIVE, bmf.stats()
    assert len(rec.opens) >= 1, (rec.opens, bmf.stats())


# ── 8. Debug telemetry (Phase A — capture-card threshold re-tune) ─

def _save_env(*keys: str) -> dict[str, str | None]:
    return {k: os.environ.get(k) for k in keys}


def _restore_env(saved: dict[str, str | None]) -> None:
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_debug_telemetry_emits_per_ingest() -> None:
    tmp_dir = Path(tempfile.mkdtemp(prefix="bmf_debug_"))
    debug_path = tmp_dir / "bmf_test.jsonl"
    saved = _save_env("BMF_DEBUG_TELEMETRY", "BMF_DEBUG_PATH")
    os.environ["BMF_DEBUG_TELEMETRY"] = "1"
    os.environ["BMF_DEBUG_PATH"] = str(debug_path)
    bmf = None
    try:
        rec = _Recorder()
        bmf = _make_filter(rec)
        bmf.mark_score_event(1.0)
        _pump_signals(bmf, duration_s=5.0, fps=5.0,
                      flow_mag=20.0, strip_diff=0.20)
    finally:
        if bmf is not None and bmf._debug_fp is not None:
            try:
                bmf._debug_fp.close()
            except Exception:
                pass
            bmf._debug_fp = None
        _restore_env(saved)

    assert debug_path.exists(), f"debug file not created: {debug_path}"
    rows = [json.loads(line) for line in
            debug_path.read_text().splitlines() if line.strip()]
    assert len(rows) == 25, f"expected 25 rows, got {len(rows)}"
    expected_keys = {"frame_idx", "ts_s", "flow_magnitude", "strip_diff",
                     "bmf_state", "score_event_within_5s",
                     "strip_roi_top", "strip_roi_bot"}
    for i, r in enumerate(rows):
        assert set(r.keys()) == expected_keys, (i, set(r.keys()))
        assert r["frame_idx"] == i, (i, r["frame_idx"])
        assert isinstance(r["ts_s"], (int, float))
        assert r["bmf_state"] in (STATE_INACTIVE, STATE_ACTIVE)
    ts_seq = [r["ts_s"] for r in rows]
    assert all(b > a for a, b in zip(ts_seq, ts_seq[1:])), \
        f"ts_s not strictly monotonic: {ts_seq}"
    early = [r for r in rows if r["ts_s"] <= 6.0]
    assert any(r["score_event_within_5s"] for r in early), \
        "score_event_within_5s never True after mark_score_event(1.0)"


def test_debug_telemetry_disabled_by_default() -> None:
    tmp_dir = Path(tempfile.mkdtemp(prefix="bmf_debug_off_"))
    sentinel = tmp_dir / "bmf_test.jsonl"
    saved = _save_env("BMF_DEBUG_TELEMETRY", "BMF_DEBUG_PATH")
    os.environ.pop("BMF_DEBUG_TELEMETRY", None)
    os.environ["BMF_DEBUG_PATH"] = str(sentinel)
    try:
        rec = _Recorder()
        bmf = _make_filter(rec)
        _pump_signals(bmf, duration_s=5.0, fps=5.0,
                      flow_mag=20.0, strip_diff=0.20)
        assert bmf._debug_fp is None
        assert not sentinel.exists(), \
            f"file unexpectedly created with telemetry off: {sentinel}"
    finally:
        _restore_env(saved)


# ── 8b. Batch T — strip ROI Y-band ───────────────────────────────

def test_batch_t_strip_roi_band_defaults_to_above_score() -> None:
    saved = _save_env("BMF_STRIP_ROI_TOP", "BMF_STRIP_ROI_BOT")
    os.environ.pop("BMF_STRIP_ROI_TOP", None)
    os.environ.pop("BMF_STRIP_ROI_BOT", None)
    try:
        rec = _Recorder()
        bmf = BroadcastModeFilter(rec.on_open, rec.on_close)
        s = bmf.stats()["params"]
        assert s["strip_roi_top_fraction"] == 0.78, s
        assert s["strip_roi_bot_fraction"] == 0.88, s
    finally:
        _restore_env(saved)


def test_batch_t_strip_roi_band_env_override() -> None:
    saved = _save_env("BMF_STRIP_ROI_TOP", "BMF_STRIP_ROI_BOT")
    os.environ["BMF_STRIP_ROI_TOP"] = "0.75"
    os.environ["BMF_STRIP_ROI_BOT"] = "0.85"
    try:
        rec = _Recorder()
        bmf = BroadcastModeFilter(rec.on_open, rec.on_close)
        s = bmf.stats()["params"]
        assert s["strip_roi_top_fraction"] == 0.75, s
        assert s["strip_roi_bot_fraction"] == 0.85, s
    finally:
        _restore_env(saved)


def test_batch_t_backward_compat_single_fraction() -> None:
    saved = _save_env("BMF_STRIP_ROI_TOP", "BMF_STRIP_ROI_BOT")
    os.environ.pop("BMF_STRIP_ROI_TOP", None)
    os.environ.pop("BMF_STRIP_ROI_BOT", None)
    try:
        rec = _Recorder()
        bmf = BroadcastModeFilter(
            rec.on_open, rec.on_close, strip_roi_fraction=0.12)
        s = bmf.stats()["params"]
        assert abs(s["strip_roi_top_fraction"] - 0.88) < 1e-9, s
        assert s["strip_roi_bot_fraction"] == 1.0, s
    finally:
        _restore_env(saved)


def test_batch_t_strip_diff_computed_in_band() -> None:
    """Synthesize a frame pair whose absdiff lives only in 78–88 % band.

    Goes through ``compute_frame_signals`` end-to-end (requires cv2);
    skipped when OpenCV is unavailable. Verifies the new band selector
    actually reads the right rows of the downsampled diff image.
    """
    try:
        import cv2  # noqa: F401
    except ImportError:
        print("[skip] cv2 not available")
        return
    from eyes.broadcast_mode_filter import compute_frame_signals

    h, w = 360, 640
    prev = np.zeros((h, w), dtype=np.uint8)
    cur = np.zeros((h, w), dtype=np.uint8)
    y0 = int(h * 0.78)
    y1 = int(h * 0.88)
    cur[y0:y1, :] = 200
    sig = compute_frame_signals(
        prev, cur,
        strip_roi_top_fraction=0.78,
        strip_roi_bot_fraction=0.88,
        max_dim=(w, h),
    )
    assert sig["strip_diff"] > 100.0, sig
    sig_legacy = compute_frame_signals(
        prev, cur,
        strip_roi_fraction=0.12,
        max_dim=(w, h),
    )
    assert sig_legacy["strip_diff"] < 50.0, sig_legacy


# ── 9. Discoverer ────────────────────────────────────────────────

def _collect_tests() -> list[tuple[str, callable]]:
    g = globals()
    return [(k, v) for k, v in sorted(g.items())
            if k.startswith("test_") and callable(v)]


def main() -> int:
    tests = _collect_tests()
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok   {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {name}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERR  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
