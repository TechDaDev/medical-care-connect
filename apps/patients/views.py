from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import IsPatient
from apps.patients.models import PatientProfile
from apps.patients.serializers import (
    PatientProfileDetailSerializer,
    PatientProfileSerializer,
)


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated, IsPatient])
def my_patient_profile(request: Request) -> Response:
    """Get or update the authenticated patient's own profile.

    GET  → return full profile with user info.
    PATCH → update profile fields (not user fields).
    """
    profile = getattr(request.user, "patient_profile", None)
    if profile is None:
        return Response(
            {"detail": "Patient profile not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        serializer = PatientProfileDetailSerializer(profile)
        return Response(serializer.data)

    # PATCH
    serializer = PatientProfileSerializer(profile, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    # Return full detail after update
    detail_serializer = PatientProfileDetailSerializer(profile)
    return Response(detail_serializer.data)
