from __future__ import annotations


class ClipboardSyncService:
    def __init__(self) -> None:
        self.enabled = False
        self.last_text: str | None = None

    def enable(self) -> None:
        self.enabled = True

    def disable(self) -> None:
        self.enabled = False
        self.last_text = None

    def sync_text(self, text: str) -> str:
        if not self.enabled:
            raise RuntimeError("clipboard sync is disabled")
        self.last_text = text
        return text
