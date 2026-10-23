# Security and permissions

## Pairing and transport

- Pairing uses TLS on the local network, with Android checking the desktop's SHA-256 certificate fingerprint before sending the one-time code.
- Pairing codes contain six digits, expire after three minutes, and are limited to eight failed attempts per session.
- A trusted-device token is created at pairing and used for later reconnection. Removing a trusted device revokes that saved token on the desktop.
- The desktop listens on TCP port `44888`; users may need to allow that port on their local firewall.

## Local data

- The desktop TLS certificate and private key are stored under `~/.config/linktolinux/tls/`. Trusted-device records and feature settings are kept under the XDG configuration directory.
- Android stores its pairing preferences in app-private storage. Release signing files are local build credentials and must not be committed.
- The current connection is direct over the local network; the app does not use a cloud relay.

## Feature permissions

- Photo browsing uses Android media permissions.
- Notification forwarding and media-session access require Android Notification access. Forwarding notification content is separately opt-in in the app.
- Clipboard sharing is opt-in on both devices.
- Remote input is disabled by default and must be enabled on the desktop. The server validates each action and restricts keys and text length before calling the local input tool. On Wayland, ydotool requires a daemon with access to `/dev/uinput`; granting that access can permit system-wide input injection, so use the distribution's documented setup and never run Link to Linux as root.
- File transfers are limited to 256 MB and verify the received content with SHA-256 before completing.

Review Android permissions before enabling the related feature. Only pair devices on networks you trust.
