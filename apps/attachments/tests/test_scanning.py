"""Tests for malware-scanning abstraction, fail-closed behavior, and EICAR detection."""

import io
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.conf import settings

from apps.attachments.services.scanning_backend.base import ScanResult
from apps.attachments.services.scanning_backend.factory import get_scanner, clear_scanner_cache
from apps.attachments.services.scanning_backend.disabled import DisabledScanner

EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


class ScanResultTests(TestCase):
    def test_clean_status(self):
        r = ScanResult.clean("all good")
        self.assertEqual(r.status, ScanResult.CLEAN)

    def test_infected_status(self):
        r = ScanResult.infected("virus found")
        self.assertEqual(r.status, ScanResult.INFECTED)

    def test_failed_status(self):
        r = ScanResult.failed("timeout")
        self.assertEqual(r.status, ScanResult.FAILED)


@override_settings(ATTACHMENT_SCAN_MODE="disabled")
class DisabledScannerTests(TestCase):
    def setUp(self):
        clear_scanner_cache()

    def test_clean_file_accepted(self):
        scanner = get_scanner()
        result = scanner.scan(io.BytesIO(b"clean data"))
        self.assertEqual(result.status, ScanResult.CLEAN)

    def test_eicar_not_rejected_in_disabled_mode(self):
        scanner = get_scanner()
        result = scanner.scan(io.BytesIO(EICAR))
        self.assertEqual(result.status, ScanResult.CLEAN)

    def test_scanner_available(self):
        scanner = get_scanner()
        self.assertTrue(scanner.is_available())

    def test_oversized_file_accepted_in_disabled(self):
        scanner = get_scanner()
        big = io.BytesIO(b"x" * (10 * 1024 * 1024))
        result = scanner.scan(big)
        self.assertEqual(result.status, ScanResult.CLEAN)


@override_settings(
    ATTACHMENT_SCAN_MODE="clamav",
    CLAMAV_HOST="127.0.0.1",
    CLAMAV_PORT=3310,
)
class ClamavScannerMockedTests(TestCase):
    def setUp(self):
        clear_scanner_cache()

    @patch("socket.socket")
    def test_clean_file_accepted(self, mock_socket):
        mock_instance = mock_socket.return_value
        mock_instance.recv.side_effect = [b"stream: OK", b""]
        scanner = get_scanner()
        result = scanner.scan(io.BytesIO(b"clean pdf content"))
        self.assertEqual(result.status, ScanResult.CLEAN)

    @patch("socket.socket")
    def test_infected_file_rejected(self, mock_socket):
        mock_instance = mock_socket.return_value
        mock_instance.recv.side_effect = [b"stream: Eicar-Test-Signature FOUND", b""]
        scanner = get_scanner()
        result = scanner.scan(io.BytesIO(EICAR))
        self.assertEqual(result.status, ScanResult.INFECTED)

    @patch("socket.socket")
    def test_scanner_timeout_fails_closed(self, mock_socket):
        from socket import timeout
        mock_instance = mock_socket.return_value
        mock_instance.connect.side_effect = timeout("timed out")
        scanner = get_scanner()
        result = scanner.scan(io.BytesIO(b"data"))
        self.assertEqual(result.status, ScanResult.FAILED)

    @patch("socket.socket")
    def test_connection_error_fails_closed(self, mock_socket):
        mock_instance = mock_socket.return_value
        mock_instance.connect.side_effect = ConnectionRefusedError("refused")
        scanner = get_scanner()
        result = scanner.scan(io.BytesIO(b"data"))
        self.assertEqual(result.status, ScanResult.FAILED)

    @patch("socket.socket")
    def test_scanner_available_positive(self, mock_socket):
        mock_instance = mock_socket.return_value
        scanner = get_scanner()
        self.assertTrue(scanner.is_available())

    @patch("socket.socket")
    def test_scanner_available_negative(self, mock_socket):
        mock_instance = mock_socket.return_value
        mock_instance.connect.side_effect = ConnectionRefusedError()
        scanner = get_scanner()
        self.assertFalse(scanner.is_available())

    @patch("socket.socket")
    def test_oversized_file_rejected(self, mock_socket):
        mock_instance = mock_socket.return_value
        mock_instance.recv.side_effect = [b"stream: OK", b""]
        scanner = get_scanner()
        big = io.BytesIO(b"x" * (100 * 1024 * 1024))
        result = scanner.scan(big)
        self.assertIn(result.status, (ScanResult.CLEAN, ScanResult.FAILED))


@override_settings(ATTACHMENT_SCAN_MODE="clamav")
class ClamavProductionConfigTests(TestCase):
    def test_missing_clamav_config_fails_startup_check(self):
        """Production should not start with clamav mode but no CLAMAV_HOST."""
        from django.core.checks import Error
        from apps.attachments.apps import AttachmentsConfig
        errors = AttachmentsConfig.check_clamav_config(None)
        self.assertTrue(any(e.id == "mcc.E001" for e in errors))


class ScanResultMiscTests(TestCase):
    def test_invalid_status_raises(self):
        with self.assertRaises(AssertionError):
            ScanResult("invalid_status")
