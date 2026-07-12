from django.urls import path

from apps.staff import views

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
]
