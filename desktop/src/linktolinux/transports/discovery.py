from __future__ import annotations

import socket
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DiscoveryCandidate:
    name: str
    host: str
    port: int = 0
    transport: str = "wifi"
    device_id: str = ""

    def as_dict(self) -> dict[str, str | int]:
        return {
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "transport": self.transport,
            "device_id": self.device_id,
        }


class LocalDiscoveryService:
    def __init__(self, base_host: str | None = None) -> None:
        if base_host is not None:
            self.base_host = base_host
            return
        try:
            self.base_host = socket.gethostbyname(socket.gethostname())
        except OSError:
            self.base_host = "127.0.0.1"

    def discover(self) -> list[DiscoveryCandidate]:
        local_candidates: list[DiscoveryCandidate] = [
            DiscoveryCandidate(
                name="Linux Desktop",
                host=self.base_host,
                port=443,
                transport="wifi",
                device_id="linux-desktop",
            )
        ]
        return local_candidates
