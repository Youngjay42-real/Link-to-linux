from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class TransferRecord:
    source: str
    destination: str
    size_bytes: int
    status: str = "queued"


def safe_destination(base_path: str, filename: str) -> str:
    if not filename or filename in {"", ".", ".."}:
        raise ValueError("filename is invalid")
    normalized = os.path.basename(filename)
    if normalized != filename:
        raise ValueError("path traversal is not allowed")
    return os.path.join(base_path, normalized)


class TransferManager:
    def __init__(self, destination_root: str) -> None:
        self.destination_root = destination_root
        self.history: list[TransferRecord] = []

    def enqueue(self, source: str, filename: str, size_bytes: int) -> TransferRecord:
        destination = safe_destination(self.destination_root, filename)
        record = TransferRecord(source=source, destination=destination, size_bytes=size_bytes)
        self.history.append(record)
        return record
