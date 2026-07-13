from django.contrib import admin
from django.urls import include, path

from apps.core.views import health, readiness

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/readiness/", readiness, name="readiness"),
    path("api/", include("apps.accounts.urls")),
    path("api/patients/", include("apps.patients.urls")),
    path("api/doctors/", include("apps.doctors.urls")),
    path("api/specialties/", include("apps.specialties.urls")),
    path("api/consultations/", include("apps.consultations.urls")),
    path("api/intake/", include("apps.ai_intake.urls")),
    path("api/medical-records/", include("apps.medical_records.urls")),
    path("api/messaging/", include("apps.messaging.urls")),
    path("api/notifications/", include("apps.notifications.urls")),
    path("api/staff/", include("apps.staff.urls")),
    path("api/", include("apps.attachments.urls")),
    path("api/privacy/", include("apps.privacy.urls")),
]
