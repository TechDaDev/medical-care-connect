"""ClamAV scanner using clamd INSTREAM protocol over TCP."""

import socket
import struct
import io
import time
from typing import BinaryIO

from django.conf import settings

from .base import BaseScanner, ScanResult


# clamd INSTREAM constants
_CHUNK_SIZE = 8192
_ROOT_REPLY_OK = b"stream: OK"
_ROOT_REPLY_FOUND = b"FOUND"


def _build_instream_payload(stream: BinaryIO, max_bytes: int = 0) -> bytes:
    """Read the stream into an INSTREAM payload (size-prefixed chunks)."""
    chunks = []
    while True:
        data = stream.read(_CHUNK_SIZE)
        if not data:
            break
        if max_bytes and sum(len(c) for c in chunks) + len(data) > max_bytes:
            data = data[: max_bytes - sum(len(c) for c in chunks)]
            if not data:
                break
        chunks.append(struct.pack("!I", len(data)))
        chunks.append(data)

    chunks.append(struct.pack("!I", 0))  # zero-length terminator
    return b"".join(chunks)


class ClamavScanner(BaseScanner):
    """Scans via clamd INSTREAM over TCP.  Fail-closed on connection errors."""

    def __init__(self):
        self._host = settings.CLAMAV_HOST
        self._port = settings.CLAMAV_PORT
        self._connect_timeout = getattr(settings, "CLAMAV_CONNECT_TIMEOUT", 5)
        self._read_timeout = getattr(settings, "CLAMAV_READ_TIMEOUT", 60)
        self._max_stream = getattr(settings, "CLAMAV_MAX_STREAM_BYTES", 0) or 0
        self._last_check = 0.0
        self._available = False

    def scan(self, file: BinaryIO) -> ScanResult:
        try:
            payload = _build_instream_payload(file, self._max_stream)
        except Exception as exc:
            return ScanResult.failed(f"Stream build error: {exc}")

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self._connect_timeout)

        try:
            sock.connect((self._host, self._port))
            sock.settimeout(self._read_timeout)

            # Send INSTREAM command
            sock.sendall(b"zINSTREAM\0")
            sock.sendall(payload)

            # Read response
            response = b""
            while True:
                try:
                    chunk = sock.recv(4096)
                except socket.timeout:
                    return ScanResult.failed("ClamAV read timeout")
                if not chunk:
                    break
                response += chunk

            text = response.strip().decode("utf-8", errors="replace")

            if _ROOT_REPLY_FOUND in response:
                return ScanResult.infected(text)
            if _ROOT_REPLY_OK in response:
                return ScanResult.clean(text)

            return ScanResult.failed(f"Unexpected ClamAV response: {text[:200]}")

        except socket.timeout:
            return ScanResult.failed("ClamAV connection timeout")
        except ConnectionRefusedError:
            return ScanResult.failed("ClamAV connection refused")
        except OSError as exc:
            return ScanResult.failed(f"ClamAV socket error: {exc}")
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def is_available(self) -> bool:
        # Cache availability for 30 s to avoid hammering
        now = time.time()
        if now - self._last_check < 30:
            return self._available

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self._connect_timeout)
        try:
            sock.connect((self._host, self._port))
            self._available = True
        except Exception:
            self._available = False
        finally:
            try:
                sock.close()
            except Exception:
                pass
        self._last_check = now
        return self._available
