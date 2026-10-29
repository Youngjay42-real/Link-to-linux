# Installation and development setup

For release downloads and the shortest setup instructions, see the project [README](../README.md).

## Linux desktop development

On Ubuntu or Debian, install the GTK4 and libadwaita bindings, then install the project in a virtual environment with system packages enabled:

```bash
sudo apt update
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-packaging python3-venv python3-dev
python3 -m venv --system-site-packages desktop/.venv
source desktop/.venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ./desktop
linktolinux
```

To add a launcher to the Applications menu, run `packaging/install_desktop.sh` from the project directory.

Remote input is an optional desktop integration. Install `xdotool` for X11 or `ydotool` for Wayland. On Wayland, start the packaged per-user daemon:

```bash
systemctl --user start ydotool.service
```

The desktop app checks that the daemon socket is reachable before advertising remote input as available. If the service cannot access `/dev/uinput`, follow your distribution's setup guidance; do not run Link to Linux as root. Remote input stays disabled until enabled in the desktop app's Remote input page.

## Android development

Install Android Studio with Android SDK Platform 35 and open the `android/` directory. Build a debug APK with `./gradlew assembleDebug` from that directory. Release builds require a locally generated signing key and `android/signing.properties`; never commit either file.

## Linux packages

Run `packaging/build_deb.sh`, `packaging/build_rpm.sh`, or `packaging/build_portable_tarball.sh` to build the matching package. `packaging/build_release_bundle.sh` assembles all release artifacts and expects a signed Android release APK and `rpmbuild` to be available. The portable archive needs GTK 4, libadwaita, Python 3.11+, PyGObject, Segno, Python Packaging, and OpenSSL from the Linux distribution.
