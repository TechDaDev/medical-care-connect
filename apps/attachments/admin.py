from django.contrib import admin

from apps.attachments.models import AttachmentAuditEvent, ConsultationAttachment, MedicalRecordAttachment


@admin.register(ConsultationAttachment)
class ConsultationAttachmentAdmin(admin.ModelAdmin):
    list_display = ["id", "consultation_id", "original_filename", "category", "status", "scan_status", "size_bytes", "created_at"]
    list_filter = ["status", "scan_status", "category", "storage_provider"]
    search_fields = ["original_filename", "sha256"]
    readonly_fields = [
        "id", "storage_key", "sha256", "created_at", "updated_at",
        "storage_provider", "size_bytes", "detected_mime_type",
    ]
    raw_id_fields = ["consultation", "uploaded_by", "deleted_by"]
    list_select_related = ["consultation", "uploaded_by"]

    def has_add_permission(self, request):
        return False


@admin.register(AttachmentAuditEvent)
class AttachmentAuditEventAdmin(admin.ModelAdmin):
    list_display = ["id", "attachment_id", "event_type", "actor", "created_at"]
    list_filter = ["event_type"]
    readonly_fields = ["attachment", "actor", "event_type", "safe_metadata", "request_ip_hash", "created_at"]
    search_fields = ["attachment_id"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MedicalRecordAttachment)
class MedicalRecordAttachmentAdmin(admin.ModelAdmin):
    list_display = ["id", "medical_record_id", "attachment_id", "added_by", "created_at"]
    raw_id_fields = ["medical_record", "attachment", "added_by"]
    readonly_fields = ["created_at"]
