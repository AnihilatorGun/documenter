import uuid
from pathlib import Path
from typing import Protocol


class Storage(Protocol):
    """Blob store for document files. The index in SQLite only keeps the returned key."""

    def upload(self, filename: str, mime_type: str, data: bytes) -> str: ...

    def download(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...

    def external_link(self, key: str) -> str | None:
        """URL where a human can open the file outside this app, if the backend has one."""
        ...


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def upload(self, filename: str, mime_type: str, data: bytes) -> str:
        key = f"{uuid.uuid4().hex}{Path(filename).suffix}"
        (self.root / key).write_bytes(data)
        return key

    def download(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def delete(self, key: str) -> None:
        (self.root / key).unlink(missing_ok=True)

    def external_link(self, key: str) -> str | None:
        return None
