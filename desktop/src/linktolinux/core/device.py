from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DeviceInfo:
    device_id: str
    name: str
    transport: str = "wifi"
    status: str = "disconnected"
    battery_level: int | None = None
    charging: bool | None = None
    last_seen: str = "never"
    trusted: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "name": self.name,
            "transport": self.transport,
            "status": self.status,
            "battery_level": self.battery_level,
            "charging": self.charging,
            "last_seen": self.last_seen,
            "trusted": self.trusted,
        }


@dataclass(slots=True)
class DeviceStatusReport:
    connected: bool = False
    transport: str = "unknown"
    device_id: str | None = None
    battery_level: int | None = None
    storage_total_gb: int | None = None
    storage_free_gb: int | None = None
    last_sync: str = "never"

    def as_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "transport": self.transport,
            "device_id": self.device_id,
            "battery_level": self.battery_level,
            "storage_total_gb": self.storage_total_gb,
            "storage_free_gb": self.storage_free_gb,
            "last_sync": self.last_sync,
        }


@dataclass(slots=True)
class DeviceRegistry:
    devices: dict[str, DeviceInfo] = field(default_factory=dict)

    def add(self, device: DeviceInfo) -> None:
        self.devices[device.device_id] = device

    def remove(self, device_id: str) -> bool:
        return self.devices.pop(device_id, None) is not None

    def list_trusted(self) -> list[DeviceInfo]:
        return [device for device in self.devices.values() if device.trusted]
