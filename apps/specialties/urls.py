from django.urls import path

from apps.specialties.views import SpecialtyViewSet

app_name = "specialties"

urlpatterns = [
    path("", SpecialtyViewSet.as_view({"get": "list", "post": "create"}), name="specialty-list"),
    path(
        "<uuid:id>/",
        SpecialtyViewSet.as_view({"get": "retrieve", "patch": "partial_update", "put": "update"}),
        name="specialty-detail",
    ),
]
