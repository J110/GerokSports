#!/usr/bin/env bash
set -u

cd "$(dirname "$0")/../.."

mkdir -p files/logs/audit_chunks
echo $$ > files/logs/audit_chunks/.pid

LIVE_LOG="files/logs/pipeline-live.log"
LIVE_TRACE="files/logs/trace/live.jsonl"

cleanup() {
    rm -f files/logs/audit_chunks/.pid
    exit 0
}
trap cleanup INT TERM EXIT

while true; do
    if date -u -v-30M '+%H:%M:%S' >/dev/null 2>&1; then
        TS_START=$(date -u -v-30M '+%H:%M:%S')
    elif date -u -d '30 minutes ago' '+%H:%M:%S' >/dev/null 2>&1; then
        TS_START=$(date -u -d '30 minutes ago' '+%H:%M:%S')
    else
        TS_START="(unknown)"
    fi
    TS_END=$(date -u '+%H:%M:%S')
    CHUNK="files/logs/audit_chunks/$(date +%H%M)_audit.txt"

    {
        echo "=== AUDIT CHUNK $(date) ==="
        echo "Window: $TS_START -> $TS_END (30 min, UTC)"
        echo "Live log target: $(readlink "$LIVE_LOG" 2>/dev/null || echo "$LIVE_LOG")"
        echo

        if [ ! -f "$LIVE_LOG" ]; then
            echo "WARNING: $LIVE_LOG not found — pipeline may not be running yet."
            echo "=== END CHUNK ==="
        else
            echo "## Cold-start events"
            grep -E "cold-start|COLD_START → WARM|COLD_START -> WARM" "$LIVE_LOG" 2>/dev/null | tail -50
            echo
            echo "## WS-SCRUB / WS-PROMOTE (B2 fix)"
            grep -E "WS-SCRUB|WS-PROMOTE" "$LIVE_LOG" 2>/dev/null | tail -50
            echo "WS-SCRUB count: $(grep -c WS-SCRUB "$LIVE_LOG" 2>/dev/null || echo 0)"
            echo "WS-PROMOTE count: $(grep -c WS-PROMOTE "$LIVE_LOG" 2>/dev/null || echo 0)"
            echo
            echo "## DIRECT-SM-REJECT (last 30)"
            grep DIRECT-SM-REJECT "$LIVE_LOG" 2>/dev/null | tail -30
            echo "Total: $(grep -c DIRECT-SM-REJECT "$LIVE_LOG" 2>/dev/null || echo 0)"
            echo
            echo "## STRIKER-ALIGN-FALLBACK count"
            grep -c STRIKER-ALIGN-FALLBACK "$LIVE_LOG" 2>/dev/null || echo 0
            echo
            echo "## BALLS-CEILING-GATE physics violations"
            grep BALLS-CEILING-GATE "$LIVE_LOG" 2>/dev/null | tail -10
            echo
            echo "## SCORE-CONSENSUS / pending events"
            grep -E "SCORE-CONSENSUS|_pending_score" "$LIVE_LOG" 2>/dev/null | tail -20
            echo
            echo "## Tracebacks / CRITICAL / ERROR (last 20)"
            grep -E "Traceback|CRITICAL|ERROR" "$LIVE_LOG" 2>/dev/null | tail -20
            echo
            echo "## Trace anomalies (P1-P9 — full trace, --window-minutes not supported, scanning whole file)"
            if [ -f "$LIVE_TRACE" ]; then
                TMP_REPORT="files/logs/audit_chunks/.tmp_$(date +%H%M)_report.md"
                python files/analyze_trace.py "$LIVE_TRACE" --report "$TMP_REPORT" 2>&1 | head -40 || true
                if [ -f "$TMP_REPORT" ]; then
                    head -100 "$TMP_REPORT"
                    rm -f "$TMP_REPORT"
                fi
            else
                echo "(trace file $LIVE_TRACE not found)"
            fi
            echo
            echo "## Latest scoreboard state (last 5 STATE: lines)"
            grep -E "STATE: " "$LIVE_LOG" 2>/dev/null | tail -5
            echo
            echo "=== END CHUNK ==="
        fi
    } > "$CHUNK" 2>&1

    echo "[audit_dumper] wrote $CHUNK"
    sleep 1800
done
