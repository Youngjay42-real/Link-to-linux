from __future__ import annotations

from linktolinux.core.device import DeviceInfo, DeviceStatusReport
from linktolinux.core.protocol import validate_message
from linktolinux.security.crypto import DeviceIdentity, create_pairing_challenge, generate_device_identity, verify_pairing_code
from linktolinux.security.pairing import PairingSession, create_pairing_session, validate_pairing_session
from linktolinux.services.clipboard import ClipboardSyncService
from linktolinux.services.notifications import NotificationSyncService
from linktolinux.services.remote_input import RemoteInputController
from linktolinux.storage.state import DesktopSettings
from linktolinux.transports.connection import ConnectionManager, TransportType
from linktolinux.transports.discovery import LocalDiscoveryService
from linktolinux.transports.pairing_server import DesktopPairingServer
from linktolinux.ui.dashboard import DesktopDashboard


class LinkToLinuxApplication:
    def __init__(self, device_name: str = "Linux") -> None:
        self.device_name = device_name
        self.identity: DeviceIdentity = generate_device_identity(device_name)
        self.settings = DesktopSettings.load()
        self.connection_manager = ConnectionManager()
        self.notification_service = NotificationSyncService()
        self.clipboard_service = ClipboardSyncService()
        self.remote_input = RemoteInputController()
        if self.settings.notifications_enabled:
            self.notification_service.enable()
        if self.settings.clipboard_enabled:
            self.clipboard_service.enable()
        self.pending_pairing: PairingSession | None = None
        self.phone_status: dict = {}
        self.received_files: list[dict] = []
        self.phone_photos: list[dict] = []
        self.pairing_server = DesktopPairingServer(
            self._record_paired_device,
            desktop_name=device_name,
            on_status=self._update_phone_status,
            on_file=self._record_received_file,
            on_clipboard=self._receive_clipboard_text,
            clipboard_enabled=lambda: self.clipboard_service.enabled,
            remote_input_available=lambda: self.remote_input.available,
            remote_input_enabled=lambda: self.settings.remote_input_enabled and self.remote_input.available,
            on_remote_input=self.remote_input.perform,
            download_directory=lambda: self.settings.download_directory,
        )
        self.settings.paired_devices.update(self.pairing_server.trusted_devices)
        self.pairing_server.auto_load_phone_photos = self.settings.auto_load_phone_photos
        self.pairing_server.add_phone_photos_listener(self._update_phone_photos)
        if self.pairing_server.trusted_devices:
            self.pairing_server.start(trusted_only=True)
        self.dashboard = DesktopDashboard(self)
        self.discovery_service = LocalDiscoveryService()

    def _record_paired_device(self, device_id: str, _device_name: str) -> None:
        self.settings.paired_devices.add(device_id)

    def set_notifications_enabled(self, enabled: bool) -> None:
        self.settings.notifications_enabled = enabled
        self.settings.save()
        (self.notification_service.enable if enabled else self.notification_service.disable)()

    def set_clipboard_enabled(self, enabled: bool) -> None:
        self.settings.clipboard_enabled = enabled
        self.settings.save()
        (self.clipboard_service.enable if enabled else self.clipboard_service.disable)()

    def set_remote_input_enabled(self, enabled: bool) -> None:
        self.settings.remote_input_enabled = bool(enabled and self.remote_input.available)
        self.settings.save()

    def set_download_directory(self, directory: str) -> None:
        self.settings.download_directory = directory
        self.settings.save()

    def enable_photo_auto_load(self) -> None:
        self.settings.auto_load_phone_photos = True
        self.settings.save()
        self.pairing_server.auto_load_phone_photos = True

    def _update_phone_status(self, _device_id: str, status: dict) -> None:
        self.phone_status = dict(status)

    def _record_received_file(self, received: dict) -> None:
        self.received_files.insert(0, dict(received))

    def _update_phone_photos(self, photos: list[dict]) -> None:
        self.phone_photos = [dict(photo) for photo in photos]

    def _receive_clipboard_text(self, _device_id: str, text: str) -> bool:
        if self.clipboard_service.enabled:
            self.clipboard_service.sync_text(text)
            return True
        return False

    def validate_incoming_message(self, message: dict) -> bool:
        return validate_message(message)

    def set_transport(self, transport: str) -> None:
        transport_type = TransportType(transport)
        self.connection_manager.connect(transport_type, self.identity.device_id)

    def begin_pairing(self, device_id: str, code: str | None = None) -> PairingSession:
        if not device_id:
            raise ValueError("device_id is required")
        challenge = code or create_pairing_challenge(6)
        session = create_pairing_session(device_id, challenge, ttl_seconds=120)
        self.pending_pairing = session
        return session

    def pair_device(self, device_id: str, candidate_code: str) -> bool:
        if self.pending_pairing is None:
            return False
        if self.pending_pairing.device_id != device_id:
            return False
        if not validate_pairing_session(self.pending_pairing, candidate_code):
            return False
        self.settings.paired_devices.add(device_id)
        self.pending_pairing = None
        return True

    def revoke_device(self, device_id: str) -> bool:
        if device_id in self.settings.paired_devices:
            self.settings.paired_devices.remove(device_id)
            self.pairing_server.revoke_device(device_id)
            return True
        return False

    def discover_devices(self) -> list[dict]:
        return [candidate.as_dict() for candidate in self.discovery_service.discover()]

    def device_status(self, device_id: str | None = None) -> DeviceStatusReport:
        report = DeviceStatusReport(
            connected=self.connection_manager.status.connected,
            transport=self.connection_manager.status.transport.value,
            device_id=device_id or self.connection_manager.status.device_id,
            battery_level=87,
            storage_total_gb=256,
            storage_free_gb=86,
            last_sync="just now",
        )
        return report

    def status(self) -> dict:
        dashboard = self.dashboard.summary()
        return {
            "device_name": self.device_name,
            "device_id": self.identity.device_id,
            "connection": self.connection_manager.as_dict(),
            "dashboard": dashboard.as_dict(),
            "notifications_enabled": self.notification_service.filter.enabled,
            "clipboard_enabled": self.clipboard_service.enabled,
            "paired_devices": sorted(self.settings.paired_devices),
        }
