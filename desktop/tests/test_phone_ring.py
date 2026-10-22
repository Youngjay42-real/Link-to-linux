from __future__ import annotations

from linktolinux.transports.pairing_server import DesktopPairingServer


def test_phone_ring_requires_connection_and_waits_for_android_ack(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    server = DesktopPairingServer(lambda _device_id, _name: None)

    assert server.set_phone_ringing(True) is False

    server.session_connected = True
    assert server.set_phone_ringing(True) is True
    waiting = server._process_session_message(
        "android-device", "Android phone", {"kind": "device.status", "phone_ringing": False}, {}
    )
    assert waiting["ring_phone"] is True
    assert waiting["phone_ring_active"] is False

    ringing = server._process_session_message(
        "android-device", "Android phone", {"kind": "device.status", "phone_ringing": True}, {}
    )
    assert ringing["ring_phone"] is True
    assert ringing["phone_ring_active"] is True

    assert server.set_phone_ringing(False) is True
    stopped = server._process_session_message(
        "android-device", "Android phone", {"kind": "device.status", "phone_ringing": False}, {}
    )
    assert stopped["ring_phone"] is False
    assert stopped["phone_ring_active"] is False


def test_media_controls_are_queued_once_and_status_is_exposed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    server = DesktopPairingServer(lambda _device_id, _name: None)
    assert server.request_media_control("next") is False

    server.session_connected = True
    assert server.request_media_control("next") is True
    command = dict(server.pending_media_command)
    response = server._process_session_message(
        "android-device", "Android phone", {
            "kind": "device.status",
            "model": "Android",
            "battery_percent": 70,
            "charging": False,
            "storage_total_bytes": 100,
            "storage_free_bytes": 50,
            "media": {"available": True, "title": "Track", "artist": "Artist", "playing": True},
        }, {},
    )
    assert response["media_command"] == command
    assert server.latest_status["media_title"] == "Track"
    assert server.latest_status["media_artist"] == "Artist"

    acknowledged = server._process_session_message(
        "android-device", "Android phone", {"kind": "device.status", "media_command_ack": command["id"]}, {},
    )
    assert acknowledged["media_command"] is None
    assert server.pending_media_command is None
