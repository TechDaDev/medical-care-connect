"""Provider-neutral storage abstraction for consultation attachments.

All attachment storage goes through this interface.
Application code never depends on FileSystemStorage or S3 directly.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import BinaryIO, Optional


@dataclass
class StoredObject:
    """Result of a successful storage operation."""

    storage_key: str
    provider: str
    size_bytes: int


class AttachmentStorageBackend(ABC):
    """Interface for all attachment storage providers."""

    @abstractmethod
    def save(self, file: BinaryIO, storage_key: str) -> StoredObject:
        """Persist file bytes under the given storage key."""

    @abstractmethod
    def open(self, storage_key: str) -> Optional[BinaryIO]:
        """Return a readable stream for an existing object, or None."""

    @abstractmethod
    def delete(self, storage_key: str) -> bool:
        """Remove the underlying object. Returns True if existed."""

    @abstractmethod
    def exists(self, storage_key: str) -> bool:
        """Check whether the object exists."""

    @abstractmethod
    def size(self, storage_key: str) -> Optional[int]:
        """Return object size in bytes, or None if missing."""

    @abstractmethod
    def metadata(self, storage_key: str) -> dict:
        """Return available metadata dict (size, etag, last_modified…)."""

    @abstractmethod
    def generate_internal_reference(self, storage_key: str) -> str:
        """Return a provider-scoped reference (not a public URL)."""
