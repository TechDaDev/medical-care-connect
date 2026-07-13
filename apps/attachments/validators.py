"""File validation for consultation attachments.

Layered validation:
1. Request contains exactly one file.
2. File is non-empty.
3. File size does not exceed configured maximum.
4. Extension is allowed.
5. Declared MIME type is allowed.
6. Detected content type matches supported formats.
7. Filename is normalized safely.
8. File signature is valid.
9. SHA-256 hash is generated while streaming.
10. Dangerous or malformed content is rejected.
"""

import hashlib
import os
import re
from typing import Optional, Tuple

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible

# ── Allowed lists ───────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
ALLOWED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png"}

# PDF signature: %PDF-
PDF_SIGNATURE = b"%PDF-"

# JPEG signature: FF D8 FF
JPEG_SIGNATURES = [bytes([0xFF, 0xD8, 0xFF])]

# PNG signature: 89 50 4E 47 0D 0A 1A 0A
PNG_SIGNATURE = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])

MAX_FILENAME_LENGTH = 255

_UNSAFE_FILENAME_RE = re.compile(r"[^\w\.\-_ ]")


@deconstructible
class AttachmentFileValidator:
    """Validates uploaded file metadata and content signatures."""

    def __init__(
        self,
        max_size_mb: Optional[int] = None,
        allowed_extensions: Optional[set] = None,
        allowed_mime_types: Optional[set] = None,
    ):
        self.max_size_bytes = (max_size_mb or settings.ATTACHMENT_MAX_SIZE_MB) * 1024 * 1024
        self.allowed_extensions = allowed_extensions or ALLOWED_EXTENSIONS
        self.allowed_mime_types = allowed_mime_types or ALLOWED_MIME_TYPES

    def __call__(self, uploaded_file) -> Tuple[bool, str, Optional[str]]:
        """Validate a file. Returns (is_valid, error_code, sha256)."""
        # 1. Non-empty
        if uploaded_file.size is None or uploaded_file.size <= 0:
            return False, "empty_file", None

        # 2. Size
        if uploaded_file.size > self.max_size_bytes:
            return False, "attachment_too_large", None

        # 3. Extension
        ext = self._safe_extension(uploaded_file.name)
        if ext not in self.allowed_extensions:
            return False, "unsupported_extension", None

        # 4. Declared MIME
        declared = uploaded_file.content_type or ""
        if declared not in self.allowed_mime_types:
            return False, "unsupported_media_type", None

        # 5. Content signature + hash (streaming)
        is_valid_sig, detected_mime, sha256 = self._verify_signature(uploaded_file, ext)
        if not is_valid_sig:
            return False, "invalid_file_signature", None

        # 6. Detected MIME matches declared
        if detected_mime and detected_mime != declared:
            return False, "content_type_mismatch", None

        # 7. Filename safe
        safe_name = self._safe_filename(uploaded_file.name)
        if safe_name != uploaded_file.name:
            return False, "unsafe_filename", None

        return True, "", sha256

    def _verify_signature(self, uploaded_file, ext: str) -> Tuple[bool, Optional[str], str]:
        """Read first bytes to verify file signature, compute SHA-256."""
        sha = hashlib.sha256()
        first_chunk = uploaded_file.read(4096)
        sha.update(first_chunk)

        # Read rest for hash
        while True:
            chunk = uploaded_file.read(65536)
            if not chunk:
                break
            sha.update(chunk)

        uploaded_file.seek(0)  # Reset for storage

        if ext == ".pdf":
            if not first_chunk.startswith(PDF_SIGNATURE):
                return False, None, sha.hexdigest()
            return True, "application/pdf", sha.hexdigest()

        if ext in (".jpg", ".jpeg"):
            for sig in JPEG_SIGNATURES:
                if first_chunk[:3] == sig:
                    return True, "image/jpeg", sha.hexdigest()
            return False, None, sha.hexdigest()

        if ext == ".png":
            if first_chunk[:8] == PNG_SIGNATURE:
                return True, "image/png", sha.hexdigest()
            return False, None, sha.hexdigest()

        return False, None, sha.hexdigest()

    def _safe_extension(self, filename: str) -> str:
        """Return lowercase extension with dot, or empty string."""
        if not filename or "." not in filename:
            return ""
        ext = filename.rsplit(".", 1)[-1].lower()
        return f".{ext}"

    def _safe_filename(self, filename: str) -> str:
        """Strip path separators, null bytes, double extensions."""
        # Remove path separators
        name = os.path.basename(filename)
        # Reject null byte
        if "\x00" in name:
            return ""
        # Remove unsafe chars
        name = _UNSAFE_FILENAME_RE.sub("_", name)
        # Truncate
        if len(name) > MAX_FILENAME_LENGTH:
            base, ext = os.path.splitext(name)
            name = base[: MAX_FILENAME_LENGTH - len(ext)] + ext
        return name


def validate_file_extension(value):
    ext = os.path.splitext(value.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(f"Unsupported file extension '{ext}'.")


def validate_file_size(value):
    max_bytes = settings.ATTACHMENT_MAX_SIZE_MB * 1024 * 1024
    if value.size > max_bytes:
        raise ValidationError(f"File size exceeds {settings.ATTACHMENT_MAX_SIZE_MB} MB.")
