"""PostgreSQL-only Doctor Phase B row-lock acceptance."""

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
from apps.medical_records.models import MedicalRecordDraft, RecordStatus
from apps.notifications.models import Notification
from apps.patients.models import PatientProfile
from apps.specialties.models import Specialty


class DoctorPhaseBPostgresConcurrencyTests(TransactionTestCase):
    reset_sequences = False

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL required for Doctor Phase B row-lock acceptance")
        self.specialty = Specialty.objects.create(
            name="Synthetic concurrency specialty",
            name_en="Synthetic concurrency specialty",
            name_ar="تخصص تزامن تجريبي",
            name_ckb="پسپۆڕی هاوکاتی تاقیکردنەوە",
            slug=f"doctor-phase-b-concurrency-{uuid4()}",
        )
        self.patient_user = User.objects.create_user(
            email=f"phase-b-patient-{uuid4()}@example.test",
            role=UserRole.PATIENT,
        )
        self.patient = PatientProfile.objects.create(user=self.patient_user)
        self.doctor_user = User.objects.create_user(
            email=f"phase-b-doctor-{uuid4()}@example.test",
            role=UserRole.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(
            user=self.doctor_user,
            specialty=self.specialty,
            professional_title="Synthetic concurrency doctor",
            license_number=f"SYN-{uuid4()}",
            is_approved=True,
            approval_status=DoctorProfile.ApprovalStatus.APPROVED,
            is_accepting_consultations=True,
        )

    def consultation(self, status=ConsultationStatus.SUBMITTED):
        return Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            specialty=self.specialty,
            status=status,
            description="Synthetic concurrency fixture only.",
        )

    def post_as(self, barrier, user_id, path, payload):
        close_old_connections()
        user = User.objects.get(pk=user_id)
        client = APIClient()
        client.force_authenticate(user)
        barrier.wait(timeout=10)
        response = client.post(path, payload, format="json")
        result = (response.status_code, response.data.get("code"))
        close_old_connections()
        return result

    def test_concurrent_accept_creates_single_side_effect_set(self):
        consultation = self.consultation()
        barrier = Barrier(2)
        path = f"/api/consultations/{consultation.id}/accept/"
        payloads = [
            {
                "expected_status": ConsultationStatus.SUBMITTED,
                "client_request_id": str(uuid4()),
            }
            for _ in range(2)
        ]
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(
                lambda payload: self.post_as(
                    barrier, self.doctor_user.id, path, payload
                ),
                payloads,
            ))
        consultation.refresh_from_db()
        self.assertEqual(consultation.status, ConsultationStatus.ACCEPTED)
        self.assertEqual(sorted(code for code, _ in results), [200, 409])
        self.assertEqual(DoctorConsultationAction.objects.filter(consultation=consultation).count(), 1)
        self.assertEqual(Notification.objects.filter(consultation=consultation).count(), 1)
        self.assertEqual(AuditEvent.objects.filter(event_type="doctor_consultation_accept", target_id=str(consultation.id)).count(), 1)

    def test_accept_racing_cancellation_has_one_terminal_mutation(self):
        consultation = self.consultation()
        barrier = Barrier(2)
        tasks = [
            (self.doctor_user.id, f"/api/consultations/{consultation.id}/accept/", {
                "expected_status": ConsultationStatus.SUBMITTED,
                "client_request_id": str(uuid4()),
            }),
            (self.patient_user.id, f"/api/consultations/{consultation.id}/cancel/", {
                "expected_status": ConsultationStatus.SUBMITTED,
                "reason": "Synthetic cancellation during concurrency acceptance test.",
            }),
        ]
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(
                lambda task: self.post_as(barrier, task[0], task[1], task[2]),
                tasks,
            ))
        consultation.refresh_from_db()
        self.assertIn(consultation.status, {ConsultationStatus.ACCEPTED, ConsultationStatus.CANCELLED})
        self.assertEqual(sorted(code for code, _ in results), [200, 409])
        self.assertEqual(
            DoctorConsultationAction.objects.filter(consultation=consultation).count()
            + AuditEvent.objects.filter(event_type="patient_consultation_cancelled", target_id=str(consultation.id)).count(),
            1,
        )

    def test_conflicting_doctor_transitions_serialize(self):
        consultation = self.consultation(ConsultationStatus.DOCTOR_REVIEW)
        record = MedicalRecordDraft.objects.create(
            consultation=consultation,
            status=RecordStatus.FINALIZED,
        )
        barrier = Barrier(2)
        path = f"/api/consultations/{consultation.id}/doctor-transition/"
        payloads = [
            {
                "action": action,
                "reason": "Synthetic concurrency transition reason.",
                "expected_status": ConsultationStatus.DOCTOR_REVIEW,
                "client_request_id": str(uuid4()),
                "outcome": (
                    "follow_up_required"
                    if action == "require_follow_up"
                    else "physical_visit_required"
                ),
                "medical_record_id": str(record.id),
                "confirmation": True,
            }
            for action in ("require_follow_up", "require_physical_visit")
        ]
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(
                lambda payload: self.post_as(barrier, self.doctor_user.id, path, payload),
                payloads,
            ))
        consultation.refresh_from_db()
        self.assertIn(consultation.status, {ConsultationStatus.FOLLOW_UP_REQUIRED, ConsultationStatus.PHYSICAL_VISIT_REQUIRED})
        self.assertEqual(sorted(code for code, _ in results), [200, 409])
        self.assertEqual(DoctorConsultationAction.objects.filter(consultation=consultation).count(), 1)
