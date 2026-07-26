from rest_framework import serializers

from apps.specialties.models import Specialty


class SpecialtySerializer(serializers.ModelSerializer):
    """Serializer for the Specialty model."""

    class Meta:
        model = Specialty
        fields = [
            "id",
            "name",
            "name_en",
            "name_ar",
            "name_ckb",
            "slug",
            "description",
            "is_active",
            "display_order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "name", "slug", "created_at", "updated_at"]


class SpecialtyListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing specialties."""

    class Meta:
        model = Specialty
        fields = [
            "id", "name", "name_en", "name_ar", "name_ckb", "slug",
            "description", "is_active", "display_order",
        ]
