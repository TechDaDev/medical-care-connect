"""Tests for consultation attachment upload, download, delete, and permissions."""

import io
import os
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import UserRole
from apps.attachments.choices import AttachmentCategory, AttachmentStatus
from apps.attachments.models import AttachmentAuditEvent, ConsultationAttachment
from apps.attachments.services.factory import clear_backend_cache, get_storage_backend
from apps.consultations.models import Consultation, ConsultationStatus
from apps.doctors.models import DoctorProfile
from apps.patients.models import PatientProfile

User = get_user_model()

# ── Helpers ─────────────────────────────────────────────────────────────────


def _create_user(email, role, password="testpass123"):
    return User.objects.create_user(email=email, password=password, role=role)


def _create_patient_profile(user):
    return PatientProfile.objects.create(user=user)


def _create_doctor_profile(user):
    return DoctorProfile.objects.create(
        user=user,
        license_number="LIC123",
        is_approved=True,
        approval_status=DoctorProfile.ApprovalStatus.APPROVED,
    )


def _small_pdf() -> bytes:
    """Return a minimal valid PDF byte stream."""
    return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]>>endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"


def _small_jpg() -> bytes:
    """Return a tiny valid JPEG using Pillow."""
    buf = io.BytesIO()
    img = Image.new("RGB", (1, 1), color="red")
    img.save(buf, format="JPEG")
    return buf.getvalue()


