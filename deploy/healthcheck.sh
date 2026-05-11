#!/usr/bin/env bash
# qrackpot stack health check — exits 0 if healthy, non-zero on failure

set -uo pipefail

LOG() { echo "[$(date '+%H:%M:%S')] $*"; }

fail=0

check() {
    local name="$1"; shift
    if "$@" >/dev/null 2>&1; then
        LOG "OK   $name"
    else
        LOG "FAIL $name"
        fail=1
    fi
}

check "caddy active"         systemctl is-active --quiet caddy
check "ui.service active"    systemctl is-active --quiet ui.service
check "https qrackpot.com"   curl -fsS -o /dev/null https://qrackpot.com/
check "https api.qrackpot"   curl -fsS -o /dev/null -m 5 https://api.qrackpot.com/ -H "Connection: close" || true
check "ui port 3000"         curl -fsS -o /dev/null http://localhost:3000/

caddy_substate=$(systemctl show caddy --property=SubState --value 2>/dev/null)
if [ "$caddy_substate" = "reloading" ]; then
    LOG "FAIL caddy wedged in reloading state"
    fail=1
fi

if [ "$fail" -eq 0 ]; then
    LOG "stack healthy"
    exit 0
else
    LOG "stack unhealthy"
    exit 1
fi
