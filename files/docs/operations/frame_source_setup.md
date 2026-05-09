# Frame source setup

The pipeline can ingest broadcast frames from one of two sources,
selected at process start by the `FRAME_SOURCE` env var:

| Mode           | Backend                              | Use                          |
| -------------- | ------------------------------------ | ---------------------------- |
| `capture_card` | `cv2.VideoCapture(N)` — UGREEN HDMI→USB | **Production default** (2026-05-02) |
| `window`       | macOS Quartz `CGWindowListCreateImage` | Fallback / offline replay    |

Switching to the capture card removed Firefox from the pipeline path,
which fixed the macOS background-window throttle that capped sustained
capture at ~0.5 fps in the 2026-05-01 evening match.

## Hardware setup (M1 Max rig)

1. Air (broadcast source): JioHotstar tab fullscreen, **Mirror Display**
   to the external HDMI output (System Settings → Displays → Use as:
   Mirror for built-in).
2. HDMI cable: Air → UGREEN HDMI-to-USB capture card (USB-C side into
   M1 Max).
3. Confirm the M1 Max sees it (and pick the right index — see below).

## Device-index gotcha (cv2 ≠ ffmpeg)

`ffmpeg`'s avfoundation enumerator and OpenCV's `cv2.VideoCapture`
**enumerate macOS AVFoundation devices in different orders**. On the
verified M1 Max + UGREEN rig:

| Tool                    | UGREEN at | FaceTime HD at |
| ----------------------- | --------- | -------------- |
| `ffmpeg -list_devices`  | `[1]`     | `[0]`          |
| `cv2.VideoCapture(N)`   | `0`       | `1`            |

i.e. ffmpeg's `[1]` is cv2's `0`. The two indices are inverted. Trust
**only** the cv2 enumeration when picking `CAPTURE_DEVICE_INDEX`.

Verification commands — run both, but use the cv2 one for the actual
index:

```bash
# ffmpeg (informational only; index here is wrong for cv2)
ffmpeg -f avfoundation -list_devices true -i "" 2>&1 \
    | grep "AVFoundation video"

# cv2 (authoritative — this is the index CAPTURE_DEVICE_INDEX wants)
python3 - <<'PY'
import cv2
for i in range(4):
    cap = cv2.VideoCapture(i)
    ok = cap.isOpened()
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    print(f"  cv2 index {i}: opened={ok} {w}x{h}")
    cap.release()
PY
```

A 1920×1080 device that opens cleanly is the UGREEN. The 1280×720
(or similar) device is the built-in webcam.

**On a new machine, always run the cv2 check first.** The default
`CAPTURE_DEVICE_INDEX=0` is correct for the verified M1 Max rig but
will silently capture the webcam on machines where the order differs.

## Verification before going live

```bash
cd files
python scripts/capture_card_test.py
```

Expected stdout:

```text
[capture_card_test] frames=100 elapsed=~3.5s observed_fps=~28.0
[capture_card_test] resolution=1920x1080 channels=3 dtype=uint8
[capture_card_test] mean_intensity min=… max=… avg=…
[capture_card_test] saved /tmp/capture_card_test_f001.png
[capture_card_test] saved /tmp/capture_card_test_f050.png
[capture_card_test] saved /tmp/capture_card_test_f100.png
[capture_card_test] OK — capture card is usable for live pipeline.
```

Open the saved PNGs to confirm the broadcast (not a black screen, not
the desktop) is being captured. Black frames typically mean the player
is paused, the Air is sleeping, or the cable was hot-unplugged.

## Configuration

| Env var                | Default        | Notes                                                                                |
| ---------------------- | -------------- | ------------------------------------------------------------------------------------ |
| `FRAME_SOURCE`         | `capture_card` | `capture_card` or `window`                                                           |
| `CAPTURE_DEVICE_INDEX` | `0`            | cv2 device index (NOT the ffmpeg one — see gotcha above)                             |
| `FRAME_COLOR_TRUE_BGR` | `0`            | `1` ships true BGR end-to-end; **requires consumer re-tuning** (see Color Order Notes) |

