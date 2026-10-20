#!/bin/sh
# Install Naga Synapse for the current user.
#   - the app (pipx, reusing the system PySide6)
#   - a desktop menu entry and icon
#   - optionally (with --udev, needs sudo) the udev rule for device access
set -eu
cd "$(dirname "$0")/.."

if command -v pipx >/dev/null 2>&1; then
    pipx install --force --system-site-packages .
else
    echo "pipx not found; installing with pip --user" >&2
    python3 -m pip install --user .
fi

data="${XDG_DATA_HOME:-$HOME/.local/share}"
install -Dm644 packaging/nagasynapse.desktop "$data/applications/nagasynapse.desktop"
install -Dm644 nagasynapse/assets/nagasynapse.svg "$data/icons/hicolor/scalable/apps/nagasynapse.svg"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$data/applications" || true

if [ "${1:-}" = "--udev" ]; then
    sudo install -Dm644 packaging/70-nagasynapse.rules /etc/udev/rules.d/70-nagasynapse.rules
    sudo udevadm control --reload
    sudo udevadm trigger --subsystem-match=hidraw
    echo "udev rule installed"
fi
echo "Installed. Start \"Naga Synapse\" from your menu, or run: nagasynapse"
