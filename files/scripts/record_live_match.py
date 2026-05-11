#!/usr/bin/env python3
"""Record live match from UGREEN HDMI->USB capture card.

Usage:
    cd files
    python scripts/record_live_match.py
    python scripts/record_live_match.py --duration 14400  # 4-hour cap
    python scripts/record_live_match.py --device-name "USB"  # custom

Output:
    files/logs/deliveries/<YYYYMMDD_HHMMSS>/match_<session>.mp4

Encoder settings (vs the prior 4Mbps recording):
    - libx264 -preset medium -crf 18 (visually lossless)
    - audio: aac 192k stereo
    - file size will be ~3x the prior 4Mbps recording but the
      cricket fast-pan artifacts go away.

Stop the recording with Ctrl-C. ffmpeg writes fragmented mp4;
moov+moofs available from t=0 so ffprobe works mid-stream.
"""
from __future__ import annotations

import argparse
import datetime
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DELIVERIES_DIR = ROOT / "logs" / "deliveries"


def list_avfoundation_devices() -> str:
    """Run ffmpeg device list, return the stderr block."""
    cmd = ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stderr


def find_capture_card(device_list_output: str, name_hint: str = "USB") -> str | None:
    """Parse ffmpeg device list, return the video device index matching hint."""
    in_video = False
    for line in device_list_output.splitlines():
        if "AVFoundation video devices" in line:
            in_video = True
            continue
        if "AVFoundation audio devices" in line:
            in_video = False
            continue
        if not in_video:
            continue
        # Lines look like: [AVFoundation indev @ 0x...] [1] UGREEN USB Capture
        m = re.search(r"\[(\d+)\]\s+(.+)$", line)
        if not m:
            continue
        idx, name = m.group(1), m.group(2).strip()
        if name_hint.lower() in name.lower():
            return idx
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=18000,
                        help="Max recording duration in seconds (default 5h)")
    parser.add_argument("--device-name", default="USB",
                        help="Substring of capture card name (default 'USB')")
    parser.add_argument("--device-index", default=None,
                        help="Override avfoundation video device index")
    parser.add_argument("--audio-index", default=None,
                        help="Override avfoundation audio device index")
    parser.add_argument("--no-audio", action="store_true",
                        help="Skip audio capture")
    parser.add_argument("--bitrate", default="12M",
                        help="Override video bitrate target (default 12M)")
    parser.add_argument("--use-crf", action="store_true",
                        help="Use CRF 18 instead of fixed bitrate")
    parser.add_argument("--fps", type=int, default=30,
                        help="Capture framerate (default 30)")
    parser.add_argument("--resolution", default="1920x1080",
                        help="Capture resolution (default 1920x1080)")
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        print("ERROR: ffmpeg not found in PATH", file=sys.stderr)
        return 2

    # Auto-detect device unless overridden
    if args.device_index is None:
        print("[record] enumerating avfoundation devices...")
        dev_list = list_avfoundation_devices()
        idx = find_capture_card(dev_list, args.device_name)
        if idx is None:
            print("[record] could not auto-detect capture card. "
                  f"Looked for '{args.device_name}' in:")
            print(dev_list)
            print("\nUse --device-index <N> with the index from the list above.")
            return 3
        args.device_index = idx
        print(f"[record] auto-detected capture card at video index {idx}")

    # Output path
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = uuid.uuid4().hex[:8]
    out_dir = DELIVERIES_DIR / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"match_{session_id}.mp4"

    # Build ffmpeg input spec: video[:audio]
    if args.no_audio:
        input_spec = f"{args.device_index}:none"
    elif args.audio_index is not None:
        input_spec = f"{args.device_index}:{args.audio_index}"
    else:
        # avfoundation audio index 0 is usually the first audio device.
        # If your capture card carries audio over HDMI, it's typically at
        # the same name as video; otherwise use system mic. Default safe
        # to 0 here; user can override with --audio-index.
        input_spec = f"{args.device_index}:0"

    cmd = [
        "ffmpeg",
        "-f", "avfoundation",
        "-framerate", str(args.fps),
        "-video_size", args.resolution,
        "-pixel_format", "uyvy422",  # native UGREEN format
        "-i", input_spec,
        "-c:v", "libx264",
        "-preset", "medium",
        "-pix_fmt", "yuv420p",
    ]
    if args.use_crf:
        cmd += ["-crf", "18"]
    else:
        cmd += ["-b:v", args.bitrate, "-maxrate", args.bitrate,
                "-bufsize", "24M"]
    cmd += [
        "-c:a", "aac",
        "-b:a", "192k",
        "-ac", "2",
        "-t", str(args.duration),
        "-movflags", "+frag_keyframe+empty_moov+default_base_moof",
        "-frag_duration", "1000000",
        "-y",
        str(out_path),
    ]

    print(f"[record] writing to {out_path}")
    print(f"[record] cmd: {shlex.join(cmd)}")
    print(f"[record] press Ctrl-C to stop cleanly\n")

    proc = subprocess.Popen(cmd)
    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\n[record] received Ctrl-C, sending SIGINT to ffmpeg...")
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            print("[record] ffmpeg did not exit cleanly, sending SIGTERM...")
            proc.terminate()
            proc.wait()

    if out_path.exists():
        size_mb = out_path.stat().st_size / (1024 * 1024)
        print(f"\n[record] saved {out_path} ({size_mb:.1f} MB)")
        # Verify with ffprobe
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=width,height,r_frame_rate,bit_rate",
             "-of", "default=noprint_wrappers=1",
             str(out_path)],
            capture_output=True, text=True)
        print(probe.stdout)
    else:
        print("[record] WARNING: output file not written")
        return 4

    return 0


if __name__ == "__main__":
    sys.exit(main())
