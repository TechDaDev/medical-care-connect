from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import IsDoctor
from apps.doctors.models import DoctorProfile
from apps.doctors.serializers import (
    DoctorProfileDetailSerializer,
    DoctorProfileSerializer,
)


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated, IsDoctor])
def my_doctor_profile(request: Request) -> Response:
    """Get or update the authenticated doctor's own profile.

    GET  → return full profile with user and specialty info.
    PATCH → update profile fields (not user fields).
            Doctor cannot change is_approved or user via this endpoint.
    """
    profile = getattr(request.user, "doctor_profile", None)
    if profile is None:
        return Response(
            {"detail": "Doctor profile not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        serializer = DoctorProfileDetailSerializer(profile)
        return Response(serializer.data)

    # PATCH
    serializer = DoctorProfileSerializer(profile, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    detail_serializer = DoctorProfileDetailSerializer(profile)
    return Response(detail_serializer.data)
