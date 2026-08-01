from uuid import uuid4

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User, UserRole
from apps.consultations.models import Consultation, ConsultationStatus
from apps.core.models import AuditEvent
from apps.doctors.models import DoctorProfile
from apps.medical_records.models import MedicalRecordAction, MedicalRecordDraft, RecordStatus
from apps.notifications.models import Notification, NotificationType
from apps.patients.models import PatientProfile
from apps.specialties.models import Specialty


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DoctorPhaseCTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.specialty = Specialty.objects.create(
            name="Synthetic Phase C specialty",
            name_en="Synthetic Phase C specialty",
            name_ar="تخصص تجريبي ج",
            name_ckb="پسپۆڕی تاقیکردنەوەی ج",
            slug="synthetic-doctor-phase-c",
        )
        cls.doctor_user = User.objects.create_user(
            email="phase-c-doctor@example.test",
            role=UserRole.DOCTOR,
            first_name="Phase",
            last_name="Doctor",
        )
        cls.doctor = DoctorProfile.objects.create(
            user=cls.doctor_user,
            specialty=cls.specialty,
            license_number="SYN-DOCTOR-PHASE-C",
            is_approved=True,
            approval_status=DoctorProfile.ApprovalStatus.APPROVED,
        )
        cls.other_doctor_user = User.objects.create_user(
            email="phase-c-other-doctor@example.test",
            role=UserRole.DOCTOR,
        )
        cls.other_doctor = DoctorProfile.objects.create(
            user=cls.other_doctor_user,
            specialty=cls.specialty,
            license_number="SYN-DOCTOR-PHASE-C-OTHER",
            is_approved=True,
            approval_status=DoctorProfile.ApprovalStatus.APPROVED,
        )
        cls.pending_user = User.objects.create_user(
            email="phase-c-pending@example.test", role=UserRole.DOCTOR
        )
        DoctorProfile.objects.create(
            user=cls.pending_user,
            specialty=cls.specialty,
            license_number="SYN-DOCTOR-PHASE-C-PENDING",
        )
        cls.patient_user = User.objects.create_user(
            email="phase-c-patient@example.test",
            role=UserRole.PATIENT,
            first_name="Phase",
            last_name="Patient",
        )
        cls.patient = PatientProfile.objects.create(user=cls.patient_user)

    def setUp(self):
        self.consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            specialty=self.specialty,
            status=ConsultationStatus.UNDER_REVIEW,
            description="Synthetic patient-reported concern; not diagnostic.",
        )
        self.client.force_authenticate(self.doctor_user)

    def create_record(self):
        return self.client.post(
            f"/api/consultations/{self.consultation.id}/medical-record/",
            {"client_request_id": str(uuid4())},
            format="json",
        )

    def complete_record(self):
        created = self.create_record()
        record_id = created.data["id"]
        updated = self.client.patch(
            f"/api/doctors/me/medical-records/{record_id}/",
            {
                "doctor_authored": {
                    "clinical_summary": "Synthetic clinician summary.",
                    "patient_instructions": "Synthetic safe instructions.",
                    "recommendations": "Synthetic non-diagnostic recommendation.",
                },
                "expected_version": created.data["version"],
                "client_request_id": str(uuid4()),
            },
            format="json",
        )
        finalized = self.client.post(
            f"/api/doctors/me/medical-records/{record_id}/finalize/",
            {
                "expected_version": updated.data["version"],
                "client_request_id": str(uuid4()),
                "confirmation": True,
            },
            format="json",
        )
        return finalized

    def test_get_or_create_is_idempotent_seeded_and_audited_once(self):
        request_id = uuid4()
        url = f"/api/consultations/{self.consultation.id}/medical-record/"
        first = self.client.post(url, {"client_request_id": str(request_id)}, format="json")
        second = self.client.post(url, {"client_request_id": str(request_id)}, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(first.data["patient_reported"]["reported_concern"], self.consultation.description)
        self.assertEqual(first.data["doctor_authored"]["clinical_summary"], "")
        self.assertEqual(first.data["provenance"]["chief_complaint"], "patient_reported")
        self.assertEqual(MedicalRecordDraft.objects.filter(consultation=self.consultation).count(), 1)
        self.assertEqual(MedicalRecordAction.objects.filter(action="create").count(), 1)
        event = AuditEvent.objects.get(event_type="doctor_medical_record_created")
        self.assertNotIn(self.consultation.description, str(event.metadata))

    def test_doctor_list_is_scoped_paginated_narrative_free_and_bounded(self):
        created = self.create_record()
        other_consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.other_doctor,
            specialty=self.specialty,
            status=ConsultationStatus.UNDER_REVIEW,
        )
        MedicalRecordDraft.objects.create(consultation=other_consultation)
        record = MedicalRecordDraft.objects.get(consultation=self.consultation)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(
                "/api/doctors/me/medical-records/",
                {"record_status": "draft", "search": str(record.id), "page_size": 999},
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1, response.data)
        self.assertLessEqual(len(response.data["results"]), 100)
        self.assertLessEqual(len(queries), 4)
        item = response.data["results"][0]
        for forbidden in ("clinical_summary", "doctor_notes", "chief_complaint", "ai_suggestions"):
            self.assertNotIn(forbidden, item)

    def test_detail_is_scoped_safe_and_query_bounded(self):
        created = self.create_record()
        with CaptureQueriesContext(connection) as queries:
            detail = self.client.get(
                f"/api/doctors/me/medical-records/{created.data['id']}/"
            )
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(queries), 3)
        self.assertFalse(detail.data["ai_suggestions"]["available"])
        self.assertNotIn("provider", str(detail.data["ai_suggestions"]).lower())
        self.client.force_authenticate(self.other_doctor_user)
        self.assertEqual(
            self.client.get(f"/api/doctors/me/medical-records/{created.data['id']}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_update_only_doctor_authored_fields_uses_version_and_audit_names(self):
        created = self.create_record()
        url = f"/api/doctors/me/medical-records/{created.data['id']}/"
        payload = {
            "doctor_authored": {
                "clinical_summary": "  ملخص تجريبي\nسطر ثانٍ  ",
                "patient_instructions": "ڕێنمایی تاقیکردنەوە",
            },
            "expected_version": created.data["version"],
            "client_request_id": str(uuid4()),
        }
        updated = self.client.patch(url, payload, format="json")
        stale = self.client.patch(
            url,
            {**payload, "client_request_id": str(uuid4())},
            format="json",
        )
        protected = self.client.patch(
            url,
            {
                "doctor_authored": {"chief_complaint": "forbidden"},
                "expected_version": updated.data["version"],
                "client_request_id": str(uuid4()),
            },
            format="json",
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertEqual(updated.data["version"], 2)
        self.assertEqual(
            updated.data["doctor_authored"]["clinical_summary"],
            "ملخص تجريبي\nسطر ثانٍ",
        )
        self.assertEqual(stale.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(stale.data["code"], "stale_medical_record")
        self.assertEqual(protected.status_code, status.HTTP_400_BAD_REQUEST)
        event = AuditEvent.objects.get(event_type="doctor_medical_record_updated")
        self.assertEqual(set(event.metadata["changed_fields"]), {"clinical_summary", "patient_instructions"})
        self.assertNotIn("ملخص", str(event.metadata))

    def test_finalization_validates_is_idempotent_and_makes_record_immutable(self):
        created = self.create_record()
        finalize_url = f"/api/doctors/me/medical-records/{created.data['id']}/finalize/"
        incomplete = self.client.post(
            finalize_url,
            {"expected_version": 1, "client_request_id": str(uuid4()), "confirmation": True},
            format="json",
        )
        self.assertEqual(incomplete.status_code, status.HTTP_400_BAD_REQUEST)
        update = self.client.patch(
            f"/api/doctors/me/medical-records/{created.data['id']}/",
            {
                "doctor_authored": {
                    "assessment": "Synthetic assessment.",
                    "patient_instructions": "Synthetic instructions.",
                    "treatment_plan": "Synthetic plan.",
                },
                "expected_version": 1,
                "client_request_id": str(uuid4()),
            },
            format="json",
        )
        request_id = uuid4()
        payload = {
            "expected_version": update.data["version"],
            "client_request_id": str(request_id),
            "confirmation": True,
        }
        first = self.client.post(finalize_url, payload, format="json")
        second = self.client.post(finalize_url, payload, format="json")
        mutation = self.client.patch(
            f"/api/doctors/me/medical-records/{created.data['id']}/",
            {
                "doctor_authored": {"assessment": "Mutation denied"},
                "expected_version": first.data["version"],
                "client_request_id": str(uuid4()),
            },
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["record_status"], RecordStatus.FINALIZED)
        self.assertEqual(mutation.data["code"], "medical_record_finalized")
        self.assertEqual(Notification.objects.filter(notification_type=NotificationType.RECORD_FINALIZED).count(), 1)
        self.assertEqual(AuditEvent.objects.filter(event_type="doctor_medical_record_finalized").count(), 1)

    def test_patient_projection_hides_drafts_and_internal_fields(self):
        created = self.create_record()
        self.client.force_authenticate(self.patient_user)
        hidden = self.client.get("/api/patients/me/medical-records/")
        self.assertEqual(hidden.data["count"], 0)
        self.assertEqual(
            self.client.get(f"/api/patients/me/medical-records/{created.data['id']}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.get(f"/api/medical-records/{created.data['id']}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.post(
                f"/api/medical-records/{created.data['id']}/confirm/",
                {"confirmed": True},
                format="json",
            ).data["code"],
            "doctor_finalization_required",
        )
        self.client.force_authenticate(self.doctor_user)
        self.assertEqual(
            self.client.patch(
                f"/api/medical-records/{created.data['id']}/",
                {"doctor_notes": "Synthetic bypass attempt"},
                format="json",
            ).data["code"],
            "use_doctor_medical_record_endpoint",
        )
        self.client.force_authenticate(self.doctor_user)
        finalized = self.complete_record()
        self.client.force_authenticate(self.patient_user)
        detail = self.client.get(f"/api/patients/me/medical-records/{finalized.data['id']}/")
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        for forbidden in ("doctor_notes", "differential_considerations", "provenance", "version", "ai_suggestions"):
            self.assertNotIn(forbidden, detail.data)

    def test_outcome_requires_finalized_record_and_records_safe_side_effects(self):
        finalized = self.complete_record()
        payload = {
            "action": "complete",
            "outcome": "remote_care_completed",
            "medical_record_id": finalized.data["id"],
            "confirmation": True,
            "reason": "Synthetic remote completion outcome.",
            "expected_status": ConsultationStatus.UNDER_REVIEW,
            "expected_updated_at": self.consultation.updated_at.isoformat(),
            "client_request_id": str(uuid4()),
        }
        response = self.client.post(
            f"/api/consultations/{self.consultation.id}/doctor-transition/",
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], ConsultationStatus.COMPLETED)
        record = MedicalRecordDraft.objects.get(pk=finalized.data["id"])
        self.assertEqual(record.clinical_outcome, "remote_care_completed")
        event = AuditEvent.objects.get(event_type="doctor_consultation_complete")
        self.assertNotIn("Synthetic remote", str(event.metadata))

    def test_transfer_changes_record_access_atomically(self):
        finalized = self.complete_record()
        response = self.client.post(
            f"/api/consultations/{self.consultation.id}/doctor-transition/",
            {
                "action": "transfer",
                "outcome": "transferred",
                "medical_record_id": finalized.data["id"],
                "confirmation": True,
                "reason": "Synthetic transfer reason for eligibility.",
                "target_doctor_id": str(self.other_doctor.id),
                "expected_status": ConsultationStatus.UNDER_REVIEW,
                "client_request_id": str(uuid4()),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.other_doctor_user)
        detail = self.client.get(f"/api/doctors/me/medical-records/{finalized.data['id']}/")
        self.assertEqual(detail.status_code, status.HTTP_200_OK)

    def test_doctor_routes_deny_pending_patient_and_anonymous(self):
        for user in (self.pending_user, self.patient_user, None):
            self.client.force_authenticate(user)
            response = self.client.get("/api/doctors/me/medical-records/")
            self.assertIn(response.status_code, {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN})
