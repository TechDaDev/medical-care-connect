from django.urls import path

from apps.patients import views

app_name = "patients"

urlpatterns = [
    path("me/", views.my_patient_profile, name="my-profile"),
]
