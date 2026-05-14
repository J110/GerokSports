#!/usr/bin/env bash
# Stream a local mp4 to qrackpot server via SRT (test the SRT path)
# Usage:  bash scripts/stream_to_server_test.sh /path/to/file.mp4

set -euo pipefail

SERVER_IP="34.14.170.238"
SERVER_PORT="9999"     # pipeline.service / UDPFrameSource
RECORDER_PORT="9998"   # recorder.service / mpegts .ts archive for Track 2 clip extraction

INPUT="${1:-files/logs/deliveries/6ff41b76/match_6ff41b76.mp4}"
if [ ! -f "$INPUT" ]; then
    echo "ERROR: input file not found: $INPUT"
    exit 1
fi

echo "[stream-test] Source: $INPUT"
echo "[stream-test] Pipeline:  udp://$SERVER_IP:$SERVER_PORT"
echo "[stream-test] Recorder:  udp://$SERVER_IP:$RECORDER_PORT"
echo "[stream-test] Streaming at real-time pace (-re), 5 min, Ctrl-C to stop"
echo

ffmpeg \
    -re \
    -i "$INPUT" \
    -t 300 \
    -c:v libx264 -preset veryfast -tune zerolatency -b:v 6M \
    -bsf:v dump_extra \
    -force_key_frames "expr:gte(t,n_forced*2)" \
    -c:a aac -b:a 128k \
    -map 0 -f mpegts "udp://${SERVER_IP}:${SERVER_PORT}?pkt_size=1316" \
    -map 0 -f mpegts "udp://${SERVER_IP}:${RECORDER_PORT}?pkt_size=1316"
