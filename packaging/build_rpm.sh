#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${VERSION:-1.1.0}"
ARCH="${RPM_ARCH:-noarch}"
WORK="$(mktemp -d "$ROOT/dist/.rpmbuild.XXXXXX")"
RPM_WORK="/tmp/linktolinux-rpm-$$"
ln -s "$WORK" "$RPM_WORK"
trap 'rm -f "$RPM_WORK"; rm -rf "$WORK"' EXIT
TOP="$RPM_WORK/rpmbuild"
mkdir -p "$TOP/BUILD" "$TOP/BUILDROOT" "$TOP/RPMS" "$TOP/SOURCES" "$TOP/SPECS" "$TOP/SRPMS"
mkdir -p "$TOP/tmp"

STAGE="$WORK/linktolinux"
mkdir -p "$STAGE"
cp -a "$ROOT/desktop/src/linktolinux" "$STAGE/"
mkdir -p "$STAGE/share"
cp "$ROOT/desktop/data/linktolinux.svg" "$STAGE/share/linktolinux.svg"
find "$STAGE" -type d -name __pycache__ -prune -exec rm -rf {} +
tar -C "$WORK" -czf "$TOP/SOURCES/linktolinux-${VERSION}.tar.gz" linktolinux

cat > "$TOP/SPECS/linktolinux.spec" <<EOF
Name:           linktolinux
Version:        $VERSION
Release:        1%{?dist}
Summary:        Android phone companion for Linux desktops
License:        MIT
BuildArch:      $ARCH
Source0:        %{name}-%{version}.tar.gz
Requires:       python3 >= 3.11
Requires:       python3-gobject
Requires:       python3-segno
Requires:       gtk4
Requires:       libadwaita
Requires:       openssl

%description
Pair an Android phone with a Linux desktop and exchange files, browse photos,
view phone status, synchronize notifications, and share clipboard text.

%prep
%setup -q -n linktolinux

%build

%install
mkdir -p %{buildroot}%{_libdir}/linktolinux
mkdir -p %{buildroot}%{_bindir}
mkdir -p %{buildroot}%{_datadir}/applications
mkdir -p %{buildroot}%{_datadir}/icons/hicolor/scalable/apps
cp -a linktolinux %{buildroot}%{_libdir}/linktolinux/
cat > %{buildroot}%{_bindir}/linktolinux <<'LAUNCHER'
#!/bin/sh
export PYTHONPATH="%{_libdir}/linktolinux\${PYTHONPATH:+:\$PYTHONPATH}"
exec /usr/bin/python3 -m linktolinux.main "\$@"
LAUNCHER
chmod 0755 %{buildroot}%{_bindir}/linktolinux
cat > %{buildroot}%{_datadir}/applications/io.github.linktolinux.LinkToLinux.desktop <<'DESKTOP'
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
DESKTOP
install -m 0644 share/linktolinux.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/io.github.linktolinux.LinkToLinux.svg

%files
%{_libdir}/linktolinux/linktolinux
%{_bindir}/linktolinux
%{_datadir}/applications/io.github.linktolinux.LinkToLinux.desktop
%{_datadir}/icons/hicolor/scalable/apps/io.github.linktolinux.LinkToLinux.svg

%changelog
* Mon Oct 19 2026 YoungTechsperts <youngjay@youngtechsperts.com> - $VERSION-1
- Initial binary package
EOF

rpmbuild --define "_topdir $TOP" --define "_tmppath $TOP/tmp" -bb "$TOP/SPECS/linktolinux.spec"
mkdir -p "$ROOT/dist"
cp "$TOP/RPMS/$ARCH/linktolinux-${VERSION}-1"*.rpm "$ROOT/dist/linktolinux-${VERSION}-1.${ARCH}.rpm"
echo "Built $ROOT/dist/linktolinux-${VERSION}-1.${ARCH}.rpm"
