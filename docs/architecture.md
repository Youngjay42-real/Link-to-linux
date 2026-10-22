# Architecture

Link to Linux is a desktop application and an Android companion connected by a TLS-protected TCP session on the local network.

## Desktop

- `desktop/src/linktolinux/ui/` builds the GTK4/libadwaita interface.
- `application.py` owns desktop settings and feature services.
- `transports/pairing_server.py` handles pairing, trusted-device reconnection, status updates, file transfer, photo requests, notification delivery, clipboard messages, and media controls.
- Desktop settings and trusted-device records are stored under the user's XDG configuration directory.

## Android

- `MainActivity.kt` builds the Jetpack Compose interface and performs QR or manual pairing.
- `LinkSessionService.kt` keeps the paired session alive in a foreground service and exchanges status and feature requests.
- `PhoneNotificationListener.kt` forwards opted-in notifications and reads active media sessions when Android notification access is granted.
- Android preferences store the selected desktop and app settings.

## Session flow

The Android app opens a TLS connection to the desktop on TCP port `44888`. The phone checks the desktop certificate fingerprint before sending the one-time pairing code. After pairing, the connection remains open for status updates and feature requests. Reconnection uses the trusted-device token saved on each side.

Messages are newline-delimited JSON objects. File data is transferred in bounded chunks with SHA-256 verification. Photo requests and notification, clipboard, status, and media updates use the same paired session.

The separate `protocol/` package contains message-envelope validation experiments; it is not the envelope format used by the current live session.
