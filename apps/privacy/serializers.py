"""Privacy serializers — no storage keys or secrets exposed."""

from rest_framework import serializers

from apps.privacy.models import DataExportRequest, AccountDeletionRequest, ExportStatus, DeletionStatus


class DataExportRequestSerializer(serializers.ModelSerializer):
    """Safe metadata — no storage_key, no path, no checksum."""

    class Meta:
        model = DataExportRequest
        fields = [
            "id",
            "status",
            "requested_at",
            "started_at",
            "completed_at",
            "expires_at",
            "size_bytes",
            "failure_code",
        ]
        read_only_fields = fields


class DataExportCreateSerializer(serializers.Serializer):
    pass  # No input fields — server sets subject_user


class AccountDeletionRequestSerializer(serializers.ModelSerializer):
    """Safe metadata for deletion requests."""

    class Meta:
        model = AccountDeletionRequest
        fields = [
            "id",
            "status",
            "reason",
            "requested_at",
            "reviewed_at",
            "rejection_reason",
        ]
        read_only_fields = [
            "id", "status", "requested_at", "reviewed_at", "rejection_reason",
        ]


class AccountDeletionReviewSerializer(serializers.Serializer):
    rejection_reason = serializers.CharField(required=False, allow_blank=True, default="")


class DeactivationSerializer(serializers.Serializer):
    password = serializers.CharField(required=True, write_only=True)
