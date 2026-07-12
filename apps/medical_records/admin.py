from django.contrib import admin

from apps.medical_records.models import MedicalRecordDraft


@admin.register(MedicalRecordDraft)
class MedicalRecordDraftAdmin(admin.ModelAdmin):
    list_display = [
        "id", "consultation", "status", "severity", "finalized_at",
    ]
    list_filter = ["status"]
    search_fields = ["consultation__id", "chief_complaint"]
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = [
        ("Summary", {"fields": [
            "consultation", "intake_session", "status",
        ]}),
        ("Clinical", {"fields": [
            "chief_complaint", "history_of_present_illness",
            "symptoms", "severity", "onset_date", "duration",
            "location", "triggers", "relieving_factors",
        ]}),
        ("History", {"fields": [
            "past_medical_history", "medications", "allergies",
            "family_history", "social_history", "review_of_systems",
        ]}),
        ("Notes", {"fields": [
            "additional_notes", "doctor_notes",
        ]}),
        ("Timestamps", {"fields": [
            "finalized_at", "created_at", "updated_at",
        ]}),
    ]
