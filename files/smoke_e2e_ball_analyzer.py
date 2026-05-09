"""E2E smoke: BallAnalyzer + Recorder + Gemini, no macOS capture.

Bypasses the Quartz capture thread by:
  - manually populating BallAnalyzer._frame_buffer with frames from
    ball_test_clip_30fps.mp4 against a synthetic timeline, and
  - manually calling ball_analyzer.on_scout_tag(ts, view) to drive
    the recorder's state machine, just like test_pipeline.py does.

Then fires a synthetic score event via analyze_last_delivery and
inspects the returned dict.

Verifies:
  - recorder is constructed in default mode
  - Gemini path is taken (_method == "gemini")
  - Tier 1+2 fields land on the result
  - commentary_line + narrative survive the merge
  - speed_kph injection works (scoreboard owns speed)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from ball_analyzer import BallAnalyzer


def main():
    ba = BallAnalyzer(window_id=0)  # window_id unused (we don't .start)
    if ba._recorder is None:
        print(f"FATAL: recorder not constructed. mode flags / key issue.")
        sys.exit(1)
    print(f"BallAnalyzer constructed in GEMINI mode "
          f"(recorder={ba._recorder!r})")

    # Mark alive so analyze_last_delivery doesn't bail.  We bypass the
    # macOS Quartz capture thread entirely; spawn a sleeper to keep
    # ba.alive truthy without any side effects on the buffer.
    import threading

    def _sleeper():
        while ba._running:
            time.sleep(0.05)

    ba._running = True
    ba._thread = threading.Thread(target=_sleeper, daemon=True)
    ba._thread.start()

    # Load real frames from clip 1 onto a synthetic 20fps timeline
    clip = ROOT / "ball_test_clip_30fps.mp4"
    cap = cv2.VideoCapture(str(clip))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    stride = max(1, int(round(src_fps / 20.0)))
    t0 = time.time() - 30.0  # frames are 30s "ago" so they fit the buffer
    i = 0
    n_appended = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if i % stride == 0:
            ts = t0 + n_appended / 20.0
            ba._frame_buffer.append((ts, fr))
            n_appended += 1
        i += 1
    cap.release()
    print(f"Loaded {n_appended} frames into rolling buffer "
          f"(span {n_appended/20.0:.1f}s)")

    # Drive the recorder state machine with a Scout tag stream.
    # Window opens at t0+1, closes at t0+8 on 'replay' tag.
    print("\nFeeding Scout tags ...")
    for offset, view in [
        (1.0, "bowlers_end"),
        (3.0, "bowlers_end"),
        (5.0, "bowlers_end"),
        (7.0, "bowlers_end"),
        (8.5, "replay"),
    ]:
        ts = t0 + offset
        ba.on_scout_tag(ts, view)
        print(f"  [{offset:5.1f}s] tag={view!r}  state={ba._recorder._state}")

    # Fire score event — should await the in-flight Gemini call
    print("\nFiring synthetic score event (runs=0, DOT) ...")
    t_start = time.time()
    result = ba.analyze_last_delivery(
        runs=0,
        speed_kph=138.0,
        over_number=4.3,
        innings=1,
        event_type="DOT",
    )
    wall = time.time() - t_start
    print(f"\nanalyze_last_delivery returned in {wall:.1f}s")

    if not result:
        print("FATAL: no result returned")
        sys.exit(2)

    print("\n── Result ──")
    print(f"  _method:         {result.get('_method')}")
    print(f"  _gemini_model:   {result.get('_gemini_model')}")
    print(f"  _gemini_ms:      {result.get('_gemini_ms')}")
    print(f"  _window_id:      {result.get('_window_id')}")
    print(f"  _window_dur_s:   {result.get('_window_dur_s')}")
    print(f"  _window_frames:  {result.get('_window_frames')}")
    print(f"  _window_reason:  {result.get('_window_reason')}")
    print(f"  _untrackable:    {result.get('_untrackable')}")
    print()
    print(f"  batsman_handed:  {result.get('batsman_handed')}")
    print(f"  bowling_arm:     {result.get('bowling_arm')}")
    print(f"  bowling_type:    {result.get('bowling_type')}")
    print(f"  bowling_angle:   {result.get('bowling_angle')}")
    print(f"  length:          {result.get('length')}")
    print(f"  line:            {result.get('line')}")
    print(f"  bounce:          {result.get('bounce')}")
    print(f"  shot_action:     {result.get('shot_action')}")
    print(f"  shot_direction:  {result.get('shot_direction')}")
    print(f"  shot_elevation:  {result.get('shot_elevation')}")
    print(f"  contact_quality: {result.get('contact_quality')}")
    print(f"  ball_speed_kph_vlm:  {result.get('ball_speed_kph_vlm')}")
    print(f"  ball_speed_visible:  {result.get('ball_speed_visible')}")
    print(f"  runs:            {result.get('runs')}")
    print()
    print(f"  commentary_line: {result.get('commentary_line')}")
    print(f"  narrative:       {result.get('narrative')}")

    # ── Assertions ─────────────────────────────────────────────
    fails: list[str] = []
    if result.get("_method") != "gemini":
        fails.append(f"_method != gemini ({result.get('_method')})")
    if not result.get("_window_frames"):
        fails.append("missing _window_frames")
    for k in ("batsman_handed", "bowling_arm", "bowling_type",
              "length", "line", "bounce", "shot_action",
              "narrative", "commentary_line"):
        if k not in result:
            fails.append(f"missing field {k}")
    if result.get("ball_speed_kph_vlm") != 138.0:
        fails.append(f"speed merge: got "
                     f"{result.get('ball_speed_kph_vlm')}, want 138.0")
    if result.get("runs") != 0:
        fails.append(f"runs: got {result.get('runs')}, want 0")

    if fails:
        print("\nFAIL:")
        for f in fails:
            print(f"  - {f}")
        ba.stop()
        sys.exit(3)

    print("\nPASS — Gemini E2E path works through BallAnalyzer.")
    ba.stop()


if __name__ == "__main__":
    main()
