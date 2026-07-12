from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("health/", views.health_check, name="health-check"),
    path("accounts/me/", views.current_user, name="current-user"),
]
