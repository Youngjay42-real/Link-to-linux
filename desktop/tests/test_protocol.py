from __future__ import annotations

from linktolinux.core.protocol import build_message, validate_message


def test_validate_message_accepts_valid_payload() -> None:
    message = build_message(
        "device.status",
        "device-1234",
        {"battery": 87, "charging": True},
        nonce="aabbccddeeff0011223344",
        signature="abcdef0123456789abcdef",
    )
    assert validate_message(message.as_dict()) is True


def test_validate_message_rejects_unsupported_kind() -> None:
    try:
        validate_message({
            "version": "1.0.0",
            "kind": "not.allowed",
            "device_id": "device-1234",
            "timestamp": 1730000000,
            "payload": {"ok": True},
            "nonce": "aabbccddeeff0011223344",
            "signature": "abcdef0123456789abcdef",
        })
        assert False, "Expected ValueError"
    except ValueError:
        pass
