"""
Ball detection test v2: white ball color filter + frame differencing + player masking.
Isolates the white cricket ball by:
1. Masking bright white pixels (the ball) in both frames
2. Masking out large moving regions (players/fielders) via morphological dilation
3. Looking for small, fast-moving white blobs in the residual

Usage:
  python ball_diff_test_v2.py ball_test_frames/ --threshold 20
  python ball_diff_test_v2.py ball_test_clip_30fps.mp4 --start 110 --end 145
"""

import cv2
import numpy as np
import sys
import os
from glob import glob
from pathlib import Path


def detect_white_ball(frame_prev, frame_curr, crop, threshold=20):
    """
    Detect white ball by intersecting frame diff with white color mask.
    Returns candidates as (x, y, area, w, h) and debug images.
    """
    x, y, w, h = crop
    prev = frame_prev[y:y+h, x:x+w]
    curr = frame_curr[y:y+h, x:x+w]

    gray_prev = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
    gray_curr = cv2.cvtColor(curr, cv2.COLOR_BGR2GRAY)
    gray_prev = cv2.GaussianBlur(gray_prev, (3, 3), 1)
    gray_curr = cv2.GaussianBlur(gray_curr, (3, 3), 1)

    diff = cv2.absdiff(gray_curr, gray_prev)
    _, diff_mask = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)

    # White ball mask: high brightness, low saturation (white = bright + not colored)
    hsv_curr = cv2.cvtColor(curr, cv2.COLOR_BGR2HSV)
    white_mask = cv2.inRange(hsv_curr, (0, 0, 180), (180, 80, 255))

    hsv_prev = cv2.cvtColor(prev, cv2.COLOR_BGR2HSV)
    white_mask_prev = cv2.inRange(hsv_prev, (0, 0, 180), (180, 80, 255))

    # Union of white in either frame (ball was white in prev OR curr position)
    white_either = cv2.bitwise_or(white_mask, white_mask_prev)

    # Intersect: only diffs that are also white
    ball_mask = cv2.bitwise_and(diff_mask, white_either)

    # Player masking: dilate the diff to find large motion blobs (players)
    # then subtract them — players create large connected regions, ball doesn't
    player_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
    player_mask = cv2.dilate(diff_mask, player_kernel, iterations=2)
    player_mask = cv2.erode(player_mask, player_kernel, iterations=2)
    # Threshold: only regions that are consistently large
    player_contours, _ = cv2.findContours(player_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    large_mask = np.zeros_like(diff_mask)
    for c in player_contours:
        if cv2.contourArea(c) > 2000:
            cv2.drawContours(large_mask, [c], -1, 255, -1)

    # Remove player regions from ball candidates
    ball_no_players = cv2.bitwise_and(ball_mask, cv2.bitwise_not(large_mask))

    # Clean up
    clean_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    ball_clean = cv2.morphologyEx(ball_no_players, cv2.MORPH_OPEN, clean_kernel)

    # Find remaining blobs
    contours, _ = cv2.findContours(ball_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < 5 or area > 500:
            continue
        bx, by, bw, bh = cv2.boundingRect(c)
        aspect = bw / max(bh, 1)
        if aspect < 0.25 or aspect > 4.0:
            continue
        cx = bx + bw // 2
        cy = by + bh // 2
        candidates.append((cx, cy, area, bw, bh))

    candidates.sort(key=lambda c: c[2])

    debug = {
        "diff": diff,
        "diff_mask": diff_mask,
        "white_mask": white_either,
        "ball_mask": ball_mask,
        "player_mask": large_mask,
        "ball_clean": ball_clean,
    }
    return candidates, debug


def main():
    if len(sys.argv) < 2:
        print("Usage: python ball_diff_test_v2.py <frames_dir|video.mp4> [opts]")
        sys.exit(1)

    source = sys.argv[1]
    threshold = 20
    start_frame = 0
    end_frame = None
    crop_str = None

    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--threshold":
            threshold = int(args[i + 1]); i += 2
        elif args[i] == "--start":
            start_frame = int(args[i + 1]); i += 2
        elif args[i] == "--end":
            end_frame = int(args[i + 1]); i += 2
        elif args[i] == "--region":
            crop_str = args[i + 1]; i += 2
        else:
            i += 1

    # Load frames
    if os.path.isfile(source) and source.endswith((".mp4", ".mov", ".mkv")):
        cap = cv2.VideoCapture(source)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if end_frame is None:
            end_frame = total
        frames = []
        for f_idx in range(start_frame, min(end_frame, total)):
            cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
            ret, frame = cap.read()
            if ret:
                frames.append(frame)
        cap.release()
        print(f"Loaded {len(frames)} frames from video (f{start_frame}-f{end_frame})")
    else:
        paths = sorted(glob(os.path.join(source, "*.png")))
        if not paths:
            paths = sorted(glob(os.path.join(source, "*.jpg")))
        frames = [cv2.imread(p) for p in paths]
        print(f"Loaded {len(frames)} frames from directory")

    if len(frames) < 2:
        print("Need at least 2 frames")
        sys.exit(1)

    h, w = frames[0].shape[:2]

    if crop_str:
        parts = [int(x) for x in crop_str.split(",")]
        crop = tuple(parts)
    else:
        crop = (int(w * 0.1), int(h * 0.05), int(w * 0.55), int(h * 0.65))

    print(f"Crop region: x={crop[0]} y={crop[1]} w={crop[2]} h={crop[3]}")
    print(f"Threshold: {threshold}")

    out_dir = Path("ball_diff_results_v2")
    out_dir.mkdir(exist_ok=True)

    # Save crop visualization
    viz = frames[0].copy()
    cv2.rectangle(viz, (crop[0], crop[1]),
                  (crop[0] + crop[2], crop[1] + crop[3]), (0, 255, 0), 3)
    cv2.imwrite(str(out_dir / "crop_region.png"), viz)

    all_detections = []
    results_log = []

    for i in range(len(frames) - 1):
        candidates, debug = detect_white_ball(frames[i], frames[i + 1], crop, threshold)

        # Save debug images for first few and key frames
        if i < 5 or (candidates and len(candidates) <= 3):
            combined = np.hstack([
                cv2.cvtColor(debug["diff_mask"], cv2.COLOR_GRAY2BGR),
                cv2.cvtColor(debug["white_mask"], cv2.COLOR_GRAY2BGR),
                cv2.cvtColor(debug["ball_clean"], cv2.COLOR_GRAY2BGR),
            ])
            cv2.putText(combined, "diff", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(combined, "white", (crop[2] + 10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(combined, "ball", (crop[2] * 2 + 10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.imwrite(str(out_dir / f"debug_{i:03d}_{i+1:03d}.png"), combined)

        # Save blob visualization
        curr_crop = frames[i + 1][crop[1]:crop[1]+crop[3], crop[0]:crop[0]+crop[2]].copy()
        for cx, cy, area, bw, bh in candidates:
            color = (0, 255, 0) if area < 100 else (0, 165, 255)
            cv2.circle(curr_crop, (cx, cy), max(bw, bh) + 3, color, 2)
            cv2.putText(curr_crop, f"{area:.0f}", (cx + 10, cy),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        cv2.imwrite(str(out_dir / f"blobs_{i:03d}_{i+1:03d}.png"), curr_crop)

        n = len(candidates)
        log = f"Frames {i}-{i+1}: {n} candidates"
        if candidates:
            best = candidates[0]
            log += f" | best: ({best[0]},{best[1]}) area={best[2]:.0f}px²"
            all_detections.append((i + 1, best[0], best[1], best[2]))
        results_log.append(log)
        print(log)

    # Trajectory
    if all_detections:
        traj_viz = frames[0][crop[1]:crop[1]+crop[3], crop[0]:crop[0]+crop[2]].copy()
        colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
                  (255, 0, 255), (0, 255, 255), (128, 0, 255), (255, 128, 0)]
        for idx, (frame_idx, bx, by, area) in enumerate(all_detections):
            color = colors[idx % len(colors)]
            cv2.circle(traj_viz, (bx, by), 8, color, 2)
            cv2.putText(traj_viz, f"f{frame_idx}", (bx + 10, by - 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        if len(all_detections) >= 2:
            pts = [(d[1], d[2]) for d in all_detections]
            for j in range(len(pts) - 1):
                cv2.line(traj_viz, pts[j], pts[j + 1], (0, 255, 255), 1)
        cv2.imwrite(str(out_dir / "trajectory.png"), traj_viz)

    summary = [
        f"Frames: {len(frames)}",
        f"Pairs diffed: {len(frames)-1}",
        f"Threshold: {threshold}",
        f"Crop: ({crop[0]},{crop[1]}) {crop[2]}x{crop[3]}",
        f"Ball detections: {len(all_detections)}/{len(frames)-1}",
        "",
        "--- Per-pair ---",
    ] + results_log
    summary_text = "\n".join(summary)
    print(f"\n{summary_text}")
    with open(out_dir / "results.txt", "w") as f:
        f.write(summary_text)
    print(f"\nResults in {out_dir}/")


if __name__ == "__main__":
    main()
