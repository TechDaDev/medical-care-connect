from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware


def _check_csrf(request):
    """Return True if CSRF is valid or not required (safe methods)."""
    if request.method in ("GET", "HEAD", "OPTIONS", "TRACE"):
        return True
    middleware = CsrfViewMiddleware(get_response=lambda r: None)
    result = middleware.process_view(request, None, (), {})
    return result is None


class CookieJWTAuthentication(BaseAuthentication):
    """Authenticate requests via JWT stored in HTTP-only cookies.

    Falls back to ``Authorization: Bearer <token>`` header for
    backward compatibility during the transition period (see MIGRATION.md).

    Cookie names are configured via ``SIMPLE_JWT["AUTH_COOKIE"]``
    and ``SIMPLE_JWT["AUTH_COOKIE_REFRESH"]``.
    """

    www_authenticate_realm = "api"

    def authenticate(self, request):
        cookie_name = settings.SIMPLE_JWT.get("AUTH_COOKIE", "mcc_access")
        header_token = self._get_header_token(request)
        cookie_token = request.COOKIES.get(cookie_name)

        raw_token = cookie_token or header_token
        if raw_token is None:
            return None

        try:
            validated_token = JWTAuthentication().get_validated_token(raw_token)
        except (InvalidToken, TokenError):
            raise AuthenticationFailed("Token is invalid or expired.")

        if cookie_token and not _check_csrf(request):
            # Cookie present but CSRF missing — treat as unauthenticated
            # rather than raising (which would mask 401 with 403).
            return None

        user = JWTAuthentication().get_user(validated_token)
        return (user, validated_token)

    def authenticate_header(self, request):
        """Return WWW-Authenticate header so DRF keeps 401 status."""
        return 'Bearer realm="%s"' % self.www_authenticate_realm

    @staticmethod
    def _get_header_token(request):
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if auth.lower().startswith("bearer "):
            return auth[7:]
        return None
