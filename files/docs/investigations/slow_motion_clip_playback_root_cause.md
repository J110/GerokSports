# Slow-motion clip playback — root-cause investigation

**Date:** 2026-05-05
**Trigger:** May 4 session `20260504_192431` clip `d001/delivery_window.mp4` plays at half-speed in QuickTime (60 fps, 1200 frames, 20.000 s duration; broadcast wall-clock window was 12.5 s).
**Yesterday's fix:** `compile_frames_to_mp4` fps clamp raised 60→120, on the hypothesis that the capture card outputs >60 fps native.
**Verdict:** Hypothesis is wrong. Capture card produces ~10–14 distinct frames per second. The 60/120 fps numbers in the metadata reflect BallAnalyzer's *poll rate*, not the capture device's output rate. The clamp bump masks the symptom (file plays at the right wall-clock duration) but the underlying duplicate-frame issue remains.

---

## Phase A — Ground truth

### A1. Capture-card reported fps
The `[capture_card] opened device …` log line was not present in either session log within the inspected sections, so the device's `cv2.CAP_PROP_FPS` reading is not directly recovered. (`grep -n "opened device" pipeline-2026-05-0{3,4}-*.log` returned no hits in the head/middle of the May 4 file; the open call happens before the `Frame source: capture_card` line at log:89, prior to log capture or with a different log level.) Falling back to packet-level analysis below.

### A2. BallAnalyzer's frame-buffer timestamp source
`files/ball_analyzer.py:2070,2085` —

```
now = time.time()
…
self._frame_buffer.append((now, bgr))
```

Timestamps are wall-clock from `time.time()`, sampled inside BallAnalyzer's poll loop. They are **not** copied from the capture device. Each loop iteration produces a fresh timestamp regardless of whether the underlying frame is new.

### A3. ffprobe of the saved clips

| Session | Clip | width×height | r_frame_rate | nb_frames | duration | wall-clock window | effective fps (frames/wall-clock) |
|---|---|---|---|---|---|---|---|
| 20260504_192431 (slow-mo) | d001 | 960×378 | 60/1 | 1200 | 20.000 s | 12.500 s¹ | 96.0 |
| 20260503_200806 (control) | d001 | 960×494 | 56183/1000 | 562 | 10.003 s | 12.500 s¹ | 44.96 |

¹ wall-clock window = `clip_end_ts - clip_start_ts` from `window_debug.json`. **Both windows are exactly 12.5 s** (same configured fallback window length); the May 4 clip contains 2.13× more frames over the same wall-clock span.

May 4 packet pts spacing (first 10 packets, after pts reorder):
`0.000, 0.0167, 0.0333, …` → 1/60 s intervals. The encoder stamped frames at exactly 60 fps because the computed raw fps was clamped down from a higher value.

May 3 packet pts spacing: `~0.0178 s` → 1/56.183 s intervals; no clamp hit.

---

## Phase B — Where the inflated fps comes from

### B1. fps derivation — `files/gemini_delivery_classifier.py:340-349`

```
duration = frames[-1][0] - frames[0][0]
fps = (len(frames) - 1) / duration
fps = max(5.0, min(120.0, fps))   # was min(60.0, fps) on May 4
```

`duration` here is the span of the **buffered timestamps**, which is the BallAnalyzer poll-loop's wall-clock interval. For May 4, span ≈ 12.5 s and len ≈ 1200 → raw fps ≈ 96. With the May-4 clamp of 60 active at the time the clip was written, the encoder used 60 fps, so `1200 / 60 = 20.000 s` of playback for 12.5 s of broadcast = 0.625× speed = slow-motion. With the new clamp at 120, fps≈96 passes through unchanged → `1200 / 96 ≈ 12.5 s` of playback ≈ wall-clock. **That is why the post-fix clip plays at correct speed.**

### B2. Distinct-content rate — pixel diff of consecutive decoded frames

Extracted the first 40 frames of each clip and computed mean-abs pixel diff between consecutive frames. h264 cannot manufacture identical decoded frames from distinct sources, so diff ≈ 0 means the input frames were genuine duplicates.

| Session | Frames analyzed | Motion transitions (diff > 1.0) | Near-duplicates (diff < 0.1) | Distinct-content fps¹ |
|---|---|---|---|---|
| May 4 d001 | 40 | 4 | 35 | ~9–10 fps |
| May 3 d001 | 40 | 10 | 27 | ~14 fps |

¹ Distinct-content fps = motion transitions / wall-clock window proportion. May 4: 4 transitions in ~0.42 s wall-clock (40 frames × 1/96 s) → ~9.6 fps. May 3: 10 transitions in ~0.71 s (40 × 1/56) → ~14 fps.

**Both clips contain heavy duplicate frames.** The capture card's effective output rate is ~10–14 distinct fps in both sessions. The 56 fps (May 3) and 96 fps (May 4) numbers reflect *how fast BallAnalyzer was polling the capture-card frame slot*, not how fast the capture device was producing new frames.

### B3. Polling mechanism — the duplicate-frame source

`files/eyes/capture/frame_source.py:271-298, 320-349`

```
def get_latest_bgr(self) -> np.ndarray | None:
    with self._lock:
        return self._latest_bgr
```

