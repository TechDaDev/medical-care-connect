from uuid import uuid4

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import User, UserRole
from apps.ai_intake.models import AIIntakeMessage, AIIntakeSession
from apps.consultations.models import Consultation, ConsultationStatus
from apps.core.models import AuditEvent
from apps.doctors.models import DoctorProfile
from apps.medical_records.models import MedicalRecordDraft
from apps.messaging.models import ConsultationMessage, MessageReadReceipt
from apps.notifications.models import Notification, NotificationType
from apps.patients.models import PatientProfile
from apps.specialties.models import Specialty


class PatientPhaseCTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.specialty = Specialty.objects.create(
            name="Phase C Medicine", name_en="Phase C Medicine",
            name_ar="طب المرحلة ج", name_ckb="پزیشکی قۆناغی ج",
            slug="phase-c-medicine",
        )
        cls.doctor_user = User.objects.create_user(
            email="phase-c-doctor@example.test", role=UserRole.DOCTOR,
            first_name="Case", last_name="Doctor",
        )
        cls.doctor = DoctorProfile.objects.create(
            user=cls.doctor_user, specialty=cls.specialty,
            professional_title="Consultant", license_number="PHASE-C-LIC",
            is_approved=True, is_accepting_consultations=True,
        )
        cls.patient_user = User.objects.create_user(
            email="phase-c-patient@example.test", role=UserRole.PATIENT,
        )
        cls.patient = PatientProfile.objects.create(user=cls.patient_user)
        cls.other_user = User.objects.create_user(
            email="phase-c-other@example.test", role=UserRole.PATIENT,
        )
        cls.other_patient = PatientProfile.objects.create(user=cls.other_user)

    def setUp(self):
        self.consultation = Consultation.objects.create(
            patient=self.patient, doctor=self.doctor, specialty=self.specialty,
            status=ConsultationStatus.SUBMITTED,
            description="Synthetic Phase C consultation.",
        )
        self.client.force_authenticate(self.patient_user)

    def test_patient_list_contract_filters_and_safe_fields(self):
        Consultation.objects.create(
            patient=self.other_patient, doctor=self.doctor,
            status=ConsultationStatus.COMPLETED,
            description="Other synthetic consultation.",
        )
        response = self.client.get(
            reverse("consultations:list"),
            {"status_group": "active", "search": str(self.consultation.id)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"count", "next", "previous", "results"})
        self.assertEqual(response.data["count"], 1)
        item = response.data["results"][0]
        self.assertNotIn("description", item)
        self.assertNotIn("cancellation_reason", item)
        self.assertIn("available_actions", item)

    def test_patient_detail_is_safe_and_server_authoritative(self):
        response = self.client.get(
            reverse("consultations:detail", args=[self.consultation.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("patient_email", response.data)
        self.assertNotIn("doctor_email", response.data)
        self.assertEqual(response.data["timeline"][0]["key"], "submitted")
        self.assertTrue(response.data["actions"]["can_cancel"])
        self.assertEqual(response.data["action_reasons"]["cancel"], None)

    def test_other_patient_cannot_access_detail_or_cancel(self):
        self.client.force_authenticate(self.other_user)
        detail = self.client.get(
            reverse("consultations:detail", args=[self.consultation.id])
        )
        cancel = self.client.post(
            reverse("consultations:cancel", args=[self.consultation.id]),
            {"reason": "This reason is long enough.", "expected_status": "submitted"},
        )
        self.assertEqual(detail.status_code, 404)
        self.assertEqual(cancel.status_code, 404)

    def test_cancellation_conflict_transaction_and_idempotency(self):
        url = reverse("consultations:cancel", args=[self.consultation.id])
        conflict = self.client.post(
            url, {"reason": "This reason is long enough.", "expected_status": "accepted"},
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.data["code"], "consultation_state_changed")
        payload = {
            "reason": "Patient no longer needs this consultation.",
            "expected_status": "submitted",
        }
        first = self.client.post(url, payload)
        second = self.client.post(url, payload)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["code"], "already_cancelled")
        self.assertEqual(
            AuditEvent.objects.filter(
                event_type="patient_consultation_cancelled",
                target_id=str(self.consultation.id),
            ).count(), 1,
        )
        self.assertEqual(
            Notification.objects.filter(
                consultation=self.consultation,
                notification_type=NotificationType.CONSULTATION_CANCELLED,
                recipient=self.doctor_user,
            ).count(), 1,
        )

    def test_patient_record_excludes_internal_fields(self):
        record = MedicalRecordDraft.objects.create(
            consultation=self.consultation,
            chief_complaint="Synthetic complaint",
            doctor_notes="Internal note",
            additional_notes="Internal additional note",
        )
        response = self.client.get(
            reverse("records:record-detail", args=[record.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("doctor_notes", response.data)
        self.assertNotIn("additional_notes", response.data)
        self.assertNotIn("intake_session", response.data)

    def test_message_idempotency_pagination_and_safe_sender(self):
        url = f"/api/messaging/{self.consultation.id}/messages/"
        request_id = str(uuid4())
        payload = {"content": "Synthetic patient message", "client_request_id": request_id}
        first = self.client.post(url, payload)
        second = self.client.post(url, payload)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.data["id"], second.data["id"])
        response = self.client.get(url)
        self.assertEqual(set(response.data), {"count", "next", "previous", "results"})
        self.assertNotIn("sender_email", response.data["results"][0])
        self.assertEqual(ConsultationMessage.objects.count(), 1)

    def test_mark_read_excludes_own_messages(self):
        own = ConsultationMessage.objects.create(
            consultation=self.consultation, sender=self.patient_user,
            content="Synthetic own message",
        )
        incoming = ConsultationMessage.objects.create(
            consultation=self.consultation, sender=self.doctor_user,
            content="Synthetic doctor message",
        )
        response = self.client.post(
            f"/api/messaging/{self.consultation.id}/messages/read/",
            {"message_ids": [str(own.id), str(incoming.id)]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            MessageReadReceipt.objects.filter(message=own, user=self.patient_user).exists()
        )
        self.assertTrue(
            MessageReadReceipt.objects.filter(
                message=incoming, user=self.patient_user
            ).exists()
        )

    def test_list_and_detail_query_counts_are_bounded(self):
        Consultation.objects.bulk_create([
            Consultation(
                patient=self.patient,
                doctor=self.doctor,
                specialty=self.specialty,
                status=ConsultationStatus.SUBMITTED,
            )
            for _ in range(12)
        ])
        with CaptureQueriesContext(connection) as list_queries:
            response = self.client.get(reverse("consultations:list"))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["count"], 13)
        self.assertLessEqual(len(list_queries), 8)

        with CaptureQueriesContext(connection) as detail_queries:
            response = self.client.get(
                reverse("consultations:detail", args=[self.consultation.id])
            )
            self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(detail_queries), 8)

    def test_intake_contract_hides_ai_internals_and_blocks_duplicate_side_effects(self):
        self.consultation.status = ConsultationStatus.ACCEPTED
        self.consultation.save(update_fields=["status", "updated_at"])
        session = AIIntakeSession.objects.create(
            consultation=self.consultation,
            status="in_progress",
            emergency_reasons=["private-rule"],
            collected_data={"private": "medical-data"},
            missing_fields=["private-field"],
            current_question="Synthetic question",
        )
        response = self.client.get(
            reverse("intake:intake-session", args=[session.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("emergency_reasons", response.data)
        self.assertNotIn("collected_data", response.data)
        self.assertNotIn("missing_fields", response.data)

        request_id = str(uuid4())
        url = reverse("intake:intake-answer", args=[session.id])
        first = self.client.post(
            url,
            {
                "answer": "I have crushing chest pain",
                "client_request_id": request_id,
            },
        )
        second = self.client.post(
            url,
            {
                "answer": "I have crushing chest pain",
                "client_request_id": request_id,
            },
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            AIIntakeMessage.objects.filter(
                session=session, client_request_id=request_id
            ).count(),
            1,
        )
        self.assertEqual(
            Notification.objects.filter(
                consultation=self.consultation,
                notification_type=NotificationType.EMERGENCY_ESCALATED,
            ).count(),
            1,
        )
        self.assertEqual(
            AuditEvent.objects.filter(
                event_type="patient_intake_emergency_escalated",
                target_id=str(self.consultation.id),
            ).count(),
            1,
        )
