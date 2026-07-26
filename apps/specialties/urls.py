from django.urls import path

from apps.specialties.views import SpecialtyViewSet

app_name = "specialties"

urlpatterns = [
    path("", SpecialtyViewSet.as_view({"get": "list"}), name="specialty-list"),
    path(
        "<uuid:id>/",
        SpecialtyViewSet.as_view({"get": "retrieve"}),
        name="specialty-detail",
    ),
]
