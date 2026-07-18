from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated

from apps.specialties.models import Specialty
from apps.specialties.serializers import SpecialtyListSerializer, SpecialtySerializer


class SpecialtyViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """ViewSet for listing, retrieving, creating, and updating specialties.

    * List / Retrieve — public (no auth required).
    * Create / Update — administrators only.
    """

    queryset = Specialty.objects.all()
    lookup_field = "id"
    pagination_class = None  # return all specialties — small, static dataset

    def get_serializer_class(self):
        if self.action == "list":
            return SpecialtyListSerializer
        return SpecialtySerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [AllowAny()]
        return [IsAuthenticated()]
