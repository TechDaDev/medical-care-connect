"""Tests for Phase 2: authentication, profiles, specialties, and permissions."""

import json

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User, UserRole
from apps.doctors.models import DoctorProfile
from apps.patients.models import PatientProfile
from apps.specialties.models import Specialty


def _jpatch(client, url: str, data: dict, **kwargs):
    """Send a PATCH with JSON body. Avoids format= pitfalls."""
    return client.patch(
        url, json.dumps(data), content_type="application/json", **kwargs,
    )


def _jpost(client, url: str, data: dict, **kwargs):
    """Send a POST with JSON body."""
    return client.post(
        url, json.dumps(data), content_type="application/json", **kwargs,
    )


def _login(client, email: str, password: str) -> str | None:
    """Helper: log in, clear cookies, return the access token string.

    Tokens now live in HTTP-only cookies.  We extract the value from
    the response cookie but then clear the client's cookie jar so tests
    that check 401/403 behaviour are not accidentally authenticated
    by a lingering cookie.
    """
    resp = _jpost(client, reverse("accounts:login"), {"email": email, "password": password})
    if resp.status_code != 200:
        return None
    token_value = None
    cookie = resp.cookies.get("mcc_access")
    if cookie:
        token_value = cookie.value
    # Remove the cookie so subsequent requests use the Bearer header
    client.cookies.clear()
    return token_value


