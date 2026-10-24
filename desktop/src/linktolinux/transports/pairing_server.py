from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import platform
import base64
import binascii
import os
import re
import secrets
import socket
import socketserver
import ssl
import subprocess
import tempfile
import threading
import time
import uuid
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


PAIRING_PORT = 44888
PAIRING_TTL_SECONDS = 180
MAX_REQUEST_BYTES = 96 * 1024
MAX_TRANSFER_BYTES = 256 * 1024 * 1024
DESKTOP_CHUNK_BYTES = 48 * 1024


def _desktop_status(desktop_name: str) -> dict:
    usage = shutil.disk_usage(Path.home())
    battery_percent = None
    charging = False
    batteries = Path("/sys/class/power_supply")
    if batteries.exists():
        for item in batteries.glob("BAT*"):
            try:
                battery_percent = int((item / "capacity").read_text().strip())
                charging = (item / "status").read_text().strip().lower() in {"charging", "full"}
                break
            except (OSError, ValueError):
                continue
    return {
        "device_name": desktop_name,
        "model": f"{platform.system()} {platform.release()}",
        "battery_percent": battery_percent,
        "charging": charging,
        "storage_total_bytes": usage.total,
        "storage_free_bytes": usage.free,
        "last_seen": time.time(),
    }


@dataclass(frozen=True)
class PairingAdvertisement:
    host: str
    port: int
    code: str
    fingerprint: str
    expires_at: float


def _config_directory() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "linktolinux" / "tls"


def _ensure_certificate() -> tuple[Path, Path, str]:
    directory = _config_directory()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    certificate = directory / "pairing-cert.pem"
    private_key = directory / "pairing-key.pem"
    if not certificate.exists() or not private_key.exists():
        result = subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256",
                "-nodes", "-days", "3650", "-keyout", str(private_key),
                "-out", str(certificate), "-subj", "/CN=Link to Linux Desktop",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Could not create the local pairing certificate: {result.stderr.strip()}")
        private_key.chmod(0o600)
        certificate.chmod(0o644)
    private_key.chmod(0o600)
    der = ssl.PEM_cert_to_DER_cert(certificate.read_text(encoding="ascii"))
    fingerprint = hashlib.sha256(der).hexdigest()
    return certificate, private_key, fingerprint


def _lan_address() -> str:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))
        address = probe.getsockname()[0]
        if not address.startswith("127."):
            return address
    except OSError:
        pass
    finally:
        probe.close()
    return "127.0.0.1"


class _PairingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], handler: type[socketserver.BaseRequestHandler], tls: ssl.SSLContext):
        self.tls = tls
        super().__init__(address, handler)

    def get_request(self) -> tuple[ssl.SSLSocket, tuple[str, int]]:
        connection, address = super().get_request()
        connection.settimeout(60)
        try:
            secure = self.tls.wrap_socket(connection, server_side=True)
        except Exception:
            connection.close()
            raise
        return secure, address


