from django.contrib import admin

from apps.consultations.models import Consultation


@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "patient",
        "doctor",
        "specialty",
        "status",
        "priority",
        "submitted_at",
        "accepted_at",
    )
    list_filter = ("status", "priority", "specialty")
    search_fields = (
        "patient__user__email",
        "doctor__user__email",
        "description",
    )
    raw_id_fields = ("patient", "doctor", "specialty")
    readonly_fields = (
        "created_at",
        "updated_at",
        "submitted_at",
        "accepted_at",
        "cancelled_at",
    )
