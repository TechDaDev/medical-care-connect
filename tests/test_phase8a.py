"""Tests for Phase 8A: HTTP-only cookie JWT authentication."""

import json

from django.test import TestCase, override_settings, Client
from django.urls import reverse

from apps.accounts.models import User, UserRole


def _jpost(client, url: str, data: dict, **kwargs):
    return client.post(
        url, json.dumps(data), content_type="application/json", **kwargs,
    )


class CookieAuthTests(TestCase):
    """Cookie-based JWT auth behavior."""

    def setUp(self):
        self.password = "testpass123"
        self.user = User.objects.create_user(
            email="cookie@example.com",
            password=self.password,
            role=UserRole.PATIENT,
            first_name="Cookie",
            last_name="Test",
        )

    # ── Login ──────────────────────────────────────────────────────────

    def test_login_sets_cookies(self):
        """Login response sets mcc_access and mcc_refresh cookies."""
        resp = _jpost(self.client, reverse("accounts:login"), {
            "email": "cookie@example.com", "password": self.password,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn("mcc_access", resp.cookies)
        self.assertIn("mcc_refresh", resp.cookies)
        # Cookies should be HttpOnly
        self.assertTrue(resp.cookies["mcc_access"].get("httponly", False))

    def test_login_no_tokens_in_body(self):
        """Login response body contains user data, not raw tokens."""
        resp = _jpost(self.client, reverse("accounts:login"), {
            "email": "cookie@example.com", "password": self.password,
        })
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertNotIn("access", body)
        self.assertNotIn("refresh", body)
        self.assertIn("user", body)
        self.assertEqual(body["user"]["email"], "cookie@example.com")

    # ── Cookie-authenticated GET ────────────────────────────────────────

    def test_cookie_auth_get_current_user(self):
        """GET /accounts/me/ works with cookie auth."""
        resp = _jpost(self.client, reverse("accounts:login"), {
            "email": "cookie@example.com", "password": self.password,
        })
        access = resp.cookies["mcc_access"].value

        me_resp = self.client.get(
            reverse("accounts:current-user"),
            HTTP_COOKIE=f"mcc_access={access}",
        )
        self.assertEqual(me_resp.status_code, 200)
        self.assertEqual(me_resp.json()["email"], "cookie@example.com")

    def test_no_cookie_returns_401(self):
        """GET /accounts/me/ without cookie returns 401."""
        resp = self.client.get(reverse("accounts:current-user"))
        self.assertEqual(resp.status_code, 401)

    # ── Cookie refresh ──────────────────────────────────────────────────

    def test_token_refresh_updates_cookie(self):
        """Token refresh endpoint updates mcc_access cookie."""
        resp = _jpost(self.client, reverse("accounts:login"), {
            "email": "cookie@example.com", "password": self.password,
        })
        refresh = resp.cookies["mcc_refresh"].value

        refresh_resp = self.client.post(
            reverse("accounts:token-refresh"),
            data=json.dumps({"refresh": refresh}),
            content_type="application/json",
            HTTP_COOKIE=f"mcc_refresh={refresh}",
        )
        self.assertEqual(refresh_resp.status_code, 200)
        self.assertIn("mcc_access", refresh_resp.cookies)
        # New access token should differ from original
        self.assertNotEqual(
            refresh_resp.cookies["mcc_access"].value,
            resp.cookies["mcc_access"].value,
        )

    # ── Logout ──────────────────────────────────────────────────────────

    def test_logout_clears_cookies(self):
        """Logout clears auth cookies."""
        resp = _jpost(self.client, reverse("accounts:login"), {
            "email": "cookie@example.com", "password": self.password,
        })
        access = resp.cookies["mcc_access"].value

        logout_resp = self.client.post(
            reverse("accounts:logout"),
            {"refresh": "dummy"},
            HTTP_COOKIE=f"mcc_access={access}",
            content_type="application/json",
        )
        self.assertEqual(logout_resp.status_code, 200)
        # Both cookies should be set to empty/max-age=0
        for name in ("mcc_access", "mcc_refresh"):
            c = logout_resp.cookies.get(name)
            if c:
                self.assertIn(c.value, ("", '""'))

    def test_logout_idempotent_without_cookie(self):
        """Logout returns 200 even when no refresh cookie/token provided."""
        resp = _jpost(self.client, reverse("accounts:login"), {
            "email": "cookie@example.com", "password": self.password,
        })
        access = resp.cookies["mcc_access"].value

        logout_resp = self.client.post(
            reverse("accounts:logout"),
            HTTP_COOKIE=f"mcc_access={access}",
            content_type="application/json",
        )
        self.assertEqual(logout_resp.status_code, 200)

    # ── CSRF enforcement (enforce_csrf_checks=True) ────────────────────

    @override_settings(
        CSRF_COOKIE_NAME="mcc_csrftoken",
        CSRF_COOKIE_HTTPONLY=False,
        CSRF_USE_SESSIONS=False,
    )
    def test_csrf_rejects_unsafe_without_token(self):
        """PATCH without X-CSRFToken is rejected when CSRF enforced."""
        csrf_client = Client(enforce_csrf_checks=True)
        # Log in — cookies stored in client's jar
        _jpost(csrf_client, reverse("accounts:login"), {
            "email": "cookie@example.com", "password": self.password,
        })
        # Get CSRF cookie (stored in jar)
        csrf_client.get(reverse("accounts:csrf"))
        # PATCH without X-CSRFToken → CookieJWTAuthentication returns None → 401
        resp = csrf_client.patch(
            reverse("accounts:current-user"),
            data=json.dumps({"first_name": "Hacked"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    @override_settings(
        CSRF_COOKIE_NAME="mcc_csrftoken",
        CSRF_COOKIE_HTTPONLY=False,
        CSRF_USE_SESSIONS=False,
    )
    def test_csrf_allows_unsafe_with_token(self):
        """PATCH with X-CSRFToken succeeds when CSRF enforced."""
        csrf_client = Client(enforce_csrf_checks=True)
        # Log in and get CSRF in separate steps (cookies in jar)
        _jpost(csrf_client, reverse("accounts:login"), {
            "email": "cookie@example.com", "password": self.password,
        })
        csrf_resp = csrf_client.get(reverse("accounts:csrf"))
        # Extract CSRF value from the response cookie for the header
        csrf_cookie = csrf_resp.cookies.get("mcc_csrftoken")
        self.assertIsNotNone(csrf_cookie)
        # PATCH with X-CSRFToken header → should pass CSRF
        resp = csrf_client.patch(
            reverse("accounts:current-user"),
            data=json.dumps({"first_name": "Updated"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_cookie.value,
        )
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Updated")

    # ── CSRF endpoint ──────────────────────────────────────────────────

    def test_csrf_endpoint_sets_cookie(self):
        """GET /auth/csrf/ sets the mcc_csrftoken cookie."""
        resp = self.client.get(reverse("accounts:csrf"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("mcc_csrftoken", resp.cookies)

    # ── Bearer backward compatibility ───────────────────────────────────

    def test_bearer_token_still_works(self):
        """Bearer Authorization header still authenticates requests."""
        resp = _jpost(self.client, reverse("accounts:login"), {
            "email": "cookie@example.com", "password": self.password,
        })
        access = resp.cookies["mcc_access"].value

        me_resp = self.client.get(
            reverse("accounts:current-user"),
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(me_resp.status_code, 200)
        self.assertEqual(me_resp.json()["email"], "cookie@example.com")

    # ── Register ────────────────────────────────────────────────────────

    def test_register_sets_cookies(self):
        """Patient registration sets auth cookies."""
        resp = _jpost(self.client, reverse("accounts:register-patient"), {
            "email": "newcookie@example.com",
            "password": "NewPass123!",
            "password_confirm": "NewPass123!",
            "first_name": "New",
            "last_name": "Cookie",
        })
        self.assertEqual(resp.status_code, 201)
        self.assertIn("mcc_access", resp.cookies)
        self.assertIn("mcc_refresh", resp.cookies)
        body = resp.json()
        self.assertNotIn("access", body)
        self.assertNotIn("refresh", body)
