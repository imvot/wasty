#!/usr/bin/env bash
# Sync the current git checkout onto the Pi install and restart wasty.
#
# Typical loop on the Pi:
#   cd ~/wasty
#   git pull
#   sudo scripts/update.sh
#
# From a laptop (optional):
#   ssh wasty@<pi> 'cd ~/wasty && git pull && sudo scripts/update.sh'
#
# Reinstall (pip / apt / systemd) is only needed when dependencies or the
# unit file change — this script detects pyproject.toml changes and re-runs
# the editable install; unit-file changes trigger daemon-reload.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run as root: sudo $0" >&2
    exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR=/opt/wasty/app
VENV_DIR=/opt/wasty/venv

if [[ ! -d "$APP_DIR" || ! -x "$VENV_DIR/bin/python" ]]; then
    echo "Wasty is not installed yet. Run: sudo scripts/install.sh" >&2
    exit 1
fi

if [[ ! -f "$REPO_DIR/webui/dist/index.html" ]]; then
    echo "!! $REPO_DIR/webui/dist/index.html missing — pull/build the SPA first" >&2
    exit 1
fi

old_pyproject=""
[[ -f "$APP_DIR/pyproject.toml" ]] && old_pyproject=$(cksum "$APP_DIR/pyproject.toml" | awk '{print $1" "$2}')
old_unit=""
[[ -f /etc/systemd/system/wasty.service ]] && old_unit=$(cksum /etc/systemd/system/wasty.service | awk '{print $1" "$2}')

echo "==> sync ${REPO_DIR} -> ${APP_DIR}"
rsync -a --delete \
    --exclude .git \
    --exclude .venv \
    --exclude .venv-dev \
    --exclude webui/node_modules \
    --exclude config/local.yaml \
    "$REPO_DIR/" "$APP_DIR/"

new_pyproject=$(cksum "$APP_DIR/pyproject.toml" | awk '{print $1" "$2}')
if [[ "$old_pyproject" != "$new_pyproject" ]]; then
    echo "==> pyproject.toml changed — refreshing editable install"
    "$VENV_DIR/bin/pip" install -e "${APP_DIR}[pi]"
fi

if ! cmp -s "$APP_DIR/systemd/wasty.service" /etc/systemd/system/wasty.service; then
    echo "==> systemd unit changed"
    cp "$APP_DIR/systemd/wasty.service" /etc/systemd/system/wasty.service
    systemctl daemon-reload
fi

echo "==> restart wasty"
systemctl restart wasty
sleep 1
systemctl --no-pager --full status wasty || true

echo
echo "Updated. SPA path / health: wastyctl status"
echo "Logs: journalctl -u wasty -f"
