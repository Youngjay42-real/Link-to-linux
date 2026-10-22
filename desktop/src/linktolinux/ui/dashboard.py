from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from linktolinux.application import LinkToLinuxApplication


@dataclass(slots=True)
class DashboardSummary:
    device_name: str
    device_id: str
    transport: str
    paired_devices: list[str] = field(default_factory=list)
    notifications_enabled: bool = False
    clipboard_enabled: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "device_name": self.device_name,
            "device_id": self.device_id,
            "transport": self.transport,
            "paired_devices": self.paired_devices,
            "notifications_enabled": self.notifications_enabled,
            "clipboard_enabled": self.clipboard_enabled,
        }


class DesktopDashboard:
    def __init__(self, app: "LinkToLinuxApplication") -> None:
        self.app = app

    def summary(self) -> DashboardSummary:
        connection = self.app.connection_manager.status
        return DashboardSummary(
            device_name=self.app.device_name,
            device_id=self.app.identity.device_id,
            transport=connection.transport.value,
            paired_devices=sorted(self.app.settings.paired_devices),
            notifications_enabled=self.app.notification_service.filter.enabled,
            clipboard_enabled=self.app.clipboard_service.enabled,
        )
