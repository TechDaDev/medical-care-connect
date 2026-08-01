from rest_framework import serializers

from apps.attachments.choices import AttachmentCategory, AttachmentStatus, ScanStatus
from apps.attachments.models import ConsultationAttachment


class AttachmentUploadSerializer(serializers.Serializer):
    """Validates multipart upload fields."""

    file = serializers.FileField()
    category = serializers.ChoiceField(choices=AttachmentCategory.choices)
    description = serializers.CharField(required=False, allow_blank=True, default="")


class AttachmentListSerializer(serializers.ModelSerializer):
    """Safe metadata for listing — no storage_key or path."""

    uploader_name = serializers.SerializerMethodField()
    uploader_role = serializers.CharField(source="uploaded_by.role", read_only=True, default=None)
    actions = serializers.SerializerMethodField()
    category_label = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()
    scan_status_label = serializers.SerializerMethodField()

    class Meta:
        model = ConsultationAttachment
        fields = [
            "id",
            "consultation_id",
            "uploader_name",
            "uploader_role",
            "original_filename",
            "safe_display_name",
            "category",
            "category_label",
            "description",
            "size_bytes",
            "detected_mime_type",
            "status",
            "status_label",
            "scan_status",
            "scan_status_label",
            "created_at",
            "updated_at",
            "actions",
        ]
        read_only_fields = fields

    def get_uploader_name(self, obj) -> str:
        if not obj.uploaded_by:
            return ""
        return obj.uploaded_by.full_name

    def get_actions(self, obj) -> dict:
        from apps.attachments.permissions import get_attachment_actions
        request = self.context.get("request")
        if request and request.user:
            return get_attachment_actions(obj, request.user)
        return {"can_download": False, "can_delete": False, "can_restore": False, "can_view_audit": False}

    def get_category_label(self, obj) -> str:
        return obj.get_category_display()

    def get_status_label(self, obj) -> str:
        return obj.get_status_display()

    def get_scan_status_label(self, obj) -> str:
        return obj.get_scan_status_display()
