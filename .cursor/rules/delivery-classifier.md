# Delivery Classifier — Workflow Guide

This rule applies when working on delivery frame detection, ball classification, or the `ball_analyzer` / `ball_classifier` / `pitch_detector` modules.

## Goal

Achieve 100% accuracy on two tasks:
1. **Detection**: Capture genuine delivery frames for every ball bowled (no misses, no contaminated frames)
2. **Classification**: Correctly label every delivery's bowling angle, length, line, bounce, shot elevation, shot direction

## Architecture

### Frame Detection Pipeline (4 layers)

```
Layer 1: is_delivery_frame()        → pitch strip + figure-at-both-ends pattern
Layer 2: Temporal windowing + dedup  → isolates correct delivery's frames
Layer 3: Energy-based window         → finds peak motion segment
Layer 4: Trajectory validation       → rejects static/horizontal/non-downward movement
```

**Capture loop** (`ball_analyzer.py:_capture_loop`):
- `is_wide_shot(frame)` → `_wide_buffer` (diagnostic/fallback, 600 frames rolling)
- `is_delivery_frame(frame)` → `_dv_buffer` (primary, 600 frames rolling, flushed per delivery)

**Analysis** (`ball_analyzer.py:analyze_last_delivery`):
- Primary: DV buffer frames (passed `is_delivery_frame`)
- Fallback: temporal-windowed wide buffer frames, **gated through `is_delivery_frame`**
- Both paths feed into `_classify_delivery` which applies trajectory validation

### Key Files

| File | Purpose |
|------|---------|
| `files/pitch_detector.py` | `is_delivery_frame()`, `_find_pitch_center()`, `_has_figures_at_both_ends()`, `find_pitch_region()` |
| `files/ball_analyzer.py` | Capture loop, buffer management, `_analyze_3layer()`, `_classify_delivery()`, trajectory validation |
| `files/ball_classifier.py` | Rule-based classification: `classify_length()`, `classify_line()`, `classify_bowling_angle()`, etc. |
| `files/phase_separator.py` | Splits detections into flight / bounce / post-shot phases |
| `files/ball_detection_utils.py` | `detect_white_ball()`, `is_wide_shot()`, `find_video_region()` |
| `files/delivery_tools.py` | CLI toolbox for testing, labeling, comparing |
| `files/test_pipeline.py` | Main pipeline — calls `ball_analyzer.analyze_last_delivery()` on ball events |

### Data Files

| File | Purpose |
|------|---------|
| `files/logs/deliveries/raw_features.jsonl` | Auto-predictions + raw numeric features per delivery |
| `files/logs/deliveries/ground_truth_labels.jsonl` | Manual ground-truth labels |
| `files/logs/deliveries/delivery_NNN/` | Saved frames per delivery (wide_shot.jpg, moment_*.jpg, pitch_annotated.jpg) |

## Workflow: Live Match Testing

### Step 1: Run the pipeline during a match

```bash
cd files
python test_pipeline.py
```

The pipeline captures frames, detects ball events from scoreboard changes, and runs `ball_analyzer.analyze_last_delivery()` for each delivery. Results are saved to `logs/deliveries/`.

### Step 2: Check detection accuracy

```bash
python delivery_tools.py accuracy-report
```

This shows: total deliveries, detected vs failed, buffer stats for failures. Target: 100% detection rate with ≥2 detections per delivery.

### Step 3: Archive the run

```bash
python delivery_tools.py save-frames --archive archive_runN_description
```

Moves `delivery_NNN/` dirs and `raw_features.jsonl` into the archive folder.

### Step 4: Label the data

```bash
python delivery_tools.py label --dir logs/deliveries/archive_runN_description
```

For each delivery:
1. Open the frame images in the delivery folder
2. Look at `wide_shot.jpg` / `moment_key.jpg` for the camera angle
3. Look at `pitch_annotated.jpg` for the ball trajectory (green=flight, red=bounce, blue=post-shot)
4. Determine `frame_quality`: genuine, partial, contaminated, no_frames
5. If genuine: label bowling_angle, length, line, bounce, shot_elevation, shot_direction_side
6. Copy the JSON template from the tool output, edit it, append to `ground_truth_labels.jsonl`

**Label values:**
- `bowling_angle`: over, round
- `length`: bouncer, short, back_of_length, good_length, full, overpitched, yorker, full_toss
- `line`: wide_outside_off, outside_off, off_stump, on_stumps, leg_stump, on_pads, down_leg
- `bounce`: bouncer, sharp_bounce, good_bounce, normal, stayed_low, skidded_through
- `shot_elevation`: along_ground, in_the_air, no_shot
- `shot_direction_side`: offside, legside, straight, no_shot

### Step 5: Compare and tune

```bash
python delivery_tools.py compare --dir logs/deliveries/archive_runN_description
```

Shows per-field accuracy with mismatches. For each mismatch, the raw numeric values (offset_frac, len_frac, speed_kph) are shown alongside the threshold that produced the wrong label.

**To fix a mismatch**, edit `ball_classifier.py`:
- `classify_length()`: adjust `frac` threshold boundaries (lines ~49-59)
- `classify_line()`: adjust `offset_frac` threshold boundaries (lines ~87-99)
- `classify_bowling_angle()`: adjust the ±15px deadzone (lines ~109-113)
- `classify_bounce()`: adjust `ratio` threshold boundaries (lines ~152-162)
- `classify_shot_elevation()`: adjust `avg_second < avg_first * 0.6` ratio (line ~185)

After editing, re-run `compare` to verify the fix. Repeat until 100%.

## Troubleshooting

### "0 DV frames" for a delivery
The `is_delivery_frame` check didn't fire during the ~3 second window when the bowler's-end camera was active. Check:
1. Is `_find_pitch_center` detecting the pitch strip? The G-R valley may need threshold tuning.
2. Is `_has_figures_at_both_ends` rejecting valid frames? Check the `_VALLEY_MAX_STD` and peak ratio thresholds in `pitch_detector.py`.
3. Was the camera angle different than expected? Some broadcasts use a batsman's-end camera.

### High detection count but wrong classification
The frames are genuine but the classifier rules are miscalibrated. Use `compare` to see raw values vs thresholds.

### Trajectory rejected (trajectory_static, trajectory_horizontal, trajectory_no_progression)
The detected ball movement didn't match a delivery pattern. This is usually correct (contaminated frames). If it's rejecting genuine deliveries, check the thresholds in `_classify_delivery` in `ball_analyzer.py`.

### is_delivery_frame parameters to tune

In `pitch_detector.py`:
- `_STRIP_MARGIN_PCT = 0.025` — width of vertical strip for figure scan
- `_VALLEY_SEARCH_LO/HI = 0.30/0.70` — where to look for clean pitch valley
- `_VALLEY_MAX_STD = 18.0` — max row-std for clean pitch (increase if genuine frames are rejected)
- `_CLEAN_BAND_MIN_PCT = 5.0` — minimum clean band height as % of frame
- `_UPPER_PEAK_RATIO = 1.8` — how much the upper figure peak must exceed the valley
- `_LOWER_PEAK_RATIO = 1.3` — how much the lower figure peak must exceed the valley (lower because batsman signal is weaker)

## Previous Chat Context

The delivery classifier was developed across chat [delivery classifier development](d0615533-db2d-480e-9f11-122fe7f8aa55). Key decisions and their rationale are documented there.

Python interpreter: `/Users/anmolmohan/opt/anaconda3/bin/python` (has OpenCV, numpy, Quartz).
