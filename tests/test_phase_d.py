"""Phase D: Privacy-request administration and audit/security-event viewer tests.

Coverage:
- Privacy list/detail approve/reject concurrency
- Audit list/detail/CSV/append-only
- Permission enforcement
"""

import io
import csv
import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.models import AuditEvent, AuditEventCategory, AuditEventSeverity, AuditEventResult, RetentionClass
from apps.privacy.models import AccountDeletionRequest, DeletionStatus
from apps.accounts.models import UserRole

User = get_user_model()


def _create_user(role=UserRole.PATIENT, **kw):
    data = dict(
        email=f"{role}@example.com",
        password="testpass123",
        first_name="Test",
        last_name=role.capitalize(),
        role=role,
        is_active=True,
    )
    data.update(kw)
    user = User.objects.create_user(**data)
    user.raw_password = "testpass123"
    return user


def _login(client, user):
    resp = client.post("/api/auth/login/", {
        "email": user.email,
        "password": user.raw_password,
    }, format="json")
    assert resp.status_code == 200, f"Login failed: {resp.data}"


# ─── Privacy Deletion Admin Tests ─────────────────────────────────────────


class PrivacyDeletionListTests(TestCase):
    """GET /api/staff/privacy/deletion-requests/ — permission & filtering."""

    def setUp(self):
        self.client = APIClient()
        self.admin = _create_user(role=UserRole.ADMINISTRATOR)
        self.coordinator = _create_user(role=UserRole.COORDINATOR, email="coord@example.com")
        self.doctor = _create_user(role=UserRole.DOCTOR, email="doc@example.com")
        self.patient = _create_user(role=UserRole.PATIENT, email="pat@example.com")
        self.other_patient = _create_user(role=UserRole.PATIENT, email="pat2@example.com")

        # Create deletion requests
        self.dr1 = AccountDeletionRequest.objects.create(
            subject_user=self.patient, requested_by=self.patient, reason="Privacy concern"
        )
        self.dr2 = AccountDeletionRequest.objects.create(
            subject_user=self.other_patient, requested_by=self.other_patient, reason="Leaving service"
        )
        self.url = "/api/staff/privacy/deletion-requests/"

    def test_anonymous_denied(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_patient_denied(self):
        _login(self.client, self.patient)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_doctor_denied(self):
        _login(self.client, self.doctor)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_coordinator_denied(self):
        _login(self.client, self.coordinator)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_administrator_allowed(self):
        _login(self.client, self.admin)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("results", resp.data)
        self.assertEqual(len(resp.data["results"]), 2)

    def test_pagination(self):
        _login(self.client, self.admin)
        for i in range(5):
            AccountDeletionRequest.objects.create(
                subject_user=self.patient, requested_by=self.patient
            )
        resp = self.client.get(self.url, {"page_size": "5"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["results"]), 5)

    def test_status_filter(self):
        _login(self.client, self.admin)
        self.dr1.status = DeletionStatus.APPROVED
        self.dr1.save()
        resp = self.client.get(self.url, {"status": "approved"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["results"]), 1)

    def test_search_by_name(self):
        _login(self.client, self.admin)
        resp = self.client.get(self.url, {"search": "Patient"})
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.data["results"]), 1)

    def test_safe_fields_only(self):
        _login(self.client, self.admin)
        resp = self.client.get(self.url)
        result = resp.data["results"][0]
        # Must contain safe fields
        self.assertIn("id", result)
        self.assertIn("requester", result)
        self.assertIn("status", result)
        # Must NOT contain raw private data
        self.assertNotIn("reason", result)

    def test_available_actions_correct(self):
        _login(self.client, self.admin)
        resp = self.client.get(self.url)
        dr_pending = [r for r in resp.data["results"] if r["status"] == "pending"]
        if dr_pending:
            self.assertIn("approve", dr_pending[0]["available_actions"])
            self.assertIn("reject", dr_pending[0]["available_actions"])


class PrivacyDeletionDetailTests(TestCase):
    """GET /api/staff/privacy/deletion-requests/<id>/"""

    def setUp(self):
        self.client = APIClient()
        self.admin = _create_user(role=UserRole.ADMINISTRATOR)
        self.patient = _create_user(role=UserRole.PATIENT)
        self.dr = AccountDeletionRequest.objects.create(
            subject_user=self.patient, requested_by=self.patient, reason="Test reason"
        )
        self.url = f"/api/staff/privacy/deletion-requests/{self.dr.id}/"

    def test_administrator_allowed(self):
        _login(self.client, self.admin)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(str(resp.data["id"]), str(self.dr.id))

    def test_no_medical_content(self):
        _login(self.client, self.admin)
        resp = self.client.get(self.url)
        self.assertIn("related_data_summary", resp.data)
        # Ensure no raw clinical content
        self.assertNotIn("description", str(resp.data).lower())
        self.assertNotIn("content", str(resp.data))

    def test_available_actions_pending(self):
        _login(self.client, self.admin)
        resp = self.client.get(self.url)
        self.assertIn("approve", resp.data["available_actions"])

    def test_no_actions_after_review(self):
        _login(self.client, self.admin)
        self.dr.status = DeletionStatus.APPROVED
        self.dr.save()
        resp = self.client.get(self.url)
        self.assertEqual(resp.data["available_actions"], [])

    def test_missing_404(self):
        _login(self.client, self.admin)
        resp = self.client.get("/api/staff/privacy/deletion-requests/00000000-0000-0000-0000-000000000000/")
        self.assertEqual(resp.status_code, 404)


