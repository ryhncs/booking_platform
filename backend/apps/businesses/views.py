from django.db.models import ProtectedError, Q
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import SAFE_METHODS

from apps.core.exceptions import Conflict

from .models import Business, Service, Staff, WorkingHours
from .permissions import IsOwnerOrReadOnly
from .serializers import (
    BusinessSerializer,
    ServiceSerializer,
    StaffSerializer,
    WorkingHoursSerializer,
)


class CatalogViewSet(viewsets.ModelViewSet):
    """Readable by any signed-in user, writable only by the owning owner.

    Writes are scoped to ``owner_lookup == request.user``, so another owner's
    objects behave as if they don't exist (404) rather than revealing them.
    """

    permission_classes = [IsOwnerOrReadOnly]
    owner_lookup: str
    # query param -> ORM lookup, e.g. ?business=3
    filter_params: dict[str, str] = {}

    def get_queryset(self):
        qs = self.queryset.all()
        if self.request.method not in SAFE_METHODS:
            qs = qs.filter(**{self.owner_lookup: self.request.user})
        for param, lookup in self.filter_params.items():
            raw = self.request.query_params.get(param)
            if raw is None:
                continue
            try:
                qs = qs.filter(**{lookup: int(raw)})
            except ValueError:
                raise ValidationError({param: "Must be an integer."}) from None
        return qs

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise Conflict("Cannot delete: it still has bookings.") from None


class BusinessViewSet(CatalogViewSet):
    queryset = Business.objects.order_by("name")
    serializer_class = BusinessSerializer
    owner_lookup = "owner"

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("mine") in ("1", "true"):
            qs = qs.filter(owner=self.request.user)
        return qs

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class StaffViewSet(CatalogViewSet):
    queryset = Staff.objects.select_related("business").order_by("display_name")
    serializer_class = StaffSerializer
    owner_lookup = "business__owner"
    filter_params = {"business": "business_id"}

    def get_queryset(self):
        qs = super().get_queryset()
        # Customers only see bookable staff; owners also see their inactive ones.
        return qs.filter(Q(is_active=True) | Q(business__owner=self.request.user))


class ServiceViewSet(CatalogViewSet):
    queryset = Service.objects.prefetch_related("staff").order_by("name")
    serializer_class = ServiceSerializer
    owner_lookup = "business__owner"
    filter_params = {"business": "business_id", "staff": "staff"}

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(Q(is_active=True) | Q(business__owner=self.request.user))


class WorkingHoursViewSet(CatalogViewSet):
    queryset = WorkingHours.objects.select_related("staff__business")
    serializer_class = WorkingHoursSerializer
    owner_lookup = "staff__business__owner"
    filter_params = {"staff": "staff_id"}
