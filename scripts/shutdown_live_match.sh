#!/usr/bin/env bash
# Graceful shutdown of live match capture stack.
# Order: Mac sender (D) -> sleep -> recorder (B) -> extractor (E)
#        -> logger (F) -> pipeline (C). UI (A) is left running.
# Run directly or schedule via `at`/sleep wrapper.

set -u

LOG=/tmp/shutdown_$(date +%Y%m%d_%H%M%S).log
exec >>"$LOG" 2>&1

stamp() { echo "[$(date '+%H:%M:%S')] $*"; }

kill_pat() {
    local label="$1"
    local pat="$2"
    local pids
    pids=$(pgrep -f "$pat" || true)
    if [ -z "$pids" ]; then
        stamp "$label: no process matching '$pat'"
        return 0
    fi
    stamp "$label: SIGINT pids=$pids"
    kill -INT $pids 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        sleep 1
        pgrep -f "$pat" >/dev/null || { stamp "$label: stopped"; return 0; }
    done
    stamp "$label: SIGTERM (escalate)"
    pkill -TERM -f "$pat" 2>/dev/null || true
    sleep 3
    if pgrep -f "$pat" >/dev/null; then
        stamp "$label: SIGKILL (final)"
        pkill -KILL -f "$pat" 2>/dev/null || true
    fi
    stamp "$label: stopped"
}

stamp "=== shutdown_live_match.sh start ==="

# 1) Mac sender (ffmpeg reading avfoundation). Stops UDP flow.
kill_pat "sender (avfoundation)" "ffmpeg.*-f avfoundation"

stamp "sleep 5 (let last keyframe traverse UDP to recorder)"
sleep 5

# 2) Recorder (ffmpeg listening on UDP 9998).
kill_pat "recorder (udp:9998)" "ffmpeg.*udp://0\.0\.0\.0:9998"

# 3) Clip extractor (bash loop).
kill_pat "clip extractor" "extract_live_clips_chunk\.sh"

# 4) Ball-by-ball logger (python).
kill_pat "ball logger" "ball_by_ball_logger\.py"

# 5) Pipeline (test_pipeline.py).
kill_pat "pipeline (test_pipeline)" "files/test_pipeline\.py"

stamp "=== shutdown complete ==="
stamp "UI (npm run dev) intentionally left running"
stamp "post-match: archive logs with"
stamp "  ARCHIVE_DIR=~/match-archives/match_\$(date +%Y%m%d_%H%M%S)"
stamp "  mkdir -p \$ARCHIVE_DIR && cp /tmp/pipeline.log /tmp/ball-log.log /tmp/live-clips.log \$ARCHIVE_DIR/ 2>/dev/null"
stamp "  cp -r ~/Projects/SportsComm/files/logs/deliveries/live_* \$ARCHIVE_DIR/ 2>/dev/null"
stamp "  cp -r ~/Projects/SportsComm/files/logs/ball_log \$ARCHIVE_DIR/ 2>/dev/null"
