#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${VERSION:-$(sed -n 's/^__version__ = "\([^"]*\)"$/\1/p' "$ROOT/desktop/src/linktolinux/__init__.py")}"
APK="${ANDROID_APK:-$ROOT/android/app/build/outputs/apk/release/app-release.apk}"

[[ -f "$APK" ]] || { echo "Release APK not found: $APK" >&2; exit 1; }
command -v rpmbuild >/dev/null || { echo "rpmbuild is required to build the Fedora RPM." >&2; exit 1; }

VERSION="$VERSION" "$ROOT/packaging/build_deb.sh"
VERSION="$VERSION" "$ROOT/packaging/build_rpm.sh"
VERSION="$VERSION" "$ROOT/packaging/build_portable_tarball.sh"

tar -czf "$ROOT/dist/LinkToLinux-${VERSION}-source.tar.gz" \
    --exclude='./dist' \
    --exclude='./.git' \
    --exclude='*/.git' \
    --exclude='./.venv' \
    --exclude='./.venv-*' \
    --exclude='./.claude' \
    --exclude='./.pytest_cache' \
    --exclude='*/.venv' \
    --exclude='*/.venv-*' \
    --exclude='*/__pycache__' \
    --exclude='*/.pytest_cache' \
    --exclude='*.egg-info' \
    --exclude='./android/.gradle' \
    --exclude='./android/.kotlin' \
    --exclude='*/.kotlin' \
    --exclude='./android/app/build' \
    --exclude='./android/local.properties' \
    --exclude='./android/signing.properties' \
    --exclude='./android/*.jks' \
    -C "$ROOT" .

RELEASE="$ROOT/dist/release-assets-${VERSION}"
mkdir -p "$RELEASE/assets"
rm -f "$RELEASE/LinkToLinux-Android.apk" \
    "$RELEASE/LinkToLinux-0.1.0-Android.apk" \
    "$RELEASE/LinkToLinux-0.1.1-Android.apk" \
    "$RELEASE/LinkToLinux-0.1.0-Linux.tar.gz" \
    "$RELEASE/linktolinux_0.1.0_all.deb" \
    "$RELEASE/linktolinux-0.1.0-1.noarch.rpm" \
    "$RELEASE/linktolinux_${VERSION}_all.deb" \
    "$RELEASE/linktolinux-${VERSION}-1.noarch.rpm" \
    "$RELEASE/LinkToLinux-${VERSION}-Linux.tar.gz" \
    "$RELEASE/LinkToLinux-${VERSION}-source.tar.gz" \
    "$RELEASE/README.md" \
    "$RELEASE/CHANGELOG.md"
install -m 0644 "$APK" "$ROOT/dist/linktolinux-android.apk"
install -m 0644 "$APK" "$RELEASE/LinkToLinux-Android.apk"
install -m 0644 "$ROOT/dist/linktolinux_${VERSION}_all.deb" "$RELEASE/"
install -m 0644 "$ROOT/dist/linktolinux-${VERSION}-1.noarch.rpm" "$RELEASE/"
install -m 0644 "$ROOT/dist/LinkToLinux-${VERSION}-Linux.tar.gz" "$RELEASE/"
install -m 0644 "$ROOT/dist/LinkToLinux-${VERSION}-source.tar.gz" "$RELEASE/"
install -m 0644 "$ROOT/packaging/RELEASE_README.md" "$RELEASE/README.md"
install -m 0644 "$ROOT/packaging/RELEASE_NOTES.md" "$RELEASE/CHANGELOG.md"
install -m 0644 "$ROOT/desktop/data/linktolinux.svg" "$RELEASE/assets/linktolinux.svg"
rm -rf "$RELEASE/screenshots"
mkdir -p "$RELEASE/screenshots"
install -m 0644 "$ROOT/packaging/screenshots/desktop-home.png" "$RELEASE/screenshots/desktop-home.png"
install -m 0644 "$ROOT/packaging/screenshots/android-home.png" "$RELEASE/screenshots/android-home.png"
(
    cd "$ROOT/dist"
    sha256sum \
        linktolinux-android.apk \
        "linktolinux_${VERSION}_all.deb" \
        "linktolinux-${VERSION}-1.noarch.rpm" \
        "LinkToLinux-${VERSION}-Linux.tar.gz" \
        "LinkToLinux-${VERSION}-source.tar.gz"
) > "$ROOT/dist/SHA256SUMS-${VERSION}.txt"
(
    cd "$RELEASE"
    sha256sum \
        LinkToLinux-Android.apk \
        "linktolinux_${VERSION}_all.deb" \
        "linktolinux-${VERSION}-1.noarch.rpm" \
        "LinkToLinux-${VERSION}-Linux.tar.gz" \
        "LinkToLinux-${VERSION}-source.tar.gz"
) > "$RELEASE/SHA256SUMS-${VERSION}.txt"
echo "Binary-only release bundle prepared at $RELEASE"
