#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
user_home="${HOME:?HOME is not set}"
environment="$project_root/desktop/.venv-launcher"
applications_dir="$user_home/.local/share/applications"
icons_dir="$user_home/.local/share/icons/hicolor/scalable/apps"

if ! /usr/bin/python3 -c 'import gi; gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1")' >/dev/null 2>&1; then
    echo "GTK4/libadwaita Python bindings are missing. Install python3-gi, gir1.2-gtk-4.0, and gir1.2-adw-1 first." >&2
    exit 1
fi

if [[ ! -x "$environment/bin/python" ]]; then
    python3 -m venv --system-site-packages "$environment"
fi

"$environment/bin/python" -m pip install --upgrade pip
"$environment/bin/python" -m pip install --editable "$project_root/desktop"

mkdir -p "$applications_dir" "$icons_dir"
install -m 0644 "$project_root/desktop/data/linktolinux.svg" "$icons_dir/linktolinux.svg"

desktop_file="$applications_dir/io.github.linktolinux.LinkToLinux.desktop"
cat > "$desktop_file" <<EOF
[Desktop Entry]
Version=1.0
Name=Link to Linux
Comment=Connect your Android phone to your Linux desktop
Exec="$environment/bin/linktolinux"
Icon=$icons_dir/linktolinux.svg
Type=Application
Terminal=false
StartupNotify=true
Categories=Network;
EOF
chmod 0644 "$desktop_file"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$applications_dir" >/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache --force --ignore-theme-index "$user_home/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

echo "Installed Link to Linux in the applications menu. Search for ‘Link to Linux’ and open it."
