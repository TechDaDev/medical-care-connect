from django.urls import path

from apps.doctors import views
from apps.medical_records import views as medical_record_views

app_name = "doctors"

urlpatterns = [
    # My profile (authenticated doctor)
    path("me/", views.my_doctor_profile, name="my-profile"),
    path("me/access-state/", views.my_doctor_access_state, name="my-access-state"),
    path("me/dashboard/", views.my_doctor_dashboard, name="my-dashboard"),
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
