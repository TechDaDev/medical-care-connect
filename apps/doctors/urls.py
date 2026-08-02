from django.urls import path

from apps.doctors import phase_d_views, views
from apps.medical_records import views as medical_record_views

app_name = "doctors"

urlpatterns = [
    # My profile (authenticated doctor)
    path("me/", views.my_doctor_profile, name="my-profile"),
    path("me/access-state/", views.my_doctor_access_state, name="my-access-state"),
    path("me/dashboard/", views.my_doctor_dashboard, name="my-dashboard"),
    path("me/message-threads/", phase_d_views.doctor_message_threads, name="my-message-threads"),
    path("me/notifications/", phase_d_views.doctor_notifications, name="my-notifications"),
    path("me/notifications/read-all/", phase_d_views.doctor_notifications_read_all, name="my-notifications-read-all"),
    path("me/notifications/<uuid:notification_id>/read/", phase_d_views.doctor_notification_read, name="my-notification-read"),
    path("me/reviews/", phase_d_views.doctor_reviews, name="my-reviews"),
    path("me/reviews/<uuid:review_id>/response/", phase_d_views.doctor_review_response, name="my-review-response"),
    path("me/privacy/", phase_d_views.doctor_privacy_overview, name="my-privacy"),
    path("me/privacy/exports/", phase_d_views.doctor_privacy_exports, name="my-privacy-exports"),
    path("me/privacy/exports/<uuid:export_id>/download/", phase_d_views.doctor_privacy_export_download, name="my-privacy-export-download"),
    path("me/privacy/deletion/", phase_d_views.doctor_privacy_deletion_requests, name="my-privacy-deletion"),
    path("me/privacy/deletion/<uuid:deletion_id>/cancel/", phase_d_views.doctor_privacy_deletion_cancel, name="my-privacy-deletion-cancel"),
    path(
        "me/medical-records/",
        medical_record_views.doctor_medical_record_list,
        name="my-medical-record-list",
    ),
    path(
        "me/medical-records/<uuid:record_id>/",
        medical_record_views.doctor_medical_record_detail,
        name="my-medical-record-detail",
    ),
    path(
        "me/medical-records/<uuid:record_id>/finalize/",
        medical_record_views.finalize_doctor_medical_record,
        name="my-medical-record-finalize",
    ),
    # My availability
    path("me/availability/", views.my_availability_list, name="my-availability-list"),
    path("me/availability/<uuid:pk>/", views.my_availability_detail, name="my-availability-detail"),
    # Accepting status
    path("me/availability-status/", views.update_accepting_status, name="my-availability-status"),
    # Public directory
    path("", views.public_doctor_list, name="doctor-list"),
    path("<uuid:pk>/", views.public_doctor_detail, name="doctor-detail"),
]
