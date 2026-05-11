#!/usr/bin/env bash
# Live launch wrapper:
#   - exports SHADOW_DELIVERY_DETECTOR=1
#   - starts the recorder in background
#   - starts the eyes pipeline in foreground
#   - on Ctrl-C, SIGINTs the recorder first so the moov writes cleanly
#
# Override defaults via env:
#   PROD_ENTRY (default: python -m eyes.main; set to "python files/test_pipeline.py" to use that)
#   RECORDER_DURATION_S (default: 18000 — 5h)
#
# To target a specific cricbuzz match:
#   CRICBUZZ_MATCH_ID=<id> ./start_live_match.sh
# (or pass --match-id <id> if invoking test_pipeline.py directly)

set -euo pipefail

cd "$(dirname "$0")/../.."  # repo root

export SHADOW_DELIVERY_DETECTOR=1
export BMF_SESSION_ID="${BMF_SESSION_ID:-live_$(date +%Y%m%d_%H%M%S)}"
export SCOUT_RAW_DUMP=1
export PYTHONUNBUFFERED=1

PROD_ENTRY="${PROD_ENTRY:-python -m eyes.main}"
RECORDER_DURATION_S="${RECORDER_DURATION_S:-18000}"

mkdir -p files/logs files/logs/trace "files/logs/deliveries/${BMF_SESSION_ID}"

echo "[start_live_match] SHADOW_DELIVERY_DETECTOR=$SHADOW_DELIVERY_DETECTOR"
echo "[start_live_match] BMF_SESSION_ID=$BMF_SESSION_ID"
echo "[start_live_match] SCOUT_RAW_DUMP=$SCOUT_RAW_DUMP"
echo "[start_live_match] starting recorder (--duration $RECORDER_DURATION_S)"

python files/scripts/record_live_match.py \
    --duration "$RECORDER_DURATION_S" \
    "$@" &
RECORDER_PID=$!
echo "[start_live_match] recorder PID=$RECORDER_PID"

cleanup() {
    echo
    echo "[start_live_match] received signal, stopping recorder PID=$RECORDER_PID"
    if kill -0 "$RECORDER_PID" 2>/dev/null; then
        kill -INT "$RECORDER_PID" || true
        # give it up to 15s to flush moov
        for _ in $(seq 1 15); do
            kill -0 "$RECORDER_PID" 2>/dev/null || break
            sleep 1
        done
        if kill -0 "$RECORDER_PID" 2>/dev/null; then
            echo "[start_live_match] recorder still running, sending SIGTERM"
            kill -TERM "$RECORDER_PID" || true
        fi
    fi
    wait "$RECORDER_PID" 2>/dev/null || true
    echo "[start_live_match] recorder stopped"
}
trap cleanup INT TERM EXIT

LOG_TS="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="files/logs/pipeline-${LOG_TS}.log"
mkdir -p files/logs

ln -sfn "pipeline-${LOG_TS}.log" "files/logs/pipeline-live.log"
ln -sfn "${BMF_SESSION_ID}.jsonl" "files/logs/trace/live.jsonl"

echo "============================================================"
echo "[start_live_match] LIVE PATHS (grep these mid-match):"
echo "  pipeline log    : $LOG_FILE"
echo "  pipeline alias  : files/logs/pipeline-live.log"
echo "  trace alias     : files/logs/trace/live.jsonl"
echo "  trace target    : files/logs/trace/${BMF_SESSION_ID}.jsonl"
echo "  scout_raw       : files/logs/deliveries/${BMF_SESSION_ID}/scout_raw.jsonl"
echo "  recorder mp4    : files/logs/deliveries/${BMF_SESSION_ID}/match_<id>.mp4"
echo "============================================================"
echo "[start_live_match] starting prod pipeline: $PROD_ENTRY"
$PROD_ENTRY 2>&1 | tee "$LOG_FILE"

# When prod exits naturally, trap EXIT handler still cleans up recorder.
