#!/usr/bin/env bash
# qrackpot deploy script — idempotent
# Run from /mnt/data/sportscomm after git pull

set -euo pipefail

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
sudo systemctl reload caddy

echo "[deploy] systemd units"
for unit in deploy/systemd/*.service; do
    name=$(basename "$unit")
    sudo cp "$unit" /etc/systemd/system/$name
done
sudo systemctl daemon-reload

echo "[deploy] enable UI"
sudo systemctl enable ui.service
sudo systemctl restart ui.service

echo "[deploy] DONE"
echo "[deploy] UI: $(sudo systemctl is-active ui.service)"
echo "[deploy] Caddy: $(sudo systemctl is-active caddy)"
