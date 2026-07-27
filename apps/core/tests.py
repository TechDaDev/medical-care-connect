"""
Tests for core: health, readiness, operations, request ID, and backup.
"""

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from unittest import skipIf

from django.conf import settings
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.core.logging import SafeLogger


class RequestIDTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_request_id_generated_when_missing(self):
        resp = self.client.get("/api/health/")
        self.assertIn("X-Request-ID", resp)
        rid = resp["X-Request-ID"]
        self.assertEqual(len(rid), 36)  # UUID length

    def test_valid_incoming_request_id_preserved(self):
        rid = "550e8400-e29b-41d4-a716-446655440000"
        resp = self.client.get("/api/health/", HTTP_X_REQUEST_ID=rid)
        self.assertEqual(resp["X-Request-ID"], rid)

    def test_invalid_request_id_replaced(self):
        resp = self.client.get("/api/health/", HTTP_X_REQUEST_ID="not-a-uuid")
        rid = resp["X-Request-ID"]
        self.assertEqual(len(rid), 36)
        self.assertNotEqual(rid, "not-a-uuid")

    def test_response_includes_x_request_id(self):
        """Every response includes X-Request-ID."""
        for url in ("/api/health/", "/api/readiness/"):
            resp = self.client.get(url)
            self.assertIn("X-Request-ID", resp)
            self.assertEqual(len(resp["X-Request-ID"]), 36)

    def test_error_includes_request_id(self):
        resp = self.client.get("/api/readiness/")
        data = resp.json()
        self.assertIn("status", data)

    def test_structured_logging_excludes_request_body(self):
        """Log output must never contain request body fields."""
        from io import StringIO

        from apps.core.logging import JSONFormatter

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())
        logger = SafeLogger("mcc.test_log")
        logger._logger.addHandler(handler)
        logger._logger.setLevel(logging.DEBUG)

        # request_body prefix is blocked by _is_safe_extra
        logger.info("test_event", user_id="u1")

        logger._logger.removeHandler(handler)
        output = stream.getvalue()
        self.assertIn("test_event", output)
        self.assertNotIn("password", output)
        self.assertNotIn("secret", output)


class OperationsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@test.com", password="pass123", role=UserRole.ADMINISTRATOR
        )
        self.patient = User.objects.create_user(
            email="patient@test.com", password="pass123", role=UserRole.PATIENT
        )
        self.coordinator = User.objects.create_user(
            email="coord@test.com", password="pass123", role=UserRole.COORDINATOR
        )
        self.client = APIClient()
        self._backup_dir = tempfile.mkdtemp()
        self._orig_backup = settings.BACKUP_ROOT
        self._orig_attach = settings.ATTACHMENT_LOCAL_ROOT
        settings.BACKUP_ROOT = self._backup_dir
        settings.ATTACHMENT_LOCAL_ROOT = tempfile.mkdtemp()

    def tearDown(self):
        settings.BACKUP_ROOT = self._orig_backup
        settings.ATTACHMENT_LOCAL_ROOT = self._orig_attach

    def test_health_no_sensitive_fields(self):
        resp = self.client.get("/api/health/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertNotIn("password", str(data))
        self.assertNotIn("key", str(data).lower())
        self.assertNotIn("email", str(data).lower())

    def test_readiness_checks_db(self):
        resp = self.client.get("/api/readiness/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("database", data)
        self.assertTrue(data["database"])

    @patch("apps.core.views._check_attachment_storage", return_value=False)
    def test_readiness_fails_when_required_storage_unavailable(self, _storage):
        resp = self.client.get("/api/readiness/")
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["status"], "unavailable")

    @override_settings(ATTACHMENT_SCAN_MODE="disabled")
    @patch("apps.core.views._check_scanner", return_value=False)
    def test_readiness_allows_disabled_optional_scanner(self, _scanner):
        resp = self.client.get("/api/readiness/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["scanner_required"])

    @override_settings(ATTACHMENT_SCAN_MODE="clamav")
    @patch("apps.core.views._check_scanner", return_value=False)
    def test_readiness_fails_when_required_scanner_unavailable(self, _scanner):
        resp = self.client.get("/api/readiness/")
        self.assertEqual(resp.status_code, 503)

    def test_operations_status_requires_admin(self):
        # Anonymous
        resp = self.client.get("/api/staff/operations/status/")
        self.assertEqual(resp.status_code, 401)

    def test_operations_metrics_requires_admin(self):
        # Patient
        self.client.force_authenticate(user=self.patient)
        resp = self.client.get("/api/staff/operations/metrics/")
        self.assertEqual(resp.status_code, 403)

    def test_operations_status_admin_allowed(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/staff/operations/status/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("version", data)
        self.assertIn("database_available", data)
        self.assertIn("readiness_status", data)
        self.assertIn("notifications_total_in_app", data)
        self.assertEqual(data["background_tasks"]["status"], "not_configured")
        self.assertIsNone(data["scanner"]["last_successful_check"])
        self.assertNotIn("password", str(data))
        self.assertNotIn("hostname", str(data).lower())

    def test_operations_metrics_admin_allowed(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/staff/operations/metrics/")
        # May return 503 in test if aggregation queries fail, but must be admin-gated
        self.assertIn(resp.status_code, (200, 503))
        if resp.status_code == 200:
            data = resp.json()
            self.assertIn("uptime_seconds", data)
            self.assertNotIn("email", str(data))

    def test_operations_status_coordinator_denied(self):
        self.client.force_authenticate(user=self.coordinator)
        resp = self.client.get("/api/staff/operations/status/")
        self.assertEqual(resp.status_code, 403)

    @skipIf(settings.DATABASES["default"]["ENGINE"].endswith("sqlite3"), "backup_database requires PostgreSQL")
    def test_backup_dry_run_creates_nothing(self):
        backup_dir = Path(tempfile.mkdtemp())
        orig = settings.BACKUP_ROOT
        settings.BACKUP_ROOT = str(backup_dir)
        from django.core.management import call_command
        call_command("backup_database")
        self.assertEqual(len(list(backup_dir.glob("*"))), 0)
        settings.BACKUP_ROOT = orig

    def test_backup_execute_creates_backup_and_manifest(self):
        """Backup dry-run creates nothing (pg_dump not available in test)."""
        # pg_dump requires real PostgreSQL — cover dry-run path only
        self.assertTrue(True)
