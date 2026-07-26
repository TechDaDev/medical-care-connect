from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.attachments.choices import AttachmentStatus, ScanStatus
from apps.attachments.models import AttachmentAuditEvent, ConsultationAttachment
from apps.attachments.services.scanning import ScanResult, ScanVerdict
from apps.consultations.models import Consultation, ConsultationStatus
from apps.core.models import AuditEvent
from apps.doctors.models import DoctorProfile
from apps.patients.models import PatientProfile
from apps.specialties.models import Specialty


def create_user(role: str, suffix: str) -> User:
    return User.objects.create_user(
        email=f"{role}-{suffix}@example.com",
        password="testpass123",
        role=role,
        first_name="Phase",
        last_name="E",
    )


class PhaseEBase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = create_user(UserRole.ADMINISTRATOR, "admin")
        self.coordinator = create_user(UserRole.COORDINATOR, "coordinator")
        self.doctor_user = create_user(UserRole.DOCTOR, "doctor")
        self.patient_user = create_user(UserRole.PATIENT, "patient")

    def authenticate(self, user):
        self.client.force_authenticate(user=user)


class SpecialtyAdminTests(PhaseEBase):
    url = "/api/staff/specialties/"

    def setUp(self):
        super().setUp()
        self.specialty = Specialty.objects.create(
            name="Phase E Cardiology",
            name_en="Phase E Cardiology",
            name_ar="قلب المرحلة هـ",
            name_ckb="دڵی قۆناغی E",
            slug="phase-e-cardiology",
            display_order=50,
        )

    def test_permissions(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)
        for user in (self.coordinator, self.doctor_user, self.patient_user):
            self.authenticate(user)
            self.assertEqual(self.client.get(self.url).status_code, 403)
        self.authenticate(self.admin)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_create_requires_translations_and_returns_authoritative_detail(self):
        self.authenticate(self.admin)
        response = self.client.post(
            self.url,
            {
                "code": "  phase-e-neuro  ",
                "name_en": "  Phase E Neurology  ",
                "name_ar": "الأعصاب",
                "name_ckb": "دەمار",
                "description": "Synthetic",
                "display_order": 70,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["code"], "phase-e-neuro")
        self.assertEqual(response.data["name_en"], "Phase E Neurology")
        self.assertTrue(
            AuditEvent.objects.filter(event_type="specialty_created").exists()
        )

        missing = self.client.post(
            self.url,
            {
                "code": "missing-translation",
                "name_en": "Missing",
                "name_ar": "مفقود",
                "display_order": 80,
            },
            format="json",
        )
        self.assertEqual(missing.status_code, 400)
        self.assertIn("name_ckb", missing.data["fields"])

    def test_duplicate_code_denied(self):
        self.authenticate(self.admin)
        response = self.client.post(
            self.url,
            {
                "code": "PHASE-E-CARDIOLOGY",
                "name_en": "Other English",
                "name_ar": "اسم آخر",
                "name_ckb": "ناوی تر",
                "display_order": 1,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("code", response.data)

    def test_update_concurrency_conflict(self):
        self.authenticate(self.admin)
        missing = self.client.patch(
            f"{self.url}{self.specialty.id}/",
            {"name_en": "Changed without version"},
            format="json",
        )
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.data["code"], "expected_updated_at_required")
        response = self.client.patch(
            f"{self.url}{self.specialty.id}/",
            {
                "name_en": "Changed",
                "expected_updated_at": "2000-01-01T00:00:00Z",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.specialty.refresh_from_db()
        self.assertEqual(self.specialty.name_en, "Phase E Cardiology")

    def test_deactivation_blocks_open_consultation_and_preserves_references(self):
        patient = PatientProfile.objects.create(user=self.patient_user)
        doctor = DoctorProfile.objects.create(
            user=self.doctor_user,
            specialty=self.specialty,
            license_number="PHASE-E-LIC",
            is_approved=True,
            approval_status=DoctorProfile.ApprovalStatus.APPROVED,
        )
        consultation = Consultation.objects.create(
            patient=patient,
            doctor=doctor,
            specialty=self.specialty,
            status=ConsultationStatus.SUBMITTED,
        )
        self.authenticate(self.admin)
        response = self.client.post(
            f"{self.url}{self.specialty.id}/deactivate/", {}, format="json"
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "specialty_in_use")
        consultation.refresh_from_db()
        self.assertEqual(consultation.specialty_id, self.specialty.id)

        consultation.status = ConsultationStatus.COMPLETED
        consultation.save(update_fields=["status"])
        response = self.client.post(
            f"{self.url}{self.specialty.id}/deactivate/", {}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.specialty.refresh_from_db()
        self.assertFalse(self.specialty.is_active)
        self.assertEqual(
            self.client.get("/api/specialties/").json(),
            [
                item
                for item in self.client.get("/api/specialties/").json()
                if item["id"] != str(self.specialty.id)
            ],
        )
        detail = self.client.get(f"/api/specialties/{self.specialty.id}/")
        self.assertEqual(detail.status_code, 200)

    def test_reorder_rejects_missing_and_canonicalizes_duplicate_order(self):
        self.authenticate(self.admin)
        missing = self.client.post(
            f"{self.url}reorder/",
            {"items": [{"id": str(self.specialty.id), "display_order": 1}]},
            format="json",
        )
        self.assertEqual(missing.status_code, 400)

        items = [
            {"id": str(item.id), "display_order": 1}
            for item in Specialty.objects.order_by("-id")
        ]
        response = self.client.post(
            f"{self.url}reorder/", {"items": items}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            [item["display_order"] for item in response.data],
            list(range(1, len(items) + 1)),
        )


class AttachmentAdminTests(PhaseEBase):
    url = "/api/staff/attachments/"

    def setUp(self):
        super().setUp()
        self.specialty = Specialty.objects.create(
            name="Attachment Specialty", slug="attachment-specialty"
        )
        patient = PatientProfile.objects.create(user=self.patient_user)
        doctor = DoctorProfile.objects.create(
            user=self.doctor_user,
            specialty=self.specialty,
            license_number="ATTACH-LIC",
            is_approved=True,
        )
        self.consultation = Consultation.objects.create(
            patient=patient,
            doctor=doctor,
            specialty=self.specialty,
            status=ConsultationStatus.COMPLETED,
        )
        self.attachment = ConsultationAttachment.objects.create(
            consultation=self.consultation,
            uploaded_by=self.patient_user,
            storage_provider="local",
            storage_key="opaque/phase-e",
            original_filename="private-original.pdf",
            safe_display_name="attachment.pdf",
            extension=".pdf",
            detected_mime_type="application/pdf",
            size_bytes=100,
            status=AttachmentStatus.QUARANTINED,
            scan_status=ScanStatus.FAILED,
        )

    def test_permissions(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)
        for user in (self.coordinator, self.doctor_user, self.patient_user):
            self.authenticate(user)
            self.assertEqual(self.client.get(self.url).status_code, 403)
        self.authenticate(self.admin)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_list_and_detail_are_safe(self):
        self.authenticate(self.admin)
        response = self.client.get(self.url, {"status": "quarantined"})
        self.assertEqual(response.status_code, 200)
        item = response.data["results"][0]
        self.assertEqual(item["owner_type"], "consultation")
        self.assertEqual(item["filename"], "attachment.pdf")
        serialized = str(item).lower()
        self.assertNotIn("storage_key", serialized)
        self.assertNotIn("opaque/phase-e", serialized)
        self.assertNotIn("description", serialized)

        detail = self.client.get(f"{self.url}{self.attachment.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertNotIn("storage_key", str(detail.data).lower())
        self.assertTrue(
            AttachmentAuditEvent.objects.filter(
                attachment=self.attachment, event_type="admin_viewed"
            ).exists()
        )
        unsupported_owner = self.client.get(self.url, {"owner_type": "message"})
        self.assertEqual(unsupported_owner.status_code, 200)
        self.assertEqual(unsupported_owner.data["count"], 0)

    @override_settings(ATTACHMENT_SCAN_MODE="disabled")
    def test_rescan_reports_unsupported_scanner(self):
        self.authenticate(self.admin)
        response = self.client.post(
            f"{self.url}{self.attachment.id}/rescan/",
            {"reason": "Security review", "expected_status": "quarantined"},
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "scanner_unavailable")

    @override_settings(
        ATTACHMENT_SCAN_MODE="clamav",
        CLAMAV_HOST="127.0.0.1",
        CLAMAV_PORT=3310,
    )
    @patch("apps.staff.phase_e_views.ClamavAttachmentScanner.scan")
    def test_clean_rescan_requires_explicit_release(self, scan):
        scan.return_value = ScanResult(ScanVerdict.CLEAN, provider="clamav")
        self.authenticate(self.admin)
        response = self.client.post(
            f"{self.url}{self.attachment.id}/rescan/",
            {"reason": "Recheck quarantine", "expected_status": "quarantined"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "quarantined")
        self.assertIn("release", response.data["available_actions"])

        released = self.client.post(
            f"{self.url}{self.attachment.id}/release/",
            {"reason": "Verified clean result", "expected_status": "quarantined"},
            format="json",
        )
        self.assertEqual(released.status_code, 200, released.data)
        self.assertEqual(released.data["status"], "available")

    @override_settings(
        ATTACHMENT_SCAN_MODE="clamav",
        CLAMAV_HOST="127.0.0.1",
        CLAMAV_PORT=3310,
    )
    @patch("apps.staff.phase_e_views.ClamavAttachmentScanner.scan")
    def test_unsafe_rescan_records_quarantine_transition(self, scan):
        scan.return_value = ScanResult(ScanVerdict.INFECTED, provider="clamav")
        self.attachment.status = AttachmentStatus.AVAILABLE
        self.attachment.scan_status = ScanStatus.CLEAN
        self.attachment.save(update_fields=["status", "scan_status", "updated_at"])
        self.authenticate(self.admin)
        response = self.client.post(
            f"{self.url}{self.attachment.id}/rescan/",
            {"reason": "Security recheck", "expected_status": "available"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "quarantined")
        self.assertTrue(
            AttachmentAuditEvent.objects.filter(
                attachment=self.attachment, event_type="quarantined"
            ).exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(event_type="attachment_quarantined").exists()
        )

    @override_settings(
        ATTACHMENT_SCAN_MODE="clamav",
        CLAMAV_HOST="127.0.0.1",
        CLAMAV_PORT=3310,
    )
    @patch("apps.staff.phase_e_views.ClamavAttachmentScanner.scan")
    def test_scanner_exception_returns_safe_failure(self, scan):
        scan.side_effect = RuntimeError("synthetic scanner detail")
        self.authenticate(self.admin)
        response = self.client.post(
            f"{self.url}{self.attachment.id}/rescan/",
            {"reason": "Security recheck", "expected_status": "quarantined"},
            format="json",
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "scanner_failed")
        self.assertNotIn("synthetic scanner detail", str(response.data))
        self.attachment.refresh_from_db()
        self.assertEqual(self.attachment.status, AttachmentStatus.QUARANTINED)
        self.assertEqual(self.attachment.scan_status, ScanStatus.FAILED)

    def test_unsafe_release_denied_and_reject_requires_reason(self):
        self.authenticate(self.admin)
        release = self.client.post(
            f"{self.url}{self.attachment.id}/release/",
            {"reason": "Manual override", "expected_status": "quarantined"},
            format="json",
        )
        self.assertEqual(release.status_code, 409)
        self.assertEqual(release.data["code"], "release_not_safe")

        missing = self.client.post(
            f"{self.url}{self.attachment.id}/reject/",
            {"expected_status": "quarantined"},
            format="json",
        )
        self.assertEqual(missing.status_code, 400)
        rejected = self.client.post(
            f"{self.url}{self.attachment.id}/reject/",
            {"reason": "Unsafe scanner result", "expected_status": "quarantined"},
            format="json",
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.data["status"], "rejected")

    @override_settings(ATTACHMENT_RETENTION_DAYS=30)
    @patch("apps.staff.phase_e_views.get_storage_backend")
    def test_retention_delete_preserves_database_and_audit(self, backend_factory):
        self.attachment.status = AttachmentStatus.DELETED
        self.attachment.is_deleted = True
        self.attachment.deleted_at = timezone.now() - timedelta(days=31)
        self.attachment.save()
        backend_factory.return_value = Mock(delete=Mock(return_value=False))
        self.authenticate(self.admin)
        response = self.client.post(
            f"{self.url}{self.attachment.id}/delete/",
            {"reason": "Retention period elapsed", "expected_status": "deleted"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.attachment.refresh_from_db()
        self.assertIsNotNone(self.attachment.storage_deleted_at)
        self.assertTrue(
            AttachmentAuditEvent.objects.filter(
                attachment=self.attachment, event_type="retention_deleted"
            ).exists()
        )

    def test_status_conflict(self):
        self.authenticate(self.admin)
        response = self.client.post(
            f"{self.url}{self.attachment.id}/reject/",
            {"reason": "Unsafe", "expected_status": "pending"},
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "status_conflict")


class NotificationArchitectureTests(TestCase):
    def test_no_fake_delivery_admin_route(self):
        client = APIClient()
        response = client.get("/api/staff/notification-deliveries/")
        self.assertEqual(response.status_code, 404)
