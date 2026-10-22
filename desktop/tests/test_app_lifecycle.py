from __future__ import annotations

from linktolinux.application import LinkToLinuxApplication
from linktolinux.services.file_transfer import safe_destination
from linktolinux.transports.discovery import LocalDiscoveryService


def test_application_pairing_and_revocation() -> None:
    app = LinkToLinuxApplication("Ubuntu Desktop")
    session = app.begin_pairing("phone-1234", "654321")
    assert session.device_id == "phone-1234"
    assert app.pair_device("phone-1234", "654321") is True
    assert "phone-1234" in app.settings.paired_devices
    assert app.revoke_device("phone-1234") is True
    assert "phone-1234" not in app.settings.paired_devices


def test_discovery_service_returns_local_candidate() -> None:
    service = LocalDiscoveryService()
    candidates = service.discover()
    assert len(candidates) >= 1
    assert candidates[0].transport == "wifi"
    assert "Linux Desktop" in candidates[0].name


def test_file_transfer_rejects_path_traversal() -> None:
    try:
        safe_destination("/tmp", "../secret.txt")
        assert False, "Expected ValueError"
    except ValueError:
        pass
