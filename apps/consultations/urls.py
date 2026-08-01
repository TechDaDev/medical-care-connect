from django.urls import path

from apps.consultations import views

app_name = "consultations"

urlpatterns = [
    path("", views.consultation_collection, name="list"),
    path("doctor/", views.doctor_consultation_queue, name="doctor-list"),
    path("<uuid:pk>/", views.consultation_detail, name="detail"),
    path("<uuid:pk>/doctor/", views.doctor_consultation_detail, name="doctor-detail"),
    path("<uuid:pk>/doctor-intake/", views.doctor_consultation_intake, name="doctor-intake"),
    path("<uuid:pk>/accept/", views.accept_consultation, name="accept"),
    path("<uuid:pk>/doctor-transition/", views.doctor_consultation_transition, name="doctor-transition"),
    path("<uuid:pk>/cancel/", views.cancel_consultation, name="cancel"),
    path(
        "<uuid:pk>/intake/start/",
        views.start_intake,
        name="intake-start",
    ),
]
