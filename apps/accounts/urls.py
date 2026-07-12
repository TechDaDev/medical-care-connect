from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    # Health
    path("health/", views.health_check, name="health-check"),
    path("readiness/", views.readiness_check, name="readiness"),
    # Auth
    path("auth/register/patient/", views.register_patient, name="register-patient"),
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/token/refresh/", views.CookieTokenRefreshView.as_view(), name="token-refresh"),
    path("auth/logout/", views.logout_view, name="logout"),
    path("auth/csrf/", views.csrf_token, name="csrf"),
    # Current user
    path("accounts/me/", views.current_user, name="current-user"),
]
