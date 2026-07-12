from django.urls import path

from apps.doctors import views

app_name = "doctors"

urlpatterns = [
    # My profile (authenticated doctor)
    path("me/", views.my_doctor_profile, name="my-profile"),
    path("me/dashboard/", views.my_doctor_dashboard, name="my-dashboard"),
    # My availability
    path("me/availability/", views.my_availability_list, name="my-availability-list"),
    path("me/availability/<uuid:pk>/", views.my_availability_detail, name="my-availability-detail"),
    # Accepting status
    path("me/availability-status/", views.update_accepting_status, name="my-availability-status"),
    # Public directory
    path("", views.public_doctor_list, name="doctor-list"),
    path("<uuid:pk>/", views.public_doctor_detail, name="doctor-detail"),
]
