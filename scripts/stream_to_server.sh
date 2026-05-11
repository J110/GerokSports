#!/usr/bin/env bash
# Stream Mac's UGREEN capture card → SRT to qrackpot server
# while simultaneously recording locally for archive.
#
# Usage:  bash scripts/stream_to_server.sh

set -euo pipefail

SERVER_IP="34.14.170.238"
SERVER_PORT="9999"
LOCAL_REC_DIR="${LOCAL_REC_DIR:-$HOME/Recordings/qrackpot}"
mkdir -p "$LOCAL_REC_DIR"

TS=$(date +%Y%m%d_%H%M%S)
LOCAL_MP4="$LOCAL_REC_DIR/match_${TS}.mp4"

DEVICE_INDEX="${DEVICE_INDEX:-0}"

echo "[stream] Source: avfoundation device $DEVICE_INDEX"
echo "[stream] Server: srt://$SERVER_IP:$SERVER_PORT"
echo "[stream] Local archive: $LOCAL_MP4"
echo "[stream] Press Ctrl-C to stop (cleanly closes both outputs)"
echo

cleanup() {
    echo
    echo "[stream] stopping..."
}
trap cleanup INT TERM

ffmpeg \
    -f avfoundation \
    -framerate 30 \
    -video_size 1920x1080 \
    -pixel_format uyvy422 \
    -i "$DEVICE_INDEX:0" \
    -c:v libx264 -preset veryfast -tune zerolatency -b:v 6M -maxrate 6M -bufsize 12M \
    -c:a aac -b:a 128k -ac 2 \
    -map 0 -f mpegts "srt://${SERVER_IP}:${SERVER_PORT}?streamid=qrackpot_live" \
    -map 0 -c copy -movflags +frag_keyframe+empty_moov+default_base_moof \
    -frag_duration 1000000 \
    "$LOCAL_MP4"
