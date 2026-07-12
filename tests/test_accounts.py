from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User, UserRole


class UserModelTests(TestCase):
    """Tests for the custom User model."""

    def test_create_user(self) -> None:
        user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
            first_name="John",
            last_name="Doe",
            role=UserRole.PATIENT,
        )
        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.first_name, "John")
        self.assertEqual(user.last_name, "Doe")
        self.assertEqual(user.role, "patient")
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password("testpass123"))

    def test_create_superuser(self) -> None:
        admin = User.objects.create_superuser(
            email="admin@example.com",
            password="adminpass123",
        )
        self.assertEqual(admin.email, "admin@example.com")
        self.assertEqual(admin.role, "administrator")
        self.assertTrue(admin.is_active)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_email_normalization(self) -> None:
        email = "Test@Example.COM"
        user = User.objects.create_user(email=email, password="pass")
        self.assertEqual(user.email, "Test@example.com")

    def test_full_name_property(self) -> None:
        user = User.objects.create_user(
            email="test@example.com",
            password="pass",
            first_name="Jane",
            last_name="Smith",
        )
        self.assertEqual(user.full_name, "Jane Smith")

    def test_full_name_fallback(self) -> None:
        user = User.objects.create_user(email="test@example.com", password="pass")
        self.assertEqual(user.full_name, "test@example.com")


class UserAPITests(TestCase):
    """Tests for the accounts API endpoints."""

    def test_health_endpoint(self) -> None:
        url = reverse("accounts:health-check")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "healthy"})

    def test_me_endpoint_requires_auth(self) -> None:
        url = reverse("accounts:current-user")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_me_endpoint_authenticated(self) -> None:
        user = User.objects.create_user(
            email="auth@example.com",
            password="authpass123",
            first_name="Auth",
            last_name="User",
            role=UserRole.DOCTOR,
        )
        self.client.force_login(user)
        url = reverse("accounts:current-user")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["email"], "auth@example.com")
        self.assertEqual(data["role"], "doctor")
        self.assertEqual(data["full_name"], "Auth User")
