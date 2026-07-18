"""Tests for the reviews app — Phase 11."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User, UserRole
from apps.consultations.models import Consultation, ConsultationStatus, Priority
from apps.doctors.models import DoctorProfile
from apps.patients.models import PatientProfile
from apps.reviews.models import ConsultationReview, ReviewReport, ReviewStatus
from apps.specialties.models import Specialty


class ReviewAPITestCase(TestCase):
    """Base test case with common setup."""

    @classmethod
    def setUpTestData(cls):
        # Users
        cls.patient_user = User.objects.create_user(
            email="patient@test.com", password="testpass123",
            first_name="Test", last_name="Patient", role=UserRole.PATIENT,
        )
        cls.doctor_user = User.objects.create_user(
            email="doctor@test.com", password="testpass123",
            first_name="Test", last_name="Doctor", role=UserRole.DOCTOR,
        )
        cls.admin_user = User.objects.create_user(
            email="admin@test.com", password="testpass123",
            first_name="Admin", last_name="User", role=UserRole.ADMINISTRATOR,
        )
        cls.coord_user = User.objects.create_user(
            email="coord@test.com", password="testpass123",
            first_name="Coord", last_name="User", role=UserRole.COORDINATOR,
        )
        cls.other_patient = User.objects.create_user(
            email="other@test.com", password="testpass123",
            first_name="Other", last_name="Patient", role=UserRole.PATIENT,
        )

        # Profiles
        spec = Specialty.objects.create(name="TestCardiology")
        cls.doctor = DoctorProfile.objects.create(
            user=cls.doctor_user, specialty=spec,
            license_number="DOC001",
            is_approved=True, is_accepting_consultations=True,
        )
        cls.patient = PatientProfile.objects.create(user=cls.patient_user)
        cls.other_patient_profile = PatientProfile.objects.create(user=cls.other_patient)

        # Completed consultation
        cls.consultation = Consultation.objects.create(
            patient=cls.patient, doctor=cls.doctor, specialty=spec,
            status=ConsultationStatus.COMPLETED,
        )
        # Non-completed consultation
        cls.active_consultation = Consultation.objects.create(
            patient=cls.patient, doctor=cls.doctor, specialty=spec,
            status=ConsultationStatus.ACCEPTED,
        )

    def setUp(self):
        self.client = APIClient()

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def _url_review(self, consultation_id):
        return f"/api/reviews/consultations/{consultation_id}/review/"

    def _url_review_edit(self, consultation_id):
        return f"/api/reviews/consultations/{consultation_id}/review/edit/"

    def _url_doctor_reviews(self, doctor_id):
        return f"/api/reviews/doctors/{doctor_id}/reviews/"

    def _url_doctor_reputation(self, doctor_id):
        return f"/api/reviews/doctors/{doctor_id}/reputation/"

    def _url_response(self, review_id):
        return f"/api/reviews/reviews/{review_id}/response/"

    def _url_report(self, review_id):
        return f"/api/reviews/reviews/{review_id}/report/"

    def _url_staff_reviews(self):
        return "/api/staff/reviews/"

    def _url_staff_moderate(self, review_id):
        return f"/api/staff/reviews/{review_id}/moderate/"

    def _url_staff_reports(self):
        return "/api/staff/reviews/reports/"

    def _url_staff_resolve(self, report_id):
        return f"/api/staff/reviews/reports/{report_id}/resolve/"


# ── Create Review ───────────────────────────────────────────────────────────


class CreateReviewTests(ReviewAPITestCase):
    def test_unauthenticated_cannot_create(self):
        resp = self.client.post(self._url_review(self.consultation.id), {"rating": 5})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_patient_can_create_review(self):
        self._auth(self.patient_user)
        resp = self.client.post(self._url_review(self.consultation.id), {
            "rating": 5, "title": "Great!", "body": "Excellent doctor", "is_anonymous": False,
        })
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["rating"] == 5
        assert resp.data["status"] == ReviewStatus.PUBLISHED

    def test_duplicate_review_blocked(self):
        self._auth(self.patient_user)
        self.client.post(self._url_review(self.consultation.id), {"rating": 4})
        resp = self.client.post(self._url_review(self.consultation.id), {"rating": 5})
        assert resp.status_code == status.HTTP_409_CONFLICT

    def test_cannot_review_non_completed_consultation(self):
        self._auth(self.patient_user)
        resp = self.client.post(self._url_review(self.active_consultation.id), {"rating": 3})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_review_others_consultation(self):
        self._auth(self.other_patient)
        resp = self.client.post(self._url_review(self.consultation.id), {"rating": 5})
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_doctor_cannot_create_review(self):
        self._auth(self.doctor_user)
        resp = self.client.post(self._url_review(self.consultation.id), {"rating": 5})
        assert resp.status_code in (status.HTTP_403_FORBIDDEN,)

    def test_rating_validation(self):
        self._auth(self.patient_user)
        resp = self.client.post(self._url_review(self.consultation.id), {"rating": 6})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        resp = self.client.post(self._url_review(self.consultation.id), {"rating": 0})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


# ── Get Review ──────────────────────────────────────────────────────────────


class GetReviewTests(ReviewAPITestCase):
    def test_get_existing_review(self):
        self._auth(self.patient_user)
        self.client.post(self._url_review(self.consultation.id), {"rating": 4})
        resp = self.client.get(self._url_review(self.consultation.id))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["rating"] == 4

    def test_get_nonexistent_review(self):
        self._auth(self.patient_user)
        resp = self.client.get(self._url_review(self.consultation.id))
        assert resp.status_code == status.HTTP_404_NOT_FOUND


# ── Update / Delete Review ──────────────────────────────────────────────────


class UpdateReviewTests(ReviewAPITestCase):
    def test_update_within_window(self):
        self._auth(self.patient_user)
        self.client.post(self._url_review(self.consultation.id), {"rating": 3})
        resp = self.client.patch(self._url_review_edit(self.consultation.id), {"rating": 5})
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["rating"] == 5

    def test_delete_within_window(self):
        self._auth(self.patient_user)
        self.client.post(self._url_review(self.consultation.id), {"rating": 3})
        resp = self.client.delete(self._url_review_edit(self.consultation.id))
        assert resp.status_code == status.HTTP_204_NO_CONTENT

    def test_cannot_update_others_review(self):
        self._auth(self.other_patient)
        r = self.client.post(self._url_review(self.consultation.id), {"rating": 2})
        # other patient doesn't own this consultation
        assert r.status_code == status.HTTP_403_FORBIDDEN


# ── Doctor Reviews (public) ─────────────────────────────────────────────────


class DoctorReviewsTests(ReviewAPITestCase):
    def test_published_reviews_visible(self):
        self._auth(self.patient_user)
        self.client.post(self._url_review(self.consultation.id), {"rating": 5, "title": "Great!"})
        # Other patient creates completed consultation + review
        other_consult = Consultation.objects.create(
            patient=self.other_patient_profile, doctor=self.doctor,
            status=ConsultationStatus.COMPLETED,
        )
        self._auth(self.other_patient)
        self.client.post(self._url_review(other_consult.id), {"rating": 4, "title": "Good"})

        self._auth(self.patient_user)
        resp = self.client.get(self._url_doctor_reviews(self.doctor.id))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["count"] == 2


# ── Doctor Reputation ───────────────────────────────────────────────────────


class DoctorReputationTests(ReviewAPITestCase):
    def test_reputation_aggregation(self):
        self._auth(self.patient_user)
        self.client.post(self._url_review(self.consultation.id), {"rating": 4})

        resp = self.client.get(self._url_doctor_reputation(self.doctor.id))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["average_rating"] == 4.0
        assert resp.data["total_reviews"] == 1
        assert resp.data["rating_distribution"]["4"] == 1

    def test_no_reviews(self):
        self._auth(self.patient_user)
        resp = self.client.get(self._url_doctor_reputation(self.doctor.id))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["total_reviews"] == 0


# ── Doctor Response ─────────────────────────────────────────────────────────


class DoctorResponseTests(ReviewAPITestCase):
    def test_doctor_can_respond(self):
        self._auth(self.patient_user)
        r = self.client.post(self._url_review(self.consultation.id), {"rating": 4})
        review_id = r.data["id"]

        self._auth(self.doctor_user)
        resp = self.client.post(self._url_response(review_id), {"body": "Thank you!"})
        assert resp.status_code == status.HTTP_201_CREATED

    def test_doctor_cannot_respond_to_other_doctors_review(self):
        self._auth(self.patient_user)
        r = self.client.post(self._url_review(self.consultation.id), {"rating": 4})
        review_id = r.data["id"]

        other_doc_user = User.objects.create_user(
            email="otherdoc@test.com", password="testpass123", role=UserRole.DOCTOR,
        )
        spec = Specialty.objects.first()
        DoctorProfile.objects.create(
            user=other_doc_user, specialty=spec,
            license_number="DOC002", is_approved=True,
        )
        self._auth(other_doc_user)
        resp = self.client.post(self._url_response(review_id), {"body": "Thanks!"})
        assert resp.status_code == status.HTTP_403_FORBIDDEN


# ── Report Review ───────────────────────────────────────────────────────────


class ReportReviewTests(ReviewAPITestCase):
    def test_report_review(self):
        self._auth(self.patient_user)
        r = self.client.post(self._url_review(self.consultation.id), {"rating": 3})
        review_id = r.data["id"]

        self._auth(self.doctor_user)
        resp = self.client.post(self._url_report(review_id), {
            "reason": "inappropriate", "description": "Not accurate",
        })
        assert resp.status_code == status.HTTP_201_CREATED

    def test_duplicate_report_blocked(self):
        self._auth(self.patient_user)
        r = self.client.post(self._url_review(self.consultation.id), {"rating": 3})
        review_id = r.data["id"]

        self._auth(self.doctor_user)
        self.client.post(self._url_report(review_id), {"reason": "spam"})
        resp = self.client.post(self._url_report(review_id), {"reason": "fake"})
        assert resp.status_code == status.HTTP_409_CONFLICT


# ── Staff Moderation ────────────────────────────────────────────────────────


class StaffModerationTests(ReviewAPITestCase):
    def test_staff_can_moderate_review(self):
        self._auth(self.patient_user)
        r = self.client.post(self._url_review(self.consultation.id), {"rating": 3})
        review_id = r.data["id"]

        self._auth(self.admin_user)
        resp = self.client.patch(self._url_staff_moderate(review_id), {
            "status": ReviewStatus.HIDDEN,
            "moderation_reason": "Under review",
        })
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["status"] == ReviewStatus.HIDDEN

    def test_non_staff_cannot_moderate(self):
        self._auth(self.patient_user)
        r = self.client.post(self._url_review(self.consultation.id), {"rating": 3})
        review_id = r.data["id"]

        self._auth(self.doctor_user)
        resp = self.client.patch(self._url_staff_moderate(review_id), {"status": ReviewStatus.HIDDEN})
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_staff_review_list(self):
        self._auth(self.admin_user)
        resp = self.client.get(self._url_staff_reviews())
        assert resp.status_code == status.HTTP_200_OK

    def test_staff_report_list(self):
        self._auth(self.admin_user)
        resp = self.client.get(self._url_staff_reports())
        assert resp.status_code == status.HTTP_200_OK

    def test_staff_resolve_report(self):
        self._auth(self.patient_user)
        r = self.client.post(self._url_review(self.consultation.id), {"rating": 3})
        review_id = r.data["id"]

        self._auth(self.doctor_user)
        r2 = self.client.post(self._url_report(review_id), {"reason": "spam"})
        report_id = r2.data["id"]

        self._auth(self.admin_user)
        resp = self.client.patch(self._url_staff_resolve(report_id), {
            "resolution": "dismissed",
            "resolution_notes": "No issue found",
        })
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["resolution"] == "dismissed"


# ── Coordinator Access ──────────────────────────────────────────────────────


class CoordinatorAccessTests(ReviewAPITestCase):
    def test_coord_can_list_reviews(self):
        self._auth(self.coord_user)
        resp = self.client.get(self._url_staff_reviews())
        assert resp.status_code == status.HTTP_200_OK

    def test_coord_can_moderate(self):
        self._auth(self.patient_user)
        r = self.client.post(self._url_review(self.consultation.id), {"rating": 2})
        review_id = r.data["id"]

        self._auth(self.coord_user)
        resp = self.client.patch(self._url_staff_moderate(review_id), {"status": ReviewStatus.REMOVED})
        assert resp.status_code == status.HTTP_200_OK

    def test_coord_can_list_reports(self):
        self._auth(self.coord_user)
        resp = self.client.get(self._url_staff_reports())
        assert resp.status_code == status.HTTP_200_OK

    def test_coord_can_resolve_report(self):
        self._auth(self.patient_user)
        r = self.client.post(self._url_review(self.consultation.id), {"rating": 3})
        review_id = r.data["id"]
        self._auth(self.doctor_user)
        r2 = self.client.post(self._url_report(review_id), {"reason": "fake"})
        report_id = r2.data["id"]
        self._auth(self.coord_user)
        resp = self.client.patch(self._url_staff_resolve(report_id), {"resolution": "dismissed"})
        assert resp.status_code == status.HTTP_200_OK
