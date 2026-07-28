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


class DeletionRequestCreateSerializer(serializers.Serializer):
    reason = serializers.CharField(
        min_length=10,
        max_length=1000,
        trim_whitespace=True,
    )
    confirmation = serializers.BooleanField(required=True)

    def validate_confirmation(self, value):
        if value is not True:
            raise serializers.ValidationError("Explicit confirmation is required.")
        return value


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
    action = serializers.ChoiceField(
        choices=["approve", "reject"], required=False, default="approve"
    )
    rejection_reason = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=500
    )
    expected_status = serializers.CharField(required=False, default=None)

    def validate_rejection_reason(self, value):
        action = self.initial_data.get("action", "approve")
        if action == "reject":
            stripped = value.strip() if value else ""
            if len(stripped) < 10:
                raise serializers.ValidationError(
                    "Reason must be at least 10 characters for rejection."
                )
            return stripped
        return value


class DeactivationSerializer(serializers.Serializer):
    password = serializers.CharField(required=True, write_only=True)