class PatientRegistrationTests(TestCase):
    """Tests for patient registration."""

    def test_register_patient_success(self) -> None:
        url = reverse("accounts:register-patient")
        payload = {
            "email": "patient@example.com",
            "password": "testpass123",
            "password_confirm": "testpass123",
            "first_name": "Test",
            "last_name": "Patient",
            "phone_number": "+964771234567",
        }
        response = self.client.post(url, json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 201)
        data = response.json()
        # Tokens are now in HTTP-only cookies, not JSON body
        self.assertNotIn("access", data)
        self.assertNotIn("refresh", data)
        self.assertIn("user", data)
        self.assertEqual(data["user"]["email"], "patient@example.com")
        self.assertEqual(data["user"]["role"], "patient")
        # Verify cookies were set
        self.assertIn("mcc_access", response.cookies)
        self.assertIn("mcc_refresh", response.cookies)

        user = User.objects.get(email="patient@example.com")
        self.assertEqual(user.role, UserRole.PATIENT)
        self.assertTrue(PatientProfile.objects.filter(user=user).exists())

    def test_register_patient_password_mismatch(self) -> None:
        url = reverse("accounts:register-patient")
        payload = {
            "email": "patient@example.com",
            "password": "testpass123",
            "password_confirm": "differentpass",
            "first_name": "Test",
            "last_name": "Patient",
        }
        response = self.client.post(url, json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_register_requires_unique_email(self) -> None:
        User.objects.create_user(email="patient@example.com", password="pass123")
        url = reverse("accounts:register-patient")
        payload = {
            "email": "patient@example.com",
            "password": "testpass123",
            "password_confirm": "testpass123",
            "first_name": "Another",
            "last_name": "Patient",
        }
        response = self.client.post(url, json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_register_patient_creates_profile_with_optional_fields(self) -> None:
        url = reverse("accounts:register-patient")
        payload = {
            "email": "detailed@example.com",
            "password": "testpass123",
            "password_confirm": "testpass123",
            "first_name": "Detailed",
            "last_name": "Patient",
            "phone_number": "+964770000000",
            "date_of_birth": "1990-01-15",
            "gender": "male",
            "preferred_language": "ar",
        }
        response = self.client.post(url, json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email="detailed@example.com")
        profile = user.patient_profile
        self.assertEqual(str(profile.date_of_birth), "1990-01-15")
        self.assertEqual(profile.gender, "male")
        self.assertEqual(profile.preferred_language, "ar")


class LoginLogoutTests(TestCase):
    """Tests for JWT login and logout."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
            role=UserRole.PATIENT,
        )

    def test_login_success(self) -> None:
        url = reverse("accounts:login")
        response = _jpost(self.client, url, {"email": "test@example.com", "password": "testpass123"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Tokens are in HTTP-only cookies, not JSON body
        self.assertNotIn("access", data)
        self.assertNotIn("refresh", data)
        self.assertIn("user", data)
        self.assertEqual(data["user"]["email"], "test@example.com")
        # Verify cookies were set
        self.assertIn("mcc_access", response.cookies)
        self.assertIn("mcc_refresh", response.cookies)

    def test_login_inactive_account(self) -> None:
        self.user.is_active = False
        self.user.save()
        url = reverse("accounts:login")
        response = _jpost(self.client, url, {"email": "test@example.com", "password": "testpass123"})
        self.assertEqual(response.status_code, 401)

    def test_login_wrong_password(self) -> None:
        url = reverse("accounts:login")
        response = _jpost(self.client, url, {"email": "test@example.com", "password": "wrongpass"})
        self.assertEqual(response.status_code, 401)

    def test_logout_success(self) -> None:
        token = _login(self.client, "test@example.com", "testpass123")
        self.assertIsNotNone(token)
        logout_url = reverse("accounts:logout")
        response = self.client.post(
            logout_url,
            {"refresh": "invalid-token-for-test"},
            **{"HTTP_AUTHORIZATION": f"Bearer {token}"},
        )
        # Refresh token invalid → 400, but auth passed
        self.assertIn(response.status_code, (200, 400))

    def test_logout_requires_auth(self) -> None:
        url = reverse("accounts:logout")
        response = _jpost(self.client, url, {"refresh": "some-token"})
        self.assertEqual(response.status_code, 401)

    def test_logout_missing_refresh_token(self) -> None:
        token = _login(self.client, "test@example.com", "testpass123")
        self.assertIsNotNone(token)
        url = reverse("accounts:logout")
        response = self.client.post(
            url, json.dumps({}), content_type="application/json",
            **{"HTTP_AUTHORIZATION": f"Bearer {token}"},
        )
        # Logout is idempotent — succeeds even without a refresh token
        self.assertEqual(response.status_code, 200)


class SpecialtiesAPITests(TestCase):
    """Tests for the specialties endpoints."""

    def setUp(self) -> None:
        self.specialty = Specialty.objects.create(
            name="Cardiology", description="Heart and cardiovascular system", display_order=1,
        )
        Specialty.objects.create(
            name="Neurology", description="Nervous system", display_order=2,
        )

    def test_list_specialties_public(self) -> None:
        url = reverse("specialties:specialty-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # ViewSet returns paginated response; results key contains items
        data = response.json()
        items = data.get("results", data)
        self.assertEqual(len(items), 2)

    def test_retrieve_specialty_public(self) -> None:
        url = reverse("specialties:specialty-detail", args=[self.specialty.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Cardiology")

    def test_create_specialty_requires_auth(self) -> None:
        url = reverse("specialties:specialty-list")
        response = _jpost(self.client, url, {"name": "Dermatology"})
        self.assertEqual(response.status_code, 401)

    def test_slug_auto_generated(self) -> None:
        specialty = Specialty.objects.create(name="General Surgery")
        self.assertEqual(specialty.slug, "general-surgery")


class PatientProfileAPITests(TestCase):
    """Tests for the patient profile endpoints."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="patient@example.com", password="testpass123",
            first_name="Test", last_name="Patient", role=UserRole.PATIENT,
        )
        self.profile = PatientProfile.objects.create(
            user=self.user, gender="female", preferred_language="ar",
        )
        self.token = _login(self.client, "patient@example.com", "testpass123")

    def test_get_profile_requires_auth(self) -> None:
        url = reverse("patients:my-profile")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 401)

    def test_get_profile_success(self) -> None:
        url = reverse("patients:my-profile")
        response = self.client.get(url, **{"HTTP_AUTHORIZATION": f"Bearer {self.token}"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["email"], "patient@example.com")
        self.assertEqual(data["gender"], "female")
        self.assertEqual(data["full_name"], "Test Patient")

    def test_update_profile(self) -> None:
        url = reverse("patients:my-profile")
        response = _jpatch(
            self.client, url, {"blood_type": "O+"},
            **{"HTTP_AUTHORIZATION": f"Bearer {self.token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.blood_type, "O+")

    def test_doctor_cannot_access_patient_profile(self) -> None:
        doc = User.objects.create_user(
            email="doctor@example.com", password="pass123", role=UserRole.DOCTOR,
        )
        doc_token = _login(self.client, "doctor@example.com", "pass123")
        url = reverse("patients:my-profile")
        response = self.client.get(url, **{"HTTP_AUTHORIZATION": f"Bearer {doc_token}"})
        self.assertEqual(response.status_code, 403)


class DoctorProfileAPITests(TestCase):
    """Tests for the doctor profile endpoints."""

    def setUp(self) -> None:
        self.specialty = Specialty.objects.create(name="Cardiology")
        self.user = User.objects.create_user(
            email="doctor@example.com", password="testpass123",
            first_name="Jane", last_name="Doctor", role=UserRole.DOCTOR,
        )
        self.profile = DoctorProfile.objects.create(
            user=self.user, specialty=self.specialty,
            professional_title="Consultant Cardiologist",
            license_number="LIC-12345", years_of_experience=10,
            consultation_fee=75.00, languages=["English", "Arabic"],
        )
        self.token = _login(self.client, "doctor@example.com", "testpass123")

    def test_get_profile_requires_auth(self) -> None:
        url = reverse("doctors:my-profile")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 401)

    def test_get_profile_success(self) -> None:
        url = reverse("doctors:my-profile")
        response = self.client.get(url, **{"HTTP_AUTHORIZATION": f"Bearer {self.token}"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["email"], "doctor@example.com")
        self.assertEqual(data["specialty_name"], "Cardiology")
        self.assertEqual(data["license_number"], "LIC-12345")
        self.assertFalse(data["is_approved"])

    def test_update_profile(self) -> None:
        url = reverse("doctors:my-profile")
        response = _jpatch(
            self.client, url,
            {"consultation_fee": "100.00", "biography": "Experienced cardiologist."},
            **{"HTTP_AUTHORIZATION": f"Bearer {self.token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.consultation_fee, 100.00)
        self.assertEqual(self.profile.biography, "Experienced cardiologist.")

    def test_doctor_cannot_change_is_approved(self) -> None:
        url = reverse("doctors:my-profile")
        response = _jpatch(
            self.client, url, {"is_approved": True},
            **{"HTTP_AUTHORIZATION": f"Bearer {self.token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_approved)

    def test_patient_cannot_access_doctor_profile(self) -> None:
        pat = User.objects.create_user(
            email="patient-x@example.com", password="pass123", role=UserRole.PATIENT,
        )
        pat_token = _login(self.client, "patient-x@example.com", "pass123")
        url = reverse("doctors:my-profile")
        response = self.client.get(url, **{"HTTP_AUTHORIZATION": f"Bearer {pat_token}"})
        self.assertEqual(response.status_code, 403)


class PermissionsTests(TestCase):
    """Tests for role-based permission classes."""

    def test_me_endpoint_patch(self) -> None:
        user = User.objects.create_user(
            email="test@example.com", password="pass123",
            first_name="Old", last_name="Name", role=UserRole.PATIENT,
        )
        token = _login(self.client, "test@example.com", "pass123")
        url = reverse("accounts:current-user")
        response = _jpatch(
            self.client, url, {"first_name": "New", "last_name": "Name"},
            **{"HTTP_AUTHORIZATION": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.first_name, "New")

    def test_me_endpoint_patch_rejects_role_change(self) -> None:
        User.objects.create_user(
            email="test@example.com", password="pass123", role=UserRole.PATIENT,
        )
        token = _login(self.client, "test@example.com", "pass123")
        url = reverse("accounts:current-user")
        response = _jpatch(
            self.client, url, {"role": "doctor"},
            **{"HTTP_AUTHORIZATION": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(email="test@example.com")
        self.assertEqual(user.role, UserRole.PATIENT)
