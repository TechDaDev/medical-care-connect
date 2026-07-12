from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.serializers import CurrentUserSerializer


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request: Request) -> Response:
    """Basic health check endpoint. No authentication required."""
    return Response({"status": "healthy"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def current_user(request: Request) -> Response:
    """Return the currently authenticated user's profile."""
    serializer = CurrentUserSerializer(request.user)
    return Response(serializer.data)
