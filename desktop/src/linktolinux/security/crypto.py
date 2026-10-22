from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DeviceIdentity:
    device_id: str
    public_key: str
    fingerprint: str


def generate_device_identity(device_id: str | None = None) -> DeviceIdentity:
    if device_id is None:
        device_id = secrets.token_hex(8)
    private_material = secrets.token_hex(32)
    public_key = hashlib.sha256(private_material.encode("utf-8")).hexdigest()
    fingerprint = hashlib.sha256(f"{device_id}:{public_key}".encode("utf-8")).hexdigest()
    return DeviceIdentity(device_id=device_id, public_key=public_key, fingerprint=fingerprint)


def create_pairing_challenge(length: int = 6) -> str:
    if length < 4 or length > 8:
        raise ValueError("Pairing code length must be between 4 and 8")
    return str(secrets.randbelow(10 ** length)).zfill(length)


def verify_pairing_code(challenge: str, expected: str) -> bool:
    if not challenge or not expected:
        return False
    try:
        return challenge.strip() == expected.strip()
    except (AttributeError, TypeError):
        return False
