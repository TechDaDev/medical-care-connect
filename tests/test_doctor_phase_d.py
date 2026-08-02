"""Doctor Phase D API acceptance: ownership, safety, conflicts, and bounds."""

from datetime import timedelta
from uuid import uuid4

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User, UserRole
from apps.consultations.models import Consultation, ConsultationStatus, Priority
from apps.core.models import AuditEvent
from apps.doctors.models import DoctorProfile
from apps.messaging.models import ConsultationMessage
from apps.notifications.models import Notification, NotificationType
from apps.patients.models import PatientProfile
from apps.privacy.models import AccountDeletionRequest, DataExportRequest, ExportStatus
from apps.reviews.models import ConsultationReview, DoctorReviewResponse, ReviewResponseAction, ReviewStatus
from apps.specialties.models import Specialty


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DoctorPhaseDTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.specialty = Specialty.objects.create(
            name="Synthetic Phase D", name_en="Synthetic Phase D",
            name_ar="تخصص اصطناعي", name_ckb="پسپۆڕیی دەستکرد",
            slug="doctor-phase-d",
        )
        cls.doctor_user = User.objects.create_user(
            email="doctor-d@example.test", role=UserRole.DOCTOR,
            first_name="Synthetic", last_name="Doctor",
        )
        cls.doctor = DoctorProfile.objects.create(
            user=cls.doctor_user, specialty=cls.specialty,
            license_number="SYN-D-PHASE-D", is_approved=True,
            approval_status=DoctorProfile.ApprovalStatus.APPROVED,
        )
        cls.other_user = User.objects.create_user(email="other-d@example.test", role=UserRole.DOCTOR)
        cls.other_doctor = DoctorProfile.objects.create(
            user=cls.other_user, specialty=cls.specialty,
            license_number="SYN-D-PHASE-D-OTHER", is_approved=True,
            approval_status=DoctorProfile.ApprovalStatus.APPROVED,
        )
        cls.pending_user = User.objects.create_user(email="pending-d@example.test", role=UserRole.DOCTOR)
        DoctorProfile.objects.create(
            user=cls.pending_user, specialty=cls.specialty,
            license_number="SYN-D-PHASE-D-PENDING",
        )
        cls.patient_user = User.objects.create_user(
            email="patient-d@example.test", role=UserRole.PATIENT,
            first_name="Synthetic", last_name="Patient",
        )
        cls.patient = PatientProfile.objects.create(user=cls.patient_user)
        cls.consultation = Consultation.objects.create(
            patient=cls.patient, doctor=cls.doctor, specialty=cls.specialty,
            status=ConsultationStatus.AWAITING_DOCTOR_RESPONSE, priority=Priority.URGENT,
        )
        cls.other_consultation = Consultation.objects.create(
            patient=cls.patient, doctor=cls.other_doctor, specialty=cls.specialty,
            status=ConsultationStatus.COMPLETED,
        )
        cls.message = ConsultationMessage.objects.create(
            consultation=cls.consultation, sender=cls.patient_user,
            content="Synthetic bounded message preview only.",
        )
        ConsultationMessage.objects.create(
            consultation=cls.other_consultation, sender=cls.patient_user,
            content="Other doctor synthetic content.",
        )
        cls.review = ConsultationReview.objects.create(
            consultation=cls.consultation, reviewer=cls.patient, rating=5,
            body="Synthetic review body.", is_anonymous=True, status=ReviewStatus.PUBLISHED,
        )
        cls.other_review = ConsultationReview.objects.create(
            consultation=cls.other_consultation, reviewer=cls.patient, rating=2,
            body="Other doctor review.", status=ReviewStatus.PUBLISHED,
        )

    def setUp(self):
        self.client.force_authenticate(self.doctor_user)

    def test_message_threads_are_owned_safe_ordered_paginated_and_query_bounded(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(
                "/api/doctors/me/message-threads/?page_size=20&group=active",
                HTTP_ACCEPT_LANGUAGE="ar",
            )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 1, [query["sql"] for query in queries.captured_queries])
        self.assertEqual(len(queries), 2)
        item = response.data["results"][0]
        self.assertEqual(item["consultation_id"], str(self.consultation.id))
        self.assertTrue(item["patient_awaiting_response"])
        self.assertEqual(item["specialty"]["name"], "تخصص اصطناعي")
        self.assertGreater(item["unread_count"], 0)
        self.assertNotIn("email", str(item))
        self.assertNotIn("phone", str(item))
        completed = Consultation.objects.create(
            patient=self.patient, doctor=self.doctor, specialty=self.specialty,
            status=ConsultationStatus.COMPLETED,
        )
        ConsultationMessage.objects.create(
            consultation=completed, sender=self.doctor_user,
            content="Synthetic closed conversation.",
        )
        closed = self.client.get("/api/doctors/me/message-threads/?group=closed")
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.data["count"], 1)
        self.assertEqual(closed.data["results"][0]["consultation_id"], str(completed.id))

    def test_doctor_access_state_applies_to_phase_d_endpoints(self):
        for user, expected in ((self.pending_user, 403), (self.patient_user, 403), (None, 401)):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get("/api/doctors/me/reviews/").status_code, expected)

    def test_notification_projection_safe_read_actions_and_ownership(self):
        own = Notification.objects.create(
            recipient=self.doctor_user, consultation=self.consultation,
            notification_type=NotificationType.NEW_MESSAGE,
            title="Synthetic notification", body="Synthetic in-app notice.",
        )
        other = Notification.objects.create(
            recipient=self.other_user, consultation=self.other_consultation,
            notification_type=NotificationType.NEW_MESSAGE,
            title="Other", body="Other notice.",
        )
        listed = self.client.get("/api/doctors/me/notifications/?unread=true")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data["count"], 1)
        self.assertEqual(listed.data["results"][0]["link"]["path"], f"/app/doctor/messages/{self.consultation.id}")
        self.assertNotIn("channel", listed.data["results"][0])
        self.assertEqual(self.client.post(f"/api/doctors/me/notifications/{other.id}/read/").status_code, 404)
        self.assertEqual(self.client.post(f"/api/doctors/me/notifications/{own.id}/read/").status_code, 200)
        self.assertEqual(self.client.post("/api/doctors/me/notifications/read-all/").status_code, 200)

    def test_reviews_hide_anonymous_identity_and_other_doctor_data(self):
        response = self.client.get("/api/doctors/me/reviews/?awaiting_response=true")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertIsNone(response.data["results"][0]["reviewer_display_name"])
        self.assertEqual(response.data["summary"]["total_published"], 1)
        self.assertNotIn("moderation_reason", str(response.data))

    def test_review_response_is_owned_idempotent_audited_and_conflict_safe(self):
        request_id = uuid4()
        url = f"/api/doctors/me/reviews/{self.review.id}/response/"
        payload = {"body": "Thank you for your synthetic feedback.", "client_request_id": str(request_id)}
        first = self.client.post(url, payload, format="json")
        replay = self.client.post(url, payload, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(DoctorReviewResponse.objects.filter(review=self.review).count(), 1)
        self.assertEqual(ReviewResponseAction.objects.filter(review=self.review).count(), 1)
        event = AuditEvent.objects.get(event_type="doctor_review_response_created")
        self.assertNotIn(payload["body"], str(event.metadata))
        denied = self.client.post(
            f"/api/doctors/me/reviews/{self.other_review.id}/response/",
            {**payload, "client_request_id": str(uuid4())}, format="json",
        )
        self.assertEqual(denied.status_code, 404)

    def test_review_response_update_uses_edit_window_and_optimistic_conflict(self):
        created = self.client.post(
            f"/api/doctors/me/reviews/{self.review.id}/response/",
            {"body": "Thank you for your synthetic feedback.", "client_request_id": str(uuid4())},
            format="json",
        )
        response_data = created.data["response"]
        url = f"/api/doctors/me/reviews/{self.review.id}/response/"
        payload = {
            "body": "Updated synthetic public response.",
            "expected_updated_at": response_data["updated_at"],
            "client_request_id": str(uuid4()),
        }
        updated = self.client.patch(url, payload, format="json")
        stale = self.client.patch(url, {**payload, "client_request_id": str(uuid4())}, format="json")
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.data["code"], "response_changed")
        DoctorReviewResponse.objects.filter(review=self.review).update(created_at=timezone.now() - timedelta(hours=73))
        closed = self.client.patch(url, {**payload, "client_request_id": str(uuid4())}, format="json")
        self.assertEqual(closed.status_code, 409)
        self.assertEqual(closed.data["code"], "response_edit_window_closed")

    def test_profile_integration_exposes_safe_completeness_and_links(self):
        response = self.client.get("/api/doctors/me/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("completeness", response.data)
        self.assertEqual(response.data["links"]["privacy"], "/app/doctor/privacy")
        self.assertNotIn("license_number", response.data)

    def test_privacy_requests_are_owned_non_destructive_and_conflict_safe(self):
        export = self.client.post("/api/doctors/me/privacy/exports/", {}, format="json")
        duplicate = self.client.post("/api/doctors/me/privacy/exports/", {}, format="json")
        self.assertEqual(export.status_code, 201)
        self.assertEqual(duplicate.status_code, 409)
        self.assertNotIn("storage_key", export.data)
        other_export = DataExportRequest.objects.create(
            requested_by=self.other_user, subject_user=self.other_user, status=ExportStatus.COMPLETED,
        )
        self.assertEqual(self.client.get(f"/api/doctors/me/privacy/exports/{other_export.id}/download/").status_code, 404)
        deletion = self.client.post(
            "/api/doctors/me/privacy/deletion/",
            {"reason": "Synthetic account closure request.", "confirmation": True}, format="json",
        )
        duplicate_deletion = self.client.post(
            "/api/doctors/me/privacy/deletion/",
            {"reason": "Another synthetic closure request.", "confirmation": True}, format="json",
        )
        self.assertEqual(deletion.status_code, 201)
        self.assertEqual(duplicate_deletion.status_code, 409)
        self.doctor_user.refresh_from_db()
        self.assertTrue(self.doctor_user.is_active)
        event = AuditEvent.objects.get(event_type="privacy.deletion.requested")
        self.assertNotIn("Synthetic account", str(event.metadata))
        cancelled = self.client.post(f"/api/doctors/me/privacy/deletion/{deletion.data['id']}/cancel/")
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.data["status"], "cancelled")

    def test_privacy_overview_and_histories_are_bounded(self):
        overview = self.client.get("/api/doctors/me/privacy/")
        exports = self.client.get("/api/doctors/me/privacy/exports/?page_size=50")
        deletions = self.client.get("/api/doctors/me/privacy/deletion/?page_size=50")
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(exports.status_code, 200)
        self.assertEqual(deletions.status_code, 200)
        self.assertTrue(overview.data["retention"]["clinical_records_may_be_retained"])

    def test_phase_d_lists_have_stable_measured_query_counts(self):
        Notification.objects.create(
            recipient=self.doctor_user,
            notification_type=NotificationType.REVIEW_AVAILABLE,
            title="Synthetic query fixture",
            body="Synthetic in-app notice.",
        )
        DataExportRequest.objects.create(
            requested_by=self.doctor_user,
            subject_user=self.doctor_user,
            status=ExportStatus.EXPIRED,
        )
        AccountDeletionRequest.objects.create(
            requested_by=self.doctor_user,
            subject_user=self.doctor_user,
            reason="Synthetic query-count fixture.",
            status="cancelled",
        )
        cases = (
            ("/api/doctors/me/", 1),
            ("/api/doctors/me/notifications/", 3),
            ("/api/doctors/me/reviews/", 3),
            ("/api/doctors/me/privacy/", 2),
            ("/api/doctors/me/privacy/exports/", 2),
            ("/api/doctors/me/privacy/deletion/", 2),
        )
        for url, expected in cases:
            with self.subTest(url=url), CaptureQueriesContext(connection) as queries:
                response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(queries), expected, [item["sql"] for item in queries.captured_queries])