class AttachmentUploadTests(TestCase):
    """Test upload flow: permissions, validation, storage."""

    def setUp(self):
        from django.conf import settings as s
        import os
        tmp = tempfile.mkdtemp()
        os.makedirs(tmp, exist_ok=True)
        s.ATTACHMENT_LOCAL_ROOT = tmp
        clear_backend_cache()
        self.client = APIClient()
        self.patient_user = _create_user("patient@test.com", UserRole.PATIENT)
        self.doctor_user = _create_user("doctor@test.com", UserRole.DOCTOR)
        self.other_user = _create_user("other@test.com", UserRole.PATIENT)
        self.staff_user = _create_user("staff@test.com", UserRole.COORDINATOR)

        self.patient_profile = _create_patient_profile(self.patient_user)
        self.other_profile = _create_patient_profile(self.other_user)
        self.doctor_profile = _create_doctor_profile(self.doctor_user)

        self.consultation = Consultation.objects.create(
            patient=self.patient_profile,
            doctor=self.doctor_profile,
            status=ConsultationStatus.SUBMITTED,
        )

    def _upload(self, user, file_content, filename="test.pdf", category=AttachmentCategory.MEDICAL_REPORT, mime="application/pdf"):
        self.client.force_authenticate(user=user)
        from django.core.files.uploadedfile import SimpleUploadedFile
        sf = SimpleUploadedFile(filename, file_content, content_type=mime)
        return self.client.post(
            reverse("attachments:upload", args=[self.consultation.id]),
            {"file": sf, "category": category},
            format="multipart",
        )

    def test_patient_can_upload_pdf(self):
        """Patient can upload a valid PDF to own consultation."""
        resp = self._upload(self.patient_user, _small_pdf())
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn("id", resp.data)
        self.assertEqual(resp.data["status"], AttachmentStatus.AVAILABLE)

    def test_unrelated_patient_cannot_upload(self):
        """Unrelated patient cannot upload to someone else's consultation."""
        resp = self._upload(self.other_user, _small_pdf())
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_assigned_doctor_can_upload(self):
        """Assigned doctor can upload to the consultation."""
        resp = self._upload(self.doctor_user, _small_pdf())
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_oversized_file_rejected(self):
        """File exceeding size limit is rejected."""
        with override_settings(ATTACHMENT_MAX_SIZE_MB=1):
            big = b"x" * (2 * 1024 * 1024)  # 2MB
            resp = self._upload(self.patient_user, big)
            self.assertEqual(resp.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
            self.assertEqual(resp.data.get("code"), "attachment_too_large")

    def test_unsupported_extension_rejected(self):
        """.exe file is rejected."""
        resp = self._upload(self.patient_user, b"fake content", "virus.exe", mime="application/x-msdownload")
        self.assertEqual(resp.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertEqual(resp.data.get("code"), "unsupported_extension")

    def test_mime_signature_mismatch_rejected(self):
        """JPEG declared as PDF is rejected."""
        # Send JPEG data with .pdf extension - should fail signature check
        resp = self._upload(self.patient_user, _small_jpg(), "test.pdf", mime="image/jpeg")
        self.assertEqual(resp.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertIn(resp.data.get("code"), ("invalid_file_signature", "unsupported_extension"))

    def test_storage_key_hides_original_filename(self):
        """Storage key must not expose original filename."""
        resp = self._upload(self.patient_user, _small_pdf(), "my_report.pdf")
        att = ConsultationAttachment.objects.get(pk=resp.data["id"])
        self.assertNotIn("my_report", att.storage_key)
        self.assertNotIn("report", att.storage_key)

    def test_metadata_does_not_expose_storage_key(self):
        """List/detail response must not include storage_key."""
        resp = self._upload(self.patient_user, _small_pdf())
        self.assertNotIn("storage_key", resp.data)
        self.assertNotIn("storage", str(resp.data).lower())


class AttachmentDownloadTests(TestCase):
    """Test download permissions and availability."""

    def setUp(self):
        from django.conf import settings as s
        import os
        tmp = tempfile.mkdtemp()
        os.makedirs(tmp, exist_ok=True)
        s.ATTACHMENT_LOCAL_ROOT = tmp
        clear_backend_cache()
        self.client = APIClient()
        self.patient_user = _create_user("patient@test.com", UserRole.PATIENT)
        self.doctor_user = _create_user("doctor@test.com", UserRole.DOCTOR)
        self.other_user = _create_user("other@test.com", UserRole.PATIENT)
        self.patient_profile = _create_patient_profile(self.patient_user)
        self.other_profile = _create_patient_profile(self.other_user)
        self.doctor_profile = _create_doctor_profile(self.doctor_user)
        self.consultation = Consultation.objects.create(
            patient=self.patient_profile, doctor=self.doctor_profile,
        )

        # Upload an attachment for tests
        self.client.force_authenticate(user=self.patient_user)
        from django.core.files.uploadedfile import SimpleUploadedFile
        sf = SimpleUploadedFile("test.pdf", _small_pdf(), content_type="application/pdf")
        resp = self.client.post(
            reverse("attachments:upload", args=[self.consultation.id]),
            {"file": sf, "category": AttachmentCategory.MEDICAL_REPORT},
            format="multipart",
        )
        self.attachment_id = resp.data["id"]

    def test_authorized_patient_can_download(self):
        """Patient who owns the consultation can download."""
        self.client.force_authenticate(user=self.patient_user)
        resp = self.client.get(reverse("attachments:download", args=[self.attachment_id]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_unrelated_user_cannot_download(self):
        """Unrelated patient cannot download."""
        self.client.force_authenticate(user=self.other_user)
        resp = self.client.get(reverse("attachments:download", args=[self.attachment_id]))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_quarantined_cannot_download(self):
        """Attachment in quarantine cannot be downloaded."""
        ConsultationAttachment.objects.filter(pk=self.attachment_id).update(
            status=AttachmentStatus.QUARANTINED,
        )
        self.client.force_authenticate(user=self.patient_user)
        resp = self.client.get(reverse("attachments:download", args=[self.attachment_id]))
        self.assertEqual(resp.status_code, status.HTTP_410_GONE)

    def test_soft_deleted_cannot_download(self):
        """Soft-deleted attachment cannot be downloaded."""
        ConsultationAttachment.objects.filter(pk=self.attachment_id).update(
            status=AttachmentStatus.DELETED, is_deleted=True,
        )
        self.client.force_authenticate(user=self.patient_user)
        resp = self.client.get(reverse("attachments:download", args=[self.attachment_id]))
        self.assertEqual(resp.status_code, status.HTTP_410_GONE)


class AttachmentDeleteTests(TestCase):
    """Test soft-delete and staff deletion."""

    def setUp(self):
        from django.conf import settings as s
        import os
        tmp = tempfile.mkdtemp()
        os.makedirs(tmp, exist_ok=True)
        s.ATTACHMENT_LOCAL_ROOT = tmp
        clear_backend_cache()
        self.client = APIClient()
        self.patient_user = _create_user("patient@test.com", UserRole.PATIENT)
        self.staff_user = _create_user("staff@test.com", UserRole.COORDINATOR)
        self.patient_profile = _create_patient_profile(self.patient_user)
        self.doctor_profile = _create_doctor_profile(
            _create_user("doc@test.com", UserRole.DOCTOR)
        )
        self.consultation = Consultation.objects.create(
            patient=self.patient_profile, doctor=self.doctor_profile,
        )
        self.client.force_authenticate(user=self.patient_user)
        from django.core.files.uploadedfile import SimpleUploadedFile
        sf = SimpleUploadedFile("report.pdf", _small_pdf(), content_type="application/pdf")
        resp = self.client.post(
            reverse("attachments:upload", args=[self.consultation.id]),
            {"file": sf, "category": AttachmentCategory.MEDICAL_REPORT},
            format="multipart",
        )
        self.attachment_id = resp.data["id"]

    def test_staff_deletion_requires_reason(self):
        """Staff deleting must provide a reason."""
        self.client.force_authenticate(user=self.staff_user)
        resp = self.client.delete(
            reverse("attachments:delete", args=[self.attachment_id]),
            {}, format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_staff_can_delete_with_reason(self):
        """Staff can delete with reason."""
        self.client.force_authenticate(user=self.staff_user)
        resp = self.client.delete(
            reverse("attachments:delete", args=[self.attachment_id]),
            {"reason": "Privacy policy violation"}, format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        att = ConsultationAttachment.objects.get(pk=self.attachment_id)
        self.assertTrue(att.is_deleted)


class PurgeCommandTests(TestCase):
    """Test purge_expired_attachments management command."""

    def setUp(self):
        self.patient_user = _create_user("purge@test.com", UserRole.PATIENT)
        self.doctor_user = _create_user("purgedoc@test.com", UserRole.DOCTOR)
        self.patient_profile = _create_patient_profile(self.patient_user)
        self.doctor_profile = _create_doctor_profile(self.doctor_user)
        self.consultation = Consultation.objects.create(
            patient=self.patient_profile, doctor=self.doctor_profile,
        )
        self.attachment = ConsultationAttachment.objects.create(
            consultation=self.consultation,
            uploaded_by=self.patient_user,
            storage_provider="test",
            storage_key="test/key",
            original_filename="test.pdf",
            status=AttachmentStatus.DELETED,
            is_deleted=True,
        )

    def test_dry_run_does_not_delete_active(self):
        """Dry-run purge must not delete active attachments."""
        self.attachment.is_deleted = False
        self.attachment.status = AttachmentStatus.AVAILABLE
        self.attachment.save()
        from django.core.management import call_command
        call_command("purge_expired_attachments")
        self.assertTrue(ConsultationAttachment.objects.filter(pk=self.attachment.pk).exists())
