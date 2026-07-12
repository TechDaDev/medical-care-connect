from rest_framework import serializers

from apps.doctors.models import DoctorProfile


class DoctorProfileSerializer(serializers.ModelSerializer):
    """Serializer for the DoctorProfile model (write)."""

    class Meta:
        model = DoctorProfile
        fields = [
            "id",
            "user",
            "specialty",
            "professional_title",
            "license_number",
            "qualifications",
            "biography",
            "years_of_experience",
            "consultation_fee",
            "languages",
            "is_approved",
            "is_accepting_consultations",
            "estimated_response_minutes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id", "user", "is_approved", "created_at", "updated_at",
        ]


class DoctorProfileDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer including user info and specialty details."""

    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    phone_number = serializers.CharField(source="user.phone_number", read_only=True)
    specialty_name = serializers.CharField(
        source="specialty.name", read_only=True, default=None
    )

    class Meta:
        model = DoctorProfile
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone_number",
            "specialty",
            "specialty_name",
            "professional_title",
            "license_number",
            "qualifications",
            "biography",
            "years_of_experience",
            "consultation_fee",
            "languages",
            "is_approved",
            "is_accepting_consultations",
            "estimated_response_minutes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
