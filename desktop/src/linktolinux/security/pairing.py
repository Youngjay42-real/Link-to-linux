from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from linktolinux.security.crypto import verify_pairing_code


@dataclass(frozen=True)
class PairingSession:
    device_id: str
    code: str
    expires_at: float


def create_pairing_session(device_id: str, code: str, ttl_seconds: int = 90) -> PairingSession:
    if not device_id:
        raise ValueError("device_id is required")
    expires_at = time.time() + ttl_seconds
    return PairingSession(device_id=device_id, code=code, expires_at=expires_at)


def validate_pairing_session(session: PairingSession, candidate: str) -> bool:
    if session.expires_at < time.time():
        return False
    return verify_pairing_code(candidate, session.code)
