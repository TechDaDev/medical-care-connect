from django.contrib import admin

from apps.patients.models import PatientProfile


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "gender", "blood_type", "preferred_language", "created_at")
    list_filter = ("gender", "blood_type", "preferred_language")
    search_fields = ("user__email", "user__first_name", "user__last_name", "emergency_contact_name")
    raw_id_fields = ("user",)
