from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny

from apps.specialties.models import Specialty
from apps.specialties.serializers import SpecialtyListSerializer, SpecialtySerializer


class SpecialtyViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Public active-specialty list plus historical detail lookup."""

    queryset = Specialty.objects.all()
    lookup_field = "id"
    pagination_class = None  # return all specialties — small, static dataset

    def get_queryset(self):
        queryset = Specialty.objects.all()
        if self.action == "list":
            return queryset.filter(is_active=True)
        return queryset

    def get_serializer_class(self):
        if self.action == "list":
            return SpecialtyListSerializer
        return SpecialtySerializer

    def get_permissions(self):
        return [AllowAny()]
