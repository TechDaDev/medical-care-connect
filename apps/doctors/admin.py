from django.contrib import admin

from apps.doctors.models import DoctorAvailability, DoctorProfile


@admin.register(DoctorProfile)
class DoctorProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "specialty",
        "professional_title",
        "is_approved",
        "is_accepting_consultations",
        "years_of_experience",
    )
    list_filter = ("is_approved", "is_accepting_consultations", "specialty")
    search_fields = ("user__email", "user__first_name", "user__last_name", "license_number")
    raw_id_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(DoctorAvailability)
class DoctorAvailabilityAdmin(admin.ModelAdmin):
    list_display = ("doctor", "day_of_week", "start_time", "end_time", "is_active")
    list_filter = ("day_of_week", "is_active")
    search_fields = ("doctor__user__email", "doctor__user__first_name", "doctor__user__last_name")
    raw_id_fields = ("doctor",)
