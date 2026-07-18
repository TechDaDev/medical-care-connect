from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User, UserRole
from apps.doctors.models import DoctorProfile
from apps.notifications.models import Notification, NotificationType
from apps.patients.models import PatientProfile
from apps.specialties.models import Specialty


class DoctorRegistrationTests(APITestCase):
    def setUp(self):
        self.specialty = Specialty.objects.create(name="Cardiology", is_active=True)
        self.coordinator = User.objects.create_user(
            email="coordinator@example.com", password="testpass123",
            role=UserRole.COORDINATOR,
        )
        self.payload = {
            "first_name": "Ava", "last_name": "Doctor", "email": "ava@example.com",
            "phone_number": "+9647000000000", "password": "testpass123",
            "password_confirm": "testpass123", "specialty": str(self.specialty.id),
            "medical_license_number": "iq-med-001", "years_of_experience": 7,
            "workplace_name": "City Hospital", "professional_bio": "Board certified.",
            "languages": ["ar", "en"],
        }

    def register(self, **overrides):
        return self.client.post(
            reverse("accounts:register-doctor"), {**self.payload, **overrides}, format="json"
        )

    def test_registration_creates_pending_private_doctor(self):
        response = self.register(role=UserRole.ADMINISTRATOR)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        profile = DoctorProfile.objects.get(user__email=self.payload["email"])
        self.assertEqual(profile.user.role, UserRole.DOCTOR)
        self.assertFalse(profile.is_approved)
        self.assertFalse(profile.is_accepting_consultations)
        self.assertEqual(profile.approval_status, DoctorProfile.ApprovalStatus.PENDING)
        self.assertEqual(response.data["next_path"], "/app/doctor/pending-approval")
        self.assertNotIn("medical_license_number", response.data)
        self.assertFalse(self.client.get(reverse("doctors:doctor-list")).data)
        self.assertTrue(Notification.objects.filter(
            recipient=self.coordinator, notification_type=NotificationType.DOCTOR_APPLICATION
        ).exists())

    def test_duplicate_license_is_rejected_safely(self):
        self.assertEqual(self.register().status_code, status.HTTP_201_CREATED)
        response = self.register(email="other@example.com", medical_license_number="IQ-MED-001")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("medical_license_number", response.data["fields"])

    def test_pending_doctor_cannot_enable_or_accept_operations(self):
        self.register()
        user = User.objects.get(email=self.payload["email"])
        self.client.force_authenticate(user)
        response = self.client.patch(
            reverse("doctors:my-availability-status"),
            {"is_accepting_consultations": True}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patient_registration_still_works(self):
        """Patient registration creates user + profile."""
        response = self.client.post(reverse("accounts:register-patient"), {
            "email": "patient@example.com", "password": "testpass123",
            "password_confirm": "testpass123", "first_name": "Pat", "last_name": "Test",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_patient_profile_created(self):
        self.client.post(reverse("accounts:register-patient"), {
            "email": "patient@example.com", "password": "testpass123",
            "password_confirm": "testpass123", "first_name": "Pat", "last_name": "Test",
        }, format="json")
        self.assertTrue(PatientProfile.objects.filter(user__email="patient@example.com").exists())

    def test_patient_role_assigned(self):
        self.client.post(reverse("accounts:register-patient"), {
            "email": "patient@example.com", "password": "testpass123",
            "password_confirm": "testpass123", "first_name": "Pat", "last_name": "Test",
        }, format="json")
        user = User.objects.get(email="patient@example.com")
        self.assertEqual(user.role, UserRole.PATIENT)

    def test_doctor_role_assigned_serverside(self):
        """Client-supplied role=administrator is ignored; server assigns doctor."""
        self.register(role=UserRole.ADMINISTRATOR)
        user = User.objects.get(email=self.payload["email"])
        self.assertEqual(user.role, UserRole.DOCTOR)

    def test_doctor_profile_created(self):
        self.register()
        profile = DoctorProfile.objects.filter(user__email=self.payload["email"])
        self.assertTrue(profile.exists())

    def test_doctor_absent_publicly(self):
        self.register()
        profile = DoctorProfile.objects.get(user__email=self.payload["email"])
        # Should not appear in public list
        list_resp = self.client.get(reverse("doctors:doctor-list"))
        ids = [d["id"] for d in list_resp.data] if isinstance(list_resp.data, list) else []
        self.assertNotIn(str(profile.id), ids)
        # Should 404 on public detail
        detail_resp = self.client.get(reverse("doctors:doctor-detail", args=[profile.id]))
        self.assertEqual(detail_resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_pending_doctor_blocked_from_availability_list(self):
        self.register()
        user = User.objects.get(email=self.payload["email"])
        self.client.force_authenticate(user)
        response = self.client.get(reverse("doctors:my-availability-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_pending_doctor_blocked_from_accepting_consultations(self):
        self.register()
        user = User.objects.get(email=self.payload["email"])
        self.client.force_authenticate(user)
        response = self.client.patch(
            reverse("doctors:my-availability-status"),
            {"is_accepting_consultations": True}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_email_rejected(self):
        self.register()
        response = self.register(email="ava@example.com")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_license_case_insensitive(self):
        self.register()
        response = self.register(email="other@example.com", medical_license_number="IQ-MED-001")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("medical_license_number", response.data["fields"])

    def test_invalid_specialty_rejected(self):
        response = self.register(specialty="00000000-0000-0000-0000-000000000000")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_experience_rejected(self):
        response = self.register(years_of_experience=-1)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_password_mismatch_rejected(self):
        response = self.register(password_confirm="wrongpass")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_arbitrary_role_ignored(self):
        """Public registration cannot set coordinator/admin role."""
        response = self.client.post(reverse("accounts:register-patient"), {
            "email": "hacker@example.com", "password": "testpass123",
            "password_confirm": "testpass123", "role": UserRole.COORDINATOR,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email="hacker@example.com")
        self.assertEqual(user.role, UserRole.PATIENT)

    def test_transaction_rollback_on_failure(self):
        """If profile creation fails, user is rolled back."""
        with patch("apps.doctors.models.DoctorProfile.objects.create") as mock_create:
            mock_create.side_effect = ValueError("DB failure")
            email = self.payload["email"]
            self.register()
            self.assertFalse(User.objects.filter(email=email).exists())

    def test_staff_notification_created_on_application(self):
        self.register()
        self.assertTrue(Notification.objects.filter(
            recipient=self.coordinator,
            notification_type=NotificationType.DOCTOR_APPLICATION,
        ).exists())

    def test_unauthorized_approval_denied(self):
        """Patient user cannot approve doctor applications."""
        self.register()
        profile = DoctorProfile.objects.get(user__email=self.payload["email"])
        patient = User.objects.create_user(
            email="patient@test.com", password="testpass123", role=UserRole.PATIENT
        )
        self.client.force_authenticate(patient)
        response = self.client.post(
            reverse("staff:doctor-application-review", args=[profile.id]),
            {"action": "approve"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_rejection_works(self):
        self.register()
        profile = DoctorProfile.objects.get(user__email=self.payload["email"])
        self.client.force_authenticate(self.coordinator)
        response = self.client.post(
            reverse("staff:doctor-application-review", args=[profile.id]),
            {"action": "reject", "reason": "Incomplete credentials"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile.refresh_from_db()
        self.assertEqual(profile.approval_status, DoctorProfile.ApprovalStatus.REJECTED)
        self.assertFalse(profile.is_approved)

    def test_approval_notification_created(self):
        self.register()
        profile = DoctorProfile.objects.get(user__email=self.payload["email"])
        self.client.force_authenticate(self.coordinator)
        self.client.post(
            reverse("staff:doctor-application-review", args=[profile.id]),
            {"action": "approve"}, format="json"
        )
        self.assertTrue(Notification.objects.filter(
            recipient=profile.user,
            notification_type=NotificationType.DOCTOR_APPLICATION_STATUS,
        ).exists())

    def test_license_absent_publicly(self):
        self.register()
        profile = DoctorProfile.objects.get(user__email=self.payload["email"])
        # Approve first
        self.client.force_authenticate(self.coordinator)
        self.client.post(
            reverse("staff:doctor-application-review", args=[profile.id]),
            {"action": "approve"}, format="json"
        )
        profile.refresh_from_db()
        # Check public detail
        list_resp = self.client.get(reverse("doctors:doctor-list"))
        for item in list_resp.data if isinstance(list_resp.data, list) else []:
            self.assertNotIn("license_number", item)
            self.assertNotIn("medical_license_number", item)
        detail_resp = self.client.get(
            reverse("doctors:doctor-detail", args=[profile.id])
        )
        self.assertNotIn("license_number", detail_resp.data)
        self.assertNotIn("medical_license_number", detail_resp.data)

    def test_staff_can_approve_and_doctor_is_not_auto_accepting(self):
        self.register()
        profile = DoctorProfile.objects.get(user__email=self.payload["email"])
        self.client.force_authenticate(self.coordinator)
        response = self.client.post(
            reverse("staff:doctor-application-review", args=[profile.id]),
            {"action": "approve"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile.refresh_from_db()
        self.assertTrue(profile.is_approved)
        self.assertFalse(profile.is_accepting_consultations)
        self.assertTrue(Notification.objects.filter(
            recipient=profile.user,
            notification_type=NotificationType.DOCTOR_APPLICATION_STATUS,
        ).exists())
