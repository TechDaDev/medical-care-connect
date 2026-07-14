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


class ClamavAttachmentScanner(AttachmentScanner):
    """Scans via clamd INSTREAM over TCP.  Reads file from storage backend."""

    def __init__(self):
        from django.conf import settings
        self._host = settings.CLAMAV_HOST
        self._port = settings.CLAMAV_PORT
        self._connect_timeout = getattr(settings, "CLAMAV_CONNECT_TIMEOUT", 5)
        self._read_timeout = getattr(settings, "CLAMAV_READ_TIMEOUT", 60)
        self._max_stream = getattr(settings, "CLAMAV_MAX_STREAM_BYTES", 0) or 0

    def scan(self, storage_backend: AttachmentStorageBackend, storage_key: str) -> ScanResult:
        import socket
        import struct
        import io

        CHUNK_SIZE = 8192
        ROOT_REPLY_OK = b"stream: OK"
        ROOT_REPLY_FOUND = b"FOUND"

        # Read from storage
        try:
            stream = storage_backend.open(storage_key)
            file_bytes = stream.read()
            stream.close()
        except Exception as exc:
            return ScanResult(verdict=ScanVerdict.FAILED, provider="clamav",
                              reference=str(exc)[:200])

        bio = io.BytesIO(file_bytes)

        # Build INSTREAM payload
        chunks = []
        total = 0
        while True:
            data = bio.read(CHUNK_SIZE)
            if not data:
                break
            if self._max_stream and total + len(data) > self._max_stream:
                data = data[: self._max_stream - total]
                if not data:
                    break
            chunks.append(struct.pack("!I", len(data)))
            chunks.append(data)
            total += len(data)
        chunks.append(struct.pack("!I", 0))
        payload = b"".join(chunks)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self._connect_timeout)
        try:
            sock.connect((self._host, self._port))
            sock.settimeout(self._read_timeout)
            sock.sendall(b"zINSTREAM\0")
            sock.sendall(payload)

            response = b""
            while True:
                try:
                    chunk = sock.recv(4096)
                except socket.timeout:
                    return ScanResult(verdict=ScanVerdict.FAILED, provider="clamav",
                                      reference="read timeout")
                if not chunk:
                    break
                response += chunk

            if ROOT_REPLY_FOUND in response:
                return ScanResult(verdict=ScanVerdict.INFECTED, provider="clamav",
                                  reference=response.decode("utf-8", errors="replace")[:200])
            if ROOT_REPLY_OK in response:
                return ScanResult(verdict=ScanVerdict.CLEAN, provider="clamav")

            return ScanResult(verdict=ScanVerdict.FAILED, provider="clamav",
                              reference=f"unexpected response: {response[:200]}")
        except socket.timeout:
            return ScanResult(verdict=ScanVerdict.FAILED, provider="clamav",
                              reference="connection timeout")
        except ConnectionRefusedError:
            return ScanResult(verdict=ScanVerdict.FAILED, provider="clamav",
                              reference="connection refused")
        except OSError as exc:
            return ScanResult(verdict=ScanVerdict.FAILED, provider="clamav",
                              reference=str(exc)[:200])
        finally:
            try:
                sock.close()
            except Exception:
                pass
