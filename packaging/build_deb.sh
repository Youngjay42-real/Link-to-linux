#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/dist"
VERSION="${VERSION:-1.1.1}"
PACKAGE="linktolinux"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

install -d "$STAGE/DEBIAN" \
    "$STAGE/usr/bin" \
    "$STAGE/usr/lib/linktolinux" \
    "$STAGE/usr/share/applications" \
    "$STAGE/usr/share/icons/hicolor/scalable/apps"
chmod 0755 "$STAGE"

cp -a "$ROOT/desktop/src/linktolinux" "$STAGE/usr/lib/linktolinux/"
find "$STAGE/usr/lib/linktolinux" -type d -name __pycache__ -prune -exec rm -rf {} +
install -m 0644 "$ROOT/desktop/data/linktolinux.svg" \
    "$STAGE/usr/share/icons/hicolor/scalable/apps/io.github.linktolinux.LinkToLinux.svg"

cat > "$STAGE/usr/bin/linktolinux" <<'EOF'
#!/bin/sh
export PYTHONPATH="/usr/lib/linktolinux${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m linktolinux.main "$@"
EOF
chmod 0755 "$STAGE/usr/bin/linktolinux"
find "$STAGE" -type d -exec chmod 0755 {} +

cat > "$STAGE/usr/share/applications/io.github.linktolinux.LinkToLinux.desktop" <<'EOF'
[Desktop Entry]
Version=1.0
Name=Link to Linux
Comment=Connect your Android phone to your Linux desktop
Exec=/usr/bin/linktolinux
TryExec=/usr/bin/linktolinux
Icon=io.github.linktolinux.LinkToLinux
Type=Application
Terminal=false
StartupNotify=true
Categories=Network;Utility;
EOF

cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PACKAGE
Version: $VERSION
Section: net
Priority: optional
Architecture: all
Maintainer: YoungTechsperts
Depends: python3 (>= 3.11), python3-gi, python3-segno, gir1.2-gtk-4.0, gir1.2-adw-1, openssl
Description: Link to Linux desktop companion
 Securely connect an Android phone and Linux desktop over a local network.
 Includes phone pairing, file transfer, photo browsing, status, notifications,
 and clipboard sharing features.
EOF

mkdir -p "$OUT"
dpkg-deb --build --root-owner-group "$STAGE" "$OUT/${PACKAGE}_${VERSION}_all.deb"
echo "Built $OUT/${PACKAGE}_${VERSION}_all.deb"
