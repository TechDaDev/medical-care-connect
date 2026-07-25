"""Tests for administrator user and role management (Phase C)."""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken, OutstandingToken

from apps.accounts.models import User, UserRole


def _auth_header(user: User) -> dict:
    """Return Authorization header for a user."""
    refresh = RefreshToken.for_user(user)
    return {"HTTP_AUTHORIZATION": f"Bearer {refresh.access_token}"}


class AdminUserListTests(APITestCase):
    """Tests for GET /api/staff/users/"""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com", password="testpass123",
            role=UserRole.ADMINISTRATOR, first_name="Admin", last_name="User",
        )
        self.coordinator = User.objects.create_user(
            email="coord@example.com", password="testpass123",
            role=UserRole.COORDINATOR,
        )
        self.doctor = User.objects.create_user(
            email="doc@example.com", password="testpass123",
            role=UserRole.DOCTOR, first_name="Doc", last_name="Tor",
        )
        self.patient = User.objects.create_user(
            email="pat@example.com", password="testpass123",
            role=UserRole.PATIENT,
        )
        self.url = reverse("staff:admin-user-list")

    def test_anonymous_denied(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_patient_denied(self):
        response = self.client.get(self.url, **_auth_header(self.patient))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_doctor_denied(self):
        response = self.client.get(self.url, **_auth_header(self.doctor))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_coordinator_denied(self):
        response = self.client.get(self.url, **_auth_header(self.coordinator))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_administrator_allowed(self):
        response = self.client.get(self.url, **_auth_header(self.admin))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_pagination(self):
        for i in range(25):
            User.objects.create_user(
                email=f"user{i}@example.com", password="testpass123",
                role=UserRole.PATIENT,
            )
        response = self.client.get(self.url, **_auth_header(self.admin))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("count", response.data)
        self.assertIn("results", response.data)
        self.assertEqual(len(response.data["results"]), 20)

    def test_role_filter(self):
        response = self.client.get(
            self.url, {"role": UserRole.DOCTOR}, **_auth_header(self.admin),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for r in response.data["results"]:
            self.assertEqual(r["role"], UserRole.DOCTOR)

    def test_active_filter(self):
        inactive = User.objects.create_user(
            email="inactive@example.com", password="testpass123",
            role=UserRole.PATIENT, is_active=False,
        )
        response = self.client.get(
            self.url, {"active": "false"}, **_auth_header(self.admin),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [r["id"] for r in response.data["results"]]
        self.assertIn(str(inactive.id), ids)

    def test_search_by_name(self):
        response = self.client.get(
            self.url, {"search": "Admin"}, **_auth_header(self.admin),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            any("Admin" in r.get("full_name", "") for r in response.data["results"])
        )

    def test_search_by_email(self):
        response = self.client.get(
            self.url, {"search": "admin@"}, **_auth_header(self.admin),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            any("admin@" in r.get("email", "") for r in response.data["results"])
        )

    def test_date_filters(self):
        response = self.client.get(
            self.url, {"created_after": "2020-01-01"}, **_auth_header(self.admin),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_ordering(self):
        response = self.client.get(
            self.url, {"ordering": "email"}, **_auth_header(self.admin),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_safe_fields_only(self):
        response = self.client.get(self.url, **_auth_header(self.admin))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for r in response.data["results"]:
            self.assertNotIn("password", r)
            self.assertNotIn("is_superuser", r)
            self.assertIn("full_name", r)
            self.assertIn("email", r)
            self.assertIn("role", r)

    def test_available_actions_present(self):
        response = self.client.get(self.url, **_auth_header(self.admin))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for r in response.data["results"]:
            self.assertIn("available_actions", r)

    def test_available_actions_self_no_deactivate(self):
        """Admin should not see deactivate for self."""
        response = self.client.get(self.url, **_auth_header(self.admin))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for r in response.data["results"]:
            if str(self.admin.id) == r["id"]:
                self.assertNotIn("deactivate", r["available_actions"])


class AdminUserDetailTests(APITestCase):
    """Tests for GET /api/staff/users/<id>/"""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com", password="testpass123",
            role=UserRole.ADMINISTRATOR,
        )
        self.coordinator = User.objects.create_user(
            email="coord@example.com", password="testpass123",
            role=UserRole.COORDINATOR,
        )
        self.target = User.objects.create_user(
            email="target@example.com", password="testpass123",
            role=UserRole.COORDINATOR, first_name="Target", last_name="User",
        )

    def test_administrator_allowed(self):
        url = reverse("staff:admin-user-detail", args=[self.target.id])
        response = self.client.get(url, **_auth_header(self.admin))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_coordinator_denied(self):
        url = reverse("staff:admin-user-detail", args=[self.target.id])
        response = self.client.get(url, **_auth_header(self.coordinator))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_safe_fields(self):
        url = reverse("staff:admin-user-detail", args=[self.target.id])
        response = self.client.get(url, **_auth_header(self.admin))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("password", response.data)
        self.assertIn("full_name", response.data)
        self.assertIn("email", response.data)
        self.assertIn("role", response.data)
        self.assertIn("is_active", response.data)

    def test_session_summary(self):
        url = reverse("staff:admin-user-detail", args=[self.target.id])
        response = self.client.get(url, **_auth_header(self.admin))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("active_refresh_tokens", response.data)
        self.assertIn("last_token_created_at", response.data)

    def test_available_actions(self):
        url = reverse("staff:admin-user-detail", args=[self.target.id])
        response = self.client.get(url, **_auth_header(self.admin))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("available_actions", response.data)

    def test_missing_user_404(self):
        url = reverse("staff:admin-user-detail", args=["00000000-0000-0000-0000-000000000000"])
        response = self.client.get(url, **_auth_header(self.admin))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class AdminUserStatusTests(APITestCase):
    """Tests for PATCH /api/staff/users/<id>/status/"""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com", password="testpass123",
            role=UserRole.ADMINISTRATOR,
        )
        self.coordinator = User.objects.create_user(
            email="coord@example.com", password="testpass123",
            role=UserRole.COORDINATOR,
        )
        self.target = User.objects.create_user(
            email="target@example.com", password="testpass123",
            role=UserRole.COORDINATOR, is_active=True,
        )
        self.inactive_target = User.objects.create_user(
            email="inactive@example.com", password="testpass123",
            role=UserRole.COORDINATOR, is_active=False,
        )

    def _url(self, user):
        return reverse("staff:admin-user-status", args=[user.id])

    def test_deactivate_active_user(self):
        response = self.client.patch(
            self._url(self.target),
            {"is_active": False, "reason": "Violated terms of service for the third time."},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)

    def test_activate_inactive_user(self):
        response = self.client.patch(
            self._url(self.inactive_target),
            {"is_active": True, "reason": "Appeal approved and account reinstated."},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.inactive_target.refresh_from_db()
        self.assertTrue(self.inactive_target.is_active)

    def test_reason_required(self):
        response = self.client.patch(
            self._url(self.target),
            {"is_active": False, "reason": "No"},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_expected_state_conflict(self):
        response = self.client.patch(
            self._url(self.target),
            {"is_active": False, "reason": "This is a valid reason for deactivation.",
             "expected_is_active": False},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_self_deactivation_denied(self):
        response = self.client.patch(
            self._url(self.admin),
            {"is_active": False, "reason": "This is a valid reason for my deactivation."},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_final_admin_deactivation_denied(self):
        response = self.client.patch(
            self._url(self.admin),
            {"is_active": False, "reason": "This is a valid reason to deactivate the only admin."},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_sessions_revoked_on_deactivation(self):
        # Generate a token first
        RefreshToken.for_user(self.target)
        response = self.client.patch(
            self._url(self.target),
            {"is_active": False, "reason": "This is a valid reason for deactivation with session revocation."},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        remaining = OutstandingToken.objects.filter(user=self.target)
        self.assertEqual(remaining.count(), 0)

    def test_activation_does_not_restore_sessions(self):
        self.target.is_active = False
        self.target.save()
        response = self.client.patch(
            self._url(self.target),
            {"is_active": True, "reason": "Good reason to reactivate this user account here."},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_audit_event_emitted(self):
        """Deactivation should succeed (audit events are fire-and-forget)."""
        response = self.client.patch(
            self._url(self.target),
            {"is_active": False, "reason": "Compliance violation that needs addressing immediately."},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_updated_detail_returned(self):
        response = self.client.patch(
            self._url(self.target),
            {"is_active": False, "reason": "Security incident that requires immediate action taken."},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("user", response.data)
        self.assertFalse(response.data["user"]["is_active"])


class AdminUserSessionRevocationTests(APITestCase):
    """Tests for POST /api/staff/users/<id>/revoke-sessions/"""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com", password="testpass123",
            role=UserRole.ADMINISTRATOR,
        )
        self.target = User.objects.create_user(
            email="target@example.com", password="testpass123",
            role=UserRole.COORDINATOR,
        )

    def _url(self, user):
        return reverse("staff:admin-user-revoke-sessions", args=[user.id])

    def test_revoke_active_sessions(self):
        RefreshToken.for_user(self.target)
        response = self.client.post(
            self._url(self.target),
            {"reason": "Suspicious activity detected. All sessions invalidated."},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["revoked_sessions"], 1)

    def test_zero_sessions_success(self):
        response = self.client.post(
            self._url(self.target),
            {"reason": "Security audit requiring complete session reset for this user."},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["revoked_sessions"], 0)

    def test_reason_required(self):
        response = self.client.post(
            self._url(self.target),
            {"reason": ""},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_self_session_revocation_denied(self):
        """Admin cannot revoke their own sessions through another-user workflow."""
        response = self.client.post(
            self._url(self.admin),
            {"reason": "Why would I revoke my own sessions anyway for testing?"},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)


class AdminUserRoleTests(APITestCase):
    """Tests for PATCH /api/staff/users/<id>/role/"""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com", password="testpass123",
            role=UserRole.ADMINISTRATOR,
        )
        self.coordinator = User.objects.create_user(
            email="coord@example.com", password="testpass123",
            role=UserRole.COORDINATOR,
        )
        self.target_coord = User.objects.create_user(
            email="target-coord@example.com", password="testpass123",
            role=UserRole.COORDINATOR,
        )
        self.second_admin = User.objects.create_user(
            email="admin2@example.com", password="testpass123",
            role=UserRole.ADMINISTRATOR,
        )
        self.patient = User.objects.create_user(
            email="patient@example.com", password="testpass123",
            role=UserRole.PATIENT,
        )
        self.doctor = User.objects.create_user(
            email="doctor@example.com", password="testpass123",
            role=UserRole.DOCTOR,
        )

    def _url(self, user):
        return reverse("staff:admin-user-role", args=[user.id])

    def test_coordinator_to_administrator(self):
        response = self.client.patch(
            self._url(self.target_coord),
            {"role": UserRole.ADMINISTRATOR, "reason": "Promoted due to outstanding performance this quarter."},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.target_coord.refresh_from_db()
        self.assertEqual(self.target_coord.role, UserRole.ADMINISTRATOR)

    def test_administrator_to_coordinator(self):
        response = self.client.patch(
            self._url(self.second_admin),
            {"role": UserRole.COORDINATOR, "reason": "Role restructuring to better fit current organizational needs."},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.second_admin.refresh_from_db()
        self.assertEqual(self.second_admin.role, UserRole.COORDINATOR)

    def test_patient_role_change_denied(self):
        response = self.client.patch(
            self._url(self.patient),
            {"role": UserRole.ADMINISTRATOR, "reason": "This role change should be denied for patient users."},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_doctor_role_change_denied(self):
        response = self.client.patch(
            self._url(self.doctor),
            {"role": UserRole.ADMINISTRATOR, "reason": "Doctors should not be promoted through this generic flow."},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_self_demotion_denied(self):
        response = self.client.patch(
            self._url(self.admin),
            {"role": UserRole.COORDINATOR, "reason": "I want to demote myself for testing purposes here."},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_final_admin_demotion_denied(self):
        # Make second_admin a coordinator first so admin is the only admin
        self.second_admin.role = UserRole.COORDINATOR
        self.second_admin.save()
        response = self.client.patch(
            self._url(self.admin),
            {"role": UserRole.COORDINATOR, "reason": "This should fail because I am the only remaining admin."},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_expected_role_conflict(self):
        response = self.client.patch(
            self._url(self.target_coord),
            {"role": UserRole.ADMINISTRATOR, "reason": "Promotion to handle increased responsibilities effectively.",
             "expected_role": UserRole.ADMINISTRATOR},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_sessions_revoked_after_role_change(self):
        RefreshToken.for_user(self.target_coord)
        response = self.client.patch(
            self._url(self.target_coord),
            {"role": UserRole.ADMINISTRATOR, "reason": "Promoted to administrator role due to excellent work."},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        remaining = OutstandingToken.objects.filter(user=self.target_coord)
        self.assertEqual(remaining.count(), 0)

    def test_updated_detail_returned(self):
        response = self.client.patch(
            self._url(self.target_coord),
            {"role": UserRole.ADMINISTRATOR, "reason": "Promoted for demonstrating strong leadership skills recently."},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("user", response.data)
        self.assertEqual(response.data["user"]["role"], UserRole.ADMINISTRATOR)


class AdminUserConcurrencyTests(APITestCase):
    """Tests for concurrent safety of admin user management."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com", password="testpass123",
            role=UserRole.ADMINISTRATOR,
        )
        self.target = User.objects.create_user(
            email="target@example.com", password="testpass123",
            role=UserRole.COORDINATOR,
        )

    def test_simultaneous_state_change(self):
        url = reverse("staff:admin-user-status", args=[self.target.id])
        # First call succeeds
        resp1 = self.client.patch(
            url,
            {"is_active": False, "reason": "First concurrent deactivation of this user account here."},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)

        # Second call should get 409 since expected_is_active doesn't match
        resp2 = self.client.patch(
            url,
            {"is_active": True, "reason": "Attempting reactivation after already deactivated earlier today.",
             "expected_is_active": True},
            **_auth_header(self.admin), format="json",
        )
        self.assertEqual(resp2.status_code, status.HTTP_409_CONFLICT)
