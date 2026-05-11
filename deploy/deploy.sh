#!/usr/bin/env bash
# qrackpot deploy script — idempotent, self-healing
# Run from /mnt/data/sportscomm after git pull

set -euo pipefail

LOG() { echo "[$(date '+%H:%M:%S')] $*"; }
DEPLOY_START=$SECONDS
trap 'LOG "FAILED after ${SECONDS}s: line $LINENO"' ERR

# Defensive cleanup: kill any stale hung deploy / systemctl reload from prior runs
for pid in $(pgrep -f "deploy.sh" | grep -v $$); do
    sudo kill -9 "$pid" 2>/dev/null || true
done
for pid in $(pgrep -f "systemctl reload caddy"); do
    sudo kill -9 "$pid" 2>/dev/null || true
done
sudo systemctl reset-failed caddy 2>/dev/null || true

# Self-heal: if caddy is wedged in reloading state, restart instead
caddy_state=$(systemctl show caddy --property=ActiveState --value 2>/dev/null)
caddy_substate=$(systemctl show caddy --property=SubState --value 2>/dev/null)
if [ "$caddy_substate" = "reloading" ]; then
    LOG "Caddy wedged in reloading state — forcing restart"
    sudo systemctl reset-failed caddy
    sudo systemctl restart caddy
    sleep 3
fi

REPO_ROOT="/mnt/data/sportscomm"
cd "$REPO_ROOT"

step_start=$SECONDS
LOG "python venv + deps START"
if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
LOG "python venv + deps END ($((SECONDS - step_start))s)"

step_start=$SECONDS
LOG "UI build START"
cd scorecard-ui
npm ci
npm run build
cd ..
LOG "UI build END ($((SECONDS - step_start))s)"

step_start=$SECONDS
LOG "log/runtime dirs START"
sudo mkdir -p /var/log/sportscomm /etc/sportscomm
sudo chown -R $USER:$USER /var/log/sportscomm
LOG "log/runtime dirs END ($((SECONDS - step_start))s)"

step_start=$SECONDS
LOG "Caddyfile START"
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile

LOG "validating Caddyfile"
if ! sudo caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1; then
    sudo caddy validate --config /etc/caddy/Caddyfile
    exit 1
fi
LOG "reloading caddy (10s timeout)"
if ! timeout 10s sudo systemctl reload caddy; then
    LOG "reload failed/timeout — restarting caddy instead"
    sudo systemctl restart caddy
    sleep 2
fi
LOG "Caddyfile END ($((SECONDS - step_start))s)"

step_start=$SECONDS
LOG "systemd units START"
for unit in deploy/systemd/*.service; do
    name=$(basename "$unit")
    sudo install -m 0644 -o root -g root "$unit" "/etc/systemd/system/$name"
done
sudo systemctl daemon-reload
LOG "systemd units END ($((SECONDS - step_start))s)"

step_start=$SECONDS
LOG "enable UI START"
sudo systemctl enable ui.service
sudo systemctl restart ui.service
LOG "enable UI END ($((SECONDS - step_start))s)"

LOG "UI: $(sudo systemctl is-active ui.service)"
LOG "Caddy: $(sudo systemctl is-active caddy)"

LOG "pipeline.service"
if [ ! -f /etc/sportscomm/pipeline.env ]; then
    LOG "  /etc/sportscomm/pipeline.env missing — skipping pipeline.service start"
    LOG "  (operator: copy from deploy/pipeline.env.example and fill in secrets)"
else
    sudo systemctl enable pipeline.service recorder.service live-clips.service
    sudo systemctl restart pipeline.service recorder.service live-clips.service
    sleep 3
    for svc in pipeline.service recorder.service live-clips.service; do
        if systemctl is-active --quiet "$svc"; then
            LOG "  $svc active"
        else
            LOG "  $svc failed — check journalctl -u $svc"
            sudo journalctl -u "$svc" -n 30 --no-pager
        fi
    done
fi

LOG "health check"
health_ok=0
for i in 1 2 3; do
    if curl -fsS -o /dev/null https://qrackpot.com/; then
        LOG "qrackpot.com responsive (attempt $i)"
        health_ok=1
        break
    fi
    sleep 2
done
if [ "$health_ok" -ne 1 ]; then
    LOG "WARN: qrackpot.com health check failed after 3 attempts"
fi

LOG "DONE in ${SECONDS}s"
