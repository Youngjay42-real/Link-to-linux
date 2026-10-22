from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NotificationFilter:
    allowed_apps: set[str] = field(default_factory=set)
    enabled: bool = False

    def allow_app(self, app_name: str) -> None:
        if app_name:
            self.allowed_apps.add(app_name)

    def should_sync(self, app_name: str) -> bool:
        return self.enabled and app_name in self.allowed_apps


class NotificationSyncService:
    def __init__(self) -> None:
        self.filter = NotificationFilter()

    def enable(self, allowed_apps: list[str] | None = None) -> None:
        self.filter.enabled = True
        for app in allowed_apps or []:
            self.filter.allow_app(app)

    def disable(self) -> None:
        self.filter.enabled = False
