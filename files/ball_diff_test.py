"""
Quick ball detection test via frame differencing.
Point this at a folder of consecutive broadcast frames captured during a delivery.

Usage:
  python ball_diff_test.py /path/to/frames/
  python ball_diff_test.py /path/to/frames/ --threshold 25

Frames should be consecutive PNGs from the broadcast, captured during a delivery
(bowler running in → ball reaching batter). Ideally 5-15 frames, ~200-300ms apart.

Outputs:
  ball_diff_results/
  ├── diff_001_002.png      # Raw difference image
  ├── blobs_001_002.png     # Detected blobs highlighted
  ├── trajectory.png        # All detected ball positions overlaid on pitch
  └── results.txt           # Summary
"""

import cv2
import numpy as np
import sys
import os
from glob import glob
from pathlib import Path

def find_pitch_region(frame, region_str=None):
    """Find the pitch area. Uses explicit region if given, otherwise auto-detect."""
    h, w = frame.shape[:2]

    if region_str:
        parts = [int(x) for x in region_str.split(",")]
        return parts[0], parts[1], parts[2], parts[3]

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (25, 20, 30), (90, 255, 255))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if contours:
        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        if area > (w * h * 0.01):
            x, y, rw, rh = cv2.boundingRect(largest)
            return x, y, rw, rh

    # Fallback: use center 60% of frame (where pitch typically is)
    return int(w * 0.15), int(h * 0.1), int(w * 0.7), int(h * 0.7)

def detect_ball(crop_prev, crop_curr, threshold=35):
    """Detect ball by frame differencing. Returns list of (x, y, area) candidates."""
    gray_prev = cv2.cvtColor(crop_prev, cv2.COLOR_BGR2GRAY)
    gray_curr = cv2.cvtColor(crop_curr, cv2.COLOR_BGR2GRAY)
    
    # Blur to reduce noise
    gray_prev = cv2.GaussianBlur(gray_prev, (5, 5), 1.5)
    gray_curr = cv2.GaussianBlur(gray_curr, (5, 5), 1.5)
    
    # Frame difference
    diff = cv2.absdiff(gray_curr, gray_prev)
    
    # Threshold
    _, binary = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)
    
    # Clean up noise
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    
    # Find blobs
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    candidates = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < 10 or area > 800:  # Ball should be ~15-100px² in crop
            continue
        x, y, w, h = cv2.boundingRect(c)
        aspect = w / max(h, 1)
        if aspect < 0.3 or aspect > 3.0:  # Roughly circular
            continue
        cx = x + w // 2
        cy = y + h // 2
        candidates.append((cx, cy, area, w, h))
    
    # Sort by area (smallest qualifying blob is most likely the ball)
    candidates.sort(key=lambda c: c[2])
    
    return candidates, diff, binary

