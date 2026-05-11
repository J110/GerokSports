#!/usr/bin/env bash
# Grab a one-shot bundle of server logs + latest detections + last 5 clip mp4 sidecars
# Writes to ~/qrackpot-snapshots/snapshot_<TS>.tar.gz so you can drop it into chat.
#
# Usage:   bash scripts/grab_logs.sh
#          bash scripts/grab_logs.sh --lines 2000   # bigger tail
#
# Requires gcloud SSH access to qrackpot-prod-1.

set -euo pipefail

LINES="${LINES:-1000}"
if [ "${1:-}" = "--lines" ] && [ -n "${2:-}" ]; then
    LINES="$2"
fi

TS="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="$HOME/qrackpot-snapshots"
BUNDLE_DIR="$OUT_DIR/snapshot_$TS"
mkdir -p "$BUNDLE_DIR"

echo "[grab] pulling last $LINES lines of each server log..."

gcloud compute ssh qrackpot-prod-1 \
  --zone=asia-south1-a \
  --tunnel-through-iap \
  --command="
    set +e
    cd /var/log/sportscomm
    for f in pipeline.log pipeline-err.log recorder.log recorder-err.log live-clips.log live-clips-err.log ui.log ui-err.log; do
        if [ -f \"\$f\" ]; then
            echo '===== '\$f' (last $LINES) ====='
            sudo tail -n $LINES \"\$f\"
            echo
        fi
    done
    echo '===== systemd: pipeline.service ====='
    sudo systemctl status pipeline.service --no-pager -n 20 || true
    echo
    echo '===== systemd: recorder.service ====='
    sudo systemctl status recorder.service --no-pager -n 20 || true
    echo
    echo '===== systemd: live-clips.service ====='
    sudo systemctl status live-clips.service --no-pager -n 20 || true
    echo
    echo '===== latest live_clips listing ====='
    sudo ls -lt /mnt/data/sportscomm/files/logs/live_clips/ 2>/dev/null | head -30 || true
    echo
    echo '===== latest detections JSON contents ====='
    LATEST=\$(sudo ls -t /mnt/data/sportscomm/files/logs/live_clips/*_detections.json 2>/dev/null | head -1)
    if [ -n \"\$LATEST\" ]; then
        echo \"# file: \$LATEST\"
        sudo cat \"\$LATEST\"
    else
        echo '(no detections JSON yet)'
    fi
    echo
    echo '===== last 5 clip sidecar JSONs ====='
    for j in \$(sudo ls -t /mnt/data/sportscomm/files/logs/live_clips/clip_anchor*.json 2>/dev/null | head -5); do
        echo \"# file: \$j\"
        sudo cat \"\$j\"
        echo
    done
    echo '===== pipeline.env (masked) ====='
    sudo grep -vE 'KEY|TOKEN|SECRET' /etc/sportscomm/pipeline.env || true
  " > "$BUNDLE_DIR/snapshot.txt" 2>&1

tar -czf "$OUT_DIR/snapshot_$TS.tar.gz" -C "$OUT_DIR" "snapshot_$TS"
rm -rf "$BUNDLE_DIR"

echo
echo "[grab] bundle: $OUT_DIR/snapshot_$TS.tar.gz"
echo "[grab] preview:"
tar -tzf "$OUT_DIR/snapshot_$TS.tar.gz"
echo
echo "[grab] Drag the .tar.gz into the chat OR run:"
echo "       open $OUT_DIR"
