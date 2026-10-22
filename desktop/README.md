# Link to Linux Desktop

This package contains the Ubuntu desktop client for the Link to Linux project.

## Launch from the applications menu

For a friend-friendly install, build `dist/linktolinux_1.0.0_all.deb` with
`packaging/build_deb.sh`, send them the `.deb`, and have them double-click it in
Ubuntu Software to install. Dependencies and the applications-menu launcher
are included in the package metadata.

For a local development install, run `packaging/install_desktop.sh` from the
project folder. It creates a GTK-enabled environment and adds a launcher to
your Applications menu. Run it again after moving the project folder.

## Run the desktop UI manually

Install the Ubuntu system packages `python3-gi`, `gir1.2-gtk-4.0`, and
`gir1.2-adw-1`, then create a virtual environment with
`python3 -m venv --system-site-packages .venv`. This exposes Ubuntu's GTK
bindings inside the venv. Install this package with `python -m pip install -e .`
and run `linktolinux`. The GTK4/libadwaita window includes the dashboard, device
pairing, files, photos, notifications, clipboard, settings, and about pages.

The Devices & pairing page starts a TLS listener on port 44888. The page shows
the desktop's LAN address, a three-minute one-time code, and the SHA-256
fingerprint of its persistent local certificate. Scan the page's QR code in the
Android app to fill those details automatically. The QR appears only while the
pairing listener is active; the APK still pins the certificate before it sends
the code. Pairing adds the
phone's ID to this desktop session's trusted-device list. The listener stops
after a successful pairing, when its code expires, or when pairing is stopped.

The desktop accepts photo browsing and notification delivery only after the
matching feature is enabled and Android grants its system permission. OpenSSL
is required to create the desktop's local TLS certificate on first use.

## Features

- Pairing and identity management
- Secure transport status tracking
- Notification and clipboard synchronization toggles
- File transfer safety and validation
