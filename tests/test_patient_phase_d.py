from datetime import date, timedelta

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import User, UserRole
from apps.consultations.models import Consultation, ConsultationStatus
from apps.core.models import AuditEvent
from apps.doctors.models import DoctorProfile
from apps.medical_records.models import MedicalRecordDraft, RecordStatus
from apps.messaging.models import ConsultationMessage, DoctorInternalNote
from apps.notifications.models import Notification, NotificationType
from apps.patients.models import PatientProfile
from apps.privacy.models import (
    AccountDeletionRequest,
    DataExportRequest,
    ExportStatus,
)
from apps.specialties.models import Specialty


class PatientPhaseDTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.specialty = Specialty.objects.create(
            name="Phase D Medicine",
            name_en="Phase D Medicine",
            name_ar="طب المرحلة د",
            name_ckb="پزیشکی قۆناغی د",
            slug="phase-d-medicine",
        )
        cls.doctor_user = User.objects.create_user(
            email="phase-d-doctor@example.test",
            role=UserRole.DOCTOR,
            first_name="Case",
            last_name="Doctor",
        )
        cls.doctor = DoctorProfile.objects.create(
            user=cls.doctor_user,
            specialty=cls.specialty,
            professional_title="Consultant",
            license_number="PHASE-D-LIC",
            is_approved=True,
            is_accepting_consultations=True,
        )
        cls.patient_user = User.objects.create_user(
            email="phase-d-patient@example.test",
            role=UserRole.PATIENT,
            first_name="Case",
            last_name="Patient",
            phone_number="+9647500000000",
        )
        cls.patient = PatientProfile.objects.create(
            user=cls.patient_user,
            date_of_birth=date(1990, 1, 1),
            gender="female",
            preferred_language="en",
            address="Synthetic address",
            emergency_contact_name="Synthetic Contact",
            emergency_contact_phone="+9647500000001",
            blood_type="O+",
        )
        cls.other_user = User.objects.create_user(
            email="phase-d-other@example.test",
            role=UserRole.PATIENT,
        )
        cls.other_patient = PatientProfile.objects.create(user=cls.other_user)
        cls.consultation = Consultation.objects.create(
            patient=cls.patient,
            doctor=cls.doctor,
            specialty=cls.specialty,
            status=ConsultationStatus.COMPLETED,
            description="Synthetic consultation.",
        )
        cls.other_consultation = Consultation.objects.create(
            patient=cls.other_patient,
            doctor=cls.doctor,
            specialty=cls.specialty,
            status=ConsultationStatus.COMPLETED,
            description="Other synthetic consultation.",
        )
        cls.record = MedicalRecordDraft.objects.create(
            consultation=cls.consultation,
            status=RecordStatus.FINALIZED,
            chief_complaint="Synthetic safe concern",
            symptoms=["synthetic symptom"],
            doctor_notes="Internal doctor note",
            additional_notes="Internal generated note",
        )
        cls.other_record = MedicalRecordDraft.objects.create(
            consultation=cls.other_consultation,
            status=RecordStatus.FINALIZED,
            chief_complaint="Other patient concern",
        )
        cls.doctor_message = ConsultationMessage.objects.create(
            consultation=cls.consultation,
            sender=cls.doctor_user,
            content="Synthetic conversation preview",
        )
        DoctorInternalNote.objects.create(
            consultation=cls.consultation,
            author=cls.doctor_user,
            content="Internal note must stay hidden",
        )

    def setUp(self):
        self.client.force_authenticate(self.patient_user)

    def test_composite_profile_and_dashboard_share_completion(self):
        response = self.client.get(reverse("patients:my-profile"))
        dashboard = self.client.get(reverse("patients:my-dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.data),
            {"account", "profile", "completion", "generated_at"},
        )
        self.assertNotIn("role", response.data["account"])
        self.assertNotIn("password", response.data["account"])
        self.assertEqual(
            response.data["completion"]["percent"],
            dashboard.data["profile"]["completion_percent"],
        )
        self.assertTrue(response.data["completion"]["emergency_contact_complete"])

    def test_profile_update_validation_and_mass_assignment_safety(self):
        profile_url = reverse("patients:my-profile")
        future = self.client.patch(
            profile_url,
            {"date_of_birth": date.today() + timedelta(days=1)},
            format="json",
        )
        partial_contact = self.client.patch(
            profile_url,
            {"emergency_contact_name": "", "emergency_contact_phone": "+9647500000001"},
            format="json",
        )
        invalid_health = self.client.patch(
            profile_url,
            {"blood_type": "invalid", "preferred_language": "invalid"},
            format="json",
        )
        account = self.client.patch(
            reverse("accounts:current-user"),
            {"first_name": "Updated", "role": UserRole.ADMINISTRATOR},
            format="json",
        )

        self.assertEqual(future.status_code, 400)
        self.assertEqual(partial_contact.status_code, 400)
        self.assertEqual(invalid_health.status_code, 400)
        self.assertEqual(account.status_code, 200)
        self.patient_user.refresh_from_db()
        self.assertEqual(self.patient_user.role, UserRole.PATIENT)

    def test_patient_record_list_and_detail_are_safe_and_bounded(self):
        list_url = reverse("patients:medical-record-list")
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(
                list_url,
                {"status": "finalized", "search": str(self.record.id)},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertLessEqual(len(queries), 7)
        item = response.data["results"][0]
        self.assertNotIn("doctor_notes", item)
        self.assertNotIn("additional_notes", item)
        self.assertNotIn("intake_session", item)

        detail = self.client.get(
            reverse("patients:medical-record-detail", args=[self.record.id])
        )
        denied = self.client.get(
            reverse("patients:medical-record-detail", args=[self.other_record.id])
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(denied.status_code, 404)
        self.assertNotIn("doctor_notes", detail.data)
        self.assertNotIn("additional_notes", detail.data)

    def test_message_threads_are_aggregated_safe_and_filtered(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(
                reverse("patients:message-thread-list"),
                {"unread_only": "true", "search": str(self.consultation.id)},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertLessEqual(len(queries), 7)
        thread = response.data["results"][0]
        self.assertEqual(thread["unread_count"], 1)
        self.assertEqual(thread["last_message_sender_role"], UserRole.DOCTOR)
        self.assertLessEqual(len(thread["last_message_preview"]), 120)
        self.assertNotIn("sender_email", thread)
        self.assertNotIn("internal note", thread["last_message_preview"].lower())

    def test_notifications_are_paginated_link_safe_and_idempotent(self):
        notification = Notification.objects.create(
            recipient=self.patient_user,
            notification_type=NotificationType.NEW_MESSAGE,
            title="Synthetic notification",
            body="Synthetic safe body",
            consultation=self.consultation,
            related_message=self.doctor_message,
        )
        response = self.client.get(
            reverse("notifications:list"),
            {"unread": "true", "type": NotificationType.NEW_MESSAGE},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        item = response.data["results"][0]
        self.assertEqual(
            item["link"]["path"],
            f"/app/patient/messages/{self.consultation.id}",
        )
        self.assertNotIn("recipient", item)
        self.assertNotIn("related_message", item)

        mark_url = reverse("notifications:mark-one-read", args=[notification.id])
        first = self.client.post(mark_url)
        second = self.client.post(mark_url)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertIsNotNone(second.data["read_at"])

    def test_phase_d_read_and_batch_query_counts_are_bounded(self):
        Notification.objects.create(
            recipient=self.patient_user,
            notification_type=NotificationType.STATUS_CHANGE,
            title="Synthetic bounded notification",
        )
        DataExportRequest.objects.create(
            requested_by=self.patient_user,
            subject_user=self.patient_user,
            status=ExportStatus.PENDING,
        )
        deletion = AccountDeletionRequest.objects.create(
            requested_by=self.patient_user,
            subject_user=self.patient_user,
            reason="Synthetic bounded privacy request.",
        )
        cases = [
            (reverse("patients:my-profile"), 5),
            (
                reverse(
                    "patients:medical-record-detail",
                    args=[self.record.id],
                ),
                5,
            ),
            (reverse("notifications:list"), 7),
            (reverse("privacy:export-list-create"), 4),
            (
                reverse(
                    "privacy:deletion-detail-cancel",
                    args=[deletion.id],
                ),
                4,
            ),
        ]
        for url, limit in cases:
            with self.subTest(url=url), CaptureQueriesContext(connection) as queries:
                response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertLessEqual(len(queries), limit)

        with CaptureQueriesContext(connection) as queries:
            response = self.client.post(reverse("notifications:mark-all-read"))
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 5)

    def test_privacy_requests_validate_and_prevent_duplicates(self):
        export_url = reverse("privacy:export-list-create")
        first_export = self.client.post(export_url, {}, format="json")
        second_export = self.client.post(export_url, {}, format="json")
        self.assertEqual(first_export.status_code, 201)
        self.assertEqual(second_export.status_code, 409)
        self.assertEqual(
            DataExportRequest.objects.filter(
                subject_user=self.patient_user,
                status=ExportStatus.PENDING,
            ).count(),
            1,
        )

        deletion_url = reverse("privacy:deletion-list-create")
        missing_confirmation = self.client.post(
            deletion_url,
            {"reason": "Synthetic deletion request reason.", "confirmation": False},
            format="json",
        )
        short_reason = self.client.post(
            deletion_url,
            {"reason": "short", "confirmation": True},
            format="json",
        )
        valid = self.client.post(
            deletion_url,
            {
                "reason": "Synthetic deletion request for lifecycle verification.",
                "confirmation": True,
            },
            format="json",
        )
        duplicate = self.client.post(
            deletion_url,
            {
                "reason": "Another synthetic deletion request.",
                "confirmation": True,
            },
            format="json",
        )
        self.assertEqual(missing_confirmation.status_code, 400)
        self.assertEqual(short_reason.status_code, 400)
        self.assertEqual(valid.status_code, 201)
        self.assertEqual(duplicate.status_code, 409)
        self.assertTrue(self.patient_user.is_active)
        self.assertEqual(
            AccountDeletionRequest.objects.filter(
                subject_user=self.patient_user
            ).count(),
            1,
        )
        audit = AuditEvent.objects.get(
            event_type="privacy.deletion.requested",
            target_id=valid.data["id"],
        )
        self.assertNotIn("Synthetic deletion request", audit.summary)
        self.assertFalse(audit.metadata)

    def test_patient_endpoints_deny_non_patient_roles(self):
        self.client.force_authenticate(self.doctor_user)
        for url in (
            reverse("patients:my-profile"),
            reverse("patients:medical-record-list"),
            reverse("patients:message-thread-list"),
        ):
            self.assertEqual(self.client.get(url).status_code, 403)
