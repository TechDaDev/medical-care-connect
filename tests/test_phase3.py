"""Tests for Phase 3: public directory, availability, consultations."""

import json
from datetime import time
from uuid import uuid4

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User, UserRole
from apps.consultations.models import Consultation, ConsultationStatus
from apps.doctors.models import DoctorAvailability, DoctorProfile, Weekday
from apps.patients.models import PatientProfile
from apps.specialties.models import Specialty


def _jpatch(client, url: str, data: dict, **kwargs):
    return client.patch(
        url, json.dumps(data), content_type="application/json", **kwargs,
    )


def _jpost(client, url: str, data: dict, **kwargs):
    return client.post(
        url, json.dumps(data), content_type="application/json", **kwargs,
    )


def _login(client, email: str, password: str) -> str | None:
    resp = _jpost(client, reverse("accounts:login"), {"email": email, "password": password})
    if resp.status_code != 200:
        return None
    token = resp.cookies.get("mcc_access")
    token_value = token.value if token else None
    client.cookies.clear()
    return token_value


class PublicDoctorDirectoryTests(TestCase):
    """Tests for the public doctor directory."""

    def setUp(self) -> None:
        self.spec = Specialty.objects.create(name="TestCardiology", slug="test-cardiology")
        # Approved doctor
        self.doc_user = User.objects.create_user(
            email="doctor@example.com", password="pass123",
            first_name="Jane", last_name="Doctor", role=UserRole.DOCTOR,
        )
        self.doc = DoctorProfile.objects.create(
            user=self.doc_user, specialty=self.spec,
            professional_title="Cardiologist", years_of_experience=10,
            consultation_fee=100, is_approved=True,
            approval_status=DoctorProfile.ApprovalStatus.APPROVED,
            is_accepting_consultations=True, languages=["English"],
            license_number="LIC-CARDIO",
        )
        # Unapproved doctor (should not appear)
        self.unapproved_user = User.objects.create_user(
            email="unapproved@example.com", password="pass123",
            first_name="Bad", last_name="Doctor", role=UserRole.DOCTOR,
        )
        self.unapproved = DoctorProfile.objects.create(
            user=self.unapproved_user, specialty=self.spec,
            professional_title="Unapproved", is_approved=False,
            license_number="LIC-UNAPPROVED",
        )

    def test_public_list_shows_only_approved_active(self):
        url = reverse("doctors:doctor-list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["results"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["full_name"], "Jane Doctor")

    def test_public_list_filter_accepting(self):
        url = reverse("doctors:doctor-list")
        resp = self.client.get(url, {"accepting": "true"})
        self.assertEqual(len(resp.json()["results"]), 1)

        self.doc.is_accepting_consultations = False
        self.doc.save()
        resp = self.client.get(url, {"accepting": "true"})
        self.assertEqual(len(resp.json()["results"]), 0)

    def test_public_list_search(self):
        url = reverse("doctors:doctor-list")
        resp = self.client.get(url, {"search": "Jane"})
        self.assertEqual(len(resp.json()["results"]), 1)
        resp = self.client.get(url, {"search": "NotFound"})
        self.assertEqual(len(resp.json()["results"]), 0)

    def test_public_detail_excludes_sensitive_fields(self):
        url = reverse("doctors:doctor-detail", args=[self.doc.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["full_name"], "Jane Doctor")
        self.assertNotIn("email", data)
        self.assertNotIn("phone_number", data)
        self.assertNotIn("license_number", data)
        self.assertNotIn("is_approved", data)


class DoctorAvailabilityTests(TestCase):
    """Tests for doctor availability CRUD."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="doctor@example.com", password="pass123",
            role=UserRole.DOCTOR,
        )
        self.profile = DoctorProfile.objects.create(
            user=self.user,
            is_approved=True,
            approval_status=DoctorProfile.ApprovalStatus.APPROVED,
            license_number="LIC-AVAIL",
        )
        self.token = _login(self.client, "doctor@example.com", "pass123")
        self._auth = {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def test_create_and_list_availability(self):
        url = reverse("doctors:my-availability-list")
        resp = _jpost(self.client, url, {
            "day_of_week": "monday",
            "start_time": "09:00",
            "end_time": "17:00",
        }, **self._auth)
        self.assertEqual(resp.status_code, 201)

        resp = self.client.get(url, **self._auth)
        self.assertEqual(len(resp.json()["slots"]), 1)
        self.assertEqual(resp.json()["slots"][0]["day_of_week"], "monday")

    def test_toggle_accepting_status(self):
        url = reverse("doctors:my-availability-status")
        resp = _jpatch(self.client, url, {"is_accepting_consultations": True}, **self._auth)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["is_accepting_consultations"])
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.is_accepting_consultations)


class ConsultationTests(TestCase):
    """Tests for consultation CRUD and actions."""

    def setUp(self) -> None:
        self.spec = Specialty.objects.create(
            name="General Medicine",
            name_en="General Medicine",
            name_ar="الطب العام",
            name_ckb="پزیشکی گشتی",
            slug="general-medicine",
        )
        # Doctor
        self.doc_user = User.objects.create_user(
            email="doctor@example.com", password="pass123",
            first_name="Doc", role=UserRole.DOCTOR,
        )
        self.doc = DoctorProfile.objects.create(
            user=self.doc_user, specialty=self.spec,
            is_approved=True,
            approval_status=DoctorProfile.ApprovalStatus.APPROVED,
            is_accepting_consultations=True,
            license_number="LIC-CONSULT",
        )
        self.doc_token = _login(self.client, "doctor@example.com", "pass123")
        # Patient
        self.pat_user = User.objects.create_user(
            email="patient@example.com", password="pass123",
            first_name="Pat", role=UserRole.PATIENT,
        )
        self.pat = PatientProfile.objects.create(user=self.pat_user)
        self.pat_token = _login(self.client, "patient@example.com", "pass123")
        # Coordinator
        self.coord_user = User.objects.create_user(
            email="coord@example.com", password="pass123",
            role=UserRole.COORDINATOR,
        )
        self.coord_token = _login(self.client, "coord@example.com", "pass123")

        self._doc_auth = {"HTTP_AUTHORIZATION": f"Bearer {self.doc_token}"}
        self._pat_auth = {"HTTP_AUTHORIZATION": f"Bearer {self.pat_token}"}
        self._coord_auth = {"HTTP_AUTHORIZATION": f"Bearer {self.coord_token}"}

    def test_create_consultation_patient_only(self):
        url = reverse("consultations:list")
        resp = _jpost(self.client, url, {
            "doctor": str(self.doc.id),
            "description": "Persistent headache lasting several days.",
            "client_request_id": str(uuid4()),
        }, **self._pat_auth)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["status"], "submitted")
        self.assertIsNotNone(data["submitted_at"])

    def test_create_consultation_doctor_not_accepting(self):
        self.doc.is_accepting_consultations = False
        self.doc.save()
        url = reverse("consultations:list")
        resp = _jpost(self.client, url, {
            "doctor": str(self.doc.id),
            "description": "Persistent headache lasting several days.",
            "client_request_id": str(uuid4()),
        }, **self._pat_auth)
        self.assertEqual(resp.status_code, 409)

    def test_list_consultations_role_scoped(self):
        c = Consultation.objects.create(
            patient=self.pat, doctor=self.doc,
            status=ConsultationStatus.SUBMITTED,
        )
        # Patient sees own
        url = reverse("consultations:list")
        resp = self.client.get(url, **self._pat_auth)
        self.assertEqual(len(resp.json()["results"]), 1)
        # Doctor sees assigned
        resp = self.client.get(url, **self._doc_auth)
        self.assertEqual(len(resp.json()), 1)
        # Coordinator sees all
        resp = self.client.get(url, **self._coord_auth)
        self.assertEqual(len(resp.json()), 1)

    def test_accept_consultation_assigned_doctor(self):
        c = Consultation.objects.create(
            patient=self.pat, doctor=self.doc,
            status=ConsultationStatus.SUBMITTED,
        )
        url = reverse("consultations:accept", args=[c.id])
        # Wrong doctor
        other_doc = User.objects.create_user(
            email="other@example.com", password="pass123", role=UserRole.DOCTOR,
        )
        DoctorProfile.objects.create(
            user=other_doc, is_approved=True, license_number="LIC-OTHER",
        )
        other_token = _login(self.client, "other@example.com", "pass123")
        resp = _jpost(self.client, url, {}, **{"HTTP_AUTHORIZATION": f"Bearer {other_token}"})
        self.assertEqual(resp.status_code, 403)

        # Correct doctor
        resp = _jpost(self.client, url, {
            "expected_status": "submitted",
            "client_request_id": str(uuid4()),
        }, **self._doc_auth)
        self.assertEqual(resp.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.status, ConsultationStatus.ACCEPTED)
        self.assertIsNotNone(c.accepted_at)

    def test_cancel_consultation_requires_reason(self):
        c = Consultation.objects.create(
            patient=self.pat, doctor=self.doc,
            status=ConsultationStatus.SUBMITTED,
        )
        url = reverse("consultations:cancel", args=[c.id])
        resp = _jpost(self.client, url, {}, **self._pat_auth)
        self.assertEqual(resp.status_code, 400)

        resp = _jpost(self.client, url, {"cancellation_reason": "Changed my mind"}, **self._pat_auth)
        self.assertEqual(resp.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.status, ConsultationStatus.CANCELLED)
        self.assertEqual(c.cancellation_reason, "Changed my mind")