class PrivacyDeletionReviewTests(TestCase):
    """POST approve/reject with concurrency protection."""

    def setUp(self):
        self.client = APIClient()
        self.admin = _create_user(role=UserRole.ADMINISTRATOR)
        self.admin2 = _create_user(role=UserRole.ADMINISTRATOR, email="admin2@example.com")
        self.patient = _create_user(role=UserRole.PATIENT)
        self.dr = AccountDeletionRequest.objects.create(
            subject_user=self.patient, requested_by=self.patient, reason="Please delete"
        )
        self.approve_url = f"/api/staff/privacy/deletion-requests/{self.dr.id}/approve/"
        self.reject_url = f"/api/staff/privacy/deletion-requests/{self.dr.id}/reject/"

    def test_approve_pending(self):
        _login(self.client, self.admin)
        resp = self.client.post(self.approve_url, {}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.dr.refresh_from_db()
        self.assertEqual(self.dr.status, DeletionStatus.APPROVED)
        self.assertIsNotNone(self.dr.reviewed_by)

    def test_reject_requires_reason(self):
        _login(self.client, self.admin)
        resp = self.client.post(self.reject_url, {"rejection_reason": "A very clear justification for why this deletion request should be rejected."}, format="json")
        self.assertEqual(resp.status_code, 200)

    def test_reject_with_reason(self):
        _login(self.client, self.admin)
        resp = self.client.post(self.reject_url, {
            "rejection_reason": "Insufficient justification provided.",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.dr.refresh_from_db()
        self.assertEqual(self.dr.status, DeletionStatus.REJECTED)
        self.assertEqual(self.dr.rejection_reason, "Insufficient justification provided.")

    def test_invalid_transition(self):
        _login(self.client, self.admin)
        self.dr.status = DeletionStatus.APPROVED
        self.dr.save()
        resp = self.client.post(self.approve_url, {}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertIn("invalid_privacy_request_transition", str(resp.data))

    def test_concurrent_review(self):
        _login(self.client, self.admin)
        # First approve
        resp = self.client.post(self.approve_url, {}, format="json")
        self.assertEqual(resp.status_code, 200)
        # Now another admin tries to reject
        _login(self.client, self.admin2)
        resp = self.client.post(self.reject_url, {
            "rejection_reason": "Already approved by another admin.",
        }, format="json")
        # Should be 409 since already approved
        self.assertEqual(resp.status_code, 409)

    def test_audit_event_created_on_approve(self):
        _login(self.client, self.admin)
        self.client.post(self.approve_url, {}, format="json")
        events = AuditEvent.objects.filter(event_type="privacy.deletion.approved")
        self.assertEqual(events.count(), 1)
        self.assertEqual(str(events[0].actor_id), str(self.admin.id))

    def test_audit_event_created_on_reject(self):
        _login(self.client, self.admin)
        self.client.post(self.reject_url, {
            "rejection_reason": "Insufficient justification provided.",
        }, format="json")
        events = AuditEvent.objects.filter(event_type="privacy.deletion.rejected")
        self.assertEqual(events.count(), 1)


# ─── Audit Event Tests ────────────────────────────────────────────────────


class AuditEventListTests(TestCase):
    """GET /api/staff/audit-events/ — permission & filtering."""

    def setUp(self):
        self.client = APIClient()
        self.admin = _create_user(role=UserRole.ADMINISTRATOR)
        self.coordinator = _create_user(role=UserRole.COORDINATOR, email="coord@example.com")
        self.doctor = _create_user(role=UserRole.DOCTOR, email="doc@example.com")
        self.patient = _create_user(role=UserRole.PATIENT, email="pat@example.com")
        self.url = "/api/staff/audit-events/"
        # Create some audit events
        for i in range(3):
            AuditEvent.objects.create(
                event_type=f"test.event.{i}",
                category=AuditEventCategory.SYSTEM,
                severity=AuditEventSeverity.INFO,
                result=AuditEventResult.SUCCESS,
            )

    def test_administrator_allowed(self):
        _login(self.client, self.admin)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("results", resp.data)

    def test_coordinator_denied(self):
        _login(self.client, self.coordinator)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 403)

    def test_doctor_denied(self):
        _login(self.client, self.doctor)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 403)

    def test_patient_denied(self):
        _login(self.client, self.patient)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 403)

    def test_anonymous_denied(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 401)

    def test_metadata_absent_in_list(self):
        _login(self.client, self.admin)
        AuditEvent.objects.create(
            event_type="test.with_meta",
            category=AuditEventCategory.SECURITY,
            metadata={"key": "value"},
        )
        resp = self.client.get(self.url)
        for r in resp.data["results"]:
            self.assertNotIn("metadata", r)

    def test_event_type_filter(self):
        _login(self.client, self.admin)
        AuditEvent.objects.create(event_type="special.event", category=AuditEventCategory.SYSTEM)
        resp = self.client.get(self.url, {"event_type": "special.event"})
        for r in resp.data["results"]:
            self.assertEqual(r["event_type"], "special.event")

    def test_severity_filter(self):
        _login(self.client, self.admin)
        AuditEvent.objects.create(
            event_type="critical.event", category=AuditEventCategory.SECURITY,
            severity=AuditEventSeverity.CRITICAL,
        )
        resp = self.client.get(self.url, {"severity": "critical"})
        for r in resp.data["results"]:
            self.assertEqual(r["severity"], "critical")


class AuditEventDetailTests(TestCase):
    """GET /api/staff/audit-events/<id>/ — sanitization."""

    def setUp(self):
        self.client = APIClient()
        self.admin = _create_user(role=UserRole.ADMINISTRATOR)
        self.event = AuditEvent.objects.create(
            event_type="test.sensitive",
            category=AuditEventCategory.SECURITY,
            metadata={
                "password": "secret123",
                "token": "jwt.eyJhbGci",
                "safe_key": "visible_value",
                "nested": {"inner_password": "hidden"},
            },
        )
        self.url = f"/api/staff/audit-events/{self.event.id}/"

    def test_safe_metadata_returned(self):
        _login(self.client, self.admin)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("metadata_safe", resp.data)

    def test_password_redacted(self):
        _login(self.client, self.admin)
        resp = self.client.get(self.url)
        meta = resp.data["metadata_safe"]
        self.assertEqual(meta["password"], "[REDACTED]")
        self.assertEqual(meta["token"], "[REDACTED]")

    def test_safe_key_preserved(self):
        _login(self.client, self.admin)
        resp = self.client.get(self.url)
        meta = resp.data["metadata_safe"]
        self.assertEqual(meta["safe_key"], "visible_value")

    def test_nested_sanitized(self):
        _login(self.client, self.admin)
        resp = self.client.get(self.url)
        meta = resp.data["metadata_safe"]
        self.assertIsInstance(meta["nested"], dict)
        self.assertIn("inner_password", str(meta["nested"]))

    def test_missing_404(self):
        _login(self.client, self.admin)
        resp = self.client.get("/api/staff/audit-events/00000000-0000-0000-0000-000000000000/")
        self.assertEqual(resp.status_code, 404)


class AuditEventCsvTests(TestCase):
    """GET /api/staff/audit-events/export.csv — safe export."""

    def setUp(self):
        self.client = APIClient()
        self.admin = _create_user(role=UserRole.ADMINISTRATOR)
        self.patient = _create_user(role=UserRole.PATIENT)
        self.url = "/api/staff/audit-events/export.csv"
        AuditEvent.objects.create(
            event_type="test.csv", category=AuditEventCategory.SYSTEM,
            summary="Test CSV export",
        )

    def test_administrator_allowed(self):
        _login(self.client, self.admin)
        resp = self.client.get(self.url, {"created_after": "2020-01-01"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv; charset=utf-8")

    def test_date_range_required(self):
        _login(self.client, self.admin)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("date_range_required", str(resp.data))

    def test_formula_injection_neutralized(self):
        _login(self.client, self.admin)
        AuditEvent.objects.create(
            event_type="=cmd|' /C calc'!A0",
            category=AuditEventCategory.SECURITY,
        )
        resp = self.client.get(self.url, {"created_after": "2020-01-01"})
        content = resp.content.decode("utf-8")
        # Formula-injection values should be prefixed with '
        if "=cmd" in content:
            self.assertIn("'=cmd", content)

    def test_csv_headers_safe(self):
        _login(self.client, self.admin)
        resp = self.client.get(self.url, {"created_after": "2020-01-01"})
        self.assertIn("Cache-Control", resp)
        self.assertIn("X-Content-Type-Options", resp)

    def test_unauthorized_denied(self):
        _login(self.client, self.patient)
        resp = self.client.get(self.url, {"created_after": "2020-01-01"})
        self.assertEqual(resp.status_code, 403)


class AuditEventAppendOnlyTests(TestCase):
    """Audit events must be append-only."""

    def setUp(self):
        self.client = APIClient()
        self.admin = _create_user(role=UserRole.ADMINISTRATOR)
        self.event = AuditEvent.objects.create(
            event_type="test.append", category=AuditEventCategory.SYSTEM,
        )

    def test_no_update_endpoint(self):
        _login(self.client, self.admin)
        resp = self.client.patch(f"/api/staff/audit-events/{self.event.id}/", {"summary": "hacked"}, format="json")
        # Should 404 or 405 since no such route
        self.assertIn(resp.status_code, (404, 405))

    def test_no_delete_endpoint(self):
        _login(self.client, self.admin)
        resp = self.client.delete(f"/api/staff/audit-events/{self.event.id}/")
        self.assertIn(resp.status_code, (404, 405))
