"""PostgreSQL-only Doctor Phase D concurrency closure."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.consultations.models import Consultation, ConsultationStatus
from apps.core.models import AuditEvent
from apps.doctors.models import DoctorProfile
from apps.notifications.models import Notification
from apps.patients.models import PatientProfile
from apps.privacy.models import AccountDeletionRequest, DataExportRequest
from apps.reviews.models import (
    ConsultationReview,
    DoctorReviewResponse,
    ReviewResponseAction,
    ReviewStatus,
)
from apps.specialties.models import Specialty


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DoctorPhaseDPostgresConcurrencyTests(TransactionTestCase):
    reset_sequences = False

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL required for Doctor Phase D row-lock acceptance")
        specialty = Specialty.objects.create(
            name="Synthetic Phase D concurrency",
            name_en="Synthetic Phase D concurrency",
            slug=f"doctor-phase-d-concurrency-{uuid4()}",
        )
        self.doctor_user = User.objects.create_user(
            email=f"doctor-phase-d-{uuid4()}@example.test",
            role=UserRole.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(
            user=self.doctor_user,
            specialty=specialty,
            license_number=f"SYN-D-{uuid4()}",
            is_approved=True,
            approval_status=DoctorProfile.ApprovalStatus.APPROVED,
        )
        patient_user = User.objects.create_user(
            email=f"patient-phase-d-{uuid4()}@example.test",
            role=UserRole.PATIENT,
        )
        patient = PatientProfile.objects.create(user=patient_user)
        consultation = Consultation.objects.create(
            patient=patient,
            doctor=self.doctor,
            specialty=specialty,
            status=ConsultationStatus.COMPLETED,
        )
        self.review = ConsultationReview.objects.create(
            consultation=consultation,
            reviewer=patient,
            rating=5,
            status=ReviewStatus.PUBLISHED,
        )

    def request(self, barrier, method, path, payload):
        close_old_connections()
        user = User.objects.get(pk=self.doctor_user.id)
        client = APIClient()
        client.force_authenticate(user)
        barrier.wait(timeout=10)
        response = getattr(client, method)(path, payload, format="json")
        result = (response.status_code, response.data.get("code"))
        close_old_connections()
        return result

    def concurrent(self, method, path, payloads):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(
                executor.map(
                    lambda payload: self.request(barrier, method, path, payload),
                    payloads,
                )
            )

    def test_duplicate_review_response_has_one_side_effect_set(self):
        path = f"/api/doctors/me/reviews/{self.review.id}/response/"
        results = self.concurrent(
            "post",
            path,
            [
                {
                    "body": "Synthetic bounded public response.",
                    "client_request_id": str(uuid4()),
                }
                for _ in range(2)
            ],
        )
        self.assertEqual(sorted(status for status, _ in results), [201, 409])
        self.assertEqual(DoctorReviewResponse.objects.filter(review=self.review).count(), 1)
        self.assertEqual(ReviewResponseAction.objects.filter(review=self.review).count(), 1)
        self.assertEqual(
            AuditEvent.objects.filter(event_type="doctor_review_response_created").count(),
            1,
        )
        self.assertEqual(Notification.objects.filter(recipient=self.review.reviewer.user).count(), 1)

    def test_stale_review_response_edit_accepts_one_version(self):
        client = APIClient()
        client.force_authenticate(self.doctor_user)
        path = f"/api/doctors/me/reviews/{self.review.id}/response/"
        created = client.post(
            path,
            {
                "body": "Synthetic initial public response.",
                "client_request_id": str(uuid4()),
            },
            format="json",
        )
        expected = created.data["response"]["updated_at"]
        results = self.concurrent(
            "patch",
            path,
            [
                {
                    "body": f"Synthetic concurrent public response {index}.",
                    "expected_updated_at": expected,
                    "client_request_id": str(uuid4()),
                }
                for index in range(2)
            ],
        )
        self.assertEqual(sorted(status for status, _ in results), [200, 409])
        self.assertEqual(ReviewResponseAction.objects.filter(review=self.review).count(), 2)
        self.assertEqual(
            AuditEvent.objects.filter(event_type="doctor_review_response_updated").count(),
            1,
        )

    def test_duplicate_export_request_creates_one_active_request(self):
        results = self.concurrent(
            "post",
            "/api/doctors/me/privacy/exports/",
            [{}, {}],
        )
        self.assertEqual(sorted(status for status, _ in results), [201, 409])
        self.assertEqual(DataExportRequest.objects.filter(subject_user=self.doctor_user).count(), 1)
        self.assertEqual(
            AuditEvent.objects.filter(event_type="privacy.export.requested").count(),
            0,
        )

    def test_duplicate_deletion_request_creates_one_active_request(self):
        results = self.concurrent(
            "post",
            "/api/doctors/me/privacy/deletion/",
            [
                {
                    "reason": f"Synthetic concurrent closure reason {index}.",
                    "confirmation": True,
                }
                for index in range(2)
            ],
        )
        self.assertEqual(sorted(status for status, _ in results), [201, 409])
        self.assertEqual(
            AccountDeletionRequest.objects.filter(subject_user=self.doctor_user).count(),
            1,
        )
        self.assertEqual(
            AuditEvent.objects.filter(event_type="privacy.deletion.requested").count(),
            1,
        )
