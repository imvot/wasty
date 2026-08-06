#!/usr/bin/env bash
# Wasty installer for Raspberry Pi OS Bookworm (run on the Pi, as root).
#
#   sudo scripts/install.sh
#
# Installs: apt deps, MediaMTX binary, a venv at /opt/wasty/venv with an
# editable install of the app at /opt/wasty/app, and the systemd unit.
#
# After this, day-to-day updates are:  sudo scripts/update.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run as root: sudo $0" >&2
    exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR=/opt/wasty/app
VENV_DIR=/opt/wasty/venv
MEDIAMTX_VERSION="${MEDIAMTX_VERSION:-v1.15.5}"
ARCH=arm64

echo "==> apt dependencies"
apt-get update
apt-get install -y --no-install-recommends \
    python3-venv python3-picamera2 ffmpeg network-manager rsync

echo "==> MediaMTX ${MEDIAMTX_VERSION}"
if ! command -v mediamtx >/dev/null && [[ ! -x /usr/local/bin/mediamtx ]]; then
    tmp=$(mktemp -d)
    curl -fL -o "$tmp/mediamtx.tar.gz" \
        "https://github.com/bluenviron/mediamtx/releases/download/${MEDIAMTX_VERSION}/mediamtx_${MEDIAMTX_VERSION}_linux_${ARCH}.tar.gz"
    tar -xzf "$tmp/mediamtx.tar.gz" -C "$tmp"
    install -m 0755 "$tmp/mediamtx" /usr/local/bin/mediamtx
    rm -rf "$tmp"
else
    echo "    already installed, skipping"
fi

echo "==> recordings dir /opt/wasty/recordings"
mkdir -p /opt/wasty/recordings

echo "==> app -> ${APP_DIR} (editable install source)"
mkdir -p "$APP_DIR"
# Preserve per-robot overrides; never wipe local.yaml on reinstall/update.
rsync -a --delete \
    --exclude .git \
    --exclude .venv \
    --exclude .venv-dev \
    --exclude webui/node_modules \
    --exclude config/local.yaml \
    "$REPO_DIR/" "$APP_DIR/"

if [[ ! -f "$APP_DIR/webui/dist/index.html" ]]; then
    echo "!! $APP_DIR/webui/dist/index.html missing"
    echo "   The SPA should be committed on the 'dev' branch. Try: git pull"
    echo "   Or build it: (cd webui && npm install && npm run build), then re-run."
    exit 1
fi
echo "    SPA found at $APP_DIR/webui/dist"

echo "==> venv -> ${VENV_DIR} (system site-packages for picamera2)"
python3 -m venv --system-site-packages "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip >/dev/null
# Editable: Python imports from $APP_DIR/src, so update.sh only needs sync + restart.
"$VENV_DIR/bin/pip" install -e "${APP_DIR}[pi]"

echo "==> systemd unit"
cp "$APP_DIR/systemd/wasty.service" /etc/systemd/system/wasty.service
systemctl daemon-reload
systemctl enable wasty.service

echo
echo "Done. Edit ${APP_DIR}/config/local.yaml (hotspot SSID/password, servo trim),"
echo "then: sudo systemctl start wasty"
echo
echo "Later updates from your git checkout:"
echo "  git pull && sudo scripts/update.sh"
