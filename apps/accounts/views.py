from django.db import connections
from django.db.utils import OperationalError
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.accounts.serializers import (
    CurrentUserSerializer,
    LoginSerializer,
    RegisterPatientSerializer,
    UpdateUserSerializer,
)
from apps.accounts.permissions import IsPatient


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request: Request) -> Response:
    """Basic health check endpoint."""
    return Response({"status": "healthy"})


@api_view(["GET"])
@permission_classes([AllowAny])
def readiness_check(request: Request) -> Response:
    """Readiness probe — checks database and AI intake config.

    Never exposes secrets or stack traces.
    """
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


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def current_user(request: Request) -> Response:
    """Return or update the currently authenticated user's profile.

    GET  → return current user data.
    PATCH → update first_name, last_name, phone_number.
    """
    if request.method == "GET":
        serializer = CurrentUserSerializer(request.user)
        return Response(serializer.data)

    # PATCH – allow partial update of basic profile fields
    serializer = UpdateUserSerializer(request.user, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(CurrentUserSerializer(request.user).data)


@api_view(["POST"])
@permission_classes([AllowAny])
def register_patient(request: Request) -> Response:
    """Register a new patient account.

    Creates the user with role=patient and a linked PatientProfile.
    Returns JWT tokens and serialized user data.
    """
    serializer = RegisterPatientSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()

    refresh = RefreshToken.for_user(user)
    return Response(
        {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": CurrentUserSerializer(user).data,
        },
        status=status.HTTP_201_CREATED,
    )


class LoginView(TokenObtainPairView):
    """Log in with email and password.

    Returns access token, refresh token, and serialized user data.
    Rejects inactive accounts.
    """
    serializer_class = LoginSerializer


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request: Request) -> Response:
    """Log out by blacklisting the refresh token.

    Requires authentication. Accepts the refresh token in the request body.
    """
    try:
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"detail": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        token = RefreshToken(refresh_token)
        token.blacklist()
        return Response({"detail": "Successfully logged out."})
    except Exception:
        return Response(
            {"detail": "Invalid or expired refresh token."},
            status=status.HTTP_400_BAD_REQUEST,
        )
