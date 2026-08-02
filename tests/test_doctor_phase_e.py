from django.test import override_settings
from django.urls import resolve
from rest_framework.test import APITestCase

from apps.consultations.models import Consultation, ConsultationStatus
from apps.core.e2e_data import fixture_email, seed
from apps.accounts.models import User


@override_settings(
    DEBUG=True,
    E2E_LOCAL_ALLOWED=True,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class DoctorPhaseEClosureTests(APITestCase):
    run_id = "doctor-phase-e-backend"
    password = "Synthetic-Phase-E-Only!"

    @classmethod
    def setUpTestData(cls):
        seed(cls.run_id, cls.password)

    @classmethod
    def user(cls, role_name):
        return User.objects.get(email=fixture_email(cls.run_id, role_name))

    def test_final_doctor_route_map_resolves(self):
        routes = {
            "/api/doctors/me/access-state/": "my-access-state",
            "/api/doctors/me/dashboard/": "my-dashboard",
            "/api/doctors/me/availability/": "my-availability-list",
            "/api/consultations/doctor/": "doctor-list",
            "/api/doctors/me/message-threads/": "my-message-threads",
            "/api/doctors/me/medical-records/": "my-medical-record-list",
            "/api/doctors/me/reviews/": "my-reviews",
            "/api/doctors/me/notifications/": "my-notifications",
            "/api/doctors/me/": "my-profile",
            "/api/doctors/me/privacy/": "my-privacy",
        }
        for path, expected_name in routes.items():
            self.assertEqual(resolve(path).url_name, expected_name, path)

    def test_approved_doctor_can_read_final_workspace_surface(self):
        self.client.force_authenticate(self.user("approved"))
        paths = (
            "/api/doctors/me/access-state/",
            "/api/doctors/me/dashboard/",
            "/api/doctors/me/availability/",
            "/api/consultations/doctor/",
            "/api/doctors/me/message-threads/",
            "/api/doctors/me/medical-records/",
            "/api/doctors/me/reviews/",
            "/api/doctors/me/notifications/",
            "/api/doctors/me/",
            "/api/doctors/me/privacy/",
        )
        for path in paths:
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_restricted_principals_cannot_read_approved_doctor_workspace(self):
        paths = (
            "/api/doctors/me/dashboard/",
            "/api/doctors/me/availability/",
            "/api/consultations/doctor/",
            "/api/doctors/me/message-threads/",
            "/api/doctors/me/medical-records/",
            "/api/doctors/me/reviews/",
            "/api/doctors/me/notifications/",
            "/api/doctors/me/privacy/",
        )
        for role_name in (
            "pending",
            "rejected",
            "suspended",
            "missing-profile",
            "patient",
            "coordinator",
            "admin",
        ):
            self.client.force_authenticate(self.user(role_name))
            for path in paths:
                self.assertEqual(self.client.get(path).status_code, 403, (role_name, path))
        self.client.force_authenticate(None)
        for path in paths:
            self.assertEqual(self.client.get(path).status_code, 401, path)

    def test_cross_doctor_and_transfer_ownership_is_concealed(self):
        approved_consultation = Consultation.objects.filter(
            doctor__user=self.user("approved"), status=ConsultationStatus.SUBMITTED
        ).get()
        self.client.force_authenticate(self.user("unrelated"))
        self.assertEqual(
            self.client.get(
                f"/api/consultations/{approved_consultation.id}/doctor/"
            ).status_code,
            404,
        )

        transferred = Consultation.objects.get(status=ConsultationStatus.TRANSFERRED)
        self.client.force_authenticate(self.user("transfer-source"))
        self.assertEqual(
            self.client.get(f"/api/consultations/{transferred.id}/doctor/").status_code,
            404,
        )
        self.client.force_authenticate(self.user("transfer-target"))
        self.assertEqual(
            self.client.get(f"/api/consultations/{transferred.id}/doctor/").status_code,
            200,
        )

    def test_final_list_payloads_exclude_sensitive_implementation_fields(self):
        self.client.force_authenticate(self.user("approved"))
        banned = {
            "password",
            "password_hash",
            "session_key",
            "token",
            "storage_key",
            "storage_path",
            "provider_payload",
            "internal_notes",
        }

        def keys(value):
            if isinstance(value, dict):
                for key, nested in value.items():
                    yield key
                    yield from keys(nested)
            elif isinstance(value, list):
                for nested in value:
                    yield from keys(nested)

        for path in (
            "/api/consultations/doctor/",
            "/api/doctors/me/message-threads/",
            "/api/doctors/me/medical-records/",
            "/api/doctors/me/reviews/",
            "/api/doctors/me/notifications/",
            "/api/doctors/me/privacy/",
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertTrue(banned.isdisjoint(set(keys(response.data))), path)
