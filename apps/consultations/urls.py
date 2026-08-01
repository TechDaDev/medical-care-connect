from django.urls import path

from apps.consultations import views
from apps.medical_records import views as medical_record_views

app_name = "consultations"

urlpatterns = [
    path("", views.consultation_collection, name="list"),
    path("doctor/", views.doctor_consultation_queue, name="doctor-list"),
    path("<uuid:pk>/", views.consultation_detail, name="detail"),
    path("<uuid:pk>/doctor/", views.doctor_consultation_detail, name="doctor-detail"),
    path("<uuid:pk>/doctor-intake/", views.doctor_consultation_intake, name="doctor-intake"),
    path("<uuid:pk>/accept/", views.accept_consultation, name="accept"),
    path("<uuid:pk>/doctor-transition/", views.doctor_consultation_transition, name="doctor-transition"),
    path(
        "<uuid:consultation_id>/medical-record/",
        medical_record_views.create_consultation_medical_record,
        name="doctor-medical-record-create",
    ),
    path("<uuid:pk>/cancel/", views.cancel_consultation, name="cancel"),
    path(
        "<uuid:pk>/intake/start/",
        views.start_intake,
        name="intake-start",
    ),
]
