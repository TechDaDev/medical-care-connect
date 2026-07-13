"""Malware-scanning abstraction and disabled adapter."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from apps.attachments.services.base import AttachmentStorageBackend


class ScanVerdict(Enum):
    NOT_REQUIRED = "not_required"
    CLEAN = "clean"
    SUSPICIOUS = "suspicious"
    INFECTED = "infected"
    FAILED = "failed"


@dataclass
class ScanResult:
    verdict: ScanVerdict
    provider: str = ""
    reference: Optional[str] = None


class AttachmentScanner(ABC):
    """Interface for malware scanners."""

    @abstractmethod
    def scan(self, storage_backend: AttachmentStorageBackend, storage_key: str) -> ScanResult:
        ...


class DisabledAttachmentScanner(AttachmentScanner):
    """No-op scanner. All files pass without inspection."""

    def scan(self, storage_backend: AttachmentStorageBackend, storage_key: str) -> ScanResult:
        return ScanResult(
            verdict=ScanVerdict.NOT_REQUIRED,
            provider="disabled",
        )
