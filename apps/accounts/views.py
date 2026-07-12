from django.conf import settings
from django.db import connections
from django.db.utils import OperationalError
from django.middleware.csrf import get_token as get_csrf_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import exceptions, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from apps.accounts.serializers import (
    CurrentUserSerializer,
    LoginSerializer,
    RegisterPatientSerializer,
    UpdateUserSerializer,
)
from apps.accounts.throttles import (
    LoginRateThrottle,
    RefreshRateThrottle,
    RegisterRateThrottle,
)
from apps.accounts.utils import clear_auth_cookies, set_auth_cookies


# ── Health ──────────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request: Request) -> Response:
    return Response({"status": "healthy"})


@api_view(["GET"])
@permission_classes([AllowAny])
def readiness_check(request: Request) -> Response:
    db_available = False
    try:
        conn = connections["default"]
        conn.ensure_connection()
        db_available = True
    except OperationalError:
        db_available = False

    ai_status = "disabled"
    if settings.AI_INTAKE_ENABLED:
        ai_status = "enabled" if settings.DEEPSEEK_API_KEY else "misconfigured"

    result = {
        "status": "ready" if db_available else "unavailable",
        "database": "available" if db_available else "unavailable",
        "ai_intake": ai_status,
    }

    if not db_available:
        return Response(result, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response(result)


# ── Current User ────────────────────────────────────────────────────────────

@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def current_user(request: Request) -> Response:
    if request.method == "GET":
        serializer = CurrentUserSerializer(request.user)
        return Response(serializer.data)

    serializer = UpdateUserSerializer(request.user, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(CurrentUserSerializer(request.user).data)


# ── Register ────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([RegisterRateThrottle])
@csrf_exempt
def register_patient(request: Request) -> Response:
    """Register a new patient account.

    Sets JWT HTTP-only cookies on success.
    Returns serialized user data (no raw tokens in JSON body).
    """
    serializer = RegisterPatientSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()

    refresh = RefreshToken.for_user(user)
    data = {"user": CurrentUserSerializer(user).data}
    response = Response(data, status=status.HTTP_201_CREATED)
    set_auth_cookies(response, str(refresh.access_token), str(refresh))
    return response


# ── Login ───────────────────────────────────────────────────────────────────

@method_decorator(csrf_exempt, name="dispatch")
class LoginView(TokenObtainPairView):
    """Log in with email and password.

    CSRF-exempt because login establishes authentication (no existing cookie
    to forge). CSRF cookie is set in the response for subsequent requests.
    Sets JWT HTTP-only cookies on success.
    Returns serialized user data (no raw tokens in JSON body).
    Rejects inactive accounts.
    """
    serializer_class = LoginSerializer
    throttle_classes = [LoginRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except exceptions.ValidationError:
            return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)
        except Exception:
            return Response(
                {"detail": "Unable to log in with provided credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        tokens = getattr(serializer, "tokens", None)
        response_data = {"user": serializer.validated_data.get("user", {})}
        response = Response(response_data, status=status.HTTP_200_OK)

        if tokens:
            set_auth_cookies(response, tokens["access"], tokens["refresh"])
        return response


# ── Token Refresh (cookie-aware) ───────────────────────────────────────────

@method_decorator(csrf_exempt, name="dispatch")
class CookieTokenRefreshView(TokenRefreshView):
    """Refresh access token using refresh token from HTTP-only cookie.

    Also accepts ``refresh`` in JSON body for backward compatibility.
    """
    throttle_classes = [RefreshRateThrottle]

    def finalize_response(self, request, response, *args, **kwargs):
        if response.status_code == status.HTTP_200_OK:
            access_token = response.data.get("access")
            if access_token:
                set_auth_cookies(response, access_token, refresh_token=None)
                # If refresh came from cookie, return empty body
                has_refresh_in_body = "refresh" in request.data
                if not has_refresh_in_body:
                    response.data = {}
        return super().finalize_response(request, response, *args, **kwargs)


# ── Logout ─────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request: Request) -> Response:
    """Log out by blacklisting the refresh token and clearing cookies.

    Fully idempotent:
    * always clears both cookies
    * attempts blacklisting when a refresh token is present
    * never returns 400 — success even when cookie is missing/expired/invalid
    """
    refresh_token = request.COOKIES.get(
        settings.SIMPLE_JWT.get("AUTH_COOKIE_REFRESH", "mcc_refresh")
    ) or request.data.get("refresh")

    if refresh_token:
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except (TokenError, InvalidToken):
            pass  # Invalid/expired — still clear cookies

    response = Response({"detail": "Successfully logged out."})
    clear_auth_cookies(response)
    return response


# ── CSRF Token ──────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([AllowAny])
def csrf_token(request: Request) -> Response:
    """Obtain a CSRF token cookie for the current session.

    Sets the ``mcc_csrftoken`` cookie (readable by JavaScript) so the
    frontend can include it as ``X-CSRFToken`` on state-changing requests.
    """
    get_csrf_token(request)  # Sets the cookie as a side effect
    return Response({"detail": "CSRF cookie set."})
