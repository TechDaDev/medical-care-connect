from django.urls import path

from apps.doctors import views

app_name = "doctors"

urlpatterns = [
    path("me/", views.my_doctor_profile, name="my-profile"),
]
