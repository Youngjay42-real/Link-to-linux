from __future__ import annotations

from linktolinux.security.crypto import create_pairing_challenge, generate_device_identity, verify_pairing_code
from linktolinux.security.pairing import PairingSession, create_pairing_session, validate_pairing_session


def test_generate_device_identity() -> None:
    identity = generate_device_identity("android-1234")
    assert identity.device_id == "android-1234"
    assert len(identity.fingerprint) == 64


def test_pairing_challenge_and_validation() -> None:
    challenge = create_pairing_challenge(6)
    assert len(challenge) == 6
    assert verify_pairing_code(challenge, challenge)


def test_pairing_session_validation() -> None:
    session = create_pairing_session("device-1234", "123456", ttl_seconds=120)
    assert isinstance(session, PairingSession)
    assert validate_pairing_session(session, "123456") is True
    assert validate_pairing_session(session, "654321") is False