class DesktopPairingServer:
    """Short-lived TLS pairing listener for the Android app."""

    def __init__(
        self,
        on_paired: Callable[[str, str], None],
        desktop_name: str = "Linux Desktop",
        on_status: Callable[[str, dict], None] | None = None,
        on_file: Callable[[dict], None] | None = None,
        on_clipboard: Callable[[str, str], bool | None] | None = None,
        clipboard_enabled: Callable[[], bool] | None = None,
        remote_input_available: Callable[[], bool] | None = None,
        remote_input_enabled: Callable[[], bool] | None = None,
        on_remote_input: Callable[..., None] | None = None,
        download_directory: Callable[[], str] | None = None,
    ) -> None:
        self.on_paired = on_paired
        self.desktop_name = desktop_name
        self.on_status = on_status
        self.on_file = on_file
        self.on_clipboard = on_clipboard
        self.clipboard_enabled = clipboard_enabled or (lambda: False)
        self.remote_input_available = remote_input_available or (lambda: False)
        self.remote_input_enabled = remote_input_enabled or (lambda: False)
        self.on_remote_input = on_remote_input
        self.download_directory = download_directory or (lambda: str(Path.home() / "Downloads"))
        self.pairing_listeners: list[Callable[[str, str], None]] = []
        self.status_listeners: list[Callable[[str, dict], None]] = []
        self.file_listeners: list[Callable[[dict], None]] = []
        self.clipboard_listeners: list[Callable[[str, str], None]] = []
        self._clipboard_lock = threading.Lock()
        self._phone_clipboard_enabled = False
        self._pending_clipboard_text: str | None = None
        self._lock = threading.Lock()
        self._server: _PairingTCPServer | None = None
        self._thread: threading.Thread | None = None
        self._active_socket: ssl.SSLSocket | None = None
        self._code = ""
        self._expires_at = 0.0
        self._failed_attempts = 0
        self._fingerprint = ""
        self._expiry_timer: threading.Timer | None = None
        self._paired_once = False
        self.session_connected = False
        self.connected_device_id = ""
        self.connected_device_name = ""
        self.phone_ring_requested = False
        self.phone_ring_active = False
        self.pending_media_command: dict[str, str] | None = None
        self.latest_status: dict = {}
        self.received_files: list[dict] = []
        self.pending_desktop_files: dict[str, dict] = {}
        self._desktop_files_lock = threading.Lock()
        self.file_sent_listeners: list[Callable[[dict], None]] = []
        self.notification_listeners: list[Callable[[dict], None]] = []
        self.phone_photos_listeners: list[Callable[[list[dict]], None]] = []
        self.photo_preview_listeners: list[Callable[[dict], None]] = []
        self.latest_phone_photos: list[dict] = []
        self.phone_photos_message = ""
        self._photo_lock = threading.Lock()
        self._photos_requested = False
        self.auto_load_phone_photos = False
        self._pending_phone_photo_id = ""
        self._pending_phone_photo_mode = "save"
        self.trusted_devices_path = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "linktolinux" / "trusted-devices.json"
        self.trusted_devices: dict[str, dict[str, str]] = {}
        self._keep_listener = False
        self._load_trusted_devices()

    def _load_trusted_devices(self) -> None:
        try:
            data = json.loads(self.trusted_devices_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self.trusted_devices = {device_id: value for device_id, value in data.items()
                    if isinstance(device_id, str) and isinstance(value, dict)
                    and isinstance(value.get("token"), str) and isinstance(value.get("name"), str)}
        except (OSError, json.JSONDecodeError):
            self.trusted_devices = {}

    def _save_trusted_devices(self) -> None:
        self.trusted_devices_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.trusted_devices_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.trusted_devices, indent=2), encoding="utf-8")
        temporary.chmod(0o600)
        os.replace(temporary, self.trusted_devices_path)

    def revoke_device(self, device_id: str) -> None:
        self.trusted_devices.pop(device_id, None)
        self._save_trusted_devices()

    def remember_device(self, device_id: str, name: str, token: str) -> None:
        self.trusted_devices[device_id] = {"name": name, "token": token}
        self._save_trusted_devices()

    @property
    def active(self) -> bool:
        return self._server is not None and time.time() < self._expires_at

    @property
    def advertisement(self) -> PairingAdvertisement | None:
        if not self.active:
            return None
        return PairingAdvertisement(
            host=_lan_address(), port=PAIRING_PORT, code=self._code,
            fingerprint=self._fingerprint, expires_at=self._expires_at,
        )

    def start(self, trusted_only: bool = False) -> PairingAdvertisement | None:
        if self._server is not None:
            self.stop()
        certificate, private_key, self._fingerprint = _ensure_certificate()
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.minimum_version = ssl.TLSVersion.TLSv1_2
        tls.load_cert_chain(str(certificate), str(private_key))
        owner = self

        class PairingHandler(socketserver.StreamRequestHandler):
            def handle(self) -> None:
                transfer: dict = {}
                try:
                    raw = self.rfile.readline(MAX_REQUEST_BYTES + 1)
                    if not raw or len(raw) > MAX_REQUEST_BYTES or not raw.endswith(b"\n"):
                        self._reply({"kind": "pairing.reject", "message": "Invalid request."})
                        return
                    request = json.loads(raw.decode("utf-8"))
                    if (
                        not isinstance(request, dict)
                        or request.get("kind") != "pairing.request"
                        or request.get("protocol_version") != "1.0.0"
                    ):
                        self._reply({"kind": "pairing.reject", "message": "Unsupported pairing request."})
                        return
                    device_id = request.get("device_id")
                    device_name = request.get("device_name")
                    candidate = request.get("pairing_code")
                    reconnect_token = request.get("reconnect_token")
                    if (
                        not isinstance(device_id, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", device_id)
                        or not isinstance(device_name, str) or not device_name.strip() or len(device_name) > 80
                        or (not isinstance(candidate, str) or (candidate and (len(candidate) != 6 or not candidate.isdigit())))
                    ):
                        self._reply({"kind": "pairing.reject", "message": "Invalid device details or code."})
                        return
                    with owner._lock:
                        trusted = owner.trusted_devices.get(device_id)
                        reconnecting = (
                            isinstance(reconnect_token, str) and trusted is not None
                            and hmac.compare_digest(reconnect_token, trusted["token"])
                        )
                        if owner.session_connected:
                            reason = "This pairing session already has a connected phone."
                            accepted = False
                        elif reconnecting:
                            reason = ""
                            accepted = True
                            owner._paired_once = True
                            owner.session_connected = True
                            owner.connected_device_id = device_id
                            owner.connected_device_name = device_name.strip()
                            owner._active_socket = self.request
                            reconnect_token = trusted["token"]
                        elif owner._paired_once:
                            reason = "This pairing session already has a connected phone."
                            accepted = False
                        elif not candidate or not owner._code:
                            reason = "Pair this device with a new QR code first."
                            accepted = False
                        elif time.time() > owner._expires_at or owner._server is None:
                            reason = "This pairing code has expired. Create a new code on the desktop."
                            accepted = False
                        elif owner._failed_attempts >= 8:
                            reason = "Too many attempts. Create a new pairing code on the desktop."
                            accepted = False
                        elif not hmac.compare_digest(candidate, owner._code):
                            owner._failed_attempts += 1
                            reason = "The pairing code is incorrect."
                            accepted = False
                        else:
                            owner._expires_at = time.time() - 1
                            owner._paired_once = True
                            owner.session_connected = True
                            owner.connected_device_id = device_id
                            owner.connected_device_name = device_name.strip()
                            owner._active_socket = self.request
                            if reconnecting:
                                reconnect_token = trusted["token"]
                            else:
                                reconnect_token = secrets.token_urlsafe(32)
                                owner.remember_device(device_id, device_name.strip(), reconnect_token)
                            reason = ""
                            accepted = True
                    if not accepted:
                        self._reply({"kind": "pairing.reject", "message": reason})
                        return
                    timer, owner._expiry_timer = owner._expiry_timer, None
                    if timer is not None:
                        timer.cancel()
                    owner.on_paired(device_id, device_name.strip())
                    if owner.auto_load_phone_photos:
                        owner.request_phone_photos()
                    for listener in tuple(owner.pairing_listeners):
                        try:
                            listener(device_id, device_name.strip())
                        except Exception:
                            pass
                    initial_status = request.get("device_status")
                    owner._phone_clipboard_enabled = request.get("clipboard_enabled") is True
                    if isinstance(initial_status, dict):
                        owner._publish_status(device_id, device_name.strip(), initial_status)
                    desktop_status = _desktop_status(owner.desktop_name)
                    desktop_status["remote_input_available"] = owner.remote_input_available()
                    desktop_status["remote_input_enabled"] = owner.remote_input_enabled()
                    self._reply({
                        "kind": "pairing.accept",
                        "protocol_version": "1.0.0",
                        "desktop_name": owner.desktop_name,
                        "desktop_id": owner._fingerprint[:24],
                        "desktop_status": desktop_status,
                        "reconnect_token": reconnect_token,
                    })
                    while True:
                        raw = self.rfile.readline(MAX_REQUEST_BYTES + 1)
                        if not raw:
                            break
                        if len(raw) > MAX_REQUEST_BYTES or not raw.endswith(b"\n"):
                            self._reply({"kind": "error", "message": "Message is too large or incomplete."})
                            break
                        try:
                            message = json.loads(raw.decode("utf-8"))
                            if not isinstance(message, dict):
                                raise ValueError("Message must be an object.")
                            response = owner._process_session_message(
                                device_id, device_name.strip(), message, transfer
                            )
                        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as error:
                            response = {"kind": "error", "message": str(error)[:240]}
                        self._reply(response)
                except (UnicodeDecodeError, json.JSONDecodeError, OSError, ssl.SSLError):
                    return
                finally:
                    owner._discard_transfer(transfer)
                    paired_device_id = locals().get("device_id")
                    if paired_device_id and owner.session_connected and owner.connected_device_id == paired_device_id:
                        threading.Thread(
                            target=owner._finish_live_session,
                            args=(device_id,),
                            name="linktolinux-session-stop",
                            daemon=True,
                        ).start()

            def _reply(self, response: dict[str, str]) -> None:
                self.wfile.write(json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n")
                self.wfile.flush()

        self._keep_listener = trusted_only
        self._code = "" if trusted_only else f"{secrets.randbelow(1_000_000):06d}"
        self._expires_at = 0.0 if trusted_only else time.time() + PAIRING_TTL_SECONDS
        self._failed_attempts = 0
        self._paired_once = False
        self._server = _PairingTCPServer(("0.0.0.0", PAIRING_PORT), PairingHandler, tls)
        self._thread = threading.Thread(target=self._server.serve_forever, name="linktolinux-pairing", daemon=True)
        self._thread.start()
        if not trusted_only:
            self._expiry_timer = threading.Timer(PAIRING_TTL_SECONDS, self._stop_expired)
            self._expiry_timer.daemon = True
            self._expiry_timer.start()
        if trusted_only:
            return None
        return self.advertisement  # type: ignore[return-value]

    def add_pairing_listener(self, listener: Callable[[str, str], None]) -> None:
        self.pairing_listeners.append(listener)

    def add_status_listener(self, listener: Callable[[str, dict], None]) -> None:
        self.status_listeners.append(listener)

    def add_file_listener(self, listener: Callable[[dict], None]) -> None:
        self.file_listeners.append(listener)

    def add_clipboard_listener(self, listener: Callable[[str, str], None]) -> None:
        self.clipboard_listeners.append(listener)

    def add_file_sent_listener(self, listener: Callable[[dict], None]) -> None:
        self.file_sent_listeners.append(listener)

    def add_notification_listener(self, listener: Callable[[dict], None]) -> None:
        self.notification_listeners.append(listener)

    def add_phone_photos_listener(self, listener: Callable[[list[dict]], None]) -> None:
        self.phone_photos_listeners.append(listener)

    def add_photo_preview_listener(self, listener: Callable[[dict], None]) -> None:
        self.photo_preview_listeners.append(listener)

    def request_phone_photos(self) -> None:
        with self._photo_lock:
            self._photos_requested = True
            self.phone_photos_message = "Waiting for the Android phone…"

    def request_phone_photo(self, media_id: str, mode: str = "save") -> None:
        if not re.fullmatch(r"[0-9]{1,20}", media_id):
            raise ValueError("Invalid phone photo identifier.")
        if mode not in {"save", "view"}:
            raise ValueError("Invalid phone photo action.")
        with self._photo_lock:
            if not any(photo.get("id") == media_id for photo in self.latest_phone_photos):
                raise ValueError("Refresh the phone photo list before requesting this image.")
            self._pending_phone_photo_id = media_id
            self._pending_phone_photo_mode = mode

    def queue_desktop_file(self, file_path: str) -> str:
        path = Path(file_path).expanduser().resolve(strict=True)
        if not path.is_file():
            raise ValueError("Choose a regular file.")
        size = path.stat().st_size
        if size > MAX_TRANSFER_BYTES:
            raise ValueError("Files must be 256 MB or smaller.")
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        transfer_id = str(uuid.uuid4())
        with self._desktop_files_lock:
            self.pending_desktop_files[transfer_id] = {
                "transfer_id": transfer_id,
                "filename": path.name[:240],
                "size_bytes": size,
                "mime_type": mime_type[:120],
                "category": "photo" if mime_type.startswith("image/") else "file",
                "path": str(path),
                "queued_at": time.time(),
            }
        return transfer_id

    def queue_clipboard_text(self, text: str | None) -> None:
        if text is not None and len(text.encode("utf-8")) > 64 * 1024:
            return
        with self._clipboard_lock:
            self._pending_clipboard_text = text

    def set_phone_ringing(self, enabled: bool) -> bool:
        with self._lock:
            if enabled and not self.session_connected:
                return False
            self.phone_ring_requested = enabled
            if not enabled:
                self.phone_ring_active = False
            return True

    def request_media_control(self, action: str) -> bool:
        if action not in {"play_pause", "next", "previous"}:
            return False
        with self._lock:
            if not self.session_connected:
                return False
            self.pending_media_command = {"id": uuid.uuid4().hex, "action": action}
            return True

    def _publish_status(self, device_id: str, device_name: str, status: dict) -> None:
        battery = status.get("battery_percent")
        charging = status.get("charging")
        total = status.get("storage_total_bytes")
        free = status.get("storage_free_bytes")
        model = status.get("model")
        if (
            type(battery) is not int or not 0 <= battery <= 100
            or not isinstance(charging, bool)
            or type(total) is not int or type(free) is not int
            or total < 0 or free < 0 or free > total
            or not isinstance(model, str) or not model.strip() or len(model) > 100
        ):
            return
        report = {
            "connected": self.session_connected,
            "device_id": device_id,
            "device_name": device_name,
            "model": model.strip(),
            "battery_percent": battery,
            "charging": charging,
            "storage_total_bytes": total,
            "storage_free_bytes": free,
            "clipboard_enabled": status.get("clipboard_enabled") is True,
            "media_access_granted": status.get("media", {}).get("access_granted") is True if isinstance(status.get("media"), dict) else False,
            "media_available": status.get("media", {}).get("available") is True if isinstance(status.get("media"), dict) else False,
            "media_title": str(status.get("media", {}).get("title", ""))[:256] if isinstance(status.get("media"), dict) else "",
            "media_artist": str(status.get("media", {}).get("artist", ""))[:256] if isinstance(status.get("media"), dict) else "",
            "media_playing": status.get("media", {}).get("playing") is True if isinstance(status.get("media"), dict) else False,
            "media_can_play_pause": status.get("media", {}).get("can_play_pause") is True if isinstance(status.get("media"), dict) else False,
            "media_can_previous": status.get("media", {}).get("can_previous") is True if isinstance(status.get("media"), dict) else False,
            "media_can_next": status.get("media", {}).get("can_next") is True if isinstance(status.get("media"), dict) else False,
            "last_seen": time.time(),
        }
        self.latest_status = report
        if self.on_status is not None:
            self.on_status(device_id, report)
        for listener in tuple(self.status_listeners):
            try:
                listener(device_id, report)
            except Exception:
                pass

    def _process_session_message(self, device_id: str, device_name: str, message: dict, transfer: dict) -> dict:
        kind = message.get("kind")
        if kind == "device.status":
            self._phone_clipboard_enabled = message.get("clipboard_enabled") is True
            with self._lock:
                self.phone_ring_active = self.phone_ring_requested and message.get("phone_ringing") is True
                ring_phone = self.phone_ring_requested
                phone_ring_active = self.phone_ring_active
                command_ack = message.get("media_command_ack")
                if self.pending_media_command and command_ack == self.pending_media_command["id"]:
                    self.pending_media_command = None
                media_command = dict(self.pending_media_command) if self.pending_media_command else None
            self._publish_status(device_id, device_name, message)
            response = {"kind": "status.accept"}
            response["clipboard_enabled"] = self.clipboard_enabled()
            desktop_status = _desktop_status(self.desktop_name)
            desktop_status["remote_input_available"] = self.remote_input_available()
            desktop_status["remote_input_enabled"] = self.remote_input_enabled()
            response["desktop_status"] = desktop_status
            response["ring_phone"] = ring_phone
            response["phone_ring_active"] = phone_ring_active
            response["media_command"] = media_command
            with self._photo_lock:
                response["photos_requested"] = self._photos_requested
                if self._pending_phone_photo_id:
                    response["photo_download_id"] = self._pending_phone_photo_id
                    response["photo_download_mode"] = self._pending_phone_photo_mode
            with self._desktop_files_lock:
                if self.pending_desktop_files:
                    offer = next(iter(self.pending_desktop_files.values()))
                    response["file_offer"] = {
                        key: offer[key] for key in ("transfer_id", "filename", "size_bytes", "mime_type", "category")
                    }
            with self._clipboard_lock:
                if self._phone_clipboard_enabled and response["clipboard_enabled"] and self._pending_clipboard_text is not None:
                    response["clipboard_text"] = self._pending_clipboard_text
                    self._pending_clipboard_text = None
            return response
        if kind == "notification.sync":
            title = message.get("title")
            body = message.get("body", "")
            app_name = message.get("app_name", "Android app")
            if (
                not isinstance(title, str) or not title.strip() or len(title) > 256
                or not isinstance(body, str) or len(body) > 2048
                or not isinstance(app_name, str) or not app_name.strip() or len(app_name) > 120
            ):
                raise ValueError("Invalid notification content.")
            notification = {"device_name": device_name, "app_name": app_name.strip(),
                "title": title.strip(), "body": body, "received_at": time.time()}
            for listener in tuple(self.notification_listeners):
                try:
                    listener(notification)
                except Exception:
                    pass
            return {"kind": "notification.accept"}
        if kind == "photos.page":
            photos = message.get("photos")
            if not isinstance(photos, list) or len(photos) > 12:
                raise ValueError("Invalid phone photo page.")
            safe_photos = []
            thumbnail_bytes = 0
            for photo in photos:
                if not isinstance(photo, dict):
                    raise ValueError("Invalid phone photo entry.")
                media_id, name, thumbnail = photo.get("id"), photo.get("name"), photo.get("thumbnail")
                if (
                    not isinstance(media_id, str) or not re.fullmatch(r"[0-9]{1,20}", media_id)
                    or not isinstance(name, str) or not name.strip() or len(name) > 240
                    or not isinstance(thumbnail, str) or len(thumbnail) > 18000
                ):
                    raise ValueError("Invalid phone photo details.")
                try:
                    decoded = base64.b64decode(thumbnail, validate=True)
                except (ValueError, binascii.Error) as error:
                    raise ValueError("Invalid phone photo thumbnail.") from error
                thumbnail_bytes += len(decoded)
                if len(decoded) > 12 * 1024 or thumbnail_bytes > 72 * 1024:
                    raise ValueError("Phone photo thumbnails exceed the preview limit.")
                safe_photos.append({"id": media_id, "name": name.strip(), "thumbnail": thumbnail,
                    "date_added": int(photo.get("date_added", 0))})
            self.latest_phone_photos = safe_photos
            self.phone_photos_message = f"Loaded {len(safe_photos)} recent phone photos."
            with self._photo_lock:
                self._photos_requested = False
            for listener in tuple(self.phone_photos_listeners):
                try:
                    listener(safe_photos)
                except Exception:
                    pass
            return {"kind": "photos.page.accept", "count": len(safe_photos)}
        if kind == "photos.unavailable":
            reason = message.get("message", "Allow photo access in Link to Linux on Android.")
            if not isinstance(reason, str) or len(reason) > 240:
                reason = "Allow photo access in Link to Linux on Android."
            self.phone_photos_message = reason
            with self._photo_lock:
                self._photos_requested = False
            for listener in tuple(self.phone_photos_listeners):
                try:
                    listener([])
                except Exception:
                    pass
            return {"kind": "photos.unavailable.accept", "message": reason}
        if kind == "photos.download.accept":
            media_id = message.get("id")
            mode = message.get("mode", "save")
            with self._photo_lock:
                if (not self._pending_phone_photo_id or media_id != self._pending_phone_photo_id
                        or mode != self._pending_phone_photo_mode):
                    raise ValueError("This phone photo request has expired.")
                self._pending_phone_photo_id = ""
            return {"kind": "photos.download.accepted", "id": media_id, "mode": mode}
        if kind == "clipboard.state":
            enabled = message.get("enabled")
            if not isinstance(enabled, bool):
                raise ValueError("Invalid clipboard preference.")
            self._phone_clipboard_enabled = enabled
            return {"kind": "clipboard.state.accept"}
        if kind == "clipboard.update":
            text = message.get("text")
            self._phone_clipboard_enabled = message.get("clipboard_enabled") is True
            if not self._phone_clipboard_enabled:
                raise ValueError("Enable clipboard sharing on the phone first.")
            if not isinstance(text, str) or len(text.encode("utf-8")) > 64 * 1024:
                raise ValueError("Clipboard text is limited to 64 KB.")
            if not self.clipboard_enabled():
                raise ValueError("Enable clipboard sharing on the desktop first.")
            if self.on_clipboard is not None and self.on_clipboard(device_id, text) is False:
                raise ValueError("Clipboard text could not be applied on the desktop.")
            for listener in tuple(self.clipboard_listeners):
                try:
                    listener(device_id, text)
                except Exception:
                    pass
            return {"kind": "clipboard.accept"}
        if kind == "remote.input":
            if not self.remote_input_enabled() or self.on_remote_input is None:
                raise ValueError("Remote input is disabled or unavailable on the desktop.")
            action = message.get("action")
            if action == "move":
                dx, dy = message.get("dx"), message.get("dy")
                if type(dx) is not int or type(dy) is not int or abs(dx) > 2000 or abs(dy) > 2000:
                    raise ValueError("Invalid pointer movement.")
                self.on_remote_input("move", dx=dx, dy=dy)
            elif action == "click":
                button = message.get("button", 1)
                if type(button) is not int or button not in {1, 2, 3}:
                    raise ValueError("Invalid mouse button.")
                self.on_remote_input("click", button=button)
            elif action == "scroll":
                dx, dy = message.get("dx", 0), message.get("dy", 0)
                if (
                    type(dx) is not int or type(dy) is not int
                    or abs(dx) > 20 or abs(dy) > 20
                ):
                    raise ValueError("Invalid scroll distance.")
                self.on_remote_input("scroll", dx=dx, dy=dy)
            elif action == "type":
                text = message.get("text")
                if not isinstance(text, str) or not text or len(text) > 1024:
                    raise ValueError("Invalid text input.")
                self.on_remote_input("type", text=text)
            elif action == "key":
                key = message.get("key")
                if not isinstance(key, str) or key not in {"Enter", "Backspace", "Tab", "Escape", "Left", "Right", "Up", "Down"}:
                    raise ValueError("Unsupported keyboard key.")
                repeat = message.get("repeat", 1)
                if type(repeat) is not int or not 1 <= repeat <= 1024:
                    raise ValueError("Invalid key repeat.")
                self.on_remote_input("key", key=key, repeat=repeat)
            else:
                raise ValueError("Unsupported remote input action.")
            return {"kind": "remote.input.accept"}
        if kind == "file.begin":
            if transfer:
                raise ValueError("A file transfer is already in progress.")
            transfer_id = message.get("transfer_id")
            filename = message.get("filename")
            size = message.get("size_bytes")
            category = message.get("category")
            mime_type = message.get("mime_type", "application/octet-stream")
            if not isinstance(transfer_id, str) or not re.fullmatch(r"[0-9a-f-]{36}", transfer_id):
                raise ValueError("Invalid transfer ID.")
            if (
                not isinstance(filename, str) or not filename.strip() or len(filename) > 240
                or filename in {".", ".."} or "/" in filename or "\\" in filename
                or any(ord(char) < 32 for char in filename)
            ):
                raise ValueError("Invalid file name.")
            if type(size) is not int or size < -1 or size > MAX_TRANSFER_BYTES:
                raise ValueError("File exceeds the 256 MB transfer limit.")
            if category not in {"file", "photo", "preview"}:
                raise ValueError("Unsupported transfer category.")
            if category == "preview" and size > 32 * 1024 * 1024:
                raise ValueError("This image is too large to preview (32 MB limit). Save it to the desktop instead.")
            if not isinstance(mime_type, str) or len(mime_type) > 120:
                raise ValueError("Invalid content type.")
            directory = (Path.home() / ".cache" / "linktolinux" / "photo-previews") if category == "preview" else Path(self.download_directory()).expanduser()
            directory.mkdir(parents=True, exist_ok=True)
            temporary = tempfile.NamedTemporaryFile(
                prefix=".linktolinux-", suffix=".part", dir=directory, delete=False
            )
            transfer.update({
                "id": transfer_id, "filename": filename.strip(), "size_expected": size,
                "category": category, "mime_type": mime_type, "stream": temporary,
                "temporary": Path(temporary.name), "bytes_written": 0, "next_chunk": 0,
                "digest": hashlib.sha256(),
            })
            return {"kind": "file.ready", "transfer_id": transfer_id}
        if kind == "file.get.begin":
            if transfer:
                raise ValueError("Another file transfer is in progress.")
            transfer_id = message.get("transfer_id")
            with self._desktop_files_lock:
                offered = self.pending_desktop_files.get(transfer_id)
            if offered is None:
                raise ValueError("This desktop file is no longer available.")
            stream = open(offered["path"], "rb")
            current_size = os.fstat(stream.fileno()).st_size
            if current_size != offered["size_bytes"] or current_size > MAX_TRANSFER_BYTES:
                stream.close()
                raise ValueError("The desktop file changed after it was queued.")
            transfer.update({
                "direction": "outgoing", "id": transfer_id, "stream": stream,
                "size_expected": current_size, "bytes_read": 0, "next_chunk": 0,
                "digest": hashlib.sha256(), "offer": offered,
            })
            return {
                "kind": "file.get.ready", "transfer_id": transfer_id,
                "filename": offered["filename"], "size_bytes": current_size,
                "mime_type": offered["mime_type"], "category": offered["category"],
            }
        if kind == "file.get.chunk":
            if not transfer or transfer.get("direction") != "outgoing" or message.get("transfer_id") != transfer.get("id"):
                raise ValueError("No matching desktop file transfer is active.")
            index = message.get("index")
            if type(index) is not int or index != transfer["next_chunk"]:
                raise ValueError("Invalid desktop file chunk sequence.")
            chunk = transfer["stream"].read(DESKTOP_CHUNK_BYTES)
            if not chunk:
                raise ValueError("The desktop file ended unexpectedly.")
            transfer["digest"].update(chunk)
            transfer["bytes_read"] += len(chunk)
            transfer["next_chunk"] += 1
            return {
                "kind": "file.get.data", "transfer_id": transfer["id"], "index": index,
                "data": base64.b64encode(chunk).decode("ascii"),
            }
        if kind == "file.get.finish":
            if not transfer or transfer.get("direction") != "outgoing" or message.get("transfer_id") != transfer.get("id"):
                raise ValueError("No matching desktop file transfer is active.")
            if transfer["bytes_read"] != transfer["size_expected"] or message.get("sha256") != transfer["digest"].hexdigest():
                raise ValueError("The phone did not verify the full desktop file.")
            transfer["stream"].close()
            offer = transfer["offer"]
            with self._desktop_files_lock:
                self.pending_desktop_files.pop(transfer["id"], None)
            sent = {key: offer[key] for key in ("transfer_id", "filename", "size_bytes", "category")}
            sent["device_name"] = device_name
            transfer.clear()
            for listener in tuple(self.file_sent_listeners):
                try:
                    listener(sent)
                except Exception:
                    pass
            return {"kind": "file.get.saved", "filename": sent["filename"]}
        if kind == "file.get.cancel":
            if transfer.get("direction") == "outgoing":
                self._discard_transfer(transfer)
            return {"kind": "file.get.cancelled"}
        if kind == "file.chunk":
            if not transfer or message.get("transfer_id") != transfer.get("id"):
                raise ValueError("No matching transfer is active.")
            index = message.get("index")
            encoded = message.get("data")
            if type(index) is not int or index != transfer["next_chunk"] or not isinstance(encoded, str):
                raise ValueError("Invalid file chunk sequence.")
            try:
                chunk = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as error:
                raise ValueError("Invalid file chunk encoding.") from error
            new_size = transfer["bytes_written"] + len(chunk)
            if not chunk or len(chunk) > 64 * 1024 or new_size > MAX_TRANSFER_BYTES:
                raise ValueError("Invalid file chunk size.")
            expected = transfer["size_expected"]
            if expected >= 0 and new_size > expected:
                raise ValueError("Received more data than the declared file size.")
            transfer["stream"].write(chunk)
            transfer["digest"].update(chunk)
            transfer["bytes_written"] = new_size
            transfer["next_chunk"] += 1
            return {"kind": "file.ack", "index": index}
        if kind == "file.finish":
            if not transfer or message.get("transfer_id") != transfer.get("id"):
                raise ValueError("No matching transfer is active.")
            expected = transfer["size_expected"]
            actual = transfer["bytes_written"]
            if expected >= 0 and actual != expected:
                raise ValueError("The received file size does not match.")
            if message.get("sha256") != transfer["digest"].hexdigest():
                raise ValueError("The received file failed its integrity check.")
            transfer["stream"].flush()
            os.fsync(transfer["stream"].fileno())
            transfer["stream"].close()
            directory = Path(transfer["temporary"]).parent
            is_preview = transfer["category"] == "preview"
            if is_preview:
                cached_previews = sorted(directory.glob("preview-*"), key=lambda item: item.stat().st_mtime)
                for old_preview in cached_previews[:-9]:
                    old_preview.unlink(missing_ok=True)
                destination = directory / f"preview-{uuid.uuid4().hex}-{transfer['filename']}"
                os.replace(transfer["temporary"], destination)
                received = {"filename": transfer["filename"], "path": str(destination), "size_bytes": actual}
                transfer.clear()
                for listener in tuple(self.photo_preview_listeners):
                    try:
                        listener(received)
                    except Exception:
                        pass
                return {"kind": "file.preview.saved", "filename": received["filename"]}
            destination = directory / transfer["filename"]
            stem, suffix = destination.stem, destination.suffix
            sequence = 1
            while destination.exists():
                destination = directory / f"{stem} ({sequence}){suffix}"
                sequence += 1
            os.replace(transfer["temporary"], destination)
            received = {
                "device_id": device_id, "device_name": device_name,
                "filename": destination.name, "path": str(destination),
                "size_bytes": actual, "category": transfer["category"],
                "mime_type": transfer["mime_type"], "received_at": time.time(),
            }
            self.received_files.append(received)
            transfer.clear()
            if self.on_file is not None:
                self.on_file(received)
            for listener in tuple(self.file_listeners):
                try:
                    listener(received)
                except Exception:
                    pass
            return {"kind": "file.saved", "filename": destination.name}
        if kind == "file.cancel":
            self._discard_transfer(transfer)
            return {"kind": "file.cancelled"}
        raise ValueError("Unsupported live-session message.")

    @staticmethod
    def _discard_transfer(transfer: dict) -> None:
        if not transfer:
            return
        stream = transfer.get("stream")
        if stream is not None and not stream.closed:
            stream.close()
        temporary = transfer.get("temporary")
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        transfer.clear()

    def _finish_live_session(self, device_id: str) -> None:
        if self.connected_device_id != device_id:
            return
        self.session_connected = False
        self._active_socket = None
        self.phone_ring_requested = False
        self.phone_ring_active = False
        self.pending_media_command = None
        status = dict(self.latest_status)
        status.update({"connected": False, "device_id": device_id, "last_seen": time.time()})
        self.latest_status = status
        if self.on_status is not None:
            self.on_status(device_id, status)
        for listener in tuple(self.status_listeners):
            try:
                listener(device_id, status)
            except Exception:
                pass
        self._paired_once = False
        self._expires_at = 0.0

    def _stop_expired(self) -> None:
        if not self._paired_once and self._expires_at and time.time() >= self._expires_at:
            if self._keep_listener:
                self._code = ""
                self._expires_at = 0.0
                self._expiry_timer = None
            else:
                self.stop()

    def stop(self) -> None:
        self._keep_listener = False
        server, self._server = self._server, None
        active_socket, self._active_socket = self._active_socket, None
        self._expires_at = 0.0
        self._code = ""
        self._paired_once = False
        self._phone_clipboard_enabled = False
        self._pending_clipboard_text = None
        self.session_connected = False
        self.connected_device_id = ""
        self.connected_device_name = ""
        self.phone_ring_requested = False
        self.phone_ring_active = False
        self.pending_media_command = None
        timer, self._expiry_timer = self._expiry_timer, None
        if timer is not None and timer is not threading.current_thread():
            timer.cancel()
        if server is not None:
            server.shutdown()
            server.server_close()
        if active_socket is not None:
            try:
                active_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            active_socket.close()
        self._thread = None
