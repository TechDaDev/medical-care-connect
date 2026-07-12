from rest_framework import serializers

from apps.patients.models import PatientProfile


class PatientProfileSerializer(serializers.ModelSerializer):
    """Serializer for the PatientProfile model."""

    class Meta:
        model = PatientProfile
        fields = [
            "id",
            "user",
            "date_of_birth",
            "gender",
            "preferred_language",
            "address",
            "emergency_contact_name",
            "emergency_contact_phone",
            "blood_type",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "created_at", "updated_at"]


class PatientProfileDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer including user info."""

    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    phone_number = serializers.CharField(source="user.phone_number", read_only=True)

    class Meta:
        model = PatientProfile
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone_number",
            "date_of_birth",
            "gender",
            "preferred_language",
            "address",
            "emergency_contact_name",
            "emergency_contact_phone",
            "blood_type",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
