#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${VERSION:-1.1.0}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
APP="$WORK/LinkToLinux-${VERSION}-Linux"
mkdir -p "$APP/usr/lib/linktolinux" "$APP/usr/bin" \
    "$APP/usr/share/applications" "$APP/usr/share/icons/hicolor/scalable/apps"
cp -a "$ROOT/desktop/src/linktolinux" "$APP/usr/lib/linktolinux/"
find "$APP" -type d -name __pycache__ -prune -exec rm -rf {} +
install -m 0644 "$ROOT/desktop/data/linktolinux.svg" \
    "$APP/usr/share/icons/hicolor/scalable/apps/io.github.linktolinux.LinkToLinux.svg"
cat > "$APP/usr/bin/linktolinux" <<'EOF'
#!/bin/sh
APPROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
export PYTHONPATH="$APPROOT/lib/linktolinux${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m linktolinux.main "$@"
EOF
chmod 0755 "$APP/usr/bin/linktolinux"
cat > "$APP/usr/share/applications/io.github.linktolinux.LinkToLinux.desktop" <<'EOF'
[Desktop Entry]
Version=1.0
Name=Link to Linux
Comment=Connect your Android phone to your Linux desktop
Exec=linktolinux
TryExec=linktolinux
Icon=io.github.linktolinux.LinkToLinux
Type=Application
Terminal=false
StartupNotify=true
Categories=Network;Utility;
EOF
mkdir -p "$ROOT/dist"
tar -C "$WORK" -czf "$ROOT/dist/LinkToLinux-${VERSION}-Linux.tar.gz" "$(basename "$APP")"
echo "Built $ROOT/dist/LinkToLinux-${VERSION}-Linux.tar.gz"
