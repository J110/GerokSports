#!/usr/bin/env bash
# qrackpot deploy script — idempotent
# Run from /mnt/data/sportscomm after git pull

set -euo pipefail

# Defensive cleanup: kill any stale hung deploy / systemctl reload from prior runs
for pid in $(pgrep -f "deploy.sh" | grep -v $$); do
    sudo kill -9 "$pid" 2>/dev/null || true
done
for pid in $(pgrep -f "systemctl reload caddy"); do
    sudo kill -9 "$pid" 2>/dev/null || true
done
sudo systemctl reset-failed caddy 2>/dev/null || true

REPO_ROOT="/mnt/data/sportscomm"
cd "$REPO_ROOT"

echo "[deploy] python venv + deps"
if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "[deploy] UI build"
cd scorecard-ui
npm ci
npm run build
cd ..

echo "[deploy] log/runtime dirs"
sudo mkdir -p /var/log/sportscomm /etc/sportscomm
sudo chown -R $USER:$USER /var/log/sportscomm

echo "[deploy] Caddyfile"
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile

# Validate before reload — fail fast on bad config
if ! sudo caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1; then
    echo "[deploy] ERROR: Caddyfile failed validation"
    sudo caddy validate --config /etc/caddy/Caddyfile
    exit 1
fi

# Bounded reload — if it doesn't return in 30s, kill and report
if ! timeout 30s sudo systemctl reload caddy; then
    echo "[deploy] ERROR: caddy reload timed out or failed"
    sudo journalctl -u caddy -n 30 --no-pager
    exit 1
fi
echo "[deploy] caddy reloaded OK"

echo "[deploy] systemd units"
for unit in deploy/systemd/*.service; do
    name=$(basename "$unit")
    sudo install -m 0644 -o root -g root "$unit" "/etc/systemd/system/$name"
done
sudo systemctl daemon-reload

echo "[deploy] enable UI"
sudo systemctl enable ui.service
sudo systemctl restart ui.service

echo "[deploy] DONE"
echo "[deploy] UI: $(sudo systemctl is-active ui.service)"
echo "[deploy] Caddy: $(sudo systemctl is-active caddy)"