`CaptureCardFrameSource` exposes a single "latest frame" slot. Its background `_capture_loop` calls `cv2.cap.read()` (which blocks until the device delivers a frame, capped to the device's native rate) and overwrites the slot.

`files/ball_analyzer.py:2022-2023, 2043-2086` —

```
def _grab_full_frame_bgr(self):
    if self._capture_card is not None:
        return self._capture_card.get_latest_bgr()
    …

def _capture_loop(self):
    while self._running:
        raw_bgr = self._grab_full_frame_bgr()
        …
        now = time.time()
        …
        self._frame_buffer.append((now, bgr))
```

BallAnalyzer's loop has **no rate limit** and **no dedupe**. It calls `get_latest_bgr` (cheap dict-locked read) and unconditionally appends `(now, bgr)`. When the loop iterates faster than the slot updates, the same `bgr` object/contents gets appended multiple times with monotonically increasing wall-clock timestamps. To `compile_frames_to_mp4`, those duplicates look like high-frame-rate content.

### B4. Cross-session comparison

| | May 3 d001 (control) | May 4 d001 (slow-mo) |
|---|---|---|
| Wall-clock window | 12.5 s | 12.5 s |
| Buffered frames | 562 | 1200 |
| BallAnalyzer poll rate (frames / window) | 45 Hz | 96 Hz |
| Distinct-content rate (pixel diff) | ~14 fps | ~10 fps |
| Duplicate ratio | ~3× | ~10× |
| Pre-clamp computed fps | ~56 | ~96 |
| Clamp result (clamp = 60) | 56 (no clamp) | 60 (clamped down) |
| File playback duration | 10.0 s ≈ wall-clock-of-buffered-span | 20.0 s ≠ wall-clock |
| Plays correctly? | Yes | No (slow-mo) |

**Variable between sessions: BallAnalyzer's poll rate** (45 Hz → 96 Hz). The capture-card hardware is the same, and the distinct-content rate is in the same ballpark in both sessions. Something in the May 4 BallAnalyzer loop iteration body got faster — most likely incidental: smaller `_content_y` trim, no resize on incoming frames, or different work scheduled by the Python GIL during `cv2.cap.read()` on the capture-card thread. The shadow runner / Option α activation does not directly drive BallAnalyzer's poll cadence (it consumes from `_frame_buffer`, not the capture-card slot), so it is not the immediate cause, but it adds CPU contention that could perturb scheduling.

---

## Phase C — Yesterday's clamp 60→120: assessment

The clamp bump produces the observable effect ("clip plays at right speed") because:
- raw computed fps (96) < new clamp (120) → no clamp hit → file fps = 96 → file duration = 1200 / 96 ≈ 12.5 s = wall-clock.

But it does not address the root issue:
1. ~90% of the frames in the saved clip are pixel-duplicates. File size is ~10× what the distinct-content rate justifies (1.27 MB for d001 vs ~0.13 MB if dedup'd). Across a full match (~250 deliveries × 12.5 s) this is ~250 MB of redundant pixels per session.
2. The "fps" written into the file metadata (96 fps for May 4) is meaningless — it tracks BallAnalyzer's loop iteration rate, which is a CPU/scheduling artifact, not a property of the broadcast.
3. If BallAnalyzer's loop ever runs faster than the new 120 clamp (e.g., on a faster machine or with less per-iteration work), the same slow-mo bug recurs at the new ceiling.
4. Gemini classification gets duplicated frames, which wastes prompt tokens and may very mildly bias temporal perception (consecutive identical frames imply slowness or stillness in the broadcast).

---

## Phase D — Recommendation

**Primary fix (BallAnalyzer-side, dedupe at append time):** In `files/ball_analyzer.py:_capture_loop`, only append when the underlying capture-card frame is new. Cheapest signal is the `_frame_count` counter already maintained by `CaptureCardFrameSource._on_read_success` (frame_source.py:345). Expose it via `get_frame_count()` (already exists at frame_source.py:276) and skip the append when the count hasn't advanced since the last iteration.

Sketch:
```
last_seen_count = -1
while self._running:
    raw_bgr = self._grab_full_frame_bgr()
    if raw_bgr is None:
        time.sleep(0.005)
        continue
    if self._capture_card is not None:
        cnt = self._capture_card.get_frame_count()
        if cnt == last_seen_count:
            time.sleep(0.005)
            continue
        last_seen_count = cnt
    …
```

This gives one append per real capture-card frame. Inter-arrival rate then equals the capture device's actual native fps. `compile_frames_to_mp4`'s computed fps becomes meaningful, and the 60→120 clamp bump becomes irrelevant (raw fps will be ≤ device native ≤ 60 in practice).

**Secondary (defense-in-depth at the writer):** In `compile_frames_to_mp4`, cap the inferred fps at a broadcast-realistic value (e.g., 30) once dedupe is in place. This is a one-line tightening; defer until after the dedupe is verified working in production. Out of scope for now per the investigation brief.

**Do not revert the 60→120 clamp.** Until the dedupe lands, the clamp at 120 is necessary to keep clips playing at correct wall-clock duration on machines where BallAnalyzer happens to poll above 60 Hz.

**Option α not implicated.** Shadow runner consumes from `_frame_buffer` post-append; it cannot inject duplicates into the buffer. Its CPU pressure may indirectly perturb BallAnalyzer's loop scheduling but is not the mechanism. No change to Option α recommended.

---

## Summary

- **Yesterday's hypothesis:** capture card outputs >60 fps. **Wrong.**
- **Actual rate from card:** ~10–14 distinct frames per second in both sessions.
- **Actual rate of metadata fps:** BallAnalyzer's wall-clock poll rate, which fluctuates per-session (45 Hz on May 3, 96 Hz on May 4).
- **Mechanism of slow-motion:** poll rate (96) > old clamp (60) → file fps clamped down → frames-per-clamped-fps inflates duration → QuickTime plays at clamped rate, stretching 12.5 s of content over 20 s.
- **Yesterday's 60→120 clamp:** correctly removes the slow-mo symptom for the current poll-rate range. Underlying duplicate-frame waste remains. Keep the clamp; add a dedupe in `BallAnalyzer._capture_loop`.