def frames_from_video(video_path, fps=10):
    """Extract frames from a video file at the given fps."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Cannot open video: {video_path}")
        sys.exit(1)
    vid_fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, int(vid_fps / fps))
    frames = []
    idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % step == 0:
            frames.append(frame)
        idx += 1
    cap.release()
    return frames


def main():
    if len(sys.argv) < 2:
        print("Usage: python ball_diff_test.py /path/to/frames_or_video [--threshold 35] [--region x,y,w,h]")
        sys.exit(1)
    
    frames_dir = sys.argv[1]
    threshold = 35
    region_str = None
    if "--threshold" in sys.argv:
        threshold = int(sys.argv[sys.argv.index("--threshold") + 1])
    if "--region" in sys.argv:
        region_str = sys.argv[sys.argv.index("--region") + 1]

    # Load frames — from directory or video file
    source = frames_dir
    if os.path.isfile(source) and source.endswith((".mp4", ".mov", ".mkv", ".webm")):
        frames = frames_from_video(source, fps=10)
        print(f"Extracted {len(frames)} frames from video, threshold={threshold}")
    else:
        frame_paths = sorted(glob(os.path.join(source, "*.png")))
        if not frame_paths:
            frame_paths = sorted(glob(os.path.join(source, "*.jpg")))
        if len(frame_paths) < 2:
            print(f"Need at least 2 frames, found {len(frame_paths)}")
            sys.exit(1)
        print(f"Found {len(frame_paths)} frames, threshold={threshold}")
        frames = [cv2.imread(p) for p in frame_paths]
    
    # Find pitch region from first frame
    px, py, pw, ph = find_pitch_region(frames[0], region_str)
    print(f"Pitch region: x={px} y={py} w={pw} h={ph}")
    
    # Output directory
    out_dir = Path("ball_diff_results")
    out_dir.mkdir(exist_ok=True)
    
    # Save pitch crop visualization
    viz = frames[0].copy()
    cv2.rectangle(viz, (px, py), (px+pw, py+ph), (0, 255, 0), 2)
    cv2.imwrite(str(out_dir / "pitch_region.png"), viz)
    
    # Process consecutive frame pairs
    all_detections = []  # (frame_idx, x, y, area)
    results_log = []
    
    for i in range(len(frames) - 1):
        crop_prev = frames[i][py:py+ph, px:px+pw]
        crop_curr = frames[i+1][py:py+ph, px:px+pw]
        
        candidates, diff, binary = detect_ball(crop_prev, crop_curr, threshold)
        
        # Save diff visualization
        diff_color = cv2.applyColorMap(diff, cv2.COLORMAP_JET)
        cv2.imwrite(str(out_dir / f"diff_{i:03d}_{i+1:03d}.png"), diff_color)
        
        # Save blob visualization
        blob_viz = crop_curr.copy()
        for cx, cy, area, w, h in candidates:
            color = (0, 255, 0) if area < 200 else (0, 165, 255)  # Green=small(ball?), Orange=large(fielder?)
            cv2.circle(blob_viz, (cx, cy), max(w, h), color, 2)
            cv2.putText(blob_viz, f"{area}px", (cx+10, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        cv2.imwrite(str(out_dir / f"blobs_{i:03d}_{i+1:03d}.png"), blob_viz)
        
        n_candidates = len(candidates)
        log = f"Frames {i}-{i+1}: {n_candidates} candidates"
        if candidates:
            best = candidates[0]  # Smallest blob
            log += f" | best: ({best[0]},{best[1]}) area={best[2]}px²"
            all_detections.append((i+1, best[0], best[1], best[2]))
        results_log.append(log)
        print(log)
    
    # Trajectory visualization
    if all_detections:
        traj_viz = frames[0][py:py+ph, px:px+pw].copy()
        colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), 
                  (255, 0, 255), (0, 255, 255), (128, 0, 255), (255, 128, 0)]
        
        for idx, (frame_idx, x, y, area) in enumerate(all_detections):
            color = colors[idx % len(colors)]
            cv2.circle(traj_viz, (x, y), 8, color, 2)
            cv2.putText(traj_viz, f"f{frame_idx}", (x+10, y-5), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        
        # Draw trajectory line
        if len(all_detections) >= 2:
            pts = [(d[1], d[2]) for d in all_detections]
            for j in range(len(pts) - 1):
                cv2.line(traj_viz, pts[j], pts[j+1], (0, 255, 255), 1)
        
        cv2.imwrite(str(out_dir / "trajectory.png"), traj_viz)
    
    # Summary
    summary = [
        f"Frames processed: {len(frames)}",
        f"Frame pairs diffed: {len(frames)-1}",
        f"Threshold: {threshold}",
        f"Pitch crop: ({px},{py}) {pw}x{ph}",
        f"Total ball detections: {len(all_detections)}",
        f"Detection rate: {len(all_detections)}/{len(frames)-1} pairs",
        "",
        "--- Per-pair results ---",
    ] + results_log
    
    summary_text = "\n".join(summary)
    print(f"\n{summary_text}")
    
    with open(out_dir / "results.txt", "w") as f:
        f.write(summary_text)
    
    print(f"\nResults saved to {out_dir}/")
    print(f"Check: trajectory.png, diff_*.png, blobs_*.png")

if __name__ == "__main__":
    main()
