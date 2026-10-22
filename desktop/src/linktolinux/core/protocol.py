from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

SUPPORTED_PROTOCOL_VERSIONS = {"1.0.0"}
MAX_PAYLOAD_BYTES = 1024 * 1024
ALLOWED_MESSAGE_KINDS = {
    "pairing.request",
    "pairing.accept",
    "pairing.verify",
    "device.status",
    "file.list",
    "file.transfer",
    "notification.sync",
    "clipboard.sync",
}


@dataclass(frozen=True)
class Envelope:
    version: str
    kind: str
    device_id: str
    timestamp: int
    payload: dict[str, Any]
    nonce: str
    signature: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "kind": self.kind,
            "device_id": self.device_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "nonce": self.nonce,
            "signature": self.signature,
        }


def build_message(kind: str, device_id: str, payload: dict[str, Any], *, nonce: str, signature: str) -> Envelope:
    now = int(datetime.now(timezone.utc).timestamp())
    if kind not in ALLOWED_MESSAGE_KINDS:
        raise ValueError(f"Unsupported message kind: {kind}")
    if not device_id or len(device_id) < 8:
        raise ValueError("device_id must be at least 8 characters")
    envelope = Envelope(
        version="1.0.0",
        kind=kind,
        device_id=device_id,
        timestamp=now,
        payload=payload,
        nonce=nonce,
        signature=signature,
    )
    validate_message(envelope.as_dict())
    return envelope


def validate_message(message: dict[str, Any]) -> bool:
    if not isinstance(message, dict):
        raise ValueError("Message must be a dictionary")
    if message.get("version") not in SUPPORTED_PROTOCOL_VERSIONS:
        raise ValueError("Unsupported protocol version")
    kind = message.get("kind")
    if kind not in ALLOWED_MESSAGE_KINDS:
        raise ValueError(f"Unsupported message kind: {kind}")
    device_id = message.get("device_id")
    if not isinstance(device_id, str) or len(device_id) < 8:
        raise ValueError("device_id is invalid")
    payload = message.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    if len(str(payload).encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise ValueError("payload exceeds maximum size")
    timestamp = int(message.get("timestamp", 0))
    now = int(datetime.now(timezone.utc).timestamp())
    if abs(now - timestamp) > 300:
        raise ValueError("timestamp is outside of the acceptable skew window")
    nonce = message.get("nonce")
    signature = message.get("signature")
    if not isinstance(nonce, str) or len(nonce) < 12:
        raise ValueError("nonce is invalid")
    if not isinstance(signature, str) or len(signature) < 16:
        raise ValueError("signature is invalid")
    return True
