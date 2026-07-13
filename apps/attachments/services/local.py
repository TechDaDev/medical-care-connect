"""Local-protected storage backend.

Files are stored outside STATIC_ROOT / MEDIA_ROOT and served
only through the authorized download endpoint — never via Nginx
or Django's static file server.
"""

import hashlib
import os
import shutil
from pathlib import Path
from typing import BinaryIO, Optional

from django.conf import settings

from apps.attachments.services.base import AttachmentStorageBackend, StoredObject


class LocalProtectedStorageBackend(AttachmentStorageBackend):
    """Stores files on local filesystem outside public directories.

    The root directory is configured via ATTACHMENT_LOCAL_ROOT.
    Files are organized as ``<root>/<prefix>/<storage_key>``.
    """

    def __init__(self) -> None:
        self._root = Path(settings.ATTACHMENT_LOCAL_ROOT)
        self._root.mkdir(parents=True, exist_ok=True)

    def _full_path(self, storage_key: str) -> Path:
        # Prefix first two chars to avoid flat directory
        prefix = storage_key[:2] if len(storage_key) > 1 else "xx"
        directory = self._root / prefix
        directory.mkdir(parents=True, exist_ok=True)
        return directory / storage_key

    def save(self, file: BinaryIO, storage_key: str) -> StoredObject:
        path = self._full_path(storage_key)
        written = 0
        with open(path, "wb") as dst:
            while True:
                chunk = file.read(65536)
                if not chunk:
                    break
                dst.write(chunk)
                written += len(chunk)
        return StoredObject(
            storage_key=storage_key,
            provider="local",
            size_bytes=written,
        )

    def open(self, storage_key: str) -> Optional[BinaryIO]:
        path = self._full_path(storage_key)
        if not path.exists():
            return None
        return open(path, "rb")

    def delete(self, storage_key: str) -> bool:
        path = self._full_path(storage_key)
        if not path.exists():
            return False
        path.unlink(missing_ok=True)
        return True

    def exists(self, storage_key: str) -> bool:
        return self._full_path(storage_key).exists()

    def size(self, storage_key: str) -> Optional[int]:
        path = self._full_path(storage_key)
        if not path.exists():
            return None
        return path.stat().st_size

    def metadata(self, storage_key: str) -> dict:
        path = self._full_path(storage_key)
        if not path.exists():
            return {"exists": False}
        stat = path.stat()
        return {
            "exists": True,
            "size_bytes": stat.st_size,
            "modified": stat.st_mtime,
            "provider": "local",
        }

    def generate_internal_reference(self, storage_key: str) -> str:
        return f"local://{storage_key}"
