from django.contrib import admin

from apps.privacy.models import DataExportRequest, AccountDeletionRequest


@admin.register(DataExportRequest)
class DataExportRequestAdmin(admin.ModelAdmin):
    list_display = ["id", "subject_user", "status", "requested_at", "completed_at"]
    list_filter = ["status"]
    readonly_fields = ["storage_key", "checksum"]
    search_fields = ["subject_user__email"]


@admin.register(AccountDeletionRequest)
class AccountDeletionRequestAdmin(admin.ModelAdmin):
    list_display = ["id", "subject_user", "status", "requested_at", "reviewed_at"]
    list_filter = ["status"]
    search_fields = ["subject_user__email"]
