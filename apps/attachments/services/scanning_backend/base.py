"""Abstract scanner interface with scan-result types."""

from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import BinaryIO


class ScanResult:
    """Immutable scan outcome."""

    CLEAN = "clean"
    INFECTED = "infected"
    FAILED = "scan_failed"

    def __init__(self, status: str, detail: str = ""):
        assert status in (self.CLEAN, self.INFECTED, self.FAILED), f"Invalid status: {status}"
        self._status = status
        self._detail = detail

    @property
    def status(self) -> str:
        return self._status

    @property
    def detail(self) -> str:
        return self._detail

    @classmethod
    def clean(cls, detail: str = "") -> "ScanResult":
        return cls(cls.CLEAN, detail)

    @classmethod
    def infected(cls, detail: str = "") -> "ScanResult":
        return cls(cls.INFECTED, detail)

    @classmethod
    def failed(cls, detail: str = "") -> "ScanResult":
        return cls(cls.FAILED, detail)


class BaseScanner(ABC):
    """Abstract malware scanner."""

    @abstractmethod
    def scan(self, file: BinaryIO) -> ScanResult:
        """Scan a file-like object. Raises on connection/configuration errors."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Lightweight health check — can the scanner connect?"""
        ...
