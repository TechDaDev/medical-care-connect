from django.urls import path

from apps.consultations import views

app_name = "consultations"

urlpatterns = [
    path("", views.list_consultations, name="list"),
    path("<uuid:pk>/", views.consultation_detail, name="detail"),
    path("create/", views.create_consultation, name="create"),
    path("<uuid:pk>/accept/", views.accept_consultation, name="accept"),
    path("<uuid:pk>/cancel/", views.cancel_consultation, name="cancel"),
]
