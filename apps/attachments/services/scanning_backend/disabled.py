"""No-op scanner for development / testing — always returns CLEAN."""

from typing import BinaryIO

from django.conf import settings

from .base import BaseScanner, ScanResult


class DisabledScanner(BaseScanner):
    """Always reports clean.  Used when ATTACHMENT_SCAN_MODE=disabled."""

    def scan(self, file: BinaryIO) -> ScanResult:
        return ScanResult.clean("Scanning disabled")

    def is_available(self) -> bool:
        return True
