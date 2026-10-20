# Link to Linux
**Join my discord.** https://discord.gg/ZD7ucwj2k
**Your Android phone, connected to your Linux desktop.**

Link to Linux is a phone companion for Linux. It is inspired by the convenience of Microsoft Link to Windows and Phone Link, and built as an independent project for Linux desktop users.

Pair devices over your local network, then use the desktop and Android apps to transfer files, browse phone photos, check phone status, forward notifications, and share clipboard text. Some features require Android permissions and an active connection.

## Downloads

| File | For |
| --- | --- |
| [Download Android APK](./LinkToLinux-Android.apk) | Android phones |
| [Download Debian/Ubuntu package](./linktolinux_0.1.0_all.deb) | Debian and Ubuntu |
| [Download Fedora RPM](./linktolinux-0.1.0-1.noarch.rpm) | Fedora and compatible RPM distributions |
| [Download portable Linux archive](./LinkToLinux-0.1.0-Linux.tar.gz) | Other Linux distributions with the listed runtime dependencies |

## Install

### Debian or Ubuntu

Open the `.deb` file in the system software installer. The package manager will install the desktop app and its dependencies. Launch **Link to Linux** from the applications menu.

### Fedora

Open the `.rpm` file in Software, or install it from a terminal:

```bash
sudo dnf install ./linktolinux-0.1.0-1.noarch.rpm
```

### Other Linux distributions

Extract the tarball and run `usr/bin/linktolinux`. Install these system dependencies with your distribution's package manager first:

- Python 3.11 or newer
- GTK 4 and libadwaita
- PyGObject and Segno for Python
- OpenSSL

### Android

Install `LinkToLinux-Android.apk`. Since it is distributed outside Google Play, Google Play Protect may warn about or block installation. Depending on the Android version and device, installation may require temporarily turning off **Scan apps with Play Protect** in Play Store → profile → Play Protect → Settings. Only do this if you trust that you downloaded the APK from this project's official release page, and turn Play Protect back on immediately after installation. Keep Android's **Allow restricted settings** permission steps below separate: they are needed for notification access, not APK installation. [Google Play Protect information](https://support.google.com/googleplay/answer/2812853).

If Android blocks notification access for this sideloaded app, open **Settings → Apps → Link to Linux → ⋮ → Allow restricted settings**, then enable it under **Special app access → Notification access**.

## Pair your devices

Connect the phone and desktop to the same local network. Open **Devices & pairing** on the desktop, start pairing, and scan its QR code with Link to Linux on Android. Confirm the secure pairing in the phone app.

## About

Built by **Young Jay** at **YoungTechsperts**. Find more projects at [youngai.site](https://youngai.site) or visit [Young Jay on GitHub](https://github.com/Youngjay42-real).

Join the community on [Discord](https://discord.gg/sMC9cV9nfU) for project updates, questions, and discussion.

Link to Linux is not affiliated with or endorsed by Microsoft. The project is distributed under the MIT License.

## MIT License

Copyright (c) 2026 Young Jay

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
