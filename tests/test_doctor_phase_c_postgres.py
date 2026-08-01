"""PostgreSQL-only Doctor Phase C row-lock acceptance."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.consultations.models import Consultation, ConsultationStatus, DoctorConsultationAction
from apps.core.models import AuditEvent
from apps.doctors.models import DoctorProfile
from apps.medical_records.models import MedicalRecordAction, MedicalRecordDraft, RecordStatus
from apps.notifications.models import Notification
from apps.patients.models import PatientProfile
from apps.specialties.models import Specialty


class DoctorPhaseCPostgresConcurrencyTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL required for Doctor Phase C row-lock acceptance")
        self.specialty = Specialty.objects.create(name="Synthetic Phase C", name_en="Synthetic Phase C", slug=f"phase-c-{uuid4()}")
        self.patient_user = User.objects.create_user(email=f"phase-c-patient-{uuid4()}@example.test", role=UserRole.PATIENT)
        self.patient = PatientProfile.objects.create(user=self.patient_user)
        self.doctor_user = User.objects.create_user(email=f"phase-c-doctor-{uuid4()}@example.test", role=UserRole.DOCTOR)
        self.doctor = DoctorProfile.objects.create(user=self.doctor_user, specialty=self.specialty, professional_title="Synthetic doctor", license_number=f"SYN-C-{uuid4()}", is_approved=True, approval_status=DoctorProfile.ApprovalStatus.APPROVED)
        self.consultation = Consultation.objects.create(patient=self.patient, doctor=self.doctor, specialty=self.specialty, status=ConsultationStatus.DOCTOR_REVIEW, description="Synthetic concurrency fixture.")

    def request(self, barrier, method, path, payload):
        close_old_connections()
        client = APIClient()
        client.force_authenticate(User.objects.get(pk=self.doctor_user.id))
        barrier.wait(timeout=10)
        response = getattr(client, method)(path, payload, format="json")
        result = response.status_code, response.data.get("code"), response.data.get("id")
        close_old_connections()
        return result

    def test_concurrent_create_returns_one_record(self):
        barrier = Barrier(2)
        path = f"/api/consultations/{self.consultation.id}/medical-record/"
        payloads = [{"client_request_id": str(uuid4())} for _ in range(2)]
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda payload: self.request(barrier, "post", path, payload), payloads))
        self.assertEqual(sorted(status for status, _, _ in results), [200, 201])
        self.assertEqual(MedicalRecordDraft.objects.filter(consultation=self.consultation).count(), 1)
        self.assertEqual(MedicalRecordAction.objects.filter(record__consultation=self.consultation, action="create").count(), 2)
        self.assertEqual(AuditEvent.objects.filter(event_type="doctor_medical_record_created", target_id=str(MedicalRecordDraft.objects.get(consultation=self.consultation).id)).count(), 1)

    def test_concurrent_updates_accept_one_version(self):
        record = MedicalRecordDraft.objects.create(consultation=self.consultation, created_by=self.doctor_user)
        barrier = Barrier(2)
        path = f"/api/doctors/me/medical-records/{record.id}/"
        payloads = [{"doctor_authored": {"assessment": value}, "expected_version": 1, "client_request_id": str(uuid4())} for value in ("Synthetic assessment one", "Synthetic assessment two")]
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda payload: self.request(barrier, "patch", path, payload), payloads))
        record.refresh_from_db()
        self.assertEqual(sorted(status for status, _, _ in results), [200, 409])
        self.assertEqual(record.version, 2)
        self.assertIn(record.assessment, {"Synthetic assessment one", "Synthetic assessment two"})
        self.assertEqual(AuditEvent.objects.filter(event_type="doctor_medical_record_updated", target_id=str(record.id)).count(), 1)

    def test_concurrent_finalize_has_one_side_effect_set(self):
        record = MedicalRecordDraft.objects.create(consultation=self.consultation, created_by=self.doctor_user, clinical_summary="Synthetic summary", patient_instructions="Synthetic instructions", recommendations="Synthetic recommendation")
        barrier = Barrier(2)
        path = f"/api/doctors/me/medical-records/{record.id}/finalize/"
        payloads = [{"expected_version": 1, "client_request_id": str(uuid4()), "confirmation": True} for _ in range(2)]
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda payload: self.request(barrier, "post", path, payload), payloads))
        record.refresh_from_db()
        self.assertEqual(sorted(status for status, _, _ in results), [200, 409])
        self.assertEqual(record.status, RecordStatus.FINALIZED)
        self.assertEqual(Notification.objects.filter(recipient=self.patient_user, notification_type="record_finalized").count(), 1)
        self.assertEqual(AuditEvent.objects.filter(event_type="doctor_medical_record_finalized", target_id=str(record.id)).count(), 1)

    def test_finalize_racing_completion_never_completes_unfinalized_record(self):
        record = MedicalRecordDraft.objects.create(consultation=self.consultation, created_by=self.doctor_user, clinical_summary="Synthetic summary", patient_instructions="Synthetic instructions", recommendations="Synthetic recommendation")
        barrier = Barrier(2)
        tasks = [
            (f"/api/doctors/me/medical-records/{record.id}/finalize/", {"expected_version": 1, "client_request_id": str(uuid4()), "confirmation": True}),
            (f"/api/consultations/{self.consultation.id}/doctor-transition/", {"action": "complete", "reason": "Synthetic completion.", "outcome": "remote_care_completed", "medical_record_id": str(record.id), "confirmation": True, "expected_status": ConsultationStatus.DOCTOR_REVIEW, "client_request_id": str(uuid4())}),
        ]
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda task: self.request(barrier, "post", task[0], task[1]), tasks))
        record.refresh_from_db()
        self.consultation.refresh_from_db()
        self.assertEqual(record.status, RecordStatus.FINALIZED)
        if self.consultation.status == ConsultationStatus.COMPLETED:
            self.assertEqual(record.clinical_outcome, "remote_care_completed")
            self.assertEqual(DoctorConsultationAction.objects.filter(consultation=self.consultation, action="complete").count(), 1)
        else:
            self.assertEqual(self.consultation.status, ConsultationStatus.DOCTOR_REVIEW)
            self.assertIn(409, [status for status, _, _ in results])
