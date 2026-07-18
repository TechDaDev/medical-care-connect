from django.urls import path

from apps.staff import views
from apps.core.views import operations_status, operations_metrics
from apps.privacy.views import deletion_approve, deletion_reject
from apps.reviews.views import staff_moderate_review, staff_review_list, staff_report_list, staff_resolve_report

app_name = "staff"

urlpatterns = [
    path("dashboard/", views.staff_dashboard, name="dashboard"),
    path("consultations/", views.staff_consultation_list, name="consultation-list"),
    path(
        "consultations/<uuid:consultation_id>/transfer/",
        views.transfer_consultation,
        name="consultation-transfer",
    ),
    path(
        "consultations/<uuid:consultation_id>/priority/",
        views.update_priority,
        name="consultation-priority",
    ),
    path("doctors/workload/", views.doctor_workload, name="doctor-workload"),
    path("doctors/applications/", views.doctor_application_list, name="doctor-application-list"),
    path("doctors/applications/<uuid:profile_id>/review/", views.review_doctor_application, name="doctor-application-review"),
    path("operations/status/", operations_status, name="operations-status"),
    path("operations/metrics/", operations_metrics, name="operations-metrics"),
    path("privacy/deletion-requests/<uuid:id>/approve/", deletion_approve, name="deletion-approve"),
    path("privacy/deletion-requests/<uuid:id>/reject/", deletion_reject, name="deletion-reject"),
    # Reviews / Moderation
    path("reviews/", staff_review_list, name="staff-review-list"),
    path("reviews/<uuid:review_id>/moderate/", staff_moderate_review, name="staff-review-moderate"),
    path("reviews/reports/", staff_report_list, name="staff-report-list"),
    path("reviews/reports/<uuid:report_id>/resolve/", staff_resolve_report, name="staff-report-resolve"),
]
