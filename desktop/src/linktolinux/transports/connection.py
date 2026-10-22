from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class TransportType(str, Enum):
    WIFI = "wifi"
    USB = "usb"
    UNKNOWN = "unknown"


@dataclass
class ConnectionStatus:
    connected: bool = False
    transport: TransportType = TransportType.UNKNOWN
    device_id: str | None = None
    last_seen: str | None = None


class ConnectionManager:
    def __init__(self) -> None:
        self.status = ConnectionStatus()

    def connect(self, transport: TransportType, device_id: str | None = None) -> ConnectionStatus:
        self.status = ConnectionStatus(connected=True, transport=transport, device_id=device_id, last_seen="just now")
        return self.status

    def disconnect(self) -> ConnectionStatus:
        self.status = ConnectionStatus()
        return self.status

    def update_last_seen(self, value: str) -> None:
        self.status.last_seen = value

    def as_dict(self) -> dict[str, Any]:
        return {
            "connected": self.status.connected,
            "transport": self.status.transport.value,
            "device_id": self.status.device_id,
            "last_seen": self.status.last_seen,
        }
