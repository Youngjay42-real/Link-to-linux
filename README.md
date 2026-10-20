<p align="center">
  <img src="./assets/linktolinux.svg" alt="Link to Linux desktop app icon" width="112">
</p>

<h1 align="center">Link to Linux</h1>

<p align="center"><strong>Your Android phone, connected to your Linux desktop.</strong></p>

Link to Linux is an independent phone companion for Linux, inspired by the convenience of Microsoft Link to Windows. Pair over your local network to share files, browse phone photos, view device status, forward notifications, and opt in to text clipboard sharing.

## Screenshots

### Desktop

![Link to Linux desktop home screen](./screenshots/desktop-home.png)

### Android

<p align="center">
  <img src="./screenshots/android-home.png" alt="Link to Linux Android home screen" width="320">
</p>

## Releases

### 1.0.0 · Current release

Improved reconnect and photo browsing, saved desktop feature preferences, and clearer connection and photo-loading states. See the [1.0.0 changelog](./CHANGELOG.md).

| Download | Package |
| --- | --- |
| [Android APK](./LinkToLinux-Android.apk) | Android |
| [Debian/Ubuntu](./linktolinux_1.0.0_all.deb) | `.deb` |
| [Fedora](./linktolinux-1.0.0-1.noarch.rpm) | `.rpm` |
| [Portable Linux](./LinkToLinux-1.0.0-Linux.tar.gz) | `.tar.gz` |

Some features require Android permissions and an active paired connection.

## Install

On Debian or Ubuntu, open the `.deb` in the system software installer. On Fedora, open the `.rpm` or run:

```bash
sudo dnf install ./linktolinux-1.0.0-1.noarch.rpm
```

For other Linux distributions, extract the portable archive and run `usr/bin/linktolinux`. GTK 4, libadwaita, Python 3.11+, PyGObject, Segno, and OpenSSL are required.

Install `LinkToLinux-Android.apk` on Android. Because the APK is distributed outside Google Play, Play Protect may warn about or block installation. Only install it if you trust that it came from this project's release page; if Android requires turning off app scanning, turn Play Protect back on immediately afterward. Notification access may separately require **Allow restricted settings** in the app info screen. See [Google Play Protect help](https://support.google.com/googleplay/answer/2812853).

## Pairing

Connect both devices to the same local network. Start pairing from **Devices & pairing** on the desktop, then scan the desktop QR code with Link to Linux on Android.

## About

Built by **Young Jay** at **YoungTechsperts**. [GitHub profile](https://github.com/Youngjay42-real) · [More projects](https://youngai.site) · [Join the Discord community](https://discord.gg/sMC9cV9nfU)

Link to Linux is an independent project and is not affiliated with Microsoft. Licensed under the MIT License.