All three vars are read by `eyes/main.py` (via `make_frame_source(...)`),
by `test_pipeline.py`, and by `BallAnalyzer` (its capture loop, separate
from `eyes/main.py`'s).

## Fallback to window mode

If the capture card is unavailable (cable damaged, USB controller
saturated, etc.):

```bash
FRAME_SOURCE=window python -m eyes.main --window-id <firefox_window_id>
```

`FrameSource.list_windows()` (used by the debug UI) lists candidate
windows and their IDs. This path is throttled when Firefox is
backgrounded — keep the tab foregrounded for usable rates.

## Hot-swap behaviour

`CaptureCardFrameSource` survives transient capture failures:

- Single `cap.read() == False` → 50 ms backoff and retry.
- 60 consecutive failures → automatic `cap.release()` + reopen.
- Persistent failure for >30 s → `[capture_card] no frames for >30s …`
  ERROR log, but the pipeline keeps serving the **last known frame**
  to avoid taking the whole pipeline down for a momentary unplug.

## Color Order Notes (audit 2026-05-02 — verdict V2)

### Finding

The downstream variable named `bgr` (in `ball_analyzer._capture_loop`,
in `FrameSource.get_latest()`, and in `CaptureCardFrameSource.get_latest()`)
**carries RGB pixel bytes, not BGR**. This is a project-wide
misnomer that predates the capture-card migration.

Reasoning:

1. `cv2.VideoCapture.read()` returns BGR by OpenCV convention.
2. `CGWindowListCreateImage` on macOS returns CGImages with memory
   layout BGRA (`kCGBitmapByteOrder32Little | kCGImageAlphaPremultipliedFirst`).
3. The legacy capture loop applies `arr[..., :3][:, :, ::-1]`, i.e.
   strip alpha → **BGR**, then reverse channel axis → **RGB**.
4. The capture-card path was tuned to mirror the same `[:, :, ::-1]`
   flip during the 2026-05-02 migration, so both backends deliver the
   same byte order.

So every consumer of the pipeline `bgr` variable receives RGB pixels:

* `cv2.imencode(".jpg", bgr, ...)` (`eyes/vision.py`,
  `vlm_delivery_classifier.py`, `delivery_window_recorder.py`,
  `eyes/network/debug_server.py`, `audit_run.py`, ~10 more) — encodes
  with R/B swapped. Scout / Qwen / Gemini receive R/B-swapped JPEGs.
* `cv2.cvtColor(bgr, COLOR_BGR2HSV)` (`pitch_detector.py`,
  `ball_detection_utils.py`, `eyes/field/field_detector.py`,
  `eyes/capture/broadcast_detector.py`) — H component is wrong;
  thresholds were empirically tuned to whatever the pipeline was
  actually seeing, so they currently work *because* the swap is
  consistent.
* `cv2.imwrite(path, bgr)` (delivery / replay snapshots) — saved
  PNGs/JPEGs on disk also have R/B swapped.

### Empirical verification

Run `python3 files/scripts/color_order_audit.py` with the broadcast
mirrored to the M1 Max display. The script:

* Captures a frame from `cv2.VideoCapture(0)` and saves it as
  `/tmp/audit_cv2_bgr.png` (correct colors — ground truth).
* Applies the pipeline's legacy `[:, :, ::-1]` flip to the same
  frame and saves it as `/tmp/audit_pipeline_to_vision_api.png`
  (this is exactly what every `cv2.imencode(".jpg", bgr)` ships).
* If granted Screen Recording permission, also captures via
  `CGWindowListCreateImage` and runs a per-channel correlation
  versus the cv2 reference, printing an explicit V1/V2 verdict.

The two PNGs differ visibly on any color-saturated broadcast frame
(player jerseys, red ball, brand logos): the `pipeline_to_vision_api`
PNG has reds → blues and blues → reds. That visible swap **is** the
finding.

### Why we have not flipped the capture layer to true BGR

Every HSV threshold in `pitch_detector`, `ball_detection_utils`,
`field_detector`, `broadcast_detector`, etc. was empirically tuned
against the swapped colors. Vision-API JPEG encoders (Scout, Qwen,
Gemini, Moondream) have been validated end-to-end with the swap. A
unilateral capture-layer flip would invalidate all of them at once.

### Opt-in fix path

Operators starting the consumer-side re-tuning audit can flip the
capture layer with:

```bash
FRAME_COLOR_TRUE_BGR=1 FRAME_SOURCE=capture_card python test_pipeline.py
```

This single env var is honoured in three places:

* `CaptureCardFrameSource.get_latest()` — skips the legacy flip.
* `FrameSource._cgimage_to_numpy()` — skips the legacy flip.
* `BallAnalyzer._capture_loop` — skips the legacy flip.

When the flag is on, every downstream `cv2.*` call is finally
receiving the bytes its API contract advertises.

**Follow-up work required when flipping `FRAME_COLOR_TRUE_BGR=1`
becomes the default** (out of scope for the 2026-05-02 housekeeping
session):

1. Re-tune HSV ranges in `files/pitch_detector.py`,
   `files/ball_detection_utils.py`,
   `files/eyes/field/field_detector.py`,
   `files/eyes/capture/broadcast_detector.py`.
2. Re-validate Scout / Qwen / Gemini camera_view + delivery
   classification against a fresh corpus captured under the new
   color order — historical corpus images on disk under
   `files/logs/deliveries/` are R/B-swapped vs reality.
3. Spot-check `pitch_grounder.py:221` (`COLOR_BGR2RGB` → PIL) since
   Moondream input becomes correct only when both this conversion
   and the upstream variable are aligned.
