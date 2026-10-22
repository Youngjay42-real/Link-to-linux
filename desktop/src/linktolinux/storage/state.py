from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import os


@dataclass
class DesktopSettings:
    download_directory: str = field(default_factory=lambda: str(Path.home() / "Downloads"))
    notifications_enabled: bool = False
    clipboard_enabled: bool = False
    paired_devices: set[str] = field(default_factory=set)
    auto_load_phone_photos: bool = False

    @staticmethod
    def path() -> Path:
        return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "linktolinux" / "settings.json"

    @classmethod
    def load(cls) -> "DesktopSettings":
        try:
            data = json.loads(cls.path().read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return cls()
            return cls(
                download_directory=str(data.get("download_directory", Path.home() / "Downloads")),
                notifications_enabled=data.get("notifications_enabled") is True,
                clipboard_enabled=data.get("clipboard_enabled") is True,
                auto_load_phone_photos=data.get("auto_load_phone_photos") is True,
            )
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self) -> None:
        path = self.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({
            "download_directory": self.download_directory,
            "notifications_enabled": self.notifications_enabled,
            "clipboard_enabled": self.clipboard_enabled,
            "auto_load_phone_photos": self.auto_load_phone_photos,
        }, indent=2), encoding="utf-8")
        temporary.replace(path)
