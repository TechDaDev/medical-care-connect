from django.urls import path

from apps.staff import views
from apps.core.views import operations_status, operations_metrics
from apps.privacy.views import deletion_approve, deletion_reject

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
    path("operations/status/", operations_status, name="operations-status"),
    path("operations/metrics/", operations_metrics, name="operations-metrics"),
    path("privacy/deletion-requests/<uuid:id>/approve/", deletion_approve, name="deletion-approve"),
    path("privacy/deletion-requests/<uuid:id>/reject/", deletion_reject, name="deletion-reject"),
]
