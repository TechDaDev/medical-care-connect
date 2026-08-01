from uuid import uuid4

from django.test import override_settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User, UserRole
from apps.ai_intake.models import AIIntakeMessage, AIIntakeSession, IntakeSessionStatus
from apps.attachments.choices import AttachmentStatus, ScanStatus
from apps.attachments.models import ConsultationAttachment
from apps.consultations.models import (
    Consultation,
    ConsultationStatus,
    DoctorConsultationAction,
    Priority,
)
from apps.core.models import AuditEvent
from apps.doctors.models import DoctorProfile
from apps.medical_records.models import MedicalRecordDraft
from apps.messaging.models import ConsultationMessage, DoctorInternalNote
from apps.messaging.services import create_consultation_message
from apps.notifications.models import Notification
from apps.patients.models import PatientProfile
from apps.specialties.models import Specialty


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DoctorPhaseBTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.specialty = Specialty.objects.create(
            name="Synthetic specialty",
            name_en="Synthetic specialty",
            name_ar="تخصص تجريبي",
            name_ckb="پسپۆڕی تاقیکردنەوە",
            slug="synthetic-phase-b",
        )
        cls.doctor_user = User.objects.create_user(
            email="phase-b-doctor@example.test",
            password="test-only",
            role=UserRole.DOCTOR,
            first_name="Doctor",
            last_name="Synthetic",
        )
        cls.doctor = DoctorProfile.objects.create(
            user=cls.doctor_user,
            specialty=cls.specialty,
            license_number="SYN-PHASE-B-1",
            is_approved=True,
            approval_status=DoctorProfile.ApprovalStatus.APPROVED,
            is_accepting_consultations=True,
        )
        cls.other_doctor_user = User.objects.create_user(
            email="phase-b-other@example.test",
            password="test-only",
            role=UserRole.DOCTOR,
        )
        cls.other_doctor = DoctorProfile.objects.create(
            user=cls.other_doctor_user,
            specialty=cls.specialty,
            license_number="SYN-PHASE-B-2",
            is_approved=True,
            approval_status=DoctorProfile.ApprovalStatus.APPROVED,
        )
        cls.pending_user = User.objects.create_user(
            email="phase-b-pending@example.test",
            password="test-only",
            role=UserRole.DOCTOR,
        )
        cls.pending_doctor = DoctorProfile.objects.create(
            user=cls.pending_user,
            specialty=cls.specialty,
            license_number="SYN-PHASE-B-3",
        )
        cls.patient_user = User.objects.create_user(
            email="phase-b-patient@example.test",
            password="test-only",
            role=UserRole.PATIENT,
            first_name="Patient",
            last_name="Synthetic",
        )
        cls.patient = PatientProfile.objects.create(
            user=cls.patient_user,
            date_of_birth="2000-01-01",
            gender="prefer_not_to_say",
        )

    def setUp(self):
        self.consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            specialty=self.specialty,
            status=ConsultationStatus.SUBMITTED,
            priority=Priority.URGENT,
            description="Synthetic non-medical workflow description only.",
            submitted_at=timezone.now(),
        )
        self.client.force_authenticate(self.doctor_user)

    def test_queue_is_paginated_scoped_safe_and_filterable(self):
        Consultation.objects.create(
            patient=self.patient,
            doctor=self.other_doctor,
            specialty=self.specialty,
            status=ConsultationStatus.SUBMITTED,
            description="Other synthetic description.",
        )
        response = self.client.get(
            "/api/consultations/doctor/",
            {"status_group": "new_requests", "priority": "urgent", "search": str(self.consultation.id)},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        item = response.data["results"][0]
        self.assertEqual(item["id"], str(self.consultation.id))
        self.assertNotIn("description", item)
        self.assertNotIn("email", str(item).lower())
        self.assertEqual(item["doctor_action_type"], "new_request")
        self.assertIn("accept", item["available_actions"])

    def test_queue_page_size_is_bounded(self):
        response = self.client.get("/api/consultations/doctor/?page_size=999")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(response.data["results"]), 50)

    def test_queue_denies_non_approved_and_non_doctor_roles(self):
        self.client.force_authenticate(self.pending_user)
        self.assertEqual(
            self.client.get("/api/consultations/doctor/").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.client.force_authenticate(self.patient_user)
        self.assertEqual(
            self.client.get("/api/consultations/doctor/").status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_detail_is_doctor_safe_and_server_authoritative(self):
        response = self.client.get(
            f"/api/consultations/{self.consultation.id}/doctor/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["patient"]["display_name"], "Patient Synthetic")
        self.assertNotIn("email", str(response.data).lower())
        self.assertNotIn("storage_key", str(response.data))
        self.assertEqual(response.data["timeline"][0]["key"], "submitted")
        self.assertTrue(response.data["actions"]["can_accept"])
        self.assertIn(
            f"/app/doctor/consultations/{self.consultation.id}/medical-record",
            response.data["medical_record"]["action_path"],
        )

    def test_unrelated_doctor_cannot_open_detail(self):
        self.client.force_authenticate(self.other_doctor_user)
        response = self.client.get(
            f"/api/consultations/{self.consultation.id}/doctor/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_accept_is_locked_idempotent_and_has_single_side_effects(self):
        request_id = uuid4()
        payload = {
            "expected_status": "submitted",
            "expected_updated_at": self.consultation.updated_at.isoformat(),
            "client_request_id": str(request_id),
        }
        url = f"/api/consultations/{self.consultation.id}/accept/"
        first = self.client.post(url, payload, format="json")
        second = self.client.post(url, payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["status"], ConsultationStatus.ACCEPTED)
        self.assertEqual(
            DoctorConsultationAction.objects.filter(
                consultation=self.consultation, action="accept"
            ).count(),
            1,
        )
        self.assertEqual(
            Notification.objects.filter(consultation=self.consultation).count(), 1
        )
        self.assertEqual(
            AuditEvent.objects.filter(
                target_id=str(self.consultation.id),
                event_type="doctor_consultation_accept",
            ).count(),
            1,
        )
        event = AuditEvent.objects.get(event_type="doctor_consultation_accept")
        self.assertNotIn("description", str(event.metadata))

    def test_accept_rejects_stale_state(self):
        response = self.client.post(
            f"/api/consultations/{self.consultation.id}/accept/",
            {
                "expected_status": "accepted",
                "client_request_id": str(uuid4()),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "consultation_state_changed")

    def test_transition_requires_reason_and_returns_authoritative_detail(self):
        self.consultation.status = ConsultationStatus.DOCTOR_REVIEW
        self.consultation.save(update_fields=["status", "updated_at"])
        url = f"/api/consultations/{self.consultation.id}/doctor-transition/"
        rejected = self.client.post(url, {
            "action": "request_patient_response",
            "expected_status": "doctor_review",
            "client_request_id": str(uuid4()),
        }, format="json")
        self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)
        accepted = self.client.post(url, {
            "action": "request_patient_response",
            "reason": "Synthetic patient-visible request",
            "expected_status": "doctor_review",
            "expected_updated_at": self.consultation.updated_at.isoformat(),
            "client_request_id": str(uuid4()),
        }, format="json")
        self.assertEqual(accepted.status_code, status.HTTP_200_OK)
        self.assertEqual(accepted.data["status"], ConsultationStatus.AWAITING_PATIENT_RESPONSE)

    def test_completed_transition_requires_record(self):
        self.consultation.status = ConsultationStatus.UNDER_REVIEW
        self.consultation.save(update_fields=["status", "updated_at"])
        payload = {
            "action": "complete",
            "reason": "Synthetic completion rationale",
            "expected_status": "under_review",
            "client_request_id": str(uuid4()),
        }
        url = f"/api/consultations/{self.consultation.id}/doctor-transition/"
        denied = self.client.post(url, payload, format="json")
        self.assertEqual(denied.data["code"], "medical_record_required")
        record = MedicalRecordDraft.objects.create(
            consultation=self.consultation,
            status="finalized",
            clinical_summary="Synthetic finalized summary.",
            patient_instructions="Synthetic finalized instructions.",
            recommendations="Synthetic finalized recommendation.",
        )
        payload["client_request_id"] = str(uuid4())
        payload.update({
            "outcome": "remote_care_completed",
            "medical_record_id": str(record.id),
            "confirmation": True,
        })
        allowed = self.client.post(url, payload, format="json")
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)
        self.assertEqual(allowed.data["status"], ConsultationStatus.COMPLETED)
        self.assertIsNotNone(allowed.data["completed_at"])

    def test_doctor_intake_excludes_hidden_ai_fields(self):
        self.consultation.status = ConsultationStatus.INTAKE_COMPLETED
        self.consultation.save(update_fields=["status", "updated_at"])
        session = AIIntakeSession.objects.create(
            consultation=self.consultation,
            status=IntakeSessionStatus.READY_FOR_REVIEW,
            ai_provider="hidden-provider",
            prompt_version="hidden-prompt",
            collected_data={"chief_complaint": "Synthetic concern", "symptoms": ["synthetic"]},
            missing_fields=["synthetic_field"],
        )
        AIIntakeMessage.objects.create(
            session=session, role="system", content="hidden system prompt", sequence_number=1
        )
        AIIntakeMessage.objects.create(
            session=session, role="assistant", content="Synthetic question", sequence_number=2
        )
        AIIntakeMessage.objects.create(
            session=session, role="patient", content="Synthetic answer", sequence_number=3
        )
        response = self.client.get(
            f"/api/consultations/{self.consultation.id}/doctor-intake/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = str(response.data)
        self.assertNotIn("hidden-provider", body)
        self.assertNotIn("hidden system prompt", body)
        self.assertNotIn("hidden-prompt", body)
        self.assertEqual(response.data["answered_count"], 1)

    def test_internal_note_is_idempotent_paginated_and_has_safe_author(self):
        request_id = str(uuid4())
        url = f"/api/messaging/{self.consultation.id}/internal-notes/"
        payload = {
            "content": "Synthetic private workspace note",
            "client_request_id": request_id,
        }
        first = self.client.post(url, payload, format="json")
        second = self.client.post(url, payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(DoctorInternalNote.objects.count(), 1)
        self.assertNotIn("email", str(first.data).lower())
        listing = self.client.get(url)
        self.assertEqual(listing.data["count"], 1)
        self.client.force_authenticate(self.patient_user)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_403_FORBIDDEN)

    def test_pending_assigned_doctor_cannot_open_internal_note_detail(self):
        self.consultation.doctor = self.pending_doctor
        self.consultation.save(update_fields=["doctor", "updated_at"])
        note = DoctorInternalNote.objects.create(
            consultation=self.consultation,
            author=self.pending_user,
            content="Synthetic private workspace note",
            client_request_id=uuid4(),
        )
        self.client.force_authenticate(self.pending_user)
        response = self.client.get(
            f"/api/messaging/{self.consultation.id}/internal-notes/{note.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_attachment_summary_and_actions_are_safe(self):
        attachment = ConsultationAttachment.objects.create(
            consultation=self.consultation,
            uploaded_by=self.doctor_user,
            storage_provider="synthetic",
            storage_key=f"private/{uuid4()}",
            original_filename="synthetic.txt",
            safe_display_name="synthetic.txt",
            size_bytes=9,
            status=AttachmentStatus.AVAILABLE,
            scan_status=ScanStatus.CLEAN,
        )
        detail = self.client.get(
            f"/api/consultations/{self.consultation.id}/doctor/"
        )
        self.assertEqual(detail.data["attachments"]["total"], 1)
        listing = self.client.get(
            f"/api/consultations/{self.consultation.id}/attachments/"
        )
        item = listing.data["results"][0]
        self.assertNotIn("storage_key", item)
        self.assertTrue(item["actions"]["can_download"])
        self.assertTrue(item["actions"]["can_delete"])
        self.assertEqual(item["id"], str(attachment.id))

    def test_patient_response_advances_state_once_without_content_in_audit(self):
        self.consultation.status = ConsultationStatus.AWAITING_PATIENT_RESPONSE
        self.consultation.save(update_fields=["status", "updated_at"])
        request_id = uuid4()
        first = create_consultation_message(
            self.consultation,
            self.patient_user,
            "Synthetic response without medical content",
            client_request_id=request_id,
        )
        second = create_consultation_message(
            self.consultation,
            self.patient_user,
            "Synthetic response without medical content",
            client_request_id=request_id,
        )
        self.consultation.refresh_from_db()
        self.assertEqual(first.id, second.id)
        self.assertEqual(
            self.consultation.status,
            ConsultationStatus.AWAITING_DOCTOR_RESPONSE,
        )
        event = AuditEvent.objects.get(event_type="patient_response_received")
        self.assertNotIn("content", str(event.metadata).lower())

    def test_queue_and_detail_query_counts_are_bounded(self):
        for index in range(5):
            Consultation.objects.create(
                patient=self.patient,
                doctor=self.doctor,
                specialty=self.specialty,
                description=f"Synthetic queue item {index}",
                status=ConsultationStatus.SUBMITTED,
                submitted_at=timezone.now(),
            )
        with CaptureQueriesContext(connection) as queue_queries:
            response = self.client.get("/api/consultations/doctor/")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        with CaptureQueriesContext(connection) as detail_queries:
            response = self.client.get(
                f"/api/consultations/{self.consultation.id}/doctor/"
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(queue_queries), 3)
        self.assertLessEqual(len(detail_queries), 2)
